"""批量启动 resnet1d transfer，用 os.system shell 重定向。"""
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
LOG = "logs/resnet1d_transfer.log"

with open(LOG, "w") as f:
    f.write("")

for src, tgt, sd, td in PAIRS:
    header = f"\n{'='*60}\nresnet1d transfer: {src} -> {tgt}\n{'='*60}\n"
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(header)
    cmd = (
        f'python scripts/eval_transfer.py '
        f'--source {src} --source-dir {sd} --target {tgt} --target-dir {td} '
        f'--arch resnet1d --seeds 42 43 --d-model 64 '
        f'--methods {METHODS} --bootstrap 200 --bci-method percentile --gpu-inference '
        f'>> {LOG} 2>&1'
    )
    ret = os.system(cmd)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"\n[ret={ret}] {src}->{tgt} 完成\n")

with open(LOG, "a", encoding="utf-8") as f:
    f.write("\nresnet1d 全量 transfer 实验完成。\n")
