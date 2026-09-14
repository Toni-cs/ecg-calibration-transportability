# 反反方审查：P0-6+7 R3修复攻击审查

## 审查摘要
- 攻击报告：docs/p0r3_attack_p0_6_7.md
- 审查文件：scripts/run_e5_inception_lite.py（801行）
- 攻击点总数：9
- **成立：6**（Attack-1, Attack-2, Attack-4, Attack-6, Attack-7, Attack-9）
- **部分成立：3**（Attack-3, Attack-5, Attack-8）
- **不成立：0**

### 严重程度校正
| 攻击点 | 反方判定 | 反反方校正 | 说明 |
|--------|---------|-----------|------|
| Attack-1 | 致命 | **致命（维持）** | csv.DictWriter schema不一致确实会崩溃 |
| Attack-2 | 严重 | **严重（维持）** | arch硬编码导致迁移CSV失真 |
| Attack-3 | 严重 | **轻微（降级）** | L451是死代码但作为防御性代码无害，严重程度被夸大 |
| Attack-4 | 中等 | **中等（维持）** | early-return缺截断统计字段 |
| Attack-5 | 中等 | **轻微（降级）** | 设计选择问题，非bug |
| Attack-6 | 轻微 | **轻微（维持）** | L426缺arch字段 |
| Attack-7 | 轻微 | **轻微（维持）** | L750-753缺skipped字段 |
| Attack-8 | 轻微 | **轻微（维持）** | 字段名语义模糊 |
| Attack-9 | 轻微 | **轻微（维持）** | oom_log未过滤 |

---

## 逐条审查

### Attack-1 [致命] R3修复2引入的early-return dict schema与normal result dict不一致，导致csv.DictWriter崩溃

**判定**：✅ 成立

**理由**：

经源码逐行验证，攻击完全成立：

1. **schema不一致事实确认**：
   - L526-545 normal result dict：20字段（source,target,seed,arch,num_classes,n_ood,ood_acc_raw,fitted_T,ood_ece_raw,ood_ece_ts,ood_brier_raw,ood_brier_ts,delta_ece,delta_ece_ci_low,delta_ece_ci_high,brier_reliability_improvement,n_dropped_cal,n_dropped_ood,truncated,subspace_filtered）
   - L484-485 cal empty early-return：6字段（source,target,seed,arch,error,skipped）
   - L487-489 ood empty early-return：6字段（同上）
   - L426 FileNotFound early-return：5字段（source,target,seed,error,skipped，**无arch**）
   - L750-753 exception handler：5字段（source,target,seed,arch,error，**无skipped**）

2. **csv.DictWriter默认行为确认**：
   - L596: `writer = csv.DictWriter(f, fieldnames=list(transfer_results[0].keys()))` — 未设置 `extrasaction='ignore'`
   - Python标准库文档明确：`csv.DictWriter` 默认 `extrasaction='raise'`，当 rowdict 包含不在 fieldnames 中的键时抛出 `ValueError: dict contains fields not in fieldnames`
   - 这是Python标准库的确定性行为，非推测

3. **反例成立性验证**：
   - 场景：第一个迁移ptbxl→chapman seed=42的cal集截断后为空（early-return，6字段），第二个ptbxl→chapman seed=43正常完成（normal result，20字段）
   - 执行流程：L596 `fieldnames = list(transfer_results[0].keys())` = 6字段 → L599写第二个20字段dict时抛出ValueError
   - L599无try-except包裹 → 程序崩溃，CSV文件损坏
   - 反例在真实实验中极易触发（某数据集缺失、某迁移数值异常均会导致early-return）

4. **非稻草人论证**：反方攻击的是R3修复2的实际代码（L482-489），未歪曲正方意图。R3修复2的目的是"防止静默nan传播"，但实现引入了schema不一致的新缺陷。

5. **攻击逻辑自洽**：反方引用Python csv模块文档作为依据，并声称已通过`python -c`实测确认，逻辑链条完整。

**修补方案**：

方案A（推荐，统一schema）：
```python
# 在文件顶部（L131附近）定义常量
TRANSFER_RESULT_FIELDS = [
    "source", "target", "seed", "arch",
    "num_classes", "n_ood", "ood_acc_raw", "fitted_T",
    "ood_ece_raw", "ood_ece_ts", "ood_brier_raw", "ood_brier_ts",
    "delta_ece", "delta_ece_ci_low", "delta_ece_ci_high",
    "brier_reliability_improvement",
    "n_dropped_cal", "n_dropped_ood", "truncated", "subspace_filtered",
    "error", "skipped",  # error/skipped仅early-return使用，normal dict设为None/False
]

# 辅助函数
def _make_transfer_result(**kwargs):
    """统一transfer result dict schema，缺失字段填None"""
    row = {k: None for k in TRANSFER_RESULT_FIELDS}
    row.update(kwargs)
    return row
```

然后所有early-return和normal result dict改用 `_make_transfer_result(...)`：
- L426: `return _make_transfer_result(source=source, target=target, seed=seed, error=str(e), skipped=True, arch=source_info.get("arch", ARCH_NAME))`
- L484-485: `return _make_transfer_result(source=source, target=target, seed=seed, arch=..., error="cal set empty after truncation", skipped=True, n_dropped_cal=..., n_dropped_ood=..., truncated=..., subspace_filtered=...)`
- L487-489: 同上
- L526-545: normal result dict 末尾加 `"error": None, "skipped": False`
- L750-753: 加 `"skipped": True` 和缺失字段

方案B（最小改动）：
- L596: `writer = csv.DictWriter(f, fieldnames=TRANSFER_RESULT_FIELDS, extrasaction='ignore')`
- 同时固定fieldnames为全字段并集

**建议采用方案A**，彻底统一schema，同时解决Attack-4/6/7。

---

### Attack-2 [严重] transfer result的arch字段硬编码为ARCH_NAME，未使用source_info["arch"]

**判定**：✅ 成立

**理由**：

经源码验证，攻击完全成立：

1. **硬编码事实确认**：
   - L527: `"arch": ARCH_NAME` — 硬编码
   - L484: `"arch": ARCH_NAME` — 硬编码
   - L488: `"arch": ARCH_NAME` — 硬编码
   - L752: `"arch": ARCH_NAME` — 硬编码
   - `ARCH_NAME = "inceptiontime_lite"`（L105）

2. **source_info["arch"]未使用确认**：
   - grep验证：`eval_transfer_pair` 中 `source_info` 仅在L413（`source_info["model"]`）和L414（`source_info["cal_eval"]`）被读取
   - **从未读取 `source_info["arch"]`**
   - 而 `source_info["arch"]` 在L372已被正确设为 `arch_display`（含 "resnet1d" 标识）

3. **反例成立性验证**：
   - 场景：OOM Level 3触发，ptbxl seed=42源模型用ResNet1D训练
   - L177-182: Level 3配置 `{"arch": "resnet1d", "depth": 3, "width": 32}`
   - L694: `_train_adapter` 传递 `arch_override=params.get("arch")` = "resnet1d"
   - L307: `arch_display = arch_override if arch_override else ARCH_NAME` = "resnet1d"
   - L372: 训练info dict `"arch": arch_display` = "resnet1d" ✓（训练CSV正确）
   - L527: 迁移result dict `"arch": ARCH_NAME` = "inceptiontime_lite" ✗（迁移CSV错误）
   - 反例完全成立：同一实验，训练CSV arch="resnet1d"，迁移CSV arch="inceptiontime_lite"

4. **R3修复4目的未达成**：R3修复4注释（L368-370）明确目的是"避免CSV arch列失真"。训练侧达成，迁移侧未达成。逻辑断链成立。

5. **非稻草人论证**：反方攻击的是R3修复4的实际效果，未歪曲正方意图。

**修补方案**：

将所有迁移result dict的 `"arch": ARCH_NAME` 改为 `"arch": source_info.get("arch", ARCH_NAME)`：
- **L527**: `"arch": ARCH_NAME` → `"arch": source_info.get("arch", ARCH_NAME)`
- **L484**: `"arch": ARCH_NAME` → `"arch": source_info.get("arch", ARCH_NAME)`
- **L488**: `"arch": ARCH_NAME` → `"arch": source_info.get("arch", ARCH_NAME)`
- **L752**: `"arch": ARCH_NAME` → `"arch": source_info.get("arch", ARCH_NAME)`（注意L750-753的exception handler在main函数中，需将source_info传入或在此处用trained_models查询）
- **L426**: 添加 `"arch": source_info.get("arch", ARCH_NAME)`（同时解决Attack-6）

注意：L750-753的exception handler在main函数的循环中，此时有 `trained_models[(source, seed)]` 可用，应改为：
```python
transfer_results.append({
    "source": source, "target": target, "seed": seed,
    "arch": trained_models[(source, seed)].get("arch", ARCH_NAME),
    "error": str(e), "skipped": True,
})
```

---

### Attack-3 [严重] R3修复1的L451 tgt_clusters[ood_keep]是死代码

**判定**：⚠️ 部分成立（严重程度降级为轻微）

**理由**：

反方的核心论点（L451是死代码）**事实成立**，但严重程度判定（严重）**被夸大**。

1. **L451是死代码的推理验证**：

   逐方向验证ood_keep = ood_labels < num_classes：

   | 迁移方向 | num_classes | target构建 | ood_labels范围 | ood_keep |
   |---------|------------|-----------|--------------|---------|
   | ptbxl→chapman | min(5,5)=5 | chapman, subspace=None | {0,1,2,3,4} | 全True ✓ |
   | ptbxl→cpsc | min(5,4)=4 | cpsc(4类, 不传subspace) | {0,1,2,3} | 全True ✓ |
   | chapman→ptbxl | min(5,5)=5 | ptbxl, subspace=None | {0,1,2,3,4} | 全True ✓ |
   | chapman→cpsc | min(5,4)=4 | cpsc(4类) | {0,1,2,3} | 全True ✓ |
   | cpsc→ptbxl | min(4,5)=4 | ptbxl, subspace=SUBSPACE_CPSC | {0,1,2,3} | 全True ✓ |
   | cpsc→chapman | min(4,5)=4 | chapman, subspace=SUBSPACE_CPSC | {0,1,2,3} | 全True ✓ |

   关键验证：
   - `SUBSPACE_CPSC = ("NORM", "MI", "STTC", "CD")`（4类，已确认）
   - `filter_subspace` 过滤后 `label_map = {c: i for i, c in enumerate(subspace)}`，labels∈{0,1,2,3}（已确认）
   - `build_cpsc_datasets` 签名无subspace参数，内部自己用SUBSPACE_CPSC过滤为4类（已确认）
   - **结论**：ood_keep在所有6个方向上恒为全True，L451 `tgt_clusters = tgt_clusters[ood_keep]` 等价于 `tgt_clusters = tgt_clusters`（no-op）

2. **L476是真正必要的修复**：
   - L476: `tgt_clusters = tgt_clusters[~ood_zero_rows]` — 零行丢弃确实会改变ood_probs长度，需同步截断tgt_clusters
   - 这是活跃的、必要的修复
   - 反方此点判断正确

3. **严重程度被夸大**（降级理由）：
   - L451作为**防御性代码**是合理的：防止builder未来变更（如新增数据集、subspace逻辑修改）后ood_keep非全True导致IndexError
   - L451是no-op，**不影响运行时正确性**，不引入任何bug
   - L451+L476同时修复后结果正确，无虚假安全感风险
   - 反方称"严重——R2判决的优先级判断有误"，但L451作为防御性代码无害，真正的问题只是R2判决未区分L451（死代码）和L476（活跃修复）的优先级——这是文档/注释问题，非代码缺陷
   - **应降级为轻微**：建议加注释说明L451为防御性no-op

4. **非稻草人论证**：反方攻击的是L451的实际行为（死代码），未歪曲正方意图。

**修补方案**（轻微，加注释）：

**L449-451** 修改注释：
```python
# R3 修复1 [P0-致命]：同步截断 tgt_clusters，否则 benefit_inference 的
# cluster bootstrap 会因 tgt_clusters 长度 != ood_probs 行数而 IndexError。
# 注：当前6个迁移方向上 ood_keep 恒为全True（target构建保证 labels < num_classes），
# 此行为防御性 no-op。真正的必要修复在 L476（零行同步）。
# 保留此行作为防御性代码，防止未来 builder 变更导致 ood_keep 非全True。
tgt_clusters = tgt_clusters[ood_keep]
```

---

### Attack-4 [中等] early-return dict缺少n_dropped_cal/n_dropped_ood/truncated/subspace_filtered字段

**判定**：✅ 成立

**理由**：

1. **字段缺失事实确认**：
   - L484-485: `return {"source":..., "target":..., "seed":..., "arch":ARCH_NAME, "error":"cal set empty after truncation", "skipped":True}` — 无 `n_dropped_cal`/`n_dropped_ood`/`truncated`/`subspace_filtered`
   - L487-489: 同上
   - normal result dict（L540-544）有这四个字段

2. **反例成立性验证**：
   - 场景：ptbxl→cpsc seed=42，cal集1000个样本全部标签=4（HYP类）
   - L437: `n_dropped_cal = 1000`
   - L445-446: cal_labels和cal_probs变空
   - L482: `len(cal_probs) == 0` → True
   - L484: 返回dict中 `n_dropped_cal=1000` 的信息丢失
   - 反例成立：跳过实验的截断统计不可追溯

3. **影响**：不影响运行时正确性，但影响CBM要求的实验可追溯性。下游分析者无法知道丢弃了多少样本才导致空集。

4. **非稻草人论证**：反方攻击的是R3修复3的覆盖不全，未歪曲正方意图。

**修补方案**（与Attack-1方案A合并）：

**L482-485** 修改：
```python
if len(cal_probs) == 0:
    print(f"[WARN] {source}→{target} seed={seed}: cal 集截断后为空，跳过 TS 校准")
    return _make_transfer_result(
        source=source, target=target, seed=seed,
        arch=source_info.get("arch", ARCH_NAME),
        error="cal set empty after truncation", skipped=True,
        n_dropped_cal=int(n_dropped_cal), n_dropped_ood=int(n_dropped_ood),
        truncated=bool((n_dropped_cal + n_dropped_ood) > 0),
        subspace_filtered=bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
    )
```

**L486-489** 同理修改ood empty early-return。

---

### Attack-5 [中等] truncated字段无法区分"标签截断"与"零行丢弃"两种丢弃原因

**判定**：⚠️ 部分成立（严重程度降级为轻微）

**理由**：

1. **事实确认**：
   - L437: `n_dropped_cal = int((cal_labels >= num_classes).sum())` — 标签截断计数
   - L460: `n_dropped_cal += int(cal_zero_rows.sum())` — 零行丢弃累计
   - L543: `"truncated": bool((n_dropped_cal + n_dropped_ood) > 0)` — 是否有丢弃
   - n_dropped_cal确实是两种丢弃原因的混合总数

2. **反例成立性验证**：
   - 场景：n_dropped_cal=100，其中50个因标签>=4被丢弃，50个因全零行被丢弃
   - CSV中只有 `n_dropped_cal=100`，无法区分
   - 反例事实成立

3. **严重程度降级理由**（设计选择，非bug）：
   - `n_dropped_cal` 记录**总丢弃数**是合理的设计选择：对下游分析者而言，"总共丢弃了多少样本"是首要信息
   - `truncated` 表示"是否有丢弃"也是合理的布尔标志
   - 区分两种丢弃原因（标签截断 vs 零行丢弃）是**可选的改进**，非必需修复
   - 反方自己也标为"中等"并说"可选改进"，且在R3修复评价表中将修复5标为"正确"
   - **不影响运行时正确性，不影响CBM可追溯性**（总丢弃数已记录，只是无法区分原因）
   - 应降级为轻微

4. **非稻草人论证**：反方攻击的是字段语义粒度，未歪曲正方意图。

**修补方案**（可选改进，非必修）：

如需区分两种丢弃原因，增加字段：
```python
# L437附近
n_dropped_cal_label = int((cal_labels >= num_classes).sum())
n_dropped_cal = n_dropped_cal_label  # 初始为标签截断数

# L460附近
n_dropped_cal_zero = int(cal_zero_rows.sum())
n_dropped_cal += n_dropped_cal_zero  # 累计零行丢弃

# L540-544 normal result dict 增加
"n_dropped_cal_label": int(n_dropped_cal_label),
"n_dropped_cal_zero": int(n_dropped_cal_zero),
```

ood侧同理。此修补**可选**，优先级低于Attack-1/2/4。

---

### Attack-6 [轻微] L426 FileNotFound early-return dict缺少arch字段

**判定**：✅ 成立

**理由**：

1. **字段缺失事实确认**：
   - L426: `return {"source": source, "target": target, "seed": seed, "error": str(e), "skipped": True}` — 确实无arch字段
   - L484/L488的early-return都有 `"arch": ARCH_NAME`

2. **反例成立性验证**：
   - 若transfer_results中同时存在L426返回的dict（无arch）和normal result dict（有arch）
   - 即使修复了Attack-1（统一schema），L426的dict仍需补arch字段
   - 反例成立

3. **非稻草人论证**：反方攻击的是schema不一致的具体实例，未歪曲正方意图。

**修补方案**（与Attack-1/2合并）：

**L426** 修改：
```python
return {"source": source, "target": target, "seed": seed,
        "arch": source_info.get("arch", ARCH_NAME),
        "error": str(e), "skipped": True}
```

---

### Attack-7 [轻微] L750-753 exception handler dict缺少skipped字段

**判定**：✅ 成立

**理由**：

1. **字段缺失事实确认**：
   - L750-753: `transfer_results.append({"source": source, "target": target, "seed": seed, "arch": ARCH_NAME, "error": str(e)})` — 确实无skipped字段
   - L426/L484/L488的error dict都有 `"skipped": True`

2. **反例成立性验证**：
   - 下游分析者用 `skipped` 字段过滤跳过的实验：`df[df.skipped]`
   - L750-753的异常结果缺少skipped字段，pandas读取后为NaN
   - `df[df.skipped]` 不包含该异常结果（NaN在布尔索引中为False）
   - 反例成立：异常结果不会被过滤为skipped

3. **非稻草人论证**：反方攻击的是schema不一致的具体实例，未歪曲正方意图。

**修补方案**（与Attack-1/2合并）：

**L750-753** 修改：
```python
transfer_results.append({
    "source": source, "target": target, "seed": seed,
    "arch": trained_models[(source, seed)].get("arch", ARCH_NAME),
    "error": str(e), "skipped": True,
})
```

---

### Attack-8 [轻微] subspace_filtered字段语义模糊

**判定**：⚠️ 部分成立（严重程度维持轻微）

**理由**：

1. **事实确认**：
   - L544: `"subspace_filtered": bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target]))`
   - 当source和target类数不同时，subspace_filtered=True

2. **反例成立性验证**：
   - ptbxl→cpsc: num_classes=4, max(5,4)=5, 4<5=True, subspace_filtered=True
     - 实际过滤：source cal侧标签截断（label 4被丢弃），target cpsc本身就是4类无需subspace过滤
     - 字段名"subspace_filtered"暗示target被subspace过滤，但此处target未被过滤
   - cpsc→ptbxl: num_classes=4, max(4,5)=5, 4<5=True, subspace_filtered=True
     - 实际过滤：target ptbxl被subspace过滤降为4类
     - 字段名"subspace_filtered"准确
   - 同样subspace_filtered=True，但两种方向的过滤机制不同
   - 反例事实成立

3. **严重程度维持轻微理由**（设计选择，非bug）：
   - `truncated`/`n_dropped_cal`/`n_dropped_ood` 字段已提供了实际过滤信息
   - `subspace_filtered` 仅是方向级标志，表示"该迁移涉及跨类数转换"
   - 字段名语义模糊不影响正确性，仅影响字段名可读性
   - 反方自己也标为"轻微"并说"可选改进"
   - 这是命名改进，非bug修复

4. **非稻草人论证**：反方攻击的是字段名语义，未歪曲正方意图。

**修补方案**（可选改进，非必修）：

方案1（重命名，需同步更新下游分析脚本）：
- L544: `"subspace_filtered"` → `"cross_class_transfer"`

方案2（加注释，推荐）：
```python
# L544: subspace_filtered 表示该迁移涉及跨类数转换（source/target类数不同）。
# 注意：5→4方向的过滤发生在source cal侧（标签截断），4→5方向的过滤发生在target侧（subspace过滤）。
# 具体过滤机制见 n_dropped_cal/n_dropped_ood 字段。
"subspace_filtered": bool(num_classes < max(DATASET_NUM_CLASSES[source], DATASET_NUM_CLASSES[target])),
```

此修补**可选**，优先级最低。

---

### Attack-9 [轻微] oom_log字段未从CSV序列化中过滤

**判定**：✅ 成立

**理由**：

1. **事实确认**：
   - L195: `return model, {**extra, "oom_log": oom_log}` — oom_log是嵌套dict
   - L589: `if k not in ("model", "loaders", "cal_eval", "test_eval", "clusters_test")` — 未包含oom_log
   - L767: 同上
   - oom_log会被写入训练CSV，值为str(dict)

2. **反例成立性验证**：
   - 训练CSV的 `oom_log` 列值为 `{'level': 1, 'actions': ['Level 1: n_filters 48→32...'], ...}`
   - csv.DictWriter会将dict转为str写入
   - pandas读取后为str类型，无法直接用 `df.oom_log.apply(lambda x: x['level'])` 提取level
   - 需手动 `ast.literal_eval` 才能解析
   - 反例成立

3. **影响范围**：仅影响**训练CSV**（train_results），不影响迁移CSV（transfer_results）。oom_log包含有用信息（level, actions, final_config），展平或保留都是合理选择。

4. **非稻草人论证**：反方攻击的是CSV序列化的实际行为，未歪曲正方意图。

5. **非崩溃**：str(dict)是合法字符串，csv模块会自动加引号转义，不会崩溃。仅影响分析便利性。

**修补方案**（可选改进，非必修）：

方案1（展平，推荐）：
```python
# L195附近，将oom_log展平后加入extra
oom_log_flat = {
    "oom_level": oom_log["level"],
    "oom_actions": " | ".join(oom_log["actions"]),
}
return model, {**extra, **oom_log_flat}  # 不再传嵌套dict
```

方案2（加入过滤列表）：
- L589: `if k not in ("model", "loaders", "cal_eval", "test_eval", "clusters_test", "oom_log")`
- L767: 同上
- 但这样会丢失oom信息，不推荐

此修补**可选**，优先级低于Attack-1/2/4。

---

## 总结

### 需R4修复的必修项清单（按优先级排序）

| 优先级 | 攻击点 | 修补内容 | 涉及行号 |
|--------|--------|---------|---------|
| **P0-致命** | Attack-1 | 统一所有transfer result dict的schema（方案A：定义TRANSFER_RESULT_FIELDS + _make_transfer_result辅助函数） | L131附近新增常量；L426/L484-485/L487-489/L526-545/L750-753 |
| **P0-严重** | Attack-2 | 迁移result dict的arch字段改用 `source_info.get("arch", ARCH_NAME)` | L527/L484/L488/L752/L426 |
| **P0-中等** | Attack-4 | early-return dict补齐 n_dropped_cal/n_dropped_ood/truncated/subspace_filtered 字段 | L484-485/L487-489（与Attack-1合并） |
| **P0-轻微** | Attack-6 | L426补arch字段 | L426（与Attack-1/2合并） |
| **P0-轻微** | Attack-7 | L750-753补skipped字段 | L750-753（与Attack-1合并） |

**说明**：Attack-1/2/4/6/7 可通过一次统一schema重构合并修复，核心改动是定义 `TRANSFER_RESULT_FIELDS` 常量和 `_make_transfer_result` 辅助函数，然后将所有5种transfer result dict改用该辅助函数构造。

### 可选改进项清单（非必修）

| 攻击点 | 改进内容 | 优先级 |
|--------|---------|--------|
| Attack-3 | L451加注释标明为防御性no-op | 轻微 |
| Attack-5 | 增加 n_dropped_cal_label/n_dropped_cal_zero 字段区分丢弃原因 | 轻微 |
| Attack-8 | subspace_filtered字段加注释说明语义 | 轻微 |
| Attack-9 | oom_log展平为 oom_level/oom_actions 字段 | 轻微 |

### 可关闭的攻击点

无完全可关闭的攻击点。所有9个攻击点均至少部分成立，反方审查质量较高，无稻草人论证、无反例构造错误、无逻辑不自洽。

### 整体评估

1. **反方审查质量**：高。9个攻击点均基于源码实际行为，无稻草人论证，反例构造合理，逻辑自洽。

2. **R3修复评价**：
   - 修复1（L451+L476）：L476有效，L451为防御性死代码（无害但非必要）
   - 修复2（空数组提前返回）：**引入新致命bug**（Attack-1，schema不一致导致csv.DictWriter崩溃）——这是本轮最严重发现
   - 修复3（result dict新字段）：字段正确但early-return dict缺失（Attack-4）
   - 修复4（info dict新字段）：训练侧正确，迁移侧arch硬编码未同步（Attack-2）
   - 修复5（n_dropped累计）：正确但语义可改进（Attack-5）

3. **最关键发现**：**Attack-1成立**——R3修复2本身引入了新的P0-致命缺陷。early-return dict与normal result dict的schema不一致，在"任一迁移失败+任一迁移成功"的常见场景下，csv.DictWriter会抛出ValueError导致程序崩溃。这违背了R3修复2的目的（"防止静默nan传播"），将一个静默数值问题升级为硬崩溃。**必须R4修复**。

4. **建议R4修复优先级**：
   1. **[P0-致命]** 统一所有transfer result dict的schema（Attack-1），同时解决Attack-4/6/7
   2. **[P0-严重]** 迁移result dict的arch字段改用source_info["arch"]（Attack-2）
   3. **[P0-轻微]** L451加注释标明为防御性no-op（Attack-3）
   4. **[P0-轻微]** 其余可选改进（Attack-5/8/9）

### 裁决统计
- 有效攻击数：6（Attack-1, 2, 4, 6, 7, 9）
- 部分有效攻击数：3（Attack-3, 5, 8）
- 被驳回攻击数：0
- 严重程度被降级攻击数：2（Attack-3: 严重→轻微, Attack-5: 中等→轻微）
