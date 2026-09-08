"""批量启动 resnet1d L2 移位阶梯 eval-only 实验（6对×2seed=12 runs）。

需 resnet1d transfer checkpoint 已训练完成。结果写入各 run_dir/l2_shift_results.json。
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
os.chdir(ROOT)
os.environ.pop("PYTHONUTF8", None)
os.environ["PYTHONUNBUFFERED"] = "1"

PAIRS = [
    ("ptbxl", "chapman", "data/ptbxl_processed", "data/chapman_processed_v2"),
    ("ptbxl", "cpsc", "data/ptbxl_processed", "data/cpsc_processed"),
    ("chapman", "ptbxl", "data/chapman_processed_v2", "data/ptbxl_processed"),
    ("chapman", "cpsc", "data/chapman_processed_v2", "data/cpsc_processed"),
    ("cpsc", "ptbxl", "data/cpsc_processed", "data/ptbxl_processed"),
    ("cpsc", "chapman", "data/cpsc_processed", "data/chapman_processed_v2"),
]
LOG = "logs/l2_shifts_resnet1d.log"

open(LOG, "w").close()

for src, tgt, sd, td in PAIRS:
    pair_key = f"{src}_{tgt}"
    skip = True
    for seed in [42, 43]:
        p = ROOT / f"checkpoints/transfer/{pair_key}/resnet1d/seed{seed}/l2_shift_results.json"
        if not p.exists():
            skip = False
            break
    if skip:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[skip] {src}->{tgt} 已完成\n")
        continue
    header = f"\n{'='*60}\nresnet1d L2 shift: {src} -> {tgt}\n{'='*60}\n"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(header)
    cmd = (
        f'python scripts/eval_l2_shift.py '
        f'--source {src} --source-dir {sd} --target {tgt} --target-dir {td} '
        f'--arch resnet1d --seeds 42 43 '
        f'>> {LOG} 2>&1'
    )
    ret = os.system(cmd)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"\n[ret={ret}] {src}->{tgt} 完成\n")

with open(LOG, "a", encoding="utf-8") as f:
    f.write("\nresnet1d L2 全量实验完成。\n")