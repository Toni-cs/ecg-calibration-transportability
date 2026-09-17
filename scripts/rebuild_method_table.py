"""重建论文 tab:methods（8 方法对比表），从权威主表 + CI 口径。

## 为什么需要这个脚本

论文 `tab:methods` 的**全部 8 行**与 `results/c4_resnet1d_8method.csv`
（mtime 2026-09-06 18:32）的摘要段逐项吻合，说明该表源自 c4。

但 c4 与权威主表 `results/robustness_validation_5seeds.csv`（由
`checkpoints/transfer/**/transfer_result.json` 重建，已验证 480/480 逐位一致）
在 **471/480 格**上数值不同。二者用的是同一批 09-06 checkpoint，所以是**两次不同
的评估运行**，不能混用。

本脚本从**权威主表**重算该表，口径与论文一致：
  Total   = InceptionTime 30 格中 **CI 下界 > 0** 的格数（论文口径）
  Full/6  = 6 个方向上 5/5 全部 CI 支持的个数
  dECE    = 该架构 30 格的 ΔECE_OOD 均值
  Neg     = 方向均值 < 0 的方向数

用法:
    python scripts/rebuild_method_table.py
"""
from __future__ import annotations

import csv
from collections import defaultdict

TABLE = "results/robustness_validation_5seeds.csv"
C4 = "results/c4_resnet1d_8method.csv"
METHODS = ["ts", "platt", "isotonic", "vector", "matrix", "dirichlet",
           "em_prior", "bbse_prior"]
PRETTY = {
    "ts": "TS", "platt": "Platt", "isotonic": "Isotonic", "vector": "Vector",
    "matrix": "Matrix", "dirichlet": "Dirichlet", "em_prior": "EM prior",
    "bbse_prior": "BBSE prior",
}
SEEDS = (42, 43, 44, 45, 46)
PAIR_ORDER = ["chapman_cpsc", "chapman_ptbxl", "cpsc_chapman",
              "cpsc_ptbxl", "ptbxl_chapman", "ptbxl_cpsc"]

# (arch, pair, seed, method) -> (delta, ci_lo)
tab: dict = {}
with open(TABLE, newline="", encoding="utf-8") as fh:
    for r in csv.DictReader(fh):
        tab[(r["arch"], r["pair"], int(r["seed"]), r["method"])] = (
            float(r["ood_deltaECE"]), float(r["ood_ci_lo"]),
        )

# 重训前基线（git HEAD 版本），用于显示变动
PRE = "results/_pre_retrain_baseline_20260917/robustness_validation_5seeds.csv"
pre: dict = {}
try:
    with open(PRE, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            pre[(r["arch"], r["pair"], int(r["seed"]), r["method"])] = (
                float(r["ood_deltaECE"]), float(r["ood_ci_lo"]),
            )
except FileNotFoundError:
    pass


def summarize(src, arch):
    out = {}
    for m in METHODS:
        cells = [(p, s) for p in PAIR_ORDER for s in SEEDS
                 if (arch, p, s, m) in src]
        vals = [src[(arch, p, s, m)][0] for p, s in cells]
        ci = sum(1 for p, s in cells if src[(arch, p, s, m)][1] > 0)
        full = 0
        neg = 0
        for p in PAIR_ORDER:
            dv = [src[(arch, p, s, m)][0] for s in SEEDS
                  if (arch, p, s, m) in src]
            ci_all = all(src[(arch, p, s, m)][1] > 0 for s in SEEDS
                         if (arch, p, s, m) in src)
            if dv and ci_all:
                full += 1
            if dv and sum(dv) / len(dv) < 0:
                neg += 1
        out[m] = {
            "n": len(cells), "ci": ci, "full": full,
            "mean": sum(vals) / len(vals) if vals else float("nan"),
            "neg": neg,
        }
    return out


print("=" * 84)
print("论文 tab:methods —— 权威主表重建（CI 口径 = ci_lo > 0）")
print("=" * 84)
for arch, label in (("inceptiontime", "InceptionTime"), ("resnet1d", "ResNet1D")):
    cur = summarize(tab, arch)
    old = summarize(pre, arch) if pre else None
    print(f"\n--- {label} (30 格) ---")
    print(f"{'Method':<13}{'Total':>9}{'Full/6':>8}{'dECE mean':>12}{'Neg':>5}"
          f"   {'旧(重训前)':>22}")
    for m in METHODS:
        c = cur[m]
        o = f"{old[m]['ci']:>2}/30  {old[m]['mean']:+.4f}  {old[m]['neg']}" if old else ""
        print(f"{PRETTY[m]:<13}{c['ci']:>5}/30{c['full']:>6}/6{c['mean']:>+12.4f}"
              f"{c['neg']:>5}   {o:>22}")

print()
print("=" * 84)
print("LaTeX 行（InceptionTime，可直接粘贴）")
print("=" * 84)
cur = summarize(tab, "inceptiontime")
for m in METHODS:
    c = cur[m]
    print(f"{PRETTY[m]:<11}& {c['ci']}/30 & {c['full']}/6 & "
          f"${c['mean']:+.4f}$ & {c['neg']} \\\\")

print()
print("=" * 84)
print("与 c4（09-06，论文旧来源）的差异记录")
print("=" * 84)
c4 = {}
try:
    lines = open(C4, encoding="utf-8").read().splitlines()
    hdr = None
    insec = False
    for ln in lines:
        if ln.startswith("arch,pair,seed,method"):
            hdr = ln.split(",")
            insec = True
            continue
        if ln.startswith("##"):
            insec = False
            continue
        if insec and hdr and ln:
            p = ln.split(",")
            if len(p) != len(hdr):
                continue
            d = dict(zip(hdr, p))
            c4[(d["arch"], d["pair"], int(d["seed"]), d["method"])] = \
                float(d["ood_deltaECE"])
except FileNotFoundError:
    pass

if c4:
    common = set(tab) & set(c4)
    ndiff = sum(1 for k in common if abs(tab[k][0] - c4[k]) > 1e-9)
    print(f"  共同 cell: {len(common)}   数值不同: {ndiff}")
    print("  c4 摘要 support_rate（CI 口径）对照：")
    for m in METHODS:
        cells = [(p, s) for p in PAIR_ORDER for s in SEEDS
                 if ("inceptiontime", p, s, m) in c4]
        c4ci = sum(1 for p, s in cells
                   if c4[("inceptiontime", p, s, m)] > 0)
        print(f"    {PRETTY[m]:<13} c4 point>0 = {c4ci:>2}/30"
              f"   权威表 CI = {cur[m]['ci']:>2}/30")
    print()
    print("  ⚠️ c4 的 summary support_rate 是 CI 口径；其 per-cell 的 >0 计数")
    print("     与 summary 并不相等，说明 c4 内部 summary 由 support 列聚合。")
