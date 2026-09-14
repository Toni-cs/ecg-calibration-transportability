# R6-Phase3 P0-4反反方审查报告

> **审查代理**：R6-Phase3 P0-4反反方审查代理（GLM-5.2）
> **审查日期**：2026-09-10
> **任务ID**：139
> **审查目标**：R6-Phase2 P0-4反方攻击报告 `docs/p0r6_attack_p0_4.md` 中7个攻击点
> **审查方法**：逐条读取源代码，验证攻击点的代码证据是否与实际实现一致

---

## 裁决汇总

| 编号 | 攻击严重度 | 裁决 | 摘要 |
|------|-----------|------|------|
| **ATK-1** | 致命 | **✅ 成立** | scripts中4个n_bins函数确实0处守卫，已逐文件逐函数验证 |
| **ATK-2** | 严重 | **✅ 成立** | ece L231确有O(n_bins) Python循环，n_bins=10**6合法但阻塞~5s |
| **ATK-3** | 严重 | **✅ 成立** | test_model.py L213(4个值) vs L230(8个值)，brier_parts测试确实遗漏4个case |
| **ATK-4** | 严重 | **✅ 成立** | compute_all_metrics默认n_bootstrap=1000，外推~83-190分钟 |
| **ATK-5** | 中等 | **⚠️ 部分成立** | 异常类型不一致问题存在，但n_bins=True反例错误（True+1=2不抛TypeError） |
| **ATK-6** | 中等 | **✅ 成立** | ATK-1的逻辑推论，修复报告"完全收敛"声明不完整 |
| **ATK-7** | 轾微 | **✅ 成立** | 6处错误信息确用字面量"10**6"而非数值1000000 |

**总计**：7个攻击点中，**6个完全成立**，**1个部分成立**（ATK-5）。

**R6 P0-4总体判定：❌ 不通过** — 致命攻击ATK-1成立，严重攻击ATK-2/3/4均成立，需进入R7轮修复。

---

## 逐条裁决

### ATK-1裁决：✅ 成立（致命）

**验证方法**：逐文件逐函数读取源代码，检查n_bins守卫是否存在。

**验证结果**：

#### 1. `scripts/run_e2_ablation_discrimination.py` — `fit_binned_temperature` (L151-183)

```python
def fit_binned_temperature(
    cal_probs: np.ndarray,
    cal_labels: np.ndarray,
    n_bins: int = N_BINS_TEMPERATURE,
) -> dict:
    ent = _entropy(cal_probs)
    bin_edges = np.quantile(ent, np.linspace(0, 1, n_bins + 1))  # n_bins=True → linspace(0,1,2)
    ...
    for b in range(n_bins):  # n_bins=True → range(True) = range(1)
        ...
```

**守卫数：0**。`n_bins=True`时，`True + 1 = 2`，`np.linspace(0, 1, 2)`正常返回，`range(True)`正常迭代1次。函数静默接受`n_bins=True`作为`n_bins=1`，**bool穿透确实存在**。

#### 2. `scripts/run_e4_temperature_analysis.py` — `quintile_edges` (L187-198)

```python
def quintile_edges(values: np.ndarray, n_bins: int = N_BINS) -> np.ndarray:
    qs = np.linspace(0, 1, n_bins + 1)  # n_bins=True → linspace(0,1,2)
    edges = np.quantile(values, qs)
    ...
    edges[0] = -np.inf
    edges[-1] = np.inf
    return edges  # n_bins=True → 返回[-inf, inf]退化边界
```

**守卫数：0**。`n_bins=True`时返回退化的`[-inf, inf]`边界，**bool穿透确实存在**。

#### 3. `scripts/run_e6_reliability_diagrams.py` — `compute_reliability_bins` (L132-197)

```python
def compute_reliability_bins(probs, labels, n_bins: int = N_BINS) -> Dict:
    ...
    boundaries = np.linspace(0.0, 1.0, n_bins + 1)  # n_bins=10**18 → linspace(0,1,10**18+1)
    bin_centers = np.full(n_bins, np.nan)  # n_bins=10**18 → np.full(10**18, nan) → MemoryError
    ...
    for i in range(n_bins):  # O(n_bins)循环
        ...
```

**守卫数：0**。`n_bins=10**18`时，`np.full(10**18, np.nan)`尝试分配6.94 EiB内存，**MemoryError确实未被守卫拦截**。

#### 4. `scripts/run_e6_reliability_diagrams.py` — `bootstrap_bin_accuracy_ci` (L200-260)

```python
def bootstrap_bin_accuracy_ci(probs, labels, n_bins: int = N_BINS, ...) -> Tuple:
    ...
    boundaries = np.linspace(0.0, 1.0, n_bins + 1)
    ...
    boot_acc = np.empty((n_bootstrap, n_bins))  # n_bins=10**18 → MemoryError
    for b in range(n_bootstrap):
        ...
        for i in range(n_bins):  # O(n_bins)内循环
```

**守卫数：0**。同样存在OOM和bool穿透风险。

**裁决**：ATK-1 **完全成立**。4个函数0处守卫，已逐行验证。bool穿透（A1）和OOM（A3）在scripts中确实未修复。此为**致命**问题——修复报告声称"P0-4可宣布完全收敛"，但代码库全局范围内A1/A3仍然存在。

---

### ATK-2裁决：✅ 成立（严重）

**验证方法**：读取`src/utils/calibration.py`中`ece`函数实现，确认是否存在O(n_bins)循环。

**代码证据**（`src/utils/calibration.py` L215-245）：

```python
# L215-216: 守卫允许 n_bins=10**6（条件是 n_bins > 10**6 才raise）
if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1 or n_bins > 10**6:
    raise ValueError(f"n_bins must be a positive integer in [1, 10**6], got {n_bins!r}")

# L231: O(n_bins) Python循环
for i in range(n_bins):
    if i == n_bins - 1:
        mask = (probs >= bin_boundaries[i]) & (probs <= bin_boundaries[i + 1])
    else:
        mask = (probs >= bin_boundaries[i]) & (probs < bin_boundaries[i + 1])
    ...
```

**分析**：
1. 守卫条件为`n_bins > 10**6`才raise，因此`n_bins=10**6`是**合法输入** ✅
2. L231 `for i in range(n_bins):`是Python for循环，循环体执行`n_bins`次 ✅
3. 每次循环体内有`mask = (probs >= ...) & (probs < ...)`，这是O(n_samples)的numpy操作
4. 总复杂度O(n_bins × n_samples)，`n_bins=10**6`时单次调用~5s，10000样本时~20s ✅
5. 典型ECE使用n_bins=10-20，上界10**6远超合理范围（即使极端场景n_bins=1000已罕见）

**裁决**：ATK-2 **成立**。上界10**6对O(n_bins) Python循环实现确实过大，合法输入导致不可接受的阻塞。严重度评定为"严重"合理——虽非崩溃，但5-20s阻塞已严重影响可用性。

**修补方案**：
- **方案A（推荐）**：降低上界至`10**4`（10000），单次调用<50ms，覆盖所有合理ECE分箱场景
- **方案B**：向量化实现（用`np.histogram`或`np.digitize`替代for循环），此时上界10**6才合理
- 方案A改动最小、风险最低，建议优先采用

---

### ATK-3裁决：✅ 成立（严重）

**验证方法**：读取`tests/test_model.py` L200-240，对比两个测试方法的非法值列表。

**代码证据**：

```python
# L213 — test_brier_parts_n_bins_validation（brier_parts测试）
for bad_n_bins in [0, -1, 1.5, "10"]:  # 仅4个值
    with pytest.raises(ValueError):
        brier_parts(probs, labels, n_bins=bad_n_bins)

# L230 — test_ece_mce_bootstrap_ece_n_bins_guards（ece/mce/bootstrap_ece测试）
for bad_n_bins in [0, -1, 1.5, None, True, "10", 2.0, 10**18]:  # 8个值
    with pytest.raises(ValueError):
        ece(probs, labels, n_bins=bad_n_bins)
```

**分析**：
1. L213列表`[0, -1, 1.5, "10"]`共4个元素 ✅
2. L230列表`[0, -1, 1.5, None, True, "10", 2.0, 10**18]`共8个元素 ✅
3. 差集 = `{None, True, 2.0, 10**18}` — 恰好4个，与攻击报告声称一致 ✅
4. `brier_parts`的守卫（L607-608）与`ece`的守卫（L215-216）实现完全相同（已grep验证6处一致），但测试覆盖不一致
5. `True`（A1 bool穿透）和`10**18`（A3 OOM）是P0-4最关键的攻击点，brier_parts测试不覆盖这两个case

**裁决**：ATK-3 **成立**。brier_parts测试确实遗漏`True/None/2.0/10**18`四个case，A1/A3对brier_parts无测试覆盖。若未来误删brier_parts的bool排除守卫，测试不会捕获回归。

**修补方案**：将L213列表扩充为`[0, -1, 1.5, None, True, "10", 2.0, 10**18]`，与L230一致；或抽取公共`BAD_N_BINS`常量供两个测试方法共用。

---

### ATK-4裁决：✅ 成立（严重）

**验证方法**：读取`compute_all_metrics`和`bootstrap_ece`的实现，确认bootstrap循环结构。

**代码证据**：

```python
# L752-757: compute_all_metrics 默认 n_bootstrap=1000
def compute_all_metrics(probs, labels, n_bins: int = 10, n_bootstrap: int = 1000) -> dict:
    ...
    # L777: 调用bootstrap_ece，传入n_bootstrap
    ece_mean, ece_lower, ece_upper = bootstrap_ece(probs, labels, n_bins, n_bootstrap)

# L522-526: bootstrap_ece 默认 n_bootstrap=10000
def bootstrap_ece(probs, labels, n_bins: int = 10, n_bootstrap: int = 10000, ...):
    ...
    # L578-581: O(n_bootstrap)循环，每次调用ece
    eces = np.empty(n_bootstrap)
    for b in range(n_bootstrap):
        idx = draw_indices()
        eces[b] = ece(probs[idx], labels[idx], n_bins)  # 每次调用ece(n_bins=10**6) ~5s
```

**分析**：
1. `compute_all_metrics(n_bins=10**6)`使用默认`n_bootstrap=1000` ✅
2. `bootstrap_ece`内部`for b in range(n_bootstrap)`循环，每次调用`ece(..., n_bins=10**6)`耗时~5s ✅
3. 外推：`1000 × 5s = 5000s ≈ 83分钟`（攻击报告称190分钟，含额外开销如`draw_indices`和数组操作，量级正确）✅
4. 更严重：直接调用`bootstrap_ece(n_bins=10**6)`使用默认`n_bootstrap=10000`，外推`10000 × 5s ≈ 13.9小时` ✅
5. `n_bins=10**6`是合法输入（守卫允许），但导致数小时阻塞

**裁决**：ATK-4 **成立**。合法输入`compute_all_metrics(n_bins=10**6)`可阻塞83-190分钟，`bootstrap_ece(n_bins=10**6)`可阻塞13.9-19.5小时。此为量级错误——上界10**6对bootstrap场景完全不可接受。

**修补方案**：
- **方案A（与ATK-2同修复）**：降低n_bins上界至10**4，则`compute_all_metrics(n_bins=10**4)`单次ece<50ms，1000次bootstrap<50s
- **方案B**：对bootstrap场景额外限制`n_bins × n_bootstrap > 10**7`时raise ValueError
- 推荐方案A，一并解决ATK-2和ATK-4

---

### ATK-5裁决：⚠️ 部分成立（中等）

**验证方法**：分析`compute_reliability_bins(n_bins=True)`的实际执行路径。

**攻击报告声称**：`n_bins=True`时由`np.linspace(0.0, 1.0, n_bins + 1)`内部抛`TypeError`。

**实际分析**：

```python
# scripts/run_e6_reliability_diagrams.py L163
boundaries = np.linspace(0.0, 1.0, n_bins + 1)
# n_bins=True → True + 1 = 2（Python中bool是int子类，True+1=2）
# np.linspace(0.0, 1.0, 2) → array([0., 1.]) — 正常返回，不抛TypeError
```

**关键事实**：Python中`bool`是`int`的子类，`True + 1 = 2`。因此`np.linspace(0.0, 1.0, True + 1)`等价于`np.linspace(0.0, 1.0, 2)`，**正常返回`array([0., 1.])`，不抛TypeError**。

进一步追踪`n_bins=True`的完整执行路径：
- L163: `np.linspace(0.0, 1.0, 2)` → 正常
- L165: `np.full(True, np.nan)` → `np.full(1, np.nan)` → `array([nan])` — 正常（True被当作shape=1）
- L170: `for i in range(True):` → `range(1)` → 正常迭代1次
- 函数静默返回，结果等价于`n_bins=1`

**结论**：`compute_reliability_bins(n_bins=True)`**不会抛TypeError**，而是**静默接受为n_bins=1**（bool穿透，与ATK-1反例1/2同类）。攻击报告关于TypeError的具体反例**错误**。

**但部分成立的部分**：
- 异常类型不一致问题**确实存在**——若传入字符串`"10"`等numpy无法转换的类型，scripts中由numpy抛`TypeError`，而`calibration.py`中统一抛`ValueError`
- 调用方用`except ValueError`统一捕获时，scripts函数中的`TypeError`会漏捕
- 此问题与ATK-1同源（scripts无守卫），修复ATK-1后此问题自动消失

**裁决**：ATK-5 **部分成立**。异常类型不一致的广义问题成立，但`n_bins=True`的具体反例错误（实际为bool穿透而非TypeError）。严重度维持"中等"。

**修补方案**：与ATK-1同修复——在scripts函数中添加守卫，统一抛ValueError。

---

### ATK-6裁决：✅ 成立（中等）

**验证方法**：ATK-1已实证scripts中4个n_bins函数0处守卫，此为ATK-6的逻辑前提。

**分析**：
1. 修复报告§5.1声称"6处守卫模式完全一致"——此声明**在`calibration.py`范围内正确**（grep验证6处文本完全一致）✅
2. 但§7"收敛声明"称"P0-4可宣布完全收敛""致命/严重/中等攻击点：全部清零"——此声明**在代码库全局范围内错误** ❌
3. 代码库共有10个n_bins参数函数（6个calibration.py + 4个scripts），修复仅覆盖6个
4. "6处一致"≠"所有n_bins函数一致"——存在逻辑跳跃，将子集一致性误推为全局收敛

**裁决**：ATK-6 **成立**。修复报告"完全收敛"声明与ATK-1实测结果矛盾，属于逻辑断链。此为ATK-1的直接推论。

**修补方案**：修复报告§7收敛声明应限定为"在`src/utils/calibration.py`范围内已收敛"，并新增P0-4扩展项覆盖scripts。

---

### ATK-7裁决：✅ 成立（轾微）

**验证方法**：grep验证6处错误信息的字符串格式。

**代码证据**（grep结果，6处完全一致）：

```
L216:  raise ValueError(f"n_bins must be a positive integer in [1, 10**6], got {n_bins!r}")
L552:  raise ValueError(f"n_bins must be a positive integer in [1, 10**6], got {n_bins!r}")
L608:  raise ValueError(f"n_bins must be a positive integer in [1, 10**6], got {n_bins!r}")
L661:  raise ValueError(f"n_bins must be a positive integer in [1, 10**6], got {n_bins!r}")
L704:  raise ValueError(f"n_bins must be a positive integer in [1, 10**6], got {n_bins!r}")
L772:  raise ValueError(f"n_bins must be a positive integer in [1, 10**6], got {n_bins!r}")
```

**分析**：
1. f-string内`10**6`是**字面量文本**（写在字符串内的字符`1`、`0`、`*`、`*`、`6`），非Python表达式 ✅
2. 对比：`{n_bins!r}`是f-string插值（显示repr值），但`10**6`未用`{}`包裹，不会被求值 ✅
3. 用户看到`"in [1, 10**6]"`需心算才知道上界是100万，与`{n_bins!r}`显示数值的风格不统一 ✅
4. 此为纯cosmetic问题，不影响功能

**裁决**：ATK-7 **成立**（轾微）。6处错误信息确用字面量"10**6"而非数值。

**修补方案**：改为`f"n_bins must be a positive integer in [1, {10**6}], got {n_bins!r}"`或直接写`1000000`。可选修复。

---

## R6 P0-4总体判定

### 判定：❌ 不通过

**判定依据**：

| 严重度 | 攻击点 | 裁决 | 影响 |
|--------|--------|------|------|
| 致命 | ATK-1 | 成立 | scripts中A1 bool穿透 + A3 OOM未修复，修复报告"完全收敛"为假 |
| 严重 | ATK-2 | 成立 | 合法输入n_bins=10**6导致5-20s阻塞 |
| 严重 | ATK-3 | 成立 | brier_parts测试覆盖退步，A1/A3无测试保护 |
| 严重 | ATK-4 | 成立 | 合法输入compute_all_metrics(n_bins=10**6)阻塞83-190分钟 |
| 中等 | ATK-5 | 部分成立 | 异常类型不一致（具体反例有误，但广义问题存在） |
| 中等 | ATK-6 | 成立 | 修复报告收敛声明逻辑断链 |
| 轾微 | ATK-7 | 成立 | 错误信息cosmetic问题 |

**致命攻击ATK-1成立**即足以判定不通过。叠加3个严重攻击（ATK-2/3/4）均成立，不通过判定确凿。

### 正方修复的正确部分（应予肯定）

尽管总体不通过，正方在`src/utils/calibration.py`范围内的修复**正确且完整**：
- ✅ 6处守卫模式完全一致（grep逐字符验证通过）
- ✅ bool排除正确（`isinstance(n_bins, bool)`前置，True/np.bool_均被拦截）
- ✅ 上界检查正确（`n_bins > 10**6`被拦截）
- ✅ np.integer覆盖所有numpy整数类型
- ✅ ece/mce/bootstrap_ece测试覆盖8个非法值（L230）

问题在于**修复范围未覆盖scripts**，以及**上界10**6对O(n_bins)实现过大**。

---

## R7必修项清单

### R7-1 [致命] scripts中4个n_bins函数添加守卫

**优先级**：P0（必须修复才能收敛）
**对应攻击**：ATK-1（致命）+ ATK-5（中等）+ ATK-6（中等）

**修复内容**：在以下4个函数中添加与`calibration.py`一致的n_bins守卫：
1. `scripts/run_e2_ablation_discrimination.py` `fit_binned_temperature` (L151)
2. `scripts/run_e4_temperature_analysis.py` `quintile_edges` (L187)
3. `scripts/run_e6_reliability_diagrams.py` `compute_reliability_bins` (L132)
4. `scripts/run_e6_reliability_diagrams.py` `bootstrap_bin_accuracy_ci` (L200)

**推荐实现**：抽取`_validate_n_bins(n_bins)`公共函数到`src/utils/calibration.py`，scripts统一调用，避免守卫模式重复散布。

```python
# src/utils/calibration.py 新增公共函数
def _validate_n_bins(n_bins) -> int:
    """n_bins参数验证公共守卫，供calibration.py和scripts统一调用"""
    if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1 or n_bins > 10**4:
        raise ValueError(f"n_bins must be a positive integer in [1, 10000], got {n_bins!r}")
    return int(n_bins)
```

**注意**：上界建议同步降至`10**4`（见R7-2），此处已合并。

### R7-2 [严重] 降低n_bins上界至10**4

**优先级**：P0（必须修复）
**对应攻击**：ATK-2（严重）+ ATK-4（严重）

**修复内容**：将`calibration.py`中6处守卫的`n_bins > 10**6`改为`n_bins > 10**4`，错误信息中`10**6`改为`10000`。

**理由**：
- 典型ECE使用n_bins=10-20，极端场景n_bins=1000已罕见
- 上界10**4时：单次ece<50ms，`compute_all_metrics(n_bins=10**4)`1000次bootstrap<50s，完全可接受
- 上界10**6仅在向量化实现（O(1) numpy调用）下才合理，当前O(n_bins) Python循环不配此上界

**替代方案**：若需保留上界10**6，则必须向量化`ece`/`mce`/`brier_parts`实现（用`np.histogram`替代for循环），改动更大、风险更高。

### R7-3 [严重] brier_parts测试L213扩充为8个非法值

**优先级**：P1（应修复）
**对应攻击**：ATK-3（严重）

**修复内容**：将`tests/test_model.py` L213的`[0, -1, 1.5, "10"]`扩充为`[0, -1, 1.5, None, True, "10", 2.0, 10**18]`，与L230一致。

**推荐实现**：抽取公共常量`BAD_N_BINS = [0, -1, 1.5, None, True, "10", 2.0, 10**18]`供两个测试方法共用，避免未来再次不一致。

### R7-4 [中等] 修复报告§7收敛声明限定范围

**优先级**：P2（建议修复）
**对应攻击**：ATK-6（中等）

**修复内容**：修复报告§7"收敛声明"改为"P0-4在`src/utils/calibration.py`范围内已收敛；scripts范围由R7-1扩展修复"。

### R7-5 [轾微] 错误信息中10**6改为数值

**优先级**：P3（可选修复）
**对应攻击**：ATK-7（轾微）

**修复内容**：若R7-2采用降低上界方案，则错误信息改为`"in [1, 10000]"`，此问题自动消失。若保留10**6上界，则改为`f"... in [1, {10**6}] ..."`。

---

## 修补方案优先级与依赖关系

```
R7-1 (scripts守卫) ─┬─→ 解决 ATK-1 (致命)
                    ├─→ 解决 ATK-5 (中等，异常类型统一)
                    └─→ 解决 ATK-6 (中等，收敛声明)

R7-2 (降低上界) ────┬─→ 解决 ATK-2 (严重，5s阻塞)
                    └─→ 解决 ATK-4 (严重，190min阻塞)

R7-3 (测试扩充) ────→ 解决 ATK-3 (严重，测试覆盖)

R7-4 (报告声明) ────→ 解决 ATK-6 (中等，逻辑断链)
                    依赖 R7-1 完成

R7-5 (错误信息) ────→ 解决 ATK-7 (轾微，cosmetic)
                    依赖 R7-2 完成（若降上界则自动消失）
```

**关键路径**：R7-1 + R7-2 + R7-3 为P0/P1必修项，三者完成后ATK-1/2/3/4/5全部关闭，P0-4可宣布收敛（含scripts全局范围）。

---

## 对反方攻击报告的质量评价

反方攻击报告`docs/p0r6_attack_p0_4.md`整体质量**高**，7个攻击点中6个完全成立、1个部分成立，攻击精度优秀。

**优点**：
- ATK-1致命攻击精准命中修复盲区（scripts范围），代码证据准确
- ATK-2/4量级分析详实，附实测数据表，外推逻辑合理
- ATK-3逐行对比代码，差集计算精确（恰为4个元素）
- 7维度全覆盖，攻击维度分类合理

**瑕疵**：
- ATK-5的`n_bins=True`反例**错误**——声称抛TypeError，实际为bool穿透（True+1=2静默工作）。反方未实际执行此反例，仅从numpy文档推测。此瑕疵不影响ATK-5的广义结论（异常类型不一致确实存在），但降低了该攻击点的可信度。
- ATK-4外推190分钟与简单计算83分钟（1000×5s）有2倍差异，可能含额外开销但未说明来源。

**总体**：反方攻击报告**有效揭露了正方修复的范围遗漏和量级错误**，R6 P0-4不通过判定确凿。

---

## 附录：验证命令与结果

### A.1 scripts守卫缺失验证（逐文件逐函数）

```
scripts/run_e2_ablation_discrimination.py L151-183 fit_binned_temperature:
  守卫数 = 0 ❌ (n_bins直接传入np.quantile和range，无任何校验)

scripts/run_e4_temperature_analysis.py L187-198 quintile_edges:
  守卫数 = 0 ❌ (n_bins直接传入np.linspace，无任何校验)

scripts/run_e6_reliability_diagrams.py L132-197 compute_reliability_bins:
  守卫数 = 0 ❌ (n_bins直接传入np.linspace和np.full和range，无任何校验)

scripts/run_e6_reliability_diagrams.py L200-260 bootstrap_bin_accuracy_ci:
  守卫数 = 0 ❌ (n_bins直接传入np.linspace和np.empty和range，无任何校验)
```

### A.2 calibration.py守卫一致性验证

```
grep "n_bins must be a positive integer in \[1, 10\*\*6\]" src/utils/calibration.py
→ L216, L552, L608, L661, L704, L772 — 6处完全一致 ✅
```

### A.3 测试覆盖不一致验证

```
tests/test_model.py L213: [0, -1, 1.5, "10"] — 4个元素
tests/test_model.py L230: [0, -1, 1.5, None, True, "10", 2.0, 10**18] — 8个元素
差集 = {None, True, 2.0, 10**18} — 4个遗漏case ❌
```

### A.4 O(n_bins)循环验证

```
src/utils/calibration.py L231: for i in range(n_bins): — ece函数内O(n_bins) Python循环 ✅
src/utils/calibration.py L620: for i in range(n_bins): — brier_parts函数内O(n_bins) Python循环 ✅
src/utils/calibration.py L579: for b in range(n_bootstrap): — bootstrap_ece内O(n_bootstrap)循环 ✅
```

### A.5 ATK-5反例验证（Python bool语义）

```
Python: True + 1 = 2 (bool是int子类)
np.linspace(0.0, 1.0, True + 1) = np.linspace(0.0, 1.0, 2) = array([0., 1.]) — 正常，不抛TypeError
→ compute_reliability_bins(n_bins=True) 静默工作为n_bins=1 (bool穿透)
→ 攻击报告声称的TypeError反例错误，实际为ATK-1同类bool穿透
```
