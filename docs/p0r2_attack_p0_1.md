# P0-1 回炉修复（第二轮）反方攻击报告

> **审查代理**: 反方-P0R2-1-rng遗漏 (session 375981aa)
> **审查对象**: 正方第二轮 P0-1 修复（eval_l2_shift.py + run_e4_temperature_analysis.py + l2_shifts.py UserWarning）
> **审查日期**: 2026-09-09
> **结论**: **修复完整性通过，但修复正确性存在 3 个中危设计缺陷，1 个低危死代码风险**

---

## 0. 审查范围与事实核验

### 0.1 审查文件清单

| 文件 | 关键行 | 审查项 |
|------|--------|--------|
| `scripts/eval_l2_shift.py` | L41, L45 | rng 创建位置 + apply_shift 传参 |
| `scripts/run_e4_temperature_analysis.py` | L303, L308 | rng 创建位置 + apply_shift 传参 |
| `src/data/l2_shifts.py` | L23, L192-199 | import warnings + UserWarning 触发条件 |
| `scripts/run_e1a_l2_shift_full.py` | L174, L178 | 第一轮修复是否仍有效 |

### 0.2 全局调用方扫描结果

**直接调用 `apply_shift` 的文件（grep 全项目）**：

| # | 文件 | 行号 | 传 rng? | 状态 |
|---|------|------|---------|------|
| 1 | `scripts/eval_l2_shift.py` | L45 | ✅ `rng=rng` | 本轮修复 |
| 2 | `scripts/run_e1a_l2_shift_full.py` | L178 | ✅ `rng=rng` | 第一轮修复（仍有效） |
| 3 | `scripts/run_e4_temperature_analysis.py` | L308 | ✅ `rng=rng` | 本轮修复 |

**间接调用方（通过 `os.system` 调用 `eval_l2_shift.py`）**：

| # | 文件 | 调用方式 | 受影响? |
|---|------|----------|---------|
| 4 | `scripts/launch_l2_shifts.py` | `os.system("python scripts/eval_l2_shift.py ...")` | ✅ 间接修复 |
| 5 | `scripts/launch_l2_shifts_resnet1d.py` | 同上 | ✅ 间接修复 |
| 6 | `scripts/launch_l2_shifts_seed444546.py` | 同上 | ✅ 间接修复 |
| 7 | `scripts/rerun_l2_noise.py` | 同上 | ✅ 间接修复 |

**不涉及 apply_shift 的文件**：
- `scripts/summarize_l2_shifts.py`：纯 JSON 汇总，不调用 apply_shift
- `paper/generate_figures.py`：RandomState 仅用于绘图 jitter（L212/L294/L490），与噪声注入无关
- 无 `.ipynb` notebook 调用 apply_shift

**遗漏检查结论**: ✅ **无遗漏**。3 处直接调用方全部已传 rng，4 处间接调用方通过 eval_l2_shift.py 受益。

---

## 1. 逐文件审查

### 1.1 `scripts/eval_l2_shift.py` — rng 修复

**代码事实**（L36-52）：
```python
def shifted_eval(model, dataset, shift, device, batch_size=64):
    """对 dataset 的每条信号施加 shift 后评估 model。"""
    model.eval()
    all_probs, all_labels = [], []
    n = len(dataset)
    rng = np.random.RandomState(42)  # 循环外创建，确保每条信号获得不同噪声  ← L41
    for i in range(n):
        x, y = dataset[i]
        sig = x.numpy()
        sig_s = apply_shift(sig, shift, rng=rng)  ← L45
        ...
```

**审查结论**：
- ✅ rng 在循环外创建（L41 在 `for i in range(n)` 之前）
- ✅ apply_shift 调用传入 `rng=rng`（L45）
- ✅ rng 在函数内创建（非模块级），避免全局状态污染
- ⚠️ **缺陷**: rng 在 `shifted_eval` 函数内创建，**每次调用该函数都重置为 RandomState(42) 初始状态**（见攻击点 A2）

### 1.2 `scripts/run_e4_temperature_analysis.py` — rng 修复

**代码事实**（L293-314）：
```python
def shifted_probs_labels(model, dataset, shift, device):
    """对 dataset 每条信号施加 shift 后前向，返回 (probs, labels)。"""
    model.eval()
    all_probs, all_labels = [], []
    n = len(dataset)
    rng = np.random.RandomState(42)  # 循环外创建，确保每条信号获得不同噪声  ← L303
    with torch.no_grad():
        for i in range(n):
            x, y = dataset[i]
            sig = x.numpy()
            sig_s = apply_shift(sig, shift, rng=rng)  ← L308
            ...
```

**审查结论**：
- ✅ rng 在循环外创建（L303 在 `for i in range(n)` 之前）
- ✅ apply_shift 调用传入 `rng=rng`（L308）
- ✅ rng 创建位置与 eval_l2_shift.py 一致（函数内循环外）
- ⚠️ **缺陷**: 同 A2，每次调用 `shifted_probs_labels` 都重置 rng
- ⚠️ **额外缺陷**: 该函数被 `process_shift_sensitivity`（L644）对每档 shift 调用一次，5 个噪声档共享同一 RandomState(42) 初始状态（见攻击点 A2 详述）

### 1.3 `src/data/l2_shifts.py` — UserWarning

**代码事实**（L23, L182-208）：
```python
import warnings  ← L23

def apply_shift(signal, shift, rng=None):
    """..."""
    t = shift["type"]
    p = shift["params"]
    if rng is None and t == "noise":  ← L192
        warnings.warn(
            "apply_shift called with rng=None for noise shift. "
            "Each signal will receive identical noise (RandomState(42)). "
            "Pass rng=np.random.RandomState(seed) from caller for per-signal noise.",
            UserWarning,
            stacklevel=2,
        )
    if t == "downsample":
        return shift_downsample(signal, p["target_hz"])
    elif t == "leads":
        return shift_leads(signal, p["n_leads"])
    elif t == "gain":
        return shift_gain(signal, p["gain"])
    elif t == "noise":
        return shift_noise(signal, p["noise_type"], p["snr_db"], rng=rng)
    return signal
```

**审查结论**：
- ✅ `import warnings` 已添加（L23）
- ✅ UserWarning 触发条件 `if rng is None and t == "noise":` 正确：
  - rng 已传入时不触发（`rng is None` 为 False）✓
  - shift type 非 noise 时不触发（`t == "noise"` 为 False）✓
  - 仅 rng=None 且 noise 类型时触发 ✓
- ✅ Warning 消息清晰，包含问题描述 + 修复建议
- ✅ `stacklevel=2` 正确指向调用方
- ⚠️ **死代码风险**: 当前 3 个调用方全部传 rng，Warning 在正常路径**永不触发**（见攻击点 A4）

### 1.4 `scripts/run_e1a_l2_shift_full.py` — 第一轮修复完整性

**代码事实**（L171-178）：
```python
    # P0-1 修复：在循环外创建 rng，避免每次调用都创建 RandomState(42)
    # 导致等长信号获得完全相同的噪声序列。传入同一 rng 后其内部状态逐次推进，
    # 每条信号获得不同噪声；固定种子 42 保证可复现性。
    rng = np.random.RandomState(42)  ← L174
    for i in range(n):
        x, y = dataset[i]
        sig = x.numpy()
        sig_s = apply_shift(sig, shift, rng=rng)  ← L178
```

**审查结论**：
- ✅ 第一轮修复仍然有效，未被第二轮修改破坏
- ✅ rng 在循环外创建（L174）
- ✅ apply_shift 传入 `rng=rng`（L178）
- ✅ 注释完整（L171-173 解释修复原因）
- ⚠️ 同样存在 A2 缺陷（函数内创建，每次调用重置）

---

## 2. 攻击要点

### A1. rng 种子选择：RandomState(42) 引入可复现性偏差 【中危】

**主张**: 三处 rng 创建均硬编码 `RandomState(42)`，不依赖实验参数（pair, arch, seed, shift），导致**所有实验组合共享同一噪声实现**。

**证据链**：

1. `eval_l2_shift.py:41`: `rng = np.random.RandomState(42)` — 硬编码 42
2. `run_e4_temperature_analysis.py:303`: `rng = np.random.RandomState(42)` — 硬编码 42
3. `run_e1a_l2_shift_full.py:174`: `rng = np.random.RandomState(42)` — 硬编码 42

**后果**：
- **跨 seed 相关性**: 5 个实验种子（42-46）的噪声实现完全相同。跨 seed 方差仅反映模型训练变异（σ²_model），缺失噪声变异分量（σ²_noise）。安全率矩阵的种子维度方差被低估。
- **跨方向相关性**: 6 个迁移方向（ptbxl→chapman 等）的噪声基底相同。方向间对比的噪声干扰非独立。
- **跨架构相关性**: resnet1d 和 inceptiontime 在同一 (pair, seed, shift) 下施加完全相同的噪声。架构对比的噪声干扰非独立。

**反方建议**:
```python
# 方案 A：基于实验参数派生种子（推荐）
noise_seed = hash((pair, arch, seed, shift_name)) % (2**32)
rng = np.random.RandomState(noise_seed)

# 方案 B：用 None（系统随机），牺牲严格可复现性
rng = np.random.RandomState()  # 系统熵种子
```

**正方可能反驳**: 固定 42 保证可复现性，符合实验规范。
**反反方**: 可复现性不要求所有实验共享同一噪声实现。`RandomState(hash(pair, arch, seed, shift))` 同样可复现，且避免系统性偏差。当前实现是"可复现的偏差"而非"无偏差的可复现"。

**严重度**: 中危。不致结果无效，但跨 seed/方向/架构方差估计有偏，影响 E1a 安全率矩阵的种子维度结论。

---

### A2. rng 生命周期：函数内创建导致跨 shift 档噪声基底相同 【中危，技术性最强】

**主张**: rng 在 `shifted_eval` / `shifted_probs_labels` 函数内创建，**每次调用该函数都重置为 RandomState(42) 初始状态**。由于主循环对每档 shift 调用一次该函数，**5 个噪声档（noise24/12/6/0/-6）共享同一底层随机序列，仅 SNR 缩放不同**。

**证据链**（以 `eval_l2_shift.py` 为例）：

```python
# main() 中（L126-127）：
for shift in shifts:
    ood_probs, ood_labels = shifted_eval(model, tgt_ds["test"], shift, device)
    # ↑ 每档 shift 调用一次 shifted_eval

# shifted_eval() 中（L41）：
rng = np.random.RandomState(42)  # 每次调用都重置！
for i in range(n):
    sig_s = apply_shift(sig, shift, rng=rng)
```

**精确推导**：
1. `main()` 对 13 档 shift 逐档调用 `shifted_eval`（L126-127）
2. 每次调用 `shifted_eval` 在 L41 创建新 `RandomState(42)`
3. 因此 noise24 档的 rng 初始状态 = noise12 档 = noise6 档 = noise0 档 = noise-6 档
4. `shift_noise` 内部（L143）: `noise = noise * np.sqrt(noise_power)`，其中 `noise_power = sig_power / (10 ** (snr_db / 10))`
5. **5 档的 `noise` 数组在归一化前完全相同**（同一 rng 序列），仅 `np.sqrt(noise_power)` 缩放因子不同
6. 即：`noise_noise24 = noise_noise12 * (10^((24-12)/20))` 等精确比例关系

**后果**：
- 5 个噪声档**不是独立的噪声实现**，而是同一噪声的 5 个缩放版本
- 噪声档间的对比（如 noise24 vs noise12 的安全率差异）反映的是 SNR 缩放效应 + 模型对同一噪声的不同响应，**非独立噪声样本的统计对比**
- E1a 安全率矩阵中 5 个噪声档单元格的噪声干扰完全相关，违反"独立同分布噪声"假设

**run_e4_temperature_analysis.py 同样存在此问题**：
- `process_shift_sensitivity`（L642-646）对每档 shift 调用 `shifted_probs_labels`
- 每次调用在 L303 创建新 `RandomState(42)`
- 5 个噪声档的 T(shift) 值基于同一噪声基底，偏移敏感度曲线的噪声维度非独立

**run_e1a_l2_shift_full.py 同样存在此问题**：
- `evaluate_one_checkpoint`（L319-322）对每档 shift 调用 `shifted_eval`
- 每次调用在 L174 创建新 `RandomState(42)`

**反方建议**:
```python
# 方案：在主循环外创建 rng，跨 shift 共享
rng = np.random.RandomState(42)  # 或基于实验参数派生
for shift in shifts:
    ood_probs, ood_labels = shifted_eval(model, tgt_ds["test"], shift, device, rng=rng)

# 或：每档 shift 用不同种子
for shift in shifts:
    shift_seed = hash((pair, arch, seed, shift["name"])) % (2**32)
    ood_probs, ood_labels = shifted_eval(model, tgt_ds["test"], shift, device, seed=shift_seed)
```

**正方可能反驳**: 每档 shift 独立创建 rng 保证档间可复现性，且每档内部每条信号噪声不同，已满足 P0-1 修复目标。
**反反方**: P0-1 的原始描述是"每条信号获得相同噪声"，修复目标是"每条信号获得不同噪声"。当前修复在**单档内**实现了每条信号不同噪声，但在**跨档间**引入了更强的相关性——5 档共享同一噪声基底。这是修复引入的新缺陷，非原始 bug 的简单修复。若正方认为"档间独立"非 P0-1 范畴，应在 docstring 显式声明此设计选择并接受反方在方差估计上的攻击。

**严重度**: 中危。影响噪声档间对比的统计有效性，但不致单档结果无效。

---

### A3. Warning 触发条件正确但消息可改进 【低危，吹毛求疵】

**主张**: UserWarning 触发条件 `if rng is None and t == "noise":` 逻辑正确，但消息中"Each signal will receive identical noise"的表述在 `apply_shift` 单次调用语境下不准确。

**证据**:
- `apply_shift` 是对**单条信号**施加变换（L182-183 docstring: "对单条信号施加移位变换"）
- Warning 消息说"Each signal will receive identical noise"，但 `apply_shift` 单次调用只处理一条信号
- "Each signal" 的语义在调用方循环语境下才成立，但 Warning 在 `apply_shift` 层发出

**反方建议**:
```python
warnings.warn(
    "apply_shift(rng=None) for noise shift: rng will be created as "
    "RandomState(42) internally. If called in a loop without passing a "
    "shared rng, every signal will receive identical noise. "
    "Pass rng=np.random.RandomState(seed) from caller for per-signal noise.",
    UserWarning,
    stacklevel=2,
)
```

**严重度**: 低危（文档表述精度问题，不影响功能）。

---

### A4. UserWarning 在当前代码库中是死代码 【低危，防御性价值仍在】

**主张**: 当前 3 个直接调用方全部传 rng，UserWarning 在正常执行路径**永不触发**。Warning 仅在未来新增调用方忘记传 rng 时才有用。

**证据**:
- `eval_l2_shift.py:45`: `apply_shift(sig, shift, rng=rng)` — 传 rng
- `run_e1a_l2_shift_full.py:178`: `apply_shift(sig, shift, rng=rng)` — 传 rng
- `run_e4_temperature_analysis.py:308`: `apply_shift(sig, shift, rng=rng)` — 传 rng
- 三处均传 rng → `rng is None` 恒为 False → Warning 恒不触发

**反方评估**:
- 这**不是缺陷**，而是防御性编程的合理实践。Warning 的价值在于防止未来回归。
- 但应在代码审查规范中记录："新增 apply_shift 调用方必须传 rng，否则触发 UserWarning"，否则 Warning 的防御价值会随时间被遗忘。
- 建议在 `l2_shifts.py` 的模块 docstring 中补充调用规范说明。

**严重度**: 低危（防御性价值仍在，但需配套审查规范）。

---

### A5. 三处 rng 创建模式一致性 【通过，附注】

**主张**: 三处 rng 创建模式（函数内循环外 + RandomState(42)）一致。

**证据**:
| 文件 | 创建位置 | 种子 | 模式 |
|------|----------|------|------|
| eval_l2_shift.py:41 | shifted_eval 函数内循环外 | 42 | 一致 |
| run_e1a_l2_shift_full.py:174 | shifted_eval 函数内循环外 | 42 | 一致 |
| run_e4_temperature_analysis.py:303 | shifted_probs_labels 函数内循环外 | 42 | 一致 |

**审查结论**: ✅ 模式一致。但"一致的缺陷"仍是缺陷（A1 + A2 在三处均成立）。

---

## 3. 修复完整性总评

### 3.1 第二轮修复目标达成情况

| 目标 | 达成? | 证据 |
|------|-------|------|
| eval_l2_shift.py 传 rng | ✅ | L45 `apply_shift(sig, shift, rng=rng)` |
| run_e4_temperature_analysis.py 传 rng | ✅ | L308 `apply_shift(sig, shift, rng=rng)` |
| l2_shifts.py 添加 UserWarning | ✅ | L192-199 `if rng is None and t == "noise": warnings.warn(...)` |
| UserWarning 不误触发 | ✅ | 条件 `rng is None and t == "noise"` 逻辑正确 |
| 第一轮修复不被破坏 | ✅ | run_e1a_l2_shift_full.py L174/L178 未变 |
| 无其他遗漏调用方 | ✅ | grep 全项目确认 3 处直接 + 4 处间接，全部覆盖 |

**完整性结论**: ✅ **第二轮修复目标全部达成**。3 处直接调用方全部传 rng，UserWarning 防御性修复到位，第一轮修复未被破坏，无遗漏调用方。

### 3.2 修复正确性问题（非完整性问题）

| 攻击点 | 严重度 | 是否成立 | 影响 |
|--------|--------|----------|------|
| A1: 硬编码 42 引入可复现性偏差 | 中危 | ✅ 成立 | 跨 seed/方向/架构方差估计有偏 |
| A2: 函数内创建导致跨档噪声基底相同 | 中危 | ✅ 成立 | 5 噪声档非独立实现，档间对比失效 |
| A3: Warning 消息表述不精确 | 低危 | ✅ 成立 | 文档精度问题 |
| A4: Warning 当前为死代码 | 低危 | ⚠️ 部分成立 | 防御性价值仍在，需配套规范 |

---

## 4. 反方最终立场

### 4.1 不成立的攻击（反方主动撤回）

- **"修复不完整"**: ❌ 撤回。3 处直接调用方全部修复，grep 确认无遗漏。
- **"UserWarning 误触发"**: ❌ 撤回。条件 `rng is None and t == "noise"` 逻辑正确，正常路径不触发。
- **"第一轮修复被破坏"**: ❌ 撤回。run_e1a_l2_shift_full.py L174/L178 未变。

### 4.2 成立的攻击（反方坚持）

- **A1（中危）**: 硬编码 RandomState(42) 引入可复现性偏差，跨 seed/方向/架构噪声实现相同。**建议改为基于实验参数派生种子**。
- **A2（中危）**: 函数内创建 rng 导致跨 shift 档噪声基底相同，5 个噪声档非独立实现。**建议在主循环外创建 rng 或每档用不同种子**。
- **A3（低危）**: Warning 消息表述可改进。**建议明确"循环语境"前提**。
- **A4（低危）**: Warning 当前为死代码，防御性价值需配套审查规范。**建议在模块 docstring 补充调用规范**。

### 4.3 对正方的建议

**优先级 P1（建议本轮修复）**:
- A2: 将 rng 创建移到主循环外（跨 shift 共享），或每档 shift 用 `RandomState(hash(shift_name))` 派生种子。这是修复引入的新缺陷，应在本轮一并修复。

**优先级 P2（建议下轮修复）**:
- A1: 将 rng 种子改为基于实验参数派生，消除跨 seed/方向/架构偏差。需评估对已有结果可复现性的影响。

**优先级 P3（文档改进）**:
- A3: 改进 Warning 消息表述。
- A4: 在 l2_shifts.py docstring 补充 apply_shift 调用规范。

### 4.4 反方签字

**第二轮修复完整性**: ✅ **通过**（3 处调用方全部修复，无遗漏）
**第二轮修复正确性**: ⚠️ **有条件通过**（A1/A2 中危缺陷成立，建议修复 A2 后再放行）

> 反方坚持 A2 应在本轮修复，因其是"修复引入的新缺陷"（跨档噪声相关性）而非预先存在的独立问题。若正方选择不修复 A2，应在 E1a 实验报告显式声明"5 个噪声档共享同一噪声基底，档间对比非独立"，并接受反方在方差估计有效性上的后续攻击。

---

## 附录 A: 审查命令记录

```
1. read D:\A1\ecg-lab-v2\scripts\run_e1a_l2_shift_full.py
2. read D:\A1\ecg-lab-v2\scripts\eval_l2_shift.py
3. read D:\A1\ecg-lab-v2\scripts\run_e4_temperature_analysis.py
4. read D:\A1\ecg-lab-v2\src\data\l2_shifts.py
5. grep apply_shift (全项目) → 3 处直接调用 + docs 引用
6. grep RandomState (全项目) → 3 处 rng 创建 + generate_figures.py jitter（无关）
7. grep shift_noise|shift_downsample|shift_leads|shift_gain → 确认 apply_shift 是唯一公共入口
8. grep shifted_eval|shifted_probs_labels → 确认 2 个封装函数的调用方
9. read rerun_l2_noise.py → 确认通过 os.system 间接调用 eval_l2_shift.py
10. grep apply_shift in launch_l2_shifts*.py → 确认通过 os.system 间接调用
11. read summarize_l2_shifts.py (前30行) → 确认纯 JSON 汇总，不调用 apply_shift
12. grep apply_shift in *.ipynb → 无 notebook 调用
```

## 附录 B: 攻击点与第一轮报告的对照

| 本轮攻击点 | 第一轮报告对应 | 状态 |
|------------|----------------|------|
| A1 (硬编码 42) | p0_attack_p0_1.md 攻击 2 | 第一轮已提出，本轮确认三处一致存在 |
| A2 (跨档重置) | p0_attack_p0_1.md 攻击 2 第3点 | 第一轮已提出"跨噪声档相关性"，本轮确认三处一致存在 |
| A3 (Warning 消息) | — | 本轮新增（第一轮无 UserWarning） |
| A4 (死代码) | — | 本轮新增（第一轮无 UserWarning） |
| 遗漏检查 | p0_attack_p0_1.md 攻击 1 | 第一轮发现 2 处遗漏，本轮确认已修复 |
