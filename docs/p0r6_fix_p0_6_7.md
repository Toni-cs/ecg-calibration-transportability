# P0-6+7 R6轮Phase1正方修复报告

> **修复代理**：R6-Phase1 P0-6+7正方修复代理（GLM-5.2）
> **修复日期**：2026-09-10
> **任务ID**：134
> **依据**：`docs/p0r5_final_verdict.md` 第3.1节R6必修清单
> **修复范围**：P0-6+7 的 Attack-4 + Attack-5（E5 OOM备选 + 标签语义错位），1项必修，1个文件，1行改动

---

## 1. 修复项清单

| 优先级 | P0 | 攻击点 | 文件路径 | 行号 | 改动内容 | 改动量 |
|--------|-----|--------|---------|------|---------|--------|
| P0-中等 | P0-6+7 | Attack-4 + Attack-5 | `scripts/run_e5_inception_lite.py` | L592（修复后L593） | `n_ood=0,` → `n_ood=int(len(ood_probs)),` | 1 行 |

**修复合计**：1 项，1 行核心改动 + 2 行注释更新，涉及 1 个文件

---

## 2. 修改前后代码对比

### 2.1 修改前（R5 状态）

```python
# scripts/run_e5_inception_lite.py L583-597（R5 版本）
if len(cal_probs) == 0:
    print(f"[WARN] {source}→{target} seed={seed}: cal 集截断后为空，跳过 TS 校准")
    # R4 修复 Attack-1/2/4: 统一 schema + arch 用 source_info + 补截断统计字段
    # R5 修复 Attack-9: 补传 n_ood=0，使 early-return dict 与正常 result dict
    # schema 完全一致（cal 空导致 TS 校准跳过，无有效 ood 评估结果，n_ood=0）
    return _make_transfer_result(
        source=source, target=target, seed=seed,
        arch=source_info.get("arch", ARCH_NAME),
        num_classes=num_classes,
        n_ood=0,                                                    # ← 事实错误
        n_dropped_cal=int(n_dropped_cal), n_dropped_ood=int(n_dropped_ood),
        truncated=True,
        subspace_filtered=bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
        error="cal set empty after truncation", skipped=True,
    )
```

### 2.2 修改后（R6 修复）

```python
# scripts/run_e5_inception_lite.py L583-598（R6 版本）
if len(cal_probs) == 0:
    print(f"[WARN] {source}→{target} seed={seed}: cal 集截断后为空，跳过 TS 校准")
    # R4 修复 Attack-1/2/4: 统一 schema + arch 用 source_info + 补截断统计字段
    # R5 修复 Attack-9: 补传 n_ood，使 early-return dict 与正常 result dict
    # schema 完全一致。R6 修复 Attack-4/5: n_ood 应反映实际 ood 样本数
    # （cal 空不代表 ood 空，cal/ood 独立截断，ood_probs 此时可能非空）。
    return _make_transfer_result(
        source=source, target=target, seed=seed,
        arch=source_info.get("arch", ARCH_NAME),
        num_classes=num_classes,
        n_ood=int(len(ood_probs)),                                  # ← 修复后
        n_dropped_cal=int(n_dropped_cal), n_dropped_ood=int(n_dropped_ood),
        truncated=True,
        subspace_filtered=bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
        error="cal set empty after truncation", skipped=True,
    )
```

### 2.3 diff 摘要

```diff
--- a/scripts/run_e5_inception_lite.py
+++ b/scripts/run_e5_inception_lite.py
@@ -584,11 +584,12 @@
         print(f"[WARN] {source}→{target} seed={seed}: cal 集截断后为空，跳过 TS 校准")
         # R4 修复 Attack-1/2/4: 统一 schema + arch 用 source_info + 补截断统计字段
-        # R5 修复 Attack-9: 补传 n_ood=0，使 early-return dict 与正常 result dict
-        # schema 完全一致（cal 空导致 TS 校准跳过，无有效 ood 评估结果，n_ood=0）
-        return _make_transfer_result(
-            source=source, target=target, seed=seed,
-            arch=source_info.get("arch", ARCH_NAME),
-            num_classes=num_classes,
-            n_ood=0,
+        # R5 修复 Attack-9: 补传 n_ood，使 early-return dict 与正常 result dict
+        # schema 完全一致。R6 修复 Attack-4/5: n_ood 应反映实际 ood 样本数
+        # （cal 空不代表 ood 空，cal/ood 独立截断，ood_probs 此时可能非空）。
+        return _make_transfer_result(
+            source=source, target=target, seed=seed,
+            arch=source_info.get("arch", ARCH_NAME),
+            num_classes=num_classes,
+            n_ood=int(len(ood_probs)),
             n_dropped_cal=int(n_dropped_cal), n_dropped_ood=int(n_dropped_ood),
             truncated=True,
```

---

## 3. ood_probs 变量可用性确认

### 3.1 ood_probs 定义与处理链路

| 行号 | 代码 | 说明 |
|------|------|------|
| L532 | `ood_probs = tgt_eval["probs"]` | 首次定义（从目标数据集评估结果取出） |
| L549 | `ood_probs = ood_probs[ood_keep][:, :num_classes]` | 截断过滤（丢弃标签≥num_classes 的样本 + 截断概率列） |
| L567 | `ood_row_sums = ood_probs.sum(axis=1, keepdims=True)` | 计算行和（用于全零行检测） |
| L574 | `ood_probs = ood_probs[~ood_zero_rows]` | 丢弃全零行 |
| L579 | `ood_probs = ood_probs / ood_row_sums` | 归一化 |
| **L583** | `if len(cal_probs) == 0:` | **early-return 检查点** |
| **L593** | `n_ood=int(len(ood_probs))` | **修复后使用 ood_probs** |

### 3.2 作用域可用性结论

✅ **ood_probs 在 early-return 作用域内完全可用**。

理由：
1. **定义在前**：`ood_probs` 在 L532 首次定义，远早于 L583 的 early-return 检查。
2. **处理链完整**：在 L583 之前，`ood_probs` 已经过截断过滤（L549）和全零行丢弃（L574）+ 归一化（L579），反映的是经过所有清洗步骤后的实际有效 ood 样本数。
3. **无重定义风险**：L583 到 L593 之间没有任何对 `ood_probs` 的重新赋值或删除操作，变量绑定稳定。
4. **len() 安全**：`ood_probs` 是 numpy 数组（来自 `tgt_eval["probs"]`），`len()` 返回行数（样本数），即使数组为空也返回 0，不会抛异常。
5. **int() 转换安全**：`len()` 返回 Python int，`int()` 是冗余但安全的转换（与正常路径 L639 附近 `n_ood=int(len(ood_probs))` 的写法保持一致）。

### 3.3 与正常路径的一致性

正常路径（非 early-return）在 L639 附近构造 result dict 时，`n_ood` 也是 `int(len(ood_probs))`。修复后 cal empty 路径与正常路径的 `n_ood` 语义完全一致——均反映实际 ood 样本数。这同时解决了 Attack-5（两条路径 n_ood 值相同但含义不同）：修复后 cal empty 路径 `n_ood=int(len(ood_probs))`（可能 >0），ood empty 路径 `n_ood=0`（ood_probs 真为空），值不同可区分两种场景。

---

## 4. 验证结果

### 4.1 语法验证

```
$ python -c "import ast; ast.parse(open('scripts/run_e5_inception_lite.py', encoding='utf-8').read()); print('SYNTAX OK')"
SYNTAX OK
```

✅ **语法验证通过**，修改后的文件可被 Python AST 正确解析。

### 4.2 改动最小化确认

- ✅ 只修改了 `scripts/run_e5_inception_lite.py` 1 个文件
- ✅ 核心改动仅 1 行（`n_ood=0,` → `n_ood=int(len(ood_probs)),`）
- ✅ 附带 2 行注释更新（说明 R6 修复原因，保持代码可读性）
- ✅ 未触碰其他任何文件（未修改 `calibration.py`、`test_model.py`、`eval_l2_shift.py`、`run_e1a_l2_shift_full.py` 等）

### 4.3 语义正确性确认

| 场景 | 修复前 n_ood | 修复后 n_ood | 正确性 |
|------|------------|------------|--------|
| cal 空 + ood 非空 | 0（❌ 事实错误） | int(len(ood_probs)) > 0（✅ 反映实际） | ✅ 修复 |
| cal 空 + ood 空 | 0（✅ 恰好正确） | int(len(ood_probs)) == 0（✅ 仍正确） | ✅ 保持 |
| cal 非空 + ood 非空 | 不走此分支 | 不走此分支 | ✅ 不受影响 |
| cal 非空 + ood 空 | 不走此分支 | 不走此分支 | ✅ 不受影响 |

修复后所有场景的 `n_ood` 均正确反映实际 ood 样本数。

---

## 5. 与 R5 终审裁决的对照

### 5.1 R5 终审裁决原文（`docs/p0r5_final_verdict.md` 第2.3节）

> **Attack-4**（严重→降级中等）：cal 和 ood 独立截断，cal 空不代表 ood 空。n_ood=0 在 ood_probs 非空时事实错误。正常路径 n_ood=int(len(ood_probs))，cal empty 路径将 n_ood 语义偏移。事实错误属实，但 skipped=True 已标记，影响范围限于边界场景。
>
> **Attack-5**（严重→降级中等，Attack-4 衍生）：两条路径 n_ood 值相同但含义不同。修复 Attack-4 后自动解决（cal empty 路径 n_ood=int(len(ood_probs))，ood empty 路径 n_ood=0，值不同可区分）。

### 5.2 R6 必修项清单（第3.1节）

| 优先级 | P0 | 攻击点 | 文件路径 | 行号 | 改动内容 | 改动量 |
|--------|-----|--------|---------|------|---------|--------|
| P0-中等 | P0-6+7 | Attack-4 + Attack-5 | scripts/run_e5_inception_lite.py | L592 | `n_ood=0,` → `n_ood=int(len(ood_probs)),` | 1 行 |

### 5.3 修复符合性

✅ **完全符合 R5 终审裁决的 R6 必修要求**：
- 文件路径一致：`scripts/run_e5_inception_lite.py`
- 行号一致：L592（修复后因注释扩展为 L593，核心改动位置一致）
- 改动内容一致：`n_ood=0,` → `n_ood=int(len(ood_probs)),`
- 改动量一致：1 行核心改动
- 同时解决 Attack-4（事实错误）和 Attack-5（语义错位），与终审预期一致

---

## 6. 收敛预期

根据 R5 终审裁决第4.2节，R6 修复后 P0-6+7 的攻击点统计预期为：

| 致命 | 严重 | 中等 | 轾微 | 收敛状态 |
|------|------|------|------|---------|
| 0 | 0 | 0 | 5（选修） | **已收敛** |

本次修复清零了 P0-6+7 的最后 1 个中等攻击点（Attack-4+5）。剩余 5 个均为 P0-轻微选修项（Attack-1/3/6/7/13），不影响收敛判定。

---

## 7. 修复声明

本次修复严格遵循 R5 终审裁决 `docs/p0r5_final_verdict.md` 第3.1节 R6 必修清单，对 P0-6+7 的 Attack-4+5（n_ood 事实错误 + 标签语义错位）执行最小化修复：

- **修复文件**：`scripts/run_e5_inception_lite.py`
- **修复位置**：L592（修复后 L593）
- **改动内容**：`n_ood=0,` → `n_ood=int(len(ood_probs)),`
- **验证结果**：语法验证通过（SYNTAX OK），ood_probs 变量可用性确认，语义正确性确认
- **改动范围**：1 个文件，1 行核心改动 + 2 行注释更新，未触碰其他文件

修复后 P0-6+7 的致命/严重/中等攻击点全部清零，仅剩 5 个 P0-轻微选修项，符合 R5 终审预期的"R6 修复后可完全收敛"判定。
