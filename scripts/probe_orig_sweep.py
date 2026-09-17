"""Broad forensic sweep for raw_ood_orig / cal_ood_orig.

Strategy: the JSON's raw_ood_orig=0.34742 does NOT equal smooth_ece on the
test split (0.41262). Sweep many candidate functionals x many data splits.
"""
import json
import os
import sys

import numpy as np

ROOT = r"D:/A1/ecg-lab-v2"
sys.path.insert(0, ROOT)

from src.utils.calibration import smooth_ece, ece, mce, brier_parts, brier_raw  # noqa
from src.utils.decomposition import ece_metric_safe  # noqa
from src.utils.calibration_methods import (  # noqa
    fit_temperature_multiclass, apply_temperature_multiclass)

TARGET = 0.34742
CAL_TARGET = 0.33353


def toplabel(probs, labels):
    pred = probs.argmax(axis=1)
    return probs.max(axis=1).astype(float), (pred == labels).astype(float)


# ---------------- candidate functionals ----------------
def smooth_prob_space(conf, corr, bw=None):
    """SmoothECE kernel in PROBABILITY space instead of logit space."""
    conf = np.asarray(conf, float); corr = np.asarray(corr, float)
    n = len(conf)
    h = bw if bw is not None else 0.45 * (n / 2000.0) ** (-0.2)
    err = np.empty(n)
    for i in range(n):
        z = (conf[i] - conf) / h
        w = np.exp(-0.5 * z ** 2)
        err[i] = abs((w * corr).sum() / max(w.sum(), 1e-12) - conf[i])
    return float(err.mean())


def smooth_sq(conf, corr, bw=None):
    """SmoothECE with squared error."""
    conf = np.asarray(conf, float); corr = np.asarray(corr, float)
    n = len(conf)
    h = bw if bw is not None else 0.45 * (n / 2000.0) ** (-0.2)
    p = np.clip(conf, 1e-6, 1 - 1e-6)
    lg = np.log(p / (1 - p))
    err = np.empty(n)
    for i in range(n):
        z = (lg[i] - lg) / h
        w = np.exp(-0.5 * z ** 2)
        err[i] = ((w * corr).sum() / max(w.sum(), 1e-12) - conf[i]) ** 2
    return float(err.mean())


def binned(conf, corr, n_bins=10, equal_freq=False):
    conf = np.asarray(conf, float); corr = np.asarray(corr, float)
    n = len(conf)
    edges = (np.quantile(conf, np.linspace(0, 1, n_bins + 1)) if equal_freq
             else np.linspace(0, 1, n_bins + 1))
    edges = np.unique(edges); edges[0], edges[-1] = 0.0, 1.0
    tot = 0.0
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        m = ((conf >= lo) & (conf < hi) if i < len(edges) - 2
             else (conf >= lo) & (conf <= hi))
        if m.sum() == 0:
            continue
        tot += m.sum() / n * abs(conf[m].mean() - corr[m].mean())
    return float(tot)


def rms_binned(conf, corr, n_bins=10):
    conf = np.asarray(conf, float); corr = np.asarray(corr, float)
    n = len(conf)
    edges = np.linspace(0, 1, n_bins + 1)
    tot = 0.0
    for i in range(n_bins):
        m = ((conf >= edges[i]) & (conf < edges[i + 1]) if i < n_bins - 1
             else (conf >= edges[i]) & (conf <= edges[i + 1]))
        if m.sum() == 0:
            continue
        tot += m.sum() / n * (conf[m].mean() - corr[m].mean()) ** 2
    return float(np.sqrt(tot))


def classwise_ece(probs, labels, n_bins=10):
    """Kull et al. 2019 classwise-ECE: mean over K binary problems."""
    probs = np.asarray(probs, float); labels = np.asarray(labels)
    K = probs.shape[1]
    tot = 0.0
    for k in range(K):
        tot += binned(probs[:, k], (labels == k).astype(float), n_bins)
    return float(tot / K)


def per_class_marginal_mean(probs, labels, n_bins=10):
    probs = np.asarray(probs, float); labels = np.asarray(labels)
    K = probs.shape[1]
    vals = []
    for k in range(K):
        m = labels == k
        if m.sum() == 0:
            continue
        vals.append(binned(probs[m, k], np.ones(m.sum()), n_bins))
    return float(np.mean(vals))


def top_label_only_ece(conf, corr, n_bins=10, thresh=0.5):
    """ECE restricted to top-label conf above thresh."""
    conf = np.asarray(conf, float); corr = np.asarray(corr, float)
    m = conf >= thresh
    return binned(conf[m], corr[m], n_bins)


def ece_all_samples_flattened(probs, labels, n_bins=10):
    probs = np.asarray(probs, float); labels = np.asarray(labels)
    K = probs.shape[1]
    return binned(probs.ravel(), np.eye(K)[labels].ravel(), n_bins)


def run_split(tag, probs_raw, probs_cal, labels):
    conf, corr = toplabel(probs_raw, labels)
    cconf, ccorr = toplabel(probs_cal, labels)
    out = {}
    out["smooth_ece(logit,abs)"] = (smooth_ece(conf, corr), smooth_ece(cconf, ccorr))
    out["smooth_prob_space"] = (smooth_prob_space(conf, corr), smooth_prob_space(cconf, ccorr))
    out["smooth_sq"] = (smooth_sq(conf, corr), smooth_sq(cconf, ccorr))
    out["binned10_eqwidth"] = (binned(conf, corr), binned(cconf, ccorr))
    out["binned10_eqfreq"] = (binned(conf, corr, equal_freq=True),
                              binned(cconf, ccorr, equal_freq=True))
    out["binned15"] = (binned(conf, corr, 15), binned(cconf, ccorr, 15))
    out["binned20"] = (binned(conf, corr, 20), binned(cconf, ccorr, 20))
    out["binned_sqrt_n"] = (binned(conf, corr, int(np.sqrt(len(conf)))),
                            binned(cconf, ccorr, int(np.sqrt(len(cconf)))))
    out["ece_metric_safe(10bin)"] = (ece_metric_safe(conf, corr), ece_metric_safe(cconf, ccorr))
    out["rms_binned10"] = (rms_binned(conf, corr), rms_binned(cconf, ccorr))
    out["mce10"] = (mce(conf, corr), mce(cconf, ccorr))
    out["brier_reliability"] = (brier_parts(conf, corr)[1], brier_parts(cconf, ccorr)[1])
    out["brier_sqrt_reliability"] = (np.sqrt(brier_parts(conf, corr)[1]),
                                     np.sqrt(brier_parts(cconf, ccorr)[1]))
    out["brier_raw"] = (brier_raw(conf, corr), brier_raw(cconf, ccorr))
    out["classwise_ece(Kull)"] = (classwise_ece(probs_raw, labels),
                                  classwise_ece(probs_cal, labels))
    out["per_class_marginal_mean"] = (per_class_marginal_mean(probs_raw, labels),
                                      per_class_marginal_mean(probs_cal, labels))
    out["toplabel_only_conf>=.5"] = (top_label_only_ece(conf, corr),
                                     top_label_only_ece(cconf, ccorr))
    out["all_samples_flattened"] = (ece_all_samples_flattened(probs_raw, labels),
                                    ece_all_samples_flattened(probs_cal, labels))
    out["repo_ece(10bin)"] = (ece(conf, corr), ece(cconf, ccorr))
    return out


def main():
    with open(os.path.join(ROOT, "results",
                           "strengthening_battle_corrected.json"),
              encoding="utf-8") as f:
        recs = json.load(f)
    r = next(x for x in recs if (x["source"], x["target"], x["arch"],
                                 x["seed"]) == ("chapman", "cpsc", "inceptiontime", 42))
    print("JSON targets: raw_ood_orig=%.5f cal_ood_orig=%.5f delta=%.5f"
          % (r["raw_ood_orig"], r["cal_ood_orig"], r["delta_obs_orig"]))

    d = np.load(os.path.join(ROOT, "checkpoints", "e2_probs_cache",
                             "chapman_cpsc_inceptiontime_seed42.npz"),
                allow_pickle=True)
    cal_p, cal_y = d["cal_probs"], d["cal_labels"]
    tgt_p, tgt_y = d["test_probs"], d["test_labels"]
    tp = fit_temperature_multiclass(cal_p, cal_y)
    T = float(tp["T"])
    print("T=%.6f" % T)

    tgt_ts = apply_temperature_multiclass(tgt_p, tp)
    cal_ts = apply_temperature_multiclass(cal_p, tp)

    print("\n" + "=" * 96)
    print("SPLIT = TEST (OOD target domain)")
    print("=" * 96)
    res = run_split("test", tgt_p, tgt_ts, tgt_y)
    rows = sorted(((abs(v[0] - TARGET), k, v) for k, v in res.items()))
    for diff, k, v in rows[:14]:
        print("  %-28s raw=%.5f (|d|=%.5f)  cal=%.5f (|d|=%.5f)  delta=%+.5f"
              % (k, v[0], abs(v[0] - TARGET), v[1], abs(v[1] - CAL_TARGET),
                 v[0] - v[1]))

    print("\n" + "=" * 96)
    print("SPLIT = CAL (source calibration domain)")
    print("=" * 96)
    res2 = run_split("cal", cal_p, cal_ts, cal_y)
    rows2 = sorted(((abs(v[0] - TARGET), k, v) for k, v in res2.items()))
    for diff, k, v in rows2[:14]:
        print("  %-28s raw=%.5f (|d|=%.5f)  cal=%.5f (|d|=%.5f)  delta=%+.5f"
              % (k, v[0], abs(v[0] - TARGET), v[1], abs(v[1] - CAL_TARGET),
                 v[0] - v[1]))


if __name__ == "__main__":
    main()
