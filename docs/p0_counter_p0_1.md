# P0-1 反反方回应报告

## 总体判定

**5 个攻击点全部技术成立，0 个可完全反驳。** 但严重程度需重新校准：

| 攻击 | 反方定级 | 反反方核验 | 实际严重度 | 成立性 |
|------|---------|-----------|-----------|--------|
| 1. eval_l2_shift.py 遗漏修复 | 严重 | ✅ 代码确认 | **严重** | 成立 |
| 2. run_e4_temperature_analysis.py 遗漏修复 | 严重 | ✅ 代码确认 | **严重** | 成立 |
| 3. 固定 seed=42 跨实验相关性 | 严重 | ✅ 代码确认 | **中-严重**（取决于论文声明） | 部分成立 |
| 4. rng=None 静默保留 bug | 轻微 | ✅ 代码确认 | **轻微** | 成立 |
| 5. 多进程安全隐患 | 轻微 | ✅ 代码确认 | **轻微（潜在）** | 成立 |

**核心结论**：反方审查质量高，5 个攻击点均有代码实证，无臆测。攻击 1、2 是正方必须立即修复的硬伤；攻击 3 揭示了修复引入的新统计偏差，需正方明确论文声明边界或修改种子策略；攻击 4、5 是合理的防御性编程建议。反反方无法推翻任何一条攻击，但为攻击 3 提供了更精确的严重度校准和修补权衡分析。

---

## 逐条回应

### 攻击点 1: eval_l2_shift.py 遗漏修复——原始 bug 仍然存活

- **反方主张**: `eval_l2_shift.py:44` 的 `shifted_eval` 仍调用 `apply_shift(sig, shift)` 不传 rng，原始 P0-1 bug 在该脚本中仍然存活。`rerun_l2_noise.py` 通过 `os.system` 调用 `eval_l2_shift.py`，间接受影响。

- **验证结果**: **成立**

- **详细分析**:
  实际读取 `scripts/eval_l2_shift.py` 第 36-51 行确认：
  ```python
  def shifted_eval(model, dataset, shift, device, batch_size=64):
      model.eval()
      all_probs, all_labels = [], []
      n = len(dataset)
      for i in range(n):
          x, y = dataset[i]
          sig = x.numpy()
          sig_s = apply_shift(sig, shift)  # ← 第44行：确认不传 rng
  ```
  对比 `run_e1a_l2_shift_full.py:174-178` 确认正方已修复版本传入 rng。

  **连锁影响验证**：读取 `scripts/rerun_l2_noise.py` 第 63-69 行确认：
  ```python
  cmd = (
      f'python scripts/eval_l2_shift.py '
      f'--source {src} --source-dir {sd} --target {tgt} --target-dir {td} '
      ...
  )
  ret = os.system(cmd)
  ```
  确认 `rerun_l2_noise.py` 通过 `os.system` 调用 `eval_l2_shift.py`，因此其重跑结果也使用未修复的噪声管线。

  **逻辑矛盾验证**：`run_e1a_l2_shift_full.py` 第 13 行 docstring 声称"复用已验证的 eval_l2_shift.py 评估管线"，但正方在 `run_e1a` 中重新实现了 `shifted_eval`（第 163-185 行）并修复了它，却未修复被"复用"的原件。这确实是逻辑自相矛盾。

  **全局调用方扫描**：用 grep 扫描全项目 `apply_shift` 调用，确认仅 3 处调用方：
  - `eval_l2_shift.py:44` — 未传 rng（bug 存活）
  - `run_e1a_l2_shift_full.py:178` — 传 rng（已修复）
  - `run_e4_temperature_analysis.py:307` — 未传 rng（bug 存活，见攻击 2）

- **反驳或修补**: **无法反驳，攻击成立。** 建议正方立即采用反方提出的修补方案：
  ```python
  # eval_l2_shift.py shifted_eval
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
  **反反方补充建议**：修复后应删除 `run_e1a_l2_shift_full.py:163-185` 中重复实现的 `shifted_eval`，改为 `from eval_l2_shift import shifted_eval`，消除"复制品与原件不一致"的根本原因。当前正方复制了 `shifted_eval` 却只修复制品，是攻击 1 发生的架构性诱因。

---

### 攻击点 2: run_e4_temperature_analysis.py 遗漏修复——偏移敏感度分析噪声失效

- **反方主张**: `run_e4_temperature_analysis.py:307` 的 `shifted_probs_labels` 函数同样不传 rng，导致偏移敏感度分析中噪声档的 T(shift) 值基于错误数据。

- **验证结果**: **成立**

- **详细分析**:
  实际读取 `scripts/run_e4_temperature_analysis.py` 第 293-313 行确认：
  ```python
  def shifted_probs_labels(
      model: torch.nn.Module, dataset, shift: dict, device,
  ) -> tuple[np.ndarray, np.ndarray]:
      model.eval()
      all_probs, all_labels = [], []
      n = len(dataset)
      with torch.no_grad():
          for i in range(n):
              x, y = dataset[i]
              sig = x.numpy()
              sig_s = apply_shift(sig, shift)  # ← 第307行：确认不传 rng
  ```
  读取第 631-635 行确认 `process_shift_sensitivity` 调用 `shifted_probs_labels` 时也不传 rng（函数签名本身就不接受 rng 参数）。

  **额外发现（反反方补充）**：grep 扫描确认 `run_e4_temperature_analysis.py` **完全没有调用 `set_seed()`**。该脚本的 seed 参数仅传给 `build_datasets(pair, seed, limit=None)`（第 604 行）用于数据分割，既不控制模型训练（模型从 checkpoint 加载），也不控制噪声生成。这意味着：
  - E4 中噪声 rng 完全无外部种子控制，`apply_shift` 不传 rng 时每次调用创建 `RandomState(42)`
  - E4 的"可复现性"仅依赖 checkpoint 固定 + 数据分割固定，噪声部分是隐式 seed=42

  **影响范围确认**：E4 输出 `results/temperature_shift_sensitivity.csv`，其中 `shift_type == "noise"` 的 5 档（noise24/12/6/0/-6）的 `T_shift` 值基于"所有信号同一噪声"的错误数据。E4 核心主张 M3（T 随 shift 单调变化）在噪声档上的验证无效。

- **反驳或修补**: **无法反驳，攻击成立。** 建议正方立即采用反方提出的修补方案：
  ```python
  def shifted_probs_labels(
      model: torch.nn.Module, dataset, shift: dict, device,
  ) -> tuple[np.ndarray, np.ndarray]:
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

### 攻击点 3: 固定种子 42 引入跨实验噪声相关性——方差低估

- **反方主张**: `run_e1a_l2_shift_full.py:174` 硬编码 `RandomState(42)`，导致 60 个实验组合共享同一噪声实现，跨 seed 方差仅反映模型训练变异，缺失噪声方差分量。5 个噪声档共享底层随机抽取，仅 SNR 缩放不同。

- **验证结果**: **部分成立**（技术观察成立，严重度需校准）

- **详细分析**:
  读取 `run_e1a_l2_shift_full.py` 第 163-185 行确认：
  ```python
  def shifted_eval(model, dataset, shift, device):
      rng = np.random.RandomState(42)  # 硬编码 42
      for i in range(n):
          sig_s = apply_shift(sig, shift, rng=rng)
  ```
  读取第 306-322 行确认 `evaluate_one_checkpoint` 中：
  ```python
  set_seed(seed)  # seed ∈ {42,43,44,45,46}，控制模型训练和数据分割
  # ...
  for shift in shifts:
      ood_probs, ood_labels = shifted_eval(model, tgt_ds["test"], shift, device)
  ```
  确认噪声 rng（42）与实验 seed（42-46）独立。

  **反方三个子主张逐条核验**：

  1. **跨 seed 相关性**：✅ 成立。`shifted_eval` 每次被调用都创建 `RandomState(42)`，5 个实验种子的噪声实现完全相同。跨 seed 方差 = σ²_model（仅模型训练方差），缺失 σ²_noise 分量。

  2. **跨方向/架构相关性**：✅ 成立。6 方向 × 2 架构 = 12 组合的噪声实现完全相同（都是 seed 42）。

  3. **跨噪声档相关性**：✅ 成立且可精确验证。`evaluate_one_checkpoint` 对每个 shift 调用一次 `shifted_eval`，每次创建新 `RandomState(42)`。因此 noise24/12/6/0/-6 五档的 rng 初始状态完全相同，底层随机序列相同，仅 `shift_noise` 第 143 行 `noise = noise * np.sqrt(noise_power)` 的 SNR 缩放不同。**5 档是同一噪声的不同缩放，非独立实现。**

  **反反方严重度校准**：
  反方定级"严重"，反反方认为应校准为"中-严重"，理由如下：

  - **原 P0-1 bug 的修复是正确的**：原 bug 是"单次 eval pass 内所有信号获得相同噪声"，修复后单次 pass 内每条信号获得不同噪声（rng 状态逐次推进）。这确实是 P0-1 的核心问题，修复有效。

  - **跨 seed 相关性是否为"新引入偏差"需辨析**：固定噪声种子是一种合法的实验设计选择——**控制噪声变量以隔离模型训练方差**。如果论文声明"跨 5 seed 的安全率稳定性反映模型训练稳定性（噪声固定）"，则当前设计是正确的（controlled experiment）。如果论文声明"跨 5 seed 的安全率稳定性反映整体鲁棒性（含噪声变异）"，则当前设计有缺陷。**严重度取决于论文的具体声明措辞**。

  - **跨噪声档相关性反而是设计特性**：5 档使用同一噪声的不同 SNR 缩放，等价于"配对实验设计"（paired design）——同一信号在同一噪声模式下的不同强度响应。这对于研究"SNR 对 T(shift) 的剂量效应"是**更优**的设计（减少混淆变量），而非缺陷。反方将其列为攻击点略显过度。

  **但反方核心担忧成立**：如果论文用 5 seed 的安全率方差作为"实验鲁棒性"的证据，且未声明"仅反映模型训练方差"，则证据不完整。这是真实风险。

- **反驳或修补**: **部分反驳，部分接受。**
  - **反驳**：跨噪声档使用同一噪声缩放是合理的配对设计，不应视为缺陷。
  - **接受**：跨 seed 使用固定噪声种子确实限制了方差估计的完整性。
  - **修补建议**（取决于论文声明）：
    - **方案 A（若论文需声明整体鲁棒性）**：将噪声种子与实验 seed 关联，`noise_seed = seed`，使 5 seed 同时捕获模型训练和噪声方差。
      ```python
      def shifted_eval(model, dataset, shift, device, noise_seed=42):
          rng = np.random.RandomState(noise_seed)
          # ...
      # evaluate_one_checkpoint 中：
      ood_probs, ood_labels = shifted_eval(model, tgt_ds["test"], shift, device, noise_seed=seed)
      ```
    - **方案 B（若论文声明控制噪声变量）**：保持当前固定 seed=42，但在论文和代码 docstring 中**明确声明**"噪声实现固定为 seed 42，跨 seed 方差仅反映模型训练变异，不包含噪声方差分量"。
    - **反反方推荐方案 B**：改动最小，且 controlled experiment 在校准研究中是标准做法。但必须在论文中诚实声明边界。

---

### 攻击点 4: rng=None 默认值静默保留 bug——无运行时警告

- **反方主张**: `apply_shift`、`shift_noise`、`_synthetic_noise` 三个函数的 rng 默认值为 None，不传时静默创建 `RandomState(42)`，无任何警告，导致调用方无感知地获得错误结果。

- **验证结果**: **成立**

- **详细分析**:
  读取 `src/data/l2_shifts.py` 确认：
  - 第 76-77 行：`if rng is None: rng = np.random.RandomState(42)`（`_synthetic_noise`）
  - 第 117-118 行：`if rng is None: rng = np.random.RandomState(42)`（`shift_noise`）
  - 第 180-181 行：`def apply_shift(signal, shift, rng=None)`（默认 None）
  - 第 186 行 docstring 承认"会导致等长信号获得相同噪声，仅用于向后兼容"

  确认无 `warnings.warn` 调用。grep 全文件确认无 `import warnings`。

  **因果链验证**：攻击 1、2 的发生正是因为默认值静默保留了 bug 行为——`eval_l2_shift.py` 和 `run_e4_temperature_analysis.py` 的调用方不传 rng 时无任何异常或警告，静默获得错误结果。如果默认值会发出警告，正方在修复 `run_e1a` 时更容易发现其他调用方也未修复。

- **反驳或修补**: **无法反驳，攻击成立。** 建议正方采用反方提出的修补方案，在 `apply_shift` 中对 noise 类型 + rng=None 发出 `UserWarning`：
  ```python
  import warnings
  
  def apply_shift(signal, shift, rng=None):
      t = shift["type"]
      if rng is None and t == "noise":
          warnings.warn(
              "apply_shift(rng=None) for noise shift: 每次调用创建 RandomState(42)，"
              "等长信号将获得相同噪声。请在循环外创建 rng 并传入。",
              UserWarning, stacklevel=2
          )
      # ...
  ```
  **反反方补充**：警告应在 `apply_shift` 层而非 `shift_noise`/`_synthetic_noise` 层发出，因为 `apply_shift` 是公共入口，能通过 `shift["type"]` 判断是否为 noise 类型，避免对 downsample/leads/gain 等确定性变换误报。

---

### 攻击点 5: 多进程/多线程安全隐患

- **反方主张**: `np.random.RandomState` 不是线程安全的，当前串行执行不受影响，但未来并行化时共享 rng 会导致随机数序列损坏。

- **验证结果**: **成立（潜在风险）**

- **详细分析**:
  读取 `run_e1a_l2_shift_full.py` 第 557 行确认主循环为串行：
  ```python
  for idx, (source, target, arch, seed) in enumerate(tasks, 1):
  ```
  确认当前无并行化，共享 rng 不会并发访问。反方也承认"当前不触发"。

  **numpy 线程安全事实核验**：numpy 文档确实未保证 `RandomState` 的线程安全。在多线程环境下共享同一 `RandomState` 对象，其内部 C 状态可能被并发推进导致未定义行为。这是真实的技术风险。

  **反反方评估**：此攻击为防御性编程建议，非当前 bug。严重度"轻微"定级合理。但考虑到 ECG 实验室代码可能未来并行化加速（390 单元格评估耗时较长），提前标注是有价值的。

- **反驳或修补**: **无法反驳，攻击成立但低优先级。** 建议正方采用反方提出的 docstring 标注方案：
  ```python
  def shifted_eval(model, dataset, shift, device):
      """...
      
      注意：内部 rng 非线程安全。如需并行，每个 worker 应创建独立 rng
      （如 RandomState(42 + worker_id)），禁止共享同一 rng 对象。
      """
  ```
  **反反方补充**：更彻底的方案是在 `apply_shift` 中对 rng 加 `threading.Lock` 保护，但这会引入性能开销且过度工程化。docstring 警告 + 代码审查规范是更合理的平衡点。

---

## 反反方独立补充发现

### 补充发现 A: run_e1a_l2_shift_full.py 存在 shifted_eval 代码重复

正方在 `run_e1a_l2_shift_full.py:163-185` 重新实现了 `shifted_eval`，而非从 `eval_l2_shift.py` 导入。这是攻击 1 发生的架构性根因——两份代码副本容易只修一份。建议修复后改为 `from eval_l2_shift import shifted_eval`，单一真相源（single source of truth）。

### 补充发现 B: run_e4_temperature_analysis.py 完全不调用 set_seed

grep 确认 `run_e4_temperature_analysis.py` 中无 `set_seed()` 调用。该脚本的 seed 参数仅用于数据分割（`build_datasets(pair, seed)`），不控制模型训练（从 checkpoint 加载）也不控制噪声。这意味着 E4 的全局可复现性仅依赖 checkpoint + 数据分割的确定性，噪声部分是隐式 `RandomState(42)`。这是攻击 2 的深层原因——E4 从未将 rng 纳束纳入实验种子管理。

---

## 结论

### 需要回炉重修的攻击（正方必须修复）

1. **攻击 1（严重）**：立即修复 `eval_l2_shift.py:shifted_eval`，添加循环外 rng 创建。同时建议消除 `run_e1a` 中的代码重复，改为导入。

2. **攻击 2（严重）**：立即修复 `run_e4_temperature_analysis.py:shifted_probs_labels`，添加循环外 rng 创建。

3. **攻击 4（轻微但高杠杆）**：在 `apply_shift` 中对 `rng=None + noise shift` 发出 `UserWarning`。这是防御性修复，能防止未来再次遗漏，成本低收益高。

### 可有条件接受的攻击（需论文声明配合）

4. **攻击 3（中-严重）**：技术观察成立，但严重度取决于论文声明。
   - 若论文声明"跨 seed 稳定性 = 模型训练稳定性（噪声固定）"→ 当前设计可接受，但需在论文和代码中明确声明边界。
   - 若论文声明"跨 seed 稳定性 = 整体鲁棒性"→ 需修改为 `noise_seed = seed`。
   - 反反方推荐方案 B（保持固定 seed + 明确声明边界），因为 controlled experiment 是校准研究的标准做法。
   - 反方关于"跨噪声档相关性"的子主张略显过度——同一噪声的不同 SNR 缩放是合理的配对设计。

### 低优先级建议

5. **攻击 5（轻微潜在）**：在 `shifted_eval` docstring 中标注非线程安全。当前串行执行无风险，但为未来并行化预留文档警示。

### 总体评价

反方审查质量**高**，5 个攻击点均有代码实证，无臆测，逻辑链条清晰。攻击 1、2 是正方修复不完整的硬伤，必须立即修复。攻击 3 揭示了修复引入的统计偏差，是本次审查最有价值的发现，但严重度需结合论文声明校准。攻击 4、5 是合理的防御性编程建议。

正方 P0-1 修复**局部正确但全局不完整**：修复了 1/3 的调用方（`run_e1a`），遗漏 2/3（`eval_l2_shift.py`、`run_e4_temperature_analysis.py`），且固定 seed=42 引入新的跨实验相关性问题。建议正方按上述优先级回炉重修。
