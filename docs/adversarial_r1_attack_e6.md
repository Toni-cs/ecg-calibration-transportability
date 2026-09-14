# E6 可靠性图脚本反方攻击报告

> **反方挑刺代理-E6 交付**。本报告对正方设计的 `scripts/run_e6_reliability_diagrams.py`（648 行）进行逐行审查，寻找数值正确性与可视化规范性方面的逻辑漏洞、隐含假设不成立、边界失效。
> **攻击日期**：2026-09-09
> **攻击对象**：`scripts/run_e6_reliability_diagrams.py`（648 行）+ `docs/Q2_UPGRADE_PROPOSAL_R5.md` §3.2 E6 + `src/utils/calibration.py` + `scripts/eval_transfer.py`
> **攻击代理**：反方挑刺代理-E6（GLM-5.2）
> **诚实原则**：对每一行代码问"这个数值是否正确？这个可视化是否规范？这个假设是否成立？"
> **攻击维度**：反例构造 / 逻辑断链 / 隐含假设 / 边界失效 / 自相矛盾 / 量级错误 / 语义偏移（7 维度全覆盖）

---

## 0. 攻击审查概述

### 攻击点数量统计

| 严重性 | 数量 | 编号 |
|--------|------|------|
| **致命** | 3 | F1, F2, F3 |
| **严重** | 10 | S1-S10 |
| **轻微** | 7 | M1-M7 |
| **合计** | 20 | - |

### 整体评估

E6 脚本的核心问题不是"代码跑不通"，而是"代码与方案文档矛盾 + 可视化数值与主终点语义不一致"。脚本能运行并产出 PDF，但产出的图在以下三个维度存在致命问题：

1. **与 R5 方案文档直接矛盾**（F1）：方案说 15 bin + per-class reliability，代码实现 10 bin + 仅 top-label
2. **图中 ECE 与主终点 smooth_ece 不一致**（F2）：图例标注的 ECE 是 binned top-label ECE，主终点是 smooth_ece，审稿人对比会发现数值对不上
3. **汇总图内部自相矛盾**（F3）：曲线用样本数加权平均，但 ECE 标注用简单算术平均，两者不匹配

**结论**：E6 脚本需要重大修补才能达到"CBM 可发表"的标准。当前版本若直接产出图放入论文，审稿人会发现图与正文数值不一致。

---

## 1. 致命攻击（3 个）

### F1：代码与 R5 方案文档直接矛盾（15 bin vs 10 bin，per-class 缺失，主图选取策略不同）

**攻击维度**：自相矛盾 + 语义偏移

**证据**：

R5 方案 `Q2_UPGRADE_PROPOSAL_R5.md` §3.2 E6（第 401-416 行）明确写道：

> 为 7 个代表迁移对（2 架构家族 × 2 极端 + 1 中位数方向 + 1 超参变体）生成：
> - Reliability diagram（**15 bin**，TS 前后对比）
> - 校准曲线 + 理想对角线
> - **Per-class reliability**

但代码实现：

| 方案文档规定 | 代码实际实现 | 矛盾 |
|-------------|-------------|------|
| 15 bin | `N_BINS = 10`（第 120 行） | **是** |
| Per-class reliability | 仅 top-label（第 156-157 行 `probs.max(axis=1)` / `argmax==labels`） | **是** |
| 7 主图 = 2 架构 × 2 极端 + 1 中位数 + 1 超参变体 | 7 主图 = 6 方向 × 1 rep(seed42, resnet1d) + 1 汇总 | **是** |

**反例构造**：

审稿人阅读论文时，Method 部分引用方案说"15 bin reliability diagram"，但 Supplementary 材料的图明显是 10 bin（x 轴有 10 个点）。审稿人质疑："Method 说 15 bin，图是 10 bin，哪个是对的？" 作者无法回答。

**严重程度**：致命——代码与方案文档的矛盾直接导致论文内部不一致，审稿人必然发现。

**修补建议**：
1. 统一 bin 数量：要么代码改 15 bin，要么方案改 10 bin（需论证为何 10 bin 够用）
2. 实现_per-class reliability 或从方案中删除该承诺
3. 统一主图选取策略：方案描述的"2 架构 × 2 极端 + 1 中位数 + 1 超参变体"与代码的"6 方向 × 1 rep"是不同的选取逻辑

---

### F2：图中 ECE 与主终点 smooth_ece 不一致——审稿人对比会发现数值对不上

**攻击维度**：语义偏移 + 隐含假设

**证据**：

1. E6 图例标注的 ECE（第 327 行）：
```python
f"Before TS (ECE={bins_before['ece']:.3f})"
```
这个 ECE 来自 `compute_reliability_bins`（第 185-188 行），是**binned top-label ECE**：
```python
ece_val = float(np.sum(bin_counts[valid] / n_total *
           np.abs(bin_confidences[valid] - bin_accuracies[valid])))
```

2. 主终点 `eval_transfer.py`（第 259 行）使用的 metric 是 **smooth_ece**：
```python
metric_fn = smooth_ece_gpu if args.gpu_inference else smooth_ece
```

3. `smooth_ece`（`calibration.py` 第 246-296 行）是**核平滑无分箱估计器**，与 binned ECE 是完全不同的数学量：
   - binned ECE = Σ (n_bin/n) · |avg_conf − avg_acc|，依赖分箱
   - smooth_ece = (1/n) Σ_i |Σ_j w_ij·y_j / Σ_j w_ij − p_i|，logit 空间核平滑

**反例构造**：

假设某 checkpoint 的 binned ECE = 0.082，smooth_ece = 0.061（两者差异可达 20-40%，因为 smooth_ece 在 logit 空间核平滑，binned ECE 在概率空间等宽分箱）。

- 论文 Table 3（E3 主终点）报告：smooth_ece_before = 0.061, smooth_ece_after = 0.038, ΔECE = 0.023
- 论文 Figure 5（E6 可靠性图）图例标注：ECE_before = 0.082, ECE_after = 0.045

审稿人问："Table 3 的 ECE 是 0.061，Figure 5 的 ECE 是 0.082，为什么不一样？哪个是对的？" 作者必须承认"用了两个不同的 ECE 估计器"，这会严重削弱论文的可信度。

**隐含假设不成立**：脚本头部 H2（第 14-15 行）声称"top-label 语义与 eval_transfer.py 的 _maxprob / _bin 一致——保证可视化与主终点 ΔECE 同语义"。但 H2 只保证了**top-label 语义**一致（max-prob vs argmax==label），没有保证**ECE 估计器**一致（binned vs smooth）。语义偏移发生在"top-label 语义"→"ECE 估计器"的隐含跳跃。

**严重程度**：致命——这是审稿人必发现的数值不一致，直接损害论文可信度。

**修补建议**：
1. **方案 A（推荐）**：图中 ECE 标注改用 `smooth_ece`（与主终点一致），binned ECE 仅用于绘制曲线点
2. **方案 B**：图中明确标注"ECE (binned, 10 bins)"，并在 caption 中说明"与 Table 3 的 smooth ECE 不同，binned ECE 用于可视化分箱校准曲线"
3. **方案 C**：主终点也改用 binned ECE（不推荐，smooth_ece 有理论优势）

---

### F3：汇总图内部自相矛盾——曲线加权平均但 ECE 标注未加权

**攻击维度**：自相矛盾

**证据**：

`plot_summary` 函数（第 392-475 行）：

1. 可靠性曲线用**样本数加权平均**（第 415-428 行）：
```python
def _weighted_avg(bins_list):
    for i in range(N_BINS):
        for b in bins_list:
            if b["bin_counts"][i] > 0:
                w = b["bin_counts"][i]      # 权重 = bin 内样本数
                total_w += w
                total_wa += w * b["bin_accuracies"][i]
        if total_w > 0:
            acc[i] = total_wa / total_w     # 加权平均
```

2. 但 ECE 标注用**简单算术平均**（第 434-435 行）：
```python
ece_before = np.mean([b["ece"] for b in all_bins_before])  # 未加权！
ece_after = np.mean([b["ece"] for b in all_bins_after])    # 未加权！
```

**反例构造**：

假设 6 个方向的样本数和 ECE 分别为：
- 方向 1: n=2000, ECE=0.05
- 方向 2: n=2000, ECE=0.05
- 方向 3: n=500, ECE=0.15
- 方向 4: n=500, ECE=0.15
- 方向 5: n=2000, ECE=0.05
- 方向 6: n=2000, ECE=0.05

- 加权平均 ECE = (2000×0.05×4 + 500×0.15×2) / 9000 = (400 + 150) / 9000 = **0.061**
- 简单平均 ECE = (0.05×4 + 0.15×2) / 6 = 0.5 / 6 = **0.083**

图例标注 ECE=0.083，但曲线是按加权平均画的（对应 ECE≈0.061）。审稿人从曲线目测的 ECE 与图例标注的 ECE 不一致。

**严重程度**：致命——汇总图是论文主图之一，内部不一致会被审稿人发现。

**修补建议**：ECE 标注也用样本数加权平均：
```python
total_n = sum(b["n_total"] for b in all_bins_before)
ece_before = sum(b["ece"] * b["n_total"] for b in all_bins_before) / total_n
```

---

## 2. 严重攻击（10 个）

### S1：柱状图仅用 TS 前的 bin_counts——TS 改变 max-prob，bin 分布会变

**攻击维度**：隐含假设不成立

**证据**（第 336-337 行）：
```python
# 用 TS 前的 bin_counts 作样本数参考（TS 不改变 argmax，bin 分布近似）
all_cnt = bins_before["bin_counts"]
```

**隐含假设**："TS 不改变 argmax → bin 分布近似"。这个推理是错误的：

- TS 不改变 argmax：✓ 正确（argmax(softmax(logit/T)) = argmax(logit)）
- 但 bin 是基于 `confidence = max(probs)`，**不是** argmax
- TS 改变 `max(probs)`：T>1 时 confidence 下降，T<1 时 confidence 上升
- 因此 TS 后样本会**迁移到不同的 bin**，bin 分布会变

**反例**：假设 T=2.0，所有样本的 raw confidence 在 [0.8, 0.95]（集中在第 9-10 bin）。TS 后 confidence 下降到 [0.6, 0.85]（集中在第 7-9 bin）。柱状图显示第 9-10 bin 样本多，但 TS 后曲线的点在第 7-9 bin——柱状图与 TS 后曲线不对应，视觉上误导。

**严重程度**：严重——柱状图是 bin 样本数的参考，仅显示 TS 前的分布会让审稿人误以为 TS 后曲线也基于相同的样本分布。

**修补建议**：同时显示 TS 前后的柱状图（不同颜色/透明度），或只显示 TS 后的 bin_counts（因为 TS 后曲线是主要分析对象）。

---

### S2：可靠性曲线 x 轴用 bin_centers 而非 bin_confidences——非标准且 x 轴标签错误

**攻击维度**：语义偏移

**证据**（第 304-305 行）：
```python
x = bins["bin_centers"][valid]   # bin 中点（0.05, 0.15, ..., 0.95）
y = bins["bin_accuracies"][valid]
```

但 x 轴标签（第 359 行）：
```python
ax.set_xlabel("Mean predicted confidence (max prob)", fontsize=11)
```

**问题**：
- 标准可靠性图：x = bin 内**平均预测置信度**（bin_confidences），y = bin 内**实际正确率**
- 本代码：x = bin **中点**（bin_centers），y = bin 内实际正确率
- x 轴标签写"Mean predicted confidence"，但实际画的是"Bin center"

**反例**：假设第 5 bin [0.4, 0.5) 内有 100 个样本，平均置信度 = 0.43（偏左）。标准图画 (0.43, accuracy)，本代码画 (0.45, accuracy)。差异不大但系统性地让曲线看起来更"完美"（因为 x 总是均匀间隔的 0.05, 0.15, ...）。

**严重程度**：严重——x 轴标签与实际数据不一致，审稿人对照标准可靠性图定义会发现。

**修补建议**：x 轴改用 `bin_confidences`（已在 `compute_reliability_bins` 中计算但未使用），或 x 轴标签改为"Bin center"。

---

### S3：Bootstrap CI 性能 O(n_bootstrap × n_bins × n)——60 checkpoint 将耗时数小时

**攻击维度**：量级错误

**证据**（第 240-251 行）：
```python
for b in range(n_bootstrap):          # 1000
    idx = rng.choice(n, n, replace=True)
    conf_b = confidence[idx]
    corr_b = correctness[idx]
    for i in range(n_bins):           # 10
        if i == n_bins - 1:
            mask = (conf_b >= boundaries[i]) & (conf_b <= boundaries[i + 1])
        else:
            mask = (conf_b >= boundaries[i]) & (conf_b < boundaries[i + 1])
        if mask.sum() > 0:
            boot_acc[b, i] = float(corr_b[mask].mean())
```

**量级分析**：
- n_bootstrap = 1000, n_bins = 10, n ≈ 5000-10000（OOD test set）
- 每次迭代：rng.choice (O(n)) + 索引 (O(n)) + 10 次 mask (O(n)) + 10 次 mean (O(n))
- 总操作：1000 × 10 × 10000 = **10^8** 次 Python 循环 + numpy 操作
- 每个 checkpoint 预计 30-60 秒，60 checkpoint × 2（before+after）= **60-120 分钟**

且这是**纯 Python 循环**，无法利用 numpy 向量化。

**严重程度**：严重——R5 方案 §7 时间线给 E6 分配 1 周（W5），但仅 CI 计算就可能需要半天。如果需要迭代调试，时间会更长。

**修补建议**：向量化 bootstrap：一次性生成所有重采样索引 `(n_bootstrap, n)`，用 `np.add.at` 或 bincount 计算每 bin 的准确率。或用 `np.random.default_rng().choice` 的 `axis` 参数批量重采样。

---

### S4：RNG 状态污染——CI 依赖图的处理顺序，不可独立复现

**攻击维度**：隐含假设

**证据**（第 671 行 + 第 698 行 + 第 731 行）：
```python
rng = np.random.default_rng(args.rng_seed)   # 全局唯一 RNG
...
# 60 补充图循环中：
bins_b, bins_a, ci_b, ci_a = _compute_bins_and_ci(
    data["ood_raw"], data["ood_cal"], data["ood_labels"], rng)  # rng 状态前进
...
# 6 主图循环中：
bins_b, bins_a, ci_b, ci_a = _compute_bins_and_ci(
    data["ood_raw"], data["ood_cal"], data["ood_labels"], rng)  # rng 状态继续前进
```

**问题**：
- 同一个 `rng` 对象在 60 补充图 + 6 主图中按顺序消费
- 主图的 CI 依赖前面 60 补充图消耗的 RNG 状态
- 如果改变补充图的处理顺序（如只跑 30 个），主图的 CI 会变
- 如果只跑 `--plot` 而之前跑过不同数量的补充图，主图 CI 不可复现

**反例**：
- 场景 A：跑全部 60 补充图 + 6 主图，主图 1 的 CI = [0.3, 0.7]
- 场景 B：只跑 6 主图（注释掉补充图），主图 1 的 CI = [0.2, 0.8]
- 同一份数据、同一个 seed，CI 不同——不可复现

**严重程度**：严重——违反可复现性原则，审稿人复现时可能得到不同的 CI。

**修补建议**：每个图用独立的 RNG（如 `np.random.default_rng(args.rng_seed + hash(source, target, arch, seed))`），或每次调用前 `rng.reset()`。

---

### S5：无 GPU 内存清理——60 checkpoint 顺序加载可能 OOM

**攻击维度**：边界失效

**证据**（`_load_model_and_extract` 第 507-527 行）：
```python
ckpt = torch.load(ckpt_path, weights_only=False, map_location=device)
sd = ckpt["model_state_dict"]
...
model = ECGClassifier(...).to(device)
model.load_state_dict(sd)
...
return {...}  # model 未显式释放
```

**问题**：
- `model` 在函数返回时进入垃圾回收，但 PyTorch GPU 内存的释放不保证即时
- 60 个 checkpoint 顺序加载，GPU 碎片化内存可能累积
- 没有 `del model`、`del ckpt`、`torch.cuda.empty_cache()`
- RTX 5060 8GB（方案硬约束），ResNet1D/InceptionTime 模型本身不大，但 60 次加载的碎片化可能触发 OOM

**严重程度**：严重——在 8GB GPU 上跑 60 次前向推理，内存碎片化是真实风险。

**修补建议**：每次迭代后：
```python
del model, ckpt
torch.cuda.empty_cache()
```

---

### S6：twinx + set_aspect 不一致——两个函数用不同的 adjustable 参数

**攻击维度**：自相矛盾

**证据**：
- `plot_reliability_enhanced`（第 363 行）：`ax.set_aspect("equal", adjustable="datalim")`
- `plot_summary`（第 461 行）：`ax.set_aspect("equal", adjustable="box")`

**问题**：
- `adjustable="datalim"`：调整数据限制以保持纵横比，可能改变 xlim/ylim
- `adjustable="box"`：调整轴框大小以保持纵横比，可能改变图形布局
- 与 `twinx()` 配合时，两者行为不同：
  - `"datalim"` 可能导致 ax 的数据范围被调整，但 ax2 不变 → 柱状图与曲线不对齐
  - `"box"` 可能导致图形变形，twinx 的柱状图比例失真
- 两个函数用不同参数，主图和汇总图的视觉风格不一致

**严重程度**：严重——matplotlib 已知 `twinx + set_aspect` 有兼容性问题，两个函数用不同参数会产出风格不一致的图。

**修补建议**：统一用 `adjustable="datalim"`（对 twin x 更安全），或不用 `set_aspect("equal")` 改用 `fig.set_size_inches` 控制比例。

---

### S7：无 cluster bootstrap——与主终点的患者级 cluster bootstrap 不一致

**攻击维度**：语义偏移

**证据**：
- E6 `bootstrap_bin_accuracy_ci`（第 241 行）：`idx = rng.choice(n, n, replace=True)` —— 简单 bootstrap
- 主终点 `eval_transfer.py`（第 264-265 行）：`clusters=ood_clusters` —— 患者级 cluster bootstrap

**问题**：
- 主终点的 CI 用患者级 cluster bootstrap（消除患者内相关性）
- E6 的 CI 用简单 bootstrap（假设样本独立）
- ECG 数据同一患者的心拍高度相关，简单 bootstrap 会**低估 CI 宽度**
- 脚本头部 A5（第 40-43 行）承认"用 percentile 而非 BCa"，但未提及"用简单 bootstrap 而非 cluster bootstrap"

**严重程度**：严重——CI 宽度被低估，审稿人可能误以为校准效果比实际更显著。

**修补建议**：`bootstrap_bin_accuracy_ci` 增加 `clusters` 参数，支持患者级重采样。

---

### S8：主图重复计算——6 主图的数据在补充图循环中已算过

**攻击维度**：量级错误（效率）

**证据**：
- 补充图循环（第 688-719 行）：对 60 checkpoint 计算 bins + CI，其中 6 个是 rep config
- 主图循环（第 725-746 行）：对同样 6 个 rep config 重新计算 bins + CI

**问题**：
- 6 个 rep config 的 `_compute_bins_and_ci` 被调用两次
- 每次调用 2 × bootstrap_bin_accuracy_ci = 2 × 1000 × 10 × n 次操作
- 浪费约 6 × 2 × 30s = 6 分钟（估计）

**严重程度**：严重——浪费计算资源，且由于 RNG 状态前进（S4），主图的 CI 与补充图中相同 checkpoint 的 CI 不同（因为 RNG 状态不同），造成数据不一致。

**修补建议**：补充图循环中缓存 rep config 的 bins + CI，主图循环直接复用。

---

### S9：float32 存储引入数值误差——npz 中的 probs 与原始 float64 不完全一致

**攻击维度**：边界失效

**证据**（第 568-573 行）：
```python
"id_raw": id_probs.astype(np.float32),    # float64 → float32
"id_cal": id_cal_probs.astype(np.float32),
"id_labels": id_labels.astype(np.int32),
"ood_raw": ood_probs.astype(np.float32),
"ood_cal": ood_cal_probs.astype(np.float32),
```

**问题**：
- 原始 probs 是 float64（softmax 输出）
- 存储为 float32，精度从 ~1e-16 降到 ~1e-7
- 读取后 `compute_reliability_bins` 转回 float64（第 151 行 `np.asarray(probs, dtype=float)`），但精度已损失
- ECE 差异通常在 1e-3 量级，float32 的 1e-7 误差对 ECE 的影响可忽略
- 但 `argmax` 操作对精度敏感：如果两个类的 probs 非常接近，float32 截断可能改变 argmax

**反例**：某样本的 raw probs = [0.40000001, 0.40000002, 0.2]（float64），argmax = 1。存为 float32 后 = [0.4, 0.4, 0.2]，argmax = 0（或 1，取决于 numpy 实现）。correctness 翻转 → ECE 变化。

**严重程度**：严重——虽然概率小，但在 60 checkpoint × 数千样本中，至少一个样本的 argmax 翻转是有可能的。

**修补建议**：存储为 float64（npz 文件增大约 2×，但可靠性图对精度敏感）。

---

### S10：num_classes 不匹配检查缺失——load_state_dict 失败时错误信息不友好

**攻击维度**：边界失效

**证据**（第 528-532 行）：
```python
try:
    model.load_state_dict(sd)
except RuntimeError as e:
    print(f"  [WARN] load_state_dict 失败 ({source}→{target} {arch} seed{seed}): {e}")
    return None
```

对比 `eval_transfer.py`（第 122-126 行）：
```python
ckpt_nc = ckpt.get("num_classes")
if ckpt_nc is not None and ckpt_nc != num_classes:
    raise RuntimeError(
        f"Checkpoint num_classes={ckpt_nc} ≠ 当前 num_classes={num_classes}。"
        f"该 checkpoint 不可复用于此 pair（标签维度不匹配）。")
```

**问题**：
- E6 没有显式检查 `num_classes` 是否匹配
- 如果 checkpoint 是用 5 类训练的，但当前 pair 需要 4 类（如 ptbxl→cpsc），`load_state_dict` 会报 "size mismatch" 错误
- 错误信息不直观，需要解读 PyTorch 的 "Error(s) in loading state_dict" 消息
- 静默返回 None，在 `extract_probs` 中只打印 `[FAIL] 返回 None`，不说明原因

**严重程度**：严重——调试困难，且可能静默跳过本应成功的 checkpoint。

**修补建议**：增加 `num_classes` 显式检查，与 `eval_transfer.py` 一致。

---

## 3. 轻微攻击（7 个）

### M1：ID 数据提取但从未使用——浪费 I/O 和存储

**证据**：`_load_model_and_extract` 提取 `id_raw, id_cal, id_labels, n_id`（第 568-571, 574 行），存入 npz。但 `generate_figures` 只使用 `ood_raw, ood_cal, ood_labels, n_ood, T`（第 698-699, 702-703 行）。ID 数据完全未使用。

**影响**：npz 文件体积翻倍，提取阶段多算一次 TS 应用。

**修补建议**：删除 ID 数据的提取和存储，或在图中也展示 ID reliability curve 作为对比。

---

### M2：npz 无版本/校验——代码变更后旧缓存可能产生错误结果

**证据**：`extract_probs` 检查 `if npz_path.exists() and not args.force_extract`（第 600 行），但无版本号或哈希校验。如果 `compute_reliability_bins` 的分箱逻辑改变，旧 npz 仍被复用，产出的图基于过时数据。

**修补建议**：npz 中存入版本号或代码哈希，加载时校验。

---

### M3：PDF→PNG 路径替换脆弱——路径中含 ".pdf" 会被误替换

**证据**（第 384 行）：
```python
png_path = str(save_path).replace(".pdf", ".png")
```

如果 `save_path` = `paper/figures/my.pdf.reliability.pdf`，`replace(".pdf", ".png")` 会替换第一个 ".pdf" → `paper/figures/my.png.reliability.pdf`（错误）。

**修补建议**：用 `Path(save_path).with_suffix(".png")`。

---

### M4：变量名 ci_val 误导——实际是 bin count 而非 CI 值

**证据**（第 351-356 行）：
```python
for xi, ci_val in zip(bins_before["bin_centers"][valid_cnt],
                      all_cnt[valid_cnt]):
    if ci_val > 0:
        ax2.text(xi, ci_val + max_cnt * 0.02, str(int(ci_val)), ...)
```

`ci_val` 是 bin 内样本数（来自 `all_cnt`），但变量名暗示 "confidence interval value"。

**修补建议**：重命名为 `bin_cnt` 或 `n_in_bin`。

---

### M5：matplotlib.use("Agg") 在函数内部调用——重复调用无效

**证据**（第 291-293 行）：
```python
import matplotlib
matplotlib.use("Agg")  # 无头模式
import matplotlib.pyplot as plt
```

`matplotlib.use()` 必须在 `pyplot` 首次导入前调用。第二次调用 `plot_reliability_enhanced` 时，`pyplot` 已被导入，`matplotlib.use("Agg")` 无效（会打印 warning）。

**修补建议**：在模块顶部调用 `matplotlib.use("Agg")`，或用 `matplotlib.pyplot.switch_backend("Agg")`。

---

### M6：Figure 关闭后返回——返回值无用

**证据**（第 388-389 行）：
```python
plt.close(fig)
return fig
```

`plt.close(fig)` 后 `fig` 已从 pyplot 管理器移除，返回的 `fig` 无法再被显示或保存。调用方 `plot_reliability_enhanced(...)` 不接收返回值，所以无实际影响，但这是代码异味。

**修补建议**：不返回 `fig`，或先返回再关闭。

---

### M7：npz 无 schema 校验——损坏的 npz 导致 KeyError

**证据**（第 649-650 行）：
```python
d = np.load(str(npz_path))
return {k: d[k] for k in d.files}
```

不检查 `d.files` 是否包含 `ood_raw, ood_cal, ood_labels, n_ood, T`。如果 npz 损坏或来自旧版本，后续 `data["ood_raw"]` 会抛 `KeyError`。

**修补建议**：加载后校验必需字段：
```python
required = {"ood_raw", "ood_cal", "ood_labels", "n_ood", "T"}
if not required.issubset(d.files):
    return None
```

---

## 4. 7 维度攻击总结

### 4.1 反例构造

| 攻击点 | 反例 |
|--------|------|
| F2 | binned ECE = 0.082, smooth_ece = 0.061，图与表数值不一致 |
| F3 | 6 方向样本数不均时，加权 ECE = 0.061 ≠ 简单平均 ECE = 0.083 |
| S1 | T=2.0 时 raw confidence [0.8,0.95] → cal confidence [0.6,0.85]，bin 分布完全改变 |
| S9 | probs = [0.40000001, 0.40000002, 0.2] float32 截断后 argmax 翻转 |

### 4.2 逻辑断链

| 攻击点 | 断链 |
|--------|------|
| F2 | H2 假设"top-label 语义一致" → 隐含跳跃到"ECE 估计器一致"（不成立） |
| S1 | "TS 不改变 argmax" → 隐含跳跃到"bin 分布不变"（不成立，bin 基于 max-prob 非 argmax） |

### 4.3 隐含假设

| 攻击点 | 假设 | 不成立条件 |
|--------|------|-----------|
| F2 | 图中 ECE = 主终点 ECE | 主终点用 smooth_ece 而非 binned ECE |
| S1 | TS 不改变 bin 分布 | TS 改变 max-prob → 改变 bin 分布 |
| S4 | RNG 状态独立 | 同一 rng 跨 66 次调用，状态污染 |
| S7 | 样本独立 | ECG 同患者心拍相关 |

### 4.4 边界失效

| 攻击点 | 边界情况 |
|--------|---------|
| S5 | 60 checkpoint 顺序加载，GPU 碎片化累积 |
| S9 | float32 截断改变 argmax |
| S10 | checkpoint num_classes 与当前 pair 不匹配 |
| M7 | npz 损坏或旧版本 |

### 4.5 自相矛盾

| 攻击点 | 矛盾 |
|--------|------|
| F1 | 方案说 15 bin，代码用 10 bin |
| F3 | 曲线加权平均，ECE 标注未加权 |
| S6 | 两个函数用不同 adjustable 参数 |

### 4.6 量级错误

| 攻击点 | 量级 |
|--------|------|
| S3 | O(10^8) Python 循环，60 checkpoint 需 1-2 小时 |
| S8 | 6 个 checkpoint 的 bins+CI 重复计算 |

### 4.7 语义偏移

| 攻击点 | 偏移 |
|--------|------|
| F1 | "per-class reliability" → 仅 top-label |
| F2 | "ECE" 标签 → binned ECE 而非 smooth_ece |
| S2 | "Mean predicted confidence" 标签 → 实际是 bin center |
| S7 | 主终点 cluster bootstrap → E6 简单 bootstrap |

---

## 5. 与 E3 Brier reliability 的一致性分析

**问题**：E6 可靠性图可视化的是 **binned top-label ECE**，而 E3 主终点是 **Brier reliability**（Murphy 分解的 Reliability 分量）。两者是不同的数学量：

| 属性 | E6 图中 ECE | E3 主终点 Brier reliability |
|------|------------|---------------------------|
| 公式 | Σ (n_bin/n)·\|avg_conf − avg_acc\| | Σ (n_bin/n)·(avg_conf − avg_acc)² |
| 分箱 | 10 等宽 bin | 10 等宽 bin（`brier_parts` 硬编码） |
| 概率 | max-prob（top-label） | 1D probs（调用方决定） |
| 估计器 | binned | binned |

**关键差异**：
1. ECE 用**绝对值**，Brier reliability 用**平方**——对同一偏差，数值不同
2. E6 图的 ECE 是 top-label，E3 的 Brier reliability 也应该是 top-label（如果 `brier_parts` 被调用时传入 max-prob 和 correctness）
3. 但 E3 主终点实际用 `smooth_ece` 而非 `brier_parts`——所以 E6 图与 E3 主终点在**估计器层面**就不一致

**审稿人视角**：
- Figure 5（E6）图例标注 "ECE=0.082"
- Table 3（E3）报告 "Brier reliability = 0.015" 或 "smooth ECE = 0.061"
- 审稿人问："Figure 5 的 ECE 和 Table 3 的指标是什么关系？为什么数值差这么多？"
- 作者需要解释三个不同的量：binned ECE、smooth ECE、Brier reliability——这会让审稿人困惑

**严重程度**：严重——E6 的可视化与 E3 主终点不在同一语义空间，削弱了 E6 对 E3 的支撑作用。

**修补建议**：
1. E6 图中同时标注 binned ECE 和 smooth ECE（与主终点一致）
2. 或 E6 图中增加 Brier reliability 的标注（与 E3 主终点一致）
3. 在 figure caption 中明确说明各指标的定义和关系

---

## 6. 代码中实际 Bug 清单

| # | 行号 | Bug | 严重性 |
|---|------|-----|--------|
| 1 | 120 | `N_BINS = 10` 与方案 15 bin 矛盾 | 致命 |
| 2 | 304 | `x = bins["bin_centers"]` 应为 `bin_confidences` | 严重 |
| 3 | 337 | `all_cnt = bins_before["bin_counts"]` TS 后 bin 分布变 | 严重 |
| 4 | 359 | x 轴标签 "Mean predicted confidence" 与实际数据不符 | 严重 |
| 5 | 363, 461 | `adjustable` 参数两个函数不一致 | 严重 |
| 6 | 434-435 | 汇总 ECE 未加权，与加权曲线矛盾 | 致命 |
| 7 | 241 | bootstrap 无 cluster 参数，与主终点不一致 | 严重 |
| 8 | 327 | 图例 ECE 是 binned，主终点是 smooth | 致命 |
| 9 | 568-573 | float32 存储可能改变 argmax | 严重 |
| 10 | 528-532 | 缺 num_classes 显式检查 | 严重 |
| 11 | 384 | `.replace(".pdf", ".png")` 脆弱 | 轻微 |
| 12 | 351 | `ci_val` 变量名误导 | 轻微 |
| 13 | 291 | `matplotlib.use("Agg")` 在函数内 | 轻微 |
| 14 | 388 | `plt.close(fig)` 后 `return fig` | 轻微 |
| 15 | 649 | npz 无 schema 校验 | 轻微 |

---

## 7. 攻击裁决

### 7.1 方案是否可救？

**可救，但需要重大修补**。E6 脚本的核心逻辑（两阶段架构、reliability bin 计算、可视化）是合理的，但有 3 个致命问题必须修复：

1. **F1（代码与方案矛盾）**：必须统一 bin 数量和主图选取策略
2. **F2（ECE 语义不一致）**：必须让图中 ECE 与主终点 smooth_ece 一致，或在 caption 中明确区分
3. **F3（汇总图内部矛盾）**：必须让 ECE 标注与曲线加权方式一致

### 7.2 修补优先级

| 优先级 | 攻击点 | 修补内容 | 工时 |
|--------|--------|---------|------|
| P0 | F1 | 统一 bin 数量（建议改方案为 10 bin，因 10 bin 是 ECE 文献标准） | 0.5 天 |
| P0 | F2 | 图中 ECE 改用 smooth_ece，或明确标注 "binned ECE" | 0.5 天 |
| P0 | F3 | 汇总 ECE 改为加权平均 | 0.5 天 |
| P1 | S1 | 柱状图同时显示 TS 前后 bin_counts | 0.5 天 |
| P1 | S2 | x 轴改用 bin_confidences | 0.5 天 |
| P1 | S3 | 向量化 bootstrap CI | 1 天 |
| P1 | S4 | 每图独立 RNG | 0.5 天 |
| P1 | S7 | 增加 cluster bootstrap 支持 | 1 天 |
| P2 | S5, S9, S10 | GPU 内存清理、float64 存储、num_classes 检查 | 0.5 天 |
| P2 | S6, S8 | 统一 adjustable、复用主图数据 | 0.5 天 |
| P3 | M1-M7 | 代码清理 | 0.5 天 |
| **合计** | - | - | **~6 天** |

### 7.3 最终裁决

**当前 E6 脚本不可直接用于论文**。3 个致命问题（F1/F2/F3）会导致论文内部数值不一致，审稿人必然发现。需要 ~6 天修补（P0+P1+P2+P3）才能达到可发表标准。

R5 方案 §7 时间线给 E6 分配 1 周（W5），修补需要 ~6 天，时间线紧张但可行。建议将 P0 修补（1.5 天）作为必须完成项，P1 修补（3 天）作为应该完成项，P2+P3 作为可选完成项。

---

## 8. 我尝试了全部 7 个攻击维度

| 维度 | 发现攻击点 | 说明 |
|------|-----------|------|
| 反例构造 | F2, F3, S1, S9 | 构造了具体反例使正方结论不成立 |
| 逻辑断链 | F2, S1 | 发现推理链条中未证明的跳跃 |
| 隐含假设 | F2, S1, S4, S7 | 发现未声明的前提条件 |
| 边界失效 | S5, S9, S10, M7 | 发现边界情况下方案崩溃 |
| 自相矛盾 | F1, F3, S6 | 发现方案内部矛盾 |
| 量级错误 | S3, S8 | 发现复杂度被错误估计 |
| 语义偏移 | F1, F2, S2, S7 | 发现概念定义被悄悄替换 |

**攻击结论**：E6 脚本存在 3 个致命攻击 + 10 个严重攻击 + 7 个轻微攻击。致命攻击集中在"代码与方案矛盾"和"数值语义不一致"两个维度。当前脚本不可直接用于论文，需要 ~6 天修补。

---

**报告结束**

E6 可靠性图脚本反方攻击报告完整版。共发现 20 个攻击点（3 致命 + 10 严重 + 7 轻微），核心问题是代码与 R5 方案文档矛盾 + 图中 ECE 与主终点 smooth_ece 不一致 + 汇总图内部自相矛盾。
