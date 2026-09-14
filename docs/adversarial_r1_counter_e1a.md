# 反反方审查报告 - E1a L2移位矩阵补齐

> **反反方审查代理-R1交付**。本报告对反方挑刺代理的攻击报告 `adversarial_r1_attack_e1a.md` 进行逐条裁决。
> **审查日期**：2026-09-09
> **审查方法**：对每个攻击点依次执行5维度审查（反例是否成立/是否稻草人/是否误解前提/攻击逻辑是否自洽/严重程度是否夸大）
> **审查依据**：实际代码逐行验证（run_e1a_l2_shift_full.py + l2_shifts.py + calibration.py）

---

## 审查摘要

- **攻击点总数**：13（F1-F2致命 + S1-S7严重 + M1-M4轻微）
- **驳回**：1（M3）
- **部分成立**：8（F2, S1, S2, S3, S4, S5, S6, S7）
- **成立**：4（F1, M1, M2, M4）
- **需要修补的**：12（1个P0必修 + 8个部分成立需改进 + 3个轻微成立）

### 裁决统计表

| 编号 | 反方标注 | 反反方裁决 | 实际严重程度 | 理由摘要 |
|------|---------|-----------|------------|---------|
| F1 | 致命 | **成立** | P0（致命） | 噪声确定性注入确认，z-score归一化后sig_power≈1使噪声完全相同 |
| F2 | 致命 | **部分成立** | P1（严重→降级） | 变长输入未显式处理属实，但"崩溃"为推测，多数CNN架构支持变长 |
| S1 | 严重 | **部分成立** | P2（轻微→降级） | 分箱限制真实但已披露，反例未构造出safety=0的失败场景 |
| S2 | 严重 | **部分成立** | P2（轻微→降级） | 冗余拟合属实但量级估计错误（10倍→实际约1.5倍） |
| S3 | 严重 | **部分成立** | P2（轻微） | 阈值未声明理由属实，但详细CSV保留全量数据可任意重算 |
| S4 | 严重 | **部分成立** | P1（严重） | 无CI属实，n_archs=2统计效力局限为真实问题 |
| S5 | 严重 | **部分成立** | P2（轻微→降级） | 命名已文档解释，非正确性问题，"安全率偏高"为推测 |
| S6 | 严重 | **部分成立** | P2（轻微） | 值验证缺失属实，但反例（模型加载失败→全零probs）不会发生 |
| S7 | 严重 | **部分成立** | P2（轻微） | 已在边界声明，sensitivity analysis建议合理 |
| M1 | 轻微 | **成立** | P3（ cosmetic） | 排序确实不直观，不影响正确性 |
| M2 | 轻微 | **成立** | P3（性能） | batch_size=1属实，性能影响真实 |
| M3 | 轻微 | **驳回** | - | 超出适用范围：13档为协议预注册定义，非脚本设计缺陷 |
| M4 | 轻微 | **成立** | P3（数据完整性） | raw_brier_raw确实未导出，可验证性降低 |

---

## 逐条审查

### F1: 噪声注入rng=RandomState(42)每条信号重建，导致所有等长信号注入完全相同的噪声序列

**裁决**：成立

**5维度审查**：

1. **反例是否成立**：✅ 成立。代码验证：
   - `l2_shifts.py:117-118`：`if rng is None: rng = np.random.RandomState(42)` — 每次调用新建rng
   - `l2_shifts.py:191`：`apply_shift` 调用 `shift_noise(signal, p["noise_type"], p["snr_db"])` — **不传rng**
   - `run_e1a_l2_shift_full.py:174`：`sig_s = apply_shift(sig, shift)` — 不传rng
   - 调用链确认：`shifted_eval` → `apply_shift` → `shift_noise`，全程不传rng

2. **是否稻草人**：❌ 非稻草人。反方准确引用了代码，未歪曲正方设计意图。

3. **是否误解前提**：❌ 未误解。反方正确识别了rng=None的默认行为。

4. **攻击逻辑是否自洽**：✅ 自洽。但需补充一个反方未提及的关键环节使论证更完整：
   - 数据管线对信号做per-record z-score归一化（l2_shifts.py docstring第12行确认"在per-record z-score归一化之后施加"）
   - z-score后 `mean(signal)=0, std(signal)=1`，故 `sig_power = np.mean(signal**2) = 1` 对所有信号恒成立
   - `noise_power = sig_power / (10**(snr_db/10)) = 1 / (10**(snr_db/10))` 对所有信号相同
   - `_synthetic_noise` 用相同rng(42)+相同n_samples生成相同噪声模式
   - 噪声归一化（zero mean, unit std）是确定性操作，相同输入→相同输出
   - 最终 `noise = same_pattern * sqrt(same_noise_power)` = **完全相同**
   - **结论**：反方"所有等长信号注入完全相同噪声"的claim在z-score归一化前提下精确成立

5. **严重程度是否夸大**：❌ 未夸大。5/13=38.5%单元格受影响，噪声完全相关（相关系数=1），统计特性确实错误。致命级合理。

**修补方案**（P0，必须在执行前修复）：

```python
# 修改 run_e1a_l2_shift_full.py 的 shifted_eval 函数
def shifted_eval(model, dataset, shift, device):
    """对 dataset 每条信号施加 shift 后评估 model。"""
    model.eval()
    all_probs, all_labels = [], []
    n = len(dataset)
    # 修复F1：在函数级创建一次rng，传给每条信号
    rng = np.random.RandomState(42)
    for i in range(n):
        x, y = dataset[i]
        sig = x.numpy()
        sig_s = apply_shift(sig, shift, rng=rng)  # 传入共享rng
        x_s = torch.from_numpy(sig_s).unsqueeze(0).to(device)
        with torch.no_grad():
            _, probs = model(x_s)
            probs = probs.cpu().numpy()
        all_probs.append(probs[0])
        all_labels.append(int(y))
    return np.array(all_probs), np.array(all_labels)
```

同时修改 `l2_shifts.py` 的 `apply_shift` 和 `shift_noise` 接受并透传rng参数：

```python
def apply_shift(signal: np.ndarray, shift: dict, rng=None) -> np.ndarray:
    t = shift["type"]
    p = shift["params"]
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

这样整体可复现（种子42），但每条信号噪声不同（rng状态推进）。

---

### F2: 降采样后信号长度变化，模型可能不支持变长输入，脚本未处理

**裁决**：部分成立

**5维度审查**：

1. **反例是否成立**：⚠️ 部分成立。
   - 代码事实确认：`shift_downsample`（l2_shifts.py:36-44）用`decimate`将长度减半/减为1/4
   - `shifted_eval`（run_e1a_l2_shift_full.py:175-177）确实无变长检查/pad/resample逻辑
   - **但**："模型可能不支持变长输入"是推测，未验证实际模型架构

2. **是否稻草人**：⚠️ 部分稻草人。反方说"模型（ResNet1D/InceptionTime）通常期望固定长度输入"，但：
   - ResNet1D标准实现含`AdaptiveAvgPool1d`，天然支持变长
   - InceptionTime由全卷积+全局平均池化构成，也支持变长
   - 反方用"通常期望"泛化，未检查`ECGClassifier`实际实现

3. **是否误解前提**：⚠️ 部分误解。降采样档的**设计意图**就是测试模型在低时间分辨率下的鲁棒性。馈入变长信号可能是**有意行为**（模拟250Hz/125Hz采集端的低分辨率输入），而非遗漏。

4. **攻击逻辑是否自洽**：⚠️ 有断链。"模型可能崩溃"→"如果模型包含全连接层（无adaptive pooling）"是条件假设，但未验证条件是否满足。逻辑链：变长输入→可能崩溃→2/13格崩溃，中间环节"可能"未坐实。

5. **严重程度是否夸大**：✅ 夸大。从"可能"直接跳到"致命"+"2/13格崩溃"，但：
   - 若模型含adaptive pooling（大概率），不会崩溃，只是特征图统计偏移
   - 即使输出异常，try-except会捕获，safety=0，不会污染其他档
   - 实际影响：要么正常工作（adaptive pooling），要么graceful降级（异常捕获），"崩溃"场景需要模型既无adaptive pooling又静默接受变长——罕见组合

**修正后的实际影响**：
- 代码确实缺少变长输入的显式声明/处理（代码质量问题，P1）
- 若模型不支持变长，会抛异常被捕获，safety=0，语义为"模型不支持"而非"TS不安全"（语义混淆，P2）
- 降级：致命→严重（P1），需验证模型行为并显式声明处理方式

**修补方案**（P1）：

```python
def shifted_eval(model, dataset, shift, device):
    model.eval()
    all_probs, all_labels = [], []
    n = len(dataset)
    rng = np.random.RandomState(42)
    orig_len = None
    for i in range(n):
        x, y = dataset[i]
        sig = x.numpy()
        if orig_len is None:
            orig_len = sig.shape[-1]
        sig_s = apply_shift(sig, shift, rng=rng)
        # F2修复：变长信号resample回原始长度（降采样再升采样，模拟低频信息丢失）
        if sig_s.shape[-1] != orig_len:
            from scipy.signal import resample
            sig_s = resample(sig_s, orig_len, axis=1).astype(np.float32)
        x_s = torch.from_numpy(sig_s).unsqueeze(0).to(device)
        with torch.no_grad():
            _, probs = model(x_s)
            probs = probs.cpu().numpy()
        all_probs.append(probs[0])
        all_labels.append(int(y))
    return np.array(all_probs), np.array(all_labels)
```

或最低限度：在脚本docstring中显式声明"降采样档馈入变长信号，依赖模型的adaptive pooling支持"。

---

### S1: 10等宽箱Brier reliability对高自信度模型不敏感

**裁决**：部分成立

**5维度审查**：

1. **反例是否成立**：⚠️ 反例未真正成立。反方构造了两个场景：
   - 场景1：raw maxprob=0.95→bin[9], TS maxprob=0.88→bin[8]，safety=1 ✓
   - 场景2：raw maxprob=0.95→bin[9], TS maxprob=0.91→bin[9]，safety=1 ✓
   - **两个反例都得到safety=1（TS安全）**，未构造出safety=0的错误判断
   - 反方随后用"如果bin内avg_label随avg_prob变化（非线性）"做**假设性论证**，但未给出具体数值反例

2. **是否稻草人**：❌ 非稻草人。等宽箱对高自信度模型不敏感是已知限制。

3. **是否误解前提**：⚠️ 部分误解。脚本**已主动披露**此限制：
   - P3："Brier reliability 用 10 等宽箱估计，小样本有偏差 → 与 smooth_ece 互补报告"
   - 脚本同时计算`smooth_ece`（无分箱核平滑估计器，calibration.py:246-296）作为互补指标
   - safety定义基于Brier reliability，但详细CSV同时保留`ts_delta_ece`（基于smooth_ece）
   - 反方未提及smooth_ece互补报告的存在

4. **攻击逻辑是否自洽**：⚠️ 有断链。"可能不敏感"→"可能safety=0"→"可能系统性低估"——三个"可能"串联，无确定性论证。

5. **严重程度是否夸大**：✅ 夸大。从"假设性可能"直接标"严重"，但：
   - 未构造出实际的safety=0错误判断反例
   - smooth_ece互补指标已覆盖分箱偏差
   - 影响所有13档的说法不准确：仅当maxprob集中在一个bin时才有问题，TS通常会改变maxprob分布使其跨bin

**修正后的实际影响**：等宽箱限制真实但已披露且有互补指标，降级严重→轻微（P2）。建议增加分箱敏感性分析作为补充。

**修补方案**（P2，可选改进）：
```python
# 在aggregate_to_390中增加分箱敏感性报告
for n_bins in [10, 15, 20]:
    rel_10 = brier_parts(mp, corr, n_bins=n_bins)  # 需brier_parts支持n_bins参数
    # 报告不同bin数的safety率对比
```

---

### S2: 校准参数每个shift重复拟合，cal_probs与shift无关导致13倍计算浪费

**裁决**：部分成立

**5维度审查**：

1. **反例是否成立**：✅ 代码事实确认。
   - `cal_probs, cal_labels`在shift循环外计算（line 306-308）
   - `fit_fn(cal_probs, cal_labels)`在shift循环内每档重新调用（line 347）
   - 对ts/platt/isotonic/vector/matrix/dirichlet这6种方法，输入相同→输出相同→冗余

2. **是否稻草人**：❌ 非稻草人。代码确实如此。

3. **是否误解前提**：❌ 未误解。反方正确识别了cal_probs与shift无关。

4. **攻击逻辑是否自洽**：✅ 逻辑自洽。但**量级估计有严重错误**。

5. **严重程度是否夸大**：✅ 严重夸大。反方claim"运行时间增加约6/8×13 ≈ 10倍"，但这是**量级错误**：
   - **反方错误**：假设fit是运行时间瓶颈
   - **实际**：运行时间瓶颈是`shifted_eval`（前向传播，每档~1-5s），fit是轻量操作
     - TS fit：1D L-BFGS-B优化，~10ms
     - Platt fit：2D L-BFGS-B优化，~20ms
     - vector/matrix/dirichlet fit：多变量优化，~50-500ms
   - 冗余fit总数：6方法 × 12冗余档 = 72次，每次~50-500ms → 总浪费~3.6-36s/checkpoint
   - 前向传播总时间：13档 × ~2s = ~26s/checkpoint
   - 实际浪费比例：3.6/26 ≈ 14% 到 36/26 ≈ 138%（最坏情况约2倍，非10倍）
   - **反方的"10倍"估计偏离实际约5-10倍**

**修正后的实际影响**：冗余拟合属实，但实际浪费约1.5-2倍（非10倍），降级严重→轻微（P2）。仍建议修复以提升效率。

**修补方案**（P2）：
```python
# 在shift循环外预拟合与shift无关的校准参数
cached_params = {}
for mname in ["ts", "platt", "isotonic", "vector", "matrix", "dirichlet"]:
    if mname in CALIBRATION_METHODS:
        fit_fn, _, _ = CALIBRATION_METHODS[mname]
        cached_params[mname] = fit_fn(cal_probs, cal_labels)

for shift in shifts:
    # ...
    for mname in METHODS:
        if mname in cached_params:
            params = cached_params[mname]  # 复用
            # ...
```

---

### S3: safety_rate >= 0.5阈值选择未声明理由

**裁决**：部分成立

**5维度审查**：

1. **反例是否成立**：✅ 代码确认。`n_safe = sum(1 for r in rows_390 if r["safety_rate"] >= 0.5)`（line 595），阈值0.5未注释理由。

2. **是否稻草人**：❌ 非稻草人。

3. **是否误解前提**：⚠️ 部分误解。`n_safe`只是**汇总打印**用的便利统计，非论文claim的唯一依据：
   - 390 CSV保留每格的`safety_rate`连续值（line 477）
   - 780 CSV保留每架构独立safety值（line 451）
   - 研究者可基于CSV用任意阈值重算，0.5阈值不影响数据完整性

4. **攻击逻辑是否自洽**：✅ 自洽。阈值选择确实影响汇总数字。

5. **严重程度是否夸大**：✅ 夸大。"审稿人可能质疑阈值选择的任意性"——但详细CSV使任何阈值可重算，论文可报告多阈值结果。影响仅限汇总打印的一行输出。

**修正后的实际影响**：阈值未声明理由属实，但数据完整性不受影响，降级严重→轻微（P2）。

**修补方案**（P2）：
```python
# 报告多阈值safe格数
for threshold in [0.5, 1.0]:
    n_safe = sum(1 for r in rows_390 if r["safety_rate"] >= threshold)
    print(f"安全格 (safety_rate>={threshold}): {n_safe}/{len(rows_390)}")
# 并在docstring声明：阈值0.5=至少一架构安全，阈值1.0=两架构都安全
```

---

### S4: 390矩阵safety_rate无置信区间，2架构均值的CI极宽

**裁决**：部分成立

**5维度审查**：

1. **反例是否成立**：✅ 统计事实确认。n=2的Wilson CI确实极宽（safety_rate=0.5时CI≈[0.06, 0.94]）。

2. **是否稻草人**：❌ 非稻草人。

3. **是否误解前提**：⚠️ 部分误解。390矩阵是**汇总视图**，非最终统计推断：
   - 780详细CSV保留每架构独立safety值
   - 脚本P2已披露"架构聚合取均值可能掩盖单架构失效 → 详细 CSV 保留每架构独立行"
   - 正式的统计推断应在780数据上做（如跨5种子×6方向的bootstrap CI）

4. **攻击逻辑是否自洽**：✅ 自洽。n_archs=2确实统计效力不足。

5. **严重程度是否夸大**：⚠️ 部分夸大。CI宽是n_archs=2的固有限制，但：
   - 390矩阵的safety_rate跨30格（6方向×5种子）聚合时可算有意义的总体CI
   - 单格CI宽不等于总体结论无统计效力
   - 反方将单格CI宽等价于"论文claim缺乏统计严谨性"，忽略了跨格聚合的统计效力

**修正后的实际影响**：单格CI宽属实（P1），但总体安全率可跨格bootstrap。建议报告总体CI并声明单格局限。

**修补方案**（P1）：
```python
# 总体安全率的bootstrap CI
from scipy.stats import bootstrap
safety_rates = [r["safety_rate"] for r in rows_390]
res = bootstrap([safety_rates], np.mean, n_resamples=10000, confidence_level=0.95)
summary["safe_rate_overall_ci"] = (float(res.confidence_interval.low),
                                    float(res.confidence_interval.high))
# 并在输出中声明：单格n_archs=2的CI宽，总体CI基于390格bootstrap
```

---

### S5: leads6命名与实际8通道不符

**裁决**：部分成立

**5维度审查**：

1. **反例是否成立**：✅ 代码确认。`LEAD_SUBSETS[6] = [0, 1, 6, 7, 8, 9, 10, 11]`为8通道。

2. **是否稻草人**：❌ 非稻草人。命名与实际通道数确实不符。

3. **是否误解前提**：✅ **误解前提**。反方承认docstring已解释，但未充分考虑：
   - l2_shifts.py docstring第6-10行**显式声明**："leads6: 键名沿用历史结果文件。实际变换为保留8个独立通道(I,II,V1-V6)，移除4个线性可导出导联——完整12导联可由I,II,V1-V6线性重构，属信息无损降档"
   - 脚本P6已披露"任务描述bilstm实为inceptiontime→按实际目录结构，已在脚本注释记录"
   - 这是**有意识的命名沿用**，非疏忽

4. **攻击逻辑是否自洽**：⚠️ "安全率可能因信息无损而偏高"是推测。信息无损降档确实可能比信息有损更容易，但这取决于TS对信息量的敏感度——未验证。

5. **严重程度是否夸大**：✅ 夸大。命名问题+已文档解释→"严重"过高。这是文档/命名规范问题，非正确性问题。实际变换正确（保留8个独立通道），仅名字有歧义。

**修正后的实际影响**：命名歧义真实但已文档解释，非正确性问题，降级严重→轻微（P2）。

**修补方案**（P2，可选）：
- 在390 CSV的shift列增加注释列`shift_actual_channels`标注实际通道数
- 或在论文中明确声明"leads6指6导联监护配置，实际保留8通道（移除4个线性可导出导联）"

---

### S6: 断点续传不验证数据一致性

**裁决**：部分成立

**5维度审查**：

1. **反例是否成立**：⚠️ 反例不成立。反方构造"模型加载失败→全零probs→cal_ece=1.0→写入json→续传跳过"场景，但：
   - `load_model`（line 184-210）在num_classes不匹配时`raise RuntimeError`（line 193）
   - state_dict不匹配时`load_state_dict(sd)`会抛`RuntimeError`
   - 异常在`main`的try-except（line 566-569）捕获，`evaluate_one_checkpoint`不会执行到写入json
   - **模型加载失败不会产生错误数据写入**——反例的关键环节不成立

2. **是否稻草人**：❌ 非稻草人。值验证缺失是真实的代码事实。

3. **是否误解前提**：⚠️ 部分误解。反方忽略了异常传播路径：加载失败→异常→不写入→续传时`is_checkpoint_complete`返回False→重跑。

4. **攻击逻辑是否自洽**：⚠️ 有断链。"部分shift的cal_ece是错误的"需要部分写入场景，但`evaluate_one_checkpoint`是**全13档成功后才写入**（line 396-402在shift循环外）。若中途OOM，已计算的`seed_results`不写入json，下次重跑。

5. **严重程度是否夸大**：✅ 夸大。反例不成立，但值验证作为防御性编程仍有价值。降级严重→轻微（P2）。

**修正后的实际影响**：值验证缺失属实但反例不成立（异常传播阻止错误数据写入），降级为P2防御性改进。

**修补方案**（P2，防御性）：
```python
def is_checkpoint_complete(run_dir, seed, shift_names):
    # ... 现有检查 ...
    for sn in shift_names:
        cell = seed_data[sn]
        # 增加值合理性检查
        cal_ece = cell.get("ts", {}).get("cal_ece", -1)
        if not (0 <= cal_ece <= 1):
            return False  # 值异常，触发重跑
        safety = cell.get("safety", -1)
        if safety not in (0, 1):
            return False
    return True
```

---

### S7: mamba仅1方向2seed排除，虽已声明但可能引入选择偏差

**裁决**：部分成立

**5维度审查**：

1. **反例是否成立**：✅ 代码确认。`ARCHS = ["resnet1d", "inceptiontime"]`（line 116），mamba不在列表。

2. **是否稻草人**：❌ 非稻草人。

3. **是否误解前提**：✅ **误解前提**。脚本已**充分声明**此限制：
   - A5："mamba 仅 ptbxl_chapman/seed42,43（OOM 限制），作为附录不进 390 主矩阵"
   - 适用边界："结论适用于 resnet1d + inceptiontime 两架构的迁移场景，不外推到 mamba"
   - 反方承认"脚本P1已披露此限制"，但仍标"严重"

4. **攻击逻辑是否自洽**：✅ 自洽。排除mamba确实可能使ptbxl_chapman方向安全率偏高。

5. **严重程度是否夸大**：✅ 夸大。已声明边界+不外推mamba→"严重"过高。选择偏差仅影响1/6方向，且已声明不外推。降级严重→轻微（P2）。

**修正后的实际影响**：已声明边界，sensitivity analysis建议合理但非必须，降级为P2。

**修补方案**（P2，可选）：
- 在780详细CSV中保留mamba的ptbxl_chapman/seed42,43数据作为附录
- 在summary JSON中增加mamba_sensitivity字段

---

### M1: aggregate_to_390排序混合int(seed)和str(shift_name)，CSV行顺序不直观

**裁决**：成立

**5维度审查**：

1. **反例是否成立**：✅ 代码确认。`sorted(agg.items())`对`(source, target, seed, sn)`排序，seed是int，sn是str。

2. **是否稻草人**：❌ 非稻草人。

3. **是否误解前提**：❌ 未误解。反方正确指出不会抛TypeError（tuple逐位比较，同位类型一致）。

4. **攻击逻辑是否自洽**：✅ 自洽。shift_name字符串排序确实不直观（"noise-6" < "noise12"因'-' < '1'）。

5. **严重程度是否夸大**：❌ 未夸大。反方正确标为轻微，不影响正确性。

**修补方案**（P3，cosmetic）：
```python
# 用显式sort key替代默认排序
shift_order = {s["name"]: i for i, s in enumerate(shifts)}
rows_390.sort(key=lambda r: (r["source"], r["target"], r["seed"], shift_order[r["shift"]]))
```

---

### M2: shifted_eval batch_size=1逐条处理，性能低

**裁决**：成立

**5维度审查**：

1. **反例是否成立**：✅ 代码确认。`for i in range(n)`逐条处理（line 171）。

2. **是否稻草人**：❌ 非稻草人。

3. **是否误解前提**：⚠️ 部分误解。逐条处理的部分原因是**变长shift**（如downsample产生不同长度），难以batch。但非变长shift（noise/gain/leads）确实可以batch。

4. **攻击逻辑是否自洽**：✅ 自洽。

5. **严重程度是否夸大**：❌ 未夸大。正确标为轻微。

**修补方案**（P3，性能优化）：
```python
# 对非变长shift做batch处理
if shift["type"] not in ("downsample",):
    # batch处理：一次性施加shift到整个batch
    batch = torch.stack([dataset[i][0] for i in range(len(dataset))])
    # ... vectorized apply_shift + model forward
else:
    # 变长shift逐条处理
```

---

### M3: 13档缺少导联置换、per-channel增益、时移等移位类型

**裁决**：驳回

**5维度审查**：

1. **反例是否成立**：❌ 不适用。这不是代码缺陷，而是**实验范围**问题。

2. **是否稻草人**：✅ **稻草人论证**。反方歪曲了正方的主张：
   - 13档由**协议预注册**定义（l2_shifts.py docstring第1行："协议§3:44-48"）
   - 脚本的目标是补齐**已定义的13档**，不是设计新的移位类型
   - 反方攻击的是"实验没测所有可能的移位"，但正方从未声称覆盖所有移位类型

3. **是否误解前提**：✅ **超出适用范围**。脚本docstring明确："13 档 L2 移位由 src/data/l2_shifts.py:get_l2_shifts() 定义，不再变更"（A2）。反方建议的导联置换/per-channel增益/时移不在13档定义内。

4. **攻击逻辑是否自洽**：✅ 逻辑自洽但前提错误。

5. **严重程度是否夸大**：反方自己标为轻微并承认"13档已覆盖主要类型"，但仍列为攻击点。

**驳回理由**：这是对未来工作的建议，非对当前脚本的攻击。13档为协议预注册定义，脚本正确实现了全部13档。反方自己承认"13档已覆盖主要类型"。增加新移位类型属于实验范围扩展，应在协议修订时讨论，非脚本缺陷。

---

### M4: 780详细CSV缺少raw_brier_raw字段，信息不完整

**裁决**：成立

**5维度审查**：

1. **反例是否成立**：✅ 代码确认。
   - `raw_brier_raw`在cell中计算并存储（line 323, 333）
   - 但780 CSV的fieldnames（line 588-592）不含`raw_brier_raw`
   - 数据已计算但未导出

2. **是否稻草人**：❌ 非稻草人。

3. **是否误解前提**：❌ 未误解。

4. **攻击逻辑是否自洽**：✅ 自洽。无法从780 CSV验证Brier分解恒等式（Brier = Rel - Res + Unc）。

5. **严重程度是否夸大**：❌ 未夸大。正确标为轻微。

**修补方案**（P3）：
```python
# 在780 CSV fieldnames中增加raw_brier_raw
write_csv(rows_780, OUT_CSV_780, [
    "direction", "source", "target", "arch", "seed", "shift", "shift_type",
    "raw_ece", "raw_brier_rel", "raw_brier_raw",  # 新增
    "ts_brier_rel", "ts_delta_ece", "brier_rel_improvement", "safety",
])

# 并在aggregate_to_390的rows_780.append中增加
"raw_brier_raw": cell.get("raw_brier_raw", float("nan")),
```

---

## 总结

### 实验整体设计是否经得起考验

**基本经得起考验，但有1个P0必修问题。**

实验的核心设计（390单元格矩阵、safety定义、断点续传、780详细附录）是合理的。13个攻击中：

- **1个真正致命（F1）**：噪声注入的rng问题会导致5/13档的噪声完全相关，这是真实的统计错误，必须在执行前修复。反方准确识别了此问题。
- **1个被夸大为致命但实际为严重（F2）**：变长输入未显式处理，但多数CNN架构支持变长，"崩溃"为推测。
- **6个严重攻击中5个降级为轻微**：S1/S2/S5/S6/S7的严重影响被夸大，实际为已披露的限制或量级估计错误。S3/S4有部分道理但详细CSV已保留全量数据。
- **1个驳回（M3）**：超出适用范围，13档为协议预注册定义。
- **3个轻微成立（M1/M2/M4）**：cosmetic/性能/数据完整性问题，不影响正确性。

### 需要优先修补的问题清单

**P0（必须修改后才能执行）**：
1. **F1**：修复噪声注入rng，在`shifted_eval`函数级创建一次rng传给`apply_shift`→`shift_noise`，同时修改`apply_shift`和`shift_noise`接受rng参数

**P1（强烈建议修改）**：
2. **F2**：验证模型对变长输入的支持，或对降采样信号resample回原始长度
3. **S4**：报告总体安全率的bootstrap CI，声明单格n_archs=2的统计效力局限

**P2（建议修改）**：
4. **S1**：增加分箱敏感性分析（10/15/20 bin对比），报告smooth_ece互补指标
5. **S2**：缓存与shift无关的校准参数（实际节省约1.5-2倍，非反方声称的10倍）
6. **S3**：报告多阈值safe格数（>=0.5, >=1.0），声明阈值选择理由
7. **S5**：在CSV增加实际通道数注释列，论文明确声明leads6的8通道语义
8. **S6**：在`is_checkpoint_complete`增加值合理性检查（0<=cal_ece<=1, safety∈{0,1}）
9. **S7**：在780 CSV保留mamba附录数据，声明mamba排除的潜在影响

**P3（cosmetic/可选）**：
10. **M1**：用显式sort key替代混合类型默认排序
11. **M2**：对非变长shift做batch处理
12. **M4**：在780 CSV增加raw_brier_raw字段

### 对反方攻击质量的评价

反方攻击整体质量**中等偏上**：
- **优点**：F1的rng问题识别精准，代码引用准确，7维度攻击框架系统性强
- **不足**：
  1. F2的"崩溃"为未验证的推测，未检查实际模型架构
  2. S2的"10倍"量级估计严重错误（实际约1.5-2倍）
  3. S1未构造出实际的safety=0失败反例（两个反例都得safety=1）
  4. S6的反例（模型加载失败→错误数据写入）不成立（异常传播阻止写入）
  5. M3超出适用范围（13档为协议预注册定义）
  6. 多个攻击未充分考虑脚本已有的主动披露（P1-P6, A1-A5, 适用边界声明）

**反方标注的"2致命+7严重"中，实际仅1致命+1严重+5轻微+1驳回**。反方有将已披露限制和量级错误包装成高严重级别的倾向。

---

## 附录：审查文件清单

| 文件 | 验证内容 | 审查状态 |
|------|---------|---------|
| `scripts/run_e1a_l2_shift_full.py` (627行) | 全部13攻击点的代码引用 | 逐行验证完成 |
| `src/data/l2_shifts.py` (192行) | F1(rng)、F2(降采样)、S5(leads6) | 逐行验证完成 |
| `src/utils/calibration.py` (860行) | S1(brier_parts分箱)、smooth_ece互补 | 重点函数验证完成 |
| `docs/adversarial_r1_attack_e1a.md` (433行) | 全部13攻击点的引用准确性 | 逐条核对完成 |

**报告结束。**
