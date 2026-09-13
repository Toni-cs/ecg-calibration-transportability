"""汇总 L2 移位阶梯实验结果（6对×2seed×8档×8方法）。

输出：
1. 跨 shift 汇总表（每对每方法 seed 均值±std）
2. TS 稳健性验证（全档负收益计数）
3. 退化趋势验证（降采样/导联单调性）
"""
from __future__ import annotations
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent

PAIRS = [
    "ptbxl_chapman", "ptbxl_cpsc",
    "chapman_ptbxl", "chapman_cpsc",
    "cpsc_ptbxl", "cpsc_chapman",
]
SEEDS = [42, 43]
ARCH = "inceptiontime"
METHODS = ["ts", "platt", "isotonic", "vector", "matrix", "dirichlet", "em_prior", "bbse_prior"]
SHIFTS = ["fs250", "fs125", "leads6", "leads3", "leads2", "leads1", "gain0.5", "gain2.0"]


def load_all():
    data = {}
    for pair in PAIRS:
        for seed in SEEDS:
            p = ROOT / "checkpoints/transfer" / pair / ARCH / f"seed{seed}" / "l2_shift_results.json"
            if p.exists():
                data[(pair, seed)] = json.loads(p.read_text(encoding="utf-8"))[f"seed{seed}"]
    return data


def main():
    data = load_all()
    print(f"已加载 {len(data)} 个 run\n")

    print("=" * 120)
    print("表1: 跨 shift raw ECE + TS ΔECE（seed 均值±std）")
    print("=" * 120)
    header = f"{'Pair':<16}" + "".join(f"{s:>14}" for s in SHIFTS)
    print(header)
    for pair in PAIRS:
        row = f"{pair:<16}"
        for shift in SHIFTS:
            vals = []
            for seed in SEEDS:
                if (pair, seed) in data and shift in data[(pair, seed)]:
                    vals.append(data[(pair, seed)][shift]["raw_ece"])
            if vals:
                row += f" {np.mean(vals):>6.4f}±{np.std(vals):>4.3f}"
            else:
                row += f"{'--':>14}"
        print(row)

    print("\n" + "=" * 120)
    print("表2: 各方法 ΔECE 汇总（跨6对×2seed×8档；正收益=恶化；剔除 skipped 与恒等假零）")
    print("=" * 120)
    header = f"{'Method':<12}{'mean':>8}{'std':>8}{'n_pos':>8}{'n_neg':>8}{'n_skip':>8}{'n_used':>8}{'pos_rate':>10}"
    print(header)
    for m in METHODS:
        deltas, n_skip = [], 0
        for pair in PAIRS:
            for seed in SEEDS:
                if (pair, seed) not in data:
                    continue
                for shift in SHIFTS:
                    if shift in data[(pair, seed)] and m in data[(pair, seed)][shift]:
                        d = data[(pair, seed)][shift][m]
                        if not isinstance(d, dict) or "delta_ece" not in d:
                            continue
                        if d.get("status") == "skipped":
                            n_skip += 1
                            continue
                        if d["cal_ece"] == data[(pair, seed)][shift]["raw_ece"]:
                            n_skip += 1
                            continue
                        deltas.append(d["delta_ece"])
        n = len(deltas)
        n_pos = sum(1 for d in deltas if d > 1e-6)
        n_neg = sum(1 for d in deltas if d < -1e-6)
        print(f"{m:<12}{np.mean(deltas):>8.4f}{np.std(deltas):>8.4f}{n_pos:>8}{n_neg:>8}{n_skip:>8}{n:>8}{n_pos/max(n,1)*100:>9.1f}%")

    print("\n" + "=" * 120)
    print("表3: TS 稳健性验证（每对 TS 负收益档数 / 总档数）")
    print("=" * 120)
    for pair in PAIRS:
        for seed in SEEDS:
            if (pair, seed) not in data:
                continue
            ts_deltas = []
            for shift in SHIFTS:
                if shift in data[(pair, seed)] and "ts" in data[(pair, seed)][shift]:
                    ts_deltas.append(data[(pair, seed)][shift]["ts"]["delta_ece"])
            n_neg = sum(1 for d in ts_deltas if d < -1e-6)
            print(f"  {pair:<16} seed{seed}: TS 负收益 {n_neg}/{len(ts_deltas)} 档 "
                  f"(mean={np.mean(ts_deltas):+.4f}, range=[{min(ts_deltas):+.4f}, {max(ts_deltas):+.4f}])")

    print("\n" + "=" * 120)
    print("表4: 退化趋势验证（降采样 fs250<fs125, 导联 leads6<leads3<leads2<leads1）")
    print("=" * 120)
    for pair in PAIRS:
        for seed in SEEDS:
            if (pair, seed) not in data:
                continue
            d = data[(pair, seed)]
            r = {}
            for s in SHIFTS:
                if s in d:
                    r[s] = d[s]["raw_ece"]
            if "fs250" in r and "fs125" in r:
                ds_ok = r["fs250"] < r["fs125"]
            else:
                ds_ok = None
            lead_chain = ["leads6", "leads3", "leads2", "leads1"]
            lead_vals = [r.get(s) for s in lead_chain]
            lead_ok = all(lead_vals[i] is not None and lead_vals[i+1] is not None and lead_vals[i] < lead_vals[i+1]
                          for i in range(len(lead_vals)-1)) if all(v is not None for v in lead_vals) else None
            ds_str = "✓" if ds_ok else "✗" if ds_ok is not None else "?"
            lead_str = "✓" if lead_ok else "✗" if lead_ok is not None else "?"
            print(f"  {pair:<16} seed{seed}: 降采样单调 {ds_str}  导联单调 {lead_str}")


if __name__ == "__main__":
    main()