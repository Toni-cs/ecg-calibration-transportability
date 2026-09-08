"""后台串行启动 seed 44/45/46 的 4 个剩余迁移方向实验。

补齐 P0 缺口：当前多seed验证只覆盖 chapman→cpsc 和 ptbxl→cpsc，
需补齐其余 4 个方向以达到 2 区要求的 6 方向覆盖。

4 个方向：
- chapman→ptbxl
- cpsc→chapman
- cpsc→ptbxl
- ptbxl→chapman

与 seed 42-46 已有实验保持一致：
- arch=inceptiontime
- methods: ts platt isotonic vector matrix dirichlet em_prior bbse_prior
- epochs=50, gpu-inference
- B=10000, bci-method=percentile（与任务26一致）

注意：eval_transfer.py 会自动训练 source 模型（如不存在），约 9-40 分钟/seed/对。
bootstrap B=10000 percentile 慢，预计每对每 seed 约 5-15 分钟。
总计 4 对 × 3 seed × (训练+评估) ≈ 4-8 小时。
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
        name = f"{src}_{tgt}_seed{seed}"
        jobs.append((
            common + ["--source", src, "--source-dir", DIRS[src],
                      "--target", tgt, "--target-dir", DIRS[tgt],
                      "--seeds", str(seed)],
            name,
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

print("All remaining 4 directions seed 44/45/46 transfer experiments done.")