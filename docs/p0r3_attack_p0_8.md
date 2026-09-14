# P0-8 R3轮反方攻击报告

> **反方挑刺代理交付**（任务 #98）。本报告对正方论证代理完成的 P0-8 R3 修复进行全方位攻击审查。
> **审查日期**：2026-09-09
> **审查代理**：反方挑刺代理（GLM-5.2）
> **审查对象**：`scripts/run_e6_reliability_diagrams.py` 的 2 个 R3 修复点
> **审查标准**：7 个攻击维度全覆盖，每个维度要么找到具体攻击点，要么明确记录"未发现可攻击点"

---

## 0. R3修复内容回顾

根据 `docs/p0r2_final_verdict.md` 第 2.4 节，R3 修复要求 2 项：

| 序号 | 优先级 | 修复点 | 文件 | 行号（R2时） | 改动内容 |
|------|--------|--------|------|-------------|---------|
| 1 | P0-严重 | A1: 标题vs图例术语不一致 | run_e6_reliability_diagrams.py | L454/L459/L478 | 3处统一为 `sample-count weighted mean ECE` |
| 2 | P0-中等 | A3: nan过滤静默无警告 | run_e6_reliability_diagrams.py | L444前 | 加 `warnings.warn` 提示被过滤方向 |

正方声称已完成上述 2 个修复点。以下逐条攻击。

---

## 1. 修复点1攻击：3处字符串统一

### 1.1 实际代码验证

读取 `scripts/run_e6_reliability_diagrams.py` 当前内容，3 处字符串的实际行号和内容（因 R3 新增 6 行 warnings 代码，行号从 L454/L459/L478 偏移至 L460/L465/L484）：

| 行号 | 位置 | 实际字符串 | 包含的术语 |
|------|------|-----------|-----------|
| L460 | 图例（Before TS） | `f"Before TS (sample-count weighted mean ECE={ece_before:.3f})"` | `sample-count weighted mean ECE` |
| L465 | 图例（After TS） | `f"After TS (sample-count weighted mean ECE={ece_after:.3f})"` | `sample-count weighted mean ECE` |
| L484 | 标题 | `f"(curve: bin-count weighted; ECE: sample-count weighted mean; {REP_ARCH}, seed{REP_SEED})"` | `ECE: sample-count weighted mean` |

### 1.2 攻击点A1-1：3处字符串并未统一为完全相同的字符串（P0-轻微）

**攻击维度**：语义偏移 + 自相矛盾

**攻击**：R3 修复要求"3处字符串统一为 `sample-count weighted mean ECE`"，但实际代码中 3 处字符串**并非完全相同**：

- L460/L465（图例）：`sample-count weighted mean ECE`（ECE 在末尾）
- L484（标题）：`ECE: sample-count weighted mean`（ECE 在开头，带冒号）

字符串比较验证：
```python
>>> "sample-count weighted mean ECE" == "ECE: sample-count weighted mean"
False
```

**反例**：读者看到图例 `Before TS (sample-count weighted mean ECE=0.123)` 和标题 `ECE: sample-count weighted mean`，需要额外认知努力才能确认两者描述的是同一种加权方式。在论文图注中，术语不一致可能被审稿人质疑。

**严重程度**：轻微。理由：标题和图例的语法语境不同——标题需要同时区分"曲线加权"（bin-count weighted）和"ECE加权"（sample-count weighted mean），因此 `ECE:` 前缀是结构化标注，非术语不一致。核心术语 `sample-count weighted mean` 在 3 处一致。但严格按 R3 修复要求"统一为 `sample-count weighted mean ECE`"，标题处并未达到此精确字符串。

### 1.3 攻击点A1-2（致命发现）：L434注释仍用旧术语"size-weighted"（P0-中等）

**攻击维度**：自相矛盾 + 语义偏移

**攻击**：R3 修复统一了用户可见的 3 处字符串（L460/L465/L484），但**遗漏了 L434 的内部注释**，该注释仍使用旧术语 `size-weighted`：

```python
# L433-437 实际代码：
# 方向级加权平均 ECE（按各方向总样本数加权）
# 注意：这是各方向 ECE 的样本数加权平均（size-weighted mean of per-direction ECE），
# 非合并所有样本后重算的全局 ECE。Guo et al. 2017 的原始 ECE 定义是单模型
# bin 级加权 Σ_b(n_b/N)×|acc(b)-conf(b)|，不适用于多方向汇总。
# 方向级加权平均 ECE ≠ 全局 ECE（因 ECE 含绝对值，|x|+|y| ≠ |x+y|）。
```

**证据**：`grep "size-weighted" scripts/run_e6_reliability_diagrams.py` 返回 L434：
```
434:     # 注意：这是各方向 ECE 的样本数加权平均（size-weighted mean of per-direction ECE），
```

**反例**：开发者阅读代码时，L434 注释说 `size-weighted mean`，L460 图例说 `sample-count weighted mean ECE`。开发者会困惑：注释中的 `size-weighted` 和图例中的 `sample-count weighted` 是同一种加权吗？还是两种不同的加权方式？这正是 R2 轮 A1 攻击点的同一矛盾——**术语不一致**——只是从"标题vs图例"转移到了"注释vs图例"。

**严重程度**：中等。理由：
1. 注释是代码可维护性的关键部分，术语不一致会误导后续开发者
2. R2 轮反反方审查报告（`docs/p0r2_counter_p0_8.md` L340）已将注释改为 `sample-count weighted mean of per-direction ECE`，但正方 R3 修复**未同步此改动到源代码**
3. 这是"修复用户可见字符串但遗漏内部注释"的典型疏漏，属于修复不完整

**修补建议**：L434 将 `size-weighted mean of per-direction ECE` 改为 `sample-count weighted mean of per-direction ECE`。

### 1.4 攻击点A1-3：单方向图（plot_reliability_enhanced）的ECE标签无"weighted"限定词（P0-轻微，非缺陷）

**攻击维度**：语义偏移

**攻击**：单方向可靠性图（`plot_reliability_enhanced` 函数）的图例标签为：

```python
# L327:
f"Before TS (ECE={bins_before['ece']:.3f})"
# L332:
f"After TS (ECE={bins_after['ece']:.3f})"
```

而汇总图（`plot_summary` 函数）的图例标签为：

```python
# L460:
f"Before TS (sample-count weighted mean ECE={ece_before:.3f})"
# L465:
f"After TS (sample-count weighted mean ECE={ece_after:.3f})"
```

**分析**：单方向图显示单个方向的 ECE（非加权平均），标签 `ECE=0.123` 正确。汇总图显示 6 方向的样本数加权平均 ECE，标签 `sample-count weighted mean ECE=0.123` 正确。两者语境不同，标签差异是**正确的语义区分**，非缺陷。

**判定**：该维度未发现可攻击点。标签差异反映的是计算语义的真实差异（单方向 ECE vs 多方向加权平均 ECE）。

### 1.5 攻击点A1-4：全局搜索确认无其他文件引用旧字符串（P0-轻微，非缺陷）

**攻击维度**：边界失效

**攻击**：全局搜索 `*.py` 文件中的 `size-weighted mean ECE`、`n_total-weighted`、`weighted avg ECE`：

```
grep "size-weighted|n_total-weighted|weighted avg ECE" --include="*.py" D:\A1\ecg-lab-v2
```

结果：仅 `scripts/run_e6_reliability_diagrams.py` L434 的注释中残留 `size-weighted`（见攻击点A1-2）。无其他 `.py` 文件引用旧字符串。

**判定**：除 A1-2 已记录的 L434 注释残留外，无其他文件引用旧字符串。该维度基本通过。

---

## 2. 修复点2攻击：nan过滤warnings.warn

### 2.1 实际代码验证

```python
# L438-452 实际代码：
def _weighted_ece(bins_list):
    """按各方向总样本数加权平均 ECE（过滤 nan 方向）。"""
    weights = np.array([b["n_total"] for b in bins_list], dtype=float)
    eces = np.array([b["ece"] for b in bins_list], dtype=float)
    # 过滤 nan 和零权重方向，防止 nan 传播
    valid = np.isfinite(eces) & (weights > 0)
    if not valid.all():
        excluded = np.where(~valid)[0]
        warnings.warn(
            f"_weighted_ece: {len(excluded)} 方向因 ECE=nan/inf 或 n_total=0 被排除: {excluded.tolist()}",
            UserWarning, stacklevel=2
        )
    if not valid.any():
        return float("nan")
    return float(np.average(eces[valid], weights=weights[valid]))
```

### 2.2 攻击点A2-1：warnings.warn的stacklevel=2是否正确（P0-轻微，非缺陷）

**攻击维度**：边界失效

**攻击**：`stacklevel=2` 是否指向调用方而非定义方？

调用链分析：
```
main() (L855)
  → generate_figures() (L838调用)
    → plot_summary() (L772调用)
      → _weighted_ece() (L454/L455调用)
        → warnings.warn() (L446)
```

Python `warnings.warn` 的 `stacklevel` 语义：
- `stacklevel=1`：指向 `warnings.warn` 调用行本身（L446，在 `_weighted_ece` 内部）
- `stacklevel=2`：指向调用 `_weighted_ece` 的行（L454 或 L455，在 `plot_summary` 内部）
- `stacklevel=3`：指向调用 `plot_summary` 的行（L772，在 `generate_figures` 内部）

**验证**：`stacklevel=2` 指向 L454/L455（`_weighted_ece` 的调用方），这是正确的——告知用户警告来自 `plot_summary` 中的 `_weighted_ece` 调用，而非 `_weighted_ece` 的定义处。

**判定**：该维度未发现可攻击点。`stacklevel=2` 正确指向调用方。

### 2.3 攻击点A2-2：warnings.warn是否在正常路径误触发（P0-轻微，非缺陷）

**攻击维度**：边界失效 + 隐含假设

**攻击**：`warnings.warn` 是否在正常实验路径下误触发？

`valid = np.isfinite(eces) & (weights > 0)` 为 False 的条件：
1. `eces` 包含 nan 或 inf
2. `weights` 包含 0 或负数

正常实验路径下：
- `weights = [b["n_total"] for b in bins_list]`，`n_total = len(confidence)`，恒为正整数（OOD 测试集非空）
- `eces = [b["ece"] for b in bins_list]`，ECE 在 `n_total > 0` 时有界 ∈ [0, 1]（因 `Σ_b(n_b/N)×|acc-conf|`，每项 ∈ [0, 1/N]，共 N 项，总和 ∈ [0, 1]）

因此正常路径下 `valid.all() == True`，`not valid.all()` 为 False，**不会触发 warnings.warn**。

**反例验证**：仅在以下异常路径触发：
- OOD 测试集为空（`n_total = 0`）→ `ece = nan`（L188 的 `else float("nan")` 分支）且 `weight = 0`
- 这是真实的异常情况，警告正确触发

**判定**：该维度未发现可攻击点。正常路径不误触发。

### 2.4 攻击点A2-3：警告消息声称"ECE=nan/inf"但inf在当前代码路径下不可能产生（P0-轻微）

**攻击维度**：自相矛盾 + 量级错误

**攻击**：L447 警告消息为：
```python
f"_weighted_ece: {len(excluded)} 方向因 ECE=nan/inf 或 n_total=0 被排除: {excluded.tolist()}"
```

消息声称 `ECE=nan/inf`，但分析 `compute_reliability_bins` 的 ECE 计算（L183-188）：

```python
# L183-188:
valid = bin_counts > 0
ece_val = float(
    np.sum(bin_counts[valid] / n_total *
           np.abs(bin_confidences[valid] - bin_accuracies[valid]))
) if n_total > 0 else float("nan")
```

当 `n_total > 0` 时：
- `bin_counts[valid] / n_total`：每项 ∈ [0, 1]（因 `bin_counts[valid] ≤ n_total`）
- `np.abs(bin_confidences[valid] - bin_accuracies[valid])`：每项 ∈ [0, 1]（因 confidence 和 accuracy 都 ∈ [0, 1]）
- 乘积：每项 ∈ [0, 1]
- 求和：最多 10 项（`N_BINS=10`），总和 ∈ [0, 10]

**但实际更紧的界**：`Σ_b(n_b/N)×|acc-conf| ≤ Σ_b(n_b/N)×1 = Σ_b(n_b/N) = 1`（因 `Σ_b n_b = N`）。所以 ECE ∈ [0, 1]，**不可能为 inf**。

当 `n_total == 0` 时：`ece_val = float("nan")`，为 nan 而非 inf。

**结论**：当前代码路径下 ECE 只可能是有限值或 nan，**不可能为 inf**。警告消息中的 `/inf` 是防御性写法但**语义不准确**——它暗示 inf 是可能的，实际上不可能。

**严重程度**：轻微。理由：这是防御性过度描述，不影响功能正确性。但作为论文实验代码，警告消息应精确描述实际可能的异常条件。

**修补建议**：L447 将 `ECE=nan/inf` 改为 `ECE=nan`（因 inf 在当前代码路径下不可能产生）。

### 2.5 攻击点A2-4：警告触发两次且消息完全相同，无法区分before/after（P0-轻微）

**攻击维度**：自相矛盾 + 语义偏移

**攻击**：`_weighted_ece` 在 L454 和 L455 被调用两次：

```python
# L454-455:
ece_before = _weighted_ece(all_bins_before)
ece_after = _weighted_ece(all_bins_after)
```

`all_bins_before` 和 `all_bins_after` 来自同一组 checkpoint（L733-736），具有相同的 `n_total` 值。因此如果某方向 `n_total=0`，则 `bins_b` 和 `bins_a` 的 `n_total` 都为 0，**两次调用都会触发警告**。

**反例**：假设方向 2 的 OOD 测试集为空，用户会看到：
```
UserWarning: _weighted_ece: 1 方向因 ECE=nan/inf 或 n_total=0 被排除: [2]
  ece_before = _weighted_ece(all_bins_before)  # L454
UserWarning: _weighted_ece: 1 方向因 ECE=nan/inf 或 n_total=0 被排除: [2]
  ece_after = _weighted_ece(all_bins_after)    # L455
```

两条警告消息**完全相同**，用户无法从消息本身区分是 `ece_before` 还是 `ece_after` 触发的。虽然 `stacklevel=2` 指向不同行号（L454 vs L455），但消息文本不包含 before/after 上下文。

**严重程度**：轻微。理由：功能正确，仅是日志噪音和可读性问题。但 `all_bins_before` 和 `all_bins_after` 的 `n_total` 恒相同（同一 checkpoint 的 `bins_b` 和 `bins_a` 共享 `n_total`），因此两次警告必然同时触发或同时不触发，冗余警告是**确定性**的而非偶发。

**修补建议**：在 `_weighted_ece` 签名增加 `label` 参数（如 `"before"` / `"after"`），警告消息中包含该标签；或在 `plot_summary` 中统一检查一次后传入已计算的 `valid` 数组。

### 2.6 攻击点A2-5：警告报告的是索引而非方向名，用户无法直接定位问题方向（P0-轻微）

**攻击维度**：隐含假设

**攻击**：L447 警告消息中 `{excluded.tolist()}` 报告的是 `bins_list` 中的索引（如 `[2]`），而非方向名（如 `"cpsc→ptbxl"`）。

`_weighted_ece` 函数签名仅接收 `bins_list`，不接收 `pair_names`，因此无法在警告中包含方向名。

**反例**：用户看到警告 `_weighted_ece: 1 方向因...被排除: [2]`，需要手动查找 `bins_list` 的第 3 个元素对应哪个方向。在 6 方向汇总图中，这需要回溯 `plot_summary` 的调用逻辑（L733-736 的 `summary_names.append(f"{source}→{target}")`），对用户不友好。

**严重程度**：轻微。理由：这是可用性问题而非正确性问题。但作为论文实验代码，警告应尽可能 actionable。

**修补建议**：`_weighted_ece` 增加 `names` 可选参数，警告中输出方向名而非索引。

### 2.7 攻击点A2-6：nan过滤后是否正确跳过nan值继续计算（P0-轻微，非缺陷）

**攻击维度**：逻辑断链 + 边界失效

**攻击**：nan 过滤后的计算逻辑是否正确？

```python
# L443-452:
valid = np.isfinite(eces) & (weights > 0)
if not valid.all():
    # ... warning ...
if not valid.any():
    return float("nan")
return float(np.average(eces[valid], weights=weights[valid]))
```

三种情况验证：
1. **全部有效**（`valid.all() == True`）：不警告，直接 `np.average(eces, weights=weights)` ✓
2. **部分有效**（`valid.any() == True and not valid.all()`）：警告，`np.average(eces[valid], weights=weights[valid])` 跳过无效方向 ✓
3. **全部无效**（`not valid.any()`）：警告，返回 `nan` ✓

**边界情况**：空 `bins_list`：
- `weights = np.array([])`, `eces = np.array([])`, `valid = np.array([])`（空布尔数组）
- `valid.all()` 对空数组返回 `True`（vacuous truth）→ 不警告
- `valid.any()` 对空数组返回 `False` → `not valid.any()` 为 True → 返回 `nan`
- **不触发警告但返回 nan**：这是合理的——空列表无方向可排除，无需警告

**判定**：该维度未发现可攻击点。nan 过滤逻辑在所有边界情况下均正确。

### 2.8 攻击点A2-7：warnings.warn在严格警告模式下会抛异常导致绘图崩溃（P0-轻微）

**攻击维度**：边界失效

**攻击**：如果用户配置了 `warnings.filterwarnings("error")`（将警告转为异常），则 `warnings.warn(..., UserWarning)` 会抛出 `UserWarning` 异常，导致 `plot_summary` 中断，汇总图无法生成。

**反例**：
```python
import warnings
warnings.filterwarnings("error")
# ... 运行 run_e6_reliability_diagrams.py --plot ...
# 若某方向 n_total=0，则 UserWarning 被抛出，plot_summary 崩溃
```

**严重程度**：轻微。理由：这是用户主动配置的严格模式，非默认行为。但论文实验脚本应考虑在警告后继续执行而非中断——当前代码在默认配置下正确（警告不中断），但在严格配置下可能崩溃。

**修补建议**：可选——将 `warnings.warn` 改为 `print` + 继续执行，或在 `plot_summary` 中 `try/except UserWarning` 捕获后继续。但这会降低警告的可见性，需权衡。

---

## 3. 全维度攻击汇总

### 3.1 攻击维度覆盖表

| 维度 | 编号 | 攻击点 | 严重程度 | 是否成立 |
|------|------|--------|---------|---------|
| 1.反例构造 | A1-2 | L434注释仍用"size-weighted"，与L460图例"sample-count weighted"矛盾 | 中等 | ✅ 成立 |
| 1.反例构造 | A2-5 | 警告报告索引非方向名，用户无法定位 | 轻微 | ✅ 成立 |
| 2.逻辑断链 | A2-7 | 严格警告模式下warnings.warn抛异常导致绘图崩溃 | 轻微 | ✅ 成立 |
| 3.隐含假设 | A2-3 | 警告消息声称"ECE=nan/inf"但inf不可能产生 | 轻微 | ✅ 成立 |
| 3.隐含假设 | A2-5 | _weighted_ece无names参数，隐含假设用户能从索引推断方向 | 轻微 | ✅ 成立 |
| 4.边界失效 | A1-4 | 全局搜索确认无其他文件引用旧字符串 | - | ⬜ 未发现可攻击点 |
| 4.边界失效 | A2-2 | 正常路径不误触发警告 | - | ⬜ 未发现可攻击点 |
| 4.边界失效 | A2-6 | nan过滤在空/部分/全部无效三种边界均正确 | - | ⬜ 未发现可攻击点 |
| 5.自相矛盾 | A1-1 | L460/L465用"sample-count weighted mean ECE"，L484用"ECE: sample-count weighted mean" | 轻微 | ✅ 成立（但语境差异合理） |
| 5.自相矛盾 | A2-4 | 警告触发两次且消息完全相同，无法区分before/after | 轻微 | ✅ 成立 |
| 6.量级错误 | A2-3 | ECE有界∈[0,1]，不可能为inf，消息中"/inf"为量级错误描述 | 轻微 | ✅ 成立（与A2-3合并） |
| 7.语义偏移 | A1-2 | 注释"size-weighted"vs代码"sample-count weighted"术语偏移 | 中等 | ✅ 成立（与A1-2合并） |
| 7.语义偏移 | A1-3 | 单方向图"ECE"vs汇总图"sample-count weighted mean ECE" | - | ⬜ 未发现可攻击点（正确语义区分） |
| - | A2-1 | stacklevel=2正确指向调用方 | - | ⬜ 未发现可攻击点 |

### 3.2 成立攻击点清单（按严重度排序）

| 优先级 | 攻击点 | 文件 | 行号 | 攻击内容 | 修补建议 |
|--------|--------|------|------|---------|---------|
| **P0-中等** | A1-2 | run_e6_reliability_diagrams.py | L434 | 注释仍用 `size-weighted mean of per-direction ECE`，与L460/L465/L484的 `sample-count weighted mean` 术语不一致 | L434 改为 `sample-count weighted mean of per-direction ECE` |
| P0-轻微 | A1-1 | run_e6_reliability_diagrams.py | L460/L465 vs L484 | 图例 `sample-count weighted mean ECE` vs 标题 `ECE: sample-count weighted mean`，非完全相同字符串 | 可接受（语境差异），或标题改为 `sample-count weighted mean ECE` 统一 |
| P0-轻微 | A2-3 | run_e6_reliability_diagrams.py | L447 | 警告消息 `ECE=nan/inf` 中 inf 不可能产生（ECE有界∈[0,1]） | 改为 `ECE=nan` |
| P0-轻微 | A2-4 | run_e6_reliability_diagrams.py | L454/L455 | 警告触发两次且消息完全相同，无法区分 before/after | _weighted_ece 增加 label 参数 |
| P0-轻微 | A2-5 | run_e6_reliability_diagrams.py | L447 | 警告报告索引 `[2]` 而非方向名 `"cpsc→ptbxl"` | _weighted_ece 增加 names 参数 |
| P0-轻微 | A2-7 | run_e6_reliability_diagrams.py | L446-449 | 严格警告模式 `filterwarnings("error")` 下会抛异常崩溃 | 可选：改用 print 或 try/except |

---

## 4. 关键攻击点详述

### 4.1 A1-2（P0-中等）：L434注释术语未统一——R3修复遗漏

这是本轮**最严重的攻击点**。

**证据链**：
1. R2 轮反反方审查报告 `docs/p0r2_counter_p0_8.md` L340 已将注释改为 `sample-count weighted mean of per-direction ECE`
2. 但正方 R3 修复**仅修改了用户可见的 3 处字符串（L460/L465/L484），未同步修改 L434 注释**
3. `grep "size-weighted" scripts/run_e6_reliability_diagrams.py` 确认 L434 仍为 `size-weighted mean of per-direction ECE`

**具体代码证据**：

```python
# L433-437（当前代码，R3修复后）：
# 方向级加权平均 ECE（按各方向总样本数加权）
# 注意：这是各方向 ECE 的样本数加权平均（size-weighted mean of per-direction ECE），  ← 旧术语
# 非合并所有样本后重算的全局 ECE。Guo et al. 2017 的原始 ECE 定义是单模型
# bin 级加权 Σ_b(n_b/N)×|acc(b)-conf(b)|，不适用于多方向汇总。
# 方向级加权平均 ECE ≠ 全局 ECE（因 ECE 含绝对值，|x|+|y| ≠ |x+y|）。
```

对比 L460（R3 修复后）：
```python
label=f"Before TS (sample-count weighted mean ECE={ece_before:.3f})", zorder=3)
#                          ^^^^^^^^^^^^^^^^^^^^^^^^ 新术语
```

**矛盾**：同一函数内，注释用 `size-weighted`，图例用 `sample-count weighted`，描述的是同一种加权方式。

**影响**：
- 开发者维护代码时被注释误导
- R2 轮 A1 攻击点（术语不一致）未完全消除，只是从"标题vs图例"转移到了"注释vs图例"
- 违反 R3 修复目标"3处字符串统一"——实际应统一所有出现该术语的位置，包括注释

**修补建议**：
```python
# L434 改为：
# 注意：这是各方向 ECE 的样本数加权平均（sample-count weighted mean of per-direction ECE），
```

### 4.2 A2-3（P0-轻微）：警告消息中"inf"为不可能条件

**数学证明 ECE 有界**：

`compute_reliability_bins` 中 ECE 计算（L183-188）：
```
ECE = Σ_b (n_b / N) × |acc(b) - conf(b)|
```

其中：
- `n_b` = bin b 内样本数 ≥ 0
- `N` = 总样本数 > 0（当 N=0 时 ece=nan，非 inf）
- `acc(b)` = bin b 内正确率 ∈ [0, 1]
- `conf(b)` = bin b 内平均置信度 ∈ [0, 1]
- `|acc(b) - conf(b)|` ∈ [0, 1]

因此：
```
ECE = Σ_b (n_b / N) × |acc(b) - conf(b)|
    ≤ Σ_b (n_b / N) × 1
    = Σ_b (n_b / N)
    = (Σ_b n_b) / N
    = N / N
    = 1
```

且 ECE ≥ 0（每项非负），所以 **ECE ∈ [0, 1]**，不可能为 inf。

警告消息 `ECE=nan/inf` 中的 `/inf` 是**防御性过度描述**，暗示了一个不可能发生的条件。

---

## 5. 对R3修复的总体评价

### 5.1 修复点1（3处字符串统一）评价

| 检查项 | 结果 | 说明 |
|--------|------|------|
| L460 图例改为 `sample-count weighted mean ECE` | ✅ | 已修改 |
| L465 图例改为 `sample-count weighted mean ECE` | ✅ | 已修改 |
| L484 标题改为 `sample-count weighted mean` | ✅ | 已修改（但词序与图例不同） |
| L434 注释同步修改 | ❌ | **遗漏**——仍用 `size-weighted` |
| 3处字符串完全相同 | ⚠️ | 图例和标题词序不同（语境差异，可接受） |
| 全局无其他旧术语残留 | ⚠️ | L434 注释残留 `size-weighted` |

**结论**：修复点1**部分完成**。用户可见的 3 处字符串已统一，但 L434 注释遗漏，术语不一致从"标题vs图例"转移至"注释vs图例"。

### 5.2 修复点2（nan过滤warnings.warn）评价

| 检查项 | 结果 | 说明 |
|--------|------|------|
| warnings.warn 已插入 | ✅ | L444-449 |
| 触发条件正确（`not valid.all()`） | ✅ | 仅在有无效方向时触发 |
| 正常路径不误触发 | ✅ | 正常路径 n_total>0 且 ECE 有限 |
| stacklevel=2 指向调用方 | ✅ | 指向 L454/L455 |
| nan 过滤后正确跳过继续计算 | ✅ | 三种边界情况均正确 |
| 警告消息精确描述异常条件 | ⚠️ | `ECE=nan/inf` 中 inf 不可能产生 |
| 警告可区分 before/after | ❌ | 两次调用消息完全相同 |
| 警告可定位问题方向 | ⚠️ | 报告索引而非方向名 |
| 严格警告模式下不崩溃 | ⚠️ | `filterwarnings("error")` 下抛异常 |

**结论**：修复点2**核心逻辑正确完成**，但警告消息的精确性和可用性有改进空间。

### 5.3 R3修复是否收敛

**部分收敛**：
- R2 轮 A1 攻击点（标题vs图例术语不一致）：**已消除**（L460/L465/L484 已统一为 `sample-count weighted mean`）
- R2 轮 A3 攻击点（nan过滤静默无警告）：**已消除**（L444-449 已加 warnings.warn）
- **但引入了新的遗留**：L434 注释术语未同步（A1-2，P0-中等）

---

## 6. R4修复建议

### 6.1 必修1项（P0-中等）

| 序号 | 攻击点 | 文件 | 行号 | 改动内容 | 改动量 |
|------|--------|------|------|---------|--------|
| 1 | A1-2 | run_e6_reliability_diagrams.py | L434 | `size-weighted mean of per-direction ECE` → `sample-count weighted mean of per-direction ECE` | 1行 |

### 6.2 建议项（P0-轻微，可选）

| 序号 | 攻击点 | 文件 | 行号 | 改动内容 | 改动量 |
|------|--------|------|------|---------|--------|
| 2 | A2-3 | run_e6_reliability_diagrams.py | L447 | `ECE=nan/inf` → `ECE=nan`（inf不可能产生） | 1行 |
| 3 | A2-4 | run_e6_reliability_diagrams.py | L438/L446-449 | _weighted_ece 增加 `label` 参数，警告消息含 before/after | 4行 |
| 4 | A2-5 | run_e6_reliability_diagrams.py | L438/L446-449 | _weighted_ece 增加 `names` 参数，警告报告方向名 | 3行 |

### 6.3 不需修复（已验证正确）

| 攻击点 | 结论 |
|--------|------|
| A1-1（图例vs标题词序） | 语境差异合理，核心术语一致 |
| A1-3（单方向图vs汇总图标签） | 正确语义区分 |
| A1-4（全局旧字符串残留） | 除L434外无残留 |
| A2-1（stacklevel=2） | 正确指向调用方 |
| A2-2（正常路径误触发） | 不误触发 |
| A2-6（nan过滤边界） | 三种边界均正确 |
| A2-7（严格警告模式崩溃） | 用户配置选择，非代码缺陷 |

---

## 7. 置信度评估

**置信度：高**

理由：
- 所有攻击点均基于 `read`/`grep` 工具直接读取源代码，证据扎实
- L434 注释残留 `size-weighted` 经 `grep` 全局搜索确认，非臆测
- ECE 有界性证明（∈[0,1]）基于代码逻辑数学推导，非推测
- stacklevel 语义分析基于 Python 官方文档
- 三种边界情况（空/部分/全部无效）均经逻辑验证

**残余疑点**：
- A1-1（图例vs标题词序）是否构成"术语不一致"取决于审稿人严格程度——核心术语 `sample-count weighted mean` 一致，但完整字符串不同。建议反反方裁决时考虑语境差异。

---

## 8. 反方声明

我尝试了全部 7 个攻击维度（反例构造、逻辑断链、隐含假设、边界失效、自相矛盾、量级错误、语义偏移），找到 **6 个成立攻击点**（1 个 P0-中等 + 5 个 P0-轻微）和 **7 个未发现可攻击点的维度**。

**关键发现**：
- R3 修复的 2 个核心目标（3处字符串统一 + nan过滤警告）**核心逻辑已达成**
- 但修复点1**遗漏了 L434 注释的术语同步**，导致术语不一致从"标题vs图例"转移至"注释vs图例"（P0-中等）
- 修复点2的警告消息**精确性不足**（声称 inf 可能但实际不可能）且**可用性不足**（报告索引非方向名、两次触发消息相同）

**最终判定**：P0-8 R3 修复**部分通过**——核心修复达成，但需 R4 轮修复 1 个 P0-中等遗留（L434 注释术语同步）+ 可选修复 3 个 P0-轻微改进。R4 必修量：1 行改动。
