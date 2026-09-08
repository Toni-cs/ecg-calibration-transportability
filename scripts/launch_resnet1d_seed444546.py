"""后台串行启动 seed 44/45/46 的 resnet1d 架构迁移实验（2个主方向）。

补齐 P1 缺口：当前 resnet1d 架构在所有迁移对上只有 seed 42,43，
需补齐 2 个主方向（chapman→cpsc, ptbxl→cpsc）的 seed 44/45/46，
以达到 2 区要求的架构稳健性。

与 inceptiontime 多seed验证保持一致：
- arch=resnet1d
- methods: ts platt isotonic vector matrix dirichlet em_prior bbse_prior
- epochs=50, gpu-inference
- B=10000, bci-method=percentile

预计每对每 seed 约 30-60 分钟（resnet1d 训练比 inceptiontime 快）。
总计 2 对 × 3 seed × (训练+评估) ≈ 3-6 小时。
"""
import subprocess, sys
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

# 2 个主方向
jobs = []
for seed in SEEDS:
    jobs.append((
        common + ["--source", "chapman", "--source-dir", "data/chapman_processed_v2",
                  "--target", "cpsc", "--target-dir", "data/cpsc_processed",
                  "--seeds", str(seed)],
        f"chapman_cpsc_resnet1d_seed{seed}",
    ))
    jobs.append((
        common + ["--source", "ptbxl", "--source-dir", "data/ptbxl_processed",
                  "--target", "cpsc", "--target-dir", "data/cpsc_processed",
                  "--seeds", str(seed)],
        f"ptbxl_cpsc_resnet1d_seed{seed}",
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

print("All resnet1d seed 44/45/46 transfer experiments done.")