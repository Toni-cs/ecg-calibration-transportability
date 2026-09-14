# P0-4 反反方审查报告（R2轮）

## 审查概要
- 攻击报告：docs/p0r2_attack_p0_4.md
- 攻击点总数：8
- 成立：3 | 部分成立：5 | 不成立：0
- 审查日期：2026-09-09
- 审查代理：反反方审查代理（GLM-5.2）
- 审查方法：逐条读取实际源代码验证，不依赖攻击报告文字描述

### 判定分布

| 攻击点 | 攻击定级 | 反反方判定 | 反反方定级 |
|--------|---------|-----------|-----------|
| F1-r2 | 严重 | 部分成立 | 轻微（降级） |
| S3-r2 | 严重 | 成立 | 严重（维持） |
| M3-r2 | 轻微 | 成立 | 轻微（维持） |
| N1-r2 | 严重 | 部分成立 | 轻微（降级） |
| N2-r2 | 严重 | 成立 | 严重（维持） |
| N3-r2 | 轻微 | 部分成立 | 轻微（维持） |
| N4-r2 | 轻微 | 部分成立 | 轻微（维持） |
| 默认值风险 | 轻微 | 部分成立 | 轻微（维持） |

**核心结论**：攻击报告中 4 个"严重"攻击点中，仅 2 个（S3-r2、N2-r2）真正成立；F1-r2 和 N1-r2 的"严重"定级被夸大——两者均无当前数值 bug，纯属未来防御性推测。正方 P0-4 第二轮修复的核心目标（brier_parts 签名 + ValueError 守卫 + compute_all_metrics 内部传参）已完整达成。

---

## 逐条审查

### 攻击点1: F1-r2——5 处调用方仍遗漏 n_bins

**判定**: 部分成立

**事实核查**（反反方独立读取代码确认）：
- `scripts/run_e1a_l2_shift_full.py:159`：`_, rel, _, _ = brier_parts(mp, corr)` — ✅ 确实未传 n_bins
- `scripts/run_e1b_loco_validation.py:552`：`brier_parts(raw_mp, raw_correct)` — ✅ 确实未传
- `scripts/run_e1b_loco_validation.py:553`：`brier_parts(cal_mp, cal_correct)` — ✅ 确实未传
- `scripts/run_e1b_loco_validation.py:593`：`brier_parts(rmp, rcor)` — ✅ 确实未传
- `scripts/run_e1b_loco_validation.py:594`：`brier_parts(cmp, ccor)` — ✅ 确实未传

事实层面：攻击报告的代码证据完全准确，5 处调用方确实未显式传 n_bins。

**夸大部分**：
1. **定级"严重"被夸大**。攻击报告自认"当前无数值 bug"，承认"默认 n_bins=10 与 E1a/E1b 期望行为一致，数值无变化"。一个不产生任何数值差异的问题定级"严重"，违反 CBM 审稿标准中"严重=影响数值正确性或可复现性"的惯例。实际定级应为"轻微（工程风格）"。

2. **稻草人论证边界**。攻击报告称"修复声称'所有调用方都正确传参'是不完整的不实声明"。但正方 P0-4 修复的声明范围是：① brier_parts 签名添加 n_bins 参数；② 添加 ValueError 守卫；③ compute_all_metrics 内部调用传 n_bins。**修复从未声称"所有外部调用方都显式传参"**。攻击将"修复未覆盖的范围"等同于"修复缺陷"，属于稻草人论证。

3. **默认参数的设计意图**。Python 默认参数的存在正是为了让使用默认值的调用方无需显式传参。若按攻击逻辑，所有使用默认参数的调用方都是"缺陷"，则 Python 语言本身的默认参数机制都是"缺陷"——这显然荒谬。

**成立部分**：
- 从防御性编程最佳实践角度，显式传参确实优于隐式依赖默认值，尤其在研究代码库中。E1b 的 `_ncv_stat` 闭包（L593-594）与点估计（L552-553）若未来默认值被修改，确实可能产生不一致。这一工程稳健性建议方向正确。
- 建议作为"建议项"而非"必修项"处理。

**反驳**：攻击报告将此列为"必修项（严重，论文投稿前必须修复）"是过度要求。论文投稿前无需修复一个不影响任何数值结果的风格问题。

---

### 攻击点2: S3-r2——测试仍通过 compute_all_metrics 间接测试

**判定**: 成立

**事实核查**（反反方独立读取 `tests/test_model.py` 确认）：
- L188-198 `test_brier_parts`：确实只通过 `compute_all_metrics(n_bins=5)` 间接测试，未直接调用 `brier_parts(n_bins=5)`。
- 全测试文件 grep `brier_parts`：仅在 L188 出现一次（函数名引用），无直接调用。
- 全测试文件 grep `ValueError`：无匹配——**确实未测试 ValueError 守卫**。
- 全测试文件 grep `np.integer`：无匹配——**确实未测试 numpy 整数类型支持**。

**分析**：
1. 修复在 `brier_parts` L603-604 新增了 `isinstance(n_bins, (int, np.integer))` 检查和 `n_bins < 1` 检查，这是新的代码路径。**新增代码路径必须有对应测试**——这是 CBM 期刊审稿的基本要求。
2. 若未来有人误删 `np.integer` 从 isinstance 检查中（例如改为 `isinstance(n_bins, int)`），所有现有测试仍通过——测试无法捕获 isinstance 检查的退化。这是真实的测试覆盖漏洞。
3. 攻击报告提供的修补建议（`test_brier_parts_n_bins_validation`）合理且可操作。

**定级维持"严重"**：在 CBM 期刊审稿标准下，新增防御性代码无对应测试属于严重的测试覆盖不足。修复违背了"修了代码必须修测试"原则。

**修补方案**：
- 文件：`tests/test_model.py`
- 位置：L198 后新增测试方法
- 改动内容：
```python
def test_brier_parts_n_bins_validation(self):
    from src.utils.calibration import brier_parts
    probs = np.random.rand(100)
    labels = (np.random.rand(100) > 0.5).astype(float)
    # 直接测试 n_bins 参数生效
    b5 = brier_parts(probs, labels, n_bins=5)
    b10 = brier_parts(probs, labels, n_bins=10)
    assert b5 != b10
    # 测试 numpy 整数类型
    b_np = brier_parts(probs, labels, n_bins=np.int64(10))
    assert b_np == b10
    # 测试 ValueError 守卫
    for bad_n_bins in [0, -1, 1.5, "10"]:
        with pytest.raises(ValueError):
            brier_parts(probs, labels, n_bins=bad_n_bins)
```

---

### 攻击点3: M3-r2——E1b 注释代码未传 n_bins

**判定**: 成立

**事实核查**（反反方独立读取代码确认）：
- `scripts/run_e1b_loco_validation.py:585`：`#   ncv = brier_parts(raw_mp, raw_correct)[1] - brier_parts(cal_mp, cal_correct)[1]` — ✅ 确实是注释代码且未传 n_bins。

**分析**：
- 事实成立。注释代码确实未传 n_bins。
- 定级"轻微"恰当——注释代码无运行时影响。
- 攻击报告的修补建议（清理注释代码或改为带 n_bins 的注释）合理。

**修补方案**：
- 文件：`scripts/run_e1b_loco_validation.py`
- 行号：L585
- 改动内容：将注释改为 `#   ncv = brier_parts(raw_mp, raw_correct, n_bins=10)[1] - brier_parts(cal_mp, cal_correct, n_bins=10)[1]`，或直接删除该注释行（因 L591-595 的 `_ncv_stat` 闭包已实现相同逻辑）。

---

### 攻击点4: N1-r2——compute_all_metrics 的 7 处调用方未传 n_bins

**判定**: 部分成立

**事实核查**（反反方独立读取代码确认）：
- `scripts/run_e5_inception_lite.py:365`：`compute_all_metrics(max_probs_raw, correct_mask, n_bootstrap=1000)` — ✅ 未传 n_bins
- `scripts/run_e5_inception_lite.py:366`：`compute_all_metrics(max_probs_ts, correct_mask, n_bootstrap=1000)` — ✅ 未传
- `scripts/run_e5_inception_lite.py:474`：`compute_all_metrics(max_probs_raw, correct_mask, n_bootstrap=1000)` — ✅ 未传
- `scripts/run_e5_inception_lite.py:475`：`compute_all_metrics(max_probs_ts, correct_mask, n_bootstrap=1000)` — ✅ 未传
- `scripts/train.py:209`：`compute_all_metrics(max_probs, correct_mask, n_bootstrap=0)` — ✅ 未传
- `scripts/train.py:674`：`compute_all_metrics(max_probs_raw, correct_mask, n_bootstrap=1000)` — ✅ 未传
- `scripts/train.py:675`：`compute_all_metrics(max_probs_cal, correct_mask, n_bootstrap=1000)` — ✅ 未传

事实层面：攻击报告的代码证据完全准确，7 处调用方确实未显式传 n_bins。

**夸大部分**：
1. **定级"严重"被夸大**，理由与 F1-r2 相同。攻击报告自认"当前行为正确（默认 10 与全代码库一致）"。一个不影响任何当前数值结果的问题定级"严重"，属于定级虚高。

2. **与 F1-r2 的性质差异**。F1-r2 涉及 `brier_parts` 的直接调用方，而 N1-r2 涉及 `compute_all_metrics` 的调用方。`compute_all_metrics` 的 n_bins 参数有默认值 10，这 7 处调用方使用默认值是正常的 API 使用模式。`compute_all_metrics` 本身已正确将 n_bins 传给 brier_parts（L770），调用链内部一致性已保证。

3. **修复范围合理性**。P0-4 修复的核心目标是 `brier_parts` 函数本身及其在 `compute_all_metrics` 内部的调用。要求 P0-4 修复同时处理所有 `compute_all_metrics` 的外部调用方，属于要求修复者承担全代码库的参数显式化责任——这超出了 P0-4 的职责范围。

**成立部分**：
- 从工程稳健性角度，显式传参确实更好。建议作为"建议项"处理，可与其他 P0 修复一并处理。

**反驳**：攻击报告将此列为"必修项（严重，论文投稿前必须修复）"并与 F1-r2 合并要求"12 处显式传参"，是过度要求。这 12 处中没有任何一处影响当前数值正确性。

---

### 攻击点5: N2-r2——ValueError 守卫覆盖范围不完整，ece/mce 无守卫

**判定**: 成立

**事实核查**（反反方独立读取 `src/utils/calibration.py` 确认）：
- `ece` 函数（L199-243）：✅ 确实无 n_bins 验证守卫。L225 `bin_boundaries = np.linspace(0, 1, n_bins + 1)`，n_bins=0 时返回 `[0.]`；L229 `for i in range(n_bins)` 不执行，返回 0.0。
- `mce` 函数（L643-676）：✅ 确实无 n_bins 验证守卫。L659 `bin_boundaries = np.linspace(0, 1, n_bins + 1)`，n_bins=0 时返回 `[0.]`；L662 `for i in range(n_bins)` 不执行，返回 0.0。
- `bootstrap_ece` 函数（L520-583）：✅ 无 n_bins 验证守卫，直接传给 ece。
- `brier_parts` 函数（L603-604）：✅ 有守卫 `if not isinstance(n_bins, (int, np.integer)) or n_bins < 1: raise ValueError(...)`。
- `compute_all_metrics` 函数（L744-784）：✅ 无入口验证。调用顺序：L767 `bootstrap_ece` → L770 `brier_parts` → L773 `mce`。

**分析**：
1. **修复引入了新的行为不一致**。修复前，所有函数对 n_bins=0 都静默返回 0.0（一致地错）；修复后，`brier_parts` 抛 ValueError 而 `ece`/`mce` 仍静默返回 0.0，造成**同一输入下部分指标抛异常、部分指标静默错误**的行为不一致。这是修复的副作用。
2. **反例可复现**。`compute_all_metrics(probs, labels, n_bins=0, n_bootstrap=0)` 的执行路径：L767 `bootstrap_ece(probs, labels, 0, 0)` → `ece(probs, labels, 0)` 返回 0.0（静默错误）→ L770 `brier_parts(probs, labels, n_bins=0)` 抛 ValueError。用户看到 ValueError 时，ECE 已静默返回 0.0 但用户不知道。
3. 攻击报告的修补方案 A（在 `compute_all_metrics` 入口处统一验证）是最佳方案——确保所有子函数调用前 n_bins 已验证，行为统一。

**定级维持"严重"**：防御性编程不完整导致行为不一致，且是修复引入的新问题（修复前行为一致地错，修复后行为不一致地错）。

**修补方案**（推荐方案 A）：
- 文件：`src/utils/calibration.py`
- 行号：L763 后（`compute_all_metrics` 函数体开头，`probs = np.asarray(probs)` 之前或之后）
- 改动内容：
```python
def compute_all_metrics(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
    n_bootstrap: int = 1000
) -> dict:
    if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
        raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
    probs = np.asarray(probs)
    labels = np.asarray(labels)
    ...
```

---

### 攻击点6: N3-r2——isinstance 检查接受 bool

**判定**: 部分成立

**事实核查**（反反方独立运行 Python 验证）：
```
isinstance(True, int): True
isinstance(False, int): True
True < 1: False
False < 1: True
```
- ✅ `isinstance(True, (int, np.integer))` 返回 `True`，`True < 1` 返回 `False`（因为 `True == 1`）→ `brier_parts(probs, labels, n_bins=True)` 会通过守卫，被当作 `n_bins=1` 使用。
- ✅ `isinstance(False, (int, np.integer))` 返回 `True`，`False < 1` 返回 `True`（因为 `False == 0`）→ `brier_parts(probs, labels, n_bins=False)` 会触发 ValueError。

**成立部分**：
- 事实成立。`n_bins=True` 确实会被静默接受为 `n_bins=1`，这是语义漏洞。

**夸大部分**：
1. **这是 Python 语言的通用特性，非修复特有缺陷**。`bool` 是 `int` 的子类是 Python 语言设计决策（PEP 285），所有使用 `isinstance(x, int)` 的 Python 函数都有此"漏洞"。若将此判定为缺陷，则 Python 标准库中数万个函数都有此"缺陷"。
2. **现实触发概率极低**。没有任何合理的调用场景会传入 `n_bins=True`。这属于理论上的类型系统边界，而非实际的工程风险。
3. 攻击报告定级"轻微"恰当，但将其列为"建议项"已属上限。

**修补方案**（可选，防御性编程最佳实践）：
- 文件：`src/utils/calibration.py`
- 行号：L603
- 改动内容：
```python
# 原：if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
# 改：if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
```

---

### 攻击点7: N4-r2——类型注解与运行时检查不一致

**判定**: 部分成立

**事实核查**（反反方独立读取代码确认）：
- L586：`def brier_parts(probs, labels, n_bins: int = 10):` — ✅ 类型注解是 `int`
- L603：`if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:` — ✅ 运行时接受 `np.integer`
- 运行验证：`isinstance(np.int64(10), (int, np.integer))` 返回 `True` — ✅ numpy 整数运行时正常工作

**成立部分**：
- 事实成立。类型注解 `int` 与运行时接受 `np.integer` 确实不一致。严格模式下的 mypy/pyright 会报 `brier_parts(probs, labels, n_bins=np.int64(10))` 不符合 `int` 注解。

**夸大部分**：
1. **实际影响极小**。大多数 numpy 项目不使用 mypy 严格模式，或使用 numpy type stubs（`numpy.typing`）处理此情况。运行时行为完全正确。
2. **这是 numpy 生态的通用问题**。numpy 数值类型与 Python 内置类型的注解不一致是整个 numpy 生态的已知问题，非此修复特有。
3. 攻击报告定级"轻微"恰当。

**修补方案**（可选）：
- 文件：`src/utils/calibration.py`
- 行号：L586
- 改动内容：
```python
# 原：def brier_parts(probs, labels, n_bins: int = 10):
# 改：from typing import Union  # 若未导入
#     def brier_parts(probs, labels, n_bins: Union[int, "np.integer"] = 10):
```
或在 docstring 中说明"n_bins 也接受 numpy 整数类型"。

---

### 攻击点8: 默认值风险——硬编码 10 无模块级常量

**判定**: 部分成立

**事实核查**（反反方独立读取代码确认）：
- `ece` L199：`n_bins: int = 10` — ✅ 硬编码
- `bootstrap_ece` L523：`n_bins: int = 10` — ✅ 硬编码
- `brier_parts` L586：`n_bins: int = 10` — ✅ 硬编码
- `mce` L643：`n_bins: int = 10` — ✅ 硬编码
- `plot_reliability_diagram` L682：`n_bins: int = 10` — ✅ 硬编码
- `compute_all_metrics` L747：`n_bins: int = 10` — ✅ 硬编码

**成立部分**：
- 事实成立。6 处默认值均为硬编码 10，无模块级常量。若未来修改其中一处而遗漏其他处，会导致不一致。

**夸大部分**：
1. **这是常见的 Python 代码风格**。硬编码默认值是 Python 的标准实践，模块级常量是可选的最佳实践而非必需。
2. **当前所有默认值一致**（均为 10），无实际不一致。
3. 攻击报告定级"轻微"恰当，但此问题接近吹毛求疵边界。

**修补方案**（可选）：
- 文件：`src/utils/calibration.py`
- 位置：模块顶部（L16 `EPS = 1e-7` 附近）
- 改动内容：
```python
DEFAULT_N_BINS = 10
```
然后将 6 处 `n_bins: int = 10` 改为 `n_bins: int = DEFAULT_N_BINS`。

---

## 总结

### 需要进一步修复的问题清单

**必修项（论文投稿前修复）**：

1. **S3-r2（严重）**：补充 `test_brier_parts_n_bins_validation` 测试，直接测试 brier_parts 的 n_bins 参数行为 + ValueError 守卫 + numpy 整数类型支持。修复新增了代码路径但无对应测试，违背"修了代码必须修测试"原则。

2. **N2-r2（严重）**：在 `compute_all_metrics` 入口处（L763 后）统一添加 n_bins 验证守卫，确保 n_bins=0/负数时所有指标行为一致（统一抛 ValueError），消除修复引入的 ece/mce 与 brier_parts 行为不一致。

**建议项（可后续迭代）**：

3. **F1-r2 + N1-r2（轻微）**：12 处调用方显式传 `n_bins=10`。虽当前无数值 bug，但显式传参是更好的工程实践。可作为代码风格统一处理，无需阻塞论文投稿。
4. **M3-r2（轻微）**：清理 E1b L585 注释代码。
5. **N3-r2（轻微）**：isinstance 检查排除 bool（可选，Python 语言通用特性）。
6. **N4-r2（轻微）**：类型注解改为 `Union[int, np.integer]` 或 docstring 说明（可选）。
7. **默认值风险（轻微）**：定义模块级常量 `DEFAULT_N_BINS = 10`（可选）。

### 已确认修复完成的问题

- ✅ brier_parts 签名添加 n_bins 参数（L586）
- ✅ brier_parts ValueError 守卫（L603-604）
- ✅ compute_all_metrics 内部调用传 n_bins（L770）
- ✅ 默认值一致性（brier_parts L586 vs compute_all_metrics L747，均为 10）
- ✅ numpy 整数类型支持（isinstance 检查包含 np.integer）
- ✅ 浮点数 n_bins 正确触发 ValueError（M2 已解决）

### 对正方修复的总体评价

**P0-4 第二轮回炉修复的核心目标已完整达成**。修复正确地：
1. 为 `brier_parts` 添加了 `n_bins` 参数
2. 添加了 ValueError 守卫覆盖整数类型和正数检查
3. 修复了 `compute_all_metrics` 内部调用遗漏 n_bins 的 bug（第一轮致命 bug F2）

**修复的不足之处**：
1. **测试覆盖不足（S3-r2）**：新增了 ValueError 守卫和 numpy 整数支持，但未新增对应测试。这是 CBM 审稿标准下的真实缺陷。
2. **防御性编程不完整（N2-r2）**：守卫只在 brier_parts 添加，ece/mce 无守卫，导致 n_bins=0 时行为不一致。这是修复引入的副作用——修复前所有函数一致地静默错误，修复后 brier_parts 抛异常而 ece/mce 仍静默。

**对攻击报告的评价**：
- 攻击报告的**事实核查质量高**——所有代码行号证据经反反方独立验证均准确无误。
- 攻击报告的**定级存在系统性虚高**：F1-r2 和 N1-r2 均被定为"严重"，但两者均无当前数值 bug，纯属未来防御性推测。将"不影响任何数值结果的风格问题"定为"严重"并要求"论文投稿前必须修复"，属于过度审查。
- 攻击报告的**N2-r2 发现质量高**——这是修复引入的真实副作用，行为不一致反例可复现，是本轮审查最有价值的发现。
- 攻击报告的**S3-r2 论证充分**——新增代码路径无测试是明确的测试覆盖漏洞。

**最终判定**：P0-4 第二轮回炉修复**基本通过**——核心 bug 已修复，但存在 2 个需在论文投稿前修复的真实缺陷（S3-r2 测试覆盖 + N2-r2 守卫一致性）。攻击报告中的 4 个"严重"攻击点中，仅 2 个真正成立；F1-r2 和 N1-r2 的"严重"定级被夸大，应降级为"轻微"并作为建议项处理。
