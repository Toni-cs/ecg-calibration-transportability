# P0 R8-Phase3 反反方审查报告

> **审查日期**：2026-09-10
> **审查代理**：R8-Phase3 反反方审查代理
> **审查对象**：`docs/p0r8_attack.md` 中 7 个攻击点（均为轻微/轾微）
> **审查方法**：逐条读取源文件验证事实成立性 + 严重度合理性评估 + R9 必要性判定
> **审查结论**：**7 个攻击点事实全部成立，严重度评级基本合理（2 处报告内部不一致需澄清），均无需 R9 修复，可挂起。R8 收敛。**

---

## 一、审查概述

### 审查范围

| 攻击点 | 修复项 | 维度 | 报告评级 | 位置 |
|--------|--------|------|----------|------|
| Attack-R8-4-1 | R8-4 | 完整性 | 轻微 | calibration.py L24 |
| Attack-R8-4-2 | R8-4 | 可维护性 | 轾微 | calibration.py L21 |
| Attack-R8-1-1 | R8-1 | 可维护性 | 轾微 | l2_shifts.py L30 |
| Attack-R8-2-1 | R8-2 | 可维护性 | 轾微 | run_e1a L522 |
| Attack-R8-2-2 | R8-2 | 可维护性 | 轾微 | run_e1a L522 |
| Attack-R8-2-3 | R8-2 | 测试覆盖 | 轾微（section 标 [轻微]） | run_e1a L511-522 |
| Attack-R8-5-1 | R8-5 | 完整性 | 轾微（section 标 [轻微]） | test_model.py |

### 审查事实基础

本报告基于以下源文件逐行验证：
1. `src/utils/calibration.py` L21-43（`_validate_n_bins` 定义 + docstring）+ 6 处调用点 grep
2. `src/data/l2_shifts.py` L26-30（`SEED_STRATEGY_VERSION` 定义）
3. `scripts/eval_l2_shift.py` L18/L190/L198（import + 使用）
4. `scripts/run_e1a_l2_shift_full.py` L80/L137/L268/L434/L462-527/L627（import + 聚合逻辑 + CSV fieldnames）
5. `scripts/run_e3_brier_dcr_ncv.py` L170/L185/L207（3 个间接 n_bins 函数）
6. `tests/test_model.py` L19/L204-242（BAD_N_BINS + 测试覆盖）
7. 全项目 grep `_validate_n_bins` / `SEED_STRATEGY_VERSION` / `upper_bound` / `plot_reliability_diagram` / `md5_v1`

---

## 二、逐条审查

### Attack-R8-4-1 [轻微] `_validate_n_bins` docstring "4 个 n_bins 函数" 表述不精确

**攻击描述**：docstring L24 声称"供 calibration.py 内 6 处守卫与 scripts/ 中 4 个 n_bins 函数统一调用"，但 `run_e3_brier_dcr_ncv.py` 有 3 个函数（`brier_parts_toplabel` L170 / `brier_parts_ovr` L185 / `ece_toplabel` L207）也接受 `n_bins` 参数却未直接调用 `_validate_n_bins`，而是经下游 `brier_parts`/`ece` 间接守卫。docstring 表述遗漏这 3 个间接调用函数。

**事实验证**：
- ✅ `src/utils/calibration.py` L24 docstring 确实写"scripts/ 中 4 个 n_bins 函数"
- ✅ scripts 中直接调用 `_validate_n_bins` 的确实是 4 处：`run_e2.fit_binned_temperature` L166 / `run_e4.quintile_edges` L190 / `run_e6.compute_reliability_bins` L153 / `run_e6.bootstrap_bin_accuracy_ci` L220
- ✅ `run_e3_brier_dcr_ncv.py` L170/L185/L207 确实有 3 个函数接受 `n_bins` 参数，间接调用 `brier_parts`/`ece`（L181/L199/L211），未导入 `_validate_n_bins`
- ✅ 功能上安全：n_bins 会被下游 `_validate_n_bins` 守卫拦截，无 bool 穿透风险

**结论**：**成立**。docstring 表述确实不精确，"4 个"暗示 scripts 中只有 4 个 n_bins 函数，实际有 7 个（4 直接 + 3 间接）。

**严重度合理性**：**轻微合理**。仅 docstring 表述不精确，无功能影响，无安全风险。run_e3 的 3 个函数经下游间接守卫，功能安全。

**是否需 R9 修复**：**否**。属 R7 遗留问题（Attack-2），R8-4 无义务修复。R8-4 修改了该 docstring（L27-29 添加 R8-4 说明），有机会一并修正但非必修。可挂起至下次 docstring 维护时修正。

**建议修补方案（可选）**：docstring L24 改为"供 calibration.py 内 6 处守卫与 scripts/ 中 4 个函数直接调用（run_e3 的 3 个函数经下游间接守卫）"。

---

### Attack-R8-4-2 [轾微] `upper_bound` 参数未被任何调用方使用

**攻击描述**：`_validate_n_bins(n_bins, upper_bound=10**4)` 的 `upper_bound` 参数有默认值，但 grep 所有 10 处调用方均为 `_validate_n_bins(n_bins)`，无一处传入 `upper_bound`。参数多余，增加维护负担。

**事实验证**：
- ✅ `src/utils/calibration.py` L21 确实定义 `def _validate_n_bins(n_bins, upper_bound=10**4):`
- ✅ grep `upper_bound` 全项目：calibration.py 6 处调用均为 `_validate_n_bins(n_bins)`，scripts 4 处同理，**无一处传入 upper_bound**
- ✅ R7 反反方审查（`p0r7_counter_p0_4.md` L219-233）已判定此为"合理扩展点设计，非缺陷"

**结论**：**事实成立，但定性偏颇**。`upper_bound` 确实无消费者，事实正确。但反方"参数多余/增加维护负担"的定性不成立——带默认值的可选参数是 Python 常见的扩展点设计模式，零运行时开销、零维护成本，为未来差异化上界预留能力。R7 终审已下调为"无害"。

**严重度合理性**：**轾微偏高，应下调为无害**。R7 终审（`p0r7_final_verdict.md` L178/L192）已明确判定"upper_bound 是合理的扩展点设计（带默认值的可选参数），非'API 设计过度'；反方定性错误"，并标注"不需修补"。R8 反方重新提起此点属重复审查。

**是否需 R9 修复**：**否**。可永久挂起。强行删除 `upper_bound` 反而降低 API 灵活性，未来若需差异化上界需破坏向后兼容。

---

### Attack-R8-1-1 [轾微] SEED_STRATEGY_VERSION 定义在数据变换模块，违反 SRP

**攻击描述**：`l2_shifts.py` 是 L2 移位数据变换模块，`SEED_STRATEGY_VERSION` 是实验管理层面的版本标记，放在数据变换模块中违反单一职责原则（SRP）。

**事实验证**：
- ✅ `src/data/l2_shifts.py` L30 确实定义 `SEED_STRATEGY_VERSION = "md5_v1"`
- ✅ `l2_shifts.py` 模块 docstring（L1-20）表明其职责是"L2 移位阶梯变换"（降采样/导联/噪声/增益）
- ✅ `SEED_STRATEGY_VERSION` 是实验管理常量，语义上与数据变换逻辑无关
- ✅ 两脚本（`eval_l2_shift.py` L18 / `run_e1a_l2_shift_full.py` L80）均已 import 并使用

**结论**：**事实成立，但属合理设计选择**。SRP 确实有轻微违反——实验管理常量放在数据变换模块中。但：
1. **实际耦合可接受**：两脚本本就依赖 `l2_shifts` 的 `get_l2_shifts`/`apply_shift`，新增一个常量 import 不增加新的依赖关系
2. **提取到新模块代价大于收益**：新建 `src/utils/experiment_meta.py` 或 `src/constants.py` 需新增 import，改动量增大，但当前只有 2 个脚本使用
3. **R8-1 的核心目标是消除 DRY 违反**（双点定义），已达成。SRP 是次要考量

**严重度合理性**：**轾微合理**。功能正确，仅架构语义不理想，无实际影响。

**是否需 R9 修复**：**否**。可挂起。当前 2 个脚本都依赖 `l2_shifts`，实际耦合可接受。若未来有非 L2 移位实验也需要版本标记，再提取到公共模块。

---

### Attack-R8-2-1 [轾微] safety_source_summary 格式无法区分未来第三种来源

**攻击描述**：`safety_source_summary` 格式 `f"{n_computed}/{n_arch} computed"` 只统计 `"computed"` 数量，若未来引入第三种来源（如 `"error"`/`"skipped"`），格式 `"0/2 computed"` 无法区分"0 computed + 2 not_computed"与"0 computed + 2 error"。

**事实验证**：
- ✅ `run_e1a_l2_shift_full.py` L522 确实为 `f"{n_computed}/{n_arch} computed"`
- ✅ L466 `safety_source = "computed" if "safety" in cell else "not_computed"` —— 当前只有两种来源
- ✅ `n_computed` 统计 `"computed"` 数量，`n_arch - n_computed` 隐含为 `not_computed` 数量

**结论**：**事实成立，但属推测性前瞻**。当前只有两种来源，格式自洽。第三种来源是假设性未来场景，当前无实际影响。

**严重度合理性**：**轾微合理**。推测性前瞻问题，无当前影响。

**是否需 R9 修复**：**否**。可挂起。若未来真引入第三种来源，届时一并修改格式。当前过度设计反而增加复杂度。

---

### Attack-R8-2-2 [轾微] safety_source_summary 字符串类型与 CSV 数值列不一致

**攻击描述**：390 CSV 中 `safety_rate`/`safety_count` 等为数值类型，`safety_source_summary` 为字符串类型（如 `"2/2 computed"`），CSV 消费者默认推断为 `object` 类型，可能影响后续数值分析。

**事实验证**：
- ✅ `run_e1a_l2_shift_full.py` L522 `safety_source_summary` 确实为字符串格式
- ✅ L520 `safety_rate` 为 float，L521 `safety_count` 为 int —— 确实类型不一致
- ✅ CSV 本身是文本格式，混合类型是常规模式

**结论**：**事实成立，但属非问题**。CSV 混合类型是常规模式，pandas `read_csv` 会正确推断为 `object` 类型，消费者需显式指定类型是标准实践。`archs` 列（L519，`"+".join(...)`）也是字符串类型，已有先例。

**严重度合理性**：**轾微偏高，可下调为无害**。CSV 混合类型是常规，非缺陷。

**是否需 R9 修复**：**否**。可永久挂起。无需修复。

---

### Attack-R8-2-3 [轻微→轾微] safety_source_summary 无单元测试

**攻击描述**：`safety_source_summary` 的计算逻辑（`n_computed` 统计 + 格式化）无单元测试覆盖，需运行完整实验（集成测试）才能验证。

**事实验证**：
- ✅ `tests/test_model.py` grep `safety_source_summary` / `aggregate_to_390`：无匹配，确实无单元测试
- ✅ `aggregate_to_390` 函数（L485-529）可单独单元测试（输入 mock `all_results`，验证输出 `rows_390`）
- ✅ 逻辑简单：L466 单点定义 `safety_source` + L511 一行 `n_computed` 统计 + L522 一行格式化

**结论**：**事实成立**。确实无单元测试。但逻辑极简（3 行核心逻辑），且集成测试（实际运行 `run_e1a`）已隐式覆盖。

**严重度合理性**：**报告内部不一致**——section header（L261）标 `[轻微]`，summary table（L405）标 `轾微`。**轾微更合理**：逻辑简单（3 行），`safety_source` 已有 L466 单点定义，集成测试隐式覆盖。轻微偏高。

**是否需 R9 修复**：**否**。可挂起。逻辑简单，集成测试已隐式覆盖。若未来 `aggregate_to_390` 逻辑复杂化，再添加单元测试。

---

### Attack-R8-5-1 [轻微→轾微] plot_reliability_diagram 守卫无测试覆盖

**攻击描述**：R8-4 将 `plot_reliability_diagram` 的内联守卫改为调用 `_validate_n_bins`（L724），但 R8-5 的 BAD_N_BINS 循环只覆盖 5 个函数（`ece`/`mce`/`bootstrap_ece`/`brier_parts`/`compute_all_metrics`），`plot_reliability_diagram` 守卫无测试。

**事实验证**：
- ✅ `src/utils/calibration.py` L724 `plot_reliability_diagram` 确实调用 `_validate_n_bins(n_bins)`
- ✅ `tests/test_model.py` grep `plot_reliability_diagram`：**无匹配**，确实无测试
- ✅ BAD_N_BINS 循环覆盖 5 个函数（L217 brier_parts / L221 compute_all_metrics / L232-238 ece/mce/bootstrap_ece），未覆盖 plot_reliability_diagram
- ✅ R7 反反方审查（`p0r7_counter_p0_4.md` L168）已认可此点可永久挂起

**结论**：**事实成立**。`plot_reliability_diagram` 守卫确实无直接测试。但：
1. 守卫逻辑与其他 5 处完全相同（都调用 `_validate_n_bins`），测试 `_validate_n_bins` 本身即覆盖逻辑
2. `plot_reliability_diagram` 是可视化函数，非核心指标，测试优先级低
3. R7 已认可可永久挂起

**严重度合理性**：**报告内部不一致**——section header（L306）标 `[轻微]`，summary table（L406）标 `轾微`。**轾微更合理**：守卫逻辑集中在一处（`_validate_n_bins`），`plot_reliability_diagram` 非核心指标，R7 已认可永久挂起。轻微偏高。

**是否需 R9 修复**：**否**。可永久挂起。R7 已认可此点可永久挂起（`p0r7_counter_p0_4.md` L168）。

---

## 三、总体结论

### R8 是否收敛？

**✅ R8 收敛。P0-1 和 P0-4 完全收敛。**

4 项必修修复全部正确完成：
1. **R8-4** ✅：6 处内联守卫全部替换为 `_validate_n_bins` 调用（grep 确认 L240/575/630/682/724/791），DRY 违反 + docstring 莎言已消除
2. **R8-1** ✅：`SEED_STRATEGY_VERSION` 单点定义在 `l2_shifts.py` L30，两脚本 import 引用（grep 确认无硬编码残留）
3. **R8-2** ✅：390 CSV 增加 `safety_source_summary` 列，4 处修改完整（L496/L503/L511-522/L627）
4. **R8-5** ✅：BAD_N_BINS 循环覆盖 compute_all_metrics 守卫（L221-223），TypeError 死分支已移除，pytest 24 passed

### 是否需要 R9？

**❌ 不需要 R9 修复。**

7 个攻击点均为轻微/轾微，且：
- 3 个为 R7 遗留问题（Attack-R8-4-1 / Attack-R8-4-2 / Attack-R8-5-1），R8 无义务修复
- 2 个为合理设计选择（Attack-R8-1-1 SRP / Attack-R8-2-1 前瞻格式）
- 1 个为非问题（Attack-R8-2-2 CSV 混合类型是常规）
- 1 个为测试覆盖遗漏但逻辑简单且集成测试隐式覆盖（Attack-R8-2-3）

### 报告内部不一致说明

`docs/p0r8_attack.md` 存在 2 处严重度评级内部不一致：
- **Attack-R8-2-3**：section header（L261）标 `[轻微]`，summary table（L405）标 `轾微`
- **Attack-R8-5-1**：section header（L306）标 `[轻微]`，summary table（L406）标 `轾微`

此外，严重度统计表（L410-416）标注"轾微 4 + 轾微 3"（两行均标轾微），与报告头部（L5）"2 轻微 + 5 轾微"不一致。

**本审查采纳 summary table 的评级**（轾微），因 section header 的 [轻微] 偏高：
- Attack-R8-2-3 逻辑仅 3 行，集成测试隐式覆盖，轾微更合理
- Attack-R8-5-1 守卫逻辑集中在一处，plot_reliability_diagram 非核心，R7 已认可永久挂起，轾微更合理

**正确严重度分布**：1 轻微（Attack-R8-4-1）+ 6 轾微 = 7 个攻击点，无致命/严重/中等。

---

## 四、可挂起的攻击点清单

| 编号 | 严重度 | 挂起类型 | 理由 |
|------|--------|----------|------|
| Attack-R8-4-1 | 轻微 | 挂起至下次 docstring 维护 | R7 遗留，docstring 表述不精确，无功能影响 |
| Attack-R8-4-2 | 轾微→无害 | 永久挂起 | R7 已判定为合理扩展点设计，非缺陷 |
| Attack-R8-1-1 | 轾微 | 挂起至非 L2 实验需要版本标记时 | 合理设计选择，当前耦合可接受 |
| Attack-R8-2-1 | 轾微 | 挂起至引入第三种来源时 | 推测性前瞻，当前无实际影响 |
| Attack-R8-2-2 | 轾微→无害 | 永久挂起 | CSV 混合类型是常规模式，非问题 |
| Attack-R8-2-3 | 轾微 | 挂起至 aggregate_to_390 逻辑复杂化时 | 逻辑简单，集成测试隐式覆盖 |
| Attack-R8-5-1 | 轾微 | 永久挂起 | R7 已认可永久挂起，plot_reliability_diagram 非核心 |

---

## 五、需 R9 修复的攻击点清单

**空。** 无需 R9 修复的攻击点。

---

## 六、审查方法说明

本报告由反反方审查代理独立撰写，基于：
1. 逐行读取 6 个源文件的关键代码段（`calibration.py` L21-43 / `l2_shifts.py` L26-30 / `eval_l2_shift.py` L18/L190/L198 / `run_e1a_l2_shift_full.py` L80/L137/L268/L434/L462-527/L627 / `run_e3_brier_dcr_ncv.py` L170-211 / `test_model.py` L19/L204-242）
2. 全项目 grep `_validate_n_bins` / `SEED_STRATEGY_VERSION` / `md5_v1` / `upper_bound` / `plot_reliability_diagram` / `n_bins` / `safety_source_summary`
3. 读取 R7 反反方审查报告（`p0r7_counter_p0_4.md` L219-233 / L168）确认 R7 已判定的问题
4. 读取 R7 终审报告（`p0r7_final_verdict.md` L178/L192）确认 upper_bound 已下调为无害
5. 交叉验证攻击报告 section header 与 summary table 的严重度一致性

所有审查结论均附具体行号和代码证据，无臆测。
