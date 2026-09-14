# R6-Phase3 P0-6+7 反反方审查报告

> **审查代理**：R6-Phase3 P0-6+7 反反方审查代理（GLM-5.2）
> **审查日期**：2026-09-10
> **任务ID**：140
> **审查对象**：`docs/p0r6_attack_p0_6_7.md` 反方攻击报告（4 个轾微攻击点）
> **审查依据**：`scripts/run_e5_inception_lite.py` L156-214（函数签名/docstring）+ L520-679（修复区域）
> **裁决原则**：以代码事实为唯一判据，逐条验证攻击点的事实成立性 + 严重度合理性 + 是否遗漏高严重度问题

---

## 0. 审查前置事实核实

### 0.1 ood_probs 变量流追踪（反方报告 0.3 节复核）

逐行核对 `scripts/run_e5_inception_lite.py`：

| 行号 | 代码 | 操作 | 核实结果 |
|------|------|------|---------|
| L532 | `ood_probs = tgt_eval["probs"]` | 首次定义（numpy 数组） | ✅ 确认 |
| L549 | `ood_probs = ood_probs[ood_keep][:, :num_classes]` | 标签截断 + 概率列截断 | ✅ 确认 |
| L567 | `ood_row_sums = ood_probs.sum(axis=1, keepdims=True)` | 计算行和 | ✅ 确认 |
| L568 | `ood_zero_rows = (ood_row_sums.flatten() == 0)` | 检测全零行 | ✅ 确认 |
| L574 | `ood_probs = ood_probs[~ood_zero_rows]` | 丢弃全零行 | ✅ 确认 |
| L579 | `ood_probs = ood_probs / ood_row_sums` | 归一化 | ✅ 确认 |
| L583 | `if len(cal_probs) == 0:` | early-return 检查点 | ✅ 确认 |
| L593 | `n_ood=int(len(ood_probs))` | R6 修复使用点 | ✅ 确认 |

**关键确认**：L579 → L583 → L593 之间无对 `ood_probs` 的重赋值。L593 处 `ood_probs` 状态 = 截断后 + 全零行过滤后 + 归一化后，与正常路径 L654 引用的变量状态完全一致。

### 0.2 函数签名默认值核实

`_make_transfer_result` 签名（L156-179）：
- L162：`n_ood: int = 0` — 默认值 0 ✅ 确认
- L163：`ood_acc_raw: float = float("nan")` — 默认 nan ✅ 确认

### 0.3 docstring 内容核实

L180-190 docstring 原文：
> "统一所有 transfer result dict 的 schema。early-return / skipped / error 路径下不可用的字段填入合理默认值（0 / False / nan / None）"

**确认**：docstring 仅声明 schema 统一策略，**未显式定义 n_ood 在 skipped 行的语义**（"存在样本数" vs "已评估样本数"）。反方 Attack-3 的事实依据成立。

### 0.4 三条 early-return 路径 n_ood 传参方式核实

| 路径 | 行号 | n_ood 传参 | 实际值 | 核实结果 |
|------|------|-----------|--------|---------|
| cal-empty | L589-598 | 显式 `int(len(ood_probs))` | 截断+过滤后 ood 样本数 | ✅ 确认 |
| ood-empty | L602-610 | 不传（依赖默认 0） | 0（L599 已确认 len==0） | ✅ 确认 |
| 正常路径 | L650-670 | 显式 `int(len(ood_probs))` | 截断+过滤后 ood 样本数 | ✅ 确认 |

**确认**：cal-empty 与 ood-empty 传参风格确实不一致（反方 Attack-5 事实依据成立），但值均正确。

---

## 1. 逐条攻击点裁决

### Attack-1：skipped=True + n_ood>0 语义张力

- **反方主张**：cal 空 + ood 非空时，修复后行 `{skipped=True, n_ood=200, ood_acc_raw=nan}`，下游 `df.n_ood.sum()`（不过滤 skipped）会将未评估的 200 个 ood 样本计入"已评估总数"。
- **事实核实**：
  - L593 `n_ood=int(len(ood_probs))` 在 ood 非空时确实 >0 ✅
  - L597 `skipped=True` ✅
  - L163 `ood_acc_raw` 默认 nan ✅
  - 三字段并存的事实成立 ✅
- **严重度评估**：
  - `skipped=True` 是明确的无效行标记，负责任的下游分析应先 `df[df.skipped == False]` 再聚合
  - n_ood 是**元数据**（样本计数），非**评估结果**（ood_acc_raw/ece 等）。元数据在 skipped 行有效是合理的——描述"存在的样本数"而非"评估得到的指标"
  - 误导风险仅存在于不过滤 skipped 行的粗放分析脚本，属下游使用问题而非上游数据缺陷
  - 轾微级别合理 ✅
- **裁决**：**成立（轾微）**
- **是否需修复**：否。skipped=True 已提供充分防御。可选改进：在 CSV 头注释或 docstring 声明 n_ood 语义。

---

### Attack-3：n_ood 语义未显式定义

- **反方主张**：n_ood 语义（"截断+过滤后有效样本数" vs "已评估样本数"）未在 docstring/注释/文档中显式声明，下游消费者可能误读。
- **事实核实**：
  - L180-190 docstring 原文已读取，确实**仅声明 schema 统一，未定义 n_ood 语义** ✅
  - 正常路径 L654 与 cal-empty 路径 L593 均用 `int(len(ood_probs))`，隐式确立"截断+过滤后有效样本数"语义，但未文档化 ✅
  - 反方假设 A/B/C 验证逻辑正确：假设 B（ood_probs 已过完整管线）成立，假设 C（两处引用同一状态变量）成立 ✅
- **严重度评估**：
  - 这是**文档缺陷**而非代码缺陷——代码行为正确，仅缺少显式语义声明
  - 影响范围：仅当下游消费者主动假设不同语义时才会产生混淆，实际触发概率低
  - 轾微/轻微级别合理 ✅
- **裁决**：**成立（轾微）**
- **是否需修复**：可选。在 `_make_transfer_result` docstring 添加 2 行 n_ood 语义声明即可消除歧义。

---

### Attack-5：cal-empty/ood-empty 传参风格不一致

- **反方主张**：cal-empty 路径（L593）显式传 `n_ood=int(len(ood_probs))`，ood-empty 路径（L602-610）不传 n_ood 依赖默认 0，风格不一致。
- **事实核实**：
  - L593：`n_ood=int(len(ood_probs))` 显式传参 ✅
  - L602-610：`_make_transfer_result(...)` 调用中**无 n_ood 参数** ✅（已逐行核对 L603-609）
  - L162：默认值 `n_ood: int = 0` ✅
  - L599：`if len(ood_probs) == 0:` 已确保此时 `int(len(ood_probs))` 也为 0，与默认值一致 ✅
  - 风格不一致事实成立，但值正确 ✅
- **严重度评估**：
  - 当前无 bug：ood-empty 路径在 L599 已确认 len==0，默认值 0 与显式传 0 等价
  - 反方指出的"防御性差异"合理：若未来重构使 L599 时 len(ood_probs) 不再为 0，ood-empty 隐式默认将变为错误，而 cal-empty 显式传参自适应
  - 这是**风格/防御性**问题，非功能缺陷
  - 轾微级别合理 ✅
- **裁决**：**成立（轾微）**
- **是否需修复**：可选。ood-empty 路径补传 `n_ood=int(len(ood_probs))`（1 行改动）可提升防御性与一致性。

---

### Attack-7：R5"值不同可区分"在 cal+ood 双空场景不成立

- **反方主张**：R5 终审声称"cal empty 路径 n_ood=int(len(ood_probs))，ood empty 路径 n_ood=0，值不同可区分"，但 cal+ood 双空时 L583 先返回 n_ood=0，与 ood-empty 路径 n_ood=0 不可区分（仅靠 error 字段区分）。
- **事实核实**：
  - L583 `if len(cal_probs) == 0:` 先检查 cal 空 ✅
  - L599 `if len(ood_probs) == 0:` 后检查 ood 空（仅 cal 非空时到达）✅
  - 双空场景：L583 命中，`n_ood=int(len(ood_probs))=int(0)=0`，error="cal set empty after truncation" ✅
  - ood-empty 场景（cal 非空）：L599 命中，n_ood 默认 0，error="ood set empty after truncation" ✅
  - 两场景 n_ood 均为 0，**仅靠 n_ood 确实不可区分** ✅
  - R5"值不同可区分"声明在双空场景**确实不成立** ✅
- **严重度评估**：
  - error 字段提供完整区分能力（"cal set empty..." vs "ood set empty..."）✅
  - 双空场景是极端边界（两个独立截断后均为空），实际触发概率极低
  - 双空时报告"cal empty"而非"ood empty"是合理的优先级（cal 先检查，且 cal 空时 TS 校准无法进行是更根本的阻塞）
  - 轾微级别合理 ✅
- **裁决**：**成立（轾微）**
- **是否需修复**：否。error 字段已提供区分能力，双空场景实际影响可忽略。强行区分属过度工程。

---

## 2. 高严重度问题遗漏检查

### 2.1 反方 7 维度覆盖完整性

| 维度 | 反方审查结果 | 反反方复核 |
|------|------------|-----------|
| 1. 反例构造 | Attack-1（轾微） | ✅ 已核实成立 |
| 2. 逻辑断链 | 未发现可攻击点 | ✅ 复核推理链条 4 环节均坚实（cal/ood 独立截断→n_ood 应反映实际数→int(len()) 给出正确值→结论） |
| 3. 隐含假设 | Attack-3（轾微） | ✅ 已核实成立 |
| 4. 边界失效 | 未发现可攻击点 | ✅ 复核 6 种边界场景（双空/单元素/大量/全截断/全零过滤/部分过滤）均正确 |
| 5. 自相矛盾 | Attack-5（轾微） | ✅ 已核实成立 |
| 6. 量级错误 | 未发现可攻击点 | ✅ 复核类型安全（int(int) 冗余无副作用）、无溢出（Python int 任意精度）、O(1) 复杂度 |
| 7. 语义偏移 | Attack-7（轾微） | ✅ 已核实成立 |

**7 维度全覆盖确认**：反方未跳过任何维度，3 个"未发现"维度均附详细验证理由，非敷衍跳过。

### 2.2 遗漏的高严重度问题排查

反反方独立排查以下潜在高严重度问题，确认均不存在：

| 排查项 | 排查结果 |
|--------|---------|
| ood_probs 作用域可用性 | ✅ L532 定义远早于 L583，无 UnboundLocalError 风险 |
| ood_probs 类型安全 | ✅ numpy.ndarray，len() 返回 Python int，int() 转换冗余但安全 |
| ood_probs 空数组处理 | ✅ len(array([]))=0，int(0)=0，无异常 |
| L579 归一化对 L593 的影响 | ✅ 归一化不改变数组第一维大小，len() 值不变 |
| cal/ood 截断独立性 | ✅ L544-547 用 cal_keep，L545/548-549 用 ood_keep，两掩码独立 |
| 修复引入的新 bug | ✅ 仅将 L593 从 `n_ood=0` 改为 `n_ood=int(len(ood_probs))`，无其他副作用 |
| 与正常路径 L654 一致性 | ✅ 两处均为 `int(len(ood_probs))`，引用同一状态变量 |
| OOM 异常路径（L887-891）n_ood 处理 | ✅ 异常路径 ood_probs 可能未定义，依赖默认 0 合理（异常时无法确定 ood 状态） |
| FileNotFound 路径（L521-527）n_ood 处理 | ✅ 目标数据集不存在时无 ood 样本，默认 0 正确 |

**结论**：**未发现任何遗漏的致命/严重/中等高严重度问题**。反方 7 维度攻击已充分覆盖，4 个轾微攻击点的事实均经反反方独立核实成立。

---

## 3. R6 P0-6+7 总体判定

### 3.1 攻击点裁决汇总

| 编号 | 维度 | 反方严重度 | 反反方裁决 | 是否需修复 |
|------|------|-----------|-----------|-----------|
| Attack-1 | 反例构造 | 轾微 | **成立（轾微）** | 否（skipped=True 已防御） |
| Attack-3 | 隐含假设 | 轾微 | **成立（轾微）** | 可选（docstring 补 2 行） |
| Attack-5 | 自相矛盾 | 轾微 | **成立（轾微）** | 可选（ood-empty 补 1 行） |
| Attack-7 | 语义偏移 | 轾微 | **成立（轾微）** | 否（error 字段已区分） |

### 3.2 收敛状态

| 致命 | 严重 | 中等 | 轻微 | 收敛状态 |
|------|------|------|------|---------|
| 0 | 0 | 0 | 4（全部成立，均轾微） | **已收敛** |

### 3.3 与 R5 终审预期的对照

R5 终审（`docs/p0r5_final_verdict.md` L188）预期："R6 修复后可完全收敛"

- R6 修复成功清零 R5 终审裁定的 1 个中等攻击点（Attack-4+5）✅
- R6 反方 7 维度攻击未发现任何致命/严重/中等问题 ✅
- 仅剩 4 个轾微可选改进项，不影响功能正确性 ✅
- **符合 R5 终审"R6 修复后可完全收敛"判定** ✅

### 3.4 总体判定

**R6 P0-6+7：通过** ✅

理由：
1. R6 修复（L593 `n_ood=0` → `n_ood=int(len(ood_probs))`）方向正确，与正常路径 L654 语义完全对齐
2. ood_probs 变量流（L532→L549→L574→L579→L583→L593）完整无误，L593 处引用的 ood_probs 已过完整截断+过滤+归一化管线
3. 反方 7 维度全覆盖攻击仅发现 4 个轾微攻击点，反反方独立核实均事实成立但严重度均正确归类为轾微
4. 反反方独立排查未发现任何遗漏的致命/严重/中等高严重度问题
5. 4 个轾微攻击点均不影响功能正确性，属可选改进项

---

## 4. 可选改进项清单（非必修）

以下改进项均为轾微级别，不影响 R6 P0-6+7 通过判定，可在后续迭代中择机实施：

| 编号 | 对应攻击 | 改进内容 | 文件:行号 | 改动量 | 优先级 |
|------|---------|---------|----------|--------|--------|
| IMP-1 | Attack-3 | 在 `_make_transfer_result` docstring 显式声明 n_ood 语义："截断+全零行过滤后的有效 ood 样本数；skipped=True 行仍反映存在的样本数，不代表已评估" | `run_e5_inception_lite.py` L180-190 | 2 行注释 | 低 |
| IMP-2 | Attack-5 | ood-empty 路径（L602-610）显式传 `n_ood=int(len(ood_probs))`，与 cal-empty 路径风格一致并提升防御性 | `run_e5_inception_lite.py` L606 | 1 行 | 低 |
| IMP-3 | Attack-1 | 在 CSV 头注释或 TRANSFER_RESULT_FIELDS 注释中声明 skipped 行 n_ood 语义，指导下游过滤 skipped 行后再聚合 | `run_e5_inception_lite.py` L694 附近 | 1 行注释 | 低 |
| IMP-4 | Attack-7 | 无需修复。error 字段已提供 cal-empty/ood-empty 区分能力，双空场景实际影响可忽略 | — | 0 行 | 不需要 |

**说明**：IMP-1/IMP-2/IMP-3 可一次性合并为一个小补丁（共 4 行改动），消除全部 4 个轾微攻击点中的 3 个（Attack-7 因 error 字段已补救，无需改动）。是否实施不影响 R6 P0-6+7 收敛判定。

---

## 5. 反反方审查声明

本次反反方审查对 `docs/p0r6_attack_p0_6_7.md` 反方攻击报告中的 4 个轾微攻击点（Attack-1/3/5/7）逐条进行了事实核实：

- **4 个攻击点全部事实成立**：每个攻击点描述的代码行为均经反反方独立读取源码核实，无虚构或误读
- **4 个攻击点严重度均正确归类为轾微**：均不影响功能正确性，属下游使用/文档/风格/边界声明层面
- **未发现遗漏的高严重度问题**：反方 7 维度全覆盖攻击已充分，反反方独立排查 9 项潜在高严重度风险均不存在
- **R6 修复方向正确**：`n_ood=int(len(ood_probs))` 与正常路径 L654 完全一致，ood_probs 变量流完整无误

**最终判定**：R6 P0-6+7 **通过**反反方审查。P0-6+7 的致命/严重/中等攻击点全部清零，仅剩 4 个轾微可选改进项，符合 R5 终审预期的"R6 修复后可完全收敛"判定。R6-Phase3 P0-6+7 审查流程终结。
