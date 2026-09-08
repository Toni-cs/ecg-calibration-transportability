"""批量启动 L2 移位阶梯 eval-only 实验（6对×2seed=12 runs, inceptiontime）。

串行执行，每 run 约 5-10 分钟。结果写入各 run_dir/l2_shift_results.json。
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
SEEDS = [42, 43]
LOG = "logs/l2_rerun_inceptiontime.log"

open(LOG, "w").close()

for src, tgt, src_dir, tgt_dir in PAIRS:
    header = f"\n{'='*60}\nL2 shift: {src} -> {tgt} (seeds {SEEDS})\n{'='*60}\n"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(header)
    seeds_arg = " ".join(str(s) for s in SEEDS)
    cmd = (
        f'python scripts/eval_l2_shift.py '
        f'--source {src} --source-dir {src_dir} '
        f'--target {tgt} --target-dir {tgt_dir} '
        f'--arch inceptiontime --seeds {seeds_arg} '
        f'>> {LOG} 2>&1'
    )
    ret = os.system(cmd)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"\n[ret={ret}] {src}->{tgt} 完成\n")

with open(LOG, "a", encoding="utf-8") as f:
    f.write("\n全量 L2 移位阶梯实验完成。\n")
