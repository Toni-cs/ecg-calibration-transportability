# P0-6+7 R5反方攻击报告

## 审查范围
- 文件: scripts/run_e5_inception_lite.py（944行）
- 审查日期: 2026-09-10
- 审查代理: R5反方挑刺代理（GLM-5.2）
- R5修复内容: 5项必修——Attack-1 FileNotFound补传num_classes/subspace_filtered + Attack-2 schema assert校验 + Attack-9 cal empty补n_ood + Attack-4 CSV头注释动态arch_display + Attack-5 run_dir改arch_display
- R4遗留问题: Attack-1（中等，FileNotFound未传num_classes/subspace_filtered）+ Attack-2（中等，schema分离维护）+ Attack-4（轻微，头注释硬编码）+ Attack-5（轻微，run_dir硬编码）+ Attack-9（轻微，cal empty未传n_ood）

## 审查方法

逐行读取R5修复后的scripts/run_e5_inception_lite.py全文（944行），对照R4反方攻击报告（docs/p0r4_attack_p0_6_7.md）的9个攻击点和R4建议的5项R5改进，从7个攻击维度（反例构造/逻辑断链/隐含假设/边界失效/自相矛盾/量级错误/语义偏移）逐一审查R5的5项改动：
1. Attack-1修复: L520-525 FileNotFound early-return补传num_classes/subspace_filtered
2. Attack-2修复: L215-218 _make_transfer_result内schema assert校验
3. Attack-9修复: L592 cal empty early-return补传n_ood=0
4. Attack-4修复: L694-697 CSV头注释动态arch_display + L907-913 推断逻辑
5. Attack-5修复: L431-433 run_dir改用arch_display变量

---

## R4遗留攻击点修复验证

### R4-Attack-1 [中等] FileNotFound未传num_classes/subspace_filtered → **已修复但引入新语义错误** ⚠️

R4问题：FileNotFound early-return未传num_classes和subspace_filtered，CSV统计字段失真（num_classes=0, subspace_filtered=False默认值）。

R5修复（L520-525）：
```python
_fnf_num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
return _make_transfer_result(
    source=source, target=target, seed=seed,
    arch=source_info.get("arch", ARCH_NAME),
    num_classes=_fnf_num_classes,
    subspace_filtered=bool(_fnf_num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
    error=str(e), skipped=True,
)
```

**验证结论**：R5确实补传了num_classes和subspace_filtered，R4-Attack-1的字段缺失问题已解决。**但补传的值语义错误**——详见下方Attack-1和Attack-2。R5修复了"字段缺失"但引入了"语义错位"，属**修复方向正确但实现有缺陷**。

### R4-Attack-2 [中等] schema分离维护风险 → **已修复但assert在-O模式下失效** ⚠️

R4问题：TRANSFER_RESULT_FIELDS与_make_transfer_result手动同步维护，无自动化校验，extrasaction="ignore"会静默掩盖未来schema不一致。

R5修复（L215-218）：
```python
assert set(result.keys()) == set(TRANSFER_RESULT_FIELDS), \
    f"Schema mismatch: {set(result.keys())} != {set(TRANSFER_RESULT_FIELDS)}"
```

**验证结论**：R5在_make_transfer_result内添加了schema一致性assert校验，能捕获_make_transfer_result内部的字段增删。**但assert在python -O模式下被完全禁用**——详见下方Attack-3。R5修复了开发时校验但未覆盖生产时保护。

### R4-Attack-4 [轻微] CSV头注释用ARCH_NAME → **已修复但多架构混合时取首个不准确** ⚠️

R4问题：CSV头注释（L678）和汇总报告（L894）硬编码ARCH_NAME，OOM备选时与arch列矛盾。

R5修复（L694-697 + L907-913）：
```python
# L911: 推断实际arch_display
_csv_arch_display = train_results[0].get("arch", ARCH_NAME) if train_results else ARCH_NAME
write_csv(serializable_train, transfer_results, OUTPUT_CSV, oom_summary=oom_log,
          arch_display=_csv_arch_display)
```

**验证结论**：R5将CSV头注释改为动态arch_display，单架构场景正确。**但多架构混合时取train_results[0]只反映首个实验的arch**——详见下方Attack-6。汇总报告L919仍用ARCH_NAME未修复。

### R4-Attack-5 [轻微] run_dir用ARCH_NAME → **已修复但破坏R4 checkpoint路径兼容性** ⚠️

R4问题：run_dir用ARCH_NAME，OOM备选时checkpoint路径与实际架构不符，不同arch互相覆盖。

R5修复（L431-433）：
```python
run_dir = Path(args.save_dir) / dataset / arch_display / f"seed{seed}"
```

**验证结论**：R5将run_dir改为arch_display，消除了不同arch互相覆盖的bug。**但破坏了R4已保存的resnet1d checkpoint路径兼容性**——详见下方Attack-7。对inceptiontime_lite模型路径不变（兼容）。

### R4-Attack-9 [轻微] cal empty未传n_ood → **已修复但n_ood=0在ood_probs非空时事实错误** ⚠️

R4问题：cal empty early-return未传n_ood，默认n_ood=0，丢失"目标集有N个OOD样本但cal集为空"的信息。

R5修复（L592）：
```python
return _make_transfer_result(
    ...
    n_ood=0,  # ← R5显式补传
    ...
)
```

**验证结论**：R5显式补传了n_ood=0。**但cal empty时ood_probs可能非空，n_ood=0事实错误**——详见下方Attack-4和Attack-5。R5的修复注释说"cal空导致TS校准跳过，无有效ood评估结果，n_ood=0"，但n_ood字段语义是"ood样本数"而非"有效评估数"，语义偏移。

---

## R5新攻击点列表

### Attack-1 [严重] FileNotFound路径subspace_filtered=True语义错误——无过滤发生却报True

**位置**: L525
**攻击维度**: 语义偏移 + 反例构造

**描述**:
R5在FileNotFound early-return中计算`subspace_filtered=bool(_fnf_num_classes < max(...))`。但FileNotFound时**目标数据集根本未加载**，没有任何子空间过滤操作发生。subspace_filtered=True表示"实际触发了5→4子空间过滤"，但在FileNotFound场景下过滤操作**从未执行**。

**反例**:
- 输入: source=ptbxl(5类), target=cpsc(4类), cpsc数据集不存在
- R5返回: num_classes=4, subspace_filtered=True
- 实际: cpsc未加载，无任何过滤发生，subspace_filtered应为False
- 下游分析者看到subspace_filtered=True，误以为过滤操作执行了，可能据此调整统计口径

**证据**: L513 `build_dataset(target, ...)`抛FileNotFoundError，L514-527捕获后直接返回。subspace过滤发生在L509 `subspace = SUBSPACE_CPSC if num_classes == 4 else None`和build_dataset内部，但build_dataset从未成功执行。

**影响**: 下游分析若按subspace_filtered分组统计，FileNotFound行会被误归入"已过滤"组，污染统计。
**判定**: 成立（严重，语义误导）

---

### Attack-2 [严重] FileNotFound路径skipped=True与num_classes/subspace_filtered有效值自相矛盾

**位置**: L521-527
**攻击维度**: 自相矛盾

**描述**:
FileNotFound early-return同时返回：
- `skipped=True`（表示"实验跳过，无有效结果"）
- `num_classes=4`（表示"目标有4类"——但目标不存在）
- `subspace_filtered=True`（表示"触发了过滤"——但无过滤发生）

skipped=True与num_classes/subspace_filtered的有效值**逻辑互斥**：如果实验跳过了，统计字段应为"不适用"（None/0/False），而非"有效值"。R5的修复让skipped行携带了"假有效"的统计信息，自相矛盾。

**反例**:
```python
# R5返回的dict（FileNotFound, ptbxl→cpsc）
{
    "skipped": True,           # 跳过了
    "num_classes": 4,          # 但有4类？（目标不存在）
    "subspace_filtered": True, # 且过滤了？（无过滤发生）
    "error": "FileNotFoundError: ...",
}
```

下游若不过滤skipped行直接统计num_classes分布：
```python
df = pd.read_csv("results/c3_inceptiontime_lite_30exp.csv")
print(df.num_classes.describe())  # FileNotFound行的num_classes=4污染统计
```

**证据**: 对比正常路径L649-669，skipped=False时num_classes/subspace_filtered是实际值；FileNotFound路径skipped=True但num_classes/subspace_filtered也是"实际值"，逻辑不一致。
**影响**: 下游分析若不过滤skipped行，统计字段被"假有效"值污染。
**判定**: 成立（严重，自相矛盾）

---

### Attack-3 [严重] schema assert在python -O模式下被完全禁用，生产环境无保护

**位置**: L217-218
**攻击维度**: 隐含假设 + 边界失效

**描述**:
R5用`assert set(result.keys()) == set(TRANSFER_RESULT_FIELDS)`做schema校验。但Python的`assert`语句在`python -O`或`python -OO`优化模式下**会被完全移除**，不执行任何代码。

R5修复Attack-2的意图是"防止未来schema不一致导致静默数据丢失"。但在`python -O`模式下，assert不触发，schema校验形同虚设，R4-Attack-2的静默数据丢失风险**完全恢复**。

**反例**:
```bash
# 生产环境用优化模式运行
python -O scripts/run_e5_inception_lite.py
# → L217-218的assert被完全移除
# → 若开发者未来修改_make_transfer_result添加字段但忘记同步TRANSFER_RESULT_FIELDS
# → csv.DictWriter(extrasaction="ignore")静默丢弃新字段
# → 无任何错误，数据丢失流入CSV
```

**证据**: Python文档——`-O`移除assert语句；`-OO`移除assert和docstring。生产部署常用`python -O`提升性能。
**影响**: R5的schema校验在-O模式下完全失效，R4-Attack-2的维护风险未消除。
**判定**: 成立（严重，生产环境失效）

---

### Attack-4 [严重] cal empty路径n_ood=0在ood_probs非空时事实错误

**位置**: L592
**攻击维度**: 反例构造 + 语义偏移

**描述**:
R5在cal empty early-return中显式补传`n_ood=0`。但cal empty检查（L583 `if len(cal_probs) == 0`）时，ood_probs已经过截断和全零行过滤（L548-579），但**尚未检查ood_probs是否为空**。ood_probs可能非空——cal和ood是独立截断的，cal空不代表ood空。

R5的注释说"cal空导致TS校准跳过，无有效ood评估结果，n_ood=0"。但n_ood字段在正常路径（L653）的语义是`int(len(ood_probs))`="ood样本数"，而非"有效ood评估数"。R5在cal empty路径将n_ood语义从"ood样本数"偏移为"有效评估数"。

**反例**:
- 输入: source=ptbxl(5类), target=cpsc(4类)
- cal集截断后为空（所有cal样本标签≥4被丢弃）
- ood集截断后有100个样本（标签<4的ood样本保留）
- R5返回: n_ood=0（**事实错误**，实际ood集有100个样本）
- 正确值: n_ood=100（=int(len(ood_probs))）

**证据**: L583检查`len(cal_probs) == 0`时，ood_probs已在L548-549截断、L567-579全零行过滤，但未检查`len(ood_probs)`。L598的ood empty检查在cal empty返回之后，不会执行。
**影响**: 下游分析用n_ood统计ood样本数时，cal empty行的n_ood=0低估了实际ood样本数。若用n_ood过滤"空ood实验"，cal empty行被误归入"ood空"组。
**判定**: 成立（严重，事实错误+语义偏移）

---

### Attack-5 [严重] cal empty与ood empty路径n_ood=0语义不一致

**位置**: L592（cal empty）vs L601-609（ood empty）
**攻击维度**: 自相矛盾 + 语义偏移

**描述**:
R5在cal empty路径显式传`n_ood=0`（L592），ood empty路径不传n_ood（默认0，L601-609）。两条路径都返回n_ood=0，但**含义不同**：

| 路径 | n_ood=0的含义 | 事实正确性 |
|------|-------------|-----------|
| cal empty | "无有效ood评估"（TS校准跳过） | **错误**（ood_probs可能非空）|
| ood empty | "ood集为空"（无ood样本） | **正确**（ood_probs确实为空）|

下游分析无法通过n_ood=0区分这两种场景：
- "cal空但ood有100样本"（cal empty，n_ood=0错误）
- "ood确实为空"（ood empty，n_ood=0正确）

**反例**:
```python
# 两个transfer result，都n_ood=0
result_a = {"error": "cal set empty after truncation", "n_ood": 0, ...}  # ood实际有100样本
result_b = {"error": "ood set empty after truncation", "n_ood": 0, ...}  # ood确实为空
# 下游无法通过n_ood区分，但两者根因完全不同
```

**证据**: L592 cal empty传n_ood=0；L601-609 ood empty不传n_ood（默认0）。两条路径的ood_probs状态不同但n_ood值相同。
**影响**: 下游根因分析无法通过n_ood区分"cal空"和"ood空"，需依赖error字符串匹配（脆弱）。
**判定**: 成立（严重，语义不一致）

---

### Attack-6 [严重] 多架构混合时CSV头注释取train_results[0]不准确

**位置**: L911
**攻击维度**: 反例构造 + 隐含假设

**描述**:
R5用`_csv_arch_display = train_results[0].get("arch", ARCH_NAME)`推断CSV头注释的arch。这取**首个训练结果**的arch，隐含假设"所有训练结果用同一arch"。

但OOM备选是per-(dataset, seed)的：不同(dataset, seed)可能触发不同OOM级别，用不同arch。若部分实验用inceptiontime_lite、部分因OOM降级为resnet1d，train_results[0]只反映首个实验的arch，CSV头注释**不反映实际架构混合**。

**反例**:
- 15个训练实验（3数据集×5种子）
- ptbxl 5种子: 全部成功用inceptiontime_lite
- chapman 5种子: 全部OOM，降级为resnet1d（Level 3）
- cpsc 5种子: 全部成功用inceptiontime_lite
- train_results[0] = ptbxl seed=42, arch=inceptiontime_lite
- R5 CSV头注释: "# 架构: inceptiontime_lite (3 Inception modules, n_filters=48, bottleneck=48)"
- **实际有5个resnet1d模型**，头注释完全误导

审稿人按头注释复现实验，只训练inceptiontime_lite，得不到resnet1d结果，**可复现性受损**。

**证据**: L911取train_results[0]；OOM备选在try_train_with_oom_fallback中per-(dataset,seed)独立触发（L820-835）；arch_display在train_single L395按arch_override独立计算。
**影响**: 多架构混合时CSV头注释不准确，论文可复现性受损。
**判定**: 成立（严重，可复现性）

---

### Attack-7 [严重] run_dir改arch_display破坏R4 resnet1d checkpoint路径兼容性

**位置**: L433
**攻击维度**: 边界失效 + 隐含假设

**描述**:
R5将run_dir从`.../ARCH_NAME/...`改为`.../arch_display/...`。对inceptiontime_lite模型，arch_display=ARCH_NAME，路径不变（兼容）。对resnet1d模型（OOM Level 3），arch_display="resnet1d"，路径从`.../inceptiontime_lite/...`变为`.../resnet1d/...`。

**R4已保存的resnet1d checkpoint在`.../inceptiontime_lite/...`目录**（因R4用ARCH_NAME）。R5升级后找`.../resnet1d/...`目录，**找不到旧checkpoint**，需重新训练。

**反例**:
```bash
# R4版本训练（OOM触发Level 3，arch_override="resnet1d"）
python scripts/run_e5_inception_lite.py  # R4代码
# → checkpoint保存到 checkpoints/e5_inception_lite/chapman/inceptiontime_lite/seed42/best_model.pt
# → （R4用ARCH_NAME，resnet1d也存到inceptiontime_lite目录）

# R5版本继续训练（同样OOM触发Level 3）
python scripts/run_e5_inception_lite.py  # R5代码
# → run_dir = checkpoints/e5_inception_lite/chapman/resnet1d/seed42/
# → 找不到R4的checkpoint（在inceptiontime_lite目录），从头训练
# → 用户困惑：为什么R5不加载已有checkpoint？
```

R5修复了R4-Attack-5的"不同arch互相覆盖"bug，但**未提供迁移路径或兼容性警告**。用户从R4升级到R5后，resnet1d checkpoint"消失"。

**证据**: R4 L426 `run_dir = Path(args.save_dir) / dataset / ARCH_NAME / f"seed{seed}"`；R5 L433 `run_dir = Path(args.save_dir) / dataset / arch_display / f"seed{seed}"`。arch_display="resnet1d"时路径不同。
**影响**: R4用户升级R5后resnet1d checkpoint无法复用，需重新训练（30-45 GPU小时）或手动迁移checkpoint目录。
**判定**: 成立（严重，兼容性破坏）

---

### Attack-8 [轻微] FileNotFound路径num_classes为假设值非实际值

**位置**: L520
**攻击维度**: 语义偏移

**描述**:
R5在FileNotFound路径计算`_fnf_num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])`。这是"如果目标数据集存在，num_classes会是多少"的**假设值**，而非实际值——目标数据集不存在，没有实际的num_classes。

num_classes字段在正常路径表示"目标数据集的实际类数"，FileNotFound路径填假设值，语义偏移为"目标数据集如果存在的理论类数"。

**反例**: target=cpsc不存在，num_classes=4（DATASET_NUM_CLASSES["cpsc"]=4的硬编码值）。但cpsc不存在，4是理论值非实际值。
**影响**: 轻微——下游若过滤skipped行则不影响；若不过滤，num_classes=4是"合理的占位值"（比R4的0更接近实际），但语义上应为None。
**判定**: 成立（轻微，语义偏移）

---

### Attack-9 [轻微] assert每次调用重复构造set，性能微优化空间

**位置**: L217
**攻击维度**: 量级错误

**描述**:
`assert set(result.keys()) == set(TRANSFER_RESULT_FIELDS)`每次调用都重新构造两个set。TRANSFER_RESULT_FIELDS是模块级常量，可预构造`_TRANSFER_RESULT_FIELDS_SET = set(TRANSFER_RESULT_FIELDS)`避免重复构造。

**量级分析**: 30个迁移实验×1次调用/实验=30次set构造，每次O(22)=O(660)操作。相对于训练时间（30-45小时）是纳秒级，**性能影响可忽略**。

**影响**: 轻微——性能影响可忽略，但属代码质量改进点。
**判定**: 成立（轻微，性能微优化）

---

### Attack-10 [轻微] assert仅覆盖_make_transfer_result内部，外部构造无保护

**位置**: L217
**攻击维度**: 逻辑断链

**描述**:
R5的schema assert在_make_transfer_result函数内部，仅校验经_make_transfer_result构造的dict。若未来有人绕过_make_transfer_result直接构造dict（如train_single L406的`{"error": str(e), "skipped": True}`模式），assert不触发。

当前所有5处transfer result构造点都用_make_transfer_result（L521/L588/L601/L649/L886），覆盖完整。但assert的**保护范围限于函数内部**，无法防止外部绕过。

**证据**: grep `_make_transfer_result`显示5处调用，无直接构造transfer result dict的代码。但train_single L406有`{"error": str(e), "skipped": True}`的直接构造模式（非transfer result）。
**影响**: 轻微——当前无风险，未来维护需约束"所有transfer result必须经_make_transfer_result构造"。
**判定**: 成立（轻微，维护性风险）

---

### Attack-11 [轻微] 空train_results回退ARCH_NAME但实际无模型

**位置**: L911
**攻击维度**: 边界失效

**描述**:
`_csv_arch_display = train_results[0].get("arch", ARCH_NAME) if train_results else ARCH_NAME`。当train_results为空（所有训练OOM降级），回退到ARCH_NAME="inceptiontime_lite"。

但此时**无任何inceptiontime_lite模型**（全部降级为resnet1d或更低），CSV头注释写"# 架构: inceptiontime_lite"是错误的——应反映"全部降级"或"无模型"。

**反例**: 15个训练实验全部OOM降级为resnet1d，train_results为空（model is None时不append，L836-840）。CSV头注释写"inceptiontime_lite"，但实际无inceptiontime_lite模型。
**影响**: 轻微——边界情况，且此时transfer_results也为空，CSV几乎无内容。但头注释语义错误。
**判定**: 成立（轻微，边界失效）

---

### Attack-12 [轻微] arch_display未校验为合法路径组件

**位置**: L433
**攻击维度**: 边界失效

**描述**:
R5将arch_display直接用作run_dir的路径组件：`run_dir = Path(args.save_dir) / dataset / arch_display / f"seed{seed}"`。但arch_display未校验是否为合法文件系统路径组件（不含`/`, `\`, `:`, 空格等特殊字符）。

arch_display = arch_override if arch_override else ARCH_NAME。当前arch_override只有"resnet1d"和None（L265-270），ARCH_NAME="inceptiontime_lite"，都是合法路径组件。但若未来arch_override含特殊字符（如"resnet1d_v2.0"或"arch/variant"），run_dir构造会出错或创建意外目录结构。

**证据**: L395 `arch_display = arch_override if arch_override else ARCH_NAME`，无路径合法性校验。L433直接用作Path组件。
**影响**: 轻微——当前安全，未来维护风险。
**判定**: 成立（轻微，未来维护风险）

---

### Attack-13 [轻微] main()启动日志用ARCH_NAME与run_dir用arch_display不一致

**位置**: L778-779 vs L433
**攻击维度**: 自相矛盾

**描述**:
R5修复了run_dir用arch_display（L433），但main()启动日志仍用ARCH_NAME：
```python
# L778-779: 启动日志
print(f"# 架构: {ARCH_NAME} (3 blocks, n_filters={args.n_filters}, ...)")
```

若OOM备选触发，run_dir用resnet1d，但启动日志打印"inceptiontime_lite"，自相矛盾。用户看日志以为训练inceptiontime_lite，实际checkpoint存到resnet1d目录。

同样，L919汇总报告`print(f"架构: {ARCH_NAME}")`也仍用ARCH_NAME。

**证据**: L778用ARCH_NAME；L433用arch_display；L919用ARCH_NAME。三处不一致。
**影响**: 轻微——日志与实际路径不一致，不影响功能，但影响调试可读性。
**判定**: 成立（轻微，日志不一致）

---

## 7个攻击维度审查结论

| 维度 | 结论 |
|------|------|
| 1. 反例构造 | **Attack-1**: ptbxl→cpsc + cpsc不存在 → subspace_filtered=True（无过滤却报True）；**Attack-4**: cal空ood有100样本 → n_ood=0（应=100）；**Attack-6**: 多架构混合 → 头注释取首个不准确 |
| 2. 逻辑断链 | **Attack-10**: assert仅覆盖_make_transfer_result内部，外部构造无保护 |
| 3. 隐含假设 | **Attack-3**: assert隐含假设"不在-O模式运行"，生产环境不成立；**Attack-6**: 头注释隐含假设"所有训练结果同arch"，OOM部分触发时不成立；**Attack-7**: run_dir改arch_display隐含假设"无R4旧checkpoint需兼容"，不成立 |
| 4. 边界失效 | **Attack-7**: R4→R5升级边界，resnet1d checkpoint路径变化；**Attack-11**: 空train_results边界，回退ARCH_NAME但无模型；**Attack-12**: arch_display含特殊字符边界 |
| 5. 自相矛盾 | **Attack-2**: skipped=True与num_classes/subspace_filtered有效值互斥；**Attack-5**: cal empty与ood empty的n_ood=0含义不同但值相同；**Attack-13**: 启动日志ARCH_NAME vs run_dir arch_display |
| 6. 量级错误 | **Attack-9**: assert每次重复构造set，性能影响可忽略但存在微优化空间 |
| 7. 语义偏移 | **Attack-1**: subspace_filtered从"实际过滤"偏移为"理论过滤"；**Attack-4**: n_ood从"ood样本数"偏移为"有效评估数"；**Attack-8**: num_classes从"实际类数"偏移为"理论类数" |

---

## R5修复逐项评价

| R5修复项 | 对应R4攻击 | 评价 | 说明 |
|---------|-----------|------|------|
| Attack-1: FileNotFound补传num_classes/subspace_filtered | R4-Attack-1 | **方向正确但值语义错误** | 补传了字段（解决缺失），但subspace_filtered=True无过滤却报True（Attack-1），skipped=True与有效值矛盾（Attack-2） |
| Attack-2: schema assert校验 | R4-Attack-2 | **开发时有效但生产时失效** | assert在-O模式下被移除（Attack-3），仅覆盖_make_transfer_result内部（Attack-10） |
| Attack-9: cal empty补n_ood=0 | R4-Attack-9 | **事实错误** | cal空时ood_probs可能非空，n_ood=0低估实际ood样本数（Attack-4），与ood empty路径语义不一致（Attack-5） |
| Attack-4: CSV头注释动态arch_display | R4-Attack-4 | **单架构正确但多架构混合不准确** | 取train_results[0]只反映首个arch（Attack-6），空train_results回退ARCH_NAME但无模型（Attack-11） |
| Attack-5: run_dir改arch_display | R4-Attack-5 | **修复覆盖bug但破坏兼容性** | 消除不同arch互相覆盖，但R4 resnet1d checkpoint路径变化（Attack-7），启动日志未同步（Attack-13） |

---

## 总结

- **致命攻击数**: 0
- **严重攻击数**: 7（Attack-1 subspace_filtered语义错误 + Attack-2 skipped矛盾 + Attack-3 assert -O失效 + Attack-4 n_ood事实错误 + Attack-5 n_ood语义不一致 + Attack-6 多架构头注释 + Attack-7 checkpoint兼容性）
- **轻微攻击数**: 6（Attack-8 num_classes假设值 + Attack-9 assert性能 + Attack-10 assert覆盖范围 + Attack-11 空train_results + Attack-12 路径合法性 + Attack-13 日志不一致）
- **总攻击数**: 13

### 总体评估

**R5修复了R4遗留的5项问题，但每项修复都引入了新的缺陷**：

1. **Attack-1修复（FileNotFound补传字段）**：解决了字段缺失，但补传的subspace_filtered=True语义错误（无过滤却报True），且skipped=True与有效值自相矛盾。**修复方向正确但值选择错误**——应传subspace_filtered=False（无过滤发生）、num_classes=0或None（目标不存在）。

2. **Attack-2修复（schema assert）**：添加了开发时校验，但assert在python -O模式下被完全禁用，生产环境无保护。应改用`if ... : raise RuntimeError(...)`显式校验，不受-O影响。

3. **Attack-9修复（cal empty补n_ood=0）**：n_ood=0在ood_probs非空时事实错误。应传`n_ood=int(len(ood_probs))`（实际ood样本数），而非0。

4. **Attack-4修复（CSV头注释动态arch_display）**：单架构场景正确，但多架构混合时取train_results[0]只反映首个arch。应收集所有unique arch并写入头注释（如"# 架构: inceptiontime_lite, resnet1d (混合)"）。

5. **Attack-5修复（run_dir改arch_display）**：消除了不同arch互相覆盖的bug，但破坏了R4 resnet1d checkpoint路径兼容性。应添加迁移警告或兼容性检查。

**判定**：R5修复**方向全部正确但实现均有缺陷**。无致命问题引入，但7个严重攻击中，Attack-1/2/4/5是R5修复直接引入的新缺陷，Attack-3/6/7是R5修复的隐含假设不成立。建议R6轮修补：

### R6必修改进项

| 优先级 | 攻击点 | 改进内容 | 改动量 |
|--------|--------|---------|--------|
| 严重 | Attack-1 | L525 subspace_filtered改为False（FileNotFound时无过滤发生） | 1行 |
| 严重 | Attack-2 | L520-525 num_classes改为0或None（目标不存在），与skipped=True语义一致 | 1行 |
| 严重 | Attack-3 | L217-218 assert改为`if set(...) != set(...): raise RuntimeError(...)`，不受-O影响 | 2行 |
| 严重 | Attack-4 | L592 n_ood改为`int(len(ood_probs))`（实际ood样本数） | 1行 |
| 严重 | Attack-6 | L911 收集所有unique arch：`set(r.get("arch", ARCH_NAME) for r in train_results)`，多架构时写"混合" | 3行 |
| 严重 | Attack-7 | L433 添加R4 checkpoint路径兼容性检查：若新路径不存在但旧路径（ARCH_NAME）存在，打印警告 | 5行 |
| 轻微 | Attack-13 | L778/L919 改用动态arch_display（需从train_results推断或传参） | 2行 |
