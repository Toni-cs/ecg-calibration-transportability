from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd


METRIC_KEYS = ("test_top@1", "test_ece", "test_ace", "test_sce")
BENCHMARK_ALIASES = {
    "05": "ptbxl_30_ood",
    "06": "cinc2021_30_ood",
    "07": "ptbxl_60_ood",
    "08": "cinc2021_60_ood",
    "ptbxl_30_ood": "ptbxl_30_ood",
    "cinc2021_30_ood": "cinc2021_30_ood",
    "ptbxl_60_ood": "ptbxl_60_ood",
    "cinc2021_60_ood": "cinc2021_60_ood",
}


def normalize_benchmarks(selected: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for benchmark_name in selected:
        canonical = BENCHMARK_ALIASES[benchmark_name]
        if canonical not in seen:
            normalized.append(canonical)
            seen.add(canonical)
    return normalized


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description="Run the release benchmark suites for PTB-XL and CINC2021.")
    parser.add_argument(
        "--benchmarks",
        nargs="+",
        choices=sorted(BENCHMARK_ALIASES.keys()),
        default=["ptbxl_30_ood", "cinc2021_30_ood", "ptbxl_60_ood", "cinc2021_60_ood"],
        help="Benchmark suites to run. Descriptive names are preferred; legacy 05-08 aliases are still accepted.",
    )
    parser.add_argument("--ptbxl-root", type=Path, default=None, help="Raw PTB-XL root directory.")
    parser.add_argument(
        "--cinc2021-root",
        type=Path,
        default=None,
        help="Processed CINC2021 root created by preprocess_cinc2021.py.",
    )
    parser.add_argument("--project-root", type=Path, default=project_root, help="Release project root.")
    parser.add_argument(
        "--checkpoint-base",
        type=Path,
        default=project_root / "checkpoints",
        help="Base directory where all checkpoints will be written.",
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


def flatten_cli_args(arg_map: dict[str, object]) -> list[str]:
    cli_args: list[str] = []
    for key, value in arg_map.items():
        flag = f"--{key}"
        if isinstance(value, bool):
            if value:
                cli_args.append(flag)
            continue
        if isinstance(value, (list, tuple)):
            cli_args.append(flag)
            cli_args.extend(str(item) for item in value)
            continue
        cli_args.extend([flag, str(value)])
    return cli_args


def benchmark_specs(checkpoint_base: Path) -> dict[str, dict[str, object]]:
    common_base = {
        "gpus": ["0"],
        "server": "main",
        "backbone-type": "resnet1d",
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
        "ptbxl-augment": "ecg",
    }

    def make_spec(script_name: str, benchmark_id: str, method_name: str) -> dict[str, object]:
        return {
            "script": f"main/{script_name}",
            "checkpoint_root": checkpoint_base / benchmark_id / method_name,
        }

    return {
        "ptbxl_30_ood": {
            "name": "PTB-XL 500 Hz 30% OOD full method suite",
            "data": "ptbxl",
            "root_key": "ptbxl",
            "common_args": {
                **common_base,
                "n-label-per-class": 50,
                "mismatch-ratio": 0.3,
                "num-workers": 0,
            },
            "specs": {
                "safeecgmatch": make_spec("run_SAFEECGMATCH.py", "ptbxl_30_ood", "safeecgmatch"),
                "ts_tfc": make_spec("run_TS_TFC.py", "ptbxl_30_ood", "ts_tfc"),
                "complematch": make_spec("run_COMPLEMATCH.py", "ptbxl_30_ood", "complematch"),
                "supervised": make_spec("run_SL.py", "ptbxl_30_ood", "supervised"),
                "calimatch": make_spec("run_CALIMATCH.py", "ptbxl_30_ood", "calimatch"),
                "fixmatch": make_spec("run_FIXMATCH.py", "ptbxl_30_ood", "fixmatch"),
                "iomatch": make_spec("run_IOMATCH.py", "ptbxl_30_ood", "iomatch"),
                "openmatch": make_spec("run_OPENMATCH.py", "ptbxl_30_ood", "openmatch"),
                "safe_student": make_spec("run_SAFE_STUDENT.py", "ptbxl_30_ood", "safe_student"),
                "scomatch": make_spec("run_SCOMATCH.py", "ptbxl_30_ood", "scomatch"),
                "adello": make_spec("run_Adello.py", "ptbxl_30_ood", "adello"),
                "ecgmatch": make_spec("run_ECGMATCH.py", "ptbxl_30_ood", "ecgmatch"),
            },
        },
        "cinc2021_30_ood": {
            "name": "CINC2021 500 Hz 30% OOD benchmark suite",
            "data": "cinc2021",
            "root_key": "cinc2021",
            "common_args": {
                **common_base,
                "n-label-per-class": 104,
                "mismatch-ratio": 0.3,
            },
            "specs": {
                "ts_tfc": make_spec("run_TS_TFC.py", "cinc2021_30_ood", "ts_tfc"),
                "complematch": make_spec("run_COMPLEMATCH.py", "cinc2021_30_ood", "complematch"),
            },
        },
        "ptbxl_60_ood": {
            "name": "PTB-XL 500 Hz 60% OOD benchmark suite",
            "data": "ptbxl",
            "root_key": "ptbxl",
            "common_args": {
                **common_base,
                "n-label-per-class": 50,
                "mismatch-ratio": 0.6,
                "num-workers": 2,
            },
            "specs": {
                "ts_tfc": make_spec("run_TS_TFC.py", "ptbxl_60_ood", "ts_tfc"),
                "complematch": make_spec("run_COMPLEMATCH.py", "ptbxl_60_ood", "complematch"),
            },
        },
        "cinc2021_60_ood": {
            "name": "CINC2021 500 Hz 60% OOD benchmark suite",
            "data": "cinc2021",
            "root_key": "cinc2021",
            "common_args": {
                **common_base,
                "cinc-id-classes": ["Rhythm", "CD", "Other"],
                "cinc-ood-classes": ["Normal", "ST"],
                "n-label-per-class": 104,
                "mismatch-ratio": 0.6,
            },
            "specs": {
                "ts_tfc": make_spec("run_TS_TFC.py", "cinc2021_60_ood", "ts_tfc"),
                "complematch": make_spec("run_COMPLEMATCH.py", "cinc2021_60_ood", "complematch"),
            },
        },
    }


def validate_dataset_roots(args: argparse.Namespace, selected_benchmarks: list[str]) -> None:
    need_ptbxl = any(
        benchmark_id in {"ptbxl_30_ood", "ptbxl_60_ood"}
        for benchmark_id in selected_benchmarks
    )
    need_cinc = any(
        benchmark_id in {"cinc2021_30_ood", "cinc2021_60_ood"}
        for benchmark_id in selected_benchmarks
    )
    if need_ptbxl and args.ptbxl_root is None:
        raise SystemExit("--ptbxl-root is required for the PTB-XL benchmark suites")
    if need_cinc and args.cinc2021_root is None:
        raise SystemExit("--cinc2021-root is required for the CINC2021 benchmark suites")


def run_specs(
    project_root: Path,
    specs: dict[str, dict[str, object]],
    seeds: list[int],
    common_args: dict[str, object],
    gpus: list[str],
    dry_run: bool,
) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)

    for experiment_name, spec in specs.items():
        for seed in seeds:
            run_args = dict(common_args)
            run_args.update(spec.get("extra_args", {}))
            run_args["seed"] = seed
            run_args["gpus"] = gpus
            run_args["checkpoint-root"] = spec["checkpoint_root"]
            command = [sys.executable, str(project_root / spec["script"])] + flatten_cli_args(run_args)

            print(f"[RUN] {experiment_name} seed={seed}")
            print(" ".join(command))
            if dry_run:
                continue

            completed = subprocess.run(command, cwd=project_root, env=env, check=False)
            if completed.returncode != 0:
                raise RuntimeError(
                    f"Experiment failed: {experiment_name}, seed={seed}, returncode={completed.returncode}"
                )


def _read_json(json_path: Path) -> dict[str, object]:
    return json.loads(json_path.read_text(encoding="utf-8"))


def latest_completed_logs_by_seed(root_dir: Path) -> dict[int, Path]:
    selected: dict[int, Path] = {}
    if not root_dir.exists():
        return selected

    for log_path in root_dir.glob("**/main.log"):
        log_text = log_path.read_text(encoding="utf-8", errors="ignore")
        if "Total training time:" not in log_text:
            continue

        config_path = log_path.parent / "configs.json"
        if not config_path.exists():
            continue

        config = _read_json(config_path)
        seed = int(config["seed"])
        current = selected.get(seed)
        if current is None or log_path.stat().st_mtime > current.stat().st_mtime:
            selected[seed] = log_path

    return selected


def parse_validation_selected_metrics(log_path: Path) -> dict[str, object] | None:
    selected_line = None
    for line in log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if "test_top@1:" in line:
            selected_line = line

    if selected_line is None:
        return None

    metrics: dict[str, object] = {}
    for metric_key in METRIC_KEYS:
        match = re.search(
            rf"{re.escape(metric_key)}:\s*([0-9]*\.?[0-9]+|nan)",
            selected_line,
            flags=re.IGNORECASE,
        )
        raw_value = match.group(1) if match else "nan"
        metrics[metric_key] = float("nan") if raw_value.lower() == "nan" else float(raw_value)

    epoch_match = re.search(r"Epoch:\s*\[\s*(\d+)/", selected_line)
    metrics["best_epoch"] = int(epoch_match.group(1)) if epoch_match else None
    return metrics


def collect_results(specs: dict[str, dict[str, object]]) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows: list[dict[str, object]] = []
    for experiment_name, spec in specs.items():
        seed_logs = latest_completed_logs_by_seed(Path(spec["checkpoint_root"]))
        for seed, log_path in sorted(seed_logs.items()):
            parsed = parse_validation_selected_metrics(log_path)
            if parsed is None:
                continue

            rows.append(
                {
                    "experiment": experiment_name,
                    "seed": seed,
                    "checkpoint_root": str(spec["checkpoint_root"]),
                    "log_path": str(log_path),
                    "best_epoch": parsed["best_epoch"],
                    "acc": parsed["test_top@1"],
                    "ece": parsed["test_ece"],
                    "ace": parsed["test_ace"],
                    "sce": parsed["test_sce"],
                }
            )

    per_seed_df = pd.DataFrame(rows)
    if per_seed_df.empty:
        return per_seed_df, per_seed_df

    summary_rows: list[dict[str, object]] = []
    for experiment_name, frame in per_seed_df.groupby("experiment", sort=False):
        acc_values = frame["acc"].dropna()
        ece_values = frame["ece"].dropna()
        ace_values = frame["ace"].dropna()
        sce_values = frame["sce"].dropna()

        summary_rows.append(
            {
                "experiment": experiment_name,
                "n_seeds": int(frame["seed"].nunique()),
                "acc_mean_pct": acc_values.mean() * 100.0,
                "acc_std_pct": acc_values.std(ddof=1) * 100.0 if len(acc_values) > 1 else 0.0,
                "ece_mean": ece_values.mean(),
                "ece_std": ece_values.std(ddof=1) if len(ece_values) > 1 else 0.0,
                "ace_mean": ace_values.mean(),
                "ace_std": ace_values.std(ddof=1) if len(ace_values) > 1 else 0.0,
                "sce_mean": sce_values.mean(),
                "sce_std": sce_values.std(ddof=1) if len(sce_values) > 1 else 0.0,
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df.sort_values("acc_mean_pct", ascending=False).reset_index(drop=True)
    return per_seed_df, summary_df


def save_results(per_seed_df: pd.DataFrame, summary_df: pd.DataFrame, results_dir: Path, stem: str) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    per_seed_df.to_csv(results_dir / f"{stem}_per_seed.csv", index=False)
    summary_df.to_csv(results_dir / f"{stem}_summary.csv", index=False)


def main() -> None:
    args = parse_args()
    args.project_root = args.project_root.resolve()
    args.checkpoint_base = args.checkpoint_base.resolve()
    args.results_dir = args.results_dir.resolve()
    args.benchmarks = normalize_benchmarks(args.benchmarks)

    validate_dataset_roots(args, args.benchmarks)
    all_specs = benchmark_specs(args.checkpoint_base)

    for benchmark_id in args.benchmarks:
        benchmark = all_specs[benchmark_id]
        root_path = args.ptbxl_root if benchmark["root_key"] == "ptbxl" else args.cinc2021_root
        assert root_path is not None

        common_args = dict(benchmark["common_args"])
        common_args["data"] = benchmark["data"]
        common_args["root"] = root_path.resolve()

        print(f"[BENCHMARK] {benchmark_id} {benchmark['name']}")
        if not args.collect_only:
            run_specs(
                project_root=args.project_root,
                specs=benchmark["specs"],
                seeds=args.seeds,
                common_args=common_args,
                gpus=args.gpus,
                dry_run=args.dry_run,
            )

        per_seed_df, summary_df = collect_results(benchmark["specs"])
        if per_seed_df.empty:
            print(f"[WARN] No completed results found for benchmark suite {benchmark_id}")
            continue

        save_results(per_seed_df, summary_df, args.results_dir, benchmark_id)
        print(f"[DONE] Saved benchmark suite {benchmark_id} summaries to {args.results_dir}")


if __name__ == "__main__":
    main()