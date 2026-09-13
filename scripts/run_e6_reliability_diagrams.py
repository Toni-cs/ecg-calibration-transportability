"""E6: reliability diagram generation (reliability curve / calibration visualization).

Generates 7 main reliability diagrams + 60 supplementary diagrams for visualizing
TS calibration before/after in the paper.

Rationale
---------
Reliability diagrams split [0,1] into 10 bins and plot, per bin, the average predicted
confidence vs the empirical accuracy, showing how well a model's confidence is calibrated
before vs after TS.

Key assumptions:
    H1. 10 equal-width bins suffice to show calibration-curve shape (ECE literature standard, Guo et al. 2017).
    H2. top-label semantics (max-prob vs argmax==label) match eval_transfer.py's _maxprob/_bin,
        so the visualization shares semantics with the primary endpoint ΔECE.
    H3. representative seed = seed42, main-figure architecture = resnet1d (both configurable).
    H4. 60 checkpoints = 6 directions x 2 complete architectures (resnet1d, inceptiontime) x 5 seeds;
        mamba is incomplete (only ptbxl_chapman, 2 seeds) and is auto-skipped.

Applicability bounds:
    - conclusions apply to top-label calibration visualization, not full per-class calibration.
    - 10 bins may hide fine-grained local bias (fine-grained needs 20+ bins or smooth ECE).
    - representative-seed selection carries cherry-picking risk; supplementary figures cover all
      5 seeds for audit.

Inference chain:
    raw probs -> max-prob -> 10 bins -> (bin-average confidence, bin accuracy)
    -> plot pre-TS curve; plot post-TS curve the same way -> compare against y=x
    -> deviation from y=x is calibration error; a post-TS curve closer to y=x means better calibration.

Caveats (sensitivity analyses)
------------------------------
- A1: 10-bin coarseness may hide in-bin local bias (e.g. a bin overconfident on its left half and
  underconfident on its right, averaging to look perfect). Mitigation: annotate per-bin sample counts;
  bins with too few samples are flagged.
- A2: top-label semantics only look at the max predicted class, ignoring the other classes'
  confidence distribution. Mitigation: shares semantics with primary endpoint ΔECE; per-class
  figures are out of E6 scope.
- A3: representative-seed cherry-picking (main figures use only seed42). Mitigation: 60 supplementary
  figures cover all seeds; the summary figure uses 6-direction averaged curves, so seed sensitivity
  is auditable from the supplementary set.
- A4: bin alignment in the averaged reliability curve -- directions differ greatly in per-bin sample
  counts, so a naive average could be dominated by small-sample bins. Mitigation: the summary figure
  uses sample-count-weighted averaging.
- A5: per-bin confidence intervals use bootstrap percentile (independent per bin), not BCa -- unlike
  the primary endpoint. Mitigation: the reliability curve is descriptive; per-bin independent BCa
  (with jackknife) costs O(bins x B x n) and is impractical. The primary endpoint ΔECE's BCa CI is
  reported separately by eval_transfer.py; here the CI is visual aid only.
- A6: mamba missing 2 seeds. Mitigation: default to resnet1d (complete 30 checkpoints); mamba is
  auto-skipped and recorded.

Two-stage architecture
----------------------
Stage 1 (--extract): load 60 best_model.pt -> forward pass -> save e6_probs.npz
    (contains raw_probs, cal_probs, labels, T, n_id, n_ood)
    Skips if npz already exists (supports iterative plotting without recompute).

Stage 2 (--plot): read e6_probs.npz -> compute 10-bin reliability data -> generate PDF
    - 7 main figures: 6 directions (representative seed42 + resnet1d) + 1 summary (6-direction weighted avg)
    - 60 supplementary figures: one per checkpoint

Usage:
    # Full pipeline (extract + plot)
    python scripts/run_e6_reliability_diagrams.py --all

    # Plot only (probs already extracted)
    python scripts/run_e6_reliability_diagrams.py --plot

    # Extract probs only
    python scripts/run_e6_reliability_diagrams.py --extract

    # Smoke test (2 checkpoints)
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
# Paths and constants
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from src.utils.calibration import _validate_n_bins  # noqa: E402  # shared n_bins guard

_FIGURES_DIR = _PROJECT_ROOT / "paper" / "figures"
_CKPT_ROOT = _PROJECT_ROOT / "checkpoints" / "transfer"

# 6 transfer directions (source -> target)
PAIRS: List[Tuple[str, str]] = [
    ("ptbxl", "chapman"),
    ("ptbxl", "cpsc"),
    ("chapman", "ptbxl"),
    ("chapman", "cpsc"),
    ("cpsc", "ptbxl"),
    ("cpsc", "chapman"),
]

# 2 complete architectures (mamba incomplete, auto-skipped)
ARCHS: List[str] = ["resnet1d", "inceptiontime"]

# 5 seeds
SEEDS: List[int] = [42, 43, 44, 45, 46]

# Default dataset paths (consistent with launch_seed444546_transfers.py)
DATA_DIRS: Dict[str, str] = {
    "ptbxl": "data/ptbxl_processed",
    "chapman": "data/chapman_processed_v2",
    "cpsc": "data/cpsc_processed",
}

# Reliability-diagram parameters
N_BINS = 10
N_BOOTSTRAP_CI = 1000  # bootstrap CI iterations per bin (visual aid, not primary endpoint)
CONFIDENCE = 0.95

# Representative config (for main figures)
REP_SEED = 42
REP_ARCH = "resnet1d"


# ---------------------------------------------------------------------------
# Reliability bin computation (binning strategy identical to calibration.py's ece())
# ---------------------------------------------------------------------------
def compute_reliability_bins(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = N_BINS,
) -> Dict:
    """Compute bin data for a reliability diagram.

    Semantics match eval_transfer.py's _maxprob / _bin:
        x = max(probs)            # top-label confidence
        y = (argmax == label)     # top-label correctness

    Binning matches calibration.py's ece() exactly:
        - equal-width bins, the last bin inclusive of 1.0 (left-closed right-open + last bin closed)
        - empty bins return nan (skipped when plotting)

    Returns:
        dict(bin_centers, bin_confidences, bin_accuracies, bin_counts,
             ece, n_total)
    """
    n_bins = _validate_n_bins(n_bins)  # shared guard: reject bool passthrough and avoid OOM

    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)

    # top-label semantics
    if probs.ndim == 2:
        confidence = probs.max(axis=1)
        correctness = (probs.argmax(axis=1) == labels).astype(float)
    else:
        confidence = probs
        correctness = labels

    n_total = len(confidence)
    boundaries = np.linspace(0.0, 1.0, n_bins + 1)

    bin_centers = np.full(n_bins, np.nan)
    bin_confidences = np.full(n_bins, np.nan)  # bin-average predicted confidence
    bin_accuracies = np.full(n_bins, np.nan)   # bin empirical accuracy
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

    # ECE (consistent with calibration.ece: sample-count weighted)
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
    """Per-bin accuracy bootstrap percentile CI (visual aid).

    Returns (ci_lo, ci_hi), shape=(n_bins,), empty bins are nan.

    Uses percentile instead of BCa; the reliability curve is descriptive and per-bin
    independent BCa (with jackknife) is impractical. The primary endpoint ΔECE's BCa CI
    is reported separately by eval_transfer.py (caveat A5).
    """
    n_bins = _validate_n_bins(n_bins)  # shared guard: reject bool passthrough and avoid OOM

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

    # Pre-allocate
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
# Enhanced plotting (does not modify the original calibration.py to avoid breaking existing code)
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
    """Draw an enhanced reliability diagram: TS-before vs TS-after.

    Includes:
        - perfect-calibration line y=x (black dashed)
        - TS-before curve (red squares)
        - TS-after curve (green dots; orange + [worsened] tag if TS increased ECE)
        - per-bin sample count (gray bars, right y-axis)
        - confidence intervals (error bars, if provided)
        - ECE annotation

    Args:
        bins_before: result of compute_reliability_bins() (pre-TS / raw)
        bins_after:  result of compute_reliability_bins() (post-TS / calibrated)
        ci_before/ci_after: (lo, hi) arrays, per-bin CI
    """
    import matplotlib
    matplotlib.use("Agg")  # headless mode, avoids Windows display-backend issues
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(1, 1, figsize=fig_size)

    # ---- perfect calibration line y=x ----
    ax.plot([0, 1], [0, 1], "k--", linewidth=1.2, alpha=0.7,
            label="Perfect (y = x)", zorder=1)

    # ---- helper: draw one curve + CI ----
    def _plot_curve(bins, ci, color, marker, label, zorder):
        valid = bins["bin_counts"] > 0
        x = bins["bin_centers"][valid]
        y = bins["bin_accuracies"][valid]
        cnt = bins["bin_counts"][valid]

        # CI error bars
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

    # ---- TS-before curve (red squares) ----
    x_b, y_b, cnt_b = _plot_curve(
        bins_before, ci_before, "#d62728", "s",
        f"Before TS (10-bin ECE={bins_before['ece']:.3f})", zorder=3)

    # ---- TS-after curve (green dots; orange + [worsened] tag if TS degraded) ----
    delta_ece = bins_after['ece'] - bins_before['ece']
    if delta_ece > 0:
        _after_color = "#ff7f0e"  # orange: TS degraded
        _after_label = f"After TS (10-bin ECE={bins_after['ece']:.3f}) [worsened]"
    else:
        _after_color = "#2ca02c"  # green: TS improved or unchanged
        _after_label = f"After TS (10-bin ECE={bins_after['ece']:.3f})"
    x_a, y_a, cnt_a = _plot_curve(
        bins_after, ci_after, _after_color, "o",
        _after_label, zorder=4)

    # ---- per-bin sample count (gray bars, right y-axis) ----
    ax2 = ax.twinx()
    # Use TS-before bin_counts as the sample-count reference (TS does not change argmax, bin distribution is similar)
    all_cnt = bins_before["bin_counts"]
    valid_cnt = all_cnt > 0
    if valid_cnt.any():
        max_cnt = all_cnt[valid_cnt].max()
        # bar width = 80% of bin width
        bar_width = 0.8 / N_BINS
        ax2.bar(bins_before["bin_centers"][valid_cnt], all_cnt[valid_cnt],
                width=bar_width, alpha=0.25, color="#7f7f7f",
                label="Sample count", zorder=2)
        ax2.set_ylabel("Sample count", fontsize=10, color="#7f7f7f")
        ax2.set_ylim(0, max_cnt * 3.5)  # leave room for the curve
        ax2.tick_params(axis="y", labelcolor="#7f7f7f")

    # ---- sample-count labels (above each bin) ----
    for xi, ci_val in zip(bins_before["bin_centers"][valid_cnt],
                          all_cnt[valid_cnt]):
        if ci_val > 0:
            ax2.text(xi, ci_val + max_cnt * 0.02, str(int(ci_val)),
                     ha="center", va="bottom", fontsize=7, color="#7f7f7f",
                     alpha=0.8)

    # ---- axes and title ----
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

    # ---- legend ----
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc="upper left",
              fontsize=9, framealpha=0.9)

    plt.tight_layout()

    if save_path:
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_path, dpi=200, bbox_inches="tight",
                    format="pdf")
        # Also save a PNG preview
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
    """Summary figure: sample-count-weighted reliability curve averaged over 6 directions.

    Mitigates caveat A4: use per-bin sample-count weighting so small-sample bins do not dominate.
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
        """Sample-count-weighted average accuracy per bin."""
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

    # Direction-level weighted-average ECE (weighted by each direction's total sample count).
    # Note: this is the sample-count-weighted mean of per-direction ECE, NOT a global ECE
    # recomputed over all pooled samples. Guo et al. 2017's original ECE is a single-model
    # bin-level weighted sum Sigma_b(n_b/N)*|acc(b)-conf(b)|, which does not apply to a
    # multi-direction summary. Direction-level weighted mean ECE != global ECE because ECE
    # contains an absolute value (|x|+|y| != |x+y|).
    def _weighted_ece(bins_list):
        """Sample-count-weighted mean of per-direction ECE (drops nan directions)."""
        weights = np.array([b["n_total"] for b in bins_list], dtype=float)
        eces = np.array([b["ece"] for b in bins_list], dtype=float)
        # Drop nan / zero-weight directions to prevent nan propagation
        valid = np.isfinite(eces) & (weights > 0)
        if not valid.all():
            excluded = np.where(~valid)[0]
            warnings.warn(
                f"_weighted_ece: {len(excluded)} directions excluded (ECE=nan/inf or n_total=0): {excluded.tolist()}",
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

    # Faint background curves for each direction (shows inter-direction variability, not inter-seed)
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
# Stage 1: extract probs
# ---------------------------------------------------------------------------
def _load_model_and_extract(args, source: str, target: str,
                            arch: str, seed: int) -> Optional[Dict]:
    """Load a checkpoint, run forward pass, return probs data.

    Reuses eval_transfer.py's _build / evaluate / fit_apply_method logic.
    Returns None if the checkpoint is missing or fails to load.
    """
    import torch
    from src.models.ecg_classifier import ECGClassifier
    from src.utils.calibration import fit_temperature, apply_temperature
    from eval_transfer import _build, DATASET_NUM_CLASSES
    from src.data.mapping import SUBSPACE_CPSC, SUPERCLASSES
    from train import set_seed, evaluate, create_dataloader

    pair_dir = _CKPT_ROOT / f"{source}_{target}" / arch / f"seed{seed}"
    ckpt_path = pair_dir / "best_model.pt"
    if not ckpt_path.exists():
        return None

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    set_seed(seed)

    num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
    subspace = SUBSPACE_CPSC if num_classes == 4 else None

    # Load checkpoint
    ckpt = torch.load(ckpt_path, weights_only=False, map_location=device)
    sd = ckpt["model_state_dict"]

    # Infer d_model / n_layers (consistent with eval_transfer.py)
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
        print(f"  [WARN] load_state_dict failed ({source}->{target} {arch} seed{seed}): {e}")
        return None

    # Build source dataset (cal + test)
    src_dir = str(_PROJECT_ROOT / DATA_DIRS[source])
    src_ds, src_clusters = _build(source, src_dir, seed, args.limit,
                                  subspace=subspace)
    cal_loader = create_dataloader(src_ds["cal"], args.batch_size,
                                   shuffle=False, num_workers=args.num_workers)
    test_loader = create_dataloader(src_ds["test"], args.batch_size,
                                    shuffle=False, num_workers=args.num_workers)

    # Source cal / test forward
    cal_eval = evaluate(model, cal_loader, device, compute_calibration=False)
    test_eval = evaluate(model, test_loader, device, compute_calibration=False)
    cal_probs = cal_eval["probs"]      # (N_cal, K)
    cal_labels = cal_eval["labels"]
    id_probs = test_eval["probs"]      # (N_id, K)
    id_labels = test_eval["labels"]

    # Target test forward
    tgt_dir = str(_PROJECT_ROOT / DATA_DIRS[target])
    tgt_ds, tgt_clusters = _build(target, tgt_dir, seed, args.limit,
                                  subspace=subspace)
    tgt_loader = create_dataloader(tgt_ds["test"], args.batch_size,
                                   shuffle=False, num_workers=args.num_workers)
    tgt_eval = evaluate(model, tgt_loader, device, compute_calibration=False)
    ood_probs = tgt_eval["probs"]      # (N_ood, K)
    ood_labels = tgt_eval["labels"]

    # Fit TS (source cal) -> apply to id / ood
    # one-hot encoding (fit_temperature expects val_y shaped like val_p)
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
    """Stage 1: extract probs for all checkpoints and cache to e6_probs.npz."""
    print("=" * 70)
    print("E6 Stage 1: extract probs (forward pass + TS fit)")
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
                    print(f"[skip] {source}->{target} {arch} seed{seed} (npz exists)")
                    skipped += 1
                    continue

                ckpt_path = pair_dir / "best_model.pt"
                if not ckpt_path.exists():
                    print(f"[miss] {source}->{target} {arch} seed{seed} (no checkpoint)")
                    failed += 1
                    continue

                print(f"[extract] {source}->{target} {arch} seed{seed} ...")
                try:
                    data = _load_model_and_extract(args, source, target, arch, seed)
                    if data is None:
                        print(f"  [FAIL] returned None")
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
    print(f"\nExtraction done: {total} succeeded, {skipped} skipped, {failed} failed "
          f"({elapsed:.1f}s)")
    return total


# ---------------------------------------------------------------------------
# Stage 2: generate figures
# ---------------------------------------------------------------------------
def _load_npz(source: str, target: str, arch: str, seed: int) -> Optional[Dict]:
    """Load e6_probs.npz, return dict or None."""
    npz_path = _CKPT_ROOT / f"{source}_{target}" / arch / f"seed{seed}" / "e6_probs.npz"
    if not npz_path.exists():
        return None
    d = np.load(str(npz_path))
    return {k: d[k] for k in d.files}


def _compute_bins_and_ci(probs_raw, probs_cal, labels, rng):
    """Compute bins + CI for a set of (raw, cal, labels)."""
    bins_before = compute_reliability_bins(probs_raw, labels)
    bins_after = compute_reliability_bins(probs_cal, labels)
    ci_before = bootstrap_bin_accuracy_ci(
        probs_raw, labels, n_bootstrap=N_BOOTSTRAP_CI, rng=rng)
    ci_after = bootstrap_bin_accuracy_ci(
        probs_cal, labels, n_bootstrap=N_BOOTSTRAP_CI, rng=rng)
    return bins_before, bins_after, ci_before, ci_after


def generate_figures(args) -> Tuple[int, int]:
    """Stage 2: generate 7 main figures + 60 supplementary figures."""
    print("=" * 70)
    print("E6 Stage 2: generate reliability diagrams")
    print("=" * 70)

    _FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(args.rng_seed)

    pairs = PAIRS[:2] if args.smoke else PAIRS
    archs = [REP_ARCH] if args.smoke else ARCHS
    seeds = [REP_SEED] if args.smoke else SEEDS

    n_main = 0
    n_supp = 0
    missing = 0

    # ---- collect summary-figure data ----
    summary_before = []
    summary_after = []
    summary_names = []

    # ---- 60 supplementary figures ----
    print("\n--- 60 supplementary reliability diagrams ---")
    for source, target in pairs:
        for arch in archs:
            for seed in seeds:
                data = _load_npz(source, target, arch, seed)
                if data is None:
                    print(f"[miss] {source}->{target} {arch} seed{seed}")
                    missing += 1
                    continue

                # OOD reliability (primary object: source model -> target domain)
                bins_b, bins_a, ci_b, ci_a = _compute_bins_and_ci(
                    data["ood_raw"], data["ood_cal"], data["ood_labels"], rng)

                title = f"{source.upper()} -> {target.upper()}  ({arch}, seed{seed})"
                subtitle = (f"OOD target-test (n={data['n_ood']}, "
                            f"T={float(data['T']):.3f})")
                supp_name = f"fig_reliability_supp_{source}_{target}_{arch}_seed{seed}.pdf"
                save_path = str(_FIGURES_DIR / supp_name)

                plot_reliability_enhanced(
                    bins_b, bins_a, ci_b, ci_a,
                    title=title, subtitle=subtitle, save_path=save_path)
                n_supp += 1

                # Collect summary data (representative seed + arch only)
                if seed == args.rep_seed and arch == args.rep_arch:
                    summary_before.append(bins_b)
                    summary_after.append(bins_a)
                    summary_names.append(f"{source}->{target}")

                if n_supp % 10 == 0:
                    print(f"  generated {n_supp} supplementary figures...")

    print(f"Supplementary figures done: {n_supp} generated, {missing} missing")

    # ---- 6 main figures (representative seed + arch, OOD domain) ----
    print("\n--- 6 main reliability diagrams (representative direction figures) ---")
    for source, target in pairs:
        data = _load_npz(source, target, args.rep_arch, args.rep_seed)
        if data is None:
            print(f"[miss] main figure {source}->{target} {args.rep_arch} seed{args.rep_seed}")
            continue

        bins_b, bins_a, ci_b, ci_a = _compute_bins_and_ci(
            data["ood_raw"], data["ood_cal"], data["ood_labels"], rng)

        title = f"{source.upper()} -> {target.upper()}"
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

    # ---- Main figure 7: summary ----
    print("\n--- Main figure 7: 6-direction summary ---")
    if len(summary_before) > 0:
        summary_path = str(_FIGURES_DIR / "fig_reliability_summary.pdf")
        plot_summary(summary_before, summary_after, summary_names,
                     save_path=summary_path)
        n_main += 1
        print(f"  [ok] fig_reliability_summary.pdf "
              f"({len(summary_before)} directions weighted average)")
    else:
        print("  [WARN] no summary data (representative checkpoint missing)")

    print(f"\nMain figures done: {n_main} (expected 7)")
    print(f"Supplementary figures done: {n_supp} (expected 60)")
    print(f"Output directory: {_FIGURES_DIR}")
    return n_main, n_supp


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="E6: reliability diagram generation (7 main + 60 supplementary figures)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--extract", action="store_true",
                      help="only Stage 1: extract probs to e6_probs.npz")
    mode.add_argument("--plot", action="store_true",
                      help="only Stage 2: generate figures from npz")
    mode.add_argument("--all", action="store_true",
                      help="run both stages (extract + plot)")

    ap.add_argument("--rep-seed", type=int, default=REP_SEED,
                    help=f"representative seed for main figures (default {REP_SEED})")
    ap.add_argument("--rep-arch", default=REP_ARCH, choices=ARCHS + ["mamba"],
                    help=f"representative architecture for main figures (default {REP_ARCH})")
    ap.add_argument("--rng-seed", type=int, default=0,
                    help="RNG seed for bootstrap CI")
    ap.add_argument("--force-extract", action="store_true",
                    help="force re-extraction (overwrite existing npz)")

    # model/data params (used only by --extract/--all)
    ap.add_argument("--d-model", dest="d_model", type=int, default=64)
    ap.add_argument("--n-layers", dest="n_layers", type=int, default=2)
    ap.add_argument("--batch-size", dest="batch_size", type=int, default=16)
    ap.add_argument("--num-workers", dest="num_workers", type=int, default=0)
    ap.add_argument("--limit", type=int, default=None,
                    help="smoke-test truncation (max samples)")

    ap.add_argument("--smoke", action="store_true",
                    help="smoke mode: only 2 directions x 1 arch x 1 seed = 2 checkpoints")

    args = ap.parse_args()

    print(f"Project root: {_PROJECT_ROOT}")
    print(f"Checkpoints: {_CKPT_ROOT}")
    print(f"Output directory:   {_FIGURES_DIR}")
    print(f"Config: pairs={len(PAIRS)} archs={ARCHS} seeds={SEEDS} "
          f"-> {len(PAIRS)*len(ARCHS)*len(SEEDS)} checkpoints")
    print(f"Representative: arch={args.rep_arch} seed={args.rep_seed}")

    if args.extract or args.all:
        n = extract_probs(args)
        if n == 0 and not args.plot:
            print("\n[WARN] No probs extracted. Check checkpoint and data paths.")
            return

    if args.plot or args.all:
        n_main, n_supp = generate_figures(args)
        # Result summary
        print("\n" + "=" * 70)
        print("E6 reliability diagram generation complete")
        print("=" * 70)
        print(f"  Main figures:     {n_main} / 7")
        print(f"  Supplementary:    {n_supp} / 60")
        print(f"  Output directory: {_FIGURES_DIR}")
        if n_main < 7 or n_supp < 60:
            print(f"  [WARN] some figures missing -- check whether e6_probs.npz was extracted")
        print("\nArgument summary:")
        print("  - Main figures show the 6 directions' pre/post-TS reliability curves + summary")
        print("  - Supplementary figures cover all 60 checkpoints for seed-sensitivity audit")
        print("  - Each figure shows the y=x line, pre-TS (red)/post-TS (green) curves, per-bin sample counts, and CI")
        print("  - See module docstring for caveats (A1-A6)")


if __name__ == "__main__":
    main()
