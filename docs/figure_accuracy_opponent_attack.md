# 反方攻击：E6可靠性图统计精准性

> 攻击代理：反方（Opponent）
> 攻击对象：正方论证 `docs/figure_accuracy_proponent.md` + `scripts/run_e6_reliability_diagrams.py` + `results/l2_shift_full_390cells.csv`
> 攻击日期：2026-09-12
> 验证方法：实际读取代码、CSV、NPZ 并执行 20 组数值验证（V1-V20）

---

## 攻击摘要

- 攻击点总数：10
- 致命攻击（Fatal）：2 个
- 严重攻击（Serious）：5 个
- 轻微攻击（Minor）：3 个

**总体评估**：正方在 10-bin 分箱实现、top-label 语义、TS argmax 不变性等**机制层面**的论证是坚实的（逐位数值验证通过）。但在**汇总图语义**、**TS效果方向性**、**ECE与CSV的数值一致性**三个维度存在致命或严重问题。正方通过"诚实披露"将这些问题归类为"已知局限"，但披露不等于问题不存在——特别是当披露本身具有误导性时。

---

## 攻击点列表

### Attack-1: 汇总图掩盖了 1/6 方向的 TS 恶化

- **严重级别**：Fatal
- **攻击维度**：自相矛盾 + 反例构造
- **具体描述**：正方在 §5.2 声称汇总图 `ΔECE = +0.076852`，暗示 TS 对 6 方向平均有改善效果。但实测发现，主图（seed42）中 `cpsc→chapman` 方向的 `ΔECE = -0.021573`，即 TS **恶化**了该方向的校准。汇总图的正值 `+0.0769` 完全掩盖了这一恶化——5 个改善方向的正面效果被 1 个恶化方向的负面效果部分抵消后仍为正，但读者无法从汇总图得知存在恶化方向。

  正方在 §6.2 声称"绿色（After TS）暗示已校准/改善，符合直觉"。但对 `cpsc→chapman` 方向，绿色曲线实际上比红色曲线**更远离** y=x（ECE 从 0.091 增至 0.112），绿色暗示的"改善"是**虚假**的。

- **代码位置**：`run_e6_reliability_diagrams.py:444-458`（`_weighted_ece` 加权平均）；`run_e6_reliability_diagrams.py:332-338`（红绿色编码）
- **反例/证据**：
  ```
  主图（seed42）各方向 ΔECE：
    ptbxl→chapman:  ΔECE=+0.020528 (改善)
    ptbxl→cpsc:     ΔECE=+0.230841 (改善)
    chapman→ptbxl:  ΔECE=+0.030117 (改善)
    chapman→cpsc:   ΔECE=+0.089136 (改善)
    cpsc→ptbxl:     ΔECE=+0.254758 (改善)
    cpsc→chapman:   ΔECE=-0.021573 (恶化)  ← 被汇总图掩盖
  汇总图 ΔECE = +0.076852（正值，暗示全面改善）
  ```
- **正方论证中的对应缺陷**：§5.2 仅报告汇总 `ΔECE = +0.076852`，未提及任何方向的恶化。§6.2 的颜色编码论证假设 TS 总是改善，未考虑恶化情况。已知局限表 L3 仅讨论 cherry-picking 风险，未讨论 TS 恶化方向被掩盖的风险。

---

### Attack-2: 加权平均 ECE 与全局 ECE 在 TS 后差异 54.56%，系统性高估

- **严重级别**：Fatal
- **攻击维度**：逻辑断链 + 误导
- **具体描述**：正方在 §5.4 承认"加权平均 ECE ≠ 全局 ECE"并在代码注释中披露。但实测发现，**TS 后**的加权平均 ECE = 0.150664，而合并所有样本重算的全局 ECE = 0.097535，**差异高达 54.56%**。这不是"小差异"，而是**系统性高估**。

  更严重的是 ΔECE 的差异：
  - 加权平均 ΔECE = 0.227516 - 0.150664 = **+0.076852**
  - 全局 ΔECE = 0.222820 - 0.097535 = **+0.125285**
  - 差异 = -0.048433（**TS 效果被低估 39%**）

  汇总图显示 ΔECE = 0.077，但实际全局 ΔECE = 0.125。读者会**低估** TS 的校准效果近一半。正方声称"图例标注 'weighted mean ECE' 避免误导"，但标注了名称不等于读者能正确理解 54.56% 的差异量级——特别是当图中没有任何地方给出全局 ECE 作为参照时。

- **代码位置**：`run_e6_reliability_diagrams.py:444-458`（`_weighted_ece`）；`run_e6_reliability_diagrams.py:440-443`（注释披露）
- **反例/证据**：
  ```
  Before TS: 加权平均 ECE = 0.227516, 全局 ECE = 0.222820, 差异 = +2.14%
  After TS:  加权平均 ECE = 0.150664, 全局 ECE = 0.097535, 差异 = +54.56%  ← 致命
  ΔECE:      加权平均 = +0.076852, 全局 = +0.125285, 差异 = -38.66%
  ```
  Before TS 的差异仅 2.14%（可忽略），但 After TS 的差异飙升至 54.56%。这是因为 TS 后各方向的 ECE 差异增大（有的方向 ECE 降至 0.087，有的仍为 0.275），加权平均对离散分布的偏差被放大。
- **正方论证中的对应缺陷**：§5.4 声称"此差异已在代码注释中显式披露"并"汇总图标注 'sample-count weighted mean ECE' 而非 'global ECE'，避免误导"。但披露的是差异的**存在性**，未披露差异的**量级**（54.56%）。已知局限表 L5 将影响评为"低"，但 54.56% 的差异应评为"高"。

---

### Attack-3: E6 ECE 与 CSV 在 cpsc→chapman 方向差异 -78.13%，"量级合理"主张不成立

- **严重级别**：Serious
- **攻击维度**：反例构造 + 量级错误
- **具体描述**：正方在 §2.3 声称"E6 图的 ECE 值（0.108）落在 CSV 的 raw_ece_mean 范围 [0.074, 0.907] 内，量级合理"。这是**以偏概全**——0.108 是 `ptbxl→chapman` 方向的 ECE，确实与 CSV 的 0.084 相近。但对 `cpsc→chapman` 方向，E6 的 ECE = 0.090842，而 CSV 的 raw_ece_mean = 0.415340，**差异 -78.13%**。

  即使取 2 架构平均（resnet1d + inceptiontime），E6 的 2 架构平均 ECE = 0.087625，与 CSV 的 0.415340 差异仍为 **-78.90%**。这不是"量级合理"，而是**量级错误**——E6 图显示 cpsc→chapman 方向几乎完美校准（ECE=0.09），但 CSV 显示该方向严重过自信（ECE=0.42）。

  正方在 §2.3 的论证 #3 用 `ptbxl→chapman` 的 0.108 代表所有方向，掩盖了 `cpsc→chapman` 的 0.091 vs 0.415 的巨大差异。

- **代码位置**：正方文档 §2.3 论证 #3；`results/l2_shift_full_390cells.csv`（cpsc→chapman, seed42, noise0 行）
- **反例/证据**：
  ```
  方向              E6 ECE (resnet1d)  E6 ECE (2架构平均)  CSV raw_ece_mean  差异(2架构)
  ptbxl→chapman     0.107704           0.114415            0.084181          +35.9%
  ptbxl→cpsc        0.373406           0.386276            0.268159          +44.0%
  chapman→ptbxl     0.246077           0.256144            0.382468          -33.0%
  chapman→cpsc      0.364260           0.386452            0.328914          +17.5%
  cpsc→ptbxl        0.418316           0.378189            0.404053          -6.4%
  cpsc→chapman      0.090842           0.087625            0.415340          -78.9%  ← 量级错误
  ```
- **正方论证中的对应缺陷**：§2.3 论证 #3 "E6 图的 ECE 值（0.108）落在 CSV 的 raw_ece_mean 范围 [0.074, 0.907] 内，量级合理"——用单一方向的数值代表全部方向，且用"落在范围内"代替"逐方向一致"。已知局限表 L6 将影响评为"中"，但 -78.9% 的差异应评为"高"。

---

### Attack-4: 汇总图混合不同类数空间（5类 vs 4类），加权平均语义不成立

- **严重级别**：Serious
- **攻击维度**：隐含假设 + 语义偏移
- **具体描述**：汇总图对 6 方向的 ECE 做样本数加权平均，但 6 方向涉及不同的类数空间：
  - `ptbxl→chapman`：5类 → 5类（probs.shape = (4050, 5)）
  - `ptbxl→cpsc`：5类 → 4类（probs.shape = (2057, 4)）
  - `cpsc→chapman`：4类 → 5类（probs.shape = (3958, 5)）
  - ...

  Top-label confidence 的分布取决于类数 K：K=5 时 max(prob) 的期望低于 K=4 时（更多类别竞争最大值）。因此，5类空间的 ECE 和 4类空间的 ECE 测量的是**不同尺度的校准误差**，对它们做加权平均在语义上不成立——就像把摄氏温度和华氏温度加权平均后声称得到"平均温度"。

  正方在 §5.1-5.2 完全未提及这一混合类数问题。

- **代码位置**：`run_e6_reliability_diagrams.py:421-434`（`_weighted_avg`）；`run_e6_reliability_diagrams.py:444-458`（`_weighted_ece`）
- **反例/证据**：
  ```
  方向              probs.shape    K(源)  K(目标)  ECE_raw
  ptbxl→chapman     (4050, 5)      5      5        0.107704
  ptbxl→cpsc        (2057, 4)      5      4        0.373406
  chapman→ptbxl     (2172, 5)      5      5        0.246077
  chapman→cpsc      (2057, 4)      5      4        0.364260
  cpsc→ptbxl        (2120, 5)      4      5        0.418316
  cpsc→chapman      (3958, 5)      4      5        0.090842
  → 4类目标 (cpsc) 的 ECE 系统性偏高 (0.37, 0.36)
  → 5类目标 (chapman, ptbxl) 的 ECE 系统性偏低
  → 加权平均混合了不同 K 空间的 ECE，语义不成立
  ```
- **正方论证中的对应缺陷**：§5.1-5.2 完全未讨论类数混合问题。适用边界 #1 仅讨论 top-label vs per-class，未讨论不同 K 的 top-label 不可加性。

---

### Attack-5: 种子间 TS 效果方向反转，seed42 不具代表性

- **严重级别**：Serious
- **攻击维度**：隐含假设 + cherry-picking
- **具体描述**：正方在 §6.7 声称"cherry-picking 风险已显式披露并提供完整缓解措施"。但实测发现，`cpsc→chapman` 方向的 ΔECE 在 5 个种子间**符号反转**：

  | 种子 | ΔECE | TS 效果 |
  |------|------|---------|
  | 42 | -0.021573 | 恶化 |
  | 43 | +0.058763 | 改善 |
  | 44 | +0.078195 | 改善 |
  | 45 | -0.088903 | 恶化 |
  | 46 | -0.007582 | 恶化 |

  3/5 种子 TS 恶化，2/5 种子 TS 改善。主图选的 seed42 恰好是恶化（ΔECE=-0.022），但汇总图的 ΔECE=+0.077（改善）——这是因为汇总图平均了 6 方向，其中 5 个改善方向掩盖了 cpsc→chapman 的恶化。

  更严重的是，`chapman→ptbxl` 方向 seed45 也恶化（ΔECE=-0.003457）。总计 4/30 (13.3%) 的（方向, 种子）组合 TS 恶化。

  正方在 §6.7 的缓解措施 #1 "60 补充图覆盖全 5 种子"是正确的，但缓解措施 #3 "补充图淡色背景曲线展示变异性"具有误导性——汇总图的淡色背景曲线展示的是**6 方向的变异性**（代码 line 742: `if seed == args.rep_seed and arch == args.rep_arch`），**不是 5 种子的变异性**。读者看到汇总图的淡色曲线会以为展示了种子变异性，但实际上只展示了方向变异性。

- **代码位置**：`run_e6_reliability_diagrams.py:742`（`if seed == args.rep_seed and arch == args.rep_arch`——汇总图只收集 seed42）；`run_e6_reliability_diagrams.py:474-481`（淡色背景曲线）
- **反例/证据**：
  ```
  cpsc→chapman 方向 5 种子 ΔECE:
    seed42: -0.021573 (恶化)  ← 主图选用
    seed43: +0.058763 (改善)
    seed44: +0.078195 (改善)
    seed45: -0.088903 (恶化)
    seed46: -0.007582 (恶化)
  均值 = +0.003780, std = 0.059934
  → TS 效果方向取决于种子选择，seed42 的 -0.022 不具代表性

  全 30 个 (方向, 种子) 组合中 TS 恶化: 4/30 (13.3%)
  ```
- **正方论证中的对应缺陷**：§6.7 缓解措施 #3 声称"补充图淡色背景曲线展示变异性"，但未说明是方向变异性而非种子变异性。已知局限表 L3 将影响评为"中"，但种子间符号反转应评为"高"。

---

### Attack-6: 图例未标注 "10-bin ECE"，与主终点 smooth_ece 混淆

- **严重级别**：Serious
- **攻击维度**：语义偏移 + 误导
- **具体描述**：正方在 §2.4 承认 E6 图用 10-bin ECE 而 `transfer_result.json` 用 smooth_ece，声称"两者都是 top-label 语义，测量同一校准误差的不同估计量"。但图例（代码 line 333）只标注 `ECE=0.108`，未标注 `10-bin ECE`。

  读者看到图例中的 "ECE=0.108" 会自然联想到主终点的 ECE（smooth_ece=0.104），认为两者是同一个量。但实际上：
  - E6 图的 ECE_raw = 0.107704（10-bin ECE）
  - transfer_result.json 的 raw = 0.103530（smooth_ece）
  - 差异 = +4.03%

  TS 后差异更大：
  - E6 图的 ECE_cal = 0.087176（10-bin ECE）
  - transfer_result.json 的 cal = 0.078600（smooth_ece）
  - 差异 = +10.91%

  正方声称"这是可靠性图的标准做法"，但标准做法是在图例中**明确标注估计量类型**（如 "10-bin ECE" 或 "ECE₁₀"），而非仅写 "ECE"。

- **代码位置**：`run_e6_reliability_diagrams.py:333`（`f"Before TS (ECE={bins_before['ece']:.3f})"`）；`run_e6_reliability_diagrams.py:338`（`f"After TS (ECE={bins_after['ece']:.3f})"`）
- **反例/证据**：
  ```
  E6 图例: "Before TS (ECE=0.108)"  ← 未标注 "10-bin"
  transfer_result.json: "raw": 0.103530 (smooth_ece)
  差异(raw) = +4.03%

  E6 图例: "After TS (ECE=0.087)"   ← 未标注 "10-bin"
  transfer_result.json: "cal": 0.078600 (smooth_ece)
  差异(cal) = +10.91%  ← 读者可能误以为两者相同
  ```
- **正方论证中的对应缺陷**：§2.4 承认估计量不同但声称"语义一致"。§6.4 声称"ECE 值直接标注在图例中"但未提及标注不完整（缺少估计量类型）。已知局限表 L6 将影响评为"中"但未提及图例标注缺失。

---

### Attack-7: bootstrap CI 对极小样本 bin 退化为零宽区间

- **严重级别**：Serious
- **攻击维度**：边界失效
- **具体描述**：正方在 §3.4 论证 `len(col) >= 10` 阈值合理。但实测发现，`ptbxl→chapman` 方向的 bin 2 仅有 5 个样本，且全部正确（accuracy=1.0）。bootstrap 1000 次中每次抽到的 5 个样本（有放回）全部正确，因此 accuracy 始终为 1.0，CI = [1.0, 1.0]——**零宽区间**。

  零宽 CI 明显不合理：5 个样本全部正确不代表真实 accuracy = 1.0 的置信度为 95%。正确的 95% CI 应约为 [0.48, 1.0]（Wilson 区间）。但代码的 `len(col) >= 10` 阈值检查的是 bootstrap 后的有效值数量（1000），不是原始样本数（5），因此无法拦截这种退化。

  正方在 §3.3 声称"空 bin 的 CI 为 nan"，但**非空但极小 bin** 的 CI 不是 nan，而是退化的零宽区间——这比 nan 更具误导性，因为读者会认为有 CI 就有统计可靠性。

- **代码位置**：`run_e6_reliability_diagrams.py:262`（`if len(col) >= 10:`）；`run_e6_reliability_diagrams.py:247`（`idx = rng.choice(n, n, replace=True)`）
- **反例/证据**：
  ```
  ptbxl→chapman, resnet1d, seed42:
    bin 2: count=5, accuracy=1.0, CI=[1.000, 1.000]  ← 零宽，退化
    bin 3: count=57, accuracy=0.2982, CI=[0.175, 0.439]  ← 正常
    bin 9: count=1389, accuracy=0.6854, CI=[0.660, 0.711]  ← 正常

  bin 2 的 5 个样本全部正确 → bootstrap 1000 次每次 accuracy=1.0
  → CI = [1.0, 1.0]（零宽）
  → Wilson 95% CI for 5/5 success = [0.483, 1.000]
  → 代码 CI 严重高估了置信度
  ```
- **正方论证中的对应缺陷**：§3.4 声称"10 个样本的 2.5% 分位数勉强可用"，但未讨论原始样本数极少（如 5 个）时 bootstrap CI 退化的问题。§3.6 声称"所有 CI ∈ [0, 1] ✓"但未检查零宽 CI。

---

### Attack-8: 汇总图淡色背景曲线展示方向变异性而非种子变异性，标注具误导性

- **严重级别**：Minor
- **攻击维度**：语义偏移 + 误导
- **具体描述**：正方在 §6.7 缓解措施 #3 声称"补充图淡色背景曲线展示变异性"。但代码 line 742 `if seed == args.rep_seed and arch == args.rep_arch` 表明汇总图只收集 seed42 + resnet1d 的 6 个方向数据。淡色背景曲线（line 474-481）叠加的是这 6 个方向的曲线，展示的是**方向间变异性**，不是**种子间变异性**。

  读者看到汇总图的淡色背景曲线，会自然以为展示了种子变异性（因为 §6.7 的上下文是 cherry-picking 风险缓解）。但实际上种子变异性只能通过手动查看 60 张补充图才能评估，汇总图本身不提供任何种子变异性信息。

- **代码位置**：`run_e6_reliability_diagrams.py:742`（`if seed == args.rep_seed and arch == args.rep_arch`）；`run_e6_reliability_diagrams.py:474-481`（淡色背景曲线）
- **反例/证据**：
  ```
  代码 line 742: if seed == args.rep_seed and arch == args.rep_arch:
  → 汇总图只收集 seed42 + resnet1d 的 6 个方向
  → 淡色背景曲线 = 6 方向的变异性（方向间）
  → 不是 5 种子的变异性（种子间）

  cpsc→chapman 方向 5 种子 ΔECE: [-0.022, +0.059, +0.078, -0.089, -0.008]
  → 种子间变异性 std = 0.060（很大）
  → 但汇总图不展示此变异性
  ```
- **正方论证中的对应缺陷**：§6.7 缓解措施 #3 "补充图淡色背景曲线展示变异性"——未说明是方向变异性而非种子变异性，在 cherry-picking 风险讨论的上下文中具误导性。

---

### Attack-9: ci_before 和 ci_after 共用同一个 rng，bootstrap 不独立

- **严重级别**：Minor
- **攻击维度**：隐含假设
- **具体描述**：代码 line 700 创建单一 `rng = np.random.default_rng(args.rng_seed)`，然后在 line 727-728 传给 `_compute_bins_and_ci` 计算 ci_before 和 ci_after。由于 `_compute_bins_and_ci` 内部顺序调用 `rng.choice` 先为 before 后为 after，ci_before 和 ci_after 的 bootstrap 重采样索引**不独立**——它们使用同一个 rng 的不同段。

  独立的 bootstrap 应为 before 和 after 分别用独立的 rng（或同一 rng 的不同种子）。不独立的 bootstrap 会使 before/after 的 CI 具有相关性，可能导致 Δaccuracy 的 CI 偏窄。

  但作为"视觉辅助"（正方 §3.5 的定位），这一相关性是**保守的**（before 和 after 的 CI 偏窄意味着图上误差棒偏短，但不会改变点估计），因此影响较小。

- **代码位置**：`run_e6_reliability_diagrams.py:700`（`rng = np.random.default_rng(args.rng_seed)`）；`run_e6_reliability_diagrams.py:727-728`（`_compute_bins_and_ci(data["ood_raw"], data["ood_cal"], data["ood_labels"], rng)`）
- **反例/证据**：
  ```
  验证: 两次相同 rng 的第一次抽样:
    rng1 = np.random.default_rng(0)
    rng2 = np.random.default_rng(0)
    idx1 = rng1.choice(n, n, replace=True)
    idx2 = rng2.choice(n, n, replace=True)
    np.array_equal(idx1, idx2) = True  ← 相同种子产生相同序列

  → ci_before 和 ci_after 用同一 rng 的不同段，不独立
  → 但作为视觉辅助影响较小（保守偏差）
  ```
- **正方论证中的对应缺陷**：§3.1 声称"标准非参数 bootstrap 有放回重采样"但未讨论 before/after CI 的独立性问题。

---

### Attack-10: 4/30 (13.3%) 的（方向, 种子）组合 TS 恶化，但主图和汇总图均未标注

- **严重级别**：Minor
- **攻击维度**：隐含假设 + cherry-picking
- **具体描述**：全 30 个（方向, 种子）组合中有 4 个 TS 恶化（ΔECE < 0）：

  | 方向 | 种子 | ΔECE |
  |------|------|------|
  | cpsc→chapman | 42 | -0.021573 |
  | cpsc→chapman | 45 | -0.088903 |
  | cpsc→chapman | 46 | -0.007582 |
  | chapman→ptbxl | 45 | -0.003457 |

  主图（seed42）中有 1/6 方向恶化（cpsc→chapman），但图上用绿色标注 "After TS"，暗示改善。汇总图 ΔECE=+0.077（正值），不显示任何恶化信息。60 补充图中虽有恶化方向的图，但读者需手动对比 60 张 PDF 才能发现。

  正方在 §6.7 声称"60 补充图覆盖全 5 种子，缓解 cherry-picking 风险"，但缓解措施只是"提供数据供审查"，不是"在主图/汇总图中标注恶化方向"。读者看主图和汇总图会得出"TS 全面改善校准"的结论，而实际上 13.3% 的组合 TS 恶化。

- **代码位置**：`run_e6_reliability_diagrams.py:332-338`（红绿色编码，未区分改善/恶化）；`run_e6_reliability_diagrams.py:444-458`（汇总图加权平均，未标注恶化方向）
- **反例/证据**：
  ```
  全 30 个 (方向, 种子) 组合:
    TS 改善: 26/30 (86.7%)
    TS 恶化: 4/30 (13.3%)
      cpsc→chapman seed42: ΔECE=-0.021573
      cpsc→chapman seed45: ΔECE=-0.088903
      cpsc→chapman seed46: ΔECE=-0.007582
      chapman→ptbxl seed45: ΔECE=-0.003457

  主图 (seed42): 1/6 方向恶化 (cpsc→chapman)，但绿色标注暗示改善
  汇总图: ΔECE=+0.077 (正值)，不显示恶化信息
  ```
- **正方论证中的对应缺陷**：§6.2 声称"绿色暗示已校准/改善，符合直觉"但未考虑恶化方向。§6.7 缓解措施只提供补充图，未在主图/汇总图中标注恶化方向。

---

## 无法找到反例的维度（诚实声明）

以下攻击维度我已穷尽尝试，未找到有效反例：

### 10-bin 分箱实现正确性
- **尝试**：V1（20 次随机试验逐位比对 `compute_reliability_bins` vs `calibration.ece`）、V1b（confidence=1.0 归入末 bin）、V1c（np.linspace vs np.arange off-by-one）、V6（空 bin 返回 nan）
- **结论**：正方在 §1 的论证**无懈可击**。10-bin 分箱实现与 `calibration.py:ece()` 逐位一致，边界处理正确，空 bin 正确返回 nan。**我无法找到反例。**

### TS 后 argmax 不变性
- **尝试**：V3（全 60 个 checkpoint 检查 TS 前后 argmax 变化数）
- **结论**：正方在 §4.4 的论证**无懈可击**。60 个 checkpoint 全部 0 变化。温度缩放对 T > 0 是单调变换，理论上不改变 argmax。**我无法找到反例。**

### Top-label 语义一致性
- **尝试**：比对 `run_e6_reliability_diagrams.py:160-161` 与 `eval_transfer.py:303-304` 的 `_maxprob/_bin`
- **结论**：正方在 §4.3 的论证**无懈可击**。`probs.max(axis=1)` 和 `(probs.argmax(axis=1) == labels)` 逐位相同。**我无法找到反例。**

### seed42 在 ptbxl→chapman 方向非 cherry-picking
- **尝试**：V7（比较 seed42 的 ΔECE 在 5 种子中的排名）
- **结论**：seed42 在 `ptbxl→chapman` 方向 ΔECE 排名 5/5（最差），**非 cherry-picking**。但注意：seed42 在 `chapman→ptbxl` 和 `chapman→cpsc` 方向排名 1/5（最佳），因此 seed42 在**某些方向**有 cherry-picking 嫌疑（见 Attack-5）。

---

## 攻击总结

| 编号 | 严重级别 | 攻击维度 | 核心问题 |
|------|----------|----------|----------|
| Attack-1 | **Fatal** | 自相矛盾 | 汇总图掩盖 1/6 方向 TS 恶化 |
| Attack-2 | **Fatal** | 逻辑断链 | 加权平均 ECE 与全局 ECE 差异 54.56% |
| Attack-3 | Serious | 反例构造 | cpsc→chapman 方向 E6 vs CSV 差异 -78.9% |
| Attack-4 | Serious | 隐含假设 | 汇总图混合 5类/4类空间 |
| Attack-5 | Serious | cherry-picking | 种子间 TS 效果方向反转 |
| Attack-6 | Serious | 语义偏移 | 图例未标注 "10-bin ECE" |
| Attack-7 | Serious | 边界失效 | 极小样本 bin CI 退化为零宽 |
| Attack-8 | Minor | 语义偏移 | 淡色背景曲线是方向变异性非种子变异性 |
| Attack-9 | Minor | 隐含假设 | before/after CI 不独立 bootstrap |
| Attack-10 | Minor | cherry-picking | 13.3% 组合 TS 恶化但未标注 |

**致命问题**：Attack-1 和 Attack-2 共同指向同一根本缺陷——**汇总图的设计倾向于展示 TS 的正面效果，同时掩盖负面效果**。汇总图的 ΔECE=+0.077（正值）既掩盖了 1/6 方向的恶化（Attack-1），又系统性高估了全局 ECE 54.56%（Attack-2），导致读者对 TS 校准效果的理解产生双重偏差。

**正方"诚实披露"的局限性**：正方通过"已知局限"表将多数问题归类为"已披露"，但披露的质量存在系统性缺陷：
1. **披露存在性但不披露量级**：L5 披露"加权平均≠全局"但不披露差异 54.56%；L6 披露"ECE 定义不同"但不披露 cpsc→chapman 差异 -78.9%。
2. **披露机制但不披露后果**：§5.4 披露加权平均的数学原因（|x|+|y|≠|x+y|）但不披露后果（TS 效果被低估 39%）。
3. **披露缓解措施但不验证有效性**：§6.7 声称"60 补充图覆盖全种子"但不评估读者是否真的会查看 60 张 PDF。

这些披露缺陷使得正方的"诚实披露"更接近**免责声明**而非**有效沟通**。

---

## 验证脚本

所有攻击点的数值证据由以下验证脚本生成：
- `scripts/_opponent_attack_verify.py`：V1-V15（分箱一致性、ECE vs CSV、TS argmax、加权平均、CI 覆盖、空 bin、cherry-picking、汇总图标注、bin_centers、ECE vs smooth_ece、极小 bin CI、全方向全种子、T 值范围、CSV 定义）
- `scripts/_opponent_attack_verify2.py`：V16-V20（2架构平均、汇总图种子变异性、rng 独立性、图例标注、TS 恶化方向）
