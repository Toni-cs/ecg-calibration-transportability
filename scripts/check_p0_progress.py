"""P0 迁移校准实验进度检查脚本

检查 12 个目标实验 (4 方向 × 3 seed) 的完成状态，读取 ts 方法的 OOD ΔECE 和 CI，
输出进度汇总，并检查 python 实验进程是否仍在运行。

用法：
    python scripts/check_p0_progress.py            # 默认输出到 stdout
    python scripts/check_p0_progress.py --json      # 输出 JSON（便于程序解析）

设计原则：
- 立即返回结果，不做任何等待/轮询（等待由外部调度器负责）
- 单次运行 O(12) 文件检查 + O(done) JSON 读取，毫秒级完成
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# 4 个迁移方向 × 3 个 seed = 12 个目标实验
DIRECTIONS = ["chapman_ptbxl", "cpsc_chapman", "cpsc_ptbxl", "ptbxl_chapman"]
SEEDS = [44, 45, 46]
ARCH = "inceptiontime"

# eval_transfer.py 中校准方法的执行顺序（用于从日志推断当前进度）
METHOD_ORDER = ["ts", "platt", "isotonic", "vector", "matrix",
                "dirichlet", "em_prior", "bbse_prior"]


# ---------------------------------------------------------------------------
# 核心函数
# ---------------------------------------------------------------------------
def result_path(direction: str, seed: int) -> Path:
    """返回某个实验的 transfer_result.json 路径。"""
    return (PROJECT_ROOT / "checkpoints" / "transfer" / direction /
            ARCH / f"seed{seed}" / "transfer_result.json")


def log_path(direction: str, seed: int) -> Path:
    """返回某个实验的日志文件路径（launch_remaining4 命名约定）。"""
    return PROJECT_ROOT / f"transfer_{direction}_seed{seed}.log"


def read_ts_result(path: Path) -> dict | None:
    """从 transfer_result.json 中提取 ts 方法的 OOD 结果。

    返回 dict:
        delta_ece_ood: float
        ci_low: float
        ci_high: float
        significant: bool   (CI 下界 > 0)
    若文件损坏或缺少 ts 方法，返回 None。
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None

    methods = data.get("methods", {})
    ts = methods.get("ts")
    if not ts or "ood" not in ts:
        return None

    ood = ts["ood"]
    dece = ood.get("deltaECE")
    ci = ood.get("ci")
    if dece is None or not isinstance(ci, list) or len(ci) < 2:
        return None

    return {
        "delta_ece_ood": dece,
        "ci_low": ci[0],
        "ci_high": ci[1],
        "significant": ci[0] > 0.0,
    }


def count_log_methods(log_file: Path) -> int:
    """从日志中统计已完成的方法数（含 'decay=' 的行数）。"""
    if not log_file.exists():
        return 0
    try:
        text = log_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return 0
    return sum(1 for line in text.splitlines() if "decay=" in line)


def tail_log(log_file: Path, n: int = 3) -> str:
    """返回日志最后 n 行。"""
    if not log_file.exists():
        return ""
    try:
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(lines[-n:]) if lines else ""


def check_python_processes() -> dict:
    """检查 python 进程是否在运行，返回进程信息。

    返回 dict:
        running: bool
        count: int
        pids: list[int]
        eval_transfer_running: bool   (是否有 eval_transfer.py 在跑)
        launcher_running: bool         (是否有 launch_remaining4 在跑)
    """
    try:
        r = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'",
             "get", "ProcessId,CommandLine", "/format:csv"],
            capture_output=True, text=True, timeout=10,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return {"running": False, "count": 0, "pids": [],
                "eval_transfer_running": False, "launcher_running": False,
                "error": "wmic 调用失败"}

    pids = []
    eval_running = False
    launcher_running = False
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line or line.lower().startswith("node,"):
            continue
        # CSV 格式: Node,CommandLine,ProcessId
        parts = line.split(",")
        if len(parts) < 3:
            continue
        cmd = ",".join(parts[1:-1])
        try:
            pid = int(parts[-1])
        except ValueError:
            continue
        pids.append(pid)
        if "eval_transfer.py" in cmd:
            eval_running = True
        if "launch_remaining4" in cmd:
            launcher_running = True

    return {
        "running": len(pids) > 0,
        "count": len(pids),
        "pids": pids,
        "eval_transfer_running": eval_running,
        "launcher_running": launcher_running,
    }


def find_current_running() -> dict | None:
    """推断当前正在运行的实验（基于日志最近修改时间 + 进程命令行）。"""
    # 优先从进程命令行解析
    try:
        r = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'",
             "get", "CommandLine", "/format:list"],
            capture_output=True, text=True, timeout=10,
        )
        for line in r.stdout.splitlines():
            if "eval_transfer.py" in line and "--source" in line:
                # 解析 --source X --target Y --seeds Z
                tokens = line.split()
                src = tgt = None
                seeds = None
                for i, t in enumerate(tokens):
                    if t == "--source" and i + 1 < len(tokens):
                        src = tokens[i + 1]
                    elif t == "--target" and i + 1 < len(tokens):
                        tgt = tokens[i + 1]
                    elif t == "--seeds" and i + 1 < len(tokens):
                        try:
                            seeds = int(tokens[i + 1])
                        except ValueError:
                            pass
                if src and tgt and seeds is not None:
                    return {
                        "direction": f"{src}_{tgt}",
                        "seed": seeds,
                        "source": "process_cmdline",
                    }
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # 回退：找最近修改的日志
    candidates = []
    for d in DIRECTIONS:
        for s in SEEDS:
            lp = log_path(d, s)
            if lp.exists() and not result_path(d, s).exists():
                candidates.append((lp.stat().st_mtime, d, s))
    if candidates:
        candidates.sort(reverse=True)
        _, d, s = candidates[0]
        return {"direction": d, "seed": s, "source": "log_mtime"}
    return None


# ---------------------------------------------------------------------------
# 主检查函数
# ---------------------------------------------------------------------------
def check_progress() -> dict:
    """执行一次完整的进度检查，返回结构化结果。"""
    results = []
    done_count = 0

    for direction in DIRECTIONS:
        for seed in SEEDS:
            rp = result_path(direction, seed)
            entry = {
                "direction": direction,
                "seed": seed,
                "done": rp.exists(),
            }
            if rp.exists():
                done_count += 1
                ts = read_ts_result(rp)
                if ts is not None:
                    entry["ts"] = ts
                else:
                    entry["ts"] = None
                    entry["warning"] = "结果文件存在但无法读取 ts 方法"
            else:
                # 未完成：尝试从日志看进度
                lp = log_path(direction, seed)
                entry["methods_done"] = count_log_methods(lp)
                if lp.exists():
                    entry["log_size"] = lp.stat().st_size
            results.append(entry)

    procs = check_python_processes()
    current = find_current_running()

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(DIRECTIONS) * len(SEEDS),
        "done": done_count,
        "remaining": len(DIRECTIONS) * len(SEEDS) - done_count,
        "all_done": done_count == len(DIRECTIONS) * len(SEEDS),
        "results": results,
        "processes": procs,
        "current_running": current,
    }


# ---------------------------------------------------------------------------
# 输出格式化
# ---------------------------------------------------------------------------
def format_text(report: dict) -> str:
    """格式化为人类可读的文本。"""
    lines = []
    lines.append("=" * 78)
    lines.append(f"P0 迁移校准实验进度检查  |  {report['timestamp']}")
    lines.append("=" * 78)
    lines.append(f"完成: {report['done']}/{report['total']}  "
                 f"剩余: {report['remaining']}  "
                 f"全部完成: {'是' if report['all_done'] else '否'}")
    lines.append("-" * 78)

    # 进程状态
    p = report["processes"]
    lines.append(f"Python 进程: {'运行中' if p['running'] else '未运行'}  "
                 f"(count={p['count']}, pids={p.get('pids', [])})")
    lines.append(f"  eval_transfer 运行中: {p.get('eval_transfer_running', False)}  "
                 f"launcher 运行中: {p.get('launcher_running', False)}")

    cur = report.get("current_running")
    if cur:
        lines.append(f"当前实验: {cur['direction']}/seed{cur['seed']}  "
                     f"(来源: {cur['source']})")
    lines.append("-" * 78)

    # 表头
    lines.append(f"{'方向':<16} {'Seed':>4} {'状态':<6} "
                 f"{'ΔECE_OOD':>10} {'CI下界':>10} {'CI上界':>10} {'显著':>5}")
    lines.append("-" * 78)

    for r in report["results"]:
        d = r["direction"]
        s = r["seed"]
        if r["done"]:
            ts = r.get("ts")
            if ts:
                dece = f"{ts['delta_ece_ood']:+.4f}"
                lo = f"{ts['ci_low']:+.4f}"
                hi = f"{ts['ci_high']:+.4f}"
                sig = "是" if ts["significant"] else "否"
            else:
                dece = lo = hi = sig = "N/A"
            status = "✅完成"
        else:
            dece = lo = hi = sig = "-"
            md = r.get("methods_done", 0)
            status = f"⏳{md}/8"
        lines.append(f"{d:<16} {s:>4} {status:<8} {dece:>10} {lo:>10} {hi:>10} {sig:>5}")

    lines.append("=" * 78)

    # 当前运行实验的日志尾部
    if cur and not report["all_done"]:
        lp = log_path(cur["direction"], cur["seed"])
        tail = tail_log(lp, 5)
        if tail:
            lines.append(f"当前日志尾部 ({lp.name}):")
            for tl in tail.splitlines():
                lines.append(f"  {tl}")
            lines.append("=" * 78)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="P0 实验进度检查")
    parser.add_argument("--json", action="store_true", help="输出 JSON 格式")
    parser.add_argument("--quiet", action="store_true", help="仅输出一行汇总")
    args = parser.parse_args()

    report = check_progress()

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.quiet:
        sig_count = sum(
            1 for r in report["results"]
            if r.get("ts") and r["ts"]["significant"]
        )
        print(f"{report['timestamp']} | 完成 {report['done']}/{report['total']} "
              f"| 显著为正 {sig_count} | "
              f"python={'运行' if report['processes']['running'] else '停止'}")
    else:
        print(format_text(report))

    # 退出码：0=全部完成, 1=未完成但进程在跑, 2=未完成且进程已停止
    if report["all_done"]:
        sys.exit(0)
    elif report["processes"]["running"]:
        sys.exit(1)
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()