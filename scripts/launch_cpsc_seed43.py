"""后台启动 seed43 CPSC 训练。"""
import subprocess, sys, time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
cmd = [
    sys.executable, "scripts/train.py",
    "--dataset", "cpsc",
    "--data_dir", "data/cpsc_processed",
    "--arch", "inceptiontime",
    "--num_classes", "4",
    "--epochs", "50",
    "--batch_size", "16",
    "--d_model", "64",
    "--seed", "43",
    "--save_dir", "checkpoints/cpsc_base_seed43",
]
log = open(root / "train_cpsc_seed43.log", "w", encoding="utf-8")
proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(root))
print(f"CPSC seed43 training started: PID={proc.pid}")
time.sleep(5)
if proc.poll() is None:
    print("Process running OK")
else:
    print(f"Process exited early with code {proc.returncode}")