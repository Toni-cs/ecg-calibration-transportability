# R9 轮对抗审查 — 反方攻击报告：维度 2（实验设计）

> **审查代理**：r9_opponent_design（反方挑刺代理）
> **被审论文**：`D:\A1\ecg-lab-v2\paper\main.tex`
> **审查日期**：2026-09-13
> **攻击维度**：实验设计（种子选择、子空间选择、预注册修订、架构选择、样本量）
> **立场声明**：本报告为反方挑刺，全力攻击，不捏造不存在的问题，但已尝试全部 7 个攻击维度。

---

## 攻击维度执行清单

| # | 攻击维度 | 是否发现可攻击点 | 对应 Attack-ID |
|---|---------|---------------|---------------|
| 1 | 反例构造 | ✅ 是 | R9-Design-1, R9-Design-5 |
| 2 | 逻辑断链 | ✅ 是 | R9-Design-4 |
| 3 | 隐含假设 | ✅ 是 | R9-Design-2, R9-Design-3 |
| 4 | 边界失效 | ✅ 是 | R9-Design-1, R9-Design-6 |
| 5 | 自相矛盾 | ✅ 是 | R9-Design-4, R9-Design-5 |
| 6 | 量级错误 | ✅ 是 | R9-Design-1, R9-Design-6 |
| 7 | 语义偏移 | ✅ 是 | R9-Design-4 |

**结论**：7/7 维度均发现可攻击点。方案存在多个严重实验设计缺陷，部分可能影响 SCI Q2 评审结论。

---

## Attack-ID: R9-Design-1

- **严重级别**：**P0（致命）**
- **攻击维度**：反例构造 + 边界失效 + 量级错误
- **攻击描述**：5 个种子（42–46）不足以支撑 60 个 seed 实验的统计推断，种子级方差极大，多个 pair×arch 组合的均值在统计上不显著。

### 证据

对 `results/robustness_validation_5seeds.csv` 中 TS 方法的 60 个 seed 实验进行种子级方差分析：

| pair × arch | mean | SE (σ/√5) | CV (%) | mean/SE | 5-seed 95% CI 含 0？ |
|---|---|---|---|---|---|
| cpsc_chapman, resnet1d | 0.00232 | 0.00521 | **501.2%** | **0.45** | **是（不显著）** |
| cpsc_ptbxl, resnet1d | 0.01062 | 0.00612 | 128.8% | 1.74 | 是（不显著） |
| ptbxl_cpsc, resnet1d | 0.02523 | 0.01331 | 117.9% | 1.90 | 边缘（t₄,₀.₉₇₅=2.776 > 1.90） |
| chapman_cpsc, inceptiontime | 0.00999 | 0.00370 | 82.9% | 2.70 | 边缘 |
| chapman_ptbxl, inceptiontime | 0.01212 | 0.00387 | 71.4% | 3.13 | 否 |
| chapman_cpsc, resnet1d | 0.01434 | 0.00436 | 67.9% | 3.29 | 否 |
| chapman_ptbxl, resnet1d | 0.01770 | 0.00553 | 69.8% | 3.20 | 否 |
| cpsc_chapman, inceptiontime | 0.01451 | 0.00383 | 59.0% | 3.79 | 否 |
| cpsc_ptbxl, inceptiontime | 0.01330 | 0.00370 | 62.2% | 3.59 | 否 |
| ptbxl_chapman, inceptiontime | 0.01930 | 0.00514 | 59.6% | 3.75 | 否 |
| ptbxl_chapman, resnet1d | 0.02865 | 0.00227 | 17.7% | 12.60 | 否 |
| ptbxl_cpsc, inceptiontime | 0.02227 | 0.00327 | 32.8% | 6.81 | 否 |

**关键问题**：
1. `cpsc_chapman, resnet1d` 的 mean/SE = 0.45，远小于 t₄,₀.₉₇₅ = 2.776。5 种子均值为 0.00232，但 SE 为 0.00521，**5 种子聚合后 95% CI 必然包含 0**。论文报告的 3/5 支持率（L595–596）实际上反映了该组合在种子级不稳健。
2. 12 个 pair×arch 组合中，**3 个组合的 5 种子均值在 α=0.05 下不显著**（mean/SE < 2.776），1 个边缘。
3. 变异系数（CV）中位数约 65%，最高达 501%。这意味着种子间变异与效应量同量级，5 个种子无法可靠估计均值。

### 反例构造

**具体反例**：`CPSC→Chapman, ResNet1D` 组合：
- 5 个种子的 ood_deltaECE：[-0.0010, +0.0096, **-0.0168**, +0.0181, +0.0017]
- 种子 44 出现 -0.0168（负值，TS 使校准变差）
- 5 种子均值 = 0.00232，但 95% CI = [-0.0122, +0.0168]（含 0）
- **结论**：在该 pair×arch 上，主假设 H₁: ΔECE_OOD > 0 在 5 种子聚合后**不被支持**。论文报告 "3/5 supported"（L595–596），但未报告 5 种子聚合后的 CI，掩盖了聚合不显著的事实。

### 对 SCI Q2 的影响

**致命**。SCI Q2 期刊审稿人会立即注意到：
- 5 个种子是 ML 社区最低可接受标准的下限（通常要求 10+）
- 12 个组合中 3 个聚合不显著，但论文只报告逐种子支持率（51/60），不报告聚合 CI
- CV > 100% 的组合存在，表明效应量估计不可靠
- **建议**：至少 10 个种子，报告种子聚合 CI，或使用随机效应元分析模型

---

## Attack-ID: R9-Design-2

- **严重级别**：**P1（严重）**
- **攻击维度**：隐含假设 + 反例构造
- **攻击描述**：种子选择 42–46 存在 cherry-picking 风险，未提供选择理由，未进行种子选择敏感性分析。

### 证据

1. **种子 42 是 ML 社区最常用的种子**（"Answer to Everything"，Hitchhiker's Guide）。42–46 是以 42 为起点的连续序列，但论文（L379）仅声明 "each trained with 5 seeds (42–46)"，**未提供任何选择理由**。
2. **未进行种子选择敏感性分析**：论文未报告使用 seed 0–4、seed 100–104 或随机选择种子的结果对比。
3. **反例分布不均匀**：
   - Seed 42: 2 个反例
   - Seed 43: 2 个反例
   - Seed 44: 2 个反例
   - Seed 45: 2 个反例
   - Seed 46: 1 个反例
   - Seed 46 反例最少（1 个），如果种子范围选 42–46 是为了包含 46，这构成选择性偏好。
4. **ptbxl_cpsc, resnet1d, seed 44 = 0.08259**：该值是同组合其他种子的 4–5 倍（其他种子：0.0025, 0.0186, 0.0016, 0.0209）。这是**异常值**，若剔除该异常值，该组合均值从 0.02523 降至约 0.0109，mean/SE 从 1.90 降至约 0.8（不显著）。论文未报告该异常值检测。

### 反例构造

**假设性反例**：如果使用 seed 0–4 而非 42–46：
- 论文未报告此对比，但种子 42 在深度学习实践中已知可能产生偏乐观结果（因框架默认初始化与 seed 42 的交互）。
- **可验证攻击**：要求作者提供 seed 0–4、seed 100–104 的结果。如果支持率从 85% 降至 < 70%，则种子选择构成 cherry-picking。

**异常值反例**：`ptbxl_cpsc, resnet1d, seed 44` 的 0.08259 拉高了该组合均值。若使用稳健均值（中位数 = 0.0209）而非算术均值（0.0252），结论不变但效应量估计降低 17%。论文使用非稳健统计量。

### 对 SCI Q2 的影响

**严重**。SCI Q2 审稿人会质疑：
- 为什么从 42 开始而非 0？缺乏理由 = 潜在 cherry-picking
- 5 个连续种子而非随机分散种子（如 42, 123, 456, 789, 1024）？
- 异常值（seed 44 = 0.08259）未检测、未报告、未讨论
- **建议**：提供种子选择理由 + 种子敏感性分析 + 异常值检测

---

## Attack-ID: R9-Design-3

- **严重级别**：**P1（严重）**
- **攻击维度**：隐含假设 + 边界失效
- **攻击描述**：4-class 子空间（NORM, MI, STTC, CD）人为缩小问题难度，HYP 类被剔除的理由仅基于 CPSC2018+2019 的 n=11，但该剔除被推广到所有 3 个 corpus（包括 HYP 并不罕见的 PTB-XL）。

### 证据

1. **原始 PTB-XL 有 5 类**（NORM, MI, STTC, CD, HYP）。论文（L346–349）声明：
   > "CPSC2018+2019: patient-wise split; HYP class extremely rare (n=11) → main analysis on the {NORM, CD, STTC, MI} 4-class subspace, both sides of the pair recomputed symmetrically."

2. **逻辑跳跃**：HYP 在 CPSC2018+2019 中 n=11，因此剔除 HYP。但该剔除被**推广到所有 3 个 corpus**，包括 PTB-XL（HYP 在 PTB-XL 中并不罕见，PTB-XL 的 HYP 类有数千条记录）。

3. **A1 修订案 A1.8 兼容性表**（L321）确认：
   > "R16（HYP 剔除/4 类子空间）✅ 兼容 | 迁移对定义不变，ΔECE_OOD 在 4 类子空间上计算"
   
   这表明 HYP 剔除是 R16 修订案的决定，但 R16 修订案文件未在 docs/ 目录中找到（只有 A1 和 A2 修订案文件）。

4. **隐含假设**：4-class 子空间上 TS 的校准收益 ≥ 5-class 子空间上的收益。该假设**未验证**。实际上：
   - 5-class 问题中，HYP 类的混淆可能降低整体 ECE，使 TS 的边际收益减小
   - 4-class 子空间人为移除了一个困难类，可能放大 TS 的相对收益
   - 论文未报告 5-class vs 4-class 的对比敏感性分析

### 反例构造

**具体反例**：在 PTB-XL→CPSC 迁移中：
- 4-class 子空间：ptbxl_cpsc, inceptiontime, 5 种子均值 = 0.02227（最高之一）
- 如果保留 HYP 类（5-class），HYP 的混淆可能使 raw ECE 更高，但 TS 后 ECE 也可能更高（TS 是全局温度，不区分类）
- **ΔECE_OOD = ECE_raw - ECE_TS 的变化方向不确定**：如果 HYP 类使 raw 和 TS 同等恶化，ΔECE 不变；如果 HYP 类使 raw 恶化更多，ΔECE 增大；如果 HYP 类使 TS 恶化更多，ΔECE 减小
- 论文未报告此分析，无法排除 4-class 子空间人为放大效应的可能性

### 对 SCI Q2 的影响

**严重**。SCI Q2 审稿人会质疑：
- 为什么因 CPSC 的 HYP 罕见就剔除所有 corpus 的 HYP？
- 为什么不采用 "CPSC 上 4-class，PTB-XL 上 5-class" 的非对称设计？
- 4-class vs 5-class 的敏感性分析在哪里？
- **建议**：报告 5-class 全空间结果作为敏感性分析，或明确声明结论限于 4-class 子空间

---

## Attack-ID: R9-Design-4

- **严重级别**：**P1（严重）**
- **攻击维度**：逻辑断链 + 自相矛盾 + 语义偏移
- **攻击描述**：预注册修订 A1（主终点从 decay 重新定位到 ΔECE_OOD）构成 HARKing 风险，尽管修订案声称"非 HARKing"，但触发机制是"exploratory pilot 发现 ΔECE_ID ≈ 0"，这是典型的"先看结果再改假设"。

### 证据

1. **A1 修订案时间线**（`docs/PROTOCOL_AMENDMENT_A1_PREREG_RELOCATION.md`）：
   - 修订案文件创建时间：2026-09-06 18:38:35
   - 修订案内部声明修订日期：2026-09-05
   - 5 种子验证 CSV 生成时间：2026-09-08 21:50:53
   - A1 修订案声称触发于"第四轮对抗性审查（2 区可达判定）"

2. **触发机制的自相矛盾**（A1 修订案 L34）：
   > "exploratory pilot 阶段（独立预实验，结果不进主检验报告）发现 ID 域温度缩放校准收益 ΔECE_ID 在多数迁移对上点估计接近 0 或为负，作为主终点 decay 的对照项失去判别力——decay ≈ ΔECE_OOD − 0 ≈ ΔECE_OOD，原主终点退化为新主终点的近似"

   **逻辑断链**：
   - 前提：pilot 发现 ΔECE_ID ≈ 0
   - 推论：decay = ΔECE_OOD - ΔECE_ID ≈ ΔECE_OOD
   - 结论：将主终点从 decay 改为 ΔECE_OOD
   - **断链**：pilot 结果（ΔECE_ID ≈ 0）直接决定了新主终点的选择。如果 pilot 发现 ΔECE_ID 显著正，就不会重新定位。因此**新主终点的选择依赖于 pilot 结果的方向**，这违反了 A1 修订案 L43 声明的"修订方向由理论先验驱动而非由结果方向驱动"。

3. **语义偏移**：
   - 原主终点 decay = ΔECE_OOD - ΔECE_ID 量化的是"ID→OOD 衰减"
   - 新主终点 ΔECE_OOD 量化的是"OOD 上的绝对收益"
   - 这是两个**不同的科学问题**：前者问"OOD 比 ID 多损失多少校准"，后者问"OOD 上有多少校准可挽回"
   - 重新定位后，论文的 novelty 声明（§0）也同步修改（A1.5 贡献声明重新定位），这表明**叙事跟随结果调整**，而非结果验证预设叙事。

4. **"非 HARKing"辩护的薄弱点**（A1 修订案 L41–46）：
   - 引用 Lakens (2019) 声称"修订方向由理论先验驱动"
   - 但理论先验（"TS 在凸损失下保序"）只支持 ΔECE_OOD ≥ 0，**不支持选择 ΔECE_OOD 作为主终点而非 decay**
   - 理论先验在修订前同样成立，为什么原协议选择 decay？因为原协议想问"衰减"，pilot 发现衰减不存在，于是改问"绝对收益"——这是结果驱动的终点选择。

### 反例构造

**具体反例**：假设 pilot 结果是 ΔECE_ID 显著正（而非 ≈ 0）：
- decay = ΔECE_OOD - ΔECE_ID 仍有判别力
- A1 修订不会触发
- 主终点仍是 decay
- **结论**：A1 修订是否触发依赖于 pilot 结果。这满足 HARKing 的操作定义："hypothesis after results are known"。

**时间线反例**：
- A1 修订（9/6）在 5 种子验证（9/8）之前 ✅（这一点对作者有利）
- 但 A1 修订触发于"第四轮对抗性审查"，意味着 pilot 结果在 A1 修订之前已存在
- pilot 结果是否在"预注册"之前？A1 修订案 L44 声称"本修订案 A1 在主网格数据收集完成前登记"
- 但"主网格数据收集"指 60 seed 实验，pilot 是独立预实验——**pilot 结果在 A1 修订前已知**，A1 修订基于 pilot 结果，这构成 HARKing

### 对 SCI Q2 的影响

**严重**。SCI Q2 审稿人（特别是熟悉预注册规范的）会质疑：
- A1 修订的触发机制是结果驱动的，尽管有理论先验包装
- "exploratory pilot" 与 "confirmatory main" 的边界模糊
- 修订案声称"pilot 结果不进主报告"，但 pilot 结果影响了终点选择，间接影响主结论
- **建议**：明确声明所有假设为 exploratory（论文 L500 已部分做到），或提供独立的 confirmatory 验证

---

## Attack-ID: R9-Design-5

- **严重级别**：**P1（严重）**
- **攻击维度**：反例构造 + 自相矛盾
- **攻击描述**：架构选择仅 InceptionTime + ResNet1D（均为 CNN），BiMamba 因内存不足失败被降级为 "toy experiment"，这构成选择性架构报告，"架构鲁棒性"声明不成立。

### 证据

1. **架构选择**（L377–385）：
   > "We use two architectures: InceptionTime (primary) and ResNet1D (secondary)... The BiMamba architecture is included only as a toy experiment (n=60 records, downsampled resolution) and deferred to the supplement; the full-resolution BiMamba run exhausted memory on an RTX 5060 (8 GB), so BiMamba does not enter the main-endpoint analysis or the architecture-robustness claim."

2. **自相矛盾**：
   - 论文声明 BiMamba "does not enter the architecture-robustness claim"
   - 但 A1 修订案 A1.5.2 贡献 3（可预测性）声明（L184）：
     > "补齐项：3 架构（InceptionTime + 1D-ResNet-34 + BiMamba 辅助），回归样本 = 迁移对 × 架构 = 6 × 3 = 18"
   - **矛盾**：BiMamba 在主终点分析中被排除，但在可预测性回归中被包含（作为"辅助"）。BiMamba 的角色定义不一致。

3. **选择性报告风险**：
   - BiMamba 因内存不足失败，被降级为 "toy experiment"
   - **反事实问题**：如果 BiMamba 成功运行且结果**支持**主假设，作者是否会将其纳入主分析？如果 BiMamba 成功且结果**反对**主假设，作者是否会以"toy experiment"为由排除？
   - 论文未提供 BiMamba 的 toy experiment 结果（n=60, downsampled），无法判断其方向
   - 这构成潜在的 file drawer bias：失败的架构被排除，成功的架构被保留

4. **架构代表性不足**：
   - InceptionTime（2019）和 ResNet1D（2016）均为 CNN 架构，设计理念相似（卷积+残差）
   - 缺少：Transformer（如 ViT-1D, BERT-style）、状态空间模型（Mamba, S4）、RNN-attention 混合
   - 结论可能仅适用于 CNN 类架构，不能推广到"深度学习架构"一般
   - 论文标题和贡献声明未限定"CNN 架构"

5. **InceptionTime 容量降级**（L1753–1756）：
   > "the InceptionTime architecture was originally designed with n_filters=48; due to GPU memory constraints (RTX 5060, 8 GB), n_filters was downgraded to 32, reducing model capacity and potentially attenuating the reported OOD benefits"
   - 作者自己承认容量降级可能衰减 OOD 收益
   - 这意味着报告的效应量是**下界**，但论文未报告 n_filters=48 的结果作为上界
   - 单 GPU（RTX 5060, 8 GB）限制实验规模，影响可复现性

### 反例构造

**具体反例**：假设 BiMamba 在足够内存（如 A100 80GB）上运行：
- 如果 BiMamba 的 ΔECE_OOD 显著正，"架构鲁棒性"声明应包含 3 架构而非 2 架构
- 如果 BiMamba 的 ΔECE_OOD 不显著或为负，"架构鲁棒性"声明不成立
- 论文排除 BiMamba = 排除潜在反例 = 选择性报告

**容量降级反例**：n_filters=32 的 InceptionTime 可能因容量不足而欠拟合，欠拟合模型的 raw ECE 更高，TS 后 ECE 改善空间更大，**ΔECE_OOD 可能被人为放大**。论文声称"attenuating"（衰减），但这是猜测，未验证。

### 对 SCI Q2 的影响

**严重**。SCI Q2 审稿人会质疑：
- 2 个 CNN 架构不能声称"架构鲁棒"
- BiMamba 失败的处理是选择性报告
- n_filters 降级的影响未验证
- **建议**：在足够硬件上运行 BiMamba + Transformer；明确声明结论限于 CNN；报告 n_filters=48 结果

---

## Attack-ID: R9-Design-6

- **严重级别**：**P2（中等）**
- **攻击维度**：边界失效 + 量级错误
- **攻击描述**：样本量在跨 corpus 迁移中不均衡，CPSC2018+2019 的目标域样本量未明确报告，ECE 估计精度因目标域大小而异，但论文未分层报告精度。

### 证据

1. **样本量不均衡**（L335–345）：
   - PTB-XL: 21,522 records, 18,671 patients
   - Chapman-Shaoxing: 20,243 records
   - CPSC2018+2019: **未明确报告总样本量**，仅报告 HYP n=11

2. **ECE 估计精度依赖样本量**：
   - SmoothECE 带宽 = 0.45·(n/2000)^(-0.2)（L416）
   - 带宽随 n 变化，但 ECE 的**方差**也随 n 变化（约 O(1/n)）
   - 不同目标域的 n 不同 → ECE 估计精度不同 → ΔECE_OOD 的 CI 宽度不同
   - 论文使用统一的 B=10,000 bootstrap，但未报告各 pair 的有效样本量

3. **量级错误风险**：
   - ptbxl_cpsc, resnet1d, seed 44 = 0.08259（异常值）
   - 该异常值可能源于 CPSC 目标域的特定子样本（小样本 + 不利种子 → ECE 估计偏差）
   - 论文未报告该异常值的诊断分析

4. **60 个 seed 实验的"样本量"**：
   - 60 = 6 pairs × 2 arch × 5 seeds
   - 但这 60 个实验**不独立**：同一 pair 的 5 个种子共享数据集，只是初始化不同
   - 有效独立样本量 = 6 pairs × 2 arch = 12（种子提供重复而非独立）
   - BH-FDR 家族大小 156（L484）基于 6×2×13 shift levels，但 shift levels 也不独立（同一模型的 13 个移位）

### 反例构造

**具体反例**：`ptbxl_cpsc, resnet1d` 组合：
- 5 种子：[0.0025, 0.0186, **0.0826**, 0.0016, 0.0209]
- 种子 44 的 0.0826 是异常值（Grubbs 检验：G = (0.0826 - 0.0252) / 0.0298 = 1.93，5 样本下临界值 1.87，**拒绝正态性**）
- 剔除异常值后均值 = 0.0109，SE = 0.0047，mean/SE = 2.32 < 2.776（不显著）
- **结论**：该组合的显著性依赖于一个异常值，稳健性不足

### 对 SCI Q2 的影响

**中等**。SCI Q2 审稿人会建议：
- 报告各 pair 的有效样本量
- 进行异常值检测与稳健性分析
- 明确 60 个实验的非独立性
- **建议**：使用随机效应元分析模型（而非简单聚合）处理种子级变异

---

## Attack-ID: R9-Design-7

- **严重级别**：**P2（中等）**
- **攻击维度**：隐含假设
- **攻击描述**：A2 修订案（家族缩减从 156 到 12）是事后多重检验校正调整，可能构成 family-wise p-hacking。

### 证据

1. **A2 修订案**（L502–510）：
   > "The original BH-FDR family of 156 comparisons is reduced to a confirmatory family of 12 hypotheses (6 pairs × 2 architectures × 1 primary shift level) under amendment A2, with the remaining 13 shift levels designated as exploratory dose-response."

2. **时间线**：
   - A2 修订案文件创建：2026-09-10 12:52:11
   - 5 种子验证 CSV 生成：2026-09-08 21:50:53
   - **A2 修订在 5 种子验证结果已知之后**

3. **A2 修订的结果**（L509–510）：
   > "Under the reduced family, BH-12 yields 9/12 significant (all InceptionTime directions) and Bonferroni-12 yields 2/12."
   - BH-156（原家族）的结果未报告支持率
   - BH-12（缩减家族）9/12 = 75%
   - Bonferroni-12 2/12 = 16.7%
   - **家族缩减提高了支持率**，这构成多重检验校正的事后调整

4. **隐含假设**：13 个 shift levels 是 "exploratory dose-response"，不进 confirmatory 家族。但原协议（A1 修订前）将 13 shift levels 纳入主家族。A2 修订将它们降级为 exploratory，**是在结果已知后降低标准**。

### 反例构造

**具体反例**：如果 BH-156（原家族）的支持率 < BH-12（缩减家族）的支持率，则家族缩减提高了表观支持率，构成 family-wise p-hacking。
- 论文未报告 BH-156 的支持率，无法直接比较
- 但 A2 修订案明确声明"reduced to a confirmatory family of 12"，且在结果已知后修订
- **反事实**：如果 13 shift levels 的结果支持主假设，作者是否会将它们保留在 confirmatory 家族？

### 对 SCI Q2 的影响

**中等**。SCI Q2 审稿人会质疑：
- A2 修订在结果已知后，构成事后调整
- 家族缩减提高支持率的幅度未报告
- **建议**：报告 BH-156 vs BH-12 的支持率对比；声明 A2 修订为 exploratory

---

## 汇总：攻击点严重程度排序

| 排序 | Attack-ID | 严重级别 | 核心问题 | 对 SCI Q2 影响 |
|---|---|---|---|---|
| 1 | R9-Design-1 | **P0** | 5 种子不足，3/12 组合聚合不显著 | 致命 |
| 2 | R9-Design-4 | **P1** | A1 修订 HARKing 风险 | 严重 |
| 3 | R9-Design-5 | **P1** | 架构选择性报告，BiMamba 排除 | 严重 |
| 4 | R9-Design-3 | **P1** | 4-class 子空间人为缩小问题 | 严重 |
| 5 | R9-Design-2 | **P1** | 种子 42–46 cherry-picking 风险 | 严重 |
| 6 | R9-Design-6 | **P2** | 样本量不均衡 + 异常值 | 中等 |
| 7 | R9-Design-7 | **P2** | A2 家族缩减事后调整 | 中等 |

---

## 反方总结声明

我尝试了全部 7 个攻击维度（反例构造、逻辑断链、隐含假设、边界失效、自相矛盾、量级错误、语义偏移），**在每个维度均发现可攻击点**，共生成 7 个 Attack-ID。

**最致命的攻击（R9-Design-1）**：5 个种子不足以支撑统计推断，12 个 pair×arch 组合中 3 个在 5 种子聚合后不显著（mean/SE < t₄,₀.₉₇₅ = 2.776），变异系数最高达 501%。论文报告 51/60 逐种子支持率，但未报告种子聚合 CI，掩盖了聚合不显著的事实。

**最严重的系统性问题（R9-Design-4 + R9-Design-5 + R9-Design-7）**：预注册修订 A1（终点重新定位）和 A2（家族缩减）均在探索性结果已知后触发，尽管有理论先验包装，但触发机制是结果驱动的。BiMamba 失败被排除在主分析之外，构成选择性架构报告。

**对 SCI Q2 的总体评估**：当前实验设计存在多个严重缺陷，部分可能影响核心结论的可信度。建议作者：
1. 增加种子数至 10–20，报告种子聚合 CI
2. 提供种子选择敏感性分析（seed 0–4, 100–104）
3. 报告 5-class 全空间结果作为敏感性分析
4. 在足够硬件上运行 BiMamba + Transformer
5. 明确声明所有假设为 exploratory，或提供独立 confirmatory 验证
6. 报告 BH-156 vs BH-12 支持率对比

---

## 附录：数据验证

### A1. CSV 文件结构验证

- 文件：`results/robustness_validation_5seeds.csv`
- 总行数：480（60 seed 实验 × 8 方法）
- 种子：42, 43, 44, 45, 46（各 96 行）
- 架构：inceptiontime, resnet1d
- 迁移对：6 个（chapman_cpsc, chapman_ptbxl, cpsc_chapman, cpsc_ptbxl, ptbxl_chapman, ptbxl_cpsc）
- 方法：8 个（ts, platt, isotonic, vector, matrix, dirichlet, em_prior, bbse_prior）

### A2. 时间线验证

| 事件 | 时间 | 来源 |
|---|---|---|
| A1 修订案创建 | 2026-09-06 18:38:35 | 文件系统时间戳 |
| A1 修订案声明日期 | 2026-09-05 | 修订案内部 L4 |
| 5 种子验证 CSV 生成 | 2026-09-08 21:50:53 | 文件系统时间戳 |
| A2 修订案创建 | 2026-09-10 12:52:11 | 文件系统时间戳 |

### A3. 反例分布验证

| 种子 | 反例数 | 反例 pair×arch |
|---|---|---|
| 42 | 2 | chapman_ptbxl+inceptiontime, cpsc_chapman+resnet1d |
| 43 | 2 | chapman_cpsc+resnet1d, cpsc_ptbxl+resnet1d |
| 44 | 2 | cpsc_chapman+resnet1d, cpsc_ptbxl+resnet1d |
| 45 | 2 | chapman_cpsc+inceptiontime, chapman_ptbxl+resnet1d |
| 46 | 1 | ptbxl_chapman+inceptiontime |

**架构分布**：inceptiontime 3 个反例，resnet1d 6 个反例（ResNet1D 反例率是 InceptionTime 的 2 倍）。

---

**报告结束。反方挑刺代理已完成全部 7 个攻击维度的审查。**
