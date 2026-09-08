"""后台串行启动 seed 44/45/46 的 2 对 CPSC 转移实验（Chapman→CPSC, PTB-XL→CPSC）。

与 seed 42/43 保持一致（launch_seed43_transfers.py）：
- arch=inceptiontime
- methods: ts platt isotonic vector matrix dirichlet em_prior bbse_prior
- epochs=50, gpu-inference
- B=10000, bci-method=bca（正式版，协议预注册）

注意：此脚本会训练 source 模型（chapman/ptbxl），约 9-22 分钟/seed/对。
bootstrap B=10000 BCa 慢，预计每对每 seed 约 5-15 分钟。
总计 2 对 × 3 seed × (训练+评估) ≈ 2-3 小时。
"""
import subprocess, sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
SEEDS = [44, 45, 46]

common = [
    sys.executable, "scripts/eval_transfer.py",
    "--arch", "inceptiontime",
    "--methods", "ts", "platt", "isotonic", "vector", "matrix", "dirichlet",
    "em_prior", "bbse_prior",
    "--epochs", "50",
    "--gpu-inference",
    "--bootstrap", "10000",
    "--bci-method", "bca",
    "--n-jobs", "8",
    "--save-dir", "checkpoints/transfer",
]

# 2 区升级主终点：Chapman→CPSC, PTB-XL→CPSC
jobs = []
for seed in SEEDS:
    jobs.append((
        common + ["--source", "chapman", "--source-dir", "data/chapman_processed_v2",
                  "--target", "cpsc", "--target-dir", "data/cpsc_processed",
                  "--seeds", str(seed)],
        f"chapman_cpsc_seed{seed}",
    ))
    jobs.append((
        common + ["--source", "ptbxl", "--source-dir", "data/ptbxl_processed",
                  "--target", "cpsc", "--target-dir", "data/cpsc_processed",
                  "--seeds", str(seed)],
        f"ptbxl_cpsc_seed{seed}",
    ))

for i, (cmd, name) in enumerate(jobs):
    log = open(root / f"transfer_{name}.log", "w", encoding="utf-8")
    print(f"[{i+1}/{len(jobs)}] Starting {name}...")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(root))
    proc.wait()
    log.close()
    print(f"[{i+1}/{len(jobs)}] {name} exited with code {proc.returncode}")
    if proc.returncode != 0:
        print(f"[{i+1}/{len(jobs)}] FAILED, continuing to next job")

print("All seed 44/45/46 transfer experiments done.")