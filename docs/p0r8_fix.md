# P0 R8 修复报告（Phase1 正方修复）

> 修复日期：2026-09-10
> 修复代理：R8-Phase1 正方修复代理
> 依据：R7 终审裁定 P0-1 和 P0-4 基本收敛但需 R8 修补，本报告完成 4 项必修修复后，P0-1 和 P0-4 可宣布完全收敛。

---

## 一、修复清单逐项对照

### R8-4（严重，最高优先级）— calibration.py 6 处内联守卫统一调用 _validate_n_bins

**文件**: `src/utils/calibration.py`

**改动内容**:

1. **6 处内联守卫替换为统一调用**（每处原 2 行 `if ... raise` → 1 行 `n_bins = _validate_n_bins(n_bins)`）:

| 函数 | 原行号 | 新行号 | 改动 |
|------|--------|--------|------|
| `ece` | L237-238 | L240 | `n_bins = _validate_n_bins(n_bins)` |
| `bootstrap_ece` | L573-574 | L575 | `n_bins = _validate_n_bins(n_bins)` |
| `brier_parts` | L629-630 | L630 | `n_bins = _validate_n_bins(n_bins)` |
| `mce` | L682-683 | L682 | `n_bins = _validate_n_bins(n_bins)` |
| `plot_reliability_diagram` | L725-726 | L724 | `n_bins = _validate_n_bins(n_bins)` |
| `compute_all_metrics` | L793-794 | L791 | `n_bins = _validate_n_bins(n_bins)` |

2. **更新 `_validate_n_bins` docstring**（L25-27 新增 3 行）: 明确标注 R8-4 已将 6 处守卫全部改为调用 `_validate_n_bins`，消除此前 docstring "统一调用" 声称与内联实现不符的"谎言"。

**验证**: `grep "isinstance\(n_bins, bool\)" src/utils/calibration.py` 仅返回 L41（`_validate_n_bins` 函数自身内部），6 处内联守卫已全部消除。

**改动行数**: -12 行（删除 6×2 内联守卫）+ 6 行（新增 6×1 调用）+ 3 行（docstring）= 净 -3 行（逻辑简化）+ 3 行（文档）。

---

### R8-1（中等）— 提取 SEED_STRATEGY_VERSION 到共享模块

**文件**: `src/data/l2_shifts.py` + `scripts/eval_l2_shift.py` + `scripts/run_e1a_l2_shift_full.py`

**改动内容**:

1. **`src/data/l2_shifts.py` L26-31 新增**（6 行含注释）:
   ```python
   # P0-1 R8-1修复：seed_strategy 版本标记共享定义（消除 eval_l2_shift.py 与
   # run_e1a_l2_shift_full.py 双点定义的 DRY 违反）。...
   SEED_STRATEGY_VERSION = "md5_v1"
   ```

2. **`scripts/eval_l2_shift.py`**:
   - L19: import 改为 `from src.data.l2_shifts import get_l2_shifts, apply_shift, SEED_STRATEGY_VERSION`
   - 删除 L27-29 本地定义（3 行含注释）

3. **`scripts/run_e1a_l2_shift_full.py`**:
   - L81: import 改为 `from src.data.l2_shifts import get_l2_shifts, apply_shift, SEED_STRATEGY_VERSION`
   - 删除 L137-140 本地定义（4 行含注释），替换为 2 行 R8-1 修复说明注释

**验证**: `grep "SEED_STRATEGY_VERSION = \"md5_v1\""` 确认代码文件中仅 `src/data/l2_shifts.py` L30 一处定义（其余命中均为 `docs/` 历史文档引用，非代码）。

**改动行数**: +6 行（l2_shifts 定义）+ 1 行（eval import 修改）- 3 行（eval 删除）+ 1 行（run_e1a import 修改）- 4 行（run_e1a 删除）+ 2 行（run_e1a 注释）= 净 +3 行。

---

### R8-2（中等）— 390 CSV 增加 safety_source_summary 列

**文件**: `scripts/run_e1a_l2_shift_full.py`

**改动内容**:

1. **聚合字典初始化**（L495-496）: 增加 `"safety_sources": []` 列表字段
2. **聚合循环**（L503）: 增加 `agg[key]["safety_sources"].append(safety_source)`
3. **390 行输出字段**（L510-511 注释 + L513 n_computed 计算 + L520 safety_source_summary 字段）:
   ```python
   n_computed = int(np.sum([s == "computed" for s in v["safety_sources"]]))
   ...
   "safety_source_summary": f"{n_computed}/{n_arch} computed",
   ```
4. **390 CSV fieldnames**（L628）: 增加 `"safety_source_summary"`

**语义**: `safety_source_summary` 值形如 `"2/2 computed"`（两架构均实算）或 `"1/2 computed"`（一架构缺失 safety），使主矩阵 `safety_rate` 聚合来源透明可审计。

**改动行数**: +1 行（初始化）+ 1 行（append）+ 2 行（注释）+ 1 行（n_computed）+ 1 行（字段）+ 1 行（fieldnames 注释修改）= 净 +7 行。

---

### R8-5（中等）— compute_all_metrics 守卫测试改为 BAD_N_BINS 循环

**文件**: `tests/test_model.py`

**改动内容**:

L220-226 原代码（7 行，含 TypeError 死分支）:
```python
# Test compute_all_metrics guard
with pytest.raises(ValueError):
    compute_all_metrics(probs, labels, n_bins=0)
with pytest.raises(ValueError):
    compute_all_metrics(probs, labels, n_bins=-1)
with pytest.raises((ValueError, TypeError)):  # TypeError 是死分支
    compute_all_metrics(probs, labels, n_bins=1.5)
```

替换为（4 行，BAD_N_BINS 循环）:
```python
# Test compute_all_metrics guard (R8-5: BAD_N_BINS 循环，移除 TypeError 死分支)
for bad_n_bins in BAD_N_BINS:
    with pytest.raises(ValueError):
        compute_all_metrics(probs, labels, n_bins=bad_n_bins)
```

**验证**: `grep "TypeError" tests/test_model.py` 仅返回 L220 注释行，无 `pytest.raises((ValueError, TypeError))` 死分支残留。

**改动行数**: -7 行 + 4 行 = 净 -3 行。

---

## 二、验证结果

### pytest 输出摘要

```
$ python -m pytest tests/test_model.py -v
============================= test session starts =============================
platform win32 -- Python 3.12.10, pytest-9.0.3
collecting ... collected 24 items

tests/test_model.py::TestCalibration::test_brier_parts_n_bins_validation PASSED [ 83%]
tests/test_model.py::TestCalibration::test_ece_mce_bootstrap_ece_n_bins_guards PASSED [ 87%]
...（其余 22 项均 PASSED）

============================= 24 passed in 7.47s ==============================
```

**n_bins 专项测试**:
```
$ python -m pytest tests/test_model.py -k "n_bins" -v
2 passed, 22 deselected in 4.39s
```

### grep 残留检查

| 检查项 | 命令 | 结果 | 状态 |
|--------|------|------|------|
| 内联守卫残留 | `grep "isinstance\(n_bins, bool\)" src/utils/calibration.py` | 仅 L41（`_validate_n_bins` 自身） | ✅ |
| 双点定义残留 | `grep "SEED_STRATEGY_VERSION = \"md5_v1\""` 代码文件 | 仅 `src/data/l2_shifts.py` L30 | ✅ |
| TypeError 死分支残留 | `grep "TypeError" tests/test_model.py` | 仅 L220 注释 | ✅ |
| `_validate_n_bins` 调用数 | `grep "n_bins = _validate_n_bins\(n_bins\)" src/utils/calibration.py` | 6 处（L240/575/630/682/724/791） | ✅ |

### 脚本语法验证

```
$ python -c "import ast; ast.parse(open('scripts/eval_l2_shift.py'...))"
eval_l2_shift.py: syntax OK
run_e1a_l2_shift_full.py: syntax OK

$ python -c "from src.data.l2_shifts import SEED_STRATEGY_VERSION; print(...)"
l2_shifts SEED_STRATEGY_VERSION: md5_v1
```

---

## 三、改动行数统计

| 修复项 | 文件 | 新增 | 删除 | 净改动 |
|--------|------|------|------|--------|
| R8-4 | src/utils/calibration.py | +9 | -12 | -3 |
| R8-1 | src/data/l2_shifts.py | +6 | 0 | +6 |
| R8-1 | scripts/eval_l2_shift.py | +1 | -3 | -2 |
| R8-1 | scripts/run_e1a_l2_shift_full.py | +3 | -4 | -1 |
| R8-2 | scripts/run_e1a_l2_shift_full.py | +7 | 0 | +7 |
| R8-5 | tests/test_model.py | +4 | -7 | -3 |
| **合计** | **6 文件** | **+30** | **-26** | **+4** |

实际净改动 +4 行（含注释），核心逻辑改动约 12 行，与 R7 终审裁定"R8 必修 4 项 ~12 行改动"一致。

---

## 四、与 R7 终审裁定 R8 修复清单逐项对照

| R7 裁定项 | 优先级 | 目标 | 本报告完成状态 | 验证 |
|-----------|--------|------|----------------|------|
| R8-4 | 严重（最高） | 6 处内联守卫改为调用 `_validate_n_bins`，消除 DRY 违反 + docstring 谎言 | ✅ 6 处全部替换 + docstring 更新 | grep 确认无内联守卫残留 |
| R8-1 | 中等 | 提取 `SEED_STRATEGY_VERSION` 到共享模块，消除双点定义 DRY 违反 | ✅ 提取至 `src/data/l2_shifts.py`，两脚本改为 import | grep 确认单点定义 |
| R8-2 | 中等 | 390 CSV 增加 `safety_source_summary` 列，使主矩阵 `safety_rate` 聚合透明 | ✅ 聚合初始化+循环+输出字段+fieldnames 4 处修改 | 语法验证通过 |
| R8-5 | 中等 | `compute_all_metrics` 守卫测试改为 `BAD_N_BINS` 循环，移除 `TypeError` 死分支 | ✅ 7 行 → 4 行循环 | grep 确认无 TypeError 死分支 |

**结论**: R7 终审裁定的 4 项必修修复全部完成，所有测试通过（24/24 PASSED），无残留违规模式。**P0-1 和 P0-4 可宣布完全收敛。**
