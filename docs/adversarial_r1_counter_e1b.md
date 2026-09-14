# 反反方审查报告 - E1b LOCO跨语料库泛化验证

> **反反方审查代理（元审查者）交付**。本报告对反方挑刺代理-E1b 的攻击报告（`adversarial_r1_attack_e1b.md`）进行逐条裁决，判定每个攻击点是否有效。
> **审查日期**：2026-09-09
> **审查对象**：反方攻击报告 20 个攻击点（F1-F5, S1-S10, M1-M5）+ 矛盾分析 S11
> **被攻击脚本**：`scripts/run_e1b_loco_validation.py`（revision 6709813f, 863 行）
> **审查代理**：反反方审查代理（GLM-5.2）
> **审查标准**：是否稻草人论证 / 是否误解正方意图 / 反例是否真的成立 / 攻击逻辑是否自洽

---

## 审查摘要

- **攻击点总数**：21（5 致命 + 10 严重 + 5 轻微 + 1 矛盾分析 S11）
- **驳回**：0
- **部分成立**：9（F2, F3, F4, F5, S5, S6, S7, S8, M5）
- **成立**：12（F1, S1, S2, S3, S4, S9, S10, S11, M1, M2, M3, M4）
- **需要修补的**：21（全部有不同程度的修补需求）

### 裁决分布

| 严重性 | 总数 | 成立 | 部分成立 | 驳回 |
|--------|------|------|---------|------|
| 致命 (F) | 5 | 1 | 4 | 0 |
| 严重 (S) | 11 | 7 | 4 | 0 |
| 轻微 (M) | 5 | 4 | 1 | 0 |

### 总体评价

反方攻击整体质量较高，20 个攻击点中无一被完全驳回——反方确实做了扎实的代码审查工作。但反方在 9 个攻击点上**夸大了严重程度**或**误读了正方的设计意图**，这些攻击应从"致命/严重"降级。最典型的夸大模式是：将"已文档化的近似局限性"当作"未发现的致命缺陷"来攻击。

**最需要优先修补的真正问题**：F1（NCV CI 伪造）、S3（全 4 类退化）、S11（E1a-E1b 不一致）、S9（docstring 错误）。

---

## 逐条审查

### F1：NCV 的 CI 用 ΔECE 的 CI 冒充——fabrication 而非 approximation

**位置**：L583-584

**裁决**：**成立**

**理由**：

反方攻击完全成立。代码确实存在点估计与 CI 来自不同度量的问题：

```python
ncv_point = delta_reliability    # Brier reliability 差（Murphy 分解的 reliability 分量）
ncv_ci = delta_ece_ci            # Smooth ECE 差的 BCa CI（完全不同的度量）
```

验证：
1. `delta_reliability = rel_raw - rel_cal`（L553），其中 `rel_raw/rel_cal` 来自 `brier_parts()`（L551-552），是 Murphy 分解的 reliability 分量——分箱平方误差。
2. `delta_ece_ci = ben["benefit_ci"]`（L566），来自 `benefit_inference(raw_mp, cal_mp, cal_correct, metric=metric_fn)`（L560-564），其中 `metric_fn = smooth_ece`——核平滑绝对误差。
3. 两个度量的定义、尺度、bootstrap 分布形状均不同，不存在可证明的收敛关系。

反方说"这不是近似，是 fabrication"——虽然"fabrication"一词过重（代码注释 L581-582 和 CSV note 字段 L646 都明确标注了"近似"），但核心论点正确：用不同度量的 CI 代替目标度量的 CI，在统计学上无效。即使标注为"近似"，下游分析者仍可能误用此 CI 做推断。

**修补方案**：

实现 Brier reliability 的 cluster bootstrap CI。在 `_eval_scenario` 中替换 L578-584：

```python
# --- NCV (Net Calibration Value) ---
# = delta_reliability，用 Brier reliability 自身的 cluster bootstrap 出 CI
def _reliability_metric(probs, correct):
    """Brier reliability 作为 benefit_inference 的 metric"""
    _, rel, _, _ = brier_parts(probs, correct)
    return rel

ben_rel = benefit_inference(
    raw_mp, cal_mp, cal_correct,
    metric=_reliability_metric, n_bootstrap=args.bootstrap, rng=rng,
    clusters=test_clusters, bci_method=args.bci_method,
)
ncv_point = ben_rel["benefit"]
ncv_ci = ben_rel["benefit_ci"]
```

注意：`brier_parts` 内部有 10-bin 分箱，在 bootstrap 重采样上重算分箱是正确的（每次重采样重新分箱）。成本：B=10000 次 `brier_parts` 调用，每次 O(n)，总成本 O(B·n) ≈ 10000×4000 = 4×10⁷，秒级。

---

### F2：DCR 定义在 docstring 与代码间自相矛盾

**位置**：L64-66（docstring）vs L570-576（实现）

**裁决**：**部分成立**

**理由**：

反方正确指出了 docstring 与代码的不一致：
- docstring（L64-66）说"Brier reliability < 阈值"
- 代码（L573-576）算的是 per-sample raw Brier `(cal_mp - cal_correct)² < 阈值`

但反方将此定性为"致命"夸大了影响。关键事实：

1. **代码注释已自我说明**（L570-572）：
   ```python
   # 逐样本 reliability 需分箱，这里用全局 reliability 作为部署判据
   # DCR = 1{rel_cal < threshold}（fold 级判据）
   # 分样本 DCR：用每个样本的 (p-y)^2 作为逐样本 Brier，校准后 < 阈值的比例
   ```
   代码注释明确解释了为什么用 per-sample Brier 而非 reliability（"逐样本 reliability 需分箱"——单样本无法分箱），说明这是**有意识的设计选择**，不是错误。

2. **per-sample Brier 作为部署判据是合理的操作定义**：`(p-y)² < threshold` 衡量"该样本的预测是否足够准确"，这是部署安全性的自然定义。fold 级 reliability 是群体级量，无法给出"哪些样本可部署"的 per-sample 判据。

3. **反方的反例有误**：反方说"完美校准但分辨率低的模型，reliability=0 但 per-sample Brier 可能很大"。但 `brier_parts` 的 reliability 是在 max-prob 和 correctness 上计算的（L551-552），不是在原始概率上。完美校准（reliability=0）意味着每个 bin 的 avg_prob=avg_correctness，但 per-sample Brier 仍反映个体误差——这正是 DCR 想要衡量的。

**实际影响**：docstring 误导，应修正。但代码行为本身是合理的部署判据。严重性应从"致命"降为"严重"（文档-代码不一致）。

**修补方案**：

修正 docstring（L64-66）为：

```python
DCR (Deployment Calibration Rate) = 在目标域上，校准后 per-sample Brier score
    (max_prob - correct)² < SAFE_RELIABILITY_THRESHOLD 的样本比例。
    衡量 "可安全部署" 的 per-sample 覆盖率。
    注意：per-sample Brier ≠ Murphy reliability 分量；前者是逐样本误差，
    后者是分箱群体级量。此处用 per-sample Brier 因部署判据需 per-sample 粒度。
```

---

### F3：per-sample Brier 退化为置信度阈值检查

**位置**：L573-576

**裁决**：**部分成立**

**理由**：

反方的数学推导正确：对 per-sample Brier `(cal_mp - cal_correct)²`：
- 正确预测：`(1 - conf)² < 0.05` ⟺ `conf > 0.776`
- 错误预测：`conf² < 0.05` ⟺ `conf < 0.224`

因此 DCR = P(正确 ∧ conf>0.776) + P(错误 ∧ conf<0.224)。

但反方对此的解读有误：

1. **"退化为置信度阈值检查"不是缺陷，而是 per-sample Brier 的数学本质**。per-sample Brier 本就是 `(p-y)²`，对二值 y 自然退化为置信度判据。这不是"退化"，而是"展开"——DCR 的语义是"模型在哪些样本上既准确又自信，或在哪些样本上虽错误但不自信"，这恰恰是部署安全性的合理定义。

2. **反方的反例（conf=0.5 模型）反而证明 DCR 工作正确**：一个对所有样本输出 conf=0.5 的模型，DCR=0%。反方说"该模型 fold 级 reliability 可能很低，按 docstring 定义 DCR 应接近 100%"。但一个永远 50/50 的模型**不应该**被认为"可安全部署"——它没有任何判别能力。DCR=0% 是正确行为：部署安全需要**同时**满足校准好和判别好，conf=0.5 模型判别为 0，不应部署。

3. **反方关于 threshold 敏感性的批评有效**：DCR 对 threshold 确实敏感（threshold=0.05→conf 边界 0.224/0.776；threshold=0.01→0.1/0.9），脚本确实未报告敏感性分析。这是合理的补充需求。

**实际影响**：threshold 敏感性分析缺失，应补充。但 DCR 的"退化为置信度阈值"本身不是问题——这是 per-sample Brier 的数学性质，且作为部署判据是合理的。严重性从"致命"降为"严重"。

**修补方案**：

1. 补充 threshold 敏感性分析，在 `_eval_scenario` 中增加：
   ```python
   # DCR threshold 敏感性
   for thr in [0.01, 0.02, 0.05, 0.10]:
       dcr_cal_thr = float(np.mean(per_sample_brier_cal < thr))
       records.append({**base, "metric": f"dcr_cal_thr{thr}",
                       "value": dcr_cal_thr, ...})
   ```
2. 在 docstring 中明确 DCR 的置信度阈值语义。

---

### F4：R5 协议描述"Youden 阈值迁移"，脚本实现"概率集成+TS校准"

**位置**：R5 L178 vs script L1-90

**裁决**：**部分成立**

**理由**：

反方正确指出了 R5 协议描述与脚本实现的不匹配：
- R5 L178："用 2 个语料库的 Youden 阈值在第 3 个上测试"
- 脚本：softmax 概率平均 + 合并 cal 拟合 TS + Brier reliability 评估

但反方将此定性为"致命"并说"这是 confirmatory 协议与实现的不匹配"，这**误解了正方意图**：

1. **R5 明确标注 E1b 为 "Exploratory"**（R5 L175："**Exploratory**——leave-one-corpus-out 验证是新提出的分析"）。这不是 confirmatory 预注册协议，探索性实验有更大的设计自由度。

2. **R5 的描述是 1 行简要概述，脚本的 docstring 是 90 行详细设计**。R5 L178 的"Youden 阈值"可能是指广义的"判别阈值迁移"概念，而脚本实现了更丰富的版本（概率集成 + 校准迁移）。两者不是矛盾，而是"简要描述 vs 详细实现"的关系。

3. **R5 L182 的诚实披露条款提到"Youden J ≈ 0"作为失败标准**，但这是"若结果不理想"的条件分支描述，不是"必须计算 Youden J"的硬性要求。脚本评估 Brier reliability 改善，若改善为 0 或负，同样表示"泛化失败"。

4. **脚本产出确实能回答 R5 的核心问题**："校准迁移是否跨语料库泛化？"——脚本通过 Brier reliability 改善、DCR、NCV 回答此问题。R5 的"Youden 阈值迁移"是此问题的一种具体化，脚本的"校准迁移"是另一种具体化，两者回答的是同一类问题。

**实际影响**：R5 的简要描述确实应更新以匹配脚本实现，避免读者困惑。但脚本产出并非"无法回答 R5 提出的问题"——它回答了一个相关的、更丰富的版本。严重性从"致命"降为"严重"（文档不匹配）。

**修补方案**：

更新 R5 L178 为：

```
LOCO 跨语料庫泛化验证：leave-one-corpus-out（LOCO）——
用 2 个源域的模型集成(softmax平均) + 合并校准(TS/Platt/Vector) 
在第 3 个目标域上评估校准迁移效果（3 折），指标为 Brier reliability 改善、DCR、NCV。
```

或在脚本中补充 Youden J 计算（若论文需要阈值迁移叙事）。

---

### F5：ensemble 混合 5类checkpoint(投影到4类) 和 4类checkpoint

**位置**：L459 + L277-284 + L404

**裁决**：**部分成立**

**理由**：

反方正确指出了理论问题：Deep Ensemble (Lakshminarayanan 2017) 要求成员在同一训练目标下训练，而 5 类模型（投影到 4 类）和原生 4 类模型的训练目标不同。

但反方将此定性为"致命"夸大了影响：

1. **脚本已显式声明此近似**（A1, L42-43）：
   ```
   A1. 集成近似假设：2个源域模型的 softmax 概率平均 ≈ 在 S1∪S2 上训练的模型的预测。
       当源域间分布差异大时，ensemble 可能比联合训练更保守（低估 LOCO 性能）。
   ```
   脚本明确声明这是近似，并指出可能"更保守（低估）"。

2. **5→4 投影是合理的工程近似**：5 类模型丢弃 HYP 列后重归一化，得到的是 4 类子空间上的合法概率分布。虽然这不是"原生 4 类模型的输出"，但它保留了 5 类模型对 NORM/MI/STTC/CD 的相对判断。投影后的概率向量满足非负性和归一化，可以参与 ensemble 平均。

3. **反方的反例分析有误**：反方设 chapman 5 类模型输出 `[0.1, 0.3, 0.1, 0.1, 0.4]`（HYP=0.4），投影到 4 类 `[0.17, 0.50, 0.17, 0.17]`。反方说"投影后的均匀分布不是真正的 4 类不确定性"。但这个投影恰恰正确反映了"5 类模型认为可能是 HYP，但在 4 类子空间中不确定"——这种"伪不确定性"是投影的**预期行为**，不是缺陷。模型在 4 类子空间中确实不确定（它想选 HYP 但 HYP 不在选项中）。

4. **实际影响可分析**：投影对 HYP-like 样本引入"分散概率"效应（降低置信度），对非 HYP 样本几乎无影响。这种偏差方向是可预测的，可以通过比较"含 5 类 checkpoint 的折" vs "纯 4 类 checkpoint 的折"来量化。

**实际影响**：Deep Ensemble 的理论保证（PAC-Bayes 界）在混合训练目标时不成立，但 ensemble 作为工程近似仍可使用。脚本应更明确地声明此限制。严重性从"致命"降为"严重"。

**修补方案**：

1. 在 A1 假设中补充：
   ```
   A1 补充：当 LOCO 折含 CPSC（4类）时，5类 checkpoint 的 4 类投影与原生 4 类 checkpoint
   混合 ensemble。Deep Ensemble 的 PAC-Bayes 保证在此不成立（训练目标不同）。
   投影对 HYP-like 样本引入"分散概率"偏差（可预测方向：降低置信度）。
   论文需声明此限制，并将 ensemble 结果定位为"工程近似"而非"有理论保证的下界"。
   ```
2. 在输出中增加 `ckpt_num_classes_mix` 字段，标记该折是否涉及 5类+4类混合。

---

### S1：ensemble ≥ max(members) 对校准指标不成立

**位置**：L36

**裁决**：**成立**

**理由**：

反方攻击成立。脚本 L36 声称"下界：ensemble ≥ max(M_S1→T, M_S2→T) 单源 best（集成不劣于成员）"，这对校准指标不成立。

Deep Ensemble 的校准优势是经验观察（Lakshminarayanan 2017 报告 NLL 更低），不是保证的下界。Rahaman et al. (2021) 确实显示 ensemble 可以恶化校准，尤其当成员相关时。

反方的反例（两个完美校准模型 ensemble 后可能过自信）逻辑自洽。

**修补方案**：

将 L34-37 的"保守性"论证修改为：

```python
# 3. 经验观察（非理论保证）：
#    - Deep Ensemble 在 OOD 上通常优于单模型（Lakshminarayanan 2017 经验观察），
#      但不保证校准指标改善（Rahaman 2021 显示 ensemble 可恶化校准）。
#    - 真 LOCO（联合训练）vs ensemble 的优劣取决于源域间分布冲突程度，
#      无通用上界/下界保证。
#    - 若近似已显示 TS 有 Brier reliability 改善，需谨慎推断真 LOCO 的表现。
```

---

### S2：真 LOCO ≥ ensemble 上界未证明

**位置**：L35

**裁决**：**成立**

**理由**：

反方攻击成立。脚本 L35 声称"上界：真 LOCO 用全部 S1∪S2 数据训练，模型容量充分利用 → 性能 ≥ ensemble"，这在迁移学习文献中不成立。

反方引用 Mansour et al. (2009) 的多源域适应理论，指出不相关源域的联合训练可能因负迁移而劣于选择性集成。逻辑自洽。

**修补方案**：与 S1 合并修改，将"上界/下界"论证降级为"经验观察"。

---

### S3：3折全部退化为4类——HYP 类从未被 LOCO 验证

**位置**：L141-145 + L178-186

**裁决**：**成立**

**理由**：

反方攻击成立。验证 3 折的 num_classes 推断：

| 折 | holdout | sources | min(所有) | subspace |
|----|---------|---------|-----------|----------|
| 1 | ptbxl(5) | chapman(5), cpsc(4) | **4** | SUBSPACE_CPSC |
| 2 | chapman(5) | ptbxl(5), cpsc(4) | **4** | SUBSPACE_CPSC |
| 3 | cpsc(4) | ptbxl(5), chapman(5) | **4** | SUBSPACE_CPSC |

所有 3 折都是 4 类，因为 cpsc（4 类）总在场。HYP 类在所有折中被丢弃，其跨语料库泛化能力从未被验证。

脚本 A3（L47-48）部分提及此问题："涉及 CPSC 时用 4 类子空间...5类折 (PTB↔Chapman) 与 4类折 (含CPSC) 不可直接比较"，但 A3 暗示存在"5类折"，实际上不存在（见 S9）。

**修补方案**：

1. 在脚本 docstring 和输出中显式声明：
   ```
   适用边界补充：由于 CPSC（4类）总在 3 折中，所有 LOCO 折均为 4 类子空间
   (NORM, CD, STTC, MI)。HYP 类的跨语料库泛化未评估。论文需明确声明
   "LOCO 验证仅覆盖 4 类子空间"。
   ```
2. 若需验证 HYP 类泛化，需补充不含 CPSC 的 fold（如 holdout=ptbxl, sources=[chapman]），但这是单源迁移而非 LOCO。

---

### S4：5→4 概率对齐引入系统性过自信偏差

**位置**：L277-284

**裁决**：**成立**

**理由**：

反方攻击成立。5→4 投影丢弃 HYP 列后重归一化：

```python
aligned = probs[:, keep_idx]          # 丢弃 HYP 列
aligned = aligned / aligned.sum(axis=1, keepdims=True)  # 重归一化
```

对 HYP-like 样本（p_HYP 高），重归一化放大剩余类概率，引入过自信偏差。偏差方向可预测（过自信），会恶化校准（reliability 增加）。

反方的反例（5 类模型输出 `[0.1, 0.1, 0.1, 0.1, 0.6]`，投影后 `[0.25, 0.25, 0.25, 0.25]`）正确展示了投影效应。虽然反方说"伪不确定性"（见 F5 审查中的讨论），但**偏差的系统性**确实存在：HYP 高概率样本的投影会系统性偏离原始校准状态。

**修补方案**：

1. 在输出中增加 HYP 投影偏差的量化报告：
   ```python
   # 在 _align_probs_to_subspace 后增加偏差诊断
   if ckpt_num_classes == 5 and loco_num_classes == 4:
       hyp_mass = probs[:, SUPERCLASSES.index("HYP")]
       bias_flag = hyp_mass > 0.3  # HYP 概率 > 30% 的样本
       print(f"  [ALIGN] 5→4 投影: {bias_flag.sum()}/{len(bias_flag)} 样本 "
             f"HYP 概率 > 0.3，投影可能引入过自信偏差")
   ```
2. 在论文中报告 HYP-like 样本比例和投影偏差的敏感性分析。

---

### S5：合并 cal 拟合 TS 时两源域类先验不同——单参数 TS 欠拟合

**位置**：L461-462

**裁决**：**部分成立**

**理由**：

反方正确指出了合并 cal 拟合 TS 的潜在问题：两源域模型预测分布不同 + 真实标签分布不同 → 合并 cal 集是双峰分布 → 单参数 TS 可能次拟合。

但反方忽略了脚本的已有缓解措施：

1. **脚本 A2（L44-46）已显式声明此风险**：
   ```
   A2. 校准迁移假设：...若源域间 cal 分布双峰严重，
       TS 单参数可能欠拟合 → 也报告 vector/platt 作敏感性。
   ```
   脚本不是不知道此问题，而是通过报告 vector/platt 作敏感性分析来缓解。

2. **反方说"vector/platt 同样是全局方法，无法处理双峰"**——这**部分正确**。Vector scaling 有 per-class 参数（4 类 × 2 参数 = 8 参数），比 TS（1 参数）更灵活，但仍无法建模"源域间"的双峰。然而，vector scaling 的 per-class 缩放可以部分吸收类先验差异（如某类在 chapman 中更常见，vector scaling 可调整该类的温度）。

3. **反方建议"分源拟合或加权合并"**是合理的改进，但分源拟合后如何应用到 ensemble？ensemble 概率是两个源域模型的平均，用哪个源域的 T？这需要额外设计（如按源域置信度加权 T），不是简单替换。

**实际影响**：TS 在双峰 cal 上的次拟合是真实风险，但脚本已通过 vector/platt 敏感性部分缓解。应补充分源拟合的对比分析。严重性维持"严重"。

**修补方案**：

增加分源拟合 TS 的对比场景：

```python
# 分源拟合：每个源域独立拟合 T，应用到 ensemble 时按源域贡献加权
src_ts_params = []
for i, src in enumerate(loaded_sources):
    T_i = fit_temperature(src_cal_probs_list[i], src_cal_labels_list[i])
    src_ts_params.append(T_i)
# 报告分源 T 的差异，若 |T_1 - T_2| 大则说明双峰严重
```

---

### S6：benefit_inference 传 cal_correct 而非 test_labels

**位置**：L560-564

**裁决**：**部分成立**

**理由**：

反方指出了两个问题，需分别评估：

**问题 1：传 cal_correct 而非 test_labels**

反方说"benefit_inference 第三参数传 cal_correct（校准后正确性），非 test_labels"。

这**不是 bug，是 top-label calibration 的标准做法**。`smooth_ece(probs, labels)` 的语义是：`probs` 是 max-prob（置信度），`labels` 是"该置信度是否对应正确预测"（binary correctness）。这与 `eval_transfer.py` 的做法一致（反方也承认"与 eval_transfer.py L263 一致"）。

`benefit_inference` 的 `labels` 参数在 top-label calibration 语境下就是 correctness，不是 class labels。反方将此列为"严重"攻击是对 top-label calibration 范式的误解。

**问题 2：T 的拟合不确定性未传入 CI**

反方说"bootstrap 重采样 cal_correct 时，T 是固定的，不随重采样变化。这忽略了 T 的拟合不确定性"。

这**是有效批评**。`benefit_inference` 用固定 T（点估计）做 bootstrap，CI 不包含 T 的拟合不确定性。`two_layer_benefit_inference`（calibration.py L780-860）正是为此设计，但 E1b 脚本未使用（已验证：grep `two_layer_benefit_inference` 无匹配）。

然而，`two_layer_benefit_inference` 的 docstring（calibration.py L799-800）承认"嵌套B=10000×重拟合在O(n²) metric下不可行，此为诚实近似并已登记"。即使用单层 bootstrap 是已知的、登记在案的近似。

**实际影响**：CI 偏窄（低估 T 不确定性），但这是已登记的近似。应文档化此限制。严重性从"严重"降为"中等"。

**修补方案**：

1. 在 `_eval_scenario` 中增加注释说明 T 固定假设：
   ```python
   # 注意：benefit_inference 用固定 T（点估计）做 bootstrap，
   # CI 不包含 T 的拟合不确定性。two_layer_benefit_inference 可解决但
   # O(n²) metric 下 B=10000×重拟合不可行（见 calibration.py L799-800 登记）。
   ```
2. 可选：对 TS 方法用 `two_layer_benefit_inference`（TS 重拟合快，O(n)），对 Platt/Vector 用单层。

---

### S7：n=3 折无跨折聚合/无统计检验——"3折CV"名不副实

**位置**：L810-859 + 全局

**裁决**：**部分成立**

**理由**：

反方正确指出了缺失的统计推断：
1. 无跨折聚合（无总均值/总 std）
2. 无跨折统计检验（无异质性检验）
3. 无 LOCO vs 单源配对检验
4. 无 FDR 校正

但反方说"'3折CV'名不副实"**部分误解了正方意图**：

1. **R5 L182 已诚实披露**："本研究的 LOCO 验证只有 3 折（3 个语料库），统计效力有限（n=3 无法达到 p<0.05）。我们明确声明这是'3 折 leave-one-corpus-out 探索性验证'（**3 个 case study**），不声称'外部验证'。"

2. **脚本 docstring B3（L59）也声明**："探索性验证，不作为 confirmatory 结论。p 值未预注册，CI 仅作描述。"

3. **脚本命名"3折 Leave-One-Corpus-Out"是准确的**——LOCO 确实是 3 折（3 个语料库留一），每折内部有 5 seeds 的描述统计。反方说"暗示交叉验证"但脚本和 R5 都明确说"3 个 case study"。

4. **反方关于"无跨折聚合"的批评有效**（M4 也指出此点）：`_print_summary` 确实只按折打印，无总汇总。这是可用性问题，不是统计推断问题。

**实际影响**：跨折聚合缺失影响结果可读性，应补充。但"3折CV 名不副实"的批评不成立——脚本和 R5 都已明确声明这是 3 个 case study。严重性维持"严重"但原因是"跨折聚合缺失"而非"名不副实"。

**修补方案**：

在 `_print_summary` 中增加跨折聚合：

```python
# 跨折聚合
print("\n  === 跨折总汇总 ===")
for mname in methods:
    for sc in scenarios:
        all_vals = []
        for holdout in holdouts:
            all_vals.extend(groups.get((holdout, mname, sc), []))
        if all_vals:
            print(f"    {mname:<10} {sc:<22} "
                  f"delta_rel = {np.mean(all_vals):+.4f}±{np.std(all_vals):.4f} "
                  f"(n={len(all_vals)}, 3 folds × 5 seeds)")
```

---

### S8：不同 pair 的 checkpoint 架构可能不同

**位置**：L404 + L220-231

**裁决**：**部分成立**

**理由**：

反方正确指出了脚本不验证架构一致性。`_load_model_from_ckpt` 从 state_dict 推断 d_model/n_layers，但不检查所有加载的模型架构是否一致。

但反方将此列为"严重"夸大了实际风险：

1. **所有 60 个 checkpoint 都用同一 `train.py` 训练**，默认 `--arch inceptiontime --d-model 64 --n-layers 2`。脚本 `--arch` 默认也是 "inceptiontime"。在实践中，架构不一致的概率极低。

2. **若架构不一致，ensemble 仍可计算**（softmax 平均不要求同架构），只是理论保证（PAC-Bayes）失效。结果不会"错误"，只是"无理论保证"。

3. **反方说"不同架构模型的 softmax 平均没有 PAC-Bayes 保证"**——正确，但脚本已因 F5（5类+4类混合）而无法依赖 PAC-Bayes 保证。架构一致性是第二层问题。

**实际影响**：应增加架构一致性检查作为防御性编程，但实际风险低。严重性从"严重"降为"中等"。

**修补方案**：

在 `run_loco_fold` 中加载所有模型后增加一致性检查：

```python
# 验证所有源域模型架构一致
d_models = [meta["d_model"] for meta in loaded_metas]
if len(set(d_models)) > 1:
    warnings.warn(f"不同源域模型 d_model 不一致: {d_models}，"
                  f"ensemble 的 PAC-Bayes 保证失效")
```

---

### S9：docstring 提"5类折(PTB↔Chapman)"但实际不存在

**位置**：L48 vs L141-145

**裁决**：**成立**

**理由**：

反方攻击成立。docstring L48 说"5类折 (PTB↔Chapman) 与 4类折 (含CPSC) 不可直接比较"，暗示存在 5 类折和 4 类折两种类型。但如 S3 所述，3 折全部是 4 类，不存在 5 类折。

这是 docstring 与实际行为的直接矛盾。

**修补方案**：

修正 L48 为：

```python
A3. 标签空间对齐：由于 CPSC（4类）总在 3 折中出现，所有 LOCO 折均为 4 类子空间
    (SUBSPACE_CPSC)。HYP 类的跨语料库泛化未评估。5 类 checkpoint 在 4 类折中
    通过 _align_probs_to_subspace 投影降级（丢弃 HYP 列后重归一化）。
```

---

### S10：num_classes 从 state_dict 正则推断——架构变更时静默回退

**位置**：L208-217

**裁决**：**成立**

**理由**：

反方攻击成立。代码 L208-217 用正则 `r"classifier\.(\d+)\.weight"` 推断 num_classes，若不匹配则静默回退到 `num_classes`（LOCO 折的 4 类），无警告。

反方的反例（分类头改名为 `head.weight`）有效：正则不匹配 → 静默回退 → 可能加载错误架构。

**修补方案**：

在 L216-217 增加警告：

```python
else:
    ckpt_nc = num_classes  # 回退到 LOCO 折的 num_classes
    warnings.warn(
        f"无法从 state_dict 正则推断 num_classes（分类头命名不匹配 "
        f"'classifier.{{N}}.weight'），回退到 LOCO 折的 num_classes={num_classes}。"
        f"若 checkpoint 实际是 {num_classes} 类以外的模型，load_state_dict 将失败。"
    )
```

---

### S11（矛盾分析）：E1a 和 E1b 的单源 baseline 数值不一致

**位置**：E1a `eval_transfer.py` vs E1b `run_loco_fold`

**裁决**：**成立**

**理由**：

反方在矛盾分析中提出的 S11 成立。E1a 的 chapman→ptbxl 用 `num_classes = min(5,5) = 5`，E1b 的 holdout=ptbxl 折中 chapman 单源 baseline 用 `num_classes = min(5,4,5) = 4`。同一 checkpoint 在 E1a 和 E1b 中用不同 num_classes 评估，结果不可比。

验证：
- E1b `_num_classes_and_subspace`（L178-186）：`nc = min(DATASET_NUM_CLASSES[n] for n in all_names)`，all_names 包含所有源域 + 目标域。
- Fold 1: all_names = [chapman, cpsc, ptbxl] → min(5,4,5) = 4
- E1a 的 chapman→ptbxl：min(5,5) = 5

同一 checkpoint M_{chapman→ptbxl} 在 E1a 中是 5 类评估，在 E1b 中是 4 类评估（投影后）。若论文同时引用两者，读者会困惑。

**修补方案**：

1. 在 E1b 输出中增加字段 `e1a_comparable`，标记该单源 baseline 是否与 E1a 的对应 cell 使用相同 num_classes：
   ```python
   # 单源 baseline 与 E1a 可比性
   e1a_nc = min(DATASET_NUM_CLASSES[src], DATASET_NUM_CLASSES[holdout])
   e1a_comparable = (e1a_nc == num_classes)
   ```
2. 在论文中明确声明：E1b 的单源 baseline 因 LOCO 折的 num_classes 降级，与 E1a 的对应 cell 不可直接比较。

---

### M1：CSV 前8行是注释——非标准格式

**位置**：L765-773

**裁决**：**成立**

**理由**：

反方攻击成立。CSV 前 8 行是 `#` 注释 + 1 行空行，列名在第 9 行。`pandas.read_csv()` 默认会尝试解析注释行为数据，需 `skiprows=8` 或 `comment='#'`。

**修补方案**：

移除 CSV 注释行，将元数据放入 JSON 输出（已有 L791-807 的 JSON 输出）。或保留注释但在 docstring 中说明需 `comment='#'` 读取。

---

### M2：ood_acc 是校准前准确率——Platt/Vector 改变 argmax

**位置**：L467 + L597-600

**裁决**：**成立**

**理由**：

反方攻击成立。`ood_acc` 在 L467 计算的是校准前准确率。TS 不改变 argmax（温度缩放保序），但 Platt（per-class sigmoid）和 Vector scaling（per-class scale+bias）会改变 argmax。脚本未报告校准后准确率。

对于 Platt/Vector，校准可能改善或恶化准确率，这是有信息量的指标。

**修补方案**：

在 `_eval_scenario` 中增加校准后准确率：

```python
ood_acc_cal = float((cal_probs.argmax(1) == test_labels).mean())
records.append({**base, "metric": "ood_acc_cal",
                "value": ood_acc_cal, "ci_lo": "", "ci_hi": "",
                "note": "argmax accuracy after calibration"})
```

---

### M3：SAFE_DELTA_ECE 定义后从未使用——死代码

**位置**：L149

**裁决**：**成立**

**理由**：

反方攻击成立。`SAFE_DELTA_ECE = -0.01`（L149）仅在 L801 写入 JSON metadata，从未在逻辑中使用。已通过 grep 验证：全文仅 2 处出现（定义 + JSON metadata）。

**修补方案**：

删除 L149，或在 NCV 判据中使用：

```python
ncv_beneficial = ncv_point > abs(SAFE_DELTA_ECE)  # NCV > 0.01 → 校准有益
records.append({**base, "metric": "ncv_beneficial",
                "value": ncv_beneficial, ...})
```

---

### M4：汇总无跨折总均值——难以看到整体 LOCO 结论

**位置**：L810-859

**裁决**：**成立**

**理由**：

反方攻击成立。`_print_summary` 按 `(holdout, method, scenario)` 聚合，每折独立打印，无跨折总汇总。读者需手动从 3 行中算平均。

此问题与 S7 的"无跨折聚合"重叠。

**修补方案**：与 S7 的修补方案合并，增加跨折聚合行。

---

### M5：E1b 单源 baseline 与 E1a L2 矩阵冗余

**位置**：L495-511

**裁决**：**部分成立**

**理由**：

反方正确指出了冗余：E1b 的单源 baseline 使用与 E1a 相同的 checkpoint 和前向，是 E1a L2 矩阵的子集。

但反方说"仅 ensemble+merged cal 是新内容"**不完全准确**：

1. **S11 已证明 E1b 单源 baseline 与 E1a 不可直接比较**（num_classes 不同）。E1b 的单源 baseline 在 4 类子空间评估，E1a 的对应 cell 在 5 类空间评估。虽然 checkpoint 相同，但评估空间不同，结果不同。

2. **E1b 的单源 baseline 是 LOCO 折内的对照组**，用于与 `loco_ensemble` 场景对比。即使数值与 E1a 不同（因 num_classes 降级），它在 E1b 内部的对比作用（ensemble vs 单源）是必要的。

3. **若直接引用 E1a 结果**，需确保 num_classes 一致——但 E1a 是 5 类、E1b 是 4 类，无法直接引用。因此 E1b 必须自己计算单源 baseline。

**实际影响**：冗余存在但不可消除（因 num_classes 降级）。应在论文中说明 E1b 单源 baseline 与 E1a 不可直接比较。严重性从"轻微"维持"轻微"。

**修补方案**：

在 docstring 中说明：

```python
# 注意：E1b 单源 baseline 因 LOCO 折 num_classes 降级（4类），与 E1a 的对应 cell
# （5类）不可直接比较。E1b 必须自行计算单源 baseline 作为 ensemble 的对照组。
```

---

## 总结

### 实验整体设计是否经得起考验

**部分经得起考验，但需显著修补。**

E1b 脚本的核心设计（ensemble-based LOCO 近似）是合理的工程方案——在无重训预算的约束下，复用现有 checkpoint 做概率集成 + 校准迁移是可接受的探索性方法。脚本的设计意图（docstring 90 行详细说明）是诚实的，明确标注了近似假设（A1-A4）和适用边界（B1-B3）。

但脚本存在**3 类需优先修补的真实问题**：

1. **指标计算错误**（F1）：NCV 的 CI 用了不同度量的 CI，这是统计错误，必须修复。
2. **文档-代码不一致**（F2, F4, S9, S10）：多处 docstring/协议描述与代码行为不匹配，会误导读者。
3. **设计局限未充分声明**（S3, S11）：全 4 类退化、E1a-E1b 不一致等局限虽有部分声明，但不够显式。

反方攻击的**整体质量较高**（21 个攻击点无一被完全驳回），但在 9 个攻击点上夸大了严重程度，主要夸大模式是：
- 将"已文档化的近似局限性"当作"未发现的致命缺陷"（F4, F5, S5, S6）
- 将"合理的设计选择"当作"逻辑错误"（F2, F3）
- 将"实践风险极低的理论问题"当作"严重问题"（S8）

### 需要优先修补的问题清单

**P0（必须修复才能产出可信结果）**：
1. **F1**：实现 Brier reliability 的 cluster bootstrap CI，替换 NCV 的 delta_ece_ci
2. **S3**：显式声明 LOCO 仅覆盖 4 类子空间，HYP 泛化未评估
3. **S11**：声明 E1b 单源 baseline 与 E1a 不可直接比较（num_classes 降级）

**P1（修复后才能用于论文）**：
4. **F2**：修正 DCR docstring 为"per-sample Brier score"
5. **F4**：更新 R5 L178 描述为"校准迁移 LOCO"（与脚本对齐）
6. **S1+S2**：将 ensemble 上下界论证降级为"经验观察"
7. **S9**：修正 docstring L48"5类折"为"全4类折"
8. **S4**：增加 5→4 投影偏差的量化报告
9. **S7+M4**：增加跨折聚合汇总

**P2（建议修复）**：
10. **F3**：增加 DCR threshold 敏感性分析
11. **F5**：在 A1 中补充 5类+4类混合的理论限制声明
12. **S5**：增加分源拟合 TS 的对比场景
13. **S6**：文档化 T 固定假设对 CI 的影响
14. **S8**：增加架构一致性检查
15. **S10**：增加 num_classes 正则回退警告
16. **M1**：修正 CSV 格式或文档化读取方式
17. **M2**：增加 ood_acc_cal
18. **M3**：删除或使用 SAFE_DELTA_ECE
19. **M5**：文档化 E1b 单源 baseline 的必要性

### 对反方攻击的质量评价

反方挑刺代理-E1b 的攻击工作**扎实且有价值**。20 个攻击点覆盖了 7 个攻击维度，无一被完全驳回，说明反方确实做了深入的代码审查。反方发现的真实问题（F1 NCV CI 伪造、S3 全 4 类退化、S11 E1a-E1b 不一致）对提升实验质量有直接贡献。

但反方在严重性标注上有系统性偏高倾向：5 个"致命"攻击中仅 1 个（F1）真正达到"致命"级别，其余 4 个（F2-F5）应降为"严重"。反方将"已文档化的近似局限性"反复当作"未发现的致命缺陷"攻击，这种模式在 F4（exploratory 实验的协议不匹配）和 F5（已声明 A1 的近似假设）上最为明显。

**建议正方**：接受反方发现的真实问题，按 P0→P1→P2 优先级修补。修补后，E1b 脚本可作为"4 类子空间中 ensemble-based LOCO 近似的探索性验证"用于论文，但需在适用边界中诚实声明所有局限。

---

## 附录：裁决汇总表

| 编号 | 反方严重性 | 裁决 | 调整后严重性 | 核心原因 |
|------|-----------|------|------------|---------|
| F1 | 致命 | 成立 | 致命 | NCV CI 确实用了不同度量的 CI |
| F2 | 致命 | 部分成立 | 严重 | docstring 误导但代码注释已解释 |
| F3 | 致命 | 部分成立 | 严重 | 数学正确但"退化"是 per-sample Brier 本质，非缺陷 |
| F4 | 致命 | 部分成立 | 严重 | 不匹配真实但 E1b 是 exploratory 非confirmatory |
| F5 | 致命 | 部分成立 | 严重 | 理论保证不成立但近似已文档化 |
| S1 | 严重 | 成立 | 严重 | ensemble 下界对校准指标不成立 |
| S2 | 严重 | 成立 | 严重 | 真 LOCO 上界未证明 |
| S3 | 严重 | 成立 | 严重 | 全 4 类退化，HYP 未验证 |
| S4 | 严重 | 成立 | 严重 | 5→4 投影偏差真实 |
| S5 | 严重 | 部分成立 | 严重 | 风险真实但 A2 已声明，缓解不完整 |
| S6 | 严重 | 部分成立 | 中等 | cal_correct 是 top-label 标准做法，T 不确定性是已登记近似 |
| S7 | 严重 | 部分成立 | 严重 | 跨折聚合缺失，但 R5 已声明 n=3 |
| S8 | 严重 | 部分成立 | 中等 | 理论风险真实但实践概率极低 |
| S9 | 严重 | 成立 | 严重 | docstring 直接矛盾 |
| S10 | 严重 | 成立 | 严重 | 静默回退风险真实 |
| S11 | 严重 | 成立 | 严重 | E1a-E1b num_classes 不一致 |
| M1 | 轻微 | 成立 | 轻微 | CSV 格式问题 |
| M2 | 轻微 | 成立 | 轻微 | 缺少 ood_acc_cal |
| M3 | 轻微 | 成立 | 轻微 | 死代码 |
| M4 | 轻微 | 成立 | 轻微 | 无跨折聚合 |
| M5 | 轻微 | 部分成立 | 轻微 | 冗余存在但因 num_classes 降级不可消除 |

**审查完成。21 个攻击点已全部裁决，其中 12 个成立、9 个部分成立、0 个驳回。**
