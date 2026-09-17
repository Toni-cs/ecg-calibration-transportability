"""Identify nb_raw (8-element monotone-decaying array) — the likely source
of the 'orig' quantities. Test binning schemes that yield 8 values.
"""
import json
import os
import sys

import numpy as np

ROOT = r"D:/A1/ecg-lab-v2"
sys.path.insert(0, ROOT)
from src.utils.calibration_methods import (  # noqa
    fit_temperature_multiclass, apply_temperature_multiclass)


def toplabel(probs, labels):
    return probs.max(axis=1).astype(float), (probs.argmax(axis=1) == labels).astype(float)


def main():
    a = json.load(open(os.path.join(ROOT, "results",
                                    "strengthening_battle_corrected.json"),
                       encoding="utf-8"))
    r = next(x for x in a if (x["source"], x["target"], x["arch"], x["seed"])
             == ("chapman", "cpsc", "inceptiontime", 42))
    nb = np.array(r["nb_raw"])
    nbt = np.array(r["nb_ts"])
    print("nb_raw =", np.round(nb, 6))
    print("len =", len(nb))

    d = np.load(os.path.join(ROOT, "checkpoints", "e2_probs_cache",
                             "chapman_cpsc_inceptiontime_seed42.npz"),
                allow_pickle=True)
    cal_p, cal_y = d["cal_probs"], d["cal_labels"]
    tgt_p, tgt_y = d["test_probs"], d["test_labels"]
    tp = fit_temperature_multiclass(cal_p, cal_y)
    T = float(tp["T"])
    tgt_ts = apply_temperature_multiclass(tgt_p, tp)

    conf, corr = toplabel(tgt_p, tgt_y)
    cconf, ccorr = toplabel(tgt_ts, tgt_y)

    K = 8
    print("\n--- candidate 8-bin schemes on TEST/raw (conf, corr) ---")
    # A. equal-width 8 bins: per-bin |conf_mean - acc|
    e = np.linspace(0, 1, K + 1)
    vals = []
    for i in range(K):
        m = (conf >= e[i]) & (conf < e[i + 1]) if i < K - 1 else (conf >= e[i]) & (conf <= e[i + 1])
        vals.append(abs(conf[m].mean() - corr[m].mean()) if m.sum() else 0.0)
    print("  equal-width8  |c-a|:", np.round(vals, 6))

    # B. equal-width 8 bins, DESCENDING conf (reverse)
    print("  ... reversed        :", np.round(vals[::-1], 6))

    # C. quantile (equal-frequency) 8 bins
    q = np.quantile(conf, np.linspace(0, 1, K + 1)); q[0], q[-1] = 0.0, 1.0
    q = np.unique(q)
    vals2 = []
    for i in range(len(q) - 1):
        m = (conf >= q[i]) & (conf < q[i + 1]) if i < len(q) - 2 else (conf >= q[i]) & (conf <= q[i + 1])
        vals2.append(abs(conf[m].mean() - corr[m].mean()) if m.sum() else 0.0)
    print("  quantile8     |c-a|:", np.round(vals2, 6))

    # D. cumulative: error of conf>=threshold as threshold descends
    for name, edges in [("equalwidth", e)]:
        cum = []
        for i in range(K):
            thr = edges[K - i - 1]
            m = conf >= thr
            cum.append(abs(conf[m].mean() - corr[m].mean()) if m.sum() else 0.0)
        print("  cumulative conf>=thr:", np.round(cum, 6))

    # E. brier per bin (squared)
    v3 = []
    for i in range(K):
        m = (conf >= e[i]) & (conf < e[i + 1]) if i < K - 1 else (conf >= e[i]) & (conf <= e[i + 1])
        v3.append(float(np.mean((conf[m] - corr[m]) ** 2)) if m.sum() else 0.0)
    print("  eqwidth8 MSE/bin    :", np.round(v3, 6))

    print("\n--- same but on CALIBRATED ---")
    vals_c = []
    for i in range(K):
        m = (cconf >= e[i]) & (cconf < e[i + 1]) if i < K - 1 else (cconf >= e[i]) & (cconf <= e[i + 1])
        vals_c.append(abs(cconf[m].mean() - ccorr[m].mean()) if m.sum() else 0.0
                      )
    print("  equal-width8  |c-a|:", np.round(vals_c, 6))

    print("\n--- what fraction of samples per bin? ---")
    for i in range(K):
        m = (conf >= e[i]) & (conf < e[i + 1]) if i < K - 1 else (conf >= e[i]) & (conf <= e[i + 1])
        print("  bin %d [%.2f,%.2f) n=%4d  conf_mean=%.4f acc=%.4f"
              % (i, e[i], e[i + 1], m.sum(),
                 conf[m].mean() if m.sum() else np.nan,
                 corr[m].mean() if m.sum() else np.nan))


if __name__ == "__main__":
    main()
