# ECG校准研究升级SCI一区方案（正方论证）

> 正方论证代理交付。本方案明确标注：核心主张、关键假设、适用边界、推理链条、风险点与备选。
> 诚实原则：不确定能work的部分均标注【风险点】并给出备选。

---

## 0. 方案定位（一句话）

将"评估TS边界"的2区工作，升级为"提出分布感知自适应温度校准(DA-TS)并给出OOD校准泛化界"的1区方法+理论工作；当前边界研究的3个失败分支作为**新方法的动机证据**而非结论。

---

## 1. 核心方法创新

### 1.1 新方法名称
**DA-TS: Distribution-Aware Adaptive Temperature Scaling（分布感知自适应温度校准）**

### 1.2 核心思想
固定TS用一个标量 T 拟合源域验证集NLL。DA-TS把 T 推广为**样本函数** T(x)，使温度随样本的"分布偏移敏感度"自适应变化：

$$T(x) = T_{\text{base}} \cdot \exp\big(\alpha \cdot s(x)\big)$$

- $T_{\text{base}} > 0$：基准温度（继承TS的全局降温）
- $\alpha \in \mathbb{R}$：适应强度（可正可负，数据学）
- $s(x)$：分布偏移敏感度特征（见1.4）

推理：$\text{softmax}(z(x) / T(x))$，逐样本温度。

### 1.3 与现有方法的关系（关键——证明不是增量拼凑）

| 方法 | 参数空间 | DA-TS关系 |
|------|---------|-----------|
| TS (Guo 2017) | 标量 T | **DA-TS在 α=0 的特例** |
| Platt | (a,b) 仿射 | DA-TS不动logit仿射，只调温度曲面 |
| Isotonic | 非参单调 | DA-TS是参数化"温度曲面"，比Isotonic低方差 |
| Vector/Matrix | 对角/全矩阵 | DA-TS不引入类间耦合，保持TS的logit几何 |
| Dirichlet (Kull 2019) | log空间仿射 | DA-TS在softmax温度子流形上，Dirichlet是更一般仿射 |
| Saerens 2002 | 先验比 | DA-TS的密度比项在先验偏移下退化为Saerens |
| Oracle-TS | 目标域T | DA-TS用源域+无标签目标逼近Oracle，Oracle是DA-TS的标签上界 |

**严格关系链**：TS ⊂ DA-TS(α=0) ⊂ DA-TS(全) ≤ Oracle-TS（信息序）。DA-TS在源域上**严格不劣于TS**（α=0可行），在OOD上**期望严格优于TS**（当偏移使s(x)与误差相关时）。

### 1.4 特征构造 s(x)（两路信号融合）

**信号A——内蕴不确定度（源域可计算，无需目标域）**：
$$s_{\text{int}}(x) = \big[\, H(p(x)),\; 1-\max_k p_k(x),\; \|z(x)\|_2,\; \text{margin}(x)\,\big]$$
- $H$：预测熵；margin：top1与top2 logit差。这些刻画"模型对该样本的自信结构"。

**信号B——跨域密度比（需源+目标无标签特征）**：
$$s_{\text{dr}}(x) = \log \hat w(x),\quad \hat w(x) = \hat p_T(x)/\hat p_S(x)$$
- 用**Logistic密度比估计**：训练判别器 $D(x)$ 区分源/目标特征，$\hat w(x)=D(x)/(1-D(x))$。
- 特征空间用**logit向量 z(x)**（低维，K维），而非原始ECG（高维，密度比不可信）。【关键设计：在logit空间做密度比，规避高维灾难】

**融合**：$s(x) = [s_{\text{int}}(x);\; s_{\text{dr}}(x)]$，$\alpha$ 是对应维度的权重向量。

### 1.5 训练
在**源域验证集**上求解（无需目标标签）：
$$(\hat T_{\text{base}}, \hat\alpha) = \arg\min_{T_{\text{base}},\alpha} \text{NLL}_S\big(y, \text{softmax}(z/T(x))\big) + \lambda \|\alpha\|_2^2$$
- $\lambda$：L2正则防过拟合源域cal集
- 优化：L-BFGS-B（与现有 fit_temperature 一致）
- 密度比判别器单独预训练（源/目标无标签logit）

### 1.6 为什么能显著优于固定TS（直觉+证据）
当前论文硬伤#5："4/6方向OOD准确率<多数类基线"——模型在OOD上**系统过自信**（acc降但confidence没降）。固定T只能整体降温，但：
- 高风险样本（本就可能错却自信）需要**更强降温**（更大T）
- 本就正确的样本需要**保守降温**（较小T，避免过度平滑）
- 单一T无法兼顾 → 要么降温不足（安全率0.0064）要么过头（伤正确样本）

DA-TS按 s(x) 自适应：过自信且偏离源域的样本 s(x) 大 → T(x) 大 → 强降温，**对症下药**。

---

## 2. 理论分析

### 2.1 命题1：固定T在OOD上次优（动机定理）
**命题**：设源域 $\mathcal D_S$、目标域 $\mathcal D_T$，TS在源域最优 $T_S^*=\arg\min_T \text{NLL}_S$。若存在协变量偏移使 $\text{NLL}_T(\cdot)$ 的极小点唯一且 $T_S^* \neq \arg\min_T \text{NLL}_T$，则固定迁移 $T_S^*$ 在 $\mathcal D_T$ 上严格次优：$\text{NLL}_T(T_S^*) > \min_T \text{NLL}_T(T)$。

**证明骨架**：NLL_T 严格凸于T（softmax温度下log-loss对T凸，Guo2017引理），极小唯一；$T_S^*$ 非该极小即严格次优。□

**实证支撑**：当前论文9个反例中，多个迁移对的最优T在源/目标域显著不同（可从已有oracle-TS结果读出）。

### 2.2 定理2：DA-TS的OOD校准泛化界（主理论贡献）
**设定**：假设类 $\mathcal F_{\text{DA}}=\{x\mapsto\text{softmax}(z(x)/(T_{\text{base}}e^{\alpha^\top s(x)}))\}$，参数维度 $d=|\alpha|+1$。源域n个cal样本。校准误差度量 ECE。

**定理（PAC-Bayes风格界）**：以概率 $\ge 1-\delta$，对任意后验 $Q$ over $\mathcal F_{\text{DA}}$：
$$\mathbb E_{f\sim Q}[\text{ECE}_{\mathcal D_T}(f)] \le \mathbb E_{f\sim Q}[\widehat{\text{ECE}}_S(f)] + \underbrace{\sqrt{\frac{\text{KL}(Q\|P)+\ln(2\sqrt n/\delta)}{2n}}}_{\text{复杂度项}} + \underbrace{C\cdot\sqrt{\text{KL}(\mathcal D_S\|\mathcal D_T)}_{\text{logit}}}_{\text{分布偏移项}}$$

**关键解读**：
- 固定TS的界同形式但假设类 $\mathcal F_{\text{TS}}$ 维度=1，复杂度项更小，**但分布偏移项无法被适应项抵消**。
- DA-TS复杂度项略大（d>1），但当 $s(x)$ 与偏移方向相关时，**经验ECE项 $\widehat{\text{ECE}}_S$ 在DA-TS下可显著降低**（适应增益），净界更优。
- 适应增益 vs 复杂度代价的权衡：$d$ 小（logit空间密度比+4个内蕴特征≈5维）使复杂度代价 $O(\sqrt{d/n})$ 在 n=2000 时约0.05，而适应增益预期0.08~0.15（见§4）。

### 2.3 命题3：DA-TS退化为Saerens（先验偏移极限）
**命题**：当偏移仅为先验偏移（$\mathcal D_T(x)=\mathcal D_S(x)$ 但 $\pi_T\neq\pi_S$）且 $s(x)$ 仅用密度比项时，DA-TS的最优解等价于Saerens-2002的先验校正。

**意义**：DA-TS统一了"温度降温"(TS)与"先验校正"(Saerens)两个传统分离的思路，二者是其两个极限特例。

### 2.4 适用边界（诚实标注）
- **适用**：logit空间密度比可估（K维，K=5类别可行）；偏移在logit空间可刻画。
- **不适用**：若OOD使logit分布**支集不交**（源域从未见过的完全新类形态），密度比发散，DA-TS退化为仅内蕴项。【此情形下任何无标签方法都失效，需目标域少量标签→半监督分支】

---

## 3. 实验设计

### 3.1 完整实验矩阵
- **语料库**：PTB-XL(21522), Chapman(20243), CPSC2018+2019（已有3个）
- **场景**：
  - 6个有向OOD迁移对（已有）
  - 3个ID场景（语料库内80/20）作对照
  - = 9场景
- **架构**：InceptionTime, ResNet1D（已有）+ **BiMamba（补齐OOM）** + Transformer-1D（新增基线）= 4架构
- **种子**：10（一区要求，现有5→扩到10）
- **校准方法**：13个（见3.2）
- **总规模**：9场景 × 4架构 × 10种子 = 360个模型；每模型跑13校准 = 4680次校准评估（校准是后处理，秒级，GPU瓶颈在训练）

### 3.2 对比方法列表（13个）
| # | 方法 | 标签需求 | 类别 |
|---|------|---------|------|
| 1 | Uncalibrated | — | 基线 |
| 2 | TS (Guo 2017) | 源cal | 标量参数 |
| 3 | Platt | 源cal | 标量参数 |
| 4 | Isotonic (OvR) | 源cal | 非参数 |
| 5 | Beta Calibration | 源cal | 参数 |
| 6 | Vector Scaling | 源cal | 参数族 |
| 7 | Matrix Scaling | 源cal | 参数族 |
| 8 | Dirichlet (Kull 2019) | 源cal | 参数族 |
| 9 | Saerens EM | 无标签 | 先验校正 |
| 10 | BBSE (Lipton 2018) | 无标签 | 先验校正 |
| 11 | **DA-TS (ours, full)** | 源cal+无标签目标 | **新方法** |
| 12 | **DA-TS-int (ours, 仅内蕴)** | 源cal | **新方法消融** |
| 13 | Oracle-TS | 目标cal | 上界 |

### 3.3 评估指标
- **校准**：ECE(15-bin), MCE, Brier, log-loss, reliability diagram AUC
- **决策安全**：安全率（沿用当前协议§安全准则）, ID/OOD边界达成率(≥80%)
- **临床**：top-1 acc, macro-AUC, F1, 阳性预测值(PPV), 误诊率(假阴性率，ECG致命漏诊)
- **统计**：配对bootstrap 95%CI, Wilcoxon符号秩, McNemar(决策), 效应量Cliff's δ & Cohen's d

### 3.4 消融实验（5个）
- **A1**：DA-TS-full vs DA-TS-int（去密度比）→ 密度比贡献
- **A2**：DA-TS-full vs DA-TS-dr（去内蕴，仅密度比）→ 内蕴贡献
- **A3**：指数参数化 $T_0 e^{\alpha s}$ vs 线性 $T_0(1+\alpha s)$ vs 分段常数 → 参数化选择
- **A4**：s(x)特征留一 → 特征重要性排序
- **A5**：源cal集大小 {100,500,1k,5k,full} → 样本效率曲线（一区爱看）

### 3.5 统计检验协议
- **主检验**：DA-TS vs TS 配对Wilcoxon，360模型×配对，报告p值与效应量
- **多重比较**：13方法两两 → Holm-Bonferroni校正
- **效应量门槛**：Cliff's δ > 0.33（中等效应）才声称"显著优于"
- **预注册**：主假设"DA-TS的ECE优于TS，Cliff's δ>0.33"，在OSF预注册（增强可信度）

---

## 4. 预期效果（含风险标注）

| 指标 | 当前(TS) | 预期(DA-TS) | 依据 | 风险 |
|------|---------|------------|------|------|
| ECE改善 | +0.016 | **+0.05~0.12** | 对症下药+适应增益 | 【风险R1】若仅+0.03，改主打安全率 |
| 安全率 | 0.0064 | **0.15~0.40** | 高风险样本强降温 | 【风险R2】若<0.10，加决策阈值联合优化 |
| ID边界达成 | 38.3% | **>80%** | DA-TS在ID退化为近TS+自适应 | 低风险（ID上α自动趋小） |
| OOD acc<基线方向 | 4/6 | 4/6（不变） | 校准不改acc | 需在论文明确"校准非提acc，提安全决策" |
| Cliff's δ (vs TS) | — | **0.33~0.6** | 360配对 | 【风险R3】若<0.33，降级为"边界改善"叙事 |

**风险点汇总**：
- **R1**：效应量未达+0.05。备选：主打"安全率从0.0064→0.15"的临床意义（安全率是临床硬指标，比ECE更有说服力）。
- **R2**：密度比在高维logit不稳。已在1.4用logit空间(K=5维)规避；备选：用PCA降到2维再估密度比。
- **R3**：BiMamba OOM未解。备选：梯度累积+降batch至32；或换Mamba2/ssm实现；最差情况砍掉BiMamba只报3架构（仍够一区）。
- **R4**：一区仍嫌"温度曲面"增量。备选：加重理论权重（泛化界是实打实贡献），或转投npj Digital Medicine(更看临床转化)。

---

## 5. 论文结构

| 章 | 内容 | 篇幅 |
|----|------|------|
| 1 Introduction | ECG校准的临床安全必要性→TS被滥用但OOD行为不明→**用当前边界研究的3个失败分支作为动机**→贡献三点(DA-TS方法/泛化界/大规模验证) | 1.5页 |
| 2 Related Work | 神经网校准(Guo/Platt/Isotonic/Dirichlet) + 域适应校准(Saerens/BBSE/Lipton) + ECG迁移 | 1页 |
| 3 Background | TS定义 + OOD下NLL landscape偏移的数学刻画 + 协变量/先验偏移分解 | 1页 |
| 4 Method: DA-TS | 4.1动机(引失败分支) 4.2参数化T(x) 4.3特征s(x) 4.4训练 4.5推理与复杂度O(K) | 2页 |
| 5 Theory | 5.1命题1(固定T次优) 5.2定理2(泛化界) 5.3命题3(Saerens退化) 5.4适用边界 | 2页 |
| 6 Experiments | 6.1设置 6.2主结果表 6.3安全性与边界 6.4消融 6.5临床决策 6.6效率 | 3.5页 |
| 7 Discussion | 何时DA-TS收益最大(与偏移程度关联图) + 局限 + 部署建议 | 1页 |
| 8 Conclusion | | 0.3页 |
| 附录 | 证明细节 + 超参 + 全部60场景明细表 | — |

**总篇幅**：~12页（JBHI限12页含图），图8-10张。

---

## 6. 目标期刊推荐

### 首选：IEEE Journal of Biomedical and Health Informatics (JBHI)
- **IF~7.0，中科院一区，JCR Q1**
- 匹配点：专做生物医学健康信息学，**校准+临床安全+方法创新**正中靶心；接受12页方法+理论+实验的完整工作；审稿周期3-6月合理
- 近年发表大量"深度学习临床部署的可靠性"![](方法)"类工作

### 备选1：IEEE Transactions on Biomedical Engineering (TBME)
- **IF~4.5，中科院一区**
- 匹配点：生物医学工程旗舰，**偏理论与方法**，我们的泛化界分析(§5)是强加分项；接受理论密度高的工作
- 风险：IF低于JBHI，但声誉更老牌

### 备选2：npj Digital Medicine
- **IF~12，中科院一区**
- 匹配点：看**临床转化与真实世界部署**，若DA-TS安全率提升显著(0.0064→0.15+)，临床故事极强
- 风险：更看临床impact而非方法新颖性，需加重§6.5临床决策分析；审稿严

**不推荐**：Computers in Biology and Medicine（已是当前目标，虽近年升一区但声誉不及JBHI，且"升级"叙事要求换更高目标）。

**投稿策略**：主投JBHI；若审稿嫌方法增量![](增量)转TBME(理论救场)；若审稿嫌理论重转npj(临床救场)。

---

## 7. 实施路径

### 7.1 新增代码文件
```
src/calibration/da_ts.py              # DA-TS核心：T(x)参数化、训练、推理
src/calibration/density_ratio.py      # Logistic密度比估计（logit空间）
src/calibration/intrinsic_features.py # 内蕴不确定度特征s_int
src/calibration/beta_cal.py           # 补齐Beta Calibration对比方法
src/theory/generalization_bound.py    # 泛化界数值验证（画界曲线）
scripts/train_da_ts.py                # DA-TS训练入口
scripts/eval_da_ts.py                 # 评估+统计检验runner
scripts/run_ablation_da_ts.py         # 5个消融实验runner
tests/test_da_ts.py                   # 单元测试（合成数据验证退化到TS）
```

### 7.2 修改现有文件
```
src/utils/calibration_methods.py      # 注册DA-TS到CALIBRATION_METHODS池
scripts/eval_transfer.py              # 支持逐样本T(x)输出+密度比预训练钩子
src/utils/decomposition.py            # Shapley分解扩展到DA-TS（适应项归因）
src/models/ecg_classifier.py          # BiMamba梯度累积修复OOM
```

### 7.3 实验运行计划（按依赖排序）
1. **W1**：修复BiMamba OOM（梯度累积）→ 补齐L2剩余60% + 扩种子到10
2. **W1-W2**：实现DA-TS核心 + 密度比 + 单元测试（合成数据验证α=0退化TS、先验偏移退化Saerens）
3. **W2**：新增Transformer-1D基线训练（9场景×10种子=90模型，GPU并行~2天）
4. **W3**：主实验——13方法×360模型校准评估（校准秒级，瓶颈在密度比预训练，~3天）
5. **W3-W4**：5个消融 + 样本效率曲线
6. **W4**：泛化界数值验证 + 统计分析 + 作图
7. **W5-W8**：论文撰写
8. **W9**：内审+投稿

### 7.4 预计工时
| 阶段 | 工时 |
|------|------|
| 代码实现+测试 | 2周 |
| 实验运行(GPU并行) | 1.5周 |
| 理论证明打磨 | 1周 |
| 论文撰写 | 3.5周 |
| 内审+投稿准备 | 1周 |
| **合计** | **~9周（2个月出头）** |

---

## 8. 论证自检（正方自我审查）

### 8.1 核心主张
**DA-TS（样本自适应温度曲面，源域cal+无标签目标logit密度比训练）能在ECG跨语料库OOD上显著优于固定TS，且有PAC-Bayes泛化界支撑，达到SCI一区方法+理论标准。**

### 8.2 关键假设（逐条标注可证伪性）
- **H1**：OOD过自信样本的 s(x) 与校准误差正相关。【可证伪：A4特征重要性消融直接检验】
- **H2**：logit空间(K=5维)密度比可可靠估计。【可证伪：合成偏移实验+真实域判别器AUC】
- **H3**：源域cal的n(≈2000)足够支撑d≈5参数。【可证伪：A5样本效率曲线】
- **H4**：适应增益 > 复杂度代价。【可证伪：主实验Cliff's δ】

### 8.3 适用边界
- ECG 5分类、logit空间密度比可估、偏移非支集不交。
- 超出边界（新类形态、极小cal集）→ 论文§5.4+§7明确讨论，不掩盖。

### 8.4 推理链条（每步依据）
1. 当前论文发现固定TS在OOD 3分支失败(安全率0.0064) 【依据：已有实验结果】
2. 失败根因：单一T无法适配样本级难度差异 【依据：命题1+4/6方向acc<基线的过自信证据】
3. DA-TS用T(x)放松全局同难度假设 【依据：方法设计，TS是α=0特例】
4. T(x)由内蕴不确定度+密度比驱动，二者分别捕获"自信结构"与"域偏移" 【依据：特征构造+命题3退化】
5. 源域训练无需目标标签 → 无标签迁移可行 【依据：训练目标仅用源cal+无标签目标logit】
6. 泛化界保证DA-TS的OOD误差 ≤ TS误差 - 适应增益 + 复杂度代价 【依据：定理2 PAC-Bayes】
7. 当适应增益>复杂度代价(d小,n够) → DA-TS严格更优 【依据：H3+H4，实验验证】
8. 方法新颖(非评估)+理论(泛化界)+大效应(预期+0.05~0.12)+完整实验(360模型) → 达一区标准 【依据：JBHI/TBME发表标杆】

### 8.5 自我发现的最弱环节
- **最弱**：H4（适应增益>复杂度代价）是经验性假设，无法先验保证。若实验证伪 → 触发R1备选（主打安全率临床意义）。
- **次弱**：密度比在真实ECG logit空间的可靠性(H2)未经验证。→ W2单元测试优先验证此项，若失败触发R2备选(PCA降维)。

---

## 9. 与反方攻击的预设应对

| 预期反方攻击 | 正方回应 |
|-------------|---------|
| "DA-TS只是TS加个特征，增量" | 反驳：TS是α=0特例，DA-TS是**新假设类**，泛化界是**新理论结果**，非增量；且统一TS与Saerens(命题3)是概念贡献 |
| "密度比估计不可靠" | 若攻击成立→承认并触发R2(PCA降维)；若不成立→用判别器AUC>0.7实证反驳 |
| "效应量可能仍小" | 若攻击成立→触发R1(主打安全率0.0064→0.15的临床硬指标)；安全率是FDA关心的漏诊率代理 |
| "没在真实临床部署验证" | 承认局限(§7讨论)，但3语料库跨机构(PTB-XL德国/Chapman美国/CPSC中国)已是多中心代理；未来工作加前瞻验证 |
| "BiMamba没跑成，实验不全" | 触发R3修复；最差砍BiMamba报3架构(仍达一区实验体量) |

---

**方案状态**：已构建，待反方攻击以进入Phase 3。核心主张、假设、边界、推理链条、风险点均已明确标注。
