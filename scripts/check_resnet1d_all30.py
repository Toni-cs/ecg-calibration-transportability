"""检查所有6方向×5seed=30个ResNet1D实验是否全部完成。"""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1]

DIRECTIONS = [
    ("chapman", "cpsc"),
    ("chapman", "ptbxl"),
    ("cpsc", "chapman"),
    ("cpsc", "ptbxl"),
    ("ptbxl", "chapman"),
    ("ptbxl", "cpsc"),
]
SEEDS = [42, 43, 44, 45, 46]

print("=" * 90)
print("ResNet1D 全量实验完成情况检查 (6方向 × 5seed = 30个)")
print("=" * 90)

total = 0
done = 0
missing = []
results_table = []

for src, tgt in DIRECTIONS:
    print(f"\n[{src}_{tgt}]")
    for seed in SEEDS:
        total += 1
        p = (root / "checkpoints" / "transfer" / f"{src}_{tgt}" /
             "resnet1d" / f"seed{seed}" / "transfer_result.json")
        if p.exists():
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                methods = d.get("methods", {})
                if isinstance(methods, dict) and len(methods) > 0:
                    done += 1
                    # 提取TS的OOD deltaECE
                    ts = methods.get("ts", {})
                    ood = ts.get("ood", {})
                    delta = ood.get("deltaECE") if ood else None
                    ci = ood.get("ci") if ood else None
                    if delta is not None and ci is not None:
                        print(f"  seed{seed}: ✓  TS ΔECE_OOD={delta:.6f}  CI=[{ci[0]:.6f}, {ci[1]:.6f}]")
                        results_table.append((src, tgt, seed, delta, ci[0], ci[1]))
                    else:
                        print(f"  seed{seed}: ✓  (TS结果字段缺失)")
                        results_table.append((src, tgt, seed, None, None, None))
                else:
                    print(f"  seed{seed}: ✗  (transfer_result.json存在但methods为空)")
                    missing.append((src, tgt, seed))
            except Exception as e:
                print(f"  seed{seed}: ✗  (JSON解析失败: {e})")
                missing.append((src, tgt, seed))
        else:
            print(f"  seed{seed}: ✗  (transfer_result.json不存在)")
            missing.append((src, tgt, seed))

print("\n" + "=" * 90)
print(f"总计: {done}/{total} 完成")
if missing:
    print(f"缺失 {len(missing)} 个:")
    for src, tgt, seed in missing:
        print(f"  - {src}_{tgt}/resnet1d/seed{seed}")
else:
    print("✓ 全部30个ResNet1D实验均已完成！")
print("=" * 90)

# 输出本次新完成的2个实验详情
print("\n本次新完成的2个实验 (ptbxl_chapman方向):")
print("-" * 90)
for src, tgt, seed, delta, ci_low, ci_high in results_table:
    if src == "ptbxl" and tgt == "chapman" and seed in (45, 46):
        if delta is not None:
            print(f"  {src}_{tgt}/resnet1d/seed{seed}:")
            print(f"    TS ΔECE_OOD = {delta:.6f}")
            print(f"    95% CI      = [{ci_low:.6f}, {ci_high:.6f}]")
            print(f"    CI 宽度     = {ci_high - ci_low:.6f}")
        else:
            print(f"  {src}_{tgt}/resnet1d/seed{seed}: 结果提取失败")
print("-" * 90)