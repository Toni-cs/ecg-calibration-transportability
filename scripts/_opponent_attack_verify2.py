"""补充验证：检查2架构平均是否能解释E6与CSV的差异"""
import sys
from pathlib import Path
import numpy as np

_PROJECT_ROOT = Path(r"D:\A1\ecg-lab-v2")
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from run_e6_reliability_diagrams import compute_reliability_bins, PAIRS, ARCHS, SEEDS, _load_npz

print("=" * 70)
print("V16: 2架构平均 ECE vs CSV raw_ece_mean")
print("=" * 70)

# 对每个方向，计算 resnet1d + inceptiontime 的平均 ECE（seed42, 无shift）
print(f"  {'方向':<20} {'resnet1d':<12} {'inception':<12} {'2架构平均':<12} {'CSV noise0':<12} {'差异':<10}")
import csv
csv_path = _PROJECT_ROOT / "results" / "l2_shift_full_390cells.csv"
csv_data = {}
with open(csv_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row["seed"] == "42" and row["shift"] == "noise0":
            csv_data[row["direction"]] = float(row["raw_ece_mean"])

for source, target in PAIRS:
    direction = f"{source}->{target}"
    eces = []
    for arch in ARCHS:
        data = _load_npz(source, target, arch, 42)
        if data is None:
            continue
        bins = compute_reliability_bins(data["ood_raw"], data["ood_labels"])
        eces.append(bins["ece"])
    
    if len(eces) == 2:
        avg = np.mean(eces)
        csv_val = csv_data.get(direction, float("nan"))
        diff = avg - csv_val
        print(f"  {direction:<20} {eces[0]:<12.6f} {eces[1]:<12.6f} {avg:<12.6f} {csv_val:<12.6f} {diff:<+10.6f}")

print("\n" + "=" * 70)
print("V17: 检查汇总图淡色背景曲线是否包含种子变异性")
print("=" * 70)
print("  代码 line 742: if seed == args.rep_seed and arch == args.rep_arch:")
print("  → 汇总图只收集 seed42 + resnet1d 的6个方向")
print("  → 淡色背景曲线（line 474-481）展示的是6方向的变异性，不是5种子的变异性")
print("  → 汇总图不展示种子变异性，读者必须手动查看60张补充图")

print("\n" + "=" * 70)
print("V18: 检查 bootstrap CI 是否用同一个 rng（相关性问题）")
print("=" * 70)
print("  代码 line 700: rng = np.random.default_rng(args.rng_seed)")
print("  代码 line 727-728: _compute_bins_and_ci(..., rng)")
print("  → ci_before 和 ci_after 用同一个 rng")
print("  → 它们的 bootstrap 重采样索引是相关的（不独立）")
print("  → 但这对'视觉辅助'可能可接受")

# 实际验证：检查ci_before和ci_after的重采样是否相关
data = _load_npz("ptbxl", "chapman", "resnet1d", 42)
rng1 = np.random.default_rng(0)
rng2 = np.random.default_rng(0)
# 模拟两次调用
n = len(data["ood_labels"])
idx1 = rng1.choice(n, n, replace=True)
idx2 = rng2.choice(n, n, replace=True)
print(f"  两次相同 rng 的第一次抽样是否相同: {np.array_equal(idx1, idx2)}")

# 在 _compute_bins_and_ci 中，ci_before 和 ci_after 顺序调用同一个 rng
# 所以 ci_after 的随机数是 ci_before 之后的
print("  → ci_before 和 ci_after 用同一个 rng 的不同段，不是独立 bootstrap")
print("  → 但这是保守的（相关性会使 CI 偏窄，但作为视觉辅助可接受）")

print("\n" + "=" * 70)
print("V19: 检查 E6 图是否标注了 ECE 是 10-bin ECE（vs smooth_ece）")
print("=" * 70)
print("  代码 line 333: f'Before TS (ECE={bins_before[\"ece\"]:.3f})'")
print("  → 图例只标注 'ECE=0.108'，未标注 '10-bin ECE'")
print("  → 读者可能误以为是 smooth_ece（主终点用的估计量）")
print("  → 这是语义偏移：图中 ECE 与主终点 ΔECE 用不同估计量，但图例不区分")

print("\n" + "=" * 70)
print("V20: 检查 ΔECE 符号——是否有方向 TS 恶化")
print("=" * 70)
print(f"  {'方向':<20} {'种子':<6} {'ECE_raw':<12} {'ECE_cal':<12} {'ΔECE':<12} {'TS效果':<10}")
n_worsened = 0
n_total = 0
for source, target in PAIRS:
    for seed in SEEDS:
        data = _load_npz(source, target, "resnet1d", seed)
        if data is None:
            continue
        bins_b = compute_reliability_bins(data["ood_raw"], data["ood_labels"])
        bins_a = compute_reliability_bins(data["ood_cal"], data["ood_labels"])
        delta = bins_b["ece"] - bins_a["ece"]
        effect = "改善" if delta > 0 else "恶化"
        if delta <= 0:
            n_worsened += 1
        n_total += 1
        marker = " ***" if delta <= 0 else ""
        print(f"  {source}→{target:<15} {seed:<6} {bins_b['ece']:<12.6f} {bins_a['ece']:<12.6f} {delta:<+12.6f} {effect:<10}{marker}")

print(f"\n  TS 恶化的 (方向,种子) 组合: {n_worsened}/{n_total} ({100*n_worsened/n_total:.1f}%)")
print(f"  → 正方声称 'TS后曲线更接近y=x则校准有效'，但 {n_worsened} 个组合 TS 恶化")

# 检查主图（seed42）中有几个方向恶化
print("\n  主图（seed42）中各方向 ΔECE：")
n_worsened_main = 0
for source, target in PAIRS:
    data = _load_npz(source, target, "resnet1d", 42)
    if data is None:
        continue
    bins_b = compute_reliability_bins(data["ood_raw"], data["ood_labels"])
    bins_a = compute_reliability_bins(data["ood_cal"], data["ood_labels"])
    delta = bins_b["ece"] - bins_a["ece"]
    effect = "改善" if delta > 0 else "恶化"
    if delta <= 0:
        n_worsened_main += 1
    print(f"    {source}→{target}: ΔECE={delta:+.6f} ({effect})")
print(f"  主图中 TS 恶化的方向数: {n_worsened_main}/6")
