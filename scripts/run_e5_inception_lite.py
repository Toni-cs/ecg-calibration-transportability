"""E5 experiment: InceptionTime-Lite training + cross-database transfer evaluation.

Experiment design (E5, preregistered protocol):
- Architecture: InceptionTime-Lite (3 blocks, n_filters=48, ~310K params)
- Training: 3 corpora x 5 seeds = 15 models
- Transfer evaluation: 6 directions x 5 seeds = 30 evaluations
  6 directions = 3 choose 2 permutations = {(ptbxl->chapman), (ptbxl->cpsc),
  (chapman->ptbxl), (chapman->cpsc), (cpsc->ptbxl), (cpsc->chapman)}
- Temperature scaling (TS) applied per transfer; report Brier reliability improvement
- Output: results/c3_inceptiontime_lite_30exp.csv

OOM fallback chain (4 levels, RTX 5060 8GB constraint):
  Level 1: n_filters 48->32 (params ~310K -> ~136K)
  Level 2: gradient checkpointing (use_checkpoint=True)
  Level 3: ResNet1D hyperparameter variants (depth 3/5/7, width 32/64/128)
  Level 4: honestly report "2 architecture families + BiMamba toy" (worst case, paper degradation statement)

Rationale (why InceptionTime-Lite counts as the 3rd architecture family):
  Architecture families differ by inductive bias, not depth. InceptionTime-Lite keeps
  the three key inductive biases of InceptionTime (multi-scale parallel conv + bottleneck +
  maxpool shortcut), orthogonal in feature extraction to ResNet1D (serial residual) and
  BiMamba (selective state space). 3 vs 6 blocks is a depth choice, not a family change.

  Key assumptions:
  H1 (multi-scale preserved): 3 blocks suffice to capture key ECG multi-scale features (P/QRS/T waves, 80-200ms)
  H2 (depth-calibration decoupling): 6->3 blocks mainly affects discriminative performance; effect on calibration transfer heterogeneity is second-order
  H3 (params-capacity monotonic): ~310K params suffice to avoid an underfitting degenerate solution
  H4 (BN stats stable): 3-block BN running stats converge stably at batch_size=16

  Applicable bounds:
  - 3 vs 6 blocks: original 6 blocks may be too deep at seq_len=1000 (no downsampling per block);
    3 blocks is an accuracy-efficiency tradeoff. If test acc lags other architectures by >5pp, report capacity shortfall.
  - Param upper bound: n_filters=64 (~555K) may OOM under RTX 5060 8GB.

Usage:
    # Full E5 (15 models + 30 transfers, GPU 30-45h)
    python scripts/run_e5_inception_lite.py

    # Smoke test (synthetic data, 2 epochs, 1 seed)
    python scripts/run_e5_inception_lite.py --smoke

    # Training only, no transfer
    python scripts/run_e5_inception_lite.py --no-transfer

    # OOM fallback Level 1+2 (reduce channels + gradient checkpointing)
    python scripts/run_e5_inception_lite.py --n-filters 32 --use-checkpoint
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.models.ecg_classifier import ECGClassifier  # noqa: E402
from src.models.inceptiontime_lite import (  # noqa: E402
    ECGInceptionTimeLite,
    build_inceptiontime_lite,
)
from src.utils.calibration import (  # noqa: E402
    benefit_inference,
    compute_all_metrics,
    fit_temperature,
    apply_temperature,
    smooth_ece,
)
from src.utils.calibration_methods import CALIBRATION_METHODS  # noqa: E402
from train import (  # noqa: E402
    set_seed,
    evaluate,
    train_model,
    create_dataloader,
    build_ptbxl_datasets,
    build_chapman_datasets,
    build_cpsc_datasets,
)
from src.data.mapping import SUBSPACE_CPSC, SUPERCLASSES  # noqa: E402


# ===========================================================================
# Experiment configuration
# ===========================================================================
ARCH_NAME = "inceptiontime_lite"
SEEDS = [42, 43, 44, 45, 46]
DATASETS = ["ptbxl", "chapman", "cpsc"]
# 6 transfer directions (3 choose 2 permutations)
TRANSFER_DIRECTIONS = [
    ("ptbxl", "chapman"),
    ("ptbxl", "cpsc"),
    ("chapman", "ptbxl"),
    ("chapman", "cpsc"),
    ("cpsc", "ptbxl"),
    ("cpsc", "chapman"),
]

DATASET_BUILDERS = {
    "ptbxl": build_ptbxl_datasets,
    "chapman": build_chapman_datasets,
    "cpsc": build_cpsc_datasets,
}
DATASET_NUM_CLASSES = {"ptbxl": 5, "chapman": 5, "cpsc": 4}
# Data directories (consistent with other experiments)
DATASET_DIRS = {
    "ptbxl": str(PROJECT_ROOT / "data" / "ptbxl_processed"),
    "chapman": str(PROJECT_ROOT / "data" / "chapman_processed_v2"),
    "cpsc": str(PROJECT_ROOT / "data" / "cpsc_processed"),
}

OUTPUT_CSV = PROJECT_ROOT / "results" / "c3_inceptiontime_lite_30exp.csv"

# Explicit n_bins constant aligned with run_e3_brier_dcr_ncv.py; avoids relying on defaults
N_BINS = 10


# ===========================================================================
# Transfer result dict schema
# ===========================================================================
# Single field list for every transfer-result dict. Early-return dicts (6 fields)
# and normal result dicts (20 fields) must share one schema, otherwise csv.DictWriter
# raises ValueError when mixing them. Field order matches the normal result dict and
# adds error/skipped for the early-return paths, so every construction site yields
# an identical schema.
TRANSFER_RESULT_FIELDS = [
    "source", "target", "seed", "arch",
    "num_classes", "n_ood",
    "ood_acc_raw", "fitted_T",
    "ood_ece_raw", "ood_ece_ts",
    "ood_brier_raw", "ood_brier_ts",
    "delta_ece", "delta_ece_ci_low", "delta_ece_ci_high",
    "brier_reliability_improvement",
    "n_dropped_cal", "n_dropped_ood",
    "truncated", "subspace_filtered",
    "error", "skipped",
]


def _make_transfer_result(
    source: str,
    target: str,
    seed: int,
    arch: str = ARCH_NAME,
    num_classes: int = 0,
    n_ood: int = 0,
    ood_acc_raw: float = float("nan"),
    fitted_T: float = float("nan"),
    ood_ece_raw: float = float("nan"),
    ood_ece_ts: float = float("nan"),
    ood_brier_raw: float = float("nan"),
    ood_brier_ts: float = float("nan"),
    delta_ece: float = float("nan"),
    delta_ece_ci_low: float = float("nan"),
    delta_ece_ci_high: float = float("nan"),
    brier_reliability_improvement: float = float("nan"),
    n_dropped_cal: int = 0,
    n_dropped_ood: int = 0,
    truncated: bool = False,
    subspace_filtered: bool = False,
    error: Optional[str] = None,
    skipped: bool = False,
) -> dict:
    """Build a fully-populated transfer-result dict.

    Every transfer-result dict shares one schema. Fields unavailable on the
    early-return / skipped / error paths are filled with safe defaults
    (0 / False / nan / None) so csv.DictWriter(fieldnames=TRANSFER_RESULT_FIELDS)
    always receives a dict with identical fields.
    """
    result = {
        "source": source,
        "target": target,
        "seed": seed,
        "arch": arch,
        "num_classes": num_classes,
        "n_ood": n_ood,
        "ood_acc_raw": ood_acc_raw,
        "fitted_T": fitted_T,
        "ood_ece_raw": ood_ece_raw,
        "ood_ece_ts": ood_ece_ts,
        "ood_brier_raw": ood_brier_raw,
        "ood_brier_ts": ood_brier_ts,
        "delta_ece": delta_ece,
        "delta_ece_ci_low": delta_ece_ci_low,
        "delta_ece_ci_high": delta_ece_ci_high,
        "brier_reliability_improvement": brier_reliability_improvement,
        "n_dropped_cal": n_dropped_cal,
        "n_dropped_ood": n_dropped_ood,
        "truncated": truncated,
        "subspace_filtered": subspace_filtered,
        "error": error,
        "skipped": skipped,
    }
    # Runtime schema-consistency check: any field add/remove triggers AssertionError.
    assert set(result.keys()) == set(TRANSFER_RESULT_FIELDS), \
        f"Schema mismatch: {set(result.keys())} != {set(TRANSFER_RESULT_FIELDS)}"
    return result


# ===========================================================================
# OOM detection and 4-level fallback
# ===========================================================================
def is_oom_error(e: Exception) -> bool:
    """Detect whether the exception is a CUDA OOM error."""
    msg = str(e).lower()
    return (
        "out of memory" in msg
        or "cuda oom" in msg
        or "memory allocation" in msg
    )


def report_oom_level(level: int, detail: str) -> None:
    """Report an OOM fallback level being triggered."""
    print(f"\n{'='*60}")
    print(f"[OOM fallback] Level {level} triggered: {detail}")
    print(f"{'='*60}\n")


def try_train_with_oom_fallback(
    train_fn,
    config: dict,
    device: torch.device,
    n_filters: int = 48,
    use_checkpoint: bool = False,
) -> Tuple[Any, dict]:
    """Training attempt with a 4-level OOM fallback chain.

    Level 1: n_filters 48->32 (~310K -> ~136K params)
    Level 2: gradient checkpointing
    Level 3: ResNet1D hyperparameter variants (depth 3/5/7, width 32/64/128)
    Level 4: honestly report "2 architecture families + BiMamba toy"
    """
    oom_log = {"level": 0, "actions": []}
    # First item (level=0) uses the user-supplied n_filters/use_checkpoint instead of
    # hardcoded {"n_filters": 48, "use_checkpoint": False}, which silently ignored CLI args.
    levels = [
        (0, {"n_filters": n_filters, "use_checkpoint": use_checkpoint},
         f"User-specified config (n_filters={n_filters}, checkpoint={use_checkpoint})"),
        (1, {"n_filters": 32, "use_checkpoint": False}, "Level 1: n_filters 48->32 (~136K params)"),
        (2, {"n_filters": 32, "use_checkpoint": True}, "Level 2: + gradient checkpointing"),
        (3, {"n_filters": 32, "use_checkpoint": True, "arch": "resnet1d", "depth": 3, "width": 32},
         "Level 3: degrade to ResNet1D variant (depth=3, width=32)"),
        (3, {"n_filters": 32, "use_checkpoint": True, "arch": "resnet1d", "depth": 5, "width": 64},
         "Level 3: ResNet1D variant (depth=5, width=64)"),
        (3, {"n_filters": 32, "use_checkpoint": True, "arch": "resnet1d", "depth": 7, "width": 128},
         "Level 3: ResNet1D variant (depth=7, width=128)"),
    ]

    for level, params, desc in levels:
        try:
            # Only report fallback for level>0; reporting level=0 would misleadingly
            # flag the user's own config as an OOM fallback.
            report_oom_level(level, desc) if level > 0 else None
            model, extra = train_fn(params, device)
            oom_log["level"] = level
            oom_log["actions"].append(desc)
            oom_log["final_config"] = params
            return model, {**extra, "oom_log": oom_log}
        except RuntimeError as e:
            if is_oom_error(e):
                print(f"[OOM] {desc} failed: {e}")
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
                oom_log["level"] = level
                oom_log["actions"].append(f"{desc} [FAILED: OOM]")
                continue
            raise
    # Level 4: all fallbacks failed
    report_oom_level(4, "Honestly report '2 architecture families + BiMamba toy' (paper degradation statement)")
    oom_log["level"] = 4
    oom_log["actions"].append("Level 4: honest degradation report")
    return None, {"oom_log": oom_log, "degraded": True}


# ===========================================================================
# Dataset construction (reuse train.py builders; handle subspace)
# ===========================================================================
def build_dataset(
    dataset: str, seed: int, limit: Optional[int] = None,
    subspace: Optional[tuple] = None,
) -> Tuple[dict, Any]:
    builder = DATASET_BUILDERS[dataset]
    if dataset == "cpsc":
        ds, clusters = builder(DATASET_DIRS[dataset], seed, limit=limit)
    elif subspace is not None:
        ds, clusters = builder(DATASET_DIRS[dataset], seed, limit=limit, subspace=subspace)
    else:
        ds, clusters = builder(DATASET_DIRS[dataset], seed, limit=limit)
    return ds, clusters


# ===========================================================================
# Model construction (InceptionTime-Lite, supports OOM-fallback params)
# ===========================================================================
def build_model(
    num_classes: int,
    n_filters: int = 48,
    use_checkpoint: bool = False,
    d_model: int = 64,
    dropout: float = 0.1,
    arch_override: Optional[str] = None,
    depth: Optional[int] = None,
    width: Optional[int] = None,
) -> ECGClassifier:
    """Build ECGClassifier (backbone=InceptionTime-Lite or OOM-fallback ResNet1D variant)."""
    if arch_override == "resnet1d":
        # Level 3 fallback: ResNet1D variant
        from src.models.baselines import ECGResNet1D
        # Use depth to control block_layers so genuinely different ResNet1D variants are built
        # (previously block_layers was computed but unused, so depth=3/5/7 all collapsed to the
        # default (2,2,2,2), effectively dead code equivalent to Level 4).
        # depth=3->(1,1,1) shallow/narrow, depth=5->(2,2,1) medium, depth=7->(2,2,2,1) deep/wide
        block_layers_map = {3: (1, 1, 1), 5: (2, 2, 1), 7: (2, 2, 2, 1)}
        block_layers = block_layers_map.get(depth, (2, 2, 2, 2))
        resnet_d_model = width or d_model
        # Build ECGClassifier (with AttentionPooling + classifier head), then swap the backbone
        # for an ECGResNet1D actually parameterized by depth/width
        model = ECGClassifier(
            in_channels=12, d_model=resnet_d_model, n_layers=2,
            num_classes=num_classes, dropout=dropout,
            backbone_type="resnet1d",
        )
        model.backbone = ECGResNet1D(
            in_channels=12, d_model=resnet_d_model,
            block_layers=block_layers, dropout=dropout,
        )
        return model
    # Default: InceptionTime-Lite
    model = ECGClassifier(
        in_channels=12, d_model=d_model, n_layers=3,
        num_classes=num_classes, dropout=dropout,
        backbone_type="inceptiontime_lite",
    )
    # If custom n_filters/use_checkpoint requested, rebuild backbone
    if n_filters != 48 or use_checkpoint:
        backbone = build_inceptiontime_lite(
            in_channels=12, d_model=d_model, n_filters=n_filters,
            bottleneck=n_filters, dropout=dropout, use_checkpoint=use_checkpoint,
        )
        model.backbone = backbone
    return model


# ===========================================================================
# Train a single model (1 corpus x 1 seed)
# ===========================================================================
def train_single(
    dataset: str,
    seed: int,
    args: argparse.Namespace,
    device: torch.device,
    n_filters: int = 48,
    use_checkpoint: bool = False,
    arch_override: Optional[str] = None,
    depth: Optional[int] = None,
    width: Optional[int] = None,
) -> Tuple[Optional[nn.Module], dict]:
    """Train a single InceptionTime-Lite model, return (model, info).

    arch_override/depth/width let the Level 3 ResNet1D variant build backbones with
    genuinely different depth/width instead of collapsing to the Level 4 default.
    - arch_override="resnet1d": build_model parameterizes ResNet1D by depth/width
    - depth controls residual block count: 3->(1,1,1), 5->(2,2,1), 7->(2,2,2,1) (see build_model)
    - width controls ResNet1D channel count (d_model)
    """
    set_seed(seed)
    num_classes = DATASET_NUM_CLASSES[dataset]
    subspace = SUBSPACE_CPSC if num_classes == 4 else None

    arch_display = arch_override if arch_override else ARCH_NAME
    print(f"\n{'='*60}")
    print(f"[Train] {dataset} seed={seed} arch={arch_display} n_filters={n_filters}"
          f"{' depth='+str(depth) if depth else ''}{' width='+str(width) if width else ''}")
    print(f"{'='*60}")

    # Build data
    try:
        ds, clusters_test = build_dataset(dataset, seed, limit=args.limit, subspace=subspace)
    except FileNotFoundError as e:
        print(f"[SKIP] dataset {dataset} not found: {e}")
        return None, {"error": str(e), "skipped": True}

    loaders = {
        k: create_dataloader(ds[k], args.batch_size, shuffle=(k == "train"),
                             drop_last=(k == "train"), num_workers=args.num_workers)
        for k in ("train", "val", "cal", "test")
    }

    # Build model
    # Pass arch_override/depth/width to build_model so the Level 3 ResNet1D variant
    # builds genuinely different backbones by depth/width.
    model = build_model(
        num_classes=num_classes, n_filters=n_filters,
        use_checkpoint=use_checkpoint, d_model=args.d_model, dropout=0.1,
        arch_override=arch_override, depth=depth, width=width,
    ).to(device)

    n_params = sum(p.numel() for p in model.parameters())
    print(f"[Model] params: {n_params:,} (target 200K-500K)")
    if n_params < 200_000:
        print(f"[WARN] params {n_params:,} below target lower bound 200K")
    elif n_params > 500_000:
        print(f"[WARN] params {n_params:,} above target upper bound 500K")

    # Training
    # Use dynamic arch_display (includes OOM-fallback ResNet1D tag) for run_dir so
    # checkpoints of different architectures do not overwrite each other.
    run_dir = Path(args.save_dir) / dataset / arch_display / f"seed{seed}"
    run_dir.mkdir(parents=True, exist_ok=True)
    cfg = {
        "epochs": args.epochs, "lr": args.lr, "lr_min": 1e-6,
        "weight_decay": 1e-4, "patience": args.patience, "save_dir": str(run_dir),
    }
    # --resume: load existing checkpoint and skip training
    ckpt_file = run_dir / "best_model.pt"
    if getattr(args, 'resume', False) and ckpt_file.exists():
        print(f"[RESUME] attempting to load checkpoint: {ckpt_file}")
        try:
            checkpoint = torch.load(ckpt_file, weights_only=False, map_location=device)
            # Support different checkpoint formats
            if isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
                model.load_state_dict(checkpoint['model_state_dict'])
            elif isinstance(checkpoint, dict) and 'state_dict' in checkpoint:
                model.load_state_dict(checkpoint['state_dict'])
            else:
                model.load_state_dict(checkpoint)
            train_time = 0.0
            print(f"[RESUME] loaded checkpoint, skipping training")
        except (RuntimeError, KeyError) as e:
            print(f"[RESUME] load failed (possible architecture mismatch): {e}")
            print(f"[RESUME] falling back to normal training")
            t0 = time.time()
            model = train_model(model, loaders["train"], loaders["val"], cfg, device)
            train_time = time.time() - t0
    else:
        t0 = time.time()
        model = train_model(model, loaders["train"], loaders["val"], cfg, device)
        train_time = time.time() - t0

    # In-distribution (ID) evaluation on test set
    test_eval = evaluate(model, loaders["test"], device, compute_calibration=True)
    cal_eval = evaluate(model, loaders["cal"], device, compute_calibration=False)

    # TS calibration (fit on cal, report on test)
    one_hot_cal = np.eye(num_classes)[cal_eval["labels"]]
    T = fit_temperature(cal_eval["probs"], one_hot_cal)
    probs_ts = apply_temperature(test_eval["probs"], T)
    max_probs_raw = test_eval["probs"].max(axis=1)
    max_probs_ts = probs_ts.max(axis=1)
    correct_mask = (test_eval["probs"].argmax(axis=1) == test_eval["labels"]).astype(float)

    raw_metrics = compute_all_metrics(max_probs_raw, correct_mask, n_bins=N_BINS, n_bootstrap=1000)  # explicit n_bins
    ts_metrics = compute_all_metrics(max_probs_ts, correct_mask, n_bins=N_BINS, n_bootstrap=1000)  # explicit n_bins

    # info dict uses arch_display (includes OOM-fallback ResNet1D tag, defined above) and
    # adds arch_override/depth/width fields so the CSV arch column is accurate.
    info = {
        "dataset": dataset, "seed": seed, "arch": arch_display,
        "arch_override": arch_override,
        "depth": depth, "width": width,
        "n_params": n_params, "n_filters": n_filters,
        "use_checkpoint": use_checkpoint,
        "train_time_sec": train_time,
        "fitted_T": float(T),
        "id_acc_raw": float(test_eval["acc"]),
        "id_ece_raw": float(raw_metrics.get("ece", float("nan"))),
        "id_ece_ts": float(ts_metrics.get("ece", float("nan"))),
        "id_brier_raw": float(raw_metrics.get("brier_raw", float("nan"))),
        "id_brier_ts": float(ts_metrics.get("brier_raw", float("nan"))),
        "n_test": int(len(test_eval["labels"])),
    }
    print(f"[Result] acc={info['id_acc_raw']:.2f}% ECE(raw)={info['id_ece_raw']:.4f} "
          f"ECE(TS)={info['id_ece_ts']:.4f} Brier(raw)={info['id_brier_raw']:.4f} "
          f"Brier(TS)={info['id_brier_ts']:.4f} T={T:.3f} time={train_time:.0f}s")

    # Save checkpoint path for reuse in transfer evaluation
    ckpt_path = run_dir / "best_model.pt"
    info["ckpt_path"] = str(ckpt_path)
    info["model"] = model  # keep in memory for transfer evaluation (avoid reload)
    info["loaders"] = loaders
    info["cal_eval"] = cal_eval
    info["test_eval"] = test_eval
    info["clusters_test"] = clusters_test
    return model, info


# ===========================================================================
# Load trained model from checkpoint (--transfer-only mode)
# ===========================================================================
def load_and_evaluate_single(
    dataset: str,
    seed: int,
    args: argparse.Namespace,
    device: torch.device,
    n_filters: int = 48,
    use_checkpoint: bool = False,
) -> Tuple[Optional[nn.Module], dict]:
    """Load a trained model from checkpoint and re-evaluate cal/test sets (--transfer-only mode).

    Skips training, loads best_model.pt, and re-runs cal/test evaluation to obtain:
    - cal_eval (cal-set probs/labels needed for transfer TS calibration)
    - test_eval (ID metrics, fills the training-results table)
    Returns an info dict compatible with train_single so Phase 2 transfer reuses it seamlessly.
    """
    set_seed(seed)
    num_classes = DATASET_NUM_CLASSES[dataset]
    subspace = SUBSPACE_CPSC if num_classes == 4 else None

    print(f"\n{'='*60}")
    print(f"[Load] {dataset} seed={seed} arch={ARCH_NAME} n_filters={n_filters}")
    print(f"{'='*60}")

    # checkpoint path (matches train_single's run_dir)
    run_dir = Path(args.save_dir) / dataset / ARCH_NAME / f"seed{seed}"
    ckpt_path = run_dir / "best_model.pt"
    if not ckpt_path.exists():
        print(f"[SKIP] checkpoint not found: {ckpt_path}")
        return None, {"error": f"checkpoint not found: {ckpt_path}", "skipped": True}

    # Build data
    try:
        ds, clusters_test = build_dataset(dataset, seed, limit=args.limit, subspace=subspace)
    except FileNotFoundError as e:
        print(f"[SKIP] dataset {dataset} not found: {e}")
        return None, {"error": str(e), "skipped": True}

    loaders = {
        k: create_dataloader(ds[k], args.batch_size, shuffle=(k == "train"),
                             drop_last=(k == "train"), num_workers=args.num_workers)
        for k in ("train", "val", "cal", "test")
    }

    # Build model and load checkpoint
    model = build_model(
        num_classes=num_classes, n_filters=n_filters,
        use_checkpoint=use_checkpoint, d_model=args.d_model, dropout=0.1,
    ).to(device)

    checkpoint = torch.load(ckpt_path, weights_only=False, map_location=device)
    model.load_state_dict(checkpoint['model_state_dict'])
    model.eval()
    print(f"[Load complete] {ckpt_path} (epoch={checkpoint.get('epoch', '?')}, "
          f"val_acc={checkpoint.get('val_acc', '?')})")

    n_params = sum(p.numel() for p in model.parameters())

    # ID eval (test) + cal eval (needed for transfer TS calibration)
    test_eval = evaluate(model, loaders["test"], device, compute_calibration=True)
    cal_eval = evaluate(model, loaders["cal"], device, compute_calibration=False)

    # TS calibration (fit on cal, report on test)
    one_hot_cal = np.eye(num_classes)[cal_eval["labels"]]
    T = fit_temperature(cal_eval["probs"], one_hot_cal)
    probs_ts = apply_temperature(test_eval["probs"], T)
    max_probs_raw = test_eval["probs"].max(axis=1)
    max_probs_ts = probs_ts.max(axis=1)
    correct_mask = (test_eval["probs"].argmax(axis=1) == test_eval["labels"]).astype(float)

    raw_metrics = compute_all_metrics(max_probs_raw, correct_mask, n_bins=N_BINS, n_bootstrap=1000)  # explicit n_bins
    ts_metrics = compute_all_metrics(max_probs_ts, correct_mask, n_bins=N_BINS, n_bootstrap=1000)  # explicit n_bins

    info = {
        "dataset": dataset, "seed": seed, "arch": ARCH_NAME,
        "arch_override": None, "depth": None, "width": None,
        "n_params": n_params, "n_filters": n_filters,
        "use_checkpoint": use_checkpoint,
        "train_time_sec": 0.0,  # loaded from checkpoint, not trained
        "fitted_T": float(T),
        "id_acc_raw": float(test_eval["acc"]),
        "id_ece_raw": float(raw_metrics.get("ece", float("nan"))),
        "id_ece_ts": float(ts_metrics.get("ece", float("nan"))),
        "id_brier_raw": float(raw_metrics.get("brier_raw", float("nan"))),
        "id_brier_ts": float(ts_metrics.get("brier_raw", float("nan"))),
        "n_test": int(len(test_eval["labels"])),
    }
    print(f"[Result] acc={info['id_acc_raw']:.2f}% ECE(raw)={info['id_ece_raw']:.4f} "
          f"ECE(TS)={info['id_ece_ts']:.4f} T={T:.3f} (loaded from checkpoint)")

    info["ckpt_path"] = str(ckpt_path)
    info["model"] = model
    info["loaders"] = loaders
    info["cal_eval"] = cal_eval
    info["test_eval"] = test_eval
    info["clusters_test"] = clusters_test
    return model, info


# ===========================================================================
# Transfer evaluation (1 direction x 1 seed)
# ===========================================================================
def eval_transfer_pair(
    source: str,
    target: str,
    seed: int,
    source_info: dict,
    args: argparse.Namespace,
    device: torch.device,
) -> dict:
    """Cross-database transfer evaluation: source model -> target test, TS calibration + Brier reliability improvement."""
    model = source_info["model"]
    cal_eval = source_info["cal_eval"]
    cal_probs = cal_eval["probs"]
    cal_labels = cal_eval["labels"]

    num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
    subspace = SUBSPACE_CPSC if num_classes == 4 else None

    print(f"\n[Transfer] {source}->{target} seed={seed}")
    try:
        tgt_ds, tgt_clusters = build_dataset(target, seed, limit=args.limit, subspace=subspace)
    except FileNotFoundError as e:
        print(f"[SKIP] target dataset {target} not found: {e}")
        # Use unified schema and supply arch (the original dict had only 5 fields, missing arch).
        # Also pass num_classes/subspace_filtered so the early-return dict is semantically
        # consistent with the normal result dict (num_classes = min classes of source/target;
        # subspace_filtered reflects whether 5->4 subspace filtering was triggered).
        _fnf_num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
        return _make_transfer_result(
            source=source, target=target, seed=seed,
            arch=source_info.get("arch", ARCH_NAME),
            num_classes=_fnf_num_classes,
            subspace_filtered=bool(_fnf_num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
            error=str(e), skipped=True,
        )

    tgt_loader = create_dataloader(tgt_ds["test"], args.batch_size, shuffle=False,
                                   num_workers=args.num_workers)
    tgt_eval = evaluate(model, tgt_loader, device, compute_calibration=False)
    ood_probs = tgt_eval["probs"]
    ood_labels = tgt_eval["labels"]

    # When a 5-class source maps to a 4-class target, cal_labels/ood_labels may contain
    # labels >= num_classes, causing IndexError in np.eye(num_classes)[cal_labels].
    # Drop labels and probability columns beyond num_classes to keep probs and labels aligned.
    n_dropped_cal = int((cal_labels >= num_classes).sum())
    n_dropped_ood = int((ood_labels >= num_classes).sum())
    if n_dropped_cal > 0 or n_dropped_ood > 0:
        print(f"[WARN] {source}->{target} seed={seed}: dropped "
              f"{n_dropped_cal} cal + {n_dropped_ood} ood samples "
              f"(label >= num_classes={num_classes})")
    cal_keep = cal_labels < num_classes
    ood_keep = ood_labels < num_classes
    cal_labels = cal_labels[cal_keep]
    cal_probs = cal_probs[cal_keep][:, :num_classes]
    ood_labels = ood_labels[ood_keep]
    ood_probs = ood_probs[ood_keep][:, :num_classes]
    # Truncate tgt_clusters in sync; otherwise benefit_inference's cluster bootstrap raises
    # IndexError because tgt_clusters length != ood_probs row count.
    tgt_clusters = tgt_clusters[ood_keep]
    # Renormalize probabilities after truncation (dropped-class probability mass removed)
    # After truncation a row may become all-zero; naive renormalization yields NaN (0/0).
    # Detect and drop all-zero rows to avoid NaN contaminating later TS fit and metrics.
    cal_row_sums = cal_probs.sum(axis=1, keepdims=True)
    cal_zero_rows = (cal_row_sums.flatten() == 0)
    if cal_zero_rows.any():
        print(f"[WARN] {source}->{target} seed={seed}: {cal_zero_rows.sum()} cal samples all-zero after truncation, dropped")
        # Accumulate all-zero row count into n_dropped_cal to keep log and stats fields consistent.
        n_dropped_cal += int(cal_zero_rows.sum())
        cal_probs = cal_probs[~cal_zero_rows]
        cal_labels = cal_labels[~cal_zero_rows]
        cal_row_sums = cal_probs.sum(axis=1, keepdims=True)
    cal_probs = cal_probs / cal_row_sums

    ood_row_sums = ood_probs.sum(axis=1, keepdims=True)
    ood_zero_rows = (ood_row_sums.flatten() == 0)
    if ood_zero_rows.any():
        print(f"[WARN] {source}->{target} seed={seed}: {ood_zero_rows.sum()} ood samples all-zero after truncation, dropped")
        # Accumulate all-zero row count into n_dropped_ood (symmetric with cal side) so the
        # result dict's truncated field reflects all drop sources.
        n_dropped_ood += int(ood_zero_rows.sum())
        ood_probs = ood_probs[~ood_zero_rows]
        ood_labels = ood_labels[~ood_zero_rows]
        # Also drop tgt_clusters rows corresponding to all-zero rows to keep lengths aligned.
        tgt_clusters = tgt_clusters[~ood_zero_rows]
        ood_row_sums = ood_probs.sum(axis=1, keepdims=True)
    ood_probs = ood_probs / ood_row_sums

    # After truncation + all-zero drops, cal/ood may be empty; without an early return,
    # fit_temperature returns nan and silently propagates into later metrics.
    if len(cal_probs) == 0:
        print(f"[WARN] {source}->{target} seed={seed}: cal set empty after truncation, skipping TS calibration")
        # Use unified schema with arch from source_info and supply truncation stats.
        # Pass n_ood reflecting the actual ood sample count (cal empty does not imply ood
        # empty; cal/ood are truncated independently, so ood_probs may be non-empty here).
        return _make_transfer_result(
            source=source, target=target, seed=seed,
            arch=source_info.get("arch", ARCH_NAME),
            num_classes=num_classes,
            n_ood=int(len(ood_probs)),
            n_dropped_cal=int(n_dropped_cal), n_dropped_ood=int(n_dropped_ood),
            truncated=True,
            subspace_filtered=bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
            error="cal set empty after truncation", skipped=True,
        )
    if len(ood_probs) == 0:
        print(f"[WARN] {source}->{target} seed={seed}: ood set empty after truncation, skipping transfer evaluation")
        # Use unified schema with arch from source_info and supply truncation stats.
        # Pass n_ood reflecting the actual ood sample count (symmetric with the cal-empty path
        # above; pass n_ood=int(len(ood_probs)) explicitly instead of relying on the default 0,
        # which would mask the real count and cause silent errors).
        return _make_transfer_result(
            source=source, target=target, seed=seed,
            arch=source_info.get("arch", ARCH_NAME),
            num_classes=num_classes,
            n_ood=int(len(ood_probs)),
            n_dropped_cal=int(n_dropped_cal), n_dropped_ood=int(n_dropped_ood),
            truncated=True,
            subspace_filtered=bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
            error="ood set empty after truncation", skipped=True,
        )

    # TS calibration (fit on source cal -> apply to target test, zero-shot transfer)
    one_hot_cal = np.eye(num_classes)[cal_labels]
    T = fit_temperature(cal_probs, one_hot_cal)
    ood_probs_ts = apply_temperature(ood_probs, T)

    max_probs_raw = ood_probs.max(axis=1)
    max_probs_ts = ood_probs_ts.max(axis=1)
    correct_mask = (ood_probs.argmax(axis=1) == ood_labels).astype(float)

    raw_metrics = compute_all_metrics(max_probs_raw, correct_mask, n_bins=N_BINS, n_bootstrap=1000)  # explicit n_bins
    ts_metrics = compute_all_metrics(max_probs_ts, correct_mask, n_bins=N_BINS, n_bootstrap=1000)  # explicit n_bins

    # Brier reliability improvement (primary endpoint: the reliability term of the
    # post-TS Brier decomposition).
    # Brier = uncertainty - resolution + reliability (Murphy decomposition).
    # reliability gain = reliability_raw - reliability_ts (positive = calibration effective).
    brier_raw = raw_metrics.get("brier_raw", float("nan"))
    brier_ts = ts_metrics.get("brier_raw", float("nan"))
    ece_raw = raw_metrics.get("ece", float("nan"))
    ece_ts = ts_metrics.get("ece", float("nan"))

    # benefit_inference paired bootstrap (CI for ΔECE)
    rng = np.random.default_rng(seed)
    try:
        benefit = benefit_inference(
            max_probs_raw, max_probs_ts, correct_mask,
            metric=smooth_ece, n_bootstrap=min(args.bootstrap, 2000),
            rng=rng, clusters=tgt_clusters,
        )
        delta_ece = float(benefit["benefit"])
        delta_ece_ci = [float(benefit["benefit_ci"][0]), float(benefit["benefit_ci"][1])]
    except Exception as e:
        print(f"[WARN] benefit_inference failed: {e}")
        delta_ece = float(ece_raw - ece_ts)
        delta_ece_ci = [float("nan"), float("nan")]

    # Use unified schema and arch from source_info.get("arch", ARCH_NAME) instead of the
    # hardcoded constant, so the transfer CSV arch column reflects the source model's actual
    # architecture (including any OOM-fallback ResNet1D tag), not the global constant.
    result = _make_transfer_result(
        source=source, target=target, seed=seed,
        arch=source_info.get("arch", ARCH_NAME),
        num_classes=num_classes,
        n_ood=int(len(ood_probs)),
        ood_acc_raw=float((ood_probs.argmax(1) == ood_labels).mean() * 100),
        fitted_T=float(T),
        ood_ece_raw=float(ece_raw),
        ood_ece_ts=float(ece_ts),
        ood_brier_raw=float(brier_raw),
        ood_brier_ts=float(brier_ts),
        delta_ece=delta_ece,
        delta_ece_ci_low=delta_ece_ci[0],
        delta_ece_ci_high=delta_ece_ci[1],
        brier_reliability_improvement=float(brier_raw - brier_ts),
        # Truncation stats for downstream analysis to track subspace filtering and dropped samples.
        n_dropped_cal=int(n_dropped_cal),
        n_dropped_ood=int(n_dropped_ood),
        truncated=bool((n_dropped_cal + n_dropped_ood) > 0),
        subspace_filtered=bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
    )
    print(f"[Transfer result] {source}->{target} s{seed}: "
          f"acc={result['ood_acc_raw']:.2f}% "
          f"ECE(raw)={ece_raw:.4f}->ECE(TS)={ece_ts:.4f} "
          f"ΔECE={delta_ece:+.4f} "
          f"Brier(raw)={brier_raw:.4f}->Brier(TS)={brier_ts:.4f} "
          f"T={T:.3f}")
    return result


# ===========================================================================
# CSV output
# ===========================================================================
def write_csv(
    train_results: List[dict],
    transfer_results: List[dict],
    output_path: Path,
    oom_summary: Optional[dict] = None,
    arch_display: str = ARCH_NAME,
) -> None:
    """Write E5 results CSV (with a metadata header comment)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        # Header comment uses dynamic arch_display reflecting the actual architecture
        # (including any OOM-fallback ResNet1D tag) rather than the hardcoded ARCH_NAME.
        f.write(f"# E5 {arch_display} experiment (3 blocks, ~310K params)\n")
        f.write(f"# Architecture: {arch_display} (3 Inception modules, n_filters=48, bottleneck=48)\n")
        f.write(f"# Training experiments: {len(train_results)} (3 corpora x 5 seeds = 15)\n")
        f.write(f"# Transfer experiments: {len(transfer_results)} (6 directions x 5 seeds = 30)\n")
        f.write(f"# Seeds: {SEEDS}\n")
        f.write(f"# Corpora: {DATASETS}\n")
        f.write(f"# Transfer directions: {TRANSFER_DIRECTIONS}\n")
        if oom_summary:
            f.write(f"# OOM fallback triggered: Level {oom_summary.get('max_level', 0)}\n")
            f.write(f"# OOM-degraded experiments: {oom_summary.get('degraded_count', 0)}\n")
        f.write(f"# Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

        # Training results table
        f.write("## Training results (15 models)\n")
        if train_results:
            writer = csv.DictWriter(f, fieldnames=list(train_results[0].keys()))
            writer.writeheader()
            for r in train_results:
                # Drop non-serializable fields
                row = {k: v for k, v in r.items()
                       if k not in ("model", "loaders", "cal_eval", "test_eval", "clusters_test")}
                writer.writerow(row)
        f.write("\n")

        # Transfer results table
        f.write("## Transfer evaluation results (30 experiments)\n")
        if transfer_results:
            # Use the unified TRANSFER_RESULT_FIELDS as fieldnames and set extrasaction="ignore"
            # to tolerate any unexpected extra fields, avoiding ValueError from mixed schemas.
            writer = csv.DictWriter(
                f, fieldnames=TRANSFER_RESULT_FIELDS, extrasaction="ignore",
            )
            writer.writeheader()
            for r in transfer_results:
                writer.writerow(r)

    print(f"\n[Output] CSV written: {output_path}")


# ===========================================================================
# Main flow
# ===========================================================================
def main():
    ap = argparse.ArgumentParser(description="E5: InceptionTime-Lite training + cross-database transfer evaluation")
    # Training params
    ap.add_argument("--epochs", type=int, default=50, help="number of training epochs")
    ap.add_argument("--batch-size", type=int, default=16, help="batch size")
    ap.add_argument("--lr", type=float, default=1e-3, help="learning rate")
    ap.add_argument("--d-model", type=int, default=64, help="d_model")
    ap.add_argument("--patience", type=int, default=10, help="early stopping patience")
    ap.add_argument("--bootstrap", type=int, default=10000, help="bootstrap B (default 10000)")
    ap.add_argument("--num-workers", type=int, default=0, help="DataLoader workers")
    ap.add_argument("--save-dir", default="checkpoints/e5_inception_lite")
    ap.add_argument("--limit", type=int, default=None, help="smoke-test truncation")
    # OOM fallback
    ap.add_argument("--n-filters", type=int, default=48,
                    help="Inception n_filters (48=default ~310K, 32=OOM fallback Level 1 ~136K)")
    ap.add_argument("--use-checkpoint", action="store_true",
                    help="enable gradient checkpointing (OOM fallback Level 2)")
    # Experiment scope
    ap.add_argument("--no-transfer", action="store_true", help="train only, skip transfer")
    ap.add_argument("--transfer-only", action="store_true",
                    help="skip training, load existing model from checkpoint for transfer evaluation only (reuse best_model.pt)")
    ap.add_argument("--seeds", nargs="+", type=int, default=SEEDS, help="list of seeds")
    ap.add_argument("--datasets", nargs="+", default=DATASETS, help="list of corpora")
    # Smoke
    ap.add_argument("--smoke", action="store_true", help="smoke test (synthetic data, 2 epochs, 1 seed)")
    # Resume
    ap.add_argument("--resume", action="store_true",
                    help="resume from existing checkpoint, skip training into transfer evaluation")
    args = ap.parse_args()

    if args.smoke:
        # Smoke mode: only set training hyperparameters; seeds/datasets keep CLI values (all by default).
        # For a quick smoke run pass --seeds 42 --datasets ptbxl explicitly.
        args.epochs = 2
        args.limit = 240 if args.limit is None else args.limit
        args.bootstrap = 200
        print(f"[Smoke mode] epochs=2, limit={args.limit}, bootstrap=200, "
              f"seeds={args.seeds}, datasets={args.datasets}")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"\n{'#'*60}")
    print(f"# E5: InceptionTime-Lite training + cross-database transfer evaluation")
    print(f"# Architecture: {ARCH_NAME} (3 blocks, n_filters={args.n_filters}, "
          f"checkpoint={args.use_checkpoint})")
    print(f"# Device: {device}")
    print(f"# Seeds: {args.seeds}")
    print(f"# Corpora: {args.datasets}")
    print(f"# Transfer directions: {TRANSFER_DIRECTIONS}")
    print(f"# Output: {OUTPUT_CSV}")
    print(f"{'#'*60}\n")

    # Parameter-count audit (before training)
    print("[Parameter audit] InceptionTime-Lite (n_filters=48, 3 blocks, d_model=64):")
    audit_model = build_inceptiontime_lite(in_channels=12, d_model=64, n_filters=48)
    audit = audit_model.count_parameters()
    print(f"  Backbone total params: {audit['total']:,}")
    for blk in audit["blocks"]:
        print(f"    Block {blk['block']}: {blk['params']:,}")
    print(f"  proj: {audit['proj']:,}, norm: {audit['norm']:,}")
    full_model = ECGClassifier(
        in_channels=12, d_model=64, n_layers=3, num_classes=5,
        backbone_type="inceptiontime_lite",
    )
    full_params = sum(p.numel() for p in full_model.parameters())
    print(f"  Full model (with head): {full_params:,}")
    assert 200_000 <= full_params <= 500_000, \
        f"param count {full_params:,} not in target 200K-500K range!"
    print(f"  OK: param count {full_params:,} in [200K, 500K] target range\n")

    # ============ Phase 1: train 15 models ============
    print("=" * 60)
    if args.transfer_only:
        print("Phase 1: load 15 models from checkpoint (skip training, --transfer-only mode)")
    else:
        print("Phase 1: train 15 models (3 corpora x 5 seeds)")
    print("=" * 60)

    train_results: List[dict] = []
    trained_models: Dict[Tuple[str, int], dict] = {}  # (dataset, seed) -> info
    oom_log = {"max_level": 0, "degraded_count": 0}

    if args.transfer_only:
        # --transfer-only mode: load existing models from checkpoint, skip training
        for dataset in args.datasets:
            for seed in args.seeds:
                try:
                    model, info = load_and_evaluate_single(
                        dataset, seed, args, device,
                        n_filters=args.n_filters,
                        use_checkpoint=args.use_checkpoint,
                    )
                    if model is not None:
                        train_results.append(info)
                        trained_models[(dataset, seed)] = info
                except Exception as e:
                    print(f"[ERROR] load {dataset} seed={seed} failed: {e}")
                    traceback.print_exc()
    else:
        for dataset in args.datasets:
            for seed in args.seeds:
                try:
                    # Activate the 4-level OOM fallback chain via try_train_with_oom_fallback
                    # (previously train_single was called directly, leaving the fallback chain dead code).
                    # Adapt train_single(dataset, seed, args, dev, ...) to the (params, dev) interface.
                    def _train_adapter(params, dev, _ds=dataset, _seed=seed):
                        # Pass arch/depth/width to train_single so the Level 3 ResNet1D variant
                        # builds genuinely different backbones (the original closure only extracted
                        # n_filters/use_checkpoint, discarding arch/depth/width).
                        return train_single(
                            _ds, _seed, args, dev,
                            n_filters=params.get("n_filters", 48),
                            use_checkpoint=params.get("use_checkpoint", False),
                            arch_override=params.get("arch"),
                            depth=params.get("depth"),
                            width=params.get("width"),
                        )
                    model, info = try_train_with_oom_fallback(
                        _train_adapter, {}, device,
                        n_filters=args.n_filters, use_checkpoint=args.use_checkpoint,
                    )
                    if model is not None:
                        train_results.append(info)
                        trained_models[(dataset, seed)] = info
                    else:
                        oom_log["degraded_count"] += 1
                        oom_lvl = info.get("oom_log", {}).get("level", 4)
                        oom_log["max_level"] = max(oom_log["max_level"], oom_lvl)
                except RuntimeError as e:
                    if is_oom_error(e):
                        print(f"[OOM] {dataset} seed={seed} training OOM: {e}")
                        torch.cuda.empty_cache() if torch.cuda.is_available() else None
                        oom_log["degraded_count"] += 1
                        oom_log["max_level"] = max(oom_log["max_level"], 4)
                    else:
                        print(f"[ERROR] {dataset} seed={seed} training failed: {e}")
                        traceback.print_exc()
                except Exception as e:
                    print(f"[ERROR] {dataset} seed={seed} training failed: {e}")
                    traceback.print_exc()

    print(f"\n[Phase 1 done] trained {len(train_results)}/{len(args.datasets)*len(args.seeds)} models")
    if oom_log["degraded_count"] > 0:
        print(f"[OOM] {oom_log['degraded_count']} models degraded due to OOM")

    # ============ Phase 2: transfer evaluation 30 experiments ============
    transfer_results: List[dict] = []
    if not args.no_transfer and len(trained_models) > 0:
        print("\n" + "=" * 60)
        print("Phase 2: transfer evaluation 30 experiments (6 directions x 5 seeds)")
        print("=" * 60)

        for source, target in TRANSFER_DIRECTIONS:
            if source not in args.datasets or target not in args.datasets:
                continue
            for seed in args.seeds:
                if (source, seed) not in trained_models:
                    print(f"[SKIP] {source}->{target} seed={seed}: source model not trained")
                    continue
                try:
                    result = eval_transfer_pair(
                        source, target, seed,
                        trained_models[(source, seed)],
                        args, device,
                    )
                    transfer_results.append(result)
                except Exception as e:
                    print(f"[ERROR] {source}->{target} seed={seed} transfer failed: {e}")
                    traceback.print_exc()
                    # Use unified schema with arch from source model info and add skipped field
                    # (the original dict had only 5 fields, missing skipped and 16 stat fields).
                    transfer_results.append(_make_transfer_result(
                        source=source, target=target, seed=seed,
                        arch=trained_models[(source, seed)].get("arch", ARCH_NAME),
                        error=str(e), skipped=True,
                    ))

        print(f"\n[Phase 2 done] evaluated {len(transfer_results)}/"
              f"{len(TRANSFER_DIRECTIONS)*len(args.seeds)} transfer experiments")

    # ============ Phase 3: write CSV ============
    print("\n" + "=" * 60)
    print("Phase 3: write CSV")
    print("=" * 60)

    # Serialize training results (drop non-serializable fields)
    serializable_train = []
    for r in train_results:
        row = {k: v for k, v in r.items()
               if k not in ("model", "loaders", "cal_eval", "test_eval", "clusters_test")}
        serializable_train.append(row)

    # Infer the actual arch_display to pass to write_csv. The OOM fallback may have changed
    # arch from inceptiontime_lite to resnet1d, so the CSV header must reflect the real architecture.
    # Prefer the first training result's arch field (set to arch_display in train_single),
    # falling back to ARCH_NAME when no training results exist.
    _csv_arch_display = train_results[0].get("arch", ARCH_NAME) if train_results else ARCH_NAME
    write_csv(serializable_train, transfer_results, OUTPUT_CSV, oom_summary=oom_log,
              arch_display=_csv_arch_display)

    # ============ Phase 4: summary report ============
    print("\n" + "=" * 60)
    print("E5 experiment summary")
    print("=" * 60)
    print(f"Architecture: {ARCH_NAME}")
    print(f"Trained models: {len(train_results)} / {len(args.datasets)*len(args.seeds)}")
    print(f"Transfer evaluations: {len(transfer_results)} / {len(TRANSFER_DIRECTIONS)*len(args.seeds)}")
    if train_results:
        accs = [r.get("id_acc_raw", 0) for r in train_results]
        eces = [r.get("id_ece_raw", 0) for r in train_results]
        print(f"ID acc mean: {np.mean(accs):.2f}% (sd={np.std(accs):.2f})")
        print(f"ID ECE(raw) mean: {np.mean(eces):.4f} (sd={np.std(eces):.4f})")
    if transfer_results:
        valid = [r for r in transfer_results if "delta_ece" in r and not np.isnan(r.get("delta_ece", float("nan")))]
        if valid:
            decays = [r["delta_ece"] for r in valid]
            print(f"Transfer ΔECE mean: {np.mean(decays):+.4f} (sd={np.std(decays):.4f}, n={len(decays)})")
            brier_imps = [r.get("brier_reliability_improvement", 0) for r in valid]
            print(f"Brier reliability improvement mean: {np.mean(brier_imps):+.4f} (sd={np.std(brier_imps):.4f})")
    if oom_log["degraded_count"] > 0:
        print(f"\n[OOM degraded] {oom_log['degraded_count']} experiments degraded (max Level {oom_log['max_level']})")
        if oom_log["max_level"] >= 4:
            print("[Warning] Level 4 fallback triggered: honestly report '2 architecture families + BiMamba toy'")

    print(f"\nOutput: {OUTPUT_CSV}")
    print("E5 experiment complete!")


if __name__ == "__main__":
    main()
