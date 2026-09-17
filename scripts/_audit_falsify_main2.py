"""证伪审计 第二阶段：逐格比对 / 去重策略 / T 分层"""
from __future__ import annotations
import csv, glob, json, os, statistics as st
from collections import defaultdict

ROOT = "D:/A1/ecg-lab-v2"
OFFICIAL_PAIRS = {"chapman_cpsc", "chapman_ptbxl", "cpsc_chapman",
                  "cpsc_ptbxl", "ptbxl_chapman", "ptbxl_cpsc"}
ARCHS = {"inceptiontime", "resnet1d"}
SEEDS = {42, 43, 44, 45, 46}

paths = sorted(set(glob.glob(os.path.join(ROOT, "**", "transfer_result.json"), recursive=True)))
recs = []
for p in paths:
    d = json.load(open(p, encoding="utf-8"))
    ts = d.get("methods", {}).get("ts", {}) or {}
    ood = ts.get("ood") or {}
    if "raw" not in ood or "cal" not in ood:
        continue
    recs.append({
        "path": os.path.relpath(p, ROOT).replace("\\", "/"),
        "pair": f"{d.get('source')}_{d.get('target')}",
        "src": d.get("source"), "tgt": d.get("target"),
        "arch": d.get("arch"), "seed": d.get("seed"),
        "n_ood": d.get("n_ood"),
        "raw": ood["raw"], "cal": ood["cal"], "d": ood["raw"] - ood["cal"],
        "d_stored": ood.get("deltaECE"),
        "id_raw": (ts.get("id") or {}).get("raw"),
        "id_cal": (ts.get("id") or {}).get("cal"),
        "id_d": (ts.get("id") or {}).get("deltaECE"),
        "T": (ts.get("meta") or {}).get("T"),
        "meta": ts.get("meta"),
        "mtime": os.path.getmtime(p),
    })

def summarize(v, label):
    n = len(v)
    pos = sum(1 for x in v if x > 0)
    print(f"  {label:52s} n={n:3d}  mean={st.mean(v):+.4f}  median={st.median(v):+.4f}  "
          f"pos={pos}/{n}={100*pos/n:.1f}%")
    return st.mean(v)

print("=" * 78)
print("攻击 3：去重策略")
print("=" * 78)

# 只看官方 pair/arch/seed
off = [r for r in recs if r["pair"] in OFFICIAL_PAIRS and r["arch"] in ARCHS and r["seed"] in SEEDS]
print(f"[官方过滤] 记录数 = {len(off)}  唯一 cell = {len({(r['pair'],r['arch'],r['seed']) for r in off})}")

# 全部记录（用户的宽松过滤：arch in 正式架构）
loose = [r for r in recs if r["arch"] in ARCHS]
print(f"[宽松过滤] 记录数 = {len(loose)}  唯一 cell = {len({(r['pair'],r['arch'],r['seed']) for r in loose})}")

print()
print("--- 策略 A：官方 60 格（pair∈6, arch∈2, seed∈5），逐格取唯一值 ---")
A = {}
for r in off:
    k = (r["pair"], r["arch"], r["seed"])
    A.setdefault(k, []).append(r)
print(f"  唯一 cell = {len(A)}")
dup = {k: v for k, v in A.items() if len(v) > 1}
print(f"  多记录 cell = {len(dup)}")
diffdup = []
for k, v in dup.items():
    vals = {round(x["d"], 12) for x in v}
    if len(vals) > 1:
        diffdup.append((k, sorted(vals)))
print(f"  多记录且数值不一致的 cell = {len(diffdup)}")
for k, vals in diffdup:
    print(f"     {k} 值={vals}")
meanA = summarize([v[0]["d"] for v in A.values()], "A: 官方60格(任意一份)")

print()
print("--- 策略 B：保留第一份（按路径排序） ---")
B = {}
for r in sorted(off, key=lambda x: x["path"]):
    k = (r["pair"], r["arch"], r["seed"])
    B.setdefault(k, r)
meanB = summarize([r["d"] for r in B.values()], "B: first-by-path")

print()
print("--- 策略 C：保留最后一份（按路径排序） ---")
C = {}
for r in sorted(off, key=lambda x: x["path"]):
    C[(r["pair"], r["arch"], r["seed"])] = r
meanC = summarize([r["d"] for r in C.values()], "C: last-by-path")

print()
print("--- 策略 D：同 cell 取平均 ---")
D = {}
for k, v in A.items():
    D[k] = st.mean([x["d"] for x in v])
meanD = summarize(list(D.values()), "D: mean-of-dups")

print()
print("--- 策略 E：用户脚本口径（arch∈正式，不限定 pair/seed） ---")
E = {}
for r in sorted(loose, key=lambda x: x["path"]):
    E[(r["pair"], r["arch"], r["seed"])] = r
meanE = summarize([r["d"] for r in E.values()], "E: 用户口径(宽松,last)")
extra = {k: r for k, r in E.items() if k not in C}
print(f"  E 比 C 多出的 cell = {len(extra)}")
for k, r in extra.items():
    print(f"     {k}  d_ood={r['d']:+.6f}  n_ood={r['n_ood']}  {r['path']}")

print()
print("=" * 78)
print("攻击 2：CSV vs transfer_result.json 逐格比对（60 格）")
print("=" * 78)
rows = [r for r in csv.DictReader(open(os.path.join(ROOT, "results/robustness_validation_5seeds.csv"),
                                      encoding="utf-8")) if r["method"] == "ts"]
print(f"CSV ts 行数 = {len(rows)}")
csv_map = {(r["pair"], r["arch"], int(r["seed"])): float(r["ood_deltaECE"]) for r in rows}
json_map = {k: v[0]["d_stored"] for k, v in A.items()}
print(f"CSV cell = {len(csv_map)}  JSON cell = {len(json_map)}")
only_csv = set(csv_map) - set(json_map)
only_json = set(json_map) - set(csv_map)
print(f"仅 CSV 有 = {len(only_csv)}  仅 JSON 有 = {len(only_json)}")
diffs = []
for k in sorted(set(csv_map) & set(json_map)):
    diffs.append((abs(csv_map[k] - json_map[k]), k, csv_map[k], json_map[k]))
diffs.sort(reverse=True)
print(f"共同 cell = {len(diffs)}")
print(f"max|diff| = {diffs[0][0]:.3e}   @ {diffs[0][1]}")
print(f"CSV 均值 = {st.mean(csv_map.values()):+.6f}")
print(f"JSON(deltaECE) 均值 = {st.mean(json_map.values()):+.6f}")
print("前 5 大差异：")
for dd, k, a, b in diffs[:5]:
    print(f"   {k}  csv={a:.9f} json={b:.9f} diff={dd:.3e}")

print()
print("=" * 78)
print("攻击 5：T 分层")
print("=" * 78)
nT = sum(1 for r in recs if r["T"] is not None)
print(f"含 meta.T 的记录 = {nT}/{len(recs)}")
Ts = [(r["T"], r["d"]) for r in off if r["T"] is not None]
print(f"官方 60 格中含 T 的 = {len(Ts)}")
if Ts:
    for lo, hi in [(0, 1.2), (1.2, 1.6), (1.6, 2.2), (2.2, 3.0), (3.0, 10)]:
        s = [d for t, d in Ts if lo <= t < hi]
        if s:
            print(f"  T∈[{lo},{hi}) n={len(s):2d}  meanΔECE={st.mean(s):+.4f}")
    tt = [t for t, _ in Ts]; dd = [d for _, d in Ts]
    mt, md = st.mean(tt), st.mean(dd)
    cov = sum((a-mt)*(b-md) for a, b in zip(tt, dd))/len(tt)
    vt = sum((a-mt)**2 for a in tt)/len(tt); vd = sum((b-md)**2 for b in dd)/len(dd)
    c = cov/(vt**.5*vd**.5)
    print(f"  corr(ΔECE, T) = {c:+.4f}  R² = {c*c:.4f}  n={len(Ts)}")
else:
    print("  官方 60 格无 T（旧版脚本产出，meta 无 T 字段）")
    print("  -> 需从别处找 T：检查 temperature 缓存 / ts 参数落盘")
