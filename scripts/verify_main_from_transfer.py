"""决定性检验：主结果 +0.0159 能否从存活的 transfer_result.json 复现？

若不能 → 论文主终点也失去 provenance（比 §real_shapley 更严重）。

口径说明（2026-09-16 修订）：
  transfer_result.json 里的 raw/cal/deltaECE 是 **OLD 编码**（模型训练编码）
  下的值，与论文主终点一致，可直接使用。
  （与之相对，checkpoints/e2_probs_cache/*.npz 的 labels 是 NEW 编码，
   直接算会得到被污染的 +0.1066。详见该目录 _CONTAMINATION_NOTICE.md。）

本脚本只读。
"""
from __future__ import annotations

import csv
import glob
import json
import statistics as st

# 设计规定的 6 个迁移对（含自迁移的 cpsc_cpsc 是冒烟测试，不在设计内）
EXPECTED_PAIRS = {
    ("chapman", "cpsc"), ("chapman", "ptbxl"),
    ("cpsc", "chapman"), ("cpsc", "ptbxl"),
    ("ptbxl", "chapman"), ("ptbxl", "cpsc"),
}
MAIN_ARCHS = ("inceptiontime", "resnet1d")
EXPECTED_N = 60          # 6 pairs x 2 archs x 5 seeds
EXPECTED_SEEDS = (42, 43, 44, 45, 46)

paths = sorted(set(
    glob.glob("checkpoints/**/transfer_result.json", recursive=True)
    + glob.glob("results/**/transfer_result.json", recursive=True)
    + glob.glob("**/transfer_result.json", recursive=True)
))
print("transfer_result.json 总数:", len(paths))

rows = []
n_smoke = n_selfpair = 0
for p in paths:
    try:
        d = json.load(open(p, encoding="utf-8"))
    except Exception:
        continue
    m = d.get("methods", {})
    if "ts" not in m:
        continue
    ts = m["ts"]
    ood = ts.get("ood", {})
    idm = ts.get("id", {})
    if "raw" not in ood or "cal" not in ood:
        continue

    src, tgt = d.get("source"), d.get("target")
    arch = d.get("architecture") or d.get("arch")
    seed = d.get("seed")

    # --- 排除冒烟/自迁移 cell（关键修复）---------------------------------
    # 1) 路径含 smoke（如 checkpoints/cpsc_transfer_smoke/...）
    if "smoke" in p.replace("\\", "/").lower():
        n_smoke += 1
        continue
    # 2) 源==目标（自迁移不在 6 对设计内）
    if src == tgt:
        n_selfpair += 1
        continue
    # 3) 不在设计内迁移对
    if (src, tgt) not in EXPECTED_PAIRS:
        continue

    rows.append({
        "path": p,
        "src": src, "tgt": tgt, "arch": arch, "seed": seed,
        "ood_raw": ood["raw"], "ood_cal": ood["cal"],
        "d_ood": ood["raw"] - ood["cal"],
        "id_raw": idm.get("raw"), "id_cal": idm.get("cal"),
        # transfer_result.json **不存 T**（meta 只有 ts_fit="source_cal"），
        # 故 T 留空，稍后从 npz 按 OLD 编码重算。
        "T": None,
        # 该 cell 存档时的标签映射 —— 这是编码口径的**第一方证据**
        "label_map": d.get("label_map"),
    })

print(f"排除冒烟 cell: {n_smoke}  排除自迁移 cell: {n_selfpair}")
print("含 ts 且 ood raw/cal 的记录:", len(rows))
if not rows:
    print("结构样例:")
    d = json.load(open(paths[0], encoding="utf-8"))
    print(json.dumps(d, ensure_ascii=False, indent=1)[:1500])
    raise SystemExit(0)

# 只保留正式架构
main = [r for r in rows if r["arch"] in MAIN_ARCHS]
print("正式架构记录:", len(main))

# 去重（同 cell 可能多份）
uniq = {}
for r in main:
    k = (r["src"], r["tgt"], r["arch"], r["seed"])
    uniq[k] = r
print("去重后 cell 数:", len(uniq))

# --- 自校验：必须恰好 60 格，且 seed 集合正确 -------------------------
assert len(uniq) == EXPECTED_N, (
    f"期望 {EXPECTED_N} 格，实得 {len(uniq)}。"
    f"若有新增/缺失 cell，请先核对设计再改此断言，不要直接放宽。"
)
for k in uniq:
    assert k[3] in EXPECTED_SEEDS, f"非设计 seed: {k}"
print(f"✓ 自校验通过：{len(uniq)} 格 = 6 pairs x 2 archs x 5 seeds")

v = [r["d_ood"] for r in uniq.values()]
print()
print("=== 从 transfer_result.json 复算 OOD ΔECE ===")
print("n = %d  mean %+.4f  median %+.4f" % (len(v), st.mean(v), st.median(v)))
print("正值: %d/%d = %.1f%%" % (sum(1 for x in v if x > 0), len(v),
                                 100 * sum(1 for x in v if x > 0) / len(v)))
print("论文主终点: mean +0.0159, 51/60 = 85.0%")
print()

# 与 robustness_validation_5seeds.csv 对照
try:
    rv = [r for r in csv.DictReader(
        open("results/robustness_validation_5seeds.csv", encoding="utf-8"))
        if r["method"] == "ts"]
    print("robustness_validation_5seeds.csv (ts): n=%d mean %+.4f"
          % (len(rv), st.mean([float(r["ood_deltaECE"]) for r in rv])))
except Exception as e:
    print("读 robustness csv 失败:", e)

# --- 第一方证据：存档 label_map 是否全为 OLD 编码 -----------------------
print()
print("=== 存档 label_map 编码核验（第一方证据）===")
lm_cpsc = {json.dumps(r["label_map"], sort_keys=True, ensure_ascii=False)
           for r in uniq.values() if "cpsc" in (r["src"], r["tgt"])}
lm_non = {json.dumps(r["label_map"], sort_keys=True, ensure_ascii=False)
          for r in uniq.values() if "cpsc" not in (r["src"], r["tgt"])}
print("  含 CPSC 的 cell 的 label_map 取值集合:", lm_cpsc)
print("  非 CPSC 的 cell 的 label_map 取值集合:", lm_non)
EXPECTED_CPS_CLM = '{"CD": 1, "MI": 3, "NORM": 0, "STTC": 2}'
if lm_cpsc == {EXPECTED_CPS_CLM}:
    print("  ✓ 全部含 CPSC cell 均为 OLD 编码 (NORM=0,CD=1,STTC=2,MI=3)")
    print("    → 存档文件自身证明模型按 OLD 顺序评估，支持 SUBSPACE_CPSC 回退。")
else:
    print("  ⚠️ 存在非 OLD 编码的 cell，需排查：", lm_cpsc)

# --- 从 npz 按 OLD 编码重算 T（transfer_result.json 不存 T）-------------
print()
print("=== T 分层（从 e2_probs_cache/*.npz 按 OLD 编码重算）===")
try:
    import sys as _sys
    from pathlib import Path as _Path
    import numpy as _np
    _ROOT = _Path(__file__).resolve().parents[1]
    _sys.path.insert(0, str(_ROOT))
    from src.utils.calibration import (
        apply_temperature as _apply, fit_temperature as _fit)

    def _swap13(y):
        o = y.copy()
        o[y == 1] = 3
        o[y == 3] = 1
        return o

    def _onehot(y, k):
        m = _np.zeros((len(y), k))
        m[_np.arange(len(y)), y] = 1.0
        return m

    _CACHE = _ROOT / "checkpoints" / "e2_probs_cache"
    T_by_key = {}
    for k in uniq:
        stem = f"{k[0]}_{k[1]}_{k[2]}_seed{k[3]}"
        f = _CACHE / f"{stem}.npz"
        if not f.exists():
            continue
        dd = _np.load(f)
        cp = dd["cal_probs"].astype(float)
        cy = dd["cal_labels"].astype(int)
        if "cpsc" in (k[0], k[1]):
            cy = _swap13(cy)          # 换回 OLD 编码
        T_by_key[k] = float(_fit(cp, _onehot(cy, cp.shape[1])))

    Ts = [(T_by_key[k], r["d_ood"]) for k, r in uniq.items() if k in T_by_key]
    if Ts:
        print("  n = %d  T 中位 %.4f  范围 [%.4f, %.4f]"
              % (len(Ts), st.median([t for t, _ in Ts]),
                 min(t for t, _ in Ts), max(t for t, _ in Ts)))
        print("  T >= 2 的比例: %.1f%%"
              % (100 * sum(1 for t, _ in Ts if t >= 2) / len(Ts)))
        for lo, hi in [(0, 1.5), (1.5, 2), (2, 3), (3, 5)]:
            s = [d for t, d in Ts if lo <= t < hi]
            if s:
                print("    T∈[%.1f,%.1f) n=%2d  mean %+.4f" % (lo, hi, len(s), st.mean(s)))
        tt = [t for t, _ in Ts]
        dd_ = [d for _, d in Ts]
        mt, md = st.mean(tt), st.mean(dd_)
        cov = sum((a - mt) * (b - md) for a, b in zip(tt, dd_)) / len(tt)
        vt = sum((a - mt) ** 2 for a in tt) / len(tt)
        vd = sum((b - md) ** 2 for b in dd_) / len(dd_)
        c = cov / (vt ** .5 * vd ** .5)
        print("    corr(ΔECE_old, T_old) = %+.4f  R² = %.4f" % (c, c * c))
    else:
        print("  npz 缓存未找到，跳过。")
except Exception as e:
    print("  T 重算失败:", type(e).__name__, e)
