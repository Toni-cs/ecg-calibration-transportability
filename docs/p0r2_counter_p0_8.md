# P0-8 反反方审查报告（R2轮）

## 审查概要
- 攻击报告：docs/p0r2_attack_p0_8.md
- 被审查源码：scripts/run_e6_reliability_diagrams.py
- 攻击点总数：8
- 成立：5 | 部分成立：3 | 不成立：0

### 判定分布表

| 攻击点 | 攻击方判定严重度 | 反反方判定 | 反反方修正严重度 |
|--------|-----------------|-----------|-----------------|
| A1. 标题与图例术语不一致 | 严重 | **成立** | 严重（确认） |
| A2. "size" 词语歧义 | 严重 | **部分成立** | 中等（严重度被夸大） |
| A3. nan 过滤静默无警告 | 中等 | **成立** | 中等（确认） |
| A4. np.isfinite 过滤 inf | 中等 | **部分成立** | 轻微（inf ECE 在当前代码中不可能产生） |
| A5. 标题用代码变量名 n_total | 轻微 | **成立** | 轻微（确认） |
| A6. L13 H1 Guo 引用概念混淆 | 轻微 | **成立** | 轻微（确认，但预存非本轮引入） |
| A7. weights 为 nan 的隐式过滤 | 轻微 | **部分成立** | 轻微（n_total 恒为 int，nan 权重不可能出现） |
| A8. docstring 未同步关键语义 | 轻微 | **成立** | 轻微（确认） |

---

## 逐条审查

### 攻击点1: A1 — 标题与图例术语不一致（size-weighted vs n_total-weighted）

**判定**: 成立

**分析**:

经代码原文逐行验证，术语不一致**确实存在**：

```python
# L454 (图例 - Before TS)
label=f"Before TS (size-weighted mean ECE={ece_before:.3f})", zorder=3)

# L459 (图例 - After TS)
label=f"After TS (size-weighted mean ECE={ece_after:.3f})", zorder=4)

# L477-479 (标题)
ax.set_title("Summary: 6-direction averaged reliability curve\n"
             f"(curve: bin-count weighted; ECE: n_total-weighted mean; {REP_ARCH}, seed{REP_SEED})",
             fontsize=12, pad=10)
```

- 图例用 `"size-weighted mean ECE"`（L454/L459）
- 标题用 `"ECE: n_total-weighted mean"`（L478）
- 两者描述的是**同一个加权量**（`weights = np.array([b["n_total"] for b in bins_list])`，L440），但用了两个不同术语

**反反方补充验证**：
1. `'size-weighted' == 'n_total-weighted'` 字符串比较确实为 `False`
2. 全局搜索确认图例只有 L454/L459 两处用 `size-weighted`，标题只有 L478 一处用 `n_total-weighted`，无其他统一术语的地方
3. S3 修复的核心目标是"消除标题与图例的矛盾"（第一轮 S3 攻击），但修复后**确实引入了新的矛盾**——这是"用一种不一致替换另一种不一致"

**严重度评估**：严重——确认。这不影响数值正确性，但对 CBM 期刊而言，标题与图例用不同术语描述同一量是明确的呈现缺陷，审稿人会要求统一。S3 修复的初衷是消除矛盾，结果引入了新矛盾，违背修复初衷。

**修补方案**:
- 文件：`scripts/run_e6_reliability_diagrams.py`
- L454：`size-weighted mean ECE` → `sample-count weighted mean ECE`
- L459：`size-weighted mean ECE` → `sample-count weighted mean ECE`
- L478：`n_total-weighted mean` → `sample-count weighted mean`
- 三处统一为 `sample-count weighted mean`，同时解决 A1（不一致）+ A2（歧义）+ A5（代码变量名）

---

### 攻击点2: A2 — "size" 词语歧义

**判定**: 部分成立

**分析**:

攻击方声称"size"在 ML 语境中常指模型大小、训练集大小，会导致审稿人误解甚至拒稿。经审查，**歧义方向成立但严重度被夸大**。

**成立部分**：
- "size" 确实不是自解释术语。L440 确认 `weights = np.array([b["n_total"] for b in bins_list])`，`n_total` 来自 `len(confidence)`（L162），即 OOD 测试集样本数
- 读者看到 "size-weighted" 需要查代码才能确认 "size" 指的是测试集样本数
- 更清晰的表述如 `sample-count weighted` 确实优于 `size-weighted`

**夸大部分**：
1. **语境强烈约束语义**。图例完整文本是 `"Before TS (size-weighted mean ECE=0.123)"`——这是 reliability diagram 的图例，ECE 是按数据集计算的指标，"size-weighted mean ECE" 中的 "size" 在此语境下最自然解读是"数据集大小/样本数"。审稿人看到 ECE 加权平均，不会解读为"按模型参数量加权 ECE"——那在数学上无意义。
2. **"会导致论文被拒"缺乏依据**。CBM 审稿人会要求澄清术语，但不会因一个可从语境推断的术语直接拒稿。攻击方声称"术语不准确会导致论文被拒"是推测性断言，未提供审稿先例。
3. **与 A1 合并考量**：一旦 A1 修复（统一术语为 `sample-count weighted mean`），A2 自动消解。A2 的独立严重度不应超过"中等"。

**严重度修正**：中等（攻击方称"严重"被夸大）。建议与 A1 合并修复，统一改为 `sample-count weighted mean ECE`。

**修补方案**: 与 A1 合并处理，见 A1 修补方案。

---

### 攻击点3: A3 — nan 过滤静默无警告

**判定**: 成立

**分析**:

经代码验证，`_weighted_ece` 函数（L438-446）确实在过滤 nan/零权重方向时**无运行时警告**：

```python
# L438-446
def _weighted_ece(bins_list):
    """按各方向总样本数加权平均 ECE（过滤 nan 方向）。"""
    weights = np.array([b["n_total"] for b in bins_list], dtype=float)
    eces = np.array([b["ece"] for b in bins_list], dtype=float)
    # 过滤 nan 和零权重方向，防止 nan 传播
    valid = np.isfinite(eces) & (weights > 0)
    if not valid.any():
        return float("nan")
    return float(np.average(eces[valid], weights=weights[valid]))
```

**反反方验证**：
1. `import warnings` 确实在 L80 存在
2. 全文搜索 `warnings.warn` — **无任何匹配**，确认 `warnings` 模块已导入但从未使用
3. 若 6 方向中部分方向 ECE=nan（如 checkpoint 缺失、n_total=0），过滤后用剩余方向计算加权平均，用户在运行时**无法得知**哪些方向被排除

**对攻击方反例的验证**：
```python
# 攻击方反例：6 方向，2 方向 nan
bins = [
    {'n_total': 1000, 'ece': 0.1},
    {'n_total': 2000, 'ece': float('nan')},  # 静默过滤
    {'n_total': 1500, 'ece': 0.15},
    {'n_total': 1800, 'ece': float('nan')},  # 静默过滤
    {'n_total': 1200, 'ece': 0.12},
    {'n_total': 1100, 'ece': 0.11},
]
# _weighted_ece 返回 (0.1*1000+0.15*1500+0.12*1200+0.11*1100)/(1000+1500+1200+1100)
# = (100+225+144+121)/4800 = 590/4800 ≈ 0.1229
# 用户不知道方向 2,4 被排除
```
反例成立——过滤行为在运行时确实静默。

**严重度评估**：中等——确认。代码注释（L442）和 docstring（L439）有文档级说明，但运行时用户看不到被过滤的方向。CBM 期刊要求"数据排除必须显式声明"，运行时警告是合理的透明性要求。

**修补方案**:
- 文件：`scripts/run_e6_reliability_diagrams.py`
- 在 L444（`if not valid.any():`）前插入：
```python
if not valid.all():
    excluded = np.where(~valid)[0]
    warnings.warn(
        f"_weighted_ece: {len(excluded)} 方向因 ECE=nan/inf 或 n_total=0 被排除: {excluded.tolist()}",
        UserWarning, stacklevel=2
    )
```

---

### 攻击点4: A4 — np.isfinite 过滤 inf 的隐含假设

**判定**: 部分成立

**分析**:

攻击方声称 `np.isfinite(eces)` 同时过滤 nan 和 inf，而 inf ECE 表示上游 bug，静默过滤会掩盖 bug。

**成立部分**：
- `np.isfinite` 确实同时过滤 nan 和 inf（这是 numpy 的定义，`np.isfinite(float('inf'))` 返回 `False`）
- 防御性编程原则上，inf 应报错而非静默过滤——攻击方的编程原则正确

**夸大部分（关键）**：

经审查 `compute_reliability_bins` 函数（L132-197），**inf ECE 在当前代码中不可能产生**：

```python
# L184-188
valid = bin_counts > 0
ece_val = float(
    np.sum(bin_counts[valid] / n_total *
           np.abs(bin_confidences[valid] - bin_accuracies[valid]))
) if n_total > 0 else float("nan")
```

- 当 `n_total > 0`：`bin_counts[valid]` 是非负整数，`n_total` 是正整数，`bin_confidences` 和 `bin_accuracies` 是 `[0,1]` 区间浮点数，`np.abs(...)` ∈ [0,1]。整个表达式是有限非负数的有限和，**结果恒有限**
- 当 `n_total == 0`：返回 `float("nan")`，**不是 inf**
- 因此 `b["ece"]` 要么是 `[0,1]` 内的有限浮点数，要么是 `nan`，**绝不可能是 inf**

**反反方验证**：
```python
# 理论上构造 inf ECE 的路径：
# 1. n_total > 0 但 bin_confidences 含 inf → 不可能，bin_confidences = confidence[mask].mean()，confidence ∈ [0,1]
# 2. n_total = 0 → 返回 nan，非 inf
# 3. 数值溢出 → float64 溢出需 ~1e308 量级，ECE ∈ [0,1] 不可能溢出
# 结论：当前代码路径下 inf ECE 不可能产生
```

**严重度修正**：轻微（攻击方称"中等"被夸大）。攻击方的防御性编程建议合理，但当前代码不存在 inf ECE 的产生路径，实际风险为零。这属于"理论上的防御性增强"而非"实际缺陷"。

**修补方案（建议性，非必须）**: 若要增强防御性，可将 L443 改为：
```python
if np.isinf(eces).any():
    raise ValueError(f"_weighted_ece: 检测到 inf ECE，表示上游 bug: {eces[np.isinf(eces)]}")
valid = ~np.isnan(eces) & (weights > 0)
```
但优先级低，因为当前代码不可能触发。

---

### 攻击点5: A5 — 标题用代码变量名 n_total

**判定**: 成立

**分析**:

经代码验证，L478 标题确实使用了代码变量名 `n_total`：

```python
# L478
f"(curve: bin-count weighted; ECE: n_total-weighted mean; {REP_ARCH}, seed{REP_SEED})",
```

- `n_total` 是 `compute_reliability_bins` 返回的 dict key（L196: `"n_total": int(n_total)`），是代码标识符
- 学术论文图标题应使用自然语言，而非代码变量名
- 对比：`"sample-count weighted mean"` 是自解释自然语言，`"n_total-weighted mean"` 需读者查代码才能理解

**反反方验证**：确认 `n_total` 在代码中作为变量名出现于 L162（`n_total = len(confidence)`）、L196（`"n_total": int(n_total)`）、L440（`b["n_total"]`），是代码标识符无疑。

**严重度评估**：轻微——确认。不影响正确性，但影响论文可读性。

**修补方案**: 与 A1 合并处理，L478 `n_total-weighted mean` → `sample-count weighted mean`。

---

### 攻击点6: A6 — L13 H1 Guo 引用概念混淆

**判定**: 成立

**分析**:

经代码验证，L13 确实存在概念混淆：

```python
# L13
H1. 10 个等宽 bin 足够展示校准曲线形态（ECE 文献标准，Guo et al. 2017）。
```

**成立部分**：
- Guo et al. 2017 的贡献是提出 ECE 指标和温度缩放，**使用了 10 bin 但未证明"10 bin 足够"**
- H1 说"10 bin 足够展示形态"是正方的**假设**，不应归因于 Guo et al. 2017
- "Guo 用了 10 bin"（事实）≠ "Guo 证明了 10 bin 足够"（假设）——这是概念混淆

**反反方补充说明**：
1. 这是**预存问题**，非本轮修复引入。攻击方自己也承认"否（预存，非本轮引入）"
2. F3 修复的目标是 L436 的错误引用（"加权 ECE 是 ECE 的标准定义（Guo et al. 2017）"），该引用**已删除**（全局搜索确认 L436 无此行）
3. L435 保留的引用（`Guo et al. 2017 的原始 ECE 定义是单模型 bin 级加权...`）是**正确的对比引用**，用于说明"我们的定义 ≠ Guo 的定义"，不应删除
4. L13 的引用概念混淆虽成立，但不在本轮 F3 修复范围内

**严重度评估**：轻微——确认。预存问题，不影响本轮修复的正确性评价。

**修补方案（建议性）**: L13 改为：
```python
H1. 10 个等宽 bin 是 ECE 文献常用约定（Guo et al. 2017 等采用），本工作假设其足以展示校准曲线形态。
```
明确区分"文献约定"（事实）和"正方假设"（推断）。

---

### 攻击点7: A7 — weights 为 nan 的隐式过滤

**判定**: 部分成立

**分析**:

攻击方声称 `weights > 0` 对 nan 返回 `False`（numpy 语义），nan 权重被隐式过滤，可读性差。

**成立部分**：
- `weights > 0` 对 nan 确实返回 `False`（numpy NaN 比较语义），这是事实
- 显式写 `np.isfinite(weights) & (weights > 0)` 确实比依赖隐式语义更清晰
- 攻击方关于"若未来重构为 `weights != 0`，nan 会被保留"的担忧在原则上成立

**夸大部分（关键）**：

经审查 `n_total` 的产生路径，**weights 在当前代码中不可能为 nan**：

```python
# L162: n_total = len(confidence)  — len() 恒返回非负整数
# L196: "n_total": int(n_total)    — 显式 cast 为 int
# L440: weights = np.array([b["n_total"] for b in bins_list], dtype=float)  — int → float，不会产生 nan
```

- `len(confidence)` 返回 `int`，不可能为 nan
- `int(n_total)` 再次确保是整数
- `np.array(..., dtype=float)` 将 int 转为 float，int → float 不会产生 nan
- **因此 `weights` 数组中不可能出现 nan**，`weights > 0` 的 nan 语义分支永远不会被触发

**反反方验证**：
```python
# 构造 nan 权重的唯一路径：
# b["n_total"] 为 nan → 但 L196 强制 int(n_total)，int(nan) 会抛 ValueError，不会进入 bins_list
# 结论：当前代码路径下 weights 不可能含 nan
```

**严重度修正**：轻微（攻击方自己也定轻微，但实际影响比"轻微"更小——是零影响的理论关切）。攻击方的可读性建议合理，但"若未来重构"是推测性风险，非当前缺陷。

**修补方案（建议性）**: 若要增强可读性，L443 可改为：
```python
valid = np.isfinite(eces) & np.isfinite(weights) & (weights > 0)
```
但优先级最低，因为当前代码不可能触发 nan 权重分支。

---

### 攻击点8: A8 — docstring 未同步关键语义

**判定**: 成立

**分析**:

经代码验证，`_weighted_ece` 的 docstring（L439）确实过简：

```python
# L438-439
def _weighted_ece(bins_list):
    """按各方向总样本数加权平均 ECE（过滤 nan 方向）。"""
```

而上方注释（L433-437）有详细的关键语义说明：
```python
# 方向级加权平均 ECE（按各方向总样本数加权）
# 注意：这是各方向 ECE 的样本数加权平均（size-weighted mean of per-direction ECE），
# 非合并所有样本后重算的全局 ECE。Guo et al. 2017 的原始 ECE 定义是单模型
# bin 级加权 Σ_b(n_b/N)×|acc(b)-conf(b)|，不适用于多方向汇总。
# 方向级加权平均 ECE ≠ 全局 ECE（因 ECE 含绝对值，|x|+|y| ≠ |x+y|）。
```

**成立部分**：
- docstring 是 IDE 悬浮提示和 `help()` 显示的内容，当前缺少"非全局 ECE"这一关键警告
- 注释 L433-437 有详细说明，但 docstring 未同步
- 用户通过 `help(_weighted_ece)` 看不到"方向级加权平均 ECE ≠ 全局 ECE"这一关键语义

**严重度评估**：轻微——确认。不影响正确性，但影响 API 文档完整性。

**修补方案**:
- 文件：`scripts/run_e6_reliability_diagrams.py`
- L439 替换为：
```python
"""按各方向总样本数加权平均 ECE（过滤 nan/零权重方向）。

注意：这是方向级加权平均（sample-count weighted mean of per-direction ECE），
非合并所有样本后重算的全局 ECE。方向级加权平均 ECE ≠ 全局 ECE
（因 ECE 含绝对值，|x|+|y| ≠ |x+y|）。
"""
```

---

## 关键验证点总结

### 1. _weighted_ece 的 nan 过滤正确性

**验证结果**：✅ 正确

```python
# L443
valid = np.isfinite(eces) & (weights > 0)
```

- `np.isfinite(eces)`：过滤 nan 和 inf 的 ECE（inf 在当前代码不可能产生，见 A4 分析）
- `weights > 0`：过滤零权重方向（n_total=0 的方向）
- 过滤后 `np.average(eces[valid], weights=weights[valid])` 自动归一化权重（`sum(e*w)/sum(w)`），无需手动归一化
- 全 nan/全零权重时返回 `float("nan")`（L444-445），有防护

### 2. Guo et al. 2017 引用删除彻底性

**验证结果**：✅ F3 目标已彻底删除，无残留错误引用

- 全局搜索 `Guo` 在 `run_e6_reliability_diagrams.py` 中仅剩 2 处：
  - L13：H1 假设中的引用（预存，概念混淆见 A6，但非 F3 目标）
  - L435：对比引用"Guo et al. 2017 的原始 ECE 定义是单模型 bin 级加权..."（**正确引用**，用于说明"我们的定义 ≠ Guo 的定义"）
- 原 L436 的错误引用"加权 ECE 是 ECE 的标准定义（Guo et al. 2017）"**已删除**

### 3. 标签 'size-weighted mean ECE' 是否准确描述实际计算

**验证结果**：⚠️ 计算描述准确但术语有歧义

- "size-weighted mean ECE" 描述的计算是 `np.average(eces, weights=n_total)`（L446），即按 n_total（样本数）加权平均各方向 ECE——**计算描述准确**
- 但 "size" 一词有歧义（见 A2），不如 `sample-count weighted mean ECE` 清晰

### 4. A1 严重攻击：title vs legend 术语不一致

**验证结果**：✅ 不一致确实存在

- Title (L478): `n_total-weighted mean`
- Legend (L454/L459): `size-weighted mean ECE`
- 两者描述同一量但用不同术语——**不一致成立**

### 5. A2 严重攻击："size" 一词是否有歧义

**验证结果**：⚠️ 有歧义但严重度被夸大

- "size" 确实不是自解释术语（见 A2 分析）
- 但在 reliability diagram + ECE 的语境下，"size" 最自然解读是"样本数"
- "会导致论文被拒"缺乏依据，严重度从"严重"下调为"中等"

---

## 总结

### 需要进一步修复的问题清单（按优先级排序）

| 优先级 | 攻击点 | 修补内容 | 文件+行号 | 改动量 |
|--------|--------|---------|-----------|--------|
| **高** | A1+A2+A5 | 统一术语为 `sample-count weighted mean ECE` | L454/L459/L478 | 3 处字符串 |
| **中** | A3 | 加 `warnings.warn` 提示被过滤方向 | L444 前插入 | 5 行 |
| **低** | A8 | docstring 同步"非全局 ECE"语义 | L439 | 4 行 |
| **建议** | A4 | `np.isfinite` → `~np.isnan` + inf 检查 | L443 | 2 行 |
| **建议** | A7 | 显式 `np.isfinite(weights)` | L443 | 1 行 |
| **建议** | A6 | L13 H1 假设措辞修正 | L13 | 1 行 |

### 已确认修复完成的问题

1. ✅ **F2 nan 过滤核心逻辑**：`valid = np.isfinite(eces) & (weights > 0)` 数学正确，权重归一化由 `np.average` 自动处理
2. ✅ **F3 Guo 错误引用删除**：L436 已删除，L435 保留正确对比引用
3. ✅ **F1+S2 标签修改**：L454/L459 已从 `weighted avg ECE` 改为 `size-weighted mean ECE`（无残留旧标签）
4. ✅ **S3 标题修改**：L477-479 已明确区分"曲线加权"和"ECE 加权"

### 对正方修复的总体评价

**第二轮修复核心逻辑正确**，消除了第一轮的全部 3 个致命缺陷（F1 标签偏移、F2 nan 传播、F3 引用错误）。F2 的 nan 过滤数学正确，F3 的引用删除精准（只删错误引用、保留正确对比引用）。

**但 S3 修复（标题修改）未与 F1+S2 修复（图例修改）协调**，引入了 1 个新的严重不一致（A1：标题 `n_total-weighted` vs 图例 `size-weighted`）。这是"修复一个矛盾时引入另一个矛盾"的典型情况，但只需 3 处字符串改动即可解决，零回归风险。

**最终判定**：第二轮修复**核心正确但有呈现缺陷**，需第三轮轻量修补（3-5 处字符串/警告改动）。无致命缺陷，不阻塞 P0-8 关闭。A1 严重不一致应在论文投稿前修复。

### 反反方对攻击报告的评价

攻击报告（docs/p0r2_attack_p0_8.md）整体质量**较高**：
- ✅ 8 个攻击点全部基于代码原文逐行分析，无臆测
- ✅ F2 正确性独立验证表（6 个测试场景）准确无误
- ✅ F3 全局 Guo 引用审查彻底，正确区分了"错误引用"和"正确对比引用"
- ⚠️ A2 严重度被夸大（"严重"→"中等"）：在 reliability diagram 语境下 "size" 歧义有限
- ⚠️ A4 严重度被夸大（"中等"→"轻微"）：inf ECE 在当前代码路径下不可能产生
- ⚠️ A7 影响被高估：n_total 恒为 int，nan 权重不可能出现

攻击报告的**核心发现（A1 标题-图例不一致）准确且有价值**，应被正方采纳修复。
