# E3 反方攻击元审查裁决报告

> **反反方审查代理-E3 交付**。本报告对反方挑刺代理提交的 `adversarial_r1_attack_e3.md`（21 个攻击点：F1-F4 致命、S1-S10 严重、M1-M7 轻微）进行逐条元审查，评估每个攻击是否为稻草人论证、是否误解正方意图、反例是否真的成立、攻击逻辑是否自洽。
> **审查日期**：2026-09-09
> **审查对象**：`docs/adversarial_r1_attack_e3.md`（反方攻击报告）
> **被攻击脚本**：`scripts/run_e3_brier_dcr_ncv.py`（revision 296db60a, 983 行）
> **依赖代码**：`src/utils/calibration.py`（revision 4fb8f570）
> **参照方案**：`docs/Q2_UPGRADE_PROPOSAL_R5.md` §3.2 E3
> **审查代理**：反反方审查代理-E3（GLM-5.2，元审查者角色）
> **审查维度**：反例是否成立 / 稻草人论证 / 误解前提 / 攻击逻辑自洽 / 严重程度是否夸大

---

## 0. 裁决概述

### 裁决汇总表

| 编号 | 反方标注 | 裁决 | 修正后严重性 | 裁决理由摘要 |
|------|---------|------|-------------|-------------|
| F1 | 致命 | **成立** | 致命 | 真实代码 bug：`brier_parts()` 签名无 `n_bins`，E3 传入被静默丢弃 |
| F2 | 致命 | **部分成立** | 轻微→严重 | 恒等式 tautological 属实但已显式文档化；reliability 分量是经验量非构造量；主终点不受影响，仅 brier_raw 未进 summary（即 M5） |
| F3 | 致命 | **部分成立** | 严重 | 阈值无理论依据、无 fallback 属实；但"循环推理"标签过重——H1 在精确分箱极限是定理非假设，主终点选择有理论先验 |
| F4 | 致命 | **部分成立** | 严重 | 独立性违反属实、pair-level 聚合未实现属实；但 ρ=0.3 估计是推测，不同 seed/arch 产生不同模型，相关性被高估 |
| S1 | 严重 | **成立** | 严重 | CI 方法确实用 percentile 而非 BCa，违反项目 own F2 修复标准 |
| S2 | 严重 | **部分成立** | 轻微 | 数学完全正确（`ttest_rel(0,x)=ttest_1samp(x,0)`），仅代码可读性问题 |
| S3 | 严重 | **部分成立** | 轻微 | 非独立性属实但脚本已主动披露并计算 `ncv_per_sample`；代码遵循 R5 规范定义 |
| S4 | 严重 | **成立** | 严重 | docstring 声称 0.3/0.7 敏感性但代码未实现 |
| S5 | 严重 | **部分成立** | 严重 | 阈值无理论依据、无 fallback 属实（与 F3 重叠）；均值比掩盖异质性属实 |
| S6 | 严重 | **部分成立** | 轻微 | n=60 时 CLT 提供合理稳健性；右偏声称是推测无数据支撑 |
| S7 | 严重 | **成立** | 严重 | ECE 可变 vs Brier 硬编码，修改 N_BINS 会静默不一致（F1 的直接后果） |
| S8 | 严重 | **部分成立** | 轻微 | 语义差异属实但代码已同时报告两种度量并标注敏感性；仅需文档化 |
| S9 | 严重 | **部分成立** | 严重 | T 在 source-cal 拟合、OOD 评估无显式 sanity check 属实；ID 指标已计算但未做对比 |
| S10 | 严重 | **部分成立** | 轻微 | 空 bin 属实但影响有限（8 vs 10 有效 bin），且 ECE 有同样问题 |
| M1 | 轻微 | **部分成立** | 轻微 | 多种子稳定性检查有价值但单种子是可复现性标准做法 |
| M2 | 轻微 | **成立** | 轻微 | n=1 退化无警告 |
| M3 | 轻微 | **部分成立** | 轻微 | 2 个检验的 FDR≈Bonferroni 属实但 FDR 校正仍有效 |
| M4 | 轻微 | **成立** | 轻微 | CSV 注释行非标准格式 |
| M5 | 轻微 | **成立** | 轻微 | brier_raw 已计算但未进 summary |
| M6 | 轻微 | **成立** | 轻微 | T 分布未汇总 |
| M7 | 轻微 | **部分成立** | 轻微 | 零测度事件但值得文档化 |

### 裁决统计

| 裁决类别 | 数量 | 编号 |
|---------|------|------|
| **成立** | 8 | F1, S1, S4, S7, M2, M4, M5, M6 |
| **部分成立** | 13 | F2, F3, F4, S2, S3, S5, S6, S8, S9, S10, M1, M3, M7 |
| **驳回** | 0 | — |
| **总计** | 21 | — |

### 严重性修正统计

| 反方标注 | 数量 | 修正后 |
|---------|------|--------|
| 致命→致命 | 1 | F1 |
| 致命→严重 | 2 | F3, F4 |
| 致命→轻微 | 1 | F2 |
| 严重→严重 | 4 | S1, S4, S5, S7, S9 |
| 严重→轻微 | 5 | S2, S3, S6, S8, S10 |
| 轻微→轻微 | 7 | M1-M7（不变） |

**关键结论**：21 个攻击点中，8 个完全成立、13 个部分成立（多数因严重程度被夸大而降级）、0 个被完全驳回。反方攻击整体质量较高，未发现稻草人论证或完全误解正方意图的情况，但 **4 个致命攻击中有 3 个严重程度被夸大**（F2 应降为轻微、F3/F4 应降为严重），仅 F1 维持致命。

---

## 1. 致命攻击裁决 (Fatal)

### F1：`brier_parts()` 静默丢弃 `n_bins` 参数

**反方主张**：`brier_parts()` 签名无 `n_bins` 参数，E3 的 `brier_parts_toplabel` 和 `brier_parts_ovr` 接受 `n_bins=N_BINS` 但从未传递给 `brier_parts()`，导致 Brier 分解永远用硬编码 10 bin，A1 缓解方案（增加 bin 数）无法通过修改 `N_BINS` 实现。

**逐维审查**：

1. **反例是否成立**：✅ 成立。经代码验证：
   - `calibration.py` L586：`def brier_parts(probs, labels):` — 签名确实无 `n_bins`
   - `calibration.py` L603：`bins = np.linspace(0, 1, 11)` — 确实硬编码 10 bin
   - E3 L181：`return brier_parts(max_p, correct)` — 确实未传递 `n_bins`
   - E3 L199：`b, r, s, u = brier_parts(p_k, y_k)` — 确实未传递 `n_bins`
   - 若修改 `N_BINS=50`，ECE 用 50 bin（`ece()` 正确接受 `n_bins`），Brier 仍用 10 bin

2. **是否稻草人论证**：❌ 否。反方准确引用了代码，未歪曲正方设计。

3. **是否误解前提**：❌ 否。反方正确理解了 `brier_parts_toplabel`/`brier_parts_ovr` 的 `n_bins` 参数意图（应为传递给底层）。

4. **攻击逻辑是否自洽**：✅ 自洽。代码 bug → A1 缓解失效 → ECE/Brier 分箱不一致，推理链完整。

5. **严重程度是否夸大**：❌ 未夸大。这是一个真实的代码 bug，使 A1 缓解方案完全失效，致命性成立。

**裁决**：**成立（致命）**

**修补方案**：
```python
# calibration.py L586 — 修改签名
def brier_parts(probs, labels, n_bins: int = 10):
    """Brier Score Murphy分解（精确恒等式）..."""
    ...
    bins = np.linspace(0, 1, n_bins + 1)  # L603 — 使用参数
    ...
    for i in range(n_bins):  # L609 — 使用参数
        ...

# E3 L181 — 传递 n_bins
def brier_parts_toplabel(probs, labels, n_bins=N_BINS):
    ...
    return brier_parts(max_p, correct, n_bins=n_bins)  # 传递

# E3 L199 — 传递 n_bins
def brier_parts_ovr(probs, labels, n_bins=N_BINS):
    ...
    b, r, s, u = brier_parts(p_k, y_k, n_bins=n_bins)  # 传递
```

---

### F2：Murphy 恒等式按构造成立（tautological）——非独立验证

**反方主张**：`brier_total = reliability - resolution + uncertainty` 按构造成立（tautological），非独立验证的数学性质；主终点 `delta_reliability` 来自该构造量而非 raw Brier；如果分箱离散化误差大，"Reliability 改善"可能不代表真实校准改善。

**逐维审查**：

1. **反例是否成立**：⚠️ 部分成立。
   - **恒等式 tautological**：✅ 属实。`brier_total` 确实定义为 `reliability - resolution + uncertainty`（L625），按构造成立。
   - **但代码已显式文档化**：`calibration.py` L590-593 docstring 明确声明：
     > "注意：用 raw mean((p-y)^2) 时该恒等式仅在分箱内概率恒定时精确成立；此处返回的 brier_total 取 REL - RES + UNC（按构造精确成立），raw Brier 由 brier_raw(probs, labels) 单独计算。"
   - **主终点来自构造量**：❌ **不成立**。主终点 `delta_reliability = rel_raw - rel_cal`（E3 L328）是 **reliability 分量的差值**，不是 `brier_total` 的差值。`reliability` 分量由 `reliability += n_bin / n * (avg_prob - avg_label) ** 2`（L622）计算，是 **经验量**（bin 内预测概率与经验频率的加权平方差），不是构造恒等式的产物。
   - **反例中"reliability ≈ 0 暗示完美校准"**：⚠️ 部分成立。反方构造的概率全集中在 [0.45, 0.55] 的反例中，reliability ≈ 0 确实可能发生，但这反映的是 **分箱粒度不足**（S10/F1 的问题），而非 Murphy 恒等式 tautological 的问题。反方将"分箱粒度不足"包装为"恒等式 tautological"，存在 **因果归因错误**。

2. **是否稻草人论证**：⚠️ 部分。反方将"恒等式 tautological"（正确）推导到"主终点来自构造量"（错误——主终点是 reliability 分量差值，是经验量），存在 **偷换概念**：从 `brier_total` 的构造性跳到 `reliability` 的构造性，但 `reliability` 是独立计算的经验量。

3. **是否误解前提**：⚠️ 部分。反方忽略了代码 docstring 的显式声明（L590-593 已说明 brier_total 是构造量、brier_raw 是经验量），也忽略了 E3 已计算 `brier_raw_before/after`（L303-306）的事实。

4. **攻击逻辑是否自洽**：⚠️ 部分自洽。推理链"恒等式 tautological → brier_total 非独立验证 → 需用 raw Brier 交叉验证"本身自洽，但中间环节"主终点来自构造量"断裂——主终点是 reliability 分量，不是 brier_total。

5. **严重程度是否夸大**：✅ **严重夸大**。
   - 恒等式 tautological 是 **已知的、已文档化的** 设计选择，不是隐藏缺陷
   - 主终点 `delta_reliability` 是 reliability 分量差值（经验量），不受恒等式 tautological 影响
   - 真正的问题是 `brier_raw` 未进 summary（即 M5），这是轻微的报告完整性问题
   - "致命"标注将一个已文档化的设计选择 + 一个轻微报告缺失包装为致命缺陷

**裁决**：**部分成立（致命→轻微）**

**有效部分**：`brier_raw` 已计算但未在 summary 中报告 `brier_total` vs `brier_raw` 偏差（与 M5 重叠）。

**无效部分**：主终点 `delta_reliability` 不受恒等式 tautological 影响——reliability 分量是经验计算的校准质量度量。

**修补建议**（与 M5 合并）：在 CSV3 summary 中增加 `brier_total` vs `brier_raw` 偏差报告，作为分箱粒度诊断。

---

### F3：H1 未验证即用作主终点理论依据——循环推理

**反方主张**：主终点选择基于 H1（"TS 只影响 Reliability"），H1 验证基于实验数据（`h1_ratio`），实验数据来自主终点计算，构成循环推理；诊断阈值 0.1/0.3 无理论依据且无 fallback 机制。

**逐维审查**：

1. **反例是否成立**：⚠️ 部分成立。
   - **阈值无理论依据**：✅ 属实。0.1 和 0.3 确实是经验阈值，无严格理论推导。
   - **无 fallback 机制**：✅ 属实。`h1_ratio > 0.3` 时仅打印建议，主终点仍用 `delta_reliability`。
   - **循环推理**：❌ **不成立**。反方的循环推理结构描述有误：
     - **主终点选择的理论先验**是 H1 在 **精确分箱极限** 下的严格成立——这是一个 **数学定理**（TS 是单调变换，保持 argmax；精确分箱下每个概率自成 bin，TS 不改变 bin 分配，因此 Resolution 不变），不是未验证的假设
     - **10-bin 近似**是已知的近似，docstring L25-26 明确声明"10 等宽分箱下**近似成立**"
     - **`h1_ratio` 诊断**是 post-hoc 验证近似质量，不是主终点选择的依据
     - 推理链：定理（精确分箱 H1 严格成立）→ 近似（10-bin H1 近似成立）→ 诊断（h1_ratio 验证近似）→ 主终点（delta_reliability），**不是循环**，是"定理→近似→验证"的标准科学推理

2. **是否稻草人论证**：⚠️ 部分。反方将"H1 在精确分箱极限是定理"降格为"H1 是未验证的假设"，歪曲了 H1 的理论地位。E3 docstring L23-26 明确区分了"精确分箱极限下**严格成立**"和"10 等宽分箱下**近似成立**"。

3. **是否误解前提**：⚠️ 部分。反方忽略了 H1 的理论先验（精确分箱定理），将主终点选择归因于"未验证的 H1"，而实际上主终点选择有理论先验支撑。

4. **攻击逻辑是否自洽**：⚠️ 部分自洽。"阈值无理论依据→无 fallback"的推理自洽，但"循环推理"的推理链断裂——主终点选择不依赖实验数据，依赖理论定理。

5. **严重程度是否夸大**：✅ **夸大**。
   - "循环推理"标签过重——主终点选择有理论先验（精确分箱定理），不是循环
   - 真正的问题是：(a) 阈值无理论依据，(b) 无 fallback 机制——这两个是 **严重** 问题但非 **致命**
   - 即使 H1 在 10-bin 下不严格成立，主终点 `delta_reliability` 仍有意义（它度量 reliability 分量的改善），只是可能混合了部分 Resolution 变化

**裁决**：**部分成立（致命→严重）**

**有效部分**：(a) 诊断阈值 0.1/0.3 无理论依据，(b) 无 fallback 到 `delta_brier_raw` 的机制，(c) 均值比可能掩盖逐 checkpoint 异质性。

**无效部分**："循环推理"标签——主终点选择有理论先验（精确分箱极限下 H1 是定理），10-bin 诊断是 post-hoc 验证近似质量，不是循环依赖。

**修补建议**：
1. 将 H1 诊断改为逐 checkpoint 报告（而非仅均值比），暴露异质性
2. 预设 fallback：若 >30% checkpoint 的 `|ΔRES|/|ΔREL| > 0.3`，自动切换主终点为 `delta_brier_raw` 并在报告中声明
3. 阈值可参考 Bröcker 2009 的分箱敏感性分析文献给出理论依据

---

### F4：60 checkpoint 共享测试集——paired t-test 独立性假设违反

**反方主张**：同一 pair 的 10 个 checkpoint 共享测试集，配对差值正相关，paired t-test p 值偏小；建议的 pair-level 聚合（n=6）未实现且样本太少。

**逐维审查**：

1. **反例是否成立**：⚠️ 部分成立。
   - **独立性违反**：✅ 属实。同一 pair 的 checkpoint 共享测试集，配对差值确实有正相关。
   - **pair-level 聚合未实现**：✅ 属实。`summarize_and_write` 函数（L710-944）仅对 60 个 checkpoint 做 paired t-test，无 pair-level 聚合。
   - **n=6 太少**：✅ 属实。n=6 时 t 临界值 ≈ 2.571（df=5），功效远低于 n=60。
   - **ρ=0.3 估计**：⚠️ **推测性**。反方声称"保守估计 ρ=0.3"，但：
     - 不同 seed → 不同模型参数 → 不同预测 → ΔREL 取决于模型和测试集的交互
     - 不同 arch（inceptiontime vs resnet1d）→ 架构差异大 → 预测差异更大 → 相关性更低
     - 共享测试集引入的相关性 **取决于模型预测的相似度**，不同 seed/arch 的模型预测差异显著，ρ=0.3 可能高估
     - 反方未提供任何数据支撑 ρ=0.3 的合理性
   - **n_eff ≈ 16 的量级估计**：⚠️ 基于 ρ=0.3 推测，若 ρ=0.1 则 n_eff ≈ 35，若 ρ=0.05 则 n_eff ≈ 48——对 ρ 极其敏感

2. **是否稻草人论证**：❌ 否。反方准确描述了数据结构（6 pairs × 2 archs × 5 seeds）和共享测试集的事实。

3. **是否误解前提**：⚠️ 部分。反方忽略了"不同 seed 独立训练"的实际效果——虽然共享测试集，但不同 seed 产生的模型在测试集上的预测不同，改善值 ΔREL 的相关性 **低于** 反方假设。反方的"反驳的反反驳"第 1 点（"不同 seed 独立训练不意味着测试集上的改善值独立"）方向正确但程度被夸大。

4. **攻击逻辑是否自洽**：✅ 自洽。共享测试集 → 正相关 → n_eff < 60 → p 值偏小，推理链完整。

5. **严重程度是否夸大**：✅ **部分夸大**。
   - 独立性违反是真实的统计问题，值得重视
   - 但 ρ=0.3 是推测，实际相关性可能更低（不同 seed/arch 的模型差异）
   - paired t-test 作为 **第一层分析** 仍合理，需补充 cluster bootstrap 作为 **敏感性分析**
   - "致命"标注意味着主终点的统计推断完全不可信，但实际上即使 n_eff=35（ρ=0.1），大多数效应仍显著
   - 应为 **严重**：需补充 cluster bootstrap，但现有分析不至完全无效

**裁决**：**部分成立（致命→严重）**

**有效部分**：(a) 独立性假设违反，(b) pair-level 聚合未实现，(c) 需 cluster bootstrap 或混合效应模型。

**无效部分**：ρ=0.3 的量级估计是推测性的，"p 值低估 ~2 倍"缺乏数据支撑；不同 seed/arch 的模型差异使实际相关性可能低于假设。

**修补建议**：
```python
# 在 summarize_and_write 中增加 cluster bootstrap（cluster=pair）
def cluster_bootstrap_paired(before, after, clusters, n_boot=10000, rng_seed=42):
    """Cluster bootstrap: 重采样 cluster（pair）而非个体"""
    rng = np.random.default_rng(rng_seed)
    unique_clusters = np.unique(clusters)
    n_clusters = len(unique_clusters)
    boot_means = np.empty(n_boot)
    for b in range(n_boot):
        chosen = rng.choice(unique_clusters, size=n_clusters, replace=True)
        idx = np.concatenate([np.where(clusters == c)[0] for c in chosen])
        diff = np.asarray(before)[idx] - np.asarray(after)[idx]
        boot_means[b] = np.mean(diff)
    return np.percentile(boot_means, [2.5, 97.5])

# 同时报告 pair-level 聚合（6 个 pair 的均值±std）作为保守分析
```

---

## 2. 严重攻击裁决 (Serious)

### S1：Cohen's d 的 95% CI 用 percentile 而非 BCa

**反方主张**：E3 的 `cohen_d_paired` 用 percentile 方法计算 CI，但项目 F2 修复明确要求 BCa（`calibration.py` L341），且 `_bca_interval` 已实现但未被 E3 使用。

**逐维审查**：

1. **反例是否成立**：✅ 成立。E3 L400 确实用 `np.percentile(boot_ds, [2.5, 97.5])`，`calibration.py` L337-384 有完整 `_bca_interval` 实现，L341 注释明确要求 BCa。

2. **是否稻草人论证**：❌ 否。反方准确引用了代码和项目标准。

3. **是否误解前提**：❌ 否。

4. **攻击逻辑是否自洽**：✅ 自洽。项目标准要求 BCa → E3 未使用 → CI 方法不一致 → 与 ECE 主终点的 CI 方法不统一。

5. **严重程度是否夸大**：❌ 未夸大。CI 方法不一致是真实的统计方法问题，percentile CI 对 Cohen's d 有已知的 undercoverage。

**裁决**：**成立（严重）**

**修补方案**：在 `cohen_d_paired` 中复用 `_bca_interval`：
```python
from src.utils.calibration import _bca_interval

# 替换 L400 的 percentile 方法
# 需计算 jackknife 统计量用于 BCa 加速度项
jackknife_ds = np.empty(n)
for i in range(n):
    mask = np.ones(n, dtype=bool)
    mask[i] = False
    d_jk = diff[mask]
    s_jk = np.std(d_jk, ddof=1)
    jackknife_ds[i] = np.mean(d_jk) / s_jk if s_jk > 1e-12 else 0.0

ci_lo, ci_hi = _bca_interval(cohen_d, boot_ds, jackknife_ds, 0.95)
```

---

### S2：DCR/NCV 用 `np.zeros(n)` 伪造配对——语义混乱

**反方主张**：DCR/NCV 已是差值，本质是 one-sample 问题，但代码用 `cohen_d_paired(np.zeros(n), dcr_ood, "increase")` 伪造配对，语义混乱。

**逐维审查**：

1. **反例是否成立**：⚠️ 部分成立。
   - **数学正确性**：✅ 完全正确。`diff = after - before = dcr_ood - 0 = dcr_ood`，`ttest_rel(zeros, x)` 等价于 `ttest_1samp(x, 0)`，bootstrap 重采样 `diff[idx] = dcr_ood[idx]` 也正确。
   - **语义混乱**：⚠️ 属实但程度有限。"before=0" 的语义是"DCR 的基线为零改善"，这在 DCR 定义（`cost_raw - cost_cal`，零=无改善）下是合理的。

2. **是否稻草人论证**：⚠️ 部分。反方将"代码可读性"问题包装为"语义混乱"的严重攻击，但数学完全正确。

3. **是否误解前提**：❌ 否。反方正确理解了数学等价性。

4. **攻击逻辑是否自洽**：✅ 自洽。

5. **严重程度是否夸大**：✅ **夸大**。数学正确，仅代码可读性问题，应为 **轻微** 而非 **严重**。

**裁决**：**部分成立（严重→轻微）**

**修补建议**：增加显式 one-sample 接口（代码质量改进，非紧急）：
```python
def cohen_d_one_sample(values, rng_seed=RNG_SEED):
    """One-sample Cohen's d + CI + t-test (H0: mean=0)"""
    from scipy.stats import ttest_1samp
    # ... 直接用 ttest_1samp(values, 0)
```

---

### S3：NCV 的 `N_total=N×K` 假设 K 个 OvR 决策独立

**反方主张**：softmax 概率和为 1，K 个 OvR 决策完全相关，NCV 量级被 K 倍稀释。

**逐维审查**：

1. **反例是否成立**：⚠️ 部分成立。
   - **非独立性**：✅ 属实。softmax 和为 1，K 个决策不独立。
   - **脚本已主动披露**：✅ E3 docstring L46-48 明确声明此假设及局限。
   - **`ncv_per_sample` 已计算**：✅ E3 L274 计算并返回 `ncv_per_sample`，L353 写入 dcr_row。
   - **K 倍稀释**：⚠️ 这是 **归一化选择**，不是 bug。R5 方案明确定义 `N_total = N_samples × N_classes`（L298-311），代码遵循规范。

2. **是否稻草人论证**：⚠️ 部分。反方将"归一化定义选择"（R5 规范明确）包装为"量级错误"。

3. **是否误解前提**：⚠️ 部分。反方忽略了 R5 方案对 NCV 的明确定义和脚本已提供的 `ncv_per_sample` 敏感性。

4. **攻击逻辑是否自洽**：✅ 自洽。

5. **严重程度是否夸大**：✅ **夸大**。代码遵循 R5 规范，已计算敏感性，已主动披露假设。应为 **轻微**。

**裁决**：**部分成立（严重→轻微）**

**修补建议**：在 summary 中更突出地报告 `ncv_per_sample`（已在 dcr_row 中，仅需在 CSV4 summary 增加一行）。

---

### S4：DCR `abstain_cost=0.5` 敏感性分析未实现

**反方主张**：docstring 声称报告 0.3/0.7 敏感性，但代码只计算 0.5；"DCR 单调"声称未验证。

**逐维审查**：

1. **反例是否成立**：✅ 成立。E3 L149 `ABSTAIN_COST = 0.5`，`dcr_multiclass` 只接受单一 `abstain_cost`，无循环计算 0.3/0.7。

2. **是否稻草人论证**：❌ 否。反方准确引用了 docstring 的承诺和代码的实现缺失。

3. **是否误解前提**：❌ 否。

4. **攻击逻辑是否自洽**：✅ 自洽。docstring 承诺 → 代码未实现 → 声称未验证。

5. **严重程度是否夸大**：❌ 未夸大。docstring 明确承诺但未实现，是真实的完整性缺失。

**裁决**：**成立（严重）**

**修补方案**：
```python
# 在 compute_all_metrics_for_split 中增加敏感性循环
ABSTAIN_COSTS = [0.3, 0.5, 0.7]
for ac in ABSTAIN_COSTS:
    dcr_ac, _, _ = dcr_multiclass(probs_raw, probs_cal, labels, abstain_cost=ac)
    metrics[f'dcr_cost_{ac}'] = dcr_ac
```

---

### S5：H1 诊断阈值无理论依据且无 fallback 机制

**反方主张**：阈值 0.1/0.3 无理论依据，"部分成立"时主终点仍用 `delta_reliability`，无切换机制；均值比掩盖异质性。

**逐维审查**：

1. **反例是否成立**：✅ 成立。
   - 阈值无理论依据：✅
   - 无 fallback：✅
   - 均值比掩盖异质性：✅ 反例构造（30 个 ratio=0.05 + 30 个 ratio=20 → 均值 ratio=1.0）成立

2. **是否稻草人论证**：❌ 否。

3. **是否误解前提**：❌ 否。

4. **攻击逻辑是否自洽**：✅ 自洽。

5. **严重程度是否夸大**：❌ 未夸大。与 F3 的有效部分重叠，是真实的诊断设计缺陷。

**裁决**：**部分成立（严重）**（与 F3 有效部分重叠）

**修补建议**：见 F3 修补方案——逐 checkpoint H1 诊断 + 预设 fallback。

---

### S6：paired t-test 未检查正态性假设

**反方主张**：校准改善分布常右偏，t-test 可能过度拒绝，未检查正态性。

**逐维审查**：

1. **反例是否成立**：⚠️ 部分成立。
   - **未检查正态性**：✅ 属实。代码无 Shapiro-Wilk 检验。
   - **校准改善常右偏**：⚠️ **推测性**。反方声称"多数 checkpoint 改善小+少数大改善=右偏"，但未提供本实验数据的偏度/峰度证据。
   - **n=60 时 CLT**：✅ 提供合理稳健性。t-test 在 n=60 时对非正态性有较好的稳健性（CLT 使均值近似正态）。
   - **反例中 Wilcoxon p=0.06 vs t-test p=0.007**：⚠️ 构造极端（55 个 0.001 + 5 个 0.05），实际数据分布可能没那么极端。

2. **是否稻草人论证**：⚠️ 部分。将推测性的分布形状（"常右偏"）作为确定事实。

3. **是否误解前提**：❌ 否。

4. **攻击逻辑是否自洽**：✅ 自洽。

5. **严重程度是否夸大**：✅ **夸大**。n=60 时 CLT 提供合理保护，右偏声称无数据支撑。应为 **轻微**。

**裁决**：**部分成立（严重→轻微）**

**修补建议**：增加 Shapiro-Wilk 正态性检验作为诊断（非阻塞），非正态时补充 Wilcoxon signed-rank test 结果。

---

### S7：ECE 与 Brier 分箱一致性仅靠巧合维持

**反方主张**：ECE 的 `n_bins` 可变，Brier 硬编码 10 bin，修改 `N_BINS` 会静默破坏一致性。

**逐维审查**：

1. **反例是否成立**：✅ 成立。这是 F1 的直接后果——`ece()` 接受 `n_bins`，`brier_parts()` 不接受。

2. **是否稻草人论证**：❌ 否。

3. **是否误解前提**：❌ 否。

4. **攻击逻辑是否自洽**：✅ 自洽。

5. **严重程度是否夸大**：❌ 未夸大。分箱一致性是 ECE-Brier 对比的语义基础。

**裁决**：**成立（严重）**（F1 的直接后果，修复 F1 即修复 S7）

---

### S8：`brier_parts_ovr` 平均 per-class 分解——语义与 top-label 不同

**反方主张**：per-class OvR reliability 与 top-label reliability 语义不同，未文档化。

**逐维审查**：

1. **反例是否成立**：⚠️ 部分成立。
   - **语义不同**：✅ 属实。per-class OvR 度量"每个二分类问题的校准"，top-label 度量"最大概率的校准"。
   - **未文档化**：⚠️ 部分属实。E3 L188-189 docstring 说明"利用全部概率信息，作为 top-label 的敏感性分析"，但未详细说明语义差异。
   - **代码已同时报告两种**：✅ top-label 为主终点，OvR 为敏感性（L334, L817），标注清晰。

2. **是否稻草人论证**：⚠️ 部分。反方忽略代码已标注"敏感性分析"的事实。

3. **是否误解前提**：❌ 否。

4. **攻击逻辑是否自洽**：✅ 自洽。

5. **严重程度是否夸大**：✅ **夸大**。代码已同时报告两种度量并标注敏感性，仅需补充文档说明。应为 **轻微**。

**裁决**：**部分成立（严重→轻微）**

**修补建议**：在 docstring 和 CSV 注释中增加 per-class OvR 与 top-label reliability 的语义差异说明。

---

### S9：T 在 source-cal 拟合，主分析在 OOD——无 sanity check

**反方主张**：T 在 source-cal 拟合但主分析在 OOD，未报告 source-cal reliability 改善作为 sanity check。

**逐维审查**：

1. **反例是否成立**：⚠️ 部分成立。
   - **T 在 source-cal 拟合**：✅ 属实（E3 L604-606）。
   - **主分析在 OOD**：✅ 属实（E3 L667-672）。
   - **无 source-cal sanity check**：⚠️ 部分属实。代码计算了 ID 指标（L671, `id_metrics`）并在 summary 中报告为"参考"（L836），但未做 ID vs OOD 的 **显式对比分析**。
   - **ID = source-test**：ID 指标在 source-test 上计算，与 source-cal 同分布，可作为 sanity check 的近似——但代码未显式对比 ID 改善 vs OOD 改善。

2. **是否稻草人论证**：⚠️ 部分。反方说"无 sanity check"，但 ID 指标已计算并报告，只是未做显式对比。

3. **是否误解前提**：⚠️ 部分。反方忽略了 ID 指标已作为参考输出。

4. **攻击逻辑是否自洽**：✅ 自洽。

5. **严重程度是否夸大**：❌ 基本未夸大。ID 指标虽已计算，但未做 ID vs OOD 对比分析，审稿人确实难以判断迁移效果。

**裁决**：**部分成立（严重）**

**修补建议**：在 summary 中增加 ID vs OOD 改善的显式对比：
```python
# 在 CSV3 中增加
id_improvement = stats_rel_id['mean_diff']
ood_improvement = stats_rel_ood['mean_diff']
transfer_ratio = ood_improvement / id_improvement if abs(id_improvement) > 1e-12 else float('nan')
w.writerow(["# Sanity check: ID vs OOD 改善对比"])
w.writerow(["id_reliability_improvement", f"{id_improvement:+.6f}"])
w.writerow(["ood_reliability_improvement", f"{ood_improvement:+.6f}"])
w.writerow(["transfer_ratio (OOD/ID)", f"{transfer_ratio:.4f}"])
```

---

### S10：Brier 分箱 [0,1] 但 top-label max-prob ∈ [1/K, 1]——20% bin 浪费

**反方主张**：K=5 时 max_p ∈ [0.2, 1.0]，bin 0 和 bin 1 永远为空，20% 分辨率浪费。

**逐维审查**：

1. **反例是否成立**：✅ 成立。K=5 时 max_p ≥ 0.2，bin [0, 0.1) 和 [0.1, 0.2) 确实为空。

2. **是否稻草人论证**：❌ 否。

3. **是否误解前提**：⚠️ 部分。反方未提及 ECE 也有同样问题（ECE 也用 [0, 1] 分箱），且 8 个有效 bin 仍可提供合理的 reliability 估计。

4. **攻击逻辑是否自洽**：✅ 自洽。

5. **严重程度是否夸大**：✅ **夸大**。8 vs 10 有效 bin 的影响有限（20% 分辨率损失不等于 20% 估计质量损失），且 ECE 有同样问题。应为 **轻微**。

**裁决**：**部分成立（严重→轻微）**

**修补建议**：可选改用自适应分箱 `np.linspace(1/K, 1.0, n_bins + 1)`，但需同时修改 ECE 以保持一致性（依赖 F1 修复）。

---

## 3. 轻微攻击裁决 (Minor)

### M1：`RNG_SEED=42` 固定 bootstrap 种子——CI 确定性

**裁决**：**部分成立（轻微）**。单种子是可复现性标准做法，多种子稳定性检查有价值但非必须。

---

### M2：n=1 退化情况未显式警告

**裁决**：**成立（轻微）**。n=1 时 `std_diff=0`, `cohen_d=0`，无警告。建议增加 `n < 2` 警告。

---

### M3：BH FDR 仅校正 2 个 p 值——近似 Bonferroni

**裁决**：**部分成立（轻微）**。2 个检验的 BH FDR 确实 ≈ Bonferroni（`adj_p ≈ 2p`），但 FDR 校正仍有效，只是与 FWER 区别不大。建议在报告中透明声明。

---

### M4：CSV 前 5 行是注释——非标准格式

**裁决**：**成立（轻微）**。`pandas.read_csv` 需 `skiprows=5` 或 `comment='#'`。建议改用 JSON 或在文档中说明读取方式。

---

### M5：`brier_raw` 已计算但未进入汇总统计

**裁决**：**成立（轻微）**。`brier_raw_before/after` 在 L303-306 计算，写入 CSV1（L735），但未在 CSV3 summary 中报告。`brier_total` vs `brier_raw` 偏差是分箱粒度的关键诊断。建议在 summary 中增加。

**注**：此攻击与 F2 的有效部分重叠。F2 被降级为轻微后，两者实质相同。

---

### M6：T 分布未汇总

**裁决**：**成立（轻微）**。T 打印到控制台（L703）但未在 summary 中汇总均值/std/范围。T 分布是判断 TS 效果幅度的关键信息。建议在 summary 中增加 T 的统计量。

---

### M7：NCV 用严格 `>tau`——概率恰好=0.5 时弃权

**裁决**：**部分成立（轻微）**。连续概率下零测度事件，但温度缩放后可能离散化。K=2 时 1/K=0.5=τ 全弃权是理论边界（当前实验 K=4/5 不触发）。建议文档化或改用 `>=`。

---

## 4. 全维度审查总结

### 4.1 反方攻击的整体质量评估

**优点**：
- 21 个攻击点均有代码行号引用，证据扎实
- 未发现完全的稻草人论证（无歪曲正方主张至荒谬程度的情况）
- 未发现完全误解正方意图的情况
- F1 发现了真实的代码 bug（`brier_parts` 静默丢弃 `n_bins`）
- S1 发现了真实的 CI 方法不一致
- S4 发现了 docstring 承诺未实现

**不足**：
- **4 个致命攻击中 3 个严重程度被夸大**（F2/F3/F4）
- F2 存在 **偷换概念**：从 `brier_total` 的构造性跳到 `reliability` 的构造性，但 reliability 是经验量
- F3 存在 **理论地位降格**：将 H1 在精确分箱极限的定理地位降格为"未验证的假设"
- F4 的 ρ=0.3 估计是 **推测性的**，缺乏数据支撑
- 多个严重攻击（S2/S3/S6/S8/S10）的严重程度被夸大，应为轻微

### 4.2 对正方方案的影响评估

**必须修复（维持实验可信度）**：
1. **F1/S7**：`brier_parts` 添加 `n_bins` 参数——真实代码 bug，影响 A1 缓解方案
2. **S1**：Cohen's d CI 改用 BCa——违反项目 own 标准
3. **S4**：实现 abstain_cost 敏感性分析——docstring 承诺未实现
4. **F3/S5**：H1 诊断增加逐 checkpoint 报告 + fallback 机制
5. **F4**：增加 cluster bootstrap（cluster=pair）作为敏感性分析
6. **S9**：增加 ID vs OOD 改善对比作为 sanity check

**建议修复（提升报告完整性）**：
7. **M5/F2**：在 summary 中报告 `brier_total` vs `brier_raw` 偏差
8. **M6**：在 summary 中汇总 T 分布统计量
9. **S3**：更突出报告 `ncv_per_sample`
10. **M4**：CSV 格式标准化或文档化读取方式

**可选改进（代码质量）**：
11. **S2**：增加显式 one-sample Cohen's d 接口
12. **S6**：增加 Shapiro-Wilk 正态性检验
13. **S10**：自适应分箱 [1/K, 1]（依赖 F1 修复）
14. **S8**：文档化 per-class OvR 与 top-label 语义差异

### 4.3 对反方"建议"的回应

反方建议："在修复 F1-F4 之前，E3 的主终点（Brier reliability 改善）不应被用于论文 C1 核心声称。"

**元审查裁决**：**部分驳回**。
- F1 确实需修复（真实 bug），但修复简单（0.5 天），修复后不影响主终点的理论依据
- F2 不影响主终点的有效性（reliability 是经验量），仅需补充 raw Brier 诊断报告
- F3 的理论先验（精确分箱定理）成立，主终点选择有理论依据，仅需补充 fallback 机制
- F4 需补充 cluster bootstrap，但现有 paired t-test 作为第一层分析仍合理

**修正后的建议**：修复 F1/S1/S4 后，E3 的主终点数值可信；修复 F3/F4 后，E3 的统计推断可信。F2 不阻塞主终点使用。建议修复优先级：F1 > S1 > S4 > F3/S5 > F4 > S9 > M5/M6。

---

## 5. 裁决结论

### 统计汇总

- **完全成立的攻击**：8 个（F1, S1, S4, S7, M2, M4, M5, M6）
- **部分成立的攻击**：13 个（多数因严重程度夸大而降级）
- **被驳回的攻击**：0 个
- **严重程度被夸大的攻击**：8 个（F2, F3, F4, S2, S3, S6, S8, S10）
- **致命攻击实际维持**：1 个（F1）
- **致命攻击降级**：3 个（F2→轻微, F3→严重, F4→严重）

### 对抗实质性评估

**反方攻击整体实质性**：✅ 较高。21 个攻击点均有代码证据，未发现稻草人论证或完全误解正方意图的情况。反方发现了 1 个真实代码 bug（F1）和多个真实的完整性缺失（S1/S4/S9/M5/M6）。

**反方攻击的主要缺陷**：⚠️ 严重程度系统性夸大。4 个致命攻击中 3 个被夸大：
- F2 将"已文档化的设计选择 + 轻微报告缺失"包装为致命
- F3 将"有理论先验的近似 + 阈值/fallback 缺失"包装为循环推理
- F4 将推测性的 ρ=0.3 估计作为致命依据

**对正方的建议**：
1. **立即修复** F1（`brier_parts` 添加 `n_bins`）——这是唯一真正致命的攻击
2. **尽快修复** S1（BCa CI）、S4（abstain_cost 敏感性）、F3/S5（H1 fallback）、F4（cluster bootstrap）
3. **补充报告** S9（ID vs OOD 对比）、M5（brier_raw 诊断）、M6（T 分布汇总）
4. **修复后** E3 的主终点（Brier reliability 改善）的数值和统计推断均可信，可用于论文 C1 核心声称

**最终裁决**：反方攻击有效但严重程度系统性偏高。**F1 是唯一真正致命的攻击**（真实代码 bug），F2/F3/F4 应降级。正方修复 F1 + S1 + S4 + F3/F5 + F4 + S9 后，E3 实验的可信度可恢复。F2 不阻塞主终点使用——reliability 分量是经验量，不受 Murphy 恒等式 tautological 影响。
