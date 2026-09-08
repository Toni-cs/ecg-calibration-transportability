"""后台串行启动 seed 44/45/46 的 CPSC base 训练（inceptiontime）。

与 seed 42/43 保持一致：
- arch=inceptiontime, d_model=64, n_layers=2, num_classes=4
- epochs=50, batch_size=16, lr=1e-3
- 早停 patience=10

预计每 seed 约 30-50 分钟（RTX 5060, 8GB），共约 1.5-2.5 小时。
"""
import subprocess, sys, time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
SEEDS = [44, 45, 46]

for seed in SEEDS:
    cmd = [
        sys.executable, "scripts/train.py",
        "--dataset", "cpsc",
        "--data_dir", "data/cpsc_processed",
        "--arch", "inceptiontime",
        "--num_classes", "4",
        "--epochs", "50",
        "--batch_size", "16",
        "--d_model", "64",
        "--seed", str(seed),
        "--save_dir", f"checkpoints/cpsc_base_seed{seed}",
    ]
    log = open(root / f"train_cpsc_seed{seed}.log", "w", encoding="utf-8")
    print(f"[seed {seed}] Starting CPSC base training...")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(root))
    proc.wait()
    log.close()
    print(f"[seed {seed}] Exited with code {proc.returncode}")
    if proc.returncode != 0:
        print(f"[seed {seed}] FAILED, skipping remaining seeds")
        break

print("All CPSC base training done.")