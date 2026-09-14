# R9轮对抗审查 - 攻击维度5：数据完整性

**审查代理**: 反方挑刺代理 (session: 6e81e037-b71d-4c36-8351-4a4c818d87eb)
**审查对象**: `paper/main.tex` Table 1 及相关CSV数据文件
**审查日期**: 2026-09-13
**攻击维度**: 数据完整性（数值一致性、计算正确性、数据捏造检测）

---

## 审查范围

| 数据源 | 路径 | 用途 |
|--------|------|------|
| 论文正文 | `paper/main.tex` L599-L703 | Table 1: 60个TS实验的ΔECE_ID, ΔECE_OOD, CI下界 |
| 鲁棒性验证 | `results/robustness_validation_5seeds.csv` | 60个TS实验的原始数值 |
| 元分析汇总 | `results/meta_analytic_pooled.csv` | 固定效应/随机效应汇总 |
| Brier可靠性 | `results/c1_brier_reliability_summary.csv` | Brier可靠性分解统计 |
| Shapley验证 | `results/decomposition_validation_n20000.csv` | 27格Shapley分解验证 |

---

## 攻击结果汇总

| 严重级别 | 数量 | 说明 |
|----------|------|------|
| P0 (数据捏造) | 0 | 未发现数据捏造 |
| P1 (数据不一致) | 4 | CI下界存在≥0.0005的系统性偏差 |
| P2 (计算错误) | 3 | CI下界存在0.0002-0.0004的偏差 |
| P3 (四舍五入问题) | 14 | CI下界末位差异0.0001 |
| P3 (NaN数据质量) | 1 | Uncertainty_toplabel t统计量为NaN |

**总计发现攻击点**: 22个

---

## A. Table 1的60个ΔECE_OOD值与CSV一致性验证

### A.1 ΔECE_ID 和 ΔECE_OOD 点估计值

**结论**: 60个ΔECE_ID值和60个ΔECE_OOD点估计值全部在四舍五入到4位小数后与CSV完全一致。**无数据捏造迹象。**

### A.2 CI下界值 - 发现21处不一致

逐个比较Table 1中"CI lower"列与CSV中`ood_ci_lo`列（四舍五入到4位小数），发现以下不一致：

#### P1级不一致（差异 ≥ 0.0005，可能影响结论判断）

---

**Attack-ID: R9-Data-1**
- **严重级别**: P1 (数据不一致)
- **攻击描述**: PTB-XL→Chap, ResNet1D, seed 43 的CI下界值存在重大不一致。论文报告的CI下界(0.0336)比CSV实际值(0.0320)高出0.0016，这是所有60个数据点中最大的偏差。
- **证据**:
  - CSV (`robustness_validation_5seeds.csv`): `ood_ci_lo = 0.0320152437061716` → 四舍五入 = **0.0320**
  - 论文 Table 1 (L682): `CI lower = +0.0336`
  - 差异: **0.0016** (论文值比CSV值高)
- **对SCI Q2的影响**: 该实验的ΔECE_OOD=+0.0385，CI下界无论取0.0320还是0.0336都远大于0，不影响support判定。但0.0016的偏差远超四舍五入误差范围（最大四舍五入误差为0.00005），表明论文使用了与CSV不同的数据源或计算方法。**审稿人可能质疑数据可追溯性。**

---

**Attack-ID: R9-Data-2**
- **严重级别**: P1 (数据不一致)
- **攻击描述**: CPSC→Chap, Incep, seed 44 的CI下界值不一致。论文报告0.0160，CSV实际值0.0167，差异0.0007。
- **证据**:
  - CSV: `ood_ci_lo = 0.0166710058675662` → 四舍五入 = **0.0167**
  - 论文 Table 1 (L646): `CI lower = +0.0160`
  - 差异: **0.0007** (论文值比CSV值低)
- **对SCI Q2的影响**: 不影响support判定（两者均>0），但0.0007的偏差无法用四舍五入解释。**表明Table 1可能基于不同版本的bootstrap结果。**

---

**Attack-ID: R9-Data-3**
- **严重级别**: P1 (数据不一致)
- **攻击描述**: PTB-XL→CPSC, ResNet1D, seed 43 的CI下界值不一致。论文报告0.0145，CSV实际值0.0152，差异0.0007。
- **证据**:
  - CSV: `ood_ci_lo = 0.0152127381243457` → 四舍五入 = **0.0152**
  - 论文 Table 1 (L697): `CI lower = +0.0145`
  - 差异: **0.0007** (论文值比CSV值低)
- **对SCI Q2的影响**: 不影响support判定（该实验OOD=-0.0050，为反例，CI下界为负），但偏差幅度值得关注。

---

**Attack-ID: R9-Data-4**
- **严重级别**: P1 (数据不一致)
- **攻击描述**: Chap→PTB-XL, ResNet1D, seed 42 的CI下界值不一致。论文报告0.0285，CSV实际值0.0291，差异0.0006。
- **证据**:
  - CSV: `ood_ci_lo = 0.0290968832788488` → 四舍五入 = **0.0291**
  - 论文 Table 1 (L636): `CI lower = +0.0285`
  - 差异: **0.0006** (论文值比CSV值低)
- **对SCI Q2的影响**: 不影响support判定，但0.0006的偏差超出四舍五入误差一个数量级。

---

#### P2级不一致（差异 0.0002-0.0004）

---

**Attack-ID: R9-Data-5**
- **严重级别**: P2 (计算错误)
- **攻击描述**: CPSC→Chap, Incep, seed 43 的CI下界值不一致，差异0.0003。
- **证据**:
  - CSV: `ood_ci_lo = 0.0203300121234065` → **0.0203**
  - 论文 Table 1 (L645): `CI lower = +0.0200`
  - 差异: **0.0003**
- **对SCI Q2的影响**: 不影响support判定，但偏差需解释。

---

**Attack-ID: R9-Data-6**
- **严重级别**: P2 (计算错误)
- **攻击描述**: Chap→PTB-XL, Incep, seed 43 的CI下界值不一致，差异0.0002。
- **证据**:
  - CSV: `ood_ci_lo = 0.0067893089539931` → **0.0068**
  - 论文 Table 1 (L630): `CI lower = +0.0066`
  - 差异: **0.0002**
- **对SCI Q2的影响**: 不影响support判定。

---

**Attack-ID: R9-Data-7**
- **严重级别**: P2 (计算错误)
- **攻击描述**: PTB-XL→Chap, ResNet1D, seed 42 的CI下界值不一致，差异0.0002。
- **证据**:
  - CSV: `ood_ci_lo = 0.0188690492021125` → **0.0189**
  - 论文 Table 1 (L681): `CI lower = +0.0191`
  - 差异: **0.0002**
- **对SCI Q2的影响**: 不影响support判定。

---

#### P3级不一致（差异 0.0001，四舍五入边界问题）

以下14个数据点的CI下界存在0.0001的差异，可能源于四舍五入方向不一致（如0.02005在论文中取0.0200，在CSV中取0.0201）：

| Attack-ID | 实验 | 论文值 | CSV值 | 差异 |
|-----------|------|--------|-------|------|
| R9-Data-8 | Chap→PTB-XL, IT, s44 | 0.0107 | 0.0106 | 0.0001 |
| R9-Data-9 | Chap→PTB-XL, IT, s45 | 0.0207 | 0.0208 | 0.0001 |
| R9-Data-10 | Chap→PTB-XL, IT, s46 | 0.0142 | 0.0141 | 0.0001 |
| R9-Data-11 | Chap→PTB-XL, RN, s43 | 0.0285 | 0.0284 | 0.0001 |
| R9-Data-12 | Chap→PTB-XL, RN, s46 | 0.0139 | 0.0140 | 0.0001 |
| R9-Data-13 | CPSC→Chap, IT, s42 | 0.0062 | 0.0061 | 0.0001 |
| R9-Data-14 | CPSC→Chap, IT, s45 | 0.0241 | 0.0242 | 0.0001 |
| R9-Data-15 | CPSC→Chap, IT, s46 | 0.0023 | 0.0024 | 0.0001 |
| R9-Data-16 | CPSC→PTB-XL, IT, s44 | 0.0189 | 0.0190 | 0.0001 |
| R9-Data-17 | CPSC→PTB-XL, RN, s46 | 0.0296 | 0.0295 | 0.0001 |
| R9-Data-18 | PTB-XL→Chap, RN, s44 | 0.0228 | 0.0227 | 0.0001 |
| R9-Data-19 | PTB-XL→Chap, RN, s46 | 0.0221 | 0.0220 | 0.0001 |
| R9-Data-20 | PTB-XL→CPSC, RN, s44 | 0.0772 | 0.0773 | 0.0001 |
| R9-Data-21 | PTB-XL→CPSC, RN, s46 | 0.0190 | 0.0191 | 0.0001 |

- **对SCI Q2的影响**: 0.0001的差异在四舍五入边界上可接受，但14个数据点存在系统性偏差方向不一致（有时论文高、有时CSV高），**排除了系统性截断/放大的可能，更可能是不同bootstrap迭代次数或随机种子导致的CI估计差异。**

---

## B. 9个Counter-example的识别正确性验证

### B.1 Counter-example列表验证

论文Table 1中标记为✗（不支持）的9个实验：

| # | Transfer pair | Arch | Seed | 论文ΔECE_OOD | 论文CI_lo | CSV ood_significant | 匹配? |
|---|---------------|------|------|-------------|-----------|---------------------|-------|
| 1 | Chap→CPSC | Incep | 45 | -0.0057 | -0.0058 | False | ✅ |
| 2 | Chap→CPSC | ResNet | 43 | -0.0006 | -0.0006 | False | ✅ |
| 3 | Chap→PTB-XL | Incep | 42 | -0.0025 | -0.0035 | False | ✅ |
| 4 | Chap→PTB-XL | ResNet | 45 | -0.0036 | -0.0036 | False | ✅ |
| 5 | CPSC→Chap | ResNet | 42 | -0.0010 | -0.0012 | False | ✅ |
| 6 | CPSC→Chap | ResNet | 44 | -0.0168 | -0.0170 | False | ✅ |
| 7 | CPSC→PTB-XL | ResNet | 43 | -0.0050 | -0.0051 | False | ✅ |
| 8 | CPSC→PTB-XL | ResNet | 44 | -0.0049 | -0.0049 | False | ✅ |
| 9 | PTB-XL→Chap | Incep | 46 | -0.0026 | -0.0029 | False | ✅ |

**结论**: 9个counter-example全部与CSV中的`ood_significant=False`完全对应。**无遗漏、无多标。**

### B.2 遗漏的Counter-example检查

CSV中`ood_significant=False`的行恰好为9行，与论文标记的9个counter-example完全一致。**未发现遗漏的counter-example。**

### B.3 51/60 = 85.0%支持率验证

CSV中`ood_significant=True`的行恰好为51行。51/60 = 85.0%。与论文L705报告一致。✅

- InceptionTime: 27/30 = 90.0% ✅
- ResNet1D: 24/30 = 80.0% ✅

---

## C. 23/60 = 38.3% ID boundary计算验证

### C.1 ID CI包含零的计数

从CSV中提取60个TS行的`id_ci_lo`和`id_ci_hi`，检查CI是否包含零（`id_ci_lo ≤ 0 ≤ id_ci_hi`）：

| 统计项 | CSV实际值 | 论文报告值 | 匹配? |
|--------|-----------|-----------|-------|
| ID CI下界 > 0（排除零） | 34 | 34 | ✅ |
| ID CI包含零 | 23 | 23 | ✅ |
| ID CI上界 < 0（CI全负） | 3 | 未明确报告 | N/A |
| ID点估计 > 0 | 47 | 47 | ✅ |
| 总计 | 60 | 60 | ✅ |

**验证**: 34 + 23 + 3 = 60 ✅（34个CI下界>0，23个CI包含零，3个CI全负）

### C.2 38.3%计算验证

23/60 = 0.3833... = 38.3% ✅

### C.3 3个CI全负的实验

以下3个实验的ID CI完全在负区间（`id_ci_hi < 0`），论文未单独披露：

| Transfer pair | Arch | Seed | id_deltaECE | id_ci_lo | id_ci_hi |
|---------------|------|------|-------------|----------|----------|
| Chap→PTB-XL | Incep | 45 | -0.0128 | -0.0175 | -0.0070 |
| CPSC→Chap | ResNet | 44 | -0.0152 | -0.0179 | -0.0093 |
| CPSC→PTB-XL | ResNet | 44 | -0.0032 | -0.0042 | -0.0009 |

**Attack-ID: R9-Data-22**
- **严重级别**: P3 (信息披露不完整)
- **攻击描述**: 论文报告"34/60 have CI lower bounds > 0"和"23/60 contain zero"，但未明确提及3个CI完全为负的实验。这3个实验的ΔECE_ID CI上界也小于0，意味着TS在ID上产生了统计显著的负面影响。论文将这3个归入"23/60 contain zero"的类别是不准确的——它们的CI不包含零。
- **证据**: 
  - 论文L789-790: "34/60 cells have CI lower bounds > 0 (BCa operating CI), and only 23/60 = 38.3% contain zero"
  - CSV实际: 34个CI_lo>0, 3个CI_hi<0, 23个包含零。34+3+23=60。
  - 论文的表述"34/60 have CI lower > 0"和"23/60 contain zero"暗示剩余3个也包含零，但实际上这3个CI全负。
- **对SCI Q2的影响**: 轻微。论文的34+23=57≠60的算术关系暗示有3个未分类，但未明确说明。**建议论文补充"3/60 cells have CI entirely negative"的披露。**

---

## D. Meta-analytic pooled estimate验证

### D.1 ResNet1D固定效应汇总值

**Attack-ID: R9-Data-23**
- **严重级别**: P3 (数据一致，但需关注披露充分性)
- **攻击描述**: ResNet1D固定效应汇总估计确实为负值(-0.000573)，与论文报告一致。论文在L1865-1885对此进行了充分披露，解释了负值源于CI宽度异质性（窄CI研究在逆方差加权中占主导），并报告了随机效应模型（全部为正）和简单均值（全部为正）作为对照。
- **证据**:
  - CSV (`meta_analytic_pooled.csv`): ResNet1D行, `pooled_effect = -0.000573`, `ci_lo = -0.000586`, `ci_hi = -0.000560`
  - 论文L1869: "the ResNet1D fixed-effect pooled estimate is slightly negative ($-0.000573$)"
  - 随机效应: `re_pooled_effect = +0.015768` (论文报告+0.0158) ✅
  - 简单均值: `simple_mean = +0.016477` (论文报告+0.0165) ✅
- **对SCI Q2的影响**: **数据一致，披露充分。** 论文透明地报告了固定效应的负值，并提供了三种汇总方法的对照。这是良好的科学实践。**未发现可攻击点。**

### D.2 InceptionTime和CrossArchitecture汇总值

| 指标 | CSV值 | 论文报告值 | 匹配? |
|------|-------|-----------|-------|
| IT固定效应 | +0.000406 | 未直接报告 | N/A |
| IT随机效应 | +0.015148 | +0.0151 | ✅ |
| IT简单均值 | +0.015248 | +0.0152 | ✅ |
| Cross固定效应 | +0.000037 | 未直接报告 | N/A |
| Cross随机效应 | +0.014771 | +0.0148 | ✅ |
| Cross简单均值 | +0.015863 | +0.0159 | ✅ |

**注意**: InceptionTime的固定效应汇总值(+0.000406)和CrossArchitecture的固定效应汇总值(+0.000037)虽然为正，但数值极小（~10⁻⁴量级），与点估计均值(~0.015)相差约40倍。这进一步证实了固定效应模型被窄CI研究主导的判断。

---

## E. Shapley decomposition 27/27 at n=20000验证

### E.1 通过率验证

从`decomposition_validation_n20000.csv`中读取27行数据，检查`passed`列：

| 统计项 | CSV实际值 | 论文报告值 | 匹配? |
|--------|-----------|-----------|-------|
| 总格数 | 27 | 27 | ✅ |
| passed=True | 27 | 27/27 | ✅ |
| passed=False | 0 | 0 | ✅ |

**结论**: 27/27全部通过，与论文L958和L1792报告一致。✅

### E.2 share_reliable标志检查

**Attack-ID: R9-Data-24**
- **严重级别**: P3 (数据质量标注问题)
- **攻击描述**: Cell 13的`share_reliable=False`但`passed=True`。该格的Shapley份额超出有效范围：`shapley_share_b = 1.528`（>1），`shapley_share_pi = -0.528`（<0）。Shapley份额应在[0,1]区间内，负值和超过1的值表明该格的Shapley分解存在数值不稳定。
- **证据**:
  - Cell 13: slope=1.0, intercept=-1.0, target_prev=0.3
  - `shapley_share_s = 0.0`, `shapley_share_b = 1.528`, `shapley_share_pi = -0.528`
  - `share_reliable = False`, `passed = True`
- **对SCI Q2的影响**: 轻微。`passed`标志可能基于不同的判定标准（如MAPE或方向准确率），而非份额有效性。但论文未明确说明`passed`的判定标准是否要求`share_reliable=True`。**建议论文澄清27/27 pass的判定标准是否包含份额有效性约束。**

---

## F. NaN/Inf异常值检查

### F.1 各文件NaN/Inf扫描结果

| 文件 | NaN/Inf | 位置 |
|------|---------|------|
| robustness_validation_5seeds.csv | 无 | - |
| meta_analytic_pooled.csv | 无 | - |
| c1_brier_reliability_summary.csv | **有** | Uncertainty_toplabel行 |
| decomposition_validation_n20000.csv | 无 | - |

### F.2 Brier可靠性汇总中的NaN

**Attack-ID: R9-Data-25**
- **严重级别**: P3 (数据质量/计算边界)
- **攻击描述**: `c1_brier_reliability_summary.csv`中`Uncertainty_toplabel (应≈0)`行的`t_stat = +nan`和`p_value = nan`。这是因为TS不改变Uncertainty分量（`mean_diff = +0.000000`, `std_diff = 0.000000`），导致t统计量计算中出现0/0的不定形式。
- **证据**:
  ```
  Uncertainty_toplabel (应≈0),OOD,0.219583,0.219583,+0.000000,0.000000,+0.0000,+0.0000,+0.0000,+nan,nan,60
  ```
  - `mean_before = 0.219583`, `mean_after = 0.219583` (TS不改变Uncertainty)
  - `mean_diff = +0.000000`, `std_diff = 0.000000`
  - `t_stat = +nan` (0/0不定形式), `p_value = nan`
- **对SCI Q2的影响**: 轻微。NaN的出现是数学上合理的（零方差下的t检验未定义），但CSV中直接存储NaN而非标注"undefined"或"not_applicable"可能引起下游分析脚本的错误。**建议将NaN替换为"undefined"或添加注释列说明原因。** 论文未在正文中直接引用Uncertainty的t统计量，因此不影响论文结论。

### F.3 Brier可靠性其他指标验证

| 指标 | CSV值 | 论文是否引用 | 一致性 |
|------|-------|-------------|--------|
| Reliability_toplabel OOD mean_diff | +0.047836 | 间接引用(C1 sign) | ✅ |
| Reliability_toplabel OOD cohen_d | +0.7000 | 未直接引用 | N/A |
| Reliability_toplabel OOD p_value | 1.15e-06 | 未直接引用 | N/A |
| Reliability_toplabel ID p_value | 0.1007 | 未直接引用 | N/A |
| h1_ratio | 0.2229 | 未直接引用 | N/A |

**注意**: 论文未在正文中直接报告Brier可靠性的具体数值（mean_diff=0.0478, Cohen's d=0.70等），仅在L1670提及"Brier reliability main claim (C1 sign: 51/60 positive)"。这些数值可能出现在补充材料中。**不构成数据不一致，但建议论文在正文中引用关键数值以增强可追溯性。**

---

## G. 补充攻击维度

### G.1 反例构造

**攻击尝试**: 尝试构造一个案例，使CSV中的`ood_significant`标志与CI下界的符号不一致（如CI下界>0但`ood_significant=False`，或CI下界≤0但`ood_significant=True`）。

**结果**: 逐行检查60个TS行，`ood_significant`标志与`ood_ci_lo`的符号完全一致。未发现不一致。**该维度未发现可攻击点。**

### G.2 逻辑断链

**攻击尝试**: 检查"51/60 supported"→"85% robustness rate"→"TS is beneficial"的推理链条是否有跳跃。

**结果**: 51/60=85%的计算正确。论文明确披露了9个反例，未将85%解读为"普遍有效"，而是标注为"robustness rate"并讨论了反例的可解释性。**推理链条完整。**

### G.3 隐含假设

**攻击尝试**: 检查"BCa CI下界>0 → TS有效"的隐含假设。

**结果**: 论文使用95% BCa CI下界>0作为"support"的判定标准，这是标准的统计推断方法。论文也报告了NCV（负对照验证）结果作为补充验证。**隐含假设成立。**

### G.4 边界失效

**攻击尝试**: 检查极端情况——CI下界恰好为0的实验。

**结果**: 60个实验中无CI下界恰好为0的情况。最接近零的正CI下界为0.0002（CPSC→PTB-XL, Incep, seed 46），最接近零的负CI下界为-0.0006（Chap→CPSC, ResNet, seed 43）。**边界情况不适用。**

### G.5 自相矛盾

**攻击尝试**: 检查Table 1的support判定与meta_analytic_pooled.csv的结论是否矛盾。

**结果**: Table 1显示51/60=85%的实验支持TS（CI下界>0），但ResNet1D固定效应汇总为负(-0.000573)。这看似矛盾，但论文在L1865-1885充分解释了这是CI宽度异质性导致的（窄CI研究主导逆方差加权），随机效应模型和简单均值均为正。**不构成自相矛盾，但固定效应负值确实是一个需要审稿人关注的微妙之处。**

### G.6 量级错误

**攻击尝试**: 检查固定效应汇总值的量级是否合理。

**结果**: ResNet1D固定效应汇总(-0.000573)与点估计均值(+0.0165)相差约30倍，InceptionTime固定效应汇总(+0.000406)与均值(+0.0152)相差约37倍。这种巨大差异表明固定效应模型被极少数窄CI研究主导，`Q`统计量极大（ResNet1D: Q=128578, 远超k-1=29），证实了强异质性。**量级差异可解释，但固定效应模型在此场景下的适用性存疑。**

### G.7 语义偏移

**攻击尝试**: 检查"support"的定义在Table 1和论文其他位置是否一致。

**结果**: Table 1 caption (L602) 定义"Support = 95% CI lower bound > 0"。论文L705使用"51/60 supported = 85.0% robustness rate"。L1752使用"main-endpoint CIs exclude zero in 51/60 cases"。"Support"和"CI exclude zero"的语义一致。**未发现语义偏移。**

---

## 攻击报告总结

### 致命问题 (P0)
**无。** 未发现数据捏造。60个ΔECE_ID和ΔECE_OOD点估计值全部与CSV一致。

### 严重问题 (P1)
**4个。** Table 1中4个CI下界值与CSV存在0.0006-0.0016的偏差，远超四舍五入误差。最严重的是PTB-XL→Chap/ResNet/seed43（偏差0.0016）。这些偏差不影响任何support判定（所有受影响实验的support状态不变），但**表明Table 1可能基于不同版本的bootstrap结果或不同的随机种子**，数据可追溯性存在疑问。

### 中等问题 (P2)
**3个。** 3个CI下界值存在0.0002-0.0004的偏差。同样不影响support判定。

### 轻微问题 (P3)
**15个。** 14个CI下界末位差异0.0001（四舍五入边界），1个NaN数据质量问题（Uncertainty_toplabel），1个信息披露不完整（3个CI全负实验未单独披露），1个Shapley份额有效性标注问题。

### 对SCI Q2的总体影响评估

1. **数据完整性底线**: 60个核心点估计值（ΔECE_ID, ΔECE_OOD）全部与CSV一致，**无数据捏造**。9个反例识别完全正确。23/60=38.3%的ID boundary计算正确。27/27 Shapley验证通过。**核心数据完整性成立。**

2. **CI下界偏差**: 21/60个CI下界值存在0.0001-0.0016的偏差。其中4个P1级偏差（≥0.0006）需要作者解释是否使用了不同版本的bootstrap结果。**不影响任何定性结论，但影响数据可追溯性。**

3. **固定效应负值**: ResNet1D固定效应汇总为负(-0.000573)，论文已充分披露并提供随机效应对照。**披露充分，不构成攻击点。**

4. **NaN数据质量**: Uncertainty_toplabel的t统计量为NaN，数学上合理但工程上需标注。**不影响论文结论。**

5. **建议**: 
   - 解释4个P1级CI下界偏差的来源（不同bootstrap迭代？不同随机种子？）
   - 补充披露3个ID CI全负的实验
   - 澄清Shapley验证`passed`的判定标准是否包含份额有效性约束
   - 将NaN替换为"undefined"并添加注释

---

## 审查声明

我尝试了全部7个攻击维度（反例构造、逻辑断链、隐含假设、边界失效、自相矛盾、量级错误、语义偏移），并对5个数据文件进行了逐行验证。未发现数据捏造（P0），但发现4个P1级数据不一致（CI下界偏差≥0.0006）和3个P2级计算错误（CI下界偏差0.0002-0.0004）。核心点估计值和定性结论全部与CSV一致，数据完整性基本成立，但CI下界的可追溯性存在疑问。

**攻击代理**: R9-Data 维度5反方
**审查完成时间**: 2026-09-13
