# E4 实验脚本反方攻击报告

> **反方挑刺代理-E4 交付**。本报告对正方设计的 `run_e4_temperature_analysis.py`（975 行）进行最严厉的逐行独立攻击审查，覆盖温度分布分析、分箱温度探索性评估、偏移敏感度分析三大模块，寻找逻辑漏洞、隐含假设不成立、边界失效、代码 bug 和输出格式问题。
> **攻击日期**：2026-09-09
> **攻击对象**：`scripts/run_e4_temperature_analysis.py`（975 行）+ `docs/Q2_UPGRADE_PROPOSAL_R5.md` E4 章节 + `src/utils/calibration.py` + `src/data/l2_shifts.py`
> **攻击代理**：反方挑刺代理-E4（GLM-5.2）
> **诚实原则**：对每个核心主张，问"代码是否真的能支撑这个结论，还是只是看起来能？"
> **攻击维度**：反例构造 / 逻辑断链 / 隐含假设 / 边界失效 / 自相矛盾 / 量级错误 / 语义偏移（7 维度全覆盖）

---

## 0. 攻击审查概述

### 攻击数量统计

| 严重性 | 数量 | 编号 |
|--------|------|------|
| **致命** | 2 | F1, F2 |
| **严重** | 10 | S1-S10 |
| **轻微** | 12 | M1-M12 |
| **合计** | 24 | — |

### 整体评估

E4 脚本在工程层面较为完整（缓存、异常处理、CSV 输出、控制台汇总均有实现），但在**科学推断层面存在两个致命缺陷**：

1. **F1（致命）**：M2 的核心比较——"binned-T 的 Brier reliability 是否优于 global-T"——**从未在代码中计算**。脚本计算了 per-bin Brier reliability 但从未计算全局 binned-T Brier reliability，而 Brier reliability 不可加，per-bin 均值 ≠ 全局差异。
2. **F2（致命）**：`summarize_distribution` 的 `DIST_STATS` 汇总行**严重滥用 CSV 字段语义**——`n_cal` 列存储 T 的中位数、`id_rel_raw` 列存储 T 的最大值等，导致同一 CSV 列在不同行有完全不同的含义，下游分析会静默出错。

此外，偏移敏感度的语义错位（S1）、隐含假设 A2 未验证（S4）、两个逻辑断链（S5, S6）等严重攻击表明：**E4 的三个核心主张 M1-M3 均无法从脚本输出中得出严格结论**。

---

## 1. 致命攻击

### F1：M2 核心比较缺失——全局 binned-T Brier reliability 从未计算

**攻击维度**：逻辑断链 + 自相矛盾

**问题描述**：

M2 的核心主张（docstring 第 20 行）：
> 若 binned-T 的 Brier reliability 优于 global-T，说明 T 不是常数

脚本确实计算了 `id_probs_binned`（第 509 行）和 `ood_probs_binned`（第 510 行）——分箱温度应用后的完整概率矩阵：
```python
id_probs_binned = apply_binned_T(id_probs, T_per_bin, bin_edges)
ood_probs_binned = apply_binned_T(ood_probs, T_per_bin, bin_edges)
```

但**从未调用** `brier_reliability_top(id_probs_binned, id_labels)` 计算全局 binned-T 的 Brier reliability。

- `dist_record`（第 488-503 行）有 `id_rel_global_T` 但**没有** `id_rel_binned_T`
- `binned_records`（第 540-564 行）有 per-bin `id_rel_binned_T` 但这是**箱内** Brier reliability，不是全局
- 控制台汇总（第 946-955 行）计算 `mean(id_delta_binned_vs_global)`——这是 per-bin Δrel 的均值

**为什么 per-bin 均值 ≠ 全局差异**：

`brier_parts`（calibration.py 第 586-626 行）的 reliability 计算为：
```
rel(global) = Σ_{j=1}^{10} (n_j / n) * (avg_prob_j - avg_label_j)²
```
其中 j 是 max-prob 的 10 等宽分箱，`avg_label_j` 是箱内正确率，n 是总样本数。

当我们在 entropy quintile bin b 的子集上计算 `brier_reliability_top` 时：
```
rel(bin_b) = Σ_{j=1}^{10} (n_{b,j} / n_b) * (avg_prob_{b,j} - avg_label_{b,j})²
```

全局 binned-T 的 Brier reliability 是：
```
rel_binned(global) = Σ_{b=1}^{5} Σ_{j=1}^{10} (n_{b,j} / n) * (avg_prob_{b,j} - avg_label_{b,j})²
```

而 per-bin 均值是：
```
mean_b [rel_binned(b) - rel_global(b)] = (1/5) Σ_b [rel_binned(b) - rel_global(b)]
```

这两个表达式**结构不同**：全局用 `n_{b,j}/n` 加权，per-bin 均值用 `1/5` 等权。当各 bin 样本量不均时（OOD 下极常见），两者不仅数值不同，**符号都可能相反**。

**反例**：
- 假设 5 个 bin 的样本量为 [800, 800, 200, 100, 100]（OOD 下低不确定度样本多）
- bin 3 的 binned-T 比 global-T 好 Δrel = -0.02（改善），但只有 200 个样本
- bin 1-2 的 binned-T 比 global-T 差 Δrel = +0.005（恶化），各有 800 个样本
- per-bin 均值 = (-0.02 + 0.005 + 0.005 + ...) / 5 ≈ -0.002（看起来 binned 更优）
- 全局差异 = (800×0.005 + 800×0.005 + 200×(-0.02) + ...) / 2000 ≈ +0.002（binned 实际更差）
- **结论相反**！

**影响**：M2 的核心问题"分箱温度是否有实用价值"**无法从脚本输出中回答**。控制台汇总的 `mean Δrel` 是误导性代理指标。

**严重程度**：**致命**——M2 是 E4 的三大核心主张之一，其核心比较在代码中缺失。

**修复建议**：在 `process_one` 中添加：
```python
id_rel_binned_global = brier_reliability_top(id_probs_binned, id_labels)
ood_rel_binned_global = brier_reliability_top(ood_probs_binned, ood_labels)
```
并将 `id_rel_binned_global` 和 `id_rel_binned_global - id_rel_global` 加入 `dist_record`。

---

### F2：summarize_distribution 的 DIST_STATS 行严重滥用 CSV 字段语义

**攻击维度**：自相矛盾 + 语义偏移

**问题描述**：

`summarize_distribution`（第 658-741 行）的 `DIST_STATS` 汇总行（第 723-739 行）将 T 分布统计量塞入不相关的 CSV 字段：

| CSV 字段 | 正常含义 | DIST_STATS 行实际存储 | 代码行 |
|----------|----------|----------------------|--------|
| `T_global` | 拟合温度值 | `np.std(Ts)` — T 的标准差 | 726 |
| `n_cal` | cal 集样本量 | `int(np.median(Ts))` — T 的中位数取整 | 728 |
| `n_id` | ID test 样本量 | `np.percentile(Ts, 25)` — T 的 25 分位 | 729 |
| `n_ood` | OOD test 样本量 | `np.percentile(Ts, 75)` — T 的 75 分位 | 730 |
| `cal_entropy_mean` | cal 熵均值 | `np.median(Ts)` — T 的中位数 | 731 |
| `cal_entropy_std` | cal 熵标准差 | `Ts.min()` — T 的最小值 | 732 |
| `id_rel_raw` | ID raw Brier reliability | `Ts.max()` — T 的最大值 | 733 |
| `id_rel_global_T` | ID global-T Brier reliability | `np.percentile(Ts, 5)` — T 的 5 分位 | 734 |
| `id_delta_rel_global` | ID Δrel | `np.percentile(Ts, 95)` — T 的 95 分位 | 735 |
| `ood_rel_raw` | OOD raw Brier reliability | `np.mean(\|Ts - 1.0\|)` — T 偏离 1.0 的均值 | 736 |

**具体 bug**：`int(np.median(Ts))`（第 728 行）——T 值通常在 0.5-3.0 范围，`int()` 截断后 `n_cal` = 0 或 1。一个名为"cal 集样本量"的字段存储了 0 或 1。

**下游影响**：

任何下游脚本如果不检查 `fit_status` 字段就跨行聚合，会得到无意义结果：
```python
df = pd.read_csv("temperature_distribution_analysis.csv")
df['n_cal'].mean()  # 混合了真实样本量（~2000）和 T 中位数（0 或 1）
df['id_rel_raw'].max()  # 混合了 Brier reliability（~0.05）和 T 最大值（~3.0）
```

`fit_status` 字段（如 `"n=60,std"`、`"n=60,mean"`）编码了语义切换，但这是一个**脆弱的隐式契约**——CSV schema 文档（docstring 第 70-73 行）没有说明汇总行的字段重定义。

**严重程度**：**致命**——CSV 输出对下游不可靠，任何自动化分析管道都可能静默出错。

**修复建议**：为汇总统计量使用专用字段名（如 `T_std`, `T_median`, `T_p25`, `T_p75`, `T_min`, `T_max`, `T_p5`, `T_p95`, `T_mean_abs_dev_1`），或输出到单独的 `temperature_distribution_summary.csv`。

---

## 2. 严重攻击

### S1：偏移敏感度语义错位——T(shift) 拟合在 shifted cal 上，非 shifted test

**攻击维度**：隐含假设 + 语义偏移

**问题描述**：

`process_shift_sensitivity`（第 579-652 行）的偏移敏感度语义（注释第 570 行）：
> T(shift) = argmin NLL(cal_shift; T)
> 即：cal 集信号施加 shift → 模型前向 → 拟合 T

代码第 622-623 行：
```python
cal_probs_s, cal_labels_s = shifted_probs_labels(
    model, src_ds["cal"], shift, device
)
```

shift 施加在 **cal 集**上，而非 test 集。

**但 M3 的实际问题是**（docstring 第 21-23 行）：
> M3. 偏移敏感度刻画 T 对分布漂移的稳健性

在部署场景中，分布漂移发生在 **test 端**（模型遇到漂移的输入），问题是"test 分布漂移后，原来 cal 上拟合的 T 还适用吗？"——即 `T_test_shift = argmin NLL(test_shift; T)` 是否 ≈ `T_cal = argmin NLL(cal; T)`。

脚本回答的是不同的问题："如果 cal 集本身漂移了，重新拟合的 T 会变多少？"——这是 **cal-time shift**，不是 **test-time shift**。

**两者的区别**：
- **Cal-time shift**（脚本实际做的）：cal 数据施加 shift → 模型前向 → 拟合 T。刻画的是"T 拟合过程对 cal 输入漂移的敏感度"。
- **Test-time shift**（M3 实际关心的）：test 数据施加 shift → 用原 cal 拟合的 T 校准 → 评估 Brier reliability。刻画的是"已拟合的 T 在漂移 test 上的校准性能退化"。

**反例**：假设模型对 downsample 鲁棒（downsample 后 logits 几乎不变），则 cal_shift 的 logits ≈ cal 的 logits，T(shift) ≈ T_base——脚本会得出"T 是 shift-invariant"的结论。但 downsample 后 test 的 logits 也几乎不变，所以 T 确实还适用——这个例子恰好一致。**但如果模型对 noise 敏感**：cal_shift 的 logits 变化大，T(shift) 变化大——脚本得出"T 对 noise 敏感"。但实际问题是在 noisy test 上，原 T 的校准性能如何——这取决于 test 的 label 分布是否也变了，而脚本完全不评估 test 端。

**影响**：M3 的"T 对分布漂移的稳健性"结论**语义不匹配**。脚本刻画的是 cal-time 敏感度，不是 test-time 稳健性。

**严重程度**：**严重**——M3 的核心语义错位，结果可能被误读为 test-time 稳健性。

---

### S2：per-bin Brier reliability 均值 ≠ 全局 Brier reliability 差异

**攻击维度**：量级错误 + 逻辑断链

**问题描述**：

控制台汇总（第 946-955 行）：
```python
id_delta = [r["id_delta_binned_vs_global"] for r in all_binned
            if np.isfinite(r["id_delta_binned_vs_global"])]
print(f"  mean Δrel = {np.mean(id_delta):+.6f}  (负=binned 更优)")
```

这计算的是 **per-bin Δrel 的均值**：
```
mean_b [rel_binned(b) - rel_global(b)]
```

但 M2 的正确比较是 **全局 Brier reliability 差异**：
```
rel_binned(global) - rel_global(global)
```

如 F1 所述，Brier reliability 不可加——`rel(global) = Σ_j (n_j/n) * (avg_prob_j - avg_label_j)²`，而 per-bin rel 用 `n_{b,j}/n_b` 加权。当各 bin 样本量不均时，per-bin 均值和全局差异不仅数值不同，**符号都可能相反**。

**影响**：控制台汇总的 `mean Δrel` 是误导性指标，可能得出与全局比较相反的结论。

**严重程度**：**严重**——与 F1 同源，控制台输出可能误导研究者。

---

### S3：T_base 拟合失败时 T_relative = T_s / 1.0 = T_s（应为 NaN）

**攻击维度**：边界失效 + 代码 bug

**问题描述**：

`fit_global_T`（第 341-351 行）的异常处理：
```python
except Exception as e:
    warnings.warn(f"fit_global_T failed: {e}")
    return 1.0, f"fail:{type(e).__name__}"
```

拟合失败时返回 `T=1.0`（identity 温度），而非 NaN。

`process_shift_sensitivity` 中 baseline 拟合（第 604 行）：
```python
T_base, status_base = fit_global_T(cal_probs_base, cal_labels_base)
```

如果 `fit_temperature` 内部抛异常，`fit_global_T` 捕获并返回 `1.0, "fail:..."`。外层 try/except（第 599-606 行）只捕获 `fit_global_T` 之外的异常（如 evaluate 失败）。

后续 shift 的 T_relative 计算（第 632 行）：
```python
"T_relative": T_s / T_base if T_base > 0 else float("nan"),
```

当 `T_base = 1.0`（拟合失败的 fallback）时，`1.0 > 0` 为 True，所以 `T_relative = T_s / 1.0 = T_s`。

**Bug**：baseline 拟合失败时，T_relative 应为 NaN（无意义），但实际输出 `T_s`——一个看似合理但完全错误的相对温度。

**反例**：
- baseline 拟合失败 → T_base = 1.0, status_base = "fail:ValueError"
- shift = noise6 拟合成功 → T_s = 1.5, status_s = "ok"
- T_relative = 1.5 / 1.0 = 1.5（看起来 T 增大了 50%）
- **实际意义**：baseline 无意义，T_relative = 1.5 也无意义，但 CSV 中显示为有效数字

**影响**：偏移敏感度 CSV 中可能包含大量看似有效但实际无意义的 T_relative 值。

**严重程度**：**严重**——静默错误，下游分析无法区分真实 T_relative 和 fallback 伪值。

**修复建议**：第 632 行改为：
```python
"T_relative": T_s / T_base if (status_base == "ok" and T_base > 0) else float("nan"),
```

---

### S4：隐含假设 A2（cal/test 熵分布相似）从未验证

**攻击维度**：隐含假设

**问题描述**：

A2（docstring 第 29-30 行）：
> 不确定度（熵）五分位定义的箱边界可从 cal 迁移到 test
> （即 cal 与 test 的不确定度分布相似——OOD 下可能违反，列为局限）

脚本在 cal 上计算熵并定义 bin 边界（`fit_binned_T` 第 364-365 行），然后应用到 test（`apply_binned_T` 第 406-407 行）。

**但脚本从未验证 A2**：
- 计算了 `cal_ent`（第 480 行）但未与 `id_ent` 或 `ood_ent` 比较
- 无 KS 检验、无直方图对比、无分位数比较
- 无 cal/test 熵分布的任何统计距离度量

**边界失效**：如果 OOD test 的熵分布与 cal 差异很大（模型对 OOD 不确定度高），cal 定义的 quintile 边界可能将 90% 的 OOD 样本放入最后一个 bin，其余 4 个 bin 几乎为空。此时：
- binned-T 退化为"最后一个 bin 的 T + 4 个空 bin"
- per-bin Brier reliability 只有 1 个 bin 有有效值
- "5 bin 探索性评估"实际变成"1 bin 评估"

**影响**：Binned-T 的 OOD 结果可能完全由 bin 边界漂移驱动，而非 T 异质性。P1（docstring 第 58 行）列出了这个攻击点但**代码中无任何检测或缓解**。

**严重程度**：**严重**——A2 是 binned-T OOD 评估的关键假设，未验证则 OOD 结果不可信。

**修复建议**：在 `process_one` 中添加 cal vs test 熵分布比较：
```python
from scipy.stats import ks_2samp
ks_stat, ks_p = ks_2samp(cal_ent, ood_ent)
dist_record["entropy_ks_stat"] = ks_stat
dist_record["entropy_ks_pvalue"] = ks_p
```

---

### S5：逻辑断链 R1→R2——T 变异 → OOD 难度未测试相关性

**攻击维度**：逻辑断链

**问题描述**：

M1 主张（docstring 第 14 行）：
> 跨方向变异 → OOD 难度是否反映在 T 上

推理链条 R1→R2（docstring 第 48-49 行）：
> R1. 加载 60 checkpoint → 在 cal 上拟合 T_global → 得 T 分布
> R2. T 分布的跨方向/架构/种子变异 → 揭示 T 的结构化变异源

脚本实现了 R1（拟合 T_global）和 R2 的描述统计（跨方向/架构/种子的 mean/std），但**R2 的推断跳跃未测试**：

- "T 变异 → OOD 难度反映在 T 上"需要 **T 与 OOD 难度指标的相关性**
- 脚本从未计算 T 与 OOD accuracy drop、OOD ECE、OOD Brier reliability 的相关系数
- `dist_record` 有 `ood_rel_raw` 和 `ood_rel_global_T`（OOD Brier reliability）但无 OOD accuracy
- 无 Spearman/Pearson 相关性、无回归、无任何关联度量

**逻辑断链**：从"T 在不同方向有不同均值"到"T 反映 OOD 难度"需要证明 T 与难度指标相关。T 可能因模型容量、训练噪声、标签分布等非难度因素变异。

**反例**：假设 6 个方向的 OOD 难度相同（accuracy drop 均为 5%），但 T 因源域类别分布不同而变异（ptbxl 5 类 vs cpsc 4 类）。脚本会报告"T 跨方向变异"，研究者可能误读为"OOD 难度不同导致 T 不同"，但实际原因是类别数差异。

**影响**：M1 的"OOD 难度反映在 T 上"是**断言而非实证**。

**严重程度**：**严重**——M1 的核心推断无数据支撑。

---

### S6：逻辑断链 R5→R6——T(shift) → shift-invariance 无统计检验

**攻击维度**：逻辑断链

**问题描述**：

M3 主张（docstring 第 22-23 行）：
> 若 T 随 shift 单调变化 → T 是 shift 的可辨识函数
> 若 T 近似不变 → T 是 shift-invariant

推理链条 R5→R6（docstring 第 52-53 行）：
> R5. 对有 l2_shift 的实验，每档 shift 重新拟合 T → T(shift) 曲线
> R6. T(shift) 的单调性/不变性 → 判断 T 是否 shift-invariant

脚本实现了 R5（计算 T(shift)）但 **R6 的判断完全缺失**：
- 无单调性检验（如 shift 幅度与 T 的 Spearman 相关）
- 无"近似不变"阈值（什么 std(T(shift)) 算"invariant"？）
- 无 T(shift) = T_base 的统计检验（如 bootstrap CI、等价性检验）
- 控制台汇总（第 958-966 行）只报告每档 shift 的 mean/std——需人工目测

**影响**：M3 的"shift-invariant"判断**无客观标准**，完全依赖研究者主观解读 mean/std 表。

**严重程度**：**严重**——M3 的结论不可复现（不同研究者可能从同一 T(shift) 表得出不同结论）。

---

### S7：brier_reliability_top 语义偏移——top-label vs full multiclass Brier reliability

**攻击维度**：语义偏移

**问题描述**：

`brier_reliability_top`（第 166-175 行）：
```python
def brier_reliability_top(probs, labels):
    mp = _maxprob(probs)       # max probability
    cm = _correct_mask(probs, labels)  # argmax == label
    _, rel, _, _ = brier_parts(mp, cm)
    return float(rel)
```

这将多分类问题**降维为二分类**：预测值 = max prob，标签 = 是否正确。然后调用 `brier_parts`（10 等宽分箱）计算二分类 Brier reliability。

**但 R5 方案讨论的 Brier reliability 是多分类 Murphy 分解**（R5 第 358 行）：
> 报告分箱温度 vs 单一 T 的 Brier reliability 改善对比

多分类 Brier reliability 应基于全部 K 个类别的概率向量，而非仅 top-label。两者的区别：
- **Top-label**：只评估"模型最自信的类别是否正确"的校准
- **Full multiclass**：评估所有类别的概率校准（如次高概率是否校准）

**反例**：温度缩放可能改善 top-label 校准（max prob 更接近正确率）但恶化次级类别校准（次高概率被过度平滑）。Top-label Brier reliability 改善但 full multiclass Brier reliability 恶化。

**影响**：脚本测量的 top-label Brier reliability 可能与论文讨论的多分类 Brier reliability 不一致，导致结论不可推广。

**严重程度**：**严重**——评估指标与论文叙事语义不匹配。

---

### S8：docstring 说"8+档"但实际 13 档——文档与代码不一致

**攻击维度**：自相矛盾

**问题描述**：

- Docstring 第 8 行：`偏移敏感度：T 值随 L2 prior shift（8+档）的变化趋势`
- `get_l2_shifts()`（l2_shifts.py 第 147-177 行）返回 **13 档**：降采样 2 + 导联 4 + 噪声 5 + 增益 2 = 13
- l2_shifts.py docstring 第 3 行明确写：`13 档 = 降采样 2 + 导联 4 + 噪声 5 + 增益 2`

此外，docstring 说"prior shift"但 l2_shifts.py 说"L2 移位阶梯变换"——降采样和导联置零是**协变量漂移**（输入空间变换），噪声注入也是协变量漂移，增益是协变量漂移。**没有一档是真正的 prior shift**（标签分布漂移）。

A4（docstring 第 32-33 行）承认：`严格说 L2 shift 是协变量漂移而非纯 prior shift`，但 docstring 第 8 行仍写"prior shift"。

**影响**：文档误导 shift 的数量和性质。研究者可能以为有 8 档 prior shift，实际有 13 档协变量漂移。

**严重程度**：**严重**——文档与代码不一致，影响对结果的解读。

---

### S9：binned-T insufficient samples 时 T=1.0 偏向 global-T

**攻击维度**：隐含假设 + 量级错误

**问题描述**：

`fit_binned_T`（第 379-382 行）：
```python
if n_b < n_classes * 2:  # 样本不足，跳过拟合
    rec["T_bin"] = 1.0
    rec["status"] = f"insufficient_samples(n={n_b})"
```

样本不足时 T_bin = 1.0（identity，不校准）。

**偏差机制**：如果某些 bin 样本不足（小数据集或 OOD 下 bin 漂移），binned-T 在这些 bin 退化为 identity。而 global-T 在全部样本上拟合，通常有足够样本。

- 如果 global-T ≠ 1.0（有校准效果），binned-T 在 insufficient bin 上 = 1.0（无校准）
- binned-T 的整体效果 = 部分 bin 有校准 + 部分 bin 无校准
- global-T 的整体效果 = 全部 bin 有统一校准
- **binned-T 被 insufficient bin 拖累**，可能显得比 global-T 差

**反例**：5 个 bin 中 bin 4-5 样本不足（n < 10），T_bin = 1.0。global-T = 1.5。bin 4-5 的 binned-T = 1.0（无校准），global-T = 1.5（有校准）。bin 4-5 的 `id_delta_binned_vs_global = rel(1.0) - rel(1.5) > 0`（binned 更差）。**但这是因为 binned-T 无法拟合，不是因为 T 是常数**。

**影响**：Binned-T vs global-T 比较被 insufficient bin 系统性偏向 global-T，可能掩盖 binned-T 的真实效果。

**严重程度**：**严重**——比较结果有系统偏差。

---

### S10：偏移敏感度不用缓存——780 次模型前向无法加速

**攻击维度**：量级错误（性能）

**问题描述**：

`process_shift_sensitivity`（第 590 行）总是重新加载模型：
```python
model, _, _, num_classes = load_checkpoint(...)
```

即使 `--cache-dir` 已提供，缓存只存储 cal/id/ood probs（第 469-473 行），不存储 shifted probs。偏移敏感度始终需要模型前向。

**量级**：60 实验 × 13 shifts = 780 次 cal 集前向。`shifted_probs_labels`（第 292-312 行）逐样本循环（无 batch），每次 ~2000 样本。总计 780 × 2000 = **1,560,000 次单样本前向**。

**影响**：`--cache-dir` 的加速效果对偏移敏感度无效。重跑时分布分析和 binned 评估可加速（缓存命中），但偏移敏感度始终全量重算。

**严重程度**：**严重**（性能）——重跑时间不可接受，可能迫使研究者跳过偏移敏感度（`--skip-shift-sensitivity`）。

---

## 3. 轻微攻击

### M1：id_ent/ood_ent 在 per-bin 循环内重复计算（性能 bug）

**位置**：第 516-517 行
```python
for rec in bin_records:
    b = rec["bin_idx"]
    id_ent = predictive_entropy(id_probs)    # 不依赖 b
    ood_ent = predictive_entropy(ood_probs)  # 不依赖 b
```

`id_ent` 和 `ood_ent` 在 5 次循环中重复计算，应移到循环外。**5 倍冗余计算**。

---

### M2：N_BINS 全局可变——多次调用 main() 状态泄漏

**位置**：第 809 行 `global N_BINS`，第 830 行 `N_BINS = args.n_bins`

`fit_binned_T` 默认参数 `n_bins=N_BINS`（第 355 行）在函数定义时绑定，但 Python 默认参数在定义时求值——**实际上 `N_BINS` 的默认值在函数定义时已固定为 5**，后续 `global N_BINS` 修改不影响 `fit_binned_T` 的默认值。

**实际 bug**：`--n-bins 7` 修改了全局 `N_BINS`，但 `fit_binned_T` 调用时显式传 `n_bins=N_BINS`（第 506 行），所以实际生效。但如果其他代码调用 `fit_binned_T()` 不传参数，会用定义时的默认值 5，而非命令行指定的值。**设计脆弱**。

---

### M3：CSV 无 provenance 元数据——无法追溯生成参数

三个 CSV 文件均无：生成时间戳、脚本版本/git hash、N_BINS、T_MIN/T_MAX、shift 数量。**可复现性受损**。

---

### M4：探索性标签未在 CSV 中强制标记

B1 说"探索性评估，不进入主检验"，但 CSV 无 "exploratory" 标记列。下游脚本可能误用为 confirmatory。**方法论约束未强制**。

---

### M5：5 quintile 无箱数敏感性分析

B2 列为局限但未实现。`--n-bins` 参数存在但无敏感性循环（如同时跑 3/5/7/10 箱对比）。**结果可能依赖箱数选择**。

---

### M6：per-bin 小样本 Brier reliability 高方差

Per-bin Brier reliability 在 ~400 样本上用 10 等宽分箱，每 max-prob bin ~40 样本。Brier reliability 估计方差高。**per-bin 比较噪声大**。

---

### M7：T_relative 无 clipping——极端值主导汇总

`T_relative = T_s / T_base`（第 632 行）可达 10000（T_s=100, T_base=0.01）。无 clipping 或 log 变换。**极端值可能主导 mean/std**。

---

### M8：NaN 熵静默入 bin 0

`np.digitize(NaN, edges[1:-1])` 返回 0。如果 probs 含 NaN（模型异常输出），entropy 为 NaN，静默分入 bin 0。**bin 0 可能被污染**。

---

### M9：退化熵 fallback 不处理全同值

`quintile_edges` fallback（第 193 行）：`np.linspace(v, v + 1e-9, n_bins + 1)`。全同值时所有样本入最后一个 bin，其余 bin 空。**退化情况未正确处理**。

---

### M10：binned_records 的 fit_status 不反映 global T 失败

第 563 行 `"fit_status": rec["status"]` 是 per-bin 状态。如果 global T 拟合失败（T_global=1.0），per-bin 的 `id_rel_global_T`（第 553 行）用 fallback T=1.0，但 `fit_status` 不反映此问题。**读者可能误认为比较有效**。

---

### M11：discover_experiments 不验证 checkpoint 完整性

第 803 行只检查 `ckpt.exists()`，不检查可加载性。损坏的 checkpoint 导致 `process_one` 失败，被 try/except 捕获（第 868 行），但失败只打印到控制台，不写入失败 CSV。**静默失败不可追溯**。

---

### M12：shifted_probs_labels 逐样本前向——无 batch

第 303 行 `for i in range(n):` 逐样本循环，无 DataLoader/batch。780 × ~2000 = 1.56M 次单样本前向。**严重性能问题**（与 S10 同源）。

---

## 4. 七维度攻击覆盖确认

| 攻击维度 | 覆盖情况 | 具体攻击点 |
|----------|----------|------------|
| **反例构造** | ✓ | F1（bin 样本不均导致 per-bin 均值与全局差异符号相反）、S1（cal-time vs test-time shift）、S9（insufficient bin 偏向 global-T） |
| **逻辑断链** | ✓ | F1（per-bin → 全局缺失）、S5（T 变异 → OOD 难度无相关性）、S6（T(shift) → shift-invariance 无检验） |
| **隐含假设** | ✓ | S1（cal-time shift 代理 test-time shift）、S4（A2 cal/test 熵相似未验证）、S9（insufficient bin 的 T=1.0 假设） |
| **边界失效** | ✓ | S3（T_base=1.0 fallback）、M8（NaN 熵入 bin 0）、M9（退化熵全入末 bin）、M11（损坏 checkpoint 静默失败） |
| **自相矛盾** | ✓ | F2（CSV 字段语义矛盾）、S8（docstring "8+档" vs 代码 13 档）、F1（计算了 binned probs 但不计算 binned Brier reliability） |
| **量级错误** | ✓ | S2（per-bin 均值 ≠ 全局差异）、S10（780 次前向无缓存）、M6（per-bin 小样本高方差）、M7（T_relative 极端值）、M12（逐样本前向性能） |
| **语义偏移** | ✓ | S1（cal-time vs test-time shift 语义）、S7（top-label vs multiclass Brier reliability）、F2（CSV 字段语义偏移）、S8（"prior shift" vs 协变量漂移） |

**全部 7 个维度均已尝试攻击，每个维度均找到有效攻击点。**

---

## 5. 攻击点优先级排序与修复建议

### 致命（必须修复才能发布）

| 编号 | 攻击 | 修复建议 | 工时 |
|------|------|----------|------|
| F1 | 全局 binned-T Brier reliability 缺失 | 在 `process_one` 中添加 `brier_reliability_top(id_probs_binned, id_labels)` 和 OOD 对应，加入 `dist_record` | 0.5h |
| F2 | DIST_STATS 行字段语义滥用 | 为汇总统计量使用专用字段名或单独 CSV | 1h |

### 严重（应修复，否则结论不可靠）

| 编号 | 攻击 | 修复建议 | 工时 |
|------|------|----------|------|
| S1 | 偏移敏感度 cal-time vs test-time 语义错位 | 增加 test-time shift 评估：shift 施加到 test → 用原 T 校准 → 评估 Brier reliability 退化 | 2h |
| S2 | per-bin 均值 ≠ 全局差异 | 依赖 F1 修复，用全局 binned-T Brier reliability 做比较 | 0h（F1 修复后自动解决） |
| S3 | T_base 失败时 T_relative = T_s | 第 632 行加 `status_base == "ok"` 条件 | 0.1h |
| S4 | A2 cal/test 熵分布未验证 | 添加 KS 检验或 Wasserstein 距离，写入 dist_record | 0.5h |
| S5 | T 变异 → OOD 难度无相关性 | 计算 T 与 OOD accuracy drop / ECE 的 Spearman 相关 | 0.5h |
| S6 | T(shift) → shift-invariance 无检验 | 添加 T(shift) 的 bootstrap CI 和等价性检验 | 1h |
| S7 | top-label vs multiclass Brier reliability | 添加 full multiclass Brier reliability（或明确声明只评估 top-label） | 1h |
| S8 | docstring "8+档" vs 13 档 | 更新 docstring 为"13 档协变量漂移" | 0.1h |
| S9 | insufficient bin T=1.0 偏向 global-T | 标记 insufficient bin 并在汇总中排除，或用 global-T 填充 | 0.5h |
| S10 | 偏移敏感度无缓存 | 缓存 shifted probs 或支持增量重算 | 2h |

### 轻微（建议修复）

| 编号 | 攻击 | 修复建议 | 工时 |
|------|------|----------|------|
| M1 | id_ent/ood_ent 循环内重计算 | 移到循环外 | 0.1h |
| M2 | N_BINS 全局可变 | 改为参数传递 | 0.2h |
| M3 | CSV 无 provenance | 添加 metadata 行或 sidecar JSON | 0.3h |
| M4 | 探索性标签未强制 | CSV 加 `analysis_type` 列 | 0.1h |
| M5 | 无箱数敏感性 | 添加 `--sensitivity-bins` 选项 | 1h |
| M6 | per-bin 小样本高方差 | 报告 per-bin Brier reliability 的 bootstrap CI | 0.5h |
| M7 | T_relative 无 clipping | clip 到 [0.01, 100] 或用 log 变换 | 0.1h |
| M8 | NaN 熵入 bin 0 | 检查 NaN 并标记 | 0.1h |
| M9 | 退化熵 fallback | 全同值时返回单 bin或报错 | 0.1h |
| M10 | binned fit_status 不反映 global 失败 | 加 `global_fit_status` 列 | 0.1h |
| M11 | checkpoint 完整性未验证 | 写 failure CSV | 0.2h |
| M12 | 逐样本前向无 batch | 改为 batched DataLoader | 0.5h |

**总修复工时估计**：致命 1.5h + 严重 7.8h + 轻微 2.4h ≈ **11.7h**

---

## 6. 对 E4 探索性定位的攻击

### 6.1 探索性标签的效力

B1（docstring 第 39 行）：`探索性评估，不进入主检验`。R5 方案（第 331 行）：`Exploratory——分箱温度的探索性评估，不依赖 H6 成立`。

**攻击**：脚本仅在控制台输出（第 969 行）声明探索性：
```python
print("正方论证声明：本评估为探索性，结果不进入主检验。")
```

但 CSV 文件**无任何探索性标记**。下游脚本（如论文图表生成）读取 CSV 时无法区分探索性 vs confirmatory 结果。如果 E4 的 Brier reliability 结果被误纳入论文主表，则探索性声明无效。

**严重程度**：轻微（M4）——但若下游误用，后果严重。

### 6.2 E4 与 E3 的指标重叠

E3 是 confirmatory 实验（Brier reliability 假设检验），E4 是 exploratory（温度分布）。但 E4 也计算 Brier reliability（第 483-486、522-538 行）——**同一指标在 confirmatory（E3）和 exploratory（E4）中均计算**。

**攻击**：如果 E4 的 Brier reliability 结果与 E3 不一致（因计算方式或子集不同），研究者可能选择性报告更有利的结果。E4 的"探索性"标签为此提供了灵活性——**探索性标签可能成为选择性报告的掩护**。

**严重程度**：轻微——取决于研究者的诚实度，但代码层面无法防范。

### 6.3 外推限制未在代码中体现

E4 的结论外推限制（如 A2 在 OOD 下可能违反、A4 的 L2 shift 非纯 prior shift、5 bin 无敏感性）在 docstring 中列出（B1-B5, P1-P5），但**代码中无任何运行时检查或警告**。

例如：如果 OOD 熵分布与 cal 差异极大（A2 违反），脚本不会警告——它静默输出可能无意义的 binned-T OOD 结果。**外推限制是文档声明，不是代码约束**。

---

## 7. 结论

### 7.1 核心问题

E4 脚本的**工程实现**较为完整（缓存、异常处理、CSV 输出），但在**科学推断**层面存在两个致命缺陷：

1. **F1**：M2 的核心比较（binned-T vs global-T 的全局 Brier reliability）**从未计算**。脚本计算了 per-bin Brier reliability 但 Brier reliability 不可加，per-bin 均值 ≠ 全局差异。控制台汇总的 `mean Δrel` 是误导性指标。

2. **F2**：`summarize_distribution` 的 `DIST_STATS` 行将 T 分布统计量塞入不相关 CSV 字段（`n_cal` 存 T 中位数、`id_rel_raw` 存 T 最大值等），导致同一 CSV 列在不同行有完全不同含义。下游分析会静默出错。

### 7.2 三大主张的可支持性

| 主张 | 代码能否支撑 | 原因 |
|------|-------------|------|
| M1（T 分布揭示变异结构） | **部分** | 描述统计有，但 T 与 OOD 难度的相关性未测试（S5） |
| M2（binned-T 捕捉 T 异质性） | **不能** | 核心比较缺失（F1），per-bin 均值 ≠ 全局差异（S2），insufficient bin 偏差（S9） |
| M3（偏移敏感度刻画 T 稳健性） | **不能** | 语义错位（S1：cal-time vs test-time），无统计检验（S6） |

### 7.3 整体裁决

**E4 脚本在当前状态下不能支撑其三大核心主张 M1-M3 的任何一个**。F1 和 F2 是必须修复的致命问题，S1-S10 是应在发布前修复的严重问题。修复后，E4 可作为**描述性探索性评估**提供 T 分布的汇总统计，但**不能作为 T 异质性或 shift-invariance 的推断依据**——后者需要 F1 的全局比较、S5 的相关性分析、S6 的统计检验。

**正方论证声明中"探索性评估，不进入主检验"的定位是合理的**——鉴于上述攻击，E4 的结果确实不应进入主检验。但当前代码连探索性评估的最低标准（核心比较正确计算、CSV 输出语义一致）都未达到。

---

> **攻击代理声明**：我尝试了全部 7 个攻击维度（反例构造 / 逻辑断链 / 隐含假设 / 边界失效 / 自相矛盾 / 量级错误 / 语义偏移），找到 2 个致命、10 个严重、12 个轻微攻击。E4 脚本在科学推断层面存在实质性缺陷，需修复 F1+F2 后才能作为探索性评估使用。
