# P0-6+7 反反方回应报告

> **反反方代理交付**（任务 #70）。本报告对反方攻击报告 `docs/p0_attack_p0_6_7.md` 中 14 个攻击点（3 致命 + 7 严重 + 4 轻微）进行逐条独立验证。
> **审查方法**：实际读取 `scripts/run_e5_inception_lite.py`、`src/models/baselines.py`、`src/data/mapping.py`、`scripts/train.py` 源代码，逐条验证反方声称的代码行为。
> **审查日期**：2026-09-09
> **审查立场**：独立审查者，非正方辩护人。攻击成立则诚实承认。

---

## 总体判定

**14 个攻击点中：14 个成立（含 2 个部分成立——攻击核心成立但范围/机制描述有偏差）。**

- **3 个致命攻击全部成立**：F1（Level 3 死代码）、F2（标签语义错位）、F3（命令行参数失效）
- **7 个严重攻击全部成立**：S1-S7
- **4 个轻微攻击全部成立**：M1-M4

**关键修正**（对反方攻击的修正，非反驳）：
1. **F2 影响范围被高估**：反方称"4 个迁移方向受影响"，实际只有 **2 个方向**（ptbxl→cpsc, chapman→cpsc）存在标签语义错位。cpsc→ptbxl 和 cpsc→chapman 方向的源/目标编码一致（均用 SUBSPACE_CPSC），不受 F2 影响（但受 S2 影响——HYP 样本被 filter_subspace 丢弃）。
2. **S2 机制描述偏差**：反方称"target 标签 4 的样本被 `ood_labels >= num_classes` 丢弃"，实际 4→5 方向 target 用 `subspace=SUBSPACE_CPSC` 构建，HYP 样本在 `build_dataset` 阶段就被 `filter_subspace` 剔除，不会进入截断逻辑。效果相同（HYP 不评估），但机制描述不准确。

**结论**：F2 标签语义错位**确认成立**，是本次修复中最危险的问题——P0-7 用隐式静默错误（标签错位，运行完成但结果无意义）替换了显式崩溃（IndexError，会停止）。建议 P0 级返工。

---

## 逐条回应

### F1: Level 3 ResNet1D fallback 死代码

- **反方主张**：Level 3 的 ResNet1D 变体（depth=3/5/7, width=32/64/128）无法被激活，因为 `_train_adapter` 闭包只提取 `n_filters/use_checkpoint`，忽略 `arch/depth/width`；且 `train_single` 函数签名不接受 `arch_override/depth/width`。

- **验证结果**：**成立**

- **详细分析**：逐行代码验证确认反方完全正确：

  1. `try_train_with_oom_fallback` 的 `levels` 列表（L169-179）Level 3 条目包含 `arch/depth/width` 键：
     ```python
     (3, {"n_filters": 32, "use_checkpoint": True, "arch": "resnet1d", "depth": 3, "width": 32}, ...)
     ```
  2. `_train_adapter` 闭包（L607-612）只提取 `n_filters` 和 `use_checkpoint`：
     ```python
     def _train_adapter(params, dev, _ds=dataset, _seed=seed):
         return train_single(
             _ds, _seed, args, dev,
             n_filters=params.get("n_filters", 48),
             use_checkpoint=params.get("use_checkpoint", False),
         )  # arch/depth/width 被丢弃
     ```
  3. `train_single` 签名（L268-275）：`def train_single(dataset, seed, args, device, n_filters=48, use_checkpoint=False)` —— 无 `arch_override/depth/width` 参数。
  4. `train_single` 内部调用 `build_model`（L299-302）也不传 `arch_override`。

  **反例验证**：当 Level 2（n_filters=32+checkpoint）OOM 后进入 Level 3（arch=resnet1d, depth=3, width=32），`_train_adapter` 忽略 `arch=resnet1d`，仍调用 `train_single(..., n_filters=32, use_checkpoint=True)` —— 与 Level 2 完全相同的 InceptionTime-Lite 配置，必然再次 OOM。三个 Level 3 变体全部如此，直接退到 Level 4。

- **反驳或修补**：攻击成立，无法反驳。修补方案：

  ```python
  # 1. train_single 增加 arch_override/depth/width 参数
  def train_single(dataset, seed, args, device, n_filters=48, use_checkpoint=False,
                   arch_override=None, depth=None, width=None):
      ...
      model = build_model(num_classes=num_classes, n_filters=n_filters,
                          use_checkpoint=use_checkpoint, d_model=args.d_model, dropout=0.1,
                          arch_override=arch_override, depth=depth, width=width).to(device)

  # 2. _train_adapter 传递所有参数
  def _train_adapter(params, dev, _ds=dataset, _seed=seed):
      return train_single(_ds, _seed, args, dev,
          n_filters=params.get("n_filters", 48),
          use_checkpoint=params.get("use_checkpoint", False),
          arch_override=params.get("arch"),
          depth=params.get("depth"),
          width=params.get("width"))
  ```

  注意：还需配合 S5 修补（build_model 的 resnet1d 路径需用 depth 构造真正的不同 backbone）。

---

### F2: 标签语义错位（最严重攻击）

- **反方主张**：`SUPERCLASSES=("NORM","MI","STTC","CD","HYP")` 中 MI=1, CD=3，但 `SUBSPACE_CPSC=("NORM","CD","STTC","MI")` 中 CD=1, MI=3。标签 1 和 3 语义互换。P0-7 截断只做数值截断不做语义重映射，导致 MI/CD 预测全错。反方称 6 个迁移方向中 4 个受影响。

- **验证结果**：**成立（但影响范围修正为 2 个方向，非 4 个）**

- **详细分析**：

  **Step 1：确认标签编码定义**（mapping.py L60, L80）：
  ```python
  SUPERCLASSES = ("NORM", "MI", "STTC", "CD", "HYP")     # NORM=0, MI=1, STTC=2, CD=3, HYP=4
  SUBSPACE_CPSC = ("NORM", "CD", "STTC", "MI")            # NORM=0, CD=1, STTC=2, MI=3
  ```
  标签 1 和 3 的语义确实对调：SUPERCLASSES 中 1=MI/3=CD，SUBSPACE_CPSC 中 1=CD/3=MI。

  **Step 2：确认各数据集实际使用的 label_map**（train.py 验证）：
  - `build_ptbxl_datasets`（L354）：`label_map = {c: i for i, c in enumerate(SUPERCLASSES)}` → SUPERCLASSES 编码
  - `build_ptbxl_datasets` with subspace（L351）：`label_map = {c: i for i, c in enumerate(subspace)}` → subspace 编码
  - `build_chapman_datasets`（L443）：同 ptbxl
  - `build_cpsc_datasets`（L523）：`label_map = {c: i for i, c in enumerate(SUBSPACE_CPSC)}` → SUBSPACE_CPSC 编码

  **Step 3：逐方向追踪迁移评估的编码匹配**（run_e5_inception_lite.py L382-383）：
  ```python
  num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
  subspace = SUBSPACE_CPSC if num_classes == 4 else None
  ```

  | 方向 | num_classes | target subspace | source 训练编码 | target 评估编码 | F2 错位？ |
  |------|-------------|-----------------|----------------|----------------|-----------|
  | ptbxl→chapman | 5 | None | SUPERCLASSES | SUPERCLASSES | **否** |
  | ptbxl→cpsc | 4 | SUBSPACE_CPSC | SUPERCLASSES(5维) | SUBSPACE_CPSC(4维) | **是** |
  | chapman→ptbxl | 5 | None | SUPERCLASSES | SUPERCLASSES | **否** |
  | chapman→cpsc | 4 | SUBSPACE_CPSC | SUPERCLASSES(5维) | SUBSPACE_CPSC(4维) | **是** |
  | cpsc→ptbxl | 4 | SUBSPACE_CPSC | SUBSPACE_CPSC(4维) | SUBSPACE_CPSC(4维) | **否** |
  | cpsc→chapman | 4 | SUBSPACE_CPSC | SUBSPACE_CPSC(4维) | SUBSPACE_CPSC(4维) | **否** |

  **关键发现**：F2 只影响 **2 个方向**（ptbxl→cpsc, chapman→cpsc），即 5 类源 → 4 类目标的迁移。反方称 4 个方向受影响是**高估**——cpsc→ptbxl 和 cpsc→chapman 方向中，target 用 `subspace=SUBSPACE_CPSC` 构建（L383），label_map 用 SUBSPACE_CPSC 编码（train.py L351/L440），与 source cpsc 模型的训练编码一致，**无语义错位**。

  **Step 4：验证 5→4 方向的错位机制**（以 ptbxl→cpsc 为例）：
  - Source ptbxl 模型：5 维输出，按 SUPERCLASSES 训练 → 输出列 = [P(NORM), P(MI), P(STTC), P(CD), P(HYP)]
  - 截断（L410）：`cal_probs[:, :4]` = [P(NORM), P(MI), P(STTC), P(CD)]
  - Target cpsc 标签：NORM=0, CD=1, STTC=2, MI=3
  - **错位**：
    - 截断后 col 1 = P(MI)，但 target label 1 = CD → MI 概率被当作 CD 概率
    - 截断后 col 3 = P(CD)，但 target label 3 = MI → CD 概率被当作 MI 概率

  **反例验证**（与反方一致）：target 有 CD 样本（cpsc label=1），source 模型正确输出 P(CD)=0.8 在 col 3，截断后 argmax=3，但 target label=1，correct=(3==1)=False。模型预测正确却被算错。MI 样本同理。

- **反驳或修补**：攻击核心成立，无法反驳。影响范围修正为 2/6 方向（非 4/6）。

  **修补方案（推荐方案 A：统一编码顺序）**：
  ```python
  # 方案 A：统一 SUBSPACE_CPSC 顺序与 SUPERCLASSES 前 4 类一致
  # mapping.py
  SUBSPACE_CPSC = ("NORM", "MI", "STTC", "CD")  # 与 SUPERCLASSES[:4] 一致，HYP 降级
  # 这样 5→4 截断后 col 0-3 语义 = NORM/MI/STTC/CD = target label 0-3，无错位
  ```

  **方案 B（保留 SUBSPACE_CPSC 现有顺序，在迁移时做重映射）**：
  ```python
  # 在 eval_transfer_pair 截断前，构造 source→target 的标签重映射
  if DATASET_NUM_CLASSES[source] == 5 and DATASET_NUM_CLASSES[target] == 4:
      # source 用 SUPERCLASSES，target 用 SUBSPACE_CPSC
      # 构造 source_col_idx → target_label_idx 的映射
      source_order = SUPERCLASSES[:4]  # (NORM, MI, STTC, CD)
      target_order = SUBSPACE_CPSC     # (NORM, CD, STTC, MI)
      remap = [target_order.index(c) for c in source_order]
      # remap = [0, 3, 2, 1]  即 source col 0→target 0, col 1→target 3, col 2→target 2, col 3→target 1
      # 重排概率列：cal_probs = cal_probs[:, remap]  (但 remap 需扩展到 5 维)
  ```

  **方案 A 更优**：改动小（一行），且消除根因；方案 B 需在每个跨类数迁移点加重映射，易遗漏。

  **注意**：方案 A 改变 SUBSPACE_CPSC 顺序会影响 cpsc 数据集的 label_map，需同步检查 cpsc 训练结果的一致性（但 cpsc 训练用 SUBSPACE_CPSC 编码，改顺序只改标签编号不改类别集合，模型训练等价，只需重跑）。

---

### F3: 命令行参数 --n-filters/--use-checkpoint 被静默忽略

- **反方主张**：`try_train_with_oom_fallback` 的 `n_filters/use_checkpoint` 形参在函数体内完全未使用，备选配置由硬编码 `levels` 列表决定，导致命令行参数静默失效。

- **验证结果**：**成立**

- **详细分析**：

  1. 函数签名（L154-160）声明接受 `n_filters=48, use_checkpoint=False`：
     ```python
     def try_train_with_oom_fallback(train_fn, config, device, n_filters=48, use_checkpoint=False):
     ```
  2. 函数体（L168-202）只使用硬编码 `levels` 列表（L169-179），**从未引用 `n_filters` 或 `use_checkpoint` 形参**。
  3. main() 调用（L613-616）传入 `args.n_filters` 和 `args.use_checkpoint`，但被忽略。
  4. `levels` 第一项固定为 `{"n_filters": 48, "use_checkpoint": False}`，无论用户传什么。

  **反例验证**：`python scripts/run_e5_inception_lite.py --n-filters 32 --use-checkpoint` 期望从 n_filters=32+checkpoint 开始，但函数忽略传入值，硬编码从 n_filters=48 开始。用户参数被静默丢弃。

  **额外发现**：`config` 参数（传入 `{}`）同样是死参数，函数体内未使用（与 M3 一致）。

- **反驳或修补**：攻击成立。修补方案：
  ```python
  def try_train_with_oom_fallback(train_fn, config, device, n_filters=48, use_checkpoint=False):
      levels = [
          (0, {"n_filters": n_filters, "use_checkpoint": use_checkpoint}, "用户指定配置"),
          (1, {"n_filters": min(n_filters, 32), "use_checkpoint": use_checkpoint}, "Level 1: 减通道"),
          (2, {"n_filters": 32, "use_checkpoint": True}, "Level 2: + checkpoint"),
          # ... Level 3/4 不变
      ]
  ```

---

### S1: 截断后概率重归一化可能产生 NaN/Inf

- **反方主张**：L414-415 重归一化 `cal_probs / cal_probs.sum(axis=1, keepdims=True)` 未检查全零行，若样本所有概率质量在被截断列上，除以零产生 NaN。

- **验证结果**：**成立**

- **详细分析**：L414-415：
  ```python
  cal_probs = cal_probs / cal_probs.sum(axis=1, keepdims=True)
  ood_probs = ood_probs / ood_probs.sum(axis=1, keepdims=True)
  ```
  若 5 类 source 模型对某 cal 样本输出 `[0, 0, 0, 0, 1.0]`（100% HYP），截断到 4 列 → `[0, 0, 0, 0]`，sum=0，除法 → NaN。NaN 传播到 `fit_temperature` → T=NaN → 整个迁移实验结果为 NaN。

  代码中无任何全零行检查（已逐行确认 L401-415 无相关 guard）。

- **反驳或修补**：攻击成立。修补方案：
  ```python
  row_sums = cal_probs.sum(axis=1, keepdims=True)
  zero_mask = row_sums.squeeze() == 0
  if zero_mask.any():
      print(f"[WARN] {zero_mask.sum()} 个 cal 样本截断后概率全零，丢弃")
      cal_probs = cal_probs[~zero_mask]
      cal_labels = cal_labels[~zero_mask]
  else:
      cal_probs = cal_probs / row_sums
  # ood_probs 同理
  ```

---

### S2: 4→5 方向丢弃 target 第5类合法样本

- **反方主张**：4→5 方向（如 cpsc→ptbxl）中 target 第5类（HYP）样本被 `ood_labels >= num_classes` 丢弃，迁移评估不反映完整 target 分布。反方称 6 方向中 2 个受影响。

- **验证结果**：**成立（但机制描述需修正）**

- **详细分析**：

  反方称"target 有5类标签（0-4），标签4的样本被 `ood_labels >= num_classes` 丢弃"。实际机制略有不同：

  对于 cpsc→ptbxl：`num_classes=min(4,5)=4`，`subspace=SUBSPACE_CPSC`（L383）。target ptbxl 用 `build_dataset("ptbxl", seed, subspace=SUBSPACE_CPSC)` 构建，在 `build_ptbxl_datasets` 内部（train.py L342-351）调用 `filter_subspace(meta['label'], SUBSPACE_CPSC)`，**HYP 样本在数据集构建阶段就被剔除**，不会进入 `eval_transfer_pair` 的截断逻辑。

  因此截断逻辑的 `ood_labels >= num_classes` 检查实际上不会发现任何 HYP 样本（已被预过滤）。但**效果相同**：HYP 样本不参与迁移评估，4→5 方向的迁移指标不反映完整 target 分布。

  受影响方向：cpsc→ptbxl, cpsc→chapman（2 个），与反方一致。

- **反驳或修补**：攻击效果成立，机制描述需修正（是 filter_subspace 而非截断逻辑丢弃 HYP）。修补方案：
  - 方案 A：4→5 方向不截断 target，将 source 4 维输出补零到 5 维（但 source 模型无 HYP 神经元，补零无意义）
  - 方案 B（推荐）：明确报告"4→5 方向仅在 target 前4类上评估"，在 CSV 中标注 `n_dropped_hyp` 字段

---

### S3: 截断后迁移评估语义被偷换

- **反方主张**：截断后"target 上的表现"变成"target 子集上的表现"，论文若报告"6方向迁移评估"实际只有部分方向完整。

- **验证结果**：**成立**

- **详细分析**：
  - 5→4 方向：source cal 集 HYP 样本被截断丢弃，T 在子集拟合
  - 4→5 方向：target HYP 样本被 filter_subspace 丢弃，评估在子集上
  - CSV 元信息头注释（L489-500）未标注截断/子空间过滤发生

  语义偷换确实存在：报告的指标是"子集上的表现"而非"完整 target 上的表现"。

- **反驳或修补**：攻击成立。修补方案：在 result dict 中增加 `n_dropped_cal`, `n_dropped_ood`, `truncated`, `subspace_filtered` 字段，CSV 元信息头注释标注。

---

### S4: 截断后概率分布扭曲

- **反方主张**：5→4 截断后重归一化，第5类高置信度样本置信度剧变，ECE/Brier 失真。

- **验证结果**：**成立**

- **详细分析**：反例数学验证正确：
  - 原始 `[0.05, 0.05, 0.05, 0.05, 0.80]`，截断到 4 列 sum=0.20，重归一化 → `[0.25, 0.25, 0.25, 0.25]`
  - max_prob 从 0.80 暴跌到 0.25，ECE 该样本贡献从 |0.80-0|=0.80 降到 |0.25-0|=0.25
  - ECE 被系统性低估，产生"校准很好"的假象

  这是截断+重归一化方案的固有问题，代码 L414-415 确实如此实现。

- **反驳或修补**：攻击成立。修补方案：
  - 方案 A：不重归一化，保留原始前4列概率（不归一化），但 fit_temperature 可能要求概率归一化
  - 方案 B（推荐）：用 5 类模型评估 5 类 target，4 类模型评估 4 类 target，避免跨类数迁移（需重构实验设计）
  - 方案 C：保留重归一化但在结果中记录原始置信度供事后分析

---

### S5: build_model 的 resnet1d 路径有 dead import/dead variable，depth 被忽略

- **反方主张**：build_model 的 resnet1d 路径（L236-248）中 `ECGResNet1D` 导入未使用、`block_layers` 计算未使用、`depth` 被忽略，三个 Level 3 变体构造相同模型。

- **验证结果**：**成立**

- **详细分析**：L236-248 逐行验证：
  ```python
  if arch_override == "resnet1d":
      from src.models.baselines import ECGResNet1D  # L238: 导入但从未使用
      block_layers_map = {3: (1, 1, 1), 5: (2, 2, 1), 7: (2, 2, 2, 1)}
      block_layers = block_layers_map.get(depth, (2, 2, 2, 2))  # L241: 计算但从未使用
      model = ECGClassifier(
          in_channels=12, d_model=width or d_model, n_layers=2,  # width 只影响 d_model
          num_classes=num_classes, dropout=dropout,
          backbone_type="resnet1d",  # 通过 ECGClassifier 构造，不用 ECGResNet1D
      )
      return model
  ```
  - `ECGResNet1D` 导入后未使用（dead import）
  - `block_layers` 计算后未使用（dead variable）
  - `depth` 完全被忽略——三个变体（depth=3/5/7）构造相同 backbone
  - `width` 只影响 `d_model`（head 维度），非 ResNet1D 的 width 概念
  - `ECGClassifier(backbone_type="resnet1d")` 内部调用 `build_backbone("resnet1d")`（baselines.py L234-236），用默认参数构造 `ECGResNet1D`，不接受 depth/width

- **反驳或修补**：攻击成立。修补方案：
  ```python
  if arch_override == "resnet1d":
      block_layers_map = {3: (1, 1, 1), 5: (2, 2, 1), 7: (2, 2, 2, 1)}
      block_layers = block_layers_map.get(depth or 5, (2, 2, 2, 2))
      # 直接构造 ECGResNet1D 并注入 ECGClassifier
      backbone = ECGResNet1D(in_channels=12, d_model=width or d_model,
                             block_layers=block_layers, dropout=dropout)
      model = ECGClassifier(in_channels=12, d_model=width or d_model, n_layers=2,
                            num_classes=num_classes, dropout=dropout,
                            backbone_type="resnet1d")
      model.backbone = backbone  # 替换为自定义 depth 的 backbone
      return model
  ```

---

### S6: cal 集截断丢弃样本后 TS 温度 T 在子集拟合

- **反方主张**：截断后 cal 集是子集，T 在子集拟合不反映完整 cal 集校准需求。

- **验证结果**：**成立**

- **详细分析**：L418-419：
  ```python
  one_hot_cal = np.eye(num_classes)[cal_labels]
  T = fit_temperature(cal_probs, one_hot_cal)
  ```
  对于 5→4 方向，cal 集 HYP 样本（label=4）在 L407-409 被截断丢弃，T 在剩余 4 类子集拟合。若 HYP 类有独特置信度分布，T 会偏倚。

  与 ID 评估（train_single L327-328 用完整 cal 集拟合 T）的 T 值不可比。

- **反驳或修补**：攻击成立。修补方案：
  - 方案 A：在完整 cal 集上拟合 T（不截断 cal），只截断 ood——但 cal_probs 是 5 维，ood_probs 截断到 4 维，T 拟合维度不匹配
  - 方案 B（推荐）：报告截断前后 T 值差异，并在论文中说明"迁移 T 在子空间 cal 上拟合"

---

### S7: levels 列表有两个 Level 1

- **反方主张**：L169-179 levels 列表第一项和第二项都标记 level=1，语义混乱。

- **验证结果**：**成立**

- **详细分析**：L169-179：
  ```python
  levels = [
      (1, {"n_filters": 48, "use_checkpoint": False}, "原始配置..."),      # 第一项 level=1
      (1, {"n_filters": 32, "use_checkpoint": False}, "Level 1: ..."),     # 第二项 level=1
      (2, {"n_filters": 32, "use_checkpoint": True}, "Level 2: ..."),
      ...
  ]
  ```
  两个 level=1 条目。第一项应为 level=0（原始配置，未降级）。若原始配置成功，`oom_log["level"]=1`，误报为"Level 1 备选触发"。

- **反驳或修补**：攻击成立。修补：第一项改为 `(0, ..., "原始配置")`。

---

### M1: report_oom_level 条件逻辑错误

- **反方主张**：L183 条件 `level > 0 or params["n_filters"] != 48` 在第一项（level=1, n_filters=48）为 True，不 OOM 也打印"OOM 备选触发"。

- **验证结果**：**成立**

- **详细分析**：L183：
  ```python
  report_oom_level(level, desc) if level > 0 or params["n_filters"] != 48 else None
  ```
  第一项 level=1：`level > 0` 为 True → 打印 `[OOM 备选] Level 1 触发: 原始配置`，误导。

- **反驳或修补**：攻击成立。修补：配合 S7，第一项 level=0，条件改为 `if level > 0`。

---

### M2: 截断警告不够详细

- **反方主张**：L403-406 警告未记录丢弃比例，未在 result dict 中标注截断发生。

- **验证结果**：**成立**

- **详细分析**：L403-406 只 print 警告，result dict（L452-466）无 `truncated`/`n_dropped_cal`/`n_dropped_ood` 字段。CSV 消费者无法知道哪些迁移实验发生了截断。

- **反驳或修补**：攻击成立。修补：在 result 中增加字段，警告含丢弃比例。

---

### M3: config 参数是死参数

- **反方主张**：`try_train_with_oom_fallback` 的 `config` 参数在函数体内未使用。

- **验证结果**：**成立**

- **详细分析**：L154 签名有 `config: dict`，main() 传入 `{}`（L614），函数体 L168-202 未引用 `config`。

- **反驳或修补**：攻击成立。修补：删除 config 参数，或用 config 覆盖 levels 初始配置。

---

### M4: 截断后 bootstrap CI 可能低估方差

- **反方主张**：截断丢弃样本后 bootstrap 次数不变，CI 宽度可能偏窄。

- **验证结果**：**成立（轻微）**

- **详细分析**：L440-444 `benefit_inference` 用 `n_bootstrap=min(args.bootstrap, 2000)`，截断后样本数减少但 n_bootstrap 不变。理论上 bootstrap CI 未能反映样本数减少的额外不确定性。实际影响较小（bootstrap 本身是近似方法，CI 宽度主要取决于样本数而非 bootstrap 次数，只要 bootstrap 次数足够）。

- **反驳或修补**：攻击成立但影响轻微。修补：在 CI 报告中标注有效样本数。

---

## 对反方攻击的修正意见

作为独立审查者，我对反方攻击提出以下**修正**（非反驳——攻击核心均成立，但部分细节有偏差）：

### 修正 1：F2 影响范围 4→2 方向

反方称"6个迁移方向中4个受影响：ptbxl→cpsc, chapman→cpsc, cpsc→ptbxl, cpsc→chapman"。

**实际只有 2 个方向受 F2 影响**：ptbxl→cpsc, chapman→cpsc（5类源→4类目标）。

cpsc→ptbxl 和 cpsc→chapman 方向中，target 用 `subspace=SUBSPACE_CPSC` 构建（run_e5_inception_lite.py L383），label_map 用 SUBSPACE_CPSC 编码（train.py L351/L440），与 source cpsc 模型的训练编码（SUBSPACE_CPSC）**一致**，无语义错位。

**但这不减弱 F2 的致命性**：2 个方向的迁移评估结果完全无意义，仍需 P0 级返工。

### 修正 2：S2 机制描述

反方称"target 标签4的样本被 `ood_labels >= num_classes` 丢弃"。

**实际机制**：4→5 方向 target 用 `subspace=SUBSPACE_CPSC` 构建，HYP 样本在 `build_dataset` → `filter_subspace` 阶段就被剔除（train.py L342-351/L431-441），不会进入截断逻辑。截断逻辑的 `ood_labels >= num_classes` 检查不会发现 HYP 样本。

**效果相同**（HYP 不评估），但机制描述不准确。这不影响 S2 的成立。

---

## 结论

### 攻击成立情况汇总

| 编号 | 严重程度 | 验证结果 | 备注 |
|------|---------|---------|------|
| F1 | 致命 | **成立** | Level 3 死代码，三层断链确认 |
| F2 | 致命 | **成立（范围修正 4→2 方向）** | **最危险**：隐式静默错误，2 方向迁移结果无意义 |
| F3 | 致命 | **成立** | 命令行参数静默失效 |
| S1 | 严重 | **成立** | NaN 风险 |
| S2 | 严重 | **成立（机制修正）** | filter_subspace 而非截断丢弃 HYP |
| S3 | 严重 | **成立** | 语义偷换 |
| S4 | 严重 | **成立** | 概率扭曲 |
| S5 | 严重 | **成立** | dead import/variable, depth 忽略 |
| S6 | 严重 | **成立** | T 在子集拟合 |
| S7 | 严重 | **成立** | 两个 Level 1 |
| M1 | 轻微 | **成立** | 误导日志 |
| M2 | 轻微 | **成立** | 警告不充分 |
| M3 | 轻微 | **成立** | 死参数 |
| M4 | 轻微 | **成立** | CI 偏窄（影响轻微） |

### 需要回炉重修的攻击

**全部 3 个致命攻击需 P0 级返工**：

1. **F2（最高优先级）**：标签语义错位是**隐式静默错误**——实验运行完成、产出 CSV、无任何报错，但 ptbxl→cpsc 和 chapman→cpsc 两个方向的 MI/CD 预测全部算错，accuracy 系统性偏低，ECE/Brier 失真。这比 P0-7 修复前的 IndexError **更危险**：IndexError 是显性失败会停止实验，标签错位是隐性失败会产出无意义结果且难以察觉。**P0-7 用更严重的错误替换了崩溃。**

   **推荐修补**：统一 `SUBSPACE_CPSC = ("NORM", "MI", "STTC", "CD")`（与 `SUPERCLASSES[:4]` 一致），消除根因。

2. **F1（次高优先级）**：Level 3 ResNet1D 备选仍是死代码，P0-6 修复的核心承诺（激活4级备选链）未兑现。需修改 `train_single` 签名和 `_train_adapter` 闭包传递 arch/depth/width，并配合 S5 修补 `build_model` 的 resnet1d 路径。

3. **F3（第三优先级）**：命令行参数静默失效，需用传入的 n_filters/use_checkpoint 构造 levels 初始配置。

### 可以接受的攻击

**无**。所有 14 个攻击均成立，其中 3 个致命攻击需返工，7 个严重攻击需在返工时一并修复，4 个轻微攻击可批量修复。

### 对正方修复的最终评价

- **P0-6 评价**：**部分失败**。修复了"完全不调用 try_train_with_oom_fallback"的问题，但 Level 3 仍是死代码（F1），命令行参数失效（F3），4级备选链实际只有2级。
- **P0-7 评价**：**用更严重的错误替换了崩溃**。修复了 IndexError（显性崩溃），但引入了标签语义错位（F2，隐性静默错误）——2 个迁移方向的结果完全无意义，且无任何报错提示。同时引入 NaN 风险（S1）、概率扭曲（S4）、T 偏倚（S6）等多个新问题。

**建议**：P0 级返工，优先修复 F2（统一标签编码顺序），其次 F1+S5（激活 Level 3 真正的 ResNet1D 变体），再次 F3（命令行参数生效），并一并修复 S1/S2/S3/S4/S6/S7 + M1-M4。

---

> **反反方声明**：作为独立审查者，我逐行验证了 14 个攻击点，确认全部成立（含 2 个范围/机制修正）。反方攻击整体**成立且高质量**——3 个致命攻击均经代码实证，F2 标签语义错位尤为致命。P0-6+P0-7 修复**不成立**，建议 P0 级返工。
