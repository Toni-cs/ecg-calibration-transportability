# R9 轮对抗审查攻击报告：维度4 — 过度声称（Overclaiming）

**审查代理**：反方挑刺代理（GLM-5.2）
**审查对象**：`D:\A1\ecg-lab-v2\paper\main.tex`
**审查日期**：2026-09-13
**攻击维度**：过度声称（Overclaiming）
**攻击状态**：全力攻击，未捏造不存在的问题

---

## 执行摘要

本报告对论文进行了 6 个攻击点（A–F）的全维度审查。**发现 6 个有效攻击点，其中 P0 级（致命）2 个，P1 级（严重）3 个，P2 级（中等）1 个。** 论文存在系统性的过度声称模式：在 Abstract 和 Conclusion 中使用强声明语言（"TS is a reasonable default"），但在正文和 Limitations 中披露的数值证据实际上削弱而非支撑该声明。论文采用"披露即免责"策略——在 Limitations 中列出问题，但在 Abstract/Conclusion 中仍使用不受限的强声明。

---

## 攻击点 A：85% support rate 基于退化 CI，实际降至 75%

- **Attack-ID**: R9-Overclaim-1
- **严重级别**: P0（致命）
- **攻击描述**: 论文以 51/60 = 85.0% 作为核心 headline 数值，但该数值包含 6 个具有退化 CI（宽度 < 3×10⁻⁴）的"支撑"cell。排除这些统计可疑的 cell 后，support rate 降至 45/60 = 75.0%。论文虽在 Conclusion 末尾的"CI width distribution"注释中披露了这一事实，但 Abstract、主 Results 表格和 Conclusion 主体均只报告 85.0%，构成选择性报告。

- **证据**:
  - **Abstract L59**: "TS yields a positive OOD benefit in 51/60 cases (85.0%)" — headline 数值，未提及退化 CI 问题
  - **L705**: "Aggregate: 51/60 supported = 85.0% robustness rate" — 主 Results 中的 headline
  - **L1907-1909（Conclusion 末尾注释）**: "six *supporting* cells have degenerate widths (<3×10⁻⁴); excluding those six, the headline count becomes 45/60 (75.0%): InceptionTime 24/30, ResNet1D 21/30, so the headline rates should be read jointly with effect sizes."
  - **L1518-1520**: "The 15.0% counter-example rate exceeds the 5% threshold commonly used in clinical safety deployment scenarios."

- **反方论证**:
  1. **退化 CI 的统计含义**：CI 宽度 < 3×10⁻⁴ 意味着 bootstrap 分布几乎为 Dirac delta，这通常表明 (a) 样本量不足导致 bootstrap 无法捕获真实不确定性，或 (b) 估计器在特定配置下退化。将这类 cell 计入"支撑"在统计上是不可靠的。
  2. **75% 是否足以支撑结论**：75% 的 support rate 意味着 25% 的失败率，是 5% 临床安全阈值的 5 倍。论文在 L1519 承认 15% 已"exceeds the 5% threshold commonly used in clinical safety deployment scenarios"，那么 25% 更不可接受。
  3. **披露位置的选择性**：75% 的数值被埋在 Conclusion 的第 4 个注释段落（L1903-1925）中，而非与 85% 并列报告。Abstract 中完全不存在 75% 的提及。这违反了"同时报告敏感度分析结果"的透明性原则。
  4. **内部矛盾**：L1910 说"headline rates should be read jointly with effect sizes"，但 Abstract 的 headline（L59）并未与 effect sizes 联合报告。

- **对 SCI Q2 的影响**: 致命。SCI Q2 期刊的统计审稿人会立即识别此为 selective reporting。headline 数值 85% 建立在统计退化的 cell 上，真实 support rate 75% 被有意埋藏。这足以触发 major revision 或 reject。

---

## 攻击点 B：效应量 ECE~0.016 缺乏临床意义讨论

- **Attack-ID**: R9-Overclaim-2
- **严重级别**: P1（严重）
- **攻击描述**: 论文的核心效应量为 ΔECE_OOD 均值 +0.0159，即 ECE 从 0.217 降至 0.201。论文从未讨论这一 0.016 的改善是否具有临床意义（clinical significance），仅讨论了统计显著性（sign 分离）。在 4-class ECG 分类中，0.016 的 ECE 改善可能低于任何合理的最小临床重要差异（MCID）阈值。

- **证据**:
  - **L891**: "Mean ΔECE = +0.0159" — 核心效应量
  - **L893**: "Mean OOD ECE: 0.217 → 0.201" — 即从 0.217 降至 0.201，改善 0.016
  - **L1295**: "mean gain +0.0027 and range [-0.001, +0.017]" — net benefit 的均值仅 0.0027
  - **L1327-1328**: "NCV CI width (ID: 0.0135; OOD: 0.0190) is comparable to the main-endpoint CI widths, indicating the noise floor is non-negligible" — 效应量与噪声底相当
  - **L1190**: "T=1.25 yields +0.014–+0.035" — SmoothECE 噪声底在 T=1.25 时即可达到 0.014，与效应量 0.016 同量级
  - **grep "clinical significance|clinically significant|MCID"**: **无匹配** — 论文完全未讨论临床意义

- **反方论证**:
  1. **效应量与噪声底同量级**：NCV 噪声底 OOD CI 宽度 0.0190，而效应量 0.0159。效应量小于噪声底 CI 宽度，意味着无法排除观测效应中包含相当比例的估计器噪声。论文在 L1747-1749 承认"part of the observed effect magnitude may be attributable to SmoothECE estimator noise rather than genuine calibration improvement"。
  2. **net benefit 微乎其微**：L1295 报告 net benefit gain 均值仅 +0.0027，范围 [-0.001, +0.017]。在决策阈值层面，平均 0.0027 的 net benefit 在临床决策中几乎不可感知。
  3. **基线 ECE 已极差**：OOD raw ECE 均值 0.217 在 4-class 问题上意味着校准严重失败。将 0.217 降至 0.201（改善 7.4%）虽统计可检，但模型仍处于严重误校准状态。宣称这种改善支撑"reasonable default"是过度声称。
  4. **无 MCID 讨论**：论文从未定义或讨论 ECE 改善的最小临床重要差异。在临床决策中，ECE 改善 0.016 是否足以改变任何决策阈值？论文未回答。

- **对 SCI Q2 的影响**: 严重。SCI Q2 临床 AI 期刊通常要求讨论临床意义 vs 统计显著性。效应量与噪声底同量级且无 MCID 讨论，是审稿人质疑"so what"的直接触发点。

---

## 攻击点 C："TS is a reasonable default" 与证据矛盾

- **Attack-ID**: R9-Overclaim-3
- **严重级别**: P0（致命）
- **攻击描述**: Conclusion L1827 声明"The findings suggest that TS is a reasonable default for cross-corpus ECG deployment"，但论文自身披露的多项证据实际上否定这一声明：(1) ID boundary 条件未满足（38.3% vs ≥80% 标准）；(2) 4/6 方向 OOD accuracy 低于 majority-class baseline；(3) 仅 7/14 strata 通过双层 gate；(4) TS safety rate 0.0064（几乎为零）。这些证据指向"TS 在多数场景下不是 reasonable default"。

- **证据**:
  - **L1827（Conclusion）**: "The findings suggest that TS is a reasonable default for cross-corpus ECG deployment"
  - **L758-759（ID boundary 未满足）**: "23/60 cells (38.3%) contain zero (BCa operating CI) and 34/60 have CI lower bound >0, triggering the pre-registered 'ID nonzero boundary' branch" — 预注册标准 ≥80% 远未达到
  - **L1588-1592（OOD accuracy 低于 baseline）**: "the mean OOD accuracy is *below* the majority-class baseline in 4 of the 6 directions"
  - **L1230-1233（仅 7/14 strata 可部署）**: "7/14 pass both layers and are deployable... The remaining 7/14 fail Layer 2"
  - **L1113-1118（safety rate 几乎为零）**: "TS yields 1 cell satisfying the operating safety criterion... a safety rate of 0.0064"
  - **L1708（Limitations 自承）**: "TS is a useful default but not a universally safe recalibrator"

- **反方论证**:
  1. **ID boundary 失败的含义**：预注册的 ID boundary 标准是 ≥80% 的 cell 的 CI 包含零。实际只有 38.3%。这意味着在 61.7% 的 cell 中，TS 在 ID 上就有显著效应——TS 并非"仅在 OOD 修复校准"的温和工具，而是一个在 ID 上也活跃干预的方法。这削弱了"TS 是安全 default"的论证。
  2. **4/6 方向 OOD accuracy 低于 majority baseline**：L1593-1595 自承"In those scenarios recalibration is moot: no temperature improves a model that should be replaced by a majority-class predictor"。如果 2/3 的方向中模型不如多数类预测器，那么"reasonable default"的适用范围仅剩 1/3 的方向——这不足以支撑通用 default 声明。
  3. **7/14 strata 可部署 = 50%**：双层 gate 只有 50% 的 strata 通过。如果一半的场景下 TS 不可部署，"reasonable default"的"reasonable"需要极强的限定，但 Abstract 中无此限定。
  4. **safety rate 0.0064**：在 157 个 cell 中仅 1 个满足安全标准。论文自承"TS is a useful default but not a universally safe recalibrator"（L1708），但 Conclusion 却说"reasonable default"——"useful but not universally safe"与"reasonable default"之间存在语义张力。
  5. **声明与证据的方向相反**：综合上述四项，证据指向"TS 在多数实测场景下不是 reasonable default"，但 Conclusion 做出了正向声明。这是过度声称的最直接形式。

- **对 SCI Q2 的影响**: 致命。Conclusion 的核心声明与论文自身披露的证据矛盾。SCI Q2 审稿人会直接质疑："你的证据显示 4/6 方向模型不如多数类预测器、safety rate 0.0064、ID boundary 失败，你如何得出 reasonable default 的结论？"这是逻辑断链。

---

## 攻击点 D：9 个反例的机制解释是事后合理化（ex post facto）

- **Attack-ID**: R9-Overclaim-4
- **严重级别**: P1（严重）
- **攻击描述**: 论文对 9 个反例给出了"机制解释"（L1433-1513），并声称这些解释"support the qualified overall claim rather than undermining it"（L1414）。但论文自身在 L1605-1612 承认这些是"post-hoc explanation, not a pre-registered prediction"。这是典型的事后合理化（ex post facto rationalization）和叙事谬误（narrative fallacy）——在已知结果后构造故事。

- **证据**:
  - **L1411-1414**: "each counter-example has an identifiable post-hoc mechanistic interpretation, which supports the qualified overall claim rather than undermining it." — 用 post-hoc 解释声称"支撑"结论
  - **L1608-1612（自承 post-hoc）**: "Explainable (post-hoc, mechanism level): after observing a counter-example, we can identify the co-occurring conditions... This is a post-hoc explanation, not a pre-registered prediction."
  - **L1505-1508（"common pattern"）**: "eight of the nine counter-examples co-occur with (a) low OOD accuracy (worst or near-worst seed for that pair) and (b) non-positive decay indicating temperature mismatch"
  - **L1509-1510（模式不普遍）**: "A low OOD raw ECE is *not* a universal feature—four of nine counter-examples have raw ECE above 0.25"
  - **L1422-1423（自承非 gate）**: "a heuristic tendency, not a gate: three counter-examples have OOD accuracy > 0.50"
  - **L1527（期望值计算）**: "0.85 × 0.0195 - 0.15 × 0.0047 = +0.0159 > 0" — 用 post-hoc 机制解释支撑的期望值计算

- **反方论证**:
  1. **叙事谬误的教科书定义**：Nassim Taleb 定义的 narrative fallacy 正是"给随机结果编故事"。9 个失败案例中 8 个有"low OOD accuracy + non-positive decay"——但这是在看到结果后寻找的共同特征。任何 9 个数据点都能找到某些共同特征。
  2. **模式不普遍即机制不成立**：L1509-1510 自承"low OOD raw ECE is not a universal feature"，L1422-1423 自承"three counter-examples have OOD accuracy > 0.50"。如果机制解释有 3/9 的例外，该机制就不是真正的因果机制，而是事后选择的相关性。
  3. **"explainable ≠ predictable" 的自相矛盾**：L1621-1625 自承"counter-examples are explainable but not predictable"。如果无法在部署前预测哪些场景会失败，那么"机制解释"对部署决策毫无价值——它只能用于事后辩护，不能用于事前规避。用无预测能力的 post-hoc 解释来"support the overall claim"是逻辑谬误。
  4. **期望值计算的循环论证**：L1527 的期望值 +0.0159 > 0 使用了 0.85 的 support rate 和 0.15 的 failure rate，但 0.85 本身是被质疑的 headline 数值（见攻击点 A）。用被质疑的数值计算期望值来"支撑"结论，是循环论证。
  5. **CE6 的特殊处理**：L1471-1483 对 CE6 给出了不同于其他 8 个的"over-correction"机制。当 9 个案例中有 1 个需要不同机制时，这暗示机制解释是在逐案构造（case-by-case rationalization），而非统一机制。

- **对 SCI Q2 的影响**: 严重。SCI Q2 方法学审稿人会识别 post-hoc 解释不能用于"支撑"结论。论文自承"not a pre-registered prediction"（L1612），但仍用其"support the qualified overall claim"（L1414），这是方法论自相矛盾。

---

## 攻击点 E：OOD accuracy 低于 majority baseline 时 calibration 意义存疑但结论仍强

- **Attack-ID**: R9-Overclaim-5
- **严重级别**: P1（严重）
- **攻击描述**: 论文承认 4/6 方向 OOD accuracy 低于 majority-class baseline（L1588-1592），并自承"recalibration is moot"（L1593, L1844）。但 Conclusion 仍声明"TS is a reasonable default for cross-corpus ECG deployment"（L1827）。论文试图通过"discrimination-aware gate"（C5）来化解这一矛盾，但 gate 结果显示仅 7/14 strata 可部署（50%），这不足以支撑通用 default 声明。

- **证据**:
  - **L1588-1592**: "the mean OOD accuracy is *below* the majority-class baseline in 4 of the 6 directions (Chap→CPSC 0.510 vs. 0.528; CPSC→PTB-XL 0.424 vs. 0.411, essentially at the baseline; CPSC→Chapman 0.619 and PTB-XL→Chapman 0.620, both well below 0.713)"
  - **L1593-1595**: "In those scenarios recalibration is moot: no temperature improves a model that should be replaced by a majority-class predictor"
  - **L1843-1845（Conclusion 自承）**: "the measured OOD accuracy is below the target majority-class baseline in 4 of the 6 directions—in those scenarios recalibration is moot until the discrimination problem is solved"
  - **L1827（同一 Conclusion 的强声明）**: "The findings suggest that TS is a reasonable default for cross-corpus ECG deployment"
  - **L1230-1233**: "7/14 pass both layers and are deployable... The remaining 7/14 fail Layer 2"

- **反方论证**:
  1. **同一 Conclusion 内的逻辑矛盾**：L1843-1845 说"4/6 方向 recalibration is moot"，L1827 说"TS is a reasonable default for cross-corpus ECG deployment"。"Moot"意为"无意义"，如果 2/3 的方向中 recalibration 无意义，"reasonable default"的适用域仅剩 1/3 方向——但声明未加此限定。
  2. **"moot" 与 "reasonable default" 的语义冲突**：论文试图通过"precondition qualification"（L1840-1845）来化解，但该 qualification 在 Abstract 中完全不存在。Abstract 读者会得到"TS is a reasonable default"的无限定印象。
  3. **7/14 = 50% 不是 default 的证据**：如果双层 gate 只有 50% 通过率，这恰恰说明 TS 在一半场景下不可用。"Default"隐含"在缺乏特定信息时的默认选择"，但论文的证据显示默认选择在 50% 场景下无效。
  4. **CPSC→PTB-XL 的边界案例**：L1590 报告 CPSC→PTB-XL 0.424 vs. baseline 0.411，论文说"essentially at the baseline"——但 0.424 > 0.411，所以这个方向实际上高于 baseline。然而 L1588 说"below... in 4 of the 6 directions"。如果 CPSC→PTB-XL 实际高于 baseline，那"4/6"的计数可能有误，或"essentially at"是在模糊处理。这种模糊性进一步削弱了声明的精确性。

- **对 SCI Q2 的影响**: 严重。同一 Conclusion 内"recalibration is moot in 4/6 directions"与"TS is a reasonable default"并存，是审稿人可直接识别的内部矛盾。SCI Q2 期刊会要求修改 Conclusion 以消除矛盾。

---

## 攻击点 F："exploratory" 标签作为逃避 confirmatory 标准的策略

- **Attack-ID**: R9-Overclaim-6
- **严重级别**: P2（中等）
- **攻击描述**: 论文将所有假设标记为"exploratory + robustness validation, not confirmatory"（L75, L1646-1647, L1825, L1846-1847）。但论文自身在 L1889-1901 披露：在 confirmatory 标准（Bonferroni-12 校正）下，仅 2/12 方向保留显著性。这意味着如果应用 confirmatory 标准，论文的核心发现几乎全部消失。"exploratory"标签使得论文能够使用 85% 的 headline 而无需面对 confirmatory 标准下的 2/12 = 16.7% 的残酷现实。

- **证据**:
  - **L75（Abstract）**: "All hypotheses are tagged exploratory + robustness validation, not confirmatory"
  - **L1646-1647（Discussion）**: "All hypotheses in this paper are tagged exploratory + robustness validation, not confirmatory, to reflect the post-revision status."
  - **L1889-1901（Conclusion 注释）**: "the pre-registered confirmatory family is the shift-level grid of 6 pairs × 2 architectures × 13 shift levels = 156 comparisons... Under Bonferroni-12 correction, only 2/12 directions retain significance (cpsc_chapman/IT and ptbxl_chapman/RN), reflecting the stringent nature of the 12-stratum family-level correction."
  - **L1770-1772（Future work）**: "confirmatory testing under the A2 family reduction (12 hypotheses, BH-12 q=9/12, Bonferroni-12 =2/12) to upgrade the exploratory A1 amendment to a confirmatory result"
  - **L1898-1899**: "the honest pair×architecture-stratum aggregation (12 strata) retains 9/12 directions after BH correction (InceptionTime 6/6)"

- **反方论证**:
  1. **exploratory vs confirmatory 的双重标准**：论文使用 exploratory 标签报告 85% 的 headline，但在 L1899-1901 披露 confirmatory 标准下仅 2/12 = 16.7%。从 85% 到 16.7% 是 5.1 倍的下降，这表明 headline 数值对多重比较校正极度敏感。
  2. **BH 校正下的 9/12 也不乐观**：即使使用较宽松的 BH 校正，9/12 = 75% 仍低于 85% 的 headline。且 BH 校正控制 FDR 而非 FWER，在临床应用中通常要求 FWER 控制。
  3. **"exploratory" 标签的战略使用**：论文在 Abstract（L75）、Discussion（L1646）、Conclusion（L1825, L1846）中反复强调"exploratory"，但同时在 Abstract 中使用"we contribute (i) the first multi-seed quantification"等强贡献声明。如果确实是 exploratory，贡献声明应相应弱化。
  4. **预注册的意义被消解**：预注册的核心价值在于约束 confirmatory 声明。将所有假设标记为 exploratory 使得预注册退化为一个流程仪式——预注册了 endpoint 但不承担 confirmatory 责任。
  5. **Future work 的自承**：L1770-1772 将 confirmatory testing 列为 future work，等于承认当前论文不是 confirmatory 研究。但 Conclusion 的"TS is a reasonable default"是 default 声明，default 声明是实践指导，需要 confirmatory 证据。

- **对 SCI Q2 的影响**: 中等偏严重。SCI Q2 期刊接受 exploratory 研究，但要求声明强度与证据等级匹配。使用 exploratory 标签但做出 default 推荐声明，是证据-声明不匹配。审稿人可能要求将"reasonable default"修改为"exploratory evidence suggests TS may be a reasonable default, pending confirmatory validation"。

---

## 综合攻击评估

### 攻击点汇总

| Attack-ID | 严重级别 | 攻击维度 | 核心问题 |
|-----------|----------|----------|----------|
| R9-Overclaim-1 | P0（致命） | 选择性报告 | 85% 基于退化 CI，实际 75% 被埋藏 |
| R9-Overclaim-2 | P1（严重） | 效应量缺失临床意义讨论 | ECE 0.016 与噪声底同量级，无 MCID |
| R9-Overclaim-3 | P0（致命） | 声明与证据矛盾 | "reasonable default" 被 4 项证据否定 |
| R9-Overclaim-4 | P1（严重） | 事后合理化 | post-hoc 解释被用于"支撑"结论 |
| R9-Overclaim-5 | P1（严重） | 内部逻辑矛盾 | "moot in 4/6" 与 "reasonable default" 并存 |
| R9-Overclaim-6 | P2（中等） | 逃避 confirmatory 标准 | exploratory 标签下 85% vs confirmatory 下 16.7% |

### 系统性过度声称模式

论文呈现一个系统性的过度声称模式，可总结为"披露即免责"策略：

1. **Abstract**：使用最强声明语言（85%, "first multi-seed quantification", "reasonable default"），不提及任何限制性数值（75%, 38.3%, 7/14, 0.0064, 2/12）。
2. **Results**：报告 headline 数值（85%），将限制性数值放在注释和后续章节。
3. **Discussion**：承认问题（"recalibration is moot", "post-hoc explanation"），但用"however"转折维持声明。
4. **Conclusion**：重申强声明（"reasonable default"），将限制性数值放在末尾注释段落。
5. **Limitations**：列出 17 项限制，但限制的累积含义（不支持 default 声明）未被整合到 Conclusion 的声明中。

### 对 SCI Q2 的总体影响

**P0 级攻击（2 个）单独即足以触发 major revision 或 reject**：
- R9-Overclaim-1：选择性报告 85% vs 75%
- R9-Overclaim-3：声明与证据直接矛盾

**P1 级攻击（3 个）联合构成严重方法论质疑**：
- R9-Overclaim-2 + R9-Overclaim-4 + R9-Overclaim-5：效应量无临床意义讨论 + post-hoc 合理化 + 内部矛盾

**P2 级攻击（1 个）**：
- R9-Overclaim-6：exploratory 标签的策略性使用

### 反方建议（若正方修补）

正方若要回应这些攻击，需：
1. 在 Abstract 中并列报告 85% 和 75%（含退化 CI 排除后的 support rate）
2. 添加 ECE 改善的 MCID 讨论段落
3. 将"TS is a reasonable default"修改为"TS shows exploratory evidence of OOD calibration benefit in 51/60 seed experiments, with qualifications: (1) 15% failure rate exceeds clinical safety threshold; (2) 4/6 directions have OOD accuracy below majority baseline; (3) only 7/14 strata are deployable; confirmatory validation is required"
4. 将 post-hoc 机制解释从"supporting the claim"修改为"descriptive characterization of failure modes"
5. 在 Conclusion 中消除"recalibration is moot in 4/6"与"reasonable default"的矛盾

---

## 攻击维度完整性声明

本报告尝试了全部 7 个攻击维度（反例构造、逻辑断链、隐含假设、边界失效、自相矛盾、量级错误、语义偏移），在过度声称这一主题下发现 6 个有效攻击点。所有攻击均基于论文原文的具体行号和数值，未捏造不存在的问题。

**反方结论**：论文存在系统性的过度声称，核心声明"TS is a reasonable default"与论文自身披露的多项证据矛盾。P0 级攻击点 2 个，建议在 SCI Q2 投稿前进行重大修订。
