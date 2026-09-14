# P0-6+7 回炉修复反方攻击报告

> **审查代理**：反方挑刺代理（GLM-5.2）
> **审查日期**：2026-09-09
> **审查任务**：任务 #78，对正方代理第二轮 P0-6+7 回炉修复进行全方位攻击审查
> **审查标准**：CBM 期刊审稿标准——代码正确性无懈可击、边界条件全覆盖、副作用可追溯

## 攻击摘要
- **审查文件**：
  - `src/data/mapping.py`（SUBSPACE_CPSC 顺序修改 L83）
  - `scripts/run_e5_inception_lite.py`（F1/F3/S1/S7/M1 修改）
  - 辅助审查：`src/models/baselines.py`、`src/models/ecg_classifier.py`、`src/models/inceptiontime_lite.py`、`scripts/train.py`、`src/utils/calibration.py`、`scripts/eval_l2_shift.py`、`scripts/eval_transfer.py`
- **发现攻击点**：14 个（0 致命 / 6 严重 / 8 轻微）
- **核心结论**：F2 标签语义错位修复**正确且完整**；F1 ResNet1D 变体激活修复**基本正确**（梯度可回传、block_layers 真正生效）；F3+S7+M1 命令行参数生效修复**正确**；S1 全零行检测修复**逻辑正确但未覆盖下游 cluster 长度对齐**，引入新的隐性崩溃路径。**最严重问题是截断+S1 修复后 ood_probs 与 tgt_clusters 长度不匹配，benefit_inference 的 cluster bootstrap 会 IndexError**——这是第一轮修复的遗留问题，S1 修复未修复反而加深。

---

## 攻击点列表

### 攻击1 [严重]：截断+S1 修复后 ood_probs 与 tgt_clusters 长度不匹配，benefit_inference 会 IndexError

- **位置**：`scripts/run_e5_inception_lite.py` L418、L432-443、L456-463、L488-492
- **问题描述**：
  - L418 `tgt_ds, tgt_clusters = build_dataset(target, seed, ...)` 返回 `tgt_clusters`（target test 集的患者 ID 数组，长度 = 原始 test 集大小 N）。
  - L426-427 `ood_probs = tgt_eval["probs"]`、`ood_labels = tgt_eval["labels"]`，长度 = N。
  - L438-443 截断：`ood_keep = ood_labels < num_classes`，`ood_labels = ood_labels[ood_keep]`、`ood_probs = ood_probs[ood_keep][:, :num_classes]`。若 5→4 方向有 HYP 样本（标签=4≥4），截断后长度 = N - n_dropped_ood < N。**tgt_clusters 未同步截断**。
  - L456-463 S1 修复：`ood_zero_rows = (ood_row_sums.flatten() == 0)`，若有全零行，`ood_probs = ood_probs[~ood_zero_rows]`、`ood_labels = ood_labels[~ood_zero_rows]`。截断后长度进一步减少。**tgt_clusters 仍未同步截断**。
  - L488-492 `benefit = benefit_inference(max_probs_raw, max_probs_ts, correct_mask, ..., clusters=tgt_clusters)`。此时 `max_probs_raw` 长度 = S1 修复后 ood_probs 长度 < N，但 `tgt_clusters` 长度 = N。
  - `benefit_inference`（calibration.py L417-504）L479-482：`clusters = np.asarray(clusters); uniq = np.unique(clusters); cluster_indices = {c: np.where(clusters == c)[0] for c in uniq}`。docstring L543 明确要求"clusters: 患者ID数组（与probs等长）"。长度不匹配时，`np.where(clusters == c)[0]` 返回的索引可能 ≥ len(max_probs_raw)，cluster bootstrap 重采样时 IndexError 或静默使用错误索引。
- **反例/证据**：
  - 假设 ptbxl→cpsc 方向，target=cpsc，test 集有 1000 样本，其中 50 个 HYP（标签=4）。
  - 截断后 ood_probs 长度 = 950，tgt_clusters 长度 = 1000。
  - benefit_inference 用 tgt_clusters[950:1000] 的患者 ID 索引 max_probs_raw[950:1000]，IndexError。
  - 即使不 IndexError（若被丢弃的 50 个样本的患者 ID 与保留的 950 个不重叠），cluster bootstrap 的簇定义仍基于 1000 个样本，但 probs 只有 950 个，统计语义错误。
- **建议修补**：
  ```python
  # L438-443 截断后，同步截断 tgt_clusters
  tgt_clusters = tgt_clusters[ood_keep]
  # L456-463 S1 修复后，同步截断 tgt_clusters
  if ood_zero_rows.any():
      tgt_clusters = tgt_clusters[~ood_zero_rows]
  ```
  或更彻底：在截断前将 tgt_clusters 与 ood_labels 绑定为 DataFrame，统一过滤。

---

### 攻击2 [严重]：S3/M2 修复未完成——result dict 缺少截断统计字段

- **位置**：`scripts/run_e5_inception_lite.py` L500-514（result dict）
- **问题描述**：
  - 终审报告 `p0_final_verdict.md` L254 修补清单第 9 项明确要求："增加 `n_dropped_cal`, `n_dropped_ood`, `truncated`, `subspace_filtered` 字段（S3/M2）"。
  - 实际 result dict L500-514 只有 `n_ood`，**没有** `n_dropped_cal`、`n_dropped_ood`、`truncated`、`subspace_filtered` 字段。
  - L432-433 计算了 `n_dropped_cal` 和 `n_dropped_ood`，但只用于 L434-437 的控制台警告，未写入 result dict。
- **反例/证据**：
  - 5→4 方向迁移实验运行后，CSV 中无任何字段记录"丢弃了多少 cal/ood 样本"。
  - 论文审稿人问"ptbxl→cpsc 方向丢弃了多少 HYP 样本？"时，无法从 CSV 回答，需重新运行实验查看控制台日志。
- **建议修补**：
  ```python
  # L500-514 result dict 增加
  result = {
      ...,
      "n_dropped_cal": n_dropped_cal,
      "n_dropped_ood": n_dropped_ood,
      "n_dropped_cal_zero": int(cal_zero_rows.sum()) if cal_zero_rows.any() else 0,
      "n_dropped_ood_zero": int(ood_zero_rows.sum()) if ood_zero_rows.any() else 0,
      "truncated": (n_dropped_cal + n_dropped_ood) > 0,
      "subspace_filtered": num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target]),
  }
  ```

---

### 攻击3 [严重]：训练侧 info dict 缺少 arch_override/depth/width 字段，CSV arch 列始终显示 "inceptiontime_lite"

- **位置**：`scripts/run_e5_inception_lite.py` L369（`info["arch"] = ARCH_NAME`）
- **问题描述**：
  - `ARCH_NAME = "inceptiontime_lite"`（L105）是模块级常量。
  - L369 `info["arch"] = ARCH_NAME`，无论 `arch_override` 是 None 还是 "resnet1d"，info["arch"] 始终是 "inceptiontime_lite"。
  - Level 3 触发时（arch_override="resnet1d", depth=3/5/7, width=32/64/128），CSV 中 arch 列仍显示 "inceptiontime_lite"，**无法区分 InceptionTime-Lite 和 ResNet1D 变体**。
  - L370-371 记录了 `n_filters` 和 `use_checkpoint`，但**没有** `arch_override`、`depth`、`width` 字段。
- **反例/证据**：
  - Level 3 触发后，CSV 训练结果表：`arch=inceptiontime_lite, n_filters=32, use_checkpoint=True`。
  - 分析者误以为是 InceptionTime-Lite with n_filters=32（Level 1 降级），实际是 ResNet1D with depth=3, width=32（Level 3 降级）。
  - 论文 Table 1 报告"3 架构家族"时，无法从 CSV 追溯哪些实验实际用了 ResNet1D。
- **建议修补**：
  ```python
  # L368-380 info dict 增加
  info = {
      "dataset": dataset, "seed": seed,
      "arch": arch_override if arch_override else ARCH_NAME,  # 反映实际架构
      "arch_override": arch_override,  # None 表示默认
      "depth": depth, "width": width,
      ...,
  }
  ```

---

### 攻击4 [严重]：控制台 arch_display 与 CSV arch 字段不一致

- **位置**：`scripts/run_e5_inception_lite.py` L307-310（控制台）vs L369（CSV）
- **问题描述**：
  - L307 `arch_display = arch_override if arch_override else ARCH_NAME`，控制台显示实际架构（Level 3 时显示 "resnet1d"）。
  - L369 `info["arch"] = ARCH_NAME`，CSV 记录始终 "inceptiontime_lite"。
  - **控制台和 CSV 不一致**：Level 3 触发时，控制台显示 `arch=resnet1d`，CSV 记录 `arch=inceptiontime_lite`。
- **反例/证据**：
  - 运行日志：`[训练] cpsc seed=42 arch=resnet1d n_filters=32 depth=3 width=32`
  - CSV 记录：`arch=inceptiontime_lite, n_filters=32, use_checkpoint=True`（无 depth/width 列）
  - 调试时对照控制台和 CSV，无法匹配 Level 3 实验的记录。
- **建议修补**：与攻击3 合并修复，info["arch"] 用 arch_display。

---

### 攻击5 [严重]：全部 cal 样本被丢弃时未提前返回，fit_temperature 收到空数组返回 nan

- **位置**：`scripts/run_e5_inception_lite.py` L432-467
- **问题描述**：
  - L438-441 截断：`cal_keep = cal_labels < num_classes`，`cal_labels = cal_labels[cal_keep]`，`cal_probs = cal_probs[cal_keep][:, :num_classes]`。
  - L447-453 S1 修复：若全零行存在，`cal_probs = cal_probs[~cal_zero_rows]`，`cal_labels = cal_labels[~cal_zero_rows]`。
  - **边界情况**：若所有 cal 样本标签 ≥ num_classes（如 5→4 方向 cal 集全为 HYP），或截断后全零行全部被丢弃，`cal_probs` 为空数组 (0, num_classes)。
  - L466 `one_hot_cal = np.eye(num_classes)[cal_labels]`，空数组。
  - L467 `T = fit_temperature(cal_probs, one_hot_cal)`，fit_temperature L77 `nll_val = -np.mean(np.sum(val_y * log_probs, axis=1))`，`np.mean([])` 返回 nan（带 RuntimeWarning）。
  - L80-87 scipy.optimize.minimize 对 nan 目标函数返回 nan 解，T=nan。
  - L468 `ood_probs_ts = apply_temperature(ood_probs, nan)`，产生 nan 概率。
  - L474-475 `compute_all_metrics` 收到 nan 概率，返回 nan 指标。
  - L500-514 result dict 记录 nan，CSV 中静默写入 nan，**无显式错误**。
- **反例/证据**：
  - 极端情况：ptbxl→cpsc 方向，cal 集恰好全为 HYP 样本（概率极低但理论可能，尤其 `--limit` 小时）。
  - 实验运行完成，CSV 中 `ood_ece_raw=nan, ood_ece_ts=nan, delta_ece=nan`，无任何报错。
  - 论文审稿人发现 nan 行，质疑数据完整性。
- **建议修补**：
  ```python
  # L463 后、L466 前加
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

### 攻击6 [严重]：全部 ood 样本被丢弃时未提前返回，compute_all_metrics 收到空数组可能崩溃

- **位置**：`scripts/run_e5_inception_lite.py` L456-474
- **问题描述**：
  - 与攻击5 同理，若所有 ood 样本被截断或全零行丢弃，`ood_probs` 为空数组。
  - L470 `max_probs_raw = ood_probs.max(axis=1)`，空数组 max 返回空数组。
  - L472 `correct_mask = (ood_probs.argmax(axis=1) == ood_labels).astype(float)`，空数组。
  - L474 `raw_metrics = compute_all_metrics(max_probs_raw, correct_mask, n_bootstrap=1000)`。
  - compute_all_metrics L767 `bootstrap_ece(probs, labels, n_bins, n_bootstrap)`，bootstrap 重采样空数组可能崩溃（np.random.choice(0) 报错）或返回 nan。
  - L770 `brier_parts(probs, labels, n_bins=n_bins)`，空数组分箱可能除以零。
  - L773 `mce(probs, labels, n_bins)`，空数组可能崩溃。
- **反例/证据**：
  - 极端情况：cpsc→ptbxl 方向，target ptbxl test 集恰好全为 HYP 样本（概率极低但理论可能）。
  - compute_all_metrics 崩溃，被 L716-722 except 捕获，记录 error 行，但**攻击5 的 cal 空情况不被 except 捕获**（fit_temperature 不抛异常，返回 nan）。
- **建议修补**：与攻击5 合并修复，在 L463 后加空数组检查并提前返回。

---

### 攻击7 [轻微]：n_dropped_cal 未包含全零行数，日志中两个丢弃警告不一致

- **位置**：`scripts/run_e5_inception_lite.py` L432-437 vs L449-452
- **问题描述**：
  - L432 `n_dropped_cal = int((cal_labels >= num_classes).sum())` 只统计标签≥num_classes 的样本数。
  - L434-437 警告：`f"丢弃 {n_dropped_cal} 个 cal + {n_dropped_ood} 个 ood 样本 (标签 >= num_classes)"`。
  - L449-452 S1 修复警告：`f"{cal_zero_rows.sum()} 个 cal 样本截断后全零，丢弃"`，单独打印，**未累计到 n_dropped_cal**。
  - 日志中两个独立的丢弃警告，分析时可能遗漏全零行丢弃。
- **反例/证据**：
  - 日志：`[WARN] ptbxl→cpsc seed=42: 丢弃 50 个 cal + 30 个 ood 样本 (标签 >= num_classes=4)`
  - 紧接：`[WARN] ptbxl→cpsc seed=42: 5 个 cal 样本截断后全零，丢弃`
  - 分析者只看第一行，误以为 cal 丢弃 50 个，实际丢弃 55 个。
- **建议修补**：统一丢弃计数，`n_dropped_cal += int(cal_zero_rows.sum())`，合并警告。

---

### 攻击8 [轻微]：build_model 先构造默认 backbone 再替换，浪费计算

- **位置**：`scripts/run_e5_inception_lite.py` L255-263
- **问题描述**：
  - L255-259 `model = ECGClassifier(..., backbone_type="resnet1d")`，ECGClassifier.__init__ L61-67 调用 `build_backbone("resnet1d", ...)` 创建默认 ECGResNet1D（block_layers=(2,2,2,2)）。
  - L260-263 `model.backbone = ECGResNet1D(..., block_layers=block_layers)` 替换为新 ECGResNet1D。
  - 默认 backbone 的参数被构造后立即丢弃（GC 回收），浪费一次构造。
  - 虽然无功能 bug，但 Level 3 触发时每次都浪费一次 backbone 构造。
- **反例/证据**：Level 3 三个变体各触发一次，共浪费 3 次默认 ECGResNet1D 构造。
- **建议修补**：ECGClassifier 支持 `backbone=None` 参数跳过默认构造，或 build_model 直接构造 backbone + pool + classifier 而非通过 ECGClassifier。

---

### 攻击9 [轻微]：width=0 会被当作 falsy，resnet_d_model 退化为 d_model

- **位置**：`scripts/run_e5_inception_lite.py` L252
- **问题描述**：
  - L252 `resnet_d_model = width or d_model`，Python `or` 运算符对 falsy 值短路。
  - `width=0` 时，`0 or d_model` = d_model，width=0 被静默忽略。
  - 虽然 width=0 无实际意义（d_model=0 不合理），但这是 falsy 陷阱。
- **反例/证据**：理论上 `build_model(width=0)` 会用 d_model 而非 0。
- **建议修补**：`resnet_d_model = d_model if width is None else width`。

---

### 攻击10 [轻微]：arch_override 字符串精确匹配，大小写敏感

- **位置**：`scripts/run_e5_inception_lite.py` L243
- **问题描述**：
  - L243 `if arch_override == "resnet1d":` 精确字符串匹配，"ResNet1D"、"RESNET1D" 不匹配。
  - 不匹配时静默走默认 InceptionTime-Lite 路径，无警告。
  - levels 列表 L177-182 中 `arch="resnet1d"` 小写，匹配，当前无 bug。
  - 但未来若有人传 "ResNet1D"（如命令行扩展），会静默走默认路径。
- **建议修补**：`if arch_override and arch_override.lower() == "resnet1d":`，或用 build_backbone 的名称归一化逻辑。

---

### 攻击11 [轻微]：Level 3 的 use_checkpoint/n_filters 被丢弃

- **位置**：`scripts/run_e5_inception_lite.py` L243-264 vs L177-182
- **问题描述**：
  - levels 列表 L177-182 中 Level 3 配置 `{"n_filters": 32, "use_checkpoint": True, "arch": "resnet1d", "depth": 3, "width": 32}`。
  - build_model L243-264 arch_override="resnet1d" 路径中，`n_filters` 和 `use_checkpoint` 参数被完全忽略（ECGResNet1D 不支持这两个概念）。
  - Level 3 的 `n_filters=32, use_checkpoint=True` 是死参数，可能误导维护者以为 ResNet1D 也用这些参数。
- **建议修补**：levels 列表 Level 3 项移除 `n_filters` 和 `use_checkpoint`，或 build_model ResNet1D 路径加注释说明这两个参数被忽略。

---

### 攻击12 [轻微]：Level 0 和 Level 1 配置可能重复

- **位置**：`scripts/run_e5_inception_lite.py` L173-175
- **问题描述**：
  - L173 Level 0：`{"n_filters": n_filters, "use_checkpoint": use_checkpoint}`（用户传入）。
  - L175 Level 1：`{"n_filters": 32, "use_checkpoint": False}`（硬编码）。
  - 用户传 `--n-filters 32` 时，Level 0 = Level 1 配置。
  - Level 0 OOM 失败后，Level 1 重复尝试相同配置，必然再次 OOM，浪费一次尝试和显存清理时间。
- **反例/证据**：`python scripts/run_e5_inception_lite.py --n-filters 32`，Level 0 OOM 后 Level 1 重复 OOM。
- **建议修补**：Level 1 检查 `if n_filters == 32 and not use_checkpoint: skip`，或 levels 列表去重。

---

### 攻击13 [轻微]：S1 全零行检测用 == 0，浮点数精度边界

- **位置**：`scripts/run_e5_inception_lite.py` L448、L457
- **问题描述**：
  - L448 `cal_zero_rows = (cal_row_sums.flatten() == 0)` 精确浮点比较。
  - softmax 输出理论上不会精确为 0（指数函数），但截断后若前 num_classes 列都极小（如 1e-300），sum 可能数值下溢为 0.0（精确 0）或保持极小（非零）。
  - 若 sum=1e-300（非零），S1 不检测，L454 `cal_probs / cal_row_sums` 归一化后概率放大到 1.0，数值不稳定但不会 NaN。
  - 若 sum=0.0（精确 0，下溢），S1 检测并丢弃。✓
  - 边界情况：sum=1e-308（接近 float64 下限），归一化后概率 ~1e308，后续 log 可能 inf。
- **反例/证据**：理论边界，实际 softmax 输出极少下溢到 1e-300（通常最小 ~1e-40）。
- **建议修补**：`cal_zero_rows = (cal_row_sums.flatten() < 1e-30)`，用阈值代替精确比较。

---

### 攻击14 [轻微]：SUBSPACE_CPSC 顺序修改后多处 docstring 未同步更新

- **位置**：
  - `src/data/mapping.py` L6：`主分析降级 {NORM, CD, STTC, MI} 4类子空间`（旧顺序）
  - `scripts/train.py` L497：`SUBSPACE_CPSC={NORM,CD,STTC,MI}（4类）`（旧顺序）
- **问题描述**：
  - mapping.py L83 已改为 `SUBSPACE_CPSC = ("NORM", "MI", "STTC", "CD")`，L79-82 注释已更新。
  - 但 L6 模块 docstring 仍写 `{NORM, CD, STTC, MI}`（旧顺序）。
  - train.py L497 build_cpsc_datasets docstring 仍写 `SUBSPACE_CPSC={NORM,CD,STTC,MI}`（旧顺序）。
  - 文档与代码不一致，维护者可能被误导。
- **反例/证据**：
  - mapping.py L6: `- CPSC2018+2019 HYP 极稀有(n=11) → 主分析降级 {NORM, CD, STTC, MI} 4类子空间`
  - mapping.py L83: `SUBSPACE_CPSC = ("NORM", "MI", "STTC", "CD")`
  - 顺序不一致。
- **建议修补**：更新 mapping.py L6 和 train.py L497 docstring 为 `{NORM, MI, STTC, CD}`。

---

## 修复正确性确认（反方独立验证）

为公平起见，以下修复点经反方独立验证确认**正确**：

### F2 修复（SUBSPACE_CPSC 顺序）——正确
- mapping.py L83 `SUBSPACE_CPSC = ("NORM", "MI", "STTC", "CD")` 与 SUPERCLASSES[:4] = ("NORM", "MI", "STTC", "CD") 完全一致。✓
- 全局 grep 确认 SUBSPACE_CPSC 引用：mapping.py（定义）、run_e5_inception_lite.py L305/L414、eval_l2_shift.py L72、eval_transfer.py L101、train.py L351/L440/L523。
- train.py L351/L440/L523 用 `enumerate(subspace)` 生成 label_map，修改后 4 类编码 = 5 类编码前 4 位，消除标签语义错位。✓
- filter_subspace L483 用 `set(allowed)`，顺序不影响过滤行为。✓
- **影响范围**：所有 4 类数据集（cpsc 训练、ptbxl/chapman 4 类模式）标签编码改变，需重跑。这是预期的（终审报告 L246 明确"需重跑 cpsc 训练"）。

### F1 修复（build_model ResNet1D 变体）——基本正确
- build_model L250 `block_layers_map = {3: (1, 1, 1), 5: (2, 2, 1), 7: (2, 2, 2, 1)}`，三个 depth 对应不同 block_layers。✓
- L260-263 `model.backbone = ECGResNet1D(..., block_layers=block_layers)` 真正构造不同 backbone。✓
- ECGClassifier.forward L100 `feats = self.backbone(x)` 调用 self.backbone，替换后调用新 backbone。✓
- ECGClassifier.__init__ L55-82 无 hook/buffer 依赖 backbone，替换安全。✓
- nn.Module.__setattr__ 自动注销旧 backbone 参数、注册新 backbone 参数，optimizer 创建时（train_model 内部）用 model.parameters() 获取新参数。✓ 梯度正常回传。
- _train_adapter L655-666 传递 arch/depth/width。✓
- train_single L284-294 接收 arch_override/depth/width，L329-333 传给 build_model。✓
- baselines.py L61 ECGResNet1D 类存在，L72-79 接受 block_layers 参数。✓

### F3+S7+M1 修复（levels 列表 + report_oom_level 条件）——正确
- L173 levels 第一项 `(0, {"n_filters": n_filters, "use_checkpoint": use_checkpoint}, ...)` 用传入参数。✓
- L175-182 Level 1/2/3 配置正确，S7 重复 Level 1 已消除（第一项 level=0）。✓
- L190 `report_oom_level(level, desc) if level > 0 else None`，Level 0 不触发 OOM 报告。✓
- 命令行 `--n-filters`/`--use-checkpoint` 通过 try_train_with_oom_fallback 形参传入 levels 第一项。✓

### S1 修复（全零行检测）——逻辑正确但不完整
- L447-454 cal_probs 全零行检测：检测、丢弃、重新计算 row_sums、归一化。✓
- L456-463 ood_probs 全零行检测：同上。✓
- 覆盖 cal_probs 和 ood_probs 两个路径。✓
- **但不完整**：未同步截断 tgt_clusters（攻击1），未处理空数组边界（攻击5/6）。

---

## 总结

### 修复完成度评估

| 修复项 | 终审清单 | 实际完成 | 完成度 |
|--------|---------|---------|--------|
| F2 SUBSPACE_CPSC 顺序 | L246 | mapping.py L83 已改 | 100% |
| F1 train_single 签名 | L247 | L284-294 已加参数 | 100% |
| F1 _train_adapter 传递 | L248 | L655-666 已传递 | 100% |
| F1 build_model depth 生效 | L249 | L250-263 已用 depth | 100% |
| F3 levels 第一项用传入参数 | L250 | L173 已改 | 100% |
| S1 全零行检测 | L251 | L447-463 已加检测 | 70%（未同步 clusters） |
| S7 levels 第一项 level=0 | L252 | L173 已改 | 100% |
| M1 report_oom_level 条件 | L253 | L190 已改 | 100% |
| S3/M2 result dict 字段 | L254 | **未完成** | 0% |

### 攻击点统计
- **致命**：0 个
- **严重**：6 个（攻击1-6）
- **轻微**：8 个（攻击7-14）
- **总计**：14 个

### 最严重问题
**攻击1**（截断后 ood_probs 与 tgt_clusters 长度不匹配）是本轮修复最严重问题。这是第一轮 P0-7 修复（截断）引入的遗留问题，S1 修复（全零行检测）加深了它（进一步丢弃行），但未修复。benefit_inference 的 cluster bootstrap 会 IndexError 或产生错误结果，导致 ΔECE CI 计算崩溃或静默错误。**这是隐式静默错误——实验运行完成、产出 CSV、可能无报错（若 IndexError 被 L716 except 捕获），但 ΔECE CI 字段缺失或错误**。

### 与第一轮修复对比
- 第一轮：3 致命 + 7 严重（F1/F2/F3 致命）
- 第二轮：0 致命 + 6 严重（F1/F2/F3 已修复，但 S1 引入新严重问题 + S3/M2 未完成）
- **进步**：3 个致命缺陷已消除，F2 标签语义错位这一最危险缺陷已正确修复。
- **遗留**：S3/M2 修复未完成（攻击2-4），S1 修复引入新严重问题（攻击1/5/6）。

### 建议
1. **立即修复攻击1**（tgt_clusters 同步截断）——这是唯一可能导致崩溃的严重问题。
2. **修复攻击2-4**（result/info dict 字段）——完成终审清单第 9 项，使 CSV 可追溯。
3. **修复攻击5-6**（空数组边界）——防御性编程，防止极端情况静默 nan。
4. **修复攻击14**（docstring 同步）——文档一致性。
5. 其余轻微攻击可后续迭代。
