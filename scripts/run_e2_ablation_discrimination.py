"""E2: temperature-scaling component ablation + discrimination metrics (all 60 experiments).

=====================================================================
Experiment goals
=====================================================================
1. 3-stage ablation that isolates the contribution of each temperature-scaling (TS)
   component to Brier reliability:
   Stage 1: TS only          -- a single global temperature T, calibrating only confidence sharpness
   Stage 2: TS + binned T    -- split into 5 bins by predicted entropy (uncertainty), one T per bin
   Stage 3: TS + binned + tau-- additionally optimize classification thresholds tau_k on top of binned

2. Discrimination metrics (AUROC/AUPRC/F1/PPV/NPV/MCC) computed for all 60 experiments.

=====================================================================
Core claims
=====================================================================
- The ablation isolates each component's contribution because the three stages are
  strictly nested parameter subsets:
    Theta_1 = {T}                    subset Theta_2 = {T, T_1..T_5}   subset Theta_3 = {T, T_1..T_5, tau_1..tau_K}
  DeltaReliability(Stage2-Stage1) = marginal contribution of binned T (controlling for global T)
  DeltaReliability(Stage3-Stage2) = marginal contribution of threshold optimization (controlling for binned T)
  The nested structure guarantees additive interpretation of marginal contributions
  (no parameter-space overlap).

- TS preserves argmax (softmax(log p / T) is order-preserving for T>0):
    * accuracy / F1 / MCC and other argmax-based metrics are identical between Stage 1/2 and raw
    * AUROC/AUPRC are based on probability ranking: under binary classification TS is a monotonic
      transform -> strictly invariant; under multiclass OvR TS does not guarantee per-class order
      preservation -> may change slightly (measured and reported by the script)
    * Stage 3 threshold optimization changes argmax -> F1/PPV/NPV/MCC change

=====================================================================
Key assumptions
=====================================================================
A1. Binned temperature uses as its binning variable the entropy H(TS(p)) = -sum p'_k log p'_k of the
    TS-calibrated distribution, where p' = TS(p) (the output of the Stage 1 temperature scaling).
    Note: E4's binned-T uses H(p) (binning on the raw probabilities), so the two are not directly
    comparable, for two reasons:
    (1) different binning variable: E2 Stage2/3 use H(TS(p)), E4 uses H(p);
    (2) different structure: E2 Stage2/3 = TS+binned (global TS first, then binned temperature),
        E4 = binned only (binned temperature without a preceding global TS).
    The two parameter spaces are neither nested nor isomorphic, so DeltaReliability is not
    interpretable as a marginal contribution.
    Assumption: high-uncertainty sample segments need a different sharpness calibration than
    low-uncertainty ones (over/under-confidence patterns differ). If false, Stage2-Stage1 ~ 0
    (reported honestly by the script).
A2. Threshold optimization is fit on the cal set and evaluated on the test set.
    Assumption: cal and test are identically distributed (ID assumption); under OOD the threshold
    transfer decays, so the script also reports the cal-optimal tau's behavior on test (no test peeking).
A3. A bin is only fit if it has >= 10 samples; otherwise T=1.0 (no calibration).
    Prevents overfitting small bins (in the n_cal=60 smoke scenario some bins may be too small).

=====================================================================
Applicability boundaries
=====================================================================
- Ablation conclusions apply to the (source, target, arch, seed) combinations of these 60 experiments;
  extrapolating to new datasets requires re-validating A1 (validity of entropy binning).
- The upside of threshold optimization is bounded by cal set size: with small n_cal the tau estimate
  has high variance, and Stage3-Stage2 may contain noise.
- Multiclass "TS invariance" of AUROC is approximate, not exact -- the script measures |DeltaAUROC| and reports it.

=====================================================================
Outputs
=====================================================================
1. results/ablation_ts_components.csv
   columns: source, target, arch, seed, stage, brier_reliability, brier_resolution,
            brier_uncertainty, brier_raw, ece, smooth_ece, n_samples, T_global,
            T_binned(mean,min,max), threshold_norm
2. results/discrimination_metrics_60exp.csv
   columns: source, target, arch, seed, split(cal/test), variant(raw/ts/binned/threshold),
            auroc, auprc, f1, ppv, npv, mcc, auroc_ts_minus_raw (honest check column)

Usage:
    python scripts/run_e2_ablation_discrimination.py
    python scripts/run_e2_ablation_discrimination.py --limit 240   # smoke test
    python scripts/run_e2_ablation_discrimination.py --pairs ptbxl_chapman   # single pair
"""

from __future__ import annotations

import argparse
import json
import sys
import warnings
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import torch
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    matthews_corrcoef,
    precision_score,
    roc_auc_score,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.models.ecg_classifier import ECGClassifier  # noqa: E402
from src.utils.calibration import brier_parts, brier_raw, ece, smooth_ece, _validate_n_bins  # noqa: E402
from src.utils.calibration_methods import (  # noqa: E402
    apply_temperature_multiclass,
    fit_temperature_multiclass,
)
from train import (  # noqa: E402
    build_chapman_datasets,
    build_cpsc_datasets,
    build_ptbxl_datasets,
    create_dataloader,
    evaluate,
    set_seed,
)
from src.data.mapping import SUBSPACE_CPSC, SUPERCLASSES  # noqa: E402

# =====================================================================
# Configuration
# =====================================================================

DATA_DIRS = {
    "ptbxl": str(_PROJECT_ROOT / "data" / "ptbxl_processed"),
    "chapman": str(_PROJECT_ROOT / "data" / "chapman_processed_v2"),
    "cpsc": str(_PROJECT_ROOT / "data" / "cpsc_processed"),
}

DATASET_BUILDERS = {
    "ptbxl": build_ptbxl_datasets,
    "chapman": build_chapman_datasets,
    "cpsc": build_cpsc_datasets,
}
DATASET_NUM_CLASSES = {"ptbxl": 5, "chapman": 5, "cpsc": 4}

CKPT_ROOT = _PROJECT_ROOT / "checkpoints" / "transfer"
RESULTS_DIR = _PROJECT_ROOT / "results"
CACHE_DIR = _PROJECT_ROOT / "checkpoints" / "e2_probs_cache"

N_BINS_TEMPERATURE = 5      # number of bins for binned temperature
MIN_SAMPLES_PER_BIN = 10    # minimum samples per bin; below this T=1.0
N_BINS = 10                 # bins for Brier reliability / ECE evaluation (consistent with E3/E4/E6 and library default)
EPS = 1e-12


# =====================================================================
# 1. Binned temperature (Stage 2 component)
# =====================================================================

def _entropy(probs: np.ndarray) -> np.ndarray:
    """Predicted-distribution entropy H(p) = -sum p_k log p_k (uncertainty measure)."""
    p = np.clip(probs, EPS, 1.0)
    return -np.sum(p * np.log(p), axis=1)


def fit_binned_temperature(
    cal_probs: np.ndarray,
    cal_labels: np.ndarray,
    n_bins: int = N_BINS_TEMPERATURE,
) -> dict:
    """Fit one temperature T per bin, binning by predicted entropy into n_bins bins.

    Binning uses equal-frequency (quantile) bins to balance sample counts per bin.
    Each bin is fit with fit_temperature_multiclass (multiclass NLL minimization).
    Bins with too few samples get T=1.0 (no calibration, assumption A3).

    Returns:
        {'temperatures': [T_0..T_{n_bins-1}],
         'bin_edges': entropy bin edges (n_bins+1,)}
    """
    n_bins = _validate_n_bins(n_bins)  # public guard: reject bool input + avoid OOM
    ent = _entropy(cal_probs)
    bin_edges = np.quantile(ent, np.linspace(0, 1, n_bins + 1))
    bin_edges[0] = -np.inf       # left edge open
    bin_edges[-1] = np.inf       # right edge closed
    bin_idx = np.digitize(ent, bin_edges[1:-1])  # 0..n_bins-1

    temperatures = []
    for b in range(n_bins):
        mask = bin_idx == b
        if mask.sum() < MIN_SAMPLES_PER_BIN:
            temperatures.append(1.0)
            continue
        try:
            params = fit_temperature_multiclass(cal_probs[mask], cal_labels[mask])
            temperatures.append(float(params["T"]))
        except Exception:
            temperatures.append(1.0)
    return {"temperatures": temperatures, "bin_edges": bin_edges.tolist()}


def apply_binned_temperature(probs: np.ndarray, params: dict) -> np.ndarray:
    """Bin by sample entropy, apply the corresponding bin's T as temperature scaling."""
    ent = _entropy(probs)
    bin_edges = np.asarray(params["bin_edges"])
    bin_idx = np.digitize(ent, bin_edges[1:-1])
    out = np.zeros_like(probs, dtype=float)
    for b, T in enumerate(params["temperatures"]):
        mask = bin_idx == b
        if not mask.any():
            continue
        out[mask] = apply_temperature_multiclass(
            probs[mask], {"T": float(T)}
        )
    return out


# =====================================================================
# 2. Threshold optimization (Stage 3 component)
# =====================================================================

def predict_with_thresholds(probs: np.ndarray, thresholds: np.ndarray) -> np.ndarray:
    """Threshold-adjusted prediction: argmax(p_k - tau_k).

    tau=0 degenerates to standard argmax. Larger tau_k -> class k is harder to predict
    (requires higher p_k).
    """
    return (probs - thresholds[None, :]).argmax(axis=1)


def optimize_thresholds(
    cal_probs: np.ndarray,
    cal_labels: np.ndarray,
    n_classes: int,
) -> np.ndarray:
    """Optimize thresholds tau on the cal set to maximize macro-F1.

    Uses coordinate descent + grid search (61 points per class on [-0.3, 0.3]).
    Objective = macro-F1 (more robust to class imbalance than accuracy).
    Returns the optimal tau (n_classes,).
    """
    from scipy.optimize import minimize

    def neg_macro_f1(tau):
        preds = predict_with_thresholds(cal_probs, tau)
        return -f1_score(cal_labels, preds, average="macro", zero_division=0)

    res = minimize(
        neg_macro_f1,
        x0=np.zeros(n_classes),
        method="Nelder-Mead",
        options={"maxiter": 2000, "xatol": 1e-3, "fatol": 1e-5},
    )
    return np.clip(res.x, -0.5, 0.5)


# =====================================================================
# 3. Discrimination metrics
# =====================================================================

def _npv(y_true, y_pred, n_classes):
    """NPV = TN/(TN+FN), macro-averaged."""
    cm = confusion_matrix(y_true, y_pred, labels=list(range(n_classes)))
    npvs = []
    for k in range(n_classes):
        tp = cm[k, k]
        fn = cm[:, k].sum() - tp
        fp = cm[k, :].sum() - tp
        tn = cm.sum() - tp - fn - fp
        denom = tn + fn
        npvs.append(tn / denom if denom > 0 else 0.0)
    return float(np.mean(npvs))


def compute_discrimination_metrics(
    probs: np.ndarray,
    labels: np.ndarray,
    thresholds: Optional[np.ndarray] = None,
) -> dict:
    """Compute AUROC/AUPRC/F1/PPV/NPV/MCC.

    AUROC/AUPRC are based on probabilities (OvR), unaffected by argmax/threshold.
    F1/PPV/NPV/MCC are based on argmax(p - tau); thresholds=None means tau=0 (standard argmax).
    """
    n_classes = probs.shape[1]
    labels = np.asarray(labels, dtype=int)

    # --- AUROC / AUPRC (probability-ranking based, OvR macro) ---
    onehot = np.eye(n_classes)[labels]
    try:
        auroc = roc_auc_score(
            labels, probs, multi_class="ovr", average="macro"
        )
    except ValueError:
        auroc = float("nan")
    try:
        auprc = average_precision_score(onehot, probs, average="macro")
    except ValueError:
        auprc = float("nan")

    # --- argmax / threshold-based metrics ---
    if thresholds is None:
        preds = probs.argmax(axis=1)
    else:
        preds = predict_with_thresholds(probs, thresholds)

    f1 = f1_score(labels, preds, average="macro", zero_division=0)
    ppv = precision_score(labels, preds, average="macro", zero_division=0)
    npv = _npv(labels, preds, n_classes)
    try:
        mcc = matthews_corrcoef(labels, preds)
    except ValueError:
        mcc = 0.0

    return {
        "auroc": float(auroc),
        "auprc": float(auprc),
        "f1": float(f1),
        "ppv": float(ppv),
        "npv": float(npv),
        "mcc": float(mcc),
    }


# =====================================================================
# 4. Brier reliability (ablation primary quantity)
# =====================================================================

def calibration_reliability(probs: np.ndarray, labels: np.ndarray) -> dict:
    """Brier reliability + ECE + SmoothECE.

    For the multiclass top-label setting: max_prob vs correct_mask binarized
    (consistent with the eval_transfer.py primary endpoint semantics).
    """
    max_prob = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == labels).astype(float)
    # Explicitly pass n_bins=N_BINS so the Brier reliability bin granularity is controlled.
    b_total, rel, res, unc = brier_parts(max_prob, correct, n_bins=N_BINS)
    return {
        "brier_reliability": float(rel),
        "brier_resolution": float(res),
        "brier_uncertainty": float(unc),
        "brier_raw": float(brier_raw(max_prob, correct)),
        "ece": float(ece(max_prob, correct, n_bins=N_BINS)),
        "smooth_ece": float(smooth_ece(max_prob, correct)),
    }


# =====================================================================
# 5. Model loading + forward inference (reuses eval_transfer logic)
# =====================================================================

def _infer_arch_params(arch: str, sd: dict, args):
    """Infer d_model / n_layers from the state_dict (reuses eval_transfer.py logic)."""
    if arch == "mamba":
        inferred_d_model = sd["backbone.stem.0.weight"].shape[0]
        import re
        layer_ids = {
            re.match(r"backbone\.layers\.(\d+)\.", k).group(1)
            for k in sd if re.match(r"backbone\.layers\.(\d+)\.", k)
        }
        inferred_n_layers = len(layer_ids)
    elif "backbone.proj.weight" in sd:
        inferred_d_model = sd["backbone.proj.weight"].shape[0]
        inferred_n_layers = args.n_layers
    else:
        inferred_d_model = args.d_model
        inferred_n_layers = args.n_layers
    return inferred_d_model, inferred_n_layers


def _build(dataset: str, data_dir: str, seed: int, limit, subspace=None):
    builder = DATASET_BUILDERS[dataset]
    if dataset == "cpsc":
        ds, clusters = builder(data_dir, seed, limit=limit)
    elif subspace is not None:
        ds, clusters = builder(data_dir, seed, limit=limit, subspace=subspace)
    else:
        ds, clusters = builder(data_dir, seed, limit=limit)
    return ds, clusters


def load_probs_for_checkpoint(
    source: str, target: str, arch: str, seed: int, args, device
) -> Optional[dict]:
    """Load checkpoint, run forward inference on source-cal and target-test.

    Returns:
        {'cal_probs': (Ncal,K), 'cal_labels': (Ncal,),
         'test_probs': (Ntest,K), 'test_labels': (Ntest,),
         'num_classes': K}
    or None (checkpoint missing / load failed)
    """
    ckpt_path = CKPT_ROOT / f"{source}_{target}" / arch / f"seed{seed}" / "best_model.pt"
    if not ckpt_path.exists():
        return None

    # cache path (avoid repeated forward inference)
    cache_file = CACHE_DIR / f"{source}_{target}_{arch}_seed{seed}.npz"
    if args.use_cache and cache_file.exists():
        d = np.load(cache_file, allow_pickle=True)
        return {
            "cal_probs": d["cal_probs"], "cal_labels": d["cal_labels"],
            "test_probs": d["test_probs"], "test_labels": d["test_labels"],
            "num_classes": int(d["num_classes"]),
        }

    set_seed(seed)
    num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
    subspace = SUBSPACE_CPSC if num_classes == 4 else None

    # load checkpoint
    ckpt = torch.load(ckpt_path, weights_only=False, map_location=device)
    sd = ckpt["model_state_dict"]
    ckpt_nc = ckpt.get("num_classes")
    if ckpt_nc is not None and ckpt_nc != num_classes:
        warnings.warn(f"{ckpt_path}: num_classes mismatch {ckpt_nc} != {num_classes}, skip")
        return None

    d_model, n_layers = _infer_arch_params(arch, sd, args)
    model = ECGClassifier(
        in_channels=12, d_model=d_model, n_layers=n_layers,
        num_classes=num_classes, dropout=0.1, backbone_type=arch,
    ).to(device)
    try:
        model.load_state_dict(sd)
    except RuntimeError as e:
        warnings.warn(f"{ckpt_path}: load_state_dict failed: {e}")
        return None
    model.eval()

    # source-cal forward
    src_ds, _ = _build(source, DATA_DIRS[source], seed, args.limit, subspace=subspace)
    cal_loader = create_dataloader(src_ds["cal"], args.batch_size, shuffle=False,
                                   num_workers=args.num_workers)
    cal_eval = evaluate(model, cal_loader, device, compute_calibration=False)

    # target-test forward
    tgt_ds, _ = _build(target, DATA_DIRS[target], seed, args.limit, subspace=subspace)
    tgt_loader = create_dataloader(tgt_ds["test"], args.batch_size, shuffle=False,
                                   num_workers=args.num_workers)
    tgt_eval = evaluate(model, tgt_loader, device, compute_calibration=False)

    result = {
        "cal_probs": cal_eval["probs"], "cal_labels": cal_eval["labels"],
        "test_probs": tgt_eval["probs"], "test_labels": tgt_eval["labels"],
        "num_classes": num_classes,
    }

    # cache
    if args.use_cache:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            cache_file,
            cal_probs=result["cal_probs"], cal_labels=result["cal_labels"],
            test_probs=result["test_probs"], test_labels=result["test_labels"],
            num_classes=num_classes,
        )
    return result


# =====================================================================
# 6. Single experiment: 3-stage ablation + discrimination metrics
# =====================================================================

def run_single_experiment(
    source: str, target: str, arch: str, seed: int, args
) -> Tuple[List[dict], List[dict]]:
    """Run the 3-stage ablation + discrimination metrics for one (source, target, arch, seed).

    Returns:
        (ablation_rows, discrimination_rows)
    """
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    data = load_probs_for_checkpoint(source, target, arch, seed, args, device)
    if data is None:
        print(f"  [SKIP] {source}_{target}/{arch}/seed{seed}: checkpoint unavailable")
        return [], []

    cal_p, cal_y = data["cal_probs"], data["cal_labels"]
    test_p, test_y = data["test_probs"], data["test_labels"]
    K = data["num_classes"]

    ablation_rows = []
    disc_rows = []

    # ===== Stage 1: TS only =====
    ts_params = fit_temperature_multiclass(cal_p, cal_y)
    T_global = float(ts_params["T"])
    cal_s1 = apply_temperature_multiclass(cal_p, ts_params)
    test_s1 = apply_temperature_multiclass(test_p, ts_params)

    # ===== Stage 2: TS + binned temperature =====
    # First apply TS (reuse Stage 1's ts_params and cal_s1/test_s1), then fit and apply
    # binned-T on the TS-calibrated probabilities. The old implementation applied
    # binned-T directly to raw cal_p/test_p (= binned only), which made Stage 2 actually
    # Theta={T_1..T_5} instead of Theta={T_global, T_1..T_5 on TS output}, breaking the
    # Stage1 subset Stage2 nesting so the ablation marginal contribution was not interpretable.
    binned_params = fit_binned_temperature(cal_s1, cal_y)
    cal_s2 = apply_binned_temperature(cal_s1, binned_params)
    test_s2 = apply_binned_temperature(test_s1, binned_params)
    T_binned = binned_params["temperatures"]

    # ===== Stage 3: TS + binned + threshold optimization =====
    tau = optimize_thresholds(cal_s2, cal_y, K)
    # Stage3 probabilities = Stage2 probabilities (threshold only changes argmax, not probabilities)
    cal_s3, test_s3 = cal_s2, test_s2

    # ===== Ablation Brier reliability (test set) =====
    for stage_name, probs in [
        ("raw", test_p),
        ("stage1_ts", test_s1),
        ("stage2_ts_binned", test_s2),
        ("stage3_ts_binned_threshold", test_s3),
    ]:
        rel = calibration_reliability(probs, test_y)
        row = {
            "source": source, "target": target, "arch": arch, "seed": seed,
            "stage": stage_name, "n_samples": len(test_y),
            "T_global": T_global if stage_name != "raw" else np.nan,
            "T_binned_mean": np.mean(T_binned) if "binned" in stage_name else np.nan,
            "T_binned_min": np.min(T_binned) if "binned" in stage_name else np.nan,
            "T_binned_max": np.max(T_binned) if "binned" in stage_name else np.nan,
            "threshold_norm": float(np.linalg.norm(tau)) if "threshold" in stage_name else 0.0,
        }
        row.update(rel)
        ablation_rows.append(row)

    # ===== Discrimination metrics (all 60 experiments) =====
    # variant: raw / ts / binned / threshold
    # AUROC/AUPRC based on probabilities; F1/PPV/NPV/MCC based on argmax(p-tau)
    for split_name, probs, labels in [
        ("cal", cal_p, cal_y),
        ("test", test_p, test_y),
    ]:
        for variant, v_probs, v_tau in [
            ("raw", probs, None),
            ("ts", apply_temperature_multiclass(probs, ts_params), None),
            # "binned" must match Stage 2 semantics (TS+binned), and "threshold" must match
            # Stage 3 semantics (TS+binned+tau). The old implementation called
            # apply_binned_temperature(probs, ...) directly (= binned only), inconsistent
            # with the ablation table's stage2_ts_binned.
            ("binned",
             apply_binned_temperature(
                 apply_temperature_multiclass(probs, ts_params), binned_params),
             None),
            ("threshold",
             apply_binned_temperature(
                 apply_temperature_multiclass(probs, ts_params), binned_params),
             tau),
        ]:
            m = compute_discrimination_metrics(v_probs, labels, thresholds=v_tau)
            row = {
                "source": source, "target": target, "arch": arch, "seed": seed,
                "split": split_name, "variant": variant,
            }
            row.update(m)
            disc_rows.append(row)

    # ===== Honest check: effect of TS on AUROC =====
    # Binary: strictly invariant (monotonic transform); multiclass OvR: may change slightly
    raw_disc = compute_discrimination_metrics(test_p, test_y)
    ts_disc = compute_discrimination_metrics(test_s1, test_y)
    delta_auroc = ts_disc["auroc"] - raw_disc["auroc"]
    delta_auprc = ts_disc["auprc"] - raw_disc["auprc"]

    print(
        f"  [{source}_{target}/{arch}/s{seed}] "
        f"T={T_global:.3f} T_binned=[{np.mean(T_binned):.3f}+-{np.std(T_binned):.3f}] "
        f"||tau||={np.linalg.norm(tau):.4f} | "
        f"Rel: raw={ablation_rows[0]['brier_reliability']:.4f} "
        f"s1={ablation_rows[1]['brier_reliability']:.4f} "
        f"s2={ablation_rows[2]['brier_reliability']:.4f} "
        f"s3={ablation_rows[3]['brier_reliability']:.4f} | "
        f"AUROC raw={raw_disc['auroc']:.4f} ts={ts_disc['auroc']:.4f} "
        f"delta={delta_auroc:+.6f} (effect of TS on AUROC; should be ~0 for multiclass)"
    )

    # Attach the DeltaAUROC check column to the test/ts row (for CSV inspection)
    for r in disc_rows:
        if r["split"] == "test" and r["variant"] == "ts":
            r["auroc_ts_minus_raw"] = delta_auroc
            r["auprc_ts_minus_raw"] = delta_auprc
        else:
            r["auroc_ts_minus_raw"] = np.nan
            r["auprc_ts_minus_raw"] = np.nan

    return ablation_rows, disc_rows


# =====================================================================
# 7. Entry point
# =====================================================================

def discover_checkpoints() -> List[Tuple[str, str, str, int]]:
    """Scan CKPT_ROOT, return all (source, target, arch, seed) combinations."""
    pairs = []
    for pair_dir in sorted(CKPT_ROOT.iterdir()):
        if not pair_dir.is_dir() or "_" not in pair_dir.name:
            continue
        source, target = pair_dir.name.split("_", 1)
        if source not in DATASET_BUILDERS or target not in DATASET_BUILDERS:
            continue
        for arch_dir in sorted(pair_dir.iterdir()):
            if not arch_dir.is_dir():
                continue
            arch = arch_dir.name
            for seed_dir in sorted(arch_dir.iterdir()):
                if not seed_dir.is_dir():
                    continue
                if (seed_dir / "best_model.pt").exists():
                    seed = int(seed_dir.name.replace("seed", ""))
                    pairs.append((source, target, arch, seed))
    return pairs


def main():
    ap = argparse.ArgumentParser(description="E2: TS ablation + discrimination metrics")
    ap.add_argument("--pairs", nargs="+", default=None,
                    help="specify pair (e.g. ptbxl_chapman); default all 60")
    ap.add_argument("--archs", nargs="+", default=None,
                    help="specify arch; default all")
    ap.add_argument("--seeds", nargs="+", type=int, default=None,
                    help="specify seed; default all")
    ap.add_argument("--limit", type=int, default=None, help="smoke-test sample cap")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--d-model", dest="d_model", type=int, default=64)
    ap.add_argument("--n-layers", dest="n_layers", type=int, default=2)
    ap.add_argument("--num-workers", type=int, default=0)
    ap.add_argument("--use-cache", action="store_true", default=True,
                    help="cache forward-inference probs (default on)")
    ap.add_argument("--no-cache", dest="use_cache", action="store_false")
    ap.add_argument("--output-ablation", default=str(RESULTS_DIR / "ablation_ts_components.csv"))
    ap.add_argument("--output-discrimination", default=str(RESULTS_DIR / "discrimination_metrics_60exp.csv"))
    args = ap.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    # discover checkpoints
    all_ckpts = discover_checkpoints()
    if args.pairs:
        all_ckpts = [c for c in all_ckpts if f"{c[0]}_{c[1]}" in args.pairs]
    if args.archs:
        all_ckpts = [c for c in all_ckpts if c[2] in args.archs]
    if args.seeds:
        all_ckpts = [c for c in all_ckpts if c[3] in args.seeds]

    print(f"E2 ablation+discrimination: {len(all_ckpts)} checkpoints")
    print(f"  output 1: {args.output_ablation}")
    print(f"  output 2: {args.output_discrimination}")
    print(f"  cache: {CACHE_DIR} (use_cache={args.use_cache})")
    print()

    all_ablation = []
    all_discrimination = []
    for i, (src, tgt, arch, seed) in enumerate(all_ckpts, 1):
        print(f"[{i}/{len(all_ckpts)}] {src}_{tgt}/{arch}/seed{seed}")
        ab_rows, disc_rows = run_single_experiment(src, tgt, arch, seed, args)
        all_ablation.extend(ab_rows)
        all_discrimination.extend(disc_rows)

    # ===== Output CSV =====
    df_abl = pd.DataFrame(all_ablation)
    df_disc = pd.DataFrame(all_discrimination)

    # ablation table: add marginal-contribution column
    if not df_abl.empty:
        pivot_rel = df_abl.pivot_table(
            index=["source", "target", "arch", "seed"],
            columns="stage", values="brier_reliability",
        )
        if "stage1_ts" in pivot_rel.columns and "raw" in pivot_rel.columns:
            df_abl["delta_rel_vs_raw"] = df_abl["brier_reliability"] - \
                df_abl.merge(pivot_rel["raw"].reset_index(),
                             on=["source", "target", "arch", "seed"],
                             how="left")["raw"]

    df_abl.to_csv(args.output_ablation, index=False, float_format="%.6f")
    df_disc.to_csv(args.output_discrimination, index=False, float_format="%.6f")

    print(f"\n{'='*70}")
    print(f"Ablation results: {args.output_ablation} ({len(df_abl)} rows)")
    print(f"Discrimination metrics: {args.output_discrimination} ({len(df_disc)} rows)")

    # ===== Summary statistics =====
    if not df_abl.empty:
        print(f"\n--- Ablation Brier reliability summary (test, mean±std) ---")
        for stage in ["raw", "stage1_ts", "stage2_ts_binned", "stage3_ts_binned_threshold"]:
            sub = df_abl[df_abl["stage"] == stage]
            if not sub.empty:
                r = sub["brier_reliability"]
                print(f"  {stage:30s}: {r.mean():.4f} ± {r.std():.4f}")

        # marginal contributions
        s1 = df_abl[df_abl["stage"] == "stage1_ts"]["brier_reliability"].mean()
        s2 = df_abl[df_abl["stage"] == "stage2_ts_binned"]["brier_reliability"].mean()
        s3 = df_abl[df_abl["stage"] == "stage3_ts_binned_threshold"]["brier_reliability"].mean()
        raw = df_abl[df_abl["stage"] == "raw"]["brier_reliability"].mean()
        print(f"\n--- Marginal contributions (lower reliability = better) ---")
        print(f"  Stage1 TS only:           {raw:.4f} -> {s1:.4f} (delta={s1-raw:+.4f})")
        print(f"  Stage2 +binned T:         {s1:.4f} -> {s2:.4f} (delta={s2-s1:+.4f})")
        print(f"  Stage3 +threshold opt:    {s2:.4f} -> {s3:.4f} (delta={s3-s2:+.4f}, =0 by construction: threshold only changes argmax, not probabilities)")

    if not df_disc.empty:
        print(f"\n--- Discrimination metrics summary (test, mean) ---")
        test_disc = df_disc[df_disc["split"] == "test"]
        for variant in ["raw", "ts", "binned", "threshold"]:
            sub = test_disc[test_disc["variant"] == variant]
            if not sub.empty:
                print(f"  {variant:10s}: "
                      f"AUROC={sub['auroc'].mean():.4f} "
                      f"AUPRC={sub['auprc'].mean():.4f} "
                      f"F1={sub['f1'].mean():.4f} "
                      f"PPV={sub['ppv'].mean():.4f} "
                      f"NPV={sub['npv'].mean():.4f} "
                      f"MCC={sub['mcc'].mean():.4f}")

        # Honest report: effect of TS on AUROC
        ts_rows = test_disc[test_disc["variant"] == "ts"]
        if "auroc_ts_minus_raw" in ts_rows.columns:
            deltas = ts_rows["auroc_ts_minus_raw"].dropna()
            if not deltas.empty:
                print(f"\n--- TS effect on AUROC check (honest report) ---")
                print(f"  deltaAUROC(ts-raw): mean={deltas.mean():+.6f} "
                      f"max|delta|={deltas.abs().max():.6f} "
                      f"(should be 0 for binary, may shift slightly for multiclass OvR)")
                print(f"  note: TS preserves argmax -> F1/MCC unchanged; "
                      f"AUROC is probability-ranking based, and under multiclass TS is not "
                      f"per-class monotonic -> may shift slightly")

    print(f"\n{'='*70}")
    print("E2 complete.")


if __name__ == "__main__":
    main()
