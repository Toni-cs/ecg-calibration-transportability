# P0-8 回炉修复（第二轮）反方攻击报告

> **反方代理交付**（任务 #79）。本报告对正方代理第二轮 P0-8 回炉修复做全方位攻击审查。
> **审查日期**：2026-09-09
> **审查代理**：反方-P0R2-8-ECE加权（GLM-5.2）
> **审查对象**：`scripts/run_e6_reliability_diagrams.py` 第二轮修改
> **审查标准**：CBM 期刊（IF~7）审稿标准——代码正确性无懈可击、术语一致性、隐含假设显式化、读者无歧义。

---

## 总览

| 修复项 | 终审要求 | 实现状态 | 攻击结果 |
|--------|---------|---------|---------|
| F2 nan 过滤 | `valid = np.isfinite(eces) & (weights > 0)` | ✅ 已实现 | 逻辑正确，但过滤静默无警告 + isfinite 过滤 inf 隐含假设 |
| F3 Guo 引用删除 | 删除 L436 错误引用 | ✅ 已删除 | L435 保留正确引用（合理），L13 H1 引用概念混淆（预存） |
| F1+S2 标签修改 | "weighted avg ECE" → "size-weighted mean ECE" | ✅ 已改 2 处 | "size" 词语歧义 |
| S3 标题修改 | "curve: bin-count weighted; ECE: n_total-weighted mean" | ✅ 已改 | **与图例术语不一致**（新引入缺陷） |

**总体判定**：第二轮修复**核心逻辑正确**（F2 nan 过滤数学正确、F3 错误引用已删、F1+S2 标签已改、S3 标题已改），但**引入 1 个新的严重不一致**（标题与图例术语不统一）+ 2 个中等缺陷（静默过滤 + isfinite 过滤 inf）+ 4 个轻微缺陷。**无致命缺陷**，但严重不一致需第三轮修补。

| 攻击点 | 严重度 | 成立性 | 是否新引入 |
|--------|--------|--------|-----------|
| A1. 标题与图例术语不一致 | **严重** | ✅ 成立 | **是（S3 修复引入）** |
| A2. "size" 词语歧义 | **严重** | ✅ 成立 | 是（F1+S2 修复引入） |
| A3. nan 过滤静默无警告 | 中等 | ✅ 成立 | 是（F2 修复引入） |
| A4. np.isfinite 过滤 inf 隐含假设 | 中等 | ✅ 成立 | 是（F2 修复引入） |
| A5. 标题用代码变量名 n_total | 轻微 | ✅ 成立 | 是（S3 修复引入） |
| A6. L13 H1 Guo 引用概念混淆 | 轻微 | ✅ 成立 | 否（预存，非本轮引入） |
| A7. weights 为 nan 的隐式过滤 | 轻微 | ✅ 成立 | 是（F2 修复引入） |
| A8. docstring 未同步关键语义 | 轻微 | ✅ 成立 | 是（F2 修复引入） |

---

## 逐项攻击

### A1：标题与图例术语不一致（严重，S3 修复新引入）

**攻击**：S3 修复将标题改为 `"curve: bin-count weighted; ECE: n_total-weighted mean"`，但图例标签（L454/L459）用的是 `"size-weighted mean ECE"`。**同一个加权量，在标题和图例中用了两种不同表述**，读者会困惑：这是两个不同的加权方式吗？

**代码证据**：

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

**读者视角**：
- 看图例："size-weighted mean ECE" → 按 size 加权
- 看标题："ECE: n_total-weighted mean" → 按 n_total 加权
- 读者自然疑问："size" 和 "n_total" 是同一个量吗？如果是，为什么用两个词？如果不是，那图例和标题报告的是两个不同的 ECE？

**验证**：Python 验证确认 `'size-weighted' == 'n_total-weighted'` 为 `False`。

**严重程度**：严重——S3 修复的核心目标是"消除标题与图例的矛盾"（终审报告 S3：标题与图例矛盾），但修复后**引入了新的矛盾**：标题和图例用不同术语描述同一量。这是"用一种不一致替换另一种不一致"，违背了 S3 修复的初衷。

**修补建议**：统一术语。推荐：
- 图例：`"Before TS (n_total-weighted mean ECE={ece_before:.3f})"`（与标题一致）
- 或标题：`"ECE: size-weighted mean"`（与图例一致）
- 或两者都改为 `"sample-count weighted mean ECE"`（最清晰，见 A2）

---

### A2："size" 词语歧义（严重，F1+S2 修复新引入）

**攻击**：图例标签 `"size-weighted mean ECE"` 中的 "size" 指的是 `n_total`（OOD 测试集样本数），但 "size" 在机器学习语境中常指：
- **模型大小**（model size / parameter count）
- **训练集大小**（training set size）
- **样本数**（sample size，但通常用 "sample-count" 或 "n" 而非 "size"）

读者看到 "size-weighted" 可能误解为"按模型大小加权"或"按训练集大小加权"，实际是"按 OOD 测试集样本数加权"。

**代码证据**：

```python
# L440: weights 实际是 n_total（OOD 测试集样本数）
weights = np.array([b["n_total"] for b in bins_list], dtype=float)
```

`n_total` 来自 `compute_reliability_bins` 的 `n_total = len(confidence)`（L162），即 OOD 测试集的样本数。但 "size" 一词无法让读者联想到 "OOD test set sample count"。

**严重程度**：严重——CBM 期刊审稿人会质疑 "size" 的定义。如果审稿人误解为"按训练集大小加权"，会质疑为什么用训练集大小加权 OOD 评估指标。术语不准确会导致论文被拒。

**修补建议**：改为 `"sample-count weighted mean ECE"` 或 `"n_ood-weighted mean ECE"`（明确是 OOD 测试集样本数）。

---

### A3：nan 过滤静默无警告（中等，F2 修复新引入）

**攻击**：F2 修复在 `_weighted_ece` 中过滤 nan 方向（L443-446），但**没有 warnings.warn 提示哪些方向被过滤**。如果某方向的 ECE=nan（因 n_total=0、checkpoint 缺失、或 `--limit=0`），静默过滤让用户完全不知道哪些方向被排除出加权平均。

**代码证据**：

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

**问题**：
1. 文件已 `import warnings`（L80），但 `_weighted_ece` 未使用。
2. 若 6 方向中 2 方向 ECE=nan，静默过滤后用剩余 4 方向计算加权平均，用户不知道汇总图实际只用了 4 方向。
3. 这违背了"隐含假设显式化"原则——过滤行为是隐含的，用户无法从图上看出哪些方向被排除。

**反例**：
```python
# 6 方向，2 方向 nan
bins = [
    {'n_total': 1000, 'ece': 0.1},   # 方向 1
    {'n_total': 2000, 'ece': float('nan')},  # 方向 2 (nan, 静默过滤)
    {'n_total': 1500, 'ece': 0.15},  # 方向 3
    {'n_total': 1800, 'ece': float('nan')},  # 方向 4 (nan, 静默过滤)
    {'n_total': 1200, 'ece': 0.12},  # 方向 5
    {'n_total': 1100, 'ece': 0.11},  # 方向 6
]
# 结果 = 加权平均(方向1,3,5,6)，但用户不知道方向2,4被排除
```

**严重程度**：中等——不影响数值正确性，但影响科学透明性。CBM 期刊要求"数据排除必须显式声明"。

**修补建议**：
```python
if not valid.all():
    excluded = np.where(~valid)[0]
    warnings.warn(
        f"_weighted_ece: {len(excluded)} 方向因 ECE=nan 或 n_total=0 被排除: {excluded.tolist()}",
        UserWarning, stacklevel=2
    )
```

---

### A4：np.isfinite 过滤 inf 的隐含假设（中等，F2 修复新引入）

**攻击**：F2 修复用 `np.isfinite(eces)` 过滤，但 `np.isfinite` **同时过滤 nan 和 inf**。ECE 理论上 ∈ [0, 1]（因 |conf - acc| ≤ 1 且权重归一化），**inf ECE 表示 `compute_reliability_bins` 有 bug**（如除零、数值溢出）。静默过滤 inf 会**掩盖上游 bug**。

**代码证据**：

```python
# L443
valid = np.isfinite(eces) & (weights > 0)  # isfinite 过滤 nan AND inf
```

**Python 验证**：
```python
# T6: 含 inf 的 ECE
bins = [{'n_total': 1000, 'ece': float('inf')}, {'n_total': 2000, 'ece': 0.2}]
print(_weighted_ece(bins))  # 输出: 0.2 (inf 被静默过滤)
```

inf 被静默过滤，返回 0.2，**用户完全不知道有方向的 ECE 是 inf**。如果 ECE=inf 是因 `compute_reliability_bins` 的除零 bug（如 `n_total=0` 但未返回 nan），那这个 bug 会被 `_weighted_ece` 的过滤掩盖。

**严重程度**：中等——ECE=inf 在正常情况下不会出现，但若出现则表示上游 bug，应报错而非静默过滤。这是防御性编程缺失。

**修补建议**：只过滤 nan，让 inf 报错：
```python
valid = ~np.isnan(eces) & (weights > 0)  # 只过滤 nan，inf 会传播并暴露 bug
# 或显式检查 inf:
if np.isinf(eces).any():
    raise ValueError(f"_weighted_ece: 检测到 inf ECE，表示上游 bug: {eces[np.isinf(eces)]}")
```

---

### A5：标题用代码变量名 n_total（轻微，S3 修复新引入）

**攻击**：S3 修复的标题 `"ECE: n_total-weighted mean"` 中 `n_total` 是**代码变量名**，出现在图标题中对读者不友好。学术论文图标题应用自然语言，而非代码标识符。

**代码证据**：

```python
# L478
f"(curve: bin-count weighted; ECE: n_total-weighted mean; {REP_ARCH}, seed{REP_SEED})",
```

**对比**：
- `"n_total-weighted mean"` ← 代码变量名，读者需查代码才能理解
- `"sample-count weighted mean"` ← 自然语言，自解释
- `"test-set-size weighted mean"` ← 自然语言，明确是测试集大小

**严重程度**：轻微——不影响正确性，但影响论文可读性。CBM 期刊图标题应自解释。

**修补建议**：改为 `"sample-count weighted mean"` 或 `"test-set-size weighted mean"`。

---

### A6：L13 H1 假设的 Guo 引用概念混淆（轻微，预存非本轮引入）

**攻击**：L13 的 H1 假设 `10 个等宽 bin 足够展示校准曲线形态（ECE 文献标准，Guo et al. 2017）` 中，Guo et al. 2017 **只是用了 10 bin**，**没有证明"10 bin 足够展示形态"**。把"Guo 用了 10 bin"等同于"10 bin 足够"是概念混淆——前者是事实，后者是假设。

**代码证据**：

```python
# L13
H1. 10 个等宽 bin 足够展示校准曲线形态（ECE 文献标准，Guo et al. 2017）。
```

**分析**：
- Guo et al. 2017 的贡献是提出 ECE 指标和温度缩放，**不是证明 10 bin 最优**
- 实际上 Guo et al. 2017 没有做 bin 数敏感性分析，10 bin 只是约定俗成
- H1 说"10 bin 足够"是正方的假设，不应把假设归因于 Guo et al. 2017

**严重程度**：轻微——这是预存问题（非本轮修复引入），且 F3 攻击的目标是 L436 的错误引用（已删除），不是 L13。但 L13 的引用仍有概念混淆，应一并修正。

**修补建议**：改为 `H1. 10 个等宽 bin 是 ECE 文献常用约定（Guo et al. 2017 等采用），本工作假设其足以展示校准曲线形态。`——明确区分"文献约定"和"正方假设"。

---

### A7：weights 为 nan 的隐式过滤（轻微，F2 修复新引入）

**攻击**：`weights > 0` 对 nan 返回 `False`（numpy 的 NaN 比较语义），所以 nan 权重会被隐式过滤。虽然结果正确，但**依赖 numpy 的隐式行为**，可读性差。

**代码证据**：

```python
# L443
valid = np.isfinite(eces) & (weights > 0)  # weights>0 对 nan 返回 False
```

**Python 验证**：
```python
# T7: 权重为 nan
bins = [{'n_total': float('nan'), 'ece': 0.1}, {'n_total': 2000, 'ece': 0.2}]
print(_weighted_ece(bins))  # 输出: 0.2 (nan 权重被隐式过滤)
```

`weights > 0` 对 nan 返回 False 是 numpy 的约定，但读者可能不熟悉这个语义。应显式过滤 nan 权重。

**严重程度**：轻微——结果正确，但可读性和健壮性差。若未来有人重构为 `weights >= 0`，nan 仍会被过滤；但若重构为 `weights != 0`，nan 会被保留（因 nan != 0 为 True），导致 nan 传播。

**修补建议**：显式过滤 nan 权重：
```python
valid = np.isfinite(eces) & np.isfinite(weights) & (weights > 0)
```

---

### A8：docstring 未同步关键语义（轻微，F2 修复新引入）

**攻击**：`_weighted_ece` 的 docstring（L439）`"""按各方向总样本数加权平均 ECE（过滤 nan 方向）。"""` 过于简略，**没有说明"非全局 ECE"这一关键语义**。注释 L433-437 有详细说明，但 docstring 是 IDE 悬浮提示和 `help()` 显示的内容，应包含关键语义。

**代码证据**：

```python
# L438-439
def _weighted_ece(bins_list):
    """按各方向总样本数加权平均 ECE（过滤 nan 方向）。"""
```

**对比注释**（L433-437，详细）：
```python
# 方向级加权平均 ECE（按各方向总样本数加权）
# 注意：这是各方向 ECE 的样本数加权平均（size-weighted mean of per-direction ECE），
# 非合并所有样本后重算的全局 ECE。Guo et al. 2017 的原始 ECE 定义是单模型
# bin 级加权 Σ_b(n_b/N)×|acc(b)-conf(b)|，不适用于多方向汇总。
# 方向级加权平均 ECE ≠ 全局 ECE（因 ECE 含绝对值，|x|+|y| ≠ |x+y|）。
```

docstring 缺少"非全局 ECE"这一关键警告，用户通过 `help(_weighted_ece)` 看不到这个语义。

**严重程度**：轻微——不影响正确性，但影响 API 文档完整性。

**修补建议**：docstring 同步关键语义：
```python
"""按各方向总样本数加权平均 ECE（过滤 nan/零权重方向）。

注意：这是方向级加权平均（size-weighted mean of per-direction ECE），
非合并所有样本后重算的全局 ECE。方向级加权平均 ECE ≠ 全局 ECE
（因 ECE 含绝对值，|x|+|y| ≠ |x+y|）。
"""
```

---

## F2 修复正确性验证（反方独立确认）

尽管上述攻击点成立，反方独立确认 **F2 的核心数学逻辑正确**：

| 测试场景 | 预期 | 实际 | 正确? |
|---------|------|------|-------|
| 正常（2 方向） | (0.1×1000+0.2×2000)/3000=0.167 | 0.167 | ✅ |
| 含 nan（1 方向 nan） | 0.1（过滤 nan） | 0.1 | ✅ |
| 全 nan | nan | nan | ✅ |
| 零权重（1 方向 n_total=0） | 0.2（过滤零权重） | 0.2 | ✅ |
| 全零权重 | nan | nan | ✅ |
| 权重归一化 | np.average 自动归一化 | 与手动计算一致 | ✅ |

**结论**：F2 的 nan 过滤、零权重过滤、全 nan 防护、权重归一化均正确。`np.average(eces[valid], weights=weights[valid])` 内部自动归一化权重（`weights / weights.sum()`），无需手动归一化。攻击点 A3/A4/A7 针对的是**过滤的副作用**（静默、inf、隐式），非核心逻辑错误。

---

## F3 Guo 引用删除彻底性审查

### 在 `run_e6_reliability_diagrams.py` 中的 Guo 引用

| 位置 | 内容 | 状态 | 评价 |
|------|------|------|------|
| L13 | `H1. ...（ECE 文献标准，Guo et al. 2017）` | 保留 | 预存，非 F3 目标。但 H1 假设概念混淆（见 A6） |
| L435 | `Guo et al. 2017 的原始 ECE 定义是单模型 bin 级加权...` | 保留 | **正确引用**，用于对比说明"非 Guo 定义"，是诚实描述 |
| ~~L436~~ | ~~`加权 ECE 是 ECE 的标准定义（Guo et al. 2017）`~~ | **已删除** | ✅ F3 攻击目标已修复 |

**判定**：F3 攻击的目标（L436 的错误引用）**已彻底删除**。L435 保留的引用是**正确的对比引用**（用于说明"我们的定义 ≠ Guo 的定义"），不应删除。L13 的引用是预存问题（见 A6），非本轮修复职责。

### 全局 Guo 引用审查

全局搜索 `Guo` 在 `D:\A1\ecg-lab-v2` 发现的其他引用：

| 文件 | 引用上下文 | 正确? |
|------|-----------|-------|
| `docs/EXPERIMENT_PROTOCOL.md` L23/128/308/369/524 | "Guo 2017" 作为 TS/ECE 文献引用 | ✅ 正确 |
| `docs/COUNTER_REBUTTAL_RESPONSE.md` L880/1526/2172 | "TS (Guo 2017)" 标注 TS 来源 | ✅ 正确 |
| `docs/adversarial_r1_counter_e4.md` L368 | "Guo et al. (ICML 2017) 的经典温度缩放论文" | ✅ 正确 |
| `docs/adversarial_r1_counter_e6.md` L66/69/76/213 | "Guo et al. 2017" 作为 10 bin 标准 | ✅ 正确 |
| `docs/p0_attack_p0_8.md` / `p0_counter_p0_8.md` | 攻击/回应报告中的引用 | ✅ 正确（文档） |
| `docs/p0_counter_p0_3.md` L86 | "Guo et al. 2017, Kumar et al. 2019 均用 10" | ✅ 正确 |

**判定**：全局无残留的**错误** Guo 引用。所有其他 Guo 引用都是正确的文献引用（TS 来源、10 bin 标准、ECE 定义对比），不应删除。F3 修复**彻底且精准**——只删除了错误的引用，保留了正确的引用。

---

## F1+S2 标签修改彻底性审查

| 位置 | 旧标签 | 新标签 | 状态 |
|------|--------|--------|------|
| L454 | `Before TS (weighted avg ECE=...)` | `Before TS (size-weighted mean ECE=...)` | ✅ 已改 |
| L459 | `After TS (weighted avg ECE=...)` | `After TS (size-weighted mean ECE=...)` | ✅ 已改 |

**判定**：图例标签已全部修改（2 处），无残留 "weighted avg ECE"。但新标签 "size-weighted" 有歧义（见 A2），且与标题 "n_total-weighted" 不一致（见 A1）。

---

## S3 标题修改审查

| 位置 | 旧标题 | 新标题 | 状态 |
|------|--------|--------|------|
| L477-479 | （原标题未明确区分曲线/ECE 加权） | `Summary: 6-direction averaged reliability curve\n(curve: bin-count weighted; ECE: n_total-weighted mean; ...)` | ✅ 已改 |

**判定**：标题已明确区分"曲线加权方式"（bin-count weighted）和"ECE 加权方式"（n_total-weighted mean），S3 的核心矛盾（标题与图例不区分两种加权）已解决。但新标题引入了与图例的术语不一致（见 A1）和代码变量名问题（见 A5）。

---

## 攻击点汇总表

| ID | 攻击点 | 严重度 | 成立性 | 新引入? | 根因 |
|----|--------|--------|--------|---------|------|
| A1 | 标题与图例术语不一致（size-weighted vs n_total-weighted） | **严重** | ✅ | 是 | S3 修复未与 F1+S2 协调 |
| A2 | "size" 词语歧义（model size? train size? test size?） | **严重** | ✅ | 是 | F1+S2 修复选词不当 |
| A3 | nan 过滤静默无警告 | 中等 | ✅ | 是 | F2 修复未加 warnings.warn |
| A4 | np.isfinite 过滤 inf 掩盖上游 bug | 中等 | ✅ | 是 | F2 修复过滤过宽 |
| A5 | 标题用代码变量名 n_total | 轻微 | ✅ | 是 | S3 修复用代码标识符 |
| A6 | L13 H1 Guo 引用概念混淆（"足够"≠"用了"） | 轻微 | ✅ | 否（预存） | 历史问题 |
| A7 | weights 为 nan 的隐式过滤 | 轻微 | ✅ | 是 | F2 修复依赖 numpy 隐式语义 |
| A8 | docstring 未同步"非全局 ECE"语义 | 轻微 | ✅ | 是 | F2 修复 docstring 过简 |

---

## 与第一轮攻击对比

| 维度 | 第一轮（p0_attack_p0_8.md） | 第二轮（本报告） |
|------|---------------------------|------------------|
| 致命攻击数 | 3（F1/F2/F3） | **0** |
| 严重攻击数 | 5（S1-S5） | **2**（A1/A2） |
| 中等攻击数 | 0 | **2**（A3/A4） |
| 轻微攻击数 | 3（M1-M3） | **4**（A5-A8） |
| 核心逻辑正确? | 否（F2 nan 传播、F3 引用错误） | **是**（F2 过滤正确、F3 引用已删） |
| 新引入缺陷? | 是（F2/F3 修复引入） | **是**（A1 标题-图例不一致） |

**进步**：第二轮修复**消除了全部 3 个致命缺陷**（F1 标签偏移、F2 nan 传播、F3 引用错误），核心数学逻辑正确。

**残留**：第二轮修复**引入了 1 个新的严重不一致**（A1 标题与图例术语不统一），这是 S3 修复时未与 F1+S2 协调导致的。另有 2 个中等缺陷（A3 静默过滤、A4 inf 过滤）需修补。

---

## 修补清单（按优先级排序）

1. **[scripts/run_e6_reliability_diagrams.py L454/L459/L478]** 统一术语：图例和标题用同一个词描述 ECE 加权方式。推荐三者都改为 `sample-count weighted mean ECE`（解决 A1+A2+A5，3 处改动）
2. **[scripts/run_e6_reliability_diagrams.py L443 后]** 加 `warnings.warn` 提示被过滤的方向（解决 A3，3 行改动）
3. **[scripts/run_e6_reliability_diagrams.py L443]** `np.isfinite(eces)` → `~np.isnan(eces)`，只过滤 nan 让 inf 报错（解决 A4，1 行改动）
4. **[建议] [scripts/run_e6_reliability_diagrams.py L443]** 显式 `np.isfinite(weights) & (weights > 0)`（解决 A7，1 行改动）
5. **[建议] [scripts/run_e6_reliability_diagrams.py L439]** docstring 同步"非全局 ECE"语义（解决 A8，3 行改动）
6. **[建议] [scripts/run_e6_reliability_diagrams.py L13]** H1 假设改为"10 bin 是文献约定（Guo et al. 2017 采用），本工作假设其足以展示形态"（解决 A6，1 行改动）

**优先级**：中——无致命缺陷，但 A1 严重不一致应在论文投稿前修复（3 处字符串改动，零回归风险）。

---

## 反方声明

本报告由反方代理独立撰写，对正方代理第二轮 P0-8 回炉修复做全方位攻击审查。审查基于代码原文逐行分析 + Python 反例验证 + 全局搜索，无臆测。

**关键发现**：
- 第二轮修复**消除了第一轮的全部 3 个致命缺陷**（F1/F2/F3），核心数学逻辑正确。
- 但 S3 修复（标题修改）未与 F1+S2 修复（图例修改）协调，**引入了新的严重不一致**（A1：标题 "n_total-weighted" vs 图例 "size-weighted"）。
- F2 修复的 nan 过滤逻辑正确，但过滤行为静默无警告（A3）、过滤范围过宽含 inf（A4），需防御性增强。
- F3 修复彻底且精准——只删除了错误引用，保留了正确的对比引用。

**最终判定**：第二轮修复**核心正确但有不一致**，需第三轮轻量修补（3-5 处字符串/警告改动，零回归风险）。无致命缺陷，不阻塞 P0-8 关闭，但 A1 严重不一致应在论文投稿前修复。
