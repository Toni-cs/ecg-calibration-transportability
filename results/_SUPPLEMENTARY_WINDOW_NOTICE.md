# 污染通告：补充材料包（`paper/submission/supplementary/`）

**状态**：❌ **整包需在重跑后重新组装 + 重签哈希**
**新增日期**：2026-09-17
**打包时间**：2026-09-13 20:06（**落在污染窗口 2026-09-09 ~ 09-16 内**）
**文件总数**：159；**落在窗口内：80**

---

## 1. 一句话结论

补充材料包是在污染窗口**内部**组装的，其中 **16 张 S2 结果表**与
**70 张 S4 可靠性图 PDF** 的 mtime 落在窗口内。至少 **10 个文件已确认污染**
（前几轮 + 本轮），且 `SHA256SUMS.txt`（09-13）把这些**污染值钉进了哈希清单**。
投稿前必须重跑 → 重新组装 → 重新生成 `SHA256SUMS.txt`。

---

## 2. 好消息：per-experiment provenance 是干净的

`S3_per_experiment/**/transfer_result.json` 共 **60 份，mtime 全部 = 2026-09-08**，
**早于污染窗口**。其中自存的 `subspace = ["NORM","CD","STTC","MI"]`（40 个含 CPSC 的
cell）是**窗口前的权威编码记录**，也是本轮全部裁决的立论基础。

（唯二例外：`S3_per_experiment/ptbxl_chapman/mamba/seed{42,43}/transfer_result.json`，
mtime 09-02，schema 残缺 —— 缺 `num_classes` / `subspace` / `label_map`。
它们属 5 类方向，无编码风险，但应在重跑后补齐字段。）

---

## 3. 窗口内的 S2 结果表（16 张）

| 文件 | mtime | 规模 | 判定 |
|---|---|---|---|
| `ablation_ts_components.csv` | 09-10 12:45 | 62 cell | ❌ **已确认污染**（前轮；修正版 `.OLD_ENCODING.csv` 已存在） |
| `l2_shift_full_390cells.csv` | 09-12 22:05 | 390 | ❌ **已确认污染**（前轮，79×/39-40 实证） |
| `l2_shift_full_780cells_detail.csv` | 09-12 22:05 | 780 | ❌ **已确认污染**（同上） |
| `binned_temperature_exploratory.csv` | 09-11 12:44 | 310 行，n_ood_bin≈1139 | ❌ **已确认污染**（温度族 3 件之一） |
| `temperature_distribution_analysis.csv` | 09-11 | 73 行，n_ood=4050 | ❌ **已确认污染**（温度族） |
| `temperature_shift_sensitivity.csv` | 09-11 | 868 行，n_cal=2158 | ❌ **已确认污染**（温度族） |
| `discrimination_metrics_60exp.csv` | 09-10 12:45 | 496 行，全量 | ❌ **本轮确认污染**（AUROC 0.642→0.861 逐位实证；修正版已生成） |
| `c1_brier_reliability.csv` | 09-10 12:29 | 60 行，**n=20** | ❌ **冒烟 + 窗口内** |
| `c1_brier_reliability_summary.csv` | 09-10 12:29 | 6 指标 | ❌ 同上 |
| `c1_dcr_ncv_multiclass.csv` | 09-10 12:29 | 60 行，**n=20** | ❌ 同上 |
| `c1_dcr_ncv_summary.csv` | 09-10 12:29 | 5 指标 | ❌ 同上（论文引其 3 个数值，见 `_C1_DCR_NCV_SMOKE_NOTICE.md`） |
| `deployment_loco_validation.csv` | 09-11 18:23 | 1755 行，n_target=2120 全量 | ⚠️ **待裁决**：全量但由带缺陷脚本产出，4 类方向受影响 |
| `deployment_loco_validation_smoke.csv` | 09-09 | 117 行，**n_target=20** | ⚠️ 冒烟件，不应随包发布 |
| `c3_inceptiontime_lite_30exp.csv` | 09-12 12:51 | **0 数据行** | ⚠️ 空占位文件，不应随包发布 |
| `EXPERIMENT_PROTOCOL.md` | 09-09 | — | ✅ 见 §5（哈希未变） |
| `PROTOCOL_AMENDMENT_A2_FAMILY_REDUCTION.md` | 09-10 | — | ✅ 文本文件，非数值产物 |

---

## 4. 窗口内的 S4 可靠性图（70 张 PDF，mtime 09-12）

`fig_reliability_supp_*.pdf` 共 70 张，由 `run_e6_reliability_diagrams.py` 生成。
该脚本原先使用同一句缺陷代码（运行时 `SUBSPACE_CPSC` 重建标签）⇒ 4 类方向的
可靠性曲线**画在错位标签上**，图形本身即污染产物。已加编码护栏；需重跑重绘。

---

## 5. `EXPERIMENT_PROTOCOL.md`（09-09）—— 未被改动

该文件被 `docs/osf_archive_manifest.json` 的哈希钉住，**不得直接改**。
其 mtime 落在窗口内仅因该轮工作区触碰；内容未变（协议快照字节不变是硬约束，
一切改动一律另立修订案 A1/A2/A3）。重打包时无需处理。

---

## 6. 处置清单

1. **重跑**：L2 网格（60 cell）、ablation/discrimination（E2）、E3（全量 n）、
   温度族（E4）、可靠性图（E6）、LOCO（E1b）。
2. **重新组装**补充材料包；`c3_inceptiontime_lite_30exp.csv`（空）与
   `deployment_loco_validation_smoke.csv`（n=20）**不应随包发布**。
3. **重新生成** `SHA256SUMS.txt`（现有清单钉的是污染值）。
4. 重跑完成前，**不要把该包上传到投稿系统**。
5. 建议在包内新增本通告与
   `results/_L2_SHIFT_CONTAMINATION_NOTICE.md`、
   `results/_DISCRIMINATION_CONTAMINATION_NOTICE.md`、
   `results/_C1_DCR_NCV_SMOKE_NOTICE.md`，作为"已自查并修正"的证据链。
