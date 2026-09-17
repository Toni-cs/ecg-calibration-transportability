"""决定性检验：从 e6_probs.npz（60 格全覆盖）独立复算主终点 + T 分层

e6_probs.npz 含: T, id_raw, id_cal, id_labels, ood_raw, ood_cal, ood_labels
=> 可完全独立重算 smooth_ece 口径的 ood.raw / ood.cal / ΔECE，并做 T 分层。
"""
from __future__ import annotations
import csv, glob, json, os, sys, statistics as st

sys.path.insert(0, "D:/A1/ecg-lab-v2")
import numpy as np
from src.utils.calibration import smooth_ece

ROOT = "D:/A1/ecg-lab-v2"
PAIRS = ["chapman_cpsc", "chapman_ptbxl", "cpsc_chapman",
         "cpsc_ptbxl", "ptbxl_chapman", "ptbxl_cpsc"]
ARCHS = ["inceptiontime", "resnet1d"]
SEEDS = [42, 43, 44, 45, 46]


def top_ece(raw, cal, labels):
    """eval_transfer.py L262-265 + calibration.py L495-496 的完全复刻"""
    r = smooth_ece(np.asarray(raw).max(axis=1),
                   (np.asarray(cal).argmax(1) == np.asarray(labels)).astype(float))
    c = smooth_ece(np.asarray(cal).max(axis=1),
                   (np.asarray(cal).argmax(1) == np.asarray(labels)).astype(float))
    return r, c


rows = []
for pair in PAIRS:
    for arch in ARCHS:
        for seed in SEEDS:
            jp = os.path.join(ROOT, "checkpoints/transfer", pair, arch, f"seed{seed}", "transfer_result.json")
            npz = os.path.join(ROOT, "checkpoints/transfer", pair, arch, f"seed{seed}", "e6_probs.npz")
            d = json.load(open(jp, encoding="utf-8"))
            ts = d["methods"]["ts"]
            z = np.load(npz, allow_pickle=True)
            r, c = top_ece(z["ood_raw"], z["ood_cal"], z["ood_labels"])
            rows.append({
                "pair": pair, "arch": arch, "seed": seed,
                "T": float(z["T"]),
                "n_ood": int(z["n_ood"]),
                "json_raw": ts["ood"]["raw"], "json_cal": ts["ood"]["cal"],
                "json_d": ts["ood"]["deltaECE"],
                "re_raw": r, "re_cal": c, "re_d": r - c,
                "n_id": int(z["n_id"]),
            })

print("=" * 78)
print("检验 A：从 e6 原始概率独立复算 smooth_ece 口径（60 格）")
print("=" * 78)
print(f"cell 数 = {len(rows)}")
dr = max(abs(x["re_raw"] - x["json_raw"]) for x in rows)
dc = max(abs(x["re_cal"] - x["json_cal"]) for x in rows)
dd = max(abs(x["re_d"] - x["json_d"]) for x in rows)
print(f"max|raw_recomputed - json_raw|  = {dr:.3e}")
print(f"max|cal_recomputed - json_cal|  = {dc:.3e}")
print(f"max|ΔECE_recomputed - json_ΔECE| = {dd:.3e}")
print(f"  -> {'口径完全一致（数值到 float32 存储精度）' if dr < 1e-5 else '口径不一致！'}")

# 与 CSV 对照
csv_map = {(r["pair"], r["arch"], int(r["seed"])): float(r["ood_deltaECE"])
           for r in csv.DictReader(open(os.path.join(ROOT, "results/robustness_validation_5seeds.csv"),
                                        encoding="utf-8")) if r["method"] == "ts"}
d_csv = max(abs(csv_map[(x["pair"], x["arch"], x["seed"])] - x["re_d"]) for x in rows)
print(f"\nmax|CSV ood_deltaECE - e6 独立复算| = {d_csv:.3e}")
print(f"CSV 均值           = {st.mean(csv_map.values()):+.6f}")
print(f"e6 独立复算均值    = {st.mean([x['re_d'] for x in rows]):+.6f}")
print(f"json deltaECE 均值 = {st.mean([x['json_d'] for x in rows]):+.6f}")
v = [x["re_d"] for x in rows]
print(f"e6 独立复算 正值   = {sum(1 for y in v if y > 0)}/{len(v)} = "
      f"{100*sum(1 for y in v if y>0)/len(v):.1f}%")
print(f"论文声称           = +0.0159, 51/60 = 85.0%")

print()
print("=" * 78)
print("检验 B：T 分层（T 来自 e6_probs.npz，与主终点同源）")
print("=" * 78)
Ts = [(x["T"], x["re_d"], x["pair"], x["arch"], x["seed"]) for x in rows]
tv = [t for t, *_ in Ts]
print(f"T 范围 = [{min(tv):.4f}, {max(tv):.4f}]  mean={st.mean(tv):.4f} median={st.median(tv):.4f}")
print(f"T 未分层均值（对照）= {st.mean([d for _, d, *_ in Ts]):+.4f}")
print("\n--- 等频 5 分层（按 T 排序分位） ---")
srt = sorted(Ts, key=lambda x: x[0])
q = len(srt) // 5
for i in range(5):
    seg = srt[i * q:(i + 1) * q] if i < 4 else srt[4 * q:]
    tvals = [s[0] for s in seg]
    dvals = [s[1] for s in seg]
    print(f"  Q{i+1}: T∈[{min(tvals):.3f},{max(tvals):.3f}] n={len(seg):2d}  "
          f"meanΔECE={st.mean(dvals):+.4f}  pos={sum(1 for y in dvals if y>0)}/{len(dvals)}")

print("\n--- 固定阈值分层（预注册语义：T<1 尖锐 / T>1 过平滑） ---")
for lo, hi, nm in [(0, 1.0, "T<1 (尖锐)"), (1.0, 1.5, "1≤T<1.5"),
                   (1.5, 2.0, "1.5≤T<2"), (2.0, 3.0, "2≤T<3"), (3.0, 99, "T≥3")]:
    s = [d for t, d, *_ in Ts if lo <= t < hi]
    if s:
        print(f"  {nm:12s} n={len(s):2d}  meanΔECE={st.mean(s):+.4f}  "
              f"pos={sum(1 for y in s if y>0)}/{len(s)}")

tt = [t for t, *_ in Ts]
dd = [d for _, d, *_ in Ts]
mt, md = st.mean(tt), st.mean(dd)
cov = sum((a - mt) * (b - md) for a, b in zip(tt, dd)) / len(tt)
vt = sum((a - mt) ** 2 for a in tt) / len(tt)
vd = sum((b - md) ** 2 for b in dd) / len(dd)
c = cov / (vt ** .5 * vd ** .5)
print(f"\ncorr(ΔECE, T) = {c:+.4f}   R² = {c*c:.4f}   n={len(Ts)}")

# 秩相关（对单调性更稳健）
def spearman(a, b):
    def rank(x):
        order = sorted(range(len(x)), key=lambda i: x[i])
        r = [0.0] * len(x)
        for pos, i in enumerate(order):
            r[i] = pos
        return r
    ra, rb = rank(a), rank(b)
    ma, mb = st.mean(ra), st.mean(rb)
    cab = sum((p - ma) * (q2 - mb) for p, q2 in zip(ra, rb))
    va = sum((p - ma) ** 2 for p in ra) ** .5
    vb = sum((q2 - mb) ** 2 for q2 in rb) ** .5
    return cab / (va * vb)
print(f"Spearman(ΔECE, T) = {spearman(tt, dd):+.4f}")

# 控制 T 后 ΔECE 是否仍为正：对 T 分箱内做单样本检验
print("\n--- 关键：T 中位数切分（高/低 T 组） ---")
med = st.median(tt)
lo_g = [d for t, d, *_ in Ts if t <= med]
hi_g = [d for t, d, *_ in Ts if t > med]
print(f"  T≤{med:.3f}: n={len(lo_g):2d} meanΔECE={st.mean(lo_g):+.4f} "
      f"sd={st.stdev(lo_g):.4f} pos={sum(1 for y in lo_g if y>0)}/{len(lo_g)}")
print(f"  T>{med:.3f}: n={len(hi_g):2d} meanΔECE={st.mean(hi_g):+.4f} "
      f"sd={st.stdev(hi_g):.4f} pos={sum(1 for y in hi_g if y>0)}/{len(hi_g)}")
print(f"  两组差 = {st.mean(hi_g)-st.mean(lo_g):+.4f}")
