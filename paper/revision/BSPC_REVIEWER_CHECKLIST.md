# BSPC 返修清单（审稿人视角，带行号）

**稿件**: `paper/main_bspc.tex`（1897 行，编译产物 `main_bspc.pdf`）
**目标期刊**: Biomedical Signal Processing and Control (BSPC)
**审查基准**: BSPC 实际水平（Elsevier，JCR Q2 / 中科院 3 区，IF ≈ 5.1）
**清单生成**: 2026-09-16
**原则**: 本文件不改任何代码/论文，只标注问题、行号、审稿人话术与补救成本。

---

## 0. 结论摘要

### 0.1 BSPC 分区纠偏（重要）

你的目标定位是 **"SCI 2 区"**，但需要先纠正一个前提：

| 口径 | BSPC 的分区 |
|---|---|
| 中科院分区（2023 升级版） | **工程技术 3 区**（不是 2 区） |
| JCR 分区 | **Q2** |
| 影响因子 | ≈ 5.1 |

如果你说的"2 区"指 **JCR Q2**，那么是**成立**的。如果指**中科院 2 区**，BSPC 是**3 区**，需要在投稿策略上重新确认（中科院 2 区同学科更接近 *Computers in Biology and Medicine*，IF ≈ 7.0，但那本对方法学新颖性要求更高）。

> 下文所有"是否够格"的判断，按 **BSPC（Q2/3区，IF 5.1）的真实标准**给，不按 CBM 标准给。这是个重要的好消息：本文的工程扎实度**明显超过 BSPC 中位稿件**。

### 0.2 总判：够格，但有一处必须先修的硬伤

| 结论 | 说明 |
|---|---|
| **方法学扎实度** | ✅ 超过 BSPC 中位数。60 次平衡实验、预注册协议+A1/A2 修订案、OSF DOI 归档、BCa B=10,000、诚实披露 9 个反例、自曝 I²≈99.98% 与 CI 不可引用——这套"自我攻击+坦诚披露"的完成度在 BSPC 里属于上游。 |
| **可以投吗** | ⚠️ **先修 §1.1（仓库链接不一致）**，其余可带 minor revision 投。 |
| **最大风险** | 不是算法深度不够，而是 **1 个可立即验证的事实性错误** + **审稿人对"只有 2 个 CNN 骨干"的泛化性质疑**（你列的 4 条薄弱点里，只有这条是真问题，见 §3）。 |
| **你列的 4 条薄弱点** | 2 条是真问题（架构多样性、I² 处理），1 条是**误判**（post-hoc baseline——你已经做了 8 种，见 §3.3），1 条待补（SQI/临床）。 |

---

## 1. 立即修复项（论文文本 + 仓库元数据，不动实验，最低风险）

### 1.1 【P0 · 硬伤】仓库 URL 双版本混用

**这是目前唯一"会被审稿人当场发现、且属于事实性错误"的问题。**

**证据（论文侧）**：
- L1699：`\url{https://github.com/Toni-cs/ecg-calibration-transportability}`
- L1712：同上（Code availability 重复一次）

**证据（仓库侧，实测）**：
- 活仓库 `github.com/Toni-cs/ecg-calibration-transportability` **存在但处于混合状态**：
  - README 正文链接已指向 `Toni-cs`（如 `docs/`、`splits/`）
  - 但 **release 链接仍指向旧仓库**：`github.com/gt17641001169-design/ecg-calibration-transportability/releases/tag/v1.0.0`
  - **CITATION.cff 的 `url` 字段仍指向旧仓库**
  - **Contact 段的 issue 链接仍指向旧仓库**
- 本地 git remote 也仍是旧仓库：
  - `origin → https://github.com/gt17641001169-design/ecg-calibration-transportability.git`

**审稿人话术**：
> "The Code Availability statement points to `Toni-cs/ecg-calibration-transportability`, but the linked README's release, citation, and issue links resolve to a *different* account (`gt17641001169-design`). I could not determine which repository is authoritative. Please reconcile."

**补救动作（全部为 (a) 类，可立即执行）**：
1. 决定 **哪一个仓库是权威记录**（建议保留 `Toni-cs`，与你论文署名 `Toni Guan` 一致）。
2. 在权威仓库中修正 3 处：README 的 release 链接、`CITATION.cff` 的 `url`、README 的 Contact/issue 链接。
3. 旧仓库设为 GitHub **Archive** 或 redirect，并在 README 顶部加一行 "This repository has moved to …"。
4. 本地执行 `git remote set-url origin https://github.com/Toni-cs/ecg-calibration-transportability.git` 并推送。
5. 重编译 `main_bspc.tex`（URL 文本无需改，但需确认 PDF 内链接可解析）。

### 1.2 【P1】预注册协议指向的 OSF 归档与新仓库不可互证

**证据**：L1700-1703 — 协议、A1/A2 修订案归档于 `https://doi.org/10.17605/OSF.IO/53H64`，同时 L1702 自述 `docs/osf_archive_manifest.json` 是 2026-09-05 的内部快照，"not a substitute for the public record"。

**审稿人话术**：
> "The manuscript relies on a pre-registered protocol as its central methodological guarantee. Please confirm that the hash manifest in the repository matches the OSF record, and state explicitly whether the OSF deposit is under the same author identity."

**补救动作（(a) 类）**：
- 在 L1702 附近补一句：OSF 归档与仓库 manifest 的 SHA-256 比对结果（一致/不一致），并给出比对脚本路径。
- 确认 OSF 账号身份与论文作者一致（你已改名 `Toni-cs`，OSF 那边若还是旧名会引发身份核验问题）。

### 1.3 【P1】架构命名全文不统一

**证据（实测计数）**：
- `ResNet1D` 出现 **44 次**
- `1D-ResNet-34` 出现 **3 次**（L203 图注、L914 正文、以及 L343 附近）
- 表格中缩写 `Incep` **6 次**，正文 `InceptionTime` 全文

**审稿人话术**：
> "The same architecture is referred to as both 'ResNet1D' and '1D-ResNet-34' and abbreviated as 'Incep' in tables. Please use one consistent nomenclature."

**补救动作（(a) 类）**：全文统一为 `ResNet1D`（正文/表格）并在首次出现处注明 "1D-ResNet-34 backbone"；表格缩写 `Incep` 改为 `IT` 并在表注定义（`IT` 已在 Table 4 的 L706 等处使用，需一并统一）。

### 1.4 【P2】CI 方法术语残留矛盾（历史遗留，已有部分修复）

**证据**：
- L406-416 已正确声明 "The pre-registered CI method is BCa … percentile CIs serve only as a sensitivity cross-check" ✅
- L546 表注已为 "BCa operating CI" ✅
- 但 L426-427 仍写 "Observed (BCa, full-grid re-run): 23/60 = 38.3%; … (percentile CIs gave 29/60 = 48.3%)"，与 L62、L697 的表注表述**并存但表述口径不一**

**审稿人话术**：
> "Section 4.4 states BCa is the operating CI and percentile is a sensitivity check, yet Section 4.4's boundary-condition text interleaves both counts without labelling which is primary."

**补救动作（(a) 类）**：把 L426-427 与 L729-730 的 percentile 数字统一降级为括注 "sensitivity cross-check (percentile, B=10,000)"，确保**主数字永远是 BCa**。

### 1.5 【P2】5 个缺日志实验未列出 ID

**证据**：L556 附近 Limitations (vii)："percentile CIs from $B=200$ in 21/60 experiments are retained as historical provenance (5 lack logs)"。

**审稿人话术**：
> "Five experiments lack provenance logs. Please identify them explicitly and state whether their main-endpoint numbers were independently reproducible."

**补救动作（(a) 类）**：在 Limitations (vii) 附列这 5 个实验的 (pair, arch, seed) 元组，并说明其主终点数字来自 BCa 全网格重跑（不依赖缺失日志）。

---

## 2. 方法学补强项（需写脚本/跑实验，(b) 类）

### 2.1 【P1】架构泛化性：只有 2 个 CNN 骨干 ← **你的第 1 条薄弱点，真问题**

**当前状态**：L342-346 — InceptionTime（主）+ ResNet1D（次），BiMamba 仅 toy（n=60, 因 RTX 5060 8GB OOM）不入主终点。

**审稿人话术（BSPC 版，比你写的那句更狠）**：
> "Both backbones are convolutional. The paper's central claim is about *when* TS pays off under *distribution shift*, which is an architectural property, yet the architecture ablation covers only two CNN variants of similar inductive bias. Without at least one non-convolutional backbone (transformer or state-space), the boundary conditions reported may be a property of CNNs, not of cross-corpus ECG transfer."

**补救动作**：
- **(b) 类最小可行**：加 1 个 Transformer 骨干（ECG 领域现成的 `ECG-FM` 或 `HeartLang` 权重，你已在 L266-291 Related Work 里引了）跑 **1 个 corpus pair × 5 seeds**，仅作 architecture ablation，不并入主终点。**成本：需重训，但只需 1 个方向。**
- **(b) 类更省**：若时间/显存不允许重训，则把"仅 2 个 CNN 骨干"**明确升级为独立 Limitation 条目**，并在 Abstract 加限定语 "for convolutional backbones"。**这不是完美解，但 BSPC 接受诚实限定。**
- **不建议**：硬做 architecture ablation table 却只有 2 行——审稿人会说 "two architectures is not an ablation, it is a comparison"。

**风险提示**：此条若重训，**不触碰 `train.py` 核心逻辑**，只是新增训练配置，属低-中风险。

### 2.2 【P1】I² ≈ 99.98% 之后为何还报 pooled effect ← **你的第 2 条薄弱点，真问题**

**当前状态（比你想的好）**：L1629-1643 已做大量补救：
- 已给出 DerSimonian–Laird random-effects（InceptionTime +0.0151, ResNet1D +0.0158, Cross +0.0148）✅
- 已明确声明 FE/DL 的 CI "spuriously narrow"、不可引用 ✅
- 已改用 **cluster-robust 12-stratum interval**: `+0.0159 [0.0113, 0.0205]` 作为可解释的 pooled uncertainty ✅

**审稿人仍会问的**：
> "If I² ≈ 100% and the FE/DL intervals are admittedly unquotable, why report a pooled point estimate at all? A pooled mean is not a meaningful summary of a heterogeneous collection of non-independent cells. Consider dropping the pooled estimate entirely and presenting only per-pair results."

**补救动作**：
- **(b) 类**：补 **prediction interval**（不是 CI）。DL 随机效应下的 prediction interval 会把异质性显式体现为宽区间，正好回应"pooled 值不可信"的质疑，且**只需在现有 DL 输出上加一步计算，无需重跑实验**。
- **(a) 类（更省，推荐）**：把 pooled 值在正文中显式标为 **"descriptive only"**，并在 Abstract/Conclusion 中**不再引用任何 pooled 数字**，主推 per-pair（已有 Table 1 全 60 行 + Table 4 的 12 strata）。你的 Abstract（L67-80）目前确实没用 pooled 值，做得**对**；只需在 Conclusion L1629 段落加一句限定。

**判**：此条你**基本已经解决**，只差一句 "descriptive only" 的显式标签 + 可选的 prediction interval。归为 **(a) 类即可**。

### 2.3 【P1】SmoothECE 与 TS 的耦合未被量化 ← **你没列，但审稿人会打**

**这条比你列的 4 条里任何一条都更可能致命**，因为 BSPC 是 *signal processing* 期刊，审稿人对 metric 的定义极度敏感。

**当前状态**：L1074-1104 有 "Noise floor control" 一节，做了 perfect-calibration 下的噪声底噪实验（T ∈ {1.0,1.25,1.5,3.0,4.5}，三种置信度分布，n=2000）。

**但审稿人会指出**：
1. 该实验的 `T` 网格是**人工设定**的，而真实实验里的 `T` 是**在 source cal 上拟合出来的**，两者分布不同。
2. L381 的 bandwidth `h = 0.45·(n/2000)^(-0.2)` 随 n 变化，而噪声底噪实验固定在 n=2000。**bandwidth 与 T 的交互项完全未被检验**——这正是"SmoothECE 耦合"问题的核心。
3. 主终点的 DE 单位是 "ECE points"，但不同 n 下 h 不同 → **不同实验的 SmoothECE 不是同一把尺子**，跨实验平均（如 pooled、51/60 计数）在计量学上不严格。

**审稿人话术**：
> "SmoothECE is a bandwidth-parameterised kernel estimator. The bandwidth depends on n (Eq. in Sec. 4.4), and the paper's headline is a cross-experiment average of ΔECE over 60 cells whose n differ. The noise-floor control fixes n = 2000, so it does not bound the bandwidth–temperature coupling that the authors themselves flag. Please quantify ΔECE_SmoothECE sensitivity to (h, T) jointly."

**补救动作（(b) 类，明确可做）**：
- 把噪声底噪实验扩为 **2D 网格：(h, T) 联合扫描**，h 取 `{0.284, 0.45, 0.594}`（对应你代码注释里的 n=20000/2000/500），T 取现有网格。产出：(h,T) → ΔECE_noise 热图。
- 关键结论只要求一句："在所有 (h,T) 组合下，最坏噪声 ≤ X，仍低于观测 ΔECE 的 Y%"。
- 代码落点：`src/utils/calibration.py:279 smooth_ece()` 已支持显式 `bandwidth=` 参数（见其 docstring "固定带宽敏感性可显式传 bandwidth=0.45 复现旧行为"），**无需改核心逻辑，新写一个 sweep 脚本即可**。

### 2.4 【P2】G 终点声明交付但未交付

**证据**：
- L429：`Secondary endpoints: $G$ (recoverable loss vs.\ oracle), …` — 声明为 secondary endpoint ✅
- L362：`CORAL, TTA, MC-Dropout, and Oracle are not delivered on real data` — 但 Oracle 缺失意味着 **G 无法计算**
- `results/` 全目录 grep `oracle` **零命中**
- **仓库 README（实测）**：明确写 "…primary endpoint D_ECE_OOD…; **distinct from the undelivered secondary endpoint G** = ECE_S1 − ECE_oracle"

**审稿人话术**：
> "Section 4.4 lists G as a secondary endpoint, but Section 4.3 states Oracle was not delivered. G is therefore undefined. The repository README confirms it is 'undelivered'. Please remove G or define an oracle-free surrogate."

**补救动作（(a) 类）**：三选一 —
1. 从 L429 删除 G（最省，推荐）；
2. 改为 "G (not delivered; see Limitations)"；
3. `\sout{G}` 保留但显式标为未交付。

**注意**：这是一个**论文自述与仓库自述互相印证为"未交付"、但论文正文仍列为 endpoint 的表述不一致**，属于 (§1) 类可立即修复项。

---

## 3. 复核你列的 4 条薄弱点

### 3.1 "仅 2 种架构" → ✅ **你的判断正确**，见 §2.1。

### 3.2 "I² ≈ 99.98% 极端异质性" → ⚠️ **部分已解决**，见 §2.2。
你已做 DL + cluster-robust 区间，比你自己估计的进度更靠前。只剩"descriptive only"标签。

### 3.3 "Temperature Scaling 是 post-hoc 中最弱的 baseline" → ❌ **你的判断有误**

**这是本次审查最重要的纠正。** 你的论文主干 **根本不是只跑 TS**：

- L356-359：8 种重校准方法 — **TS、per-class Platt、Isotonic (OvR)、Vector scaling、Matrix scaling、Dirichlet calibration、Saerens EM、BBSE**
- `src/utils/calibration_methods.py` 实测已实现：`fit_isotonic`、`fit_vector_scaling`、`fit_matrix_scaling`、`fit_dirichlet`、`fit_saerens_em`、`fit_temperature_multiclass`、`fit_platt_multiclass` ✅
- L790-797 Table 3：8 方法 × 6 pair 的完整支持率表 ✅

**你提到的四种，三种已经在做**：Matrix Scaling ✅、Platt Scaling ✅、Isotonic Regression ✅。
**唯一缺的是 Mix-n-Match**（Zhang et al. 2020，ICML），它是*ensemble* calibration，与你的单模型 post-hoc 设定不同类。

**所以正确的定位是**：你不是"只跑 TS"，而是"**以 TS 为主终点 + 8 方法边界对比**"。审稿人真正会问的**不是**"为什么只跑 TS"，而是：
> "TS is presented as the *robust default*, yet Platt achieves 24/30 vs TS 27/30 and a *higher* mean ΔECE (+0.0169 vs +0.0152, Table 3). On what basis is TS singled out as the recommended default rather than Platt?"

**这条才是真问题。** 补救（(a) 类，纯写作）：在 §5.3 或 §6.2 增加一段 "why TS over Platt"，理由可用：(i) 单参数 vs 2 参数的正则化优势；(ii) Platt 的 OvR 结构破坏排序不变性（你代码 `apply_isotonic` docstring 已声明破坏排序，Platt 同理）；(iii) argmax 不变性只对 TS 严格成立。

> **建议**：把这条从你的"薄弱点清单"中**划掉**，换成上面这条"为何 TS 优于 Platt"。你原清单里的这条如果写进 cover letter 的 response，会**主动暴露一个并不存在的弱点**，反而给审稿人递刀。

### 3.4 "无外部临床/信号质量验证" → ✅ **你的判断正确**，见 §4.1。

---

## 4. BSPC 特有的审稿维度（信号处理 + 转化相关性）

### 4.1 【P1】无 SQI / 信号质量分层 ← **BSPC 核心关切**

**实测证据**：`main_bspc.tex` 中 `SQI` 仅出现在 L282、L1882 的 **Related Work 引用**（描述别人的工作），本文**自己的分析中零 SQI**。`src/`、`scripts/` 全目录 grep `sqi` **零命中**。

**审稿人话术（BSPC 编辑最可能直接发这句）**：
> "This journal's readership is signal-processing oriented. The paper treats cross-corpus transfer as a label/prior shift problem but never characterises the *signal-level* differences (sampling rate, lead configuration, noise, electrode placement). The L2 shift matrix (Sec. 4.1) injects synthetic noise, but no real signal-quality stratification is performed. Given that 'calibration degradation under acquisition shift' is the stated motivation (L228-231), a signal-quality-conditioned analysis is expected."

**补救动作**：
- **(b) 类（首选）**：用标准 SQI（如 `pSQI`, `kSQI`, `basSQI`，或现成的 `neurokit2` / `ecg-kit`）对 target 测试集**分层**，报告各 SQI 分位下的 ΔECE。若 ΔECE 在低 SQI 段显著偏移，这是**强 novelty**（正好呼应 L1074 的 noise floor）。
- **(a) 类（降级）**：若无法新跑，在 Limitations 增加一条 "(xviii) no SQI-conditioned analysis; the L2 noise grid is synthetic"，并把 Abstract 的"translational"措辞改为 "algorithmic"。

### 4.2 【P2】无 short-term stability / test-retest

**实测证据**：`main_bspc.tex` grep `test-retest|repeatab|stability` → **零命中**（仅在 `T` 稳定性的意义上有零星表述）。

**审稿人话术**：
> "Calibration is presented as a deployment-time decision. Is the fitted temperature stable across sessions for the same patient? Without a test-retest or repeatability analysis, the deployment gate cannot be validated."

**补救动作（(a) 类，推荐）**：放入 Limitations。理由充分且诚实：本文使用的三个公开语料库**均为横断面、每患者单次记录**（Chapman L309-310 已写明 "1 ECG per patient"），**数据结构上就不支持 test-retest**。这句话本身就是对审稿人的完整回答，**不需要新实验**。

> 建议措辞："(xix) None of the three public corpora provides repeat recordings for the same patient (Chapman-Shaoxing: one ECG per patient), so a test-retest stability analysis of the fitted temperature is not possible within this data regime; prospective multi-session validation is registered as future work."
>
> 注意：你的 Future work (1) "prospective multi-device validation" 已覆盖此方向 ✅，只需在 Limitations 里把"为何做不了"讲清楚。

### 4.3 【P2】5-class 主分析 vs 4-class subspace 的口径

**证据**：L311-314 — CPSC 因 HYP 极稀有（n=11）降为 4 类子空间 `{NORM, CD, STTC, MI}`，"both sides of the pair recomputed symmetrically" ✅；L300-306 — PTB-XL 单标签映射后 21,522。

**但**：L378 主终点定义为 "4-class confidence SmoothECE"，而 Chapman/PTB-XL 侧原本是 5 类体系。**6 个 pair 中有几个是 4 类、几个是 5 类？** 论文未在 Result 表内标注每个 pair 的类别数。

**补救动作（(a) 类）**：在 Table 1 增加一列 `K`（类别数），或在 L311 后加一句明确列出 6 个 pair 各自的 K。这是审稿人复核时的必查项。

---

## 5. 内部一致性与数字核对

| 检查项 | 状态 | 证据 |
|---|---|---|
| 贡献数量 4 vs 5 | ✅ 已修 | L135 "Five independent contributions" + C1–C5 齐备 |
| 期望值算式 `0.85×0.0195 − 0.15×0.0047 = +0.0159` | ✅ 正确 | 0.016575 − 0.000705 = 0.01587 ≈ 0.0159 |
| 51/60 支持率 | ✅ 与 Table 1 一致 | 60 行逐行复核，9 个 ✗，51 个 ✓ |
| ID 23/60 含零 | ✅ 与 Table 2 一致 | Table 2 的 CI∩0 列求和 = 1+2+1+0+3+4+3+3+2+2+2+0 = 23 ✅ |
| "85%" 算术 | ✅ | 51/60 = 85.0% |
| "1.9×" | ✅ | 0.0159/0.0083 = 1.916 ✅ |
| 表 4 的 27/30+24/30=51/60 | ✅ | 一致 |
| Limitations 编号 (i)–(xvii) 连续 | ✅ | 已含 (xvi) n_filters、(xvii) 单作者 |
| 术语 `Incep` vs `InceptionTime` | ⚠️ | 见表中 6 处，见 §1.3 |
| 术语 `ResNet1D` vs `1D-ResNet-34` | ⚠️ | 44:3 混用，见 §1.3 |
| G 终点交付状态 | ❌ | 声明交付但未交付，见 §2.4 |

**注意**：L1229 那句 "0.4779 in earlier drafts is the OOD **accuracy**" 是**主动披露历史笔误**——这在审稿中是加分项，保留。

---

## 6. 建议执行顺序（风险由低到高）

### 第 1 轮 — 立即执行，不重编译风险
1. **§1.1 仓库 URL 统一**（P0，唯一硬伤）— 改仓库元数据 3 处 + `git remote set-url` + 可选 archive 旧库
2. **§2.4 G 终点**（删除或标注未交付）
3. **§1.3 术语统一**（ResNet1D / IT）
4. **§1.4 CI 术语降级**（percentile 统一为 sensitivity cross-check）
5. **§1.5 5 个缺日志实验列 ID**
6. **§4.3 Table 1 加 K 列**
7. **§3.3 "为何 TS 优于 Platt" 段落**（替换你原清单里的误判项）
8. **§2.2 加 "descriptive only" 标签**
9. **§4.1 + §4.2 Limitations 新条目 (xviii)(xix)**
10. 重编译 `main_bspc.tex` → `main_bspc.pdf`

### 第 2 轮 — 需写脚本，不改核心训练逻辑
11. **§2.3 (h, T) 二维耦合扫描**（新脚本，复用 `smooth_ece(bandwidth=…)`）
12. **§4.1 SQI 分层分析**（新脚本，target 集分层 + ΔECE 分位报告）
13. **§2.2 prediction interval**（在现有 DL 输出上加一步）

### 第 3 轮 — 高风险，可能改动主终点
14. **§2.1 非 CNN 骨干**（1 pair × 5 seeds，新训练配置）
    ⚠️ 若时间不允，改为 Limitations 限定语 "for convolutional backbones"，**不要动主终点**

---

## 7. 最终判词

**本文投 BSPC：够格。** 与 BSPC 已发表同类工作（如 L251-260 引的 Barandas 2024 *Information Fusion*、Vranken 2021 *EHJ-DH*）相比，本文的**多 seed 预注册闭环 + 全反例披露 + 自曝异质性**在方法学诚信度上明显更强。

**三个必须做**：
1. 修仓库 URL 不一致（**否则审稿人会认为代码不可复现**，这是唯一可能直接导致 reject 的因素）
2. 给自己论文的"2 个 CNN 骨干"加限定语，或补 1 个 Transformer
3. 补 (h, T) 耦合分析或 SQI 分层——**BSPC 是信号处理刊，metric 定义与信号质量的辩护不能缺**

**一个不要做**：不要在 response letter 里写"我们只跑了 TS 作为 baseline"。你跑了 8 种，主动认领一个不存在的弱点是最亏的。

---

*清单完毕。本文件不改任何代码或论文正文，仅作返修定位用途。*
