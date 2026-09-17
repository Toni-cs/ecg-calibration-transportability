"""汇总 L2 移位阶梯实验结果（6对×2seed×8档×8方法）。

输出：
1. 跨 shift 汇总表（每对每方法 seed 均值±std）
2. TS 稳健性验证（全档负收益计数）
3. 退化趋势验证（降采样/导联单调性）

⚠️ 编码护栏（2026-09-17 对抗审查发现 F5）
----------------------------------------
本脚本原先**零编码校验**，会把 09-10~09-12 产出的 60 份**污染** `l2_shift_results.json`
直接聚合成"结果表"，与 `run_e1a_l2_shift_full.py` 自己的"不完整 → 重跑"判定
（`is_checkpoint_complete` 判据 0）直接矛盾：上游说"这些文件不能用"，下游照单全收。

现在 `load_all()` 强制要求每份 JSON 顶层 `label_encoding` 与期望编码**逐字符相等**：
  * 缺失 → 拒绝加载（这些正是 09-10~09-12 那一批）；
  * 不符 → 拒绝加载。
默认严格模式；确需人工核对时用 `--allow-unstamped`（会在 stdout 显式标注）。
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.data.mapping import SUBSPACE_CPSC, SUPERCLASSES          # noqa: E402
from src.utils.encoding_guard import encoding_stamp               # noqa: E402

DATASET_NUM_CLASSES = {"ptbxl": 5, "chapman": 5, "cpsc": 4}

PAIRS = [
    "ptbxl_chapman", "ptbxl_cpsc",
    "chapman_ptbxl", "chapman_cpsc",
    "cpsc_ptbxl", "cpsc_chapman",
]
SEEDS = [42, 43]
ARCH = "inceptiontime"
METHODS = ["ts", "platt", "isotonic", "vector", "matrix", "dirichlet", "em_prior", "bbse_prior"]
SHIFTS = ["fs250", "fs125", "leads6", "leads3", "leads2", "leads1", "gain0.5", "gain2.0"]


def expected_encoding_for(pair: str) -> str:
    """按 pair 推算该 run 应有的编码戳（与 run_e1a 的 expected_encoding_for 一致）。"""
    source, target = pair.split("_")
    nc = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
    return encoding_stamp(nc, SUBSPACE_CPSC if nc == 4 else None)


def load_all(strict: bool = True):
    """加载各 run 的 `l2_shift_results.json`，并校验编码戳。

    返回 `(data, rejected, unstamped)`：
      data       —— {(pair, seed): {shift: {...}}}，仅含通过校验的 run
      rejected   —— 因编码戳缺失/不符而被拒的 run 说明
      unstamped  —— strict=False 下被放行的无戳 run（需人工复核）
    """
    data, rejected, unstamped = {}, [], []
    for pair in PAIRS:
        want = expected_encoding_for(pair)
        for seed in SEEDS:
            p = (ROOT / "checkpoints/transfer" / pair / ARCH
                 / f"seed{seed}" / "l2_shift_results.json")
            if not p.exists():
                continue
            try:
                whole = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                rejected.append(f"{pair}/seed{seed}: JSON 解析失败 {e}")
                continue

            have = whole.get("label_encoding")
            if have is None:
                if strict:
                    rejected.append(
                        f"{pair}/seed{seed}: 无 `label_encoding` 戳"
                        f"（护栏上线前的产物，09-10~09-12 那批为污染值）")
                    continue
                unstamped.append(f"{pair}/seed{seed}")
            elif str(have) != want:
                rejected.append(
                    f"{pair}/seed{seed}: 编码戳不符 文件={have} 期望={want}")
                continue

            sk = f"seed{seed}"
            if sk in whole:
                data[(pair, seed)] = whole[sk]
    return data, rejected, unstamped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--allow-unstamped", action="store_true", default=False,
                    help="放行无编码戳的 JSON（需人工确认；会在输出中标注）")
    args = ap.parse_args()

    data, rejected, unstamped = load_all(strict=not args.allow_unstamped)

    if rejected:
        print("=" * 120)
        print(f"⛔ 因编码护栏被拒的 run：{len(rejected)} 个（这些是 09-10~09-12 的污染产物）")
        print("=" * 120)
        for r in rejected:
            print("   ", r)
        print("   → 需先按 results/_L2_SHIFT_CONTAMINATION_NOTICE.md 重跑 E1a，"
              "再运行本脚本。\n")
    if unstamped:
        print(f"⚠️ --allow-unstamped：放行了 {len(unstamped)} 个无戳 run，"
              f"其编码未经验证：{unstamped}\n")

    print(f"已加载 {len(data)} 个**通过编码校验**的 run\n")
    if not data:
        print("无可汇总的数据。中止（不输出任何表格，避免把污染值当结果）。")
        return 1

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
        if n == 0:
            print(f"{m:<12}{'--':>8}{'--':>8}{0:>8}{0:>8}{n_skip:>8}{0:>8}{'--':>10}")
            continue
        n_pos = sum(1 for d in deltas if d > 1e-6)
        n_neg = sum(1 for d in deltas if d < -1e-6)
        print(f"{m:<12}{np.mean(deltas):>8.4f}{np.std(deltas):>8.4f}{n_pos:>8}{n_neg:>8}{n_skip:>8}{n:>8}{n_pos/n*100:>9.1f}%")

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
            if not ts_deltas:
                continue
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

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
