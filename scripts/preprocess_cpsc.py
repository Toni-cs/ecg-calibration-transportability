"""Preprocess CPSC2018 (CPSC Database + CPSC-Extra) into the ECGNPZDataset format.

Corpus identity (corrected 2026-09-16; do NOT describe this corpus as "CPSC2018+2019"):
  Both subsets handled here belong to CPSC2018. The corpus contains NO CPSC2019 data.
  - Training_WFDB/ (A0001.hea ...) = **CPSC Database**, the public CPSC2018 training set
    (6,877 records officially; 9 distinct SNOMED codes measured, one-to-one with the
    official 9 classes; **MI = 0**)
  - Training_2/    (Q0001.hea ...) = **CPSC-Extra**, the CPSC2018 records that were NOT
    used by the official challenge (3,453 records officially; 72 distinct SNOMED codes
    measured, including MI/HYP)
  Basis: the PhysioNet/CinC 2020 data description
  (physionet.org/content/challenge-2020) lists "CPSC Database 6,877" and
  "CPSC-Extra Database 3,453", the latter described verbatim as
  "the CPSC2018 data that was not used". The local archives are named
  china-physiological-signal-challenge-in-2018.zip and
  china-12lead-ecg-challenge-database.zip (the latter published by the official
  PhysioNet Kaggle account, described as "The data are from the China Physiological
  Signal Challenge in 2018 (CPSC2018)").
  Note: CPSC2019 was a QRS / heart-rate **detection** task with no diagnostic labels
  and is unrelated to this corpus.

  WARNING: the internal source tag is still spelled "cpsc2019" (legacy naming). That
  string is baked into the patient_id column of splits/cpsc_seed*.csv and into
  data/cpsc_processed/*. It **must not be renamed**, or every published split and every
  trained model will become misaligned.

Inputs:
  --cpsc2018-root  directory containing Training_WFDB/ (= CPSC Database)
  --cpsc2019-root  directory containing Training_2/ (= CPSC-Extra; flag name kept for
                   historical compatibility)
  --output-root     output directory

Outputs (same structure as preprocess_chapman.py):
  - metadata_single_label.csv: id/label/npy_path/fs/original_len/patient_id
    Each CPSC record = 1 patient; patient_id = record name; no strat_fold
    (patient_wise_split in train.py applies the 70/10/20 split)
  - data/*.npy: float32 (12, 5000) 500Hz x 10s
  - preprocess_summary.json: STROBE counts + SNOMED code frequency table + mapping coverage

CPSC Database (Training_WFDB): 6,844 extracted (6,877 in the zip; 33 records
    A6845-A6877 were lost during extraction and still need to be restored),
    12 leads, 500Hz, 7500 samples (15s) -> truncated to 5000 (10s)
CPSC-Extra (Training_2):       3,453 records, 12 leads, 500Hz, 5000 samples (10s)
Total ~10,297 records (the two subsets do not overlap)
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
from src.data.mapping import SCP_TO_SUPERCLASS, SUPERCLASSES  # noqa: E402

PRIORITY = ["MI", "STTC", "CD", "HYP", "NORM"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preprocess CPSC2018 (CPSC Database + CPSC-Extra) "
                    "into the ECGNPZDataset format.")
    parser.add_argument("--cpsc2018-root", type=Path, required=True,
                        help="Directory containing Training_WFDB/ (= CPSC Database)")
    parser.add_argument("--cpsc2019-root", type=Path, required=True,
                        help="Directory containing Training_2/ (= CPSC-Extra, the "
                             "unused portion of CPSC2018; flag name kept for "
                             "historical compatibility)")
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--sampling-rate", type=int, default=500)
    parser.add_argument("--signal-length", type=int, default=5000)
    parser.add_argument("--limit", type=int, default=None, help="Cap records (debug).")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def parse_dx_line(hea_path: Path) -> list[str]:
    for line in hea_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        t = line.strip()
        if t.startswith("#Dx:") or t.startswith("# Dx:"):
            return [c.strip() for c in t.split(":", 1)[1].split(",") if c.strip()]
    return []


def codes_to_superclasses(codes: list[str]) -> list[str]:
    result = []
    for code in codes:
        sc = SCP_TO_SUPERCLASS.get(str(code))
        if sc is not None:
            result.append(sc)
    return result


def single_label(superclasses: list[str]) -> str | None:
    if not superclasses:
        return None
    for label in PRIORITY:
        if label in superclasses:
            return label
    return None


def process_record(hea_path: Path, target_fs: int, target_length: int) -> tuple[np.ndarray, list[str]] | None:
    try:
        signal, fs = load_signal(hea_path.with_suffix(""))
        sig = resample_and_fix_length(signal, fs, target_fs, target_length)
        codes = parse_dx_line(hea_path)
        return sig, codes
    except Exception as e:
        print(f"  [skip] {hea_path.name}: {e}")
        return None


def main() -> None:
    args = parse_args()
    data_dir = args.output_root / "data"
    if args.output_root.exists() and not args.overwrite:
        if (args.output_root / "metadata_single_label.csv").exists() or data_dir.exists():
            raise FileExistsError(
                f"Output exists at {args.output_root}. Pass --overwrite to replace.")
    args.output_root.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    # NOTE: the source strings below become the patient_id prefix (e.g. cpsc2019_Q0001)
    # and are already baked into splits/cpsc_seed*.csv and data/cpsc_processed/*.
    # "cpsc2019" is legacy naming; the actual corpus is CPSC-Extra (the unused portion
    # of CPSC2018). It must NOT be renamed, or every published split and trained model
    # will become misaligned.
    dirs = []
    d18 = args.cpsc2018_root / "Training_WFDB"
    if d18.exists():
        dirs.append(("cpsc2018", d18))
    d19 = args.cpsc2019_root / "Training_2"
    if d19.exists():
        dirs.append(("cpsc2019", d19))
    if not dirs:
        raise FileNotFoundError(f"No Training_WFDB/ or Training_2/ found")

    hea_paths = []
    for source, d in dirs:
        paths = sorted(d.rglob("*.hea"))
        hea_paths.extend((source, p) for p in paths)
        print(f"[{source}] {len(paths)} records in {d}")

    if args.limit:
        hea_paths = hea_paths[:args.limit]

    rows = []
    code_counter = Counter()
    unmapped_codes = Counter()
    mapped_count = 0
    skipped_count = 0
    label_counter = Counter()

    for i, (source, hea_path) in enumerate(hea_paths):
        result = process_record(hea_path, args.sampling_rate, args.signal_length)
        if result is None:
            skipped_count += 1
            continue
        signal, codes = result

        for c in codes:
            code_counter[c] += 1
            if c not in SCP_TO_SUPERCLASS:
                unmapped_codes[c] += 1

        superclasses = codes_to_superclasses(codes)
        label = single_label(superclasses)
        if label is None:
            skipped_count += 1
            continue

        record_name = hea_path.stem
        patient_id = f"{source}_{record_name}"
        npy_name = f"{patient_id}.npy"
        np.save(data_dir / npy_name, signal)

        rows.append({
            "id": patient_id,
            "label": label,
            "npy_path": npy_name,
            "fs": args.sampling_rate,
            "original_len": signal.shape[1],
            "patient_id": patient_id,
        })
        mapped_count += 1
        label_counter[label] += 1

        if (i + 1) % 1000 == 0:
            print(f"  processed {i+1}/{len(hea_paths)} ({mapped_count} mapped, {skipped_count} skipped)")

    df = pd.DataFrame(rows)
    df.to_csv(args.output_root / "metadata_single_label.csv", index=False)

    summary = {
        "total_records": len(hea_paths),
        "mapped_single_label": mapped_count,
        "skipped_no_label_or_error": skipped_count,
        "label_distribution": dict(label_counter),
        "top_codes": dict(code_counter.most_common(30)),
        "unmapped_codes": dict(unmapped_codes.most_common(20)),
        "sources": {s: sum(1 for _, p in hea_paths if _ == s) for s, _ in [(k, None) for k, _ in dirs]},
        "sampling_rate": args.sampling_rate,
        "signal_length": args.signal_length,
    }
    (args.output_root / "preprocess_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nDone: {mapped_count} mapped, {skipped_count} skipped")
    print(f"Label distribution: {dict(label_counter)}")
    if unmapped_codes:
        print(f"Unmapped codes ({len(unmapped_codes)}): {dict(unmapped_codes.most_common(10))}")


if __name__ == "__main__":
    main()
