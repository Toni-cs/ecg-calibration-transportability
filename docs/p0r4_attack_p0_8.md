# P0-8 R4轮反方攻击报告

> **反方挑刺代理交付**（任务 #115）。本报告对正方论证代理完成的 P0-8 R4 修复进行全方位攻击审查。
> **审查日期**：2026-09-09
> **审查代理**：反方挑刺代理（GLM-5.2）
> **审查对象**：`scripts/run_e6_reliability_diagrams.py` L434 注释术语同步（R3 终审遗留 A1-2 的 R4 修复）
> **审查标准**：7 个攻击维度全覆盖，每个维度要么找到具体攻击点，要么明确记录"未发现可攻击点"

---

## 0. R4修复内容回顾

根据 `docs/p0r3_final_verdict.md` 第 2.4 节，R4 修复要求 1 项：

| 序号 | 优先级 | 攻击点 | 文件 | 行号 | 改动内容 | 改动量 |
|------|--------|--------|------|------|---------|--------|
| 1 | P0-中等 | A1-2 | scripts/run_e6_reliability_diagrams.py | L434 | `size-weighted mean of per-direction ECE` → `sample-count weighted mean of per-direction ECE` | 1行 |

正方声称已完成此 1 行注释术语同步。以下逐维度攻击。

---

## 1. R4修复实际验证

### 1.1 L434当前内容确认

读取 `scripts/run_e6_reliability_diagrams.py` L433-437 当前内容：

```python
# L433-437（R4修复后）：
# 方向级加权平均 ECE（按各方向总样本数加权）
# 注意：这是各方向 ECE 的样本数加权平均（sample-count weighted mean of per-direction ECE），
# 非合并所有样本后重算的全局 ECE。Guo et al. 2017 的原始 ECE 定义是单模型
# bin 级加权 Σ_b(n_b/N)×|acc(b)-conf(b)|，不适用于多方向汇总。
# 方向级加权平均 ECE ≠ 全局 ECE（因 ECE 含绝对值，|x|+|y| ≠ |x+y|）。
```

**验证结果**：L434 的英文术语已从 `size-weighted mean of per-direction ECE` 改为 `sample-count weighted mean of per-direction ECE`。✅ R4 修复的**直接目标已达成**。

### 1.2 全局 `size-weighted` 残留检查

执行全局搜索 `size-weighted` 在所有 `.py` 文件中：

```
grep "size-weighted" --include="*.py" D:\A1\ecg-lab-v2
```

**结果**：**零匹配**。所有 `size-weighted` 出现仅在 `docs/` 目录的历史报告文件中（p0r2_*.md, p0r3_*.md），源代码中无任何残留。

**验证结果**：✅ 全局 `.py` 文件中 `size-weighted` 已完全清除。

### 1.3 `sample-count weighted` 全局出现位置

源代码中 `sample-count weighted` 共 4 处，全部位于 `scripts/run_e6_reliability_diagrams.py`：

| 行号 | 位置 | 完整字符串 | 核心术语 |
|------|------|-----------|---------|
| L434 | 注释 | `sample-count weighted mean of per-direction ECE` | `sample-count weighted mean` |
| L460 | 图例（Before TS） | `sample-count weighted mean ECE={ece_before:.3f}` | `sample-count weighted mean` |
| L465 | 图例（After TS） | `sample-count weighted mean ECE={ece_after:.3f}` | `sample-count weighted mean` |
| L484 | 标题 | `ECE: sample-count weighted mean` | `sample-count weighted mean` |

**核心术语 `sample-count weighted mean` 在 4 处一致**。✅

---

## 2. 全维度攻击

### 2.1 维度1：反例构造

#### 攻击点B1：L434中英文术语精度不对称（P0-轻微）

**攻击**：R4 修复将 L434 英文从 `size-weighted` 改为 `sample-count weighted`，但 L434 的**中文术语**仍为 `样本数加权平均`，与相邻行 L433 和 L439 的中文术语精度不一致：

| 行号 | 中文术语 | 精度 |
|------|---------|------|
| L433 | `各方向总样本数加权` | **精确**（明确"各方向总"） |
| L434 | `样本数加权平均` | **模糊**（未限定"各方向总"） |
| L439 | `各方向总样本数加权平均 ECE` | **精确**（明确"各方向总"） |

**反例**：开发者阅读 L433 `各方向总样本数加权` → L434 `样本数加权平均` → L439 `各方向总样本数加权平均`，三行描述同一种加权，但中文术语三种写法，L434 最模糊。L434 的英文 `sample-count weighted mean` 虽然清晰，但中文 `样本数加权平均` 未限定"各方向总"，与 L416 的 `样本数加权平均`（描述 bin_counts 加权）**完全相同**，造成跨函数歧义。

**严重程度**：轻微。理由：
1. R4 的 stated scope 是英文术语同步（R3 终审要求），中文术语不在 R4 修复范围内
2. L434 英文括注 `（sample-count weighted mean of per-direction ECE）` 已消除歧义
3. 但作为彻底审查，中英文精度不对称是真实存在的可维护性问题

**修补建议**：L434 中文改为 `各方向 ECE 的各方向总样本数加权平均`（与 L433/L439 中文精度对齐）。

#### 攻击点B2：L434中文术语与L416中文术语完全相同但描述不同加权（P0-轻微）

**攻击**：L434 和 L416 使用**完全相同的中文术语** `样本数加权平均`，但描述的是**两种不同的加权方式**：

```python
# L416（_weighted_avg 的 docstring）：
"""样本数加权平均每个 bin 的 accuracy。"""
# 实际计算：w = b["bin_counts"][i]  ← bin 级样本数

# L434（_weighted_ece 的注释）：
# 注意：这是各方向 ECE 的样本数加权平均（sample-count weighted mean of per-direction ECE），
# 实际计算：weights = [b["n_total"] for b in bins_list]  ← 方向级总样本数
```

**反例**：开发者搜索 `样本数加权平均` 会同时命中 L416 和 L434，需阅读代码才能区分一个是 bin_counts 加权、另一个是 n_total 加权。中文术语未区分两种粒度的"样本数"。

**严重程度**：轻微。理由：
1. 这是**R3 遗留问题**，非 R4 引入——R4 只改了 L434 英文，未改中文
2. L434 英文 `sample-count weighted mean of per-direction ECE` 中的 `of per-direction` 已隐含方向级粒度
3. 但 L416 无英文括注，仅靠中文 `样本数加权平均` 无法区分粒度

**修补建议**：L416 中文改为 `bin 内样本数加权平均`（与 L400 `bin 内样本数加权平均` 对齐），或 L434 中文改为 `各方向总样本数加权平均`（与 L433/L439 对齐）。

### 2.2 维度2：逻辑断链

**攻击尝试**：R4 修复是否在推理链条中引入未证明的跳跃？

R4 修复的推理链条：
1. R3 终审判定 L434 注释术语 `size-weighted` 与 L460/L465/L484 的 `sample-count weighted` 不一致（A1-2，P0-中等）
2. R4 将 L434 的 `size-weighted` 改为 `sample-count weighted`
3. 改后 L434 核心术语 `sample-count weighted mean` 与 L460/L465/L484 一致

推理链条坚实，无跳跃。✅

**判定**：该维度未发现可攻击点。

### 2.3 维度3：隐含假设

#### 攻击点B3：`sample-count weighted` 是否准确描述实际计算？（P0-轻微，非缺陷）

**攻击**：`sample-count weighted` 是否准确描述 `_weighted_ece` 的实际计算？

实际计算（L440-452）：
```python
weights = np.array([b["n_total"] for b in bins_list], dtype=float)
eces = np.array([b["ece"] for b in bins_list], dtype=float)
return float(np.average(eces[valid], weights=weights[valid]))
```

权重 = `n_total` = `len(confidence)` = 该方向 OOD 测试集的总样本数。

**分析**：
- `n_total` 确实是"样本数"（sample count）→ `sample-count weighted` 字面准确 ✅
- 但标题 L484 将 `bin-count weighted`（曲线加权）与 `sample-count weighted`（ECE 加权）**对比并列**，暗示两者是不同概念
- 实际上 `bin_counts[i]` 也是"样本数"（bin 内样本数），`n_total` 也是"样本数"（方向总样本数），两者都是 sample count，只是粒度不同
- `bin-count` = bin 级样本数，`sample-count` = 方向级总样本数——命名未体现粒度差异

**反例**：读者看到标题 `curve: bin-count weighted; ECE: sample-count weighted mean`，可能误解为：
- `bin-count` = 按 bin 数量加权（如 10 个 bin 等权）
- `sample-count` = 按样本数加权

实际两者都是按样本数加权，只是粒度不同（bin 级 vs 方向级）。

**严重程度**：轻微。理由：
1. 这是 **R3 遗留问题**（标题 L484 在 R3 修复时设定），非 R4 引入
2. R4 只改了 L434 注释，未改 L484 标题
3. `sample-count weighted` 对 `_weighted_ece` 的描述本身是准确的——n_total 确实是 sample count
4. 标题中 `bin-count` vs `sample-count` 的对比虽有粒度歧义，但上下文（curve vs ECE）已约束语义

**判定**：该维度未发现 R4 引入的可攻击点。`sample-count weighted` 对 L434 描述的计算是准确的。标题粒度歧义是 R3 遗留，非 R4 scope。

### 2.4 维度4：边界失效

#### 攻击点B4：R4修改是否引入新问题？注释与代码行为是否匹配？（未发现可攻击点）

**攻击**：R4 修改了 L434 注释。注释修改是否可能引入新问题？

1. **注释不影响代码行为**：L434 是 `#` 注释行，Python 解释器跳过，不影响任何运行时行为 ✅
2. **注释与代码行为匹配性**：
   - 注释说 `sample-count weighted mean of per-direction ECE`
   - 代码做 `np.average(eces, weights=n_total)` = 按 n_total（样本数）加权平均各方向 ECE
   - 注释准确描述代码行为 ✅
3. **注释与 L433 一致性**：
   - L433: `方向级加权平均 ECE（按各方向总样本数加权）`
   - L434: `各方向 ECE 的样本数加权平均（sample-count weighted mean of per-direction ECE）`
   - 两行描述同一计算，L433 简洁中文标签，L434 详细中英文解释，无矛盾 ✅

**判定**：该维度未发现可攻击点。注释修改不引入任何功能性问题，且注释内容与代码行为一致。

### 2.5 维度5：自相矛盾

#### 攻击点B5：L434与L460/L465的完整字符串仍不完全相同（P0-轻微，R3遗留A1-1）

**攻击**：R4 将 L434 改为 `sample-count weighted mean of per-direction ECE`，与 L460/L465 的 `sample-count weighted mean ECE` 相比，插入了 `of per-direction`：

| 行号 | 字符串 | 差异 |
|------|--------|------|
| L434 | `sample-count weighted mean of per-direction ECE` | 含 `of per-direction` |
| L460 | `sample-count weighted mean ECE` | 无 `of per-direction` |
| L465 | `sample-count weighted mean ECE` | 无 `of per-direction` |
| L484 | `ECE: sample-count weighted mean` | 词序不同 + 无 `of per-direction` |

```python
>>> "sample-count weighted mean of per-direction ECE" == "sample-count weighted mean ECE"
False
```

**分析**：
- 核心术语 `sample-count weighted mean` 在 4 处一致 ✅
- L434 的 `of per-direction` 是注释的**精确化补充**（注释需要解释清楚"是什么的加权平均"），图例 L460/L465 因空间限制省略 `of per-direction`，标题 L484 因结构化标注用 `ECE:` 前缀
- 这是**语境差异**（注释 vs 图例 vs 标题），非术语不一致

**严重程度**：轻微。理由：此即 R3 轮 A1-1 攻击点，R3 终审判定为"语境差异合理，核心术语一致，非缺陷"（`docs/p0r3_final_verdict.md` L205）。R4 修复未改变此状况——L434 本就是注释，注释比图例更详细是合理的。

**判定**：该维度未发现 R4 引入的新可攻击点。L434 vs L460/L465 的字符串差异是合理的语境差异，核心术语一致。

### 2.6 维度6：量级错误

**攻击尝试**：R4 修复是否涉及复杂度/收敛性/稳定性的错误估计？

R4 修改的是 1 行注释，不涉及任何计算逻辑、复杂度、收敛性或稳定性。

**判定**：该维度未发现可攻击点。注释修改不涉及量级估计。

### 2.7 维度7：语义偏移

#### 攻击点B6：`size-weighted` → `sample-count weighted` 是否语义偏移？（未发现可攻击点）

**攻击**：R4 将 `size-weighted` 改为 `sample-count weighted`，是否存在语义偏移（概念定义被悄悄替换）？

**原术语 `size-weighted` 的语义**：
- `size` 在 ML 语境中歧义：可指 model size / dataset size / training set size / test set size / bin size
- 在 L434 上下文中，`size` 实际指 `n_total`（OOD 测试集样本数）

**新术语 `sample-count weighted` 的语义**：
- `sample-count` = 样本数 = `n_total`
- 语义明确，无歧义

**语义对比**：
- `size-weighted`（歧义）→ `sample-count weighted`（明确）
- 两者描述的**实际计算相同**（都是按 n_total 加权）
- 新术语**消除了歧义**，非语义偏移

**验证**：`np.average(eces, weights=n_total)` 的权重是 n_total = 样本数 = sample count。`sample-count weighted` 精确描述此计算。✅

**判定**：该维度未发现可攻击点。`sample-count weighted` 比 `size-weighted` 更精确地描述了实际计算，无语义偏移。

---

## 3. 跨文件术语一致性检查

### 3.1 论文文本检查

搜索 `paper/` 目录中的 `main.tex` 和 `cover_letter.tex`：

```
grep "size-weighted|sample-count weighted|n_total-weighted|weighted avg ECE|bin-count weighted" paper/
```

**结果**：**零匹配**。论文文本使用标准 ECE 数学符号（`$\Delta\text{ECE}_{\text{OOD}}$`），未提及可靠性图汇总的加权方式。

**判定**：✅ 论文文本无需同步修改。可靠性图的加权术语是代码内部实现细节，未出现在论文文本中。

### 3.2 其他 .py 文件检查

搜索所有 `.py` 文件中的 `size.weighted` 和 `sample.count.weighted`：

```
grep "size.weighted|sample.count.weighted" --include="*.py" D:\A1\ecg-lab-v2
```

**结果**：
- `size-weighted`：**零匹配**（全部清除）
- `sample-count weighted`：仅 `scripts/run_e6_reliability_diagrams.py` 4 处（L434/L460/L465/L484）

**判定**：✅ 全局 `.py` 文件术语一致，无跨文件不一致。

### 3.3 docs/ 历史报告中的旧术语

`docs/` 目录中仍有大量 `size-weighted` 和 `n_total-weighted` 出现（p0r2_*.md, p0r3_*.md 等），这些是**历史审查报告**，记录修复过程中的术语演变，非代码文件，无需同步修改。

**判定**：✅ 历史报告中的旧术语是审查记录，非需同步的代码。

---

## 4. R3修复中3处字符串与R4的L434一致性验证

R3 修复统一了 3 处用户可见字符串（L460/L465/L484）为 `sample-count weighted mean`。R4 的 L434 修改是否与这 3 处一致？

| 行号 | R3/R4 修复 | 完整术语 | 核心术语 | 一致性 |
|------|-----------|---------|---------|--------|
| L460（R3） | 图例 Before | `sample-count weighted mean ECE` | `sample-count weighted mean` | ✅ |
| L465（R3） | 图例 After | `sample-count weighted mean ECE` | `sample-count weighted mean` | ✅ |
| L484（R3） | 标题 | `ECE: sample-count weighted mean` | `sample-count weighted mean` | ✅ |
| L434（R4） | 注释 | `sample-count weighted mean of per-direction ECE` | `sample-count weighted mean` | ✅ |

**核心术语 `sample-count weighted mean` 在 4 处完全一致**。完整字符串因语境（注释/图例/标题）有合理差异，但核心术语无偏移。

**判定**：✅ R4 的 L434 修改与 R3 的 3 处字符串在核心术语层面完全一致。

---

## 5. `sample-count weighted` 是否准确描述实际计算？

### 5.1 实际计算验证

`_weighted_ece` 函数（L438-452）的实际计算：

```python
weights = np.array([b["n_total"] for b in bins_list], dtype=float)
eces = np.array([b["ece"] for b in bins_list], dtype=float)
return float(np.average(eces[valid], weights=weights[valid]))
```

数学表达：
```
ECE_summary = Σ_d (n_total_d × ECE_d) / Σ_d n_total_d
```
其中 d 遍历 6 个迁移方向，`n_total_d` = 方向 d 的 OOD 测试集样本数。

### 5.2 术语准确性分析

| 术语 | 对应的权重 | 是否准确 |
|------|-----------|---------|
| `sample-count weighted` | n_total（方向级总样本数） | ✅ 准确 |
| `size-weighted`（旧） | n_total（但"size"歧义） | ⚠️ 歧义 |
| `n_total-weighted`（R2曾用） | n_total | ✅ 准确但暴露代码变量名 |
| `bin-count weighted`（标题中曲线的加权） | bin_counts[i]（bin级样本数） | ✅ 准确（描述曲线，非ECE） |

**结论**：`sample-count weighted` 准确描述了 `_weighted_ece` 的实际计算（按 n_total = 方向级样本数加权）。✅

### 5.3 标题中两种加权的对比

标题 L484：`(curve: bin-count weighted; ECE: sample-count weighted mean; ...)`

| 加权对象 | 权重变量 | 术语 | 粒度 |
|---------|---------|------|------|
| 曲线（每 bin 的 accuracy） | `bin_counts[i]` | `bin-count weighted` | bin 级 |
| ECE（每方向的 ECE） | `n_total` | `sample-count weighted mean` | 方向级 |

两种加权都是"按样本数加权"，但粒度不同（bin 级 vs 方向级）。标题通过 `curve:` / `ECE:` 前缀区分了加权对象，通过 `bin-count` / `sample-count` 区分了粒度。

**潜在歧义**：`bin-count` 也是"样本数"（bin 内样本数），`sample-count` 也是"样本数"（方向总样本数），两者都是 sample count。但上下文（curve vs ECE）已约束语义，歧义可接受。

**判定**：✅ `sample-count weighted` 对 L434 描述的计算是准确的。标题粒度歧义是 R3 遗留（L484 在 R3 设定），非 R4 引入。

---

## 6. 全维度攻击汇总

### 6.1 攻击维度覆盖表

| 维度 | 编号 | 攻击点 | 严重程度 | 是否成立 | R4引入? |
|------|------|--------|---------|---------|---------|
| 1.反例构造 | B1 | L434中英文术语精度不对称（中文"样本数加权平均"模糊） | 轻微 | ✅ 成立 | 否（R3遗留，R4只改英文） |
| 1.反例构造 | B2 | L434中文与L416中文完全相同但描述不同加权 | 轻微 | ✅ 成立 | 否（R3遗留，R4只改英文） |
| 2.逻辑断链 | - | 推理链条坚实无跳跃 | - | ⬜ 未发现可攻击点 | - |
| 3.隐含假设 | B3 | 标题`bin-count`vs`sample-count`粒度歧义 | 轻微 | ✅ 成立 | 否（R3遗留，L484在R3设定） |
| 4.边界失效 | - | 注释修改不影响代码行为，注释与代码匹配 | - | ⬜ 未发现可攻击点 | - |
| 5.自相矛盾 | B5 | L434与L460/L465完整字符串不同（`of per-direction`插入） | 轻微 | ✅ 成立（语境差异合理） | 否（R3遗留A1-1） |
| 6.量级错误 | - | 注释修改不涉及量级估计 | - | ⬜ 未发现可攻击点 | - |
| 7.语义偏移 | - | `size-weighted`→`sample-count weighted`消除歧义，无语义偏移 | - | ⬜ 未发现可攻击点 | - |

### 6.2 成立攻击点清单（按严重度排序）

| 优先级 | 攻击点 | 文件 | 行号 | 攻击内容 | R4引入? | 修补建议 |
|--------|--------|------|------|---------|---------|---------|
| P0-轻微 | B2 | run_e6_reliability_diagrams.py | L434 vs L416 | 中文"样本数加权平均"同时描述bin_counts加权和n_total加权，跨函数歧义 | 否（R3遗留） | L416改为"bin内样本数加权平均"或L434中文改为"各方向总样本数加权平均" |
| P0-轻微 | B5 | run_e6_reliability_diagrams.py | L434 vs L460/L465 | 完整字符串不同（`of per-direction`插入），核心术语一致 | 否（R3遗留A1-1） | 可接受（语境差异） |
| P0-轾微 | B1 | run_e6_reliability_diagrams.py | L434 | 中文"样本数加权平均"精度低于L433/L439的"各方向总样本数加权" | 否（R3遗留） | L434中文改为"各方向总样本数加权平均" |
| P0-轾微 | B3 | run_e6_reliability_diagrams.py | L484 | 标题`bin-count`vs`sample-count`均为sample count，粒度歧义 | 否（R3遗留） | 可选：改为`bin-level count`vs`direction-level count` |

---

## 7. 关键发现详述

### 7.1 R4修复本身评价

| 检查项 | 结果 | 说明 |
|--------|------|------|
| L434 英文 `size-weighted` → `sample-count weighted` | ✅ | 已修改 |
| 全局 `.py` 文件无 `size-weighted` 残留 | ✅ | 零匹配 |
| L434 核心术语与 L460/L465/L484 一致 | ✅ | `sample-count weighted mean` 4处一致 |
| `sample-count weighted` 准确描述实际计算 | ✅ | n_total = 样本数 = sample count |
| 注释与代码行为匹配 | ✅ | 注释描述 = `np.average(eces, weights=n_total)` |
| 修改不引入新功能问题 | ✅ | 注释修改不影响运行时 |
| 论文文本无需同步 | ✅ | paper/ 中无相关术语 |
| 其他 .py 文件无需同步 | ✅ | 仅此文件有该术语 |

**结论**：R4 修复**完全达成 stated scope**（L434 注释术语同步），且**未引入任何新问题**。

### 7.2 R3遗留问题分析

R4 修复后仍存在的术语问题（全部为 R3 遗留，非 R4 引入）：

#### B2（P0-轻微）：中文术语跨函数歧义

`样本数加权平均` 在两个函数中描述不同加权：

```python
# L416（_weighted_avg docstring）：
"""样本数加权平均每个 bin 的 accuracy。"""
# 权重 = bin_counts[i]  ← bin 级

# L434（_weighted_ece 注释）：
# 注意：这是各方向 ECE 的样本数加权平均（sample-count weighted mean of per-direction ECE），
# 权重 = n_total  ← 方向级
```

**影响**：开发者搜索 `样本数加权平均` 同时命中两处，需读代码区分粒度。但 L434 有英文括注消除歧义，L416 无英文括注。

**修补建议**（可选）：L416 改为 `"""bin 内样本数加权平均每个 bin 的 accuracy。"""`（与 L400 `bin 内样本数加权平均` 对齐）。

#### B5（P0-轻微）：L434 vs L460/L465 完整字符串不同

L434 含 `of per-direction`，L460/L465 不含。此即 R3 轮 A1-1，R3 终审判定"语境差异合理，非缺陷"。R4 修复未改变此状况。

**判定**：可接受（注释比图例更详细是合理的）。

---

## 8. 对R4修复的总体评价

### 8.1 R3终审遗留A1-2是否完全消除？

**R3 终审 A1-2（P0-中等）**：L434 注释仍用 `size-weighted mean of per-direction ECE`，与 L460/L465/L484 的 `sample-count weighted mean` 术语不一致。

**R4 修复后**：L434 改为 `sample-count weighted mean of per-direction ECE`，核心术语 `sample-count weighted mean` 与 L460/L465/L484 一致。

**判定**：✅ **A1-2 完全消除**。R3 终审遗留的 P0-中等攻击点已由 R4 修复。

### 8.2 R4是否引入新问题？

| 检查项 | 结果 |
|--------|------|
| 新功能 bug | ❌ 无（注释修改） |
| 新术语不一致 | ❌ 无（核心术语4处一致） |
| 新语义偏移 | ❌ 无（`sample-count`比`size`更精确） |
| 新量级错误 | ❌ 无（不涉及计算） |
| 新边界失效 | ❌ 无（注释不影响运行时） |

**判定**：✅ R4 修复**未引入任何新问题**。

### 8.3 收敛趋势

| 轮次 | P0-8 必修项 | 严重程度 | 状态 |
|------|-----------|---------|------|
| R1→R2 | 2项（1严重+1中等） | 严重 | R2修复引入新不一致 |
| R2→R3 | 2项（1严重+1中等） | 严重 | R3修复统一3处字符串，遗漏L434注释 |
| R3→R4 | 1项（1中等） | 中等 | R4修复L434注释术语 |
| R4→R5(预期) | 0项必修 | - | **已收敛**（仅剩R3遗留轻微建议项） |

**判定**：P0-8 经 R4 修复后**已收敛**。P0-致命/P0-严重/P0-中等攻击点全部清零，仅剩 4 个 P0-轻微/P0-轾微建议项（全部为 R3 遗留，非 R4 引入，可选修复）。

---

## 9. R5修复建议

### 9.1 必修项

**无**。R4 修复已完全消除 R3 终审遗留的 P0-中等攻击点（A1-2），未引入新问题。

### 9.2 可选改进项（P0-轻微，全部为R3遗留）

| 序号 | 攻击点 | 文件 | 行号 | 改动内容 | 改动量 | 优先级 |
|------|--------|------|------|---------|--------|--------|
| 1 | B2 | run_e6_reliability_diagrams.py | L416 | `样本数加权平均` → `bin 内样本数加权平均`（与L400对齐，消除跨函数歧义） | 1行 | 轻微 |
| 2 | B1 | run_e6_reliability_diagrams.py | L434 | 中文`样本数加权平均` → `各方向总样本数加权平均`（与L433/L439精度对齐） | 1行 | 轾微 |
| 3 | B3 | run_e6_reliability_diagrams.py | L484 | `bin-count` → `bin-level count`，`sample-count` → `direction-level count`（消除粒度歧义） | 1行 | 轾微 |
| 4 | B5 | - | - | 无需修复（语境差异合理） | 0行 | - |

### 9.3 不需修复（已验证正确）

| 检查项 | 结论 |
|--------|------|
| L434 英文术语同步 | ✅ 已完成 |
| 全局 `size-weighted` 清除 | ✅ 零残留 |
| 核心术语4处一致 | ✅ `sample-count weighted mean` |
| `sample-count weighted` 准确性 | ✅ n_total = sample count |
| 注释与代码行为匹配 | ✅ |
| 论文文本同步 | ✅ 无需同步 |
| 其他 .py 文件同步 | ✅ 无需同步 |

---

## 10. 置信度评估

**置信度：高**

理由：
- L434 当前内容经 `read` 工具直接读取确认，R4 修复已应用 ✅
- 全局 `size-weighted` 搜索经 `grep` 工具确认零 `.py` 匹配，非臆测 ✅
- `sample-count weighted` 4 处出现位置经 `grep` 全局搜索确认 ✅
- 论文文本检查经 `grep` 搜索 `paper/` 目录确认无相关术语 ✅
- 实际计算 `np.average(eces, weights=n_total)` 与术语 `sample-count weighted` 的匹配性经代码逻辑验证 ✅
- 所有"R3遗留"判定均基于 R3 终审报告 `docs/p0r3_final_verdict.md` 的明确记录 ✅

**残余疑点**：
- B2（中文跨函数歧义）是否需 R5 修复取决于团队对中文术语精度的要求——英文已一致，中文歧义不影响代码正确性
- B3（标题粒度歧义）是否需 R5 修复取决于审稿人对 `bin-count` vs `sample-count` 命名的严格程度——上下文已约束语义

---

## 11. 反方声明

我尝试了全部 7 个攻击维度（反例构造、逻辑断链、隐含假设、边界失效、自相矛盾、量级错误、语义偏移），找到 **4 个成立攻击点**（2 个 P0-轻微 + 2 个 P0-轾微）和 **3 个未发现可攻击点的维度**。

**关键发现**：
1. R4 修复的 stated scope（L434 注释英文术语 `size-weighted` → `sample-count weighted`）**完全达成**
2. R3 终审遗留的 P0-中等攻击点（A1-2）**已完全消除**
3. R4 修复**未引入任何新问题**（注释修改不影响运行时，核心术语4处一致，术语准确性提升）
4. 全局 `.py` 文件中 `size-weighted` **零残留**
5. 论文文本和其他 .py 文件**无需同步修改**
6. 剩余 4 个攻击点**全部为 R3 遗留**（B1/B2/B3/B5），非 R4 引入，均为 P0-轻微或更轻

**最终判定**：P0-8 R4 修复**通过**。R3 终审遗留的 P0-中等攻击点（A1-2）已完全消除，R4 未引入新问题。P0-8 已收敛——P0-致命/P0-严重/P0-中等攻击点全部清零，仅剩 4 个 P0-轻微/P0-轾微可选建议项（全部为 R3 遗留）。

**攻击点数量**：4 个成立（2 轻微 + 2 轻微），3 个维度未发现可攻击点。
**严重程度分布**：0 致命 + 0 严重 + 0 中等 + 2 轻微 + 2 轻微 = 4 个全部为轻微或更轻。
**R4 引入的新攻击点**：0 个。
