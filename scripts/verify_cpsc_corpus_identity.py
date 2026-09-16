"""Audit the CPSC corpus identity: CPSC Database (2018) vs CPSC-Extra vs CPSC2019.

Read-only; modifies nothing. Reports:
  1. Record counts on disk for each subset.
  2. SNOMED #Dx code distribution per subset (showing MI comes only from CPSC-Extra).
  3. Whether CPSC's official nine class names cover MI/STTC/CD/HYP
     (showing the superclass system is PTB-XL's, not CPSC's).

Usage:
    python scripts/verify_cpsc_corpus_identity.py [--data-root data/downloads]

Default --data-root expects the layout produced by downloading:
    <data-root>/kaggle_cpsc2018/Training_WFDB   -> CPSC Database
    <data-root>/kaggle_cpsc2019/Training_2      -> CPSC-Extra
(the directory names are legacy; the second is NOT CPSC2019).
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

# Official CPSC2018 nine disease classes
OFFICIAL_9 = ["Normal", "AF", "I-AVB", "LBBB", "RBBB", "PAC", "PVC", "STD", "STE"]

# SNOMED codes that map to the MI superclass (the only MI source in this corpus)
MI_CODES = {"164867002", "164865005", "54329005", "57054005", "426434006"}

DX_RE = re.compile(r"^#\s*Dx:\s*(.+)$", re.M)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-root", type=Path, default=Path("data/downloads"),
                    help="root holding kaggle_cpsc2018/ and kaggle_cpsc2019/")
    args = ap.parse_args()
    dl = args.data_root

    subsets = [
        ("CPSC Database (CPSC2018)", dl / "kaggle_cpsc2018" / "Training_WFDB"),
        ("CPSC-Extra",              dl / "kaggle_cpsc2019" / "Training_2"),
    ]

    print("=" * 78)
    print("1. Record counts on disk")
    print("=" * 78)
    for name, d in subsets:
        if not d.is_dir():
            print(f"  {name:28s} MISSING: {d}")
            continue
        print(f"  {name:28s} {d}  .hea = {len(list(d.glob('*.hea')))}")

    print()
    print("=" * 78)
    print("2. SNOMED #Dx code distribution")
    print("=" * 78)
    for name, d in subsets:
        if not d.is_dir():
            continue
        cnt: Counter[str] = Counter()
        n_mi = n_files = 0
        for hea in sorted(d.glob("*.hea")):
            n_files += 1
            m = DX_RE.search(hea.read_text(errors="ignore"))
            if not m:
                continue
            codes = {c.strip() for c in m.group(1).split(",") if c.strip()}
            cnt.update(codes)
            if codes & MI_CODES:
                n_mi += 1
        print(f"\n  --- {name} ---")
        print(f"  records={n_files}  distinct SNOMED codes={len(cnt)}")
        if n_files:
            print(f"  records carrying an MI code = {n_mi} ({100.0 * n_mi / n_files:.1f}%)")
        print("  top 12 codes:")
        for code, c in cnt.most_common(12):
            print(f"    {code:14s} x{c:<6d}{'  <-- MI' if code in MI_CODES else ''}")
        mi_detail = {c: cnt[c] for c in sorted(MI_CODES) if cnt[c]}
        print(f"  MI code detail: {mi_detail}")

    print()
    print("=" * 78)
    print("3. Official nine-class coverage check")
    print("=" * 78)
    print(f"  official CPSC2018 classes: {OFFICIAL_9}")
    for probe in ("MI", "STTC", "CD", "HYP"):
        print(f"    '{probe}' in official classes? {probe in OFFICIAL_9}")
    print("  -> MI/STTC/CD/HYP do not exist in the official nine; the superclass")
    print("     system is PTB-XL's (Wagner et al., Sci Data 7:148, 2020).")


if __name__ == "__main__":
    sys.exit(main())
