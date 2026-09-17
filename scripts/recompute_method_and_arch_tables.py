"""复算论文的两张主表（方法对比表 + 架构稳健性表），供逐格对照粘贴。

表 1 `tab:methods`      : 8 方法 x InceptionTime 30 格 —— 支持数、5/5 方向数、
                          ΔECE_OOD 均值、负方向数
表 2 `tab:arch_robust`  : 6 pair x {InceptionTime, ResNet1D} 的支持数、
                          反例数、均值/标准差

背景：`cpsc_ptbxl/inceptiontime/seed{42,43}` 重训后 seed43 由 +0.020283 翻为
-0.005657。**该两格对全部 8 个方法都变了**，所以方法表的每一行都要重算，不只是 TS。

用法:
    python scripts/recompute_method_and_arch_tables.py
"""
from __future__ import annotations

import csv
import statistics as st

TABLE = "results/robustness_validation_5seeds.csv"
ARCHS = ("inceptiontime", "resnet1d")
SEEDS = (42, 43, 44, 45, 46)
PAIR_ORDER = [
    ("chapman", "cpsc"), ("chapman", "ptbxl"),
    ("cpsc", "chapman"), ("cpsc", "ptbxl"),
    ("ptbxl", "chapman"), ("ptbxl", "cpsc"),
]
PAIR_LABEL = {
    ("chapman", "cpsc"): "Chap$\\rightarrow$CPSC",
    ("chapman", "ptbxl"): "Chap$\\rightarrow$PTB-XL",
    ("cpsc", "chapman"): "CPSC$\\rightarrow$Chap",
    ("cpsc", "ptbxl"): "CPSC$\\rightarrow$PTB-XL",
    ("ptbxl", "chapman"): "PTB-XL$\\rightarrow$Chap",
    ("ptbxl", "cpsc"): "PTB-XL$\\rightarrow$CPSC",
}

# (pair, arch, seed) -> {method: (ood_delta, id_delta)}
data: dict[tuple, dict] = {}
methods: list[str] = []
with open(TABLE, newline="", encoding="utf-8") as fh:
    for r in csv.DictReader(fh):
        m = r["method"]
        if m not in methods:
            methods.append(m)
        pair = tuple(r["pair"].split("_"))
        key = (pair, r["arch"], int(r["seed"]))
        data.setdefault(key, {})[m] = (
            float(r["ood_deltaECE"]), float(r["id_deltaECE"]),
        )

n_cells = len({k for k in data if k[1] in ARCHS and k[2] in SEEDS})
assert n_cells == 60, f"cell 数 {n_cells} != 60"

print("=" * 78)
print("表 1  tab:methods —— 8 方法 x InceptionTime（30 格）")
print("=" * 78)
print(f"{'Method':<12}{'Total':>8}{'Full/6':>8}{'dECE mean':>12}{'Neg dirs':>10}")
for m in methods:
    cells = [k for k in data if k[1] == "inceptiontime" and k[2] in SEEDS]
    vals = [data[k][m][0] for k in cells if m in data[k]]
    if not vals:
        continue
    sup = sum(1 for v in vals if v > 0)
    # 5/5 方向数 + 负方向数
    full = 0
    neg_dirs = 0
    for p in PAIR_ORDER:
        dv = [data[(p, "inceptiontime", s)][m][0]
              for s in SEEDS if (p, "inceptiontime", s) in data
              and m in data[(p, "inceptiontime", s)]]
        if not dv:
            continue
        if all(v > 0 for v in dv):
            full += 1
        if sum(dv) / len(dv) < 0:
            neg_dirs += 1
    print(f"{m:<12}{sup:>5}/30{full:>6}/6{sum(vals)/len(vals):>+12.4f}"
          f"{neg_dirs:>10}")

print()
print("=" * 78)
print("表 2  tab:arch_robust —— 6 pair x 2 架构")
print("=" * 78)
print(f"{'pair':<28}{'IT':>7}{'R1D':>7}{'Total':>8}{'neg':>5}")
tot_it = tot_r1 = 0
for p in PAIR_ORDER:
    row = {}
    for a in ARCHS:
        vs = [data[(p, a, s)]["ts"][0] for s in SEEDS
              if (p, a, s) in data]
        row[a] = (sum(1 for v in vs if v > 0), len(vs), vs)
    it_p, it_n, it_v = row["inceptiontime"]
    r1_p, r1_n, r1_v = row["resnet1d"]
    tot_it += it_p
    tot_r1 += r1_p
    nneg = (it_n - it_p) + (r1_n - r1_p)
    print(f"{PAIR_LABEL[p]:<28}{it_p:>4}/{it_n}{r1_p:>4}/{r1_n}"
          f"{it_p+r1_p:>5}/{(it_n+r1_n):<3}{nneg:>5}")
print("-" * 78)
print(f"{'TOTAL':<28}{tot_it:>4}/30{tot_r1:>4}/30"
      f"{tot_it+tot_r1:>5}/60   = {100*(tot_it+tot_r1)/60:.1f}%")

print()
it_all = [data[(p, "inceptiontime", s)]["ts"][0]
          for p in PAIR_ORDER for s in SEEDS]
r1_all = [data[(p, "resnet1d", s)]["ts"][0]
          for p in PAIR_ORDER for s in SEEDS]
allv = it_all + r1_all
print("Mean ΔECE   IT=%+.4f  R1D=%+.4f  All=%+.4f"
      % (sum(it_all)/len(it_all), sum(r1_all)/len(r1_all),
         sum(allv)/len(allv)))
print("Std  ΔECE   IT=%.4f  R1D=%.4f  All=%.4f"
      % (st.stdev(it_all), st.stdev(r1_all), st.stdev(allv)))
print("R1D/IT std ratio = %.2f" % (st.stdev(r1_all)/st.stdev(it_all)))
print("Median ΔECE IT=%+.4f  R1D=%+.4f  All=%+.4f"
      % (st.median(it_all), st.median(r1_all), st.median(allv)))

print()
print("=" * 78)
print("ID 对照（供 C2 段）")
print("=" * 78)
idv = [data[k]["ts"][1] for k in data if k[1] in ARCHS and k[2] in SEEDS]
print(f"  ID mean = {sum(idv)/len(idv):+.4f}   median = {st.median(idv):+.4f}")
print(f"  ID 正点估计 = {sum(1 for v in idv if v > 0)}/60")
print(f"  ID CI 含零  = 见 recompute_all_derived.py 第 5 节")
print(f"  OOD/ID 比值 = {(sum(allv)/len(allv))/(sum(idv)/len(idv)):.2f}x")

print()
print("=" * 78)
print("逐 pair 的 OOD/ID 均值（供 C2 的 stratum means 区间）")
print("=" * 78)
for p in PAIR_ORDER:
    for a in ARCHS:
        ks = [(p, a, s) for s in SEEDS if (p, a, s) in data]
        ov = [data[k]["ts"][0] for k in ks]
        iv = [data[k]["ts"][1] for k in ks]
        print(f"  {p[0][:6]:>6}->{p[1][:6]:<6} {a:<14}"
              f" OOD={sum(ov)/len(ov):+.4f}  ID={sum(iv)/len(iv):+.4f}")
