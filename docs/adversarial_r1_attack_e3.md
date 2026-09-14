# E3 Brier Reliability + DCR + NCV 实验脚本反方攻击报告

> **反方挑刺代理-E3 交付**。本报告对正方设计的 `scripts/run_e3_brier_dcr_ncv.py`（983 行）进行最严厉的逐行攻击审查，覆盖 Brier Murphy 分解、DCR、NCV、Cohen's d、bootstrap CI、BH FDR 的逻辑漏洞、隐含假设、边界失效、统计方法不当、代码 bug。
> **攻击日期**：2026-09-09
> **攻击对象**：`scripts/run_e3_brier_dcr_ncv.py`（revision 296db60a, 983 行）
> **参照方案**：`docs/Q2_UPGRADE_PROPOSAL_R5.md` §3.2 E3（lines 231-326）
> **依赖审查**：`src/utils/calibration.py`（revision 4fb8f570）、`scripts/train.py`（revision 024b429a）
> **攻击代理**：反方挑刺代理-E3（GLM-5.2）
> **攻击维度**：反例构造 / 逻辑断链 / 隐含假设 / 边界失效 / 自相矛盾 / 量级错误 / 语义偏移（7 维度全覆盖）

---

## 0. 攻击审查概述

### 严重性汇总表

| 编号 | 严重性 | 攻击维度 | 位置 | 攻击摘要 | 可修补性 |
|------|--------|---------|------|---------|---------|
| F1 | **致命** | 代码bug/隐含假设 | calibration.py L586-626 vs E3 L169-204 | `brier_parts()` 不接受 `n_bins` 参数，E3 传入的 `n_bins=N_BINS` 被静默丢弃，Brier 分解永远用硬编码 10 bin | 需修改 `brier_parts` 签名 |
| F2 | **致命** | 语义偏移/自相矛盾 | calibration.py L625 | Murphy 恒等式 `Brier=REL-RES+UNC` 按构造成立（tautological），非独立验证；主终点 `delta_reliability` 来自该构造量而非 raw Brier | 需用 raw Brier 交叉验证 |
| F3 | **致命** | 逻辑断链/隐含假设 | E3 L69-72, L819-833 | H1（"TS 只影响 Reliability"）是主终点选择的理论依据，但仅在精确分箱极限严格成立；10-bin 下未验证即用作主终点，post-hoc 诊断阈值(0.1/0.3)无理论依据且无 fallback | 需预先验证或改用 raw Brier |
| F4 | **致命** | 隐含假设/量级错误 | E3 L83-86, L390 | 60 checkpoint 共享测试集→配对差非独立→paired t-test p 值偏小；建议的 pair-level 聚合(n=6)样本太少无法做 t 检验 | 需混合效应模型或 cluster bootstrap |
| S1 | **严重** | 量级错误/自相矛盾 | E3 L393-400 vs calibration.py L337-384 | Cohen's d 的 95% CI 用 percentile 方法，但项目 F2 修复明确要求 BCa（预注册§7:116）；E3 未使用项目自有的 `_bca_interval` | 需改用 BCa |
| S2 | **严重** | 语义偏移/代码质量 | E3 L864-871 | DCR/NCV 用 `cohen_d_paired(np.zeros(n), dcr_ood, "increase")` hack 伪造配对，语义混乱；`ttest_rel(zeros, dcr)` 等价于 `ttest_1samp(dcr, 0)` 但可读性差且易出错 | 需显式 one-sample 接口 |
| S3 | **严重** | 量级错误/隐含假设 | E3 L258, L272-274 | NCV 的 `N_total=N×K` 假设 K 个 OvR 决策独立，但 softmax 概率和为 1 完全相关；NCV 量级被 K 倍稀释，可能使有意义效应显得微不足道 | 需报告 per-sample NCV 为主 |
| S4 | **严重** | 隐含假设/逻辑断链 | E3 L78-81, L214-236 | DCR `abstain_cost=0.5` 对称假设；A3 声称"DCR 在 abstain_cost 上单调，符号不变"但代码未实现 0.3/0.7 敏感性分析，声称未验证 | 需实现敏感性分析 |
| S5 | **严重** | 边界失效/量级错误 | E3 L822, L928-933 | H1 诊断阈值 0.1/0.3 无理论依据；若 h1_ratio=0.15 判为"部分成立"但主终点仍用 `delta_reliability`，无切换机制 | 需预设 fallback 到 raw Brier |
| S6 | **严重** | 隐含假设 | E3 L390 | paired t-test 假设差值正态；n=60 时 CLT 有帮助但校准改善分布常右偏（少数大改善+多数近零）；未检查正态性 | 需 Shapiro-Wilk 或 Wilcoxon |
| S7 | **严重** | 语义偏移/代码质量 | E3 L150 vs calibration.py L603 | ECE 用 `n_bins` 参数（可变），Brier 硬编码 10 bin（不可变）；"ECE 与 Brier 分箱一致"仅因巧合（都=10），改 N_BINS 会静默不一致 | 需统一分箱接口 |
| S8 | **严重** | 语义偏移 | E3 L184-204 | `brier_parts_ovr` 平均 per-class 分解，但"平均的分解"≠"分解的平均"；per-class reliability 语义与 top-label reliability 不同，未在报告中说明 | 需文档化语义差异 |
| S9 | **严重** | 隐含假设/逻辑断链 | E3 L604-606, L667-672 | T 在 source-cal 拟合，主分析在 OOD 评估；OOD reliability 改善不保证（TS 可能过拟合 source-cal）；未报告 source-cal reliability 改善作为 sanity check | 需加 source-cal sanity check |
| S10 | **严重** | 边界失效/量级错误 | calibration.py L603 | Brier 分箱 `linspace(0,1,11)`，但 top-label max-prob ∈ [1/K, 1]；K=5 时 [0,0.2] 两个 bin 永远为空，浪费 20% 分辨率 | 需自适应分箱或 [1/K, 1] 区间 |
| M1 | **轻微** | 代码质量 | E3 L153 | `RNG_SEED=42` 固定 bootstrap 种子，CI 确定性；未报告跨种子 CI 稳定性 | 需多种子稳定性检查 |
| M2 | **轻微** | 边界失效 | E3 L386-387 | n=1 时 `std_diff=0`, `cohen_d=0`，bootstrap 全零；退化情况未显式警告 | 需加 n<2 警告 |
| M3 | **轻微** | 量级错误 | E3 L416-451, L879 | BH FDR 仅校正 2 个 p 值，近似 Bonferroni（adj_p ≈ 2p）；"FDR 校正"名义大于实际 | 需透明报告或增加终点数 |
| M4 | **轻微** | 代码质量 | E3 L746-756 | CSV 前 5 行是 `#` 注释+空行，非标准 CSV；`pandas.read_csv` 需 `skiprows` 或 `comment='#'` | 需用 JSON 或标准 CSV |
| M5 | **轻微** | 逻辑断链 | E3 L303-306, L735 | `brier_raw_before/after` 已计算但未进入汇总统计；`brier_total` vs `brier_raw` 的偏差（分箱误差）是关键诊断但未在 summary 报告 | 需在 summary 报告分箱误差 |
| M6 | **轻微** | 隐含假设 | E3 L658, L703 | T 分布未汇总；若所有 T≈1.0 则 TS 是 no-op，所有改善是噪声；若 T 很大则过平滑 | 需报告 T 分布统计 |
| M7 | **轻微** | 边界失效 | E3 L263-264 | NCV 用严格 `>tau`，概率恰好=0.5 时弃权；连续概率下零测度但离散化后可能触发 | 需用 `>=` 或文档化 |

### 攻击数量统计

- **致命攻击 (F)**：4 个
- **严重攻击 (S)**：10 个
- **轻微攻击 (M)**：7 个
- **总计**：21 个攻击点

### 整体评估

**E3 脚本存在 4 个致命攻击，其中 F1（`brier_parts` 静默丢弃 `n_bins`）、F3（H1 未验证即用作主终点理论依据）最为严重。** F1 是一个实际的代码 bug——E3 脚本和 R5 方案都声称 Brier 分解用 10 bin，但 `brier_parts()` 函数签名根本不接受 `n_bins` 参数，E3 传入的 `n_bins=N_BINS` 被静默丢弃。这意味着 A1 攻击缓解方案（"改用 50/100 bin"）无法通过修改 `N_BINS` 实现。F3 是逻辑循环：主终点 `delta_reliability` 的选择依据是 H1（"TS 只影响 Reliability"），但 H1 在 10-bin 下不严格成立，且仅用 post-hoc 诊断验证（阈值无理论依据），主终点选择先于验证。

**F2 揭示一个深层问题**：Murphy 恒等式 `Brier=REL-RES+UNC` 在实现中是 `brier_total = reliability - resolution + uncertainty`（按构造成立），不是独立验证的数学性质。主终点 `delta_reliability` 来自这个构造量，而非经验 raw Brier。如果分箱离散化误差大，"Reliability 改善"可能不代表真实的校准改善。F4 是统计推断的核心问题：60 checkpoint 共享测试集，配对差不独立，paired t-test 的 p 值偏小。

**即使修复所有致命攻击，10 个严重攻击仍限制结论强度**：最关键的是 S1（Cohen's d CI 用 percentile 而非 BCa，违反项目 own F2 修复）、S3（NCV 被 K 倍稀释）、S9（T 在 source-cal 拟合但主分析在 OOD，无 sanity check）。S10 是一个隐蔽的边界问题：top-label max-prob ∈ [1/K, 1]，但 Brier 分箱用 [0, 1]，K=5 时 20% 的 bin 永远为空。

**建议**：在修复 F1-F4 之前，E3 的主终点（Brier reliability 改善）的数值和统计推断不应被用于任何论文结论。特别是 F3 意味着主终点的理论依据（H1）是一个未验证的近似，如果 H1 不成立，主终点应该是 `delta_brier_raw` 而非 `delta_reliability`。

---

## 1. 致命攻击 (Fatal)

### F1：`brier_parts()` 静默丢弃 `n_bins` 参数——Brier 分箱数不可配置

**位置**：`calibration.py` L586-626 vs E3 L169-204, L150

**代码证据**：

`calibration.py` L586-603:
```python
def brier_parts(probs, labels):  # ← 签名无 n_bins 参数！
    """Brier Score Murphy分解（精确恒等式）..."""
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    n = len(probs)
    bins = np.linspace(0, 1, 11)  # ← 硬编码 10 bin
```

E3 L169-181:
```python
def brier_parts_toplabel(probs, labels, n_bins=N_BINS):  # ← 接受 n_bins
    max_p = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == labels).astype(float)
    return brier_parts(max_p, correct)  # ← n_bins 未传递！
```

E3 L184-204:
```python
def brier_parts_ovr(probs, labels, n_bins=N_BINS):  # ← 接受 n_bins
    K = probs.shape[1]
    for k in range(K):
        ...
        b, r, s, u = brier_parts(p_k, y_k)  # ← n_bins 未传递！
```

**攻击维度**：代码 bug + 隐含假设

**论证**：

1. `brier_parts()` 的函数签名是 `(probs, labels)`——**没有 `n_bins` 参数**。
2. E3 的 `brier_parts_toplabel` 和 `brier_parts_ovr` 都接受 `n_bins=N_BINS` 参数，但**从未将其传递给 `brier_parts()`**。
3. `brier_parts()` 内部硬编码 `bins = np.linspace(0, 1, 11)`——永远是 10 bin。
4. E3 配置 `N_BINS = 10`（L150）是**死代码**——改变它对 Brier 分解无任何影响。

**致命后果**：

E3 脚本 docstring L69-72 主动披露攻击点 A1：
> A1. "TS 只影响 Reliability"在 10-bin 下不严格：
>     → 若不成立：改用精确分箱（unique probs）或增加 bin 数到 50/100

**但这个缓解方案无法通过修改 `N_BINS` 实现**——`brier_parts()` 根本不接受 `n_bins`。如果研究者按 A1 的建议将 `N_BINS` 改为 50，ECE 会用 50 bin（`ece()` 函数正确接受 `n_bins`），但 Brier 分解仍用 10 bin。这会导致 ECE 和 Brier reliability 用不同分箱，破坏它们之间的语义一致性。

**反例**：设 `N_BINS = 50`。ECE 用 50 bin 计算（正确），Brier 分解用 10 bin 计算（错误——`n_bins` 被丢弃）。`h1_ratio` 诊断基于 10-bin 的 Resolution 变化，无法反映 50-bin 下的真实 H1 成立情况。研究者误以为已切换到 50 bin，实际未切换。

**裁决**：**致命**——A1 缓解方案失效，分箱数不可配置，ECE 与 Brier 分箱一致性仅靠巧合（都=10）维持。

---

### F2：Murphy 恒等式按构造成立（tautological）——非独立验证

**位置**：`calibration.py` L625

**代码证据**：

```python
brier_total = reliability - resolution + uncertainty  # L625
return float(brier_total), float(reliability), float(resolution), float(uncertainty)
```

**攻击维度**：语义偏移 + 自相矛盾

**论证**：

E3 脚本 docstring L6-8 声称：
> Brier Score 的 Murphy 分解（Murphy 1973）：
>     Brier = Reliability - Resolution + Uncertainty

R5 方案 L248 声称：
> **Brier score decomposition (Murphy 1973)**: The Brier score decomposes as Brier = Reliability - Resolution + Uncertainty

但实现中，`brier_total` **定义为** `reliability - resolution + uncertainty`——恒等式**按构造成立**，不是从 raw Brier 独立验证的性质。真正的 raw Brier `mean((p-y)²)` 由 `brier_raw()` 单独计算（L629-633），可能与 `brier_total` 不同。

**关键问题**：

1. 主终点 `delta_reliability = rel_raw - rel_cal`（E3 L328）来自 `brier_parts()` 返回的 `reliability`，这个 reliability 是 10-bin 分箱后的 `(avg_prob - avg_label)²` 加权和。
2. 如果 10-bin 离散化误差大（`brier_total` ≠ `brier_raw`），那么 "reliability" 分量可能不代表真实的校准质量。
3. 脚本计算了 `brier_raw_before/after`（L303-306）但**未在汇总统计中使用**（M5），也未报告 `brier_total` vs `brier_raw` 的偏差。

**反例**：设 raw 概率全集中在 [0.45, 0.55] 区间（模型不自信）。10 等宽 bin 中，这些概率全落入 bin 4 ([0.4, 0.5)) 和 bin 5 ([0.5, 0.6])。分箱后 `avg_prob` ≈ 0.5，`avg_label` ≈ base_rate。如果 base_rate = 0.5，reliability ≈ 0，resolution ≈ 0。但 raw Brier = mean((0.5 - y)²) = 0.25。`brier_total = 0 - 0 + 0.25 = 0.25`（按构造匹配 raw Brier），但 reliability = 0 暗示"完美校准"——实际上模型只是把所有概率都压到 0.5，没有区分能力。TS 改变概率到 [0.3, 0.7]，reliability 可能"改善"（从 0 到负？不可能，reliability ≥ 0），但实际上校准质量没变——只是分箱变了。

**裁决**：**致命**——主终点的理论基础（Murphy 分解）在实现中是 tautological 的，不能作为"TS 改善校准"的独立证据。需要用 `brier_raw` 交叉验证。

---

### F3：H1 未验证即用作主终点理论依据——循环推理

**位置**：E3 L69-72, L819-833, L928-933

**攻击维度**：逻辑断链 + 隐含假设

**论证**：

E3 的核心推理链条（docstring L57-64）：
1. Murphy: `Brier = REL - RES + UNC`
2. TS 保持 argmax → RES/UNC 不受控 **[H1, H2]**
3. ∴ 主终点 = `REL_before - REL_after`

**H1 是主终点选择的理论依据**。但 H1 仅在"精确分箱极限"（每个唯一概率一个 bin）下严格成立。10-bin 下 TS 改变概率值导致样本跨 bin 迁移，改变 Resolution。

**循环推理结构**：
- 主终点选择 **基于** H1
- H1 的验证 **基于** 实验数据（`h1_ratio = |ΔRES|/|ΔREL|`）
- 实验数据 **来自** 主终点的计算
- 如果 H1 不成立，主终点应该是 `delta_brier_raw`，但脚本**无此 fallback**

**诊断阈值无理论依据**（E3 L928-933）：
```python
if h1_ratio < 0.1:    # 为什么是 0.1？
    print("→ H1 近似成立")
elif h1_ratio < 0.3:  # 为什么是 0.3？
    print("→ H1 部分成立")
else:
    print("→ H1 可能不成立")
```

0.1 和 0.3 这两个阈值没有任何理论依据。如果 `h1_ratio = 0.15`，脚本输出"部分成立"，但主终点**仍然是** `delta_reliability`——没有机制切换到 `delta_brier_raw`。

**反例**：设 60 个 checkpoint 的平均 `ΔREL = 0.01`，`ΔRES = 0.003`。`h1_ratio = 0.3`，脚本输出"部分成立"。但实际上 30% 的 Brier 改善来自 Resolution 变化（TS 改变了分箱组成），只有 70% 来自 Reliability。主终点 `ΔREL = 0.01` 高估了纯校准改善（实际纯校准改善 ≈ 0.007）。

**裁决**：**致命**——主终点的理论依据是未验证的近似，验证是 post-hoc 的且阈值无理论依据，无 fallback 机制。

---

### F4：60 checkpoint 共享测试集——paired t-test 独立性假设违反

**位置**：E3 L83-86, L390, L640-643

**攻击维度**：隐含假设 + 量级错误

**论证**：

E3 docstring L83-86（H3 假设）：
> H3（配对独立性）：
>   - 60 个 checkpoint 的改善值视为独立配对样本
>   - **近似成立**——不同 checkpoint 使用不同 seed/pair/arch，但共享数据集和代码路径

**独立性违反的具体机制**：

60 个 checkpoint = 6 pairs × 2 archs × 5 seeds。对于同一 pair（如 `ptbxl_chapman`），所有 10 个 checkpoint（2 arch × 5 seed）使用**同一个 Chapman 测试集**。这 10 个配对差值（`ΔREL_i = REL_raw_i - REL_cal_i`）共享相同的测试样本，因此：
- `Cov(ΔREL_i, ΔREL_j) > 0`（同一测试集上的改善值正相关）
- 有效样本量 `n_eff = n / (1 + (n-1)ρ)` < 60
- paired t-test 的 p 值**偏小**（过度拒绝 H0）

**脚本承认但未修正**（E3 L84-86）：
> → 反驳：不同 pair 使用不同源/目标域，不同 seed 独立训练
> → 补充：报告 pair-level 聚合（6 个 pair 的均值）作为保守分析

**反驳的反驳**：
1. "不同 seed 独立训练"不意味着测试集上的改善值独立——同一测试集上的改善值有正相关（共享测试样本的随机性）。
2. "pair-level 聚合（6 个 pair 的均值）"在代码中**未实现**——`summarize_and_write` 函数（L710-944）只对 60 个 checkpoint 做配对 t-test，没有 pair-level 聚合。
3. 即使实现 pair-level 聚合，n=6 对 t-test 太少（功效极低，t 临界值 ≈ 2.571 vs n=60 的 2.00）。

**量级估计**：设同 pair 内 10 个 checkpoint 的改善值相关系数 ρ=0.3（保守估计，共享测试集）。`n_eff = 60 / (1 + 9×0.3) = 60/3.7 ≈ 16`。实际有效样本量只有 16，而非 60。paired t-test 的 p 值被低估约 `sqrt(60/16) ≈ 1.94` 倍。

**裁决**：**致命**——paired t-test 的独立性假设违反，p 值偏小；建议的 pair-level 聚合未实现且 n=6 不可行。需用混合效应模型或 cluster bootstrap（cluster = pair）。

---

## 2. 严重攻击 (Serious)

### S1：Cohen's d 的 95% CI 用 percentile 而非 BCa——违反项目 own F2 修复

**位置**：E3 L393-400 vs `calibration.py` L337-384

**代码证据**：

E3 L393-400（percentile 方法）：
```python
rng = np.random.default_rng(RNG_SEED)
boot_ds = np.empty(N_BOOTSTRAP)
for b in range(N_BOOTSTRAP):
    idx = rng.choice(n, n, replace=True)
    d_b = diff[idx]
    s_b = np.std(d_b, ddof=1)
    boot_ds[b] = np.mean(d_b) / s_b if s_b > 1e-12 else 0.0
ci_lo, ci_hi = np.percentile(boot_ds, [2.5, 97.5])  # ← percentile，非 BCa
```

`calibration.py` L337-384 有完整的 `_bca_interval` 实现（bias-correction + acceleration），且 `benefit_inference` 函数默认用 BCa（L502-505）。

**攻击维度**：量级错误 + 自相矛盾

**论证**：

1. 项目 F2 修复明确要求 BCa（`calibration.py` L341: "F2修复：此前的'CI'实为percentile；预注册§7:116要求BCa"）。
2. `calibration.py` 已实现 `_bca_interval`（L337-384）和 `_group_jackknife_benefit`（L387-414）。
3. E3 的 `cohen_d_paired` 函数**未使用**这些函数，而是用简单的 percentile 方法。
4. Percentile CI 对 Cohen's d 有已知的 undercoverage（特别是 n=60 边界情况，偏态分布）。

**自相矛盾**：同一项目中，`benefit_inference`（ECE 主终点）用 BCa，`cohen_d_paired`（E3 Brier reliability 主终点）用 percentile。两个主终点用不同 CI 方法，无法统一比较。

**裁决**：**严重**——E3 主终点的 CI 方法违反项目 own 标准，与 ECE 主终点的 CI 方法不一致。

---

### S2：DCR/NCV 用 `np.zeros(n)` 伪造配对——语义混乱

**位置**：E3 L864-871

**代码证据**：
```python
# DCR 已是 (cost_raw - cost_cal)，正值=改善。用 "increase" 方向。
stats_dcr_ood = cohen_d_paired(np.zeros(n), dcr_ood, "increase")
stats_ncv_ood = cohen_d_paired(np.zeros(n), ncv_ood, "increase")
```

**攻击维度**：语义偏移 + 代码质量

**论证**：

DCR 和 NCV 已经是差值（`cost_raw - cost_cal`），本质是 one-sample 问题（H0: mean(DCR) = 0）。但代码用 `cohen_d_paired(np.zeros(n), dcr_ood, "increase")` 伪造配对：

1. `before = np.zeros(n)`, `after = dcr_ood`
2. `diff = after - before = dcr_ood`（正确）
3. `ttest_rel(np.zeros(n), dcr_ood)` 等价于 `ttest_1samp(dcr_ood, 0)`（数学正确但语义混乱）
4. Bootstrap 重采样 `diff[idx] = dcr_ood[idx]`（正确）

**问题**：
- "before" 和 "after" 语义误导——没有真实的 "before" = 0
- 如果重构时有人误以为这是真配对，可能错误地修改方向
- `ttest_rel` 对 `before` 全零的情况可能有数值边缘问题（虽然 scipy 实现稳健）
- 非标准做法，增加代码审查负担

**裁决**：**严重**——数学正确但语义混乱，应显式用 `ttest_1samp` 和 one-sample Cohen's d 接口。

---

### S3：NCV 的 `N_total=N×K` 假设 K 个 OvR 决策独立——softmax 概率和为 1

**位置**：E3 L258, L272-274

**代码证据**：
```python
N, K = probs_raw.shape
N_total = N * K  # ← 假设 K 个决策独立
...
ncv = (tp_improved + tn_improved - fp_worsened - fn_worsened) / N_total
ncv_per_sample = (...) / N  # 敏感性，但不是主报告
```

**攻击维度**：量级错误 + 隐含假设

**论证**：

对于 softmax 输出，K 个概率 `p_1, ..., p_K` 满足 `Σp_k = 1`。因此：
- K 个 OvR 决策 `1[p_k > τ]` **完全相关**（知道 K-1 个就知道第 K 个）
- `N_total = N × K` 假设 K 个决策独立，**严重违反**
- NCV 量级被 K 倍稀释：`ncv = raw_score / (N×K)` vs `ncv_per_sample = raw_score / N`

**反例**：设 N=1000, K=5, raw_score = 50（50 个净改善决策）。
- `ncv = 50 / 5000 = 0.01`（用 N×K，看起来微不足道）
- `ncv_per_sample = 50 / 1000 = 0.05`（用 N，看起来有意义）

主报告用 `ncv = 0.01`（L277: `'ncv': float(ncv)`），审稿人可能认为"NCV = 1% 无临床意义"。但如果用 per-sample（`ncv_per_sample = 0.05`），"5% 的样本有净改善"听起来更有意义。

**脚本承认但未修正**（E3 L46-48）：
> N_total = N_samples × N_classes 假设每个 (sample, class) 对独立
> 实际上同一样本的 K 个 OvR 决策不独立（概率和为 1），NCV 方差被低估

承认了问题，但主报告仍用 `N×K`。`ncv_per_sample` 作为敏感性在 dict 中返回但**未在 CSV summary 中突出报告**。

**裁决**：**严重**——NCV 量级被 K 倍稀释，可能使有意义效应显得微不足道；per-sample NCV 应为主报告。

---

### S4：DCR `abstain_cost=0.5` 敏感性分析未实现——声称未验证

**位置**：E3 L78-81, L214-236

**攻击维度**：隐含假设 + 逻辑断链

**论证**：

E3 docstring L78-81（A3 攻击及缓解）：
> A3. DCR 的 abstain_cost=0.5 选择：
>     → 攻击：对称成本不反映临床现实
>     → 反驳：DCR 在 abstain_cost ∈ [0,1] 上单调，符号不变（TS 改善决策的方向）
>     → 补充：报告 abstain_cost=0.3 和 0.7 的敏感性

**但代码只计算 `abstain_cost=0.5`**（L149: `ABSTAIN_COST = 0.5`，L216: `abstain_cost: float = ABSTAIN_COST`）。`dcr_multiclass` 函数只接受一个 `abstain_cost` 值，没有循环计算 0.3/0.5/0.7 的敏感性。

"DCR 在 abstain_cost 上单调，符号不变"这个声称**未在代码中验证**——没有任何代码检查 DCR 在不同 abstain_cost 下的符号稳定性。

**裁决**：**严重**——A3 缓解方案（0.3/0.7 敏感性）未实现，单调性声称未验证。

---

### S5：H1 诊断阈值无理论依据且无 fallback 机制

**位置**：E3 L822, L928-933

**攻击维度**：边界失效 + 量级错误

**论证**：

```python
h1_ratio = abs(mean_delta_res) / abs(mean_delta_rel)  # L822
...
if h1_ratio < 0.1:    # L928
    print("→ H1 近似成立")
elif h1_ratio < 0.3:  # L930
    print("→ H1 部分成立")
else:                 # L932
    print("→ H1 可能不成立，建议增加 bin 数")
```

**问题**：
1. 阈值 0.1 和 0.3 **无理论依据**——为什么不是 0.05 和 0.2？或 0.2 和 0.5？
2. "部分成立"时主终点**仍用** `delta_reliability`——没有切换到 `delta_brier_raw` 的机制
3. "可能不成立"时只打印"建议增加 bin 数"——但 F1 表明 bin 数不可配置
4. `h1_ratio` 是**均值比** `|mean(ΔRES)| / |mean(ΔREL)|`，不是逐 checkpoint 比值的均值。如果某些 checkpoint 的 ΔREL ≈ 0，均值比可能误导。

**反例**：30 个 checkpoint ΔREL=0.02, ΔRES=0.001；30 个 ΔREL=0.001, ΔRES=0.02。`mean(ΔREL)=0.0105`, `mean(ΔRES)=0.0105`, `h1_ratio=1.0`→"H1 可能不成立"。但前 30 个 checkpoint H1 完全成立（ratio=0.05），后 30 个 H1 不成立（ratio=20）。均值比掩盖了异质性。

**裁决**：**严重**——阈值无理论依据，无 fallback，均值比掩盖异质性。

---

### S6：paired t-test 未检查正态性假设

**位置**：E3 L390

**攻击维度**：隐含假设

**论证**：

`scipy.stats.ttest_rel` 假设差值 `diff = before - after` 服从正态分布。n=60 时 CLT 有帮助，但校准改善的分布常**右偏**：
- 多数 checkpoint 改善小（ΔREL ≈ 0.001-0.005）
- 少数 checkpoint 改善大（ΔREL ≈ 0.02-0.05）
- 分布有长右尾

脚本未检查正态性（如 Shapiro-Wilk test），也未报告差值分布的偏度/峰度。如果严重非正态，应改用 Wilcoxon signed-rank test（非参数）。

**反例**：60 个差值中 55 个 ≈ 0.001，5 个 ≈ 0.05。mean=0.00508, std=0.0142, t=0.00508×√60/0.0142=2.77, p=0.007。但 Wilcoxon 可能 p=0.06（5 个大值不足以拒绝 H0）。t-test 过度拒绝。

**裁决**：**严重**——未验证正态性，校准改善分布常右偏，t-test 可能误导。

---

### S7：ECE 与 Brier 分箱一致性仅靠巧合维持

**位置**：E3 L150 vs `calibration.py` L603

**攻击维度**：语义偏移 + 代码质量

**论证**：

- ECE: `ece(probs, labels, n_bins=10)` —— `n_bins` 参数有效（`calibration.py` L199）
- Brier: `brier_parts(probs, labels)` —— 无 `n_bins` 参数，硬编码 10 bin（`calibration.py` L603）

两者都用 10 bin，但**原因不同**：ECE 是因为参数默认值=10，Brier 是因为硬编码。如果修改 `N_BINS=50`：
- ECE 用 50 bin（正确）
- Brier 仍用 10 bin（F1 bug）
- 两者分箱不一致，破坏语义对应关系

E3 docstring L53 声称 "brier_total = REL - RES + UNC 按构造成立"，但未声明 "ECE 与 Brier 用相同分箱"。R5 方案也未声明分箱一致性。这是**隐含假设**——读者自然假设两者用相同分箱，但代码不保证。

**裁决**：**严重**——分箱一致性无代码保证，修改 `N_BINS` 会静默破坏一致性。

---

### S8：`brier_parts_ovr` 平均 per-class 分解——语义与 top-label 不同

**位置**：E3 L184-204

**攻击维度**：语义偏移

**论证**：

`brier_parts_ovr` 对每个类 k 做二分类 Brier 分解（`p_k` vs `1[label==k]`），然后平均：
```python
for k in range(K):
    p_k = probs[:, k]
    y_k = (labels == k).astype(float)
    b, r, s, u = brier_parts(p_k, y_k)
    ...
return float(np.mean(briers)), float(np.mean(rels)), ...
```

**问题**：平均的分解 ≠ 分解的平均。`mean(reliability_k)` ≠ `reliability(mean(Brier_k))`。per-class reliability 的语义是"每个二分类问题的校准质量"，top-label reliability 的语义是"最大概率的校准质量"。两者度量不同的东西。

脚本报告 `delta_reliability_ovr` 作为"敏感性分析"（L334, L817），但未在报告或 CSV 中说明 per-class OvR reliability 与 top-label reliability 的语义差异。审稿人可能误以为两者度量同一概念。

**反例**：5 类问题，top-label reliability=0.02（最大概率校准好），但 per-class reliability=0.08（非最大类的概率校准差）。`delta_reliability_ovr` 可能显示"无改善"（因为非最大类的概率 TS 改善有限），而 `delta_reliability_toplabel` 显示"有改善"。两者不矛盾，但语义不同。

**裁决**：**严重**——per-class OvR 与 top-label reliability 语义不同，未文档化。

---

### S9：T 在 source-cal 拟合，主分析在 OOD——无 sanity check

**位置**：E3 L604-606, L667-672

**代码证据**：
```python
# L604-606: T 在 source-cal 拟合
cal_onehot = _to_onehot(cal_labels, K)
T = fit_temperature(cal_probs, cal_onehot)

# L667-672: 主分析在 OOD
id_probs_cal = apply_temperature(id_probs_raw, T)
ood_probs_cal = apply_temperature(ood_probs_raw, T)
id_metrics = compute_all_metrics_for_split(id_probs_raw, id_probs_cal, id_labels)
ood_metrics = compute_all_metrics_for_split(ood_probs_raw, ood_probs_cal, ood_labels)
```

**攻击维度**：隐含假设 + 逻辑断链

**论证**：

温度 T 在 source-cal 上拟合，但主终点在 OOD 上评估。这是迁移学习的标准做法（源域校准→目标域评估），但意味着：
1. OOD reliability 改善**不保证**——TS 可能过拟合 source-cal，在 OOD 上无效甚至有害
2. 脚本未报告 **source-cal reliability 改善**作为 sanity check——如果 source-cal 改善但 OOD 不改善，说明 TS 不迁移
3. 脚本未报告 **ID reliability 改善**与 OOD 的对比——ID 是 source-test，与 source-cal 同分布，应该有改善；如果 ID 改善但 OOD 不改善，说明迁移失败

`summarize_and_write` 函数（L800-802）计算了 `stats_rel_id`（ID 参考），但只是作为"参考"输出，未与 OOD 做对比分析。

**反例**：T=2.0 在 source-cal 上使 reliability 从 0.05 降到 0.02（改善 0.03）。但 source-cal 的概率分布与 OOD 不同（域偏移），T=2.0 在 OOD 上使 reliability 从 0.04 降到 0.035（改善 0.005）。主终点报告 OOD 改善 0.005，但未报告 source-cal 改善 0.03——审稿人无法判断 0.005 是"TS 在 OOD 上效果差"还是"TS 本身有效但迁移损失大"。

**裁决**：**严重**——未报告 source-cal sanity check，无法区分"TS 无效"和"TS 不迁移"。

---

### S10：Brier 分箱 [0,1] 但 top-label max-prob ∈ [1/K, 1]——20% bin 浪费

**位置**：`calibration.py` L603

**攻击维度**：边界失效 + 量级错误

**论证**：

`brier_parts` 用 `bins = np.linspace(0, 1, 11)`——10 个等宽 bin 覆盖 [0, 1]。

但 top-label `max_p = probs.max(axis=1)`，对于 K 类 softmax，`max_p ≥ 1/K`（最大概率至少是均匀分布的 1/K）。

- K=5: `max_p ∈ [0.2, 1.0]`，bin 0 ([0, 0.1)) 和 bin 1 ([0.1, 0.2)) **永远为空**
- K=4: `max_p ∈ [0.25, 1.0]`，bin 0 和 bin 1 永远为空，bin 2 ([0.2, 0.3)) 部分为空

**后果**：
1. 20-25% 的 bin 浪费，有效分箱数从 10 降到 8（K=5）或 7-8（K=4）
2. 分辨率降低——每个有效 bin 更宽，reliability 估计更粗糙
3. `brier_total` vs `brier_raw` 的偏差更大（更粗的分箱 = 更大的离散化误差）
4. 与 ECE 的有效分箱数不一致——ECE 也用 [0, 1] 分箱，但 ECE 的 `max_p` 同样 ∈ [1/K, 1]，所以 ECE 也有同样问题（但 ECE 的 bin 用于计算 `|avg_prob - avg_label|`，空 bin 跳过，影响较小）

**反例**：K=5，所有 max_p ∈ [0.2, 1.0]。10 bin 中 bin 0 和 bin 1 为空，reliability 和 resolution 只在 8 个 bin 上计算。如果改用 `linspace(0.2, 1.0, 9)`（8 bin 覆盖有效范围），分辨率提升 25%。当前实现浪费了 20% 的分箱资源。

**裁决**：**严重**——top-label max-prob 的有效范围 [1/K, 1] 未被利用，20% bin 浪费，分辨率降低。

---

## 3. 轻微攻击 (Minor)

### M1：`RNG_SEED=42` 固定 bootstrap 种子——CI 确定性

**位置**：E3 L153, L393

**论证**：`RNG_SEED = 42` 固定，bootstrap CI 是确定性的。不同种子给出不同 CI（特别是 n=60, B=10000 时 CI 有种子依赖性）。脚本未报告跨种子 CI 稳定性。如果 CI 边界恰好接近 0（d 的 CI = [-0.05, 0.02]），换种子可能变成 [0.01, 0.08]——结论从"不显著"变"显著"。

**建议**：报告 5-10 个种子的 CI 范围。

---

### M2：n=1 退化情况未显式警告

**位置**：E3 L386-387

```python
std_diff = float(np.std(diff, ddof=1)) if n > 1 else 0.0
cohen_d = mean_diff / std_diff if std_diff > 1e-12 else 0.0
```

n=1 时 `std_diff=0`, `cohen_d=0`，bootstrap 全零。无警告。虽然 60 checkpoint 场景下 n=1 不太可能，但 `--limit` 冒烟测试或大量 checkpoint 加载失败时可能触发。

---

### M3：BH FDR 仅校正 2 个 p 值——近似 Bonferroni

**位置**：E3 L416-451, L879

**论证**：2 个 p 值的 BH FDR：`adj_p = min(p×2, 1)`。这与 Bonferroni 几乎相同（Bonferroni: `adj_p = p×2`）。"FDR 校正"名义大于实际——2 个检验的 FDR 控制和 FWER 控制几乎等价。脚本声称"总检验数从 R2 的 72 个降至 2 个"（R5 L276），但 2 个检验的 FDR 校正统计意义有限。

---

### M4：CSV 前 5 行是注释——非标准格式

**位置**：E3 L746-756

```python
w.writerow(["# E3 主终点：Brier Reliability 改善（Murphy 分解）"])
w.writerow(["# Brier = Reliability - Resolution + Uncertainty (Murphy 1973)"])
...
w.writerow([])  # 空行
w.writerow(brier_fields)
```

`pandas.read_csv` 默认无法读取——需 `skiprows=5` 或 `comment='#'`。非标准 CSV 格式，增加下游分析负担。

---

### M5：`brier_raw` 已计算但未进入汇总统计

**位置**：E3 L303-306, L735

**论证**：`brier_raw_before/after` 在 `compute_all_metrics_for_split` 中计算（L303-306），写入 CSV1（L735），但**未在 CSV3 summary 中报告**。`brier_total`（来自分解）vs `brier_raw`（经验）的偏差是分箱离散化误差的关键诊断——如果偏差大，说明 10 bin 不足以近似 raw Brier，主终点 `delta_reliability` 可能不可靠。这个诊断信息已计算但未在 summary 中突出报告。

---

### M6：T 分布未汇总

**位置**：E3 L658, L703

**论证**：每个 checkpoint 的 T 打印到控制台（L703: `T={T:.3f}`），但 T 分布未在 summary 中汇总。T 是关键参数：
- 若所有 T ≈ 1.0：TS 是 no-op，所有改善是噪声
- 若 T 很大（如 T > 5）：TS 过平滑，可能损害分辨率
- T 的变异度反映不同 checkpoint 的校准需求差异

未报告 T 的均值、std、范围，审稿人无法判断 TS 的实际效果幅度。

---

### M7：NCV 用严格 `>tau`——概率恰好=0.5 时弃权

**位置**：E3 L263-264

```python
raw_pos = probs_raw > tau       # 严格 >
cal_pos = probs_cal > tau       # 严格 >
```

概率恰好 = 0.5 时 `raw_pos = False`（弃权）。连续概率下这是零测度事件，但温度缩放后概率可能有离散化（如 T 很大时概率趋近 1/K）。K=2 时 1/K=0.5=τ，所有概率恰好 0.5 → 全部弃权 → NCV=0。虽然 K=2 不在当前实验范围（K=4 或 5），但这是边界隐患。

---

## 4. 全维度攻击记录

### 4.1 反例构造维度

- **F1 反例**：设 `N_BINS=50`。ECE 用 50 bin，Brier 仍用 10 bin。`h1_ratio` 基于 10-bin，无法反映 50-bin 真实情况。✓ 找到攻击点。
- **F3 反例**：`ΔREL=0.01, ΔRES=0.003, h1_ratio=0.3`。主终点高估纯校准改善 30%。✓ 找到攻击点。
- **F4 反例**：同 pair 10 checkpoint 共享测试集，ρ=0.3，n_eff≈16，p 值低估 ~2 倍。✓ 找到攻击点。
- **S3 反例**：N=1000, K=5, raw_score=50。ncv=0.01 vs ncv_per_sample=0.05，5 倍差异。✓ 找到攻击点。
- **S10 反例**：K=5, max_p∈[0.2,1]，bin 0-1 永远空，20% 浪费。✓ 找到攻击点。

### 4.2 逻辑断链维度

- **F3**：主终点选择→H1→post-hoc 验证→无 fallback。循环推理。✓ 找到攻击点。
- **S4**：A3 声称"DCR 单调"但未验证。✓ 找到攻击点。
- **S9**：T 在 source-cal 拟合→OOD 评估→无 sanity check。✓ 找到攻击点。

### 4.3 隐含假设维度

- **F1**：假设 `brier_parts` 接受 `n_bins`——实际不接受。✓ 找到攻击点。
- **F4**：H3 假设 60 checkpoint 独立——实际共享测试集。✓ 找到攻击点。
- **S3**：假设 K 个 OvR 决策独立——实际 softmax 和为 1。✓ 找到攻击点。
- **S6**：假设差值正态——校准改善常右偏。✓ 找到攻击点。
- **S9**：假设 T 从 source 迁移到 target 有效——未验证。✓ 找到攻击点。

### 4.4 边界失效维度

- **S5**：h1_ratio=0.15 时"部分成立"但无 fallback。✓ 找到攻击点。
- **S10**：max_p ∈ [1/K, 1] 但分箱 [0, 1]，20% bin 空。✓ 找到攻击点。
- **M2**：n=1 退化，无警告。✓ 找到攻击点。
- **M7**：概率=0.5=τ 时弃权，K=2 全弃权。✓ 找到攻击点。

### 4.5 自相矛盾维度

- **F2**：Murphy 恒等式按构造成立 vs 声称"数学性质"。✓ 找到攻击点。
- **S1**：项目 F2 修复要求 BCa vs E3 用 percentile。✓ 找到攻击点。

### 4.6 量级错误维度

- **F4**：n_eff=16 vs n=60，p 值低估 ~2 倍。✓ 找到攻击点。
- **S1**：percentile CI undercoverage。✓ 找到攻击点。
- **S3**：NCV 被 K 倍稀释。✓ 找到攻击点。
- **S10**：20% bin 浪费，分辨率降低。✓ 找到攻击点。
- **M3**：2 个检验的 FDR ≈ Bonferroni。✓ 找到攻击点。

### 4.7 语义偏移维度

- **F2**：`brier_total`（构造量）vs `brier_raw`（经验量）。✓ 找到攻击点。
- **S2**：`np.zeros(n)` 伪造配对，one-sample 伪装成 paired。✓ 找到攻击点。
- **S7**：ECE `n_bins` 可变 vs Brier 硬编码。✓ 找到攻击点。
- **S8**：per-class OvR reliability vs top-label reliability 语义不同。✓ 找到攻击点。

---

## 5. 攻击点精化与可验证反例

### 5.1 F1 可验证反例

```python
# 在 E3 脚本中修改：
N_BINS = 50  # 改为 50

# 运行后检查：
# - ECE 用 50 bin（ece() 接受 n_bins=50）
# - Brier 分解仍用 10 bin（brier_parts() 硬编码）
# - h1_ratio 基于 10-bin Resolution，不反映 50-bin 真实情况
# 验证：在 brier_parts_toplabel 中加 print(n_bins) 确认参数被接收但未传递
```

### 5.2 F3 可验证反例

```python
# 构造数据：60 个 checkpoint，30 个 ΔREL=0.02/ΔRES=0.001，30 个 ΔREL=0.001/ΔRES=0.02
# mean(ΔREL)=0.0105, mean(ΔRES)=0.0105, h1_ratio=1.0
# 脚本输出"H1 可能不成立"，但主终点仍用 delta_reliability
# 前 30 个 checkpoint H1 成立（ratio=0.05），后 30 个不成立（ratio=20）
# 均值比掩盖异质性，无 per-checkpoint H1 诊断
```

### 5.3 F4 可验证反例

```python
# 设同 pair 内 10 checkpoint 的 ΔREL 相关 ρ=0.3
# n_eff = 60 / (1 + 9×0.3) = 16.2
# paired t-test 报告 n=60, p=0.001
# 实际 n_eff=16, 校正后 p≈0.02（仍显著但功效大降）
# 若 ρ=0.5: n_eff=60/(1+9×0.5)=10.9, 校正后 p≈0.06（不显著）
# 脚本未报告 ρ 估计或 n_eff
```

### 5.4 S10 可验证反例

```python
# K=5, 生成 max_p ~ Uniform(0.2, 1.0), N=10000
# bins = linspace(0, 1, 11)
# bin 0 ([0, 0.1)): 0 样本
# bin 1 ([0.1, 0.2)): 0 样本
# bin 2-9: 有样本
# 有效 bin = 8, 浪费 20%
# 改用 linspace(0.2, 1.0, 9): 8 bin 覆盖有效范围, 分辨率提升 25%
```

---

## 6. 修复建议优先级

| 优先级 | 攻击 | 修复建议 | 工作量 |
|--------|------|---------|--------|
| **P0** | F1 | `brier_parts` 添加 `n_bins` 参数，E3 传递 `n_bins` | 0.5 天 |
| **P0** | F3 | 预先验证 H1（在 cal set 上检查 ΔRES/ΔREL），若不成立改用 `delta_brier_raw` 为主终点 | 1 天 |
| **P0** | F4 | 改用 cluster bootstrap（cluster=pair）或混合效应模型 | 1 天 |
| **P0** | F2 | 在 summary 中报告 `brier_total` vs `brier_raw` 偏差，用 raw Brier 交叉验证 | 0.5 天 |
| **P1** | S1 | Cohen's d CI 改用 BCa（复用 `_bca_interval`） | 0.5 天 |
| **P1** | S3 | `ncv_per_sample` 为主报告，`ncv` 为敏感性 | 0.5 天 |
| **P1** | S9 | 报告 source-cal reliability 改善作为 sanity check | 0.5 天 |
| **P1** | S10 | Brier 分箱改用 `linspace(1/K, 1, n_bins+1)` | 0.5 天 |
| **P2** | S4 | 实现 abstain_cost=0.3/0.7 敏感性 | 0.5 天 |
| **P2** | S6 | 加 Shapiro-Wilk 正态性检验，非正态时用 Wilcoxon | 0.5 天 |
| **P2** | S5 | 加 per-checkpoint H1 诊断，预设 fallback 到 raw Brier | 0.5 天 |

---

## 7. 结论

**E3 脚本作为论文 C1 主终点的实验脚本，存在 4 个致命攻击、10 个严重攻击、7 个轻微攻击。**

**最致命的问题**：
1. **F1**（`brier_parts` 静默丢弃 `n_bins`）：A1 缓解方案（增加 bin 数）无法通过修改配置实现，是实际代码 bug。
2. **F3**（H1 循环推理）：主终点的理论依据是未验证的近似，验证是 post-hoc 的，无 fallback 机制。如果 H1 不成立，主终点应该是 `delta_brier_raw` 而非 `delta_reliability`。
3. **F4**（独立性违反）：60 checkpoint 共享测试集，paired t-test p 值偏小，建议的 pair-level 聚合（n=6）不可行。
4. **F2**（Murphy 恒等式 tautological）：主终点来自构造量而非经验量，需用 raw Brier 交叉验证。

**对论文核心声称的影响**：

E3 是论文 C1 主贡献（"Brier reliability 改善作为校准方法论贡献"）的实验基础。F1-F4 中的任何一个都足以使主终点的数值和统计推断不可信。特别是：
- F3 意味着"TS 只影响 Reliability"的理论依据是未验证的近似
- F4 意味着 paired t-test 的 p 值被低估，显著性可能虚假
- F1 意味着无法通过增加 bin 数来缓解 H1 问题

**建议**：在修复 F1-F4 之前，E3 的主终点（Brier reliability 改善）不应被用于论文 C1 核心声称。修复后需重新运行实验并验证 H1 在新分箱下是否成立。
