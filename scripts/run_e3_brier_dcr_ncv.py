"""E3 核心实验：Brier Reliability + DCR + NCV + ECE 变化

==========================================================================
核心主张（正方论证）
==========================================================================
Brier Score 的 Murphy 分解（Murphy 1973）：

    Brier = Reliability - Resolution + Uncertainty

温度缩放（TS）在 T>0 时保持 argmax（不改变预测类别），因此：
  - Uncertainty（全局 base rate 的函数）严格不变
  - Resolution（分箱内标签频率与全局 base rate 的偏离）在**精确分箱极限**下不变
  - Reliability（分箱内预测概率与经验频率的偏离）是 TS 唯一显著影响的分量

∴ 主终点 = Reliability 组件的改善（而非总 Brier Score），因为：
  1. 总 Brier Score 的变化混合了 Reliability 改善和 Resolution 变化，效应稀释
  2. Reliability 直接度量"概率与频率的匹配程度"——校准的数学定义
  3. Resolution 和 Uncertainty 不由 TS 控制，报告它们的改善无意义

==========================================================================
关键假设
==========================================================================
H1（TS 只影响 Reliability）：
  - 精确分箱（每个唯一概率一个 bin）极限下**严格成立**
  - 10 等宽分箱下**近似成立**——TS 改变概率值可能导致样本跨 bin 迁移，
    从而轻微改变 Resolution。本脚本报告 ΔResolution 作为 H1 的诊断验证。

H2（TS 保持 argmax）：
  - T>0 时 softmax(logits/T) 的 argmax = softmax(logits) 的 argmax
  - **严格成立**（T>0 是单调变换）。∴ ECE 的 correct mask 在 TS 前后不变。

H3（配对独立性）：
  - 60 个 checkpoint 的改善值视为独立配对样本
  - **近似成立**——不同 checkpoint 使用不同 seed/pair/arch，但共享数据集和代码路径

==========================================================================
适用边界
==========================================================================
1. DCR（Decision Cost Reduction）——间接临床意义指标：
   - τ=0.5 阈值含义："模型置信度 > 50% 才决策，否则弃权"
   - abstain_cost=0.5（对称）是简化假设；真实临床中误诊与漏诊成本不对称
   - DCR 不替代正式决策曲线分析（DCA），仅作方向性证据

2. NCV（Net Clinical Value）对称定义的边界：
   - N_total = N_samples × N_classes 假设每个 (sample, class) 对独立
   - 实际上同一样本的 K 个 OvR 决策不独立（概率和为 1），NCV 方差被低估
   - 对称定义（TP/TN/FP/FN 等权）不反映临床偏好
   - NCV 是间接指标，不作为正式临床效用声明

3. Brier 分解的 10-bin 离散化：
   - 精确恒等式仅在分箱内概率恒定时成立
   - brier_total = REL - RES + UNC 按构造成立
   - raw Brier（mean((p-y)²)）与 brier_total 的偏差反映分箱粒度

==========================================================================
推理链条
==========================================================================
1. Murphy (1973): Brier = REL - RES + UNC（概率预报的角分解定理）
2. TS: p' = softmax(logits/T), T>0 → argmax 不变 → RES/UNC 不受控 [H1,H2]
3. 校准目标: min REL（使概率匹配经验频率）
4. ∴ 主终点 = REL_before - REL_after（TS 前后的 Reliability 改善，正值=好）
5. 统计: 60 个 checkpoint 配对 → paired t-test + Cohen's d + 95% bootstrap CI
6. 次要: DCR/NCV 量化决策层面收益 → BH FDR (q=0.05, 2 个次要终点)
7. 探索: ECE 变化（top-label）作为校准误差的补充度量

==========================================================================
潜在攻击点（正方主动披露）
==========================================================================
A1. "TS 只影响 Reliability"在 10-bin 下不严格：
    → 反驳：报告 ΔResolution/ΔReliability 比值，若 <<1 则近似成立
    → 若不成立：改用精确分箱（unique probs）或增加 bin 数到 50/100

A2. NCV 多类定义的合理性：
    → 攻击：N_total=N×K 中同一样本的 K 个决策不独立，NCV 方差被低估
    → 反驳：NCV 是方向性指标（正/负），不用于正式假设检验的效应量
    → 补充：报告 per-sample 聚合的 NCV（N_total=N）作为敏感性

A3. DCR 的 abstain_cost=0.5 选择：
    → 攻击：对称成本不反映临床现实
    → 反驳：DCR 在 abstain_cost ∈ [0,1] 上单调，符号不变（TS 改善决策的方向）
    → 补充：报告 abstain_cost=0.3 和 0.7 的敏感性

A4. 60 个 checkpoint 的独立性：
    → 攻击：共享数据集 → 改善值有相关性 → paired t-test 的 p 值偏小
    → 反驳：不同 pair 使用不同源/目标域，不同 seed 独立训练
    → 补充：报告 pair-level 聚合（6 个 pair 的均值）作为保守分析

A5. top-label vs per-class OvR Brier 分解：
    → 攻击：top-label 丢弃非最大类的信息
    → 反驳：top-label 与 ECE 主终点语义一致（置信度-正确性映射）
    → 补充：同时报告 per-class OvR 作为敏感性

==========================================================================
输出
==========================================================================
1. results/c1_brier_reliability.csv         — 60 checkpoint × Brier 3 分量（TS 前后, ID+OOD）
2. results/c1_dcr_ncv_multiclass.csv        — 60 checkpoint × DCR/NCV/ECE（TS 前后, ID+OOD）
3. results/c1_brier_reliability_summary.csv — 主终点汇总（Cohen's d, 95% CI, paired t-test）
4. results/c1_dcr_ncv_summary.csv           — 次要终点汇总（t-test, BH FDR q=0.05）

用法:
    python scripts/run_e3_brier_dcr_ncv.py           # 用缓存概率（若存在）
    python scripts/run_e3_brier_dcr_ncv.py --regen   # 重新前向传播生成概率
    python scripts/run_e3_brier_dcr_ncv.py --limit 240  # 冒烟测试
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# 路径设置
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.utils.calibration import (  # noqa: E402
    fit_temperature, apply_temperature, ece, brier_parts, brier_raw,
)

# ---------------------------------------------------------------------------
# 实验配置
# ---------------------------------------------------------------------------
PAIRS = [
    "ptbxl_chapman", "ptbxl_cpsc",
    "chapman_ptbxl", "chapman_cpsc",
    "cpsc_ptbxl", "cpsc_chapman",
]
ARCHS = ["inceptiontime", "resnet1d"]
SEEDS = [42, 43, 44, 45, 46]
# 6 pairs × 2 archs × 5 seeds = 60 checkpoints

DATA_DIRS = {
    "ptbxl": _PROJECT_ROOT / "data" / "ptbxl_processed",
    "chapman": _PROJECT_ROOT / "data" / "chapman_processed_v2",
    "cpsc": _PROJECT_ROOT / "data" / "cpsc_processed",
}
DATASET_NUM_CLASSES = {"ptbxl": 5, "chapman": 5, "cpsc": 4}

TAU = 0.5           # DCR/NCV 决策阈值
ABSTAIN_COST = 0.5  # 弃权成本（对称）
N_BINS = 10         # Brier 分解分箱数
N_BOOTSTRAP = 10000 # Cohen's d bootstrap CI
FDR_Q = 0.05        # BH FDR 显著性水平
RNG_SEED = 42       # 全局可复现种子

RESULTS_DIR = _PROJECT_ROOT / "results"


# ===========================================================================
# 第一部分：指标计算
# ===========================================================================

def _to_onehot(labels: np.ndarray, K: int) -> np.ndarray:
    """类索引 → one-hot (N, K)"""
    onehot = np.zeros((len(labels), K), dtype=float)
    onehot[np.arange(len(labels)), labels] = 1.0
    return onehot


def brier_parts_toplabel(probs: np.ndarray, labels: np.ndarray,
                         n_bins: int = N_BINS) -> Tuple[float, float, float, float]:
    """Top-label Brier 分解

    将多分类转化为二分类：p = max prob, y = 1[argmax == label]
    与 calibration.compute_all_metrics 语义一致（置信度-正确性映射）。

    Returns:
        (brier_total, reliability, resolution, uncertainty)
    """
    max_p = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == labels).astype(float)
    return brier_parts(max_p, correct, n_bins=n_bins)


def brier_parts_ovr(probs: np.ndarray, labels: np.ndarray,
                    n_bins: int = N_BINS) -> Tuple[float, float, float, float]:
    """Per-class OvR Brier 分解（平均 over classes）

    对每个类 k 做二分类 Brier 分解：(p_k vs 1[label==k])，然后平均。
    利用全部概率信息，作为 top-label 的敏感性分析。

    Returns:
        (brier_total_mean, reliability_mean, resolution_mean, uncertainty_mean)
    """
    K = probs.shape[1]
    rels, ress, uncs, briers = [], [], [], []
    for k in range(K):
        p_k = probs[:, k]
        y_k = (labels == k).astype(float)
        b, r, s, u = brier_parts(p_k, y_k, n_bins=n_bins)
        briers.append(b)
        rels.append(r)
        ress.append(s)
        uncs.append(u)
    return float(np.mean(briers)), float(np.mean(rels)), float(np.mean(ress)), float(np.mean(uncs))


def ece_toplabel(probs: np.ndarray, labels: np.ndarray, n_bins: int = N_BINS) -> float:
    """Top-label ECE（与 calibration.ece 一致）"""
    max_p = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == labels).astype(float)
    return ece(max_p, correct, n_bins=n_bins)


def dcr_multiclass(probs_raw: np.ndarray, probs_cal: np.ndarray,
                   labels: np.ndarray, tau: float = TAU,
                   abstain_cost: float = ABSTAIN_COST) -> Tuple[float, float, float]:
    """Decision Cost Reduction at threshold τ

    决策规则：if max_p > τ → 预测 argmax；else → 弃权
    成本：错误决策=1，弃权=abstain_cost，正确决策=0
    DCR = Cost_raw - Cost_cal（正值=TS 减少了决策成本=好）

    Returns:
        (dcr, cost_raw, cost_cal)
    """
    def _cost(probs: np.ndarray, labels: np.ndarray) -> float:
        max_p = probs.max(axis=1)
        pred = probs.argmax(axis=1)
        decide = max_p > tau
        n_wrong = int(((pred != labels) & decide).sum())
        n_abstain = int((~decide).sum())
        return (n_wrong + abstain_cost * n_abstain) / len(labels)

    cost_raw = _cost(probs_raw, labels)
    cost_cal = _cost(probs_cal, labels)
    return cost_raw - cost_cal, cost_raw, cost_cal


def ncv_multiclass(probs_raw: np.ndarray, probs_cal: np.ndarray,
                   labels: np.ndarray, tau: float = TAU) -> Dict:
    """Net Clinical Value（对称定义）

    NCV = (TP_improved + TN_improved - FP_worsened - FN_worsened) / N_total
    N_total = N_samples × N_classes

    对每个 (sample, class) 对：
      raw_pos = p_raw > τ,  cal_pos = p_cal > τ,  true_pos = (label == class)
      TP_improved: raw=neg → cal=pos, true=pos  （正确地变得更自信）
      TN_improved: raw=pos → cal=neg, true=neg  （正确地变得更不自信）
      FP_worsened: raw=neg → cal=pos, true=neg  （错误地变得更自信）
      FN_worsened: raw=pos → cal=neg, true=pos  （错误地变得更不自信）

    Returns:
        dict(ncv, tp_improved, tn_improved, fp_worsened, fn_worsened, n_total,
             ncv_per_sample)  # ncv_per_sample 用 N_total=N 作敏感性
    """
    N, K = probs_raw.shape
    N_total = N * K

    onehot = np.zeros((N, K), dtype=bool)
    onehot[np.arange(N), labels] = True

    raw_pos = probs_raw > tau       # (N, K)
    cal_pos = probs_cal > tau       # (N, K)
    true_pos = onehot               # (N, K)

    tp_improved = int(((~raw_pos) & cal_pos & true_pos).sum())
    tn_improved = int((raw_pos & (~cal_pos) & (~true_pos)).sum())
    fp_worsened = int(((~raw_pos) & cal_pos & (~true_pos)).sum())
    fn_worsened = int((raw_pos & (~cal_pos) & true_pos).sum())

    ncv = (tp_improved + tn_improved - fp_worsened - fn_worsened) / N_total
    # 敏感性：per-sample 聚合（N_total=N）
    ncv_per_sample = (tp_improved + tn_improved - fp_worsened - fn_worsened) / N

    return {
        'ncv': float(ncv),
        'tp_improved': tp_improved,
        'tn_improved': tn_improved,
        'fp_worsened': fp_worsened,
        'fn_worsened': fn_worsened,
        'n_total': int(N_total),
        'ncv_per_sample': float(ncv_per_sample),
    }


def compute_all_metrics_for_split(probs_raw: np.ndarray, probs_cal: np.ndarray,
                                  labels: np.ndarray) -> Dict:
    """对一个测试集（ID 或 OOD）计算 TS 前后的所有指标

    Returns:
        dict with all E3 metrics for this split
    """
    # --- Brier 3 分量（top-label，主终点） ---
    b_raw, rel_raw, res_raw, unc_raw = brier_parts_toplabel(probs_raw, labels)
    b_cal, rel_cal, res_cal, unc_cal = brier_parts_toplabel(probs_cal, labels)

    # --- Brier 3 分量（per-class OvR，敏感性） ---
    bo_raw, relo_raw, reso_raw, unco_raw = brier_parts_ovr(probs_raw, labels)
    bo_cal, relo_cal, reso_cal, unco_cal = brier_parts_ovr(probs_cal, labels)

    # --- raw Brier Score（经验均值，无分箱） ---
    brier_raw_before = brier_raw(probs_raw.max(axis=1),
                                 (probs_raw.argmax(axis=1) == labels).astype(float))
    brier_raw_after = brier_raw(probs_cal.max(axis=1),
                                (probs_cal.argmax(axis=1) == labels).astype(float))

    # --- ECE（top-label，探索性） ---
    ece_before = ece_toplabel(probs_raw, labels)
    ece_after = ece_toplabel(probs_cal, labels)

    # --- DCR（次要终点 1） ---
    dcr_val, cost_raw, cost_cal = dcr_multiclass(probs_raw, probs_cal, labels)

    # --- NCV（次要终点 2） ---
    ncv_result = ncv_multiclass(probs_raw, probs_cal, labels)

    return {
        # Brier top-label（主终点）
        'brier_toplabel_before': b_raw,
        'brier_toplabel_after': b_cal,
        'reliability_toplabel_before': rel_raw,
        'reliability_toplabel_after': rel_cal,
        'resolution_toplabel_before': res_raw,
        'resolution_toplabel_after': res_cal,
        'uncertainty_toplabel_before': unc_raw,
        'uncertainty_toplabel_after': unc_cal,
        'delta_reliability_toplabel': rel_raw - rel_cal,  # 正值=改善
        'delta_resolution_toplabel': res_raw - res_cal,   # 诊断 H1
        'delta_uncertainty_toplabel': unc_raw - unc_cal,  # 应≈0
        # Brier per-class OvR（敏感性）
        'reliability_ovr_before': relo_raw,
        'reliability_ovr_after': relo_cal,
        'delta_reliability_ovr': relo_raw - relo_cal,
        # raw Brier
        'brier_raw_before': brier_raw_before,
        'brier_raw_after': brier_raw_after,
        # ECE
        'ece_before': ece_before,
        'ece_after': ece_after,
        'delta_ece': ece_before - ece_after,  # 正值=改善
        # DCR
        'dcr': dcr_val,
        'decision_cost_before': cost_raw,
        'decision_cost_after': cost_cal,
        # NCV
        'ncv': ncv_result['ncv'],
        'ncv_tp_improved': ncv_result['tp_improved'],
        'ncv_tn_improved': ncv_result['tn_improved'],
        'ncv_fp_worsened': ncv_result['fp_worsened'],
        'ncv_fn_worsened': ncv_result['fn_worsened'],
        'ncv_n_total': ncv_result['n_total'],
        'ncv_per_sample': ncv_result['ncv_per_sample'],
    }


# ===========================================================================
# 第二部分：统计检验
# ===========================================================================

def cohen_d_paired(before: np.ndarray, after: np.ndarray,
                   improvement_direction: str = "decrease") -> Dict:
    """配对 Cohen's d + 95% bootstrap CI + paired t-test

    Args:
        before, after: TS 前后的指标值（60 个配对）
        improvement_direction: "decrease"（指标减小为改善，如 Reliability/ECE）
                               或 "increase"（指标增大为改善，如 DCR/NCV）

    Returns:
        dict(mean_before, mean_after, mean_diff, std_diff, cohen_d,
             cohen_d_ci_lo, cohen_d_ci_hi, t_stat, p_value, n)
    """
    from scipy.stats import ttest_rel

    before = np.asarray(before, dtype=float)
    after = np.asarray(after, dtype=float)
    n = len(before)

    if improvement_direction == "decrease":
        diff = before - after  # 正值=改善
    else:
        diff = after - before  # 正值=改善

    mean_diff = float(np.mean(diff))
    std_diff = float(np.std(diff, ddof=1)) if n > 1 else 0.0
    cohen_d = mean_diff / std_diff if std_diff > 1e-12 else 0.0

    # paired t-test（scipy 的 ttest_rel 检验 before==after 的 H0）
    t_stat, p_value = ttest_rel(before, after)

    # 95% CI for Cohen's d via bootstrap
    rng = np.random.default_rng(RNG_SEED)
    boot_ds = np.empty(N_BOOTSTRAP)
    for b in range(N_BOOTSTRAP):
        idx = rng.choice(n, n, replace=True)
        d_b = diff[idx]
        s_b = np.std(d_b, ddof=1)
        boot_ds[b] = np.mean(d_b) / s_b if s_b > 1e-12 else 0.0
    ci_lo, ci_hi = np.percentile(boot_ds, [2.5, 97.5])

    return {
        'mean_before': float(np.mean(before)),
        'mean_after': float(np.mean(after)),
        'mean_diff': mean_diff,
        'std_diff': std_diff,
        'cohen_d': float(cohen_d),
        'cohen_d_ci_lo': float(ci_lo),
        'cohen_d_ci_hi': float(ci_hi),
        't_stat': float(t_stat),
        'p_value': float(p_value),
        'n': n,
    }


def bh_fdr(p_values: List[float], q: float = FDR_Q) -> Tuple[List[bool], List[float]]:
    """Benjamini-Hochberg FDR 校正

    Args:
        p_values: 原始 p 值列表
        q: FDR 显著性水平

    Returns:
        (reject_list, adjusted_p_list)
    """
    p = np.asarray(p_values, dtype=float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order]

    # BH 临界值: k * q / n
    critical = q * np.arange(1, n + 1) / n

    # 找最大的 k 使得 p_(k) <= k*q/n
    reject_flags = np.zeros(n, dtype=bool)
    max_k = 0
    for i in range(n - 1, -1, -1):
        if ranked[i] <= critical[i]:
            max_k = i + 1
            break
    reject_flags[order[:max_k]] = True

    # 调整 p 值: p_adj_(k) = min_{j>=k} (p_(j) * n / j)
    adj_p_sorted = ranked * n / np.arange(1, n + 1)
    # 从大到小取累积最小，保证单调性
    adj_p_sorted = np.minimum.accumulate(adj_p_sorted[::-1])[::-1]
    adj_p = np.empty(n)
    adj_p[order] = adj_p_sorted
    adj_p = np.clip(adj_p, 0, 1)

    return reject_flags.tolist(), adj_p.tolist()


# ===========================================================================
# 第三部分：概率获取（带缓存）
# ===========================================================================

def _parse_pair(pair: str) -> Tuple[str, str]:
    """ptbxl_chapman → (ptbxl, chapman)"""
    parts = pair.split("_")
    return parts[0], parts[1]


def get_num_classes(source: str, target: str) -> int:
    """涉及 CPSC → 4 类（SUBSPACE_CPSC 对称降级）；否则 5 类"""
    return min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])


def load_or_compute_probs(pair: str, arch: str, seed: int,
                          regen: bool, limit: Optional[int],
                          batch_size: int = 16, num_workers: int = 0) -> Optional[Dict]:
    """加载或计算一个 checkpoint 的原始概率

    缓存路径: checkpoints/transfer/{pair}/{arch}/seed{seed}/e3_probs.npz

    Returns:
        dict(cal_probs, cal_labels, id_probs, id_labels, ood_probs, ood_labels,
             T, num_classes) 或 None（加载失败）
    """
    source, target = _parse_pair(pair)
    ckpt_dir = _PROJECT_ROOT / "checkpoints" / "transfer" / pair / arch / f"seed{seed}"
    cache_path = ckpt_dir / "e3_probs.npz"
    ckpt_path = ckpt_dir / "best_model.pt"

    # --- 编码护栏（必须在读缓存之前） ---
    # e3_probs.npz 里存的是「某套编码下的标签」，所以要先确定该用哪套。
    # 全部 60 份 e3_probs.npz 的 mtime = 2026-09-10 12:24，落在污染窗口内，
    # 而 results/c1_brier_reliability.csv（12:29）正是从它们算出来的。
    # 参见 results/_L2_SHIFT_CONTAMINATION_NOTICE.md。
    from src.data.mapping import SUBSPACE_CPSC
    from src.utils.encoding_guard import (
        assert_cache_encoding, checkpoint_subspace, encoding_stamp,
    )
    K = get_num_classes(source, target)
    runtime_subspace = SUBSPACE_CPSC if K == 4 else None
    subspace = checkpoint_subspace(ckpt_dir, K, runtime_subspace)
    encoding = encoding_stamp(K, subspace)

    # --- 尝试从缓存加载 ---
    if not regen and cache_path.exists():
        try:
            data = np.load(cache_path, allow_pickle=False)
            assert_cache_encoding(cache_path, data, K, subspace,
                                  allow_unstamped=False)
            return {
                'cal_probs': data['cal_probs'],
                'cal_labels': data['cal_labels'],
                'id_probs': data['id_probs'],
                'id_labels': data['id_labels'],
                'ood_probs': data['ood_probs'],
                'ood_labels': data['ood_labels'],
                'T': float(data['T']),
                'num_classes': int(data['num_classes']),
            }
        except Exception as e:
            warnings.warn(f"缓存加载失败 {cache_path}: {e}，将重新计算")

    # --- 检查 checkpoint 是否存在 ---
    if not ckpt_path.exists():
        warnings.warn(f"Checkpoint 不存在: {ckpt_path}")
        return None

    # --- 检查数据目录 ---
    src_data = DATA_DIRS.get(source)
    tgt_data = DATA_DIRS.get(target)
    if src_data is None or tgt_data is None or not src_data.exists() or not tgt_data.exists():
        warnings.warn(f"数据目录不存在: {src_data} 或 {tgt_data}")
        return None

    # --- 加载模型并前向传播 ---
    try:
        import torch
        from src.models.ecg_classifier import ECGClassifier
        from train import (
            set_seed, evaluate, create_dataloader,
            build_ptbxl_datasets, build_chapman_datasets, build_cpsc_datasets,
        )
        from src.data.mapping import SUBSPACE_CPSC
    except ImportError as e:
        warnings.warn(f"无法导入训练依赖: {e}")
        return None

    builders = {
        "ptbxl": build_ptbxl_datasets,
        "chapman": build_chapman_datasets,
        "cpsc": build_cpsc_datasets,
    }

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    set_seed(seed)

    # 构建源数据集
    try:
        if source == "cpsc":
            src_ds, src_clusters = builders[source](str(src_data), seed, limit=limit)
        elif subspace is not None:
            src_ds, src_clusters = builders[source](str(src_data), seed, limit=limit, subspace=subspace)
        else:
            src_ds, src_clusters = builders[source](str(src_data), seed, limit=limit)
    except Exception as e:
        warnings.warn(f"构建源数据集失败 ({source}): {e}")
        return None

    # cal 和 test 的 DataLoader
    cal_loader = create_dataloader(src_ds["cal"], batch_size, shuffle=False, num_workers=num_workers)
    test_loader = create_dataloader(src_ds["test"], batch_size, shuffle=False, num_workers=num_workers)

    # 加载模型
    try:
        ckpt = torch.load(ckpt_path, weights_only=False, map_location=device)
        sd = ckpt["model_state_dict"]
        # 推断 d_model 和 n_layers
        if arch == "mamba":
            inferred_d = sd["backbone.stem.0.weight"].shape[0]
            import re
            layer_ids = {re.match(r"backbone\.layers\.(\d+)\.", k).group(1)
                         for k in sd if re.match(r"backbone\.layers\.(\d+)\.", k)}
            inferred_n = len(layer_ids)
        elif "backbone.proj.weight" in sd:
            inferred_d = sd["backbone.proj.weight"].shape[0]
            inferred_n = 2
        else:
            inferred_d = 64
            inferred_n = 2
        model = ECGClassifier(in_channels=12, d_model=inferred_d,
                              n_layers=inferred_n, num_classes=K,
                              dropout=0.1, backbone_type=arch).to(device)
        model.load_state_dict(sd)
    except Exception as e:
        warnings.warn(f"模型加载失败 {ckpt_path}: {e}")
        return None

    # 前向传播：source-cal, source-test (ID)
    cal_eval = evaluate(model, cal_loader, device, compute_calibration=False)
    test_eval = evaluate(model, test_loader, device, compute_calibration=False)
    cal_probs = cal_eval["probs"]
    cal_labels = cal_eval["labels"]
    id_probs = test_eval["probs"]
    id_labels = test_eval["labels"]

    # 构建目标数据集并前向传播 (OOD)
    try:
        if target == "cpsc":
            tgt_ds, tgt_clusters = builders[target](str(tgt_data), seed, limit=limit)
        elif subspace is not None:
            tgt_ds, tgt_clusters = builders[target](str(tgt_data), seed, limit=limit, subspace=subspace)
        else:
            tgt_ds, tgt_clusters = builders[target](str(tgt_data), seed, limit=limit)
        tgt_loader = create_dataloader(tgt_ds["test"], batch_size, shuffle=False, num_workers=num_workers)
        tgt_eval = evaluate(model, tgt_loader, device, compute_calibration=False)
        ood_probs = tgt_eval["probs"]
        ood_labels = tgt_eval["labels"]
    except Exception as e:
        warnings.warn(f"目标数据集评估失败 ({target}): {e}")
        return None

    # 拟合温度缩放（在 source-cal 上）
    cal_onehot = _to_onehot(cal_labels, K)
    T = fit_temperature(cal_probs, cal_onehot)

    # 缓存
    try:
        np.savez_compressed(
            str(cache_path),
            cal_probs=cal_probs, cal_labels=cal_labels,
            id_probs=id_probs, id_labels=id_labels,
            ood_probs=ood_probs, ood_labels=ood_labels,
            T=np.array([T]), num_classes=np.array([K]),
            # 编码戳：无此戳的缓存一律被 assert_cache_encoding 拒绝
            label_encoding=np.array(encoding),
        )
    except Exception as e:
        warnings.warn(f"缓存保存失败: {e}")

    return {
        'cal_probs': cal_probs, 'cal_labels': cal_labels,
        'id_probs': id_probs, 'id_labels': id_labels,
        'ood_probs': ood_probs, 'ood_labels': ood_labels,
        'T': T, 'num_classes': K,
    }


# ===========================================================================
# 第四部分：主流程
# ===========================================================================

def run_experiment(args: argparse.Namespace) -> Tuple[List[Dict], List[Dict]]:
    """运行 E3 实验，返回 (brier_rows, dcr_ncv_rows)"""

    brier_rows: List[Dict] = []
    dcr_ncv_rows: List[Dict] = []
    total = len(PAIRS) * len(ARCHS) * len(SEEDS)
    idx = 0

    for pair in PAIRS:
        source, target = _parse_pair(pair)
        for arch in ARCHS:
            for seed in SEEDS:
                idx += 1
                tag = f"[{idx}/{total}] {pair}/{arch}/seed{seed}"
                print(f"{tag} 加载概率...", end=" ", flush=True)

                probs_data = load_or_compute_probs(
                    pair, arch, seed,
                    regen=args.regen, limit=args.limit,
                    batch_size=args.batch_size, num_workers=args.num_workers,
                )

                if probs_data is None:
                    print("SKIP (概率不可用)")
                    continue

                T = probs_data['T']
                K = probs_data['num_classes']

                # 应用温度缩放
                id_probs_raw = probs_data['id_probs']
                id_labels = probs_data['id_labels']
                ood_probs_raw = probs_data['ood_probs']
                ood_labels = probs_data['ood_labels']

                id_probs_cal = apply_temperature(id_probs_raw, T)
                ood_probs_cal = apply_temperature(ood_probs_raw, T)

                # 计算指标（ID 和 OOD）
                id_metrics = compute_all_metrics_for_split(id_probs_raw, id_probs_cal, id_labels)
                ood_metrics = compute_all_metrics_for_split(ood_probs_raw, ood_probs_cal, ood_labels)

                # 组装行
                base = {
                    'pair': pair, 'source': source, 'target': target,
                    'arch': arch, 'seed': seed, 'T': T, 'num_classes': K,
                    'n_id': len(id_labels), 'n_ood': len(ood_labels),
                }

                # Brier reliability 行（ID + OOD 各一列）
                brier_row = {**base}
                for split_name, m in [('id', id_metrics), ('ood', ood_metrics)]:
                    for key, val in m.items():
                        if key.startswith('brier') or key.startswith('reliability') \
                           or key.startswith('resolution') or key.startswith('uncertainty') \
                           or key.startswith('delta_reliability') or key.startswith('delta_resolution') \
                           or key.startswith('delta_uncertainty'):
                            brier_row[f'{key}_{split_name}'] = val
                brier_rows.append(brier_row)

                # DCR/NCV/ECE 行
                dcr_row = {**base}
                for split_name, m in [('id', id_metrics), ('ood', ood_metrics)]:
                    for key in ['ece_before', 'ece_after', 'delta_ece',
                                'dcr', 'decision_cost_before', 'decision_cost_after',
                                'ncv', 'ncv_tp_improved', 'ncv_tn_improved',
                                'ncv_fp_worsened', 'ncv_fn_worsened',
                                'ncv_n_total', 'ncv_per_sample']:
                        dcr_row[f'{key}_{split_name}'] = m[key]
                dcr_ncv_rows.append(dcr_row)

                print(f"T={T:.3f} ΔREL_id={id_metrics['delta_reliability_toplabel']:+.4f} "
                      f"ΔREL_ood={ood_metrics['delta_reliability_toplabel']:+.4f} "
                      f"DCR_ood={ood_metrics['dcr']:+.4f} NCV_ood={ood_metrics['ncv']:+.4f}")

    return brier_rows, dcr_ncv_rows


def summarize_and_write(brier_rows: List[Dict], dcr_ncv_rows: List[Dict]) -> None:
    """汇总统计 + 写入 4 个 CSV"""

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    n = len(brier_rows)
    print(f"\n成功处理 {n} / 60 个 checkpoint")

    if n == 0:
        print("WARNING: 无数据，跳过汇总")
        return

    # ==================================================================
    # CSV 1: c1_brier_reliability.csv（逐 checkpoint）
    # ==================================================================
    csv1 = RESULTS_DIR / "c1_brier_reliability.csv"
    brier_fields = [
        'pair', 'source', 'target', 'arch', 'seed', 'T', 'num_classes', 'n_id', 'n_ood',
        # ID
        'brier_toplabel_before_id', 'brier_toplabel_after_id',
        'reliability_toplabel_before_id', 'reliability_toplabel_after_id',
        'resolution_toplabel_before_id', 'resolution_toplabel_after_id',
        'uncertainty_toplabel_before_id', 'uncertainty_toplabel_after_id',
        'delta_reliability_toplabel_id', 'delta_resolution_toplabel_id',
        'delta_uncertainty_toplabel_id',
        'reliability_ovr_before_id', 'reliability_ovr_after_id', 'delta_reliability_ovr_id',
        'brier_raw_before_id', 'brier_raw_after_id',
        # OOD
        'brier_toplabel_before_ood', 'brier_toplabel_after_ood',
        'reliability_toplabel_before_ood', 'reliability_toplabel_after_ood',
        'resolution_toplabel_before_ood', 'resolution_toplabel_after_ood',
        'uncertainty_toplabel_before_ood', 'uncertainty_toplabel_after_ood',
        'delta_reliability_toplabel_ood', 'delta_resolution_toplabel_ood',
        'delta_uncertainty_toplabel_ood',
        'reliability_ovr_before_ood', 'reliability_ovr_after_ood', 'delta_reliability_ovr_ood',
        'brier_raw_before_ood', 'brier_raw_after_ood',
    ]
    with open(csv1, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# E3 主终点：Brier Reliability 改善（Murphy 分解）"])
        w.writerow(["# Brier = Reliability - Resolution + Uncertainty (Murphy 1973)"])
        w.writerow(["# 主终点 = delta_reliability_toplabel（TS 前后，正值=改善）"])
        w.writerow(["# 主分析在 OOD 上（60 配对），ID 作参考"])
        w.writerow(["# n_checkpoints", n])
        w.writerow([])
        w.writerow(brier_fields)
        for row in brier_rows:
            w.writerow([row.get(k, '') for k in brier_fields])
    print(f"写入 {csv1}")

    # ==================================================================
    # CSV 2: c1_dcr_ncv_multiclass.csv（逐 checkpoint）
    # ==================================================================
    csv2 = RESULTS_DIR / "c1_dcr_ncv_multiclass.csv"
    dcr_fields = [
        'pair', 'source', 'target', 'arch', 'seed', 'T', 'num_classes', 'n_id', 'n_ood',
        # ID
        'ece_before_id', 'ece_after_id', 'delta_ece_id',
        'dcr_id', 'decision_cost_before_id', 'decision_cost_after_id',
        'ncv_id', 'ncv_tp_improved_id', 'ncv_tn_improved_id',
        'ncv_fp_worsened_id', 'ncv_fn_worsened_id', 'ncv_n_total_id', 'ncv_per_sample_id',
        # OOD
        'ece_before_ood', 'ece_after_ood', 'delta_ece_ood',
        'dcr_ood', 'decision_cost_before_ood', 'decision_cost_after_ood',
        'ncv_ood', 'ncv_tp_improved_ood', 'ncv_tn_improved_ood',
        'ncv_fp_worsened_ood', 'ncv_fn_worsened_ood', 'ncv_n_total_ood', 'ncv_per_sample_ood',
    ]
    with open(csv2, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# E3 次要终点：DCR + NCV + 探索性 ECE 变化"])
        w.writerow(["# DCR: Decision Cost Reduction, τ=0.5, abstain_cost=0.5"])
        w.writerow(["# NCV: Net Clinical Value, 对称定义, N_total=N_samples×N_classes"])
        w.writerow(["# ECE: Expected Calibration Error (top-label, 10 bins)"])
        w.writerow(["# n_checkpoints", n])
        w.writerow([])
        w.writerow(dcr_fields)
        for row in dcr_ncv_rows:
            w.writerow([row.get(k, '') for k in dcr_fields])
    print(f"写入 {csv2}")

    # ==================================================================
    # CSV 3: c1_brier_reliability_summary.csv（主终点汇总）
    # ==================================================================
    csv3 = RESULTS_DIR / "c1_brier_reliability_summary.csv"

    # 提取 OOD 和 ID 的配对值
    rel_before_ood = [r['reliability_toplabel_before_ood'] for r in brier_rows]
    rel_after_ood = [r['reliability_toplabel_after_ood'] for r in brier_rows]
    rel_before_id = [r['reliability_toplabel_before_id'] for r in brier_rows]
    rel_after_id = [r['reliability_toplabel_after_id'] for r in brier_rows]

    # 主终点统计（OOD）
    stats_rel_ood = cohen_d_paired(rel_before_ood, rel_after_ood, "decrease")
    stats_rel_id = cohen_d_paired(rel_before_id, rel_after_id, "decrease")

    # Resolution 变化（H1 诊断）
    res_before_ood = [r['resolution_toplabel_before_ood'] for r in brier_rows]
    res_after_ood = [r['resolution_toplabel_after_ood'] for r in brier_rows]
    stats_res_ood = cohen_d_paired(res_before_ood, res_after_ood, "decrease")

    # Uncertainty 变化（应≈0）
    unc_before_ood = [r['uncertainty_toplabel_before_ood'] for r in brier_rows]
    unc_after_ood = [r['uncertainty_toplabel_after_ood'] for r in brier_rows]
    stats_unc_ood = cohen_d_paired(unc_before_ood, unc_after_ood, "decrease")

    # per-class OvR Reliability（敏感性）
    relo_before_ood = [r['reliability_ovr_before_ood'] for r in brier_rows]
    relo_after_ood = [r['reliability_ovr_after_ood'] for r in brier_rows]
    stats_relo_ood = cohen_d_paired(relo_before_ood, relo_after_ood, "decrease")

    # H1 诊断比值
    mean_delta_rel = stats_rel_ood['mean_diff']
    mean_delta_res = stats_res_ood['mean_diff']
    h1_ratio = abs(mean_delta_res) / abs(mean_delta_rel) if abs(mean_delta_rel) > 1e-12 else float('nan')

    with open(csv3, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# E3 主终点汇总：Brier Reliability 改善"])
        w.writerow(["# 主终点 = Reliability_toplabel 改善 (TS 前 - TS 后, 正值=好)"])
        w.writerow(["# 统计: paired t-test + Cohen's d + 95% bootstrap CI (B=10000)"])
        w.writerow(["# n_checkpoints", n])
        w.writerow([])
        w.writerow(["metric", "split", "mean_before", "mean_after", "mean_diff",
                    "std_diff", "cohen_d", "cohen_d_ci_lo", "cohen_d_ci_hi",
                    "t_stat", "p_value", "n"])
        for name, s, split in [
            ("Reliability_toplabel (主终点)", stats_rel_ood, "OOD"),
            ("Reliability_toplabel (参考)", stats_rel_id, "ID"),
            ("Resolution_toplabel (H1诊断)", stats_res_ood, "OOD"),
            ("Uncertainty_toplabel (应≈0)", stats_unc_ood, "OOD"),
            ("Reliability_OvR (敏感性)", stats_relo_ood, "OOD"),
        ]:
            w.writerow([name, split,
                        f"{s['mean_before']:.6f}", f"{s['mean_after']:.6f}",
                        f"{s['mean_diff']:+.6f}", f"{s['std_diff']:.6f}",
                        f"{s['cohen_d']:+.4f}",
                        f"{s['cohen_d_ci_lo']:+.4f}", f"{s['cohen_d_ci_hi']:+.4f}",
                        f"{s['t_stat']:+.4f}", f"{s['p_value']:.6e}", s['n']])
        w.writerow([])
        w.writerow(["# H1 诊断: |ΔResolution| / |ΔReliability| (OOD)"])
        w.writerow(["h1_ratio", f"{h1_ratio:.4f}",
                    "# <0.1 → H1 近似成立; >0.3 → H1 可能不成立"])
        w.writerow(["mean_delta_reliability", f"{mean_delta_rel:+.6f}"])
        w.writerow(["mean_delta_resolution", f"{mean_delta_res:+.6f}"])
    print(f"写入 {csv3}")

    # ==================================================================
    # CSV 4: c1_dcr_ncv_summary.csv（次要终点汇总 + BH FDR）
    # ==================================================================
    csv4 = RESULTS_DIR / "c1_dcr_ncv_summary.csv"

    # DCR（OOD 主分析）
    dcr_ood = [r['dcr_ood'] for r in dcr_ncv_rows]
    dcr_id = [r['dcr_id'] for r in dcr_ncv_rows]
    # DCR 已是 (cost_raw - cost_cal)，正值=改善。用 "increase" 方向。
    stats_dcr_ood = cohen_d_paired(np.zeros(n), dcr_ood, "increase")
    stats_dcr_id = cohen_d_paired(np.zeros(n), dcr_id, "increase")

    # NCV（OOD 主分析）
    ncv_ood = [r['ncv_ood'] for r in dcr_ncv_rows]
    ncv_id = [r['ncv_id'] for r in dcr_ncv_rows]
    stats_ncv_ood = cohen_d_paired(np.zeros(n), ncv_ood, "increase")
    stats_ncv_id = cohen_d_paired(np.zeros(n), ncv_id, "increase")

    # ECE 变化（探索性）
    ece_before_ood = [r['ece_before_ood'] for r in dcr_ncv_rows]
    ece_after_ood = [r['ece_after_ood'] for r in dcr_ncv_rows]
    stats_ece_ood = cohen_d_paired(ece_before_ood, ece_after_ood, "decrease")

    # BH FDR 校正（2 个次要终点：DCR, NCV）
    p_values = [stats_dcr_ood['p_value'], stats_ncv_ood['p_value']]
    reject, adj_p = bh_fdr(p_values, q=FDR_Q)

    with open(csv4, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# E3 次要终点汇总：DCR + NCV + 探索性 ECE"])
        w.writerow(["# DCR: Decision Cost Reduction (τ=0.5, abstain_cost=0.5)"])
        w.writerow(["# NCV: Net Clinical Value (对称, N_total=N×K)"])
        w.writerow(["# BH FDR 校正: q=0.05, 2 个次要终点 (DCR, NCV)"])
        w.writerow(["# n_checkpoints", n])
        w.writerow([])
        w.writerow(["metric", "split", "mean", "std", "cohen_d",
                    "cohen_d_ci_lo", "cohen_d_ci_hi", "t_stat", "p_value",
                    "p_adj_bh", "reject_h0", "n"])
        for name, s, split, p_adj, rej in [
            ("DCR (次要终点1)", stats_dcr_ood, "OOD", adj_p[0], reject[0]),
            ("DCR (参考)", stats_dcr_id, "ID", "", ""),
            ("NCV (次要终点2)", stats_ncv_ood, "OOD", adj_p[1], reject[1]),
            ("NCV (参考)", stats_ncv_id, "ID", "", ""),
            ("ΔECE (探索性)", stats_ece_ood, "OOD", "", ""),
        ]:
            w.writerow([name, split,
                        f"{s['mean_diff']:+.6f}", f"{s['std_diff']:.6f}",
                        f"{s['cohen_d']:+.4f}",
                        f"{s['cohen_d_ci_lo']:+.4f}", f"{s['cohen_d_ci_hi']:+.4f}",
                        f"{s['t_stat']:+.4f}", f"{s['p_value']:.6e}",
                        f"{p_adj:.6e}" if p_adj != "" else "",
                        str(rej) if rej != "" else "", s['n']])
        w.writerow([])
        w.writerow(["# BH FDR 校正详情"])
        w.writerow(["# 原始 p 值: DCR={:.6e}, NCV={:.6e}".format(p_values[0], p_values[1])])
        w.writerow(["# 调整 p 值: DCR={:.6e}, NCV={:.6e}".format(adj_p[0], adj_p[1])])
        w.writerow(["# 拒绝 H0:   DCR={}, NCV={}".format(reject[0], reject[1])])
        w.writerow(["# FDR 阈值:   q={}".format(FDR_Q)])
    print(f"写入 {csv4}")

    # ==================================================================
    # 控制台汇总
    # ==================================================================
    print("\n" + "=" * 80)
    print("E3 实验汇总")
    print("=" * 80)
    print(f"\n【主终点】Brier Reliability 改善 (OOD, n={n})")
    print(f"  ΔReliability = {stats_rel_ood['mean_diff']:+.6f} ± {stats_rel_ood['std_diff']:.6f}")
    print(f"  Cohen's d = {stats_rel_ood['cohen_d']:+.4f} "
          f"[{stats_rel_ood['cohen_d_ci_lo']:+.4f}, {stats_rel_ood['cohen_d_ci_hi']:+.4f}]")
    print(f"  paired t = {stats_rel_ood['t_stat']:+.4f}, p = {stats_rel_ood['p_value']:.6e}")

    print(f"\n【H1 诊断】|ΔResolution|/|ΔReliability| = {h1_ratio:.4f}")
    if h1_ratio < 0.1:
        print(f"  → H1 近似成立（Resolution 变化 << Reliability 变化）")
    elif h1_ratio < 0.3:
        print(f"  → H1 部分成立（Resolution 有轻微变化）")
    else:
        print(f"  → H1 可能不成立（Resolution 变化显著，建议增加 bin 数）")

    print(f"\n【次要终点1】DCR (OOD, τ=0.5)")
    print(f"  DCR = {stats_dcr_ood['mean_diff']:+.6f}, p = {stats_dcr_ood['p_value']:.6e}, "
          f"p_adj = {adj_p[0]:.6e}, reject = {reject[0]}")

    print(f"\n【次要终点2】NCV (OOD, N_total=N×K)")
    print(f"  NCV = {stats_ncv_ood['mean_diff']:+.6f}, p = {stats_ncv_ood['p_value']:.6e}, "
          f"p_adj = {adj_p[1]:.6e}, reject = {reject[1]}")

    print(f"\n【探索性】ΔECE (OOD)")
    print(f"  ΔECE = {stats_ece_ood['mean_diff']:+.6f}, p = {stats_ece_ood['p_value']:.6e}")


# ===========================================================================
# 第五部分：入口
# ===========================================================================

def main():
    ap = argparse.ArgumentParser(
        description="E3 核心实验: Brier Reliability + DCR + NCV + ECE 变化")
    ap.add_argument("--regen", action="store_true",
                    help="重新前向传播生成概率（否则用缓存）")
    ap.add_argument("--limit", type=int, default=None,
                    help="冒烟测试截断样本数")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--num-workers", type=int, default=0,
                    help="DataLoader 多线程")
    args = ap.parse_args()

    print("=" * 80)
    print("E3 核心实验：Brier Reliability + DCR + NCV + ECE 变化")
    print("=" * 80)
    print(f"Checkpoints: {len(PAIRS)} pairs × {len(ARCHS)} archs × {len(SEEDS)} seeds "
          f"= {len(PAIRS) * len(ARCHS) * len(SEEDS)}")
    print(f"主终点: Brier Reliability 改善 (Cohen's d + 95% CI + paired t-test)")
    print(f"次要终点1: DCR (τ={TAU})")
    print(f"次要终点2: NCV (对称, N_total=N×K)")
    print(f"探索性: ECE 变化")
    print(f"多重比较: BH FDR (q={FDR_Q}, 2 个次要终点)")
    print(f"缓存: {'重新生成' if args.regen else '优先使用'}")
    print()

    brier_rows, dcr_ncv_rows = run_experiment(args)
    summarize_and_write(brier_rows, dcr_ncv_rows)

    print("\nE3 实验完成。")


if __name__ == "__main__":
    main()
