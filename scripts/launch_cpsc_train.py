"""后台启动 CPSC 正式训练（subprocess.Popen，非阻塞）。"""
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
    "--seed", "42",
    "--save_dir", "checkpoints/cpsc_base",
]
log = open(root / "train_cpsc_seed42.log", "w", encoding="utf-8")
proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(root))
print(f"CPSC training started: PID={proc.pid}, log=train_cpsc_seed42.log")
time.sleep(5)
if proc.poll() is None:
    print("Process running OK")
else:
    print(f"Process exited early with code {proc.returncode}")