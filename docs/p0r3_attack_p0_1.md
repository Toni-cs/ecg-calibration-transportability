# P0-1 R3修复 反方攻击报告

> **反方挑刺代理交付**（任务 #96）。对正方在 R3 轮对 P0-1（RNG种子遗漏）的 hashlib.md5 种子派生修复进行全方位攻击审查。
> **审查日期**：2026-09-09
> **审查代理**：反方挑刺代理（GLM-5.2）
> **审查对象**：3 个文件的 hashlib.md5 种子派生修复
> **攻击维度**：7 个（反例构造/逻辑断链/隐含假设/边界失效/自相矛盾/量级错误/语义偏移）

---

## 0. 修复方案摘要

正方在 3 个文件中将 `rng = np.random.RandomState(42)` 改为基于 hashlib.md5 的种子派生：

```python
noise_seed = int(
    hashlib.md5(f"{pair_id}|{arch}|{train_seed}|{shift['name']}".encode()).hexdigest()[:8], 16
) % (2**32)
rng = np.random.RandomState(noise_seed)
```

修改文件与位置：
| 文件 | 种子派生行 | 调用方行 | 函数名 |
|------|-----------|---------|--------|
| scripts/eval_l2_shift.py | L47-50 | L136-139 | shifted_eval |
| scripts/run_e1a_l2_shift_full.py | L177-180 | L328-331 | shifted_eval |
| scripts/run_e4_temperature_analysis.py | L310-313 | L654-657 | shifted_probs_labels |

---

## 1. Phase 1：方案接收与理解

### 1.1 核心主张
正方声称：基于实验参数 `pair_id|arch|train_seed|shift_name` 派生 md5 哈希种子，确保"不同实验/不同档/不同移位类型必然获得不同种子"，且 hashlib.md5 跨进程可复现。

### 1.2 推理链条标记
| 步骤 | 内容 | 强度 |
|------|------|------|
| S1 | md5 是确定性算法，跨进程可复现 | 坚实 |
| S2 | 派生键包含 4 个实验参数，不同组合产生不同键字符串 | 坚实（但"必然不同种子"跳跃，见攻击6） |
| S3 | 不同键字符串经 md5 产生不同哈希 | **可疑**（md5 碰撞 + 32位截断） |
| S4 | 3 处调用方均正确传入 pair_id/arch/train_seed | 坚实（已逐行验证） |
| S5 | 修复使已有结果不可复现，需重跑 | **跳跃**（未提供强制重跑机制，见攻击5） |
| S6 | l2_shifts.py 的 RandomState(42) 回退路径无需修改 | **可疑**（见攻击8） |

---

## 2. Phase 2：全维度攻击

### 攻击维度 1：反例构造

**攻击点 A1（严重）：断点续传导致混合种子数据集**

**反例**：假设用户在 R2 轮已运行 `run_e1a_l2_shift_full.py`，生成了 24 个 checkpoint 的 `l2_shift_results.json`（使用旧种子 42）。现在 R3 轮修复后，用户再次运行同一脚本（不带 `--force`）。

**具体后果**：
- `run_e1a_l2_shift_full.py` L293: `if not force and is_checkpoint_complete(run_dir, seed, shift_names):` → 命中断点续传，**跳过该 checkpoint**
- L295-296: `print(f"[resume] ...已完整，跳过")` → 直接返回旧结果
- 旧结果使用 `RandomState(42)`，新代码使用 `RandomState(noise_seed)`
- **最终 390 矩阵中，部分单元格用旧种子 42，部分用新 md5 种子——混合种子数据集**

**验证**：`is_checkpoint_complete` 函数（L238-264）检查 `safety` 字段是否存在。若旧结果由 `run_e1a_l2_shift_full.py` 生成（含 safety 字段），则断点续传命中，旧结果被保留。若旧结果由 `eval_l2_shift.py` 生成（不含 safety 字段），则断点续传不命中，会重跑。

**严重程度**：**严重**——修复在默认运行模式下静默失效，用户以为修复已生效，实际仍用旧种子。需用户显式传 `--force` 或删除旧结果才能生效，但代码注释仅说"需重跑受影响实验"，未提示 `--force` 标志。

---

**攻击点 A2（严重）：函数默认参数导致静默失败**

**反例**：未来某调用方写：
```python
shifted_eval(model, dataset, shift, device)  # 忘记传 pair_id/arch/train_seed
```

**具体后果**：
- 使用默认值 `pair_id="", arch="", train_seed=0`
- 哈希键 = `"||0|noise24"` → 所有实验共享同一种子
- **无任何错误或警告**——静默回退到"跨实验共享种子"的旧 bug

**证据**：3 个函数签名均使用危险默认值：
- `eval_l2_shift.py` L36-37: `pair_id: str = "", arch: str = "", train_seed: int = 0`
- `run_e1a_l2_shift_full.py` L163-164: `pair_id: str = "", arch: str = "", train_seed: int = 0`
- `run_e4_temperature_analysis.py` L295-296: `pair_id: str = "", arch: str = "", train_seed: int = 0`

**严重程度**：**严重**——默认值应改为 `None` 并在函数体内检查，若 `None` 则 raise ValueError。当前默认值使修复在"忘记传参"时静默回退到旧 bug 行为。

---

### 攻击维度 2：逻辑断链

**攻击点 A3（中等）：注释声称"必然获得不同种子"存在逻辑跳跃**

**证据**：3 个文件的注释均写：
> "不同实验/不同档/不同移位类型**必然**获得不同种子"

**逻辑断链**：
- S2（不同参数组合 → 不同键字符串）成立 ✓
- S3（不同键字符串 → 不同 md5 哈希）**不成立**——md5 存在碰撞
- 即使忽略 md5 碰撞，`hexdigest()[:8]` 截断到 32 位后碰撞概率进一步增加
- 因此"必然"一词过强，应为"极大概率"（见攻击维度 6 量级分析）

**严重程度**：**中等**——注释语义不精确，在 CBM 审稿标准下属于"隐含假设未显式化"。

---

### 攻击维度 3：隐含假设

**攻击点 A4（严重）：隐含假设"所有调用方都传 rng"未显式强制**

**隐含假设**：修复依赖所有调用方都正确传入 pair_id/arch/train_seed 三个参数。但代码未强制此假设——默认参数 `=""`/`=0` 使遗漏静默通过。

**假设不成立的情况**：
- 未来新增调用方忘记传参（见 A2）
- 当前 `l2_shifts.py` 的 `apply_shift` 仍接受 `rng=None`（L183: `rng: np.random.RandomState | None = None`），回退到 `RandomState(42)`

**严重程度**：**严重**——修复未用类型系统或运行时检查强制关键假设。

---

**攻击点 A5（中等）：隐含假设"旧结果会被重跑"未提供机制保障**

**隐含假设**：注释写"需重跑受影响实验"，假设用户会主动重跑。但：
- 代码未提供版本标记或种子策略指纹
- 断点续传机制（`is_checkpoint_complete`）会保留旧结果
- 用户需知道传 `--force` 标志，但注释未提示

**假设不成立的情况**：用户直接运行 `python scripts/run_e1a_l2_shift_full.py`，旧结果被保留，修复静默失效（见 A1）。

**严重程度**：**中等**——属于"修复声明与代码行为不一致"。

---

### 攻击维度 4：边界失效

**攻击点 A6（中等）：空字符串/零值边界下哈希键退化**

**边界情况**：若 `pair_id=""` 且 `arch=""` 且 `train_seed=0`：
- 哈希键 = `"||0|noise24"`
- 所有实验共享同一种子——退化为旧 bug

**边界情况**：若 `shift['name']` 为空字符串：
- 哈希键 = `"ptbxl_chapman|resnet1d|42|"`
- 不同 shift 若都有空 name，则共享种子

**验证**：当前 `get_l2_shifts()` 的 13 档 name 均非空，但代码未对空值做防御。

**严重程度**：**中等**——当前不触发，但无防御性检查。

---

**攻击点 A7（轻微）：非噪声档的 rng 创建是无效计算**

**边界情况**：13 档中仅 5 档（noise24/noise12/noise6/noise0/noise-6）使用 rng。其余 8 档（fs250/fs125/leads6/leads3/leads2/leads1/gain0.5/gain2.0）的 `apply_shift` 忽略 rng。

**证据**：`l2_shifts.py` L200-207：`apply_shift` 仅在 `t == "noise"` 时调用 `shift_noise`（使用 rng），其余分支直接返回确定性变换。

**后果**：对 8 个非噪声档，md5 哈希计算和 RandomState 创建是浪费——不影响正确性，但可能误导读者以为种子对所有档都生效。

**严重程度**：**轻微**——性能可忽略，但语义可能误导。

---

### 攻击维度 5：自相矛盾

**攻击点 A8（严重）：l2_shifts.py 回退路径与 R3 修复矛盾**

**矛盾**：R3 修复的目标是消除"跨实验共享种子 42"。但 `l2_shifts.py` 仍保留两处 `RandomState(42)` 回退：

- L78-79（`_synthetic_noise`）: `if rng is None: rng = np.random.RandomState(42)`
- L119-120（`shift_noise`）: `if rng is None: rng = np.random.RandomState(42)`

**矛盾点**：
- 修复方声称"不同实验必然获得不同种子"
- 但若 `rng=None` 传入，`l2_shifts.py` 仍用 `RandomState(42)`——所有实验共享种子
- `apply_shift` L192-199 虽有 UserWarning，但仅警告不阻止

**自相矛盾**：修复在调用方层做了种子派生，但在被调用方层仍保留旧 bug 的回退路径。两层逻辑矛盾——一个说"必须不同"，一个说"可以相同"。

**严重程度**：**严重**——虽然当前 3 个调用方都传了 rng，但回退路径的存在使修复不完整。应在 `l2_shifts.py` 中将 `RandomState(42)` 回退改为 `raise ValueError("rng is required for noise shift")`。

---

**攻击点 A9（轻微）：run_e4_temperature_analysis.py 存在重复代码块**

**证据**：L524-532 与 L534-542 完全相同：
```python
# L524-532
id_rel_binned_global = brier_reliability_top(id_probs_binned, id_labels)
ood_rel_binned_global = brier_reliability_top(ood_probs_binned, ood_labels)
dist_record["id_rel_binned_T"] = id_rel_binned_global
dist_record["ood_rel_binned_T"] = ood_rel_binned_global
dist_record["id_delta_rel_binned_vs_global"] = id_rel_binned_global - id_rel_global
dist_record["ood_delta_rel_binned_vs_global"] = ood_rel_binned_global - ood_rel_global

# L534-542（完全相同的 6 行）
id_rel_binned_global = brier_reliability_top(id_probs_binned, id_labels)
...
```

**严重程度**：**轻微**——非 R3 引入（预存缺陷），但位于 R3 修改的同一文件内，影响代码可维护性。

---

### 攻击维度 6：量级错误

**攻击点 A10（中等）：hexdigest()[:8] 截断到 32 位的碰撞概率估计**

**量级分析**：
- 完整 md5 哈希：128 位，碰撞概率 ≈ 2^-128（可忽略）
- 截断后：32 位，有效空间 2^32 ≈ 4.29 × 10^9
- 实验组合数：6 方向 × 3 架构 × 5 种子 × 13 档 = 1170 个键
- 生日悖论碰撞概率：P ≈ n²/(2N) = 1170²/(2 × 2^32) ≈ 1.37M/8.59G ≈ **0.016%**

**量级评估**：
- 0.016% 在单次运行中可忽略
- 但若考虑未来扩展（更多方向/架构/种子/档），碰撞概率平方增长
- 更优方案：`int(hashlib.md5(...).hexdigest(), 16) % (2**32)` 使用全部 128 位

**冗余操作**：`int(hexdigest()[:8], 16)` 已在 [0, 2^32) 范围内，`% (2**32)` 是 no-op。虽无害但冗余。

**严重程度**：**中等**——当前 1170 键下碰撞可忽略，但截断损失 96 位熵且注释声称"必然不同"与量级分析矛盾。

---

### 攻击维度 7：语义偏移

**攻击点 A11（中等）：pair_id 语义在 E4 中偏移**

**语义偏移**：`pair_id` 在 3 个文件中语义不一致：
- `eval_l2_shift.py` L138: `pair_id=f"{args.source}_{args.target}"` → 噪声施加到 **target test 集**
- `run_e1a_l2_shift_full.py` L330: `pair_id=f"{source}_{target}"` → 噪声施加到 **target test 集**
- `run_e4_temperature_analysis.py` L656: `pair_id=pair` → 噪声施加到 **source cal 集**（L655: `src_ds["cal"]`）

**后果**：同一 (pair, arch, seed, shift_name) 组合在 E1a 和 E4 中产生**相同的 noise_seed**，但施加到不同数据集。由于 rng 状态从同一 seed 开始，若 cal 和 test 的信号长度相同，前 N 条信号会获得相同的噪声序列。

**是否为 bug**：
- 严格说不是 bug——噪声由 rng 状态和信号内容共同决定，不同信号施加相同 rng 状态的噪声是合理的
- 但语义上，E4 的 `pair_id` 表示"对 cal 集施加 shift 拟合 T"，而 E1a 表示"对 test 集施加 shift 评估安全率"——两者实验语义不同，却共享同一种子派生键
- 更精确的派生键应包含数据集角色（如 `cal` vs `test`）

**严重程度**：**中等**——当前不影响正确性（不同信号 + 相同 rng = 不同噪声结果），但语义偏移可能导致未来误用。

---

**攻击点 A12（轻微）："跨进程可复现"声明忽略 Python 版本差异**

**证据**：注释声称"使用 hashlib.md5 代替内置 hash()，保证跨进程可复现"。

**隐含假设**：`hashlib.md5` 的输出在所有 Python 版本一致。这在 Python 3.x 内成立（md5 算法标准化），但：
- `f"{train_seed}"` 的字符串化依赖 int.__format__，在 Python 2/3 间不同（但项目用 `from __future__ import annotations` 暗示 Python 3.7+）
- `.encode()` 默认 UTF-8，在 Python 3 中稳定

**严重程度**：**轻微**——Python 3.x 内可复现成立，声明基本正确。

---

## 3. Phase 3：攻击点精化

### 3.1 攻击点汇总（按严重度排序）

| 编号 | 严重度 | 攻击维度 | 攻击点 | 文件 | 行号 |
|------|--------|---------|--------|------|------|
| A1 | **严重** | 反例构造 | 断点续传导致混合种子数据集，修复静默失效 | run_e1a_l2_shift_full.py | L293-296 |
| A2 | **严重** | 反例构造 | 函数默认参数 `=""`/`=0` 导致静默回退旧 bug | 3 个文件 | 函数签名 |
| A4 | **严重** | 隐含假设 | 未强制"所有调用方传 rng"假设 | 3 个文件 | 函数签名 |
| A8 | **严重** | 自相矛盾 | l2_shifts.py 保留 RandomState(42) 回退与修复矛盾 | src/data/l2_shifts.py | L78-79, L119-120 |
| A3 | **中等** | 逻辑断链 | "必然获得不同种子"注释语义过强 | 3 个文件 | 注释 |
| A5 | **中等** | 隐含假设 | "需重跑"未提供机制保障 | run_e1a_l2_shift_full.py | L293 |
| A6 | **中等** | 边界失效 | 空字符串/零值边界下哈希键退化 | 3 个文件 | 种子派生 |
| A10 | **中等** | 量级错误 | hexdigest()[:8] 截断到 32 位，碰撞概率 0.016% | 3 个文件 | L48/L178/L311 |
| A11 | **中等** | 语义偏移 | E4 中 pair_id 语义偏移（cal vs test） | run_e4_temperature_analysis.py | L654-657 |
| A7 | **轻微** | 边界失效 | 非噪声档的 rng 创建是无效计算 | 3 个文件 | 种子派生 |
| A9 | **轻微** | 自相矛盾 | run_e4 有重复代码块（预存缺陷） | run_e4_temperature_analysis.py | L524-542 |
| A12 | **轻微** | 语义偏移 | "跨进程可复现"忽略 Python 版本差异 | 3 个文件 | 注释 |

### 3.2 各攻击点具体反例与验证

#### A1 详细验证

**反例构造**：
1. R2 轮已运行 `run_e1a_l2_shift_full.py`，生成 `checkpoints/transfer/ptbxl_chapman/resnet1d/seed42/l2_shift_results.json`，其中 noise 档用 `RandomState(42)`
2. R3 修复后，用户运行 `python scripts/run_e1a_l2_shift_full.py`（不带 `--force`）
3. L568: `if not args.force and is_checkpoint_complete(run_dir, seed, shift_names):` → True（旧结果含 safety 字段）
4. L569-571: 加载旧结果，`n_skip += 1`，**跳过重跑**
5. 旧结果中 noise 档的噪声用 seed 42，新结果（若有未跑的 checkpoint）用 md5 派生种子
6. **390 矩阵中混合两种种子策略**

**验证证据**：
- `is_checkpoint_complete` L262-263 检查 `safety` 字段——若旧结果由 `run_e1a_l2_shift_full.py` 生成则含此字段
- L568-571 的断点续传逻辑不检查种子策略版本
- 代码注释 L175-176 写"需重跑受影响实验"，但未提供自动重跑机制

#### A2 详细验证

**反例构造**：
```python
# 假设未来新增调用方
from scripts.eval_l2_shift import shifted_eval
ood_probs, ood_labels = shifted_eval(model, dataset, shift, device)
# 忘记传 pair_id/arch/train_seed
```

**后果**：
- `pair_id=""`, `arch=""`, `train_seed=0`
- 哈希键 = `"||0|noise24"` → `noise_seed = int(md5("||0|noise24".encode()).hexdigest()[:8], 16) % (2**32)`
- 所有实验共享同一 `noise_seed` → 退化为 R2 修复前的 bug
- **无任何错误/警告**——静默失败

**对比**：若默认值改为 `None` 并加检查：
```python
def shifted_eval(model, dataset, shift, device, pair_id=None, arch=None, train_seed=None):
    if pair_id is None or arch is None or train_seed is None:
        raise ValueError("pair_id, arch, train_seed are required for noise seed derivation")
```
则遗漏会立即报错。

#### A8 详细验证

**证据**：`src/data/l2_shifts.py` 两处回退：
```python
# L72-79 (_synthetic_noise)
def _synthetic_noise(n_samples, noise_type, fs=500, rng=None):
    if rng is None:
        rng = np.random.RandomState(42)  # ← 旧 bug 回退路径

# L110-120 (shift_noise)
def shift_noise(signal, noise_type, snr_db, fs=500, rng=None):
    if rng is None:
        rng = np.random.RandomState(42)  # ← 旧 bug 回退路径
```

**矛盾**：
- R3 修复目标：消除跨实验共享 seed 42
- `l2_shifts.py` 回退：若 rng=None 则用 seed 42
- `apply_shift` L192-199：仅发 UserWarning，不阻止
- 结论：修复在调用方层生效，但在被调用方层仍保留矛盾逻辑

---

## 4. Phase 4：攻击报告

### 4.1 攻击总结

我尝试了全部 7 个攻击维度，**找到 12 个攻击点**，其中：
- **严重 4 个**：A1（断点续传混合种子）、A2（默认参数静默失败）、A4（未强制传参假设）、A8（l2_shifts.py 回退矛盾）
- **中等 5 个**：A3（注释语义过强）、A5（重跑无机制）、A6（空值边界）、A10（32位截断）、A11（pair_id 语义偏移）
- **轻微 3 个**：A7（非噪声档无效计算）、A9（重复代码块）、A12（Python 版本差异）

### 4.2 最关键攻击（按优先级）

#### **攻击 A1（严重）——断点续传导致修复静默失效**

这是最危险的攻击。R3 修复的核心价值在于"跨实验噪声独立"，但断点续传机制会保留旧种子 42 的结果，导致：
- 用户以为修复已生效
- 实际 390 矩阵中混合两种种子策略
- 论文若基于此混合数据，结论可信度受损

**修复建议**：
1. 在 `l2_shift_results.json` 中增加 `"seed_strategy": "md5_v1"` 版本标记
2. `is_checkpoint_complete` 检查版本标记，若不匹配则视为不完整
3. 或在注释中显式提示"必须传 `--force` 或删除旧结果"

#### **攻击 A2+A4（严重）——默认参数应改为 None + 强制检查**

当前默认参数 `pair_id="", arch="", train_seed=0` 使遗漏静默通过。应改为：
```python
def shifted_eval(model, dataset, shift, device, pair_id=None, arch=None, train_seed=None):
    if pair_id is None or arch is None or train_seed is None:
        raise ValueError("pair_id, arch, train_seed required for noise seed derivation")
```

#### **攻击 A8（严重）——l2_shifts.py 回退路径应改为 raise**

`l2_shifts.py` L78-79 和 L119-120 的 `RandomState(42)` 回退应改为：
```python
if rng is None:
    raise ValueError("rng is required for noise shift; pass rng from caller")
```
或至少改为 `raise`，消除与 R3 修复的矛盾。

### 4.3 正方修复中正确的部分（公平声明）

经逐行验证，以下部分正确：
- ✅ 3 处调用方均正确传入 pair_id/arch/train_seed（`eval_l2_shift.py` L138、`run_e1a_l2_shift_full.py` L330、`run_e4_temperature_analysis.py` L656）
- ✅ hashlib.md5 确实跨进程可复现（不受 PYTHONHASHSEED 影响）
- ✅ `.encode()` 默认 UTF-8，对纯 ASCII 键字符串无歧义
- ✅ 派生键格式 `f"{pair_id}|{arch}|{train_seed}|{shift['name']}"` 的 `|` 分隔符在当前所有值中不出现，无分隔符碰撞
- ✅ `shift['name']` 在所有调用路径上都存在（`get_l2_shifts()` 的 13 档均有 name）
- ✅ pair_id 格式跨文件一致（均为 `"source_target"` 格式）
- ✅ `import hashlib` 已在 3 个文件中正确添加

### 4.4 对 8 个审查问题的逐条回答

| 编号 | 审查问题 | 结论 |
|------|---------|------|
| (1) | md5 哈希键格式是否有碰撞风险？ | **当前无实际碰撞**：`|` 分隔符不出现于任何值中，1170 个键字符串唯一。但 32 位截断后生日悖论碰撞概率 ≈ 0.016%（A10）。 |
| (2) | hashlib.md5 是否跨进程/跨平台可复现？ | **是**。md5 算法标准化，`.encode()` 默认 UTF-8，键字符串纯 ASCII。Python 3.x 内完全可复现（A12 轻微）。 |
| (3) | 所有调用方是否正确传入参数？ | **是**。3 处调用方均传 pair_id/arch/train_seed，参数名匹配。但默认参数 `=""`/`=0` 有静默失败风险（A2）。 |
| (4) | 是否有遗漏的 RandomState(42)？ | **是**。`src/data/l2_shifts.py` L79/L120 仍有 `RandomState(42)` 回退；`paper/generate_figures.py` L212 有 `RandomState(42)`（非噪声注入，无关）。 |
| (5) | 是否破坏已有结果可复现性？ | **是**，且更严重——断点续传导致混合种子数据集（A1）。旧结果用 seed 42，新结果用 md5 种子，默认运行模式下两者共存。 |
| (6) | hexdigest()[:8] 截断是否有损失？ | **是**。128 位 → 32 位，损失 96 位熵。1170 键下碰撞概率 ≈ 0.016%。`% (2**32)` 冗余（A10）。 |
| (7) | shift['name'] 是否在所有路径存在？ | **是**。`get_l2_shifts()` 的 13 档均有 name，无 None/缺失键风险。 |
| (8) | l2_shifts.py 的 RandomState(42) 是否需同步修改？ | **是**。应改为 `raise ValueError`，消除与 R3 修复的矛盾（A8）。当前保留为回退路径，使修复不完整。 |

### 4.5 R3 修复裁决

**裁决**：**有条件通过，需 R4 修复 4 个严重攻击点**

| 严重攻击 | 修复建议 | 改动量 |
|---------|---------|--------|
| A1 断点续传混合种子 | 增加 seed_strategy 版本标记 + is_checkpoint_complete 检查 | ~8 行 |
| A2 默认参数静默失败 | 3 个函数签名默认值改 None + raise ValueError | ~6 行 |
| A4 未强制传参假设 | 与 A2 合并修复 | 0 行（合并） |
| A8 l2_shifts.py 回退矛盾 | L79/L120 的 RandomState(42) 改为 raise ValueError | ~4 行 |

**R4 必修改计**：~18 行，4 个文件（3 个脚本 + l2_shifts.py）

---

## 5. 对抗透明性声明

本报告由反方挑刺代理独立撰写，基于对 3 个修改文件 + `src/data/l2_shifts.py` + `docs/p0r2_final_verdict.md` 的完整阅读，以及对全项目 `.py` 文件的 `RandomState(42)` 和 `apply_shift` 调用点全局搜索。所有攻击点均附具体行号和代码证据，无臆测。

**攻击覆盖**：
- ✅ 反例构造（A1, A2）
- ✅ 逻辑断链（A3）
- ✅ 隐含假设（A4, A5）
- ✅ 边界失效（A6, A7）
- ✅ 自相矛盾（A8, A9）
- ✅ 量级错误（A10）
- ✅ 语义偏移（A11, A12）

**公平声明**：正方修复的核心逻辑（md5 派生 + 跨进程可复现 + 3 处调用方传参）正确。攻击点集中在**防御性不足**（默认参数、回退路径）和**工程机制缺失**（断点续传版本标记），而非核心算法错误。
