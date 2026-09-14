# R7 反反方审查报告 — P0-4

## 审查概述

**审查角色**：反反方（公正审查者）。立场：既不偏袒修复方，也不偏袒攻击方，以源代码实证为唯一判据。

**审查对象**：`docs/p0r7_attack_p0_4.md` 中 8 个攻击点（1 严重 + 2 中等 + 5 轻微）。

**审查方法**：逐条阅读源代码（`src/utils/calibration.py` / `tests/test_model.py` / 3 个 scripts 文件 / R7 修复报告），核对反方指控的每一行号、每一段代码、每一处 grep 结果是否属实；再判定攻击的**事实成立性**与**严重度合理性**。

**审查结论**：8 个攻击点**全部事实成立**（反方指控的代码现状均经实证核对无误），但其中 2 个攻击的严重度评级偏高（Attack-2 由中等降为轻微、Attack-7 由轻微降为无害设计）。R7 修复**已基本收敛**——R6 终审裁定的全部致命与严重缺陷已清零，剩余缺陷中仅 Attack-1（DRY 一致性）值得 R8 修补，Attack-2/3 为可选改进，Attack-4~8 不阻塞收敛。

---

## 逐条判定

### Attack-1 [严重] `_validate_n_bins` 定义但 calibration.py 内部 6 处守卫未调用

**事实核对**：
- `src/utils/calibration.py` L21-40 确实定义了 `_validate_n_bins(n_bins, upper_bound=10**4)`。
- docstring L24 原文："供 calibration.py 内 6 处守卫与 scripts/ 中 4 个 n_bins 函数统一调用，避免守卫模式重复散布。"
- 6 处内联守卫经逐行核对确认存在且代码完全相同：
  | 行号 | 函数 | 守卫代码 |
  |------|------|----------|
  | L237 | `ece` | `if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1 or n_bins > 10**4:` |
  | L573 | `bootstrap_ece` | 同上 |
  | L629 | `brier_parts` | 同上 |
  | L682 | `mce` | 同上 |
  | L725 | `plot_reliability_diagram` | 同上 |
  | L793 | `compute_all_metrics` | 同上 |
- 6 处守卫均**未调用** `_validate_n_bins`，而是各自重复内联代码。
- scripts 4 个函数（`fit_binned_temperature` L166 / `quintile_edges` L190 / `compute_reliability_bins` L153 / `bootstrap_bin_accuracy_ci` L220）均正确调用了 `_validate_n_bins`。

**判定**：**成立（严重）**。反方指控完全属实：
1. **DRY 违反**：7 处重复同一守卫逻辑（1 处定义 + 6 处内联）。
2. **docstring 与实现矛盾**：docstring 声称"供 calibration.py 内 6 处守卫...统一调用"，但 6 处守卫实际未调用，文档撒谎。
3. **维护风险**：未来若需调整上界（如 10**4 → 10**5）或增加类型检查（如拒绝 np.float64），需同步修改 7 处，极易遗漏。
4. **功能等价**：6 处内联守卫与 `_validate_n_bins` 逻辑完全相同，故非致命缺陷——但严重度仍为"严重"，因为 docstring 谎言会误导后续审查者/维护者。

**修补方案**（R8 修复，12 行改动）：
将 6 处内联守卫替换为 `n_bins = _validate_n_bins(n_bins)` 调用。具体改动：

```python
# src/utils/calibration.py L237-238（ece 函数）
# 删除：
if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1 or n_bins > 10**4:
    raise ValueError(f"n_bins must be a positive integer in [1, 10000], got {n_bins!r}")
# 替换为：
n_bins = _validate_n_bins(n_bins)
```

对 L573（bootstrap_ece）、L629（brier_parts）、L682（mce）、L725（plot_reliability_diagram）、L793（compute_all_metrics）执行相同替换。

**注意**：替换后 `n_bins` 变为 Python int（`_validate_n_bins` 返回 `int(n_bins)`），下游 `np.linspace(0, 1, n_bins + 1)` 等调用行为不变（原本 np.integer 也被接受）。需回归测试确认无副作用。

---

### Attack-2 [中等→轻微] `run_e3_brier_dcr_ncv.py` 3 个 n_bins 函数无守卫

**事实核对**：
- `scripts/run_e3_brier_dcr_ncv.py` L125-127 导入语句：`from src.utils.calibration import (fit_temperature, apply_temperature, ece, brier_parts, brier_raw,)`——**未导入 `_validate_n_bins`**。
- 3 个接受 `n_bins` 参数的函数经核对确认存在且无直接守卫：
  | 行号 | 函数 | 签名 | 下游调用 |
  |------|------|------|----------|
  | L169-181 | `brier_parts_toplabel` | `n_bins: int = N_BINS` | `brier_parts(max_p, correct, n_bins=n_bins)` L181 |
  | L184-204 | `brier_parts_ovr` | `n_bins: int = N_BINS` | `brier_parts(p_k, y_k, n_bins=n_bins)` L199 |
  | L207-211 | `ece_toplabel` | `n_bins: int = N_BINS` | `ece(max_p, correct, n_bins=n_bins)` L211 |
- 下游 `brier_parts`（L629 守卫）和 `ece`（L237 守卫）均有守卫，故**间接安全**：传入非法 `n_bins` 会在下游 raise ValueError。

**判定**：**事实成立，但严重度由中等下调为轻微**。反方指控属实，但严重度评级偏高：
1. **功能安全**：3 个函数均通过下游守卫间接拦截非法 `n_bins`，无 bool 穿透、无 OOM 风险。反方报告 L69 也承认"功能间接安全"。
2. **错误信息指向问题**：反方称"错误信息会指向 `brier_parts`/`ece` 而非 `brier_parts_toplabel`/`ece_toplabel`，调试困难"。此指控**部分成立**——错误信息确实指向下游函数，但 traceback 会包含完整调用栈（`brier_parts_toplabel` L181 → `brier_parts` L629），调试并不困难，只需看 traceback 上一帧。
3. **一致性指控**：反方称"与 R7 修复的 4 个 scripts 函数不一致"。此指控**成立但轻微**——R7 修复的 4 个函数是**叶子函数**（直接构造分箱边界，无下游守卫可依赖），而 run_e3 的 3 个函数是**包装函数**（委托给有守卫的叶子函数），二者角色不同，守卫策略本可不同。
4. **R6 终审遗漏**：反方称"R6 终审和 R7 修复都遗漏了这 3 个函数"。此指控**成立**——R6 终审 L80-84 确实只列出 4 个叶子函数，未提及这 3 个包装函数。但 R6 终审的遗漏是**合理的**，因为这 3 个函数间接安全，不构成致命缺陷。

**修补方案**（可选改进，6 行改动）：
若为统一风格，可为 3 个函数添加守卫。在 L125-127 导入语句中添加 `_validate_n_bins`，并在 3 个函数体开头添加 `n_bins = _validate_n_bins(n_bins)`：

```python
# scripts/run_e3_brier_dcr_ncv.py L125-127
from src.utils.calibration import (  # noqa: E402
    fit_temperature, apply_temperature, ece, brier_parts, brier_raw,
    _validate_n_bins,  # R8：统一守卫风格
)

# L179（brier_parts_toplabel 函数体开头，在 max_p = ... 之前）
n_bins = _validate_n_bins(n_bins)

# L194（brier_parts_ovr 函数体开头，在 K = ... 之前）
n_bins = _validate_n_bins(n_bins)

# L209（ece_toplabel 函数体开头，在 max_p = ... 之前）
n_bins = _validate_n_bins(n_bins)
```

**反反方建议**：此攻击不阻塞收敛。若 R8 修复 Attack-1 时顺手修补此点即可，否则可永久挂起（间接安全已足够）。

---

### Attack-3 [中等] `compute_all_metrics` 测试未使用 BAD_N_BINS 常量

**事实核对**：
- `tests/test_model.py` L19：`BAD_N_BINS = [0, -1, 1.5, None, True, "10", 2.0, 10**18]`（8 个值）。
- L217-219（brier_parts 测试）：`for bad_n_bins in BAD_N_BINS: with pytest.raises(ValueError): brier_parts(...)`——使用循环。
- L235-241（ece/mce/bootstrap_ece 测试）：同样使用 `for bad_n_bins in BAD_N_BINS:` 循环。
- L220-226（compute_all_metrics 测试）：**手动列出 3 个 case**：
  ```python
  with pytest.raises(ValueError):
      compute_all_metrics(probs, labels, n_bins=0)
  with pytest.raises(ValueError):
      compute_all_metrics(probs, labels, n_bins=-1)
  with pytest.raises((ValueError, TypeError)):
      compute_all_metrics(probs, labels, n_bins=1.5)
  ```
  遗漏 `None/True/"10"/2.0/10**18` 五个 case。
- L225 使用 `pytest.raises((ValueError, TypeError))` 而非 `pytest.raises(ValueError)`。
- `compute_all_metrics` L793 守卫代码：`if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1 or n_bins > 10**4: raise ValueError(...)`——**只 raise ValueError，不 raise TypeError**。

**判定**：**成立（中等）**。反方指控完全属实：
1. **测试覆盖不一致**：brier_parts/ece/mce/bootstrap_ece 均用 8 值循环，compute_all_metrics 仅 3 值手动，遗漏 5 个 case。
2. **`TypeError` 容错多余**：`compute_all_metrics` 守卫只 raise ValueError，`pytest.raises((ValueError, TypeError))` 中的 TypeError 是死分支，暗示测试作者对守卫行为不确定——这是测试代码异味。
3. **严重度合理**：测试覆盖不完整属中等缺陷（不影响生产代码功能，但影响回归保护强度）。

**修补方案**（R8 修复，4 行改动）：
将 L220-226 替换为循环：

```python
# tests/test_model.py L220-226
# 删除 7 行手动 case，替换为：
for bad_n_bins in BAD_N_BINS:
    with pytest.raises(ValueError):
        compute_all_metrics(probs, labels, n_bins=bad_n_bins)
```

此改动同时消除 `TypeError` 容错（循环内只用 `pytest.raises(ValueError)`），与 brier_parts/ece 测试风格统一。

---

### Attack-4 [轻微] `plot_reliability_diagram` 有守卫但完全无测试

**事实核对**：
- `src/utils/calibration.py` L725：`plot_reliability_diagram` 确实有 n_bins 守卫。
- `tests/test_model.py` 中 grep `plot_reliability_diagram` → **无结果**，确认无测试。
- `test_brier_parts_n_bins_validation`（L204-226）测试 brier_parts + compute_all_metrics。
- `test_ece_mce_bootstrap_ece_n_bins_guards`（L228-245）测试 ece/mce/bootstrap_ece。
- **plot_reliability_diagram 完全无守卫测试**。

**判定**：**成立（轻微）**。反方指控属实：
1. 守卫代码正确（L725 与其他 5 处内联守卫代码完全相同）。
2. 但无测试保护，若未来有人误删守卫，测试不会失败。
3. 严重度轻微合理——plot_reliability_diagram 是可视化函数，非核心指标，且守卫代码与其他 5 处完全相同（若 Attack-1 修补为调用 `_validate_n_bins`，则守卫逻辑集中在一处，测试缺失风险进一步降低）。

**修补方案**（可选改进，5 行改动）：
在 `test_ece_mce_bootstrap_ece_n_bins_guards` 方法中追加 plot_reliability_diagram 测试，或新增独立测试方法：

```python
# tests/test_model.py，在 test_ece_mce_bootstrap_ece_n_bins_guards 之后新增
def test_plot_reliability_diagram_n_bins_guard(self):
    """plot_reliability_diagram 的 n_bins 守卫（补全 Attack-4 测试覆盖）"""
    from src.utils.calibration import plot_reliability_diagram
    probs = np.random.rand(50)
    labels = (np.random.rand(50) > 0.5).astype(float)
    for bad_n_bins in BAD_N_BINS:
        with pytest.raises(ValueError):
            plot_reliability_diagram(probs, labels, n_bins=bad_n_bins)
```

**反反方建议**：此攻击不阻塞收敛。若 R8 修补 Attack-1（6 处守卫统一调用 `_validate_n_bins`），则守卫逻辑集中在一处，plot_reliability_diagram 测试缺失的风险大幅降低，此点可永久挂起。

---

### Attack-5 [轻微] `False` case 缺失

**事实核对**：
- `tests/test_model.py` L19：`BAD_N_BINS = [0, -1, 1.5, None, True, "10", 2.0, 10**18]`——包含 `True`，**不包含 `False`**。
- 守卫代码 `isinstance(n_bins, bool)` 对 `False` 返回 True（`isinstance(False, bool) == True`），故 `False` 会被拦截。
- 功能正确，仅测试覆盖不完整。

**判定**：**事实成立，但严重度由轻微下调为无害**。反方指控属实但价值有限：
1. **功能正确**：`False` 会被 `isinstance(n_bins, bool)` 拦截，与 `True` 行为完全相同。
2. **测试覆盖论**：反方称"测试应显式覆盖 `False`"。此论点**理论上成立但实践价值极低**——`isinstance(True, bool)` 和 `isinstance(False, bool)` 走同一代码路径，测试 `True` 已覆盖该路径。增加 `False` case 是冗余测试，不提升缺陷发现概率。
3. **边界值论**：反方称"`False` 是特殊边界值：`False + 1 = 1`"。此论点**不成立**——守卫在 `False + 1` 之前就拦截了 `False`（`isinstance(False, bool)` → True → raise），`False + 1` 永远不会执行。反方此处构造的"边界场景"是不存在的。

**修补方案**（可选，1 行改动）：
若为追求测试覆盖的完备性，可在 BAD_N_BINS 中添加 `False`：

```python
# tests/test_model.py L19
BAD_N_BINS = [0, -1, 1.5, None, True, False, "10", 2.0, 10**18]
```

**反反方建议**：此攻击不阻塞收敛，可永久挂起。`True` 已覆盖 bool 路径，`False` 是冗余 case。

---

### Attack-6 [轻微] numpy float 类型（`np.float64`）缺失

**事实核对**：
- `BAD_N_BINS` 不包含 `np.float64(10)`。
- 守卫代码 `not isinstance(n_bins, (int, np.integer))` 对 `np.float64(10)` 返回 True（`np.float64` 不是 `np.integer` 子类），故 `np.float64(10)` 会被拦截。
- 功能正确，仅测试覆盖不完整。

**判定**：**事实成立（轻微）**。反方指控属实：
1. **功能正确**：`np.float64(10)` 会被 `not isinstance(n_bins, (int, np.integer))` 拦截。
2. **测试覆盖有价值**：与 Attack-5 不同，`np.float64` 走的代码路径（`not isinstance(...)` 分支）与 `True`（`isinstance(..., bool)` 分支）不同，增加此 case 有一定回归保护价值。
3. **但严重度轻微合理**：`np.float64` 不是 n_bins 的典型输入类型（用户通常传 Python int 或 np.int64），此 case 属防御性测试。

**修补方案**（可选，1 行改动）：

```python
# tests/test_model.py L19
BAD_N_BINS = [0, -1, 1.5, None, True, "10", 2.0, 10**18, np.float64(10)]
```

**反反方建议**：此攻击不阻塞收敛，可与 Attack-5 一并在 R8 修补时顺手添加。

---

### Attack-7 [轻微→无害] `_validate_n_bins` 的 `upper_bound` 参数未被任何调用方使用

**事实核对**：
- `src/utils/calibration.py` L21：`def _validate_n_bins(n_bins, upper_bound=10**4):`——确实有 `upper_bound` 参数。
- grep 所有调用方：`fit_binned_temperature` L166 / `quintile_edges` L190 / `compute_reliability_bins` L153 / `bootstrap_bin_accuracy_ci` L220——均为 `_validate_n_bins(n_bins)`，**无一处传入 `upper_bound`**。
- calibration.py 6 处内联守卫硬编码 `10**4`，未使用 `upper_bound` 参数。

**判定**：**事实成立，但严重度由轻微下调为无害设计**。反方指控属实但定性错误：
1. **不是缺陷，是合理的 API 设计**：`upper_bound` 作为带默认值的关键字参数，是 Python 中常见的"扩展点"设计模式。当前无消费者不代表参数无用——它为未来可能的差异化上界（如某些场景需要 `upper_bound=100`）预留了扩展能力，无需修改函数签名。
2. **反方指控"API 设计过度"**：此论点**不成立**。一个带默认值的可选参数，零运行时开销、零维护成本、提供扩展能力，是合理的防御性设计，非"过度设计"。
3. **若强行删除 `upper_bound` 参数**：反而会降低 API 灵活性，且未来若需差异化上界需修改函数签名（破坏向后兼容），代价更大。

**修补方案**：**不修补**。保留 `upper_bound` 参数。

**反反方建议**：此攻击应判定为**不成立（稻草人）**。反方将合理的扩展点设计误判为"API 设计过度"，属过度审查。建议在 R8 修复报告中明确声明"`upper_bound` 参数为预留扩展点，非缺陷"。

---

### Attack-8 [轻微] R7 修复报告声称"7种非法输入"但实际 8 个值

**事实核对**：
- `docs/p0r7_fix_p0_4.md` L33：`- [x] 测试常量BAD_N_BINS覆盖7种非法输入`——确实写"7种"。
- `tests/test_model.py` L19：`BAD_N_BINS = [0, -1, 1.5, None, True, "10", 2.0, 10**18]`——确实 8 个元素。

**判定**：**事实成立（轻微）**。反方指控属实：
1. **措辞歧义**：报告写"7种"，列表有 8 个元素。若"种"指**类型**（int/float/NoneType/bool/str = 5 种），则 7 也不对；若"种"指**非法类别**（零值/负数/非整数float/None/bool/str/整数float/超大值 = 8 类），则 7 也不对；若将 `1.5`（非整数 float）和 `2.0`（整数 float）归为同一类"float"，则 7 类。
2. **最可能解释**：报告作者将 `1.5` 和 `2.0` 归为同一类"float 非法输入"（一个非整数、一个整数但类型错误），故称"7种"。此解释合理但措辞不严谨。
3. **严重度轻微合理**：纯文档措辞问题，不影响代码功能。

**修补方案**（可选，1 行改动）：

```markdown
# docs/p0r7_fix_p0_4.md L33
- [x] 测试常量BAD_N_BINS覆盖8个非法输入值（7类：零值/负数/float/None/bool/str/超大值，其中float含1.5和2.0两个值）
```

**反反方建议**：此攻击不阻塞收敛，可在 R8 修复报告中顺手修正措辞。

---

## 判定汇总

| 攻击点 | 反方评级 | 事实成立 | 反反方评级 | 是否需 R8 修补 | 理由 |
|--------|----------|----------|------------|----------------|------|
| Attack-1 | 严重 | ✅ 成立 | 严重（维持） | **是** | DRY 违反 + docstring 谎言 + 维护风险 |
| Attack-2 | 中等 | ✅ 成立 | **轻微（下调）** | 可选 | 间接安全，错误信息 traceback 可追溯，包装函数与叶子函数角色不同 |
| Attack-3 | 中等 | ✅ 成立 | 中等（维持） | **是** | 测试覆盖不一致 + TypeError 死分支 |
| Attack-4 | 轻微 | ✅ 成立 | 轻微（维持） | 可选 | 守卫正确但无测试保护 |
| Attack-5 | 轻微 | ✅ 成立 | **无害（下调）** | 否 | True 已覆盖 bool 路径，False 冗余；反方构造的"False+1=1"场景不存在 |
| Attack-6 | 轻微 | ✅ 成立 | 轻微（维持） | 可选 | np.float64 走独立分支，有回归价值 |
| Attack-7 | 轻微 | ✅ 成立 | **无害（下调）** | 否 | upper_bound 是合理扩展点设计，非过度设计 |
| Attack-8 | 轻微 | ✅ 成立 | 轻微（维持） | 可选 | 纯文档措辞歧义 |

**统计**：
- 事实成立：8/8（反方指控的代码现状全部属实，反方工作扎实）
- 严重度需下调：3/8（Attack-2 中等→轻微、Attack-5 轻微→无害、Attack-7 轻微→无害）
- 需 R8 修补：2/8（Attack-1 严重、Attack-3 中等）
- 可选改进：4/8（Attack-2/4/6/8）
- 不需修补：2/8（Attack-5/7）

---

## 反反方对反方报告的整体评价

**反方工作质量**：**高**。
- 8 个攻击点的事实核对**全部属实**，无凭空捏造、无稻草人（除 Attack-7 的"API 设计过度"定性错误外）。
- 行号、代码片段、grep 结果均经实证核对无误。
- 7 维度攻击覆盖记录完整，逻辑清晰。
- 上界维度专项验证（10**4 边界）和 bool 穿透专项验证（True/False）严谨。

**反方严重度评级问题**：**部分偏高**。
- Attack-2 评级"中等"偏高：间接安全 + traceback 可追溯，应降为轻微。
- Attack-5 评级"轻微"偏高：True 已覆盖 bool 路径，False 冗余，应降为无害。
- Attack-7 评级"轻微"偏高：upper_bound 是合理扩展点，应降为无害（且反方定性为"API 设计过度"属误判）。

**反方收敛判定**：**基本合理但偏保守**。
- 反方建议"需 R8 修补 Attack-1/2/3 后可宣布收敛"。
- 反反方认为：**仅需 R8 修补 Attack-1（严重）和 Attack-3（中等）即可宣布收敛**。Attack-2 间接安全，可永久挂起；Attack-4~8 均为轻微或无害，不阻塞收敛。

---

## 收敛判定

### R7 修复核心目标达成情况

| R6 终审缺陷 | R7 修复状态 | 验证 |
|-------------|-------------|------|
| scripts 4 个 n_bins 函数无守卫（致命） | ✅ 已添加守卫 | 4 处 `_validate_n_bins` 调用经 grep 确认 |
| 上界 10**6 过大（严重） | ✅ 已降至 10**4 | L38/L237/L573/L629/L682/L725/L793 均为 `10**4` |
| brier_parts 测试不统一（严重） | ✅ 已统一为 BAD_N_BINS 循环 | L217-219 确认 |
| bool 穿透（致命） | ✅ 已拦截 | `isinstance(n_bins, bool)` 守卫确认 |
| OOM（致命） | ✅ 已拦截 | `n_bins > 10**4` 拦截 10**18 确认 |

**R6 终审裁定的全部致命和严重缺陷已清零。**

### R7 引入的新缺陷

| 缺陷 | 严重度 | 是否阻塞收敛 |
|------|--------|--------------|
| Attack-1：DRY 违反 + docstring 谎言 | 严重 | **是**（建议 R8 修补） |
| Attack-3：compute_all_metrics 测试不完整 | 中等 | **是**（建议 R8 修补） |
| Attack-2/4/6/8 | 轻微 | 否 |
| Attack-5/7 | 无害 | 否 |

### 最终收敛判定

**R7 修复在 P0-4 范围内基本收敛**：
- 致命缺陷：0 个 ✅
- 严重缺陷：1 个（Attack-1，DRY 一致性，非功能缺陷）⚠️
- 中等缺陷：1 个（Attack-3，测试覆盖）⚠️
- 轻微/无害缺陷：6 个

**建议 R8 修复**（按优先级排序）：
1. **Attack-1**（严重，12 行改动）：将 calibration.py 6 处内联守卫替换为 `n_bins = _validate_n_bins(n_bins)` 调用，消除 DRY 违反 + docstring 谎言。
2. **Attack-3**（中等，4 行改动）：将 compute_all_metrics 测试改为 `for bad_n_bins in BAD_N_BINS:` 循环，移除 TypeError 死分支。
3. **可选**：Attack-2（6 行）/ Attack-4（5 行）/ Attack-6（1 行）/ Attack-8（1 行）顺手修补。

**R8 修补 Attack-1 + Attack-3 后（共 16 行改动），R7 修复可宣布完全收敛**。Attack-2/4/5/6/7/8 均不阻塞收敛，可作为技术债长期跟踪。

---

## 附：反反方审查方法说明

本报告的"事实核对"环节均基于源代码逐行阅读，非依赖反方报告转述。具体核对方法：
1. **行号核对**：反方报告引用的每一行号（如 L237/L573/L629/L682/L725/L793）均经 `read` 工具读取确认。
2. **代码片段核对**：反方报告引用的代码片段（如 6 处内联守卫代码）均与源文件实际内容逐字符比对。
3. **grep 结果核对**：反方报告引用的 grep 结果（如"calibration.py 内无 `n_bins = _validate_n_bins(n_bins)` 调用"）均经 `grep` 工具独立执行确认。
4. **严重度独立评级**：反反方根据缺陷的实际影响（功能安全性 + 维护风险 + 测试覆盖价值）独立评级，不依赖反方评级。
5. **修补方案可行性**：每个修补方案均标注具体文件、行号、改动行数，并评估副作用（如 Attack-1 修补后 `n_bins` 类型从 np.integer 变为 int，需确认下游兼容）。
