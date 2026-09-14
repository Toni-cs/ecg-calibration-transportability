"""反方攻击验证脚本：对E6可靠性图统计精准性进行数值验证。

执行以下验证：
1. compute_reliability_bins 与 calibration.ece 是否真的逐位一致
2. E6图的ECE值是否与CSV数值一致
3. bin计算是否有off-by-one错误
4. TS后argmax是否真的不变
5. 加权平均ECE与全局ECE是否相等
6. bootstrap CI是否正确覆盖
7. 空bin处理是否正确
8. 边界情况：所有样本集中在一个bin
9. 检查汇总图标注是否误导
10. cherry-picking检查：所有种子的ECE值
"""
from __future__ import annotations

import sys
import json
import csv
import warnings
from pathlib import Path

import numpy as np

_PROJECT_ROOT = Path(r"D:\A1\ecg-lab-v2")
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from src.utils.calibration import ece as cal_ece, smooth_ece, _validate_n_bins
from run_e6_reliability_diagrams import (
    compute_reliability_bins,
    bootstrap_bin_accuracy_ci,
    PAIRS, ARCHS, SEEDS, N_BINS, N_BOOTSTRAP_CI, REP_SEED, REP_ARCH,
    _load_npz,
)


def sep(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


# ============================================================================
# 验证1：compute_reliability_bins 与 calibration.ece 逐位一致性
# ============================================================================
sep("V1: compute_reliability_bins vs calibration.ece 逐位一致性")

rng = np.random.default_rng(42)
mismatches = []
for trial in range(20):
    n = rng.integers(100, 5000)
    k = rng.integers(2, 8)
    probs = rng.dirichlet(np.ones(k), size=n)
    labels = rng.integers(0, k, size=n)

    # E6 脚本
    bins = compute_reliability_bins(probs, labels, n_bins=10)
    ece_e6 = bins["ece"]

    # calibration.py：注意 ece() 期望 1D probs + 1D labels
    # E6 用 top-label：confidence=max(probs), correctness=(argmax==label)
    confidence = probs.max(axis=1)
    correctness = (probs.argmax(axis=1) == labels).astype(float)
    ece_cal = cal_ece(confidence, correctness, n_bins=10)

    diff = abs(ece_e6 - ece_cal)
    if diff > 1e-12:
        mismatches.append((trial, n, k, ece_e6, ece_cal, diff))
        print(f"  [MISMATCH] trial={trial} n={n} k={k}: E6={ece_e6:.10f} cal={ece_cal:.10f} diff={diff:.2e}")

if not mismatches:
    print("  20 次随机试验全部逐位一致（diff < 1e-12）")
else:
    print(f"  发现 {len(mismatches)} 次不一致！")


# ============================================================================
# 验证1b：边界情况 - confidence=1.0 是否归入最后一个bin
# ============================================================================
sep("V1b: confidence=1.0 归入最后一个bin")

probs = np.array([[1.0, 0, 0, 0, 0], [0.95, 0.05, 0, 0, 0], [0.85, 0.15, 0, 0, 0]])
labels = np.array([0, 0, 1])
bins = compute_reliability_bins(probs, labels, n_bins=10)
print(f"  bin_counts = {bins['bin_counts']}")
print(f"  bin 9 (last) count = {bins['bin_counts'][9]} (期望 2: 1.0 和 0.95)")
print(f"  bin 8 count = {bins['bin_counts'][8]} (期望 1: 0.85)")
assert bins["bin_counts"][9] == 2, "FATAL: confidence=1.0 未归入最后一个bin"
assert bins["bin_counts"][8] == 1, "FATAL: 0.85 未归入 bin 8"
print("  ✓ confidence=1.0 正确归入最后一个bin")


# ============================================================================
# 验证1c：off-by-one 检查 - np.linspace vs np.arange
# ============================================================================
sep("V1c: off-by-one 检查 - np.linspace(0,1,11) vs np.arange(0,1.1,0.1)")

boundaries_linspace = np.linspace(0.0, 1.0, 11)
boundaries_arange = np.arange(0, 1.1, 0.1)
print(f"  np.linspace(0,1,11) = {boundaries_linspace}")
print(f"  np.arange(0,1.1,0.1) = {boundaries_arange}")
print(f"  差异 = {np.abs(boundaries_linspace - boundaries_arange).max():.2e}")
# np.arange 有浮点误差
print(f"  np.arange(0,1.1,0.1) 最后一个元素 = {boundaries_arange[-1]:.17f} (可能 != 1.0 精确)")
print(f"  np.linspace(0,1,11) 最后一个元素 = {boundaries_linspace[-1]:.17f}")

# 关键：如果用 np.arange，最后一个边界可能略大于1.0或略小于1.0
if boundaries_arange[-1] != 1.0:
    print(f"  [WARN] np.arange 最后元素 != 1.0 精确（浮点误差）→ 可能导致 confidence=1.0 归属错误")
else:
    print(f"  np.arange 最后元素 == 1.0 精确")


# ============================================================================
# 验证2：E6图ECE值与CSV数值一致性
# ============================================================================
sep("V2: E6图ECE值与CSV数值一致性（逐方向）")

# 加载CSV
csv_path = _PROJECT_ROOT / "results" / "l2_shift_full_390cells.csv"
csv_rows = []
with open(csv_path, "r", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for row in reader:
        csv_rows.append(row)

print(f"  CSV 行数: {len(csv_rows)}")
print(f"  CSV 列: {list(csv_rows[0].keys())}")

# 提取 CSV 中 seed42 + noise0 shift（最接近"无shift基线"）的 raw_ece_mean
print("\n  --- CSV 中 seed42 + noise0 shift 的 raw_ece_mean（2架构平均）---")
for row in csv_rows:
    if row["seed"] == "42" and row["shift"] == "noise0":
        print(f"    {row['direction']}: raw_ece_mean={float(row['raw_ece_mean']):.6f}, "
              f"ts_delta_ece_mean={float(row['ts_delta_ece_mean']):.6f}")

# E6 图的 ECE 值（单架构 resnet1d + seed42 + 无shift）
print("\n  --- E6 图的 ECE 值（resnet1d, seed42, 无shift OOD）---")
e6_ece_data = {}
for source, target in PAIRS:
    data = _load_npz(source, target, "resnet1d", 42)
    if data is None:
        print(f"    {source}→{target}: npz 缺失")
        continue
    bins_raw = compute_reliability_bins(data["ood_raw"], data["ood_labels"])
    bins_cal = compute_reliability_bins(data["ood_cal"], data["ood_labels"])
    e6_ece_data[(source, target)] = {
        "ece_raw": bins_raw["ece"],
        "ece_cal": bins_cal["ece"],
        "n_ood": bins_raw["n_total"],
        "T": float(data["T"]),
    }
    print(f"    {source}→{target}: ECE_raw={bins_raw['ece']:.6f}, "
          f"ECE_cal={bins_cal['ece']:.6f}, n_ood={bins_raw['n_total']}, T={float(data['T']):.4f}")

# 比对
print("\n  --- 数值比对：E6 ECE_raw vs CSV raw_ece_mean (seed42, noise0) ---")
print(f"  {'方向':<20} {'E6 ECE_raw':<15} {'CSV raw_ece_mean':<20} {'差异':<15} {'相对差异':<10}")
for source, target in PAIRS:
    e6_val = e6_ece_data.get((source, target), {}).get("ece_raw")
    if e6_val is None:
        continue
    direction = f"{source}->{target}"
    for row in csv_rows:
        if row["direction"] == direction and row["seed"] == "42" and row["shift"] == "noise0":
            csv_val = float(row["raw_ece_mean"])
            diff = e6_val - csv_val
            rel_diff = diff / csv_val if csv_val > 0 else float("nan")
            print(f"  {direction:<20} {e6_val:<15.6f} {csv_val:<20.6f} {diff:<+15.6f} {rel_diff:<+10.2%}")
            break


# ============================================================================
# 验证3：TS后argmax是否真的不变
# ============================================================================
sep("V3: TS后argmax不变性验证（全60 checkpoint）")

argmax_changes = []
for source, target in PAIRS:
    for arch in ARCHS:
        for seed in SEEDS:
            data = _load_npz(source, target, arch, seed)
            if data is None:
                continue
            raw_argmax = data["ood_raw"].argmax(axis=1)
            cal_argmax = data["ood_cal"].argmax(axis=1)
            n_changed = int((raw_argmax != cal_argmax).sum())
            n_total = len(raw_argmax)
            argmax_changes.append({
                "pair": f"{source}→{target}",
                "arch": arch,
                "seed": seed,
                "n_changed": n_changed,
                "n_total": n_total,
                "pct": 100.0 * n_changed / n_total,
            })

print(f"  总 checkpoint 数: {len(argmax_changes)}")
n_with_changes = sum(1 for x in argmax_changes if x["n_changed"] > 0)
print(f"  argmax 发生变化的 checkpoint 数: {n_with_changes}")
if n_with_changes > 0:
    print("  [FATAL] 正方声称'TS后argmax变化数=0/4050'，但实际有变化！")
    for x in argmax_changes:
        if x["n_changed"] > 0:
            print(f"    {x['pair']} {x['arch']} seed{x['seed']}: "
                  f"{x['n_changed']}/{x['n_total']} ({x['pct']:.2f}%)")
else:
    print("  ✓ 全部 checkpoint TS 后 argmax 不变")

# 显示最大变化数
max_change = max(argmax_changes, key=lambda x: x["n_changed"])
print(f"\n  最大 argmax 变化: {max_change['pair']} {max_change['arch']} seed{max_change['seed']}: "
      f"{max_change['n_changed']}/{max_change['n_total']} ({max_change['pct']:.4f}%)")


# ============================================================================
# 验证4：加权平均ECE vs 全局ECE
# ============================================================================
sep("V4: 加权平均ECE vs 全局ECE（汇总图）")

# 收集6方向的bins（resnet1d, seed42）
all_bins_before = []
all_bins_after = []
all_probs_raw = []
all_probs_cal = []
all_labels = []
pair_names = []
for source, target in PAIRS:
    data = _load_npz(source, target, "resnet1d", 42)
    if data is None:
        continue
    bins_b = compute_reliability_bins(data["ood_raw"], data["ood_labels"])
    bins_a = compute_reliability_bins(data["ood_cal"], data["ood_labels"])
    all_bins_before.append(bins_b)
    all_bins_after.append(bins_a)
    all_probs_raw.append(data["ood_raw"])
    all_probs_cal.append(data["ood_cal"])
    all_labels.append(data["ood_labels"])
    pair_names.append(f"{source}→{target}")

# 加权平均ECE（E6脚本的方法）
weights = np.array([b["n_total"] for b in all_bins_before], dtype=float)
eces = np.array([b["ece"] for b in all_bins_before], dtype=float)
weighted_ece = float(np.average(eces, weights=weights))
print(f"  加权平均 ECE (before) = {weighted_ece:.6f}")

# 全局ECE（合并所有样本重算）—— 注意：不同方向 num_classes 不同（5/4），不能直接 concatenate
# 这本身就是一个攻击点：汇总图把不同类数的方向混在一起加权平均
print("  [关键发现] 不同方向的 num_classes 不同（ptbxl/chapman=5, cpsc=4）")
print("  → 不能直接 concatenate 所有方向的 probs 矩阵")
print("  → 汇总图的'加权平均'是把不同类数空间的 ECE 混在一起平均")

# 分别检查每个方向的 probs 形状
for i, (pair, probs_r) in enumerate(zip(pair_names, all_probs_raw)):
    print(f"    {pair}: ood_raw.shape = {probs_r.shape}, n_total = {len(probs_r)}")

# 改用 top-label 1D 形式计算全局 ECE（confidence + correctness）
all_confidence = []
all_correctness = []
for probs_r, labels_r in zip(all_probs_raw, all_labels):
    conf = probs_r.max(axis=1)
    corr = (probs_r.argmax(axis=1) == labels_r).astype(float)
    all_confidence.append(conf)
    all_correctness.append(corr)

global_confidence = np.concatenate(all_confidence)
global_correctness = np.concatenate(all_correctness)
# 用 calibration.ece 计算全局 ECE
global_ece = cal_ece(global_confidence, global_correctness, n_bins=10)
print(f"\n  全局 ECE (before, 合并 top-label 1D 重算) = {global_ece:.6f}")
print(f"  差异 = {weighted_ece - global_ece:+.6f}")
print(f"  相对差异 = {(weighted_ece - global_ece) / global_ece * 100:+.2f}%")

# TS后
weights_a = np.array([b["n_total"] for b in all_bins_after], dtype=float)
eces_a = np.array([b["ece"] for b in all_bins_after], dtype=float)
weighted_ece_a = float(np.average(eces_a, weights=weights_a))

# TS后全局
all_confidence_a = []
all_correctness_a = []
for probs_c, labels_r in zip(all_probs_cal, all_labels):
    conf = probs_c.max(axis=1)
    corr = (probs_c.argmax(axis=1) == labels_r).astype(float)
    all_confidence_a.append(conf)
    all_correctness_a.append(corr)
global_confidence_a = np.concatenate(all_confidence_a)
global_correctness_a = np.concatenate(all_correctness_a)
global_ece_a = cal_ece(global_confidence_a, global_correctness_a, n_bins=10)
print(f"\n  加权平均 ECE (after) = {weighted_ece_a:.6f}")
print(f"  全局 ECE (after, 合并 top-label 1D 重算) = {global_ece_a:.6f}")
print(f"  差异 = {weighted_ece_a - global_ece_a:+.6f}")
print(f"  相对差异 = {(weighted_ece_a - global_ece_a) / global_ece_a * 100:+.2f}%")

# ΔECE
print(f"\n  加权平均 ΔECE = {weighted_ece - weighted_ece_a:+.6f}")
print(f"  全局 ΔECE = {global_ece - global_ece_a:+.6f}")
print(f"  ΔECE 差异 = {(weighted_ece - weighted_ece_a) - (global_ece - global_ece_a):+.6f}")


# ============================================================================
# 验证5：bootstrap CI 覆盖性检查
# ============================================================================
sep("V5: bootstrap CI 覆盖性检查（蒙特卡洛）")

# 用 ptbxl→chapman resnet1d seed42
data = _load_npz("ptbxl", "chapman", "resnet1d", 42)
probs_raw = data["ood_raw"]
labels = data["ood_labels"]

# 计算点估计
bins_true = compute_reliability_bins(probs_raw, labels)
print(f"  点估计 ECE = {bins_true['ece']:.6f}")
print(f"  bin_counts = {bins_true['bin_counts']}")

# 计算CI（1000次bootstrap）
rng_ci = np.random.default_rng(0)
ci_lo, ci_hi = bootstrap_bin_accuracy_ci(probs_raw, labels, n_bootstrap=1000, rng=rng_ci)
print(f"\n  各 bin 的 CI（accuracy）：")
for i in range(N_BINS):
    if bins_true["bin_counts"][i] > 0:
        acc = bins_true["bin_accuracies"][i]
        lo = ci_lo[i]
        hi = ci_hi[i]
        width = hi - lo if np.isfinite(lo) and np.isfinite(hi) else float("nan")
        covered = lo <= acc <= hi if np.isfinite(lo) and np.isfinite(hi) else False
        print(f"    bin {i}: acc={acc:.4f}, CI=[{lo:.4f}, {hi:.4f}], width={width:.4f}, 点估计∈CI={covered}")

# 蒙特卡洛覆盖性：对每个bin，多次抽样看CI是否覆盖真值
print("\n  蒙特卡洛覆盖性（200次重抽样，每次算CI，看CI是否包含点估计）...")
n_mc = 200
n_cover = np.zeros(N_BINS)
n_total_valid = np.zeros(N_BINS)
rng_mc = np.random.default_rng(123)
n = len(labels)
confidence = probs_raw.max(axis=1)
correctness = (probs_raw.argmax(axis=1) == labels).astype(float)

for mc in range(n_mc):
    idx = rng_mc.choice(n, n, replace=True)
    sub_probs = probs_raw[idx]
    sub_labels = labels[idx]
    sub_bins = compute_reliability_bins(sub_probs, sub_labels)
    sub_ci_lo, sub_ci_hi = bootstrap_bin_accuracy_ci(
        sub_probs, sub_labels, n_bootstrap=200, rng=rng_mc)
    for i in range(N_BINS):
        if sub_bins["bin_counts"][i] > 0 and np.isfinite(sub_ci_lo[i]) and np.isfinite(sub_ci_hi[i]):
            n_total_valid[i] += 1
            if sub_ci_lo[i] <= sub_bins["bin_accuracies"][i] <= sub_ci_hi[i]:
                n_cover[i] += 1

print(f"  {'bin':<5} {'覆盖次数':<10} {'有效次数':<10} {'覆盖率':<10}")
for i in range(N_BINS):
    if n_total_valid[i] > 0:
        rate = n_cover[i] / n_total_valid[i]
        print(f"  {i:<5} {int(n_cover[i]):<10} {int(n_total_valid[i]):<10} {rate:<10.2%}")


# ============================================================================
# 验证6：空bin处理
# ============================================================================
sep("V6: 空bin处理")

# 构造所有样本都在 bin 9 的情况
probs_concentrated = np.zeros((100, 5))
probs_concentrated[:, 0] = 0.95  # 全部 confidence=0.95 → bin 9
probs_concentrated[:, 1:] = 0.05 / 4
labels_concentrated = np.zeros(100, dtype=int)
labels_concentrated[:50] = 0  # 50个正确
labels_concentrated[50:] = 1  # 50个错误

bins_conc = compute_reliability_bins(probs_concentrated, labels_concentrated)
print(f"  bin_counts = {bins_conc['bin_counts']}")
print(f"  bin_centers = {bins_conc['bin_centers']}")
print(f"  bin_accuracies = {bins_conc['bin_accuracies']}")
print(f"  ECE = {bins_conc['ece']:.6f}")
print(f"  空 bin 数量 = {np.sum(bins_conc['bin_counts'] == 0)}")
print(f"  空 bin 的 bin_centers 是否 nan = {np.all(np.isnan(bins_conc['bin_centers'][bins_conc['bin_counts'] == 0]))}")

# CI 对空 bin
ci_lo_c, ci_hi_c = bootstrap_bin_accuracy_ci(probs_concentrated, labels_concentrated, n_bootstrap=100)
print(f"\n  空 bin 的 CI：")
for i in range(N_BINS):
    if bins_conc["bin_counts"][i] == 0:
        print(f"    bin {i}: ci_lo={ci_lo_c[i]}, ci_hi={ci_hi_c[i]} (期望 nan)")


# ============================================================================
# 验证7：cherry-picking 检查 - 所有种子的ECE
# ============================================================================
sep("V7: cherry-picking 检查 - 所有种子的ECE（ptbxl→chapman, resnet1d）")

print(f"  {'种子':<8} {'ECE_raw':<15} {'ECE_cal':<15} {'ΔECE':<15} {'T':<10}")
seed_eces = []
for seed in SEEDS:
    data = _load_npz("ptbxl", "chapman", "resnet1d", seed)
    if data is None:
        continue
    bins_b = compute_reliability_bins(data["ood_raw"], data["ood_labels"])
    bins_a = compute_reliability_bins(data["ood_cal"], data["ood_labels"])
    delta = bins_b["ece"] - bins_a["ece"]
    seed_eces.append({
        "seed": seed,
        "ece_raw": bins_b["ece"],
        "ece_cal": bins_a["ece"],
        "delta": delta,
        "T": float(data["T"]),
    })
    print(f"  {seed:<8} {bins_b['ece']:<15.6f} {bins_a['ece']:<15.6f} {delta:<+15.6f} {float(data['T']):<10.4f}")

if seed_eces:
    eces_raw = [x["ece_raw"] for x in seed_eces]
    eces_cal = [x["ece_cal"] for x in seed_eces]
    deltas = [x["delta"] for x in seed_eces]
    print(f"\n  ECE_raw: mean={np.mean(eces_raw):.6f}, std={np.std(eces_raw):.6f}, "
          f"min={np.min(eces_raw):.6f}, max={np.max(eces_raw):.6f}")
    print(f"  ECE_cal: mean={np.mean(eces_cal):.6f}, std={np.std(eces_cal):.6f}, "
          f"min={np.min(eces_cal):.6f}, max={np.max(eces_cal):.6f}")
    print(f"  ΔECE:    mean={np.mean(deltas):.6f}, std={np.std(deltas):.6f}, "
          f"min={np.min(deltas):.6f}, max={np.max(deltas):.6f}")
    # seed42 是否是最佳（ΔECE最大）
    seed42_delta = next(x["delta"] for x in seed_eces if x["seed"] == 42)
    rank = sum(1 for x in seed_eces if x["delta"] >= seed42_delta)
    print(f"\n  seed42 的 ΔECE 排名: {rank}/{len(seed_eces)} （1=最佳=ΔECE最大）")
    if rank == 1:
        print(f"  [WARN] seed42 是 ΔECE 最大的种子 → 可能 cherry-picking")
    elif rank == len(seed_eces):
        print(f"  [INFO] seed42 是 ΔECE 最小的种子 → 非 cherry-picking")
    else:
        print(f"  [INFO] seed42 处于中间排名")


# ============================================================================
# 验证8：汇总图标注检查 - "weighted mean ECE" 是否误导
# ============================================================================
sep("V8: 汇总图标注检查")

# 读取汇总图的标注（从代码中提取）
print("  汇总图图例标注（代码 line 466）:")
print("    'Before TS (sample-count weighted mean ECE={ece_before:.3f})'")
print("  汇总图标题（代码 line 489-491）:")
print("    'Summary: 6-direction averaged reliability curve'")
print("    '(curve: bin-count weighted; ECE: sample-count weighted mean; resnet1d, seed42)'")
print()
print(f"  实际加权平均 ECE (before) = {weighted_ece:.6f}")
print(f"  实际全局 ECE (before) = {global_ece:.6f}")
print(f"  差异 = {abs(weighted_ece - global_ece):.6f}")
print(f"  相对差异 = {abs(weighted_ece - global_ece) / global_ece * 100:.2f}%")
print()
print("  攻击点：读者看到 'ECE=0.228' 可能误以为是全局ECE，")
print(f"  但实际全局ECE={global_ece:.6f}，差异 {abs(weighted_ece - global_ece)/global_ece*100:.1f}%")


# ============================================================================
# 验证9：bin_centers 计算 - 是否用边界中点还是样本均值
# ============================================================================
sep("V9: bin_centers 是边界中点还是样本均值")

# 代码 line 183: bin_centers[i] = (boundaries[i] + boundaries[i+1]) / 2.0
# 这是边界中点，不是 bin 内样本的均值 confidence
# 但 bin_confidences 是样本均值 confidence

# 构造测试：bin 5 内有 confidence=0.51 和 0.59
probs_test = np.array([
    [0.51, 0.49, 0, 0, 0],
    [0.59, 0.41, 0, 0, 0],
])
labels_test = np.array([0, 0])
bins_test = compute_reliability_bins(probs_test, labels_test)
print(f"  bin 5 (0.5-0.6):")
print(f"    bin_centers[5] = {bins_test['bin_centers'][5]} (边界中点 = 0.55)")
print(f"    bin_confidences[5] = {bins_test['bin_confidences'][5]} (样本均值 = 0.55)")
print(f"  在此例中两者相同，但若样本不均匀则不同")

# 构造不均匀样本
probs_test2 = np.array([
    [0.51, 0.49, 0, 0, 0],
    [0.51, 0.49, 0, 0, 0],
    [0.51, 0.49, 0, 0, 0],
    [0.59, 0.41, 0, 0, 0],
])
labels_test2 = np.array([0, 0, 0, 0])
bins_test2 = compute_reliability_bins(probs_test2, labels_test2)
print(f"\n  bin 5 (0.5-0.6) 不均匀样本:")
print(f"    bin_centers[5] = {bins_test2['bin_centers'][5]} (边界中点 = 0.55)")
print(f"    bin_confidences[5] = {bins_test2['bin_confidences'][5]:.6f} (样本均值 = 0.53)")
print(f"  → bin_centers 是 x 轴坐标（边界中点），bin_confidences 是用于 ECE 计算的样本均值")


# ============================================================================
# 验证10：ECE 与 transfer_result.json 的 smooth_ece 对比
# ============================================================================
sep("V10: E6 ECE (10-bin) vs transfer_result.json smooth_ece")

# 查找 transfer_result.json
tr_path = _PROJECT_ROOT / "checkpoints" / "transfer" / "ptbxl_chapman" / "resnet1d" / "seed42" / "transfer_result.json"
if tr_path.exists():
    with open(tr_path, "r", encoding="utf-8") as f:
        tr = json.load(f)
    print(f"  transfer_result.json 存在")
    if "methods" in tr and "ts" in tr["methods"]:
        ts = tr["methods"]["ts"]
        if "ood" in ts:
            ood = ts["ood"]
            print(f"  OOD smooth_ece raw = {ood['raw']:.6f}")
            print(f"  OOD smooth_ece cal = {ood['cal']:.6f}")
            print(f"  OOD ΔECE = {ood['deltaECE']:+.6f}")
            print(f"  E6 ECE_raw = {e6_ece_data.get(('ptbxl','chapman'),{}).get('ece_raw',float('nan')):.6f}")
            print(f"  E6 ECE_cal = {e6_ece_data.get(('ptbxl','chapman'),{}).get('ece_cal',float('nan')):.6f}")
            e6_raw = e6_ece_data.get(('ptbxl','chapman'),{}).get('ece_raw',float('nan'))
            e6_cal = e6_ece_data.get(('ptbxl','chapman'),{}).get('ece_cal',float('nan'))
            print(f"  差异 raw = {e6_raw - ood['raw']:+.6f}")
            print(f"  差异 cal = {e6_cal - ood['cal']:+.6f}")
            print(f"  相对差异 raw = {(e6_raw - ood['raw'])/ood['raw']*100:+.2f}%")
            print(f"  相对差异 cal = {(e6_cal - ood['cal'])/ood['cal']*100:+.2f}%")
else:
    print(f"  transfer_result.json 不存在: {tr_path}")


# ============================================================================
# 验证11：bootstrap CI 的 len(col) >= 10 阈值检查
# ============================================================================
sep("V11: bootstrap CI len(col) >= 10 阈值检查")

# 构造一个 bin 只有少量样本的情况
# bin 5 只有 5 个样本
probs_sparse = np.zeros((100, 5))
probs_sparse[:95, 0] = 0.95  # 95个在 bin 9
probs_sparse[:95, 1:] = 0.05 / 4
probs_sparse[95:, 0] = 0.55  # 5个在 bin 5
probs_sparse[95:, 1:] = 0.45 / 4
labels_sparse = np.zeros(100, dtype=int)
labels_sparse[:47] = 0  # bin 9: 47正确
labels_sparse[47:95] = 1  # bin 9: 48错误
labels_sparse[95:] = 0  # bin 5: 5正确

bins_sparse = compute_reliability_bins(probs_sparse, labels_sparse)
print(f"  bin_counts = {bins_sparse['bin_counts']}")
print(f"  bin 5 有 5 个样本")

# 1000次 bootstrap
rng_sparse = np.random.default_rng(0)
ci_lo_s, ci_hi_s = bootstrap_bin_accuracy_ci(probs_sparse, labels_sparse, n_bootstrap=1000, rng=rng_sparse)
print(f"  bin 5 CI: [{ci_lo_s[5]}, {ci_hi_s[5]}] (5个样本，1000次bootstrap)")
print(f"  bin 9 CI: [{ci_lo_s[9]}, {ci_hi_s[9]}] (95个样本，1000次bootstrap)")

# 检查 bin 5 的 CI 是否合理（5个样本全部正确，CI应该很窄且接近1）
if np.isfinite(ci_lo_s[5]) and np.isfinite(ci_hi_s[5]):
    print(f"  bin 5 CI width = {ci_hi_s[5] - ci_lo_s[5]:.4f}")
    print(f"  bin 5 acc = {bins_sparse['bin_accuracies'][5]:.4f}")


# ============================================================================
# 验证12：所有方向所有种子的ECE变异性
# ============================================================================
sep("V12: 所有方向所有种子的ECE变异性（cherry-picking 深度检查）")

print(f"  {'方向':<20} {'种子':<6} {'ECE_raw':<12} {'ECE_cal':<12} {'ΔECE':<12}")
all_delta_by_pair = {}
for source, target in PAIRS:
    all_delta_by_pair[(source, target)] = []
    for seed in SEEDS:
        data = _load_npz(source, target, "resnet1d", seed)
        if data is None:
            continue
        bins_b = compute_reliability_bins(data["ood_raw"], data["ood_labels"])
        bins_a = compute_reliability_bins(data["ood_cal"], data["ood_labels"])
        delta = bins_b["ece"] - bins_a["ece"]
        all_delta_by_pair[(source, target)].append(delta)
        print(f"  {source}→{target:<15} {seed:<6} {bins_b['ece']:<12.6f} {bins_a['ece']:<12.6f} {delta:<+12.6f}")

print(f"\n  各方向 ΔECE 的种子间变异性：")
for pair, deltas in all_delta_by_pair.items():
    if deltas:
        s42 = deltas[0]  # seed42 是第一个
        rank = sum(1 for d in deltas if d >= s42)
        print(f"    {pair[0]}→{pair[1]}: mean={np.mean(deltas):+.6f}, std={np.std(deltas):.6f}, "
              f"seed42 rank={rank}/{len(deltas)}")


# ============================================================================
# 验证13：检查汇总图是否用 bin_centers 而非 bin_confidences 作为 x 轴
# ============================================================================
sep("V13: 汇总图 x 轴使用 bin_centers（边界中点）而非 bin_confidences")

# 代码 line 419: bin_centers = (boundaries[:-1] + boundaries[1:]) / 2.0
# 代码 line 464: ax.plot(bin_centers[valid], avg_before[valid], ...)
# → x 轴是固定的边界中点，不是 bin 内样本均值 confidence
# 这与单方向图（line 310: x = bins["bin_centers"][valid]）一致
# 但 bin_centers 在 compute_reliability_bins 中也是边界中点（line 183）
print("  单方向图 x 轴: bins['bin_centers'][valid]（边界中点，line 310）")
print("  汇总图 x 轴: bin_centers（边界中点，line 419, 464）")
print("  → 两者一致，都是边界中点")
print()
print("  但注意：ECE 计算用的是 bin_confidences（样本均值），不是 bin_centers")
print("  这意味着图中点的 x 坐标（边界中点）与 ECE 计算的 x 坐标（样本均值）不同")
print("  这是可靠性图的标准做法，但可能误导读者")


# ============================================================================
# 验证14：检查 CSV 中 raw_ece_mean 的定义 - 是 smooth_ece 还是 10-bin ECE
# ============================================================================
sep("V14: CSV raw_ece_mean 的定义检查")

# 从 eval_transfer.py 代码看，metric=smooth_ece（line 259-265）
# 所以 CSV 的 raw_ece_mean 是 smooth_ece，不是 10-bin ECE
print("  eval_transfer.py line 259: metric_fn = smooth_ece_gpu if args.gpu_inference else smooth_ece")
print("  → CSV 的 raw_ece_mean 是 smooth_ece（核平滑估计），不是 10-bin ECE")
print("  → E6 图的 ECE 是 10-bin ECE（分箱估计）")
print("  → 两者是不同的估计量，数值不可直接对比")
print()
print("  这是正方承认的语义差异（§2.4），但需检查是否在图中标注")


# ============================================================================
# 验证15：边界情况 - T→0 和 T→∞
# ============================================================================
sep("V15: 边界情况 - 温度 T 极端值")

# 检查实际 T 值范围
all_T = []
for source, target in PAIRS:
    for arch in ARCHS:
        for seed in SEEDS:
            data = _load_npz(source, target, arch, seed)
            if data is not None:
                all_T.append(float(data["T"]))

print(f"  T 值范围: min={min(all_T):.4f}, max={max(all_T):.4f}, mean={np.mean(all_T):.4f}")
print(f"  T < 1 的数量: {sum(1 for t in all_T if t < 1)} (TS 后更自信)")
print(f"  T > 1 的数量: {sum(1 for t in all_T if t > 1)} (TS 后更不自信)")
print(f"  T = 1 的数量: {sum(1 for t in all_T if abs(t - 1) < 1e-6)} (无变化)")

# 检查 T 是否接近边界
if min(all_T) < 0.1:
    print(f"  [WARN] T 接近 0 → TS 后概率接近 one-hot，可能数值不稳定")
if max(all_T) > 50:
    print(f"  [WARN] T 很大 → TS 后概率接近均匀分布")


# ============================================================================
# 总结
# ============================================================================
sep("验证完成")
print("  所有验证已执行。请检查上述输出中的 [MISMATCH], [FATAL], [WARN] 标记。")
