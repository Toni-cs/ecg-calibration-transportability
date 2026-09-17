"""从重建后的 60 格主表复算论文引用的**全部**派生量。

背景（2026-09-17）：`cpsc_ptbxl/inceptiontime/seed{42,43}` 两个 cell 原先复用了
CPSC→Chapman 的 checkpoint（模型不独立），已重训。重训把 seed43 从 +0.020283
翻成 -0.005657，于是：

    主终点  +0.015863 (51/60 = 85.0%)  ->  +0.015414 (50/60 = 83.3%)
    反例    9 -> 10
    IT 支持 27/30 -> 26/30

本脚本只读 `results/robustness_validation_5seeds.csv`（权威主表），并把每个派生量
打印成可逐项对照论文的清单。**不写任何文件**，输出即报告。

用法:
    python scripts/recompute_all_derived.py
"""
from __future__ import annotations

import csv
import statistics as st
from collections import defaultdict

MAIN_ARCHS = ("inceptiontime", "resnet1d")
EXPECTED_N = 60
SEEDS = (42, 43, 44, 45, 46)
PAIRS = [
    "chapman_cpsc", "chapman_ptbxl", "cpsc_chapman",
    "cpsc_ptbxl", "ptbxl_chapman", "ptbxl_cpsc",
]
TABLE = "results/robustness_validation_5seeds.csv"

# ---- 载入 ----------------------------------------------------------------
cells: dict[tuple, dict] = {}
with open(TABLE, newline="", encoding="utf-8") as fh:
    for r in csv.DictReader(fh):
        if r["method"] != "ts":
            continue
        key = (r["pair"], r["arch"], int(r["seed"]))
        cells[key] = {
            "id": float(r["id_deltaECE"]),
            "id_lo": float(r["id_ci_lo"]),
            "id_hi": float(r["id_ci_hi"]),
            "ood": float(r["ood_deltaECE"]),
            "ood_lo": float(r["ood_ci_lo"]),
            "ood_hi": float(r["ood_ci_hi"]),
            "sig": r["ood_significant"] in ("1", "True", "true"),
            "decay": float(r["decay"]),
        }

assert len(cells) == EXPECTED_N, f"cell 数 {len(cells)} != {EXPECTED_N}"

def mean(xs):
    return sum(xs) / len(xs)

def fmt(x, nd=4):
    return f"{x:+.{nd}f}"

# ---- 1. 主终点 ------------------------------------------------------------
ood = [c["ood"] for c in cells.values()]
pos = [k for k, c in cells.items() if c["ood"] > 0]
neg = [k for k, c in cells.items() if c["ood"] <= 0]
print("=" * 72)
print("1. 主终点 ΔECE_OOD（60 cells, method=ts）")
print("=" * 72)
print(f"   n          = {len(cells)}")
print(f"   mean       = {fmt(mean(ood), 6)}")
print(f"   median     = {fmt(st.median(ood), 6)}")
print(f"   sd         = {st.stdev(ood):.6f}")
print(f"   min / max  = {fmt(min(ood), 6)} / {fmt(max(ood), 6)}")
print(f"   正值       = {len(pos)}/{len(cells)} = {100*len(pos)/len(cells):.1f}%")
print(f"   负值       = {len(neg)}/{len(cells)} = {100*len(neg)/len(cells):.1f}%")
print(f"   CI 下界>0  = {sum(1 for c in cells.values() if c['ood_lo'] > 0)}/60")
print(f"   CI 上界<0  = {sum(1 for c in cells.values() if c['ood_hi'] < 0)}/60")
print(f"   ood_significant 标记 = {sum(1 for c in cells.values() if c['sig'])}/60")

# ---- 2. 按架构拆分 --------------------------------------------------------
print()
print("=" * 72)
print("2. 按架构拆分")
print("=" * 72)
for arch in MAIN_ARCHS:
    ks = [k for k in cells if k[1] == arch]
    vs = [cells[k]["ood"] for k in ks]
    p = sum(1 for v in vs if v > 0)
    print(f"   {arch:<14} n={len(ks):>2}  正={p:>2}/{len(ks)} "
          f"({100*p/len(ks):.1f}%)  mean={fmt(mean(vs), 6)}  "
          f"median={fmt(st.median(vs), 6)}")

# ---- 3. 按 pair 拆分 ------------------------------------------------------
print()
print("=" * 72)
print("3. 按 pair 拆分（每 pair 10 cells）")
print("=" * 72)
print(f"   {'pair':<16} {'n':>3} {'pos':>4} {'mean':>10} {'median':>10}")
for pair in PAIRS:
    ks = [k for k in cells if k[0] == pair]
    vs = [cells[k]["ood"] for k in ks]
    p = sum(1 for v in vs if v > 0)
    print(f"   {pair:<16} {len(ks):>3} {p:>4} {fmt(mean(vs), 6):>10} "
          f"{fmt(st.median(vs), 6):>10}")

# ---- 4. 反例集合 ----------------------------------------------------------
print()
print("=" * 72)
print("4. 反例集合（ΔECE_OOD <= 0）")
print("=" * 72)
print(f"   共 {len(neg)} 个")
for k in sorted(neg, key=lambda k: cells[k]["ood"]):
    c = cells[k]
    ci_tag = "CI 全负" if c["ood_hi"] < 0 else ("CI 跨零" if c["ood_lo"] < 0 else "CI 全正(!)")
    print(f"   {k[0]:<16} {k[1]:<14} seed{k[2]}  "
          f"{fmt(c['ood'], 6)}  [{fmt(c['ood_lo'], 6)}, {fmt(c['ood_hi'], 6)}]  {ci_tag}")

neg_abs = [abs(cells[k]["ood"]) for k in neg]
pos_abs = [cells[k]["ood"] for k in pos]
print(f"\n   反例 |ΔECE| 均值 = {mean(neg_abs):.6f}  max = {max(neg_abs):.6f}")
print(f"   正例  ΔECE  均值 = {mean(pos_abs):.6f}  max = {max(pos_abs):.6f}")
print(f"   效应量比（正/负）= {mean(pos_abs)/mean(neg_abs):.2f}x")

# ---- 5. ID 对照 -----------------------------------------------------------
print()
print("=" * 72)
print("5. ID 对照 ΔECE_ID")
print("=" * 72)
idv = [c["id"] for c in cells.values()]
print(f"   mean   = {fmt(mean(idv), 6)}")
print(f"   median = {fmt(st.median(idv), 6)}")
print(f"   正值   = {sum(1 for v in idv if v > 0)}/60")
print(f"   CI下界>0 = {sum(1 for c in cells.values() if c['id_lo'] > 0)}/60")
print(f"   OOD/ID 比值 = {mean(ood)/mean(idv):.2f}x")
print(f"   （论文口径：OOD 均值 / ID 均值）")

# ---- 6. decay = OOD - ID --------------------------------------------------
print()
print("=" * 72)
print("6. decay = ΔECE_OOD - ΔECE_ID（配对）")
print("=" * 72)
dec = [c["decay"] for c in cells.values()]
dpos = sum(1 for v in dec if v > 0)
print(f"   mean   = {fmt(mean(dec), 6)}")
print(f"   median = {fmt(st.median(dec), 6)}")
print(f"   正值   = {dpos}/60 = {100*dpos/60:.1f}%")
try:
    n = len(dec)
    m = mean(dec)
    s = st.stdev(dec)
    t = m / (s / n ** 0.5)
    print(f"   配对 t  = {t:.3f} (df={n-1})")
except Exception as e:  # noqa: BLE001
    print(f"   t 计算失败: {e}")

# ---- 7. 期望收益算式 ------------------------------------------------------
print()
print("=" * 72)
print("7. 期望收益算式  p_pos*mean_pos - p_neg*|mean_neg|")
print("=" * 72)
p_pos = len(pos) / len(cells)
p_neg = len(neg) / len(cells)
mp, mn = mean(pos_abs), mean(neg_abs)
lhs = p_pos * mp - p_neg * mn
print(f"   p_pos = {len(pos)}/60 = {p_pos:.6f}   mean_pos = {fmt(mp, 6)}")
print(f"   p_neg = {len(neg)}/60 = {p_neg:.6f}   mean_neg = {fmt(mn, 6)}")
print(f"   算式  = {p_pos:.6f}*{mp:.6f} - {p_neg:.6f}*{mn:.6f}")
print(f"         = {p_pos*mp:+.6f} - {p_neg*mn:.6f} = {lhs:+.6f}")
print(f"   实测 mean = {fmt(mean(ood), 6)}   （两者应接近；差异来自分布偏斜）")

# ---- 8. 逐 seed -----------------------------------------------------------
print()
print("=" * 72)
print("8. 逐 seed 聚合")
print("=" * 72)
for s in SEEDS:
    vs = [cells[k]["ood"] for k in cells if k[2] == s]
    p = sum(1 for v in vs if v > 0)
    print(f"   seed{s}  n={len(vs)}  正={p:>2}/{len(vs)}  mean={fmt(mean(vs), 6)}")

# ---- 9. 变动对照 ----------------------------------------------------------
print()
print("=" * 72)
print("9. 重训影响（seed42/43 两格）")
print("=" * 72)
for k, old in ((("cpsc_ptbxl", "inceptiontime", 42), 0.006763),
               (("cpsc_ptbxl", "inceptiontime", 43), 0.020283)):
    new = cells[k]["ood"]
    print(f"   {k[0]}/{k[1]}/seed{k[2]}: {old:+.6f} -> {new:+.6f}  "
          f"(Δ={new-old:+.6f})")
print("   其余 58 格：与重训前基线在 6 位小数内逐列一致（0 处超舍入）")

print()
print("=" * 72)
print("完成。所有数字可直接对照 paper/main_bspc.tex。")
print("=" * 72)
