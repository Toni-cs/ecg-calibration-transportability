"""E3 core experiment: Brier Reliability + DCR + NCV + ECE change.

Primary endpoint rationale
--------------------------
Murphy decomposition of the Brier score (Murphy 1973):

    Brier = Reliability - Resolution + Uncertainty

Temperature scaling (TS) with T>0 preserves argmax (the predicted class is unchanged), therefore:
  - Uncertainty (a function of the global base rate) is exactly invariant
  - Resolution (per-bin deviation of label frequency from the global base rate) is invariant
    in the exact-binning limit
  - Reliability (per-bin deviation of predicted probability from empirical frequency) is the
    only component materially affected by TS

Hence the primary endpoint is the improvement in the Reliability component (not the total Brier
Score), because:
  1. Total Brier change mixes Reliability improvement with Resolution change, diluting the effect
  2. Reliability directly measures calibration (agreement of probability with frequency)
  3. Resolution and Uncertainty are not controlled by TS, so reporting their "improvement" is meaningless

Key assumptions
---------------
H1 (TS affects only Reliability):
  - strictly holds in the exact-binning limit (one bin per unique probability)
  - approximately holds under 10 equal-width bins; TS can shift samples across bins, slightly
    changing Resolution. This script reports DeltaResolution as a diagnostic for H1.
H2 (TS preserves argmax): softmax(logits/T) argmax = softmax(logits) argmax for T>0. Strictly
  holds (T>0 is a monotonic transform); thus the ECE correctness mask is unchanged by TS.
H3 (paired independence): the 60 checkpoints' improvement values are treated as independent
  paired samples. Approximately holds: checkpoints differ in seed/pair/arch but share data and code.

Applicability bounds
--------------------
1. DCR (Decision Cost Reduction) is an indirect clinical-relevance indicator:
   - tau=0.5 means "act only if confidence > 50%, otherwise abstain"
   - abstain_cost=0.5 (symmetric) is a simplification; real clinical costs of misdiagnosis vs
     missed diagnosis are asymmetric
   - DCR does not replace a formal decision-curve analysis (DCA); it is directional evidence only
2. NCV (Net Clinical Value) symmetric definition bounds:
   - N_total = N_samples * N_classes assumes each (sample, class) pair is independent
   - the K OvR decisions for one sample are not independent (probabilities sum to 1),
     so NCV variance is underestimated
   - the symmetric definition (equal weights on TP/TN/FP/FN) does not reflect clinical preference
   - NCV is an indirect indicator, not a formal clinical-utility claim
3. Brier decomposition 10-bin discretization:
   - the exact identity holds only when probabilities are constant within a bin
   - brier_total = REL - RES + UNC holds by construction
   - the gap between raw Brier (mean((p-y)^2)) and brier_total reflects binning granularity

Caveats (sensitivity analyses)
------------------------------
- A1: TS-only-affects-Reliability is not strict under 10 bins. Mitigation: report the
  DeltaResolution/DeltaReliability ratio; if <<1 the approximation holds, otherwise use exact
  binning (unique probs) or more bins (50/100).
- A2: NCV multiclass definition. Mitigation: NCV is directional (sign), not an effect size for
  formal hypothesis testing; report per-sample-aggregated NCV (N_total=N) as sensitivity.
- A3: DCR abstain_cost=0.5. Mitigation: DCR is monotonic in abstain_cost over [0,1], so the sign
  is invariant (TS improves the decision direction); report abstain_cost=0.3 and 0.7 as sensitivity.
- A4: independence of the 60 checkpoints. Mitigation: different pairs use different source/target
  domains and independently trained seeds; report pair-level aggregation (mean of 6 pairs) as a
  conservative analysis.
- A5: top-label vs per-class OvR Brier decomposition. Mitigation: top-label matches the ECE
  primary-endpoint semantics; report per-class OvR as sensitivity.

Outputs
-------
1. results/c1_brier_reliability.csv         -- 60 checkpoints x Brier 3 components (TS before/after, ID+OOD)
2. results/c1_dcr_ncv_multiclass.csv        -- 60 checkpoints x DCR/NCV/ECE (TS before/after, ID+OOD)
3. results/c1_brier_reliability_summary.csv -- primary endpoint summary (Cohen's d, 95% CI, paired t-test)
4. results/c1_dcr_ncv_summary.csv           -- secondary endpoint summary (t-test, BH FDR q=0.05)

Usage:
    python scripts/run_e3_brier_dcr_ncv.py           # use cached probs (if present)
    python scripts/run_e3_brier_dcr_ncv.py --regen   # re-run forward pass to generate probs
    python scripts/run_e3_brier_dcr_ncv.py --limit 240  # smoke test
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
# Path setup
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.utils.calibration import (  # noqa: E402
    fit_temperature, apply_temperature, ece, brier_parts, brier_raw,
)

# ---------------------------------------------------------------------------
# Experiment configuration
# ---------------------------------------------------------------------------
PAIRS = [
    "ptbxl_chapman", "ptbxl_cpsc",
    "chapman_ptbxl", "chapman_cpsc",
    "cpsc_ptbxl", "cpsc_chapman",
]
ARCHS = ["inceptiontime", "resnet1d"]
SEEDS = [42, 43, 44, 45, 46]
# 6 pairs x 2 archs x 5 seeds = 60 checkpoints

DATA_DIRS = {
    "ptbxl": _PROJECT_ROOT / "data" / "ptbxl_processed",
    "chapman": _PROJECT_ROOT / "data" / "chapman_processed_v2",
    "cpsc": _PROJECT_ROOT / "data" / "cpsc_processed",
}
DATASET_NUM_CLASSES = {"ptbxl": 5, "chapman": 5, "cpsc": 4}

TAU = 0.5           # DCR/NCV decision threshold
ABSTAIN_COST = 0.5  # abstain cost (symmetric)
N_BINS = 10         # Brier decomposition bin count
N_BOOTSTRAP = 10000 # Cohen's d bootstrap CI
FDR_Q = 0.05        # BH FDR significance level
RNG_SEED = 42       # global reproducible seed

RESULTS_DIR = _PROJECT_ROOT / "results"


# ===========================================================================
# Part 1: metric computation
# ===========================================================================

def _to_onehot(labels: np.ndarray, K: int) -> np.ndarray:
    """Class indices -> one-hot (N, K)"""
    onehot = np.zeros((len(labels), K), dtype=float)
    onehot[np.arange(len(labels)), labels] = 1.0
    return onehot


def brier_parts_toplabel(probs: np.ndarray, labels: np.ndarray,
                         n_bins: int = N_BINS) -> Tuple[float, float, float, float]:
    """Top-label Brier decomposition.

    Reduce multiclass to binary: p = max prob, y = 1[argmax == label].
    Consistent with calibration.compute_all_metrics (confidence-correctness mapping).

    Returns:
        (brier_total, reliability, resolution, uncertainty)
    """
    max_p = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == labels).astype(float)
    return brier_parts(max_p, correct, n_bins=n_bins)


def brier_parts_ovr(probs: np.ndarray, labels: np.ndarray,
                    n_bins: int = N_BINS) -> Tuple[float, float, float, float]:
    """Per-class OvR Brier decomposition (averaged over classes).

    For each class k compute a binary Brier decomposition (p_k vs 1[label==k]), then average.
    Uses all probability information; serves as a sensitivity analysis to top-label.

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
    """Top-label ECE (consistent with calibration.ece)"""
    max_p = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == labels).astype(float)
    return ece(max_p, correct, n_bins=n_bins)


def dcr_multiclass(probs_raw: np.ndarray, probs_cal: np.ndarray,
                   labels: np.ndarray, tau: float = TAU,
                   abstain_cost: float = ABSTAIN_COST) -> Tuple[float, float, float]:
    """Decision Cost Reduction at threshold tau.

    Decision rule: if max_p > tau -> predict argmax; else -> abstain.
    Cost: wrong decision = 1, abstain = abstain_cost, correct decision = 0.
    DCR = Cost_raw - Cost_cal (positive = TS reduced decision cost = good).

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
    """Net Clinical Value (symmetric definition).

    NCV = (TP_improved + TN_improved - FP_worsened - FN_worsened) / N_total
    N_total = N_samples * N_classes

    For each (sample, class) pair:
      raw_pos = p_raw > tau,  cal_pos = p_cal > tau,  true_pos = (label == class)
      TP_improved: raw=neg -> cal=pos, true=pos  (correctly became more confident)
      TN_improved: raw=pos -> cal=neg, true=neg  (correctly became less confident)
      FP_worsened: raw=neg -> cal=pos, true=neg  (wrongly became more confident)
      FN_worsened: raw=pos -> cal=neg, true=pos  (wrongly became less confident)

    Returns:
        dict(ncv, tp_improved, tn_improved, fp_worsened, fn_worsened, n_total,
             ncv_per_sample)  # ncv_per_sample uses N_total=N as sensitivity
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
    # Sensitivity: per-sample aggregation (N_total=N)
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
    """Compute all E3 metrics for one test split (ID or OOD), before and after TS.

    Returns:
        dict with all E3 metrics for this split
    """
    # --- Brier 3 components (top-label, primary endpoint) ---
    b_raw, rel_raw, res_raw, unc_raw = brier_parts_toplabel(probs_raw, labels)
    b_cal, rel_cal, res_cal, unc_cal = brier_parts_toplabel(probs_cal, labels)

    # --- Brier 3 components (per-class OvR, sensitivity) ---
    bo_raw, relo_raw, reso_raw, unco_raw = brier_parts_ovr(probs_raw, labels)
    bo_cal, relo_cal, reso_cal, unco_cal = brier_parts_ovr(probs_cal, labels)

    # --- raw Brier Score (empirical mean, no binning) ---
    brier_raw_before = brier_raw(probs_raw.max(axis=1),
                                 (probs_raw.argmax(axis=1) == labels).astype(float))
    brier_raw_after = brier_raw(probs_cal.max(axis=1),
                                (probs_cal.argmax(axis=1) == labels).astype(float))

    # --- ECE (top-label, exploratory) ---
    ece_before = ece_toplabel(probs_raw, labels)
    ece_after = ece_toplabel(probs_cal, labels)

    # --- DCR (secondary endpoint 1) ---
    dcr_val, cost_raw, cost_cal = dcr_multiclass(probs_raw, probs_cal, labels)

    # --- NCV (secondary endpoint 2) ---
    ncv_result = ncv_multiclass(probs_raw, probs_cal, labels)

    return {
        # Brier top-label (primary endpoint)
        'brier_toplabel_before': b_raw,
        'brier_toplabel_after': b_cal,
        'reliability_toplabel_before': rel_raw,
        'reliability_toplabel_after': rel_cal,
        'resolution_toplabel_before': res_raw,
        'resolution_toplabel_after': res_cal,
        'uncertainty_toplabel_before': unc_raw,
        'uncertainty_toplabel_after': unc_cal,
        'delta_reliability_toplabel': rel_raw - rel_cal,  # positive = improvement
        'delta_resolution_toplabel': res_raw - res_cal,   # H1 diagnostic
        'delta_uncertainty_toplabel': unc_raw - unc_cal,  # should ~= 0
        # Brier per-class OvR (sensitivity)
        'reliability_ovr_before': relo_raw,
        'reliability_ovr_after': relo_cal,
        'delta_reliability_ovr': relo_raw - relo_cal,
        # raw Brier
        'brier_raw_before': brier_raw_before,
        'brier_raw_after': brier_raw_after,
        # ECE
        'ece_before': ece_before,
        'ece_after': ece_after,
        'delta_ece': ece_before - ece_after,  # positive = improvement
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
# Part 2: statistical tests
# ===========================================================================

def cohen_d_paired(before: np.ndarray, after: np.ndarray,
                   improvement_direction: str = "decrease") -> Dict:
    """Paired Cohen's d + 95% bootstrap CI + paired t-test.

    Args:
        before, after: metric values before/after TS (60 pairs)
        improvement_direction: "decrease" (smaller is better, e.g. Reliability/ECE)
                               or "increase" (larger is better, e.g. DCR/NCV)

    Returns:
        dict(mean_before, mean_after, mean_diff, std_diff, cohen_d,
             cohen_d_ci_lo, cohen_d_ci_hi, t_stat, p_value, n)
    """
    from scipy.stats import ttest_rel

    before = np.asarray(before, dtype=float)
    after = np.asarray(after, dtype=float)
    n = len(before)

    if improvement_direction == "decrease":
        diff = before - after  # positive = improvement
    else:
        diff = after - before  # positive = improvement

    mean_diff = float(np.mean(diff))
    std_diff = float(np.std(diff, ddof=1)) if n > 1 else 0.0
    cohen_d = mean_diff / std_diff if std_diff > 1e-12 else 0.0

    # paired t-test (scipy's ttest_rel tests H0: before == after)
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
    """Benjamini-Hochberg FDR correction.

    Args:
        p_values: raw p-value list
        q: FDR significance level

    Returns:
        (reject_list, adjusted_p_list)
    """
    p = np.asarray(p_values, dtype=float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order]

    # BH critical value: k * q / n
    critical = q * np.arange(1, n + 1) / n

    # Find the largest k with p_(k) <= k*q/n
    reject_flags = np.zeros(n, dtype=bool)
    max_k = 0
    for i in range(n - 1, -1, -1):
        if ranked[i] <= critical[i]:
            max_k = i + 1
            break
    reject_flags[order[:max_k]] = True

    # Adjusted p-values: p_adj_(k) = min_{j>=k} (p_(j) * n / j)
    adj_p_sorted = ranked * n / np.arange(1, n + 1)
    # Cumulative minimum from largest to smallest to ensure monotonicity
    adj_p_sorted = np.minimum.accumulate(adj_p_sorted[::-1])[::-1]
    adj_p = np.empty(n)
    adj_p[order] = adj_p_sorted
    adj_p = np.clip(adj_p, 0, 1)

    return reject_flags.tolist(), adj_p.tolist()


# ===========================================================================
# Part 3: probability acquisition (with cache)
# ===========================================================================

def _parse_pair(pair: str) -> Tuple[str, str]:
    """ptbxl_chapman -> (ptbxl, chapman)"""
    parts = pair.split("_")
    return parts[0], parts[1]


def get_num_classes(source: str, target: str) -> int:
    """CPSC maps to 4 classes (symmetric SUBSPACE_CPSC downgrade); otherwise 5."""
    return min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])


def load_or_compute_probs(pair: str, arch: str, seed: int,
                          regen: bool, limit: Optional[int],
                          batch_size: int = 16, num_workers: int = 0) -> Optional[Dict]:
    """Load or compute the raw probabilities for one checkpoint.

    Cache path: checkpoints/transfer/{pair}/{arch}/seed{seed}/e3_probs.npz

    Returns:
        dict(cal_probs, cal_labels, id_probs, id_labels, ood_probs, ood_labels,
             T, num_classes) or None (load failed)
    """
    source, target = _parse_pair(pair)
    ckpt_dir = _PROJECT_ROOT / "checkpoints" / "transfer" / pair / arch / f"seed{seed}"
    cache_path = ckpt_dir / "e3_probs.npz"
    ckpt_path = ckpt_dir / "best_model.pt"

    # --- try loading from cache ---
    if not regen and cache_path.exists():
        try:
            data = np.load(cache_path, allow_pickle=False)
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
            warnings.warn(f"Cache load failed {cache_path}: {e}; will recompute")

    # --- check checkpoint exists ---
    if not ckpt_path.exists():
        warnings.warn(f"Checkpoint not found: {ckpt_path}")
        return None

    # --- check data directories ---
    src_data = DATA_DIRS.get(source)
    tgt_data = DATA_DIRS.get(target)
    if src_data is None or tgt_data is None or not src_data.exists() or not tgt_data.exists():
        warnings.warn(f"Data directory not found: {src_data} or {tgt_data}")
        return None

    # --- load model and run forward pass ---
    try:
        import torch
        from src.models.ecg_classifier import ECGClassifier
        from train import (
            set_seed, evaluate, create_dataloader,
            build_ptbxl_datasets, build_chapman_datasets, build_cpsc_datasets,
        )
        from src.data.mapping import SUBSPACE_CPSC
    except ImportError as e:
        warnings.warn(f"Cannot import training dependencies: {e}")
        return None

    K = get_num_classes(source, target)
    subspace = SUBSPACE_CPSC if K == 4 else None

    builders = {
        "ptbxl": build_ptbxl_datasets,
        "chapman": build_chapman_datasets,
        "cpsc": build_cpsc_datasets,
    }

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    set_seed(seed)

    # Build source dataset
    try:
        if source == "cpsc":
            src_ds, src_clusters = builders[source](str(src_data), seed, limit=limit)
        elif subspace is not None:
            src_ds, src_clusters = builders[source](str(src_data), seed, limit=limit, subspace=subspace)
        else:
            src_ds, src_clusters = builders[source](str(src_data), seed, limit=limit)
    except Exception as e:
        warnings.warn(f"Failed to build source dataset ({source}): {e}")
        return None

    # cal and test DataLoaders
    cal_loader = create_dataloader(src_ds["cal"], batch_size, shuffle=False, num_workers=num_workers)
    test_loader = create_dataloader(src_ds["test"], batch_size, shuffle=False, num_workers=num_workers)

    # Load model
    try:
        ckpt = torch.load(ckpt_path, weights_only=False, map_location=device)
        sd = ckpt["model_state_dict"]
        # Infer d_model and n_layers
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
        warnings.warn(f"Model load failed {ckpt_path}: {e}")
        return None

    # Forward pass: source-cal, source-test (ID)
    cal_eval = evaluate(model, cal_loader, device, compute_calibration=False)
    test_eval = evaluate(model, test_loader, device, compute_calibration=False)
    cal_probs = cal_eval["probs"]
    cal_labels = cal_eval["labels"]
    id_probs = test_eval["probs"]
    id_labels = test_eval["labels"]

    # Build target dataset and run forward pass (OOD)
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
        warnings.warn(f"Target dataset evaluation failed ({target}): {e}")
        return None

    # Fit temperature scaling (on source-cal)
    cal_onehot = _to_onehot(cal_labels, K)
    T = fit_temperature(cal_probs, cal_onehot)

    # Cache
    try:
        np.savez_compressed(
            str(cache_path),
            cal_probs=cal_probs, cal_labels=cal_labels,
            id_probs=id_probs, id_labels=id_labels,
            ood_probs=ood_probs, ood_labels=ood_labels,
            T=np.array([T]), num_classes=np.array([K]),
        )
    except Exception as e:
        warnings.warn(f"Cache save failed: {e}")

    return {
        'cal_probs': cal_probs, 'cal_labels': cal_labels,
        'id_probs': id_probs, 'id_labels': id_labels,
        'ood_probs': ood_probs, 'ood_labels': ood_labels,
        'T': T, 'num_classes': K,
    }


# ===========================================================================
# Part 4: main flow
# ===========================================================================

def run_experiment(args: argparse.Namespace) -> Tuple[List[Dict], List[Dict]]:
    """Run the E3 experiment, return (brier_rows, dcr_ncv_rows)"""

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
                print(f"{tag} loading probs...", end=" ", flush=True)

                probs_data = load_or_compute_probs(
                    pair, arch, seed,
                    regen=args.regen, limit=args.limit,
                    batch_size=args.batch_size, num_workers=args.num_workers,
                )

                if probs_data is None:
                    print("SKIP (probs unavailable)")
                    continue

                T = probs_data['T']
                K = probs_data['num_classes']

                # Apply temperature scaling
                id_probs_raw = probs_data['id_probs']
                id_labels = probs_data['id_labels']
                ood_probs_raw = probs_data['ood_probs']
                ood_labels = probs_data['ood_labels']

                id_probs_cal = apply_temperature(id_probs_raw, T)
                ood_probs_cal = apply_temperature(ood_probs_raw, T)

                # Compute metrics (ID and OOD)
                id_metrics = compute_all_metrics_for_split(id_probs_raw, id_probs_cal, id_labels)
                ood_metrics = compute_all_metrics_for_split(ood_probs_raw, ood_probs_cal, ood_labels)

                # Assemble rows
                base = {
                    'pair': pair, 'source': source, 'target': target,
                    'arch': arch, 'seed': seed, 'T': T, 'num_classes': K,
                    'n_id': len(id_labels), 'n_ood': len(ood_labels),
                }

                # Brier reliability row (ID + OOD side by side)
                brier_row = {**base}
                for split_name, m in [('id', id_metrics), ('ood', ood_metrics)]:
                    for key, val in m.items():
                        if key.startswith('brier') or key.startswith('reliability') \
                           or key.startswith('resolution') or key.startswith('uncertainty') \
                           or key.startswith('delta_reliability') or key.startswith('delta_resolution') \
                           or key.startswith('delta_uncertainty'):
                            brier_row[f'{key}_{split_name}'] = val
                brier_rows.append(brier_row)

                # DCR/NCV/ECE row
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
    """Aggregate statistics and write the 4 CSVs"""

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    n = len(brier_rows)
    print(f"\nProcessed {n} / 60 checkpoints")

    if n == 0:
        print("WARNING: no data, skipping summary")
        return

    # ==================================================================
    # CSV 1: c1_brier_reliability.csv (per checkpoint)
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
        w.writerow(["# E3 primary endpoint: Brier Reliability improvement (Murphy decomposition)"])
        w.writerow(["# Brier = Reliability - Resolution + Uncertainty (Murphy 1973)"])
        w.writerow(["# Primary endpoint = delta_reliability_toplabel (TS before/after, positive = improvement)"])
        w.writerow(["# Primary analysis on OOD (60 pairs); ID as reference"])
        w.writerow(["# n_checkpoints", n])
        w.writerow([])
        w.writerow(brier_fields)
        for row in brier_rows:
            w.writerow([row.get(k, '') for k in brier_fields])
    print(f"Wrote {csv1}")

    # ==================================================================
    # CSV 2: c1_dcr_ncv_multiclass.csv (per checkpoint)
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
        w.writerow(["# E3 secondary endpoints: DCR + NCV + exploratory ECE change"])
        w.writerow(["# DCR: Decision Cost Reduction, tau=0.5, abstain_cost=0.5"])
        w.writerow(["# NCV: Net Clinical Value, symmetric definition, N_total=N_samples x N_classes"])
        w.writerow(["# ECE: Expected Calibration Error (top-label, 10 bins)"])
        w.writerow(["# n_checkpoints", n])
        w.writerow([])
        w.writerow(dcr_fields)
        for row in dcr_ncv_rows:
            w.writerow([row.get(k, '') for k in dcr_fields])
    print(f"Wrote {csv2}")

    # ==================================================================
    # CSV 3: c1_brier_reliability_summary.csv (primary endpoint summary)
    # ==================================================================
    csv3 = RESULTS_DIR / "c1_brier_reliability_summary.csv"

    # Extract paired values for OOD and ID
    rel_before_ood = [r['reliability_toplabel_before_ood'] for r in brier_rows]
    rel_after_ood = [r['reliability_toplabel_after_ood'] for r in brier_rows]
    rel_before_id = [r['reliability_toplabel_before_id'] for r in brier_rows]
    rel_after_id = [r['reliability_toplabel_after_id'] for r in brier_rows]

    # Primary endpoint statistics (OOD)
    stats_rel_ood = cohen_d_paired(rel_before_ood, rel_after_ood, "decrease")
    stats_rel_id = cohen_d_paired(rel_before_id, rel_after_id, "decrease")

    # Resolution change (H1 diagnostic)
    res_before_ood = [r['resolution_toplabel_before_ood'] for r in brier_rows]
    res_after_ood = [r['resolution_toplabel_after_ood'] for r in brier_rows]
    stats_res_ood = cohen_d_paired(res_before_ood, res_after_ood, "decrease")

    # Uncertainty change (should ~= 0)
    unc_before_ood = [r['uncertainty_toplabel_before_ood'] for r in brier_rows]
    unc_after_ood = [r['uncertainty_toplabel_after_ood'] for r in brier_rows]
    stats_unc_ood = cohen_d_paired(unc_before_ood, unc_after_ood, "decrease")

    # per-class OvR Reliability (sensitivity)
    relo_before_ood = [r['reliability_ovr_before_ood'] for r in brier_rows]
    relo_after_ood = [r['reliability_ovr_after_ood'] for r in brier_rows]
    stats_relo_ood = cohen_d_paired(relo_before_ood, relo_after_ood, "decrease")

    # H1 diagnostic ratio
    mean_delta_rel = stats_rel_ood['mean_diff']
    mean_delta_res = stats_res_ood['mean_diff']
    h1_ratio = abs(mean_delta_res) / abs(mean_delta_rel) if abs(mean_delta_rel) > 1e-12 else float('nan')

    with open(csv3, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# E3 primary endpoint summary: Brier Reliability improvement"])
        w.writerow(["# Primary endpoint = Reliability_toplabel improvement (TS before - TS after, positive = good)"])
        w.writerow(["# Statistics: paired t-test + Cohen's d + 95% bootstrap CI (B=10000)"])
        w.writerow(["# n_checkpoints", n])
        w.writerow([])
        w.writerow(["metric", "split", "mean_before", "mean_after", "mean_diff",
                    "std_diff", "cohen_d", "cohen_d_ci_lo", "cohen_d_ci_hi",
                    "t_stat", "p_value", "n"])
        for name, s, split in [
            ("Reliability_toplabel (primary)", stats_rel_ood, "OOD"),
            ("Reliability_toplabel (reference)", stats_rel_id, "ID"),
            ("Resolution_toplabel (H1 diagnostic)", stats_res_ood, "OOD"),
            ("Uncertainty_toplabel (should ~=0)", stats_unc_ood, "OOD"),
            ("Reliability_OvR (sensitivity)", stats_relo_ood, "OOD"),
        ]:
            w.writerow([name, split,
                        f"{s['mean_before']:.6f}", f"{s['mean_after']:.6f}",
                        f"{s['mean_diff']:+.6f}", f"{s['std_diff']:.6f}",
                        f"{s['cohen_d']:+.4f}",
                        f"{s['cohen_d_ci_lo']:+.4f}", f"{s['cohen_d_ci_hi']:+.4f}",
                        f"{s['t_stat']:+.4f}", f"{s['p_value']:.6e}", s['n']])
        w.writerow([])
        w.writerow(["# H1 diagnostic: |DeltaResolution| / |DeltaReliability| (OOD)"])
        w.writerow(["h1_ratio", f"{h1_ratio:.4f}",
                    "# <0.1 -> H1 approx holds; >0.3 -> H1 may not hold"])
        w.writerow(["mean_delta_reliability", f"{mean_delta_rel:+.6f}"])
        w.writerow(["mean_delta_resolution", f"{mean_delta_res:+.6f}"])
    print(f"Wrote {csv3}")

    # ==================================================================
    # CSV 4: c1_dcr_ncv_summary.csv (secondary endpoint summary + BH FDR)
    # ==================================================================
    csv4 = RESULTS_DIR / "c1_dcr_ncv_summary.csv"

    # DCR (OOD primary analysis)
    dcr_ood = [r['dcr_ood'] for r in dcr_ncv_rows]
    dcr_id = [r['dcr_id'] for r in dcr_ncv_rows]
    # DCR is already (cost_raw - cost_cal), positive = improvement. Use "increase" direction.
    stats_dcr_ood = cohen_d_paired(np.zeros(n), dcr_ood, "increase")
    stats_dcr_id = cohen_d_paired(np.zeros(n), dcr_id, "increase")

    # NCV (OOD primary analysis)
    ncv_ood = [r['ncv_ood'] for r in dcr_ncv_rows]
    ncv_id = [r['ncv_id'] for r in dcr_ncv_rows]
    stats_ncv_ood = cohen_d_paired(np.zeros(n), ncv_ood, "increase")
    stats_ncv_id = cohen_d_paired(np.zeros(n), ncv_id, "increase")

    # ECE change (exploratory)
    ece_before_ood = [r['ece_before_ood'] for r in dcr_ncv_rows]
    ece_after_ood = [r['ece_after_ood'] for r in dcr_ncv_rows]
    stats_ece_ood = cohen_d_paired(ece_before_ood, ece_after_ood, "decrease")

    # BH FDR correction (2 secondary endpoints: DCR, NCV)
    p_values = [stats_dcr_ood['p_value'], stats_ncv_ood['p_value']]
    reject, adj_p = bh_fdr(p_values, q=FDR_Q)

    with open(csv4, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["# E3 secondary endpoint summary: DCR + NCV + exploratory ECE"])
        w.writerow(["# DCR: Decision Cost Reduction (tau=0.5, abstain_cost=0.5)"])
        w.writerow(["# NCV: Net Clinical Value (symmetric, N_total=N x K)"])
        w.writerow(["# BH FDR correction: q=0.05, 2 secondary endpoints (DCR, NCV)"])
        w.writerow(["# n_checkpoints", n])
        w.writerow([])
        w.writerow(["metric", "split", "mean", "std", "cohen_d",
                    "cohen_d_ci_lo", "cohen_d_ci_hi", "t_stat", "p_value",
                    "p_adj_bh", "reject_h0", "n"])
        for name, s, split, p_adj, rej in [
            ("DCR (secondary 1)", stats_dcr_ood, "OOD", adj_p[0], reject[0]),
            ("DCR (reference)", stats_dcr_id, "ID", "", ""),
            ("NCV (secondary 2)", stats_ncv_ood, "OOD", adj_p[1], reject[1]),
            ("NCV (reference)", stats_ncv_id, "ID", "", ""),
            ("ΔECE (exploratory)", stats_ece_ood, "OOD", "", ""),
        ]:
            w.writerow([name, split,
                        f"{s['mean_diff']:+.6f}", f"{s['std_diff']:.6f}",
                        f"{s['cohen_d']:+.4f}",
                        f"{s['cohen_d_ci_lo']:+.4f}", f"{s['cohen_d_ci_hi']:+.4f}",
                        f"{s['t_stat']:+.4f}", f"{s['p_value']:.6e}",
                        f"{p_adj:.6e}" if p_adj != "" else "",
                        str(rej) if rej != "" else "", s['n']])
        w.writerow([])
        w.writerow(["# BH FDR correction details"])
        w.writerow(["# Raw p-values: DCR={:.6e}, NCV={:.6e}".format(p_values[0], p_values[1])])
        w.writerow(["# Adjusted p-values: DCR={:.6e}, NCV={:.6e}".format(adj_p[0], adj_p[1])])
        w.writerow(["# Reject H0:   DCR={}, NCV={}".format(reject[0], reject[1])])
        w.writerow(["# FDR threshold:   q={}".format(FDR_Q)])
    print(f"Wrote {csv4}")

    # ==================================================================
    # Console summary
    # ==================================================================
    print("\n" + "=" * 80)
    print("E3 experiment summary")
    print("=" * 80)
    print(f"\n[Primary endpoint] Brier Reliability improvement (OOD, n={n})")
    print(f"  ΔReliability = {stats_rel_ood['mean_diff']:+.6f} ± {stats_rel_ood['std_diff']:.6f}")
    print(f"  Cohen's d = {stats_rel_ood['cohen_d']:+.4f} "
          f"[{stats_rel_ood['cohen_d_ci_lo']:+.4f}, {stats_rel_ood['cohen_d_ci_hi']:+.4f}]")
    print(f"  paired t = {stats_rel_ood['t_stat']:+.4f}, p = {stats_rel_ood['p_value']:.6e}")

    print(f"\n[H1 diagnostic] |ΔResolution|/|ΔReliability| = {h1_ratio:.4f}")
    if h1_ratio < 0.1:
        print(f"  -> H1 approximately holds (Resolution change << Reliability change)")
    elif h1_ratio < 0.3:
        print(f"  -> H1 partially holds (Resolution changes slightly)")
    else:
        print(f"  -> H1 may not hold (Resolution changes substantially; consider more bins)")

    print(f"\n[Secondary endpoint 1] DCR (OOD, tau=0.5)")
    print(f"  DCR = {stats_dcr_ood['mean_diff']:+.6f}, p = {stats_dcr_ood['p_value']:.6e}, "
          f"p_adj = {adj_p[0]:.6e}, reject = {reject[0]}")

    print(f"\n[Secondary endpoint 2] NCV (OOD, N_total=N x K)")
    print(f"  NCV = {stats_ncv_ood['mean_diff']:+.6f}, p = {stats_ncv_ood['p_value']:.6e}, "
          f"p_adj = {adj_p[1]:.6e}, reject = {reject[1]}")

    print(f"\n[Exploratory] ΔECE (OOD)")
    print(f"  ΔECE = {stats_ece_ood['mean_diff']:+.6f}, p = {stats_ece_ood['p_value']:.6e}")


# ===========================================================================
# Part 5: entry point
# ===========================================================================

def main():
    ap = argparse.ArgumentParser(
        description="E3 core experiment: Brier Reliability + DCR + NCV + ECE change")
    ap.add_argument("--regen", action="store_true",
                    help="re-run forward pass to generate probabilities (otherwise use cache)")
    ap.add_argument("--limit", type=int, default=None,
                    help="smoke-test sample truncation count")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--num-workers", type=int, default=0,
                    help="DataLoader worker threads")
    args = ap.parse_args()

    print("=" * 80)
    print("E3 core experiment: Brier Reliability + DCR + NCV + ECE change")
    print("=" * 80)
    print(f"Checkpoints: {len(PAIRS)} pairs x {len(ARCHS)} archs x {len(SEEDS)} seeds "
          f"= {len(PAIRS) * len(ARCHS) * len(SEEDS)}")
    print(f"Primary endpoint: Brier Reliability improvement (Cohen's d + 95% CI + paired t-test)")
    print(f"Secondary endpoint 1: DCR (tau={TAU})")
    print(f"Secondary endpoint 2: NCV (symmetric, N_total=N x K)")
    print(f"Exploratory: ECE change")
    print(f"Multiple comparisons: BH FDR (q={FDR_Q}, 2 secondary endpoints)")
    print(f"Cache: {'regenerate' if args.regen else 'prefer existing'}")
    print()

    brier_rows, dcr_ncv_rows = run_experiment(args)
    summarize_and_write(brier_rows, dcr_ncv_rows)

    print("\nE3 experiment complete.")


if __name__ == "__main__":
    main()
