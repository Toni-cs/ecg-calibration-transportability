# P0-1 反反方审查报告（R2轮）

> **审查代理**: 反反方-P0R2-counter (session 6d496f64)
> **审查对象**: 反方攻击报告 `docs/p0r2_attack_p0_1.md`（4 个攻击点 A1-A4）
> **审查日期**: 2026-09-09
> **审查方法**: 逐条核验攻击报告引用的代码行号与事实，独立判定每个攻击点的成立性

## 审查概要
- 攻击报告：docs/p0r2_attack_p0_1.md
- 攻击点总数：4（A1, A2, A3, A4；A5 为一致性附注，非攻击点）
- **成立：2**（A1, A2）| **部分成立：1**（A3）| **不成立：1**（A4）

### 判定汇总表

| 攻击点 | 反方主张 | 反方严重度 | 反反方判定 | 反反方理由 |
|--------|----------|------------|------------|------------|
| A1 | 硬编码 42 引入可复现性偏差 | 中危 | **成立** | 事实核验通过，跨 seed/方向/架构确实共享噪声实现 |
| A2 | 函数内创建导致跨档噪声基底相同 | 中危 | **成立**（但"修复引入新缺陷"表述不准确） | 事实核验通过，5 噪声档确实共享基底；但此为预存在独立问题，非修复引入 |
| A3 | Warning 消息"Each signal"表述不精确 | 低危 | **部分成立** | 消息确实不精确，但反方自承"吹毛求疵"，实际影响极小 |
| A4 | Warning 当前为死代码 | 低危 | **不成立** | 反方自承"不是缺陷，而是防御性编程合理实践"，不构成攻击 |

---

## 逐条审查

### 攻击点1: A1 — rng 种子选择：RandomState(42) 引入可复现性偏差

**判定**: 成立

**事实核验**:
- `eval_l2_shift.py:41`: `rng = np.random.RandomState(42)` — 硬编码 42，不依赖 `args.seed`/`args.source`/`args.target`/`args.arch`/`shift["name"]` ✓
- `run_e4_temperature_analysis.py:303`: `rng = np.random.RandomState(42)` — 硬编码 42，不依赖 `pair`/`arch`/`seed`/`shift` ✓
- `run_e1a_l2_shift_full.py:174`: `rng = np.random.RandomState(42)` — 硬编码 42 ✓

**分析**:

攻击报告的事实陈述准确。三处 rng 创建均硬编码 `RandomState(42)`，不依赖任何实验参数。后果推导成立：

1. **跨 seed 相关性**: `eval_l2_shift.py` 主循环 L80 `for seed in args.seeds:` 内，每个 seed 调用 `shifted_eval` 时都创建 `RandomState(42)`。5 个种子（42-46）的噪声实现完全相同。跨 seed 方差仅反映模型训练变异 σ²_model，缺失噪声变异分量 σ²_noise，方差被低估。
2. **跨方向相关性**: 6 个迁移方向（ptbxl→chapman 等）的噪声基底相同。方向间对比的噪声干扰非独立。
3. **跨架构相关性**: resnet1d 和 inceptiontime 在同一 (pair, seed, shift) 下施加完全相同的噪声。

反方在"反反方"段落中的论证是正确的：可复现性不要求所有实验共享同一噪声实现。`RandomState(hash(pair, arch, seed, shift))` 同样可复现，且避免系统性偏差。当前实现确实是"可复现的偏差"而非"无偏差的可复现"。

**严重度评估**: 中危合理。不致单格结果无效，但跨 seed/方向/架构方差估计有偏，影响 E1a 安全率矩阵的种子维度结论。反方已明确"不致结果无效"，未夸大严重度。

**修补方案**:
- **文件**: `scripts/eval_l2_shift.py`
- **行号**: L41
- **改动**: 将硬编码 42 改为基于实验参数派生种子。需将 `seed`/`args.source`/`args.target`/`args.arch`/`shift["name"]` 传入 `shifted_eval` 并派生种子：
  ```python
  def shifted_eval(model, dataset, shift, device, batch_size=64, 
                   pair_id=None, arch=None, train_seed=None):
      """对 dataset 的每条信号施加 shift 后评估 model。"""
      model.eval()
      all_probs, all_labels = [], []
      n = len(dataset)
      # 基于实验参数派生噪声种子，避免跨实验组合共享同一噪声实现
      shift_name = shift["name"]
      noise_seed = abs(hash((pair_id, arch, train_seed, shift_name))) % (2**32)
      rng = np.random.RandomState(noise_seed)
      ...
  ```
  并在 L127 调用处传入 `pair_id=f"{args.source}_{args.target}", arch=args.arch, train_seed=seed`。
- **同步改动**: `run_e4_temperature_analysis.py:303` 和 `run_e1a_l2_shift_full.py:174` 同样改造。
- **注意**: 此改动会影响已有 `l2_shift_results.json` 的可复现性。需在实验报告中显式声明种子派生策略变更，并重跑受影响实验。

---

### 攻击点2: A2 — rng 生命周期：函数内创建导致跨 shift 档噪声基底相同

**判定**: 成立（但"修复引入的新缺陷"表述不准确，应为"修复范围外的预存在独立问题"）

**事实核验**:

1. `eval_l2_shift.py` L126-127 主循环：`for shift in shifts: ood_probs, ood_labels = shifted_eval(model, tgt_ds["test"], shift, device)` — 对每档 shift 调用一次 `shifted_eval` ✓
2. `eval_l2_shift.py` L41: `rng = np.random.RandomState(42)` 在 `shifted_eval` 函数内创建 — 每次调用都重置 ✓
3. `run_e4_temperature_analysis.py` L642-646 主循环：`for shift in shifts: ... shifted_probs_labels(model, src_ds["cal"], shift, device)` — 对每档 shift 调用一次 ✓
4. `run_e4_temperature_analysis.py` L303: `rng = np.random.RandomState(42)` 在 `shifted_probs_labels` 函数内创建 ✓
5. `run_e1a_l2_shift_full.py` L319-322 主循环：`for shift in shifts: ... shifted_eval(model, tgt_ds["test"], shift, device)` ✓
6. `run_e1a_l2_shift_full.py` L174: `rng = np.random.RandomState(42)` 在 `shifted_eval` 函数内创建 ✓

**精确推导验证**:

`shift_noise`（`l2_shifts.py` L110-146）的逻辑：
- L122: `sig_power = np.mean(signal ** 2)` — 对同一信号，5 档 sig_power 相同
- L125: `noise_power = sig_power / (10 ** (snr_db / 10))` — 仅 snr_db 不同
- L130-137: `noise_type == "mixed"` 分支调用 `_synthetic_noise` 生成 bwl/ma/em，使用传入的 rng
- L142-144: `noise = noise - noise.mean(); noise = noise / noise.std()` — 归一化
- L145: `noise = noise * np.sqrt(noise_power)` — 最终缩放

**关键推导**: 对于 dataset[0]：
- noise24 档：`shifted_eval` 创建 `rng=RandomState(42)`，调用 `shift_noise(sig, "mixed", 24, rng=rng)`，生成 `noise_24 = base_noise * sqrt(power_24)`
- noise12 档：`shifted_eval` 重新创建 `rng=RandomState(42)`（重置！），调用 `shift_noise(sig, "mixed", 12, rng=rng)`，生成 `noise_12 = base_noise * sqrt(power_12)`
- 由于 rng 初始状态相同、n_samples 相同、noise_type 相同，`base_noise` 完全相同，仅 `sqrt(power)` 缩放因子不同 ✓

对于 dataset[1]：
- noise24 档：rng 状态已推进（经过 dataset[0] 的噪声生成），生成 `noise_24_1 = base_noise_1 * sqrt(power_24)`
- noise12 档：rng 状态已推进（经过 dataset[0] 的噪声生成，且推进量相同因为 rng 初始状态相同且操作相同），生成 `noise_12_1 = base_noise_1 * sqrt(power_12)`
- `base_noise_1` 完全相同 ✓

**结论**: 5 个噪声档确实共享同一噪声基底，仅 SNR 缩放不同。攻击事实成立。

**对"修复引入的新缺陷"表述的反驳**:

反方在 A2 中称"这是修复引入的新缺陷，非原始 bug 的简单修复"。此表述**不准确**：

- **原始 bug**: rng 在循环内创建 → 每条信号获得相同噪声。在此状态下，跨档共享噪声基底是**显而易见的**（因为每档每条都相同，跨档必然共享）。
- **修复后**: rng 在循环外创建 → 每条信号获得不同噪声。跨档共享仍然存在（因为每档 rng 都重置为 42）。
- **事实**: 跨档共享在修复前就存在，修复后仍然存在。这不是"修复引入的新缺陷"，而是"修复范围外的预存在独立问题"。

P0-1 的原始描述是"每条信号获得相同噪声"，修复目标是"每条信号获得不同噪声"。跨档独立性**不在 P0-1 的明确修复范围内**。修复成功达成了 P0-1 的目标（单档内每条信号噪声不同），但未解决跨档独立性这个独立问题。

反方的论据"修复后跨档共享变得隐蔽"有一定道理——修复前每条相同是显而易见的问题，修复后每条不同容易让人误以为档间独立。但"隐蔽性增加"不等于"引入新缺陷"。准确表述应为：**"修复未解决跨档独立性问题，且修复后此问题变得隐蔽，建议作为独立问题修复"**。

**严重度评估**: 中危合理。影响噪声档间对比的统计有效性，但不致单档结果无效。反方已明确"不致单档结果无效"，未夸大严重度。

**修补方案**:
- **方案 A（推荐）**: 在主循环外创建 rng，跨 shift 共享同一 rng（状态逐档推进）
  - **文件**: `scripts/eval_l2_shift.py`
  - **行号**: L36-52（`shifted_eval` 函数签名增加 `rng` 参数）+ L126-127（主循环外创建 rng）
  - **改动**:
    ```python
    def shifted_eval(model, dataset, shift, device, batch_size=64, rng=None):
        """对 dataset 的每条信号施加 shift 后评估 model。"""
        model.eval()
        all_probs, all_labels = [], []
        n = len(dataset)
        if rng is None:
            rng = np.random.RandomState(42)
        for i in range(n):
            ...
    ```
    主循环改为：
    ```python
    # 在 for shift in shifts 循环外创建 rng，跨档共享（状态逐档推进）
    cross_shift_rng = np.random.RandomState(42)
    for shift in shifts:
        ood_probs, ood_labels = shifted_eval(model, tgt_ds["test"], shift, device, rng=cross_shift_rng)
    ```
  - **同步改动**: `run_e4_temperature_analysis.py` L293-314 + L642-646；`run_e1a_l2_shift_full.py` L163-185 + L319-322
- **方案 B**: 每档 shift 用不同种子派生（与 A1 修补方案合并）
  ```python
  for shift in shifts:
      shift_seed = abs(hash((pair, arch, seed, shift["name"]))) % (2**32)
      rng = np.random.RandomState(shift_seed)
      ood_probs, ood_labels = shifted_eval(model, tgt_ds["test"], shift, device, rng=rng)
  ```
- **注意**: 方案 A 使跨档噪声基底不同（rng 状态逐档推进），但跨实验组合仍共享（除非同时修 A1）。方案 B 同时解决 A1 和 A2。建议采用方案 B 一次性修复 A1+A2。

---

### 攻击点3: A3 — Warning 触发条件正确但消息可改进

**判定**: 部分成立

**事实核验**:
- `l2_shifts.py` L182-183 docstring: "对单条信号施加移位变换" — `apply_shift` 确实是单条信号接口 ✓
- `l2_shifts.py` L194-196 Warning 消息: `"apply_shift called with rng=None for noise shift. Each signal will receive identical noise (RandomState(42)). Pass rng=np.random.RandomState(seed) from caller for per-signal noise."` ✓

**分析**:

**成立部分**:
- `apply_shift` 单次调用只处理一条信号（docstring 明确"对单条信号施加移位变换"）
- Warning 消息说"Each signal will receive identical noise"，但 `apply_shift` 单次调用只有一条信号，不存在"each"
- "Each signal" 的语义在调用方循环语境下才成立，但 Warning 在 `apply_shift` 层发出
- 严格语义上，消息确实不精确

**夸大部分**:
- 反方自己将此攻击标为"低危（吹毛求疵）"，承认"不影响功能"
- 消息的实用价值仍在：调用方能理解"如果不传 rng，会导致信号获得相同噪声"的核心意图
- 当前消息并非"错误"，只是"不够精确"——它描述的是 Warning 的**典型触发场景**（循环内调用），而非 `apply_shift` 单次调用的字面语义
- 反方建议的改进消息确实更精确，但改进收益主要是文档精度，非功能或正确性提升

**严重度评估**: 低危合理（反方自承"吹毛求疵"）。实际影响极小，不影响 Warning 的防御功能。

**修补方案**（建议采纳，低成本）:
- **文件**: `src/data/l2_shifts.py`
- **行号**: L193-199
- **改动**: 采纳反方建议，改进消息表述：
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

---

### 攻击点4: A4 — UserWarning 在当前代码库中是死代码

**判定**: 不成立（作为缺陷攻击）

**事实核验**:
- `eval_l2_shift.py:45`: `apply_shift(sig, shift, rng=rng)` — 传 rng ✓
- `run_e1a_l2_shift_full.py:178`: `apply_shift(sig, shift, rng=rng)` — 传 rng ✓
- `run_e4_temperature_analysis.py:308`: `apply_shift(sig, shift, rng=rng)` — 传 rng ✓
- 三处均传 rng → `rng is None` 恒为 False → Warning 恒不触发 ✓

**反驳**:

1. **反方自相矛盾**: 反方在 A4 中明确写道："这**不是缺陷**，而是防御性编程的合理实践。Warning 的价值在于防止未来回归。" 既然反方自己承认这不是缺陷，则不构成有效攻击点。将"防御性编程"列为"攻击点"是稻草人论证。

2. **防御性代码的工程价值**: Warning 的设计目标是**防止未来回归**，而非"在当前代码中触发"。这是软件工程的标准实践：
   - 类型检查、断言、契约检查在正常路径下都不触发，但它们不是"死代码"
   - `if __name__ == "__main__":` 守卫在作为模块导入时不触发，但不是"死代码"
   - UserWarning 在当前 3 个调用方都正确传 rng 时不触发，但能在未来新增调用方忘记传 rng 时立即告警，这正是其设计目的

3. **反方建议合理但非攻击**: 反方建议"在 `l2_shifts.py` 的模块 docstring 中补充调用规范说明"是合理的改进建议，但这属于**文档增强**，而非**缺陷修复**。将其列为"攻击点"混淆了"改进建议"与"缺陷指控"的界限。

4. **反方严重度自评矛盾**: 反方标"低危（防御性价值仍在，但需配套审查规范）"。"防御性价值仍在"即承认其有价值，"需配套审查规范"是流程建议而非代码缺陷。这与"攻击"的定义（"正方修复确实有问题"）不符。

**结论**: A4 不成立作为缺陷攻击。反方自己撤回缺陷指控（"这不是缺陷"），仅保留文档增强建议。文档增强建议可采纳，但不构成对正方修复正确性的攻击。

**附注**（采纳反方建议作为改进，非缺陷修复）:
- **文件**: `src/data/l2_shifts.py`
- **行号**: L1-20（模块 docstring）
- **改动**: 在模块 docstring 末尾补充调用规范：
  ```
  调用规范：
  - apply_shift 的 noise 类型 shift 必须传入 rng 参数（从调用方创建并传入）
  - 若 rng=None 且 t=="noise"，将触发 UserWarning（防御性检查）
  - 新增 apply_shift 调用方必须在循环外创建 rng 并传入，避免每条信号获得相同噪声
  ```

---

## 对反方攻击报告的整体评价

### 反方报告的优点
1. **事实核验扎实**: 攻击报告引用的代码行号全部准确，无虚构事实
2. **证据链完整**: A1/A2 的推导链条清晰，从代码事实到后果分析逻辑严密
3. **自我撤回诚实**: 反方主动撤回"修复不完整""UserWarning 误触发""第一轮修复被破坏"三个不成立攻击，体现审查诚信
4. **严重度评估合理**: A1/A2 中危、A3/A4 低危的分级符合实际影响，未夸大
5. **修补建议具体**: 反方提供的修补方案 A/B 可操作性强

### 反方报告的问题
1. **A2"修复引入新缺陷"表述不准确**: 跨档共享是预存在独立问题，非修复引入。修复未解决此问题，但也未引入此问题。准确表述应为"修复范围外的预存在独立问题，修复后变得隐蔽"。
2. **A4 列为攻击点不当**: 反方自承"不是缺陷"，将其列为攻击点混淆了"改进建议"与"缺陷指控"的界限。
3. **A3 严重度自评矛盾**: 标为"低危（吹毛求疵）"同时列为攻击点，若自认吹毛求疵则不应列为攻击。

---

## 总结

### 需要进一步修复的问题清单

| 优先级 | 问题 | 严重度 | 修补方案 |
|--------|------|--------|----------|
| P1 | A2: 跨档噪声基底共享 | 中危 | 方案 B：每档 shift 用 `RandomState(hash(pair, arch, seed, shift_name))` 派生种子（同时解决 A1） |
| P1 | A1: 硬编码 42 跨实验共享 | 中危 | 与 A2 合并修复，采用基于实验参数派生种子 |
| P3 | A3: Warning 消息表述 | 低危 | 采纳反方建议改进消息文本（低成本，可选） |
| P3 | A4 附注: 模块 docstring 调用规范 | 低危 | 在 l2_shifts.py docstring 补充调用规范（文档增强，非缺陷修复） |

### 已确认修复完成的问题
- ✅ 3 处直接调用方全部传 rng（eval_l2_shift.py / run_e1a_l2_shift_full.py / run_e4_temperature_analysis.py）
- ✅ UserWarning 触发条件 `if rng is None and t == "noise":` 逻辑正确
- ✅ 第一轮修复未被破坏（run_e1a_l2_shift_full.py L174/L178 未变）
- ✅ 无遗漏调用方（grep 全项目确认 3 处直接 + 4 处间接）
- ✅ P0-1 原始修复目标达成：单档内每条信号获得不同噪声（rng 在循环外创建，状态逐次推进）

### 对正方修复的总体评价

**P0-1 修复目标达成**: ✅ 通过。原始 bug"每条信号获得相同噪声"已修复，单档内每条信号现在获得不同噪声。

**修复完整性**: ✅ 通过。3 处直接调用方全部修复，无遗漏，第一轮修复未被破坏。

**修复正确性**: ⚠️ 有条件通过。
- A1/A2 成立，但属于"修复范围外的独立问题"（跨实验/跨档噪声独立性），非 P0-1 原始修复目标的范畴。
- 建议采用反方方案 B（基于实验参数派生种子）一次性修复 A1+A2，将 rng 种子改为 `RandomState(hash(pair, arch, seed, shift_name))`，同时解决跨实验和跨档共享问题。
- 若正方选择不修复 A1/A2，应在 E1a 实验报告显式声明"所有实验组合共享同一噪声实现，5 个噪声档共享同一噪声基底，跨 seed/方向/架构/档方差估计有偏"，并接受反方在方差估计有效性上的后续攻击。

**最终立场**: 反方攻击报告整体质量高，A1/A2 攻击成立且修补建议可操作。建议正方采纳方案 B 一次性修复 A1+A2，并可选采纳 A3/A4 的文档改进建议。修复后 P0-1 可放行。
