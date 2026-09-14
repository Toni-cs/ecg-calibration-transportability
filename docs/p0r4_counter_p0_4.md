# R4反反方审查报告：P0-4

## 审查摘要
- 反方攻击报告：docs/p0r4_attack_p0_4.md
- 审查文件：src/utils/calibration.py, tests/test_model.py
- 攻击点总数：8
- 成立攻击：6（A1, A2, A3, A4, A5, A6, A8 中 A3 部分成立，A4/A5/A6/A8 成立但轻微）
- 不成立攻击：1（A7）
- 需R5修补项：2 项必修（A1, A2）+ 5 项可选改进（A3, A4, A5, A6, A8）

## 逐条审查

### Attack-1: plot_reliability_diagram 无 n_bins 守卫——R4 修复范围仍不完整

**判定**：成立

**理由**：

经源代码逐行验证，反方此攻击点成立，且论证扎实：

1. **plot_reliability_diagram 确实无守卫**：源代码 `src/utils/calibration.py` L685-747，函数签名 L688 `n_bins: int = 10`，函数体 L703-706 直接 `import matplotlib` 和 `probs = np.asarray(probs)`，L708 `bin_boundaries = np.linspace(0, 1, n_bins + 1)` 直接使用 n_bins，**无任何 isinstance 检查或 n_bins < 1 守卫**。

2. **plot_reliability_diagram 是公开 API**：反方声称 `scripts/train.py` L40 import、L725 调用。虽然本次审查未读取 train.py 验证，但 plot_reliability_diagram 是模块级公开函数（非 `_` 前缀私有函数），且是校准可视化的标准入口，属于公开 API 无疑。

3. **行为不一致确实存在**：
   - `n_bins=0`：`np.linspace(0, 1, 1)` 产生 `[0.0]`，`range(0)` 不执行循环，返回空图（bin_centers/bin_means/bin_counts 均为空列表）——**静默返回**，无 ValueError
   - `n_bins=-1`：`np.linspace(0, 1, 0)` 产生 `[]`，`range(-1)` 不执行，同样静默返回空图
   - `n_bins=1.5`：`range(1.5)` 抛 `TypeError: 'float' object cannot be interpreted as an integer`——**抛 TypeError 而非 ValueError**
   - `n_bins="10"`：`n_bins + 1` 抛 `TypeError: can only concatenate str (not "int") to str`——**抛 TypeError 而非 ValueError**
   - `n_bins=None`：`n_bins + 1` 抛 `TypeError: unsupported operand type(s) for +: 'NoneType' and 'int'`——**抛 TypeError 而非 ValueError**
   - `n_bins=True`：`isinstance` 不检查（无守卫），`True + 1 = 2`，`range(True) = range(1)`，静默返回单 bin 图——**bool 穿透**

4. **与 R3 终审报告的关系**：R3 终审报告（p0r3_final_verdict.md L237）R4 必修项明确只列了 ece/mce/bootstrap_ece 三个函数，**未明确列出 plot_reliability_diagram**。但 R3 终审报告 L223 的论证指出"R2 终审报告 N2-r2 攻击点未被彻底修复：ece/mce/bootstrap_ece 作为公开 API 仍无守卫"，其根本原则是"所有接受 n_bins 的公开函数都应有守卫"。R4 机械执行了终审报告明确列出的 3 个函数，但未主动检查同模块其他接受 n_bins 的函数。**这是修复范围的不完整，反方攻击成立**。

5. **严重程度评估**：反方定级"严重"合理。plot_reliability_diagram 虽然是可视化函数（返回 fig 而非数值），不会产生"伪完美校准 ECE=0.0"的数值危害，但：
   - 行为不一致问题仍未彻底消除（其他 5 个函数统一抛 ValueError，plot_reliability_diagram 对 0/-1/True 静默返回，对 1.5/"10"/None 抛 TypeError）
   - 作为公开 API，可被其他代码或未来开发直接调用传非法 n_bins
   - 静默返回空图可能误导调用方认为"校准图已生成"而未察觉错误

**若成立，修补方案**：

文件：`src/utils/calibration.py`
位置：L702 后（docstring 结束的 `"""` 之后、L703 `import matplotlib.pyplot as plt` 之前）
改动：插入 2 行守卫

```python
def plot_reliability_diagram(
    probs: np.ndarray,
    labels: np.ndarray,
    n_bins: int = 10,
    title: str = "Reliability Diagram",
    save_path: Optional[str] = None
):
    """绘制校准曲线（可靠性图）
    
    新增功能：可视化校准效果
    
    Args:
        probs: 预测概率
        labels: 真实标签
        n_bins: 分箱数量
        title: 图表标题
        save_path: 保存路径（可选）
    """
    if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
        raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
    import matplotlib.pyplot as plt
    
    probs = np.asarray(probs)
    labels = np.asarray(labels)
    ...
```

守卫位置选择理由：与 ece/mce/bootstrap_ece/brier_parts/compute_all_metrics 完全一致（docstring 后、probs 转换前），且在 `import matplotlib` 之前可避免非法 n_bins 时的无意义 import 开销。

---

### Attack-2: ece/mce/bootstrap_ece 守卫无直接测试覆盖——R4 修复了代码但未修复测试

**判定**：成立

**理由**：

经测试代码逐行验证，反方此攻击点成立：

1. **测试确实未直接调用 ece/mce/bootstrap_ece 传非法 n_bins**：`tests/test_model.py` L200-222 `test_brier_parts_n_bins_validation` 函数体：
   - L206-215：直接调用 `brier_parts(probs, labels, n_bins=...)` 测试 brier_parts 守卫
   - L217-222：直接调用 `compute_all_metrics(probs, labels, n_bins=...)` 测试 compute_all_metrics 守卫
   - **无任何 `ece(probs, labels, n_bins=...)` / `mce(probs, labels, n_bins=...)` / `bootstrap_ece(probs, labels, n_bins=...)` 传非法 n_bins 的测试代码**

2. **删除 ece 守卫后测试仍通过**：反方的反例论证成立。如果删除 ece L215-216 守卫，`ece(n_bins=0)` 会静默返回 0.0（`np.linspace(0,1,1)=[0.0]`，`range(0)` 不执行，`ece_val` 保持 0.0）。但测试不直接调用 `ece(n_bins=0)`，所以测试不会失败。`compute_all_metrics(n_bins=0)` 虽然会失败（L769-770 守卫拦截），但那测试的是 compute_all_metrics 守卫，**不是 ece 守卫**。

3. **R3 攻击报告攻击7 的核心问题转移**：R3 终审报告 L221-222 指出"修复点2（compute_all_metrics 守卫）：代码正确，位置正确，但无直接测试覆盖"。R4 修复了 compute_all_metrics 守卫的测试覆盖（L217-222），但新增的 ece/mce/bootstrap_ece 守卫**无测试覆盖**。攻击点从 compute_all_metrics 转移到 ece/mce/bootstrap_ece，**未被消除**。

4. **回归风险**：如果未来重构删除 ece/mce/bootstrap_ece 守卫，测试不会失败，直接调用 `ece(n_bins=0)` 会静默返回 0.0（伪"完美校准"），可能写入论文作为真实 ECE。这是真实的回归风险。

5. **严重程度评估**：反方定级"严重"合理。R4 修复了代码但未添加测试，违反了"修代码同时修测试"的最佳实践。

**若成立，修补方案**：

文件：`tests/test_model.py`
位置：L222 后（`test_brier_parts_n_bins_validation` 函数末尾，compute_all_metrics 守卫测试之后）
改动：插入 8-10 行直接测试

```python
        with pytest.raises((ValueError, TypeError)):
            compute_all_metrics(probs, labels, n_bins=1.5)
        # Test ece/mce/bootstrap_ece guards (R5 补充)
        from src.utils.calibration import ece, mce, bootstrap_ece
        for bad_n_bins in [0, -1, 1.5, "10", None]:
            with pytest.raises(ValueError):
                ece(probs, labels, n_bins=bad_n_bins)
            with pytest.raises(ValueError):
                mce(probs, labels, n_bins=bad_n_bins)
            with pytest.raises(ValueError):
                bootstrap_ece(probs, labels, n_bins=bad_n_bins, n_bootstrap=5)
```

注意：`ece` 和 `bootstrap_ece` 已在 L15 顶部 import，`mce` 需新增 import（可在函数内 import 或顶部补充）。`bootstrap_ece` 传 `n_bootstrap=5` 以加速测试。

---

### Attack-3: compute_all_metrics 守卫测试不完整——边界值覆盖不全

**判定**：部分成立（降级为轻微）

**理由**：

反方指出的边界值覆盖不全确实存在，但严重程度被高估：

1. **已覆盖的核心路径**：测试 L217-222 覆盖了 `n_bins=0`（边界非法）、`n_bins=-1`（负数非法）、`n_bins=1.5`（浮点数非法）。这三个值覆盖了守卫 `if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:` 的两个分支：
   - `n_bins=0`：`isinstance(0, (int, np.integer))` 为 True，`0 < 1` 为 True → 守卫触发（n_bins < 1 分支）
   - `n_bins=-1`：`isinstance(-1, (int, np.integer))` 为 True，`-1 < 1` 为 True → 守卫触发（n_bins < 1 分支）
   - `n_bins=1.5`：`isinstance(1.5, (int, np.integer))` 为 False → 守卫触发（isinstance 分支）

2. **未覆盖的边界值分析**：
   - `n_bins="10"`（字符串）：`isinstance("10", (int, np.integer))` 为 False → 守卫触发。**与 n_bins=1.5 同属 isinstance 分支，覆盖价值有限**——已有一个 isinstance 分支的测试用例（1.5），再加 "10" 只是增加同分支的另一个用例，不提升分支覆盖率。
   - `n_bins=None`：`isinstance(None, (int, np.integer))` 为 False → 守卫触发。**同样属 isinstance 分支**。
   - `n_bins=True`（bool）：这是 A4 的问题（bool 穿透），不是"守卫测试不完整"的问题。True 不会触发守卫，会被静默接受为 n_bins=1。这属于 A4 的攻击范围，不应在 A3 重复计数。
   - `n_bins=np.int64(10)`（合法 numpy 整数）：这是**正面测试**（应正常工作），不是**守卫测试**（应抛异常）。反方将其混入守卫测试清单是范畴混淆。
   - `n_bins=1`（合法最小边界值）：同样是**正面测试**，不是守卫测试。

3. **R3 终审报告定位**：R3 终审报告 L244 可选改进项 A4"补充 n_bins=1 边界值测试和 n_bins=None 测试"明确标记为"中等（建议）"，非必修。R4 未修复可选改进项不构成攻击成立。

4. **严重程度评估**：反方定级"中等"偏高。核心路径（两个分支）已覆盖，缺失的是同分支的额外用例和正面测试。降级为**轻微**。

**若成立，修补方案**（可选改进）：

文件：`tests/test_model.py`
位置：L222 后
改动：补充边界值测试（可选）

```python
        # 补充边界值测试（R5 可选）
        with pytest.raises(ValueError):
            compute_all_metrics(probs, labels, n_bins="10")
        with pytest.raises(ValueError):
            compute_all_metrics(probs, labels, n_bins=None)
        # 合法边界值正面测试
        _ = compute_all_metrics(probs, labels, n_bins=1, n_bootstrap=5)
        _ = compute_all_metrics(probs, labels, n_bins=np.int64(10), n_bootstrap=5)
```

---

### Attack-4: bool 类型穿透守卫——n_bins=True 被当作 n_bins=1

**判定**：成立（轻微）

**理由**：

反方此攻击点成立，但严重程度为轻微：

1. **bool 穿透事实确认**：Python 中 `bool` 是 `int` 的子类，`isinstance(True, int)` 返回 `True`，`True == 1`。守卫 `if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:` 对 `n_bins=True`：`isinstance(True, (int, np.integer))` 为 True，`True < 1` 为 False（True == 1）→ 守卫通过，静默接受为 n_bins=1。

2. **n_bins=False 行为**：`isinstance(False, (int, np.integer))` 为 True，`False < 1` 为 True（False == 0）→ 守卫拦截，抛 ValueError。所以 False 会被正确拦截，只有 True 穿透。

3. **实际影响评估**：`n_bins=True` 被当作 `n_bins=1` 使用，会产生单 bin 的校准图/指标。虽然语义错误（用户可能误传 bool），但：
   - `n_bins=True` 是极端异常用法，正常开发中不会出现
   - 单 bin 的结果不会是"伪完美校准"（ECE 仍会正确计算，只是分箱粒度为 1）
   - 不会导致崩溃或静默返回 0.0

4. **R3 终审报告定位**：R3 终审报告 L245 可选改进项 A5"排除 bool 类型（isinstance(n_bins, bool) 排除）"明确标记为"轾微"。R4 未修复可选改进项不构成攻击成立（但反方攻击本身成立，只是严重程度低）。

**若成立，修补方案**（可选改进）：

文件：`src/utils/calibration.py`
位置：所有 6 处守卫（ece L215 / mce L660 / bootstrap_ece L551 / brier_parts L607 / compute_all_metrics L769 / plot_reliability_diagram 新增守卫）
改动：各加 1 行 bool 排除

```python
    if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
        raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
```

注意：此修补为可选，优先级低。bool 穿透的实际危害极小。

---

### Attack-5: 测试 L221 pytest.raises((ValueError, TypeError)) 语义模糊——异常类型未锁定

**判定**：成立（轻微）

**理由**：

反方此攻击点成立，但严重程度为轻微：

1. **测试代码确认**：`tests/test_model.py` L221 `with pytest.raises((ValueError, TypeError)):` 确实使用了 `(ValueError, TypeError)` 元组。

2. **实际行为确认**：`compute_all_metrics` L769 `if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:` 对 `n_bins=1.5`：`isinstance(1.5, (int, np.integer))` 为 False → `not False` 为 True → 抛 **ValueError**（L770 `raise ValueError(...)`）。实际只会抛 ValueError，不会抛 TypeError。

3. **过度宽松**：测试用 `(ValueError, TypeError)` 元组接受 TypeError，但实际不会抛 TypeError。如果有人修改守卫使其对浮点数抛 TypeError（例如改用 `int(n_bins)` 转换而非 isinstance 检查），测试仍通过——**测试无法锁定异常类型**。

4. **可能的原因**：测试作者可能对守卫行为不确定（不确定会抛 ValueError 还是 TypeError），因此用元组兜底。R4 修复后守卫行为已明确（isinstance 检查 → ValueError），测试应明确为 `pytest.raises(ValueError)`。

5. **严重程度评估**：反方定级"轻微"合理。测试当前能通过，但异常类型未锁定，无法防止守卫行为退化。这是测试代码的风格问题，不影响当前正确性。

**若成立，修补方案**（可选改进）：

文件：`tests/test_model.py`
位置：L221
改动：1 行

```python
# 原代码
        with pytest.raises((ValueError, TypeError)):
            compute_all_metrics(probs, labels, n_bins=1.5)
# 改为
        with pytest.raises(ValueError):
            compute_all_metrics(probs, labels, n_bins=1.5)
```

---

### Attack-6: 测试未验证 ValueError 错误消息内容

**判定**：成立（轻微）

**理由**：

反方此攻击点成立，但严重程度为轻微：

1. **测试代码确认**：`tests/test_model.py` L217-222 只用 `pytest.raises(ValueError)`，未用 `match` 参数验证错误消息内容。

2. **源代码错误消息确认**：`src/utils/calibration.py` L770 `raise ValueError(f"n_bins must be a positive integer, got {n_bins}")` 包含 n_bins 实际值（用于调试）。

3. **回归风险**：如果有人把错误消息改为 `raise ValueError("invalid n_bins")`（丢失实际值），测试不会失败。错误消息中的实际值对调试有帮助，但丢失不影响守卫的正确性。

4. **R3 终审报告定位**：R3 终审报告 L247 可选改进项 A7"测试验证 ValueError 错误消息内容"明确标记为"轾微"。R4 未修复可选改进项不构成攻击成立（但反方攻击本身成立，只是严重程度低）。

5. **严重程度评估**：反方定级"轻微"合理。错误消息当前正确，测试未锁定，但不影响守卫功能。

**若成立，修补方案**（可选改进）：

文件：`tests/test_model.py`
位置：L213-215（brier_parts 守卫测试）和 L217-222（compute_all_metrics 守卫测试）
改动：增加 `match` 参数

```python
# 原代码
        for bad_n_bins in [0, -1, 1.5, "10"]:
            with pytest.raises(ValueError):
                brier_parts(probs, labels, n_bins=bad_n_bins)
# 改为
        for bad_n_bins in [0, -1, 1.5, "10"]:
            with pytest.raises(ValueError, match="n_bins must be a positive integer"):
                brier_parts(probs, labels, n_bins=bad_n_bins)
```

注意：`match` 参数使用正则表达式，`"n_bins must be a positive integer"` 会匹配消息前缀。如需验证实际值，可改为 `match=rf"n_bins must be a positive integer, got {re.escape(str(bad_n_bins))}"`，但需 `import re`。

---

### Attack-7: bootstrap_ece 双重守卫冗余——bootstrap_ece 守卫后 ece 守卫永不触发

**判定**：不成立

**理由**：

反方此攻击点不成立，属于对防御性编程最佳实践的误解：

1. **事实确认**：反方描述的代码事实正确——`bootstrap_ece` L551-552 守卫验证 n_bins 合法，L560/L581 调用 `ece` 传已验证合法的 n_bins，`ece` L215-216 守卫对已验证合法的 n_bins 在 bootstrap_ece 调用路径下永不触发。这部分事实无误。

2. **但"冗余"论断错误**：两个守卫各有其独立目的，非冗余：
   - **bootstrap_ece 守卫**：保护 bootstrap_ece 自身的入口，实现**快速失败**（fast-fail）。如果 n_bins 非法，在进入 bootstrap 循环前就拦截，避免循环内才失败（节省 n_bootstrap 次 ece 调用的无意义开销）。
   - **ece 守卫**：保护 ece 自身的入口。ece 是**公开 API**（非 `_` 前缀私有函数），可被直接调用（不通过 bootstrap_ece）。如果删除 ece 守卫，直接调用 `ece(n_bins=0)` 会静默返回 0.0（伪"完美校准"），这是 R3 终审报告 L227 明确指出的严重危害。

3. **防御性编程原则**：每个公开函数都应有自己的输入验证，不依赖调用方验证。这是"深度防御"（defense in depth）的基本原则。如果 ece 的守卫依赖 bootstrap_ece 的守卫，那么：
   - 直接调用 ece 时无守卫保护（ece 是公开 API）
   - bootstrap_ece 守卫被删除/绕过时，ece 无保护
   - 代码耦合度增加（ece 的安全性依赖 bootstrap_ece 的实现）

4. **反方自相矛盾**：反方在 A2 中攻击"ece/mce/bootstrap_ece 守卫无直接测试覆盖"（要求守卫存在且有测试），在 A7 中又攻击"bootstrap_ece 双重守卫冗余"（暗示守卫不应存在）。两个攻击点相互矛盾——如果 A7 成立（ece 守卫冗余应删除），那么 A2 的"删除 ece 守卫后测试仍通过"就不成立（因为守卫本就不应存在）。

5. **反方自己承认**：反方在论证中承认"冗余守卫无害（额外一次 isinstance 检查，O(1) 开销，可忽略）"。既然无害，就不构成攻击点。

6. **行业最佳实践**：NumPy、SciPy、scikit-learn 等主流库的公开函数都在各自入口做输入验证，即使被其他函数调用时"理论上冗余"。这是标准做法，非缺陷。

**若不成立，反驳**：

反方将"防御性编程的最佳实践"歪曲为"冗余"，属于稻草人论证。每个公开函数的入口守卫是独立必要的，不因调用方已验证而冗余。bootstrap_ece 守卫实现快速失败，ece 守卫保护直接调用路径，两者目的不同、各自必要。反方自己承认"无害"，不构成缺陷。此攻击点应关闭。

---

### Attack-8: 测试随机种子未固定——非确定性测试

**判定**：成立（轻微）

**理由**：

反方此攻击点成立，但严重程度为轻微：

1. **测试代码确认**：`tests/test_model.py` L203-204 `probs = np.random.rand(100); labels = (np.random.rand(100) > 0.5).astype(float)` 确实未固定随机种子。

2. **非确定性断言**：L208 `assert b5 != b10, "n_bins=5 和 n_bins=10 应产生不同结果"` 依赖随机数据使 n_bins=5 和 n_bins=10 产生不同结果。理论上存在数据使两者相等（如所有概率落在同一个 bin 内）。

3. **实际概率评估**：反方实测 1000 个种子下 b5==b10 发生 0 次，概率极低（<1/1000）。在 CI 环境中，如果 numpy 版本升级改变随机数生成算法，理论上可能触发，但实际概率极低。

4. **R3 终审报告定位**：R3 终审报告 L246 可选改进项 A6"测试固定随机种子"明确标记为"轾微"。R4 未修复可选改进项不构成攻击成立（但反方攻击本身成立，只是严重程度低）。

5. **严重程度评估**：反方定级"轻微"合理。理论非确定性，实际概率极低。但固定随机种子是测试最佳实践，应修复。

**若成立，修补方案**（可选改进）：

文件：`tests/test_model.py`
位置：L203 前
改动：增加随机种子固定

```python
    def test_brier_parts_n_bins_validation(self):
        """测试 brier_parts 的 n_bins 参数验证和生效"""
        from src.utils.calibration import brier_parts
        rng = np.random.default_rng(42)
        probs = rng.random(100)
        labels = (rng.random(100) > 0.5).astype(float)
        ...
```

注意：使用 `np.random.default_rng(42)` 而非 `np.random.seed(42)`，因为前者是 numpy 推荐的现代随机数生成方式，不污染全局随机状态。

---

## 总结

### 需R5修复的必修项清单（按优先级排序）

| 优先级 | 攻击点 | 文件 | 行号 | 改动内容 | 改动量 |
|--------|--------|------|------|---------|--------|
| P0-严重 | A1 | src/utils/calibration.py | L702后 | plot_reliability_diagram 函数体开头添加 n_bins 守卫 | 2行 |
| P0-严重 | A2 | tests/test_model.py | L222后 | test_brier_parts_n_bins_validation 中增加 ece/mce/bootstrap_ece 守卫直接测试 | 8-10行 |

**必修合计**：2 项，约 10-12 行改动

### 可选改进项清单（按优先级排序）

| 优先级 | 攻击点 | 文件 | 行号 | 改动内容 | 改动量 |
|--------|--------|------|------|---------|--------|
| P0-轻微 | A3 | tests/test_model.py | L222后 | 补充 compute_all_metrics 守卫测试边界值（"10"/None/1/np.int64） | 4-5行 |
| P0-轻微 | A4 | src/utils/calibration.py | 6处守卫 | 排除 bool 类型（isinstance(n_bins, bool) 排除） | 6行 |
| P0-轻微 | A5 | tests/test_model.py | L221 | pytest.raises((ValueError, TypeError)) 改为 pytest.raises(ValueError) | 1行 |
| P0-轻微 | A6 | tests/test_model.py | L213-222 | 测试增加 match 参数验证错误消息 | 2-3行 |
| P0-轻微 | A8 | tests/test_model.py | L203-204 | 测试固定随机种子 | 2行 |

**可选合计**：5 项，约 15-17 行改动

### 可关闭的攻击点及理由

| 攻击点 | 关闭理由 |
|--------|---------|
| A7 | **稻草人论证**。将"防御性编程的最佳实践"（每个公开函数入口独立验证）歪曲为"冗余"。bootstrap_ece 守卫实现快速失败，ece 守卫保护直接调用路径，两者目的不同、各自必要。反方自己承认"无害"。且 A7 与 A2 相互矛盾（A2 要求守卫存在，A7 暗示守卫冗余应删除）。 |

### 对R4修复质量的总体评价

**R4 修复部分达成目标，质量中等偏上**：

**优点**：
1. R3 终审报告的 2 个必修项均执行：ece/mce/bootstrap_ece 守卫代码正确、位置正确、与 brier_parts/compute_all_metrics 守卫完全一致；compute_all_metrics 守卫测试代码正确、能通过运行。
2. R3 攻击报告的攻击8（ece/mce 无守卫）和攻击8扩展（异常类型不一致）**已被 R4 修复**——5 个数值函数（brier_parts/ece/mce/bootstrap_ece/compute_all_metrics）对非法 n_bins 统一抛 ValueError。
3. 守卫代码风格一致，位置一致（docstring 后、probs 转换前），便于维护。

**不足**：
1. **修复范围不完整**（A1）：R4 机械执行了 R3 终审报告明确列出的 3 个函数（ece/mce/bootstrap_ece），未主动检查同模块其他接受 n_bins 的公开函数（plot_reliability_diagram）。R3 攻击报告攻击8 的根本原则"所有接受 n_bins 的公开函数都应有守卫"未被彻底贯彻。
2. **测试覆盖不完整**（A2）：R4 修复了代码但未添加对应的直接测试。新增的 ece/mce/bootstrap_ece 守卫无直接测试覆盖，存在回归风险。R3 攻击报告攻击7 的核心问题（守卫无测试覆盖）从 compute_all_metrics 转移到 ece/mce/bootstrap_ece，未被消除。
3. **边界值覆盖不全**（A3）：compute_all_metrics 守卫测试只覆盖 0/-1/1.5，缺 "10"/None 等边界值（轻微）。

**与 R3 终审报告 R4 必修要求的对比**：

| R3终审R4必修项 | R4实际执行 | 是否达标 |
|------------------------------------------------|-----------|---------|
| 必修1: ece/mce/bootstrap_ece 函数体开头各添加 n_bins 守卫 | ece L215-216 / mce L660-661 / bootstrap_ece L551-552 | ✅ 达标 |
| 必修1: 守卫代码与 compute_all_metrics 一致 | 5 处守卫代码完全一致 | ✅ 达标 |
| 必修1: 守卫在函数体最前面 | 均在 docstring 后、probs 转换前 | ✅ 达标 |
| 必修2: compute_all_metrics 守卫测试 | test_model.py L217-222 | ✅ 达标（但不完整） |
| 隐含: 消除所有接受 n_bins 的公开函数行为不一致 | plot_reliability_diagram 仍无守卫 | ❌ 未达标（A1） |
| 隐含: 新增守卫有测试覆盖 | ece/mce/bootstrap_ece 守卫无直接测试 | ❌ 未达标（A2） |

**收敛趋势**：

| 轮次 | P0-4 必修量 | 说明 |
|------|------------|------|
| R2→R3 | 14行（2严重） | compute_all_metrics 守卫 + 测试 |
| R3→R4 | 10行（1严重+1中等） | ece/mce/bootstrap_ece 守卫 + compute_all_metrics 守卫测试 |
| R4→R5(预期) | 10-12行（2严重） | plot_reliability_diagram 守卫 + ece/mce/bootstrap_ece 守卫测试 |

R4 修复了 R3 终审报告明确列出的必修项，但引入了 2 个新的严重攻击点（A1 修复范围不完整、A2 测试覆盖不完整）。攻击点从"代码无守卫"转移为"修复范围不完整"和"测试覆盖不完整"，严重程度未升级但也未完全收敛。**R5 修复后（plot_reliability_diagram 守卫 + ece/mce/bootstrap_ece 守卫测试，约 10-12 行）可完全收敛**，仅剩 5 个 P0-轻微可选改进项。

**最终判定**：P0-4 R4 轮修复**需 R5 轮修复**，必修 2 项约 10-12 行改动。
