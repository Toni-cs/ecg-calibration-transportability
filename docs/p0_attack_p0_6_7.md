# 反方攻击报告：P0-6+P0-7 OOM备选链激活 + 迁移IndexError修复

> **反方挑刺代理交付**。本报告对 `scripts/run_e5_inception_lite.py` 中 P0-6（OOM备选链死代码激活）和 P0-7（5→4类迁移IndexError截断修复）两个修复进行7维度全方位攻击审查。
> **审查范围**：run_e5_inception_lite.py (716行) + inceptiontime_lite.py (214行) + train.py build_*_datasets + mapping.py 标签编码
> **审查日期**：2026-09-09
> **审查方法**：逐行代码审查 + 7维度攻击（反例构造/逻辑断链/隐含假设/边界失效/自相矛盾/量级错误/语义偏移）

---

## 攻击摘要

| 严重程度 | 数量 | 攻击编号 |
|---------|------|---------|
| **致命(F)** | 3 | F1, F2, F3 |
| **严重(S)** | 7 | S1-S7 |
| **轻微(M)** | 4 | M1-M4 |
| **合计** | 14 | - |

**总体判断**：P0-6 修复**未真正激活完整的4级OOM备选链**——Level 3 的 ResNet1D 变体因 `_train_adapter` 闭包忽略 `arch/depth/width` 参数而仍是死代码，且 `train_single` 根本不接受 `arch_override` 参数。P0-7 修复**引入了更严重的标签语义错位**——SUPERCLASSES 与 SUBSPACE_CPSC 的标签编码顺序不一致（标签1和3对调），截断后迁移评估的 accuracy/ECE 数字失去物理意义。此外 `try_train_with_oom_fallback` 的 `n_filters/use_checkpoint` 形参被完全忽略，导致命令行 `--n-filters/--use-checkpoint` 静默失效。建议 P0 级返工。

---

## 致命攻击(F)

### F1: Level 3 ResNet1D 备选仍是死代码——_train_adapter 闭包忽略 arch/depth/width，train_single 不接受 arch_override

- **攻击维度**：反例构造 + 逻辑断链

- **攻击点**：P0-6 声称"在 main() 中用 try_train_with_oom_fallback() 替代直接 train_single() 调用"以激活4级备选链。但备选链 Level 3 的三个 ResNet1D 变体（depth=3/5/7, width=32/64/128）**无法被激活**，因为：

  1. `try_train_with_oom_fallback` 的 levels 列表（L169-179）中 Level 3 的 params 包含 `arch/depth/width`：
     ```python
     (3, {"n_filters": 32, "use_checkpoint": True, "arch": "resnet1d", "depth": 3, "width": 32}, ...)
     ```
  2. 但 `_train_adapter` 闭包（L607-612）只提取 `n_filters` 和 `use_checkpoint`，**完全忽略 arch/depth/width**：
     ```python
     def _train_adapter(params, dev, _ds=dataset, _seed=seed):
         return train_single(
             _ds, _seed, args, dev,
             n_filters=params.get("n_filters", 48),
             use_checkpoint=params.get("use_checkpoint", False),
         )  # arch/depth/width 去哪了？
     ```
  3. 即使 _train_adapter 想传递 arch，`train_single` 函数签名（L268-275）**根本没有 arch_override/depth/width 参数**：
     ```python
     def train_single(dataset, seed, args, device, n_filters=48, use_checkpoint=False):
     ```
  4. `train_single` 内部调用 `build_model`（L299-302）也不传 arch_override：
     ```python
     model = build_model(num_classes=num_classes, n_filters=n_filters,
                         use_checkpoint=use_checkpoint, d_model=args.d_model, dropout=0.1)
     ```

- **反例**：假设 RTX 5060 8GB 上 n_filters=48 OOM，n_filters=32+checkpoint 也 OOM。`try_train_with_oom_fallback` 进入 Level 3 第一个变体（arch=resnet1d, depth=3, width=32），调用 `_train_adapter(params, dev)`。但 _train_adapter 忽略 arch=resnet1d，仍然调用 `train_single(..., n_filters=32, use_checkpoint=True)`——**用 InceptionTime-Lite(n_filters=32, checkpoint) 再次训练**，与 Level 2 完全相同，必然再次 OOM。三个 Level 3 变体全部如此，最终退到 Level 4 降级报告。

- **影响**：
  1. 声称的"4级OOM备选链"实际只有2级（Level 1: n_filters=32; Level 2: +checkpoint），Level 3 是死代码
  2. 文档（L12-16）和论文材料中"Level 3: ResNet1D 不同超参变体"的承诺无法兑现
  3. 若 Level 2 仍 OOM，会直接跳到 Level 4 降级（"2架构家族+BiMamba toy"），跳过了本应尝试的 ResNet1D 变体
  4. 这正是 P0-6 声称要修复的"死代码"问题——修复后 Level 3 仍是死代码，只是换了一层包装

- **严重程度**：致命——P0-6 修复的核心承诺（激活4级备选链）未兑现

- **建议修补**：
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

---

### F2: 标签语义错位——SUPERCLASSES 与 SUBSPACE_CPSC 编码顺序不一致，标签1和3对调，截断后迁移评估失去物理意义

- **攻击维度**：隐含假设 + 语义偏移 + 反例构造

- **攻击点**：P0-7 修复了 5→4 类迁移的 IndexError，但**完全没有处理标签语义对齐**。源数据集和目标数据集的标签编码顺序不一致：

  1. `SUPERCLASSES = ("NORM", "MI", "STTC", "CD", "HYP")`（mapping.py L43）
     - ptbxl/chapman 5类编码：NORM=0, **MI=1**, STTC=2, **CD=3**, HYP=4
  2. `SUBSPACE_CPSC = ("NORM", "CD", "STTC", "MI")`（mapping.py L51）
     - cpsc 4类编码：NORM=0, **CD=1**, STTC=2, **MI=3**

  **标签 1 和 3 的语义在两套编码中对调**：
  - ptbxl 标签 1 = MI，cpsc 标签 1 = CD
  - ptbxl 标签 3 = CD，cpsc 标签 3 = MI

  P0-7 截断逻辑（L401-415）只做 `cal_labels < num_classes` 的数值截断，**不做语义重映射**。截断后 source 的标签 0-3（NORM/MI/STTC/CD）被直接与 target 的标签 0-3（NORM/CD/STTC/MI）比较，标签 1 和 3 的类别语义完全错位。

- **反例**：
  ```
  场景：ptbxl(5类) → cpsc(4类) 迁移
  source 模型用 SUPERCLASSES 编码训练：NORM=0, MI=1, STTC=2, CD=3, HYP=4
  target (cpsc) 用 SUBSPACE_CPSC 编码：NORM=0, CD=1, STTC=2, MI=3

  假设 target test 集有一个 CD 样本（cpsc 标签=1）
  source 模型对该样本输出概率 [0.1, 0.05, 0.05, 0.8, 0.0]
  （模型预测类别 3=CD，因为 source 编码中 CD=3，模型学会了"CD→输出维度3"）

  截断到 4 列：[0.1, 0.05, 0.05, 0.8] → 重归一化 → [0.1, 0.05, 0.05, 0.8]
  argmax = 3
  target label = 1（CD）
  correct = (3 == 1) = False ❌

  但模型实际上正确识别了 CD（输出维度3=CD），只是 target 的 CD 编码是 1！
  模型预测正确，却被算作错误。
  ```

  反过来：
  ```
  假设 target test 集有一个 MI 样本（cpsc 标签=3）
  source 模型对该样本输出概率 [0.1, 0.8, 0.05, 0.05, 0.0]
  （模型预测类别 1=MI，source 编码中 MI=1）

  截断：[0.1, 0.8, 0.05, 0.05] → argmax = 1
  target label = 3（MI）
  correct = (1 == 3) = False ❌

  模型正确识别 MI（输出维度1=MI），但 target 的 MI 编码是 3！
  又被算作错误。
  ```

  **所有 MI 和 CD 样本的预测都被系统性算错**，accuracy 严重低估。而 NORM(0) 和 STTC(2) 编码一致，这两类的预测不受影响。最终迁移 accuracy ≈ (NORM+STTC 正确数) / 总数，MI 和 CD 的贡献被系统性抹杀。

- **影响**：
  1. **6个迁移方向中4个受影响**：ptbxl→cpsc, chapman→cpsc, cpsc→ptbxl, cpsc→chapman（凡涉及 5类↔4类 跨编码的方向）
  2. **迁移 accuracy 系统性偏低**：MI 和 CD 类的预测全部算错，accuracy 可能低估 20-40%（取决于 MI+CD 在 target 中的占比）
  3. **ECE/Brier reliability 失真**：correct_mask 错误导致置信度-准确度关系完全扭曲
  4. **TS 校准温度 T 偏倚**：cal 集的 one_hot 用 source 编码构造，但评估用 target 编码，T 拟合在错误的标签对应上
  5. **论文结论失效**：基于错位标签的迁移评估结论不能支持任何关于"校准迁移异质性"的论断
  6. **P0-7 修复了崩溃但引入了更严重的静默错误**：IndexError 会停止实验（显性失败），标签错位会让实验跑完但结果无意义（隐性失败，更危险）

- **严重程度**：致命——迁移评估结果完全不可信

- **建议修补**：
  ```python
  # 在截断前做语义重映射：source 编码 → target 编码
  from src.data.mapping import SUPERCLASSES, SUBSPACE_CPSC
  if DATASET_NUM_CLASSES[source] != DATASET_NUM_CLASSES[target]:
      # 构造 source→target 的标签重映射
      source_classes = SUPERCLASSES[:DATASET_NUM_CLASSES[source]]  # 假设 source 用 SUPERCLASSES
      target_classes = SUBSPACE_CPSC if DATASET_NUM_CLASSES[target] == 4 else SUPERCLASSES
      # 但这需要确认 source 的实际编码...
      # 更根本的修复：统一所有数据集的标签编码顺序
  ```

  更根本的修复：**统一 SUPERCLASSES 和 SUBSPACE_CPSC 的顺序**，或在迁移评估时显式做标签语义对齐。

---

### F3: try_train_with_oom_fallback 的 n_filters/use_checkpoint 形参被完全忽略——命令行 --n-filters/--use-checkpoint 静默失效

- **攻击维度**：隐含假设 + 语义偏移

- **攻击点**：`try_train_with_oom_fallback` 函数签名（L154-160）声明接受 `n_filters` 和 `use_checkpoint` 参数：
  ```python
  def try_train_with_oom_fallback(
      train_fn, config: dict, device: torch.device,
      n_filters: int = 48, use_checkpoint: bool = False,
  ) -> Tuple[Any, dict]:
  ```

  main() 调用时传入了 `args.n_filters` 和 `args.use_checkpoint`（L613-616）：
  ```python
  model, info = try_train_with_oom_fallback(
      _train_adapter, {}, device,
      n_filters=args.n_filters, use_checkpoint=args.use_checkpoint,
  )
  ```

  但函数体内**完全没有使用 n_filters 和 use_checkpoint**！备选配置由硬编码的 `levels` 列表（L169-179）决定，第一项固定为 `{"n_filters": 48, "use_checkpoint": False}`。

- **反例**：用户运行 `python scripts/run_e5_inception_lite.py --n-filters 32 --use-checkpoint`，期望用 n_filters=32+checkpoint 训练。但 `try_train_with_oom_fallback` 忽略传入的 n_filters=32，硬编码从 `{"n_filters": 48, "use_checkpoint": False}` 开始尝试。**用户指定的参数被静默丢弃**，实际用 n_filters=48 训练。

- **影响**：
  1. 文档（L51-52）的用法说明 `python scripts/run_e5_inception_lite.py --n-filters 32 --use-checkpoint` **不生效**
  2. 用户无法通过命令行控制初始配置，只能依赖 OOM 触发后的自动降级
  3. 如果用户明确知道 8GB 显存不够 n_filters=48，想直接从 n_filters=32 开始——做不到，必须先 OOM 一次才降级
  4. `config: dict` 参数同样是死参数（传入 `{}`，函数体内未使用）

- **严重程度**：致命——用户可控性失效，文档与实现不符

- **建议修补**：
  ```python
  def try_train_with_oom_fallback(train_fn, config, device, n_filters=48, use_checkpoint=False):
      # 用传入的 n_filters/use_checkpoint 构造初始配置
      levels = [
          (0, {"n_filters": n_filters, "use_checkpoint": use_checkpoint}, "用户指定配置"),
          (1, {"n_filters": min(n_filters, 32), "use_checkpoint": use_checkpoint}, "Level 1: 减通道"),
          (2, {"n_filters": 32, "use_checkpoint": True}, "Level 2: + checkpoint"),
          ...
      ]
  ```

---

## 严重攻击(S)

### S1: 截断后概率重归一化可能产生 NaN/Inf——全零行未检查

- **攻击维度**：边界失效

- **攻击点**：L414-415 的重归一化：
  ```python
  cal_probs = cal_probs / cal_probs.sum(axis=1, keepdims=True)
  ood_probs = ood_probs / ood_probs.sum(axis=1, keepdims=True)
  ```

  隐含假设：截断后每行概率和 > 0。但如果某个样本的所有概率质量都在被截断的列上，截断后该行全零，sum=0，除法产生 NaN。

- **反例**：5-class source 模型对某个 cal 样本输出 `[0.0, 0.0, 0.0, 0.0, 1.0]`（100% 置信第5类 HYP）。截断到 4 列：`[0.0, 0.0, 0.0, 0.0]`，sum=0，重归一化 → `[nan, nan, nan, nan]`。NaN 传播到 `fit_temperature` → T=nan → `apply_temperature` → ood_probs_ts 全 NaN → `compute_all_metrics` → ECE/Brier=nan。

- **影响**：
  1. 单个全零行可能污染整个 batch 的聚合指标（取决于 compute_all_metrics 是否处理 NaN）
  2. 如果 cal 集有 HYP 样本（label=4）且模型对其高置信（概率≈1.0），截断后该样本概率全零
  3. NaN 传播链：cal_probs → T → ood_probs_ts → ECE/Brier → delta_ece → CSV

- **严重程度**：严重——可能导致整个迁移实验结果为 NaN

- **建议修补**：
  ```python
  row_sums = cal_probs.sum(axis=1, keepdims=True)
  zero_mask = row_sums.squeeze() == 0
  if zero_mask.any():
      print(f"[WARN] {zero_mask.sum()} 个 cal 样本截断后概率全零，丢弃")
      cal_probs = cal_probs[~zero_mask]
      cal_labels = cal_labels[~zero_mask]
  else:
      cal_probs = cal_probs / row_sums
  ```

---

### S2: 4→5 方向丢弃 target 第5类合法样本——num_classes=min 的语义偏移

- **攻击维度**：语义偏移 + 边界失效

- **攻击点**：L382 `num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])`。对于 4-class source → 5-class target（如 cpsc→ptbxl），num_classes=4。target 有5类标签（0-4），标签4的样本被 `ood_labels >= num_classes` 丢弃。

  但 target 的第5类（HYP）是**真实存在的合法类别**，不是编码错误。丢弃这些样本意味着迁移评估只在 target 的前4类上做，**不反映 target 的完整分布**。

- **反例**：cpsc(4类) → ptbxl(5类) 迁移。ptbxl test 集有 HYP 样本（label=4），假设占20%。截断丢弃这20%样本，剩余80%样本计算迁移指标。论文报告"cpsc→ptbxl 迁移 acc=X%"，实际是"cpsc→ptbxl 前4类 acc=X%"，**HYP 类的迁移表现完全未知**。

- **影响**：
  1. 4→5 方向的迁移指标不反映完整 target 分布
  2. 如果 HYP 类的迁移表现特别差（或特别好），截断后的指标会系统性偏倚
  3. 6个迁移方向中2个受影响（cpsc→ptbxl, cpsc→chapman）
  4. 论文若报告"6方向迁移评估"，实际只有4个方向是完整的，2个是部分评估

- **严重程度**：严重——迁移评估不完整

- **建议修补**：4→5 方向不应截断 target 标签，而应将 source 模型的4维输出扩展到5维（如补零到5维，或训练时就用5类）。或明确报告"4→5方向仅在target前4类上评估"。

---

### S3: 截断后迁移评估语义被偷换——"target上的表现"变成"target子集上的表现"

- **攻击维度**：语义偏移

- **攻击点**：原始迁移评估语义：source模型 → target test，评估模型在 target 上的表现。截断后：source模型 → target test 的**子集**（丢弃 label >= num_classes 的样本），评估模型在 target 子集上的表现。

  这两者**不是同一回事**。截断后的结果不能代表"模型在 target 上的迁移表现"，只能代表"模型在 target 前 num_classes 类上的表现"。

- **反例**：论文报告"ptbxl→cpsc 迁移 ECE=0.15"，但实际是"ptbxl→cpsc 前4类 ECE=0.15"。如果完整5类评估（含 HYP 类的 cal 样本）的 ECE=0.22，则截断后的 0.15 **系统性低估**了迁移 ECE。

- **影响**：
  1. 所有涉及截断的迁移方向，报告的指标语义与论文声称的不符
  2. 与其他实验（如 ResNet1D、BiMamba 的迁移评估）若未做截断，则**不可比**
  3. 元信息头注释（L489-500）未标注截断发生，CSV 消费者无法知道指标语义被偷换

- **严重程度**：严重——论文结论的可解释性受损

- **建议修补**：在 CSV 结果中增加 `n_dropped_cal`, `n_dropped_ood`, `truncated` 字段，并在元信息头注释中标注截断发生。

---

### S4: 截断后概率分布扭曲——第5类高置信度样本截断后置信度剧变，ECE/Brier失真

- **攻击维度**：量级错误 + 边界失效

- **攻击点**：5-class source → 4-class target 时，source 模型输出5维概率。截断第5列后重归一化，如果原始第5列概率质量显著，剩余4列概率会显著增大，**置信度剧变**。

- **反例**：
  ```
  source 模型对某 OOD 样本输出 [0.05, 0.05, 0.05, 0.05, 0.80]（80% 置信第5类）
  截断到 4 列：[0.05, 0.05, 0.05, 0.05]，sum=0.20
  重归一化：[0.25, 0.25, 0.25, 0.25]
  max_prob: 0.80 → 0.25（置信度从80%暴跌到25%）
  
  ECE 计算：该样本落入 [0.2, 0.3] bin，bin 内准确度可能=0（随机猜）
  原始（不截断）：该样本落入 [0.8, 0.9] bin，bin 内准确度=0（第5类被截断，预测必错）
  截断后 ECE 在 [0.2, 0.3] bin 的贡献 |0.25 - 0| = 0.25
  原始 ECE 在 [0.8, 0.9] bin 的贡献 |0.80 - 0| = 0.80
  截断后 ECE 该样本贡献从 0.80 降到 0.25——ECE 被系统性低估
  ```

- **影响**：
  1. 模型对第5类高置信度的样本，截断后置信度剧降，ECE 失真
  2. Brier reliability 同理失真（reliability 项依赖置信度-准确度对）
  3. TS 校准温度 T 在扭曲的 cal 概率上拟合，T 值偏倚
  4. 如果模型对大量 OOD 样本预测第5类（合理，因为 OOD 样本可能不属于前4类），截断后所有这些样本的置信度被压缩到均匀分布附近，ECE 看起来"很好"但实际是假象

- **严重程度**：严重——ECE/Brier 指标失真，可能产生"校准很好"的假象

- **建议修补**：不要重归一化，而是保留原始概率（前4列不归一化），或在截断时记录原始置信度供分析。或更根本地，用5类模型评估5类target，4类模型评估4类target，避免跨类数迁移。

---

### S5: build_model 的 resnet1d 路径有 dead import/dead variable，depth 被忽略

- **攻击维度**：逻辑断链 + 自相矛盾

- **攻击点**：`build_model` 的 resnet1d 路径（L236-248）：
  ```python
  if arch_override == "resnet1d":
      from src.models.baselines import ECGResNet1D  # 导入但从未使用
      block_layers_map = {3: (1, 1, 1), 5: (2, 2, 1), 7: (2, 2, 2, 1)}
      block_layers = block_layers_map.get(depth, (2, 2, 2, 2))  # 计算但从未使用
      model = ECGClassifier(
          in_channels=12, d_model=width or d_model, n_layers=2,
          num_classes=num_classes, dropout=dropout,
          backbone_type="resnet1d",
      )
      return model
  ```

  1. `ECGResNet1D` 导入了但**从未使用**（dead import）
  2. `block_layers` 计算了但**从未使用**（dead variable）
  3. `depth` 参数完全被忽略——三个 Level 3 变体（depth=3/5/7）构造的是**相同的模型**
  4. `width` 只影响 `d_model`，不是 ResNet1D 的 width 概念
  5. 没有用 depth 构造不同的 ResNet1D 结构

- **反例**：即使 F1 修复后 _train_adapter 传递了 arch=resnet1d, depth=3/5/7，build_model 对三个变体构造的模型**完全相同**（除了 d_model=32/64/128 不同，但这改变的是 head 维度不是 backbone 深度）。Level 3 的三个"不同超参变体"实际是三个"相同 backbone + 不同 head 维度"的模型，不是真正的 depth 变体。

- **影响**：
  1. Level 3 的三个变体不是真正的 ResNet1D depth 变体，无法提供不同的容量-深度权衡
  2. 即使激活 Level 3，三个变体可能全部 OOM 或全部成功（因为 backbone 相同），无法渐进降级
  3. dead import/dead variable 是代码质量问题

- **严重程度**：严重——Level 3 即使激活也无法提供真正的备选

- **建议修补**：用 depth 构造真正的 ResNet1D 变体（不同 block 数），或删除 Level 3 承认只支持2级备选。

---

### S6: cal 集截断丢弃样本后 TS 温度 T 在子集拟合——不反映完整 cal 集的校准需求

- **攻击维度**：隐含假设 + 量级错误

- **攻击点**：TS 校准在 cal 集拟合温度 T（L418-419）：
  ```python
  one_hot_cal = np.eye(num_classes)[cal_labels]
  T = fit_temperature(cal_probs, one_hot_cal)
  ```

  截断后 cal 集是子集（丢弃了 label >= num_classes 的样本）。T 在子集上拟合，**不反映完整 cal 集的校准需求**。如果被丢弃的类（如 HYP）有独特的置信度分布（如模型对 HYP 过度自信），T 会偏倚。

- **反例**：5-class source 的 cal 集有 20% HYP 样本，模型对 HYP 过度自信（置信度0.9，准确度0.6）。完整 cal 集拟合的 T=1.5（需要降温）。截断丢弃 HYP 后，剩余4类的置信度-准确度匹配较好，T=1.05。用 T=1.05 应用到 target test，校准不足。

- **影响**：
  1. T 偏倚导致 TS 校准效果失真
  2. delta_ece（TS 改善）可能被高估或低估
  3. Brier reliability improvement 失真
  4. 与 ID 评估（train_single 中用完整 cal 集拟合 T）的 T 值不可比

- **严重程度**：严重——TS 校准结果失真

- **建议修补**：在完整 cal 集上拟合 T（不截断 cal），只截断 ood。或报告截断前后的 T 值差异供分析。

---

### S7: levels 列表有两个 Level 1——语义混乱

- **攻击维度**：自相矛盾

- **攻击点**：L169-179 的 levels 列表：
  ```python
  levels = [
      (1, {"n_filters": 48, "use_checkpoint": False}, "原始配置（n_filters=48, no checkpoint）"),
      (1, {"n_filters": 32, "use_checkpoint": False}, "Level 1: n_filters 48→32（参数量 ~136K）"),
      (2, {"n_filters": 32, "use_checkpoint": True}, "Level 2: + gradient checkpointing"),
      ...
  ]
  ```

  第一项标记为 `level=1` 但描述是"原始配置"，第二项也标记为 `level=1` 但描述是"Level 1: n_filters 48→32"。**Level 1 有两个条目**，语义混乱。

  实际上第一项应该是 Level 0（原始配置，不触发备选），第二项才是 Level 1（第一次降级）。

- **影响**：
  1. oom_log["level"] 记录的 level 值语义不清——level=1 可能是"原始配置成功"也可能是"Level 1 降级成功"
  2. CSV 元信息头注释 `# OOM 备选触发: Level {oom_summary.get('max_level', 0)}` 可能误报
  3. 如果原始配置成功（第一项），oom_log["level"]=1，看起来像触发了 Level 1 备选，实际没有

- **严重程度**：严重——日志和元信息误导

- **建议修补**：第一项改为 `(0, ..., "原始配置")`，level=0 表示未降级。

---

## 轻微攻击(M)

### M1: report_oom_level 条件逻辑错误——不 OOM 也打印"OOM 备选触发"

- **攻击维度**：自相矛盾

- **攻击点**：L183：
  ```python
  report_oom_level(level, desc) if level > 0 or params["n_filters"] != 48 else None
  ```

  第一项 level=1, n_filters=48：`level > 0` 为 True，调用 `report_oom_level(1, "原始配置")`。这意味着**即使不 OOM、原始配置直接成功**，也会打印 `[OOM 备选] Level 1 触发: 原始配置`，这是误导性日志。

- **影响**：日志噪声，用户看到"OOM 备选触发"以为发生了 OOM 降级，实际没有。

- **建议修补**：第一项 level=0，条件改为 `if level > 0`。

---

### M2: 截断警告不够详细——未记录丢弃比例、未在结果中标注截断发生

- **攻击维度**：隐含假设

- **攻击点**：L403-406 的警告：
  ```python
  if n_dropped_cal > 0 or n_dropped_ood > 0:
      print(f"[WARN] {source}→{target} seed={seed}: 丢弃 "
            f"{n_dropped_cal} 个 cal + {n_dropped_ood} 个 ood 样本 "
            f"(标签 >= num_classes={num_classes})")
  ```

  1. 未记录丢弃比例（丢弃数/总数），难以判断截断严重程度
  2. 未在 result dict 中标注截断发生（result 没有 `truncated`/`n_dropped_cal`/`n_dropped_ood` 字段）
  3. CSV 消费者无法知道哪些迁移实验发生了截断
  4. 未记录哪些类别被丢弃（如"HYP 类被丢弃"而非"标签>=4"）

- **影响**：截断发生时用户难以评估影响，CSV 后处理可能误将截断结果与完整结果同等对待。

- **建议修补**：在 result 中增加 `n_dropped_cal`, `n_dropped_ood`, `truncated` 字段，警告中包含丢弃比例。

---

### M3: config 参数是死参数

- **攻击维度**：隐含假设

- **攻击点**：`try_train_with_oom_fallback(train_fn, config, device, ...)` 的 `config` 参数在函数体内完全未使用。main() 传入 `config={}`。

- **影响**：API 误导，看起来可以传入配置但实际被忽略。

- **建议修补**：删除 config 参数，或实际使用它（如用 config 覆盖 levels 列表的初始配置）。

---

### M4: 截断后 bootstrap CI 可能低估方差——样本数减少但 bootstrap 次数不变

- **攻击维度**：量级错误

- **攻击点**：截断丢弃部分样本后，`benefit_inference` 的 bootstrap（L440-444）在减少的样本上做：
  ```python
  benefit = benefit_inference(
      max_probs_raw, max_probs_ts, correct_mask,
      metric=smooth_ece, n_bootstrap=min(args.bootstrap, 2000),
      rng=rng, clusters=tgt_clusters,
  )
  ```

  样本数减少（如从1000降到800），但 n_bootstrap 不变（2000）。bootstrap CI 的宽度可能偏窄（因为有效样本减少，但 bootstrap 次数不变，CI 未能反映额外的样本数不确定性）。

- **影响**：delta_ece_ci 可能偏窄，置信区间覆盖概率不足。

- **建议修补**：根据截断后样本数调整 n_bootstrap，或在 CI 报告中标注样本数减少。

---

## 7维度攻击总结

| 维度 | 攻击点 | 严重程度 |
|------|--------|---------|
| **反例构造** | F1（Level 3 死代码反例）、F2（标签错位反例）、F3（命令行参数失效反例） | 致命 |
| **逻辑断链** | F1（_train_adapter→train_single→build_model 三层断链）、S5（dead import/variable） | 致命/严重 |
| **隐含假设** | F2（假设标签编码一致）、F3（假设形参被使用）、S1（假设概率和>0）、S6（假设子集T代表完整集T）、M2（假设警告足够）、M3（假设config被使用） | 致命/严重/轻微 |
| **边界失效** | S1（全零行NaN）、S2（4→5丢弃合法样本）、S4（高置信度样本扭曲） | 严重 |
| **自相矛盾** | S7（两个Level 1）、M1（不OOM却报告OOM触发） | 严重/轻微 |
| **量级错误** | S4（置信度剧变）、S6（T偏倚）、M4（CI偏窄） | 严重/轻微 |
| **语义偏移** | F2（标签语义错位）、F3（形参语义偏移）、S2（num_classes语义偏移）、S3（迁移评估语义偷换） | 致命/严重 |

---

## 对正方修复的评价

### P0-6 评价：部分失败
- **承诺**：激活4级OOM备选链
- **兑现**：Level 1-2 激活（n_filters=32, +checkpoint），Level 3 仍是死代码（F1），Level 4 是降级报告
- **新问题**：F3（命令行参数失效）、S7（Level编号混乱）、M1（误导日志）
- **结论**：P0-6 修复了"完全不调用"的问题，但未真正激活完整的4级链，Level 3 的 ResNet1D 变体仍不可达

### P0-7 评价：修复了崩溃但引入更严重的静默错误
- **承诺**：修复 5→4 类迁移的 IndexError
- **兑现**：IndexError 不再发生（截断逻辑生效）
- **新问题**：F2（标签语义错位，比 IndexError 更危险——IndexError 是显性失败会停止，标签错位是隐性失败会产出无意义结果）、S1（NaN风险）、S2（4→5丢弃合法样本）、S3（语义偷换）、S4（概率扭曲）、S6（T偏倚）
- **结论**：P0-7 用"截断+重归一化"治标，但未治本。根本问题是跨类数迁移的标签语义对齐，截断只是掩盖了崩溃，标签错位仍然存在且更危险

### 根本问题
两个修复都停留在"让代码不崩溃"的层面，未触及根本问题：
1. P0-6 的根本问题：train_single 不支持架构切换，build_model 的 resnet1d 路径未完成
2. P0-7 的根本问题：跨类数迁移的标签语义对齐，SUPERCLASSES 与 SUBSPACE_CPSC 编码顺序不一致

**建议**：P0 级返工，优先修复 F2（标签语义错位），其次 F1（Level 3 死代码），再次 F3（命令行参数失效）。

---

## 附录：审查的代码文件

1. `scripts/run_e5_inception_lite.py` (716行)——主审查对象
2. `src/models/inceptiontime_lite.py` (214行)——模型架构
3. `scripts/train.py` L316-555——build_ptbxl/chapman/cpsc_datasets 标签编码
4. `src/data/mapping.py` L43-51——SUPERCLASSES/SUBSPACE_CPSC 定义

---

> **反方声明**：我尝试了全部7个攻击维度，找到14个有效攻击点（3致命+7严重+4轻微）。P0-6+P0-7 修复**不成立**——P0-6 未真正激活4级备选链（Level 3 仍是死代码），P0-7 引入了比 IndexError 更严重的标签语义错位。建议 P0 级返工。
