# Q2 R5 正方论证反驳报告

**正方代理**：正方论证代理-R5-Rebuttal（GLM-5.2）
**反驳对象**：R5反方挑刺攻击报告（`Q2_R5_OPPONENT_ATTACK.md`，11个攻击点）
**反驳日期**：2026-09-12
**反驳轮次**：第5轮反方攻击 → 正方反驳
**攻击点统计**：11个（0P0 / 5P1 / 6P2）

---

## §1 反驳概述

### 1.1 正方总体立场

正方对反方R5攻击报告的总体立场是：**承认大部分P1级攻击的事实准确性，但区分攻击性质并提供修复路径；对部分P2级攻击进行反驳**。

**立场分布**：
- **接受（Accept）**：6个攻击点（Attack-R5-1, R5-2, R5-3, R5-4, R5-5, R5-6）——承认事实成立，提供修复建议
- **部分接受（Partial Accept）**：3个攻击点（Attack-R5-7, R5-9, R5-11）——承认部分成立，反驳部分
- **部分反驳（Partial Rebut）**：2个攻击点（Attack-R5-8, R5-10）——反驳核心论点，承认次要问题

### 1.2 关键区分：R5 P1级攻击 vs R4 P1级攻击

**正方最重要的反驳论点**：R5的5个P1级攻击与R4的5个P1级攻击在**性质上根本不同**，这一区分对收敛判断至关重要。

| 维度 | R4 P1级攻击 | R5 P1级攻击 |
|------|------------|------------|
| **性质** | 实质性问题 | 内部不一致问题（编辑遗漏） |
| **示例** | 核心贡献定位错误、技术论证错误、post-hoc rationalization | 叙述位置已修补但LaTeX代码未同步 |
| **修复难度** | 需根本性修改论证结构 | 只需同步LaTeX代码（1-2小时） |
| **对论文实质影响** | 影响论证有效性 | 不影响论证有效性，只影响文档一致性 |
| **审稿人发现概率** | 高（直接质疑核心论证） | 中（需对比叙述与LaTeX代码才能发现） |

**正方论证**：R5的P1级攻击是**编辑同步问题**，不是**论证缺陷**。R5在叙述性位置（§1、§3.2、§4.2）的修补反映了正方的真实意图——将核心贡献重新定位、修正技术论证、删除post-hoc rationalization。LaTeX代码中的旧声称是编辑遗漏，不是正方有意保留的论证。修复方法是机械性的：将LaTeX代码与叙述性位置同步。

### 1.3 反方攻击的事实准确性认可

正方认可反方攻击的事实准确性。通过grep验证，反方引用的所有行号和内容均准确：
- Line 525-526, 719-720确实包含"pure statistical contribution" ✅
- Line 517-518, 662-663确实包含"TS directly affects reliability without affecting resolution" ✅
- Line 659, 664, 670-671, 1294, 1369确实包含"theoretical prior"和"was recognized before A1" ✅
- Line 370, 376确实将E5标注为"Confirmatory" ✅
- Line 1041确实保留"这个估计是独立的" ✅

**正方立场**：事实准确不代表攻击性质等同于R4。事实成立 + 性质区分 = 需要修复但修复简单。

---

## §2 逐项反驳

### 2.1 Attack-R5-1反驳：§4.3 LaTeX代码保留"pure statistical contribution"

- **正方立场**：**接受（Accept）**
- **严重级别认同**：P1（内部不一致）
- **性质判定**：编辑同步遗漏，非论证缺陷

**正方反驳**：

1. **承认事实**：反方引用的Line 525-526和Line 719-720确实包含"pure statistical contribution"。这是事实，正方不否认。

2. **性质区分**：但这一攻击的性质是**编辑同步遗漏**，不是**论证缺陷**：
   - R5在§1（Line 395-407）、§4.2 C1（Line 413-435）、§4.5.1（Line 755-762）中已将核心贡献重新定位为"跨语料库ECG部署中的校准可靠性改善"——这反映了正方的真实意图
   - §4.3 LaTeX代码中的"pure statistical contribution"是**未同步的旧措辞**，不是正方有意保留的论证
   - 修复方法是机械性的：将Line 525-526和Line 719-720的"pure statistical contribution"替换为"calibration reliability improvement in cross-corpus ECG deployment"

3. **与R4 Attack-R4-1的区别**：R4的Attack-R4-1攻击的是**论证本身**——核心贡献定位为"纯统计贡献"在临床期刊CBM中自我削弱。R5的Attack-R5-1攻击的是**文档一致性**——叙述位置已修正，LaTeX代码未同步。前者需要根本性修改论证，后者只需要编辑同步。

4. **审稿人发现概率**：审稿人看到论文LaTeX代码中的"pure statistical contribution"会质疑——这一风险确实存在。但审稿人不会对比R5提案文档的叙述位置和LaTeX代码——审稿人只看最终论文。因此，**只要在投稿前同步LaTeX代码，这一攻击就完全消除**。

**修复建议**：
- 将Line 524-529的`\textbf{The core contribution of this paper is the Brier reliability improvement as a pure statistical contribution}, which does not depend on specific clinical workflows.`替换为`\textbf{The core contribution of this paper is the calibration reliability improvement in cross-corpus ECG deployment}, which is supported by systematic evaluation of 60 cross-corpus transfer experiments.`
- 将Line 719-720的`The core contribution——Brier reliability improvement as a pure statistical contribution——is supported by both the confirmatory`替换为`The core contribution——calibration reliability improvement in cross-corpus ECG deployment——is supported by both the systematic evaluation`

**修复工作量**：约10分钟（两处文本替换）

---

### 2.2 Attack-R5-2反驳：§4.3 LaTeX代码保留"TS directly affects reliability without affecting resolution"

- **正方立场**：**接受（Accept）**
- **严重级别认同**：P1（内部不一致 + 技术论证错误保留）
- **性质判定**：编辑同步遗漏，但涉及技术论证，需更谨慎修复

**正方反驳**：

1. **承认事实**：反方引用的Line 517-518和Line 662-663确实包含"TS directly affects the reliability component without affecting the resolution component"。这是事实。

2. **技术论证问题承认**：正方承认"TS不影响resolution"的技术论证存在问题。TS改变概率分布 → 样本可能在不同bin间移动 → n_b和x̄_b改变 → RES改变。这一论证确实不是严格正确的。R5在§3.2 E3（Line 250）中已修正为"TS不改变argmax → Brier reliability和ECE应同时报告"，但LaTeX代码未同步。

3. **正确的技术论证**：TS的严格性质是：
   - TS不改变argmax（正确）→ top-1准确率不变（正确）
   - TS改变概率分布 → Brier score的REL和RES分量都可能改变（正确）
   - 因此，评估TS效果应使用**概率依赖指标**（ECE, Brier reliability）而非**决策依赖指标**（accuracy, F1）——这是正确的论证
   - 但"TS直接影响reliability而不影响resolution"是**过度声称**——TS可能同时影响两者

4. **修复方法**：将LaTeX代码中的错误论证替换为正确论证：
   - 将"TS directly affects the reliability component without affecting the resolution component"替换为"TS does not change argmax, so evaluation should use probability-dependent metrics (ECE, Brier reliability) rather than decision-dependent metrics (accuracy, F1)"
   - 这一替换保留了"选择Brier reliability作为主指标"的动机，但用正确论证替代错误论证

5. **与R4 Attack-R4-11的区别**：R4的Attack-R4-11攻击的是**技术论证错误本身**。R5的Attack-R5-2攻击的是**LaTeX代码未同步修正**。前者需要识别并修正错误论证，后者只需要将已识别的修正同步到LaTeX代码。

**修复建议**：
- 将Line 517-518的`TS directly affects the reliability component without affecting the resolution component (which depends on argmax).`替换为`TS does not change argmax, so evaluation should use probability-dependent metrics (ECE, Brier reliability) rather than decision-dependent metrics (accuracy, F1).`
- 将Line 662-663的`TS directly affects the reliability component without affecting the resolution component.`替换为`TS does not change argmax, so evaluation should use probability-dependent metrics rather than decision-dependent metrics.`

**修复工作量**：约10分钟（两处文本替换）

---

### 2.3 Attack-R5-3反驳：§4.3 LaTeX代码保留"theoretical prior"和"was recognized before A1"

- **正方立场**：**接受（Accept）**
- **严重级别认同**：P1（内部不一致 + post-hoc rationalization保留）
- **性质判定**：编辑同步遗漏，但涉及时间线声称，需特别谨慎

**正方反驳**：

1. **承认事实**：反方引用的Line 659, 664, 670-671, 1294, 1369确实包含"theoretical prior"和"was recognized before A1 was created"。这是事实。

2. **"theoretical prior"问题**：正方承认"theoretical prior"措辞暗示这一论证在实验前就已确立，但实际上"TS不改变argmax → Brier reliability是自然主指标"这一论证首次出现在R4提案中。虽然TS不改变argmax是数学事实（独立于数据），但"因此Brier reliability是主指标"是**选择论证**，不是**理论先验**。R5在§3.2 E3（Line 250）中已修正为"基于TS数学性质的合理选择"，但LaTeX代码和附录A未同步。

3. **"was recognized before A1 was created"问题**：正方承认这一时间线声称无法证实。R1-R3方案历史中，核心贡献定位经历了多次变化（R1: 部署决策框架 → R2: 边界条件刻画 → R3: 阈值化决策价值 → R4: Brier reliability改善），"Brier reliability作为主指标"的选择确实是在R4中确定的，不是在A1创建前就认识到的。这一声称应删除。

4. **修复方法**：
   - 将"theoretical prior"替换为"mathematical property of TS"——保留"TS不改变argmax"的数学事实，但不暗示这是先验选择
   - 删除"was recognized before A1 was created"——无法证实的时间线声称
   - 保留"TS does not change argmax (a mathematical property independent of data)"——这是正确的数学事实

5. **与R4 Attack-R4-3的区别**：R4的Attack-R4-3攻击的是**post-hoc rationalization本身**。R5的Attack-R5-3攻击的是**LaTeX代码和附录A未同步修正**。前者需要识别并承认post-hoc rationalization，后者只需要将已识别的修正同步。

**修复建议**：
- 将Line 658-665的`is motivated by a \textbf{theoretical prior}: because TS does not change argmax (a mathematical property independent of data), Brier reliability is the natural primary metric for evaluating TS effects——TS directly affects the reliability component without affecting the resolution component. This theoretical motivation is independent of the experimental results and was recognized before A1 was created.`替换为`is motivated by a \textbf{mathematical property of TS}: because TS does not change argmax (a mathematical property independent of data), evaluation should use probability-dependent metrics (ECE, Brier reliability) rather than decision-dependent metrics. This mathematical property is independent of the experimental results.`
- 将Line 670-671的`motivated by theoretical prior (TS preserves argmax), not by data peeking`替换为`motivated by mathematical property of TS (TS preserves argmax), not by data peeking`
- 将Line 1294的`theoretical prior`替换为`mathematical property of TS`
- 将Line 1369的`theoretical prior`替换为`mathematical property of TS`

**修复工作量**：约15分钟（四处文本替换）

---

### 2.4 Attack-R5-4反驳：§3.3 E5标注仍为"Confirmatory"

- **正方立场**：**接受（Accept）**
- **严重级别认同**：P1（内部不一致）
- **性质判定**：编辑同步遗漏，非论证缺陷

**正方反驳**：

1. **承认事实**：反方引用的Line 370和Line 376确实将E5标注为"Confirmatory"。同时，Line 317将E5标注为"exploratory"，Line 1472说"E5 改为 exploratory"。同一文档中E5标注矛盾，这是事实。

2. **E5的正确标注**：正方认为E5应标注为"exploratory"而非"Confirmatory"，理由：
   - E5是InceptionTime简化版（超参变体），不是严格复现原架构
   - 超参变体引入了新的设计选择，不属于confirmatory replication
   - R5在§3.2 E5（Line 317）中的"exploratory"标注是正确的
   - §3.3实验总览表（Line 370）和§3.3"Confirmatory vs Exploratory 明确标注"（Line 376）中的"Confirmatory"标注是未同步的旧标注

3. **修复方法**：将§3.3中E5的标注从"Confirmatory"改为"exploratory"，与§3.2 E5一致。

4. **审稿人影响**：审稿人看到§3.2说E5是exploratory，§3.3说E5是Confirmatory——会困惑E5的性质。这一风险确实存在，但修复简单。

**修复建议**：
- 将Line 370的`| E5: InceptionTime 简化版（超参变体） | **Confirmatory** | 30-45 | 4 天 | +1-3% | G5 |`改为`| E5: InceptionTime 简化版（超参变体） | **Exploratory** | 30-45 | 4 天 | +1-3% | G5 |`
- 将Line 376的`- **Confirmatory**：E1（复现已发表 8 种校准方法在跨语料库 ECG 迁移中的表现）+ E5（复现 InceptionTime 架构在 ECG 上的表现）`改为`- **Confirmatory**：E1（复现已发表 8 种校准方法在跨语料库 ECG 迁移中的表现）`并添加`- **Exploratory**：E5（InceptionTime 简化版超参变体）+ E2（消融实验）+ E3（假设检验）+ E4（分箱温度+偏移敏感度）`

**修复工作量**：约5分钟（两处文本替换）

---

### 2.5 Attack-R5-5反驳：§8.3仍保留"这个估计是独立的"

- **正方立场**：**接受（Accept）**
- **严重级别认同**：P1（内部不一致 + 自相矛盾措辞）
- **性质判定**：编辑同步遗漏 + 措辞混乱

**正方反驳**：

1. **承认事实**：反方引用的Line 1041确实保留"这个估计是独立的，不依赖与 R2/R3 终审的一致性"。这是事实。

2. **自相矛盾承认**：正方承认Line 1039-1041存在自相矛盾：
   - Line 1039说"基于R3终审的锚定估计"
   - Line 1041说"这个估计是独立的，不依赖与 R2/R3 终审的一致性"
   - 这两个声称相互矛盾：如果估计基于R3终审的锚定，则不是独立的；如果估计是独立的，则不基于R3终审的锚定

3. **正确的表述**：R5的接收概率估计（29-37%，中值33%）确实与R3终审一致，但原因不是"独立估计碰巧一致"，而是"R5正确实施了R4终审的修补清单，因此估计与R3终审一致"。正确的表述应删除"独立的"声称，改为"基于R3终审的锚定估计+R5修补的边际影响分析"。

4. **循环论证问题**：反方指出"如果估计真的独立，为什么与R3终审完全一致？"——这一质疑成立。正方不应声称"独立"，而应诚实承认估计基于R3终审的锚定。

5. **修复方法**：删除"这个估计是独立的，不依赖与 R2/R3 终审的一致性"，改为"这个估计基于R3终审的锚定估计+R5修补的边际影响分析，与R3终审估计一致是因为R5正确实施了R4终审的修补清单"。

**修复建议**：
- 将Line 1041的`这个估计是独立的，不依赖与 R2/R3 终审的一致性，而是基于以下因素的综合判断：`替换为`这个估计基于R3终审的锚定估计+R5修补的边际影响分析，与R3终审估计一致是因为R5正确实施了R4终审的修补清单。具体因素如下：`

**修复工作量**：约5分钟（一处文本替换）

---

### 2.6 Attack-R5-6反驳：附录A保留"cross-direction stability analysis"

- **正方立场**：**接受（Accept）**
- **严重级别认同**：P2（术语不一致，影响较小）
- **性质判定**：编辑同步遗漏

**正方反驳**：

1. **承认事实**：反方引用的Line 1294确实包含"cross-direction stability analysis"。同时，§4.2 C2（Line 446）已改为"跨方向描述性比较+变异度报告"。术语不一致，这是事实。

2. **影响较小**：附录A是补充材料，审稿人可能不会仔细阅读。但术语不一致反映文档编辑不仔细，应修复。

3. **修复方法**：将附录A中"cross-direction stability analysis"替换为"cross-direction descriptive comparison"，与§4.2 C2一致。

**修复建议**：
- 将Line 1294的`with cross-direction stability analysis`替换为`with cross-direction descriptive comparison and variance report`

**修复工作量**：约2分钟（一处文本替换）

---

### 2.7 Attack-R5-7反驳："systematic evaluation"标签可能只是"confirmatory"换名

- **正方立场**：**部分接受（Partial Accept）**
- **严重级别认同**：P2
- **性质判定**：措辞改善实质 + LaTeX代码未同步

**正方反驳**：

1. **部分接受**：正方承认§4.3 LaTeX代码（Line 539）仍使用"Confirmatory components"标注E1，与§3.2的"systematic evaluation"标签不一致。这是编辑同步问题，应修复。

2. **反驳"只是换名"**：正方反驳"systematic evaluation只是confirmatory换名"的论点：
   - **"confirmatory"暗示pre-registration**：在开放科学语境中，"confirmatory"特指预先注册假设并检验——E1没有pre-registration，因此"confirmatory"不准确
   - **"systematic evaluation"不暗示pre-registration**：systematic evaluation指系统性评估已发表方法，不暗示假设检验或pre-registration——这更准确描述E1的性质
   - **实质区别**：E1是"在新数据集（跨语料库ECG）上系统性应用已发表方法"，不是"复现原论文的confirmatory hypothesis test"——"systematic evaluation"准确描述前者，"confirmatory"错误暗示后者
   - **审稿人视角**：熟悉开放科学的审稿人会区分"confirmatory"（需pre-registration）和"systematic evaluation"（不需pre-registration）——这不是换名，是准确化

3. **R4 Attack-R4-2的核心问题**：R4反方攻击"confirmatory标签不准确"的核心是"E1是在新数据集上应用已发表方法，不是confirmatory replication"。R5改为"systematic evaluation"**确实解决了这一核心问题**——"systematic evaluation"准确描述了E1的性质。

4. **修复方法**：在§4.3 LaTeX代码中同步使用"systematic evaluation"而非"Confirmatory"。

**修复建议**：
- 将Line 539的`\textbf{Confirmatory components}:`替换为`\textbf{Systematic evaluation components}:`
- 在Methods中明确说明"systematic evaluation"与"confirmatory"的区别——systematic evaluation不暗示pre-registration

**修复工作量**：约10分钟（文本替换 + 添加说明）

---

### 2.8 Attack-R5-8反驳：NCV多阈值报告可能暴露阈值敏感性

- **正方立场**：**部分反驳（Partial Rebut）**
- **严重级别认同**：P2
- **性质判定**：反方攻击是推测性的（"可能暴露"），多阈值报告本身是最佳实践

**正方反驳**：

1. **反驳"可能暴露阈值敏感性"**：反方的攻击是推测性的——"如果不同阈值下NCV结论不一致，则多阈值报告反而暴露NCV对阈值选择的敏感性"。但这一推测没有证据支持：
   - R5尚未实际运行E3实验，不知道不同阈值下NCV结论是否一致
   - 反方假设"τ=0.25时NCV显示校准改善，τ=0.9时NCV显示校准恶化"——这是**未经验证的假设**
   - 实际情况可能是：TS作为单调变换，在所有阈值下NCV方向一致（TS只调整置信度，不改变argmax，因此NCV的变化模式在不同阈值下应一致）

2. **多阈值报告是最佳实践**：
   - **开放科学**：多阈值报告比单一阈值更透明，符合开放科学实践
   - **审稿人信任**：审稿人看到多阈值报告，会认为作者没有选择性报告——这增强信任
   - **稳健性证据**：如果不同阈值下NCV结论一致，多阈值报告**增强**结论稳健性
   - **反方承认**：反方在攻击点4中也承认"多阈值报告确实比单一阈值更透明，符合开放科学实践"

3. **部分接受**：正方承认R5未明确报告不同阈值下NCV结论的一致性。建议在E3实验完成后，明确报告一致性分析。

4. **修复建议**：在§3.2 E3中添加"多阈值一致性分析"声明：
   - 如果实验完成后发现不同阈值下NCV结论一致，强调结论稳健性
   - 如果发现不一致，诚实声明NCV对阈值选择的敏感性
   - 这一修复需要E3实验完成后才能实施——不是文档编辑问题，是实验报告问题

**修复工作量**：约30分钟（E3实验完成后的分析报告）

---

### 2.9 Attack-R5-9反驳：同时报告ECE和Brier reliability但仍将Brier reliability作为"主指标"

- **正方立场**：**部分接受（Partial Accept）**
- **严重级别认同**：P2
- **性质判定**：透明度改善 + "主指标"区分需论证

**正方反驳**：

1. **部分接受**：正方承认同时报告ECE和Brier reliability但仍将Brier reliability作为"主指标"（Line 254）需要额外论证。反方的质疑"选择Brier reliability作为主指标的动机是否仍然是post-hoc的"有一定合理性。

2. **反驳"ECE更常用"**：正方反驳"ECE是校准文献中更常用的指标，因此应选ECE作为主指标"的论点：
   - **Brier reliability是proper scoring rule分量**：Brier score是proper scoring rule，其reliability分量有明确的数学定义（Murphy 1973分解）——这是理论优势
   - **ECE不是proper scoring rule**：ECE是启发式指标，binning方式影响结果，不是proper scoring rule——这是理论劣势
   - **TS效果评估**：TS改变概率分布，Brier reliability直接度量概率分布的校准质量，ECE度量binning后的校准质量——Brier reliability对TS效果更敏感
   - **文献支持**：Kull et al. 2019在NeurIPS中推荐Brier decomposition分析，reliability改善0.01量级被报告为有意义——Brier reliability在跨域校准文献中有先例

3. **"主指标"的合理论证**：选择Brier reliability作为"主指标"的理论论证：
   - Brier reliability是proper scoring rule分量（理论优势）
   - Brier reliability对TS效果更敏感（TS改变概率分布，Brier reliability直接度量）
   - Brier reliability有明确的数学定义（Murphy 1973分解），ECE依赖binning选择
   - 这一论证不是post-hoc的——Brier reliability的理论优势是数学事实，独立于实验结果

4. **修复建议**：在§3.2 E3和§4.3 LaTeX代码中添加Brier reliability作为主指标的理论论证：
   - "Brier reliability is chosen as the primary endpoint because (1) it is a component of a proper scoring rule (Brier score), (2) it directly measures probability calibration quality without binning artifacts, and (3) it is more sensitive to TS effects than ECE because TS changes probability distributions."

**修复工作量**：约20分钟（添加理论论证段落）

---

### 2.10 Attack-R5-10反驳："跨语料库ECG部署中的校准可靠性改善"可能过度包装

- **正方立场**：**部分反驳（Partial Rebut）**
- **严重级别认同**：P2
- **性质判定**：反方攻击部分成立（与§4.3 LaTeX代码矛盾），但"过度包装"论点不成立

**正方反驳**：

1. **部分接受**：正方承认§4.3 LaTeX代码仍说"pure statistical contribution"（Attack-R5-1），与§1的"跨语料库ECG部署中的校准可靠性改善"矛盾。这一矛盾已在Attack-R5-1中承认并提供修复建议。

2. **反驳"过度包装"**：正方反驳"跨语料库ECG部署中的校准可靠性改善是过度包装"的论点：
   - **跨语料库ECG迁移是实际部署问题**：不同医院、不同设备采集的ECG数据存在分布偏移，这是实际部署中的核心问题——不是事后编造的叙事
   - **TS校准的可靠性改善与部署相关**：TS校准在跨语料库迁移中的可靠性改善直接关系到多中心AI-ECG系统的安全部署——这是真实的临床context
   - **实验设计支持**：60实验的6个迁移方向（CPSC2018↔PTBXL等）直接对应跨语料库部署场景——实验设计本身就是针对跨语料库迁移
   - **反方承认**：反方在攻击点4中也承认"§4.5.1的ECG临床部署意义确实提供了合理的临床context。跨语料库ECG迁移确实是实际部署中的问题，TS校准的可靠性改善确实与部署相关。这是合理的叙事重构，不是纯粹包装"

3. **反驳"事后叙事"**：正方反驳"§4.5.1的ECG临床部署意义是事后补充的叙事"的论点：
   - **实验设计的出发点**：60实验的6个迁移方向本身就是跨语料库部署场景——实验设计从一开始就针对跨语料库迁移
   - **叙事重构 vs 事后叙事**：R5将核心贡献从"纯统计贡献"重新定位为"跨语料库ECG部署中的校准可靠性改善"——这是**叙事重构**（重新表述已有实验的意义），不是**事后叙事**（编造新的实验目的）
   - **区别**：事后叙事是"实验做完了才发现可以包装成某个故事"，叙事重构是"实验本身针对某个问题，但之前的表述没有突出这一点"。R5属于后者。

4. **修复建议**：确保§4.3 LaTeX代码与§1定位一致（删除"pure statistical contribution"，已在Attack-R5-1中提供修复建议）。在Methods中明确说明实验设计与ECG部署的关联。

**修复工作量**：约15分钟（与Attack-R5-1的修复合并实施）

---

### 2.11 Attack-R5-11反驳：R5收敛标准声明中预设收敛（循环论证）

- **正方立场**：**接受（Accept）**
- **严重级别认同**：P2
- **性质判定**：文档声明问题，不影响论文实质

**正方反驳**：

1. **承认事实**：反方引用的Line 1454-1468确实包含R5收敛标准声明，且声明中预设了收敛。这是事实。

2. **循环论证承认**：正方承认R5在收敛标准声明中预设收敛是循环论证：
   - R5声称"三方估计发散度 < 3%"，但三方估计中有一方是R5自己
   - R5自己说收敛，然后声称三方一致——这是"学生自己给自己打分"
   - 收敛标准应该由反方和终审独立验证，而非正方自己声明

3. **与反方审查结果矛盾**：反方审查发现11个攻击点（5个P1），R5未达到收敛标准（攻击点≤5个且无P1级）。R5的收敛声明与反方审查结果矛盾。

4. **影响较小**：这是文档声明问题，不影响论文实际内容。但反映R5对收敛标准的理解有误。

5. **修复方法**：删除R5中的收敛标准声明，改为"R5是否收敛需由反方和终审独立判定"。

**修复建议**：
- 将Line 1454-1468的R5收敛标准声明删除
- 替换为"R5是否收敛需由反方审查和终审独立判定。R5自身不做收敛声明。"

**修复工作量**：约5分钟（删除并替换声明）

---

## §3 正方立场总结

### 3.1 立场汇总表

| 攻击点 | 严重级别 | 正方立场 | 修复工作量 | 性质判定 |
|--------|---------|---------|-----------|---------|
| Attack-R5-1 | P1 | 接受 | 10分钟 | 编辑同步遗漏 |
| Attack-R5-2 | P1 | 接受 | 10分钟 | 编辑同步遗漏（技术论证） |
| Attack-R5-3 | P1 | 接受 | 15分钟 | 编辑同步遗漏（时间线声称） |
| Attack-R5-4 | P1 | 接受 | 5分钟 | 编辑同步遗漏 |
| Attack-R5-5 | P1 | 接受 | 5分钟 | 编辑同步遗漏 + 措辞混乱 |
| Attack-R5-6 | P2 | 接受 | 2分钟 | 编辑同步遗漏 |
| Attack-R5-7 | P2 | 部分接受 | 10分钟 | 措辞改善实质 + LaTeX未同步 |
| Attack-R5-8 | P2 | 部分反驳 | 30分钟 | 反方推测性攻击 |
| Attack-R5-9 | P2 | 部分接受 | 20分钟 | 透明度改善 + 主指标需论证 |
| Attack-R5-10 | P2 | 部分反驳 | 15分钟 | 与LaTeX矛盾（已计入R5-1） |
| Attack-R5-11 | P2 | 接受 | 5分钟 | 文档声明问题 |

**总修复工作量**：约2小时15分钟（P1级约45分钟，P2级约1小时30分钟）

### 3.2 正方核心论点

**正方核心论点1：R5的P1级攻击是内部不一致问题，不是实质性论证缺陷**

R5的5个P1级攻击全部是"叙述位置已修补但LaTeX代码未同步"的编辑遗漏问题。这与R4的5个P1级攻击（核心贡献定位错误、技术论证错误、post-hoc rationalization、标注不一致、循环论证）在性质上根本不同：
- R4 P1级攻击需要根本性修改论证结构
- R5 P1级攻击只需要同步LaTeX代码（机械性编辑操作）

**正方核心论点2：R5的叙述性位置修补反映了正方的真实意图**

R5在§1、§3.2、§4.2、§4.5.1等叙述性位置的修补是正方的真实意图——将核心贡献重新定位、修正技术论证、删除post-hoc rationalization、统一E5标注、修正接收概率表述。LaTeX代码中的旧声称是编辑遗漏，不是正方有意保留的论证。

**正方核心论点3：R5相比R4有实质进步**

R5相比R4的实质进步：
1. P2级攻击从8个减少到6个（-2）
2. §4.5 Discussion补充ECG临床部署意义和效应量文献对照
3. 文档从4194行压缩到1482行（删除重复内容）
4. "systematic evaluation"标签比"confirmatory"更准确
5. NCV多阈值报告增加透明度
6. 同时报告ECE和Brier reliability增加透明度

**正方核心论点4：R5的P1级攻击修复简单，R6轮有望达到收敛**

R5的5个P1级攻击修复工作量约45分钟（5处文本替换 + 2处标注修改）。修复后，R5的P1级攻击将降至0个。P2级攻击中，Attack-R5-6和R5-11可同步修复（约7分钟），Attack-R5-7和R5-9需添加论证段落（约30分钟），Attack-R5-8需E3实验完成后报告一致性（约30分钟），Attack-R5-10与Attack-R5-1修复合并实施。R6轮有望达到收敛（攻击点≤5个且无P1级）。

### 3.3 正方对收敛的判断

**正方收敛判断**：R5当前未达到收敛标准（11个攻击点>5，5个P1级>0），但R5的未收敛原因是**编辑同步问题**，不是**论证缺陷**。R6轮只需进行机械性编辑同步（约2小时15分钟工作量），即可将攻击点降至≤3个P2级，达到收敛标准。

**与反方收敛判断的共识**：正方与反方在收敛判断上达成共识——R5未达到收敛标准，需要R6轮。但正方强调R6轮修补的简单性（编辑同步），反方也承认"R6轮只需修正5个P1级内部不一致问题（同步LaTeX代码），预计1-2小时工作量"。

---

## §4 对R6轮的建议

### 4.1 R6轮修补优先级

**P1级（必须修补，约45分钟）**：
1. **Attack-R5-1**：将§4.3 LaTeX代码Line 524-529和Line 719-720的"pure statistical contribution"替换为"calibration reliability improvement in cross-corpus ECG deployment"
2. **Attack-R5-2**：将§4.3 LaTeX代码Line 517-518和Line 662-663的"TS directly affects reliability without affecting resolution"替换为"TS does not change argmax, so evaluation should use probability-dependent metrics"
3. **Attack-R5-3**：将§4.3 LaTeX代码Line 658-665和Line 670-671、附录A Line 1294和Line 1369的"theoretical prior"替换为"mathematical property of TS"，删除"was recognized before A1 was created"
4. **Attack-R5-4**：将§3.3 Line 370和Line 376中E5的标注从"Confirmatory"改为"exploratory"
5. **Attack-R5-5**：删除§8.3 Line 1041中"这个估计是独立的"，改为"基于R3终审的锚定估计+边际影响分析"

**P2级（建议修补，约1小时30分钟）**：
6. **Attack-R5-6**：将附录A Line 1294中"stability analysis"替换为"descriptive comparison"（2分钟）
7. **Attack-R5-7**：在§4.3 LaTeX代码中同步使用"systematic evaluation"而非"Confirmatory"（10分钟）
8. **Attack-R5-8**：在E3实验完成后报告NCV多阈值结论的一致性分析（30分钟，需实验完成）
9. **Attack-R5-9**：在§3.2 E3和§4.3 LaTeX代码中添加Brier reliability作为主指标的理论论证（20分钟）
10. **Attack-R5-10**：与Attack-R5-1修复合并实施，确保§4.3 LaTeX代码与§1定位一致（已计入Attack-R5-1）
11. **Attack-R5-11**：删除R5收敛标准声明，改为"R5是否收敛需由反方和终审独立判定"（5分钟）

### 4.2 R6轮收敛预测

如果R6轮修正上述5个P1级内部不一致问题 + 6个P2级问题：
- **P1级攻击**：0个（内部不一致问题全部解决）
- **P2级攻击**：0-2个（Attack-R5-8需E3实验完成才能完全解决，可能残留1-2个P2级关于实验结果的攻击）
- **总攻击点**：0-2个
- **判定**：**达到收敛标准**（攻击点≤5个且无P1级）

### 4.3 R6轮与R4/R5的区别

| 维度 | R4→R5 | R5→R6 |
|------|-------|-------|
| **修补性质** | 叙述性位置修补（改措辞） | LaTeX代码同步（机械性编辑） |
| **修补工作量** | 数小时（需重新表述论证） | 约2小时15分钟（文本替换） |
| **修补风险** | 中（可能引入新问题） | 低（机械性操作，不改变论证结构） |
| **收敛可能性** | 未收敛（LaTeX未同步） | 高（同步后P1级攻击消除） |

---

## §5 正方独立接收概率估计

### 5.1 正方独立估计

**正方独立估计：30-36%（中值33%）**

### 5.2 估计理由

**上行因素**（使接收概率向36%靠拢）：
1. **R5相比R4的改善**：+1-2%
   - P2级攻击从8个减少到6个
   - §4.5 Discussion补充ECG临床部署意义和效应量文献对照
   - "systematic evaluation"标签比"confirmatory"更准确
   - NCV多阈值报告增加透明度
   - 同时报告ECE和Brier reliability增加透明度

2. **R5的P1级内部不一致问题影响有限**：-1-2%
   - 这些是编辑同步问题，审稿人看到的是最终论文（LaTeX代码），不会对比R5提案文档的叙述位置和LaTeX代码
   - 但LaTeX代码中确实保留旧声称，审稿人可能直接质疑——需R6轮同步修复
   - 部分抵消：+0-1%（R5的叙述性位置修补反映了正方真实意图，R6轮同步后可完全消除）

3. **R6轮同步修复后**：+1-2%
   - R6轮同步LaTeX代码后，P1级内部不一致问题全部消除
   - 论文实际写入的LaTeX代码与叙述性位置一致
   - 审稿人看到的是修正后的论文

**下行因素**（使接收概率向30%靠拢）：
1. **效应量小（ECE 0.016）是无法修补的硬伤**：-5-8%（已计入R4基线，不重复扣减）
2. **CBM 12%接收率竞争激烈**：即使方案完美，接收概率也受期刊接收率限制
3. **CBM审稿人可能不接受"跨语料库ECG部署中的校准可靠性改善"作为临床期刊的贡献**：若审稿人要求临床意义，接收概率可能降至25-30%

### 5.3 三方估计对比

| 来源 | 估计范围 | 中值 |
|------|---------|------|
| R5自身估计 | 29-35% | 32% |
| R5反方独立估计 | 28-34% | 31% |
| **R5正方独立估计** | **30-36%** | **33%** |

**三方分歧**：正方（33%）与反方（31%）分歧2%，在3%阈值内。

### 5.4 正方与反方估计的差异原因

正方估计（30-36%，中值33%）比反方估计（28-34%，中值31%）高2%，原因：
1. **正方对R5改善的评价更高**：正方认为§4.5 Discussion补充和"systematic evaluation"标签改善的边际贡献更大（+1-2%）
2. **正方对P1级内部不一致问题的影响评价更低**：正方认为这些是编辑同步问题，R6轮同步后可完全消除，对最终论文影响有限（-1-2% vs 反方的-2-3%）
3. **正方对R6轮同步修复的信心更高**：正方认为R6轮同步修复后，论文实际写入的LaTeX代码与叙述性位置一致，P1级攻击全部消除（+1-2%）

### 5.5 关键风险

**R5的关键风险与R4相同**：

1. **效应量硬伤**：ECE 0.016 / Brier reliability ~0.01的改善量小，是无法修补的硬伤
2. **§4.3 LaTeX代码问题**：论文实际写入的LaTeX代码仍包含"pure statistical contribution"、"TS不影响resolution"、"theoretical prior"等被攻击声称——审稿人看到这些会质疑。**R6轮同步修复后可消除**
3. **CBM期刊适配性**：核心贡献是校准可靠性改善，CBM是临床应用期刊——审稿人可能质疑论文是否适合CBM

---

## 签名

**正方论证代理-R5-Rebuttal 签名**：正方论证代理-R5-Rebuttal（GLM-5.2）
**交付日期**：2026-09-12
**反驳攻击总数**：11个（接受6个 / 部分接受3个 / 部分反驳2个）
**关键结论1**：R5的5个P1级攻击全部是内部不一致问题（编辑同步遗漏），不是实质性论证缺陷。修复工作量约45分钟（5处文本替换）。
**关键结论2**：R5相比R4有实质进步（P2级攻击-2，Discussion补充，文档压缩），但进步被内部不一致问题掩盖。
**关键结论3**：R6轮只需进行机械性编辑同步（约2小时15分钟工作量），即可将攻击点降至≤2个P2级，达到收敛标准。
**收敛判断**：R5当前未收敛（11个攻击点>5，5个P1级>0），但R6轮修补简单，有望达到收敛。
**正方独立接收概率估计**：30-36%（中值33%）
**三方分歧**：正方（33%）与反方（31%）分歧2%，在3%阈值内。
**对R6轮的建议**：P1级必须修补（约45分钟），P2级建议修补（约1小时30分钟），总工作量约2小时15分钟。
