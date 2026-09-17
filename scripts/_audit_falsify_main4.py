"""攻击 5（决定性）：T 分层

事实链：
- transfer_result.json 全部 126 份的 methods.ts.meta = {n_bootstrap,bci_method,ts_fit,metric}
  → **不含 T**。主终点文件里没有温度。
- 唯一逐格 T 存活于 checkpoints/transfer/<pair>/<arch>/seed<k>/e6_probs.npz（60 份，Sep 11）。
- 但 src/data/mapping.py 于 2026-09-09 20:26 被改（git: dd96647→452b3bf）：
      SUBSPACE_CPSC: ("NORM","CD","STTC","MI")  ->  ("NORM","MI","STTC","CD")
  主终点 JSON 产出于 09-08（subspace 字段仍是旧序），e6 产出于 09-11（新序）。
  → 40 个涉及 CPSC 的 cell 上 e6 与主终点标签编码不同，e6 不可用。
- 20 个不涉及 CPSC 的 cell（chapman_ptbxl, ptbxl_chapman）标签编码未变
  → e6 与主终点逐位一致，可用于 T 分层。
"""
from __future__ import annotations
import csv, json, os, statistics as st, sys

sys.path.insert(0, "D:/A1/ecg-lab-v2")
import numpy as np
from src.utils.calibration import smooth_ece

ROOT = "D:/A1/ecg-lab-v2"
CLEAN_PAIRS = ["chapman_ptbxl", "ptbxl_chapman"]      # 不含 CPSC
CPSC_PAIRS = ["chapman_cpsc", "cpsc_chapman", "cpsc_ptbxl", "ptbxl_cpsc"]
ARCHS = ["inceptiontime", "resnet1d"]
SEEDS = [42, 43, 44, 45, 46]


def top_ece(raw, cal, labels):
    b = (np.asarray(cal).argmax(1) == np.asarray(labels)).astype(float)
    return (smooth_ece(np.asarray(raw).max(axis=1), b),
            smooth_ece(np.asarray(cal).max(axis=1), b))


def load(pairs):
    out = []
    for pair in pairs:
        for arch in ARCHS:
            for seed in SEEDS:
                base = os.path.join(ROOT, "checkpoints/transfer", pair, arch, f"seed{seed}")
                d = json.load(open(base + "/transfer_result.json", encoding="utf-8"))
                z = np.load(base + "/e6_probs.npz", allow_pickle=True)
                r, c = top_ece(z["ood_raw"], z["ood_cal"], z["ood_labels"])
                out.append({"pair": pair, "arch": arch, "seed": seed,
                            "T": float(z["T"]), "re_d": r - c,
                            "json_d": d["methods"]["ts"]["ood"]["deltaECE"]})
    return out


print("=" * 78)
print("步骤 1：确认 e6 与主终点在 20 个非 CPSC cell 上逐位一致")
print("=" * 78)
clean = load(CLEAN_PAIRS)
mx = max(abs(x["re_d"] - x["json_d"]) for x in clean)
print(f"非 CPSC cell 数 = {len(clean)}")
print(f"max|ΔECE(e6 独立复算) - ΔECE(主终点 JSON)| = {mx:.3e}")
print(f"e6 均值   = {st.mean([x['re_d'] for x in clean]):+.6f}")
print(f"JSON 均值 = {st.mean([x['json_d'] for x in clean]):+.6f}")

cpsc = load(CPSC_PAIRS)
mx2 = max(abs(x["re_d"] - x["json_d"]) for x in cpsc)
print(f"\n（对照）CPSC cell 数 = {len(cpsc)}")
print(f"max|ΔECE(e6) - ΔECE(主终点)| = {mx2:.3e}  <- 标签编码已变，e6 失效")
print(f"e6 均值 = {st.mean([x['re_d'] for x in cpsc]):+.6f} vs JSON 均值 = "
      f"{st.mean([x['json_d'] for x in cpsc]):+.6f}")

print()
print("=" * 78)
print("步骤 2：T 分层（仅 20 个非 CPSC cell，e6 == 主终点）")
print("=" * 78)
Ts = [(x["T"], x["re_d"]) for x in clean]
tv = [t for t, _ in Ts]
dv = [d for _, d in Ts]
print(f"T 范围 = [{min(tv):.4f}, {max(tv):.4f}]  mean={st.mean(tv):.4f}  median={st.median(tv):.4f}")
print(f"未分层 ΔECE 均值 = {st.mean(dv):+.4f}  median={st.median(dv):+.4f}  "
      f"pos={sum(1 for d in dv if d>0)}/{len(dv)}")

print("\n--- 等频 4 分层（按 T 排序，n=20 → 每层 5） ---")
srt = sorted(Ts, key=lambda x: x[0])
for i in range(4):
    seg = srt[i * 5:(i + 1) * 5]
    t = [s[0] for s in seg]; d = [s[1] for s in seg]
    print(f"  Q{i+1}: T∈[{min(t):.3f},{max(t):.3f}] n={len(seg)}  meanΔECE={st.mean(d):+.4f}  "
          f"pos={sum(1 for y in d if y>0)}/{len(d)}")

print("\n--- 固定阈值（预注册语义 T<1 尖锐 / T>1 过平滑） ---")
for lo, hi, nm in [(0, 1.0, "T<1"), (1.0, 1.5, "1≤T<1.5"),
                   (1.5, 2.0, "1.5≤T<2"), (2.0, 99, "T≥2")]:
    s = [d for t, d in Ts if lo <= t < hi]
    if s:
        print(f"  {nm:10s} n={len(s):2d}  meanΔECE={st.mean(s):+.4f}  "
              f"pos={sum(1 for y in s if y>0)}/{len(s)}")

print("\n--- 按 pair 拆分（T 分布是否本身就在 pair 间不同） ---")
for pair in CLEAN_PAIRS:
    s = [(x["T"], x["re_d"]) for x in clean if x["pair"] == pair]
    print(f"  {pair:16s} n={len(s)}  T: mean={st.mean([a for a,_ in s]):.3f} "
          f"range=[{min(a for a,_ in s):.3f},{max(a for a,_ in s):.3f}]  "
          f"ΔECE mean={st.mean([b for _,b in s]):+.4f}")

def pearson(a, b):
    ma, mb = st.mean(a), st.mean(b)
    cab = sum((p - ma) * (q - mb) for p, q in zip(a, b))
    va = sum((p - ma) ** 2 for p in a) ** .5
    vb = sum((q - mb) ** 2 for q in b) ** .5
    return cab / (va * vb)

def spearman(a, b):
    def rk(x):
        o = sorted(range(len(x)), key=lambda i: x[i]); r = [0.0] * len(x)
        for pos, i in enumerate(o): r[i] = pos
        return r
    return pearson(rk(a), rk(b))

print(f"\ncorr(ΔECE, T)   = {pearson(tv, dv):+.4f}   R²={pearson(tv,dv)**2:.4f}")
print(f"Spearman(ΔECE,T) = {spearman(tv, dv):+.4f}")

print("\n--- 分层内去趋势：控制 T 后 ΔECE 是否仍显著为正 ---")
med = st.median(tv)
lo_g = [d for t, d in Ts if t <= med]; hi_g = [d for t, d in Ts if t > med]
print(f"  T≤{med:.3f}: n={len(lo_g)} meanΔECE={st.mean(lo_g):+.4f} sd={st.stdev(lo_g):.4f} "
      f"pos={sum(1 for y in lo_g if y>0)}/{len(lo_g)}")
print(f"  T>{med:.3f}: n={len(hi_g)} meanΔECE={st.mean(hi_g):+.4f} sd={st.stdev(hi_g):.4f} "
      f"pos={sum(1 for y in hi_g if y>0)}/{len(hi_g)}")
# 低 T 组单样本 t
import math
t_lo = st.mean(lo_g) / (st.stdev(lo_g) / math.sqrt(len(lo_g)))
t_hi = st.mean(hi_g) / (st.stdev(hi_g) / math.sqrt(len(hi_g)))
print(f"  低 T 组 t = {t_lo:.2f} (df={len(lo_g)-1})   高 T 组 t = {t_hi:.2f} (df={len(hi_g)-1})")
