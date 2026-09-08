"""重跑 inceptiontime 6对×2seed transfer（--load-model eval-only）。

修复 eval_transfer.py:235 度量 bug（_bin 用校准后 argmax）后重跑所有方法。
checkpoint 已存在，仅重新评估 + bootstrap。
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
METHODS = "ts platt isotonic vector matrix dirichlet em_prior bbse_prior"
LOG = "logs/rerun_inceptiontime_transfer.log"

open(LOG, "w").close()

for src, tgt, sd, td in PAIRS:
    header = f"\n{'='*60}\nrerun inceptiontime: {src} -> {tgt}\n{'='*60}\n"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(header)
    cmd = (
        f'python scripts/eval_transfer.py '
        f'--source {src} --source-dir {sd} --target {tgt} --target-dir {td} '
        f'--arch inceptiontime --seeds 42 43 --load-model '
        f'--methods {METHODS} --bootstrap 200 --bci-method percentile --gpu-inference '
        f'>> {LOG} 2>&1'
    )
    ret = os.system(cmd)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"\n[ret={ret}] {src}->{tgt} 完成\n")

with open(LOG, "a", encoding="utf-8") as f:
    f.write("\ninceptiontime transfer 重跑完成。\n")