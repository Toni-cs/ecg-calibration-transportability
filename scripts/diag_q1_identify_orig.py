"""Q1 诊断：raw_ood_orig / cal_ood_orig 到底是什么量？

目标锚点（cell = chapman_cpsc_inceptiontime_seed42）：
    raw_ood_orig = 0.3474239249443988
    cal_ood_orig = 0.3335284685932505
    (已知 smooth_ece(top-label, ood_raw) = 0.4126247553697963)

策略：不猜。对同一 cell 枚举「度量 x 数据源 x 子采样 x 带宽」大量候选，
打印每个候选值，找出同时命中 raw 与 cal 的那个组合。

用法：/c/python/python.exe -X faulthandler scripts/diag_q1_identify_orig.py
"""
import json
import os
import sys

import numpy as np

ROOT = r"D:/A1/ecg-lab-v2"
sys.path.insert(0, ROOT)

from src.utils.calibration import smooth_ece, ece as ece_repo  # noqa: E402
from src.utils.decomposition import ece_metric_safe  # noqa: E402
from src.utils.calibration_methods import (  # noqa: E402
    fit_temperature_multiclass, apply_temperature_multiclass)

CACHE = os.path.join(ROOT, "checkpoints", "e2_probs_cache")
CELL = "chapman_cpsc_inceptiontime_seed42"
TGT_RAW = 0.3474239249443988
TGT_CAL = 0.3335284685932505


def toplabel(p, y):
    return p.max(1).astype(float), (p.argmax(1) == y).astype(float)


def smooth_prob_space(conf, corr, bw=None):
    """概率空间高斯核（非 logit 空间）"""
    conf = np.asarray(conf, float)
    corr = np.asarray(corr, float)
    n = len(conf)
    h = bw if bw is not None else 0.45 * (n / 2000.0) ** (-0.2)
    err = np.empty(n)
    for i in range(n):
        z = (conf[i] - conf) / h
        w = np.exp(-0.5 * z ** 2)
        err[i] = abs((w * corr).sum() / max(w.sum(), 1e-12) - conf[i])
    return float(err.mean())


def binned(conf, corr, n_bins=10, scheme="width"):
    conf = np.asarray(conf, float)
    corr = np.asarray(corr, float)
    if scheme == "width":
        edges = np.linspace(0, 1, n_bins + 1)
    else:
        edges = np.quantile(conf, np.linspace(0, 1, n_bins + 1))
        edges[0], edges[-1] = 0.0, 1.0
    tot = 0.0
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        m = (conf >= lo) & (conf <= hi) if i == n_bins - 1 else (conf >= lo) & (conf < hi)
        if m.sum() == 0:
            continue
        tot += m.sum() / len(conf) * abs(conf[m].mean() - corr[m].mean())
    return float(tot)


def classwise_smooth(p, y, bw=None):
    """逐类 flatten 后做 smooth_ece（多分类 marginal 版）"""
    K = p.shape[1]
    c = p.reshape(-1).astype(float)
    y1 = np.zeros_like(p, dtype=float)
    for k in range(K):
        y1[:, k] = (y == k)
    return smooth_ece(c, y1.reshape(-1), bandwidth=bw)


def macro_classwise_smooth(p, y, bw=None):
    K = p.shape[1]
    vals = []
    for k in range(K):
        vals.append(smooth_ece(p[:, k].astype(float), (y == k).astype(float),
                               bandwidth=bw))
    return float(np.mean(vals))


def main():
    print("=" * 100)
    print("锚点 cell:", CELL)
    print("  JSON raw_ood_orig = %.10f" % TGT_RAW)
    print("  JSON cal_ood_orig = %.10f" % TGT_CAL)
    print("=" * 100)

    d = np.load(os.path.join(CACHE, CELL + ".npz"), allow_pickle=True)
    cal_p, cal_y = d["cal_probs"], d["cal_labels"]
    tgt_p, tgt_y = d["test_probs"], d["test_labels"]
    n = len(tgt_y)
    print("n_cal=%d n_test=%d K=%d" % (len(cal_y), n, tgt_p.shape[1]))

    tp = fit_temperature_multiclass(cal_p, cal_y)
    T = float(tp["T"])
    ts_p = apply_temperature_multiclass(tgt_p, tp)
    print("T = %.10f" % T)

    r_conf, r_corr = toplabel(tgt_p, tgt_y)
    c_conf, c_corr = toplabel(ts_p, tgt_y)

    results = []

    def rec(name, raw_v, cal_v):
        results.append((name, raw_v, cal_v))
        flag = ""
        if abs(raw_v - TGT_RAW) < 1e-6:
            flag += " <<RAW-HIT"
        if abs(cal_v - TGT_CAL) < 1e-6:
            flag += " <<CAL-HIT"
        print("  %-46s raw=%12.8f cal=%12.8f%s" % (name, raw_v, cal_v, flag))

    print("\n--- A. 度量族（数据 = 全 test 集 top-label） ---")
    rec("smooth_ece(logit, default bw)", smooth_ece(r_conf, r_corr),
        smooth_ece(c_conf, c_corr))
    for bw in [0.15, 0.25, 0.35, 0.45, 0.594, 0.9, 1.5, 3.0, 10.0]:
        rec("smooth_ece(logit, bw=%.3f)" % bw,
            smooth_ece(r_conf, r_corr, bandwidth=bw),
            smooth_ece(c_conf, c_corr, bandwidth=bw))
    for bw in [0.05, 0.1, 0.15, 0.2, 0.3, 0.45]:
        rec("smooth_prob_space(bw=%.2f)" % bw,
            smooth_prob_space(r_conf, r_corr, bw),
            smooth_prob_space(c_conf, c_corr, bw))
    for nb in [5, 8, 10, 15, 20, 30]:
        rec("binned(width, %d bins)" % nb, binned(r_conf, r_corr, nb, "width"),
            binned(c_conf, c_corr, nb, "width"))
        rec("binned(quantile, %d bins)" % nb,
            binned(r_conf, r_corr, nb, "quantile"),
            binned(c_conf, c_corr, nb, "quantile"))
    rec("repo ece() 10-bin", ece_repo(r_conf, r_corr), ece_repo(c_conf, c_corr))
    rec("ece_metric_safe", ece_metric_safe(r_conf, r_corr),
        ece_metric_safe(c_conf, c_corr))

    print("\n--- B. 多分类 marginal（逐类 flatten / 宏平均） ---")
    rec("classwise_smooth(flatten)", classwise_smooth(tgt_p, tgt_y),
        classwise_smooth(ts_p, tgt_y))
    rec("macro_classwise_smooth", macro_classwise_smooth(tgt_p, tgt_y),
        macro_classwise_smooth(ts_p, tgt_y))

    print("\n--- C. 子采样（cross-fit 半样本 / 随机子集） ---")
    half = n // 2
    for name, idx in [("first-half", np.arange(0, half)),
                      ("second-half", np.arange(half, n)),
                      ("even", np.arange(0, n, 2)),
                      ("odd", np.arange(1, n, 2))]:
        rec("smooth_ece[%s] n=%d" % (name, len(idx)),
            smooth_ece(r_conf[idx], r_corr[idx]),
            smooth_ece(c_conf[idx], c_corr[idx]))
    for seed in [0, 1, 42, 44]:
        rng = np.random.default_rng(seed)
        for m in [500, 1000, 1500]:
            idx = rng.choice(n, m, replace=False)
            rec("smooth_ece[rand s=%d m=%d]" % (seed, m),
                smooth_ece(r_conf[idx], r_corr[idx]),
                smooth_ece(c_conf[idx], c_corr[idx]))

    print("\n--- D. TS 应用方式变体（cal 侧） ---")
    # D1: T 用别的来源（例如在 test 上 fit —— 不合规，仅诊断）
    tp_t = fit_temperature_multiclass(tgt_p, tgt_y)
    rec("TS fit on TEST (T=%.3f)" % tp_t["T"], smooth_ece(r_conf, r_corr),
        smooth_ece(*toplabel(apply_temperature_multiclass(tgt_p, tp_t), tgt_y)))
    # D2: TS 用 float32 精度
    rec("TS float32", smooth_ece(r_conf, r_corr),
        smooth_ece(*toplabel(apply_temperature_multiclass(
            tgt_p.astype(np.float32), {"T": np.float32(T)}), tgt_y)))

    print("\n--- E. 标签扰动 / 打乱（检验是否为随机化零假设） ---")
    for seed in [0, 1, 42]:
        rng = np.random.default_rng(seed)
        perm = rng.permutation(n)
        rec("smooth_ece[label-shuffle s=%d]" % seed,
            smooth_ece(r_conf, r_corr[perm]), smooth_ece(c_conf, c_corr[perm]))

    print("\n--- F. 其他数据源（e6 id / cal 集） ---")
    try:
        z = np.load(os.path.join(ROOT, "checkpoints", "transfer", "chapman_cpsc",
                                 "inceptiontime", "seed42", "e6_probs.npz"),
                    allow_pickle=True)
        idr, idc, idl = z["id_raw"], z["id_cal"], z["id_labels"]
        rec("smooth_ece[e6 id_raw]", smooth_ece(*toplabel(idr, idl)), float("nan"))
        rec("smooth_ece[e6 id_cal]", smooth_ece(*toplabel(idc, idl)), float("nan"))
        orw, ocl, ol = z["ood_raw"], z["ood_cal"], z["ood_labels"]
        rec("smooth_ece[e6 ood_raw/ood_cal]",
            smooth_ece(*toplabel(orw, ol)), smooth_ece(*toplabel(ocl, ol)))
        print("  [info] e6 ood_raw==cache test_probs:",
              np.allclose(orw, tgt_p, atol=1e-6))
    except Exception as e:
        print("  e6 load failed:", e)
    rec("smooth_ece[cache cal]", smooth_ece(*toplabel(cal_p, cal_y)), float("nan"))
    rec("smooth_ece[cache cal + TS]", smooth_ece(*toplabel(cal_p, cal_y)),
        smooth_ece(*toplabel(apply_temperature_multiclass(cal_p, tp), cal_y)))

    print("\n" + "=" * 100)
    print("最接近 raw 目标的 5 个候选：")
    for name, rv, cv in sorted(results, key=lambda x: abs(x[1] - TGT_RAW))[:5]:
        print("   %-46s raw=%.8f  (Δ=%+.2e)  cal=%.8f" % (name, rv, rv - TGT_RAW, cv))
    print("最接近 cal 目标的 5 个候选：")
    for name, rv, cv in sorted(results, key=lambda x: abs(x[2] - TGT_CAL))[:5]:
        print("   %-46s raw=%.8f  cal=%.8f (Δ=%+.2e)" % (name, rv, cv, cv - TGT_CAL))
    return 0


if __name__ == "__main__":
    sys.exit(main())
