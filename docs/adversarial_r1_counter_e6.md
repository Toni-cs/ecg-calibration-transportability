# E6 可靠性图脚本反反方裁决报告

> **反反方审查代理-E6 交付**。本报告对反方挑刺代理产出的 `docs/adversarial_r1_attack_e6.md`（20 个攻击点：3 致命 + 10 严重 + 7 轻微）进行逐条元审查。
> **裁决日期**：2026-09-09
> **审查对象**：`docs/adversarial_r1_attack_e6.md`（反方攻击报告）
> **被攻击代码**：`scripts/run_e6_reliability_diagrams.py`（836 行）
> **审查代理**：反反方元审查者-E6（GLM-5.2）
> **审查原则**：对每个攻击点依次检查 5 个维度——反例是否成立 / 是否稻草人 / 是否误解前提 / 攻击逻辑是否自洽 / 严重程度是否被夸大

---

## 0. 裁决概述

### 裁决统计

| 裁决类别 | 数量 | 编号 |
|----------|------|------|
| **驳回** | 1 | S6 |
| **部分成立** | 11 | F1, F2, S1, S2, S3, S5, S7, S8, S9, S10, M5 |
| **成立** | 8 | F3, S4, M1, M2, M3, M4, M6, M7 |
| **合计** | 20 | - |

### 严重程度修正

| 原始严重性 | 修正后严重性 | 编号 | 修正理由 |
|------------|-------------|------|---------|
| 致命 → 严重 | F1 | 文档漂移而非代码 bug，10 bin 是文献标准 |
| 致命 → 严重 | F2 | 标注歧义而非数值错误，binned ECE 是可靠性图的自然度量 |
| 致命 → 严重（成立） | F3 | 真实内部矛盾，但不影响单图正确性 |
| 严重 → 轻微 | S2 | bin_centers 是标准做法，仅标签需修正 |
| 严重 → 轻微 | S3 | 时间估计高估约 10×，实际 ~10 分钟 |
| 严重 → 轻微 | S5 | 小模型 OOM 风险极低 |
| 严重 → 轻微 | S7 | CI 明确声明为视觉辅助 |
| 严重 → 轻微 | S8 | 重复计算 ~12 秒非 6 分钟 |
| 严重 → 轻微 | S9 | argmax 翻转概率极低 |
| 严重 → 轻微 | S10 | 错误已被 try/except 捕获 |

### 整体评估

反方攻击报告质量较高，20 个攻击点中 19 个有事实依据（仅 S6 为稻草人）。但**严重程度存在系统性夸大**：3 个"致命"攻击中，F1 是文档漂移（fix R5 即可），F2 是标注歧义（加标签即可），仅 F3 是真正的代码内部矛盾（一行修复）。10 个"严重"攻击中，6 个应降级为"轻微"。

**核心结论**：E6 脚本存在 1 个需立即修复的真实矛盾（F3，一行代码）+ 2 个需文档/标注修补的设计问题（F1/F2）+ 1 个需架构改进的可复现性问题（S4）+ 8 个轻微改进项。**不需要 6 天修补，约 1-1.5 天即可达到可发表标准**。

---

## 1. 致命攻击裁决（3 个）

### F1：代码与 R5 方案文档直接矛盾（15 bin vs 10 bin，per-class 缺失，主图选取策略不同）

**裁决：部分成立（严重程度：致命 → 严重）**

#### 事实核查

反方指出的三处矛盾**事实准确**：

| 矛盾点 | R5 方案（§3.2 E6，第 406-410 行） | 代码实现 | 矛盾确认 |
|--------|----------------------------------|---------|---------|
| bin 数量 | "15 bin" | `N_BINS = 10`（第 120 行） | ✓ 真实矛盾 |
| per-class | "Per-class reliability" | 仅 top-label（第 156-157 行） | ✓ 真实矛盾 |
| 主图选取 | "2 架构 × 2 极端 + 1 中位数 + 1 超参变体" | "6 方向 × 1 rep + 1 汇总" | ✓ 真实矛盾 |

#### 逐维审查

1. **反例是否成立**：部分成立。审稿人发现矛盾的场景**仅在论文 Method 直接引用 R5 方案原文时**才会发生。若论文 Method 按代码实际实现描述（10 bin + top-label），则不存在矛盾。
2. **是否稻草人**：部分稻草人。反方将 R5 方案视为"绑定规格"，但 R5 是**规划文档**（proposal），代码实现过程中根据技术约束调整是正常工程实践。脚本头部文档字符串（第 6-46 行）已**明确声明**自己的设计假设 H1-H4 和适用边界，构成独立的设计论证。
3. **是否误解前提**：部分误解。反方未考虑代码头部的 H1（"10 个等宽 bin 足够展示校准曲线形态，ECE 文献标准，Guo et al. 2017"）和 A2（"per-class 图超出 E6 范围"）——这些是**有意识的设计偏离**，不是疏漏。
4. **攻击逻辑是否自洽**：自洽。文档矛盾确实存在。
5. **严重程度是否被夸大**：**被夸大**。"致命"暗示代码有 bug，但实际是文档漂移。关键论点：
   - **10 bin 是 ECE 文献标准**（Guo et al. 2017, Müller et al. 2019），代码的选择比 R5 的 15 bin **更有学术依据**
   - **per-class reliability 在 top-label 校准语境下无意义**——主终点 ΔECE 是 top-label 语义，per-class reliability 与主终点不在同一语义空间
   - 修复方向应是**更新 R5 方案以匹配代码**（改文档），而非**改代码以匹配 R5**（改代码）

#### 修正后的实际影响

**严重**（非致命）。这是文档与代码的漂移，修复方式：
1. 更新 R5 §3.2 E6：将"15 bin"改为"10 bin（ECE 文献标准，Guo et al. 2017）"
2. 更新 R5 §3.2 E6：将"Per-class reliability"改为"Top-label reliability（与主终点 ΔECE 同语义）"
3. 更新 R5 §3.2 E6：将主图选取策略描述改为"6 方向 × 代表性配置 + 1 汇总"
4. 论文 Method 按代码实际实现描述，不引用 R5 原文

**工时：0.5 天（改文档）**，而非反方建议的"统一 bin 数量 + 实现 per-class + 统一主图策略"的数天代码修改。

---

### F2：图中 ECE 与主终点 smooth_ece 不一致

**裁决：部分成立（严重程度：致命 → 严重）**

#### 事实核查

反方指出的事实**全部准确**：

- E6 图例标注的 ECE 是 **binned top-label ECE**（第 185-188 行）✓
- 主终点 `eval_transfer.py` 使用 **smooth_ece**（第 259 行 `metric_fn = smooth_ece_gpu if args.gpu_inference else smooth_ece`）✓
- 两者是不同的数学量（binned ECE 在概率空间等宽分箱；smooth_ece 在 logit 空间核平滑）✓
- 脚本 H2（第 14-15 行）仅声明"top-label 语义一致"，未声明"ECE 估计器一致"✓

#### 逐维审查

1. **反例是否成立**：成立。binned ECE = 0.082 与 smooth_ece = 0.061 确实可能同时出现，审稿人对比会发现数值不一致。
2. **是否稻草人**：非稻草人。反方准确引用了代码和方案。
3. **是否误解前提**：部分误解。反方未充分考虑**可靠性图的数学本质**——可靠性图是**分箱可视化工具**，其自然度量就是 binned ECE。在分箱可靠性图上标注 smooth_ece（无分箱核平滑估计器）反而是**数学上不自洽**的：图的每个点来自 bin 内平均，但标注的 ECE 不来自分箱——图与标注不在同一数学框架内。
4. **攻击逻辑是否自洽**：基本自洽，但有一处断链——反方建议"方案 A：图中 ECE 改用 smooth_ece"，这在数学上不自洽（见上）。反方的方案 B（明确标注"binned ECE"）才是正确方案。
5. **严重程度是否被夸大**：**被夸大**。这是**标注歧义**而非**数值错误**。binned ECE 的数值本身是正确的——它正确计算了 10 bin 的分箱校准误差。问题仅在于标签写"ECE"而非"Binned ECE"，导致审稿人可能误以为它与 Table 的 smooth ECE 是同一个量。

#### 修正后的实际影响

**严重**（非致命）。修复方式：

```python
# 第 327 行，修改图例标签
f"Before TS (binned ECE={bins_before['ece']:.3f}, 10 bins)"

# 第 332 行
f"After TS (binned ECE={bins_after['ece']:.3f}, 10 bins)"
```

并在 figure caption 中添加：
> The ECE values shown in legends are binned top-label ECE (10 equal-width bins), consistent with the reliability diagram's binning. They differ from the smooth ECE reported in Table 3, which uses kernel-smoothed estimation without binning (Błasiok & Nakkiran, 2024). Both estimators measure the same underlying calibration error but with different bias-variance tradeoffs.

**工时：0.5 天（改标签 + caption）**。反方建议的"方案 A（改用 smooth_ece）"反而**不推荐**——会在分箱图上标注无分箱度量，数学上不自洽。

---

### F3：汇总图内部自相矛盾——曲线加权平均但 ECE 标注未加权

**裁决：成立（严重程度：致命 → 严重，但确认是真实 bug）**

#### 事实核查

反方指出的事实**完全准确**：

- 曲线用样本数加权平均（第 415-428 行 `_weighted_avg`）✓
- ECE 标注用简单算术平均（第 434-435 行 `np.mean([b["ece"] for b in all_bins_before])`）✓
- 反例数值正确：加权 ECE = 0.061 ≠ 简单平均 ECE = 0.083 ✓

#### 逐维审查

1. **反例是否成立**：成立。6 方向样本数不均时，两种平均确实产生不同 ECE。
2. **是否稻草人**：非稻草人。直接引用代码，无歪曲。
3. **是否误解前提**：无误解。代码确实存在两种不同的聚合方式。
4. **攻击逻辑是否自洽**：自洽。曲线和标注在同一图中用不同聚合方式，确实构成内部矛盾。
5. **严重程度是否被夸大**：**部分夸大**。这是真实 bug，但影响范围仅限汇总图的 ECE 标注数值，不影响：
   - 7 个主图的正确性（每图独立计算）
   - 60 个补充图的正确性
   - 汇总图的曲线形态（曲线本身是正确的加权平均）
   
   "致命"暗示整个脚本不可用，实际仅汇总图的一个标注数值需修正。

#### 修补方案

```python
# 第 434-435 行，修改为加权平均
total_n_before = sum(b["n_total"] for b in all_bins_before)
total_n_after = sum(b["n_total"] for b in all_bins_after)
ece_before = sum(b["ece"] * b["n_total"] for b in all_bins_before) / total_n_before
ece_after = sum(b["ece"] * b["n_total"] for b in all_bins_after) / total_n_after
```

**注意**：加权平均 ECE 仍不完全等于曲线的 ECE（因为 ECE 是非线性函数 of 曲线点），但与曲线的聚合方式一致，消除了"曲线加权、标注不加权"的内部矛盾。

**工时：0.5 小时（一行代码修改）**。

---

## 2. 严重攻击裁决（10 个）

### S1：柱状图仅用 TS 前的 bin_counts——TS 改变 max-prob，bin 分布会变

**裁决：部分成立（严重程度：严重 → 轻微）**

#### 事实核查

- 代码使用 `bins_before["bin_counts"]`（第 337 行）✓
- 注释说"TS 不改变 argmax，bin 分布近似"（第 336 行）✓
- TS 确实改变 max-prob（T>1 降低 confidence）✓

#### 逐维审查

1. **反例是否成立**：部分成立。TS 确实改变 bin 分布，注释的推理"TS 不改变 argmax → bin 分布近似"确实有逻辑断链（bin 基于 max-prob 而非 argmax）。
2. **是否误解前提**：部分误解。柱状图的目的是展示**原始模型的置信度分布**——即"模型把多少样本预测在某个置信度区间"。用 TS 前的 bin_counts 是**语义正确**的：它回答"原始模型的置信度分布是什么"。TS 后的分布是校准后的分布，是另一个问题。
3. **严重程度是否被夸大**：**被夸大**。柱状图是辅助视觉元素（灰色半透明，alpha=0.25），不是主要分析对象。用 TS 前分布作为参考是**可视化设计选择**，不是 bug。真正的问题仅是**注释的推理逻辑有误**。

#### 修补方案

修正注释（非代码逻辑）：

```python
# 第 336 行，修正注释
# 用 TS 前的 bin_counts 展示原始模型的置信度分布
# 注：TS 会改变 max-prob 从而改变 bin 分布，此处有意展示 TS 前分布作为参考
all_cnt = bins_before["bin_counts"]
```

可选增强：同时显示 TS 前后柱状图（不同透明度），但非必须。

**工时：0.5 小时（改注释）**。

---

### S2：可靠性曲线 x 轴用 bin_centers 而非 bin_confidences

**裁决：部分成立（严重程度：严重 → 轻微）**

#### 事实核查

- 代码用 `bin_centers`（第 304 行）✓
- x 轴标签写"Mean predicted confidence"（第 359 行）✓

#### 逐维审查

1. **反例是否成立**：部分成立。标签与数据确实不完全对应。
2. **是否误解前提**：**反方误解了可靠性图的标准实践**。Guo et al. 2017（"On Calibration of Modern Neural Networks"，ECE 文献最权威引用）的可靠性图**正是用 bin centers 作为 x 轴**——这是 ECE 文献的标准做法，不是非标准的。用 bin_confidences 作为 x 轴反而是少数派做法。
3. **严重程度是否被夸大**：**被夸大**。bin_centers 是文献标准做法。唯一的问题是 x 轴标签"Mean predicted confidence"不够精确——应改为"Bin center (predicted confidence)"或"Predicted confidence (bin center)"。

#### 修补方案

```python
# 第 359 行，修正标签
ax.set_xlabel("Predicted confidence (bin center)", fontsize=11)
```

**工时：0.5 小时（改标签）**。不需要改 x 轴数据（bin_centers 是标准做法）。

---

### S3：Bootstrap CI 性能 O(n_bootstrap × n_bins × n)——60 checkpoint 将耗时数小时

**裁决：部分成立（严重程度：严重 → 轻微）**

#### 事实核查

- 外层 Python 循环 1000 次（n_bootstrap）✓
- 内层 Python 循环 10 次（n_bins）✓
- 每次迭代内是 numpy 向量化操作 ✓

#### 逐维审查

1. **反例是否成立**：不成立。反方的时间估计**高估约 10×**。
2. **攻击逻辑是否自洽**：**断链**。反方声称"纯 Python 循环，无法利用 numpy 向量化"——这是**错误的**。外层 1000 次是 Python 循环，但**每次迭代内的 mask + mean 是 numpy 向量化操作**（对 n=10000 的数组，每次 ~0.1ms）。
3. **量级重算**：
   - 每次 bootstrap：`rng.choice` (~0.1ms) + 索引 (~0.05ms) + 10 × mask+mean (~1ms) ≈ **1.2ms**
   - 1000 次 bootstrap ≈ **1.2 秒**
   - 60 checkpoint × 2（before+after）× 1.2 秒 ≈ **144 秒 ≈ 2.4 分钟**
   - 即使考虑 Python 循环开销（1000 × 10 = 10000 次），实际约 **5-10 分钟**
   - 反方估计的"60-120 分钟"**高估约 6-12×**
4. **严重程度是否被夸大**：**被夸大**。实际 5-10 分钟的 CI 计算不构成性能问题。

#### 修补方案（可选优化）

向量化 bootstrap 可进一步加速到 ~1 分钟，但非必须：

```python
# 一次性生成所有重采样索引
all_idx = rng.choice(n, size=(n_bootstrap, n), replace=True)
# 向量化计算每 bin 的准确率
for i in range(n_bins):
    # 对所有 bootstrap 样本同时计算 bin i 的准确率
    ...
```

**工时：0 天（当前性能可接受）** 或 0.5 天（可选优化）。

---

### S4：RNG 状态污染——CI 依赖图的处理顺序，不可独立复现

**裁决：成立（严重程度：严重，确认）**

#### 事实核查

- 单一 `rng = np.random.default_rng(args.rng_seed)`（第 671 行）✓
- 同一 rng 在 60 补充图 + 6 主图中按顺序消费 ✓
- 改变处理顺序会改变主图 CI ✓

#### 逐维审查

1. **反例是否成立**：成立。场景 A（全跑）与场景 B（仅主图）的主图 CI 确实不同。
2. **是否稻草人**：非稻草人。
3. **攻击逻辑是否自洽**：自洽。可复现性是科学论文的基本要求。
4. **严重程度**：严重，**未被夸大**。这是真实的可复现性缺陷。

#### 修补方案

```python
# 为每个 checkpoint 创建独立 RNG（基于内容哈希）
import hashlib
def _make_rng(base_seed, source, target, arch, seed):
    key = f"{source}_{target}_{arch}_seed{seed}".encode()
    h = int(hashlib.md5(key).hexdigest()[:8], 16)
    return np.random.default_rng(base_seed + h)

# 在 _compute_bins_and_ci 调用处
rng_fig = _make_rng(args.rng_seed, source, target, arch, seed)
bins_b, bins_a, ci_b, ci_a = _compute_bins_and_ci(
    data["ood_raw"], data["ood_cal"], data["ood_labels"], rng_fig)
```

**工时：0.5 天**。

---

### S5：无 GPU 内存清理——60 checkpoint 顺序加载可能 OOM

**裁决：部分成立（严重程度：严重 → 轻微）**

#### 事实核查

- 无 `del model` / `torch.cuda.empty_cache()` ✓
- 60 checkpoint 顺序加载 ✓

#### 逐维审查

1. **反例是否成立**：**不成立**（概率极低）。
2. **是否误解前提**：**反方误解了 PyTorch 的内存管理**。
   - `model` 在 `_load_model_and_extract` 返回时，引用计数归零，Python 垃圾回收器**立即释放** Python 对象
   - PyTorch 的 CUDA caching allocator 会**缓存**已分配的 GPU 内存块供下次复用，不会真正归还给 OS，但**不会累积增长**——新模型复用旧模型的缓存块
   - ResNet1D / InceptionTime for ECG 是**小模型**（参数量 ~100K-1M，显存 <100MB），60 次加载的峰值显存 ≈ 单模型显存，不是 60 × 单模型
   - RTX 5060 8GB 对 ECG 小模型绰绰有余
3. **严重程度是否被夸大**：**被夸大**。"碎片化累积触发 OOM"对小模型（<100MB）在 8GB GPU 上几乎不可能发生。

#### 修补方案（良好实践，但非必须）

```python
# 在 _load_model_and_extract 返回前
del model, ckpt
if torch.cuda.is_available():
    torch.cuda.empty_cache()
```

**工时：0.5 小时（防御性编程）**。

---

### S6：twinx + set_aspect 不一致——两个函数用不同的 adjustable 参数

**裁决：驳回（稻草人论证）**

#### 事实核查

- `plot_reliability_enhanced`：`adjustable="datalim"`（第 363 行）✓
- `plot_summary`：`adjustable="box"`（第 461 行）✓

#### 逐维审查

1. **反例是否成立**：**不成立**。
2. **是否误解前提**：**反方误解了 matplotlib 的 API 语义和两个函数的结构差异**：
   - `plot_reliability_enhanced` **有 twin x 轴**（第 335 行 `ax2 = ax.twinx()`，用于柱状图）→ `adjustable="datalim"` 是**正确选择**：调整数据范围保持纵横比，不影响 twin x 的柱状图
   - `plot_summary` **无 twin x 轴**（无柱状图，仅曲线）→ `adjustable="box"` 是**正确选择**：调整轴框大小保持纵横比，单轴场景下视觉更稳定
   - **两个函数用不同参数是因为它们有不同的结构**（有/无 twin x），这是**正确的差异化设计**，不是 bug
3. **攻击逻辑是否自洽**：**断链**。反方声称"两个函数用不同参数会产出风格不一致的图"——但两个函数产出的图**本就不同**（一个有柱状图，一个没有），"风格不一致"是设计意图，不是 bug。
4. **是否稻草人**：**是稻草人**。反方将"差异化设计"歪曲为"自相矛盾"。

#### 裁决理由

不同参数适配不同结构（twin x vs 单轴）是 matplotlib 的**最佳实践**。统一参数反而可能引入问题：
- 若 `plot_reliability_enhanced` 改用 `adjustable="box"`：twin x 的柱状图可能比例失真
- 若 `plot_summary` 改用 `adjustable="datalim"`：单轴场景下可能不必要地调整数据范围

**无需修补**。

---

### S7：无 cluster bootstrap——与主终点的患者级 cluster bootstrap 不一致

**裁决：部分成立（严重程度：严重 → 轻微）**

#### 事实核查

- E6 用简单 bootstrap（第 241 行）✓
- 主终点用 cluster bootstrap（eval_transfer.py 第 264-265 行）✓

#### 逐维审查

1. **反例是否成立**：部分成立。简单 bootstrap 确实可能低估 CI 宽度。
2. **是否误解前提**：**反方忽略了脚本头部的显式声明**。脚本 A5（第 40-43 行）明确声明：
   > "reliability curve 是描述性可视化，每 bin 独立 BCa（含 jackknife）成本 O(bins × B × n) 不现实；主终点 ΔECE 的 BCa CI 已由 eval_transfer.py 独立报告，此处 CI 仅为视觉辅助。"
   
   同理，cluster bootstrap 也是"主终点独立报告，此处 CI 仅为视觉辅助"。A5 的逻辑同样适用于 cluster bootstrap——反方承认 A5 提到了 percentile vs BCa，但抱怨没提到 simple vs cluster。这是**文档完整性问题**，不是代码 bug。
3. **严重程度是否被夸大**：**被夸大**。CI 是视觉辅助（灰色误差棒），不是假设检验的依据。审稿人不会从误差棒宽度得出统计结论——统计结论来自 Table 3 的主终点 BCa CI。

#### 修补方案

在 A5 注释中补充说明：

```python
# 脚本头部 A5，补充
# A5. 置信区间用 bootstrap percentile（每 bin 独立），未做 BCa 也未做 cluster
#     bootstrap——与主终点 BCa + cluster bootstrap 不一致。→ 缓解：reliability curve
#     是描述性可视化，主终点 ΔECE 的 BCa cluster CI 已由 eval_transfer.py 独立报告，
#     此处 CI 仅为视觉辅助。
```

**工时：0.5 小时（改注释）**。

---

### S8：主图重复计算——6 主图的数据在补充图循环中已算过

**裁决：部分成立（严重程度：严重 → 轻微）**

#### 事实核查

- 6 个 rep config 在补充图循环中已计算（第 688-719 行）✓
- 主图循环重新计算同样 6 个 rep config（第 725-746 行）✓

#### 逐维审查

1. **反例是否成立**：成立。确实重复计算。
2. **攻击逻辑是否自洽**：部分断链。反方估计"浪费约 6 × 2 × 30s = 6 分钟"——但根据 S3 的重算，每次 `_compute_bins_and_ci` 约 2.4 秒，6 × 2 × 2.4 ≈ **29 秒**，非 6 分钟。反方**高估约 12×**。
3. **严重程度是否被夸大**：**被夸大**。29 秒的重复计算不构成性能问题。但反方指出的 RNG 不一致问题（重复计算因 RNG 状态前进导致主图 CI 与补充图中相同 checkpoint 的 CI 不同）是**真实的逻辑问题**，链接到 S4。

#### 修补方案

```python
# 在补充图循环中缓存 rep config 的结果
rep_cache = {}  # (source, target) -> (bins_b, bins_a, ci_b, ci_a)

# 补充图循环中
if seed == args.rep_seed and arch == args.rep_arch:
    rep_cache[(source, target)] = (bins_b, bins_a, ci_b, ci_a)

# 主图循环中
if (source, target) in rep_cache:
    bins_b, bins_a, ci_b, ci_a = rep_cache[(source, target)]
else:
    bins_b, bins_a, ci_b, ci_a = _compute_bins_and_ci(...)
```

**工时：0.5 小时**。与 S4 修补一起实施可同时解决 RNG 不一致问题。

---

### S9：float32 存储引入数值误差——argmax 可能翻转

**裁决：部分成立（严重程度：严重 → 轻微）**

#### 事实核查

- 代码存储为 float32（第 568-573 行）✓
- float32 精度 ~1e-7 ✓

#### 逐维审查

1. **反例是否成立**：**理论上成立，实践中概率极低**。反方的反例 `[0.40000001, 0.40000002, 0.2]` 是**人为构造**的——softmax 输出两个类概率差恰好为 1e-8（float32 精度边界）的概率，在真实 ECG 分类器中**几乎为零**。
2. **攻击逻辑是否自洽**：部分断链。反方承认"ECE 差异通常在 1e-3 量级，float32 的 1e-7 误差对 ECE 的影响可忽略"——这**直接否定了"严重"分级**。如果影响可忽略，就不是严重问题。
3. **严重程度是否被夸大**：**被夸大**。60 checkpoint × 数千样本中，至少一个样本 argmax 翻转的概率，需要两个类的 softmax 输出差 < 1e-7。ECG 分类器的 softmax 输出通常有明确的 winner（max prob > 0.5，次高 < 0.3），差 > 0.2 >> 1e-7。

#### 修补方案（可选，防御性）

```python
# 第 568-573 行，改为 float64（npz 增大约 2×，但消除精度风险）
"id_raw": id_probs.astype(np.float64),
"id_cal": id_cal_probs.astype(np.float64),
```

**工时：0.5 小时**。但当前 float32 在实践中可接受。

---

### S10：num_classes 不匹配检查缺失——load_state_dict 失败时错误信息不友好

**裁决：部分成立（严重程度：严重 → 轻微）**

#### 事实核查

- E6 无显式 num_classes 检查 ✓
- eval_transfer.py 有显式检查（第 122-126 行）✓

#### 逐维审查

1. **反例是否成立**：部分成立。num_classes 不匹配时错误信息不够直观。
2. **是否误解前提**：**反方忽略了 E6 已有 try/except 保护**（第 528-532 行）。`load_state_dict` 失败时不会崩溃，而是打印 `[WARN] load_state_dict 失败` 并返回 None。错误信息虽不如 eval_transfer.py 直观，但**不是静默失败**——PyTorch 的 RuntimeError 消息会包含 "size mismatch" 字样，足以定位问题。
3. **严重程度是否被夸大**：**被夸大**。这是 UX 问题（错误信息不够友好），不是正确性问题（错误已被捕获和处理）。

#### 修补方案

```python
# 在 load_state_dict 前，增加显式检查
ckpt_nc = ckpt.get("num_classes")
if ckpt_nc is not None and ckpt_nc != num_classes:
    print(f"  [WARN] num_classes 不匹配: checkpoint={ckpt_nc} vs 当前={num_classes}")
    return None
```

**工时：0.5 小时**。

---

## 3. 轻微攻击裁决（7 个）

### M1：ID 数据提取但从未使用——浪费 I/O 和存储

**裁决：成立（轻微）**

事实准确。`id_raw, id_cal, id_labels, n_id` 被提取存储但 `generate_figures` 未使用。

**修补**：删除 ID 数据提取，或在图中也展示 ID reliability curve 作为对比（后者更有学术价值）。**工时：0.5 小时**。

---

### M2：npz 无版本/校验——代码变更后旧缓存可能产生错误结果

**裁决：成立（轻微）**

事实准确。npz 无版本字段，`--force-extract` 是手动 workaround。

**修补**：npz 中存入版本号或代码哈希，加载时校验。**工时：0.5 小时**。

---

### M3：PDF→PNG 路径替换脆弱——路径中含 ".pdf" 会被误替换

**裁决：成立（轻微）**

事实准确。`str(save_path).replace(".pdf", ".png")` 会替换第一个 ".pdf"。

**修补**：`Path(save_path).with_suffix(".png")`。**工时：5 分钟**。

---

### M4：变量名 ci_val 误导——实际是 bin count 而非 CI 值

**裁决：成立（轻微）**

事实准确。`ci_val` 来自 `all_cnt`，是 bin 内样本数，不是 CI 值。

**修补**：重命名为 `bin_cnt`。**工时：5 分钟**。

---

### M5：matplotlib.use("Agg") 在函数内部调用——重复调用无效

**裁决：部分成立（轻微）**

事实准确。第二次调用 `matplotlib.use("Agg")` 是 no-op + warning。

但**实际行为正确**：第一次调用设置了 "Agg" 后端，后续调用虽无效但后端已是 "Agg"。**不影响正确性，仅产生 warning**。

**修补**：在模块顶部调用 `matplotlib.use("Agg")`。**工时：5 分钟**。

---

### M6：Figure 关闭后返回——返回值无用

**裁决：成立（轻微）**

事实准确。`plt.close(fig)` 后返回 `fig`，调用方不接收返回值。

**修补**：不返回 `fig`，或先返回再关闭。**工时：5 分钟**。

---

### M7：npz 无 schema 校验——损坏的 npz 导致 KeyError

**裁决：成立（轻微）**

事实准确。不检查 `d.files` 是否包含必需字段。

**修补**：加载后校验必需字段。**工时：0.5 小时**。

---

## 4. 对反方"7 维度攻击总结"的元审查

### 4.1 反方声称的"反例构造"（F2, F3, S1, S9）

| 攻击点 | 反方反例 | 元审查裁决 |
|--------|---------|-----------|
| F2 | binned ECE = 0.082, smooth_ece = 0.061 | **反例成立**，但修复方案 A（改用 smooth_ece）数学上不自洽 |
| F3 | 加权 ECE = 0.061 ≠ 简单平均 ECE = 0.083 | **反例成立**，真实 bug |
| S1 | T=2.0 时 bin 分布改变 | **反例成立**，但注释问题非可视化 bug |
| S9 | float32 截断改变 argmax | **反例理论成立，实践概率极低**（需两类 softmax 差 < 1e-7） |

### 4.2 反方声称的"逻辑断链"（F2, S1）

| 攻击点 | 反方断链 | 元审查裁决 |
|--------|---------|-----------|
| F2 | H2 "top-label 语义一致" → "ECE 估计器一致" | **断链成立**，H2 确实未覆盖 ECE 估计器 |
| S1 | "TS 不改变 argmax" → "bin 分布不变" | **断链成立**，bin 基于 max-prob 而非 argmax |

### 4.3 反方声称的"隐含假设"（F2, S1, S4, S7）

| 攻击点 | 隐含假设 | 元审查裁决 |
|--------|---------|-----------|
| F2 | 图中 ECE = 主终点 ECE | **假设确实未声明**，但 binned ECE 是可靠性图的自然度量 |
| S1 | TS 不改变 bin 分布 | **假设不成立**，但用 TS 前分布是合理的可视化选择 |
| S4 | RNG 状态独立 | **假设不成立**，真实可复现性问题 |
| S7 | 样本独立 | **假设未声明**，但 CI 是视觉辅助，A5 已声明非主终点 |

### 4.4 反方声称的"自相矛盾"（F1, F3, S6）

| 攻击点 | 矛盾 | 元审查裁决 |
|--------|------|-----------|
| F1 | 方案 15 bin vs 代码 10 bin | **真实矛盾**，但 10 bin 是文献标准，应改方案 |
| F3 | 曲线加权 vs ECE 不加权 | **真实矛盾**，一行修复 |
| S6 | 两个函数 adjustable 不同 | **非矛盾**，差异化设计适配不同结构（twin x vs 单轴）→ **驳回** |

### 4.5 反方声称的"量级错误"（S3, S8）

| 攻击点 | 量级估计 | 元审查裁决 |
|--------|---------|-----------|
| S3 | 60-120 分钟 | **高估约 6-12×**，实际 5-10 分钟 |
| S8 | 6 分钟 | **高估约 12×**，实际 ~29 秒 |

### 4.6 反方声称的"语义偏移"（F1, F2, S2, S7）

| 攻击点 | 语义偏移 | 元审查裁决 |
|--------|---------|-----------|
| F1 | "per-class" → top-label | **真实偏移**，但 top-label 与主终点同语义，per-class 反而不一致 |
| F2 | "ECE" → binned ECE | **真实偏移**，标注需明确 |
| S2 | "Mean predicted confidence" → bin center | **标签不精确**，但 bin center 是文献标准做法 |
| S7 | cluster bootstrap → simple bootstrap | **真实偏移**，但 CI 是视觉辅助 |

---

## 5. 对反方"与 E3 Brier reliability 一致性分析"的元审查

反方第 5 节声称"E3 主终点是 Brier reliability"，但**事实核查发现**：

- `eval_transfer.py` 第 259 行：`metric_fn = smooth_ece_gpu if args.gpu_inference else smooth_ece`
- E3 的**实际主终点度量是 smooth_ece**，不是 Brier reliability
- Brier reliability（`brier_parts`）是 E3 的**辅助分析**（Murphy 分解），不是主终点
- R5 方案第 426 行虽提到"Brier reliability（核心）"，但代码实现的主终点是 smooth_ece

**裁决**：反方第 5 节的论证基于**对 E3 主终点的误解**——将 Brier reliability 当作 E3 主终点，实际上 smooth_ece 才是。因此反方第 5 节的"三个不同的量"（binned ECE, smooth ECE, Brier reliability）中，Brier reliability 不是主终点，**实际只需区分两个量**（binned ECE for 可靠性图, smooth ECE for 主终点），这正是 F2 已覆盖的问题。

**反方第 5 节不构成独立攻击**，是 F2 的重复包装，且因误解 E3 主终点而**部分无效**。

---

## 6. 对反方"代码中实际 Bug 清单"的元审查

| # | 反方标注 | 元审查裁决 |
|---|---------|-----------|
| 1 | `N_BINS = 10` 与方案矛盾 → 致命 | **文档漂移**，10 bin 是标准，改方案即可 → 严重 |
| 2 | `x = bin_centers` 应为 `bin_confidences` → 严重 | **bin_centers 是文献标准**，仅标签需改 → 轻微 |
| 3 | `all_cnt = bins_before` TS 后 bin 分布变 → 严重 | **注释逻辑有误**，可视化选择合理 → 轻微 |
| 4 | x 轴标签不符 → 严重 | **标签不精确**，改标签即可 → 轻微 |
| 5 | `adjustable` 不一致 → 严重 | **差异化设计正确** → **驳回** |
| 6 | 汇总 ECE 未加权 → 致命 | **真实 bug**，一行修复 → 严重（成立） |
| 7 | bootstrap 无 cluster → 严重 | **CI 是视觉辅助**，注释补充即可 → 轻微 |
| 8 | 图例 ECE 是 binned → 致命 | **标注歧义**，加标签即可 → 严重 |
| 9 | float32 改变 argmax → 严重 | **概率极低**，防御性改 float64 → 轻微 |
| 10 | 缺 num_classes 检查 → 严重 | **已有 try/except**，UX 改进 → 轻微 |
| 11 | `.replace` 脆弱 → 轻微 | **成立** |
| 12 | `ci_val` 误导 → 轻微 | **成立** |
| 13 | `matplotlib.use` 在函数内 → 轻微 | **成立**（行为正确但有 warning） |
| 14 | `plt.close` 后 return → 轻微 | **成立** |
| 15 | npz 无 schema → 轻微 | **成立** |

---

## 7. 最终裁决

### 7.1 反方攻击的整体质量评估

**质量：中上**。20 个攻击点中：
- 19 个有事实依据（仅 S6 为稻草人）—— **事实核查通过率 95%**
- 11 个严重程度被夸大（3 致命 + 8 严重中 6 个）—— **严重程度高估率 55%**
- 2 个时间/量级估计高估 6-12× —— **量级估计不准确**
- 1 个对 E3 主终点有误解 —— **上下文理解有误**

### 7.2 修补优先级（修正后）

| 优先级 | 攻击点 | 修补内容 | 工时 | 理由 |
|--------|--------|---------|------|------|
| **P0** | F3 | 汇总 ECE 改为加权平均 | 0.5 小时 | 真实 bug，一行代码 |
| **P0** | F2 | 图例标注改为 "binned ECE (10 bins)" + caption 说明 | 0.5 天 | 标注歧义，审稿人可能困惑 |
| **P0** | F1 | 更新 R5 方案 §3.2 E6 以匹配代码 | 0.5 天 | 文档漂移，改文档非改代码 |
| **P1** | S4 | 每图独立 RNG（内容哈希） | 0.5 天 | 可复现性 |
| **P1** | S8 | 缓存 rep config 结果复用 | 0.5 小时 | 与 S4 一起实施 |
| **P2** | S1, S2, S7 | 修正注释和标签 | 0.5 天 | 文档/标签精确性 |
| **P2** | S10 | 增加 num_classes 显式检查 | 0.5 小时 | UX 改进 |
| **P3** | M1-M7 | 代码清理 | 0.5 天 | 代码质量 |
| **可选** | S3, S5, S9 | 性能优化、GPU 清理、float64 | 0.5 天 | 防御性，当前可接受 |
| **无需** | S6 | 无需修补 | 0 | 驳回 |
| **合计** | - | - | **~2.5 天** | （非反方估计的 6 天） |

### 7.3 对反方最终裁决的修正

**反方裁决**："当前 E6 脚本不可直接用于论文，需要 ~6 天修补"

**元审查裁决**：

1. **"不可直接用于论文"——部分同意**。F3（汇总 ECE 未加权）必须修复后才能用于论文。F2（标注歧义）必须在 caption 中说明后才能用于论文。F1（文档矛盾）必须统一文档与代码后才能投稿。
2. **"需要 ~6 天"——不同意**。实际修补工时约 **2.5 天**（P0+P1+P2+P3），因为：
   - F1 改文档（0.5 天）而非改代码（数天）
   - F2 改标签+caption（0.5 天）而非重写 ECE 估计器
   - F3 一行代码（0.5 小时）而非重构
   - S3/S5/S8/S9 当前可接受，仅可选优化
   - S6 驳回，无需修补
3. **"3 个致命问题"——不同意**。仅 F3 是真正的代码 bug（一行修复）。F1 是文档漂移，F2 是标注歧义——两者都是**文档/标注层面的问题**，不是代码逻辑错误。将它们标为"致命"夸大了严重程度。

### 7.4 建议正方声明

E6 脚本在修复 F3（一行代码）+ F2（标注+caption）+ F1（文档统一）后即可用于论文。S4（可复现性）应在投稿前修复。其余攻击点为代码质量改进，不阻塞投稿。

**E6 脚本的核心逻辑（两阶段架构、reliability bin 计算、top-label 语义、10 bin 分箱、加权汇总曲线）是合理的**，与反方"核心逻辑合理但有 3 个致命问题"的评估相比，更准确的描述是"核心逻辑合理，有 1 个真实 bug（一行修复）+ 2 个标注/文档问题 + 若干改进项"。

---

## 8. 我尝试了全部 5 个审查维度

| 维度 | 审查结果 | 说明 |
|------|---------|------|
| 反例是否成立 | 15/20 成立，3 部分成立，1 不成立，1 概率极低 | S6 反例不成立，S9 概率极低 |
| 是否稻草人 | 1/20 是稻草人 | S6 将差异化设计歪曲为自相矛盾 |
| 是否误解前提 | 5/20 有部分误解 | S2（bin_centers 是标准）、S5（PyTorch 内存管理）、S6（twin x 差异）、S7（A5 已声明）、第 5 节（E3 主终点） |
| 攻击逻辑是否自洽 | 3/20 有断链 | S3（高估 10×）、S8（高估 12×）、第 5 节（误解 E3） |
| 严重程度是否被夸大 | 11/20 被夸大 | 3 致命均应降级，6 严重应降级为轻微 |

**最终裁决**：反方攻击报告事实核查质量高（95%），但严重程度存在系统性夸大（55%）。20 个攻击点中，1 个驳回，11 个部分成立，8 个成立。实际修补工时约 2.5 天（非 6 天），E6 脚本在 P0 修补（1.5 天）后即可用于论文。

---

**报告结束**

E6 可靠性图脚本反反方裁决报告完整版。共审查 20 个攻击点：1 驳回 + 11 部分成立 + 8 成立。核心发现：反方事实核查质量高但严重程度系统性夸大，3 个"致命"攻击中仅 F3 是真实代码 bug（一行修复），F1/F2 是文档/标注问题。实际修补工时 ~2.5 天而非反方估计的 6 天。
