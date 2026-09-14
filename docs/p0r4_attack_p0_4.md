# P0-4 R4轮反方攻击报告

> **反方挑刺代理 R4 交付**（任务 #113）。本报告对正方 P0-4 R4 轮修复（`src/utils/calibration.py` ece/mce/bootstrap_ece 函数体开头各添加 n_bins 验证守卫 + `tests/test_model.py` 增加 compute_all_metrics 守卫测试）进行全方位 7 维度攻击审查。
> **审查日期**：2026-09-09
> **审查代理**：反方挑刺代理（GLM-5.2）
> **攻击原则**：真诚攻击，逐行代码验证，构造具体反例，不臆测

---

## 1. R4修复内容确认

### 修复点1：src/utils/calibration.py ece/mce/bootstrap_ece 添加 n_bins 守卫

```python
# ece L215-216
def ece(probs, labels, n_bins: int = 10, adaptive: bool = False) -> float:
    """..."""
    if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
        raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
    probs = np.asarray(probs, dtype=float)
    ...

# mce L660-661
def mce(probs, labels, n_bins: int = 10) -> float:
    """..."""
    if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
        raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
    probs = np.asarray(probs, dtype=float)
    ...

# bootstrap_ece L551-552
def bootstrap_ece(probs, labels, n_bins: int = 10, ...):
    """..."""
    if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
        raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
    probs = np.asarray(probs, dtype=float)
    ...
```

**确认**：3 处守卫代码存在，位置均在函数体最前面（docstring 之后、probs/labels 转换之前），代码与 brier_parts L607-608 / compute_all_metrics L769-770 守卫完全一致。

### 修复点2：tests/test_model.py L216-222 增加 compute_all_metrics 守卫测试

```python
# tests/test_model.py L216-222（在 test_brier_parts_n_bins_validation 内）
# Test compute_all_metrics guard
with pytest.raises(ValueError):
    compute_all_metrics(probs, labels, n_bins=0)
with pytest.raises(ValueError):
    compute_all_metrics(probs, labels, n_bins=-1)
with pytest.raises((ValueError, TypeError)):
    compute_all_metrics(probs, labels, n_bins=1.5)
```

**确认**：测试代码存在，位于 test_brier_parts_n_bins_validation 函数末尾。

### 测试运行验证

```
$ python -m pytest tests/test_model.py::TestCalibration::test_brier_parts_n_bins_validation -v
tests/test_model.py::TestCalibration::test_brier_parts_n_bins_validation PASSED [100%]
============================== 1 passed in 4.49s ==============================
```

**确认**：测试能通过运行。

### 守卫一致性验证（实测）

```
=== ece/mce/bootstrap_ece 守卫验证（R4 修复）===
  ece(n_bins=0): ValueError OK
  ece(n_bins=-1): ValueError OK
  ece(n_bins=1.5): ValueError OK
  ece(n_bins='10'): ValueError OK
  ece(n_bins=None): ValueError OK
  mce(n_bins=0/-1/1.5/'10'/None): ValueError OK
  bootstrap_ece(n_bins=0/-1/1.5/'10'/None): ValueError OK
```

**确认**：R4 修复的 ece/mce/bootstrap_ece 守卫对 0/-1/1.5/"10"/None 均正确抛 ValueError。R3 攻击报告攻击8（ece/mce 无守卫）和攻击8扩展（异常类型不一致）**已被 R4 修复**。

---

## 2. 全维度攻击结果

### 攻击维度1：反例构造

#### A1（严重）：plot_reliability_diagram 无 n_bins 守卫——R4 修复范围仍不完整

**反例**（实测验证）：

```python
>>> from src.utils.calibration import plot_reliability_diagram
>>> import numpy as np
>>> probs = np.random.rand(100); labels = (np.random.rand(100) > 0.5).astype(float)
>>> plot_reliability_diagram(probs, labels, n_bins=0)     # 静默返回空图，无 ValueError!
>>> plot_reliability_diagram(probs, labels, n_bins=-1)    # 静默返回空图，无 ValueError!
>>> plot_reliability_diagram(probs, labels, n_bins=True)  # 静默返回（bool 穿透），无 ValueError!
>>> plot_reliability_diagram(probs, labels, n_bins=1.5)   # 抛 TypeError（非 ValueError！）
TypeError: 'float' object cannot be interpreted as an integer
>>> plot_reliability_diagram(probs, labels, n_bins="10")  # 抛 TypeError（非 ValueError！）
TypeError: can only concatenate str (not "int") to str
>>> plot_reliability_diagram(probs, labels, n_bins=None)  # 抛 TypeError（非 ValueError！）
TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'
```

**论证**：

- `plot_reliability_diagram`（calibration.py L685-747）接受 `n_bins: int = 10` 参数（L688），是**公开 API**：
  - `scripts/train.py` L40 `from src.utils.calibration import (..., plot_reliability_diagram, ...)` 直接 import
  - `scripts/train.py` L725 `fig = plot_reliability_diagram(max_probs_cal, correct_mask, ...)` 直接调用
- `plot_reliability_diagram` 函数体**无任何 n_bins 验证守卫**。L708 `bin_boundaries = np.linspace(0, 1, n_bins + 1)` 和 L713 `for i in range(n_bins):` 直接使用 n_bins。
- `n_bins=0` 时 `np.linspace(0, 1, 1)` 产生 `[0.0]`，`range(0)` 不执行循环，返回空图（bin_centers/bin_means/bin_counts 均为空列表）。
- `n_bins=-1` 时 `np.linspace(0, 1, 0)` 产生 `[]`，`range(-1)` 不执行，同样返回空图。
- `n_bins=1.5` 时 `range(1.5)` 抛 `TypeError: 'float' object cannot be interpreted as an integer`。
- **R4 修复目标**（R3 终审报告 L237）："ece/mce/bootstrap_ece 函数体开头各添加 n_bins 守卫"。但 R3 攻击报告攻击8 的核心是"所有接受 n_bins 的公开函数都应有守卫"，R4 只修复了 ece/mce/bootstrap_ece，**遗漏了 plot_reliability_diagram**。
- **行为不一致仍未彻底消除**：brier_parts/ece/mce/bootstrap_ece/compute_all_metrics 对非法 n_bins 统一抛 ValueError，但 plot_reliability_diagram 对 0/-1/True 静默返回，对 1.5/"10"/None 抛 TypeError。

**生产路径风险评估**：
- `train.py` L725 调用 `plot_reliability_diagram` 时**未传 n_bins**（使用默认值 10），生产路径安全。
- 但 `plot_reliability_diagram` 是公开 API，可被其他代码或未来开发直接调用传非法 n_bins。R4 修复的目的是"消除行为不一致"，但 plot_reliability_diagram 的行为不一致仍存在。

**严重程度**：**严重**。R4 修复范围仍不完整——R3 终审报告要求修复 ece/mce/bootstrap_ece，R4 执行了，但遗漏了同模块同性质的 plot_reliability_diagram。R3 攻击报告攻击8 的根本问题（"所有接受 n_bins 的公开函数都应有守卫"）仍未彻底解决。

---

### 攻击维度2：逻辑断链

#### A2（严重）：ece/mce/bootstrap_ece 守卫无直接测试覆盖——R4 修复了代码但未修复测试

**论证**（代码分析 + 实测验证）：

- 测试 `test_brier_parts_n_bins_validation`（L200-222）的函数体调用分析（自动提取）：
  ```
  调用的函数: ['astype', 'brier_parts', 'compute_all_metrics', 'int64', 'rand', 'test_brier_parts_n_bins_validation']
  直接调用 ece(): False
  直接调用 mce(): False
  直接调用 bootstrap_ece(): False
  直接调用 brier_parts(): True
  直接调用 compute_all_metrics(): True
  ```
- 测试**只直接调用 brier_parts（L206-215）和 compute_all_metrics（L217-222）**，**未直接调用 ece/mce/bootstrap_ece 传非法 n_bins**。
- R4 在 ece/mce/bootstrap_ece 添加了守卫，但**无任何测试直接验证这些守卫**。
- **反例**：删除 ece L215-216 守卫后，`ece(n_bins=0)` 静默返回 0.0（实测验证），但测试 `test_brier_parts_n_bins_validation` 仍通过——因为测试不直接调用 `ece(n_bins=0)`。compute_all_metrics 守卫（L769-770）会兜底拦截 `compute_all_metrics(n_bins=0)`，但**无法检测 ece 守卫是否被删除**。
- **R3 攻击报告攻击7 的核心问题（守卫无测试覆盖）在 R4 中从 compute_all_metrics 转移到 ece/mce/bootstrap_ece**：R4 修复了 compute_all_metrics 守卫测试（L217-222），但新增的 ece/mce/bootstrap_ece 守卫**无测试覆盖**。攻击点未被消除，只是转移。

**严重程度**：**严重**。R4 修复了 R3 攻击报告攻击8（代码层面），但未修复攻击7（测试层面）——新增的 ece/mce/bootstrap_ece 守卫无直接测试覆盖，无法防止回归。如果未来重构删除 ece 守卫，测试不会失败，直接调用 ece(n_bins=0) 会静默返回 0.0（伪"完美校准"）。

---

### 攻击维度3：隐含假设

#### A3（中等）：compute_all_metrics 守卫测试不完整——边界值覆盖不全

**论证**：

- R4 新增的 compute_all_metrics 守卫测试（L217-222）覆盖：
  - ✅ n_bins=0
  - ✅ n_bins=-1
  - ✅ n_bins=1.5（浮点数）
  - ❌ **n_bins="10"（字符串）未测试**
  - ❌ **n_bins=None 未测试**
  - ❌ **n_bins=True（bool）未测试**（bool 穿透，静默接受为 n_bins=1）
  - ❌ **n_bins=np.int64(10)（合法 numpy 整数）未测试**（应正常工作）
  - ❌ **n_bins=1（合法最小边界值）未测试**（应正常工作）
- R3 终审报告可选改进项 A4（"补充 n_bins=1 边界值测试和 n_bins=None 测试"）**未修复**。
- `n_bins="10"` 应触发 ValueError（`isinstance("10", (int, np.integer))` 为 False）。实测 `compute_all_metrics(n_bins="10")` 确实抛 ValueError，但测试未覆盖。
- `n_bins=None` 应触发 ValueError（`isinstance(None, (int, np.integer))` 为 False）。测试未覆盖。

**严重程度**：**中等**。边界值覆盖不全，核心路径（0/-1/1.5）已覆盖，但 "10"/None/True/np.int64/1 未覆盖。

---

### 攻击维度4：边界失效

#### A4（轻微）：bool 类型穿透守卫——n_bins=True 被当作 n_bins=1

**反例**（实测验证）：

```python
>>> ece(probs, labels, n_bins=True)        # 静默接受为 n_bins=1，返回 0.035388
0.035388
>>> mce(probs, labels, n_bins=True)        # 静默接受为 n_bins=1，返回 0.035388
0.035388
>>> brier_parts(probs, labels, n_bins=True)  # 静默接受为 n_bins=1，返回 (0.251152, ...)
(0.251152, ...)
>>> bootstrap_ece(probs, labels, n_bins=True, n_bootstrap=5)  # 静默接受
```

**论证**：

- Python 中 `bool` 是 `int` 的子类，`isinstance(True, int)` 返回 `True`，`True == 1`。
- 所有守卫 `if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:` 对 `n_bins=True`：`isinstance(True, (int, np.integer))` 为 True，`True < 1` 为 False（True == 1）→ 守卫通过，静默接受为 n_bins=1。
- `n_bins=False`：`isinstance(False, (int, np.integer))` 为 True，`False < 1` 为 True（False == 0）→ 守卫拦截，抛 ValueError。
- 这是 R3 终审报告可选改进项 A5（"排除 bool 类型（isinstance(n_bins, bool) 排除）"），R4 **未修复**。

**严重程度**：**轻微**。bool 作为 n_bins 是极端异常用法，实际影响极小。但 R3 已记录，R4 未修复。

---

### 攻击维度5：自相矛盾

#### A5（轻微）：测试 L221 `pytest.raises((ValueError, TypeError))` 语义模糊——异常类型未锁定

**论证**：

- 测试 L221 `with pytest.raises((ValueError, TypeError)):` 对 `compute_all_metrics(n_bins=1.5)` 使用了 `(ValueError, TypeError)` 元组。
- 实际行为：`compute_all_metrics` L769 `if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:` 对 `n_bins=1.5`：`isinstance(1.5, (int, np.integer))` 为 False → `not False` 为 True → 抛 **ValueError**。
- 测试用 `(ValueError, TypeError)` 元组**过度宽松**——它接受 TypeError，但实际只会抛 ValueError。
- **如果有人修改守卫**使其对浮点数抛 TypeError（例如改用 `int(n_bins)` 转换而非 isinstance 检查），测试仍通过——**测试无法锁定异常类型**。
- 这暗示测试作者对守卫行为**不确定**（不确定会抛 ValueError 还是 TypeError），因此用元组兜底。但 R4 修复后守卫行为已明确（isinstance 检查 → ValueError），测试应明确为 `pytest.raises(ValueError)`。

**严重程度**：**轻微**。测试当前能通过，但异常类型未锁定，无法防止守卫行为退化。

---

#### A6（轻微）：测试未验证 ValueError 错误消息内容

**论证**：

- 测试 L217-222 只验证异常类型（`pytest.raises(ValueError)`），未验证错误消息内容。
- 源代码 L770 `raise ValueError(f"n_bins must be a positive integer, got {n_bins}")` 包含 n_bins 实际值（用于调试）。
- 如果有人把错误消息改为 `raise ValueError("invalid n_bins")`（丢失实际值），测试不会失败。
- R3 攻击报告攻击6（"测试未验证 ValueError 错误消息包含 n_bins 实际值"）**未修复**。

**严重程度**：**轻微**。错误消息当前正确，测试未锁定。

---

### 攻击维度6：量级错误

#### A7（轻微）：bootstrap_ece 双重守卫冗余——bootstrap_ece 守卫后 ece 守卫永不触发

**论证**：

- `bootstrap_ece` L551-552 守卫验证 n_bins 合法。
- `bootstrap_ece` 内部 L560 `point = ece(probs, labels, n_bins)` 和 L581 `eces[b] = ece(probs[idx], labels[idx], n_bins)` 调用 `ece`，传已验证合法的 n_bins。
- `ece` L215-216 守卫对已验证合法的 n_bins **永不触发**（isinstance 检查和 n_bins < 1 检查均通过）。
- 这是**双重守卫冗余**——bootstrap_ece 守卫后，ece 守卫是死代码（在 bootstrap_ece 调用路径下）。
- 冗余守卫无害（额外一次 isinstance 检查，O(1) 开销，可忽略），但属于代码风格问题。

**严重程度**：**轻微**。冗余但无害，不影响正确性或性能。

---

### 攻击维度7：语义偏移

#### A8（轻微）：测试随机种子未固定——非确定性测试

**论证**：

- 测试 L203-204 `probs = np.random.rand(100); labels = (np.random.rand(100) > 0.5).astype(float)` 未固定随机种子。
- 断言 `b5 != b10`（L208）依赖随机数据使 n_bins=5 和 n_bins=10 产生不同结果。
- 实测 1000 个种子下 b5==b10 发生 0 次，概率极低。
- 但理论上存在数据使两者相等（如所有概率落在同一个 bin 内）。在 CI 环境中，如果 numpy 版本升级改变随机数生成算法，理论上可能触发。
- R3 攻击报告攻击4（"测试随机种子未固定"）**未修复**。

**严重程度**：**轻微**。理论非确定性，实际概率极低（<1/1000）。

---

## 3. 攻击点精化汇总

| 序号 | 攻击维度 | 攻击点 | 严重程度 | 代码证据 | 是否成立 |
|------|---------|--------|---------|---------|---------|
| 1 | 反例构造 | A1: plot_reliability_diagram 无 n_bins 守卫，n_bins=0/-1/True 静默返回，1.5/"10"/None 抛 TypeError | **严重** | calibration.py L685-747 无 isinstance 检查；train.py L40/L725 调用 | ✅ 成立（实测验证） |
| 2 | 逻辑断链 | A2: ece/mce/bootstrap_ece 守卫无直接测试覆盖，删除 ece 守卫后测试仍通过 | **严重** | test_model.py L200-222 只调用 brier_parts/compute_all_metrics，未调用 ece/mce/bootstrap_ece | ✅ 成立（代码分析+实测） |
| 3 | 隐含假设 | A3: compute_all_metrics 守卫测试不完整，缺 "10"/None/True/np.int64/1 边界值 | **中等** | test_model.py L217-222 只覆盖 0/-1/1.5 | ✅ 成立 |
| 4 | 边界失效 | A4: bool 类型穿透守卫，n_bins=True 被当作 n_bins=1 | **轻微** | calibration.py 所有守卫 isinstance(n_bins, (int, np.integer)) 不排除 bool | ✅ 成立（实测验证） |
| 5 | 自相矛盾 | A5: 测试 L221 pytest.raises((ValueError, TypeError)) 语义模糊，异常类型未锁定 | **轻微** | test_model.py L221 用元组而非 ValueError | ✅ 成立 |
| 6 | 自相矛盾 | A6: 测试未验证 ValueError 错误消息包含 n_bins 实际值 | **轻微** | test_model.py L217-222 只验证异常类型 | ✅ 成立 |
| 7 | 量级错误 | A7: bootstrap_ece 双重守卫冗余，ece 守卫在 bootstrap_ece 调用路径下永不触发 | **轻微** | calibration.py L551-552 + L560/L581 调用 ece | ✅ 成立（代码分析） |
| 8 | 语义偏移 | A8: 测试随机种子未固定，b5!=b10 非确定性 | **轻微** | test_model.py L203-204 np.random.rand(100) 无 seed | ✅ 成立（理论，实测 0/1000） |

---

## 4. 关键攻击点详细论证

### 4.1 A1（严重）：plot_reliability_diagram 无守卫——R4 修复范围仍不完整

**R3 终审报告 R4 必修项**（p0r3_final_verdict.md L237）：
> P0-严重 | A1 | src/utils/calibration.py | L214后（ece）/L548后（bootstrap_ece）/L655后（mce） | ece/mce/bootstrap_ece 函数体开头各添加 n_bins 守卫

**R4 修复执行**：在 ece L215-216 / mce L660-661 / bootstrap_ece L551-552 添加守卫。

**攻击**：R4 机械执行了 R3 终审报告的必修项（ece/mce/bootstrap_ece），但**遗漏了同模块同性质的 plot_reliability_diagram**。R3 攻击报告攻击8 的根本问题是"所有接受 n_bins 的公开函数都应有守卫"，R4 只修复了终审报告明确列出的 3 个函数，未主动检查同模块其他接受 n_bins 的函数。

**证据**：
- `plot_reliability_diagram`（calibration.py L685-747）接受 `n_bins: int = 10` 参数（L688）。
- `plot_reliability_diagram` 是公开 API：`scripts/train.py` L40 import，L725 调用。
- `plot_reliability_diagram` 函数体无 n_bins 守卫（L703-706 直接 `probs = np.asarray(probs); labels = np.asarray(labels)`，L708 `bin_boundaries = np.linspace(0, 1, n_bins + 1)` 直接使用 n_bins）。
- 实测：`plot_reliability_diagram(n_bins=0)` 静默返回空图，`plot_reliability_diagram(n_bins=1.5)` 抛 TypeError（非 ValueError）。

**修复建议**：在 `plot_reliability_diagram` 函数体开头添加同样的 n_bins 守卫：
```python
def plot_reliability_diagram(probs, labels, n_bins: int = 10, ...):
    """..."""
    if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
        raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
    import matplotlib.pyplot as plt
    ...
```

### 4.2 A2（严重）：ece/mce/bootstrap_ece 守卫无直接测试覆盖

**论证链条**：

1. R4 在 ece L215-216 / mce L660-661 / bootstrap_ece L551-552 添加守卫。
2. 测试 `test_brier_parts_n_bins_validation`（L200-222）只直接调用 `brier_parts`（L206-215）和 `compute_all_metrics`（L217-222）。
3. 测试**未直接调用 ece/mce/bootstrap_ece 传非法 n_bins**（代码分析确认）。
4. 如果删除 ece L215-216 守卫，`ece(n_bins=0)` 静默返回 0.0（实测验证），但测试仍通过——因为测试不直接调用 `ece(n_bins=0)`。
5. `compute_all_metrics` 守卫（L769-770）会兜底拦截 `compute_all_metrics(n_bins=0)`，但**无法检测 ece 守卫是否被删除**。
6. **R3 攻击报告攻击7 的核心问题（守卫无测试覆盖）在 R4 中从 compute_all_metrics 转移到 ece/mce/bootstrap_ece**：R4 修复了 compute_all_metrics 守卫测试（L217-222），但新增的 ece/mce/bootstrap_ece 守卫无测试覆盖。攻击点未被消除，只是转移。

**修复建议**：在 `test_brier_parts_n_bins_validation` 中增加 ece/mce/bootstrap_ece 守卫的直接测试：
```python
# Test ece/mce/bootstrap_ece guards
from src.utils.calibration import ece, mce, bootstrap_ece
for bad_n_bins in [0, -1, 1.5, "10", None]:
    with pytest.raises(ValueError):
        ece(probs, labels, n_bins=bad_n_bins)
    with pytest.raises(ValueError):
        mce(probs, labels, n_bins=bad_n_bins)
    with pytest.raises(ValueError):
        bootstrap_ece(probs, labels, n_bins=bad_n_bins, n_bootstrap=5)
```

---

## 5. 与R3终审报告R4修复要求的对比

| R3终审R4必修项（p0r3_final_verdict.md L237-238） | R4实际执行 | 是否达标 |
|------------------------------------------------|-----------|---------|
| **必修1**: ece/mce/bootstrap_ece 函数体开头各添加 n_bins 守卫 | ece L215-216 / mce L660-661 / bootstrap_ece L551-552 | ✅ 达标 |
| **必修1**: 守卫代码与 compute_all_metrics 一致 | 5 处守卫代码完全一致 | ✅ 达标 |
| **必修1**: 守卫在函数体最前面 | 均在 docstring 后、probs 转换前 | ✅ 达标 |
| **必修2**: compute_all_metrics 守卫测试 | test_model.py L217-222 | ✅ 达标（但不完整） |
| **隐含**: 消除所有接受 n_bins 的公开函数行为不一致（A1 根本问题） | plot_reliability_diagram 仍无守卫 | ❌ **未达标** |
| **隐含**: 新增守卫有测试覆盖（A2 核心问题） | ece/mce/bootstrap_ece 守卫无直接测试 | ❌ **未达标** |

---

## 6. 总体判定

### 6.1 R4修复是否收敛

**部分收敛但未完全收敛**。

- ✅ 修复点1（ece/mce/bootstrap_ece 守卫）：代码正确，位置正确，守卫一致。R3 攻击报告攻击8（ece/mce 无守卫）和攻击8扩展（异常类型不一致）**已被 R4 修复**。
- ✅ 修复点2（compute_all_metrics 守卫测试）：测试代码正确，能通过运行。R3 攻击报告攻击7（compute_all_metrics 守卫无测试）**已被 R4 修复**。
- ❌ **A1: plot_reliability_diagram 仍无守卫**——R4 修复范围仍不完整，遗漏了同模块同性质的 plot_reliability_diagram。行为不一致问题仍未彻底消除。
- ❌ **A2: ece/mce/bootstrap_ece 守卫无直接测试覆盖**——R4 修复了代码但未添加测试。R3 攻击报告攻击7 的核心问题（守卫无测试覆盖）从 compute_all_metrics 转移到 ece/mce/bootstrap_ece。
- ⚠️ **A3: compute_all_metrics 守卫测试不完整**——边界值覆盖不全（缺 "10"/None/True/np.int64/1）。

### 6.2 攻击点统计

| 严重程度 | 数量 | 攻击点 |
|---------|------|--------|
| 致命 | 0 | - |
| 严重 | 2 | A1(plot_reliability_diagram无守卫) + A2(ece/mce/bootstrap_ece守卫无测试覆盖) |
| 中等 | 1 | A3(compute_all_metrics守卫测试不完整) |
| 轻微 | 5 | A4(bool穿透) + A5(异常类型未锁定) + A6(错误消息未验证) + A7(双重守卫冗余) + A8(随机种子未固定) |
| **合计** | **8** | |

### 6.3 是否需要R5轮

**需要R5轮**，但修复量极小（约 10-15 行改动）。

R5 必修2项：
1. **[严重]** 在 `plot_reliability_diagram` 函数体开头添加 n_bins 守卫（2 行）。这是 A1 的彻底修复，消除行为不一致。
2. **[严重]** 在 `test_brier_parts_n_bins_validation` 中增加 ece/mce/bootstrap_ece 守卫的直接测试（约 6-8 行）。这消除 A2 的测试覆盖空白。

R5 建议项（可选）：
3. **[中等]** 补充 compute_all_metrics 守卫测试的边界值（"10"/None/True/np.int64/1，约 3-4 行）。
4. **[轻微]** 排除 bool 类型（`isinstance(n_bins, bool)` 排除，所有守卫各加 1 行）。
5. **[轻微]** 测试 L221 `pytest.raises((ValueError, TypeError))` 改为 `pytest.raises(ValueError)`。
6. **[轻微]** 测试验证 ValueError 错误消息内容。
7. **[轻微]** 测试固定随机种子。

---

## 7. 对抗透明性声明

- 本报告所有攻击点均经代码实测验证（read 工具读取源代码 + python 脚本运行验证），无臆测。
- A1 的反例通过实际运行 `plot_reliability_diagram(n_bins=0/-1/1.5/"10"/None/True)` 确认。
- A2 通过代码分析（自动提取测试函数体调用列表）+ 实测（模拟删除 ece 守卫后 ece_no_guard(n_bins=0) 静默返回 0.0）确认。
- A4 的 bool 穿透通过实际运行 `ece/mce/brier_parts(n_bins=True)` 确认。
- 测试运行确认 `test_brier_parts_n_bins_validation` 能通过（1 passed in 4.49s）。
- 守卫一致性验证：ece/mce/bootstrap_ece 对 0/-1/1.5/"10"/None 均正确抛 ValueError（R4 修复有效）。
- 本报告未发现致命攻击点——R4 修复的代码本身是正确的，问题在于修复范围仍不完整（plot_reliability_diagram 未覆盖）和测试覆盖不完整（ece/mce/bootstrap_ece 守卫未测试）。

---

## 8. 结论

R4 轮修复**部分达成目标**：R3 终审报告的 2 个必修项（ece/mce/bootstrap_ece 守卫 + compute_all_metrics 守卫测试）均已执行，代码正确，测试能通过运行。R3 攻击报告的攻击8（ece/mce 无守卫）和攻击8扩展（异常类型不一致）**已被 R4 修复**。

但存在 2 个严重攻击点：

1. **plot_reliability_diagram 仍无 n_bins 守卫**——R4 修复范围仍不完整，遗漏了同模块同性质的 plot_reliability_diagram（公开 API，train.py L725 调用）。n_bins=0/-1/True 静默返回空图，1.5/"10"/None 抛 TypeError。行为不一致问题仍未彻底消除。
2. **ece/mce/bootstrap_ece 守卫无直接测试覆盖**——R4 修复了代码但未添加测试。R3 攻击报告攻击7 的核心问题（守卫无测试覆盖）从 compute_all_metrics 转移到 ece/mce/bootstrap_ece。删除 ece 守卫后测试仍通过，无法防止回归。

**建议R5轮修复**：在 plot_reliability_diagram 添加 n_bins 守卫（2 行）+ 补充 ece/mce/bootstrap_ece 守卫直接测试（6-8 行），共约 10 行改动。

**最终判定**：P0-4 R4 轮修复**需 R5 轮修复**。
