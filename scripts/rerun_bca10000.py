"""BCa B=10,000 全网格重跑（ts 主终点）：6 对 × 2 架构 × 5 种子 = 60 runs。

协议预注册 B=10,000 + BCa（含 jackknife 加速度项）；历史 60 实验中
31 个 percentile/B=10000、21 个 percentile/B=200、3 个 BCa（仅 ts 混合溯源）。
本脚本把 ts 方法全部升级为正式版 BCa，并依赖 eval_transfer.py 写入的
methods.ts.meta.n_bootstrap/bci_method 做可续跑 skip 判据。

- 每格独立调用（崩一格不影响其余），[ret=] 逐格落盘。
- 已完成格（meta.n_bootstrap>=10000 且 bci_method=bca）自动跳过。
- 只重写 ts 键（--methods ts），其余 7 方法历史 percentile 结果保留；
  全方法 BCa 版可在全网格 ts 完成后把 METHODS 改为全部方法列表。

需 GPU 空闲。预计每格 5-15 分钟（B=10000+jackknife），共 6-12 小时。
用法：python scripts/rerun_bca10000.py [--archs inceptiontime resnet1d] [--dry-run]
"""
import os
import sys
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
os.environ.pop("PYTHONUTF8", None)
os.environ["PYTHONUNBUFFERED"] = "1"

PAIRS = [
    ("chapman", "cpsc", "data/chapman_processed_v2", "data/cpsc_processed"),
    ("chapman", "ptbxl", "data/chapman_processed_v2", "data/ptbxl_processed"),
    ("cpsc", "chapman", "data/cpsc_processed", "data/chapman_processed_v2"),
    ("cpsc", "ptbxl", "data/cpsc_processed", "data/ptbxl_processed"),
    ("ptbxl", "chapman", "data/ptbxl_processed", "data/chapman_processed_v2"),
    ("ptbxl", "cpsc", "data/ptbxl_processed", "data/cpsc_processed"),
]
ARCHS = ["inceptiontime", "resnet1d"]
SEEDS = [42, 43, 44, 45, 46]
METHODS = "ts"
LOG = "logs/bca10000_full.log"


def done(rj: Path) -> bool:
    if not rj.exists():
        return False
    try:
        d = json.loads(rj.read_text(encoding="utf-8"))
        ts = d.get("methods", {}).get("ts", {})
        meta = ts.get("meta", {})
        return int(meta.get("n_bootstrap", 0)) >= 10000 and meta.get("bci_method") == "bca"
    except Exception:
        return False


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--archs", nargs="+", default=ARCHS)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    open(LOG, "w").close()
    todo, skip_n = [], 0
    for src, tgt, sd, td in PAIRS:
        pair_key = f"{src}_{tgt}"
        for arch in args.archs:
            for seed in SEEDS:
                rj = ROOT / f"checkpoints/transfer/{pair_key}/{arch}/seed{seed}/transfer_result.json"
                if done(rj):
                    skip_n += 1
                    continue
                todo.append((src, tgt, sd, td, pair_key, arch, seed, rj))
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"[plan] {len(todo)} runs to do, {skip_n} already BCa-complete\n")
    print(f"[plan] {len(todo)} runs to do, {skip_n} already BCa-complete")

    if args.dry_run:
        for t in todo:
            print("  would run:", t[4], t[5], "seed", t[6])
        return

    rets = []
    for src, tgt, sd, td, pair_key, arch, seed, _rj in todo:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\nBCa B=10000: {src} -> {tgt} [{arch}] seed{seed}\n{'='*60}\n")
        cmd = (
            f'python scripts/eval_transfer.py '
            f'--source {src} --source-dir {sd} --target {tgt} --target-dir {td} '
            f'--arch {arch} --seeds {seed} --load-model '
            f'--methods {METHODS} --bootstrap 10000 --bci-method bca '
            f'--gpu-inference --n-jobs 8 '
            f'>> {LOG} 2>&1'
        )
        ret = os.system(cmd)
        rets.append((pair_key, arch, seed, ret))
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[ret={ret}] {src}->{tgt} {arch} seed{seed} 完成\n")

    n_fail = sum(1 for r in rets if r[3] != 0)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"\nBCa B=10000 全网格完成：{len(rets)} runs，失败 {n_fail}。\n")
    print(f"[done] {len(rets)} runs, {n_fail} failed")


if __name__ == "__main__":
    main()
