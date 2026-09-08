"""重跑 L2 噪声 5 档（修复 shift_noise mixed bug 后）。

只跑 noise24/noise12/noise6/noise0/noise-6，合并到已有 l2_shift_results.json。
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
NOISE_SHIFTS = "noise24 noise12 noise6 noise0 noise-6"
LOG = "logs/l2_noise_rerun.log"

import json

open(LOG, "w").close()

NOISE_NAMES = ["noise24", "noise12", "noise6", "noise0", "noise-6"]

for arch in ["inceptiontime", "resnet1d"]:
    for src, tgt, sd, td in PAIRS:
        pair_key = f"{src}_{tgt}"
        skip = True
        for seed in [42, 43]:
            p = ROOT / f"checkpoints/transfer/{pair_key}/{arch}/seed{seed}/l2_shift_results.json"
            if not p.exists():
                skip = False
                break
            try:
                d = json.loads(p.read_text(encoding="utf-8"))[f"seed{seed}"]
                raws = []
                for ns in NOISE_NAMES:
                    if ns not in d or "ts" not in d[ns]:
                        skip = False
                        break
                    raws.append(d[ns]["raw_ece"])
                if not skip:
                    break
                if len(set(round(r, 6) for r in raws)) < 3:
                    skip = False
                    break
            except Exception:
                skip = False
                break
        if skip:
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(f"\n[skip] {arch} {src}->{tgt} 噪声档已完成\n")
            continue
        header = f"\n{'='*60}\n{arch} noise rerun: {src} -> {tgt}\n{'='*60}\n"
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(header)
        cmd = (
            f'python scripts/eval_l2_shift.py '
            f'--source {src} --source-dir {sd} --target {tgt} --target-dir {td} '
            f'--arch {arch} --seeds 42 43 --shifts {NOISE_SHIFTS} '
            f'>> {LOG} 2>&1'
        )
        ret = os.system(cmd)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"\n[ret={ret}] {arch} {src}->{tgt} 完成\n")

with open(LOG, "a", encoding="utf-8") as f:
    f.write("\n噪声 5 档重跑完成。\n")