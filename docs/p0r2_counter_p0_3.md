# P0-3 反反方审查报告（R2轮）

## 审查概要
- 攻击报告：docs/p0r2_attack_p0_3.md
- 攻击点总数：12（A1-A5 自评不成立 + B1-B5 自评成立 + C1-C2 附带审查）
- **成立：3** | **部分成立：2** | **不成立：7**

### 判定分布

| 攻击点 | 反方自评 | 反反方判定 | 分歧 |
|--------|---------|-----------|------|
| A1. L321 ece 传 n_bins | 不成立 | **不成立** | 一致 |
| A2. L131 N_BINS=10 | 不成立 | **不成立** | 一致 |
| A3. ece 签名接受 n_bins | 不成立 | **不成立** | 一致 |
| A4. brier_parts 与 ece 共享 N_BINS | 不成立 | **不成立** | 一致 |
| A5. 无其他 ece() 漏传 | 不成立 | **不成立** | 一致 |
| **B1. E4 命名混淆** | 成立（严重） | **部分成立** | **严重程度夸大** |
| **B2. docstring L17 未更新** | 成立（严重） | **成立** | 一致 |
| **B3. 假设 A1 L31 未更新** | 成立（严重） | **成立** | 一致 |
| **B4. variant="binned" 命名误导** | 成立（严重） | **部分成立** | **严重程度夸大** |
| **B5. Stage3−Stage2≡0 未声明** | 成立（中等） | **成立** | 一致（但定级偏轻） |
| C1. N_BINS=10 合理性 | 不成立 | **不成立** | 一致 |
| C2. E1a/E1b 未传 n_bins | 成立（非P0-3职责） | **不成立** | **越界** |

---

## 逐条审查

### 攻击点 A1: L321 ece() 已传 n_bins=N_BINS
**判定**: 不成立
**分析**: 实测 `run_e2_ablation_discrimination.py` L321：
```python
"ece": float(ece(max_prob, correct, n_bins=N_BINS)),
```
ece() 调用显式传了 `n_bins=N_BINS`。F1 必修项已正确修复。反方此项自评"不成立（修复正确）"，反反方确认一致——这不是一个有效攻击点，而是反方对正方修复的肯定。
**反驳**: 攻击不成立。代码正确。

---

### 攻击点 A2: L131 N_BINS=10 + 注释更新
**判定**: 不成立
**分析**: 实测 L129-132：
```python
N_BINS_TEMPERATURE = 5      # binned temperature 箱数
MIN_SAMPLES_PER_BIN = 10    # 每箱最少样本数，不足则 T=1.0
N_BINS = 10                 # Brier reliability / ECE 评估分箱数（与 E3/E4/E6 及库默认一致）
EPS = 1e-12
```
N_BINS=10，注释已更新为"与 E3/E4/E6 及库默认一致"。F2 必修项已正确修复。反方自评"不成立"，反反方确认一致。
**反驳**: 攻击不成立。代码正确。

---

### 攻击点 A3: ece 函数签名不接受 n_bins → TypeError
**判定**: 不成立
**分析**: 实测 `src/utils/calibration.py` L199：
```python
def ece(probs, labels, n_bins: int = 10, adaptive: bool = False) -> float:
```
ece 函数签名第 3 参数为 `n_bins: int = 10`，确实接受 n_bins。修改后不会报 TypeError。brier_parts 签名（L586）同样接受 n_bins，且有输入验证（L603-604）。
**反驳**: 攻击不成立。签名兼容，无 TypeError 风险。

---

### 攻击点 A4: brier_parts 与 ece 不共享 N_BINS
**判定**: 不成立
**分析**: 实测 L315 + L321：
```python
b_total, rel, res, unc = brier_parts(max_prob, correct, n_bins=N_BINS)  # L315
"ece": float(ece(max_prob, correct, n_bins=N_BINS)),                     # L321
```
两者同用 `N_BINS=10`，分箱粒度一致。
**反驳**: 攻击不成立。共享同一 N_BINS。

---

### 攻击点 A5: 文件内其他 ece() 调用漏传 n_bins
**判定**: 不成立
**分析**: grep `ece\s*\(` 在 E2 文件中仅返回 2 行：
```
321:         "ece": float(ece(max_prob, correct, n_bins=N_BINS)),
322:         "smooth_ece": float(smooth_ece(max_prob, correct)),
```
L321 是唯一的 `ece()` 调用；L322 是 `smooth_ece`（核平滑方法，无 n_bins 概念，不需传）。
**反驳**: 攻击不成立。无遗漏调用。

---

### 攻击点 B1: E4 命名混淆 N_BINS=5 vs BRIER_N_BINS=10
**判定**: 部分成立
**分析**:

**成立部分**：E4 确实存在命名混淆。实测 `run_e4_temperature_analysis.py` L140-141：
```python
N_BINS = 5  # binned temperature 箱数（quintile）
BRIER_N_BINS = 10  # Brier reliability 等宽分箱数（与 calibration.brier_parts 默认一致）
```
E4 用 `N_BINS` 表示温度干预分箱（5），用 `BRIER_N_BINS` 表示评估分箱（10），而 E2/E3/E6 用 `N_BINS` 表示评估分箱（10）。同一变量名 `N_BINS` 在 E4 和 E2/E3/E6 中语义不同，这是真实的命名不一致隐患。

**夸大部分**：反方定级"严重"被夸大，理由如下：

1. **E2 注释上下文已消歧**：E2 L131 注释完整文本为"Brier reliability / ECE 评估分箱数（与 E3/E4/E6 及库默认一致）"。注释前半句"Brier reliability / ECE 评估分箱数"已明确限定语义为**评估分箱**，读者据此可对应到 E4 的 `BRIER_N_BINS=10`（L141 注释也是"Brier reliability 等宽分箱数"），而非 E4 的 `N_BINS=5`（L140 注释是"binned temperature 箱数"）。注释指代并非"不明"——上下文已消歧。

2. **数值一致性正确**：E2 N_BINS=10 = E3 N_BINS=10 = E4 BRIER_N_BINS=10 = E6 N_BINS=10 = 库默认 10。所有评估分箱数值全部一致，无实际 bug。

3. **E4 命名是预存问题，非 P0-3 引入**：E4 的 `N_BINS=5` / `BRIER_N_BINS=10` 命名在 P0-3 修复前就已存在。P0-3 的职责是修复 E2，不是重构 E4 的变量命名。反方建议的"方案 A"（E4 重命名）会修改 E4 源文件，属于跨实验重构，超出 P0-3 职责范围。

4. **"维护者误读风险"是假设性风险**：反方说"未来维护者看到 E4 的 N_BINS=5，可能误以为 E4 的评估分箱是 5，从而把 E2/E3/E6 改成 5"。这是假设性风险，非当前 bug。且 E4 L140-141 的注释已清晰区分两个变量的语义，认真读注释的维护者不会误读。

**反反方定级**：**轻微**（命名可改进，但注释已消歧，数值一致，无实际 bug）。

**修补方案**（可选，非阻塞）：E2 L131 注释微调，显式区分 E4 的两个变量：
```python
# 文件: scripts/run_e2_ablation_discrimination.py
# 行号: L131
# 改动:
N_BINS = 10  # Brier reliability / ECE 评估分箱数（与 E3/E6 及库默认一致；E4 对应 BRIER_N_BINS=10）
```
此改动 1 行，不涉及 E4 文件，不引入跨实验重构风险。

---

### 攻击点 B2: docstring 嵌套符号未更新（S1 未修复）
**判定**: 成立
**分析**: 实测 L17：
```
    Θ_1 = {T}                    ⊂ Θ_2 = {T_1..T_5}        ⊂ Θ_3 = {T_1..T_5, τ_1..τ_K}
```

实际 Stage 2 实现（L464-478）：
```python
# Stage 1: TS only
ts_params = fit_temperature_multiclass(cal_p, cal_y)       # L465
cal_s1 = apply_temperature_multiclass(cal_p, ts_params)    # L467

# Stage 2: TS + binned temperature
binned_params = fit_binned_temperature(cal_s1, cal_y)      # L476 ← 对 cal_s1=TS(cal_p) 分箱
cal_s2 = apply_binned_temperature(cal_s1, binned_params)   # L477
```

Stage 2 先做 TS（得 `cal_s1`），再在 TS 输出上做 binned-T。因此 Stage 2 的参数空间为 `Θ_2 = {T_global, T_1..T_5}`（全局 T + 5 个分箱 T），而非 docstring 所写的 `Θ_2 = {T_1..T_5}`。

docstring 的嵌套关系 `Θ_1 ⊂ Θ_2 ⊂ Θ_3` 在数学上要求 Θ_2 是 Θ_1 的超集。若 `Θ_1 = {T}` 而 `Θ_2 = {T_1..T_5}`，则 Θ_1 ⊄ Θ_2（{T} 不是 {T_1..T_5} 的子集），嵌套关系**数学上不成立**。正确的写法应为 `Θ_2 = {T, T_1..T_5}`，此时 `{T} ⊂ {T, T_1..T_5}` 嵌套成立。

代码注释 L471-475 自己都承认了这一点：
```python
# 旧实现直接对 raw cal_p/test_p 做 binned-T（=binned only），导致
# Stage 2 实际是 Θ={T_1..T_5} 而非 Θ={T_global, T_1..T_5 on TS output}，
# 破坏了 Stage1 ⊂ Stage2 的嵌套关系
```

但 docstring L17 未同步更新，仍描述旧实现的参数空间。这是文档-代码语义偏移。

**反反方定级**：**严重**（同意反方）。docstring 是论文 Method 部分的直接来源，嵌套关系是消融可解释性的核心论证。Θ_1 ⊂ Θ_2 在当前 docstring 中数学上不成立，审稿人对照检查会发现矛盾。

**修补方案**：
```python
# 文件: scripts/run_e2_ablation_discrimination.py
# 行号: L17
# 原文:
    Θ_1 = {T}                    ⊂ Θ_2 = {T_1..T_5}        ⊂ Θ_3 = {T_1..T_5, τ_1..τ_K}
# 改为:
    Θ_1 = {T}                    ⊂ Θ_2 = {T, T_1..T_5}     ⊂ Θ_3 = {T, T_1..T_5, τ_1..τ_K}
```

---

### 攻击点 B3: 假设 A1 未更新为 H(TS(p))（S2 未修复）
**判定**: 成立
**分析**: 实测 L31：
```
A1. binned temperature 的分箱变量=预测分布熵 H(p)=−Σp_k log p_k。
```

实际实现 L476：`binned_params = fit_binned_temperature(cal_s1, cal_y)`，其中 `cal_s1 = apply_temperature_multiclass(cal_p, ts_params)`（L467）。即分箱变量是对 **TS 校准后的概率** `cal_s1` 计算熵，而非对原始概率 `cal_p` 计算熵。

`fit_binned_temperature` 内部（L160）调用 `_entropy(cal_probs)`，传入的 `cal_probs` 是 `cal_s1`（TS 输出）。因此分箱变量实为 `H(TS(p))`，而非 `H(p)`。

假设 A1 写 `H(p)` 与实际实现 `H(TS(p))` 不一致。后果：

1. **E2 vs E4 不可直接比较**：E2 的 binned-T 分箱变量是 `H(TS(p))`（先 TS 再分箱），E4 的 binned-T 分箱变量是 `H(p)`（直接对 raw probs 分箱，E4 L160 对 raw cal_p 调用 `_entropy`）。两者分箱变量不同，binned-T 的语义不同，不可直接比较——但 docstring 未声明此限制。

2. **审稿人误读风险**：审稿人若按 A1 字面理解（`H(p)`），会误以为 E2 和 E4 的 binned-T 是同一干预，实际不是。这影响跨实验对比结论的有效性。

**反反方定级**：**严重**（同意反方）。隐含假设未显式化，违反 CBM 期刊"隐含假设显式化"要求。分箱变量的差异直接影响 binned-T 的拟合结果和 Stage2−Stage1 边际贡献的可解释性。

**修补方案**：
```python
# 文件: scripts/run_e2_ablation_discrimination.py
# 行号: L31-34
# 原文:
A1. binned temperature 的分箱变量=预测分布熵 H(p)=−Σp_k log p_k。
    假设：不确定度高的样本段需要不同的锐度校准（置信与不确定样本
    的 over/under-confidence 模式不同）。若该假设不成立，
    Stage2−Stage1 ≈ 0（脚本会如实报告）。
# 改为:
A1. binned temperature 的分箱变量=TS 校准后预测分布熵 H(TS(p))=−Σ p'_k log p'_k，
    其中 p'=TS(p)（Stage 1 的温度缩放输出）。注意：E4 的 binned-T 分箱变量
    为 H(p)（对原始概率分箱），两者分箱变量不同，不可直接比较。
    假设：不确定度高的样本段需要不同的锐度校准（置信与不确定样本
    的 over/under-confidence 模式不同）。若该假设不成立，
    Stage2−Stage1 ≈ 0（脚本会如实报告）。
```

---

### 攻击点 B4: variant="binned" 命名误导（S4 未修复）
**判定**: 部分成立
**分析**:

**成立部分**：实测 L520：
```python
("binned",
 apply_binned_temperature(
     apply_temperature_multiclass(probs, ts_params), binned_params),
 None),
```
variant 名为 `"binned"`，但实际语义是 **TS + binned**（先 `apply_temperature_multiclass` 再 `apply_binned_temperature`）。ablation 表用 `stage2_ts_binned`（L490），discrimination 表用 `binned`（L520），同一语义两个名字，跨表 join 时需映射。

**夸大部分**：反方定级"严重"被夸大，理由如下：

1. **代码注释已显式文档化**：L516-519 有详细注释：
   ```python
   # 正方修补(P0-3): "binned" variant 须与 Stage 2 语义一致(TS+binned)，
   # "threshold" variant 须与 Stage 3 语义一致(TS+binned+τ)。
   # 旧实现直接 apply_binned_temperature(probs, ...) 是 binned only，
   # 与 ablation 表的 stage2_ts_binned 不一致。
   ```
   任何阅读源码的分析者都能看到此注释，理解 "binned" 的实际语义。这不是"未文档化的误导"，而是"命名简写 + 注释补充说明"。

2. **variant 名是短标签，非完整描述**：discrimination 表的 variant 列设计为短标签（`raw`/`ts`/`binned`/`threshold`），对应消融的 4 个阶段。若改为 `ts_binned`，则 `threshold` 也应改为 `ts_binned_threshold`，列值变长，可读性下降。短标签 + 注释是合理的工程权衡。

3. **下游影响**：反方自己标注 S4"需下游同步"。改名会改变 CSV 列值，所有下游分析脚本（读取 `variant=="binned"` 的代码）需同步修改。这是有破坏性的改动，不应在"建议项"中轻率执行。

4. **跨表映射简单**：ablation 表 `stage2_ts_binned` ↔ discrimination 表 `binned`，映射关系一目了然（ablation 表的 stage 名带前缀 `stageN_`，discrimination 表的 variant 名是去前缀的短标签）。下游 join 时按文档映射即可，非"混淆"而是"命名约定不同"。

**反反方定级**：**中等**（命名可改进，但注释已文档化，改名有下游影响，非"严重"误导）。

**修补方案**（可选，需评估下游影响）：若正方决定改名，需同步检查所有读取 `discrimination_metrics_60exp.csv` 的下游脚本：
```python
# 文件: scripts/run_e2_ablation_discrimination.py
# 行号: L520
# 原文:
            ("binned",
# 改为:
            ("ts_binned",
# 行号: L524
# 原文:
            ("threshold",
# 改为:
            ("ts_binned_threshold",
# 同时需修改 L684 的汇总循环:
# 原文: for variant in ["raw", "ts", "binned", "threshold"]:
# 改为: for variant in ["raw", "ts", "ts_binned", "ts_binned_threshold"]:
```
**注意**：此改动会改变 CSV 输出的 variant 列值，需同步更新所有下游分析脚本。建议在 P0-3 范围内仅添加注释说明，改名留待下游同步时一并处理。

---

### 攻击点 B5: Stage3−Stage2≡0 未声明（S3 未修复）
**判定**: 成立
**分析**: 实测 L484 + L679：

L484：
```python
cal_s3, test_s3 = cal_s2, test_s2
```
Stage 3 概率**就是** Stage 2 概率（同一对象引用，非拷贝）。threshold optimization 只改 argmax（L205 `(probs - thresholds).argmax(axis=1)`），不改概率本身。

L679：
```python
print(f"  Stage3 +threshold opt:    {s2:.4f} → {s3:.4f} (Δ={s3-s2:+.4f})")
```
由于 `test_s3 is test_s2`（同一对象），`calibration_reliability(test_s3, test_y)` 与 `calibration_reliability(test_s2, test_y)` 输入完全相同，输出必然完全相同（`calibration_reliability` 是确定性函数，无随机性）。因此 `s3 == s2` 精确成立（非浮点噪声，是精确相等），`Δ` 恒为 `+0.0000`。

但 L679 打印 `Δ={s3-s2:+.4f}` 时未声明此 Δ 数学上恒为 0。读者看到 `Δ=+0.0000` 可能：
1. 误以为 threshold optimization 对 reliability 恰好零影响（巧合），而非数学上必然为零（构造性）。
2. 若出现浮点噪声（虽然本例不会，因输入完全相同），可能过度解读为 threshold 有微小效果。

这是科学诚实性缺陷：打印一个数学上恒为 0 的量而不声明其构造性为零的原因。

**反反方定级**：**轻微至中等**（同意反方"中等"方向，但实际影响偏轻——因为 Δ 会精确显示 0.0000，读者从数值本身已可判断无影响。缺陷在于未解释**为什么**为零）。

**修补方案**：
```python
# 文件: scripts/run_e2_ablation_discrimination.py
# 行号: L679
# 原文:
        print(f"  Stage3 +threshold opt:    {s2:.4f} → {s3:.4f} (Δ={s3-s2:+.4f})")
# 改为:
        print(f"  Stage3 +threshold opt:    {s2:.4f} → {s3:.4f} (Δ={s3-s2:+.4f}, ≡0 by construction: threshold只改argmax不改概率)")
```

---

### 攻击点 C1: N_BINS=10 合理性
**判定**: 不成立
**分析**: 10 个 bin 是校准评估的社区标准（Kumar 2019, Nixon & Liu 2019）。Guo 2017 用 15 bin，但 ECE 对 bin 数不敏感，10/15 差异在噪声内。反方自评"不成立（社区标准）"，反反方确认一致。
**反驳**: 攻击不成立。N_BINS=10 符合社区标准。

---

### 攻击点 C2: E1a/E1b brier_parts 未显式传 n_bins
**判定**: 不成立
**分析**: 反方自己标注"非 P0-3 职责"。E1a/E1b 的 `brier_parts` 调用未传 n_bins，但使用默认值 10，与 E2 N_BINS=10 行为等价。这是 P0-4 的工程稳健性问题，不属于 P0-3 审查范围。将非 P0-3 职责的问题纳入 P0-3 攻击报告，是**越界审查**。

**反驳**: 攻击不成立（对 P0-3 而言）。E1a/E1b 的 brier_parts 调用属于 P0-4 职责范围，不应在 P0-3 攻击报告中定级。反方自己亦承认"非 P0-3 职责"，却仍以"成立"登记，自相矛盾。

---

## 总结

### 需要进一步修复的问题清单

| 优先级 | 问题 | 攻击点 | 改动量 | 修补方案 |
|--------|------|--------|--------|---------|
| **高** | docstring L17 嵌套符号 Θ_2 缺 T | B2 | 1 行 | `Θ_2 = {T_1..T_5}` → `Θ_2 = {T, T_1..T_5}`，Θ_3 同步 |
| **高** | 假设 A1 L31 分箱变量 H(p) → H(TS(p)) | B3 | 2-3 行 | 更新 A1 描述 + 添加 E4 不可比声明 |
| **中** | L679 Δ(Stage3−Stage2) 未声明 ≡0 | B5 | 1 行 | print 中追加 "≡0 by construction" 说明 |
| **低** | E2 L131 注释 E4 指代消歧 | B1 | 1 行 | 注释改为"E4 对应 BRIER_N_BINS=10" |
| **低**（需下游同步） | variant="binned" → "ts_binned" | B4 | 3-4 行 + 下游 | 改名 + 同步下游脚本 |

**总改动量**：高优先级 2 项（B2+B3）共约 4 行，可在本轮一并修复。中优先级 1 项（B5）约 1 行。低优先级 2 项（B1+B4）可选修复。

### 已确认修复完成的问题

| 问题 | 验证结果 |
|------|---------|
| F1 必修：L321 ece 传 n_bins=N_BINS | ✅ 已修复（L321 实测） |
| F2 必修：L131 N_BINS=10 + 注释更新 | ✅ 已修复（L131 实测） |
| ece 函数签名接受 n_bins | ✅ 兼容（calibration.py L199） |
| brier_parts 与 ece 共享 N_BINS | ✅ 共享（L315+L321 同用 N_BINS） |
| 文件内无其他 ece() 漏传 | ✅ 无遗漏（grep 仅 L321） |
| brier_parts 输入验证 | ✅ 防御性充分（L603-604） |

### 对正方修复的总体评价

**代码层面：优秀**。F1+F2 必修项修复正确，ece() 显式传 n_bins=N_BINS、N_BINS=10 与跨实验一致、brier_parts 与 ece 共享分箱粒度、函数签名兼容——四项核心验证全部通过。代码注释（L314, L471-475, L516-519）详尽说明了修复意图和旧实现问题，工程质量高。

**文档层面：不完整**。P0-3 修补清单中 4 项"建议项"（S1/S2/S3/S4）全部未执行，导致 2 处文档-代码语义偏移（B2 docstring 嵌套符号、B3 假设 A1 分箱变量）和 1 处科学诚实性缺陷（B5 Δ≡0 未声明）。其中 B2/B3 直接违反 CBM 期刊"隐含假设显式化"要求，建议本轮一并修复（共约 4 行改动）。B4 命名误导有代码注释兜底，严重程度被反方夸大，可延后处理。B1 是 E4 的预存命名问题，非 P0-3 引入，E2 注释微调即可消歧。

**反方攻击质量评价**：反方攻击报告整体质量较高，B2/B3/B5 三个攻击点证据扎实、定级合理，有效揭示了文档-代码偏移。但 B1 和 B4 两个攻击点存在严重程度夸大：B1 忽略了 E2 注释上下文已消歧、E4 命名是预存问题非 P0-3 职责；B4 忽略了代码注释已显式文档化、改名有下游影响。C2 将 P0-4 职责纳入 P0-3 攻击，属于越界审查。反方在"建议项"全部未执行这一点上判断准确，但将所有"建议项"未执行都定为"严重"有定级通胀之嫌——B5 实际影响偏轻（Δ 精确显示 0.0000），B4 有注释兜底。

---

## 反反方声明

本报告由反反方审查代理独立撰写，所有判定均基于代码实测（read/grep 工具直接读取文件内容），无臆测。对反方攻击的肯定（B2/B3/B5）与反驳（B1 部分夸大/B4 部分夸大/C2 越界）均给出代码行号与内容证据。审查标准与反方一致：CBM 期刊（IF~7）审稿要求。

**最终判定**：反方攻击报告 12 个攻击点中，**3 个成立**（B2/B3/B5，文档-代码偏移需修复）、**2 个部分成立**（B1/B4，方向正确但严重程度夸大）、**7 个不成立**（A1-A5 确认修复正确 + C1 社区标准 + C2 越界）。正方 P0-3 第二轮修复**代码层面通过**，**文档层面需补修 B2+B3（约 4 行，高优先级）+ B5（1 行，中优先级）**。
