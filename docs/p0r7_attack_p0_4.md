# R7 反方攻击报告 — P0-4

## 攻击概述

**审查范围**：R7 修复后的 7 个文件
- `src/utils/calibration.py`（`_validate_n_bins` 公共函数 + 6 处内联守卫）
- `tests/test_model.py`（`BAD_N_BINS` 常量 + 2 个测试方法）
- `scripts/run_e2_ablation_discrimination.py`（`fit_binned_temperature` 守卫）
- `scripts/run_e4_temperature_analysis.py`（`quintile_edges` 守卫）
- `scripts/run_e6_reliability_diagrams.py`（`compute_reliability_bins` + `bootstrap_bin_accuracy_ci` 守卫）
- `docs/p0r7_fix_p0_4.md`（R7 修复报告）
- `docs/p0r6_final_verdict.md`（R6 终审裁决，参考）

**攻击方法**：7 维度全覆盖（反例构造 / 逻辑断链 / 隐含假设 / 边界失效 / 自相矛盾 / 量级错误 / 语义偏移），逐行代码实证 + grep 全局搜索确认遗漏。

**攻击结论**：R7 修复成功消除了 R6 终审裁定的致命缺陷（scripts 4 函数无守卫）和严重缺陷（上界 10**6 过大、brier_parts 测试不统一），但引入了 1 个严重的一致性缺陷（`_validate_n_bins` 定义但 calibration.py 内部 6 处守卫未调用）+ 2 个中等缺陷（run_e3 遗漏 + compute_all_metrics 测试不完整）+ 5 个轾微缺陷。**无致命缺陷**。

---

## 攻击点清单

### Attack-1: [严重] `_validate_n_bins` 定义但 calibration.py 内部 6 处守卫未调用，DRY 违反 + docstring 与实现矛盾

- **维度**：自相矛盾 / 一致性
- **位置**：`src/utils/calibration.py` L21-40（`_validate_n_bins` 定义）vs L237 / L573 / L629 / L682 / L725 / L793（6 处内联守卫）
- **描述**：
  R6 终审 L143 建议"抽取 `_validate_n_bins(n_bins)` 公共函数到 `src/utils/calibration.py`，scripts 统一调用"。R7 修复确实定义了 `_validate_n_bins`（L21-40），且 scripts 4 个函数正确调用了它。但 **calibration.py 内部 6 处守卫（ece/bootstrap_ece/brier_parts/mce/plot_reliability_diagram/compute_all_metrics）没有调用 `_validate_n_bins`，而是各自重复了完全相同的内联代码**：
  ```python
  if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1 or n_bins > 10**4:
      raise ValueError(f"n_bins must be a positive integer in [1, 10000], got {n_bins!r}")
  ```
  这与 `_validate_n_bins` L38-39 的逻辑完全相同但未调用。

  更严重的是，`_validate_n_bins` 的 docstring L24 声称：
  > "供 calibration.py 内 6 处守卫与 scripts/ 中 4 个 n_bins 函数统一调用，避免守卫模式重复散布。"

  但实际 6 处守卫**没有调用** `_validate_n_bins`，docstring 与实现直接矛盾。

- **证据**：
  - grep 确认 6 处守卫均为内联代码：`if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1 or n_bins > 10**4:`（L237/L573/L629/L682/L725/L793）
  - grep 确认 calibration.py 内无 `n_bins = _validate_n_bins(n_bins)` 调用
  - docstring L24 明确声称"供 calibration.py 内 6 处守卫...统一调用"
  - 功能等价：6 处内联守卫与 `_validate_n_bins` 逻辑完全相同，但 DRY 违反（7 处重复代码）

- **判定**：成立（严重，需修补）。功能等价故非致命，但 docstring 与实现矛盾 + DRY 违反 + 未来维护风险（改上界需改 7 处）。

---

### Attack-2: [中等] `run_e3_brier_dcr_ncv.py` 3 个 n_bins 函数无守卫，R6 终审遗漏

- **维度**：遗漏 / 隐含假设
- **位置**：`scripts/run_e3_brier_dcr_ncv.py` L169-181（`brier_parts_toplabel`）/ L184-204（`brier_parts_ovr`）/ L207-211（`ece_toplabel`）
- **描述**：
  R6 终审 L80-84 列出了 scripts 中 4 个无守卫的 n_bins 函数，R7 修复为这 4 个函数添加了守卫。但 **`run_e3_brier_dcr_ncv.py` 中还有 3 个接受 `n_bins` 参数的函数完全被遗漏**：
  - `brier_parts_toplabel` (L169): `n_bins: int = N_BINS` → 调用 `brier_parts(max_p, correct, n_bins=n_bins)` (L181)
  - `brier_parts_ovr` (L184): `n_bins: int = N_BINS` → 调用 `brier_parts(p_k, y_k, n_bins=n_bins)` (L199)
  - `ece_toplabel` (L207): `n_bins: int = N_BINS` → 调用 `ece(max_p, correct, n_bins=n_bins)` (L211)

  这 3 个函数本身没有守卫。虽然它们调用的 `brier_parts`/`ece` 有守卫（间接安全），但：
  1. 错误信息会指向 `brier_parts`/`ece` 而非 `brier_parts_toplabel`/`ece_toplabel`，调试困难
  2. 与 R7 修复的 4 个 scripts 函数不一致（它们都有守卫）
  3. R6 终审和 R7 修复都遗漏了这 3 个函数

- **证据**：
  - grep `def\s+\w+\(.*n_bins` 确认 `run_e3` 有 3 个函数接受 n_bins 参数
  - grep `_validate_n_bins` 确认 `run_e3` 无导入、无调用
  - `brier_parts_toplabel(n_bins=True)` → 调用 `brier_parts(n_bins=True)` → raise ValueError（间接安全，但错误信息指向 brier_parts）

- **判定**：成立（中等，需修补）。功能间接安全（下游守卫拦截），但错误信息不友好 + 与 R7 修复模式不一致。

---

### Attack-3: [中等] `compute_all_metrics` 测试未使用 BAD_N_BINS 常量，覆盖不完整

- **维度**：测试覆盖 / 一致性
- **位置**：`tests/test_model.py` L220-226
- **描述**：
  R7 修复将 `brier_parts` 测试（L217-219）和 `ece/mce/bootstrap_ece` 测试（L235-241）统一使用 `BAD_N_BINS` 常量（8 个非法值）。但 **`compute_all_metrics` 的守卫测试（L220-226）仍手动列出 3 个 case（0, -1, 1.5），没有使用 `BAD_N_BINS` 常量**：
  ```python
  # Test compute_all_metrics guard
  with pytest.raises(ValueError):
      compute_all_metrics(probs, labels, n_bins=0)
  with pytest.raises(ValueError):
      compute_all_metrics(probs, labels, n_bins=-1)
  with pytest.raises((ValueError, TypeError)):
      compute_all_metrics(probs, labels, n_bins=1.5)
  ```
  遗漏了 `None/True/"10"/2.0/10**18` 五个 case，与 `brier_parts` 和 `ece/mce/bootstrap_ece` 的测试覆盖不一致。

  特别注意 L225 使用 `pytest.raises((ValueError, TypeError))` 而非 `pytest.raises(ValueError)`，暗示对 `compute_all_metrics` 守卫行为不确定。实际上 `compute_all_metrics` L793 的守卫会 raise ValueError（与 `brier_parts` 一致），所以 `TypeError` 是多余的容错。

- **证据**：
  - L220-226 手动列出 3 个 case，而非 `for bad_n_bins in BAD_N_BINS:`
  - L217-219（brier_parts）和 L235-241（ece/mce/bootstrap_ece）均使用 `BAD_N_BINS` 循环
  - `compute_all_metrics` L793 守卫与 `brier_parts` L629 守卫代码完全相同，均 raise ValueError

- **判定**：成立（中等，需修补）。测试覆盖不一致 + `TypeError` 容错多余。

---

### Attack-4: [轾微] `plot_reliability_diagram` 有守卫但完全无测试

- **维度**：测试覆盖
- **位置**：`src/utils/calibration.py` L707-725（`plot_reliability_diagram` 守卫）vs `tests/test_model.py`（无对应测试）
- **描述**：
  `calibration.py` L725 的 `plot_reliability_diagram` 有 n_bins 守卫，但 `test_model.py` 中没有针对它的测试。`test_brier_parts_n_bins_validation`（L204-226）测试了 `brier_parts` 和 `compute_all_metrics`，`test_ece_mce_bootstrap_ece_n_bins_guards`（L228-245）测试了 `ece/mce/bootstrap_ece`，但 **`plot_reliability_diagram` 和 `mce` 的守卫测试不完整**（`mce` 在 L239 有测试，但 `plot_reliability_diagram` 完全无测试）。

- **证据**：
  - grep `plot_reliability_diagram` in test_model.py → 无结果
  - `plot_reliability_diagram` L725 有守卫代码

- **判定**：成立（轾微，可选改进）。守卫代码正确，但无测试保护。

---

### Attack-5: [轾微] `False` case 缺失

- **维度**：测试覆盖 / 边界失效
- **位置**：`tests/test_model.py` L19
- **描述**：
  `BAD_N_BINS = [0, -1, 1.5, None, True, "10", 2.0, 10**18]` 包含 `True` 但不包含 `False`。虽然 `isinstance(False, bool)` 也会返回 True（被守卫拦截），但测试没有显式验证 `False` case。

  `False` 是一个特殊边界值：`False + 1 = 1`（bool 穿透后 n_bins=1，静默工作），与 `True + 1 = 2` 类似。虽然守卫会拦截 `False`（`isinstance(False, bool)` → True），但测试应显式覆盖。

- **证据**：
  - `BAD_N_BINS` 列表中无 `False`
  - `isinstance(False, bool)` → True → 被守卫拦截（功能正确）

- **判定**：成立（轾微，可选改进）。功能正确，但测试覆盖不完整。

---

### Attack-6: [轾微] numpy float 类型（`np.float64`）缺失

- **维度**：测试覆盖 / 边界失效
- **位置**：`tests/test_model.py` L19
- **描述**：
  `BAD_N_BINS` 包含 Python float（`1.5`, `2.0`）但不包含 numpy float（`np.float64(10)`）。如果传入 `np.float64(10)`：
  - `isinstance(np.float64(10), bool)` → False
  - `isinstance(np.float64(10), (int, np.integer))` → False（`np.float64` 不是 `np.integer`）
  - `not isinstance(...)` → True → raise ValueError ✅

  守卫会正确拦截 `np.float64`，但测试没有验证这个 case。

- **证据**：
  - `BAD_N_BINS` 列表中无 `np.float64(10)`
  - `np.float64` 不是 `np.integer` 子类，会被 `not isinstance(n_bins, (int, np.integer))` 拦截

- **判定**：成立（轾微，可选改进）。功能正确，但测试覆盖不完整。

---

### Attack-7: [轾微] `_validate_n_bins` 的 `upper_bound` 参数未被任何调用方使用

- **维度**：副作用 / 语义偏移
- **位置**：`src/utils/calibration.py` L21
- **描述**：
  `_validate_n_bins` 接受 `upper_bound=10**4` 参数，但 4 个 scripts 函数都没有传入 `upper_bound`，都用默认值。calibration.py 内部 6 处守卫也没有使用 `_validate_n_bins`（见 Attack-1）。所以 **`upper_bound` 参数实际上是多余的**，没有任何调用方使用它。

  这不是 bug，但暗示 API 设计过度：参数存在但无消费者。如果未来需要不同上界，可以传入 `upper_bound`，但当前无此需求。

- **证据**：
  - grep 确认所有调用方都是 `_validate_n_bins(n_bins)`，无 `_validate_n_bins(n_bins, upper_bound=X)`
  - calibration.py 6 处内联守卫硬编码 `10**4`，未使用 `upper_bound` 参数

- **判定**：成立（轾微，可选改进）。API 设计过度，但无害。

---

### Attack-8: [轾微] R7 修复报告声称"7种非法输入"但实际 8 个值

- **维度**：自相矛盾 / 语义偏移
- **位置**：`docs/p0r7_fix_p0_4.md` L33 vs `tests/test_model.py` L19
- **描述**：
  R7 修复报告 L33 声称"测试常量BAD_N_BINS覆盖7种非法输入"，但实际 `BAD_N_BINS = [0, -1, 1.5, None, True, "10", 2.0, 10**18]` 有 **8 个值**。

  报告可能将 `1.5` 和 `2.0` 归为同一种"float"类型（7 种类型：零值/负数/float/None/bool/str/超大值），但列表有 8 个元素。措辞有歧义：是"7 种类型"还是"7 个值"？

- **证据**：
  - R7 修复报告 L33: "测试常量BAD_N_BINS覆盖7种非法输入"
  - test_model.py L19: `BAD_N_BINS = [0, -1, 1.5, None, True, "10", 2.0, 10**18]`（8 个元素）

- **判定**：成立（轾微，可选改进）。报告措辞与实现不一致，但功能正确。

---

## 攻击统计

| 严重度 | 数量 | 编号 |
|--------|------|------|
| 致命 | 0 | — |
| 严重 | 1 | Attack-1 |
| 中等 | 2 | Attack-2, Attack-3 |
| 轾微 | 5 | Attack-4, Attack-5, Attack-6, Attack-7, Attack-8 |
| 不成立 | 0 | — |
| **合计** | **8** | — |

---

## 7 维度攻击覆盖记录

| 维度 | 攻击点 | 结果 |
|------|--------|------|
| 1. 反例构造 | Attack-2（run_e3 遗漏）、Attack-5（False 缺失） | 找到 2 个 |
| 2. 逻辑断链 | Attack-1（docstring 声称统一调用但实际未调用） | 找到 1 个 |
| 3. 隐含假设 | Attack-2（假设 R6 终审列出了所有 scripts n_bins 函数）、Attack-7（假设 upper_bound 有消费者） | 找到 2 个 |
| 4. 边界失效 | Attack-5（False 边界）、Attack-6（np.float64 边界） | 找到 2 个 |
| 5. 自相矛盾 | Attack-1（docstring vs 实现）、Attack-8（报告 vs 实现） | 找到 2 个 |
| 6. 量级错误 | 上界 10**4 覆盖所有合理场景（N_BINS=5/10/15 均通过），未发现量级错误 | 未找到 |
| 7. 语义偏移 | Attack-7（upper_bound 语义）、Attack-8（"7种"语义） | 找到 2 个 |

**上界维度专项验证**：
- `N_BINS_TEMPERATURE = 5`（run_e2）→ 通过 ✅
- `N_BINS = 10`（run_e2/run_e6）→ 通过 ✅
- `N_BINS = 5`（run_e4）→ 通过 ✅
- `BRIER_N_BINS = 10`（run_e4）→ 通过 ✅
- 默认 `n_bins=10`（calibration.py）→ 通过 ✅
- 极端 `n_bins=1000` → 通过 ✅
- `n_bins=10**4` → 通过（上界） ✅
- `n_bins=10**4+1` → raise ValueError ✅
- 无合法场景需要 >10**4（典型 ECE n_bins=10-20，极端 n_bins=1000 已罕见）

**bool 穿透专项验证**：
- `True` → `isinstance(True, bool)` → True → raise ValueError ✅
- `False` → `isinstance(False, bool)` → True → raise ValueError ✅（但测试未覆盖，见 Attack-5）

**numpy 整数类型专项验证**：
- `np.int64(10)` → `isinstance(np.int64(10), (int, np.integer))` → True → 通过 ✅
- 测试 L214 显式验证 `brier_parts(probs, labels, n_bins=np.int64(10))` ✅

---

## 结论

R7 修复**成功消除了 R6 终审裁定的全部致命和严重缺陷**：
- ✅ scripts 4 个 n_bins 函数已添加守卫（R6 ATK-1 致命 → 清零）
- ✅ 上界从 10**6 降至 10**4（R6 ATK-2/4 严重 → 清零）
- ✅ brier_parts 测试扩充为 8 个值（R6 ATK-3 严重 → 清零）
- ✅ bool 穿透被拦截（True/False 均被 `isinstance(n_bins, bool)` 拦截）
- ✅ OOM 被拦截（10**18 > 10**4 → raise ValueError）
- ✅ numpy 整数类型通过（np.int64 被 `isinstance(n_bins, (int, np.integer))` 接受）

但 R7 修复**引入了 1 个严重一致性缺陷**（Attack-1：`_validate_n_bins` 定义但 calibration.py 内部 6 处守卫未调用，docstring 与实现矛盾）+ **2 个中等缺陷**（Attack-2：run_e3 遗漏 + Attack-3：compute_all_metrics 测试不完整）+ **5 个轾微缺陷**。

**致命缺陷：0 个**。R7 修复的核心目标（消除 scripts 无守卫 + 上界过大 + 测试不统一）已达成。

**建议 R8 修复**（按优先级排序）：
1. **Attack-1**（严重）：将 calibration.py 6 处内联守卫改为调用 `_validate_n_bins(n_bins)`，消除 DRY 违反 + docstring 与实现矛盾。改动量：6 处 × 2 行 = 12 行。
2. **Attack-2**（中等）：为 `run_e3` 的 3 个函数添加 `_validate_n_bins` 守卫，或在 docstring 中声明"间接安全，由下游守卫拦截"。改动量：3 处 × 2 行 = 6 行。
3. **Attack-3**（中等）：将 `compute_all_metrics` 测试改为 `for bad_n_bins in BAD_N_BINS:` 循环，移除多余的 `TypeError` 容错。改动量：4 行。

Attack-4/5/6/7/8 均为轾微可选改进，不阻塞收敛。

**收敛判定**：R7 修复在 P0-4 范围内**基本收敛**——致命和严重缺陷已清零，仅剩 1 个严重一致性缺陷（Attack-1）+ 2 个中等缺陷 + 5 个轾微缺陷。按收敛标准（致命/严重/中等清零），**需 R8 修补 Attack-1/2/3 后可宣布收敛**。
