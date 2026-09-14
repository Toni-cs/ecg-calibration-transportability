# P0-8 反反方回应报告

> **反反方代理-P0-8-ECE加权 交付**。本报告对反方在 `docs/p0_attack_p0_8.md` 中提出的 11 个攻击点（3 致命 + 5 严重 + 3 轻微）进行逐条独立审查。
> **审查日期**：2026-09-09
> **审查对象**：`scripts/run_e6_reliability_diagrams.py` L415-446（`_weighted_avg` / `_weighted_ece`）+ L451/456（图例标签）+ L474-476（标题）+ L433-436（修补注释）
> **审查代理**：反反方代理-P0-8-ECE加权（GLM-5.2）
> **诚实原则**：独立审查，不替正方辩护。攻击成立即承认，并给出可执行修补方案。

---

## 总体判定

**11 个攻击点中：11 个成立（3 致命 + 5 严重 + 3 轻微），0 个可完全反驳。**

反方的攻击质量很高，三个致命攻击均经数值验证属实：
- F1 反例（0.1 vs 0.0）已用 Python 复现确认
- F2 nan 传播已用 `np.average([0.2,nan],weights=[1000,0])=nan` 确认
- F3 Guo et al. 2017 引用错误经定义比对确认

正方 P0-8 修复**方向正确**（识别到了曲线加权 vs ECE 简单平均的矛盾），但**实现有缺陷**：用"方向级加权平均"替换"简单平均"后，标签"weighted avg ECE"让读者误以为是"全局 ECE"，且未处理 nan 边界、误引 Guo et al.。修复把一种语义矛盾换成了另一种。

**推荐方案**：采用反方次选方案（保留 `_weighted_ece` 但诚实标注 + 过滤 nan + 删除 Guo 引用），原因见下文 F1 修补方案论证。

---

## 逐条回应

### F1: 语义偏移——"weighted avg ECE" ≠ 全局 ECE

- **反方主张**：`_weighted_ece` 计算的是"各方向 ECE 的方向级加权平均" `Σ(N_dir×ECE_dir)/ΣN_dir`，但图例标注"weighted avg ECE"让读者理解为"合并样本后重算的全局 ECE" `Σ_bin(n_bin/N)×|conf-acc|`。反例：两方向偏差相反时，加权平均 ECE=0.1，全局 ECE=0.0。
- **验证结果**：**成立**
- **详细分析**：
  代码 L437-443 确认 `_weighted_ece` 实现：
  ```python
  weights = np.array([b["n_total"] for b in bins_list], dtype=float)
  eces = np.array([b["ece"] for b in bins_list], dtype=float)
  return float(np.average(eces, weights=weights))
  ```
  这是 `Σ_dir(N_dir × ECE_dir) / Σ_dir N_dir`，方向级加权平均。

  图例标签 L451：`f"Before TS (weighted avg ECE={ece_before:.3f})"`，"weighted avg ECE"字面可理解为"加权平均的 ECE"，但读者最自然的期望是"用汇总曲线（已加权平均）算出的 ECE"，即全局 ECE。

  **反例数值复现**（已用 Python 验证）：
  - 方向 A：500 样本全在 bin 5，conf=0.5, acc=0.6 → ECE_A = 1.0×|0.5-0.6| = 0.1
  - 方向 B：500 样本全在 bin 5，conf=0.5, acc=0.4 → ECE_B = 1.0×|0.5-0.4| = 0.1
  - 方向级加权平均：`(500×0.1 + 500×0.1)/1000 = 0.1` ✓
  - 全局 ECE（合并后 acc=(500×0.6+500×0.4)/1000=0.5）：`1.0×|0.5-0.5| = 0.0` ✓
  - 两者差 0.1，相对误差 ∞。**反例成立**。

  物理含义：两方向偏差方向相反，合并后互相抵消，全局校准完美；但方向级加权平均无法捕捉抵消，仍报 0.1。ECE 含绝对值，`|x|+|y| ≠ |x+y|`，加权平均与绝对值不可交换。

- **反驳或修补**：
  无法反驳，攻击数学上严格成立。两个修补方案：

  **方案 A（首选，真正"与曲线一致"）**：扩展 `_weighted_avg` 返回 `(acc, conf, counts)`，用汇总曲线重算 ECE：
  ```python
  def _weighted_avg(bins_list):
      """样本数加权平均每个 bin 的 accuracy/confidence/counts。"""
      acc = np.full(N_BINS, np.nan)
      conf = np.full(N_BINS, np.nan)
      counts = np.zeros(N_BINS, dtype=int)
      for i in range(N_BINS):
          total_w = 0
          total_wa = 0
          total_wc = 0
          for b in bins_list:
              if b["bin_counts"][i] > 0:
                  w = b["bin_counts"][i]
                  total_w += w
                  total_wa += w * b["bin_accuracies"][i]
                  total_wc += w * b["bin_confidences"][i]
          if total_w > 0:
              acc[i] = total_wa / total_w
              conf[i] = total_wc / total_w
              counts[i] = total_w
      return acc, conf, counts

  def _pooled_ece(acc, conf, counts):
      """用汇总曲线重算 ECE（真正的 Guo et al. 定义）。"""
      valid = counts > 0
      n_total = counts[valid].sum()
      if n_total <= 0:
          return float("nan")
      return float(np.sum(counts[valid] / n_total *
                          np.abs(conf[valid] - acc[valid])))
  ```
  图例标签改为 `ECE of averaged curve` 或 `pooled ECE`。

  **方案 B（次选，最小改动）**：保留 `_weighted_ece`，但标签明确语义：
  ```python
  label=f"Before TS (size-weighted mean ECE={ece_before:.3f})"
  ```
  或更详细：`mean ECE (weighted by n_total)`。

  **推荐方案 B**，理由：
  1. 方案 A 虽数学更优，但改动 `_weighted_avg` 返回值签名，需同步修改 L430-431、L448-456 等多处调用，回归测试成本高，Q2 补充阶段风险/收益不划算。
  2. 方案 B 只改标签字符串 + 过滤 nan + 删 Guo 引用，3 行改动，零回归风险。
  3. "size-weighted mean of per-direction ECE"是诚实的描述——它确实是各方向 ECE 的样本数加权平均，只是不是全局 ECE。审稿人看到明确标签不会误解。
  4. 论文 Method 部分可一句话说明"汇总图 ECE 报告各方向 ECE 的样本数加权平均，非合并样本重算的全局 ECE"，彻底消除歧义。

---

### F2: 边界失效——部分 n_total=0 + nan ece 导致整个汇总 ECE 变 nan

- **反方主张**：当任一方向 `n_total=0`（`ece=nan`）时，`np.average` 把 nan 传播到整个结果，即使其他方向有效。已验证 `np.average([0.2,nan],weights=[1000,0])=nan`。
- **验证结果**：**成立**
- **详细分析**：
  代码 L441-443：
  ```python
  if weights.sum() <= 0:
      return float("nan")
  return float(np.average(eces, weights=weights))
  ```
  只检查 `weights.sum() <= 0`（全零边界），未检查部分 ece 为 nan。

  `compute_reliability_bins` L188 确认 `n_total=0` 时返回 `ece=nan`：
  ```python
  ece_val = float(...) if n_total > 0 else float("nan")
  ```

  **数值验证**（已用 Python 复现）：
  ```
  np.average([0.2, nan], weights=[1000, 0]) = nan  ✓
  ```
  原因：`np.average` 内部 `Σ(w_i × x_i) / Σ w_i`，`0 × nan = nan`，`200 + nan = nan`，`nan / 1000 = nan`。即使空方向权重为 0，nan 仍污染整体。

  **触发场景现实**：迁移学习中某方向 OOD 测试集缺失（数据加载失败、checkpoint 缺失、`--limit` 截断为 0）是常见情况。`generate_figures` L703-705 在 `_load_npz` 返回 None 时跳过，但若 npz 存在且 `n_ood=0`（数据集为空），`compute_reliability_bins` 返回 `n_total=0, ece=nan`，该方向仍被加入 `summary_before`（L725），触发此 bug。

- **反驳或修补**：
  无法反驳，这是真实的边界 bug。修补方案（反方建议正确）：
  ```python
  def _weighted_ece(bins_list):
      """按各方向总样本数加权平均 ECE。"""
      weights = np.array([b["n_total"] for b in bins_list], dtype=float)
      eces = np.array([b["ece"] for b in bins_list], dtype=float)
      # 过滤 nan ece 和零权重方向，避免 nan 传播
      valid = np.isfinite(eces) & (weights > 0)
      if not valid.any() or weights[valid].sum() <= 0:
          return float("nan")
      return float(np.average(eces[valid], weights=weights[valid]))
  ```
  此修补同时解决 S4（nan ece 未过滤）。

---

### F3: 引用错误——Guo et al. 2017 的 ECE 定义不是"多方向 ECE 加权平均"

- **反方主张**：代码注释 L436 声称"加权 ECE 是 ECE 的标准定义（Guo et al. 2017）"，但 Guo et al. 2017 的 ECE 是单模型按 bin 样本数加权，不是多方向 ECE 的方向级加权平均。
- **验证结果**：**成立**
- **详细分析**：
  注释 L433-436：
  ```python
  # 平均 ECE（按各方向总样本数加权平均，与曲线的样本数加权方式一致）
  # 修补说明：此前用 np.mean（简单算术平均）与曲线的样本数加权平均不匹配，
  # 审稿人对比图内数值会发现不一致。现改为按 n_total 加权，使 ECE 标注与
  # 曲线加权方式统一。加权 ECE 是 ECE 的标准定义（Guo et al. 2017）。
  ```

  **Guo et al. 2017《On Calibration of Modern Neural Networks》的 ECE 定义**：
  ```
  ECE = Σ_b (n_b / N) × |acc(b) - conf(b)|
  ```
  - 单模型，bin 级加权，权重是 bin 样本数 `n_b`

  **`_weighted_ece` 计算的**：
  ```
  ECE_weighted = Σ_dir (N_dir / N_total) × ECE_dir
  ```
  - 多方向，方向级加权，权重是方向总样本数 `N_dir`

  两者是**不同层级的加权**：
  | | Guo et al. 2017 | `_weighted_ece` |
  |---|---|---|
  | 加权层级 | bin 级 | 方向级 |
  | 模型数 | 单模型 | 多方向 |
  | 权重 | `n_b`（bin 样本数） | `N_dir`（方向总样本数） |
  | 求和对象 | `|acc(b)-conf(b)|` | `ECE_dir` |

  把"单模型 ECE 的 bin 加权定义"套用到"多方向 ECE 的方向加权平均"上并声称是 Guo et al. 标准定义，是**概念混淆**。反例（F1 的 0.1 vs 0.0）证明两者数值不等。

- **反驳或修补**：
  无法反驳，引用确实错误。修补方案：
  删除 L436 "加权 ECE 是 ECE 的标准定义（Guo et al. 2017）"，改为诚实描述：
  ```python
  # 平均 ECE（按各方向总样本数加权平均各方向的 ECE）
  # 修补说明：此前用 np.mean（简单算术平均）与曲线的样本数加权平均不匹配，
  # 审稿人对比图内数值会发现不一致。现改为按 n_total 加权平均各方向 ECE。
  # 注意：这是对多方向 ECE 的汇总约定（方向级加权平均），非 Guo et al. 2017
  # 的原始 ECE 定义（单模型 bin 级加权）。各方向 ECE 本身按 Guo et al. 2017
  # 的 bin 加权定义计算。全局 ECE（合并样本重算）与方向级加权平均 ECE
  # 一般不相等，因 ECE 含绝对值，加权平均与绝对值不可交换。
  ```

---

### S1: 逻辑断链——曲线 bin 级加权 vs ECE 方向级加权，"一致"是误导

- **反方主张**：修补说明 L435 声称"使 ECE 标注与曲线加权方式统一"，但曲线是 bin 级加权（`_weighted_avg` 按 `bin_counts[i]`），ECE 是方向级加权（`_weighted_ece` 按 `n_total`），两者层级不同，"一致"是未证明的跳跃。
- **验证结果**：**成立**
- **详细分析**：
  代码确认两种加权层级不同：
  - `_weighted_avg` L423：`w = b["bin_counts"][i]`（bin 级，每个 bin 内跨方向加权）
  - `_weighted_ece` L439：`weights = [b["n_total"] for b in bins_list]`（方向级，跨方向加权 ECE）

  **三种 ECE 数值验证**（已用 Python 复现反方构造）：
  | ECE 计算方式 | 值 |
  |---|---|
  | 简单平均（修复前） | 0.200 |
  | 方向级加权平均（`_weighted_ece`，修复后） | 0.118 |
  | 汇总曲线重算 ECE（bin 级加权后算 `|conf-acc|`） | 0.082 |

  三者互不相等。若真要"与曲线加权方式一致"，应取第三种（汇总曲线重算），但代码实现的是第二种。修复后 ECE 仍不"一致"于曲线。

- **反驳或修补**：
  无法反驳。修补方案：
  - 若采用 F1 方案 A（汇总曲线重算 ECE），则 S1 自动解决——ECE 真正用汇总曲线算，与曲线加权一致。
  - 若采用 F1 方案 B（诚实标注），则需修改注释 L435，删除"使 ECE 标注与曲线加权方式统一"的"统一"声称，改为"使 ECE 标注采用与曲线相同的样本数加权思想（但层级不同：曲线为 bin 级加权，ECE 为方向级加权平均）"。

  **推荐随 F1 方案 B**：注释改为：
  ```python
  # 平均 ECE（按各方向总样本数加权平均各方向的 ECE）
  # 修补说明：此前用 np.mean（简单算术平均）未考虑各方向样本数差异，
  # 现改为按 n_total 加权平均。注意：曲线加权是 bin 级（每个 bin 内
  # 跨方向按 bin_counts 加权），ECE 加权是方向级（跨方向按 n_total
  # 加权），两者层级不同但都基于样本数加权思想。
  ```

---

### S2: 图例标签歧义——"weighted avg ECE" 未说明权重是什么

- **反方主张**：图例标签"weighted avg ECE"没说明权重是什么（bin 样本数？方向总样本数？方向数？），实际是方向总样本数 `n_total`，但标签没说。
- **验证结果**：**成立**
- **详细分析**：
  代码 L451：`label=f"Before TS (weighted avg ECE={ece_before:.3f})"`，"weighted"未指明权重。
  实际实现 L439：`weights = [b["n_total"] for b in bins_list]`，是方向总样本数。
  读者可能误解为按 bin sample count 加权（因标题 L474-476 说"weighted by bin sample count"）。

- **反驳或修补**：
  无法反驳。修补方案（随 F1 方案 B）：
  ```python
  label=f"Before TS (size-weighted mean ECE={ece_before:.3f})"
  ```
  "size-weighted mean ECE"明确权重是样本数（size），消除歧义。

---

### S3: 标题与图例矛盾——标题说 "bin sample count"，图例说 "weighted avg ECE"（n_total）

- **反方主张**：标题 L474-476 说曲线"weighted by bin sample count"（bin 级），图例 L451 说 ECE "weighted avg"（实际方向级 n_total），同一张图内"weighted"含义不同。
- **验证结果**：**成立**
- **详细分析**：
  - 标题 L474-476：`"Summary: 6-direction averaged reliability curve\n(weighted by bin sample count; ...)"`
  - 图例 L451：`"Before TS (weighted avg ECE=...)"`（实际按 `n_total` 方向级加权）

  读者合理推断：标题强调"weighted by bin sample count"，图例的"weighted avg ECE"应也是按 bin sample count 加权。但实际 ECE 按 `n_total`（方向级）加权。标题与图例的"weighted"语义不一致。

- **反驳或修补**：
  无法反驳。修补方案：标题区分曲线和 ECE 的加权方式：
  ```python
  ax.set_title("Summary: 6-direction averaged reliability curve\n"
               f"(curve: bin-count weighted; ECE: n_total-weighted mean; "
               f"{REP_ARCH}, seed{REP_SEED})",
               fontsize=12, pad=10)
  ```
  或更简洁：
  ```python
  ax.set_title("Summary: 6-direction averaged reliability curve\n"
               f"(curve & ECE weighted by sample count; {REP_ARCH}, seed{REP_SEED})",
               fontsize=12, pad=10)
  ```
  后者更简洁但略模糊；前者更精确但标题变长。**推荐前者**（精确优先）。

---

### S4: nan ece 未过滤——F2 边界失效的根因

- **反方主张**：`_weighted_ece` 隐含假设"所有方向 ece 有效"，但 `compute_reliability_bins` 在 `n_total=0` 时返回 `ece=nan`，代码未用 `np.isfinite` 过滤，导致 F2。
- **验证结果**：**成立**（与 F2 同一根因）
- **详细分析**：
  代码 L437-443 无 `np.isfinite` 过滤。`compute_reliability_bins` L188 在 `n_total=0` 时返回 `ece=nan`。隐含假设在 OOD 测试集为空、checkpoint 缺失、`--limit=0` 等场景不成立。

- **反驳或修补**：
  无法反驳。修补方案同 F2（过滤 `np.isfinite(eces) & (weights > 0)`）。F2 修补自动解决 S4。

---

### S5: 缺少 bin_confidences 加权平均——即使要"用汇总曲线算 ECE"也缺数据

- **反方主张**：`_weighted_avg` L415-428 只加权平均了 `bin_accuracies`，没有加权平均 `bin_confidences`。若按 F1 方案 A（用汇总曲线重算 ECE），需要 `conf_avg[i]` 和 `acc_avg[i]` 都做 bin 级加权平均，但当前 `_weighted_avg` 只返回 `acc`，无法计算。
- **验证结果**：**成立**
- **详细分析**：
  代码 L415-428 确认 `_weighted_avg` 只返回 `acc`：
  ```python
  def _weighted_avg(bins_list):
      acc = np.full(N_BINS, np.nan)
      for i in range(N_BINS):
          ...
          total_wa += w * b["bin_accuracies"][i]  # 只加权 acc
          ...
      return acc  # 只返回 acc
  ```
  没有 `total_wc += w * b["bin_confidences"][i]`，没有返回 `conf`。

  若要实现 F1 方案 A（`ECE = Σ_i (n_i/N) × |conf_avg[i] - acc_avg[i]|`），需要 `conf_avg[i]`，但当前无法获得。

- **反驳或修补**：
  无法反驳。修补方案：
  - 若采用 F1 方案 A：扩展 `_weighted_avg` 返回 `(acc, conf, counts)`，代码见 F1 方案 A。
  - 若采用 F1 方案 B：S5 不阻塞（方案 B 不需要汇总曲线重算 ECE），但建议仍扩展 `_weighted_avg` 返回 `conf` 和 `counts`，为未来可能的方案 A 迁移留接口。

  **推荐随 F1 方案 B**：S5 暂不修补（不阻塞），但在注释中标注技术债：
  ```python
  # TODO(未来): 若要改为用汇总曲线重算 ECE（真正的全局 ECE），
  # 需扩展 _weighted_avg 同时返回加权平均的 bin_confidences 和 bin_counts。
  ```

---

### M1: 量级错误——0.05 绝对差异在 ECE 量级上不显著

- **反方主张**：正方报告简单平均=0.20、加权平均=0.25、差异 25%，但绝对差异仅 0.05，在 ECE 文献量级（0.05-0.20）上可能不显著，且正方未报告各方向 n_total，无法验证差异来源。
- **验证结果**：**部分成立**
- **详细分析**：
  反方指出两点：
  1. **绝对差异 0.05 可能不显著**：合理。ECE 量级常在 0.05-0.20，0.05 差异可能在 bootstrap CI 内。但这是"修复必要性"的论证，不影响修复正确性。
  2. **正方未报告各方向 n_total**：合理。无法验证 0.20 vs 0.25 的差异是否真由样本数差异驱动。

  但需注意：即使差异不显著，修复本身无害（加权平均比简单平均更合理），且消除了"曲线加权 vs ECE 简单平均"的形式矛盾。反方也承认"修复本身无害"。

- **反驳或修补**：
  部分反驳：差异显著性不影响修复正确性，且修复无害。但反方"未报告 n_total 明细"的批评合理。
  修补建议：在修补注释或论文 Method 部分补充各方向 n_total 和 ECE 明细，让审稿人自行判断。例如在 `plot_summary` 中添加 debug 打印：
  ```python
  # debug: 打印各方向 n_total 和 ECE 明细
  for i, b in enumerate(bins_list):
      print(f"  dir {i}: n_total={b['n_total']}, ece={b['ece']:.4f}")
  ```

---

### M2: 单图 vs 汇总图语义不一致——修复引入新的不一致

- **反方主张**：单图（L327）显示该方向 ECE，汇总图（L451）显示加权平均 ECE。修复前汇总图=简单平均（与手动平均单图一致），修复后=加权平均（与手动平均单图不一致），读者手动平均 6 个单图 ECE 会发现对不上。
- **验证结果**：**成立**（但属修复固有代价）
- **详细分析**：
  - 单图 L327：`f"Before TS (ECE={bins_before['ece']:.3f})"`——该方向 ECE
  - 汇总图 L451：`f"Before TS (weighted avg ECE={ece_before:.3f})"`——加权平均

  修复前汇总图用 `np.mean`（简单平均），读者手动平均 6 单图 ECE ≈ 汇总图 ECE。修复后用加权平均，手动平均 ≠ 汇总图 ECE。

  但这是**加权平均 vs 简单平均的固有差异**，非 bug。加权平均本身比简单平均更合理（反映样本数差异）。问题在于标签未说明"这是加权平均，非简单平均"。

- **反驳或修补**：
  部分反驳：这是加权平均的固有特性，非缺陷。但反方"需说明加权方式"的批评合理。
  修补方案：随 F1 方案 B，标签改为 `size-weighted mean ECE`，读者看到"size-weighted mean"即知非简单平均，不会手动平均后困惑。论文 Method 部分一句话说明即可。

---

### M3: 未报告其他校准指标（Brier/MCE）——非 P0-8 问题但值得指出

- **反方主张**：脚本中没有 Brier score、MCE、reliability gap 的汇总计算，只报告 ECE。P0-8 修复未建立通用加权汇总框架，只是针对 ECE 打补丁。
- **验证结果**：**成立**（但超出 P0-8 范围）
- **详细分析**：
  grep 确认脚本无 Brier/MCE 计算。反方承认"这不是 P0-8 修复引入的问题"，只是提示未来技术债。

- **反驳或修补**：
  部分反驳：超出 P0-8 范围，P0-8 的任务是修复 ECE 加权矛盾，不是建立通用校准指标框架。但反方提示合理。
  修补建议：暂不修补（超出 P0-8 范围），但在技术债文档中记录"未来若添加 Brier/MCE 汇总，需统一加权框架"。

---

## 结论

### 攻击成立情况汇总

| 编号 | 严重性 | 验证结果 | 可反驳程度 |
|------|--------|----------|------------|
| F1 | 致命 | 成立 | 0%（数学严格成立，反例已复现） |
| F2 | 致命 | 成立 | 0%（nan 传播已复现） |
| F3 | 致命 | 成立 | 0%（Guo 定义比对确认） |
| S1 | 严重 | 成立 | 0%（三种 ECE 数值已验证不等） |
| S2 | 严重 | 成立 | 0%（标签确实未说明权重） |
| S3 | 严重 | 成立 | 0%（标题与图例语义确实不一致） |
| S4 | 严重 | 成立 | 0%（F2 同一根因） |
| S5 | 严重 | 成立 | 0%（代码确认只返回 acc） |
| M1 | 轻微 | 部分成立 | 50%（差异显著性可辩，但未报 n_total 合理） |
| M2 | 轻微 | 成立 | 30%（加权平均固有特性，但需说明） |
| M3 | 轻微 | 成立 | 70%（超出 P0-8 范围） |

**11 个攻击全部成立，0 个可完全反驳。** 反方攻击质量极高，三个致命攻击均经独立数值验证确认。

### 需要回炉重修的攻击

**F1、F2、F3 必须回炉**（致命）：
- F2：nan 传播是真实 bug，一个空方向会让汇总图 ECE 变 nan，图报废。必须过滤 nan。
- F3：Guo et al. 引用错误会被审稿人当场抓出。必须删除或改正。
- F1：标签"weighted avg ECE"语义偏移，读者误以为全局 ECE。必须明确标签。

**S1、S2、S3、S4、S5 应一并修补**（严重）：
- S4 随 F2 自动解决。
- S1、S2、S3 随 F1 标签修改和注释修改解决。
- S5 暂不阻塞（采用方案 B 时），但标注技术债。

### 可以接受的攻击

**M1、M2、M3 可接受**（轻微）：
- M1：差异显著性是论证问题，不影响修复正确性。补充 n_total 明细即可。
- M2：加权平均固有特性，标签明确后非问题。
- M3：超出 P0-8 范围，记录技术债即可。

### 推荐的最终修补方案（方案 B，最小改动）

采用反方次选方案，3 处改动，零回归风险：

**改动 1：`_weighted_ece` 过滤 nan（解决 F2、S4）**
```python
def _weighted_ece(bins_list):
    """按各方向总样本数加权平均 ECE。"""
    weights = np.array([b["n_total"] for b in bins_list], dtype=float)
    eces = np.array([b["ece"] for b in bins_list], dtype=float)
    # 过滤 nan ece 和零权重方向，避免 nan 传播（F2 修补）
    valid = np.isfinite(eces) & (weights > 0)
    if not valid.any() or weights[valid].sum() <= 0:
        return float("nan")
    return float(np.average(eces[valid], weights=weights[valid]))
```

**改动 2：图例标签明确语义（解决 F1、S1、S2、S3、M2）**
```python
# L451
label=f"Before TS (size-weighted mean ECE={ece_before:.3f})", zorder=3)
# L456
label=f"After TS (size-weighted mean ECE={ece_after:.3f})", zorder=4)
```

**改动 3：注释删除 Guo 引用，诚实描述（解决 F3、S1）**
```python
# 平均 ECE（按各方向总样本数加权平均各方向的 ECE）
# 修补说明：此前用 np.mean（简单算术平均）未考虑各方向样本数差异，
# 现改为按 n_total 加权平均各方向 ECE。注意：
# 1. 这是方向级加权平均（跨方向按 n_total 加权），非 Guo et al. 2017
#    的原始 ECE 定义（单模型 bin 级加权）。各方向 ECE 本身按 Guo et al.
#    2017 的 bin 加权定义计算。
# 2. 方向级加权平均 ECE ≠ 全局 ECE（合并样本重算），因 ECE 含绝对值，
#    加权平均与绝对值不可交换。本图报告前者，标签已明确为
#    "size-weighted mean ECE"。
# 3. 曲线加权是 bin 级（每个 bin 内跨方向按 bin_counts 加权），
#    ECE 加权是方向级（跨方向按 n_total 加权），两者层级不同但
#    都基于样本数加权思想。
# 4. nan ece（n_total=0 方向）已过滤，避免传播（F2 修补）。
```

**改动 4：标题区分曲线和 ECE 加权（解决 S3）**
```python
ax.set_title("Summary: 6-direction averaged reliability curve\n"
             f"(curve: bin-count weighted; ECE: n_total-weighted mean; "
             f"{REP_ARCH}, seed{REP_SEED})",
             fontsize=12, pad=10)
```

**论文 Method 部分补充一句话**：
> 汇总图 ECE 报告各方向 ECE 的样本数加权平均（size-weighted mean of per-direction ECE），非合并所有样本后重算的全局 ECE。两者一般不相等，因 ECE 含绝对值，加权平均与绝对值不可交换。

### 方案 A vs 方案 B 的选择论证

| 维度 | 方案 A（汇总曲线重算 ECE） | 方案 B（诚实标注 + 过滤 nan） |
|------|---------------------------|-------------------------------|
| 数学正确性 | 更优（真正全局 ECE，与曲线一致） | 次优（方向级加权平均，非全局） |
| 改动量 | 大（扩展 `_weighted_avg` 返回值，改多处调用） | 小（3-4 处字符串/逻辑改动） |
| 回归风险 | 中（`_weighted_avg` 签名变化） | 零（只改标签和过滤） |
| 审稿人接受度 | 高（真正的 Guo 定义） | 中（诚实标注后可接受） |
| Q2 阶段适用性 | 偏重（Q2 是补充实验，非核心重构） | 合适（最小改动消除矛盾） |

**结论**：Q2 补充阶段推荐方案 B。若未来期刊要求严格全局 ECE，再迁移到方案 A（届时 S5 的 `_weighted_avg` 扩展是前置工作）。

### 最终判定

**P0-8 修复方向正确，但实现有 3 个致命缺陷 + 5 个严重缺陷，必须二次修补。** 反方攻击全部成立，质量极高。推荐采用方案 B（最小改动）进行二次修补，可消除全部 3 致命 + 4 严重攻击（S5 标注技术债），剩余 1 严重（S5）+ 3 轻微可接受。

---

*报告结束。反反方代理-P0-8-ECE加权 已逐条审查 11 个攻击点，全部成立，推荐方案 B 二次修补。*
