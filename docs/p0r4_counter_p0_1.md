# R4反反方审查报告：P0-1

## 审查摘要
- 反方攻击报告：docs/p0r4_attack_p0_1.md
- 审查文件：eval_l2_shift.py, run_e1a_l2_shift_full.py, run_e4_temperature_analysis.py, l2_shifts.py
- 攻击点总数：9（A1-A8 + A10；A9 为"未发现可攻击点"占位，非实际攻击）
- 成立攻击：6（A1, A2, A3, A5, A6, A8）
- 部分成立攻击：2（A4, A7）
- 不成立攻击：1（A10）
- 需R5修补项：4（A1+A5 合并、A2、A3+A6 合并、A8）

## 逐条审查

### Attack-1: 顶层版本标记，部分重跑导致混合种子数据集

**判定**：成立

**理由**：

经逐行代码验证，反方构造的反例完全成立。核心问题在于版本标记写入位置（顶层 `existing["__seed_strategy__"]`）与数据组织方式（per-seed `existing["seed42"]`、`existing["seed43"]`...）不匹配。

**代码证据链**（已逐行核对）：

1. `run_e1a_l2_shift_full.py` L264：`if data.get("__seed_strategy__") != SEED_STRATEGY_VERSION: return False` —— 只检查**顶层**版本标记，不检查 per-seed
2. `run_e1a_l2_shift_full.py` L425-429：`existing = load_existing_results(run_dir)` 加载旧文件（含所有 seed），`existing[sk].update(seed_results)` **仅更新当前 seed** 的数据，其他 seed 的旧数据原样保留
3. `run_e1a_l2_shift_full.py` L431：`existing["__seed_strategy__"] = SEED_STRATEGY_VERSION` —— 写入**顶层**标记，无论实际只重跑了哪个 seed
4. `run_e1a_l2_shift_full.py` L309/L586：`if not args.force and is_checkpoint_complete(...)` —— `--force` 跳过完整性检查，允许部分重跑

**反例执行路径**（已验证可行）：
1. R2 版本 `run_e1a_l2_shift_full.py` 生成 5 个 seed 的旧结果（用 `RandomState(42)`，含 `safety` 字段，无 `__seed_strategy__`）
2. R4 版本运行 `--seeds 42 --force`：
   - L586: `not args.force` = False → 跳过 resume 检查 → 调用 `evaluate_one_checkpoint(force=True)`
   - L309: `not force` = False → 跳过 resume 检查 → 执行评估
   - L425: 加载旧文件（5 个 seed 旧数据）
   - L429: `existing["seed42"].update(seed_results)` —— 仅 seed42 更新为 md5 派生数据
   - L431: `existing["__seed_strategy__"] = "md5_v1"` —— 顶层标记写入
   - L433: 保存 —— 文件含 seed42 新数据 + seed43/44/45/46 旧数据 + 顶层 `"md5_v1"`
3. R4 版本运行 `--seeds 42 43 44 45 46`（不带 `--force`）：
   - 对 seed 43 调用 `is_checkpoint_complete(run_dir, 43, shift_names)`
   - L264: `data.get("__seed_strategy__")` = `"md5_v1"` == `SEED_STRATEGY_VERSION` → 通过
   - L266-279: `seed43` 存在，每档含 `safety` 字段 → 通过
   - 返回 True → L588: `existing.get("seed43", {})` 返回**旧数据**（用 `RandomState(42)`）
4. **390 矩阵中 seed42 用 md5 派生，seed43/44/45/46 用 `RandomState(42)` —— 混合种子数据集**

这正是 R4 修复声称要消除的问题，但在部分重跑场景下静默失效。反方定级"严重"合理。

**修补方案**：

文件：`scripts/run_e1a_l2_shift_full.py`

改动 1（L263-265，删除顶层检查）：
```python
# 删除这两行：
#     # P0-1 R4修复（A1+A5）：seed_strategy 版本检查
#     if data.get("__seed_strategy__") != SEED_STRATEGY_VERSION:
#         return False
```

改动 2（L269 后，添加 per-seed 检查）：
```python
    seed_data = data[sk]
    # P0-1 R5修复（A1）：per-seed 版本检查，防止部分重跑导致混合种子策略
    if seed_data.get("__seed_strategy__") != SEED_STRATEGY_VERSION:
        return False
```

改动 3（L431，改为 per-seed 写入）：
```python
    # 旧：existing["__seed_strategy__"] = SEED_STRATEGY_VERSION
    # 新：
    existing[sk]["__seed_strategy__"] = SEED_STRATEGY_VERSION
```

改动 4（L251-253 docstring 同步更新）：
```python
    """断点续传检查：l2_shift_results.json 是否已含该 seed 的全部 13 档×所有方法。

    判据：
    1. seed_strategy 版本匹配（P0-1 R5修复 A1）：per-seed __seed_strategy__ 字段
       必须等于 SEED_STRATEGY_VERSION（"md5_v1"）。旧结果（legacy_42 / 缺失）
       视为不完整，需重跑，避免新旧种子策略混用。
    2. seed{N} 键下包含全部 13 档名，且每档含 ts 方法的 cal_ece（安全率依赖项）。
    """
```

净改动：约 +4 行 -2 行 = +2 行

---

### Attack-2: apply_shift docstring 与代码不一致（R4 修复遗漏）

**判定**：成立

**理由**：

经核对 `src/data/l2_shifts.py`，反方指控完全属实。

**代码证据**：
- L193-194 docstring：`若 None 则每次创建 RandomState(42)（会导致等长信号获得相同噪声，仅用于向后兼容）。`
- L78-82 `_synthetic_noise`：`if rng is None: raise ValueError("rng must be explicitly provided; RandomState(42) fallback was removed ...")`
- L122-126 `shift_noise`：`if rng is None: raise ValueError("rng must be explicitly provided; RandomState(42) fallback was removed ...")`
- L212-213 `apply_shift`：`return shift_noise(signal, p["noise_type"], p["snr_db"], rng=rng)` —— 将 `rng=None` 透传给 `shift_noise`

**矛盾确认**：docstring 声称 `rng=None` 时"创建 `RandomState(42)`"，但实际行为是 `shift_noise` 抛出 `ValueError`。R4 修复了 `shift_noise`/`_synthetic_noise` 的回退路径（改 raise），但**遗漏了 `apply_shift` 的 docstring 同步更新**。

`apply_shift` 是 `shift_noise` 的直接公开调用方，docstring 与实际行为矛盾会误导未来维护者，使其认为 `rng=None` 是合法的向后兼容路径。反方定级"严重"合理（文档-代码不一致影响 API 可用性）。

**修补方案**：

文件：`src/data/l2_shifts.py`

改动（L192-194，更新 docstring）：
```python
    """对单条信号施加移位变换。

    rng: 可选随机数生成器，仅 noise 类型使用。传入同一 rng 可确保循环内
    每条信号获得不同噪声（rng 状态逐次推进）。若 None 且 shift 类型为 noise，
    则 raise ValueError（要求调用方显式传入 rng 以保证跨实验种子独立性）。
    非 noise 类型（downsample/leads/gain）不使用 rng，rng=None 合法。
    """
```

净改动：约 +2 行 -1 行 = +1 行

---

### Attack-3: apply_shift warnings.warn 消息与实际行为矛盾

**判定**：成立

**理由**：

经核对 `src/data/l2_shifts.py`，反方指控完全属实。

**代码证据**：
- L198-205 `apply_shift`：
  ```python
  if rng is None and t == "noise":
      warnings.warn(
          "apply_shift called with rng=None for noise shift. "
          "Each signal will receive identical noise (RandomState(42)). "
          "Pass rng=np.random.RandomState(seed) from caller for per-signal noise.",
          UserWarning,
          stacklevel=2,
      )
  ```
- L212-213：`return shift_noise(signal, p["noise_type"], p["snr_db"], rng=rng)` —— `rng=None` 透传
- L122-126 `shift_noise`：`raise ValueError(...)`

**执行流程确认**（`apply_shift(sig, noise_shift, rng=None)`）：
1. L198: `rng is None and t == "noise"` → True → 发 UserWarning（声称"会用 `RandomState(42)`"）
2. L212-213: 调用 `shift_noise(..., rng=None)`
3. L122-126: `raise ValueError`（声称"必须提供 rng"）

用户会先看到警告（说会做 A），然后立即看到 ValueError（说必须做 B）。**两个消息直接矛盾**。R4 修复了 `shift_noise`/`_synthetic_noise`，但**遗漏了 `apply_shift` 的 `warnings.warn` 同步更新**。反方定级"严重"合理。

**修补方案**：

文件：`src/data/l2_shifts.py`

改动（L198-205，删除 warnings.warn 块，改为提前 raise）：
```python
    # 旧（删除）：
    #     if rng is None and t == "noise":
    #         warnings.warn(
    #             "apply_shift called with rng=None for noise shift. "
    #             "Each signal will receive identical noise (RandomState(42)). "
    #             "Pass rng=np.random.RandomState(seed) from caller for per-signal noise.",
    #             UserWarning,
    #             stacklevel=2,
    #         )
    # 新：
    if rng is None and t == "noise":
        raise ValueError(
            "apply_shift requires rng for noise shift; "
            "pass rng=np.random.RandomState(seed) from caller for per-signal noise. "
            "RandomState(42) fallback was removed to prevent cross-experiment seed collision."
        )
```

此修补同时消解 A6（warnings.warn 冗余）和 A8（签名矛盾，因为现在 `apply_shift` 对 noise 类型提前 raise，不再依赖下游 `shift_noise` 兜底）。

净改动：约 +5 行 -7 行 = -2 行

---

### Attack-4: eval_l2_shift.py 不写入 __seed_strategy__ 版本标记，设计不一致

**判定**：部分成立（降级为轻微）

**理由**：

反方指控的事实成立——`eval_l2_shift.py` L186-194 确实不写入 `__seed_strategy__` 字段。但反方对后果的描述存在夸大，需降级。

**事实确认**：
- `eval_l2_shift.py` L186-194：保存逻辑中无 `__seed_strategy__` 写入
- `run_e1a_l2_shift_full.py` L264：`is_checkpoint_complete` 检查 `__seed_strategy__`
- `run_e1a_l2_shift_full.py` L431：写入 `__seed_strategy__`

**但功能行为正确**（反方自己也承认"功能正确（重跑是安全的）"）：

1. **场景 A**：用户先跑 `eval_l2_shift.py`（无标记），再跑 `run_e1a_l2_shift_full.py`（不带 `--force`）
   - `is_checkpoint_complete` 发现无 `__seed_strategy__` → 返回 False → **重跑所有 seed**
   - 结果正确（重跑后写入标记），仅效率低

2. **场景 B**：用户先跑 `run_e1a_l2_shift_full.py`（写入标记），再跑 `eval_l2_shift.py`
   - `eval_l2_shift.py` L188: `existing = json.loads(...)` 加载含 `__seed_strategy__` 的旧文件
   - L192: `existing[sk].update(seed_results)` 仅更新 seed 数据
   - L193: `all_results = existing` —— **`__seed_strategy__` 被保留**（因为 existing 含此字段）
   - L194: 保存 —— `__seed_strategy__` 不丢失

3. **关键点**：两个脚本使用**相同的 md5 派生逻辑**（`eval_l2_shift.py` L51-53 与 `run_e1a_l2_shift_full.py` L186-188 完全一致），所以即使混用，数据本身的种子策略一致，不会产生 A1 那样的混合种子数据集问题。

**降级理由**：反方定级"中等"偏高。实际后果仅为"场景 A 下效率低（重跑）"，无正确性风险。设计不一致真实存在，但属**轻微**级别（代码异味，非 bug）。

**修补方案**（可选，非必修）：

若为设计一致性，可在 `eval_l2_shift.py` L193 后添加：
```python
        # P0-1 R5修复（A4）：与 run_e1a_l2_shift_full.py 保持一致，写入版本标记
        all_results["__seed_strategy__"] = "md5_v1"
```

但需注意：`eval_l2_shift.py` 不定义 `SEED_STRATEGY_VERSION` 常量，硬编码字符串 `"md5_v1"` 会引入维护负担。建议提取到公共模块（见 A7）。

**反驳**（针对"中等"定级）：反方称"两个脚本产生的 `l2_shift_results.json` 格式不一致——一个有版本标记，一个没有"，但这是**设计差异**而非 bug：`run_e1a_l2_shift_full.py` 有断点续传需求故需版本标记，`eval_l2_shift.py` 是单次运行脚本无此需求。功能行为正确，定级应降为轻微。

---

### Attack-5: 隐含假设"用户不会部分重跑"未显式声明

**判定**：成立

**理由**：

此攻击与 A1 同源。代码确实支持部分重跑（`--seeds` 参数 + `--force` 标志），但顶层版本标记机制假设"全量重跑或全量不重跑"。

**代码证据**：
- `run_e1a_l2_shift_full.py` L541: `ap.add_argument("--seeds", nargs="+", type=int, default=SEEDS, help="种子列表")` —— 显式支持部分 seed
- L536: `ap.add_argument("--force", action="store_true", help="强制重跑，忽略断点续传")` —— 显式支持强制重跑
- L431: `existing["__seed_strategy__"] = SEED_STRATEGY_VERSION` —— 顶层标记，不区分 per-seed

**隐含假设确认**：R4 的版本标记机制隐含假设"用户要么全部重跑（`--force` 全部 seed），要么全部不重跑（不带 `--force`）"。但代码同时支持 `--seeds 42 --force`（部分重跑），与版本标记机制冲突。此假设未在代码注释或 docstring 中显式声明，也未在代码中防御。

反方定级"中等"合理。此攻击与 A1 同源，修 A1（per-seed 版本标记）即自动消解 A5。

**修补方案**：与 A1 合并（per-seed 版本标记）。无需独立修补。

---

### Attack-6: apply_shift warnings.warn 是冗余/误导性代码

**判定**：成立

**理由**：

此攻击与 A3 同源。`warnings.warn`（L198-205）执行后，`shift_noise`（L122-126）立即 `raise ValueError`，故 `warnings.warn` 是冗余的。

**代码证据**：
- L198-205: `warnings.warn(...)` —— 发警告
- L212-213: `shift_noise(..., rng=None)` —— 调用
- L122-126: `raise ValueError(...)` —— 立即抛异常

用户会看到两个矛盾的提示（见 A3），`warnings.warn` 无实际价值。反方定级"轻微"合理（当前 3 个调用方都传非 None rng，不会触发）。

**修补方案**：与 A3 合并（删除 `warnings.warn`，改为提前 `raise ValueError`）。无需独立修补。

---

### Attack-7: SEED_STRATEGY_VERSION 常量只在 run_e1a_l2_shift_full.py 定义

**判定**：部分成立（轻微，设计改进建议）

**理由**：

反方指控的事实成立——`SEED_STRATEGY_VERSION = "md5_v1"` 只在 `run_e1a_l2_shift_full.py` L140 定义。`eval_l2_shift.py` 和 `run_e4_temperature_analysis.py` 未定义。

**但反方自己承认"当前不影响正确性"且"非 bug"**：
- 只有 `run_e1a_l2_shift_full.py` 有断点续传检查（`is_checkpoint_complete`），故只有它需要 `SEED_STRATEGY_VERSION`
- `eval_l2_shift.py` 是单次运行脚本，无断点续传
- `run_e4_temperature_analysis.py` 不读写 `l2_shift_results.json`，无版本标记需求

**判定**：这是合理的设计改进建议，非攻击点。当前设计正确（每个脚本按需定义常量）。若未来需要在其他脚本中使用版本标记，再提取到公共模块即可。反方定级"轻微"合理。

**修补方案**（可选，非必修）：

若要改进，可提取到 `src/data/l2_shifts.py`：
```python
# 在 l2_shifts.py 顶部添加
SEED_STRATEGY_VERSION = "md5_v1"
```
然后在 `run_e1a_l2_shift_full.py` 改为 `from src.data.l2_shifts import SEED_STRATEGY_VERSION`。

但当前无正确性风险，建议留至 R5+ 或重构时处理。

---

### Attack-8: apply_shift 保留 rng=None 默认值与 shift_noise raise ValueError 矛盾

**判定**：成立

**理由**：

经核对 `src/data/l2_shifts.py`，反方指控属实。

**代码证据**：
- L188: `def apply_shift(signal: np.ndarray, shift: dict, rng: np.random.RandomState | None = None) -> np.ndarray:` —— 签名默认值 `rng=None`，类型注解含 `None`
- L122-126: `shift_noise` 中 `if rng is None: raise ValueError(...)`
- L212-213: `apply_shift` 调用 `shift_noise(..., rng=rng)` —— 透传 `rng=None`

**矛盾确认**：`apply_shift` 的签名暗示 `rng=None` 是合法输入（默认值），但实际传给 `shift_noise` 会 `raise ValueError`。**类型签名与运行时行为矛盾**。

**对比 R4 修复**：R4 修复了 `shifted_eval`/`shifted_probs_labels` 的默认值改 None + raise ValueError（3 处），但**未同步修复 `apply_shift`**——`apply_shift` 仍保留 `rng=None` 默认值，仅靠 `warnings.warn` + 下游 `shift_noise` raise 兜底。

**但需澄清一点**：`apply_shift` 对**非 noise 类型**（downsample/leads/gain）确实接受 `rng=None`（L198: `if rng is None and t == "noise"` 仅对 noise 类型检查）。所以矛盾仅存在于 noise 类型路径。反方定级"中等"合理。

**修补方案**：与 A3 合并。在 `apply_shift` 中对 noise 类型提前 `raise ValueError`（见 A3 修补方案），使 `apply_shift` 的运行时行为与签名一致（对 noise 类型明确拒绝 `rng=None`，对非 noise 类型接受 `rng=None`）。

若要更彻底，可改签名为重载或移除默认值，但 Python 类型系统难以表达"rng 仅 noise 类型必需"，提前 raise 是最务实的方案。

---

### Attack-9: 量级错误维度未发现可攻击点

**判定**：N/A（非攻击点）

**理由**：反方明确记录"该维度未发现可攻击点"。R4 修复涉及版本标记（O(1) 字符串比较）和默认值检查（O(1) 比较），无量级错误。无需审查。

---

### Attack-10: paper/generate_figures.py L212 仍有 RandomState(42)

**判定**：不成立

**理由**：

反方自己承认此攻击"非 P0-1 范围"且"与 P0-1（RNG种子遗漏）无关"。

**代码证据**：
- `paper/generate_figures.py` L212: `jitter = np.random.RandomState(42).uniform(-0.06, 0.06, size=5)` —— 用于可视化 jitter（图表抖动）

**反驳**：
1. P0-1 的范围是"L2 移位实验中跨实验噪声种子独立性"，关注的是 `apply_shift` → `shift_noise` → `_synthetic_noise` 的噪声注入路径
2. `generate_figures.py` L212 的 `RandomState(42)` 用于**可视化 jitter**（图表中数据点的微小水平位移，避免重叠），不涉及实验数据生成、模型评估或校准
3. 可视化 jitter 使用固定种子是**正确做法**——确保图表可复现，且 jitter 不影响任何数值结论
4. R3 终审裁决（`docs/p0r3_final_verdict.md`）已将此点归为"可关闭的攻击点"或未列入 P0-1 必修项

**结论**：稻草人论证——将无关的可视化代码强行纳入 P0-1 范围。反方定级"轻微"但仍列为攻击点，属过度审查。应关闭。

---

## 总结

### 需R5修复的必修项清单（按优先级排序）

| 优先级 | 攻击点 | 文件 | 行号 | 改动内容 | 改动量 |
|--------|--------|------|------|---------|--------|
| P0-严重 | A1+A5 | scripts/run_e1a_l2_shift_full.py | L264/L269/L431/L251-253 | 版本标记改为 per-seed 层（删除顶层检查 + 添加 per-seed 检查 + 改写入位置 + 更新 docstring） | ~+2行 |
| P0-严重 | A2 | src/data/l2_shifts.py | L192-194 | 更新 apply_shift docstring（"若 None 则创建 RandomState(42)" → "若 None 且 noise 类型则 raise ValueError"） | ~+1行 |
| P0-严重 | A3+A6+A8 | src/data/l2_shifts.py | L198-205 | 删除 warnings.warn，改为提前 raise ValueError（同时消解 A6 冗余 + A8 签名矛盾） | ~-2行 |
| **合计** | | | | | **~+1行净改动** |

**说明**：
- A1 与 A5 同源（顶层 vs per-seed 版本标记），修 A1 即自动消解 A5
- A3 与 A6 同源（warnings.warn 冗余），修 A3 即自动消解 A6
- A3 的修补方案（提前 raise）同时消解 A8（签名矛盾），因为 `apply_shift` 对 noise 类型显式 raise，不再依赖下游兜底
- A2（docstring）需独立修补
- 总改动量约 +1 行净改动（含 -7 行删除 warnings.warn + 新增 raise），涉及 2 个文件

### 可关闭的攻击点及理由

| 攻击点 | 关闭理由 |
|--------|---------|
| A4 | **部分成立，降级轻微**。设计不一致真实存在，但功能行为正确（重跑安全 + 两脚本用相同 md5 派生 + __seed_strategy__ 不丢失）。非必修，可选改进。 |
| A7 | **部分成立，轻微**。设计改进建议，非 bug。当前只有 `run_e1a_l2_shift_full.py` 需版本标记，常量定义位置合理。可选改进。 |
| A9 | **N/A**。反方自己记录"未发现可攻击点"，非实际攻击。 |
| A10 | **不成立**。稻草人论证——`paper/generate_figures.py` L212 的 `RandomState(42)` 用于可视化 jitter，与 P0-1（L2 移位实验噪声种子独立性）无关。可视化用固定种子是正确做法。 |

### 对 R4 修复质量的总体评价

**R4 修复相比 R3 有实质进步，但仍有 3 个严重攻击点需 R5 修复。**

**正面评价**（反方公平声明中确认，经我独立验证）：
- ✅ `is_checkpoint_complete` L264 的版本检查逻辑正确处理 None（旧结果无字段 → 重跑）
- ✅ 3 处函数默认值改 None + raise ValueError 正确（`eval_l2_shift.py` L36-42、`run_e1a_l2_shift_full.py` L168-177、`run_e4_temperature_analysis.py` L295-305）
- ✅ `l2_shifts.py` L78-82/L122-126 回退路径改 raise ValueError 正确
- ✅ 重复代码块删除正确
- ✅ 3 处调用方均正确传入 pair_id/arch/train_seed
- ✅ `raise ValueError` 错误消息足够 informative
- ✅ `--force` 标志正确跳过版本检查

**负面评价**（需 R5 修复）：
- ❌ **A1（严重）**：版本标记位置错误（顶层 vs per-seed），部分重跑场景下静默失效——这是 R4 修复**最核心的遗漏**，正是 R4 声称要消除的问题
- ❌ **A2（严重）**：`apply_shift` docstring 未同步更新，与代码行为矛盾
- ❌ **A3（严重）**：`apply_shift` `warnings.warn` 未同步更新，与实际 raise 行为矛盾

**收敛趋势**：
- R3 → R4：P0-1 必修从 ~23 行降至 ~1 行净改动（R4 修复了大部分 R3 遗留问题）
- R4 → R5（预期）：~1 行净改动，3 个严重攻击点可清零
- R5 修复后 P0-1 可完全收敛（仅剩 A4/A7 可选改进项）

**R5 修复建议**：优先修 A1（per-seed 版本标记，最核心）+ A3（提前 raise，同时消解 A6/A8）+ A2（docstring）。总工作量约 1 行净改动，2 个文件，工时约 30 分钟（含验证）。

---

## 审查透明性声明

本报告由反反方审查代理独立撰写，基于对以下文件的完整阅读和逐行代码验证：
- `docs/p0r4_attack_p0_1.md`（反方攻击报告全文）
- `scripts/eval_l2_shift.py`（完整 199 行）
- `scripts/run_e1a_l2_shift_full.py`（完整 658 行）
- `scripts/run_e4_temperature_analysis.py`（完整 1025 行）
- `src/data/l2_shifts.py`（完整 214 行）
- `docs/p0r3_final_verdict.md`（R3 终审裁决全文）

并使用 grep 工具全局搜索 `__seed_strategy__`、`SEED_STRATEGY_VERSION`、`apply_shift`、`RandomState(42)` 调用点，确认所有调用方均传非 None rng，无遗漏。

所有判定均附具体行号和代码证据，无臆测。对反方攻击点既不轻信（逐行验证反例是否真的成立），也不偏袒正方（A1/A2/A3 经验证确认成立，未因"R4 已修复"而放过）。
