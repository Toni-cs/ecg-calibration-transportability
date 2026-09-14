# 反反方审查：P0-1 R3修复攻击审查

## 审查摘要
- **攻击报告**：docs/p0r3_attack_p0_1.md
- **审查文件**：eval_l2_shift.py, run_e4_temperature_analysis.py, run_e1a_l2_shift_full.py, l2_shifts.py
- **攻击点总数**：12
- **成立**：7（A1, A2, A4, A5, A7, A8, A9）
- **不成立**：1（A12）
- **部分成立**：4（A3, A6, A10, A11）

### 裁决统计
| 裁决类型 | 数量 | 攻击点 |
|---------|------|--------|
| 成立 | 7 | A1, A2, A4, A5, A7, A8, A9 |
| 部分成立 | 4 | A3, A6, A10, A11 |
| 不成立 | 1 | A12 |

### 严重度复核
| 原严重度 | 复核严重度 | 攻击点 | 说明 |
|---------|-----------|--------|------|
| 严重 | **成立·严重** | A1 | 断点续传确实保留旧种子结果 |
| 严重 | **成立·严重** | A2 | 默认参数确实静默回退旧bug |
| 严重 | **成立·严重（与A2同源）** | A4 | A2的另一种表述，修A2即修A4 |
| 严重 | **成立·严重** | A8 | l2_shifts.py回退路径确实矛盾 |
| 中等 | **部分成立·轻微** | A3 | 注释语义不精确，实际影响可忽略 |
| 中等 | **成立·中等（与A1同源）** | A5 | A1的另一种表述，修A1即修A5 |
| 中等 | **部分成立·轻微（与A2同源）** | A6 | 空值边界即A2的默认值问题 |
| 中等 | **部分成立·轻微** | A10 | 截断损失真实但0.016%可忽略；`% (2**32)`冗余成立 |
| 中等 | **部分成立·轻微** | A11 | 语义偏移真实但非正确性bug |
| 轻微 | **成立·轻微** | A7 | 非噪声档rng创建确实无效，但性能影响可忽略 |
| 轻微 | **成立·轻微** | A9 | 重复代码块确实存在，但非R3引入 |
| 轻微 | **不成立** | A12 | Python 3.x内可复现声明正确 |

---

## 逐条审查

### 攻击点A1: 断点续传导致混合种子数据集
**判定**：成立
**原严重度**：严重 → **复核严重度**：严重

**理由**：
反方攻击真实成立。经逐行验证：

1. `run_e1a_l2_shift_full.py` L293: `if not force and is_checkpoint_complete(run_dir, seed, shift_names):` — 断点续传逻辑确实存在
2. L295-296: 命中后直接 `return existing[f"seed{seed}"]` — 旧结果被保留
3. `is_checkpoint_complete` L238-264: 仅检查 `safety` 字段存在性（L262-263），**不检查种子策略版本**
4. R2轮若用 `run_e1a_l2_shift_full.py` 生成结果，则含 `safety` 字段（L399添加），断点续传会命中
5. 旧结果用 `RandomState(42)`，新代码用 `RandomState(noise_seed)` — 混合种子数据集真实存在

**反例验证**：反例成立。用户不带 `--force` 运行时，旧结果被保留，修复静默失效。

**修补方案**：
- **文件**：`scripts/run_e1a_l2_shift_full.py`
- **改动1**：在 `is_checkpoint_complete` 函数（L238-264）中增加种子策略版本检查
```python
# L260后增加：
SEED_STRATEGY_VERSION = "md5_v1"  # 模块级常量

# 在 is_checkpoint_complete 的循环内（L263后）增加：
if cell.get("seed_strategy") != SEED_STRATEGY_VERSION:
    return False
```
- **改动2**：在 `evaluate_one_checkpoint` 的 cell 字典中（L343附近）增加版本标记
```python
cell["seed_strategy"] = SEED_STRATEGY_VERSION  # 种子策略版本标记
```
- **改动3**：在注释 L175-176 中显式提示 `--force`
```python
# 需重跑受影响实验：必须传 --force 或删除旧 l2_shift_results.json（见 docs/p0r2_final_verdict.md §2.2）
```

---

### 攻击点A2: 函数默认参数导致静默失败
**判定**：成立
**原严重度**：严重 → **复核严重度**：严重

**理由**：
反方攻击真实成立。经逐行验证：

1. `eval_l2_shift.py` L36-37: `pair_id: str = "", arch: str = "", train_seed: int = 0` — 默认值确实危险
2. `run_e1a_l2_shift_full.py` L163-164: 同上
3. `run_e4_temperature_analysis.py` L295-296: 同上
4. 若调用方忘记传参，哈希键 = `"||0|noise24"` → 所有实验共享同一种子 → 退化为R2修复前的bug
5. **无任何错误或警告** — 静默失败

**当前调用方验证**：3处调用方均正确传参（eval_l2_shift.py L138、run_e1a_l2_shift_full.py L330、run_e4_temperature_analysis.py L656），但默认值使未来新增调用方容易遗漏。

**反例验证**：反例成立。未来调用方忘记传参时静默回退旧bug。

**修补方案**：
- **文件1**：`scripts/eval_l2_shift.py` L36-37
- **文件2**：`scripts/run_e1a_l2_shift_full.py` L163-164
- **文件3**：`scripts/run_e4_temperature_analysis.py` L295-296
- **改动**（3处相同）：
```python
# 旧：
def shifted_eval(model, dataset, shift, device, batch_size=64,
                 pair_id: str = "", arch: str = "", train_seed: int = 0):
# 新：
def shifted_eval(model, dataset, shift, device, batch_size=64,
                 pair_id: str = None, arch: str = None, train_seed: int = None):
    if pair_id is None or arch is None or train_seed is None:
        raise ValueError(
            "pair_id, arch, train_seed are required for noise seed derivation; "
            "got pair_id=%r, arch=%r, train_seed=%r" % (pair_id, arch, train_seed)
        )
```
- `run_e4_temperature_analysis.py` 的函数名为 `shifted_probs_labels`，改动相同。

---

### 攻击点A3: 注释声称"必然获得不同种子"存在逻辑跳跃
**判定**：部分成立
**原严重度**：中等 → **复核严重度**：轻微

**理由**：
反方攻击在逻辑上成立，但严重度被夸大。

1. 注释确实写"必然获得不同种子"（eval_l2_shift.py L44、run_e1a_l2_shift_full.py L174、run_e4_temperature_analysis.py L308）
2. md5存在碰撞（理论上），`hexdigest()[:8]`截断到32位后碰撞概率增加
3. 因此"必然"一词在数学上不精确，应为"极大概率"

**但严重度被夸大**：
- 当前1170个键的碰撞概率 ≈ 0.016%（见A10量级分析），实际运行中几乎不可能碰撞
- md5碰撞在当前键空间下属于"理论存在、实际不发生"的范畴
- 注释不精确属于文档质量问题，不影响代码正确性
- CBM审稿标准下属于"措辞不严谨"，非"隐含假设未显式化"的实质问题

**反驳**：反方将"注释措辞不精确"包装为"逻辑断链"中等严重度，实际应为轻微。注释的"必然"是工程语境下的近似表达，非数学定理声明。

**修补方案**（可选，轻微）：
- **文件**：3个脚本的注释行
- **改动**：将"必然获得不同种子"改为"极大概率获得不同种子（1170键下碰撞概率≈0.016%）"

---

### 攻击点A4: 隐含假设"所有调用方都传rng"未显式强制
**判定**：成立（与A2同源）
**原严重度**：严重 → **复核严重度**：严重（但与A2合并修复）

**理由**：
反方攻击成立，但本质上是A2的另一种表述。

1. 修复确实依赖所有调用方传 pair_id/arch/train_seed
2. 默认参数 `=""`/`=0` 使遗漏静默通过 — 这正是A2描述的问题
3. `l2_shifts.py` 的 `apply_shift` 接受 `rng=None` 回退到 `RandomState(42)` — 这正是A8描述的问题

**与A2的关系**：A4是A2（默认参数）+ A8（回退路径）的组合表述。修A2和A8即修A4，无需独立修复。

**修补方案**：与A2合并修复（改默认值为None + raise ValueError）。

---

### 攻击点A5: 隐含假设"旧结果会被重跑"未提供机制保障
**判定**：成立（与A1同源）
**原严重度**：中等 → **复核严重度**：中等（但与A1合并修复）

**理由**：
反方攻击成立，但本质上是A1的另一种表述。

1. 注释写"需重跑受影响实验"，假设用户会主动重跑
2. 代码未提供版本标记或种子策略指纹 — 这正是A1描述的问题
3. 断点续传机制会保留旧结果 — 这正是A1描述的问题

**与A1的关系**：A5是A1的"假设层面"表述，A1是A5的"反例构造"表述。修A1即修A5，无需独立修复。

**修补方案**：与A1合并修复（增加seed_strategy版本标记 + is_checkpoint_complete检查）。

---

### 攻击点A6: 空字符串/零值边界下哈希键退化
**判定**：部分成立（与A2同源）
**原严重度**：中等 → **复核严重度**：轻微

**理由**：
反方攻击部分成立，但严重度被夸大。

1. **`pair_id=""` 且 `arch=""` 且 `train_seed=0` 的情况**：这与A2完全相同 — 默认值导致哈希键退化为 `"||0|noise24"`。修A2即修此情况。
2. **`shift['name']` 为空字符串的情况**：反方自己验证"当前 `get_l2_shifts()` 的 13 档 name 均非空"，此情况不触发。属于假设性边界，当前无实际风险。

**严重度被夸大**：
- 第一种情况是A2的重复，应随A2合并处理
- 第二种情况是假设性边界，当前不触发，且 `get_l2_shifts()` 是唯一 shift 来源，受控
- "中等"严重度过高，应为"轻微"（当前不触发，无防御性检查）

**修补方案**：与A2合并修复（改默认值为None + raise ValueError）。`shift['name']` 空值防御可选：
```python
# 在种子派生前增加（可选）：
if not shift.get("name"):
    raise ValueError("shift['name'] is required for noise seed derivation")
```

---

### 攻击点A7: 非噪声档的 rng 创建是无效计算
**判定**：成立
**原严重度**：轻微 → **复核严重度**：轻微

**理由**：
反方攻击成立，严重度评估准确。

1. 13档中仅5档（noise24/noise12/noise6/noise0/noise-6）使用rng
2. `l2_shifts.py` L200-207: `apply_shift` 仅在 `t == "noise"` 时调用 `shift_noise`（使用rng），其余分支直接返回确定性变换
3. 对8个非噪声档，md5哈希计算和RandomState创建是浪费

**但影响可忽略**：
- md5哈希 + RandomState创建耗时 < 1微秒
- 相对于模型前向推理（毫秒级），性能影响可忽略
- 不影响正确性

**修补方案**（可选，提升语义清晰度）：
- **文件**：3个脚本的种子派生行
- **改动**：将rng创建移入条件分支
```python
# 旧：
noise_seed = int(hashlib.md5(...).hexdigest()[:8], 16) % (2**32)
rng = np.random.RandomState(noise_seed)
for i in range(n):
    ...
    sig_s = apply_shift(sig, shift, rng=rng)

# 新：
rng = None
if shift["type"] == "noise":
    noise_seed = int(hashlib.md5(...).hexdigest()[:8], 16) % (2**32)
    rng = np.random.RandomState(noise_seed)
for i in range(n):
    ...
    sig_s = apply_shift(sig, shift, rng=rng)  # apply_shift 对非噪声档忽略 rng
```
- **注意**：此改动可选，当前性能影响可忽略。若不改，建议在注释中说明"rng仅对noise档生效"。

---

### 攻击点A8: l2_shifts.py 回退路径与 R3 修复矛盾
**判定**：成立
**原严重度**：严重 → **复核严重度**：严重

**理由**：
反方攻击真实成立。经逐行验证：

1. `l2_shifts.py` L78-79 (`_synthetic_noise`): `if rng is None: rng = np.random.RandomState(42)` — 回退路径确实存在
2. `l2_shifts.py` L119-120 (`shift_noise`): `if rng is None: rng = np.random.RandomState(42)` — 回退路径确实存在
3. R3修复目标：消除跨实验共享seed 42
4. 若 `rng=None` 传入，`l2_shifts.py` 仍用 `RandomState(42)` — 所有实验共享种子
5. `apply_shift` L192-199: 仅发 UserWarning，不阻止执行

**当前调用方验证**：3处调用方均传 `rng=rng`（eval_l2_shift.py L54、run_e1a_l2_shift_full.py L184、run_e4_temperature_analysis.py L318），回退路径当前不触发。但回退路径的存在使修复不完整 — 若未来调用方忘记传rng，静默回退旧bug。

**矛盾点确认**：修复在调用方层做了种子派生（"必须不同"），但在被调用方层保留旧bug回退（"可以相同"），两层逻辑矛盾。

**修补方案**：
- **文件**：`src/data/l2_shifts.py`
- **改动1**：L78-79
```python
# 旧：
if rng is None:
    rng = np.random.RandomState(42)
# 新：
if rng is None:
    raise ValueError(
        "rng is required for _synthetic_noise; pass rng from caller "
        "(e.g., np.random.RandomState(seed)) to ensure per-experiment noise independence"
    )
```
- **改动2**：L119-120
```python
# 旧：
if rng is None:
    rng = np.random.RandomState(42)
# 新：
if rng is None:
    raise ValueError(
        "rng is required for shift_noise; pass rng from caller "
        "(e.g., np.random.RandomState(seed)) to ensure per-experiment noise independence"
    )
```
- **改动3**（可选）：L192-199 的 UserWarning 可保留为兼容层，或同步改为 raise。建议改为 raise 以消除矛盾。

---

### 攻击点A9: run_e4_temperature_analysis.py 存在重复代码块
**判定**：成立
**原严重度**：轻微 → **复核严重度**：轻微

**理由**：
反方攻击成立。经逐行验证：

1. L524-532 与 L534-542 确实是完全相同的代码块（含注释）
2. 两块都计算 `id_rel_binned_global`、`ood_rel_binned_global` 并写入 `dist_record`
3. 第二块（L534-542）是冗余的 — 重复赋值相同值

**反方公平声明**：反方已注明"非 R3 引入（预存缺陷）"，攻击诚实。

**修补方案**：
- **文件**：`scripts/run_e4_temperature_analysis.py`
- **改动**：删除 L534-542 的重复代码块
```python
# 删除以下重复块（L534-542）：
    # 全局 binned-T Brier reliability（在整个 test 集上一次计算，非 per-bin 均值）
    # M2 核心比较：binned-T 的全局 Brier reliability vs global-T 的全局 Brier reliability
    # 注意：per-bin 均值 ≠ 全局 Brier reliability（Brier reliability 是加权非线性，不可加）
    id_rel_binned_global = brier_reliability_top(id_probs_binned, id_labels)
    ood_rel_binned_global = brier_reliability_top(ood_probs_binned, ood_labels)
    dist_record["id_rel_binned_T"] = id_rel_binned_global
    dist_record["ood_rel_binned_T"] = ood_rel_binned_global
    dist_record["id_delta_rel_binned_vs_global"] = id_rel_binned_global - id_rel_global
    dist_record["ood_delta_rel_binned_vs_global"] = ood_rel_binned_global - ood_rel_global
```

---

### 攻击点A10: hexdigest()[:8] 截断到 32 位的碰撞概率估计
**判定**：部分成立
**原严重度**：中等 → **复核严重度**：轻微

**理由**：
反方攻击部分成立，但严重度被夸大。

1. **截断损失真实**：完整md5 128位 → 截断32位，确实损失96位熵
2. **碰撞概率计算正确**：1170键下生日悖论碰撞概率 ≈ 0.016%，量级分析无误
3. **`% (2**32)` 冗余成立**：`int(hexdigest()[:8], 16)` 已在 [0, 2^32) 范围内，`% (2**32)` 确实是 no-op

**但严重度被夸大**：
- 0.016%碰撞概率在单次运行中可忽略 — 实际运行1170个键几乎不可能碰撞
- 反方自己承认"当前 1170 键下碰撞可忽略"
- "中等"严重度过高，应为"轻微"（当前无实际风险，仅理论改进空间）
- `% (2**32)` 冗余虽成立但无害 — 不影响正确性，仅代码风格问题

**反驳**：反方将"理论改进空间"包装为"中等严重度"，实际应为轻微。当前1170键下碰撞概率0.016%属于"可忽略"范畴，非"中等风险"。

**修补方案**（可选，提升熵利用）：
- **文件**：3个脚本的种子派生行
- **改动**：使用全部128位哈希
```python
# 旧：
noise_seed = int(
    hashlib.md5(f"{pair_id}|{arch}|{train_seed}|{shift['name']}".encode()).hexdigest()[:8], 16
) % (2**32)
# 新（使用全部128位，% 2^32 映射到 RandomState 接受范围）：
noise_seed = int(
    hashlib.md5(f"{pair_id}|{arch}|{train_seed}|{shift['name']}".encode()).hexdigest(), 16
) % (2**32)
```
- **注意**：此改动可选，当前0.016%碰撞概率可忽略。若不改，建议删除冗余的 `% (2**32)` 并添加注释说明截断选择。

---

### 攻击点A11: pair_id 语义在 E4 中偏移
**判定**：部分成立
**原严重度**：中等 → **复核严重度**：轻微

**理由**：
反方攻击部分成立，但严重度被夸大，且反方自己承认"严格说不是bug"。

1. **语义偏移真实**：
   - `eval_l2_shift.py` L136-139: 噪声施加到 `tgt_ds["test"]`（target test集）
   - `run_e1a_l2_shift_full.py` L328-331: 噪声施加到 `tgt_ds["test"]`（target test集）
   - `run_e4_temperature_analysis.py` L654-657: 噪声施加到 `src_ds["cal"]`（source cal集）
2. **同一 (pair, arch, seed, shift_name) 在 E1a 和 E4 产生相同 noise_seed** — 属实

**但不是正确性bug**（反方自己承认）：
- 噪声由 rng 状态和信号内容共同决定
- 不同信号（cal vs test）+ 相同 rng 状态 = 不同噪声结果
- E4 的语义是"对 cal 集施加 shift 拟合 T"，E1a 是"对 test 集施加 shift 评估安全率" — 两者实验语义不同但各自正确
- 共享种子派生键不会导致错误结果，仅是"语义不够精确"

**严重度被夸大**：
- 反方承认"当前不影响正确性"
- "中等"严重度过高，应为"轻微"（语义精确性问题，非正确性问题）
- 添加数据集角色到派生键是"更精确"而非"修复bug"

**修补方案**（可选，提升语义精确性）：
- **文件**：`scripts/run_e4_temperature_analysis.py` L654-657
- **改动**：在派生键中增加数据集角色
```python
# 旧：
cal_probs_s, cal_labels_s = shifted_probs_labels(
    model, src_ds["cal"], shift, device,
    pair_id=pair, arch=arch, train_seed=seed,
)
# 新（增加 dataset_role 参数，或在 pair_id 中编码）：
cal_probs_s, cal_labels_s = shifted_probs_labels(
    model, src_ds["cal"], shift, device,
    pair_id=f"{pair}#cal", arch=arch, train_seed=seed,  # # 不出现于 pair_id 中，无分隔符碰撞
)
```
- **注意**：此改动可选，当前不影响正确性。若不改，建议在注释中说明 E4 的 pair_id 语义。

---

### 攻击点A12: "跨进程可复现"声明忽略 Python 版本差异
**判定**：不成立
**原严重度**：轻微 → **复核严重度**：不成立

**理由**：
反方攻击不成立，反方自己承认"声明基本正确"。

1. **hashlib.md5 跨进程可复现**：md5算法标准化（RFC 1321），Python 3.x 内输出一致 — 声明正确
2. **`.encode()` 默认 UTF-8**：Python 3 中稳定，键字符串纯ASCII — 无歧义
3. **`f"{train_seed}"` 字符串化**：`int.__format__` 在 Python 3.x 内稳定
4. **项目用 `from __future__ import annotations`**：暗示 Python 3.7+，Python 2 不在支持范围

**反驳**：
- 反方承认"Python 3.x 内可复现成立，声明基本正确"
- 项目明确使用 Python 3.7+ 语法（type hints、f-string、`from __future__ import annotations`）
- Python 2/3 差异不在项目支持范围
- "跨进程可复现"声明在项目支持的 Python 版本内完全正确
- 反方将"不在支持范围内的理论差异"包装为攻击点，属于稻草人论证

**稻草人论证**：反方歪曲了"跨进程可复现"的适用范围。声明的语境是"跨进程"（同一 Python 版本的不同进程），非"跨 Python 版本"。反方将"跨 Python 版本"的假设性差异强加于声明，属于超出适用范围的攻击。

**修补方案**：无需修补。声明在项目支持的 Python 3.7+ 范围内完全正确。

---

## 总结

### 需R4修复的必修项清单

按优先级排序，去重后（A4合并入A2，A5合并入A1，A6合并入A2）：

| 优先级 | 攻击点 | 修复文件 | 改动量 | 说明 |
|--------|--------|---------|--------|------|
| **P0** | A1+A5 | run_e1a_l2_shift_full.py | ~8行 | 增加 seed_strategy 版本标记 + is_checkpoint_complete 检查 |
| **P0** | A2+A4+A6 | 3个脚本函数签名 | ~9行 | 默认值改 None + raise ValueError（3处×3行） |
| **P0** | A8 | src/data/l2_shifts.py | ~6行 | L79/L120 的 RandomState(42) 改为 raise ValueError（2处×3行） |
| **P1** | A9 | run_e4_temperature_analysis.py | -9行 | 删除 L534-542 重复代码块 |

**R4 必修改计**：~23行改动，4个文件（3个脚本 + l2_shifts.py）

### 可选改进项清单（非必修）

| 攻击点 | 修复文件 | 改动量 | 说明 |
|--------|---------|--------|------|
| A3 | 3个脚本注释 | ~3行 | "必然"改为"极大概率" |
| A7 | 3个脚本种子派生 | ~6行 | rng创建移入noise-only分支（可选） |
| A10 | 3个脚本种子派生 | ~3行 | 使用全部128位哈希 / 删除冗余 `% (2**32)` |
| A11 | run_e4_temperature_analysis.py | ~1行 | pair_id 增加 `#cal` 角色标记 |

### 可关闭的攻击点

| 攻击点 | 关闭理由 |
|--------|---------|
| A12 | 不成立。Python 3.x 内可复现声明正确，反方自己承认"基本正确"。属于稻草人论证（将跨Python版本差异强加于跨进程声明）。 |
| A3 | 部分成立但严重度被夸大。注释措辞不精确属于轻微文档质量问题，0.016%碰撞概率下"必然"是合理工程近似。 |
| A10 | 部分成立但严重度被夸大。0.016%碰撞概率可忽略，`% (2**32)`冗余无害。属理论改进空间非实际风险。 |
| A11 | 部分成立但非正确性bug。反方自己承认"严格说不是bug"。语义精确性问题不影响结果正确性。 |

### 整体评估

**对反方攻击报告的评价**：

1. **攻击质量较高**：12个攻击点均附具体行号和代码证据，无臆测，覆盖7个攻击维度。反方在§4.3公平声明中诚实列出了正方修复正确的部分。

2. **核心攻击成立**：A1（断点续传混合种子）、A2（默认参数静默失败）、A8（回退路径矛盾）三个严重攻击真实成立，需R4修复。这些攻击指向**防御性不足**和**工程机制缺失**，而非核心算法错误。

3. **部分攻击严重度被夸大**：
   - A3（注释措辞）应为轻微非中等
   - A6（空值边界）与A2同源，应为轻微非中等
   - A10（32位截断）0.016%可忽略，应为轻微非中等
   - A11（语义偏移）非正确性bug，应为轻微非中等

4. **一个攻击不成立**：A12（Python版本差异）属于稻草人论证，反方自己承认"基本正确"。

5. **重复攻击**：A4与A2同源、A5与A1同源、A6与A2部分同源。反方将同一问题从不同维度重复列出，增加了攻击点数量但未增加实质内容。去重后实质攻击点为9个（含1个不成立）。

**对正方R3修复的评价**：

R3修复的**核心逻辑正确**（md5派生 + 跨进程可复现 + 3处调用方传参），反方在§4.3公平声明中确认。但修复存在**防御性不足**（A2默认参数、A8回退路径）和**工程机制缺失**（A1断点续传版本标记），需R4补强。

**裁决**：**有条件通过，需R4修复3个严重攻击点（A1、A2、A8）+ 1个清理项（A9）**。R4必修改计~23行，4个文件。修复后建议正方声明方案稳定。

---

## 审查透明性声明

本报告由反反方审查代理（GLM-5.2）独立撰写，基于对以下文件的完整阅读：
- `docs/p0r3_attack_p0_1.md`（反方攻击报告）
- `scripts/eval_l2_shift.py`（R3修改文件）
- `scripts/run_e1a_l2_shift_full.py`（R3修改文件）
- `scripts/run_e4_temperature_analysis.py`（R3修改文件）
- `src/data/l2_shifts.py`（被调用方，A8审查对象）

以及对 `RandomState(42)` 和 `apply_shift` 调用点的全局搜索验证。所有裁决均附具体行号和代码证据，无臆测。

**审查覆盖**：
- ✅ 反例是否真的成立（逐条验证反例）
- ✅ 是否稻草人论证（A12判定为稻草人）
- ✅ 是否误解前提（A11反方自己承认非bug）
- ✅ 攻击逻辑是否自洽（A3/A10/A11严重度被夸大）
- ✅ 严重程度是否被夸大（A3/A6/A10/A11降级）

**公平声明**：本审查既驳回不成立攻击（A12），也确认成立攻击（A1/A2/A8），并对夸大严重度的攻击进行降级（A3/A6/A10/A11）。审查目标是确保对抗实质性，非偏袒任何一方。
