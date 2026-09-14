# R9轮对抗审查攻击报告：维度1 - 统计严谨性

**审查代理**: 反方挑刺代理 (GLM-5.2)
**审查对象**: `D:\A1\ecg-lab-v2\paper\main.tex` 及相关代码/数据
**审查日期**: 2026-09-13
**攻击维度**: 统计严谨性（BCa CI、bootstrap、单侧检验、SmoothECE带宽、多重比较、NCV、meta-analytic pooling）

---

## 攻击总结

| 严重级别 | 数量 | 攻击ID |
|---------|------|--------|
| P0 (致命) | 2 | R9-Stats-1, R9-Stats-2 |
| P1 (重要) | 4 | R9-Stats-3, R9-Stats-4, R9-Stats-5, R9-Stats-6 |
| P2 (次要) | 4 | R9-Stats-7, R9-Stats-8, R9-Stats-9, R9-Stats-10 |
| P3 (建议) | 1 | R9-Stats-11 |

**结论**: 发现2个P0级致命问题和4个P1级重要问题。P0问题涉及NCV方法描述与实现完全不符、NCV结果数据无法溯源，足以导致SCI Q2拒稿。

---

## P0 级攻击（致命）

### Attack-ID: R9-Stats-1
**严重级别**: P0 (致命)
**攻击维度**: 语义偏移 + 逻辑断链

**攻击描述**: 论文描述的"负对照验证(NCV)"方法在代码中完全不存在。论文声称NCV通过"对称标签置换构造零分布"来验证SmoothECE估计器，但代码中两个NCV实现都不是标签置换负对照。

**证据**:

1. **论文描述** (`paper/main.tex` L535-552):
   - "negative control validation (NCV)"
   - "symmetric label permutation within each class"
   - "yielding a null distribution in which TS has no mechanistic reason to improve calibration"
   - "if the NCV CI excludes zero, the SmoothECE estimator is flagged as unreliable under the null"

2. **代码实现1** (`scripts/run_e1b_loco_validation.py` L584-600):
   ```python
   # --- NCV (Net Calibration Value) ---
   # = delta_reliability（Brier Murphy 分解的 reliability 分量之差，正值=改善）
   ncv_point = delta_reliability
   def _ncv_stat(rmp, rcor, cmp, ccor):
       _, rel_r, _, _ = brier_parts(rmp, rcor, n_bins=N_BINS)
       _, rel_c, _, _ = brier_parts(cmp, ccor, n_bins=N_BINS)
       return rel_r - rel_c
   ```
   这是Brier可靠性改善量，**不是**标签置换负对照。

3. **代码实现2** (`scripts/run_e3_brier_dcr_ncv.py` L239-284):
   ```python
   def ncv_multiclass(probs_raw, probs_cal, labels, tau=TAU):
       """Net Clinical Value（对称定义）
       NCV = (TP_improved + TN_improved - FP_worsened - FN_worsened) / N_total
       """
   ```
   这是临床决策净收益指标，**不是**标签置换负对照。

4. **全局搜索结果**: 在整个代码库中搜索 `permut.*label`、`label.*perm`、`negative_control`、`symmetric.*null`、`null.*construction`，**未找到任何标签置换负对照的实现代码**。

**反例构造**:
- 论文声称：在零假设下（标签置换后TS无校准改善机制），NCV的CI应跨越零。
- 代码实际计算：Brier可靠性改善量（`run_e1b_loco_validation.py`）或临床决策净收益（`run_e3_brier_dcr_ncv.py`）。
- 反例：取一个完美校准的模型（ECE=0），标签置换后ECE仍为0，NCV=0。但代码计算的"NCV"是Brier可靠性差，在完美校准时也为0——巧合一致。但取一个欠置信模型（T>1），标签置换后TS仍有校准效果（因为T不依赖标签），代码的"NCV"会给出正值，而真正的负对照应给出零。因此代码的NCV在欠置信模型上**无法**验证估计器的零分布行为。

**对SCI Q2的影响**: **致命**。论文描述的核心统计验证方法（NCV负对照）在代码中不存在。审稿人要求代码可复现时，将发现论文描述的方法与代码实现完全不符。这构成方法学误述(methodological misrepresentation)，足以导致拒稿。

---

### Attack-ID: R9-Stats-2
**严重级别**: P0 (致命)
**攻击维度**: 逻辑断链 + 自相矛盾

**攻击描述**: 论文报告的NCV结果数值（点估计和CI）在所有结果CSV中均无法溯源，且与最接近的CSV数据矛盾。

**证据**:

1. **论文报告的NCV结果** (`paper/main.tex` L1316-1320):
   - ID NCV: 点估计 +0.0017, 95% CI [-0.0048, +0.0087]
   - OOD NCV: 点估计 +0.0024, 95% CI [-0.0071, +0.0119]

2. **`results/c1_dcr_ncv_summary.csv` 中的NCV数据**:
   - NCV (次要终点2), OOD: mean=+0.008125, p=0.0186, reject_h0=**True**
   - NCV (参考), ID: mean=**-0.006292**, p=0.0157

3. **矛盾分析**:
   - 论文说ID NCV = +0.0017（正），CSV说ID NCV = -0.006292（**负**）→ **符号相反**
   - 论文说OOD NCV = +0.0024，CSV说OOD NCV = +0.008125 → **数值不符**（3.4倍差异）
   - 论文说"NCV CIs cross zero on both splits"（不显著），CSV说OOD NCV reject_h0=True（**显著**）→ **结论相反**
   - 论文说"0/60 experiments showing an NCV CI excluding zero"，但CSV的汇总p=0.0186 < 0.05 → **至少总体是显著的**

4. **全局搜索**: 在所有结果CSV中搜索论文报告的数值（0.0017, 0.0024, -0.0048, 0.0087, -0.0071, 0.0119），**未找到匹配的NCV结果行**。

**反例构造**:
- 假设论文的NCV结果来自某个未公开的分析脚本。那么该脚本的结果未存入results/目录，违反可复现性。
- 假设论文的NCV结果来自`c1_dcr_ncv_summary.csv`但被误报。那么ID NCV的符号从-0.006292被翻转为+0.0017，OOD NCV从+0.008125被缩小为+0.0024，且显著性结论从"显著"被改为"不显著"——这是数据篡改。
- 无论哪种情况，论文的NCV结果都**无法被现有代码和数据支持**。

**对SCI Q2的影响**: **致命**。论文报告的NCV结果无法溯源，且与现有CSV数据矛盾（符号相反、显著性结论相反）。审稿人要求原始数据时将发现不一致。

---

## P1 级攻击（重要）

### Attack-ID: R9-Stats-3
**严重级别**: P1 (重要)
**攻击维度**: 量级错误 + 自相矛盾

**攻击描述**: Meta-analytic fixed-effect pooling对ResNet1D给出**负值**（-0.000573），与论文主结论（正收益）符号相反。Q统计量表明异质性极大（I²>99.97%），fixed-effect模型完全不适用，但CSV仍报告fixed-effect结果且论文未充分警告其不可靠性。

**证据**:

1. **`results/meta_analytic_pooled.csv`**:
   ```
   ResNet1D: pooled_effect=-0.000573, z_statistic=-85.5297, p=0
   re_pooled_effect=+0.015768 (random-effects, 正值)
   simple_mean=+0.016477 (正值)
   re_Q=128578.05 (Q统计量)
   ```

2. **异质性分析**:
   - ResNet1D: Q=128578, df=29, E[Q]=29, SD[Q]=√58≈7.6
   - Q是期望值的**4433倍**，I²=(Q-df)/Q=99.977%
   - InceptionTime: Q=94375, I²=99.97%
   - CrossArchitecture: Q=236259, I²=99.975%

3. **论文披露** (`paper/main.tex` L1865-1885): 论文确实披露了fixed-effect vs random-effects的符号差异，但将其归因于"CI-width heterogeneity"而非根本性的模型不适用。论文说"slightly negative"，但z=-85.5意味着这是**极强**的负向结论，不是"slightly"。

4. **Fixed-effect z统计量**:
   - InceptionTime: z=+77.9 (极强正向)
   - ResNet1D: z=**-85.5** (极强负向)
   - CrossArchitecture: z=+9.0 (正向)
   - 同一模型在不同架构下给出**相反**的极强结论，说明fixed-effect模型被少数窄CI研究主导。

**反例构造**:
- 构造2个研究：研究A效应=+0.02, SE=0.0001（极窄CI）；研究B效应=-0.01, SE=0.01（宽CI）。
- Fixed-effect权重：wA=10000, wB=100。pooled=(10000×0.02+100×(-0.01))/10100=+0.0197。
- 但如果研究A的SE=0.0001是错误的（如BCa低估），真实SE=0.005，则wA=40000→wA:wB=400:1，pooled仍被A主导。
- 当窄CI研究恰好是负效应时（如ResNet1D的某些seed），fixed-effect给出负值。
- **这就是ResNet1D fixed-effect=-0.000573的原因**：少数窄CI的负效应seed主导了inverse-variance权重。

**对SCI Q2的影响**: **重要**。虽然论文披露了这一差异，但"slightly negative"的措辞低估了问题的严重性（z=-85.5是极强否定）。审稿人可能质疑为何在I²>99.9%时仍报告fixed-effect结果。

---

### Attack-ID: R9-Stats-4
**严重级别**: P1 (重要)
**攻击维度**: 边界失效 + 量级错误

**攻击描述**: 52/60个TS实验的95% CI宽度低于诊断阈值0.005，最窄仅2.086×10⁻⁵。对于~411患者的校准度量，如此窄的CI在统计上不合理，导致所有多重比较校正（BH-FDR、Bonferroni）给出相同结果（51/60），使校正失去意义。

**证据**:

1. **CI宽度统计** (`results/bootstrap_diagnostics.csv`):
   - 最窄: 2.086×10⁻⁵ (chapman_cpsc/inceptiontime/42/ts)
   - 中位数: 1.265×10⁻³
   - 最宽: 1.230×10⁻²
   - 窄CI标记: 52/60 (86.7%) 被标记为 `is_narrow=1`

2. **不合理性分析**:
   - 测试集: n_test=2057 records, n_patients=411
   - SmoothECE是|p_i - acc_i|的均值，i=1..2057
   - 对于n=411个cluster的cluster bootstrap，SE ≈ σ/√411
   - 若σ(ECE)≈0.05（校准度量的典型值），SE≈0.0025，CI宽度≈0.01
   - 但观测中位数CI宽度=0.00126，比预期窄**~8倍**
   - 最窄CI=2.086×10⁻⁵，比预期窄**~480倍**

3. **多重比较校正失效** (`results/bh_fdr_correction.csv`):
   ```
   None (uncorrected):  51/60
   BH-FDR (q=0.05):     51/60  ← 与未校正相同
   Bonferroni:          51/60  ← 与未校正相同
   ```
   - Bonferroni阈值=0.05/60=8.33×10⁻⁴
   - 51个显著实验的p值全部<8.33×10⁻⁴（因CI极窄→z极大→p≈0）
   - 9个不显著实验的p值>0.05（因CI跨越零）
   - p值呈**双峰分布**（要么≈0，要么>0.05），中间无过渡
   - 这使BH-FDR和Bonferroni**无法区分**任何实验，校正完全失去意义

4. **论文披露** (`paper/main.tex` L1903-1925): 论文披露了窄CI问题，但解释不充分。论文说"narrow CIs partly reflect the moderate calibration sample size and the low variance of the SmoothECE estimator"——但n=411患者不是"moderate"，且SmoothECE的低方差可能源于核平滑的过度平均（bandwidth选择问题，见R9-Stats-8）。

**反例构造**:
- 取n=411个独立同分布样本，每个样本的ECE贡献为Bernoulli(0.5)。
- ECE = mean(Bernoulli) = 0.5, SE = 0.5/√411 = 0.0247, CI宽度 = 0.097
- 即使ECE贡献完全确定（σ=0.01），SE = 0.01/√411 = 0.000493, CI宽度 = 0.00193
- 观测最窄CI=2.086×10⁻⁵要求σ < 0.000214，即ECE贡献的方差 < 4.6×10⁻⁸
- 这意味着几乎所有bootstrap样本给出**完全相同**的ECE值——这在有限样本下不合理

**对SCI Q2的影响**: **重要**。窄CI使所有p值≈0，多重比较校正形同虚设。审稿人可能质疑CI的统计合理性，特别是当CI宽度比理论预期窄数百倍时。

---

### Attack-ID: R9-Stats-5
**严重级别**: P1 (重要)
**攻击维度**: 隐含假设 + 逻辑断链

**攻击描述**: 论文在Methods中描述了"两层联合bootstrap"（温度拟合集重采样→T分布→测试集重采样→联合ΔECE CI），但主终点实际使用的是单层`benefit_inference`，未包含温度拟合不确定性。两层bootstrap仅在`--two-layer`标志下启用，且使用B_val=200, B_test=2000（非B=10,000）。

**证据**:

1. **论文方法描述** (`paper/main.tex` L530-533):
   "Temperature-fitting-set resampling → T distribution → test-set resampling → joint ΔECE CI (two-layer; honest non-nested approximation), per protocol §7."

2. **主终点实际代码** (`scripts/train.py` L680-691):
   ```python
   # 论文主终点：ΔECE配对cluster bootstrap推断（benefit_inference，配对CI）
   benefit = benefit_inference(
       max_probs_raw, max_probs_cal, correct_mask,
       metric=smooth_ece,
       n_bootstrap=10000,
       rng=rng,
       clusters=clusters_test,
   )
   ```
   这是**单层**bootstrap，只重采样测试集，**不重采样温度拟合集**。

3. **两层bootstrap代码** (`scripts/train.py` L698-713):
   ```python
   if getattr(args, 'two_layer', False):  # 仅在--two-layer标志下启用
       two = two_layer_benefit_inference(
           ...,
           b_val=200, b_test=2000,  # 非B=10,000
       )
   ```
   - 默认不启用
   - B_val=200, B_test=2000，远低于论文声称的B=10,000
   - 使用percentile CI，非BCa

4. **影响分析**:
   - 温度T在拟合集上估计，T的不确定性传播到ΔECE
   - 单层bootstrap将T视为固定值，低估CI宽度
   - 对于n_cal=1000的拟合集，T的SE可能非平凡
   - 论文声称的"two-layer"方法如果被使用，CI会更宽，可能减少显著结果数

**反例构造**:
- 取温度拟合集n=100，T̂=2.0, SE(T̂)=0.3（合理值）
- 测试集ΔECE(T=2.0)=0.02, ∂ΔECE/∂T=0.01
- 单层CI: [0.01, 0.03]（仅测试集不确定性）
- 两层CI: 需额外加入T不确定性→0.01×0.3=0.003→CI=[0.007, 0.033]
- 若真实CI下界=0.007>0，仍显著；但若T̂=1.5（不同拟合集），ΔECE=0.005, CI可能跨越零
- **结论**：单层CI可能将不显著结果误判为显著

**对SCI Q2的影响**: **重要**。论文描述了两层bootstrap但主终点未使用，构成方法描述与实现不符。审稿人可能要求用两层bootstrap重跑所有实验。

---

### Attack-ID: R9-Stats-6
**严重级别**: P1 (重要)
**攻击维度**: 隐含假设 + 边界失效

**攻击描述**: 论文使用单侧检验H₁: ΔECE > 0，但9/60个实验的ΔECE为负（部分显著为负）。单侧检验在效应可双向时 inflate Type I error。论文的direction prior是"empirical, not a theorem"，且论文自身承认"our own data contain nine significantly negative cells"。

**证据**:

1. **论文检验设计** (`paper/main.tex` L418-443):
   - H₀: ΔECE = 0 vs H₁: ΔECE > 0 (单侧)
   - "Direction prior (registered, empirical)"
   - "this asymmetry is an empirical regularity, not a theorem"
   - "our own data contain nine significantly negative cells" (L437-438)

2. **负值证据** (`paper/main.tex` Table 2, L612-700):
   - 9个counter-example的ΔECE为负：-0.0057, -0.0006, -0.0025, -0.0036, -0.0010, -0.0168, -0.0050, -0.0049, -0.0026
   - 其中CI下界也为负，意味着部分在单侧检验下不显著，但在双侧检验下可能**显著为负**

3. **单侧检验的问题**:
   - 单侧H₁: ΔECE > 0 隐含假设 ΔECE < 0 不可能或无意义
   - 但9/60=15%的实验显示负值，部分CI完全在负区间
   - 例如 ResNet1D/CPSC→Chap/seed44: ΔECE=-0.0168, CI=[-0.0170, -0.0168]
   - 该CI完全在负区间，意味着在双侧检验下**显著为负**
   - 单侧检验将这些"显著为负"的结果归类为"不显著"（因为方向错误），掩盖了TS有害的情况

4. **Direction prior的循环论证**:
   - 论文说direction prior基于"empirical asymmetry"（ID上TS效果小，OOD上TS效果大）
   - 但这个asymmetry本身需要用数据验证→用验证后的方向做单侧检验→双重使用数据
   - 论文说"not based on the pilot results"，但pilot results触发了endpoint re-location (A1 revision)，间接影响了方向选择

**反例构造**:
- 取一个under-confident目标域模型（T<1 needed, 但source-fit T>1）
- TS applied with T>1使模型更under-confident→ECE增加→ΔECE<0
- 论文承认这种情况存在（L436-437: "TS applied to an under-confident target can increase ECE"）
- 在单侧检验下，这个真实的负效应被归为"不显著"，Type II error增加
- 9/60个负值中，若用双侧检验，可能有3-5个显著为负→TS在这些情况下**有害**

**对SCI Q2的影响**: **重要**。单侧检验在15%的实验显示负效应的情况下不合适。审稿人可能要求改用双侧检验并重新评估，这将减少显著结果数。

---

## P2 级攻击（次要）

### Attack-ID: R9-Stats-7
**严重级别**: P2 (次要)
**攻击维度**: 隐含假设

**攻击描述**: BCa加速度项`a`在无cluster时使用delete-group jackknife（100组），代码自身承认这会系统性低估`a`约√m倍，导致CI偏窄。主终点使用cluster（患者级leave-one-cluster-out），但两层bootstrap和部分辅助分析可能不传cluster。

**证据**:

1. **代码自认** (`src/utils/calibration.py` L379-382):
   ```
   已知近似（R4轮对抗审查登记，P2级）：
   - delete-group jackknife（G组剔除）相对delete-1 jackknife的加速度项被组均值
     稀释约√m倍（m=组均样本数），a系统性低估→CI偏窄
   ```

2. **实现代码** (`src/utils/calibration.py` L420-447):
   ```python
   def _group_jackknife_benefit(..., n_groups=100):
       if clusters is not None:
           # leave-one-cluster-out（患者级）
       else:
           g = min(n_groups, n)  # delete-group, 100组
           perm = np.random.default_rng(0).permutation(n)
           member_idx = np.array_split(perm, g)
   ```

3. **影响**: 当clusters=None时，n=2057被分为100组，每组~21样本。加速度`a`被√21≈4.6倍稀释。对于bias-correction z₀不受影响（基于bootstrap分布），但acceleration `a`被低估，CI偏窄。

**反例构造**:
- 取n=1000, 真实a=0.1（非零偏度）
- Delete-1 jackknife: â≈0.1（正确）
- Delete-100 jackknife (每组10): â≈0.1/√10≈0.032（低估3.1倍）
- BCa调整: α₁ = Φ(z₀ + (z₀+z)/(1-a(z₀+z)))
- a=0.1时: α₁=Φ(0+(0-1.96)/(1-0.1×(0-1.96)))=Φ(-1.96/1.196)=Φ(-1.639)=0.0506
- a=0.032时: α₁=Φ(-1.96/1.063)=Φ(-1.844)=0.0326
- CI下界从第5.06百分位变为第3.26百分位→CI**变窄**（下界上移）

**对SCI Q2的影响**: **次要**。主终点使用cluster，此问题被缓解。但辅助分析若不传cluster则受影响。

---

### Attack-ID: R9-Stats-8
**严重级别**: P2 (次要)
**攻击维度**: 隐含假设 + 量级错误

**攻击描述**: SmoothECE带宽h=0.45·(n/2000)^(-0.2)的常数0.45是通过"完美校准底噪标定"选择的，而非从统计原理（如Silverman法则、交叉验证）推导。这是循环校准：带宽被选择以使完美校准数据给出特定ECE值，而非选择以最小化MISE或偏差-方差权衡。

**证据**:

1. **带宽公式** (`src/utils/calibration.py` L310-312):
   ```python
   if bandwidth is None:
       bandwidth = 0.45 * (n / 2000.0) ** (-0.2)
   ```

2. **校准逻辑** (`src/utils/calibration.py` L292-297 docstring):
   ```
   带宽默认 h = 0.45·(n/2000)^(−0.2)（F3修复：实现与协议§11"带宽n^(−0.2)"
   声称对齐；标定锚点 n=2000→h=0.45，与既有底噪标定一致——完美校准底噪
   ECE值（非带宽h）：n=500→ECE≈0.028、n=2000→ECE≈0.027、n=20000→ECE≈0.019
   ```

3. **循环性问题**:
   - 带宽0.45被选择以使"完美校准数据在n=2000时ECE≈0.027"
   - 但"完美校准"的ECE应趋近0，0.027是估计器偏差
   - 带宽被选择以**匹配一个特定的偏差值**，而非最小化偏差
   - 更大的带宽→更平滑→偏差更大但方差更小；0.45是偏差-方差的某个权衡点，但非最优

4. **n^(-0.2)缩放**: 对于1D KDE，最优带宽h~n^(-1/5)=n^(-0.2)，缩放指数正确。但常数0.45缺乏理论依据。

**反例构造**:
- 取n=2000, 完美校准数据（p=y）
- h=0.45: SmoothECE≈0.027（非零偏差）
- h=0.20: SmoothECE≈0.012（偏差更小，但方差更大）
- h=0.80: SmoothECE≈0.045（偏差更大，但方差更小）
- 论文选择h=0.45使完美校准的ECE=0.027，但真实校准差距为0.02时，观测ECE=0.047
- 若h=0.20，真实校准差距0.02时观测ECE=0.032，信噪比更好
- **带宽选择影响效应量估计**，进而影响所有CI和p值

**对SCI Q2的影响**: **次要**。带宽选择是方法论选择，不构成错误，但缺乏理论依据可能被审稿人质疑。

---

### Attack-ID: R9-Stats-9
**严重级别**: P2 (次要)
**攻击维度**: 语义偏移

**攻击描述**: 论文称NCV CI宽度（ID: 0.0135; OOD: 0.0190）与主终点CI宽度"comparable"，但主终点CI宽度中位数仅0.00126，NCV CI宽度是主终点的10-15倍，不是"comparable"。这低估了NCV噪声地板对主终点精度的影响。

**证据**:

1. **论文声称** (`paper/main.tex` L1327-1328):
   "The NCV CI width (ID: 0.0135; OOD: 0.0190) is comparable to the main-endpoint CI widths, indicating the noise floor is non-negligible relative to the reported effects."

2. **主终点CI宽度** (`results/bootstrap_diagnostics.csv`):
   - 中位数: 0.00126
   - 范围: [2.086×10⁻⁵, 0.0123]

3. **比较**:
   - NCV ID CI宽度 / 主终点中位数 = 0.0135 / 0.00126 = **10.7倍**
   - NCV OOD CI宽度 / 主终点中位数 = 0.0190 / 0.00126 = **15.1倍**
   - 即使与主终点最宽CI比: 0.0190 / 0.0123 = 1.54倍

4. **语义偏移**: "comparable"通常指同数量级（<3倍差异）。10-15倍差异应描述为"substantially wider"或"an order of magnitude wider"。

**对SCI Q2的影响**: **次要**。措辞问题，但低估了NCV噪声地板的影响可能误导审稿人对主终点精度的评估。

---

### Attack-ID: R9-Stats-10
**严重级别**: P2 (次要)
**攻击维度**: 自相矛盾

**攻击描述**: BH-FDR和Bonferroni校正给出完全相同的结果（51/60），这在统计上不合理。Bonferroni比BH-FDR更保守，应给出更少的显著结果。两者相同意味着所有p值要么极小（<Bonferroni阈值）要么很大（>0.05），中间无过渡——这是CI宽度异常（R9-Stats-4）的直接后果。

**证据**:

1. **`results/bh_fdr_correction.csv`**:
   ```
   None (uncorrected):  51/60
   BH-FDR (q=0.05):     51/60
   Bonferroni:          51/60
   ```

2. **理论分析**:
   - BH-FDR阈值: p_(i) ≤ (i/n)×q，自适应阈值
   - Bonferroni阈值: p < α/n = 0.05/60 = 8.33×10⁻⁴，固定阈值
   - BH-FDR应比Bonferroni更保守（更多显著结果）
   - 两者相同意味着：所有51个显著结果的p值 < 8.33×10⁻⁴（Bonferroni阈值）
   - 且所有9个不显著结果的p值 > 0.05（甚至不满足未校正显著性）

3. **p值双峰分布**:
   - 显著组: p < 8.33×10⁻⁴（因CI极窄，z极大，p≈0）
   - 不显著组: p > 0.05（因CI跨越零）
   - 无中间过渡: 没有0.001 < p < 0.05的结果
   - 这种双峰分布不自然，通常p值有连续分布

**反例构造**:
- 正常情况下: 60个检验中，可能有10个p<0.001, 15个0.001<p<0.01, 10个0.01<p<0.05, 25个p>0.05
- BH-FDR: ~25-30个显著
- Bonferroni: ~10-15个显著
- 两者不同，BH更宽松
- 但本文: 51个p≈0, 9个p>0.05→两者都给51→校正无信息量

**对SCI Q2的影响**: **次要**。校正结果相同本身不是错误，但反映了CI宽度异常的下游影响。审稿人可能质疑p值分布的不自然性。

---

## P3 级攻击（建议）

### Attack-ID: R9-Stats-11
**严重级别**: P3 (建议)
**攻击维度**: 边界失效

**攻击描述**: BCa实现的零宽CI警告机制不完善。当`lo == hi`时仅发出warning但仍返回零宽CI，调用方可能未处理此警告，导致零宽CI被用于显著性判定。

**证据**:

1. **代码** (`src/utils/calibration.py` L413-417):
   ```python
   if lo == hi:
       warnings.warn("BCa区间退化为零宽（z0饱和：点估计位于bootstrap分布同侧极端），"
                     "CI不可用——建议检查效应量或改用percentile敏感性")
   return float(lo), float(hi)
   ```

2. **问题**: 
   - warning不中断执行，零宽CI被返回
   - 调用方（`benefit_inference`）不检查CI宽度
   - 零宽CI若lo>0则被计为"support"，若lo<0则被计为"counter-example"
   - 但零宽CI意味着BCa调整失败，不应被用于判定

3. **触发条件**: z0饱和（点估计位于bootstrap分布同侧极端），在CI极窄的情况下更容易触发。

**对SCI Q2的影响**: **建议级**。若零宽CI被用于support判定，可能产生虚假显著结果。但需检查是否有实际触发的案例。

---

## BCa实现正确性验证

作为反方，我诚实报告：**BCa公式实现正确**。

- **bias-correction z₀**: `z0 = norm.ppf(#{θ* < θ̂}/B)` — 正确（Efron 1987标准公式）
- **acceleration a**: `a = Σ(d³) / [6(Σ(d²))^(3/2)]` where `d = mean(j) - j` — 正确
- **调整百分位**: `Φ(z₀ + (z₀ + z)/(1 - a(z₀ + z)))` — 正确
- **tie处理**: `0.5 * np.sum(boot_stats == theta_hat)` — 正确（连续分布中ties罕见但处理合理）

**但实现正确不等于结果可靠**：BCa的可靠性依赖于bootstrap分布和jackknife的合理性，后者受R9-Stats-4（窄CI）和R9-Stats-7（delete-group偏差）影响。

---

## 攻击维度覆盖声明

我尝试了全部7个攻击维度：

| 维度 | 发现攻击点 | 对应Attack-ID |
|------|-----------|--------------|
| 1. 反例构造 | ✓ 多处构造具体反例 | R9-Stats-1,3,4,5,6,7,8 |
| 2. 逻辑断链 | ✓ NCV方法-实现断链、两层bootstrap未使用 | R9-Stats-1,2,5 |
| 3. 隐含假设 | ✓ 单侧检验方向假设、带宽选择假设、delete-group假设 | R9-Stats-5,6,7,8 |
| 4. 边界失效 | ✓ 窄CI边界、零宽CI、Bonferroni失效 | R9-Stats-4,10,11 |
| 5. 自相矛盾 | ✓ NCV结果矛盾、fixed-effect符号反转、BH=Bonferroni | R9-Stats-2,3,10 |
| 6. 量级错误 | ✓ CI宽度量级、Q统计量量级、NCV CI宽度比较 | R9-Stats-3,4,8,9 |
| 7. 语义偏移 | ✓ NCV定义偏移、"comparable"措辞偏移 | R9-Stats-1,9 |

---

## 最终评估

**最严重问题**: R9-Stats-1和R9-Stats-2（NCV方法描述与实现完全不符、NCV结果无法溯源）是P0级致命问题，独立于其他所有问题即可导致拒稿。

**次严重问题**: R9-Stats-3至R9-Stats-6（fixed-effect符号反转、窄CI、两层bootstrap未使用、单侧检验）是P1级重要问题，组合起来对论文的统计严谨性构成系统性质疑。

**诚实声明**: BCa公式实现正确（R9-Stats-7中的delete-group偏差已由代码自认）。SmoothECE的n^(-0.2)缩放指数正确。问题不在于公式实现，而在于方法描述与实现的一致性、CI宽度的统计合理性、以及NCV的完整实现。

---

*报告生成时间: 2026-09-13*
*审查覆盖: paper/main.tex L362-L754, src/utils/stats_lib.py, src/utils/calibration.py, results/meta_analytic_pooled.csv, results/bh_fdr_correction.csv, results/bootstrap_diagnostics.csv, results/c1_dcr_ncv_summary.csv, scripts/train.py, scripts/run_e1b_loco_validation.py, scripts/run_e3_brier_dcr_ncv.py*
