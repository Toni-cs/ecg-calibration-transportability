# R6-Phase2 P0-6+7 反方攻击报告

> **攻击代理**：R6-Phase2 P0-6+7 反方挑刺代理（GLM-5.2）
> **攻击日期**：2026-09-10
> **任务ID**：137
> **攻击目标**：R6-Phase1 正方修复 `scripts/run_e5_inception_lite.py` L593（`n_ood=0` → `n_ood=int(len(ood_probs))`）
> **依据**：`docs/p0r6_fix_p0_6_7.md` 正方修复报告 + `docs/p0r5_final_verdict.md` R5 终审裁决
> **判定原则**：以代码事实为唯一判据，7 维度全覆盖攻击，不跳过任何维度

---

## 0. 审查对象与上下文确认

### 0.1 修复内容

| 文件 | 行号 | 修改前 | 修改后 |
|------|------|--------|--------|
| `scripts/run_e5_inception_lite.py` | L593（修复前 L592） | `n_ood=0,` | `n_ood=int(len(ood_probs)),` |

### 0.2 修复所在路径

```python
# L583-598（R6 修复后）
if len(cal_probs) == 0:                              # cal 集截断后为空
    print(f"[WARN] ... cal 集截断后为空，跳过 TS 校准")
    return _make_transfer_result(
        source=source, target=target, seed=seed,
        arch=source_info.get("arch", ARCH_NAME),
        num_classes=num_classes,
        n_ood=int(len(ood_probs)),                   # ← R6 修复点
        n_dropped_cal=int(n_dropped_cal), n_dropped_ood=int(n_dropped_ood),
        truncated=True,
        subspace_filtered=bool(num_classes < max(...)),
        error="cal set empty after truncation", skipped=True,
    )
```

### 0.3 ood_probs 变量流追踪（L532→L593）

| 行号 | 代码 | 操作 |
|------|------|------|
| L532 | `ood_probs = tgt_eval["probs"]` | 首次定义（numpy 数组） |
| L549 | `ood_probs = ood_probs[ood_keep][:, :num_classes]` | 标签截断 + 概率列截断 |
| L567 | `ood_row_sums = ood_probs.sum(axis=1, keepdims=True)` | 计算行和 |
| L568 | `ood_zero_rows = (ood_row_sums.flatten() == 0)` | 检测全零行 |
| L574 | `ood_probs = ood_probs[~ood_zero_rows]` | 丢弃全零行 |
| L579 | `ood_probs = ood_probs / ood_row_sums` | 归一化 |
| L583 | `if len(cal_probs) == 0:` | early-return 检查点 |
| L593 | `n_ood=int(len(ood_probs))` | **R6 修复使用点** |

### 0.4 正常路径 n_ood 计算（L654）

```python
# L650-654（正常路径）
result = _make_transfer_result(
    source=source, target=target, seed=seed,
    arch=source_info.get("arch", ARCH_NAME),
    num_classes=num_classes,
    n_ood=int(len(ood_probs)),                       # ← 正常路径（与 R6 修复完全一致）
    ...
)
```

### 0.5 其他 early-return 路径 n_ood 处理

| 路径 | 行号 | n_ood 传值 | 是否显式传参 | 正确性 |
|------|------|-----------|-------------|--------|
| FileNotFound | L521-527 | 默认 0 | 否（ood_probs 未定义） | ✅ 正确（目标数据集不存在，无 ood 样本） |
| cal empty | L589-598 | `int(len(ood_probs))` | 是（R6 修复） | ✅ 修复后正确 |
| ood empty | L602-610 | 默认 0 | 否（依赖函数签名默认值） | ✅ 正确（`len(ood_probs)==0`，显式传 `int(len(ood_probs))` 也是 0） |
| OOM 异常 | L887-891 | 默认 0 | 否（ood_probs 可能未定义） | ✅ 正确（异常路径，无法确定 ood 状态） |

---

## 1. 攻击点汇总

| 编号 | 维度 | 严重度 | 摘要 |
|------|------|--------|------|
| Attack-1 | 反例构造 | 轻微 | skipped=True + n_ood>0 语义张力：下游 `df.n_ood.sum()` 会计入未评估的 ood 样本 |
| Attack-2 | 逻辑断链 | — | 未发现可攻击点（推理链条完整） |
| Attack-3 | 隐含假设 | 轻微 | n_ood 语义未显式定义："存在样本数" vs "已评估样本数"，修复选择前者但未文档化 |
| Attack-4 | 边界失效 | — | 未发现可攻击点（空集/单元素/极大值/双空均正确） |
| Attack-5 | 自相矛盾 | 轻微 | cal-empty 路径显式传 n_ood，ood-empty 路径依赖默认值——风格不一致；skipped=True 行含非零数值字段 |
| Attack-6 | 量级错误 | — | 未发现可攻击点（int(len()) 冗余但安全，无溢出） |
| Attack-7 | 语义偏移 | 轻微 | R5 终审声称"值不同可区分"，但 cal+ood 双空时 cal-empty 路径先返回 n_ood=0，与 ood-empty 路径 n_ood=0 不可区分（仅靠 error 字段区分） |

**统计**：7 个维度中 3 个未发现可攻击点，4 个发现攻击点（0 致命 / 0 严重 / 0 中等 / 1 轻微→轻微 / 3 轻微）

---

## 2. 逐条攻击

### Attack-1：反例构造

- **维度**：反例构造
- **严重度**：轾微
- **攻击**：构造一个 cal 空 + ood 非空的场景，展示修复后 `skipped=True` 行的 `n_ood > 0` 对下游聚合分析的误导。

  **具体反例**：
  - 数据集配置：source=PTBXL（5 类），target=CPSC2020（4 类），num_classes=4
  - cal 集：截断后所有样本标签 ≥4 或截断后全零 → `len(cal_probs) == 0`
  - ood 集：截断后有 200 个有效样本 → `len(ood_probs) == 200`
  - 修复后输出行：`{skipped=True, n_ood=200, ood_acc_raw=nan, error="cal set empty after truncation"}`

  **下游误导场景**：若分析脚本执行 `total_ood_evaluated = df.n_ood.sum()`（不过滤 skipped 行），则该 200 个样本被计入"已评估 ood 样本总数"，但实际上这些样本从未经过 TS 校准和 metrics 计算（ood_acc_raw=nan 证实无评估结果）。修复前 n_ood=0 不会导致此问题，修复后引入了新的误导风险。

- **代码证据**：
  ```python
  # L593: n_ood=int(len(ood_probs))  → 200
  # L597: skipped=True               → 实验被跳过
  # ood_acc_raw: 默认 nan（L163）     → 无评估结果
  # 矛盾：n_ood=200 说"有 200 个 ood 样本"，但 ood_acc_raw=nan 说"未评估"
  ```
- **反反方预判**：`skipped=True` 已明确标记该行无效，负责任的下游分析应先过滤 `df[df.skipped == False]`。n_ood 是元数据（样本计数）而非评估结果，反映"存在的 ood 样本数"是合理语义。误导风险仅存在于不过滤 skipped 行的粗放分析脚本，属下游使用问题而非上游数据问题。
- **修复建议**：无需修复。若需彻底消除歧义，可在 docstring 或 CSV 头注释中声明"n_ood 反映截断后有效 ood 样本数，skipped=True 行的 n_ood 仍反映样本数而非已评估数"。

---

### Attack-2：逻辑断链

- **维度**：逻辑断链
- **严重度**：—（未发现可攻击点）
- **攻击**：逐环节验证修复推理链条。

  **推理链条**：
  1. cal 和 ood 独立截断 → cal 空不代表 ood 空
  2. n_ood 应反映实际 ood 样本数
  3. `int(len(ood_probs))` 在 L593 处给出实际 ood 样本数
  4. 因此 `n_ood=int(len(ood_probs))` 正确

  **逐环节验证**：
  - **环节 1**（cal/ood 独立截断）：✅ 坚实。L546-547 对 cal_labels/cal_probs 截断，L548-549 对 ood_labels/ood_probs 截断，两处使用独立的 `cal_keep` 和 `ood_keep` 掩码，无交叉依赖。cal 截断不影响 ood，反之亦然。
  - **环节 2**（n_ood 应反映实际样本数）：✅ 坚实。正常路径 L654 `n_ood=int(len(ood_probs))` 确立了 n_ood 的语义基准——截断+全零行过滤后的有效 ood 样本数。R6 修复使 cal-empty 路径与该基准一致。
  - **环节 3**（int(len(ood_probs)) 给出正确值）：✅ 坚实。ood_probs 在 L532 定义为 numpy 数组，经 L549 截断、L574 全零行过滤、L579 归一化后仍为 numpy 数组。`len()` 返回第一维大小（样本数），`int()` 转换为 Python int（冗余但安全）。L583 到 L593 之间无对 ood_probs 的重赋值。
  - **环节 4**（结论正确）：✅ 由 1-3 逻辑推出，无跳跃。

- **结论**：推理链条完整，4 个环节全部坚实，无断链。

---

### Attack-3：隐含假设

- **维度**：隐含假设
- **严重度**：轻微
- **攻击**：修复依赖以下未显式声明的假设：

  **假设 A**：`n_ood` 的语义是"截断+全零行过滤后的有效 ood 样本数"，而非"原始 ood 样本数"或"已评估 ood 样本数"。
  - **验证**：正常路径 L654 `n_ood=int(len(ood_probs))` 确实使用过滤后的 count，故假设 A 与正常路径一致。但该语义未在任何 docstring、注释或文档中显式声明。`_make_transfer_result` 的 docstring（L180-190）仅说明"统一 schema"，未定义 n_ood 的语义。
  - **假设不成立的情况**：若下游消费者假设 n_ood 是"已评估样本数"（因为正常路径中 n_ood 与 ood_acc_raw 同时有效），则 cal-empty 路径的 n_ood>0 会违反其假设。

  **假设 B**：cal-empty 路径中 ood_probs 已经过完整的截断+过滤管线。
  - **验证**：✅ 成立。L549（截断）→ L574（全零行过滤）→ L579（归一化）均在 L583（cal-empty 检查）之前执行。代码顺序保证 ood_probs 在 L593 使用时已是过滤后的状态。
  - **假设不成立的情况**：若未来重构将 cal-empty 检查提前到 L549 之前（截断前），则 `len(ood_probs)` 会反映原始样本数而非过滤后样本数，与正常路径不一致。当前代码无此风险，但缺乏防御性注释标注该顺序依赖。

  **假设 C**：`int(len(ood_probs))` 与正常路径的 `int(len(ood_probs))`（L654）引用的是同一个变量、同一种处理状态。
  - **验证**：✅ 成立。两处引用的 ood_probs 均经过 L532→L549→L574→L579 的完整处理链，且在 L583-L654 之间无重赋值（cal-empty 路径在 L598 return，不会到达 L654）。

- **代码证据**：
  ```python
  # _make_transfer_result docstring（L180-190）未定义 n_ood 语义：
  """构造字段完整的 transfer result dict（R4 修复 Attack-1/4/6/7）。
  统一所有 transfer result dict 的 schema。early-return / skipped / error
  路径下不可用的字段填入合理默认值（0 / False / nan / None）..."""
  # ↑ 仅说明 schema 统一，未声明 n_ood 在 skipped 行的语义
  ```
- **修复建议**：在 `_make_transfer_result` docstring 或 `TRANSFER_RESULT_FIELDS` 注释中显式声明 n_ood 语义："截断+全零行过滤后的有效 ood 样本数；skipped=True 行仍反映存在的样本数，不代表已评估"。改动量：2 行注释。

---

### Attack-4：边界失效

- **维度**：边界失效
- **严重度**：—（未发现可攻击点）
- **攻击**：逐一测试边界条件。

  | 边界场景 | ood_probs 状态 | int(len(ood_probs)) | 修复前 n_ood | 修复后 n_ood | 正确性 |
  |---------|---------------|---------------------|-------------|-------------|--------|
  | cal 空 + ood 空 | `array([])` shape=(0,4) | 0 | 0 | 0 | ✅ 两者一致 |
  | cal 空 + ood 单元素 | `array([[0.3,0.7,0,0]])` | 1 | 0（❌错误） | 1（✅正确） | ✅ 修复 |
  | cal 空 + ood 大量 | shape=(10000,4) | 10000 | 0（❌错误） | 10000（✅正确） | ✅ 修复 |
  | cal 空 + ood 全被截断 | `array([])` shape=(0,4) | 0 | 0 | 0 | ✅ 两者一致 |
  | cal 空 + ood 全零行被过滤 | `array([])` shape=(0,4) | 0 | 0 | 0 | ✅ 两者一致 |
  | cal 空 + ood 部分被过滤 | shape=(150,4) | 150 | 0（❌错误） | 150（✅正确） | ✅ 修复 |

  **极端值测试**：
  - `len(ood_probs)` 返回 Python int，无溢出风险（Python int 任意精度）
  - `int(len(ood_probs))` 冗余转换，`int(int)` 返回相同 int，无副作用
  - ood_probs 为空数组时 `len()` 返回 0，`int(0)` 返回 0，无异常

- **结论**：所有边界条件下修复均正确，无失效。修复仅在"cal 空 + ood 非空"场景改变行为（从错误值 0 改为正确值 >0），其余场景行为不变。

---

### Attack-5：自相矛盾

- **维度**：自相矛盾
- **严重度**：轾微
- **攻击**：检查修复后代码内部一致性。

  **矛盾点 1**：cal-empty 路径与 ood-empty 路径的 n_ood 传参风格不一致。
  - cal-empty 路径（L593）：显式传 `n_ood=int(len(ood_probs))`
  - ood-empty 路径（L602-610）：不传 n_ood，依赖函数签名默认值 `n_ood: int = 0`（L162）
  - **是否真矛盾**：否。ood-empty 路径在 L599 已确认 `len(ood_probs) == 0`，故 `int(len(ood_probs))` 也为 0，与默认值一致。值正确但风格不一致——若未来有人修改 ood_probs 的处理逻辑导致 L599 时 len(ood_probs) 不再为 0，ood-empty 路径的隐式默认值 0 将变为错误，而 cal-empty 路径的显式传参则自适应。这是**防御性差异**，非当前 bug。

  **矛盾点 2**：`skipped=True` 行包含非零数值字段（n_ood > 0, n_dropped_ood > 0, truncated=True, subspace_filtered=bool(...)）。
  - **是否真矛盾**：否。`skipped=True` 标记的是"TS 校准被跳过"，而非"整行数据无效"。n_ood/n_dropped_ood/truncated/subspace_filtered 是**元数据字段**（描述数据集状态），非**评估结果字段**（ood_acc_raw/ood_ece_raw 等为 nan）。元数据在 skipped 行中有效是合理的——它们描述"如果运行了会怎样"，而非"运行了得到什么"。
  - **潜在混淆**：skipped=True 行的 n_ood > 0 与 ood_acc_raw=nan 并存，可能让下游消费者困惑"有样本但无结果"。但 error="cal set empty after truncation" 已解释原因。

  **矛盾点 3**：修复注释（L587-588）声称"n_ood 应反映实际 ood 样本数"，但 `_make_transfer_result` docstring（L180-190）将 early-return 路径字段描述为"不可用的字段填入合理默认值"。
  - **是否真矛盾**：轻微。n_ood 在 cal-empty 路径并非"不可用"（ood_probs 已定义且有效），但 docstring 的泛化描述暗示 early-return 字段均为默认占位。修复后 n_ood 不再是默认占位而是实际值，与 docstring 的描述框架有轻微摩擦。

- **代码证据**：
  ```python
  # L593: n_ood=int(len(ood_probs)),        # cal-empty 显式传参
  # L602-610: _make_transfer_result(...)     # ood-empty 不传 n_ood，依赖默认 0
  # L162: n_ood: int = 0,                    # 函数签名默认值
  ```
- **修复建议**：为防御性一致性，建议 ood-empty 路径也显式传 `n_ood=int(len(ood_probs))`（值为 0，与默认一致但表达意图更清晰）。改动量：1 行。非必修，属风格改进。

---

### Attack-6：量级错误

- **维度**：量级错误
- **严重度**：—（未发现可攻击点）
- **攻击**：检查数值量级、复杂度、类型安全。

  **类型分析**：
  - `ood_probs` 是 numpy.ndarray（来自 `tgt_eval["probs"]`，evaluate 函数返回）
  - `len(ood_probs)` 返回 Python int（numpy 数组第一维大小）
  - `int(len(ood_probs))` 是 `int(int)` → 返回相同 Python int，冗余但无副作用
  - 与正常路径 L654 `n_ood=int(len(ood_probs))` 写法完全一致

  **量级分析**：
  - `len(ood_probs)` ∈ [0, 原始 ood 样本数]，上界由数据集大小决定（ECG 数据集通常 ≤ 10000）
  - 无溢出风险（Python int 任意精度）
  - 无下溢风险（最小值 0）
  - 无 NaN/Inf 风险（len() 对数组返回有限整数）

  **复杂度分析**：
  - `len()` 是 O(1) 操作（numpy 数组 shape 属性读取）
  - `int()` 是 O(1) 操作
  - 修复不引入任何计算开销

- **结论**：无量级错误，无类型安全问题，无性能影响。

---

### Attack-7：语义偏移

- **维度**：语义偏移
- **严重度**：轾微
- **攻击**：检查修复后 n_ood 语义是否与设计意图偏移，以及 R5 终审的"值不同可区分"声明是否完全成立。

  **语义偏移分析**：

  修复前（R5）：cal-empty 路径 n_ood=0，语义="无 ood 评估结果"
  修复后（R6）：cal-empty 路径 n_ood=int(len(ood_probs))，语义="截断后有效 ood 样本数"
  正常路径：n_ood=int(len(ood_probs))，语义="截断后有效 ood 样本数"

  修复将 cal-empty 路径的 n_ood 语义从"评估结果计数"偏移到"样本存在计数"，与正常路径对齐。这是 R5 终审要求的修复方向（"正常路径 n_ood=int(len(ood_probs))，cal empty 路径将 n_ood 语义偏移"），修复方向正确。

  **R5 终审"值不同可区分"声明的验证**：

  R5 终审 L189 原文："修复 Attack-4 后自动解决（cal empty 路径 n_ood=int(len(ood_probs))，ood empty 路径 n_ood=0，值不同可区分）"

  修复后各路径 n_ood 值：

  | 场景 | 进入路径 | n_ood | error |
  |------|---------|-------|-------|
  | cal 空 + ood 非空 | L583 cal-empty | >0 | "cal set empty after truncation" |
  | cal 空 + ood 空 | L583 cal-empty（先检查） | 0 | "cal set empty after truncation" |
  | cal 非空 + ood 空 | L599 ood-empty | 0 | "ood set empty after truncation" |
  | cal 非空 + ood 非空 | L650 正常路径 | >0 | None |

  **"值不同可区分"成立情况**：
  - cal空+ood非空（n_ood>0）vs ood空（n_ood=0）：✅ 可区分
  - cal空+ood空（n_ood=0）vs ood空（n_ood=0）：❌ **n_ood 不可区分**（均为 0）

  当 cal 和 ood 同时为空时，L583 的 cal-empty 检查先于 L599 的 ood-empty 检查，返回 n_ood=0 + error="cal set empty after truncation"。此 n_ood 值与 ood-empty 路径的 n_ood=0 相同，**仅靠 n_ood 无法区分两种场景**，需依赖 error 字段。

  R5 终审的"值不同可区分"声明在 cal+ood 双空场景下**不成立**。但实际影响极小：
  1. error 字段仍可区分两种场景
  2. cal+ood 双空是极端边界（两个独立截断后均为空），实际触发概率极低
  3. 双空时报告"cal empty"而非"ood empty"是合理的优先级（cal 先检查）

- **代码证据**：
  ```python
  # L583: if len(cal_probs) == 0:     # 先检查 cal 空
  #     return ... n_ood=int(len(ood_probs))  # ood 也空时 → 0
  # L599: if len(ood_probs) == 0:     # 后检查 ood 空（cal 非空时才到达）
  #     return ... (n_ood 默认 0)
  # 双空时 L583 先返回，n_ood=0，与 L599 的 n_ood=0 不可区分
  ```
- **修复建议**：无需修复。R5 终审的"值不同可区分"声明在双空场景不成立，但 error 字段提供区分能力，且双空场景实际影响可忽略。若需严格区分，可在 cal-empty 路径添加 `ood_also_empty = (len(ood_probs) == 0)` 并在 error 中体现，但属过度工程。

---

## 3. 攻击维度汇总

| 维度 | 攻击结果 | 严重度 | 说明 |
|------|---------|--------|------|
| 1. 反例构造 | 找到攻击点 | 轾微 | skipped=True + n_ood>0 对下游 sum() 的误导风险 |
| 2. 逻辑断链 | 未发现可攻击点 | — | 4 环节推理链条全部坚实 |
| 3. 隐含假设 | 找到攻击点 | 轻微 | n_ood 语义（存在数 vs 评估数）未显式声明 |
| 4. 边界失效 | 未发现可攻击点 | — | 6 种边界场景全部正确 |
| 5. 自相矛盾 | 找到攻击点 | 轾微 | cal-empty/ood-empty 传参风格不一致 + skipped 行含非零元数据 |
| 6. 量级错误 | 未发现可攻击点 | — | 类型安全、无溢出、O(1) 复杂度 |
| 7. 语义偏移 | 找到攻击点 | 轾微 | R5"值不同可区分"在双空场景不成立（error 字段可补救） |

---

## 4. 与 R5 终审裁决的对照

### 4.1 R5 终审要求的修复方向

R5 终审（`docs/p0r5_final_verdict.md` L188-189）：
> **Attack-4**（中等）：cal 和 ood 独立截断，cal 空不代表 ood 空。n_ood=0 在 ood_probs 非空时事实错误。正常路径 n_ood=int(len(ood_probs))，cal empty 路径将 n_ood 语义偏移。
> **Attack-5**（中等，Attack-4 衍生）：修复 Attack-4 后自动解决（cal empty 路径 n_ood=int(len(ood_probs))，ood empty 路径 n_ood=0，值不同可区分）。

### 4.2 R6 修复符合性

| R5 要求 | R6 实现 | 符合性 |
|---------|---------|--------|
| cal empty 路径改为 n_ood=int(len(ood_probs)) | L593 `n_ood=int(len(ood_probs))` | ✅ 完全符合 |
| 与正常路径 n_ood 语义一致 | 正常路径 L654 同为 `int(len(ood_probs))` | ✅ 完全一致 |
| 值不同可区分（cal empty vs ood empty） | cal空+ood非空时 n_ood>0 vs ood空时 n_ood=0 | ⚠️ 部分成立（双空场景不可区分） |

### 4.3 R5 终审残余疑点验证

R5 终审 L483 残余疑点：
> P0-6+7 Attack-4 的修复（n_ood=int(len(ood_probs))）需确认 ood_probs 在 cal empty 路径时确实已截断+零行过滤（L548-579），且 len(ood_probs) 反映实际 ood 样本数

**验证结果**：
- ✅ ood_probs 在 L583 之前已过 L549 截断 + L574 全零行过滤 + L579 归一化
- ✅ len(ood_probs) 反映截断+过滤后的有效 ood 样本数（与正常路径一致）
- ✅ ood_probs 在 L532 定义，远早于 L583，作用域可用性确认

---

## 5. 收敛判定

### 5.1 R6 修复后 P0-6+7 攻击点统计

| 致命 | 严重 | 中等 | 轻微 | 收敛状态 |
|------|------|------|------|---------|
| 0 | 0 | 0 | 4（Attack-1/3/5/7，均轾微或轻微） | **已收敛** |

### 5.2 收敛分析

R6 修复成功清零了 R5 终审裁定的 1 个中等攻击点（Attack-4+5）。本次反方 7 维度攻击未发现任何致命/严重/中等攻击点，仅发现 4 个轾微/轻微攻击点：

1. **Attack-1**（轾微）：skipped=True + n_ood>0 的下游误导风险——属下游使用问题，skipped=True 已标记
2. **Attack-3**（轻微）：n_ood 语义未显式文档化——属文档改进，非代码缺陷
3. **Attack-5**（轾微）：cal-empty/ood-empty 传参风格不一致——值正确，风格差异
4. **Attack-7**（轾微）：R5"值不同可区分"在双空场景不成立——error 字段可补救，实际影响可忽略

所有攻击点均为轾微/轻微级别，不影响功能正确性，属可选改进项。

### 5.3 与 R5 终审预期的对照

R5 终审预期（L188）："R6 修复后可完全收敛"
R6 反方验证结果：✅ **符合预期**。P0-6+7 的致命/严重/中等攻击点全部清零，仅剩 4 个轾微/轻微可选建议项。

---

## 6. 攻击声明

本次反方攻击对 R6-Phase1 P0-6+7 正方修复（`scripts/run_e5_inception_lite.py` L593 `n_ood=0` → `n_ood=int(len(ood_probs))`）执行了 7 维度全覆盖攻击：

- **3 个维度未发现可攻击点**：逻辑断链（推理链条完整）、边界失效（6 种边界全正确）、量级错误（类型安全无溢出）
- **4 个维度发现轾微/轻微攻击点**：反例构造（下游 sum 误导风险）、隐含假设（n_ood 语义未文档化）、自相矛盾（传参风格不一致）、语义偏移（R5"值不同可区分"在双空场景不成立）
- **0 个致命/严重/中等攻击点**：R6 修复成功消除了 R5 终审裁定的中等攻击点（Attack-4+5），未引入新的高严重度问题

**最终判定**：R6 修复**通过**反方 7 维度攻击审查。P0-6+7 的致命/严重/中等攻击点全部清零，仅剩 4 个轾微/轻微可选改进项，符合 R5 终审预期的"R6 修复后可完全收敛"判定。

**可选改进项清单**（非必修，均轾微/轻微）：

| 编号 | 改进内容 | 文件 | 改动量 |
|------|---------|------|--------|
| Attack-3 | 在 _make_transfer_result docstring 声明 n_ood 语义 | run_e5_inception_lite.py L180 | 2 行注释 |
| Attack-5 | ood-empty 路径显式传 n_ood=int(len(ood_probs)) | run_e5_inception_lite.py L606 | 1 行 |
| Attack-1 | CSV 头注释声明 skipped 行 n_ood 语义 | run_e5_inception_lite.py L694 | 1 行注释 |
| Attack-7 | 无需修复（error 字段已提供区分能力） | — | 0 行 |
