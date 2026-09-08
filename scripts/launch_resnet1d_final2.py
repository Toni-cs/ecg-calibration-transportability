"""
ResNet1D 最后2个实验补齐脚本（第四批）
方向: ptbxl_chapman, 架构: resnet1d
- seed45: 已有best_model.pt, 用--load-model跳过重训
- seed46: 从头训练+评估
配置: bootstrap=10000, bci-method=percentile, methods=8种, epochs=50, gpu-inference
"""
import subprocess, sys, json, time
from pathlib import Path

root = Path(__file__).resolve().parents[1]

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

DIRS = {
    "chapman": "data/chapman_processed_v2",
    "ptbxl": "data/ptbxl_processed",
}

# 2 个缺失实验
MISSING = [
    ("ptbxl", "chapman", 45, True),    # 已有 best_model.pt，复用
    ("ptbxl", "chapman", 46, False),   # 从头训练
]


def result_exists(src, tgt, seed):
    p = (root / "checkpoints" / "transfer" / f"{src}_{tgt}" /
         "resnet1d" / f"seed{seed}" / "transfer_result.json")
    if not p.exists():
        return False
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return "methods" in d and isinstance(d["methods"], dict) and len(d["methods"]) > 0
    except Exception:
        return False


def extract_ts_delta_ece(src, tgt, seed):
    """从 transfer_result.json 提取 TS 方法的 OOD deltaECE 和 CI。"""
    p = (root / "checkpoints" / "transfer" / f"{src}_{tgt}" /
         "resnet1d" / f"seed{seed}" / "transfer_result.json")
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        methods = d.get("methods", {})
        ts = methods.get("ts", {})
        # 兼容两种字段命名
        ood = ts.get("ood", {})
        delta = ood.get("deltaECE") if ood else ts.get("delta_ece_ood")
        ci = ood.get("ci") if ood else None
        if ci is None:
            ci = [ts.get("ci_low"), ts.get("ci_high")]
        return (delta, ci[0], ci[1])
    except Exception as e:
        print(f"  提取TS结果异常: {e}")
        return None


jobs = []
for src, tgt, seed, use_load in MISSING:
    if result_exists(src, tgt, seed):
        print(f"[SKIP] {src}_{tgt}_resnet1d_seed{seed} 已完成，跳过")
        continue
    name = f"{src}_{tgt}_resnet1d_seed{seed}"
    cmd = common + ["--source", src, "--source-dir", DIRS[src],
                    "--target", tgt, "--target-dir", DIRS[tgt],
                    "--seeds", str(seed)]
    if use_load:
        cmd.append("--load-model")
    jobs.append((cmd, name, use_load, (src, tgt, seed)))

print(f"\nTotal {len(jobs)} resnet1d 缺失实验待运行。")
for i, (cmd, name, use_load, _) in enumerate(jobs):
    tag = " [load-model]" if use_load else ""
    print(f"  [{i+1}/{len(jobs)}] {name}{tag}")

print("\n" + "=" * 60)
print("开始串行执行")
print("=" * 60)

done = 0
failed = []
completed_results = []
overall_start = time.time()

for i, (cmd, name, use_load, (src, tgt, seed)) in enumerate(jobs):
    log = open(root / f"transfer_{name}_batch4.log", "w", encoding="utf-8")
    tag = " [load-model]" if use_load else ""
    print(f"\n[{i+1}/{len(jobs)}] Starting {name}{tag}...", flush=True)
    t0 = time.time()
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(root))
    proc.wait()
    elapsed = time.time() - t0
    log.close()
    print(f"[{i+1}/{len(jobs)}] {name} exited with code {proc.returncode} "
          f"({elapsed/60:.1f} min)", flush=True)
    if proc.returncode != 0:
        print(f"[{i+1}/{len(jobs)}] FAILED, continuing to next job", flush=True)
        failed.append(name)
    else:
        done += 1
        res = extract_ts_delta_ece(src, tgt, seed)
        if res is not None:
            delta, ci_low, ci_high = res
            completed_results.append((name, delta, ci_low, ci_high))
            print(f"  -> TS ΔECE_OOD = {delta}, CI = [{ci_low}, {ci_high}]",
                  flush=True)
        else:
            completed_results.append((name, None, None, None))
            print(f"  -> 警告：未能提取 TS 结果", flush=True)

total_elapsed = time.time() - overall_start
print("\n" + "=" * 60)
print(f"完成：{done}/{len(jobs)} 成功，{len(failed)} 失败 "
      f"(总耗时 {total_elapsed/60:.1f} min)")
if failed:
    print("失败列表：")
    for f in failed:
        print(f"  - {f}")
print("=" * 60)

if completed_results:
    print("\n新完成实验的 TS 方法 ΔECE_OOD 和 CI：")
    print("-" * 80)
    for name, delta, ci_low, ci_high in completed_results:
        if delta is not None:
            print(f"  {name}: ΔECE_OOD = {delta:.6f}, CI = [{ci_low:.6f}, {ci_high:.6f}]")
        else:
            print(f"  {name}: 未能提取结果")
    print("-" * 80)

print("Batch 4 (final 2): All missing resnet1d experiments done.")
