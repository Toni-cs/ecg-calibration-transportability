"""Chapman-Shaoxing (ecg-arrhythmia 1.0.0, 20265 patients) preprocessing -> ECGNPZDataset format.

Input: PhysioNet ecg-arrhythmia 1.0.0 unpacked directory
       (a-large-scale-...-1.0.0/WFDBRecords/XX/XXX/JSxxxxx.hea, #Dx: SNOMED codes)
Output: isomorphic with preprocess_ptbxl.py
  - metadata_single_label.csv: id/label/npy_path/fs/original_len/patient_id
    (Chapman has one ECG per patient, patient_id = record-stem; no strat_fold -- splitting is
    done by train.py's patient_wise_split at the protocol §2 patient-level 70/10/20 ratio)
  - data/*.npy: float32 (12, 5000) 500Hz x 10s
  - preprocess_summary.json: STROBE counts + unmapped-SNOMED-code frequency table + code-table
    coverage

Chapman-specific code-table override (code_overrides, does not touch the global
SCP_TO_SUPERCLASS):
  the global table is CINC2021-customized and maps 426177001 (SB bradycardia) /
  427084000 (ST tachycardia) to STTC; but in the Chapman context these two are rate variants of
  normal sinus rhythm and, under the ECG five-superclass scheme, should map to NORM (sinus).
  Without the override, 91% of Chapman samples would be labeled STTC (severe class-imbalance
  artifact). This cross-library semantic conflict is registered as a protocol sensitivity object,
  and the override applies only to Chapman preprocessing.

Usage:
    python scripts/preprocess_chapman.py \
        --source-root ./data/downloads/ecg-arrhythmia-1.0.0/a-large-scale-...-1.0.0 \
        --output-root ./data/chapman_processed_v2
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from preprocess_cinc2021 import load_signal, resample_and_fix_length  # noqa: E402
from src.data.mapping import SCP_TO_SUPERCLASS, MAP_TO_5SUPERCLASS  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preprocess Chapman-Shaoxing (ecg-arrhythmia 1.0.0) into "
                    "the ECGNPZDataset format.")
    parser.add_argument("--source-root", type=Path, required=True,
                        help="Directory containing WFDBRecords/ and ConditionNames_SNOMED-CT.csv")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--sampling-rate", type=int, default=500)
    parser.add_argument("--signal-length", type=int, default=5000)
    parser.add_argument("--limit", type=int, default=None, help="Cap records (debug only).")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def parse_dx_line(hea_path: Path) -> list[str]:
    """Parse '#Dx: code,code,...' from the .hea (the dataset has no space-prefixed variant;
    both forms are accepted)."""
    for line in hea_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        t = line.strip()
        if t.startswith("#Dx:") or t.startswith("# Dx:"):
            return [c.strip() for c in t.split(":", 1)[1].split(",") if c.strip()]
    return []


def ensure_output_dirs(output_root: Path, overwrite: bool) -> Path:
    data_dir = output_root / "data"
    if output_root.exists() and not overwrite:
        if (output_root / "metadata_single_label.csv").exists() or data_dir.exists():
            raise FileExistsError(
                f"Output already exists at {output_root}. Pass --overwrite to replace it.")
    output_root.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def main() -> None:
    args = parse_args()
    wfdb_root = args.source_root / "WFDBRecords"
    if not wfdb_root.exists():
        raise FileNotFoundError(f"WFDBRecords/ not found under {args.source_root}")
    data_dir = ensure_output_dirs(args.output_root, args.overwrite)

    # Chapman-specific code-table override (does not touch the global table, to avoid
    # contaminating PTB-XL; see module docstring):
    # SB/ST in Chapman are normal sinus-rhythm rate variants -> NORM (the global table maps them
    # to STTC for CINC2021)
    chapman_overrides = {
        "426177001": "NORM",  # SB sinus bradycardia -> normal sinus
        "427084000": "NORM",  # ST sinus tachycardia -> normal sinus
        "427393009": "NORM",  # SA sinus arrhythmia -> normal sinus (cross-library alignment)
    }

    hea_paths = sorted(wfdb_root.rglob("*.hea"))
    if args.limit is not None:
        hea_paths = hea_paths[: args.limit]
    if not hea_paths:
        raise FileNotFoundError(f"No .hea files under {wfdb_root}")

    rows: list[dict[str, object]] = []
    counters = {"total_headers": 0, "skipped_missing_dx": 0, "skipped_unmappable": 0,
                "skipped_signal_error": 0, "skipped_nonfinite": 0,  # QC: contaminated signals excluded
                "skipped_existing": 0, "written": 0}
    unmapped_code_freq: Counter = Counter()

    for hea_path in hea_paths:
        counters["total_headers"] += 1
        dx_codes = parse_dx_line(hea_path)
        if not dx_codes:
            counters["skipped_missing_dx"] += 1
            continue
        scp = {c: 1.0 for c in dx_codes}
        label = MAP_TO_5SUPERCLASS(scp, code_overrides=chapman_overrides)
        if label is None:
            counters["skipped_unmappable"] += 1
            for c in dx_codes:
                if str(c) not in SCP_TO_SUPERCLASS or SCP_TO_SUPERCLASS[str(c)] is None:
                    unmapped_code_freq[str(c)] += 1
            continue
        stem = hea_path.stem  # JSxxxxx (one ECG per patient, patient_id = record stem)
        record_id = f"chapman_{stem}"
        npy_path = data_dir / f"{record_id}.npy"
        record_path = hea_path.with_suffix("")

        if npy_path.exists():
            # Resumable rerun: the npy signal is independent of the label, so if it already
            # exists skip signal loading/rewriting and rebuild the metadata row from the current
            # mapping (a label-semantics update does not require rewriting the signal).
            counters["skipped_existing"] += 1
            rows.append({
                "id": record_id,
                "label": label,
                "npy_path": npy_path.name,
                "fs": args.sampling_rate,
                "original_len": args.signal_length,
                "patient_id": stem,  # string patient_id (compatible with patient_wise_split Hashable)
            })
            continue

        try:
            signal, source_fs = load_signal(record_path)
            signal = resample_and_fix_length(
                signal, source_fs=source_fs,
                target_fs=args.sampling_rate, target_length=args.signal_length)
        except Exception:
            counters["skipped_signal_error"] += 1
            continue

        # QC (protocol §13 data integrity): source signals containing NaN/Inf (bad-lead segments /
        # artifact sampling) must be dropped here -- otherwise non-finite values would silently
        # propagate into calibration error and training/evaluation (ECGNPZDataset._load_signal's
        # fail-fast guard would crash at runtime). Dropping ~0.1% contaminated records is standard
        # ECG QC (artifacts); interpolation would introduce systematic bias.
        if not np.isfinite(signal).all():
            counters["skipped_nonfinite"] += 1
            continue

        np.save(npy_path, signal)
        rows.append({
            "id": record_id,
            "label": label,
            "npy_path": npy_path.name,
            "fs": args.sampling_rate,
            "original_len": int(signal.shape[1]),
            "patient_id": stem,  # string patient_id (compatible with patient_wise_split Hashable)
        })
        counters["written"] += 1

    if not rows:
        raise RuntimeError("No samples produced. Check Dx parsing and mapping coverage.")

    metadata = pd.DataFrame(rows).sort_values("id").reset_index(drop=True)
    metadata_path = args.output_root / "metadata_single_label.csv"
    metadata.to_csv(metadata_path, index=False)

    # Code-table coverage analysis (against the full ConditionNames_SNOMED-CT table, for
    # code-table extension decisions)
    cond_csv = args.source_root / "ConditionNames_SNOMED-CT.csv"
    coverage_note = {}
    if cond_csv.exists():
        cond = pd.read_csv(cond_csv, encoding="utf-8-sig")
        for _, r in cond.iterrows():
            code = str(r["Snomed_CT"]).strip()
            in_table = code in SCP_TO_SUPERCLASS
            coverage_note[code] = {
                "acronym": r["Acronym Name"], "mapped": in_table,
                "target": SCP_TO_SUPERCLASS.get(code) if in_table else None,
                "unmapped_freq": unmapped_code_freq.get(code, 0),
            }

    summary = {
        "source_root": str(args.source_root.resolve()),
        "output_root": str(args.output_root.resolve()),
        "sampling_rate": args.sampling_rate,
        "signal_length": args.signal_length,
        "counts": counters,
        "n_patients": int(metadata["patient_id"].nunique()),
        "label_distribution": metadata["label"].value_counts().sort_index().to_dict(),
        "unmapped_code_freq": dict(unmapped_code_freq.most_common()),
        "mapping_coverage": coverage_note or None,
        "mapping": "src.data.mapping.MAP_TO_5SUPERCLASS (MI>STTC>CD>HYP>NORM); "
                   "patient_id = record-stem (one ECG per patient); "
                   f"Chapman overrides: {', '.join(f'{k}->{v}' for k, v in chapman_overrides.items())}"
                   " (sinus-family cross-library semantic conflict, registered under protocol §10-T1)",
    }
    summary_path = args.output_root / "preprocess_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False),
                            encoding="utf-8")

    print(f"Wrote {counters['written']} samples to {args.output_root}")
    print(f"Unmapped excluded: {counters['skipped_unmappable']} "
          f"(code freq: {dict(unmapped_code_freq.most_common(10))})")
    print(f"Label distribution: {summary['label_distribution']}")
    print(f"Metadata: {metadata_path}\nSummary: {summary_path}")


if __name__ == "__main__":
    main()
