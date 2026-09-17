"""Q1 终极验证：raw_ood_orig / cal_ood_orig 是否 = 在「CD<->MI 交换的标签映射」下
的 smooth_ece？

线索：transfer_result.json 的 ood_acc=0.48614487117160915 恰等于
      perm=(0,3,2,1) 下的 argmax 准确率（npz/e6 数据），
      而 npz 默认映射(0,1,2,3) 给出 0.41711229946524064。
      → 两次 run 的差异是「类别索引置换」，模型(best_model.pt, Sep4)未变。
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
TRANS = os.path.join(ROOT, "checkpoints", "transfer")
JSON = os.path.join(ROOT, "results", "strengthening_battle_corrected.json")

def make_perm(K):
    """CD<->MI 交换：索引 1 与 3 互换，其余不变（K<4 时退化为恒等）"""
    p = np.arange(K)
    if K >= 4:
        p[1], p[3] = 3, 1
    return p


def corr_of(p, y, perm=None):
    pred = p.argmax(1)
    if perm is not None:
        pred = perm[pred]
    return p.max(1).astype(float), (pred == y).astype(float)


def main():
    recs = [r for r in json.load(open(JSON, encoding="utf-8"))
            if r.get("arch") != "mamba"]
    key = {(r["source"], r["target"], r["arch"], r["seed"]): r for r in recs}

    print("=" * 104)
    print("单 cell 明细（锚点 = chapman_cpsc_inceptiontime_seed42）")
    print("=" * 104)
    rows = []
    for k, r in key.items():
        src, tgt, arch, seed = k
        z = np.load(os.path.join(CACHE, "%s_%s_%s_seed%d.npz"
                                 % (src, tgt, arch, seed)), allow_pickle=True)
        cal_p, cal_y = z["cal_probs"], z["cal_labels"]
        tp, ty = z["test_probs"], z["test_labels"]
        tpar = fit_temperature_multiclass(cal_p, cal_y)
        ts = apply_temperature_multiclass(tp, tpar)
        # 默认映射
        c0, y0 = corr_of(tp, ty)
        c0c, y0c = corr_of(ts, ty)
        # 置换映射
        c1, y1 = corr_of(tp, ty, make_perm(tp.shape[1]))
        c1c, y1c = corr_of(ts, ty, make_perm(tp.shape[1]))
        rows.append(dict(
            src=src, tgt=tgt, arch=arch, seed=seed, T=float(tpar["T"]),
            raw_def=smooth_ece(c0, y0), cal_def=smooth_ece(c0c, y0c),
            raw_perm=smooth_ece(c1, y1), cal_perm=smooth_ece(c1c, y1c),
            raw_o=r["raw_ood_orig"], cal_o=r["cal_ood_orig"],
            acc_def=float((tp.argmax(1) == ty).mean()),
            acc_perm=float((make_perm(tp.shape[1])[tp.argmax(1)] == ty).mean()),
        ))

    for x in rows[:4]:
        print("  %s %s %s %d  T=%.4f" % (x["src"], x["tgt"], x["arch"], x["seed"], x["T"]))
        print("     默认映射 acc=%.6f  smooth(raw)=%.6f smooth(ts)=%.6f"
              % (x["acc_def"], x["raw_def"], x["cal_def"]))
        print("     置换映射 acc=%.6f  smooth(raw)=%.6f smooth(ts)=%.6f"
              % (x["acc_perm"], x["raw_perm"], x["cal_perm"]))
        print("     JSON       acc=%.6f  raw_ood_orig=%.6f cal_ood_orig=%.6f"
              % (x["acc_def"], x["raw_o"], x["cal_o"]))

    print("\n" + "=" * 104)
    print("全 60 cells：置换映射下的 smooth_ece 是否 == JSON 的 raw_ood_orig / cal_ood_orig？")
    print("=" * 104)
    rp = np.array([x["raw_perm"] for x in rows])
    cp = np.array([x["cal_perm"] for x in rows])
    ro = np.array([x["raw_o"] for x in rows])
    co = np.array([x["cal_o"] for x in rows])
    rd = np.array([x["raw_def"] for x in rows])
    cd = np.array([x["cal_def"] for x in rows])
    print("  置换映射 raw : max|diff| vs JSON = %.3e   corr=%.6f"
          % (np.abs(rp - ro).max(), np.corrcoef(rp, ro)[0, 1]))
    print("  置换映射 cal : max|diff| vs JSON = %.3e   corr=%.6f"
          % (np.abs(cp - co).max(), np.corrcoef(cp, co)[0, 1]))
    print("  默认映射 raw : max|diff| vs JSON = %.3e" % np.abs(rd - ro).max())
    print("  完全命中(1e-9) raw: %d/60 ; cal: %d/60"
          % (int((np.abs(rp - ro) < 1e-9).sum()),
             int((np.abs(cp - co) < 1e-9).sum())))
    print("  acc: 置换 mean=%.4f  vs transfer ood_acc mean=0.5402 ; 默认 mean=%.4f"
          % (np.mean([x["acc_perm"] for x in rows]),
             np.mean([x["acc_def"] for x in rows])))

    # 用置换映射重算 ΔECE
    dperm = rp - cp
    ddef = rd - cd
    doo = np.array([key[(x["src"], x["tgt"], x["arch"], x["seed"])]["delta_obs_orig"]
                    for x in rows])
    T = np.array([x["T"] for x in rows])
    print("\n" + "=" * 104)
    print("★ 用置换映射重算 ΔECE（= 论文主终点口径）")
    print("=" * 104)
    print("  置换映射 ΔECE mean=%+.6f  pos %d/60  corr(T)=%+.4f  R2=%.4f"
          % (dperm.mean(), (dperm > 0).sum(), np.corrcoef(dperm, T)[0, 1],
             np.corrcoef(dperm, T)[0, 1] ** 2))
    print("  JSON delta_obs_orig mean=%+.6f  pos %d/60  corr(T)=%+.4f  R2=%.4f"
          % (doo.mean(), (doo > 0).sum(), np.corrcoef(doo, T)[0, 1],
             np.corrcoef(doo, T)[0, 1] ** 2))
    print("  corr(置换复算, JSON.delta_obs_orig) = %.6f"
          % np.corrcoef(dperm, doo)[0, 1])
    print("  默认映射 ΔECE mean=%+.6f" % ddef.mean())
    print("\n  T 分层（置换映射复算）:")
    for lo, hi in [(0, 1.5), (1.5, 2), (2, 3), (3, 5)]:
        m = (T >= lo) & (T < hi)
        if m.sum():
            print("    T∈[%.1f,%.1f) n=%2d  置换=%+.4f  JSON.orig=%+.4f"
                  % (lo, hi, m.sum(), dperm[m].mean(), doo[m].mean()))
    json.dump(rows, open(os.path.join(ROOT, "results",
                                      "q1_perm_recompute.json"), "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
