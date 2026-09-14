# P0-4 第二轮回炉修复——反方攻击报告（R2）

> **反方挑刺代理 R2 交付**（任务 #81）。本报告对正方 P0-4 第二轮修复（`src/utils/calibration.py` 的 `brier_parts()` 添加 `n_bins` 参数 + ValueError 守卫 + `compute_all_metrics` 内部调用传 n_bins）进行全方位攻击审查。
> **审查日期**：2026-09-09
> **审查代理**：反方挑刺代理 R2（GLM-5.2）
> **审查标准**：CBM 期刊审稿标准 + 防御性编程原则——修复必须完整、一致、可测试，不能"修了 A 漏了 B"。

---

## 修复审查总览

### 正方声称的修复内容
1. `brier_parts` 签名添加 `n_bins: int = 10` 参数
2. `brier_parts` 内添加 ValueError 守卫（L603-604）：`if not isinstance(n_bins, (int, np.integer)) or n_bins < 1: raise ValueError(...)`
3. `compute_all_metrics` 内部调用 `brier_parts` 时传 `n_bins=n_bins`（L770）

### 反方独立审查结论

| 修复项 | 代码位置 | 审查结果 | 备注 |
|--------|---------|---------|------|
| brier_parts 签名添加 n_bins | L586 | ✅ 已修复 | `def brier_parts(probs, labels, n_bins: int = 10):` |
| ValueError 守卫 | L603-604 | ✅ 已修复 | `isinstance(n_bins, (int, np.integer))` 覆盖 numpy 整数 |
| compute_all_metrics 传 n_bins | L770 | ✅ 已修复 | `brier_parts(probs, labels, n_bins=n_bins)` |
| 默认值一致性 | L586 vs L747 | ✅ 一致 | 两者默认值均为 10 |

**核心修复（F2 + S1/S2）确实已完成**。但反方在全方位审查中发现 **6 个仍存活的攻击点 + 4 个新发现攻击点**，证明本次回炉修复**仍不完整**。

---

## 存活攻击点（第一轮已识别但本轮未修复）

### F1-r2：5 处调用方仍遗漏 n_bins（严重，存活）

**攻击点**：第一轮 P0-4 审查的 F1 攻击点指出 `run_e1a_l2_shift_full.py` 和 `run_e1b_loco_validation.py` 共 5 处调用 `brier_parts()` 未传 n_bins。**本轮回炉修复未处理这 5 处**。

**代码证据**（反方独立 grep 确认，2026-09-09）：

```python
# scripts/run_e1a_l2_shift_full.py:159
_, rel, _, _ = brier_parts(mp, corr)              # ← 未传 n_bins

# scripts/run_e1b_loco_validation.py:552-553
brier_raw_total, rel_raw, res_raw, unc_raw = brier_parts(raw_mp, raw_correct)   # ← 未传
brier_cal_total, rel_cal, res_cal, unc_cal = brier_parts(cal_mp, cal_correct)   # ← 未传

# scripts/run_e1b_loco_validation.py:593-594（_ncv_stat 闭包内）
_, rel_r, _, _ = brier_parts(rmp, rcor)           # ← 未传
_, rel_c, _, _ = brier_parts(cmp, ccor)           # ← 未传
```

**反例构造**：
- 当前 `brier_parts` 默认 n_bins=10，与 E1a/E1b 期望行为一致，**数值无变化**。
- 但若未来研究者将 `brier_parts` 默认值改为 15（例如匹配 E2 的 N_BINS=15），这 5 处会**静默改变行为**而无任何告警。
- 更危险的是：E1b 的 `_ncv_stat` 闭包（L593-594）用于 NCV 的 cluster bootstrap CI，若默认值改变，NCV 数值会与点估计（L552-553）不一致——**同一函数内点估计用默认 n_bins、CI 重采样也用默认 n_bins，但两者依赖的默认值可能被未来修改者遗漏**。

**定级**：严重（工程稳健性）。当前无数值 bug，但修复声称"所有调用方都正确传参"是不完整的不实声明。

**修补建议**：5 处显式传 `n_bins=10`（或定义模块级常量 `N_BINS = 10` 并引用）。

---

### S3-r2：测试仍通过 compute_all_metrics 间接测试（严重，存活）

**攻击点**：第一轮 S3 指出 `test_brier_parts` 通过 `compute_all_metrics(n_bins=5)` 间接测试 brier_parts，无法直接验证 brier_parts 的 n_bins 参数行为。**本轮回炉修复未补充直接测试**。

**代码证据**（`tests/test_model.py` L188-198，未修改）：

```python
def test_brier_parts(self):
    metrics = compute_all_metrics(
        np.random.rand(100), (np.random.rand(100) > 0.5).astype(float), n_bins=5, n_bootstrap=20
    )
    assert 'ece' in metrics and 'brier' in metrics
    # Murphy分解精确恒等式（按构造成立）
    total = (metrics['brier_reliability'] - metrics['brier_resolution']
             + metrics['brier_uncertainty'])
    assert total == pytest.approx(metrics['brier'], abs=1e-12)
    # raw Brier 与分解总量应接近（分箱残差小）
    assert abs(metrics['brier_raw'] - metrics['brier']) < 0.1
```

**问题分析**：
1. 测试仍通过 `compute_all_metrics(n_bins=5)` 间接测试，未直接调用 `brier_parts(n_bins=5)`。
2. **未测试 ValueError 守卫**：本轮新增了 `isinstance` 检查和 `n_bins < 1` 检查，但没有任何测试验证守卫是否正确触发（n_bins=0、n_bins=-1、n_bins=1.5、n_bins="10" 等）。
3. **未测试 numpy 整数类型**：本轮声称 `isinstance(n_bins, (int, np.integer))` 覆盖 np.int64，但无测试验证 `brier_parts(probs, labels, n_bins=np.int64(10))` 是否正常工作。

**反例**：若未来有人误删 `np.integer` 从 isinstance 检查中（例如改为 `isinstance(n_bins, int)`），所有现有测试仍通过——**测试无法捕获 isinstance 检查的退化**。

**定级**：严重（测试覆盖不足）。修复添加了新逻辑（ValueError 守卫）但未添加对应测试，违背"修了代码必须修测试"原则。

**修补建议**：
```python
def test_brier_parts_n_bins_validation(self):
    probs = np.random.rand(100)
    labels = (np.random.rand(100) > 0.5).astype(float)
    # 直接测试 n_bins 参数生效
    b5 = brier_parts(probs, labels, n_bins=5)
    b10 = brier_parts(probs, labels, n_bins=10)
    assert b5 != b10  # 不同 n_bins 应产生不同结果
    # 测试 numpy 整数类型
    b_np = brier_parts(probs, labels, n_bins=np.int64(10))
    assert b_np == b10
    # 测试 ValueError 守卫
    for bad_n_bins in [0, -1, 1.5, "10", None]:
        with pytest.raises(ValueError):
            brier_parts(probs, labels, n_bins=bad_n_bins)
```

---

### M3-r2：E1b 注释代码未传 n_bins（轻微，存活）

**攻击点**：第一轮 M3 指出 `run_e1b_loco_validation.py` L585 注释代码 `# ncv = brier_parts(raw_mp, raw_correct)[1] - brier_parts(cal_mp, cal_correct)[1]` 未传 n_bins。**本轮未清理**。

**代码证据**（L585，未修改）：
```python
#   ncv = brier_parts(raw_mp, raw_correct)[1] - brier_parts(cal_mp, cal_correct)[1]
```

**定级**：轻微（注释代码，无运行时影响）。但若未来取消注释，会继承 F1-r2 的 bug。

**修补建议**：清理注释代码，或改为 `# ncv = brier_parts(raw_mp, raw_correct, n_bins=N_BINS)[1] - ...`。

---

## 新发现攻击点（本轮审查首次发现）

### N1-r2：compute_all_metrics 的 7 处调用方未传 n_bins（严重，新发现）

**攻击点**：本轮全方位 grep `compute_all_metrics(` 发现 **7 处调用方未传 n_bins**，依赖默认值 10。

**代码证据**（反方独立 grep 确认）：

```python
# scripts/run_e5_inception_lite.py:365-366, 474-475（4 处）
raw_metrics = compute_all_metrics(max_probs_raw, correct_mask, n_bootstrap=1000)
ts_metrics = compute_all_metrics(max_probs_ts, correct_mask, n_bootstrap=1000)

# scripts/train.py:209, 674-675（3 处）
cal_metrics = compute_all_metrics(max_probs, correct_mask, n_bootstrap=0)
raw_metrics = compute_all_metrics(max_probs_raw, correct_mask, n_bootstrap=1000)
cal_m = compute_all_metrics(max_probs_cal, correct_mask, n_bootstrap=1000)
```

**问题分析**：
- 这 7 处都未传 `n_bins`，依赖 `compute_all_metrics` 的默认值 10。
- 当前行为正确（默认 10 与全代码库一致），但**与 F1-r2 同性质的工程稳健性问题**：若未来修改 `compute_all_metrics` 默认值，这 7 处会静默改变行为。
- 更严重的是：`run_e5_inception_lite.py` 是 P0-6+7 的修复目标脚本，已确认存在多个致命缺陷（F1/F2/F3），若 P0-6+7 回炉修复时研究者调整 n_bins 默认值，E5 的校准指标会静默偏移。

**定级**：严重（工程稳健性，与 F1-r2 同级）。修复 F1-r2 时应同步处理这 7 处。

**修补建议**：7 处显式传 `n_bins=10`，或定义模块级常量并引用。

---

### N2-r2：ValueError 守卫覆盖范围不完整——ece/mce 无守卫（严重，新发现）

**攻击点**：本轮在 `brier_parts` 内添加了 ValueError 守卫，但 **`ece()`、`mce()`、`bootstrap_ece()` 都没有 n_bins 验证**。这导致 `compute_all_metrics(n_bins=0)` 时**部分指标静默错误、部分抛异常，行为不一致**。

**代码证据**：

```python
# src/utils/calibration.py L199-243（ece 函数）
def ece(probs, labels, n_bins: int = 10, adaptive: bool = False) -> float:
    # ← 无 n_bins 验证！
    ...
    bin_boundaries = np.linspace(0, 1, n_bins + 1)  # n_bins=0 → np.linspace(0,1,1)=[0.]
    ...
    for i in range(n_bins):  # n_bins=0 → 不执行
        ...
    return float(ece_val)  # n_bins=0 → 返回 0.0（静默错误）

# src/utils/calibration.py L643-676（mce 函数）
def mce(probs, labels, n_bins: int = 10) -> float:
    # ← 无 n_bins 验证！
    ...
    for i in range(n_bins):  # n_bins=0 → 不执行
        ...
    return float(max_error)  # n_bins=0 → 返回 0.0（静默错误）
```

**反例构造**：

```python
>>> import numpy as np
>>> from src.utils.calibration import compute_all_metrics
>>> probs = np.random.rand(100)
>>> labels = (probs > 0.5).astype(float)
>>> compute_all_metrics(probs, labels, n_bins=0, n_bootstrap=0)
# 执行顺序：
# 1. bootstrap_ece(probs, labels, 0, 0) → ece(probs, labels, 0) → 返回 0.0（静默错误）
# 2. brier_parts(probs, labels, n_bins=0) → raise ValueError（守卫触发）
# 结果：用户看到 ValueError，但不知道 ece/mce 已经静默返回了 0.0
# 更糟糕的是：如果用户 catch 了 ValueError，会拿到部分错误的指标
```

**问题分析**：
- `compute_all_metrics` 内部调用顺序：L767 `bootstrap_ece` → L770 `brier_parts` → L773 `mce`。
- n_bins=0 时：`bootstrap_ece` 先静默返回 0.0，然后 `brier_parts` 抛 ValueError，`mce` 未执行。
- **行为不一致**：ECE 静默错误（0.0），Brier 抛异常，MCE 未执行。用户无法判断哪个指标可信。
- n_bins=-1 时更糟：`np.linspace(0, 1, 0)` 返回空数组，`for i in range(-1)` 不执行，ece/mce 都返回 0.0，然后 `brier_parts` 抛 ValueError。

**定级**：严重（防御性编程不完整）。修复在 brier_parts 添加守卫是好的，但**应该在 compute_all_metrics 入口处统一验证**，或同步在 ece/mce 中添加守卫。

**修补建议**：
```python
# 方案 A（推荐）：在 compute_all_metrics 入口处统一验证
def compute_all_metrics(probs, labels, n_bins: int = 10, n_bootstrap: int = 1000) -> dict:
    if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
        raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
    ...

# 方案 B：在 ece/mce 中同步添加守卫（与 brier_parts 一致）
def ece(probs, labels, n_bins: int = 10, adaptive: bool = False) -> float:
    if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
        raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
    ...
```

---

### N3-r2：isinstance 检查接受 bool——语义漏洞（轻微，新发现）

**攻击点**：`isinstance(n_bins, (int, np.integer))` 中，Python 的 `bool` 是 `int` 的子类，`isinstance(True, int)` 返回 `True`。这导致 `brier_parts(probs, labels, n_bins=True)` 会通过守卫。

**代码证据**：

```python
>>> isinstance(True, int)
True
>>> isinstance(False, int)
True
>>> True < 1
False  # True == 1，所以 True < 1 为 False
>>> False < 1
True   # False == 0，所以 False < 1 为 True
```

**反例构造**：

```python
>>> brier_parts(probs, labels, n_bins=True)
# isinstance(True, (int, np.integer)) → True
# True < 1 → False（因为 True == 1）
# 通过守卫，n_bins=True 被当作 n_bins=1 使用
# 返回正常结果，但 n_bins=True 是语义错误——用户可能误传布尔值

>>> brier_parts(probs, labels, n_bins=False)
# isinstance(False, (int, np.integer)) → True
# False < 1 → True（因为 False == 0）
# 触发 ValueError——这是正确的，但原因不是"False 不是整数"，而是"False < 1"
```

**问题分析**：
- `n_bins=True` 会被静默接受为 `n_bins=1`，这是语义漏洞——bool 不应该被接受为分箱数。
- `n_bins=False` 会触发 ValueError，但错误信息 `"n_bins must be a positive integer, got False"` 会让用户困惑（False 看起来不是整数）。
- 这是 Python 类型系统的已知陷阱，但防御性编程应该排除 bool。

**定级**：轻微（边界条件，现实触发概率低）。但防御性编程应严谨。

**修补建议**：
```python
if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
    raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
```

---

### N4-r2：类型注解与运行时检查不一致（轻微，新发现）

**攻击点**：`brier_parts` 签名 `n_bins: int = 10` 类型注解是 `int`，但运行时 `isinstance` 检查接受 `np.integer`。类型注解与运行时行为不一致。

**代码证据**：

```python
def brier_parts(probs, labels, n_bins: int = 10):  # ← 类型注解是 int
    if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:  # ← 运行时接受 np.integer
        raise ValueError(...)
```

**问题分析**：
- mypy / pyright 静态类型检查会报 `brier_parts(probs, labels, n_bins=np.int64(10))` 不符合 `int` 注解。
- 但运行时 `isinstance(np.int64(10), (int, np.integer))` 返回 `True`，正常工作。
- **静态检查与运行时行为矛盾**：静态检查拒绝的代码运行时正常，会让用户困惑。

**定级**：轻微（类型系统问题，不影响运行时正确性）。但若项目使用 mypy 严格模式，会触发误报。

**修补建议**：
```python
from typing import Union
def brier_parts(probs, labels, n_bins: Union[int, np.integer] = 10):
    ...
```
或保持 `int` 注解但在 docstring 中说明也接受 `np.integer`。

---

## 全局调用链完整性审查

### brier_parts 调用方清单（反方独立 grep 确认）

| 调用方 | 行号 | 传 n_bins? | 状态 |
|--------|------|-----------|------|
| `scripts/run_e1a_l2_shift_full.py` | L159 | ❌ 未传 | **F1-r2 存活** |
| `scripts/run_e1b_loco_validation.py` | L552 | ❌ 未传 | **F1-r2 存活** |
| `scripts/run_e1b_loco_validation.py` | L553 | ❌ 未传 | **F1-r2 存活** |
| `scripts/run_e1b_loco_validation.py` | L585 | ❌ 注释代码 | **M3-r2 存活** |
| `scripts/run_e1b_loco_validation.py` | L593 | ❌ 未传 | **F1-r2 存活** |
| `scripts/run_e1b_loco_validation.py` | L594 | ❌ 未传 | **F1-r2 存活** |
| `scripts/run_e2_ablation_discrimination.py` | L315 | ✅ `n_bins=N_BINS` | 正确 |
| `scripts/run_e3_brier_dcr_ncv.py` | L181 | ✅ `n_bins=n_bins` | 正确 |
| `scripts/run_e3_brier_dcr_ncv.py` | L199 | ✅ `n_bins=n_bins` | 正确 |
| `scripts/run_e4_temperature_analysis.py` | L175 | ✅ `n_bins=BRIER_N_BINS` | 正确 |
| `src/utils/calibration.py` | L770 | ✅ `n_bins=n_bins` | **本轮已修复** |
| `scripts/run_e6_reliability_diagrams.py` | — | 不调用 | N/A（M1 已确认） |

**结论**：11 处实际调用中，**5 处仍未传 n_bins**（F1-r2），1 处注释代码未传（M3-r2），5 处正确传参。**调用链完整性 5/11 = 45%**。

### compute_all_metrics 调用方清单

| 调用方 | 行号 | 传 n_bins? | 状态 |
|--------|------|-----------|------|
| `scripts/run_e5_inception_lite.py` | L365 | ❌ 未传（默认 10） | **N1-r2 新发现** |
| `scripts/run_e5_inception_lite.py` | L366 | ❌ 未传（默认 10） | **N1-r2 新发现** |
| `scripts/run_e5_inception_lite.py` | L474 | ❌ 未传（默认 10） | **N1-r2 新发现** |
| `scripts/run_e5_inception_lite.py` | L475 | ❌ 未传（默认 10） | **N1-r2 新发现** |
| `scripts/train.py` | L209 | ❌ 未传（默认 10） | **N1-r2 新发现** |
| `scripts/train.py` | L674 | ❌ 未传（默认 10） | **N1-r2 新发现** |
| `scripts/train.py` | L675 | ❌ 未传（默认 10） | **N1-r2 新发现** |
| `tests/test_model.py` | L189 | ✅ `n_bins=5` | 正确 |
| `tests/test_model.py` | L230 | ✅ `n_bins=5` | 正确 |

**结论**：9 处调用中，**7 处未传 n_bins**（N1-r2），2 处正确传参。**调用链完整性 2/9 = 22%**。

---

## 边界条件审查

### n_bins=1（所有样本一个 bin）

**审查结果**：正常工作，但 docstring 未说明退化行为。

**代码分析**：
- `np.linspace(0, 1, 2)` = `[0., 1.]`
- 所有样本进一个 bin（`mask = (probs >= 0) & (probs <= 1)` = 全 True）
- `reliability = (avg_prob - avg_label)²`
- `resolution = (avg_label - base_rate)² = 0`（因为 `avg_label = base_rate`）
- `uncertainty = base_rate * (1 - base_rate)`
- `brier_total = reliability - 0 + uncertainty = (avg_prob - avg_label)² + base_rate*(1-base_rate)`

**定级**：无 bug，但建议 docstring 说明 n_bins=1 的退化行为。

### n_bins > len(probs)（bins 多于样本）

**审查结果**：正常工作，不崩溃，但 reliability/resolution 估计高方差。

**代码分析**：
- 例如 `n_bins=100, len(probs)=50`：会有很多空 bin
- `if mask.sum() == 0: continue` 正确处理空 bin
- 非空 bin 中 `n_bin=1`，`avg_prob` 和 `avg_label` 都是单样本值
- reliability 估计高方差（每箱单样本），但数学上正确

**定级**：无 bug，已知统计问题。建议 docstring 警告"n_bins >> n_samples 时估计高方差"。

### n_bins=0 / 负数

**审查结果**：brier_parts 正确触发 ValueError，但 ece/mce 静默返回 0.0（见 N2-r2）。

**代码分析**：
- `brier_parts(n_bins=0)`：L603 `isinstance(0, (int, np.integer))` = True，`0 < 1` = True → 触发 ValueError ✓
- `brier_parts(n_bins=-1)`：`-1 < 1` = True → 触发 ValueError ✓
- `ece(n_bins=0)`：无守卫，`np.linspace(0, 1, 1)` = `[0.]`，`for i in range(0)` 不执行，返回 0.0 ❌
- `mce(n_bins=0)`：无守卫，同上，返回 0.0 ❌

**定级**：brier_parts 守卫正确，但 ece/mce 缺守卫（N2-r2）。

### n_bins=浮点数

**审查结果**：正确触发 ValueError。

**代码分析**：
- `brier_parts(n_bins=1.5)`：`isinstance(1.5, (int, np.integer))` = False → 触发 ValueError ✓
- `brier_parts(n_bins=10.0)`：`isinstance(10.0, (int, np.integer))` = False → 触发 ValueError ✓

**定级**：正确修复（M2 已解决）。

---

## 默认值一致性审查

### 模块内默认值

| 函数 | n_bins 默认值 | 位置 |
|------|--------------|------|
| `ece` | 10 | L199 |
| `smooth_ece` | N/A（无 n_bins） | L246 |
| `bootstrap_ece` | 10 | L523 |
| `brier_parts` | 10 | L586 |
| `mce` | 10 | L643 |
| `plot_reliability_diagram` | 10 | L682 |
| `compute_all_metrics` | 10 | L747 |

**结论**：模块内默认值全部一致（10）✅。

### 跨实验默认值

| 脚本 | n_bins 值 | 来源 |
|------|----------|------|
| E1a (`run_e1a_l2_shift_full.py`) | 默认 10（未显式传） | 依赖 brier_parts 默认 |
| E1b (`run_e1b_loco_validation.py`) | 默认 10（未显式传） | 依赖 brier_parts 默认 |
| E2 (`run_e2_ablation_discrimination.py`) | `N_BINS=15` | 显式传 |
| E3 (`run_e3_brier_dcr_ncv.py`) | `N_BINS=10` | 显式传 |
| E4 (`run_e4_temperature_analysis.py`) | `BRIER_N_BINS=10` | 显式传 |
| E5 (`run_e5_inception_lite.py`) | 默认 10（未显式传） | 依赖 compute_all_metrics 默认 |
| E6 (`run_e6_reliability_diagrams.py`) | N/A | 不调用 brier_parts |

**问题**：
- E2 用 `N_BINS=15`，与其他实验的 10 不一致（P0-3 职责，非 P0-4）。
- E1a/E1b/E5 依赖默认值，未显式声明——**隐式约定脆弱**。

**定级**：E2 不一致是 P0-3 职责；E1a/E1b/E5 依赖默认值是 F1-r2/N1-r2 的体现。

### 默认值一致性风险

**攻击点**：所有函数默认值都是硬编码 `10`，**没有模块级常量**。若未来修改其中一个函数的默认值（例如 `brier_parts` 改为 15），其他函数不会同步修改，导致不一致。

**修补建议**：定义模块级常量 `DEFAULT_N_BINS = 10`，所有函数默认值引用此常量：
```python
DEFAULT_N_BINS = 10

def brier_parts(probs, labels, n_bins: int = DEFAULT_N_BINS):
    ...

def compute_all_metrics(probs, labels, n_bins: int = DEFAULT_N_BINS, ...):
    ...
```

---

## ValueError 守卫位置审查

### 守卫位置

**当前**：守卫在 `brier_parts` 内部（L603-604）。

**审查结论**：位置正确——在最底层函数中验证输入，所有调用方都会被保护。但**覆盖不完整**（N2-r2）：`ece`/`mce`/`bootstrap_ece` 无守卫。

### 守卫触发时机

**当前**：`compute_all_metrics(n_bins=0)` 时，L767 `bootstrap_ece` 先执行（静默错误），L770 `brier_parts` 后执行（触发 ValueError）。

**问题**：用户看到 ValueError 时，`bootstrap_ece` 已经静默返回了 0.0，但用户不知道。如果用户 catch ValueError 并继续使用部分结果，会拿到错误的 ECE。

**修补建议**：在 `compute_all_metrics` 入口处统一验证（N2-r2 方案 A），确保所有子函数调用前 n_bins 已验证。

---

## 攻击点汇总表

| 攻击点 | 定级 | 类别 | 状态 | 修补建议 |
|--------|------|------|------|---------|
| F1-r2 | 严重 | 存活（第一轮 F1） | 5 处调用方未传 n_bins | 5 处显式传 n_bins=10 |
| S3-r2 | 严重 | 存活（第一轮 S3） | 测试未补充直接测试 + 未测试 ValueError 守卫 | 补充 test_brier_parts_n_bins_validation |
| M3-r2 | 轻微 | 存活（第一轮 M3） | E1b 注释代码未传 n_bins | 清理注释代码 |
| N1-r2 | 严重 | 新发现 | compute_all_metrics 7 处调用方未传 n_bins | 7 处显式传 n_bins=10 |
| N2-r2 | 严重 | 新发现 | ece/mce 无 n_bins 守卫，n_bins=0 时行为不一致 | compute_all_metrics 入口统一验证或 ece/mce 同步加守卫 |
| N3-r2 | 轻微 | 新发现 | isinstance 接受 bool（n_bins=True 被当作 1） | 排除 bool |
| N4-r2 | 轻微 | 新发现 | 类型注解 int vs 运行时接受 np.integer 不一致 | 改为 Union[int, np.integer] 或 docstring 说明 |
| 默认值风险 | 轻微 | 新发现 | 硬编码 10 无模块级常量，未来修改易不一致 | 定义 DEFAULT_N_BINS = 10 |

**总计**：4 个严重 + 4 个轻微，共 8 个攻击点。

---

## 与第一轮攻击对比

| 第一轮攻击点 | 第一轮定级 | 本轮状态 | 本轮定级 |
|-------------|-----------|---------|---------|
| F1（5 处调用方遗漏） | 致命 | **存活**（F1-r2） | 严重（降级，因默认值兼容） |
| F2（compute_all_metrics 漏传） | 致命 | **已修复** ✅ | — |
| F3（E2 用 N_BINS=15） | 严重 | 不适用（P0-3 职责） | — |
| F4（跨实验分箱不一致） | 严重 | 不适用（实验设计决策） | — |
| S1（无 n_bins 输入验证） | 严重 | **已修复** ✅ | — |
| S2（n_bins=0 时 reliability=0） | 严重 | **已修复** ✅（brier_parts） | — |
| S3（测试因 F2 失效） | 严重 | **存活**（S3-r2） | 严重 |
| M1（E6 不调用 brier_parts） | 轻微 | 不适用 | — |
| M2（n_bins=浮点数崩溃） | 轻微 | **已修复** ✅ | — |
| M3（E1b 注释代码） | 轻微 | **存活**（M3-r2） | 轻微 |

**新发现攻击点**：N1-r2（严重）、N2-r2（严重）、N3-r2（轻微）、N4-r2（轻微）、默认值风险（轻微）。

---

## 终审建议

### 必修项（严重，论文投稿前必须修复）

1. **F1-r2 + N1-r2**：12 处调用方显式传 `n_bins=10`（5 处 brier_parts + 7 处 compute_all_metrics）。虽当前默认值兼容，但修复声称"所有调用方都正确传参"是不完整声明，且未来默认值修改会静默改变行为。

2. **S3-r2**：补充 `test_brier_parts_n_bins_validation` 测试，直接测试 brier_parts 的 n_bins 参数行为 + ValueError 守卫 + numpy 整数类型支持。

3. **N2-r2**：在 `compute_all_metrics` 入口处统一验证 n_bins，或在 `ece`/`mce`/`bootstrap_ece` 中同步添加守卫。确保 n_bins=0/负数时所有指标行为一致（统一抛 ValueError 或统一静默，不能混合）。

### 建议项（轻微，可后续迭代）

4. **M3-r2**：清理 E1b L585 注释代码。
5. **N3-r2**：isinstance 检查排除 bool。
6. **N4-r2**：类型注解改为 `Union[int, np.integer]` 或 docstring 说明。
7. **默认值风险**：定义模块级常量 `DEFAULT_N_BINS = 10`。

### 优先级

- **高**：F1-r2 + N1-r2（12 处显式传参，工程稳健性）
- **高**：S3-r2（测试覆盖，验证本轮新增的 ValueError 守卫）
- **中**：N2-r2（防御性编程完整性，ece/mce 守卫）
- **低**：M3-r2、N3-r2、N4-r2、默认值风险

---

## 反方声明

本报告由反方挑刺代理 R2 独立撰写，基于对 `src/utils/calibration.py` 全文 + 全代码库 grep `brier_parts(` 和 `compute_all_metrics(` 的独立审查。所有攻击点均有代码行号证据，无臆测。

**关键发现**：
- **核心修复（F2 + S1/S2）确实已完成**，正方本轮回炉修复了第一轮的致命 bug（F2）和严重 bug（S1/S2）。
- **但修复仍不完整**：4 个严重攻击点存活/新发现（F1-r2、S3-r2、N1-r2、N2-r2），证明本次回炉修复**未通过全方位审查**。
- **最危险的新发现是 N2-r2**：ValueError 守卫只在 brier_parts 添加，ece/mce 无守卫，导致 `compute_all_metrics(n_bins=0)` 时 ECE 静默返回 0.0 而 Brier 抛异常——**部分指标静默错误、部分抛异常，行为不一致**。这是防御性编程不完整的典型反例。
- **F1-r2 + N1-r2 共 12 处调用方未传 n_bins**：虽当前默认值兼容，但修复声称"所有调用方都正确传参"是不完整声明，且未来默认值修改会静默改变行为。

**最终判定**：P0-4 第二轮回炉修复**部分通过**——核心 bug 已修复，但仍有 4 个严重攻击点需在论文投稿前修复。建议第三轮回炉处理 F1-r2 + N1-r2 + S3-r2 + N2-r2。
