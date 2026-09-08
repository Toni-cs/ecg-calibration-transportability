"""监控4方向迁移实验进度，循环检查直到所有12个实验完成或超时。"""
import json, time, sys
from pathlib import Path

root = Path(r"D:\A1\ecg-lab-v2")
targets = [
    ("chapman_ptbxl", 44), ("chapman_ptbxl", 45), ("chapman_ptbxl", 46),
    ("cpsc_chapman", 44), ("cpsc_chapman", 45), ("cpsc_chapman", 46),
    ("cpsc_ptbxl", 44), ("cpsc_ptbxl", 45), ("cpsc_ptbxl", 46),
    ("ptbxl_chapman", 44), ("ptbxl_chapman", 45), ("ptbxl_chapman", 46),
]

def done_count():
    n = 0
    for src_tgt, seed in targets:
        p = root / "checkpoints/transfer" / src_tgt / "inceptiontime" / f"seed{seed}" / "transfer_result.json"
        if p.exists():
            n += 1
    return n

def current_log():
    """找最新的正在运行的实验日志。"""
    logs = sorted(root.glob("transfer_*_seed4*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    logs += sorted(root.glob("transfer_*_seed5*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
    # 去重并按mtime排序
    seen = set()
    all_logs = []
    for p in list(root.glob("transfer_*_seed4*.log")) + list(root.glob("transfer_*_seed5*.log")):
        if p.name not in seen:
            seen.add(p.name)
            all_logs.append(p)
    all_logs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return all_logs[0] if all_logs else None

# 监控循环：最多运行19分钟（1140秒），每90秒检查一次
start = time.time()
max_run = 1140
interval = 90

while time.time() - start < max_run:
    done = done_count()
    elapsed = int(time.time() - start)
    log = current_log()
    tail = ""
    methods_done = 0
    if log and log.exists():
        try:
            lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = "\n".join(lines[-3:]) if lines else ""
            methods_done = sum(1 for l in lines if "decay=" in l and "sd=" in l)
        except Exception:
            pass
    print(f"[{elapsed:4d}s] 已完成 {done}/12 | 当前: {log.name if log else 'N/A'} | 方法: {methods_done}/8", flush=True)
    if tail:
        for l in tail.splitlines():
            print(f"    {l}", flush=True)
    if done >= 12:
        print("所有12个实验完成！", flush=True)
        break
    time.sleep(interval)

print(f"监控结束。最终完成: {done_count()}/12", flush=True)