#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""给 strengthening_battle_corrected.json 增量补出 T_old 字段（第三轮对抗审查 R3-E）。

背景
----
该 JSON 的 62 条记录里：
  * `T`             ≡ 新编码（NEW）拟合温度，max|Δ| vs T_new = 4.8e-07
  * `raw_ood_orig` / `cal_ood_orig` / `delta_obs_orig`  用**旧编码**温度
⇒ 按 `T` 复算主终点会得到 3–6 倍偏差（cell 1 得 +0.0829 而非 +0.0139）。
  `(T, raw_ood_orig, cal_ood_orig)` **不可联合复现**。

修法
----
**不修改** `T`（避免破坏既有消费者），**增量**添加：
  * `T_old`        —— 旧编码温度（取自 ablation_ts_components.OLD_ENCODING.csv
                      stage1_ts 的 T_global，与主终点同口径）
  * `T_encoding`   —— 字符串，标明 `T` 字段的真实编码（"NEW"）

用法:
    python scripts/add_t_old_to_strengthening.py
"""
from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "results" / "strengthening_battle_corrected.json"
ABL_OLD = ROOT / "results" / "ablation_ts_components.OLD_ENCODING.csv"


def load_T_old():
    out = {}
    with ABL_OLD.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r.get("stage") != "stage1_ts":
                continue
            out[(r["source"], r["target"], r["arch"], int(r["seed"]))] = float(r["T_global"])
    return out


def main() -> int:
    recs = json.loads(TARGET.read_text(encoding="utf-8"))
    t_old = load_T_old()
    shutil.copy2(TARGET, TARGET.with_suffix(".json.bak_before_T_old"))
    n_added = n_missing = 0
    for r in recs:
        key = (r["source"], r["target"], r["arch"], r["seed"])
        if key in t_old:
            r["T_old"] = t_old[key]
            n_added += 1
        else:
            n_missing += 1
        r["T_encoding"] = "NEW"          # `T` 字段的真实身份
    TARGET.write_text(json.dumps(recs, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{TARGET.name}: {len(recs)} 条；补 T_old {n_added} 条，缺 {n_missing} 条")
    print("已备份 ->", TARGET.with_suffix(".json.bak_before_T_old").name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
