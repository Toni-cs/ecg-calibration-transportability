"""后台串行启动 seed 44/45/46 的 resnet1d 架构 4 个剩余迁移方向实验。

补齐 P2.1 缺口：当前 resnet1d 架构在 4 个迁移方向上只有 seed 42,43，
需补齐 4 个方向 × 3 seed = 12 个实验，以达到 ResNet1D 多 seed 覆盖。

4 个方向：
- chapman→ptbxl
- cpsc→chapman
- cpsc→ptbxl
- ptbxl→chapman

与 inceptiontime 多 seed 验证保持一致：
- arch=resnet1d
- methods: ts platt isotonic vector matrix dirichlet em_prior bbse_prior
- epochs=50, gpu-inference
- B=10000, bci-method=percentile（与现有实验一致）

预计每对每 seed 约 15-30 分钟（resnet1d 训练比 inceptiontime 快）。
总计 4 对 × 3 seed × (训练+评估) ≈ 3-6 小时。

输出路径：checkpoints/transfer/<source>_<target>/resnet1d/seed<seed>/transfer_result.json
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

# 4 个剩余迁移方向
DIRS = {
    "chapman": "data/chapman_processed_v2",
    "cpsc": "data/cpsc_processed",
    "ptbxl": "data/ptbxl_processed",
}

jobs = []
for seed in SEEDS:
    for src, tgt in [
        ("chapman", "ptbxl"),
        ("cpsc", "chapman"),
        ("cpsc", "ptbxl"),
        ("ptbxl", "chapman"),
    ]:
        name = f"{src}_{tgt}_resnet1d_seed{seed}"
        jobs.append((
            common + ["--source", src, "--source-dir", DIRS[src],
                      "--target", tgt, "--target-dir", DIRS[tgt],
                      "--seeds", str(seed)],
            name,
        ))

print(f"Total {len(jobs)} resnet1d remaining-4 seed 44/45/46 transfer experiments.")
for i, (cmd, name) in enumerate(jobs):
    log = open(root / f"transfer_{name}.log", "w", encoding="utf-8")
    print(f"[{i+1}/{len(jobs)}] Starting {name}...", flush=True)
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(root))
    proc.wait()
    log.close()
    print(f"[{i+1}/{len(jobs)}] {name} exited with code {proc.returncode}", flush=True)
    if proc.returncode != 0:
        print(f"[{i+1}/{len(jobs)}] FAILED, continuing to next job", flush=True)

print("All resnet1d remaining 4 directions seed 44/45/46 transfer experiments done.")