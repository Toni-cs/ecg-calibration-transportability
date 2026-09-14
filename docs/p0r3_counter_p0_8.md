# 反反方审查：P0-8 R3修复攻击审查

## 审查摘要
- 攻击报告：docs/p0r3_attack_p0_8.md
- 审查文件：scripts/run_e6_reliability_diagrams.py
- 攻击点总数：11
- 成立：4（A1-2 中等, A2-3 轻微, A2-4 轻微, A2-5 轻微）
- 不成立：6（A1-3, A1-4, A2-1, A2-2, A2-6, A2-7）
- 部分成立：1（A1-1）

**审查方法**：逐条对照源文件 `scripts/run_e6_reliability_diagrams.py` 实际代码验证反方主张，对每个攻击点执行 5 维审查（反例成立性、稻草人论证、误解前提、攻击逻辑自洽、严重程度夸大）。

---

## 逐条审查

### 攻击点A1-1：3处字符串并未统一为完全相同的字符串（P0-轻微）

**判定**：部分成立

**理由**：
反方事实陈述准确——L460/L465 用 `sample-count weighted mean ECE`（ECE 在末尾），L484 用 `ECE: sample-count weighted mean`（ECE 在开头带冒号）。字符串确实不完全相同：

```python
>>> "sample-count weighted mean ECE" == "ECE: sample-count weighted mean"
False
```

但反方自己已承认"语境差异合理"，并标注为 P0-轻微。审查维度5（严重程度夸大）分析：

1. **标题语境**：L484 标题需同时区分两种加权——`curve: bin-count weighted`（曲线加权）和 `ECE: sample-count weighted mean`（ECE 加权）。`ECE:` 前缀是结构化标注，用于在同一个标题中并列两种不同加权方式。
2. **图例语境**：L460/L465 图例只需描述一种加权（ECE 加权），无需前缀区分。
3. **核心术语一致**：3 处都包含核心术语 `sample-count weighted mean`，差异仅在 ECE 的位置和是否带冒号——这是语法结构差异，非术语不一致。

**反驳（针对"应统一为完全相同字符串"的隐含主张）**：
若强行将 L484 标题改为 `sample-count weighted mean ECE`，会破坏标题中 `curve: bin-count weighted; ECE: sample-count weighted mean` 的并列结构，反而降低可读性。R3 修复要求"3处统一为 `sample-count weighted mean ECE`"应理解为**核心术语统一**，而非**字节级字符串相同**——否则标题无法承载双重加权标注。

**结论**：字符串确实不同（事实成立），但这是合理的语境差异，非缺陷。不需修复。

---

### 攻击点A1-2：L434注释仍用旧术语"size-weighted"（P0-中等）

**判定**：成立

**理由**：
反方主张经源代码直接验证为真。L434 实际内容：

```python
# 注意：这是各方向 ECE 的样本数加权平均（size-weighted mean of per-direction ECE），
```

而 L460 图例为 `sample-count weighted mean ECE`。同一函数 `plot_summary` 内：
- L434 注释说 `size-weighted mean`
- L460/L465/L484 用户可见字符串说 `sample-count weighted`

两者描述的是**同一种加权方式**（按各方向总样本数加权平均 ECE），但用了不同术语。

**5 维审查均通过**：
1. 反例成立：开发者阅读代码时会困惑 `size-weighted` 和 `sample-count weighted` 是否同一种加权
2. 非稻草人：反方攻击的是真实的代码事实，经 grep 验证
3. 未误解前提：R3 修复目标是消除术语不一致，注释术语不一致属于同一问题范畴
4. 攻击逻辑自洽：R2 轮 A1 攻击点是"标题vs图例术语不一致"，R3 修复了用户可见字符串但遗漏注释，问题转移至"注释vs图例"，逻辑链完整
5. 严重程度未夸大：反方标注 P0-中等合理——注释是代码可维护性的关键部分，术语不一致会误导后续开发者

**修补方案**：
- 文件：`scripts/run_e6_reliability_diagrams.py`
- 行号：L434
- 改动：`size-weighted mean of per-direction ECE` → `sample-count weighted mean of per-direction ECE`
- 改动量：1 行

```python
# L434 改前：
# 注意：这是各方向 ECE 的样本数加权平均（size-weighted mean of per-direction ECE），

# L434 改后：
# 注意：这是各方向 ECE 的样本数加权平均（sample-count weighted mean of per-direction ECE），
```

---

### 攻击点A1-3：单方向图的ECE标签无"weighted"限定词（P0-轻微，非缺陷）

**判定**：不成立

**理由**：
反方自己已判定"未发现可攻击点"，认为这是正确的语义区分。审查确认：

- L327 `f"Before TS (ECE={bins_before['ece']:.3f})"` — 单方向图，显示单个方向的 ECE（非加权平均），标签 `ECE=0.123` 正确
- L460 `f"Before TS (sample-count weighted mean ECE={ece_before:.3f})"` — 汇总图，显示 6 方向的样本数加权平均 ECE，标签含 `weighted mean` 正确

两者语境不同：单方向图是单个方向的 ECE，无需"weighted"限定；汇总图是多方向加权平均 ECE，需"weighted mean"区分。标签差异反映的是**计算语义的真实差异**，非术语不一致。

**反驳**：反方在此维度未找到可攻击点，此条实质上是反方为覆盖全维度而列出的"未发现"记录，非真实攻击。

---

### 攻击点A1-4：全局搜索确认无其他文件引用旧字符串（P0-轻微，非缺陷）

**判定**：不成立

**理由**：
反方自己已判定"基本通过"，除 L434 注释残留（已由 A1-2 记入）外，无其他 `.py` 文件引用旧字符串。此条实质上是反方的"未发现"记录，非独立攻击点。

**反驳**：A1-4 的内容已被 A1-2 完全覆盖（L434 注释残留），不构成独立攻击。反方将其列为攻击点属于重复计数。

---

### 攻击点A2-1：warnings.warn的stacklevel=2是否正确（P0-轻微，非缺陷）

**判定**：不成立

**理由**：
反方自己已判定"未发现可攻击点"。审查确认 `stacklevel=2` 正确：

Python `warnings.warn` 的 `stacklevel` 语义：
- `stacklevel=1`：指向 `warnings.warn` 调用行本身（L446，在 `_weighted_ece` 内部）
- `stacklevel=2`：指向调用 `_weighted_ece` 的行（L454 或 L455，在 `plot_summary` 内部）✓

`stacklevel=2` 指向 `_weighted_ece` 的调用方（L454/L455），告知用户警告来自 `plot_summary` 中的 `_weighted_ece` 调用，这是正确的设计。

**反驳**：反方在此维度未找到可攻击点，此条是"未发现"记录，非真实攻击。

---

### 攻击点A2-2：warnings.warn是否在正常路径误触发（P0-轻微，非缺陷）

**判定**：不成立

**理由**：
反方自己已判定"未发现可攻击点"。审查确认正常路径不误触发：

`valid = np.isfinite(eces) & (weights > 0)` 为 False 的条件：
1. `eces` 包含 nan 或 inf
2. `weights` 包含 0 或负数

正常实验路径下：
- `weights = [b["n_total"] for b in bins_list]`，`n_total = len(confidence)`，恒为正整数（OOD 测试集非空）
- `eces` 在 `n_total > 0` 时有界 ∈ [0, 1]（ECE = Σ_b(n_b/N)×|acc-conf| ≤ Σ_b(n_b/N) = 1）

因此正常路径下 `valid.all() == True`，`not valid.all()` 为 False，**不会触发 warnings.warn**。仅在异常路径（OOD 测试集为空）触发，这是正确的警告行为。

**反驳**：反方在此维度未找到可攻击点，此条是"未发现"记录，非真实攻击。

---

### 攻击点A2-3：警告消息声称"ECE=nan/inf"但inf不可能产生（P0-轻微）

**判定**：成立

**理由**：
反方数学证明正确。ECE 计算公式：

```
ECE = Σ_b (n_b / N) × |acc(b) - conf(b)|
```

其中：
- `n_b ≥ 0`，`N > 0`（当 N=0 时 ece=nan，非 inf）
- `acc(b) ∈ [0, 1]`，`conf(b) ∈ [0, 1]`，`|acc(b) - conf(b)| ∈ [0, 1]`

因此：
```
ECE = Σ_b (n_b / N) × |acc(b) - conf(b)|
    ≤ Σ_b (n_b / N) × 1
    = (Σ_b n_b) / N
    = N / N = 1
```

且 ECE ≥ 0（每项非负），所以 **ECE ∈ [0, 1]**，不可能为 inf。

当 `n_total == 0` 时：`ece_val = float("nan")`，为 nan 而非 inf。

**5 维审查**：
1. 反例成立：警告消息声称 inf 可能，但数学上不可能
2. 非稻草人：反方攻击的是真实的消息文本 `ECE=nan/inf`
3. 未误解前提：消息文本确实包含 `/inf`
4. 攻击逻辑自洽：数学证明严谨
5. 严重程度未夸大：反方标注 P0-轻微合理——这是防御性过度描述，不影响功能正确性

**修补方案**：
- 文件：`scripts/run_e6_reliability_diagrams.py`
- 行号：L447
- 改动：`ECE=nan/inf` → `ECE=nan`
- 改动量：1 行

```python
# L447 改前：
f"_weighted_ece: {len(excluded)} 方向因 ECE=nan/inf 或 n_total=0 被排除: {excluded.tolist()}",

# L447 改后：
f"_weighted_ece: {len(excluded)} 方向因 ECE=nan 或 n_total=0 被排除: {excluded.tolist()}",
```

---

### 攻击点A2-4：警告触发两次且消息完全相同，无法区分before/after（P0-轻微）

**判定**：成立

**理由**：
反方主张经源代码验证为真。L454-455：

```python
ece_before = _weighted_ece(all_bins_before)
ece_after = _weighted_ece(all_bins_after)
```

`all_bins_before` 和 `all_bins_after` 来自同一组 checkpoint（L733-736 收集的 `bins_b` 和 `bins_a`），具有相同的 `n_total` 值。因此如果某方向 `n_total=0`，则 `bins_b` 和 `bins_a` 的 `n_total` 都为 0，**两次调用都会触发警告**，且消息文本完全相同（仅 `stacklevel=2` 指向的行号 L454 vs L455 不同）。

用户看到：
```
UserWarning: _weighted_ece: 1 方向因 ECE=nan/inf 或 n_total=0 被排除: [2]
  ece_before = _weighted_ece(all_bins_before)  # L454
UserWarning: _weighted_ece: 1 方向因 ECE=nan/inf 或 n_total=0 被排除: [2]
  ece_after = _weighted_ece(all_bins_after)    # L455
```

**5 维审查**：
1. 反例成立：消息文本确实完全相同，无法从消息本身区分 before/after
2. 非稻草人：反方攻击的是真实的代码行为
3. 未误解前提：`all_bins_before` 和 `all_bins_after` 的 `n_total` 确实恒相同（同一 checkpoint 的 `bins_b` 和 `bins_a` 共享 `n_total`）
4. 攻击逻辑自洽：两次警告必然同时触发或同时不触发，冗余警告是确定性的
5. 严重程度未夸大：反方标注 P0-轻微合理——功能正确，仅是日志可读性问题

**修补方案**：
- 文件：`scripts/run_e6_reliability_diagrams.py`
- 行号：L438（函数签名）+ L446-449（警告消息）+ L454-455（调用处）
- 改动：`_weighted_ece` 增加 `label` 参数，警告消息含 before/after
- 改动量：4 行

```python
# L438 改前：
def _weighted_ece(bins_list):

# L438 改后：
def _weighted_ece(bins_list, label=""):

# L446-449 改前：
warnings.warn(
    f"_weighted_ece: {len(excluded)} 方向因 ECE=nan/inf 或 n_total=0 被排除: {excluded.tolist()}",
    UserWarning, stacklevel=2
)

# L446-449 改后：
_tag = f"[{label}] " if label else ""
warnings.warn(
    f"_weighted_ece{_tag}: {len(excluded)} 方向因 ECE=nan 或 n_total=0 被排除: {excluded.tolist()}",
    UserWarning, stacklevel=2
)

# L454-455 改前：
ece_before = _weighted_ece(all_bins_before)
ece_after = _weighted_ece(all_bins_after)

# L454-455 改后：
ece_before = _weighted_ece(all_bins_before, label="before")
ece_after = _weighted_ece(all_bins_after, label="after")
```

---

### 攻击点A2-5：警告报告的是索引而非方向名（P0-轻微）

**判定**：成立

**理由**：
反方主张经源代码验证为真。L447 警告消息中 `{excluded.tolist()}` 报告的是 `bins_list` 中的索引（如 `[2]`），而非方向名（如 `"cpsc→ptbxl"`）。

`_weighted_ece` 函数签名（L438）仅接收 `bins_list`，不接收 `pair_names`，因此无法在警告中包含方向名。

用户看到警告 `_weighted_ece: 1 方向因...被排除: [2]`，需要手动回溯 `plot_summary` 的调用逻辑（L733-736 的 `summary_names.append(f"{source}→{target}")`）才能定位索引 2 对应哪个方向，对用户不友好。

**5 维审查**：
1. 反例成立：警告确实报告索引而非方向名
2. 非稻草人：反方攻击的是真实的函数签名限制
3. 未误解前提：`_weighted_ece` 确实无 `names` 参数
4. 攻击逻辑自洽：用户需额外回溯才能定位问题方向
5. 严重程度未夸大：反方标注 P0-轻微合理——这是可用性问题而非正确性问题

**修补方案**：
- 文件：`scripts/run_e6_reliability_diagrams.py`
- 行号：L438（函数签名）+ L446-449（警告消息）+ L454-455（调用处）
- 改动：`_weighted_ece` 增加 `names` 可选参数，警告报告方向名
- 改动量：3 行

```python
# L438 改前：
def _weighted_ece(bins_list):

# L438 改后：
def _weighted_ece(bins_list, names=None):

# L446-449 改前：
excluded = np.where(~valid)[0]
warnings.warn(
    f"_weighted_ece: {len(excluded)} 方向因 ECE=nan/inf 或 n_total=0 被排除: {excluded.tolist()}",
    UserWarning, stacklevel=2
)

# L446-449 改后：
excluded = np.where(~valid)[0]
excluded_desc = [names[i] if names is not None and i < len(names) else i for i in excluded.tolist()]
warnings.warn(
    f"_weighted_ece: {len(excluded)} 方向因 ECE=nan 或 n_total=0 被排除: {excluded_desc}",
    UserWarning, stacklevel=2
)

# L454-455 改前：
ece_before = _weighted_ece(all_bins_before)
ece_after = _weighted_ece(all_bins_after)

# L454-455 改后：
ece_before = _weighted_ece(all_bins_before, names=pair_names)
ece_after = _weighted_ece(all_bins_after, names=pair_names)
```

注：`pair_names` 已作为 `plot_summary` 的参数传入（L395），可直接传递。

---

### 攻击点A2-6：nan过滤后是否正确跳过nan值继续计算（P0-轻微，非缺陷）

**判定**：不成立

**理由**：
反方自己已判定"未发现可攻击点"。审查确认三种边界情况均正确：

1. **全部有效**（`valid.all() == True`）：不警告，直接 `np.average(eces, weights=weights)` ✓
2. **部分有效**（`valid.any() == True and not valid.all()`）：警告，`np.average(eces[valid], weights=weights[valid])` 跳过无效方向 ✓
3. **全部无效**（`not valid.any()`）：警告，返回 `nan` ✓

**空 `bins_list` 边界**：
- `weights = np.array([])`, `eces = np.array([])`, `valid = np.array([])`（空布尔数组）
- `valid.all()` 对空数组返回 `True`（vacuous truth）→ 不警告
- `valid.any()` 对空数组返回 `False` → `not valid.any()` 为 True → 返回 `nan`
- 不触发警告但返回 nan：合理——空列表无方向可排除，无需警告 ✓

**反驳**：nan 过滤逻辑在所有边界情况下均正确，反方在此维度未找到可攻击点。

---

### 攻击点A2-7：warnings.warn在严格警告模式下会抛异常导致绘图崩溃（P0-轻微）

**判定**：不成立

**理由**：
反方主张"如果用户配置 `warnings.filterwarnings("error")`，则 `warnings.warn` 会抛出 `UserWarning` 异常，导致 `plot_summary` 中断"。

审查维度2（稻草人论证）和维度3（误解前提）分析：

1. **稻草人论证**：反方攻击的是一个**用户主动配置的非默认场景**。`warnings.filterwarnings("error")` 是用户明确意图将所有警告转为异常——这是用户的**明确选择**，而非代码的缺陷。如果用户这样配置，**任何** `warnings.warn` 调用都会抛异常，这是 Python warnings 模块的标准行为。

2. **误解前提**：反方忽略了 `warnings.warn` 的设计前提——警告是**非中断性**的提示，默认不中断程序。如果用户主动配置 `filterwarnings("error")`，用户已经明确表达了"我希望警告中断程序"的意图。此时程序中断是**符合用户预期**的行为，而非崩溃。

3. **攻击逻辑不自洽**：若按反方建议将 `warnings.warn` 改为 `print`，则：
   - 失去警告的可见性（`print` 输出可能被重定向或忽略）
   - 无法被 `warnings.filterwarnings` 捕获和管理
   - 违反 Python 警告系统的设计惯例
   - 反方自己也将此条标注为"可选"修补，承认非必修

4. **严重程度夸大**：反方标注 P0-轻微，但实际应标注为"非缺陷"——这是用户配置选择，非代码问题。论文实验脚本在默认配置下正确运行，无需为用户主动配置的严格模式负责。

**反驳**：
- `warnings.warn` 是 Python 标准的警告机制，其设计意图就是"默认不中断，可配置为中断"
- 用户配置 `filterwarnings("error")` 是明确意图让警告中断程序，此时中断是符合预期的行为
- 若为此修改代码（改用 `print` 或 `try/except`），反而破坏警告的可见性和可配置性
- 反方自己也将此条列为"可选"修补，承认非必修
- **结论**：此攻击不成立，是稻草人论证 + 误解前提 + 严重程度夸大

---

## 总结

### 需R4修复的必修项清单

| 序号 | 攻击点 | 优先级 | 文件 | 行号 | 改动内容 | 改动量 |
|------|--------|--------|------|------|---------|--------|
| 1 | A1-2 | P0-中等 | run_e6_reliability_diagrams.py | L434 | `size-weighted mean of per-direction ECE` → `sample-count weighted mean of per-direction ECE` | 1行 |

### 建议项清单（可选，P0-轻微）

| 序号 | 攻击点 | 优先级 | 文件 | 行号 | 改动内容 | 改动量 |
|------|--------|--------|------|------|---------|--------|
| 2 | A2-3 | P0-轻微 | run_e6_reliability_diagrams.py | L447 | `ECE=nan/inf` → `ECE=nan`（inf不可能产生） | 1行 |
| 3 | A2-4 | P0-轻微 | run_e6_reliability_diagrams.py | L438/L446-449/L454-455 | `_weighted_ece` 增加 `label` 参数，警告含 before/after | 4行 |
| 4 | A2-5 | P0-轻微 | run_e6_reliability_diagrams.py | L438/L446-449/L454-455 | `_weighted_ece` 增加 `names` 参数，警告报告方向名 | 3行 |

注：A2-4 和 A2-5 可合并为一次修改——同时增加 `label` 和 `names` 参数，总改动量约 5 行（非 4+3=7 行，因函数签名和调用处修改可共享）。

### 可关闭的攻击点

| 攻击点 | 关闭理由 |
|--------|---------|
| A1-1 | 字符串确实不同但语境差异合理，核心术语一致，非缺陷 |
| A1-3 | 单方向图vs汇总图标签差异是正确的语义区分，反方自己承认 |
| A1-4 | 内容被 A1-2 完全覆盖，非独立攻击点，重复计数 |
| A2-1 | stacklevel=2 正确指向调用方，反方自己承认 |
| A2-2 | 正常路径不误触发警告，反方自己承认 |
| A2-6 | nan 过滤在三种边界情况均正确，反方自己承认 |
| A2-7 | 稻草人论证 + 误解前提 + 严重程度夸大——用户主动配置 `filterwarnings("error")` 是明确意图，非代码缺陷 |

### 整体评估

**R3 修复评价**：**部分通过，接近收敛**

- **修复点1（3处字符串统一）**：用户可见的 3 处字符串（L460/L465/L484）已统一核心术语 `sample-count weighted mean`，**核心目标达成**。遗漏 L434 注释术语同步（A1-2，P0-中等），需 R4 修复 1 行。
- **修复点2（nan过滤warnings.warn）**：核心逻辑正确完成——warnings.warn 已插入（L446-449），触发条件正确，正常路径不误触发，nan 过滤边界正确。警告消息的精确性（A2-3）和可用性（A2-4, A2-5）有改进空间，但均为 P0-轻微，可选修复。

**R4 必修量**：1 行改动（L434 注释术语同步）。

**收敛趋势**：
- R2 轮：A1（标题vs图例术语不一致）+ A3（nan过滤静默无警告）→ 2 个 P0 攻击点
- R3 轮：A1 核心已消除（用户可见字符串统一），A3 已消除（warnings.warn 已加）；新遗留 A1-2（注释术语未同步，P0-中等）
- R4 轮预期：修复 A1-2 后，P0-中等攻击点清零，仅剩 3 个 P0-轻微建议项（可选）

**反方攻击质量评价**：
- 反方覆盖了 7 个攻击维度，找到 6 个成立攻击点（1 中等 + 5 轻微）和 5 个"未发现可攻击点"的维度记录
- 反方攻击整体质量较高——A1-2（L434 注释遗漏）是真实的修复不完整，A2-3（inf 不可能产生）有严谨数学证明
- 但反方将 A1-3、A1-4、A2-1、A2-2、A2-6 等"未发现可攻击点"的维度记录列为攻击点，存在**重复计数**问题——这些不是独立攻击，而是反方为覆盖全维度而列出的"未发现"记录
- A2-7（严格警告模式崩溃）是稻草人论证——攻击用户主动配置的非默认场景，非代码缺陷

**最终判定**：P0-8 R3 修复**部分通过**。R4 必修 1 项（A1-2，L434 注释术语同步，1 行改动），可选 3 项（A2-3, A2-4, A2-5，共约 5 行改动）。修复后 P0-中等攻击点清零，方案接近稳定。
