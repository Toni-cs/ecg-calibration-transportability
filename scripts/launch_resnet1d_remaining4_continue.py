"""继续运行缺失的 resnet1d 4方向 seed 44/45/46 实验。

跳过已存在 transfer_result.json 的实验，只运行缺失的。
"""
import subprocess, sys, json
from pathlib import Path

root = Path(__file__).resolve().parents[1]
SEEDS = [44, 45, 46]

common = [
    sys.executable, "scripts/eval_transfer.py",
    "--arch", "resnet1d",
    "--methods", "ts", "platt", "isotonic", "vector", "matrix", "dirichlet",
    "em_prior", "bbse_prior",
    "--epochs", "50",
    "--gpu-inference",
    "--bootstrap", "10000",
    "--bci-method", "percentile",
    "--n-jobs", "8",
    "--save-dir", "checkpoints/transfer",
]

DIRS = {
    "chapman": "data/chapman_processed_v2",
    "cpsc": "data/cpsc_processed",
    "ptbxl": "data/ptbxl_processed",
}

# 构建所有12个实验
all_jobs = []
for seed in SEEDS:
    for src, tgt in [
        ("chapman", "ptbxl"),
        ("cpsc", "chapman"),
        ("cpsc", "ptbxl"),
        ("ptbxl", "chapman"),
    ]:
        name = f"{src}_{tgt}_resnet1d_seed{seed}"
        result_path = root / "checkpoints" / "transfer" / f"{src}_{tgt}" / "resnet1d" / f"seed{seed}" / "transfer_result.json"
        all_jobs.append((
            common + ["--source", src, "--source-dir", DIRS[src],
                      "--target", tgt, "--target-dir", DIRS[tgt],
                      "--seeds", str(seed)],
            name,
            result_path,
        ))

# 过滤出缺失的实验
jobs = []
for cmd, name, result_path in all_jobs:
    if result_path.exists():
        try:
            with open(result_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if "methods" in data and "ts" in data["methods"]:
                print(f"[SKIP] {name} already done", flush=True)
                continue
        except Exception:
            pass
    jobs.append((cmd, name))

print(f"Remaining {len(jobs)} experiments to run.", flush=True)
for i, (cmd, name) in enumerate(jobs):
    log = open(root / f"transfer_{name}.log", "w", encoding="utf-8")
    print(f"[{i+1}/{len(jobs)}] Starting {name}...", flush=True)
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(root))
    proc.wait()
    log.close()
    print(f"[{i+1}/{len(jobs)}] {name} exited with code {proc.returncode}", flush=True)
    if proc.returncode != 0:
        print(f"[{i+1}/{len(jobs)}] FAILED, continuing to next job", flush=True)

print("All remaining resnet1d experiments done.", flush=True)