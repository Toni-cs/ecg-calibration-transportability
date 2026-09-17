"""Trace what delta_obs_orig actually IS.

The rebuild script claims delta_obs_orig = smooth_ece(raw) - smooth_ece(TS).
My independent reproduction of that exact formula gives +0.1066 == delta_obs.
So EITHER the rebuild script never ran on these artifacts, OR the json was
produced by a different code path. Reverse-engineer the functional.
"""
import os
import sys
import json
import math

import numpy as np

ROOT = r"D:\A1\ecg-lab-v2"
sys.path.insert(0, ROOT)
from src.utils.calibration import smooth_ece  # noqa
from src.utils.calibration_methods import (  # noqa
    fit_temperature_multiclass, apply_temperature_multiclass)

CACHE = os.path.join(ROOT, "checkpoints", "e2_probs_cache")


def toplabel(p, y):
    return p.max(axis=1).astype(float), (p.argmax(axis=1) == y).astype(float)


def flat_marginal(probs, labels, K):
    """Stack all classes: conf = p[:,k], corr = (y==k). length n*K."""
    c = probs.reshape(-1).astype(float)
    y1 = np.zeros_like(probs)
    for k in range(K):
        y1[:, k] = (labels == k)
    return c, y1.reshape(-1).astype(float)


def main():
    js = json.load(open(os.path.join(ROOT, "results",
                                     "strengthening_battle_corrected.json")))
    files = sorted(f for f in os.listdir(CACHE) if f.endswith(".npz"))
    print("%-46s %9s %9s %9s %9s %9s" %
          ("cell", "json_orig", "d_smooth", "n_ood", "raw_orig", "cal_orig"))

    diffs = []
    for r in js:
        key = "%s_%s_%s_seed%d" % (r["source"], r["target"], r["arch"], r["seed"])
        fn = key + ".npz"
        if fn not in files:
            print(key, "NO NPZ")
            continue
        d = np.load(os.path.join(CACHE, fn), allow_pickle=True)
        cp, cy = d["cal_probs"], d["cal_labels"]
        tp, ty = d["test_probs"], d["test_labels"]
        K = d["num_classes"].item()
        par = fit_temperature_multiclass(cp, cy)
        tsp = apply_temperature_multiclass(tp, par)
        rc, ry = toplabel(tp, ty)
        tc, tyy = toplabel(tsp, ty)
        d_smooth = smooth_ece(rc, ry) - smooth_ece(tc, tyy)
        m_rc, m_ry = flat_marginal(tp, ty, K)
        m_tc, m_ty = flat_marginal(tsp, ty, K)
        d_marg = smooth_ece(m_rc, m_ry) - smooth_ece(m_tc, m_ty)

        print("%-46s %+9.5f %+9.5f %9d %9.5f %9.5f" %
              (key[:46], r["delta_obs_orig"], d_smooth, len(ty),
               r.get("raw_ood_orig", np.nan), r.get("cal_ood_orig", np.nan)))
        diffs.append((r["delta_obs_orig"], d_smooth, d_marg,
                      r.get("raw_ood_orig", np.nan),
                      r.get("cal_ood_orig", np.nan), len(ty), par["T"]))

    a = np.array(diffs, float)
    print("\n=== SUMMARY ===")
    print("n =", len(a))
    print("json delta_obs_orig   mean %+.6f" % a[:, 0].mean())
    print("my smooth_ece (topL)  mean %+.6f" % a[:, 1].mean())
    print("my smooth_ece (marg)  mean %+.6f" % a[:, 2].mean())
    print("raw_ood_orig(json) mean %.6f" % np.nanmean(a[:, 3]))
    print("cal_ood_orig(json) mean %.6f" % np.nanmean(a[:, 4]))

    # Is json_orig simply raw-cal from json?
    rec = a[:, 3] - a[:, 4]
    print("mean(json raw - json cal) = %+.6f  vs json_orig mean %+.6f"
          % (np.nanmean(rec), a[:, 0].mean()))
    print("max|diff| = %.3e" % np.nanmax(np.abs(rec - a[:, 0])))

    print("\ncorr(T, json_orig) = %+.4f  R2=%.4f" %
          (np.corrcoef(a[:, 6], a[:, 0])[0, 1],
           np.corrcoef(a[:, 6], a[:, 0])[0, 1] ** 2))
    print("corr(T, my smooth) = %+.4f  R2=%.4f" %
          (np.corrcoef(a[:, 6], a[:, 1])[0, 1],
           np.corrcoef(a[:, 6], a[:, 1])[0, 1] ** 2))
    print("corr(json_orig, my smooth) = %+.4f" % np.corrcoef(a[:, 0], a[:, 1])[0, 1])

    # sign rate / t
    n = len(a)
    for name, v in [("json_orig", a[:, 0]), ("my smooth", a[:, 1]),
                    ("marginal", a[:, 2])]:
        print("%-12s mean %+.4f pos %.1f%% t %.3f" %
              (name, v.mean(), 100 * (v > 0).mean(),
               v.mean() / (v.std(ddof=1) / math.sqrt(n))))


if __name__ == "__main__":
    main()
