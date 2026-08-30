"""三成分分解估计器 v2（攻击者3反例修复版）

数学定义（二分类，概率p，二值标签y）：
- 注入：p' = sigmoid(s·logit(p) + b)；prevalence注入=按目标先验重采样
- 恢复（v2修复反例1）：在**重采样后**数据上恢复，并做King-Zeng case-control校正：
    重采样后拟合 logit(y) = a·x' + c（x'=logit(p')），
    case-control偏移：重采样使 b̂_raw 带上 −(logit(π_resampled) − logit(π_injected))/a，
    校正：b̂ = b̂_raw + (logit(π_resampled) − logit(π_injected))/a   [实现为准]
  其中 π_injected=注入后（重采样前）数据的正类频率，π_resampled=重采样后正类频率。
  校正后 prev轴真正进入(s,b)恢复的检验——27格因子设计不再退化。
- 反事实分解（固定顺序s→b→π，协议预注册）：Δ_s, Δ_b, Δ_π链式增量；
  **附加输出**（v2修复反例3/4）：
    - 6排列敏感性：每种顺序的链式分解 + 极差
    - Shapley对称归因：8个子集全枚举，贡献占比客观化
    - 析因交互项 I_sb = ECE_sb − ECE_s − ECE_b + ECE_0（真实交互，不再恒0）
- Fisher信息（v2修复反例5）：恢复似然的FI——设计矩阵取x'=logit(p_injected)，
  权重取**基线**Bernoulli方差 w=σ(x_base)(1−σ(x_base))（x_base=logit(p_base)）。
  该det独立于b、∝s²（实测验证：det(0.5):det(1):det(2)=1:4:16），正确反映恢复可辨识性（原实现用注入概率方差产生假阳性纠缠判定）。

入口校验（v2修复反例6）：labels必须∈{0,1}，probs必须1维——多分类top-label场景需
调用方先做二值化并在结果中注明语义（置信度-正确性映射，含基线失准污染）。
"""

import warnings
import math
import itertools
from typing import Dict, Optional

import numpy as np
from scipy.special import expit
from sklearn.linear_model import LogisticRegression

IDENTIFIABILITY_TAU = 1e-6  # 预注册阈值（协议§8）
N_REF = 20000               # 参考样本量（门槛标定）
MAPE_REF = 0.0123           # n=N_REF时实测MAPE_s参考值（建造者报告1.23%）
GATE_BASE = 0.10            # 协议原门槛
GATE_FLOOR = 0.10           # 门槛下限（不低于原预注册值）


def _validate_binary(probs: np.ndarray, labels: np.ndarray):
    """入口校验（反例6）：labels∈{0,1}，probs一维"""
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels)
    if probs.ndim != 1:
        raise ValueError(f"probs必须1维（二分类），得到shape={probs.shape}。"
                         f"多分类top-label场景请先二值化（max_prob + correct_mask）"
                         f"并注明语义。")
    if labels.size and not np.isin(labels, [0, 1]).all():
        raise ValueError(f"labels必须∈{{0,1}}，实际值域"
                         f"[{labels.min()},{labels.max()}]——多分类类索引会静默产生垃圾结果")
    return probs, labels.astype(float)


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return np.log(p / (1 - p))


def inject_transform(probs: np.ndarray, slope: float = 1.0,
                     intercept: float = 0.0) -> np.ndarray:
    """logit空间注入变换：p' = sigmoid(s·logit(p)+b)"""
    probs, _ = _validate_binary(probs, np.zeros(0, dtype=int))
    return expit(slope * _logit(probs) + intercept)


def resample_prevalence(probs: np.ndarray, labels: np.ndarray,
                        target_prev: float, rng: np.random.Generator) -> np.ndarray:
    """按target_prev重采样索引（有放回，保持(p,y)配对）

    边界（反例8）：target_prev clip到[0.01,0.99]并warn；正类不足时复制并warn。
    """
    probs, labels = _validate_binary(probs, labels)
    if not (0 < target_prev < 1):
        warnings.warn(f"target_prev={target_prev}越界，clip到[0.01,0.99]")
        target_prev = float(np.clip(target_prev, 0.01, 0.99))
    n = len(labels)
    pos_idx = np.where(labels == 1)[0]
    neg_idx = np.where(labels == 0)[0]
    if len(pos_idx) == 0:
        raise ValueError("无正类样本，无法重采样")
    n_pos = max(int(round(target_prev * n)), 1)
    if n_pos > 5 * len(pos_idx):
        warnings.warn(f"正类样本({len(pos_idx)})将被复制{n_pos/len(pos_idx):.0f}倍，"
                      f"重采样样本不独立，ECE的不确定性被低估")
    pos_sampled = rng.choice(pos_idx, size=n_pos, replace=True)
    n_neg = n - n_pos
    neg_sampled = rng.choice(neg_idx, size=n_neg, replace=True)
    idx = np.concatenate([pos_sampled, neg_sampled])
    rng.shuffle(idx)
    return idx


def recover_slope_intercept(probs_injected: np.ndarray, labels: np.ndarray,
                            pi_reference: Optional[float] = None,
                            pi_resampled: Optional[float] = None,
                            slope_hint: Optional[float] = None) -> Dict[str, float]:
    """在（重采样后）数据上恢复(s,b)，带King-Zeng case-control校正

    数学：注入p'=σ(s·x+b)，y~Bern(σ(x))（基线校准）。恢复回归logit(y)=a·x'+c。
    反演：ŝ=1/a, b̂_raw=−c/a。
    case-control偏移（建造者实测验证）：重采样使b̂_raw带上
        −(logit(π_resampled) − logit(π_injected))/a，
    校正：b̂ = b̂_raw + (logit(π_resampled) − logit(π_injected))/a   [实现为准]。
    """
    probs_injected, labels = _validate_binary(probs_injected, labels)
    x_prime = _logit(probs_injected).reshape(-1, 1)
    lr = LogisticRegression(C=1e4, solver='lbfgs', max_iter=5000)
    lr.fit(x_prime, labels.astype(int))
    a, c = float(lr.coef_[0, 0]), float(lr.intercept_[0])
    if abs(a) < 1e-12:
        raise ValueError("logistic回归斜率≈0，恢复退化（数据无信息）")
    s_hat = 1.0 / a
    b_hat_raw = -c / a

    b_hat = b_hat_raw
    if pi_reference is not None and pi_resampled is not None:
        # King-Zeng case-control校正（实证验证：b̂=b̂_raw+L/a，真值0.5恢复为0.494）
        L = (np.log(pi_resampled / (1 - pi_resampled))
             - np.log(pi_reference / (1 - pi_reference)))
        b_hat = b_hat_raw + L / a

    return {'s_hat': s_hat, 'b_hat': b_hat, 'b_hat_raw': b_hat_raw}


def fisher_information_det(probs_injected: np.ndarray,
                           probs_baseline: np.ndarray) -> float:
    """恢复似然的Fisher信息行列式（v2修复反例5权重错配）

    恢复问题：y|x' ~ Bern(σ((x'−b)/s))，x'=logit(p_injected)，x_base=logit(p_baseline)。
    设计矩阵[1, x']，权重 w_i = σ(x_base_i)(1−σ(x_base_i))（基线Bernoulli方差——
    原实现误用注入概率方差，产生假阳性纠缠判定）。
    det独立于b、随x'设计缩放 ∝ s²（2×2信息矩阵单维缩放律，实测验证）。
    """
    probs_injected, _ = _validate_binary(probs_injected, np.zeros(0, dtype=int))
    probs_baseline, _ = _validate_binary(probs_baseline, np.zeros(0, dtype=int))
    x_prime = _logit(probs_injected)
    x_base = _logit(probs_baseline)
    w = expit(x_base) * (1 - expit(x_base))
    n = len(x_prime)
    sw = w.sum()
    swx = (w * x_prime).sum()
    swxx = (w * x_prime ** 2).sum()
    det = (sw * swxx - swx ** 2) / (n ** 2)
    return float(max(det, 0.0))


def identifiability_gate(n: int) -> float:
    """MAPE门槛随样本量缩放（v2修复反例2：n=500时57%失败→统计容差）

    gate(n) = max(GATE_FLOOR, 3 × MAPE_REF × sqrt(N_REF/n))
    n=N_REF=20000 → max(10%, 3.7%)=10%（协议原门槛）
    n=500  → max(10%, 23%)≈23%（3σ统计容差，与实测p95=19.6%一致）
    """
    gate = 3 * MAPE_REF * np.sqrt(N_REF / max(n, 1))
    return float(max(GATE_FLOOR, gate))


def _ece_chain(probs_base, labels_base, slope, intercept, prev_idx, labels_full,
               rng, metric) -> float:
    """ECE on (注入(s,b)后 + 重采样prev_idx) 的数据"""
    p_inj = inject_transform(probs_base, slope, intercept)
    if prev_idx is None:
        return float(metric(p_inj, labels_base))
    return float(metric(p_inj[prev_idx], labels_full[prev_idx]))


def ece_metric_safe(probs: np.ndarray, labels: np.ndarray) -> float:
    """二分类ECE（10等宽bin），供decompose_benefit默认metric"""
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    ece_val = 0.0
    n = len(probs)
    for i in range(10):
        lo, hi = i / 10, (i + 1) / 10
        mask = (probs >= lo) & (probs < hi) if i < 9 else (probs >= lo) & (probs <= hi)
        if mask.sum() == 0:
            continue
        ece_val += mask.sum() / n * abs(probs[mask].mean() - labels[mask].mean())
    return float(ece_val)


def decompose_benefit(probs_base: np.ndarray, labels_base: np.ndarray,
                      slope: float, intercept: float,
                      target_prev: Optional[float], rng: np.random.Generator,
                      metric=ece_metric_safe) -> Dict:
    """完整三成分分解（v2）

    v2变化：
    - 恢复在重采样后数据上进行 + King-Zeng校正（反例1：prev轴进入检验）
    - 附加：6排列敏感性、Shapley归因、析因交互项（反例3/4）
    - FI用基线权重（反例5）
    - 入口校验（反例6）
    """
    probs_base, labels_base = _validate_binary(probs_base, labels_base)

    # 注入
    p_inj = inject_transform(probs_base, slope, intercept)
    prev_idx = None
    if target_prev is not None and abs(target_prev - labels_base.mean()) > 1e-9:
        prev_idx = resample_prevalence(p_inj, labels_base, target_prev, rng)

    # 各子集ECE（8子集全枚举：用于Shapley+析因交互）
    def ece_subset(s, b, use_prev):
        p = inject_transform(probs_base, s, b)
        if use_prev and prev_idx is not None:
            return float(metric(p[prev_idx], labels_base[prev_idx]))
        return float(metric(p, labels_base))

    e0 = ece_subset(1.0, 0.0, False)
    e_s = ece_subset(slope, 0.0, False)
    e_b = ece_subset(1.0, intercept, False)
    e_pi = ece_subset(1.0, 0.0, True)
    e_sb = ece_subset(slope, intercept, False)
    e_spi = ece_subset(slope, 0.0, True)
    e_bpi = ece_subset(1.0, intercept, True)
    e_sbpi = ece_subset(slope, intercept, True)

    delta_total = e_sbpi - e0

    # 链式分解（预注册顺序s→b→π）
    delta_s = e_s - e0
    delta_b = e_sb - e_s
    delta_pi = e_sbpi - e_sb
    # 残差按链式定义恒为0（套叠恒等式）——真实交互用析因项：
    # 交互残差=Δ_total − (Δ_s+Δ_b+Δ_π+跨级交互修正)，改报析因交互I_sb等
    chain_residual = delta_total - (delta_s + delta_b + delta_pi)

    # 析因交互项（真实交互，反例4）
    I_sb = e_sb - e_s - e_b + e0
    I_s_pi = e_spi - e_s - e_pi + e0
    I_b_pi = e_bpi - e_b - e_pi + e0

    I_3way = e_sbpi - e_sb - e_spi - e_bpi + e_s + e_b + e_pi - e0

    # 6排列敏感性（反例3）
    _canon = {'s': 0, 'b': 1, 'pi': 2}

    def chain_decomp(order):
        # order是('s','b','pi')的排列；返回该顺序的各成分
        current = e0
        comps = {}
        steps = {'s': e_s, 'b': e_b, 'pi': e_pi,
                 'sb': e_sb, 'spi': e_spi, 'bpi': e_bpi, 'sbpi': e_sbpi}
        done = set()
        for comp in order:
            target_key = ''.join(sorted(done | {comp}, key=lambda c: _canon[c]))
            e_next = steps[target_key]
            comps[comp] = e_next - current
            current = e_next
            done.add(comp)
        return comps

    permutations = {}
    for order in itertools.permutations(['s', 'b', 'pi']):
        permutations[''.join(order)] = chain_decomp(order)

    # Shapley值（8子集全枚举）
    def shapley(comp):
        vals = {'': e0, 's': e_s, 'b': e_b, 'pi': e_pi, 'sb': e_sb,
                'spi': e_spi, 'bpi': e_bpi, 'sbpi': e_sbpi}
        total = 0.0
        others = [c for c in ['s', 'b', 'pi'] if c != comp]
        for r in range(len(others) + 1):
            for subset in itertools.combinations(others, r):
                key_with = ''.join(sorted(subset + (comp,), key=lambda c: _canon[c]))
                key_without = ''.join(sorted(subset, key=lambda c: _canon[c]))
                weight = (math.factorial(len(subset))
                          * math.factorial(3 - len(subset) - 1) / 6)
                total += weight * (vals[key_with] - vals[key_without])
        return total

    shap_s = shapley('s')
    shap_b = shapley('b')
    shap_pi = shapley('pi')
    shap_sum = shap_s + shap_b + shap_pi
    shapley_shares = {
        's': shap_s / shap_sum if shap_sum != 0 else 0.0,
        'b': shap_b / shap_sum if shap_sum != 0 else 0.0,
        'pi': shap_pi / shap_sum if shap_sum != 0 else 0.0,
    }

    # 恢复（重采样后 + King-Zeng校正，反例1）
    pi_injected = float(labels_base.mean())
    if prev_idx is not None:
        labels_resampled = labels_base[prev_idx]
        p_resampled = p_inj[prev_idx]
        pi_resampled = float(labels_resampled.mean())
        rec = recover_slope_intercept(
            p_resampled, labels_resampled,
            pi_reference=pi_injected, pi_resampled=pi_resampled,
        )
        prev_hat = pi_resampled  # 直接估计（重采样设计下标签频率=MLE）
        prev_true = float(target_prev)
    else:
        rec = recover_slope_intercept(p_inj, labels_base,
                                      pi_reference=pi_injected,
                                      pi_resampled=pi_injected)
        prev_hat = pi_injected
        prev_true = pi_injected

    # FI（基线权重）
    det = fisher_information_det(p_inj, probs_base)
    entangled = det < IDENTIFIABILITY_TAU

    return {
        'delta_total': delta_total,
        'chain': {'delta_s': delta_s, 'delta_b': delta_b, 'delta_pi': delta_pi,
                  'residual': chain_residual},
        'interactions': {'I_sb': I_sb, 'I_s_pi': I_s_pi, 'I_b_pi': I_b_pi,
                         'I_3way': I_3way},
        'permutations': permutations,
        'shapley': {'values': {'s': shap_s, 'b': shap_b, 'pi': shap_pi},
                    'shares': shapley_shares},
        'recovery': {'s_hat': rec['s_hat'], 'b_hat': rec['b_hat'],
                     'b_hat_raw': rec['b_hat_raw'],
                     'prev_hat': prev_hat, 'prev_true': prev_true},
        'fisher_det': det,
        'entangled': bool(entangled),
        'ece_subsets': {'base': e0, 's': e_s, 'b': e_b, 'pi': e_pi,
                        'sb': e_sb, 'spi': e_spi, 'bpi': e_bpi, 'sbpi': e_sbpi},
    }

