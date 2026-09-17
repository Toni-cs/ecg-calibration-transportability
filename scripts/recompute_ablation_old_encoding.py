#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""在 OLD 编码下重算 results/ablation_ts_components.csv（P0-F 修复）。

=====================================================================
背景（为什么需要这个脚本）
=====================================================================
``checkpoints/e2_probs_cache/*.npz`` 同时存放 probs 与 labels，但二者来自**不同编码**：

* **probs** 来自 2026-09-08 训练、当时 ``SUBSPACE_CPSC = ("NORM","CD","STTC","MI")``
  （OLD）的 checkpoint。故 probs 的第 1 列 = CD、第 3 列 = MI。
  第一方证据：``checkpoints/transfer/**/transfer_result.json`` 自存
  ``label_map = {"CD":1,"MI":3,"NORM":0,"STTC":2}``（40/40 个含 CPSC 的 cell）。

* **labels** 是 2026-09-09 编码变更之后写入的，为 ``("NORM","MI","STTC","CD")``
  （NEW）。故 labels 的 1 = MI、3 = CD。
  证据：CPSC 测试集标签频次 ``[NORM=183, ?1=303, STTC=1086, ?3=485]``，
  除以 2057 得 8.90% / 14.73% / 52.80% / 23.58%；
  而 ``data/cpsc_processed/preprocess_summary.json`` 全库分布为
  NORM 8.88% / MI 14.71% / STTC 52.75% / CD 23.55% / HYP 0.11%。
  ⇒ 索引 1 = MI、索引 3 = CD，即 NEW。逐位吻合。

于是 ``run_e2_ablation_discrimination.py::load_probs_for_checkpoint`` 在
09-10 生成 ``ablation_ts_components.csv`` 时，命中了缓存（probs=OLD、labels=NEW），
产生 **probs/labels 错配**：模型把 CD 质量放在第 1 列，而真值第 1 列是 MI，
CD 与 MI（合计 38.3% 的样本）被系统性判错，raw ECE 因此虚高。

错配的指纹（ptbxl→cpsc/resnet1d/seed42 混淆矩阵）：
NEW-标签 1（=MI）的患者有 250/303 = 82.5% 被判为 argmax **3**；
NEW-标签 3（=CD）的患者有 42.5% 被判为 argmax **1**。
若 probs 与 labels 同为 NEW，则对角线应占优——故 probs 必为 OLD。

=====================================================================
本脚本做什么
=====================================================================
对每个 cell：若 ``"cpsc" in (source, target)``（即 num_classes==4，标签落在
CPSC 4 类子空间内），把 ``cal_labels``/``test_labels`` 施加 ``swap13``（1↔3）
还原为 OLD，然后**用与原脚本完全相同的函数**重算四个 stage 的全部指标。

只改标签、不动 probs——这正是「还原归档事实」而非「重新解释」。

用法::

    /c/python/python.exe scripts/recompute_ablation_old_encoding.py
    /c/python/python.exe scripts/recompute_ablation_old_encoding.py --write
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.utils.calibration_methods import (  # noqa: E402
    apply_temperature_multiclass,
    fit_temperature_multiclass,
)
from run_e2_ablation_discrimination import (  # noqa: E402
    apply_binned_temperature,
    calibration_reliability,
    fit_binned_temperature,
    optimize_thresholds,
)

CSV_IN = _PROJECT_ROOT / "results" / "ablation_ts_components.csv"
CSV_OUT = _PROJECT_ROOT / "results" / "ablation_ts_components.OLD_ENCODING.csv"
CACHE_DIR = _PROJECT_ROOT / "checkpoints" / "e2_probs_cache"

# OLD 整数 -> NEW 整数：OLD 1=CD -> NEW 3；OLD 3=MI -> NEW 1
PERM = np.array([0, 3, 2, 1], dtype=np.int64)


def npz_old_labels(source: str, target: str, arch: str, seed: int):
    """读 npz，返回 (cal_probs, cal_labels_OLD, test_probs, test_labels_OLD, K)。

    含 CPSC 的 cell（num_classes==4）需要 swap13 还原；chapman↔ptbxl（5 类）不动。
    """
    p = CACHE_DIR / f"{source}_{target}_{arch}_seed{seed}.npz"
    if not p.exists():
        return None
    d = np.load(p, allow_pickle=True)
    is_cpsc = ("cpsc" in source) or ("cpsc" in target)
    cal_y = d["cal_labels"].astype(np.int64)
    tst_y = d["test_labels"].astype(np.int64)
    if is_cpsc:
        cal_y = PERM[cal_y]
        tst_y = PERM[tst_y]
    return d["cal_probs"], cal_y, d["test_probs"], tst_y, int(d["num_classes"])


def recompute_cell(source, target, arch, seed):
    """重算一个 cell 的 4 个 stage 行；返回 list[dict] 或 None。"""
    got = npz_old_labels(source, target, arch, seed)
    if got is None:
        return None
    cal_p, cal_y, test_p, test_y, K = got

    ts_params = fit_temperature_multiclass(cal_p, cal_y)
    T_global = float(ts_params["T"])
    cal_s1 = apply_temperature_multiclass(cal_p, ts_params)
    test_s1 = apply_temperature_multiclass(test_p, ts_params)

    binned_params = fit_binned_temperature(cal_s1, cal_y)
    cal_s2 = apply_binned_temperature(cal_s1, binned_params)
    test_s2 = apply_binned_temperature(test_s1, binned_params)
    T_binned = binned_params["temperatures"]

    tau = optimize_thresholds(cal_s2, cal_y, K)
    cal_s3, test_s3 = cal_s2, test_s2

    rows = []
    for stage_name, probs in [
        ("raw", test_p),
        ("stage1_ts", test_s1),
        ("stage2_ts_binned", test_s2),
        ("stage3_ts_binned_threshold", test_s3),
    ]:
        rel = calibration_reliability(probs, test_y)
        row = {
            "source": source, "target": target, "arch": arch, "seed": seed,
            "stage": stage_name, "n_samples": len(test_y),
            "T_global": T_global if stage_name != "raw" else np.nan,
            "T_binned_mean": float(np.mean(T_binned)) if "binned" in stage_name else np.nan,
            "T_binned_min": float(np.min(T_binned)) if "binned" in stage_name else np.nan,
            "T_binned_max": float(np.max(T_binned)) if "binned" in stage_name else np.nan,
            "threshold_norm": float(np.linalg.norm(tau)) if "threshold" in stage_name else 0.0,
        }
        row.update(rel)
        rows.append(row)
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true", help="写出修正后的 CSV")
    args = ap.parse_args()

    df = pd.read_csv(CSV_IN)
    cols = list(df.columns)
    print(f"读入 {CSV_IN.name}: {len(df)} 行, {df.groupby(['source','target','arch','seed']).ngroups} 个 cell")

    out_rows = []
    failed = []
    for (s, t, a, sd), _g in df.groupby(["source", "target", "arch", "seed"], sort=False):
        r = recompute_cell(s, t, a, int(sd))
        if r is None:
            failed.append((s, t, a, sd))
        else:
            out_rows.extend(r)

    if failed:
        print(f"[WARN] {len(failed)} 个 cell 无 npz 缓存: {failed[:5]}")

    new = pd.DataFrame(out_rows)
    # delta_rel_vs_raw：与 run_e2_ablation_discrimination.py:657 同口径
    _pv = new.pivot_table(index=["source", "target", "arch", "seed"],
                          columns="stage", values="brier_reliability")
    if "stage1_ts" in _pv.columns and "raw" in _pv.columns:
        new = new.merge(_pv["raw"].rename("raw_base").reset_index(),
                        on=["source", "target", "arch", "seed"], how="left")
        new["delta_rel_vs_raw"] = new["brier_reliability"] - new["raw_base"]
        new = new.drop(columns=["raw_base"])
    else:
        new["delta_rel_vs_raw"] = np.nan
    new = new[cols]
    old = df.copy()

    key = ["source", "target", "arch", "seed", "stage"]
    m = old.merge(new, on=key, suffixes=("_old_csv", "_old_enc"), how="inner")
    print(f"逐位配对成功: {len(m)}/{len(df)}")

    print("\n=== stage=raw：smooth_ece ===")
    for tag, col in [("CSV as shipped (错配/NEW)", "smooth_ece_old_csv"),
                     ("recomputed OLD (正确)", "smooth_ece_old_enc")]:
        v = m.loc[m.stage == "raw", col].astype(float)
        print(f"  {tag:26s} n={len(v)} mean={v.mean():.4f} min={v.min():.4f} max={v.max():.4f}")
    d = (m.loc[m.stage == "raw", "smooth_ece_old_csv"].astype(float)
         - m.loc[m.stage == "raw", "smooth_ece_old_enc"].astype(float))
    print(f"  max|CSV-OLD| = {d.abs().max():.6f}   逐位相同 {int((d.abs()<1e-12).sum())}/{len(d)}")

    print("\n=== stage=raw：含 CPSC vs 非 CPSC ===")
    mr = m[m.stage == "raw"].copy()
    mr["is_cpsc"] = mr.apply(lambda r: ("cpsc" in r["source"]) or ("cpsc" in r["target"]), axis=1)
    for tag, sub in [("含 CPSC", mr[mr.is_cpsc]), ("非 CPSC", mr[~mr.is_cpsc])]:
        a1 = sub["smooth_ece_old_csv"].astype(float)
        a2 = sub["smooth_ece_old_enc"].astype(float)
        print(f"  {tag:8s} n={len(sub):3d}  CSV mean={a1.mean():.4f} [{a1.min():.4f},{a1.max():.4f}]"
              f"  OLD mean={a2.mean():.4f} [{a2.min():.4f},{a2.max():.4f}]")

    print("\n=== T_global（60 main cells，排除 mamba）===")
    tm = new[(new.stage == "stage1_ts") & (~new.arch.str.contains("mamba"))]
    T = tm["T_global"].astype(float)
    print(f"  n={len(T)}  median={T.median():.4f}  min={T.min():.4f}  max={T.max():.4f}"
          f"  T>=2: {int((T>=2).sum())}/{len(T)} = {(T>=2).mean()*100:.1f}%")

    print("\n=== 反例（ΔECE_OOD = raw − TS < 0，即 TS 有益）的 raw smooth_ece ===")
    piv = new.pivot_table(index=["source", "target", "arch", "seed"], columns="stage",
                          values="smooth_ece", aggfunc="first")
    piv["dECE"] = piv["raw"] - piv["stage1_ts"]          # 与论文主终点同向
    piv60 = piv[~piv.index.get_level_values("arch").str.contains("mamba")]
    neg = piv60[piv60.dECE < 0]
    pos = piv60[piv60.dECE >= 0]
    print(f"  60 main cells: ΔECE>0 {len(pos)}/{len(piv60)},  ΔECE<0（反例）{len(neg)}/{len(piv60)}")
    if len(neg):
        print(f"  反例 raw smooth_ece: min={neg['raw'].min():.4f} max={neg['raw'].max():.4f}"
              f" mean={neg['raw'].mean():.4f}")
        print(f"  反例 ΔECE 范围: [{neg.dECE.min():.4f}, {neg.dECE.max():.4f}]")
    print(f"  全 60 cell raw smooth_ece: min={piv60['raw'].min():.4f} "
          f"max={piv60['raw'].max():.4f} mean={piv60['raw'].mean():.4f}")

    if args.write:
        new.to_csv(CSV_OUT, index=False)
        print(f"\n[OK] 写出 {CSV_OUT}")
    else:
        print("\n（未写盘；加 --write 生成修正 CSV）")


if __name__ == "__main__":
    main()
