# P0-3 修复反方攻击报告

> **反方挑刺代理-P0-3 交付**。本报告对正方 P0-3 修复（`scripts/run_e2_ablation_discrimination.py` Stage 2 消融逻辑修复）进行逐行审查，从 7 个攻击维度寻找修复后的残留问题、修复不完整处、及修复引入的新不一致。
> **攻击日期**：2026-09-09
> **攻击对象**：`scripts/run_e2_ablation_discrimination.py`（712 行，P0-3 修复后版本）
> **攻击代理**：反方挑刺代理-P0-3（GLM-5.2）
> **诚实原则**：对每条攻击给出可验证的具体代码行号或反例，不允许"可能有问题"的空泛指控。若修复确实正确，明确声明。
> **攻击维度**：反例构造 / 逻辑断链 / 隐含假设 / 边界失效 / 自相矛盾 / 量级错误 / 语义偏移（7 维度全覆盖）

---

## 0. 攻击审查概述

### 修复内容回顾

P0-3 修复了 `run_e2_ablation_discrimination.py` 中 Stage 2 消融逻辑错误。原问题（P0-1 F1）：Stage 2 应为 TS+binned-T，但旧实现直接在 raw 概率上做 binned-T（binned only），破坏了 Stage1⊂Stage2 嵌套。修复方案：
- Stage 2 核心逻辑改为 `fit_binned_temperature(cal_s1, cal_y)` + `apply_binned_temperature(cal_s1/test_s1, ...)`（L476-478）
- 判别指标 "binned" 变体改为 TS+binned（L520-523）
- 新增 `N_BINS=15` 常量（L131）
- `brier_parts` 调用添加 `n_bins=N_BINS`（L315）

### 攻击数量统计

| 严重性 | 数量 | 编号 |
|--------|------|------|
| **致命** | 2 | F1, F2 |
| **严重** | 4 | S1, S2, S3, S4 |
| **轻微** | 3 | M1, M2, M3 |
| **合计** | 9 | — |

### 整体评估

**修复的核心逻辑（Stage 2 先 TS 再 binned-T）经审查确认正确**：L476-478 确实将 `cal_s1`（TS 校准后概率）传入 `fit_binned_temperature`，并在 `cal_s1`/`test_s1` 上 apply binned-T。P0-1 的 F1 攻击点已被有效修复。判别指标 "binned" 变体（L520-523）也正确改为 TS+binned 语义。

**但修复存在 2 个致命残留问题**，任一独立成立即可削弱修复的可信度：

1. **F1（ECE 与 Brier reliability 分箱数不一致——修复不完整）**：`calibration_reliability` 函数中 `brier_parts` 用 `n_bins=N_BINS=15`，但同函数内 `ece()` 调用（L321）未传 `n_bins`，使用默认值 10。同一函数内两个校准指标用不同分箱粒度，修复只补了 `brier_parts` 漏了 `ece`。

2. **F2（N_BINS=15 与全代码库不一致——跨实验比较失效）**：E2 用 15，E3/E4/E6 及 `calibration.py` 库默认均用 10。E2 的 Brier reliability/ECE 无法与 E3/E4/E6 横向比较。无 15 的合理性论证。

4 个严重攻击进一步暴露修复的文档同步问题和度量退化：docstring 嵌套符号未更新（S1）、分箱变量语义偏移 H(raw)→H(TS(p)) 未声明（S2）、Stage 3 Brier reliability 恒等于 Stage 2（S3）、variant="binned" 命名误导（S4）。

**结论：P0-3 修复的核心逻辑正确，但修复不完整（F1）且引入了跨实验不一致（F2）。需补充修复。**

---

## 1. 致命攻击（方案完全失败）

### F1：`calibration_reliability` 内 ECE 与 Brier reliability 分箱数不一致——修复只补了一半

**攻击维度**：自相矛盾 + 逻辑断链

**修复声称**（L131 注释 + L314-315 注释）：
```python
N_BINS = 15                 # Brier reliability / ECE 评估分箱数（校准评估粒度）
# 正方修补(P0-3): 显式传 n_bins=N_BINS，使 Brier reliability 分箱粒度可控
b_total, rel, res, unc = brier_parts(max_prob, correct, n_bins=N_BINS)
```

注释明确声称 `N_BINS=15` 是 "Brier reliability **/ ECE** 评估分箱数"。

**代码实现**（L306-323 `calibration_reliability` 函数）：
```python
def calibration_reliability(probs: np.ndarray, labels: np.ndarray) -> dict:
    max_prob = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == labels).astype(float)
    b_total, rel, res, unc = brier_parts(max_prob, correct, n_bins=N_BINS)  # ← 15 箱
    return {
        "brier_reliability": float(rel),
        ...
        "ece": float(ece(max_prob, correct)),               # ← 默认 10 箱！未传 n_bins
        "smooth_ece": float(smooth_ece(max_prob, correct)),  # ← 核方法，无分箱
    }
```

**攻击点**：
- L315：`brier_parts(..., n_bins=N_BINS)` → 15 箱 ✓（已修复）
- L321：`ece(max_prob, correct)` → **未传 `n_bins`**，使用 `calibration.py` L199 的默认值 `n_bins=10`
- 同一函数内，Brier reliability 用 15 箱，ECE 用 10 箱。**两个校准指标的分箱粒度不一致**。

**为什么致命**：
1. **修复声称与实现矛盾**：L131 注释声称 `N_BINS=15` 同时用于 "Brier reliability / ECE"，但 ECE 实际用 10。注释是虚假的。
2. **指标间不可比**：Brier reliability 和 ECE 是消融实验的两个主量。若分箱粒度不同，"Brier reliability 改善 0.02 对应 ECE 改善 0.03" 这类联合解读失效——两者在不同粒度下估计，无法判断哪个指标对校准更敏感。
3. **修复意图未完成**：若 P0-3 的意图是"统一分箱粒度以可控评估"，则只修 `brier_parts` 不修 `ece` 是半成品。若意图仅修 `brier_parts`，则 L131 注释不应提及 ECE。

**可验证反例**：
- 设 `max_prob = [0.05, 0.15, 0.25, ..., 0.95]`（10 个等距点），`correct = [0,1,0,1,...]`。
- `brier_parts(max_prob, correct, n_bins=15)`：15 箱，每箱约 0-1 个样本，多数箱为空 → reliability 估计高方差。
- `ece(max_prob, correct)`（默认 10 箱）：10 箱，每箱恰好 1 个样本 → ECE 估计不同。
- 两个指标在不同分箱下计算，联合报告无意义。

**严重程度**：**致命**——修复声称统一分箱粒度但实际只统一了一半，消融表的核心指标间不可比。

**修复建议**：L321 改为 `ece(max_prob, correct, n_bins=N_BINS)`，或修改 L131 注释删除 "/ ECE"。

---

### F2：N_BINS=15 与全代码库不一致——跨实验 Brier reliability 横向比较失效

**攻击维度**：隐含假设 + 量级错误

**E2 修复后**（L131）：
```python
N_BINS = 15                 # Brier reliability / ECE 评估分箱数
```

**全代码库 Brier/ECE 分箱数统计**（经 grep 验证）：

| 脚本 | 常量 | 值 | 用途 |
|------|------|----|------|
| `run_e2_ablation_discrimination.py`（P0-3 修复后） | `N_BINS` | **15** | Brier reliability 评估 |
| `run_e3_brier_dcr_ncv.py` | `N_BINS` | **10** | Brier 分解（L150） |
| `run_e4_temperature_analysis.py` | `BRIER_N_BINS` | **10** | Brier reliability 等宽分箱（L141） |
| `run_e6_reliability_diagrams.py` | `N_BINS` | **10** | 可靠性图分箱（L120） |
| `src/utils/calibration.py` `brier_parts` 默认 | — | **10** | 库默认（L586） |
| `src/utils/calibration.py` `ece` 默认 | — | **10** | 库默认（L199） |

**攻击点**：
- E2 用 15 箱，**所有其他脚本和库默认用 10 箱**。
- E2 的 `brier_reliability` 列无法与 E3 的 `brier_parts_toplabel` 结果横向比较——不同分箱数产生不同的 reliability 估计。
- E2 的 `ece` 列（即便修复 F1 后用 15）也无法与 E4 的 `ece_toplabel`（用 10）比较。
- **无任何文档或注释解释为什么选 15**。L131 仅写 "校准评估粒度"，未给出 15 vs 10 的理由。

**为什么致命**：
1. **跨实验元分析失效**：论文通常需要联合 E2（消融）+ E3（Brier 分解）+ E4（温度分析）的结果。若 E2 的 Brier reliability 用 15 箱而 E3/E4 用 10 箱，"E2 Stage 2 的 reliability=0.03 vs E4 binned-T 的 reliability=0.025" 这类对比无意义——差异可能纯粹来自分箱粒度不同，而非校准方法差异。
2. **分箱数影响 reliability 估计值**：Brier reliability = Σ_bin (n_bin/n)(avg_prob_bin − avg_label_bin)²。更多箱 → 每箱样本更少 → avg 估计方差更大 → reliability 估计偏高（overfitting to bin noise）。15 箱比 10 箱系统性高估 reliability，使 E2 的校准改善看起来比 E3/E4 更大（虚假收益）。
3. **与 E4 的显式对齐声称矛盾**：E4 L141 注释 `BRIER_N_BINS = 10  # 与 calibration.brier_parts 默认一致`——E4 显式对齐库默认 10，而 E2 修复引入 15 破坏了这个对齐。

**可验证反例**：
- 设 `max_prob` 在 [0.0, 0.1] 区间有 100 个样本，`correct` 的真实校准率为 0.05。
- 10 箱：[0.0,0.1] 是一个箱，avg_prob≈0.05，avg_label≈0.05 → reliability 贡献≈0。
- 15 箱：[0.0, 0.0667] 和 [0.0667, 0.1] 两个箱，若样本分布不均，两个箱的 avg_prob ≠ avg_label → reliability 贡献 > 0。
- 同一数据，15 箱的 reliability 系统性 ≥ 10 箱的 reliability。E2 的 reliability 数值不可与 E3/E4 直接比较。

**严重程度**：**致命**——E2 的消融结果无法与 E3/E4/E6 横向对比，论文的跨实验联合论证失效。

**修复建议**：将 `N_BINS` 改为 10（与 E3/E4/E6 及库默认对齐），或若确需 15 则同步修改 E3/E4/E6 并给出 15 的统计理由（如样本量 ≥ 1500 时 15 箱的 bias-variance tradeoff 更优）。

---

## 2. 严重攻击（需重大修补）

### S1：docstring 嵌套符号 Θ_2={T_1..T_5} 与修复后实现不一致——文档未同步更新

**攻击维度**：自相矛盾 + 语义偏移

**docstring 声称**（L17，P0-3 修复后仍未更新）：
```
Θ_1 = {T}                    ⊂ Θ_2 = {T_1..T_5}        ⊂ Θ_3 = {T_1..T_5, τ_1..τ_K}
```

这描述 Stage 2 的参数空间为 `{T_1..T_5}`（5 个分箱温度，**无全局 T**）——即旧的 "binned only" 设计。

**修复后实际实现**（L465-478）：
```python
ts_params = fit_temperature_multiclass(cal_p, cal_y)      # T_global（Stage 1）
cal_s1 = apply_temperature_multiclass(cal_p, ts_params)
binned_params = fit_binned_temperature(cal_s1, cal_y)     # T_1..T_5（在 TS 输出上）
cal_s2 = apply_binned_temperature(cal_s1, binned_params)
```

Stage 2 实际参数空间 = `{T_global, T_1..T_5}`（6 个参数：先全局 T，再 5 个分箱 T）。

**攻击点**：
- docstring L17 写 `Θ_2 = {T_1..T_5}`（5 参数），实际是 `{T_global, T_1..T_5}`（6 参数）。
- 修复改了代码但**未同步更新 docstring**。L14-20 的"核心主张"整段仍描述旧设计。
- L18 `ΔReliability(Stage2−Stage1) = binned T 的边际贡献（控制全局 T 后）`——这句解释在修复后是正确的，但 L17 的符号 `Θ_2 = {T_1..T_5}` 与之矛盾（符号说 5 参数，解释说"控制全局 T 后"暗示 6 参数）。

**为什么严重**：
1. **读者误判参数空间**：依赖 docstring 的读者会认为 Stage 2 只有 5 个自由参数（binned only），而实际有 6 个（TS + binned）。参数计数影响自由度分析、AIC/BIC 比较、过拟合风险评估。
2. **嵌套关系的数学表述错误**：正确的嵌套应为 `Θ_1 = {T_global} ⊂ Θ_2 = {T_global, T_1..T_5} ⊂ Θ_3 = {T_global, T_1..T_5, τ_1..τ_K}`。当前 docstring 的 `Θ_1 = {T} ⊂ Θ_2 = {T_1..T_5}` 在集合论上不成立——`{T}` 不是 `{T_1..T_5}` 的子集（不同符号）。

**严重程度**：**严重**——核心设计文档与实现不一致，影响论文写作和后续维护者的正确理解。

**修复建议**：更新 L17 为 `Θ_1 = {T_global} ⊂ Θ_2 = {T_global, T_1..T_5} ⊂ Θ_3 = {T_global, T_1..T_5, τ_1..τ_K}`。

---

### S2：分箱变量语义偏移 H(raw) → H(TS(p))——与 E4 不可比且 docstring 未声明

**攻击维度**：语义偏移 + 隐含假设

**docstring 声称**（L31，假设 A1）：
```
A1. binned temperature 的分箱变量=预测分布熵 H(p)=−Σp_k log p_k。
```

**修复后实现**（L476 + L160 `fit_binned_temperature`）：
```python
binned_params = fit_binned_temperature(cal_s1, cal_y)  # cal_s1 = TS(cal_p)
# fit_binned_temperature 内部：
ent = _entropy(cal_probs)  # cal_probs = cal_s1 → ent = H(TS(cal_p))
```

分箱变量实际是 `H(TS(p))`（TS 校准后概率的熵），**不是** `H(p)`（原始概率的熵）。

**与 E4 的对比**（`run_e4_temperature_analysis.py` L365, L507）：
```python
# E4: 在 raw cal_probs 上计算熵
ent = predictive_entropy(cal_probs)  # cal_probs = raw → ent = H(raw_p)
T_per_bin, bin_edges, bin_records = fit_binned_T(cal_probs, cal_labels, n_bins=N_BINS)
```

E4 在 raw 概率上分箱（`H(raw_p)`），E2 修复后在 TS 输出上分箱（`H(TS(p))`）。

**攻击点**：
- TS with T>1 → 概率分布变平坦 → 熵增大；T<1 → 变尖锐 → 熵减小。
- 同一样本在 `H(raw_p)` 和 `H(TS(p))` 下可能落入**不同分箱**，获得**不同 T_b**，产生**不同校准输出**。
- E2 的 binned-T 与 E4 的 binned-T **不是同一个操作**——分箱变量不同，结果不可比。
- docstring L31 的 `H(p)` 未澄清 `p` 是 raw 还是 TS 输出。修复后 `p = TS(raw)`，但 docstring 仍写 `H(p)` 暗示 raw。

**为什么严重**：
1. **跨实验不可比**：E2 的 "Stage 2 binned-T 收益" 与 E4 的 "binned-T vs global-T 收益" 用不同分箱变量，论文不能将两者互引。
2. **隐含假设未声明**：修复引入了 "分箱变量应为 TS 校准后的熵" 这一新假设（合理：TS 改变了不确定度分布，分箱应在校准后空间进行），但 docstring 未更新假设 A1 来声明此选择。
3. **E4 的 P5 已知问题被放大**：E4 docstring L58 `P1. binned-T 的箱边界在 cal 上 test 上定义，OOD 下箱边界可能漂移`。E2 修复后，箱边界在 cal 的 TS 输出上定义，test 的 TS 输出上应用——TS 本身在 OOD 下可能失效（T 在 source-cal 上拟合），导致箱边界双重漂移（TS 漂移 + 熵分箱漂移）。

**严重程度**：**严重**——修复正确地改变了分箱变量（设计上合理），但未更新 docstring 声明此变化，且与 E4 产生不可比性。

**修复建议**：更新 L31 假设 A1 为 `H(p) where p = TS(raw)（Stage 2 在 TS 输出上分箱）`，并在适用边界中声明 E2 与 E4 的 binned-T 不可直接比较。

---

### S3：Stage 3 Brier reliability 恒等于 Stage 2——消融度量退化，"严格嵌套"在度量层面不成立

**攻击维度**：边界失效 + 自相矛盾

**代码实现**（L482-484）：
```python
tau = optimize_thresholds(cal_s2, cal_y, K)
# Stage3 概率=Stage2 概率（threshold 只改 argmax，不改概率）
cal_s3, test_s3 = cal_s2, test_s2
```

**消融表 Stage 3 行**（L487-504）：
```python
for stage_name, probs in [
    ...
    ("stage3_ts_binned_threshold", test_s3),  # test_s3 = test_s2
]:
    rel = calibration_reliability(probs, test_y)  # 用 test_s3 = test_s2
```

**`calibration_reliability` 内部**（L312-313）：
```python
max_prob = probs.max(axis=1)                    # test_s3.max = test_s2.max（相同）
correct = (probs.argmax(axis=1) == labels)      # test_s3.argmax = test_s2.argmax（相同）
```

**攻击点**：
- `test_s3 = test_s2`（L484，同一对象引用），所以 `calibration_reliability(test_s3, test_y)` 与 `calibration_reliability(test_s2, test_y)` **逐字节相同**。
- Stage 3 的 Brier reliability 行是 Stage 2 的**精确副本**。
- `ΔReliability(Stage3−Stage2) ≡ 0`，**恒等于零，对任何数据、任何模型、任何 seed**。
- 但 L679 汇总仍报告 `Stage3 +threshold opt: {s2:.4f} → {s3:.4f} (Δ={s3-s2:+.4f})`，暗示这是一个可能有非零值的边际贡献——**误导性报告**。

**为什么严重**：
1. **消融设计退化**：4 阶段消融中 Stage 3 对 Brier reliability 无信息增量。ablation 表有 4 行但有效信息只有 3 行（raw, stage1, stage2），Stage 3 行是冗余副本。
2. **"严格嵌套"声称在度量层面不成立**：docstring L16 声称 "三阶段是严格嵌套的参数子集"。参数空间确实严格嵌套（Θ_3 ⊃ Θ_2），但**度量**（Brier reliability）不严格——Stage 3 = Stage 2。嵌套保证的是"参数空间包含"，不保证"度量值变化"。修复未解决此退化（虽为 P0-1 遗留问题，但修复声称验证嵌套关系时未提及）。
3. **threshold 对 Brier reliability 的影响被忽略**：threshold 改变 argmax → 改变 `correct` mask → 理论上应改变 Brier reliability。但代码中 `calibration_reliability` 用 `probs.argmax(axis=1)`（标准 argmax），**未应用 threshold**。若要让 Stage 3 的 Brier reliability 反映 threshold 效果，应改为 `(predict_with_thresholds(probs, tau) == labels)`。当前实现使 threshold 对 ablation 表完全透明。

**可验证反例**：
- 设 `test_s2 = [[0.4, 0.6], [0.55, 0.45]]`，`test_y = [0, 0]`，`tau = [0.1, 0.0]`。
- Stage 2: `argmax = [1, 0]`，`correct = [0, 1]`，`max_prob = [0.6, 0.55]`。
- Stage 3 (应应用 threshold): `argmax(p - tau) = argmax([0.3, 0.6], [0.45, 0.45]) = [1, 0]`，`correct = [0, 1]`——本例恰好相同。
- 但若 `tau = [0.3, 0.0]`：`argmax(p - tau) = argmax([0.1, 0.6], [0.25, 0.45]) = [1, 1]`，`correct = [0, 0]`——**不同**。但代码用 `test_s3.argmax(axis=1) = [1, 0]`（未应用 threshold），得到 `correct = [0, 1]`——**错误**，与 Stage 2 相同。
- Stage 3 的 Brier reliability 应反映 threshold 效果但实际没有。

**严重程度**：**严重**——Stage 3 消融行对 Brier reliability 无信息增量，消融设计的 1/4 是退化的。汇总报告的 Δ(Stage3−Stage2) 恒为 0 但未声明。

**修复建议**：要么 (a) 在 `calibration_reliability` 中对 Stage 3 应用 threshold 计算 `correct`，要么 (b) 在汇总中显式声明 `Δ(Stage3−Stage2)≡0 by construction（threshold 不改概率）` 并移除 Stage 3 的 ablation 行（仅保留判别指标行）。

---

### S4：判别指标 variant="binned" 命名误导——实际是 TS+binned

**攻击维度**：语义偏移

**代码实现**（L513-528）：
```python
for variant, v_probs, v_tau in [
    ("raw", probs, None),
    ("ts", apply_temperature_multiclass(probs, ts_params), None),
    ("binned",                                              # ← variant 名是 "binned"
     apply_binned_temperature(
         apply_temperature_multiclass(probs, ts_params), binned_params),  # ← 实际是 TS+binned
     None),
    ("threshold",
     apply_binned_temperature(
         apply_temperature_multiclass(probs, ts_params), binned_params),
     tau),
]:
```

**攻击点**：
- CSV `discrimination_metrics_60exp.csv` 的 `variant` 列值为 `"binned"`，但对应概率是 `TS+binned`（先 TS 再 binned-T）。
- variant 名 `"binned"` 暗示 "binned only"（仅分箱温度），与 `"ts"`（仅 TS）并列时，读者自然解读为 "binned without TS"。
- 修复注释 L516-519 承认了语义变化：`"binned" variant 须与 Stage 2 语义一致(TS+binned)`，但 **variant 名未改为 `"ts_binned"`**。
- 下游分析（如 `pd.read_csv(...).query("variant == 'binned'")`）会得到 TS+binned 结果，但分析者以为是 binned-only。

**与 ablation 表的命名对比**：
- ablation 表 `stage` 列：`"stage2_ts_binned"`（L490）——命名正确，含 "ts"。
- discrimination 表 `variant` 列：`"binned"`（L520）——命名错误，缺 "ts"。
- **两表对同一语义的命名不一致**。

**为什么严重**：
1. **跨表 join 误导**：若分析者按 `stage="stage2_ts_binned"` 和 `variant="binned"` join 两表，会误以为 ablation 的 "ts_binned" 对应 discrimination 的 "binned only"——语义不匹配。
2. **与 P0-1 攻击的 F1 同源**：P0-1 攻击 F1 正是 "Stage 2 实现是 binned only 而非 TS+binned"。修复改了实现但 variant 名仍叫 "binned"，保留了旧实现的命名痕迹。

**严重程度**：**严重**——CSV 是论文的数据源，variant 命名误导会传播到论文表格和图表。

**修复建议**：将 variant 名改为 `"ts_binned"`（与 ablation 表的 `stage2_ts_binned` 对齐），或改为 `"binned_on_ts"`。

---

## 3. 轻微攻击（需小修补）

### M1：cal split "binned" variant 是 in-sample 拟合——乐观偏差未标注

**攻击维度**：隐含假设

**代码路径**：
- L476：`binned_params = fit_binned_temperature(cal_s1, cal_y)` — 在 cal_s1 上拟合
- L509-510：对 cal split，`probs = cal_p` → `apply_temperature_multiclass(cal_p, ts_params)` = `cal_s1` → `apply_binned_temperature(cal_s1, binned_params)` = `cal_s2`
- cal split 的 "binned" variant = `cal_s2`，而 `binned_params` 在 `cal_s1` 上拟合 → **in-sample apply**

**攻击点**：
- cal split 的 "binned" AUROC/AUPRC/F1 是 in-sample（拟合集上评估），乐观偏差。
- test split 的 "binned" 是 out-of-sample。
- CSV 的 `split` 列区分了 cal/test，但未标注 cal 的 in-sample 性质。分析者比较 cal vs test "binned" AUROC 时可能误判泛化能力。

**严重程度**：**轻微**——split 列已区分 cal/test，有经验的分析者应知道 cal 是拟合集。但显式标注更安全。

**修复建议**：在 CSV 中添加 `is_in_sample` 列，或在 docstring 中声明 cal split 的 "binned"/"threshold" variant 是 in-sample。

---

### M2：N_BINS 与 N_BINS_TEMPERATURE 命名易混淆

**攻击维度**：隐含假设（可维护性）

**代码**（L129-131）：
```python
N_BINS_TEMPERATURE = 5      # binned temperature 箱数
MIN_SAMPLES_PER_BIN = 10    # 每箱最少样本数
N_BINS = 15                 # Brier reliability / ECE 评估分箱数
```

**攻击点**：
- `N_BINS`（15，评估分箱）和 `N_BINS_TEMPERATURE`（5，温度分箱）命名相近，仅后缀区分。
- `fit_binned_temperature` 的默认参数 `n_bins=N_BINS_TEMPERATURE`（L148）——正确使用 5。
- `brier_parts` 调用 `n_bins=N_BINS`（L315）——正确使用 15。
- 当前代码正确，但未来维护者修改时易将 `N_BINS` 误传给 `fit_binned_temperature`（或反之），导致温度分 15 箱（每箱样本不足，大量 T=1.0）或 Brier 用 5 箱（粒度不足）。

**严重程度**：**轻微**——当前代码正确，但命名设计有维护风险。

**修复建议**：重命名为 `N_BINS_EVAL`（评估分箱）和 `N_BINS_TEMP`（温度分箱），或添加类型别名区分。

---

### M3：T_global 在 Stage 2 未联合重拟合——顺序拟合假设未声明

**攻击维度**：隐含假设

**代码**（L465, L476）：
```python
ts_params = fit_temperature_multiclass(cal_p, cal_y)      # Stage 1: T_global on raw
...
binned_params = fit_binned_temperature(cal_s1, cal_y)     # Stage 2: binned-T on TS output
```

**攻击点**：
- Stage 2 复用 Stage 1 的 `ts_params`（T_global 在 raw 上拟合），然后在 TS 输出上拟合 binned-T。
- 这是**顺序拟合**（greedy/staged），非**联合优化**（joint NLL minimization over {T_global, T_1..T_5} simultaneously）。
- 顺序拟合的 T_global 是 raw 上的全局最优 T，不一定是 TS+binned 联合最优的 T_global。联合优化可能找到不同的 (T_global, T_1..T_5) 组合，使 NLL 更低。
- 但顺序拟合保证了 Stage 1 ⊂ Stage 2 的嵌套（Stage 2 的 T_global = Stage 1 的 T_global），联合优化会破坏嵌套（Stage 2 的 T_global ≠ Stage 1 的 T_global）。
- **这是正确的设计选择**（嵌套优先于最优性），但 docstring 未声明 "顺序拟合" 假设。

**严重程度**：**轻微**——设计选择合理，但未声明。若读者假设联合优化，会误解 T_global 的含义。

**修复建议**：在 docstring 假设中声明 "A4: Stage 2 的 T_global 复用 Stage 1 拟合结果（顺序拟合），非联合优化——保证嵌套但可能次优"。

---

## 4. 七维度攻击总结

| 维度 | 攻击点 | 严重性 | 状态 |
|------|--------|--------|------|
| **反例构造** | F2（15 vs 10 箱 reliability 估计差异）、S3（Stage3=Stage2 恒等反例） | 致命+严重 | 成立 |
| **逻辑断链** | F1（修复声称统一分箱但 ece 未修——逻辑链断裂于"统一"→"只修 brier_parts"） | 致命 | 成立 |
| **隐含假设** | F2（15 箱的合理性未论证）、M1（in-sample 未标注）、M3（顺序拟合未声明） | 致命+轻微×2 | 成立 |
| **边界失效** | S3（Stage 3 退化为 Stage 2 副本——度量边界退化） | 严重 | 成立 |
| **自相矛盾** | F1（brier 15 箱 vs ece 10 箱——同函数内矛盾）、S1（docstring Θ_2 与实现矛盾） | 致命+严重 | 成立 |
| **量级错误** | F2（15 箱系统性高估 reliability——量级偏移） | 致命 | 成立 |
| **语义偏移** | S1（Θ_2 符号偏移）、S2（H(p)→H(TS(p)) 分箱变量偏移）、S4（"binned" 命名偏移） | 严重×3 | 成立 |

**全部 7 个维度均发现可攻击点。无任何维度可声明"未发现可攻击点"。**

---

## 5. 对修复核心逻辑的诚实评估

**修复正确部分**（明确声明）：
1. **Stage 2 核心逻辑（L476-478）正确**：`fit_binned_temperature(cal_s1, cal_y)` 确实将 `cal_s1`（TS 校准后概率，L467 `apply_temperature_multiclass(cal_p, ts_params)`）传入拟合，`apply_binned_temperature(cal_s1/test_s1, ...)` 确实在 TS 输出上应用。P0-1 的 F1 攻击点（"Stage 2 是 binned only"）已被有效修复。
2. **判别指标 "binned" 变体（L520-523）正确**：`apply_binned_temperature(apply_temperature_multiclass(probs, ts_params), binned_params)` 确实先 TS 再 binned，与 Stage 2 语义一致。
3. **apply_binned_temperature 的分箱边界一致性正确**：`binned_params` 的 `bin_edges` 在 cal_s1 上计算（L160-161），cal 和 test 使用同一 `binned_params`（同一 bin_edges），无信息泄漏。
4. **fit_binned_temperature 的分箱数正确**：使用默认 `n_bins=N_BINS_TEMPERATURE=5`（L148），未误用 `N_BINS=15`。两个常量未混淆。

**修复不完整/引入新问题部分**：
1. F1：`ece()` 调用未同步修复（仍用默认 10 箱）。
2. F2：`N_BINS=15` 与全代码库的 10 不一致。
3. S1-S4：docstring、命名、退化问题未同步处理。

---

## 6. 修复建议优先级

| 优先级 | 编号 | 修复内容 | 工作量 |
|--------|------|----------|--------|
| **P0** | F1 | L321 `ece(max_prob, correct)` → `ece(max_prob, correct, n_bins=N_BINS)` | 1 行 |
| **P0** | F2 | L131 `N_BINS = 15` → `N_BINS = 10`（与 E3/E4/E6 对齐），或同步修改 E3/E4/E6 并给出 15 的理由 | 1 行或跨文件 |
| **P1** | S1 | 更新 L17 嵌套符号为 `Θ_2 = {T_global, T_1..T_5}` | 1 行 |
| **P1** | S4 | L520 variant 名 `"binned"` → `"ts_binned"` | 1 行 |
| **P2** | S2 | 更新 L31 假设 A1 声明分箱变量为 `H(TS(p))` | 1 行 |
| **P2** | S3 | 在 L679 汇总中声明 `Δ(Stage3−Stage2)≡0 by construction` | 1 行 |
| **P3** | M1-M3 | 添加 in_sample 标注、重命名常量、声明顺序拟合假设 | 3-5 行 |

---

## 7. 结论

P0-3 修复的**核心逻辑正确**——Stage 2 确实改为先 TS 再 binned-T，P0-1 的 F1 攻击点已被有效解决。但修复**不完整**（F1: ECE 未同步修复）且**引入了新的跨实验不一致**（F2: N_BINS=15 vs 全代码库 10）。此外，docstring 嵌套符号（S1）、分箱变量语义（S2）、Stage 3 度量退化（S3）、variant 命名（S4）四个严重问题未同步处理。

**修复评级：部分有效。** 核心逻辑修复成功，但需补充修复 F1（1 行）和 F2（1 行）才能达到可发表标准。S1-S4 需在论文写作前修复以避免文档误导。

**我尝试了全部 7 个攻击维度，在每个维度均找到可攻击点。修复非无懈可击。**
