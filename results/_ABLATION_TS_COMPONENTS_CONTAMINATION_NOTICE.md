# ⚠️ 污染通告 — `results/ablation_ts_components.csv` 的 raw 阶段

> **日期**：2026-09-17
> **受影响文件**：`results/ablation_ts_components.csv`（两仓库逐字节相同，
> sha256 `6b9a49fa…68ead550`）
> **受影响列**：**含 CPSC 的 40 个 cell** 的 `raw` / `stage1_ts` /
> `stage2_ts_binned` / `stage3_ts_binned_threshold` 四行的全部指标列
> （`smooth_ece`、`ece`、`brier_*`、`T_global`、`T_binned_*`、
> `delta_rel_vs_raw`）
> **未受影响**：`chapman` ↔ `ptbxl` 的 22 个 cell（两种编码在那里重合）
> **状态**：**含 CPSC 的值不可用**；修正值见
> `results/ablation_ts_components.OLD_ENCODING.csv`
> **相关**：`results/_TEMPERATURE_CONTAMINATION_NOTICE.md`（release 仓）、
> `docs/PROTOCOL_AMENDMENT_A3_CORPUS_IDENTITY.md`

## 根因：probs 与 labels 的编码错配（**不是**噪声底）

`checkpoints/e2_probs_cache/*.npz` 同时存放 probs 与 labels，但二者来自**不同编码**：

| | 来源 | 编码 | 含义 |
|---|---|---|---|
| **probs** | 2026-09-08 训练、当时 `SUBSPACE_CPSC=("NORM","CD","STTC","MI")` 的 checkpoint | **OLD** | 第 1 列 = CD，第 3 列 = MI |
| **labels** | 2026-09-09 编码变更**之后**写入 | **NEW** | 1 = MI，3 = CD |

`scripts/run_e2_ablation_discrimination.py::load_probs_for_checkpoint`
在 `--use-cache` 下直接读该 npz（L384-390）；否则用**当前** `SUBSPACE_CPSC`
重建数据集标签（L394/L423）再前向。CSV 生成于 2026-09-10，即编码已变更之后，
于是命中了错配缓存：模型把 CD 的质量放在第 1 列，而真值第 1 列是 MI，
**CD 与 MI（合计 38.3% 的样本）被系统性判错**，raw ECE 因此虚高。

## 证据链

1. **第一方归档**：`checkpoints/transfer/**/transfer_result.json` 自存
   `label_map`；40 个含 CPSC 的 cell 全部是
   `{"CD":1,"MI":3,"NORM":0,"STTC":2}`（= OLD）。
2. **标签频次反推**：npz 的 CPSC 测试集标签为
   `[NORM=183, ?1=303, STTC=1086, ?3=485]`（n=2057）→
   8.90% / 14.73% / 52.80% / 23.58%；
   `data/cpsc_processed/preprocess_summary.json` 全库分布为
   NORM 8.88% / MI 14.71% / STTC 52.75% / CD 23.55% / HYP 0.11%。
   逐位吻合 ⇒ 索引 1 = MI、3 = CD，即 **labels 是 NEW**。
   （若按 OLD 读，则 MI=23.6% > CD=14.7%，与流行病学相反。）
3. **混淆矩阵指纹**：`ptbxl_cpsc_resnet1d_seed42` 中，
   NEW-标签 1（=MI）的患者 **250/303 = 82.5%** 被判为 argmax **3**；
   NEW-标签 3（=CD）的患者 42.5% 被判为 argmax **1**。
   若 probs 与 labels 同为 NEW，对角线应占优 ⇒ **probs 必为 OLD**。
4. **论文自洽锚点**：`paper/main_bspc.tex` 的 case study 引用
   `0.3160`（L1440）、`0.3144`（L1448）、`0.0649`（L1467），
   与本通告的 OLD 重算**精确到 4 位小数**一致；污染 CSV 对应为
   `0.3747` / `0.3685` / `0.0832`。⇒ 论文的 raw ECE 口径本来就是 OLD。

## 修正值

### `stage=raw` 的 `smooth_ece`

| 子集 | n | 污染 CSV | **修正（OLD）** |
|---|---|---|---|
| 全部 62 个 raw cell | 62 | mean 0.2728，[0.0357, 0.4689] | **mean 0.2114，[0.0357, 0.3566]** |
| 含 CPSC | 40 | mean 0.3219，[0.0746, 0.4689] | **mean 0.2268，[0.0620, 0.3566]** |
| 非 CPSC | 22 | mean 0.1833，[0.0357, 0.2714] | 不变 |

逐位对比：`max|CSV − OLD| = 0.193472`，**62 个 cell 无一相同**。

### 主终点反例（9 个，与 `robustness_validation_5seeds.csv` 的
`ood_deltaECE < 0` 集合**完全相同**）

| cell | raw（污染） | raw（修正） |
|---|---|---|
| chapman→cpsc/inceptiontime/45 | 0.3747 | 0.3160 |
| chapman→cpsc/resnet1d/43 | 0.3685 | 0.3144 |
| chapman→ptbxl/inceptiontime/42 | 0.2583 | 0.2583 |
| chapman→ptbxl/resnet1d/45 | 0.2452 | 0.2452 |
| cpsc→chapman/resnet1d/42 | 0.0832 | 0.0649 |
| cpsc→chapman/resnet1d/44 | 0.1802 | 0.1435 |
| cpsc→ptbxl/resnet1d/43 | 0.4028 | 0.2893 |
| cpsc→ptbxl/resnet1d/44 | 0.4167 | 0.3213 |
| ptbxl→chapman/inceptiontime/46 | 0.1613 | 0.1613 |

反例 raw 范围：污染 `0.0832–0.4167` → **修正 `0.0649–0.3213`**。

### `T_global`（60 个 main cell）

修正后 **median 1.0757，范围 0.9320–1.4982，T ≥ 2 占 0.0%**。
与 `_TEMPERATURE_CONTAMINATION_NOTICE.md` 中「污染 CSV 报 median 1.836 /
T≥2 占 50.0%」形成对照，两条独立路径给出同一个修正值。

## 对论文的影响（已同步修改）

`paper/main_bspc.tex` 两处引用了污染值，均已改：

| 位置 | 原（污染） | 改后（修正） |
|---|---|---|
| L1213 | `$0.036$ to $0.469$ (mean $0.273$)` | `$0.036$ to $0.357$ (mean $0.211$)` |
| L1214 | `$2$--$28\times$` | `$2$--$21\times$` |
| L1216 | `($0.08$--$0.24$)` | `($0.065$--$0.321$)` |
| L1782 | `$2$--$28\times$` | `$2$--$21\times$` |
| L1783 | `($0.036$--$0.469$, mean $0.273$)` | `($0.036$--$0.357$, mean $0.211$)` |

**注意**：L1216 原句 `confirming the negative $\Delta$ECE reflects genuine
TS-induced harm, not metric noise` 亦被改写。该句有两处问题：(a) 反例的
$\Delta$ECE 为**负**即 TS 有益，"harm" 与符号矛盾；(b) 度量噪声的方向恰恰是
让 $\Delta$ECE 变负（TS 抬高完美校准下的 ECE），故"raw ECE 大"**不能**推出
"非噪声"。改写后仅陈述可证事实，并把反例的符号降级为 exploratory。

## 复现

```bash
cd D:/A1/ecg-lab-v2
/c/python/python.exe scripts/recompute_ablation_old_encoding.py          # 只看对比
/c/python/python.exe scripts/recompute_ablation_old_encoding.py --write  # 写出修正 CSV
```

脚本只改标签（对含 CPSC 的 cell 施加 `swap13`，即 1↔3）、**不动 probs**，
再调用与原脚本**完全相同**的 `fit_temperature_multiclass` /
`fit_binned_temperature` / `optimize_thresholds` / `calibration_reliability`
重算四个 stage。

## 待决

- 是否用修正版**替换**（而非并存）`ablation_ts_components.csv`。当前策略是
  **保留原文件 + 并存修正文件 + 本通告**，以保留可审计的原始产物。
- 是否重跑整条 `run_e2_ablation_discrimination.py`（清空
  `checkpoints/e2_probs_cache/` 后重跑）以生成「同一次运行、同一编码」的
  权威 CSV。本通告的修正值是**标签还原**，与重跑在数值上应当等价，
  但重跑能同时消除缓存本身。
