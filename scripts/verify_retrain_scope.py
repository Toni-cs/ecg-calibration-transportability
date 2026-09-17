"""Verify that the checkpoint retrain changed ONLY the cells it was meant to.

Context
-------
A post-hoc audit found that two of the 60 main-grid cells
(cpsc_ptbxl / inceptiontime / seed{42,43}) had been seeded from the
cpsc_chapman model of the same seed instead of being trained independently
(see reports/CHECKPOINT_INDEPENDENCE_AUDIT_2026-09-17.md). Both were retrained
and every artifact downstream of them was regenerated.

The retrain is only trustworthy if its blast radius is exactly those two cells.
This script diffs the regenerated E3 artifacts against the snapshot taken
immediately before the retrain (results/_pre_retrain_baseline_20260917/, which
is itself the post-encoding-correction output) and asserts:

    the set of changed (pair, arch, seed) cells == {cpsc_ptbxl/inceptiontime/42, 43}

If more cells moved, the retrain perturbed something it should not have, and the
result must not be used until that is understood.

Read-only. Usage:

    python scripts/verify_retrain_scope.py
    python scripts/verify_retrain_scope.py --baseline results/_pre_retrain_baseline_20260917

Exit code 0 = blast radius exactly as expected, 1 = wider (or narrower) than
expected, 2 = a file is missing / unparseable.
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "results" / "_pre_retrain_baseline_20260917"

# The only cells the retrain is allowed to touch.
EXPECTED_CHANGED = {
    ("cpsc_ptbxl", "inceptiontime", "42"),
    ("cpsc_ptbxl", "inceptiontime", "43"),
}

# Columns that identify a cell. The E3 tables all carry pair/arch/seed.
KEY_CANDIDATES = ["pair", "source", "target", "arch", "seed"]


def read_rows(path: Path):
    """Yield (key_tuple, row_dict, header) for a commented CSV.

    The E3 tables begin with '#' provenance lines and may contain blank lines
    before the header, so a plain csv.DictReader would not work.
    """
    with open(path, newline="", encoding="utf-8") as fh:
        lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        raise ValueError(f"{path.name}: no data rows")
    reader = csv.DictReader(lines)
    if reader.fieldnames is None:
        raise ValueError(f"{path.name}: no header")
    header = [h.strip() for h in reader.fieldnames]
    present = [k for k in KEY_CANDIDATES if k in header]
    if not present:
        raise ValueError(f"{path.name}: no key columns among {KEY_CANDIDATES}")
    out = []
    for row in reader:
        clean = {(k or "").strip(): (v or "").strip() for k, v in row.items() if k}
        key = tuple(clean.get(k, "") for k in present)
        out.append((key, clean))
    return out, present, header


def to_float(s: str):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def file_sha(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def diff_file(base: Path, cur: Path, tol: float = 0.0):
    """Return (changed_keys, notes) comparing base against cur."""
    b_rows, b_keys, b_header = read_rows(base)
    c_rows, c_keys, c_header = read_rows(cur)
    if b_keys != c_keys:
        raise ValueError(f"{base.name}: key columns changed {b_keys} -> {c_keys}")

    b_map = dict(b_rows)
    c_map = dict(c_rows)
    notes = []

    only_base = set(b_map) - set(c_map)
    only_cur = set(c_map) - set(b_map)
    for k in sorted(only_base):
        notes.append(f"  - row present in baseline but not now: {k}")
    for k in sorted(only_cur):
        notes.append(f"  + row present now but not in baseline: {k}")

    changed = set(only_base) | set(only_cur)
    for k in sorted(set(b_map) & set(c_map)):
        b, c = b_map[k], c_map[k]
        for col in sorted(set(b) | set(c)):
            bv, cv = b.get(col, ""), c.get(col, "")
            if bv == cv:
                continue
            bf, cf = to_float(bv), to_float(cv)
            if bf is not None and cf is not None:
                if abs(bf - cf) <= tol:
                    continue
            changed.add(k)
            notes.append(f"  ~ {k} :: {col}: {bv} -> {cv}")
    return changed, notes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default=str(DEFAULT_BASELINE))
    ap.add_argument("--tol", type=float, default=0.0,
                    help="absolute tolerance for float comparison (default exact)")
    args = ap.parse_args()

    baseline = Path(args.baseline)
    if not baseline.is_dir():
        print(f"FAIL: baseline directory not found: {baseline}")
        return 2

    files = sorted(p for p in baseline.glob("*.csv"))
    if not files:
        print(f"FAIL: no CSV in {baseline}")
        return 2

    all_changed: set[tuple] = set()
    aggregates_changed: list[str] = []
    rc = 0
    for b in files:
        cur = ROOT / "results" / b.name
        print("=" * 78)
        print(f"{b.name}")
        print("=" * 78)
        if not cur.exists():
            print(f"  ! missing current counterpart: results/{b.name}")
            rc = 2
            continue
        try:
            changed, notes = diff_file(b, cur, tol=args.tol)
        except ValueError as exc:
            # Aggregate tables (the *_summary.csv files) have no per-cell key.
            # Compare them whole-file: a change is expected, because the two
            # retrained cells feed into every aggregate, but it cannot be
            # attributed to a cell and so must not widen the blast radius.
            if "no key columns" not in str(exc):
                print(f"  ! {exc}")
                rc = 2
                continue
            same = file_sha(b) == file_sha(cur)
            print(f"  aggregate file (no per-cell key): "
                  f"{'unchanged' if same else 'CHANGED'}")
            if not same:
                aggregates_changed.append(b.name)
            continue
        except Exception as exc:  # noqa: BLE001
            print(f"  ! {exc}")
            rc = 2
            continue
        all_changed |= changed
        if not changed:
            print("  unchanged (every row identical)")
        else:
            print(f"  {len(changed)} cell(s) changed:")
            for n in notes:
                print(n)

    print()
    print("=" * 78)
    print("BLAST RADIUS")
    print("=" * 78)
    # pair is always the first key column, so a key looks like
    # (pair, source, target, arch, seed) -> reduce to (pair, arch, seed)
    def norm(k):
        return (k[0], k[3], k[4]) if len(k) >= 5 else k

    got = {norm(k) for k in all_changed}
    print(f"  expected: {sorted(EXPECTED_CHANGED)}")
    print(f"  observed: {sorted(got)}")
    if aggregates_changed:
        print(f"  aggregate files also changed (expected, not cell-attributable): "
              f"{aggregates_changed}")

    unexpected = got - EXPECTED_CHANGED
    missing = EXPECTED_CHANGED - got

    if rc == 2:
        print("\nFAIL: could not complete the comparison (see above).")
        return 2
    if unexpected:
        print(f"\nFAIL: {len(unexpected)} unexpected cell(s) moved: {sorted(unexpected)}")
        print("The retrain perturbed cells it should not have touched.")
        print("Do NOT use the regenerated results until this is understood.")
        return 1
    if missing:
        print(f"\nFAIL: expected cells did not move: {sorted(missing)}")
        print("Either the retrain did not take effect, or the artifacts were not regenerated.")
        return 1

    print("\nPASS: exactly the retrained cells changed; the other 58 are bit-identical.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
