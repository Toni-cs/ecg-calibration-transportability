"""Q1 决定性探针：raw_ood_orig / cal_ood_orig 到底是什么量？

锚点 cell = chapman_cpsc_inceptiontime_seed42
    raw_ood_orig = 0.3474239249443988
    cal_ood_orig = 0.3335284685932505
    nb_raw = 8 个单调下降的数
    nb_ts  = 同长度，仅 2~3 个位置不同

策略：
  (A) 先看 raw_ood_orig 是否是 nb_raw 的某个确定性聚合（跨 60 cells 找 corr≈1）
  (B) 反推 nb_raw 本身是什么 8 元曲线
  (C) 用 B 的结果重建 raw/cal，检验是否命中 JSON

用法: /c/python/python.exe -X faulthandler scripts/probe_q1_nb2.py
"""
import json
import os
import sys

import numpy as np

ROOT = r"D:/A1/ecg-lab-v2"
sys.path.insert(0, ROOT)

from src.utils.calibration import smooth_ece  # noqa: E402
from src.utils.calibration_methods import (  # noqa: E402
    fit_temperature_multiclass, apply_temperature_multiclass)

CACHE = os.path.join(ROOT, "checkpoints", "e2_probs_cache")
JSON = os.path.join(ROOT, "results", "strengthening_battle_corrected.json")


def toplabel(p, y):
    return p.max(1).astype(float), (p.argmax(1) == y).astype(float)


def load_main():
    D = json.load(open(JSON, encoding="utf-8"))
    return [r for r in D if r.get("arch") != "mamba"]


def part_A(recs):
    print("=" * 96)
    print("A. raw_ood_orig 是否 = f(nb_raw) ？（跨 60 cells 相关系数）")
    print("=" * 96)
    nb = np.array([r["nb_raw"] for r in recs])
    nbt = np.array([r["nb_ts"] for r in recs])
    raw = np.array([r["raw_ood_orig"] for r in recs])
    cal = np.array([r["cal_ood_orig"] for r in recs])
    cands = {
        "mean(nb)": nb.mean(1),
        "median(nb)": np.median(nb, 1),
        "nb[:,0]": nb[:, 0],
        "nb[:,1]": nb[:, 1],
        "nb[:,-1]": nb[:, -1],
        "nb[:,-2]": nb[:, -2],
        "max(nb)": nb.max(1),
        "min(nb)": nb.min(1),
        "sum(nb)/n": nb.sum(1) / nb.shape[1],
        "1.5*mean(nb)": 1.5 * nb.mean(1),
        "mean(nb[:,:4])": nb[:, :4].mean(1),
        "mean(nb[:,4:])": nb[:, 4:].mean(1),
    }
    for k, v in cands.items():
        d = np.abs(v - raw)
        c = np.corrcoef(v, raw)[0, 1]
        print("  %-16s corr=%+.6f  maxabsdiff=%.6f  meandiff=%+.6f"
              % (k, c, d.max(), (v - raw).mean()))
    print("  ---- 对 cal 同样 ----")
    for k in ["mean(nb)", "1.5*mean(nb)", "nb[:,1]"]:
        v = cands[k]
        print("  %-16s corr(cal)=%+.4f" % (k, np.corrcoef(v, cal)[0, 1]))

    print("\n  nb_raw 与 nb_ts 的逐列均值：")
    print("    nb_raw mean:", np.round(nb.mean(0), 5))
    print("    nb_ts  mean:", np.round(nbt.mean(0), 5))
    print("    raw mean=%.5f  cal mean=%.5f" % (raw.mean(), cal.mean()))
    print("    sum(nb_raw) mean=%.5f  sum(nb_ts) mean=%.5f"
          % (nb.sum(1).mean(), nbt.sum(1).mean()))
    print("    delta_obs mean=%.5f ; sum(nb_raw)-sum(nb_ts) mean=%.5f"
          % (np.array([r["delta_obs"] for r in recs]).mean(),
             (nb.sum(1) - nbt.sum(1)).mean()))


def part_B(recs, cell="chapman_cpsc_inceptiontime_seed42"):
    print("\n" + "=" * 96)
    print("B. 反推 nb_raw 是什么曲线（锚点 cell = %s）" % cell)
    print("=" * 96)
    r = next(x for x in recs
             if (x["source"], x["target"], x["arch"], x["seed"])
             == ("chapman", "cpsc", "inceptiontime", 42))
    nb = np.array(r["nb_raw"])
    nbt = np.array(r["nb_ts"])
    print("  target nb_raw =", np.round(nb, 6))
    print("  target nb_ts  =", np.round(nbt, 6))

    d = np.load(os.path.join(CACHE, cell + ".npz"), allow_pickle=True)
    cal_p, cal_y = d["cal_probs"], d["cal_labels"]
    tgt_p, tgt_y = d["test_probs"], d["test_labels"]
    K = tgt_p.shape[1]
    print("  n_cal=%d n_test=%d K=%d" % (len(cal_y), len(tgt_y), K))

    tp = fit_temperature_multiclass(cal_p, cal_y)
    print("  T = %.6f (JSON %.6f)" % (tp["T"], r["T"]))
    ts_p = apply_temperature_multiclass(tgt_p, tp)

    conf, corr = toplabel(tgt_p, tgt_y)
    cconf, ccorr = toplabel(ts_p, tgt_y)
    print("  mean conf raw=%.5f acc=%.5f gap=%.5f"
          % (conf.mean(), corr.mean(), abs(conf.mean() - corr.mean())))

    def show(name, v, vc=None):
        v = np.asarray(v, float)
        ok = len(v) == 8
        m = np.abs(v - nb).max() if ok else float("nan")
        print("  %-40s %s  maxdiff=%.3e" % (name, np.round(v, 6), m))
        if vc is not None:
            vc = np.asarray(vc, float)
            if len(vc) == 8:
                print("  %-40s %s  maxdiff=%.3e" % ("  ...cal side",
                      np.round(vc, 6), np.abs(vc - nbt).max()))

    # --- 候选 1: 8 等宽 bin 的 |conf-acc|，按 conf 升序/降序 ---
    edges = np.linspace(0, 1, 9)
    g = []
    for i in range(8):
        m = ((conf >= edges[i]) & (conf < edges[i + 1])) if i < 7 \
            else ((conf >= edges[i]) & (conf <= edges[i + 1]))
        g.append(abs(conf[m].mean() - corr[m].mean()) if m.sum() else 0.0)
    show("8等宽bin |c-a| 升序", g)
    show("8等宽bin |c-a| 降序", g[::-1])

    # --- 候选 2: 8 分位 bin ---
    q = np.quantile(conf, np.linspace(0, 1, 9))
    q[0], q[-1] = 0.0, 1.0
    q = np.unique(q)
    g2 = []
    for i in range(len(q) - 1):
        m = ((conf >= q[i]) & (conf < q[i + 1])) if i < len(q) - 2 \
            else ((conf >= q[i]) & (conf <= q[i + 1]))
        g2.append(abs(conf[m].mean() - corr[m].mean()) if m.sum() else 0.0)
    show("8分位bin |c-a|", g2)

    # --- 候选 3: 累进 top-k/8 子集（按 conf 排序取前 k/8 比例） ---
    order = np.argsort(-conf)
    cum = []
    cumc = []
    order_c = np.argsort(-cconf)
    for k in range(1, 9):
        m = order[:int(round(len(conf) * k / 8))]
        mc = order_c[:int(round(len(cconf) * k / 8))]
        cum.append(abs(conf[m].mean() - corr[m].mean()))
        cumc.append(abs(cconf[mc].mean() - ccorr[mc].mean()))
    show("累进 top-(k/8) |c-a|", cum, cumc)

    # --- 候选 4: 逐类 gap（K 类） ---
    gk, gkc = [], []
    for k in range(K):
        m = (tgt_p.argmax(1) == k)
        mc = (ts_p.argmax(1) == k)
        gk.append(abs(conf[m].mean() - corr[m].mean()) if m.sum() else 0.0)
        gkc.append(abs(cconf[mc].mean() - ccorr[mc].mean()) if mc.sum() else 0.0)
    if K == 8:
        show("逐类 gap (K=8)", gk, gkc)
    else:
        print("  (K=%d != 8, 跳过逐类)" % K)

    # --- 候选 5: smooth_ece 在累进子集上 ---
    sm, smc = [], []
    for k in range(1, 9):
        m = order[:int(round(len(conf) * k / 8))]
        mc = order_c[:int(round(len(cconf) * k / 8))]
        sm.append(smooth_ece(conf[m], corr[m]))
        smc.append(smooth_ece(cconf[mc], ccorr[mc]))
    show("smooth_ece 累进 top-(k/8)", sm, smc)

    # --- 候选 6: 用 (1+eps) 之类 ---
    print("\n  参考：smooth_ece(raw)=%.6f  smooth_ece(ts)=%.6f  JSON raw=%.6f"
          % (smooth_ece(conf, corr), smooth_ece(cconf, ccorr),
             r["raw_ood_orig"]))
    print("  参考：nb_raw[-1]=%.6f  nb_ts[-1]=%.6f" % (nb[-1], nbt[-1]))
    print("  参考：nb 逐元素 / 8 =", np.round(nb / 8, 6))
    print("  参考：cumsum(nb)/8 =", np.round(np.cumsum(nb) / 8, 6))
    print("  参考：nb 的一阶差分 =", np.round(np.diff(nb), 6))


def main():
    recs = load_main()
    part_A(recs)
    part_B(recs)
    return 0


if __name__ == "__main__":
    sys.exit(main())
