# P0-1 反方攻击报告

## 攻击摘要

对正方 P0-1 修复（`src/data/l2_shifts.py` 添加 rng 参数 + `scripts/run_e1a_l2_shift_full.py` 循环外创建 rng）进行 7 维度全攻击审查。

**发现 5 个攻击点**：
- 严重：2 个（遗漏调用方，bug 在其他脚本中仍然存活）
- 严重：1 个（固定种子 42 引入跨实验相关性，方差低估）
- 轻微：1 个（rng=None 默认值静默保留 bug）
- 轻微：1 个（多进程安全隐患）

**7 维度攻击结果**：

| 维度 | 结果 |
|------|------|
| 1. 反例构造 | ✅ 找到：eval_l2_shift.py 仍产生相同噪声 |
| 2. 逻辑断链 | ✅ 找到：修复声明"复用 eval_l2_shift.py 逻辑"但 eval_l2_shift.py 未修 |
| 3. 隐含假设 | ✅ 找到：假设固定种子42不引入偏差——不成立 |
| 4. 边界失效 | ✅ 找到：rng=None 默认值退化为 bug 行为 |
| 5. 自相矛盾 | ✅ 找到：5 个 seed 实验声称独立，但共享同一噪声实现 |
| 6. 量级错误 | ✅ 找到：跨 seed 方差被低估（缺失噪声方差分量） |
| 7. 语义偏移 | ✅ 找到："可复现性"被偷换为"确定性"——所有运行完全相同 |

---

## 攻击点列表

### 攻击 1: eval_l2_shift.py 遗漏修复——原始 bug 仍然存活

- **严重程度**: 严重
- **位置**: `scripts/eval_l2_shift.py:44`
- **描述**: 正方仅修复了 `run_e1a_l2_shift_full.py`，但 `eval_l2_shift.py` 的 `shifted_eval` 函数仍调用 `apply_shift(sig, shift)` 不传 rng。由于 `apply_shift` 的 `rng=None` 默认值会在 `shift_noise` 内部每次创建 `RandomState(42)`，**该脚本中每条等长信号仍获得完全相同的噪声序列**——这正是 P0-1 声称要修复的 bug。

- **反例/证据**:
  ```python
  # eval_l2_shift.py:36-51 — 未修复的 shifted_eval
  def shifted_eval(model, dataset, shift, device, batch_size=64):
      model.eval()
      all_probs, all_labels = [], []
      n = len(dataset)
      for i in range(n):
          x, y = dataset[i]
          sig = x.numpy()
          sig_s = apply_shift(sig, shift)  # ← 第44行：不传 rng！
          # ...
  ```
  对比 `run_e1a_l2_shift_full.py:174-178`（已修复）：
  ```python
  rng = np.random.RandomState(42)  # 循环外创建
  for i in range(n):
      sig_s = apply_shift(sig, shift, rng=rng)  # 传入 rng
  ```
  `eval_l2_shift.py` 是 `run_e1a_l2_shift_full.py` docstring 第 13-14 行声称"复用已验证的 eval_l2_shift.py 评估管线"的原始管线。正方修复了复制品却未修复原件。

- **影响**: 
  - `eval_l2_shift.py` 产出的 `l2_shift_results.json` 中噪声档结果仍然无效（所有信号同一噪声）
  - `rerun_l2_noise.py` 通过 `os.system` 调用 `eval_l2_shift.py`（第 64-68 行），因此 `rerun_l2_noise.py` 的重跑结果也无效
  - 如果有人用 `eval_l2_shift.py` 做单独评估，会得到错误结论

- **建议修复**: 在 `eval_l2_shift.py:shifted_eval` 中同样添加循环外 rng 创建：
  ```python
  def shifted_eval(model, dataset, shift, device, batch_size=64):
      model.eval()
      all_probs, all_labels = [], []
      n = len(dataset)
      rng = np.random.RandomState(42)  # 循环外创建
      for i in range(n):
          x, y = dataset[i]
          sig = x.numpy()
          sig_s = apply_shift(sig, shift, rng=rng)
          # ...
  ```

---

### 攻击 2: run_e4_temperature_analysis.py 遗漏修复——偏移敏感度分析噪声失效

- **严重程度**: 严重
- **位置**: `scripts/run_e4_temperature_analysis.py:307`（`shifted_probs_labels` 函数）
- **描述**: `run_e4_temperature_analysis.py` 的 `shifted_probs_labels` 函数同样调用 `apply_shift(sig, shift)` 不传 rng。该函数被 `process_shift_sensitivity`（第 633 行）调用，用于偏移敏感度分析（T(shift) 曲线）。由于不传 rng，每条信号获得相同噪声，导致偏移敏感度分析中噪声档的 T(shift) 值基于错误数据。

- **反例/证据**:
  ```python
  # run_e4_temperature_analysis.py:293-313 — 未修复
  def shifted_probs_labels(model, dataset, shift, device):
      model.eval()
      all_probs, all_labels = [], []
      n = len(dataset)
      with torch.no_grad():
          for i in range(n):
              x, y = dataset[i]
              sig = x.numpy()
              sig_s = apply_shift(sig, shift)  # ← 第307行：不传 rng！
              # ...
  ```
  该函数被 `process_shift_sensitivity` 调用（第 631-635 行）：
  ```python
  for shift in shifts:
      cal_probs_s, cal_labels_s = shifted_probs_labels(
          model, src_ds["cal"], shift, device  # 不传 rng
      )
      T_s, status_s = fit_global_T(cal_probs_s, cal_labels_s)
  ```
  偏移敏感度分析的核心主张 M3（"T 随 shift 单调变化"）依赖 T(shift) 曲线，但噪声档的 T_shift 值基于"所有信号同一噪声"的错误数据。

- **影响**:
  - `results/temperature_shift_sensitivity.csv` 中噪声档的 T_shift 值无效
  - E4 核心主张 M3（偏移敏感度）在噪声档上不成立
  - 如果论文引用 E4 的 T(shift) 曲线做"校准温度对输入漂移敏感度"论证，结论不可靠

- **建议修复**: 在 `shifted_probs_labels` 中添加循环外 rng 创建并传入：
  ```python
  def shifted_probs_labels(model, dataset, shift, device):
      model.eval()
      all_probs, all_labels = [], []
      n = len(dataset)
      rng = np.random.RandomState(42)  # 循环外创建
      with torch.no_grad():
          for i in range(n):
              x, y = dataset[i]
              sig = x.numpy()
              sig_s = apply_shift(sig, shift, rng=rng)
              # ...
  ```

---

### 攻击 3: 固定种子 42 引入跨实验噪声相关性——方差低估

- **严重程度**: 严重
- **位置**: `scripts/run_e1a_l2_shift_full.py:174`（`rng = np.random.RandomState(42)`）
- **描述**: 正方在 `shifted_eval` 中硬编码 `RandomState(42)`。该函数被 `evaluate_one_checkpoint` 对每个 (source, target, arch, seed, shift) 组合调用，每次调用都创建新的 `RandomState(42)`。这意味着：

  1. **跨 seed 相关性**：5 个实验种子（42-46）仅控制模型训练和数据分割，噪声实现完全相同（都是 seed 42）。实验声称通过 5 个种子估计"安全率的统计稳定性"，但实际上 5 个种子只捕获模型训练方差，**缺失噪声方差分量**。跨 seed 方差被系统性低估。

  2. **跨方向/架构相关性**：6 个方向 × 2 架构 = 12 个实验组合的噪声实现完全相同。如果某个噪声实现恰好对某类信号不利，所有 12 个组合同时受影响——它们不是独立的。

  3. **跨噪声档相关性**：5 个噪声档（noise24, noise12, noise6, noise0, noise-6）每次都从 `RandomState(42)` 开始，底层随机抽取（uniform, randn, randint）完全相同，仅 SNR 缩放不同。这 5 档不是独立的噪声实现，而是同一噪声的不同缩放。

- **反例/证据**:
  ```python
  # run_e1a_l2_shift_full.py:163-185
  def shifted_eval(model, dataset, shift, device):
      rng = np.random.RandomState(42)  # 硬编码 42，不依赖实验 seed
      for i in range(n):
          sig_s = apply_shift(sig, shift, rng=rng)
  ```
  对比实验种子设置（第 306 行）：
  ```python
  set_seed(seed)  # seed ∈ {42,43,44,45,46}，控制模型和数据
  ```
  噪声 rng（42）与实验 seed（42-46）独立。对于 seed=43 的实验，模型用 seed 43 训练，但噪声用 seed 42 生成——两者不匹配。

  **具体反例**：假设安全率对噪声实现敏感（某些噪声实现使 TS 改善 Brier rel，另一些不）。用 5 个不同噪声种子可估计安全率对噪声的方差 σ²_noise。但当前修复中 5 个 seed 的噪声完全相同，σ²_noise = 0 被错误估计。总方差 σ²_total = σ²_model + σ²_noise 被低估为 σ²_model。

- **影响**:
  - 390 矩阵中跨 seed 的安全率变异仅反映模型训练变异，不反映噪声变异
  - 如果论文声称"跨 5 seed 的安全率稳定性"作为鲁棒性证据，该证据不完整
  - 5 个噪声档的 safety_rate 之间存在人为相关性，影响跨档分析的统计推断

- **建议修复**: 将噪声 rng 种子与实验 seed 关联，或使用独立噪声种子：
  ```python
  # 方案 A：噪声种子 = 实验种子（噪声随 seed 变化）
  def shifted_eval(model, dataset, shift, device, noise_seed=42):
      rng = np.random.RandomState(noise_seed)
      # ...
  
  # 方案 B：噪声种子独立于实验种子，但跨 seed 不同
  # 在 evaluate_one_checkpoint 中传入 seed 作为 noise_seed
  ood_probs, ood_labels = shifted_eval(model, tgt_ds["test"], shift, device, noise_seed=seed)
  ```

---

### 攻击 4: rng=None 默认值静默保留 bug——无运行时警告

- **严重程度**: 轻微
- **位置**: `src/data/l2_shifts.py:77`、`src/data/l2_shifts.py:117-118`、`src/data/l2_shifts.py:181`
- **描述**: `apply_shift`、`shift_noise`、`_synthetic_noise` 三个函数的 rng 参数默认值为 None。当 rng=None 时，内部创建 `RandomState(42)`——这正是 P0-1 修复的 bug 行为。docstring（第 186 行）承认"会导致等长信号获得相同噪声，仅用于向后兼容"，但**不发出任何运行时警告**。调用方不传 rng 时静默获得错误结果，无任何提示。

- **反例/证据**:
  ```python
  # l2_shifts.py:76-77
  if rng is None:
      rng = np.random.RandomState(42)  # 静默创建，无 warning
  ```
  对比：Python 标准库对类似弃用行为通常发出 `DeprecationWarning` 或 `UserWarning`。此处完全静默。

- **影响**:
  - 未来新增的调用方可能忘记传 rng，静默引入 bug
  - 攻击 1、2 中的遗漏修复正是因为默认值静默保留了 bug 行为，调用方无感知
  - 代码审查时难以发现哪些调用方传了 rng、哪些没传

- **建议修复**: 当 rng=None 且 shift 类型为 noise 时，发出警告：
  ```python
  import warnings
  def apply_shift(signal, shift, rng=None):
      if rng is None and shift["type"] == "noise":
          warnings.warn(
              "apply_shift(rng=None) for noise shift: 每次调用创建 RandomState(42)，"
              "等长信号将获得相同噪声。请在循环外创建 rng 并传入。",
              UserWarning, stacklevel=2
          )
      # ...
  ```

---

### 攻击 5: 多进程/多线程安全隐患

- **严重程度**: 轻微（当前不触发，但为潜在风险）
- **位置**: `scripts/run_e1a_l2_shift_full.py:174`（共享 rng 对象）
- **描述**: `np.random.RandomState` 对象**不是线程安全的**。当前 `run_e1a_l2_shift_full.py` 的主循环是串行的（第 557 行 `for idx, (source, target, arch, seed) in enumerate(tasks, 1)`），因此共享 rng 不会并发访问。但如果未来将实验并行化（如用 `multiprocessing.Pool` 或 `joblib.Parallel` 在信号级别并行），同一 rng 对象被多个线程/进程同时调用会导致随机数序列损坏或不可预测的行为。

- **反例/证据**:
  ```python
  # 假设未来并行化 shifted_eval 内部循环
  from multiprocessing.pool import ThreadPool
  rng = np.random.RandomState(42)
  def process_signal(i):
      x, y = dataset[i]
      sig_s = apply_shift(x.numpy(), shift, rng=rng)  # 多线程同时访问 rng
      # ...
  ThreadPool(4).map(process_signal, range(n))  # rng 状态损坏
  ```

- **影响**:
  - 当前串行执行不受影响
  - 未来并行化时会产生静默错误（随机数序列损坏，结果不可复现）
  - numpy 文档未保证 RandomState 的线程安全

- **建议修复**: 在 `shifted_eval` docstring 中明确标注"非线程安全，禁止并行共享 rng"：
  ```python
  def shifted_eval(model, dataset, shift, device):
      """...
      
      注意：内部 rng 非线程安全。如需并行，每个 worker 应创建独立 rng
      （如 RandomState(42 + worker_id)），禁止共享同一 rng 对象。
      """
  ```

---

## 未发现攻击的维度（诚实记录）

### shift_noise 内部 rng 转发：正确

`shift_noise`（第 108-144 行）接收 rng 后正确转发给 `_synthetic_noise`：
- 第 126 行：`_synthetic_noise(n_samples, "bwl", fs, rng)` ✓
- 第 129 行：`_synthetic_noise(n_samples, "bwl", fs, rng)` ✓
- 第 131-132 行：`_synthetic_noise(n_samples, "ma", fs, rng)` ✓
- 第 133-134 行：`_synthetic_noise(n_samples, "em", fs, rng)` ✓
- 第 137 行：`_synthetic_noise(n_samples, noise_type, fs, rng)` ✓

所有调用均传入同一 rng，状态逐次推进，每条信号获得不同噪声。**该维度未发现可攻击点**。

### _synthetic_noise 内部 rng 使用：正确

`_synthetic_noise`（第 70-105 行）使用 rng 的所有随机调用：
- 第 82-84 行：`rng.uniform` ✓
- 第 86 行：`rng.randn` ✓
- 第 94-98 行：`rng.randint`、`rng.uniform` ✓

无其他 `RandomState` 创建或 `np.random` 全局调用。**该维度未发现可攻击点**。

### apply_shift 对非噪声类型的处理：正确

`apply_shift`（第 180-198 行）仅对 `t == "noise"` 调用 `shift_noise` 并传 rng；其他类型（downsample, leads, gain）不涉及随机性，无需 rng。**该维度未发现可攻击点**。

---

## 总结

正方 P0-1 修复在 `run_e1a_l2_shift_full.py` 内部是**局部正确**的：循环外创建 rng、传入 apply_shift、shift_noise 转发给 _synthetic_noise 的链条完整，确实解决了该脚本中"等长信号获得相同噪声"的问题。

但修复存在**三个严重缺陷**：

1. **修复不完整**：`eval_l2_shift.py` 和 `run_e4_temperature_analysis.py` 两个调用方未修复，原始 bug 仍然存活。`eval_l2_shift.py` 是 `run_e1a` 声称"复用"的原始管线，修复复制品却不修复原件，逻辑自相矛盾。`rerun_l2_noise.py` 通过 `os.system` 调用 `eval_l2_shift.py`，间接受影响。

2. **固定种子 42 引入新偏差**：所有 60 个实验（6方向×2架构×5种子）共享同一噪声实现（seed 42），跨 seed 方差仅反映模型训练变异，缺失噪声方差分量。5 个噪声档共享底层随机抽取，仅 SNR 缩放不同，不是独立噪声实现。实验声称的"跨 5 seed 统计稳定性"证据不完整。

3. **静默保留 bug 行为**：`rng=None` 默认值不发出警告，导致遗漏修复的调用方无感知地获得错误结果。这正是攻击 1、2 发生的根本原因——默认值设计鼓励了遗漏。

**总体评估**：正方修复**未完全经得起考验**。修复了 1/3 的调用方，引入了跨实验相关性新问题，且默认值设计为未来遗漏埋下隐患。建议：(1) 立即修复 eval_l2_shift.py 和 run_e4_temperature_analysis.py；(2) 将噪声种子与实验 seed 关联或使用独立噪声种子；(3) 对 rng=None 发出运行时警告。
