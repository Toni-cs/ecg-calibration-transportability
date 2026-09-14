# E2 反反方裁决报告

> **反反方审查代理-E2 交付**。本报告对反方挑刺代理在 `adversarial_r1_attack_e2.md` 中提出的 15 个攻击点（F1-F2, S1-S6, M1-M7）逐条进行元审查，评估每个攻击是否为稻草人论证、是否误解正方意图、反例是否真的成立、攻击逻辑是否自洽。
> **裁决日期**：2026-09-09
> **审查对象**：`adversarial_r1_attack_e2.md`（15 个攻击点）
> **被攻击代码**：`scripts/run_e2_ablation_discrimination.py`（695 行）
> **审查代理**：反反方审查代理-E2（GLM-5.2）
> **裁决原则**：对每个攻击点给出"驳回 / 部分成立 / 成立"裁决，附具体理由。对成立攻击给出修补方案，对不成立攻击进行反驳。

---

## 0. 裁决概述

### 裁决统计

| 裁决类别 | 数量 | 编号 |
|----------|------|------|
| **成立** | 9 | F1, S1, S2, S3, M1, M2, M3, M4, M5 |
| **部分成立** | 4 | F2, S4, S5, S6 |
| **驳回** | 2 | M6, M7 |
| **合计** | 15 | — |

### 严重程度修正

| 原始编号 | 原始严重性 | 修正后严重性 | 说明 |
|----------|-----------|-------------|------|
| F1 | 致命 | **致命（维持）** | 代码确实与设计声称不符 |
| F2 | 致命 | **严重（降级）** | docstring 不一致成立，但"几乎必然 no-op"被夸大 |
| S1 | 严重 | **严重（维持）** | Stage 3 Brier reliability 确实恒等于 Stage 2 |
| S2 | 严重 | **严重（维持）** | DCR 确实未计算 |
| S3 | 严重 | **严重（维持）** | 缓存键确实不含 limit |
| S4 | 严重 | **轻微（降级）** | ID 假设未满足成立，但 cal/test 双指标已报，影响有限 |
| S5 | 严重 | **轻微（降级）** | E2 是 exploratory，R5 统计检验要求针对 E3 |
| S6 | 严重 | **轻微（降级）** | 语义偏移成立但攻击的 Resolution 不变性推理有误 |
| M1-M5 | 轻微 | **轻微（维持）** | 均成立 |
| M6 | 轻微 | **驳回** | argmax 不变性是数学定理，无需数值验证 |
| M7 | 轻微 | **驳回** | 当前数据集名无下划线，纯假设性攻击 |

### 整体评估

反方找到了 **1 个真正致命攻击（F1）** 和 **3 个严重攻击（S1, S2, S3）**，这些攻击确实成立且需要修复。反方在 F2 中正确发现了 docstring 与代码不一致，但将优化器失效夸大为"几乎必然 no-op"。S4/S5/S6 虽有部分道理，但严重程度被夸大——S4 的 cal/test 双指标已提供迁移衰减信息，S5 忽略了 E2 的 exploratory 定位，S6 的 Resolution 不变性推理本身有误。M6/M7 是过度审查。

**结论：E2 脚本存在 1 个致命 + 3 个严重 + 5 个轻微的真实问题，需约 2.5 天修复。反方的"2 致命 + 6 严重"评估存在夸大。**

---

## 1. 致命攻击裁决

### F1：Stage 2 实现"binned only"，非设计声称的"TS + binned"

**裁决：成立**

**审查过程**：

1. **是否稻草人论证**：否。反方准确引用了 R5 line 201（"TS + 分箱温度"）和脚本 docstring line 8（"Stage 2: TS + binned T"），未歪曲正方主张。

2. **是否误解正方意图**：否。反方正确读取了代码 line 468-471：
   ```python
   binned_params = fit_binned_temperature(cal_p, cal_y)       # 在 raw cal_p 上拟合
   cal_s2 = apply_binned_temperature(cal_p, binned_params)     # 在 raw cal_p 上应用
   test_s2 = apply_binned_temperature(test_p, binned_params)   # 在 raw test_p 上应用
   ```
   `cal_p` 是 raw 概率，`cal_s1` 是 TS 输出。代码确实在 raw 上拟合/应用 binned temperature，未使用 `cal_s1`。

3. **反例是否真的成立**：是。温度缩放的复合是乘法性的：先 apply T₁ 再 apply T₂ 等价于 apply T₁×T₂（因为 `softmax(logit/T₁)` 再取 logit 得 `logit/T₁`，再除以 T₂ 得 `logit/(T₁×T₂)`）。因此：
   - 设计声称的 Stage 2（先 TS 再 binned）：最低熵箱有效 T = T_global × T_b
   - 代码实现的 Stage 2（直接 binned）：最低熵箱有效 T = T_b
   - 两者确实不同。

4. **攻击逻辑是否自洽**：是。反方的推理链条完整：设计声称组合 → 代码实现替换 → 语义不同 → 边际贡献解释失效。

**严重程度评估**：**致命（维持）**。这不是代码 bug 而是设计实现不一致——docstring 声称的"控制全局 T 后 binned T 的边际贡献"在代码中不成立。论文若基于此代码声称"条件贡献"，实际测量的是"替换贡献"，核心解释框架失效。

**修补方案**（二选一）：

方案 A（改代码匹配设计）：
```python
# Stage 2: 在 TS 输出上拟合 binned temperature
binned_params = fit_binned_temperature(cal_s1, cal_y)   # 改为 cal_s1
cal_s2 = apply_binned_temperature(cal_s1, binned_params) # 改为 cal_s1
test_s2 = apply_binned_temperature(test_s1, binned_params) # 改为 test_s1
```

方案 B（改 docstring 匹配代码）：
- 将 docstring line 8 改为 "Stage 2: binned T only — 按预测熵分 5 箱，每箱一个 T（直接替换 raw）"
- 将 line 18 改为 "ΔReliability(Stage2−Stage1) = 5 分箱 T vs 1 全局 T 的灵活度收益（非条件贡献）"
- 同步修改 R5 line 201

**推荐方案 A**，因为组合设计（先全局 TS 再分箱）在理论上更合理：全局 T 校准整体锐度，分箱 T 在已校准基础上进一步细化。

---

### F2：threshold optimization 用 Nelder-Mead 优化 piecewise-constant macro-F1

**裁决：部分成立**

**审查过程**：

1. **是否稻草人论证**：否。反方准确引用了 docstring line 213-216（"坐标下降+网格搜索"）和代码 line 218-230（Nelder-Mead）。

2. **是否误解正方意图**：部分。反方正确识别了 docstring 与代码不一致（网格搜索 vs Nelder-Mead，[-0.3,0.3] vs [-0.5,0.5]），这是事实。但反方对"Nelder-Mead 几乎必然 no-op"的推断被夸大。

3. **反例是否真的成立**：部分成立。
   - **docstring 不一致**：完全成立。代码确实用 Nelder-Mead 而非网格搜索，clip 范围 [-0.5, 0.5] 而非 [-0.3, 0.3]。
   - **Nelder-Mead 在 piecewise-constant 上失效**：理论方向正确——macro-F1 关于 τ 确实是分段常数函数。但"几乎必然返回 τ≈0"是**夸大**：
     - Nelder-Mead 初始单纯形扰动为 0.05（默认），但 ECG 5 分类中，部分样本的概率差（max_prob - second_max_prob）可能 < 0.05，这些样本的 argmax 会被 τ 扰动改变，从而改变 F1
     - Nelder-Mead 在检测到 F1 变化后会沿改善方向扩展单纯形，有可能找到有意义的 τ
     - "几乎必然"需要实际运行验证，反方在 line 525 也承认"未实际运行验证"
   - 实际效果更可能是：Nelder-Mead 找到**次优** τ（非全局最优），而非完全 no-op。

4. **攻击逻辑是否自洽**：部分。推理链条在"分段常数 → 梯度=0 → Nelder-Mead 难以优化"方向正确，但在"→ 几乎必然返回 τ≈0"处存在跳跃——这依赖于"初始单纯形所有顶点 F1 相同"的假设，该假设不一定成立（取决于数据中近决策边界样本的比例）。

**严重程度评估**：**严重（从致命降级）**。
- docstring 与代码不一致：**成立**，需修复（P0）
- Nelder-Mead 是次优选择：**成立**，grid search 更可靠（P1）
- "几乎必然 no-op"：**夸大**，实际更可能是次优而非零优化
- Stage 3 消融不会完全失效，但结果可信度降低

**修补方案**：实现 docstring 声称的坐标下降 + 网格搜索（反方的修复建议正确）：
```python
def optimize_thresholds(cal_probs, cal_labels, n_classes):
    tau = np.zeros(n_classes)
    grid = np.linspace(-0.3, 0.3, 61)
    for _ in range(3):  # 坐标下降 3 轮
        for k in range(n_classes):
            best_f1, best_t = -1, 0.0
            for t in grid:
                tau_try = tau.copy(); tau_try[k] = t
                f1 = f1_score(cal_labels, predict_with_thresholds(cal_probs, tau_try),
                              average="macro", zero_division=0)
                if f1 > best_f1:
                    best_f1, best_t = f1, t
            tau[k] = best_t
    return tau
```

---

## 2. 严重攻击裁决

### S1：Stage 3 Brier reliability 恒等于 Stage 2

**裁决：成立**

**审查过程**：

1. **是否稻草人论证**：否。反方准确引用了代码 line 474-477 和 line 480-484。

2. **是否误解正方意图**：否。代码确实设置 `cal_s3, test_s3 = cal_s2, test_s2`（line 477），且代码注释明确说明"Stage3 概率=Stage2 概率（threshold 只改 argmax，不改概率）"。反方正确理解了这一设计。

3. **反例是否真的成立**：是。`test_s3` 和 `test_s2` 是同一对象引用（Python 赋值语义），`calibration_reliability(test_s3, test_y)` 必然等于 `calibration_reliability(test_s2, test_y)`。消融表 Stage 3 行的 `brier_reliability` 永远等于 Stage 2 行。line 662 的 `Δ={s3-s2:+.4f}` 永远输出 `Δ=+0.0000`。

4. **攻击逻辑是否自洽**：是。推理链条完整：threshold 不改概率 → Stage 3 概率 = Stage 2 概率 → Brier reliability 恒等 → 消融表冗余行。

**严重程度评估**：**严重（维持）**。消融表包含结构性恒等行，确实误导。但需注意：代码注释已解释原因，开发者知道这一点。问题在于消融表设计——不应将 Stage 3 放入 Brier reliability 消融表（因为 threshold 不改概率），而应通过 DCR 或 F1 变化体现 threshold 贡献。

**修补方案**：
- 从 Brier reliability 消融表移除 Stage 3 行（或标注"= Stage 2，threshold 不改概率"）
- Stage 3 的贡献通过 DCR（见 S2 修复）和 F1/PPV/NPV/MCC 变化体现
- 修改 line 662 的边际贡献汇总，将 Stage 3 的 Δ 改为 ΔF1 而非 ΔReliability

---

### S2：DCR 未计算

**裁决：成立**

**审查过程**：

1. **是否稻草人论证**：否。R5 line 203 明确声称"比较三者的 Brier reliability 和 阈值化决策改变率（DCR）"。

2. **是否误解正方意图**：否。脚本确实不计算 DCR。脚本计算 AUROC/AUPRC/F1/PPV/NPV/MCC（line 251-298），但无 DCR 定义。

3. **反例是否真的成立**：是。grep 确认脚本中无 "DCR" / "decision_change" 匹配。R5 line 290-293 定义了 DCR = |{x : 1[p_c^TS(x) > τ] ≠ 1[p_c^pre(x) > τ]}| / N，但脚本未实现。

4. **攻击逻辑是否自洽**：是。R5 声称报告 DCR → 代码不实现 → threshold 贡献无法量化。

**严重程度评估**：**严重（维持）**。DCR 是 R5 E2 设计中 threshold 贡献的核心度量，缺失意味着 threshold 的边际贡献只能通过 F1 等间接指标推断。

**修补方案**：在 `run_single_experiment` 中添加 DCR 计算：
```python
def compute_dcr(probs_pre, probs_post, threshold=0.5):
    """Decision Change Rate: TS 后阈值化决策的变化率"""
    decisions_pre = (probs_pre > threshold).astype(int)
    decisions_post = (probs_post > threshold).astype(int)
    return float(np.mean(decisions_pre != decisions_post))

# 在消融循环中添加：
dcr_s1 = compute_dcr(test_p, test_s1)
dcr_s2 = compute_dcr(test_p, test_s2)
# Stage 3 的 DCR 用 threshold 后的决策 vs raw 决策
```

---

### S3：缓存键不含 limit 和 subspace

**裁决：成立**

**审查过程**：

1. **是否稻草人论证**：否。反方准确引用了代码 line 374。

2. **是否误解正方意图**：否。缓存键确实为 `{source}_{target}_{arch}_seed{seed}.npz`，不含 `args.limit` 和 `subspace`。

3. **反例是否真的成立**：是。先跑 `--limit 240`（冒烟），缓存写入 60 样本的 probs；再跑无 `--limit`（全量），加载缓存 → 用 60 样本报告全量结果。这是静默数据污染，无警告。

4. **攻击逻辑是否自洽**：是。缓存键缺陷 → 冒烟跑污染全量跑 → 结果错误但看起来正常。

**严重程度评估**：**严重（维持）**。静默数据污染是研究代码中的高危 bug。

**修补方案**（反方的修复建议正确）：
```python
import hashlib
config_str = f"{args.limit}_{subspace}"
config_hash = hashlib.md5(config_str.encode()).hexdigest()[:8]
cache_file = CACHE_DIR / f"{source}_{target}_{arch}_seed{seed}_{config_hash}.npz"
```

---

### S4：threshold 在 source-cal 上拟合，应用于 target-test——ID 假设始终不成立

**裁决：部分成立**

**审查过程**：

1. **是否稻草人论证**：部分。反方正确指出 cal 来自 source 域、test 来自 target 域，source ≠ target。但反方将 docstring 的"OOD 下阈值迁移有衰减"曲解为"例外"——docstring 的原意是**承认 OOD 场景并声明会报告衰减**，并非声称 ID 是默认。

2. **是否误解正方意图**：部分。反方说"脚本不主动报告 gap"，但脚本在 line 502-505 同时报告 cal 和 test 两个 split 的所有判别指标：
   ```python
   for split_name, probs, labels in [
       ("cal", cal_p, cal_y),
       ("test", test_p, test_y),
   ]:
   ```
   CSV 中 cal 行（in-sample 上界）和 test 行（OOD）均可直接对比，迁移衰减 = test_F1 - cal_F1 可后处理计算。反方说"不主动报告"在 print 层面成立（汇总只打印 test），但在 CSV 层面不成立。

3. **反例是否真的成立**：是。ID 假设确实从未满足（60 实验全部跨语料库）。

4. **攻击逻辑是否自洽**：部分。"ID 假设与实验设计矛盾"成立，但"threshold 迁移性未量化"不完全成立——cal/test 双 split 的 F1 差即为迁移衰减的度量，只是未在汇总 print 中显式计算。

**严重程度评估**：**轻微（从严重降级）**。
- ID 假设未满足：成立，但 docstring 已承认 OOD
- 迁移衰减未量化：部分成立——CSV 有 cal/test 双 split 数据，衰减可后处理计算
- 影响有限：threshold 是 Stage 3 组件，其贡献已被 S1 证明对 Brier reliability 无影响，对 F1 的影响受 F2 限制

**修补方案**：在汇总 print 中添加 cal vs test 的 F1 gap 报告：
```python
# 在 line 664 后添加
cal_f1 = df_disc[(df_disc["split"]=="cal") & (df_disc["variant"]=="threshold")]["f1"].mean()
test_f1 = df_disc[(df_disc["split"]=="test") & (df_disc["variant"]=="threshold")]["f1"].mean()
print(f"  Threshold 迁移衰减: cal F1={cal_f1:.4f} → test F1={test_f1:.4f} (gap={test_f1-cal_f1:+.4f})")
```

---

### S5：无统计检验

**裁决：部分成立**

**审查过程**：

1. **是否稻草人论证**：**是（部分）**。反方将 R5 §3.2 **E3** 的统计检验要求（line 259-264：配对 t 检验 + Cohen's d + 95% CI）强加于 **E2**。但 R5 line 192 明确标注 E2 为"**Exploratory**——消融实验是新提出的分析，不是复现已发表方法"。E3 是 confirmatory hypothesis testing，E2 是 exploratory ablation analysis，两者的统计要求不同。

2. **是否误解正方意图**：部分。反方说"R5 §3.2 E3 对 H1-primary 用配对 t 检验...但 E2 无任何统计检验"——这暗示 E2 应该和 E3 一样有统计检验。但 R5 对 E2 的设计（line 208-212）用"若 (2) > (1)"的描述性比较，未要求统计检验。E2 的结论定位是"支持/不支持"而非"显著/不显著"。

3. **反例是否真的成立**：是。脚本确实无统计检验（grep 确认）。

4. **攻击逻辑是否自洽**：部分。"无统计检验 → 无法判断显著性"成立，但"消融结论需要统计显著性判断"是反方自己的标准，不是 R5 对 E2 的要求。R5 对 E2 的判断标准是描述性比较（line 209: "若 (2) > (1)"）。

**严重程度评估**：**轻微（从严重降级）**。
- E2 是 exploratory，R5 未要求统计检验
- 反方将 E3 的 confirmatory 标准强加于 E2 的 exploratory 分析——稻草人
- 但即使 exploratory 分析也**建议**有统计检验以增强可信度
- 无 FDR 校正：E2 的 3 个阶段比较是预先设计的消融，不是多假设检验，FDR 校正的必要性存疑

**修补方案**（建议而非必须）：对 60 实验的 ΔReliability 添加配对 t 检验 + 95% CI（不强制要求 FDR，因为 E2 是 exploratory 且只有 3 个预先设计的阶段比较）：
```python
from scipy.stats import ttest_rel
delta_s2_s1 = (pivot_rel["stage2_ts_binned"] - pivot_rel["stage1_ts"]).dropna()
t_stat, p_val = ttest_rel(delta_s2_s1, np.zeros_like(delta_s2_s1))
print(f"  Stage2-Stage1: t={t_stat:.3f}, p={p_val:.4f}, mean Δ={delta_s2_s1.mean():+.6f}")
```

---

### S6：top-label Brier reliability vs R5 多分类 Brier 分解论证

**裁决：部分成立**

**审查过程**：

1. **是否稻草人论证**：否。反方正确识别了 R5 的多分类 Brier 分解论证（line 248-253）与代码的 top-label Brier 实现（line 305-321）之间的语义偏移。

2. **是否误解正方意图**：部分。反方正确指出代码用 `max_prob` 和 `correct` 二值化后计算 Brier 分解。但反方在分析 top-label Brier 的 Resolution 不变性时存在**推理错误**：

   反方声称（line 350）：
   > "TS 不改变 argmax → 不改变 correct → 不改变分箱内的 avg_label → Resolution 不变"

   **这一推理是错误的**。`brier_parts` 的分箱是基于 `max_prob` 的值（`bins = np.linspace(0, 1, 11)`，line 603）。TS 改变 `max_prob`（T>1 时 max_prob 降低）→ 样本在 bin 间的分配改变 → 每个 bin 内的 `avg_label`（即 `correct` 的均值）改变 → **Resolution 可以改变**。

   具体反例：设 T=2.0，两个样本：
   - 样本 A：max_prob=0.75, correct=1（正确预测，高置信）
   - 样本 B：max_prob=0.65, correct=0（错误预测，较低置信）
   - TS 前：两者都在 bin [0.6, 0.7)（A 在 [0.7, 0.8)），假设 A 在 [0.7,0.8)，B 在 [0.6,0.7)
   - TS 后：A 的 max_prob 降至 0.55，B 降至 0.48，两者都在更低 bin
   - bin 内 avg_label 改变 → Resolution 改变

   因此，反方"Resolution 不变"的结论是**错误**的。实际情况是：TS 确实可以改变 top-label Brier 的 Resolution（通过 bin 重分配），这使得 R5 的"TS 只影响 Reliability"声称对 top-label Brier **更加不成立**——但原因与反方给出的不同。

3. **反例是否真的成立**：语义偏移成立（top-label vs 多分类 Brier），但反方对 top-label Brier 性质的分析有误。

4. **攻击逻辑是否自洽**：部分。主论点（语义偏移）自洽，但子论点（"Resolution 不变是因为 argmax 不变"）的推理链条断裂——忽略了 bin 重分配效应。

**严重程度评估**：**轻微（从严重降级）**。
- 语义偏移（top-label vs 多分类 Brier）：成立，但 top-label Brier 是校准评估中的**标准做法**（与 `eval_transfer.py` 主终点语义一致，line 308-309 注释已说明）
- 反方的 Resolution 不变性推理有误，削弱了攻击的可信度
- R5 的 Brier 分解论证确实需要修正为 top-label 版本，但这是论文论证问题，不影响实验数据的正确性
- top-label Brier 作为消融指标本身是合理的——它测量"最高置信预测的校准质量"

**修补方案**：在论文中重新论证 top-label Brier 的 TS 性质：
- 不声称"TS 只影响 Reliability 不影响 Resolution"（这对 binned 分解不精确成立）
- 改为论证"TS 保持 argmax → top-label 的 correct 不变 → TS 对 top-label Brier 的影响主要通过 max_prob 的校准质量（Reliability）体现，Resolution 的变化是 bin 重分配的二阶效应"
- 或改用 ECE/smooth_ece 作为主指标（不涉及分解论证）

---

## 3. 轻微攻击裁决

### M1：诚实校验只检查 Stage 1 ΔAUROC

**裁决：成立**

**审查过程**：代码 line 521-525 确实只比较 Stage 1 (TS) vs raw 的 ΔAUROC，不报告 Stage 2 binned 对 AUROC 的影响。但 CSV 中所有 variant 的 AUROC 都有（line 506-511），可后处理计算。

**严重程度**：**轻微（维持）**。不影响结论正确性，但主动报告更诚实。

**修补方案**：在诚实校验中添加 Stage 2 的 ΔAUROC：
```python
binned_disc = compute_discrimination_metrics(test_s2, test_y)
delta_auroc_binned = binned_disc["auroc"] - raw_disc["auroc"]
print(f"  ΔAUROC(binned−raw)={delta_auroc_binned:+.6f}")
```

---

### M2：T_binned 统计含 fallback T=1.0

**裁决：成立**

**审查过程**：代码 line 168-169 确实对不足 10 样本的箱设 T=1.0，line 491-493 的 mean/min/max 包含这些 fallback 值。

**严重程度**：**轻微（维持）**。不影响消融结论，但 T 分布统计有误导。

**修补方案**：在 T_binned 统计中区分 fitted 和 fallback：
```python
fitted_mask = np.array([t != 1.0 for t in T_binned])  # 简化：假设拟合 T 不会恰好=1.0
"T_binned_fitted_mean": np.mean(np.array(T_binned)[fitted_mask]) if fitted_mask.any() else np.nan,
```

---

### M3：discrimination "threshold" variant 只有 binned+threshold

**裁决：成立**

**审查过程**：代码 line 506-511 确实只有 `("threshold", apply_binned_temperature(probs, binned_params), tau)`，缺少 raw+threshold 和 ts+threshold。

**严重程度**：**轻微（维持）**。设计限制，不影响现有结论正确性。

**修补方案**：添加 raw+threshold 和 ts+threshold variant：
```python
for variant, v_probs, v_tau in [
    ("raw", probs, None),
    ("ts", apply_temperature_multiclass(probs, ts_params), None),
    ("binned", apply_binned_temperature(probs, binned_params), None),
    ("raw_threshold", probs, tau_raw),           # 新增
    ("ts_threshold", apply_temperature_multiclass(probs, ts_params), tau_ts),  # 新增
    ("threshold", apply_binned_temperature(probs, binned_params), tau),
]:
```

---

### M4：broad exception catch 静默吞掉所有错误

**裁决：成立**

**审查过程**：代码 line 171-175 确实用 `except Exception` 捕获所有异常并静默设 T=1.0。

**严重程度**：**轻微（维持）**。正常情况下不影响结果，但掩盖数据质量问题。

**修补方案**：收窄异常范围并添加 warning：
```python
except (ValueError, RuntimeError) as e:
    warnings.warn(f"Bin {b}: fit_temperature failed ({e}), using T=1.0")
    temperatures.append(1.0)
```

---

### M5：brier_parts 用 10 等宽分箱——R5 未声明分箱策略

**裁决：成立**

**审查过程**：`calibration.py` line 603 确实用 `np.linspace(0, 1, 11)`（10 等宽分箱），R5 未声明分箱策略。

**严重程度**：**轻微（维持）**。10 等宽是标准选择，但应声明。

**修补方案**：在 R5 方案或论文 Method 部分声明"Brier 分解使用 10 个等宽分箱（Murphy 1973 标准选择）"。可选添加敏感性分析（15 等宽、等频）。

---

### M6：F1/MCC 的 argmax 不变性未数值验证

**裁决：驳回**

**审查过程**：

1. **是否稻草人论证**：**是**。反方要求"数值验证"一个**数学定理**。TS 保持 argmax 是 softmax 的数学性质：对任意 T>0，`argmax(softmax(logit/T)) = argmax(logit)`，因为除以正数不改变排序。这是精确的数学事实，不是近似。

2. **是否误解正方意图**：**是**。反方说"若数值精度导致 argmax 改变"——但温度缩放实现（`apply_temperature_multiclass`）使用 `_to_probs(_to_logits(probs) / T)`，其中 `_to_logits` 和 `_to_probs` 都是单调函数。在 float64 精度下，除以 T（0.01-100 范围）不会导致排序翻转，除非两个 logit 的差 < 1e-15（远低于任何实际 ECG 模型的输出精度）。

3. **反例是否真的成立**：**否**。反方未给出任何实际案例 where F1_ts ≠ F1_raw。反方说"可能微变"但无证据。

4. **攻击逻辑是否自洽**：否。要求对数学定理做数值验证，本身是对数学的不信任。若按此逻辑，所有基于数学性质的代码（如矩阵乘法结合律）都需"数值验证"。

**严重程度评估**：**驳回**。argmax 不变性是精确的数学性质，无需数值验证。脚本已通过 `auroc_ts_minus_raw` 校验列（line 539-546）诚实报告 TS 对 AUROC 的影响（多分类 OvR 下确实可能微变），这已足够。F1/MCC 基于 argmax，数学上精确不变。

---

### M7：discover_checkpoints 用 split("_", 1) 解析 pair 名

**裁决：驳回**

**审查过程**：

1. **是否稻草人论证**：**是**。反方构造了一个**当前不存在的场景**（数据集名含下划线如 `ptbxl_v2`）。当前数据集名为 `ptbxl`、`chapman`、`cpsc`（line 112-116），均不含下划线。

2. **是否误解正方意图**：**是**。`split("_", 1)` 的设计意图是分割 pair 名中的第一个下划线（如 `ptbxl_chapman` → `["ptbxl", "chapman"]`）。line 562-563 的 `if source not in DATASET_BUILDERS or target not in DATASET_BUILDERS` 检查会过滤掉无效解析结果，是安全网。

3. **反例是否真的成立**：**否**。当前数据集名无下划线，反例不触发。反方承认"当前不触发"（line 449）。

4. **攻击逻辑是否自洽**：部分。代码确实对含下划线的数据集名脆弱，但这是**假设性**问题，不是当前 bug。按此标准，所有不支持未来未知输入的代码都是"攻击点"——这会使审查范围无限膨胀。

**严重程度评估**：**驳回**。当前不触发，且有 `DATASET_BUILDERS` 检查作为安全网。若未来添加含下划线的数据集名，需同步修改解析逻辑——这是正常的维护任务，不是当前代码缺陷。

---

## 4. 裁决汇总表

| 编号 | 原始严重性 | 修正严重性 | 裁决 | 核心理由 |
|------|-----------|-----------|------|---------|
| F1 | 致命 | **致命** | **成立** | 代码在 raw 上拟合 binned T，非设计声称的 TS 输出上 |
| F2 | 致命 | **严重** | **部分成立** | docstring 不一致成立；"几乎必然 no-op"夸大 |
| S1 | 严重 | **严重** | **成立** | test_s3 = test_s2 同引用，Brier reliability 恒等 |
| S2 | 严重 | **严重** | **成立** | DCR 确实未计算 |
| S3 | 严重 | **严重** | **成立** | 缓存键不含 limit，冒烟跑污染全量跑 |
| S4 | 严重 | **轻微** | **部分成立** | ID 假设未满足成立，但 cal/test 双 split 已报，影响有限 |
| S5 | 严重 | **轻微** | **部分成立** | E2 是 exploratory，反方将 E3 的 confirmatory 标准强加于 E2 |
| S6 | 严重 | **轻微** | **部分成立** | 语义偏移成立，但反方 Resolution 不变性推理有误 |
| M1 | 轻微 | **轻微** | **成立** | 只校验 Stage 1 ΔAUROC |
| M2 | 轻微 | **轻微** | **成立** | T_binned 统计含 fallback |
| M3 | 轻微 | **轻微** | **成立** | 缺少 raw+threshold / ts+threshold |
| M4 | 轻微 | **轻微** | **成立** | broad exception 静默吞错 |
| M5 | 轻微 | **轻微** | **成立** | 分箱策略未声明 |
| M6 | 轻微 | **驳回** | **驳回** | argmax 不变性是数学定理，无需数值验证 |
| M7 | 轻微 | **驳回** | **驳回** | 当前不触发，假设性攻击 |

---

## 5. 修补优先级与工时

### P0：致命修复（必须修复才能发布）

| 攻击 | 修复方案 | 工时 |
|------|---------|------|
| F1 | Stage 2 改为在 `cal_s1`/`test_s1` 上拟合/应用 binned temperature | 0.5 天 |

### P1：严重修复（需修复才能可信）

| 攻击 | 修复方案 | 工时 |
|------|---------|------|
| F2 | 实现坐标下降 + 网格搜索替代 Nelder-Mead；修正 docstring | 0.5 天 |
| S1 | 从 Brier reliability 消融表移除/标注 Stage 3 恒等行 | 0.25 天 |
| S2 | 实现 DCR 计算 | 0.5 天 |
| S3 | 缓存键加入 limit + subspace hash | 0.25 天 |

### P2：轻微修复（建议修复）

| 攻击 | 修复方案 | 工时 |
|------|---------|------|
| S4 | 汇总 print 中添加 cal vs test F1 gap | 0.25 天 |
| S5 | 添加配对 t 检验 + 95% CI（exploratory，不强制 FDR） | 0.5 天 |
| S6 | 论文中重新论证 top-label Brier 的 TS 性质 | 0.5 天 |
| M1 | 诚实校验添加 Stage 2 ΔAUROC | 0.1 天 |
| M2 | T_binned 统计区分 fitted/fallback | 0.1 天 |
| M3 | 添加 raw+threshold / ts+threshold variant | 0.2 天 |
| M4 | 收窄异常范围 + warning | 0.1 天 |
| M5 | R5/论文声明分箱策略 | 0.1 天 |

**总修复工时**：P0 = 0.5 天，P1 = 1.5 天，P2 = 1.9 天，合计 **3.9 天**。

（反方原估 5 天，修正后 3.9 天——差异来自 S4/S5/S6 降级和 M6/M7 驳回）

---

## 6. 对反方攻击质量的评价

### 反方做得好的地方

1. **F1 的反例构造精确**：温度缩放复合的乘法性分析（T_global × T_b vs T_b）是正确的数学推理
2. **S1/S2/S3 的代码事实核查准确**：引用的行号和代码片段均与实际代码一致
3. **F2 的 docstring 不一致发现**：网格搜索 vs Nelder-Mead、[-0.3,0.3] vs [-0.5,0.5] 的不一致是确凿事实
4. **诚实声明局限性**：反方在 line 525-526 承认 F2 的"几乎必然 no-op"未实际运行验证

### 反方存在的问题

1. **F2 严重程度夸大**：将"Nelder-Mead 是次优选择"夸大为"几乎必然 no-op"，从"严重"包装成"致命"
2. **S5 稻草人**：将 E3 的 confirmatory 统计检验要求强加于 E2 的 exploratory 分析
3. **S6 推理错误**：声称 top-label Brier 的 Resolution 不变，但忽略了 TS 改变 max_prob → bin 重分配 → avg_label_bin 改变 → Resolution 可变
4. **S4 忽略已有数据**：声称迁移衰减未量化，但 CSV 中 cal/test 双 split 数据已提供衰减信息
5. **M6/M7 过度审查**：要求对数学定理做数值验证（M6）、对当前不存在的场景做防御（M7）

---

## 7. 最终结论

### 对正方的建议

E2 脚本存在 **1 个致命问题（F1）** 和 **3 个严重问题（S1, S2, S3）**，这些确实成立且需优先修复。F2 的 docstring 不一致也需修复，但其影响从"致命"降级为"严重"。

修复后，E2 脚本可以支持 R5 方案 §3.2 E2 的消融结论，但需注意：
- Stage 2 的边际贡献解释需与实现一致（F1 修复后）
- Stage 3 的贡献通过 DCR 和 F1 变化体现，不通过 Brier reliability（S1/S2 修复后）
- 论文论证需使用 top-label Brier 的正确性质（S6 修复后）

### 对反方的评价

反方找到了 4 个确实成立的重要攻击（F1, S1, S2, S3），展现了扎实的代码审查能力。但在严重程度评估上存在系统性夸大倾向：将 1 个严重问题（F2 的优化器选择）包装为致命，将 2 个轻微问题（S5 的统计检验、S6 的语义偏移）包装为严重。M6/M7 属于过度审查。

**反方攻击的有效率**：15 个攻击中 9 个完全成立、4 个部分成立、2 个驳回。有效攻击（含部分成立）占比 87%，但致命/严重攻击的准确率仅 50%（8 个声称致命/严重中，4 个实际达到该级别）。

---

*裁决报告结束。E2 脚本需修复 F1 + S1 + S2 + S3 + F2（P0+P1 ≈ 2 天）才能支持论文消融结论。*
