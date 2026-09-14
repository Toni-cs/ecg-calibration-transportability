# P0-3 R4轮反方攻击报告

> **反方挑刺代理交付**（任务 #114）。本报告对正方在 R4 轮对 `scripts/run_e2_ablation_discrimination.py` 的 2 个修复进行独立全维度攻击审查。
> **审查日期**：2026-09-09
> **审查代理**：反方挑刺代理（GLM-5.2）
> **攻击维度**：反例构造 / 逻辑断链 / 隐含假设 / 边界失效 / 自相矛盾 / 量级错误 / 语义偏移（7 维全扫）
> **判定原则**：以代码事实为唯一判据，逐行验证修复正确性，寻找反例、逻辑漏洞、新引入的不一致。对每个攻击点给出具体行号和代码片段作为证据。

---

## 0. R4修复内容回顾

| 修复点 | 优先级 | 位置 | 修复内容 | 对应R3攻击点 |
|--------|--------|------|---------|-------------|
| Fix-1 | P0-严重 | L503 | T_global 报告条件从 `stage_name in ("stage1_ts",)` 改为 `stage_name != "raw"` | A1: docstring-CSV 矛盾 |
| Fix-2 | P0-中等 | L32-37 | E4 不可比归因补全：增加"结构不同（TS+binned vs binned-only）"说明 + "参数空间非嵌套亦非同构"结论 | A3: E4 归因不完整 |

### R4 修复后代码（L503）
```python
"T_global": T_global if stage_name != "raw" else np.nan,
```

### R4 修复后 docstring（L31-40）
```
A1. binned temperature 的分箱变量=TS 校准后预测分布熵 H(TS(p))=−Σ p'_k log p'_k，
    其中 p'=TS(p)（Stage 1 的温度缩放输出）。注意：E4 的 binned-T 分箱变量
    为 H(p)（对原始概率分箱），两者不可直接比较，原因有二：
    (1) 分箱变量不同：E2 Stage2/3 为 H(TS(p))，E4 为 H(p)；
    (2) 结构不同：E2 Stage2/3 为 TS+binned（先全局 TS 再分箱温度），
        E4 为 binned-only（仅分箱温度，无前置全局 TS）。
    两者参数空间非嵌套亦非同构，故 ΔReliability 不可作边际贡献解释。
    假设：不确定度高的样本段需要不同的锐度校准（置信与不确定样本
    的 over/under-confidence 模式不同）。若该假设不成立，
    Stage2−Stage1 ≈ 0（脚本会如实报告）。
```

---

## 1. 逐修复点攻击审查

### 1.1 Fix-1：L503 T_global 报告条件 `stage_name != "raw"`

#### stage_name 所有可能值（代码 L493-497 穷举）

```python
for stage_name, probs in [
    ("raw", test_p),
    ("stage1_ts", test_s1),
    ("stage2_ts_binned", test_s2),
    ("stage3_ts_binned_threshold", test_s3),
]:
```

| stage_name | `!= "raw"` | T_global 报告值 | 该 stage 是否使用 TS | 一致性 |
|------------|-----------|----------------|---------------------|--------|
| `"raw"` | False | np.nan | 否（无 TS） | ✓ |
| `"stage1_ts"` | True | T_global | 是（L471-474 拟合+应用） | ✓ |
| `"stage2_ts_binned"` | True | T_global | 是（L482-484 复用 cal_s1=TS(cal_p)） | ✓ |
| `"stage3_ts_binned_threshold"` | True | T_global | 是（L490 复用 cal_s2，间接复用 TS） | ✓ |

#### 攻击维度 1：反例构造 — **未发现可攻击点**

逐一验证 4 个 stage_name：
- `"raw"`：不使用 TS，T_global 语义上不存在 → nan ✓
- `"stage1_ts"`：使用 TS，T_global = float(ts_params["T"])（L472）→ 报告 T_global ✓
- `"stage2_ts_binned"`：复用 Stage 1 的 ts_params（L482 fit_binned_temperature(cal_s1,...)，cal_s1=TS(cal_p)）→ T_global 仍是该实验的全局 T → 报告 T_global ✓
- `"stage3_ts_binned_threshold"`：cal_s3=test_s2（L490 同引用），T_global 不变 → 报告 T_global ✓

**关键验证**：T_global 在 L472 一次性拟合，stage1/2/3 共享同一 T_global 值（stage2/3 通过复用 cal_s1/test_s1 继承）。CSV 对 stage1/2/3 报告相同的 T_global 值，与 docstring L17 的 Θ_1 ⊂ Θ_2 ⊂ Θ_3（均含 T）一致。

无反例。

#### 攻击维度 2：逻辑断链 — **未发现可攻击点**

推理链条完整：
1. docstring L17 声明 T ∈ Θ_1, Θ_2, Θ_3
2. 代码 L471-472 拟合 T_global 一次
3. stage1/2/3 均复用该 T_global（通过 cal_s1/test_s1 传递）
4. CSV L503 对 stage1/2/3 报告 T_global，对 raw 报告 nan
5. → CSV 与 docstring 一致

无缺失步骤。

#### 攻击维度 3：隐含假设 — **发现攻击点 B1（P0-轻微）**

**攻击点 B1：`stage_name != "raw"` 是负条件，隐含假设"所有非 raw 的 stage 都使用 TS"，该假设当前成立但脆弱**

`stage_name != "raw"` 等价于 `stage_name in ("stage1_ts", "stage2_ts_binned", "stage3_ts_binned_threshold")`（当前 4 个 stage）。但这是**负向枚举**（排除 raw），而非**正向枚举**（列出使用 TS 的 stage）。

**反例场景**：若未来新增一个 stage（如 `"binned_only"` 或 `"threshold_only"`）不使用全局 TS，则 `stage_name != "raw"` 会对其错误报告 T_global（一个该 stage 未使用的参数）。

**对比**：同文件 L504-507 使用正向条件：
```python
"T_binned_mean": np.mean(T_binned) if "binned" in stage_name else np.nan,    # 正向：含 "binned" 才报告
"threshold_norm": float(np.linalg.norm(tau)) if "threshold" in stage_name else 0.0,  # 正向：含 "threshold" 才报告
```

L503 的负条件 `!= "raw"` 与 L504-507 的正条件风格不一致。更稳健的写法为 `stage_name in ("stage1_ts", "stage2_ts_binned", "stage3_ts_binned_threshold")` 或 `stage_name.startswith("stage")`。

**严重程度**：P0-轻微。当前 4 个 stage 下逻辑正确，仅为未来可维护性风险。无当前 bug。

#### 攻击维度 4：边界失效 — **未发现可攻击点**

- **T_global 为 nan**：若 L472 `fit_temperature_multiclass` 返回 nan，则 T_global=nan，stage1/2/3 报告 nan，raw 报告 nan → 全 nan，无崩溃 ✓
- **stage_name 为空串/None**：L493-497 硬编码 4 个 stage_name，不可能为其他值 ✓
- **空实验列表**：L646 `df_abl = pd.DataFrame(all_ablation)` 为空时，L650 `if not df_abl.empty:` 守卫跳过 pivot → 无崩溃 ✓

无边界失效。

#### 攻击维度 5：自相矛盾 — **未发现可攻击点**

验证 CSV 各列报告条件的一致性：

| 列 | 报告条件 | raw | stage1_ts | stage2_ts_binned | stage3_ts_binned_threshold |
|----|---------|-----|-----------|------------------|---------------------------|
| T_global | `!= "raw"` | nan | T | T | T |
| T_binned_mean | `"binned" in stage_name` | nan | nan | T_b | T_b |
| T_binned_min | `"binned" in stage_name` | nan | nan | T_b | T_b |
| T_binned_max | `"binned" in stage_name` | nan | nan | T_b | T_b |
| threshold_norm | `"threshold" in stage_name` | 0.0 | 0.0 | 0.0 | τ |

嵌套结构清晰：stage1 报告 T，stage2 报告 T+T_b，stage3 报告 T+T_b+τ。与 docstring L17 的 Θ_1 ⊂ Θ_2 ⊂ Θ_3 完全一致。无矛盾。

#### 攻击维度 6：量级错误 — **未发现可攻击点**

无复杂度/收敛性/稳定性估计涉及。

#### 攻击维度 7：语义偏移 — **未发现可攻击点**

`stage_name != "raw"` 的语义 = "使用 TS 的 stage"（当前等价）。与 docstring L17 的 T ∈ Θ_1, Θ_2, Θ_3 语义一致。无偏移。

#### Fix-1 小结

| 攻击点 | 维度 | 严重程度 | 状态 |
|--------|------|---------|------|
| B1: 负条件 `!= "raw"` 可维护性脆弱 | 隐含假设 | P0-轻微 | 成立（当前无 bug，未来风险） |

**Fix-1 成功消除 R3-A1**：docstring-CSV 矛盾已解决，T_global 对 stage1/2/3 均报告实际值，与 Θ_2/Θ_3 含 T 一致。

---

### 1.2 Fix-2：L32-37 E4 不可比归因补全

#### 修复内容对比

| 版本 | L32-33 文本 | 归因 |
|------|------------|------|
| R3（修复前） | "两者分箱变量不同，不可直接比较" | 仅分箱变量不同 |
| R4（修复后） | "两者不可直接比较，原因有二：(1) 分箱变量不同；(2) 结构不同" | 分箱变量 + 结构 |

#### E4 代码验证（独立读取 `run_e4_temperature_analysis.py`）

| 声明 | E4 代码行 | 验证 |
|------|----------|------|
| E4 binned-T 分箱变量为 H(p) | L380 `ent = predictive_entropy(cal_probs)` | ✓ H(p) |
| E4 binned-T 直接对 raw 概率拟合 | L522 `fit_binned_T(cal_probs, cal_labels, ...)` | ✓ 无前置 TS |
| E4 binned-T 应用时不经 TS | L425-429 `apply_temperature(probs[mask], T_per_bin[b])` | ✓ 直接对 probs |
| E4 也拟合了 global T | L495 `T_global, fit_status = fit_global_T(cal_probs, cal_labels)` | ⚠️ E4 有 global T，但用于独立比较，非 binned-T 前置 |

#### E2 代码验证（`run_e2_ablation_discrimination.py`）

| 声明 | E2 代码行 | 验证 |
|------|----------|------|
| E2 Stage2 分箱变量为 H(TS(p)) | L166 `ent = _entropy(cal_probs)`，传入 cal_s1=TS(cal_p) | ✓ H(TS(p)) |
| E2 Stage2 先 TS 再 binned | L482 `fit_binned_temperature(cal_s1, cal_y)` | ✓ TS+binned |
| E2 Stage2 复用 Stage1 的 T | L471-474 拟合 ts_params，L482 传入 cal_s1 | ✓ |

#### 攻击维度 1：反例构造 — **未发现可攻击点**

E4 不可比的两个原因均经代码验证：
- (1) 分箱变量不同：E2=H(TS(p))（L166+L482），E4=H(p)（L380）→ 确实不同 ✓
- (2) 结构不同：E2=TS+binned（L482 对 cal_s1=TS(cal_p) 拟合），E4=binned-only（L522 对 cal_probs 拟合）→ 确实不同 ✓

无反例。

#### 攻击维度 2：逻辑断链 — **未发现可攻击点**

推理链条完整：
1. E2 Stage2/3 为 TS+binned（L482 证据）
2. E4 binned-T 为 binned-only（L522 证据）
3. → 参数空间非嵌套（E2 含 T，E4 binned-T 不含前置 T）
4. → ΔReliability 不可作边际贡献解释（边际贡献要求嵌套）

无缺失步骤。

#### 攻击维度 3：隐含假设 — **未发现可攻击点**

"参数空间非嵌套"的论证：
- E2 Stage2 参数空间：{T, T_1..T_5}（6 参数，T_1..T_5 拟合在 TS(p, T) 上）
- E4 binned-T 参数空间：{T_1..T_5}（5 参数，拟合在 p 上）
- E4 的 T_1..T_5 拟合在 raw p 上，E2 的 T_1..T_5 拟合在 TS(p) 上 → 同名不同对象 → 非嵌套 ✓

"非嵌套 → 不可作边际贡献解释"是标准消融分析理论（边际贡献要求 Θ_A ⊂ Θ_B）。无隐含假设问题。

#### 攻击维度 4：边界失效 — **未发现可攻击点**

无边界场景涉及（纯 docstring 文本修改）。

#### 攻击维度 5：自相矛盾 — **未发现可攻击点**

- L33 "不可直接比较" 与 L37 "不可作边际贡献解释" 是两个递进声明（比较性 → 解释性），不矛盾
- L37 "非嵌套亦非同构" 中"非嵌套"是核心论据，"非同构"是辅助论据，不矛盾
- 与 L17 "嵌套结构保证边际贡献可加性解释" 不矛盾（L17 说 E2 内部 stage1/2/3 嵌套，L37 说 E2 vs E4 非嵌套，不同对象）

无矛盾。

#### 攻击维度 6：量级错误 — **未发现可攻击点**

无复杂度/收敛性估计涉及。

#### 攻击维度 7：语义偏移 — **发现攻击点 B2、B3（均 P0-轻微）**

**攻击点 B2：L36 "E4 为 binned-only" 措辞不精确——E4 实际同时拟合 global-T（L495）和 binned-T（L522），只是不组合**

L36: "E4 为 binned-only（仅分箱温度，无前置全局 TS）"

**证据**：E4 `run_e4_temperature_analysis.py` L495:
```python
T_global, fit_status = fit_global_T(cal_probs, cal_labels)
```
E4 **确实拟合了全局 T**，用于独立比较（L500-502 global-T reliability vs raw reliability）。E4 的 binned-T（L522）不经过这个 global T，但 E4 脚本整体并非"仅分箱温度"。

**语义分析**：
- 上下文意图："E4 的 binned-T 为 binned-only"（指 binned-T 组件不经过前置 TS）
- 字面含义："E4 为 binned-only"（可误读为 E4 脚本只有 binned-T，无 global T）
- 审稿人读 L36 可能误以为 E4 完全没有全局 T，实际 E4 有 global T（用于独立比较）

**对比**：L35 对 E2 的描述 "E2 Stage2/3 为 TS+binned" 限定了 "Stage2/3"（具体 stage），但 L36 对 E4 的描述 "E4 为 binned-only" 未限定 "binned-T 组件"，不对称。

**严重程度**：P0-轻微。上下文可推断意图（对比的是 binned-T 实现），但措辞不精确。建议改为 "E4 的 binned-T 为 binned-only（不经过前置全局 TS）"。

---

**攻击点 B3：L37 "参数空间非嵌套亦非同构" 中"非同构"论证依赖不对称比较——E2 用 6 参数空间，E4 用 5 参数 binned-T 空间，但 E4 整体也是 6 参数**

L37: "两者参数空间非嵌套亦非同构，故 ΔReliability 不可作边际贡献解释。"

**论证分析**：
- E2 Stage2 参数空间：{T, T_1..T_5} = (R⁺)⁶（6 参数）
- E4 binned-T 参数空间：{T_1..T_5} = (R⁺)⁵（5 参数）
- 6 ≠ 5 → 非同构 ✓（**但这是不对称比较**）

**对称比较**：
- E2 Stage2 全部参数：{T, T_1..T_5} = (R⁺)⁶（6 参数）
- E4 全部参数：{T_global, T_1..T_5} = (R⁺)⁶（6 参数，L495 的 T_global + L522 的 T_per_bin）
- 6 = 6 → **同构**（维度相同）

**核心问题**：L37 的"非同构"源于将 E2 的**完整参数空间**（6 参数）与 E4 的**仅 binned-T 参数空间**（5 参数）比较，忽略了 E4 也拟合了 global T（L495）。若对称比较（E2 全部 vs E4 全部），两者均为 6 参数，维度相同。

**真正的非可比原因**不是"非同构"（维度差异是人为不对称比较的产物），而是：
1. **非嵌套**：E2 的 T_1..T_5 拟合在 TS(p, T) 上，E4 的 T_1..T_5 拟合在 p 上 → 同名不同对象 → 参数空间非嵌套 ✓
2. **拟合流程不同**：E2 是顺序拟合（先 T 再 T_1..T_5 on TS output），E4 是独立拟合（T 和 T_1..T_5 各自拟合 on raw p）→ 即使参数空间同构，流程不同导致结果不可比

"非嵌套"是充分且必要的论据。"非同构"是不必要的附加论据，且其论证依赖不对称比较，数学上不严谨。

**严重程度**：P0-轻微。结论"不可作边际贡献解释"正确（"非嵌套"已充分），但"非同构"的论证不严谨。审稿人若仔细检查"非同构"声明，可能质疑比较的不对称性。建议删除"亦非同构"，仅保留"非嵌套"。

#### Fix-2 小结

| 攻击点 | 维度 | 严重程度 | 状态 |
|--------|------|---------|------|
| B2: "E4 为 binned-only" 措辞不精确（E4 有 global T） | 语义偏移 | P0-轻微 | 成立 |
| B3: "非同构" 论证依赖不对称比较 | 语义偏移 | P0-轻微 | 成立 |

**Fix-2 成功消除 R3-A3**：E4 不可比归因已补全"结构不同"，不再误导审稿人以为"统一分箱变量即可可比"。但引入 2 个 P0-轻微措辞问题（B2, B3）。

---

## 2. 全维度攻击扫描 — 其他潜在问题

### 2.1 T_global 报告条件修改的下游影响

| 检查项 | 结果 |
|--------|------|
| 其他脚本读取 ablation_ts_components.csv | **无**（grep 全仓库，仅 docs 引用 CSV 名，无 .py 读取） |
| 其他脚本引用 T_global 报告条件 | **无**（grep `stage_name != "raw"` 仅 L503 一处） |
| 测试文件验证 T_global 值 | **无**（无 test*e2* 文件） |
| CSV schema 变化 | **无**（T_global 列已存在 L61，仅值从 nan 变为实际值） |
| 旧 CSV 结果兼容性 | **警告**：旧 CSV 中 stage2/3 的 T_global=nan，新 CSV 为实际值。若有人对比新旧 CSV，会看到 T_global 列变化。但无下游脚本依赖，影响可忽略 |

### 2.2 E4 归因补全的下游影响

| 检查项 | 结果 |
|--------|------|
| docstring 行数变化 | R3 的 L31-36（6 行）→ R4 的 L31-40（10 行），增加 4 行 |
| 后续行号偏移 | L37-40 原为 A2 假设，现 L41-44 为 A2 假设。**docs 中引用 L37/L38 等行号的文档可能失效**，但代码功能不受影响 |
| 新引入的 docstring-代码偏移 | **无**（B2 是措辞不精确，非代码偏移；E4 代码行为未变） |

### 2.3 逐行 docstring-代码一致性复查

| 行号 | docstring 声明 | 对应代码 | 一致性 |
|------|---------------|---------|--------|
| L17 | Θ_2 = {T, T_1..T_5} | L482 复用 cal_s1=TS(cal_p) | ✓（R4 Fix-1 使 CSV 也一致） |
| L31 | H(TS(p)) | L166 _entropy(cal_s1), L482 cal_s1=TS(cal_p) | ✓ |
| L33 | "两者不可直接比较" | E2 vs E4 代码差异 | ✓ |
| L34 | "E2 Stage2/3 为 H(TS(p))" | L166+L482 | ✓ |
| L34 | "E4 为 H(p)" | E4 L380 predictive_entropy(cal_probs) | ✓ |
| L35 | "E2 Stage2/3 为 TS+binned" | L482 fit_binned_temperature(cal_s1,...) | ✓ |
| L36 | "E4 为 binned-only" | E4 L522 fit_binned_T(cal_probs,...) | ⚠️ B2: E4 也有 global T (L495) |
| L37 | "参数空间非嵌套亦非同构" | E2 6参数 vs E4 binned-T 5参数 | ⚠️ B3: 不对称比较 |
| L37 | "不可作边际贡献解释" | 非嵌套 → 边际贡献无意义 | ✓ |
| L503 | T_global if stage_name != "raw" | L17 Θ_1/Θ_2/Θ_3 含 T | ✓ |

### 2.4 R3 可关闭攻击点复查

| R3 攻击点 | R3 状态 | R4 是否影响 | 复查结论 |
|-----------|---------|------------|---------|
| A2 (Θ_2 独立性隐含) | P0-轻微 | 否 | 仍为 notation 简化，可接受 |
| A4 (假设改变未讨论) | P0-中等→轻微 | 否 | 嵌套修复的数学必然，可接受 |
| A5 (L36 "≈0" 忽略过拟合) | P0-轻微 | 否 | 仍为预存问题，未恶化 |
| A6 (L8 "按预测熵" 模糊) | P0-轻微 | 否 | 仍为预存问题，未恶化 |
| A7 (L19 未提前说明 Δ≡0) | P0-轻微 | 否 | 仍为预存问题，未恶化 |
| A8 (H(p) 符号冲突) | P0-轻微 | 否 | 仍为 notation 约定，可接受 |
| A9 (0-indexed vs 1-indexed) | P0-轻微 | 否 | 仍为约定差异，可接受 |
| A10 (可加性混淆) | P0-轻微 | 否 | 仍为措辞不精确，可接受 |

R4 修复未恶化任何 R3 预存攻击点。

---

## 3. 攻击点汇总（按严重程度排序）

### P0-严重

**无。**

### P0-中等

**无。**

### P0-轻微（措辞/可维护性改进）

| 序号 | 攻击点 | 位置 | 描述 | R4 引入? |
|------|--------|------|------|----------|
| B1 | 负条件 `!= "raw"` 可维护性脆弱 | L503 | 负条件隐含"所有非 raw 都用 TS"，未来新增非 TS stage 会误报。正条件 `stage_name in (...)` 更稳健 | 是（Fix-1） |
| B2 | "E4 为 binned-only" 措辞不精确 | L36 | E4 实际同时拟合 global-T（E4 L495）和 binned-T（E4 L522），"binned-only" 未限定 binned-T 组件，可误读为 E4 无 global T | 是（Fix-2） |
| B3 | "非同构" 论证不对称 | L37 | E2 用 6 参数空间 vs E4 用 5 参数 binned-T 空间 → 6≠5 → 非同构。但 E4 整体也是 6 参数（含 global T），对称比较则同构。"非嵌套"已充分，"非同构"不必要且不严谨 | 是（Fix-2） |

---

## 4. R4 修复评价

### 4.1 各 Fix 正确性评价

| Fix | 核心目标 | 代码验证 | 目标达成 | 引入新问题 |
|-----|---------|---------|---------|-----------|
| Fix-1 | 消除 A1: docstring-CSV 矛盾 | L503 对 stage1/2/3 报告 T_global | ✓ 完全达成 | B1（P0-轻微，可维护性） |
| Fix-2 | 消除 A3: E4 归因不完整 | L32-37 补全"结构不同"归因 | ✓ 完全达成 | B2+B3（P0-轻微，措辞） |

### 4.2 R3 攻击点消除验证

| R3 攻击点 | R3 严重程度 | R4 修复 | 消除验证 |
|-----------|------------|---------|---------|
| A1: T_global CSV=nan 与 Θ_2 含 T 矛盾 | P0-严重 | Fix-1: `!= "raw"` | ✓ stage1/2/3 均报告 T_global，与 docstring 一致 |
| A3: E4 不可比归因不完整 | P0-中等 | Fix-2: 补"结构不同" | ✓ 两个原因均列出，结论正确 |

**R3 的 2 个必修项（A1 + A3）均完全消除。**

### 4.3 总体评价

**R4 修复完全达成 R3 终审裁决的 2 个必修项**：
- Fix-1 消除了 A1（P0-严重）：T_global 报告条件修正，CSV 与 docstring 一致
- Fix-2 消除了 A3（P0-中等）：E4 不可比归因补全，不再误导审稿人

**R4 引入 3 个新攻击点，均为 P0-轻微**：
- B1：负条件可维护性（未来风险，当前无 bug）
- B2："binned-only" 措辞不精确（上下文可推断意图）
- B3："非同构" 论证不严谨（"非嵌套"已充分）

**无新 P0-严重或 P0-中等问题引入。** R4 修复质量高，核心目标完全达成，仅剩 3 个 P0-轻微措辞/可维护性建议。

### 4.4 与 R3 终审判定的对比

R3 终审判定（`p0r3_final_verdict.md` §2.3）要求 R4 修复：
1. [P0-严重] A1: L499 T_global 报告条件 → **Fix-1 已完成，引入 B1（P0-轻微）**
2. [P0-中等] A3: L32-33 E4 不可比归因补全 → **Fix-2 已完成，引入 B2+B3（P0-轻微）**

R3 判定的 2 个必修项全部完成，引入的新问题均为 P0-轻微（可忽略）。**R4 修复完全收敛 R3 必修项。**

---

## 5. R5 修复建议

### P0-轻微（可选改进，非阻塞）

| 序号 | 攻击点 | 文件 | 行号 | 改动内容 | 改动量 |
|------|--------|------|------|---------|--------|
| 1 | B1 | scripts/run_e2_ablation_discrimination.py | L503 | `stage_name != "raw"` → `stage_name in ("stage1_ts", "stage2_ts_binned", "stage3_ts_binned_threshold")`（正向枚举，更稳健） | 1行 |
| 2 | B2 | scripts/run_e2_ablation_discrimination.py | L36 | "E4 为 binned-only" → "E4 的 binned-T 为 binned-only"（限定组件） | 1行 |
| 3 | B3 | scripts/run_e2_ablation_discrimination.py | L37 | "非嵌套亦非同构" → "非嵌套"（删除不严谨的"非同构"） | 1行 |

### R3 遗留可选改进项（仍未处理，非 R4 引入）

| 序号 | 攻击点 | 改动内容 |
|------|--------|---------|
| 4 | A5 | L40 "≈0" → "≈0 或为负（过拟合风险）" |
| 5 | A6 | L8 "按预测熵" → "按TS校准后预测熵" |
| 6 | A7 | L19 补注 "reliability 边际贡献恒为 0；threshold opt 仅改善判别指标" |
| 7 | A10 | L20 "可加性解释" → "可解释性" |

**R5 必修项：无。** R4 已消除全部 R3 必修项（A1 + A3），引入的新问题均为 P0-轻微可选改进。

---

## 6. 对抗透明性声明

### 6.1 尝试的全部 7 个攻击维度

| 维度 | Fix-1 是否发现攻击点 | Fix-2 是否发现攻击点 | 涉及攻击点 |
|------|---------------------|---------------------|-----------|
| 反例构造 | 否 | 否 | — |
| 逻辑断链 | 否 | 否 | — |
| 隐含假设 | 是 | 否 | B1（负条件脆弱性） |
| 边界失效 | 否 | 否 | — |
| 自相矛盾 | 否 | 否 | — |
| 量级错误 | 否 | 否 | — |
| 语义偏移 | 否 | 是 | B2（binned-only 措辞）、B3（非同构论证） |

### 6.2 证据来源

所有攻击点均基于直接读取源代码验证：
- `scripts/run_e2_ablation_discrimination.py`（完整读取 718 行，重点 L31-40/L493-507）
- `scripts/run_e4_temperature_analysis.py`（读取 L360-530，验证 fit_binned_T/apply_binned_T/process_one）
- `docs/p0r3_final_verdict.md`（R3 终审裁决，R4 必修项）
- `docs/p0r3_attack_p0_3.md`（R3 攻击报告，A1/A3 原始论证）
- grep 全仓库确认无下游脚本读取 ablation_ts_components.csv
- grep 全仓库确认 T_global 报告条件仅 L503 一处

无稻草人论证、无臆测。每个攻击点均附具体行号和代码片段。

### 6.3 独立验证声明

本报告独立验证了以下关键事实（非引用 R3 报告）：
1. E4 `fit_binned_T`（L370-412）确实对 raw cal_probs 拟合，无前置 TS ✓
2. E4 `process_one`（L495）确实拟合了 global T（用于独立比较，非 binned-T 前置）✓
3. E2 `fit_binned_temperature`（L151-183）确实对 cal_s1=TS(cal_p) 拟合 ✓
4. T_global 在 L472 一次性拟合，stage1/2/3 共享同一值 ✓
5. 无下游脚本读取 ablation_ts_components.csv ✓
6. 无测试文件验证 T_global CSV 值 ✓

---

## 7. 最终判定

| Fix | 核心目标达成 | 消除 R3 攻击点 | 引入新 P0-严重 | 引入新 P0-中等 | 引入新 P0-轻微 | 判定 |
|-----|------------|--------------|--------------|--------------|--------------|------|
| Fix-1 | ✓ | A1（P0-严重） | 0 | 0 | 1（B1） | **通过** |
| Fix-2 | ✓ | A3（P0-中等） | 0 | 0 | 2（B2, B3） | **通过** |

**总体判定**：P0-3 的 R4 轮 2 个修复**全部通过**。

- Fix-1 完全消除 R3-A1（P0-严重 docstring-CSV 矛盾），引入 1 个 P0-轻微（B1 负条件可维护性）
- Fix-2 完全消除 R3-A3（P0-中等 E4 归因不完整），引入 2 个 P0-轻微（B2 措辞 + B3 论证）
- **无新 P0-严重或 P0-中等问题引入**
- R3 终审的 2 个必修项（A1 + A3）全部消除

**攻击点数量**：3 个（B1 + B2 + B3），均为 P0-轻微。

**严重程度分布**：
- P0-致命：0
- P0-严重：0
- P0-中等：0
- P0-轻微：3

**R5 必修项**：无。R4 已完全收敛 R3 必修项，剩余 3 个 P0-轻微为可选改进，非阻塞。

**P0-3 收敛声明**：R4 修复后，P0-3 的 P0-严重/P0-中等攻击点清零，仅剩 3 个 P0-轻微措辞/可维护性建议（可选）。**P0-3 已收敛。**
