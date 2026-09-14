# P0-1 R5反方攻击报告

## 攻击摘要
- 审查文件：
  - `src/data/l2_shifts.py`（raise ValueError + docstring）
  - `scripts/eval_l2_shift.py`（rng 传入检查）
  - `scripts/run_e1a_l2_shift_full.py`（per-seed 版本标记）
  - `scripts/run_e4_temperature_analysis.py`（rng 传入检查）
- 发现攻击点：10个（致命0 / 严重2 / 中等5 / 轻微3）
- 审查维度：7个维度全覆盖（反例构造/逻辑断链/隐含假设/边界失效/自相矛盾/量级错误/语义偏移）

## 修复确认（正方已正确处理）
- ✅ `l2_shifts.py` `_synthetic_noise`/`shift_noise`/`apply_shift` 三处 rng=None 均 raise ValueError（line 76-80, 120-124, 197-198）
- ✅ `l2_shifts.py` 已删除 `import warnings`（无残留）
- ✅ `apply_shift` docstring 已更新（line 188-194）
- ✅ `eval_l2_shift.py` shifted_eval 传入 rng（line 51-54, 58）
- ✅ `run_e1a_l2_shift_full.py` shifted_eval 传入 rng（line 186-189, 193）
- ✅ `run_e4_temperature_analysis.py` shifted_probs_labels 传入 rng（line 314-317, 322）
- ✅ `run_e1a_l2_shift_full.py` per-seed 标记写入（line 431）+ 检查（line 268）

## 攻击点列表

### Attack-1 [严重] eval_l2_shift.py 不写 __seed_strategy__ 标记，跨脚本共享JSON时标记体系失效
- **维度**：自相矛盾 + 逻辑断链
- **位置**：`scripts/eval_l2_shift.py:185-194` vs `scripts/run_e1a_l2_shift_full.py:431`
- **描述**：两个脚本共享同一 `l2_shift_results.json` 文件，但 `eval_l2_shift.py` 写结果时不写 `__seed_strategy__` 标记，而 `run_e1a_l2_shift_full.py` 的 `is_checkpoint_complete` 要求该标记存在。这导致标记体系只对 `run_e1a` 自身有效，对 `eval_l2_shift` 产生的结果无法区分新旧种子策略。
- **反例**：
  1. 用户先用**旧版** `eval_l2_shift.py`（RandomState(42) 回退）跑 `ptbxl_chapman/resnet1d/seed42`，写入 `seed42` 无标记，数据是 legacy_42 策略
  2. 用户再用**新版** `eval_l2_shift.py`（md5 派生）跑 `seed43`，写入 `seed43` 无标记
  3. 此时 JSON：`{seed42: {legacy_42数据}, seed43: {md5_v1数据}}`，两者均无 `__seed_strategy__`
  4. 用户跑 `run_e1a_l2_shift_full.py`，检查 seed42 → 无标记 → 重跑（正确）；检查 seed43 → 无标记 → 重跑（浪费但正确）
  5. **但**：如果用户只跑 `eval_l2_shift.py` 不跑 `run_e1a`，新旧种子策略的结果会**静默混在同一文件**，无任何标记可区分。`eval_l2_shift.py` 自身不做任何版本检查。
- **影响**：`eval_l2_shift.py` 独立使用时，R5 的标记保护完全失效。新旧种子策略结果可混用且无法检测。`run_e1a` 用户不受影响（会重跑），但 `eval_l2_shift` 用户直接受影响。
- **建议**：`eval_l2_shift.py` 也应写入 `__seed_strategy__` 标记，或两脚本共用一个结果写入工具函数。

### Attack-2 [严重] run_e1a 与 eval_l2_shift 的 shifted_eval 代码重复，种子策略可能漂移
- **维度**：隐含假设 + 自相矛盾
- **位置**：`scripts/run_e1a_l2_shift_full.py:168-200` vs `scripts/eval_l2_shift.py:36-65`
- **描述**：两个脚本各自独立定义了 `shifted_eval`，种子派生逻辑（md5 哈希）复制粘贴。R5 修复假设两者始终一致，但无任何机制保证。未来修改一处忘记另一处，会导致两个脚本对同一实验产生不同噪声，且无标记可检测（因 eval_l2_shift 不写标记，见 Attack-1）。
- **反例**：
  1. 当前两脚本 md5 派生键均为 `f"{pair_id}|{arch}|{train_seed}|{shift['name']}"`
  2. 假设未来 `run_e1a` 改为 `f"{pair_id}|{arch}|{train_seed}|{shift['name']}|v2"`（新增版本后缀）
  3. `eval_l2_shift` 忘记同步修改
  4. 同一 checkpoint 的 `l2_shift_results.json` 会被两个脚本用不同种子策略交替覆盖
  5. `run_e1a` 的 `__seed_strategy__` 标记仍是 "md5_v1"，但数据已被 `eval_l2_shift` 的旧策略污染
- **影响**：代码重复是隐含的"双源真理"假设，违反 DRY 原则。种子策略漂移会导致结果不可复现且无法检测。
- **建议**：将 `shifted_eval` 提取到共享模块（如 `src/data/l2_shifts.py` 或 `scripts/_shared.py`），单一来源。

### Attack-3 [中等] per-seed 标记的 TOCTOU 竞态（并发跑同一JSON丢标记）
- **维度**：边界失效（并发）
- **位置**：`scripts/run_e1a_l2_shift_full.py:309-312, 425-433`
- **描述**：`is_checkpoint_complete` 检查（读）和 `evaluate_one_checkpoint` 写入（写）之间无文件锁。若用户并行启动两个 `run_e1a` 进程跑同一 checkpoint（或同一 JSON 不同 seed），存在 TOCTOU（Time-Of-Check-To-Time-Of-Use）竞态。
- **反例**：
  1. 进程A 检查 seed42 → 不完整 → 开始评估
  2. 进程B 检查 seed42 → 不完整 → 开始评估
  3. 进程A 先完成，写入 `{seed42: {__seed_strategy__: md5_v1, ...}}`
  4. 进程B 后完成，`existing = load_existing_results` 读到A的结果，`existing[sk].update(seed_results)` 覆盖A的结果，写入 `{seed42: {__seed_strategy__: md5_v1, B的结果}}`
  5. 结果：A 的结果丢失，B 的结果保留。若A和B的 rng 状态不同（因 md5 派生相同应相同，但若代码漂移则不同），结果不可复现。
- **影响**：并发场景下结果可能丢失或覆盖。md5 派生使两进程产生相同数据（确定性），所以数据丢失是主要风险，不是数据错误。
- **建议**：写入时用文件锁（`fcntl.flock` Unix / `msvcrt.locking` Windows）或原子写入（写临时文件后 rename）。

### Attack-4 [中等] __seed_strategy__ 标记可被伪造，无法验证数据实际来源
- **维度**：隐含假设
- **位置**：`scripts/run_e1a_l2_shift_full.py:268, 431`
- **描述**：`__seed_strategy__` 是纯字符串标记，写入时无签名/校验和。假设该标记存在且等于 "md5_v1" 即信任数据是 md5 派生策略产生的。但标记可被手动伪造。
- **反例**：
  1. 用户有旧版结果 `seed42 = {fs250: {...legacy_42数据...}, noise24: {...legacy_42数据...}}`
  2. 用户手动编辑 JSON，添加 `"__seed_strategy__": "md5_v1"`
  3. `run_e1a` 检查 → 标记匹配 → 视为完整 → 跳过重跑
  4. 旧种子策略结果被当作新策略结果使用，与 md5_v1 结果混入同一 390 矩阵
- **影响**：标记体系依赖"标记存在即数据可信"的假设，该假设在用户手动编辑或部分写入失败时不成立。实际风险较低（需用户主动伪造），但理论上是安全漏洞。
- **建议**：可接受当前设计（信任用户不伪造），但应在 docstring 声明此假设。

### Attack-5 [中等] 边界：noise.std() < 1e-12 时噪声档静默无效果
- **维度**：边界失效
- **位置**：`src/data/l2_shifts.py:106-107, 147-148`
- **描述**：`_synthetic_noise` 和 `shift_noise` 在噪声标准差 < 1e-12 时跳过归一化，保留全零噪声。此时信号 + 零噪声 = 原信号，噪声档静默退化为 identity。
- **反例**：
  1. `noise_type == "em"`，`n_samples` 很小（如 10）
  2. `n_steps = max(1, 10 // 500) = 1`，仅 1 个步进
  3. 若该步进的 `amp` 恰好接近 0（rng.uniform(-0.5, 0.5) 可能返回接近 0），且正弦项也接近 0
  4. `noise.std() < 1e-12` → 跳过归一化 → 噪声全零
  5. `shift_noise` 返回原信号，noise0 档与 raw 无差异，safety 计算基于无噪声信号
- **影响**：极短信号（降采样到 fs125 后约 1250 点，不太可能触发，但理论存在）下噪声档失效，安全率矩阵含无效单元格。实际触发概率极低（需 n_samples 极小且 rng 恰好产生近零噪声）。
- **建议**：`noise.std() < 1e-12` 时应 raise ValueError 或 log warning，而非静默返回零噪声。

### Attack-6 [中等] md5 派生种子碰撞概率未声明
- **维度**：量级错误 + 隐含假设
- **位置**：`scripts/run_e1a_l2_shift_full.py:186-188`（及 eval_l2_shift.py:51-53, run_e4:314-316）
- **描述**：`int(hashlib.md5(...).hexdigest()[:8], 16) % (2**32)` 取 md5 前 8 位十六进制（32 位），再 mod 2^32（实际无影响，因前8位已 < 2^32）。32 位种子空间有 2^32 ≈ 4.3×10^9 个可能。实验组合数：6方向 × 3架构 × 5种子 × 13档 = 1170 个。生日碰撞概率 ≈ 1170^2 / (2 × 2^32) ≈ 1.6×10^-4。
- **反例**：若两个不同实验组合（如 `ptbxl_chapman|resnet1d|42|noise24` 和 `chapman_cpsc|inceptiontime|45|noise6`）的 md5 前 8 位恰好相同，两者获得相同 noise_seed，噪声序列相同。这不会导致错误（两者是独立实验），但会破坏"不同实验必然不同种子"的声明。
- **影响**：碰撞概率约 0.016%，可接受但未在 docstring 声明。若碰撞发生，两个实验的噪声相同，可能影响跨实验聚合统计（如安全率矩阵的独立性假设）。
- **建议**：docstring 声明碰撞概率 ≈ 1.6×10^-4，或使用 64 位种子（取 md5 前 16 位）。

### Attack-7 [中等] eval_l2_shift.py 不写 safety 字段，两脚本对"完整"定义不对称
- **维度**：自相矛盾
- **位置**：`scripts/eval_l2_shift.py:152-180` vs `scripts/run_e1a_l2_shift_full.py:278-279`
- **描述**：`run_e1a` 的 `is_checkpoint_complete` 要求每档含 `safety` 字段（line 278），但 `eval_l2_shift.py` 不写 `safety`。两脚本共享同一 JSON，对"完整"的定义不对称。
- **反例**：
  1. `run_e1a` 跑 seed42，写入含 `safety` 的完整结果
  2. `eval_l2_shift.py` 跑 seed42，`existing[sk].update(seed_results)` 用不含 `safety` 的结果覆盖
  3. `run_e1a` 再检查 seed42 → `safety` 字段丢失 → 视为不完整 → 重跑
  4. 若用户反复交替运行两脚本，`run_e1a` 每次都重跑，永无止境
- **影响**：效率问题（反复重跑），非正确性问题。但若用户误以为 `eval_l2_shift.py` 跑完后 `run_e1a` 可续传，会困惑。
- **建议**：`eval_l2_shift.py` 应计算并写入 `safety` 字段，或 `run_e1a` 的完整性检查放宽 `safety` 要求（仅检查 `__seed_strategy__` + `ts.cal_ece`）。

### Attack-8 [轻微] docstring 语义偏移："rng=None 会立即 raise ValueError" 实际仅限 noise 类型
- **维度**：语义偏移
- **位置**：`src/data/l2_shifts.py:188-194`
- **描述**：docstring 写 "rng=None 会立即 raise ValueError（不再静默回退到 RandomState(42)..."，但实际 `apply_shift` 仅在 `t == "noise"` 时 raise（line 197）。对 downsample/leads/gain 类型，rng=None 不 raise（因这些变换不用 rng）。docstring 的"立即 raise"可能被误解为"任何 shift 类型 rng=None 都 raise"。
- **反例**：调用 `apply_shift(signal, {"type": "downsample", "params": {"target_hz": 250}}, rng=None)` 不 raise，正常返回。但 docstring 暗示会 raise。
- **影响**：文档与行为轻微不一致，可能误导调用方。实际行为是合理的（非 noise 类型不需要 rng），但 docstring 应更精确。
- **建议**：docstring 改为 "对 noise 类型 shift，rng=None 会立即 raise ValueError；非 noise 类型不使用 rng"。

### Attack-9 [轻微] apply_shift 的 rng 检查冗余（shift_noise 内部已检查）
- **维度**：逻辑断链
- **位置**：`src/data/l2_shifts.py:197-198` vs `shift_noise:120-124`
- **描述**：`apply_shift` 在 line 197 检查 `rng is None and t == "noise"` 并 raise，然后 line 206 调用 `shift_noise(..., rng=rng)`，`shift_noise` 内部 line 120 又检查 `rng is None` 并 raise。两层检查冗余，且错误消息不同（apply_shift 的更简略）。
- **反例**：若未来 `shift_noise` 的检查被删除（误以为 apply_shift 已检查），但有人直接调用 `shift_noise` 不经 `apply_shift`，则 rng=None 不 raise，回退到... 等等，shift_noise 已删除回退，会 raise。所以冗余检查是防御性编程，不是 bug。
- **影响**：无功能影响，仅代码冗余。若 `shift_noise` 的检查被删除，`apply_shift` 的检查仍能保护，反之亦然。这是防御性深度，可接受。
- **建议**：保留冗余检查（防御性编程），但统一错误消息。

### Attack-10 [轻微] __seed_strategy__ 键名与未来 shift 名冲突的理论可能
- **维度**：边界失效
- **位置**：`scripts/run_e1a_l2_shift_full.py:268, 431`
- **描述**：`__seed_strategy__` 存储在 `seed_data`（即 `data["seed42"]`）下，与 shift 结果（如 `data["seed42"]["noise24"]`）同级。若未来有人添加名为 `__seed_strategy__` 的 shift 档（极不可能但理论存在），会被 `is_checkpoint_complete` 误判为版本标记而非 shift 结果。
- **反例**：未来扩展 shift 档，新增 `__seed_strategy__` 档（如某种策略性移位），`get_l2_shifts()` 返回含该名的 shift。`is_checkpoint_complete` line 270 遍历 `shift_names`，查找 `seed_data["__seed_strategy__"]`，找到字符串 "md5_v1" 而非 dict，`cell["ts"]` 报 KeyError。
- **影响**：理论风险，实际极低（无人会用 `__` 前缀命名 shift 档）。但键名空间未隔离是设计缺陷。
- **建议**：将标记存到独立键如 `_meta`：`data["seed42"]["_meta"]["seed_strategy"]`，与 shift 结果隔离。

## 维度覆盖确认

| 维度 | 覆盖 | 发现攻击点 |
|------|------|-----------|
| 1. 反例构造 | ✅ | Attack-1, Attack-4, Attack-5, Attack-10 |
| 2. 逻辑断链 | ✅ | Attack-1, Attack-9 |
| 3. 隐含假设 | ✅ | Attack-2, Attack-4, Attack-6 |
| 4. 边界失效 | ✅ | Attack-3, Attack-5, Attack-10 |
| 5. 自相矛盾 | ✅ | Attack-1, Attack-2, Attack-7 |
| 6. 量级错误 | ✅ | Attack-6 |
| 7. 语义偏移 | ✅ | Attack-8 |

## 结论

R5 修复在 `run_e1a_l2_shift_full.py` 内部（per-seed 标记 + raise ValueError）是有效的，能阻止该脚本自身新旧种子策略混用。但存在两个**严重**攻击点：

1. **Attack-1**：`eval_l2_shift.py` 不写 `__seed_strategy__` 标记，导致该脚本独立使用时标记体系完全失效，新旧结果可静默混用。
2. **Attack-2**：两脚本 `shifted_eval` 代码重复，种子策略可能漂移且无法检测。

这两个攻击点联合作用：`eval_l2_shift.py` 既不写标记，又独立维护种子派生逻辑，是标记体系的盲区。建议 R6 修复：
- 将 `shifted_eval` 提取到共享模块
- `eval_l2_shift.py` 也写入 `__seed_strategy__` 标记
- 或合并两脚本的 JSON 写入逻辑为统一工具函数

其余 8 个攻击点为中等或轻微，不阻塞 R5 合入，但应列入后续修复 backlog。
