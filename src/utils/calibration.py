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
    """
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
    - 带宽默认 h = 0.45（logit 空间固定带宽，标定：完美校准底噪 n=500→0.033、
      n=2000→0.027、n=20000→0.020；n=200 冒烟量级→0.050 为信息极限）

    Args:
        probs: 预测概率 (n,)
        labels: 真实标签 (n,)
        bandwidth: logit 空间核带宽（默认0.45）

    Returns:
        SmoothECE值（完全校准的数据 → 趋近0）
    """
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    n = len(probs)
    if bandwidth is None:
        bandwidth = 0.45  # logit 空间固定带宽（标定见 docstring）

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


def benefit_inference(
    probs_raw: np.ndarray,
    probs_cal: np.ndarray,
    labels: np.ndarray,
    metric=ece,
    n_bootstrap: int = 10000,
    confidence: float = 0.95,
    clusters: Optional[np.ndarray] = None,
    rng: Optional[np.random.Generator] = None,
) -> dict:
    """校准修复收益的配对bootstrap推断（论文主终点）

    统计修复（对抗性审查FATAL-1/FATAL-3）：
    - 主终点 = 绝对收益 ΔECE = metric(probs_raw) - metric(probs_cal)，带配对CI
      （比值ECE_raw/ECE_cal有floor effect与估计器偏差伪影，降级为次要描述量）
    - before/after在同一批样本上强正相关 → 必须同一重采样索引上配对计算
    - 支持患者级cluster重采样
    - 同时返回比值R（次要）与比值CI

    Args:
        probs_raw: 未校准概率
        probs_cal: 校准后概率（须与probs_raw同序）
        labels: 真实标签
        metric: 校准误差函数（默认ece；可传smooth_ece）
        n_bootstrap: 重采样次数
        confidence: 置信水平
        clusters: 患者ID（可选）
        rng: Generator

    Returns:
        dict(benefit=ΔECE, benefit_ci=(lo,hi), ratio=R, ratio_ci=(lo,hi),
             raw=..., cal=...)
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
    b_lo, b_hi = np.percentile(benefits, [alpha * 100, (1 - alpha) * 100])
    r_lo, r_hi = np.nanpercentile(ratios, [alpha * 100, (1 - alpha) * 100])

    return {
        'raw': raw_point,
        'cal': cal_point,
        'benefit': benefit_point,
        'benefit_ci': (float(b_lo), float(b_hi)),
        'ratio': float(ratio_point),
        'ratio_ci': (float(r_lo), float(r_hi)),
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


def brier_parts(probs, labels):
    """Brier Score Murphy分解（精确恒等式）

    Brier = Reliability - Resolution + Uncertainty

    注意：用 raw mean((p-y)^2) 时该恒等式仅在分箱内概率恒定时精确成立；
    此处返回的 brier_total 取 REL - RES + UNC（按构造精确成立），
    raw Brier 由 brier_raw(probs, labels) 单独计算。

    Returns:
        (brier_total, reliability, resolution, uncertainty)
    """
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    n = len(probs)

    # 分箱计算
    bins = np.linspace(0, 1, 11)
    reliability = 0.0
    resolution = 0.0
    base_rate = labels.mean()
    uncertainty = base_rate * (1 - base_rate)

    for i in range(10):
        if i == 9:  # 最后一个bin包含1.0
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
    """
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
    probs = np.asarray(probs)
    labels = np.asarray(labels)
    
    # ECE with confidence interval
    ece_mean, ece_lower, ece_upper = bootstrap_ece(probs, labels, n_bins, n_bootstrap)

    # Brier Score decomposition (Murphy, exact identity) + raw empirical Brier
    brier, reliability, resolution, uncertainty = brier_parts(probs, labels)

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
