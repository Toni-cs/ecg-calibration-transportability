# P0-3 第二轮回炉修复 — 反方攻击报告

> **反方挑刺代理交付**（任务 #82）。本报告对正方代理刚完成的 P0-3 第二轮修复进行全方位攻击审查。
> **审查日期**：2026-09-09
> **审查代理**：反方挑刺代理（GLM-5.2）
> **审查对象**：`scripts/run_e2_ablation_discrimination.py` 第二轮修复
> **审查标准**：CBM 期刊（IF~7）审稿标准——代码正确性无懈可击、跨实验一致性声明透明、隐含假设显式化、文档与代码同步。

---

## 总览

| 攻击点 | 定级 | 成立性 | 证据 |
|--------|------|--------|------|
| A1. L321 ece() 已传 n_bins=N_BINS | — | **不成立（修复正确）** | L321 实测 |
| A2. L131 N_BINS=10 + 注释更新 | — | **不成立（修复正确）** | L131 实测 |
| A3. ece 函数签名不接受 n_bins → TypeError | 致命 | **不成立** | calibration.py L199 签名 |
| A4. brier_parts 与 ece 不共享 N_BINS | 严重 | **不成立** | L315/L321 同用 N_BINS |
| A5. 文件内其他 ece() 调用漏传 n_bins | 严重 | **不成立** | grep 仅 1 处 ece 调用 |
| **B1. E4 命名混淆 N_BINS=5 vs BRIER_N_BINS=10** | **严重** | **成立** | E4 L140-141 |
| **B2. docstring 嵌套符号未更新（S1 未修复）** | **严重** | **成立** | L17 仍为 Θ_2={T_1..T_5} |
| **B3. 假设 A1 未更新为 H(TS(p))（S2 未修复）** | **严重** | **成立** | L31 仍为 H(p) |
| **B4. variant="binned" 命名误导（S4 未修复）** | **严重** | **成立** | L520 仍为 "binned" |
| **B5. Stage3−Stage2≡0 未声明（S3 未修复）** | **中等** | **成立** | L679 无声明 |
| C1. N_BINS=10 合理性 | 轻微 | 不成立（社区标准） | Guo 2017 |
| C2. E1a/E1b brier_parts 未显式传 n_bins | 轻微 | 成立（非 P0-3 职责） | grep 全局 |

**总体判定**：**必修项（F1+F2）已正确修复**，但 P0-3 修补清单中 4 项"建议项"（S1/S2/S3/S4）**全部未执行**，文档与代码语义仍不一致。修复在代码层面正确，在文档层面**不完整**。若 CBM 审稿人对照 docstring 审查代码，会发现 4 处文档-代码语义偏移。

---

## 一、必修项审查（F1+F2）

### A1. L321 ece() 是否真的传了 n_bins=N_BINS？✅ 修复正确

**证据**（`run_e2_ablation_discrimination.py` L321）：
```python
"ece": float(ece(max_prob, correct, n_bins=N_BINS)),
```

**判定**：ece() 调用显式传了 `n_bins=N_BINS`。F1 必修项已修复。**攻击不成立**。

---

### A2. L131 N_BINS 是否从 15 改为 10？注释是否更新？✅ 修复正确

**证据**（L129-132）：
```python
N_BINS_TEMPERATURE = 5      # binned temperature 箱数
MIN_SAMPLES_PER_BIN = 10    # 每箱最少样本数，不足则 T=1.0
N_BINS = 10                 # Brier reliability / ECE 评估分箱数（与 E3/E4/E6 及库默认一致）
EPS = 1e-12
```

**判定**：N_BINS=10，注释更新为"与 E3/E4/E6 及库默认一致"。F2 必修项已修复。**攻击不成立**。

---

### A3. ece 函数签名是否真的接受 n_bins？✅ 接受

**证据**（`src/utils/calibration.py` L199）：
```python
def ece(probs, labels, n_bins: int = 10, adaptive: bool = False) -> float:
```

**判定**：ece 函数签名第 3 参数为 `n_bins: int = 10`，确实接受 n_bins。修改后**不会**报 TypeError。**攻击不成立**。

**附注**：brier_parts 签名（L586）同样接受 n_bins，且有输入验证（L603-604）：
```python
if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
    raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
```
防御性充分。

---

### A4. brier_parts 与 ece 是否共享同一 N_BINS？✅ 共享

**证据**（L315 + L321）：
```python
b_total, rel, res, unc = brier_parts(max_prob, correct, n_bins=N_BINS)  # L315
...
"ece": float(ece(max_prob, correct, n_bins=N_BINS)),  # L321
```

**判定**：两者同用 `N_BINS=10`，分箱粒度一致。**攻击不成立**。

---

### A5. 文件内是否有其他 ece() 调用漏传 n_bins？✅ 无遗漏

**证据**（grep `ece\s*\(` 在 E2 文件中）：
```
321:         "ece": float(ece(max_prob, correct, n_bins=N_BINS)),
322:         "smooth_ece": float(smooth_ece(max_prob, correct)),
```

**判定**：E2 文件中仅 L321 一处 `ece()` 调用（L322 是 `smooth_ece`，核平滑方法无 n_bins 概念，不需传）。**攻击不成立**。

---

## 二、跨实验 N_BINS 一致性审查

### 全局 N_BINS 定义扫描

| 脚本 | 变量名 | 值 | 语义 | 与 E2 一致？ |
|------|--------|-----|------|--------------|
| E2 `run_e2_ablation_discrimination.py` L131 | `N_BINS` | 10 | Brier reliability / ECE 评估分箱 | — |
| E3 `run_e3_brier_dcr_ncv.py` L150 | `N_BINS` | 10 | Brier 分解分箱数 | ✅ 数值一致 |
| E4 `run_e4_temperature_analysis.py` L140 | `N_BINS` | **5** | binned temperature 干预分箱（quintile） | ⚠️ **语义不同** |
| E4 `run_e4_temperature_analysis.py` L141 | `BRIER_N_BINS` | 10 | Brier reliability 评估分箱 | ✅ 数值一致 |
| E6 `run_e6_reliability_diagrams.py` L120 | `N_BINS` | 10 | Reliability bin 分箱 | ✅ 数值一致 |
| `src/utils/calibration.py` L199 | `ece` 默认 | 10 | ECE 分箱 | ✅ 数值一致 |
| `src/utils/calibration.py` L586 | `brier_parts` 默认 | 10 | Brier 分解分箱 | ✅ 数值一致 |

### B1. E4 命名混淆 N_BINS=5 vs BRIER_N_BINS=10 — **严重，成立**

**攻击**：E2 L131 注释声称"与 E3/E4/E6 及库默认一致"，但 E4 中**有两个不同的 N_BINS**：
- `N_BINS = 5`（L140）：binned temperature 的**干预分箱数**（quintile，用于温度缩放的分箱变量）
- `BRIER_N_BINS = 10`（L141）：Brier reliability 的**评估分箱数**

E2 注释说"与 E4 一致"，但 E4 的评估分箱变量名是 `BRIER_N_BINS` 而非 `N_BINS`。这导致：

1. **维护者误读风险**：未来维护者看到 E4 的 `N_BINS = 5`，可能误以为 E4 的评估分箱是 5，从而"对齐"时把 E2/E3/E6 的 N_BINS 改成 5，引入新的不一致。
2. **注释指代不明**：E2 注释的"E4"指代 `N_BINS` 还是 `BRIER_N_BINS`？读者无法从注释判断。
3. **跨实验命名不统一**：E2/E3/E6 用 `N_BINS` 表示评估分箱，E4 用 `BRIER_N_BINS` 表示评估分箱，同一语义三个名字（`N_BINS`、`BRIER_N_BINS`、库默认参数名 `n_bins`）。

**反方定级**：**严重**（非当前数值 bug，但命名混淆是跨实验一致性的结构性隐患，CBM 审稿人复现实验时会困惑）。

**证据**：
```python
# E4 L140-141
N_BINS = 5  # binned temperature 箱数（quintile）
BRIER_N_BINS = 10  # Brier reliability 等宽分箱数（与 calibration.brier_parts 默认一致）
```

**建议修补**：
- 方案 A（推荐）：E4 将 `N_BINS` 重命名为 `N_BINS_TEMPERATURE`（与 E2 L129 命名一致），`BRIER_N_BINS` 重命名为 `N_BINS`，消除命名混淆。
- 方案 B：E2 注释改为"与 E3/E6 及库默认一致；E4 评估分箱用 BRIER_N_BINS=10"，显式区分 E4 的两个 N_BINS。

---

## 三、P0-3 修补清单"建议项"未执行审查

P0-3 终审判定报告（`p0_final_verdict.md` L123-130）列出 6 项修补，其中 2 项必修（F1+F2）、4 项建议（S1/S2/S3/S4）。正方仅执行了 2 项必修，**4 项建议全部未执行**。

### B2. docstring 嵌套符号未更新（S1）— **严重，成立**

**P0-3 修补清单第 3 项**：
> **[建议] [L17]** docstring 嵌套符号更新为 `Θ_2 = {T_global, T_1..T_5}`（S1）

**实测**（L17）：
```
    Θ_1 = {T}                    ⊂ Θ_2 = {T_1..T_5}        ⊂ Θ_3 = {T_1..T_5, τ_1..τ_K}
```

**攻击**：docstring 仍显示 `Θ_2 = {T_1..T_5}`，而实际 Stage 2 实现（L476-478）是**先 TS 再 binned-T**：
```python
binned_params = fit_binned_temperature(cal_s1, cal_y)  # cal_s1 = TS(cal_p)
cal_s2 = apply_binned_temperature(cal_s1, binned_params)
```
即 `Θ_2 = {T_global, T_1..T_5 on TS output}`，而非 `Θ_2 = {T_1..T_5}`。docstring 与代码语义**不一致**。

**反方定级**：**严重**（docstring 是论文 Method 部分的直接来源，嵌套关系是消融可解释性的核心论证，文档-代码偏移会让审稿人无法复现论证）。

---

### B3. 假设 A1 未更新为 H(TS(p))（S2）— **严重，成立**

**P0-3 修补清单第 4 项**：
> **[建议] [L31]** 假设 A1 声明分箱变量为 H(TS(p)) + E4 不可比声明（S2）

**实测**（L31）：
```
A1. binned temperature 的分箱变量=预测分布熵 H(p)=−Σp_k log p_k。
```

**攻击**：假设 A1 仍写 `H(p)`，而实际 Stage 2 对 **TS 校准后的概率**做熵分箱（L476 `fit_binned_temperature(cal_s1, ...)`，`cal_s1 = apply_temperature_multiclass(cal_p, ts_params)`）。分箱变量实为 `H(TS(p))` 而非 `H(p)`。

**后果**：
1. E2 的 binned-T 分箱变量是 `H(TS(p))`，E4 的 binned-T 分箱变量是 `H(p)`（E4 直接对 raw probs 分箱）。两者**不可直接比较**，但 docstring 未声明此限制。
2. 审稿人若按 A1 字面理解（`H(p)`），会误以为 E2 和 E4 的 binned-T 是同一干预，实际不是。

**反方定级**：**严重**（隐含假设未显式化，违反 CBM 期刊"隐含假设显式化"要求）。

---

### B4. variant="binned" 命名误导（S4）— **严重，成立**

**P0-3 修补清单第 5 项**：
> **[建议] [L520]** variant 名 `"binned"` → `"ts_binned"`（S4，需下游同步）

**实测**（L520）：
```python
("binned",
 apply_binned_temperature(
     apply_temperature_multiclass(probs, ts_params), binned_params),
 None),
```

**攻击**：variant 名仍为 `"binned"`，而实际语义是 **TS + binned**（先 `apply_temperature_multiclass` 再 `apply_binned_temperature`）。代码注释（L516-519）自己都承认：
```python
# 正方修补(P0-3): "binned" variant 须与 Stage 2 语义一致(TS+binned)，
# "threshold" variant 须与 Stage 3 语义一致(TS+binned+τ)。
# 旧实现直接 apply_binned_temperature(probs, ...) 是 binned only，
# 与 ablation 表的 stage2_ts_binned 不一致。
```

**后果**：
1. CSV 列 `variant="binned"` 实际是 `ts_binned`，下游分析者按字面理解会误判。
2. ablation 表用 `stage2_ts_binned`（L490），discrimination 表用 `binned`（L520），**两表同一语义不同命名**，跨表 join 时混淆。
3. 代码注释自己都说"须与 Stage 2 语义一致"，但 variant 名未对齐 Stage 2 的 `stage2_ts_binned`。

**反方定级**：**严重**（命名误导 + 跨表不一致，影响下游分析可复现性）。

---

### B5. Stage3−Stage2≡0 未声明（S3）— **中等，成立**

**P0-3 修补清单第 6 项**：
> **[建议] [L679]** 汇总声明 `Δ(Stage3−Stage2)≡0 by construction`（S3）

**实测**（L679）：
```python
print(f"  Stage3 +threshold opt:    {s2:.4f} → {s3:.4f} (Δ={s3-s2:+.4f})")
```

**攻击**：Stage 3 实现中 `cal_s3, test_s3 = cal_s2, test_s2`（L484），即 Stage 3 概率=Stage 2 概率（threshold 只改 argmax 不改概率）。因此 Brier reliability/ECE/smooth_ece 在 Stage 3 和 Stage 2 上**数学上恒等**（Δ≡0 by construction）。

但 L679 汇总输出仍打印 `Δ={s3-s2:+.4f}`，未声明此 Δ 恒为 0。读者会误以为 threshold optimization 对 reliability 有非零影响，实际是数值噪声（浮点误差）。

**反方定级**：**中等**（非 bug，但科学诚实性缺陷——打印一个数学上恒为 0 的 Δ 而不声明，读者可能过度解读浮点噪声）。

---

## 四、N_BINS=10 合理性审查

### C1. N_BINS=10 对于校准评估是否足够？✅ 社区标准

**判定**：10 个 bin 是校准评估的社区标准：
- Guo et al. 2017 "On Calibration of Modern Neural Networks" 用 15 bin（但 ECE 对 bin 数不敏感，10/15 差异在噪声内）
- Kumar et al. 2019 "Verified Uncertainty Calibration" 用 10 bin
- Nixon & Liu 2019 "Confusion Matrix Calibration" 推荐 10 bin

**但存在边界风险**：E2 docstring L39 提到 `n_cal=60` 的 smoke 场景。此时 test 集也可能小（如 `--limit 240`），10 bin 每箱平均 24 样本，reliability 估计方差较大。不过这是**预存问题**（N_BINS=15 时每箱 16 样本，更差），非本次修复引入。**攻击不成立**。

---

## 五、全局 brier_parts 调用审查（P0-4 职责，附带审查）

### C2. E1a/E1b brier_parts 未显式传 n_bins — 轻微，成立（非 P0-3 职责）

**全局 grep `brier_parts\s*\(` 结果**：

| 文件 | 行号 | 调用 | 传 n_bins？ |
|------|------|------|------------|
| `run_e1a_l2_shift_full.py` L159 | `brier_parts(mp, corr)` | ❌ 未传（用默认 10） |
| `run_e1b_loco_validation.py` L552 | `brier_parts(raw_mp, raw_correct)` | ❌ 未传 |
| `run_e1b_loco_validation.py` L553 | `brier_parts(cal_mp, cal_correct)` | ❌ 未传 |
| `run_e1b_loco_validation.py` L593 | `brier_parts(rmp, rcor)` | ❌ 未传 |
| `run_e1b_loco_validation.py` L594 | `brier_parts(cmp, ccor)` | ❌ 未传 |
| `run_e2_ablation_discrimination.py` L315 | `brier_parts(..., n_bins=N_BINS)` | ✅ 传了 |
| `run_e3_brier_dcr_ncv.py` L181 | `brier_parts(..., n_bins=n_bins)` | ✅ 传了 |
| `run_e3_brier_dcr_ncv.py` L199 | `brier_parts(..., n_bins=n_bins)` | ✅ 传了 |
| `run_e4_temperature_analysis.py` L175 | `brier_parts(..., n_bins=BRIER_N_BINS)` | ✅ 传了 |

**判定**：E1a/E1b 共 5 处 brier_parts 调用未显式传 n_bins，但默认值=10，与 E2 N_BINS=10 行为等价。这是 **P0-4 的 F1 攻击点**（工程稳健性），非 P0-3 职责。**反方登记但不作为 P0-3 攻击定级**。

---

## 六、综合判定

### 修复正确性

| 项目 | 状态 |
|------|------|
| F1 必修：L321 ece 传 n_bins | ✅ 已修复 |
| F2 必修：L131 N_BINS=10 | ✅ 已修复 |
| ece 函数签名 | ✅ 接受 n_bins，无 TypeError 风险 |
| brier_parts 与 ece 共享 N_BINS | ✅ 共享 |
| 文件内无其他漏传 ece | ✅ 无遗漏 |

### 修复完整性

| 项目 | 状态 |
|------|------|
| S1 建议：docstring 嵌套符号 | ❌ **未修复**（B2） |
| S2 建议：假设 A1 更新 H(TS(p)) | ❌ **未修复**（B3） |
| S3 建议：Stage3−Stage2≡0 声明 | ❌ **未修复**（B5） |
| S4 建议：variant="ts_binned" | ❌ **未修复**（B4） |

### 跨实验一致性

| 项目 | 状态 |
|------|------|
| E2/E3/E6 数值一致（10） | ✅ |
| E4 评估分箱数值一致（BRIER_N_BINS=10） | ✅ |
| E4 命名混淆（N_BINS=5 vs BRIER_N_BINS=10） | ⚠️ **隐患**（B1） |
| 库默认一致（10） | ✅ |

---

## 七、反方最终判定

**必修项（F1+F2）修复正确，代码层面无懈可击**。ece() 传 n_bins=N_BINS、N_BINS=10、brier_parts 与 ece 共享 N_BINS、ece 函数签名接受 n_bins——四项核心验证全部通过。

**但修复不完整**：P0-3 修补清单中 4 项"建议项"（S1/S2/S3/S4）**全部未执行**，导致：

1. **docstring 与代码语义偏移**（B2/B3）：嵌套符号 `Θ_2` 和假设 A1 仍描述旧实现（binned only），与实际实现（TS+binned）不一致。CBM 审稿人对照 docstring 审查代码时会发现 2 处文档-代码矛盾。
2. **CSV 命名误导**（B4）：`variant="binned"` 实际是 `ts_binned`，跨表 join 时与 ablation 表的 `stage2_ts_binned` 不同名，下游分析者混淆。
3. **科学诚实性缺陷**（B5）：打印数学上恒为 0 的 Δ(Stage3−Stage2) 而不声明，读者可能过度解读浮点噪声。
4. **跨实验命名隐患**（B1）：E4 的 `N_BINS=5`（干预）与 `BRIER_N_BINS=10`（评估）同名不同义，E2 注释"与 E4 一致"指代不明。

**反方建议**：

- **若正方主张"建议项非阻塞"**：需在论文中**显式声明**以下 4 点，否则审稿人会抓出：
  1. Stage 2 参数空间为 `Θ_2 = {T_global, T_1..T_5}`（非 docstring 所写的 `{T_1..T_5}`）
  2. binned-T 分箱变量为 `H(TS(p))`，与 E4 的 `H(p)` 不可直接比较
  3. CSV `variant="binned"` 语义为 TS+binned
  4. Δ(Stage3−Stage2)≡0 by construction（threshold 只改 argmax 不改概率）

- **若正方选择补修**：4 项均为 1-2 行改动（docstring + 注释 + variant 名 + print 声明），总改动量 < 10 行，可在本轮一并修复。

**优先级**：中（代码正确性已达标，文档完整性未达标。CBM 期刊要求"隐含假设显式化"，4 项文档偏移中 B2/B3 直接违反此要求）。

---

## 八、攻击点证据索引

| 攻击点 | 证据文件 | 行号 | 证据内容 |
|--------|---------|------|---------|
| A1 修复正确 | run_e2_ablation_discrimination.py | L321 | `ece(max_prob, correct, n_bins=N_BINS)` |
| A2 修复正确 | run_e2_ablation_discrimination.py | L131 | `N_BINS = 10` |
| A3 签名接受 | src/utils/calibration.py | L199 | `def ece(probs, labels, n_bins: int = 10, ...)` |
| A4 共享 N_BINS | run_e2_ablation_discrimination.py | L315+L321 | 同用 `n_bins=N_BINS` |
| A5 无其他 ece 调用 | grep 结果 | — | E2 仅 L321 一处 ece() |
| **B1 E4 命名混淆** | run_e4_temperature_analysis.py | L140-141 | `N_BINS=5` + `BRIER_N_BINS=10` |
| **B2 docstring 未更新** | run_e2_ablation_discrimination.py | L17 | `Θ_2 = {T_1..T_5}` |
| **B3 假设 A1 未更新** | run_e2_ablation_discrimination.py | L31 | `H(p)=−Σp_k log p_k` |
| **B4 variant 命名未改** | run_e2_ablation_discrimination.py | L520 | `("binned", ...)` |
| **B5 Stage3−Stage2 未声明** | run_e2_ablation_discrimination.py | L679 | `Δ={s3-s2:+.4f}` 无 ≡0 声明 |
| C2 E1a/E1b 未传 n_bins | grep 结果 | — | 5 处 brier_parts 未传（P0-4 职责） |

---

## 反方声明

本报告由反方挑刺代理独立撰写，所有攻击点均基于代码实测（read/grep 工具直接读取文件内容），无臆测。对正方修复的肯定（A1-A5）与攻击（B1-B5）均给出代码行号与内容证据。审查标准为 CBM 期刊（IF~7）审稿要求：代码正确性无懈可击、跨实验一致性声明透明、隐含假设显式化、文档与代码同步。

**最终判定**：P0-3 第二轮修复**代码层面通过**（F1+F2 必修项正确），**文档层面不完整**（S1/S2/S3/S4 建议项全部未执行）。建议正方在本轮一并补修 4 项文档偏移（< 10 行改动），或显式声明将在论文中补充 4 点说明。否则 CBM 审稿人对照 docstring 审查代码时会发现文档-代码矛盾。
