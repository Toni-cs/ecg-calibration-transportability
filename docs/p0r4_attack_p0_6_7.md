# P0-6+7 R4反方攻击报告

## 审查范围
- 文件: scripts/run_e5_inception_lite.py（919行）
- 审查日期: 2026-09-09
- 审查代理: R4反方挑刺代理（GLM-5.2）
- R4修复内容: TRANSFER_RESULT_FIELDS常量（22字段）+ _make_transfer_result辅助函数 + extrasaction="ignore" + arch动态获取
- R3遗留问题: Attack-1（致命，CSV schema不一致导致DictWriter崩溃）+ Attack-2（严重，arch硬编码）+ Attack-4/6/7（中等/轻微，字段缺失）

## 审查方法

逐行读取R4修复后的scripts/run_e5_inception_lite.py全文，对照R3终审裁决（docs/p0r3_final_verdict.md）和R3反方攻击报告（docs/p0r3_attack_p0_6_7.md），从7个攻击维度（反例构造/逻辑断链/隐含假设/边界失效/自相矛盾/量级错误/语义偏移）逐一审查R4修复的4项改动：
1. TRANSFER_RESULT_FIELDS常量定义（L142-153）
2. _make_transfer_result辅助函数（L156-214）
3. 5处构造点统一调用（L510-514/L573-581/L585-593/L633-653/L867-871）
4. write_csv的DictWriter设置（L709-711）

---

## R3遗留攻击点修复验证

### R3-Attack-1 [致命] CSV schema不一致 → **已修复** ✅

R3的致命问题：early-return dict（6字段）与normal result dict（20字段）schema不一致，csv.DictWriter未设extrasaction='ignore'，混合时触发ValueError崩溃。

R4修复验证：
- TRANSFER_RESULT_FIELDS定义22字段（L142-153）
- _make_transfer_result返回恰好22个键（L191-214），与TRANSFER_RESULT_FIELDS完全一致
- 全部5处构造点均调用_make_transfer_result（grep验证：L510/L573/L585/L633/L867）
- write_csv使用TRANSFER_RESULT_FIELDS作为fieldnames + extrasaction="ignore"（L709-711）
- 无论transfer_results[0]是early-return还是normal result，fieldnames始终为22字段，不会因首个dict类型不同而变化

**结论**：R3-Attack-1致命缺陷已彻底消除。schema统一 + 固定fieldnames + extrasaction安全网，三层防御。

### R3-Attack-2 [严重] arch硬编码 → **已修复** ✅

R3的严重问题：迁移result dict的arch字段硬编码为ARCH_NAME，OOM Level 3时CSV arch列失真。

R4修复验证：
- L512: `arch=source_info.get("arch", ARCH_NAME)`（FileNotFound）
- L575: `arch=source_info.get("arch", ARCH_NAME)`（cal empty）
- L587: `arch=source_info.get("arch", ARCH_NAME)`（ood empty）
- L635: `arch=source_info.get("arch", ARCH_NAME)`（normal result）
- L869: `arch=trained_models[(source, seed)].get("arch", ARCH_NAME)`（exception handler）

全部5处均使用动态获取，无硬编码ARCH_NAME作为arch值。source_info["arch"]在train_single L455被正确设为arch_display（含OOM备选"resnet1d"标识）。

**结论**：R3-Attack-2严重缺陷已修复。

### R3-Attack-4/6/7 [中等/轻微] 字段缺失 → **已修复** ✅

R3问题：early-return dict缺少n_dropped_cal/n_dropped_ood/truncated/subspace_filtered（Attack-4）、arch（Attack-6）、skipped（Attack-7）。

R4修复验证：_make_transfer_result的默认值机制自动补齐所有缺失字段：
- n_dropped_cal=0, n_dropped_ood=0, truncated=False, subspace_filtered=False（默认）
- arch=ARCH_NAME（默认，但所有调用点均显式传参覆盖）
- error=None, skipped=False（默认，early-return显式传True）

**结论**：R3-Attack-4/6/7已通过统一schema合并修复。

---

## R4新攻击点列表

### Attack-1 [中等] FileNotFound early-return未传num_classes和subspace_filtered，CSV统计字段失真

**位置**: L501（num_classes计算）+ L510-514（FileNotFound early-return）
**描述**:

num_classes在L501已计算（`num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])`），位于try块（L505）之前，因此在FileNotFound异常处理中**完全可用**。但L510-514的FileNotFound early-return未传num_classes和subspace_filtered：

```python
# L501: num_classes已计算（try块之前）
num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
# L505-514: try-except
try:
    tgt_ds, tgt_clusters = build_dataset(...)
except FileNotFoundError as e:
    return _make_transfer_result(
        source=source, target=target, seed=seed,
        arch=source_info.get("arch", ARCH_NAME),
        error=str(e), skipped=True,
        # ← 未传 num_classes（默认0）、subspace_filtered（默认False）
    )
```

对比cal/ood empty early-return（L573-581/L585-593）**显式传递**了num_classes和subspace_filtered，FileNotFound early-return是唯一遗漏的构造点。

**证据**: 反例——ptbxl→cpsc方向，cpsc数据集缺失：
- num_classes = min(5, 4) = 4（L501已计算）
- subspace_filtered应=True（4 < max(5,4)=5）
- 但CSV写入：num_classes=0, subspace_filtered=False（默认值）
- 下游分析者看到num_classes=0，无法区分"4类迁移目标缺失"与"未知类数迁移"

**影响**: 不影响运行时正确性（error/skipped字段标明跳过），但影响CBM要求的实验可追溯性。下游分析若不过滤skipped行直接统计num_classes分布，FileNotFound行会污染统计。
**判定**: 成立（中等）

---

### Attack-2 [中等] TRANSFER_RESULT_FIELDS与_make_transfer_result分离维护，extrasaction="ignore"会静默掩盖未来schema不一致

**位置**: L142-153（TRANSFER_RESULT_FIELDS）+ L156-214（_make_transfer_result）+ L710（extrasaction="ignore"）
**描述**:

TRANSFER_RESULT_FIELDS（22字段列表）和_make_transfer_result（返回22键dict）是**手动同步维护**的两个独立定义。当前一致（逐字段验证），但无自动化检查保证未来一致性。

若开发者向_make_transfer_result添加新字段但忘记同步TRANSFER_RESULT_FIELDS：
- _make_transfer_result返回23键dict
- TRANSFER_RESULT_FIELDS仍为22字段
- csv.DictWriter(extrasaction="ignore") **静默丢弃**第23个字段
- 无任何错误或警告，数据丢失

extrasaction="ignore"的设计意图是"容忍意外多余字段避免崩溃"，但副作用是**将崩溃替换为静默数据丢失**。对于科学实验代码，静默数据丢失比崩溃更危险——崩溃会被发现并修复，静默丢失可能流入论文。

**证据**: 当前无自动化校验。可构造反例：
```python
# 假设未来开发者修改 _make_transfer_result 添加 "new_metric" 字段
# 但忘记在 TRANSFER_RESULT_FIELDS 添加 "new_metric"
# → CSV中无 new_metric 列，所有行的 new_metric 值被静默丢弃
# → 论文引用的CSV数据缺失该指标，但无人察觉
```

**影响**: 当前无bug（两者一致），但存在维护风险。科学代码应优先"显式失败"而非"静默容忍"。
**判定**: 成立（中等，维护性风险）

---

### Attack-3 [轻微] extrasaction="ignore"将未来schema不匹配从崩溃降级为静默丢弃，违背科学代码"显式失败"原则

**位置**: L710
**描述**:

R3的Attack-1是csv.DictWriter默认extrasaction="raise"导致崩溃。R4的修复有两层：
1. **主修复**：统一schema（_make_transfer_result）→ 所有dict字段一致 → 无多余字段
2. **安全网**：extrasaction="ignore" → 即使有多余字段也不崩溃

主修复（层1）已完全消除R3-Attack-1，安全网（层2）是防御性冗余。但extrasaction="ignore"的语义是"静默忽略多余字段"，这意味着：
- 如果未来有人绕过_make_transfer_result手工构造dict（如L401的train_single返回`{"error": str(e), "skipped": True}`模式），多余字段会被静默丢弃
- 如果_make_transfer_result的某个字段名拼写错误（如"skippd"），TRANSFER_RESULT_FIELDS中的"skipped"列会写入空字符串，"skippd"列被丢弃，无警告

**证据**: csv.DictWriter文档——extrasaction="ignore"仅影响rowdict中**不在fieldnames中的键**，静默跳过不写入。
**影响**: 当前无bug（所有dict经_make_transfer_result构造），但降低了未来schema错误的可发现性。
**判定**: 成立（轻微，设计权衡）

---

### Attack-4 [轻微] CSV头注释和汇总报告仍用ARCH_NAME，与arch列动态值不一致

**位置**: L678（CSV头注释）+ L894（汇总报告）+ L759（启动信息）
**描述**:

R4修复了transfer result dict的arch字段（L512/L575/L587/L635/L869），但以下3处仍硬编码ARCH_NAME：

```python
# L678: CSV头注释
f.write(f"# 架构: {ARCH_NAME} (3 Inception modules, n_filters=48, bottleneck=48)\n")

# L759: 启动信息
print(f"# 架构: {ARCH_NAME} (3 blocks, n_filters={args.n_filters}, ...")

# L894: 汇总报告
print(f"架构: {ARCH_NAME}")
```

若OOM Level 3触发，部分模型用ResNet1D训练：
- CSV迁移结果表arch列：正确显示"resnet1d"（R4修复）
- CSV头注释：仍显示"inceptiontime_lite"（未修复）
- 汇总报告：仍显示"inceptiontime_lite"（未修复）

头注释与数据列矛盾，审稿人可能质疑数据一致性。

**证据**: grep ARCH_NAME显示L678/L759/L894三处未改为动态获取。
**影响**: 不影响数据正确性（arch列已正确），但影响可读性和可追溯性。属R3-Attack-2的未覆盖边界，R4修复了CSV数据列但遗漏了注释/报告。
**判定**: 成立（轻微，R3-Attack-2的残留边界）

---

### Attack-5 [轻微] run_dir用ARCH_NAME作为目录名，OOM备选时checkpoint路径与实际架构不符

**位置**: L426
**描述**:

```python
# L426: 训练checkpoint目录
run_dir = Path(args.save_dir) / dataset / ARCH_NAME / f"seed{seed}"
```

train_single有arch_override参数（L374），若arch_override="resnet1d"（OOM Level 3），checkpoint仍保存到`.../inceptiontime_lite/seed42/`目录。导致：
1. info["ckpt_path"]（L475）路径含"inceptiontime_lite"但info["arch"]="resnet1d"，路径与arch矛盾
2. 若同一dataset/seed先用InceptionTime-Lite训练再用ResNet1D训练（如多次运行不同OOM级别），checkpoint会互相覆盖

**证据**: L426用ARCH_NAME而非arch_display。对比L455 `info["arch"] = arch_display`（正确反映实际架构）。
**影响**: 不在R4修复范围内（R4仅修transfer result dict），但属arch动态获取的未覆盖点。checkpoint覆盖可能导致模型丢失。
**判定**: 成立（轻微，预存问题，R4未覆盖）

---

### Attack-6 [轻微] bool字段写入CSV为"True"/"False"字符串，pandas类型推断不确定

**位置**: L709-714（write_csv）+ _make_transfer_result的truncated/subspace_filtered/skipped字段
**描述**:

csv.DictWriter将Python bool写为str(bool)：
- `truncated=True` → CSV写入"True"
- `skipped=False` → CSV写入"False"

pandas.read_csv对"True"/"False"字符串的类型推断行为**版本相关**：
- pandas ≥1.3: 可能推断为bool（若列内全为"True"/"False"）
- pandas <1.3: 推断为object(str)
- 混合NaN（normal result的error=None写为空字符串→pandas读为NaN）: 列为object(str)

下游分析需`df.skipped == 'True'`而非`df.skipped == True`或`df.skipped`（bool上下文）。R4使所有dict都有bool字段（R3仅normal dict有truncated/subspace_filtered），使该问题更系统性。

**证据**: Python csv模块——str(True)="True", str(False)="False"。pandas文档——bool推断依赖列内容纯度。
**影响**: 不影响数据正确性，影响分析便利性。R3预存问题，R4加剧（更系统性）。
**判定**: 成立（轻微，预存问题）

---

### Attack-7 [轻微] NaN写入CSV为"nan"字符串，R语言默认不识别

**位置**: _make_transfer_result的float("nan")默认值 + L714 writer.writerow
**描述**:

_make_transfer_result对不可用的metric字段默认float("nan")。csv.DictWriter写为str(float("nan"))="nan"。

- pandas: 默认na_values包含"nan"→正确读为NaN ✅
- R read.csv: 默认na.strings="NA"→"nan"读为字符串→需手动na.strings="nan" ⚠️
- numpy.loadtxt: 需指定converters处理"nan"

R4使所有early-return dict都有nan metric字段（R3的early-return dict无这些字段→CSV空字符串），改变了NaN的CSV表示从空字符串到"nan"。

**证据**: Python str(float("nan"))="nan"。R文档——read.csv默认na.strings="NA"。
**影响**: 不影响pandas分析，影响R/其他语言分析。R3预存问题，R4改变表示形式。
**判定**: 成立（轻微，兼容性）

---

### Attack-8 [轻微] exception handler无法传递num_classes/subspace_filtered（main()作用域不可见）

**位置**: L862-871（main()中的except块）
**描述**:

```python
except Exception as e:
    transfer_results.append(_make_transfer_result(
        source=source, target=target, seed=seed,
        arch=trained_models[(source, seed)].get("arch", ARCH_NAME),
        error=str(e), skipped=True,
        # ← num_classes=0, subspace_filtered=False（默认）
    ))
```

num_classes和subspace_filtered是eval_transfer_pair的局部变量，在main()的except块中不可见。因此exception handler只能用默认值num_classes=0, subspace_filtered=False。

与Attack-1不同，此处是**作用域限制**而非遗漏——无法获取这些值。但结果相同：CSV中num_classes=0对跨类迁移（如ptbxl→cpsc应num_classes=4）是误导的。

**证据**: num_classes在eval_transfer_pair L501定义，main() L862-871无法访问。
**影响**: 不影响运行时正确性（error/skipped标明失败），影响统计字段准确性。可改进方案：eval_transfer_pair抛出自定义异常携带num_classes。
**判定**: 成立（轻微，作用域限制）

---

### Attack-9 [轻微] cal/ood empty early-return未传n_ood，跳过实验的OOD样本数丢失

**位置**: L573-581（cal empty）+ L585-593（ood empty）
**描述**:

cal empty early-return（L573-581）和ood empty early-return（L585-593）未传n_ood，默认n_ood=0。

但此时target数据集已成功加载（L506未抛FileNotFoundError），tgt_eval已计算（L518），ood_probs已有数据（L519）。只是cal集或ood集截断后为空，跳过TS校准。

- cal empty: ood集可能非空（有OOD样本但无法校准）→ n_ood=0误导（实际有OOD样本）
- ood empty: ood集确实为空 → n_ood=0正确

**证据**: L518 `tgt_eval = evaluate(...)`在L570的cal empty检查之前已执行，ood_probs已有值。L573-581未传n_ood=int(len(ood_probs))。
**影响**: cal empty场景下n_ood=0丢失"目标集有N个OOD样本但cal集为空无法校准"的信息。不影响运行时，影响根因分析。
**判定**: 成立（轻微，信息丢失）

---

## 7个攻击维度审查结论

| 维度 | 结论 |
|------|------|
| 1. 反例构造 | **Attack-1**：构造ptbxl→cpsc + cpsc数据缺失反例，num_classes=0（应=4）|
| 2. 逻辑断链 | **Attack-2**：TRANSFER_RESULT_FIELDS与_make_transfer_result无自动同步校验，逻辑链有断裂风险 |
| 3. 隐含假设 | **Attack-3**：extrasaction="ignore"隐含假设"多余字段可安全丢弃"，科学代码该假设不成立 |
| 4. 边界失效 | **Attack-8**：exception handler边界（作用域限制）导致num_classes=0 |
| 5. 自相矛盾 | **Attack-4**：CSV头注释arch=inceptiontime_lite vs 数据列arch=resnet1d（OOM时）|
| 6. 量级错误 | 未发现量级错误（字段数22=22，默认值类型正确）|
| 7. 语义偏移 | **Attack-9**：n_ood=0在cal empty场景语义偏移（"无OOD样本"vs"有OOD样本但未评估"）|

---

## R4修复逐项评价

| R4修复项 | 对应R3攻击 | 评价 | 说明 |
|---------|-----------|------|------|
| TRANSFER_RESULT_FIELDS常量 | Attack-1 | **有效** | 22字段覆盖所有构造点字段，与_make_transfer_result一致 |
| _make_transfer_result函数 | Attack-1/4/6/7 | **有效** | 统一所有5处构造点，默认值机制自动补齐缺失字段 |
| extrasaction="ignore" | Attack-1 | **有效但有副作用** | 消除崩溃但引入静默丢弃风险（Attack-2/3）|
| arch动态获取 | Attack-2 | **有效** | 5处均用source_info.get("arch", ARCH_NAME)，无硬编码遗漏 |

---

## 总结

- **致命攻击数**: 0
- **严重攻击数**: 0
- **中等攻击数**: 2（Attack-1 FileNotFound未传num_classes/subspace_filtered + Attack-2 schema分离维护风险）
- **轻微攻击数**: 7（Attack-3 extrasaction副作用 + Attack-4 头注释未同步 + Attack-5 run_dir未同步 + Attack-6 bool写入 + Attack-7 NaN写入 + Attack-8 exception作用域 + Attack-9 n_ood丢失）
- **总攻击数**: 9

### 总体评估

**R4修复成功解决了R3遗留的全部关键问题**：

1. **R3-Attack-1（致命）已彻底修复**：TRANSFER_RESULT_FIELDS + _make_transfer_result + extrasaction="ignore"三层防御，CSV schema不一致导致DictWriter崩溃的致命缺陷已消除。所有5处构造点统一使用_make_transfer_result，返回恰好22字段与TRANSFER_RESULT_FIELDS完全一致。

2. **R3-Attack-2（严重）已修复**：全部5处arch字段改用source_info.get("arch", ARCH_NAME)动态获取，OOM备选时迁移CSV的arch列正确反映源模型实际架构。

3. **R3-Attack-4/6/7（中等/轻微）已合并修复**：_make_transfer_result默认值机制自动补齐所有缺失字段。

**R4引入的新问题均为中等或轻微**，无致命或严重：

- 2个中等攻击（Attack-1/2）是**完整性不足**而非**错误**：FileNotFound未传可用字段、schema分离维护风险。不影响运行时正确性，影响可追溯性和维护性。
- 7个轻微攻击中，4个是**预存问题**（Attack-4/5/6/7），R4未引入但也未修复；3个是**R4副效应**（Attack-3/8/9），属设计权衡。

**判定**：R4修复**有效且基本完整**。R3终审裁决的P0-致命（Attack-1）和P0-严重（Attack-2）均已消除，无新致命/严重问题引入。剩余2个中等攻击建议R5轮修补（FileNotFound补传num_classes/subspace_filtered + 增加schema一致性自动校验），但不影响R4通过。

### R5可选改进项

| 优先级 | 攻击点 | 改进内容 | 改动量 |
|--------|--------|---------|--------|
| 中等 | Attack-1 | L510-514 FileNotFound early-return补传num_classes和subspace_filtered | 2行 |
| 中等 | Attack-2 | 增加assert _make_transfer_result(...)字段数==len(TRANSFER_RESULT_FIELDS)校验 | 1行 |
| 轻微 | Attack-4 | L678/L894改为动态arch（需汇总实际arch集合） | 2行 |
| 轻微 | Attack-5 | L426 run_dir改用arch_display | 1行 |
| 轻微 | Attack-9 | L573-581 cal empty补传n_ood=int(len(ood_probs)) | 1行 |
