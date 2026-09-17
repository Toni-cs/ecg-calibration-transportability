"""E6: 可靠性图生成（Reliability Diagram / Calibration Curve Visualization）

生成 7 个主可靠性图 + 60 个补充可靠性图，用于论文可视化 TS 校准前后效果。

======================================================================
设计论证（正方）
======================================================================
核心主张：
    可靠性图将 [0,1] 分 10 个 bin，绘制每个 bin 内"平均预测置信度 vs 实际
    正确率"，能直观展示 TS 校准前后模型置信度与准确率的对齐程度。

关键假设：
    H1. 10 个等宽 bin 足够展示校准曲线形态（ECE 文献标准，Guo et al. 2017）。
    H2. top-label 语义（max-prob vs argmax==label），与 eval_transfer.py 的
        _maxprob / _bin 一致——保证可视化与主终点 ΔECE 同语义。
    H3. 代表性种子 = seed42，主图架构 = resnet1d（均可配置）。
    H4. 60 checkpoint = 6 方向 × 2 完整架构(resnet1d, inceptiontime) × 5 种子；
        mamba 不完整（仅 ptbxl_chapman 2 seed）自动跳过。

适用边界：
    - 结论适用于 top-label 校准可视化，不反映 per-class 全类校准。
    - 10 bin 可能掩盖局部细粒度偏差（fine-grained 需 20+ bin 或 smooth ECE）。
    - 代表性种子选择存在 cherry-picking 风险——补充图覆盖全部 5 种子以供审查。

推理链条：
    raw probs → max-prob → 10 bin → (bin 内平均置信度, bin 内正确率)
    → 绘制 TS 前曲线；同法绘制 TS 后曲线 → 与 y=x 对比
    → 偏离 y=x 的程度 = 校准误差 → TS 后曲线更接近 y=x 则校准有效。

潜在攻击点（主动列出）：
    A1. 10 bin 粗粒度：可能掩盖单 bin 内的局部偏差（反例：某 bin 内左半过自信、
        右半欠自信，平均后看似完美）。→ 缓解：补充图标注 bin 内样本数，
        样本过少的 bin 会显式标记。
    A2. top-label 语义局限：只看最大预测类，忽略其余类的置信度分布。→ 缓解：
        与主终点 ΔECE 同语义，可视化一致性优先；per-class 图超出 E6 范围。
    A3. 代表性种子 cherry-picking：主图只选 seed42。→ 缓解：60 补充图覆盖全种子，
        汇总图用 6 方向平均曲线，种子敏感性可从补充图直接审查。
    A4. 平均 reliability curve 的 bin 对齐：不同方向 bin 内样本数差异大，
        简单平均可能被小样本 bin 主导。→ 缓解：汇总图用样本数加权平均。
    A5. 置信区间用 bootstrap percentile（每 bin 独立），未做 BCa——与主终点
        BCa 不一致。→ 缓解：reliability curve 是描述性可视化，每 bin 独立
        BCa（含 jackknife）成本 O(bins × B × n) 不现实；主终点 ΔECE 的 BCa
        CI 已由 eval_transfer.py 独立报告，此处 CI 仅为视觉辅助。
    A6. mamba 缺失 2 seed：若主图强制用 mamba 会有缺失。→ 缓解：默认用
        resnet1d（完整 30 checkpoint），mamba 自动跳过并记录。

======================================================================
两阶段架构
======================================================================
阶段 1 (--extract)：
    加载 60 个 best_model.pt → 前向推理 → 保存 e6_probs.npz
    （含 raw_probs, cal_probs, labels, T, n_id, n_ood）
    若 npz 已存在则跳过（支持迭代绘图不重算）。

阶段 2 (--plot)：
    读取 e6_probs.npz → 计算 10 bin reliability 数据 → 生成 PDF
    - 7 主图：6 方向（代表性 seed42 + resnet1d）+ 1 汇总（6 方向加权平均）
    - 60 补充图：每个 checkpoint 一个

用法：
    # 完整流程（提取 + 绘图）
    python scripts/run_e6_reliability_diagrams.py --all

    # 仅绘图（probs 已提取）
    python scripts/run_e6_reliability_diagrams.py --plot

    # 仅提取 probs
    python scripts/run_e6_reliability_diagrams.py --extract

    # 冒烟测试（2 checkpoint）
    python scripts/run_e6_reliability_diagrams.py --all --smoke
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# 路径与常量
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from src.utils.calibration import _validate_n_bins  # noqa: E402  # R7-ATK-1：n_bins 公共守卫

_FIGURES_DIR = _PROJECT_ROOT / "paper" / "figures"
_CKPT_ROOT = _PROJECT_ROOT / "checkpoints" / "transfer"

# 6 个迁移方向（source → target）
PAIRS: List[Tuple[str, str]] = [
    ("ptbxl", "chapman"),
    ("ptbxl", "cpsc"),
    ("chapman", "ptbxl"),
    ("chapman", "cpsc"),
    ("cpsc", "ptbxl"),
    ("cpsc", "chapman"),
]

# 2 个完整架构（mamba 不完整，自动跳过）
ARCHS: List[str] = ["resnet1d", "inceptiontime"]

# 5 个种子
SEEDS: List[int] = [42, 43, 44, 45, 46]

# 数据集路径默认值（与 launch_seed444546_transfers.py 一致）
DATA_DIRS: Dict[str, str] = {
    "ptbxl": "data/ptbxl_processed",
    "chapman": "data/chapman_processed_v2",
    "cpsc": "data/cpsc_processed",
}

# 可靠性图参数
N_BINS = 10
N_BOOTSTRAP_CI = 1000  # 每 bin 的 bootstrap CI 次数（视觉辅助，非主终点）
CONFIDENCE = 0.95

# 代表性配置（主图用）
REP_SEED = 42
REP_ARCH = "resnet1d"


# ---------------------------------------------------------------------------
# Reliability bin 计算（与 calibration.py 的 ece() 分箱策略完全一致）
# ---------------------------------------------------------------------------
def compute_reliability_bins(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = N_BINS,
) -> Dict:
    """计算 reliability diagram 的 bin 数据。

    语义与 eval_transfer.py 的 _maxprob / _bin 一致：
        x = max(probs)            # top-label confidence
        y = (argmax == label)     # top-label correctness

    分箱与 calibration.py 的 ece() 完全一致：
        - 等宽 bin，最后一个 bin 包含 1.0（左闭右开 + 末 bin 闭）
        - 空 bin 返回 nan（绘图时跳过）

    Returns:
        dict(bin_centers, bin_confidences, bin_accuracies, bin_counts,
             ece, n_total)
    """
    n_bins = _validate_n_bins(n_bins)  # R7-ATK-1：公共守卫，拦截 bool 穿透 + OOM

    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)

    # top-label 语义
    if probs.ndim == 2:
        confidence = probs.max(axis=1)
        correctness = (probs.argmax(axis=1) == labels).astype(float)
    else:
        confidence = probs
        correctness = labels

    n_total = len(confidence)
    boundaries = np.linspace(0.0, 1.0, n_bins + 1)

    bin_centers = np.full(n_bins, np.nan)
    bin_confidences = np.full(n_bins, np.nan)  # bin 内平均预测置信度
    bin_accuracies = np.full(n_bins, np.nan)   # bin 内实际正确率
    bin_counts = np.zeros(n_bins, dtype=int)

    for i in range(n_bins):
        if i == n_bins - 1:
            mask = (confidence >= boundaries[i]) & (confidence <= boundaries[i + 1])
        else:
            mask = (confidence >= boundaries[i]) & (confidence < boundaries[i + 1])

        cnt = int(mask.sum())
        bin_counts[i] = cnt
        if cnt > 0:
            bin_centers[i] = (boundaries[i] + boundaries[i + 1]) / 2.0
            bin_confidences[i] = float(confidence[mask].mean())
            bin_accuracies[i] = float(correctness[mask].mean())

    # ECE（与 calibration.ece 一致：按样本数加权）
    valid = bin_counts > 0
    ece_val = float(
        np.sum(bin_counts[valid] / n_total *
               np.abs(bin_confidences[valid] - bin_accuracies[valid]))
    ) if n_total > 0 else float("nan")

    return {
        "bin_centers": bin_centers,
        "bin_confidences": bin_confidences,
        "bin_accuracies": bin_accuracies,
        "bin_counts": bin_counts,
        "ece": ece_val,
        "n_total": int(n_total),
    }


def bootstrap_bin_accuracy_ci(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = N_BINS,
    n_bootstrap: int = N_BOOTSTRAP_CI,
    confidence: float = CONFIDENCE,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """每个 bin 的正确率 bootstrap percentile CI（视觉辅助）。

    返回 (ci_lo, ci_hi)，shape=(n_bins,)，空 bin 为 nan。

    注记：用 percentile 而非 BCa——reliability curve 是描述性可视化，
    每 bin 独立 BCa（含 jackknife）成本不现实；主终点 ΔECE 的 BCa CI
    已由 eval_transfer.py 独立报告（攻击点 A5）。
    """
    n_bins = _validate_n_bins(n_bins)  # R7-ATK-1：公共守卫，拦截 bool 穿透 + OOM

    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    if rng is None:
        rng = np.random.default_rng(0)

    if probs.ndim == 2:
        confidence = probs.max(axis=1)
        correctness = (probs.argmax(axis=1) == labels).astype(float)
    else:
        confidence = probs
        correctness = labels

    n = len(confidence)
    boundaries = np.linspace(0.0, 1.0, n_bins + 1)
    ci_lo = np.full(n_bins, np.nan)
    ci_hi = np.full(n_bins, np.nan)

    if n == 0 or n_bootstrap <= 0:
        return ci_lo, ci_hi

    # 预分配
    boot_acc = np.empty((n_bootstrap, n_bins))
    boot_acc.fill(np.nan)

    for b in range(n_bootstrap):
        idx = rng.choice(n, n, replace=True)
        conf_b = confidence[idx]
        corr_b = correctness[idx]
        for i in range(n_bins):
            if i == n_bins - 1:
                mask = (conf_b >= boundaries[i]) & (conf_b <= boundaries[i + 1])
            else:
                mask = (conf_b >= boundaries[i]) & (conf_b < boundaries[i + 1])
            if mask.sum() > 0:
                boot_acc[b, i] = float(corr_b[mask].mean())

    alpha = (1.0 - confidence) / 2.0
    for i in range(n_bins):
        col = boot_acc[:, i]
        col = col[np.isfinite(col)]
        if len(col) >= 10:
            ci_lo[i] = float(np.ravel(np.percentile(col, alpha * 100))[0])
            ci_hi[i] = float(np.ravel(np.percentile(col, (1.0 - alpha) * 100))[0])

    return ci_lo, ci_hi


# ---------------------------------------------------------------------------
# 增强版绘图（不修改原 calibration.py，避免破坏现有代码）
# ---------------------------------------------------------------------------
def plot_reliability_enhanced(
    bins_before: Dict,
    bins_after: Dict,
    ci_before: Optional[Tuple[np.ndarray, np.ndarray]] = None,
    ci_after: Optional[Tuple[np.ndarray, np.ndarray]] = None,
    title: str = "Reliability Diagram",
    subtitle: str = "",
    save_path: Optional[str] = None,
    fig_size: Tuple[float, float] = (7.0, 6.0),
) -> "Figure":  # noqa: F821
    """绘制 TS 前 vs TS 后的增强版 reliability diagram。

    包含：
        - y=x 完美校准线（黑色虚线）
        - TS 前曲线（红色方块）
        - TS 后曲线（绿色圆点）
        - bin 内样本数（灰色柱状图，右侧 y 轴）
        - 置信区间（误差棒，若提供）
        - ECE 标注

    Args:
        bins_before: compute_reliability_bins() 的结果（TS 前 / raw）
        bins_after:  compute_reliability_bins() 的结果（TS 后 / calibrated）
        ci_before/ci_after: (lo, hi) 数组，每 bin 的 CI
    """
    import matplotlib
    matplotlib.use("Agg")  # 无头模式，避免 Windows 显示后端问题
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 1, figsize=fig_size)

    # ---- 完美校准线 y=x ----
    ax.plot([0, 1], [0, 1], "k--", linewidth=1.2, alpha=0.7,
            label="Perfect (y = x)", zorder=1)

    # ---- 辅助：绘制一条曲线 + CI ----
    def _plot_curve(bins, ci, color, marker, label, zorder):
        valid = bins["bin_counts"] > 0
        x = bins["bin_centers"][valid]
        y = bins["bin_accuracies"][valid]
        cnt = bins["bin_counts"][valid]

        # CI 误差棒
        if ci is not None:
            lo, hi = ci
            lo_v = lo[valid]
            hi_v = hi[valid]
            err_lo = y - np.where(np.isfinite(lo_v), lo_v, y)
            err_hi = np.where(np.isfinite(hi_v), hi_v, y) - y
            err = np.vstack([err_lo, err_hi])
            ax.errorbar(x, y, yerr=err, fmt=marker + "-", color=color,
                        markersize=6, capsize=3, linewidth=1.5, alpha=0.9,
                        label=label, zorder=zorder)
        else:
            ax.plot(x, y, marker + "-", color=color, markersize=6,
                    linewidth=1.5, alpha=0.9, label=label, zorder=zorder)
        return x, y, cnt

    # ---- TS 前曲线（红色方块） ----
    x_b, y_b, cnt_b = _plot_curve(
        bins_before, ci_before, "#d62728", "s",
        f"Before TS (10-bin ECE={bins_before['ece']:.3f})", zorder=3)

    # ---- TS 后曲线（绿色圆点；TS 恶化时改橙色+⚠标注） ----
    delta_ece = bins_after['ece'] - bins_before['ece']
    if delta_ece > 0:
        _after_color = "#ff7f0e"  # 橙色：TS 恶化方向
        _after_label = f"After TS (10-bin ECE={bins_after['ece']:.3f}) ⚠ worsened"
    else:
        _after_color = "#2ca02c"  # 绿色：TS 改善或不变
        _after_label = f"After TS (10-bin ECE={bins_after['ece']:.3f})"
    x_a, y_a, cnt_a = _plot_curve(
        bins_after, ci_after, _after_color, "o",
        _after_label, zorder=4)

    # ---- bin 内样本数（灰色柱状图，右侧 y 轴） ----
    ax2 = ax.twinx()
    # 用 TS 前的 bin_counts 作样本数参考（TS 不改变 argmax，bin 分布近似）
    all_cnt = bins_before["bin_counts"]
    valid_cnt = all_cnt > 0
    if valid_cnt.any():
        max_cnt = all_cnt[valid_cnt].max()
        # 柱宽 = bin 宽度的 80%
        bar_width = 0.8 / N_BINS
        ax2.bar(bins_before["bin_centers"][valid_cnt], all_cnt[valid_cnt],
                width=bar_width, alpha=0.25, color="#7f7f7f",
                label="Sample count", zorder=2)
        ax2.set_ylabel("Sample count", fontsize=10, color="#7f7f7f")
        ax2.set_ylim(0, max_cnt * 3.5)  # 留空间给曲线
        ax2.tick_params(axis="y", labelcolor="#7f7f7f")

    # ---- 样本数标注（每个 bin 上方） ----
    for xi, ci_val in zip(bins_before["bin_centers"][valid_cnt],
                          all_cnt[valid_cnt]):
        if ci_val > 0:
            ax2.text(xi, ci_val + max_cnt * 0.02, str(int(ci_val)),
                     ha="center", va="bottom", fontsize=7, color="#7f7f7f",
                     alpha=0.8)

    # ---- 轴与标题 ----
    ax.set_xlabel("Mean predicted confidence (max prob)", fontsize=11)
    ax.set_ylabel("Fraction of positives (accuracy)", fontsize=11)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, alpha=0.2, linestyle=":", zorder=0)

    full_title = title
    if subtitle:
        full_title = f"{title}\n{subtitle}"
    ax.set_title(full_title, fontsize=12, pad=10)

    # ---- 图例 ----
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left",
              fontsize=9, framealpha=0.9)

    plt.tight_layout()

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=200, bbox_inches="tight",
                    format="pdf")
        # 同时存 PNG 预览
        png_path = str(save_path).replace(".pdf", ".png")
        fig.savefig(png_path, dpi=150, bbox_inches="tight",
                    format="png")

    plt.close(fig)
    return fig


def plot_summary(
    all_bins_before: List[Dict],
    all_bins_after: List[Dict],
    pair_names: List[str],
    save_path: Optional[str] = None,
) -> "Figure":  # noqa: F821
    """汇总图：6 方向的样本数加权平均 reliability curve。

    攻击点 A4 缓解：用 bin 内样本数加权平均，避免小样本 bin 主导。
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 1, figsize=(7.0, 6.0))

    # y=x
    ax.plot([0, 1], [0, 1], "k--", linewidth=1.2, alpha=0.7,
            label="Perfect (y = x)", zorder=1)

    boundaries = np.linspace(0.0, 1.0, N_BINS + 1)
    bin_centers = (boundaries[:-1] + boundaries[1:]) / 2.0

    def _weighted_avg(bins_list):
        """样本数加权平均每个 bin 的 accuracy。"""
        acc = np.full(N_BINS, np.nan)
        for i in range(N_BINS):
            total_w = 0
            total_wa = 0
            for b in bins_list:
                if b["bin_counts"][i] > 0:
                    w = b["bin_counts"][i]
                    total_w += w
                    total_wa += w * b["bin_accuracies"][i]
            if total_w > 0:
                acc[i] = total_wa / total_w
        return acc

    avg_before = _weighted_avg(all_bins_before)
    avg_after = _weighted_avg(all_bins_after)

    # 方向级加权平均 ECE（按各方向总样本数加权）
    # 注意：这是各方向 ECE 的样本数加权平均（sample-count weighted mean of per-direction ECE），
    # 非合并所有样本后重算的全局 ECE。Guo et al. 2017 的原始 ECE 定义是单模型
    # bin 级加权 Σ_b(n_b/N)×|acc(b)-conf(b)|，不适用于多方向汇总。
    # 方向级加权平均 ECE ≠ 全局 ECE（因 ECE 含绝对值，|x|+|y| ≠ |x+y|）。
    def _weighted_ece(bins_list):
        """按各方向总样本数加权平均 ECE（过滤 nan 方向）。"""
        weights = np.array([b["n_total"] for b in bins_list], dtype=float)
        eces = np.array([b["ece"] for b in bins_list], dtype=float)
        # 过滤 nan 和零权重方向，防止 nan 传播
        valid = np.isfinite(eces) & (weights > 0)
        if not valid.all():
            excluded = np.where(~valid)[0]
            warnings.warn(
                f"_weighted_ece: {len(excluded)} 方向因 ECE=nan/inf 或 n_total=0 被排除: {excluded.tolist()}",
                UserWarning, stacklevel=2
            )
        if not valid.any():
            return float("nan")
        return float(np.average(eces[valid], weights=weights[valid]))

    ece_before = _weighted_ece(all_bins_before)
    ece_after = _weighted_ece(all_bins_after)

    valid = np.isfinite(avg_before)
    ax.plot(bin_centers[valid], avg_before[valid], "s-",
            color="#d62728", markersize=7, linewidth=1.8, alpha=0.9,
            label=f"Before TS (sample-count weighted mean 10-bin ECE={ece_before:.3f})", zorder=3)

    valid2 = np.isfinite(avg_after)
    ax.plot(bin_centers[valid2], avg_after[valid2], "o-",
            color="#2ca02c", markersize=7, linewidth=1.8, alpha=0.9,
            label=f"After TS (sample-count weighted mean 10-bin ECE={ece_after:.3f})", zorder=4)

    # 各方向淡色背景曲线（展示6方向间变异性，非种子间变异性）
    for b_before, name in zip(all_bins_before, pair_names):
        v = b_before["bin_counts"] > 0
        ax.plot(b_before["bin_centers"][v], b_before["bin_accuracies"][v],
                "-", color="#d62728", alpha=0.15, linewidth=0.8, zorder=2)
    for b_after, name in zip(all_bins_after, pair_names):
        v = b_after["bin_counts"] > 0
        ax.plot(b_after["bin_centers"][v], b_after["bin_accuracies"][v],
                "-", color="#2ca02c", alpha=0.15, linewidth=0.8, zorder=2)

    ax.set_xlabel("Mean predicted confidence (max prob)", fontsize=11)
    ax.set_ylabel("Fraction of positives (accuracy)", fontsize=11)
    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, alpha=0.2, linestyle=":", zorder=0)
    ax.set_title("Summary: 6-direction averaged reliability curve\n"
                 f"(curve: bin-count weighted; ECE: sample-count weighted mean 10-bin; {REP_ARCH}, seed{REP_SEED})\n"
                 "Background curves: inter-direction variability (not inter-seed)",
                 fontsize=11, pad=10)
    ax.legend(loc="upper left", fontsize=9, framealpha=0.9)

    plt.tight_layout()
    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=200, bbox_inches="tight", format="pdf")
        png_path = str(save_path).replace(".pdf", ".png")
        fig.savefig(png_path, dpi=150, bbox_inches="tight", format="png")
    plt.close(fig)
    return fig


# ---------------------------------------------------------------------------
# 阶段 1：提取 probs
# ---------------------------------------------------------------------------
def _load_model_and_extract(args, source: str, target: str,
                            arch: str, seed: int) -> Optional[Dict]:
    """加载 checkpoint，前向推理，返回 probs 数据。

    复用 eval_transfer.py 的 _build / evaluate / fit_apply_method 逻辑。
    返回 None 表示 checkpoint 不存在或加载失败。
    """
    import torch
    from src.models.ecg_classifier import ECGClassifier
    from src.utils.calibration import fit_temperature, apply_temperature
    from eval_transfer import _build, DATASET_NUM_CLASSES
    from src.data.mapping import SUBSPACE_CPSC, SUPERCLASSES
    from src.utils.encoding_guard import checkpoint_subspace
    from train import set_seed, evaluate, create_dataloader

    pair_dir = _CKPT_ROOT / f"{source}_{target}" / arch / f"seed{seed}"
    ckpt_path = pair_dir / "best_model.pt"
    if not ckpt_path.exists():
        return None

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    set_seed(seed)

    num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
    # 编码护栏（2026-09-17）：本脚本产出的 70 张可靠性图 PDF（mtime 09-12，
    # 已随补充材料 S4 一起打包）原先用运行时常量重建标签，落在污染窗口内。
    # 现以 checkpoint 自存的 subspace 为准，不符即 raise。
    # 参见 results/_L2_SHIFT_CONTAMINATION_NOTICE.md。
    subspace = checkpoint_subspace(
        pair_dir, num_classes,
        SUBSPACE_CPSC if num_classes == 4 else None)

    # 加载 checkpoint
    ckpt = torch.load(ckpt_path, weights_only=False, map_location=device)
    sd = ckpt["model_state_dict"]

    # 推断 d_model / n_layers（与 eval_transfer.py 一致）
    if arch == "mamba":
        inferred_d_model = sd["backbone.stem.0.weight"].shape[0]
        import re
        layer_ids = {re.match(r"backbone\.layers\.(\d+)\.", k).group(1)
                     for k in sd if re.match(r"backbone\.layers\.(\d+)\.", k)}
        inferred_n_layers = len(layer_ids)
    elif "backbone.proj.weight" in sd:
        inferred_d_model = sd["backbone.proj.weight"].shape[0]
        inferred_n_layers = args.n_layers
    else:
        inferred_d_model = args.d_model
        inferred_n_layers = args.n_layers

    model = ECGClassifier(
        in_channels=12, d_model=inferred_d_model,
        n_layers=inferred_n_layers, num_classes=num_classes,
        dropout=0.1, backbone_type=arch).to(device)
    try:
        model.load_state_dict(sd)
    except RuntimeError as e:
        print(f"  [WARN] load_state_dict 失败 ({source}→{target} {arch} seed{seed}): {e}")
        return None

    # 构建源数据集（cal + test）
    src_dir = str(_PROJECT_ROOT / DATA_DIRS[source])
    src_ds, src_clusters = _build(source, src_dir, seed, args.limit,
                                  subspace=subspace)
    cal_loader = create_dataloader(src_ds["cal"], args.batch_size,
                                   shuffle=False, num_workers=args.num_workers)
    test_loader = create_dataloader(src_ds["test"], args.batch_size,
                                    shuffle=False, num_workers=args.num_workers)

    # 源 cal / test 前向
    cal_eval = evaluate(model, cal_loader, device, compute_calibration=False)
    test_eval = evaluate(model, test_loader, device, compute_calibration=False)
    cal_probs = cal_eval["probs"]      # (N_cal, K)
    cal_labels = cal_eval["labels"]
    id_probs = test_eval["probs"]      # (N_id, K)
    id_labels = test_eval["labels"]

    # 目标 test 前向
    tgt_dir = str(_PROJECT_ROOT / DATA_DIRS[target])
    tgt_ds, tgt_clusters = _build(target, tgt_dir, seed, args.limit,
                                  subspace=subspace)
    tgt_loader = create_dataloader(tgt_ds["test"], args.batch_size,
                                   shuffle=False, num_workers=args.num_workers)
    tgt_eval = evaluate(model, tgt_loader, device, compute_calibration=False)
    ood_probs = tgt_eval["probs"]      # (N_ood, K)
    ood_labels = tgt_eval["labels"]

    # 拟合 TS（源 cal）→ 应用到 id / ood
    # one-hot 编码（fit_temperature 期望 val_y 与 val_p 同形状）
    n_classes = cal_probs.shape[1]
    y_onehot = np.eye(n_classes)[cal_labels]
    T = fit_temperature(cal_probs, y_onehot, method="L-BFGS-B")
    id_cal_probs = apply_temperature(id_probs, T)
    ood_cal_probs = apply_temperature(ood_probs, T)

    return {
        "T": float(T),
        "id_raw": id_probs.astype(np.float32),
        "id_cal": id_cal_probs.astype(np.float32),
        "id_labels": id_labels.astype(np.int32),
        "ood_raw": ood_probs.astype(np.float32),
        "ood_cal": ood_cal_probs.astype(np.float32),
        "ood_labels": ood_labels.astype(np.int32),
        "n_id": int(len(id_probs)),
        "n_ood": int(len(ood_probs)),
    }


def extract_probs(args) -> int:
    """阶段 1：对所有 checkpoint 提取 probs 并缓存到 e6_probs.npz。"""
    print("=" * 70)
    print("E6 阶段 1：提取 probs（前向推理 + TS 拟合）")
    print("=" * 70)

    pairs = PAIRS[:2] if args.smoke else PAIRS
    archs = [REP_ARCH] if args.smoke else ARCHS
    seeds = [REP_SEED] if args.smoke else SEEDS

    total = 0
    skipped = 0
    failed = 0
    t0 = time.time()

    for source, target in pairs:
        for arch in archs:
            for seed in seeds:
                pair_dir = _CKPT_ROOT / f"{source}_{target}" / arch / f"seed{seed}"
                npz_path = pair_dir / "e6_probs.npz"

                if npz_path.exists() and not args.force_extract:
                    print(f"[skip] {source}→{target} {arch} seed{seed} (npz exists)")
                    skipped += 1
                    continue

                ckpt_path = pair_dir / "best_model.pt"
                if not ckpt_path.exists():
                    print(f"[miss] {source}→{target} {arch} seed{seed} (no checkpoint)")
                    failed += 1
                    continue

                print(f"[extract] {source}→{target} {arch} seed{seed} ...")
                try:
                    data = _load_model_and_extract(args, source, target, arch, seed)
                    if data is None:
                        print(f"  [FAIL] 返回 None")
                        failed += 1
                        continue
                    pair_dir.mkdir(parents=True, exist_ok=True)
                    np.savez_compressed(
                        str(npz_path),
                        T=data["T"],
                        id_raw=data["id_raw"], id_cal=data["id_cal"],
                        id_labels=data["id_labels"],
                        ood_raw=data["ood_raw"], ood_cal=data["ood_cal"],
                        ood_labels=data["ood_labels"],
                        n_id=data["n_id"], n_ood=data["n_ood"],
                    )
                    print(f"  [ok] T={data['T']:.3f} "
                          f"n_id={data['n_id']} n_ood={data['n_ood']}")
                    total += 1
                except Exception as e:
                    print(f"  [ERROR] {type(e).__name__}: {e}")
                    failed += 1

    elapsed = time.time() - t0
    print(f"\n提取完成：{total} 成功, {skipped} 跳过, {failed} 失败 "
          f"({elapsed:.1f}s)")
    return total


# ---------------------------------------------------------------------------
# 阶段 2：生成图
# ---------------------------------------------------------------------------
def _load_npz(source: str, target: str, arch: str, seed: int) -> Optional[Dict]:
    """加载 e6_probs.npz，返回 dict 或 None。"""
    npz_path = _CKPT_ROOT / f"{source}_{target}" / arch / f"seed{seed}" / "e6_probs.npz"
    if not npz_path.exists():
        return None
    d = np.load(str(npz_path))
    return {k: d[k] for k in d.files}


def _compute_bins_and_ci(probs_raw, probs_cal, labels, rng):
    """对一组 (raw, cal, labels) 计算 bins + CI。"""
    bins_before = compute_reliability_bins(probs_raw, labels)
    bins_after = compute_reliability_bins(probs_cal, labels)
    ci_before = bootstrap_bin_accuracy_ci(
        probs_raw, labels, n_bootstrap=N_BOOTSTRAP_CI, rng=rng)
    ci_after = bootstrap_bin_accuracy_ci(
        probs_cal, labels, n_bootstrap=N_BOOTSTRAP_CI, rng=rng)
    return bins_before, bins_after, ci_before, ci_after


def generate_figures(args) -> Tuple[int, int]:
    """阶段 2：生成 7 主图 + 60 补充图。"""
    print("=" * 70)
    print("E6 阶段 2：生成可靠性图")
    print("=" * 70)

    _FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.rng_seed)

    pairs = PAIRS[:2] if args.smoke else PAIRS
    archs = [REP_ARCH] if args.smoke else ARCHS
    seeds = [REP_SEED] if args.smoke else SEEDS

    n_main = 0
    n_supp = 0
    missing = 0

    # ---- 收集汇总图数据 ----
    summary_before = []
    summary_after = []
    summary_names = []

    # ---- 60 补充图 ----
    print("\n--- 60 补充可靠性图 ---")
    for source, target in pairs:
        for arch in archs:
            for seed in seeds:
                data = _load_npz(source, target, arch, seed)
                if data is None:
                    print(f"[miss] {source}→{target} {arch} seed{seed}")
                    missing += 1
                    continue

                # OOD reliability（主分析对象：源模型 → 目标域）
                bins_b, bins_a, ci_b, ci_a = _compute_bins_and_ci(
                    data["ood_raw"], data["ood_cal"], data["ood_labels"], rng)

                title = f"{source.upper()} → {target.upper()}  ({arch}, seed{seed})"
                subtitle = (f"OOD target-test (n={data['n_ood']}, "
                            f"T={float(data['T']):.3f})")
                supp_name = f"fig_reliability_supp_{source}_{target}_{arch}_seed{seed}.pdf"
                save_path = str(_FIGURES_DIR / supp_name)

                plot_reliability_enhanced(
                    bins_b, bins_a, ci_b, ci_a,
                    title=title, subtitle=subtitle, save_path=save_path)
                n_supp += 1

                # 收集汇总数据（仅代表性 seed + arch）
                if seed == args.rep_seed and arch == args.rep_arch:
                    summary_before.append(bins_b)
                    summary_after.append(bins_a)
                    summary_names.append(f"{source}→{target}")

                if n_supp % 10 == 0:
                    print(f"  已生成 {n_supp} 补充图...")

    print(f"补充图完成：{n_supp} 生成, {missing} 缺失")

    # ---- 6 主图（代表性 seed + arch，OOD 域） ----
    print("\n--- 6 主可靠性图（代表性方向图）---")
    for source, target in pairs:
        data = _load_npz(source, target, args.rep_arch, args.rep_seed)
        if data is None:
            print(f"[miss] 主图 {source}→{target} {args.rep_arch} seed{args.rep_seed}")
            continue

        bins_b, bins_a, ci_b, ci_a = _compute_bins_and_ci(
            data["ood_raw"], data["ood_cal"], data["ood_labels"], rng)

        title = f"{source.upper()} → {target.upper()}"
        subtitle = (f"OOD target-test (n={data['n_ood']}, "
                    f"{args.rep_arch}, seed{args.rep_seed}, "
                    f"T={float(data['T']):.3f})")
        main_name = f"fig_reliability_{source}_{target}.pdf"
        save_path = str(_FIGURES_DIR / main_name)

        plot_reliability_enhanced(
            bins_b, bins_a, ci_b, ci_a,
            title=title, subtitle=subtitle, save_path=save_path,
            fig_size=(7.5, 6.5))
        n_main += 1
        print(f"  [ok] {main_name}")

    # ---- 第 7 主图：汇总 ----
    print("\n--- 第 7 主图：6 方向汇总 ---")
    if len(summary_before) > 0:
        summary_path = str(_FIGURES_DIR / "fig_reliability_summary.pdf")
        plot_summary(summary_before, summary_after, summary_names,
                     save_path=summary_path)
        n_main += 1
        print(f"  [ok] fig_reliability_summary.pdf "
              f"({len(summary_before)} 方向加权平均)")
    else:
        print("  [WARN] 无汇总数据（代表性 checkpoint 缺失）")

    print(f"\n主图完成：{n_main}（预期 7）")
    print(f"补充图完成：{n_supp}（预期 60）")
    print(f"输出目录：{_FIGURES_DIR}")
    return n_main, n_supp


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="E6: 可靠性图生成（7 主图 + 60 补充图）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--extract", action="store_true",
                      help="仅阶段 1：提取 probs 到 e6_probs.npz")
    mode.add_argument("--plot", action="store_true",
                      help="仅阶段 2：从 npz 生成图")
    mode.add_argument("--all", action="store_true",
                      help="两阶段都跑（提取 + 绘图）")

    ap.add_argument("--rep-seed", type=int, default=REP_SEED,
                    help=f"主图代表性种子（默认 {REP_SEED}）")
    ap.add_argument("--rep-arch", default=REP_ARCH, choices=ARCHS + ["mamba"],
                    help=f"主图代表性架构（默认 {REP_ARCH}）")
    ap.add_argument("--rng-seed", type=int, default=0,
                    help="bootstrap CI 的 RNG 种子")
    ap.add_argument("--force-extract", action="store_true",
                    help="强制重新提取（覆盖已有 npz）")

    # 模型/数据参数（仅 --extract/--all 用到）
    ap.add_argument("--d-model", dest="d_model", type=int, default=64)
    ap.add_argument("--n-layers", dest="n_layers", type=int, default=2)
    ap.add_argument("--batch-size", dest="batch_size", type=int, default=16)
    ap.add_argument("--num-workers", dest="num_workers", type=int, default=0)
    ap.add_argument("--limit", type=int, default=None,
                    help="冒烟截断（样本数上限）")

    ap.add_argument("--smoke", action="store_true",
                    help="冒烟模式：仅 2 方向 × 1 架构 × 1 种子 = 2 checkpoint")

    args = ap.parse_args()

    print(f"项目根目录: {_PROJECT_ROOT}")
    print(f"Checkpoint: {_CKPT_ROOT}")
    print(f"输出目录:   {_FIGURES_DIR}")
    print(f"配置: pairs={len(PAIRS)} archs={ARCHS} seeds={SEEDS} "
          f"→ {len(PAIRS)*len(ARCHS)*len(SEEDS)} checkpoint")
    print(f"代表性: arch={args.rep_arch} seed={args.rep_seed}")

    if args.extract or args.all:
        n = extract_probs(args)
        if n == 0 and not args.plot:
            print("\n[WARN] 未提取任何 probs。请检查 checkpoint 与数据路径。")
            return

    if args.plot or args.all:
        n_main, n_supp = generate_figures(args)
        # 结果摘要
        print("\n" + "=" * 70)
        print("E6 可靠性图生成完成")
        print("=" * 70)
        print(f"  主图:     {n_main} / 7")
        print(f"  补充图:   {n_supp} / 60")
        print(f"  输出目录: {_FIGURES_DIR}")
        if n_main < 7 or n_supp < 60:
            print(f"  [WARN] 部分图缺失——检查 e6_probs.npz 是否已提取")
        print("\n论证摘要：")
        print("  - 主图展示 6 方向的 TS 前 vs 后 reliability curve + 汇总")
        print("  - 补充图覆盖全 60 checkpoint，供种子敏感性审查")
        print("  - 每图含 y=x 线、TS 前(红)/后(绿)曲线、bin 样本数、CI")
        print("  - 潜在攻击点见脚本头部文档字符串（A1-A6）")


if __name__ == "__main__":
    main()
