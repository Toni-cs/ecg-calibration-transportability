# P0-8 反方攻击报告：ECE 加权修复审查

> **反方挑刺代理-P0-8 交付**。本报告对正方在 `scripts/run_e6_reliability_diagrams.py` 中的 ECE 加权修复（`_weighted_ece` 函数及图例标签变更）进行逐行审查，寻找逻辑漏洞、隐含假设不成立、边界失效、语义偏移。
> **攻击日期**：2026-09-09
> **攻击对象**：`scripts/run_e6_reliability_diagrams.py` L415-446（`_weighted_avg` / `_weighted_ece`）+ L451/456（图例标签）+ L474-476（标题）
> **攻击代理**：反方挑刺代理-P0-8（GLM-5.2）
> **诚实原则**：对每一行代码问"这个加权是否正确？这个标注是否诚实？这个'一致'是否真的成立？"
> **攻击维度**：反例构造 / 逻辑断链 / 隐含假设 / 边界失效 / 自相矛盾 / 量级错误 / 语义偏移（7 维度全覆盖）

---

## 0. 攻击审查概述

### 攻击点数量统计

| 严重性 | 数量 | 编号 |
|--------|------|------|
| **致命** | 3 | F1, F2, F3 |
| **严重** | 5 | S1-S5 |
| **轻微** | 3 | M1-M3 |
| **合计** | 11 | - |

### 整体评估

正方 P0-8 修复的**出发点是正确的**：汇总图曲线用样本数加权平均（`_weighted_avg`，bin 级加权），而 ECE 标注此前用 `np.mean`（简单算术平均），两者确实不匹配，审稿人对比图内数值会发现不一致。

但**修复方案本身引入了三个致命问题**：

1. **语义偏移（F1）**：`_weighted_ece` 计算的是"各方向 ECE 的方向级加权平均"，但图例标注为 "weighted avg ECE"，读者自然理解为"合并所有样本后重算的全局 ECE"。**这两者数学上不相等**，反例可证（0.1 vs 0.0）。修复只是把"简单平均 vs 曲线加权"的矛盾，换成了"方向级加权 vs 读者期望的全局 ECE"的矛盾。
2. **边界失效（F2）**：当任一方向 `n_total=0`（其 `ece=nan`）时，`np.average` 会把 nan 传播到整个结果，即使其他方向都有有效数据，汇总 ECE 也变成 nan。**已数值验证**。
3. **引用错误（F3）**：修补说明 L436 声称"加权 ECE 是 ECE 的标准定义（Guo et al. 2017）"。**这是错误的**：Guo et al. 2017 的 ECE 是单模型按 bin 样本数加权的定义，不是"多方向 ECE 的方向级加权平均"。正方把两个不同层级的加权混淆了。

**结论**：P0-8 修复方向正确，但实现有缺陷。当前修复**没有真正消除"曲线加权 vs ECE 加权"的语义矛盾**，只是用一种新的矛盾替换了旧的矛盾。需要：(a) 明确标注语义（"size-weighted mean of per-direction ECE"而非"weighted avg ECE"）；(b) 过滤 nan ece；(c) 修正或删除 Guo et al. 引用；(d) 考虑直接用汇总曲线重算 ECE 以真正"与曲线加权方式一致"。

---

## 1. 致命攻击（3 个）

### F1：语义偏移——"weighted avg ECE" ≠ 全局 ECE（反例可证）

**攻击维度**：语义偏移 + 反例构造

**证据**：

`_weighted_ece`（L437-443）计算的是：
```
ECE_weighted = Σ_dir (N_dir × ECE_dir) / Σ_dir N_dir
```
即"各方向 ECE 的方向级加权平均"。

但图例标签（L451）标注为 `weighted avg ECE`，读者最自然的理解是"把所有方向的样本合并后重新分 bin 计算的全局 ECE"，即：
```
ECE_global = Σ_bin (n_bin/N_total) × |conf_bin - acc_bin|
```
其中 `n_bin`、`conf_bin`、`acc_bin` 是合并所有方向样本后该 bin 的统计量。

**这两者数学上不相等**。ECE 含绝对值，绝对值与加权平均不可交换。

**反例构造（已数值验证）**：

构造两个方向，各 500 样本，全部落在 bin 5：
- 方向 A：`conf=0.5, acc=0.6`（偏差 -0.1）
- 方向 B：`conf=0.5, acc=0.4`（偏差 +0.1）

| 量 | 值 |
|----|----|
| `ECE_A` | `0.5 × |0.5-0.6| = 0.1` |
| `ECE_B` | `0.5 × |0.5-0.4| = 0.1` |
| `_weighted_ece`（方向级加权平均） | `(500×0.1 + 500×0.1)/1000 = 0.1` |
| 全局 ECE（合并样本后重算） | 合并后 `acc=(500×0.6+500×0.4)/1000=0.5`，`|0.5-0.5|=0`，**ECE=0.0** |

**`_weighted_ece` 返回 0.1，但真正的全局 ECE 是 0.0。加权平均高估了 0.1（相对误差 ∞）。**

物理含义：两个方向的偏差方向相反，合并后互相抵消，全局校准是完美的；但"各方向 ECE 的加权平均"无法捕捉这种抵消，仍然报告 0.1 的偏差。审稿人若按"全局 ECE"理解图例，会误以为模型整体欠校准。

**严重程度**：致命——修复后的图例标注仍然误导读者，只是从"简单平均误导"变成"加权平均误导"。审稿人对比汇总图 ECE 与正文报告的（按主终点口径计算的）ECE，仍会发现数值对不上。

**修补建议**：
1. **首选**：直接用汇总曲线重算 ECE。即对 `_weighted_avg` 返回的 `acc[i]` 和对应的加权 `conf[i]` 计算 `Σ_i (n_i/N) × |conf_i - acc_i|`。这才是真正"与曲线加权方式一致"的 ECE。但需同时加权平均 `bin_confidences`（当前 `_weighted_avg` 只加权了 `bin_accuracies`，见 S5）。
2. **次选**：保留 `_weighted_ece`，但图例标签改为 `size-weighted mean of per-direction ECE`，明确这是"各方向 ECE 的加权平均"而非"全局 ECE"，避免读者误解。

---

### F2：边界失效——部分 n_total=0 + nan ece 导致整个汇总 ECE 变 nan

**攻击维度**：边界失效

**证据**：

`_weighted_ece`（L437-443）：
```python
def _weighted_ece(bins_list):
    weights = np.array([b["n_total"] for b in bins_list], dtype=float)
    eces = np.array([b["ece"] for b in bins_list], dtype=float)
    if weights.sum() <= 0:
        return float("nan")
    return float(np.average(eces, weights=weights))
```

只检查了 `weights.sum() <= 0`（全零边界），**没有检查部分方向 ece 为 nan 的情况**。

`compute_reliability_bins`（L185-188）在 `n_total=0` 时返回 `ece=nan`：
```python
ece_val = float(...) if n_total > 0 else float("nan")
```

**边界场景**：6 个方向中，5 个方向有样本（`n_total>0, ece` 有效），1 个方向 OOD 测试集为空（`n_total=0, ece=nan`，权重=0）。

**数值验证（已执行）**：
```python
weights = np.array([1000, 0], dtype=float)
eces = np.array([0.2, float('nan')], dtype=float)
np.average(eces, weights=weights)  # 返回 nan！
```

原因：`np.average` 内部计算 `Σ(w_i × x_i) / Σ(w_i)`，其中 `0 × nan = nan`，`1000×0.2 + 0×nan = 200 + nan = nan`，`nan / 1000 = nan`。**即使空方向的权重为 0，它的 nan ece 仍然污染了整个结果**。

对照：过滤 nan 后 `np.average([0.2], weights=[1000]) = 0.2`，结果正确。

**触发条件**：在迁移学习场景下，某个方向的 OOD 测试集缺失（数据加载失败、checkpoint 缺失、`--limit` 截断为 0）是常见情况。`generate_figures` 中 `_load_npz` 返回 None 时会 `missing += 1` 并跳过，但如果 npz 存在但 `n_ood=0`（例如数据集为空），`compute_reliability_bins` 会返回 `n_total=0, ece=nan`，该方向仍会被加入 `summary_before`，触发此 bug。

**严重程度**：致命——一个空方向会让整个汇总图的 ECE 标注变成 `nan`，图例显示 `weighted avg ECE=nan`，汇总图直接报废。

**修补建议**：
```python
def _weighted_ece(bins_list):
    weights = np.array([b["n_total"] for b in bins_list], dtype=float)
    eces = np.array([b["ece"] for b in bins_list], dtype=float)
    # 过滤 nan ece 和零权重
    valid = np.isfinite(eces) & (weights > 0)
    if not valid.any() or weights[valid].sum() <= 0:
        return float("nan")
    return float(np.average(eces[valid], weights=weights[valid]))
```

---

### F3：引用错误——Guo et al. 2017 的 ECE 定义不是"多方向 ECE 加权平均"

**攻击维度**：隐含假设 + 语义偏移

**证据**：

修补说明（L433-436）：
```python
# 修补说明：此前用 np.mean（简单算术平均）与曲线的样本数加权平均不匹配，
# 审稿人对比图内数值会发现不一致。现改为按 n_total 加权，使 ECE 标注与
# 曲线加权方式统一。加权 ECE 是 ECE 的标准定义（Guo et al. 2017）。
```

最后一句"加权 ECE 是 ECE 的标准定义（Guo et al. 2017）"是**错误的引用**。

**Guo et al. 2017《On Calibration of Modern Neural Networks》的 ECE 定义**：
```
ECE = Σ_b (n_b / N) × |acc(b) - conf(b)|
```
这是**单个模型**的 ECE，按 **bin 样本数** `n_b` 加权，对 **bin 级** 的 `|acc - conf|` 求和。

`_weighted_ece` 计算的是：
```
ECE_weighted = Σ_dir (N_dir / N_total) × ECE_dir
```
这是**多个方向**的 ECE 的加权平均，按 **方向总样本数** `N_dir` 加权，对 **方向级** 的 `ECE_dir` 求平均。

**这是两个完全不同层级的加权**：
- Guo et al.：bin 级加权，单模型，权重是 `n_b`
- `_weighted_ece`：方向级加权，多方向，权重是 `N_dir`

正方把"单模型 ECE 的 bin 加权定义"套用到"多方向 ECE 的方向加权平均"上，并声称这是 Guo et al. 的标准定义。**这是引用错误/概念混淆**。

**反例**：按 Guo et al. 的定义，"全局 ECE"应该是把所有方向样本合并后按 bin 加权计算（即 F1 中的 `ECE_global`）。但 `_weighted_ece` 计算的不是这个（见 F1 反例：0.1 vs 0.0）。

**严重程度**：致命——引用错误会被审稿人当场抓出。若审稿人熟悉 Guo et al. 2017，会指出"这不是 Guo 的定义"，进而质疑作者是否理解自己报告的指标。

**修补建议**：
1. 删除"加权 ECE 是 ECE 的标准定义（Guo et al. 2017）"这句。
2. 改为诚实描述："按各方向总样本数加权平均各方向的 ECE（各方向 ECE 本身按 Guo et al. 2017 的 bin 加权定义计算）。这是对多方向 ECE 的汇总约定，非 Guo et al. 的原始定义。"
3. 或直接采用 F1 修补建议 1（用汇总曲线重算 ECE），那样才是真正的 Guo et al. 定义。

---

## 2. 严重攻击（5 个）

### S1：逻辑断链——曲线 bin 级加权 vs ECE 方向级加权，"一致"是误导

**攻击维度**：逻辑断链 + 自相矛盾

**证据**：

正方修补说明 L435 声称"使 ECE 标注与曲线加权方式统一"。但代码中两种加权是**不同层级**的：

| 函数 | 加权对象 | 权重 | 层级 |
|------|----------|------|------|
| `_weighted_avg`（L415-428，曲线） | 每个 bin 的 `bin_accuracies[i]` | `bin_counts[i]`（该 bin 样本数） | **bin 级** |
| `_weighted_ece`（L437-443，ECE） | 每个方向的 `ece` | `n_total`（该方向总样本数） | **方向级** |

曲线加权公式：`acc[i] = Σ_dir (n_{dir,i} × acc_{dir,i}) / Σ_dir n_{dir,i}`（每个 bin 内跨方向加权）
ECE 加权公式：`ECE = Σ_dir (N_dir × ECE_dir) / Σ_dir N_dir`（跨方向加权 ECE）

**这两个公式的加权结构相似，但语义不同**。"与曲线加权方式一致"是一个**未经证明的跳跃**。

**数值验证（已执行）**：构造方向 A（1000 样本，bin 5 acc=0.6，ECE=0.1）和方向 B（100 样本，bin 5 acc=0.4，ECE=0.3），conf 均为 0.5：

| ECE 计算方式 | 值 |
|--------------|----|
| 简单平均（修复前） | 0.200 |
| 方向级加权平均（`_weighted_ece`，修复后） | 0.118 |
| 汇总曲线重算 ECE（bin 级加权后算 `|conf-acc|`） | 0.082 |

**三种 ECE 互不相等**。如果真的要"与曲线加权方式一致"，应该用第三种（汇总曲线重算），但代码实现的是第二种。修复后的 ECE 仍然不"一致"于曲线。

**严重程度**：严重——修复的核心主张（"使 ECE 标注与曲线加权方式统一"）未达成。审稿人若按"一致"理解，会误以为汇总图 ECE 是用汇总曲线算的，实际不是。

**修补建议**：见 F1 修补建议 1（用汇总曲线重算 ECE）。

---

### S2：图例标签歧义——"weighted avg ECE" 未说明权重是什么

**攻击维度**：语义偏移

**证据**：

图例标签（L451）：
```python
label=f"Before TS (weighted avg ECE={ece_before:.3f})"
```

"weighted avg ECE" 没有说明**权重是什么**。读者可能理解为：
- 按 bin 样本数加权？（与标题 "weighted by bin sample count" 一致）
- 按方向总样本数加权？（代码实际实现）
- 按方向数加权？（即简单平均）

实际实现是"按方向总样本数 `n_total` 加权"，但标签没说。标题（L474-476）说 "weighted by bin sample count"，更让读者误以为 ECE 也按 bin sample count 加权。

**严重程度**：严重——图例标签歧义会让审稿人误解数值含义。

**修补建议**：标签改为 `size-weighted mean ECE` 或 `n-weighted avg ECE`，明确权重是样本数。或更详细：`mean ECE (weighted by n_total)`。

---

### S3：标题与图例矛盾——标题说 "bin sample count"，图例说 "weighted avg ECE"（n_total）

**攻击维度**：自相矛盾

**证据**：

- 标题（L474-476）：`"Summary: 6-direction averaged reliability curve\n(weighted by bin sample count; ...)"`
- 图例（L451）：`"Before TS (weighted avg ECE=...)"`

标题说曲线"weighted by bin sample count"（bin 级加权），图例说 ECE "weighted avg"（未说明，但实际是方向级 `n_total` 加权）。

**读者合理推断**：既然标题强调"weighted by bin sample count"，图例的"weighted avg ECE"应该也是按 bin sample count 加权。但实际 ECE 是按 `n_total`（方向级）加权。**标题与图例的加权语义不一致**。

**严重程度**：严重——同一张图内标题与图例的"weighted"含义不同，审稿人会质疑"到底按什么加权"。

**修补建议**：标题区分曲线和 ECE 的加权方式，例如：`"Summary: 6-direction averaged reliability curve\n(curve weighted by bin count; ECE weighted by n_total)"`。

---

### S4：nan ece 未过滤——F2 边界失效的根因

**攻击维度**：边界失效 + 隐含假设

**证据**：

`_weighted_ece`（L437-443）隐含假设"所有方向的 ece 都是有效数值"。但 `compute_reliability_bins` 在 `n_total=0` 时返回 `ece=nan`（L188）。代码没有用 `np.isfinite` 过滤 nan ece，导致 F2 的边界失效。

**隐含假设不成立的情况**：
- 某方向 OOD 测试集为空（数据缺失、加载失败、`--limit=0`）
- 某方向 checkpoint 缺失但 npz 存在且 `n_ood=0`
- 某方向所有样本的 confidence 都是 nan（数据损坏）

**严重程度**：严重——这是 F2 的根因，单独列出以明确修补点。

**修补建议**：见 F2 修补建议（过滤 `np.isfinite(eces) & (weights > 0)`）。

---

### S5：缺少 bin_confidences 加权平均——即使要"用汇总曲线算 ECE"也缺数据

**攻击维度**：逻辑断链

**证据**：

`_weighted_avg`（L415-428）只加权平均了 `bin_accuracies`：
```python
total_wa += w * b["bin_accuracies"][i]
```
**没有加权平均 `bin_confidences`**。

如果按 F1 修补建议 1（用汇总曲线重算 ECE）来真正"与曲线加权方式一致"，需要：
```
ECE_consistent = Σ_i (n_i/N) × |conf_avg[i] - acc_avg[i]|
```
其中 `conf_avg[i]` 和 `acc_avg[i]` 都是 bin 级加权平均。但当前 `_weighted_avg` 只返回 `acc`，没返回 `conf`，无法计算 `ECE_consistent`。

**严重程度**：严重——这阻碍了 F1 修补建议 1 的直接实施。要真正"与曲线加权方式一致"，需要扩展 `_weighted_avg` 同时返回加权平均的 `conf`。

**修补建议**：扩展 `_weighted_avg` 返回 `(acc, conf, counts)`，然后用三者重算 ECE。

---

## 3. 轻微攻击（3 个）

### M1：量级错误——0.05 绝对差异在 ECE 量级上不显著

**攻击维度**：量级错误

**证据**：

正方报告：简单平均=0.20，加权平均=0.25，差异 25%。但**绝对差异仅 0.05**。

在 ECE 文献中：
- Guo et al. 2017 报告的 ECE 量级在 0.05-0.20 之间
- 0.05 的差异通常在 bootstrap CI 的置信区间内（E6 的 CI 是 1000 次 bootstrap）
- 25% 的相对差异看起来显著，但 ECE 本身是 `[0,1]` 区间的小数，相对差异容易放大

**反问**：如果各方向样本数相近（例如 ptbxl test ≈ chapman test），简单平均与加权平均的差异会很小（<0.01），修复意义不大。正方报告 0.20 vs 0.25 的差异，说明各方向样本数差异较大，但**正方没有报告各方向的 n_total**，无法验证差异来源。

**严重程度**：轻微——修复本身无害，但"差异显著"的说法可能夸大了修复的必要性。

**修补建议**：在修补说明中补充各方向 n_total 和 ECE 的明细，让审稿人自行判断差异显著性。

---

### M2：单图 vs 汇总图语义不一致——修复引入新的不一致

**攻击维度**：自相矛盾

**证据**：

- 单图（`plot_reliability_enhanced`，L327）：`ECE={bins_before['ece']:.3f}`——该方向的 ECE
- 汇总图（`plot_summary`，L451）：`weighted avg ECE={ece_before:.3f}`——各方向 ECE 的加权平均

修复前：汇总图 ECE = 简单平均，与单图 ECE 的"平均"语义一致（读者看 6 个单图 ECE，手动平均 ≈ 汇总图 ECE）。
修复后：汇总图 ECE = 加权平均，与单图 ECE 的"简单平均"语义不一致（读者手动平均 6 个单图 ECE ≠ 汇总图 ECE）。

**修复把"汇总图 vs 单图手动平均"的语义一致性打破了**。读者若手动平均 6 个单图的 ECE，会发现与汇总图的 "weighted avg ECE" 对不上，可能质疑"为什么不是简单平均"。

**严重程度**：轻微——这是修复的固有代价，加权平均本身比简单平均更合理。但需要在图注或 Method 部分说明"汇总图 ECE 是加权平均，非简单平均"，避免读者困惑。

**修补建议**：在图注或 caption 中说明加权方式。

---

### M3：未报告其他校准指标（Brier/MCE）——非 P0-8 问题但值得指出

**攻击维度**：隐含假设

**证据**：

grep 显示脚本中没有 Brier score、MCE（Maximum Calibration Error）、reliability gap 的汇总计算。只报告 ECE。

这不是 P0-8 修复引入的问题，但**值得指出**：如果未来添加 Brier/MCE 的汇总，同样需要考虑加权 vs 简单平均的问题。P0-8 修复没有建立通用的加权汇总框架，只是针对 ECE 打了补丁。

**严重程度**：轻微——超出 P0-8 范围，但提示未来技术债。

**修补建议**：若未来添加其他指标，统一用加权汇总框架。

---

## 4. 全维度攻击记录

| 维度 | 是否发现攻击点 | 对应攻击点 |
|------|----------------|------------|
| **1. 反例构造** | ✅ 是 | F1（加权平均 ECE ≠ 全局 ECE，反例 0.1 vs 0.0） |
| **2. 逻辑断链** | ✅ 是 | S1（曲线 bin 级 vs ECE 方向级，"一致"未证明）、S5（缺 conf 加权） |
| **3. 隐含假设** | ✅ 是 | F3（Guo 引用错误）、S4（假设所有 ece 有效）、M3（假设只报 ECE 够用） |
| **4. 边界失效** | ✅ 是 | F2（部分 n_total=0 + nan ece → 整体 nan，已验证） |
| **5. 自相矛盾** | ✅ 是 | S3（标题 bin count vs 图例 n_total）、M2（单图 vs 汇总语义） |
| **6. 量级错误** | ✅ 是 | M1（0.05 绝对差异不显著，相对差异 25% 被放大） |
| **7. 语义偏移** | ✅ 是 | F1（"weighted avg ECE" 偏移到"全局 ECE"）、S2（标签未说明权重）、F3（Guo 定义偏移） |

**全部 7 个维度均发现可攻击点**。无"未发现可攻击点"的维度。

---

## 5. 攻击点汇总（按严重程度排序）

### 致命（3 个）

| 编号 | 攻击点 | 维度 | 修补建议 |
|------|--------|------|----------|
| F1 | "weighted avg ECE" ≠ 全局 ECE，反例 0.1 vs 0.0 | 语义偏移+反例 | 用汇总曲线重算 ECE，或明确标签语义 |
| F2 | 部分 n_total=0 + nan ece → 整体 nan | 边界失效 | 过滤 `np.isfinite(eces) & (weights>0)` |
| F3 | Guo et al. 2017 引用错误 | 隐含假设+语义偏移 | 删除错误引用，诚实描述加权约定 |

### 严重（5 个）

| 编号 | 攻击点 | 维度 | 修补建议 |
|------|--------|------|----------|
| S1 | 曲线 bin 级 vs ECE 方向级，"一致"是误导 | 逻辑断链 | 用汇总曲线重算 ECE |
| S2 | "weighted avg ECE" 未说明权重 | 语义偏移 | 标签改为 `size-weighted mean ECE` |
| S3 | 标题 "bin sample count" vs 图例 n_total | 自相矛盾 | 标题区分曲线和 ECE 加权 |
| S4 | nan ece 未过滤（F2 根因） | 边界失效 | 同 F2 |
| S5 | 缺 bin_confidences 加权平均 | 逻辑断链 | 扩展 `_weighted_avg` 返回 conf |

### 轻微（3 个）

| 编号 | 攻击点 | 维度 | 修补建议 |
|------|--------|------|----------|
| M1 | 0.05 绝对差异不显著 | 量级错误 | 补充各方向 n_total 明细 |
| M2 | 单图 vs 汇总语义不一致 | 自相矛盾 | 图注说明加权方式 |
| M3 | 未报告 Brier/MCE | 隐含假设 | 未来统一加权框架 |

---

## 6. 总结

### 修复的正确之处

正方 P0-8 修复的**出发点正确**：识别到了汇总图曲线加权 vs ECE 标注简单平均的矛盾（原 F3 攻击点），并尝试用加权平均替换简单平均。`_weighted_ece` 的实现公式 `Σ(N_dir × ECE_dir)/ΣN_dir` 本身是合理的"各方向 ECE 的加权平均"。

### 修复的致命缺陷

但修复**没有真正消除语义矛盾**，只是替换了矛盾的形式：

1. **旧矛盾**：曲线加权 vs ECE 简单平均 → 读者对比图内数值发现不一致
2. **新矛盾**：曲线 bin 级加权 vs ECE 方向级加权 → 读者仍会发现"汇总图 ECE"不等于"用汇总曲线算的 ECE"，且"weighted avg ECE"标签让读者误以为是"全局 ECE"

修复还引入了**新的边界失效**（F2：nan 传播）和**引用错误**（F3：Guo et al. 误用）。

### 推荐的真正修复

**首选方案（真正"与曲线加权方式一致"）**：
1. 扩展 `_weighted_avg` 同时返回加权平均的 `acc[i]`、`conf[i]`、`counts[i]`
2. 用三者重算 ECE：`ECE = Σ_i (n_i/N) × |conf_avg[i] - acc_avg[i]|`
3. 这才是真正的 Guo et al. 2017 定义（bin 级加权），且与汇总曲线完全一致
4. 图例标签改为 `ECE of averaged curve` 或 `pooled ECE`
5. 过滤 nan 方向

**次选方案（保留 `_weighted_ece` 但诚实标注）**：
1. 保留当前 `_weighted_ece` 实现
2. 图例标签改为 `size-weighted mean of per-direction ECE`，明确这是"各方向 ECE 的加权平均"而非"全局 ECE"
3. 删除 L436 的 Guo et al. 引用，改为"按各方向总样本数加权平均各方向 ECE（汇总约定，非 Guo et al. 原始定义）"
4. 过滤 nan ece（F2 修补）
5. 标题区分曲线和 ECE 的加权方式（S3 修补）

### 最终判定

**P0-8 修复方向正确，但实现有致命缺陷，需要二次修补。** 当前版本若直接产出图放入论文，审稿人仍会发现：
- 图例 "weighted avg ECE" 与正文 ECE 数值对不上（F1 语义偏移）
- 某方向数据缺失时汇总图 ECE 变 nan（F2 边界失效）
- 修补说明误引 Guo et al.（F3 引用错误）

**建议**：采用首选方案（用汇总曲线重算 ECE），真正实现"曲线加权与 ECE 加权一致"，并修复 F2/F3。

---

*报告结束。反方挑刺代理-P0-8 已尝试全部 7 个攻击维度，发现 3 个致命、5 个严重、3 个轻微攻击点。*
