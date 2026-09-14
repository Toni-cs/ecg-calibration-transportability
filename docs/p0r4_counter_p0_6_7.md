# R4反反方审查报告：P0-6+7

## 审查摘要
- 反方攻击报告：docs/p0r4_attack_p0_6_7.md
- 审查文件：scripts/run_e5_inception_lite.py（919行）
- 攻击点总数：9
- 成立攻击：8（Attack-1/2/4/5/6/7/8/9）
- 部分成立攻击：1（Attack-3）
- 不成立攻击：0
- 需R5修补项：5（必修）+ 3（可选）

## 审查方法

逐行对照源代码（scripts/run_e5_inception_lite.py）验证反方每个攻击点的：
1. 行号准确性（grep + read 双重核对）
2. 代码事实（反方引用的代码片段是否与源文件一致）
3. 反例可构造性（反方构造的反例是否真的能触发）
4. 影响评估（反方声称的影响是否合理）
5. 是否稻草人论证（反方是否误解正方意图或夸大严重度）

**关键验证**：
- TRANSFER_RESULT_FIELDS（L142-153）= 22字段，_make_transfer_result返回（L191-214）= 22键，逐字段比对完全一致 ✅
- 5处构造点（L510/L573/L585/L633/L867）均调用_make_transfer_result ✅
- ARCH_NAME硬编码残留点：L426（run_dir）/L678（CSV头注释）/L759（启动信息）/L894（汇总报告）共4处 ✅
- num_classes在L501定义，位于try块（L505）之前，FileNotFound except块中可用 ✅

---

## 逐条审查

### Attack-1: FileNotFound early-return未传num_classes和subspace_filtered，CSV统计字段失真

**判定**：成立（中等）

**理由**：

经源代码逐行验证，反方描述完全准确：

1. **L501**：`num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])` 确实在try块（L505）**之前**定义，在FileNotFoundError except块（L507-514）中**完全可用**。

2. **L510-514**（FileNotFound early-return）：
```python
return _make_transfer_result(
    source=source, target=target, seed=seed,
    arch=source_info.get("arch", ARCH_NAME),
    error=str(e), skipped=True,
    # 未传 num_classes（默认0）、subspace_filtered（默认False）
)
```
确实未传num_classes和subspace_filtered。

3. **对比L573-581**（cal empty early-return）和**L585-593**（ood empty early-return）：两处均显式传递了`num_classes=num_classes`和`subspace_filtered=bool(...)`。FileNotFound early-return是5个构造点中**唯一遗漏**这两个字段的。

4. **反例可构造**：ptbxl→cpsc方向，cpsc数据集缺失时：
   - L501已计算 `num_classes = min(5, 4) = 4`
   - `subspace_filtered` 应为 `bool(4 < max(5,4)) = bool(4 < 5) = True`
   - 但CSV写入：`num_classes=0, subspace_filtered=False`（_make_transfer_result默认值）
   - 下游分析者看到num_classes=0，无法区分"4类迁移目标缺失"与"未知类数迁移"

5. **影响评估合理**：反方承认"不影响运行时正确性（error/skipped字段标明跳过）"，仅影响CBM要求的实验可追溯性。定级中等合理。

**修补方案**：

文件：`scripts/run_e5_inception_lite.py`
行号：L510-514
改动：补传num_classes和subspace_filtered

```python
# 修改前（L510-514）：
return _make_transfer_result(
    source=source, target=target, seed=seed,
    arch=source_info.get("arch", ARCH_NAME),
    error=str(e), skipped=True,
)

# 修改后：
return _make_transfer_result(
    source=source, target=target, seed=seed,
    arch=source_info.get("arch", ARCH_NAME),
    num_classes=num_classes,
    subspace_filtered=bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
    error=str(e), skipped=True,
)
```
改动量：+2行

---

### Attack-2: TRANSFER_RESULT_FIELDS与_make_transfer_result分离维护，extrasaction="ignore"会静默掩盖未来schema不一致

**判定**：成立（中等，维护性风险）

**理由**：

经源代码逐字段验证：

1. **TRANSFER_RESULT_FIELDS**（L142-153）共22字段：
   `source, target, seed, arch, num_classes, n_ood, ood_acc_raw, fitted_T, ood_ece_raw, ood_ece_ts, ood_brier_raw, ood_brier_ts, delta_ece, delta_ece_ci_low, delta_ece_ci_high, brier_reliability_improvement, n_dropped_cal, n_dropped_ood, truncated, subspace_filtered, error, skipped`

2. **_make_transfer_result返回dict**（L191-214）共22键，与TRANSFER_RESULT_FIELDS**逐字段完全一致**。

3. **当前无bug**：两者一致，csv.DictWriter正常工作。

4. **维护风险真实存在**：两者是手动同步维护的独立定义，无自动化校验。若未来开发者向_make_transfer_result添加新字段但忘记同步TRANSFER_RESULT_FIELDS：
   - _make_transfer_result返回23键dict
   - TRANSFER_RESULT_FIELDS仍为22字段
   - csv.DictWriter(extrasaction="ignore") **静默丢弃**第23个字段
   - 无任何错误或警告，数据丢失

5. **反方论证合理**：对科学实验代码，静默数据丢失比崩溃更危险——崩溃会被发现并修复，静默丢失可能流入论文。这是真实的维护性风险。

**修补方案**：

文件：`scripts/run_e5_inception_lite.py`
行号：L214后（_make_transfer_result函数末尾）或模块级
改动：增加schema一致性自动校验

```python
# 方案A（模块级断言，推荐）：在L214后添加
# R5 修复 Attack-2: schema 一致性自动校验，防止 TRANSFER_RESULT_FIELDS 与
# _make_transfer_result 分离维护导致静默数据丢失。
assert len(TRANSFER_RESULT_FIELDS) == len(_make_transfer_result.__code__.co_varnames), \
    "TRANSFER_RESULT_FIELDS 与 _make_transfer_result 参数数不一致，请同步更新"

# 方案B（运行时校验，更稳健）：在 _make_transfer_result 函数体末尾（L214 return 前）添加
_result = { ... }  # 现有dict
assert set(_result.keys()) == set(TRANSFER_RESULT_FIELDS), \
    f"schema 不一致: {_result.keys()} vs {TRANSFER_RESULT_FIELDS}"
return _result
```
改动量：+1~3行

推荐方案B（运行时校验），因为它能捕获字段名拼写错误（如"skippd" vs "skipped"），而方案A仅校验数量。

---

### Attack-3: extrasaction="ignore"将未来schema不匹配从崩溃降级为静默丢弃，违背科学代码"显式失败"原则

**判定**：部分成立（轻微，设计权衡）

**理由**：

反方对R4修复结构的理解准确：
1. **主修复**（层1）：统一schema（_make_transfer_result）→ 所有dict字段一致 → 无多余字段
2. **安全网**（层2）：extrasaction="ignore" → 即使有多余字段也不崩溃

反方提出的两个风险场景分析：

**场景1**（绕过_make_transfer_result手工构造dict）：
- 反方引用L401的train_single返回`{"error": str(e), "skipped": True}`作为例子
- **但L401是train_single的返回，不是transfer_results**。train_single的返回dict由write_csv的**训练结果表**（L692）写入，使用`fieldnames=list(train_results[0].keys())`，**不经过TRANSFER_RESULT_FIELDS和extrasaction="ignore"**
- transfer_results只由eval_transfer_pair和main()的except块构造，全部5处均经_make_transfer_result
- **此场景不成立**——反方混淆了train_single返回dict和transfer result dict两个独立的schema

**场景2**（_make_transfer_result字段名拼写错误）：
- 若开发者将"skipped"误写为"skippd"，TRANSFER_RESULT_FIELDS中的"skipped"列会写入空字符串，"skippd"列被extrasaction="ignore"静默丢弃
- **此场景成立**——这是真实的维护风险，但与Attack-2同源，Attack-2的修补方案（运行时schema一致性校验）可同时消解此风险

**设计权衡分析**：
- 若改用extrasaction="raise"：消除静默丢弃风险，但若未来有人绕过_make_transfer_result构造多余字段dict，会重新触发R3-Attack-1的崩溃
- 当前选择extrasaction="ignore" + 主修复（统一schema）：崩溃风险已由主修复消除，安全网仅防御意外
- **最佳方案**：保留extrasaction="ignore" + 增加Attack-2的schema一致性校验 → 既不崩溃也不静默丢失

**反驳**：反方将此攻击独立列为"违背科学代码显式失败原则"，但忽略了两层修复的互补关系。主修复已实现"显式失败"（_make_transfer_result强制统一schema），安全网是防御性冗余而非主要防线。将此攻击定级为"轻微"合理，但其独立性弱——与Attack-2同源，修补Attack-2后此攻击自动消解。

**修补方案**：与Attack-2合并修补。增加schema一致性校验后，字段名拼写错误会被assert捕获，静默丢弃风险消除。无需独立修补。

---

### Attack-4: CSV头注释和汇总报告仍用ARCH_NAME，与arch列动态值不一致

**判定**：成立（轻微，R3-Attack-2的残留边界）

**理由**：

经grep验证，ARCH_NAME在源文件中共出现12处（L105定义 + 11处使用）。R4修复了5处transfer result dict的arch字段（L512/L575/L587/L635/L869），但以下3处仍硬编码ARCH_NAME：

1. **L678**（CSV头注释）：
```python
f.write(f"# 架构: {ARCH_NAME} (3 Inception modules, n_filters=48, bottleneck=48)\n")
```

2. **L759**（启动信息）：
```python
print(f"# 架构: {ARCH_NAME} (3 blocks, n_filters={args.n_filters}, "
```

3. **L894**（汇总报告）：
```python
print(f"架构: {ARCH_NAME}")
```

**反例可构造**：若OOM Level 3触发，部分模型用ResNet1D训练：
- CSV迁移结果表arch列：正确显示"resnet1d"（R4修复L635）
- CSV头注释（L678）：仍显示"inceptiontime_lite"
- 汇总报告（L894）：仍显示"inceptiontime_lite"
- 头注释与数据列矛盾，审稿人可能质疑数据一致性

**影响评估合理**：反方承认"不影响数据正确性（arch列已正确），但影响可读性和可追溯性"。定级轻微合理。

**修补方案**：

文件：`scripts/run_e5_inception_lite.py`

**L678**（CSV头注释）：改为汇总实际使用的arch集合
```python
# 修改前：
f.write(f"# 架构: {ARCH_NAME} (3 Inception modules, n_filters=48, bottleneck=48)\n")

# 修改后（需在write_csv函数签名增加arch_used参数）：
_archs_used = sorted({r.get("arch", ARCH_NAME) for r in transfer_results})
f.write(f"# 架构: {', '.join(_archs_used)} (OOM备选可能含多架构)\n")
```

**L894**（汇总报告）：改为汇总实际arch集合
```python
# 修改前：
print(f"架构: {ARCH_NAME}")

# 修改后：
_archs_used = sorted({r.get("arch", ARCH_NAME) for r in transfer_results})
print(f"架构: {', '.join(_archs_used)}")
```

**L759**（启动信息）：此处是运行前打印，此时还不知道是否会触发OOM备选，保留ARCH_NAME合理（表示"计划使用的架构"）。**可不改**。

改动量：+4行（L678和L894各+2行）

---

### Attack-5: run_dir用ARCH_NAME作为目录名，OOM备选时checkpoint路径与实际架构不符

**判定**：成立（轻微，预存问题，R4未覆盖）

**理由**：

经源代码验证：

**L426**：
```python
run_dir = Path(args.save_dir) / dataset / ARCH_NAME / f"seed{seed}"
```

确实使用ARCH_NAME而非arch_display。对比**L390**：
```python
arch_display = arch_override if arch_override else ARCH_NAME
```
和**L455**：
```python
info = { ... "arch": arch_display, ... }
```

若arch_override="resnet1d"（OOM Level 3）：
- checkpoint保存到`.../inceptiontime_lite/seed42/`（L426用ARCH_NAME）
- info["arch"]="resnet1d"（L455用arch_display）
- info["ckpt_path"]路径含"inceptiontime_lite"但info["arch"]="resnet1d"，路径与arch矛盾

**反方提到的覆盖风险**：若同一dataset/seed先用InceptionTime-Lite训练再用ResNet1D训练（如多次运行不同OOM级别），checkpoint会互相覆盖。此风险真实存在。

**影响评估合理**：反方承认"不在R4修复范围内（R4仅修transfer result dict），但属arch动态获取的未覆盖点"。定级轻微合理。

**修补方案**：

文件：`scripts/run_e5_inception_lite.py`
行号：L426
改动：改用arch_display

```python
# 修改前：
run_dir = Path(args.save_dir) / dataset / ARCH_NAME / f"seed{seed}"

# 修改后：
run_dir = Path(args.save_dir) / dataset / arch_display / f"seed{seed}"
```
改动量：1行替换

**注意**：此改动会改变checkpoint目录结构，若已有旧checkpoint需迁移或重跑。建议在R5修复时一并声明。

---

### Attack-6: bool字段写入CSV为"True"/"False"字符串，pandas类型推断不确定

**判定**：成立（轻微，预存问题）

**理由**：

反方对csv.DictWriter和pandas行为的描述技术上正确：
- Python csv模块：`str(True)="True"`, `str(False)="False"`
- pandas.read_csv对"True"/"False"字符串的类型推断确实版本相关
- 混合NaN时列推断为object(str)

**但需补充重要事实**：

1. **这是Python csv模块的标准行为**，非本项目特有bug。所有使用csv.DictWriter写入bool的Python项目都有此行为。

2. **R4确实使该问题更系统性**：R3的early-return dict无truncated/subspace_filtered字段（CSV空字符串），normal dict有（"True"/"False"）。R4统一后所有dict都有bool字段，列内纯度更高，pandas≥1.3更可能正确推断为bool。**实际上R4部分缓解了此问题**（列内纯度提升）。

3. **对分析的实际影响有限**：下游分析者可通过`df.skipped == 'True'`或`df.skipped.astype(bool)`显式转换，无需依赖pandas自动推断。

4. **反方未夸大严重度**：定级轻微合理，承认"不影响数据正确性，影响分析便利性"。

**修补方案**（可选）：

文件：`scripts/run_e5_inception_lite.py`
行号：L713（writer.writerow前）
改动：将bool转为int(0/1)写入

```python
# 修改前（L713-714）：
for r in transfer_results:
    writer.writerow(r)

# 修改后：
_bool_fields = {"truncated", "subspace_filtered", "skipped"}
for r in transfer_results:
    _row = {k: (int(v) if k in _bool_fields and isinstance(v, bool) else v) for k, v in r.items()}
    writer.writerow(_row)
```
改动量：+3行

**建议**：此为预存问题且影响轻微，可不在R5修复，但在CSV头注释中增加类型说明：
```python
f.write("# bool字段（truncated/subspace_filtered/skipped）写入为True/False字符串，pandas读取需astype(bool)\n")
```

---

### Attack-7: NaN写入CSV为"nan"字符串，R语言默认不识别

**判定**：成立（轻微，兼容性）

**理由**：

反方对NaN写入行为的描述技术上正确：
- Python `str(float("nan"))="nan"`
- pandas: 默认na_values包含"nan"→正确读为NaN ✅
- R read.csv: 默认na.strings="NA"→"nan"读为字符串 ⚠️

**但需补充重要事实**：

1. **R4改变NaN表示从空字符串到"nan"实际上是改进**：
   - R3的early-return dict无metric字段→CSV空字符串→pandas读为NaN，R读为空字符串
   - R4的early-return dict有float("nan")默认值→CSV"nan"→pandas读为NaN，R读为字符串"nan"
   - 对pandas用户：两种表示都正确读为NaN，无差异
   - 对R用户：两种表示都需手动处理（空字符串需na.strings=""，"nan"需na.strings="nan"），无本质差异

2. **本项目主要下游是pandas**：从代码可见（L898-908的汇总分析使用numpy/pandas），R兼容性非主要需求。

3. **反方未夸大严重度**：定级轻微合理，承认"不影响pandas分析，影响R/其他语言分析"。

**修补方案**（可选）：

若需R兼容，可将float("nan")改为"NA"字符串：
```python
# 在write_csv的row写入前转换
_nan_sentinel = "NA"  # R兼容的NA表示
for r in transfer_results:
    _row = {k: (_nan_sentinel if isinstance(v, float) and np.isnan(v) else v) for k, v in r.items()}
    writer.writerow(_row)
```

**建议**：此为兼容性问题且影响轻微，可不在R5修复，但在CSV头注释中增加说明：
```python
f.write("# 缺失metric字段写入为nan，pandas自动识别为NaN，R读取需na.strings='nan'\n")
```

---

### Attack-8: exception handler无法传递num_classes/subspace_filtered（main()作用域不可见）

**判定**：成立（轻微，作用域限制）

**理由**：

经源代码验证：

**L862-871**（main()中的except块）：
```python
except Exception as e:
    print(f"[ERROR] {source}→{target} seed={seed} 迁移失败: {e}")
    traceback.print_exc()
    transfer_results.append(_make_transfer_result(
        source=source, target=target, seed=seed,
        arch=trained_models[(source, seed)].get("arch", ARCH_NAME),
        error=str(e), skipped=True,
        # num_classes=0, subspace_filtered=False（默认）
    ))
```

**反方分析准确**：
1. num_classes在eval_transfer_pair的L501定义，是局部变量，main()无法访问
2. subspace_filtered在eval_transfer_pair内计算，main()无法访问
3. 此处是**作用域限制**而非遗漏——main()确实无法获取这些值

**但需补充重要事实**：

1. **此except块捕获的是eval_transfer_pair**未捕获的异常**（L856-861的try块）。eval_transfer_pair内部的early-return（FileNotFound/cal empty/ood empty）已通过return而非raise处理，不会触发此except块。

2. **触发此except块的异常类型**：eval_transfer_pair在L596-628的TS校准/metrics计算/benefit_inference阶段抛出的异常（如数值错误、benefit_inference失败未捕获的异常等）。此时num_classes和subspace_filtered已在eval_transfer_pair内计算，但无法传回main()。

3. **反方提出的改进方案合理**：eval_transfer_pair抛出自定义异常携带num_classes。但此改动较复杂，需定义新异常类并修改eval_transfer_pair的异常处理逻辑。

**影响评估合理**：反方承认"不影响运行时正确性（error/skipped标明失败），影响统计字段准确性"。定级轻微合理。

**修补方案**（可选，改动较大）：

文件：`scripts/run_e5_inception_lite.py`

**方案A**（自定义异常，推荐）：
```python
# 在文件顶部定义自定义异常
class TransferEvalError(Exception):
    def __init__(self, message, num_classes=0, subspace_filtered=False):
        super().__init__(message)
        self.num_classes = num_classes
        self.subspace_filtered = subspace_filtered

# 在eval_transfer_pair中，将可能触发main except的异常包装：
# 在L596（TS校准前）添加：
try:
    # L596-628 现有代码
    ...
except Exception as e:
    raise TransferEvalError(str(e), num_classes=num_classes,
                           subspace_filtered=bool(num_classes < max(...))) from e

# 在main() L862-871修改：
except TransferEvalError as e:
    transfer_results.append(_make_transfer_result(
        source=source, target=target, seed=seed,
        arch=trained_models[(source, seed)].get("arch", ARCH_NAME),
        num_classes=e.num_classes, subspace_filtered=e.subspace_filtered,
        error=str(e), skipped=True,
    ))
except Exception as e:
    # 未知异常，仍用默认值
    ...
```
改动量：+15行

**方案B**（在main()中预计算，简单但冗余）：
```python
# 在L855（for seed循环内）添加：
_num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])
_subspace_filtered = bool(_num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target]))
# L867-871使用这两个变量
```
改动量：+2行

**建议**：方案B更简单，虽与eval_transfer_pair内计算冗余，但能正确填充CSV字段。推荐R5采用方案B。

---

### Attack-9: cal/ood empty early-return未传n_ood，跳过实验的OOD样本数丢失

**判定**：成立（轻微，信息丢失）

**理由**：

经源代码验证：

**L573-581**（cal empty early-return）：
```python
return _make_transfer_result(
    source=source, target=target, seed=seed,
    arch=source_info.get("arch", ARCH_NAME),
    num_classes=num_classes,
    n_dropped_cal=int(n_dropped_cal), n_dropped_ood=int(n_dropped_ood),
    truncated=True,
    subspace_filtered=bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
    error="cal set empty after truncation", skipped=True,
    # 未传 n_ood（默认0）
)
```

确实未传n_ood。此时n_ood默认为0。

**反方分析准确**：
1. **L518** `tgt_eval = evaluate(...)` 在L570的cal empty检查**之前**已执行
2. **L519** `ood_probs = tgt_eval["probs"]` 已有值
3. **L536** ood_probs已截断（`ood_probs = ood_probs[ood_keep][:, :num_classes]`）
4. **L566** ood_probs已归一化（`ood_probs = ood_probs / ood_row_sums`）
5. 在L573 cal empty检查时，`int(len(ood_probs))`是可用的，反映截断后的OOD样本数

**cal empty vs ood empty区分**：
- **cal empty**（L570-581）：cal集截断后为空，但ood集可能非空（有OOD样本但无法校准）→ n_ood=0误导（实际有OOD样本）
- **ood empty**（L582-593）：ood集确实为空 → n_ood=0正确（len(ood_probs)==0）

**反方仅指出cal empty场景需修复是准确的**。ood empty场景n_ood=0本就正确。

**影响评估合理**：反方承认"不影响运行时，影响根因分析"。定级轻微合理。

**修补方案**：

文件：`scripts/run_e5_inception_lite.py`
行号：L573-581（cal empty early-return）
改动：补传n_ood

```python
# 修改前（L573-581）：
return _make_transfer_result(
    source=source, target=target, seed=seed,
    arch=source_info.get("arch", ARCH_NAME),
    num_classes=num_classes,
    n_dropped_cal=int(n_dropped_cal), n_dropped_ood=int(n_dropped_ood),
    truncated=True,
    subspace_filtered=bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
    error="cal set empty after truncation", skipped=True,
)

# 修改后：
return _make_transfer_result(
    source=source, target=target, seed=seed,
    arch=source_info.get("arch", ARCH_NAME),
    num_classes=num_classes,
    n_ood=int(len(ood_probs)),  # 补传：截断后OOD样本数
    n_dropped_cal=int(n_dropped_cal), n_dropped_ood=int(n_dropped_ood),
    truncated=True,
    subspace_filtered=bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
    error="cal set empty after truncation", skipped=True,
)
```
改动量：+1行

**注**：L585-593（ood empty）无需修改，因len(ood_probs)==0时n_ood=0本就正确。

---

## 7个攻击维度审查结论

| 维度 | 反方结论 | 反反方验证 |
|------|---------|-----------|
| 1. 反例构造 | Attack-1：ptbxl→cpsc + cpsc缺失反例 | **确认成立**，num_classes=0（应=4）反例可构造 |
| 2. 逻辑断链 | Attack-2：schema分离维护无自动校验 | **确认成立**，当前一致但无校验保证未来一致性 |
| 3. 隐含假设 | Attack-3：extrasaction="ignore"隐含假设多余字段可安全丢弃 | **部分成立**，场景1不成立（混淆train_single和transfer result dict），场景2成立但与Attack-2同源 |
| 4. 边界失效 | Attack-8：exception handler作用域限制 | **确认成立**，num_classes是eval_transfer_pair局部变量 |
| 5. 自相矛盾 | Attack-4：CSV头注释arch=inceptiontime_lite vs 数据列arch=resnet1d | **确认成立**，L678/L894确实未改为动态 |
| 6. 量级错误 | 未发现 | **确认无量级错误**，22=22字段一致 |
| 7. 语义偏移 | Attack-9：n_ood=0在cal empty场景语义偏移 | **确认成立**，cal empty时ood集可能非空 |

---

## R4修复逐项评价验证

| R4修复项 | 对应R3攻击 | 反方评价 | 反反方验证 |
|---------|-----------|---------|-----------|
| TRANSFER_RESULT_FIELDS常量 | Attack-1 | 有效 | **确认有效**，22字段覆盖完整，与_make_transfer_result一致 |
| _make_transfer_result函数 | Attack-1/4/6/7 | 有效 | **确认有效**，5处构造点统一调用，默认值机制自动补齐 |
| extrasaction="ignore" | Attack-1 | 有效但有副作用 | **确认有效**，消除崩溃；副作用（静默丢弃）需配合Attack-2校验消解 |
| arch动态获取 | Attack-2 | 有效 | **确认有效**，5处均用source_info.get("arch", ARCH_NAME)；但L426/L678/L759/L894四处未覆盖（Attack-4/5） |

---

## 总结

### 攻击点统计

| 严重度 | 数量 | 攻击点 |
|--------|------|--------|
| 致命 | 0 | — |
| 严重 | 0 | — |
| 中等 | 2 | Attack-1（FileNotFound未传num_classes/subspace_filtered）、Attack-2（schema分离维护风险） |
| 轻微 | 7 | Attack-3（extrasaction副作用，部分成立）、Attack-4（头注释未同步）、Attack-5（run_dir未同步）、Attack-6（bool写入）、Attack-7（NaN写入）、Attack-8（exception作用域）、Attack-9（n_ood丢失） |
| **总计** | **9** | |

### 需R5修复的必修项清单（按优先级排序）

| 优先级 | 攻击点 | 文件 | 行号 | 改动内容 | 改动量 |
|--------|--------|------|------|---------|--------|
| 中等 | Attack-1 | scripts/run_e5_inception_lite.py | L510-514 | FileNotFound early-return补传num_classes和subspace_filtered | +2行 |
| 中等 | Attack-2 | scripts/run_e5_inception_lite.py | L214后 | 增加schema一致性运行时校验（set(_result.keys()) == set(TRANSFER_RESULT_FIELDS)） | +3行 |
| 轻微 | Attack-9 | scripts/run_e5_inception_lite.py | L573-581 | cal empty early-return补传n_ood=int(len(ood_probs)) | +1行 |
| 轻微 | Attack-4 | scripts/run_e5_inception_lite.py | L678/L894 | CSV头注释和汇总报告改为动态arch集合 | +4行 |
| 轻微 | Attack-5 | scripts/run_e5_inception_lite.py | L426 | run_dir改用arch_display | 1行替换 |

**必修合计**：5项，约+11行改动

### 可选改进项（建议但不阻塞R5通过）

| 优先级 | 攻击点 | 改进内容 | 改动量 | 理由 |
|--------|--------|---------|--------|------|
| 轻微 | Attack-3 | 与Attack-2合并修补，无需独立改动 | 0行 | 场景2与Attack-2同源，场景1不成立 |
| 轻微 | Attack-6 | CSV头注释增加bool字段类型说明 | +1行 | 预存问题，影响轻微，pandas用户可通过astype(bool)处理 |
| 轻微 | Attack-7 | CSV头注释增加NaN表示说明 | +1行 | 预存问题，影响轻微，本项目主要下游是pandas |
| 轻微 | Attack-8 | main()中预计算num_classes/subspace_filtered | +2行 | 作用域限制，方案B简单但冗余；error/skipped已标明失败，影响有限 |

### 可关闭的攻击点及理由

| 攻击点 | 关闭理由 |
|--------|---------|
| Attack-3（部分成立） | 场景1不成立（反方混淆train_single返回dict和transfer result dict两个独立schema）；场景2与Attack-2同源，修补Attack-2后自动消解。无需独立修补。 |

### 对R4修复质量的总体评价

**R4修复成功且高质量**：

1. **R3遗留的全部关键问题已彻底修复**：
   - R3-Attack-1（致命，CSV schema不一致导致DictWriter崩溃）：TRANSFER_RESULT_FIELDS + _make_transfer_result + extrasaction="ignore"三层防御，**致命缺陷已消除** ✅
   - R3-Attack-2（严重，arch硬编码）：5处transfer result dict均改用source_info.get("arch", ARCH_NAME)动态获取，**严重缺陷已修复** ✅
   - R3-Attack-4/6/7（中等/轻微，字段缺失）：_make_transfer_result默认值机制自动补齐，**已合并修复** ✅

2. **R4引入的新问题均为中等或轻微，无致命或严重**：
   - 2个中等攻击（Attack-1/2）是**完整性不足**和**维护性风险**，非运行时错误
   - 7个轻微攻击中，4个是**预存问题**（Attack-4/5/6/7），R4未引入但也未修复；2个是**R4副效应**（Attack-3/9），属设计权衡；1个是**作用域限制**（Attack-8），非R4引入

3. **反方攻击质量高，无稻草人论证**：
   - 9个攻击点中8个完全成立，1个部分成立（Attack-3场景1不成立但场景2成立）
   - 反方行号引用准确，代码片段与源文件一致，反例可构造
   - 反方严重度定级合理，未夸大（无致命/严重，2中等+7轻微）

4. **R4修复的工程质量值得肯定**：
   - TRANSFER_RESULT_FIELDS常量定义 + _make_transfer_result辅助函数的设计模式正确
   - 22字段逐字段一致，5处构造点统一调用
   - 注释清晰（L135-141说明修复目标，L180-189 docstring说明修复机制）
   - 三层防御（统一schema + 固定fieldnames + extrasaction安全网）设计合理

**判定**：R4修复**有效、完整、高质量**。R3终审裁决的P0-致命（Attack-1）和P0-严重（Attack-2）均已彻底消除，无新致命/严重问题引入。剩余9个攻击点均为中等或轻微，建议R5轮修补5项必修（约11行改动），但不影响R4通过。

### R5修复优先级

**Attack-1 > Attack-2 > Attack-9 > Attack-4 > Attack-5**

1. **Attack-1**（+2行）：FileNotFound补传num_classes/subspace_filtered，消除CSV统计字段失真
2. **Attack-2**（+3行）：schema一致性校验，消除静默数据丢失风险（同时消解Attack-3）
3. **Attack-9**（+1行）：cal empty补传n_ood，消除OOD样本数信息丢失
4. **Attack-4**（+4行）：CSV头注释/汇总报告改动态arch，消除头注释-数据列矛盾
5. **Attack-5**（1行替换）：run_dir改用arch_display，消除checkpoint路径-arch矛盾

**预期R5轮可完全收敛**：5项必修约11行改动，均为明确的代码改动（补传参数+加校验+改字符串），无设计层面分歧。R5修复后P0-6+7的P0-致命/P0-严重/P0-中等攻击点均可清零，仅剩P0-轻微建议项（可选）。

---

## 对抗透明性记录

### 反方攻击质量评价

| 维度 | 评价 |
|------|------|
| 行号准确性 | **高**：9个攻击点行号引用全部准确（grep + read双重验证） |
| 代码片段一致性 | **高**：反方引用的代码片段与源文件完全一致 |
| 反例可构造性 | **高**：8个成立攻击的反例均可实际构造 |
| 严重度定级 | **合理**：无致命/严重，2中等+7轻微，未夸大 |
| 稻草人论证 | **1处**：Attack-3场景1混淆train_single返回dict和transfer result dict（已标注） |
| 总体 | **高质量**，对抗实质性，无臆测 |

### 反反方审查立场声明

本报告基于源代码逐行验证，未轻信反方声称。对每个攻击点：
1. 用read工具读取源文件相关行号，确认代码事实
2. 用grep工具验证字段数/构造点数/ARCH_NAME使用点
3. 对反方引用的代码片段逐字比对
4. 对反方构造的反例评估可构造性
5. 对反方的严重度定级独立评估，未盲目接受

审查过程中发现1处反方论证不严谨（Attack-3场景1混淆两个独立schema），已明确标注。其余8个攻击点反方论证严谨，判定成立。
