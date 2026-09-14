# 反方攻击报告：E1a L2移位矩阵补齐实验

> **反方挑刺代理-R1交付**。本报告对 `scripts/run_e1a_l2_shift_full.py`（E1a实验脚本）进行7维度全方位攻击审查。
> **审查范围**：run_e1a_l2_shift_full.py (627行) + eval_l2_shift.py (182行) + calibration.py + l2_shifts.py + Q2_UPGRADE_PROPOSAL_R5.md
> **审查日期**：2026-09-09
> **审查方法**：逐行代码审查 + 7维度攻击（反例构造/逻辑断链/隐含假设/边界失效/自相矛盾/量级错误/语义偏移）

---

## 攻击摘要

| 严重程度 | 数量 | 攻击编号 |
|---------|------|---------|
| **致命(F)** | 2 | F1, F2 |
| **严重(S)** | 7 | S1-S7 |
| **轻微(M)** | 4 | M1-M4 |
| **合计** | 13 | - |

**总体判断**：实验脚本存在1个致命的噪声注入统计错误（F1），会导致噪声档5/13格的实验结果不可信。另有1个致命的变长输入未处理问题（F2），可能导致降采样档2/13格崩溃。建议P0级修改后再执行。

---

## 致命攻击(F)

### F1: 噪声注入rng=RandomState(42)每条信号重建，导致所有等长信号注入完全相同的噪声序列

- **攻击点**：`l2_shifts.py` 的 `shift_noise` 函数默认 `rng=None`，当不传rng时每次调用都新建 `np.random.RandomState(42)`。`run_e1a_l2_shift_full.py` 的 `shifted_eval` → `apply_shift` → `shift_noise` 调用链中**不传rng**，导致每条信号都用同一个种子42生成噪声。

- **反例/证据**：
  ```python
  # l2_shifts.py
  def shift_noise(signal, noise_type, snr_db, fs=500, rng=None):
      if rng is None:
          rng = np.random.RandomState(42)  # 每次调用都新建！

  # run_e1a_l2_shift_full.py shifted_eval
  for i in range(n):
      x, y = dataset[i]
      sig = x.numpy()
      sig_s = apply_shift(sig, shift)  # shift是固定dict，不传rng
  ```
  对于同一数据集的等长信号（如ptbxl test集所有信号长度相同），信号1和信号2注入的噪声**完全相同**（因为RandomState(42)生成的随机序列相同，长度相同）。

  具体反例：假设test集有1000条信号，长度均为4096。对noise24档，所有1000条信号叠加的噪声序列完全相同。这不是"噪声注入"，而是"确定性扰动"。

- **影响**：
  1. **噪声的统计特性完全错误**：所有信号的噪声完全相关（相关系数=1），而真实噪声应该是独立的（相关系数≈0）
  2. **ECE/Brier reliability评估的方差严重低估**：因为噪声不是真正随机的，评估结果不反映真实的噪声影响
  3. **safety率可能系统性偏倚**：确定性扰动下，TS的校准效果可能与真实随机噪声下不同（方向不可预知）
  4. **影响范围**：13档中5档是噪声档（noise24/12/6/0/-6），占5/13=38.5%的单元格受影响
  5. **结论外推失效**：基于确定性扰动的结论不能外推到真实噪声场景

- **建议修补**（P0，必须修改后才能执行）：
  ```python
  # 修改 shifted_eval 函数
  def shifted_eval(model, dataset, shift, device):
      import numpy as np
      rng = np.random.RandomState(42)  # 在函数开始创建一次
      for i in range(n):
          x, y = dataset[i]
          sig = x.numpy()
          sig_s = apply_shift(sig, shift, rng=rng)  # 传入共享rng
  ```
  并修改 `apply_shift` 和 `shift_noise` 接受并使用传入的rng。这样整体可复现（种子42），但每条信号噪声不同。

---

### F2: 降采样后信号长度变化，模型可能不支持变长输入，脚本未处理

- **攻击点**：`shift_downsample` 将信号从500Hz降到250Hz/125Hz，长度减半/减为1/4。`shifted_eval` 将变长信号直接送入模型，但模型（ResNet1D/InceptionTime）通常期望固定长度输入。脚本没有任何变长输入处理逻辑。

- **反例/证据**：
  ```python
  # l2_shifts.py
  def shift_downsample(signal, target_hz, orig_hz=500):
      # 返回长度 = L * target_hz / orig_hz
      # 500Hz×4096 → 250Hz×2048 → 125Hz×1024

  # run_e1a_l2_shift_full.py shifted_eval
  x_s = torch.from_numpy(sig_s).unsqueeze(0).to(device)
  with torch.no_grad():
      _, probs = model(x_s)  # 变长输入直接送入模型
  ```
  如果模型包含全连接层（无adaptive pooling），2048或1024长度的输入会导致维度不匹配错误。即使有adaptive pooling，降采样后的信号在频域上的信息也与原始信号不同，模型可能产生异常输出。

- **影响**：
  1. 降采样档（downsample_fs250, downsample_fs125）共2/13=15.4%的单元格可能崩溃
  2. 如果模型静默接受变长输入但产生异常输出（如全零概率），safety计算会产生误导性结果
  3. 如果模型抛异常，被try-except捕获后cell记录error，safety=0，但这是"模型不支持"而非"TS不安全"，语义混淆

- **建议修补**（P0）：
  1. 在shifted_eval中检查 `sig_s.shape[-1] == sig.shape[-1]`，对变长信号做resize/pad到原始长度
  2. 或在shift_downsample后加resample回原始长度（降采样再升采样，模拟低频信息丢失）
  3. 明确声明降采样档的处理方式（是变长输入还是resample回原长）

---

## 严重攻击(S)

### S1: 10等宽箱Brier reliability对高自信度模型不敏感，可能系统性低估safety率

- **攻击点**：`brier_parts` 用10等宽箱（0-0.1, ..., 0.9-1.0）计算Murphy分解的reliability分量。对于训练良好的ECG分类模型，maxprob通常集中在0.9-1.0区间，绝大部分样本落入最后一个bin。此时reliability ≈ (avg_prob_last_bin - avg_label_last_bin)²，只有一个bin的估计，对TS的效果不敏感。

- **反例/证据**：
  ```python
  # calibration.py brier_parts
  bins = np.linspace(0, 1, 11)  # 10等宽箱
  for i in range(10):
      mask = (mp >= bins[i]) & (mp < bins[i+1])
      # 如果95%样本maxprob > 0.9，只有最后一个bin有大量样本
  ```
  具体反例：假设raw maxprob = [0.95, 0.95, 0.95, ...]，TS后 maxprob = [0.88, 0.88, 0.88, ...]。
  - raw: 所有样本在bin[9]（0.9-1.0），reliability = (0.95 - 0.9)² = 0.0025
  - TS: 所有样本在bin[8]（0.8-0.9），reliability = (0.88 - 0.9)² = 0.0004
  - safety = 1（0.0004 < 0.0025）✓

  但如果TS后 maxprob = [0.91, 0.91, 0.91, ...]（仍在bin[9]）：
  - TS reliability = (0.91 - 0.9)² = 0.0001
  - safety = 1（0.0001 < 0.0025）✓

  问题场景：如果raw和TS的maxprob都在同一bin内，且bin内样本的avg_label相同，则reliability差异仅来自avg_prob的变化。但如果bin内avg_label随avg_prob变化（非线性），reliability可能不变甚至增加，导致safety=0，即使TS确实改善了校准。

- **影响**：
  1. safety率可能被低估（TS确实改善校准但因分箱不敏感而safety=0）
  2. 影响所有13档的safety计算（不仅噪声档）
  3. 脚本P3已披露"分箱偏差"，但未量化影响程度

- **建议修补**（P1）：
  1. 改用等频箱（quantile binning）替代等宽箱，确保每个bin有足够样本
  2. 或增加bin数量（如15或20），提高分辨率
  3. 报告分箱敏感性分析（10/15/20 bin的safety率对比）

---

### S2: 校准参数每个shift重复拟合，cal_probs与shift无关导致13倍计算浪费

- **攻击点**：`evaluate_one_checkpoint` 中，`cal_probs` 和 `cal_labels` 在shift循环外计算（source cal split的预测，不随shift变化）。但在shift循环内，对每个shift都重新调用 `fit_fn(cal_probs, cal_labels)` 拟合校准参数。由于输入相同，拟合结果相同，这是13倍的计算浪费。

- **反例/证据**：
  ```python
  # run_e1a_l2_shift_full.py 第320-350行
  cal_ev = evaluate(model, cal_loader, ...)  # shift循环外
  cal_probs, cal_labels = cal_ev["probs"], cal_ev["labels"]

  for shift in shifts:  # 13档
      for mname in METHODS:  # 8方法
          if mname in CALIBRATION_METHODS:
              params = fit_fn(cal_probs, cal_labels)  # 每次都重新拟合！
  ```
  对于ts/platt/isotonic/vector/matrix/dirichlet这6种方法，校准参数与shift无关，应该只拟合一次。只有em_prior/bbse_prior需要ood_probs（随shift变化）而重新拟合。

- **影响**：
  1. 运行时间增加约6/8×13 ≈ 10倍（6种方法×13档 vs 6种方法×1次）
  2. 对于390单元格实验，总运行时间可能从~1小时增加到~10小时
  3. 不是正确性问题（结果相同），但影响实验可行性

- **建议修补**（P1）：
  ```python
  # 在shift循环外预拟合与shift无关的校准参数
  cached_params = {}
  for mname in ["ts", "platt", "isotonic", "vector", "matrix", "dirichlet"]:
      fit_fn, _, _ = CALIBRATION_METHODS[mname]
      cached_params[mname] = fit_fn(cal_probs, cal_labels)

  for shift in shifts:
      for mname in METHODS:
          if mname in cached_params:
              params = cached_params[mname]  # 复用
  ```

---

### S3: safety_rate >= 0.5阈值选择未声明理由，影响总体安全率统计

- **攻击点**：`aggregate_to_390` 中，`n_safe = sum(1 for r in rows_390 if r["safety_rate"] >= 0.5)`。对于2架构聚合，safety_rate ∈ {0, 0.5, 1.0}。>= 0.5意味着"至少一架构安全"就算安全格。但脚本未声明为什么用0.5而非1.0（两架构都安全）。

- **反例/证据**：
  ```python
  # run_e1a_l2_shift_full.py 第470行
  n_safe = sum(1 for r in rows_390 if r["safety_rate"] >= 0.5)
  ```
  具体反例：某格resnet1d safety=0, inceptiontime safety=1，safety_rate=0.5。
  - 阈值0.5：算安全格（n_safe+1）
  - 阈值1.0：算不安全格
  - 两种阈值的总体安全率可能差异显著（如从60%降到30%）

- **影响**：
  1. 总体安全率统计依赖未声明的阈值选择
  2. 论文claim"安全率X%"的解读依赖此阈值
  3. 审稿人可能质疑阈值选择的任意性

- **建议修补**（P1）：
  1. 同时报告多个阈值的safe格数（>= 0.5, >= 1.0, == 1.0）
  2. 声明阈值选择理由（如"至少一架构安全即有参考价值"）
  3. 或改用连续指标（如平均safety_rate）而非二值阈值

---

### S4: 390矩阵safety_rate无置信区间，2架构均值的CI极宽

- **攻击点**：safety_rate是2个二值量的均值，点估计为{0, 0.5, 1.0}。脚本只报告点估计，不报告置信区间。对于n=2的均值，Wilson 95% CI极宽：safety_rate=0.5的CI ≈ [0.06, 0.94]，几乎无法区分"真安全率0.1"和"真安全率0.9"。

- **反例/证据**：
  ```python
  # run_e1a_l2_shift_full.py
  safety_rate = sum(safety_values) / len(safety_values)  # 2架构均值
  # 无CI计算
  ```
  具体反例：390格中180格safety_rate=0.5，报告"安全率46%"（180/390）。但每格的CI是[0.06, 0.94]，总体安全率的CI也很宽，不能得出"TS在46%的情况下安全"的可靠结论。

- **影响**：
  1. 论文claim"安全率X%"缺乏统计严谨性
  2. 审稿人可能要求CI或更多架构以缩小CI
  3. 与R5方案§3.2 E3的"多指标报告+CI"要求不一致

- **建议修补**（P1）：
  1. 对每格报告Wilson CI（基于n_archs=2）
  2. 对总体安全率报告bootstrap CI
  3. 诚实声明n_archs=2的统计效力局限

---

### S5: leads6命名与实际8通道不符，论文claim语义偏移

- **攻击点**：`l2_shifts.py` 中 `LEAD_SUBSETS[6] = [0, 1, 6, 7, 8, 9, 10, 11]`，对应I, II, V1, V2, V3, V4, V5, V6共**8个通道**，而非6个。docstring已解释"6导联监护配置实际保留8通道（移除4个线性可导出导联）"，但shift名仍为"leads6"。

- **反例/证据**：
  ```python
  # l2_shifts.py
  LEAD_SUBSETS = {
      6: [0, 1, 6, 7, 8, 9, 10, 11],  # I, II, V1-V6 = 8通道
  }
  # shift名: "leads6"
  ```
  如果论文claim"TS在6导联监护配置下安全率X%"，而实际测试的是8通道（信息无损，因为移除的4个导联可由保留的8个线性导出），则claim的语义偏移：
  - "6导联鲁棒性"（论文claim）≠ "8导联信息无损降档鲁棒性"（实际测试）
  - 8导联信息无损比6导联信息有损更容易，安全率可能偏高

- **影响**：
  1. 论文claim与实验测试的语义不一致
  2. 审稿人可能质疑"6导联"的准确性
  3. 安全率可能因信息无损而偏高

- **建议修补**（P1）：
  1. 将shift名改为"leads8_monitor"或"leads6_config_8ch"以准确反映实际通道数
  2. 论文中明确声明"6导联监护配置实际保留8通道，移除4个线性可导出导联"
  3. 或增加真正的6通道测试（如只保留I, II, V1, V2, V3, V4）

---

### S6: 断点续传不验证数据一致性，可能使用错误数据

- **攻击点**：`is_checkpoint_complete` 只检查字段存在性（`"cal_ece" in cell`），不验证值的合理性。如果之前的运行被中断导致部分shift的cal_ece是错误的（如模型加载不完整、OOM导致部分样本未评估），断点续传会跳过重跑，使用错误数据。

- **反例/证据**：
  ```python
  # run_e1a_l2_shift_full.py
  def is_checkpoint_complete(run_dir, seed):
      # 只检查字段存在性
      if "cal_ece" not in cell:
          return False
      if "safety" not in cell:
          return False
      # 不检查值合理性（如cal_ece是否在[0,1]范围）
  ```
  具体反例：某次运行中模型加载失败（state_dict不匹配），但evaluate返回了全零probs。cal_ece=1.0（最大不校准），safety=0。这些值被写入json。下次运行时is_checkpoint_complete返回True，跳过重跑，使用错误的cal_ece=1.0和safety=0。

- **影响**：
  1. 错误数据可能进入390矩阵，影响总体安全率
  2. 已有24个json缺少safety字段会触发重跑（正确），但重跑后如果再次中断，可能留下部分错误数据
  3. 难以检测（需要人工检查每个json的值合理性）

- **建议修补**（P2）：
  1. 在is_checkpoint_complete中增加值合理性检查（0 <= cal_ece <= 1, 0 <= brier_rel <= 1, safety in {0,1}）
  2. 增加checksum/hash验证（如记录模型state_dict的hash，重跑时验证）
  3. 增加--validate模式，检查已有json的数据一致性

---

### S7: mamba仅1方向2seed排除，虽已声明但可能引入选择偏差

- **攻击点**：mamba因OOM仅在ptbxl_chapman方向有seed42,43的数据，不进主390矩阵。脚本P1已披露此限制。但问题：mamba在ptbxl_chapman方向的表现可能与resnet1d/inceptiontime差异显著，排除它会让该方向的安全率只反映2架构而非3架构。

- **反例/证据**：
  ```python
  # run_e1a_l2_shift_full.py
  ARCHS = ["resnet1d", "inceptiontime"]  # mamba不在此列表
  # mamba数据在aggregate_to_390中被跳过
  ```
  具体反例：假设ptbxl_chapman方向mamba safety=0（TS不安全），resnet1d safety=1, inceptiontime safety=1。
  - 排除mamba：safety_rate = 1.0（2架构都安全）
  - 包含mamba：safety_rate = 0.67（2/3安全）
  - 排除mamba使该方向安全率偏高

- **影响**：
  1. ptbxl_chapman方向的安全率可能偏高（如果mamba表现差）
  2. 跨方向稳定性分析受影响（1/6方向可能有偏）
  3. 已声明但未量化影响程度

- **建议修补**（P2）：
  1. 报告mamba在ptbxl_chapman方向的safety（作为sensitivity analysis）
  2. 诚实声明"mamba排除可能使ptbxl_chapman方向安全率偏高"
  3. 或在780详细CSV中保留mamba数据，供审稿人检查

---

## 轻微攻击(M)

### M1: aggregate_to_390排序混合int(seed)和str(shift_name)，CSV行顺序不直观

- **攻击点**：`sorted(agg.items())` 对 `(source, target, seed, sn)` 排序，seed是int，sn是str。混合类型排序在Python 3中会抛TypeError，但这里source/target/sn都是str，seed是int，tuple排序先比source（str），再比target（str），再比seed（int），再比sn（str）。不会抛异常，但shift_name的字符串排序可能不直观（如"noise-6" < "noise12"因'-'< '1'）。

- **影响**：CSV行顺序不直观，但不影响数据正确性。

- **建议修补**（P2）：将seed转为str排序，或用显式sort key。

---

### M2: shifted_eval batch_size=1逐条处理，性能低

- **攻击点**：`shifted_eval` 逐条处理信号（`for i in range(n)`），batch_size=1。对于390单元格×每格几百条信号，这会非常慢。

- **影响**：运行时间长，但不影响正确性。

- **建议修补**（P2）：对非变长shift（如noise/gain）做batch处理，对变长shift（如downsample）逐条处理。

---

### M3: 13档缺少导联置换、per-channel增益、时移等移位类型

- **攻击点**：13档 = 降采样2 + 导联4 + 噪声5 + 增益2。缺少：
  - 导联置换（lead permutation）：模拟导联连接错误
  - per-channel增益（per-channel gain）：模拟各导联增益不一致
  - 时移（time shift）：模拟R波对齐偏差
  - 基线漂移作为独立档（当前混在noise mixed中）

- **影响**：L2移位覆盖不全面，但13档已覆盖主要类型。

- **建议修补**（P2）：在论文limitation中声明未覆盖的移位类型，或未来工作补充。

---

### M4: 780详细CSV缺少raw_brier_raw字段，信息不完整

- **攻击点**：`aggregate_to_390` 中 `rows_780` 的fieldnames没有 `raw_brier_raw`，但cell中有这个字段。780 CSV不包含raw Brier score的原始值，只包含brier_reliability分量。

- **影响**：无法从780 CSV验证Brier分解的正确性（brier_total = rel - res + unc）。

- **建议修补**（P2）：在780 CSV中增加raw_brier_raw字段。

---

## 7维度攻击记录

### 维度1：反例构造
- **F1**：构造等长信号反例，证明所有信号注入相同噪声
- **F2**：构造降采样反例，证明变长输入可能导致模型崩溃
- **S1**：构造高自信度模型反例，证明等宽箱对TS效果不敏感
- **S3**：构造safety_rate=0.5反例，证明阈值选择影响安全率统计

### 维度2：逻辑断链
- **S2**：cal_probs与shift无关但每个shift重新拟合，逻辑冗余（非错误但效率断链）
- **S6**：断点续传检查字段存在→认为数据完整，缺少"字段存在→数据正确"的中间步骤

### 维度3：隐含假设
- **F1**：隐含假设"固定种子42保证可复现"，但实际导致所有信号噪声相同
- **F2**：隐含假设"模型支持变长输入"，但未验证
- **S5**：隐含假设"leads6指6通道"，但实际是8通道
- **S7**：隐含假设"排除mamba不影响结论"，但未验证

### 维度4：边界失效
- **F1**：噪声注入在"等长信号"边界情况下退化为确定性扰动
- **F2**：降采样在"模型不支持变长输入"边界情况下崩溃
- **S1**：等宽箱在"所有maxprob > 0.9"边界情况下退化为单bin估计
- **S4**：safety_rate在"n_archs=2"边界情况下CI极宽

### 维度5：自相矛盾
- **S5**：leads6命名与8通道实际矛盾
- **S3**：safety_rate >= 0.5阈值与"严格安全"语义矛盾（0.5意味着一架构不安全）

### 维度6：量级错误
- **S2**：校准参数重复拟合导致13倍计算浪费（量级估计错误）
- **S4**：n_archs=2的CI宽度[0.06, 0.94]与点估计0.5的量级不匹配

### 维度7：语义偏移
- **S5**："6导联鲁棒性"（论文claim）→ "8导联信息无损降档鲁棒性"（实际测试）
- **F1**："噪声注入"（预期语义）→ "确定性扰动"（实际实现）
- **S3**："安全格"（预期语义：TS安全）→ "至少一架构安全"（实际语义：阈值0.5）

---

## 总体评估

### 实验设计可信度
- **低**。存在2个致命攻击（F1噪声注入统计错误 + F2变长输入未处理），会导致38.5%+15.4%=53.9%的单元格结果不可信或崩溃。

### 需要修改后才能执行
- **是**。F1和F2必须P0级修改后才能执行，否则噪声档和降采样档的结果不可信。

### 关键修改优先级
- **P0**（必须修改后才能执行）：
  1. F1：修复噪声注入rng，在shifted_eval开始创建一次rng传给每条信号
  2. F2：处理降采样变长输入（resize/pad/resample回原长）

- **P1**（强烈建议修改）：
  3. S1：改用等频箱或增加bin数量，报告分箱敏感性分析
  4. S2：缓存与shift无关的校准参数，减少10倍计算浪费
  5. S3：报告多个阈值的safe格数，声明阈值选择理由
  6. S4：报告safety_rate的CI，诚实声明n_archs=2的统计效力局限
  7. S5：修正leads6命名或增加真正的6通道测试

- **P2**（建议修改）：
  8. S6：增加断点续传数据一致性检查
  9. S7：报告mamba sensitivity analysis
  10. M1-M4：代码质量改进

### 攻击代理声明
我尝试了全部7个攻击维度（反例构造/逻辑断链/隐含假设/边界失效/自相矛盾/量级错误/语义偏移），找到13个攻击点（2致命+7严重+4轻微）。**实验脚本不能在当前状态下执行**，F1和F2的致命问题会导致超过一半的实验结果不可信。建议P0级修改后再执行。

---

## 附录：审查文件清单

| 文件 | 行数 | 审查状态 |
|------|------|---------|
| `scripts/run_e1a_l2_shift_full.py` | 627 | 逐行审查完成 |
| `scripts/eval_l2_shift.py` | 182 | 逐行审查完成 |
| `src/utils/calibration.py` | - | 重点函数审查（brier_parts, smooth_ece） |
| `src/data/l2_shifts.py` | - | 重点函数审查（shift_noise, apply_shift, get_l2_shifts） |
| `docs/Q2_UPGRADE_PROPOSAL_R5.md` | 1313 | E1a定位审查完成 |
| `src/data/mapping.py` | - | SUBSPACE_CPSC定义审查 |

**报告结束。**
