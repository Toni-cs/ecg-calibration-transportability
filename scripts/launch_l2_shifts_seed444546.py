"""后台串行启动 seed 44/45/46 的 L2 移分实验（仅针对已有 checkpoint 的 2 对：chapman_cpsc, ptbxl_cpsc）。

需要 best_model.pt 已存在。结果写入各 run_dir/l2_shift_results.json。
每 run 约 5-10 分钟，总计 2 对 × 3 seed = 6 runs ≈ 30-60 分钟。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
os.environ.pop("PYTHONUTF8", None)
os.environ["PYTHONUNBUFFERED"] = "1"

# 只有这 2 对在 seed 44/45/46 上有 best_model.pt
PAIRS = [
    ("ptbxl", "cpsc", "data/ptbxl_processed", "data/cpsc_processed"),
    ("chapman", "cpsc", "data/chapman_processed_v2", "data/cpsc_processed"),
]
SEEDS = [44, 45, 46]
LOG = "logs/l2_shifts_seed444546.log"

open(LOG, "w").close()

for src, tgt, src_dir, tgt_dir in PAIRS:
    for seed in SEEDS:
        pair_key = f"{src}_{tgt}"
        ckpt = ROOT / f"checkpoints/transfer/{pair_key}/inceptiontime/seed{seed}/best_model.pt"
        if not ckpt.exists():
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(f"\n[skip] {ckpt} not found\n")
            continue
        header = f"\n{'='*60}\nL2 shift: {src} -> {tgt} seed{seed}\n{'='*60}\n"
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(header)
        cmd = (
            f'python scripts/eval_l2_shift.py '
            f'--source {src} --source-dir {src_dir} '
            f'--target {tgt} --target-dir {tgt_dir} '
            f'--arch inceptiontime --seeds {seed} '
            f'>> {LOG} 2>&1'
        )
        ret = os.system(cmd)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[ret={ret}] {src}->{tgt} seed{seed} 完成\n")

with open(LOG, "a", encoding="utf-8") as f:
    f.write("\nseed 44/45/46 L2 移位阶梯实验完成。\n")