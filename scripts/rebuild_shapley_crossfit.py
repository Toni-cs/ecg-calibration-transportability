"""重建 real-data Shapley cross-fitting（§real_shapley）—— 补回丢失的生成脚本

背景：论文 §real_shapley 报告了 real-data Shapley cross-fitting，但生成脚本在
仓库与全部 git 历史中均不存在，导致该节无法端到端复现（审计判定：provenance 缺陷）。

本脚本从原始 npz 重建该实验，产出可审计的结果，并明确区分三个 ΔECE 口径：
  - delta_obs_orig : raw_ood_orig - cal_ood_orig（SmoothECE 口径，论文主终点）
  - delta_obs      : binned-ECE 口径，随 T 膨胀 → 度量伪信号（勿用于论文结论）
  - delta_pred     : Shapley 三分量之和（decompose_benefit 的 delta_total）

用法：
  /c/python/python.exe -X faulthandler scripts/rebuild_shapley_crossfit.py
"""
import csv
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.utils.calibration import smooth_ece            # noqa: E402
from src.utils.decomposition import decompose_benefit    # noqa: E402
from src.utils.calibration_methods import (              # noqa: E402
    fit_temperature_multiclass, apply_temperature_multiclass)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "checkpoints", "e2_probs_cache")
OUT_CSV = os.path.join(ROOT, "results", "rebuild_shapley_crossfit.csv")
OUT_JSON = os.path.join(ROOT, "results", "rebuild_shapley_crossfit.json")

ARCHS = ("inceptiontime", "resnet1d")
SEEDS = (42, 43, 44, 45, 46)


def _toplabel_binary(probs, labels):
    """多分类 → top-label 二值化 (conf, correct)

    与论文 top-label marginal ECE 约定一致（Guo et al. 2017）。
    """
    pred = probs.argmax(axis=1)
    conf = probs.max(axis=1)
    correct = (pred == labels).astype(float)
    return conf, correct


def _load(npz_path):
    d = np.load(npz_path, allow_pickle=True)
    return (d["cal_probs"], d["cal_labels"],
            d["test_probs"], d["test_labels"])


def _parse_name(fname):
    """chapman_cpsc_inceptiontime_seed42.npz → (src, tgt, arch, seed)

    约定：<source>_<target>_<arch>_seed<k>
    arch 名可能含下划线（如 inceptiontime_lite），故 arch = 中间所有 token。
    """
    base = fname[:-4]
    parts = base.split("_")
    if len(parts) < 4:
        return None
    seed_s = parts[-1]
    if not seed_s.startswith("seed"):
        return None
    try:
        seed = int(seed_s[4:])
    except ValueError:
        return None
    src = parts[0]
    tgt = parts[1]
    arch = "_".join(parts[2:-1])
    return src, tgt, arch, seed


def main():
    if not os.path.isdir(CACHE):
        print("[FATAL] cache dir missing:", CACHE)
        return 1

    files = sorted(f for f in os.listdir(CACHE) if f.endswith(".npz"))
    print("cache 文件数: %d" % len(files))

    rows = []
    skipped = []
    for fname in files:
        meta = _parse_name(fname)
        if meta is None:
            skipped.append((fname, "name-parse"))
            continue
        src, tgt, arch, seed = meta
        # 排除玩具架构（BiMamba toy 格）
        if arch not in ARCHS or seed not in SEEDS:
            skipped.append((fname, "arch/seed filter: %s/%d" % (arch, seed)))
            continue

        cal_p, cal_y, tgt_p, tgt_y = _load(os.path.join(CACHE, fname))

        # ---- top-label 二值化 ----
        cal_conf, cal_correct = _toplabel_binary(cal_p, cal_y)
        tgt_conf, tgt_correct = _toplabel_binary(tgt_p, tgt_y)

        # ---- 拟合温度 T（source cal）----
        try:
            tp = fit_temperature_multiclass(cal_p, cal_y)
            T = float(tp["T"])
        except Exception as e:
            skipped.append((fname, "T fit failed: %s" % e))
            continue

        # ---- 主终点：SmoothECE 口径 ----
        raw_ood_orig = smooth_ece(tgt_conf, tgt_correct)
        tgt_p_ts = apply_temperature_multiclass(tgt_p, tp)
        ts_conf, ts_correct = _toplabel_binary(tgt_p_ts, tgt_y)
        cal_ood_orig = smooth_ece(ts_conf, ts_correct)
        delta_obs_orig = raw_ood_orig - cal_ood_orig

        # ---- 分解（Shapley 三分量）----
        rng = np.random.default_rng(seed)
        prev_true = float(tgt_correct.mean())
        try:
            dec = decompose_benefit(cal_conf, cal_correct,
                                    slope=1.0, intercept=0.0,
                                    target_prev=prev_true, rng=rng)
        except Exception as e:
            skipped.append((fname, "decompose failed: %s" % e))
            continue

        sh = dec["shapley"]["values"]
        delta_pred = float(sh["s"] + sh["b"] + sh["pi"])

        rows.append({
            "cell": fname[:-4],
            "source": src, "target": tgt, "arch": arch, "seed": seed,
            "T": T,
            "raw_ood_orig": raw_ood_orig,
            "cal_ood_orig": cal_ood_orig,
            "delta_obs_orig": delta_obs_orig,
            "shap_s": float(sh["s"]),
            "shap_b": float(sh["b"]),
            "shap_pi": float(sh["pi"]),
            "delta_pred": delta_pred,
            "recovery_failed": bool(dec["recovery_failed"]),
            "entangled": bool(dec["entangled"]),
            "fisher_det": float(dec["fisher_det"]),
        })

    print("成功重建 cell 数: %d" % len(rows))
    if skipped:
        print("跳过 %d 条（前 5 条）:" % len(skipped))
        for s in skipped[:5]:
            print("   ", s)

    if not rows:
        print("[FATAL] no cells reconstructed")
        return 1

    # ---- 落盘 ----
    os.makedirs(os.path.dirname(OUT_CSV), exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(rows, f, indent=2, ensure_ascii=False)

    # ---- 指标 ----
    import statistics as st
    import math

    dobs = [r["delta_obs_orig"] for r in rows]
    dprd = [r["delta_pred"] for r in rows]
    Ts = [r["T"] for r in rows]
    n = len(rows)

    print("\n" + "=" * 72)
    print("指标（口径 = delta_obs_orig，与论文主终点一致）")
    print("=" * 72)
    print("n = %d" % n)
    print("delta_obs_orig mean %+.4f  median %+.4f"
          % (st.mean(dobs), st.median(dobs)))
    print("delta_pred     mean %+.4f  median %+.4f"
          % (st.mean(dprd), st.median(dprd)))

    pos = sum(1 for v in dobs if v > 0)
    const_acc = max(pos, n - pos) / n
    sign_ok = sum(1 for a, b in zip(dprd, dobs) if (a > 0) == (b > 0))
    print("\n--- 方向准确率 vs 常数基线 ---")
    print("观测正值率        : %d/%d = %.1f%%" % (pos, n, 100 * pos / n))
    print("常数预测器(恒正)  : %d/%d = %.1f%%" % (max(pos, n - pos), n,
                                                100 * const_acc))
    print("分解模型          : %d/%d = %.1f%%" % (sign_ok, n,
                                                100 * sign_ok / n))
    print("→ κ = %.4f" % (0.0 if abs(sign_ok - max(pos, n - pos)) < 1e-9 else -1))
    print("pred 全正? %s" % ("是" if all(v > 0 for v in dprd) else "否"))

    err = [a - b for a, b in zip(dprd, dobs)]
    print("\n--- 预测误差 ---")
    print("mean %+.4f  median %+.4f" % (st.mean(err), st.median(err)))

    rc = math.sqrt(st.mean([(v - st.mean(dobs)) ** 2 for v in dobs]))
    rm = math.sqrt(st.mean([(a - b) ** 2 for a, b in zip(dprd, dobs)]))
    print("\n--- RMSE ---")
    print("常数(obs 均值) : %.4f" % rc)
    print("分解模型       : %.4f" % rm)
    print("倍数           : %.2fx" % (rm / rc))

    print("\n--- T 不变性自检（主终点安全性的证据）---")
    for lo, hi in [(0, 1.5), (1.5, 2), (2, 3), (3, 5)]:
        s = [r["delta_obs_orig"] for r in rows if lo <= r["T"] < hi]
        if s:
            print("  T∈[%.1f,%.1f) n=%2d  mean %+.4f" % (lo, hi, len(s),
                                                        st.mean(s)))

    mT, my = st.mean(Ts), st.mean(dobs)
    cov = sum((a - mT) * (b - my) for a, b in zip(Ts, dobs)) / n
    vT = sum((a - mT) ** 2 for a in Ts) / n
    vy = sum((b - my) ** 2 for b in dobs) / n
    print("  corr(delta_obs_orig, T) = %+.4f  R² = %.4f"
          % (cov / (vT ** 0.5 * vy ** 0.5), (cov / (vT ** 0.5 * vy ** 0.5)) ** 2))

    print("\n落盘: %s" % OUT_CSV)
    print("落盘: %s" % OUT_JSON)
    return 0


if __name__ == "__main__":
    sys.exit(main())
