from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.signal
import wfdb


NORMAL_CODE = "426783006"
LABEL_FILES = {
    "Rhythm": "Rhythm_labels.txt",
    "CD": "cd_labels.txt",
    "ST": "ST_labels.txt",
    "Other": "other_labels.txt",
}


def parse_args() -> argparse.Namespace:
    project_root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Preprocess raw CINC2021 records into the single-label ECGMatch-style format."
    )
    parser.add_argument("--source-root", type=Path, required=True, help="Raw CINC2021 root directory.")
    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
        help="Output directory that will contain metadata_single_label.csv and data/*.npy.",
    )
    parser.add_argument(
        "--label-root",
        type=Path,
        default=project_root / "resources" / "cinc_labels",
        help="Directory containing ECGMatch superclass label text files.",
    )
    parser.add_argument("--sampling-rate", type=int, default=500, help="Target sampling rate.")
    parser.add_argument("--signal-length", type=int, default=5000, help="Target signal length.")
    parser.add_argument("--limit", type=int, default=None, help="Optional cap for debugging.")
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files if they already exist.",
    )
    return parser.parse_args()


def load_label_sets(label_root: Path) -> dict[str, set[str]]:
    label_sets: dict[str, set[str]] = {}
    for label_name, file_name in LABEL_FILES.items():
        path = label_root / file_name
        if not path.exists():
            raise FileNotFoundError(f"Missing label file: {path}")
        label_sets[label_name] = {
            line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        }
    return label_sets


def parse_dx_codes(header_path: Path) -> list[str]:
    for line in header_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.startswith("# Dx:"):
            return [code.strip() for code in line.split(":", 1)[1].split(",") if code.strip()]
    return []


def assign_single_label(dx_codes: list[str], label_sets: dict[str, set[str]]) -> str | None:
    if len(dx_codes) == 1 and dx_codes[0] == NORMAL_CODE:
        return "Normal"

    matched_groups = {
        label_name
        for code in dx_codes
        for label_name, codes in label_sets.items()
        if code in codes
    }
    if len(matched_groups) != 1:
        return None
    return next(iter(matched_groups))


def load_signal(record_path: Path) -> tuple[np.ndarray, float]:
    signal, fields = wfdb.rdsamp(str(record_path))
    return signal.astype(np.float32), float(fields["fs"])


def resample_and_fix_length(
    signal: np.ndarray,
    source_fs: float,
    target_fs: int,
    target_length: int,
) -> np.ndarray:
    if signal.ndim != 2:
        raise ValueError(f"Expected a 2D signal array, got shape {signal.shape}")

    if signal.shape[1] != 12:
        raise ValueError(f"Expected 12 leads, got shape {signal.shape}")

    if int(round(source_fs)) != target_fs:
        target_samples = int(round(signal.shape[0] * target_fs / source_fs))
        signal = scipy.signal.resample(signal, target_samples, axis=0).astype(np.float32)

    if signal.shape[0] >= target_length:
        signal = signal[:target_length]
    else:
        pad_len = target_length - signal.shape[0]
        signal = np.pad(signal, ((0, pad_len), (0, 0)), mode="constant")

    return signal.T.astype(np.float32)


def ensure_output_dirs(output_root: Path, overwrite: bool) -> Path:
    data_dir = output_root / "data"
    if output_root.exists() and not overwrite:
        metadata_path = output_root / "metadata_single_label.csv"
        if metadata_path.exists() or data_dir.exists():
            raise FileExistsError(
                f"Output already exists at {output_root}. Pass --overwrite to replace it."
            )
    output_root.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def main() -> None:
    args = parse_args()
    label_sets = load_label_sets(args.label_root)
    data_dir = ensure_output_dirs(args.output_root, args.overwrite)

    header_paths = sorted(args.source_root.rglob("*.hea"))
    if args.limit is not None:
        header_paths = header_paths[: args.limit]

    if not header_paths:
        raise FileNotFoundError(f"No .hea files found under {args.source_root}")

    rows: list[dict[str, object]] = []
    id_to_source: dict[str, Path] = {}
    counters: Counter[str] = Counter()

    for header_path in header_paths:
        counters["total_headers"] += 1
        record_path = header_path.with_suffix("")
        record_id = record_path.name

        if record_id in id_to_source:
            raise RuntimeError(
                f"Duplicate record id detected: {record_id} from {header_path} and {id_to_source[record_id]}"
            )

        dx_codes = parse_dx_codes(header_path)
        if not dx_codes:
            counters["skipped_missing_dx"] += 1
            continue

        label = assign_single_label(dx_codes, label_sets)
        if label is None:
            counters["skipped_non_single_group"] += 1
            continue

        try:
            signal, source_fs = load_signal(record_path)
            signal = resample_and_fix_length(
                signal,
                source_fs=source_fs,
                target_fs=args.sampling_rate,
                target_length=args.signal_length,
            )
        except Exception:
            counters["skipped_signal_error"] += 1
            continue

        npy_path = data_dir / f"{record_id}.npy"
        np.save(npy_path, signal)

        rows.append(
            {
                "id": record_id,
                "label": label,
                "npy_path": npy_path.name,
                "fs": args.sampling_rate,
                "original_len": signal.shape[1],
            }
        )
        id_to_source[record_id] = header_path
        counters["written"] += 1

    if not rows:
        raise RuntimeError("No single-label samples were produced. Check the input root and label mapping.")

    metadata = pd.DataFrame(rows).sort_values("id").reset_index(drop=True)
    metadata_path = args.output_root / "metadata_single_label.csv"
    metadata.to_csv(metadata_path, index=False)

    summary = {
        "source_root": str(args.source_root.resolve()),
        "output_root": str(args.output_root.resolve()),
        "sampling_rate": args.sampling_rate,
        "signal_length": args.signal_length,
        "counts": dict(counters),
        "label_distribution": metadata["label"].value_counts().sort_index().to_dict(),
    }
    summary_path = args.output_root / "preprocess_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote {len(metadata)} samples to {args.output_root}")
    print(f"Metadata: {metadata_path}")
    print(f"Summary: {summary_path}")


if __name__ == "__main__":
    main()