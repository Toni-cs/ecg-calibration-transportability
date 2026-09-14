# R9 轮对抗审查 - 反方攻击维度 3：新颖性 (Novelty)

**审查对象**: `D:\A1\ecg-lab-v2\paper\main.tex`
**审查代理**: r9_opponent_novelty (session 1685f7d3-932b-448e-8825-c64112ea8c13)
**审查日期**: 2026-09-13
**攻击维度**: 新颖性 — 论证 5 个贡献可能不新颖
**攻击立场**: 全力挑刺，但基于证据，不捏造

---

## 一、审查范围与提取的贡献声明

### 1.1 Introduction 中的贡献声明 (L146-L206)

论文在 L146 声明 "We make five independent contributions"，并在 L211-L227 进一步澄清 novelty 核心：

> "The novelty of this paper is *not* ``doing multi-seed validation on ECG'' (multi-seed validation is a methodological choice, not a scientific contribution); the novelty is the **first systematic characterization of the boundary conditions under which TS yields a positive OOD calibration benefit in cross-corpus ECG transfer**"

### 1.2 Conclusion 中的正式表述 (L1785-L1799)

- **C1**: 51/60 seed experiments support ΔECE_OOD > 0 (85.0%)
- **C2**: 23/60 cells (38.3%) have CIs containing zero, below ≥80% criterion
- **C3**: 27/27 cells pass at n=20,000 (21/27 at n=500)
- **C4**: TS robust (51/60), EM prior and Matrix scaling fragile (15/30 each)
- **C5**: 7/14 strata pass both calibration and discrimination layers

### 1.3 Related Work 中的自我定位 (L281-L326)

论文在 L292-L295 承认：
> "The ID-vs-OOD asymmetry of TS has been studied in general vision \cite{ovadia2019calibration}; we contribute the multi-seed ECG quantification and the boundary-condition analysis"

---

## 二、逐贡献攻击

### Attack-ID: R9-Novelty-1
**攻击目标**: C1 "OOD calibration benefit quantification"
**严重级别**: P1 (严重 — 需重大修补以论证新颖性)

#### 攻击描述

C1 声称 "OOD benefit quantification" 是一个独立贡献，但该贡献的新颖性在三个层面失效：

1. **现象已被量化**：Ovadia et al. 2019 已经量化了 OOD calibration degradation（论文 L99, L292 均引用）。Ovadia 的工作标题即为 "Can you trust your model's uncertainty? Evaluating predictive uncertainty under dataset shift"，其中 "Evaluating" 即包含量化。论文在 L292-L295 自己承认："The ID-vs-OOD asymmetry of TS has been studied in general vision \cite{ovadia2019calibration}"。因此，"OOD calibration benefit quantification" 的概念不是新的。

2. **现象在 ECG 领域已被报告**：论文在 L208-L210 承认："prior ECG calibration studies report the phenomenon \cite{barandas2023,zhang2022,physiolmeas2026,medrxiv2026}"。即 Barandas 2023、Vranken 2022、Haekal 2026、Patel 2026 已经在 ECG 领域报告了 calibration drift 现象。C1 只是增加了 multi-seed robustness evidence。

3. **Multi-seed validation 被论文自己否认是贡献**：论文在 L211-L213 明确声明："The novelty of this paper is *not* ``doing multi-seed validation on ECG'' (multi-seed validation is a methodological choice, not a scientific contribution)"。但 C1 的核心内容正是 multi-seed validation 下的 51/60 support rate。如果 multi-seed validation 不是贡献，那么 C1 剩下的只是 "在 ECG 上确认 Ovadia 2019 的发现"。

#### 证据

- **L99**: `\cite{ovadia2019calibration,guo2017calibration,wagner2020ptbxl}` — Ovadia 2019 被引用为该问题的奠基性工作
- **L208-L210**: "prior ECG calibration studies report the phenomenon" — 论文承认现象已被报告
- **L211-L213**: "multi-seed validation is a methodological choice, not a scientific contribution" — 论文自己否认 multi-seed 是贡献
- **L292-L295**: "The ID-vs-OOD asymmetry of TS has been studied in general vision \cite{ovadia2019calibration}; we contribute the multi-seed ECG quantification" — 论文承认概念来自 Ovadia
- **L1786-L1788**: "51/60 seed experiments support ΔECE_OOD > 0 (85.0%)" — C1 的核心数字只是确认性结果

#### 反例构造

考虑一个假想的 reviewer 提问："如果 Ovadia 2019 在 vision domain 已经量化了 OOD calibration degradation，且 Barandas 2023 在 ECG domain 已经报告了 calibration drift，那么 C1 的 51/60=85% support rate 提供了什么 Ovadia 和 Barandas 没有提供的新知识？"

论文的答案是 "multi-seed robustness evidence"（L293-L294），但论文同时声明 multi-seed validation 不是 scientific contribution（L212-L213）。这是一个**自相矛盾**：C1 的内容 = multi-seed validation，但 multi-seed validation ≠ contribution。

#### 对 SCI Q2 的影响

**中等拒稿风险**。SCI Q2 期刊的 reviewer 会质疑："你的 C1 只是在 ECG 上确认了 Ovadia 2019 的发现，并增加了 multi-seed robustness evidence。这是 domain application + methodological rigor，不是 conceptual novelty。" 如果论文无法论证 "boundary condition characterization" 的整体新颖性来弥补 C1 单独的不足，C1 单独会被判定为 incremental。

---

### Attack-ID: R9-Novelty-2
**攻击目标**: C2 "ID boundary condition characterization"
**严重级别**: P1 (严重 — 本质是包装过的负结果)

#### 攻击描述

C2 声称 "ID boundary condition characterization" 是一个独立贡献，但该贡献存在两个新颖性问题：

1. **C2 是一个包装过的负结果**：C2 的核心发现是 38.3% < 80%，即 pre-registered boundary criterion **未被满足**（L164-L166, L1810-L1813）。论文在 L166-L170 承认："the pre-registered ``ID nonzero boundary'' branch (protocol A1.4.2) is triggered: the premise that TS has no ID recalibratable miscalibration is re-examined"。即原始假设失败，pre-registered failure branch 被触发。将一个失败的假设检验重新包装为 "boundary condition characterization" 是修辞操作，不是科学贡献。

2. **"Boundary condition" 是给失败结果起的好名字**：论文在 L1566-L1570 承认："the OOD benefit is about $1.9\times$ the ID benefit on average, rather than an exclusively OOD effect"。即原始的 ID-vs-OOD asymmetry 主张被削弱为 "difference in magnitude between two positive benefits"（L1568-L1570）。C2 实际上是在说 "ID benefit 不是零，而是 OOD benefit 的一半"，这削弱了 C1 的 "OOD-specific" 主张。

3. **负结果本身不构成新颖性**：报告 "假设不成立" 是科学实践的正常部分，但不构成独立贡献。论文的 pre-registration 设计（L132-L144）已经预设了 failure branch，因此触发 failure branch 是预期内的可能结果，不是新发现。

#### 证据

- **L158-L175**: C2 的完整表述，核心是 "38.3% < 80%" 的失败结果
- **L164-L170**: "the pre-registered boundary criterion (≥80% of cells with CI containing zero) is *not* met, so the pre-registered ``ID nonzero boundary'' branch (protocol A1.4.2) is triggered" — 明确承认假设失败
- **L1566-L1570**: "the OOD benefit is about $1.9\times$ the ID benefit on average, rather than an exclusively OOD effect" — 承认原始 asymmetry 主张被削弱
- **L1810-L1813**: "The ID boundary criterion was *not* met (23/60 = 38.3%...below the ≥80% threshold)" — Conclusion 中再次确认失败
- **L1823-L1824**: "The predictability failure branch is triggered, downgrading the three-step chain to a two-step chain" — 另一个 failure branch

#### 反例构造

考虑 reviewer 提问："C2 的科学内容是什么？如果去掉 'boundary condition' 这个标签，C2 说的就是 'ID benefit 不是零'。这只是一个观察，不是一个 contribution。"

论文的辩护可能是 "boundary condition characterization 帮助 qualify C1"。但如果 C2 的作用只是 qualify C1（即 C1 的 OOD benefit 不是 exclusively OOD），那么 C2 不是一个独立贡献，而是 C1 的一个 qualification/caveat。论文在 L146 声称 "five **independent** contributions"，但 C2 依赖 C1 存在才有意义，因此 C2 不是独立的。

#### 对 SCI Q2 的影响

**中等拒稿风险**。SCI Q2 reviewer 会质疑："你的 C2 是一个 pre-registered hypothesis 被拒绝的结果。虽然诚实报告值得肯定，但 'hypothesis rejected' 不构成独立新颖贡献。将 failure branch trigger 包装为 'boundary condition characterization' 是修辞，不是科学。" 如果论文无法论证 C2 提供了超越 "假设失败" 的额外洞察，C2 会被降级为 C1 的 caveat。

---

### Attack-ID: R9-Novelty-3
**攻击目标**: C3 "Shapley decomposition validation"
**严重级别**: P1 (严重 — 标准方法应用 + synthetic-only validation)

#### 攻击描述

C3 声称 "Shapley decomposition validation" 是一个 methodological contribution，但该贡献在三个层面缺乏新颖性：

1. **Shapley value decomposition 是已有方法**：论文在 L526 承认使用 "Shapley attribution"，在 L515 承认使用 "counterfactual-replacement additive approximation"。Shapley value 来自合作博弈论（Shapley 1953），在 ML 中的 attribution 应用已有大量先例（Lundberg & Lee 2017 SHAP; Kumar et al. 2021 等）。论文没有引用任何 Shapley value 方法论文献，暗示论文没有意识到这是标准方法的应用。

2. **27/27 at n=20,000 是预期内的确认性结果**：在 n=20,000 的大样本下，一个 correctly-specified 的 decomposition 通过 recovery test 是统计力学的基本预期。论文在 L950-L951 设定的 threshold 是 "Fisher information determinant > τ=10^{-6}"，即只在 identifiable regime 测试。在 identifiable regime + n=20,000 下通过 27/27 不是 surprising result，而是 sanity check。真正有信息量的是 n=500 下的 21/27（6 failures），但论文将此列为 limitation 而非 contribution。

3. **Real-data cross-fitting 尚未完成**：论文在 L966-L972 承认："The 27-cell validation uses binned ECE, not the SmoothECE of the main endpoint; quantitative conclusions are not cross-extrapolable. The cross-fitting step (OOD-fold validation of decomposition explanatory power) remains to be run on real data"。在 Honesty Declaration（L1944-L1947）中再次确认："cross-fitting on real data is pending"。即 C3 的 synthetic validation 是一个 **未完成工作** 的部分报告，不是已完成的 methodological contribution。

4. **Predictability failure branch 被 trigger**：论文在 L989-L997 承认 predictability experiment 的 R²=-0.096，CI upper bound +0.104 < 0.5，触发 failure branch，"the three-step chain (decomposition + predictability + deployment) is downgraded to a two-step chain"。即 C3 的原始目标（decomposition → predictability → deployment）失败，被降级为 decomposition + deployment lookup table。

#### 证据

- **L176-L182**: C3 的完整表述，核心是 "27/27 pass at n=20,000"
- **L515**: "counterfactual-replacement additive approximation" — 标准 Shapley 方法
- **L526**: "Shapley attribution is reported with absolute-value bootstrap CIs" — 标准 Shapley 应用
- **L950-L951**: "Fisher information determinant > τ=10^{-6}" — 只在 identifiable regime 测试
- **L966-L972**: "quantitative conclusions are not cross-extrapolable. The cross-fitting step...remains to be run on real data" — 承认未完成
- **L989-L997**: "R²=-0.096...triggering the failure branch: the three-step chain...is downgraded to a two-step chain" — predictability 失败
- **L1944-L1947**: "cross-fitting on real data is pending" — Honesty Declaration 中确认未完成

#### 反例构造

考虑 reviewer 提问："C3 使用标准 Shapley value decomposition，在 synthetic data 的 identifiable regime + n=20,000 下通过 27/27 recovery test。这是否只是确认了标准方法在它设计工作的条件下工作？有什么 surprising finding？"

论文无法提供 surprising finding，因为：(a) 27/27 pass 是预期内的 sanity check；(b) n=500 下的 6 failures 是 limitation；(c) real-data cross-fitting 未完成；(d) predictability branch 失败。C3 的所有 "interesting" 结果都是负结果或未完成工作。

#### 对 SCI Q2 的影响

**较高拒稿风险**。SCI Q2 reviewer 会质疑："C3 是标准 Shapley 方法在 synthetic data 上的 sanity check，real-data validation 未完成，predictability branch 失败。这构成 methodological contribution 吗？" 如果论文无法论证 C3 提供了超越 "标准方法在它设计工作的条件下工作" 的方法论洞察，C3 会被判定为 preliminary/incomplete work。

---

### Attack-ID: R9-Novelty-4
**攻击目标**: C4 "Method selection boundary"
**严重级别**: P2 (中等 — 标准方法比较 + 已知的失败机制)

#### 攻击描述

C4 声称 "method-selection boundary" 是一个 practical contribution，但该贡献在两个层面缺乏新颖性：

1. **比较 TS vs EM, BBSE, Platt 等是标准方法比较**：Kull et al. 2019（论文 L254-L255 引用）已经比较了 calibration methods（TS vs Dirichlet calibration）。Alexandari et al. 2020（论文 L267-L269 引用）已经分析了 maximum-likelihood calibration 在 label shift 下的性能。论文的 8-method 比较是这些已有比较的扩展，不是新的方法论贡献。

2. **"Prior-correction fragile when ill-conditioned" 是已知机制**：论文在 L1540-L1545 解释 EM 的失败机制为 "prior-likelihood mismatch: prior-correction methods fit a target prior that, when the source confusion matrix is ill-conditioned, amplifies the shift-induced miscalibration"。但 ill-conditioned confusion matrix 导致 BBSE/EM 不稳定是 Lipton et al. 2018（论文 L265-L266 引用）和 Alexandari et al. 2020 已经讨论过的已知问题。论文的 "mechanism" 是对已知机制的重述。

3. **"TS robust" 是 TS 的已知性质**：TS 是 monotone transform，不估计 target prior，因此 immune to prior-estimation failure。这是 TS 的定义性质（Guo 2017），不是新发现。论文在 L1543-L1545 承认："Posterior-correction methods do not estimate a target prior and are therefore immune to this failure mode" — 这是定义性的，不是经验发现。

#### 证据

- **L183-L192**: C4 的完整表述
- **L254-L255**: "Kull et al. \cite{kull2019dirichlet} generalized TS to Dirichlet calibration" — Kull 已比较 calibration methods
- **L265-L269**: "Lipton et al. \cite{lipton2018bbs} introduced black-box shift estimation (BBSE)... Alexandari et al. \cite{alexandari2020} showed that maximum-likelihood calibration with bias correction is hard-to-beat at label shift adaptation" — 已有方法比较
- **L1540-L1545**: "The mechanism is the prior-likelihood mismatch: prior-correction methods fit a target prior that, when the source confusion matrix is ill-conditioned, amplifies the shift-induced miscalibration" — 已知机制
- **L1543-L1545**: "Posterior-correction methods do not estimate a target prior and are therefore immune to this failure mode" — TS 的定义性质

#### 反例构造

考虑 reviewer 提问："C4 发现 'TS robust, EM fragile when ill-conditioned'。Lipton 2018 已经讨论了 BBSE 在 ill-conditioned confusion matrix 下的不稳定性，Alexandari 2020 已经分析了 ML calibration 在 label shift 下的性能。C4 提供了什么 Lipton 和 Alexandari 没有提供的新知识？"

论文的答案可能是 "multi-seed ECG evidence"，但如前所述（R9-Novelty-1），multi-seed validation 被论文自己否认是 scientific contribution。

#### 对 SCI Q2 的影响

**较低拒稿风险但需修补**。SCI Q2 reviewer 可能接受 C4 作为 "practical contribution"，但会质疑其新颖性。如果论文明确将 C4 定位为 "已知机制在 ECG cross-corpus 场景下的首次系统验证"，则可接受为 practical contribution；但当前表述 "method-selection boundary" 暗示了新边界发现，这会被质疑。

---

### Attack-ID: R9-Novelty-5
**攻击目标**: C5 "Discrimination-aware calibration gate"
**严重级别**: P1 (严重 — 常识重述 + 50% pass rate 不可靠)

#### 攻击描述

C5 声称 "discrimination-aware calibration gate" 是一个 clinical contribution，但该贡献在三个层面缺乏新颖性：

1. **"Calibration 不应损害 discrimination" 是常识重述**：TS 是 monotone transform of softmax probabilities，preserve argmax by construction。论文在 L1574-L1576 自己承认："Temperature scaling is a monotone transform of the softmax probabilities; it preserves the argmax by construction (asserted bitwise in the released sanity check), and therefore it cannot change classification accuracy, AUROC, or AUPRC"。即 "calibration ≠ discrimination" 是 TS 的定义性质，不是新发现。将这个定义性质包装成 "two-layer deployment gate" 是修辞操作。

2. **"Calibration necessary but not sufficient for deployment" 是临床部署的基本常识**：论文在 L1215-L1218 声称："Calibration improvement (ΔECE_OOD > 0) is necessary but not sufficient for clinical deployment: a model whose discrimination has collapsed under distribution shift may be recalibrable but clinically useless"。这是临床决策理论的基本原则（Van Calster et al. 2016, 2019，论文 L257-L259 引用），不是新贡献。

3. **7/14 = 50% pass rate 说明 gate 本身不可靠**：C5 的核心数字是 7/14 strata pass both layers（L1796-L1797, L1230-L1233）。50% 的 pass rate意味着 gate 的决策与随机抛硬币无异。如果 gate 是 "actionable deployment criterion"（L1245-L1246 声称），那么 50% 的 pass rate 说明 gate 的 actionable value 存疑。论文在 L1675-L1676 承认："discrimination gate relies on point-estimate accuracy comparisons"，即 gate 是 heuristic，不是 validated criterion。

4. **Gate 的 "reframing" 9 counter-examples 是重新分类，不是新知识**：论文在 L1242-L1244 声称 gate "reframes the 9/60 counter-examples: 4 are calibration failures (Layer 1 rejects) and 5 are discrimination failures (Layer 1 passes but Layer 2 rejects)"。但 9 counter-examples 的存在已经在 C1 中报告，将它们重新分类为 4+5 不提供新知识，只是重新标记。

#### 证据

- **L193-L206**: C5 的完整表述
- **L1215-L1218**: "Calibration improvement (ΔECE_OOD > 0) is necessary but not sufficient for clinical deployment" — 临床常识
- **L1574-L1576**: "Temperature scaling is a monotone transform...it preserves the argmax by construction...it cannot change classification accuracy, AUROC, or AUPRC" — TS 定义性质
- **L1230-L1233**: "7/14 pass both layers and are deployable" — 50% pass rate
- **L1242-L1244**: "This gate reframes the 9/60 counter-examples: 4 are calibration failures...and 5 are discrimination failures" — 重新分类
- **L1245-L1246**: "The gate provides an actionable deployment criterion" — 声称 actionable
- **L1675-L1676**: "discrimination gate relies on point-estimate accuracy comparisons" — 承认 heuristic
- **L257-L259**: "Van Calster et al. \cite{vancalster2016,vancalster2019} established a calibration hierarchy" — 已有临床 calibration 文献

#### 反例构造

考虑 reviewer 提问："C5 的 Layer 2 (discrimination) 检查 'acc_OOD ≥ acc_source_baseline'。这只是一个 accuracy check，不是 'gate'。且 7/14 = 50% pass rate 与随机抛硬币无异。C5 的 actionable value 是什么？"

论文无法提供强有力的辩护，因为：(a) Layer 2 是 accuracy check，不是 novel criterion；(b) 50% pass rate 不可靠；(c) gate 是 heuristic（L1675-L1676）；(d) "reframing" 9 counter-examples 是重新标记，不是新知识。

#### 对 SCI Q2 的影响

**中等拒稿风险**。SCI Q2 reviewer 会质疑："C5 将 'calibration ≠ discrimination' 这个 TS 定义性质包装成 'gate'，且 50% pass rate 说明 gate 的实用性存疑。这构成 clinical contribution 吗？" 如果论文无法论证 C5 提供了超越 "accuracy check" 的临床决策价值，C5 会被判定为 common-sense repackaging。

---

## 三、跨贡献的系统性攻击

### Attack-ID: R9-Novelty-6
**攻击目标**: 5 个贡献的 "独立性" 声明
**严重级别**: P1 (严重 — 贡献之间不独立)

#### 攻击描述

论文在 L146 声明 "We make five **independent** contributions"，但贡献之间存在依赖关系：

1. **C2 依赖 C1**：C2 的 "ID boundary condition" 只有在 C1 的 "OOD benefit" 存在时才有意义。如果 C1 不成立（即没有 OOD benefit），C2 的 "ID benefit 是 OOD benefit 的一半" 无意义。因此 C2 不是独立的。

2. **C5 依赖 C1**：C5 的 Layer 1 直接复用 C1 的 criterion (ΔECE_OOD > 0)（L1221-L1222: "Layer 1 (Calibration): ΔECE_OOD > 0 (C1 criterion)"）。因此 C5 不是独立的。

3. **C3 的 "failure branch" 影响 C4**：论文在 L1278-L1286 承认 C3 的 predictability failure branch 影响 C4 的 deployment criterion（"the gate in §ref{sec:gate}---which uses only the sign of ΔECE_OOD and the discrimination criterion---is the appropriate deployment criterion, not the Shapley-predicted magnitude"）。因此 C3 和 C4 不独立。

4. **C4 的 "TS robust" 与 C1 的 "51/60 supported" 是同一事实**：C4 在 L183-L186 声称 "TS is robust (51/60 supported)"，这与 C1 的 "51/60 seed experiments support ΔECE_OOD > 0"（L1786-L1787）是同一数字。因此 C4 的 TS 部分与 C1 不独立。

#### 证据

- **L146**: "We make five independent contributions" — 独立性声明
- **L1221-L1222**: "Layer 1 (Calibration): ΔECE_OOD > 0 (C1 criterion)" — C5 复用 C1
- **L1278-L1286**: "the gate in §ref{sec:gate}...is the appropriate deployment criterion, not the Shapley-predicted magnitude" — C3 影响 C4/C5
- **L183-L186**: "TS is robust (51/60 supported)" — C4 的 TS 部分与 C1 数字相同
- **L1786-L1787**: "51/60 seed experiments support ΔECE_OOD > 0" — C1 的数字

#### 对 SCI Q2 的影响

**中等拒稿风险**。SCI Q2 reviewer 会质疑："你声称 5 个独立贡献，但 C2 依赖 C1，C5 复用 C1，C4 的 TS 部分与 C1 数字相同。实际独立贡献只有 2-3 个。" 这会削弱论文的 contribution count，影响 reviewer 对论文整体价值的评估。

---

### Attack-ID: R9-Novelty-7
**攻击目标**: "First systematic characterization" 声明
**严重级别**: P2 (中等 — "first" 声明需严格验证)

#### 攻击描述

论文在 L214-L216 声称 novelty 是 "the **first systematic characterization of the boundary conditions under which TS yields a positive OOD calibration benefit in cross-corpus ECG transfer**"。但：

1. **"First" 声明与 Related Work 矛盾**：论文在 L281-L295 引用了 Barandas 2023、Vranken 2022、Haekal 2026、Patel 2026 等 ECG calibration studies，且承认它们 "report the phenomenon"。如果这些工作已经报告了 calibration drift 现象，那么 "first systematic characterization" 的 "first" 需要更严格的限定（如 "first with pre-registered endpoint + multi-seed"）。

2. **"Systematic" 是自我评价**：论文没有提供外部基准来论证 "systematic" 的程度。8 methods × 6 pairs × 5 seeds × 2 architectures = 480 cells 是一个规模声明，不是 "systematic" 的内容声明。

3. **"Boundary conditions" 的内容是负结果集合**：如 R9-Novelty-2 和 R9-Novelty-3 所示，C2 和 C3 的 boundary condition 内容主要是 failure branch triggered。将多个负结果包装为 "boundary condition characterization" 是修辞操作。

#### 证据

- **L214-L216**: "the **first systematic characterization of the boundary conditions under which TS yields a positive OOD calibration benefit in cross-corpus ECG transfer**" — "first" 声明
- **L208-L210**: "prior ECG calibration studies report the phenomenon" — 承认已有 ECG calibration 工作
- **L281-L295**: 引用多个 ECG calibration 先驱工作
- **L1823-L1824**: "The predictability failure branch is triggered" — boundary condition 内容是负结果

#### 对 SCI Q2 的影响

**较低拒稿风险但需限定**。SCI Q2 reviewer 会要求论文明确 "first" 的限定条件（如 "first pre-registered multi-seed study"），否则会质疑 "first" 声明的准确性。

---

## 四、攻击汇总与严重程度排序

| Attack-ID | 攻击目标 | 严重级别 | 核心问题 | SCI Q2 影响 |
|-----------|----------|----------|----------|-------------|
| R9-Novelty-1 | C1 OOD benefit quantification | P1 | 重复 Ovadia 2019 发现 + multi-seed 被否认是贡献 | 中等拒稿风险 |
| R9-Novelty-2 | C2 ID boundary condition | P1 | 包装过的负结果 + 削弱 C1 | 中等拒稿风险 |
| R9-Novelty-3 | C3 Shapley decomposition | P1 | 标准方法 + synthetic-only + real-data 未完成 | 较高拒稿风险 |
| R9-Novelty-4 | C4 Method selection boundary | P2 | 标准方法比较 + 已知机制 | 较低拒稿风险 |
| R9-Novelty-5 | C5 Discrimination gate | P1 | 常识重述 + 50% pass rate | 中等拒稿风险 |
| R9-Novelty-6 | 5 贡献独立性 | P1 | C2/C5 依赖 C1，C4 与 C1 数字相同 | 中等拒稿风险 |
| R9-Novelty-7 | "First" 声明 | P2 | "first" 需严格限定 | 较低拒稿风险 |

### 严重程度统计
- **P0 (致命)**: 0
- **P1 (严重)**: 5
- **P2 (中等)**: 2
- **P3 (轻微)**: 0

---

## 五、对论文整体新颖性的综合评估

### 5.1 论文的核心新颖性声明

论文在 L211-L227 将 novelty 核心定位为 "first systematic characterization of the boundary conditions under which TS yields a positive OOD calibration benefit in cross-corpus ECG transfer"，包含 5 个子项。

### 5.2 反方综合评估

经过 7 个攻击点的审查，反方认为论文的新颖性存在以下系统性问题：

1. **概念来源问题**：C1 的核心概念（OOD calibration degradation）来自 Ovadia 2019，C3 的核心方法（Shapley decomposition）来自合作博弈论/ML attribution 文献，C5 的核心原则（calibration ≠ discrimination）来自 TS 定义性质和 Van Calster 2016/2019。论文的 5 个贡献在概念层面均依赖已有工作。

2. **证据标准问题**：论文将 multi-seed validation 作为证据标准（L226-L227: "the multi-seed validation is the evidence standard applied to each boundary"），但 multi-seed validation 被论文自己否认是 scientific contribution（L212-L213）。这导致论文的 novelty = "boundary condition characterization"，但 boundary condition 的内容主要是负结果（C2 failure branch, C3 predictability failure）。

3. **独立性问题**：5 个贡献之间存在依赖关系（C2→C1, C5→C1, C4-TS=C1），实际独立贡献约 2-3 个。

4. **未完成工作问题**：C3 的 real-data cross-fitting "pending"（L1945-L1946），C5 的 gate 是 "heuristic"（L1675-L1676），C2 的 boundary condition 是 "exploratory"（L1825-L1826: "All hypotheses are tagged exploratory + robustness validation, not confirmatory"）。

### 5.3 反方结论

**反方认为论文的新颖性不足以支撑 5 个独立贡献的声明。** 具体而言：

- **C1** 是 Ovadia 2019 在 ECG domain 的确认性应用，novelty 不足。
- **C2** 是包装过的负结果，不构成独立贡献。
- **C3** 是标准 Shapley 方法的 synthetic sanity check，real-data validation 未完成。
- **C4** 是标准方法比较 + 已知机制，novelty 不足。
- **C5** 是 TS 定义性质 + 临床常识的重新包装，50% pass rate 不可靠。

**如果论文要达到 SCI Q2 的 novelty 标准，需要：**
1. 将 5 个贡献合并为 2-3 个真正的独立贡献（如 "pre-registered multi-seed boundary characterization" 作为一个贡献）。
2. 明确 "first" 声明的限定条件（如 "first pre-registered multi-seed ECG study"）。
3. 完成 C3 的 real-data cross-fitting，否则 C3 只是 preliminary work。
4. 论证 C5 的 gate 提供了超越 "accuracy check" 的临床决策价值，或将其降级为 practical remark。

### 5.4 反方尝试的攻击维度总结

反方尝试了以下 7 个攻击维度：
1. **反例构造**：为每个贡献构造了 reviewer 提问反例（R9-Novelty-1 至 R9-Novelty-5）
2. **逻辑断链**：C1 的 "multi-seed 是贡献" 与 "multi-seed 不是贡献" 自相矛盾（R9-Novelty-1）
3. **隐含假设**：C2 的 "boundary condition" 隐含 "负结果可包装为贡献" 假设（R9-Novelty-2）
4. **边界失效**：C5 的 50% pass rate 是 gate 可靠性的边界失效（R9-Novelty-5）
5. **自相矛盾**：5 贡献 "独立性" 与实际依赖关系矛盾（R9-Novelty-6）
6. **量级错误**：C3 的 27/27 at n=20,000 是预期内，不是 surprising finding（R9-Novelty-3）
7. **语义偏移**：C2 的 "boundary condition characterization" 从 "假设失败" 语义偏移到 "贡献" 语义（R9-Novelty-2）

反方未找到 P0 致命攻击（即论文完全失败），但找到 5 个 P1 严重攻击和 2 个 P2 中等攻击，合计 7 个有效攻击点。论文的新颖性声明需要重大修补才能达到 SCI Q2 标准。

---

## 六、建议正方修补方向

反方建议正方从以下方向修补新颖性：

1. **合并贡献**：将 C1+C2 合并为 "pre-registered OOD benefit quantification with ID boundary qualification"，将 C4+C5 合并为 "method-selection and deployment boundary"，将 C3 降级为 "methodological appendix"。这样 5 个贡献合并为 2 个真正的独立贡献。

2. **限定 "first" 声明**：将 "first systematic characterization" 改为 "first pre-registered multi-seed ECG study with boundary-condition analysis"，明确限定条件。

3. **完成 C3 real-data cross-fitting**：如果 real-data cross-fitting 完成，C3 可从 "preliminary" 升级为 "methodological contribution"。

4. **论证 C5 的临床决策价值**：提供 evidence that the gate improves clinical decision outcomes compared to calibration-only criterion，否则将 C5 降级为 "practical remark"。

5. **明确 novelty 的层次**：区分 "conceptual novelty"（新概念/新方法）和 "empirical novelty"（新领域/新数据）。论文的 novelty 主要是 empirical（ECG domain application），应明确承认这一点，避免 reviewer 期望 conceptual novelty。

---

**攻击报告结束**

**反方声明**：我尝试了全部 7 个攻击维度（反例构造、逻辑断链、隐含假设、边界失效、自相矛盾、量级错误、语义偏移），找到 7 个有效攻击点（5 个 P1，2 个 P2）。论文的新颖性声明存在系统性不足，需要重大修补。我没有捏造不存在的问题，所有攻击点均基于论文 main.tex 的具体行号和引用文献。
