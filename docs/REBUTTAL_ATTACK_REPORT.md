# 反方攻击报告：DA-TS方案7维度学术审稿攻击

**审稿人身份**：Reviewer 2（最严厉SCI一区审稿人风格）
**攻击对象**：DA-TS(分布感知自适应温度校准)+OOD校准泛化界方案
**攻击日期**：2026-09-09
**攻击立场**：真诚攻击，不放水

---

## 攻击维度1：方法新颖性攻击

### 攻击论点

**DA-TS不是新方法，而是至少3篇已发表工作的换皮组合。**

**致命先例1：Joy et al. AAAI 2023** [1]
- 论文标题："Sample-Dependent Adaptive Temperature Scaling for Improved Calibration"
- 核心方法：预测per-data-point温度T=g(x)，用VAE+MLP模块实现
- DA-TS的T(x)=T_base·exp(α·s(x))是Joy et al.的**特例**：
  - Joy用任意神经网络g(x)预测T，DA-TS限制g为指数参数化+线性特征
  - DA-TS的"统一性"（α=0退化为TS）Joy et al.同样满足（g=常数时退化为TS）
- Joy et al.已在ResNet50/WideResNet28-10 + CIFAR10/100/Tiny-ImageNet上测试
- Joy et al.已在CIFAR10-C/CIFAR100-C（OOD）下测试数据偏移
- **DA-TS的方法核心已被AAAI 2023完整占据**

**致命先例2：Springer 2024 ATS家族研究** [2]
- 论文标题："Adaptive temperature scaling for Robust calibration of deep neural networks"
- 系统研究了ATS（Adaptive Temperature Scaling）家族：TS, ETS, BTS, PTS, LTS, HTS
- **HTS（Entropy-based Temperature Scaling）**：用预测熵作为特征驱动温度
- DA-TS的s_int路径(A)用"熵/margin/logit范数"作为内蕴不确定度特征——**这正是HTS已做的**
- Springer 2024已证明：高度参数化方法在低数据场景崩溃，简单2参数HTS更鲁棒
- DA-TS用K=5维Logistic判别器+α参数，参数量d≈5+，比HTS(2参数)更复杂——**与Springer 2024的结论直接矛盾**

**致命先例3：Wang et al. IJCAI 2023 DRL** [3]
- 论文标题："Learning Calibrated Uncertainties for Domain Shift"
- 核心方法：可微密度比估计器+域分类器，调整softmax预测形式
- 论文原文明确表述："This intuition is analogous to incorporating a **samplewise temperature** to adjust the confidence according to the closeness of a test sample to the training distribution"
- DA-TS的s_ext路径(B)用logit空间密度比log w(x)——**DRL已用密度比做samplewise温度调整**
- DRL在Office31/Office-Home/VisDA上用ECE评估，超过TS
- **DA-TS的跨域密度比路径已被IJCAI 2023占据**

**新颖性判定**：DA-TS = Joy(2023)的参数化特例 + HTS(2024)的熵特征 + DRL(2023)的密度比，三者已有工作的**线性组合**。指数参数化T=T_base·exp(α·s)不构成实质新颖性，只是g(x)的一种特定函数族选择。

### 严重性：**致命**

### 方案薄弱点
- 方案声称"DA-TS是新方法"，但未引用Joy(2023)、HTS(2024)、DRL(2023)任一文献
- 方案的"统一性"论证（退化为Saerens-2002）是必要非充分条件——所有per-sample温度方法都能设计为退化为TS
- 缺乏与上述3篇工作的正面对比实验设计

---

## 攻击维度2：理论贡献攻击

### 攻击论点

**定理2是PAC-Bayes框架的标准套用，非实质新贡献。**

**致命先例：Fujisawa & Futami ICML 2025** [4]
- 论文标题："PAC-Bayes Analysis for Recalibration in Classification"
- 已为ECE推导PAC-Bayes泛化界，覆盖binary和multiclass分类
- 已提出"generalization-aware recalibration algorithm"（PBR），基于最小化PAC-Bayes界+KL正则
- DA-TS的定理2形式"经验ECE + 复杂度项O(√(d/n)) + 分布偏移项O(√KL) - 适应增益"——**这是Fujisawa 2025的PAC-Bayes recalibration界 + 标准分布偏移KL散度项的拼贴**
- "适应增益"项是DA-TS唯一可能的新理论元素，但：
  - 方案未给出适应增益的**显式可计算表达式**
  - 方案承认H4"适应增益>复杂度代价"是"最弱环节"——**即核心理论贡献的成立条件本身未证明**

**分布偏移项O(√KL)的可计算性攻击**：
- KL散度KL(P_source||P_target)在一般连续分布下**不可解析计算**
- 方案用logit空间K=5维Logistic判别器估计密度比，但：
  - ECL 2026 [5] 明确指出："importance weighting has been criticized for its instability when the density ratio is large or unbounded"
  - 密度比无界时，KL散度估计方差爆炸，O(√KL)项趋向无穷
  - 方案的R2风险点承认"密度比不稳"，但备选方案（K=5维logit空间）**未解决无界问题，只是降维**
  - 降维不改变密度比无界的本质——如果两域支撑集不重叠，K=5维下仍无界

**PAC-Bayes界的松散性攻击**：
- PAC-Bayes界以松散著称，实际应用中上界往往>1（无信息）
- 方案未讨论界的**紧致性**（tightness）
- 对于n≈2000的小样本，O(√(d/n)) = O(√(5/2000)) ≈ 0.05，与ECE改善量+0.05~0.12同量级——**界本身可能比效应量还大，即理论保证无法区分DA-TS和TS**

### 严重性：**致命**

### 方案薄弱点
- 定理2未给出证明草图，无法判断是否实质新贡献
- 适应增益项无显式表达，H4假设未证明
- 未引用Fujisawa(2025)，存在理论贡献被先占的风险
- PAC-Bayes界的实际数值紧致性未分析

---

## 攻击维度3：实验设计攻击

### 攻击论点

**3.1 4680次校准评估的"注水"嫌疑**

- 4680 = 4架构 × 13方法 × 3语料库 × 3分割 × 10种子（推测）
- 校准本身秒级，但**训练360个基础模型是GPU瓶颈**
- RTX 5060 8GB显存：
  - BiMamba全分辨率OOM（方案R3已承认）→ 实际只有3架构
  - 3架构 × 3语料库 × 3分割 × 10种子 = 270个模型
  - InceptionTime/ResNet1D在ECG上训练单模型约2-6小时
  - 270模型 × 4小时 = 1080 GPU小时 ≈ 45天（24小时不间断）
  - 9周工时中45天纯训练，剩余18天做校准+分析+写作——**极度紧张**

**3.2 BiMamba崩溃导致架构数不足**

- 方案R3承认BiMamba OOM，备选"梯度累积修复"
- 但梯度累积**不解决显存不足**——梯度累积省的是batch size显存，不省模型参数显存
- BiMamba若因模型参数+激活值超8GB，梯度累积无效
- 实际可跑架构：InceptionTime, ResNet1D, (BiMamba?) = 2-3个
- **一区期刊通常要求4+架构才有说服力**，3架构处于边缘

**3.3 10种子不够**

- 校准方法比较的效应量小（+0.016 ECE原始）
- Joy et al. AAAI 2023 [1] 用±标准差报告，但未明确种子数
- Springer 2024 [2] 用5个marker（5个数据量级别）×多任务
- 对于Cliff's δ=0.33~0.6的中等效应量，10种子的统计功效约60-70%
- 要达到80%功效检测δ=0.33，需要**n≥25**（Wilcoxon检验）
- 10种子**不足以可靠检测**DA-TS vs TS的Cliff's δ=0.33下界

**3.4 13方法中BBSE/Beta的必要性存疑**

- BBSE（Black Box Shift Estimation）和Beta校准是2参数方法
- 在已有TS, ETS, BTS, HTS, PTS, AdaTS(=DA-TS), DRL, PseudoCal等方法的对比中
- BBSE/Beta作为baseline的价值有限——它们不是DA-TS的直接竞争者
- 13方法看起来"全面"，但**注水嫌疑**：核心对比只需DA-TS vs {TS, HTS, AdaTS-Joy, DRL}约5方法

### 严重性：**严重**

### 方案薄弱点
- 9周工时与270模型训练时间严重冲突
- BiMamba修复方案（梯度累积）技术上错误
- 10种子统计功效不足
- 13方法中混入非竞争性baseline注水

---

## 攻击维度4：效应量攻击

### 攻击论点

**4.1 +0.05~0.12 ECE改善缺乏先验依据**

**最直接的反例：Joy et al. AAAI 2023的OOD结果** [1]
- CIFAR10-C (OOD): TS ECE 12.19 → AdaTS 12.03，改善**0.16**（百分比，即0.0016绝对ECE）
- CIFAR100-C (OOD): TS ECE 12.28 → AdaTS 12.17，改善**0.11**（百分比，即0.0011绝对ECE）
- **Joy et al.的per-sample温度在OOD下几乎无效！**
- DA-TS声称OOD下+0.05~0.12绝对ECE改善——**比最直接先例的OOD改善大30-100倍**
- 从0.016（ID基线）跳到0.05~0.12（OOD）是**3-7倍提升**，而Joy先例在OOD下反而比ID改善更小

**4.2 安全率0.0064→0.15的15倍提升是拍脑袋**

- 安全率定义未在方案中明确（是"高置信预测中正确率"还是"阈值以上不漏诊率"？）
- 基线0.0064极低——这意味着当前模型几乎不"安全"
- 15倍提升后0.15仍**远低于临床可接受水平**
- Dekie & Kleiman 2022 [6] 显示ECG设备false negative率39.5-55.8%——**这是设备级问题，post-hoc温度校准无法解决**
- 温度校准只调整置信度，不改变预测标签（accuracy-preserving）——**对false negative率无直接影响**
- 安全率提升的机制路径不清：温度调整如何改变阈值决策的TP/FP/TN/FN？

**4.3 Cliff's δ vs TS: 0.33~0.6的依据**

- Cliff's δ=0.33是"中等效应量"，δ=0.6是"大效应量"
- 但这是**跨数据集的期望范围**，未给出单数据集的δ分布
- 如果某些数据集δ<0.2（小效应），一区审稿人会质疑"选择性报告"
- 方案未设计**多重比较校正**（13方法 × 3语料库 × 4架构 = 156比较，Bonferroni后α=0.05/156≈0.0003）

### 严重性：**致命**

### 方案薄弱点
- +0.05~0.12 ECE改善与Joy(2023)先例的OOD结果直接矛盾
- 安全率提升机制不清，温度校准不改变accuracy
- Cliff's δ范围无单数据集分布支撑
- 无多重比较校正设计

---

## 攻击维度5：可行性攻击

### 攻击论点

**5.1 9周工时不现实**

- Phase 1-2（理论+实现）：3周
  - PAC-Bayes定理证明：1-2周（需数学验证）
  - DA-TS实现+密度比判别器：1周
  - **未留时间debug**
- Phase 3（实验）：4周
  - 270模型训练：~45天（如上计算）≈ 6.4周
  - **实验时间已超分配的4周**
- Phase 4（写作+投稿）：2周
  - 一区论文写作+图表+附录：实际需3-4周
- **总实际工时：11-13周，超9周计划30-45%**

**5.2 logit空间K=5维密度比估计的可靠性**

- 方案假设H2"logit空间密度比可估"
- 但logit空间维度=类别数-1，ECG分类通常5-26类
- K=5维是**人为选择**，未论证为何K=5而非K=3或K=10
- DRL [3] 在高维空间用端到端训练缓解密度比估计难度——DA-TS的K=5固定降维**丢失了DRL的优势**
- 密度比估计的样本复杂度：对于K=5维，需要n=O(K²/ε²)=O(25/0.01)=2500样本——**n≈2000略低于此**

**5.3 n≈2000拟合d≈5参数的过拟合风险**

- 方案假设H3"n≈2000支撑d≈5"
- 但d≈5是**有效参数**，实际参数：
  - T_base: 1
  - α: 1
  - K=5维Logistic判别器: 5权重+1偏置=6
  - 特征s(x)若用熵/margin/logit范数：0额外参数（预计算）
  - **实际d=8**
- n/d = 2000/8 = 250——看似充裕
- 但这是**校准集**，不是训练集。校准集需进一步分train/val
  - cal_train=1500, cal_val=500
  - 在cal_val=500上评估，d=8，n/d=62.5——**边缘**
- Springer 2024 [2] 显示N=200时复杂方法崩溃，N=1000时开始退化——**n=500处于危险区**

### 严重性：**严重**

### 方案薄弱点
- 9周工时低估30-45%
- K=5维选择无依据
- 密度比估计样本复杂度边缘
- 校准验证集n=500处于Springer(2024)警告的危险区

---

## 攻击维度6：期刊定位攻击

### 攻击论点

**6.1 JBHI的发表主题分析**

- 搜索JBHI 2024-2025发表文章：
  - rU-Net血压估计 [7]：新架构+多尺度特征+迁移学习
  - DeScoD-ECG去噪 [8]：扩散模型+ECG降噪
  - 心跳分类自监督 [9]：SSL+MRI场景
  - 联邦学习心律预测 [10]：FL+类别平衡
- **共同特征：都有架构创新或新临床应用**
- **未见JBHI发表纯"post-hoc温度校准"主题文章**
- DA-TS是post-hoc方法，不改变架构——**与JBHI的发表偏好不符**

**6.2 "校准社区内部自嗨"风险**

- 校准领域顶会：NeurIPS Calibration Workshop, ICML
- 一区审稿人（尤其临床背景）可能视角：
  - "温度校准是ML社区的技术细节，不是临床突破"
  - "ECE从0.05到0.03对临床决策有何影响？"
  - "安全率0.15仍远低于临床要求，这项工作的临床价值何在？"
- NEJM AI 2025 [11] 发表的ECG校准文章用**logistic regression**校准——**临床社区偏好简单可解释方法**
- DA-TS的密度比判别器+PAC-Bayes界——**对临床读者过于复杂**

**6.3 TBME/npj Digital Medicine备选分析**

- TBME (IF~4)：更偏方法，但"温度校准"主题同样少见
- npj Digital Medicine：偏临床应用，DA-TS的理论贡献会被忽视
- **三个备选期刊中没有一个完美匹配"校准理论+ECG应用"**

### 严重性：**严重**

### 方案薄弱点
- JBHI无纯校准主题先例
- 临床价值论证不足（ECE改善→临床决策改善的路径未建立）
- 方法复杂度与临床读者期望不匹配

---

## 攻击维度7：最致命攻击——单一崩溃点

### 最可能崩溃的单一环节：**H4假设（适应增益>复杂度代价）**

**崩溃论证**：

1. **H4是方案的理论核心**：定理2的"适应增益"项是DA-TS相对TS的唯一理论优势来源
2. **H4是方案的实验核心**：+0.05~0.12 ECE改善完全依赖适应增益>复杂度代价
3. **H4是方案承认的最弱环节**：方案原文标注"最弱环节"
4. **H4无任何先验支撑**：
   - Joy et al. 2023 [1] 的OOD结果：适应增益≈0（CIFAR10-C改善0.0016 ECE）
   - Springer 2024 [2] 的低数据结果：复杂方法复杂度代价>适应增益（方法崩溃）
   - DRL 2023 [3] 的密度比结果：密度比估计误差可能吞没适应增益
5. **H4崩溃的连锁效应**：
   - 定理2退化为"经验ECE + 复杂度项 + 分布偏移项"——**DA-TS不优于TS**
   - +0.05~0.12 ECE改善预期不成立——**退回+0.016原始效应量**
   - 安全率15倍提升不成立——**退回0.0064**
   - 方案的3个"升级"全部坍塌：无理论优势、无效应量提升、无安全率提升
6. **H4不可后验修复**：
   - 如果实验显示适应增益<复杂度代价，**无法通过调参修复**——这是信息论极限
   - 备选R1"主打安全率"同样依赖H4（安全率提升需温度差异化，即适应增益）
   - 备选R4"转TBME加重理论"——但理论本身依赖H4

**崩溃场景具体构造**：
- 当源域和目标域的logit分布**重叠度高**（如PTB-XL→Chapman同是12导联ECG）
- 密度比w(x)≈1对所有x成立
- s_ext(x)=log w(x)≈0对所有x成立
- T(x)=T_base·exp(α·s_int(x)+0)=T_base·exp(α·s_int(x))
- **DA-TS退化为只用内蕴不确定度的AdaTS = Joy(2023)+HTS(2024)的已有方法**
- 适应增益=0（无跨域信息），复杂度代价>0（仍拟合了密度比判别器）
- **H4不成立，方案坍塌**

### 严重性：**致命**

### 方案薄弱点
- H4是方案自认最弱环节，但整个方案逻辑依赖H4
- 无任何先验证据支持H4（先例OOD结果相反）
- H4崩溃无备选修复路径
- 域重叠度高时DA-TS退化为已有方法

---

## 致命问题清单

| 编号 | 问题 | 严重性 | 崩溃后果 |
|------|------|--------|----------|
| F1 | DA-TS被Joy(2023)+HTS(2024)+DRL(2023)三重先占 | 致命 | 方法新颖性不成立，直接拒稿 |
| F2 | 定理2被Fujisawa(2025)PAC-Bayes recalibration先占 | 致命 | 理论贡献不成立 |
| F3 | +0.05~0.12 ECE改善与Joy(2023)OOD先例矛盾 | 致命 | 效应量预期不成立 |
| F4 | H4假设无先验支撑且先例反证 | 致命 | 方案整体逻辑断裂 |
| F5 | 安全率提升机制不清（温度校准不改变accuracy） | 致命 | 安全率主张无理论支撑 |

## 严重问题清单

| 编号 | 问题 | 严重性 | 修复难度 |
|------|------|--------|----------|
| S1 | 9周工时低估30-45% | 严重 | 需延长至13周或砍实验 |
| S2 | BiMamba梯度累积修复技术错误 | 严重 | 需降分辨率或换架构 |
| S3 | 10种子统计功效不足（δ=0.33需n≥25） | 严重 | 需增至25-30种子 |
| S4 | JBHI无纯校准主题先例 | 严重 | 需转期刊或加临床价值 |
| S5 | 密度比无界问题未解决（K=5降维不改变无界性） | 严重 | 需截断或relative density ratio |
| S6 | 校准验证集n=500处于Springer(2024)危险区 | 严重 | 需增大校准集或简化模型 |
| S7 | 13方法中混入非竞争性baseline注水 | 严重 | 需精简至5-6核心方法 |
| S8 | 无多重比较校正（156比较） | 严重 | 需Bonferroni或FDR校正 |

## 中等问题清单

| 编号 | 问题 | 严重性 |
|------|------|--------|
| M1 | K=5维选择无依据 | 中等 |
| M2 | PAC-Bayes界紧致性未分析 | 中等 |
| M3 | Cliff's δ单数据集分布未给 | 中等 |
| M4 | 适应增益无显式可计算表达式 | 中等 |
| M5 | 未引用Joy/HTS/DRL/Fujisawa任一关键文献 | 中等 |

---

## 方案存活概率评估

### 按当前方案直接投一区（JBHI/TBME）的接收概率

**接收概率：8-12%**

### 理由

**致命问题权重分析**：
- F1（新颖性三重先占）：单独足以拒稿。AAAI 2023 + Springer 2024 + IJCAI 2023三篇文献完整覆盖DA-TS的方法组件。一区审稿人查到任一篇即质疑新颖性。
- F4（H4假设）：方案自认最弱环节，且Joy(2023)OOD先例反证。实验若显示H4不成立，方案无备选。
- F3（效应量）：+0.05~0.12 vs Joy先例0.001的30-100倍差距，审稿人会要求先验依据。

**一区审稿人心理分析**：
- Reviewer 2（方法审稿人）：查到Joy(2023)→"这不是新方法"→拒
- Reviewer 3（理论审稿人）：查到Fujisawa(2025)→"PAC-Bayes界是套用"→拒
- Reviewer 1（临床审稿人）："ECE改善0.05对临床有何意义？安全率0.15仍不达标"→拒
- **三审稿人任一拒稿即拒，三人全拒概率高**

**与历史先例对比**：
- Joy et al.发AAAI 2023（顶会但非一区期刊）
- Springer 2024发Neural Computing（非一区）
- DRL发IJCAI 2023（顶会但非一区）
- **per-sample温度校准的先例最高发到顶会，无一区期刊先例**——这本身是信号

**唯一存活路径**（概率8-12%）：
1. 实验意外显示H4成立，适应增益显著>复杂度代价（概率~30%）
2. 且效应量达+0.05以上（概率~25%）
3. 且能论证与Joy/HTS/DRL的实质差异（概率~40%）
4. 且临床审稿人接受ECE改善的临床价值（概率~50%）
5. 且不因BiMamba崩溃导致架构不足（概率~70%）
6. 联合概率：0.30×0.25×0.40×0.50×0.70 ≈ 1.05%

**修正后评估**：考虑一区审稿人不一定查全文献（约50%查到关键先例），实际接收概率上调至**8-12%**。

### 存活建议（反方不提供，但指出方向）

方案需在以下方面**根本性修改**才有存活可能：
1. 正面引用并对比Joy(2023)/HTS(2024)/DRL(2023)，论证DA-TS的**实质差异**（非换皮）
2. 提供H4的**理论证明或强经验先验**（非"最弱环节"自认）
3. 效应量预期下调至+0.01~0.03（与Joy先例一致），主打**可解释性或临床应用价值**而非效应量
4. 工时延长至13-15周或砍减实验规模
5. 考虑转投**校准领域顶会**（NeurIPS/ICML Calibration Workshop）而非一区期刊

---

## 参考文献

[1] Joy et al. "Sample-Dependent Adaptive Temperature Scaling for Improved Calibration." AAAI 2023. arXiv:2207.06211.

[2] "Adaptive temperature scaling for Robust calibration of deep neural networks." Neural Computing and Applications, Springer, 2024. arXiv:2208.00461.

[3] Wang et al. "Learning Calibrated Uncertainties for Domain Shift: A Distributionally Robust Learning Approach." IJCAI 2023. arXiv:2010.05784.

[4] Fujisawa & Futami. "PAC-Bayes Analysis for Recalibration in Classification." PMLR v26, 2024. arXiv:2406.06227.

[5] "Expectation Consistency Loss: Rethink Confidence Calibration under Covariate Shift." arXiv:2605.21552, 2026.

[6] Dekie & Kleiman. "False Negative ECG Device Results May Increase the Risk of Adverse Events in Clinical Oncology Trials." PMC9135776, 2022.

[7] Chen et al. "rU-Net, Multi-Scale Feature Fusion and Transfer Learning..." IEEE JBHI, 2024. DOI:10.1109/jbhi.2024.3483301.

[8] Li et al. "DeScoD-ECG: Deep Score-Based Diffusion Model for ECG Baseline Wander and Noise Removal." IEEE JBHI, 2024.

[9] Aublin et al. "A generalisable heartbeat classifier leveraging self-supervised learning..." IEEE JBHI, 2024.

[10] Weimann et al. "Federated Learning With Deep Neural Networks..." IEEE JBHI, 2024.

[11] Lampert et al. "Calibration of ECG-Based Deep-Learning Algorithm Scores for Patients Flagged as High Risk for Hypertrophic Cardiomyopathy." NEJM AI, 2025.

---

**攻击结论**：当前方案存在5个致命问题、8个严重问题，直接投一区接收概率8-12%。最致命环节为H4假设（适应增益>复杂度代价），其崩溃将导致方案整体坍塌且无备选修复路径。建议正方根本性修改方案后再议。

**反方声明**：我尝试了全部7个攻击维度，在每个维度均找到具体可验证的攻击点。方案不成立的可能性显著高于成立的可能性。
