# 论文审查报告

**论文标题**: When Does Temperature Scaling Pay Off in Cross-Corpus ECG Transfer? A Multi-Seed Calibration Boundary Study  
**目标期刊**: Computers in Biology and Medicine (CBM), 中科院2区  
**审查文件**: `D:\A1\ecg-lab-v2\paper\main.tex`  
**实际行数**: 1707行（任务描述为1817行，存在偏差）  
**审查日期**: 2026-09-12  
**审查标准**: SCI 2区 (Computers in Biology and Medicine)

---

## 1. Abstract (L40-72)

### 1.1 贡献数量不一致（严重）
- **[L135]** Introduction中声明"We make **four** independent contributions"，但实际列出**五个**贡献项（C1-C5）：C1 (L137)、C2 (L147)、C3 (L165)、C4 (L172)、C5 (L182)。Abstract（L40-72）仅隐式描述贡献，未显式枚举，且完全未提及C5（discrimination-aware calibration gate）。
- **建议修改**: 统一为"five independent contributions"并将C5纳入Abstract；或将C5降级为Discussion中的扩展分析，保持"four"。**推荐前者**——C5在Results（L1116-1153）和Conclusion（L1593）中均有实质内容，应作为独立贡献。

### 1.2 Abstract未显式突出4个（或5个）独立贡献的novelty
- **[L40-72]** Abstract以叙述方式描述结果，但未明确标注"我们的四个独立贡献是：(1)... (2)... (3)... (4)..."。读者难以快速识别novelty。
- **建议修改**: 在Abstract末尾（L71前）增加一句明确枚举贡献的总结句，例如："In summary, we contribute (i) the first multi-seed quantification of OOD calibration benefit... (ii) the ID boundary condition analysis... (iii) Shapley decomposition validation... (iv) the method-selection boundary... (v) a discrimination-aware deployment gate."

### 1.3 CI方法描述混乱（严重）
- **[L49-52]** Abstract描述："the earlier operating percentile CI, $B=10{,}000$ in 31/60 experiments and $B=200$ in 21/60, has been fully re-run at $B=10{,}000$ BCa on the entire grid; the two CI methods agree in sign in 60/60 experiments"。这段话嵌在括号内，逻辑混乱：先说percentile是"earlier operating"，再说"fully re-run at BCa"，但未明确说明**最终采用哪个**。
- **[L62]** 后文又称"under the BCa operating CI"，但L227图注说"percentile operating CI"，L506表注也说"percentile operating CI"。
- **建议修改**: 统一CI方法术语。如果最终采用BCa，则全文统一为"BCa $B=10{,}000$"；如果仍用percentile，则统一为"percentile $B=10{,}000$"。当前状态是**两种术语混用**，严重影响可读性和统计严谨性。

### 1.4 未披露NCV不显著（严重遗漏）
- **[全文]** Abstract（及全文）**完全未提及NCV（Negative Control Validation）**。任务背景指出"P0-2攻击发现NCV CI=(-0.0048,+0.0087)跨0"，即NCV不显著，但论文对此**只字未提**。
- **建议修改**: 在Abstract中增加一句诚实披露："A negative control validation (NCV) yielded a non-significant result (CI crossing zero), disclosed as a robustness caveat." 并在Methods和Results中增加NCV实验的完整描述。

### 1.5 潜在overclaim
- **[L57-59]** "TS yields a positive OOD benefit in 51/60 cases (85.0%)"——虽然披露了9个counter-example，但85%的表述在Abstract开头可能给读者留下过强印象。
- **建议修改**: 在51/60后立即补充限定语，如"with the pre-registered ID boundary branch triggered, qualifying the exclusivity of the OOD attribution"。

---

## 2. 统计严谨性

### 2.1 CI方法全文不一致（严重）
- **[L374-375]** CI method note明确说"implementation used the **percentile** bootstrap as the operating CI method, with BCa reserved as a sensitivity analysis"。
- **[L396]** 但同节又说"Observed (**BCa operating CI**, full-grid re-run): 23/60 = 38.3%"。
- **[L506]** Table 1 caption说"$B=10{,}000$, **percentile operating CI**"。
- **[L662]** Table 2 caption说"**BCa operating CI**"。
- **[L1491]** Limitations (vii)说"operating CI is **BCa** at $B=10{,}000$, fully re-run on the entire 60-experiment grid"。
- **[L1654]** CI width distribution说"CI method=**BCa**"。
- **建议修改**: 这是**全文最严重的统计不一致问题**。必须统一：若BCa已full re-run（如L1491所述），则全文统一为"BCa $B=10{,}000$"，删除所有"percentile operating CI"表述；若未完成，则诚实说明。当前状态是Table 1用percentile、Table 2用BCa，**同一论文两张核心表用不同CI方法**，CBM审稿人必然质疑。

### 2.2 NCV不显著未披露（严重遗漏）
- **[全文]** NCV（Negative Control Validation）在全文中**完全缺失**。任务背景明确指出P0-2攻击发现NCV CI=(-0.0048,+0.0087)跨0，即负控制验证不显著。这意味着主效应可能部分归因于度量噪声或方法论artifact，但论文**未作任何披露**。
- **建议修改**: 
  1. 在Methods中增加NCV实验设计描述（P0-2攻击协议）。
  2. 在Results中增加NCV结果小节，如实报告CI跨0。
  3. 在Discussion中讨论NCV不显著对主claim的影响。
  4. 在Limitations中增加NCV条目。

### 2.3 p值报告缺失
- **[全文]** 全文仅报告CI lower bound是否>0，**未报告任何p值**（除L829 Fisher's exact test $p=0.47$外）。对于预注册的单侧检验 $H_1: \Delta\text{ECE}_{\text{OOD}} > 0$，应报告对应的p值。
- **建议修改**: 在Table 1（L502-607）中增加p值列，或在正文中补充关键p值。至少对12个stratum-level聚合结果报告BH校正后的p值。

### 2.4 exploratory vs confirmatory标注基本一致但存在冗余
- **[L70-71, L423, L1461-1462, L1564, L1585-1586]** "exploratory + robustness validation, not confirmatory"在全文重复出现**至少5次**（Abstract、Methods、Discussion、Conclusion两处）。标注本身一致，但重复次数过多影响行文流畅。
- **建议修改**: 保留Abstract和Conclusion各一次，Methods中一次，删除Discussion中冗余表述。

### 2.5 B=200的历史CI保留但未充分说明
- **[L49-50]** Abstract提到"$B=200$ in 21/60"，L1493-1494也提到"earlier percentile CI results from $B=200$ in 21/60 experiments are retained as historical provenance (5 experiments lack log provenance)"。**5个实验缺乏日志溯源**是严重可复现性问题。
- **建议修改**: 在Limitations中明确列出这5个实验的ID，并说明为何缺乏日志、如何确保结果可信。

### 2.6 CI宽度过窄未充分讨论
- **[L1642-1664]** CI width分布显示52/60 cells的CI宽度<0.005，6个supporting cells有degenerate widths ($<3\times10^{-4}$)。排除后headline count从51/60降至45/60 (75%)。这暗示部分"support"可能由过窄CI驱动。
- **建议修改**: 在Abstract或Results开头增加caveat："Six supporting cells have degenerate CI widths ($<3\times10^{-4}$); excluding them, the support rate is 45/60 (75.0%)." 当前此信息仅在Conclusion后段（L1646-1649）提及，位置过深。

---

## 3. Figure引用完整性（严重）

### 3.1 大量figure未引用
- **实际PDF数量**: 72个PDF文件（含60个supplementary reliability图）。
- **正文引用数量**: 仅**5个**figure通过`\includegraphics`引用：
  1. `fig_design_overview.pdf` (L220)
  2. `fig_main_results.pdf` (L477)
  3. `fig_method_boundary.pdf` (L727)
  4. `fig_arch_comparison.pdf` (L804)
  5. `fig_counterexamples.pdf` (L1233)
- **未引用的main figure（7个）**:
  - `fig_reliability_summary.pdf` — reliability汇总图，**应引用**
  - `fig_reliability_chapman_cpsc.pdf` — 6方向reliability图均未引用
  - `fig_reliability_chapman_ptbxl.pdf`
  - `fig_reliability_cpsc_chapman.pdf`
  - `fig_reliability_cpsc_ptbxl.pdf`
  - `fig_reliability_ptbxl_chapman.pdf`
  - `fig_reliability_ptbxl_cpsc.pdf`
- **未引用的supplementary figure（60个）**: 全部`fig_reliability_supp_*.pdf`未引用。
- **建议修改**: 
  1. 在Results中增加`\subsection{Reliability diagrams}`，引用`fig_reliability_summary.pdf`和6个方向reliability图。
  2. 创建Supplementary Material section（或单独`supplement.tex`），引用60个supplementary reliability图。
  3. 当前论文**无任何appendix/supplementary section**，但L305、L890、L1471多次提到"deferred to the supplement"——这是**悬空引用**。

### 3.2 缺少Supplementary Material section
- **[L305, L890, L1471]** 三处提到"deferred to the supplement"，但论文中**无supplementary section**。BiMamba toy experiment、60个reliability supplementary图均无处安放。
- **建议修改**: 在`\section*{Data availability}`前增加`\appendix`或单独创建`supplementary.tex`，包含：(1) BiMamba toy experiment结果；(2) 60个supplementary reliability图；(3) per-seed详细数值表。

### 3.3 每个figure的caption和label检查
- 已引用的5个figure均有caption和label，**此项合格**。
- 但caption中存在术语不一致：L227说"percentile operating CI"，L506也说"percentile operating CI"，而L662说"BCa operating CI"——同§2.1问题。

### 3.4 Forward reference检查
- 未发现forward reference问题。Figure均在定义后引用，Table引用顺序正常。

---

## 4. Related Work (L232-251)

### 4.1 篇幅过短（严重）
- **[L232-251]** Related Work仅**20行**，对于CBM（中科院2区）标准**严重不足**。CBM典型Related Work应至少1-2页（40-80行），覆盖：(1) ECG深度学习校准；(2) 跨语料库ECG迁移；(3) Temperature scaling的OOD行为；(4) 标签偏移校正方法；(5) 预注册与可复现性。
- **建议修改**: 大幅扩展Related Work至至少60行，分3-4个子主题。

### 4.2 2024-2026最新文献覆盖不足
- **已引用的2024-2026文献**:
  - `barandas2023`（实际2024, Information Fusion）— L1747-1752
  - `physiolmeas2026`（2026, Physiol Meas）— L1780-1784
  - `medrxiv2026`（2026, medRxiv preprint）— L1785-1788
  - `lascal2024`（2024, NeurIPS）— L1795-1797
- **缺失的重要2024-2026文献**:
  - ECG基础模型相关校准研究（如ECG-FM, HeartLang等2024-2025工作）
  - 跨机构ECG部署的校准漂移研究
  - 2024-2025年temperature scaling改进方法（如Ensemble-TS, Group-TS）
  - 2025-2026年跨语料库ECG迁移最新benchmark
  - 医学AI中预注册研究的最新进展
- **建议修改**: 补充至少8-10篇2024-2026年相关文献，特别是ECG校准和跨语料库迁移方向。

### 4.3 Positioning不够明确
- **[L247-249]** 仅一句"The ID-vs-OOD asymmetry of TS has been studied in general vision \cite{ovadia2019calibration}; we contribute the multi-seed ECG quantification and the boundary-condition analysis." 这与Ovadia 2019的区分**过于简略**。
- **建议修改**: 明确列出与Ovadia 2019的3-4点本质区别：(1) ECG领域 vs vision；(2) 多seed稳健性 vs 单次实验；(3) 预注册endpoint vs post-hoc分析；(4) boundary condition分析 vs 单一OOD评估。

### 4.4 文献引用格式问题
- **[L1753-1756]** `\bibitem{zhang2022}` 引用的是"J.~F.~Vranken et al."发表于2021年的European Heart Journal -- Digital Health，但bibitem key为"zhang2022"——**key与实际文献不匹配**，可能造成混淆。
- **建议修改**: 将key改为`vranken2021`或更新引用内容。

---

## 5. Limitations (L1465-1536)

### 5.1 n_filters=32降级未讨论（严重遗漏）
- **[全文]** 任务背景指出"原设计n_filters=48，因OOM降为32"，但**全文未提及n_filters=32降级**。这是架构设计的重要偏离，影响模型容量和结果可复现性。
- **建议修改**: 在Limitations中增加条目"(xv) The InceptionTime architecture was originally designed with n_filters=48; due to GPU memory constraints (RTX 5060, 8GB), n_filters was downgraded to 32. This reduces model capacity and may attenuate the reported OOD benefits; the n_filters=48 configuration is registered as future work."

### 5.2 NCV不显著未讨论（严重遗漏）
- **[全文]** Limitations中**无NCV条目**。NCV CI跨0意味着主效应可能部分由度量噪声驱动，这是重要的统计局限。
- **建议修改**: 增加条目"(xvi) The negative control validation (NCV) yielded a non-significant result (CI=[-0.0048, +0.0087] crossing zero), indicating that part of the observed effect may be attributable to SmoothECE estimator noise rather than genuine calibration improvement. This caveat applies to all C1-C5 claims."

### 5.3 exploratory非confirmatory已充分讨论
- **[L1461-1462, L1564, L1585-1586]** exploratory标注在Limitations前后均有提及，**此项合格**。但如§2.4所述，重复过多。

### 5.4 单作者Zero Token Lab未讨论
- **[L31]** 作者为"Zero Token Lab"（单一实验室/作者），**未作为limitation讨论**。单作者可能影响同行评审深度、代码审查严格性、以及学术独立性。
- **建议修改**: 增加条目"(xvii) This work is from a single-author lab (Zero Token Lab), which limits the depth of independent code review and statistical audit; the pre-registration protocol and public repository are intended to partially mitigate this limitation."

### 5.5 Limitations条目过多但结构清晰
- **[L1467-1522]** 共14条Limitations (i-xiv)，条目详尽，结构清晰，**总体合格**。但缺少上述三个关键条目（n_filters、NCV、单作者）。

### 5.6 Future work条目合理
- **[L1524-1534]** 5条Future work条目合理，与Limitations对应。但应增加n_filters=48重跑和NCV改进的future work。

---

## 6. Conclusion (L1537-1602)

### 6.1 与Results基本一致但有轻微overclaim
- **[L1566-1567]** "The findings suggest that TS is a **reasonable default** for cross-corpus ECG deployment"——考虑到15% counter-example率、NCV不显著（未披露）、ID boundary未满足、safety rate仅0.0064，"reasonable default"表述**偏强**。
- **建议修改**: 改为"TS is a **candidate default** that requires local validation before cross-corpus ECG deployment"或"TS is a reasonable default **only when** the discrimination gate (C5) and local validation are satisfied"。

### 6.2 未显式呼应4个（5个）独立贡献
- **[L1540-1602]** Conclusion以叙述方式总结，但未显式映射回C1-C5。读者难以确认每个贡献是否被结论覆盖。
- **建议修改**: 在Conclusion开头增加结构化总结："Our five contributions are: (C1) ... (C2) ... (C3) ... (C4) ... (C5) ...". 然后逐一对应Results证据。

### 6.3 C5在Conclusion中提及但Abstract未提及
- **[L1593-1595]** Conclusion提及C5（discrimination-aware gate, 7/14 strata），但Abstract（L40-72）**完全未提及C5**。这是Abstract-Conclusion不对称。
- **建议修改**: 在Abstract中增加C5的简要描述。

### 6.4 重复声明exploratory
- **[L1564, L1585-1586]** Conclusion中**两次**声明"All hypotheses are exploratory + robustness validation, not confirmatory"，冗余。
- **建议修改**: 保留一次（建议L1564处），删除L1585-1586。

### 6.5 "Three additional analyses"段落位置
- **[L1588-1602]** "Three additional analyses strengthen these conclusions"段落放在Conclusion主体之后，结构上更像Discussion的延伸。其中meta-analytic pooling（L1604-1624）和CI width distribution（L1642-1664）**放在Conclusion section内**，但内容属于Results/Discussion。
- **建议修改**: 将L1604-1664内容移至Discussion或Results，Conclusion应简洁收束。

---

## 7. 写作质量

### 7.1 术语不一致（严重）
- **CI方法**: "percentile operating CI"（L227, L506）vs "BCa operating CI"（L62, L662, L1491）——同§2.1。
- **架构名**: "ResNet1D"（全文）vs "1D-ResNet-34"（L47, L301, L889）——应统一为一种。
- **InceptionTime缩写**: 表格中用"Incep"（L517），正文用"InceptionTime"——建议统一。
- **建议修改**: 建立术语表，全文统一。

### 7.2 段落过渡
- **[L232-251]** Related Work到Data section过渡生硬，无过渡句。
- **[L1077-1115]** Noise floor control到C5 gate过渡生硬。
- **建议修改**: 增加过渡句。

### 7.3 Abstract过长且信息密度过高
- **[L40-72]** Abstract约330词，信息密度极高，包含大量数字（51/60, 27/30, 24/30, 23/60, 38.3%, 29/60, 48.3%, 1.9×, +0.0159, +0.0083, 27-cell, n=20,000, 0.104, 0.5）。CBM建议Abstract 150-250词。
- **建议修改**: 精简Abstract至250词以内，将部分数字移入Results。

### 7.4 语法和表述问题
- **[L262-263]** "official 10-fold / official 10-fold (folds 1--8 train..."——"official 10-fold"重复两次，明显笔误。
- **[L1254]** "the failure is therefore not a room shortage but temperature mismatch"——"room shortage"表述非标准，建议改为"calibration room shortage"或"lack of calibration headroom"。
- **[L1320-1322]** "Common pattern: eight of the nine counter-examples co-occur with (a) low OOD accuracy... and (c) non-positive decay"——跳过了(b)，编号不连续。
- **[L1342]** "$0.85 \times 0.0195 - 0.15 \times 0.0047 = +0.0159 > 0$"——验算：0.85×0.0195=0.016575, 0.15×0.0047=0.000705, 差=0.01587≈0.0159，**数值正确**。
- **建议修改**: 修正上述笔误和编号问题。

### 7.5 表格格式
- **[L502-607]** Table 1（primary_60seed）有60行数据，**过长**。CBM建议大表移至supplementary。
- **建议修改**: 保留12-stratum聚合表（Table 2风格），将60-seed详表移至Supplementary。

### 7.6 引用风格
- **[L198]** `\cite{barandas2023,zhang2022,physiolmeas2026,medrxiv2026}`——4篇文献堆叠引用，未区分各自贡献。
- **建议修改**: 分开引用并简述各自贡献。

---

## 总体评估

### 总体质量评分: **5.5/10**

### 距离SCI 2区标准的主要差距（按严重性排序）

| 优先级 | 问题 | 严重性 | 影响范围 |
|--------|------|--------|----------|
| **P0** | NCV不显著完全未披露 | 严重 | 统计严谨性、诚实性 |
| **P0** | CI方法全文不一致（percentile vs BCa混用） | 严重 | 统计严谨性、可复现性 |
| **P0** | 贡献数量不一致（说4个实际列5个） | 严重 | Abstract、Introduction |
| **P1** | n_filters=32降级未讨论 | 严重 | Limitations、可复现性 |
| **P1** | 67个figure未引用，无supplementary section | 严重 | Figure完整性 |
| **P1** | Related Work仅20行，文献覆盖不足 | 严重 | 学术定位 |
| **P2** | Abstract未显式枚举贡献 | 中等 | 可读性 |
| **P2** | p值未报告 | 中等 | 统计严谨性 |
| **P2** | Conclusion有轻微overclaim | 中等 | 诚实性 |
| **P2** | 单作者未作为limitation | 中等 | 透明性 |
| **P3** | 术语不一致 | 中等 | 写作质量 |
| **P3** | Abstract过长（330词） | 轻微 | 格式 |
| **P3** | exploratory声明重复5次 | 轻微 | 行文流畅性 |
| **P3** | Table 1过长 | 轻微 | 格式 |
| **P3** | 笔误（L262重复、L1320编号跳b） | 轻微 | 校对 |

### 优先修改建议（按重要性排序）

1. **【P0】统一CI方法术语**: 全文搜索替换，统一为"BCa $B=10{,}000$"或"percentile $B=10{,}000$"，删除矛盾表述。这是审稿人**第一眼就会发现**的问题。

2. **【P0】增加NCV实验披露**: 在Methods增加NCV设计、Results增加NCV结果（CI跨0）、Discussion讨论影响、Limitations增加条目。**不披露NCV是学术诚信问题**。

3. **【P0】修正贡献数量**: L135将"four"改为"five"，并在Abstract中增加C5描述；或将C5降级保持"four"。

4. **【P1】增加n_filters=32降级讨论**: Limitations增加条目，说明原设计n_filters=48、因OOM降为32、对结果的影响。

5. **【P1】引用所有figure并创建supplementary section**: 引用7个main reliability figure，创建appendix引用60个supplementary figure，解决"deferred to supplement"的悬空引用。

6. **【P1】大幅扩展Related Work**: 从20行扩展至60+行，补充8-10篇2024-2026文献，明确与Ovadia 2019的positioning。

7. **【P2】在Abstract中显式枚举贡献**: 增加结构化总结句。

8. **【P2】补充p值报告**: 在Table 1增加p值列，或在正文补充关键p值。

9. **【P2】修正Conclusion overclaim**: "reasonable default"改为有条件表述。

10. **【P3】统一术语、精简Abstract、修正笔误**: 全文校对。

### 总结

论文实验工作扎实（60 seed experiments、预注册协议、多架构验证），但**写作完成度不足SCI 2区标准**。最严重的问题是**NCV不显著未披露**（学术诚信风险）和**CI方法全文不一致**（审稿人必拒点）。其次是**贡献数量矛盾**和**大量figure未引用**。建议按上述P0-P3优先级依次修改，预计需要**2-3轮修订**才能达到CBM投稿标准。

---

*审查完成。以上建议基于CBM（Computers in Biology and Medicine）中科院2区期刊标准。*
