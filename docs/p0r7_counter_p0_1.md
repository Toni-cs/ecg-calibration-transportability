# R7 反反方审查报告 — P0-1

## 审查概述

**审查者**：反反方审查代理（公正审查者立场）
**审查对象**：`docs/p0r7_attack_p0_1.md`（反方攻击报告，3 个攻击点）
**审查方法**：逐条阅读源代码实证验证 + grep 全局搜索确认，区分真攻击 vs 伪攻击

**审查结论**：反方攻击报告的 3 个攻击点**全部成立**（0 个伪攻击 / 稻草人）。反方代理的指控均有代码实证支撑，无过度解读或误解。R7 修复在 P0-1 范围内**基本收敛**（致命/严重清零），剩余 2 中等 + 1 轻微缺陷可在 R8 轮统一修补。

---

## 逐条判定

### Attack-1: [中等] `SEED_STRATEGY_VERSION` 双点定义 DRY 违反

- **反方指控**：`eval_l2_shift.py` L29 与 `run_e1a_l2_shift_full.py` L140 各自独立定义 `SEED_STRATEGY_VERSION = "md5_v1"`，无共享模块导入，DRY 违反。
- **代码验证**：
  ```
  # eval_l2_shift.py L29
  SEED_STRATEGY_VERSION = "md5_v1"

  # run_e1a_l2_shift_full.py L140
  SEED_STRATEGY_VERSION = "md5_v1"
  ```
  - grep `SEED_STRATEGY_VERSION` 全工程：仅在两个脚本中定义（L29 + L140），无 `from ... import SEED_STRATEGY_VERSION` 语句。✅
  - grep `md5_v1` 全工程：字面量仅出现在两个脚本中。✅
  - `eval_l2_shift.py` L27-28 注释声称"与 `run_e1a_l2_shift_full.py` 共享的种子策略版本常量"，但**仅是注释声明，非代码级共享**——两处独立赋值，无编译期/导入期约束保证同步。✅
  - 两文件均已 `from src.data.l2_shifts import get_l2_shifts, apply_shift`（L18 / L80），存在现成共享模块可托管该常量。✅

- **判定**：**成立（中等，需修补）**
  - 反方指控属实：确为 DRY 违反，未来版本升级（如 `md5_v2`）需改两处，遗漏一处将导致续传版本检查误判。
  - 非致命：当前两处值相同（`"md5_v1"`），功能等价；风险仅在未来维护时显现。
  - 反方将其定为"中等"合理，未过度升级为"严重"。

- **修补方案**：
  - **文件**：`src/data/l2_shifts.py`（两脚本已导入此模块，零新增依赖）
  - **改动 1**（`src/data/l2_shifts.py`，L26 `LEAD_NAMES` 之前插入）：
    ```python
    # P0-1 R8修复（Attack-1）：种子策略版本常量单点定义，消除两脚本 DRY 违反。
    # eval_l2_shift.py 与 run_e1a_l2_shift_full.py 共同 import 此常量，
    # 未来版本升级（如 md5_v2）只需改此一处。
    SEED_STRATEGY_VERSION = "md5_v1"
    ```
  - **改动 2**（`scripts/eval_l2_shift.py` L18）：
    ```python
    # 旧：from src.data.l2_shifts import get_l2_shifts, apply_shift
    # 新：
    from src.data.l2_shifts import get_l2_shifts, apply_shift, SEED_STRATEGY_VERSION
    ```
    并删除 L27-29 的本地定义。
  - **改动 3**（`scripts/run_e1a_l2_shift_full.py` L80）：
    ```python
    # 旧：from src.data.l2_shifts import get_l2_shifts, apply_shift
    # 新：
    from src.data.l2_shifts import get_l2_shifts, apply_shift, SEED_STRATEGY_VERSION
    ```
    并删除 L137-140 的本地定义。
  - **改动量**：4 处（共享模块 +1 行定义，两脚本各改 1 行 import + 删 3 行本地定义）。

---

### Attack-2: [中等] 390 CSV 缺 `safety_source` 列，聚合偏置不透明

- **反方指控**：780 详细 CSV 有 `safety_source` 列（L631），但 390 主矩阵 CSV（L621-625）无此列。390 矩阵的 `safety_rate` 聚合中 `None → 0` 偏置（L498），审稿人看 390 CSV 无法区分 `computed` vs `not_computed`。
- **代码验证**：
  ```
  # L621-625: 390 CSV fieldnames（无 safety_source）
  "direction", "source", "target", "seed", "shift",
  "n_archs", "archs", "safety_rate", "safety_count",
  "raw_ece_mean", "raw_brier_rel_mean", "brier_impr_mean", "ts_delta_ece_mean",

  # L628-632: 780 CSV fieldnames（有 safety_source）
  ..., "brier_rel_improvement", "safety", "safety_source",
  ```
  - L498：`agg[key]["safeties"].append(safety if safety is not None else 0)` — `None→0` 保守聚合。✅
  - L508：`safety_rate = float(np.mean(v["safeties"]))` — 聚合后无法追溯来源。✅
  - L467-468：`safety = cell.get("safety", None)` + `safety_source = "computed" if "safety" in cell else "not_computed"` — 780 行级来源标注存在，但**未向上传递到 390 聚合键**。✅
  - 390 聚合字典 `agg[key]`（L496-497）只收集 `safeties` 列表，不收集 `safety_sources`。✅
  - **实际触发路径确认**：`is_checkpoint_complete` L283-284 将 `safety` 缺失视为"不阻塞完整"（`pass`），因此 `eval_l2_shift.py` 产出（不含 safety）会被续传复用，聚合时触发 `None→0`，390 CSV 的 `safety_rate` 被静默偏置且无来源标注。✅

- **判定**：**成立（中等，需修补）**
  - 反方指控属实：390 主矩阵是论文引用对象，`safety_rate` 偏置不透明确为审计缺陷。
  - 非致命：偏置方向保守（`None→0` 偏低），不会高估安全率；且 780 CSV 保留来源可交叉审计。但"需交叉另一文件才能审计主矩阵"本身即透明度不足。
  - 反方将其定为"中等"合理。

- **修补方案**：
  - **文件**：`scripts/run_e1a_l2_shift_full.py`
  - **改动 1**（L496-497，扩展聚合字典初始化）：
    ```python
    # 旧：
    agg[key] = {"safeties": [], "raw_ece": [], "raw_brier_rel": [],
                "brier_impr": [], "ts_delta_ece": [], "archs": []}
    # 新：
    agg[key] = {"safeties": [], "safety_sources": [], "raw_ece": [], "raw_brier_rel": [],
                "brier_impr": [], "ts_delta_ece": [], "archs": []}
    ```
  - **改动 2**（L498 后追加一行）：
    ```python
    agg[key]["safeties"].append(safety if safety is not None else 0)
    agg[key]["safety_sources"].append(safety_source)  # R8修复（Attack-2）：收集来源供390审计
    ```
  - **改动 3**（L509-523，390 行增加 `safety_source_summary` 字段）：
    ```python
    # 在 rows_390.append({...}) 中新增：
    n_computed = sum(1 for s in v["safety_sources"] if s == "computed")
    "safety_source_summary": f"{n_computed}/{n_arch} computed",
    ```
  - **改动 4**（L621-625，390 CSV fieldnames 增加列）：
    ```python
    # 在 "safety_count" 后追加：
    "safety_source_summary",
    ```
  - **改动量**：4 处，约 6 行。

---

### Attack-3: [轻微] `None → 0` 转换逻辑重复，DRY 违反

- **反方指控**：`safety if safety is not None else 0` 表达式在 L489 和 L498 重复出现，可提取辅助函数。
- **代码验证**：
  ```
  # L489（780 行写入）
  "safety": safety if safety is not None else 0,

  # L498（390 聚合）
  agg[key]["safeties"].append(safety if safety is not None else 0)
  ```
  - 两处表达式完全相同（`safety if safety is not None else 0`）。✅
  - 无辅助函数封装。✅
  - 语义一致：均将 `None`（未计算）保守映射为 `0`，与 `safety=0`（计算了且 TS 未改善）在 CSV 中不可区分——但此区分已由 `safety_source` 列承担（Attack-2），故此处仅是代码重复，非语义缺陷。✅

- **判定**：**成立（轻微，可选改进）**
  - 反方指控属实：确为 DRY 违反。
  - 非中等：表达式为单行三元，语义简单且稳定（保守策略 unlikely 变更），重复风险低。反方将其定为"轻微"合理，未过度升级。
  - 修补优先级低于 Attack-1/2。

- **修补方案**：
  - **文件**：`scripts/run_e1a_l2_shift_full.py`
  - **改动 1**（L145 辅助函数区，`_brier_reliability` 之前插入）：
    ```python
    def _safety_to_int(safety) -> int:
        """safety 保守转 int：None（未计算）→ 0，与 safety=0（TS 未改善）在 CSV 同值，
        由 safety_source 列区分来源。R8修复（Attack-3）：消除 L489/L498 重复。"""
        return safety if safety is not None else 0
    ```
  - **改动 2**（L489）：
    ```python
    # 旧："safety": safety if safety is not None else 0,
    # 新：
    "safety": _safety_to_int(safety),
    ```
  - **改动 3**（L498）：
    ```python
    # 旧：agg[key]["safeties"].append(safety if safety is not None else 0)
    # 新：
    agg[key]["safeties"].append(_safety_to_int(safety))
    ```
  - **改动量**：3 处，约 5 行。

---

## 反方"未发现可攻击点"维度的复核

反方报告声称维度 1/5/6/7 未发现可攻击点。反反方独立复核如下：

### 维度 1（致命）— 复核通过 ✅
- `eval_l2_shift.py` L189 `all_results[f"seed{seed}"] = seed_results` → L194 `all_results[f"seed{seed}"]["__seed_strategy__"] = SEED_STRATEGY_VERSION` 在 L196 `if out_path.exists()` **之前**无条件执行。
- 首次运行 `out_path.exists()=False`，跳过续传块，L204 直接保存含标记的 `all_results`。
- **首次运行标记确实写入**。R6 Attack-1（致命）已清零。反方"未发现可攻击点"判定正确。

### 维度 5（边界）— 复核通过 ✅
- 多 seed：L189 每个 seed 独立 `all_results[f"seed{seed}"]` 字典，标记不互相覆盖。
- 续传旧标记：L270 `if seed_data.get("__seed_strategy__") != SEED_STRATEGY_VERSION: return False` — 不匹配则重跑。
- 空结果集：L508 `float(np.mean(v["safeties"])) if n_arch else float("nan")` — `n_arch=0` 返回 nan。
- 反方"未发现可攻击点"判定正确。

### 维度 6（遗漏）— 复核通过 ✅
- grep `md5_v1` 全工程 `.py`：仅 `eval_l2_shift.py` L29 + `run_e1a_l2_shift_full.py` L140（+注释提及）。无遗漏文件。
- grep `SEED_STRATEGY_VERSION` 全工程 `.py`：仅两个脚本。无遗漏。
- 反方"未发现可攻击点"判定正确。

### 维度 7（回归）— 复核通过 ✅
- grep `cell["safety"]` 全工程 `.py`：**仅 `run_e1a_l2_shift_full.py` L420 一处**（`cell["safety"] = safety`，写入站点，在 `evaluate_one_checkpoint` 内部）。
- 下游 `aggregate_to_390` L467 用 `cell.get("safety", None)` 容错访问，不触发 KeyError。
- `is_checkpoint_complete` L283-284 改 `pass` 后不再写入 safety 键，无副作用。
- 反方"未发现可攻击点"判定正确。

---

## 总结

### 攻击点判定汇总

| 编号 | 严重度 | 反方指控 | 反反方判定 | 理由 |
|------|--------|----------|------------|------|
| Attack-1 | 中等 | SEED_STRATEGY_VERSION 双点定义 DRY 违反 | **成立** | grep 确认两处独立定义，无共享导入，注释声明非代码约束 |
| Attack-2 | 中等 | 390 CSV 缺 safety_source 列 | **成立** | L621-625 确无此列，None→0 偏置经续传路径可达，主矩阵不透明 |
| Attack-3 | 轻微 | None→0 转换逻辑重复 | **成立** | L489/L498 表达式完全相同，无辅助函数封装 |

**伪攻击数量：0**。反方攻击报告的 3 个攻击点全部有代码实证支撑，无稻草人、无误解、无过度解读。反方代理的严重度定级合理（未将 DRY 违反夸大为严重，未将偏置不透明夸大为致命）。

### R7 修复收敛判定

**R7 修复在 P0-1 范围内基本收敛**：

- ✅ **致命缺陷清零**：首次运行标记丢失（R6 Attack-1 致命）已修复——L194 无条件写入。
- ✅ **严重缺陷清零**：`cell["safety"]=0` 死代码（R6 Attack-4）已修复——L284 改 `pass`；谓词函数副作用（R6 Attack-8）已修复——`is_checkpoint_complete` 不再修改 cell。
- ⚠️ **中等缺陷 2 个**：Attack-1（DRY 违反）+ Attack-2（390 CSV 不透明）——不阻塞收敛，可在 R8 修补。
- ⚠️ **轻微缺陷 1 个**：Attack-3（None→0 重复）——可选改进。

按收敛标准（致命/严重清零），**可宣布 R7 在 P0-1 范围内收敛**。

### 是否需要 R8 修复

**建议进行 R8 修复**，但非阻塞：

1. **Attack-1**（中等，优先级高）：提取 `SEED_STRATEGY_VERSION` 到 `src/data/l2_shifts.py`。改动 4 处。消除未来版本升级不同步风险。
2. **Attack-2**（中等，优先级中）：390 CSV 增加 `safety_source_summary` 列。改动 4 处。提升主矩阵审计透明度。
3. **Attack-3**（轻微，优先级低）：提取 `_safety_to_int` 辅助函数。改动 3 处。纯代码质量改进。

三项改动总量约 13 行，无功能变更，可在 R8 轮一次性完成。若资源紧张，Attack-3 可延后或作为可选改进。
