# ECG校准修复边界研究 — 预注册实验协议 v2.0

> 本协议由五路独立对抗性审查（实验设计/统计方法/工程可复现性/文献novelty/Reviewer 2模拟）交叉验证后生成。
> 状态：**预注册草案**。投稿前应将本文件哈希存档至OSF等时间戳平台。

## 0. Novelty重定位（文献审查结论）

**不得声称**："首次在ECG上证明校准修复收益从内部到外部衰减"
——这是Ovadia et al. (NeurIPS 2019)已知结论的ECG复现，且Barandas 2023、Zhang 2022、Physiol Meas 2026已分别报道ECG上的现象。

**应声称**（三步链，每步都有剩余novelty空间）：
1. **参数级分解**：将校准修复收益的ID→OOD衰减分解为slope/intercept/prevalence三个可干预成分的贡献占比（ECG深度模型+跨数据集公开基准上无人做过"贡献占比"视角）
2. **可预测性**：用目标域无标签统计量（预测先验L1距离、logit分布统计量）预测修复收益保留率
3. **部署判据**：输出"移位类型 × 主导成分 × 推荐再校准策略"的可操作决策表，并在迁移矩阵留出集上验证判据的敏感度/特异度

**必须正面引用**（引言锚点）：Ovadia 2019, van Calster 2016/2019, Guo 2017, Kull 2019 (Dirichlet), Nixon 2019, Kumar 2019, Alexandari 2020, Lipton 2018 (BBSE), Wagner 2020 (PTB-XL), Strodthoff 2021。
**必须显式对比的最近邻**：Physiol Meas 2026 (RR-interval AF跨库校准，特征模型vs本文深度多标签)；medRxiv 2026 ICU calibration drift（slope保持/intercept漂移平行结论）；TransCal/PseudoCal/LaSCal（方法类上界）。

## 1. 术语纪律

- "recalibration"（非"calibration repair"）
- "transportability"（非"portability"）
- "dataset shift"必须细分为：covariate shift / prior probability shift / concept shift（Moreno-Torres 2012分类法），逐迁移对声明类型
- 拒用比值作主报告量："ΔECE = X [95% CI]，基线Y→修复后Z"格式；比值仅括号内出现

## 2. 数据与划分（防泄漏协议）

| 库 | 角色 | 划分 |
|---|---|---|
| PTB-XL v1.0.3 | 源/目标 | **官方10折**：folds 1-8训练 / fold 9校准 / fold 10内部测试（patient-stratified） |
| Chapman-Shaoxing | 源/目标 | 患者级分层 70/10/20，固定种子 |
| CPSC2018+2019 | 源/目标 | 患者级分层 70/10/20；**无HYP类→主分析降级{NORM,CD,STTC}子空间**，敏感性分析报告。HYP优先级记录**剔除并在STROBE流程图单列计数，不做重映射**；涉及CPSC的迁移对**两侧均按同子空间重算**（对称性） |
| （可选）Ningbo | 增加对数 | 同上 |

- **硬性断言脚本**：train/cal/test患者ID交集为空（进CI与复现仓库）
- 单标签优先级规则固定并做敏感性分析；多标签sigmoid作第二形式化
- STROBE式流程图：每库原始记录→映射后→排除→终样本，逐类计数
- 归一化统计量**只来自train split**；增广只作用于train

## 3. 移位剂量阶梯（BSPC叙事第一幕）——eval-only为主，控制计算预算

- **L0**：源test（ID基线）
- **L1**：跨库有向对，3库全排列=6对
- **L2**（**eval-time变换，不重训练**，Ovadia 2019同款惯例）：
  - 采样率 500→250→125 Hz（eval-time抗混叠降采样）
  - 导联 12→6→3→2→1（eval-time通道置零）
  - 噪声注入（PTB-XL Noise Stress Test DB: BWL/MA/EM）@ SNR {24,12,6,0,−6} dB
  - 增益 ×0.5 / ×2
  - **重训练验证点**：仅BiMamba×PTB-XL源×导联6档×5种子（30 runs）验证"eval-time移位结论与重训练模型一致"
- 外部性量化：逐导联功率谱KS检验/MMD报告库间信号分布距离

## 3.5 计算预算表（第二轮审查新增，防不可行设计）

| 项 | 规模 | 估计 |
|---|---|---|
| 基础训练 | 3架构×3库×5种子（固定划分） | 45 runs ≈ 3-5 GPU日 |
| 重训练验证点 | BiMamba×1库×4导联档×5种子 | 20 runs ≈ 1-2 GPU日 |
| S1主网格 | 6对×3架构×5种子×7主方法 | eval-only ≈ 2-4 GPU时 |
| L2阶梯 | 全eval-only | ≈ 4-8 GPU时 |
| S2小样本 | 4方法×3 n_cal×10重复×代表档 | ≈ 1.1万次拟合 ≈ 4-6 CPU时 |
| Bootstrap | 主检验/G: B=10,000；次要: B=2,000 | ≈ 8-12 CPU时 |
| **合计** | | **≈ 5-8 GPU日 + 1 CPU日**（单卡8GB投稿周期内可行）|

**方法池（M1-M13）**：主文7个（None/TS/per-class Platt/Isotonic/Dirichlet/Saerens EM/Oracle）+ 附录6个（Vector/Matrix scaling/CORAL/TTA/MC-Dropout±TS）。附录方法仅在PTB-XL源的2个代表对上跑。
- BBSE处理：单标签OvR下与Saerens EM同族，以Saerens代表，§5写明排除理由
- TTA定义：高斯噪声σ=0.005mV×8 + 时间移位±20ms×2，平均softmax

## 4. 模型与训练

- **3架构 × ≥5种子**：BiMamba（主）、1D-ResNet-34、InceptionTime
- BiMamba须报告与公开SOTA（AUROC macro ≈0.92-0.93）对齐；mambapy与官方kernel数值一致性测试（max|Δy|<1e-4）
- 训练协议：AdamW + cosine schedule + linear warmup + grad clip 1.0 + NaN防护
- **温度单一化**：主协议训练时T≡1冻结（learnable_temp=False已实施）；co-trained T作独立消融轨且不再post-hoc拟合
- **MC-Dropout协议**：BN冻结（已实施）；聚合=平均softmax概率；MC-Dropout与MC-Dropout+TS进方法表；T=20次前向平均**后**的概率上拟合TS
- 早停准则跨所有库/架构统一：val NLL（明示该选择对基线校准的影响）
- 显存可行性：patch-embedding下采样（/4）或d_model≤128；论文如实报告硬件

## 5. 校准方法库 × 三场景

方法全矩阵（R2命门：不跑全就是"没试对方法"的把柄）：
None / TS / per-class Platt / Vector scaling / Matrix scaling / Isotonic(OvR，报告拟合集大小) / Dirichlet / Saerens EM先验适配（无标签）/ CORAL+重校准 / TTA / MC-Dropout / **Oracle**（目标全量拟合=上界）

场景：
- **S1 零样本迁移**（主分析）：源val拟合→目标直接用
- **S2 本地小样本再校准**（临床手册）：目标域 n_cal ∈ {50,100,250,500,1000} 有标签样本，患者级抽样×20重复 → "标注预算-收益挽回"剂量曲线
- **S3 目标全量refit**（上界）

## 6. 终点定义（写死，禁止事后修改）

**主形式化**：单标签5类softmax；**主ECE=5类confidence SmoothECE**（无分箱偏差），classwise宏平均为次要视角。
**终点层级**：**主终点=G（唯一）**；ΔECE与R为关键次要。主检验只有一个，逐格比较全部进BH家族（家族大小=6对×3架构×15移位级）。

**主终点**：
- G = ECE_S1(目标) − ECE_oracle(目标)  【可挽回损失：区分"没东西可修"vs"修不动"】
  - **Oracle定义（防in-sample偏差）**：目标域cal split全量拟合、与所有方法同test集评估；每迁移格独立拟合
- ΔECE = ECE_raw − ECE_cal，患者级cluster bootstrap配对CI（`benefit_inference`）

**次要**：保留率R=ΔECE_ext/ΔECE_int（仅描述+敏感性检验）；NLL；classwise-ECE（宏平均，空类单列）；Brier Murphy分解（逐类二值化构造，单测断言恒等；跨库只比REL项）；Cox slope/intercept；预测/真实先验L1距离

**主检验（唯一，绝对量纲，与§1比值降级一致）**：
H0: ΔECE_ID − ΔECE_OOD = 0（患者级cluster配对bootstrap B=10,000，BCa；分层池化：strata=迁移对×架构）
log R仅作敏感性检验；ΔECE≤0的单元预注册处理：报告"修复有害"计数，不取log。

**次级家族**：BH-FDR q=0.05；其余标注exploratory只报CI
**Sanity**：全局TS后argmax逐位不变（已在train.py断言）

**预设解读（prevalence匹配实验，支柱实验）——TOST三段式，数值边界写死**：
- 匹配启用条件：匹配后类边际先验最大绝对差≤0.02，否则报"匹配失败"分支，不参与解读
- **衰减保留** = R的95%CI下界 ≥ 0.7
- **衰减消失** = CI包含1 且 点估计 ≥ 0.85
- **部分衰减** = 其余情形
- 匹配=按类边际先验患者级子采样；联合匹配不可行时报告匹配残差

## 7. 统计协议

- 重采样单元=患者（cluster bootstrap）；主检验/G用B=10,000 BCa；次要终点B=2,000百分位
- 两层联合bootstrap：val重采样→拟合T→test重采样→指标（T不确定性传入CI）
- **划分方差分量**：仅在Chapman/CPSC（可重划分）以5个患者级重划分×BiMamba估计；PTB-XL以官方折为主划分（与§2一致），folds 1-8内部重划分仅作敏感性——解决官方折与"≥5划分"的冲突
- 点估计=全样本统计量，**永不报bootstrap均值**
- ECE估计量：主=SmoothECE（已实施并修正）；敏感性=等宽10+等频15双报；MCE仅等频+bin容量≥50
- McNemar精确二项版，阈值只在val搜；DeLong仅跨模型比较
- 功效：**pilot=1个迁移对×1架构×2种子的独立预实验（结果不进主检验报告）**，估Var(log ΔECE) → n=(z_.975+z_.8)²·Var/d²，逐L2级别报告最小可行n

## 8. 机制分解验证（三条腿，缺一即撤回"机制"措辞）

1. **数学声明**：Murphy分解=精确恒等式（OvR逐类构造）；三成分归因=反事实替换可加近似，**交互残差显式报告**
2. **合成注入**：27格全因子（slope∈{0.5,1,2}×intercept∈{−1,0,1}×prevalence×{0.5,1,2}）。**门槛仅施加于预定义可辨识区**（判定规则：Fisher信息行列式>阈值τ，τ预注册），恢复MAPE<10%为门槛；纠缠区仅报告误差图，不设门槛
3. **可辨识性**：合成环境验证三成分纠缠区域；分解归因带bootstrap CI，CI重叠不得排序"主因"；cross-fitting（OOD折半验证分解的解释力）

## 8.5 可预测性实验（novelty三步链的中段，缺失即链断）

**特征**（全部目标域无标签或低成本可估）：预测先验L1距离、logit一/二阶矩、信号级KS/MMD距离（§3）、移位剂量档
**模型**：岭回归（特征≤5，防过拟合）
**评估**：leave-one-transfer-pair-out，报告LOO R² + bootstrap CI
**预注册失败分支（写死）**：若LOO R²的95%CI上界<0.5 → 论文降级为两步链（分解+判据），判据改称"经验查表"，**禁止事后追认预测性**
**样本量边界**：可用迁移单元≈90-200个且高度相依（同源模型衍生），LOO R²的CI必须如实报告宽度；R²<0.3不得在摘要提"可预测"

## 9. 临床价值落点（缺此节BSPC必压分）

1. 判据=伪代码/流程图：输入（本地标注预算）→测量（可估量）→决策（直接部署修复 / 买n个标注重校准 / 拒绝部署）
2. **判据自验证（操作定义写死）**：
   - "安全" := 修复后macro SmoothECE ≤ ε 且 ΔECE的95%CI下界>0（ε=0.05预注册）
   - 验证单元=迁移条件级；每移位类型留1个剂量档作判据专用留出集（写死）
   - 报告判据预测"可安全部署"的敏感度/特异度
3. 决策曲线分析（net benefit）：按NORM与STTC两类分别报告；修复 vs 不修复 vs 全体阳性，各风险阈值
4. "何时可信任"从口号变成算术：给定移位类型和标注预算，查表得策略

## 10. 交付物清单

- T1 数据/映射表/流程图（映射表逐条给文献依据+映射敏感性分析）
- T2 主网格：6对×3架构×12方法×[G, ΔECE, R]全部带CI（含不利结果，无挑选）
- F1 移位剂量-反应曲线；F2 reliability diagrams（ID/OOD × raw/TS/oracle，逐类+置信带）；F3 三成分贡献堆叠图；F4 S2标注预算-挽回曲线；F5 合成恢复误差曲线；F6 方法选择热图（判据）
- 预注册：OSF时间戳（迁移矩阵、主结局、统计方案）
- 复现仓库：代码+种子+官方划分加载器+映射表+一键脚本+环境锁；ECE实现与netcal/sklearn数值对照<1e-6
- **映射敏感性分析（操作化）**：对每个歧义映射决策生成替代变体，重跑1个代表迁移对全管线；稳健性判据=G跨对排序Kendall τ≥0.8且主检验结论不变，否则在讨论中降级对应claim
- **S2展开**：估计量G(n_cal)=ECE_S1−ECE_S2(n_cal)；重复间方差经两层cluster bootstrap进CI；预注册预期：isotonic/Matrix scaling在n_cal≤100失效（参数过多）

## 11. 已实施的P0/P1代码修复（第一、二轮对抗审查产物）

| 轮次 | 修复 | 位置 | 状态 |
|---|---|---|---|
| R1 | train.py启动地雷（不存在kwargs） | train.py | ✅ R2验证通过 |
| R1 | torch.load weights_only | train.py | ✅ R2验证通过 |
| R1 | 全局种子+合成数据固定缓存 | train.py | ✅ R2实测bitwise一致 |
| R1 | 温度单一化（T≡1训练） | ecg_classifier.py | ✅ R2验证grad=None |
| R1 | fit_temperature 2D分支 | train.py | ✅ R2 spy验证 |
| R1 | train/val/cal/test四分割 | train.py | ✅ R2验证无重叠 |
| R1 | 梯度裁剪+NaN防护 | train.py | ✅ |
| R1 | drop_last=False + loss按样本加权 | train.py | ✅ |
| R1 | MC-Dropout冻结BN | ecg_classifier.py | ✅ R2实测Δ=0.000e+00 |
| R1 | bootstrap点估计+rng+cluster | calibration.py | ✅ R2配对CI更窄验证 |
| R1 | mambapy入requirements | requirements.txt | ✅ |
| R1 | argmax不变sanity断言 | train.py | ✅ |
| **R2** | **温度拟合误用test标签（反例-1，R1修复引入）** | train.py | ✅ 已修：只用cal标签 |
| **R2** | **smooth_ece实现错误（反例-2）** | calibration.py | ✅ 已重写：数据点处核加权+带宽n^(-0.2)+chunking |
| **R2** | **benefit_inference未接线+n_bootstrap=0崩溃（反例-3）** | calibration.py+train.py | ✅ 已接入主报告+边界分支 |

## 12. P1实施状态（第三轮建造-攻击-修复循环产物）

| 组件 | 建造者交付 | 攻击者发现 | 修复状态 |
|---|---|---|---|
| **数据加载模块** (src/data/) | mapping 190码表（44条官方语句逐字核对）+患者级划分+泄漏断言+Dataset，35测试 | FATAL-1管线断裂（train.py未接入）；MAJOR×4（记录级泄漏静默/NaN患者ID/统计量无守卫/NaN信号传播）；MINOR×6 | 防线类全部修复+18回归测试（53测试过）；**FATAL-1集成层待真实数据下载后接入**（preprocess需增patient_id列+双标签列） |
| **校准方法库** (calibration_methods.py) | isotonic/vector/matrix/dirichlet/saerens/oracle/ts/platt+注册表，24测试 | 攻击评分38/100：**platt fit/apply脱节**（logit vs odds）、matrix静默返回垃圾、saerens零区分力坍缩到one-hot、注册表缺saerens、dirichlet空类列错位、isotonic守卫off-by-one | 全部修复：platt往返一致性测试、matrix/saerens失败返回None+warn、注册表9方法全、dirichlet按classes_重排、isotonic真实自由度报告（25测试过） |
| **27格分解验证** (decomposition.py+validate) | 27/27过门槛 | 攻击评分52/100：**27格退化**（prev轴零影响）、**n=500门槛57%失败**、顺序依赖119%、残差恒0掩盖真实交互、FI权重错配假阳性、多分类静默垃圾 | 全部修复：重采样后恢复+King-Zeng校正（实证b̂ 0.506≈真值0.5）、样本量自适应门槛（gate(n)=max(10%,3σ)、小样本信息模式）、6排列+Shapley归因+析因交互I_sb/I_sπ/I_bπ/I_3way、FI基线权重（det∝s²实测）、入口校验raise |

**最终状态**：119/119测试通过；train.py端到端跑通；分解验证在预注册n=20000全部PASS。

## 13. 剩余工作（真实数据阶段）

1. **下载PTB-XL/Chapman/CPSC** → 补集成层（攻击者1 FATAL-1）：preprocess增patient_id、train.py接入patient_wise_split+assert_no_leakage+MAP_TO_5SUPERCLASS
2. ResNet-1D + InceptionTime基线（§4三架构）
3. §8.5可预测性实验（岭回归+LOO-pair）
4. S2小样本剂量曲线runner（§3.5预算表）
5. 判据流程图 + 留出验证（§9操作定义）
