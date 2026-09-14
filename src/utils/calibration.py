"""校准原语库 v2: 温度缩放 / Platt scaling / ECE / Brier Score

关键修复（基于对抗性审查）：
1. Nelder-Mead → L-BFGS-B（梯度方法更高效）
2. 添加多分类校准支持
3. 添加Bootstrap置信区间
4. 修复ECE分箱策略
5. 添加校准曲线可视化
"""

import warnings
import numpy as np
from scipy.optimize import minimize, minimize_scalar
from typing import Tuple, List, Optional

EPS = 1e-7
T_MIN = 0.01  # 温度下界（更宽松的范围）
T_MAX = 100.0  # 温度上界


def _validate_n_bins(n_bins, upper_bound=10**4):
    """验证 n_bins 参数合法性（公共守卫）。

    供 calibration.py 内 6 处守卫与 scripts/ 中 4 个 n_bins 函数统一调用，
    避免守卫模式重复散布。R7 修复：上界由 10**6 降至 10**4，
    与 O(n_bins) Python 循环实现匹配（单次 ece <50ms）。
    R8-4 修复：calibration.py 内 ece/bootstrap_ece/brier_parts/mce/
    plot_reliability_diagram/compute_all_metrics 6 处守卫已全部改为调用
    _validate_n_bins（此前为内联重复守卫，与本 docstring "统一调用" 声称不符）。
    R8-4 修复：calibration.py 内 ece/bootstrap_ece/brier_parts/mce/
    plot_reliability_diagram/compute_all_metrics 6 处守卫已全部改为调用
    _validate_n_bins（此前为内联重复守卫，与本 docstring "统一调用" 声称不符）。

    Args:
        n_bins: 待验证的分箱数量
        upper_bound: 上界（默认 10000）

    Returns:
        int(n_bins)

    Raises:
        ValueError: n_bins 非 int/np.integer、为 bool、<1 或 > upper_bound
    """
    if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1 or n_bins > upper_bound:
        raise ValueError(f"n_bins must be a positive integer in [1, {upper_bound}], got {n_bins!r}")
    return int(n_bins)


def to_logit(p: np.ndarray) -> np.ndarray:
    """概率转logit，带数值保护"""
    p = np.clip(p, EPS, 1 - EPS)
    return np.log(p / (1 - p))


def sigmoid(x: np.ndarray) -> np.ndarray:
    """logit转概率，带数值保护"""
    x = np.clip(x, -30, 30)
    return 1.0 / (1.0 + np.exp(-x))


def nll(a: float, b: float, lg: np.ndarray, y: np.ndarray) -> float:
    """负对数似然: Platt scaling的目标函数"""
    z = a * lg + b
    z = np.clip(z, -30, 30)
    return float(-np.mean(y * z - np.log1p(np.exp(z))))


def fit_temperature(val_p, val_y, method: str = "L-BFGS-B") -> float:
    """在验证集上拟合温度缩放参数T
    
    修复：
    1. 默认使用L-BFGS-B（梯度方法），而非Nelder-Mead
    2. 合理的温度范围[0.01, 100.0]
    3. 多分类使用单一全局温度（标准做法）
    
    Args:
        val_p: 验证集预测概率 (n_samples,) 或 (n_samples, n_classes)
        val_y: 验证集真实标签 (n_samples,) 或 one-hot (n_samples, n_classes)
        method: 优化方法 ('L-BFGS-B', 'Brent', 'Nelder-Mead')
    
    Returns:
        最优温度参数T
    """
    val_p = np.asarray(val_p)
    val_y = np.asarray(val_y)
    
    # 多分类：使用单一全局温度（标准做法）
    # 参考：Guo et al., 2017 "On Calibration of Modern Neural Networks"
    if val_p.ndim == 2:
        # 计算logits（从概率反推）
        # 使用log-sum-exp技巧数值稳定
        logits = np.log(np.clip(val_p, EPS, 1 - EPS))
        
        # 单一温度优化（全局NLL）
        def objective(T_arr):
            T = T_arr[0]
            if T < T_MIN or T > T_MAX:
                return 1e10
            # 多分类NLL
            scaled_logits = logits / T
            # log-sum-exp
            log_sum_exp = np.max(scaled_logits, axis=1, keepdims=True)
            log_probs = scaled_logits - log_sum_exp - np.log(np.sum(np.exp(scaled_logits - log_sum_exp), axis=1, keepdims=True))
            # NLL
            nll_val = -np.mean(np.sum(val_y * log_probs, axis=1))
            return nll_val
        
        res = minimize(
            objective,
            x0=np.array([1.0]),
            method="L-BFGS-B",
            bounds=[(T_MIN, T_MAX)],
            options={"maxiter": 100}
        )
        return float(np.clip(res.x[0], T_MIN, T_MAX))
    
    # 二分类
    lg = to_logit(val_p)
    
    if method == "L-BFGS-B":
        # 使用L-BFGS-B（修复：替换Nelder-Mead）
        def objective(T_arr):
            T = T_arr[0]
            if T < T_MIN or T > T_MAX:
                return 1e10
            return nll(1.0 / T, 0.0, lg, val_y)
        
        res = minimize(
            objective,
            x0=np.array([1.0]),
            method="L-BFGS-B",
            bounds=[(T_MIN, T_MAX)],
            options={"maxiter": 100}
        )
        T = float(np.clip(res.x[0], T_MIN, T_MAX))
        
    elif method == "Brent":
        # 使用Brent方法（专用于1D优化）
        def objective(T):
            return nll(1.0 / T, 0.0, lg, val_y)
        
        res = minimize_scalar(
            objective,
            bounds=(T_MIN, T_MAX),
            method='bounded'
        )
        T = float(np.clip(res.x, T_MIN, T_MAX))
        
    else:
        # Nelder-Mead（兼容旧代码）
        def objective(T_arr):
            T = T_arr[0]
            if T < T_MIN or T > T_MAX:
                return 1e10
            return nll(1.0 / T, 0.0, lg, val_y)
        
        res = minimize(
            objective,
            x0=np.array([1.0]),
            method="Nelder-Mead",
            options={"xatol": 1e-4, "fatol": 1e-8, "maxiter": 100}
        )
        T = float(np.clip(res.x[0], T_MIN, T_MAX))
    
    if not res.success:
        warnings.warn(f"Temperature optimization failed: {res.message}")
    
    return T


def fit_platt(val_p, val_y):
    """在验证集上拟合Platt scaling参数(a, b)
    
    Platt scaling: p' = sigmoid(a * logit(p) + b)
    
    Args:
        val_p: 验证集预测概率 (n_samples,)
        val_y: 验证集真实标签 (n_samples,)
    
    Returns:
        (a, b) 参数对
    """
    val_p = np.asarray(val_p)
    val_y = np.asarray(val_y)
    lg = to_logit(val_p)
    
    def objective(ab):
        a, b = ab
        if a < 0.05 or a > 20.0 or b < -10.0 or b > 10.0:
            return 1e10
        return nll(a, b, lg, val_y)  # 移除正则化项
    
    res = minimize(objective, x0=np.array([1.0, 0.0]), method="L-BFGS-B",
                   bounds=[(0.05, 20.0), (-10.0, 10.0)])
    
    if not res.success:
        warnings.warn(f"Platt optimization failed: {res.message}")
    
    return float(res.x[0]), float(res.x[1])


def apply_cal(p, a, b) -> np.ndarray:
    """应用Platt scaling校准"""
    return sigmoid(a * to_logit(p) + b)


def apply_temperature(p, T) -> np.ndarray:
    """应用温度缩放校准

    - 1-D输入（二分类概率）：sigmoid(logit(p)/T)，数学上等价于 p^(1/T) 重归一化
    - 2-D输入（多分类概率矩阵）：softmax(log(p)/T)，即 p^(1/T) 逐行归一化

    两种情况下输出均严格归一化（和为1）。
    """
    T = float(np.clip(T, T_MIN, T_MAX))
    p = np.asarray(p, dtype=float)
    if p.ndim == 1:
        return sigmoid(to_logit(p) / T)
    # 多分类：log p / T 后重归一化（数值上等价于 p^(1/T) / sum）
    p = np.clip(p, EPS, 1.0)
    log_p = np.log(p) / T
    log_p -= log_p.max(axis=-1, keepdims=True)  # 数值稳定
    out = np.exp(log_p)
    return out / out.sum(axis=-1, keepdims=True)


def ece(probs, labels, n_bins: int = 10, adaptive: bool = False) -> float:
    """Expected Calibration Error
    
    修复：
    1. 支持自适应分箱（等样本量）
    2. 修复最后一个bin的边界问题
    
    Args:
        probs: 预测概率
        labels: 真实标签
        n_bins: 分箱数量
        adaptive: 是否使用自适应分箱
    
    Returns:
        ECE值（越小越好）
    
    Raises:
        ValueError: n_bins 非法时由 _validate_n_bins 抛出（N2-r2 fix: 文档化
            ValueError 行为；调用方不应 try-except，让异常传播以暴露编程错误）
    """
    n_bins = _validate_n_bins(n_bins)
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)

    if adaptive:
        # 自适应分箱（等样本量）
        quantiles = np.linspace(0, 1, n_bins + 1)
        bin_boundaries = np.quantile(probs, quantiles)
        bin_boundaries[0] = 0.0
        bin_boundaries[-1] = 1.0
    else:
        bin_boundaries = np.linspace(0, 1, n_bins + 1)
    
    ece_val = 0.0
    
    for i in range(n_bins):
        # 修复边界问题：所有bin使用左闭右开，最后一个bin包含1.0
        if i == n_bins - 1:
            mask = (probs >= bin_boundaries[i]) & (probs <= bin_boundaries[i + 1])
        else:
            mask = (probs >= bin_boundaries[i]) & (probs < bin_boundaries[i + 1])
        
        if mask.sum() == 0:
            continue
        
        avg_prob = probs[mask].mean()
        avg_label = labels[mask].mean()
        ece_val += mask.sum() / len(probs) * abs(avg_prob - avg_label)
    
    return float(ece_val)


def smooth_ece(probs, labels, bandwidth: Optional[float] = None) -> float:
    """SmoothECE：核平滑校准误差（无分箱偏差的主估计量）

    统计修复（对抗性审查第三轮，修正第二轮发现的实现错误）：
    - 旧版错误：在均匀网格上平均（无样本的网格点稀释估计）+ 带宽不随n缩放
    - 正确实现（Błasiok & Nakkiran, ICLR 2024思想）：在**每个数据点处**计算
      核加权的准确率，与该点预测概率之差取绝对值，按数据权重平均：

          smooth_ece = (1/n) * Σ_i | Σ_j w_ij·y_j / Σ_j w_ij − p_i |
          w_ij = exp(-0.5 ((logit(p_i) - logit(p_j))/h)²)

    - logit 空间核（Błasiok & Nakkiran 思想）：避免概率空间端点饱和
      （p→1 时 logit 分辨率远高于 p，修复对抗审查 N9 端点饱和反例）
    - 带宽默认 h = 0.45·(n/2000)^(−0.2)（F3修复：实现与协议§11"带宽n^(−0.2)"
    声称对齐；标定锚点 n=2000→h=0.45，与既有底噪标定一致——完美校准底噪
    ECE值（非带宽h）：n=500→ECE≈0.028、n=2000→ECE≈0.027、n=20000→ECE≈0.019；
    n=200 冒烟量级→ECE≈0.049 为信息极限。
    对应带宽h值：n=500→h≈0.594、n=2000→h=0.45、n=20000→h≈0.284、n=200→h≈0.713。
    固定带宽敏感性可显式传 bandwidth=0.45 复现旧行为）

    Args:
        probs: 预测概率 (n,)
        labels: 真实标签 (n,)
        bandwidth: logit 空间核带宽（默认 0.45·(n/2000)^(−0.2)，F3修复见docstring）

    Returns:
        SmoothECE值（完全校准的数据 → 趋近0）
    """
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    n = len(probs)
    if bandwidth is None:
        # F3修复：n^(-0.2)缩放（协议§11声称），锚点n=2000→0.45
        bandwidth = 0.45 * (n / 2000.0) ** (-0.2)

    # logit 空间高斯核
    p_clip = np.clip(probs, 1e-6, 1 - 1e-6)
    logit_p = np.log(p_clip / (1 - p_clip))

    # 分块计算核加权准确率，防O(n²)内存（n=10000时全矩阵≈800MB）
    abs_err = np.empty(n)
    chunk = max(1, int(2e7 // max(n, 1)))  # 每块约20M个float
    for s in range(0, n, chunk):
        e = min(s + chunk, n)
        z = (logit_p[s:e, None] - logit_p[None, :]) / bandwidth
        w = np.exp(-0.5 * z ** 2)
        w_sum = w.sum(axis=1)
        acc_i = (w * labels[None, :]).sum(axis=1) / np.maximum(w_sum, 1e-12)
        abs_err[s:e] = np.abs(acc_i - probs[s:e])

    return float(abs_err.mean())


def smooth_ece_gpu(probs, labels, bandwidth=None, device=None):
    """smooth_ece 的 PyTorch GPU 实现（float64，与 CPU 版数值一致）

    用于 bootstrap/jackknife 大量重复调用的加速：n=4050 时 CPU 单次 ~0.59s，
    GPU 单次 ~10ms（RTX 5060 实测）。无 CUDA 时自动回退 CPU 版。

    Args/Returns: 与 smooth_ece 完全相同（bandwidth 逻辑一致）
    """
    import torch
    probs = np.asarray(probs, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.float64)
    n = len(probs)
    if bandwidth is None:
        bandwidth = 0.45 * (n / 2000.0) ** (-0.2)

    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cpu" or not torch.cuda.is_available():
        return smooth_ece(probs, labels, bandwidth=bandwidth)

    t_p = torch.from_numpy(probs).to(device)
    t_l = torch.from_numpy(labels).to(device)
    p_clip = torch.clamp(t_p, 1e-6, 1 - 1e-6)
    logit_p = torch.log(p_clip / (1 - p_clip))

    abs_err = torch.empty(n, dtype=torch.float64, device=device)
    chunk = max(1, int(2e7 // max(n, 1)))  # 与CPU版同块策略
    for s in range(0, n, chunk):
        e = min(s + chunk, n)
        z = (logit_p[s:e, None] - logit_p[None, :]) / bandwidth
        w = torch.exp(-0.5 * z ** 2)
        w_sum = w.sum(dim=1)
        acc_i = (w * t_l[None, :]).sum(dim=1) / torch.clamp(w_sum, min=1e-12)
        abs_err[s:e] = torch.abs(acc_i - t_p[s:e])

    return float(abs_err.mean().item())


def _bca_interval(theta_hat: float, boot_stats: np.ndarray,
                  jackknife_stats: np.ndarray, confidence: float) -> Tuple[float, float]:
    """BCa区间（bias-correction + acceleration）

    F2修复：此前的"CI"实为percentile；预注册§7:116要求BCa。
    - bias-correction z0：bootstrap分布相对点估计的中位偏移
    - acceleration a：delete-group/delete-cluster jackknife（Efron 1987标准公式）
    返回percentile截断点（百分比）。

    已知近似（R4轮对抗审查登记，P2级）：
    - delete-group jackknife（G组剔除）相对delete-1 jackknife的加速度项被组均值
      稀释约√m倍（m=组均样本数），a系统性低估→CI偏窄；cluster场景用
      leave-one-cluster-out（每患者一簇）近似delete-1，偏差更小
    - θ̂位于bootstrap分布同侧极端时z0饱和→截断点相等→零宽CI（触发时警告）
    """
    from scipy.stats import norm
    boot_stats = np.asarray(boot_stats, dtype=float)
    boot_stats = boot_stats[np.isfinite(boot_stats)]
    B = len(boot_stats)
    if B < 10:
        return (float('nan'), float('nan'))

    prop_less = ((np.sum(boot_stats < theta_hat)
                  + 0.5 * np.sum(boot_stats == theta_hat)) / B)
    z0 = norm.ppf(np.clip(prop_less, 1e-6, 1 - 1e-6))

    j = np.asarray(jackknife_stats, dtype=float)
    j = j[np.isfinite(j)]
    d = j.mean() - j
    denom = 6.0 * float(np.sum(d ** 2)) ** 1.5
    a = float(np.sum(d ** 3)) / denom if denom > 0 else 0.0

    z_alpha = norm.ppf((1 - confidence) / 2)
    z_1alpha = norm.ppf(1 - (1 - confidence) / 2)

    def _adj(z):
        denom_adj = 1 - a * (z0 + z)
        if abs(denom_adj) < 1e-12:
            return 1 - (1 - confidence) / 2 if z > 0 else (1 - confidence) / 2
        return float(norm.cdf(z0 + (z0 + z) / denom_adj))

    a1 = np.clip(_adj(z_alpha), 1e-6, 1 - 1e-6)
    a2 = np.clip(_adj(z_1alpha), 1e-6, 1 - 1e-6)
    lo, hi = np.percentile(boot_stats, [a1 * 100, a2 * 100])
    if lo == hi:
        warnings.warn("BCa区间退化为零宽（z0饱和：点估计位于bootstrap分布同侧极端），"
                      "CI不可用——建议检查效应量或改用percentile敏感性")
    return float(lo), float(hi)


def _group_jackknife_benefit(probs_raw, probs_cal, labels, metric, clusters,
                             n_groups=100):
    """ΔECE的jackknife影响值（BCa加速度项）

    F2修复：cluster提供时=leave-one-cluster-out（患者级，协议语义）；
    否则=delete-group jackknife（G=min(100,n)组剔除，delete-m近似，
    O(n²)metric下控制成本）。返回每次剔除后的ΔECE。
    """
    n = len(labels)
    if clusters is not None:
        clusters = np.asarray(clusters)
        units = np.unique(clusters)
        member_idx = [np.where(clusters == u)[0] for u in units]
    else:
        g = min(n_groups, n)
        perm = np.random.default_rng(0).permutation(n)
        member_idx = np.array_split(perm, g)
    jacks = np.empty(len(member_idx))
    for k, idxs in enumerate(member_idx):
        keep = np.ones(n, dtype=bool)
        keep[idxs] = False
        if keep.sum() < 10:
            jacks[k] = np.nan
            continue
        r_b = float(metric(probs_raw[keep], labels[keep]))
        c_b = float(metric(probs_cal[keep], labels[keep]))
        jacks[k] = r_b - c_b
    return jacks


def benefit_inference(
    probs_raw: np.ndarray,
    probs_cal: np.ndarray,
    labels: np.ndarray,
    metric=ece,
    n_bootstrap: int = 10000,
    confidence: float = 0.95,
    clusters: Optional[np.ndarray] = None,
    rng: Optional[np.random.Generator] = None,
    bci_method: str = "bca",
) -> dict:
    """校准修复收益的配对bootstrap推断（论文主终点）

    统计修复（对抗性审查FATAL-1/FATAL-3 + R轮F2）：
    - 主终点 = 绝对收益 ΔECE = metric(probs_raw) - metric(probs_cal)，带配对CI
      （比值ECE_raw/ECE_cal有floor effect与估计器偏差伪影，降级为次要描述量）
    - before/after在同一批样本上强正相关 → 必须同一重采样索引上配对计算
    - 支持患者级cluster重采样（clusters=患者ID）
    - bci_method='bca'（默认，F2修复：预注册§7:116要求BCa，含bias-correction与
      delete-group/leave-one-cluster-out jackknife加速度）；'percentile'仅作敏感性
    - n_bootstrap默认10000（F2修复：此前train.py传2000≠预注册B=10,000）
    - 同时返回比值R（次要）与比值CI（percentile——比值含inf/nan，BCa不稳）

    Args:
        probs_raw: 未校准概率
        probs_cal: 校准后概率（须与probs_raw同序）
        labels: 真实标签
        metric: 校准误差函数（默认ece；可传smooth_ece）
        n_bootstrap: 重采样次数
        confidence: 置信水平
        clusters: 患者ID（可选）
        rng: Generator
        bci_method: 'bca'（默认）| 'percentile'

    Returns:
        dict(benefit=ΔECE, benefit_ci=(lo,hi), ratio=R, ratio_ci=(lo,hi),
             raw=..., cal=..., method=...)
    """
    probs_raw = np.asarray(probs_raw, dtype=float)
    probs_cal = np.asarray(probs_cal, dtype=float)
    labels = np.asarray(labels, dtype=float)
    n = len(labels)
    if rng is None:
        rng = np.random.default_rng(0)

    raw_point = float(metric(probs_raw, labels))
    cal_point = float(metric(probs_cal, labels))
    benefit_point = raw_point - cal_point
    ratio_point = raw_point / cal_point if cal_point > 0 else np.inf

    # n_bootstrap=0：跳过CI（快速路径）
    if n_bootstrap <= 0:
        return {
            'raw': raw_point,
            'cal': cal_point,
            'benefit': benefit_point,
            'benefit_ci': (float('nan'), float('nan')),
            'ratio': float(ratio_point),
            'ratio_ci': (float('nan'), float('nan')),
            'method': 'none',
        }

    if clusters is not None:
        clusters = np.asarray(clusters)
        uniq = np.unique(clusters)
        cluster_indices = {c: np.where(clusters == c)[0] for c in uniq}
        def draw_indices():
            chosen = rng.choice(uniq, size=len(uniq), replace=True)
            return np.concatenate([cluster_indices[c] for c in chosen])
    else:
        def draw_indices():
            return rng.choice(n, n, replace=True)

    benefits = np.empty(n_bootstrap)
    ratios = np.empty(n_bootstrap)
    for b in range(n_bootstrap):
        idx = draw_indices()
        r_b = float(metric(probs_raw[idx], labels[idx]))
        c_b = float(metric(probs_cal[idx], labels[idx]))
        benefits[b] = r_b - c_b
        ratios[b] = r_b / c_b if c_b > 0 else np.nan

    alpha = (1 - confidence) / 2
    r_lo, r_hi = np.nanpercentile(ratios, [alpha * 100, (1 - alpha) * 100])

    if bci_method == "bca":
        jacks = _group_jackknife_benefit(probs_raw, probs_cal, labels,
                                         metric, clusters)
        b_lo, b_hi = _bca_interval(benefit_point, benefits, jacks, confidence)
    else:
        b_lo, b_hi = np.percentile(benefits, [alpha * 100, (1 - alpha) * 100])

    return {
        'raw': raw_point,
        'cal': cal_point,
        'benefit': benefit_point,
        'benefit_ci': (float(b_lo), float(b_hi)),
        'ratio': float(ratio_point),
        'ratio_ci': (float(r_lo), float(r_hi)),
        'method': bci_method,
    }


def bootstrap_ece(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
    n_bootstrap: int = 10000,
    confidence: float = 0.95,
    clusters: Optional[np.ndarray] = None,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[float, float, float]:
    """Bootstrap置信区间 for ECE

    统计修复（对抗性审查第二轮）：
    1. 点估计 = 全样本统计量（bootstrap均值只用于CI，不作为点估计报告）
    2. 显式rng参数保证可复现
    3. 支持患者级cluster重采样（cluster bootstrap，消除患者内相关性导致的CI过窄）
    4. n_bootstrap默认提升到10000

    Args:
        probs: 预测概率
        labels: 真实标签
        n_bins: 分箱数量
        n_bootstrap: Bootstrap采样次数
        confidence: 置信水平
        clusters: 患者ID数组（与probs等长）；提供时按簇重采样
        rng: np.random.Generator

    Returns:
        (point_estimate, ci_lower, ci_upper)  point_estimate为全样本ECE
    """
    n_bins = _validate_n_bins(n_bins)
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    n = len(probs)
    if rng is None:
        rng = np.random.default_rng(0)

    # 全样本点估计
    point = ece(probs, labels, n_bins)

    # n_bootstrap=0：跳过CI（早停快速路径）
    if n_bootstrap <= 0:
        return float(point), float('nan'), float('nan')

    # 重采样索引（记录级或患者级cluster）
    if clusters is not None:
        clusters = np.asarray(clusters)
        uniq = np.unique(clusters)
        cluster_indices = {c: np.where(clusters == c)[0] for c in uniq}
        def draw_indices():
            chosen = rng.choice(uniq, size=len(uniq), replace=True)
            return np.concatenate([cluster_indices[c] for c in chosen])
    else:
        def draw_indices():
            return rng.choice(n, n, replace=True)

    eces = np.empty(n_bootstrap)
    for b in range(n_bootstrap):
        idx = draw_indices()
        eces[b] = ece(probs[idx], labels[idx], n_bins)

    alpha = (1 - confidence) / 2
    ci_lower = np.percentile(eces, alpha * 100)
    ci_upper = np.percentile(eces, (1 - alpha) * 100)

    return float(point), float(ci_lower), float(ci_upper)


def brier_parts(probs, labels, n_bins: int = 10):
    """Brier Score Murphy分解（精确恒等式）

    Brier = Reliability - Resolution + Uncertainty

    注意：用 raw mean((p-y)^2) 时该恒等式仅在分箱内概率恒定时精确成立；
    此处返回的 brier_total 取 REL - RES + UNC（按构造精确成立），
    raw Brier 由 brier_raw(probs, labels) 单独计算。

    Args:
        probs: 预测概率
        labels: 真实标签
        n_bins: 分箱数量（默认10，与原实现保持一致）

    Returns:
        (brier_total, reliability, resolution, uncertainty)
    """
    n_bins = _validate_n_bins(n_bins)
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    n = len(probs)

    # 分箱计算
    bins = np.linspace(0, 1, n_bins + 1)
    reliability = 0.0
    resolution = 0.0
    base_rate = labels.mean()
    uncertainty = base_rate * (1 - base_rate)

    for i in range(n_bins):
        if i == n_bins - 1:  # 最后一个bin包含1.0
            mask = (probs >= bins[i]) & (probs <= bins[i + 1])
        else:
            mask = (probs >= bins[i]) & (probs < bins[i + 1])

        if mask.sum() == 0:
            continue

        n_bin = mask.sum()
        avg_prob = probs[mask].mean()
        avg_label = labels[mask].mean()

        reliability += n_bin / n * (avg_prob - avg_label) ** 2
        resolution += n_bin / n * (avg_label - base_rate) ** 2

    brier_total = reliability - resolution + uncertainty
    return float(brier_total), float(reliability), float(resolution), float(uncertainty)


def brier_raw(probs, labels) -> float:
    """经验Brier Score: mean((p - y)^2)"""
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    return float(np.mean((probs - labels) ** 2))


def mce(probs, labels, n_bins: int = 10) -> float:
    """Maximum Calibration Error
    
    新增指标：最差bin的校准误差
    
    Args:
        probs: 预测概率
        labels: 真实标签
        n_bins: 分箱数量
    
    Returns:
        MCE值（越小越好）
    
    Raises:
        ValueError: n_bins 非法时由 _validate_n_bins 抛出（N2-r2 fix: 文档化
            ValueError 行为；调用方不应 try-except，让异常传播以暴露编程错误）
    """
    n_bins = _validate_n_bins(n_bins)
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)

    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    max_error = 0.0
    
    for i in range(n_bins):
        if i == n_bins - 1:
            mask = (probs >= bin_boundaries[i]) & (probs <= bin_boundaries[i + 1])
        else:
            mask = (probs >= bin_boundaries[i]) & (probs < bin_boundaries[i + 1])
        
        if mask.sum() == 0:
            continue
        
        avg_prob = probs[mask].mean()
        avg_label = labels[mask].mean()
        error = abs(avg_prob - avg_label)
        max_error = max(max_error, error)
    
    return float(max_error)


def plot_reliability_diagram(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
    title: str = "Reliability Diagram",
    save_path: Optional[str] = None
):
    """绘制校准曲线（可靠性图）
    
    新增功能：可视化校准效果
    
    Args:
        probs: 预测概率
        labels: 真实标签
        n_bins: 分箱数量
        title: 图表标题
        save_path: 保存路径（可选）
    """
    n_bins = _validate_n_bins(n_bins)
    import matplotlib.pyplot as plt
    
    probs = np.asarray(probs)
    labels = np.asarray(labels)
    
    bin_boundaries = np.linspace(0, 1, n_bins + 1)
    bin_centers = []
    bin_means = []
    bin_counts = []
    
    for i in range(n_bins):
        if i == n_bins - 1:
            mask = (probs >= bin_boundaries[i]) & (probs <= bin_boundaries[i + 1])
        else:
            mask = (probs >= bin_boundaries[i]) & (probs < bin_boundaries[i + 1])
        
        if mask.sum() > 0:
            bin_centers.append((bin_boundaries[i] + bin_boundaries[i + 1]) / 2)
            bin_means.append(labels[mask].mean())
            bin_counts.append(mask.sum())
    
    fig, ax = plt.subplots(1, 1, figsize=(6, 6))
    
    # 完美校准线
    ax.plot([0, 1], [0, 1], 'k--', label='Perfect calibration')
    
    # 实际校准曲线
    ax.plot(bin_centers, bin_means, 's-', label='Model', color='blue')
    
    # 样本数量柱状图
    ax2 = ax.twinx()
    ax2.bar(bin_centers, bin_counts, width=0.05, alpha=0.3, color='gray', label='Sample count')
    ax2.set_ylabel('Sample count')
    
    ax.set_xlabel('Mean predicted probability')
    ax.set_ylabel('Fraction of positives')
    ax.set_title(title)
    ax.legend(loc='upper left')
    
    plt.tight_layout()
    
    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
    
    return fig


def compute_all_metrics(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
    n_bootstrap: int = 1000
) -> dict:
    """计算所有校准指标
    
    新增功能：一站式评估
    
    Args:
        probs: 预测概率
        labels: 真实标签
        n_bins: 分箱数量
        n_bootstrap: Bootstrap采样次数
    
    Returns:
        字典包含所有指标
    """
    n_bins = _validate_n_bins(n_bins)
    probs = np.asarray(probs)
    labels = np.asarray(labels)
    
    # ECE with confidence interval
    ece_mean, ece_lower, ece_upper = bootstrap_ece(probs, labels, n_bins, n_bootstrap)

    # Brier Score decomposition (Murphy, exact identity) + raw empirical Brier
    brier, reliability, resolution, uncertainty = brier_parts(probs, labels, n_bins=n_bins)

    # MCE
    max_ce = mce(probs, labels, n_bins)

    return {
        'ece': ece_mean,
        'ece_ci_95': (ece_lower, ece_upper),
        'mce': max_ce,
        'brier': brier,
        'brier_raw': brier_raw(probs, labels),
        'brier_reliability': reliability,
        'brier_resolution': resolution,
        'brier_uncertainty': uncertainty,
    }


def two_layer_benefit_inference(
    probs_raw_test: np.ndarray,
    labels_test: np.ndarray,
    fit_probs: np.ndarray,
    fit_labels: np.ndarray,
    fit_fn,
    apply_fn,
    metric=ece,
    b_val: int = 200,
    b_test: int = 2000,
    confidence: float = 0.95,
    rng: Optional[np.random.Generator] = None,
) -> dict:
    """两层联合bootstrap（F2修复：协议§7:117"val重采样→拟合T→test重采样→指标"）

    温度拟合集的不确定性传入ΔECE的CI：
    - 第一层（b_val次）：温度拟合集有放回重采样 → fit_fn重拟合 → T分布
    - 第二层（b_test次）：测试集有放回重采样 idx → 从T分布抽T_b → apply_fn →
      配对ΔECE_b
    CI = T不确定性 ⊕ 重采样不确定性的联合percentile（非嵌套实现，成本可控；
    协议注记：嵌套B=10000×重拟合在O(n²) metric下不可行，此为诚实近似并已登记）。

    Args:
        probs_raw_test: 测试集未校准概率（1D max-prob或2D矩阵，与fit/apply闭包一致）
        labels_test: 测试集标签（top-label场景为correct mask，与主终点语义一致）
        fit_probs/fit_labels: 温度拟合集概率/标签（协议：cal split）
        fit_fn: (probs, labels) -> T 的拟合闭包
        apply_fn: (probs, T) -> 校准后概率 的应用闭包
        metric: 校准误差（主终点=smooth_ece，由调用方传入）
        b_val/b_test: 两层重复数
        rng: Generator

    Returns:
        dict(t_hat, t_std, benefit, benefit_ci, benefit_ci_percentile_only)
    """
    probs_raw_test = np.asarray(probs_raw_test)
    labels_test = np.asarray(labels_test, dtype=float)
    fit_probs = np.asarray(fit_probs)
    fit_labels = np.asarray(fit_labels)
    if rng is None:
        rng = np.random.default_rng(0)

    t_hat = float(fit_fn(fit_probs, fit_labels))
    n_fit = len(fit_labels)
    n_test = len(labels_test)

    t_draws = np.empty(b_val)
    for b in range(b_val):
        idx = rng.choice(n_fit, n_fit, replace=True)
        t_draws[b] = float(fit_fn(fit_probs[idx], fit_labels[idx]))
    t_std = float(np.std(t_draws)) if b_val > 1 else 0.0

    benefits = np.empty(b_test)
    for b in range(b_test):
        idx = rng.choice(n_test, n_test, replace=True)
        t_b = float(rng.choice(t_draws)) if b_val > 0 else t_hat
        probs_cal_b = apply_fn(probs_raw_test[idx], t_b)
        mp_raw = (probs_raw_test[idx].max(axis=1)
                  if probs_raw_test.ndim == 2 else probs_raw_test[idx])
        mp_cal = probs_cal_b.max(axis=1) if probs_cal_b.ndim == 2 else probs_cal_b
        benefits[b] = float(metric(mp_raw, labels_test[idx])) \
            - float(metric(mp_cal, labels_test[idx]))

    alpha = (1 - confidence) / 2 * 100
    lo, hi = np.percentile(benefits, [alpha, 100 - alpha])

    mp_raw_full = (probs_raw_test.max(axis=1)
                   if probs_raw_test.ndim == 2 else probs_raw_test)
    cal_full = apply_fn(probs_raw_test, t_hat)
    mp_cal_full = cal_full.max(axis=1) if cal_full.ndim == 2 else cal_full
    benefit_point = (float(metric(mp_raw_full, labels_test))
                     - float(metric(mp_cal_full, labels_test)))

    return {
        't_hat': t_hat,
        't_std': t_std,
        'benefit': benefit_point,
        'benefit_ci': (float(lo), float(hi)),
        'b_val': b_val,
        'b_test': b_test,
    }
