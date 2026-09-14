# P0-5 反方攻击报告：全局 binned-T Brier reliability 修复

**攻击对象**：`scripts/run_e4_temperature_analysis.py` 的 P0-5 修复
**攻击代理**：反方挑刺代理（GLM-5.2）
**攻击日期**：2026-09-09
**攻击范围**：7 个指定攻击点 + 全维度补充攻击

---

## 一、攻击维度汇总

| # | 攻击维度 | 攻击点 | 严重程度 | 结论 |
|---|---------|--------|---------|------|
| 1 | 全局计算真实性 | L513-521 是否在整个 test 集上算 | — | **未发现可攻击点**（修复正确） |
| 2 | 常量语义区分 | BRIER_N_BINS=10 vs N_BINS=5 | — | **未发现可攻击点**（区分正确） |
| 3 | Δrel 符号方向 | id_delta_rel_binned_vs_global 方向 | — | **未发现可攻击点**（符号正确） |
| 4 | 控制台汇总 | 是否仍用 per-bin 均值 | — | **未发现可攻击点**（已改用全局） |
| 5 | CSV 新字段完整性 | summary_rows / 失败分支 | 轻微 | 字段完整，但汇总行全 nan（可用性缺陷） |
| 6 | brier_parts 调用 | n_bins 传参 | — | **未发现可攻击点**（传 BRIER_N_BINS=10） |
| 7 | id_probs_binned 来源 | 是否整个 test 集 | — | **未发现可攻击点**（整个 test 集） |
| A | 跨 CSV 字段名冲突 | id_rel_binned_T 同名不同义 | **严重** | 两个 CSV 同名字段语义不同 |
| B | 指标片面性 | 只比 Rel 不比整体 Brier | 严重 | Δrel<0 不保证整体 Brier 更优（A5 局限） |
| C | DIST_STATS 字段滥用 | n_cal 塞 T median | 轻微 | 原有问题，P0-5 未引入也未修复 |
| D | BRIER_N_BINS 不可配置 | 无法做箱数敏感性 | 轻微 | 加剧 B2 局限 |
| E | 内部变量名混淆 | id_rel_global vs id_rel_binned_global | 轻微 | "global" 语义双重含义 |

**致命攻击点：0 个 | 严重攻击点：2 个 | 轻微攻击点：2 个 | 轻微攻击点：2 个**

---

## 二、指定攻击点详细分析（1-7）

### 攻击点 1：全局计算是否真的在整个 test 集上算

**审查位置**：L506-521

```python
# L510-511
id_probs_binned = apply_binned_T(id_probs, T_per_bin, bin_edges)
ood_probs_binned = apply_binned_T(ood_probs, T_per_bin, bin_edges)
# L516-517
id_rel_binned_global = brier_reliability_top(id_probs_binned, id_labels)
ood_rel_binned_global = brier_reliability_top(ood_probs_binned, ood_labels)
```

**数据流追踪**：
- `id_probs` 来源：L447（cache 命中）或 L466（`id_ev["probs"]`，整个 ID test 集前向结果）
- `apply_binned_T`（L400-415）：对 `probs` 每个样本按自身熵分箱，用该箱 T 缩放，返回 `out = probs.copy()` 同形状数组 → **整个 test 集的 binned-T 概率**
- `brier_reliability_top`（L167-176）：接收整个数组，内部 `brier_parts(mp, cm, n_bins=10)` 在整个数组上按 max-prob 等宽分 10 箱计算 reliability

**结论**：`id_probs_binned` 确实是整个 test 集的 binned-T 概率（每个样本用其所在箱的 T 缩放），**不是某个 bin 的子集**。`id_rel_binned_global` 在整个 test 集上一次计算。**该维度未发现可攻击点。**

**反例构造尝试**：假设 test 集有 1000 样本，分 5 箱各 200 样本。`id_probs_binned` 形状 (1000, n_classes)，`brier_reliability_top` 在 1000 样本上计算，非 200。无法构造反例。

---

### 攻击点 2：BRIER_N_BINS=10 vs N_BINS=5 语义区分

**审查位置**：L140-141

```python
N_BINS = 5  # binned temperature 箱数（quintile）
BRIER_N_BINS = 10  # Brier reliability 等宽分箱数（与 calibration.brier_parts 默认一致）
```

**验证 `brier_parts` 默认值**：查阅 `src/utils/calibration.py` L586：
```python
def brier_parts(probs, labels, n_bins: int = 10):
```
默认 `n_bins=10`，与 `BRIER_N_BINS=10` 一致。注释正确。

**语义区分验证**：
- `N_BINS=5`：binned-T 的**干预分箱**——按预测熵 quintile 分 5 箱，每箱拟合一个 T（`fit_binned_T` L356, `apply_binned_T` L400）
- `BRIER_N_BINS=10`：Brier reliability 的**评估分箱**——按 max-prob 等宽分 10 箱，计算 Murphy 分解的 reliability 项（`brier_reliability_top` L175）

两个分箱是**不同维度、不同目的**：前者按不确定度（熵）分箱以施加不同温度，后者按置信度（max-prob）分箱以评估校准。不冲突。

**指标定义变更检查**：`brier_reliability_top` 显式传 `n_bins=BRIER_N_BINS=10`（L175），与 `brier_parts` 默认 10 一致。**未改变 Brier reliability 的指标定义。**

**结论**：**该维度未发现可攻击点。** 语义区分正确，与底层默认一致。

---

### 攻击点 3：Δrel 字段符号方向

**审查位置**：L520-521

```python
dist_record["id_delta_rel_binned_vs_global"] = id_rel_binned_global - id_rel_global
dist_record["ood_delta_rel_binned_vs_global"] = ood_rel_binned_global - ood_rel_global
```

**语义分析**：
- `id_rel_binned_global`：binned-T 的全局 Brier reliability（L516）
- `id_rel_global`：global-T 的全局 Brier reliability（L485: `brier_reliability_top(apply_global_T(id_probs, T_global), id_labels)`）
- Brier reliability 是 Murphy 分解的 reliability 项（`brier_parts` L627: `reliability += n_bin/n * (avg_prob - avg_label)**2`），**越小越校准**

**符号方向**：
- binned-T 更优 → `rel_binned < rel_global` → Δrel < 0
- binned-T 更差 → `rel_binned > rel_global` → Δrel > 0

**控制台一致性**（L980）：
```python
print(f"  mean Δrel = {np.mean(id_delta_global):+.6f}  (负=binned 更优)")
```
注释"负=binned 更优"与 Δrel = binned - global 的符号一致。✓

**结论**：**该维度未发现可攻击点。** 符号方向正确，Δrel = binned - global，负值表示 binned-T 校准更好。

---

### 攻击点 4：控制台汇总是否仍用 per-bin 均值

**审查位置**：L974-989

```python
id_delta_global = [r.get("id_delta_rel_binned_vs_global", float("nan")) for r in all_dist
                   if np.isfinite(r.get("id_delta_rel_binned_vs_global", float("nan")))]
...
print(f"\nBinned vs Global Brier reliability (ID, 全局, n={len(id_delta_global)}):")
print(f"  mean Δrel = {np.mean(id_delta_global):+.6f}  (负=binned 更优)")
```

**数据流追踪**：
- `all_dist` 的每个元素是 `dist_record`（L489-521）
- `id_delta_rel_binned_vs_global` 在 L520 赋值：`id_rel_binned_global - id_rel_global`，两者都是**全局** Brier reliability（L516, L485）
- 控制台汇总对这些全局 Δrel 取 mean/median，**非 per-bin 均值**

**per-bin 均值的定义**：若用 `binned_records`（L523-575）的 `id_delta_binned_vs_global`（L567，箱内 Δrel）取平均，才是 per-bin 均值。控制台**没有**这么做。

**边界检查**：
- 失败实验的 `id_delta_rel_binned_vs_global = nan`（L903），被 `np.isfinite` 过滤 ✓
- 全部失败时 `id_delta_global` 为空，`if id_delta_global:` 为 False，不打印 ✓

**结论**：**该维度未发现可攻击点。** 控制台汇总确实用全局 Δrel，非 per-bin 均值。

---

### 攻击点 5：CSV 新字段完整性

**审查位置**：`write_dist_csv` fieldnames（L782-791）、`summarize_distribution`（L669-764）、失败分支（L895-907）

**4 个新字段**：`id_rel_binned_T`, `ood_rel_binned_T`, `id_delta_rel_binned_vs_global`, `ood_delta_rel_binned_vs_global`

| 位置 | id_rel_binned_T | ood_rel_binned_T | id_delta_rel_binned_vs_global | ood_delta_rel_binned_vs_global |
|------|-----------------|------------------|-------------------------------|--------------------------------|
| fieldnames (L788-790) | ✓ | ✓ | ✓ | ✓ |
| dist_record (L518-521) | ✓ 全局值 | ✓ 全局值 | ✓ 全局值 | ✓ 全局值 |
| 全局汇总 (L692-698) | ✓ nan | ✓ nan | ✓ nan | ✓ nan |
| 跨方向汇总 (L715-718) | ✓ nan | ✓ nan | ✓ nan | ✓ nan |
| 跨架构汇总 (L735-738) | ✓ nan | ✓ nan | ✓ nan | ✓ nan |
| DIST_STATS (L755-761) | ✓ nan | ✓ nan | ✓ nan | ✓ nan |
| 失败分支 (L903-906) | ✓ nan | ✓ nan | ✓ nan | ✓ nan |

**字段完整性**：所有位置都添加了新字段。✓

**攻击点（轻微）**：所有 `summary_rows` 的新字段都是 `float("nan")`。这意味着 **CSV 的汇总行不提供 binned-T 的汇总统计**（mean Δrel、binned 更优比例等）。用户若只读 CSV 做自动化分析，无法获得 binned-T 的汇总——必须从控制台输出读取，或自行从 dist_records 过滤汇总行后计算。

**反例**：下游脚本 `pd.read_csv("temperature_distribution_analysis.csv")` 后对 `arch=="SUMMARY"` 行取 `id_delta_rel_binned_vs_global`，得到 nan，无法获得平均改善量。必须过滤 `fit_status=="ok"` 的实验行自行计算。

**结论**：字段完整，但**汇总行新字段全 nan 是可用性缺陷**（轻微）。控制台汇总弥补了这一缺陷，但 CSV 与控制台信息不对称。

---

### 攻击点 6：brier_parts 调用的 n_bins

**审查位置**：`brier_reliability_top` L175

```python
_, rel, _, _ = brier_parts(mp, cm, n_bins=BRIER_N_BINS)
```

显式传 `n_bins=BRIER_N_BINS=10`。全局计算（L516-517）和箱级计算（L534-547）都通过 `brier_reliability_top` 间接传 10。

**精度攻击尝试**：10 箱等宽分箱，若 test 集较小（如 OOD 仅几百样本），每箱约几十样本，reliability 估计方差较大。但这是统计精度问题，非 bug。且 `brier_parts` 默认就是 10 箱，与项目其他脚本一致。

**结论**：**该维度未发现可攻击点。** 全局 Brier reliability 用 10 箱计算，与 `brier_parts` 默认一致。

---

### 攻击点 7：id_probs_binned 变量来源

**审查位置**：L510 赋值，L516 全局计算，L536 箱级使用

```python
# L510
id_probs_binned = apply_binned_T(id_probs, T_per_bin, bin_edges)
# L516（bin 循环之前）
id_rel_binned_global = brier_reliability_top(id_probs_binned, id_labels)
# L536（bin 循环内，只读不写）
id_rel_binned_b = brier_reliability_top(id_probs_binned[id_bin_mask], id_labels[id_bin_mask])
```

**数据流追踪**：
- L510：`id_probs_binned` 赋值为整个 test 集的 binned-T 概率（`apply_binned_T` 返回 `probs.copy()` 同形状）
- L516：在 bin 循环**之前**，用整个 `id_probs_binned` 计算全局 reliability
- L536：在 bin 循环**内**，用 `id_probs_binned[id_bin_mask]`（子集索引，**不修改原数组**）计算箱级 reliability

**关键**：`id_probs_binned` 在 L510 赋值后**从未被重新赋值**。L536 是只读索引操作。全局计算 L516 用的是完整的 `id_probs_binned`。

**反例构造尝试**：假设 bin 循环内修改了 `id_probs_binned`（如 `id_probs_binned = ...`），则 L516 的全局计算会受影响。但代码中无此修改。无法构造反例。

**结论**：**该维度未发现可攻击点。** `id_probs_binned` 是整个 test 集的 binned-T 概率，未被覆盖。

---

## 三、补充攻击点（全维度扫描）

### 攻击点 A（严重）：跨 CSV 字段名 `id_rel_binned_T` 同名不同义

**审查位置**：
- `temperature_distribution_analysis.csv` 的 `id_rel_binned_T`（L788 fieldname, L518 赋值）
- `binned_temperature_exploratory.csv` 的 `id_rel_binned_T`（L801 fieldname, L563 赋值）

**攻击论证**：

两个 CSV 都有 `id_rel_binned_T` 字段，但**语义完全不同**：

| CSV | 来源代码 | 值的语义 | 粒度 |
|-----|---------|---------|------|
| temperature_distribution_analysis.csv | L518: `dist_record["id_rel_binned_T"] = id_rel_binned_global` | **全局** binned-T Brier reliability（整个 test 集） | 每实验 1 行 |
| binned_temperature_exploratory.csv | L563: `"id_rel_binned_T": id_rel_binned_b` | **箱级** binned-T Brier reliability（箱内子集） | 每实验 5 行 |

**具体反例**：
- 实验 `ptbxl_chapman/resnet1d/seed42`，test 集 1000 样本，分 5 箱各 200 样本
- temperature_distribution_analysis.csv 的 `id_rel_binned_T` = 在 1000 样本上计算的 reliability（全局）
- binned_temperature_exploratory.csv 的 `id_rel_binned_T`（bin_idx=0）= 在 200 样本上计算的 reliability（箱级）
- **同名字段，数值不同，语义不同**

**危害**：
1. 下游脚本按字段名 `id_rel_binned_T` 读取两个 CSV 并比较，会得到错误结论
2. 用户读 binned_temperature_exploratory.csv 的 `id_rel_binned_T`，可能误以为是全局值（因 temperature_distribution_analysis.csv 的同名字段是全局的）
3. 文档 docstring（L76-79）描述 binned CSV 的字段为 `brier_rel_binned`，与实际字段名 `id_rel_binned_T` 不一致，加剧混淆

**同理**：`ood_rel_binned_T` 也存在同名冲突（L790 vs L569）。

**修复建议**：binned_temperature_exploratory.csv 的箱级字段应命名为 `id_rel_binned_T_bin` 或 `id_rel_binned_T_within_bin`，与全局字段区分。

**严重程度**：**严重**（非致命，因两 CSV 粒度不同不太可能直接 join；但字段名冲突会误导人工阅读和自动化分析）

---

### 攻击点 B（严重）：只比较 Brier reliability 项，不比较整体 Brier score

**审查位置**：L520 Δrel 计算，L980 控制台"负=binned 更优"

**攻击论证**：

Murphy 分解（`brier_parts` L589）：`Brier = Reliability - Resolution + Uncertainty`

正方的 Δrel 只比较 **Reliability 项**：
```python
Δrel = rel_binned - rel_global
```

但 **Δrel < 0（reliability 更小）不保证整体 Brier score 更小**。因为 binned-T 可能同时降低 Resolution（区分能力）：

```
Brier_binned = Rel_binned - Res_binned + Unc
Brier_global = Rel_global - Res_global + Unc
Brier_binned - Brier_global = (Rel_binned - Rel_global) - (Res_binned - Res_global)
                             = Δrel - Δresolution
```

若 binned-T 把高置信度样本的 T 拉大（平滑），可能同时降低 Rel 和 Res。当 `Δresolution < Δrel < 0` 时，Δrel < 0（reliability 改善）但整体 Brier 反而增大（更差）。

**具体反例**：
- global-T: Rel=0.05, Res=0.15, Unc=0.25 → Brier=0.15
- binned-T: Rel=0.03（改善）, Res=0.10（下降）, Unc=0.25 → Brier=0.18（更差）
- Δrel = 0.03 - 0.05 = -0.02 < 0 → 控制台报告"binned 更优"
- 但实际 Brier 从 0.15 恶化到 0.18 → **binned 更差**

**正方辩护**：A5 假设声明"Brier reliability 是 binned-T 评估的合理指标"。这是**显式假设**，非隐含。

**攻击定性**：此攻击针对 **A5 假设**，非 P0-5 修复本身引入的 bug。P0-5 修复正确计算了全局 reliability，但**指标选择（只看 Rel 不看整体 Brier）可能误导结论**。正方应同时报告 Δ Brier（整体）作为稳健性检查。

**严重程度**：**严重**（结论可能被指标选择误导，但正方已显式声明 A5）

---

### 攻击点 C（轻微）：DIST_STATS 行字段滥用

**审查位置**：L742-762

```python
summary_rows.append({
    "pair": "ALL", "arch": "DIST_STATS", "seed": -1,
    ...
    "n_cal": int(np.median(Ts)),          # n_cal 字段塞 T 的 median
    "n_id": float(np.percentile(Ts, 25)), # n_id 字段塞 T 的 Q25
    "n_ood": float(np.percentile(Ts, 75)),# n_ood 字段塞 T 的 Q75
    "id_rel_raw": float(Ts.max()),        # id_rel_raw 字段塞 T 的 max
    ...
})
```

**攻击论证**：DIST_STATS 行把 T 分布的统计量塞进 `n_cal`/`n_id`/`n_ood`/`id_rel_raw` 等字段。`n_cal` 语义应为样本数，这里塞的是 T 的 median。下游脚本按字段名解析会误读。

**与 P0-5 的关系**：这是**原有问题**，P0-5 未引入也未修复。但 P0-5 新增的字段（`id_rel_binned_T` 等）在 DIST_STATS 行是 nan，与旧字段的滥用风格**不一致**——旧字段塞 T 统计量，新字段是 nan。若正方想保持"复用字段塞分布统计量"的风格，新字段也应塞 T 统计量；若想干净，旧字段也应改 nan。当前是**混合状态**。

**严重程度**：轻微（原有问题，P0-5 未加剧，但风格不一致暴露了修复的不彻底性）

---

### 攻击点 D（轻微）：BRIER_N_BINS 不可配置，无法做箱数敏感性

**审查位置**：L141 `BRIER_N_BINS = 10`（模块级常量），L834-855 `N_BINS` 可通过 `--n-bins` 配置但 `BRIER_N_BINS` 不可

**攻击论证**：
- `N_BINS` 有 `global N_BINS` 声明（L834）和 `--n-bins` 参数（L845-846, L855），可配置
- `BRIER_N_BINS` 无 `global` 声明，无命令行参数，固定为 10

用户无法通过命令行做 Brier reliability 的箱数敏感性分析（如 5/10/15 箱对比）。必须改源码。

**与正方声明的关联**：docstring L40 (B2) 承认"5 箱 quintile 是约定选择，未做箱数敏感性（3/7/10 箱）——列为局限"。`BRIER_N_BINS` 不可配置**加剧了 B2 局限**——连 Brier reliability 的箱数敏感性也无法做。

**严重程度**：轻微（可用性/可复现性缺陷，非正确性 bug）

---

### 攻击点 E（轻微）：内部变量名 "global" 语义双重含义

**审查位置**：
- L485: `id_rel_global = brier_reliability_top(apply_global_T(id_probs, T_global), id_labels)` — "global" 指 **global-T**（单一温度）
- L516: `id_rel_binned_global = brier_reliability_top(id_probs_binned, id_labels)` — "global" 指 **全局计算**（整个 test 集）

**攻击论证**：两个变量的 "global" 语义不同：
- `id_rel_global`：global-T（单一 T）的 Brier reliability
- `id_rel_binned_global`：binned-T（分箱 T）的**全局** Brier reliability

读者可能误读 `id_rel_binned_global` 为"binned-T 的 global-T 版本"（无意义）或"global 的 binned 版本"（混淆）。

**缓解**：CSV 字段名清晰——`id_rel_global_T`（L499，global-T 的 rel）和 `id_rel_binned_T`（L518，binned-T 的 rel），无 "global" 歧义。问题仅在内部变量名。

**严重程度**：轻微（可读性问题，不影响正确性）

---

## 四、边界失效扫描

| 边界情况 | 分析 | 是否崩溃 |
|---------|------|---------|
| test 集为空 | `id_probs` 形状 (0, n_classes)，`brier_reliability_top` → `brier_parts` 中 `n=0`，`labels.mean()` 除零 | **潜在崩溃**（但 `brier_parts` L611 `base_rate = labels.mean()` 对空数组返回 nan，不抛异常；L620 `mask.sum()==0` 跳过空箱，reliability=0.0）→ 不崩溃，但 reliability=0.0 误报"完美校准" |
| 单样本 test | `brier_parts` 10 箱只有 1 箱非空，reliability 基于单点 | 估计方差极大，但不出错 |
| 所有样本同一箱 | `apply_binned_T` 其他箱 mask 全 False 跳过，仅一箱缩放 | 正常工作 |
| T_per_bin 全为 1.0 | `apply_temperature(probs, 1.0)` = probs（identity） | binned-T = raw，Δrel = rel_raw - rel_global，正常 |
| 全部实验失败 | `all_dist` 全为失败分支记录，`id_delta_global` 过滤 nan 后为空 | `if id_delta_global:` 为 False，不打印汇总，正常 |
| BRIER_N_BINS > 样本数 | 10 箱多数空，`brier_parts` 跳过空箱 | reliability 基于少数非空箱，方差大但不崩溃 |

**边界攻击结论**：空 test 集时 reliability=0.0 误报"完美校准"是**潜在误导**，但这是 `brier_parts` 的固有行为，非 P0-5 引入。P0-5 修复在边界情况下不崩溃。

---

## 五、量级错误扫描

**正方声明**（L515）："per-bin 均值 ≠ 全局 Brier reliability（Brier reliability 是加权非线性，不可加）"

**数学验证**：

Brier reliability = Σ_b (n_b/n) · (avg_p_b - avg_y_b)²

per-bin 均值（按 binned-T 的 5 箱）= (1/5) Σ_{k=1}^{5} Σ_{j=1}^{10} (n_{k,j}/n_k) · (avg_p_{k,j} - avg_y_{k,j})²

全局 = Σ_{k=1}^{5} Σ_{j=1}^{10} (n_{k,j}/n) · (avg_p_{k,j} - avg_y_{k,j})²

差异在权重：per-bin 均值用 `1/5 · n_{k,j}/n_k`，全局用 `n_{k,j}/n`。当各 binned-T 箱样本数不均（n_k ≠ n/5）时，两者**确实不同**。

**结论**：正方的数学声明**正确**。per-bin 均值 ≠ 全局 Brier reliability。修复用全局计算是正确的。**该维度未发现量级错误。**

---

## 六、自相矛盾扫描

**检查**：dist_record 的 `id_rel_binned_T`（全局，L518）与 binned_records 的 `id_rel_binned_T`（箱级，L563）是否在同一实验中矛盾？

**分析**：两者度量不同对象（全局校准 vs 箱内校准），不矛盾。但**同名字段不同值**（攻击点 A）会造成**语义矛盾**——读者期望同名字段同语义。

**结论**：无逻辑矛盾，但存在**命名矛盾**（攻击点 A）。

---

## 七、语义偏移扫描

**检查**：修复过程中是否有概念定义被悄悄替换？

**分析**：
- "全局 binned-T Brier reliability" 的定义在 L513-515 注释中明确：在整个 test 集上一次计算
- 实现与定义一致（L516-517）
- 控制台汇总（L971-973）重复了该定义，与实现一致

**未发现语义偏移。** 修复的"全局"语义从注释到实现到汇总保持一致。

---

## 八、攻击报告总结

### 致命攻击点：0 个

P0-5 修复的**核心逻辑正确**：全局 binned-T Brier reliability 确实在整个 test 集上计算，非 per-bin 均值。7 个指定攻击点中 6 个未发现可攻击点。

### 严重攻击点：2 个

1. **攻击点 A**：跨 CSV 字段名 `id_rel_binned_T`/`ood_rel_binned_T` 同名不同义（temperature_distribution_analysis.csv 是全局，binned_temperature_exploratory.csv 是箱级）。下游分析易混淆。**建议**：箱级字段加 `_bin` 后缀。

2. **攻击点 B**：只比较 Brier reliability 项，不比较整体 Brier score。Δrel < 0 不保证整体 Brier 更优（Resolution 可能同时下降）。正方已显式声明 A5 假设，但**应补充 Δ Brier（整体）作为稳健性检查**，否则"binned 更优"的结论可能被指标选择误导。

### 轻微/轻微攻击点：4 个

3. **攻击点 C**：DIST_STATS 行字段滥用（n_cal 塞 T median）——原有问题，P0-5 新字段全 nan 与旧字段滥用风格不一致。
4. **攻击点 5**：summary_rows 的 binned-T 字段全 nan，CSV 无 binned-T 汇总，自动化分析需过滤或自行计算。
5. **攻击点 D**：BRIER_N_BINS 不可配置，无法做 Brier reliability 箱数敏感性，加剧 B2 局限。
6. **攻击点 E**：内部变量名 `id_rel_global` vs `id_rel_binned_global` 的 "global" 语义双重含义（CSV 字段名已规避）。

### 正方修复正确的部分

- ✅ 全局计算确实在整个 test 集上算（攻击点 1）
- ✅ BRIER_N_BINS=10 vs N_BINS=5 语义区分正确，与 `brier_parts` 默认一致（攻击点 2）
- ✅ Δrel 符号方向正确：binned - global，负=binned 更优（攻击点 3）
- ✅ 控制台汇总已改用全局 Δrel，非 per-bin 均值（攻击点 4）
- ✅ brier_parts 传 n_bins=BRIER_N_BINS=10（攻击点 6）
- ✅ id_probs_binned 是整个 test 集的 binned-T 概率，未被覆盖（攻击点 7）
- ✅ per-bin 均值 ≠ 全局 Brier reliability 的数学声明正确（量级扫描）

### 最终判定

P0-5 修复的**核心目标**（全局 binned-T Brier reliability 从未计算 → 现已正确计算）**已达成**，7 个指定攻击点中 6 个无懈可击。但修复存在 **2 个严重附带问题**（跨 CSV 字段名冲突、指标片面性）和 4 个轻微问题。建议正方在反驳中：
1. 重命名 binned CSV 的箱级 `id_rel_binned_T` → `id_rel_binned_T_bin` 以消除跨 CSV 冲突
2. 补充整体 Brier score 的 Δ 作为稳健性检查，避免"只看 reliability 项"的误导

---

*本报告由反方挑刺代理生成，尝试了全部 7 个攻击维度 + 边界/量级/矛盾/语义偏移扫描。核心修复逻辑无懈可击，但发现 2 个严重附带问题。*
