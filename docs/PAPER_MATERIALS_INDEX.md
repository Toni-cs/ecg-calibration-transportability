# 论文资料与数据索引（R8 整理后，2026-09-07）

> 论文：`paper/main.pdf`（11 页，源 `main.tex` + `cover_letter.tex`）
> 当前审计状态：R8 三轮对抗审计完成，21 处论文修复已执行，底层数据已端到端封口。
> 总索引：`docs/ROUND8_AUDIT_AND_FIXES.md`（审计全文 + 复算口径 + 遗留清单）。

## 1. 论文层（paper/）

| 文件 | 说明 | 数据来源 |
|------|------|----------|
| `main.tex` → `main.pdf` | 投稿正文（60 实验版，R8 修复后） | 全部数字可溯源到 results/ 与 checkpoints/ 的 JSON |
| `cover_letter.tex` | 投稿信（已撤回裸域名声称） | — |
| `generate_figures.py` | 图 1-5 生成脚本 | results/robustness_validation_5seeds.csv、counterexample_analysis、c4_resnet1d_8method.csv |
| `figures/fig_*.pdf/png` | 已重生成（fig1 图例已改 percentile） | 同上 |

## 2. 数据层（data/）——只剩单一有效版本

| 目录 | 状态 | 说明 |
|------|------|------|
| `chapman_processed_v2/` | ✅ 唯一有效 | NORM 4767/STTC 14116（SB/ST/SA→NORM 覆写后）；21 条非有限记录已隔离 `quarantine_nonfinite/`，`qc_report.json` 在位 |
| `cpsc_processed/` | ✅ | 10296 患者，4 类子空间（HYP n=11 剔除） |
| `ptbxl_processed/` | ✅ | 21522 记录 / 官方 strat_fold；**注意：源 CSV 21799 行（官方 21837，缺 38 条，论文须披露）** |
| `nstdb/` | 空 | 真实噪声库未下载（PhysioNet 认证）→ L2 噪声档为合成替代，论文须披露（协议 §3:54 偏离） |
| `downloads/` | ✅ 原始档案保留 | ecg-arrhythmia zip（2,498,709,074 B 与 meta 精确一致）、ptb-xl-data.zip、ptbxl_database.csv |

**已删除**：`data/cpsc_test/`（cpsc_processed 的 50 条位级复制体，全库零引用）、
`data/chapman_processed/`（v1 陈旧版本：旧映射+21 条 NaN 污染记录，landmine）、
`downloads/*.zip.parts`（75 个分块残留，正式 zip 已完整）。

## 3. 结果层（results/）——60 实验世界（当前生效）

| 文件 | 说明 |
|------|------|
| `robustness_validation_5seeds.csv` | **主数据**：480 行 = 60 实验 × 8 方法（论文主表唯一数据源） |
| `robustness_report.md` | 51/60、9 反例、逐格明细（2026-09-06 19:02 生成，60 世界） |
| `meta_analytic_pooled.csv` | RE-DL 0.014771 [0.014051,0.015490]；FE 列病态已披露（退化 CI 权重垄断） |
| `bh_fdr_correction.csv` | n_total=60，BH/Bonf 后均 51/60（伪 p 层；诚实口径 12 层 BH=9/12） |
| `bootstrap_diagnostics.csv` | CI 宽度/效应量真实；**n_*_est 与 converged/cluster 列为公式常量（R8 发现），待重测（P1）** |
| `c4_resnet1d_8method.csv` | ResNet 8 方法支持数（EM 19/30 非 ResNet 最脆弱） |
| `predictability_3arch.csv` | 失败分支判定（R² CI 上界 0.104<0.5）；实为 2 架构 12 折（偏离已登记 §11.5-A2） |
| `deployment_metrics.csv` | 部署表 1-7 原始数据（`#` 注释头，pandas 读取需跳行） |
| `decomposition_validation_n20000.csv` | 27 格分解正式版（27/27 PASS）；`*_postfix/_rerun` 哈希相同的事故存档 |
| `counterexample_analysis.md`、`zone2_*.md`、`round7_*.md`、`final_arbitration_v6.md`、`coverage_gap_attack.md`、`defense_report.md` | **历史审计痕迹（48 实验世界 + 60 世界混合）**，只作审计记录，不得当现状引用；paper 已与 60 世界对齐 |

## 4. 溯源层

- `logs/`（R8 整理后归拢，含 0 字节日志）：全部 40+ 执行日志。关键证据：
  - `bca10000_transfer.log` = 3 个 BCa 重跑（ts-only，混合溯源证据）
  - `transfer_ptbxl_cpsc_seed444546.log`（0 字节）= R1 无日志实验的证据本体
  - 各 `transfer_*.log` 尾行与 CSV/JSON 数值三方一致（R8 已抽样 + 恒等式全量校验）
- `checkpoints/`：62 个 best_model.pt（60 正式 + 2 mamba toy）+ transfer_result.json；**BCa 重跑（rerun_bca10000.py）依赖这些 checkpoint，勿删**
- `docs/osf_archive_manifest.json`：快照哈希清单（协议/论文已漂移——OSF 重传前勿再改协议）

## 5. 归档（D:\A1\_archive_attack_scripts\）

8 个历史攻击脚本 + README（含 R8 逐脚本判决：2 崩溃、2 构造错误、2 部分成立、2 攻击失败）。
唯一存活的实质发现（BBSE/EM ID sanity w_ID 漂移无门控）已登记协议 §11.5-A2。

## 6. 今日删除清单（全部零引用校验后执行）

| 对象 | 理由 |
|------|------|
| `D:\A1\python`（0 字节）、`D:\A1\__pycache__`、`D:\A1\temp_skills`（空壳克隆） | 垃圾 |
| `ecg-lab-v2/tmp_audit{,_ckpt,_n500,_round7,_small}` | 旧审计临时产物（已被 R8 取代，tmp 命名 + gitignored） |
| 全库 `__pycache__`/`.pytest_cache` | 可再生 |
| `data/cpsc_test`、`data/chapman_processed`(v1)、`downloads/*.zip.parts` | 数据 landmine（见 §2） |
| 根目录 57 个日志/元数据文件 | 归拢至 `logs/`（未删除） |

`ecg-lab/`（v1 原始仓库）与 `D:\A1\{.arts,.codeartsdoer,.codegraph,.merkle-snapshot.json}` 为编辑器状态/历史工作，未触碰。
