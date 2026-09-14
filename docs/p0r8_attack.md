# P0 R8-Phase2 反方攻击报告

> **审查对象**：R8-Phase1 正方完成的 4 项必修修复
> **审查方法**：7 维度全覆盖攻击（正确性/完整性/DRY/可维护性/性能/测试覆盖/文档一致性）
> **审查结论**：**R8 修复通过反方攻击，无致命/严重问题**。发现 2 个轻微 + 5 个轾微问题，均不阻塞收敛，可挂起至后续轮次或永久挂起。

## 审查事实基础

| 修复项 | 文件 | 验证方法 | 结果 |
|--------|------|----------|------|
| R8-4 | `src/utils/calibration.py` | 逐行读取 L21-43 + 6 处调用点 grep | ✅ 6 处全部调用 `_validate_n_bins` |
| R8-1 | `src/data/l2_shifts.py` + 2 scripts | grep `SEED_STRATEGY_VERSION` + `md5_v1` 全项目 | ✅ 单点定义，无硬编码残留 |
| R8-2 | `scripts/run_e1a_l2_shift_full.py` | 读取 L494-527 + L625-636 确认 4 处修改 | ✅ 4 处修改完整 |
| R8-5 | `tests/test_model.py` | grep `TypeError` + pytest 运行 | ✅ 24 passed，TypeError 死分支已移除 |

---

## R8-4 审查：calibration.py `_validate_n_bins` 统一调用

### 维度 1：正确性 ✅

**验证内容**：6 处函数是否都调用了 `_validate_n_bins(n_bins)`，调用方式是否一致。

**证据**（`src/utils/calibration.py`）：
- L240 `ece`: `n_bins = _validate_n_bins(n_bins)` ✅
- L575 `bootstrap_ece`: `n_bins = _validate_n_bins(n_bins)` ✅
- L630 `brier_parts`: `n_bins = _validate_n_bins(n_bins)` ✅
- L682 `mce`: `n_bins = _validate_n_bins(n_bins)` ✅
- L724 `plot_reliability_diagram`: `n_bins = _validate_n_bins(n_bins)` ✅
- L791 `compute_all_metrics`: `n_bins = _validate_n_bins(n_bins)` ✅

**`_validate_n_bins` 实现验证**（L41-43）：
```python
if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1 or n_bins > upper_bound:
    raise ValueError(...)
return int(n_bins)
```
- bool 排除：`isinstance(n_bins, bool)` 在最前，短路求值防止 `True < 1` 误判 ✅
- 类型检查：`not isinstance(n_bins, (int, np.integer))` 在 `< 1` 前，短路求值防止 `None < 1` TypeError ✅
- 范围检查：`n_bins < 1 or n_bins > upper_bound` ✅
- 返回 `int(n_bins)`：np.int64 → Python int，下游 `np.linspace` 行为不变 ✅

**调用方式一致性**：6 处均为 `n_bins = _validate_n_bins(n_bins)`（赋值回写），无其他形式 ✅

**结论**：正确性无问题。

### 维度 2：完整性 ⚠️

#### Attack-R8-4-1 [轻微] `_validate_n_bins` docstring "scripts/ 中 4 个 n_bins 函数" 表述不精确，遗漏 run_e3 的 3 个间接调用函数

- **位置**：`src/utils/calibration.py` L24
- **问题描述**：docstring L24 声称"供 calibration.py 内 6 处守卫与 scripts/ 中 4 个 n_bins 函数统一调用"。经 grep 确认，scripts 中**直接调用** `_validate_n_bins` 的确实是 4 个函数（`run_e2.fit_binned_temperature` L166 / `run_e4.quintile_edges` L190 / `run_e6.compute_reliability_bins` L153 / `run_e6.bootstrap_bin_accuracy_ci` L220）。但 `run_e3_brier_dcr_ncv.py` 中有 **3 个函数也接受 `n_bins` 参数却未调用 `_validate_n_bins`**：
  - L170 `brier_parts_toplabel(n_bins)` → 间接调用 `brier_parts(n_bins=n_bins)` L181
  - L185 `brier_parts_ovr(n_bins)` → 间接调用 `brier_parts(n_bins=n_bins)` L199
  - L207 `ece_toplabel(n_bins)` → 间接调用 `ece(n_bins=n_bins)` L211
- **run_e3 import 验证**：L125-127 `from src.utils.calibration import (fit_temperature, apply_temperature, ece, brier_parts, brier_raw,)` —— **未导入 `_validate_n_bins`**。
- **影响分析**：run_e3 的 3 个函数**功能上安全**（n_bins 会被下游 `brier_parts`/`ece` 的 `_validate_n_bins` 守卫拦截），但 docstring 的"4 个 n_bins 函数"暗示 scripts 中只有 4 个 n_bins 函数，实际上有 7 个（4 个直接 + 3 个间接）。表述不够精确，可能误导后续维护者认为 run_e3 无 n_bins 参数。
- **反例**：维护者阅读 docstring 后认为 scripts 中只有 4 个 n_bins 函数，在 run_e3 新增函数时未添加守卫，且该函数不间接调用 `brier_parts`/`ece`，导致 bool 穿透。
- **严重度**：轻微（功能安全，仅 docstring 表述不精确）
- **建议修复**：docstring L24 改为"供 calibration.py 内 6 处守卫与 scripts/ 中 4 个函数直接调用（run_e3 的 3 个函数经下游间接守卫）"。
- **归属**：R7 遗留问题（Attack-2），R8-4 无义务修复，但 R8-4 修改了该 docstring（L27-29 添加 R8-4 说明），有机会一并修正表述。

### 维度 3：DRY ✅

**验证内容**：6 处内联守卫是否全部消除，是否引入新重复。

**证据**：grep `n_bins` 在 calibration.py 中，6 处均为 `n_bins = _validate_n_bins(n_bins)` 调用，无内联 `isinstance` / `raise ValueError` 重复代码。R7 的 7 处重复代码（1 处定义 + 6 处内联）已消除为 1 处定义 + 6 处调用 ✅

**结论**：DRY 违反已消除，未引入新重复。

### 维度 4：可维护性 ⚠️

#### Attack-R8-4-2 [轾微] `upper_bound` 参数未被任何调用方使用，R8-4 修改 docstring 时未一并清理

- **位置**：`src/utils/calibration.py` L21 `def _validate_n_bins(n_bins, upper_bound=10**4):`
- **问题描述**：`upper_bound` 参数有默认值 `10**4`，但 grep 所有 10 处调用方（calibration.py 6 处 + scripts 4 处）均为 `_validate_n_bins(n_bins)`，**无一处传入 `upper_bound`**。该参数实际上是多余的，增加了维护负担（后续维护者可能误以为不同调用方有不同上界）。
- **影响分析**：无功能影响，仅代码冗余。
- **严重度**：轾微
- **建议修复**：删除 `upper_bound` 参数，硬编码 `10**4` 到函数体内；或保留但 docstring 说明"预留扩展"。
- **归属**：R7 遗留问题（Attack-7），R8-4 无义务修复。

### 维度 5：性能 ✅

**验证内容**：修复是否引入性能回退。

**分析**：`_validate_n_bins` 是 O(1) 操作（类型检查 + 两次比较），6 处调用均在函数入口执行一次，对 `ece`/`brier_parts` 等 O(n_bins·n) 主逻辑无可测量影响。R7 内联守卫也是 O(1)，性能等价 ✅

**结论**：无性能回退。

### 维度 6：测试覆盖 ✅

**验证内容**：是否有对应测试验证修复。

**证据**（`tests/test_model.py`）：
- L204-223 `test_brier_parts_n_bins_validation`：BAD_N_BINS 循环测试 `brier_parts` + `compute_all_metrics` ✅
- L225-242 `test_ece_mce_bootstrap_ece_n_bins_guards`：BAD_N_BINS 循环测试 `ece`/`mce`/`bootstrap_ece` ✅
- BAD_N_BINS = `[0, -1, 1.5, None, True, "10", 2.0, 10**18]` 覆盖所有非法类型 ✅
- pytest 运行：24 passed in 7.49s ✅

**结论**：6 处守卫中 5 处有直接测试（ece/mce/bootstrap_ece/brier_parts/compute_all_metrics），plot_reliability_diagram 见 R8-5 审查。

### 维度 7：文档一致性 ✅

**验证内容**：docstring 是否与代码一致。

**证据**：
- L27-29 R8-4 修复说明："calibration.py 内 ece/bootstrap_ece/brier_parts/mce/plot_reliability_diagram/compute_all_metrics 6 处守卫已全部改为调用 `_validate_n_bins`" —— 与实际代码一致 ✅
- L38-39 Raises 说明："ValueError: n_bins 非 int/np.integer、为 bool、<1 或 > upper_bound" —— 与 L41 实现一致 ✅

**结论**：docstring 与代码一致（除 Attack-R8-4-1 的表述不精确外）。

---

## R8-1 审查：SEED_STRATEGY_VERSION 共享常量

### 维度 1：正确性 ✅

**验证内容**：`SEED_STRATEGY_VERSION` 定义是否存在，import 是否正确。

**证据**：
- `src/data/l2_shifts.py` L30: `SEED_STRATEGY_VERSION = "md5_v1"` ✅
- `scripts/eval_l2_shift.py` L18: `from src.data.l2_shifts import get_l2_shifts, apply_shift, SEED_STRATEGY_VERSION` ✅
- `scripts/run_e1a_l2_shift_full.py` L80: `from src.data.l2_shifts import get_l2_shifts, apply_shift, SEED_STRATEGY_VERSION` ✅
- 两脚本使用 `SEED_STRATEGY_VERSION` 常量（eval_l2_shift L190/L198，run_e1a L268/L434），不再硬编码 `"md5_v1"` ✅

**结论**：正确性无问题。

### 维度 2：完整性 ✅

**验证内容**：是否有其他地方硬编码 `"md5_v1"` 或定义 `SEED_STRATEGY_VERSION`。

**证据**（全项目 grep）：
- grep `md5_v1`：只在 `l2_shifts.py` L30（定义）和 `docs/` 中找到，**无 .py 文件硬编码** ✅
- grep `SEED_STRATEGY_VERSION`：只在 `l2_shifts.py`（定义）、`eval_l2_shift.py`（import+使用）、`run_e1a_l2_shift_full.py`（import+使用）、`docs/` 中找到 ✅
- grep `__seed_strategy__`：只在 `eval_l2_shift.py`（L190/L198）、`run_e1a_l2_shift_full.py`（L268/L434）、`docs/` 中找到，均通过 `SEED_STRATEGY_VERSION` 常量引用 ✅

**结论**：无遗漏的硬编码或重复定义。

### 维度 3：DRY ✅

**验证内容**：是否消除了重复定义。

**证据**：R7 修复前 `SEED_STRATEGY_VERSION = "md5_v1"` 在 `run_e1a_l2_shift_full.py` L140 定义，`eval_l2_shift.py` L196 硬编码 `"md5_v1"`（双源）。R8-1 后单点定义在 `l2_shifts.py` L30，两脚本 import 引用 ✅

**结论**：DRY 违反已消除。

### 维度 4：可维护性 ⚠️

#### Attack-R8-1-1 [轻微] SEED_STRATEGY_VERSION 定义在数据变换模块 l2_shifts.py 中，违反单一职责原则

- **位置**：`src/data/l2_shifts.py` L30
- **问题描述**：`l2_shifts.py` 是 L2 移位变换模块（降采样/导联/噪声/增益），其职责是**数据变换**。`SEED_STRATEGY_VERSION` 是**实验管理**层面的版本标记，与数据变换逻辑无关。将实验管理常量放在数据变换模块中，违反单一职责原则（SRP）。
- **影响分析**：
  1. 语义耦合：维护者修改数据变换逻辑时可能误改版本标记，反之亦然。
  2. 依赖方向：scripts 依赖 l2_shifts 的数据变换功能，现在额外依赖其版本标记常量，依赖理由不纯。
  3. 扩展困难：未来若有其他实验（非 L2 移位）也需要 `SEED_STRATEGY_VERSION`，需从 `l2_shifts` import，语义怪异。
- **反例**：新增 `run_e7_xxx.py` 实验需要版本标记，需 `from src.data.l2_shifts import SEED_STRATEGY_VERSION`——从"L2 移位变换"模块导入"实验版本标记"，语义不通。
- **严重度**：轻微（功能正确，仅架构语义不理想）
- **建议修复**：将 `SEED_STRATEGY_VERSION` 提取到 `src/utils/experiment_meta.py` 或 `src/constants.py` 等专门模块。但需权衡：当前两脚本已依赖 `l2_shifts`，提取到新模块需新增 import，改动量增大。**可挂起**——当前只有 2 个脚本使用，且都依赖 `l2_shifts`，实际耦合可接受。
- **归属**：R8-1 的设计选择，非缺陷。

### 维度 5：性能 ✅

**结论**：常量定义和 import 无性能影响。

### 维度 6：测试覆盖 ✅

**结论**：`SEED_STRATEGY_VERSION` 是字符串常量，无需专门测试。两脚本的断点续传逻辑（`is_checkpoint_complete`）已有集成测试覆盖（通过实际运行验证）。

### 维度 7：文档一致性 ✅

**证据**：
- `l2_shifts.py` L26-29 注释解释了 `SEED_STRATEGY_VERSION` 的用途（"消除 eval_l2_shift.py 与 run_e1a_l2_shift_full.py 双点定义的 DRY 违反"）✅
- `run_e1a_l2_shift_full.py` L137-138 注释："SEED_STRATEGY_VERSION 已提取至 src/data/l2_shifts.py 共享模块" ✅
- `eval_l2_shift.py` L186-189 注释解释了 per-seed 标记写入逻辑 ✅

**结论**：文档与代码一致。

---

## R8-2 审查：safety_source_summary 列

### 维度 1：正确性 ✅

**验证内容**：4 处修改点是否正确。

**证据**（`scripts/run_e1a_l2_shift_full.py`）：
1. **聚合字典初始化**（L494-496）：
   ```python
   agg[key] = {"safeties": [], "raw_ece": [], "raw_brier_rel": [],
               "brier_impr": [], "ts_delta_ece": [], "archs": [],
               "safety_sources": []}
   ```
   ✅ 新增 `"safety_sources": []` 列表

2. **循环 append**（L503）：
   ```python
   agg[key]["safety_sources"].append(safety_source)
   ```
   ✅ 在 L466 `safety_source = "computed" if "safety" in cell else "not_computed"` 之后 append

3. **390 行输出字段**（L511-522）：
   ```python
   n_computed = int(np.sum([s == "computed" for s in v["safety_sources"]]))
   ...
   "safety_source_summary": f"{n_computed}/{n_arch} computed",
   ```
   ✅ 计算逻辑正确：`n_computed` 统计 `"computed"` 来源数量，`n_arch` 是总架构数

4. **fieldnames**（L627）：
   ```python
   "n_archs", "archs", "safety_rate", "safety_count", "safety_source_summary",
   ```
   ✅ `safety_source_summary` 在 fieldnames 中，位置与 rows_390 字段一致

**结论**：4 处修改正确，逻辑自洽。

### 维度 2：完整性 ✅

**验证内容**：是否有其他 CSV 输出也缺少这个列。

**证据**：
- 390 主矩阵（`OUT_CSV_390`）：有 `safety_source_summary` 列 ✅
- 780 详细附录（`OUT_CSV_780`）：有 `safety_source` 列（L635，每行标注来源），**不需要** `safety_source_summary`（聚合摘要只适用于聚合行）✅
- 其他脚本的 CSV（如 `run_e2`/`run_e3`/`run_e4`/`run_e6`）：不输出 safety 相关列，不在 R8-2 修复范围 ✅

**结论**：无遗漏。

### 维度 3：DRY ✅

**验证内容**：`safety_source` 判断逻辑是否重复。

**证据**：`safety_source` 的判断在 L466 单点定义（`safety_source = "computed" if "safety" in cell else "not_computed"`），780 行（L488）和 390 聚合（L503 append）共用此变量 ✅

**结论**：无新重复。

### 维度 4：可维护性 ⚠️

#### Attack-R8-2-1 [轾微] safety_source_summary 格式 "n_computed/n_arch computed" 无法区分 not_computed 与未来可能的第三种来源

- **位置**：`scripts/run_e1a_l2_shift_full.py` L522
- **问题描述**：`safety_source_summary` 格式为 `f"{n_computed}/{n_arch} computed"`，只统计 `"computed"` 数量。当前 `safety_source` 只有两个值（`"computed"` / `"not_computed"`），`n_arch - n_computed` 隐含为 `not_computed` 数量。但若未来引入第三种来源（如 `"error"` / `"skipped"`），格式 `"0/2 computed"` 无法区分"0 computed + 2 not_computed"与"0 computed + 2 error"。
- **影响分析**：当前无第三种来源，无实际影响。但格式设计不够前瞻。
- **严重度**：轾微
- **建议修复**：改为 `f"{n_computed}/{n_arch} computed ({n_arch - n_computed} not_computed)"` 或用 JSON 格式。**可挂起**——当前只有两种来源。

#### Attack-R8-2-2 [轾微] safety_source_summary 为字符串类型，与 CSV 其他数值列类型不一致

- **位置**：`scripts/run_e1a_l2_shift_full.py` L522
- **问题描述**：390 CSV 中 `safety_rate`/`safety_count`/`raw_ece_mean` 等为数值类型，`safety_source_summary` 为字符串类型（如 `"2/2 computed"`）。CSV 消费者（如 pandas `read_csv`）默认推断类型时，字符串列会被推断为 `object` 类型，可能影响后续数值分析。
- **影响分析**：CSV 本身是文本格式，消费者需显式指定类型。实际影响轻微。
- **严重度**：轾微
- **建议修复**：无需修复，CSV 混合类型是常规模式。

### 维度 5：性能 ✅

**结论**：`safety_sources` 列表 append 和 `np.sum` 均为 O(n_arch)（n_arch ≤ 2），无可测量影响。

### 维度 6：测试覆盖 ⚠️

#### Attack-R8-2-3 [轻微] safety_source_summary 列无单元测试验证

- **位置**：`scripts/run_e1a_l2_shift_full.py` L511-522
- **问题描述**：`safety_source_summary` 的计算逻辑（`n_computed` 统计 + 格式化）无单元测试覆盖。需运行完整实验（集成测试）才能验证输出。
- **影响分析**：`aggregate_to_390` 函数可单独单元测试（输入 mock `all_results`，验证输出 `rows_390` 含正确 `safety_source_summary`），但当前无此测试。
- **严重度**：轻微（逻辑简单，且 `safety_source` 已有 L466 单点定义）
- **建议修复**：为 `aggregate_to_390` 添加单元测试，构造 mock `all_results`（含/不含 `safety` 字段），验证 `safety_source_summary` 输出。**可挂起**——逻辑简单，集成测试已隐式覆盖。

### 维度 7：文档一致性 ✅

**证据**：
- L509-510 注释："safety_source_summary 使主矩阵 safety_rate 聚合透明，标注 n_computed/n_arch" ✅
- L522 行内注释："R8-2：聚合来源透明化" ✅
- L627 fieldnames 行内注释："R8-2：聚合来源透明化" ✅

**结论**：文档与代码一致。

---

## R8-5 审查：BAD_N_BINS 循环测试

### 维度 1：正确性 ✅

**验证内容**：BAD_N_BINS 常量定义，循环是否覆盖所有非法值，TypeError 死分支是否移除。

**证据**（`tests/test_model.py`）：
- L19: `BAD_N_BINS = [0, -1, 1.5, None, True, "10", 2.0, 10**18]` ✅
  - `0`: 边界值（<1）✅
  - `-1`: 负数 ✅
  - `1.5`: 非整数 float ✅
  - `None`: NoneType ✅
  - `True`: bool ✅
  - `"10"`: 字符串 ✅
  - `2.0`: 整数 float（值合法但类型非法）✅
  - `10**18`: 超上界 ✅
- L220-223: `compute_all_metrics` 的 BAD_N_BINS 循环 ✅
- L221-223: `brier_parts` 的 BAD_N_BINS 循环 ✅
- L232-238: `ece`/`mce`/`bootstrap_ece` 的 BAD_N_BINS 循环 ✅
- grep `TypeError` 在 test_model.py：只在 L220 注释中提到"移除 TypeError 死分支"，**无实际 TypeError 代码** ✅
- pytest 运行：**24 passed in 7.49s** ✅

**结论**：正确性无问题，TypeError 死分支已彻底移除。

### 维度 2：完整性 ⚠️

#### Attack-R8-5-1 [轻微] plot_reliability_diagram 的 _validate_n_bins 守卫无测试覆盖

- **位置**：`src/utils/calibration.py` L724（`plot_reliability_diagram` 调用 `_validate_n_bins`）vs `tests/test_model.py`（无 `plot_reliability_diagram` 测试）
- **问题描述**：R8-4 将 `plot_reliability_diagram` 的内联守卫改为调用 `_validate_n_bins`（L724），但 R8-5 的 BAD_N_BINS 循环只覆盖了 5 个函数（`ece`/`mce`/`bootstrap_ece`/`brier_parts`/`compute_all_metrics`），**`plot_reliability_diagram` 的守卫无测试**。
- **影响分析**：`plot_reliability_diagram` 是可视化函数，非核心指标，且守卫逻辑与其他 5 处完全相同（都调用 `_validate_n_bins`），测试缺失风险低。但 R8-4 修改了 `plot_reliability_diagram` 的守卫（内联→调用），R8-5 有机会一并添加测试。
- **严重度**：轻微（守卫逻辑集中在一处，测试缺失风险低）
- **建议修复**：在 `test_brier_parts_n_bins_validation` 或新测试方法中添加：
  ```python
  from src.utils.calibration import plot_reliability_diagram
  for bad_n_bins in BAD_N_BINS:
      with pytest.raises(ValueError):
          plot_reliability_diagram(probs, labels, n_bins=bad_n_bins)
  ```
  **可挂起**——`plot_reliability_diagram` 非核心指标，且 R7 反方已认可此点可永久挂起（见 `p0r7_counter_p0_4.md` L168）。
- **归属**：R7 遗留问题（Attack-5），R8-5 无义务修复。

### 维度 3：DRY ✅

**验证内容**：BAD_N_BINS 常量是否复用。

**证据**：`BAD_N_BINS` 在 L19 模块级定义，被 `test_brier_parts_n_bins_validation`（L217/L221）和 `test_ece_mce_bootstrap_ece_n_bins_guards`（L232）共用 ✅

**结论**：DRY 良好。

### 维度 4：可维护性 ✅

**结论**：BAD_N_BINS 模块级常量，新增非法值只需修改一处，所有测试自动覆盖 ✅

### 维度 5：性能 ✅

**结论**：BAD_N_BINS 循环 8 个值 × 5 个函数 = 40 次 `pytest.raises`，对测试套件无可测量影响（7.49s 总时长）✅

### 维度 6：测试覆盖 ✅

**验证内容**：pytest 是否通过，测试是否充分。

**证据**：
- `pytest tests/test_model.py -x -q`：**24 passed in 7.49s** ✅
- BAD_N_BINS 覆盖 8 种非法类型（bool/None/str/float/int/超上界/零/负）✅
- 合法值 `n_bins=1`（边界）有正向测试（L240-242）✅
- numpy 整数类型 `np.int64(10)` 有等价性测试（L214-215）✅

**结论**：测试覆盖充分（除 Attack-R8-5-1 外）。

### 维度 7：文档一致性 ✅

**证据**：
- L17-18 注释："brier_parts 与 ece/mce/bootstrap_ece 共用同一份非法 n_bins 列表，避免两处测试覆盖不一致" ✅
- L220 注释："R8-5: BAD_N_BINS 循环，移除 TypeError 死分支" ✅
- L230 注释列出所有非法值 ✅

**结论**：文档与代码一致。

---

## 其他测试文件的 n_bins 守卫覆盖检查

**验证内容**：`tests/` 目录其他测试文件是否需要 n_bins 守卫测试。

**证据**（grep `brier_parts|ece|mce|bootstrap_ece|compute_all_metrics|plot_reliability` 在 tests/）：
- `test_calibration_inference.py`：只用 `smooth_ece`（不接受 n_bins 参数）✅ 无需 n_bins 测试
- `test_calibration_methods.py`：只用 `smooth_ece`/`ece`（L11 import），但测试中未传 n_bins 参数（用默认值）✅ 无需 n_bins 测试
- `test_decomposition.py`：用 `ece_metric_safe`（非 calibration.py 的 ece）✅ 无需 n_bins 测试
- `test_model.py`：已覆盖 5 个函数的 n_bins 守卫 ✅

**结论**：其他测试文件不涉及 n_bins 守卫，无需同样改造 ✅

---

## 780 CSV safety_source 列与 390 CSV safety_source_summary 列的一致性验证

**验证内容**：780 CSV 的 `safety_source` 列与 390 CSV 的 `safety_source_summary` 列是否语义一致。

**证据**（`run_e1a_l2_shift_full.py`）：
- 780 CSV（L632-636）：`"safety_source"` 列，每行值为 `"computed"` 或 `"not_computed"`（来自 L466）
- 390 CSV（L627）：`"safety_source_summary"` 列，聚合值为 `f"{n_computed}/{n_arch} computed"`（来自 L511-522）
- 聚合逻辑（L503）：`agg[key]["safety_sources"].append(safety_source)` 收集 780 行的 `safety_source` 值
- 汇总逻辑（L511）：`n_computed = int(np.sum([s == "computed" for s in v["safety_sources"]]))` 统计 `"computed"` 数量

**一致性验证**：
- 780 有 2 行（2 架构），`safety_source` 分别为 `"computed"`/`"computed"` → 390 `safety_source_summary` = `"2/2 computed"` ✅
- 780 有 2 行，`safety_source` 分别为 `"computed"`/`"not_computed"` → 390 `safety_source_summary` = `"1/2 computed"` ✅
- 780 有 2 行，`safety_source` 分别为 `"not_computed"`/`"not_computed"` → 390 `safety_source_summary` = `"0/2 computed"` ✅

**结论**：780 与 390 语义一致 ✅

---

## 总结

### 攻击点汇总

| 编号 | 修复项 | 维度 | 严重度 | 位置 | 问题 | 归属 |
|------|--------|------|--------|------|------|------|
| Attack-R8-4-1 | R8-4 | 完整性 | 轻微 | calibration.py L24 | docstring "4 个 n_bins 函数" 遗漏 run_e3 的 3 个间接调用 | R7 遗留 |
| Attack-R8-4-2 | R8-4 | 可维护性 | 轾微 | calibration.py L21 | `upper_bound` 参数未被任何调用方使用 | R7 遗留 |
| Attack-R8-1-1 | R8-1 | 可维护性 | 轻微 | l2_shifts.py L30 | SEED_STRATEGY_VERSION 定义在数据变换模块，违反 SRP | R8-1 设计选择 |
| Attack-R8-2-1 | R8-2 | 可维护性 | 轾微 | run_e1a L522 | safety_source_summary 格式无法区分未来第三种来源 | R8-2 设计选择 |
| Attack-R8-2-2 | R8-2 | 可维护性 | 轾微 | run_e1a L522 | safety_source_summary 字符串类型与 CSV 数值列不一致 | R8-2 设计选择 |
| Attack-R8-2-3 | R8-2 | 测试覆盖 | 轻微 | run_e1a L511-522 | safety_source_summary 无单元测试 | R8-2 遗漏 |
| Attack-R8-5-1 | R8-5 | 完整性 | 轻微 | test_model.py | plot_reliability_diagram 守卫无测试 | R7 遗留 |

### 严重度统计

| 严重度 | 数量 | 是否阻塞收敛 |
|--------|------|--------------|
| 致命 | 0 | - |
| 严重 | 0 | - |
| 中等 | 0 | - |
| 轻微 | 4 | 否 |
| 轻微 | 3 | 否 |

### 最终裁定

**R8 修复通过反方攻击。**

4 项必修修复全部正确完成：
1. **R8-4** ✅：6 处内联守卫全部替换为 `_validate_n_bins` 调用，DRY 违反 + docstring 谎言已消除。
2. **R8-1** ✅：`SEED_STRATEGY_VERSION` 单点定义在 `l2_shifts.py`，两脚本 import 引用，无硬编码残留。
3. **R8-2** ✅：390 CSV 增加 `safety_source_summary` 列，4 处修改完整，聚合透明化达成。
4. **R8-5** ✅：BAD_N_BINS 循环覆盖 compute_all_metrics 守卫，TypeError 死分支已移除，pytest 24 passed。

**无致命/严重问题，无需 R9 修复。** 发现的 7 个攻击点均为轻微/轾微，且多数为 R7 遗留问题或合理设计选择，可挂起至后续轮次或永久挂起。

### 建议挂起清单（非必修，可选改进）

1. **Attack-R8-4-1**（轻微）：修正 `_validate_n_bins` docstring L24 表述，明确"4 个直接调用 + 3 个间接调用"。
2. **Attack-R8-2-3**（轻微）：为 `aggregate_to_390` 添加单元测试，验证 `safety_source_summary` 输出。
3. **Attack-R8-5-1**（轻微）：为 `plot_reliability_diagram` 的 n_bins 守卫添加 BAD_N_BINS 循环测试。
4. **Attack-R8-4-2/Attack-R8-1-1/Attack-R8-2-1/Attack-R8-2-2**（轾微）：永久挂起，当前无实际影响。

---

## 审查方法说明

本报告由反方挑刺代理独立撰写，基于：
1. 逐行读取 5 个修复文件（`calibration.py` / `l2_shifts.py` / `eval_l2_shift.py` / `run_e1a_l2_shift_full.py` / `test_model.py`）
2. 全项目 grep 搜索 `_validate_n_bins` / `SEED_STRATEGY_VERSION` / `md5_v1` / `__seed_strategy__` / `safety_source_summary` / `n_bins` / `TypeError` / `BAD_N_BINS`
3. 读取 `run_e3_brier_dcr_ncv.py` L125-211 确认 3 个函数未调用 `_validate_n_bins`
4. 运行 `pytest tests/test_model.py -x -q` 确认 24 passed
5. 检查 `tests/` 目录 7 个测试文件的 n_bins 覆盖情况

所有攻击点均附具体行号和代码证据，无臆测。
