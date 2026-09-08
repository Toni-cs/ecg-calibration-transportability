"""ResNet1D 补齐第三批：6 个缺失实验串行执行。

前两批子代理已完成 6 个新实验，本批补齐剩余 6 个：
1. ptbxl_chapman/resnet1d/seed44  (已有 best_model.pt，用 --load-model 复用)
2. cpsc_chapman/resnet1d/seed46   (已有 best_model.pt，用 --load-model 复用)
3. cpsc_ptbxl/resnet1d/seed45
4. cpsc_ptbxl/resnet1d/seed46
5. ptbxl_chapman/resnet1d/seed45
6. ptbxl_chapman/resnet1d/seed46

参数与前两批保持一致：
- arch=resnet1d
- methods: ts platt isotonic vector matrix dirichlet em_prior bbse_prior
- epochs=50, gpu-inference
- B=10000, bci-method=percentile

输出路径：checkpoints/transfer/<source>_<target>/resnet1d/seed<seed>/transfer_result.json
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
    "cpsc": "data/cpsc_processed",
    "ptbxl": "data/ptbxl_processed",
}

# 6 个缺失实验（按推荐顺序：先 load-model 快速完成的）
MISSING = [
    ("ptbxl", "chapman", 44, True),    # 已有 best_model.pt，复用
    ("cpsc", "chapman", 46, True),     # 已有 best_model.pt，复用
    ("cpsc", "ptbxl", 45, False),
    ("cpsc", "ptbxl", 46, False),
    ("ptbxl", "chapman", 45, False),
    ("ptbxl", "chapman", 46, False),
]


def result_exists(src, tgt, seed):
    """检查 transfer_result.json 是否已存在且包含 methods 字段。"""
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
    """从 transfer_result.json 提取 TS 方法的 delta_ece_ood 和 CI。"""
    p = (root / "checkpoints" / "transfer" / f"{src}_{tgt}" /
         "resnet1d" / f"seed{seed}" / "transfer_result.json")
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        methods = d.get("methods", {})
        ts = methods.get("ts", {})
        delta = ts.get("delta_ece_ood")
        ci_low = ts.get("ci_low")
        ci_high = ts.get("ci_high")
        return (delta, ci_low, ci_high)
    except Exception:
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
    log = open(root / f"transfer_{name}_batch3.log", "w", encoding="utf-8")
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
        # 提取 TS 方法结果
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

print("Batch 3: All 6 missing resnet1d experiments done.")