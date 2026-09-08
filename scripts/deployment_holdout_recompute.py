# -*- coding: utf-8 -*-
"""Leave-shift-type-out Youden recomputation for the deployment criterion.

论文 main.tex 部署节 caveat 的持久化产物：
- 阈值搜索 = 排除留出档的全格池（percentile 网格 0..100 step 0.5）
- 评估 = 仅该留出档（fs125 / leads2 / noise0 / gain2.0）
- 冻结阈值 0.126725 在四个留出档上的 sens/spec/J

输出 results/deployment_holdout_recompute.csv；与正文四值同口径。
只读计算，不修改任何实验产物。
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = __import__('pathlib').Path(__file__).resolve().parent.parent
PAIRS = ["ptbxl_cpsc", "ptbxl_chapman", "chapman_ptbxl", "chapman_cpsc",
         "cpsc_ptbxl", "cpsc_chapman"]
SEEDS = [42, 43, 44, 45, 46]
ARCH = "inceptiontime"
SHIFTS = ["fs250", "fs125", "leads6", "leads3", "leads2", "leads1",
          "noise24", "noise12", "noise6", "noise0", "noise-6",
          "gain0.5", "gain2.0"]
HOLDOUT = {"downsample": "fs125", "lead_drop": "leads2",
           "noise": "noise0", "gain": "gain2.0"}
SAFE = -0.01   # deployment-metrics convention: delta_ece < -0.01 = improvement
FROZEN_T = 0.126725


def main():
    # Use the exact cell set of the in-sample Table (step3_deployment.load_l2_data)
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from step3_deployment import load_l2_data
    data = load_l2_data()
    rows = [(pair, seed, shift, v["raw_ece"], v["delta_ece"])
            for (pair, seed, shift, m), v in data.items()]
    raw = np.array([r[3] for r in rows])
    ben = np.array([r[4] < SAFE for r in rows])
    lvl = np.array([r[2] for r in rows])
    print(f"cells: {len(rows)}")

    def youden(t, idx):
        pred = raw[idx] > t
        b = ben[idx]
        tp = int((pred & b).sum()); fn = int((~pred & b).sum())
        tn = int((~pred & ~b).sum()); fp = int((pred & ~b).sum())
        sens = tp / (tp + fn) if (tp + fn) else 0.0
        spec = tn / (tn + fp) if (tn + fp) else 0.0
        return sens, spec, sens + spec - 1.0, tp, fp, tn, fn

    grid = np.percentile(raw, np.arange(0, 100.01, 0.5))
    out = []
    allidx = np.arange(len(raw))
    js = [youden(t, allidx)[2] for t in grid]
    bt_in = float(grid[int(np.argmax(js))])
    s_in, sp_in, J_in, tp_in, fp_in, tn_in, fn_in = youden(bt_in, allidx)
    out.append(("in_sample_all_cells", "*", bt_in, s_in, sp_in, J_in, tp_in, fp_in, tn_in, fn_in))
    for st, hs in {"downsample": "fs125", "lead_drop": "leads2",
                   "noise": "noise0", "gain": "gain2.0"}.items():
        tr = np.where(lvl != hs)[0]
        te = np.where(lvl == hs)[0]
        g = np.percentile(raw[tr], np.arange(0, 100.01, 0.5))
        js_t = [youden(t, tr)[2] for t in g]
        bt = float(g[int(np.argmax(js_t))])
        s, sp, J, tp, fp, tn, fn = youden(bt, te)
        out.append((st, hs, bt, s, sp, J, tp, fp, tn, fn))
    fh = np.where(np.isin(lvl, ["fs125", "leads2", "noise0", "gain2.0"]))[0]
    s, sp, J, tp, fp, tn, fn = youden(FROZEN_T, fh)
    out.append(("frozen_threshold", "4 holdout levels", FROZEN_T, s, sp, J, tp, fp, tn, fn))

    df = pd.DataFrame({
        "scheme": [o[0] for o in out],
        "holdout_level": [o[1] for o in out],
        "best_threshold": [o[2] for o in out],
        "sensitivity": [o[3] for o in out],
        "specificity": [o[4] for o in out],
        "youden_J": [o[5] for o in out],
        "note": ["paper caveat numbers" for _ in out],
    })
    dest = ROOT / "results" / "deployment_holdout_recompute.csv"
    df.to_csv(dest, index=False, encoding="utf-8")
    print(df.round(4).to_string(index=False))
    print(f"saved -> {dest}")


if __name__ == "__main__":
    main()
