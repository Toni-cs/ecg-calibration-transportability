"""后台串行启动 ptbxl→cpsc 和 chapman→cpsc 转移实验。"""
import subprocess, sys, time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
common = [
    sys.executable, "scripts/eval_transfer.py",
    "--arch", "inceptiontime",
    "--methods", "ts", "platt", "isotonic", "vector", "matrix", "dirichlet",
    "em_prior", "bbse_prior",
    "--seeds", "42",
    "--epochs", "50",
    "--gpu-inference",
    "--bootstrap", "200",
    "--bci-method", "percentile",
    "--save-dir", "checkpoints/transfer",
]
jobs = [
    common + ["--source", "ptbxl", "--source-dir", "data/ptbxl_processed",
              "--target", "cpsc", "--target-dir", "data/cpsc_processed"],
    common + ["--source", "chapman", "--source-dir", "data/chapman_processed_v2",
              "--target", "cpsc", "--target-dir", "data/cpsc_processed"],
]
for i, cmd in enumerate(jobs):
    pair = f"{cmd[cmd.index('--source')+1]}_{cmd[cmd.index('--target')+1]}"
    log = open(root / f"transfer_{pair}.log", "w", encoding="utf-8")
    print(f"[{i+1}/2] Starting {pair}...")
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(root))
    proc.wait()
    log.close()
    print(f"[{i+1}/2] {pair} exited with code {proc.returncode}")
print("All transfer experiments done.")