# P0-6+7 R5反反方审查报告

## 审查概要
- 审查攻击点数：13
- 真攻击数：3（Attack-4, Attack-5, Attack-13）
- 伪攻击数：5（Attack-2, Attack-8, Attack-9, Attack-10, Attack-12）
- 部分成立数：5（Attack-1, Attack-3, Attack-6, Attack-7, Attack-11）
- 需R6修复数：6（Attack-1, Attack-3, Attack-4+5合并, Attack-6, Attack-7, Attack-13）

### 裁决统计
| 裁决类型 | 数量 | 攻击点 |
|---------|------|--------|
| 真攻击（需R6修复） | 3 | Attack-4, Attack-5, Attack-13 |
| 伪攻击（驳回） | 5 | Attack-2, Attack-8, Attack-9, Attack-10, Attack-12 |
| 部分成立（降级修复） | 5 | Attack-1, Attack-3, Attack-6, Attack-7, Attack-11 |

### 严重度校正
| 攻击点 | R5标注 | 审查后 | 校正理由 |
|--------|--------|--------|---------|
| Attack-1 | 严重 | 轻微 | skipped=True已标记，下游应过滤 |
| Attack-2 | 严重 | 驳回 | num_classes是配置元数据非统计量 |
| Attack-3 | 严重 | 轻微 | 项目无python -O使用证据 |
| Attack-4 | 严重 | 中等 | 事实错误属实但skipped=True标记 |
| Attack-5 | 严重 | 中等 | Attack-4的衍生，修复Attack-4即解决 |
| Attack-6 | 严重 | 轻微 | CSV arch列已记录实际架构 |
| Attack-7 | 严重 | 轻微 | R4 OOM备选为死代码，无实际checkpoint |
| Attack-13 | 轻微 | 轻微 | 维持原判 |

---

## 逐条审查

### Attack-1 [严重→轻微] subspace_filtered=True语义错误——无过滤发生却报True

- **判定**：部分成立（严重度被高估，应为轻微）
- **验证**：
  - L525代码确认：`subspace_filtered=bool(_fnf_num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target]))`
  - L513 `build_dataset(target, ...)`抛FileNotFoundError时，目标数据集未加载，subspace过滤操作（L509 `subspace = SUBSPACE_CPSC if num_classes == 4 else None`）虽计算了subspace变量，但build_dataset从未成功执行，过滤未发生
  - 正常路径L668的subspace_filtered含义是"实际触发了5→4子空间过滤"，FileNotFound路径无过滤却报True，语义确实偏移
  - **但**：skipped=True已明确标记该行为无效实验，任何合理的下游分析应先过滤skipped行再统计subspace_filtered
- **反驳理由（降级部分）**：
  1. skipped=True是明确的"无效行"标记，subspace_filtered=True仅在不过滤skipped行时才产生误导
  2. subspace_filtered是布尔字段，不影响任何数值统计的准确性
  3. 实际危害场景极窄：需下游既不过滤skipped行又按subspace_filtered分组统计——属不合理使用模式
- **修补方案**（语义正确性改进，优先级低）：
  - 文件：`scripts/run_e5_inception_lite.py`
  - 行号：L525
  - 改动：`subspace_filtered=bool(_fnf_num_classes < max(...))` → `subspace_filtered=False`
  - 理由：FileNotFound时无过滤发生，应报False

---

### Attack-2 [严重→驳回] FileNotFound路径skipped=True与num_classes/subspace_filtered有效值自相矛盾

- **判定**：伪攻击（稻草人论证——将配置元数据误归类为统计结果）
- **验证**：
  - L520: `_fnf_num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])`
  - L508（正常路径）: `num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])`
  - **关键发现**：正常路径和FileNotFound路径的num_classes计算公式完全相同，均从DATASET_NUM_CLASSES配置常量派生，非从数据集实际测量
  - subspace_filtered同理：L525和L668公式相同，均从配置派生
  - 真正的统计量（ood_acc_raw, ood_ece_raw, fitted_T等）在FileNotFound路径正确填NaN
- **反驳理由**：
  1. **num_classes和subspace_filtered是配置元数据（实验参数），非实验统计结果**。它们描述"实验试图做什么"，而非"实验得到了什么"。在正常路径中也是从DATASET_NUM_CLASSES配置计算，不从数据集测量
  2. skipped=True与配置元数据的有效值**不矛盾**：skipped表示"实验未完成"，num_classes=4表示"本实验配置为4类目标"——两者描述不同维度
  3. 真正的矛盾应是"skipped=True且ood_acc_raw=85.0"（跳过了却有有效精度）——但R5正确地将统计量填NaN，无此矛盾
  4. 在skipped行保留配置元数据有助于调试（知道尝试了什么source→target组合），是合理的设计选择
  5. 反方将配置参数误归类为"统计字段"，构造了虚假的矛盾——稻草人论证
- **结论**：驳回，无需修复

---

### Attack-3 [严重→轻微] schema assert在python -O模式下被完全禁用，生产环境无保护

- **判定**：部分成立（技术事实正确但严重度被高估，应为轻微）
- **验证**：
  - L217-218代码确认：`assert set(result.keys()) == set(TRANSFER_RESULT_FIELDS), ...`
  - Python文档确认：`python -O`移除assert语句，`python -OO`移除assert和docstring——技术事实正确
  - **但**：grep搜索整个项目未发现任何`python -O`或`python -OO`的使用证据
  - 文档用法示例（L42-43）：`python scripts/run_e5_inception_lite.py`——无-O标志
  - 本项目是科研实验脚本（非高并发生产服务），无使用-O优化模式的动机
- **反驳理由（降级部分）**：
  1. **项目无python -O使用证据**：这是理论风险非实际风险
  2. schema校验本质是**开发时安全网**（防止开发者修改_make_transfer_result时忘记同步TRANSFER_RESULT_FIELDS），非生产时运行时检查
  3. TRANSFER_RESULT_FIELDS和_make_transfer_result在同一文件L142-219，物理距离<80行，维护时很难不同步
  4. 即使在-O模式下schema不一致，csv.DictWriter(extrasaction="ignore")也只是丢弃多余字段——不会崩溃或 corrupt 已有数据
- **修补方案**（代码健壮性改进，优先级低）：
  - 文件：`scripts/run_e5_inception_lite.py`
  - 行号：L217-218
  - 改动：
    ```python
    # 原：
    assert set(result.keys()) == set(TRANSFER_RESULT_FIELDS), \
        f"Schema mismatch: {set(result.keys())} != {set(TRANSFER_RESULT_FIELDS)}"
    # 改为：
    _actual_keys = set(result.keys())
    _expected_keys = set(TRANSFER_RESULT_FIELDS)
    if _actual_keys != _expected_keys:
        raise RuntimeError(
            f"Schema mismatch: {_actual_keys} != {_expected_keys}"
        )
    ```
  - 理由：if/raise不受-O影响，但当前无实际风险

---

### Attack-4 [严重→中等] cal empty路径n_ood=0在ood_probs非空时事实错误

- **判定**：真攻击（事实错误属实，严重度从严重降为中等）
- **验证**：
  - L583: `if len(cal_probs) == 0:` — 检查cal是否为空
  - L592: `n_ood=0` — 硬编码为0
  - L538-549: cal和ood**独立截断**（cal_keep和ood_keep是分别计算的布尔掩码）
  - L567-579: ood零行过滤在cal空检查之前完成，但ood的空检查在L598（cal空返回之后）
  - **确认**：L583时ood_probs已截断+零行过滤，但可能非空（如100个样本），n_ood=0是事实错误
  - 正常路径L653: `n_ood=int(len(ood_probs))` — n_ood语义是"ood样本数"
  - cal empty路径将n_ood从"ood样本数"偏移为"有效评估数"——语义偏移属实
- **降级理由**：
  1. skipped=True和error="cal set empty after truncation"已明确标记该行状态
  2. 下游若过滤skipped行则无影响；若不过滤，n_ood=0低估但不崩溃
  3. 影响范围限于"cal空但ood非空"的边界场景（需5→4迁移且cal标签全≥4但ood标签有<4的）
- **修补方案**（必修，优先级中）：
  - 文件：`scripts/run_e5_inception_lite.py`
  - 行号：L592
  - 改动：`n_ood=0,` → `n_ood=int(len(ood_probs)),`
  - 理由：n_ood应反映实际ood样本数，即使TS校准跳过

---

### Attack-5 [严重→中等] cal empty与ood empty路径n_ood=0语义不一致

- **判定**：真攻击（Attack-4的衍生攻击，修复Attack-4即自动解决）
- **验证**：
  - L592（cal empty）: `n_ood=0` 显式传0
  - L601-609（ood empty）: n_ood未传，默认0（_make_transfer_result签名L162: `n_ood: int = 0`）
  - cal empty时ood_probs可能非空（100样本），n_ood=0错误
  - ood empty时ood_probs确实为空（0样本），n_ood=0正确
  - 两条路径n_ood值相同但含义不同——语义不一致属实
- **修补方案**：修复Attack-4后自动解决
  - Attack-4修复后：cal empty路径n_ood=int(len(ood_probs))（可能=100），ood empty路径n_ood=0（确实为空）
  - 两条路径n_ood值不同，下游可通过n_ood区分——语义一致
- **结论**：随Attack-4一并修复，无需额外改动

---

### Attack-6 [严重→轻微] 多架构混合时CSV头注释取train_results[0]不准确

- **判定**：部分成立（问题属实但严重度被高估，应为轻微）
- **验证**：
  - L911: `_csv_arch_display = train_results[0].get("arch", ARCH_NAME) if train_results else ARCH_NAME`
  - L820-835: `_train_adapter`在per-(dataset, seed)循环中调用，不同实验可能触发不同OOM级别
  - L265-270: Level 3备选用`arch: "resnet1d"`——不同实验可能用不同arch
  - **确认**：多架构混合时train_results[0]只反映首个实验的arch，头注释不准确
  - **但**：L462训练结果dict中`"arch": arch_display`——CSV训练结果表有arch列记录每个实验的实际架构
  - L728-730: 迁移结果也用TRANSFER_RESULT_FIELDS含arch列
- **反驳理由（降级部分）**：
  1. **CSV数据列已正确记录每个实验的arch**——头注释只是注释，非数据源
  2. 审稿人复现实验应读CSV的arch列而非头注释——头注释是概览非精确记录
  3. 头注释写"架构: inceptiontime_lite"在多架构混合时不准确，但CSV的arch列会显示"resnet1d"——任何认真阅读CSV的人都能发现
  4. "可复现性受损"被夸大——可复现性依赖CSV数据列（有arch列），不依赖头注释
- **修补方案**（改进头注释准确性，优先级低）：
  - 文件：`scripts/run_e5_inception_lite.py`
  - 行号：L911
  - 改动：
    ```python
    # 原：
    _csv_arch_display = train_results[0].get("arch", ARCH_NAME) if train_results else ARCH_NAME
    # 改为：
    _unique_archs = sorted(set(r.get("arch", ARCH_NAME) for r in train_results)) if train_results else [ARCH_NAME]
    _csv_arch_display = _unique_archs[0] if len(_unique_archs) == 1 else f"混合({','.join(_unique_archs)})"
    ```
  - 理由：多架构时头注释明确标注"混合"

---

### Attack-7 [严重→轻微] run_dir改arch_display破坏R4 resnet1d checkpoint路径兼容性

- **判定**：部分成立（兼容性理论存在但前提不成立，应为轻微）
- **验证**：
  - R5 L433: `run_dir = Path(args.save_dir) / dataset / arch_display / f"seed{seed}"`
  - arch_display="resnet1d"时路径为`.../dataset/resnet1d/seed{seed}`
  - R4用ARCH_NAME，路径为`.../dataset/inceptiontime_lite/seed{seed}`
  - **关键发现**：L817-818注释——"P0-6 修复：通过 try_train_with_oom_fallback 激活 4 级 OOM 备选链（原代码直接调用 train_single，导致 OOM 备选链成为死代码）"
  - L336-337注释——"F1 修复：原代码计算了 block_layers 但未使用...导致 depth=3/5/7 三个变体全部退化为同一默认配置，等同 Level 4 死代码"
  - **R4的OOM备选链是死代码**：原代码直接调用train_single，try_train_with_oom_fallback从未被调用，Level 3从未触发
  - 即使P0-6修复激活了OOM备选链，F1修复前Level 3的三个ResNet1D变体全部退化为同一默认配置
  - **结论**：R4从未成功保存过有效的resnet1d checkpoint——兼容性问题的前提（"R4已保存resnet1d checkpoint"）不成立
- **反驳理由（降级部分）**：
  1. **R4的OOM备选链是死代码**（L817-818明确注释），Level 3从未触发，无resnet1d checkpoint被保存
  2. 即使P0-6修复在R4前已应用，F1修复前Level 3退化为默认配置——保存的也不是真正的resnet1d变体
  3. 本实验需30-45 GPU小时，代码仍在R5审查迭代中——极不可能有用户已用R4完成完整训练
  4. 反方假设"R4已保存resnet1d checkpoint"缺乏证据——超出适用范围
- **修补方案**（防御性兼容警告，优先级低）：
  - 文件：`scripts/run_e5_inception_lite.py`
  - 行号：L433后
  - 改动：添加旧路径兼容检查
    ```python
    run_dir = Path(args.save_dir) / dataset / arch_display / f"seed{seed}"
    # R6兼容: 若新路径不存在但旧ARCH_NAME路径有checkpoint，打印迁移警告
    if arch_display != ARCH_NAME:
        _old_ckpt = Path(args.save_dir) / dataset / ARCH_NAME / f"seed{seed}" / "best_model.pt"
        if _old_ckpt.exists() and not (run_dir / "best_model.pt").exists():
            print(f"[WARN] 发现旧路径checkpoint {_old_ckpt}，R5已迁移到 {run_dir}，需手动迁移或重新训练")
    ```

---

### Attack-8 [轻微→驳回] FileNotFound路径num_classes为假设值非实际值

- **判定**：伪攻击（超出适用范围——将配置常量误认为测量值）
- **验证**：
  - L520: `_fnf_num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])`
  - L508（正常路径）: `num_classes = min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])`
  - **关键发现**：正常路径和FileNotFound路径的num_classes计算方式**完全相同**，均从DATASET_NUM_CLASSES配置常量派生
  - DATASET_NUM_CLASSES = {"ptbxl": 5, "chapman": 5, "cpsc": 4}（L123）——这是硬编码配置，非从数据集测量
  - 正常路径中num_classes也从未"从数据集实际测量类数"——它始终来自配置
- **反驳理由**：
  1. **num_classes在所有路径中都是配置派生值**，不存在"实际值"vs"假设值"的区分
  2. 正常路径L508也是`min(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])`——与FileNotFound路径L520完全相同
  3. 反方声称"目标数据集不存在，4是理论值非实际值"——但即使目标数据集存在，num_classes也是从DATASET_NUM_CLASSES配置读取的，不从数据集测量
  4. DATASET_NUM_CLASSES是项目的类数定义（source of truth），不存在比它更"实际"的值
  5. 反方构造了"实际值vs理论值"的虚假对立——超出适用范围
- **结论**：驳回，无需修复

---

### Attack-9 [轻微→驳回] assert每次调用重复构造set，性能微优化空间

- **判定**：伪攻击（量级错误——反方自认性能影响可忽略）
- **验证**：
  - L217: `assert set(result.keys()) == set(TRANSFER_RESULT_FIELDS), ...`
  - 每次调用_make_transfer_result都构造两个set
  - 反方自述："性能影响可忽略"——30次set构造，O(660)操作，相对训练时间（30-45小时）是纳秒级
- **反驳理由**：
  1. **反方自认"性能影响可忽略"**——这不构成"攻击"，是代码风格建议
  2. 30次set构造的耗时远小于一次磁盘IO——优化无实际意义
  3. 预构造`_TRANSFER_RESULT_FIELDS_SET`会引入模块级额外变量，增加代码复杂度——反而降低可读性
  4. assert的本意是开发时校验，性能不是设计目标
  5. 反方将代码风格建议包装为"攻击"——量级错误
- **结论**：驳回，无需修复

---

### Attack-10 [轻微→驳回] assert仅覆盖_make_transfer_result内部，外部构造无保护

- **判定**：伪攻击（逻辑断链——假设未来违规，当前无风险）
- **验证**：
  - L217: assert在_make_transfer_result函数内部
  - grep确认5处调用：L521/L588/L601/L649/L886——所有transfer result构造点都用_make_transfer_result
  - 反方自述："当前所有5处transfer result构造点都用_make_transfer_result，覆盖完整"和"当前无风险"
  - 反方承认这是"未来维护需约束"——非当前bug
- **反驳理由**：
  1. **反方自认"当前无风险"**——这不构成当前攻击，是未来维护建议
  2. 当前所有5处构造点都被assert覆盖——保护完整
  3. "若未来有人绕过_make_transfer_result直接构造dict"是假设性未来违规——不能据此判定当前代码有bug
  4. 任何函数的内部校验都只能覆盖经该函数的路径——这是函数封装的固有特性，非缺陷
  5. 防止未来违规应靠代码规范/CR，而非在当前代码中添加不可能触发的校验
- **结论**：驳回，无需修复

---

### Attack-11 [轻微→部分成立] 空train_results回退ARCH_NAME但实际无模型

- **判定**：部分成立（技术属实但危害可忽略）
- **验证**：
  - L911: `_csv_arch_display = train_results[0].get("arch", ARCH_NAME) if train_results else ARCH_NAME`
  - train_results为空时回退ARCH_NAME="inceptiontime_lite"
  - L836-840: model is None时不append到train_results——全部OOM降级时train_results为空
  - **但**：L862 `if not args.no_transfer and len(trained_models) > 0:`——无训练模型时不执行迁移
  - 此时transfer_results也为空，CSV只有头注释无数据行
- **反驳理由（降级部分）**：
  1. train_results为空时CSV**无任何数据行**——头注释写什么都不影响数据
  2. 头注释是"无数据CSV的标签"——无实际误导对象
  3. 反方自认"CSV几乎无内容"——危害可忽略
  4. 此场景需所有15个训练实验全部OOM降级——极端边界情况
- **修补方案**：不值得R6修复（投入产出比极低），如需修复可随Attack-6一并处理
- **结论**：部分成立，不单独修复

---

### Attack-12 [轻微→驳回] arch_display未校验为合法路径组件

- **判定**：伪攻击（边界失效——假设未来违规，当前安全）
- **验证**：
  - L395: `arch_display = arch_override if arch_override else ARCH_NAME`
  - L433: `run_dir = Path(args.save_dir) / dataset / arch_display / f"seed{seed}"`
  - 当前arch_override只有"resnet1d"和None（L265-270）
  - ARCH_NAME="inceptiontime_lite"（L105）
  - **两者都是合法路径组件**——反方自认"当前安全"
- **反驳理由**：
  1. **反方自认"当前安全"**——这不构成当前攻击，是未来维护建议
  2. arch_display的取值范围由try_train_with_oom_fallback的levels列表（L260-271）严格控制——只有"resnet1d"和None
  3. "若未来arch_override含特殊字符"是假设性未来扩展——不能据此判定当前代码有bug
  4. Python的Path/操作符会自动处理大部分路径组件——"resnet1d"和"inceptiontime_lite"无需校验
  5. 添加路径合法性校验属过度防御——当前取值范围已保证安全
- **结论**：驳回，无需修复

---

### Attack-13 [轻微] main()启动日志用ARCH_NAME与run_dir用arch_display不一致

- **判定**：真攻击（不一致属实，严重度维持轻微）
- **验证**：
  - L778-779: `print(f"# 架构: {ARCH_NAME} (3 blocks, n_filters={args.n_filters}, ...")` — 用ARCH_NAME
  - L433: `run_dir = Path(args.save_dir) / dataset / arch_display / f"seed{seed}"` — 用arch_display
  - L919: `print(f"架构: {ARCH_NAME}")` — 用ARCH_NAME
  - L397（per-experiment）: `print(f"[训练] {dataset} seed={seed} arch={arch_display} ...")` — 用arch_display
  - **确认**：启动日志L778和汇总报告L919用ARCH_NAME，run_dir和per-experiment日志用arch_display
  - OOM触发时：启动日志打印"inceptiontime_lite"，但checkpoint存到"resnet1d"目录——不一致属实
- **降级理由**：
  1. 启动日志L778在训练前打印，此时不知OOM是否触发——描述的是**意图配置**非实际配置
  2. per-experiment日志L397用arch_display，正确反映每次训练的实际架构
  3. CSV的arch列正确记录每个实验的实际架构
  4. 不影响功能，仅影响调试可读性
- **修补方案**（改进日志一致性，优先级低）：
  - 文件：`scripts/run_e5_inception_lite.py`
  - 行号：L919
  - 改动：
    ```python
    # 原：
    print(f"架构: {ARCH_NAME}")
    # 改为：
    _summary_archs = sorted(set(r.get("arch", ARCH_NAME) for r in train_results)) if train_results else [ARCH_NAME]
    print(f"架构: {','.join(_summary_archs)}")
    ```
  - 注：L778启动日志保持ARCH_NAME（因训练前不知实际arch，描述意图配置合理）

---

## R6修复清单

| 优先级 | 攻击点 | 文件 | 行号 | 改动内容 | 改动量 | 理由 |
|--------|--------|------|------|---------|--------|------|
| **中** | Attack-4+5 | run_e5_inception_lite.py | L592 | `n_ood=0` → `n_ood=int(len(ood_probs))` | 1行 | 事实错误：cal空时ood可能非空，n_ood应反映实际ood样本数 |
| **低** | Attack-1 | run_e5_inception_lite.py | L525 | `subspace_filtered=bool(...)` → `subspace_filtered=False` | 1行 | 语义正确性：FileNotFound时无过滤发生 |
| **低** | Attack-3 | run_e5_inception_lite.py | L217-218 | `assert ...` → `if ...: raise RuntimeError(...)` | 2行 | 健壮性：if/raise不受-O影响（当前无-O使用但属最佳实践） |
| **低** | Attack-6 | run_e5_inception_lite.py | L911 | 收集unique archs，多架构时标注"混合" | 3行 | 头注释准确性：多架构混合时反映实际 |
| **低** | Attack-7 | run_e5_inception_lite.py | L433后 | 添加旧路径checkpoint兼容警告 | 5行 | 迁移友好性：R4旧路径checkpoint存在时警告 |
| **低** | Attack-13 | run_e5_inception_lite.py | L919 | 汇总报告用动态arch | 2行 | 日志一致性：汇总报告反映实际架构 |

### 修复优先级说明
- **中优先级**：Attack-4+5是唯一的事实错误（n_ood=0 vs 实际ood样本数），应优先修复
- **低优先级**：Attack-1/3/6/7/13均为语义改进/健壮性/一致性改进，不影响核心功能，可在R6轮一并处理

### 不修复清单（驳回）
| 攻击点 | 驳回理由 |
|--------|---------|
| Attack-2 | num_classes/subspace_filtered是配置元数据非统计量，skipped=True与配置参数不矛盾 |
| Attack-8 | num_classes在所有路径均从DATASET_NUM_CLASSES配置派生，无"实际vs假设"区分 |
| Attack-9 | 反方自认性能影响可忽略，非bug属代码风格建议 |
| Attack-10 | 反方自认当前无风险，所有5处构造点已被assert覆盖 |
| Attack-11 | train_results为空时CSV无数据行，头注释无误导对象（随Attack-6一并处理） |
| Attack-12 | 反方自认当前安全，arch_display取值由代码严格控制 |

---

## 7个攻击维度审查结论

| 维度 | 反方主张 | 反反方裁决 |
|------|---------|-----------|
| 1. 反例构造 | Attack-1/4/6构造反例 | Attack-4反例成立（n_ood=0事实错误）；Attack-1反例成立但危害窄；Attack-6反例成立但CSV arch列已记录实际 |
| 2. 逻辑断链 | Attack-10 assert覆盖范围 | 驳回——当前5处构造点全覆盖，无逻辑断链 |
| 3. 隐含假设 | Attack-3/6/7隐含假设 | Attack-3隐含假设"不用-O"成立（项目无-O证据）；Attack-6隐含假设"同arch"部分成立；Attack-7隐含假设"无R4旧checkpoint"成立（R4 OOM为死代码） |
| 4. 边界失效 | Attack-7/11/12边界 | Attack-7前提不成立（R4无resnet1d checkpoint）；Attack-11边界成立但CSV空；Attack-12当前安全 |
| 5. 自相矛盾 | Attack-2/5/13矛盾 | Attack-2驳回（配置元数据非统计量）；Attack-5成立（Attack-4衍生）；Attack-13成立（日志不一致） |
| 6. 量级错误 | Attack-9性能 | 驳回——反方自认可忽略 |
| 7. 语义偏移 | Attack-1/4/8语义 | Attack-1部分成立（subspace_filtered语义）；Attack-4成立（n_ood语义偏移）；Attack-8驳回（无实际vs假设区分） |

---

## 结论

### R5修复是否通过？

**有条件通过**——R5修复方向全部正确，5项修复中：
- 3项修复完全有效（Attack-2 schema assert开发时有效 / Attack-4 CSV头注释单架构正确 / Attack-5 run_dir消除覆盖bug）
- 2项修复引入了1个事实错误（Attack-9修复中n_ood=0在ood_probs非空时错误）

### 裁决汇总
- **真攻击3个**：Attack-4（n_ood事实错误，中等）+ Attack-5（Attack-4衍生，中等）+ Attack-13（日志不一致，轻微）
- **伪攻击5个**：Attack-2/8/9/10/12——基于错误假设/自认无风险/配置元数据误归类
- **部分成立5个**：Attack-1/3/6/7/11——问题属实但严重度被高估

### R6修复建议
1. **必修1项**（中优先级）：Attack-4+5合并修复，L592改`n_ood=int(len(ood_probs))`，1行改动
2. **选修5项**（低优先级）：Attack-1/3/6/7/13，语义/健壮性/一致性改进，共约13行改动
3. **驳回6项**：Attack-2/8/9/10/11/12，无需修复

### 对反方的评价
反方13个攻击中：
- **3个真攻击**（Attack-4/5/13）——审查认真，发现n_ood事实错误属实
- **5个伪攻击**（Attack-2/8/9/10/12）——Attack-2/8将配置元数据误归类为统计量；Attack-9/10/12反方自认无实际风险仍包装为攻击
- **5个部分成立**（Attack-1/3/6/7/11）——问题属实但严重度全部被高估：Attack-1/3/6从严重降为轻微，Attack-4/5从严重降为中等，Attack-7前提不成立

反方整体审查质量**中等偏上**：发现了n_ood事实错误（Attack-4）这一真问题，但存在严重度系统性高估倾向（7个严重攻击中仅0个维持严重，2个降为中等，5个降为轻微/驳回），且部分攻击基于错误假设（Attack-2/8误将配置当统计，Attack-7误假设R4有resnet1d checkpoint）。
