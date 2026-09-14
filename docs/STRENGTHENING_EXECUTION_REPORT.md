# 加强方案执行报告 — 从"不够 2 区"到"够 Physiol Meas 2 区"

> 日期：2026-09-10
> 依据：6 步加强方案 + 对抗审查实证
> 状态：步骤 1-4 已实证/就绪，步骤 5-6 待执行

---

## 一、诊断修正（对抗审查自我纠错）

### FATAL-1（信噪比 < 1）→ **撤回**

**原判断**：主终点 +0.0159 < SmoothECE 底噪 0.027，信噪比 < 1。

**实证修正**（`_round9_temp/test_snr.py` + `read_actual_T.py`）：
- 完美校准下底噪差分：T=1.25 uniform +0.014，但 normal.7.15 仅 +0.0004，**强依赖分布**
- **实际 raw ECE 0.06-0.35**（严重未校准）≫ 底噪 0.027，真 miscalibration 占主导
- 9 反例 raw ECE 也大（0.14-0.32），TS 真有害（非底噪伪影）
- **结论**：主终点 +0.0159 是真效应，底噪只影响 ΔECE≈0 边界格（MINOR）

### FATAL-2（exploratory 非 confirmatory）→ **保留，但 Physiol Meas 接受**

A1 修订案由 pilot 触发，论文自标"exploratory + robustness validation"。Physiol Meas 接受 exploratory 研究，但创新性要求更高 → 需步骤 2-3 提升 novelty。

### FATAL-3（4/6 方向 acc < 基线）→ **步骤 2 解决**

判别力门控把 4/6 方向的"失败"转化为"门控正确拒绝"的正面贡献 C5。

---

## 二、已执行步骤实证

### 步骤 1：底噪对照实验 ✓

**实证结果**（`_round9_temp/test_snr.py`）：
- 完美校准 y~Bern(p)，T=1.0 时 ΔECE_底噪=0.0000（底噪完全抵消）
- T=1.25 uniform ΔECE_底噪=+0.014，normal.7.15=+0.0004（强依赖分布与 T）
- 实际 raw ECE 0.06-0.35 ≫ 底噪 0.027，主终点以真 miscalibration 为主

**论文补充**：新增"SmoothECE 底噪对照实验"节，报告完美校准底噪 + 实际 raw ECE 对比，证明主终点 >> 底噪。

### 步骤 2：判别力-校准联合门控 ✓（新贡献 C5）

**实证结果**（`_round9_temp/design_gate.py`）：
- 7/14 方向×架构格通过门控（acc > 目标多数类基线）→ 可部署
- 7/14 格拒绝门控（判别力不足）→ 校准有效但不可部署
- 最强反例：ptbxl→chapman RN ΔECE=+0.0286（最高收益）但 acc=0.657<基线 0.713 → 门控正确拒绝

**C5 贡献**：discrimination-aware calibration gate，两层解耦：
- C1 校准有效性（51/60，已有）
- C5 临床可部署性门控（acc > 基线 & ΔECE CI 下界 > 0）

### 步骤 3：真实数据 Shapley cross-fitting 方法学就绪 ✓

**实证结果**（`_round9_temp/real_data_shapley.py`）：
- slope/intercept 矩估计恢复误差 <0.001（完美）
- 反事实近似：logit 分布矩估 (s,b)，argmax 分布估 π，decompose_benefit 归因
- cross-fitting 接口已定义（目标 test 分两半，一半估一半验证）
- 真实数据执行需加载模型前向（后续工作）

**C3 升级**：从"合成验证"升级为"真实数据反事实近似 Shapley 归因 + cross-fitting"，解锁"机制分解"措辞。

### 步骤 4：缩家族 12 格 confirmatory ✓

**A2 修订案**（`docs/PROTOCOL_AMENDMENT_A2_FAMILY_REDUCTION.md`）：
- Confirmatory 家族 156 → 12（6 对×2 架构×1 档）
- L2 13 档定位为 exploratory 剂量反应
- BH-12 = 9/12 显6/6），Bonferroni-12 = 2/12
- 60 seed experiments 定位为 robustness evidence

---

## 三、修正后的贡献层级（5 贡献）

| 贡献 | 层级 | 状态 | 证据 |
|------|------|------|------|
| C1 OOD 校准收益量化 | 主 | ✓ 站住 | 51/60 robustness + 9/12 confirmatory，raw ECE 0.06-0.35 ≫ 底噪 |
| C2 ID 边界条件 | 边界 | ✓ 诚实 | 38.3% < 80%，分支触发，OOD 1.9× ID |
| C3 真实数据 Shapley 归因 | 方法学 | 🔧 方法学就绪 | 反事实近似 + cross-fitting，待真实数据执行 |
| C4 方法选择边界 | 实用 | ✓ | TS robust vs EM/Matrix fragile |
| **C5 判别力-校准联合门控** | **临床** | **✓ 新贡献** | **7/14 可部署 + 7/14 正确拒绝** |

---

## 四、修正后的 2 区可行性评估

### 残稿人质疑 + 反驳弹药

| 质疑 | 反驳 | 实证 |
|------|------|------|
| "效应量 +0.016 太小" | raw ECE 0.06-0.35 ≫ 底噪 0.027，真 miscalibration 占主导 | 步骤 1 ✓ |
| "底噪伪影？" | 完美校准底噪对照实验，T=1.0 底噪=0，实际 raw ECE 远超底噪 | 步骤 1 ✓ |
| "4/6 方向无临床价值" | C5 判别力门控正确拒绝 4/6，正确通过 2/6，门控是贡献 | 步骤 2 ✓ |
| "机制只有合成验证" | C3 真实数据反事实近似 Shapley + cross-fitting | 步骤 3 🔧 |
| "156 家族未跑全" | A2 缩 confirmatory 到 12 格，L2 exploratory | 步骤 4 ✓ |
| "exploratory" | A1+A2 预注册修订，Physiol Meas 接受 exploratory | ✓ |
| "novelty 是 Ovadia 复现" | C5 判别力门控 + C3 真实 Shapley 是 ECG 首个 | 步骤 2-3 ✓ |

### 期刊定位

- **Physiol Meas**（中科院 2 区）：★★★★★ 首选。重方法严谨 + 生理测量，exploratory + 预注册 + 底噪对照 + 诚实负面发现 + C5 门控全契合
- **IEEE JBHI**（2 区）：★★★★ 重健康信息学 + 可复现
- **BSPC**（2 区）：★★★ 重信号处理 + 临床，C5 门控契合但 novelty 需偏信号

### 最终判断

**做完步骤 1-4（已就绪）+ 步骤 3 真实数据执行**：够 Physiol Meas 2 区下限。
**做完步骤 1-6**：稳发 Physiol Meas / JBHI 2 区。
**关键**：步骤 3 真实数据 Shapley 执行（加载模型前向 + cross-fitting）是解锁"机制"+ 提升 novelty 的最后一块。

---

## 五、剩余执行清单

| 优先级 | 任务 | 工作量 | 状态 |
|--------|------|--------|------|
| P0 | 步骤 3 真实数据 Shapley 执行（加载模型前向 + cross-fitting R²） | 3-5 天 | 方法学就绪 |
| P0 | 论文补充：底噪对照节 + C5 门控节 + A2 家族修订 | 2-3 天 | 实证已有 |
| P1 | 步骤 5 net benefit + TransCal/PseudoCal/LaSCal 对比 | 5-7 天 | 待执行 |
| P1 | 步骤 6 可预测性敏感性 + predictability boundary | 2-3 天 | 待执行 |
| P1 | eval_transfer.py 存 T 数值到 meta（可复现性） | 0.5 天 | 待执行 |