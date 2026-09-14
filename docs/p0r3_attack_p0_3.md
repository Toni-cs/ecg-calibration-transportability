# P0-3 R3轮反方攻击报告

> **反方挑刺代理交付**（任务 #97）。本报告对正方论证代理在 R3 轮对 `scripts/run_e2_ablation_discrimination.py` 的 3 个 docstring 修复进行全方位攻击审查。
> **审查日期**：2026-09-09
> **审查代理**：反方挑刺代理（GLM-5.2）
> **攻击维度**：反例构造 / 逻辑断链 / 隐含假设 / 边界失效 / 自相矛盾 / 量级错误 / 语义偏移（7 维全扫）
> **判定原则**：逐条验证修复正确性，寻找反例、逻辑漏洞、新引入的不一致。对每个攻击点给出具体行号和代码片段作为证据。

---

## 0. R3修复内容回顾

| 修复点 | 优先级 | 位置 | 修复内容 |
|--------|--------|------|---------|
| Fix-1 | P0-严重 | L17 | docstring 嵌套符号 Θ_2 = {T_1..T_5} → Θ_2 = {T, T_1..T_5}（补上缺失的 T），Θ_3 同步 |
| Fix-2 | P0-严重 | L31-36 | 假设 A1 分箱变量 H(p) → H(TS(p))，并声明 E4 不可比 |
| Fix-3 | P0-中等 | L681 | Stage3−Stage2 print 中追加 "≡0 by construction: threshold只改argmax不改概率" 说明 |

---

## 1. 逐修复点攻击审查

### 1.1 Fix-1：L17 嵌套符号 Θ_2 = {T, T_1..T_5}

#### 修复后文本（L17）
```
    Θ_1 = {T}                    ⊂ Θ_2 = {T, T_1..T_5}     ⊂ Θ_3 = {T, T_1..T_5, τ_1..τ_K}
```

#### 攻击维度 1：反例构造 — **未发现可攻击点**

嵌套关系 Θ_1 ⊂ Θ_2 ⊂ Θ_3 作为集合包含关系成立：
- Θ_1 = {T} ⊂ Θ_2 = {T, T_1..T_5}：{T} 是 {T, T_1..T_5} 的真子集 ✓
- Θ_2 ⊂ Θ_3 = {T, T_1..T_5, τ_1..τ_K}：{T, T_1..T_5} 是 {T, T_1..T_5, τ_1..τ_K} 的真子集 ✓

代码验证：Stage 2（L478-480）确实复用 Stage 1 的 `ts_params`（含 T_global），并在 TS 输出上拟合 T_1..T_5。T 是 Stage 2 的参数（继承自 Stage 1），T_1..T_5 是 Stage 2 新拟合的参数。Θ_2 = {T, T_1..T_5} 准确描述了 Stage 2 的参数空间。

#### 攻击维度 2：自相矛盾 — **发现攻击点 A1（P0-严重）**

**攻击点 A1：Fix-1 引入新的 docstring-CSV 语义偏移——T_global 在 Stage 2/3 的 CSV 中报告为 nan，与 Θ_2 包含 T 矛盾**

**证据**：
- L17（Fix-1 修复后）：`Θ_2 = {T, T_1..T_5}` — 声明 T 是 Stage 2 的参数
- L499（CSV 输出代码）：
  ```python
  "T_global": T_global if stage_name in ("stage1_ts",) else np.nan,
  ```
  T_global 仅对 `stage1_ts` 报告，对 `stage2_ts_binned` 和 `stage3_ts_binned_threshold` 报告为 `np.nan`

**矛盾分析**：
- Fix-1 之前：docstring 说 Θ_2 = {T_1..T_5}（不含 T），CSV 对 Stage 2 报告 T_global=nan → **一致**
- Fix-1 之后：docstring 说 Θ_2 = {T, T_1..T_5}（含 T），CSV 对 Stage 2 仍报告 T_global=nan → **不一致**

Fix-1 修复了数学嵌套关系，但**引入了新的 docstring-CSV 偏移**：docstring 声明 T ∈ Θ_2，但 CSV 输出对 Stage 2/3 的 T_global 列为 nan，暗示 T 不是 Stage 2/3 的参数。审稿人从 CSV 验证嵌套关系时会发现 T_global 缺失，无法从 CSV 独立验证 Θ_1 ⊂ Θ_2。

**严重程度**：P0-严重。这不是纯文档问题——CSV 是论文的原始数据来源，CSV 中 T_global=nan 会让审稿人误以为 Stage 2 不使用全局 T（即 Stage 2 是 binned-only 而非 TS+binned），这与 R2 轮 P0-3 的核心修复（Stage 2 = TS+binned）直接矛盾。

**修复建议**：L499 改为：
```python
"T_global": T_global if stage_name != "raw" else np.nan,
```
即对 stage1_ts / stage2_ts_binned / stage3_ts_binned_threshold 均报告 T_global，仅 raw 报告 nan。

#### 攻击维度 3：隐含假设 — **发现攻击点 A2（P0-轻微）**

**攻击点 A2：Θ_2 = {T, T_1..T_5} 隐含 T 与 T_1..T_5 独立，但代码中 T_1..T_5 依赖 T**

L17 的集合 notation Θ_2 = {T, T_1..T_5} 隐含 T 和 T_1..T_5 是独立参数。但代码中：
- L467: `ts_params = fit_temperature_multiclass(cal_p, cal_y)` — 先拟合 T
- L469: `cal_s1 = apply_temperature_multiclass(cal_p, ts_params)` — 用 T 校准
- L478: `binned_params = fit_binned_temperature(cal_s1, cal_y)` — 在 TS 输出上拟合 T_1..T_5

T_1..T_5 是在 TS(cal_p, T) 上拟合的，因此 T_1..T_5 **条件依赖于 T**。这不是一个简单的参数集合，而是一个有序的参数拟合流程。集合 notation 无法表达这种依赖关系。

**严重程度**：P0-轻微。这是 ablation study 中常见的 notation 简化，不影响边际贡献的可解释性（控制 T 后加 T_1..T_5 的边际效应是良定义的），但严格的数学表述应写 Θ_2 = {T, T_1..T_5 | T_1..T_5 = f(T)}。

#### 攻击维度 4：语义偏移 — **未发现可攻击点**

Θ_3 = {T, T_1..T_5, τ_1..τ_K} 中 K 未在 docstring 中显式定义。但从代码 L461 `K = data["num_classes"]` 和 L484 `optimize_thresholds(cal_s2, cal_y, K)` 可知 K = num_classes。这是轻微的文档缺口，但不构成语义偏移（K 的含义可从上下文推断）。

#### Fix-1 小结

| 攻击点 | 维度 | 严重程度 | 状态 |
|--------|------|---------|------|
| A1: T_global CSV=nan 与 Θ_2 含 T 矛盾 | 自相矛盾 | **P0-严重** | **成立** |
| A2: Θ_2 notation 隐含独立性但实际有依赖 | 隐含假设 | P0-轻微 | 成立（notation 简化，可接受） |

---

### 1.2 Fix-2：L31-36 假设 A1 分箱变量 H(p) → H(TS(p)) + E4 不可比声明

#### 修复后文本（L31-36）
```
A1. binned temperature 的分箱变量=TS 校准后预测分布熵 H(TS(p))=−Σ p'_k log p'_k，
    其中 p'=TS(p)（Stage 1 的温度缩放输出）。注意：E4 的 binned-T 分箱变量
    为 H(p)（对原始概率分箱），两者分箱变量不同，不可直接比较。
    假设：不确定度高的样本段需要不同的锐度校准（置信与不确定样本
    的 over/under-confidence 模式不同）。若该假设不成立，
    Stage2−Stage1 ≈ 0（脚本会如实报告）。
```

#### 攻击维度 1：反例构造 — H(TS(p)) 描述代码行为 — **未发现可攻击点**

逐行验证代码：
- L478: `binned_params = fit_binned_temperature(cal_s1, cal_y)` — 传入 `cal_s1`
- L469: `cal_s1 = apply_temperature_multiclass(cal_p, ts_params)` — `cal_s1 = TS(cal_p)`
- L162（fit_binned_temperature 内）: `ent = _entropy(cal_probs)` — 计算 H(cal_s1) = H(TS(cal_p))
- L479-480: `apply_binned_temperature(cal_s1, ...)` / `apply_binned_temperature(test_s1, ...)` — 应用时也用 H(TS(p)) 分箱

**结论**：fit 和 apply 均使用 H(TS(p)) 作为分箱变量。Fix-2 对分箱变量的描述**准确无误**。

#### 攻击维度 2：反例构造 — E4 不可比声明 — **发现攻击点 A3（P0-严重）**

**攻击点 A3：E4 不可比的原因解释不完整且误导——归因于"分箱变量不同"，但根本原因是"结构不同"（E2=TS+binned 双层 vs E4=binned-only 单层）**

**证据 — E4 的 binned-T 实现**：
- E4 L518: `T_per_bin, bin_edges, bin_records = fit_binned_T(cal_probs, cal_labels, n_bins=N_BINS)` — **直接对 raw cal_probs 拟合 binned-T**，未先应用 global T
- E4 L521-522: `apply_binned_T(id_probs, ...)` / `apply_binned_T(ood_probs, ...)` — **直接对 raw probs 应用 binned-T**
- E4 L376: `ent = predictive_entropy(cal_probs)` — 分箱变量 = H(p)（raw entropy）

**证据 — E2 的 Stage 2 实现**：
- E2 L478: `fit_binned_temperature(cal_s1, cal_y)` — 对 **TS(cal_p)** 拟合 binned-T
- E2 L479-480: `apply_binned_temperature(cal_s1, ...)` / `apply_binned_temperature(test_s1, ...)` — 对 **TS 输出** 应用 binned-T

**结构差异对比**：

| 属性 | E2 Stage 2 | E4 binned-T |
|------|-----------|-------------|
| 输入到 binned-T | TS(p)（先全局校准） | p（raw 概率） |
| 分箱变量 | H(TS(p)) | H(p) |
| 结构 | 双层：global T → binned T | 单层：binned T only |
| 是否复用 global T | 是（L467 的 ts_params） | 否（独立拟合） |

**攻击论证**：

L32-33 声明："E4 的 binned-T 分箱变量为 H(p)（对原始概率分箱），两者分箱变量不同，不可直接比较。"

这将不可比性**归因于分箱变量不同**（H(TS(p)) vs H(p)）。但更根本的不可比原因是**结构不同**：
- E2 Stage 2 是 **TS + binned**（先全局 T 校准，再在 TS 输出上分箱拟合 binned-T）
- E4 binned-T 是 **binned-only**（直接在 raw 概率上分箱拟合 binned-T，不先做全局 T）

即使两者的分箱变量相同（都是 H(p)），E2 的 binned-T 作用于 TS(p) 而 E4 的 binned-T 作用于 p，结果仍然不可比。分箱变量差异只是不可比的一个**次要原因**，结构差异才是**根本原因**。

Fix-2 的不可比声明**结论正确**（确实不可比），但**归因错误/不完整**。这会误导审稿人：审稿人可能以为只要统一分箱变量就能让 E2 和 E4 可比，但实际上即使统一分箱变量，由于结构差异（TS+binned vs binned-only），结果仍不可比。

**严重程度**：P0-严重。在 CBM 期刊审稿中，不可比声明的归因必须准确。错误的归因比不声明更危险——它给审稿人一个虚假的可修复路径（"统一分箱变量即可"），而真正的修复路径（"统一结构"）被掩盖。

**修复建议**：L32-33 改为：
```
    其中 p'=TS(p)（Stage 1 的温度缩放输出）。注意：E4 的 binned-T 直接对
    原始概率 p 拟合（binned-only，不先做全局 TS），而 E2 Stage 2 在 TS 输出
    上拟合（TS+binned 双层）。两者不仅分箱变量不同（H(p) vs H(TS(p))），
    且输入结构不同（raw vs TS output），不可直接比较。
```

#### 攻击维度 3：隐含假设 — **发现攻击点 A4（P0-中等）**

**攻击点 A4：Fix-2 改变了科学假设本身——从"raw 不确定度驱动分箱"变为"post-TS 不确定度驱动分箱"，但未讨论这一改变的科学合理性**

Fix-2 将分箱变量从 H(p) 改为 H(TS(p))。这不只是描述修正，而是**假设本身的改变**：
- 原假设：模型 raw 输出的不确定度驱动分箱（H(p)）
- 新假设：TS 校准后的不确定度驱动分箱（H(TS(p))）

这两个假设有科学差异：
- H(p) 分箱：基于模型原始置信度分组，bin 在校准前确定
- H(TS(p)) 分箱：基于校准后置信度分组，bin 依赖 T（T 变则 bin 变）

Fix-2 正确地让 docstring 匹配代码，但未讨论 post-TS 熵分箱是否比 raw 熵分箱更合理。如果 post-TS 熵分箱在科学上更弱（例如：T 的拟合噪声会传播到分箱），则代码实现的是一个更弱的方法，而 docstring 未提示这一风险。

**严重程度**：P0-中等。这是科学诚实性问题——docstring 应注明"post-TS 熵分箱依赖 T 的拟合质量，T 估计有噪声时分箱边界不稳定"。

#### 攻击维度 4：边界失效 — **发现攻击点 A5（P0-轻微）**

**攻击点 A5：L36 "Stage2−Stage1 ≈ 0" 忽略过拟合风险——A1 不成立时 Δ 可能为负（binned-T 过拟合使 reliability 恶化）**

L36: "若该假设不成立，Stage2−Stage1 ≈ 0（脚本会如实报告）。"

这声称 A1 不成立时 Stage2−Stage1 ≈ 0。但 A1 不成立时，binned-T 可能：
1. 拟合 T_1≈T_2≈...≈T_5≈1（无校准）→ Stage2 ≈ Stage1，Δ ≈ 0 ✓
2. **过拟合**：在 cal 上拟合出差异化的 T_1..T_5，但在 test 上不泛化 → Stage2 的 reliability **恶化**（Δ < 0，reliability 增加是坏事）

情况 2 在小 cal 集（n_cal=60 smoke 场景）下完全可能发生。L40-41 的 A3 假设（每箱 ≥10 样本）正是为了防止过拟合，但如果 A3 也不满足（部分箱 T=1.0，其余箱过拟合），Stage2 可能比 Stage1 更差。

"≈ 0" 忽略了过拟合导致的负 Δ 风险。更准确的表述应为"Stage2−Stage1 ≈ 0 或为负（过拟合风险）"。

**严重程度**：P0-轻微。代码会如实报告 Δ（包括负值），所以这是文档表述不精确，不影响代码正确性。

#### 攻击维度 5：语义偏移 — **发现攻击点 A6（P0-轻微）**

**攻击点 A6：L8 "按预测熵" 与 L31 "H(TS(p))" 语义不一致——L8 未指定是 raw 还是 TS 校准后熵**

L8: "Stage 2: TS + binned T — 按预测熵(不确定度)分 5 箱，每箱一个 T"

Fix-2 将 L31 改为 H(TS(p))，但 L8 仍说"按预测熵"未指定是 raw 还是 TS 校准后。读者阅读 L8 时会自然理解为 H(p)（raw 熵），与 L31 的 H(TS(p)) 矛盾。

**严重程度**：P0-轻微。L31-33 有详细说明，L8 是概述，但概述与详述的语义应一致。

**修复建议**：L8 改为 "按 TS 校准后预测熵(不确定度)分 5 箱，每箱一个 T"。

#### 攻击维度 6：逻辑断链 — **未发现可攻击点**

L31-33 的推理链条完整：分箱变量 = H(TS(p)) → p' = TS(p) → E4 用 H(p) → 分箱变量不同 → 不可比。每一步都有代码证据支撑。

#### 攻击维度 7：量级错误 — **未发现可攻击点**

无复杂度/收敛性/稳定性估计涉及。

#### Fix-2 小结

| 攻击点 | 维度 | 严重程度 | 状态 |
|--------|------|---------|------|
| A3: E4 不可比归因不完整（漏结构差异） | 反例构造 | **P0-严重** | **成立** |
| A4: 假设改变未讨论科学合理性 | 隐含假设 | P0-中等 | 成立 |
| A5: L36 "≈0" 忽略过拟合负 Δ 风险 | 边界失效 | P0-轻微 | 成立 |
| A6: L8 "按预测熵" 与 L31 H(TS(p)) 不一致 | 语义偏移 | P0-轻微 | 成立 |

---

### 1.3 Fix-3：L681 Stage3−Stage2 ≡ 0 by construction 声明

#### 修复后文本（L681）
```python
print(f"  Stage3 +threshold opt:    {s2:.4f} → {s3:.4f} (Δ={s3-s2:+.4f}, ≡0 by construction: threshold只改argmax不改概率)")
```

#### 攻击维度 1：反例构造 — **未发现可攻击点**

逐行验证 "≡0 by construction" 声明：

1. L486: `cal_s3, test_s3 = cal_s2, test_s2` — **同一对象引用**（非拷贝）
2. L489-506: ablation 循环对 Stage 2 用 `test_s2`，对 Stage 3 用 `test_s3`
3. 由于 `test_s3 is test_s2`（同一引用），`calibration_reliability(test_s3, test_y)` 与 `calibration_reliability(test_s2, test_y)` 输入完全相同
4. L314-315: `max_prob = probs.max(axis=1)` 和 `correct = (probs.argmax(axis=1) == labels)` — probs 相同则 max_prob 和 correct 相同
5. L317: `brier_parts(max_prob, correct, n_bins=N_BINS)` — 输入相同则输出相同
6. 因此每个实验的 Stage 2 和 Stage 3 的 `brier_reliability` **逐位相同**
7. L675-676: `s2` 和 `s3` 是相同值的 mean → `s3 - s2 = 0.0` **精确为零**（非近似）

**结论**："≡0 by construction" 声明**数学正确**。threshold 只改 argmax（L207: `(probs - thresholds[None, :]).argmax(axis=1)`），不改概率（L486: `cal_s3, test_s3 = cal_s2, test_s2`）。Brier reliability 基于概率（max_prob）和 argmax（correct），概率不变则 reliability 不变。

#### 攻击维度 2：边界失效 — **未发现可攻击点**

- 空 DataFrame：L665 `if not df_abl.empty:` 守卫，空时不执行该 print ✓
- 部分实验失败：run_single_experiment 要么返回 4 行（raw/stage1/stage2/stage3），要么返回 0 行（L455-457），不存在有 stage2 无 stage3 的情况 ✓
- 浮点精度：s2 和 s3 是相同 float 值的 mean，`s3 - s2` 精确为 0.0（非浮点误差）✓

#### 攻击维度 3：自相矛盾 — **发现攻击点 A7（P0-轻微）**

**攻击点 A7：L681 声明 "≡0 by construction" 但 L19 说 "ΔReliability(Stage3−Stage2) = threshold opt 的边际贡献"——边际贡献恒为 0 意味着 Stage 3 对 reliability 无贡献，但 docstring 未显式说明这一含义**

L19: "ΔReliability(Stage3−Stage2) = threshold opt 的边际贡献（控制 binned T 后）"
L681: "≡0 by construction: threshold只改argmax不改概率"

L19 说边际贡献 = threshold opt 的贡献，L681 说这个贡献 ≡ 0。逻辑上自洽（边际贡献 = 0），但 docstring 未在 L19 处显式注明"此边际贡献对 reliability 恒为 0，threshold opt 仅影响判别指标（F1/PPV/NPV/MCC）"。

读者阅读 L19 时会期望 Stage 3 对 reliability 有非零边际贡献，直到看到 L681 的 print 才意识到恒为 0。这是**期望管理问题**——L19 应提前声明"reliability 边际贡献恒为 0；threshold opt 仅改善判别指标"。

**严重程度**：P0-轻微。L681 的 print 声明是诚实的，但 L19 的 docstring 应同步说明。

#### 攻击维度 4：语义偏移 — **未发现可攻击点**

"threshold只改argmax不改概率" 准确描述了 L486 的代码行为（概率不变）和 L207 的 threshold 机制（改 argmax）。

#### Fix-3 小结

| 攻击点 | 维度 | 严重程度 | 状态 |
|--------|------|---------|------|
| A7: L19 未提前说明 Stage3 reliability 边际贡献恒为 0 | 自相矛盾 | P0-轻微 | 成立（期望管理问题） |

---

## 2. 全维度攻击扫描 — 其他 docstring-代码偏移

### 2.1 逐行 docstring-代码一致性检查

| 行号 | docstring 声明 | 对应代码 | 一致性 |
|------|---------------|---------|--------|
| L8 | "按预测熵(不确定度)分 5 箱" | L131 N_BINS_TEMPERATURE=5, L162 _entropy | ⚠️ A6: "预测熵"未指定 raw/TS |
| L9 | "在 binned 基础上优化分类阈值 τ_k" | L484 optimize_thresholds(cal_s2, cal_y, K) | ✓ |
| L17 | Θ_2 = {T, T_1..T_5} | L478 fit_binned_temperature(cal_s1,...) 复用 T | ✓（但 CSV 报告不一致，见 A1） |
| L22 | "TS 保持 argmax 不变" | softmax(log p / T) 对 T>0 保序 | ✓ |
| L24 | "二分类下 TS 是单调变换→严格不变" | 二分类 softmax 单调性 | ✓ |
| L25 | "多分类 OvR 下 TS 不保证逐类保序" | 多分类 OvR AUROC 可能微变 | ✓ |
| L26 | "Stage 3 的 threshold optimization 改变 argmax" | L207 (probs - thresholds).argmax | ✓ |
| L31 | "H(TS(p))=−Σ p'_k log p'_k" | L162 _entropy(cal_s1), L478 cal_s1=TS(cal_p) | ✓ |
| L32-33 | "E4 的 binned-T 分箱变量为 H(p)" | E4 L376 predictive_entropy(cal_probs), L518 fit_binned_T(cal_probs,...) | ✓（但归因不完整，见 A3） |
| L37 | "threshold optimization 在 cal 集上拟合" | L484 optimize_thresholds(cal_s2, cal_y, K) | ✓ |
| L39 | "脚本同时报告 cal 上最优 τ 在 test 上的表现" | L484 fit on cal, L528-529 apply on test | ✓ |
| L40 | "每箱样本量 ≥ 10 才拟合" | L132 MIN_SAMPLES_PER_BIN=10, L171-172 | ✓ |
| L50 | "脚本实测 \|ΔAUROC\| 并报告" | L543 delta_auroc, L554 print | ✓ |
| L58 | "T_binned(mean,min,max)" | L500-502 | ✓ |
| L60 | "variant(raw/ts/binned/threshold)" | L516, L522, L526 | ✓ |
| L61 | "auroc_ts_minus_raw(诚实校验列)" | L561 | ✓ |
| L142 | "H(p) = -Σ p_k log p_k" | L143-144 _entropy 实现 | ⚠️ A8: H(p) vs L31 H(TS(p)) 符号冲突 |
| L159 | "T_0..T_{n_bins-1}" | L17 用 T_1..T_5 | ⚠️ A9: 0-indexed vs 1-indexed |
| L499 | T_global 仅 stage1_ts 报告 | L17 Θ_2 含 T | ❌ A1: docstring-CSV 矛盾 |

### 2.2 新发现攻击点

#### 攻击点 A8（P0-轻微）：L142 _entropy docstring H(p) 与 L31 H(TS(p)) 符号冲突

L142: `"""预测分布熵 H(p) = -Σ p_k log p_k（不确定度度量）"""`

_entropy 函数是通用的（计算输入的熵），当传入 TS(p) 时计算 H(TS(p))。但 docstring 写 H(p)，与 L31 的 H(TS(p)) 在符号上冲突。读者可能误以为 _entropy 始终计算 raw 概率熵。

**严重程度**：P0-轻微。函数是通用的，H(p) 中的 p 指"输入概率"（泛型），但与 L31 的具体语义有符号碰撞。

#### 攻击点 A9（P0-轻微）：L159 T_0..T_{n_bins-1} 与 L17 T_1..T_5 索引约定不一致

L159: `'temperatures': [T_0..T_{n_bins-1}],` — 0-indexed
L17: `Θ_2 = {T, T_1..T_5}` — 1-indexed

同一文件内对 binned temperature 的索引约定不统一（0-indexed vs 1-indexed）。

**严重程度**：P0-轻微。纯文档约定问题，不影响代码。

#### 攻击点 A10（P0-轻微）：L20 "可加性解释" 混淆了可解释性与可加性

L20: "嵌套结构保证边际贡献可加性解释（无参数空间交叉）"

"可加性"是平凡的 telescoping 性质：Rel(S3) - Rel(S1) = [Rel(S2) - Rel(S1)] + [Rel(S3) - Rel(S2)]。这对任何三阶段都成立，不需要嵌套结构保证。嵌套结构保证的是**可解释性**（每个边际贡献对应一个明确的组件增量），而非可加性。

**严重程度**：P0-轻微。概念表述不精确，但不影响实际消融分析的正确性。

---

## 3. 攻击点汇总（按严重程度排序）

### P0-严重（CBM 审稿标准下必须在论文投稿前修复）

| 序号 | 攻击点 | 位置 | 描述 | Fix 引入? |
|------|--------|------|------|----------|
| **A1** | T_global CSV=nan 与 Θ_2 含 T 矛盾 | L499 vs L17 | Fix-1 声明 T ∈ Θ_2，但 CSV 对 Stage 2/3 报告 T_global=nan，审稿人无法从 CSV 验证嵌套 | **是**（Fix-1 引入） |
| **A3** | E4 不可比归因不完整 | L32-33 | 归因于"分箱变量不同"，漏掉根本原因"结构不同"（E2=TS+binned 双层 vs E4=binned-only 单层） | **是**（Fix-2 引入） |

### P0-中等（影响科学严谨性但非阻塞）

| 序号 | 攻击点 | 位置 | 描述 | Fix 引入? |
|------|--------|------|------|----------|
| **A4** | 假设改变未讨论科学合理性 | L31-36 | H(p)→H(TS(p)) 改变了科学假设（raw 熵→post-TS 熵分箱），未讨论 post-TS 熵分箱的稳定性风险 | **是**（Fix-2 引入） |

### P0-轻微（文档精确性改进）

| 序号 | 攻击点 | 位置 | 描述 | Fix 引入? |
|------|--------|------|------|----------|
| A2 | Θ_2 notation 隐含独立性 | L17 | 集合 notation 隐含 T 与 T_1..T_5 独立，实际有依赖 | 是（Fix-1） |
| A5 | L36 "≈0" 忽略过拟合负 Δ | L36 | A1 不成立时 Δ 可能为负（过拟合），非 ≈0 | 否（预存） |
| A6 | L8 "按预测熵" 语义模糊 | L8 | 未指定 raw/TS 校准后，与 L31 不一致 | 是（Fix-2 引入） |
| A7 | L19 未提前说明 Stage3 Δ≡0 | L19 | 读者期望非零边际贡献，实际恒为 0 | 否（预存） |
| A8 | L142 H(p) vs L31 H(TS(p)) 符号冲突 | L142 | _entropy docstring 用 H(p)，与 L31 的 H(TS(p)) 碰撞 | 是（Fix-2 引入） |
| A9 | T_0..T_{n_bins-1} vs T_1..T_5 索引不一致 | L159 vs L17 | 0-indexed vs 1-indexed | 否（预存） |
| A10 | L20 "可加性" 混淆可解释性 | L20 | 可加性是平凡的，嵌套保证的是可解释性 | 否（预存） |

---

## 4. R3 修复评价

### 4.1 各 Fix 正确性评价

| Fix | 核心声明 | 代码验证 | 数学正确 | 引入新问题 |
|-----|---------|---------|---------|-----------|
| Fix-1 | Θ_2 = {T, T_1..T_5} | L478 复用 ts_params | ✓ 嵌套关系成立 | ❌ A1: CSV T_global=nan 矛盾 |
| Fix-2 | 分箱变量 = H(TS(p)) | L162 _entropy(cal_s1), cal_s1=TS(cal_p) | ✓ 描述准确 | ❌ A3: E4 不可比归因不完整 |
| Fix-3 | Stage3−Stage2 ≡ 0 | L486 cal_s3=test_s2 同引用 | ✓ 精确为零 | ✓ 无新问题 |

### 4.2 总体评价

**3 个 Fix 的核心声明均经代码验证为正确**：
- Fix-1 的嵌套关系 Θ_1 ⊂ Θ_2 ⊂ Θ_3 数学成立
- Fix-2 的 H(TS(p)) 分箱变量描述准确匹配代码
- Fix-3 的 ≡0 by construction 精确成立（同引用 → 同概率 → 同 reliability）

**但 Fix-1 和 Fix-2 各引入了 1 个 P0-严重新问题**：
- Fix-1 引入 A1：docstring 说 T ∈ Θ_2 但 CSV 报告 T_global=nan，破坏了 docstring-CSV 一致性
- Fix-2 引入 A3：E4 不可比声明归因于"分箱变量不同"，漏掉根本原因"结构不同"（TS+binned vs binned-only），误导审稿人

**R3 修复部分收敛但未完全收敛**：3 个目标修复点全部正确修复，但引入了 2 个新的 P0-严重问题。需 R4 轮修复 A1（CSV T_global 报告）和 A3（E4 不可比归因补全）。

### 4.3 与 R2 终审判定的对比

R2 终审判定（`p0r2_final_verdict.md` §2.3）要求 R3 修复：
1. [P0-严重] B2: L17 Θ_2 补 T → **Fix-1 已完成，但引入 A1**
2. [P0-严重] B3: L31-34 H(p)→H(TS(p)) + E4 不可比 → **Fix-2 已完成，但引入 A3**
3. [P0-中等] B5: L679 ≡0 by construction → **Fix-3 已完成，无新问题**

R2 判定的 3 个必修项中，2 个完成但引入新问题，1 个完全完成。R3 修复**部分达成 R2 要求**。

---

## 5. R4 修复建议

### P0-严重（必修）

| 序号 | 攻击点 | 文件 | 行号 | 改动内容 | 改动量 |
|------|--------|------|------|---------|--------|
| 1 | A1 | scripts/run_e2_ablation_discrimination.py | L499 | `T_global if stage_name in ("stage1_ts",) else np.nan` → `T_global if stage_name != "raw" else np.nan` | 1行 |
| 2 | A3 | scripts/run_e2_ablation_discrimination.py | L32-33 | 补全 E4 不可比归因：增加"结构不同（TS+binned vs binned-only）"说明 | 2行 |

### P0-中等（建议）

| 序号 | 攻击点 | 文件 | 行号 | 改动内容 |
|------|--------|------|------|---------|
| 3 | A4 | scripts/run_e2_ablation_discrimination.py | L34-36 | 补注 post-TS 熵分箱的稳定性风险 |
| 4 | A6 | scripts/run_e2_ablation_discrimination.py | L8 | "按预测熵" → "按TS校准后预测熵" |

### P0-轻微（可选）

| 序号 | 攻击点 | 改动内容 |
|------|--------|---------|
| 5 | A8 | L142 _entropy docstring 注明"p 为输入概率（调用方决定语义）" |
| 6 | A9 | L159 统一为 1-indexed T_1..T_{n_bins} |
| 7 | A10 | L20 "可加性解释" → "可解释性（边际贡献对应明确组件增量）" |
| 8 | A5 | L36 "≈0" → "≈0 或为负（过拟合风险）" |
| 9 | A7 | L19 补注 "reliability 边际贡献恒为 0；threshold opt 仅改善判别指标" |

---

## 6. 对抗透明性声明

### 6.1 尝试的全部 7 个攻击维度

| 维度 | 是否发现攻击点 | 涉及攻击点 |
|------|--------------|-----------|
| 反例构造 | 是 | A3（E4 不可比归因反例） |
| 逻辑断链 | 否 | — |
| 隐含假设 | 是 | A2（Θ_2 独立性隐含）、A4（假设改变未讨论） |
| 边界失效 | 是 | A5（过拟合负 Δ 边界） |
| 自相矛盾 | 是 | A1（docstring-CSV 矛盾）、A7（L19 vs L681 期望矛盾） |
| 量级错误 | 否 | — |
| 语义偏移 | 是 | A6（L8 语义模糊）、A8（H(p) 符号冲突）、A9（索引不一致）、A10（可加性混淆） |

### 6.2 证据来源

所有攻击点均基于直接读取源代码验证：
- `scripts/run_e2_ablation_discrimination.py`（完整读取 714 行）
- `scripts/run_e4_temperature_analysis.py`（关键函数 fit_binned_T L366-408、apply_binned_T L411-426、process_one L490-522）
- `docs/p0r2_final_verdict.md`（R3 修复要求）

无稻草人论证、无臆测。每个攻击点均附具体行号和代码片段。

### 6.3 Fix-3 无攻击声明

Fix-3（L681 ≡0 by construction）经全 7 维度扫描未发现有效攻击点。该修复的数学声明精确成立（同引用 → 同概率 → 同 reliability → Δ 精确为 0）。仅发现 A7（P0-轻微，L19 期望管理问题），且 A7 是预存问题非 Fix-3 引入。**Fix-3 完全通过攻击审查。**

---

## 7. 最终判定

| Fix | 核心声明正确 | 引入新 P0-严重 | 引入新 P0-中等 | 引入新 P0-轻微 | 判定 |
|-----|------------|--------------|--------------|--------------|------|
| Fix-1 | ✓ | 1（A1） | 0 | 1（A2） | **需 R4 修复** |
| Fix-2 | ✓ | 1（A3） | 1（A4） | 2（A6, A8） | **需 R4 修复** |
| Fix-3 | ✓ | 0 | 0 | 0 | **通过** |

**总体判定**：P0-3 的 R3 轮 3 个 docstring 修复中，**Fix-3 完全通过**，**Fix-1 和 Fix-2 核心声明正确但各引入 1 个 P0-严重新问题**（A1: docstring-CSV 矛盾，A3: E4 不可比归因不完整）。需 R4 轮修复 2 个 P0-严重 + 1 个 P0-中等，约 5 行改动。

**R4 修复量预估**：必修 2 项约 3 行，建议 2 项约 2 行，可选 5 项约 5 行。涉及 1 个文件（`scripts/run_e2_ablation_discrimination.py`）。
