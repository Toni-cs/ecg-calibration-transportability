# P0-1 R5反反方审查报告

## 审查概要
- 审查攻击点数：10
- 真攻击数：2（Attack-1, Attack-7）
- 伪攻击数：5（Attack-3, Attack-4, Attack-8, Attack-9, Attack-10）
- 部分成立数：3（Attack-2, Attack-5, Attack-6）
- 需R6修复数：2（Attack-1, Attack-7；Attack-2列为backlog改进项）

## 逐条审查

### Attack-1 [严重] eval_l2_shift.py 不写 __seed_strategy__ 标记，跨脚本共享JSON时标记体系失效
- **判定**：真攻击
- **验证**：
  1. 读取 `eval_l2_shift.py:185-194`，确认写入逻辑为 `all_results[f"seed{seed}"] = seed_results` + `existing[sk].update(seed_results)`，全文搜索 `__seed_strategy__` 无任何匹配 → **确实不写标记**。
  2. 读取 `run_e1a_l2_shift_full.py:431`，确认 `existing[sk]["__seed_strategy__"] = SEED_STRATEGY_VERSION` → run_e1a 写标记。
  3. 读取 `run_e1a_l2_shift_full.py:268`，确认 `is_checkpoint_complete` 检查 `seed_data.get("__seed_strategy__") != SEED_STRATEGY_VERSION` → 不匹配则视为不完整。
  4. 反例验证：用户只用 `eval_l2_shift.py` 跑新旧两版（legacy_42 + md5_v1），两者均无标记，静默混入同一 JSON，`eval_l2_shift.py` 自身无任何版本检查 → **反例成立**。
- **影响评估**：`eval_l2_shift.py` 是该实验的原始底层脚本（run_e1a 在其上构建），用户可合法独立使用。标记体系对该脚本完全失效，新旧种子策略结果可静默混用且无法检测。这是标记体系的设计盲区，非边缘场景。
- **修补方案**：
  - 文件：`scripts/eval_l2_shift.py`
  - 行号：line 192 之后（`existing[sk].update(seed_results)` 之后）
  - 改动：添加 `existing[sk]["__seed_strategy__"] = "md5_v1"`（与 run_e1a 一致的版本标记）
  - 同时在文件头添加常量 `SEED_STRATEGY_VERSION = "md5_v1"` 以便统一管理
  - 建议进一步将标记写入逻辑提取为共享函数（见 Attack-2 修补）

### Attack-2 [严重] run_e1a 与 eval_l2_shift 的 shifted_eval 代码重复，种子策略可能漂移
- **判定**：部分成立
- **验证**：
  1. 读取 `eval_l2_shift.py:36-65`、`run_e1a_l2_shift_full.py:168-200`、`run_e4_temperature_analysis.py:300-328`，确认三处 `shifted_eval`/`shifted_probs_labels` 的 md5 派生逻辑完全相同：`int(hashlib.md5(f"{pair_id}|{arch}|{train_seed}|{shift['name']}".encode()).hexdigest()[:8], 16) % (2**32)`。
  2. 代码重复属实，违反 DRY 原则。
  3. 但**当前三处逻辑完全一致，无实际 bug**。攻击描述的危害（"未来修改一处忘记另一处"）是假设性场景，非现存问题。
  4. 攻击的"无法检测"依赖 Attack-1（eval_l2_shift 不写标记）。若 Attack-1 修复后，eval_l2_shift 写入标记，则策略漂移可被 run_e1a 检测（标记不匹配 → 重跑）。
- **降级说明**：原严重度 严重 → 实际严重度 中等。理由：当前无实际 bug，危害为假设性未来风险。代码重复是可维护性问题，非正确性问题。修复 Attack-1 后，策略漂移变得可检测，进一步降低风险。
- **修补方案**（列为 backlog 改进项，非阻塞 R5）：
  - 将 `shifted_eval` 提取到 `src/data/l2_shifts.py` 或新建 `scripts/_shared_l2_eval.py`
  - 三处脚本统一 import，消除代码重复
  - 改动量：中等（提取函数 + 修改3处 import + 删除3处重复定义）

### Attack-3 [中等] per-seed 标记的 TOCTOU 竞态（并发跑同一JSON丢标记）
- **判定**：伪攻击
- **验证**：
  1. 读取 `run_e1a_l2_shift_full.py:309`（is_checkpoint_complete 读检查）和 `425-433`（写入），确认无文件锁。TOCTOU 竞态在理论层面存在。
  2. 但检查 `run_dir` 构造逻辑（line 304: `CKPT_ROOT / f"{source}_{target}" / arch / f"seed{seed}"`），每个 (source, target, arch, seed) 组合有**独立目录**和**独立 JSON 文件**。TOCTOU 竞态要求两个进程写**同一 JSON 文件**，即同一 (source, target, arch, seed) 组合。
  3. 并行启动两个 `run_e1a` 进程跑**完全相同的 checkpoint** 是异常用户行为（浪费算力，无实际理由）。
  4. 即使发生，md5 派生种子对同一 (pair_id, arch, train_seed, shift_name) 组合是**确定性的**，两进程产生**完全相同的数据**。后写入者覆盖先写入者，但数据相同 → **无实际数据丢失**。
  5. 攻击自身承认："md5 派生使两进程产生相同数据（确定性），所以数据丢失是主要风险，不是数据错误"。但如上分析，数据丢失也不发生（数据相同）。
  6. 攻击提到的"若代码漂移则不同"依赖 Attack-2 的假设性场景，构成循环依赖。
- **反驳理由**：TOCTOU 竞态要求异常用户行为（并发跑同一 checkpoint），即使触发，数据确定性保证两进程输出完全相同，覆盖不造成任何损失。危害场景依赖 Attack-2 的假设性代码漂移，不独立成立。

### Attack-4 [中等] __seed_strategy__ 标记可被伪造，无法验证数据实际来源
- **判定**：伪攻击
- **验证**：
  1. 读取 `run_e1a_l2_shift_full.py:268`，确认标记为纯字符串比较 `seed_data.get("__seed_strategy__") != SEED_STRATEGY_VERSION`，无签名/校验和。
  2. 标记可被手动伪造属实。
  3. 但 `__seed_strategy__` 标记的设计目标是**版本检查**（区分新旧种子策略），非**数据完整性校验**或**防篡改安全机制**。
  4. 用户手动编辑自己的结果 JSON 属于**自伤行为**，不在任何实验脚本的威胁模型内。同理，用户也可直接修改 checkpoint 权重、篡改 CSV 结果——这不是脚本的职责。
  5. 攻击自身承认："实际风险较低（需用户主动伪造）"且"可接受当前设计（信任用户不伪造）"。
- **反驳理由**：标记体系是版本检查机制，非安全防篡改机制。用户手动伪造自己的结果文件属于自伤行为，不在实验脚本的威胁模型内。攻击自身承认设计可接受，仅建议添加 docstring 声明假设——这是文档改进，非 bug 修复。

### Attack-5 [中等] 边界：noise.std() < 1e-12 时噪声档静默无效果
- **判定**：部分成立
- **验证**：
  1. 读取 `l2_shifts.py:106-107`（`_synthetic_noise`）和 `147-148`（`shift_noise`），确认 `if noise.std() > 1e-12: noise = noise / noise.std()`。当 std < 1e-12 时跳过归一化，噪声保持近零值。
  2. 后续 `shift_noise:149` 执行 `noise = noise * np.sqrt(noise_power)`，近零噪声 × 有限系数 ≈ 近零 → `signal + noise ≈ signal` → 噪声档退化为 identity。
  3. 边界在理论层面存在。
  4. 但实际触发条件分析：
     - ECG 信号长度：PTB-XL/Chapman/CPSC 数据集信号为 10 秒 × 500Hz = 5000 样本，降采样到 125Hz 仍为 1250 样本。
     - "em" 噪声：`n_steps = max(1, n_samples // 500)`。n_samples=1250 → n_steps=2。需 2 个步进的 amp 均接近 0 且正弦项接近 0，概率极低。
     - "bwl" 噪声：0.3×sin + 0.2×sin + 0.1×poly，三个独立正弦/多项式项同时为零的概率测度为零。
     - "ma" 噪声：滤波后白噪声，std < 1e-12 需 raw 全零，rng.randn 返回全零的概率测度为零。
  5. 攻击自身承认："实际触发概率极低（需 n_samples 极小且 rng 恰好产生近零噪声）"且"降采样到 fs125 后约 1250 点，不太可能触发"。
- **降级说明**：原严重度 中等 → 实际严重度 轻微。理由：边界在理论层面存在，但实际 ECG 信号长度（≥1250 样本）下触发概率测度趋近于零。bwl/ma 噪声的 std < 1e-12 概率测度严格为零（连续分布），em 噪声需极端 rng 输出。
- **修补方案**（可选，低优先级）：`l2_shifts.py:106` 和 `147` 处，将静默跳过改为 `raise ValueError(f"noise std={noise.std():.2e} < 1e-12, degenerate noise")` 或 log warning，使退化可见。

### Attack-6 [中等] md5 派生种子碰撞概率未声明
- **判定**：部分成立
- **验证**：
  1. 读取三处 md5 派生逻辑，确认 `int(hashlib.md5(...).hexdigest()[:8], 16) % (2**32)`。md5 hexdigest 为 32 位十六进制（128 bit），取前 8 位 = 32 bit。`int(..., 16)` 产生 32 位整数，`% (2**32)` 为恒等操作（32 bit 数 mod 2^32 = 自身）。
  2. 种子空间 = 2^32 ≈ 4.295×10^9。
  3. 实验组合数：攻击用 6方向×3架构×5种子×13档=1170。实际 run_e1a 用 2 架构（resnet1d+inceptiontime），6×2×5×13=780；含 mamba 附录为 1170。取 1170 保守估计。
  4. 生日碰撞概率公式：P ≈ n²/(2N) = 1170²/(2×2^32) = 1368900/8589934592 ≈ 1.594×10⁻⁴。
  5. **数学计算正确**，碰撞概率约 0.016%。
  6. 但攻击自身承认："这不会导致错误（两者是独立实验）"且"碰撞概率约 0.016%，可接受"。碰撞仅影响"不同实验必然不同种子"的声明，不影响结果正确性（独立实验的噪声相同不产生错误）。
- **降级说明**：原严重度 中等 → 实际严重度 轻微。理由：数学计算正确，但碰撞概率可忽略（0.016%），且碰撞不导致错误（攻击自身承认）。唯一可操作项是在 docstring 声明碰撞概率，属文档改进。
- **修补方案**（可选，低优先级）：在三处 md5 派生逻辑的注释中添加 `# 碰撞概率 ≈ 1.6e-4（1170 组合 / 2^32 种子空间），可接受`。

### Attack-7 [中等] eval_l2_shift.py 不写 safety 字段，两脚本对"完整"定义不对称
- **判定**：真攻击
- **验证**：
  1. 读取 `run_e1a_l2_shift_full.py:278`，确认 `if "safety" not in cell: return False` → 完整性检查要求 safety 字段。
  2. 读取 `eval_l2_shift.py:152-181`，确认 `method_results` 仅含 `raw_ece`, `mean_conf`, `pred_entropy`, `pi_shift_l1`, 各方法结果（`cal_ece`, `delta_ece`, `protocol`）。全文搜索 `safety` 无匹配 → **确实不写 safety**。
  3. 读取 `eval_l2_shift.py:192`，确认 `existing[sk].update(seed_results)`。`seed_results` 的键为 shift_name（如 `noise24`），`update` 会用新 cell（无 safety）**整体替换** `existing[sk][shift_name]`，而非合并字段。因此 run_e1a 写入的 safety 字段会被 eval_l2_shift 的无 safety cell 覆盖丢失。
  4. 反例验证：run_e1a 跑 seed42 写入含 safety 的结果 → eval_l2_shift 跑 seed42 覆盖为无 safety 结果 → run_e1a 再检查 seed42 → safety 丢失 → 视为不完整 → 重跑。若用户交替运行两脚本，run_e1a 每次都重跑 → **反例成立**。
  5. 注意：`__seed_strategy__` 标记不会被覆盖（不在 `seed_results` 键中），但 safety 会被覆盖（shift cell 整体替换）。
- **影响评估**：效率问题（反复重跑）+ 可用性问题（用户困惑）。非正确性问题（重跑产生正确结果）。但反复重跑浪费算力，且用户可能误以为 eval_l2_shift 跑完后 run_e1a 可续传。
- **修补方案**：
  - 方案A（推荐）：`run_e1a_l2_shift_full.py:278` 放宽完整性检查，将 `if "safety" not in cell: return False` 改为 `if "safety" not in cell: cell["safety"] = 0  # eval_l2_shift 产生的旧结果无 safety，默认 0`。即缺失 safety 时不视为不完整，而是默认为 0 并补写。
  - 方案B：`eval_l2_shift.py` 也计算并写入 safety 字段（需引入 brier_parts 计算，改动较大）。
  - 方案C：两脚本共用结果写入工具函数，统一字段集（与 Attack-1/Attack-2 修复合并）。
  - 推荐方案A，改动最小（1 行），且语义合理（eval_l2_shift 不计算 safety，默认 0 不影响 run_e1a 续传）。

### Attack-8 [轻微] docstring 语义偏移："rng=None 会立即 raise ValueError" 实际仅限 noise 类型
- **判定**：伪攻击
- **验证**：
  1. 读取 `l2_shifts.py:188-194` 的完整 docstring：
     ```
     rng: 随机数生成器，仅 noise 类型使用。传入同一 rng 可确保循环内
     每条信号获得不同噪声（rng 状态逐次推进）。对 noise 类型 shift，
     rng=None 会立即 raise ValueError（不再静默回退到 RandomState(42)，
     以避免跨实验种子碰撞和等长信号获得相同噪声的隐蔽错误）。
     ```
  2. docstring **明确包含** "对 noise 类型 shift，rng=None 会立即 raise ValueError" 的限定语。主语是"对 noise 类型 shift"，不是"任何 shift"。
  3. 攻击引用 docstring 时省略了 "对 noise 类型 shift" 限定语，仅引用 "rng=None 会立即 raise ValueError"，构成**断章取义**。
  4. docstring 第一句 "rng: 随机数生成器，仅 noise 类型使用" 已进一步明确 rng 仅对 noise 类型有意义。
- **反驳理由**：稻草人论证。攻击断章取义引用 docstring，省略了 "对 noise 类型 shift" 限定语和 "仅 noise 类型使用" 的前置说明。完整阅读 docstring 不会产生"任何 shift 类型 rng=None 都 raise"的误解。docstring 与代码行为完全一致。

### Attack-9 [轻微] apply_shift 的 rng 检查冗余（shift_noise 内部已检查）
- **判定**：伪攻击
- **验证**：
  1. 读取 `l2_shifts.py:197-198`（apply_shift 检查 `rng is None and t == "noise"`）、`120-124`（shift_noise 检查 `rng is None`）、`76-80`（_synthetic_noise 检查 `rng is None`）。三处检查属实。
  2. 调用链：`apply_shift` → `shift_noise` → `_synthetic_noise`。三层各有 rng 检查，确实冗余。
  3. 但这是**防御性编程**（defense in depth），非 bug：
     - 若 `shift_noise` 的检查被删除，`apply_shift` 的检查仍能保护经 apply_shift 调用的路径。
     - 若 `apply_shift` 的检查被删除，`shift_noise` 的检查仍能保护直接调用 shift_noise 的路径。
     - 两层检查互为冗余备份，提高鲁棒性。
  4. 攻击自身承认："无功能影响，仅代码冗余"、"这是防御性深度，可接受"、"保留冗余检查（防御性编程）"。
- **反驳理由**：攻击自身承认这是可接受的防御性编程，无功能影响。攻击的"反例"部分自相矛盾（"等等，shift_noise 已删除回退，会 raise。所以冗余检查是防御性编程，不是 bug"）。唯一建议是统一错误消息，属代码风格改进，非 bug 修复。

### Attack-10 [轻微] __seed_strategy__ 键名与未来 shift 名冲突的理论可能
- **判定**：伪攻击
- **验证**：
  1. 读取 `run_e1a_l2_shift_full.py:431`，确认 `existing[sk]["__seed_strategy__"] = SEED_STRATEGY_VERSION`，标记存储在 `seed_data`（即 `data["seed42"]`）下，与 shift 结果同级。
  2. 读取 `get_l2_shifts()` 返回的 13 档名称：fs250, fs125, leads6, leads3, leads2, leads1, noise24, noise12, noise6, noise0, noise-6, gain0.5, gain2.0。无任何 `__` 前缀名称。
  3. `__` 前缀是 Python 惯例表示"私有/特殊"名称，shift 档名遵循 `类型+参数` 命名规范，不会使用 `__` 前缀。
  4. 攻击描述的冲突场景要求未来有人**主动添加**名为 `__seed_strategy__` 的 shift 档，这需要同时违反命名规范和常识。
  5. 攻击自身承认："理论风险，实际极低（无人会用 __ 前缀命名 shift 档）"。
- **反驳理由**：理论风险，实际概率可忽略。shift 档名遵循 `类型+参数` 命名规范（fs/leads/noise/gain），`__` 前缀是 Python 私有名称惯例，两者命名空间自然隔离。攻击自身承认"实际极低"。建议的 `_meta` 子字典是合理的设计改进，但非 bug 修复，可列为 backlog。

## R6修复清单（按优先级排序）

| 优先级 | 攻击点 | 修补内容 | 文件 | 改动量 |
|--------|--------|---------|------|--------|
| P0（必修） | Attack-1 | eval_l2_shift.py 写入 `__seed_strategy__` 标记 | `scripts/eval_l2_shift.py:192` 后添加 1 行 | 1 行 |
| P1（必修） | Attack-7 | run_e1a 完整性检查放宽 safety 要求（缺失时默认 0） | `scripts/run_e1a_l2_shift_full.py:278` | 1 行 |
| P2（backlog） | Attack-2 | 提取 shifted_eval 到共享模块，消除三处代码重复 | `src/data/l2_shifts.py` 或 `scripts/_shared_l2_eval.py` + 3 处 import | 中等 |
| P3（可选） | Attack-5 | noise.std() < 1e-12 时 raise/log 而非静默 | `src/data/l2_shifts.py:106,147` | 2 行 |
| P4（可选） | Attack-6 | docstring 声明 md5 碰撞概率 | 3 处注释 | 3 行 |

## 结论

R5 修复在 `run_e1a_l2_shift_full.py` 内部（per-seed 标记 + raise ValueError）是有效的，能阻止该脚本自身新旧种子策略混用。但存在 **2 个真攻击**需 R6 修复：

1. **Attack-1 [严重→必修]**：`eval_l2_shift.py` 不写 `__seed_strategy__` 标记，导致该脚本独立使用时标记体系完全失效。修补简单（1 行）。
2. **Attack-7 [中等→必修]**：`eval_l2_shift.py` 不写 `safety` 字段，导致两脚本交替运行时 run_e1a 反复重跑。修补简单（1 行）。

**5 个伪攻击可关闭**：
- Attack-3（TOCTOU 竞态）：需异常并发 + 数据确定性保证无损失
- Attack-4（标记伪造）：用户自伤行为，不在威胁模型内
- Attack-8（docstring 偏移）：断章取义，docstring 已有限定语
- Attack-9（冗余检查）：攻击自身承认是可接受的防御性编程
- Attack-10（键名冲突）：理论风险，命名规范自然隔离

**3 个部分成立列为 backlog**：
- Attack-2（代码重复）：当前无 bug，DRY 改进列为 backlog
- Attack-5（噪声退化边界）：理论存在，实际触发概率测度趋近零
- Attack-6（碰撞概率未声明）：数学正确，概率可忽略，仅需文档补充

**R5 修复判定**：**有条件通过**。R5 在 run_e1a 内部的修复有效，但 eval_l2_shift.py 的标记盲区（Attack-1）和 safety 不对称（Attack-7）需 R6 补齐。建议 R6 修复 Attack-1 + Attack-7（共 2 行改动），即可关闭所有真攻击。
