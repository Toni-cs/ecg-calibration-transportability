# P0-4 R5 修复反方攻击报告

**攻击对象**：P0-4 R5 修复（calibration.py 守卫 + test_model.py 新测试）
**攻击代理**：反方挑刺代理（GLM-5.2）
**攻击轮次**：R5
**攻击日期**：2026-09-10
**攻击结论**：发现 7 个攻击点，其中严重 3 个、轻微 4 个。R5 修复存在 bool 类型静默接受、无上界检查 OOM、测试覆盖不足三项严重缺陷，建议 R6 修补。

---

## 一、R5 修复内容回顾

| 修复项 | 内容 | 位置 |
|--------|------|------|
| A1 | `plot_reliability_diagram` 函数体开头添加 `n_bins` 验证守卫 | calibration.py:703-704 |
| A2 | `test_model.py` 新增 `test_ece_mce_bootstrap_ece_n_bins_guards` 直接测试 ece/mce/bootstrap_ece 守卫 | test_model.py:224-240 |

**守卫模式（6 处统一）**：
```python
if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
    raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
```

出现位置：`ece`(L215)、`bootstrap_ece`(L551)、`brier_parts`(L607)、`mce`(L660)、`plot_reliability_diagram`(L703)、`compute_all_metrics`(L771)。

---

## 二、七维度全攻击结果

### 维度 1：反例构造

#### 攻击点 A1【严重】bool 类型 `True` 被静默接受为 `n_bins=1`

**反例**：
```python
>>> isinstance(True, (int, np.integer))
True        # bool 是 int 的子类！
>>> True < 1
False       # True == 1
>>> not isinstance(True, (int, np.integer)) or True < 1
False       # 守卫条件为 False → 不 raise
```

**构造**：调用 `ece(probs, labels, n_bins=True)`，守卫不拦截，`True` 被当作 `n_bins=1` 静默使用。

**危害**：若调用方存在 `n_bins = some_flag`（布尔标志误传为分箱数）的 bug，守卫无法捕获，导致静默错误结果。Python 类型系统已知陷阱（`bool` 是 `int` 子类），专业校验代码应显式排除。

**验证**：
```python
import numpy as np
from src.utils.calibration import ece
probs = np.random.rand(100); labels = (probs > 0.5).astype(float)
ece(probs, labels, n_bins=True)   # 不 raise，静默当作 n_bins=1
```

**修复建议**：守卫增加 `isinstance(n_bins, bool)` 排除：
```python
if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
    raise ValueError(...)
```

---

#### 攻击点 A2【轻微】浮点整数 `2.0` 被拒绝

**反例**：
```python
>>> isinstance(2.0, (int, np.integer))
False       # 2.0 是 float，不是 int
```

**构造**：调用 `ece(probs, labels, n_bins=2.0)`，守卫 raise ValueError。但数学上 `2.0 == 2` 是合法正整数。

**危害**：用户从除法/均值/JSON 配置得到 `n_bins=10.0`（浮点）会被拒绝，尽管语义合法。过于严格的类型检查拒绝数学上合法的整数值浮点数。

**严重度说明**：安全方向偏严，不会导致错误结果，仅影响易用性。

---

### 维度 2：逻辑断链

#### 攻击点 A3【严重】守卫只检查下界，无上界检查 → 极大 n_bins OOM

**断链**：守卫逻辑链为「类型合法 → 值 ≥ 1 → 放行」，但缺失「值 ≤ 上界」环节。`n_bins` 通过守卫后进入 `np.linspace(0, 1, n_bins + 1)`，该调用对极大值无防护。

**反例**：
```python
ece(probs, labels, n_bins=10**18)
# 守卫：isinstance(10**18, int)=True, 10**18 < 1=False → 不 raise
# np.linspace(0, 1, 10**18 + 1) → 尝试分配 ~8 EB 内存 → MemoryError / OOM 崩溃
```

**验证**：
```python
import numpy as np
np.linspace(0, 1, 10**9 + 1)   # 实测：分配 ~8 GB，勉强成功
np.linspace(0, 1, 10**12 + 1)  # ~8 TB → MemoryError
```

**危害**：
- 生产环境若 `n_bins` 从配置文件/用户输入/超参搜索读取，可触发 OOM 拒绝服务（DoS）。
- 守卫给人「已验证安全」的错觉，实则只防了半边。

**修复建议**：增加上界（如 `n_bins > 10**6` 时 raise，或根据 `len(probs)` 动态限制）：
```python
if ... or n_bins < 1 or n_bins > 10**6:
    raise ValueError(f"n_bins must be in [1, 10**6], got {n_bins}")
```

---

### 维度 3：隐含假设

#### 攻击点 A4【轻微】隐含假设 n_bins 来自 Python int 或 numpy 整数，未覆盖 ML 工作流常见类型

**未声明假设**：守卫假设调用方传入 Python `int` 或 `np.integer` 子类。但 ML 工作流中 `n_bins` 可能来自：
- `torch.tensor(10)`：`isinstance(torch.tensor(10), (int, np.integer))` 返回 `False` → 被拒
- `pd.Series([10])[0]`：pandas 可空整数类型 `Int64Dtype`，某些版本返回 `False` → 被拒
- JSON 配置：`json.load` 可能将 `10` 解析为 `int`（OK），但 `10.0` 解析为 `float` → 被拒（与 A2 相关）

**危害**：从 PyTorch/pandas 工作流传 `n_bins` 需额外类型转换，否则被拒。隐含假设未在 docstring 声明。

**严重度说明**：可要求调用方转换类型，属设计选择，但应显式声明。

---

### 维度 4：边界失效

#### 攻击点 A5【严重】新测试边界覆盖不足，遗漏关键非法输入

**边界覆盖对比**：

| 测试函数 | 覆盖的非法 n_bins | 遗漏 |
|----------|-------------------|------|
| `test_brier_parts_n_bins_validation` (既有) | `[0, -1, 1.5, "10"]` | None、True、极大值 |
| `test_ece_mce_bootstrap_ece_n_bins_guards` (R5 新增) | `[0, 1.5, None]` | **-1（负数）、"10"（字符串）、True（bool）、极大值** |

**断链**：R5 新测试声称「直接测试 ece/mce/bootstrap_ece 的 n_bins 验证守卫」，但覆盖度**退步**于既有 `test_brier_parts_n_bins_validation`：
- 既有测试覆盖了负数 `-1` 和字符串 `"10"`，新测试未覆盖。
- **A1 的 bool `True` 反例**（本报告最严重发现）未被任何测试覆盖。
- **A3 的极大值 OOM 反例**未被任何测试覆盖。

**危害**：A1（bool 静默接受）和 A3（OOM）均未被测试捕获，将在生产环境潜伏。

**修复建议**：扩充测试覆盖：
```python
for bad_n_bins in [0, -1, 1.5, None, True, "10", 10**18, 2.0]:
    with pytest.raises(ValueError):
        ece(probs, labels, n_bins=bad_n_bins)
    # ... mce, bootstrap_ece 同理
```

---

### 维度 5：自相矛盾

#### 攻击点 A6【轻微】`plot_reliability_diagram` 守卫错误信息格式与其他不一致

**矛盾**：
- `plot_reliability_diagram` (L704)：`raise ValueError(f"n_bins must be a positive integer, got {n_bins!r}")` → 用 `!r`（repr 格式）
- 其他 5 处（ece/mce/bootstrap_ece/brier_parts/compute_all_metrics）：`raise ValueError(f"n_bins must be a positive integer, got {n_bins}")` → 用 str 格式

**反例**：传入 `n_bins="10"`：
- `plot_reliability_diagram` 报错：`got '10'`（带引号）
- `ece` 报错：`got 10`（不带引号）

**危害**：错误信息不一致，影响调试体验和日志解析自动化。对 `None` 两者一致（`None` 的 repr 与 str 相同），对字符串/特殊类型不一致。

**修复建议**：统一为 `{n_bins!r}`（repr 更精确反映类型）或统一为 `{n_bins}`。

---

#### 攻击点 A7【轻微】`compute_all_metrics` 守卫与子函数守卫冗余

**矛盾**：`compute_all_metrics` (L771) 有守卫，但其调用的 `bootstrap_ece`/`brier_parts`/`mce` 都有独立守卫。若移除 `compute_all_metrics` 守卫，子函数仍会拦截非法 `n_bins`。

**危害**：
- 冗余检查（轻微性能开销，可忽略）。
- 若未来修改子函数守卫逻辑（如增加上界），`compute_all_metrics` 守卫可能与之不同步，产生不一致。
- 但属防御性编程，无害且提供更早的错误报告。

**严重度说明**：设计选择，非错误。建议保留但确保与子函数同步。

---

### 维度 6：量级错误

#### （与 A3 合并）

`n_bins` 无上界检查导致量级错误：`n_bins=10**6` 时 `np.linspace` 创建 ~8 MB（可接受），`n_bins=10**9` 时 ~8 GB（危险），`n_bins=10**12` 时 ~8 TB（OOM）。无明确量级边界声明。详见 A3。

---

### 维度 7：语义偏移

#### （与 A1、A5 合并）

- **A1**：守卫语义为「n_bins 必须是正整数」，但 `True`（布尔值）被接受。`True` 不是正整数，是布尔值。语义偏移。
- **A5**：测试声称覆盖「非法 n_bins」，但遗漏负数、字符串、bool、极大值，覆盖语义不完整。

---

## 三、重点攻击点逐项裁决

### 重点 1：`plot_reliability_diagram` 守卫与 ece/mce/bootstrap_ece 守卫模式一致性

**裁决**：模式基本一致（`isinstance(n_bins, (int, np.integer)) or n_bins < 1`），但存在 **A6 错误信息格式不一致**（`{n_bins!r}` vs `{n_bins}`）。严重度轻微。

**建议**：统一错误信息格式。

---

### 重点 2：新测试 `test_ece_mce_bootstrap_ece_n_bins_guards` 覆盖度

**裁决**：**覆盖不足（A5，严重）**。仅测 `[0, 1.5, None]`，遗漏 `-1`（负数）、`"10"`（字符串）、`True`（bool，A1 反例）、极大值（A3 反例）。覆盖度退步于既有 `test_brier_parts_n_bins_validation`。

**建议**：扩充至 `[0, -1, 1.5, None, True, "10", 10**18, 2.0]`。

---

### 重点 3：其他函数是否遗漏 n_bins 守卫

**裁决**：**未发现遗漏**。所有使用 `n_bins` 的函数均有守卫：

| 函数 | 有守卫 | 备注 |
|------|--------|------|
| `ece` (L215) | ✓ | |
| `bootstrap_ece` (L551) | ✓ | |
| `brier_parts` (L607) | ✓ | |
| `mce` (L660) | ✓ | |
| `plot_reliability_diagram` (L703) | ✓ | R5 新增 |
| `compute_all_metrics` (L771) | ✓ | |
| `smooth_ece` / `smooth_ece_gpu` | N/A | 不使用 n_bins（用 bandwidth） |
| `benefit_inference` / `two_layer_benefit_inference` | N/A | 不直接使用 n_bins（通过 metric 闭包） |

---

### 重点 4：isinstance 检查是否覆盖所有 numpy 整数类型

**裁决**：**numpy 整数类型完整覆盖，但 bool/float/torch 类型未覆盖**。

**验证**：
```python
>>> isinstance(np.int8(5), (int, np.integer))    # True ✓
>>> isinstance(np.int16(5), (int, np.integer))   # True ✓
>>> isinstance(np.int32(5), (int, np.integer))   # True ✓
>>> isinstance(np.int64(5), (int, np.integer))   # True ✓
>>> isinstance(np.uint8(5), (int, np.integer))   # True ✓
>>> isinstance(np.uint16(5), (int, np.integer))  # True ✓
>>> isinstance(np.uint32(5), (int, np.integer))  # True ✓
>>> isinstance(np.uint64(5), (int, np.integer))  # True ✓
>>> isinstance(True, (int, np.integer))          # True ✗ (bool 被接受，A1)
>>> isinstance(2.0, (int, np.integer))           # False (float 被拒，A2)
>>> isinstance(torch.tensor(10), (int, np.integer))  # False (torch 被拒，A4)
```

`np.integer` 是所有 numpy 整数类型的抽象基类，覆盖完整。但 `bool`（Python int 子类）未被排除（A1）。

---

### 重点 5：测试是否能运行通过

**裁决**：**能通过，但覆盖不足**。

**验证**（对 `[0, 1.5, None]` 三个非法值）：
- `n_bins=0`：`isinstance(0, (int, np.integer))=True`，`0 < 1=True` → raise ✓
- `n_bins=1.5`：`isinstance(1.5, (int, np.integer))=False` → raise ✓
- `n_bins=None`：`isinstance(None, (int, np.integer))=False` → raise ✓
- `n_bins=1`（合法）：`isinstance(1, ...)=True`，`1 < 1=False` → 不 raise ✓

测试逻辑正确，能通过。但 **A1（bool True）和 A3（极大值）的反例未被测试覆盖**，守卫漏洞潜伏。

---

## 四、攻击点汇总（按严重度排序）

| 编号 | 严重度 | 维度 | 攻击点 | 位置 |
|------|--------|------|--------|------|
| A1 | **严重** | 反例构造 + 语义偏移 | `n_bins=True` 被静默接受为 `n_bins=1`（bool 是 int 子类） | 所有 6 处守卫 |
| A3 | **严重** | 逻辑断链 + 边界失效 + 量级错误 | 无上界检查，`n_bins=10**18` 导致 `np.linspace` OOM 崩溃 | 所有 6 处守卫 |
| A5 | **严重** | 边界失效 + 语义偏移 | 新测试仅覆盖 `[0, 1.5, None]`，遗漏 `-1`/`"10"`/`True`/极大值，覆盖度退步 | test_model.py:230 |
| A2 | 轻微 | 反例构造 | 浮点整数 `2.0` 被拒（数学上合法） | 所有 6 处守卫 |
| A4 | 轻微 | 隐含假设 | `torch.tensor`/pandas 可空整数类型未覆盖 | 所有 6 处守卫 |
| A6 | 轻微 | 自相矛盾 | `plot_reliability_diagram` 错误信息用 `{n_bins!r}`，其他用 `{n_bins}`，不一致 | calibration.py:704 |
| A7 | 轻微 | 自相矛盾 | `compute_all_metrics` 守卫与子函数守卫冗余（防御性编程，无害） | calibration.py:771 |

**统计**：
- 严重：3 个（A1、A3、A5）
- 轻微：4 个（A2、A4、A6、A7）
- 致命：0 个
- 总计：7 个攻击点

---

## 五、R6 修复建议（优先级排序）

### 必修 1（严重）：排除 bool 类型

所有 6 处守卫增加 `isinstance(n_bins, bool)` 排除：
```python
if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
    raise ValueError(f"n_bins must be a positive integer, got {n_bins!r}")
```

### 必修 2（严重）：增加上界检查

所有 6 处守卫增加上界（建议 `10**6`，或根据 `len(probs)` 动态限制）：
```python
if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1 or n_bins > 10**6:
    raise ValueError(f"n_bins must be a positive integer in [1, 10**6], got {n_bins!r}")
```

### 必修 3（严重）：扩充测试覆盖

`test_ece_mce_bootstrap_ece_n_bins_guards` 扩充非法值覆盖：
```python
for bad_n_bins in [0, -1, 1.5, None, True, "10", 10**18, 2.0]:
    with pytest.raises(ValueError):
        ece(probs, labels, n_bins=bad_n_bins)
    with pytest.raises(ValueError):
        mce(probs, labels, n_bins=bad_n_bins)
    with pytest.raises(ValueError):
        bootstrap_ece(probs, labels, n_bins=bad_n_bins)
```

### 选修 1（轻微）：统一错误信息格式

所有 6 处守卫统一用 `{n_bins!r}`（repr 更精确）或 `{n_bins}`。

### 选修 2（轻微）：docstring 声明 n_bins 类型要求

在 docstring 中显式声明 `n_bins: int (Python int 或 numpy 整数，不接受 bool/float/torch.tensor)`。

---

## 六、未发现可攻击点的维度

以下维度经检查未发现独立攻击点（部分与上述合并）：

- **维度 6（量级错误）**：与 A3 合并。无独立量级错误。
- **其他函数遗漏守卫**：所有使用 `n_bins` 的函数均有守卫，未发现遗漏。
- **numpy 整数类型覆盖**：`np.integer` 抽象基类完整覆盖所有 numpy 整数类型（int8/16/32/64, uint8/16/32/64）。

---

## 七、结论

R5 修复在「添加守卫」和「添加测试」两个方向上正确，但存在 **3 项严重缺陷**：

1. **A1**：bool 类型 `True` 被静默接受（Python 类型系统陷阱未处理）。
2. **A3**：无上界检查，极大 `n_bins` 导致 OOM（守卫只防了半边）。
3. **A5**：新测试覆盖不足，遗漏负数/字符串/bool/极大值，覆盖度退步于既有测试。

**建议**：R5 修复**不通过**，需 R6 修补上述 3 项严重缺陷后方可放行。4 项轻微缺陷可择机修复。

**攻击代理声明**：我尝试了全部 7 个攻击维度，找到 7 个有效攻击点（3 严重 + 4 轻微）。R5 修复不无懈可击。
