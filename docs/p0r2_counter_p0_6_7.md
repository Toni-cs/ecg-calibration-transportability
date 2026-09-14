# P0-6+7 反反方审查报告（R2轮）

## 审查概要
- **审查代理**：反反方审查代理（GLM-5.2）
- **审查日期**：2026-09-09
- **攻击报告**：docs/p0r2_attack_p0_6_7.md
- **被攻击源代码**：
  - `scripts/run_e5_inception_lite.py`（revision 5e3941ae）
  - `src/data/mapping.py`（revision 185f863d）
  - `src/models/baselines.py`（revision 1186f74d，辅助验证 ECGResNet1D）
  - `src/utils/calibration.py`（revision 3782ef31，辅助验证 benefit_inference/compute_all_metrics/fit_temperature）
  - `scripts/train.py`（revision 024b429a，辅助验证 docstring）
- **攻击点总数**：14
- **成立**：12 | **部分成立**：2 | **不成立**：0
- **总体结论**：反方攻击报告质量较高，14个攻击点均经实际代码验证，无稻草人论证。最严重的攻击1（tgt_clusters 长度不匹配）确实成立，是本轮修复最关键的遗留问题。F2/F1/F3+S7+M1 核心修复经反反方独立验证确认正确，反方对此的"修复正确性确认"章节诚实可信。

---

## 逐条审查

### 攻击点1: [严重] 截断+S1 修复后 ood_probs 与 tgt_clusters 长度不匹配，benefit_inference 会 IndexError
**判定**: 成立

**分析**:
经实际代码逐行验证，攻击完全成立。数据流追踪如下：

1. `run_e5_inception_lite.py` L418：`tgt_ds, tgt_clusters = build_dataset(target, seed, ...)` 返回 `tgt_clusters`，长度 = 原始 target test 集大小 N。
2. L426-427：`ood_probs = tgt_eval["probs"]`、`ood_labels = tgt_eval["labels"]`，长度 = N（与 tgt_clusters 对齐）。
3. L438-443 截断：`ood_keep = ood_labels < num_classes`，`ood_labels = ood_labels[ood_keep]`、`ood_probs = ood_probs[ood_keep][:, :num_classes]`。若 5→4 方向有 HYP 样本（标签=4≥4），截断后长度 = N - n_dropped_ood < N。**tgt_clusters 未同步截断**（代码中无 `tgt_clusters = tgt_clusters[ood_keep]` 语句）。
4. L456-463 S1 修复：`ood_zero_rows = (ood_row_sums.flatten() == 0)`，若有全零行，`ood_probs = ood_probs[~ood_zero_rows]`、`ood_labels = ood_labels[~ood_zero_rows]`。**tgt_clusters 仍未同步截断**。
5. L488-492：`benefit = benefit_inference(max_probs_raw, max_probs_ts, correct_mask, ..., clusters=tgt_clusters)`。此时 `max_probs_raw` 长度 = S1 修复后 ood_probs 长度 < N，但 `tgt_clusters` 长度 = N。

验证 `benefit_inference`（`calibration.py` L479-485）：
```python
clusters = np.asarray(clusters)
uniq = np.unique(clusters)
cluster_indices = {c: np.where(clusters == c)[0] for c in uniq}
def draw_indices():
    chosen = rng.choice(uniq, size=len(uniq), replace=True)
    return np.concatenate([cluster_indices[c] for c in chosen])
```
`np.where(clusters == c)[0]` 返回的索引范围是 [0, N-1]，但 `probs_raw` 长度 < N。当 `idx` 包含 ≥ len(probs_raw) 的索引时，L494 `probs_raw[idx]` 触发 IndexError。

docstring（L543）明确要求"clusters: 患者ID数组（与probs等长）"，当前调用违反此契约。

**反例可构造性**：ptbxl→cpsc 方向，target=cpsc，test 集有 1000 样本其中 50 个 HYP（标签=4）。截断后 ood_probs 长度 = 950，tgt_clusters 长度 = 1000。cluster bootstrap 重采样时索引 ≥ 950 触发 IndexError。即使不 IndexError（若被丢弃的 50 个样本患者 ID 与保留的 950 个不重叠），cluster 簇定义仍基于 1000 个样本，但 probs 只有 950 个，统计语义错误。

**修补方案**:
- 文件：`scripts/run_e5_inception_lite.py`
- 改动1（L443 后，截断后同步）：
  ```python
  # 同步截断 tgt_clusters，保持与 ood_probs 等长（benefit_inference 契约要求）
  tgt_clusters = tgt_clusters[ood_keep]
  ```
- 改动2（L463 后，S1 全零行丢弃后同步）：
  ```python
  if ood_zero_rows.any():
      tgt_clusters = tgt_clusters[~ood_zero_rows]
  ```
  注意：当前 L458-462 的 `if ood_zero_rows.any():` 块内需追加 `tgt_clusters = tgt_clusters[~ood_zero_rows]`。

---

### 攻击点2: [严重] S3/M2 修复未完成——result dict 缺少截断统计字段
**判定**: 成立

**分析**:
经实际代码验证，攻击成立。

`run_e5_inception_lite.py` L500-514 result dict 实际内容：
```python
result = {
    "source": source, "target": target, "seed": seed, "arch": ARCH_NAME,
    "num_classes": num_classes,
    "n_ood": int(len(ood_probs)),
    "ood_acc_raw": ..., "fitted_T": ..., "ood_ece_raw": ..., "ood_ece_ts": ...,
    "ood_brier_raw": ..., "ood_brier_ts": ..., "delta_ece": ...,
    "delta_ece_ci_low": ..., "delta_ece_ci_high": ...,
    "brier_reliability_improvement": ...,
}
```
确实**没有** `n_dropped_cal`、`n_dropped_ood`、`truncated`、`subspace_filtered` 字段。

L432-433 计算了 `n_dropped_cal` 和 `n_dropped_ood`，但仅用于 L434-437 的控制台警告，未写入 result dict。这违反了终审报告 L254 修补清单第 9 项的明确要求。

后果：5→4 方向迁移实验运行后，CSV 中无任何字段记录"丢弃了多少 cal/ood 样本"，论文审稿人问"ptbxl→cpsc 方向丢弃了多少 HYP 样本？"时无法从 CSV 回答。

**修补方案**:
- 文件：`scripts/run_e5_inception_lite.py`
- 改动（L500-514 result dict 增加字段）：
  ```python
  result = {
      ...,
      "n_ood": int(len(ood_probs)),
      "n_dropped_cal": int(n_dropped_cal),
      "n_dropped_ood": int(n_dropped_ood),
      "n_dropped_cal_zero": int(cal_zero_rows.sum()) if cal_zero_rows.any() else 0,
      "n_dropped_ood_zero": int(ood_zero_rows.sum()) if ood_zero_rows.any() else 0,
      "truncated": bool((n_dropped_cal + n_dropped_ood) > 0),
      "subspace_filtered": bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
      ...,
  }
  ```

---

### 攻击点3: [严重] 训练侧 info dict 缺少 arch_override/depth/width 字段，CSV arch 列始终显示 "inceptiontime_lite"
**判定**: 成立

**分析**:
经实际代码验证，攻击成立。

- `ARCH_NAME = "inceptiontime_lite"`（L105 模块级常量）。
- L369：`info["arch"] = ARCH_NAME`，无论 `arch_override` 是 None 还是 "resnet1d"，`info["arch"]` 始终是 "inceptiontime_lite"。
- L370-371：记录了 `n_filters` 和 `use_checkpoint`，但**没有** `arch_override`、`depth`、`width` 字段。

Level 3 触发时（arch_override="resnet1d", depth=3/5/7, width=32/64/128），CSV 中 arch 列仍显示 "inceptiontime_lite"，无法区分 InceptionTime-Lite 和 ResNet1D 变体。论文 Table 1 报告"3 架构家族"时，无法从 CSV 追溯哪些实验实际用了 ResNet1D。

**修补方案**:
- 文件：`scripts/run_e5_inception_lite.py`
- 改动（L368-380 info dict）：
  ```python
  arch_display = arch_override if arch_override else ARCH_NAME
  info = {
      "dataset": dataset, "seed": seed,
      "arch": arch_display,           # 反映实际架构
      "arch_override": arch_override,  # None 表示默认
      "depth": depth, "width": width,
      "n_params": n_params, "n_filters": n_filters,
      "use_checkpoint": use_checkpoint,
      ...,
  }
  ```

---

### 攻击点4: [严重] 控制台 arch_display 与 CSV arch 字段不一致
**判定**: 成立

**分析**:
经实际代码验证，攻击成立。

- L307：`arch_display = arch_override if arch_override else ARCH_NAME`，控制台显示实际架构。
- L309-310：`print(f"[训练] {dataset} seed={seed} arch={arch_display} ...")`，Level 3 时显示 "resnet1d"。
- L369：`info["arch"] = ARCH_NAME`，CSV 记录始终 "inceptiontime_lite"。

Level 3 触发时，控制台显示 `arch=resnet1d`，CSV 记录 `arch=inceptiontime_lite`，**两者不一致**。调试时对照控制台和 CSV 无法匹配 Level 3 实验记录。

**修补方案**: 与攻击3 合并修复，`info["arch"]` 用 `arch_display`（即 `arch_override if arch_override else ARCH_NAME`）。

---

### 攻击点5: [严重] 全部 cal 样本被丢弃时未提前返回，fit_temperature 收到空数组返回 nan
**判定**: 成立

**分析**:
经实际代码验证，攻击成立。

数据流追踪：
1. L438-441 截断：`cal_keep = cal_labels < num_classes`，`cal_labels = cal_labels[cal_keep]`，`cal_probs = cal_probs[cal_keep][:, :num_classes]`。
2. L447-453 S1 修复：若全零行存在，`cal_probs = cal_probs[~cal_zero_rows]`，`cal_labels = cal_labels[~cal_zero_rows]`。
3. **边界情况**：若所有 cal 样本标签 ≥ num_classes（如 5→4 方向 cal 集全为 HYP），或截断后全零行全部被丢弃，`cal_probs` 为空数组 (0, num_classes)。
4. L466：`one_hot_cal = np.eye(num_classes)[cal_labels]`，空数组。
5. L467：`T = fit_temperature(cal_probs, one_hot_cal)`。

验证 `fit_temperature`（`calibration.py` L60-87）空数组行为：
- L64：`logits = np.log(np.clip(val_p, EPS, 1 - EPS))`，shape (0, num_classes)。
- L74-75：`log_sum_exp`、`log_probs` 均 shape (0, num_classes)。
- L77：`nll_val = -np.mean(np.sum(val_y * log_probs, axis=1))`，`np.sum(..., axis=1)` shape (0,)，`np.mean([])` 返回 nan（带 RuntimeWarning）。
- L80-87：`scipy.optimize.minimize` 对 nan 目标函数返回 nan 解，`np.clip(nan, T_MIN, T_MAX)` = nan。
- 返回 T=nan。

后续传播：
- L468：`ood_probs_ts = apply_temperature(ood_probs, nan)` 产生 nan 概率。
- L474-475：`compute_all_metrics` 收到 nan 概率，返回 nan 指标。
- L500-514：result dict 记录 nan，CSV 静默写入 nan，**无显式错误**。

关键：此 nan 传播路径**不被** L716-722 的 `except Exception` 捕获（fit_temperature 不抛异常，返回 nan），是真正的静默错误。

反例可构造性：`--limit` 较小时（如 `--limit 50`），cal 集可能恰好全为 HYP 样本，概率虽低但理论可能。

**修补方案**:
- 文件：`scripts/run_e5_inception_lite.py`
- 改动（L463 后、L466 前加空数组检查）：
  ```python
  if len(cal_probs) == 0:
      print(f"[WARN] {source}→{target} seed={seed}: cal 集截断后为空，跳过 TS 校准")
      return {"source": source, "target": target, "seed": seed, "arch": ARCH_NAME,
              "error": "cal set empty after truncation", "skipped": True}
  if len(ood_probs) == 0:
      print(f"[WARN] {source}→{target} seed={seed}: ood 集截断后为空，跳过迁移评估")
      return {"source": source, "target": target, "seed": seed, "arch": ARCH_NAME,
              "error": "ood set empty after truncation", "skipped": True}
  ```

---

### 攻击点6: [严重] 全部 ood 样本被丢弃时未提前返回，compute_all_metrics 收到空数组可能崩溃
**判定**: 部分成立

**分析**:
攻击方向正确（空数组边界未处理），但"崩溃"的严重程度被夸大。经实际代码验证，`compute_all_metrics` 对空数组**大概率不崩溃**，而是返回 nan，属静默错误而非崩溃。

逐函数验证空数组行为：

1. `ece(probs=[], labels=[], n_bins)`（L199-243）：所有 bin 的 `mask.sum() == 0`，循环体 `continue` 跳过，`ece_val` 保持 0.0。返回 0.0。**不崩溃**。

2. `bootstrap_ece(probs=[], labels=[], n_bins, n_bootstrap)`（L520-583）：
   - L551：`n = 0`。
   - L556：`point = ece([], [], n_bins)` = 0.0。
   - L572：`rng.choice(0, 0, replace=True)` 返回空数组（numpy 对 size=0 的 choice 返回空数组，不报错）。
   - L577：`ece([], [], n_bins)` = 0.0。
   - 返回 (0.0, 0.0, 0.0)。**不崩溃**。

3. `brier_parts(probs=[], labels=[], n_bins)`（L586-633）：
   - L607：`n = 0`。
   - L613：`base_rate = labels.mean()` = `np.mean([])` = nan（RuntimeWarning）。
   - L614：`uncertainty = nan * (1 - nan)` = nan。
   - L616-630：所有 bin `mask.sum() == 0`，`continue` 跳过，`reliability` = 0.0，`resolution` = 0.0。
   - L632：`brier_total = 0.0 - 0.0 + nan` = nan。
   - 返回 (nan, 0.0, 0.0, nan)。**不崩溃**，但返回 nan。

4. `brier_raw(probs=[], labels=[])`（L636-640）：`np.mean([])` = nan。**不崩溃**。

5. `mce(probs=[], labels=[], n_bins)`（L643+）：类似 ece，返回 0.0 或 nan。**不崩溃**。

**成立部分**：空数组边界确实未显式处理，`brier_parts` 和 `brier_raw` 返回 nan，nan 静默传播到 CSV，与攻击5 同属"未处理空数组"问题。

**夸大部分**：攻击称"compute_all_metrics 崩溃，被 L716-722 except 捕获"，但实际代码对空数组不崩溃（`if mask.sum() == 0: continue` 防止了除以零，`rng.choice(0, 0, replace=True)` 返回空数组不报错），而是返回 nan。这是静默错误而非崩溃，严重程度低于"崩溃"。

**修补方案**: 与攻击5 合并修复（加空数组检查并提前返回）。

---

### 攻击点7: [轻微] n_dropped_cal 未包含全零行数，日志中两个丢弃警告不一致
**判定**: 成立

**分析**:
经实际代码验证，攻击成立。

- L432：`n_dropped_cal = int((cal_labels >= num_classes).sum())` 只统计标签 ≥ num_classes 的样本数。
- L434-437 警告：`f"丢弃 {n_dropped_cal} 个 cal + {n_dropped_ood} 个 ood 样本 (标签 >= num_classes)"`。
- L449-452 S1 修复警告：`f"{cal_zero_rows.sum()} 个 cal 样本截断后全零，丢弃"`，单独打印，**未累计到 n_dropped_cal**。

日志中两个独立的丢弃警告，分析者只看第一行会误以为 cal 丢弃 50 个，实际丢弃 55 个（50 标签截断 + 5 全零行）。

**修补方案**:
- 文件：`scripts/run_e5_inception_lite.py`
- 改动（L449-452 S1 修复块内，累计计数）：
  ```python
  if cal_zero_rows.any():
      n_zero_cal = int(cal_zero_rows.sum())
      n_dropped_cal += n_zero_cal
      print(f"[WARN] {source}→{target} seed={seed}: {n_zero_cal} 个 cal 样本截断后全零，丢弃（累计 cal 丢弃 {n_dropped_cal}）")
      ...
  ```
  ood 侧同理。

---

### 攻击点8: [轻微] build_model 先构造默认 backbone 再替换，浪费计算
**判定**: 成立

**分析**:
经实际代码验证，攻击成立。

`run_e5_inception_lite.py` L255-263：
```python
model = ECGClassifier(
    in_channels=12, d_model=resnet_d_model, n_layers=2,
    num_classes=num_classes, dropout=dropout,
    backbone_type="resnet1d",  # 触发 ECGClassifier.__init__ 调用 build_backbone("resnet1d", ...)
)
model.backbone = ECGResNet1D(  # 替换为新构造的 ECGResNet1D
    in_channels=12, d_model=resnet_d_model,
    block_layers=block_layers, dropout=dropout,
)
```

`ECGClassifier.__init__` 会调用 `build_backbone("resnet1d", ...)` 创建默认 `ECGResNet1D(block_layers=(2,2,2,2))`（baselines.py L234-236），其参数在 L260-263 替换后被立即丢弃（GC 回收）。Level 3 三个变体各触发一次，共浪费 3 次默认 ECGResNet1D 构造。

无功能 bug，但属计算浪费。

**修补方案**:
- 文件：`scripts/run_e5_inception_lite.py` 或 `src/models/ecg_classifier.py`
- 方案A（推荐）：`ECGClassifier` 支持 `backbone=None` 参数，跳过默认构造：
  ```python
  model = ECGClassifier(
      in_channels=12, d_model=resnet_d_model, n_layers=2,
      num_classes=num_classes, dropout=dropout,
      backbone=None,  # 跳过默认构造
  )
  model.backbone = ECGResNet1D(...)
  ```
- 方案B：`build_model` 直接构造 backbone + pool + classifier 而非通过 ECGClassifier。

---

### 攻击点9: [轻微] width=0 会被当作 falsy，resnet_d_model 退化为 d_model
**判定**: 成立

**分析**:
经实际代码验证，攻击成立。

L252：`resnet_d_model = width or d_model`，Python `or` 运算符对 falsy 值短路。`width=0` 时，`0 or d_model` = d_model，width=0 被静默忽略。

虽然 width=0 无实际意义（d_model=0 不合理），但这是 falsy 陷阱，与 `width=None`（合法的"未指定"语义）行为混淆。

**修补方案**:
- 文件：`scripts/run_e5_inception_lite.py`
- 改动（L252）：
  ```python
  resnet_d_model = d_model if width is None else width
  ```

---

### 攻击点10: [轻微] arch_override 字符串精确匹配，大小写敏感
**判定**: 成立

**分析**:
经实际代码验证，攻击成立。

L243：`if arch_override == "resnet1d":` 精确字符串匹配，"ResNet1D"、"RESNET1D" 不匹配。不匹配时静默走默认 InceptionTime-Lite 路径，无警告。

当前 levels 列表 L177-182 中 `arch="resnet1d"` 小写，匹配，**当前无 bug**。但未来若有人传 "ResNet1D"（如命令行扩展），会静默走默认路径，属潜在风险。

对比 `build_backbone`（baselines.py L229）：`name = name.lower()` 做了大小写归一化，build_model L243 未对齐此逻辑。

**修补方案**:
- 文件：`scripts/run_e5_inception_lite.py`
- 改动（L243）：
  ```python
  if arch_override and arch_override.lower() == "resnet1d":
  ```

---

### 攻击点11: [轻微] Level 3 的 use_checkpoint/n_filters 被丢弃
**判定**: 成立

**分析**:
经实际代码验证，攻击成立。

- L177-182 Level 3 配置：`{"n_filters": 32, "use_checkpoint": True, "arch": "resnet1d", "depth": 3, "width": 32}`。
- L243-264 build_model arch_override="resnet1d" 路径中，`n_filters` 和 `use_checkpoint` 参数被完全忽略（`ECGResNet1D` 不支持这两个概念，ResNet1D 路径未引用它们）。

Level 3 的 `n_filters=32, use_checkpoint=True` 是死参数，可能误导维护者以为 ResNet1D 也用这些参数。

**修补方案**:
- 文件：`scripts/run_e5_inception_lite.py`
- 方案A（推荐）：levels 列表 Level 3 项移除 `n_filters` 和 `use_checkpoint`：
  ```python
  (3, {"arch": "resnet1d", "depth": 3, "width": 32}, "Level 3: ..."),
  ```
- 方案B：build_model ResNet1D 路径加注释说明这两个参数被忽略。

---

### 攻击点12: [轻微] Level 0 和 Level 1 配置可能重复
**判定**: 成立

**分析**:
经实际代码验证，攻击成立。

- L173 Level 0：`{"n_filters": n_filters, "use_checkpoint": use_checkpoint}`（用户传入）。
- L175 Level 1：`{"n_filters": 32, "use_checkpoint": False}`（硬编码）。

用户传 `--n-filters 32`（且未传 `--use-checkpoint`）时，Level 0 = Level 1 配置。Level 0 OOM 失败后，Level 1 重复尝试相同配置，必然再次 OOM，浪费一次尝试和显存清理时间。

**修补方案**:
- 文件：`scripts/run_e5_inception_lite.py`
- 改动（levels 列表构造时去重）：
  ```python
  levels = [(0, {"n_filters": n_filters, "use_checkpoint": use_checkpoint}, "...")]
  if not (n_filters == 32 and not use_checkpoint):
      levels.append((1, {"n_filters": 32, "use_checkpoint": False}, "Level 1: ..."))
  levels.extend([(2, ...), (3, ...), ...])
  ```

---

### 攻击点13: [轻微] S1 全零行检测用 == 0，浮点数精度边界
**判定**: 部分成立

**分析**:
攻击方向正确（浮点精度边界存在），但严重程度被夸大（实际下溢概率极低，且建议修补有副作用）。

**成立部分**：
- L448 `cal_zero_rows = (cal_row_sums.flatten() == 0)` 精确浮点比较。
- 截断后若前 num_classes 列都极小（如 1e-300），sum 可能数值下溢为 0.0（精确 0，S1 检测✓）或保持极小（非零，S1 不检测）。
- 边界情况：sum=1e-308（接近 float64 下限），归一化后概率 ~1e308，后续 log 可能 inf。

**夸大部分**：
- 攻击自承"理论边界，实际 softmax 输出极少下溢到 1e-300（通常最小 ~1e-40）"。softmax 输出 = exp(logit) / Σexp(logit)，logit 经 clip 到 [EPS, 1-EPS]，最小概率约 1e-7 量级，截断 5→4 列后 sum 最小约 4e-7，远高于 1e-300 下溢阈值。
- 建议修补 `< 1e-30` 有副作用：会丢弃 sum 在 (0, 1e-30) 区间的合法样本（虽概率极小但非全零），引入额外样本损失，且阈值 1e-30 缺乏理论依据。
- `== 0` 对检测精确下溢（NaN 主因 0/0）是正确且必要的，S1 修复的核心目标（防 NaN）已达成。

**结论**：S1 的 `== 0` 检测对主要威胁（精确下溢导致 0/0=NaN）是正确且充分的。near-zero（非零但极小）导致的数值不稳定是独立的数值分析问题，不应混入 S1 修复范畴。若需进一步加固，应在归一化后加 `np.clip` 而非改 S1 检测阈值。

**修补方案**（可选，低优先级）:
- 文件：`scripts/run_e5_inception_lite.py`
- 改动（L454 归一化后加 clip 防止极小 sum 放大）：
  ```python
  cal_probs = cal_probs / cal_row_sums
  # 防止 near-zero sum 归一化后数值放大
  cal_probs = np.clip(cal_probs, 0.0, 1.0)
  ```
  ood 侧同理。注意：此改动不影响 S1 的 `== 0` 检测逻辑。

---

### 攻击点14: [轻微] SUBSPACE_CPSC 顺序修改后多处 docstring 未同步更新
**判定**: 成立

**分析**:
经实际代码验证，攻击成立。

- `mapping.py` L83：`SUBSPACE_CPSC = ("NORM", "MI", "STTC", "CD")`（新顺序，F2 修复）。
- `mapping.py` L6：`主分析降级 {NORM, CD, STTC, MI} 4类子空间`（旧顺序，**未更新**）。
- `train.py` L497：`SUBSPACE_CPSC={NORM,CD,STTC,MI}（4类）`（旧顺序，**未更新**）。

文档与代码不一致，维护者可能被误导。F2 修复改了代码和 L79-82 注释，但遗漏了 L6 模块 docstring 和 train.py L497 docstring。

**修补方案**:
- 文件1：`src/data/mapping.py`
- 改动（L6）：
  ```
  - CPSC2018+2019 HYP 极稀有(n=11) → 主分析降级 {NORM, CD, STTC, MI} 4类子空间
  + CPSC2018+2019 HYP 极稀有(n=11) → 主分析降级 {NORM, MI, STTC, CD} 4类子空间
  ```
- 文件2：`scripts/train.py`
- 改动（L497）：
  ```
  - SUBSPACE_CPSC={NORM,CD,STTC,MI}（4类）
  + SUBSPACE_CPSC={NORM,MI,STTC,CD}（4类）
  ```

---

## 反反方独立验证：F2/F1/F3+S7+M1 核心修复正确性

为公平起见，反反方对反方"修复正确性确认"章节的关键结论进行独立验证：

### F2 修复（SUBSPACE_CPSC 顺序）——反方确认正确，反反方复核✓
- `mapping.py` L60：`SUPERCLASSES = ("NORM", "MI", "STTC", "CD", "HYP")`。
- `SUPERCLASSES[:4]` = `("NORM", "MI", "STTC", "CD")`。
- `mapping.py` L83：`SUBSPACE_CPSC = ("NORM", "MI", "STTC", "CD")`。
- **`SUBSPACE_CPSC == SUPERCLASSES[:4]` ✓**，标签语义错位已消除。
- `filter_subspace`（L483）用 `set(allowed)`，顺序不影响过滤行为，仅影响 `enumerate(subspace)` 生成的 label_map。修改后 4 类编码 = 5 类编码前 4 位，ptbxl→cpsc 与 chapman→cpsc 两个方向的 MI/CD 预测对齐。✓
- 影响范围：所有 4 类数据集标签编码改变，需重跑（终审报告 L246 已明确"需重跑 cpsc 训练"）。✓

### F1 修复（build_model ResNet1D 变体）——反方确认基本正确，反反方复核✓
- `run_e5_inception_lite.py` L250：`block_layers_map = {3: (1, 1, 1), 5: (2, 2, 1), 7: (2, 2, 2, 1)}`，三个 depth 对应不同 block_layers。✓
- L260-263：`model.backbone = ECGResNet1D(..., block_layers=block_layers)` 真正构造不同 backbone。✓
- `baselines.py` L72-79：`ECGResNet1D.__init__` 接受 `block_layers` 参数，L99-103 `for i, n_blocks in enumerate(block_layers)` 按 block_layers 构造 stages。✓
- `ECGClassifier.forward` 调用 `self.backbone(x)`，替换后调用新 backbone。✓
- `nn.Module.__setattr__` 自动注销旧 backbone 参数、注册新 backbone 参数，optimizer 创建时用 `model.parameters()` 获取新参数，梯度正常回传。✓
- `_train_adapter`（L655-666）传递 `arch_override=params.get("arch")`、`depth=params.get("depth")`、`width=params.get("width")`。✓
- `train_single`（L284-294）接收参数，L329-333 传给 `build_model`。✓

### F3+S7+M1 修复（levels 列表 + report_oom_level 条件）——反方确认正确，反反方复核✓
- L173 levels 第一项 `(0, {"n_filters": n_filters, "use_checkpoint": use_checkpoint}, ...)` 用传入参数。✓
- L175-182 Level 1/2/3 配置正确，S7 重复 Level 1 已消除（第一项 level=0 而非 level=1）。✓
- L190：`report_oom_level(level, desc) if level > 0 else None`，Level 0 不触发 OOM 报告。✓
- 命令行 `--n-filters`/`--use-checkpoint` 通过 `try_train_with_oom_fallback` 形参传入 levels 第一项。✓

### S1 修复（全零行检测）——反方确认逻辑正确但不完整，反反方复核✓
- L447-454 cal_probs 全零行检测：检测、丢弃、重新计算 row_sums、归一化。✓
- L456-463 ood_probs 全零行检测：同上。✓
- 覆盖 cal_probs 和 ood_probs 两个路径。✓
- **不完整**：未同步截断 tgt_clusters（攻击1），未处理空数组边界（攻击5/6）。反方此判断准确。

---

## 总结

### 需要进一步修复的问题清单（按优先级）

| 优先级 | 攻击点 | 问题 | 修补文件 |
|--------|--------|------|----------|
| P0-紧急 | 攻击1 | tgt_clusters 未同步截断，benefit_inference IndexError | run_e5_inception_lite.py L443/L463 |
| P1-高 | 攻击5 | cal 空数组未提前返回，fit_temperature 返回 nan 静默传播 | run_e5_inception_lite.py L463 后 |
| P1-高 | 攻击2 | result dict 缺少截断统计字段（S3/M2 未完成） | run_e5_inception_lite.py L500-514 |
| P1-高 | 攻击3+4 | info dict 缺少 arch_override/depth/width，CSV arch 列失真 | run_e5_inception_lite.py L368-380 |
| P2-中 | 攻击6 | ood 空数组未提前返回（部分成立，nan 非崩溃） | run_e5_inception_lite.py L463 后 |
| P2-中 | 攻击7 | n_dropped_cal 未含全零行数，日志不一致 | run_e5_inception_lite.py L449-452 |
| P3-低 | 攻击14 | docstring 未同步更新 | mapping.py L6, train.py L497 |
| P3-低 | 攻击8 | build_model 浪费默认 backbone 构造 | run_e5_inception_lite.py L255 |
| P3-低 | 攻击9 | width=0 falsy 陷阱 | run_e5_inception_lite.py L252 |
| P3-低 | 攻击10 | arch_override 大小写敏感 | run_e5_inception_lite.py L243 |
| P3-低 | 攻击11 | Level 3 死参数 n_filters/use_checkpoint | run_e5_inception_lite.py L177-182 |
| P3-低 | 攻击12 | Level 0/1 配置可能重复 | run_e5_inception_lite.py L173-175 |
| P4-观察 | 攻击13 | S1 == 0 浮点精度边界（部分成立，极低概率） | 可选 clip 加固 |

### 已确认修复完成的问题
- **F2 标签语义错位**：SUBSPACE_CPSC 顺序改为 (NORM, MI, STTC, CD)，与 SUPERCLASSES[:4] 完全一致。✓
- **F1 ResNet1D 变体激活**：build_model 用 depth 控制 block_layers，真正构造不同深度 backbone，梯度可回传。✓
- **F3 命令行参数生效**：levels 第一项用传入 n_filters/use_checkpoint。✓
- **S7 levels 重复消除**：第一项 level=0 而非 level=1。✓
- **M1 report_oom_level 条件**：Level 0 不误报 OOM。✓
- **S1 全零行检测（主路径）**：cal_probs 和 ood_probs 两路径均检测并丢弃全零行，防 NaN。✓

### 对正方修复的总体评价

**进步显著**：第一轮 3 致命 + 7 严重 → 第二轮 0 致命 + 6 严重。3 个致命缺陷（F1/F2/F3）已正确修复，其中 F2 标签语义错位这一最危险缺陷修复正确且完整，反方"修复正确性确认"章节诚实可信。F1 ResNet1D 变体激活修复经反反方独立验证确认正确（block_layers 真正生效、梯度可回传、nn.Module.__setattr__ 自动管理参数注册）。

**遗留问题**：S1 修复引入新的严重问题（攻击1：tgt_clusters 长度不匹配），这是本轮最关键的遗留——benefit_inference 的 cluster bootstrap 会 IndexError 或产生错误结果。S3/M2 修复未完成（攻击2：result dict 缺字段），CSV 不可追溯。空数组边界未处理（攻击5/6），极端情况静默 nan。

**反方攻击质量评价**：14 个攻击点均经实际代码验证，无稻草人论证、无误解正方意图、无反例不成立。攻击1-5、7-12、14 完全成立，攻击6/13 部分成立（方向正确但严重程度略有夸大）。反方在"修复正确性确认"章节诚实承认 F2/F1/F3+S7+M1 修复正确，体现了审稿的公正性。建议正方优先修复攻击1（tgt_clusters 同步截断），其次修复攻击2-5（result/info dict 字段 + 空数组边界），完成终审清单第 9 项。
