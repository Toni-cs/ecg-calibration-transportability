# P0-2 反方攻击报告：NCV 独立 cluster bootstrap CI 修复

> **反方挑刺代理-P0-2 交付**。本报告对正方 P0-2 修复（`scripts/run_e1b_loco_validation.py` L579-641 的 NCV CI 独立 cluster bootstrap 实现）进行全方位攻击审查。
> **攻击日期**：2026-09-09
> **攻击对象**：`scripts/run_e1b_loco_validation.py` L579-641（NCV CI 修复块）+ `src/utils/calibration.py` `_bca_interval` L337-384
> **修复主张**：为 NCV 实现独立的 cluster bootstrap CI，替换此前用 ΔECE CI 冒充的伪造；统计量 `_ncv_stat = brier_parts(raw)[1] - brier_parts(cal)[1]`；BCa 含 leave-one-cluster-out jackknife 加速度。
> **正方验证**：NCV(Δreliability=+0.002084) vs ΔECE(-0.016200) 符号相反，证明原代码是统计推断伪造；BCa CI=(-0.0048, +0.0087)。
> **攻击代理**：反方挑刺代理-P0-2（GLM-5.2）
> **攻击维度**：反例构造 / 逻辑断链 / 隐含假设 / 边界失效 / 自相矛盾 / 量级错误 / 语义偏移（7 维度全覆盖）

---

## 0. 攻击审查概述

### 严重性汇总表

| 编号 | 严重性 | 攻击维度 | 位置 | 攻击摘要 | 可修补性 |
|------|--------|---------|------|---------|---------|
| F1 | **致命** | 反例构造/自相矛盾 | L636 + 正方报告 | 修复反噬：正确 CI=(-0.0048,+0.0087) 跨越0，NCV 不显著（p>0.05），推翻论文"校准有益"核心主张 | 需重新审视论文结论 |
| F2 | **致命** | 隐含假设/语义偏移 | L593-594, L552-553 | `brier_parts(rmp, rcor)` 未传 n_bins，继承 P0-4 的 F1 bug，与 E3 脚本 `brier_parts_toplabel(n_bins=N_BINS)` 跨脚本不一致 | 需传 n_bins |
| S1 | **严重** | 语义偏移/逻辑断链 | E1b L589 vs E3 L239-283 | NCV 定义跨脚本不一致：E1b=delta_reliability（Murphy reliability 差），E3=ncv_multiclass（逐样本符号计数），P0-2 只修 E1b | 需统一定义或重命名 |
| S2 | **严重** | 量级错误/边界失效 | L620-635, calibration.py L363-367 | BCa 加速因子 `a` 依赖 jackknife 三阶矩，cluster 数少时（冒烟 `--limit`）估计极不稳定；`denom=6·sum(d²)^1.5` 数值敏感 | 需加 cluster 数下限断言 |
| S3 | **严重** | 边界失效/隐含假设 | L628-635, calibration.py L363-367 | jackknife `keep.sum()<10` 时 `jacks[k]=NaN`，全 NaN 时 `j.mean()` 返回 NaN+RuntimeWarning，`a` 静默退化为0，BCa 降级无警告 | 需显式 fallback 警告 |
| S4 | **严重** | 逻辑断链/语义偏移 | 正方验证论证 | "NCV 与 ΔECE 符号相反→原代码伪造"推理跳跃：符号相反可能是度量差异（10-bin reliability vs smooth ECE）而非 CI 伪造证据 | 需补强论证 |
| M1 | **轻微** | 量级错误 | L764, L612 | 冒烟 `--bootstrap 500` 对 BCa 偏少（尾部 percentile 噪声大），默认 10000 足够 | 需冒烟时强制 percentile |
| M2 | **轻微** | 边界失效 | calibration.py L381-383 | `theta_hat` 位于 bootstrap 同侧极端时 z0 饱和→零宽 CI，有警告无 fallback | 需自动 fallback percentile |
| M3 | **轻微** | 量级错误 | L593-594 → brier_parts L620 | bootstrap 重采样后 bin 可能为空（`mask.sum()==0` continue），小样本 reliability 系统性低估，CI 偏窄 | 需 adaptive bin 或警告 |

### 攻击数量统计

- **致命攻击 (F)**：2 个
- **严重攻击 (S)**：4 个
- **轻微攻击 (M)**：3 个
- **不成立攻击点**：2 个（符号方向、cluster 分组——见 §3）
- **总计**：9 个有效攻击点

### 整体评估

**P0-2 修复在统计实现层面是正确的**——`_ncv_stat` 的符号方向、cluster bootstrap 的患者级分组、BCa 的 jackknife 加速度因子实现，均与 `benefit_inference` 对齐，内部一致。修复确实消除了"用 ΔECE CI 冒充 NCV CI"的伪造。

**但修复引入了两个致命问题**：

1. **F1 修复反噬**：正确的 CI=(-0.0048, +0.0087) 跨越0，NCV 不显著。原代码的伪造 CI（借用 ΔECE CI）可能恰好给出"显著"结论，修复后正确的 CI 反而推翻了"校准有益"的核心主张。这是"统计正确性"与"科学结论"的冲突——修复在统计上对，但在论文结论上反噬。

2. **F2 n_bins 遗传 bug**：P0-2 修复了 CI 但未同步修复 P0-4 已识别的 `brier_parts` n_bins 硬编码 bug。`_ncv_stat` 中 `brier_parts(rmp, rcor)` 用默认 n_bins=10，与 E3 脚本显式传 `n_bins=N_BINS` 不一致。跨脚本 NCV 数值不可比。

**4 个严重攻击进一步限制结论强度**：S1（NCV 定义跨脚本不一致）和 S4（"符号相反→伪造"推理跳跃）最为关键。S1 意味着论文若同时引用 E1b 和 E3 的 NCV，读者会困惑。S4 意味着正方的核心论证链条有未证明的跳跃。

**建议**：P0-2 修复可接受为"统计实现正确"，但：
- 必须在论文中如实报告 NCV CI 跨越0（NCV 不显著），不得隐瞒；
- 必须同步修复 F2（传 n_bins）；
- 必须统一 E1b 和 E3 的 NCV 定义（S1）；
- 必须补强"符号相反→伪造"的论证（S4）。

---

## 1. 致命攻击 (Fatal)

### F1：修复反噬——正确 CI 跨越0，NCV 不显著，推翻论文核心主张

**位置**：L636（`ncv_ci = _bca_interval(...)`）+ 正方验证报告

**攻击维度**：反例构造 + 自相矛盾

**论证**：

正方报告修复后的 NCV 推断结果：
- 点估计：NCV = Δreliability = **+0.002084**
- 95% BCa CI = **(-0.0048, +0.0087)**
- CI 跨越0（lo < 0 < hi）

**反例**：CI 跨越0 意味着在 95% 置信水平下**无法拒绝 NCV = 0 的零假设**。即校准对 Brier reliability 的改善**不显著**（p > 0.05）。

这与论文的核心主张"温度缩放校准有益"**直接矛盾**：
- 原代码：`ncv_ci = delta_ece_ci`（伪造），ΔECE 的 CI 可能不跨0 → NCV "显著" → 支持论文主张
- 修复后：`ncv_ci = 独立 bootstrap CI`（正确），CI 跨越0 → NCV 不显著 → **推翻论文主张**

**自相矛盾**：正方修复的动机是"原代码伪造 CI"，但修复后正确的 CI 反而表明原代码的"伪造"CI 可能给出了更"好看"的结论。这是"修复反噬"——统计正确性的提升导致科学结论的恶化。

**量级分析**：
- NCV 点估计 +0.002084，CI 半宽 ≈ 0.0068
- 效应量（点估计/CI 半宽）≈ 0.31，远低于常规显著性阈值（z > 1.96）
- 即使 CI 不跨0（如 CI = [0.0001, 0.0041]），效应量 0.31 仍属"弱效应"
- 当前 CI 跨越0，连"弱效应"都无法声称

**严重性**：致命——这不是代码 bug，而是修复揭示的**真实统计结论**。正方必须如实报告 NCV 不显著，不得在论文中声称"校准显著改善 Brier reliability"。

**修复建议**：
1. 在论文中如实报告 NCV CI 跨越0，NCV 不显著；
2. 降级 NCV 为"探索性观察"而非"确认性结论"；
3. 若论文已声称"校准显著改善 reliability"，需更正。

---

### F2：`brier_parts` 未传 n_bins——继承 P0-4 的 F1 bug，跨脚本 NCV 不可比

**位置**：L593-594（`_ncv_stat` 内）、L552-553（点估计）

**攻击维度**：隐含假设 + 语义偏移

**论证**：

P0-2 修复的 `_ncv_stat` 函数：
```python
def _ncv_stat(rmp, rcor, cmp, ccor):
    _, rel_r, _, _ = brier_parts(rmp, rcor)      # ← 未传 n_bins
    _, rel_c, _, _ = brier_parts(cmp, ccor)      # ← 未传 n_bins
    return rel_r - rel_c
```

点估计同样未传：
```python
brier_raw_total, rel_raw, res_raw, unc_raw = brier_parts(raw_mp, raw_correct)   # L552
brier_cal_total, rel_cal, res_cal, unc_cal = brier_parts(cal_mp, cal_correct)   # L553
```

`brier_parts` 签名（calibration.py L586）：
```python
def brier_parts(probs, labels, n_bins: int = 10):   # 默认 10
```

**反例**：E3 脚本（`run_e3_brier_dcr_ncv.py`）的 `brier_parts_toplabel` 显式传 n_bins：
```python
def brier_parts_toplabel(probs, labels, n_bins: int = N_BINS):   # N_BINS=10
    return brier_parts(max_p, correct, n_bins=n_bins)             # 显式传
```

虽然 E3 当前 `N_BINS=10` 与 E1b 默认值一致，但：
1. E1b 的 `brier_parts` 调用**无法通过修改参数改变分箱数**——n_bins 硬编码在调用处（用默认值）；
2. 若未来 E3 将 `N_BINS` 改为 50（P0-4/A1 缓解方案），E1b 的 NCV 仍用 10 bin，跨脚本数值不可比；
3. P0-4 已识别此 bug（`adversarial_r1_attack_e3.md` F1），P0-2 修复**未同步修复**。

**隐含假设**：P0-2 隐含假设 `brier_parts` 的 n_bins=10 与脚本其他地方的 n_bins 一致。但脚本中 `smooth_ece`（ΔECE 的度量）**无分箱**（核平滑），而 NCV 用 10-bin 分箱。两者分箱策略不一致是设计选择，但**未在代码或文档中显式声明**。

**严重性**：致命——这是 P0-4 F1 bug 的遗传。P0-2 修复了 CI 伪造但继承了分箱硬编码 bug。跨脚本 NCV 数值不可比，且无法通过参数调整分箱数。

**修复建议**：
1. `_ncv_stat` 和点估计都显式传 `n_bins`（如 `brier_parts(rmp, rcor, n_bins=N_BINS)`）；
2. 在脚本顶部定义 `N_BINS = 10` 常量，与 E3 对齐；
3. 在输出 CSV 的 note 字段记录 `n_bins=10`。

---

## 2. 严重攻击 (Severe)

### S1：NCV 定义跨脚本不一致——E1b vs E3 语义偏移

**位置**：E1b L589（`ncv_point = delta_reliability`）vs E3 L239-283（`ncv_multiclass`）

**攻击维度**：语义偏移 + 逻辑断链

**论证**：

**E1b 的 NCV**（P0-2 修复后）：
```python
ncv_point = delta_reliability = rel_raw - rel_cal   # Brier Murphy reliability 分量差
```
语义：校准前后 Brier reliability（分箱平方误差加权和）的改善量，连续值，∈ [-0.25, 0.25]。

**E3 的 NCV**（`run_e3_brier_dcr_ncv.py` L239-283）：
```python
def ncv_multiclass(probs_raw, probs_cal, labels):
    # 逐样本 Brier 改善的符号计数
    ncv = (tp_improved + tn_improved - fp_worsened - fn_worsened) / N_total
```
语义：校准前后逐样本 Brier `(p-y)²` 改善/恶化的符号计数（TP+TN-FP-FN）/N，离散值，∈ [-1, 1]。

**反例**：设校准使 60% 样本的 Brier 改善、40% 恶化，但改善幅度小、恶化幅度大。
- E3 NCV = (60 - 40)/100 = +0.2（正，"多数改善"）
- E1b NCV = Δreliability = -0.01（负，"reliability 恶化"）
- 两者**符号相反**，但都叫 "NCV"。

**逻辑断链**：P0-2 只修复了 E1b 的 NCV CI，未同步 E3 的 NCV。论文若同时引用两脚本的 NCV：
- 表格中 "NCV" 列可能混合两个定义；
- 读者无法判断 E1b 的 NCV=+0.002 和 E3 的 NCV=+0.2 是否可比；
- 元分析（如跨实验聚合）会因定义不同得出错误结论。

**严重性**：严重——P0-2 的修复范围过窄，未考虑跨脚本一致性。

**修复建议**：
1. 统一 NCV 定义（建议用 E1b 的 `delta_reliability`，有 Murphy 分解理论依据）；
2. 或重命名 E3 的 NCV 为 "NCV_sign"（符号计数），E1b 的为 "NCV_rel"（reliability 差）；
3. 在论文中显式声明两脚本 NCV 的定义差异。

---

### S2：BCa 加速因子在 cluster 数量少时不稳定

**位置**：L620-635（jackknife）+ calibration.py L363-367（`a` 计算）

**攻击维度**：量级错误 + 边界失效

**论证**：

BCa 加速因子 `a` 的计算（calibration.py L363-367）：
```python
j = np.asarray(jackknife_stats, dtype=float)
j = j[np.isfinite(j)]
d = j.mean() - j
denom = 6.0 * float(np.sum(d ** 2)) ** 1.5
a = float(np.sum(d ** 3)) / denom if denom > 0 else 0.0
```

`a` 是 jackknife 统计量的三阶矩 / 二阶矩^1.5，需要**足够的 jackknife 点**才能稳定估计。

**反例**：冒烟模式 `--limit 100` 时，每 split 截 25 条记录（L387-388），患者级 cluster 数可能仅 10-20 个。jackknife 只有 10-20 个点：
- `d = j.mean() - j`：10 维向量
- `sum(d²)`：10 个样本的二阶矩估计，方差 O(1/10)
- `sum(d³)`：10 个样本的三阶矩估计，方差 O(1/10) 但偏度更大
- `a = sum(d³) / (6 · sum(d²)^1.5)`：比值估计，分母接近0时数值爆炸

**量级分析**：
- 正常情况（cluster 数 > 100）：`a` 估计稳定，BCa CI 与 percentile CI 差异小
- 冒烟情况（cluster 数 10-20）：`a` 估计噪声大，BCa CI 可能比 percentile CI 宽或窄 50%+
- 极端情况（cluster 数 < 5）：`a` 估计无意义，BCa CI 不可信

**隐含假设**：P0-2 隐含假设 cluster 数足够大（> 30）。但脚本支持 `--limit` 冒烟模式，未对 cluster 数设下限断言。

**严重性**：严重——冒烟模式下 BCa CI 不可信，但脚本仍输出 BCa CI 而非 fallback 到 percentile。

**修复建议**：
1. 在 BCa 计算前断言 `len(member_idx) >= 30`（或类似下限）；
2. cluster 数不足时自动 fallback 到 percentile CI 并警告；
3. 在输出 CSV note 字段记录 cluster 数。

---

### S3：jackknife 全 NaN 时加速因子静默退化为0

**位置**：L628-635（jackknife NaN 生成）+ calibration.py L363-367（NaN 传播）

**攻击维度**：边界失效 + 隐含假设

**论证**：

jackknife 计算（L628-635）：
```python
jacks = np.empty(len(member_idx))
for k, idxs in enumerate(member_idx):
    keep = np.ones(n_tgt, dtype=bool)
    keep[idxs] = False
    if keep.sum() < 10:                    # ← 剔除后样本不足
        jacks[k] = np.nan                  # ← NaN
        continue
    jacks[k] = _ncv_stat(...)
```

`_bca_interval` 中 NaN 处理（calibration.py L363-364）：
```python
j = np.asarray(jackknife_stats, dtype=float)
j = j[np.isfinite(j)]                      # ← 过滤 NaN
d = j.mean() - j
denom = 6.0 * float(np.sum(d ** 2)) ** 1.5
a = float(np.sum(d ** 3)) / denom if denom > 0 else 0.0
```

**反例**：设 cluster 数 = 5，每个 cluster 占 20% 样本。剔除任一 cluster 后 `keep.sum() = 80%`。若总样本 n_tgt = 50，则 `keep.sum() = 40 > 10`，正常。但若 n_tgt = 12（冒烟 `--limit 50`），`keep.sum() = 9.6 ≈ 9 < 10`，**所有** jackknife 都是 NaN。

此时：
- `j = j[np.isfinite(j)]` → 空数组 `array([])`
- `j.mean()` → `NaN`（NumPy 对空数组返回 NaN + RuntimeWarning: Mean of empty slice）
- `d = NaN - array([])` → `array([])`（空）
- `np.sum(d ** 2)` → `0.0`（空数组的和为0）
- `denom = 6 * 0.0 ** 1.5 = 0.0`
- `if denom > 0` → `False`（0.0 不大于0）
- `a = 0.0`

**结果**：`a = 0.0`，BCa 退化为 `bias-correction only`（`z0` 仍计算，但加速度项消失）。**无任何警告**告知用户 jackknife 全失败、加速因子被强制置0。

**边界失效**：
- `j.mean()` 对空数组返回 NaN，触发 `RuntimeWarning: Mean of empty slice`，但被 `if denom > 0 else 0.0` 静默吞掉；
- 用户看到的 CI 看似 BCa，实际是"bias-correction only"（缺少加速度修正）；
- 与 `bci_method="percentile"` 的结果不同（percentile 无 bias-correction），用户无法察觉降级。

**严重性**：严重——静默降级，用户误以为得到完整 BCa CI。

**修复建议**：
1. 在 `_bca_interval` 中检查 `len(j) < 3`（或类似下限），返回 `(NaN, NaN)` 或显式 fallback；
2. 在 L628-635 中统计 NaN 数量，超过阈值时警告；
3. 在输出 note 字段记录 `jackknife_valid_count / jackknife_total_count`。

---

### S4："符号相反→伪造"推理链条跳跃

**位置**：正方验证报告（"NCV (Δreliability=+0.002084) vs ΔECE (-0.016200) 有相反符号，证明原代码是统计推断伪造"）

**攻击维度**：逻辑断链 + 语义偏移

**论证**：

正方的核心论证：
1. 原代码：`ncv_ci = delta_ece_ci`（用 ΔECE CI 替代 NCV CI）
2. 观察：NCV 点估计（+0.002084）与 ΔECE 点估计（-0.016200）**符号相反**
3. 结论：原代码是"统计推断伪造"

**逻辑断链**：从"符号相反"到"伪造"之间有未证明的跳跃。符号相反有多种可能解释：

**解释A（正方主张）**：NCV 和 ΔECE 是不同统计量，共用 CI 是伪造。符号相反证明两者不同。
- 评价：论证成立，但符号相反**不是**"伪造"的直接证据，而是"两者不同"的佐证。"伪造"是**定义性**的（用 A 的 CI 作为 B 的 CI），无需符号相反即可判定。

**解释B（替代解释）**：符号相反是因为 10-bin Brier reliability 与 smooth ECE 对校准的敏感度不同：
- Brier reliability：分箱平方误差，对 bin 内偏差敏感
- smooth ECE：核平滑绝对误差，对全局偏差敏感
- 校准可能改善 bin 内偏差（reliability↓）但恶化全局偏差（ECE↑），导致符号相反
- 此时符号相反反映的是**度量差异**，与 CI 是否伪造无关

**解释C（替代解释）**：符号相反是因为分箱数不一致：
- NCV 用 10-bin Brier reliability（F2 bug）
- ΔECE 用 smooth ECE（无分箱）
- 10-bin 离散化误差可能使 reliability 改善方向与 ECE 改善方向不一致
- 此时符号相反是**分箱离散化伪影**，与 CI 伪造无关

**反例**：设校准真实效果为"reliability 改善 0.001，ECE 改善 0.01"（同向）。但 10-bin 离散化使 reliability 估计偏置 +0.001（伪改善），NCV = +0.002；smooth ECE 无偏置，ΔECE = -0.016（校准使 ECE 增加？或定义方向不同）。符号相反是离散化伪影，非 CI 伪造证据。

**隐含假设**：正方隐含假设"NCV 和 ΔECE 应同号"。但两者度量不同（平方 vs 绝对值，分箱 vs 核平滑），**无理论保证同号**。

**严重性**：严重——正方的论证链条有跳跃。修复本身正确（CI 伪造是定义性的），但"符号相反→伪造"的论证逻辑不严谨，可能误导读者认为"符号相反是伪造的证据"。

**修复建议**：
1. 将论证改为"CI 伪造是定义性的（用 A 的 CI 作为 B 的 CI，A≠B），符号相反是数值佐证"；
2. 补充分析符号相反的替代解释（度量差异、分箱不一致）；
3. 若符号相反主要由分箱不一致（F2）导致，修复 F2 后符号可能同号，需重新验证。

---

## 3. 轻微攻击 (Minor)

### M1：冒烟模式 B=500 对 BCa 偏少

**位置**：L764（`--bootstrap` 默认 10000）+ L612（`boot_ncvs = np.empty(args.bootstrap)`）

**攻击维度**：量级错误

**论证**：

BCa CI 的 percentile 截断点 `a1, a2`（calibration.py L378-379）依赖 bootstrap 分布的尾部分位数。B=500 时：
- 2.5% 分位 = 第 12.5 个值（插值）
- 97.5% 分位 = 第 487.5 个值
- 尾部估计噪声 O(1/√(B·α)) = O(1/√12.5) ≈ 0.28（相对误差 28%）

B=10000 时：
- 2.5% 分位 = 第 250 个值
- 尾部噪声 O(1/√250) ≈ 0.06（相对误差 6%）

**反例**：冒烟 `--bootstrap 500 --bci-method bca`，BCa CI 宽度可能波动 ±28%，不同 seed 下 CI 可能跨0或不跨0，结论不稳定。

**严重性**：轻微——默认 B=10000 足够，仅冒烟模式受影响。但冒烟结果可能误导。

**修复建议**：冒烟模式（B<2000）时强制 `bci_method=percentile` 并警告"BCa 需 B≥2000"。

---

### M2：z0 饱和零宽 CI 无 fallback

**位置**：calibration.py L381-383

**攻击维度**：边界失效

**论证**：

`_bca_interval` 中 `theta_hat` 位于 bootstrap 分布同侧极端时（如 `theta_hat > max(boot_stats)`），`prop_less = 1.0`，`z0 = +inf`（被 clip 到 `norm.ppf(1-1e-6) ≈ 4.75`），`a1 ≈ a2`，CI 退化为零宽。

代码有警告（L381-383）：
```python
if lo == hi:
    warnings.warn("BCa区间退化为零宽...")
```

但**无自动 fallback**——用户得到 `(lo, lo)` 零宽 CI，下游分析可能误用。

**反例**：`ncv_point = +0.002084`，但 bootstrap 分布因 cluster 数少而集中在 [-0.001, 0.001]，`theta_hat` 超出 bootstrap 最大值，z0 饱和，CI = (0.001, 0.001) 零宽。

**严重性**：轻微——有警告，但无 fallback。用户需手动检查。

**修复建议**：零宽 CI 时自动 fallback 到 percentile CI，并在 note 中标注。

---

### M3：bootstrap 中 bin 为空时 reliability 系统性低估

**位置**：L593-594 → `brier_parts` L620（`if mask.sum() == 0: continue`）

**攻击维度**：量级错误

**论证**：

`brier_parts` 对空 bin 跳过（`continue`），该 bin 对 reliability 贡献为0。但真实的 reliability 应按 bin 期望贡献分配。bootstrap 重采样后（特别是 cluster bootstrap，某些 cluster 被多次采样、某些从未采样），bin 内样本数波动大，空 bin 概率增加。

**反例**：n_tgt=100，10 bin，每 bin 期望 10 样本。cluster bootstrap 后某 bin 可能仅 2 样本（或0），`avg_prob - avg_label` 估计方差大。空 bin 的 reliability 贡献被置0，系统性低估 reliability，导致 NCV CI 偏窄。

**严重性**：轻微——这是 `brier_parts` 的已知问题（非 P0-2 新引入），但影响 NCV CI 准确性。大样本量下影响小。

**修复建议**：在 `brier_parts` 中对空 bin 发出警告，或改用 adaptive binning。

---

## 4. 不成立的攻击点（明确记录）

按攻击规范，以下维度**未发现可攻击点**，明确记录：

### 符号方向：✅ 正确

**审查**：`_ncv_stat` 返回 `rel_r - rel_c`（raw reliability - cal reliability），与点估计 `delta_reliability = rel_raw - rel_cal`（L554）**完全一致**，正值=改善。

```python
def _ncv_stat(rmp, rcor, cmp, ccor):
    _, rel_r, _, _ = brier_parts(rmp, rcor)   # raw reliability
    _, rel_c, _, _ = brier_parts(cmp, ccor)   # cal reliability
    return rel_r - rel_c                       # 正值=改善，与点估计一致
```

**结论**：符号方向正确，无攻击点。

### cluster bootstrap 分组：✅ 正确

**审查**：L600-607 的 cluster 重采样逻辑：
```python
if test_clusters is not None:
    uniq_clusters = np.unique(test_clusters)
    cluster_indices = {c: np.where(test_clusters == c)[0] for c in uniq_clusters}
    def _draw_ncv():
        chosen = rng.choice(uniq_clusters, size=len(uniq_clusters), replace=True)
        return np.concatenate([cluster_indices[c] for c in chosen])
```

与 `benefit_inference`（calibration.py L479-485）**完全一致**：按 cluster（患者ID）有放回重采样，同一 cluster 的所有样本一起被选或未被选。

`test_clusters` 来源：`tgt_clusters_arr = np.asarray(tgt_clusters)`（L466），`tgt_clusters` 来自 `_build`（L391），`build_ptbxl_datasets` 返回 `clusters_test = split_meta.loc[pos['test'], 'patient_id'].to_numpy().astype(int)`（train.py L391）——**确实是患者级 patient_id**。

**结论**：cluster bootstrap 正确按 patient 分组，同一 patient 的多个 sample 不会被拆散，无攻击点。

---

## 5. 攻击点精化汇总

### 按严重程度排序

| 排名 | 编号 | 严重性 | 攻击摘要 | 验证状态 |
|------|------|--------|---------|---------|
| 1 | F1 | 致命 | 修复反噬：正确 CI 跨越0，NCV 不显著 | ✅ 可验证（正方报告数值） |
| 2 | F2 | 致命 | brier_parts 未传 n_bins，跨脚本不一致 | ✅ 可验证（代码 L593-594） |
| 3 | S1 | 严重 | NCV 定义跨脚本不一致（E1b vs E3） | ✅ 可验证（E3 L239 vs E1b L589） |
| 4 | S4 | 严重 | "符号相反→伪造"推理跳跃 | ✅ 逻辑论证 |
| 5 | S2 | 严重 | BCa 加速因子 cluster 数少时不稳定 | ⚠️ 需冒烟模式验证 |
| 6 | S3 | 严重 | jackknife 全 NaN 时静默降级 | ⚠️ 需极端边界验证 |
| 7 | M1 | 轻微 | 冒烟 B=500 对 BCa 偏少 | ⚠️ 需多 seed 验证 |
| 8 | M2 | 轻微 | z0 饱和零宽 CI 无 fallback | ⚠️ 需极端边界验证 |
| 9 | M3 | 轻微 | bootstrap bin 空时 reliability 低估 | ⚠️ 需大样本对比 |

### 7 维度覆盖确认

| 维度 | 覆盖状态 | 发现攻击点 |
|------|---------|-----------|
| 反例构造 | ✅ 已尝试 | F1（CI 跨越0 反例）、S1（NCV 定义反例） |
| 逻辑断链 | ✅ 已尝试 | S4（符号相反→伪造跳跃）、S1（跨脚本逻辑断链） |
| 隐含假设 | ✅ 已尝试 | F2（n_bins=10 隐含假设）、S3（cluster 数足够隐含假设） |
| 边界失效 | ✅ 已尝试 | S2（cluster 数少）、S3（全 NaN）、M2（z0 饱和） |
| 自相矛盾 | ✅ 已尝试 | F1（修复反噬：统计正确 vs 科学结论矛盾） |
| 量级错误 | ✅ 已尝试 | S2（加速因子量级）、M1（B=500 量级）、M3（bin 空低估） |
| 语义偏移 | ✅ 已尝试 | F2（n_bins 语义）、S1（NCV 定义偏移）、S4（度量语义） |

---

## 6. 最终评估

### 修复的正面价值

P0-2 修复**确实消除了统计推断伪造**——原代码 `ncv_ci = delta_ece_ci` 是定义性的 fabrication（用 A 的 CI 作为 B 的 CI，A≠B），修复后 `_ncv_stat` 独立 bootstrap 在**统计实现层面正确**：
- 符号方向与点估计一致（✅）
- cluster bootstrap 按 patient 分组（✅）
- BCa jackknife 与 `benefit_inference` 对齐（✅）
- 内部一致性（点估计、bootstrap、jackknife 用相同 `brier_parts` 调用）（✅）

### 修复的遗留问题

但修复**未达无懈可击**，存在 2 个致命 + 4 个严重攻击点：

1. **F1 修复反噬**（致命）：正确 CI 推翻论文主张，正方必须如实报告 NCV 不显著；
2. **F2 n_bins 遗传**（致命）：未同步修复 P0-4 的 F1 bug，跨脚本不可比；
3. **S1 定义不一致**（严重）：E1b vs E3 的 NCV 定义不同，P0-2 修复范围过窄；
4. **S4 论证跳跃**（严重）："符号相反→伪造"推理不严谨；
5. **S2/S3 边界失效**（严重）：cluster 数少 / 全 NaN 时 BCa 静默降级。

### 建议

**P0-2 修复可接受为"统计实现正确"，但必须**：
1. **如实报告** NCV CI 跨越0、NCV 不显著（F1）；
2. **同步修复** `brier_parts` n_bins 传参（F2）；
3. **统一** E1b 和 E3 的 NCV 定义（S1）；
4. **补强** "符号相反→伪造"论证（S4）；
5. **加边界保护**：cluster 数下限断言、jackknife 全 NaN fallback（S2/S3）。

**若以上 5 项未完成，P0-2 修复不应被视为"已关闭"。**

---

## 附录：代码位置索引

| 代码位置 | 内容 | 相关攻击点 |
|---------|------|-----------|
| L547-553 | `brier_parts(raw_mp, raw_correct)` 点估计 | F2 |
| L554 | `delta_reliability = rel_raw - rel_cal` | 符号方向（✅正确） |
| L560-567 | `benefit_inference` 出 ΔECE CI | S4（对比） |
| L589 | `ncv_point = delta_reliability` | F1 |
| L591-595 | `_ncv_stat` 定义 | F2, 符号方向（✅） |
| L600-607 | cluster 重采样 | cluster 分组（✅） |
| L612-616 | bootstrap 循环 | M1, M3 |
| L618-636 | BCa jackknife + `_bca_interval` | S2, S3, M2 |
| L638-639 | percentile fallback | M1 |
| calibration.py L337-384 | `_bca_interval` | S2, S3, M2 |
| calibration.py L586-631 | `brier_parts` | F2, M3 |
| E3 L239-283 | `ncv_multiclass` | S1 |

---

> **攻击代理声明**：我尝试了全部 7 个攻击维度，发现 2 个致命、4 个严重、3 个轻微攻击点，2 个攻击点不成立（已明确记录）。P0-2 修复在统计实现层面正确，但存在修复反噬（F1）和遗传 bug（F2）两个致命问题，且论证链条有跳跃（S4）。修复不应被视为"已关闭"，需补完上述 5 项建议。
