# R4反反方审查报告：P0-3

## 审查摘要
- 反方攻击报告：docs/p0r4_attack_p0_3.md
- 审查文件：scripts/run_e2_ablation_discrimination.py
- 攻击点总数：3（B1 + B2 + B3，反方自评均为 P0-轻微）
- 成立攻击：2（B1、B2）
- 部分成立攻击：1（B3）
- 不成立攻击：0
- 需R5修补项：0（均为P0-轻微可选改进，非阻塞）

**总体判定**：反方攻击报告质量高，3 个攻击点均基于代码实测，无稻草人论证、无臆测。但所有攻击点均为 P0-轻微级别，反方自身亦承认"无当前 bug"或"上下文可推断意图"。R4 修复完全消除了 R3 终审裁决的 2 个必修项（A1 P0-严重 + A3 P0-中等），未引入任何 P0-严重或 P0-中等新问题。**P0-3 已收敛。**

---

## 逐条审查

### Attack-1 (B1): 负条件 `!= "raw"` 可维护性脆弱

**反方指控**：L503 `T_global if stage_name != "raw" else np.nan` 使用负向枚举（排除 raw），隐含假设"所有非 raw 的 stage 都使用 TS"。该假设当前成立但脆弱——若未来新增不使用全局 TS 的 stage（如 `"binned_only"`），负条件会对其错误报告 T_global。对比 L504-507 的正条件风格（`"binned" in stage_name`、`"threshold" in stage_name`），L503 风格不一致。

**判定**：成立（P0-轻微）

**理由**：

经逐行代码验证，反方指控的代码事实全部属实：

1. **L503 确为负条件**（源文件 L503）：
   ```python
   "T_global": T_global if stage_name != "raw" else np.nan,
   ```

2. **L504-507 确为正条件**（源文件 L504-507）：
   ```python
   "T_binned_mean": np.mean(T_binned) if "binned" in stage_name else np.nan,
   "T_binned_min": np.min(T_binned) if "binned" in stage_name else np.nan,
   "T_binned_max": np.max(T_binned) if "binned" in stage_name else np.nan,
   "threshold_norm": float(np.linalg.norm(tau)) if "threshold" in stage_name else 0.0,
   ```

3. **风格不一致客观存在**：L503 用负条件（`!= "raw"`），紧邻的 L504-507 用正条件（`"binned" in` / `"threshold" in`）。同一 dict 字面量内 5 个条件表达式采用两种不同风格，确实影响可读性和可维护性。

4. **未来风险真实存在**：当前 4 个 stage（L493-497 硬编码）中非 raw 的 3 个确实都使用 TS。但若未来新增 stage（如 `"binned_only"` 不经全局 TS），`!= "raw"` 会对其错误报告 T_global——一个该 stage 未使用的参数。正条件 `stage_name in ("stage1_ts", "stage2_ts_binned", "stage3_ts_binned_threshold")` 或 `stage_name.startswith("stage")` 则天然免疫此风险。

5. **当前无 bug**：反方明确承认"当前 4 个 stage 下逻辑正确，仅为未来可维护性风险。无当前 bug。"——此判定准确。在当前代码状态下，`!= "raw"` 与 `stage_name in ("stage1_ts", "stage2_ts_binned", "stage3_ts_binned_threshold")` 完全等价。

**严重程度确认**：P0-轻微。无当前功能 bug，仅为代码风格一致性和未来可维护性风险。不阻塞 R5。

**若成立，修补方案**：

| 文件 | 行号 | 改动内容 | 改动量 |
|------|------|---------|--------|
| scripts/run_e2_ablation_discrimination.py | L503 | `stage_name != "raw"` → `stage_name in ("stage1_ts", "stage2_ts_binned", "stage3_ts_binned_threshold")` | 1行 |

修补后代码：
```python
"T_global": T_global if stage_name in ("stage1_ts", "stage2_ts_binned", "stage3_ts_binned_threshold") else np.nan,
```

此修补使 L503 与 L504-507 风格一致（均为正条件），且未来新增 stage 时需显式加入此元组，强制开发者思考该 stage 是否使用 TS，消除静默误报风险。

**备注**：此修补为可选改进（P0-轻微），非 R5 必修项。当前代码功能正确，仅在未来扩展时才有风险。

---

### Attack-2 (B2): "E4 为 binned-only" 措辞不精确

**反方指控**：L36 docstring 写 "E4 为 binned-only（仅分箱温度，无前置全局 TS）"，但 E4 脚本实际同时拟合了 global-T（E4 L495 `fit_global_T`）和 binned-T（E4 L522 `fit_binned_T`）。"binned-only" 未限定"binned-T 组件"，可被审稿人误读为"E4 脚本只有 binned-T，无 global T"。对比 L35 对 E2 的描述限定了"Stage2/3"，L36 对 E4 未限定组件，不对称。

**判定**：成立（P0-轻微）

**理由**：

经独立读取 E4 源文件验证，反方指控的代码事实全部属实：

1. **E4 确实拟合了 global T**（E4 L495）：
   ```python
   T_global, fit_status = fit_global_T(cal_probs, cal_labels)
   ```
   `fit_global_T` 定义于 E4 L357-367，对 `cal_probs` 拟合单一全局温度 T，用于独立比较（L500-502 `id_rel_global` vs `id_rel_raw`）。

2. **E4 确实拟合了 binned-T**（E4 L522）：
   ```python
   T_per_bin, bin_edges, bin_records = fit_binned_T(cal_probs, cal_labels, n_bins=N_BINS)
   ```
   `fit_binned_T` 定义于 E4 L370-412，对 `cal_probs`（raw，无前置 TS）按熵分箱拟合每箱 T。

3. **E4 的 binned-T 不经过 global T**：L522 的 `fit_binned_T` 直接接收 `cal_probs`（raw），不接收 `apply_global_T(cal_probs, T_global)`。E4 的 global T（L495）和 binned-T（L522）是两条独立路径，非组合关系。

4. **L36 措辞确实不精确**（源文件 L36）：
   ```
   E4 为 binned-only（仅分箱温度，无前置全局 TS）。
   ```
   字面含义："E4 为 binned-only"——可误读为"E4 脚本整体只有 binned-T"。
   上下文意图："E4 的 binned-T 组件为 binned-only"——指 binned-T 不经前置 TS。

5. **L35 vs L36 不对称**（源文件 L35-36）：
   ```
   (2) 结构不同：E2 Stage2/3 为 TS+binned（先全局 TS 再分箱温度），
       E4 为 binned-only（仅分箱温度，无前置全局 TS）。
   ```
   L35 限定了"E2 Stage2/3"（具体 stage），L36 未限定"E4 的 binned-T"（具体组件），确实不对称。

6. **审稿人误读风险真实**：若审稿人仅读 L36 不读 E4 代码，可能误以为 E4 完全没有全局 T 拟合，实际 E4 有（用于独立比较）。虽然上下文（L32-33 讨论"binned-T 分箱变量"）可推断意图，但措辞不精确客观存在。

**严重程度确认**：P0-轻微。上下文可推断意图（对比的是 binned-T 实现），但措辞不精确。不影响代码功能，不影响实验结果，仅为 docstring 表述问题。

**若成立，修补方案**：

| 文件 | 行号 | 改动内容 | 改动量 |
|------|------|---------|--------|
| scripts/run_e2_ablation_discrimination.py | L36 | `E4 为 binned-only（仅分箱温度，无前置全局 TS）` → `E4 的 binned-T 为 binned-only（不经过前置全局 TS；E4 另有独立 global-T 用于比较）` | 1行 |

修补后 docstring（L35-36）：
```
    (2) 结构不同：E2 Stage2/3 为 TS+binned（先全局 TS 再分箱温度），
        E4 的 binned-T 为 binned-only（不经过前置全局 TS；E4 另有独立 global-T 用于比较）。
```

此修补：
- 限定"binned-T 组件"（与 L35 的"Stage2/3"对称）
- 显式说明"E4 另有独立 global-T"（消除"E4 无 global T"的误读）
- 保留"不经过前置全局 TS"的核心论据

**备注**：此修补为可选改进（P0-轻微），非 R5 必修项。当前 docstring 在上下文中可正确理解，仅为精确性改进。

---

### Attack-3 (B3): "非同构" 论证依赖不对称比较

**反方指控**：L37 "两者参数空间非嵌套亦非同构" 中"非同构"论证不严谨——E2 Stage2 用 6 参数空间 {T, T_1..T_5}，E4 binned-T 用 5 参数空间 {T_1..T_5}，6≠5 → 非同构。但这是不对称比较：E4 整体也拟合了 global T（E4 L495），E4 全部参数也是 6 个 {T_global, T_1..T_5}。对称比较则 6=6 → 同构。"非嵌套"已充分且必要，"非同构"不必要且论证不严谨。建议删除"亦非同构"。

**判定**：部分成立（P0-轻微）

**理由**：

反方的数学分析部分正确，但存在一个关键遗漏——"同构"在参数空间语境下不仅指维度相同，更指结构保持的双射。需分层分析：

**1. 反方正确的部分**：

- E2 Stage2 参数空间：{T, T_1..T_5} = (R⁺)⁶（6 参数）✓
- E4 binned-T 参数空间：{T_1..T_5} = (R⁺)⁵（5 参数）✓
- E4 全部参数：{T_global, T_1..T_5} = (R⁺)⁶（6 参数，E4 L495 + L522）✓

L37 的"非同构"若仅基于维度计数（6 vs 5），确实是不对称比较（E2 全部 6 参数 vs E4 binned-T 5 参数，忽略了 E4 的 global T）。对称比较（E2 全部 6 vs E4 全部 6）维度相同。反方此点成立。

**2. 反方遗漏的部分**：

"同构"（isomorphism）在参数空间/模型空间语境下，不仅要求维度相同，更要求存在**结构保持的双射**。即使 E2 和 E4 全部参数均为 6 维，两者的参数**作用方式**不同：

- E2 Stage2：T 先作用于 p 得 TS(p, T)，然后 T_1..T_5 作用于 TS(p, T) 的分箱 → **顺序组合**（T_1..T_5 的输入依赖 T 的输出）
- E4：T_global 和 T_1..T_5 各自独立拟合于 raw p → **独立并行**（T_1..T_5 的输入不依赖 T_global）

因此，即使维度同为 6，参数空间的**代数结构**不同（顺序组合 vs 独立并行），严格意义上确实非同构。反方将"同构"仅理解为"维度相同"是过度简化。

**3. 但反方的核心建议仍然合理**：

尽管"非同构"在结构意义上可辩护，但 L37 的文本**未展开此结构论证**，仅断言"非同构"。审稿人读 L37 最自然的理解是"维度不同 → 非同构"，而这正是反方指出的不对称比较。因此：

- "非同构"的**结论**可辩护（结构不同）
- "非同构"的**论证呈现**不严谨（未说明是结构非同构而非维度非同构）
- "非嵌套"已**充分且必要**（E2 的 T_1..T_5 拟合在 TS(p) 上，E4 的 T_1..T_5 拟合在 p 上 → 同名不同对象 → 参数空间非嵌套 → 边际贡献无意义）

保留"亦非同构"增加了一个**可辩护但呈现不严谨**的附加论据，删除它**不削弱结论**且**消除论证风险**。反方建议删除"亦非同构"是合理的简化。

**4. 严重程度确认**：P0-轻微。结论"不可作边际贡献解释"正确（"非嵌套"已充分），"非同构"的论证呈现不严谨但不影响结论。审稿人若仔细检查"非同构"声明可能质疑比较的不对称性，但不会推翻核心结论。

**若成立，修补方案**：

提供两个可选方案，推荐方案 A（更简洁）：

| 方案 | 文件 | 行号 | 改动内容 | 改动量 |
|------|------|------|---------|--------|
| A（推荐） | scripts/run_e2_ablation_discrimination.py | L37 | `两者参数空间非嵌套亦非同构，故 ΔReliability 不可作边际贡献解释。` → `两者参数空间非嵌套（E2 的 T_1..T_5 拟合在 TS(p) 上，E4 的 T_1..T_5 拟合在 p 上，同名不同对象），故 ΔReliability 不可作边际贡献解释。` | 1行 |
| B（保留非同构但补论证） | scripts/run_e2_ablation_discrimination.py | L37 | `两者参数空间非嵌套亦非同构` → `两者参数空间非嵌套（拟合对象不同）亦非同构（E2 顺序组合 vs E4 独立并行，代数结构不同）` | 1行 |

**推荐方案 A**：删除"亦非同构"，仅保留"非嵌套"并展开其论证。理由：
1. "非嵌套"是充分且必要的论据，展开后论证更清晰
2. 删除"非同构"消除不对称比较的论证风险
3. 改动更简洁，不引入新的论证负担

**备注**：此修补为可选改进（P0-轻微），非 R5 必修项。当前结论正确，仅为论证严谨性改进。

---

## 总结

### 需R5修复的必修项清单（按优先级排序）

**无。**

R4 修复已完全消除 R3 终审裁决的 2 个必修项：
- ✅ A1（P0-严重）：Fix-1 将 T_global 报告条件从 `stage_name in ("stage1_ts",)` 改为 `stage_name != "raw"`，使 stage1/2/3 均报告 T_global，与 docstring L17 的 Θ_1 ⊂ Θ_2 ⊂ Θ_3（均含 T）一致
- ✅ A3（P0-中等）：Fix-2 在 L32-37 补全 E4 不可比归因，增加"结构不同（TS+binned vs binned-only）"说明

R4 引入的 3 个新攻击点（B1/B2/B3）均为 P0-轻微，无当前功能 bug，仅为代码风格和 docstring 措辞改进，非阻塞。

### 可选改进项（P0-轻微，非阻塞）

| 优先级 | 攻击点 | 文件 | 行号 | 改动内容 | 改动量 | 理由 |
|--------|--------|------|------|---------|--------|------|
| P0-轻微 | B1 | scripts/run_e2_ablation_discrimination.py | L503 | `!= "raw"` → `in ("stage1_ts", "stage2_ts_binned", "stage3_ts_binned_threshold")` | 1行 | 风格一致性 + 未来可维护性 |
| P0-轻微 | B2 | scripts/run_e2_ablation_discrimination.py | L36 | `E4 为 binned-only` → `E4 的 binned-T 为 binned-only（不经过前置全局 TS；E4 另有独立 global-T 用于比较）` | 1行 | 措辞精确性 + 消除误读 |
| P0-轻微 | B3 | scripts/run_e2_ablation_discrimination.py | L37 | `非嵌套亦非同构` → `非嵌套（E2 的 T_1..T_5 拟合在 TS(p) 上，E4 的 T_1..T_5 拟合在 p 上，同名不同对象）` | 1行 | 论证严谨性 + 消除不对称比较 |

**三项可选改进合计**：3 行改动，1 个文件。可在 R5 轮一并处理，工时约 5 分钟。

### 可关闭的攻击点及理由

**无可关闭的攻击点**——3 个攻击点均成立或部分成立，但均为 P0-轻微可选改进，不阻塞收敛。

需特别说明的是，反方攻击报告本身质量高，无稻草人论证：
- B1 基于代码风格不一致的客观事实（L503 负条件 vs L504-507 正条件）
- B2 基于代码事实（E4 L495 确实拟合了 global T）
- B3 基于数学分析（6 vs 5 不对称比较）

反方自身亦诚实承认所有攻击点均为 P0-轻微，且 R4 修复"完全达成 R3 终审裁决的 2 个必修项"。

### 对R4修复质量的总体评价

**R4 修复质量：高。P0-3 已收敛。**

| 评价维度 | 评分 | 说明 |
|---------|------|------|
| R3 必修项消除 | ✅ 完全达成 | A1（P0-严重）+ A3（P0-中等）均完全消除 |
| 新引入问题严重度 | ✅ 仅 P0-轻微 | 3 个新攻击点均为 P0-轻微，无 P0-严重/P0-中等 |
| 代码功能正确性 | ✅ 无影响 | Fix-1 改报告条件不影响计算逻辑；Fix-2 改 docstring 不影响代码 |
| 下游兼容性 | ✅ 无影响 | grep 确认无下游 .py 脚本读取 ablation_ts_components.csv，T_global 列值变化无下游依赖 |
| 收敛状态 | ✅ 已收敛 | P0-严重/P0-中等/P0-致命攻击点清零，仅剩 3 个 P0-轻微可选改进 |

**与 R3 终审判定的对比**：

R3 终审（`p0r3_final_verdict.md` §2.3）要求 R4 修复 2 项：
1. [P0-严重] A1: T_global 报告条件 → **Fix-1 已完成**，引入 B1（P0-轻微）
2. [P0-中等] A3: E4 不可比归因补全 → **Fix-2 已完成**，引入 B2+B3（P0-轻微）

R3 判定的 2 个必修项全部完成，引入的新问题均为 P0-轻微（可忽略）。**R4 修复完全收敛 R3 必修项。**

**收敛趋势**：

| 轮次 | P0-致命 | P0-严重 | P0-中等 | P0-轻微 | 状态 |
|------|---------|---------|---------|---------|------|
| R3 终审 | 0 | 1（A1） | 1（A3） | 7（A2/A4-A10） | 有条件通过 |
| R4 修复后 | 0 | 0 | 0 | 3（B1/B2/B3）+ 7（R3 遗留） | **已收敛** |

P0-3 的 P0-严重/P0-中等攻击点已清零，仅剩 P0-轻微可选改进项。**P0-3 已收敛，无需 R5 必修。**

---

## 对抗透明性记录

### 审查方法

1. 完整读取 `scripts/run_e2_ablation_discrimination.py`（718 行），重点验证 L31-40（docstring A1 假设）、L471-507（Stage 1/2/3 拟合+CSV 报告）、L493-497（stage_name 穷举）
2. 读取 `scripts/run_e4_temperature_analysis.py` L355-530，验证 E4 的 `fit_global_T`（L357-367）、`fit_binned_T`（L370-412）、`process_one` 中 global T 拟合（L495）和 binned-T 拟合（L522）
3. 读取 `docs/p0r3_final_verdict.md` §2.3，确认 R3 终审对 P0-3 的 2 个必修项
4. grep 全仓库确认无下游 .py 脚本读取 `ablation_ts_components.csv`（仅 docs 引用文件名）
5. 逐行验证反方攻击报告中引用的所有行号和代码片段

### 独立验证的关键事实

| 事实 | 验证方式 | 结论 |
|------|---------|------|
| L503 确为 `stage_name != "raw"` | 读取源文件 L503 | ✅ 确认 |
| L504-507 确为正条件 | 读取源文件 L504-507 | ✅ 确认 |
| L493-497 硬编码 4 个 stage_name | 读取源文件 L493-497 | ✅ 确认 |
| T_global 在 L472 一次性拟合 | 读取源文件 L471-472 | ✅ 确认 |
| Stage2 复用 cal_s1=TS(cal_p) | 读取源文件 L482 | ✅ 确认 |
| Stage3 复用 cal_s2 | 读取源文件 L490 | ✅ 确认 |
| E4 L495 拟合 global T | 读取 E4 源文件 L495 | ✅ 确认 |
| E4 L522 binned-T 对 raw cal_probs 拟合 | 读取 E4 源文件 L522 | ✅ 确认 |
| E4 binned-T 不经前置 TS | 读取 E4 L370-412 + L522 | ✅ 确认 |
| 无下游 .py 读取 ablation_ts_components.csv | grep 全仓库 | ✅ 确认 |
| L36 docstring 措辞 "E4 为 binned-only" | 读取源文件 L36 | ✅ 确认 |
| L37 docstring "非嵌套亦非同构" | 读取源文件 L37 | ✅ 确认 |

### 对反方攻击报告的评价

反方攻击报告（`p0r4_attack_p0_3.md`）质量高：
- **无稻草人论证**：所有攻击点基于代码实测，引用行号准确
- **无臆测**：B2 引用 E4 L495 经独立验证属实；B3 的参数计数经独立验证正确
- **诚实定级**：反方自身将 3 个攻击点均定为 P0-轻微，承认"无当前 bug"（B1）/"上下文可推断意图"（B2）/"结论正确"（B3）
- **7 维全扫**：反方对每个 Fix 均尝试 7 个攻击维度，未发现攻击点的维度均明确标注"未发现可攻击点"
- **对抗透明**：反方声明证据来源、独立验证事实、尝试的全部维度

反方最终判定"P0-3 的 R4 轮 2 个修复全部通过"与本审查报告结论一致。

---

## 最终声明

本报告由反反方审查代理独立撰写，基于逐行代码验证（非引用反方或 R3 报告），对 P0-3 的 R4 轮 3 个攻击点给出独立裁决。

**关键结论**：
- R4 修复完全消除 R3 终审的 2 个必修项（A1 P0-严重 + A3 P0-中等）
- R4 引入 3 个新攻击点（B1/B2/B3），均为 P0-轻微可选改进
- 无新 P0-严重或 P0-中等问题引入
- **P0-3 已收敛，R5 必修项为 0**
- 3 个 P0-轻微可选改进可在 R5 一并处理（3 行改动，1 个文件，约 5 分钟）

**P0-3 收敛声明**：R4 修复后，P0-3 的 P0-致命/P0-严重/P0-中等攻击点清零，仅剩 3 个 P0-轻微措辞/可维护性建议（可选）。**P0-3 已收敛。**
