"""Forensic probe: what functional produces raw_ood_orig / cal_ood_orig?

Follows scripts/rebuild_shapley_crossfit.py exactly to test whether
smooth_ece(target_toplabel_conf, target_toplabel_correct) reproduces
the JSON's raw_ood_orig.
"""
import json
import os
import sys

import numpy as np

ROOT = r"D:/A1/ecg-lab-v2"
sys.path.insert(0, ROOT)

from src.utils.calibration import smooth_ece, ece, mce  # noqa: E402
from src.utils.calibration_methods import (  # noqa: E402
    fit_temperature_multiclass, apply_temperature_multiclass)


def _toplabel(probs, labels):
    pred = probs.argmax(axis=1)
    conf = probs.max(axis=1)
    correct = (pred == labels).astype(float)
    return conf, correct


def probe(cell, exp):
    npz = os.path.join(ROOT, "checkpoints", "e2_probs_cache", cell + ".npz")
    d = np.load(npz, allow_pickle=True)
    cal_p, cal_y = d["cal_probs"], d["cal_labels"]
    tgt_p, tgt_y = d["test_probs"], d["test_labels"]

    tp = fit_temperature_multiclass(cal_p, cal_y)
    T = float(tp["T"])
    print("=" * 78)
    print(cell)
    print("  T fitted      = %.6f   (JSON T = %.6f)" % (T, exp["T"]))

    cal_conf, cal_corr = _toplabel(cal_p, cal_y)
    tgt_conf, tgt_corr = _toplabel(tgt_p, tgt_y)

    tgt_p_ts = apply_temperature_multiclass(tgt_p, tp)
    ts_conf, ts_corr = _toplabel(tgt_p_ts, tgt_y)

    raw_sm = smooth_ece(tgt_conf, tgt_corr)
    cal_sm = smooth_ece(ts_conf, ts_corr)

    print("  --- script L113-117 path (smooth_ece, top-label, test split) ---")
    print("  raw smooth_ece        = %.5f   (JSON raw_ood_orig = %.5f)"
          % (raw_sm, exp["raw_ood_orig"]))
    print("  cal smooth_ece        = %.5f   (JSON cal_ood_orig = %.5f)"
          % (cal_sm, exp["cal_ood_orig"]))
    print("  delta (raw-cal)       = %.5f   (JSON delta_obs_orig = %.5f)"
          % (raw_sm - cal_sm, exp["delta_obs_orig"]))
    print("  n_test = %d  n_cal = %d" % (len(tgt_y), len(cal_y)))
    print("  h_test = %.5f" % (0.45 * (len(tgt_conf) / 2000.0) ** (-0.2)))

    # bandwididth sweep
    print("  --- bandwidth sweep on raw (test/top-label) ---")
    for h in [0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75]:
        print("     h=%.2f  raw=%.5f  cal=%.5f  d=%.5f"
              % (h, smooth_ece(tgt_conf, tgt_corr, h),
                 smooth_ece(ts_conf, ts_corr, h),
                 smooth_ece(tgt_conf, tgt_corr, h) - smooth_ece(ts_conf, ts_corr, h)))

    print("  --- variants ---")
    print("     smooth_ece(raw PROBS on all 4 classes flattened) = %.5f"
          % smooth_ece(tgt_p.ravel(), np.eye(tgt_p.shape[1])[tgt_y].ravel()))
    print("     ece(top-label, 10 bins)   = %.5f" % ece(tgt_conf, tgt_corr))
    print("     mce(top-label, 10 bins)   = %.5f" % mce(tgt_conf, tgt_corr))

    for k in ("delta_obs", "nb_gain", "nb_raw", "nb_ts", "shapley"):
        if k in exp:
            print("  JSON %s = %s" % (k, exp[k]))


def main():
    with open(os.path.join(ROOT, "results",
                           "strengthening_battle_corrected.json"),
              encoding="utf-8") as f:
        recs = json.load(f)

    want = [
        ("chapman_cpsc_inceptiontime_seed42", ("chapman", "cpsc", "inceptiontime", 42)),
    ]
    for cell, key in want:
        r = next((x for x in recs if (x.get("source"), x.get("target"),
                                      x.get("arch"), x.get("seed")) == key), None)
        if r is None:
            print("NOT FOUND:", key)
            continue
        probe(cell, r)


if __name__ == "__main__":
    main()
