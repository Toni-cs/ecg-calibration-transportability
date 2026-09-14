# P0-4 R3轮反方攻击报告

> **反方挑刺代理 R3 交付**（任务 #99）。本报告对正方 P0-4 R3 轮修复（`tests/test_model.py` 新增 `test_brier_parts_n_bins_validation` + `src/utils/calibration.py` `compute_all_metrics` 入口添加 n_bins 验证守卫）进行全方位 7 维度攻击审查。
> **审查日期**：2026-09-09
> **审查代理**：反方挑刺代理（GLM-5.2）
> **攻击原则**：真诚攻击，逐行代码验证，构造具体反例，不臆测

---

## 1. R3修复内容确认

### 修复点1：tests/test_model.py L200-215 新增 test_brier_parts_n_bins_validation

```python
# tests/test_model.py L200-215
def test_brier_parts_n_bins_validation(self):
    """测试 brier_parts 的 n_bins 参数验证和生效"""
    from src.utils.calibration import brier_parts
    probs = np.random.rand(100)
    labels = (np.random.rand(100) > 0.5).astype(float)
    # 直接测试 n_bins 参数生效
    b5 = brier_parts(probs, labels, n_bins=5)
    b10 = brier_parts(probs, labels, n_bins=10)
    assert b5 != b10, "n_bins=5 和 n_bins=10 应产生不同结果"
    # 测试 numpy 整数类型
    b_np = brier_parts(probs, labels, n_bins=np.int64(10))
    assert b_np == b10, "numpy int64 应与 Python int 等价"
    # 测试 ValueError 守卫
    for bad_n_bins in [0, -1, 1.5, "10"]:
        with pytest.raises(ValueError):
            brier_parts(probs, labels, n_bins=bad_n_bins)
```

**确认**：代码存在，与 R2 终审报告 R3 修复建议一致。

### 修复点2：src/utils/calibration.py L763-764 compute_all_metrics 入口守卫

```python
# src/utils/calibration.py L744-766
def compute_all_metrics(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
    n_bootstrap: int = 1000
) -> dict:
    """..."""
    if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:          # L763
        raise ValueError(f"n_bins must be a positive integer, got {n_bins}")  # L764
    probs = np.asarray(probs)
    labels = np.asarray(labels)
```

**确认**：代码存在，位于函数体最前面（docstring 之后、probs/labels 转换之前），位置正确。

### 测试运行验证

```
$ python -m pytest tests/test_model.py::TestCalibration::test_brier_parts_n_bins_validation -v
tests/test_model.py::TestCalibration::test_brier_parts_n_bins_validation PASSED [100%]
============================== 1 passed in 5.22s ==============================
```

**确认**：测试能通过运行。

---

## 2. 全维度攻击结果

### 攻击维度1：反例构造

#### 攻击8（严重）：ece/mce/bootstrap_ece 无 n_bins 守卫——直接调用静默返回错误结果

**反例**：

```python
>>> from src.utils.calibration import ece, mce, bootstrap_ece
>>> import numpy as np
>>> probs = np.random.rand(100); labels = (np.random.rand(100) > 0.5).astype(float)
>>> ece(probs, labels, n_bins=0)     # 静默返回 0.0，无 ValueError!
0.0
>>> ece(probs, labels, n_bins=-1)    # 静默返回 0.0，无 ValueError!
0.0
>>> mce(probs, labels, n_bins=0)     # 静默返回 0.0，无 ValueError!
0.0
>>> mce(probs, labels, n_bins=-1)    # 静默返回 0.0，无 ValueError!
0.0
>>> bootstrap_ece(probs, labels, n_bins=0, n_bootstrap=5)   # 静默返回 (0.0, 0.0, 0.0)
(0.0, 0.0, 0.0)
```

**论证**：

- `ece` 函数（calibration.py L199-243）**无任何 n_bins 验证守卫**。`n_bins=0` 时 `np.linspace(0, 1, 1)` 产生 `[0.0]`，`for i in range(0)` 不执行循环体，`ece_val` 保持 0.0 返回。`n_bins=-1` 时 `np.linspace(0, 1, 0)` 产生 `[]`，`for i in range(-1)` 不执行，同样返回 0.0。
- `mce` 函数（calibration.py L643-676）**无任何 n_bins 验证守卫**，同理会静默返回 0.0。
- `bootstrap_ece` 函数（calibration.py L520-583）**无任何 n_bins 验证守卫**，内部调用 `ece(probs, labels, n_bins)`，ece 静默返回 0.0 导致 bootstrap 也返回 0.0。
- R2 终审报告明确指出 N2-r2 攻击点："ece/mce无n_bins守卫导致行为不一致"。R3 修复建议是在 `compute_all_metrics` 入口添加守卫。**但 R3 修复只在 compute_all_metrics 入口加了守卫，ece/mce/bootstrap_ece 作为公开 API 仍无守卫**。
- 测试文件 L15 `from src.utils.calibration import ece, bootstrap_ece, compute_all_metrics, ...` 和 L179 `val = ece(probs, labels, n_bins=5)` 证明 ece 是公开 API，可被直接调用。
- scripts/run_e2_ablation_discrimination.py L323 `ece(max_prob, correct, n_bins=N_BINS)` 和 scripts/run_e3_brier_dcr_ncv.py L211 `ece(max_p, correct, n_bins=n_bins)` 证明生产代码直接调用 ece。

**严重程度**：**严重**。R3 修复声称消除"ece/mce 与 brier_parts 行为不一致"，但实际只保护了经 compute_all_metrics 的路径。直接调用 ece/mce 传非法 n_bins 仍静默返回错误结果（0.0），而 brier_parts 抛 ValueError——**行为不一致仍未消除**。R2 终审报告 N2-r2 攻击点未被彻底修复。

---

#### 攻击8扩展（严重）：异常类型不一致——brier_parts 抛 ValueError，ece 抛 TypeError

**反例**：

```python
>>> brier_parts(probs, labels, n_bins=1.5)   # 抛 ValueError
ValueError: n_bins must be a positive integer, got 1.5
>>> ece(probs, labels, n_bins=1.5)           # 抛 TypeError（不是 ValueError！）
TypeError: 'float' object cannot be interpreted as an integer
```

**论证**：

- `brier_parts` L603 `if not isinstance(n_bins, (int, np.integer)) or n_bins < 1: raise ValueError(...)` 对浮点数 n_bins 抛 ValueError。
- `ece` 无守卫，浮点数 n_bins 传给 `np.linspace(0, 1, n_bins + 1)`（L225）和 `range(n_bins)`（L229）。`range(1.5)` 在 Python 3 中抛 `TypeError: 'float' object cannot be interpreted as an integer`。
- **R3 修复的目标是消除 ece/mce 与 brier_parts 的行为不一致**（R2 终审报告 N2-r2）。但修复后，对浮点数 n_bins，brier_parts 抛 ValueError 而 ece 抛 TypeError——**异常类型仍不一致**。调用方如果 `try: ... except ValueError:` 捕获，对 ece 的调用会漏捕 TypeError。

**严重程度**：**严重**。R3 修复的核心目标（行为一致性）未达成。

---

### 攻击维度2：逻辑断链

#### 攻击7（严重）：compute_all_metrics 入口守卫无直接测试覆盖

**论证**：

- 测试 `test_brier_parts_n_bins_validation`（L200-215）只调用 `brier_parts`，**未调用 `compute_all_metrics`**。
- R3 修复点2是在 `compute_all_metrics` L763-764 添加入口守卫。但该守卫**无任何测试直接验证**。
- 如果有人删除 `compute_all_metrics` L763-764 的守卫，测试仍会通过——因为 `compute_all_metrics` 内部 L772 调用 `brier_parts(probs, labels, n_bins=n_bins)`，`brier_parts` L603-604 的内部守卫会兜底抛 ValueError。
- **这意味着 R3 修复点2的守卫是冗余的**（被 brier_parts 内部守卫覆盖），且其存在与否无法被测试检测。R3 修复点2要么是冗余代码（brier_parts 内部守卫已足够），要么需要独立测试证明其在 brier_parts 调用前就拦截。

**反例**：删除 calibration.py L763-764 后运行测试：

```python
# 假设删除 L763-764：
# if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
#     raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
# 测试 test_brier_parts_n_bins_validation 仍通过（brier_parts 内部守卫兜底）
# 但 compute_all_metrics(n_bins=0) 的错误消息会变成 brier_parts 的消息，
# 且 ece/mce 在 brier_parts 调用前已执行（L769 bootstrap_ece），产生无意义计算
```

**严重程度**：**严重**。R3 修复点2缺乏测试覆盖，无法防止回归。且守卫位置在 `bootstrap_ece` 调用（L769）之前是正确的，但测试未验证这个位置优势。

---

### 攻击维度3：隐含假设

#### 攻击1/2（中等）：测试缺少 n_bins=1 边界值和 n_bins=None 覆盖

**论证**：

- 任务要求明确列出应测试：正常 n_bins、n_bins=1、n_bins=0、n_bins=-1、n_bins=None、n_bins=浮点数、n_bins=np.int64。
- 实际测试覆盖：
  - ✅ 正常 n_bins（5, 10）
  - ✅ n_bins=0
  - ✅ n_bins=-1
  - ✅ n_bins=浮点数（1.5）
  - ✅ n_bins=np.int64
  - ✅ n_bins=字符串（"10"）
  - ❌ **n_bins=1 未测试**（合法最小边界值）
  - ❌ **n_bins=None 未测试**
  - ❌ **n_bins=np.int32 未测试**（只测了 np.int64）
- `n_bins=1` 是合法边界值（`isinstance(1, int)` 且 `1 >= 1`），应验证其正常工作而非崩溃。
- `n_bins=None` 应触发 ValueError（`isinstance(None, (int, np.integer))` 为 False）。实际验证 `brier_parts(n_bins=None)` 确实抛 ValueError，但测试未覆盖。

**严重程度**：**中等**。边界值覆盖不全，但核心路径已覆盖。

---

### 攻击维度4：边界失效

#### 攻击11（轻微）：bool 类型穿透守卫

**反例**：

```python
>>> brier_parts(probs, labels, n_bins=True)   # 静默接受，被当作 n_bins=1
(0.251486, ...)
>>> compute_all_metrics(probs, labels, n_bins=True, n_bootstrap=5)  # 静默接受
{'ece': 0.039819, ...}
>>> brier_parts(probs, labels, n_bins=False)  # 抛 ValueError（False == 0 < 1）
ValueError: n_bins must be a positive integer, got False
```

**论证**：

- Python 中 `bool` 是 `int` 的子类，`isinstance(True, int)` 返回 `True`，`True == 1`。
- `brier_parts(n_bins=True)` 通过 L603 的 `isinstance` 检查和 `n_bins < 1` 检查（`True < 1` 为 `False`），静默接受为 n_bins=1。
- `compute_all_metrics(n_bins=True)` 同样穿透 L763 守卫。
- 这是 R2 终审报告已记录的 N3-r2 攻击点（P0-轻微），R3 未修复。

**严重程度**：**轻微**。bool 作为 n_bins 是极端异常用法，实际影响极小。

---

#### 攻击4（轻微）：测试随机种子未固定——非确定性测试

**论证**：

- 测试 L203-204 `probs = np.random.rand(100); labels = (np.random.rand(100) > 0.5).astype(float)` 未固定随机种子。
- 断言 `b5 != b10`（L208）依赖随机数据使 n_bins=5 和 n_bins=10 产生不同结果。
- 实测 1000 个种子下 b5==b10 发生 0 次（元组完全相等），概率极低。
- 但理论上存在数据使两者相等（如所有概率落在同一个 bin 内，或数据极度均匀）。在 CI 环境中，如果 numpy 版本升级改变随机数生成算法，种子序列变化，理论上可能触发。
- **更实质的问题**：`b5 != b10` 比较的是整个 4 元组 `(brier_total, reliability, resolution, uncertainty)`。即使 brier_total 恰好相同，reliability/resolution 也几乎必然不同。所以这个断言实际上比比较标量更稳健。

**严重程度**：**轻微**。理论非确定性，实际概率极低（<1/1000）。

---

### 攻击维度5：自相矛盾

#### 攻击6（轻微）：测试未验证 ValueError 错误消息内容

**论证**：

- 测试 L213-215 `with pytest.raises(ValueError): brier_parts(probs, labels, n_bins=bad_n_bins)` 只验证异常类型，未验证错误消息。
- 源代码 L604 `raise ValueError(f"n_bins must be a positive integer, got {n_bins}")` 确实包含 n_bins 实际值（用于调试）。
- 但测试未验证这一点。如果有人把错误消息改为 `raise ValueError("invalid n_bins")`（丢失实际值），测试不会失败。
- 任务要求第(5)点："ValueError的错误消息是否清晰？是否包含n_bins的实际值用于调试？"——源代码做到了，但测试未验证。

**严重程度**：**轻微**。错误消息当前正确，测试未锁定。

---

### 攻击维度6：量级错误

本维度未发现可攻击点。测试和数据量级合理（100 个样本，n_bins=5/10），无复杂度/收敛性/稳定性问题。

---

### 攻击维度7：语义偏移

#### 攻击13（轻微）：函数内 import 风格不一致

**论证**：

- 测试 L202 `from src.utils.calibration import brier_parts` 是函数内 import。
- 测试文件顶部 L15 `from src.utils.calibration import ece, bootstrap_ece, compute_all_metrics, fit_temperature, apply_temperature` 已 import 了其他校准函数，但未 import `brier_parts`。
- 这不是缺陷（函数内 import 合法），但风格不一致——同一模块的函数，有的在顶部 import，有的在函数内 import。

**严重程度**：**轻微**。风格问题，无功能影响。

---

#### 攻击14（轻微）：类型注解与运行时检查范围不一致

**论证**：

- 所有函数的 n_bins 类型注解均为 `int`（L199, L586, L643, L747）。
- `brier_parts` 和 `compute_all_metrics` 运行时通过 `isinstance(n_bins, (int, np.integer))` 接受 numpy 整数类型。
- `ece`/`mce` 运行时也隐式接受 numpy 整数（传给 `range()` 和 `np.linspace()`，numpy 整数会被转换），但无运行时验证。
- 类型注解 `int` 不包含 `np.integer`，静态类型检查器（mypy/pyright）会报错，但运行时正常。
- R2 终审报告已记录为 N4-r2（P0-轻微），R3 未修复。

**严重程度**：**轻微**。类型注解与运行时行为不一致，但无运行时 bug。

---

## 3. 攻击点精化汇总

| 序号 | 攻击维度 | 攻击点 | 严重程度 | 代码证据 | 是否成立 |
|------|---------|--------|---------|---------|---------|
| 1 | 反例构造 | 攻击8: ece/mce/bootstrap_ece 无 n_bins 守卫，直接调用静默返回 0.0 | **严重** | calibration.py L199-243(ece) L643-676(mce) L520-583(bootstrap_ece) 均无 isinstance 检查 | ✅ 成立（实测验证） |
| 2 | 反例构造 | 攻击8扩展: brier_parts(n_bins=1.5) 抛 ValueError，ece(n_bins=1.5) 抛 TypeError，异常类型不一致 | **严重** | calibration.py L603 vs L229 `range(n_bins)` | ✅ 成立（实测验证） |
| 3 | 逻辑断链 | 攻击7: compute_all_metrics 入口守卫无直接测试覆盖，删除后测试仍通过 | **严重** | test_model.py L200-215 只调用 brier_parts，未调用 compute_all_metrics | ✅ 成立（代码分析） |
| 4 | 隐含假设 | 攻击1/2: 测试缺少 n_bins=1 边界值和 n_bins=None 覆盖 | **中等** | test_model.py L213 `for bad_n_bins in [0, -1, 1.5, "10"]` 缺少 1 和 None | ✅ 成立 |
| 5 | 边界失效 | 攻击11: bool 类型穿透守卫，n_bins=True 被当作 n_bins=1 | **轻微** | calibration.py L603 `isinstance(n_bins, (int, np.integer))` 不排除 bool | ✅ 成立（实测验证） |
| 6 | 边界失效 | 攻击4: 测试随机种子未固定，b5!=b10 非确定性 | **轻微** | test_model.py L203-204 `np.random.rand(100)` 无 seed | ✅ 成立（理论，实测 0/1000） |
| 7 | 自相矛盾 | 攻击6: 测试未验证 ValueError 错误消息包含 n_bins 实际值 | **轻微** | test_model.py L214 `pytest.raises(ValueError)` 未检查消息 | ✅ 成立 |
| 8 | 语义偏移 | 攻击13: 函数内 import brier_parts 风格不一致 | **轻微** | test_model.py L202 vs L15 | ✅ 成立 |
| 9 | 语义偏移 | 攻击14: 类型注解 int 与运行时接受 np.integer 不一致 | **轻微** | calibration.py L199/L586/L643/L747 注解均为 int | ✅ 成立 |
| 10 | 量级错误 | （未发现可攻击点） | - | - | ❌ 未发现 |

---

## 4. 关键攻击点详细论证

### 4.1 攻击8（严重）：R3 修复未彻底解决 N2-r2——ece/mce 仍无守卫

**R2 终审报告 N2-r2 原文**（p0r2_final_verdict.md L243）：
> ece/mce无n_bins守卫导致行为不一致 | src/utils/calibration.py | L763后 | compute_all_metrics入口处统一添加n_bins验证守卫

**R3 修复执行**：在 compute_all_metrics L763-764 添加守卫。

**攻击**：R3 修复建议本身不完整——只在 compute_all_metrics 入口加守卫，未在 ece/mce/bootstrap_ece 内部加守卫。正方机械执行了建议但未彻底修复根本问题。

**证据**：
- `ece` 是公开 API（test_model.py L15 import，L179 直接调用；run_e2 L323 直接调用；run_e3 L211 直接调用）。
- `mce` 是公开 API（calibration.py L643 `def mce(...)`，被 compute_all_metrics L775 调用，也可被直接调用）。
- `bootstrap_ece` 是公开 API（test_model.py L15 import，L185 直接调用）。
- 直接调用 `ece(n_bins=0)` 静默返回 0.0——**行为不一致仍未消除**：brier_parts 抛 ValueError，ece 静默返回。

**修复建议**：在 ece/mce/bootstrap_ece 函数体开头各添加同样的 n_bins 守卫：
```python
def ece(probs, labels, n_bins: int = 10, adaptive: bool = False) -> float:
    if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
        raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
    ...

def mce(probs, labels, n_bins: int = 10) -> float:
    if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
        raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
    ...

def bootstrap_ece(probs, labels, n_bins: int = 10, ...):
    if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
        raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
    ...
```

### 4.2 攻击7（严重）：compute_all_metrics 守卫无测试覆盖

**论证链条**：

1. R3 修复点2在 compute_all_metrics L763-764 添加守卫。
2. 测试 test_brier_parts_n_bins_validation 只测试 brier_parts，未测试 compute_all_metrics。
3. compute_all_metrics 内部 L772 调用 `brier_parts(probs, labels, n_bins=n_bins)`，brier_parts L603-604 有内部守卫。
4. 如果删除 compute_all_metrics L763-764，非法 n_bins 会在 L769 `bootstrap_ece(probs, labels, n_bins, n_bootstrap)` 时静默通过（bootstrap_ece 无守卫），然后在 L772 `brier_parts` 时抛 ValueError。
5. **但此时 ece/mce 已经在 L769 执行了无意义的计算**（bootstrap_ece 内部循环调用 ece），浪费计算资源且产生无意义中间结果。compute_all_metrics 入口守卫的价值在于"提前拦截，避免无意义计算"——但测试未验证这个价值。

**修复建议**：在 test_brier_parts_n_bins_validation 中增加 compute_all_metrics 守卫测试：
```python
# 测试 compute_all_metrics 入口守卫
for bad_n_bins in [0, -1, 1.5, "10", None]:
    with pytest.raises(ValueError):
        compute_all_metrics(probs, labels, n_bins=bad_n_bins, n_bootstrap=5)
```

---

## 5. 与R2终审报告R3修复要求的对比

| R3修复要求（p0r2_final_verdict.md L252-285） | R3实际执行 | 是否达标 |
|---------------------------------------------|-----------|---------|
| **必修1**: test_brier_parts_n_bins_validation 测试 n_bins 生效 | L206-208 `b5 != b10` | ✅ 达标 |
| **必修1**: 测试 numpy 整数类型 | L210-211 `np.int64(10)` | ✅ 达标（但缺 np.int32） |
| **必修1**: 测试 ValueError 守卫 (0, -1, 1.5, "10") | L213-215 | ✅ 达标 |
| **必修2**: compute_all_metrics 入口 n_bins 守卫 | L763-764 | ✅ 达标 |
| **必修2**: 守卫在函数体最前面 | L763（docstring 后、probs 转换前） | ✅ 达标 |
| **隐含**: 消除 ece/mce 与 brier_parts 行为不一致（N2-r2） | ece/mce 仍无守卫 | ❌ **未达标** |
| **隐含**: 新增守卫有测试覆盖 | compute_all_metrics 守卫无直接测试 | ❌ **未达标** |

---

## 6. 总体判定

### 6.1 R3修复是否收敛

**部分收敛但未完全收敛**。

- ✅ 修复点1（测试）：基本达标，覆盖了 brier_parts 的核心验证逻辑。
- ✅ 修复点2（compute_all_metrics 守卫）：代码正确，位置正确。
- ❌ **N2-r2 攻击点未彻底修复**：ece/mce/bootstrap_ece 仍无守卫，直接调用仍静默返回错误结果。R3 修复建议本身不完整，正方机械执行未补全。
- ❌ **修复点2无测试覆盖**：compute_all_metrics 入口守卫无法被测试检测回归。
- ❌ **异常类型不一致**：brier_parts 抛 ValueError，ece 抛 TypeError，行为一致性目标未达成。

### 6.2 攻击点统计

| 严重程度 | 数量 | 攻击点 |
|---------|------|--------|
| 致命 | 0 | - |
| 严重 | 3 | 攻击8(ece/mce无守卫) + 攻击8扩展(异常类型不一致) + 攻击7(守卫无测试覆盖) |
| 中等 | 1 | 攻击1/2(边界值覆盖不全) |
| 轻微 | 5 | 攻击11(bool穿透) + 攻击4(随机种子) + 攻击6(错误消息未验证) + 攻击13(import风格) + 攻击14(类型注解) |
| **合计** | **9** | |

### 6.3 是否需要R4轮

**需要R4轮**，但修复量极小（约 8-12 行改动）。

R4 必修2项：
1. **[严重]** 在 `ece`/`mce`/`bootstrap_ece` 函数体开头各添加 n_bins 守卫（各 2 行，共 6 行）。这是 N2-r2 攻击点的彻底修复。
2. **[严重]** 在 `test_brier_parts_n_bins_validation` 中增加 `compute_all_metrics` 守卫测试（约 3-4 行）。这消除修复点2的测试覆盖空白。

R4 建议项（可选）：
3. 补充 n_bins=1 边界值测试和 n_bins=None 测试。
4. 排除 bool 类型（`isinstance(n_bins, bool)` 排除）。
5. 测试固定随机种子。
6. 测试验证 ValueError 错误消息内容。

---

## 7. 对抗透明性声明

- 本报告所有攻击点均经代码实测验证（read 工具读取源代码 + python 脚本运行验证），无臆测。
- 攻击8/8扩展/11 的反例均通过实际运行 Python 代码确认。
- 攻击7 通过代码分析确认（测试代码只调用 brier_parts 未调用 compute_all_metrics）。
- 测试运行确认 `test_brier_parts_n_bins_validation` 能通过（1 passed in 5.22s）。
- 本报告未发现致命攻击点——R3 修复的代码本身是正确的，问题在于修复范围不完整（ece/mce 未覆盖）和测试覆盖不完整（compute_all_metrics 守卫未测试）。

---

## 8. 结论

R3 轮修复**部分达成目标**：2 个修复点的代码本身正确，测试能通过运行。但存在 3 个严重攻击点：

1. **ece/mce/bootstrap_ece 仍无 n_bins 守卫**——R2 终审报告 N2-r2 攻击点未被彻底修复，直接调用仍静默返回错误结果，行为不一致问题仍存在。
2. **异常类型不一致**——brier_parts 抛 ValueError，ece 抛 TypeError，R3 修复的"行为一致性"目标未达成。
3. **compute_all_metrics 入口守卫无测试覆盖**——删除后测试仍通过，无法防止回归。

**建议R4轮修复**：在 ece/mce/bootstrap_ece 内部添加 n_bins 守卫（6 行）+ 补充 compute_all_metrics 守卫测试（3-4 行），共约 10 行改动。

**最终判定**：P0-4 R3 轮修复**需 R4 轮修复**。
