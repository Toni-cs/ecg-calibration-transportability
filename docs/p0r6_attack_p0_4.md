# R6-Phase2 P0-4反方攻击报告

> **攻击代理**：R6-Phase2 P0-4反方挑刺代理（GLM-5.2）
> **攻击日期**：2026-09-10
> **任务ID**：136
> **攻击目标**：R6-Phase1 P0-4正方修复（task 133）
> **攻击范围**：`src/utils/calibration.py` 6处守卫 + `tests/test_model.py` 测试扩充
> **攻击维度**：7维度全扫（反例构造/逻辑断链/隐含假设/边界失效/自相矛盾/量级错误/语义偏移）

---

## 攻击点汇总

| 编号 | 维度 | 严重度 | 摘要 |
|------|------|--------|------|
| **ATK-1** | 隐含假设 + 边界失效 | **致命** | scripts中3个n_bins函数完全无守卫，A1 bool穿透+A3 OOM在scripts中未修复 |
| **ATK-2** | 量级错误 | **严重** | 上界10**6对O(n_bins)循环实现过大，合法输入导致5s阻塞；bootstrap场景外推19.5小时 |
| **ATK-3** | 自相矛盾 | **严重** | brier_parts测试L213仍用`[0,-1,1.5,"10"]`，遗漏True/None/2.0/10**18，A1/A3对brier_parts无测试覆盖 |
| **ATK-4** | 量级错误 | **严重** | compute_all_metrics(n_bins=10**6)默认n_bootstrap=1000外推190分钟阻塞 |
| **ATK-5** | 语义偏移 | **中等** | scripts中compute_reliability_bins(n_bins=True)抛TypeError而非ValueError，异常类型不一致 |
| **ATK-6** | 逻辑断链 | **中等** | 修复报告§5.1声称"6处守卫模式完全一致"但未验证scripts同源函数，修复范围声明不完整 |
| **ATK-7** | 语义偏移 | **轾微** | 错误信息中"10**6"为字面量字符串而非数值1000000，用户可能误解 |

**总计**：7个攻击点，其中致命1个、严重3个、中等2个、轾微1个

---

## 逐条攻击

### ATK-1：scripts中3个n_bins函数完全无守卫（A1 bool穿透 + A3 OOM未修复）

- **维度**：隐含假设 + 边界失效
- **严重度**：**致命**
- **攻击**：R6修复报告声称"已收敛""完全消除了P0-4的3个严重攻击点（A1 bool穿透 + A3 无上界OOM + A5 测试覆盖退步）"，但修复仅覆盖`src/utils/calibration.py`的6处守卫。代码库中`scripts/`目录下有3个文件包含独立`n_bins`参数的函数，**完全没有任何n_bins守卫**，A1 bool穿透和A3 OOM攻击在这些函数中**完全未修复**。

**反例1（bool穿透，A1未修复）**：
```python
# scripts/run_e2_ablation_discrimination.py fit_binned_temperature
from scripts.run_e2_ablation_discrimination import fit_binned_temperature
probs = np.array([[0.3, 0.7], [0.5, 0.5], [0.7, 0.3]])
labels = np.array([0, 1, 1])
fit_binned_temperature(probs, labels, n_bins=True)  # NOT RAISED — 静默接受为n_bins=1
```
实测结果：`fit_binned_temperature(n_bins=True): NOT RAISED (BUG!)` — bool穿透**仍然存在**。

**反例2（bool穿透，A1未修复）**：
```python
# scripts/run_e4_temperature_analysis.py quintile_edges
from scripts.run_e4_temperature_analysis import quintile_edges
quintile_edges(np.array([1.0, 2.0, 3.0]), n_bins=True)  # NOT RAISED, returns [-inf, inf]
```
实测结果：`quintile_edges(n_bins=True): NOT RAISED, result=[-inf  inf] (BUG!)` — bool穿透**仍然存在**，且返回退化的`[-inf, inf]`边界。

**反例3（OOM未防止，A3未修复）**：
```python
# scripts/run_e6_reliability_diagrams.py compute_reliability_bins
from scripts.run_e6_reliability_diagrams import compute_reliability_bins
compute_reliability_bins(probs, labels, n_bins=10**18)  # MemoryError: Unable to allocate 6.94 EiB
```
实测结果：`compute_reliability_bins(n_bins=10**18): MemoryError: Unable to allocate 6.94 EiB for an array with shape (1000000000000000000,)` — OOM**未被守卫拦截**，直接崩溃。

- **代码证据**：
  - `scripts/run_e2_ablation_discrimination.py` L151-183 `fit_binned_temperature(n_bins=N_BINS_TEMPERATURE)` — 0处守卫
  - `scripts/run_e4_temperature_analysis.py` L187-195 `quintile_edges(n_bins=N_BINS)` — 0处守卫
  - `scripts/run_e6_reliability_diagrams.py` L132-197 `compute_reliability_bins(n_bins=N_BINS)` — 0处守卫
  - `scripts/run_e6_reliability_diagrams.py` L200-258 `bootstrap_bin_accuracy_ci(n_bins=N_BINS)` — 0处守卫
  - grep验证：3个scripts文件中`isinstance(n_bins.*raise|n_bins.*<.*1.*raise|n_bins.*>.*raise`匹配数=0
- **修复建议**：
  1. 在3个scripts文件的4个函数中复制`src/utils/calibration.py`的守卫模式
  2. 或抽取`_validate_n_bins(n_bins)`公共函数到`src/utils/calibration.py`，scripts统一调用
  3. 修复报告§7"收敛声明"应改为"P0-4在`src/utils/calibration.py`范围内已收敛，scripts范围未覆盖"

---

### ATK-2：上界10**6对O(n_bins)循环实现过大，合法输入导致5秒阻塞

- **维度**：量级错误
- **严重度**：**严重**
- **攻击**：守卫上界设为`n_bins > 10**6`，即`n_bins=10**6`是**合法输入**。但`ece`/`mce`/`brier_parts`/`plot_reliability_diagram`的实现使用Python for循环`for i in range(n_bins)`，复杂度为O(n_bins)。`n_bins=10**6`时循环体执行100万次，实测阻塞4.8秒。

**反例（合法输入导致5秒阻塞）**：
```python
from src.utils.calibration import ece
import numpy as np
import time
probs = np.array([0.3, 0.5, 0.7])
labels = np.array([0, 1, 1])
t0 = time.time()
ece(probs, labels, n_bins=10**6)  # 合法输入，但阻塞4.8秒
print(f'{time.time()-t0:.3f}s')  # 4.803s
```

**量级实测**：
| n_bins | 耗时 | 倍率 |
|--------|------|------|
| 100 | 0.000s | — |
| 1,000 | 0.005s | — |
| 10,000 | 0.048s | 9.6× |
| 100,000 | 0.474s | 9.9× |
| 1,000,000 | 4.800s | 10.1× |

复杂度严格O(n_bins)，每10×n_bins耗时约10×。`n_bins=10**6`时单次调用4.8s，已超出交互响应阈值（通常<1s）。

**更严重场景**：`n_bins=10**6` + 10000样本时耗时19.8s（O(n_bins × n_samples)的mask计算）：
```python
probs = np.random.rand(10000)
labels = (np.random.rand(10000) > 0.5).astype(float)
ece(probs, labels, n_bins=10**6)  # 19.814s
```

- **代码证据**：`src/utils/calibration.py` L231 `for i in range(n_bins):` — O(n_bins) Python循环
- **修复建议**：
  1. **降低上界**：将上界从`10**6`降至`10**4`（10000），单次调用<50ms，覆盖所有合理ECE分箱场景（典型n_bins=10-20，极端n_bins=1000）
  2. **向量化实现**：用`np.histogram`或`np.digitize`替代for循环，将O(n_bins) Python循环降为O(1) numpy调用，此时上界10**6才合理
  3. 当前实现下上界10**6是**量级错误**——允许的合法输入会导致不可接受的阻塞

---

### ATK-3：brier_parts测试覆盖退步（A1/A3对brier_parts无测试覆盖）

- **维度**：自相矛盾
- **严重度**：**严重**
- **攻击**：R6修复报告§4声称"A5已关闭：测试扩充为[0, -1, 1.5, None, True, "10", 2.0, 10**18]，覆盖bool/str/float/极大值/负数"。但该扩充**仅应用于`test_ece_mce_bootstrap_ece_n_bins_guards`（L230）**，另一个同样测试n_bins守卫的方法`test_brier_parts_n_bins_validation`（L213）**仍使用旧列表`[0, -1, 1.5, "10"]`**，遗漏了`None, True, 2.0, 10**18`四个关键case。

**代码对比**：
```python
# tests/test_model.py L213 — brier_parts测试（未扩充）
for bad_n_bins in [0, -1, 1.5, "10"]:  # 仅4个，遗漏True/None/2.0/10**18
    with pytest.raises(ValueError):
        brier_parts(probs, labels, n_bins=bad_n_bins)

# tests/test_model.py L230 — ece/mce/bootstrap_ece测试（已扩充）
for bad_n_bins in [0, -1, 1.5, None, True, "10", 2.0, 10**18]:  # 8个
    with pytest.raises(ValueError):
        ece(probs, labels, n_bins=bad_n_bins)
```

**自相矛盾点**：
1. `brier_parts`的守卫（L607-608）与`ece`的守卫（L215-216）**完全相同**（已由grep验证6处一致）
2. 但`brier_parts`的测试**不覆盖**A1（True）和A3（10**18）这两个最关键的攻击点
3. 修复报告声称A5（测试覆盖退步）已关闭，但A5对`brier_parts`**仍然存在**——测试覆盖退步未完全修复

**实测验证**：brier_parts守卫本身工作正常（True/10**18都raise ValueError），但**测试不验证这一点**——若未来有人误删brier_parts的bool排除，测试不会捕获回归。

- **代码证据**：`tests/test_model.py` L213 `[0, -1, 1.5, "10"]` vs L230 `[0, -1, 1.5, None, True, "10", 2.0, 10**18]`
- **修复建议**：将L213的列表也扩充为`[0, -1, 1.5, None, True, "10", 2.0, 10**18]`，与L230一致；或抽取公共`BAD_N_BINS`常量供两个测试方法共用

---

### ATK-4：compute_all_metrics(n_bins=10**6)默认n_bootstrap=1000外推190分钟阻塞

- **维度**：量级错误
- **严重度**：**严重**
- **攻击**：`compute_all_metrics`内部调用`bootstrap_ece(probs, labels, n_bins, n_bootstrap)`（L777），默认`n_bootstrap=1000`。每次bootstrap迭代调用`ece(..., n_bins=10**6)`耗时约5s，1000次迭代外推`1000 × 5s = 5000s ≈ 83分钟`。实测`n_bootstrap=2`耗时22.8s，外推`n_bootstrap=1000`为**189.9分钟**。

**反例（合法输入导致3小时阻塞）**：
```python
from src.utils.calibration import compute_all_metrics
import numpy as np
probs = np.array([0.3, 0.5, 0.7])
labels = np.array([0, 1, 1])
# 合法调用，但会阻塞约190分钟（3.2小时）
compute_all_metrics(probs, labels, n_bins=10**6)  # n_bootstrap默认1000
```

**更严重场景**：`bootstrap_ece`默认`n_bootstrap=10000`，`n_bins=10**6`时外推`10000 × 5s = 50000s ≈ 13.9小时`。实测`n_bootstrap=2`耗时14.0s，外推`n_bootstrap=10000`为**19.5小时**。

**量级错误分析**：
| 函数 | n_bins | n_bootstrap | 实测/外推耗时 |
|------|--------|-------------|---------------|
| ece | 10**6 | — | 4.8s |
| bootstrap_ece | 10**6 | 2 | 14.0s |
| bootstrap_ece | 10**6 | 10000（默认） | **19.5小时** |
| compute_all_metrics | 10**6 | 2 | 22.8s |
| compute_all_metrics | 10**6 | 1000（默认） | **190分钟** |

- **代码证据**：`src/utils/calibration.py` L777 `bootstrap_ece(probs, labels, n_bins, n_bootstrap)` + L579 `for b in range(n_bootstrap):` + L581 `eces[b] = ece(probs[idx], labels[idx], n_bins)`
- **修复建议**：
  1. **降低n_bins上界**至10**4（与ATK-2相同修复）
  2. 或**对bootstrap场景额外限制n_bins**：bootstrap_ece/compute_all_metrics中`n_bins × n_bootstrap > 10**7`时raise ValueError
  3. 当前上界10**6使合法输入可阻塞数小时，属于**量级错误**

---

### ATK-5：scripts中compute_reliability_bins(n_bins=True)抛TypeError而非ValueError

- **维度**：语义偏移
- **严重度**：**中等**
- **攻击**：`scripts/run_e6_reliability_diagrams.py`的`compute_reliability_bins`无n_bins守卫，`n_bins=True`时由`np.linspace(0.0, 1.0, n_bins + 1)`内部抛`TypeError: expected a sequence of integers or a single integer, got 'True'`。这与`src/utils/calibration.py`中统一抛`ValueError`的语义**不一致**。

**反例（异常类型不一致）**：
```python
# src/utils/calibration.py — 抛ValueError
ece(probs, labels, n_bins=True)  # ValueError: n_bins must be a positive integer...

# scripts/run_e6_reliability_diagrams.py — 抛TypeError
compute_reliability_bins(probs, labels, n_bins=True)  # TypeError: expected a sequence of integers...
```

**语义偏移**：调用方若用`except ValueError`统一捕获n_bins非法输入，在scripts函数中会**漏捕**TypeError导致未处理异常上浮。修复报告§2.1强调"错误信息统一"为`ValueError`，但该统一**仅限于calibration.py内部**，scripts中异常类型仍为numpy内部抛出的TypeError。

- **代码证据**：`scripts/run_e6_reliability_diagrams.py` L163 `boundaries = np.linspace(0.0, 1.0, n_bins + 1)` — 无守卫，TypeError由numpy抛出
- **修复建议**：在scripts函数中添加与calibration.py相同的守卫，统一抛ValueError（与ATK-1修复相同）

---

### ATK-6：修复报告"6处守卫模式完全一致"声明不完整，未覆盖scripts同源函数

- **维度**：逻辑断链
- **严重度**：**中等**
- **攻击**：修复报告§5.1验证项"6处守卫模式完全一致"通过grep验证calibration.py内6处一致（✅），但该验证**逻辑断链**——只验证了calibration.py内部一致性，未验证**整个代码库中所有n_bins参数函数**的一致性。代码库中另有4个n_bins函数（scripts中）**0处守卫**，与"完全一致"声明矛盾。

**逻辑断链分析**：
- 前提：修复目标是"P0-4的A1 bool穿透 + A3 OOM"
- 推理：A1/A3是n_bins参数的通用缺陷，应覆盖所有n_bins函数
- 跳跃：修复报告将"6处"等同于"所有n_bins函数"，但实际有10个n_bins函数（6个calibration.py + 4个scripts）
- 结论：§7"收敛声明""P0-4可宣布完全收敛"**逻辑断链**——仅在calibration.py子集内收敛，scripts中A1/A3仍存在

**修复报告§7原文**：
> **P0-4 修复后状态**：✅ **已收敛**
> - 致命/严重/中等攻击点：全部清零
> - P0-4 可宣布完全收敛

该声明**与ATK-1实测结果矛盾**：scripts中A1 bool穿透（fit_binned_temperature/quintile_edges）和A3 OOM（compute_reliability_bins）仍然存在，"全部清零"为假。

- **代码证据**：修复报告`docs/p0r6_fix_p0_4.md` L175-178 vs scripts中0处守卫（ATK-1证据）
- **修复建议**：修复报告§7应声明收敛范围为"src/utils/calibration.py内"，并新增P0-4扩展项覆盖scripts

---

### ATK-7：错误信息中"10**6"为字面量字符串而非数值1000000

- **维度**：语义偏移
- **严重度**：**轾微**
- **攻击**：6处守卫的错误信息为`f"n_bins must be a positive integer in [1, 10**6], got {n_bins!r}"`，其中`10**6`是**字面量字符串**（写在f-string内的文本），而非数值`1000000`。用户看到"10**6"需心算才知道上界是100万，可能误解为"10的6次方个某种单位"或忽略。

**对比**：
```python
# 当前（字面量）
raise ValueError(f"n_bins must be a positive integer in [1, 10**6], got {n_bins!r}")
# 输出: n_bins must be a positive integer in [1, 10**6], got 1000000000000000000

# 替代（数值）
raise ValueError(f"n_bins must be a positive integer in [1, {10**6}], got {n_bins!r}")
# 输出: n_bins must be a positive integer in [1, 1000000], got 1000000000000000000
```

**语义偏移**：错误信息中"10**6"是Python表达式文本而非数学结果，与`{n_bins!r}`显示repr值的语义不一致——上界用表达式文本，非法值用repr值，信息风格不统一。此为轾微问题，不影响功能。

- **代码证据**：`src/utils/calibration.py` L216/552/608/661/704/772 `[1, 10**6]` 为f-string内字面量
- **修复建议**：改为`f"n_bins must be a positive integer in [1, {10**6}], got {n_bins!r}"`或`f"... in [1, 1000000], got {n_bins!r}"`（可选）

---

## 7维度攻击完整性声明

| 维度 | 是否尝试 | 发现攻击点 | 对应ATK |
|------|---------|-----------|---------|
| 1. 反例构造 | ✅ | 是 | ATK-1（3个反例）、ATK-2/4（性能反例） |
| 2. 逻辑断链 | ✅ | 是 | ATK-6（"6处"≠"所有n_bins函数"） |
| 3. 隐含假设 | ✅ | 是 | ATK-1（假设修复范围=calibration.py，遗漏scripts） |
| 4. 边界失效 | ✅ | 是 | ATK-1（bool穿透+OOM在scripts边界失效） |
| 5. 自相矛盾 | ✅ | 是 | ATK-3（brier_parts测试vs ece测试不一致） |
| 6. 量级错误 | ✅ | 是 | ATK-2（5s阻塞）、ATK-4（190分钟/19.5小时阻塞） |
| 7. 语义偏移 | ✅ | 是 | ATK-5（TypeError vs ValueError）、ATK-7（字面量vs数值） |

**全部7个维度均已尝试，发现7个攻击点。R6-Phase1 P0-4正方修复未通过反方审查。**

---

## 攻击点优先级排序与修复建议

### 致命（必须修复才能收敛）
1. **ATK-1**：scripts中4个n_bins函数添加守卫（或抽取`_validate_n_bins`公共函数）

### 严重（应修复）
2. **ATK-2**：降低n_bins上界至10**4，或向量化ece/mce/brier_parts实现
3. **ATK-4**：对bootstrap场景额外限制`n_bins × n_bootstrap`，或降低n_bins上界（与ATK-2同修复）
4. **ATK-3**：brier_parts测试L213扩充为8个非法值，与L230一致

### 中等（建议修复）
5. **ATK-5**：scripts守卫统一抛ValueError（与ATK-1同修复）
6. **ATK-6**：修复报告§7收敛声明限定为"calibration.py内"，新增scripts扩展项

### 轻微（可选修复）
7. **ATK-7**：错误信息中`10**6`改为`{10**6}`或`1000000`

---

## 对R6-Phase1 P0-4正方修复的总体评价

**修复在`src/utils/calibration.py`范围内正确且完整**：
- ✅ 6处守卫模式完全一致（grep逐字符验证通过）
- ✅ bool排除正确（True/np.bool_均被拦截）
- ✅ 上界检查正确（10**6+1被拦截）
- ✅ np.integer覆盖所有numpy整数类型（int8/16/32/64/uint8/16/32/64均通过）
- ✅ ece/mce/bootstrap_ece测试覆盖8个非法值

**修复在代码库全局范围内不完整**：
- ❌ scripts中4个n_bins函数无守卫（ATK-1致命）
- ❌ 上界10**6对O(n_bins)循环实现过大（ATK-2/4严重）
- ❌ brier_parts测试覆盖退步未完全修复（ATK-3严重）
- ❌ 修复报告"完全收敛"声明逻辑断链（ATK-6中等）

**结论**：R6-Phase1 P0-4正方修复**未通过反方审查**，需进入R7轮修复ATK-1（致命）+ ATK-2/3/4（严重）。

---

## 附录：实测命令与结果

### A.1 6处守卫文本一致性验证
```
$ grep "isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1 or n_bins > 10\*\*6" src/utils/calibration.py
L215, L551, L607, L660, L703, L771 — 6处完全一致 ✅
```

### A.2 scripts守卫缺失验证
```
$ grep "isinstance(n_bins.*raise|n_bins.*<.*1.*raise|n_bins.*>.*raise" scripts/run_e2_*.py scripts/run_e4_*.py scripts/run_e6_*.py
0处匹配 ❌
```

### A.3 bool穿透实测
```
fit_binned_temperature(n_bins=True): NOT RAISED (BUG!) ❌
quintile_edges(n_bins=True): NOT RAISED, result=[-inf  inf] (BUG!) ❌
compute_reliability_bins(n_bins=True): TypeError (非ValueError) ❌
```

### A.4 OOM未防止实测
```
compute_reliability_bins(n_bins=10**18): MemoryError: Unable to allocate 6.94 EiB ❌
```

### A.5 性能量级实测
```
ece(n_bins=10**6, 3样本): 4.803s
ece(n_bins=10**6, 10000样本): 19.814s
bootstrap_ece(n_bins=10**6, n_bootstrap=2): 14.042s → 外推n_bootstrap=10000: 19.5小时
compute_all_metrics(n_bins=10**6, n_bootstrap=2): 22.788s → 外推n_bootstrap=1000: 190分钟
```

### A.6 测试覆盖不一致验证
```
tests/test_model.py L213: [0, -1, 1.5, "10"] — 4个（遗漏True/None/2.0/10**18）
tests/test_model.py L230: [0, -1, 1.5, None, True, "10", 2.0, 10**18] — 8个
```

### A.7 numpy类型覆盖验证
```
np.int8/16/32/64, np.uint8/16/32/64: 全部通过 ✅
np.bool_(True): ValueError OK ✅（因非(int, np.integer)实例）
np.float32/64(10): ValueError OK ✅
```
