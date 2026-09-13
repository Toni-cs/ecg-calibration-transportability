"""Data-integrity QC: drop contaminated ECG records containing NaN/Inf (preregistered protocol §13 data integrity).

Background: in earlier versions, Chapman/PTB-XL preprocessing (preprocess_*.py) did not run
an isfinite check on the source signals, so bad-lead segments / sparse NaN from
artifact sampling in the source wfdb were passed through into data/*.npy. The
ECGNPZDataset._load_signal fail-fast guard would then crash at runtime (hit during the
cross-library S1 target-test forward pass) instead of silently polluting the
normalization statistics.

This script applies exactly the same filtering QC to already-produced data directories as
preprocess_*.py (drops ~0.1% contaminated records; standard ECG QC; interpolation would
introduce systematic bias, so it is not used):
  1. Scan data/*.npy file by file; collect records containing non-finite values (NaN/Inf).
  2. Move bad npy files to <output_root>/quarantine_nonfinite/<id>.npy (not deleted; traceable).
  3. Drop the corresponding rows from metadata_single_label.csv.
  4. Write qc_report.json (removed id list + count + label-distribution impact).

Usage (reproducible):
    python scripts/qc_drop_nonfinite.py --data-root data/chapman_processed_v2
Also works for PTB-XL (--data-root data/ptbxl_processed).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def scan_nonfinite_ids(data_dir: Path) -> list[str]:
    """Scan data/*.npy and return the list of npy stems whose records contain non-finite values (reproducible)"""
    bad = []
    for p in sorted(data_dir.glob("*.npy")):
        try:
            x = np.load(p, mmap_mode="r")
            if not np.isfinite(x).all():
                bad.append(p.stem)  # e.g. chapman_JS10765
        except Exception:
            bad.append(p.stem)  # unreadable files are also treated as contaminated and quarantined
    return bad


def qc_clean(output_root: Path, quarantine_name: str = "quarantine_nonfinite") -> dict:
    data_dir = output_root / "data"
    meta_csv = output_root / "metadata_single_label.csv"
    if not data_dir.is_dir() or not meta_csv.exists():
        raise FileNotFoundError(f"{output_root} is not a preprocessing output directory"
                                f"(missing data/ or metadata_single_label.csv)")

    meta = pd.read_csv(meta_csv)
    bad_ids = scan_nonfinite_ids(data_dir)
    if not bad_ids:
        print(f"[QC] {output_root}: no contaminated records, skipping")
        return {"n_scanned": len(meta), "n_removed": 0, "removed_ids": []}

    # move bad npy files to quarantine (not deleted, traceable)
    qdir = output_root / quarantine_name
    qdir.mkdir(parents=True, exist_ok=True)
    npy_removed = []
    for stem in bad_ids:
        src = data_dir / f"{stem}.npy"
        if src.exists():
            shutil.move(str(src), str(qdir / f"{stem}.npy"))
            npy_removed.append(stem)

    # drop the corresponding rows from metadata
    removed_meta = meta[meta["npy_path"].isin([f"{s}.npy" for s in npy_removed])]
    meta_clean = meta[~meta["npy_path"].isin([f"{s}.npy" for s in npy_removed])]
    meta_clean = meta_clean.reset_index(drop=True)
    meta_clean.to_csv(meta_csv, index=False)

    report = {
        "output_root": str(output_root.resolve()),
        "n_metadata_before": int(len(meta)),
        "n_metadata_after": int(len(meta_clean)),
        "n_removed": int(len(npy_removed)),
        "removed_ids": npy_removed,
        "label_dist_before": meta["label"].value_counts().sort_index().to_dict(),
        "label_dist_after": meta_clean["label"].value_counts().sort_index().to_dict(),
        "quarantine_dir": str(qdir.resolve()),
        "note": "Dropped contaminated records containing NaN/Inf (standard ECG QC; interpolation would introduce bias, so it is not used). "
                "Mirrors the isfinite QC logic in preprocess_*.py.",
    }
    (output_root / "qc_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[QC] {output_root}: dropped {len(npy_removed)}/{len(meta)} contaminated records")
    print(f"  bad ids: {npy_removed}")
    print(f"  quarantine -> {qdir}\n  metadata updated + qc_report.json")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", type=Path, required=True)
    args = ap.parse_args()
    qc_clean(args.data_root)


if __name__ == "__main__":
    main()
