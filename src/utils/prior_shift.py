"""P-independent 目标先验恢复估计器：BBSE + EM（协议§13 item 7 升级）

背景：decompose_benefit 的 prev_hat 目前是**设计常量回读**（重采样精确控制
正类数 → MAPE_π 仅是 design check，非估计量能力检验）。本节把 MAPE_π 升级为
**真实无标签估计量**检验：在目标域**不提供标签**的前提下，仅凭源域（有标签）
+ 目标域（仅模型 soft-probabilities）恢复目标类先验 π_target。

方法池（K类，K≥2）：
1. **BBSE**（Lipton, Wang & Smola, ICML 2018 "Detecting and Correcting for
   Label Shift with Black Box Predictors"）：
   - 源域 soft-confusion：C[j,k] = E_src[ P_pred_j(x) | y=k ]（K×K）
   - 目标平均预测：μ_target[j] = E_target[ P_pred_j(x) ]（仅需目标概率，无标签）
    - 关键恒等式（label shift 下）：
          μ_target = C · π_target          （π_target=目标类先验）
   - 解线性系统 + 投影到概率单纯形。C 满秩时目标先验可辨识。
   - 秩/条件数守卫：C 近奇异（cond>阈值 或 rank<K）→ 返回 None+warn（不可辨识）。
2. **EM**（Saerens, Latinne & Decaestecker 2002 "Adjusting the Outputs of a
   Classifier to New a Priori Probabilities"；即 fit_saerens_em 的干净接口）：
   迭代重估 π_k，收敛到目标先验。零区分力（目标概率行方差≈0）→ 不可辨识，
   返回源先验副本+warn。

统一接口（对齐 calibration_methods 约定）：
    fit_bbse(src_probs, src_labels, target_probs) -> dict | None
    fit_em(   src_probs, src_labels, target_probs) -> dict | None
返回 {'pi_hat': (K,) 目标先验估计, 'pi_train': (K,) 源先验, ...}
None = 不可辨识/数值失效（协议：失效区间如实报告，禁止静默垃圾）。

计量与边界守卫（对抗审查纪律）：
- src_probs/src_labels 必须等长；target_probs 类数=src_probs 类数。
- 每类至少 min_samples 源样本（默认 10），否则该类的 confusion 列不可靠→None。
- BBSE 解经 非负最小二乘 + 单纯形投影，投影后归一化。
- 报告 identifiability 诊断：confusion 条件数、秩、BBSE 与 EM 的 π̂ 距离。
- 不修改任何现有训练/推断路径——纯增量模块，供 decompose 的 MAPE_π 升级调用。
"""

from __future__ import annotations

import warnings
from typing import Optional

import numpy as np

EPS = 1e-12


def _validate(src_probs, src_labels, target_probs):
    src_probs = np.asarray(src_probs, dtype=float)
    src_labels = np.asarray(src_labels)
    target_probs = np.asarray(target_probs, dtype=float)
    if src_probs.ndim != 2 or target_probs.ndim != 2:
        raise ValueError(f"probs须2D (n,K)，得到 {src_probs.shape}/{target_probs.shape}")
    K = src_probs.shape[1]
    if target_probs.shape[1] != K:
        raise ValueError(f"源/目标类数不一致: {K} vs {target_probs.shape[1]}")
    if src_probs.shape[0] != src_labels.shape[0]:
        raise ValueError("src_probs 与 src_labels 行数不一致")
    if K < 2:
        raise ValueError("K≥2（多分类）")
    # 源先验（训练/参考域）
    pi_train = np.bincount(src_labels.astype(int), minlength=K).astype(float)
    if pi_train.sum() == 0:
        raise ValueError("源域空/无有效标签")
    pi_train = pi_train / pi_train.sum()
    return src_probs, src_labels.astype(int), target_probs, pi_train


def _simplex_project(x: np.ndarray) -> np.ndarray:
    """投影到概率单纯形（Duchi 2008 欧几里得投影精确算法）。
    返回概率向量（和=1，元素>=0）。全零/全负输入返回 NaN（失效信号）。"""
    v = np.asarray(x, dtype=float).copy()
    n = len(v)
    if n == 1:
        return np.array([1.0])
    if np.max(v) <= 0:
        return np.full(n, np.nan)
    u = np.sort(v)[::-1]  # 降序
    cssv = np.cumsum(u) - 1.0
    rho = np.nonzero(u - cssv / np.arange(1, n + 1) > 0)[0]
    if len(rho) == 0:
        return np.full(n, 1.0 / n)
    rho = rho[-1] + 1  # 最大满足条件的 j（1-indexed）
    tau = cssv[rho - 1] / rho
    w = np.maximum(v - tau, 0.0)
    s = w.sum()
    if s <= 0 or not np.isfinite(w).all():
        return np.full(n, np.nan)
    return w / s


def _cond_rank(C: np.ndarray):
    return float(np.linalg.cond(C)), int(np.linalg.matrix_rank(C, tol=1e-9))


def fit_bbse(src_probs, src_labels, target_probs,
             min_samples: int = 10,
             cond_max: float = 1e8,
             solver: str = "nnls") -> Optional[dict]:
    """BBSE：μ_target = C^T π_target，解 π_target 并投影。

    C[j,k] = 源域上 类k样本 的平均预测概率_j（soft-confusion）。
    """
    src_probs, src_labels, target_probs, pi_train = _validate(
        src_probs, src_labels, target_probs)
    K = src_probs.shape[1]

    # 每类源样本数守卫（confusion 列估计的可靠性）
    per_class = np.bincount(src_labels, minlength=K)
    if per_class.min() < min_samples:
        warnings.warn(
            f"fit_bbse: 最少类源样本 {per_class.min()} < min_samples={min_samples}，"
            "confusion列不可靠 → 返回None")
        return None

    # soft-confusion C[j,k] = mean_src[ P_j | y=k ]
    C = np.zeros((K, K))
    for k in range(K):
        m = src_labels == k
        C[:, k] = src_probs[m].mean(axis=0)
    C = np.maximum(C, EPS)  # 防零列

    # 目标平均预测
    mu = target_probs.mean(axis=0)  # (K,)

    cond, rank = _cond_rank(C)
    if rank < K or cond > cond_max:
        warnings.warn(
            f"fit_bbse: confusion 条件数={cond:.3g} 秩={rank}/{K}，"
            "目标先验不可辨识（C近奇异）→ 返回None")
        return None

    # 解 C π = mu（C[j,k]=E[P(ŷ=j)|y=k], μ[j]=Σ_k π_k·C[j,k]）
    if solver == "nnls":
        from scipy.optimize import nnls
        pi_hat, _ = nnls(C, mu)
    else:  # lstsq
        pi_hat, *_ = np.linalg.lstsq(C, mu, rcond=None)
    pi_hat = np.maximum(pi_hat, 0.0)
    s = pi_hat.sum()
    if s <= 0 or not np.isfinite(pi_hat).all():
        warnings.warn("fit_bbse: 解非正/非有限 → 返回None")
        return None
    pi_hat = _simplex_project(pi_hat)
    if not np.isfinite(pi_hat).all():
        warnings.warn("fit_bbse: 单纯形投影失效 → 返回None")
        return None

    return {"pi_hat": pi_hat, "pi_train": pi_train, "method": "bbse",
            "confusion_cond": cond, "rank": rank, "n_src": int(len(src_labels)),
            "n_target": int(len(target_probs))}


def fit_em(src_probs, src_labels, target_probs,
           max_iter: int = 1000, tol: float = 1e-8) -> Optional[dict]:
    """EM 目标先验估计（Saerens 2002 标准算法，接口与BBSE对齐）。

    用源先验 π_train 初始化；迭代：
        E:  s_ik ∝ π_k/π_train_k · P_k(x_i)   （x_i∈目标，无标签）
        M:  π_k ← mean_i(s_ik)
    零区分力（目标预测分布行方差≈0）→ 不可辨识，返回None+warn。
    """
    src_probs, src_labels, target_probs, pi_train = _validate(
        src_probs, src_labels, target_probs)
    K = src_probs.shape[1]

    # 零区分力守卫（对齐 fit_saerens_em）
    P = np.clip(target_probs, EPS, 1.0)
    if P.std(axis=0).max() < 1e-9:
        warnings.warn("fit_em: 目标预测无区分力（行方差≈0），先验不可辨识 → 返回None")
        return None

    pi = np.clip(pi_train, EPS, 1.0).copy()
    converged = False
    for _ in range(max_iter):
        ratios = (pi / pi_train)[None, :] * P      # (n,K)
        s = ratios / ratios.sum(axis=1, keepdims=True)
        pi_new = s.mean(axis=0)
        pi_new = pi_new / pi_new.sum()
        if np.abs(pi_new - pi).max() < tol:
            pi = pi_new
            converged = True
            break
        pi = pi_new
    if not converged:
        warnings.warn(f"fit_em: {max_iter}次迭代未收敛(tol={tol})")

    pi_hat = _simplex_project(pi)
    if not np.isfinite(pi_hat).all():
        warnings.warn("fit_em: 投影失效 → 返回None")
        return None
    return {"pi_hat": pi_hat, "pi_train": pi_train, "method": "em",
            "converged": converged, "n_src": int(len(src_labels)),
            "n_target": int(len(target_probs))}


# 注册表：方法与是否需源标签（BBSE/EM 都只需源标签拟合混淆/先验，目标域无标签）
P_INDEPENDENT_METHODS = {
    "bbse": fit_bbse,
    "em": fit_em,
}


if __name__ == "__main__":
    # 自检：label shift 下 BBSE/EM 应恢复真实目标先验（无需目标标签）
    rng = np.random.default_rng(0)
    K = 5
    n_src = 8000
    # 源：近似可分的分类器 soft-probs（类k的样本预测集中该类）
    src_labels = rng.integers(0, K, n_src)
    conf = 0.7 * np.eye(K) + 0.3 * np.full((K, K), 1.0 / K)  # 行随机? 构造 soft-rows
    src_probs = rng.dirichlet(np.full(K, 1.0), n_src) * 0.3
    src_probs[np.arange(n_src), src_labels] += 0.7  # 让类内概率集中
    src_probs = src_probs / src_probs.sum(axis=1, keepdims=True)

    # 目标：真实先验偏离源先验（label shift）
    pi_true = np.array([0.5, 0.1, 0.1, 0.15, 0.15])
    n_tgt = 20000
    tgt_labels = rng.choice(K, n_tgt, p=pi_true)
    tgt_probs = rng.dirichlet(np.full(K, 1.0), n_tgt) * 0.3
    tgt_probs[np.arange(n_tgt), tgt_labels] += 0.7
    tgt_probs = tgt_probs / tgt_probs.sum(axis=1, keepdims=True)

    pi_train = np.bincount(src_labels, minlength=K) / n_src
    print(f"源先验(train): {np.round(pi_train,3)}")
    print(f"真实目标先验: {pi_true}")
    for name, fn in P_INDEPENDENT_METHODS.items():
        res = fn(src_probs, src_labels, tgt_probs)
        if res is None:
            print(f"{name}: FAILED(不可辨识)")
        else:
            err = np.abs(res['pi_hat'] - pi_true).mean()
            print(f"{name}: π̂={np.round(res['pi_hat'],3)} mean_abs_err={err:.4f}")
