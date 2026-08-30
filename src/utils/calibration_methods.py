"""校准方法库扩展（协议§5方法池 M1-M13）

统一接口：fit_X(input, labels) -> params；apply_X(input, params) -> calibrated_probs_2d
logit纪律：概率输入内部clip[1e-12,1]后取log（饱和区防护，对抗审查结论）

方法清单：
- isotonic:  per-class OvR IsotonicRegression（小样本防护：n_cal < 10K返回None）
- vector:    对角scale + bias（2K参数）
- matrix:    全矩阵scale + bias（K²+K参数，小样本预期失效）
- dirichlet: Kull et al. 2019，log概率空间仿射映射（特征增强+multinomial LR）
- saerens:   Saerens et al. 2002 EM先验估计（无标签）+ 先验校正
- oracle:    目标域cal上拟合温度（上界）

注册表 CALIBRATION_METHODS 供实验runner遍历。
"""

import warnings
from typing import Dict, Optional, Tuple, Callable

import numpy as np
from scipy.optimize import minimize
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

EPS = 1e-12
SCALE_MIN, SCALE_MAX = 0.05, 20.0
BIAS_MIN, BIAS_MAX = -10.0, 10.0


def _to_logits(probs: np.ndarray) -> np.ndarray:
    """概率→logits（2D，行独立，饱和防护）"""
    p = np.clip(np.asarray(probs, dtype=float), EPS, 1.0)
    return np.log(p)


def _to_probs(logits: np.ndarray) -> np.ndarray:
    """logits→概率（数值稳定softmax）"""
    z = np.asarray(logits, dtype=float)
    z = z - z.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)


def _nll(logits: np.ndarray, labels_onehot: np.ndarray) -> float:
    """多分类NLL（logits, one-hot (n,K)）"""
    z = logits - logits.max(axis=1, keepdims=True)
    logp = z - np.log(np.exp(z).sum(axis=1, keepdims=True))
    return float(-(logp * labels_onehot).sum(axis=1).mean())


# =====================================================================
# 1. Isotonic (OvR)
# =====================================================================

def fit_isotonic(val_probs: np.ndarray, val_labels: np.ndarray,
                 min_per_class: int = 10) -> Optional[dict]:
    """per-class one-vs-rest isotonic回归

    小样本防护（协议预注册：isotonic在n_cal≤100失效；修复HIGH-3 off-by-one：
    原守卫 n<10*K 在n_cal=50,K=5时恰好不触发）。
    """
    val_probs = np.asarray(val_probs, dtype=float)
    val_labels = np.asarray(val_labels)
    n, K = val_probs.shape
    _assert_labels_valid(val_labels, K)
    if n <= min_per_class * K:  # 修复：<= 防off-by-one
        warnings.warn(f"fit_isotonic: n_cal={n} <= 10*K={min_per_class*K}，"
                      f"isotonic过拟合风险（协议预注册失效区间），返回None")
        return None
    models = {}
    total_steps = 0
    for k in range(K):
        ir = IsotonicRegression(out_of_bounds='clip', y_min=0.0, y_max=1.0)
        ir.fit(val_probs[:, k], (val_labels == k).astype(float))
        models[k] = ir
        # 修复MED-1：报告实际自由度（台阶数），不是n的线性函数
        total_steps += max(len(ir.X_thresholds_) - 1, 0)
    return {'models': models, 'n_params': total_steps}


def apply_isotonic(probs: np.ndarray, params: dict) -> np.ndarray:
    """apply：逐类映射后renormalize（注意：破坏排序不变性，docstring声明）

    修复LOW-1：renormalize后行和为0时回退raw probs（防全零行静默判错类）。
    """
    if params is None:
        raise ValueError("fit_isotonic返回None（小样本），不能apply——runner应跳过")
    probs = np.asarray(probs, dtype=float)
    out = np.stack(
        [params['models'][k].predict(probs[:, k]) for k in range(probs.shape[1])],
        axis=1,
    )
    out = np.clip(out, 0.0, 1.0)
    s = out.sum(axis=1, keepdims=True)
    fallback = s[:, 0] <= 0
    out[fallback] = probs[fallback]  # 全零行回退raw
    s = out.sum(axis=1, keepdims=True)
    s[s <= 0] = 1.0
    return out / s


# =====================================================================
# 2. Vector scaling
# =====================================================================

def fit_vector_scaling(val_probs: np.ndarray, val_labels: np.ndarray) -> dict:
    """对角scale w(K) + bias b(K)：logit' = w ⊙ logit + b（2K参数）"""
    val_probs = np.asarray(val_probs, dtype=float)
    K = val_probs.shape[1]
    val_labels = np.asarray(val_labels)
    _assert_labels_valid(val_labels, K)
    labels_onehot = np.eye(K)[val_labels]
    z = _to_logits(val_probs)

    def objective(theta):
        w, b = theta[:K], theta[K:]
        if np.any(w < SCALE_MIN) or np.any(w > SCALE_MAX):
            return 1e10
        return _nll(w * z + b, labels_onehot)

    x0 = np.concatenate([np.ones(K), np.zeros(K)])
    res = minimize(objective, x0, method='L-BFGS-B',
                   bounds=[(SCALE_MIN, SCALE_MAX)] * K + [(BIAS_MIN, BIAS_MAX)] * K)
    w, b = res.x[:K], res.x[K:]
    return {'w': w, 'b': b, 'n_params': 2 * K}


def apply_vector_scaling(probs: np.ndarray, params: dict) -> np.ndarray:
    z = _to_logits(probs)
    return _to_probs(params['w'] * z + params['b'])


# =====================================================================
# 3. Matrix scaling
# =====================================================================

def fit_matrix_scaling(val_probs: np.ndarray, val_labels: np.ndarray,
                       ridge: float = 1e-6, min_cal_per_param: float = 2.0) -> Optional[dict]:
    """全矩阵M(K×K) + b：logit' = M·logit + b（K²+K参数）

    协议预期：n_cal≤100时崩溃（过参数化）。
    防护（攻击者2反例FATAL-2）：n_cal < 2×(K²+K)时返回None+warn（统计性失效预防）；
    优化失败(res.success=False)返回None+warn，禁止静默返回垃圾参数。
    """
    val_probs = np.asarray(val_probs, dtype=float)
    val_labels = np.asarray(val_labels)
    _assert_labels_valid(val_labels, val_probs.shape[1])
    K = val_probs.shape[1]
    nP = K * K + K
    n = len(val_probs)
    if n < min_cal_per_param * nP:
        warnings.warn(f"fit_matrix_scaling: n_cal={n} < 2*(K^2+K)={min_cal_per_param*nP}，"
                      f"过参数化（协议预注册失效区间），返回None")
        return None
    labels_onehot = np.eye(K)[val_labels]
    z = _to_logits(val_probs)

    def objective(theta):
        M = theta[:K * K].reshape(K, K)
        b = theta[K * K:]
        out = z @ M.T + b
        if not np.isfinite(out).all() or np.abs(out).max() > 50:
            return 1e10
        return _nll(out, labels_onehot)

    x0 = np.concatenate([np.eye(K).ravel(), np.zeros(K)])
    bounds = [(None, None)] * (K * K) + [(BIAS_MIN, BIAS_MAX)] * K
    res = minimize(objective, x0, method='L-BFGS-B',
                   bounds=bounds, options={'maxiter': 500})
    if not res.success:  # 修复FATAL-2：禁止静默失败
        warnings.warn(f"fit_matrix_scaling: 优化未收敛(status={res.status})，返回None")
        return None
    M = res.x[:K * K].reshape(K, K) + ridge * np.eye(K)
    b = res.x[K * K:]
    return {'M': M, 'b': b, 'n_params': nP, 'converged': True}


def apply_matrix_scaling(probs: np.ndarray, params: dict) -> np.ndarray:
    if params is None:
        raise ValueError("fit_matrix_scaling返回None（小样本/未收敛），不能apply——"
                         "runner应跳过该格")
    z = _to_logits(probs)
    return _to_probs(z @ params['M'].T + params['b'])


# =====================================================================
# 4. Dirichlet calibration (Kull et al. 2019)
# =====================================================================

def _assert_labels_valid(labels: np.ndarray, K: int):
    """标签合法性断言（防-label回绕等静默垃圾，攻击者2反例LOW-2）"""
    labels = np.asarray(labels)
    if labels.size and (labels.min() < 0 or labels.max() >= K):
        raise ValueError(f"标签越界: 有效范围[0,{K})，"
                         f"实际范围[{labels.min()},{labels.max()}]——"
                         f"请检查是否混入-1（无标签哨兵）")


def _dirichlet_features(probs: np.ndarray) -> np.ndarray:
    """φ(p) = [log p_1..log p_K, log p_1..log p_{K-1}]（2K-1维）

    Kull 2019 §4：Dirichlet校准 = log概率空间上的仿射映射+softmax。
    """
    lp = _to_logits(probs)  # log p
    return np.concatenate([lp, lp[:, :-1]], axis=1)


def fit_dirichlet(val_probs: np.ndarray, val_labels: np.ndarray,
                  C: float = 1e4) -> dict:
    """Dirichlet calibration：特征增强+multinomial logistic regression

    注意：sklearn LR自带L2正则（C=1e4时近似无正则MLE），非严格Kull实现——近似，
    docstring声明。n_params = K*(2K-1) + K。
    """
    val_probs = np.asarray(val_probs, dtype=float)
    val_labels = np.asarray(val_labels)
    X = _dirichlet_features(val_probs)
    lr = LogisticRegression(solver='lbfgs', C=C, max_iter=5000)
    lr.fit(X, val_labels)
    return {'lr': lr, 'n_params': lr.coef_.size + lr.intercept_.size}


def apply_dirichlet(probs: np.ndarray, params: dict) -> np.ndarray:
    """apply（修复HIGH-2空类列错位）：按lr.classes_重排进K列，缺席类置0后renormalize"""
    probs = np.asarray(probs, dtype=float)
    K = probs.shape[1]
    X = _dirichlet_features(probs)
    raw = params['lr'].predict_proba(X)          # (n, len(classes_))，可能<K
    classes = params['lr'].classes_
    out = np.zeros((probs.shape[0], K))
    for j, c in enumerate(classes):
        out[:, int(c)] = raw[:, j]
    s = out.sum(axis=1, keepdims=True)
    s[s <= 0] = 1.0
    return out / s


# =====================================================================
# 5. Saerens EM先验适配（无标签）
# =====================================================================

def fit_saerens_em(target_probs_unlabeled: np.ndarray,
                   prior_train: np.ndarray,
                   max_iter: int = 1000,
                   tol: float = 1e-8) -> np.ndarray:
    """Saerens et al. 2002 EM估计目标先验（无需目标标签）

    迭代：s_ik ∝ π_k · p_k(x_i)/π_train_k → π_k = mean_i(s_ik)
    收敛到目标域先验π_target。

    防护（攻击者2反例FATAL-3）：
    - 零区分力（预测分布行方差≈0）：EM不可辨识，返回prior_train副本并warn
      （原实现坍缩到one-hot argmin(prior_train)顶点，下游prior correction把所有样本判为一类）
    - max_iter内未收敛：warn
    """
    P = np.clip(np.asarray(target_probs_unlabeled, dtype=float), EPS, 1.0)
    pi_train = np.asarray(prior_train, dtype=float)
    pi = np.clip(pi_train, EPS, 1.0).copy()

    # 零区分力检测：预测分布的行间方差≈0 → EM不可辨识
    if P.std(axis=0).max() < 1e-9:
        warnings.warn("fit_saerens_em: 目标预测无区分力（行方差≈0），先验不可辨识，"
                      "返回prior_train副本")
        return pi_train.copy()

    converged = False
    for _ in range(max_iter):
        # E步：s_ik ∝ π_k/p_train_k * p_ik
        ratios = (pi / pi_train)[None, :] * P  # (n, K)
        s = ratios / ratios.sum(axis=1, keepdims=True)
        # M步
        pi_new = s.mean(axis=0)
        pi_new = pi_new / pi_new.sum()
        if np.abs(pi_new - pi).max() < tol:
            pi = pi_new
            converged = True
            break
        pi = pi_new

    if not converged:
        warnings.warn(f"fit_saerens_em: {max_iter}次迭代内未收敛(tol={tol})，"
                      f"返回当前估计（欠收敛）")
    return pi


def apply_prior_correction(probs: np.ndarray, pi_train: np.ndarray,
                           pi_target: np.ndarray) -> np.ndarray:
    """先验校正（BCTS式）：logit' = logit + log(π_target/π_train)"""
    z = _to_logits(probs)
    shift = np.log(np.clip(np.asarray(pi_target, dtype=float), EPS, 1.0)
                   / np.clip(np.asarray(pi_train, dtype=float), EPS, 1.0))
    return _to_probs(z + shift[None, :])


# =====================================================================
# 6. Oracle（目标域cal上拟合温度，上界）
# =====================================================================

def fit_oracle(target_cal_probs: np.ndarray, target_cal_labels: np.ndarray) -> dict:
    """Oracle上界：目标cal split上拟合全局温度（协议§6定义）"""
    K = np.asarray(target_cal_probs).shape[1]
    onehot = np.eye(K)[np.asarray(target_cal_labels)]

    def objective(theta):
        T = theta[0]
        if T < 0.01 or T > 100.0:
            return 1e10
        return _nll(_to_logits(target_cal_probs) / T, onehot)

    res = minimize(objective, np.array([1.0]), method='L-BFGS-B',
                   bounds=[(0.01, 100.0)])
    return {'T': float(res.x[0]), 'n_params': 1}


def apply_oracle(probs: np.ndarray, params: dict) -> np.ndarray:
    return _to_probs(_to_logits(probs) / params['T'])


# =====================================================================
# 7. none / ts / platt + 注册表
# =====================================================================

def apply_none(probs: np.ndarray, params: dict = None) -> np.ndarray:
    return np.asarray(probs, dtype=float).copy()


def fit_temperature_multiclass(val_probs: np.ndarray,
                               val_labels: np.ndarray) -> dict:
    """标准多分类温度缩放（Guo et al. 2017）"""
    K = np.asarray(val_probs).shape[1]
    onehot = np.eye(K)[np.asarray(val_labels)]

    def objective(theta):
        T = theta[0]
        if T < 0.01 or T > 100.0:
            return 1e10
        return _nll(_to_logits(val_probs) / T, onehot)

    res = minimize(objective, np.array([1.0]), method='L-BFGS-B',
                   bounds=[(0.01, 100.0)])
    return {'T': float(res.x[0]), 'n_params': 1}


def apply_temperature_multiclass(probs: np.ndarray, params: dict) -> np.ndarray:
    return _to_probs(_to_logits(probs) / params['T'])


def fit_platt_multiclass(val_probs: np.ndarray, val_labels: np.ndarray) -> dict:
    """per-class Platt（OvR，每类(s,b)，logit空间：sigmoid(s·logit(p)+b)）"""
    from scipy.special import expit
    val_probs = np.asarray(val_probs, dtype=float)
    val_labels = np.asarray(val_labels)
    K = val_probs.shape[1]
    _assert_labels_valid(val_labels, K)
    params = {}
    for k in range(K):
        y = (val_labels == k).astype(float)
        p = np.clip(val_probs[:, k], EPS, 1 - EPS)
        z = np.log(p / (1 - p))  # logit

        def objective(ab):
            s, b = ab
            if s < SCALE_MIN or s > SCALE_MAX:
                return 1e10
            pred = expit(s * z + b)  # 与apply完全同构（logit空间）
            pred = np.clip(pred, 1e-12, 1 - 1e-12)
            return float(-(y * np.log(pred) + (1 - y) * np.log(1 - pred)).mean())

        res = minimize(objective, np.array([1.0, 0.0]), method='L-BFGS-B',
                       bounds=[(SCALE_MIN, SCALE_MAX), (BIAS_MIN, BIAS_MAX)])
        params[k] = (float(res.x[0]), float(res.x[1]))
    return {'models': params, 'n_params': 2 * K}


def apply_platt_multiclass(probs: np.ndarray, params: dict) -> np.ndarray:
    """apply与fit同构：sigmoid(s·logit(p)+b)，逐类后renormalize"""
    from scipy.special import expit
    probs = np.asarray(probs, dtype=float)
    p = np.clip(probs, EPS, 1 - EPS)
    z = np.log(p / (1 - p))  # logit（修复FATAL-1：原实现误用odds）
    out = np.stack([
        expit(params['models'][k][0] * z[:, k] + params['models'][k][1])
        for k in range(probs.shape[1])
    ], axis=1)
    out = out / out.sum(axis=1, keepdims=True)
    return out


# 方法注册表：(fit_fn, apply_fn, needs_labels)
# 修复HIGH-1：saerens纳入注册表（needs_labels=False，fit签名特殊：
#   fit_saerens_entry(target_probs_unlabeled, val_labels) → prior_train=val_labels用作train先验，
#   runner按needs_labels分流：False时fit的第二个参数传"train先验"而非标签）
def _fit_saerens_entry(target_probs_unlabeled, prior_train, **kw):
    return {'pi_target': fit_saerens_em(target_probs_unlabeled, prior_train, **kw),
            'pi_train': np.asarray(prior_train, dtype=float), 'n_params': 0}

def _apply_saerens_entry(probs, params):
    return apply_prior_correction(probs, params['pi_train'], params['pi_target'])

CALIBRATION_METHODS: Dict[str, Tuple[Callable, Callable, bool]] = {
    'none': (lambda p, y=None: {'n_params': 0}, apply_none, False),
    'ts': (fit_temperature_multiclass, apply_temperature_multiclass, True),
    'platt': (fit_platt_multiclass, apply_platt_multiclass, True),
    'isotonic': (fit_isotonic, apply_isotonic, True),
    'vector': (fit_vector_scaling, apply_vector_scaling, True),
    'matrix': (fit_matrix_scaling, apply_matrix_scaling, True),
    'dirichlet': (fit_dirichlet, apply_dirichlet, True),
    'saerens': (_fit_saerens_entry, _apply_saerens_entry, False),  # 修复HIGH-1
    'oracle': (fit_oracle, apply_oracle, True),
}
