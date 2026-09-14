# P0-5 反反方回应报告

**回应对象**：`docs/p0_attack_p0_5.md`（反方攻击报告）
**回应代理**：反反方代理（GLM-5.2）
**回应日期**：2026-09-09
**审查文件**：`scripts/run_e4_temperature_analysis.py`、`src/utils/calibration.py`

---

## 总体判定

反方报告质量较高，攻击点均有代码依据，无臆造内容。经逐条验证：

- **6 个指定攻击点（1-4, 6, 7）**：反方自己承认"未发现可攻击点"，经独立验证确认**确实无问题**，反方判定诚实。
- **1 个指定攻击点（5）**：**部分成立**——字段完整性无缺陷，但 summary 行新字段全 nan 是真实可用性缺陷。建议修补。
- **2 个严重攻击点（A, B）**：
  - **A（跨 CSV 字段名冲突）**：**成立**。两个 CSV 同名字段 `id_rel_binned_T` 语义不同，会误导下游分析。建议重命名。
  - **B（指标片面性）**：**部分成立**。数学论证正确，但这是 A5 显式假设的体现，非 P0-5 引入的 bug。建议补充整体 Brier 作为稳健性检查，但不应视为修复缺陷。
- **3 个轻微攻击点（C, D, E）**：**均成立但影响有限**。C 是原有问题，D/E 是可用性/可读性问题。

**总结**：0 个攻击需要回炉重修（无致命/无修复逻辑错误），2 个攻击建议正方在下一轮迭代中改进（A 重命名、B 补充整体 Brier），3 个攻击可接受但建议优化（5、C、D、E）。**P0-5 核心修复目标已达成，反方未推翻核心逻辑。**

---

## 逐条回应

### 攻击点 1：全局计算是否真的在整个 test 集上算

- **反方主张**：审查 L506-521，追踪数据流，结论是"未发现可攻击点"（修复正确）
- **验证结果**：**不成立（即反方的"无攻击点"判定正确）**
- **详细分析**：
  - L510：`id_probs_binned = apply_binned_T(id_probs, T_per_bin, bin_edges)`，`apply_binned_T`（L400-415）返回 `probs.copy()` 同形状数组，对每个样本按自身熵分箱施加对应 T → 整个 test 集的 binned-T 概率
  - L516：`id_rel_binned_global = brier_reliability_top(id_probs_binned, id_labels)`，在完整 `id_probs_binned` 上一次计算
  - `brier_reliability_top`（L167-176）→ `brier_parts(mp, cm, n_bins=10)` 在整个数组上分箱计算 reliability
  - **数据流无截断、无子集索引、无重新赋值**，全局计算属实
- **反驳或修补**：无需修补。反方判定正确，本攻击点不成立。

---

### 攻击点 2：BRIER_N_BINS=10 vs N_BINS=5 语义区分

- **反方主张**：审查 L140-141，验证 `brier_parts` 默认值，结论是"未发现可攻击点"
- **验证结果**：**不成立（反方判定正确）**
- **详细分析**：
  - 已独立查阅 `src/utils/calibration.py` L586：`def brier_parts(probs, labels, n_bins: int = 10)`，默认 10，与 `BRIER_N_BINS=10` 一致 ✓
  - `N_BINS=5`：binned-T 的**干预分箱**（按熵 quintile 分 5 箱，每箱拟合一个 T）
  - `BRIER_N_BINS=10`：Brier reliability 的**评估分箱**（按 max-prob 等宽分 10 箱，计算 Murphy reliability 项）
  - 两者维度不同（不确定度 vs 置信度）、目的不同（干预 vs 评估），不冲突
  - L175 显式传 `n_bins=BRIER_N_BINS`，未改变指标定义
- **反驳或修补**：无需修补。反方判定正确。

---

### 攻击点 3：Δrel 字段符号方向

- **反方主张**：审查 L520-521，分析符号方向，结论是"未发现可攻击点"
- **验证结果**：**不成立（反方判定正确）**
- **详细分析**：
  - L520：`dist_record["id_delta_rel_binned_vs_global"] = id_rel_binned_global - id_rel_global`
  - `brier_parts` L627：`reliability += n_bin/n * (avg_prob - avg_label) ** 2`，reliability ≥ 0，**越小越校准**
  - binned-T 更优 → `rel_binned < rel_global` → Δrel < 0
  - L980 控制台注释"负=binned 更优"与符号一致 ✓
- **反驳或修补**：无需修补。反方判定正确。

---

### 攻击点 4：控制台汇总是否仍用 per-bin 均值

- **反方主张**：审查 L974-989，追踪数据流，结论是"未发现可攻击点"
- **验证结果**：**不成立（反方判定正确）**
- **详细分析**：
  - L974-975：`id_delta_global` 从 `all_dist` 中取 `id_delta_rel_binned_vs_global` 字段
  - 该字段在 L520 赋值为 `id_rel_binned_global - id_rel_global`，两者都是**全局** Brier reliability（L516, L485）
  - 控制台对这些全局 Δrel 取 mean/median，**非 per-bin 均值**
  - 边界处理正确：失败实验 nan 被 `np.isfinite` 过滤（L975），全失败时 `if id_delta_global:` 为 False 不打印（L978）
- **反驳或修补**：无需修补。反方判定正确。

---

### 攻击点 5：CSV 新字段完整性

- **反方主张**：字段完整，但 summary_rows 新字段全 nan 是可用性缺陷（轻微）
- **验证结果**：**部分成立**
- **详细分析**：
  - **字段完整性验证通过**：fieldnames（L788-790）、dist_record（L518-521）、全局汇总（L692-698）、跨方向汇总（L715-718）、跨架构汇总（L735-738）、DIST_STATS（L755-761）、失败分支（L903-906）均包含 4 个新字段 ✓
  - **summary 行新字段全 nan 属实**：L692-698、L715-718、L735-738、L755-761 确实将 `id_rel_binned_T`、`id_delta_rel_binned_vs_global` 等设为 `float("nan")`
  - **反方反例成立**：下游脚本读 CSV 的 `arch=="SUMMARY"` 行取 `id_delta_rel_binned_vs_global` 得到 nan，无法获得平均改善量，必须过滤 `fit_status=="ok"` 行自行计算
- **反驳或修补**：
  - **部分反驳**：这是**设计选择**而非 bug。summary 行的语义是"T_global 分布的汇总统计"，新字段（binned-T 的 rel）与 T_global 分布无直接关系，塞入 nan 是合理的"不适用"标记。控制台汇总（L978-989）已弥补这一信息缺口，打印了 mean/median Δrel 和 binned 更优比例。
  - **建议修补**：若要提升 CSV 自包含性，可在 `summarize_distribution` 中对 `arch=="SUMMARY"` 行计算 `id_delta_rel_binned_vs_global` 的均值：
    ```python
    # 在 L699 全局汇总行中添加
    "id_delta_rel_binned_vs_global": float(np.mean([
        r["id_delta_rel_binned_vs_global"] for r in dist_records
        if r["fit_status"] == "ok" and np.isfinite(r.get("id_delta_rel_binned_vs_global", float("nan")))
    ])) if any(...) else float("nan"),
    ```
  - **严重程度**：轻微（可用性缺陷，非正确性 bug，控制台已弥补）

---

### 攻击点 6：brier_parts 调用的 n_bins

- **反方主张**：审查 L175，显式传 `n_bins=BRIER_N_BINS=10`，结论是"未发现可攻击点"
- **验证结果**：**不成立（反方判定正确）**
- **详细分析**：
  - L175：`_, rel, _, _ = brier_parts(mp, cm, n_bins=BRIER_N_BINS)` 显式传 10
  - 全局计算（L516-517）和箱级计算（L534-547）都通过 `brier_reliability_top` 间接传 10
  - 与 `brier_parts` 默认值 10 一致（已独立验证 `calibration.py` L586）
- **反驳或修补**：无需修补。反方判定正确。

---

### 攻击点 7：id_probs_binned 变量来源

- **反方主张**：审查 L510/L516/L536，结论是"未发现可攻击点"
- **验证结果**：**不成立（反方判定正确）**
- **详细分析**：
  - L510：`id_probs_binned` 赋值为整个 test 集的 binned-T 概率
  - L516：bin 循环之前，用完整 `id_probs_binned` 计算全局 reliability
  - L536：bin 循环内，`id_probs_binned[id_bin_mask]` 是**只读索引**，不修改原数组
  - 全局计算 L516 用的是完整的 `id_probs_binned`，未被覆盖
- **反驳或修补**：无需修补。反方判定正确。

---

### 攻击点 A（严重）：跨 CSV 字段名 `id_rel_binned_T` 同名不同义

- **反方主张**：`temperature_distribution_analysis.csv` 的 `id_rel_binned_T` 是全局值，`binned_temperature_exploratory.csv` 的同名字段是箱级值，同名不同义会误导下游
- **验证结果**：**成立**
- **详细分析**：
  - **temperature_distribution_analysis.csv**：
    - L788 fieldname 包含 `id_rel_binned_T`
    - L518 赋值：`dist_record["id_rel_binned_T"] = id_rel_binned_global`（L516 全局值，整个 test 集）
  - **binned_temperature_exploratory.csv**：
    - L801 fieldname 包含 `id_rel_binned_T`
    - L563 赋值：`"id_rel_binned_T": id_rel_binned_b`（L535 箱级值，箱内子集）
  - **同名字段，数值不同，语义不同**：前者是全局 reliability（每实验 1 行），后者是箱级 reliability（每实验 5 行）
  - **反方反例成立**：下游脚本按字段名 `id_rel_binned_T` 读取两个 CSV 会混淆
  - **docstring 不一致**：L76-79 描述 binned CSV 字段为 `brier_rel_binned`，与实际字段名 `id_rel_binned_T` 不符，加剧混淆
  - `ood_rel_binned_T` 同理（L790 vs L569）
- **反驳或修补**：
  - **无法反驳，攻击成立**。这是真实的字段名冲突。
  - **修补方案**：将 `binned_temperature_exploratory.csv` 的箱级字段重命名为 `id_rel_binned_T_within_bin` / `ood_rel_binned_T_within_bin`，与全局字段区分：
    ```python
    # L563 修改
    "id_rel_binned_T_within_bin": id_rel_binned_b,
    # L569 修改
    "ood_rel_binned_T_within_bin": ood_rel_binned_b,
    # L801-803 fieldnames 同步修改
    ```
  - 同时修正 docstring L76-79 的字段名描述
  - **严重程度**：严重（但非致命——两 CSV 粒度不同不太可能直接 join，但人工阅读和自动化分析易混淆）

---

### 攻击点 B（严重）：只比较 Brier reliability 项，不比较整体 Brier score

- **反方主张**：Δrel < 0 不保证整体 Brier 更优（Resolution 可能同时下降），正方应补充 Δ Brier 作为稳健性检查
- **验证结果**：**部分成立**
- **详细分析**：
  - **数学论证正确**：已独立验证 `brier_parts` L589 注释 `Brier = Reliability - Resolution + Uncertainty`，L630 `brier_total = reliability - resolution + uncertainty`
  - ΔBrier = Δrel - Δresolution，当 binned-T 同时降低 Rel 和 Res 时，Δrel < 0 但 ΔBrier 可能 > 0
  - **反方反例成立**：global-T (Rel=0.05, Res=0.15, Brier=0.15) vs binned-T (Rel=0.03, Res=0.10, Brier=0.18) → Δrel=-0.02<0 但 Brier 恶化
  - **但这是 A5 显式假设的体现**：docstring L34 明确声明 "A5. Brier reliability 是 binned-T 评估的合理指标（相比 ECE 无分箱偏差）"。正方**显式**选择了 reliability 项作为指标，非隐含缺陷。
  - **P0-5 修复本身未引入此问题**：P0-5 修复的是"全局 reliability 从未计算"的 bug，修复后正确计算了 reliability。指标选择（只看 Rel）是 A5 假设，与 P0-5 修复目标正交。
  - **脚本定位为探索性**：B1 声明"探索性评估，不进入主检验"，主检验由 `eval_transfer.py` 的 BCa CI 承担。探索性分析的指标选择宽松度更高。
- **反驳或修补**：
  - **部分反驳**：攻击针对 A5 假设，非 P0-5 修复引入的 bug。正方已显式声明假设，符合"假设透明化"的学术规范。将此列为"严重"略高估——这是**方法学讨论点**，非修复缺陷。
  - **建议修补**（提升稳健性，非必须）：在 `dist_record` 中补充整体 Brier score 的 Δ：
    ```python
    # L519 后添加
    id_brier_binned_global = brier_raw_top(id_probs_binned, id_labels)
    id_brier_global = brier_raw_top(apply_global_T(id_probs, T_global), id_labels)
    dist_record["id_delta_brier_binned_vs_global"] = id_brier_binned_global - id_brier_global
    # OOD 同理
    ```
    并在控制台汇总中同时报告 Δrel 和 ΔBrier，让读者自行判断。
  - **严重程度**：严重（方法学层面），但**不应要求 P0-5 回炉重修**——修复目标已达成，补充整体 Brier 是增量改进。

---

### 攻击点 C（轻微）：DIST_STATS 行字段滥用

- **反方主张**：DIST_STATS 行把 T 分布统计量塞进 `n_cal`/`n_id`/`n_ood`/`id_rel_raw` 等字段，P0-5 新字段全 nan 与旧字段滥用风格不一致
- **验证结果**：**成立（但为原有问题）**
- **详细分析**：
  - L742-762 确认：`"n_cal": int(np.median(Ts))`（n_cal 字段塞 T median）、`"n_id": float(np.percentile(Ts, 25))`（n_id 塞 T Q25）、`"id_rel_raw": float(Ts.max())`（id_rel_raw 塞 T max）等
  - **字段语义滥用属实**：`n_cal` 应为样本数，这里塞 T 的 median，下游按字段名解析会误读
  - **P0-5 未引入此问题**：这是 `summarize_distribution` 的原有设计（用 DIST_STATS 行复用字段塞 T 分布统计量，避免新增列）
  - **P0-5 新字段全 nan 属实**：L755-761 将 `id_rel_binned_T` 等设为 nan，与旧字段滥用风格不一致
  - **风格不一致的实质**：旧字段被滥用（塞 T 统计量），新字段未被滥用（nan）。这其实是**新字段更干净**，但暴露了旧字段滥用的不彻底性
- **反驳或修补**：
  - **部分反驳**：P0-5 新字段设为 nan 是**更正确的做法**——新字段与 T 分布无直接关系，塞 T 统计量才是滥用。P0-5 没有跟风滥用，反而是好事。反方将此列为"风格不一致"略牵强。
  - **建议修补**（可选，治本）：重构 DIST_STATS 行，新增专用字段 `T_median`/`T_q25`/`T_q75`/`T_max`/`T_std`/`T_mean_abs_dev`，不再复用 `n_cal` 等字段。但这超出 P0-5 范围，应作为独立重构任务。
  - **严重程度**：轻微（原有问题，P0-5 未加剧，新字段反而更干净）

---

### 攻击点 D（轻微）：BRIER_N_BINS 不可配置，无法做箱数敏感性

- **反方主张**：`N_BINS` 可通过 `--n-bins` 配置但 `BRIER_N_BINS` 不可，加剧 B2 局限
- **验证结果**：**成立**
- **详细分析**：
  - L834：`global N_BINS` 声明 ✓
  - L845-846：`--n-bins` 参数 ✓
  - L855：`N_BINS = args.n_bins` 赋值 ✓
  - **BRIER_N_BINS 无 `global` 声明、无命令行参数**：L141 模块级常量，固定为 10
  - 用户无法通过命令行做 Brier reliability 箱数敏感性分析（如 5/10/15 箱对比），必须改源码
  - docstring L40 (B2) 承认"5 箱 quintile 未做箱数敏感性"，`BRIER_N_BINS` 不可配置**确实加剧 B2**——连 Brier reliability 的箱数敏感性也无法做
- **反驳或修补**：
  - **无法反驳，攻击成立**。配置不对称是真实的可用性缺陷。
  - **修补方案**：添加 `--brier-n-bins` 参数：
    ```python
    # L141 后添加 global 声明（或在 main 内用 global）
    # L834 修改：global N_BINS, BRIER_N_BINS
    # L845-846 后添加：
    ap.add_argument("--brier-n-bins", type=int, default=BRIER_N_BINS,
                    help="Brier reliability 等宽分箱数（默认 10）")
    # L855 后添加：
    BRIER_N_BINS = args.brier_n_bins
    ```
  - **严重程度**：轻微（可用性缺陷，非正确性 bug）

---

### 攻击点 E（轻微）：内部变量名 "global" 语义双重含义

- **反方主张**：`id_rel_global` 的 "global" 指 global-T，`id_rel_binned_global` 的 "global" 指全局计算，语义双重含义
- **验证结果**：**成立（但仅限可读性）**
- **详细分析**：
  - L485：`id_rel_global = brier_reliability_top(apply_global_T(id_probs, T_global), id_labels)` — "global" 指 **global-T**（单一温度）
  - L516：`id_rel_binned_global = brier_reliability_top(id_probs_binned, id_labels)` — "global" 指 **全局计算**（整个 test 集）
  - 两个 "global" 语义不同，读者可能误读 `id_rel_binned_global` 为"binned-T 的 global-T 版本"（无意义）
  - **CSV 字段名已规避**：`id_rel_global_T`（L499，global-T 的 rel）和 `id_rel_binned_T`（L518，binned-T 的 rel），无 "global" 歧义
  - **问题仅在内部变量名**，不影响外部接口
- **反驳或修补**：
  - **部分反驳**：CSV 字段名清晰，外部接口无歧义。内部变量名混淆仅影响代码维护者，不影响用户和下游分析。
  - **建议修补**（可选）：重命名内部变量：
    ```python
    # L516 修改
    id_rel_binned_overall = brier_reliability_top(id_probs_binned, id_labels)
    ood_rel_binned_overall = brier_reliability_top(ood_probs_binned, ood_labels)
    # L518-521 同步修改
    ```
    用 "overall"（整体计算）替代 "global"（与 global-T 的 global 区分）
  - **严重程度**：轻微（可读性问题，不影响正确性和外部接口）

---

## 边界失效扫描回应

反方边界扫描结论（空 test 集 reliability=0.0 误报"完美校准"）经验证：

- **属 `brier_parts` 固有行为**：L611 `base_rate = labels.mean()` 对空数组返回 nan，L620 `mask.sum()==0` 跳过空箱，reliability=0.0
- **非 P0-5 引入**：这是 `brier_parts` 的原有行为，P0-5 修复未改变
- **实际影响有限**：E4 实验中 test 集为空的概率极低（需 checkpoint 存在但 test 集为空，矛盾）
- **结论**：边界行为可接受，无需修补

---

## 量级错误扫描回应

反方验证了"per-bin 均值 ≠ 全局 Brier reliability"的数学声明：

- **数学验证正确**：per-bin 均值用 `1/5 · n_{k,j}/n_k` 权重，全局用 `n_{k,j}/n` 权重，当各 binned-T 箱样本数不均时确实不同
- **正方声明属实**：L515 注释"Brier reliability 是加权非线性，不可加"正确
- **结论**：无量级错误，修复用全局计算是正确的

---

## 结论

### 需要回炉重修的攻击：0 个

P0-5 修复的**核心目标**（全局 binned-T Brier reliability 从未计算 → 现已正确计算）**已达成**。7 个指定攻击点中 6 个无懈可击，反方自己承认。无致命攻击，无修复逻辑错误。

### 建议正方在下一轮迭代中改进的攻击：2 个（严重）

1. **攻击点 A（跨 CSV 字段名冲突）**：**成立，建议修补**。将 `binned_temperature_exploratory.csv` 的箱级字段 `id_rel_binned_T` → `id_rel_binned_T_within_bin`，`ood_rel_binned_T` → `ood_rel_binned_T_within_bin`，消除跨 CSV 同名冲突。同步修正 docstring L76-79 的字段名描述。

2. **攻击点 B（指标片面性）**：**部分成立，建议补充但非必须**。正方已显式声明 A5 假设，方法学上站得住。但建议在 `dist_record` 中补充整体 Brier score 的 Δ（`id_delta_brier_binned_vs_global`），并在控制台同时报告 Δrel 和 ΔBrier，让读者自行判断 binned-T 是否在 reliability 和整体 Brier 上一致改善。这是**增量改进**，非 P0-5 修复缺陷。

### 可接受但建议优化的攻击：4 个（轻微）

3. **攻击点 5（summary 行新字段全 nan）**：部分成立。控制台已弥补信息缺口，但 CSV 自包含性可提升。建议在 `arch=="SUMMARY"` 行计算并填入 `id_delta_rel_binned_vs_global` 的均值。

4. **攻击点 C（DIST_STATS 字段滥用）**：成立但为原有问题。P0-5 新字段设为 nan 反而更干净。建议作为独立重构任务，新增专用字段 `T_median`/`T_q25` 等，不再复用 `n_cal`。

5. **攻击点 D（BRIER_N_BINS 不可配置）**：成立。建议添加 `--brier-n-bins` 参数，与 `--n-bins` 对称。

6. **攻击点 E（内部变量名混淆）**：成立但仅限可读性。CSV 字段名已规避，外部接口无歧义。建议将 `id_rel_binned_global` 重命名为 `id_rel_binned_overall`。

### 反方报告质量评价

- **优点**：攻击点均有代码依据，无臆造；6 个指定攻击点诚实承认"未发现可攻击点"；数学验证（量级扫描）严谨；边界扫描全面
- **不足**：攻击点 C 将"P0-5 新字段更干净"误判为"风格不一致暴露不彻底性"——新字段不滥用才是正确做法；攻击点 B 列为"严重"略高估，这是 A5 显式假设的体现，非修复缺陷
- **总体**：反方报告可信度高，未推翻 P0-5 核心修复逻辑，发现的附带问题有改进价值

### 最终判定

**P0-5 修复通过反反方审查。** 核心逻辑正确，无致命/严重修复缺陷。2 个严重附带问题（A 字段名冲突、B 指标片面性）建议正方在下一轮迭代中改进，但不构成回炉重修的理由。4 个轻微问题可接受，建议优化。

---

*本报告由反反方代理生成，独立审查反方攻击报告，逐条验证代码后给出判定。*
