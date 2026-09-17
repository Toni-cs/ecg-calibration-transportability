"""ADVERSARIAL PROBE: attack the +0.0159 headline.

Convention matrix over 60 main cells. For each cell and each convention,
compute ECE_raw and ECE_TS, then delta = raw - ts.

All ECE implementations imported from repo. Binned variants re-implemented
locally ONLY because repo has no parametric binned-ECE on top-label conf
(repo ece_metric_safe is 10-bin equal-width, imported and used as-is).
"""
import csv
import glob
import os
import sys
import math
import json

import numpy as np

ROOT = r"D:\A1\ecg-lab-v2"
sys.path.insert(0, ROOT)

from src.utils.calibration import smooth_ece  # noqa
from src.utils.decomposition import ece_metric_safe  # noqa
from src.utils.calibration_methods import (  # noqa
    fit_temperature_multiclass, apply_temperature_multiclass)

CACHE = os.path.join(ROOT, "checkpoints", "e2_probs_cache")
ARCHS = ("inceptiontime", "resnet1d")
SEEDS = (42, 43, 44, 45, 46)


def toplabel(probs, labels):
    pred = probs.argmax(axis=1)
    return probs.max(axis=1).astype(float), (pred == labels).astype(float)


def binned_ece(conf, corr, n_bins=10, scheme="equal_width"):
    """Local binned ECE on top-label confidences."""
    conf = np.asarray(conf, float)
    corr = np.asarray(corr, float)
    n = len(conf)
    if scheme == "equal_width":
        edges = np.linspace(0.0, 1.0, n_bins + 1)
    else:  # equal_freq
        edges = np.quantile(conf, np.linspace(0, 1, n_bins + 1))
        edges[0], edges[-1] = 0.0, 1.0
        edges = np.unique(edges)
    tot = 0.0
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        m = (conf >= lo) & (conf < hi) if i < len(edges) - 2 else (conf >= lo) & (conf <= hi)
        if m.sum() == 0:
            continue
        tot += m.sum() / n * abs(conf[m].mean() - corr[m].mean())
    return float(tot)


def brier_reliability(conf, corr, n_bins=10):
    conf = np.asarray(conf, float); corr = np.asarray(corr, float)
    n = len(conf)
    edges = np.linspace(0, 1, n_bins + 1)
    tot = 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        m = (conf >= lo) & (conf < hi) if i < n_bins - 1 else (conf >= lo) & (conf <= hi)
        if m.sum() == 0:
            continue
        tot += m.sum() / n * (conf[m].mean() - corr[m].mean()) ** 2
    return float(tot)


def mce(conf, corr, n_bins=10):
    conf = np.asarray(conf, float); corr = np.asarray(corr, float)
    edges = np.linspace(0, 1, n_bins + 1)
    worst = 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        m = (conf >= lo) & (conf < hi) if i < n_bins - 1 else (conf >= lo) & (conf <= hi)
        if m.sum() == 0:
            continue
        worst = max(worst, abs(conf[m].mean() - corr[m].mean()))
    return float(worst)


def rms_cal_err(conf, corr, n_bins=10):
    conf = np.asarray(conf, float); corr = np.asarray(corr, float)
    n = len(conf)
    edges = np.linspace(0, 1, n_bins + 1)
    tot = 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        m = (conf >= lo) & (conf < hi) if i < n_bins - 1 else (conf >= lo) & (conf <= hi)
        if m.sum() == 0:
            continue
        tot += m.sum() / n * (conf[m].mean() - corr[m].mean()) ** 2
    return float(math.sqrt(tot))


def parse(fname):
    base = fname[:-4]
    p = base.split("_")
    if len(p) < 4 or not p[-1].startswith("seed"):
        return None
    src, tgt = p[0], p[1]
    arch = "_".join(p[2:-1])
    try:
        seed = int(p[-1][4:])
    except ValueError:
        return None
    return src, tgt, arch, seed


# convention registry: name -> fn(conf, corr) -> float
CONVENTIONS = {
    "smooth_ece_h_default": lambda c, y: smooth_ece(c, y),
    "smooth_ece_h_0.45": lambda c, y: smooth_ece(c, y, bandwidth=0.45),
    "ece_bin10_eqwidth": lambda c, y: binned_ece(c, y, 10, "equal_width"),
    "ece_bin15_eqwidth": lambda c, y: binned_ece(c, y, 15, "equal_width"),
    "ece_bin20_eqwidth": lambda c, y: binned_ece(c, y, 20, "equal_width"),
    "ece_bin10_eqfreq": lambda c, y: binned_ece(c, y, 10, "equal_freq"),
    "repo_ece_metric_safe": lambda c, y: ece_metric_safe(c, y),
    "brier_reliability10": lambda c, y: brier_reliability(c, y, 10),
    "mce_bin10": lambda c, y: mce(c, y, 10),
    "rms_ce_bin10": lambda c, y: rms_cal_err(c, y, 10),
}


def main():
    files = sorted(f for f in os.listdir(CACHE) if f.endswith(".npz"))
    cells = []
    for f in files:
        m = parse(f)
        if m is None or m[2] not in ARCHS or m[3] not in SEEDS:
            continue
        cells.append((f, m))
    print("main cells found: %d (expect 60)" % len(cells))

    results = []
    T_list = []
    for fname, (src, tgt, arch, seed) in cells:
        d = np.load(os.path.join(CACHE, fname), allow_pickle=True)
        cal_p, cal_y = d["cal_probs"], d["cal_labels"]
        tst_p, tst_y = d["test_probs"], d["test_labels"]

        tp = fit_temperature_multiclass(cal_p, cal_y)
        T = float(tp["T"])
        T_list.append(T)

        raw_conf, raw_corr = toplabel(tst_p, tst_y)
        ts_p = apply_temperature_multiclass(tst_p, tp)
        ts_conf, ts_corr = toplabel(ts_p, tst_y)

        rec = {"cell": fname[:-4], "source": src, "target": tgt,
               "arch": arch, "seed": seed, "T": T,
               "n_ood": len(tst_y)}
        for cname, fn in CONVENTIONS.items():
            rec["raw_" + cname] = fn(raw_conf, raw_corr)
            rec["ts_" + cname] = fn(ts_conf, ts_corr)
            rec["d_" + cname] = rec["raw_" + cname] - rec["ts_" + cname]
        # raw smooth ece as reported in json (unnormalized toplabel? same)
        results.append(rec)

    # cross-check vs paper json
    main_json = json.load(open(os.path.join(ROOT, "results",
                                            "strengthening_battle_corrected.json")))
    bycell = {}
    for r in main_json:
        k = r.get("cell") or "%s_%s_%s_seed%d" % (
            r["source"], r["target"], r["arch"], r["seed"])
        bycell[k] = r
    dd = []
    for r in results:
        key = "%s_%s_%s_seed%d" % (r["source"], r["target"], r["arch"], r["seed"])
        j = bycell.get(key)
        if j is None:
            dd.append((r["cell"], "MISSING_IN_JSON", None))
            continue
        dd.append((key, j["delta_obs_orig"] - r["d_smooth_ece_h_default"],
                   j["delta_obs_orig"]))
    print("\n=== CROSS-CHECK: my smooth_ece vs json delta_obs_orig ===")
    errs = [abs(x[1]) for x in dd if x[1] is not None]
    print("matched n=%d  max|err|=%.3e  mean|err|=%.3e"
          % (len(errs), max(errs) if errs else -1,
             np.mean(errs) if errs else -1))
    miss = [x for x in dd if x[1] is None]
    if miss:
        print("missing in json:", miss[:5])

    # convention matrix
    print("\n=== CONVENTION MATRIX: mean deltaECE over 60 cells ===")
    print("%-24s %10s %10s %10s %10s %10s" %
          ("convention", "mean_d", "median_d", "pos_rate", "t_stat", "corr(T)"))
    matrix = {}
    Ts = np.array(T_list)
    for cname in CONVENTIONS:
        v = np.array([r["d_" + cname] for r in results], float)
        n = len(v)
        m = v.mean()
        sd = v.std(ddof=1)
        t = m / (sd / math.sqrt(n))
        cT = np.corrcoef(v, Ts)[0, 1]
        pos = (v > 0).sum() / n
        matrix[cname] = {"mean": m, "median": float(np.median(v)),
                         "pos_rate": float(pos), "t": float(t),
                         "corrT": float(cT)}
        print("%-24s %+10.4f %+10.4f %9.1f%% %10.3f %+10.4f"
              % (cname, m, np.median(v), 100 * pos, t, cT))

    print("\nPAPER TARGET: mean=+0.0159  pos_rate=82.0%  t=6.434 (df=59)")
    print("\n=== PER-CONVENTION MATCH SCORE vs paper triple ===")
    for cname, s in matrix.items():
        sc = 0
        if abs(s["mean"] - 0.0159) < 0.0015:
            sc += 1
        if abs(s["pos_rate"] - 0.82) < 0.02:
            sc += 1
        if abs(s["t"] - 6.434) < 0.15:
            sc += 1
        flag = "  <<< MATCH x%d" % sc if sc > 0 else ""
        print("%-24s mean=%+.4f(%.4f) pos=%.0f%% t=%.3f  score=%d%s"
              % (cname, s["mean"], abs(s["mean"] - 0.0159),
                 100 * s["pos_rate"], s["t"], sc, flag))

    with open(os.path.join(ROOT, "scripts", "_probe_convmatrix.csv"), "w",
              newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0].keys()))
        w.writeheader()
        w.writerows(results)
    with open(os.path.join(ROOT, "scripts", "_probe_matrix_summary.json"), "w",
              encoding="utf-8") as f:
        json.dump({"matrix": matrix, "n": len(results)}, f, indent=2)
    print("\nwrote _probe_convmatrix.csv / _probe_matrix_summary.json")


if __name__ == "__main__":
    main()
