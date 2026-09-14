"""自动监控 E4 进度并在完成后串联启动 E6 -> E1b -> E5。"""
import subprocess, sys, time, os
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
LOG_FILE = RESULTS / "auto_chain.log"

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")

def run_experiment(name, script, timeout_hours=48):
    log(f"=== 启动 {name}: {script} ===")
    cmd = [sys.executable, "-X", "utf8", str(ROOT / script)]
    log_file = RESULTS / f"{name.lower()}_chain.log"
    err_file = RESULTS / f"{name.lower()}_chain_err.log"
    with open(log_file, "w", encoding="utf-8") as lf, open(err_file, "w", encoding="utf-8") as ef:
        proc = subprocess.Popen(cmd, stdout=lf, stderr=ef, cwd=str(ROOT))
        log(f"PID={proc.pid}")
        elapsed = 0
        while True:
            ret = proc.poll()
            if ret is not None: break
            time.sleep(60)
            elapsed += 60
            if elapsed % 3600 == 0:
                log(f"{name} 运行中... {elapsed // 3600}h elapsed")
        if ret == 0: log(f"OK {name} 完成")
        else: log(f"FAIL {name} 失败 (rc={ret})")
    return ret == 0

def is_e4_running():
    try:
        result = subprocess.run(["wmic", "process", "where", "name='python.exe'", "get", "commandline"],
                                capture_output=True, text=True, timeout=10)
        return "run_e4_temperature" in result.stdout
    except: return False

def main():
    log("=" * 60)
    log("自动串联: E4(运行中) -> E6 -> E1b -> E5")
    log("=" * 60)
    log("Step 1: 等待 E4 完成...")
    wait_min = 0
    while is_e4_running():
        time.sleep(120)
        wait_min += 2
        if wait_min % 30 == 0:
            log(f"E4 仍在运行... 已等待 {wait_min} 分钟")
    log(f"E4 进程已结束 (等待了 {wait_min} 分钟)")
    
    log("Step 2: 启动 E6")
    e6_ok = run_experiment("E6", "scripts/run_e6_reliability_diagrams.py", 3)
    
    log("Step 3: 启动 E1b")
    e1b_ok = run_experiment("E1b", "scripts/run_e1b_loco_validation.py", 6)
    
    log("Step 4: 启动 E5")
    e5_ok = run_experiment("E5", "scripts/run_e5_inception_lite.py", 48)
    
    log("=" * 60)
    log(f"全部完成! E6={'OK' if e6_ok else 'FAIL'} E1b={'OK' if e1b_ok else 'FAIL'} E5={'OK' if e5_ok else 'FAIL'}")
    log("=" * 60)

if __name__ == "__main__":
    main()
