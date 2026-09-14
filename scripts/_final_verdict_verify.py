"""终审代理独立验证脚本：验证Attack-7的bin 2 accuracy和bootstrap CI。

验证目标：
1. ptbxl→chapman resnet1d seed42 的 bin 2 样本数、accuracy、correctness值
2. bootstrap CI是否为零宽区间
3. 同时复现ECE计算，确认与正方§5.2表一致
"""
import numpy as np

# 加载NPZ
npz_path = r"D:\A1\ecg-lab-v2\checkpoints\e2_probs_cache\ptbxl_chapman_resnet1d_seed42.npz"
data = np.load(npz_path, allow_pickle=True)
print("=== NPZ keys ===")
print(list(data.keys()))

# 确定probs和labels的key
probs_key = None
labels_key = None
for k in data.keys():
    arr = data[k]
    if arr.ndim == 2 and arr.shape[1] > 1:
        probs_key = k
    elif arr.ndim == 1 and arr.dtype in [np.int32, np.int64, np.intp, np.intc]:
        labels_key = k

print(f"\nprobs_key = {probs_key}, labels_key = {labels_key}")

probs = data[probs_key]
labels = data[labels_key]
print(f"probs.shape = {probs.shape}, labels.shape = {labels.shape}")

# Top-label confidence和correctness（与代码line 160-161一致）
confidence = probs.max(axis=1)
correctness = (probs.argmax(axis=1) == labels).astype(float)
n_total = len(probs)
print(f"n_total = {n_total}")

# 10-bin分箱（与代码line 167-178一致）
n_bins = 10
boundaries = np.linspace(0.0, 1.0, n_bins + 1)
bin_counts = np.zeros(n_bins, dtype=int)
bin_confidences = np.full(n_bins, np.nan)
bin_accuracies = np.full(n_bins, np.nan)
bin_correctness_lists = [[] for _ in range(n_bins)]  # 保存每个bin的correctness值

for i in range(n_bins):
    if i == n_bins - 1:
        mask = (confidence >= boundaries[i]) & (confidence <= boundaries[i + 1])
    else:
        mask = (confidence >= boundaries[i]) & (confidence < boundaries[i + 1])
    cnt = int(mask.sum())
    bin_counts[i] = cnt
    if cnt > 0:
        bin_confidences[i] = float(confidence[mask].mean())
        bin_accuracies[i] = float(correctness[mask].mean())
        bin_correctness_lists[i] = correctness[mask].tolist()

print("\n=== 各bin统计 ===")
print(f"{'bin':>4} {'count':>7} {'conf':>10} {'acc':>10} {'correctness_values':>30}")
for i in range(n_bins):
    vals = bin_correctness_lists[i]
    vals_str = str(vals) if len(vals) <= 10 else f"[{len(vals)} items]"
    print(f"{i:>4} {bin_counts[i]:>7} {bin_confidences[i]:>10.4f} {bin_accuracies[i]:>10.4f} {vals_str:>30}")

# 重点验证bin 2
print("\n=== Attack-7 核心验证：bin 2 ===")
print(f"bin 2 count = {bin_counts[2]}")
print(f"bin 2 accuracy = {bin_accuracies[2]}")
print(f"bin 2 correctness values = {bin_correctness_lists[2]}")
n_correct = int(sum(bin_correctness_lists[2]))
n_total_bin2 = len(bin_correctness_lists[2])
print(f"bin 2 正确数 = {n_correct}/{n_total_bin2}")

# Bootstrap CI验证（与代码line 247-264一致）
rng_seed = 42
n_boot = 1000
confidence_level = 0.95
rng = np.random.default_rng(rng_seed)

# 对bin 2执行bootstrap（正确取bin 2的5个样本，非>=0.2的所有样本）
n = bin_counts[2]
mask_bin2 = (confidence >= boundaries[2]) & (confidence < boundaries[3])
bin2_correctness = correctness[mask_bin2]
print(f"\nbin2_correctness = {bin2_correctness.tolist()}, len = {len(bin2_correctness)}")

boot_acc = np.full(n_boot, np.nan)
for b in range(n_boot):
    idx = rng.choice(n, n, replace=True)
    boot_acc[b] = float(bin2_correctness[idx].mean())

col = boot_acc[np.isfinite(boot_acc)]
alpha = (1.0 - confidence_level) / 2.0
ci_lo = float(np.percentile(col, alpha * 100))
ci_hi = float(np.percentile(col, (1.0 - alpha) * 100))
ci_width = ci_hi - ci_lo

print(f"\nbin 2 bootstrap CI (1000次):")
print(f"  ci_lo = {ci_lo:.4f}")
print(f"  ci_hi = {ci_hi:.4f}")
print(f"  width = {ci_width:.4f}")
print(f"  零宽?  {'是 ← Attack-7成立' if ci_width < 1e-10 else '否 ← Attack-7不成立'}")

# ECE计算（与代码line 188-192一致）
valid = bin_counts > 0
ece_val = float(np.sum(bin_counts[valid] / n_total * np.abs(bin_confidences[valid] - bin_accuracies[valid])))
print(f"\n=== ECE验证 ===")
print(f"ECE_raw (10-bin, top-label) = {ece_val:.6f}")
print(f"正方§5.2声称 ptbxl→chapman ECE_raw = 0.107704")
print(f"差异 = {abs(ece_val - 0.107704):.2e}")

# 结论
print("\n=== 终审独立验证结论 ===")
if bin_accuracies[2] == 1.0 and ci_width < 1e-10:
    print("反方Attack-7成立：bin 2 accuracy=1.0, CI零宽")
    print("→ 反反方OVERRULED裁决有误，应改为SUSTAINED")
elif bin_accuracies[2] < 1.0 and ci_width > 0.01:
    print(f"反方Attack-7不成立：bin 2 accuracy={bin_accuracies[2]:.4f}非1.0, CI宽度={ci_width:.4f}非零")
    print("→ 反反方OVERRULED裁决正确，反方核心证据有事实错误")
else:
    print(f"需进一步调查：accuracy={bin_accuracies[2]:.4f}, CI宽度={ci_width:.4f}")
