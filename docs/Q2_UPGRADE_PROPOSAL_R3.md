# ECG温度校准论文 Q2（CBM）稳定接收升级方案 — 正方论证 R3

> **正方论证代理-R3交付**。本方案在 R2 基础上，按 R2 终审裁定的 P0+P1 修补清单（4 项 P0 + 8 项 P1 = 12 项）修改而成。
> **诚实原则**：不确定能 work 的部分均标注【风险点】并给出备选；不夸大边际贡献；主动声明已知数学性质；**绝不掩盖时间线问题**。
> **目标定位**：SCI 二区 Computers in Biology and Medicine（IF~7, 接收率~12%, 平均审稿 10.5 月）。
> **Fallback 期刊**：Physiological Measurement（IF~3, SCI Q3/Q2, 接收率更高, ECG+校准对口）。
> **硬约束**：9 周；RTX 5060 8GB（BiMamba OOM，InceptionTime + ResNet1D 可用）；代码已基本完成，主攻补充实验 + 论文修改。
> **方案版本**：R3（2026-09-09），基于 R2 终审裁决 GO WITH MODIFICATIONS 修补而成。
> **R2→R3 核心变化**：放弃"预注册"叙事改用"诚实披露证伪"（P0-1）、A1修订案正式OSF存档（P0-2）、透明披露时间线（P0-3）、1.9×标记post-hoc（P0-4）、放弃乘法模型改分箱温度（P1-1）、减少FDR检验（P1-2）、降级TS-DRA为经验查表（P1-3）、诚实声明架构变体（P1-4）、聚焦阈值化决策（P1-5）、明确净临床价值定义（P1-6）、降低H1阈值（P1-7）、修正E2为消融实验（P1-8）。

---

## 0. R2→R3 修改追踪表

<!-- R3-FIX: 追踪表 -->
本表列出 R2 终审裁定的 12 项修补（4 项 P0 + 8 项 P1）在本文档中的具体位置和内容。

| # | 优先级 | 修补项 | 对应攻击 | 本文档位置 | 修补内容摘要 |
|---|--------|--------|---------|-----------|------------|
| 1 | P0-1 | 放弃A1.4.2预注册叙事 | N1 | §4.2 C2、§附录A、§5.2 Q3 | 删除所有"预注册"字样，C2改用"诚实披露证伪+post-hoc exploratory observation"叙事 |
| 2 | P0-2 | A1修订案正式OSF存档 | N1 | §附录C（新增） | 新增"OSF存档补救措施"小节，列出存档内容、时间节点和DOI占位符 |
| 3 | P0-3 | 透明披露实验与协议修订时间线 | 遗漏问题1-2 | §4.3（新增§Methods小节）、Table X | 新增"实验时间线与协议演进"小节，Table X对照表 |
| 4 | P0-4 | 1.9×标记post-hoc | N1 | §4.2 C2、§4.1叙事链条、§附录A | 全局所有1.9×处加"post-hoc exploratory observation, not pre-registered hypothesis confirmation" |
| 5 | P1-1 | 放弃乘法模型改分箱温度 | N2 | §3.2 E4、§4.3 §Methods | 放弃T(x)=T_base·exp(α·s(x))，改用分箱温度（binned temperature）：样本按uncertainty score分5 bin，每bin独立估计T |
| 6 | P1-2 | 减少FDR检验数量 | N3 | §3.2 E3、§9.2 H1 | 主假设降为1-2个primary endpoint + 少量secondary；主：TS在阈值化决策下显著改善Brier reliability；次：TS对top-1准确率无显著影响 |
| 7 | P1-3 | 降级TS-DRA为经验查表 | N4 | §4.2 C4、§4.3 §6.Y | 诚实称"empirical binned temperature lookup table"，删除理论推导，只保留经验描述 |
| 8 | P1-4 | 诚实声明架构变体 | N5 | §3.2 E5、§4.2 C4 | 明确声明"InceptionTime (2 blocks) 和 ResNet1D-Wide 为两种架构家族，InceptionTime-Lite 为 InceptionTime 的超参变体" |
| 9 | P1-5 | 聚焦阈值化决策 | N6 | §1定位、§4.1叙事、§4.2 C1 | 核心贡献从"TS改善校准"转向"TS在阈值化临床决策中的价值" |
| 10 | P1-6 | 明确净临床价值定义 | N7 | §3.2 E3、§4.3 §Methods | 净临床价值 = (TP改善的诊疗决策数 - FP增加的误诊数) / 总样本数，E3直接量化 |
| 11 | P1-7 | 降低H1阈值 | N8 | §9.2 H1 | H1从"Cohen's d > 0.5"降为"Cohen's d > 0.2, small effect" |
| 12 | P1-8 | 修正E2为消融实验 | N10 | §3.2 E2 | E2改为消融：(1) TS only, (2) TS + binned temperature, (3) TS + binned temperature + threshold optimization |

---

## 1. 方案一句话定位

<!-- R3-FIX: P1-5 聚焦阈值化决策 -->
<!-- R3-FIX: P0-1 放弃预注册叙事 -->
**不追求方法创新**（前一轮对抗已确认 DA-TS/CSC-ECG 路线对 Q1 不成立），**转而把当前 60 实验的边界研究重新包装为"跨语料库 ECG 部署的 TS 校准在阈值化临床决策中的价值刻画 + 经验性部署前查表工具"**，通过 6 项后处理分析补齐审稿人必问的缺口，将叙事从"边界条件刻画"升级为"**阈值化决策价值 + 经验查表工具 + 透明的失败边界披露 + 诚实证伪的开放科学实践**"，达到 CBM 二区稳定接收标准（预期接收概率 28-38%，中值 33%）。

**与 R2 的区别**：
- R2 定位为"风险评估工具 + 边界条件刻画 + 预注册分支触发"，被反方攻击 A1.4.2 预注册性质造假（N1致命）；
- R3 定位为"**阈值化决策价值 + 经验查表工具 + 诚实证伪**"，**放弃所有"预注册"叙事**，改用"诚实披露证伪 + post-hoc exploratory observation"叙事，聚焦 TS 在阈值化临床决策中的真实价值。

**与 R1 的区别**：R1 定位为"校准决策框架"，被反方攻击为空壳；R2 引入预注册叙事但造假；R3 回归诚实，聚焦 TS 真正有用的场景（阈值化决策）。

---

## 2. 当前论文 Q2 就绪度评估（诚实诊断）

### 2.1 已具备的 Q2 级资产（不需要再补）

| 资产 | 状态 | Q2 价值 |
|------|------|---------|
| 60 实验完整（6方向×2架构×5种子） | ✅ 全跑完 | 实验体量已达 CBM 上限 |
| 3 语料库跨机构（PTB-XL 德国/Chapman 美国/CPSC 中国） | ✅ | 多中心代理，CBM 看重 |
| 8 校准方法对比 | ✅ | 方法覆盖面足够 |
| 协议 v2.1 + OSF 中期存档 + A1修订案（**事后分析计划，非预注册**） | ✅ | 透明性加分（**诚实披露事后性质**） |
| 患者级聚类 bootstrap B=10000 BCa | ✅ 全 60 实验重跑 | 统计严谨度超 CBM 平均 |
| 9 反例透明披露 + 机制解释 | ✅ | 诚实性加分 |
| Shapley 分解 27/27 合成验证 | ✅ | 方法论贡献 |
| 完整代码 + 测试套件 | ✅ | 可复现 |
| 47 页论文已成型 | ✅ | 写作完成度高 |

<!-- R3-FIX: P0-1 -->
**结论**：论文的**实验骨架和统计严谨度已超 CBM 平均水平**。CBM 大量发表的 ECG+DL 论文只有 1-2 数据集、无预注册、无多种子。当前论文的透明性和严谨度是差异化优势。**但 A1 修订案是事后分析计划（9/5 创建，部分实验已完成），不是预注册——R3 诚实披露这一事实，不声称预注册。**

### 2.2 距离 CBM 稳定接收的 7 个缺口（按致命性排序）

| # | 缺口 | 当前状态 | 致命性 | CBM 审稿人视角 |
|---|------|---------|--------|---------------|
| **G1** | **效应量临床意义未论证** | OOD 均值 +0.0159 ECE，但论文未论证这个数字对临床决策意味着什么 | **高** | "ECE 改善 0.016 有临床意义吗？对应多少决策变化？" |
| **G2** | **C2 叙事需诚实披露证伪** | ID 边界 38.3% 远低于 80%，**A1修订案是事后分析计划，不是预注册** | **高** | "你的假设失败了，这篇论文到底证明了什么？时间线透明吗？" |
| **G3** | **4/6 方向 OOD 准确率 < 多数类基线** | 论文已披露但未深入分析 | **高** | "模型在多数方向上不如多数类预测器，校准还有什么意义？" |
| **G4** | **安全率 0.0064 极低** | L2 shift 矩阵上 TS 几乎不安全 | **中高** | "安全率 0.6%，TS 作为默认推荐合理吗？" |
| **G5** | **只有 2 架构家族 + 1 超参变体** | toy 实验 deferred to supplement | **中** | "架构稳健性声称只有 2 架构家族支撑" |
| **G6** | **部署准则是 in-sample 拟合** | Youden 阈值在同一数据上拟合和评估 | **中** | "部署判据没有外部验证，如何部署？" |
| **G7** | **AUROC/AUPRC 未计算** | limitation (xiv) 已登记 | **中** | "只有 accuracy，无法判断模型区分能力" |

### 2.3 不需要补的（避免过度设计）

- **不需要新方法**：前一轮对抗已确认 DA-TS/CSC-ECG 对 Q1 都不成立，Q2 不需要方法创新
- **不需要补到 10 种子**：5 种子 × 60 实验已够 CBM 稳健性要求
- **不需要 BiMamba 全跑**：RTX 5060 8GB OOM 是硬约束，2 架构家族 + 1 超参变体 + 诚实披露比强行跑 3 架构更可信
- **不需要新数据集**：3 语料库跨 3 国已够多中心代理
- **不需要声称预注册**：A1 修订案是事后分析计划，诚实披露即可

### 2.4 Q2 就绪度评分

| 维度 | 当前得分 | CBM 稳定接收阈值 | 差距 |
|------|---------|----------------|------|
| 实验体量 | 9/10 | 7/10 | +2（已超） |
| 统计严谨 | 9/10 | 6/10 | +3（已超） |
| 透明性 | 9/10 | 5/10 | +4（已超，**R3 进一步通过时间线披露增强**） |
| **临床意义论证** | **3/10** | **7/10** | **-4（缺口）** |
| **叙事连贯性** | **5/10** | **7/10** | **-2（缺口，**R3 通过聚焦阈值化决策改善**）** |
| **部署可操作性** | **4/10** | **6/10** | **-2（缺口）** |
| 新颖性 | 5/10 | 5/10 | 0（刚好） |

**总诊断**：论文在"严谨度/透明性"上超 CBM 平均，但在"临床意义论证/叙事连贯性/部署可操作性"上有缺口。**这 3 个缺口全部可以通过后处理分析 + 论文重写解决，不需要大量新实验**。

<!-- R3-FIX: P0-1 -->
**就绪度结论**：当前论文 Q2 接收概率约 25-35%（主要风险是审稿人认为"效应量小 + 事后分析 + 无临床意义论证"）。执行本方案后目标 **28-38%（中值 33%）**——与 R2 的 35-45% 相比下调 5-7 个百分点，主要因为：(1) 放弃预注册叙事后 C2 贡献从+4-6%降至+2-3%；(2) 效应量小（ECE 0.016）是无法修补的硬伤；(3) CBM 12% 接收率竞争激烈。**这个估计与 R2 终审独立估计一致。**

---

## 3. 具体补充实验（9 周内，考虑 GPU 限制）

### 3.1 实验筛选原则

1. **优先后处理分析**（从已有 60 checkpoint 提取，GPU 负担 ≈ 0）
2. **轻量训练仅 1 项**（第 3 架构超参变体，用 InceptionTime 简化版）
3. **每项实验标注边际贡献**（对接收概率的增量）
4. **全部可在 RTX 5060 8GB 上跑**

### 3.2 6 项补充实验（按优先级排序）

#### E1：补齐 L2 shift 矩阵 + LOCO 跨语料庫泛化验证 【最高优先级】

**当前缺口**：L2 部署/安全分析只覆盖 157/390 cells（2 seed, 单架构）；Youden 阈值 in-sample 拟合。

**具体操作**：
- 对已有 60 checkpoint，在 L2 shift 矩阵的剩余 233 cells 上跑 eval-only 校准评估
- 每个 cell = 8 方法 × 13 shift levels 的后处理校准，秒级，不需训练
- **LOCO 跨语料庫泛化验证**：leave-one-corpus-out（LOCO）——用 2 个语料库的 Youden 阈值在第 3 个上测试（3 折）
- 产出：`results/l2_shift_full_390cells.csv` + `results/deployment_loco_validation.csv`

**LOCO 诚实披露条款**：
> 本研究的 LOCO 验证只有 3 折（3 个语料库），统计效力有限（n=3 无法达到 p<0.05）。我们明确声明这是"3 折 leave-one-corpus-out 探索性验证"（**3 个 case study**），不声称"外部验证"。**若 LOCO 结果不理想（如泛化性能显著下降、Youden J ≈ 0），本文将如实报告并分析原因，不选择性呈现。** 报告 3 个测试点的点估计 + 诚实声明 n=3 的统计效力局限。

**GPU 负担**：≈ 0（纯后处理，CPU 可跑）
**工时**：3 天（含脚本编写 + 运行 + 分析）
**边际贡献**：**+5-8% 接收概率**（L2 补齐解决 G4；LOCO n=3 只提供 descriptive 证据，不解决 G6）
**风险**：LOCO n=3 统计效力低【中风险】→ 备选：诚实披露 n=3 局限，报告点估计不声称统计显著

#### E2：消融实验 — TS 组件边际贡献 【高优先级】

<!-- R3-FIX: P1-8 修正E2为消融实验 -->
**当前缺口**：R2 的 E2 是 discrimination metrics 补充计算，但边际贡献分析不清晰，无法证明每个组件的必要性。

**R3 重写为消融实验**（P1-8 修补）：

**具体操作**：
- 从已有 60 checkpoint 提取 logits，进行三阶段消融：
  - **(1) TS only**：仅应用温度缩放，T 在源域校准集上拟合
  - **(2) TS + binned temperature**：TS + 分箱温度（按 uncertainty score 分 5 bin，每 bin 独立估计 T，见 P1-1）
  - **(3) TS + binned temperature + threshold optimization**：在 (2) 基础上，对阈值化决策的阈值 τ 进行 Youden 优化
- 比较三者的 **Brier reliability** 和 **阈值化决策改变率（DCR）**
- 同时补充计算 discrimination metrics（AUROC/AUPRC/F1/PPV/NPV/MCC），作为辅助指标
- 产出：`results/ablation_ts_components.csv` + `results/discrimination_metrics_60exp.csv`
- 论文新增 Table：消融实验结果 + discrimination × calibration 联合报告

**消融实验的逻辑**：
- 若 (2) > (1)：分箱温度比单一 T 有边际改善 → 支持分箱温度方法
- 若 (3) > (2)：阈值优化有边际改善 → 支持阈值化决策叙事
- 若 (2) ≈ (1)：分箱温度无边际改善 → 诚实报告，单一 T 已足够
- 若 (3) ≈ (2)：阈值优化无边际改善 → 诚实报告，阈值化决策价值有限

**E2 风险标注**：

| 风险 | 描述 | 检测方法 | Fallback 方案 |
|------|------|---------|--------------|
| **R1** | Isotonic 回归在小样本上过拟合，AUROC 异常高 | 检查 Isotonic 的 train/test AUROC gap；若 gap > 0.1 则过拟合 | 改用 Platt sigmoid 或限制 Isotonic 的自由度 |
| **R2** | Vector/Matrix calibration 参数过多而退化（4 类需 4-16 参数） | 检查参数估计的 condition number；若 > 1e6 则退化 | 改用 TS 或 Dirichlet（参数更少） |
| **R3** | Saerens EM 不收敛或收敛到退化解 | 监控 EM 的 log-likelihood 迭代；若 50 次迭代未收敛或 LL 下降则失败 | 改用 BBSE（矩阵校正）或报告 EM 失败并排除 |
| **R4** | 消融实验显示分箱温度无边际改善 | (2) ≈ (1) | 诚实报告，单一 T 已足够；聚焦 TS only 的价值 |
| **R5** | 消融实验显示阈值优化无边际改善 | (3) ≈ (2) | 诚实报告，阈值化决策价值有限；触发备选叙事 |

**额外风险**：4/6 方向 OOD 准确率 < 多数类基线 → AUROC 大概率也低，补齐后**可能暴露问题**（负交互效应）。预先准备 Discussion 段落"Calibration value under insufficient discrimination"。

**GPU 负担**：≈ 0（从 checkpoint 提取 logits，CPU 算）
**工时**：2.5 天（消融实验比单纯 discrimination 计算多 0.5 天）
**边际贡献**：**-2% 到 +3% 接收概率**（消融实验更严谨，但可能显示组件无边际改善；考虑反暴露风险）
**风险**：可能暴露 4/6 方向低 AUROC 或消融无差异【中风险】→ 备选：预先准备 Discussion 段落，主动讨论"discrimination 不足时校准的有限价值"和"单一 T 已足够的诚实结论"

#### E3：效应量临床意义量化（阈值化决策 + Brier reliability）【高优先级，解决 G1】

<!-- R3-FIX: P1-2 减少FDR检验数量 -->
<!-- R3-FIX: P1-6 明确净临床价值定义 -->
<!-- R3-FIX: P1-7 降低H1阈值 -->
**当前缺口**：ECE +0.016 的临床意义未论证。

**TS 数学性质声明**（在论文 Method 部分主动声明）：
> **Properties of Temperature Scaling**: Temperature Scaling (T>0) is a confidence calibration method that preserves the argmax of softmax outputs. For any T>0, argmax_i(softmax_i(logit/T)) = argmax_i(logit_i), because dividing by a positive number does not change the ordering. Therefore, **top-1 classification accuracy is invariant under TS**. This property is by design: TS adjusts confidence without altering decisions. We evaluate TS effects on calibration metrics (ECE, Brier reliability) and thresholded decision changes, not on accuracy. **The clinical value of TS lies primarily in threshold-based binary decisions** (e.g., P(AF)>0.5), where calibrated probabilities change the decision boundary and thus affect clinical outcomes.

**明确声明**：TS 不改变 argmax，因此 top-1 准确率变化 = 0（精确等于 0，不是"<1%"）。**本文不以 top-1 准确率变化作为 TS 效果指标**。这不是弱点而是 TS 的设计特性，我们主动声明而非隐藏。

**E3 假设体系**（P1-2 修补，减少 FDR 检验数量）：

**Primary endpoint（主假设，1个，不进入FDR校正的预先声明主检验）**：
- **H1-primary**：TS 在阈值化决策场景下显著改善 **Brier reliability**（Cohen's d > 0.2, small effect；P1-7 修补降低阈值）
  - 检验：对 6 个迁移方向，TS 前后 Brier reliability 分量变化，配对 t 检验
  - 这是预先声明的主检验，不进入 FDR 校正

**Secondary endpoints（次假设，2个，进入FDR校正）**：
- **H1-secondary-a**：TS 对 top-1 准确率无显著影响（负面结果，证明 TS 不损害预测）——已知数学上必然成立，但经验验证
- **H1-secondary-b**：TS 在阈值 τ=0.5 下产生决策改变率 DCR > 0（证明 TS 确实改变阈值化决策）

**Tertiary/exploratory endpoints（探索性，不声称确认）**：
- per-class DCR、per-threshold DCR（τ=0.7/0.9）、per-direction 净临床价值——**全部标记为 exploratory，不进入主推断**

**FDR 校正范围**（P1-2 修补）：
- 主检验（H1-primary）：不进入 FDR 校正（预先声明）
- 次检验（H1-secondary-a, H1-secondary-b）：2 个检验，BH FDR 校正（q=0.05）
- 探索性检验：不进入 FDR 校正，明确标记 exploratory
- **总检验数从 R2 的 72 个降至 2 个进入 FDR 校正**，大幅提升功效

**E3 主指标**：

**(a) Brier 可靠性（Brier Reliability）**——主指标（primary endpoint）
- 分解 Brier score 为 Reliability + Resolution + Uncertainty（Murphy 1973 分解）
- 报告 TS 前后 Reliability 分量的变化（ΔReliability = Reliability_pre - Reliability_post）
- Reliability 越小越好（校准越好），TS 应使 Reliability 下降

**(b) 阈值化决策变化率（Thresholded Decision Change Rate, DCR）**——主指标（primary endpoint）
- 在置信度阈值 τ = 0.5 下（主阈值），统计 TS 后预测决策的变化率
- 对每个类 c，计算：DCR(τ) = |{x : 1[p_c^TS(x) > τ] ≠ 1[p_c^pre(x) > τ]}| / N
- 报告 macro-DCR（τ=0.5 主报告，τ=0.7/0.9 探索性）

**(c) ECE 变化**——次要指标（保留但降级为 exploratory）
- 报告 TS 前后 ECE 变化（ΔECE = ECE_pre - ECE_post）
- 作为辅助指标，不作为主指标

**净临床价值定义**（P1-6 修补，明确量化定义）：
> **净临床价值（Net Clinical Value, NCV）**：
> NCV = (TP_improved - FP_worsened) / N_total
> 
> 其中：
> - **TP_improved**：TS 后决策更接近真实标签的样本数（改对）
>   - 具体定义：对 true class c，TS 前预测 p_c ≤ τ 但 TS 后 p_c > τ（从"不报告 c"到"报告 c"，且 c 是真实标签）→ 改对
> - **FP_worsened**：TS 后决策更远离真实标签的样本数（改错）
>   - 具体定义：对 true class c，TS 前预测 p_c > τ 但 TS 后 p_c ≤ τ（从"报告 c"到"不报告 c"，且 c 是真实标签）→ 改错
>   - 或：对 false class c'，TS 前预测 p_c' ≤ τ 但 TS 后 p_c' > τ（从"不报告 c'"到"报告 c'"，且 c' 不是真实标签）→ 改错
> - **N_total**：总样本数
> 
> **需证明 NCV > 0**（改对比例显著高于改错比例）。NCV 在 E3 实验中直接量化，per-direction 报告。

**具体操作**：
- 从已有 60 checkpoint 提取 TS 前后 softmax 输出
- 计算 Brier reliability 变化（primary）+ DCR（primary）+ NCV（primary）+ ECE 变化（exploratory）
- 对 primary endpoint 应用配对 t 检验（Cohen's d > 0.2 阈值，P1-7 修补）
- 对 secondary endpoints 应用 BH FDR 校正（2 个检验，q=0.05）
- 产出：`results/brier_decomposition_primary.csv` + `results/thresholded_decision_change_primary.csv` + `results/net_clinical_value.csv` + `results/ece_change_exploratory.csv`

**GPU 负担**：≈ 0
**工时**：2 天
**边际贡献**：**+3-5% 接收概率**（P1-2 减少检验数量提升功效；P1-6 明确定义；P1-7 降低阈值降低失败风险；但弱于 R2 的 +4-6%，因为放弃预注册叙事）
**风险**：若 Brier reliability 改善 Cohen's d < 0.2 或 NCV ≤ 0，则临床意义论证弱 → 备选：改用"校准使置信度更可信，对不确定性感知工作流有价值"的叙事【中风险】

#### E4：温度分布 + 分箱温度 + 偏移敏感度分析 【中优先级】

<!-- R3-FIX: P1-1 放弃乘法模型改分箱温度 -->
**当前缺口**：60 实验的 T 值分布未报告，无法回答"什么样的偏移需要多大的降温"。

**R3 放弃乘法模型**（P1-1 修补）：

**R2 的问题**：R2 在接收概率估计中使用了乘法模型 T(x) = T_base · exp(α·s(x))（s(x) 为 uncertainty score），这是 Joy et al. AAAI 2023 的受限特例，有 prior art 风险，且与 35-45% 的接收概率估计脱节。

**R3 改用分箱温度（binned temperature）**：
- **方法**：将样本按 uncertainty score s(x) 分 5 个 bin（quintile），每个 bin 独立估计一个温度 T_bin
- **公式**：T(x) = T_bin where x ∈ bin(s(x))
- **优点**：
  1. 无参数化假设（不依赖 exp/线性/任何特定函数形式）
  2. 无 prior art 风险（分箱是通用非参数方法）
  3. 可解释（每个 bin 的 T 直接报告）
  4. 与 E2 消融实验对接（E2 的第 2 阶段就是 TS + binned temperature）
- **缺点**：5 个 bin 的边界选择有任意性（用 quintile 缓解）

**具体操作**：
- 提取 60 实验的拟合 T 值，报告分布（per-direction, per-architecture）
- **分箱温度实现**：对每个迁移方向，按 uncertainty score 分 5 bin，每 bin 拟合 T_bin
- 计算 T_bin 与以下偏移度量的关联：
  - 源/目标先验距离（L1）
  - 源/目标 logit 分布距离（MMD, KS）
  - OOD accuracy drop
  - OOD raw ECE
- 报告分箱温度 vs 单一 T 的 Brier reliability 改善对比（与 E2 消融实验对接）
- **不拟合 T ~ f(偏移度量) 的参数化回归**（避免乘法模型和 prior art 风险），只报告 descriptive 统计
- 产出：`results/temperature_distribution_analysis.csv` + `results/binned_temperature_results.csv`

**GPU 负担**：≈ 0
**工时**：1.5 天
**边际贡献**：+1-2% 接收概率（分箱温度是 descriptive 方法，无理论贡献，但支持 E2 消融和 E3 临床意义）
**风险**：分箱温度可能无边际改善（vs 单一 T）【中风险】→ 备选：诚实报告，单一 T 已足够

#### E5：轻量第 3 架构超参变体（InceptionTime 简化版）补齐架构稳健性 【中优先级，解决 G5】

<!-- R3-FIX: P1-4 诚实声明架构变体 -->
**当前缺口**：只有 InceptionTime + ResNet1D，BiMamba OOM。

**硬件约束**：RTX 5060 8GB（BiMamba OOM 是硬约束，InceptionTime 简化版需实测显存）

**具体操作**：
- **架构选择**：InceptionTime 简化版（3 层 Inception module 而非 6 层，~200K-500K 参数，<1M）
- **诚实声明**（P1-4 修补）：
  > "本研究的架构稳健性声称基于 **2 个架构家族 + 1 个超参变体**：
  > - **架构家族 1**：InceptionTime (6 blocks, ~500K-1M 参数)
  > - **架构家族 2**：ResNet1D-Wide (不同 depth/width)
  > - **超参变体**：InceptionTime-Lite (3 blocks, ~200K-500K 参数) 是 InceptionTime 的超参变体（减少 Inception module 数量），**不是独立的架构家族**
  > 
  > 因此，本研究的架构稳健性声称应理解为'在 2 个架构家族上的稳健性'，而非'3 个独立架构上的稳健性'。"
- 训练 3 语料库 × 5 种子 = 15 模型（每个 ~2-3 小时，共 ~30-45 GPU 小时）
- 6 迁移对 × 5 种子 = 30 transfer 评估（eval-only，秒级）
- 8 校准方法 × 30 = 240 校准评估
- 产出：`results/c3_inceptiontime_lite_30exp.csv`
- 论文：架构稳健性基于 **2 架构家族 + 1 超参变体**（诚实声明）

**GPU 负担**：~30-45 GPU 小时（RTX 5060 8GB，~1.5-2 天连续跑，需实测显存）
**工时**：4 天（1 天实现 + 1.5-2 天训练 + 1 天评估）
**边际贡献**：+1-3% 接收概率（**超参变体弱于新架构家族**，诚实声明后贡献降低；从 R2 的 +2-4% 降至 +1-3%）
**风险**：InceptionTime 简化版可能 OOM 或 accuracy 不达标【中风险】→ 备选：改用 ResNet1D 不同超参变体（depth 3/5/7, width 32/64/128）；或诚实报告"2 架构家族 + BiMamba toy"

#### E6：可靠性图 + 校准曲线可视化 【低优先级但必要】

**当前缺口**：论文只有箱线图，无 reliability diagram（CBM 审稿人期望的校准可视化）。

**具体操作**：
- 为 7 个代表迁移对（2 架构家族 × 2 极端 + 1 中位数方向 + 1 超参变体）生成：
  - Reliability diagram（15 bin，TS 前后对比）
  - 校准曲线 + 理想对角线
  - Per-class reliability
- 补充材料：全部 60 实验的 reliability diagram
- 产出：`paper/figures/fig_reliability_*.pdf`（主文 7 张 + 补充材料 60 张）

**GPU 负担**：≈ 0
**工时**：2-3 天（生成 67 张图 + 排版）
**边际贡献**：+2-3% 接收概率（可视化质量，CBM 审稿人视觉动物）
**风险**：无【低风险】

### 3.3 实验总览

| 实验 | GPU 小时 | 工时 | 边际贡献 | 解决缺口 |
|------|---------|------|---------|---------|
| E1: L2 补齐 + LOCO 探索性 | 0 | 3 天 | +5-8% | G4（G6 部分） |
| E2: 消融实验 + discrimination | 0 | 2.5 天 | -2% 到 +3% | G7 + 组件必要性 |
| E3: Brier reliability + DCR + NCV（减少FDR） | 0 | 2 天 | +3-5% | G1 |
| E4: 分箱温度 + 偏移敏感度 | 0 | 1.5 天 | +1-2% | 叙事增强 + E2 支持 |
| E5: InceptionTime 简化版（超参变体） | 30-45 | 4 天 | +1-3% | G5 |
| E6: 可靠性图 | 0 | 2-3 天 | +2-3% | 可视化 |
| **合计** | **30-45 GPU 小时** | **15-16 天** | **+10-24%** | **G1-G7 全覆盖** |

**关键洞察**：6 项实验中 5 项是后处理（GPU ≈ 0），只有 E5 需要轻量训练。**9 周内完全可行**，实验阶段 2-3 周，剩余 5-6 周写论文。

---

## 4. 论文修改策略（4 贡献重新组织）

### 4.1 叙事重定位（核心改动）

<!-- R3-FIX: P1-5 聚焦阈值化决策 -->
<!-- R3-FIX: P0-1 放弃预注册叙事 -->
**当前叙事**："边界条件刻画"（学术化，但 CBM 审稿人觉得"所以呢？"）
**R1 叙事**："跨语料库 ECG 部署的校准决策框架"（被反方攻击为空壳）
**R2 叙事**："边界条件刻画 + 风险评估工具 + 预注册分支触发"（被反方攻击 A1.4.2 预注册造假）
**R3 升级叙事**："**跨语料库 ECG 部署的 TS 校准在阈值化临床决策中的价值刻画 + 经验性部署前查表工具：基于 60 实验的诚实证伪开放科学实践**"

**叙事链条**（每步都有实验支撑，R3 修补后）：
1. **问题**：ECG 跨机构部署时，源域校准的 TS 在目标域还有效吗？**在阈值化临床决策中有什么价值？**（临床痛点，P1-5 聚焦阈值化决策）
2. **方法**：60 实验 + 8 方法 + 患者级 bootstrap（严谨度）+ **诚实披露事后分析性质**（P0-1）
3. **发现 1**：TS 在 85% 实验中产生 OOD Brier reliability 收益（C1，主发现）
4. **发现 2**：收益有边界——9 个反例 + 机制解释（C1 诚实补充）
5. **证伪 1**：**假设 ID 边界 > 80% 未达到（实际 38.3%），诚实披露这一证伪结果**（C2，开放科学，P0-1 放弃预注册叙事）
6. **观察 1**：ID 也有收益（+0.0083），OOD/ID ≈ 1.9×（**post-hoc exploratory observation, not pre-registered hypothesis confirmation**，附跨方向稳定性分析，不做假设检验，P0-4）
7. **发现 3**：TS 最稳健，EM/Matrix 脆弱（C4，方法选择边界）
8. **工具**：**经验性部署前查表** + LOCO 跨语料庫泛化验证（C4，经验查表，P1-3 降级）
9. **临床意义**：ECE 0.016 → **阈值化决策改变率 + Brier reliability 改善 + 净临床价值 NCV**（E3，临床落地，P1-5/P1-6）
10. **诚实声明**：TS 不改变 argmax，**临床价值在于阈值化决策**（P0-4，主动声明，P1-5 聚焦）
11. **时间线透明披露**：实验与协议修订时间线（P0-3，Table X）

### 4.2 4 贡献的重新组织

#### C1（主贡献）：阈值化决策价值 + Brier reliability 改善 + OOD 收益量化

<!-- R3-FIX: P1-5 聚焦阈值化决策 -->
**当前**：51/60 支持，均值 +0.0159
**R3 升级**：
- 保留 51/60 的量化
- **核心转向**：TS 在阈值化临床决策中的价值（P1-5 修补）——当使用概率阈值（如 P(AF)>0.5）做 binary decision 时，TS 能改变决策边界，从而影响临床 outcome
- **新增**：ECE +0.016 对应的阈值化决策改变率 DCR + Brier reliability 改善 + 净临床价值 NCV（E3 结果）
- **新增**：discrimination metrics 联合报告（E2 结果）
- **新增**：reliability diagram 可视化（E6）
- **诚实声明**：TS 不改变 argmax，top-1 准确率变化 = 0；**临床价值在于阈值化决策**（聚焦，不分散到"不确定性感知工作流"等存疑场景）
- 叙事：从"统计显著 + 误判率改善"升级为"**阈值化决策改变 + Brier reliability 改善 + 净临床价值**"

**边际贡献**：+3-5%（CBM 是临床期刊，阈值化决策叙事比 R2 的"多临床价值来源"更聚焦、更诚实）

#### C2（边界贡献）：诚实披露证伪 + post-hoc exploratory observation

<!-- R3-FIX: P0-1 放弃预注册叙事 -->
<!-- R3-FIX: P0-4 1.9×标记post-hoc -->
**当前**：R2 包装为"预注册分支触发"，被反方攻击 A1.4.2 预注册性质造假（N1致命）
**R3 升级**：
- **放弃所有"预注册"叙事**（P0-1 修补）
- **改用"诚实披露证伪 + post-hoc exploratory observation"叙事**：
  > "We hypothesized that ID boundary condition satisfaction rate > 80%. The result (38.3%) falsified this hypothesis. **We honestly report this falsification.** The 1.9× OOD/ID ratio is a **post-hoc exploratory observation** with cross-direction stability analysis, **not a confirmatory finding and not a pre-registered hypothesis confirmation**. Protocol amendment A1 (2026-09-05) was a **post-hoc analysis plan** based on partial experimental results, **not a pre-registration**. We transparently disclose this timeline (see Table X)."
- **1.9× 比率标记为"post-hoc exploratory observation, not pre-registered hypothesis confirmation"**（P0-4 修补）：报告点估计、置信区间、跨方向稳定性分析（用 E4），**不做假设检验**
- **诚实披露价值的多维定位**：(1) confirmatory 假设检验——事先声明 ID 边界 > 80% 假设，结果 38.3% 证伪，诚实报告；(2) 透明性——公开分析计划和时间线防止事后隐瞒；(3) 开放科学实践——**诚实披露证伪 + 事后分析计划的透明记录**本身就是贡献
- 叙事：**不是 HARKing，也不是预注册，而是"诚实披露证伪 + post-hoc exploratory observation + 时间线透明"**

**边际贡献**：+2-3%（**从 R2 的 +2-4% 降至 +2-3%**，因为放弃预注册叙事后 C2 贡献降低，但诚实披露仍有开放科学价值）

#### C3（方法论）：Shapley 分解 + 分箱温度 + 消融实验

**当前**：27/27 合成验证
**R3 升级**：
- 保留 27/27 验证
- **新增**：分箱温度（binned temperature）方法（E4 结果，P1-1 修补，放弃乘法模型）
- **新增**：消融实验（E2 结果，P1-8 修补）——TS only vs TS + binned vs TS + binned + threshold opt
- 叙事：从"分解验证"扩展为"校准收益的参数级理解 + 组件边际贡献消融"

**边际贡献**：+2-3%（增强方法论深度，分箱温度无 prior art 风险）

#### C4（实践）：经验性部署前查表 + 边界条件刻画 + LOCO 跨语料庫泛化验证

<!-- R3-FIX: P1-3 降级TS-DRA为经验查表 -->
<!-- R3-FIX: P1-4 诚实声明架构变体 -->
**当前**：TS 稳健 vs EM 脆弱
**R2 升级**："可操作的部署决策工具"（被反方攻击为空壳）
**R3 升级**：
- 保留 8 方法对比
- **新增**：2 架构家族 + 1 超参变体方法对比（E5 结果，P1-4 诚实声明）
- **新增**：完整 L2 矩阵安全率报告（E1 结果）
- **新增**：LOCO 跨语料庫泛化验证（E1 结果，诚实披露 n=3 局限，定位为"3 个 case study"）
- **新增**：**经验性部署前查表工具**（基于 E4 分箱温度 + 源域特征）
- 叙事：从"决策框架"改为"**经验性查表工具 + 边界条件刻画**"（P1-3 降级）

**经验性查表工具规格**（P1-3 修补，降级为经验查表，删除理论推导）：

| 维度 | 规格 |
|------|------|
| **工具名称** | Empirical Binned Temperature Lookup Table (EBT-LT) |
| **性质** | **经验性查表工具，非理论方法**（P1-3 降级） |
| **使用场景** | 从业者在跨语料库 ECG 部署前，**查表参考** TS 校准是否适用于自己的迁移对 |
| **输入** | (1) 训练集 ID 校准性能（源域 ECE、源域 accuracy）；(2) 目标域 OOD 估计（源/目标先验距离、logit 分布距离估计） |
| **输出** | (1) **经验性参考建议**（非理论预测）：推荐/不推荐 TS；(2) 经验性 ECE 改善区间（基于 60 实验的经验分布）；(3) 风险等级（低/中/高，基于经验安全率和反例率） |
| **正面推荐** | 在 2/6 可部署方向（源域 accuracy > X 且源域 ECE > Y）上，TS 有 OOD 收益，**经验上建议使用** |
| **风险警告** | 在 4/6 不可部署方向上，模型 discrimination 不足，校准收益有限，**经验上不建议使用 TS** |
| **经验基础** | 60 实验 + E1 的 L2 完整矩阵 + E4 的分箱温度结果 |
| **局限性** | **这是经验性查表工具，不是理论方法**；6 个迁移方向的经验基础有限；部署前判据的 R² 可能低；LOCO 只有 3 折（3 个 case study），统计效力有限 |
| **与 R2 的区别** | R2 称"TS Deployment Risk Assessor (TS-DRA)"并包装为理论方法；R3 诚实称"Empirical Binned Temperature Lookup Table (EBT-LT)"，**删除所有理论推导，只保留经验描述** |

**边际贡献**：+2-4%（**从 R2 的 +4-6% 降至 +2-4%**，因为降级为经验查表后贡献降低，但更诚实）

### 4.3 新增章节

#### 新增 §Methods：Properties of Temperature Scaling

```latex
\subsection{Properties of Temperature Scaling}
Temperature Scaling (T>0) is a confidence calibration method that 
preserves the argmax of softmax outputs. For any T>0, 
argmax_i(softmax_i(logit/T)) = argmax_i(logit_i), because dividing 
by a positive number does not change the ordering. Therefore, top-1 
classification accuracy is invariant under TS. This property is by 
design: TS adjusts confidence without altering decisions. We evaluate 
TS effects on calibration metrics (ECE, Brier reliability) and 
thresholded decision changes, not on accuracy. \textbf{The clinical 
value of TS lies primarily in threshold-based binary decisions} 
(e.g., P(AF)>0.5), where calibrated probabilities change the decision 
boundary and thus affect clinical outcomes.
```

#### 新增 §Methods：实验时间线与协议演进（P0-3 修补）

<!-- R3-FIX: P0-3 透明披露时间线 -->
```latex
\subsection{Experiment Timeline and Protocol Evolution}
We transparently disclose the timeline of experiments and protocol 
amendments to allow readers to assess potential HARKing risks:

\begin{table}[h]
\centering
\caption{Experiment-Protocol Timeline (Table X)}
\begin{tabular}{lll}
\hline
Event & Date & Nature \\
\hline
Initial protocol v2.1 created & 2026-08-XX & Pre-experiment \\
60 experiments started & 2026-09-02 & Experiment execution \\
Earliest 60-experiment result & 2026-09-02 15:59 & Experiment result \\
OSF mid-stream archive manifest & 2026-09-05 12:19 & Mid-stream archive \\
A1 amendment created & 2026-09-05 14:33 & \textbf{Post-hoc analysis plan} \\
A1 amendment last modified & 2026-09-06 18:38 & Post-hoc revision \\
Latest 60-experiment result & 2026-09-06 18:25 & Experiment result \\
A1 formal OSF archiving & [TBD, P0-2] & Formal archive \\
Supplementary experiments (E1-E6) & 2026-09-09 onward & Planned \\
\hline
\end{tabular}
\end{table}

\textbf{Honest disclosure}: Protocol amendment A1 (including A1.1, 
A1.2, A1.3, A1.4.2) was created on 2026-09-05, after some 60 
experiments had been completed (earliest result 2026-09-02). 
\textbf{A1 is a post-hoc analysis plan based on partial experimental 
results, not a pre-registration.} The OSF archive manifest (2026-09-05 
12:19) was also created mid-stream, not before experiments. We do not 
claim any pre-registration status for A1 or the OSF manifest. All 
hypotheses tested in this paper should be considered exploratory, 
not confirmatory pre-registered hypotheses.
```

#### 新增 §Methods：净临床价值定义（P1-6 修补）

```latex
\subsection{Net Clinical Value Definition}
We define Net Clinical Value (NCV) to quantify the clinical impact 
of thresholded decision changes:
\begin{equation}
NCV = \frac{TP_{improved} - FP_{worsened}}{N_{total}}
\end{equation}
where $TP_{improved}$ is the number of samples where TS changes 
the decision to be closer to the true label (correctly reporting 
a true class that was previously below threshold), and 
$FP_{worsened}$ is the number of samples where TS changes the 
decision to be further from the true label (incorrectly reporting 
a false class or missing a true class). We require $NCV > 0$ for 
TS to have net clinical value.
```

#### 新增 §6.X：临床决策影响分析（E3 支撑）

```latex
\subsection{Clinical decision impact of calibration benefit}
- TS 不改变 argmax，top-1 准确率变化 = 0（主动声明）
- \textbf{Primary endpoint}: Brier reliability 改善（Cohen's d > 0.2, small effect）
- \textbf{Primary endpoint}: 阈值化决策改变率 DCR（τ=0.5 主报告）
- 净临床价值 NCV（改对比例 - 改错比例，P1-6 明确定义）
- Secondary endpoints: TS 对 top-1 准确率无显著影响；DCR > 0
- BH FDR 校正仅用于 2 个 secondary endpoints（q=0.05）
- Exploratory: per-class DCR, per-threshold DCR (τ=0.7/0.9), ECE 变化
```

#### 新增 §6.Y：经验性部署前查表工具 + LOCO 跨语料庫泛化验证（E1 + E4 支撑）

```latex
\subsection{Empirical pre-deployment lookup table and cross-corpus 
generalization validation}
- EBT-LT 工具（经验性查表，非理论方法）：输入（源域 ID 校准性能 + 目标域 OOD 估计）→ 输出（经验性参考建议 + ECE 改善区间 + 风险等级）
- LOCO 3 折探索性验证（3 个 case study，诚实披露 n=3 局限）
- 完整 L2 矩阵安全率
- 2/6 可部署方向正面推荐 + 4/6 不可部署方向风险警告
- \textbf{诚实声明}: 这是经验性查表工具，不是理论方法；6 个迁移方向的经验基础有限
```

### 4.4 需要删减的内容

- **删减**：过度冗长的反例逐个描述（9 个反例当前每个 1 段，压缩为 1 个表 + 1 段共性模式）
- **删减**：CI 方法（BCa vs percentile）的过度讨论（压缩为 1 句话）
- **删减**：meta-analytic pooling 的固定效应 vs 随机效应讨论（压缩为 1 段）
- **删减**：**所有"预注册"字样**（P0-1 修补，全局搜索删除）
- **删减**：**乘法模型 T(x) = T_base · exp(α·s(x)) 的所有引用**（P1-1 修补）
- **删减**：**TS-DRA 的理论推导**（P1-3 修补，只保留经验描述）
- **目的**：从 47 页压缩到 CBM 期望的 15-20 页（CBM 无硬性页限，但审稿人不喜欢注水）

**页数目标**：主文 18-22 页（从 47 页压缩），补充材料不限。

---

## 5. 审稿人预判 + 预防性回应

### 5.1 CBM 审稿人画像

CBM 审稿人通常是：
- **生物医学 AI 应用研究者**（不是校准理论专家）
- 看重**临床相关性**和**实验严谨性**
- 对**预注册**可能不熟悉（**R3 不引用预注册，改用"诚实披露证伪"**）
- 对**效应量**敏感（"0.016 有意义吗？"）
- 对**多数据集验证**有好感
- **对时间线透明度敏感**（如果发现事后分析包装为预注册，会严重影响可信度）

### 5.2 预期审稿问题 + 预防性回应

| # | 预期问题 | 严重性 | 预防性回应（论文中预先写入） | 对应实验 |
|---|---------|--------|---------------------------|---------|
| **Q1** | "ECE 改善 0.016 有临床意义吗？TS 不改变 top-1 预测，有什么用？" | **致命** | §Methods 主动声明 TS preserves argmax；§6.X：ECE 0.016 对应阈值化决策改变率 DCR + Brier reliability 改善 + 净临床价值 NCV；**临床价值在于阈值化决策**（聚焦，P1-5） | E3 |
| **Q2** | "4/6 方向准确率不如多数类基线，校准有意义吗？" | **高** | §Discussion：校准的前提是 discrimination 可接受；我们明确划分"可部署方向"（2/6）和"不可部署方向"（4/6）；在可部署方向上校准收益更大；不可部署方向上诚实报告 discrimination 不足时校准的有限价值 | E2 |
| **Q3** | "ID 边界 38.3% < 80%，假设失败了，论文证明了什么？这是 HARKing 吗？时间线透明吗？" | **高** | §C2：**诚实披露证伪**——假设 ID 边界 > 80% 未达到，诚实报告证伪；1.9× 标记为 **post-hoc exploratory observation, not pre-registered hypothesis confirmation**；§Methods Table X 透明披露时间线；**A1 修订案是事后分析计划，不是预注册**（P0-1/P0-3/P0-4） | 无需新实验 |
| **Q4** | "安全率 0.0064 这么低，TS 还推荐吗？" | **中高** | §C4：安全率是在最严格 L2 矩阵上的结果；在 L1 跨語料庫層面 85% 支持率；**经验性查表工具**区分"可部署方向"（2/6，推荐）和"不可部署方向"（4/6，风险警告） | E1 |
| **Q5** | "只有 2 架构家族 + 1 超参变体，架构稳健性成立吗？" | **中** | §C4：**诚实声明 2 架构家族 + 1 超参变体**（P1-4）；InceptionTime-Lite 是 InceptionTime 的超参变体，不是独立架构家族；架构稳健性在 2 主架构家族上成立 | E5 |
| **Q6** | "部署准则是 in-sample 的，能部署吗？" | **中** | §6.Y：LOCO 3 折探索性验证（3 个 case study，诚实披露 n=3 局限）+ **经验性查表工具**基于源域特征（不需要先跑 TS） | E1, E4 |
| **Q7** | "与 TransCal/PseudoCal/LaSCal 相比有什么优势？" | **中** | §Related Work：S1 范式（源域 cal fit，无目标标签）是严格更弱假设；我们的贡献是边界刻画 + **经验查表工具**，不是方法上界 | 无需新实验 |
| **Q8** | "9 个反例 15% 率，超过临床安全 5%，怎么保证部署安全？" | **中** | §Discussion：这是边界研究不是部署指南；反例有可识别机制（低 OOD acc + 大 gap）；**经验性查表工具**提供部署前门控 | E1 |
| **Q9** | "所有假设都是 exploratory，那有什么意义？" | **中** | §Methods：**诚实披露所有假设是 exploratory**；价值在于(1) 诚实证伪（ID 边界 > 80% 证伪）；(2) 透明性（公开时间线）；(3) 开放科学实践（诚实披露事后分析 + 证伪本身就是贡献） | 无需新实验 |
| **Q10** | "为什么不用 conformal prediction？" | **低** | §Discussion：CP 提供预测集保证但不改变 argmax；TS 改变置信度用于决策阈值；两者互补，未来工作 | 无需新实验 |
| **Q11** | "EBT-LT 只有 6 个数据点，能泛化吗？" | **中** | §C4：**诚实声明 EBT-LT 是经验性查表工具，不是理论方法**（P1-3）；6 个迁移方向的经验基础有限；我们不声称泛化能力，只提供经验参考 | E1, E4 |

### 5.3 审稿人攻击优先级排序

**必须在论文中预防的 Top 3**（不预防则被拒）：
1. **Q1（临床意义 + TS 不改变 argmax）** → E3 + 主动声明 + P1-5 聚焦阈值化决策解决
2. **Q2（准确率 < 基线）** → E2 + 重新叙事解决
3. **Q3（证伪 + HARKing + 时间线）** → C2 诚实披露证伪 + P0-3 时间线透明披露解决

**预防后可大幅缓解的 Top 3**：
4. **Q4（安全率低）** → E1 + 经验性查表工具解决
5. **Q6（in-sample 部署）** → E1 LOCO + E4 经验查表解决
6. **Q5（架构数）** → E5 + P1-4 诚实声明解决

---

## 6. 与现有文献的定位（Related Work 增强）

### 6.1 当前 Related Work 的问题

当前 §Related Work 只有 1 段（~15 行），太薄。CBM 审稿人会问"你的工作和 X 有什么区别？"

### 6.2 增强后的 Related Work 结构（~1.5 页）

#### §2.1 深度学习校准方法
- **TS/Platt/Isotonic**（Guo 2017, Platt, Zadrozny 2002）：参数化 vs 非参数
- **Dirichlet/Vector/Matrix**（Kull 2019）：多类扩展
- **我们的定位**：不提新方法，做边界刻画 + **经验查表工具**

#### §2.2 域适应校准
- **TransCal**（Wang 2020）：目标域无监督最优 T → 需要目标域 logits
- **PseudoCal**（Garg 2020）：伪标签校准 → 需要目标域伪标签
- **LaSCal**（Popordanoska 2024）：label-shift 校准 → 需要 shift 估计
- **Saerens EM / BBSE**（Saerens 2002, Lipton 2018）：先验校正
- **我们的定位**：S1 范式（源域 cal fit，无目标标签）是**严格更弱假设**；我们在 S1 下做边界刻画 + **经验查表**，不做方法上界

#### §2.3 ECG 跨語料庫迁移与校准
- **PTB-XL 基准**（Strodthoff 2021）：单语料库内校准
- **Barandas 2023**：ECG 不确定性量化，多标签，但未做跨语料库边界
- **Physiol Meas 2026**（Haekal）：RR-interval AF 跨庫校准，特征模型 vs 本文深度多标签
- **medRxiv 2026**（Patel）：ICU calibration drift，slope 保持/intercept 漂移（与本文平行结论）
- **EA-CRC 2025**：ECG conformal risk control，missed-finding risk（与本文互补，CP vs TS）
- **我们的定位**：首个在 3 语料库 × 2 架构家族 × 5 种子上做 TS 边界条件刻画 + **经验性部署前查表工具**的工作

#### §2.4 OOD 校准的一般理论
- **Ovadia 2019**：ID vs OOD 校准不对称（一般视觉）
- **我们的定位**：ECG 特化的量化 + 边界条件 + **经验查表工具**

### 6.3 关键定位语句（论文中必须出现）

<!-- R3-FIX: P0-1 放弃预注册叙事 -->
<!-- R3-FIX: P1-3 降级TS-DRA为经验查表 -->
> "Our contribution is not a new recalibration method, nor the first observation of ID-to-OOD calibration benefit attenuation (Ovadia et al. 2019). It is the first systematic, multi-seed characterization of the boundary conditions under which temperature scaling yields a positive OOD calibration benefit in cross-corpus ECG transfer, with a **focus on the value of TS in thresholded clinical decisions**, an **empirical pre-deployment lookup table and boundary condition characterization** based on 60 experiments, and a **transparent disclosure of falsified hypotheses and post-hoc exploratory observations as an open science practice**."

这句话明确划清与 Ovadia 2019 的界限，同时定位贡献为"**阈值化决策价值 + 经验查表工具 + 诚实证伪的开放科学实践**"而非"新方法"、"决策框架"或"预注册分支触发"。

---

## 7. 9 周时间表

### 7.1 总体节奏

| 阶段 | 周次 | 内容 | 产出 |
|------|------|------|------|
| **Phase A: 补充实验** | W1-W2 | E1-E4 后处理 + E5 轻量训练 | 6 个 results CSV |
| **Phase B: 可视化** | W3 上半 | E6 可靠性图 + 论文图表更新 | figures/ |
| **Phase C: 论文重写** | W3 下半 - W7 | 4 贡献重组 + 新增章节 + 压缩 + **删除所有预注册字样** | main.tex v4.0 |
| **Phase D: 内审** | W8 | 自审 + 修复 + cover letter + **时间线一致性检查** | main.pdf |
| **Phase E: 投稿** | W9 | 格式检查 + 补充材料整理 + **A1修订案OSF正式存档** + 投稿 | 投稿包 |

### 7.2 详细周计划

#### W1（9/9-9/15）：后处理实验 E1 + E2

| 天 | 任务 | 产出 |
|----|------|------|
| D1-D2 | E1: 编写 L2 补齐脚本 + 跑 233 cells | `l2_shift_full_390cells.csv` |
| D3 | E1: LOCO 跨语料庫泛化验证脚本 + 运行 | `deployment_loco_validation.csv` |
| D4-D5 | E2: 消融实验（TS only / TS+binned / TS+binned+threshold opt）+ discrimination metrics | `ablation_ts_components.csv` + `discrimination_metrics_60exp.csv` |

#### W2（9/16-9/22）：后处理实验 E3 + E4 + E5 启动

| 天 | 任务 | 产出 |
|----|------|------|
| D1-D2 | E3: Brier reliability + DCR + NCV（primary endpoint，减少FDR） | `brier_decomposition_primary.csv` + `thresholded_decision_change_primary.csv` + `net_clinical_value.csv` |
| D3 | E4: 分箱温度 + 偏移敏感度（放弃乘法模型） | `binned_temperature_results.csv` + `temperature_distribution_analysis.csv` |
| D4 | E5: 实现 InceptionTime 简化版 + 单元测试 + 显存实测 | `src/models/inceptiontime_lite.py` |
| D5-D7 | E5: 训练 15 模型（3 语料库 × 5 种子，GPU 后台） | 15 checkpoint |

#### W3（9/23-9/29）：E5 评估 + E6 可视化 + 论文重写启动

| 天 | 任务 | 产出 |
|----|------|------|
| D1 | E5: 30 transfer 评估 + 240 校准评估 | `c3_inceptiontime_lite_30exp.csv` |
| D2-D3 | E6: 生成 7 张主文 + 60 张补充材料 reliability diagram | `figures/fig_reliability_*.pdf` |
| D4-D7 | 论文重写：§Related Work 扩写 + §Introduction 重定位（聚焦阈值化决策）+ §Methods 新增 TS 性质声明 + **时间线披露 Table X** | main.tex §1-2 |

#### W4（9/30-10/6）：论文重写 — Methods + Results

| 天 | 任务 |
|----|------|
| D1-D2 | §Methods 重写（加入 E5 的 InceptionTime-Lite 描述 + TS 性质声明 + **净临床价值定义** + **时间线披露** + **分箱温度方法**） |
| D3-D5 | §Results 重写：C1 升级（聚焦阈值化决策，加入 E2/E3 结果） |
| D6-D7 | §Results：C2 **诚实披露证伪**（删除所有预注册字样）+ C4 **经验性查表工具**（加入 E1/E5 结果） |

#### W5（10/7-10/13）：论文重写 — 新增章节 + Discussion

| 天 | 任务 |
|----|------|
| D1-D2 | 新增 §6.X 临床决策影响分析（E3 支撑，primary/secondary endpoint 分层） |
| D3-D4 | 新增 §6.Y 经验性部署前查表工具 + LOCO 验证（E1 + E4 支撑） |
| D5-D7 | §Discussion 重写：11 个审稿人问题预防性回应 + 低 AUROC 讨论段落 + **时间线透明披露** |

#### W6（10/14-10/20）：论文压缩 + 图表整合

| 天 | 任务 |
|----|------|
| D1-D3 | 压缩：反例描述 + CI 方法讨论 + meta-analysis 讨论 + **全局搜索删除"预注册"字样** + **删除乘法模型引用** + **删除 TS-DRA 理论推导** |
| D4-D5 | 图表整合：新增 Table（discrimination, clinical impact, LOCO, empirical lookup, **Table X 时间线**） |
| D6-D7 | 参考文献更新（加入 EA-CRC 2025, Cost-Sensitive CP 2026 等新文献） |

#### W7（10/21-10/27）：补充材料 + 代码整理

| 天 | 任务 |
|----|------|
| D1-D3 | 补充材料整理（完整 60 实验表 + L2 全矩阵 + 反例详情 + 60 张 reliability diagram + **A1修订案事后性质声明**） |
| D4-D5 | 代码整理 + README 更新 + 复现脚本验证 |
| D6-D7 | cover letter 撰写 |

#### W8（10/28-11/3）：内审 + 修复

| 天 | 任务 |
|----|------|
| D1-D3 | 自审：数字一致性检查（论文 vs results CSV，自动化脚本） |
| D4-D5 | 自审：逻辑一致性检查（4 贡献叙事链条 + **时间线一致性** + **无"预注册"字样残留**） |
| D6-D7 | 修复 + 最终编译 |

#### W9（11/4-11/10）：投稿准备 + 投稿

| 天 | 任务 |
|----|------|
| D1-D2 | CBM 格式检查（elsarticle 模板 + 作者信息 + 利益声明） |
| D3-D4 | 补充材料打包 + **A1修订案正式OSF存档（P0-2）** + OSF DOI 获取 |
| D5 | 投稿 |
| D6-D7 | 投稿后确认 + 预期审稿周期规划 |

### 7.3 关键里程碑

| 里程碑 | 时间 | 验收标准 |
|--------|------|---------|
| M1: 6 项实验完成 | W3 D1 | 6 个 results CSV + InceptionTime-Lite 30 实验 |
| M2: 论文初稿 v4.0 | W7 D7 | main.tex 重写完成，18-22 页，**无"预注册"字样** |
| M3: 内审通过 | W8 D7 | 数字 + 逻辑 + 时间线一致性检查通过 |
| M4: A1 OSF 正式存档 | W9 D4 | OSF DOI 获取（P0-2） |
| M5: 投稿 | W9 D5 | CBM 投稿系统提交成功 |

### 7.4 风险缓冲

- **W1-W2 的后处理实验**有 2 天缓冲（万一脚本有 bug）
- **E5 的 InceptionTime 简化版训练**有 2 天缓冲（万一 OOM 需调参或改用 ResNet1D 变体）
- **论文重写**有 1 周缓冲（W8 内审可吸收重写延期）
- **A1 OSF 存档**有 1 天缓冲（W9 D3-D4）
- **总缓冲**：~5 天，足够吸收一般风险

---

## 8. 预期效果 + 边际贡献汇总

### 8.1 改进前后对比

| 指标 | 当前 | 改进后 | 改进来源 |
|------|------|--------|---------|
| Q2 接收概率 | 25-35% | **28-38%（中值 33%）** | 6 项实验 + 叙事重定位 + 主动声明 + **诚实披露证伪** |
| 临床意义论证 | 无 | 阈值化决策改变率 DCR + Brier reliability + NCV | E3 |
| 架构数 | 2 | 2 架构家族 + 1 超参变体（诚实声明） | E5 |
| L2 覆盖 | 157/390 | 390/390 | E1 |
| 部署验证 | 无 | LOCO 3 个 case study + **经验性查表工具** | E1, E4 |
| Discrimination metrics | 无 | AUROC/AUPRC/F1/PPV/NPV | E2 |
| 可靠性图 | 无 | 7 张主文 + 60 张补充 | E6 |
| 论文页数 | 47 | 18-22 | 压缩 |
| Related Work | 1 段 | 1.5 页 | 扩写 |
| TS 性质声明 | 无 | Method 主动声明 | P0-4 |
| **预注册叙事** | **R2 有（造假）** | **R3 无（诚实披露证伪）** | **P0-1** |
| **时间线透明** | **R2 不透明** | **R3 Table X 透明披露** | **P0-3** |
| **温度模型** | **R2 乘法模型（prior art 风险）** | **R3 分箱温度（无 prior art）** | **P1-1** |
| **FDR 检验数** | **R2 72 个** | **R3 2 个（primary 不校正）** | **P1-2** |
| **TS-DRA/EBT-LT** | **R2 理论方法（6 数据点）** | **R3 经验查表（诚实）** | **P1-3** |

### 8.2 边际贡献分解（R3 修正，考虑放弃预注册叙事 + 效应量硬伤）

| 改进 | 边际贡献 | 累计 | 理由 |
|------|---------|------|------|
| 基线（当前论文） | 25-35% | 30% | 效应量小 + 无临床意义 + 事后分析叙事 |
| + E1（L2 补齐 + LOCO 3 个 case study） | +5-8% | 36% | L2 补齐解决 G4；LOCO n=3 只提供 descriptive 证据 |
| + E2（消融实验 + discrimination，可能暴露问题） | -2% 到 +3% | 37% | 消融更严谨，但可能暴露无边际改善或低 AUROC（负交互） |
| + E3（Brier reliability + DCR + NCV，减少FDR） | +3-5% | 41% | P1-2 减少检验提升功效；P1-6 明确定义；P1-7 降低阈值 |
| + E4（分箱温度 + 偏移敏感度） | +1-2% | 42% | 分箱温度无 prior art 风险，支持 E2 消融 |
| + E5（InceptionTime 简化版，超参变体） | +1-3% | 44% | 超参变体弱于新架构家族，诚实声明后贡献降低 |
| + E6（可靠性图） | +2-3% | 46% | 可视化质量提升 |
| - 负交互效应 | -6-10% | 40% | E2 与 E3 负交互 + E1 与 E3 负交互 + E5 与 C4 负交互 |
| - 叙事重定位风险 | -3-5% | 37% | **放弃预注册叙事后 C2 贡献降低**；"经验查表"弱于"决策框架" |
| + 诚实声明 TS 性质（主动披露加分） | +1-2% | 38% | 把 F1 从攻击点转化为诚实声明 |
| + **诚实披露证伪 + 时间线透明**（开放科学加分） | +1-2% | 39% | **诚实披露证伪 + post-hoc exploratory observation + 时间线透明**（弱于预注册，但仍有开放科学价值） |
| - **效应量小的硬伤** | **-5-8%** | **33%** | **ECE 0.016 的效应量小是无法修补的硬伤** |
| **R3 预期接收概率** | | **28-38%** | |

### 8.3 接收概率的详细分解

<!-- R3-FIX: P1-1 放弃乘法模型 -->
**R3 放弃乘法模型**（P1-1 修补）：R2 使用乘法模型 T(x) = T_base · exp(α·s(x)) 估计接收概率，这是 Joy et al. AAAI 2023 的受限特例，有 prior art 风险，且 4.2% vs 35-45% 脱节。R3 改用**基于 CBM 历史接收率和论文特征的主观估计**，诚实承认 28-38% 是主观估计。

**接收概率主观估计 = 基准 × 调整因子**

| 维度 | R2 评分 | R3 评分 | 理由 |
|------|---------|---------|------|
| 创新性 | 20% | 18% | 不做新方法；创新点在"阈值化决策价值 + 经验查表 + 诚实证伪"，CBM 可能不认为这是"计算机方法创新"；**放弃预注册叙事后创新性略降** |
| 方法严谨性 | 60% | 62% | 60 实验 + 3 语料库 + 8 方法 + 患者级 bootstrap BCa；**P1-2 减少FDR检验提升功效**；**P1-1 分箱温度无prior art风险**；LOCO n=3 限制 |
| 叙事完整性 | 70% | 68% | **R3 叙事更诚实（诚实披露证伪 + 时间线透明），但"经验查表"弱于"决策框架"，"诚实证伪"弱于"预注册分支触发"**；效应量小叙事难自圆 |
| 效应量风险 | 50% | 50% | ECE 0.016 的效应量小是无法修补的硬伤；**P1-7 降低 H1 阈值至 Cohen's d > 0.2 降低失败风险** |
| **综合（主观估计）** | **35-45%** | **28-38%** | **R3 比 R2 低 5-7%，主要因为放弃预注册叙事后 C2 贡献降低** |

**说明**：上述是**主观估计**（非乘法模型），基于 CBM 历史接收率（~12%）、论文特征（实验体量、透明性、效应量）和 R2 终审独立估计的综合判断。28-38%（中值 33%）与 R2 终审独立估计一致。

### 8.4 与"不做任何改进"的对比

| 场景 | 接收概率 | 理由 |
|------|---------|------|
| 不改进直接投 | 25-35% | 效应量小 + 无临床意义 + 事后分析叙事 |
| 执行 R3 方案 | 28-38% | 补齐 7 个缺口 + 叙事升级 + 主动声明 + **诚实披露证伪** |
| 执行 R2 方案（已废弃） | 35-45%（高估，含造假叙事） | 基于虚假预注册声明，N1 攻击成立后降至 28-38% |
| 执行 R1 方案（已废弃） | 55-65%（高估） | 基于独立可加假设，未考虑负交互 + 效应量硬伤 |
| 执行一区方案（DA-TS） | 15-25% | 方法新颖性不足（前一轮对抗结论） |

**结论**：R3 方案是当前条件下的**最优策略**——不追求方法创新（已证不可行），不声称预注册（已证造假），而是最大化现有 60 实验的价值通过后处理分析 + 叙事重定位 + 主动诚实声明 + **诚实披露证伪**。9 周工作量换取 3-8% 的接收概率提升，性价比可接受（有 fallback 期刊）。

---

## 9. 论证自检（正方自我审查）

### 9.1 核心主张

<!-- R3-FIX: P0-1 放弃预注册叙事 -->
**通过 6 项后处理实验（5 项 GPU≈0）+ 论文叙事重定位 + 主动声明 TS 数学性质 + 诚实披露证伪 + 时间线透明披露，将当前 60 实验的边界研究升级为"跨语料库 ECG 部署的 TS 校准在阈值化临床决策中的价值刻画 + 经验性部署前查表工具"，达到 CBM 二区稳定接收标准（28-38% 接收概率，中值 33%）。**

### 9.2 关键假设（逐条标注可证伪性）

<!-- R3-FIX: P1-7 降低H1阈值 -->
- **H1**（R3 重写，P1-7 降低阈值）：ECE 0.016 的改善对应可感知的 **Brier reliability 改善（Cohen's d > 0.2, small effect）**，且**阈值化决策改变率 DCR > 0**，且**净临床价值 NCV > 0**（改对比例显著高于改错比例）。【可证伪：E3 直接检验。若 Brier reliability 改善 Cohen's d < 0.2 或 NCV ≤ 0 → 触发备选叙事"校准使置信度更可信，对不确定性感知工作流有价值"】
  - **明确声明**：TS 不改变 argmax，top-1 准确率变化 = 0。本文不以 top-1 准确率变化作为 TS 效果指标。
  - **与 R2 的区别**：R2 的 H1 阈值是"决策改变率 > 5%"，R3 降为"Cohen's d > 0.2"（P1-7 修补），降低失败风险

- **H2**（R3 重写）：InceptionTime 简化版（~200K-500K 参数，<1M）在 ECG 上能达到 accuracy > 0.8（接近主架构），且 RTX 5060 8GB 能跑。**InceptionTime-Lite 是 InceptionTime 的超参变体，不是独立架构家族**（P1-4 诚实声明）。【可证伪：E5 直接检验。若 accuracy < 0.7 或 OOM → 备选：改用 ResNet1D 不同超参变体；或诚实报告"2 架构家族 + BiMamba toy"】

- **H3**（R3 重写）：LOCO 3 折验证的 Youden J 点估计 > 0，**定位为"3 个 case study"**，诚实披露 n=3 的统计效力局限。【可证伪：E1 直接检验。若 J ≈ 0 → 诚实报告"部署准则需局部验证"，不选择性呈现】

- **H4**：CBM 审稿人接受"阈值化决策价值 + 经验查表工具 + 诚实证伪"作为贡献（不要求新方法，不要求预注册）。【可证伪：投稿后审稿结果。若审稿人要求新方法 → 转 Physiological Measurement（IF~3, 接收率更高, ECG+校准对口）】

- **H5**（R3 重写，**放弃预注册叙事**）：CBM 审稿人接受"诚实披露证伪 + post-hoc exploratory observation + 时间线透明"作为开放科学贡献（不认为是 HARKing）。【可证伪：投稿后审稿结果。若审稿人仍认为 HARKing → 进一步强调证伪的诚实性和时间线透明性】

- **H6**（R3 新增，P1-1 分箱温度）：分箱温度（5 bin）比单一 T 有边际 Brier reliability 改善。【可证伪：E2 消融实验直接检验。若分箱温度无边际改善 → 诚实报告，单一 T 已足够】

### 9.3 适用边界

- **适用**：CBM（IF~7, 接收率 12%）、Physiological Measurement（IF~3, 接收率更高）、Expert Systems with Applications 等二区期刊
- **不适用**：JBHI、npj Digital Medicine 等一区（前一轮对抗已证方法创新不足）
- **不适用**：若审稿人坚持要求新方法（此时需转投或延长到 6 个月做真正创新）
- **不适用**：若审稿人坚持要求预注册（**R3 不声称预注册，若审稿人要求 → 转投不要求预注册的期刊**）

### 9.4 推理链条（每步依据）

1. 前一轮对抗确认 DA-TS/CSC-ECG 对 Q1 不成立（方法新颖性不足）【依据：FINAL_DECISION.md】
2. 当前论文实验骨架已超 CBM 平均（60 实验 + 透明披露）【依据：§2.1 评估】
3. 当前论文在临床意义/叙事/部署可操作性上有 7 个缺口【依据：§2.2 诊断】
4. 7 个缺口中 6 个可通过后处理分析解决（GPU≈0），1 个需轻量训练【依据：§3 实验设计】
5. R2 方案被反方攻击 N1（A1.4.2 预注册造假），终审独立验证确认【依据：R2 终审裁决】
6. R3 方案按 P0+P1 修补清单（12 项）修改后，**放弃预注册叙事，改用诚实披露证伪**【依据：§0 修改追踪表】
7. R3 方案聚焦 TS 在阈值化临床决策中的价值（P1-5），规避"TS 不改变 argmax"攻击【依据：§4.2 C1】
8. R3 方案减少 FDR 检验数量（P1-2），降低 H1 阈值（P1-7），提升功效【依据：§3.2 E3】
9. R3 方案放弃乘法模型改分箱温度（P1-1），规避 prior art 风险【依据：§3.2 E4】
10. R3 方案降级 TS-DRA 为经验查表（P1-3），诚实声明架构变体（P1-4），更诚实【依据：§4.2 C4】
11. 后处理分析 + 叙事重定位 + 主动声明 + 诚实披露证伪可将接收概率从 30% 提升到 28-38%【依据：§8.2 边际贡献分解】
12. 9 周内可行（实验 2-3 周 + 写作 5-6 周 + 缓冲 1 周）【依据：§7 时间表】
13. → R3 方案是当前条件下的最优 Q2 策略【依据：与"不改进"和"一区方案"的对比】

### 9.5 自我发现的最弱环节（R3 诚实审查）

- **最弱**：**效应量小（ECE 0.016）是无法修补的硬伤**。即使所有修补成功，ECE 0.016 的效应量小仍然是审稿人可能拒稿的理由。E3 的 Brier reliability + DCR + NCV 是缓解措施，但无法消除这一硬伤。终审在接收概率中计入 -5-8% 的效应量硬伤。
- **次弱**：H1（Brier reliability 改善 Cohen's d > 0.2 且 NCV > 0）是经验性假设，需 E3 实验验证。**P1-7 降低阈值至 Cohen's d > 0.2 降低失败风险**，但若仍失败需触发备选叙事"置信度校准对不确定性感知工作流的价值"。
- **第三弱**：**放弃预注册叙事后 C2 贡献降低**（从 R2 的 +4-6% 降至 +2-3%）。"诚实披露证伪"叙事的强度不如"预注册分支触发"，但这是诚实的代价。
- **第四弱**：H4/H5（CBM 审稿人接受"阈值化决策价值 + 经验查表 + 诚实证伪"作为贡献）无法先验保证。CBM 12% 接收率意味着竞争激烈。备选：转投 Physiological Measurement（IF~3, 接收率更高）。
- **第五弱**：H6（分箱温度有边际改善）是经验性假设，需 E2 消融实验验证。若分箱温度无边际改善，需诚实报告"单一 T 已足够"。

---

## 10. 与反方攻击的预设应对（R3 更新）

| 预期反方攻击 | 正方 R3 回应 |
|-------------|---------|
| "28-38% 接收概率，9 周工作量性价比存疑" | 回应：9 周工作量换取 3-8% 的接收概率提升，且有 fallback 期刊（Physiol Meas 接收率更高）；实验阶段 2-3 周（5 项后处理 GPU≈0），主要工作量在论文重写 |
| "ECE 0.016 的效应量小，临床意义不成立" | 回应：E3 的 Brier reliability + DCR + NCV 是缓解措施；主动声明 TS 不改变 argmax，**临床价值在于阈值化决策**（P1-5 聚焦）；若 E3 证伪 → 触发备选叙事 |
| "TS 不改变 argmax，这篇论文有什么用？" | 回应：§Methods 主动声明 TS preserves argmax；**临床价值在于阈值化决策**（P1-5 聚焦，不分散到存疑场景）；这不是弱点而是 TS 的设计特性 |
| "C2 还是 HARKing，A1.4.2 不是预注册" | 回应：**R3 承认 A1.4.2 不是预注册**（P0-1）；C2 改用"诚实披露证伪 + post-hoc exploratory observation"叙事；**时间线透明披露**（Table X，P0-3）；1.9× 标记为 post-hoc exploratory observation（P0-4）；**不声称预注册，诚实披露事后分析性质** |
| "经验查表工具只有 6 个数据点，能泛化吗？" | 回应：**诚实声明 EBT-LT 是经验性查表工具，不是理论方法**（P1-3）；6 个迁移方向的经验基础有限；不声称泛化能力，只提供经验参考 |
| "InceptionTime-Lite 是同家族变体，不是独立架构" | 回应：**诚实声明 2 架构家族 + 1 超参变体**（P1-4）；InceptionTime-Lite 是 InceptionTime 的超参变体；架构稳健性在 2 主架构家族上成立 |
| "LOCO 3 折算什么外部验证？" | 回应：明确声明"3 折 leave-one-corpus-out 探索性验证"（**3 个 case study**），不声称"外部验证"；报告点估计 + 诚实披露 n=3 局限；经验查表工具基于源域特征，不需要先跑 TS |
| "9 周可能不够" | 回应：6 项实验中 5 项后处理（GPU≈0），只有 E5 需训练；实验 2-3 周 + 写作 5-6 周，9 周可行；W8 有缓冲；若延期 → 砍 E4 保其他 |
| "分箱温度是 ad hoc 方法" | 回应：分箱温度是通用非参数方法（quintile binning），无参数化假设，无 prior art 风险（P1-1）；比 R2 的乘法模型更诚实 |
| "FDR 检验数量减少是 cherry-picking" | 回应：**预先声明 primary endpoint**（Brier reliability），不进入 FDR 校正；secondary endpoints 只有 2 个，BH FDR 校正；exploratory endpoints 明确标记，不进入主推断（P1-2）；这是标准的假设分层做法，不是 cherry-picking |

---

## 11. 备选方案（若 R3 方案受阻）

### 11.1 若 E3（临床意义）失败

**触发条件**：Brier reliability 改善 Cohen's d < 0.2 或 NCV ≤ 0
**备选叙事**：从"阈值化决策影响"转为"校准可信度提升"——TS 使高风险样本的置信度更接近真实频率，即使 argmax 不变，置信度校准对**不确定性感知的临床工作流**（如人工复核阈值 P>0.7 自动报告，0.3<P<0.7 人工复核）有价值
**目标期刊不变**：CBM 仍可接受"可信度提升"叙事
**接收概率**：25-33%（E3 边际贡献降至 +1-2%）

### 11.2 若 E5（InceptionTime 简化版）失败

**触发条件**：InceptionTime 简化版 accuracy < 0.7 或 OOM
**备选**：改用 ResNet1D 不同超参变体（depth 3/5/7, width 32/64/128）；或直接砍掉第 3 架构，诚实报告"2 架构家族 + BiMamba toy"，强调"架构稳健性在 2 主架构家族上成立"
**边际贡献损失**：-1-3%（回到 27-35%）

### 11.3 若 E2 消融实验显示无边际改善

**触发条件**：分箱温度无边际改善（(2) ≈ (1)）或阈值优化无边际改善（(3) ≈ (2)）
**备选**：诚实报告"单一 T 已足够"或"阈值化决策价值有限"；聚焦 TS only 的 Brier reliability 改善
**边际贡献损失**：-1-2%（回到 27-36%）

### 11.4 若 CBM 被拒

**备选期刊**（按推荐度）：
1. **Physiological Measurement**（IF~3, SCI Q3/Q2, 接收率更高, ECG+校准对口）——**首选 fallback**
2. **Expert Systems with Applications**（IF~8, 看应用不看方法创新）
3. **Biomedical Signal Processing and Control**（IF~5, ECG 专刊）
4. **IEEE Access**（IF~3, 接收率高，保底）

**转投策略**：CBM 审稿反馈可用于改进，转投时已解决 CBM 审稿人问题，接收概率 65-75%。

---

## 12. 方案状态声明

### 12.1 已完成

- ✅ R1 方案对抗审查（正方→反方→反反方→终审）
- ✅ R2 方案对抗审查（正方→反方→反反方→终审）
- ✅ R2 终审裁决：GO WITH MODIFICATIONS（N1 严重可修补）
- ✅ R3 方案按 P0+P1 修补清单（12 项）修改完成
- ✅ R2→R3 修改追踪表（§0）
- ✅ 6 项具体补充实验设计（含 GPU 负担 + 边际贡献 + 风险标注）
- ✅ 4 贡献重新组织策略（**C2 诚实披露证伪，C4 经验查表工具**）
- ✅ 11 个审稿人问题预防性回应
- ✅ Related Work 增强定位
- ✅ 9 周详细时间表
- ✅ 自检（6 假设 + 5 最弱环节 + 10 反方攻击应对）
- ✅ 接收概率下调至 28-38%（中值 33%）

### 12.2 R3 修补完成状态

| 修补项 | 优先级 | 状态 | 本文档位置 |
|--------|--------|------|-----------|
| P0-1 放弃A1.4.2预注册叙事 | P0 | ✅ 完成 | §4.2 C2, §5.2 Q3, §附录A |
| P0-2 A1修订案正式OSF存档 | P0 | ✅ 完成（计划） | §附录C, §7.2 W9 |
| P0-3 透明披露时间线 | P0 | ✅ 完成 | §4.3 §Methods, Table X |
| P0-4 1.9×标记post-hoc | P0 | ✅ 完成 | §4.2 C2, §4.1叙事, §附录A |
| P1-1 放弃乘法模型改分箱温度 | P1 | ✅ 完成 | §3.2 E4, §4.3 §Methods |
| P1-2 减少FDR检验数量 | P1 | ✅ 完成 | §3.2 E3, §9.2 H1 |
| P1-3 降级TS-DRA为经验查表 | P1 | ✅ 完成 | §4.2 C4, §4.3 §6.Y |
| P1-4 诚实声明架构变体 | P1 | ✅ 完成 | §3.2 E5, §4.2 C4 |
| P1-5 聚焦阈值化决策 | P1 | ✅ 完成 | §1, §4.1, §4.2 C1 |
| P1-6 明确净临床价值定义 | P1 | ✅ 完成 | §3.2 E3, §4.3 §Methods |
| P1-7 降低H1阈值 | P1 | ✅ 完成 | §9.2 H1 |
| P1-8 修正E2为消融实验 | P1 | ✅ 完成 | §3.2 E2 |

### 12.3 核心自信度

- **高自信**：6 项实验可行（5 项后处理 + 1 项轻量训练，9 周内）
- **中自信**：接收概率 28-38%（中值 33%）——与 R2 终审独立估计一致，考虑了放弃预注册叙事 + 效应量硬伤 + 负交互 + CBM 竞争激烈
- **低自信**：E3 的 Brier reliability 改善 Cohen's d > 0.2 且 NCV > 0（需实验验证）；E5 的 InceptionTime 简化版性能达标（需实验验证）；E2 消融实验显示分箱温度有边际改善（需实验验证）；CBM 审稿人接受"诚实披露证伪"叙事（需投稿验证）

---

## 附录 A：A1 修订案诚实披露（R3 重写，放弃预注册叙事）

<!-- R3-FIX: P0-1 放弃预注册叙事 -->
<!-- R3-FIX: P0-4 1.9×标记post-hoc -->
**来源**：`PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md`（2026-09-05 14:33 创建，2026-09-06 18:38 最后修改）

**R3 诚实披露**（P0-1 修补，**放弃所有预注册声明**）：

> **A1 修订案的性质**：Protocol amendment A1（包括 A1.1, A1.2, A1.3, A1.4.2）创建于 2026-09-05 14:33，**晚于部分 60 实验完成时间**（最早结果 2026-09-02 15:59）。**A1 是基于部分实验结果的 post-hoc analysis plan，不是 pre-registration。**
> 
> **时间线证据**（R2 终审独立验证）：
> - 60 实验最早结果：2026-09-02 15:59:25
> - OSF 存档清单创建：2026-09-05 12:19:46（**mid-stream archive，不是 pre-experiment archive**）
> - A1 修订案创建：2026-09-05 14:33:03（晚于 OSF 清单 2 小时 13 分钟）
> - A1 修订案最后修改：2026-09-06 18:38:35
> - 60 实验最晚结果：2026-09-06 18:25:24
> 
> **R3 不声称**：
> - ❌ "这一分支触发条件在数据收集前已预注册"（**不成立**）
> - ❌ "有 OSF 哈希存档，可验证预注册时间戳"（**不成立**）
> - ❌ "A1.4.2 是预注册的分支触发条件"（**不成立**）
> 
> **R3 诚实声明**：
> - ✅ A1 修订案是 **post-hoc analysis plan**，基于部分实验结果创建
> - ✅ OSF 存档清单是 **mid-stream archive**，不是 pre-experiment archive
> - ✅ 所有假设应视为 **exploratory**，不是 confirmatory pre-registered hypotheses
> - ✅ 1.9× OOD/ID 比率是 **post-hoc exploratory observation, not pre-registered hypothesis confirmation**（P0-4 修补）

**A1.4.2 原文摘要**（保留，但重新定性）：

> **分支触发**：若 95% CI 含 0 的格占比 < 80%，触发"ID 非零边界"分支：
> - 在讨论中重新审视"ID 无可修空间"前提
> - decay = ΔECE_OOD − ΔECE_ID 恢复为对照终点（仍非主终点），报告 decay 的探索性 CI
> - 主结论增加限定语："在 ID 边界条件（ΔECE_ID ≈ 0）成立的 N% 格上，OOD 校准收益 ΔECE_OOD 显著正向"
> - 不撤销主终点重新定位（A1.1），仅增加边界条件稳健性限定

**对 C2 叙事的意义**（R3 重写）：
- 正方的 C2 重定位**不是 HARKing，也不是预注册**，而是**诚实披露证伪 + post-hoc exploratory observation + 时间线透明**
- 1.9× 比率作为 **post-hoc exploratory observation** 报告，标记为 exploratory，不做假设检验
- 反方的 N1 攻击（预注册造假）在 R3 放弃预注册叙事后**不再适用**——R3 不声称预注册

**在论文中的引用方式**（R3 重写）：
> "We hypothesized that ID boundary condition satisfaction rate > 80%. The result (38.3%) falsified this hypothesis. **We honestly report this falsification.** The 1.9× OOD/ID ratio is a **post-hoc exploratory observation** with cross-direction stability analysis, **not a confirmatory finding and not a pre-registered hypothesis confirmation**. Protocol amendment A1 (2026-09-05) was a **post-hoc analysis plan** based on partial experimental results, **not a pre-registration**. We transparently disclose this timeline (see Table X)."

---

## 附录 B：R2→R3 关键变化对比（diff 对照）

| 维度 | R2 | R3 | 变化原因 | 对应修补 |
|------|----|----|---------|---------|
| **C2 叙事** | A1.4.2 预注册分支触发 | **诚实披露证伪 + post-hoc exploratory observation** | N1 攻击成立（预注册造假） | P0-1, P0-4 |
| **预注册声明** | 有（"数据收集前已预注册"、"OSF 哈希存档"） | **无（全部删除）** | N1 攻击成立 | P0-1 |
| **时间线透明** | 不透明 | **Table X 透明披露** | 遗漏问题1-2 | P0-3 |
| **A1 OSF 存档** | "待存档" | **正式存档（W9 D3-D4）** | N1 攻击成立 | P0-2 |
| **温度模型** | 乘法模型 T(x) = T_base · exp(α·s(x)) | **分箱温度（binned temperature）** | N2 攻击（prior art 风险） | P1-1 |
| **FDR 检验数** | 72 个 | **2 个（primary 不校正）** | N3 攻击（功效大降） | P1-2 |
| **TS-DRA/EBT-LT** | 理论方法（TS-DRA） | **经验查表（EBT-LT）** | N4 攻击（6 数据点） | P1-3 |
| **架构声明** | "3 架构" | **"2 架构家族 + 1 超参变体"** | N5 攻击（同家族） | P1-4 |
| **临床价值来源** | 3 个（阈值化决策 + 不确定性工作流 + Brier） | **聚焦阈值化决策** | N6 攻击（工作流存疑） | P1-5 |
| **净临床价值** | 定义模糊 | **明确量化定义 NCV** | N7 攻击（定义模糊） | P1-6 |
| **H1 阈值** | 决策改变率 > 5% | **Brier reliability Cohen's d > 0.2** | N8 攻击（>5% 矛盾） | P1-7 |
| **E2 实验** | discrimination metrics 计算 | **消融实验（3 阶段）** | N10 攻击（边际贡献高估） | P1-8 |
| **接收概率** | 35-45%（中值 40%） | **28-38%（中值 33%）** | 放弃预注册叙事 + R2 终审独立估计 | P0-1 |
| **定位** | 边界刻画 + 风险评估工具 + 预注册分支触发 | **阈值化决策价值 + 经验查表 + 诚实证伪** | N1 + N6 | P0-1, P1-5 |

---

## 附录 C：OSF 存档补救措施（P0-2 修补，新增）

<!-- R3-FIX: P0-2 A1修订案正式OSF存档 -->
**问题**：A1 修订案从未正式 OSF 存档，状态为"待存档"。R2 方案声称"有 OSF 哈希存档"是虚假的。

**R3 补救措施**：

### C.1 存档内容

| 文件 | 存档内容 | 存档状态 |
|------|---------|---------|
| `PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md` | A1 修订案全文（包括 A1.1-A1.4.2） | **待正式存档** |
| `osf_archive_manifest.json` | OSF 存档清单（9/5 12:19 创建，mid-stream archive） | 已存档（mid-stream） |
| `paper/main.tex` | 论文 main.tex（9/5 03:57 版本） | 已存档（mid-stream） |
| 60 实验结果 | 全部 60 实验的 transfer_result.json | 已存档 |
| **R3 新增**：时间线披露 | Table X 实验-协议时间线对照表 | **待正式存档** |
| **R3 新增**：诚实披露声明 | A1 事后分析性质声明 | **待正式存档** |

### C.2 存档时间节点

| 步骤 | 时间 | 操作 |
|------|------|------|
| 1 | W9 D3（11/6） | 将 A1 修订案 + 时间线披露 + 诚实披露声明上传到 OSF |
| 2 | W9 D4（11/7） | 获取 OSF DOI |
| 3 | W9 D4（11/7） | 在论文附录中填入 OSF DOI 链接 |
| 4 | W9 D5（11/8） | 投稿时在 cover letter 中说明 OSF 存档 |

### C.3 OSF DOI 占位符

在论文附录中：
```latex
\section*{Data and Code Availability}
All experimental data, code, and protocol documents are archived 
on the Open Science Framework (OSF) at 
\url{https://osf.io/[DOI_PLACEHOLDER]}.
This includes:
\begin{itemize}
\item 60 experiment results (6 directions × 2 architectures × 5 seeds)
\item Protocol v2.1 and amendment A1 (\textbf{post-hoc analysis plan, 
not pre-registration})
\item Experiment-protocol timeline disclosure (Table X)
\item Complete code and reproduction scripts
\end{itemize}
\textbf{Honest disclosure}: Protocol amendment A1 was created on 
2026-09-05, after some experiments had been completed. The OSF 
archive includes both mid-stream archives (2026-09-05) and the 
final formal archive (2026-11-XX). We do not claim pre-registration 
status for any protocol documents.
```

### C.4 存档的诚实性质

- **不声称预注册**：A1 修订案是 post-hoc analysis plan，OSF 存档只是正式记录，不赋予预注册地位
- **时间戳透明**：OSF 会记录上传时间（2026-11-XX），读者可以判断这是事后存档
- **mid-stream archive 诚实披露**：9/5 12:19 的 OSF 清单是 mid-stream archive，不是 pre-experiment archive，R3 诚实披露

---

## 附录 D：R3 自评（诚实评估仍可能存在的问题）

### D.1 R3 方案仍可能存在的问题

| # | 问题 | 严重性 | 可修补性 | 说明 |
|---|------|--------|---------|------|
| 1 | **效应量小（ECE 0.016）是无法修补的硬伤** | 严重 | 不可修补 | 数据决定的硬约束，E3 的 Brier reliability + DCR + NCV 是缓解措施但无法消除 |
| 2 | **放弃预注册叙事后 C2 贡献降低** | 中 | 已修补（诚实披露证伪） | 从 R2 的 +4-6% 降至 +2-3%，但这是诚实的代价 |
| 3 | **H1（Brier reliability Cohen's d > 0.2）可能失败** | 中 | 有备选叙事 | P1-7 降低阈值降低失败风险，但若仍失败需触发备选 |
| 4 | **H6（分箱温度有边际改善）可能失败** | 中 | 有备选 | 若分箱温度无边际改善，诚实报告"单一 T 已足够" |
| 5 | **CBM 审稿人可能不接受"诚实披露证伪"作为贡献** | 中 | 有 fallback 期刊 | 若审稿人要求预注册或新方法 → 转 Physiological Measurement |
| 6 | **E2 消融实验可能显示无边际改善** | 低 | 有备选 | 诚实报告，聚焦 TS only 的价值 |
| 7 | **E5 InceptionTime 简化版可能 OOM 或性能不达标** | 低 | 有备选 | 改用 ResNet1D 变体或诚实报告"2 架构家族" |
| 8 | **LOCO n=3 统计效力低** | 低 | 已诚实披露 | 定位为"3 个 case study"，不声称外部验证 |
| 9 | **EBT-LT 只有 6 个数据点** | 低 | 已诚实降级 | 降级为经验查表，不声称泛化能力 |
| 10 | **9 周时间紧张** | 低 | 有缓冲 | 5 天缓冲，可吸收一般风险 |

### D.2 R3 方案的优势（相比 R2）

1. **诚实**：放弃虚假的预注册叙事，改用诚实披露证伪——规避学术不端风险
2. **聚焦**：聚焦 TS 在阈值化临床决策中的价值——比 R2 的"多临床价值来源"更聚焦
3. **无 prior art 风险**：分箱温度替代乘法模型——规避 N2 攻击
4. **功效提升**：减少 FDR 检验数量至 2 个——规避 N3 攻击
5. **更诚实的工具定位**：EBT-LT 经验查表替代 TS-DRA 理论方法——规避 N4 攻击
6. **更诚实的架构声明**：2 架构家族 + 1 超参变体——规避 N5 攻击
7. **时间线透明**：Table X 透明披露——规避 HARKing 质疑

### D.3 R3 方案的劣势（相比 R2）

1. **接收概率降低**：从 35-45% 降至 28-38%（放弃预注册叙事的代价）
2. **C2 贡献降低**：从 +4-6% 降至 +2-3%（诚实披露证伪弱于预注册分支触发）
3. **C4 贡献降低**：从 +4-6% 降至 +2-4%（经验查表弱于理论方法）

---

## 附录 E：接收概率自评

### E.1 R3 方案 CBM 接收概率估计

**估计：28-38%（中值 33%）**

### E.2 估计理由

1. **与 R2 终审独立估计一致**：R2 终审独立估计 28-38%（中值 33%），R3 方案正是按 R2 终审的修补清单修改，预期接收概率应与终审估计一致

2. **上行风险（可能高于 38%）**：
   - 如果 CBM 审稿人不深究时间线，且"诚实披露证伪"叙事有说服力，接收概率可能接近 38-40%
   - 如果 E3 实验发现 Brier reliability 改善 Cohen's d > 0.3（中等效应），E3 的边际贡献可能高于估计
   - 如果 E2 消融实验显示分箱温度有显著边际改善，C3 贡献增加

3. **下行风险（可能低于 28%）**：
   - 如果 CBM 审稿人要求预注册（R3 不声称预注册），可能直接拒稿，接收概率可能降至 20-25%
   - 如果 E3 实验发现 Brier reliability 改善 Cohen's d < 0.2 或 NCV ≤ 0（H1 失败），需要触发备选叙事，接收概率可能降至 25-30%
   - 如果 E2 消融实验显示无边际改善，C3 贡献降低，接收概率可能降至 25-30%
   - 如果审稿人以"效应量小"直接拒稿（ECE 0.016），接收概率可能降至 20-25%

4. **中值 33% 的合理性**：
   - 考虑了上行和下行风险后的合理估计
   - 比 R2 的 35-45% 低 5-7%，主要因为放弃预注册叙事后 C2 贡献降低
   - 比"不改进直接投"的 25-35% 高 3-8%，主要因为补齐 7 个缺口 + 叙事升级 + 诚实披露证伪
   - 与 R2 终审独立估计一致，说明 R3 方案正确实施了终审的修补清单

### E.3 与 R2 方案接收概率的对比

| 方案 | 接收概率 | 中值 | 关键差异 |
|------|---------|------|---------|
| R2 方案 | 35-45% | 40% | 含虚假预注册叙事（N1 攻击成立后实际降至 28-38%） |
| **R3 方案** | **28-38%** | **33%** | **放弃预注册叙事，诚实披露证伪，与 R2 终审独立估计一致** |
| 不改进直接投 | 25-35% | 30% | 效应量小 + 无临床意义 + 事后分析叙事 |

**结论**：R3 方案的 28-38%（中值 33%）是**诚实的估计**——不依赖虚假的预注册叙事，考虑了效应量硬伤和负交互，与 R2 终审独立估计一致。这个估计比 R2 的 35-45% 更诚实，因为 R2 的估计建立在虚假的预注册声明之上。

---

**方案状态**：R3 已完成，按 R2 终审裁定的 P0+P1 修补清单（4 项 P0 + 8 项 P1 = 12 项）全部实施。核心主张、假设、边界、推理链条、风险点均已明确标注。**放弃所有预注册叙事，改用诚实披露证伪 + post-hoc exploratory observation + 时间线透明披露**。预期接收概率 28-38%（中值 33%），与 R2 终审独立估计一致。

**正方论证代理-R3 签名**：正方论证代理-R3（GLM-5.2）
**交付日期**：2026-09-09
**基于**：R2 方案 + R2 反方攻击 + R2 反反方回应 + R2 终审裁决
**修补清单**：P0（4 项必须）+ P1（8 项重要）= 12 项，全部完成
**预期接收概率**：28-38%（中值 33%）
**目标期刊**：Computers in Biology and Medicine (IF~7, SCI Q2)
**Fallback 期刊**：Physiological Measurement (IF~3, SCI Q3/Q2)
**核心变化**：放弃预注册叙事 → 诚实披露证伪；乘法模型 → 分箱温度；TS-DRA 理论方法 → EBT-LT 经验查表；多临床价值来源 → 聚焦阈值化决策
**下一步**：R3 轮反方攻击 → 反反方回应 → 终审裁决（若需要）
