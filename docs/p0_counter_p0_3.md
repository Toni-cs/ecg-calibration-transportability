# P0-3 反反方回应报告

> **反反方代理-P0-3 交付**。本报告对反方攻击报告 `docs/p0_attack_p0_3.md` 的 9 个攻击点进行逐条独立审查。审查基于实际代码读取（`scripts/run_e2_ablation_discrimination.py` 712 行 + `src/utils/calibration.py` 865 行 + 跨脚本 grep 验证），不预设正方立场。
> **审查日期**：2026-09-09
> **审查代理**：反反方代理-P0-3（GLM-5.2）
> **诚实原则**：作为独立审查者，若攻击确实成立则诚实承认并提修补方案；若攻击夸大或有反驳空间则给出具体反驳理由和代码证据。

---

## 总体判定

**9 个攻击点中：6 个成立（含 2 个可降级）、3 个成立但轻微。0 个可完全反驳。**

| 编号 | 反方严重性 | 反反方判定 | 理由 |
|------|-----------|-----------|------|
| F1 | 致命 | **成立，但降级为严重** | 代码证据确凿，但"致命"（方案完全失败）偏严——核心消融逻辑不受影响 |
| F2 | 致命 | **成立，但降级为严重** | 跨实验不一致属实，但 E2 内部消融自洽，"方案完全失败"不成立 |
| S1 | 严重 | **成立** | docstring 确实未更新，符号与实现矛盾 |
| S2 | 严重 | **成立** | 分箱变量语义偏移属实，docstring 未声明 |
| S3 | 严重 | **部分成立，降级为中等** | Stage3=Stage2 是数学必然非 bug，但汇总呈现误导且未声明 |
| S4 | 严重 | **成立** | variant 命名确实误导 |
| M1 | 轻微 | **成立** | in-sample 未标注 |
| M2 | 软微 | **成立** | 命名易混淆，当前代码正确 |
| M3 | 软微 | **成立** | 顺序拟合假设未声明 |

**核心结论**：反方攻击整体质量高，9 个攻击点均有代码证据支撑，无空泛指控。但 2 个"致命"攻击的严重性被夸大——核心消融逻辑（Stage 2 先 TS 再 binned-T）经独立验证确认正确，攻击点均为修复不完整或文档同步问题，非"方案完全失败"。需补充修复 F1（1 行）和 F2（1 行或跨文件），并同步处理 S1-S4 的文档/命名问题。

---

## 逐条回应

### 攻击点 F1: `calibration_reliability` 内 ECE 与 Brier reliability 分箱数不一致

- **反方主张**: L315 `brier_parts(..., n_bins=N_BINS)` 用 15 箱，但 L321 `ece(max_prob, correct)` 未传 `n_bins`，使用默认 10 箱。同一函数内两个校准指标分箱粒度不一致，且 L131 注释声称 `N_BINS=15` 同时用于 "Brier reliability / ECE" 是虚假的。
- **验证结果**: **成立，但严重性降级为严重（非致命）**
- **详细分析**:
  - **代码证据确凿**：
    - L131: `N_BINS = 15  # Brier reliability / ECE 评估分箱数` — 注释明确提及 ECE
    - L315: `brier_parts(max_prob, correct, n_bins=N_BINS)` — 传 15 ✓
    - L321: `ece(max_prob, correct)` — **未传 n_bins**，使用 `calibration.py` L199 默认值 `n_bins=10`
    - 经 grep 验证 `calibration.py` L199: `def ece(probs, labels, n_bins: int = 10, adaptive: bool = False)` — 默认 10 确认
  - **注释与实现矛盾确认**：L131 注释声称 `N_BINS=15` 用于 "Brier reliability / ECE"，但 ECE 实际用 10。注释确实虚假。
  - **指标间不可比性确认**：Brier reliability 和 ECE 在同一函数内用不同分箱粒度，联合解读确实受限。
- **反驳或降级理由**:
  - **"致命"（方案完全失败）偏严**：F1 影响的是校准指标的评估粒度一致性，**不影响消融的核心逻辑**（Stage 2 先 TS 再 binned-T 的嵌套关系）。消融的参数空间嵌套 Θ_1⊂Θ_2⊂Θ_3 仍成立，边际贡献的可解释性不受分箱数影响。
  - **ECE 与 Brier reliability 是不同指标**：ECE 是期望校准误差（L1 范数），Brier reliability 是 Murphy 分解的可靠性项（L2 范数）。两者用不同分箱数不会导致"方案完全失败"——只是联合报告时需注意粒度差异。实际分析中，研究者通常分别解读 ECE 和 Brier reliability，而非直接比较其数值大小。
  - **但攻击本质成立**：注释虚假 + 修复意图未完成（若意图是统一分箱）。降级为"严重"更合理——需修复但非"方案完全失败"。
- **修补方案**（1 行修改）:
  ```python
  # L321: 改为
  "ece": float(ece(max_prob, correct, n_bins=N_BINS)),
  ```
  或 alternatively，修改 L131 注释删除 "/ ECE"（若意图仅修 brier_parts）。**推荐前者**，与修复意图一致。

---

### 攻击点 F2: N_BINS=15 与全代码库不一致——跨实验 Brier reliability 横向比较失效

- **反方主张**: E2 用 N_BINS=15，E3/E4/E6 及 `calibration.py` 库默认均用 10。E2 的 Brier reliability/ECE 无法与 E3/E4/E6 横向比较。无 15 的合理性论证。
- **验证结果**: **成立，但严重性降级为严重（非致命）**
- **详细分析**:
  - **跨脚本不一致确认**（经 grep 验证）：
    | 脚本 | 常量 | 值 |
    |------|------|----|
    | `run_e2_ablation_discrimination.py` | `N_BINS` | **15** |
    | `run_e3_brier_dcr_ncv.py` L150 | `N_BINS` | **10** |
    | `run_e4_temperature_analysis.py` L141 | `BRIER_N_BINS` | **10** |
    | `run_e6_reliability_diagrams.py` L120 | `N_BINS` | **10** |
    | `calibration.py` L586 `brier_parts` 默认 | — | **10** |
    | `calibration.py` L199 `ece` 默认 | — | **10** |
  - **无 15 的合理性论证确认**：L131 仅写 "校准评估粒度"，未给出 15 vs 10 的理由。
  - **E4 显式对齐确认**：E4 L141 注释 `BRIER_N_BINS = 10  # 与 calibration.brier_parts 默认一致`，E2 修复引入 15 确实破坏了这个对齐。
- **反驳或降级理由**:
  - **"致命"（方案完全失败）偏严**：F2 影响的是跨实验比较的粒度一致性，**不影响 E2 内部消融的自洽性**。E2 的核心结论是 Stage1→Stage2→Stage3 的边际贡献，这些比较都在 E2 内部用同一分箱数（15），相对结论不受影响。
  - **E2 的消融结论是自洽的**：Stage1 vs Stage2 vs Stage3 的 Brier reliability 都用 15 箱，内部比较有效。跨实验比较（E2 vs E3/E4）确实受限，但这不是 E2 消融的"方案完全失败"——只是论文写作时需注意 E2 的 reliability 数值不能直接与 E3/E4 的数值并列。
  - **但攻击本质成立**：跨实验元分析确实失效，且无 15 的合理性论证。降级为"严重"更合理——需修复但非"方案完全失败"。
  - **补充反驳**：反方声称"15 箱系统性高估 reliability"——这个方向正确（更多箱→每箱样本更少→方差更大），但"系统性高估"偏强。实际上分箱数对 reliability 的影响取决于数据分布，非单调高估。在样本量充足时（n=4050，15 箱每箱约 270 样本），方差增加有限。但样本量不足时（冒烟 n=200），15 箱确实会有问题。
- **修补方案**（推荐方案 A，1 行修改）:
  ```python
  # 方案 A（推荐）: L131 改为 10，与全代码库对齐
  N_BINS = 10  # Brier reliability / ECE 评估分箱数（与 E3/E4/E6 及库默认一致）
  
  # 方案 B（若确需 15）: 同步修改 E3/E4/E6 并给出 15 的统计理由
  # 需在 docstring 中论证：如样本量 ≥ 1500 时 15 箱的 bias-variance tradeoff 更优
  ```
  **推荐方案 A**：与全代码库对齐，避免跨实验不一致，且 10 是校准评估的社区标准（Guo et al. 2017, Kumar et al. 2019 均用 10）。

---

### 攻击点 S1: docstring 嵌套符号 Θ_2={T_1..T_5} 与修复后实现不一致

- **反方主张**: L17 docstring 写 `Θ_2 = {T_1..T_5}`（5 参数，binned only），但修复后 Stage 2 实际是 `{T_global, T_1..T_5}`（6 参数，TS+binned）。docstring 未同步更新。
- **验证结果**: **成立**
- **详细分析**:
  - **docstring 证据**：L17 `Θ_1 = {T} ⊂ Θ_2 = {T_1..T_5} ⊂ Θ_3 = {T_1..T_5, τ_1..τ_K}` — 确实描述旧设计（binned only）
  - **实现证据**：
    - L465: `ts_params = fit_temperature_multiclass(cal_p, cal_y)` — 拟合 T_global
    - L467: `cal_s1 = apply_temperature_multiclass(cal_p, ts_params)` — 应用 TS
    - L476: `binned_params = fit_binned_temperature(cal_s1, cal_y)` — 在 TS 输出上拟合 binned-T
    - L477: `cal_s2 = apply_binned_temperature(cal_s1, binned_params)` — 应用 binned-T
    - Stage 2 实际参数空间 = `{T_global, T_1..T_5}`（6 参数）
  - **集合论问题确认**：`{T}` 不是 `{T_1..T_5}` 的子集（不同符号），当前 docstring 的嵌套关系在集合论上不成立。
- **反驳或修补**: 无法反驳，攻击成立。docstring 确实未同步更新。
- **修补方案**（1 行修改）:
  ```python
  # L17 改为
  #     Θ_1 = {T_global}          ⊂ Θ_2 = {T_global, T_1..T_5}    ⊂ Θ_3 = {T_global, T_1..T_5, τ_1..τ_K}
  ```

---

### 攻击点 S2: 分箱变量语义偏移 H(raw) → H(TS(p))——与 E4 不可比且 docstring 未声明

- **反方主张**: 修复后 E2 的 binned-T 分箱变量是 H(TS(p))（TS 校准后概率的熵），但 docstring L31 仍写 H(p)（暗示 raw）。E4 在 raw 概率上分箱（H(raw_p)），E2 修复后在 TS 输出上分箱（H(TS(p))），两者不可比。
- **验证结果**: **成立**
- **详细分析**:
  - **E2 修复后分箱变量确认**：
    - L476: `binned_params = fit_binned_temperature(cal_s1, cal_y)` — cal_s1 = TS(cal_p)
    - `fit_binned_temperature` L160: `ent = _entropy(cal_probs)` — cal_probs = cal_s1
    - 所以分箱变量 = H(cal_s1) = H(TS(cal_p)) = H(TS(p)) ✓
  - **E4 分箱变量确认**（经 grep 验证）：
    - E4 L365: `ent = predictive_entropy(cal_probs)` — cal_probs 是 raw 概率（E4 L465 `cal_probs = cal_ev["probs"]`）
    - E4 L507: `fit_binned_T(cal_probs, cal_labels, n_bins=N_BINS)` — 在 raw cal_probs 上拟合
    - 所以 E4 分箱变量 = H(raw_p) ✓
  - **docstring 未声明确认**：L31 `A1. binned temperature 的分箱变量=预测分布熵 H(p)=−Σp_k log p_k` — 未澄清 p 是 raw 还是 TS 输出
  - **不可比性确认**：TS with T>1 → 概率变平坦 → 熵增大；T<1 → 变尖锐 → 熵减小。同一样本在 H(raw_p) 和 H(TS(p)) 下可能落入不同分箱。
- **反驳或修补**: 无法反驳，攻击成立。
  - **补充说明**：修复引入 H(TS(p)) 作为分箱变量在**设计上是合理的**——TS 改变了不确定度分布，分箱应在校准后空间进行，使 binned-T 能捕获 TS 后的残余不校准。但 docstring 未声明此变化，且与 E4 的不可比性未声明。
- **修补方案**（1 行修改 + 边界声明）:
  ```python
  # L31 改为
  # A1. binned temperature 的分箱变量=预测分布熵 H(p)=−Σp_k log p_k。
  #     Stage 2 中 p = TS(raw)（在 TS 校准后概率上分箱），非 raw 概率。
  #     注: 此选择使 E2 的 binned-T 与 E4（在 raw 上分箱）不可直接比较。
  ```

---

### 攻击点 S3: Stage 3 Brier reliability 恒等于 Stage 2——消融度量退化

- **反方主张**: L484 `cal_s3, test_s3 = cal_s2, test_s2`（同一对象引用），`calibration_reliability` 不应用 threshold，所以 Stage 3 的 Brier reliability 与 Stage 2 逐字节相同。ΔReliability(Stage3−Stage2) ≡ 0，但汇总 L679 仍报告 Δ 暗示可能有非零值。
- **验证结果**: **部分成立，严重性降级为中等**
- **详细分析**:
  - **代码证据确凿**：
    - L484: `cal_s3, test_s3 = cal_s2, test_s2` — 同一对象引用 ✓
    - L491: `("stage3_ts_binned_threshold", test_s3)` — test_s3 = test_s2 ✓
    - L493: `rel = calibration_reliability(probs, test_y)` — 用 test_s3 = test_s2 ✓
    - `calibration_reliability` L312-313: `max_prob = probs.max(axis=1)`, `correct = (probs.argmax(axis=1) == labels)` — 不应用 threshold ✓
    - 所以 `calibration_reliability(test_s3, test_y) == calibration_reliability(test_s2, test_y)` 逐字节相同 ✓
  - **Δ(Stage3−Stage2) ≡ 0 确认**：对任何数据、任何模型、任何 seed，Stage 3 的 Brier reliability 行是 Stage 2 的精确副本。
- **反驳或降级理由**:
  - **这是数学必然，非实现 bug**：threshold optimization 改变 argmax（`predict_with_thresholds` L205: `argmax(p_k - τ_k)`），但**不改变概率值**。Brier reliability 基于概率（`max_prob`）和 correct mask（`argmax == label`）。代码中 `cal_s3 = cal_s2`（L484）明确声明"Stage3 概率=Stage2 概率"，这是设计选择——threshold 的贡献体现在**判别指标**（F1/PPV/NPV/MCC，L524-527 的 `threshold` variant 传了 `tau`），而非 Brier reliability。
  - **docstring 已部分暗示**：L19 `ΔReliability(Stage3−Stage2) = threshold opt 的边际贡献（控制 binned T 后）` — 这句暗示 threshold 对 reliability 有贡献，确实有误导。但 L25-26 `Stage 3 的 threshold optimization 改变 argmax→F1/PPV/NPV/MCC 改变` 暗示 threshold 主要影响判别指标。
  - **但汇总呈现确实误导**：L679 `Stage3 +threshold opt: {s2:.4f} → {s3:.4f} (Δ={s3-s2:+.4f})` 报告 Δ 暗示可能有非零值，但实际恒为 0。未声明 `Δ≡0 by construction`。
  - **降级为中等**：Stage3=Stage2 在 Brier reliability 上是数学必然（threshold 不改概率），非实现错误。消融设计的 4 行中 Stage 3 行对 reliability 确实冗余，但对判别指标有信息增量（L524-527）。问题在于汇总呈现未声明此特性，而非消融逻辑错误。
- **修补方案**（推荐方案 B，声明而非移除）:
  ```python
  # 方案 B（推荐）: 在 L679 汇总中显式声明
  print(f"  Stage3 +threshold opt:    {s2:.4f} → {s3:.4f} (Δ={s3-s2:+.4f})")
  print(f"    注: Δ≡0 by construction（threshold 不改概率，Brier reliability 基于概率）")
  print(f"    Stage 3 的贡献体现在判别指标（F1/PPV/NPV/MCC），见 discrimination 表")
  
  # 方案 A（更激进）: 在 calibration_reliability 中对 Stage 3 应用 threshold
  # 但这会改变 Brier reliability 的语义（基于概率 vs 基于阈值预测），不推荐
  ```

---

### 攻击点 S4: 判别指标 variant="binned" 命名误导——实际是 TS+binned

- **反方主张**: L520 variant 名 `"binned"`，但对应概率是 `TS+binned`（先 TS 再 binned-T）。variant 名暗示 "binned only"，与 ablation 表的 `"stage2_ts_binned"`（L490）命名不一致。
- **验证结果**: **成立**
- **详细分析**:
  - **代码证据确凿**：
    - L520-523: `("binned", apply_binned_temperature(apply_temperature_multiclass(probs, ts_params), binned_params), None)` — variant 名 "binned"，实际是 TS+binned ✓
    - L490: `("stage2_ts_binned", test_s2)` — ablation 表命名 "stage2_ts_binned"，含 "ts" ✓
    - 两表对同一语义的命名不一致 ✓
  - **注释承认语义变化**：L516-519 `# "binned" variant 须与 Stage 2 语义一致(TS+binned)` — 注释承认了，但 variant 名未改。
  - **下游分析误导风险确认**：`pd.read_csv(...).query("variant == 'binned'")` 会得到 TS+binned 结果，但分析者可能以为是 binned-only。
- **反驳或修补**: 无法反驳，攻击成立。
  - **补充说明**：这是 P0-1 攻击 F1 的命名残留——P0-1 攻击 Stage 2 实现是 binned only，修复改了实现但保留了旧命名。
- **修补方案**（1 行修改，但需注意向后兼容）:
  ```python
  # L520 改为
  ("ts_binned",
   apply_binned_temperature(
       apply_temperature_multiclass(probs, ts_params), binned_params),
   None),
  # 同步修改 L684 汇总中的 variant 列表
  # 注意: 若已有下游分析依赖 variant=="binned"，需提供迁移说明
  ```
  **向后兼容警告**：此修改会改变 CSV 的 variant 列值。若已有下游分析脚本查询 `variant == "binned"`，需同步更新。建议在 release notes 中声明此命名变更。

---

### 攻击点 M1: cal split "binned" variant 是 in-sample 拟合——乐观偏差未标注

- **反方主张**: cal split 的 "binned" variant = cal_s2，而 binned_params 在 cal_s1 上拟合 → in-sample apply。CSV 的 split 列区分了 cal/test，但未标注 cal 的 in-sample 性质。
- **验证结果**: **成立**
- **详细分析**:
  - **代码路径确认**：
    - L476: `binned_params = fit_binned_temperature(cal_s1, cal_y)` — 在 cal_s1 上拟合
    - L509-510: cal split 的 probs = cal_p
    - L521-522: `apply_binned_temperature(apply_temperature_multiclass(cal_p, ts_params), binned_params)` = `apply_binned_temperature(cal_s1, binned_params)` = cal_s2
    - cal split 的 "binned" variant = cal_s2，binned_params 在 cal_s1 上拟合 → in-sample apply ✓
  - **test split 是 out-of-sample 确认**：test split 用 test_s1（L522 `apply_temperature_multiclass(probs, ts_params)` where probs=test_p），binned_params 在 cal_s1 上拟合，test_s1 上 apply → out-of-sample ✓
- **反驳或修补**: 无法反驳，攻击成立。
  - **补充说明**：split 列已区分 cal/test，有经验的分析者应知道 cal 是拟合集。但反方指出"显式标注更安全"合理。
- **修补方案**（docstring 声明，最小改动）:
  ```python
  # 在 docstring L57-59 输出说明后添加:
  # 注: cal split 的 "binned"/"threshold" variant 是 in-sample（binned_params 在 cal 上拟合并 apply），
  #     test split 是 out-of-sample。比较 cal vs test 可评估泛化能力。
  ```

---

### 攻击点 M2: N_BINS 与 N_BINS_TEMPERATURE 命名易混淆

- **反方主张**: `N_BINS`（15，评估分箱）和 `N_BINS_TEMPERATURE`（5，温度分箱）命名相近，未来维护者易混淆。
- **验证结果**: **成立**
- **详细分析**:
  - **代码证据**：
    - L129: `N_BINS_TEMPERATURE = 5` — 温度分箱
    - L131: `N_BINS = 15` — 评估分箱
    - L148: `fit_binned_temperature(..., n_bins=N_BINS_TEMPERATURE)` — 正确用 5 ✓
    - L315: `brier_parts(..., n_bins=N_BINS)` — 正确用 15 ✓
  - **当前代码正确**：两个常量未混淆使用。
  - **维护风险确认**：命名相近，未来修改时易误传。
- **反驳或修补**: 无法反驳，攻击成立但轻微。
- **修补方案**（重命名，可选）:
  ```python
  # L129-131 改为
  N_BINS_TEMP = 5          # binned temperature 箱数（温度分箱）
  MIN_SAMPLES_PER_BIN = 10 # 每箱最少样本数
  N_BINS_EVAL = 15         # Brier reliability / ECE 评估分箱数（评估分箱）
  # 同步更新 L148 和 L315 的引用
  ```
  **优先级低**：当前代码正确，重命名仅为可维护性。若 F2 采纳方案 A（N_BINS=10），可一并重命名。

---

### 攻击点 M3: T_global 在 Stage 2 未联合重拟合——顺序拟合假设未声明

- **反方主张**: Stage 2 复用 Stage 1 的 ts_params（T_global 在 raw 上拟合），然后 in TS 输出上拟合 binned-T。这是顺序拟合非联合优化，但 docstring 未声明。
- **验证结果**: **成立**
- **详细分析**:
  - **代码证据**：
    - L465: `ts_params = fit_temperature_multiclass(cal_p, cal_y)` — T_global on raw
    - L476: `binned_params = fit_binned_temperature(cal_s1, cal_y)` — binned-T on TS output (cal_s1)
    - T_global 复用 Stage 1 结果，非联合优化 {T_global, T_1..T_5} simultaneously ✓
  - **设计合理性确认**：顺序拟合保证 Stage 1 ⊂ Stage 2 的嵌套（Stage 2 的 T_global = Stage 1 的 T_global）。联合优化会破坏嵌套（Stage 2 的 T_global ≠ Stage 1 的 T_global），使边际贡献不可解释。**这是正确的设计选择**。
  - **docstring 未声明确认**：L29-39 的假设 A1-A3 未提及顺序拟合。
- **反驳或修补**: 无法反驳，攻击成立但轻微。
  - **补充说明**：顺序拟合是保证嵌套的必要条件，设计上合理。反方也承认"这是正确的设计选择"。
- **修补方案**（docstring 声明，1 行）:
  ```python
  # 在 docstring 假设中添加（L39 后）:
  # A4. Stage 2 的 T_global 复用 Stage 1 拟合结果（顺序拟合），非联合优化——
  #     保证 Stage1 ⊂ Stage2 嵌套但可能次优于联合 NLL 最小化。
  ```

---

## 结论

### 攻击质量评估

反方攻击报告**整体质量高**：
- 9 个攻击点均有具体代码行号和可验证证据，无空泛指控
- 7 个攻击维度（反例构造/逻辑断链/隐含假设/边界失效/自相矛盾/量级错误/语义偏移）全覆盖
- 对修复核心逻辑的诚实评估（第 5 节）客观准确——确认 Stage 2 核心逻辑正确

### 严重性校准

反方将 F1、F2 标为"致命"（方案完全失败），经独立审查**降级为"严重"**：
- F1、F2 均为修复不完整或跨实验一致性问题，**不影响 E2 内部消融的核心逻辑**（Stage 2 先 TS 再 binned-T 的嵌套关系成立）
- "致命"应保留给"核心消融逻辑错误"（如 P0-1 的原始问题：Stage 2 实现 binned only 破坏嵌套）
- F1、F2 需补充修复但非"方案完全失败"

S3 标为"严重"，经独立审查**降级为"中等"**：
- Stage3=Stage2 在 Brier reliability 上是数学必然（threshold 不改概率），非实现错误
- 问题在于汇总呈现未声明此特性，而非消融逻辑错误

### 需回炉重修的攻击点

| 优先级 | 编号 | 修补内容 | 工作量 |
|--------|------|----------|--------|
| **P0** | F1 | L321 `ece(max_prob, correct)` → `ece(max_prob, correct, n_bins=N_BINS)` | 1 行 |
| **P0** | F2 | L131 `N_BINS = 15` → `N_BINS = 10`（与 E3/E4/E6 对齐） | 1 行 |
| **P1** | S1 | L17 嵌套符号更新为 `Θ_2 = {T_global, T_1..T_5}` | 1 行 |
| **P1** | S4 | L520 variant 名 `"binned"` → `"ts_binned"`（+下游同步） | 1 行 + 迁移说明 |
| **P2** | S2 | L31 假设 A1 声明分箱变量为 H(TS(p)) + E4 不可比声明 | 1-2 行 |
| **P2** | S3 | L679 汇总声明 `Δ(Stage3−Stage2)≡0 by construction` | 1-2 行 |
| **P3** | M1 | docstring 声明 cal split in-sample 性质 | 1 行 |
| **P3** | M2 | 重命名 N_BINS → N_BINS_EVAL（可选） | 3-4 行 |
| **P3** | M3 | docstring 声明顺序拟合假设 A4 | 1 行 |

### 可接受的攻击点

无完全可反驳的攻击点。所有 9 个攻击点均成立（含 3 个降级）。反方攻击经得起审查，正方需补充修复。

### 最终判定

**P0-3 修复的核心逻辑（Stage 2 先 TS 再 binned-T）经独立验证确认正确**，P0-1 的 F1 攻击点已被有效解决。但修复**不完整**（F1: ECE 未同步修复）且**引入了新的跨实验不一致**（F2: N_BINS=15 vs 全代码库 10）。S1-S4 四个严重问题为文档同步和命名问题，不影响核心逻辑但需在论文写作前修复。M1-M3 三个轻微问题为可维护性改进。

**修复评级：部分有效，需补充修复 F1（1 行）和 F2（1 行）达到可发表标准。**
