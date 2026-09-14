# 反反方审查：P0-3 R3修复攻击审查

## 审查摘要
- 攻击报告：docs/p0r3_attack_p0_3.md
- 审查文件：scripts/run_e2_ablation_discrimination.py（714 行）
- 交叉验证文件：scripts/run_e4_temperature_analysis.py（验证 A3 中 E4 结构声明）
- 攻击点总数：10（A1-A10）
- **成立：4**（A1, A5, A6, A10）
- **部分成立：4**（A2, A3, A4, A7）
- **不成立：2**（A8, A9）

### 裁决原则
本审查以代码事实为唯一判据，对每个攻击点执行 5 维审查：
1. 反例是否真的成立（代码验证）
2. 是否稻草人论证（反方是否歪曲正方主张）
3. 是否误解前提（反方是否忽略正方声明的边界）
4. 攻击逻辑是否自洽
5. 严重程度是否被夸大

---

## 逐条审查

### 攻击点 A1: T_global CSV=nan 与 Θ_2 含 T 矛盾（反方标 P0-严重）

**判定：成立**

**理由**：

代码事实验证：
- L17（Fix-1 修复后）：`Θ_2 = {T, T_1..T_5}` — 声明 T 是 Stage 2 的参数
- L499（CSV 输出代码）：
  ```python
  "T_global": T_global if stage_name in ("stage1_ts",) else np.nan,
  ```
  T_global 仅对 `stage1_ts` 报告，对 `stage2_ts_binned` 和 `stage3_ts_binned_threshold` 报告为 `np.nan`
- L478-480（Stage 2 实现）：`fit_binned_temperature(cal_s1, cal_y)` 其中 `cal_s1 = apply_temperature_multiclass(cal_p, ts_params)` — Stage 2 **确实使用** T_global（通过 cal_s1 间接使用）

矛盾确认：
- docstring 声明 T ∈ Θ_2（T 是 Stage 2 的参数）
- 代码实现确实使用 T（cal_s1 = TS(cal_p, T_global)）
- 但 CSV 对 Stage 2/3 的 T_global 列报告 nan，**与代码实现和 docstring 声明均不一致**

这不是稻草人论证：反方准确引用了 L17 和 L499，矛盾真实存在。反方未误解前提：CSV 是论文原始数据来源，审稿人会从 CSV 验证嵌套关系。攻击逻辑自洽：docstring 说 T ∈ Θ_2 → CSV 应报告 T → CSV 报告 nan → 矛盾。

严重程度评估：**P0-严重 成立**。CSV 是论文数据来源，T_global=nan 会让审稿人误以为 Stage 2 不使用全局 T（即 Stage 2 是 binned-only），这与 R2 轮 P0-3 的核心修复（Stage 2 = TS+binned）直接矛盾。反方未夸大严重程度。

**修补方案**：
- 文件：`scripts/run_e2_ablation_discrimination.py`
- 行号：L499
- 改动：
  ```python
  # 旧：
  "T_global": T_global if stage_name in ("stage1_ts",) else np.nan,
  # 新：
  "T_global": T_global if stage_name != "raw" else np.nan,
  ```
- 效果：对 stage1_ts / stage2_ts_binned / stage3_ts_binned_threshold 均报告 T_global，仅 raw 报告 nan。使 CSV 与 docstring 的 Θ_2 = {T, T_1..T_5} 一致。

---

### 攻击点 A2: Θ_2 notation 隐含 T 与 T_1..T_5 独立（反方标 P0-轻微）

**判定：部分成立**

**理由**：

代码事实验证：
- L467: `ts_params = fit_temperature_multiclass(cal_p, cal_y)` — 先拟合 T
- L469: `cal_s1 = apply_temperature_multiclass(cal_p, ts_params)` — 用 T 校准
- L478: `binned_params = fit_binned_temperature(cal_s1, cal_y)` — 在 TS 输出上拟合 T_1..T_5

反方观察正确：T_1..T_5 确实条件依赖于 T（因为 T_1..T_5 是在 TS(cal_p, T) 上拟合的）。集合 notation {T, T_1..T_5} 确实隐含独立性。

**但反方自身已承认此为可接受的 notation 简化**：
> "这是 ablation study 中常见的 notation 简化，不影响边际贡献的可解释性（控制 T 后加 T_1..T_5 的边际效应是良定义的）"

反驳点：
1. **边际贡献良定义**：控制 T 后加 T_1..T_5 的边际效应 = Rel(S2) - Rel(S1)，这与 T_1..T_5 是否独立于 T 无关。消融分析的核心是边际效应，不是参数独立性。
2. **ablation study 标准约定**：参数空间 notation 在消融研究中普遍使用集合表示，隐含的是"参数组"而非"独立参数"。这是领域约定，非错误。
3. **严格的条件依赖 notation** Θ_2 = {T, T_1..T_5 | T_1..T_5 = f(T)} 会过度复杂化 docstring，降低可读性，且不增加信息量。

**严重程度评估**：反方标 P0-轻微 恰当，未夸大。但此攻击的实践价值很低——这是 notation 约定问题，不影响代码正确性、消融可解释性或论文结论。**建议不修复**（修复反而降低可读性）。

**反驳**：此攻击虽技术观察正确，但属于 ablation study 领域的标准 notation 约定。正方无需修改——任何熟悉消融分析的审稿人都理解集合 notation 表示"参数组"而非"独立参数"。

---

### 攻击点 A3: E4 不可比归因不完整（反方标 P0-严重）

**判定：部分成立（严重程度被夸大，应降级为 P0-中等）**

**理由**：

代码事实验证（交叉验证 E4 文件）：
- E4 L518: `T_per_bin, bin_edges, bin_records = fit_binned_T(cal_probs, cal_labels, n_bins=N_BINS)` — **直接对 raw cal_probs 拟合 binned-T**，未先应用 global T ✓
- E4 L521-522: `apply_binned_T(id_probs, ...)` / `apply_binned_T(ood_probs, ...)` — **直接对 raw probs 应用 binned-T** ✓
- E4 L376: `ent = predictive_entropy(cal_probs)` — 分箱变量 = H(p)（raw entropy）✓
- E2 L478: `fit_binned_temperature(cal_s1, cal_y)` — 对 TS(cal_p) 拟合 binned-T ✓

反方对 E2 vs E4 结构差异的描述**准确**：
- E2 Stage 2 = TS + binned（双层：global T → binned T on TS output）
- E4 binned-T = binned-only（单层：binned T on raw）

反方观察正确：L32-33 将不可比性归因于"分箱变量不同"（H(TS(p)) vs H(p)），但漏掉了更根本的"结构不同"（TS+binned vs binned-only）。即使统一分箱变量，结构差异仍导致结果不可比。

**但严重程度被夸大**，理由如下：

1. **docstring 结论正确**：L32-33 说"不可直接比较"——这是正确的结论。归因不完整 ≠ 结论错误。
2. **"虚假可修复路径"论证被夸大**：反方声称"审稿人可能以为只要统一分箱变量就能让 E2 和 E4 可比"。但 docstring 明确说"不可直接比较"，并未暗示任何"可修复路径"。审稿人读到"不可直接比较"的理解是"不要比较"，而非"统一分箱变量后可以比较"。
3. **docstring 的归因是充分条件**：分箱变量不同 → 不可比。这是逻辑上有效的充分条件推理。漏掉另一个充分条件（结构不同）是不完整，但不是错误。
4. **E4 不可比声明的核心功能**是防止审稿人跨实验比较 E2 和 E4 的 binned-T 结果。当前声明已达成此功能——审稿人读到"不可直接比较"就不会比较。

**严重程度评估**：反方标 P0-严重 **被夸大**，应降级为 **P0-中等**。归因不完整是文档精确性问题，不影响代码正确性或论文结论。CBM 审稿中，不可比声明的结论正确即可通过；归因完整性是"建议改进"而非"必须修复"。

**修补方案**（建议但非必修）：
- 文件：`scripts/run_e2_ablation_discrimination.py`
- 行号：L32-33
- 改动：
  ```
  # 旧：
  其中 p'=TS(p)（Stage 1 的温度缩放输出）。注意：E4 的 binned-T 分箱变量
  为 H(p)（对原始概率分箱），两者分箱变量不同，不可直接比较。
  # 新：
  其中 p'=TS(p)（Stage 1 的温度缩放输出）。注意：E4 的 binned-T 直接对
  原始概率 p 拟合（binned-only，不先做全局 TS），而 E2 Stage 2 在 TS 输出
  上拟合（TS+binned 双层）。两者不仅分箱变量不同（H(p) vs H(TS(p))），
  且输入结构不同（raw vs TS output），不可直接比较。
  ```

---

### 攻击点 A4: 假设改变未讨论科学合理性（反方标 P0-中等）

**判定：部分成立（严重程度被夸大，应降级为 P0-轻微）**

**理由**：

代码事实验证：
- L478: `binned_params = fit_binned_temperature(cal_s1, cal_y)` — 使用 cal_s1 = TS(cal_p)
- L473-477 注释明确说明：R3 修复将 binned-T 输入从 raw cal_p 改为 cal_s1（TS 输出），目的是恢复 Stage1 ⊂ Stage2 嵌套关系

反方观察正确：H(p) → H(TS(p)) 确实改变了分箱变量的科学语义。

**但反方误解了改变的性质**，理由如下：

1. **这是嵌套修复的必然推论，非独立假设改变**：
   - R2 轮判定的核心问题是 Stage 2 对 raw cal_p 做 binned-T，破坏了 Stage1 ⊂ Stage2 嵌套
   - 修复嵌套**必须**让 binned-T 作用于 TS 输出（cal_s1）
   - binned-T 输入改为 cal_s1 → 分箱变量自动变为 H(TS(p))
   - 因此 H(TS(p)) 分箱是嵌套修复的**数学必然**，不是独立的科学假设选择

2. **反方的"T 拟合噪声传播到分箱"论证被夸大**：
   - T_global 在 cal 集上拟合，n_cal 通常 ≥ 数百（非 smoke 场景），T 估计稳定
   - smoke 场景（n_cal=60）下有 A3 假设（每箱 ≥10 样本）保护
   - docstring L36 已声明"若该假设不成立，Stage2−Stage1 ≈ 0（脚本会如实报告）"——脚本诚实报告假设失效情况
   - post-TS 熵分箱的稳定性风险是 multi-stage calibration 的已知 trade-off，非本脚本特有问题

3. **post-TS 熵分箱有科学合理性**：
   - TS 校准后的熵更准确反映"校准后的不确定度"
   - 分箱基于校准后不确定度 → 同一箱内样本有相似的"校准后置信模式" → binned-T 更有针对性
   - 这比 raw 熵分箱（基于未校准置信度）在科学上**更合理**，而非更弱

**严重程度评估**：反方标 P0-中等 **被夸大**，应降级为 **P0-轻微**。假设改变是嵌套修复的数学必然，非独立选择。post-TS 熵分箱有科学合理性。docstring 已有诚实报告机制。反方未提供 post-TS 熵分箱"更弱"的实际证据，仅提出理论风险。

**反驳**：反方将嵌套修复的数学必然推论误标为"假设改变"，并要求讨论"科学合理性"。但 post-TS 熵分箱在科学上比 raw 熵分箱更合理（基于校准后不确定度），且 docstring 已有诚实报告机制。此攻击的核心前提（"假设改变需讨论合理性"）成立但方向错误——改变是向更合理的方向。

---

### 攻击点 A5: L36 "≈0" 忽略过拟合负 Δ 风险（反方标 P0-轻微）

**判定：成立**

**理由**：

代码事实验证：
- L36: "若该假设不成立，Stage2−Stage1 ≈ 0（脚本会如实报告）。"
- L40-41: A3 假设"每箱样本量 ≥ 10 才拟合该箱 T；否则该箱 T=1.0（不校准）"
- L171-172: `if mask.sum() < MIN_SAMPLES_PER_BIN: temperatures.append(1.0)` — A3 假设有代码实现

反方观察正确：A1 假设不成立时，binned-T 可能过拟合（在 cal 上拟合差异化 T_1..T_5，但 test 上不泛化），导致 Stage2 reliability 恶化（Δ < 0），而非 ≈ 0。

逻辑验证：
- 情况 1：binned-T 拟合 T_1≈...≈T_5≈1 → Stage2 ≈ Stage1，Δ ≈ 0 ✓
- 情况 2：binned-T 过拟合 → cal 上 Δ < 0，test 上 Δ < 0（reliability 恶化）✓
- 情况 3：A3 也不满足 → 部分箱 T=1.0，其余箱过拟合 → Δ 可能为负 ✓

"≈ 0" 未覆盖情况 2 和 3，文档表述不精确。

反方未夸大严重程度：自标 P0-轻微，且明确声明"代码会如实报告 Δ（包括负值），所以这是文档表述不精确，不影响代码正确性"。

**修补方案**：
- 文件：`scripts/run_e2_ablation_discrimination.py`
- 行号：L36
- 改动：
  ```
  # 旧：
  Stage2−Stage1 ≈ 0（脚本会如实报告）。
  # 新：
  Stage2−Stage1 ≈ 0 或为负（过拟合风险，脚本会如实报告）。
  ```

---

### 攻击点 A6: L8 "按预测熵" 与 L31 H(TS(p)) 语义不一致（反方标 P0-轻微）

**判定：成立**

**理由**：

代码事实验证：
- L8: "Stage 2: TS + binned T — 按预测熵(不确定度)分 5 箱，每箱一个 T"
- L31: "A1. binned temperature 的分箱变量=TS 校准后预测分布熵 H(TS(p))=−Σ p'_k log p'_k"
- L478: `fit_binned_temperature(cal_s1, cal_y)` — 确实用 cal_s1 = TS(cal_p)

反方观察正确：L8 说"按预测熵"未指定 raw 或 TS 校准后，L31 明确为 H(TS(p))。读者阅读 L8 时自然理解为 H(p)（raw 熵），与 L31 矛盾。

这不是稻草人论证：L8 确实未指定，且"预测熵"在无限定词时默认指 raw 概率熵。反方未夸大严重程度：P0-轻微 恰当。

**修补方案**：
- 文件：`scripts/run_e2_ablation_discrimination.py`
- 行号：L8
- 改动：
  ```
  # 旧：
  Stage 2: TS + binned T    — 按预测熵(不确定度)分 5 箱，每箱一个 T
  # 新：
  Stage 2: TS + binned T    — 按 TS 校准后预测熵(不确定度)分 5 箱，每箱一个 T
  ```

---

### 攻击点 A7: L19 未提前说明 Stage3 reliability 边际贡献恒为 0（反方标 P0-轻微）

**判定：部分成立**

**理由**：

代码事实验证：
- L19: "ΔReliability(Stage3−Stage2) = threshold opt 的边际贡献（控制 binned T 后）"
- L26: "Stage 3 的 threshold optimization 改变 argmax→F1/PPV/NPV/MCC 改变"
- L486: `cal_s3, test_s3 = cal_s2, test_s2` — 同引用
- L681: "≡0 by construction: threshold只改argmax不改概率"

反方观察正确：L19 描述边际贡献公式但未显式说明此边际贡献对 reliability 恒为 0。读者需读到 L681 的 print 才意识到。

**但信息可从上下文推导**：
1. L26 明确说"Stage 3 的 threshold optimization 改变 argmax→F1/PPV/NPV/MCC 改变"——这暗示 threshold opt 影响 argmax 类指标
2. L22-25 讨论 TS 对 argmax 和概率类指标的影响——建立"argmax 类 vs 概率类"的区分
3. Brier reliability 基于概率（max_prob）和 argmax（correct），但 L486 的同引用保证概率不变 → reliability 不变
4. 仔细读者可从 L26 + L486 推导出 Stage3 reliability 边际贡献 = 0

反方承认这是"期望管理问题"且"预存问题非 Fix-3 引入"。严重程度 P0-轻微 恰当，未夸大。

**修补方案**（可选）：
- 文件：`scripts/run_e2_ablation_discrimination.py`
- 行号：L19
- 改动：在 L19 末尾追加注释
  ```
  # 旧：
  ΔReliability(Stage3−Stage2) = threshold opt 的边际贡献（控制 binned T 后）
  # 新：
  ΔReliability(Stage3−Stage2) = threshold opt 的边际贡献（控制 binned T 后；
  对 reliability 恒为 0，threshold opt 仅改善判别指标 F1/PPV/NPV/MCC）
  ```

---

### 攻击点 A8: L142 _entropy docstring H(p) 与 L31 H(TS(p)) 符号冲突（反方标 P0-轻微）

**判定：不成立**

**理由**：

代码事实验证：
- L141-144:
  ```python
  def _entropy(probs: np.ndarray) -> np.ndarray:
      """预测分布熵 H(p) = -Σ p_k log p_k（不确定度度量）"""
      p = np.clip(probs, EPS, 1.0)
      return -np.sum(p * np.log(p), axis=1)
  ```
- L31: "H(TS(p))=−Σ p'_k log p'_k，其中 p'=TS(p)"

**反方此攻击是稻草人论证**，理由如下：

1. **H(p) 是函数定义，p 是形式参数（泛型）**：
   - `_entropy` 函数的 docstring 定义函数行为：计算输入概率分布的熵
   - `p` 是形式参数名，代表"任意输入概率分布"，不是"raw 概率"
   - 当调用 `_entropy(cal_s1)` 时，p = cal_s1 = TS(cal_p)，函数计算 H(TS(p))
   - 这是标准编程约定：函数 docstring 描述函数对输入做什么，调用方决定输入语义

2. **H(p) 与 H(TS(p)) 是一致的，非冲突**：
   - H(·) 是函数定义：H(x) = -Σ x_k log x_k
   - H(p) 是 H 在 p 处的取值
   - H(TS(p)) 是 H 在 TS(p) 处的取值
   - L142 定义 H(·)，L31 应用 H(TS(p))——这是定义与应用的关系，非冲突
   - 数学上完全自洽：函数定义 H(x) + 代入 x=TS(p) → H(TS(p))

3. **反方的"读者误以为"论证是臆测**：
   - 反方声称"读者可能误以为 _entropy 始终计算 raw 概率熵"
   - 但函数 docstring 写的是"预测分布熵 H(p)"，p 是函数参数名，非"raw 概率"的别名
   - 任何理解 Python 函数定义的读者都知道参数名是泛型占位符
   - 反方未提供任何证据表明真实读者会如此误解

4. **反方自身已承认"函数是通用的"**：
   > "_entropy 函数是通用的（计算输入的熵），当传入 TS(p) 时计算 H(TS(p))"
   
   这直接否定了"符号冲突"——通用函数的定义用泛型参数是正确做法。

**反驳**：此攻击是稻草人论证。反方将函数定义中的形式参数 p（泛型占位符）歪曲为"raw 概率 p"（具体语义），然后声称与 L31 的 H(TS(p)) 冲突。但 H(p) 作为函数定义与 H(TS(p)) 作为具体应用是标准数学/编程约定，完全自洽。反方自身已承认"函数是通用的"，即已承认此攻击不成立。**无需修复。**

---

### 攻击点 A9: T_0..T_{n_bins-1} vs T_1..T_5 索引约定不一致（反方标 P0-轻微）

**判定：不成立**

**理由**：

代码事实验证：
- L159: `'temperatures': [T_0..T_{n_bins-1}],` — 0-indexed（代码返回值描述）
- L17: `Θ_2 = {T, T_1..T_5}` — 1-indexed（数学参数空间描述）

**反方此攻击误解了代码与数学的约定差异**，理由如下：

1. **0-indexed 是 Python/代码的标准约定**：
   - L159 描述的是 `fit_binned_temperature` 函数的返回值（Python list）
   - Python list 是 0-indexed：`temperatures[0]`, `temperatures[1]`, ..., `temperatures[n_bins-1]`
   - docstring 用 T_0..T_{n_bins-1} 准确描述了 Python list 的索引范围
   - 若写 T_1..T_5 会与实际代码 `temperatures[0]` 到 `temperatures[4]` 矛盾

2. **1-indexed 是数学公式的标准约定**：
   - L17 描述的是参数空间 Θ_2，是数学对象
   - 数学文献中参数下标通常 1-indexed：T_1, T_2, ..., T_5
   - 这是数学排版的国际约定（LaTeX 默认 1-indexed）

3. **不同上下文用不同约定是正确做法**：
   - 代码 docstring（L159）用 0-indexed → 与 Python 代码一致
   - 数学公式（L17）用 1-indexed → 与数学文献一致
   - 强制统一反而引入错误：若 L159 用 1-indexed 会误导读者访问 `temperatures[5]`（越界）

4. **反方自身已承认"纯文档约定问题，不影响代码"**：
   > "严重程度：P0-轻微。纯文档约定问题，不影响代码。"
   
   既然不影响代码，且约定差异是标准做法，此攻击无实践价值。

**反驳**：此攻击误解了代码与数学的约定差异。L159 描述 Python list 返回值（0-indexed 正确），L17 描述数学参数空间（1-indexed 标准）。不同上下文用不同约定是正确做法，强制统一反而引入错误（L159 用 1-indexed 会误导读者越界访问）。反方自身承认"不影响代码"。**无需修复。**

---

### 攻击点 A10: L20 "可加性解释" 混淆可解释性与可加性（反方标 P0-轻微）

**判定：成立**

**理由**：

代码事实验证：
- L20: "嵌套结构保证边际贡献可加性解释（无参数空间交叉）"

反方观察数学正确：
- **可加性（additivity）**：Rel(S3) - Rel(S1) = [Rel(S2) - Rel(S1)] + [Rel(S3) - Rel(S2)]
  这是 telescoping（望远镜求和），对**任意**三个阶段成立，不需要嵌套结构保证
- **可解释性（interpretability）**：每个边际贡献对应一个明确的组件增量
  - Δ(S2-S1) = binned T 的边际贡献（控制全局 T 后）
  - Δ(S3-S2) = threshold opt 的边际贡献（控制 binned T 后）
  这**需要**嵌套结构保证（无参数空间交叉 → 每个增量对应唯一组件）

L20 说"嵌套结构保证边际贡献可加性解释"——将嵌套结构的作用错误归因于可加性（平凡性质），而非可解释性（嵌套结构真正保证的性质）。

反方未夸大严重程度：P0-轻微 恰当，且明确声明"不影响实际消融分析的正确性"。

**修补方案**：
- 文件：`scripts/run_e2_ablation_discrimination.py`
- 行号：L20
- 改动：
  ```
  # 旧：
  嵌套结构保证边际贡献可加性解释（无参数空间交叉）。
  # 新：
  嵌套结构保证边际贡献可解释性（每个增量对应唯一组件，无参数空间交叉）。
  ```

---

## 总结

### 裁决统计

| 判定 | 数量 | 攻击点 |
|------|------|--------|
| **成立** | 4 | A1, A5, A6, A10 |
| **部分成立** | 4 | A2, A3, A4, A7 |
| **不成立** | 2 | A8, A9 |

### 需 R4 修复的必修项清单（P0-严重，成立）

| 序号 | 攻击点 | 文件 | 行号 | 改动 | 改动量 |
|------|--------|------|------|------|--------|
| 1 | **A1** | scripts/run_e2_ablation_discrimination.py | L499 | `T_global if stage_name in ("stage1_ts",) else np.nan` → `T_global if stage_name != "raw" else np.nan` | 1 行 |

### 需 R4 修复的建议项清单（P0-中等，部分成立但降级）

| 序号 | 攻击点 | 文件 | 行号 | 改动 | 改动量 |
|------|--------|------|------|------|--------|
| 2 | **A3**（降级 P0-中等） | scripts/run_e2_ablation_discrimination.py | L32-33 | 补全 E4 不可比归因：增加"结构不同（TS+binned vs binned-only）"说明 | 2 行 |

### 可选修复项清单（P0-轻微，成立或部分成立）

| 序号 | 攻击点 | 文件 | 行号 | 改动 | 价值 |
|------|--------|------|------|------|------|
| 3 | A5 | scripts/run_e2_ablation_discrimination.py | L36 | "≈0" → "≈0 或为负（过拟合风险）" | 低（文档精确性） |
| 4 | A6 | scripts/run_e2_ablation_discrimination.py | L8 | "按预测熵" → "按TS校准后预测熵" | 中（概述-详述一致性） |
| 5 | A10 | scripts/run_e2_ablation_discrimination.py | L20 | "可加性解释" → "可解释性" | 中（数学精确性） |
| 6 | A7 | scripts/run_e2_ablation_discrimination.py | L19 | 补注"reliability 边际贡献恒为 0" | 低（期望管理） |

### 可关闭的攻击点

| 攻击点 | 关闭理由 |
|--------|---------|
| **A2** | ablation study 标准 notation 约定，反方自身承认"可接受"。修复反而降低可读性。 |
| **A4** | 假设改变是嵌套修复的数学必然（非独立选择），post-TS 熵分箱科学上更合理（非更弱），docstring 已有诚实报告机制。反方未提供"更弱"的实际证据。 |
| **A8** | **稻草人论证**。H(p) 是函数定义（p 为形式参数），H(TS(p)) 是具体应用，标准数学/编程约定，完全自洽。反方自身已承认"函数是通用的"。 |
| **A9** | 代码 docstring 用 0-indexed（与 Python 一致），数学公式用 1-indexed（与数学文献一致），不同上下文用不同约定是正确做法。反方自身承认"不影响代码"。 |

### 整体评估

**反方攻击质量评估**：
- 反方进行了认真的逐行代码验证，10 个攻击点均有具体行号和代码证据，无臆测
- 但攻击质量参差不齐：
  - **高质量攻击**：A1（真实矛盾，必修）、A5/A6/A10（文档精确性问题，成立）
  - **中等质量攻击**：A3（归因不完整但结论正确，严重程度被夸大）、A4（误解改变性质，严重程度被夸大）
  - **低质量攻击**：A8（稻草人论证）、A9（误解约定差异）、A2（notation 约定，反方自身承认可接受）

**严重程度夸大分析**：
- A3：反方标 P0-严重，实际 P0-中等（归因不完整但结论正确）
- A4：反方标 P0-中等，实际 P0-轻微（嵌套修复的数学必然，非独立假设改变）
- 共 2 处严重程度被夸大

**稻草人论证分析**：
- A8：反方将函数定义中的形式参数 p 歪曲为"raw 概率 p"，构造虚假冲突
- 共 1 处稻草人论证

**R4 修复建议**：
- **必修**：1 项（A1，1 行改动）——修复 CSV T_global 报告
- **建议**：1 项（A3，2 行改动）——补全 E4 不可比归因
- **可选**：4 项（A5, A6, A7, A10，共约 4 行改动）——文档精确性改进
- **关闭**：4 项（A2, A4, A8, A9）——notation 约定/稻草人/误解

**与反方判定的差异**：
- 反方判定需 R4 修复 2 个 P0-严重 + 1 个 P0-中等 + 5 个 P0-轻微
- 本审查判定需 R4 修复 **1 个 P0-严重** + 1 个 P0-中等 + 4 个 P0-轻微
- 差异原因：A3 降级（P0-严重 → P0-中等）、A4 降级（P0-中等 → P0-轻微并关闭）、A8/A9 驳回（稻草人/误解约定）

**最终结论**：反方攻击部分有效。A1 是真实必修问题（CSV T_global 报告与 docstring 矛盾），需 R4 修复。A3 是有价值的建议改进（归因完整性）。其余攻击为文档精确性改进（可选）或可关闭（notation 约定/稻草人/误解）。R3 修复的核心声明（Fix-1 嵌套关系、Fix-2 分箱变量描述、Fix-3 ≡0 by construction）均经代码验证为正确。
