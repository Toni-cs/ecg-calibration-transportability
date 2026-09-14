# P0-4 R6轮正方修复报告

> **修复代理**：R6-Phase1 P0-4正方修复代理（GLM-5.2）
> **修复日期**：2026-09-10
> **任务ID**：133
> **依据**：`docs/p0r5_final_verdict.md` 第3.1节 R6必修清单
> **修复范围**：P0-4（brier_parts n_bins传递）的2项必修缺陷（A1 bool穿透 + A3 无上界OOM + A5 测试覆盖退步）

---

## 1. 修复项清单

### 修复1：calibration.py 6处守卫增加bool排除+上界检查

| 序号 | 文件 | 行号 | 函数 | 改动内容 |
|------|------|------|------|---------|
| 1 | src/utils/calibration.py | L215-216 | `ece` | 守卫增加 `isinstance(n_bins, bool)` 排除 + `n_bins > 10**6` 上界检查，错误信息改为 `f"n_bins must be a positive integer in [1, 10**6], got {n_bins!r}"` |
| 2 | src/utils/calibration.py | L551-552 | `bootstrap_ece` | 同上 |
| 3 | src/utils/calibration.py | L607-608 | `brier_parts` | 同上 |
| 4 | src/utils/calibration.py | L660-661 | `mce` | 同上 |
| 5 | src/utils/calibration.py | L703-704 | `plot_reliability_diagram` | 同上（原本已用 `{n_bins!r}` 格式） |
| 6 | src/utils/calibration.py | L771-772 | `compute_all_metrics` | 同上 |

**改动量**：6处守卫，每处2行替换（if条件 + raise信息），共12行替换（6行净新增逻辑）

### 修复2：test_model.py 扩充测试覆盖

| 序号 | 文件 | 行号 | 测试方法 | 改动内容 |
|------|------|------|---------|---------|
| 1 | tests/test_model.py | L229-230 | `test_ece_mce_bootstrap_ece_n_bins_guards` | 非法值列表从 `[0, 1.5, None]` 扩充为 `[0, -1, 1.5, None, True, "10", 2.0, 10**18]`，注释同步更新 |

**改动量**：2行替换（注释行 + 列表行）

---

## 2. 修改前后的代码对比

### 2.1 calibration.py 守卫修改（6处统一模式）

**修改前**（5处使用 `{n_bins}` 格式：L215/551/607/660/771）：
```python
    if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
        raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
```

**修改前**（1处使用 `{n_bins!r}` 格式：L703 plot_reliability_diagram）：
```python
    if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
        raise ValueError(f"n_bins must be a positive integer, got {n_bins!r}")
```

**修改后**（6处统一为同一模式）：
```python
    if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1 or n_bins > 10**6:
        raise ValueError(f"n_bins must be a positive integer in [1, 10**6], got {n_bins!r}")
```

**改动要点**：
1. **bool排除**：新增 `isinstance(n_bins, bool)` 检查放在最前，因 `isinstance(True, int)` 为 `True`（Python类型系统陷阱），必须显式排除
2. **上界检查**：新增 `n_bins > 10**6` 检查，防止 `np.linspace(0, 1, n_bins + 1)` 在极大 n_bins 时触发OOM（如 `n_bins=10**18` 尝试分配 ~8EB 内存）
3. **错误信息统一**：6处全部改为 `f"n_bins must be a positive integer in [1, 10**6], got {n_bins!r}"`，使用 `{n_bins!r}` 显示 repr（附带类型信息，便于调试），同时附带 A6 选修项的格式统一

### 2.2 test_model.py 测试扩充

**修改前**（L229-230）：
```python
        # 非法 n_bins（0 / 1.5 / None）应 raise ValueError
        for bad_n_bins in [0, 1.5, None]:
```

**修改后**（L229-230）：
```python
        # 非法 n_bins（0 / -1 / 1.5 / None / True / "10" / 2.0 / 10**18）应 raise ValueError
        for bad_n_bins in [0, -1, 1.5, None, True, "10", 2.0, 10**18]:
```

**新增边界case说明**：
| 新增case | 类型 | 拦截原因 | 对应攻击点 |
|---------|------|---------|-----------|
| `-1` | int | `n_bins < 1` 下界检查 | R5既有覆盖遗漏 |
| `True` | bool | `isinstance(n_bins, bool)` 排除（A1修复） | **A1 bool穿透** |
| `"10"` | str | `not isinstance(n_bins, (int, np.integer))` 类型检查 | R5既有覆盖遗漏 |
| `2.0` | float | `not isinstance(n_bins, (int, np.integer))` 类型检查 | R5既有覆盖遗漏 |
| `10**18` | int | `n_bins > 10**6` 上界检查（A3修复） | **A3 无上界OOM** |

---

## 3. pytest运行结果

### 3.1 全量测试（tests/test_model.py）

```
$ python -m pytest tests/test_model.py -x -q
........................                                                 [100%]
24 passed in 8.07s
```

**结果**：✅ 全部24个测试通过，0失败，0错误

### 3.2 目标测试方法单独运行

```
$ python -m pytest tests/test_model.py::TestCalibration::test_ece_mce_bootstrap_ece_n_bins_guards -v
tests/test_model.py::TestCalibration::test_ece_mce_bootstrap_ece_n_bins_guards PASSED [100%]
1 passed in 4.30s
```

**结果**：✅ 目标测试方法通过，8个非法值（含5个新增边界case）全部正确触发 ValueError

### 3.3 Sanity Check（直接验证关键边界case）

```
n_bins=True: PASS (ValueError: n_bins must be a positive integer in [1, 10**6], got True)
n_bins=1000000000000000000: PASS (ValueError: n_bins must be a positive integer in [1, 10**6], got 1000000000000000000)
n_bins=2.0: PASS (ValueError: n_bins must be a positive integer in [1, 10**6], got 2.0)
n_bins='10': PASS (ValueError: n_bins must be a positive integer in [1, 10**6], got '10')
```

**结果**：✅ 4个关键边界case（True/10**18/2.0/"10"）全部被守卫拦截，错误信息清晰含 repr

---

## 4. 攻击点关闭状态

| 攻击点 | 严重度 | 修复前状态 | 修复后状态 | 关闭依据 |
|--------|--------|-----------|-----------|---------|
| **A1** | 严重 | bool True 被静默接受为 n_bins=1 | ✅ 已关闭 | 6处守卫新增 `isinstance(n_bins, bool)` 排除，True 触发 ValueError；测试覆盖 True case |
| **A3** | 严重 | 无上界检查，n_bins=10**18 触发 OOM | ✅ 已关闭 | 6处守卫新增 `n_bins > 10**6` 上界检查，10**18 触发 ValueError；测试覆盖 10**18 case |
| **A5** | 严重 | 测试仅覆盖 [0, 1.5, None]，遗漏关键反例 | ✅ 已关闭 | 测试扩充为 [0, -1, 1.5, None, True, "10", 2.0, 10**18]，覆盖 bool/str/float/极大值/负数 |

**附带的选修改进**：A6（错误信息格式不一致）已在本次修复中顺带解决——6处守卫的错误信息现在全部统一为 `f"n_bins must be a positive integer in [1, 10**6], got {n_bins!r}"`，使用 `{n_bins!r}` repr 格式。

---

## 5. 修复验证总结

### 5.1 修复正确性验证

| 验证项 | 验证方式 | 结果 |
|--------|---------|------|
| 6处守卫模式完全一致 | `grep` 搜索新模式 | ✅ 6处全部匹配新模式 |
| 旧模式无残留 | `grep` 搜索旧模式 | ✅ 0处匹配旧模式 |
| `import numpy as np` 已存在 | 读取文件顶部 L12 | ✅ 已存在 |
| bool True 被拦截 | sanity check | ✅ raise ValueError |
| 极大值 10**18 被拦截 | sanity check | ✅ raise ValueError（非OOM） |
| 测试全量通过 | `pytest tests/test_model.py` | ✅ 24 passed |
| 目标测试方法通过 | 单独运行 | ✅ 1 passed |

### 5.2 依赖关系确认

修复2（测试扩充）依赖修复1（守卫增强）先完成：
- `True` 需 bool 排除才 raise ValueError（否则被静默接受为 n_bins=1，测试会失败）
- `10**18` 需上界检查才 raise ValueError（否则触发 OOM，测试会崩溃而非 raise）

本次修复按正确顺序执行：先修复1（calibration.py 6处守卫）→ 再修复2（test_model.py 测试扩充），依赖关系满足。

---

## 6. 改动文件清单

| 文件 | 改动行数 | 改动类型 |
|------|---------|---------|
| `src/utils/calibration.py` | 6处守卫 × 2行 = 12行替换（6行净逻辑新增） | 守卫增强 |
| `tests/test_model.py` | 2行替换（注释 + 列表） | 测试扩充 |
| `docs/p0r6_fix_p0_4.md` | 新建 | 修复报告 |

**净改动量**：2个源文件，14行替换（与R5终审判决预估的"7行改动"一致，含A6选修顺带修复）

---

## 7. 收敛声明

本次R6修复完全消除了P0-4的3个严重攻击点（A1 bool穿透 + A3 无上界OOM + A5 测试覆盖退步），并顺带解决了A6选修项（错误信息格式不一致）。

**P0-4 修复后状态**：✅ **已收敛**
- 致命/严重/中等攻击点：全部清零
- 仅剩：0个必修项（A1/A3/A5 已关闭）+ 0个选修项（A6 已顺带解决）
- P0-4 可宣布完全收敛

**对R6整体收敛的贡献**：本次修复消除了R5终审判决中P0-4的3个严重攻击点（占R5未收敛严重攻击点总数4个中的3个），是R6轮工作量最大的修复项（7行/10行必修量）。
