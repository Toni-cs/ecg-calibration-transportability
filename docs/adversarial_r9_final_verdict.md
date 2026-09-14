# R9轮对抗审查 — 终审判决报告

**终审代理**: 终审代理 (GLM-5.2)
**审查对象**: 8份反方攻击报告 + 1份正方反驳报告 + 1份反反方元审查裁决 + 论文原文 `paper/main.tex`
**审查日期**: 2026-09-13
**角色声明**: 独立终审代理，不跟随元审查结论，对每个P0攻击亲自验证论文原文行号。
**任务ID**: 55

---

## 1. 最终结论

### 裁决：**NO-GO**

**一句话总结**：论文存在13个SUSTAINED P0级致命问题（8处虚假作者引用、2处NCV方法学误述、2处过度声称、1处编译错误），当前状态不满足SCI Q2投稿门槛，必须完成P0修补后重新审查。

### 裁决依据

| 裁决标准 | 阈值 | 当前值 | 判定 |
|---------|------|--------|------|
| SUSTAINED P0数 | ≤ 0 | **13** | ❌ 未达标 |
| SUSTAINED P1数 | ≤ 5 | 0 | ✅ 达标 |
| 收敛状态 | 已收敛 | **未收敛** | ❌ |

**裁决规则**：SUSTAINED P0 > 0 → **NO-GO**，需要修补后重新审查。

---

## 2. 有效攻击点汇总表

### 2.1 SUSTAINED攻击点（13个，全部P0）

| # | Attack-ID | 级别 | 类别 | 论文行号 | 攻击内容 | 终审独立验证 |
|---|-----------|------|------|---------|---------|-------------|
| 1 | R9-Stats-1 | P0 | 方法学误述 | L535-552 | NCV描述"symmetric label permutation" vs 代码"Brier reliability decomposition" | ✅ 已验证L541-542原文"symmetric label permutation within each class" |
| 2 | R9-Stats-2 | P0 | 数据无法溯源 | L1316-1320 | 论文ID NCV=+0.0017 vs CSV=-0.006292（符号相反）；OOD NCV +0.0024 vs +0.008125（3.4倍差异） | ✅ 已验证L1317-1320原文数值 |
| 3 | R9-Overclaim-1 | P0 | 选择性报告 | L705, L1907-1909 | Abstract报告85%，埋藏75%（排除6个退化CI后） | ✅ 已验证L705"85.0%"和L1908-1909"45/60 (75.0%)" |
| 4 | R9-Overclaim-3 | P0 | 声明与证据矛盾 | L1827 vs L758, L1588, L1113 | "reasonable default"被safety rate=0.0064等4项证据否定 | ✅ 已验证L1827"reasonable default"和L1834"safety rate 0.0064" |
| 5 | R9-LaTeX-1 | P0 | 编译错误 | L536, L2194 | `\label{sec:ncv_methods}`(下划线) vs `\ref{sec:ncv-methods}`(连字符) | ✅ 已验证L536下划线、L2194连字符 |
| 6 | R9-Lit-7 | P0 | 虚假引用 | L2309 | "N. McKeen" → 实际"Jun Li"(arXiv:2410.04133) | ✅ 已验证L2309原文 |
| 7 | R9-Lit-8 | P0 | 虚假引用 | L2316 | "J. Li" → 实际"Jiarui Jin"(arXiv:2502.10707) | ✅ 已验证L2316原文 |
| 8 | R9-Lit-9 | P0 | 虚假引用 | L2331 | "X. Chen" → 实际"Xinran Liu"(arXiv:2607.15928) | ✅ 已验证L2331原文 |
| 9 | R9-Lit-10 | P0 | 虚假引用 | L2325 | "Y. Zhang" → 实际"Wenhan Jiang"(arXiv:2608.23347) | ✅ 已验证L2325原文 |
| 10 | R9-Lit-11 | P0 | 虚假引用 | L2322 | "R. S. Ali" → 实际"Sotirios Vavaroutas"(arXiv:2606.04164) | ✅ 已验证L2322原文 |
| 11 | R9-Lit-12 | P0 | 虚假引用 | L2328 | "A. Costa" → 实际"Nader Nemati"(单人作者, arXiv:2510.24740) | ✅ 已验证L2328原文 |
| 12 | R9-Lit-13 | P0 | 虚假引用 | L2319 | "S. N. Tan" → 实际"Cuong V. Nguyen"(PLOS ONE) | ✅ 已验证L2319原文 |
| 13 | R9-Lit-14 | P0 | 虚假引用(部分) | L2289 | 第一作者正确，第二三作者"G. Tiwari, M. Tack" → 实际"G. Radevski, T. Tuytelaars" | ✅ 已验证L2289原文 |

### 2.2 PARTIAL攻击点（28个，按级别排序）

#### P0降级PARTIAL（1个）

| # | Attack-ID | 原级别 | 降级后 | 内容 | 终审意见 |
|---|-----------|--------|--------|------|---------|
| 1 | R9-Design-1 | P0 | P1 | 5种子不足(CV=501%)，但bootstrap CI已量化不确定性 | **同意降级**：5种子+B=10,000 bootstrap的推断框架方法学上成立，不构成"方案完全失效" |

#### P1级PARTIAL（19个）

| # | Attack-ID | 维度 | 内容摘要 |
|---|-----------|------|---------|
| 1 | R9-Stats-3 | Stats | ResNet1D fixed-effect=-0.000573(z=-85.5)，"slightly negative"措辞低估 |
| 2 | R9-Stats-4 | Stats | 52/60个CI宽度<0.005，BH-FDR=Bonferroni=51/60，校正失去区分力 |
| 3 | R9-Stats-5 | Stats | 两层bootstrap未在主终点使用，实际使用单层 |
| 4 | R9-Stats-6 | Stats | 单侧检验在9/60实验ΔECE为负时不合适 |
| 5 | R9-Design-2 | Design | 仅2种架构(InceptionTime+ResNet1D)，BiMamba因OOM失败 |
| 6 | R9-Design-3 | Design | 3个数据集选择可能存在bias，HYP剔除影响 |
| 7 | R9-Novelty-1 | Novelty | C1"OOD benefit quantification"新颖性受Ovadia 2019先例质疑 |
| 8 | R9-Novelty-2 | Novelty | C2"ID boundary characterization"概念上不新 |
| 9 | R9-Novelty-4 | Novelty | C4"method selection boundary"比较已有先例 |
| 10 | R9-Novelty-5 | Novelty | C5"discrimination-aware gate"概念不复杂 |
| 11 | R9-Overclaim-2 | Overclaim | 效应量ΔECE=+0.0159与NCV噪声底同量级，无MCID讨论 |
| 12 | R9-Overclaim-4 | Overclaim | 9个反例的"机制解释"为post-hoc，不能用于"support"结论 |
| 13 | R9-Overclaim-5 | Overclaim | Conclusion内"reasonable default"与"moot"矛盾 |
| 14 | R9-Data-1至4 | Data | 4处CI下界偏差≥0.0005（BCa重算与CSV存储精度差异） |
| 15 | R9-Repro-1 | Repro | 缺少独立Code availability声明 |
| 16 | R9-Repro-3 | Repro | PyTorch/CUDA/Python版本未记录 |
| 17 | R9-Repro-4 | Repro | 训练时间未报告 |
| 18 | R9-Repro-6 | Repro | 62个checkpoint元数据完整性不足 |
| 19 | R9-LaTeX-2 | LaTeX | 3个图有label但从未被引用 |

#### P2级PARTIAL（7个）

| # | Attack-ID | 维度 | 内容摘要 |
|---|-----------|------|---------|
| 1 | R9-Stats-9 | Stats | NCV CI宽度是主终点10-15倍，"comparable"措辞不当 |
| 2 | R9-Design-6 | Design | 样本量n_patients=411偏小 |
| 3 | R9-Novelty-7 | Novelty | "first systematic characterization"措辞过强 |
| 4 | R9-Overclaim-6 | Overclaim | exploratory标签与"reasonable default"实践指导不匹配 |
| 5 | R9-Lit-18 | Lit | 未引用Ribeiro et al. 2020 |
| 6 | R9-LaTeX-3 | LaTeX | L872和L1807重复句子 |
| 7 | R9-LaTeX-4 | LaTeX | L1699和L1858重复句子 |

#### P3级PARTIAL（1个）

| # | Attack-ID | 维度 | 内容摘要 |
|---|-----------|------|---------|
| 1 | R9-LaTeX-5 | LaTeX | `$\Delta$ECE`与`$\Delta\text{ECE}$`表示法不一致 |

### 2.3 裁决分布汇总

| 裁决结果 | P0 | P1 | P2 | P3 | 合计 |
|---------|----|----|----|----|------|
| **SUSTAINED** | 13 | 0 | 0 | 0 | **13** |
| **PARTIAL** | 1(降级) | 19 | 7 | 1 | **28** |
| **OVERRULED** | 0 | 19 | 22 | 22 | **63** |
| **合计** | 14 | 38 | 29 | 23 | **104** |

---

## 3. 正方修补点汇总

### 3.1 P0级修补方案（13个SUSTAINED + 1个降级PARTIAL）

| # | Attack-ID | 正方修补方案 | 终审可行性评估 | 估计工作量 |
|---|-----------|-------------|--------------|-----------|
| 1 | R9-LaTeX-1 | L2194改`ncv-methods`为`ncv_methods` | **充分**（1行修改，机械操作） | 1分钟 |
| 2 | R9-Stats-1 | 方案A：重写L535-552匹配代码（Brier可靠性分解） | **充分**（方案A务实可行，重写~20行使描述与实现一致。方案B需重跑实验，非必要） | 2小时 |
| 3 | R9-Stats-2 | 以CSV为准更新L1316-1320，重算BCa CI | **充分**（以原始数据为准消除矛盾，需同步R9-Stats-1） | 4小时 |
| 4 | R9-Overclaim-1 | Abstract中并列报告85%和75% | **充分**（消除选择性报告，提高透明度） | 1小时 |
| 5 | R9-Overclaim-3 | 修改Conclusion"reasonable default"为限定声明 | **充分**（添加qualifications消除矛盾） | 2小时 |
| 6 | R9-Lit-7 | 替换"N. McKeen"为正确作者"Jun Li" | **充分**（直接更正，需验证arXiv页面） | 30分钟 |
| 7 | R9-Lit-8 | 替换"J. Li"为正确作者"Jiarui Jin" | **充分** | 30分钟 |
| 8 | R9-Lit-9 | 替换"X. Chen"为正确作者"Xinran Liu" | **充分** | 30分钟 |
| 9 | R9-Lit-10 | 替换"Y. Zhang"为正确作者"Wenhan Jiang" | **充分** | 30分钟 |
| 10 | R9-Lit-11 | 替换"R. S. Ali"为正确作者"Sotirios Vavaroutas" | **充分** | 30分钟 |
| 11 | R9-Lit-12 | 替换"A. Costa"为正确作者"Nader Nemati"（单人作者） | **充分** | 30分钟 |
| 12 | R9-Lit-13 | 替换"S. N. Tan"为正确作者"Cuong V. Nguyen" | **充分** | 30分钟 |
| 13 | R9-Lit-14 | 替换"G. Tiwari, M. Tack"为"G. Radevski, T. Tuytelaars" | **充分** | 30分钟 |
| 14 | R9-Design-1 | 补充种子聚合CI表（12个pair×arch组合） | **部分充分**（补充分析但不增加种子数，根本问题未解决） | 4小时 |

### 3.2 P0修补方案总体评估

**终审评估**：正方对全部13个SUSTAINED P0攻击提供了具体、可行的修补方案。

- **学术诚信类（8处）**：修补方案为直接更正作者信息，方案充分且工作量小（每处30分钟）。关键前提：必须逐条通过arXiv API或期刊网站验证实际作者列表，不可凭记忆更正。
- **方法学误述类（2处）**：方案A（重写NCV描述匹配代码）优于方案B（重跑实验），务实可行。但需注意：重写NCV描述后，NCV的统计含义需重新解释，可能影响论文的falsification check论证。
- **过度声称类（2处）**：修补方案为修改措辞，充分。但需注意：修改Abstract和Conclusion后，需检查全文论证链条是否一致。
- **编译错误类（1处）**：1行修改，充分。

**P0修补总工作量估计**：约1-2个工作日（含验证时间）。

### 3.3 P1级修补方案评估（关键项）

| Attack-ID | 正方方案 | 终审评估 |
|-----------|---------|---------|
| R9-Stats-4 | 增强窄CI解释 | **部分充分** — 需更深入分析CI宽度异常的统计原因 |
| R9-Stats-5 | 明确两层bootstrap为sensitivity analysis | **充分** |
| R9-Overclaim-2 | 添加MCID讨论段落 | **充分** |
| R9-Lit-1至6 | 补充6篇遗漏文献 | **充分** |
| R9-Repro-1/3/4 | 添加Code availability声明、环境信息 | **充分** |
| R9-Design-1/2/3 | 增加种子数/架构数的future work声明 | **部分充分** — 声明future work不等于解决问题 |

---

## 4. 置信度评估

### 4.1 对元审查裁决的置信度

**置信度：高**

| 评估维度 | 评估结果 | 依据 |
|---------|---------|------|
| P0裁决准确性 | **高** | 终审独立验证全部14个P0攻击的论文原文行号，13个SUSTAINED裁决全部正确，1个降级（R9-Design-1）合理 |
| P1/P2裁决合理性 | **高** | PARTIAL/OVERRULED分布合理，裁决理由清晰 |
| 独立性 | **高** | 元审查声明独立验证，终审复核确认其验证了论文原文 |
| 完整性 | **高** | 104个攻击点全部裁决，无遗漏 |

**终审独立验证结论**：
- ✅ 验证L536 `\label{sec:ncv_methods}`（下划线）— 确认
- ✅ 验证L2194 `\ref{sec:ncv-methods}`（连字符）— 确认不匹配
- ✅ 验证L541-542 "symmetric label permutation within each class" — 确认NCV描述
- ✅ 验证L1317-1320 NCV数值（ID:+0.0017, OOD:+0.0024）— 确认与CSV矛盾
- ✅ 验证L705 "85.0% robustness rate" — 确认选择性报告
- ✅ 验证L1908-1909 "45/60 (75.0%)" — 确认75%被埋藏
- ✅ 验证L1827 "reasonable default" — 确认过度声称
- ✅ 验证L1834 "safety rate 0.0064" — 确认与"reasonable default"矛盾
- ✅ 验证L2289-2334 全部8处bibitem作者信息 — 确认虚假引用

### 4.2 对正方修补方案充分性的置信度

**置信度：中高**

| 评估维度 | 评估结果 | 依据 |
|---------|---------|------|
| P0修补方案可行性 | **高** | 全部13个方案具体可行，工作量合理 |
| P0修补方案充分性 | **中高** | 方案A（重写NCV描述）充分，但NCV重写后可能引发新的论证链条问题 |
| P1修补方案充分性 | **中** | 大部分充分，但R9-Stats-4（窄CI）和R9-Design-1/2/3（种子/架构不足）仅部分充分 |
| 修补实施可能性 | **高** | 正方态度诚实，承认全部P0攻击，有明确修补意愿 |

### 4.3 对论文核心结论的置信度

**置信度：中**

论文的核心结论（51/60 support rate, TS as default with caveats）在修补P0后可能仍然成立，但存在以下残余风险：
- NCV重写后，falsification check的论证逻辑可能需要调整
- 75% vs 85%的修正可能影响论文的headline吸引力
- "reasonable default"的限定可能削弱论文的实践指导价值

---

## 5. 是否需要R10轮

### 裁决：**YES — 需要R10轮**

### 5.1 R10轮必要性理由

1. **P0修补需验证**：13个SUSTAINED P0攻击的修补方案虽充分，但修补实施后需独立验证：
   - NCV章节重写后是否与代码实现一致
   - 8处作者更正后是否与arXiv/DOI页面一致
   - Abstract/Conclusion修改后论证链条是否一致
   - LaTeX引用修复后PDF是否不再显示`??`

2. **P0修补可能引入新问题**：
   - NCV描述重写可能影响falsification check论证
   - 85%→75%修正可能引发审稿人对headline的进一步质疑
   - "reasonable default"限定可能需要全文措辞调整

3. **P1级PARTIAL攻击需收敛验证**：19个P1级PARTIAL攻击中，部分需要更深入的分析（如窄CI解释、MCID讨论），需验证修补是否充分。

### 5.2 R10轮重点验证项

| 优先级 | 验证项 | 验证方法 |
|--------|--------|---------|
| **P0-1** | NCV章节重写 | 比对新描述与代码实现（`run_e1b_loco_validation.py` L584-600, `run_e3_brier_dcr_ncv.py` L239-284） |
| **P0-2** | NCV数值更新 | 比对论文新数值与`c1_dcr_ncv_summary.csv` |
| **P0-3** | 8处作者更正 | 逐条通过arXiv API验证更正后的作者信息 |
| **P0-4** | Abstract 85%/75%并列 | 检查Abstract是否同时报告两个数字 |
| **P0-5** | Conclusion限定声明 | 检查"reasonable default"是否添加qualifications |
| **P0-6** | LaTeX引用修复 | 编译PDF检查不再显示`??` |
| **P1-1** | 窄CI解释增强 | 检查是否补充了kernel smoothing的方差缩减解释 |
| **P1-2** | MCID讨论 | 检查Discussion是否新增MCID段落 |
| **P1-3** | Code availability声明 | 检查是否新增独立Code availability section |

### 5.3 R10轮执行建议

**分两阶段执行**：

- **阶段1（P0修补验证）**：正方实施全部13个SUSTAINED P0修补 → 反反方验证修补充分性 → 若P0全部消除，进入阶段2
- **阶段2（P1收敛验证）**：反方对修补后论文发起R10轮攻击 → 验证P1级PARTIAL修补 → 收敛标准：SUSTAINED P0 ≤ 0 AND SUSTAINED P1 ≤ 5

---

## 6. 对SCI Q2投稿的具体建议

### 6.1 当前状态下的投稿建议

**建议：不投稿。立即进入P0修补阶段。**

理由：
- 13个SUSTAINED P0中，8处虚假作者引用构成学术不端，任何审稿人发现即触发即时拒稿并可能引发学术诚信调查
- NCV方法学误述（描述与实现完全不符）在code availability要求下必然暴露
- 未定义引用导致PDF显示`??`是格式审查的即时拒稿信号
- 选择性报告（85% vs 75%）在数据透明度要求下易被发现

### 6.2 修补后的投稿建议

| 修补阶段 | 投稿建议 | 接收概率 |
|---------|---------|---------|
| **当前状态** | **不投稿** — 13个P0均为即时拒稿信号 | Reject (90%) |
| **修补P0后** | **可投稿，预期Major Revision** — 28个PARTIAL攻击（含19个P1）需进一步修补 | Major Revision (60%) |
| **修补P0+P1后** | **可投稿，预期Minor Revision** — 剩余P2/P3问题可在revision中解决 | Minor Revision (70%) |
| **全部修补后** | **可投稿，预期Accept** — 论文核心贡献（empirical boundary study）有价值 | Accept (75-85%) |

### 6.3 接收概率估计详细分析

**当前状态 — Reject (90%)**：
- 8处虚假引用：任何一处被发现即触发学术诚信调查，概率极高
- NCV方法学误述：审稿人要求code时必然发现描述与实现不符
- 编译错误`??`：格式审查即拒
- 综合判断：90%概率被拒，10%概率审稿人未注意到（极低）

**修补P0后 — Major Revision (60%)**：
- 学术诚信问题消除
- 方法学描述与实现一致
- 但19个P1级PARTIAL问题仍存在：窄CI异常、两层bootstrap说明、MCID缺失、文献覆盖不足等
- SCI Q2审稿人可能要求major revision解决P1问题
- 综合判断：60%概率major revision，30%概率minor revision，10%概率reject

**修补P0+P1后 — Minor Revision (70%)**：
- P0和P1问题全部解决
- 剩余P2/P3问题（措辞、格式、minor数据偏差）可在minor revision中快速修复
- 论文的预注册框架、诚实披露、系统实验设计等优势显现
- 综合判断：70%概率minor revision，20%概率直接accept，10%概率major revision

**全部修补后 — Accept (75-85%)**：
- 论文核心贡献（ECG跨语料校准的empirical boundary study）有学术价值
- 预注册框架在ML领域是先进实践
- 60个实验的系统设计在ECG校准领域是全面的
- 综合判断：75-85%概率accept，15-25%概率reject（取决于审稿人对新颖性的判断）

### 6.4 投稿前检查清单

| # | 检查项 | 状态 |
|---|--------|------|
| 1 | 8处虚假引用已更正并验证 | ❌ 待完成 |
| 2 | NCV章节重写，描述与代码一致 | ❌ 待完成 |
| 3 | NCV数值与CSV一致 | ❌ 待完成 |
| 4 | Abstract并列报告85%/75% | ❌ 待完成 |
| 5 | Conclusion"reasonable default"已限定 | ❌ 待完成 |
| 6 | LaTeX引用修复，PDF无`??` | ❌ 待完成 |
| 7 | Code availability section已添加 | ❌ 待完成 |
| 8 | 6篇缺失文献已补充 | ❌ 待完成 |
| 9 | MCID讨论已添加 | ❌ 待完成 |
| 10 | 窄CI解释已增强 | ❌ 待完成 |

---

## 7. P0修补优先级排序

### 7.1 按修补紧急度排序

| 优先级 | # | Attack-ID | 类别 | 修补内容 | 紧急度理由 | 估计时间 |
|--------|---|-----------|------|---------|-----------|---------|
| **紧急-1** | 1 | R9-Lit-7至14 | 学术诚信 | 更正8处虚假作者引用 | 学术诚信问题最严重，任何审稿人发现即触发拒稿+调查 | 4小时 |
| **紧急-2** | 2 | R9-Stats-1 | 方法学误述 | 重写NCV方法描述匹配代码 | 方法学误述影响论文核心可信度 | 2小时 |
| **紧急-3** | 3 | R9-Stats-2 | 数据无法溯源 | 以CSV为准更新NCV结果 | 需与R9-Stats-1同步修复 | 4小时 |
| **紧急-4** | 4 | R9-Overclaim-1 | 选择性报告 | Abstract并列报告85%/75% | Abstract是审稿人第一印象，选择性报告严重影响可信度 | 1小时 |
| **紧急-5** | 5 | R9-Overclaim-3 | 声明与证据矛盾 | 限定"reasonable default"声明 | Conclusion是审稿人最后印象，与证据矛盾影响整体评价 | 2小时 |
| **紧急-6** | 6 | R9-LaTeX-1 | 编译错误 | 修复未定义引用 | 1行修改，最易完成 | 1分钟 |

### 7.2 修补时间估计

| 阶段 | 内容 | 估计时间 | 前置条件 |
|------|------|---------|---------|
| **阶段1** | 8处虚假引用更正 | 4小时 | 需逐条通过arXiv API验证实际作者 |
| **阶段2** | NCV章节重写+数据更新 | 6小时 | 需与R9-Stats-1同步，重算BCa CI |
| **阶段3** | Abstract/Conclusion修改 | 3小时 | 需检查全文论证链条一致性 |
| **阶段4** | LaTeX引用修复 | 1分钟 | 无 |
| **阶段5** | 编译验证+全文检查 | 2小时 | 需运行`latexmk -pdf main.tex` |
| **总计** | 全部P0修补 | **约1.5-2个工作日** | — |

### 7.3 修补后验证清单

| # | 验证项 | 验证方法 | 通过标准 |
|---|--------|---------|---------|
| 1 | 8处作者更正 | 逐条比对arXiv/DOI页面 | 8/8一致 |
| 2 | NCV描述与代码一致 | 比对论文L535-552与代码实现 | 描述匹配代码 |
| 3 | NCV数值与CSV一致 | 比对论文L1316-1320与`c1_dcr_ncv_summary.csv` | 数值一致 |
| 4 | Abstract并列报告 | 检查Abstract文本 | 同时包含85%和75% |
| 5 | Conclusion限定声明 | 检查L1827附近文本 | 包含qualifications |
| 6 | LaTeX编译无错误 | `latexmk -pdf main.tex` | 无undefined reference |
| 7 | PDF无`??` | 检查PDF输出 | 全文无`??` |

---

## 8. 对抗透明性记录

### 8.1 被驳回的反方攻击及驳回理由

**OVERRULED攻击共63个**，典型代表：

| Attack-ID | 级别 | 驳回理由 |
|-----------|------|---------|
| R9-Stats-7 | P2 | BCa delete-group jackknife问题已被代码自披露(R4轮登记)，主终点使用cluster不受影响 |
| R9-Stats-8 | P2 | SmoothECE带宽0.45是方法论选择，n^(-0.2)缩放指数与Silverman法则一致，非错误 |
| R9-Stats-10 | P2 | BH-FDR=Bonferroni是窄CI的下游后果，非独立攻击 |
| R9-Design-4 | P1 | A1修订案在主网格数据收集前登记，透明披露消除事后调整指控 |
| R9-Design-5 | P1 | 种子42-46是连续整数，ML社区标准默认，无cherry-picking证据 |
| R9-Novelty-3 | P1 | Shapley分解应用于ECG校准是新的应用，self-positioning合理 |
| R9-Novelty-7 | P2 | 论文L75明确声明"empirical boundary study"，未声称方法学新颖性 |
| R9-LaTeX-7 | P1 | Mamba vs BiMamba仅1处，上下文清晰，非严重混淆 |
| R9-Lit-15 | P3 | 自引比例2.9%，远低于20%警戒线 |
| R9-Lit-16 | P3 | 35篇引用，2024-2026占比37.1%，通过检查 |

**驳回总结**：63个OVERRULED攻击中，大部分为P2/P3级格式/措辞问题，或为非独立攻击（下游后果），或为论文已充分披露的局限。驳回理由充分，对抗是实质性的。

### 8.2 正方修补的所有点及修补方式

**正方承认并修补的攻击点共50个**，其中P0级13个、P1级多个。关键修补点：

| 修补类别 | 攻击点数 | 修补方式 | 修补状态 |
|---------|---------|---------|---------|
| 虚假引用更正 | 8 | 替换为正确作者 | 承认，未实施 |
| NCV章节重写 | 2 | 方案A：重写描述匹配代码 | 承认，未实施 |
| 过度声称修改 | 2 | 修改Abstract/Conclusion措辞 | 承认，未实施 |
| 编译错误修复 | 1 | 1行修改 | 承认，未实施 |
| 文献补充 | 6 | 添加缺失bibitem | 承认，未实施 |
| 可复现性增强 | 4 | 添加Code availability section | 承认，未实施 |
| 措辞调整 | 多个 | 修改不当措辞 | 承认，未实施 |

**修补状态总结**：正方已承认全部P0攻击并提供了具体修补方案，但**修补尚未实施**。这是NO-GO裁决的直接原因。

### 8.3 对抗收敛过程

| 轮次 | SUSTAINED P0 | SUSTAINED P1 | 收敛状态 | 说明 |
|------|-------------|-------------|---------|------|
| R9 | 13 | 0 | 未收敛 | 13个P0攻击全部SUSTAINED |
| R10(预测) | 0(若P0修补) | 0-5(若P1修补) | 可达收敛 | 前提：正方完成全部P0修补 |

---

## 9. 总结

### 9.1 最终裁决声明

**R9轮对抗审查终审判决：NO-GO**

论文《ECG跨语料校准的empirical boundary study》在R9轮对抗审查中，104个攻击点中有**13个P0级攻击被SUSTAINED**，涉及：
- **学术诚信**：8处虚假作者引用（R9-Lit-7至R9-Lit-14），2024-2026年文献中66.7%的引用存在作者信息篡改
- **方法学误述**：2处NCV描述与实现完全不符（R9-Stats-1, R9-Stats-2），论文描述"symmetric label permutation"但代码实现为"Brier reliability decomposition"
- **过度声称**：2处选择性报告和声明与证据矛盾（R9-Overclaim-1, R9-Overclaim-3）
- **编译错误**：1处未定义交叉引用（R9-LaTeX-1），PDF显示`??`

以上13个P0攻击均经终审代理独立验证论文原文行号确认。论文当前状态**不满足SCI Q2投稿门槛**，必须完成P0修补后进入R10轮重新审查。

正方已承认全部13个P0攻击并提供了具体、可行的修补方案，修补总工作量约1.5-2个工作日。修补后预测可达收敛（SUSTAINED P0 = 0），届时可进入R10轮验证P1收敛。

**接收概率估计**：
- 当前状态：Reject (90%)
- 修补P0后：Major Revision (60%)
- 修补P0+P1后：Minor Revision (70%)
- 全部修补后：Accept (75-85%)

### 9.2 关键风险提示

1. **学术诚信风险最高**：8处虚假引用不仅是拒稿问题，更可能触发期刊的学术诚信调查。建议正方在修补前自查是否存在系统性引用生成错误（如使用AI工具生成引用未验证作者信息）。
2. **NCV重写的连锁效应**：重写NCV描述后，论文的falsification check论证逻辑可能需要调整，需检查全文论证链条。
3. **75% vs 85%的影响**：修正后论文的headline吸引力下降，但诚实报告是SCI Q2的基本要求。

### 9.3 签名

**终审代理**: GLM-5.2
**日期**: 2026-09-13
**任务ID**: 55
**审查文件**: 8份反方攻击报告 + 1份正方反驳报告 + 1份反反方元审查裁决 + 论文原文`paper/main.tex`
**独立验证**: 已对全部14个P0攻击亲自验证论文原文行号
**裁决标准**: SUSTAINED P0 > 0 → NO-GO

---

*终审判决报告生成时间: 2026-09-13*
*终审代理: GLM-5.2*
*任务ID: 55*
