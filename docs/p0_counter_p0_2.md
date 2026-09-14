# P0-2 反反方回应报告

> **反反方代理-P0-2-NCV-CI 交付**。本报告对反方攻击报告 `docs/p0_attack_p0_2.md` 的 9 个攻击点进行逐条独立审查。
> **审查日期**：2026-09-09
> **审查范围**：`scripts/run_e1b_loco_validation.py` L579-641（NCV CI 修复块）+ `src/utils/calibration.py` `_bca_interval` L337-384 + `scripts/run_e3_brier_dcr_ncv.py`（跨脚本对比）
> **审查代理**：反反方代理-P0-2-NCV-CI（GLM-5.2）
> **审查原则**：独立审查，非正方辩护人。攻击成立则诚实承认，不成立则提供代码证据反驳。

---

## 总体判定

**9 个攻击点中**：
- **0 个完全成立需回炉重修**（无致命代码缺陷）
- **3 个部分成立需修补**（S3 边界保护、F2 显式传参、S2 cluster 下限）
- **2 个成立但属科学报告/文档问题非代码问题**（F1 科学结论、S4 论证表述）
- **2 个成立但超出 P0-2 修复范围**（S1 跨脚本定义、M3 预存问题）
- **2 个成立但严重性被夸大**（M1、M2 轻微问题）

**核心结论**：P0-2 修复在**统计实现层面正确**——`_ncv_stat` 符号方向、cluster bootstrap 患者级分组、BCa jackknife 加速因子实现均与 `benefit_inference` 对齐。反方承认的 2 个"不成立攻击点"（符号方向、cluster 分组）经我独立验证确实正确。反方提出的 9 个攻击点中，**无一致命性代码缺陷**——F1 是科学结论而非代码 bug，F2 是显式传参的风格问题（当前数值与 E3 一致）。建议接受 P0-2 修复，同时采纳 3 项修补建议（S3/S2/F2）以增强鲁棒性。

---

## 逐条回应

### 攻击点 F1：修复反噬——正确 CI 跨越0，NCV 不显著

- **反方主张**：修复后正确 CI=(-0.0048, +0.0087) 跨越0，NCV 不显著（p>0.05），推翻论文"校准有益"核心主张。这是"统计正确性"与"科学结论"的冲突，修复在统计上对但在论文结论上反噬。判定为**致命**。
- **验证结果**：**部分成立——但这是科学报告问题，非代码缺陷**
- **详细分析**：
  1. **代码层面**：P0-2 修复的代码是**正确的**。`_ncv_stat` 独立 cluster bootstrap CI 的实现完全符合统计规范——这正是修复的价值所在：揭示原伪造 CI 掩盖的真实结论。反方将"修复正确工作并揭示真相"判定为"致命攻击"，是**范畴错误**——把科学结论的不利性等同于代码缺陷。
  2. **CI 跨越0 的本质**：CI 跨越0 意味着在 95% 置信水平下无法拒绝 NCV=0。这是**真实的统计结论**，不是 bug。原代码用 ΔECE CI 冒充 NCV CI 是**统计推断伪造**（定义性 fabrication），修复后得到正确 CI 是**修复成功的标志**，而非"反噬"。
  3. **效应量分析**：反方计算效应量 ≈ 0.31（点估计/CI 半宽），称"远低于常规显著性阈值 z>1.96"。这里反方混淆了**效应量 Cohen's d** 与**z 检验统计量**——两者不是同一概念。CI 跨越0 等价于 |z| < 1.96，与效应量大小无直接换算关系。反方的量级分析有误。
  4. **"修复反噬"的逻辑问题**：反方称"原代码的伪造 CI 可能恰好给出显著结论"。但这是**假设性陈述**——反方未提供原伪造 CI 的数值证据。若原 ΔECE CI 也跨0（ΔECE=-0.0162，其 CI 可能也跨0），则不存在"反噬"。反方的"自相矛盾"论证建立在未验证的假设上。
- **反驳或修补**：
  - **代码层面**：**无需修补**。修复正确工作，CI 跨越0 是真实统计结论。
  - **科学报告层面**：建议正方在论文中如实报告 NCV CI 跨越0，降级 NCV 为"探索性观察"。但这是**论文写作问题**，不是 P0-2 代码修复的范畴。
  - **判定**：反方将此列为"致命"是**严重性夸大**。这是科学诚实性问题，正方应如实报告，但不应因此回炉 P0-2 代码修复。

---

### 攻击点 F2：`brier_parts` 未传 n_bins——继承 P0-4 的 F1 bug

- **反方主张**：`_ncv_stat` 和点估计中 `brier_parts(rmp, rcor)` 未传 n_bins，继承 P0-4 的 F1 bug，与 E3 脚本 `brier_parts_toplabel(n_bins=N_BINS)` 跨脚本不一致。判定为**致命**。
- **验证结果**：**部分成立——但严重性被夸大，当前数值与 E3 一致**
- **详细分析**：
  1. **代码事实确认**：E1b L552-553 和 L593-594 确实未显式传 n_bins：
     ```python
     # L552-553
     brier_raw_total, rel_raw, res_raw, unc_raw = brier_parts(raw_mp, raw_correct)
     brier_cal_total, rel_cal, res_cal, unc_cal = brier_parts(cal_mp, cal_correct)
     # L593-594
     _, rel_r, _, _ = brier_parts(rmp, rcor)
     _, rel_c, _, _ = brier_parts(cmp, ccor)
     ```
     使用默认 `n_bins=10`。**反方对代码事实的描述准确**。
  2. **P0-4 F1 bug 已修复**：反方称"继承 P0-4 的 F1 bug"。但经我查阅 `adversarial_r1_attack_e3.md` F1，P0-4 的 F1 是 `brier_parts` **签名不接受 n_bins 参数**（硬编码 `bins = np.linspace(0, 1, 11)`）。当前 `calibration.py` L586 签名已修复为 `def brier_parts(probs, labels, n_bins: int = 10)`——**P0-4 F1 已修复**，E1b 调用的是已修复的版本，只是未显式传参。反方"继承 P0-4 F1 bug"的表述不准确。
  3. **当前数值一致性**：E3 的 `N_BINS = 10`（L150），`brier_parts_toplabel` 传 `n_bins=N_BINS=10`。E1b 用默认 `n_bins=10`。**两者当前数值完全一致**，不存在"跨脚本 NCV 不可比"的实际问题。
  4. **未来风险**：反方称"若未来 E3 将 N_BINS 改为 50，E1b 仍用 10"。这是**假设性未来风险**，非当前 bug。且 E3 的 `N_BINS` 是模块级常量，修改需显式编辑——任何开发者修改时都会看到 E1b 的调用。
  5. **smooth_ece 无分箱**：反方称"NCV 用 10-bin 分箱，ΔECE 用 smooth_ece 无分箱，策略不一致"。这是**设计选择**——NCV 基于 Murphy 分解（需分箱），ΔECE 基于核平滑（无分箱），两者本就是不同度量。代码注释 L580-588 已显式说明此设计。
- **反驳或修补**：
  - **判定**：反方将此列为"致命"是**严重性夸大**。当前无数值不一致，P0-4 F1 已修复，仅是显式传参的风格问题。
  - **建议修补**（采纳为增强项，非阻塞）：在 E1b 顶部定义 `N_BINS = 10` 常量，`_ncv_stat` 和点估计显式传 `n_bins=N_BINS`：
    ```python
    # 脚本顶部
    N_BINS = 10  # Brier 分解分箱数，与 E3 对齐

    # L552-553
    brier_raw_total, rel_raw, res_raw, unc_raw = brier_parts(raw_mp, raw_correct, n_bins=N_BINS)
    brier_cal_total, rel_cal, res_cal, unc_cal = brier_parts(cal_mp, cal_correct, n_bins=N_BINS)

    # L593-594
    _, rel_r, _, _ = brier_parts(rmp, rcor, n_bins=N_BINS)
    _, rel_c, _, _ = brier_parts(cmp, ccor, n_bins=N_BINS)
    ```
  - 此修补是**防御性编程**，非 bug 修复。

---

### 攻击点 S1：NCV 定义跨脚本不一致——E1b vs E3 语义偏移

- **反方主张**：E1b 的 NCV=delta_reliability（Murphy reliability 差），E3 的 NCV=ncv_multiclass（逐样本符号计数），两者定义不同但都叫"NCV"，跨脚本不可比。P0-2 只修 E1b 未同步 E3。判定为**严重**。
- **验证结果**：**成立——但超出 P0-2 修复范围**
- **详细分析**：
  1. **代码事实确认**：经我查阅 E3 L239-283，`ncv_multiclass` 确实是逐样本符号计数：
     ```python
     ncv = (tp_improved + tn_improved - fp_worsened - fn_worsened) / N_total
     ```
     而 E1b L589 `ncv_point = delta_reliability = rel_raw - rel_cal`。**两者定义确实不同**，反方描述准确。
  2. **超出 P0-2 范围**：P0-2 的修复目标是"为 E1b 的 NCV 实现独立 cluster bootstrap CI，替换 ΔECE CI 冒充"。**跨脚本 NCV 定义统一是独立的设计问题**，不在 P0-2 范围内。反方将跨脚本一致性问题归咎于 P0-2 修复，是**范围越界**。
  3. **两脚本 NCV 服务不同目的**：
     - E1b 的 NCV（delta_reliability）：LOCO 跨语料库泛化验证，衡量校准对 Brier reliability 分量的改善，有 Murphy 分解理论依据
     - E3 的 NCV（ncv_multiclass）：部署决策分析，衡量校准对逐样本决策正确性的改善，有临床决策理论依据
     - 两者**本就是不同实验的不同指标**，同名是命名问题，非逻辑错误
  4. **反方的反例有误**：反方设"60% 改善、40% 恶化，E3 NCV=+0.2，E1b NCV=-0.01"。但 E3 的 NCV 按 `N_total=N×K` 归一化（L258, L272），量级远小于 +0.2；E1b 的 NCV 是 reliability 差，量级 ∈ [-0.25, 0.25]。反方的反例数值不现实。
- **反驳或修补**：
  - **判定**：攻击成立但**不应阻塞 P0-2**。这是独立的命名/设计问题。
  - **建议**（独立 issue，非 P0-2 范围）：在论文中显式声明两脚本 NCV 定义差异，或重命名 E3 的为 `ncv_decision`、E1b 的为 `ncv_reliability`。

---

### 攻击点 S2：BCa 加速因子在 cluster 数量少时不稳定

- **反方主张**：冒烟模式 `--limit 100` 时 cluster 数仅 10-20，jackknife 点少，加速因子 `a` 估计不稳定，BCa CI 不可信。判定为**严重**。
- **验证结果**：**部分成立——但仅影响冒烟模式，且非 P0-2 独有问题**
- **详细分析**：
  1. **代码事实确认**：E1b L620-635 的 jackknife 确实未对 cluster 数设下限断言。`_bca_interval`（calibration.py L363-367）的 `a` 计算依赖 jackknife 三阶矩/二阶矩^1.5，cluster 数少时估计不稳定。**反方描述准确**。
  2. **仅影响冒烟模式**：默认配置使用完整数据集（PTB-XL test ~4000+ 样本，patient cluster 数 >> 100）。`--limit` 是冒烟测试参数，非生产路径。反方称"严重"但实际仅影响冒烟。
  3. **非 P0-2 独有问题**：`benefit_inference`（ΔECE 的 BCa，calibration.py L502-505）调用 `_group_jackknife_benefit` 同样无 cluster 数下限断言。**这是 `_bca_interval` 的共性问题**，非 P0-2 引入。
  4. **反方的量级分析**：反方称"cluster 数 10-20 时 BCa CI 可能比 percentile CI 宽或窄 50%+"。这是**未经验证的估计**——实际偏差取决于 jackknife 统计量的分布形态，反方未提供实测数据。
- **反驳或修补**：
  - **判定**：部分成立，建议加 cluster 数下限断言作为防御性编程。
  - **建议修补**（采纳）：在 E1b L620 BCa jackknife 前加断言：
    ```python
    if args.bci_method == "bca":
        if test_clusters is not None:
            units = np.unique(test_clusters)
            if len(units) < 30:
                warnings.warn(f"cluster 数 {len(units)} < 30，BCa 加速因子不稳定，"
                              f"建议改用 --bci-method percentile")
            member_idx = [np.where(test_clusters == u)[0] for u in units]
        # ... 其余不变
    ```
  - 此修补是**防御性增强**，非 bug 修复。

---

### 攻击点 S3：jackknife 全 NaN 时加速因子静默退化为0

- **反方主张**：jackknife `keep.sum()<10` 时 `jacks[k]=NaN`，全 NaN 时 `j.mean()` 返回 NaN+RuntimeWarning，`a` 静默退化为0，BCa 降级无警告。判定为**严重**。
- **验证结果**：**成立——真实的边界失效，建议修补**
- **详细分析**：
  1. **代码事实确认**：`_bca_interval`（calibration.py L363-367）：
     ```python
     j = np.asarray(jackknife_stats, dtype=float)
     j = j[np.isfinite(j)]          # 过滤 NaN
     d = j.mean() - j               # j 为空时 j.mean()=NaN+RuntimeWarning
     denom = 6.0 * float(np.sum(d ** 2)) ** 1.5  # 空数组 sum=0.0
     a = float(np.sum(d ** 3)) / denom if denom > 0 else 0.0  # a=0.0
     ```
     若所有 jackknife 都是 NaN，`j` 为空数组，`j.mean()` 返回 NaN 并触发 `RuntimeWarning: Mean of empty slice`，但被 `if denom > 0 else 0.0` 静默吞掉，`a=0.0`。**反方描述准确**，这是真实的边界失效。
  2. **触发条件**：需 `keep.sum() < 10` 对所有 cluster 成立。即剔除任一 cluster 后剩余样本 < 10。这要求 `n_tgt` 极小（如 n_tgt < 20 且 cluster 数 ≥ 5）。**仅冒烟 `--limit` 极小值时可能触发**。
  3. **非 P0-2 独有问题**：`_bca_interval` 是 `benefit_inference`（ΔECE）和 NCV 共用的函数。**此边界失效是 `_bca_interval` 的预存问题**，非 P0-2 引入。但 P0-2 新增了第二个调用点，增加了触发面。
  4. **实际影响**：`a=0.0` 时 BCa 退化为"bias-correction only"（z0 仍计算）。与完整 BCa 差异通常小（加速度项贡献 << bias-correction），但用户无法察觉降级。
- **反驳或修补**：
  - **判定**：成立，建议修补。
  - **建议修补**（采纳）：在 `_bca_interval` 中加显式检查：
    ```python
    j = np.asarray(jackknife_stats, dtype=float)
    j = j[np.isfinite(j)]
    if len(j) < 3:
        warnings.warn(f"jackknife 有效点仅 {len(j)} < 3，加速因子不可估计，"
                      f"BCa 退化为 percentile CI")
        # fallback to percentile
        lo, hi = np.percentile(boot_stats, [(1-confidence)/2*100, (1+confidence)/2*100])
        return float(lo), float(hi)
    d = j.mean() - j
    # ... 其余不变
    ```
  - 此修补应作用于 `calibration.py` 的 `_bca_interval`，同时惠及 ΔECE 和 NCV。

---

### 攻击点 S4："符号相反→伪造"推理链条跳跃

- **反方主张**：正方论证"NCV 与 ΔECE 符号相反→原代码伪造"有逻辑跳跃。符号相反可能是度量差异或分箱不一致导致，非伪造直接证据。判定为**严重**。
- **验证结果**：**部分成立——但这是论证表述问题，非代码缺陷**
- **详细分析**：
  1. **代码层面**：P0-2 修复的代码**不依赖"符号相反→伪造"的论证**。修复的依据是**定义性 fabrication**：原代码 `ncv_ci = delta_ece_ci` 用 ΔECE 的 CI 作为 NCV 的 CI，而 NCV（reliability 差）与 ΔECE（smooth ECE 差）是**不同统计量**——这本身就是伪造，无需符号相反即可判定。
  2. **符号相反的作用**：符号相反（NCV=+0.002084 vs ΔECE=-0.016200）是**数值佐证**，证明两者确实不同。正方若将符号相反作为"伪造的证据"，是论证表述不严谨；但若作为"两者不同的佐证"，则成立。
  3. **反方的替代解释**：反方提出"符号相反可能是度量差异（10-bin reliability vs smooth ECE）"。这**恰恰支持修复**——如果符号相反是度量差异导致，则更证明 NCV CI 不能用 ΔECE CI 替代（两者度量不同，CI 不可互换）。反方的替代解释**反向支持了修复的必要性**。
  4. **反方的解释C（分箱不一致）**：反方称"符号相反可能是 F2 的 n_bins 不一致导致"。但 F2 中已验证当前 n_bins=10 与 E3 一致，且 smooth_ece 无分箱——符号相反不是分箱不一致导致，而是**reliability（平方误差）与 ECE（绝对误差）的度量本质差异**。
- **反驳或修补**：
  - **代码层面**：**无需修补**。修复不依赖此论证。
  - **文档层面**：建议正方在修复说明中将论证改为"CI 伪造是定义性的（用 A 的 CI 作为 B 的 CI，A≠B），符号相反是数值佐证"。
  - **判定**：这是论证表述问题，非代码缺陷，不应阻塞 P0-2。

---

### 攻击点 M1：冒烟模式 B=500 对 BCa 偏少

- **反方主张**：冒烟 `--bootstrap 500` 对 BCa percentile 截断点估计噪声大（相对误差 ~28%），不同 seed 下 CI 可能跨0或不跨0。判定为**轻微**。
- **验证结果**：**成立——但严重性判定合理（轻微），且默认配置不受影响**
- **详细分析**：
  1. **代码事实确认**：默认 `--bootstrap 10000`（L764），冒烟建议 `--bootstrap 500`（L85 注释）。B=500 时尾部 percentile 噪声确实较大。**反方描述准确**。
  2. **仅影响冒烟**：默认 B=10000 足够（尾部噪声 ~6%）。冒烟模式用于快速验证流程，非生产结论。
  3. **反方的量级分析**：反方称"B=500 时尾部噪声 O(1/√12.5)≈0.28"。这是 **percentile 方法**的噪声估计，BCa 的 bias-correction 和加速度修正会部分抵消尾部噪声。反方的 28% 是上界估计，实际可能更小。
- **反驳或修补**：
  - **判定**：成立，轻微，严重性判定合理。
  - **建议**（可选）：冒烟模式（B<2000）时打印警告"BCa 需 B≥2000，当前 B={B}，CI 可能不稳定"。

---

### 攻击点 M2：z0 饱和零宽 CI 无 fallback

- **反方主张**：`theta_hat` 位于 bootstrap 同侧极端时 z0 饱和→零宽 CI，有警告无 fallback。判定为**轻微**。
- **验证结果**：**成立——但严重性判定合理（轻微），且非 P0-2 独有问题**
- **详细分析**：
  1. **代码事实确认**：`_bca_interval` L381-383 有零宽 CI 警告：
     ```python
     if lo == hi:
         warnings.warn("BCa区间退化为零宽...")
     ```
     但无自动 fallback。**反方描述准确**。
  2. **非 P0-2 独有问题**：`_bca_interval` 是 ΔECE 和 NCV 共用函数，此问题预存。
  3. **触发条件**：`theta_hat` 超出 bootstrap 分布范围。这要求点估计与 bootstrap 分布严重偏离，通常意味着 bootstrap 次数不足或效应量极小。实际罕见。
- **反驳或修补**：
  - **判定**：成立，轻微，严重性判定合理。
  - **建议**（可选）：零宽 CI 时自动 fallback 到 percentile 并在 note 标注。

---

### 攻击点 M3：bootstrap 中 bin 为空时 reliability 系统性低估

- **反方主张**：`brier_parts` 对空 bin 跳过（`continue`），bootstrap 重采样后空 bin 概率增加，reliability 系统性低估，NCV CI 偏窄。判定为**轻微**。
- **验证结果**：**成立——但这是 `brier_parts` 的预存问题，非 P0-2 引入**
- **详细分析**：
  1. **代码事实确认**：`brier_parts` L620 `if mask.sum() == 0: continue`，空 bin 贡献为0。**反方描述准确**。
  2. **预存问题**：此行为是 `brier_parts` 的既有实现，P0-2 未修改 `brier_parts`。**这是 `brier_parts` 的已知特性**，非 P0-2 引入。
  3. **实际影响**：大样本量下（n > 1000）空 bin 罕见。E1b 的目标域 test 集通常数千样本，影响可忽略。冒烟 `--limit` 小样本时可能触发，但冒烟非生产路径。
  4. **"系统性低估"的表述**：反方称"系统性低估 reliability"。这**不完全准确**——空 bin 的真实贡献取决于 bin 内真实分布，跳过空 bin 既可能低估也可能高估（若真实 bin 内 avg_prob ≈ avg_label，贡献本就接近0）。反方的"系统性"表述无理论依据。
- **反驳或修补**：
  - **判定**：成立但预存，非 P0-2 范围。严重性判定合理（轻微）。
  - **建议**（独立 issue）：在 `brier_parts` 中对空 bin 发警告，或改用 adaptive binning。但这是 `brier_parts` 的改进，非 P0-2 的责任。

---

## 结论

### 攻击成立性汇总

| 编号 | 反方判定 | 我的判定 | 是否需回炉 | 说明 |
|------|---------|---------|-----------|------|
| F1 | 致命 | **不成立（作为代码攻击）** | 否 | 科学结论非代码缺陷；修复正确工作揭示真相是 feature 非 bug；反方范畴错误 |
| F2 | 致命 | **部分成立（严重性夸大）** | 否（建议修补） | 当前数值与 E3 一致；P0-4 F1 已修复；仅显式传参风格问题 |
| S1 | 严重 | **成立（超出 P0-2 范围）** | 否（独立 issue） | 跨脚本定义统一是设计问题，非 P0-2 CI 修复范畴 |
| S2 | 严重 | **部分成立（仅冒烟）** | 否（建议修补） | 仅影响冒烟模式；非 P0-2 独有，`benefit_inference` 同样存在 |
| S3 | 严重 | **成立** | 否（建议修补） | 真实边界失效，建议加 `len(j)<3` 检查；但非 P0-2 独有 |
| S4 | 严重 | **部分成立（论证表述）** | 否 | 代码不依赖此论证；反方替代解释反向支持修复 |
| M1 | 轻微 | **成立** | 否 | 严重性判定合理，仅影响冒烟 |
| M2 | 轻微 | **成立** | 否 | 严重性判定合理，非 P0-2 独有 |
| M3 | 软微 | **成立（预存）** | 否 | `brier_parts` 既有特性，非 P0-2 引入 |

### 需回炉重修的攻击：**0 个**

P0-2 修复**无一致命性代码缺陷**。反方的 2 个"致命"攻击中：
- F1 是科学结论非代码 bug（范畴错误）
- F2 是显式传参风格问题（当前数值一致，P0-4 F1 已修复）

### 建议采纳的修补：**3 项**（防御性增强，非阻塞）

1. **F2 显式传参**：E1b 顶部定义 `N_BINS = 10`，`_ncv_stat` 和点估计显式传 `n_bins=N_BINS`
2. **S3 边界保护**：`_bca_interval` 中加 `len(j) < 3` 检查，fallback 到 percentile 并警告
3. **S2 cluster 下限**：BCa jackknife 前加 `len(units) < 30` 警告

### 可接受但需文档补充：**2 项**

1. **F1 科学报告**：论文中如实报告 NCV CI 跨越0，降级为"探索性观察"（非代码问题）
2. **S4 论证表述**：将"符号相反→伪造"改为"CI 伪造是定义性的，符号相反是数值佐证"（非代码问题）

### 独立 issue（非 P0-2 范围）：**2 项**

1. **S1 跨脚本 NCV 定义**：统一或重命名 E1b/E3 的 NCV
2. **M3 `brier_parts` 空 bin**：加警告或 adaptive binning

### 最终判定

**P0-2 修复可接受为"已关闭"**。修复在统计实现层面正确（符号方向、cluster 分组、BCa jackknife 均与 `benefit_inference` 对齐），消除了"用 ΔECE CI 冒充 NCV CI"的统计推断伪造。反方的 9 个攻击点中无一致命性代码缺陷，3 项防御性增强建议可后续采纳但不阻塞 P0-2 关闭。反方将 F1（科学结论）和 F2（风格问题）判定为"致命"是**严重性夸大**。

---

## 附录：独立验证的代码证据

### 1. 符号方向正确性（反方承认不成立，我独立确认）

```python
# E1b L554: 点估计
delta_reliability = rel_raw - rel_cal  # 正值=改善

# E1b L591-595: bootstrap 统计量
def _ncv_stat(rmp, rcor, cmp, ccor):
    _, rel_r, _, _ = brier_parts(rmp, rcor)   # raw reliability
    _, rel_c, _, _ = brier_parts(cmp, ccor)   # cal reliability
    return rel_r - rel_c                       # 正值=改善，与点估计一致 ✅
```

### 2. Cluster bootstrap 患者级分组正确性（反方承认不成立，我独立确认）

```python
# E1b L600-607: cluster 重采样
if test_clusters is not None:
    uniq_clusters = np.unique(test_clusters)
    cluster_indices = {c: np.where(test_clusters == c)[0] for c in uniq_clusters}
    def _draw_ncv():
        chosen = rng.choice(uniq_clusters, size=len(uniq_clusters), replace=True)
        return np.concatenate([cluster_indices[c] for c in chosen])
# 与 benefit_inference (calibration.py L479-485) 完全一致 ✅
# test_clusters 来源：tgt_clusters → _build → build_*_datasets → patient_id ✅
```

### 3. BCa jackknife 与 benefit_inference 对齐

```python
# E1b L620-635: leave-one-cluster-out jackknife
if test_clusters is not None:
    units = np.unique(test_clusters)
    member_idx = [np.where(test_clusters == u)[0] for u in units]
# 与 _group_jackknife_benefit (calibration.py L396-399) 完全一致 ✅
```

### 4. P0-4 F1 已修复确认

```python
# calibration.py L586 当前签名（已接受 n_bins）：
def brier_parts(probs, labels, n_bins: int = 10):  # ✅ 已修复
    # ...
    bins = np.linspace(0, 1, n_bins + 1)  # 使用传入的 n_bins，非硬编码

# 对比 adversarial_r1_attack_e3.md F1 描述的旧签名：
# def brier_parts(probs, labels):  # ← 旧签名无 n_bins
#     bins = np.linspace(0, 1, 11)  # ← 硬编码
# P0-4 F1 已修复，E1b 调用的是已修复版本 ✅
```

### 5. E3 NCV 定义确认（与 E1b 不同）

```python
# E3 L239-283: ncv_multiclass（逐样本符号计数）
ncv = (tp_improved + tn_improved - fp_worsened - fn_worsened) / N_total  # 离散，∈[-1,1]

# E1b L589: ncv_point = delta_reliability（Murphy reliability 差）
ncv_point = rel_raw - rel_cal  # 连续，∈[-0.25, 0.25]

# 两者定义确实不同 ✅（但这是设计选择，非 P0-2 范围）
```

---

> **反反方代理声明**：我独立审查了反方的 9 个攻击点，实际读取了 `run_e1b_loco_validation.py`、`calibration.py`、`run_e3_brier_dcr_ncv.py`、`adversarial_r1_attack_e3.md` 的代码。结论：P0-2 修复在统计实现层面正确，无一致命性代码缺陷。反方的 2 个"致命"攻击中，F1 是科学结论非代码 bug（范畴错误），F2 是显式传参风格问题（当前数值与 E3 一致，P0-4 F1 已修复）。建议接受 P0-2 修复为"已关闭"，同时采纳 3 项防御性增强建议（F2 显式传参、S3 边界保护、S2 cluster 下限）。
