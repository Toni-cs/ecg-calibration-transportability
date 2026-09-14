# P0 R6轮终审裁决

> **终审代理交付**（任务 #141）。本报告综合 3 份 R6 反方攻击报告（`docs/p0r6_attack_p0_{1,4,6_7}.md`）、3 份 R6 反反方审查报告（`docs/p0r6_counter_p0_{1,4,6_7}.md`）和 R5 终审裁决（`docs/p0r5_final_verdict.md`），对 R6 轮 3 个 P0 修复做最终独立裁决。
> **审查日期**：2026-09-10
> **审查代理**：R6-Phase4 终审代理（GLM-5.2）
> **判定原则**：以代码事实为唯一判据，独立交叉对照反方攻击与反反方审查，不盲从任何一方。收敛标准：P0-致命/P0-严重/P0-中等攻击点全部清零才算"已收敛"，仅剩 P0-轻微/P0-轾微可选改进也算收敛。

---

## 1. R6轮对抗审查总览

### 1.1 审查范围

- **3 个 P0 类别**：P0-1（RNG seed 标记体系）、P0-4（n_bins 验证守卫）、P0-6+7（CSV schema/OOM 备选）
- **已收敛 P0**：P0-3（E2 消融分箱）、P0-8（ECE 加权术语）—— R4 已判定通过，R5/R6 无新攻击
- **参与代理**：3 个反方挑刺代理（GLM-5.2）+ 3 个反反方审查代理（GLM-5.2）+ 1 个终审代理（GLM-5.2）
- **审查流程**：反方 7 维度攻击 → 反反方逐行代码验证 → 终审交叉对照独立裁决

### 1.2 R6 修复内容概述

| P0 | R6 修复内容 | 涉及文件 | 改动量 |
|----|-----------|---------|--------|
| P0-1 | eval_l2_shift.py L196 添加 `__seed_strategy__` 标记写入 + run_e1a_l2_shift_full.py L280-281 放宽 safety 检查 | eval_l2_shift.py + run_e1a_l2_shift_full.py | 4 行 |
| P0-4 | calibration.py 6 处守卫增加 bool 排除 + 上界 10**6 + test_model.py L230 扩充测试 | calibration.py + test_model.py | 5 行 |
| P0-6+7 | run_e5_inception_lite.py L593 `n_ood=0` → `n_ood=int(len(ood_probs))` | run_e5_inception_lite.py | 1 行 |

**R6 总改动量**：10 行（P0-1 4 行 + P0-4 5 行 + P0-6+7 1 行）

### 1.3 三份反方攻击报告统计（按 P0 分类 × 严重度）

| P0 | 致命 | 严重 | 中等 | 轾微 | 总计 |
|----|------|------|------|------|------|
| P0-1 | 1（Attack-1） | 1（Attack-2） | 4（Attack-3/4/6/7） | 2（Attack-5/8） | 8 |
| P0-4 | 1（ATK-1） | 3（ATK-2/3/4） | 2（ATK-5/6） | 1（ATK-7） | 7 |
| P0-6+7 | 0 | 0 | 0 | 4（Attack-1/3/5/7） | 4 |
| **合计** | **2** | **4** | **6** | **7** | **19** |

### 1.4 三份反反方审查报告裁决统计

| P0 | 完全成立 | 部分成立 | 不成立 | 需 R7 修复 |
|----|---------|---------|--------|-----------|
| P0-1 | 8（全部成立） | 0 | 0 | 5 项 |
| P0-4 | 6（ATK-1/2/3/4/6/7） | 1（ATK-5） | 0 | 5 项 |
| P0-6+7 | 4（全部成立，均轾微） | 0 | 0 | 0 项 |
| **合计** | **18** | **1** | **0** | **10 项** |

### 1.5 与 R5 轮的对比

| 维度 | R5 攻击点（终审校准后） | R6 攻击点（反反方校准后） | 变化 |
|------|----------------------|------------------------|------|
| P0-1 | 2（1 严重 + 1 中等） | 8（1 致命 + 1 严重 + 4 中等 + 2 轻微） | +6，**升级为致命** |
| P0-4 | 3（3 严重） | 7（1 致命 + 3 严重 + 2 中等 + 1 轾微） | +4，**升级为致命** |
| P0-6+7 | 2（2 中等） | 4（4 轾微） | +2，**降级为轾微** |
| **总计** | **7** | **19** | **+12** |

**趋势分析**：R6 攻击点总数从 R5 的 7 升至 19，**出现反弹**。原因：R6 修复存在两个致命缺陷（P0-1 标记写入位置错误 + P0-4 修复范围未覆盖 scripts），导致 R5 已识别的严重问题未实际修复反而升级。P0-6+7 则成功收敛（中等→轾微）。

---

## 2. R6总体判定

### 2.1 P0-1 判定：❌ 不通过

**判定理由**：

1. **致命缺陷未修复**：Attack-1 确认成立——R6 修复将标记写入 `existing[sk]["__seed_strategy__"] = "md5_v1"` 放在 `if out_path.exists():` 条件块**内部**（L187 条件，L196 写入）。首次运行时 `l2_shift_results.json` 不存在，L187 条件为 False，L188-197 整块跳过，L196 标记写入**永远不执行**。R6 修复对最常见使用场景（首次运行）完全失效，这正是 R5 Attack-1 要修复的 bug。

2. **修复报告错误声明**：`docs/p0r6_fix_p0_1.md` §3.3 声称"Attack-1 关闭✅"是错误声明——验证仅覆盖续传路径（L192-197 分支），未覆盖首次运行路径（L185-186 + L198 分支）。Attack-2（严重）成立。

3. **次生风险**：Attack-6/7 在 Attack-1 修复后会显现——eval_l2_shift 产出的结果（无 safety）会被 run_e1a 复用，safety 默认 0 向下偏置聚合，且"从未计算"被静默等同"TS 未改善"。

4. **代码质量问题**：Attack-3（DRY 违反，硬编码 "md5_v1"）、Attack-4（cell["safety"]=0 死代码）、Attack-5（docstring 矛盾）、Attack-8（谓词函数副作用）均确认成立。

**关键发现**：R6 修复代码放置位置错误（标记写入在条件块内），是**单行缩进错误**导致的致命缺陷。修复本意是"无条件写入标记"，实际实现是"条件写入标记"。这是典型的**意图与实现偏差**。

### 2.2 P0-4 判定：❌ 不通过

**判定理由**：

1. **致命缺陷未修复**：ATK-1 确认成立——R6 修复仅覆盖 `src/utils/calibration.py` 的 6 处守卫，但代码库中 `scripts/` 目录下 3 个文件的 4 个 n_bins 函数**完全无守卫**：
   - `scripts/run_e2_ablation_discrimination.py` `fit_binned_temperature` (L151)
   - `scripts/run_e4_temperature_analysis.py` `quintile_edges` (L187)
   - `scripts/run_e6_reliability_diagrams.py` `compute_reliability_bins` (L132)
   - `scripts/run_e6_reliability_diagrams.py` `bootstrap_bin_accuracy_ci` (L200)
   
   A1 bool 穿透和 A3 OOM 在这些函数中**完全未修复**。修复报告声称"P0-4 可宣布完全收敛"为假。

2. **量级错误**：ATK-2/4 确认成立——上界 10**6 对 O(n_bins) Python 循环实现过大。合法输入 `ece(n_bins=10**6)` 阻塞 4.8s，`compute_all_metrics(n_bins=10**6)` 阻塞 83-190 分钟，`bootstrap_ece(n_bins=10**6)` 阻塞 13.9-19.5 小时。

3. **测试覆盖退步未完全修复**：ATK-3 确认成立——brier_parts 测试 L213 仍用 `[0, -1, 1.5, "10"]`（4 个值），遗漏 `None/True/2.0/10**18` 四个关键 case，与 L230 的 8 个值不一致。A1/A3 对 brier_parts 无测试保护。

4. **修复报告逻辑断链**：ATK-6 确认成立——§7"完全收敛"声明与 ATK-1 实测结果矛盾，将子集一致性误推为全局收敛。

**正方修复的正确部分**（应予肯定）：在 `src/utils/calibration.py` 范围内的修复**正确且完整**——6 处守卫模式完全一致、bool 排除正确、上界检查正确、np.integer 覆盖所有 numpy 整数类型、ece/mce/bootstrap_ece 测试覆盖 8 个非法值。问题在于**修复范围未覆盖 scripts**，以及**上界 10**6 对 O(n_bins) 实现过大**。

### 2.3 P0-6+7 判定：✅ 通过（已收敛）

**判定理由**：

1. **R6 修复方向正确**：L593 `n_ood=0` → `n_ood=int(len(ood_probs))` 与正常路径 L654 语义完全对齐。ood_probs 变量流（L532→L549→L574→L579→L583→L593）完整无误，L593 处引用的 ood_probs 已过完整截断+过滤+归一化管线。

2. **反方 7 维度全覆盖攻击仅发现 4 个轾微攻击点**：Attack-1（下游 sum 误导风险）、Attack-3（n_ood 语义未文档化）、Attack-5（传参风格不一致）、Attack-7（R5"值不同可区分"在双空场景不成立）。反反方独立核实均事实成立但严重度均正确归类为轾微。

3. **反反方独立排查未发现任何遗漏的致命/严重/中等高严重度问题**：9 项潜在高严重度风险（ood_probs 作用域、类型安全、空数组处理、归一化影响、截断独立性、新 bug 引入、与正常路径一致性、OOM 异常路径、FileNotFound 路径）均不存在。

4. **符合 R5 终审预期**：R5 终审预期"R6 修复后可完全收敛"，R6 反方验证结果符合预期——P0-6+7 的致命/严重/中等攻击点全部清零，仅剩 4 个轾微可选改进项。

5. **4 个轾微攻击点均不影响功能正确性**，属可选改进项（IMP-1/IMP-2/IMP-3 可一次性合并为 4 行改动，IMP-4 无需修复）。

---

## 3. 收敛状态汇总表

| P0 | 致命 | 严重 | 中等 | 微 | 判定 | R7必修 |
|----|------|------|------|------|------|--------|
| P0-1 | 1 | 1 | 4 | 2 | ❌ 不通过 | 5 项（~11-14 行） |
| P0-4 | 1 | 3 | 2 | 1 | ❌ 不通过 | 5 项（~15-20 行） |
| P0-6+7 | 0 | 0 | 0 | 4 | ✅ 通过 | 0 项 |
| **合计** | **2** | **4** | **6** | **7** | **2/3 不通过** | **10 项（~26-34 行）** |

**收敛判定**：❌ **R6 未收敛**。存在 2 个致命攻击点（P0-1 Attack-1 + P0-4 ATK-1）+ 4 个严重攻击点 + 6 个中等攻击点未清零。仅 P0-6+7 单项收敛。

---

## 4. R7必修项清单（按优先级排序）

### 4.1 P0-1 R7必修项（5 项，~11-14 行改动）

| 优先级 | 对应攻击点 | 文件路径 | 行号 | 改动内容 | 改动量 | 验证方法 |
|--------|-----------|---------|------|---------|--------|---------|
| **P0-致命** | Attack-1 | scripts/eval_l2_shift.py | L185 后 | 在 `all_results[f"seed{seed}"] = seed_results` 后**无条件**写入 `all_results[f"seed{seed}"]["__seed_strategy__"] = SEED_STRATEGY_VERSION`，确保首次运行也写入标记（移到 `if out_path.exists():` 条件块外部） | 1 行 | 删除 l2_shift_results.json 后首次运行 eval_l2_shift，检查产出文件含 `__seed_strategy__` 标记 |
| **P0-中等** | Attack-3 | scripts/eval_l2_shift.py | 顶部 + L196 | 定义 `SEED_STRATEGY_VERSION = "md5_v1"` 常量，L196 改为常量引用（或从共享模块导入，消除 DRY 违反） | 2 行 | grep 确认 eval_l2_shift.py 无硬编码 "md5_v1" 字符串 |
| **P0-中等** | Attack-4 + Attack-8 | scripts/run_e1a_l2_shift_full.py | L280-281 | `cell["safety"] = 0` 改为 `pass`，消除死代码和谓词函数副作用 | 1 行 | 单元测试：is_checkpoint_complete 不修改输入 dict |
| **P0-中等** | Attack-6 + Attack-7 | scripts/run_e1a_l2_shift_full.py | L462 + L470 + L621 | safety 默认改 None，780 CSV 增加 `safety_source` 列（"computed"/"default"），聚合时区分来源 | 5-8 行 | 检查 780 CSV 含 safety_source 列，eval_l2_shift 产出的 cell 标注 "default" |
| **P0-轻微** | Attack-5 | scripts/run_e1a_l2_shift_full.py | L254 + L277 | 更新 docstring 和注释，safety 标注为可选字段 | 2 行 | 阅读 docstring 确认与代码一致 |

**P0-1 R7 核心修复**：将 eval_l2_shift.py 的标记写入移到条件块外部（1 行改动），消除致命的首次运行不写入缺陷。

### 4.2 P0-4 R7必修项（5 项，~15-20 行改动）

| 优先级 | 对应攻击点 | 文件路径 | 行号 | 改动内容 | 改动量 | 验证方法 |
|--------|-----------|---------|------|---------|--------|---------|
| **P0-致命** | ATK-1 + ATK-5 + ATK-6 | scripts/run_e2_ablation_discrimination.py + scripts/run_e4_temperature_analysis.py + scripts/run_e6_reliability_diagrams.py | L151 / L187 / L132 / L200 | 在 scripts 中 4 个 n_bins 函数添加与 calibration.py 一致的守卫。**推荐**：抽取 `_validate_n_bins(n_bins)` 公共函数到 `src/utils/calibration.py`，scripts 统一调用 | 8-12 行 | 实测 `fit_binned_temperature(n_bins=True)` / `quintile_edges(n_bins=True)` / `compute_reliability_bins(n_bins=10**18)` 均 raise ValueError |
| **P0-严重** | ATK-2 + ATK-4 | src/utils/calibration.py | L216 / L552 / L608 / L661 / L704 / L772 | 将 6 处守卫的 `n_bins > 10**6` 改为 `n_bins > 10**4`，错误信息中 `10**6` 改为 `10000`。降低上界至 10**4，单次 ece <50ms，compute_all_metrics 1000 次 bootstrap <50s | 6 行 | 实测 `ece(n_bins=10**4)` <50ms；`ece(n_bins=10**5)` raise ValueError |
| **P0-严重** | ATK-3 | tests/test_model.py | L213 | 将 `[0, -1, 1.5, "10"]` 扩充为 `[0, -1, 1.5, None, True, "10", 2.0, 10**18]`，与 L230 一致。**推荐**：抽取公共常量 `BAD_N_BINS` 供两个测试方法共用 | 1 行 | 运行 `pytest tests/test_model.py::test_brier_parts_n_bins_validation` 通过 |
| **P0-中等** | ATK-6 | docs/p0r6_fix_p0_4.md（修复报告） | §7 | 修复报告 §7"收敛声明"改为"P0-4 在 `src/utils/calibration.py` 范围内已收敛；scripts 范围由 R7-1 扩展修复" | 0 行代码 | 阅读修复报告确认声明范围限定 |
| **P0-轾微** | ATK-7 | src/utils/calibration.py | L216 / L552 / L608 / L661 / L704 / L772 | 若 R7-2 采用降低上界方案，错误信息改为 `"in [1, 10000]"`，此问题自动消失。若保留 10**6 上界，则改为 `f"... in [1, {10**6}] ..."` | 0-6 行 | grep 确认错误信息中无字面量 "10**6" |

**P0-4 R7 核心修复**：在 scripts 中 4 个 n_bins 函数添加守卫（建议抽取 `_validate_n_bins` 公共函数）+ 降低上界至 10**4。

### 4.3 P0-6+7 R7必修项

**无 R7 必修项**。P0-6+7 已收敛，仅剩 4 个轾微可选改进项（IMP-1/IMP-2/IMP-3 可择机实施，IMP-4 无需修复）。

### 4.4 R7必修项汇总

| P0 | 致命 | 严重 | 中等 | 轾微 | 必修项数 | 改动量 |
|----|------|------|------|------|---------|--------|
| P0-1 | 1 | 0 | 3 | 1 | 5 项 | ~11-14 行 |
| P0-4 | 1 | 2 | 1 | 1 | 5 项 | ~15-20 行 |
| P0-6+7 | 0 | 0 | 0 | 0 | 0 项 | 0 行 |
| **合计** | **2** | **2** | **4** | **2** | **10 项** | **~26-34 行** |

**R7 修复优先级排序**：
1. **P0-1 Attack-1**（致命，1 行）：eval_l2_shift.py 标记写入移到条件块外
2. **P0-4 ATK-1**（致命，8-12 行）：scripts 中 4 个 n_bins 函数添加守卫
3. **P0-4 ATK-2+ATK-4**（严重，6 行）：降低 n_bins 上界至 10**4
4. **P0-4 ATK-3**（严重，1 行）：brier_parts 测试扩充
5. **P0-1 Attack-3**（中等，2 行）：定义 SEED_STRATEGY_VERSION 常量
6. **P0-1 Attack-4+8**（中等，1 行）：cell["safety"]=0 改 pass
7. **P0-1 Attack-6+7**（中等，5-8 行）：safety_source 列
8. **P0-4 ATK-6**（中等，0 行代码）：修复报告声明限定
9. **P0-1 Attack-5**（轻微，2 行）：docstring 更新
10. **P0-4 ATK-7**（轾微，0-6 行）：错误信息改数值（若降上界则自动消失）

---

## 5. 收敛趋势分析

### 5.1 R1-R6 各轮攻击点数量与必修行数

| 轮次 | 致命 | 严重 | 中等 | 微 | 必修行数 | 收敛状态 |
|------|------|------|------|------|---------|---------|
| R1 | 1 | 9 | 1 | - | ~57 行 | 未收敛 |
| R2 | 1 | 9 | 1 | - | ~57 行 | 未收敛 |
| R3 | 1 | 6 | 3 | - | ~72 行 | 未收敛 |
| R4 | 0 | 5 | 2 | - | ~22-24 行 | 未收敛 |
| R5 | 0 | 4 | 3 | 9 | 10 行 | 未收敛 |
| **R6** | **2** | **4** | **6** | **7** | **~26-34 行** | **未收敛（反弹）** |
| R7（预期） | 0 | 0 | 0 | 7+ | 0 行 | 已收敛 |

### 5.2 趋势分析

- **致命攻击点**：R1-R3 存在 1 个（P0-6+7 CSV schema 不一致），R4-R5 已消除（0），**R6 反弹至 2 个**（P0-1 Attack-1 标记写入位置错误 + P0-4 ATK-1 scripts 守卫缺失）。R7 预期清零。
- **严重攻击点**：R1-R2 有 9 个，R3 降至 6 个，R4 降至 5 个，R5 降至 4 个，**R6 维持 4 个**（P0-1 Attack-2 + P0-4 ATK-2/3/4）。R7 预期清零。
- **中等攻击点**：R1-R2 有 1 个，R3 升至 3 个，R4 降至 2 个，R5 升至 3 个，**R6 升至 6 个**（P0-1 Attack-3/4/6/7 + P0-4 ATK-5/6）。R7 预期清零。
- **必修行数**：R1-R2 ~57 行，R3 ~72 行（上升因 P0-6+7 引入致命 bug），R4 ~22-24 行，R5 10 行，**R6 反弹至 ~26-34 行**。R7 预期清零。

### 5.3 R6 反弹原因分析

R6 出现收敛反弹（必修行数 10→26-34，致命 0→2），原因：

1. **P0-1 修复存在致命位置错误**：R6 修复本意是"无条件写入标记"，实际实现是"条件写入标记"（标记写入在 `if out_path.exists():` 条件块内）。这是**单行缩进错误**导致的意图与实现偏差。R5 Attack-1（严重）未实际修复，反而升级为 R6 Attack-1（致命）。

2. **P0-4 修复范围未覆盖 scripts**：R6 修复仅覆盖 `src/utils/calibration.py` 的 6 处守卫，忽略了 `scripts/` 目录下 4 个同源 n_bins 函数。修复报告"完全收敛"声明是**子集一致性误推为全局收敛**的逻辑断链。R5 A1/A3（严重）在 scripts 中未实际修复，反而升级为 R6 ATK-1（致命）。

3. **P0-6+7 修复正确**：R6 修复（L593 `n_ood=int(len(ood_probs))`）方向正确，与正常路径 L654 完全一致，成功清零 R5 的 1 个中等攻击点，仅剩 4 个轾微可选改进项。

**反弹模式**：R5→R6 的反弹集中在 P0-1 和 P0-4，根因是**修复实现缺陷**（位置错误 + 范围遗漏），而非修复方向错误。P0-6+7 的成功收敛证明修复方向正确时对抗流程有效推动收敛。

---

## 6. R7修复工作量估计

| P0 | R7 必修项 | 改动量 | 涉及文件数 | 工时估计 |
|----|----------|--------|-----------|---------|
| P0-1 | 5 项（1 致命 + 3 中等 + 1 轻微） | ~11-14 行 | 2（eval_l2_shift.py + run_e1a_l2_shift_full.py） | ~30 分钟 |
| P0-4 | 5 项（1 致命 + 2 严重 + 1 中等 + 1 轾微） | ~15-20 行 | 5（calibration.py + test_model.py + 3 个 scripts） | ~45 分钟 |
| P0-6+7 | 0 项（已收敛） | 0 行 | 0 | 0 |
| **合计** | **10 项** | **~26-34 行** | **7 个文件** | **~1.25 小时** |

**R7 修复关键路径**：
1. P0-1 Attack-1（1 行）：标记写入移到条件块外——**最高优先级，1 行改动消除致命缺陷**
2. P0-4 ATK-1（8-12 行）：scripts 中 4 个 n_bins 函数添加守卫——**建议抽取 `_validate_n_bins` 公共函数**
3. P0-4 ATK-2+ATK-4（6 行）：降低 n_bins 上界至 10**4——一并解决 5s 阻塞和 190 分钟阻塞
4. P0-4 ATK-3（1 行）：brier_parts 测试扩充——**建议抽取 `BAD_N_BINS` 公共常量**
5. P0-1 Attack-3/4/5/6/7/8（~10 行）：代码质量清理——DRY 常量 + 死代码消除 + safety_source 列 + docstring 更新

---

## 7. 关键发现

### 7.1 R6 P0-1 修复存在致命缺陷：标记写入位置在 if 条件块内

**事实**：`scripts/eval_l2_shift.py` L196 `existing[sk]["__seed_strategy__"] = "md5_v1"` 位于 L187 `if out_path.exists():` 条件块**内部**。首次运行时 `l2_shift_results.json` 不存在，L187 条件为 False，L188-197 整块跳过，L196 标记写入**永远不执行**。

**对比正确模式**：`scripts/run_e1a_l2_shift_full.py` L433 `existing[sk]["__seed_strategy__"] = SEED_STRATEGY_VERSION` 在条件块**外部**（无条件执行），两脚本模式不一致。

**下游影响**：`is_checkpoint_complete` L268 检查 `seed_data.get("__seed_strategy__") != SEED_STRATEGY_VERSION`，首次运行产出的结果无标记 → 返回 False → run_e1a 重跑。R6 修复对首次运行路径完全失效。

**根因**：单行缩进错误导致的意图与实现偏差。修复本意是"无条件写入标记"，实际实现是"条件写入标记"。

### 7.2 R6 P0-4 修复存在致命缺陷：修复范围未覆盖 scripts 中 4 个同源 n_bins 函数

**事实**：R6 修复仅覆盖 `src/utils/calibration.py` 的 6 处守卫，但代码库中 `scripts/` 目录下 3 个文件的 4 个 n_bins 函数**完全无守卫**：
- `scripts/run_e2_ablation_discrimination.py` `fit_binned_temperature` (L151) — 0 处守卫
- `scripts/run_e4_temperature_analysis.py` `quintile_edges` (L187) — 0 处守卫
- `scripts/run_e6_reliability_diagrams.py` `compute_reliability_bins` (L132) — 0 处守卫
- `scripts/run_e6_reliability_diagrams.py` `bootstrap_bin_accuracy_ci` (L200) — 0 处守卫

**实测验证**：
- `fit_binned_temperature(n_bins=True)`：NOT RAISED（bool 穿透）
- `quintile_edges(n_bins=True)`：NOT RAISED，返回退化 `[-inf, inf]` 边界
- `compute_reliability_bins(n_bins=10**18)`：MemoryError（OOM 未被守卫拦截）

**根因**：修复报告将"6 处守卫模式完全一致"（calibration.py 子集内）误推为"P0-4 可宣布完全收敛"（代码库全局），存在逻辑断链。

### 7.3 R6 P0-6+7 修复正确：n_ood=int(len(ood_probs)) 与正常路径完全一致

**事实**：`scripts/run_e5_inception_lite.py` L593 `n_ood=int(len(ood_probs))` 与正常路径 L654 `n_ood=int(len(ood_probs))` 写法完全一致，引用同一状态变量（已过 L532→L549→L574→L579 完整截断+过滤+归一化管线）。

**反方 7 维度全覆盖攻击仅发现 4 个轾微攻击点**，反反方独立排查 9 项潜在高严重度风险均不存在。R6 修复成功清零 R5 终审裁定的 1 个中等攻击点（Attack-4+5），符合 R5 终审"R6 修复后可完全收敛"预期。

### 7.4 R6 修复 10 行改动的质量评估

| P0 | R6 改动量 | 正确性 | 问题 |
|----|----------|--------|------|
| P0-1 | 4 行 | ❌ 4 行均有问题 | L196 标记写入位置错误（致命）+ L196 硬编码 "md5_v1"（DRY 违反）+ L281 cell["safety"]=0 死代码 + L281 谓词函数副作用 |
| P0-4 | 5 行 | ⚠️ 部分正确 | calibration.py 6 处守卫正确，但未覆盖 scripts 4 个同源函数（致命）+ 上界 10**6 过大（严重）+ brier_parts 测试未扩充（严重） |
| P0-6+7 | 1 行 | ✅ 完全正确 | L593 n_ood=int(len(ood_probs)) 与正常路径 L654 完全一致 |
| **合计** | **10 行** | **2/3 有缺陷** | P0-6+7 的 1 行正确，P0-1 的 4 行有致命位置错误，P0-4 的 5 行仅覆盖 calibration.py 未覆盖 scripts |

**关键结论**：R6 修复 10 行改动中，仅 P0-6+7 的 1 行完全正确（10% 正确率）。P0-1 和 P0-4 的修复均存在致命缺陷，需 R7 修复。

---

## 8. 对R7的指导建议

### 8.1 P0-1 R7 修复建议

1. **将 eval_l2_shift.py L196 标记写入移到 L185 后（条件块外），无条件写入**：
   ```python
   all_results[f"seed{seed}"] = seed_results
   all_results[f"seed{seed}"]["__seed_strategy__"] = SEED_STRATEGY_VERSION  # 无条件写入
   out_path = run_dir / "l2_shift_results.json"
   if out_path.exists():
       existing = json.loads(out_path.read_text(encoding="utf-8"))
       sk = f"seed{seed}"
       if sk not in existing:
           existing[sk] = {}
       existing[sk].update(seed_results)
       existing[sk]["__seed_strategy__"] = SEED_STRATEGY_VERSION  # 续传也写入
       all_results = existing
   out_path.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8")
   ```

2. **定义 SEED_STRATEGY_VERSION 常量替代硬编码 "md5_v1"**：在 eval_l2_shift.py 顶部定义 `SEED_STRATEGY_VERSION = "md5_v1"`，或提取到 `src/data/l2_shifts.py` 共享模块，两脚本统一导入。

3. **cell["safety"]=0 改为 pass 消除死代码**：在 run_e1a_l2_shift_full.py L280-281，将 `if "safety" not in cell: cell["safety"] = 0` 改为 `if "safety" not in cell: pass`，消除死代码（Attack-4）和谓词函数副作用（Attack-8）。

4. **safety_source 列**：在 780 详细 CSV 增加 `safety_source` 列（"computed"/"default"），明确标注每个 cell 的 safety 来源，消除聚合偏置（Attack-6）和语义偏移（Attack-7）。

5. **更新 docstring**：将 L254 docstring 和 L277 注释中 safety 标注为可选字段，消除自相矛盾（Attack-5）。

### 8.2 P0-4 R7 修复建议

1. **在 scripts 中 4 个 n_bins 函数添加守卫**：
   - **推荐方案**：抽取 `_validate_n_bins(n_bins)` 公共函数到 `src/utils/calibration.py`，scripts 统一调用，避免守卫模式重复散布。
   ```python
   # src/utils/calibration.py 新增公共函数
   def _validate_n_bins(n_bins) -> int:
       """n_bins 参数验证公共守卫，供 calibration.py 和 scripts 统一调用"""
       if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1 or n_bins > 10**4:
           raise ValueError(f"n_bins must be a positive integer in [1, 10000], got {n_bins!r}")
       return int(n_bins)
   ```
   - 在 4 个 scripts 函数开头调用 `_validate_n_bins(n_bins)`。

2. **降低上界至 10**4：将 `calibration.py` 中 6 处守卫的 `n_bins > 10**6` 改为 `n_bins > 10**4`，错误信息中 `10**6` 改为 `10000`。理由：典型 ECE 使用 n_bins=10-20，极端场景 n_bins=1000 已罕见；上界 10**4 时单次 ece <50ms，`compute_all_metrics(n_bins=10**4)` 1000 次 bootstrap <50s，完全可接受。

3. **扩充 brier_parts 测试列表**：将 `tests/test_model.py` L213 的 `[0, -1, 1.5, "10"]` 扩充为 `[0, -1, 1.5, None, True, "10", 2.0, 10**18]`，与 L230 一致。**推荐**：抽取公共常量 `BAD_N_BINS = [0, -1, 1.5, None, True, "10", 2.0, 10**18]` 供两个测试方法共用，避免未来再次不一致。

4. **修复报告声明限定**：修复报告 §7"收敛声明"改为"P0-4 在 `src/utils/calibration.py` 范围内已收敛；scripts 范围由 R7 扩展修复"。

### 8.3 P0-6+7 R7 修复建议

**无需 R7**。P0-6+7 已收敛，4 个轾微改进项可择机实施：

| 编号 | 对应攻击 | 改进内容 | 文件:行号 | 改动量 |
|------|---------|---------|----------|--------|
| IMP-1 | Attack-3 | 在 `_make_transfer_result` docstring 显式声明 n_ood 语义 | run_e5_inception_lite.py L180-190 | 2 行注释 |
| IMP-2 | Attack-5 | ood-empty 路径显式传 `n_ood=int(len(ood_probs))` | run_e5_inception_lite.py L606 | 1 行 |
| IMP-3 | Attack-1 | CSV 头注释声明 skipped 行 n_ood 语义 | run_e5_inception_lite.py L694 | 1 行注释 |
| IMP-4 | Attack-7 | 无需修复（error 字段已提供区分能力） | — | 0 行 |

IMP-1/IMP-2/IMP-3 可一次性合并为 4 行改动，消除 3 个轾微攻击点。

---

## 9. 对抗透明性记录

### 9.1 被驳回的反方攻击及驳回理由

**R6 轮无被驳回的反方攻击**。三份反反方审查报告中：
- P0-1：8 个攻击点全部成立（0 驳回）
- P0-4：7 个攻击点中 6 个完全成立 + 1 个部分成立（0 驳回，ATK-5 部分成立因 n_bins=True 反例错误——实际为 bool 穿透而非 TypeError，但广义问题存在）
- P0-6+7：4 个攻击点全部成立（0 驳回）

**说明**：R6 反方攻击质量高，无过度攻击或误报。所有攻击点均经反反方逐行代码实证确认成立。

### 9.2 正方修补的所有点及修补方式

| P0 | R6 修补点 | 修补方式 | 验证状态 |
|----|---------|---------|---------|
| P0-1 | eval_l2_shift.py L196 标记写入 | 添加 `existing[sk]["__seed_strategy__"] = "md5_v1"` | ❌ **位置错误**——在 `if out_path.exists():` 条件块内，首次运行不写入（Attack-1 致命） |
| P0-1 | run_e1a_l2_shift_full.py L280-281 safety 检查放宽 | `if "safety" not in cell: cell["safety"] = 0` | ⚠️ **部分修复**——return False 改为不返回（修复重跑），但 cell["safety"]=0 是死代码（Attack-4），语义偏移（Attack-7），聚合偏置（Attack-6） |
| P0-4 | calibration.py 6 处守卫增加 bool 排除 + 上界 10**6 | `if isinstance(n_bins, bool) or not isinstance(n_bins, (int, np.integer)) or n_bins < 1 or n_bins > 10**6: raise ValueError(...)` | ⚠️ **calibration.py 内正确**，但未覆盖 scripts 4 个同源函数（ATK-1 致命）+ 上界 10**6 过大（ATK-2/4 严重） |
| P0-4 | test_model.py L230 测试扩充 | `[0, 1.5, None]` → `[0, -1, 1.5, None, True, "10", 2.0, 10**18]` | ⚠️ **L230 正确**，但 L213 brier_parts 测试未扩充（ATK-3 严重） |
| P0-6+7 | run_e5_inception_lite.py L593 n_ood 修复 | `n_ood=0` → `n_ood=int(len(ood_probs))` | ✅ **完全正确**——与正常路径 L654 完全一致，ood_probs 变量流完整无误 |

### 9.3 R6 轮引入的新问题

| P0 | 新问题 | 引入原因 | 严重度 |
|----|--------|---------|--------|
| P0-1 | 标记写入位置错误，首次运行不写入 | R6 修复代码放置在 `if out_path.exists():` 条件块内（单行缩进错误） | P0-致命 |
| P0-1 | 硬编码 "md5_v1" 引入第二处定义 | R6 修复未使用常量引用，DRY 违反恶化 | P0-中等 |
| P0-1 | cell["safety"]=0 死代码 + 谓词函数副作用 | R6 修复在谓词函数中修改 dict 内容，修改丢失 | P0-中等 + P0-轻微 |
| P0-1 | safety 默认 0 向下偏置聚合 + "从未计算"等同"未改善" | R6 修复未区分 safety 来源，语义偏移 | P0-中等 + P0-中等 |
| P0-4 | scripts 中 4 个 n_bins 函数无守卫 | R6 修复范围仅覆盖 calibration.py，遗漏 scripts 同源函数 | P0-致命 |
| P0-4 | 上界 10**6 对 O(n_bins) 循环过大 | R6 修复未考虑实现复杂度，上界与 O(n_bins) 不匹配 | P0-严重 |
| P0-4 | brier_parts 测试覆盖退步未完全修复 | R6 修复仅扩充 L230，遗漏 L213 | P0-严重 |

---

## 10. 置信度评估

**置信度：高**

理由：
- 反方在全部攻击维度上均经反反方逐行代码验证 + 实际运行 Python 验证，无稻草人论证、无臆测
- 3 份反反方审查报告均基于代码实测（read/grep 工具直接读取文件内容 + 实际运行 Python 确认代码行为），证据扎实
- R6 轮核心缺陷的正确性经反反方独立验证确认（P0-1 Attack-1 标记写入位置错误、P0-4 ATK-1 scripts 守卫缺失、P0-6+7 修复正确）
- 遗留缺陷的严重度评估经反反方修正后合理（P0-4 ATK-5 部分成立——n_bins=True 反例错误但广义问题存在）
- 终审独立逐条审查，与反反方裁决高度一致（19 个攻击点中 18 个完全成立 + 1 个部分成立，0 纠正）
- 对抗过程体现了实质性：反方发现真实问题（特别是 P0-1 Attack-1 标记写入位置错误、P0-4 ATK-1 scripts 守卫缺失），反反方验证并修正定级，终审独立裁决

**残余疑点**：
- P0-1 Attack-1 的 R7 修复（标记写入移到条件块外）需确认首次运行 + 续传 + 多 seed 三种路径均写入标记
- P0-4 ATK-1 的 R7 修复（scripts 添加守卫）需确认 4 个 scripts 函数的守卫模式与 calibration.py 完全一致
- P0-4 ATK-2 的 R7 修复（降低上界至 10**4）需确认上界值是否覆盖所有合理分箱需求（典型 n_bins=10-20，极端 n_bins=1000）
- P0-1 Attack-6+7 的 R7 修复（safety_source 列）需确认 CSV 消费者能正确处理新列

这些残余疑点可在 R7 轮修复后通过轻量验证解决，不影响当前裁决的置信度。

---

## 11. 已收敛 P0 状态确认

### 11.1 P0-3（E2 消融分箱）

- **R4 判定**：✅ 通过
- **R5/R6 状态**：无新攻击
- **终审确认**：✅ **已收敛**。仅剩 3 个 P0-轻微可选改进（B1/B2/B3，均为 R3 遗留）。

### 11.2 P0-8（ECE 加权术语）

- **R4 判定**：✅ 通过
- **R5/R6 状态**：无新攻击
- **终审确认**：✅ **已收敛**。仅剩 3 个 P0-轻微/P0-轾微可选改进（B1/B2/B3，均为 R3 遗留）。

### 11.3 P0-6+7（CSV schema/OOM 备选）

- **R6 判定**：✅ 通过（本轮新收敛）
- **终审确认**：✅ **已收敛**。仅剩 4 个 P0-轾微可选改进（IMP-1/IMP-2/IMP-3/IMP-4）。

---

## 12. 对R6轮对抗质量的评价

### 12.1 反方攻击质量

**真攻击率**：19/19 = 100%（经终审独立校准后，18 个完全成立 + 1 个部分成立，0 个伪攻击）

| P0 | 反方攻击数 | 真攻击数 | 真攻击率 | 严重度校准准确性 |
|----|-----------|---------|---------|----------------|
| P0-1 | 8 | 8 | 100% | **校准准确**——致命 1（Attack-1 标记位置错误）、严重 1（Attack-2 验证不全）、中等 4、轻微 2，均经代码实证确认 |
| P0-4 | 7 | 7（6 完全 + 1 部分） | 100% | **校准准确**——致命 1（ATK-1 scripts 守卫缺失）、严重 3、中等 2、轾微 1，ATK-5 的 n_bins=True 反例有误但广义问题成立 |
| P0-6+7 | 4 | 4 | 100% | **校准准确**——4 个轾微攻击点均事实成立，严重度正确归类为轾微 |
| **合计** | **19** | **19** | **100%** | **整体校准准确**，无高估或低估 |

**反方攻击质量总评**：**高**。
- **优点**：所有攻击点均经代码实证确认，无过度攻击或误报。反例构造具体可执行，代码证据准确，修复建议可行。反方代理成功发现了 R6 修复的两个致命缺陷（P0-1 标记写入位置错误 + P0-4 scripts 守卫缺失），避免了 R5 Attack-1 和 R5 A1/A3 被错误关闭。
- **瑕疵**：P0-4 ATK-5 的 `n_bins=True` 反例**错误**——声称抛 TypeError，实际为 bool 穿透（True+1=2 静默工作）。反方未实际执行此反例，仅从 numpy 文档推测。此瑕疵不影响 ATK-5 的广义结论（异常类型不一致确实存在），但降低了该攻击点的可信度。

### 12.2 反反方审查质量

**裁决准确性**：经终审独立校准，反反方裁决**整体准确**。

| P0 | 反反方裁决数 | 终审纠正数 | 裁决准确率 |
|----|------------|-----------|-----------|
| P0-1 | 8 | 0 | 100% |
| P0-4 | 7 | 0 | 100% |
| P0-6+7 | 4 | 0 | 100% |
| **合计** | **19** | **0** | **100%** |

**反反方审查质量总评**：**高**。裁决准确率 100%，严重度校准客观，反驳理由基于代码实测，无稻草人论证。特别是：
- P0-1 Attack-1：逐行阅读 eval_l2_shift.py L185-198，控制流追踪首次运行路径，确认标记写入在条件块内。
- P0-4 ATK-1：逐文件逐函数读取 4 个 scripts 函数源代码，确认 0 处守卫。
- P0-6+7：独立排查 9 项潜在高严重度风险均不存在，确认 R6 修复正确。

### 12.3 对抗流程是否有效发现了真实缺陷

**有效性评估**：✅ **有效**。

对抗流程成功发现了 2 个致命缺陷 + 4 个严重缺陷：
1. **P0-1 Attack-1**（致命）：eval_l2_shift.py 标记写入在 `if out_path.exists():` 条件块内，首次运行不写入。这是 R6 修复的**单行缩进错误**导致的意图与实现偏差。
2. **P0-4 ATK-1**（致命）：scripts 中 4 个 n_bins 函数完全无守卫，A1 bool 穿透和 A3 OOM 在 scripts 中未修复。这是 R6 修复的**范围遗漏**。
3. **P0-4 ATK-2/4**（严重）：上界 10**6 对 O(n_bins) Python 循环实现过大，合法输入导致 5s-19.5 小时阻塞。
4. **P0-4 ATK-3**（严重）：brier_parts 测试 L213 未扩充，A1/A3 对 brier_parts 无测试保护。
5. **P0-1 Attack-2**（严重）：修复报告验证未覆盖首次运行路径，"Attack-1 关闭✅"是错误声明。
6. **P0-1 Attack-6/7**（中等）：safety 默认 0 向下偏置聚合 + "从未计算"等同"TS 未改善"。

**对抗流程的价值**：
- 反方从 7 个维度全覆盖攻击，发现了正方修复的致命盲区（标记写入位置错误 + scripts 守卫缺失）。
- 反反方逐行代码验证 + 实际运行 Python，确保裁决基于事实而非臆测。
- 终审独立交叉对照，校准严重度，确保不盲从任何一方。
- P0-6+7 的成功收敛证明修复方向正确时对抗流程有效推动收敛。

**对抗流程的不足**：
- R6 出现收敛反弹（必修行数 10→26-34），表明 R6 修复质量低于 R5。
- P0-4 ATK-5 的 n_bins=True 反例错误（反方未实际执行），增加了反反方的校准负担。
- 但这些不足不影响对抗流程的整体有效性——真实缺陷被发现了，这就是对抗的核心价值。

---

## 13. 终审声明

本报告由 R6-Phase4 终审代理独立撰写，综合了 3 份 R6 反方攻击报告和 3 份 R6 反反方审查报告的全文内容，并参考 R5 终审裁决，对每个 P0 项给出了"通过 / 不通过"的独立裁决。判定标准为 CBM 期刊（IF~7）审稿要求：代码正确性无懈可击、统计方法严谨、跨实验一致性声明透明、隐含假设显式化。

**关键发现**：
- R6 轮核心修复方向正确，但 P0-1 和 P0-4 的修复实现存在致命缺陷
- P0-1：标记写入位置错误（单行缩进错误），首次运行不写入——R5 Attack-1（严重）升级为 R6 Attack-1（致命）
- P0-4：修复范围未覆盖 scripts 中 4 个同源 n_bins 函数——R5 A1/A3（严重）升级为 R6 ATK-1（致命）
- P0-6+7：修复完全正确，成功收敛（中等→轾微）
- R6 修复 10 行改动中，仅 P0-6+7 的 1 行完全正确（10% 正确率）
- R6 出现收敛反弹（必修行数 10→26-34，致命 0→2），但反弹集中在 P0-1 和 P0-4，根因是修复实现缺陷而非修复方向错误

**最终判定**：R6 轮 3 个 P0 修复中，**P0-1 和 P0-4 不通过，P0-6+7 通过**。R7 必修 10 项 ~26-34 行改动 7 个文件，工时约 1.25 小时（含验证）。**预期 R7 轮可完全收敛**——全部 5 个 P0 项的致命/严重/中等攻击点均可清零，仅剩轻微/轾微可选建议项。

**R7 修复优先级排序**：

1. **P0-1 Attack-1**（致命，1 行）：eval_l2_shift.py 标记写入移到条件块外。消除首次运行不写入缺陷。
2. **P0-4 ATK-1**（致命，8-12 行）：scripts 中 4 个 n_bins 函数添加守卫（建议抽取 `_validate_n_bins` 公共函数）。消除 scripts 中 bool 穿透 + OOM。
3. **P0-4 ATK-2+ATK-4**（严重，6 行）：降低 n_bins 上界至 10**4。消除 5s 阻塞和 190 分钟阻塞。
4. **P0-4 ATK-3**（严重，1 行）：brier_parts 测试 L213 扩充为 8 个非法值。消除测试覆盖退步。
5. **P0-1 Attack-3/4/5/6/7/8**（中等+轻微，~10 行）：代码质量清理——DRY 常量 + 死代码消除 + safety_source 列 + docstring 更新。

**预期 R7 轮后是否可宣布全部 P0 收敛**：**是**。R7 修复后：
- P0-1：致命/严重/中等攻击点清零，仅剩 backlog 改进项
- P0-3：已收敛，仅剩 3 个 P0-轻微可选改进
- P0-4：致命/严重/中等攻击点清零，仅剩 1 个 P0-轾微选修（ATK-7，若降上界则自动消失）
- P0-6+7：已收敛，仅剩 4 个 P0-轾微可选改进
- P0-8：已收敛，仅剩 3 个 P0-轻微/P0-轾微可选改进

**全部 5 个 P0 项的致命/严重/中等攻击点均可清零**，仅剩轻微/轾微可选建议项。按收敛标准，可宣布全部 P0 收敛。
