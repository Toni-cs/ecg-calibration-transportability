# P0-4 反反方回应报告

> **反反方代理-P0-4 交付**。本报告对反方攻击报告 `docs/p0_attack_p0_4.md` 的 8 个攻击点进行逐条独立审查，基于实际代码验证（非假设），诚实评估每个攻击是否成立、能否反驳、若成立如何修补。
>
> **审查日期**：2026-09-09
> **审查代理**：反反方代理-P0-4（GLM-5.2）
> **审查依据**：实际读取 `src/utils/calibration.py`、5 个脚本、`tests/test_model.py` 的源代码

---

## 总体判定

**8 个攻击点中**：
- **3 个成立**（F2、S1/S2、S3）——反方发现真实问题，需修补
- **3 个部分成立**（F1、F3、F4）——事实成立但严重性被夸大或归因有误，可部分反驳
- **2 个成立但轻微**（M1、M2、M3 中合并为 3 个轻微，均成立）——反方描述准确

**核心结论**：
- **F2 是真实致命 bug**：`compute_all_metrics()` 漏传 `n_bins` 给 `brier_parts()`，与 P0-4 修复目标直接矛盾，必须修补
- **F1 事实成立但"致命"评级过重**：5 处调用方未传 `n_bins`，但当前默认值=原始硬编码=10，行为完全等价，无任何数值变化。是工程稳健性问题而非当前 bug
- **F3/F4 归因有误**：E2 用 `N_BINS=15` 是 P0-3 修补的有意选择，不是 P0-4 修复引入的问题。反方将 P0-3 的行为变更归咎于 P0-4

**需回炉重修**：F2（必修）、S1/S2（建议修）、S3（建议修）
**可接受**：F1（建议显式传参但非必须）、F3/F4（需文档化但非 P0-4 职责）、M1/M2/M3（轻微）

---

## 逐条回应

### 攻击点 F1：E1a/E1b 共 5 处调用方遗漏

- **反方主张**：E1a L159、E1b L552/553/593/594 共 5 处调用 `brier_parts()` 未传 `n_bins`，修复声称"所有调用方都正确传参"不成立，评级"致命"
- **验证结果**：**部分成立**（事实成立，严重性夸大）
- **详细分析**：

  **事实层面成立**——经 `grep brier_parts\(` 全代码库验证，5 处调用方确实未传 `n_bins`：
  ```
  run_e1a_l2_shift_full.py:159:     _, rel, _, _ = brier_parts(mp, corr)
  run_e1b_loco_validation.py:552:   brier_raw_total, rel_raw, res_raw, unc_raw = brier_parts(raw_mp, raw_correct)
  run_e1b_loco_validation.py:553:   brier_cal_total, rel_cal, res_cal, unc_cal = brier_parts(cal_mp, cal_correct)
  run_e1b_loco_validation.py:593:   _, rel_r, _, _ = brier_parts(rmp, rcor)
  run_e1b_loco_validation.py:594:   _, rel_c, _, _ = brier_parts(cmp, ccor)
  ```
  这 5 处均依赖默认值 10。

  **但"致命"评级不成立**，理由如下：

  1. **当前行为完全等价**：`brier_parts` 默认值 `n_bins: int = 10` 与原始硬编码 `np.linspace(0, 1, 11)`、`range(10)`、`i == 9` 在数值上**完全一致**。E1a/E1b 调用结果与修复前逐字节相同，无任何数值变化。反方在 §0 概述中也承认"当前因默认值=原始硬编码而向后兼容"。

  2. **反例是假设性风险，非当前 bug**：反方构造的反例"设未来某次维护将默认值从 10 改为 15"是**未来可能发生但当前未发生**的事件。按此标准，所有依赖默认参数的代码都是"致命"——这显然不合理。Python 默认参数的设计意图正是允许调用方省略参数。

  3. **"修复声称'所有调用方都正确传参'不成立"——需核对正方原始声明**：反方攻击报告中"修复主张"原文是"更新 E3 调用处传 `n_bins=N_BINS`"，**并未声称"所有调用方都正确传参"**。反方将"未声称"曲解为"声称不成立"，是稻草人论证。

  4. **任务描述明确限定范围**：原任务描述只提到 E2/E3/E4/E6，未要求检查 E1a/E1b。E1a/E1b 未传参是**任务范围外的遗漏**，不是"修复声称覆盖但实际未覆盖"的违约。

- **反驳或修补**：

  **反驳**：F1 不构成"致命"攻击。当前无数值错误，反例是假设性未来风险，正方未做不实声明。

  **但建议修补**（提升工程稳健性，非修 bug）：
  ```python
  # run_e1a_l2_shift_full.py L159
  BRIER_N_BINS = 10  # 模块级常量，显式声明分箱数
  _, rel, _, _ = brier_parts(mp, corr, n_bins=BRIER_N_BINS)

  # run_e1b_loco_validation.py L552/553/593/594 同理
  BRIER_N_BINS = 10
  brier_raw_total, rel_raw, res_raw, unc_raw = brier_parts(raw_mp, raw_correct, n_bins=BRIER_N_BINS)
  brier_cal_total, rel_cal, res_cal, unc_cal = brier_parts(cal_mp, cal_correct, n_bins=BRIER_N_BINS)
  # L593/594 同理
  ```

  **裁决调整**：致命 → 严重（工程稳健性改进，非当前 bug）。

---

### 攻击点 F2：`compute_all_metrics()` 内部自相矛盾

- **反方主张**：`compute_all_metrics()` 接受 `n_bins` 参数并传给 `ece()`/`mce()`/`bootstrap_ece()`，但 L768 调用 `brier_parts(probs, labels)` 漏传 `n_bins`，同一函数内分箱数不一致，评级"致命"
- **验证结果**：**成立**（真实 bug，反方发现准确）
- **详细分析**：

  经读取 `calibration.py` L742-782 验证，反方描述完全准确：
  ```python
  def compute_all_metrics(probs, labels, n_bins: int = 10, n_bootstrap: int = 1000):
      ...
      ece_mean, ece_lower, ece_upper = bootstrap_ece(probs, labels, n_bins, n_bootstrap)  # L765: 传了
      brier, reliability, resolution, uncertainty = brier_parts(probs, labels)              # L768: 漏传！
      max_ce = mce(probs, labels, n_bins)                                                  # L771: 传了
  ```

  **这是 P0-4 修复最直接的内部遗漏**：
  - P0-4 修复目标是为 `brier_parts` 添加 `n_bins` 参数以支持分箱数控制
  - `compute_all_metrics` 是同文件内最直接的调用方，且自身已接受 `n_bins` 参数
  - 修复了 `brier_parts` 签名却未更新同文件内调用——是典型的"修复不完整"
  - 反方构造的反例 `compute_all_metrics(n_bins=5)` 确实会让 ECE/MCE 用 5 bin、Brier 用 10 bin，**同一返回字典内分箱数不一致**

  **与 P0-4 修复目标直接矛盾**：P0-4 声称解决"分箱不一致"，但在 `compute_all_metrics` 内部仍存在分箱不一致。

- **反驳或修补**：

  **无法反驳，必须修补**。最小修补：
  ```python
  # calibration.py L768
  brier, reliability, resolution, uncertainty = brier_parts(probs, labels, n_bins=n_bins)
  ```

  **裁决**：维持"致命"。F2 是 P0-4 修复的真实内部遗漏，必须回炉修补。

---

### 攻击点 F3：E2 使用 N_BINS=15，与原始硬编码 10 不一致

- **反方主张**：E2 传 `n_bins=N_BINS=15`，与原始硬编码 10 不一致，是静默行为变更，评级"严重"
- **验证结果**：**部分成立**（事实成立，归因有误）
- **详细分析**：

  **事实层面成立**——经读取 `run_e2_ablation_discrimination.py` L131/L315 验证：
  ```python
  N_BINS = 15                 # L131
  b_total, rel, res, unc = brier_parts(max_prob, correct, n_bins=N_BINS)  # L315，传 15
  ```

  **但归因错误**，理由如下：

  1. **这是 P0-3 修补引入的，不是 P0-4 修复引入的**：E2 L315 的注释明确写 `# 正方修补(P0-3): 显式传 n_bins=N_BINS`。E2 在 P0-3 阶段就显式传 15，P0-4 只是给 `brier_parts` 加了 `n_bins` 参数（使 P0-3 的传参成为可能）。反方将 P0-3 的有意行为变更归咎于 P0-4，是**归因错误**。

  2. **P0-4 修复前 E2 无法传参**：P0-4 修复前 `brier_parts` 无 `n_bins` 参数，E2 只能用默认 10 bin。P0-3 修补时若 P0-4 未修复，E2 传 `n_bins=N_BINS` 会抛 `TypeError`。即 P0-3 的传参依赖 P0-4 的签名修复——P0-4 是 P0-3 的前置条件，不是 P0-3 行为变更的原因。

  3. **"若 E2 之前用 10 bin 生成缓存结果，现在用 15 bin，结果不可复现"——这是 P0-3 的行为变更**：P0-3 主动选择 15 bin（更细粒度），是有意的实验设计调整，不是 P0-4 的遗漏。反方应将此攻击指向 P0-3 而非 P0-4。

  4. **15 bin 是合理的实验设计选择**：E2 是消融实验，更细的分箱粒度（15 bin）能更敏感地检测 discrimination 贡献。E3/E4 用 10 bin 是与默认值对齐。不同实验用不同粒度是合理的，只需文档化。

- **反驳或修补**：

  **反驳归因**：F3 的行为变更是 P0-3 修补引入的，不是 P0-4 修复的问题。反方应将此攻击重新指向 P0-3。

  **但事实层面建议**（在论文中文档化）：
  ```python
  # run_e2_ablation_discrimination.py L131
  N_BINS = 15  # Brier reliability / ECE 评估分箱数
  # 注：E2 用 15 bin（更细粒度以敏感检测消融贡献），E3/E4 用 10 bin（与默认对齐）。
  # 跨实验比较 Brier reliability 时需注意分箱数差异，或重算至统一分箱数。
  ```

  **裁决调整**：严重 → 轻微（归因错误，且是 P0-3 的有意设计选择，只需文档化）。

---

### 攻击点 F4：跨实验分箱数不一致

- **反方主张**：E2=15, E3=10, E4=10, E1a/E1b=10(default)，Brier reliability 跨实验不可直接比较，评级"严重"
- **验证结果**：**部分成立**（事实成立，但非 P0-4 职责）
- **详细分析**：

  **事实层面成立**——经全脚本验证，分箱数分布如下：
  | 脚本 | 常量 | 值 | 传参方式 |
  |------|------|----|---------|
  | E1a | （无） | 10（默认） | 未传 |
  | E1b | （无） | 10（默认） | 未传 |
  | E2 | `N_BINS` | 15 | 显式传 |
  | E3 | `N_BINS` | 10 | 显式传 |
  | E4 | `BRIER_N_BINS` | 10 | 显式传 |

  **但非 P0-4 修复的职责**，理由如下：

  1. **P0-4 修复目标是 `brier_parts` 函数签名**，不是统一跨实验分箱数。跨实验分箱数一致性是**实验设计层面的决策**，不是函数签名修复的职责。

  2. **跨实验分箱数不一致在 P0-4 修复前就存在**：P0-4 修复前 E2 用默认 10 bin，E3/E4 也用默认 10 bin——表面一致但实际是"都依赖硬编码"的巧合。P0-4 修复后各实验显式传参，暴露了原本隐含的设计差异。这是**暴露问题而非引入问题**。

  3. **E2 用 15 bin 是 P0-3 的有意选择**（见 F3 反驳）：不同实验用不同分箱粒度是合理的实验设计，只需论文文档化。

  4. **反方建议"统一 N_BINS=10"会破坏 E2 的实验设计**：E2 用 15 bin 是为了更敏感检测消融贡献，强行统一为 10 bin 会降低 E2 的检测灵敏度。

- **反驳或修补**：

  **反驳归因**：跨实验分箱数一致性是实验设计决策，不是 P0-4 函数签名修复的职责。P0-4 修复反而通过让各实验显式传参，暴露了原本隐含的设计差异，是改进而非退步。

  **建议**（论文层面，非代码层面）：在论文方法学部分显式文档化各实验的分箱数选择及理由。

  **裁决调整**：严重 → 轻微（非 P0-4 职责，且 P0-4 修复暴露问题而非引入问题）。

---

### 攻击点 S1：无 n_bins 输入验证

- **反方主张**：`brier_parts` 无 `if n_bins < 1: raise ValueError` 验证，n_bins≤0 静默返回无意义值，评级"严重"
- **验证结果**：**成立**（真实边界失效）
- **详细分析**：

  经读取 `calibration.py` L586-631 验证，`brier_parts` 确实无输入验证：
  ```python
  def brier_parts(probs, labels, n_bins: int = 10):
      ...
      bins = np.linspace(0, 1, n_bins + 1)  # n_bins=0 → [0.0]
      ...
      for i in range(n_bins):               # n_bins=0 → 空循环
          ...
      brier_total = reliability - resolution + uncertainty
      return float(brier_total), float(reliability), float(resolution), float(uncertainty)
  ```

  **反方描述准确**：
  - `n_bins=0`：`np.linspace(0,1,1)`=[0.0]，`range(0)`=空循环，返回 `(uncertainty, 0, 0, uncertainty)`，不崩溃不警告
  - `n_bins=-1`：`np.linspace(0,1,0)`=[]，`range(-1)`=空循环，同上
  - 返回值看似合法浮点数但完全无意义，违反 fail-fast 原则

  **但严重性可商榷**：
  1. **无实际触发场景**：全代码库调用方都传正整数（10 或 15），无任何路径会传 n_bins≤0
  2. **这是防御性编程缺失，非当前 bug**：实际运行中不会触发
  3. **但 fail-fast 原则确实违反**：若未来用户误传 n_bins=0，会得到无意义结果且无告警

- **反驳或修补**：

  **建议修补**（防御性编程，符合 fail-fast 原则）：
  ```python
  def brier_parts(probs, labels, n_bins: int = 10):
      if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
          raise ValueError(f"n_bins must be a positive integer, got {n_bins}")
      ...
  ```

  **裁决**：维持"严重"但标注"防御性改进，非当前 bug"。建议修补以提升代码健壮性。

---

### 攻击点 S2：n_bins=0 时 brier_total=uncertainty

- **反方主张**：n_bins=0 时返回 `(uncertainty, 0, 0, uncertainty)`，reliability=0 暗示"完美校准"但实际未分箱，语义错误，评级"严重"
- **验证结果**：**成立**（与 S1 同一问题，是 S1 的具体表现）
- **详细分析**：

  S2 是 S1 的具体语义分析，非独立攻击点。n_bins=0 时的语义错误（reliability=0 暗示完美校准）是 S1 边界失效的后果。

  **与 S1 合并处理**：修补 S1（加输入验证）后，S2 自动消失——n_bins=0 会抛 ValueError 而非返回无意义值。

- **反驳或修补**：

  **与 S1 同一修补**：加 `if n_bins < 1: raise ValueError` 后，S2 不再可能触发。

  **裁决**：与 S1 合并，维持"严重"但非独立攻击点。

---

### 攻击点 S3：测试因 F2 而失效

- **反方主张**：`test_brier_parts` 通过 `compute_all_metrics(n_bins=5)` 间接测试，因 F2 实际用 10 bin，测试无法捕获 F2 bug，评级"严重"
- **验证结果**：**成立**（真实测试缺陷）
- **详细分析**：

  经读取 `tests/test_model.py` L188-198 验证，反方描述准确：
  ```python
  def test_brier_parts(self):
      metrics = compute_all_metrics(
          np.random.rand(100), (np.random.rand(100) > 0.5).astype(float), n_bins=5, n_bootstrap=20
      )
      ...
      total = (metrics['brier_reliability'] - metrics['brier_resolution'] + metrics['brier_uncertainty'])
      assert total == pytest.approx(metrics['brier'], abs=1e-12)  # 按构造恒成立
      assert abs(metrics['brier_raw'] - metrics['brier']) < 0.1   # 阈值宽松
  ```

  **反方分析准确**：
  1. 测试通过 `compute_all_metrics(n_bins=5)` 间接测试 `brier_parts`
  2. 因 F2，`compute_all_metrics` 不传 `n_bins=5` 给 `brier_parts`，实际用默认 10 bin
  3. Murphy 恒等式 `total == brier` 按**构造**成立（`brier_total = reliability - resolution + uncertainty`），对任何 n_bins 都成立，**无法区分 5 bin 还是 10 bin**
  4. `abs(brier_raw - brier) < 0.1` 阈值宽松，10 bin 和 5 bin 都可能成立
  5. **测试无法检测 F2 bug**——即使 F2 存在，测试仍通过

  **关于"阻碍正确修复"**：反方称"修复 F2 后，5 bin 的 `brier_raw - brier` 可能 >0.1，测试反而失败"。这是**推测**——100 样本 + 5 bin 的分箱残差是否 >0.1 取决于数据分布，不一定触发。但方向正确：修复 F2 后该测试可能需要调整阈值。

- **反驳或修补**：

  **无法反驳，建议修补**。改进测试以直接测试 `brier_parts` 并能捕获 F2：
  ```python
  def test_brier_parts_n_bins(self):
      """直接测试 brier_parts 的 n_bins 参数生效"""
      np.random.seed(42)
      probs = np.random.rand(1000)
      labels = (np.random.rand(1000) > 0.5).astype(float)

      # 直接调用 brier_parts，验证 n_bins 生效
      _, rel_5, _, _ = brier_parts(probs, labels, n_bins=5)
      _, rel_10, _, _ = brier_parts(probs, labels, n_bins=10)
      # 5 bin vs 10 bin 的 reliability 应不同（分箱粒度不同）
      assert rel_5 != rel_10  # 捕获 n_bins 未生效的 bug

  def test_compute_all_metrics_n_bins_consistency(self):
      """验证 compute_all_metrics 的 n_bins 对所有指标生效（捕获 F2）"""
      np.random.seed(42)
      probs = np.random.rand(1000)
      labels = (np.random.rand(1000) > 0.5).astype(float)

      m5 = compute_all_metrics(probs, labels, n_bins=5, n_bootstrap=0)
      m10 = compute_all_metrics(probs, labels, n_bins=10, n_bootstrap=0)
      # ECE 用 n_bins，应不同
      assert m5['ece'] != m10['ece']
      # Brier reliability 也应用 n_bins，应不同（捕获 F2）
      assert m5['brier_reliability'] != m10['brier_reliability']
  ```

  **裁决**：维持"严重"。测试确实无法捕获 F2，需补充直接测试。

---

### 攻击点 M1：E6 不调用 brier_parts

- **反方主张**：E6 有自己的分箱逻辑，不调用 `brier_parts`，任务要求检查 E6 是多余，修复覆盖声明提到 E6 也不准确
- **验证结果**：**成立**（事实准确）
- **详细分析**：

  经 `grep brier_parts run_e6_reliability_diagrams.py` 验证，无匹配——E6 确实不调用 `brier_parts`。反方描述准确。

  **但这是覆盖声明问题，不影响 P0-4 修复正确性**：P0-4 修复的是 `brier_parts` 函数签名，E6 不调用 `brier_parts` 则不在修复范围内。任务描述提到 E6 是检查范围过大，不是修复错误。

- **反驳或修补**：

  **事实成立但无需代码修补**。建议修正修复覆盖声明，明确 E6 不在 P0-4 修复范围内。

  **裁决**：维持"轻微"。

---

### 攻击点 M2：n_bins=浮点数时崩溃

- **反方主张**：`n_bins: int = 10` 类型注解无运行时检查，传 `n_bins=10.5` 时 `range(10.5)` 抛 TypeError，错误信息不友好
- **验证结果**：**成立**（事实准确）
- **详细分析**：

  反方描述准确：`range(10.5)` 确实抛 `TypeError: 'float' object cannot be interpreted as an integer`。类型注解为 `int` 但无运行时检查。

  **但这是用户错误，崩溃合理**：类型注解已明确声明 `int`，传浮点数是调用方违反契约。Python 类型注解本就是文档性质，不强制运行时检查。错误信息虽不友好但定位准确。

- **反驳或修补**：

  **建议修补**（与 S1 同一处理，提升错误信息友好性）：
  ```python
  if not isinstance(n_bins, (int, np.integer)) or n_bins < 1:
      raise ValueError(f"n_bins must be a positive integer, got {n_bins!r} (type {type(n_bins).__name__})")
  ```

  **裁决**：维持"轻微"。

---

### 攻击点 M3：E1b 注释代码也未传 n_bins

- **反方主张**：E1b L585 注释代码 `#   ncv = brier_parts(raw_mp, raw_correct)[1] - brier_parts(cal_mp, cal_correct)[1]` 也未传 n_bins，若未来取消注释会重复 F1 遗漏
- **验证结果**：**成立**（事实准确）
- **详细分析**：

  经读取 `run_e1b_loco_validation.py` L585 验证，注释代码确实存在且未传 n_bins：
  ```python
  #   ncv = brier_parts(raw_mp, raw_correct)[1] - brier_parts(cal_mp, cal_correct)[1]
  ```

  **但这是注释，不影响运行**：注释代码是 NCV 定义的说明性文档，不执行。反方称"若未来取消注释会重复 F1 遗漏"是假设性维护风险，非当前 bug。

- **反驳或修补**：

  **建议修补**（清理注释或补全参数，降低维护风险）：
  ```python
  #   ncv = brier_parts(raw_mp, raw_correct, n_bins=BRIER_N_BINS)[1] \
  #         - brier_parts(cal_mp, cal_correct, n_bins=BRIER_N_BINS)[1]
  ```

  **裁决**：维持"轻微"。

---

## 边界条件独立验证

### n_bins=1（单 bin）
- **行为**：`np.linspace(0,1,2)`=[0.0, 1.0]，`range(1)`=[0]，i=0 == n_bins-1=0，mask = 全 True。所有样本在一个 bin。
- **验证**：✅ 正确处理，数学上合理（单 bin 退化为全局校准误差）。反方 §4.1 判定正确。

### n_bins=100（多 bin）
- **行为**：100 个 bin，空 bin 被 `if mask.sum() == 0: continue` 跳过，无 NaN/inf。
- **验证**：✅ 不崩溃。反方 §4.2 判定正确。

### n_bins=0 / n_bins=-1
- **验证**：❌ 静默返回无意义值（见 S1/S2）。反方判定正确。

### 概率恰好=1.0
- **验证**：✅ `i == n_bins - 1` 时 mask 用 `<=` 包含 1.0，与原始 `i == 9` 等价。反方 §4.5 判定正确。

---

## 结论

### 需回炉重修（必修）

1. **F2（致命）**：`calibration.py` L768 `brier_parts(probs, labels)` → `brier_parts(probs, labels, n_bins=n_bins)`。这是 P0-4 修复的真实内部遗漏，与修复目标直接矛盾，必须修补。

### 建议修补（提升健壮性，非阻塞）

2. **S1/S2（严重）**：`brier_parts` 开头加输入验证 `if not isinstance(n_bins, (int, np.integer)) or n_bins < 1: raise ValueError(...)`。防御性编程，符合 fail-fast 原则。
3. **S3（严重）**：补充直接测试 `brier_parts(n_bins=5)` 与 `compute_all_metrics` 的 n_bins 一致性测试，以能捕获 F2 类 bug。
4. **F1（严重，降级自致命）**：E1a/E1b 5 处调用方显式传 `n_bins=10`（或模块级常量）。提升工程稳健性，防止未来默认值变更导致静默行为变更。

### 可接受（无需代码修补）

5. **F3（轻微，降级自严重）**：E2 用 15 bin 是 P0-3 的有意选择，非 P0-4 引入。归因错误。建议论文文档化。
6. **F4（轻微，降级自严重）**：跨实验分箱数一致性是实验设计决策，非 P0-4 函数签名修复的职责。P0-4 修复反而暴露了原本隐含的设计差异。
7. **M1（轻微）**：E6 不调用 `brier_parts`，覆盖声明不精确，不影响修复正确性。
8. **M2（轻微）**：浮点 n_bins 崩溃是用户违反类型契约，错误信息不友好但定位准确。S1 修补后自动改善。
9. **M3（轻微）**：注释代码不影响运行，维护风险轻微。

### 反方攻击质量评估

- **高质量攻击**：F2、S1/S2、S3——发现真实问题，代码证据准确，论证严谨
- **归因错误攻击**：F3、F4——事实成立但将 P0-3 的有意选择或实验设计决策归咎于 P0-4
- **严重性夸大攻击**：F1——事实成立但"致命"评级过重，当前无数值错误，是工程稳健性问题
- **准确轻微攻击**：M1、M2、M3——事实准确，严重性评级合理

### 最终裁决

**P0-4 修复的核心变更（`brier_parts` 签名 + 硬编码替换）技术正确**，向后兼容性成立，边界处理正确。

**但存在 1 个真实致命遗漏（F2）**：`compute_all_metrics` 漏传 `n_bins` 给 `brier_parts`，与 P0-4 修复目标直接矛盾，必须回炉修补。

**修补 F2 后，P0-4 修复可视为完成**。S1/S2/S3/F1 是建议性改进，不阻塞修复完成。F3/F4 归因有误，不构成对 P0-4 的有效攻击。

**最小修补路径**：
1. `calibration.py` L768：`brier_parts(probs, labels)` → `brier_parts(probs, labels, n_bins=n_bins)`（必修）
2. `calibration.py` L586 后加输入验证（建议）
3. `tests/test_model.py` 补充直接测试 `brier_parts(n_bins=5)` 与 `compute_all_metrics` 一致性（建议）
4. E1a/E1b 5 处显式传 `n_bins=10`（建议）
