"""证伪审计：论文主终点 ΔECE_OOD = +0.0159 能否从存活数据复现？

攻击 1：口径确认（smooth_ece vs ece；top-label 定义；ood 定义）
攻击 2：CSV vs transfer_result.json 逐格比对（60 格）
攻击 3：去重策略（first / last / mean）对均值的影响
攻击 4：幽灵记录枚举（126 文件 / 122 正式架构记录 / 60 官方格）
攻击 5：T 分层（从 transfer_result.json 复算）
"""
from __future__ import annotations
import csv, glob, json, math, os, statistics as st
from collections import defaultdict

ROOT = "D:/A1/ecg-lab-v2"
OFFICIAL_PAIRS = {"chapman_cpsc", "chapman_ptbxl", "cpsc_chapman",
                  "cpsc_ptbxl", "ptbxl_chapman", "ptbxl_cpsc"}
ARCHS = {"inceptiontime", "resnet1d"}
SEEDS = {42, 43, 44, 45, 46}

print("=" * 78)
print("攻击 1：口径（读脚本 + 结构验证）")
print("=" * 78)
# eval_transfer.py L259: metric_fn = smooth_ece_gpu if args.gpu_inference else smooth_ece
# L262-265: benefit_inference(_maxprob(ood_probs), _maxprob(ood_cal), _bin(ood_cal, ood_labels), metric=...)
# L303-304: _maxprob = max axis1 ; _bin = (argmax==label)
# calibration.py L495-497: raw_point=metric(probs_raw,labels); cal_point=metric(probs_cal,labels)
#                           benefit_point = raw_point - cal_point
# => ood.raw / ood.cal 是 top-label SmoothECE 的绝对值；ood.deltaECE == raw - cal（同一性）
print("[口径] metric_fn = smooth_ece_gpu if --gpu-inference else smooth_ece  (eval_transfer.py:259)")
print("[口径] ood.raw = smooth_ece(maxprob(raw_probs), correct_bin)          (calibration.py:495)")
print("[口径] ood.cal = smooth_ece(maxprob(cal_probs), correct_bin)          (calibration.py:496)")
print("[口径] ood 指 target-test 前向（eval_transfer.py:167-171）")
print("[口径] 恒等式 ood.deltaECE == ood.raw - ood.cal（calibration.py:497）")

# ---- 枚举全部 transfer_result.json ----
paths = sorted(set(glob.glob(os.path.join(ROOT, "**", "transfer_result.json"), recursive=True)))
print(f"\n[文件] 全仓库 transfer_result.json = {len(paths)}")

recs = []
for p in paths:
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception as e:
        print("  读取失败", p, e); continue
    m = d.get("methods", {})
    ts = m.get("ts")
    recs.append({
        "path": os.path.relpath(p, ROOT).replace("\\", "/"),
        "src": d.get("source"), "tgt": d.get("target"),
        "arch": d.get("arch"), "seed": d.get("seed"),
        "n_ood": d.get("n_ood"), "n_id": d.get("n_id"),
        "nc": d.get("num_classes"),
        "has_ts": ts is not None,
        "ts_keys": sorted(ts.keys()) if isinstance(ts, dict) else None,
        "raw": (ts or {}).get("ood", {}).get("raw") if isinstance(ts, dict) else None,
        "cal": (ts or {}).get("ood", {}).get("cal") if isinstance(ts, dict) else None,
        "d_ood": (ts or {}).get("ood", {}).get("deltaECE") if isinstance(ts, dict) else None,
        "id_raw": (ts or {}).get("id", {}).get("raw") if isinstance(ts, dict) else None,
        "id_cal": (ts or {}).get("id", {}).get("cal") if isinstance(ts, dict) else None,
        "id_d": (ts or {}).get("id", {}).get("deltaECE") if isinstance(ts, dict) else None,
        "decay": (ts or {}).get("decay") if isinstance(ts, dict) else None,
        "T": ((ts or {}).get("meta") or {}).get("T") if isinstance(ts, dict) else None,
        "meta": (ts or {}).get("meta") if isinstance(ts, dict) else None,
        "mtime": os.path.getmtime(p),
    })

print(f"[记录] 成功解析 = {len(recs)}")
print(f"[记录] 含 ts 方法 = {sum(1 for r in recs if r['has_ts'])}")
print(f"[记录] arch ∈ 正式架构 = {sum(1 for r in recs if r['arch'] in ARCHS)}")

# 恒等式检查
bad_id = [r for r in recs if r["has_ts"] and r["raw"] is not None and r["cal"] is not None
          and abs(r["d_ood"] - (r["raw"] - r["cal"])) > 1e-12]
print(f"[恒等式] |deltaECE-(raw-cal)|>1e-12 的记录数 = {len(bad_id)}")

# 口径字符串
metas = defaultdict(int)
for r in recs:
    if r["meta"]:
        metas[json.dumps(r["meta"], sort_keys=True)] += 1
print(f"[meta 变体] 共 {len(metas)} 种：")
for k, v in sorted(metas.items(), key=lambda x: -x[1]):
    print(f"   n={v:3d}  {k}")

print()
print("=" * 78)
print("攻击 4：幽灵记录枚举")
print("=" * 78)
groups = defaultdict(list)
for r in recs:
    key = (r["src"], r["tgt"], r["arch"], r["seed"])
    groups[key].append(r)

official_cells = {k: v for k, v in groups.items()
                  if f"{k[0]}_{k[1]}" in OFFICIAL_PAIRS and k[2] in ARCHS and k[3] in SEEDS}
ghost_cells = {k: v for k, v in groups.items() if k not in official_cells}
print(f"[cell] 全部唯一 cell = {len(groups)}")
print(f"[cell] 官方格 = {len(official_cells)}")
print(f"[cell] 非官方/幽灵 cell = {len(ghost_cells)}")
print("\n非官方 cell 明细：")
for k in sorted(ghost_cells):
    for r in ghost_cells[k]:
        print(f"   {k[0]}->{k[1]} {k[2]:14s} seed{k[3]}  n_ood={r['n_ood']:>5}  "
              f"d_ood={r['d_ood'] if r['d_ood'] is None else round(r['d_ood'],6)}  "
              f"ts_keys={r['ts_keys']}  {r['path']}")

print("\n官方 cell 中记录数 >1 的（重复/覆盖）：")
for k in sorted(official_cells):
    if len(official_cells[k]) > 1:
        for r in official_cells[k]:
            print(f"   {k[0]}->{k[1]} {k[2]:14s} seed{k[3]}  n_ood={r['n_ood']:>5}  "
                  f"d_ood={r['d_ood'] if r['d_ood'] is None else round(r['d_ood'],6)}  {r['path']}")

print(f"\n[幽灵统计] 非官方 cell 记录的 d_ood 数 = "
      f"{sum(1 for k in ghost_cells for r in ghost_cells[k] if r['d_ood'] is not None)}")
ghost_vals = [r["d_ood"] for k in ghost_cells for r in ghost_cells[k] if r["d_ood"] is not None]
if ghost_vals:
    print(f"            其均值 = {st.mean(ghost_vals):+.4f} "
          f"（若混入官方 60 格会污染主终点）")
