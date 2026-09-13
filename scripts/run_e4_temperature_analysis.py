"""E4: temperature distribution + binned-temperature exploratory evaluation
(preregistered-protocol exploratory analysis, not part of the primary test).

Three components:
  1. Distribution of fitted T values across the 60 experiments (histogram statistics,
     variation across direction / architecture / seed).
  2. Binned-temperature evaluation, binning by uncertainty quintiles (5 bins):
     - one T is fit independently per bin on cal and applied to test by uncertainty bin
     - compare global-T vs binned-T on Brier reliability improvement
  3. Shift sensitivity: how T changes across L2 prior-shift levels (8+ levels).

================================================================
Claims
================================================================
C1. The T-value distribution reveals the variation structure of the "calibration
    temperature" across experiments:
    - cross-direction variation -> whether OOD difficulty is reflected in T
    - cross-architecture variation -> whether different backbones differ systematically in overconfidence
    - cross-seed variation -> statistical stability of the T estimate
C2. Binned temperature (binned by uncertainty) captures T heterogeneity:
    - high-uncertainty bins may need larger T (more aggressive smoothing)
    - low-uncertainty bins may be near identity (T~1)
    - if binned-T Brier reliability beats global-T, T is not constant
C3. Shift sensitivity characterizes the robustness of T to distribution drift:
    - if T changes monotonically with shift -> T is an identifiable function of shift (learnable prior)
    - if T is approximately invariant -> T is shift-invariant (single-point calibration suffices)

================================================================
Key assumptions
================================================================
A1. The T fit on cal represents that experiment's "calibration temperature" (standard TS paradigm).
A2. Quintile boundaries defined by uncertainty (entropy) on cal transfer to test
    (i.e. cal and test have similar uncertainty distributions -- may be violated under OOD, a limitation).
A3. Binned T assumes samples in the same bin share an optimal T (T is a piecewise-constant function of uncertainty).
A4. The 8+ L2-shift levels are a meaningful proxy for prior shift
    (strictly, L2 shift is covariate drift rather than pure prior shift -- a limitation).
A5. Brier reliability is a reasonable metric for binned-T evaluation (no binning bias, unlike ECE).

================================================================
Scope and limitations
================================================================
B1. Exploratory evaluation; does not enter the primary test (the primary test is the BCa CI in eval_transfer.py).
B2. 5 quintile bins is a conventional choice; no bin-count sensitivity (3/7/10) was run -- a limitation.
B3. Shift sensitivity depends on l2_shift_results.json availability (present for 24/60 experiments).
B4. Under OOD, assumption A2 may be violated -- interpret results with caution.
B5. T re-fitting relies on cal being reproducible (same seed and data split).

================================================================
Reasoning chain (from distribution analysis to conclusions)
================================================================
1. Load 60 checkpoints -> fit T_global on cal -> obtain the T distribution.
2. Cross-direction/architecture/seed variation of the T distribution -> reveals structured variation sources of T.
3. Bin by uncertainty quintiles into 5 bins -> fit T_bin per bin -> obtain T as a function of uncertainty.
4. Compare binned-T vs global-T Brier reliability -> assess practical value of T heterogeneity.
5. For experiments with l2_shift, re-fit T per shift level -> T(shift) curve.
6. Monotonicity / invariance of T(shift) -> decide whether T is shift-invariant.

Outputs:
  results/temperature_distribution_analysis.csv
    - one row: pair, arch, seed, T_global, n_cal, n_test,
            cal_entropy_mean, cal_entropy_std, fit_status
    - cross-direction/architecture/seed variation summary rows
  results/binned_temperature_exploratory.csv
    - one row: pair, arch, seed, bin_idx, n_cal_bin, n_test_bin,
            T_bin, T_global,
            brier_rel_raw, brier_rel_binned, brier_rel_global,
            delta_rel_binned_vs_raw, delta_rel_global_vs_raw,
            bin_entropy_lo, bin_entropy_hi
  - shift sensitivity: shift rows in results/temperature_distribution_analysis.csv

Usage:
    python scripts/run_e4_temperature_analysis.py
    # subset:
    python scripts/run_e4_temperature_analysis.py --pairs ptbxl_chapman --archs resnet1d --seeds 42
    # skip shift sensitivity (when no l2_shift data):
    python scripts/run_e4_temperature_analysis.py --skip-shift-sensitivity
    # cache probs to speed up reruns:
    python scripts/run_e4_temperature_analysis.py --cache-dir checkpoints/e4_cache
"""
from __future__ import annotations

import argparse
import json
import sys
import warnings
import hashlib
from pathlib import Path
from typing import Optional

import numpy as np
import torch

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from src.models.ecg_classifier import ECGClassifier  # noqa: E402
from src.data.mapping import SUBSPACE_CPSC, SUPERCLASSES  # noqa: E402
from src.data.l2_shifts import get_l2_shifts, apply_shift  # noqa: E402
from src.utils.calibration import (  # noqa: E402
    fit_temperature, apply_temperature, brier_parts, brier_raw, smooth_ece,
    _validate_n_bins,
)
from train import (  # noqa: E402
    set_seed, evaluate, create_dataloader,
    build_ptbxl_datasets, build_chapman_datasets, build_cpsc_datasets,
)

# =====================================================================
# Experiment grid (aligned with eval_transfer.py)
# =====================================================================
DATASET_BUILDERS = {
    "ptbxl": build_ptbxl_datasets,
    "chapman": build_chapman_datasets,
    "cpsc": build_cpsc_datasets,
}
DATASET_NUM_CLASSES = {"ptbxl": 5, "chapman": 5, "cpsc": 4}
DATASET_DIRS = {
    "ptbxl": "data/ptbxl_processed",
    "chapman": "data/chapman_processed_v2",
    "cpsc": "data/cpsc_processed",
}
ALL_PAIRS = [
    "ptbxl_chapman", "ptbxl_cpsc",
    "chapman_ptbxl", "chapman_cpsc",
    "cpsc_ptbxl", "cpsc_chapman",
]
ALL_ARCHS = ["mamba", "resnet1d", "inceptiontime"]
ALL_SEEDS = [42, 43, 44, 45, 46]

N_BINS = 5  # number of bins for binned temperature (quintiles)
BRIER_N_BINS = 10  # equal-width bins for Brier reliability (matches calibration.brier_parts default)
T_MIN, T_MAX = 0.01, 100.0  # aligned with calibration.py


# =====================================================================
# Utility functions
# =====================================================================
def _maxprob(p: np.ndarray) -> np.ndarray:
    return np.asarray(p).max(axis=1)


def _correct_mask(p: np.ndarray, labels: np.ndarray) -> np.ndarray:
    return (np.asarray(p).argmax(1) == np.asarray(labels)).astype(float)


def predictive_entropy(probs: np.ndarray) -> np.ndarray:
    """Multiclass predictive entropy H[p] = -sum p_k log p_k (uncertainty measure).

    High entropy = high uncertainty; low entropy = confident model.
    Used as the binning variable for binned temperature.
    """
    probs = np.asarray(probs, dtype=float)
    p_clip = np.clip(probs, 1e-12, 1.0)
    return -np.sum(probs * np.log(p_clip), axis=1)


def brier_reliability_top(probs: np.ndarray, labels: np.ndarray) -> float:
    """Top-label Brier reliability (the reliability term of the Murphy decomposition).

    Uses max-prob as the predicted confidence and correct_mask as the label, with
    BRIER_N_BINS equal-width bins. Consistent with calibration.brier_parts
    (top-label calibration in a binary-view perspective).
    """
    mp = _maxprob(probs)
    cm = _correct_mask(probs, labels)
    _, rel, _, _ = brier_parts(mp, cm, n_bins=BRIER_N_BINS)
    return float(rel)


def brier_raw_top(probs: np.ndarray, labels: np.ndarray) -> float:
    """Top-label raw Brier score = mean((maxprob - correct)^2)."""
    mp = _maxprob(probs)
    cm = _correct_mask(probs, labels)
    return float(brier_raw(mp, cm))


def quintile_edges(values: np.ndarray, n_bins: int = N_BINS) -> np.ndarray:
    """Compute bin edges at n_bins quantiles (n_bins+1 points, including 0% and 100%)."""
    n_bins = _validate_n_bins(n_bins)  # public guard: reject bool input + avoid OOM
    qs = np.linspace(0, 1, n_bins + 1)
    edges = np.quantile(values, qs)
    # de-duplication guard (edges may repeat if values have many ties)
    edges = np.unique(edges)
    if len(edges) < n_bins + 1:
        # degenerate case: fall back to equal-width edges
        edges = np.linspace(values.min(), values.max() + 1e-9, n_bins + 1)
    edges[0] = -np.inf  # first bin left-open
    edges[-1] = np.inf  # last bin right-closed
    return edges


def assign_bins(values: np.ndarray, edges: np.ndarray) -> np.ndarray:
    """Assign each sample to a bin by edges, returning the 0-based bin index.

    edges[0]=-inf, edges[-1]=inf; bin i = [edges[i], edges[i+1])
    """
    bin_idx = np.digitize(values, edges[1:-1], right=False)
    return bin_idx.astype(int)


# =====================================================================
# Checkpoint loading (reuses eval_transfer.py logic)
# =====================================================================
def load_checkpoint(
    pair: str, arch: str, seed: int, save_dir: Path,
    d_model: int = 64, n_layers: int = 2,
) -> tuple[torch.nn.Module, int, int, int]:
    """Load a checkpoint, returning (model, inferred_d_model, inferred_n_layers, num_classes).

    Inference logic matches eval_transfer.py: d_model/n_layers are recovered from the
    state_dict.
    """
    source, target = pair.split("_")
    num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    run_dir = save_dir / pair / arch / f"seed{seed}"
    ckpt_path = run_dir / "best_model.pt"
    if not ckpt_path.exists():
        raise FileNotFoundError(f"Checkpoint not found: {ckpt_path}")

    ckpt = torch.load(ckpt_path, weights_only=False, map_location=device)
    sd = ckpt["model_state_dict"]
    ckpt_nc = ckpt.get("num_classes")
    if ckpt_nc is not None and ckpt_nc != num_classes:
        raise RuntimeError(
            f"Checkpoint num_classes={ckpt_nc} != {num_classes} for {pair}/{arch}/seed{seed}"
        )

    # recover architecture parameters from the state_dict (consistent with eval_transfer.py)
    if arch == "mamba":
        inferred_d_model = sd["backbone.stem.0.weight"].shape[0]
        import re
        layer_ids = {re.match(r"backbone\.layers\.(\d+)\.", k).group(1)
                     for k in sd if re.match(r"backbone\.layers\.(\d+)\.", k)}
        inferred_n_layers = len(layer_ids)
    elif "backbone.proj.weight" in sd:
        inferred_d_model = sd["backbone.proj.weight"].shape[0]
        inferred_n_layers = n_layers
    else:
        inferred_d_model = d_model
        inferred_n_layers = n_layers

    model = ECGClassifier(
        in_channels=12, d_model=inferred_d_model, n_layers=inferred_n_layers,
        num_classes=num_classes, dropout=0.1, backbone_type=arch,
    ).to(device)
    model.load_state_dict(sd)
    model.eval()
    return model, inferred_d_model, inferred_n_layers, num_classes


def build_datasets(pair: str, seed: int, limit: Optional[int] = None):
    """Build the four-split datasets for source and target, returning
    (src_ds, tgt_ds, src_clusters, tgt_clusters, num_classes, subspace)."""
    source, target = pair.split("_")
    num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
    subspace = SUBSPACE_CPSC if num_classes == 4 else None

    src_builder = DATASET_BUILDERS[source]
    tgt_builder = DATASET_BUILDERS[target]

    src_dir = str(_PROJECT_ROOT / DATASET_DIRS[source])
    tgt_dir = str(_PROJECT_ROOT / DATASET_DIRS[target])

    if source == "cpsc":
        src_ds, src_clusters = src_builder(src_dir, seed, limit=limit)
    else:
        src_ds, src_clusters = src_builder(src_dir, seed, limit=limit, subspace=subspace)
    if target == "cpsc":
        tgt_ds, tgt_clusters = tgt_builder(tgt_dir, seed, limit=limit)
    else:
        tgt_ds, tgt_clusters = tgt_builder(tgt_dir, seed, limit=limit, subspace=subspace)

    return src_ds, tgt_ds, src_clusters, tgt_clusters, num_classes, subspace


def get_probs_labels(
    model: torch.nn.Module, dataset, device, batch_size: int = 64,
) -> tuple[np.ndarray, np.ndarray]:
    """Run forward inference on dataset, returning (probs, labels)."""
    loader = create_dataloader(dataset, batch_size, shuffle=False, num_workers=0)
    ev = evaluate(model, loader, device, compute_calibration=False)
    return ev["probs"], ev["labels"]


def shifted_probs_labels(
    model: torch.nn.Module, dataset, shift: dict, device,
    pair_id: str = None, arch: str = None, train_seed: int = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply the shift to every signal in dataset, then run forward inference, returning
    (probs, labels). Consistent with eval_l2_shift.py's shifted_eval.
    """
    if pair_id is None or arch is None or train_seed is None:
        raise ValueError(
            "pair_id, arch, train_seed must be explicitly provided for reproducible seed derivation"
        )
    model.eval()
    all_probs, all_labels = [], []
    n = len(dataset)
    # Derive the noise seed from the experiment parameters so that noise stays
    # independent across experiments, shift levels, and shift types. Use hashlib.md5
    # instead of the built-in hash() for cross-process reproducibility (independent of
    # PYTHONHASHSEED). The derived key includes pair_id|arch|train_seed|shift_name, so
    # different experiments/levels/types always obtain distinct seeds.
    noise_seed = int(
        hashlib.md5(f"{pair_id}|{arch}|{train_seed}|{shift['name']}".encode()).hexdigest()[:8], 16
    ) % (2**32)
    rng = np.random.RandomState(noise_seed)
    with torch.no_grad():
        for i in range(n):
            x, y = dataset[i]
            sig = x.numpy()
            sig_s = apply_shift(sig, shift, rng=rng)
            x_s = torch.from_numpy(sig_s).unsqueeze(0).to(device)
            _, probs = model(x_s)
            probs = probs.cpu().numpy()
            all_probs.append(probs[0])
            all_labels.append(int(y))
    return np.array(all_probs), np.array(all_labels)


# =====================================================================
# Caching (avoid reloading models)
# =====================================================================
def cache_key(pair: str, arch: str, seed: int) -> str:
    return f"{pair}__{arch}__seed{seed}"


def load_cache(cache_dir: Optional[Path], pair: str, arch: str, seed: int) -> Optional[dict]:
    if cache_dir is None:
        return None
    p = cache_dir / f"{cache_key(pair, arch, seed)}.npz"
    if not p.exists():
        return None
    d = np.load(p, allow_pickle=True)
    return {k: d[k] for k in d.files}


def save_cache(cache_dir: Path, pair: str, arch: str, seed: int, data: dict) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_dir / f"{cache_key(pair, arch, seed)}.npz"
    np.savez(p, **data)


# =====================================================================
# Core: T fitting + binned T
# =====================================================================
def fit_global_T(cal_probs: np.ndarray, cal_labels: np.ndarray) -> tuple[float, str]:
    """Global temperature fitting (consistent with fit_temperature, single T for multiclass)."""
    try:
        # one-hot encoding (fit_temperature expects val_y shaped like val_p)
        n_classes = cal_probs.shape[1]
        y_onehot = np.eye(n_classes)[cal_labels]
        T = fit_temperature(cal_probs, y_onehot, method="L-BFGS-B")
        return float(np.clip(T, T_MIN, T_MAX)), "ok"
    except Exception as e:
        warnings.warn(f"fit_global_T failed: {e}")
        return 1.0, f"fail:{type(e).__name__}"


def fit_binned_T(
    cal_probs: np.ndarray, cal_labels: np.ndarray, n_bins: int = N_BINS,
) -> tuple[np.ndarray, np.ndarray, list]:
    """Bin by uncertainty (entropy) quintiles and fit one T per bin independently.

    Returns:
        T_per_bin: (n_bins,) T per bin
        bin_edges: (n_bins+1,) bin edges (including -inf, inf)
        bin_records: list of dict, detailed info per bin
    """
    ent = predictive_entropy(cal_probs)
    edges = quintile_edges(ent, n_bins=n_bins)
    bin_idx = assign_bins(ent, edges)

    n_classes = cal_probs.shape[1]
    T_per_bin = np.ones(n_bins, dtype=float)
    bin_records = []

    for b in range(n_bins):
        mask = bin_idx == b
        n_b = int(mask.sum())
        rec = {"bin_idx": b, "n_cal_bin": n_b,
               "entropy_lo": float(edges[b]) if np.isfinite(edges[b]) else -np.inf,
               "entropy_hi": float(edges[b + 1]) if np.isfinite(edges[b + 1]) else np.inf,
               "entropy_mean": float(ent[mask].mean()) if n_b > 0 else float("nan")}
        if n_b < n_classes * 2:  # too few samples, skip fitting
            rec["T_bin"] = 1.0
            rec["status"] = f"insufficient_samples(n={n_b})"
            bin_records.append(rec)
            continue
        try:
            y_oh = np.eye(n_classes)[cal_labels[mask]]
            T_b = fit_temperature(cal_probs[mask], y_oh, method="L-BFGS-B")
            T_b = float(np.clip(T_b, T_MIN, T_MAX))
            T_per_bin[b] = T_b
            rec["T_bin"] = T_b
            rec["status"] = "ok"
        except Exception as e:
            rec["T_bin"] = 1.0
            rec["status"] = f"fail:{type(e).__name__}"
        bin_records.append(rec)

    return T_per_bin, edges, bin_records


def apply_binned_T(
    probs: np.ndarray, T_per_bin: np.ndarray, bin_edges: np.ndarray,
) -> np.ndarray:
    """Apply the corresponding T to probs, per uncertainty bin.

    Each sample is binned by its own entropy and temperature-scaled with that bin's T.
    """
    ent = predictive_entropy(probs)
    bin_idx = assign_bins(ent, bin_edges)
    out = probs.copy()
    for b in range(len(T_per_bin)):
        mask = bin_idx == b
        if not mask.any():
            continue
        out[mask] = apply_temperature(probs[mask], T_per_bin[b])
    return out


def apply_global_T(probs: np.ndarray, T: float) -> np.ndarray:
    """Apply global T."""
    return apply_temperature(probs, T)


# =====================================================================
# Single-experiment processing
# =====================================================================
def process_one(
    pair: str, arch: str, seed: int, save_dir: Path,
    cache_dir: Optional[Path], device: torch.device,
    d_model: int = 64, n_layers: int = 2,
) -> dict:
    """Process a single experiment, returning distribution analysis + binned evaluation records.

    Returns:
        dict with keys:
            dist: dict (one row of temperature_distribution_analysis)
            binned: list[dict] (N_BINS rows of binned_temperature_exploratory)
            shift: list[dict] (shift-sensitivity rows, possibly empty)
    """
    source, target = pair.split("_")
    key = cache_key(pair, arch, seed)

    # ---------- load probs/labels (prefer cache) ----------
    cache = load_cache(cache_dir, pair, arch, seed)
    if cache is not None:
        cal_probs = cache["cal_probs"]
        cal_labels = cache["cal_labels"]
        id_probs = cache["id_probs"]
        id_labels = cache["id_labels"]
        ood_probs = cache["ood_probs"]
        ood_labels = cache["ood_labels"]
    else:
        model, _, _, num_classes = load_checkpoint(
            pair, arch, seed, save_dir, d_model=d_model, n_layers=n_layers
        )
        src_ds, tgt_ds, _, _, _, _ = build_datasets(pair, seed, limit=None)

        cal_loader = create_dataloader(src_ds["cal"], 64, shuffle=False, num_workers=0)
        id_loader = create_dataloader(src_ds["test"], 64, shuffle=False, num_workers=0)
        ood_loader = create_dataloader(tgt_ds["test"], 64, shuffle=False, num_workers=0)

        cal_ev = evaluate(model, cal_loader, device, compute_calibration=False)
        id_ev = evaluate(model, id_loader, device, compute_calibration=False)
        ood_ev = evaluate(model, ood_loader, device, compute_calibration=False)

        cal_probs, cal_labels = cal_ev["probs"], cal_ev["labels"]
        id_probs, id_labels = id_ev["probs"], id_ev["labels"]
        ood_probs, ood_labels = ood_ev["probs"], ood_ev["labels"]

        if cache_dir is not None:
            save_cache(cache_dir, pair, arch, seed, {
                "cal_probs": cal_probs, "cal_labels": cal_labels,
                "id_probs": id_probs, "id_labels": id_labels,
                "ood_probs": ood_probs, "ood_labels": ood_labels,
            })
        del model
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    # ---------- 1. Global T fit ----------
    T_global, fit_status = fit_global_T(cal_probs, cal_labels)
    cal_ent = predictive_entropy(cal_probs)

    # global-T Brier reliability on ID / OOD
    id_rel_raw = brier_reliability_top(id_probs, id_labels)
    id_rel_global = brier_reliability_top(apply_global_T(id_probs, T_global), id_labels)
    ood_rel_raw = brier_reliability_top(ood_probs, ood_labels)
    ood_rel_global = brier_reliability_top(apply_global_T(ood_probs, T_global), ood_labels)

    dist_record = {
        "pair": pair, "arch": arch, "seed": seed,
        "source": source, "target": target,
        "T_global": T_global, "fit_status": fit_status,
        "n_cal": int(len(cal_probs)),
        "n_id": int(len(id_probs)),
        "n_ood": int(len(ood_probs)),
        "cal_entropy_mean": float(cal_ent.mean()),
        "cal_entropy_std": float(cal_ent.std()),
        "id_rel_raw": id_rel_raw,
        "id_rel_global_T": id_rel_global,
        "id_delta_rel_global": id_rel_global - id_rel_raw,
        "ood_rel_raw": ood_rel_raw,
        "ood_rel_global_T": ood_rel_global,
        "ood_delta_rel_global": ood_rel_global - ood_rel_raw,
    }

    # ---------- 2. Binned T evaluation ----------
    T_per_bin, bin_edges, bin_records = fit_binned_T(cal_probs, cal_labels, n_bins=N_BINS)

    id_probs_binned = apply_binned_T(id_probs, T_per_bin, bin_edges)
    ood_probs_binned = apply_binned_T(ood_probs, T_per_bin, bin_edges)

    # global binned-T Brier reliability (computed once over the whole test set, not a per-bin mean)
    # Core comparison: global Brier reliability of binned-T vs global-T.
    # Note: per-bin mean != global Brier reliability (Brier reliability is weighted and
    # non-linear, so non-additive); the global value is used instead.
    id_rel_binned_global = brier_reliability_top(id_probs_binned, id_labels)
    ood_rel_binned_global = brier_reliability_top(ood_probs_binned, ood_labels)
    dist_record["id_rel_binned_T"] = id_rel_binned_global
    dist_record["ood_rel_binned_T"] = ood_rel_binned_global
    dist_record["id_delta_rel_binned_vs_global"] = id_rel_binned_global - id_rel_global
    dist_record["ood_delta_rel_binned_vs_global"] = ood_rel_binned_global - ood_rel_global

    binned_records = []
    for rec in bin_records:
        b = rec["bin_idx"]
        id_ent = predictive_entropy(id_probs)
        ood_ent = predictive_entropy(ood_probs)
        id_bin_mask = assign_bins(id_ent, bin_edges) == b
        ood_bin_mask = assign_bins(ood_ent, bin_edges) == b

        # per-bin Brier reliability (on in-bin samples)
        if id_bin_mask.sum() > 0:
            id_rel_raw_b = brier_reliability_top(id_probs[id_bin_mask], id_labels[id_bin_mask])
            id_rel_binned_b = brier_reliability_top(
                id_probs_binned[id_bin_mask], id_labels[id_bin_mask])
            id_rel_global_b = brier_reliability_top(
                apply_global_T(id_probs[id_bin_mask], T_global), id_labels[id_bin_mask])
        else:
            id_rel_raw_b = id_rel_binned_b = id_rel_global_b = float("nan")

        if ood_bin_mask.sum() > 0:
            ood_rel_raw_b = brier_reliability_top(ood_probs[ood_bin_mask], ood_labels[ood_bin_mask])
            ood_rel_binned_b = brier_reliability_top(
                ood_probs_binned[ood_bin_mask], ood_labels[ood_bin_mask])
            ood_rel_global_b = brier_reliability_top(
                apply_global_T(ood_probs[ood_bin_mask], T_global), ood_labels[ood_bin_mask])
        else:
            ood_rel_raw_b = ood_rel_binned_b = ood_rel_global_b = float("nan")

        binned_records.append({
            "pair": pair, "arch": arch, "seed": seed,
            "bin_idx": b,
            "n_cal_bin": rec["n_cal_bin"],
            "n_id_bin": int(id_bin_mask.sum()),
            "n_ood_bin": int(ood_bin_mask.sum()),
            "T_bin": rec["T_bin"],
            "T_global": T_global,
            "bin_entropy_lo": rec["entropy_lo"],
            "bin_entropy_hi": rec["entropy_hi"],
            "bin_entropy_mean": rec["entropy_mean"],
            "id_rel_raw": id_rel_raw_b,
            "id_rel_binned_T": id_rel_binned_b,
            "id_rel_global_T": id_rel_global_b,
            "id_delta_binned_vs_raw": id_rel_binned_b - id_rel_raw_b,
            "id_delta_global_vs_raw": id_rel_global_b - id_rel_raw_b,
            "id_delta_binned_vs_global": id_rel_binned_b - id_rel_global_b,
            "ood_rel_raw": ood_rel_raw_b,
            "ood_rel_binned_T": ood_rel_binned_b,
            "ood_rel_global_T": ood_rel_global_b,
            "ood_delta_binned_vs_raw": ood_rel_binned_b - ood_rel_raw_b,
            "ood_delta_global_vs_raw": ood_rel_global_b - ood_rel_raw_b,
            "ood_delta_binned_vs_global": ood_rel_binned_b - ood_rel_global_b,
            "fit_status": rec["status"],
        })

    # ---------- 3. Shift sensitivity (if l2_shift data exists) ----------
    shift_records = []
    # shift sensitivity: re-fit T per shift level
    # Note: shift is applied to cal, then forward inference yields cal_shift probs, then T is fit
    # (strict semantics: T(shift) = argmin NLL(cal_shift; T)). This characterizes how
    # the calibration temperature responds to input drift. To avoid reloading the model
    # on cache hits, the shift sensitivity is handled by a separate function below.
    return {"dist": dist_record, "binned": binned_records, "shift": shift_records}


def process_shift_sensitivity(
    pair: str, arch: str, seed: int, save_dir: Path,
    device: torch.device, shifts: list,
    d_model: int = 64, n_layers: int = 2,
) -> list:
    """Shift sensitivity: for each L2 shift level, fit T on cal_shift, returning T(shift) records.

    Semantics: apply shift to cal signals -> forward through model to get cal_shift_probs
    -> fit T_shift. This characterizes the calibration temperature's sensitivity to input
    distribution drift.
    """
    try:
        model, _, _, num_classes = load_checkpoint(
            pair, arch, seed, save_dir, d_model=d_model, n_layers=n_layers
        )
        src_ds, tgt_ds, _, _, _, _ = build_datasets(pair, seed, limit=None)
    except FileNotFoundError:
        return []

    records = []
    # baseline T (no shift)
    try:
        cal_loader = create_dataloader(src_ds["cal"], 64, shuffle=False, num_workers=0)
        cal_ev = evaluate(model, cal_loader, device, compute_calibration=False)
        cal_probs_base = cal_ev["probs"]
        cal_labels_base = cal_ev["labels"]
        T_base, status_base = fit_global_T(cal_probs_base, cal_labels_base)
    except Exception as e:
        T_base, status_base = float("nan"), f"fail:{type(e).__name__}"

    records.append({
        "pair": pair, "arch": arch, "seed": seed,
        "shift_name": "baseline",
        "shift_type": "none",
        "T_shift": T_base,
        "T_relative": 1.0,
        "cal_entropy_mean": float(predictive_entropy(cal_probs_base).mean())
            if status_base == "ok" else float("nan"),
        "n_cal": int(len(cal_probs_base)) if status_base == "ok" else 0,
        "fit_status": status_base,
    })

    for shift in shifts:
        try:
            cal_probs_s, cal_labels_s = shifted_probs_labels(
                model, src_ds["cal"], shift, device,
                pair_id=pair, arch=arch, train_seed=seed,
            )
            T_s, status_s = fit_global_T(cal_probs_s, cal_labels_s)
            ent_mean = float(predictive_entropy(cal_probs_s).mean())
            records.append({
                "pair": pair, "arch": arch, "seed": seed,
                "shift_name": shift["name"],
                "shift_type": shift["type"],
                "T_shift": T_s,
                "T_relative": T_s / T_base if T_base > 0 else float("nan"),
                "cal_entropy_mean": ent_mean,
                "n_cal": int(len(cal_probs_s)),
                "fit_status": status_s,
            })
        except Exception as e:
            records.append({
                "pair": pair, "arch": arch, "seed": seed,
                "shift_name": shift["name"],
                "shift_type": shift["type"],
                "T_shift": float("nan"),
                "T_relative": float("nan"),
                "cal_entropy_mean": float("nan"),
                "n_cal": 0,
                "fit_status": f"fail:{type(e).__name__}",
            })

    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    return records


# =====================================================================
# Distribution summary statistics
# =====================================================================
def summarize_distribution(dist_records: list) -> list:
    """Summarize statistics over the T_global distribution, returning extra rows (arch=SUMMARY)."""
    if not dist_records:
        return []
    Ts = np.array([r["T_global"] for r in dist_records if r["fit_status"] == "ok"])
    if len(Ts) == 0:
        return []

    summary_rows = []
    # global summary
    summary_rows.append({
        "pair": "ALL", "arch": "SUMMARY", "seed": -1,
        "source": "", "target": "",
        "T_global": float(np.mean(Ts)),
        "fit_status": f"n={len(Ts)},mean",
        "n_cal": int(np.median([r["n_cal"] for r in dist_records])),
        "n_id": int(np.median([r["n_id"] for r in dist_records])),
        "n_ood": int(np.median([r["n_ood"] for r in dist_records])),
        "cal_entropy_mean": float(np.mean([r["cal_entropy_mean"] for r in dist_records])),
        "cal_entropy_std": float(np.mean([r["cal_entropy_std"] for r in dist_records])),
        "id_rel_raw": float("nan"),
        "id_rel_global_T": float("nan"),
        "id_delta_rel_global": float("nan"),
        "id_rel_binned_T": float("nan"),
        "id_delta_rel_binned_vs_global": float("nan"),
        "ood_rel_raw": float("nan"),
        "ood_rel_global_T": float("nan"),
        "ood_delta_rel_global": float("nan"),
        "ood_rel_binned_T": float("nan"),
        "ood_delta_rel_binned_vs_global": float("nan"),
    })

    # cross-direction summary
    for pair in ALL_PAIRS:
        pair_Ts = [r["T_global"] for r in dist_records
                   if r["pair"] == pair and r["fit_status"] == "ok"]
        if len(pair_Ts) >= 2:
            summary_rows.append({
                "pair": pair, "arch": "PAIR_MEAN", "seed": -1,
                "source": "", "target": "",
                "T_global": float(np.mean(pair_Ts)),
                "fit_status": f"n={len(pair_Ts)},pair_mean",
                "n_cal": 0, "n_id": 0, "n_ood": 0,
                "cal_entropy_mean": float("nan"), "cal_entropy_std": float("nan"),
                "id_rel_raw": float("nan"), "id_rel_global_T": float("nan"),
                "id_delta_rel_global": float("nan"),
                "id_rel_binned_T": float("nan"), "id_delta_rel_binned_vs_global": float("nan"),
                "ood_rel_raw": float("nan"), "ood_rel_global_T": float("nan"),
                "ood_delta_rel_global": float("nan"),
                "ood_rel_binned_T": float("nan"), "ood_delta_rel_binned_vs_global": float("nan"),
            })

    # cross-architecture summary
    for arch in ALL_ARCHS:
        arch_Ts = [r["T_global"] for r in dist_records
                   if r["arch"] == arch and r["fit_status"] == "ok"]
        if len(arch_Ts) >= 2:
            summary_rows.append({
                "pair": "ALL", "arch": f"{arch}_MEAN", "seed": -1,
                "source": "", "target": "",
                "T_global": float(np.mean(arch_Ts)),
                "fit_status": f"n={len(arch_Ts)},arch_mean",
                "n_cal": 0, "n_id": 0, "n_ood": 0,
                "cal_entropy_mean": float("nan"), "cal_entropy_std": float("nan"),
                "id_rel_raw": float("nan"), "id_rel_global_T": float("nan"),
                "id_delta_rel_global": float("nan"),
                "id_rel_binned_T": float("nan"), "id_delta_rel_binned_vs_global": float("nan"),
                "ood_rel_raw": float("nan"), "ood_rel_global_T": float("nan"),
                "ood_delta_rel_global": float("nan"),
                "ood_rel_binned_T": float("nan"), "ood_delta_rel_binned_vs_global": float("nan"),
            })

    # distribution statistic row
    summary_rows.append({
        "pair": "ALL", "arch": "DIST_STATS", "seed": -1,
        "source": "", "target": "",
        "T_global": float(np.std(Ts)),
        "fit_status": f"n={len(Ts)},std",
        "n_cal": int(np.median(Ts)),
        "n_id": float(np.percentile(Ts, 25)),
        "n_ood": float(np.percentile(Ts, 75)),
        "cal_entropy_mean": float(np.median(Ts)),
        "cal_entropy_std": float(Ts.min()),
        "id_rel_raw": float(Ts.max()),
        "id_rel_global_T": float(np.percentile(Ts, 5)),
        "id_delta_rel_global": float(np.percentile(Ts, 95)),
        "id_rel_binned_T": float("nan"),
        "id_delta_rel_binned_vs_global": float("nan"),
        "ood_rel_raw": float(np.mean(np.abs(Ts - 1.0))),  # average deviation from 1.0
        "ood_rel_global_T": float("nan"),
        "ood_delta_rel_global": float("nan"),
        "ood_rel_binned_T": float("nan"),
        "ood_delta_rel_binned_vs_global": float("nan"),
    })

    return summary_rows


# =====================================================================
# CSV writing
# =====================================================================
def write_csv(records: list, path: Path, fieldnames: list) -> None:
    """Write CSV (no pandas dependency, to avoid environment issues)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            writer.writerow(r)


def write_dist_csv(dist_records: list, summary_rows: list, path: Path) -> None:
    fieldnames = [
        "pair", "arch", "seed", "source", "target",
        "T_global", "fit_status",
        "n_cal", "n_id", "n_ood",
        "cal_entropy_mean", "cal_entropy_std",
        "id_rel_raw", "id_rel_global_T", "id_delta_rel_global",
        "id_rel_binned_T", "id_delta_rel_binned_vs_global",
        "ood_rel_raw", "ood_rel_global_T", "ood_delta_rel_global",
        "ood_rel_binned_T", "ood_delta_rel_binned_vs_global",
    ]
    write_csv(dist_records + summary_rows, path, fieldnames)


def write_binned_csv(binned_records: list, path: Path) -> None:
    fieldnames = [
        "pair", "arch", "seed", "bin_idx",
        "n_cal_bin", "n_id_bin", "n_ood_bin",
        "T_bin", "T_global",
        "bin_entropy_lo", "bin_entropy_hi", "bin_entropy_mean",
        "id_rel_raw", "id_rel_binned_T", "id_rel_global_T",
        "id_delta_binned_vs_raw", "id_delta_global_vs_raw", "id_delta_binned_vs_global",
        "ood_rel_raw", "ood_rel_binned_T", "ood_rel_global_T",
        "ood_delta_binned_vs_raw", "ood_delta_global_vs_raw", "ood_delta_binned_vs_global",
        "fit_status",
    ]
    write_csv(binned_records, path, fieldnames)


def write_shift_csv(shift_records: list, path: Path) -> None:
    fieldnames = [
        "pair", "arch", "seed", "shift_name", "shift_type",
        "T_shift", "T_relative", "cal_entropy_mean", "n_cal", "fit_status",
    ]
    write_csv(shift_records, path, fieldnames)


# =====================================================================
# Main flow
# =====================================================================
def discover_experiments(save_dir: Path, pairs: list, archs: list, seeds: list) -> list:
    """Discover experiments that actually exist (checkpoint present)."""
    exps = []
    for pair in pairs:
        for arch in archs:
            for seed in seeds:
                ckpt = save_dir / pair / arch / f"seed{seed}" / "best_model.pt"
                if ckpt.exists():
                    exps.append((pair, arch, seed))
    return exps


def main():
    global N_BINS
    ap = argparse.ArgumentParser(description="E4: temperature distribution + binned-temperature exploratory evaluation")
    ap.add_argument("--save-dir", default="checkpoints/transfer")
    ap.add_argument("--results-dir", default="results")
    ap.add_argument("--cache-dir", default=None,
                    help="probs cache directory (speeds up reruns, avoids reloading models)")
    ap.add_argument("--pairs", nargs="+", default=ALL_PAIRS)
    ap.add_argument("--archs", nargs="+", default=ALL_ARCHS)
    ap.add_argument("--seeds", nargs="+", type=int, default=ALL_SEEDS)
    ap.add_argument("--d-model", type=int, default=64)
    ap.add_argument("--n-layers", type=int, default=2)
    ap.add_argument("--n-bins", type=int, default=N_BINS,
                    help="number of bins for binned temperature (default 5 quintiles)")
    ap.add_argument("--skip-binned", action="store_true",
                    help="skip binned temperature evaluation")
    ap.add_argument("--skip-shift-sensitivity", action="store_true",
                    help="skip shift sensitivity (no l2_shift data, or speed up)")
    ap.add_argument("--shifts", nargs="+", default=None,
                    help="only run specified shift levels (e.g. fs250 noise12); default all")
    args = ap.parse_args()

    N_BINS = args.n_bins

    save_dir = _PROJECT_ROOT / args.save_dir
    results_dir = _PROJECT_ROOT / args.results_dir
    cache_dir = _PROJECT_ROOT / args.cache_dir if args.cache_dir else None
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # discover experiments
    exps = discover_experiments(save_dir, args.pairs, args.archs, args.seeds)
    print(f"Discovered {len(exps)} experiments (checkpoint present)")
    if not exps:
        print("No experiments to run, exiting.")
        return

    # L2 shifts
    all_shifts = get_l2_shifts()
    if args.shifts:
        shifts = [s for s in all_shifts if s["name"] in args.shifts]
    else:
        shifts = all_shifts

    # ---------- main loop ----------
    all_dist = []
    all_binned = []
    all_shift = []

    for i, (pair, arch, seed) in enumerate(exps, 1):
        print(f"\n[{i}/{len(exps)}] {pair}/{arch}/seed{seed}", flush=True)
        try:
            res = process_one(
                pair, arch, seed, save_dir, cache_dir, device,
                d_model=args.d_model, n_layers=args.n_layers,
            )
            all_dist.append(res["dist"])
            if not args.skip_binned:
                all_binned.extend(res["binned"])
            print(f"  T_global={res['dist']['T_global']:.4f} "
                  f"(status={res['dist']['fit_status']})", flush=True)
        except Exception as e:
            print(f"  [FAIL] {type(e).__name__}: {e}", flush=True)
            all_dist.append({
                "pair": pair, "arch": arch, "seed": seed,
                "source": pair.split("_")[0], "target": pair.split("_")[1],
                "T_global": float("nan"), "fit_status": f"fail:{type(e).__name__}",
                "n_cal": 0, "n_id": 0, "n_ood": 0,
                "cal_entropy_mean": float("nan"), "cal_entropy_std": float("nan"),
                "id_rel_raw": float("nan"), "id_rel_global_T": float("nan"),
                "id_delta_rel_global": float("nan"),
                "id_rel_binned_T": float("nan"), "id_delta_rel_binned_vs_global": float("nan"),
                "ood_rel_raw": float("nan"), "ood_rel_global_T": float("nan"),
                "ood_delta_rel_global": float("nan"),
                "ood_rel_binned_T": float("nan"), "ood_delta_rel_binned_vs_global": float("nan"),
            })

        # shift sensitivity (on demand, reloads model per experiment)
        if not args.skip_shift_sensitivity:
            try:
                shift_recs = process_shift_sensitivity(
                    pair, arch, seed, save_dir, device, shifts,
                    d_model=args.d_model, n_layers=args.n_layers,
                )
                all_shift.extend(shift_recs)
                if shift_recs:
                    T_base = shift_recs[0]["T_shift"]
                    print(f"  Shift sensitivity: T_baseline={T_base:.4f}, "
                          f"{len(shift_recs)-1} shift levels", flush=True)
            except Exception as e:
                print(f"  [SHIFT FAIL] {type(e).__name__}: {e}", flush=True)

    # ---------- summary + write CSV ----------
    summary_rows = summarize_distribution(all_dist)

    dist_path = results_dir / "temperature_distribution_analysis.csv"
    binned_path = results_dir / "binned_temperature_exploratory.csv"
    shift_path = results_dir / "temperature_shift_sensitivity.csv"

    write_dist_csv(all_dist, summary_rows, dist_path)
    print(f"\nDistribution analysis -> {dist_path} ({len(all_dist)} experiments + {len(summary_rows)} summary rows)")

    if not args.skip_binned and all_binned:
        write_binned_csv(all_binned, binned_path)
        print(f"Binned evaluation -> {binned_path} ({len(all_binned)} rows = {len(all_dist)} experiments x {N_BINS} bins)")

    if not args.skip_shift_sensitivity and all_shift:
        write_shift_csv(all_shift, shift_path)
        print(f"Shift sensitivity -> {shift_path} ({len(all_shift)} rows)")

    # ---------- console summary ----------
    print("\n" + "=" * 70)
    print("E4 exploratory evaluation summary")
    print("=" * 70)
    ok_Ts = [r["T_global"] for r in all_dist if r["fit_status"] == "ok"]
    if ok_Ts:
        Ts = np.array(ok_Ts)
        print(f"T_global distribution (n={len(Ts)}):")
        print(f"  mean={np.mean(Ts):.4f}  std={np.std(Ts):.4f}")
        print(f"  median={np.median(Ts):.4f}  IQR=[{np.percentile(Ts,25):.4f}, {np.percentile(Ts,75):.4f}]")
        print(f"  range=[{Ts.min():.4f}, {Ts.max():.4f}]")
        print(f"  mean|T-1|={np.mean(np.abs(Ts-1.0)):.4f}  (average deviation from identity)")

    # cross-direction variation
    print("\nCross-direction T variation:")
    for pair in args.pairs:
        pair_Ts = [r["T_global"] for r in all_dist
                   if r["pair"] == pair and r["fit_status"] == "ok"]
        if len(pair_Ts) >= 2:
            print(f"  {pair:<16} mean={np.mean(pair_Ts):.4f} std={np.std(pair_Ts):.4f} n={len(pair_Ts)}")

    # cross-architecture variation
    print("\nCross-architecture T variation:")
    for arch in args.archs:
        arch_Ts = [r["T_global"] for r in all_dist
                   if r["arch"] == arch and r["fit_status"] == "ok"]
        if len(arch_Ts) >= 2:
            print(f"  {arch:<14} mean={np.mean(arch_Ts):.4f} std={np.std(arch_Ts):.4f} n={len(arch_Ts)}")

    # Binned vs global summary (global Brier reliability, not per-bin mean)
    # Core comparison: global Brier reliability of binned-T vs global-T.
    # Note: per-bin mean != global Brier reliability (weighted, non-linear, non-additive),
    # so the global value is used.
    id_delta_global = [r.get("id_delta_rel_binned_vs_global", float("nan")) for r in all_dist
                       if np.isfinite(r.get("id_delta_rel_binned_vs_global", float("nan")))]
    ood_delta_global = [r.get("ood_delta_rel_binned_vs_global", float("nan")) for r in all_dist
                        if np.isfinite(r.get("ood_delta_rel_binned_vs_global", float("nan")))]
    if id_delta_global:
        print(f"\nBinned vs Global Brier reliability (ID, global, n={len(id_delta_global)}):")
        print(f"  mean delta_rel = {np.mean(id_delta_global):+.6f}  (negative = binned better)")
        print(f"  median delta_rel = {np.median(id_delta_global):+.6f}")
        n_better = int(np.sum(np.array(id_delta_global) < 0))
        print(f"  binned better: {n_better}/{len(id_delta_global)} experiments")
    if ood_delta_global:
        print(f"Binned vs Global Brier reliability (OOD, global, n={len(ood_delta_global)}):")
        print(f"  mean delta_rel = {np.mean(ood_delta_global):+.6f}  (negative = binned better)")
        print(f"  median delta_rel = {np.median(ood_delta_global):+.6f}")
        n_better = int(np.sum(np.array(ood_delta_global) < 0))
        print(f"  binned better: {n_better}/{len(ood_delta_global)} experiments")

    # shift sensitivity summary
    if not args.skip_shift_sensitivity and all_shift:
        print("\nShift sensitivity T(shift) summary:")
        for shift_name in ["baseline"] + [s["name"] for s in shifts]:
            recs = [r for r in all_shift if r["shift_name"] == shift_name
                    and r["fit_status"] == "ok"]
            if recs:
                T_vals = [r["T_shift"] for r in recs]
                print(f"  {shift_name:<10} mean={np.mean(T_vals):.4f} "
                      f"std={np.std(T_vals):.4f} n={len(T_vals)}")

    print("\n" + "=" * 70)
    print("This evaluation is exploratory and does not enter the primary test.")
    print("Methodological assumptions and limitations are documented in the module docstring.")
    print("=" * 70)


if __name__ == "__main__":
    main()
