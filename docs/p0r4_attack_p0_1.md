# P0-1 R4修复 反方攻击报告

> **反方挑刺代理交付**（任务 #112）。对正方在 R4 轮对 P0-1（RNG种子遗漏）的 6 个必修项修复进行全方位攻击审查。
> **审查日期**：2026-09-09
> **审查代理**：反方挑刺代理（GLM-5.2）
> **审查对象**：4 个文件的 R4 修复（SEED_STRATEGY_VERSION 版本标记 + 默认值改 None + raise ValueError + 删除重复代码 + l2_shifts.py 回退路径改 raise）
> **攻击维度**：7 个（反例构造/逻辑断链/隐含假设/边界失效/自相矛盾/量级错误/语义偏移）

---

## 0. R4 修复方案摘要

正方在 R4 轮对 R3 终审裁决的 6 个必修项做了以下修复：

| 必修项 | 文件 | 修复内容 | 验证状态 |
|--------|------|---------|---------|
| A1+A5 | scripts/run_e1a_l2_shift_full.py | L140 定义 `SEED_STRATEGY_VERSION="md5_v1"` + L264 版本检查 + L431 写入标记 | ✅ 代码已加 |
| A2+A4+A6 | scripts/eval_l2_shift.py | L36-37 默认值改 None + L39-42 raise ValueError | ✅ 代码已改 |
| A2+A4+A6 | scripts/run_e1a_l2_shift_full.py | L168-169 默认值改 None + L174-177 raise ValueError | ✅ 代码已改 |
| A2+A4+A6 | scripts/run_e4_temperature_analysis.py | L295-296 默认值改 None + L302-305 raise ValueError | ✅ 代码已改 |
| A8 | src/data/l2_shifts.py | L78-82/L122-126 回退路径改 raise ValueError | ✅ 代码已改 |
| A9 | scripts/run_e4_temperature_analysis.py | 删除 L534-542 重复代码块 | ✅ 已删除 |

---

## 1. Phase 1：方案接收与理解

### 1.1 核心主张
正方声称 R4 修复彻底解决了 R3 轮遗留的 3 个严重攻击点 + 1 个清理项：
- A1：seed_strategy 版本标记阻止旧结果混用
- A2：默认值改 None + raise ValueError 阻止静默失败
- A8：l2_shifts.py 回退路径改 raise 消除矛盾
- A9：删除重复代码块

### 1.2 推理链条标记
| 步骤 | 内容 | 强度 |
|------|------|------|
| S1 | SEED_STRATEGY_VERSION="md5_v1" 写入顶层，is_checkpoint_complete 检查 | **可疑**（顶层 vs per-seed，见攻击A1） |
| S2 | 旧结果无 __seed_strategy__ 字段 → data.get 返回 None → != "md5_v1" → return False → 重跑 | 坚实 |
| S3 | 3 处函数默认值改 None + raise ValueError 阻止静默失败 | 坚实 |
| S4 | l2_shifts.py 回退路径改 raise ValueError 消除矛盾 | 坚实（但 apply_shift 未同步，见攻击A2/A3） |
| S5 | 删除重复代码块不影响功能 | 坚实 |
| S6 | eval_l2_shift.py 不写入版本标记 | **跳跃**（见攻击A4） |

---

## 2. Phase 2：全维度攻击

### 攻击维度 1：反例构造

**攻击点 A1（严重）：版本标记在顶层而非 per-seed，部分重跑导致混合种子数据集**

**反例构造**：
1. R2 轮用户运行 `python scripts/run_e1a_l2_shift_full.py`，生成所有 5 个 seed 的 `l2_shift_results.json`（用旧种子 42，无 `__seed_strategy__` 字段，但含 `safety` 字段）
2. R4 轮用户用 `--seeds 42 --force` 部分重跑 seed 42：
   - `evaluate_one_checkpoint` 对 seed 42 运行
   - L425: `existing = load_existing_results(run_dir)` —— 加载旧结果（含 seed 42/43/44/45/46 的旧数据，无版本标记）
   - L429: `existing["seed42"].update(seed_results)` —— 更新 seed 42 的数据为新 md5 派生数据
   - L431: `existing["__seed_strategy__"] = "md5_v1"` —— **写入顶层版本标记**
   - L433: 保存 —— 文件含 seed 42 的新数据 + seed 43/44/45/46 的**旧数据** + 顶层 `"md5_v1"`
3. R4 轮用户用 `--seeds 42 43 44 45 46`（不带 `--force`）运行：
   - `is_checkpoint_complete` 对 seed 43 检查：
     - 顶层 `__seed_strategy__` = `"md5_v1"` → 通过 ✓
     - `seed43` 键存在 → 通过 ✓
     - 每档含 `safety` 字段 → 通过 ✓（旧结果由 `run_e1a_l2_shift_full.py` 生成，含 `safety`）
   - `is_checkpoint_complete` 返回 True，**跳过重跑**
   - seed 43 的旧数据（用种子 42）被保留
4. **390 矩阵中混合两种种子策略**——seed 42 用 md5 派生，seed 43/44/45/46 用种子 42

**验证证据**：
- `is_checkpoint_complete` L264: `if data.get("__seed_strategy__") != SEED_STRATEGY_VERSION: return False` —— 只检查**顶层**版本标记
- L431: `existing["__seed_strategy__"] = SEED_STRATEGY_VERSION` —— 写入**顶层**
- 无 per-seed 版本标记机制

**严重程度**：**严重**——R4 修复声称"阻止旧结果混用"，但部分重跑场景下仍会混用。版本标记应在 per-seed 层（如 `existing[sk]["__seed_strategy__"] = SEED_STRATEGY_VERSION`），而非顶层。

---

**攻击点 A2（严重）：apply_shift 的 docstring 与代码不一致（R4 修复遗漏）**

**证据**：`src/data/l2_shifts.py` L188-194 的 `apply_shift` docstring 仍然写：
```
rng: 可选随机数生成器，仅 noise 类型使用。传入同一 rng 可确保循环内
每条信号获得不同噪声（rng 状态逐次推进）；若 None 则每次创建
RandomState(42)（会导致等长信号获得相同噪声，仅用于向后兼容）。
```

但 R4 修复后，`rng=None` 传给 `shift_noise` 会触发 L122-126 的 `raise ValueError`，**不会创建 RandomState(42)**。

**矛盾**：docstring 说"若 None 则每次创建 RandomState(42)"，实际行为是 raise ValueError。R4 修复了 `shift_noise`/`_synthetic_noise` 的回退路径，但**遗漏了 `apply_shift` 的 docstring 同步更新**。

**严重程度**：**严重**——`apply_shift` 是 `shift_noise` 的直接调用方，docstring 与实际行为矛盾会误导未来维护者。R4 修复不完整。

---

**攻击点 A3（严重）：apply_shift 的 warnings.warn 消息与实际行为矛盾**

**证据**：`src/data/l2_shifts.py` L198-205：
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

**执行流程**（`rng=None` 且 `t == "noise"`）：
1. L198-205: 发 UserWarning（说"Each signal will receive identical noise (RandomState(42))"）
2. L212-213: 调用 `shift_noise(signal, p["noise_type"], p["snr_db"], rng=None)`
3. `shift_noise` L122-126: `raise ValueError("rng must be explicitly provided; ...")`

**矛盾**：用户会先看到警告（说"会用 RandomState(42)"），然后看到 ValueError（说"必须提供 rng"）。**两个消息直接矛盾**——警告说会做 A，实际做的是 B（raise）。

**严重程度**：**严重**——R4 修复了 `shift_noise`/`_synthetic_noise`，但**遗漏了 `apply_shift` 的 warnings.warn 同步更新**。warnings.warn 消息应改为提示"将 raise ValueError"或直接删除（因为 raise 会立即终止）。

---

### 攻击维度 2：逻辑断链

**攻击点 A4（中等）：eval_l2_shift.py 不写入 __seed_strategy__ 版本标记，设计不一致**

**证据**：`scripts/eval_l2_shift.py` L186-194 保存结果时**不写入 `__seed_strategy__` 字段**：
```python
out_path = run_dir / "l2_shift_results.json"
if out_path.exists():
    existing = json.loads(out_path.read_text(encoding="utf-8"))
    sk = f"seed{seed}"
    if sk not in existing:
        existing[sk] = {}
    existing[sk].update(seed_results)
    all_results = existing
out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
```

**逻辑断链**：
- `run_e1a_l2_shift_full.py` 写入版本标记 → `is_checkpoint_complete` 检查版本标记
- `eval_l2_shift.py` **不写入**版本标记 → 它生成的结果无版本标记
- `rerun_l2_noise.py`（L64-68）通过调用 `eval_l2_shift.py` 生成结果 → 这些结果无版本标记

**后果**：
1. 用户用 `eval_l2_shift.py` 生成结果（无版本标记）
2. 用户用 `run_e1a_l2_shift_full.py` 运行 → `is_checkpoint_complete` 发现无版本标记 → 返回 False → **重跑**（正确但低效）
3. 两个脚本产生的 `l2_shift_results.json` 格式不一致——一个有版本标记，一个没有

**严重程度**：**中等**——功能正确（重跑是安全的），但设计不一致。`eval_l2_shift.py` 应同步写入版本标记，或两个脚本共享版本标记逻辑。

---

### 攻击维度 3：隐含假设

**攻击点 A5（中等）：隐含假设"用户不会部分重跑"未显式声明**

**隐含假设**：R4 的顶层版本标记机制假设用户要么全部重跑（`--force`），要么全部不重跑。但代码支持 `--seeds 42` 部分重跑，与顶层版本标记机制冲突。

**假设不成立的情况**：见攻击 A1——用户用 `--seeds 42 --force` 部分重跑，顶层版本标记更新，但其他 seed 的旧数据被保留。

**严重程度**：**中等**——代码支持部分重跑（`--seeds` 参数），但版本标记机制不支持。隐含假设未显式声明，也未在代码中防御。

---

### 攻击维度 4：边界失效

**攻击点 A6（轻微）：apply_shift 的 warnings.warn 是冗余/误导性代码**

**边界情况**：`apply_shift(sig, shift, rng=None)` 其中 shift 是 noise 类型：
1. L198-205: 发 UserWarning（冗余，因为马上 raise）
2. L212-213: 调用 `shift_noise(..., rng=None)`
3. `shift_noise` L122-126: `raise ValueError`

**后果**：warnings.warn 执行后立即 raise——warnings.warn 是**冗余**的。用户会看到两个矛盾的提示（见攻击 A3）。

**严重程度**：**轻微**——当前 3 个调用方都传非 None rng，不会触发。但防御性代码不一致——R4 修复了 `shift_noise`/`_synthetic_noise`，但 `apply_shift` 的 warnings.warn 应同步删除或改为提示 raise。

---

**攻击点 A7（轻微）：SEED_STRATEGY_VERSION 常量只在 run_e1a_l2_shift_full.py 定义**

**证据**：`SEED_STRATEGY_VERSION = "md5_v1"` 只在 `run_e1a_l2_shift_full.py` L140 定义。`eval_l2_shift.py` 和 `run_e4_temperature_analysis.py` 没有定义。

**后果**：
- 如果未来需要在其他脚本中使用版本标记，需要重复定义
- 建议提取到 `src/data/l2_shifts.py` 或公共模块
- 当前不影响正确性（只有 `run_e1a_l2_shift_full.py` 有断点续传检查）

**严重程度**：**轻微**——设计改进空间，非 bug。

---

### 攻击维度 5：自相矛盾

**攻击点 A8（中等）：apply_shift 保留 rng=None 默认值与 shift_noise raise ValueError 矛盾**

**矛盾**：
- `apply_shift` L188: `rng: np.random.RandomState | None = None` —— 仍接受 `rng=None`
- `shift_noise` L122-126: `if rng is None: raise ValueError` —— 拒绝 `rng=None`
- `apply_shift` L212-213: 调用 `shift_noise(..., rng=rng)` —— 传递 `rng=None` 给 `shift_noise`

**矛盾点**：`apply_shift` 的签名暗示 `rng=None` 是合法输入（默认值），但实际传给 `shift_noise` 会 raise。**类型签名与运行时行为矛盾**。

**对比**：R4 修复了 `shifted_eval`/`shifted_probs_labels` 的默认值改 None + raise ValueError，但**未同步修复 `apply_shift`**——`apply_shift` 仍保留 `rng=None` 默认值，仅靠 warnings.warn + 下游 raise 兜底。

**严重程度**：**中等**——`apply_shift` 是公开 API，签名暗示 `rng=None` 合法，但实际会 raise。应在 `apply_shift` 中对 noise 类型提前检查并 raise，或改签名。

---

### 攻击维度 6：量级错误

**攻击点 A9（未发现可攻击点）**

R4 修复不涉及复杂度/收敛性/稳定性估计。版本标记是 O(1) 字符串比较，默认值检查是 O(1) 比较，无量级错误。

**记录**：该维度未发现可攻击点。

---

### 攻击维度 7：语义偏移

**攻击点 A10（轻微）：paper/generate_figures.py L212 仍有 RandomState(42)**

**证据**：`paper/generate_figures.py` L212: `jitter = np.random.RandomState(42).uniform(-0.06, 0.06, size=5)`

**分析**：这是用于可视化 jitter（图表抖动），不是噪声注入。与 P0-1（RNG种子遗漏）无关——P0-1 关注的是 L2 移位实验中跨实验噪声种子独立性，可视化 jitter 不涉及实验数据生成。

**严重程度**：**轻微**——非 P0-1 范围，但需声明已检查。R3 攻击报告已提及（L399）。

---

## 3. Phase 3：攻击点精化

### 3.1 攻击点汇总（按严重度排序）

| 编号 | 严重度 | 攻击维度 | 攻击点 | 文件 | 行号 |
|------|--------|---------|--------|------|------|
| A1 | **严重** | 反例构造 | 顶层版本标记，部分重跑导致混合种子数据集 | run_e1a_l2_shift_full.py | L264/L431 |
| A2 | **严重** | 反例构造 | apply_shift docstring 与代码不一致（仍写 RandomState(42)） | src/data/l2_shifts.py | L193-194 |
| A3 | **严重** | 反例构造 | apply_shift warnings.warn 消息与实际行为矛盾 | src/data/l2_shifts.py | L199-204 |
| A4 | **中等** | 逻辑断链 | eval_l2_shift.py 不写入 __seed_strategy__ 版本标记 | scripts/eval_l2_shift.py | L186-194 |
| A5 | **中等** | 隐含假设 | 隐含假设"用户不会部分重跑"未显式声明 | run_e1a_l2_shift_full.py | L264/L431 |
| A8 | **中等** | 自相矛盾 | apply_shift 保留 rng=None 默认值与 shift_noise raise 矛盾 | src/data/l2_shifts.py | L188/L212-213 |
| A6 | **轻微** | 边界失效 | apply_shift warnings.warn 是冗余/误导性代码 | src/data/l2_shifts.py | L198-205 |
| A7 | **轻微** | 边界失效 | SEED_STRATEGY_VERSION 常量只在单文件定义 | run_e1a_l2_shift_full.py | L140 |
| A10 | **轻微** | 语义偏移 | paper/generate_figures.py L212 仍有 RandomState(42)（无关） | paper/generate_figures.py | L212 |

### 3.2 各攻击点具体反例与验证

#### A1 详细验证（最关键攻击）

**反例构造**（具体到可验证程度）：
1. 假设 `checkpoints/transfer/ptbxl_chapman/resnet1d/seed42/l2_shift_results.json` 含 5 个 seed 的旧数据（用种子 42，含 safety 字段，无 `__seed_strategy__`）
2. 运行 `python scripts/run_e1a_l2_shift_full.py --only ptbxl_chapman --archs resnet1d --seeds 42 --force`
3. L425: `existing = load_existing_results(run_dir)` 加载旧结果（5 个 seed）
4. L429: `existing["seed42"].update(seed_results)` 更新 seed 42
5. L431: `existing["__seed_strategy__"] = "md5_v1"` 写入顶层
6. L433: 保存——文件含 seed42 新数据 + seed43/44/45/46 旧数据 + 顶层 `"md5_v1"`
7. 运行 `python scripts/run_e1a_l2_shift_full.py --only ptbxl_chapman --archs resnet1d`（不带 --force）
8. L586: `is_checkpoint_complete(run_dir, 43, shift_names)` 检查 seed 43
9. L264: `data.get("__seed_strategy__")` = `"md5_v1"` == `SEED_STRATEGY_VERSION` → 通过
10. L266-279: seed43 存在，每档含 safety → 通过
11. `is_checkpoint_complete` 返回 True，L588: `existing.get("seed43", {})` 返回**旧数据**
12. **390 矩阵中 seed 42 用 md5 派生，seed 43 用种子 42——混合种子数据集**

**修复建议**：版本标记应在 per-seed 层：
```python
# 写入时
existing[sk]["__seed_strategy__"] = SEED_STRATEGY_VERSION

# 检查时
if seed_data.get("__seed_strategy__") != SEED_STRATEGY_VERSION:
    return False
```

#### A2/A3 详细验证

**反例构造**：
```python
from src.data.l2_shifts import apply_shift
import numpy as np
sig = np.random.randn(12, 5000)
shift = {"name": "noise24", "type": "noise", "params": {"noise_type": "mixed", "snr_db": 24}}
# 调用 apply_shift 不传 rng
apply_shift(sig, shift, rng=None)
```

**实际行为**：
1. UserWarning: "apply_shift called with rng=None for noise shift. Each signal will receive identical noise (RandomState(42)). ..."
2. ValueError: "rng must be explicitly provided; RandomState(42) fallback was removed to prevent cross-experiment seed collision"

**矛盾**：警告说"会用 RandomState(42)"，实际 raise ValueError。docstring 也说"若 None 则每次创建 RandomState(42)"。

**修复建议**：
1. 删除 `apply_shift` L198-205 的 warnings.warn（因为 raise 会立即终止）
2. 更新 `apply_shift` L193-194 docstring：`若 None 且为 noise 类型则 raise ValueError`
3. 或在 `apply_shift` 中对 noise 类型提前 raise ValueError（与 `shift_noise` 一致）

---

## 4. Phase 4：攻击报告

### 4.1 攻击总结

我尝试了全部 7 个攻击维度，**找到 9 个攻击点**，其中：
- **严重 3 个**：A1（顶层版本标记部分重跑混用）、A2（apply_shift docstring 不一致）、A3（apply_shift warnings.warn 矛盾）
- **中等 3 个**：A4（eval_l2_shift.py 不写版本标记）、A5（部分重跑假设未声明）、A8（apply_shift 签名矛盾）
- **轻微 3 个**：A6（warnings.warn 冗余）、A7（常量单文件定义）、A10（generate_figures.py 无关 RandomState(42)）

### 4.2 最关键攻击（按优先级）

#### **攻击 A1（严重）——顶层版本标记导致部分重跑混用**

这是 R4 修复**最核心的遗漏**。R4 的版本标记机制（顶层 `__seed_strategy__`）在部分重跑场景下失效：
- 用户用 `--seeds 42 --force` 重跑 seed 42 → 顶层版本标记更新为 `"md5_v1"`
- 其他 seed 的旧数据（用种子 42）被保留，但 `is_checkpoint_complete` 因顶层版本标记正确而跳过重跑
- **390 矩阵中混合两种种子策略**——正是 R4 修复声称要消除的问题

**修复建议**：版本标记改为 per-seed 层（`existing[sk]["__seed_strategy__"]`），`is_checkpoint_complete` 检查 `seed_data.get("__seed_strategy__")`。

#### **攻击 A2+A3（严重）——apply_shift 的 docstring 和 warnings.warn 未同步更新**

R4 修复了 `shift_noise`/`_synthetic_noise` 的回退路径（改 raise ValueError），但**遗漏了 `apply_shift` 的同步更新**：
- docstring 仍写"若 None 则每次创建 RandomState(42)"
- warnings.warn 仍说"Each signal will receive identical noise (RandomState(42))"
- 实际行为是 raise ValueError

**修复建议**：删除 warnings.warn，更新 docstring，或在 `apply_shift` 中提前 raise。

### 4.3 正方修复中正确的部分（公平声明）

经逐行验证，以下部分正确：
- ✅ `is_checkpoint_complete` L264 的版本检查逻辑正确：`data.get("__seed_strategy__") != SEED_STRATEGY_VERSION` 正确处理 None（旧结果无字段 → 返回 None → != "md5_v1" → return False → 重跑）
- ✅ L431 写入版本标记：`existing["__seed_strategy__"] = SEED_STRATEGY_VERSION` 正确写入顶层
- ✅ 3 处函数默认值改 None + raise ValueError 正确（`eval_l2_shift.py` L36-42、`run_e1a_l2_shift_full.py` L168-177、`run_e4_temperature_analysis.py` L295-305）
- ✅ `l2_shifts.py` L78-82/L122-126 回退路径改 raise ValueError 正确
- ✅ 重复代码块删除正确（`run_e4_temperature_analysis.py` 原 L534-542 已删除，保留 L531-536 功能完整）
- ✅ 3 处调用方均正确传入 pair_id/arch/train_seed（`eval_l2_shift.py` L140-143、`run_e1a_l2_shift_full.py` L344-347、`run_e4_temperature_analysis.py` L648-651）
- ✅ `raise ValueError` 错误消息足够 informative（说明原因 + 修复建议）
- ✅ `--force` 标志正确跳过版本检查（L309/L586: `if not args.force and is_checkpoint_complete(...)`）
- ✅ `--dry-run` 模式正确调用 `is_checkpoint_complete`（L573-576）

### 4.4 对 8 个审查重点的逐条回答

| 编号 | 审查重点 | 结论 |
|------|---------|------|
| (1) | SEED_STRATEGY_VERSION="md5_v1" 是否真正阻止旧结果混用？ | **部分阻止**：全量重跑场景下阻止（旧结果无字段 → 重跑）。但**部分重跑场景下失效**（顶层标记更新，其他 seed 旧数据保留，见 A1）。 |
| (2) | 旧 checkpoint 无 __seed_strategy__ 字段，is_checkpoint_complete 是否返回 False？ | **是**。`data.get("__seed_strategy__")` 返回 None，`None != "md5_v1"` → True → return False → 重跑。逻辑正确。 |
| (3) | 默认值改 None+raise ValueError 是否覆盖所有调用路径？ | **是**。3 处函数签名已改，3 处调用方均传非 None 值。但 `apply_shift` 仍保留 `rng=None` 默认值（见 A8）。 |
| (4) | 是否有调用方传入 None 导致后续代码崩溃？ | **否**。3 处调用方均传 pair_id/arch/train_seed 非 None。`apply_shift` 的 3 处调用方均传 rng 非 None。 |
| (5) | l2_shifts.py 回退路径改 raise ValueError 是否破坏正常调用？ | **否**。3 处调用方均传 rng 非 None。但 `apply_shift` 的 docstring 和 warnings.warn 未同步更新（见 A2/A3）。 |
| (6) | 是否有合法的 rng=None 场景？ | **是**。`apply_shift` 对非 noise 类型（downsample/leads/gain）接受 rng=None（L198: `if rng is None and t == "noise"`）。仅 noise 类型要求 rng 非 None。 |
| (7) | 删除重复代码块是否影响功能？ | **否**。R3 报告说 L524-532 和 L534-542 完全相同，删除任一段都正确。现保留 L531-536，功能完整。 |
| (8) | is_checkpoint_complete 的版本检查逻辑是否正确？ | **逻辑正确**（见 (2)），但**位置错误**——在顶层而非 per-seed（见 A1）。 |
| (9) | SEED_STRATEGY_VERSION 常量定义位置是否合理？ | **当前合理**（只有 `run_e1a_l2_shift_full.py` 有断点续传检查），但建议提取到公共模块（见 A7）。 |
| (10) | 是否有其他文件中仍存在 RandomState(42) 硬编码？ | **是**。`paper/generate_figures.py` L212 有 `RandomState(42)`，但用于可视化 jitter，与 P0-1 无关（见 A10）。 |

### 4.5 R4 修复裁决

**裁决**：**有条件通过，需 R5 修复 3 个严重攻击点**

| 严重攻击 | 修复建议 | 改动量 |
|---------|---------|--------|
| A1 顶层版本标记部分重跑混用 | 版本标记改为 per-seed 层（`existing[sk]["__seed_strategy__"]` + `seed_data.get("__seed_strategy__")` 检查） | ~4 行 |
| A2 apply_shift docstring 不一致 | L193-194 更新为"若 None 且为 noise 类型则 raise ValueError" | ~2 行 |
| A3 apply_shift warnings.warn 矛盾 | 删除 L198-205 的 warnings.warn（或改为提示 raise） | ~-7 行 |

**R5 必修改计**：~5 行净改动（含 -7 行删除），1 个文件（`src/data/l2_shifts.py`）+ 1 个文件（`run_e1a_l2_shift_full.py` per-seed 版本标记）

---

## 5. 对抗透明性声明

本报告由反方挑刺代理独立撰写，基于对 4 个修改文件 + `docs/p0r3_final_verdict.md` + `docs/p0r3_attack_p0_1.md` 的完整阅读，以及对全项目 `.py` 文件的 `RandomState(42)`、`apply_shift`、`shifted_eval`、`shifted_probs_labels`、`__seed_strategy__`、`SEED_STRATEGY_VERSION` 调用点全局搜索。所有攻击点均附具体行号和代码证据，无臆测。

**攻击覆盖**：
- ✅ 反例构造（A1, A2, A3）
- ✅ 逻辑断链（A4）
- ✅ 隐含假设（A5）
- ✅ 边界失效（A6, A7）
- ✅ 自相矛盾（A8）
- ✅ 量级错误（A9 未发现可攻击点，已明确记录）
- ✅ 语义偏移（A10）

**公平声明**：正方 R4 修复的**核心逻辑正确**——版本标记机制能阻止全量重跑场景下的旧结果混用，默认值改 None + raise ValueError 能阻止静默失败，l2_shifts.py 回退路径改 raise 能消除矛盾。攻击点集中在**版本标记位置不当**（顶层 vs per-seed）和**apply_shift 同步更新遗漏**（docstring + warnings.warn），而非核心算法错误。R4 修复相比 R3 有实质进步，但仍有 3 个严重攻击点需 R5 修复。
