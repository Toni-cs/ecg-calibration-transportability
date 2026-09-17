"""Q1 溯源：strengthening JSON 的 raw_ood_orig 是否 = transfer_result.json 的 ts/ood/raw？

同时检验：
  - transfer_result.json 的 ood_acc 是否等于 npz cache 复算的 ood_acc
  - e6_probs.npz（同 run 的中间产物）复算的 smooth_ece 是否等于 transfer_result 的 raw

用法: /c/python/python.exe -X faulthandler scripts/probe_q1_provenance.py
"""
import glob
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
TRANS = os.path.join(ROOT, "checkpoints", "transfer")
JSON = os.path.join(ROOT, "results", "strengthening_battle_corrected.json")


def main():
    recs = [r for r in json.load(open(JSON, encoding="utf-8"))
            if r.get("arch") != "mamba"]

    n_have = 0
    match_raw = match_cal = 0
    acc_mismatch = 0
    e6_ok = 0
    e6_n = 0
    rows = []
    for r in recs:
        src, tgt, arch, seed = r["source"], r["target"], r["arch"], r["seed"]
        p = os.path.join(TRANS, "%s_%s" % (src, tgt), arch, "seed%d" % seed,
                         "transfer_result.json")
        if not os.path.exists(p):
            rows.append((src, tgt, arch, seed, None, None, None, None))
            continue
        n_have += 1
        d = json.load(open(p, encoding="utf-8"))
        ts = d.get("methods", {}).get("ts", {})
        ood = ts.get("ood", {}) or {}
        raw_t, cal_t = ood.get("raw"), ood.get("cal")
        acc_t = d.get("ood_acc")
        mraw = (raw_t is not None and abs(raw_t - r["raw_ood_orig"]) < 1e-12)
        mcal = (cal_t is not None and abs(cal_t - r["cal_ood_orig"]) < 1e-12)
        match_raw += bool(mraw)
        match_cal += bool(mcal)
        am = (acc_t is not None and abs(acc_t - r["ood_acc"]) > 1e-9)
        acc_mismatch += bool(am)

        # e6 复算
        e6p = os.path.join(TRANS, "%s_%s" % (src, tgt), arch,
                           "seed%d" % seed, "e6_probs.npz")
        e6s = float("nan")
        if os.path.exists(e6p):
            e6_n += 1
            z = np.load(e6p, allow_pickle=True)
            orw = z["ood_raw"]
            conf = orw.max(1)
            corr = (orw.argmax(1) == z["ood_labels"]).astype(float)
            e6s = smooth_ece(conf, corr)
            if abs(e6s - raw_t) < 1e-9:
                e6_ok += 1
        rows.append((src, tgt, arch, seed, raw_t, r["raw_ood_orig"], acc_t,
                     r["ood_acc"], e6s))

    print("=" * 110)
    print("transfer_result.json 存在: %d / %d" % (n_have, len(recs)))
    print("  methods.ts.ood.raw == JSON.raw_ood_orig : %d / %d" % (match_raw, n_have))
    print("  methods.ts.ood.cal == JSON.cal_ood_orig : %d / %d" % (match_cal, n_have))
    print("  transfer.ood_acc  != JSON.ood_acc       : %d / %d" % (acc_mismatch, n_have))
    print("  e6_probs.npz 复算 smooth_ece == transfer raw : %d / %d" % (e6_ok, e6_n))
    print()
    print("%-9s %-9s %-13s %4s | %10s %10s | %8s %8s | %10s"
          % ("src", "tgt", "arch", "seed", "trans.raw", "JSON.raw",
             "trans.acc", "JSON.acc", "e6 smooth"))
    for t in rows[:12]:
        if t[4] is None:
            print("%-9s %-9s %-13s %4s |  (no transfer_result.json)" % t[:4])
            continue
        print("%-9s %-9s %-13s %4d | %10.6f %10.6f | %8.4f %8.4f | %10.6f"
              % t)

    # 全局对比
    print("\n--- 全局（全部有 transfer_result 的 cell）---")
    a = np.array([t[4] for t in rows if t[4] is not None])
    b = np.array([t[5] for t in rows if t[4] is not None])
    print("  transfer raw  mean=%.6f ; JSON raw_ood_orig mean=%.6f"
          % (a.mean(), b.mean()))
    print("  max|diff| = %.3e ; corr = %.6f" % (np.abs(a - b).max(),
                                               np.corrcoef(a, b)[0, 1]))
    ea = np.array([t[6] for t in rows if t[6] is not None])
    eb = np.array([t[7] for t in rows if t[6] is not None])
    print("  transfer ood_acc mean=%.4f ; JSON ood_acc mean=%.4f ; "
          "corr=%.4f" % (ea.mean(), eb.mean(), np.corrcoef(ea, eb)[0, 1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
