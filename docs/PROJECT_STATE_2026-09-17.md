# 项目状态汇总（2026-09-17）

> 本文件把散落在 `reports/`、`results/_*_NOTICE.md`、会话记忆里的**项目级事实**收拢到一处，
> 使知识随仓库版本化，而不是留在本地缓存里。凡有独立报告的主题，此处只留结论 + 指针。

---

## 1. 仓库拓扑（最易搞错）

远端 `Toni-cs/ecg-calibration-transportability` 有**两个分支**，两个本地仓库历史独立、各推各的：

| 本地目录 | 推送目标 | 角色 |
|---|---|---|
| `D:\A1\ecg-lab-v2\` | `release/full-work` | 全量工作区（含 paper/ docs/ logs/ data/） |
| `D:\A1\ecg-release\` | `origin/main` | 发布本体（src/ scripts/ tests/ splits/ results/） |

- 2026-09-17 已推：lab `e739f68`、release `34231d3`。
- ⚠️ 早期笔记「lab 不该推」是**错的**；早期「56 个未推」是**拿错远端**算的
  （`vendor` 指向别人的 `github.com/labhai/SafeECGMatch`），真实是 **20 个**。
- lab 已配 `push.default=upstream` + `branch.main.{remote=release, merge=refs/heads/full-work}`，裸 `git push` 安全。
- ⚠️ `.gitignore` 的目录模式**必须前导斜杠**（`/data/` 而非 `data/`）。裸写曾把 release 的整个 `src/data/`
  排除出仓库，导致 11 个 `import src.data.*` 的脚本在克隆后全部 `ModuleNotFoundError`（**仓库不可运行**）。
- ⚠️ lab 的 `results/`、`checkpoints/`、`logs/` 被忽略，需要时用 `git add -f`。

## 2. 论文

- 活跃稿 `paper/main_bspc.tex` → **68 页 / 0 undefined references / 0 warning / 2 Overfull**（pdflatex 两遍，2026-09-18 复验）。
- **文件名不要改**：预注册哈希清单与 40+ 处审计记录引用 `main_bspc.tex`；投稿若需 `main.tex`，打包时复制改名。
- `\journal{}` 与 `paper/cover_letter.tex` **均已是 CMPB**（早期笔记「仍写 BSPC」已过期）。
- 目标期刊 **CMPB**（Computer Methods and Programs in Biomedicine, Elsevier）。
  中科院分区表已于 **2026-09-30 关停**，2025-03-20 版为最后一版。
  **CBM（Computers in Biology and Medicine）已从 WoS 除名（2025-11-17 起），绝不能投。**
- OSF DOI（2026-09-18 实测解析）：**项目** `10.17605/OSF.IO/53H64` ✅ 200 → `osf.io/53h64/`；
  **注册** `10.17605/OSF.IO/WJZ3Y` ✅ 200 → `osf.io/wjz3y/`（`OSF Preregistration`，2026-09-14，公开）。
  ⚠️ OSF 注册元数据页显示的 `10.17605/OSF.IO/NGJE2Y` **不解析（doi.org 404）**，**不得引用**。
- ⚠️ `sec:coverage` 标签**不存在**（有的是 `sec:counter`/`sec:noise_floor`/`sec:noise_mechanism`）。
- ⚠️「仅 2 种架构」的表述散布 **~20 处**：
  L67, 141, 150, 176, 213, 389, 508, 510, 600, 625, 633, 746, 764, 836, 891, 926, 1036, 1214, 1530, 1532。
- 已新增 **Limitation (xxi)**（检查点非逐位可复现 + 2 格曾共用源模型）；Code availability 的表述已从
  "reproducible from the public repository" 收窄为 "reproducible from the released checkpoints and result artifacts"。

## 3. 主终点与关键量（均已独立复算）

- **ΔECE_OOD = +0.015414**（60 cells，**50/60** 为正 = 83.3%，中位 +0.017043）。ID 对照 **+0.008264**（47/60）。
  源：`results/robustness_validation_5seeds.csv`，`method=ts`。
  ✅ 重训 2 格后**已重算并同步更新论文**。旧值 +0.015863 / 51/60 **已作废**。
- 拟合温度（**OLD 口径**）中位 **1.075689**，范围 0.9320–1.4982，**T≥2 占 0.0%**。
  `corr(ΔECE, T) = +0.9753` ⚠️ **机械结果，不可当作证据引用**。
- 9 个反例的 CI 是**整段为负（`ci_hi < 0`）**，不是「下界 < 0」（`ood_significant` 才是 `ci_lo > 0`）。
- 噪声底约定 = `SmoothECE(TS) − SmoothECE(raw)`（**post − raw，与主终点符号相反**）→ 机理斜率 **−0.045**；T=1 时恰为 0。
  ⚠️ 必须使用主网格 60 格的**真实 top-label 分布**；cell 集合钉死 `EXCLUDE_ARCH=("mamba",)`。
- BBSE 先验恢复 0.1132 vs 基线 0.1916（**40.9% 改善**，56/60）。
  decomposition 估计器 cross-fit 误差 **+0.29**（是效应的 18 倍）——**本文真实短板**。

## 4. 标签编码污染

**根因**：2026-09-09 把 `SUBSPACE_CPSC` 改成 NEW，却**没有重训模型** → MI↔CD 语义错位（涉及 38.3% 样本）。
09-16 回退了代码，但**产物没有全部重跑**。污染窗口 ≈ **09-09 20:26:34 → 09-16 20:48:18**。

- OLD = `("NORM","CD","STTC","MI")`；NEW = `("NORM","MI","STTC","CD")`；两者恰为 **1↔3 互换**（`swap13`）。
- **脏**：`checkpoints/e2_probs_cache/*.npz`（仅 labels 脏，probs 干净）；`strengthening_battle_corrected.json`
  的 `T`/`delta_obs`；3 份温度 CSV；`ablation_ts_components.csv`；L2 shift 全家族；`deployment_loco_validation.*` 全部；
  `discrimination_metrics_60exp.csv`；`c1_brier_reliability*` / `c1_dcr_ncv*`；补充材料整包（75 个文件在窗口内）。
- **安全**：`delta_obs_orig`、`raw_ood_orig`、`cal_ood_orig`、`deployment_metrics.csv`
  （09-05，git 跟踪，提交 `dd96647` 早于窗口）。
- **判定编码的四种手段**（效力递增）：① 文件自存 `label_map`/`subspace`；② 标签频次反推
  （CPSC 测试集 8.90/14.73/52.80/23.58% ⇒ 索引 1=MI、3=CD）；③ 混淆矩阵指纹；④ **同编码不变量**（最有效）。
- 三条硬约束：
  - `swap13` 能逐位复现 `ood_acc` 40/40（`max|Δ| = 0`），但 ⚠️ **绝不可用于 5 类 cell**。
  - ⚠️ **ECE 对 probs/labels 的同步置换不变**，因此不能用来判定编码。
  - ⚠️ `l2_shift_results.json` 的 `delta_ece` 是 `post − raw`，**比较前必须取负**（漏负号曾得出假的「0/40」）。
- ⚠️「79×」是**跨 13 档的选择效应**（实测 1.0×–79.1×）；诚实说法是「低扰动档 100%（39/39）」。
- 完整实测细节见 `reports/NUMBER_PROVENANCE_SWEEP_2026-09-17.md` 与 `results/_*_NOTICE.md`。

### 两道机制护栏

- 🔑 **同编码不变量**：把 y 与「依赖标签的派生特征」放进同一回归之前，先断言
  `smooth_ece(raw) − smooth_ece(stage1_ts) == ood_deltaECE`（tol 1e-9）；60/60 通过才算同源，否则 `SystemExit`。
- 🔑 `src/utils/encoding_guard.py`：`checkpoint_subspace()` 以 checkpoint 自存的
  `transfer_result.json:subspace` 为唯一权威，不一致**永远 raise**。
  ⚠️ 例外：`run_e5_inception_lite.py` 的 checkpoint **从不写** `transfer_result.json`。

## 5. 易回退的数值（改回去就是错）

- 62 raw-stage raw ECE **`0.036–0.357, mean 0.211`**（倍数 2–21×）；9 反例 raw ECE **`0.065–0.321`**。
- 温度中位 **`1.076`**（不是 1.836）；底噪斜率 **`−0.045`**；T 可预测性 R² **`+0.34`**。
- **`ΔAUROC_TS−raw` = `+0.000355 / max 0.001706`**（OLD 标签 + **OLD 温度**）；
  `+0.000856 / 0.010477` 只在**错误温度**下复现。
- 部署安全率：源 `results/deployment_metrics.csv` L182；**列义 `n_safe = 1`**；
  **`157 = 144 + 13`**（残缺网格产物，**不是「2 seeds × 1 arch」**，157 是质数）；
  **1/157 对 ts/platt/vector/bbse_prior 四法相同**；`156` = BH-FDR 家族（6 × **2 架构** × 13）。
- OOD AUROC **`0.735–0.843`**（6 方向均值）。C1 名称 = **"primary OOD benefit"**。
- Shapley 错误簇**散布 5 个 pair**（2/2/2/2/1）；Wasserstein 实测 **0.569**。
- 分解模型**方向零信息（κ = 0）**但秩次弱显著（ρ = +0.3138, p = 0.0146），**R²_oos = 0.00035** ⇒「仿射能救」不成立。
- OOD/ID 的 NCV、DCR 三值 **待重跑**（源表是 n=20 冒烟且在窗口内）。
- 措辞口径：`rules out a SmoothECE artifact` → `bounds, but does not eliminate`；类别数按 pair 披露 K=4/K=5；
  `CPSC2018+2019` → **`CPSC2018`（CPSC Database + CPSC-Extra）**；§A3 已加；AI 声明已统一。
- 🔑 **论文自身锚点证明其 raw ECE 口径本就是 OLD**：case study 引用的 `0.3160/0.3144/0.0649`
  与 OLD 重算一致（污染 CSV 给的是 `0.3747/0.3685/0.0832`）。

## 6. 已裁决事项

- **CPSC 官方没有 superclass 定义**。CPSC2018 官方 = 9 类（**无 MI**）；CPSC2019 = QRS/心率**检测**任务。
  superclass（NORM/MI/STTC/CD/HYP）是 **PTB-XL** 体系。
  本地 `kaggle_cpsc2018/` = CPSC Database（6844 条，**丢失 33 条 A6845–A6877**，MI 计数 0）；
  `kaggle_cpsc2019/` = **CPSC-Extra**（3453 条，MI 1515）⇒ **语料里根本没有 CPSC2019**。
- **协议快照字节不变**：`docs/EXPERIMENT_PROTOCOL.md` 被 manifest 钉住，**不得直接修改**；改动一律另立修订案（A1/A2/A3）。
- **三个 ΔECE 字段的真实身份**：`delta_obs_orig` = **+0.015414** ✅ 有效（在干净缓存上以独立代码路径
  复现主表 60/60，max|Δ| = 4.66e-07）；`delta_obs` = +0.106843 ❌（NEW 编码的伪信号）；
  `delta_pred` = +0.184788 ⚠️ **退化**（`decompose_benefit(slope=1.0, intercept=0.0)` 的注入是恒等变换，
  `shap_s ≡ shap_b ≡ 0`）⇒ **论文 §real_shapley 的 +0.29 / +0.31 / 20.86× 目前不可复现**（任务 #49）。
  另 **"85% 方向准确率"零信息量**（常数恒正基线也是 50/60，与分解模型**逐位相等**，κ = 0）。
- ⚠️ **`sign(ΔECE) = sign(T−1)` 在 60/60 成立，是「可证伪的经验规律」，不是逻辑等价**：
  固定 `T = 2.0` 会让 5/62 翻转为负；换成 NEW 温度会掉到 56/62。论文 §(ii) 的原句已删。
  仍然成立的是：`T* > 1` 对 60/60（其中 41 格右删失于**人为上界 2.0**）；
  完美校准 + 固定 T=1.0757 的配对 bootstrap CI **排除 0**。
- **算法创新四条路线全部否决**（无标签特征替代分解 / King-Zeng 协变量偏移界 / BBSE 接入 `decompose_benefit` /
  汇编融合）。**正确顺序：统一口径 → 重建 cross-fit 脚本 → 再加架构。**
- **BiMamba 第 3 架构**：修 `mamba_chunked.py`（**只分块 SSM，不碰 conv1d**）→ 19.71 GB / 18.06 s 降到
  **5.24 GB / 1.38 s**。⚠️ 分块**不加速**；**chunked Mamba 是已知工程技巧，不可包装成新算法**。
- ✅ **检查点独立性已闭合并已修**：`cpsc_chapman/inceptiontime/seed{42,43}` 与
  `cpsc_ptbxl/inceptiontime/seed{42,43}` 的 `best_model.pt` **逐字节相同**（全 64 个 checkpoint 中唯一重复）
  ⇒ 60 格只对应 **58 个不同源模型**。**根因两层**：
  ① 只有 cpsc 当源时才可能共用（`num_classes = min(...)`，K 不同则 `eval_transfer.py` 直接 raise）；
  ② `launch_seed43_transfers.py` 对两个 cpsc 作业都传了 `--load-model`，而它只在自己 `run_dir` 里找，
  于是模型是**手工拷进去**的——只对 seed 42/43 做了、44–46 没做，**网格是两种方式拼起来的**。
  **已重训那 2 格**（`scripts/retrain_cpsc_ptbxl_it_seed42_43.py`）。
  ⚠️ `scripts/train.py:51` 的 `set_seed(seed, deterministic=False)` ⇒ **cuDNN 非确定性开启 ⇒ 归档 checkpoint 不可逐位复现**。
  ⚠️ **重训协议已验证与原始一致**：`eval_transfer.py` 省略 `learnable_temp` 而 `train.py` 显式传 `False`，
  但 `ECGClassifier` 的**默认值就是 `False`** ⇒ 等价；其余超参与 `train_model` 完全一致。
- ⚠️ **K=5 恰当且仅当 pair = {chapman, ptbxl}**（任何含 cpsc 的 pair 一律 K=4）。
  源为 chapman/ptbxl 时 `cal_labels` 跨目标不同，**是 K 不同所致，不是缺陷**。

## 7. 已推翻（勿沿用）

R1/R2/R3 各轮被自己打掉的旧结论**不在此重述**——见 `reports/ADVERSARIAL_ROUND*.md`。
唯一必须记住的元规则：

- ⚠️ **R3 期间一个只读代理覆盖了 `results/deployment_loco_validation.json`**（违反只读前提），
  已由 `scripts/reconstruct_loco_json.py` 从 sha256 校验通过的 CSV 重建。
  **约束代理要靠文件系统，不能只靠提示词。**
- `strengthening_battle_corrected.json` 的 `T` ≡ `T_new` ⇒ `(T, raw_ood_orig, cal_ood_orig)` 不可联合复现；
  已**增量补 `T_old`**（62/62，不改动 `T`）。

## 8. 待办

### 8.1 BiMamba 网格（已暂停，1/30 完成）

⚠️ **瓶颈是训练，不是 bootstrap**（早期笔记写反了）：`--batch_size` 默认 **16** → 759 步/epoch，
实测 **≈19 min/epoch**，13–15 epoch 早停 ⇒ **4.1–4.8 h/格**。
- 恢复：`python scripts/run_mamba_grid.py`（自带断点续跑）。
- 降本：batch 16→64 ⇒ 约 **4×**（5.4 天 → 约 1.3 天），需要修订案 **A4** 声明「batch 只影响优化」。
- 跑完后：① 核对 30 格的 `label_map` 全为 OLD（`ptbxl_chapman/mamba/seed42,43` 的 JSON 是 09-02 遗留、schema 残缺）
  ② 重算三架构 90 格汇总 ③ 修改 ~20 处「仅 2 种架构」。

### 8.2 重训 → 重跑链（进行中）

`scripts/post_retrain_then_chain.sh`：等 2 个 `transfer_result.json` → 校验独立性 → 重建 60 格主表 →
起 `scripts/rerun_contaminated_chain.sh`。链序：E3 全量 n → E1a L2 → E2 `--no-cache` → E4 → E6 → E1b LOCO。

- 污染原件备份在 `results/*.bak_contaminated`；**重训前快照**在 `results/_pre_retrain_baseline_20260917/`。
- 🔑 **两条验收**：① `python scripts/verify_retrain_scope.py` 必须 **PASS**（只有那 2 格变，其余 58 格逐位不变）；
  ② 新 `ablation_ts_components.csv` 的 `stage=raw` 必须复现 **`0.036–0.357, mean 0.211`**。不复现就停下排查。
- ⚠️ **LOCO 未被论文引用**（`grep -c LOCO paper/main_bspc.tex` = 0），优先级最低。

### 8.3 其余

- ⏳ `docs/osf_archive_manifest.json` **已漂移 6 处 / 14**（`main_bspc.tex`、`eval_transfer.py`、`eval_l2_shift.py`、
  `step2_predictability.py`、`summarize_l2_shifts.py`、`src/data/mapping.py`）。
  早期笔记的「8 处」把「清单后**新增**文件」也算成了漂移。**已写入 `_post_manifest_corrections`**
  （完整版 `docs/OSF_MANIFEST_POST_CORRECTIONS_2026-09-17.md`；09-16 那份只看到 2 个，已标注「已被取代」）。
  ⚠️ 未变的 8 个里含 **`src/utils/calibration.py`** ⇒ **度量定义从未被改动**。
- ⏳ 补充材料包：**已排除**空占位 `c3_inceptiontime_lite_30exp.csv`、`deployment_loco_validation_smoke.csv`
  （在 `_build_supp.py` 的 `EXCLUDE_S2`，不删源文件）；
  **重跑 + 重训结束后必须重跑 `_build_supp.py` 并重签 `SHA256SUMS.txt`**。
- ⏳ `157` 的逐 cell 清单**已不可重建**（磁盘上 `l2_shift_results.json` 现为 5 种子全量，
  ts 有 **390** 个 (pair, seed, shift)）。`144 + 13` 是边际约束下的唯一解。重跑后统一 157/390 口径。
- ⏳ MI 类去留（降为 3 类 vs 维持 4 类 + 显式声明来源，待拍板）；**恢复 33 条丢失记录**（A6845–A6877，需重下语料）。
- ⏳ §real_shapley 重写（10 项清单见 `reports/REAL_SHAPLEY_AUDIT_VERDICT_2026-09-16.md`）；
  修 `rebuild_shapley_crossfit.py`（其 `delta_obs_orig` 实为 NEW 编码量，κ 是 L195 的 hack）。
- ⏳ CMPB 强化：P0 已全清；余 P1 Honesty 内容上移、P2 A1/A2 协议前置、Limitations 增列。
- ⏳ 真实短板：仅 2 种架构、无外部临床/SQI 验证、Shapley 仅合成数据验证。
- ⏳ 投稿前检查单：每个被引数字登记「来源文件 + 编码戳 + n」。
