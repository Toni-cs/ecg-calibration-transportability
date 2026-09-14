# P0-4 反方攻击报告：brier_parts n_bins 参数修复

> **反方挑刺代理-P0-4 交付**。本报告对正方 P0-4 修复（`src/utils/calibration.py` 的 `brier_parts()` 函数添加 `n_bins` 参数）进行全方位攻击审查，覆盖所有调用方传参正确性、默认值一致性、边界条件、跨实验一致性、内部一致性等维度。
>
> **攻击日期**：2026-09-09
> **攻击对象**：`src/utils/calibration.py` L586-631（`brier_parts` 函数）及所有调用方
> **修复主张**：添加 `n_bins: int = 10` 参数，替换硬编码 11→`n_bins+1`、`range(10)`→`range(n_bins)`、`i==9`→`i==n_bins-1`，更新 E3 调用处传 `n_bins=N_BINS`
> **攻击代理**：反方挑刺代理-P0-4（GLM-5.2）
> **攻击维度**：反例构造 / 逻辑断链 / 隐含假设 / 边界失效 / 自相矛盾 / 量级错误 / 语义偏移（7 维度全覆盖）

---

## 0. 攻击审查概述

### 严重性汇总表

| 编号 | 严重性 | 攻击维度 | 位置 | 攻击摘要 | 可修补性 |
|------|--------|---------|------|---------|---------|
| F1 | **致命** | 隐含假设/逻辑断链 | `run_e1a_l2_shift_full.py` L159, `run_e1b_loco_validation.py` L552/553/593/594 | **5 处调用方遗漏**：E1a/E1b 调用 `brier_parts()` 未传 n_bins，修复声称"所有调用方都正确传参"不成立 | 需显式传 n_bins 或文档化默认依赖 |
| F2 | **致命** | 自相矛盾/语义偏移 | `calibration.py` L768 | `compute_all_metrics()` 接受 `n_bins` 参数但**未传给 `brier_parts()`**，内部自相矛盾；ece/mce 都传了，唯独 brier_parts 漏传 | 需在 L768 添加 `n_bins=n_bins` |
| F3 | **严重** | 语义偏移/量级错误 | `run_e2_ablation_discrimination.py` L131/L315 | E2 传 `n_bins=N_BINS=15`，与原始硬编码 10 **不一致**，是静默行为变更；若 E2 之前用 10 bin 生成缓存结果，现在用 15 bin，结果不可复现 | 需文档化或统一 N_BINS=10 |
| F4 | **严重** | 自相矛盾/量级错误 | E2 L131 vs E3 L150 vs E4 L141 | **跨实验分箱数不一致**：E2=15, E3=10, E4=10, E1a=10(default), E1b=10(default)；Brier reliability 跨实验不可直接比较 | 需统一分箱数或显式文档化差异 |
| S1 | **严重** | 边界失效/隐含假设 | `calibration.py` L608/L614 | **无 n_bins 输入验证**：n_bins=0 或负数不崩溃但产生无意义结果（brier_total=uncertainty），无警告；n_bins=浮点数崩溃 | 需加 `if n_bins < 1: raise ValueError` |
| S2 | **严重** | 边界失效 | `calibration.py` L608 | n_bins=0 时 `np.linspace(0,1,1)`=[0.0]，`range(0)`=空循环，reliability=0, resolution=0, brier_total=uncertainty——**静默返回无意义值** | 需显式拒绝 n_bins<1 |
| S3 | **严重** | 隐含假设/逻辑断链 | `tests/test_model.py` L188-198 | `test_brier_parts` 通过 `compute_all_metrics(n_bins=5)` 间接测试，但因 F2（compute_all_metrics 不传 n_bins 给 brier_parts），**测试实际验证的是默认 10 bin 而非 5 bin**；测试无法捕获 F2 bug | 需直接测试 brier_parts(n_bins=5) |
| M1 | **轻微** | 隐含假设 | `run_e6_reliability_diagrams.py` | E6 **不调用 brier_parts**，有自己的分箱逻辑；任务要求检查 E6 是多余，但修复覆盖声明提到 E6 也不准确 | 需修正覆盖声明 |
| M2 | **轻微** | 边界失效 | `calibration.py` L608 | n_bins=浮点数（如 10.5）时 `range(n_bins)` 抛 TypeError 崩溃；类型注解为 int 但无运行时检查 | 需加 `n_bins = int(n_bins)` 或运行时检查 |
| M3 | **轻微** | 语义偏移 | `calibration.py` L585 注释 | E1b L585 注释 `# ncv = brier_parts(raw_mp, raw_correct)[1] - ...` 是注释代码，也未传 n_bins | 需清理注释代码 |

### 攻击数量统计

- **致命攻击 (F)**：2 个
- **严重攻击 (S)**：3 个
- **轻微攻击 (M)**：3 个
- **总计**：8 个攻击点

### 整体评估

**P0-4 修复的核心变更（添加 n_bins 参数、替换硬编码）本身是正确的**：`i == n_bins - 1` 与原始 `i == 9` 在 n_bins=10 时等价，`np.linspace(0, 1, n_bins + 1)` 与原始 `np.linspace(0, 1, 11)` 等价，默认值 10 与原始硬编码一致，向后兼容性成立。

**但修复的覆盖范围存在两个致命缺口**：

1. **F1：E1a/E1b 共 5 处调用方被遗漏**。任务描述只提到 E2/E3/E4/E6，但 `run_e1a_l2_shift_full.py` 和 `run_e1b_loco_validation.py` 也调用 `brier_parts()` 且未传 n_bins。虽然依赖默认值 10 在当前向后兼容，但修复声称"所有调用方都正确传参"是不完整的不实声明。更危险的是：如果未来有人修改 `brier_parts` 的默认值（例如改为 15 以匹配 E2），E1a/E1b 会**静默改变行为**而无任何告警。

2. **F2：`compute_all_metrics()` 内部自相矛盾**。该函数接受 `n_bins` 参数并正确传给 `ece()`、`mce()`、`bootstrap_ece()`，但 L768 调用 `brier_parts(probs, labels)` 时**漏传 n_bins**。这意味着 `compute_all_metrics(n_bins=5)` 会用 5 bin 算 ECE/MCE，但用 10 bin 算 Brier——**同一函数内分箱数不一致**。这是 P0-4 修复最直接的内部遗漏。

**即使修复 F1/F2，严重攻击仍限制结论强度**：F3/F4 揭示跨实验分箱数不一致（E2=15 vs E3/E4=10），使 Brier reliability 跨实验比较无效；S1/S2 揭示无输入验证导致 n_bins≤0 静默返回无意义值；S3 揭示测试因 F2 而失效。

**建议**：在修复 F1/F2 之前，P0-4 修复不应被视为完成。最小修补：在 `compute_all_metrics` L768 添加 `n_bins=n_bins`；在 E1a/E1b 所有调用处显式传 `n_bins=10`；在 `brier_parts` 开头加 `if n_bins < 1: raise ValueError`。

---

## 1. 致命攻击 (Fatal)

### F1：E1a/E1b 共 5 处调用方遗漏——"所有调用方都正确传参"是不实声明

**位置**：
- `scripts/run_e1a_l2_shift_full.py` L159
- `scripts/run_e1b_loco_validation.py` L552, L553, L593, L594

**攻击维度**：隐含假设 + 逻辑断链

**代码证据**：

`run_e1a_l2_shift_full.py` L151-160:
```python
def _brier_reliability(probs: np.ndarray, labels: np.ndarray) -> float:
    """Brier reliability 分量（Murphy 分解，10 等宽箱）。"""
    mp = _maxprob(probs) if probs.ndim == 2 else np.asarray(probs)
    corr = _bin(probs, labels) if probs.ndim == 2 else np.asarray(labels, dtype=float)
    _, rel, _, _ = brier_parts(mp, corr)  # ← 未传 n_bins！
    return float(rel)
```

`run_e1b_loco_validation.py` L552-553:
```python
brier_raw_total, rel_raw, res_raw, unc_raw = brier_parts(raw_mp, raw_correct)  # ← 未传 n_bins
brier_cal_total, rel_cal, res_cal, unc_cal = brier_parts(cal_mp, cal_correct)  # ← 未传 n_bins
```

`run_e1b_loco_validation.py` L593-594（NCV cluster bootstrap 内部）:
```python
_, rel_r, _, _ = brier_parts(rmp, rcor)  # ← 未传 n_bins
_, rel_c, _, _ = brier_parts(cmp, ccor)  # ← 未传 n_bins
```

**论证**：

1. 全代码库 `grep brier_parts\(` 共找到 **11 处调用**（含定义处 1 处、文档中 6 处、实际代码 10 处）。
2. 实际代码调用方：
   - `calibration.py` L768（`compute_all_metrics` 内）— **未传**（见 F2）
   - `run_e1a_l2_shift_full.py` L159 — **未传**
   - `run_e1b_loco_validation.py` L552/553/593/594 — **未传**（4 处）
   - `run_e2_ablation_discrimination.py` L315 — 传 `n_bins=N_BINS`（=15）
   - `run_e3_brier_dcr_ncv.py` L181/199 — 传 `n_bins=n_bins`
   - `run_e4_temperature_analysis.py` L175 — 传 `n_bins=BRIER_N_BINS`（=10）
3. **未传 n_bins 的调用方共 6 处**（E1a 1 处 + E1b 4 处 + compute_all_metrics 1 处），均依赖默认值 10。
4. 任务描述只提到 E2/E3/E4/E6，**完全遗漏 E1a/E1b**。

**反例**：

设未来某次维护将 `brier_parts` 默认值从 10 改为 15（例如为与 E2 的 N_BINS=15 对齐）。此时：
- E3/E4 显式传 10，不受影响 ✅
- E2 显式传 15，不受影响 ✅
- **E1a/E1b 静默从 10 bin 切换到 15 bin**，所有 E1a/E1b 的历史结果不可复现，且无任何告警 ❌

**裁决**：**致命**——修复覆盖声明不实，5 处调用方遗漏。当前因默认值=原始硬编码而向后兼容，但这是**脆弱的巧合兼容**，非显式安全。

---

### F2：`compute_all_metrics()` 内部自相矛盾——接受 n_bins 但不传给 brier_parts

**位置**：`src/utils/calibration.py` L742-782

**攻击维度**：自相矛盾 + 语义偏移

**代码证据**：

`calibration.py` L742-768:
```python
def compute_all_metrics(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,          # ← 接受 n_bins
    n_bootstrap: int = 1000
) -> dict:
    ...
    # ECE with confidence interval
    ece_mean, ece_lower, ece_upper = bootstrap_ece(probs, labels, n_bins, n_bootstrap)  # ← 传了

    # Brier Score decomposition (Murphy, exact identity) + raw empirical Brier
    brier, reliability, resolution, uncertainty = brier_parts(probs, labels)  # ← 漏传！

    # MCE
    max_ce = mce(probs, labels, n_bins)  # ← 传了
```

**论证**：

1. `compute_all_metrics` 接受 `n_bins` 参数，docstring 明确说明"分箱数量"。
2. 该参数被传给 `bootstrap_ece`（L765）和 `mce`（L771），但**唯独漏传给 `brier_parts`**（L768）。
3. 这是 P0-4 修复最直接的内部遗漏——修复了 `brier_parts` 签名，却未更新同文件内 `compute_all_metrics` 的调用。

**反例**：

```python
from src.utils.calibration import compute_all_metrics
import numpy as np
np.random.seed(42)
probs = np.random.rand(1000)
labels = (np.random.rand(1000) > 0.5).astype(float)

# 用户期望 n_bins=5 对所有指标生效
m5 = compute_all_metrics(probs, labels, n_bins=5, n_bootstrap=0)
m10 = compute_all_metrics(probs, labels, n_bins=10, n_bootstrap=0)

# ECE 用 5 bin vs 10 bin，应不同
assert m5['ece'] != m10['ece']  # ✅ 成立

# Brier reliability 也应不同（5 bin vs 10 bin）
# 但实际：brier_parts 用默认 10 bin，两者相同！
assert m5['brier_reliability'] == m10['brier_reliability']  # ❌ 意外成立——bug
```

**致命后果**：

`compute_all_metrics(n_bins=5)` 返回的字典中，`ece`/`mce` 用 5 bin 计算，但 `brier`/`brier_reliability`/`brier_resolution` 用 10 bin 计算。**同一函数返回的指标分箱数不一致**，破坏 ECE 与 Brier reliability 的语义可比性。这正是 P0-4 修复声称要解决的"分箱不一致"问题，但在 `compute_all_metrics` 内部仍然存在。

**裁决**：**致命**——P0-4 修复了 `brier_parts` 签名却未更新同文件内最直接的调用方，自相矛盾。

---

## 2. 严重攻击 (Severe)

### F3：E2 使用 N_BINS=15，与原始硬编码 10 不一致——静默行为变更

**位置**：`scripts/run_e2_ablation_discrimination.py` L131, L315

**攻击维度**：语义偏移 + 量级错误

**代码证据**：

`run_e2_ablation_discrimination.py` L131:
```python
N_BINS = 15                 # Brier reliability / ECE 评估分箱数（校准评估粒度）
```

L315:
```python
# 正方修补(P0-3): 显式传 n_bins=N_BINS，使 Brier reliability 分箱粒度可控
b_total, rel, res, unc = brier_parts(max_prob, correct, n_bins=N_BINS)  # n_bins=15
```

**论证**：

1. 原始 `brier_parts` 硬编码 10 bin（`np.linspace(0, 1, 11)`）。
2. P0-4 修复后默认值=10，向后兼容。
3. 但 E2 的 P0-3 修补显式传 `n_bins=N_BINS=15`，**与原始 10 bin 不同**。
4. 如果 E2 在 P0-3/P0-4 之前曾运行并产生缓存结果（用 10 bin），修复后重跑用 15 bin，**结果不可复现**。
5. Brier reliability 对分箱数敏感：bin 越多，每个 bin 内概率越均匀，reliability 越小（分箱误差减小）；bin 越少，reliability 越大。15 bin 的 reliability **系统性低于** 10 bin 的 reliability。

**反例**：

设 E2 之前用 10 bin 得到 `brier_reliability=0.05`，现在用 15 bin 得到 `brier_reliability=0.035`。消融实验的"discrimination 贡献"结论可能因 reliability 下降而改变显著性。如果论文已报告 10 bin 结果，修复后重跑得到 15 bin 结果，**已发表数据与新数据不一致**。

**裁决**：**严重**——静默行为变更，需文档化或统一 N_BINS=10。

---

### F4：跨实验分箱数不一致——Brier reliability 跨实验不可直接比较

**位置**：E2 L131 vs E3 L150 vs E4 L141 vs E1a/E1b（默认）

**攻击维度**：自相矛盾 + 量级错误

**代码证据**：

| 脚本 | 常量 | 值 | 传参方式 |
|------|------|----|---------|
| `run_e1a_l2_shift_full.py` | （无） | 10（默认） | 未传 n_bins |
| `run_e1b_loco_validation.py` | （无） | 10（默认） | 未传 n_bins |
| `run_e2_ablation_discrimination.py` | `N_BINS` | **15** | 显式传 |
| `run_e3_brier_dcr_ncv.py` | `N_BINS` | 10 | 显式传 |
| `run_e4_temperature_analysis.py` | `BRIER_N_BINS` | 10 | 显式传 |
| `run_e6_reliability_diagrams.py` | `N_BINS` | 10 | 不调用 brier_parts |

**论证**：

1. E2 用 15 bin，E3/E4/E1a/E1b 用 10 bin。
2. Brier reliability 的分箱数影响数值大小（见 F3），**不同分箱数的 reliability 不可直接比较**。
3. 如果论文跨实验比较 Brier reliability（如"E2 的消融 reliability 改善 vs E3 的 TS reliability 改善"），比较无效。
4. E4 的注释 L141 明确写 `BRIER_N_BINS = 10  # ... 与 calibration.brier_parts 默认一致`，说明开发者意识到需对齐默认值，但 E2 的 N_BINS=15 **未对齐**。

**反例**：

E2 报告 `delta_reliability=0.020`（15 bin），E3 报告 `delta_reliability=0.025`（10 bin）。研究者结论"E3 的 TS 改善优于 E2 的消融改善"——**无效**，因为分箱数不同导致 reliability 量纲不一致。需统一分箱数后才能比较。

**裁决**：**严重**——跨实验分箱数不一致，Brier reliability 跨实验比较无效。

---

### S1：无 n_bins 输入验证——n_bins≤0 静默返回无意义值

**位置**：`src/utils/calibration.py` L608, L614

**攻击维度**：边界失效 + 隐含假设

**代码证据**：

```python
def brier_parts(probs, labels, n_bins: int = 10):
    ...
    bins = np.linspace(0, 1, n_bins + 1)  # L608
    ...
    for i in range(n_bins):               # L614
        ...
    brier_total = reliability - resolution + uncertainty
    return float(brier_total), float(reliability), float(resolution), float(uncertainty)
```

**论证**：

1. **n_bins=0**：`np.linspace(0, 1, 1)`=[0.0]，`range(0)`=空循环。reliability=0.0, resolution=0.0, brier_total=uncertainty。**不崩溃，不警告，返回 (uncertainty, 0, 0, uncertainty)**——一个无意义但看似合法的结果。
2. **n_bins=-1**：`np.linspace(0, 1, 0)`=[]，`range(-1)`=空循环。同上，返回 (uncertainty, 0, 0, uncertainty)。**不崩溃**。
3. **n_bins=-5**：`np.linspace(0, 1, -4)`=[]，`range(-5)`=空循环。同上。
4. 无任何 `if n_bins < 1: raise ValueError` 验证。

**反例**：

```python
import numpy as np
from src.utils.calibration import brier_parts

probs = np.array([0.3, 0.7, 0.8])
labels = np.array([0, 1, 1])

# n_bins=0：不崩溃，返回无意义值
b, r, s, u = brier_parts(probs, labels, n_bins=0)
# b = u = 0.555*0.444 = 0.247, r = 0, s = 0
# 看似合法的浮点数，但完全无意义

# n_bins=-1：同样不崩溃
b, r, s, u = brier_parts(probs, labels, n_bins=-1)
# 同上
```

**裁决**：**严重**——n_bins≤0 静默返回无意义值，无崩溃无警告，违反 fail-fast 原则。

---

### S2：n_bins=0 时 brier_total=uncertainty——语义错误但无告警

**位置**：`src/utils/calibration.py` L608-631

**攻击维度**：边界失效

**论证**：

当 n_bins=0 时：
- `bins = np.linspace(0, 1, 1)` = [0.0]
- `for i in range(0):` — 循环不执行
- `reliability = 0.0`, `resolution = 0.0`
- `brier_total = 0 - 0 + uncertainty = uncertainty`
- 返回 `(uncertainty, 0.0, 0.0, uncertainty)`

这满足 Murphy 恒等式 `Brier = REL - RES + UNC`（按构造），但语义上：
- reliability=0 意味着"完美校准"——错误，实际未做任何分箱
- resolution=0 意味着"无分辨能力"——错误，实际未做任何分箱
- brier_total=uncertainty 意味着"Brier 等于 base rate 方差"——这是"无信息预测"的 Brier，但实际有预测

**反例**：研究者误传 `n_bins=0`（如配置文件错误或变量未初始化），得到 reliability=0，误以为"模型完美校准"。实际是 bug，但无任何告警。

**裁决**：**严重**——退化情况静默返回语义错误值。

---

### S3：测试因 F2 而失效——test_brier_parts 无法捕获 compute_all_metrics 漏传 n_bins

**位置**：`tests/test_model.py` L188-198

**攻击维度**：隐含假设 + 逻辑断链

**代码证据**：

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

**论证**：

1. 测试通过 `compute_all_metrics(n_bins=5)` 间接测试 `brier_parts`。
2. 但因 F2，`compute_all_metrics` 不将 `n_bins=5` 传给 `brier_parts`，实际用默认 10 bin。
3. 测试的 Murphy 恒等式断言 `total == brier` 对任何 n_bins 都成立（按构造），**无法区分 5 bin 还是 10 bin**。
4. 测试的 `abs(brier_raw - brier) < 0.1` 断言对 10 bin 和 5 bin 都可能成立（阈值宽松）。
5. **测试无法检测 F2 bug**——即使 `compute_all_metrics` 漏传 n_bins，测试仍通过。

**反例**：修复 F2（在 L768 添加 `n_bins=n_bins`）后，`compute_all_metrics(n_bins=5)` 的 brier 用 5 bin，`brier_raw - brier` 可能 >0.1（5 bin 分箱误差更大），测试**反而失败**。即测试不仅无法捕获 bug，还会阻碍正确修复。

**裁决**：**严重**——测试无效，且可能阻碍 F2 的正确修复。

---

## 3. 轻微攻击 (Minor)

### M1：E6 不调用 brier_parts——任务要求检查 E6 是多余

**位置**：`scripts/run_e6_reliability_diagrams.py`

**论证**：

`grep brier_parts run_e6_reliability_diagrams.py` 无结果。E6 有自己的 `compute_reliability_bins` 函数（L132），用 `np.linspace(0.0, 1.0, n_bins + 1)` 分箱，不调用 `brier_parts`。任务要求检查 E6 的 brier_parts 调用是多余，但修复覆盖声明提到 E6 也不准确。

**裁决**：**轻微**——不影响修复正确性，但覆盖声明不精确。

---

### M2：n_bins=浮点数时崩溃——类型注解无运行时检查

**位置**：`src/utils/calibration.py` L614

**论证**：

`n_bins: int = 10` 类型注解为 int，但无运行时检查。若传 `n_bins=10.5`：
- `np.linspace(0, 1, 11.5)` — numpy 可能接受（转 int=11）或抛 TypeError（取决于版本）
- `range(10.5)` — **必然抛 TypeError**: `'float' object cannot be interpreted as an integer`

错误信息不直观，未在函数入口处显式检查类型。

**裁决**：**轻微**——崩溃但错误信息不友好。

---

### M3：E1b 注释代码也未传 n_bins

**位置**：`scripts/run_e1b_loco_validation.py` L585

**代码证据**：

```python
#   ncv = brier_parts(raw_mp, raw_correct)[1] - brier_parts(cal_mp, cal_correct)[1]
```

**论证**：

L585 是注释代码（说明 NCV 的定义），也未传 n_bins。虽是注释不影响运行，但若未来取消注释，会重复 F1 的遗漏。应清理或补全。

**裁决**：**轻微**——注释代码，不影响运行，但维护风险。

---

## 4. 边界条件系统测试

### 4.1 n_bins=1（单 bin）

**行为**：`np.linspace(0, 1, 2)`=[0.0, 1.0]，`range(1)`=[0]。i=0 == n_bins-1=0，mask = (probs >= 0) & (probs <= 1) = 全 True。所有样本在一个 bin。
- reliability = (avg_prob - avg_label)²
- resolution = (avg_label - base_rate)² = 0（因 avg_label = base_rate）
- brier_total = reliability + uncertainty

**裁决**：✅ 正确处理，数学上合理（单 bin 退化为全局校准误差）。

### 4.2 n_bins=100（多 bin）

**行为**：100 个 bin，每个 bin 样本少。空 bin 被 `if mask.sum() == 0: continue` 跳过。无 NaN/inf。

**裁决**：✅ 不崩溃，但统计上 reliability/resolution 估计噪声大（每 bin 样本少）。这是统计问题非代码 bug。

### 4.3 n_bins=0（见 S2）

**裁决**：❌ 静默返回无意义值，无告警。

### 4.4 n_bins=-1（见 S1）

**裁决**：❌ 静默返回无意义值，无告警。

### 4.5 概率恰好=1.0

**行为**：i == n_bins-1 时 mask = (probs >= bins[i]) & (probs <= bins[i+1])，1.0 被包含。i < n_bins-1 时 mask 用 `<`，1.0 不被包含。**正确处理**。

**裁决**：✅ `i == n_bins - 1` 与原始 `i == 9` 在 n_bins=10 时等价，边界处理正确。

---

## 5. 其他硬编码 bin 数量审查

对 `calibration.py` 全文件审查分箱相关函数：

| 函数 | 行号 | n_bins 参数 | 硬编码? | 备注 |
|------|------|------------|--------|------|
| `ece()` | L199 | ✅ `n_bins: int = 10` | 否 | 已支持 |
| `smooth_ece()` | L246 | ❌ 无（用 bandwidth） | N/A | 核平滑，无分箱 |
| `brier_parts()` | L586 | ✅ `n_bins: int = 10` | 否 | **P0-4 修复** |
| `brier_raw()` | L634 | N/A | N/A | 无分箱（经验均值） |
| `mce()` | L641 | ✅ `n_bins: int = 10` | 否 | 已支持 |
| `plot_reliability_diagram()` | L677 | ✅ `n_bins: int = 10` | 否 | 已支持 |
| `compute_all_metrics()` | L742 | ✅ `n_bins: int = 10` | 否 | 但**漏传给 brier_parts**（F2） |
| `bootstrap_ece()` | L520 | ✅ `n_bins: int = 10` | 否 | 正确传给 ece |

**裁决**：`brier_parts` 是最后一个硬编码 bin 数量的函数，P0-4 修复后**无其他硬编码残留**。但 `compute_all_metrics` 的漏传（F2）是新引入的内部不一致。

---

## 6. 7 维度攻击总结

| 维度 | 发现攻击点 | 严重程度 |
|------|-----------|---------|
| **反例构造** | F2（compute_all_metrics(n_bins=5) 仍用 10 bin）、S2（n_bins=0 返回无意义值） | 致命 + 严重 |
| **逻辑断链** | F1（5 处调用方遗漏）、S3（测试无法捕获 F2） | 致命 + 严重 |
| **隐含假设** | F1（默认值兼容是脆弱巧合）、S1（无输入验证） | 致命 + 严重 |
| **边界失效** | S1（n_bins≤0）、S2（n_bins=0 语义错误）、M2（浮点 n_bins 崩溃） | 严重 + 轻微 |
| **自相矛盾** | F2（compute_all_metrics 内部不一致）、F4（跨实验分箱数不一致） | 致命 + 严重 |
| **量级错误** | F3（15 vs 10 bin 静默变更）、F4（跨实验不可比） | 严重 |
| **语义偏移** | F2（n_bins 语义未贯穿）、F3（E2 行为变更）、M1（E6 覆盖声明不精确） | 致命 + 严重 + 轻微 |

**全部 7 个维度均发现有效攻击点**，无"未发现可攻击点"的维度。

---

## 7. 修复建议（反方提出的最小修补）

按优先级排序：

1. **[致命 F2]** `calibration.py` L768：`brier_parts(probs, labels)` → `brier_parts(probs, labels, n_bins=n_bins)`
2. **[致命 F1]** E1a L159、E1b L552/553/593/594：显式传 `n_bins=10`（或定义模块级常量 `BRIER_N_BINS = 10` 并引用）
3. **[严重 S1/S2]** `brier_parts` 开头加：`if not isinstance(n_bins, int) or n_bins < 1: raise ValueError(f"n_bins must be a positive integer, got {n_bins}")`
4. **[严重 F3/F4]** 统一跨实验分箱数：E2 的 `N_BINS=15` 改为 10，或在论文中显式文档化"E2 用 15 bin，E3/E4 用 10 bin，跨实验比较需重算"
5. **[严重 S3]** 测试中直接调用 `brier_parts(probs, labels, n_bins=5)` 并断言结果与 `n_bins=10` 不同
6. **[轻微]** 清理 E1b L585 注释代码；修正覆盖声明中 E6 的描述

---

## 8. 最终裁决

**P0-4 修复的核心变更（brier_parts 签名 + 硬编码替换）技术正确**，向后兼容性成立（默认值=原始硬编码=10），边界处理（i == n_bins - 1）与原始等价。

**但修复的覆盖范围存在两个致命缺口**（F1: 5 处调用方遗漏 + F2: compute_all_metrics 内部漏传），且引入新的跨实验不一致风险（F3/F4: E2 用 15 bin vs 其他用 10 bin）。测试（S3）因 F2 而失效，无法提供安全网。

**裁决**：**P0-4 修复不完整，需补丁修复 F1/F2 后方可视为完成**。当前状态：核心签名修复正确，但调用方覆盖和内部一致性存在致命遗漏。
