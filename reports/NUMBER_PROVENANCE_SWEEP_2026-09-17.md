# 数字溯源清扫报告

**日期**：2026-09-17
**触发**：本轮已连续发现 6 次由**标签编码错配**导致的数值修正，每次都改动了论文的标题性结论。与其等审稿人发现第 7 次，不如自己系统扫一遍。
**方法**：把论文正文（去注释）中每一个数值声明对回它的源文件，并**验证源文件本身的编码**——而不是只验证"论文抄对了源文件"。

---

## 0. 一句话结论

论文**引用的文件名是干净的**，但**其中两个被引文件本身是污染的**，另有一个关键数字**在仓库内根本没有来源**。三处都已在正文加注，待 L2 网格重跑后统一修复。

---

## 1. 清扫方法

三步，可机械执行：

1. **建立引用图**：从正文（剔除 `%` 注释行与行内注释）抽出所有 `results/` `checkpoints/` `scripts/` `docs/` 路径，还原 `\_` 转义。
2. **标注污染窗口**：根因是 2026-09-09~09-16 期间 `SUBSPACE_CPSC` 为 NEW 编码而模型未重训。以**文件 mtime** 落在窗口内为一级嫌疑。
3. **经验判定**：mtime 只是线索。对每个嫌疑产物，用**不依赖 GPU 的判别法**独立判定（见 §3）。

> ⚠️ 教训：第 1 步的 grep 必须先去注释。首轮用 `grep -o "results/..."` 直接扫全文件，把审计注释里的文件名也算成了"正文引用"，得出"论文引用了 3 个污染文件"的**假警报**。正确做法见 `_sweep_numbers.txt` 的生成方式。

---

## 2. 污染窗口地图（按 mtime）

窗口 = **2026-09-09 ~ 2026-09-16**（NEW 编码生效期；NEW 值 09-14 提交为 `452b3bf`，09-16 由 `72b2e59` 恢复为 OLD）。同一窗口内 09-10 生成的 `ablation_ts_components.csv` 已被三重指纹判定为污染，证明工作区在 09-10 已是 NEW。

| 文件 | mtime | 窗口 | 状态 |
|---|---|---|---|
| `results/deployment_metrics.csv` | 09-05 | 前 | ✅ 干净 |
| `results/predictability_3arch.csv` | **09-05** | 前 | ⚠️ **数字干净，输入已被覆盖 → 不可复现**（§4） |
| `results/c3_crossfit_results.csv` | 09-06 | 前 | ✅ 干净 |
| `results/robustness_validation_5seeds.csv` | 09-08 | 前 | ✅ 干净（主终点源，+0.015863 与 OLD 逐位一致） |
| `results/deployment_holdout_recompute.csv` | 09-08 | 前 | ✅ 干净 |
| `results/c1_brier_reliability.csv` | **09-10** | **内** | ⚠️ 未判定，待查 |
| `results/discrimination_metrics_60exp.csv` | **09-10** | **内** | ⚠️ 未判定，待查 |
| `results/strengthening_battle_corrected.json` | 09-10 | 内 | ❌ 已知（`T`、`delta_obs`） |
| `checkpoints/.../l2_shift_results.json`（60 个） | **09-10~09-13** | **内** | ❌ **本轮新判定**（§3.2） |
| `results/l2_shift_full_390cells.csv` | **09-12** | **内** | ❌ **本轮新判定**（§3.1） |
| `results/l2_shift_full_780cells_detail.csv` | **09-12** | **内** | ❌ **本轮新判定**（§3.1） |
| `results/ablation_ts_components.OLD_ENCODING.csv` | 09-17 | 后 | ✅ 修正表 |
| `results/real_prior_recovery.csv` | 09-17 | 后 | ✅ 干净 |

**论文实际引用的文件**（去注释后）：`l2_shift_full_390cells.csv`（×2）、
`discrimination_metrics_60exp.csv`（×2）、`deployment_holdout_recompute.csv`、
`deployment_metrics.csv`、`ablation_ts_components.OLD_ENCODING.csv`、
`checkpoints/e2_probs_cache/*.npz`。

⇒ 两个 `l2_shift` 引用指向**污染文件**；`discrimination_metrics_60exp.csv` 是**待查项**。

---

## 3. 新判定：L2 移位族全部污染

### 3.1 判定方法（不依赖日期推断）

L2 有 13 档信号扰动。其中 **`noise24`** 在**非 CPSC** 方向（chapman↔ptbxl，两种编码在那里重合）上几乎不改变数值 → 可作为**近恒等档**来标定"该档固有偏离"。再用它判别 CPSC 方向属于哪种口径：

```
d_clean = | L2(cell, noise24) − 干净口径 |
d_cont  = | L2(cell, noise24) − 污染口径 |
```

脚本：`scripts/verify_l2_shift_encoding.py`（写出 `results/l2_shift_encoding_verdict.json`）。

### 3.2 结果

**① 聚合/明细表**（用 `raw_ece` 对 `smooth_ece`）

| 量 | 值 |
|---|---|
| 非 CPSC 20 格固有偏离（median） | **0.0007** |
| CPSC 40 格 \|L2 − 干净\| median | **0.0987** |
| CPSC 40 格 \|L2 − 污染\| median | **0.0012** |
| 比值 | **79×** |
| 逐 cell 与污染口径更近 | **39/40** |

**② 每 cell 的 `l2_shift_results.json`**（用 `delta_ece` 对主终点）

⚠️ 该文件的 `delta_ece` 是**相反符号约定**（`post − raw`），比较前需取负 —— 首轮漏了这一步，得到"0/40 指向污染"的**错误结论**。

| 量 | 值 |
|---|---|
| 非 CPSC 20 格固有偏离（median） | **0.0002** |
| CPSC 40 格 \|L2 − 干净\| median | **0.1693** |
| CPSC 40 格 \|L2 − 污染\| median | **0.0027** |
| 比值 | **62×** |
| 逐 cell 与污染口径更近 | **39/40** |

个例：`cpsc_ptbxl/resnet1d/44` 在 `noise24` 档 `L2 = −0.2898`，
污染口径 `−0.2900`（Δ=0.0002），干净口径 `+0.0049`（Δ=0.2947）。

**两个独立产物族、两种独立方法、同一结论。**

### 3.3 根因（与 ablation 那次不同）

`scripts/eval_l2_shift.py` L85 用**运行时**模块常量重建标签：

```python
subspace = SUBSPACE_CPSC if num_classes == 4 else None
```

它**没有**读 `checkpoints/transfer/**/transfer_result.json` 里自存的 `label_map`
（那 40 个含 CPSC 的 cell 全部是 `{"CD":1,"MI":3,"NORM":0,"STTC":2}` = OLD）。
`SUBSPACE_CPSC` 的时间线（git 证据）：

| 提交 | 日期 | 取值 |
|---|---|---|
| `df9c914` | 08-30 | `("NORM","CD","STTC")` |
| `dd96647` | 09-08 | `("NORM","CD","STTC","MI")` ← OLD |
| `452b3bf` | 09-14 | `("NORM","MI","STTC","CD")` ← **NEW** |
| `72b2e59` | 09-16 | `("NORM","CD","STTC","MI")` ← 恢复 OLD |

⇒ **probs 来自 OLD checkpoint，标签用 NEW 常量重建**，MI↔CD 互换。

---

## 4. 论文摘要的数字在仓库内已不可复现

`scripts/step2_predictability.py` 读的正是 `l2_shift_results.json`。
但 `results/predictability_3arch.csv` 的 mtime 是 **09-05（窗口前）**，
即由**污染前**的输入生成。论文引用的合并 LOO R² = −0.096、CI 上界 **0.104**
与该文件逐位一致（5 处引用，含摘要）。

然而那些**输入已被污染版覆盖**。实测重跑：

| 口径 | TS LOO R² | 95% CI | 上界 < 0.5？ |
|---|---|---|---|
| 论文 / 09-05 历史文件（干净输入，**输入已丢失**） | **−0.0958** | [−0.7199, **+0.1038**] | 是 |
| 重跑于当前污染输入 | **+0.0321** | [−0.7206, **+0.2919**] | 是 |

- **结论方向不变**：两种口径都触发预注册失败分支。
- 但引用的 `0.104` **不可复现**；当前输入给 `0.292`。
- **处置**：`predictability_3arch.csv` 恢复为 09-05 历史版（论文数字的存档）；
  污染重跑版并存为 `predictability_3arch.CONTAMINATED_INPUTS.csv`。

---

## 5. 安全率 0.0064：仓库内无来源

论文 3 处引用（L1201 / L1901 / L1993）"TS safety rate 0.0064"，承载
"TS 不是普遍安全"这一结论。溯源结果：

| 检查 | 结果 |
|---|---|
| 全 `results/` 搜字符串 `0.0064` | 只命中其它列的同名数字子串，**无一是安全率** |
| 含 `safety` 列的文件 | 只有两张 L2 表，取值域 `{0,1}`（780 行中 679 行 = 1，即 **87% 安全**） |
| 反推分母 | `1/157 = 0.0063694 ≈ 0.0064` ⇒ 该数是 **1/157** |
| 论文自述子集 | 6 对 × 2 seed × 13 档 = **156**，**157 多 1，内部不一致** |
| 按论文判据在当前明细表复算 | inceptiontime×seeds42,43 得 **6/156 = 0.0385**；全 780 行 **31/780 = 0.0397** |

⇒ 该数字来自**污染前**的一次运行，产物不在仓库内；当前口径给出约 **6 倍**之值。
方向性结论（安全判据罕被满足）两种口径都成立，但**确切率必须重算**。
已在正文明确标注不可复现。

---

## 6. 已执行的修复

| 动作 | 产物 |
|---|---|
| 新增 L2 污染通告 | `results/_L2_SHIFT_CONTAMINATION_NOTICE.md` |
| 新增 L2 编码判定脚本 | `scripts/verify_l2_shift_encoding.py` → `results/l2_shift_encoding_verdict.json` |
| 恢复历史（干净输入）CSV | `results/predictability_3arch.csv`（09-05 版） |
| 并存污染重跑版 | `results/predictability_3arch.CONTAMINATED_INPUTS.csv` |
| 论文 L2 引用处加溯源注记 | `paper/main_bspc.tex`（覆盖度说明段） |
| 论文安全率加不可复现声明 | `paper/main_bspc.tex`（§deployment） |
| 两段 AUDIT 注释（含复现路径与判定数字） | `paper/main_bspc.tex` |

编译 64 页，0 undefined refs。

---

## 7. 待办（按优先级）

1. **修 `eval_l2_shift.py` 的口径缺陷**：优先读 checkpoint 自存的 `label_map`，
   并加断言（运行时编码必须等于 `label_map`，否则 raise）。**这是根因，不修则下次改
   `SUBSPACE_CPSC` 会再次静默污染。** 同理应审 `run_e2_ablation_discrimination.py`
   与 `step2_predictability.py` 的取数路径。
2. **重跑 L2 网格**（60 cell × 13 档 × 8 方法，需 GPU，约数小时）。跑完后
   `l2_shift_results.json`、两张 `l2_shift_full_*`、`predictability_3arch.csv`
   一并重生，并重算论文所有引用它们的数字（含摘要的 0.104、安全率 0.0064）。
3. **判定两个待查项**：`results/c1_brier_reliability.csv`、
   `results/discrimination_metrics_60exp.csv`（均 09-10，窗口内）。
4. **给每个被引数字建立"来源 + 编码"登记**，纳入投稿前检查单。
5. 复核 `results/deployment_loco_validation.csv`（**09-11**，窗口内，1.08 MB，
   本轮未判定）。
