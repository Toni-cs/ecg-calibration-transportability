# E4 反方攻击审查裁决报告（反反方）

> **反反方审查代理-E4 交付**。本报告对反方挑刺代理在 `adversarial_r1_attack_e4.md` 中提出的 24 个攻击点（F1-F2 致命、S1-S10 严重、M1-M12 轻微）逐条进行元审查，评估每个攻击是否为稻草人论证、是否误解正方意图、反例是否真的成立、攻击逻辑是否自洽。
> **审查日期**：2026-09-09
> **审查对象**：`docs/adversarial_r1_attack_e4.md`（反方攻击报告）vs `scripts/run_e4_temperature_analysis.py`（975 行）+ `docs/Q2_UPGRADE_PROPOSAL_R5.md` E4 章节
> **审查代理**：反反方审查代理-E4（GLM-5.2）
> **审查原则**：既非正方帮手，也非反方帮手。以代码事实为唯一裁判依据。

---

## 0. 裁决概述

### 裁决统计

| 裁决类别 | 数量 | 编号 |
|----------|------|------|
| **成立** | 13 | F1, S2, S3, S8, M1, M3, M4, M5, M6, M7, M8, M9, M10 |
| **部分成立** | 9 | F2, S1, S4, S5, S6, S7, S9, S10, M2 |
| **驳回** | 2 | M11, M12（部分驳回） |
| **合计** | 24 | — |

### 严重程度修正统计

| 反方标注 | 实际裁决 | 数量 | 说明 |
|----------|----------|------|------|
| 致命→致命 | 1 | F1 | 核心比较确实缺失 |
| 致命→严重 | 1 | F2 | 字段语义滥用真实但不影响科学推断 |
| 严重→严重 | 2 | S2, S3 | 技术缺陷确认 |
| 严重→中等 | 7 | S1, S4, S5, S6, S7, S9, S10 | 探索性定位下被夸大 |
| 严重→轻微 | 1 | S8 | 文档笔误 |
| 轻微→轻微 | 11 | M1-M10, M12 | 基本确认 |
| 轻微→驳回 | 1 | M11 | 反例不成立 |

### 整体评估

反方攻击在**代码事实核查**层面质量较高——24 个攻击点中 22 个的事实观察基本准确（代码确实如此行）。但在**严重程度判定**和**科学影响推断**层面存在系统性夸大倾向：

1. **探索性定位被忽视**：E4 在 R5 方案中明确为探索性评估（B1: "不进入主检验"），反方多处用 confirmatory 标准要求探索性分析，导致 7 个"严重"攻击实际应为"中等"。
2. **一个稻草人论证**：S1 将 M3 的"T 对分布漂移的敏感性"重解读为"test-time 部署稳健性"，但 M3 的原文和子条目明确说的是 cal-time 语义。
3. **F1 是真正的核心发现**：全局 binned-T Brier reliability 确实未计算，这是反方最有价值的攻击，修复简单（2 行代码）。
4. **F2 被过度定级**：DIST_STATS 行字段语义滥用是真实的代码坏味，但不影响任何科学推断（纯描述性汇总行），"致命"定级不成立。

---

## 1. 致命攻击裁决

### F1：M2 核心比较缺失——全局 binned-T Brier reliability 从未计算

**裁决：成立（致命确认）**

**事实核查**：

反方称脚本计算了 `id_probs_binned`（第 509 行）但从未调用 `brier_reliability_top(id_probs_binned, id_labels)` 计算全局 binned-T Brier reliability。经逐行核查确认：

- `dist_record`（第 488-503 行）：有 `id_rel_global_T`、`ood_rel_global_T`，**无** `id_rel_binned_T`（全局）
- `binned_records`（第 540-564 行）：有 per-bin `id_rel_binned_T`，但这是**箱内子集**的 Brier reliability，非全局
- 控制台汇总（第 946-955 行）：计算 `mean(id_delta_binned_vs_global)`——per-bin Δrel 的等权均值

**数学论证核查**：

反方的数学论证正确。Brier reliability 的 Murphy 分解为 `rel = Σ_j (n_j/n) · (avg_prob_j - avg_label_j)²`，其中 j 是 max-prob 的 10 等宽分箱。per-bin rel 用 `n_{b,j}/n_b` 加权，全局 rel 用 `n_{b,j}/n` 加权。当各 bin 样本量不均时（OOD 下极常见），per-bin 等权均值与全局加权差异不仅数值不同，**符号可相反**。

反方构造的反例（bin 样本量 [800,800,200,100,100]，per-bin 均值 -0.002 vs 全局 +0.002）数学上成立。

**是否稻草人**：否。反方攻击的是 M2 的字面主张（"binned-T 的 Brier reliability 优于 global-T"），未歪曲。

**是否误解正方意图**：否。脚本确实计算了 `id_probs_binned` 但未计算其全局 Brier reliability，这是代码事实。

**反例是否成立**：是。per-bin 均值 ≠ 全局差异的数学论证严格正确。

**严重程度评估**：**致命确认**。M2 是 E4 三大核心主张之一，其核心比较在代码中缺失。控制台汇总的 `mean Δrel` 是误导性代理指标，可能得出与全局比较相反的结论。

**修补方案**（反方建议正确，补充完整实现）：

在 `process_one` 函数中，第 510 行之后添加：
```python
# 全局 binned-T Brier reliability（F1 修复）
id_rel_binned_global = brier_reliability_top(id_probs_binned, id_labels)
ood_rel_binned_global = brier_reliability_top(ood_probs_binned, ood_labels)
```

并在 `dist_record`（第 488-503 行）中添加：
```python
"id_rel_binned_T": id_rel_binned_global,
"ood_rel_binned_T": ood_rel_binned_global,
"id_delta_binned_vs_global": id_rel_binned_global - id_rel_global,
"ood_delta_binned_vs_global": ood_rel_binned_global - ood_rel_global,
```

同时在 `write_dist_csv` 的 `fieldnames` 中添加对应列。

控制台汇总（第 946-955 行）改为报告全局差异而非 per-bin 均值。

**工时**：0.5h（反方估计准确）

---

### F2：summarize_distribution 的 DIST_STATS 行严重滥用 CSV 字段语义

**裁决：部分成立（致命→严重降级）**

**事实核查**：

反方称 `DIST_STATS` 汇总行（第 723-739 行）将 T 分布统计量塞入不相关 CSV 字段。经逐行核查确认：

| CSV 字段 | 正常含义 | DIST_STATS 行实际存储 | 代码行 | 确认 |
|----------|----------|----------------------|--------|------|
| `T_global` | 拟合温度值 | `np.std(Ts)` | 726 | ✓ |
| `n_cal` | cal 集样本量 | `int(np.median(Ts))` | 728 | ✓ |
| `n_id` | ID test 样本量 | `np.percentile(Ts, 25)` | 729 | ✓ |
| `n_ood` | OOD test 样本量 | `np.percentile(Ts, 75)` | 730 | ✓ |
| `cal_entropy_mean` | cal 熵均值 | `np.median(Ts)` | 731 | ✓ |
| `id_rel_raw` | ID raw Brier reliability | `Ts.max()` | 733 | ✓ |

字段语义滥用事实确认。`int(np.median(Ts))` 对 T~0.5-3.0 确实得 0 或 1。

**是否稻草人**：否。代码确实如此。

**反例是否成立**：部分成立。反方称"下游分析会静默出错"——这取决于下游是否过滤 `fit_status`。

**驳回"致命"定级的理由**：

1. **DIST_STATS 是纯描述性汇总行**，不参与任何科学推断。M1-M3 的结论不依赖此行。该行存储的是 T 分布的 std/median/percentiles 等统计量，供人工查看，非自动化推理输入。

2. **语义切换有显式标记**：`fit_status` 字段编码了行的语义类型（`"n=60,std"`、`"n=60,mean"`、`"n=60,pair_mean"`），`arch` 字段标记 `"SUMMARY"`/`"DIST_STATS"`/`"PAIR_MEAN"`。任何合理的下游消费者过滤 `fit_status == "ok"` 即可只获取真实数据行。

3. **影响范围有限**：R5 方案中 E4 的 CSV 输出用于补充表格和探索性图表，非主检验数据管道。主检验由 `eval_transfer.py` 的 BCa CI 承担（B1 明确声明）。

4. **"致命"的定义是"科学结论被破坏"**：此问题破坏的是数据工程整洁性，非科学推断。降级为"严重"（应修复的代码坏味）。

**实际影响**：中等。若下游脚本不过滤 `fit_status` 直接聚合，会得到无意义结果。但这是下游脚本的健壮性问题，非 E4 脚本的科学推断缺陷。

**修补方案**（采纳反方建议）：

方案 A（推荐）：为汇总统计量使用专用字段名：
```python
summary_rows.append({
    "pair": "ALL", "arch": "DIST_STATS", "seed": -1,
    "T_global": float("nan"),  # 不滥用
    "T_std": float(np.std(Ts)),
    "T_median": float(np.median(Ts)),
    "T_p25": float(np.percentile(Ts, 25)),
    "T_p75": float(np.percentile(Ts, 75)),
    "T_min": float(Ts.min()),
    "T_max": float(Ts.max()),
    "T_p5": float(np.percentile(Ts, 5)),
    "T_p95": float(np.percentile(Ts, 95)),
    "T_mean_abs_dev_1": float(np.mean(np.abs(Ts - 1.0))),
    "fit_status": f"n={len(Ts)},dist_stats",
    # 其余字段留空
})
```

方案 B：输出到单独的 `temperature_distribution_summary.csv`。

**工时**：1h（反方估计准确）

---

## 2. 严重攻击裁决

### S1：偏移敏感度语义错位——cal-time vs test-time shift

**裁决：部分成立（严重→中等降级）**

**事实核查**：

反方称 `process_shift_sensitivity` 在 shifted cal 上拟合 T（cal-time shift），而 M3 实际关心的是 test-time shift（test 漂移后原 T 是否还适用）。代码事实确认：shift 确实施加在 cal 集上（第 622-623 行）。

**是否稻草人论证**：**是，部分稻草人**。

反方将 M3 重解读为"test-time 部署稳健性"问题（"test 分布漂移后，原来 cal 上拟合的 T 还适用吗？"），但 M3 的原文（docstring 第 21-23 行）说的是：

> M3. 偏移敏感度刻画 T 对分布漂移的稳健性：
>     - 若 T 随 shift 单调变化 → T 是 shift 的可辨识函数（可学习先验）
>     - 若 T 近似不变 → T 是 shift-invariant（单点校准即可）

"T 随 shift 单调变化"明确说的是**最优 T 作为 shift 的函数如何变化**——即"如果输入分布变了，最优温度会变多少？"。这正是 cal-time shift 语义：在 shifted 数据上重新拟合 T，观察 T(shift) 的变化。

子条目"T 是 shift-invariant（单点校准即可）"的意思是：如果 T(shift) ≈ T_base 对所有 shift 成立，则无论输入分布如何漂移，单一 T 都是最优的——这也正是 cal-time 语义。

脚本注释（第 570 行）也明确声明：`T(shift) = argmin NLL(cal_shift; T)`，与 M3 一致。

**反方的 test-time 解读是另一个合理问题**，但不是 M3 所问的问题。反方将 M3 的"cal-time T 敏感性"偷换为"test-time T 部署稳健性"，构成部分稻草人。

**反例是否成立**：反方的反例自相矛盾。反方先说"假设模型对 downsample 鲁棒 → T(shift) ≈ T_base → 脚本得出 shift-invariant"，然后说"但 downsample 后 test 的 logits 也几乎不变，所以 T 确实还适用——这个例子恰好一致"。反方自己承认这个例子下两种语义一致。反方随后用 noise 敏感的例子，但承认"这取决于 test 的 label 分布是否也变了，而脚本完全不评估 test 端"——这恰恰说明 test-time 问题是另一个问题，非 M3 所问。

**实际影响**：中等。cal-time shift 分析是 M3 的正确实现，结果有科学意义（刻画 T 对输入分布的依赖性）。但反方正确指出 test-time shift 评估对部署场景更有实践价值，建议作为补充分析添加。

**修补建议**：保留当前 cal-time shift 分析（符合 M3 语义），**额外添加** test-time shift 评估作为补充：
```python
# Test-time shift：shift 施加到 test → 用原 T 校准 → 评估 Brier reliability 退化
ood_probs_shifted = shifted_probs_labels(model, tgt_ds["test"], shift, device)
ood_rel_shifted_raw = brier_reliability_top(ood_probs_shifted[0], ood_probs_shifted[1])
ood_rel_shifted_T = brier_reliability_top(
    apply_global_T(ood_probs_shifted[0], T_base), ood_probs_shifted[1])
# 记算校准性能退化 Δrel = rel_shifted_T - rel_ood_T
```

**工时**：2h（反方估计准确，但这是新增功能非修复 bug）

---

### S2：per-bin Brier reliability 均值 ≠ 全局 Brier reliability 差异

**裁决：成立（严重确认，但为 F1 的衍生问题）**

**事实核查**：

反方称控制台汇总（第 946-955 行）计算 per-bin Δrel 均值而非全局差异。代码事实确认。

**是否独立攻击**：否。S2 与 F1 同源——都是"全局 binned-T Brier reliability 未计算"的表现。F1 是根因（`dist_record` 缺失），S2 是症状（控制台汇总用 per-bin 均值替代）。

**严重程度**：严重确认。控制台输出是研究者最先看到的结果，若 `mean Δrel` 符号与全局差异相反，会直接误导研究结论。

**修补方案**：F1 修复后自动解决。在控制台汇总中改为报告全局 `id_delta_binned_vs_global`（来自 `dist_record`）而非 per-bin 均值。

**工时**：0h（F1 修复后自动解决，反方估计准确）

---

### S3：T_base 拟合失败时 T_relative = T_s / 1.0 = T_s

**裁决：成立（严重确认，但为边界情况）**

**事实核查**：

反方称 `fit_global_T` 失败时返回 `1.0, "fail:..."`，后续 `T_relative = T_s / T_base if T_base > 0` 中 `1.0 > 0` 为 True，输出 `T_s` 而非 NaN。代码事实确认。

**触发条件分析**：

此 bug 仅在以下条件同时满足时触发：
1. `evaluate(model, cal_loader, ...)` 成功（外层 try 不触发）
2. `fit_temperature(cal_probs, y_onehot, method="L-BFGS-B")` 内部抛异常（`fit_global_T` 捕获并返回 1.0）

`fit_temperature` 用 L-BFGS-B 优化，在正常概率矩阵上极少失败。触发场景：cal_probs 含 NaN/Inf（模型异常输出）、所有样本同一类别（NLL 退化）等。属于边界情况。

**反例是否成立**：是。反例（baseline 失败 → T_base=1.0, shift 成功 → T_s=1.5, T_relative=1.5 看似有效但无意义）逻辑正确。

**严重程度**：严重确认（静默错误），但实际触发概率低。定级维持严重是因为"静默错误"的性质——即使罕见，一旦发生无法从输出中区分。

**修补方案**（采纳反方建议）：

第 632 行改为：
```python
"T_relative": T_s / T_base if (status_base == "ok" and T_base > 0) else float("nan"),
```

**工时**：0.1h（反方估计准确）

---

### S4：隐含假设 A2（cal/test 熵分布相似）从未验证

**裁决：部分成立（严重→中等降级）**

**事实核查**：

反方称 A2（cal/test 熵分布相似）在 docstring 中列出但代码从未验证。事实确认：脚本计算了 `cal_ent`（第 480 行）但未与 `id_ent`/`ood_ent` 做任何统计比较。

**是否误解正方意图**：部分误解。

A2 在 docstring 中**显式标注为假设并声明局限**：
> A2. 不确定度（熵）五分位定义的箱边界可从 cal 迁移到 test
>     （即 cal 与 test 的不确定度分布相似——OOD 下可能违反，列为局限）

B4 进一步声明：
> B4. binned-T 在 OOD 下的假设 A2 可能违反——结果解读需谨慎

正方已将"A2 可能违反"列为已知局限。对于**探索性评估**（B1: "不进入主检验"），在 docstring 中声明假设和局限是方法论上的最低标准，已满足。

**反方的标准过高**：反方要求探索性分析在代码中运行时验证每个假设。这在 confirmatory 实验中是合理要求，但探索性分析的标准是"声明假设、谨慎解读"，非"运行时验证每个假设"。

**实际影响**：中等。反方正确指出添加 KS 检验是低成本高收益的改进——当 A2 严重违反时警告研究者，避免无意义的 OOD binned-T 结果被误读。但当前不验证不构成"严重"缺陷，因为局限已声明。

**修补建议**：添加 cal vs OOD 熵分布 KS 检验作为**稳健性检查**（非假设验证）：
```python
from scipy.stats import ks_2samp
ks_stat, ks_p = ks_2samp(cal_ent, predictive_entropy(ood_probs))
dist_record["entropy_ks_stat"] = float(ks_stat)
dist_record["entropy_ks_pvalue"] = float(ks_p)
if ks_stat > 0.3:  # 经验阈值
    warnings.warn(f"A2 可能违反: cal/OOD 熵 KS stat={ks_stat:.3f}, binned-T OOD 结果需谨慎解读")
```

**工时**：0.5h（反方估计准确）

---

### S5：逻辑断链 R1→R2——T 变异 → OOD 难度未测试相关性

**裁决：部分成立（严重→中等降级）**

**事实核查**：

反方称 M1 主张"跨方向变异 → OOD 难度是否反映在 T 上"但脚本从未计算 T 与 OOD 难度指标的相关性。事实确认：脚本计算了 T 的跨方向/架构/种子描述统计（mean/std），但无相关系数、无回归。

**是否误解正方意图**：部分误解。

M1 的原文（第 14 行）：
> 跨方向变异 → OOD 难度是否反映在 T 上

"是否反映在 T 上"是一个**问题**（question），非**断言**（assertion）。脚本提供描述统计（T 跨方向的 mean/std），让研究者**探索**这个问题。对于探索性评估，提供描述统计是合理的第一步——相关性分析可以在后 hoc 用 CSV 数据完成。

反方要求脚本内嵌相关性分析，这对 confirmatory 实验合理，对探索性评估是过高标准。

**反例是否成立**：部分成立。反方反例（T 因类别数差异变异而非 OOD 难度）逻辑正确——T 跨方向变异的原因可能非 OOD 难度。但脚本报告的是"T 有跨方向变异"（描述事实），非"T 因 OOD 难度而变异"（因果断言）。反方攻击的是后者，但脚本说的是前者。

**实际影响**：中等。描述统计有用但不足以支撑因果推断。添加相关性分析会增强 M1 的说服力，但当前不构成"严重"缺陷。

**修补建议**：在 `summarize_distribution` 中添加 T 与 OOD 指标的相关性：
```python
# T vs OOD Brier reliability 改善的相关性
from scipy.stats import spearmanr
ok_records = [r for r in dist_records if r["fit_status"] == "ok"]
Ts = [r["T_global"] for r in ok_records]
ood_deltas = [r["ood_delta_rel_global"] for r in ok_records]
rho, p = spearmanr(Ts, ood_deltas)
# 写入汇总行
```

**工时**：0.5h（反方估计准确）

---

### S6：逻辑断链 R5→R6——T(shift) → shift-invariance 无统计检验

**裁决：部分成立（严重→中等降级）**

**事实核查**：

反方称 M3 的 shift-invariance 判断无统计检验（无单调性检验、无等价性检验、无阈值），完全依赖人工目测 mean/std 表。事实确认。

**是否误解正方意图**：部分误解。

与 S5 类似，M3 的子条目用的是条件式表述："若 T 随 shift 单调变化 → ..."、"若 T 近似不变 → ..."。这是**条件判断框架**，脚本提供 T(shift) 数据供研究者判断条件是否满足。对于探索性评估，提供数据 + 条件框架是合理的。

反方要求"客观标准"和"等价性检验"——这是 confirmatory 分析的标准。探索性分析中，"研究者根据数据主观判断"是可接受的，因为结论不进入主检验。

**反例是否成立**：反方称"不同研究者可能从同一 T(shift) 表得出不同结论"——这在探索性分析中是正常现象，不构成缺陷。探索性结论本就允许主观判断，只要不进入主检验。

**实际影响**：中等。添加简单的不变性判据（如"所有 |T_relative - 1| < 0.1 则标记 shift-invariant"）会提高可复现性，但当前不构成"严重"缺陷。

**修补建议**：添加经验性 shift-invariance 判据：
```python
# 在偏移敏感度汇总中
T_rels = [r["T_relative"] for r in shift_recs if r["shift_name"] != "baseline" 
          and np.isfinite(r["T_relative"])]
max_dev = max(abs(tr - 1.0) for tr in T_rels) if T_rels else float("nan")
invariant_flag = max_dev < 0.1  # 经验阈值：所有 shift 的 T 偏离 <10%
print(f"  Shift-invariance: max|T_rel-1|={max_dev:.4f} → {'INVARIANT' if invariant_flag else 'NOT invariant'}")
```

**工时**：1h（反方估计准确）

---

### S7：brier_reliability_top 语义偏移——top-label vs full multiclass

**裁决：部分成立（严重→中等降级）**

**事实核查**：

反方称 `brier_reliability_top` 用 max-prob + correct_mask 将多分类降维为二分类，而 R5 讨论的是多分类 Murphy 分解。代码事实确认：`brier_reliability_top`（第 166-175 行）确实用 top-label 语义。

**是否误解正方意图**：部分误解。

1. **Top-label 校准是标准方法**：Guo et al. (ICML 2017) 的经典温度缩放论文使用 top-label ECE。Top-label Brier reliability 是校准文献中的标准指标，非非标准做法。

2. **R5 方案未指定 multiclass**：R5 第 358 行说"报告分箱温度 vs 单一 T 的 Brier reliability 改善对比"，未指定 top-label vs multiclass。R5 §Methods 讨论的"Brier reliability"在 TS 语境下通常指 top-label（因为 TS 主要影响 max-prob 的校准）。

3. **脚本内部一致**：所有 Brier reliability 计算都用 top-label 语义，无混用。

**反例是否成立**：理论成立但实践影响小。反方称"TS 可能改善 top-label 但恶化次级类别校准"——TS 对所有 logits 做统一缩放（softmax 温度），对 top-label 和次级类别的影响方向通常一致。大幅分歧在实践中罕见。

**实际影响**：中等。脚本应在 docstring 和论文中明确标注"top-label Brier reliability"，避免读者误以为是 multiclass。但当前做法是标准且自洽的。

**修补建议**：
1. 在 `brier_reliability_top` 的 docstring 中明确标注"top-label（binary reduction）Brier reliability"
2. 在 E4 脚本 docstring 和 R5 方案中注明"E4 使用 top-label Brier reliability"
3. 可选：添加 multiclass Brier reliability 作为补充指标

**工时**：0.5h（文档标注）+ 0.5h（可选 multiclass 实现）

---

### S8：docstring 说"8+档"但实际 13 档

**裁决：成立（严重→轻微降级）**

**事实核查**：

反方称 docstring 第 8 行说"8+档"但 `get_l2_shifts()` 返回 13 档。经核查 `l2_shifts.py` 确认：降采样 2 + 导联 4 + 噪声 5 + 增益 2 = 13 档。docstring 第 8 行确实写"8+档"。

反方还指出 docstring 写"prior shift"但实际是协变量漂移。A4（第 32-33 行）承认"严格说 L2 shift 是协变量漂移而非纯 prior shift"，但 docstring 第 8 行仍写"prior shift"。

**是否稻草人**：否。文档与代码不一致是事实。

**严重程度降级理由**：这是**文档笔误**，不影响代码行为或科学推断。`get_l2_shifts()` 返回 13 档是正确的，脚本正确处理 13 档。"8+档"只是 docstring 描述不准确。同理"prior shift"是术语不严谨，但 A4 已声明局限。

**修补方案**：
- docstring 第 8 行：`偏移敏感度：T 值随 L2 prior shift（8+档）的变化趋势` → `偏移敏感度：T 值随 L2 协变量漂移（13 档）的变化趋势`

**工时**：0.1h（反方估计准确）

---

### S9：binned-T insufficient samples 时 T=1.0 偏向 global-T

**裁决：部分成立（严重→中等降级）**

**事实核查**：

反方称 `fit_binned_T` 在样本不足时设 T_bin=1.0（identity），系统性偏向 global-T。代码事实确认（第 379-382 行）。

**偏差机制核查**：

反方的偏差机制分析正确：insufficient bin 的 binned-T=1.0（无校准），而 global-T 在全样本上拟合（有校准）。在 insufficient bin 上，binned-T 的 `id_delta_binned_vs_global = rel(1.0) - rel(T_global) > 0`（binned 更差），但这是因为 binned-T 无法拟合，非 T 是常数。

**部分成立的理由**：

1. **偏差机制真实**：insufficient bin 确实系统性偏向 global-T。
2. **但有显式标记**：`fit_status = "insufficient_samples(n=...)"` 标记了这些 bin，下游可过滤。
3. **影响有限**：cal 集通常 ~2000 样本，5 bin 每箱 ~400 样本，`n_classes * 2 = 8-10` 的阈值极少触发。OOD 下 bin 漂移可能导致某些 bin 样本少，但这是 A2 问题（S4 已覆盖）。

**实际影响**：中等。偏差机制真实但 `fit_status` 标记部分缓解。在 F1 修复后（用全局 binned-T Brier reliability 做比较），insufficient bin 的影响会被正确反映（全局计算自动包含 insufficient bin 的 identity 效果）。

**修补建议**：
- 方案 A：insufficient bin 用 global-T 填充而非 1.0（`T_bin = T_global`），避免人为偏向
- 方案 B：在汇总中排除 insufficient bin 并报告排除数量

```python
if n_b < n_classes * 2:
    rec["T_bin"] = T_global  # 用 global-T 填充，避免人为偏向
    rec["status"] = f"insufficient_samples(n={n_b},filled_with_global_T)"
```

**工时**：0.5h（反方估计准确）

---

### S10：偏移敏感度不用缓存——780 次模型前向无法加速

**裁决：部分成立（严重→中等降级）**

**事实核查**：

反方称 `process_shift_sensitivity` 总是重新加载模型，即使 `--cache-dir` 提供也不缓存 shifted probs。事实确认：缓存只存 cal/id/ood probs（第 469-473 行），不存 shifted probs。

**量级核查**：

反方估计 60 实验 × 13 shifts = 780 次 cal 集前向，每次 ~2000 样本逐样本循环，总计 1.56M 次单样本前向。量级估计合理。

**严重程度降级理由**：

1. **这是性能问题，非正确性问题**：结果正确，只是慢。
2. **有 workaround**：`--skip-shift-sensitivity` 标志允许跳过。
3. **不影响科学推断**：慢但结果正确。
4. **"严重"定级不成立**：性能问题不应定级为"严重"（严重应留给影响结论正确性的问题）。

**实际影响**：中等（性能）。重跑时间可能不可接受，但首次运行结果正确。

**修补建议**：
- 短期：缓存 shifted probs（`shifted_cache_key = f"{cache_key}__shift_{shift['name']}"`）
- 长期：`shifted_probs_labels` 改为 batched DataLoader（与 M12 同源）

**工时**：2h（反方估计准确）

---

## 3. 轻微攻击裁决

### M1：id_ent/ood_ent 在 per-bin 循环内重复计算

**裁决：成立（轻微确认）**

**事实核查**：第 516-517 行在 5 次循环内重复计算 `predictive_entropy(id_probs)` 和 `predictive_entropy(ood_probs)`，应移到循环外。5 倍冗余。

**修补**：移到循环外。**工时**：0.1h。

---

### M2：N_BINS 全局可变——多次调用 main() 状态泄漏

**裁决：部分成立（轻微确认，但反方分析有误）**

**事实核查**：

反方称 `N_BINS` 全局可变导致 `fit_binned_T` 默认参数问题。但反方自己的分析承认：

> 实际上 `N_BINS` 的默认值在函数定义时已固定为 5，后续 `global N_BINS` 修改不影响 `fit_binned_T` 的默认值。**但** `fit_binned_T` 调用时显式传 `n_bins=N_BINS`（第 506 行），所以实际生效。

反方自相矛盾：先说有 bug，后说"实际生效"。**实际上无 bug**——`fit_binned_T` 在第 506 行被调用时显式传 `n_bins=N_BINS`，全局修改生效。

**设计脆弱性确认**：如果其他代码调用 `fit_binned_T()` 不传参数，会用定义时默认值 5 而非命令行值。这是设计坏味，非实际 bug。

**修补建议**：将 `N_BINS` 改为参数传递而非全局变量。**工时**：0.2h。

---

### M3：CSV 无 provenance 元数据

**裁决：成立（轻微确认）**

**事实核查**：三个 CSV 无生成时间戳、脚本版本、N_BINS、T_MIN/T_MAX 等。事实确认。

**修补**：添加 sidecar JSON metadata。**工时**：0.3h。

---

### M4：探索性标签未在 CSV 中强制标记

**裁决：成立（轻微确认）**

**事实核查**：B1 声明探索性但 CSV 无标记列。事实确认。

**修补**：CSV 加 `analysis_type` 列（值="exploratory"）。**工时**：0.1h。

---

### M5：5 quintile 无箱数敏感性分析

**裁决：成立（轻微确认）**

**事实核查**：B2 列为局限但未实现。`--n-bins` 参数存在但无敏感性循环。事实确认。

**修补**：添加 `--sensitivity-bins 3,5,7,10` 选项循环跑。**工时**：1h。

---

### M6：per-bin 小样本 Brier reliability 高方差

**裁决：成立（轻微确认）**

**事实核查**：per-bin ~400 样本用 10 等宽分箱，每 max-prob bin ~40 样本，Brier reliability 估计方差高。统计事实确认。

**修补**：报告 per-bin Brier reliability 的 bootstrap CI。**工时**：0.5h。

---

### M7：T_relative 无 clipping——极端值主导汇总

**裁决：成立（轻微确认）**

**事实核查**：`T_relative = T_s / T_base`（第 632 行）可达 10000（T_s=100, T_base=0.01），无 clipping。事实确认。

**修补**：`T_relative = np.clip(T_s / T_base, 0.01, 100.0)` 或用 log 变换。**工时**：0.1h。

---

### M8：NaN 熵静默入 bin 0

**裁决：成立（轻微确认）**

**事实核查**：`np.digitize(NaN, edges[1:-1])` 返回 0，NaN 熵静默分入 bin 0。事实确认。

**修补**：检查 NaN 并标记。**工时**：0.1h。

---

### M9：退化熵 fallback 不处理全同值

**裁决：成立（轻微确认）**

**事实核查**：`quintile_edges` fallback（第 193 行）`np.linspace(v, v+1e-9, n_bins+1)`，全同值时所有样本入最后一个 bin。事实确认。

**修补**：全同值时返回单 bin 或报错。**工时**：0.1h。

---

### M10：binned_records 的 fit_status 不反映 global T 失败

**裁决：成立（轻微确认）**

**事实核查**：第 563 行 `"fit_status": rec["status"]` 是 per-bin 状态。若 global T 失败（T_global=1.0），per-bin 的 `id_rel_global_T` 用 fallback T=1.0 但 `fit_status` 不反映。事实确认。

**修补**：加 `global_fit_status` 列。**工时**：0.1h。

---

### M11：discover_experiments 不验证 checkpoint 完整性

**裁决：部分驳回（轻微→驳回降级）**

**事实核查**：

反方称第 803 行只检查 `ckpt.exists()` 不检查可加载性，损坏 checkpoint 导致 `process_one` 失败被 try/except 捕获（第 868 行），"失败只打印到控制台，不写入失败 CSV"。

**驳回理由**：

1. **失败记录在 dist_records 中**：第 870-880 行的 except 分支**确实**将失败记录写入 `all_dist`：
```python
all_dist.append({
    "pair": pair, "arch": arch, "seed": seed,
    ...
    "T_global": float("nan"), "fit_status": f"fail:{type(e).__name__}",
    ...
})
```
失败实验以 `fit_status="fail:..."` 和 `T_global=NaN` 写入 CSV，**非静默失败**。下游过滤 `fit_status == "ok"` 即可排除。

2. **checkpoint 完整性验证成本不合理**：加载每个 checkpoint 验证完整性需要反序列化整个 state_dict，与实际使用时的加载成本相同。`discover_experiments` 只做存在性检查是合理的快速筛选。

**实际影响**：极低。失败有记录（`fit_status` 列），非静默。

**修补建议**：无需修改。若需增强，可在失败记录中添加 `error_message` 列。

---

### M12：shifted_probs_labels 逐样本前向——无 batch

**裁决：成立（轻微确认，与 S10 同源）**

**事实核查**：第 303 行 `for i in range(n):` 逐样本循环，无 DataLoader/batch。事实确认。

**与 S10 的关系**：M12 是 S10 的性能根因（逐样本前向导致 780×2000 次单样本前向）。S10 是系统级影响，M12 是代码级实现。

**修补**：改为 batched DataLoader。**工时**：0.5h。

---

## 4. 对"探索性定位攻击"的裁决（§6.1-6.3）

### 6.1 探索性标签的效力

**裁决**：与 M4 同源，已覆盖。CSV 无探索性标记是真实问题（M4 成立），但"若下游误用，后果严重"的推断依赖假设性下游行为。E4 的探索性定位在 docstring、R5 方案、控制台输出中三重声明，方法论约束已满足。

### 6.2 E4 与 E3 的指标重叠

**裁决：驳回（方法论质疑，非代码缺陷）**

反方称 E4 和 E3 都计算 Brier reliability，"探索性标签可能成为选择性报告的掩护"。但反方自己承认"代码层面无法防范"。

这是对研究者诚实度的质疑，非对代码的攻击。代码无法防范选择性报告——这是方法论和审稿流程的职责，非代码审查的范畴。**作为代码审查攻击点，此条不成立**。

### 6.3 外推限制未在代码中体现

**裁决**：与 S4/M4 同源，已覆盖。外推限制在 docstring 中声明（B1-B5, P1-P5），代码中无运行时检查。对探索性评估，docstring 声明是最低标准。S4 已建议添加 KS 检验作为稳健性检查。

---

## 5. 裁决汇总表

| 编号 | 反方标注 | 裁决 | 实际严重程度 | 是否稻草人 | 反例是否成立 | 修补工时 |
|------|----------|------|-------------|-----------|-------------|---------|
| F1 | 致命 | **成立** | 致命 | 否 | 是 | 0.5h |
| F2 | 致命 | **部分成立** | 严重 | 否 | 部分 | 1h |
| S1 | 严重 | **部分成立** | 中等 | **是（部分）** | 自相矛盾 | 2h（新增功能） |
| S2 | 严重 | **成立** | 严重 | 否 | 是 | 0h（F1 修复后解决） |
| S3 | 严重 | **成立** | 严重（边界） | 否 | 是 | 0.1h |
| S4 | 严重 | **部分成立** | 中等 | 部分 | — | 0.5h |
| S5 | 严重 | **部分成立** | 中等 | 部分 | 部分 | 0.5h |
| S6 | 严重 | **部分成立** | 中等 | 部分 | — | 1h |
| S7 | 严重 | **部分成立** | 中等 | 部分 | 理论成立实践罕见 | 0.5h |
| S8 | 严重 | **成立** | 轻微 | 否 | 是 | 0.1h |
| S9 | 严重 | **部分成立** | 中等 | 否 | 是（有标记缓解） | 0.5h |
| S10 | 严重 | **部分成立** | 中等（性能） | 否 | — | 2h |
| M1 | 轻微 | **成立** | 轻微 | 否 | 是 | 0.1h |
| M2 | 轻微 | **部分成立** | 轻微（设计坏味） | 否 | 无实际 bug | 0.2h |
| M3 | 轻微 | **成立** | 轻微 | 否 | 是 | 0.3h |
| M4 | 轻微 | **成立** | 轻微 | 否 | 是 | 0.1h |
| M5 | 轻微 | **成立** | 轻微 | 否 | 是 | 1h |
| M6 | 轻微 | **成立** | 轻微 | 否 | 是 | 0.5h |
| M7 | 轻微 | **成立** | 轻微 | 否 | 是 | 0.1h |
| M8 | 轻微 | **成立** | 轻微 | 否 | 是 | 0.1h |
| M9 | 轻微 | **成立** | 轻微 | 否 | 是 | 0.1h |
| M10 | 轻微 | **成立** | 轻微 | 否 | 是 | 0.1h |
| M11 | 轻微 | **部分驳回** | — | 否 | **不成立** | 0h |
| M12 | 轻微 | **成立** | 轻微 | 否 | 是 | 0.5h |

---

## 6. 对反方攻击质量的元评估

### 6.1 反方攻击的优点

1. **代码事实核查准确率高**：24 个攻击点中 22 个的代码行号和事实描述基本准确（M11 的"不写入失败 CSV"有误，M2 的分析自相矛盾）。事实核查质量高。

2. **F1 是真正的核心发现**：全局 binned-T Brier reliability 未计算是反方最有价值的攻击。数学论证严格（per-bin 均值 ≠ 全局差异），反例构造正确，修复建议合理。此攻击单独成立即可证明 M2 无法从当前输出评估。

3. **七维度覆盖全面**：反例构造、逻辑断链、隐含假设、边界失效、自相矛盾、量级错误、语义偏移均有覆盖。

4. **修复建议可操作**：大部分修复建议给出了具体代码修改，工时估计合理。

### 6.2 反方攻击的缺陷

1. **系统性严重程度夸大**：24 个攻击中 12 个被标为"致命"或"严重"，但经审查仅 3 个真正达到"严重"及以上（F1 致命、S2/S3 严重）。9 个"严重"攻击中 7 个应为"中等"——反方一致性地用 confirmatory 标准要求探索性分析，忽视 E4 的 B1 定位（"不进入主检验"）。

2. **一个稻草人论证（S1）**：反方将 M3 的"T 对分布漂移的敏感性"（cal-time 语义）重解读为"test-time 部署稳健性"，但 M3 原文和子条目明确说的是 cal-time。脚本实现与 M3 一致。

3. **F2 过度定级**：DIST_STATS 行字段语义滥用是真实的代码坏味，但该行是纯描述性汇总，不参与任何科学推断。"致命"要求科学结论被破坏，此处破坏的是数据工程整洁性。

4. **M11 事实错误**：反方称失败"不写入失败 CSV"，但第 870-880 行的 except 分支确实将失败记录写入 `all_dist`（`fit_status="fail:..."`），非静默失败。

5. **M2 分析自相矛盾**：反方先说有 bug，后承认"实际生效"。

6. **6.2 超出代码审查范畴**：对研究者诚实度的质疑（"探索性标签可能成为选择性报告的掩护"）是方法论质疑，非代码缺陷。

### 6.3 对正方的建议

基于有效攻击的修补优先级：

**P0（必须修复，阻塞发布）**：
- F1：添加全局 binned-T Brier reliability 计算（0.5h）
- S3：修复 T_base 失败时 T_relative 的条件判断（0.1h）

**P1（应修复，提升可靠性）**：
- F2：DIST_STATS 行使用专用字段名（1h）
- S8：更新 docstring "8+档"→"13档"、"prior shift"→"协变量漂移"（0.1h）
- S9：insufficient bin 用 global-T 填充而非 1.0（0.5h）
- M1：id_ent/ood_ent 移到循环外（0.1h）
- M7：T_relative 添加 clipping（0.1h）

**P2（建议修复，提升完整性）**：
- S4：添加 cal/OOD 熵 KS 检验（0.5h）
- S5：添加 T 与 OOD 指标 Spearman 相关（0.5h）
- S6：添加 shift-invariance 经验判据（1h）
- S7：明确标注 top-label Brier reliability（0.5h）
- S10/M12：偏移敏感度缓存 + batched 前向（2h）
- S1：添加 test-time shift 补充评估（2h）
- M3-M6, M8-M10：各种轻微改进（1.3h）

**总修补工时**：P0 0.6h + P1 1.8h + P2 7.8h ≈ **10.2h**（反方估计 11.7h，差异来自 M11 驳回和部分降级）

---

## 7. 最终裁决

### 7.1 核心问题确认

反方攻击的**核心发现 F1 成立**：E4 脚本确实未计算全局 binned-T Brier reliability，M2 的核心比较（binned-T vs global-T 的全局 Brier reliability）无法从当前输出中得出。per-bin 均值是误导性代理指标，符号可与全局差异相反。**此问题必须修复（P0）。**

### 7.2 反方过度攻击的方面

1. **F2 非"致命"**：DIST_STATS 字段语义滥用是代码坏味，不影响科学推断。降级为严重。
2. **S1 是部分稻草人**：脚本实现与 M3 原文一致（cal-time 语义），反方重解读为 test-time 语义。
3. **7 个"严重"攻击应为"中等"**：S4/S5/S6/S7/S9/S10 在探索性定位下被夸大，用 confirmatory 标准要求探索性分析。
4. **M11 事实错误**：失败记录确实写入 CSV，非静默失败。

### 7.3 三大主张的可支持性（修正后评估）

| 主张 | 反方裁决 | 反反方裁决 | 修正后能否支撑 |
|------|----------|-----------|---------------|
| M1（T 分布揭示变异结构） | 部分 | 部分成立 | **能（描述统计层面）**；相关性分析（S5）为增强项非必需 |
| M2（binned-T 捕捉 T 异质性） | 不能 | F1 成立时不能，**F1 修复后能** | **修复 F1 后能**；全局 binned-T Brier reliability 是正确比较 |
| M3（偏移敏感度刻画 T 稳健性） | 不能 | **部分成立**（S1 部分稻草人） | **能（cal-time 语义层面）**；test-time 补充评估为增强项 |

### 7.4 整体裁决

**反方攻击在代码事实层面质量较高，但在严重程度判定上存在系统性夸大。** 24 个攻击点中：

- **1 个真正致命**（F1）：M2 核心比较缺失，必须修复
- **2 个真正严重**（S2, S3）：S2 随 F1 解决，S3 为边界 bug
- **1 个严重代码坏味**（F2）：应修复但不影响科学推断
- **7 个中等**（S1, S4-S7, S9, S10）：探索性定位下被夸大，建议修复
- **1 个轻微文档问题**（S8）：docstring 笔误
- **11 个轻微**（M1-M10, M12）：基本确认，多数修复简单
- **1 个部分驳回**（M11）：反方事实错误

**正方行动建议**：修复 F1（0.5h）+ S3（0.1h）后，E4 可作为探索性评估提供 T 分布的汇总统计和 binned-T 的全局比较。S4-S7/S9/S10 的修复将进一步提升可靠性，但非阻塞发布项。

**反方攻击的净贡献**：正面。F1 是反方最有价值的发现，直接指向 M2 的核心缺陷。尽管严重程度被系统性夸大（12 个"致命/严重"中仅 3 个真正达到该级别），但 F1 单独成立即证明了反方攻击的实质价值。建议正方采纳 F1/S3 的 P0 修复和 F2/S8/S9 的 P1 修复。

---

> **反反方审查代理声明**：我以代码事实为唯一裁判依据，对反方 24 个攻击点逐条审查。裁决 13 个成立、9 个部分成立、2 个部分驳回。反方攻击的核心发现（F1）成立且有价值，但严重程度存在系统性夸大（7 个"严重"应为"中等"），1 个稻草人论证（S1），1 个事实错误（M11）。建议正方优先修复 F1（全局 binned-T Brier reliability 缺失）和 S3（T_relative 边界 bug），合计 0.6h。
