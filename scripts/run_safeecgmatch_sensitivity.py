from __future__ import annotations

import argparse
from pathlib import Path

from run_paper_benchmarks import collect_results, run_specs, save_results


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Run the PTB-XL 60% OOD branch-weight sensitivity analysis for SafeECGMatch."
    )
    parser.add_argument(
        "--variants",
        nargs="+",
        choices=["freqheavy", "timeheavy"],
        default=["freqheavy", "timeheavy"],
        help="Sensitivity variants to run.",
    )
    parser.add_argument("--ptbxl-root", type=Path, required=True, help="Raw PTB-XL root directory.")
    parser.add_argument("--project-root", type=Path, default=project_root, help="Release project root.")
    parser.add_argument(
        "--checkpoint-base",
        type=Path,
        default=project_root / "checkpoints" / "sensitivity",
        help="Base directory where sensitivity-analysis checkpoints will be written.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=project_root / "results",
        help="Directory for aggregated CSV summaries.",
    )
    parser.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3], help="Random seeds to run.")
    parser.add_argument("--gpus", nargs="+", default=["0"], help="GPU ids passed through to training scripts.")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing them.")
    parser.add_argument(
        "--collect-only",
        action="store_true",
        help="Skip execution and only aggregate metrics from existing checkpoints.",
    )
    return parser.parse_args()


def common_args(ptbxl_root: Path) -> dict[str, object]:
    return {
        "gpus": ["0"],
        "server": "main",
        "data": "ptbxl",
        "root": ptbxl_root.resolve(),
        "backbone-type": "resnet1d",
        "n-label-per-class": 50,
        "mismatch-ratio": 0.6,
        "ptbxl-sampling-rate": 500,
        "ptbxl-split-mode": "fixed_volume_mismatch",
        "ptbxl-unlabeled-multiplier": 99.0,
        "ptbxl-open-test-mode": "test",
        "iterations": 50000,
        "warm-up": 500,
        "save-every": 1000,
        "batch-size": 64,
        "learning-rate": 0.001,
        "optimizer": "adam",
        "weight-decay": 0,
        "normalize": True,
        "num-workers": 2,
        "ptbxl-augment": "ecg",
    }


def sensitivity_specs(checkpoint_base: Path, variants: list[str]) -> dict[str, dict[str, object]]:
    variant_args = {
        "freqheavy": {
            "lambda-ova-cali": 0.1,
            "lambda-ova": 0.1,
            "lambda-time-branch": 0.5,
            "lambda-freq-branch": 1.5,
        },
        "timeheavy": {
            "lambda-ova-cali": 0.1,
            "lambda-ova": 0.1,
            "lambda-time-branch": 1.5,
            "lambda-freq-branch": 0.5,
        },
    }

    specs: dict[str, dict[str, object]] = {}
    for variant in variants:
        specs[f"safeecgmatch_{variant}"] = {
            "script": "main/run_SAFEECGMATCH.py",
            "checkpoint_root": checkpoint_base / variant,
            "extra_args": variant_args[variant],
        }
    return specs


def main() -> None:
    args = parse_args()
    args.project_root = args.project_root.resolve()
    args.checkpoint_base = args.checkpoint_base.resolve()
    args.results_dir = args.results_dir.resolve()
    args.ptbxl_root = args.ptbxl_root.resolve()

    specs = sensitivity_specs(args.checkpoint_base, args.variants)
    run_args = common_args(args.ptbxl_root)

    print("[SENSITIVITY] PTB-XL 500 Hz 60% OOD SafeECGMatch branch-weight analysis")
    if not args.collect_only:
        run_specs(
            project_root=args.project_root,
            specs=specs,
            seeds=args.seeds,
            common_args=run_args,
            gpus=args.gpus,
            dry_run=args.dry_run,
        )

    per_seed_df, summary_df = collect_results(specs)
    if per_seed_df.empty:
        print("[WARN] No completed results found for the requested sensitivity variants")
        return

    save_results(per_seed_df, summary_df, args.results_dir, "sensitivity_analysis")
    print(f"[DONE] Saved sensitivity-analysis summaries to {args.results_dir}")


if __name__ == "__main__":
    main()