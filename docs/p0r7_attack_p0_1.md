# R7 反方攻击报告 — P0-1

## 攻击概述

**审查范围**：R7 修复后的 3 个核心文件
- `scripts/eval_l2_shift.py`（SEED_STRATEGY_VERSION 标记 + 续传机制）
- `scripts/run_e1a_l2_shift_full.py`（is_checkpoint_complete 纯谓词化 + safety_source 列 + docstring）
- `docs/p0r7_fix_p0_1.md`（R7 修复报告）

**参考文件**：
- `docs/p0r6_final_verdict.md`（R6 终审裁决）
- `docs/p0r6_attack_p0_1.md`（R6 反方攻击报告）

**攻击方法**：7 维度全覆盖（致命 / 一致性 / 副作用 / 数据完整性 / 边界 / 遗漏 / 回归），逐行代码实证 + grep 全局搜索确认。

**攻击结论**：R7 修复成功消除了 R6 终审裁定的全部致命缺陷（首次运行标记丢失）和严重缺陷（cell["safety"]=0 死代码 + 谓词函数副作用），但引入了 2 个中等缺陷（SEED_STRATEGY_VERSION 双点定义 DRY 违反 + 390 CSV 缺 safety_source 列）+ 1 个轻微缺陷（None→0 转换逻辑重复）。**无致命缺陷**。

---

## 攻击点清单

### Attack-1: [中等] `SEED_STRATEGY_VERSION` 双点定义，DRY 违反

- **维度**：一致性
- **位置**：`scripts/eval_l2_shift.py` L29 vs `scripts/run_e1a_l2_shift_full.py` L140
- **描述**：
  R6 终审 §8.1 建议"提取 `SEED_STRATEGY_VERSION` 到 `src/data/l2_shifts.py` 共享模块"。R7 修复选择了在两个脚本中各自定义：
  ```python
  # eval_l2_shift.py L29
  SEED_STRATEGY_VERSION = "md5_v1"

  # run_e1a_l2_shift_full.py L140
  SEED_STRATEGY_VERSION = "md5_v1"
  ```
  虽比 R6 的硬编码 `"md5_v1"` 好（变量名一致可 grep），但仍是 DRY 违反。未来版本升级（如 `md5_v2`）需修改两处，可能不同步导致续传版本检查失败。

- **证据**：
  - grep `SEED_STRATEGY_VERSION` 确认仅在两个脚本中定义，无共享模块导入
  - 两处定义值相同（`"md5_v1"`），但无编译期约束保证一致
  - R6 终审 §8.1 明确建议提取到共享模块

- **影响**：未来版本升级时可能遗漏一处，导致续传版本检查误判
- **修复建议**：提取到 `src/data/l2_shifts.py` 或 `src/utils/constants.py`，两个脚本 import
- **判定**：成立（中等，需修补）。功能等价故非致命，但 DRY 违反 + 未来维护风险。

---

### Attack-2: [中等] 390 CSV 缺 `safety_source` 列，聚合偏置不透明

- **维度**：副作用
- **位置**：`scripts/run_e1a_l2_shift_full.py` L621-625（390 CSV fieldnames）vs L628-632（780 CSV fieldnames）
- **描述**：
  R7 修复为 780 详细 CSV 增加了 `safety_source` 列（L631），但 **390 矩阵 CSV（L621-625）不含 `safety_source` 列**：
  ```python
  # L621-625: 390 CSV fieldnames（无 safety_source）
  "n_archs", "archs", "safety_rate", "safety_count",
  ...

  # L628-632: 780 CSV fieldnames（有 safety_source）
  "brier_rel_improvement", "safety", "safety_source",
  ```
  390 矩阵的 `safety_rate` 聚合中 `None → 0` 偏置（L498），审稿人看 390 CSV 无法区分哪些 cell 是 `computed`、哪些是 `not_computed`。修复报告 §2.4 声称"通过 780 CSV 的 safety_source 列可区分"，但 **390 CSV 是主矩阵**，论文引用的是 390 矩阵结果。

- **证据**：
  - L621-625 fieldnames 无 `safety_source`
  - L498 `agg[key]["safeties"].append(safety if safety is not None else 0)` — None→0 保守聚合
  - L508 `safety_rate = float(np.mean(v["safeties"]))` — 聚合后无法追溯来源
  - 780 CSV 有 `safety_source` 列但 390 CSV 没有

- **影响**：审稿人看 390 主矩阵时，safety_rate 偏置不透明
- **修复建议**：在 390 CSV 增加 `safety_source_summary` 列（如 `"2/2 computed"` 或 `"1/2 computed"`），或在论文中声明偏置方向
- **判定**：成立（中等，需修补）。780 CSV 可审计但 390 主矩阵不透明。

---

### Attack-3: [轻微] `None → 0` 转换逻辑重复，DRY 违反

- **维度**：数据完整性
- **位置**：`scripts/run_e1a_l2_shift_full.py` L489 vs L498
- **描述**：
  `None → 0` 保守转换逻辑在两处重复：
  ```python
  # L489（780 行）
  "safety": safety if safety is not None else 0,

  # L498（聚合）
  agg[key]["safeties"].append(safety if safety is not None else 0)
  ```
  两处使用完全相同的表达式 `safety if safety is not None else 0`，可提取为辅助函数或常量。

- **证据**：
  - L489 和 L498 代码模式完全相同
  - 无辅助函数封装

- **影响**：轻微 DRY 违反，未来修改保守策略需改两处
- **修复建议**：提取 `_safety_to_int(safety)` 辅助函数，或用 `int(safety or 0)` 简化
- **判定**：成立（轻微，可选改进）。功能正确，仅代码质量。

---

## 维度覆盖记录

### 维度 1: 致命 — 未发现可攻击点

**验证证据**：
- `eval_l2_shift.py` L194 `all_results[f"seed{seed}"]["__seed_strategy__"] = SEED_STRATEGY_VERSION` 在 L189 之后**无条件执行**
- L196 `if out_path.exists()` 首次运行为 False，跳过续传条件块
- L204 直接保存含标记的 `all_results`
- **首次运行标记确实被写入** ✅
- Fix-1 修复成功，R6 Attack-1（首次运行标记丢失）已关闭

### 维度 2: 一致性 — Attack-1

见 Attack-1（SEED_STRATEGY_VERSION 双点定义 DRY 违反）。

### 维度 3: 副作用 — Attack-2

见 Attack-2（390 CSV 缺 safety_source 列）。

### 维度 4: 数据完整性 — Attack-3

见 Attack-3（None→0 转换逻辑重复）。safety_source 判定逻辑本身正确（L468 `"computed" if "safety" in cell else "not_computed"`）。

### 维度 5: 边界 — 未发现可攻击点

**验证证据**：
- 多 seed 共享 JSON 文件场景：每个 seed 有独立 `seed_data` 字典（L189 `all_results[f"seed{seed}"]`），标记不互相覆盖 ✅
- 续传时旧标记不匹配：L277-278 检查 `__seed_strategy__` 版本，不匹配则 `return False` 重跑 ✅
- 空结果集场景：L508 `float("nan")` 处理 `n_arch == 0` ✅

### 维度 6: 遗漏 — 未发现可攻击点

**验证证据**：
- grep `md5_v1` 搜索全部 `.py` 文件：仅在 `eval_l2_shift.py` L29 和 `run_e1a_l2_shift_full.py` L140 出现
- grep `SEED_STRATEGY_VERSION` 搜索全部 `.py` 文件：仅在两个脚本中出现
- 无其他 `.py` 文件遗漏版本标记机制 ✅

### 维度 7: 回归 — 未发现可攻击点

**验证证据**：
- `is_checkpoint_complete` L283-284 改 `pass` 后不添加 safety 键
- 下游 `aggregate_to_390` L467 用 `cell.get("safety", None)` 容错，不触发 KeyError ✅
- grep `cell["safety"]` 搜索全部 `.py` 文件（排除 docs）：**无匹配** — 无其他地方用直接索引访问 safety 字段 ✅
- `cell["safety"] = safety`（L420）仅在 `run_e1a` 内部写入，不影响 `eval_l2_shift` 产出

---

## 攻击统计

| 严重度 | 数量 | 编号 |
|--------|------|------|
| 致命 | 0 | — |
| 严重 | 0 | — |
| 中等 | 2 | Attack-1, Attack-2 |
| 轻微 | 1 | Attack-3 |
| 不成立 | 0 | — |
| **合计** | **3** | — |

---

## 7 维度攻击覆盖记录

| 维度 | 攻击点 | 结果 |
|------|--------|------|
| 1. 致命 | — | 未发现可攻击点（Fix-1 标记写入验证通过） |
| 2. 一致性 | Attack-1（SEED_STRATEGY_VERSION 双点定义） | 找到 1 个 |
| 3. 副作用 | Attack-2（390 CSV 缺 safety_source 列） | 找到 1 个 |
| 4. 数据完整性 | Attack-3（None→0 转换重复） | 找到 1 个 |
| 5. 边界 | — | 未发现可攻击点（多 seed + 续传 + 空集 均验证通过） |
| 6. 遗漏 | — | 未发现可攻击点（grep 确认无遗漏） |
| 7. 回归 | — | 未发现可攻击点（grep 确认无 cell["safety"] 直接索引） |

---

## 结论

R7 修复**成功消除了 R6 终审裁定的全部致命和严重缺陷**：
- ✅ 首次运行标记丢失（R6 Attack-1 致命 → 清零）：L194 无条件写入 `__seed_strategy__`
- ✅ cell["safety"]=0 死代码（R6 Attack-4 严重 → 清零）：L284 改为 `pass`
- ✅ 谓词函数副作用（R6 Attack-8 严重 → 清零）：`is_checkpoint_complete` 不再修改 cell
- ✅ safety_source 列（R6 Attack-6+7 中等 → 部分清零）：780 CSV 已增加，390 CSV 仍缺（Attack-2）
- ✅ docstring 更新（R6 Attack-5 中等 → 清零）：safety 字段标注为可选

但 R7 修复**引入了 2 个中等缺陷**（Attack-1: DRY 违反 + Attack-2: 390 CSV 不透明）+ **1 个轻微缺陷**（Attack-3: None→0 重复）。

**致命缺陷：0 个**。R7 修复的核心目标（消除首次运行标记丢失 + 死代码 + 谓词副作用）已达成。

**建议 R8 修复**（按优先级排序）：
1. **Attack-1**（中等）：提取 `SEED_STRATEGY_VERSION` 到共享模块，两个脚本 import。改动量：3 行（新建模块 1 行 + 两个脚本各改 1 行 import）。
2. **Attack-2**（中等）：在 390 CSV 增加 `safety_source_summary` 列，或在论文中声明偏置方向。改动量：2-4 行。
3. **Attack-3**（轻微）：提取 `_safety_to_int(safety)` 辅助函数。改动量：3 行。

Attack-1/2/3 均为中等或轻微，不阻塞收敛。

**收敛判定**：R7 修复在 P0-1 范围内**基本收敛**——致命和严重缺陷已清零，仅剩 2 个中等缺陷 + 1 个轻微缺陷。按收敛标准（致命/严重清零），**可宣布收敛**。Attack-1/2/3 可在 R8 轮统一修补或作为可选改进。
