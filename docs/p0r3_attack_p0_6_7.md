# P0-6+7 R3反方攻击报告

## 攻击摘要
- 审查文件：scripts/run_e5_inception_lite.py
- 审查依据：docs/p0r2_final_verdict.md 第2.1节 P0-6+7 R3必修4项
- 攻击点数：9
- 致命：1 | 严重：2 | 中等：2 | 轻微：4

## 审查方法

逐行读取 scripts/run_e5_inception_lite.py（801行）全文，对照 R2 终审判定中 P0-6+7 的 4 项 R3 必修要求，从 7 个攻击维度（反例构造/逻辑断链/隐含假设/边界失效/自相矛盾/量级错误/语义偏移）逐一审查。同时读取 scripts/train.py 的三个 builder（build_ptbxl_datasets/build_chapman_datasets/build_cpsc_datasets）和 src/utils/calibration.py 的 benefit_inference 签名，验证 tgt_clusters 类型与下游接口契约。

---

## 攻击点详情

### Attack-1 [致命] R3修复2引入的early-return dict schema与normal result dict不一致，导致csv.DictWriter崩溃

- **位置**：L482-489（R3修复2）vs L526-545（normal result dict）vs L596-599（write_csv）
- **问题描述**：

  R3修复2在L482-489引入了两个early-return dict，其schema与normal result dict（L526-545）**完全不同**：

  | dict类型 | 位置 | 字段数 | 字段列表 |
  |---------|------|--------|---------|
  | normal result | L526-545 | 20 | source,target,seed,arch,num_classes,n_ood,ood_acc_raw,fitted_T,ood_ece_raw,ood_ece_ts,ood_brier_raw,ood_brier_ts,delta_ece,delta_ece_ci_low,delta_ece_ci_high,brier_reliability_improvement,n_dropped_cal,n_dropped_ood,truncated,subspace_filtered |
  | cal empty early-return | L484-485 | 6 | source,target,seed,arch,error,skipped |
  | ood empty early-return | L487-489 | 6 | source,target,seed,arch,error,skipped |
  | FileNotFound early-return | L426 | 5 | source,target,seed,error,skipped（**无arch**） |
  | exception handler | L750-753 | 5 | source,target,seed,arch,error（**无skipped**） |

  `write_csv` 在L596使用 `csv.DictWriter(f, fieldnames=list(transfer_results[0].keys()))`，**未设置 extrasaction='ignore'**，默认 `extrasaction='raise'`。

  **Python csv.DictWriter 文档明确**：当 rowdict 包含不在 fieldnames 中的键时，默认抛出 `ValueError: dict contains fields not in fieldnames`。已通过 `python -c` 实测确认。

- **反例/证据**：

  场景：6个迁移方向中，第一个 ptbxl→chapman seed=42 的 cal 集截断后为空（early-return，6字段），第二个 ptbxl→chapman seed=43 正常完成（normal result，20字段）。

  执行流程：
  1. L741: `result = eval_transfer_pair(...)` 返回 `{"source":"ptbxl","target":"chapman","seed":42,"arch":"inceptiontime_lite","error":"cal set empty after truncation","skipped":True}`（6字段）
  2. L746: `transfer_results.append(result)` → transfer_results[0] 有6个键
  3. L596: `fieldnames = list(transfer_results[0].keys())` = `['source','target','seed','arch','error','skipped']`
  4. 第二个迁移正常完成，返回20字段 dict
  5. L599: `writer.writerow(r)` → **ValueError: dict contains fields not in fieldnames: 'num_classes', 'n_ood', 'ood_acc_raw', ...**
  6. L599无 try-except 包裹 → **程序崩溃，CSV文件损坏（仅有header和第一行）**

  反向也崩溃：若第一个是normal result（20字段），后续early-return有 `error`/`skipped` 额外字段 → 同样 ValueError。

- **严重程度**：致命——任一迁移失败/跳过 + 任一迁移成功即触发崩溃，CSV完全无法写入。这在实际实验中极易发生（如某个数据集缺失、某个迁移数值异常）。
- **修复建议**：统一所有 transfer result dict 的 schema。方案A（推荐）：定义 `TRANSFER_RESULT_FIELDS` 常量列表，所有 early-return/error dict 用 `{k: None for k in TRANSFER_RESULT_FIELDS}` 填充缺失字段后 update。方案B：`csv.DictWriter(f, fieldnames=..., extrasaction='ignore')` + 固定 fieldnames 为全字段并集。

---

### Attack-2 [严重] transfer result的arch字段硬编码为ARCH_NAME，未使用source_info["arch"]，OOM Level 3时CSV arch列失真

- **位置**：L527（normal result）、L484/L488（early-return）、L752（exception handler）
- **问题描述**：

  R3修复4（L368-374）正确地将 `info["arch"]` 设为 `arch_display`（含 "resnet1d" 标识），使**训练CSV**的arch列准确反映OOM备选架构。

  但 `eval_transfer_pair` 中所有 result dict 的 `arch` 字段均**硬编码为 `ARCH_NAME`**（即 "inceptiontime_lite"），未从 `source_info` 获取源模型的真实arch：

  ```python
  # L527 (normal result)
  "arch": ARCH_NAME,  # 硬编码！应该是 source_info.get("arch", ARCH_NAME)

  # L484 (cal empty early-return)
  "arch": ARCH_NAME,  # 同样硬编码

  # L488 (ood empty early-return)
  "arch": ARCH_NAME,  # 同样硬编码
  ```

  `source_info` 在L408作为参数传入，且 `source_info["arch"]` 在L372已被正确设为 `arch_display`，但 `eval_transfer_pair` **从未读取该字段**。

- **反例/证据**：

  场景：OOM Level 3 触发，ptbxl seed=42 的源模型用 ResNet1D 训练（arch_override="resnet1d"）。

  - 训练CSV：`arch` 列 = "resnet1d"（正确，来自L372 `arch_display`）
  - 迁移CSV：`arch` 列 = "inceptiontime_lite"（**错误**，来自L527 硬编码 `ARCH_NAME`）

  下游分析者从迁移CSV看到 arch="inceptiontime_lite"，但实际源模型是 ResNet1D，导致架构-性能关联分析完全错误。R3修复4的目的（"避免CSV arch列失真"）在迁移CSV中**完全未达成**。

- **严重程度**：严重——CBM审稿要求实验结果可追溯，arch列失真直接导致架构消融结论无效。
- **修复建议**：L527/L484/L488/L752 的 `"arch": ARCH_NAME` 全部改为 `"arch": source_info.get("arch", ARCH_NAME)`。

---

### Attack-3 [严重] R3修复1的L451 tgt_clusters[ood_keep]是死代码——ood_keep在所有6个迁移方向上恒为全True

- **位置**：L451（R3修复1第一处）
- **问题描述**：

  R2终审判定将L451的 `tgt_clusters = tgt_clusters[ood_keep]` 标记为 **P0-致命**（"不修则 benefit_inference 的 cluster bootstrap 会 IndexError"）。但经逐方向分析，`ood_keep` 在所有6个迁移方向上**恒为全True**，L451是no-op（死代码）。

  推理链条：
  1. `ood_keep = ood_labels < num_classes`（L444）
  2. `ood_labels` 来自目标数据集的 test 集（L432: `ood_labels = tgt_eval["labels"]`）
  3. 目标数据集通过 `build_dataset(target, seed, subspace=subspace)` 构建（L423）
  4. `subspace = SUBSPACE_CPSC if num_classes == 4 else None`（L419）
  5. 当 `num_classes == 4`：目标数据集被过滤为4类，labels ∈ {0,1,2,3}，全部 < 4 ✓
  6. 当 `num_classes == 5`：subspace=None，目标数据集为5类，labels ∈ {0,1,2,3,4}，全部 < 5 ✓
  7. **结论**：`ood_labels < num_classes` 恒为全True，`ood_keep` 恒为全True

  逐方向验证：

  | 迁移方向 | source类数 | target类数 | num_classes | target构建方式 | ood_labels范围 | ood_keep |
  |---------|-----------|-----------|------------|--------------|--------------|---------|
  | ptbxl→chapman | 5 | 5 | 5 | chapman无subspace | 0-4 | 全True |
  | ptbxl→cpsc | 5 | 4 | 4 | cpsc(4类) | 0-3 | 全True |
  | chapman→ptbxl | 5 | 5 | 5 | ptbxl无subspace | 0-4 | 全True |
  | chapman→cpsc | 5 | 4 | 4 | cpsc(4类) | 0-3 | 全True |
  | cpsc→ptbxl | 4 | 5 | 4 | ptbxl+subspace(4类) | 0-3 | 全True |
  | cpsc→chapman | 4 | 5 | 4 | chapman+subspace(4类) | 0-3 | 全True |

- **反例/证据**：

  L451 `tgt_clusters = tgt_clusters[ood_keep]` 等价于 `tgt_clusters = tgt_clusters[全True布尔数组]` = `tgt_clusters`（no-op）。

  R2判决称"不修则 benefit_inference 的 cluster bootstrap 会 IndexError"——但这个IndexError**在L451处根本不可能发生**，因为ood_keep恒为全True，tgt_clusters长度永远不会因ood_keep而改变。

  **真正的P0-致命修复在L476**（`tgt_clusters = tgt_clusters[~ood_zero_rows]`），因为零行丢弃确实会改变ood_probs长度，需要同步截断tgt_clusters。L476是必要的、活跃的修复。

- **严重程度**：严重——R2判决的优先级判断有误：将死代码L451标为P0-致命并列为"第一优先修复"，而真正致命的L476被放在同一修复项中未区分。虽然L451+L476同时修复后结果正确，但L451本身是无效修复，给人虚假的安全感。
- **修复建议**：L451可保留作为防御性代码（防止builder未来变更），但应加注释说明"当前ood_keep恒为全True，此行为防御性no-op"。R3修复的真正价值在L476。

---

### Attack-4 [中等] early-return dict缺少n_dropped_cal/n_dropped_ood/truncated/subspace_filtered字段，跳过实验的截断统计不可追溯

- **位置**：L484-485（cal empty）、L487-489（ood empty）
- **问题描述**：

  R3修复3在normal result dict中增加了 `n_dropped_cal`/`n_dropped_ood`/`truncated`/`subspace_filtered` 四个字段（L540-544），用于追踪截断统计。

  但R3修复2的early-return dict（L484-485/L487-489）**未包含这四个字段**。当cal或ood集截断后为空时，实验被跳过，但跳过原因中的截断统计（丢弃了多少样本才导致空集）完全丢失。

  具体来说：
  - L484-485: `return {"source":..., "target":..., "seed":..., "arch":ARCH_NAME, "error":"cal set empty after truncation", "skipped":True}` — 无 `n_dropped_cal`/`n_dropped_ood`/`truncated`/`subspace_filtered`
  - L487-489: 同上

  在cal集为空的场景中，`n_dropped_cal` 可能很大（如全部样本的标签都 >= num_classes），这个信息对分析"为什么5→4迁移会失败"至关重要，但early-return丢弃了它。

- **反例/证据**：

  场景：ptbxl→cpsc seed=42，cal集有1000个样本，其中全部1000个的标签=4（HYP类）。
  - L437: `n_dropped_cal = 1000`
  - L445-446: cal_labels 和 cal_probs 变为空数组
  - L482: `len(cal_probs) == 0` → True
  - L484: 返回 `{"error": "cal set empty after truncation", ...}` — **n_dropped_cal=1000 的信息丢失**

  下游分析者只能看到 "cal set empty after truncation"，无法知道丢弃了多少样本、是否所有样本都被丢弃。

- **严重程度**：中等——不影响运行时正确性，但影响CBM要求的实验可追溯性。
- **修复建议**：early-return dict 应包含 `n_dropped_cal`/`n_dropped_ood`/`truncated`/`subspace_filtered` 字段（与Attack-1的schema统一修复合并）。

---

### Attack-5 [中等] n_dropped_cal/n_dropped_ood累计逻辑虽对称，但truncated字段无法区分"标签截断"与"零行丢弃"两种丢弃原因

- **位置**：L437/L460（n_dropped_cal累计）、L438/L472（n_dropped_ood累计）、L543（truncated）
- **问题描述**：

  R3修复5将零行丢弃数累计到 `n_dropped_cal`/`n_dropped_ood`：
  - L437: `n_dropped_cal = int((cal_labels >= num_classes).sum())` — 标签截断计数
  - L460: `n_dropped_cal += int(cal_zero_rows.sum())` — 零行丢弃累计
  - L543: `"truncated": bool((n_dropped_cal + n_dropped_ood) > 0)` — 是否有丢弃

  cal侧和ood侧的累计逻辑**确实对称**（R3修复5本身正确）。但 `n_dropped_cal` 是两种丢弃原因的混合总数，CSV中无法区分：
  - 有多少样本因 `label >= num_classes` 被丢弃（子空间过滤）
  - 有多少样本因截断后全零被丢弃（概率质量集中在被截断类别上）

  这两种丢弃的物理含义完全不同：前者是标签语义不匹配，后者是模型预测偏移。混在同一字段中，下游分析者无法判断迁移失败的根因。

- **反例/证据**：

  场景：n_dropped_cal = 100，其中50个因标签>=4被丢弃，50个因全零行被丢弃。CSV中只有 `n_dropped_cal=100`，无法区分。

- **严重程度**：中等——不影响正确性，但影响根因分析能力。
- **修复建议**：增加 `n_dropped_cal_label`/`n_dropped_cal_zero` 字段分别记录两种丢弃原因（可选改进）。

---

### Attack-6 [轻微] L426 FileNotFound early-return dict缺少arch字段，与其他early-return dict不一致

- **位置**：L426
- **问题描述**：

  L426的FileNotFound early-return：
  ```python
  return {"source": source, "target": target, "seed": seed, "error": str(e), "skipped": True}
  ```
  缺少 `"arch"` 字段，而L484/L488的early-return都有 `"arch": ARCH_NAME`。

  这是5种transfer result schema中的第4种（5字段无arch），进一步加剧了Attack-1的schema不一致问题。

- **反例/证据**：若transfer_results中同时存在L426返回的dict（无arch）和normal result dict（有arch），即使修复了Attack-1（统一schema），L426的dict仍需补arch字段。
- **严重程度**：轻微——与Attack-1合并修复。
- **修复建议**：L426添加 `"arch": source_info.get("arch", ARCH_NAME)`。

---

### Attack-7 [轻微] L750-753 exception handler dict缺少skipped字段，与其他error dict不一致

- **位置**：L750-753
- **问题描述**：

  L750-753的exception handler：
  ```python
  transfer_results.append({
      "source": source, "target": target, "seed": seed,
      "arch": ARCH_NAME, "error": str(e),
  })
  ```
  缺少 `"skipped"` 字段，而L426/L484/L488的error dict都有 `"skipped": True`。

  这是5种transfer result schema中的第5种（5字段无skipped）。

- **反例/证据**：下游分析者用 `skipped` 字段过滤跳过的实验时，L750-753的异常结果不会被过滤（因为缺少skipped字段，pandas读取后为NaN，`df[df.skipped]` 不包含它）。
- **严重程度**：轻微——与Attack-1合并修复。
- **修复建议**：L750-753添加 `"skipped": True`，并将 `"arch": ARCH_NAME` 改为 `"arch": source_info.get("arch", ARCH_NAME)`（与Attack-2合并）。

---

### Attack-8 [轻微] subspace_filtered字段语义模糊——不区分"source cal被标签截断"与"target被subspace过滤"

- **位置**：L544
- **问题描述**：

  `"subspace_filtered": bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target]))`

  当source和target的类数不同时，`subspace_filtered=True`。但实际触发的过滤机制取决于方向：

  | 方向 | source类数 | target类数 | subspace_filtered | 实际过滤机制 |
  |------|-----------|-----------|-------------------|------------|
  | ptbxl→cpsc | 5 | 4 | True | **source cal被标签截断**（label 4被丢弃） |
  | cpsc→ptbxl | 4 | 5 | True | **target被subspace过滤**（ptbxl降为4类） |

  同样 `subspace_filtered=True`，但5→4方向是source侧截断，4→5方向是target侧过滤。字段名"subspace_filtered"暗示target被subspace过滤，但对5→4方向不准确（target cpsc本身就是4类，无需subspace过滤）。

- **反例/证据**：ptbxl→cpsc 方向，subspace_filtered=True，但target cpsc的构建未传subspace参数（L220: `if dataset == "cpsc": ds, clusters = builder(...)` 无subspace），实际过滤发生在source cal侧。
- **严重程度**：轻微——`truncated`/`n_dropped_cal`/`n_dropped_ood` 字段提供了实际过滤信息，`subspace_filtered` 仅是方向级标志。
- **修复建议**：重命名为 `cross_class_transfer` 或增加文档注释说明语义（可选）。

---

### Attack-9 [轻微] train info dict的oom_log字段未从CSV序列化中过滤，写入CSV时变为dict的str repr

- **位置**：L588-590（write_csv中的train row过滤）、L764-768（serializable_train过滤）
- **问题描述**：

  `try_train_with_oom_fallback` 在L195返回 `{**extra, "oom_log": oom_log}`，其中 `oom_log` 是嵌套dict。`write_csv` 的过滤列表（L589/L767）为 `("model", "loaders", "cal_eval", "test_eval", "clusters_test")`，**未包含 "oom_log"**。

  因此 `oom_log` 被写入CSV，值为 `str(dict)`，如 `{'level': 0, 'actions': ['用户指定配置...'], 'final_config': {'n_filters': 48, 'use_checkpoint': False}}`。该字符串包含逗号和引号，虽然csv模块会自动加引号转义，但下游pandas读取后该列为字符串，需手动 `ast.literal_eval` 才能解析，影响分析便利性。

- **反例/证据**：训练CSV的 `oom_log` 列值为 `{'level': 1, 'actions': ['Level 1: n_filters 48→32...'], ...}`，pandas读取后为str类型，无法直接用 `df.oom_log.apply(lambda x: x['level'])` 提取level。
- **严重程度**：轻微——不影响正确性，仅影响分析便利性。
- **修复建议**：将 `oom_log` 展平为 `oom_level`（int）和 `oom_actions`（str）两个字段，或加入过滤列表（可选）。

---

## 7个攻击维度审查结论

| 维度 | 结论 |
|------|------|
| 1. 反例构造 | **Attack-1**：构造"第一个迁移cal空+第二个迁移正常"反例，触发csv.DictWriter ValueError崩溃 |
| 2. 逻辑断链 | **Attack-2**：R3修复4声称"避免CSV arch列失真"，但迁移CSV的arch仍硬编码，逻辑断链 |
| 3. 隐含假设 | **Attack-3**：R3修复1的L451隐含假设"ood_keep可能非全True"，但该假设在当前6个方向上不成立 |
| 4. 边界失效 | **Attack-1**：边界情况（cal/ood空集）的early-return dict与normal dict schema不兼容 |
| 5. 自相矛盾 | **Attack-2**：训练CSV的arch正确 vs 迁移CSV的arch错误，同一实验两个CSV矛盾 |
| 6. 量级错误 | 未发现量级错误（n_dropped累计逻辑正确，truncated布尔判断正确） |
| 7. 语义偏移 | **Attack-8**：subspace_filtered字段名暗示target过滤，但5→4方向实际是source过滤 |

---

## R3修复逐项评价

| R3修复项 | R2判定优先级 | 反方评价 | 说明 |
|---------|------------|---------|------|
| 修复1: tgt_clusters同步截断 | P0-致命 | **部分有效** | L476（零行同步）是真正必要的修复；L451（ood_keep同步）是死代码，no-op |
| 修复2: 空数组提前返回 | P0-严重 | **引入新致命bug** | early-return dict schema与normal dict不一致，导致csv.DictWriter崩溃（Attack-1） |
| 修复3: result dict新字段 | P0-严重 | **部分有效** | 字段类型正确（int/bool），但仅存在于normal dict，early-return dict缺失（Attack-4） |
| 修复4: info dict新字段 | P0-严重 | **部分有效** | 训练info dict正确，但迁移result dict的arch仍硬编码（Attack-2），修复目的未完全达成 |
| 修复5: n_dropped累计 | P0-中等 | **正确** | cal侧和ood侧累计逻辑对称，类型正确。但混合两种丢弃原因（Attack-5） |

---

## 总结

R3的5个修复中：
- **修复1**：L476有效但L451是死代码，R2优先级判断有误
- **修复2**：**引入了新的P0-致命bug**（CSV schema不一致导致崩溃），这是本轮最严重发现
- **修复3**：字段正确但覆盖不全（early-return dict缺失）
- **修复4**：训练侧正确但迁移侧未同步（arch硬编码）
- **修复5**：正确但语义可改进

**最关键发现**：R3修复2（空数组提前返回）本身引入了新的致命缺陷——early-return dict与normal result dict的schema不一致，在任一迁移失败+任一迁移成功的常见场景下，csv.DictWriter会抛出ValueError导致程序崩溃。这违背了R3修复2的目的（"防止静默nan传播"），将一个静默数值问题升级为硬崩溃。

**建议R4修复优先级**：
1. **[P0-致命]** 统一所有transfer result dict的schema（Attack-1），同时解决Attack-4/6/7
2. **[P0-严重]** 迁移result dict的arch字段改用source_info["arch"]（Attack-2）
3. **[P0-中等]** L451加注释标明为防御性no-op（Attack-3）
4. **[P0-轻微]** 其余可选改进
