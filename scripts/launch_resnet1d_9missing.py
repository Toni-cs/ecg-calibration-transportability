"""后台串行启动 9 个缺失的 resnet1d 架构迁移实验。

补齐 P2.1 缺口：前一个子代理已完成 3 个实验
(chapman_ptbxl/seed44, cpsc_chapman/seed44, cpsc_ptbxl/seed44)，
本脚本只运行剩余 9 个缺失实验。

9 个实验清单：
1. chapman_ptbxl/resnet1d/seed45
2. chapman_ptbxl/resnet1d/seed46
3. cpsc_chapman/resnet1d/seed45
4. cpsc_chapman/resnet1d/seed46
5. cpsc_ptbxl/resnet1d/seed45
6. cpsc_ptbxl/resnet1d/seed46
7. ptbxl_chapman/resnet1d/seed44  (已有 best_model.pt，用 --load-model 复用)
8. ptbxl_chapman/resnet1d/seed45
9. ptbxl_chapman/resnet1d/seed46

参数与已完成的 3 个实验保持一致：
- arch=resnet1d
- methods: ts platt isotonic vector matrix dirichlet em_prior bbse_prior
- epochs=50, gpu-inference
- B=10000, bci-method=percentile

预计每个约 15-30 分钟，总计约 2-4 小时。

输出路径：checkpoints/transfer/<source>_<target>/resnet1d/seed<seed>/transfer_result.json
"""
import subprocess, sys, json
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

# 9 个缺失实验：(source, target, seed, use_load_model)
MISSING = [
    ("chapman", "ptbxl", 45, False),
    ("chapman", "ptbxl", 46, False),
    ("cpsc", "chapman", 45, False),
    ("cpsc", "chapman", 46, False),
    ("cpsc", "ptbxl", 45, False),
    ("cpsc", "ptbxl", 46, False),
    ("ptbxl", "chapman", 44, True),   # 已有 best_model.pt，复用
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
    jobs.append((cmd, name, use_load))

print(f"\nTotal {len(jobs)} resnet1d 缺失实验待运行。")
for i, (cmd, name, use_load) in enumerate(jobs):
    tag = " [load-model]" if use_load else ""
    print(f"  [{i+1}/{len(jobs)}] {name}{tag}")

print("\n" + "=" * 60)
print("开始串行执行")
print("=" * 60)

done = 0
failed = []
for i, (cmd, name, use_load) in enumerate(jobs):
    log = open(root / f"transfer_{name}.log", "w", encoding="utf-8")
    print(f"\n[{i+1}/{len(jobs)}] Starting {name}{' [load-model]' if use_load else ''}...",
          flush=True)
    proc = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, cwd=str(root))
    proc.wait()
    log.close()
    print(f"[{i+1}/{len(jobs)}] {name} exited with code {proc.returncode}", flush=True)
    if proc.returncode != 0:
        print(f"[{i+1}/{len(jobs)}] FAILED, continuing to next job", flush=True)
        failed.append(name)
    else:
        done += 1

print("\n" + "=" * 60)
print(f"完成：{done}/{len(jobs)} 成功，{len(failed)} 失败")
if failed:
    print("失败列表：")
    for f in failed:
        print(f"  - {f}")
print("=" * 60)
print("All 9 missing resnet1d experiments done.")