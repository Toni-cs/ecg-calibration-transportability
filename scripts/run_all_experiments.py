"""批量运行全部实验（顺序执行，避免GPU OOM）

执行顺序：
1. E3  - Brier Reliability + DCR + NCV (核心实验, ~1h)
2. E2  - 消融 + 判别指标 (~1h)
3. E1a - L2移位矩阵补齐 (~2h)
4. E1b - LOCO跨语料库验证 (~30min)
5. E4  - 温度分布分析 (~1h)
6. E6  - 可靠性图生成 (~1h)
7. E5  - InceptionTime-Lite训练 (~30-45h)
"""
import subprocess
import sys
import time
import os

os.environ["PYTHONIOENCODING"] = "utf-8"

EXPERIMENTS = [
    {
        "name": "E3",
        "cmd": [sys.executable, "scripts/run_e3_brier_dcr_ncv.py", "--batch-size", "16"],
        "log": "results/e3_full.log",
        "timeout": 7200,  # 2 hours
    },
    {
        "name": "E2",
        "cmd": [sys.executable, "scripts/run_e2_ablation_discrimination.py"],
        "log": "results/e2_full.log",
        "timeout": 7200,
    },
    {
        "name": "E1a",
        "cmd": [sys.executable, "scripts/run_e1a_l2_shift_full.py"],
        "log": "results/e1a_full.log",
        "timeout": 14400,  # 4 hours
    },
    {
        "name": "E1b",
        "cmd": [sys.executable, "scripts/run_e1b_loco_validation.py"],
        "log": "results/e1b_full.log",
        "timeout": 3600,
    },
    {
        "name": "E4",
        "cmd": [sys.executable, "scripts/run_e4_temperature_analysis.py"],
        "log": "results/e4_full.log",
        "timeout": 7200,
    },
    {
        "name": "E6",
        "cmd": [sys.executable, "scripts/run_e6_reliability_diagrams.py"],
        "log": "results/e6_full.log",
        "timeout": 7200,
    },
    # E5 is last (30-45 hours)
    {
        "name": "E5",
        "cmd": [sys.executable, "scripts/run_e5_inception_lite.py"],
        "log": "results/e5_full.log",
        "timeout": 180000,  # 50 hours
    },
]


def run_experiment(exp):
    name = exp["name"]
    cmd = exp["cmd"]
    log_path = exp["log"]
    timeout = exp["timeout"]

    print(f"\n{'='*80}")
    print(f"开始 {name}: {' '.join(cmd)}")
    print(f"日志: {log_path}")
    print(f"超时: {timeout}s")
    print(f"{'='*80}")

    start = time.time()
    try:
        with open(log_path, "w", encoding="utf-8") as logf:
            proc = subprocess.Popen(
                cmd,
                stdout=logf,
                stderr=subprocess.STDOUT,
                cwd=r"D:\A1\ecg-lab-v2",
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            proc.wait(timeout=timeout)
            elapsed = time.time() - start
            rc = proc.returncode
            print(f"\n{name} 完成: returncode={rc}, 耗时={elapsed:.0f}s ({elapsed/3600:.1f}h)")
            return rc == 0
    except subprocess.TimeoutExpired:
        proc.kill()
        elapsed = time.time() - start
        print(f"\n{name} 超时! 耗时={elapsed:.0f}s")
        return False
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n{name} 异常: {e}, 耗时={elapsed:.0f}s")
        return False


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip", nargs="*", default=[], help="跳过的实验")
    ap.add_argument("--only", nargs="*", default=None, help="只运行指定实验")
    args = ap.parse_args()

    exps = EXPERIMENTS
    if args.only:
        exps = [e for e in EXPERIMENTS if e["name"] in args.only]
    else:
        exps = [e for e in EXPERIMENTS if e["name"] not in args.skip]

    results = {}
    for exp in exps:
        ok = run_experiment(exp)
        results[exp["name"]] = ok
        if not ok and exp["name"] != "E5":
            print(f"\n警告: {exp['name']} 失败，继续下一个实验")

    print(f"\n{'='*80}")
    print("全部实验完成")
    print(f"{'='*80}")
    for name, ok in results.items():
        status = "✓ 成功" if ok else "✗ 失败"
        print(f"  {name}: {status}")


if __name__ == "__main__":
    main()
