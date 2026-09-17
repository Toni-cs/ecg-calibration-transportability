#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Recompute `results/ablation_ts_components.csv` under the ORIGINAL label encoding.

=====================================================================
Why this script exists
=====================================================================
``checkpoints/e2_probs_cache/*.npz`` stores ``probs`` and ``labels`` together,
but the two arrays come from **different encodings**:

* **probs** are the output of checkpoints trained on 2026-09-08, when
  ``SUBSPACE_CPSC = ("NORM","CD","STTC","MI")`` (OLD). Column 1 is therefore
  CD and column 3 is MI.
  First-party evidence: every ``checkpoints/transfer/**/transfer_result.json``
  archives its own ``label_map``, and all 40 CPSC-containing cells record
  ``{"CD":1,"MI":3,"NORM":0,"STTC":2}``.

* **labels** were written *after* the 2026-09-09 encoding change, so they follow
  ``("NORM","MI","STTC","CD")`` (NEW): index 1 is MI and index 3 is CD.
  Evidence: the CPSC test labels in the cache are
  ``[NORM=183, ?1=303, STTC=1086, ?3=485]`` (n = 2057), i.e. 8.90% / 14.73% /
  52.80% / 23.58%. The full-corpus distribution recorded in
  ``data/cpsc_processed/preprocess_summary.json`` is NORM 8.88% / MI 14.71% /
  STTC 52.75% / CD 23.55% / HYP 0.11%. The match pins index 1 = MI and
  index 3 = CD, i.e. the labels are NEW.

Consequently, when ``run_e2_ablation_discrimination.py`` produced
``ablation_ts_components.csv`` on 2026-09-10 it consumed a cache whose probs and
labels disagreed: the model places its CD mass in column 1 while the ground
truth in column 1 is MI. CD and MI — 38.3% of the samples — are then scored
wrong, which inflates the raw ECE.

Fingerprint of the mismatch (``ptbxl→cpsc/resnet1d/seed42``): patients whose
NEW label is 1 (= MI) are classified as argmax **3** in 250/303 = 82.5% of
cases, and patients whose NEW label is 3 (= CD) as argmax **1** in 42.5%. A
consistent encoding would put the diagonal on top, so the probs must be OLD.

=====================================================================
What this script does
=====================================================================
For each cell, if ``"cpsc" in (source, target)`` — i.e. ``num_classes == 4``, so
the labels live in the CPSC 4-class subspace — it applies ``swap13`` (1↔3) to
``cal_labels``/``test_labels`` to restore the OLD encoding, then recomputes all
four stages through **exactly the same functions** as the original script.

Only the labels are permuted; ``probs`` are untouched. This restores the
archived truth rather than reinterpreting it.

Requires ``checkpoints/e2_probs_cache/`` and ``checkpoints/transfer/`` to be
present (both are excluded from version control), so this script is intended
for the development workspace.

Usage::

    python scripts/recompute_ablation_old_encoding.py
    python scripts/recompute_ablation_old_encoding.py --write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.utils.calibration_methods import (  # noqa: E402
    apply_temperature_multiclass,
    fit_temperature_multiclass,
)
from run_e2_ablation_discrimination import (  # noqa: E402
    apply_binned_temperature,
    calibration_reliability,
    fit_binned_temperature,
    optimize_thresholds,
)

CSV_IN = _PROJECT_ROOT / "results" / "ablation_ts_components.csv"
CSV_OUT = _PROJECT_ROOT / "results" / "ablation_ts_components.OLD_ENCODING.csv"
CACHE_DIR = _PROJECT_ROOT / "checkpoints" / "e2_probs_cache"

# OLD integer -> NEW integer: OLD 1 (CD) -> NEW 3; OLD 3 (MI) -> NEW 1
PERM = np.array([0, 3, 2, 1], dtype=np.int64)


def npz_old_labels(source: str, target: str, arch: str, seed: int):
    """Return (cal_probs, cal_labels_OLD, test_probs, test_labels_OLD, K).

    CPSC-containing cells (num_classes == 4) need the swap13 restoration;
    chapman<->ptbxl cells (5 classes) are left alone.
    """
    p = CACHE_DIR / f"{source}_{target}_{arch}_seed{seed}.npz"
    if not p.exists():
        return None
    d = np.load(p, allow_pickle=True)
    is_cpsc = ("cpsc" in source) or ("cpsc" in target)
    cal_y = d["cal_labels"].astype(np.int64)
    tst_y = d["test_labels"].astype(np.int64)
    if is_cpsc:
        cal_y = PERM[cal_y]
        tst_y = PERM[tst_y]
    return d["cal_probs"], cal_y, d["test_probs"], tst_y, int(d["num_classes"])


def recompute_cell(source, target, arch, seed):
    """Recompute the four stage rows for one cell; returns list[dict] or None."""
    got = npz_old_labels(source, target, arch, seed)
    if got is None:
        return None
    cal_p, cal_y, test_p, test_y, K = got

    ts_params = fit_temperature_multiclass(cal_p, cal_y)
    T_global = float(ts_params["T"])
    cal_s1 = apply_temperature_multiclass(cal_p, ts_params)
    test_s1 = apply_temperature_multiclass(test_p, ts_params)

    binned_params = fit_binned_temperature(cal_s1, cal_y)
    cal_s2 = apply_binned_temperature(cal_s1, binned_params)
    test_s2 = apply_binned_temperature(test_s1, binned_params)
    T_binned = binned_params["temperatures"]

    tau = optimize_thresholds(cal_s2, cal_y, K)
    cal_s3, test_s3 = cal_s2, test_s2

    rows = []
    for stage_name, probs in [
        ("raw", test_p),
        ("stage1_ts", test_s1),
        ("stage2_ts_binned", test_s2),
        ("stage3_ts_binned_threshold", test_s3),
    ]:
        rel = calibration_reliability(probs, test_y)
        row = {
            "source": source, "target": target, "arch": arch, "seed": seed,
            "stage": stage_name, "n_samples": len(test_y),
            "T_global": T_global if stage_name != "raw" else np.nan,
            "T_binned_mean": float(np.mean(T_binned)) if "binned" in stage_name else np.nan,
            "T_binned_min": float(np.min(T_binned)) if "binned" in stage_name else np.nan,
            "T_binned_max": float(np.max(T_binned)) if "binned" in stage_name else np.nan,
            "threshold_norm": float(np.linalg.norm(tau)) if "threshold" in stage_name else 0.0,
        }
        row.update(rel)
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="write the corrected CSV")
    args = ap.parse_args()

    df = pd.read_csv(CSV_IN)
    cols = list(df.columns)
    print(f"read {CSV_IN.name}: {len(df)} rows, "
          f"{df.groupby(['source','target','arch','seed']).ngroups} cells")

    out_rows = []
    failed = []
    for (s, t, a, sd), _g in df.groupby(["source", "target", "arch", "seed"], sort=False):
        r = recompute_cell(s, t, a, int(sd))
        if r is None:
            failed.append((s, t, a, sd))
        else:
            out_rows.extend(r)

    if failed:
        print(f"[WARN] {len(failed)} cells without an npz cache: {failed[:5]}")

    if not out_rows:
        print("\n[ABORT] no cell could be recomputed — "
              f"'{CACHE_DIR}' is missing or empty.")
        print("        The probability cache is excluded from version control; "
              "this script must run in the development workspace.")
        return

    new = pd.DataFrame(out_rows)
    # delta_rel_vs_raw, same convention as run_e2_ablation_discrimination.py:657
    _pv = new.pivot_table(index=["source", "target", "arch", "seed"],
                          columns="stage", values="brier_reliability")
    if "stage1_ts" in _pv.columns and "raw" in _pv.columns:
        new = new.merge(_pv["raw"].rename("raw_base").reset_index(),
                        on=["source", "target", "arch", "seed"], how="left")
        new["delta_rel_vs_raw"] = new["brier_reliability"] - new["raw_base"]
        new = new.drop(columns=["raw_base"])
    else:
        new["delta_rel_vs_raw"] = np.nan
    new = new[cols]
    old = df.copy()

    key = ["source", "target", "arch", "seed", "stage"]
    m = old.merge(new, on=key, suffixes=("_old_csv", "_old_enc"), how="inner")
    print(f"element-wise pairs matched: {len(m)}/{len(df)}")

    print("\n=== stage=raw: smooth_ece ===")
    for tag, col in [("CSV as shipped (mismatched/NEW)", "smooth_ece_old_csv"),
                     ("recomputed OLD (correct)", "smooth_ece_old_enc")]:
        v = m.loc[m.stage == "raw", col].astype(float)
        print(f"  {tag:32s} n={len(v)} mean={v.mean():.4f} min={v.min():.4f} max={v.max():.4f}")
    d = (m.loc[m.stage == "raw", "smooth_ece_old_csv"].astype(float)
         - m.loc[m.stage == "raw", "smooth_ece_old_enc"].astype(float))
    print(f"  max|CSV-OLD| = {d.abs().max():.6f}   identical {int((d.abs()<1e-12).sum())}/{len(d)}")

    print("\n=== stage=raw: CPSC-containing vs not ===")
    mr = m[m.stage == "raw"].copy()
    mr["is_cpsc"] = mr.apply(lambda r: ("cpsc" in r["source"]) or ("cpsc" in r["target"]), axis=1)
    for tag, sub in [("CPSC", mr[mr.is_cpsc]), ("non-CPSC", mr[~mr.is_cpsc])]:
        a1 = sub["smooth_ece_old_csv"].astype(float)
        a2 = sub["smooth_ece_old_enc"].astype(float)
        print(f"  {tag:9s} n={len(sub):3d}  CSV mean={a1.mean():.4f} [{a1.min():.4f},{a1.max():.4f}]"
              f"  OLD mean={a2.mean():.4f} [{a2.min():.4f},{a2.max():.4f}]")

    print("\n=== T_global (60 main cells, mamba excluded) ===")
    tm = new[(new.stage == "stage1_ts") & (~new.arch.str.contains("mamba"))]
    T = tm["T_global"].astype(float)
    print(f"  n={len(T)}  median={T.median():.4f}  min={T.min():.4f}  max={T.max():.4f}"
          f"  T>=2: {int((T>=2).sum())}/{len(T)} = {(T>=2).mean()*100:.1f}%")

    print("\n=== counter-examples (dECE_OOD = raw - TS < 0, i.e. TS helps) ===")
    piv = new.pivot_table(index=["source", "target", "arch", "seed"], columns="stage",
                          values="smooth_ece", aggfunc="first")
    piv["dECE"] = piv["raw"] - piv["stage1_ts"]          # same sign as the primary endpoint
    piv60 = piv[~piv.index.get_level_values("arch").str.contains("mamba")]
    neg = piv60[piv60.dECE < 0]
    pos = piv60[piv60.dECE >= 0]
    print(f"  60 main cells: dECE>0 {len(pos)}/{len(piv60)},  dECE<0 (counter-examples) {len(neg)}/{len(piv60)}")
    if len(neg):
        print(f"  counter-example raw smooth_ece: min={neg['raw'].min():.4f} max={neg['raw'].max():.4f}"
              f" mean={neg['raw'].mean():.4f}")
        print(f"  counter-example dECE range: [{neg.dECE.min():.4f}, {neg.dECE.max():.4f}]")
    print(f"  all 60 cells raw smooth_ece: min={piv60['raw'].min():.4f} "
          f"max={piv60['raw'].max():.4f} mean={piv60['raw'].mean():.4f}")

    if args.write:
        new.to_csv(CSV_OUT, index=False)
        print(f"\n[OK] wrote {CSV_OUT}")
    else:
        print("\n(not written; pass --write to emit the corrected CSV)")


if __name__ == "__main__":
    main()
