# E2 实验脚本反方攻击报告

> **反方挑刺代理-E2 交付**。本报告对正方设计的 `scripts/run_e2_ablation_discrimination.py`（695 行）进行逐行审查，结合 `docs/Q2_UPGRADE_PROPOSAL_R5.md` §3.2 E2 的设计声称，寻找消融实验 + 判别指标逻辑中的反例、逻辑断链、隐含假设不成立、边界失效、自相矛盾、量级错误、语义偏移。
> **攻击日期**：2026-09-09
> **攻击对象**：`run_e2_ablation_discrimination.py`（695 行）+ `Q2_UPGRADE_PROPOSAL_R5.md` §3.2 E2（lines 189-229）
> **攻击代理**：反方挑刺代理-E2（GLM-5.2）
> **诚实原则**：对每条攻击给出可验证的具体反例或代码行号，不允许"可能有问题"的空泛指控。
> **攻击维度**：反例构造 / 逻辑断链 / 隐含假设 / 边界失效 / 自相矛盾 / 量级错误 / 语义偏移（7 维度全覆盖）

---

## 0. 攻击审查概述

### 攻击数量统计

| 严重性 | 数量 | 编号 |
|--------|------|------|
| **致命** | 2 | F1, F2 |
| **严重** | 6 | S1, S2, S3, S4, S5, S6 |
| **轻微** | 7 | M1-M7 |
| **合计** | 15 | — |

### 整体评估

E2 脚本存在 **2 个致命攻击**，任一独立成立即可使消融实验的结论失效：

1. **F1（Stage 2 实现与设计声称不符）**：R5 方案和脚本 docstring 均声称 Stage 2 = "TS + binned temperature"（组合设计），但代码实现是 "binned only"（替换设计）——直接在 raw 概率上拟合分箱温度，**未先应用全局 TS**。这导致边际贡献的解释（"控制全局 T 后 binned T 的边际贡献"）在数学上不成立。

2. **F2（threshold optimization 用 Nelder-Mead 优化 piecewise-constant 目标）**：macro-F1 关于阈值 τ 是分段常数函数（梯度几乎处处为 0），Nelder-Mead 在此类函数上几乎必然立即收敛于 τ≈0（no-op）。且 docstring 声称用"坐标下降+网格搜索"但代码用 Nelder-Mead——**文档与代码不一致**。Stage 3 的阈值优化大概率不产生任何改变。

6 个严重攻击进一步削弱实验的可信度：Stage 3 Brier reliability 恒等于 Stage 2（S1）、DCR 未计算（S2）、缓存键不含 limit 导致冒烟跑污染全量跑（S3）、threshold 始终在 OOD 下迁移（S4）、无统计检验（S5）、top-label Brier 与 R5 的多分类 Brier 分解论证语义偏移（S6）。

**结论：E2 脚本在当前形态下不能支持 R5 方案 §3.2 E2 的任何消融结论。需重大重写。**

---

## 1. 致命攻击（方案完全失败）

### F1：Stage 2 实现"binned only"，非设计声称的"TS + binned"——边际贡献解释失效

**攻击维度**：语义偏移 + 反例构造

**设计声称**（R5 §3.2 E2, line 201 + 脚本 docstring line 8-9）：
> - **(2) TS + binned temperature**：TS + 分箱温度（按 uncertainty score 分 5 bin，每 bin 独立估计 T）
> - Stage 2: TS + binned T — 按预测熵(不确定度)分 5 箱，每箱一个 T

脚本 docstring（line 17-19）进一步声称嵌套结构与边际贡献解释：
> Θ_1 = {T} ⊂ Θ_2 = {T_1..T_5} ⊂ Θ_3 = {T_1..T_5, τ_1..τ_K}
> ΔReliability(Stage2−Stage1) = binned T 的边际贡献（**控制全局 T 后**）

**代码实现**（line 462-471）：
```python
# ===== Stage 1: TS only =====
ts_params = fit_temperature_multiclass(cal_p, cal_y)
T_global = float(ts_params["T"])
cal_s1 = apply_temperature_multiclass(cal_p, ts_params)
test_s1 = apply_temperature_multiclass(test_p, ts_params)

# ===== Stage 2: TS + binned temperature =====
binned_params = fit_binned_temperature(cal_p, cal_y)       # ← 在 RAW cal_p 上拟合
cal_s2 = apply_binned_temperature(cal_p, binned_params)     # ← 在 RAW cal_p 上应用
test_s2 = apply_binned_temperature(test_p, binned_params)   # ← 在 RAW test_p 上应用
```

**反例构造**：
- Stage 2 的 `fit_binned_temperature(cal_p, cal_y)` 在 **raw 概率** `cal_p` 上拟合，**不是**在 Stage 1 输出 `cal_s1` 上拟合。
- Stage 2 的 `apply_binned_temperature(cal_p, ...)` 在 **raw 概率** 上应用，**不是** `apply_binned_temperature(cal_s1, ...)`。
- 因此 Stage 2 = "binned temperature only"（每箱独立 T，直接替换 raw），**不是** "TS + binned"（先全局 TS，再在 TS 输出上分箱）。

**为什么致命**：
1. **边际贡献解释错误**：docstring 声称 "ΔReliability(Stage2−Stage1) = binned T 的边际贡献（控制全局 T 后）"。但代码中 Stage 2 根本没有"控制全局 T"——它完全不用 `ts_params`。实际测量的是 "5 个分箱 T vs 1 个全局 T"（灵活度对比），**不是** "在全局 T 基础上增加分箱 T 的增量贡献"（组合对比）。
2. **参数空间嵌套声称被破坏**：docstring 声称 Θ_1 = {T} ⊂ Θ_2 = {T_1..T_5}。作为参数集合这成立（所有 T_b 相等时退化为 Stage 1），但"嵌套保证边际贡献可加性解释"不成立——可加性解释需要 Stage 2 在 Stage 1 输出上构建（条件贡献），而非独立替换。
3. **论文文本将基于错误解释**：若按 R5 方案写论文，会声称"在控制全局温度缩放后，分箱温度的边际贡献为 ΔReliability"，但代码测量的是"分箱温度相对于单一温度的改善"——两者语义不同。前者是增量（additive），后者是替换（substitution）。

**可验证反例**：
- 设 raw 概率为 p，全局 T=2.0，分箱 T=[0.5, 2.0, 2.0, 2.0, 2.0]（仅最低熵箱不同）。
- **设计声称的 Stage 2**：先 apply T=2.0 得 p'，再在 p' 上按熵分箱，最低熵箱 apply T=0.5。结果：最低熵箱的有效 T = 2.0 × 0.5 = 1.0（无校准），其他箱 T = 2.0。
- **代码实现的 Stage 2**：直接在 p 上分箱，最低熵箱 apply T=0.5，其他箱 apply T=2.0。结果：最低熵箱 T=0.5，其他箱 T=2.0。
- 两者结果**不同**，Brier reliability **不同**，边际贡献**不同**。

**严重程度**：**致命**——消融实验的核心解释框架失效。任何基于此代码的论文声称"控制全局 T 后分箱 T 的边际贡献"都是虚假的。

**修复建议**：若要实现设计声称的"TS + binned"，Stage 2 应改为：
```python
binned_params = fit_binned_temperature(cal_s1, cal_y)  # 在 TS 输出上拟合
cal_s2 = apply_binned_temperature(cal_s1, binned_params)
test_s2 = apply_binned_temperature(test_s1, binned_params)
```
或者修改 docstring/R5 方案的声称，将 Stage 2 改为 "binned temperature only"（替换设计），并修正边际贡献解释为 "5 分箱 T vs 1 全局 T 的灵活度收益"。

---

### F2：threshold optimization 用 Nelder-Mead 优化 piecewise-constant macro-F1——几乎必然 no-op + docstring 虚假声称网格搜索

**攻击维度**：量级错误 + 自相矛盾

**docstring 声称**（line 213-216）：
> 用坐标下降+网格搜索（每类在 [-0.3, 0.3] 上 61 个点）。
> 目标=macro-F1（对类别不平衡更稳健 than accuracy）。

**代码实现**（line 218-230）：
```python
def optimize_thresholds(cal_probs, cal_labels, n_classes):
    from scipy.optimize import minimize
    def neg_macro_f1(tau):
        preds = predict_with_thresholds(cal_probs, tau)
        return -f1_score(cal_labels, preds, average="macro", zero_division=0)
    res = minimize(
        neg_macro_f1,
        x0=np.zeros(n_classes),
        method="Nelder-Mead",
        options={"maxiter": 2000, "xatol": 1e-3, "fatol": 1e-5},
    )
    return np.clip(res.x, -0.5, 0.5)
```

**攻击点 1：docstring 与代码不一致**
- docstring 声称 "坐标下降+网格搜索（每类在 [-0.3, 0.3] 上 61 个点）"
- 代码用 `scipy.optimize.minimize(method="Nelder-Mead")`——**不是**网格搜索，**不是**坐标下降
- 搜索范围 [-0.3, 0.3] 未在代码中体现；代码用 `np.clip(res.x, -0.5, 0.5)`（范围 [-0.5, 0.5]），与 docstring 的 [-0.3, 0.3] 不一致

**攻击点 2：Nelder-Mead 不适合 piecewise-constant 目标函数**
- `predict_with_thresholds` 计算 `(probs - tau).argmax(axis=1)`。argmax 是分段常数——τ 的微小变化不改变 argmax，直到某个阈值跨越概率差。
- `f1_score` 基于分段常数的预测，因此 macro-F1 关于 τ 是**分段常数函数**，梯度 = 0 几乎处处成立。
- Nelder-Mead 在分段常数函数上的行为：
  1. 初始单纯形围绕 x0=0 构建（默认扰动 ≈ 0.05）
  2. 若所有单纯形顶点的 macro-F1 相同（大概率，因为 0.05 的扰动通常不跨越概率差阈值），Nelder-Mead 认为已处于局部最优
  3. 单纯形收缩（xatol=1e-3），无法找到改善方向，返回 τ ≈ 0
- 结果：**threshold optimization 几乎必然返回 τ ≈ 0**，Stage 3 退化为 Stage 2

**反例构造**：
- 设 cal_probs 有 100 个样本，5 类，概率范围 [0.15, 0.35]
- τ=0 时 macro-F1 = 0.62
- τ=[0.02, 0, 0, 0, 0] 时（仅类 0 阈值微调），若 0.02 不跨越任何概率差，macro-F1 仍 = 0.62
- Nelder-Mead 初始单纯形顶点 τ ≈ [±0.05, 0, 0, 0, 0] 等，若 0.05 不跨越概率差，所有顶点 F1=0.62
- Nelder-Mead 收敛 → 返回 τ ≈ 0 → Stage 3 = Stage 2

**为什么致命**：
1. Stage 3 的阈值优化大概率不产生任何改变，整个 Stage 3 消融是 no-op
2. 论文将报告 "threshold optimization 无边际改善"（Stage 3 ≈ Stage 2），但这是**优化器失效**的结果，不是"阈值优化无用"的真实结论
3. docstring 虚假声称网格搜索——审稿人若查代码会发现声称与实现不符

**严重程度**：**致命**——Stage 3 消融因优化器选择不当而失效，且 docstring 虚假声称。

**修复建议**：实现 docstring 声称的坐标下降 + 网格搜索：
```python
def optimize_thresholds(cal_probs, cal_labels, n_classes):
    tau = np.zeros(n_classes)
    grid = np.linspace(-0.3, 0.3, 61)
    for _ in range(3):  # 坐标下降 3 轮
        for k in range(n_classes):
            best_f1, best_t = -1, 0.0
            for t in grid:
                tau_try = tau.copy(); tau_try[k] = t
                f1 = f1_score(cal_labels, predict_with_thresholds(cal_probs, tau_try), average="macro", zero_division=0)
                if f1 > best_f1: best_f1, best_t = f1, t
            tau[k] = best_t
    return tau
```

---

## 2. 严重攻击（需重大修补）

### S1：Stage 3 Brier reliability 恒等于 Stage 2——消融表 Stage 3 行是冗余常量

**攻击维度**：逻辑断链

**代码**（line 474-477）：
```python
# ===== Stage 3: TS + binned + threshold optimization =====
tau = optimize_thresholds(cal_s2, cal_y, K)
# Stage3 概率=Stage2 概率（threshold 只改 argmax，不改概率）
cal_s3, test_s3 = cal_s2, test_s2
```

**消融表计算**（line 480-497）：
```python
for stage_name, probs in [
    ("raw", test_p),
    ("stage1_ts", test_s1),
    ("stage2_ts_binned", test_s2),
    ("stage3_ts_binned_threshold", test_s3),  # ← test_s3 IS test_s2
]:
    rel = calibration_reliability(probs, test_y)
```

**攻击**：
- `test_s3 = test_s2`（同一对象引用），因此 `calibration_reliability(test_s3, test_y) == calibration_reliability(test_s2, test_y)` **恒等**。
- 消融表的 `stage3_ts_binned_threshold` 行的 `brier_reliability` **永远等于** `stage2_ts_binned` 行。
- 脚本 line 662 的边际贡献汇总 `print(f"Stage3 +threshold opt: {s2:.4f} → {s3:.4f} (Δ={s3-s2:+.4f})")` 将**永远**输出 `Δ=+0.0000`。

**为什么严重**：
1. 消融表包含一个**结构性恒等行**，浪费空间且误导读者以为 Stage 3 可能改变 Brier reliability
2. R5 方案 §3.2 E2（line 203）声称"比较三者的 Brier reliability 和 DCR"——threshold 的贡献应通过 DCR 体现，而非 Brier reliability。但脚本将 Stage 3 放入 Brier reliability 消融表（恒等），却**不计算 DCR**（见 S2）
3. 审稿人会问："Stage 3 的 Brier reliability 与 Stage 2 完全相同，为什么单独列一行？作者是否不理解 threshold 不改变概率？"

**严重程度**：**严重**——消融表设计不当，Stage 3 行是恒等常量。

---

### S2：DCR（阈值化决策改变率）未计算——R5 E2 设计的核心指标缺失

**攻击维度**：隐含假设

**R5 设计声称**（line 203）：
> 比较三者的 **Brier reliability** 和 **阈值化决策改变率（DCR）**

**代码实现**：grep `DCR` / `decision_change` in `run_e2_ablation_discrimination.py` → **零匹配**。脚本计算 AUROC/AUPRC/F1/PPV/NPV/MCC（line 251-298），但**不计算 DCR**。

**攻击**：
- DCR 是 R5 E2 设计中 threshold 贡献的核心度量（"TS 后预测决策的变化率"）
- R5 §3.2 E3（line 290-293）定义 DCR = |{x : 1[p_c^TS(x) > τ] ≠ 1[p_c^pre(x) > τ]}| / N
- 脚本不计算 DCR，意味着 **threshold optimization 的贡献无法被量化**——只能通过 F1/PPV/NPV/MCC 的变化间接推断
- 但 F1/PPV/NPV/MCC 的变化受多种因素影响（阈值改变 argmax → 混淆矩阵变化 → 所有指标变化），不等于 DCR

**为什么严重**：
1. R5 方案声称 E2 会报告 DCR，但代码不实现——**设计声称与实现不一致**
2. 没有 DCR，"threshold optimization 的边际贡献"无法直接回答
3. 结合 F2（threshold 优化是 no-op），DCR 即使计算了也大概率 = 0

**严重程度**：**严重**——核心指标缺失，E2 不能回答 R5 设计的问题。

---

### S3：缓存键不含 `--limit` 和 subspace——冒烟跑污染全量跑

**攻击维度**：边界失效

**代码**（line 374）：
```python
cache_file = CACHE_DIR / f"{source}_{target}_{arch}_seed{seed}.npz"
```

**攻击**：
- 缓存键 = `{source}_{target}_{arch}_seed{seed}`，**不含** `args.limit`、`subspace`、`num_classes`
- `--use-cache` 默认为 True（line 590）
- **反例**：
  1. 先跑 `python run_e2_ablation_discrimination.py --limit 240`（冒烟，每 split 60 样本）
  2. 缓存写入 `{source}_{target}_{arch}_seed{seed}.npz`（60 样本的 probs）
  3. 再跑 `python run_e2_ablation_discrimination.py`（全量，无 --limit）
  4. 脚本加载缓存 → **用 60 样本的 probs 报告全量结果**
  5. 所有 Brier reliability、AUROC 等指标基于 60 样本，但论文声称基于全量
- 同理，subspace 变化（如 SUBSPACE_CPSC 定义改变）后，旧缓存仍被加载

**为什么严重**：
1. 这是**静默数据污染**——无警告、无错误，结果完全错误但看起来正常
2. 冒烟测试是开发常规操作，极易触发此 bug
3. 论文结果可能基于被污染的缓存，且无法检测

**严重程度**：**严重**——缓存键设计缺陷导致静默结果污染。

**修复建议**：缓存键加入 limit 和 subspace hash：
```python
import hashlib
config_hash = hashlib.md5(str((args.limit, subspace)).encode()).hexdigest()[:8]
cache_file = CACHE_DIR / f"{source}_{target}_{arch}_seed{seed}_{config_hash}.npz"
```

---

### S4：threshold 在 source-cal 上拟合，应用于 target-test——ID 假设始终不成立

**攻击维度**：隐含假设

**docstring 声称**（line 36-37）：
> A2. threshold optimization 在 cal 集上拟合、test 集上评估。
> 假设：cal 与 test 同分布（ID 假设）；OOD 下阈值迁移有衰减

**代码实现**（line 407-417）：
```python
# source-cal 前向
src_ds, _ = _build(source, DATA_DIRS[source], seed, args.limit, subspace=subspace)
cal_loader = create_dataloader(src_ds["cal"], ...)
cal_eval = evaluate(model, cal_loader, ...)

# target-test 前向
tgt_ds, _ = _build(target, DATA_DIRS[target], seed, args.limit, subspace=subspace)
tgt_loader = create_dataloader(tgt_ds["test"], ...)
tgt_eval = evaluate(model, tgt_loader, ...)
```

**攻击**：
- `cal_p` = **source 域** cal split 的概率（如 PTB-XL cal）
- `test_p` = **target 域** test split 的概率（如 Chapman test）
- threshold 在 `cal_s2`（source cal 的 binned 校准概率）上拟合，应用于 `test_s2`（target test 的 binned 校准概率）
- **source ≠ target**（60 实验全部是跨语料库迁移），因此 cal 与 test **始终**来自不同分布
- A2 的 "ID 假设" **从未满足**——"OOD 下阈值迁移有衰减"不是例外，而是**所有 60 实验的默认场景**

**为什么严重**：
1. docstring 将 OOD 列为"衰减"例外，但 OOD 是默认——**假设与实验设计矛盾**
2. threshold 在 source cal 上的最优 τ，迁移到 target test 上的衰减程度**未量化**——脚本不报告 cal 上 threshold 的 F1（in-sample 上界）vs test 上的 F1（OOD），无法评估迁移衰减
3. 实际上 discrimination metrics 的 cal/test 两个 split 都在 CSV 中（line 502-505），但 cal split 用的是 source cal（threshold 拟合集本身）→ in-sample 乐观估计；test split 用 target test → OOD 悲观估计。审稿人可对比，但脚本不主动报告 gap

**严重程度**：**严重**——threshold 的迁移性未评估，ID 假设与实验设计矛盾。

---

### S5：无统计检验——消融差异的显著性无法判断 + 无多重比较校正

**攻击维度**：逻辑断链

**代码**：grep `t_test` / `wilcoxon` / `fdr` / `pvalue` in `run_e2_ablation_discrimination.py` → **零匹配**。

**攻击**：
- 脚本报告 60 实验的 mean±std（line 647-662），但**无配对 t 检验 / Wilcoxon / bootstrap CI** for ΔReliability(Stage2−Stage1) 或 ΔReliability(Stage3−Stage2)
- R5 §3.2 E3（line 259-264）对 H1-primary 用配对 t 检验 + Cohen's d + 95% CI，但 E2 **无任何统计检验**
- 消融结论 "若 (2) > (1) 则支持分箱温度"（R5 line 209）需要统计显著性判断——仅凭 mean 差异无法区分真实效应与噪声
- 60 实验 × 3 阶段比较 = 180 次检验，**无 FDR 校正**（R5 §3.2 E3 对 secondary endpoints 用 BH FDR，但 E2 无）

**反例**：
- 设 ΔReliability(Stage2−Stage1) 的 mean = 0.001，std = 0.005，n=60
- 配对 t 检验：t = 0.001 / (0.005/√60) ≈ 1.55，p ≈ 0.13 → **不显著**
- 脚本会报告 "Stage2 → Stage1: Δ=+0.001000"，看似有改善，但实际不显著
- 论文若声称 "分箱温度有边际改善"，基于未检验的 descriptive 统计——**过度推断**

**为什么严重**：
1. 消融结论无统计支撑——R5 的 "若 (2) > (1)" 判断无统计基础
2. 60 实验的 mean±std 隐藏了跨实验异质性——某些实验可能 Δ>0，某些 Δ<0，mean 接近 0
3. 无 FDR 校正，多重比较下假阳性率膨胀

**严重程度**：**严重**——消融结论无统计推断基础。

---

### S6：top-label Brier reliability vs R5 多分类 Brier 分解论证——语义偏移

**攻击维度**：语义偏移

**R5 理论声称**（line 248-253）：
> Brier score decomposes as Brier = Reliability - Resolution + Uncertainty
> **Key theoretical property**: TS only affects the **Reliability** component, not the **Resolution** component.
> based on the Brier decomposition, we select Brier reliability as the primary metric

**代码实现**（line 305-321）：
```python
def calibration_reliability(probs, labels):
    max_prob = probs.max(axis=1)
    correct = (probs.argmax(axis=1) == labels).astype(float)
    b_total, rel, res, unc = brier_parts(max_prob, correct)
```

**攻击**：
- R5 的 Brier 分解论证针对**多分类 Brier score**（K 类，每个样本对每个类有预测概率）
- 代码实现的是 **top-label Brier**：将多分类问题二值化为 (max_prob, correct_mask)，然后对二值化后的 (max_prob, correct) 计算 Brier 分解
- **语义偏移**：
  1. 多分类 Brier = (1/n) Σ_i Σ_k (p_ik - y_ik)² → TS 对此的 Reliability/Resolution 分解有理论保证
  2. top-label Brier = (1/n) Σ_i (max(p_i) - 1[argmax=i==y_i])² → 这是**二分类** Brier，其分解性质不同
  3. TS 保持 argmax → `correct` 不变；TS 改变 `max_prob` → top-label Brier 的 Reliability 改变。但 R5 声称 "TS 只影响 Reliability 不影响 Resolution" 是对**多分类 Brier** 的声称，对 top-label Brier 不直接成立
- top-label Brier 的 Resolution = Σ_bin n_bin/n * (avg_label_bin - base_rate)²，其中 base_rate = accuracy。TS 不改变 argmax → 不改变 correct → 不改变分箱内的 avg_label → **Resolution 不变**。所以 TS 确实只影响 top-label Reliability。但这是**因为 argmax 不变**，不是因为 R5 声称的"多分类 Brier 分解"理论。

**为什么严重**：
1. R5 的理论论证（多分类 Brier 分解）与实现指标（top-label Brier）**不直接对应**
2. 审稿人若查代码会发现：论文用多分类 Brier 分解论证，但代码计算 top-label Brier——**理论-实现脱节**
3. top-label Brier 的 TS 性质（argmax 不变 → Resolution 不变）是**更弱**的论证，不依赖 Murphy 分解

**严重程度**：**严重**——理论论证与实现指标语义偏移，论文需重新论证 top-label Brier 的 TS 性质。

---

## 3. 轻微攻击（需小修补）

### M1：诚实校验只检查 Stage 1 ΔAUROC，不检查 Stage 2 binned 对 AUROC 的影响

**攻击维度**：边界失效

**代码**（line 521-525）：`delta_auroc = ts_disc["auroc"] - raw_disc["auroc"]`——只比较 Stage 1 (TS) vs raw。

**攻击**：Stage 2 用不同样本不同 T（binned），**不是**全局单调变换，对 AUROC 的影响可能比 Stage 1 更大。脚本不报告 ΔAUROC(Stage2−raw)，审稿人无法评估 binned temperature 对判别指标的影响。docstring（line 25-26）只讨论 TS 对 AUROC 的影响，未讨论 binned 的影响。

**严重程度**：轻微——CSV 中有 Stage 2 的 AUROC，可后处理计算，但脚本不主动报告。

---

### M2：T_binned 统计含 fallback T=1.0——mean/min/max 不区分拟合 T 与 fallback

**代码**（line 491-493）：
```python
"T_binned_mean": np.mean(T_binned) if "binned" in stage_name else np.nan,
"T_binned_min": np.min(T_binned) if "binned" in stage_name else np.nan,
"T_binned_max": np.max(T_binned) if "binned" in stage_name else np.nan,
```

**攻击**：`T_binned` 中不足 10 样本的箱被设为 T=1.0（line 168-169）。mean/min/max 包含这些 fallback 值，不区分"拟合的 T"与"fallback T=1.0"。若 3/5 箱 fallback，mean 主要反映 1.0，掩盖实际拟合的 T 值。

**严重程度**：轻微——不影响消融结论，但误导 T 分布分析。

---

### M3：discrimination "threshold" variant 只有 binned+threshold，缺少 raw+threshold / ts+threshold

**代码**（line 506-511）：
```python
for variant, v_probs, v_tau in [
    ("raw", probs, None),
    ("ts", apply_temperature_multiclass(probs, ts_params), None),
    ("binned", apply_binned_temperature(probs, binned_params), None),
    ("threshold", apply_binned_temperature(probs, binned_params), tau),
]:
```

**攻击**：threshold 只与 binned 组合，不与 raw 或 ts 组合。无法隔离 "threshold 在 raw 上" 或 "threshold 在 TS 上" 的贡献。消融不完整——缺少 raw+threshold 和 ts+threshold 两个 variant。

**严重程度**：轻微——设计限制，不影响现有结论的正确性，但限制消融的完整性。

---

### M4：`fit_binned_temperature` 的 broad exception catch 静默吞掉所有错误

**代码**（line 171-175）：
```python
try:
    params = fit_temperature_multiclass(cal_probs[mask], cal_labels[mask])
    temperatures.append(float(params["T"]))
except Exception:
    temperatures.append(1.0)
```

**攻击**：`except Exception` 捕获所有异常（包括 NaN 输入、shape 不匹配等），静默设 T=1.0。若 `cal_probs` 含 NaN（模型输出异常），该箱被静默跳过，无 warning。掩盖数据质量问题。

**严重程度**：轻微——不影响正常情况下的结果，但掩盖异常。

---

### M5：`brier_parts` 用 10 等宽分箱——R5 未声明分箱策略

**代码**（`calibration.py` line 603）：`bins = np.linspace(0, 1, 11)`——10 个等宽分箱。

**攻击**：Brier reliability 依赖分箱策略。10 等宽分箱是常见选择，但 R5 方案未声明。不同分箱（如 15 等宽、等频）→ 不同 reliability → 可能改变消融结论。审稿人可能问："为什么 10 等宽？敏感性分析？"

**严重程度**：轻微——分箱选择合理但未声明/未做敏感性。

---

### M6：F1/MCC 的 argmax 不变性未数值验证

**攻击**：docstring 声称 "TS 保持 argmax → F1/MCC 不变"（line 24-25）。代码计算了 TS 后的 F1/MCC（line 506-511 variant="ts"），但**不与 raw 的 F1/MCC 对比验证**。若数值精度导致 argmax 改变（两个 logit 极接近时，除以 T 后浮点排序可能翻转），F1 可能微变。脚本不检查 |F1_ts - F1_raw| == 0。

**严重程度**：轻微——数学上应精确不变，数值上可能微变，但不影响结论。

---

### M7：`discover_checkpoints` 用 `split("_", 1)` 解析 pair 名——数据集名含下划线会断裂

**代码**（line 561）：`source, target = pair_dir.name.split("_", 1)`

**攻击**：若未来数据集名含下划线（如 `ptbxl_v2`），`split("_", 1)` 会错误解析。当前数据集名（ptbxl, chapman, cpsc）无下划线，安全。但这是潜在脆弱性。

**严重程度**：轻微——当前不触发，但代码脆弱。

---

## 4. 7 维度攻击总结

| 维度 | 攻击点 | 严重性 |
|------|--------|--------|
| **反例构造** | F1（Stage 2 实现与设计不符，构造具体 T 组合显示结果不同） | 致命 |
| **逻辑断链** | S1（Stage 3 = Stage 2 恒等，消融表冗余）、S5（无统计检验，消融差异显著性未知） | 严重 |
| **隐含假设** | S2（DCR 未计算）、S4（ID 假设始终不成立）、S6（top-label vs 多分类 Brier 语义偏移） | 严重 |
| **边界失效** | S3（缓存键不含 limit → 冒烟污染全量）、M1（binned 对 AUROC 影响未校验）、M4（broad exception 静默吞错） | 严重/轻微 |
| **自相矛盾** | F2（docstring 声称网格搜索但代码用 Nelder-Mead）、S4（ID 假设与迁移实验设计矛盾） | 致命/严重 |
| **量级错误** | F2（Nelder-Mead 在 piecewise-constant 上失效）、M2（T_binned 统计含 fallback） | 致命/轻微 |
| **语义偏移** | F1（"TS+binned" 名义 vs "binned only" 实现）、S6（多分类 Brier 论证 vs top-label 实现） | 致命/严重 |

---

## 5. 额外审查项（用户指定 10 点）

| 审查项 | 结论 | 对应攻击 |
|--------|------|---------|
| 1. 3 阶段消融设计逻辑 | **不清晰**：Stage 2 实现与"TS+binned"声称不符（F1）；Stage 3 Brier reliability 恒等于 Stage 2（S1） | F1, S1 |
| 2. binned temperature 实现 | **部分正确**：分箱策略（熵五分位）合理，但拟合对象是 raw 而非 TS 输出（F1）；broad exception 静默吞错（M4） | F1, M4 |
| 3. threshold optimization 过拟合风险 | **优化器失效**：Nelder-Mead 在 piecewise-constant 上 no-op（F2）；阈值在 source-cal 拟合、target-test 评估，始终 OOD（S4） | F2, S4 |
| 4. 判别指标计算 | **基本正确**：AUROC/AUPRC 用 OvR macro（line 267-275）；F1/PPV/MCC 用 sklearn 标准；NPV 自定义 macro（line 237-248）合理。但 M1（binned 对 AUROC 影响未校验）、M6（argmax 不变性未验证） | M1, M6 |
| 5. 消融对照设计 | **有混淆变量**：Stage 2 未控制 Stage 1（F1）；Stage 3 概率=Stage 2 概率（S1）；缺少 raw+threshold / ts+threshold variant（M3） | F1, S1, M3 |
| 6. TS 对判别指标影响的 claim | **未充分验证**：只校验 Stage 1 ΔAUROC（line 521-525），不校验 Stage 2 binned 对 AUROC 的影响（M1）；不验证 F1/MCC 的 argmax 不变性（M6） | M1, M6 |
| 7. 60 checkpoint 复用与数据泄漏 | **无直接泄漏**：cal/test 患者级不交（train.py line 377-380 assert_no_leakage）；但**缓存键缺陷**导致冒烟跑污染全量跑（S3） | S3 |
| 8. 统计检验与多重比较校正 | **完全缺失**：无配对 t 检验 / Wilcoxon / bootstrap CI；无 FDR 校正（S5） | S5 |
| 9. 代码 bug | **多个**：F1（Stage 2 实现错误）、F2（优化器选择不当 + docstring 虚假）、S3（缓存键缺陷）、S1（Stage 3 冗余行） | F1, F2, S1, S3 |
| 10. 输出 CSV 格式 | **基本正确**：ablation CSV 含 stage/brier/T_global/T_binned/threshold_norm（line 487-497）；discrimination CSV 含 split/variant/6 指标（line 513-518）。但 `delta_rel_vs_raw` 的 merge 操作（line 633-636）依赖索引对齐，脆弱 | — |

---

## 6. 裁决与修复优先级

### 致命攻击修复（必须修复才能发布）

| 优先级 | 攻击 | 修复方案 | 工时 |
|--------|------|---------|------|
| P0 | F1 | Stage 2 改为在 `cal_s1`/`test_s1` 上拟合/应用 binned temperature；或修改 docstring/R5 声称为 "binned only" 并修正边际贡献解释 | 0.5 天 |
| P0 | F2 | 实现 docstring 声称的坐标下降+网格搜索；或修改 docstring 为 Nelder-Mead 并接受 Stage 3 ≈ Stage 2 | 0.5 天 |

### 严重攻击修复（需修复才能可信）

| 优先级 | 攻击 | 修复方案 | 工时 |
|--------|------|---------|------|
| P1 | S1 | 从消融表移除 Stage 3 Brier reliability 行（恒等无信息），改为报告 Stage 3 的 DCR 或 F1 改变 | 0.5 天 |
| P1 | S2 | 实现 DCR 计算（R5 §3.2 E3 line 290-293 已有定义） | 0.5 天 |
| P1 | S3 | 缓存键加入 limit + subspace hash | 0.5 天 |
| P1 | S4 | 报告 cal 上 threshold F1（in-sample 上界）vs test 上 F1（OOD），量化迁移衰减 | 0.5 天 |
| P1 | S5 | 对 60 实验的 ΔReliability 加配对 t 检验 + Cohen's d + 95% CI；3 个阶段比较用 BH FDR | 1 天 |
| P1 | S6 | 在论文中重新论证 top-label Brier 的 TS 性质（argmax 不变 → Resolution 不变），不引用多分类 Brier 分解 | 1 天（论文修改） |

### 轻微攻击修复（建议修复）

| 优先级 | 攻击 | 修复方案 | 工时 |
|--------|------|---------|------|
| P2 | M1-M7 | 见各攻击的修复建议 | 0.5 天 |

**总修复工时**：P0 = 1 天，P1 = 3.5 天，P2 = 0.5 天，合计 **5 天**。

---

## 7. 诚实声明

本反方代理尝试了全部 7 个攻击维度，找到 **2 个致命 + 6 个严重 + 7 个轻微 = 15 个攻击点**。E2 脚本在当前形态下**不能支持 R5 方案 §3.2 E2 的任何消融结论**，主要原因是：

1. **F1 使消融的解释框架失效**——"控制全局 T 后 binned T 的边际贡献"在代码中不成立
2. **F2 使 Stage 3 消融失效**——Nelder-Mead 在 piecewise-constant 上几乎必然 no-op
3. **S1-S6 使消融结论不可信**——无统计检验、核心指标缺失、缓存污染风险、假设与设计矛盾、理论-实现脱节

**未找到有效反例的维度**：无。所有 7 个维度均找到至少一个可验证攻击点。

**攻击的局限性**：
- F2 的 "Nelder-Mead 几乎必然 no-op" 是基于 piecewise-constant 函数性质的理论推断，未实际运行验证。建议正方运行 `--pairs ptbxl_chapman --limit 240` 并检查 `||τ||` 是否 ≈ 0 来验证。
- S3 的缓存污染需要实际触发（先冒烟后全量）才能确认，但缓存键缺陷是确定的代码事实。

---

*报告结束。E2 脚本需重大重写（P0+P1 修复 ≈ 4.5 天）才能支持论文消融结论。*
