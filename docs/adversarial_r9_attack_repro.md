# R9 轮对抗审查 · 反方攻击报告 · 维度 6：可复现性

> **审查代理**：反方挑刺代理（GLM-5.2）
> **审查对象**：`D:\A1\ecg-lab-v2\paper\main.tex` 的可复现性声明
> **审查日期**：2026-09-13
> **任务 ID**：50
> **攻击维度**：可复现性（Reproducibility）
> **立场声明**：本报告为反方攻击产物，全力挑刺，但不捏造不存在的问题。所有攻击点均有代码/论文证据支撑。

---

## 0. 审查方法与证据来源

| 证据来源 | 路径 | 用途 |
|---|---|---|
| 论文正文 | `paper/main.tex` L1782-L1981 (Conclusion), L330-L399 (Datasets/Arch), L1685-L1761 (Limitations) | 提取可复现性声明 |
| 依赖清单 | `requirements.txt` | 检查依赖版本固定 |
| 训练脚本 | `scripts/train.py` L51-L122, L585-L624 | 检查种子控制、DataLoader |
| 评估脚本 | `scripts/eval_l2_shift.py`, `scripts/run_e1a_l2_shift_full.py` | 检查种子传播 |
| 数据加载 | `src/data/datasets.py` L1-L50 | 检查数据加载可复现性 |
| Checkpoints | `checkpoints/transfer/**/transfer_result.json` (62个) | 检查元数据完整性 |
| 全仓 grep | `D:\A1\ecg-lab-v2\**\*.py` | 检查 hardcoded 路径、环境变量 |

---

## 1. 论文可复现性声明提取

### 1.1 Data availability（main.tex L1956-L1965）

> "The PTB-XL, Chapman-Shaoxing, and CPSC2018+2019 datasets are publicly available via PhysioNet/Kaggle under their respective licenses. The pre-registered protocol v2.1-A1, its hash manifest (`docs/osf_archive_manifest.json`), the revision A1 document, and the full per-experiment result files (`checkpoints/transfer/**/transfer_result.json`, `results/*.csv`) are included with the submission as supplementary material; **a public repository will accompany acceptance**."

### 1.2 Code availability

**论文中不存在独立的 "Code availability" 声明。** 仅有 Data availability 末尾的条件承诺："a public repository will accompany acceptance"。

### 1.3 BiMamba 失败披露（main.tex L383, L1693）

> "the full-resolution BiMamba run exhausted memory on an RTX 5060 (8 GB), so BiMamba does not enter the main-endpoint analysis or the architecture-robustness claim."

### 1.4 计算环境披露

- GPU：RTX 5060, 8 GB（L383, L1693, L1754）
- PyTorch/CUDA/Python 版本：**未记录**
- 训练时间：**未报告**

---

## 2. 攻击点汇总

共发现 **15 个攻击点**：P1 级 6 个，P2 级 8 个，P3 级 1 个。无 P0 级（未发现导致方案完全失败的致命问题）。

| Attack-ID | 严重级别 | 方面 | 摘要 |
|---|---|---|---|
| R9-Repro-1 | P1 | A.代码完整性 | 缺少独立 Code availability 声明，仅有条件承诺 |
| R9-Repro-2 | P1 | A.代码完整性 | 15+ 脚本含 hardcoded 路径 `D:\A1\ecg-lab-v2` |
| R9-Repro-3 | P2 | A.代码完整性 | requirements.txt 用 `>=` 未固定版本 |
| R9-Repro-4 | P2 | A.代码完整性 | PYTHONIOENCODING 环境变量依赖未文档化 |
| R9-Repro-5 | P1 | B.种子控制 | cudnn.deterministic 默认 False，未启用 |
| R9-Repro-6 | P2 | B.种子控制 | DataLoader shuffle=True 未传 generator |
| R9-Repro-7 | P2 | B.种子控制 | cudnn.benchmark 未显式设置 |
| R9-Repro-8 | P1 | C.数据可复现性 | CPSC2018+2019 无版本号/下载链接 |
| R9-Repro-9 | P2 | C.数据可复现性 | PTB-XL 38条记录缺失影响可复现性 |
| R9-Repro-10 | P2 | C.数据可复现性 | 预处理脚本未在 Data availability 中明确提及 |
| R9-Repro-11 | P2 | D.BiMamba失败 | mamba 的2个 transfer_result.json 缺少 meta 字段 |
| R9-Repro-12 | P1 | E.Checkpoints | transfer_result.json 缺少环境元数据 |
| R9-Repro-13 | P2 | E.Checkpoints | best_model.pt 缺少独立架构/数据集版本元数据 |
| R9-Repro-14 | P1 | F.计算环境 | PyTorch/CUDA/Python 版本未记录 |
| R9-Repro-15 | P1 | F.计算环境 | 训练时间未报告 |

---

## 3. 攻击点详述

### Attack-ID: R9-Repro-1
- **严重级别**: P1
- **方面**: A. 代码完整性
- **攻击描述**: 论文缺少独立的 "Code availability" 声明。Data availability 声明末尾的条件承诺 "a public repository will accompany acceptance" 不是实际可用的代码，而是**以论文被接收为前提条件的未来承诺**。SCI Q2 期刊（如 Physiol. Meas.、Comput. Biol. Med.）通常要求投稿时即提供可访问的代码仓库（GitHub/Zenodo with DOI），而非条件承诺。
- **证据**:
  - `main.tex` L1965: "a public repository will accompany acceptance."
  - `cover_letter.tex` L96: 同样表述
  - grep `Code availability` 在 main.tex 中无匹配
- **对 SCI Q2 的影响**: 多数 Q2 期刊的 code sharing policy 要求投稿时提供可访问仓库。条件承诺可能触发 "major revision" 或 desk reject。这是可复现性声明的**核心缺陷**：声明了数据可用性，但代码可用性是有条件的。

---

### Attack-ID: R9-Repro-2
- **严重级别**: P1
- **方面**: A. 代码完整性
- **攻击描述**: 至少 15 个脚本包含 hardcoded 绝对路径 `D:\A1\ecg-lab-v2`，导致代码无法在任何其他机器上直接运行。这些脚本包括分析脚本、报告生成脚本、验证脚本和主实验编排脚本。
- **证据** (grep `D:\\A1|D:/A1` 命中):
  ```
  analyze_aggregate.py:8:        root = Path(r'D:\A1\ecg-lab-v2\checkpoints\transfer')
  analyze_attacks.py:6:          root = Path(r'D:\A1\ecg-lab-v2\checkpoints\transfer')
  analyze_coverage.py:6:         root = Path(r'D:\A1\ecg-lab-v2\checkpoints\transfer')
  generate_robustness_report.py:12:  WORK_DIR = Path(r"D:\A1\ecg-lab-v2")
  generate_robustness_report_v2.py:13: WORK_DIR = Path(r"D:\A1\ecg-lab-v2")
  monitor_progress.py:5:         root = Path(r"D:\A1\ecg-lab-v2")
  paper/generate_figures.py:25:  FIG_DIR = 'D:/A1/ecg-lab-v2/paper/figures'
  paper/generate_figures.py:28:  CSV_PATH = 'D:/A1/ecg-lab-v2/results/robustness_validation_5seeds.csv'
  regenerate_stats_60exp.py:13: WORK_DIR = Path(r"D:\A1\ecg-lab-v2")
  scripts/_check_missing.py:3:   root = Path('D:/A1/ecg-lab-v2')
  scripts/_final_verdict_verify.py:11: npz_path = r"D:\A1\ecg-lab-v2\checkpoints\..."
  scripts/_opponent_attack_verify.py:25: _PROJECT_ROOT = Path(r"D:\A1\ecg-lab-v2")
  scripts/_opponent_attack_verify2.py:6: _PROJECT_ROOT = Path(r"D:\A1\ecg-lab-v2")
  scripts/_verify_mamba_E.py:3:  sys.path.insert(0, "D:/A1/ecg-lab-v2")
  scripts/_verify_mamba_review.py:3: sys.path.insert(0, "D:/A1/ecg-lab-v2")
  scripts/run_all_experiments.py:85: cwd=r"D:\A1\ecg-lab-v2"
  data/downloads/_sha256_ptbxl.py:4: root = Path(r"D:/A1/ecg-lab-v2/data/downloads/ptb-xl-1.0.3")
  ```
- **对 SCI Q2 的影响**: 审稿人克隆仓库后无法直接运行分析脚本复现图表。虽然核心训练/评估脚本（train.py, eval_transfer.py）使用相对路径，但**论文图表生成脚本**（paper/generate_figures.py）含 hardcoded 路径，直接阻断图表复现。这是可复现性的**实际阻断点**。

---

### Attack-ID: R9-Repro-3
- **严重级别**: P2
- **方面**: A. 代码完整性
- **攻击描述**: `requirements.txt` 使用 `>=` 而非 `==` 固定依赖版本。不同时间 `pip install -r requirements.txt` 会安装不同版本，可能导致数值结果差异（尤其 PyTorch、numpy 的 RNG 行为可能跨版本变化）。
- **证据** (`requirements.txt` 全文):
  ```
  torch>=2.4.0
  numpy>=1.26.0
  scipy>=1.12.0
  scikit-learn>=1.4.0
  mambapy==1.2.0          # 仅此一个用 == 固定
  pandas>=2.2.0
  wfdb>=4.1.0
  matplotlib>=3.8.0
  seaborn>=0.13.0
  ...
  ```
  仅 `mambapy==1.2.0` 用精确版本，其余 10 个核心依赖均用 `>=`。
- **对 SCI Q2 的影响**: 中等。审稿人可能安装 torch 2.7.0（而非作者的 2.4.x），cudnn 行为差异可能导致 bit-level 不可复现。建议提供 `requirements.lock.txt` 或 `environment.yml`。

---

### Attack-ID: R9-Repro-4
- **严重级别**: P2
- **方面**: A. 代码完整性
- **攻击描述**: `scripts/run_all_experiments.py` 和 `scripts/run_e1a_wrapper.py` 设置了 `PYTHONIOENCODING=utf-8` 环境变量，但 README.md 和论文均未说明这是 Windows 环境的必需配置。在未设置此变量的 Windows PowerShell 环境下，中文日志输出可能触发 UnicodeEncodeError。
- **证据**:
  ```
  scripts/run_all_experiments.py:17: os.environ["PYTHONIOENCODING"] = "utf-8"
  scripts/run_all_experiments.py:86: env={**os.environ, "PYTHONIOENCODING": "utf-8"}
  scripts/run_e1a_wrapper.py:5: env['PYTHONIOENCODING'] = 'utf-8'
  ```
  README.md L34-L48 的"快速开始"未提及此环境变量。
- **对 SCI Q2 的影响**: 较低。仅影响 Windows 用户，Linux/Mac 默认 UTF-8。但论文未声明计算平台，审稿人可能误判。

---

### Attack-ID: R9-Repro-5
- **严重级别**: P1
- **方面**: B. 种子控制
- **攻击描述**: `set_seed()` 函数的 `deterministic` 参数默认为 `False`，且所有调用点均未传 `deterministic=True`。这意味着 `torch.backends.cudnn.deterministic` 保持默认 `False`，CUDA 上的卷积操作（InceptionTime 和 ResNet1D 均含卷积）**不保证 bit-level 可复现**。虽然 `set_seed` 设置了 `torch.manual_seed` 和 `torch.cuda.manual_seed_all`，但 cuDNN 的非确定性算法选择仍可能导致同种子不同运行的权重微小差异。
- **证据**:
  - `scripts/train.py` L51-L60:
    ```python
    def set_seed(seed: int, deterministic: bool = False):
        import random
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        if deterministic:                    # 默认不进入此分支
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
            os.environ['CUBLAS_WORKSPACE_CONFIG'] = ':4096:8'
    ```
  - `scripts/train.py` L595: `set_seed(args.seed)` — 未传 `deterministic=True`
  - 所有其他调用点（eval_l2_shift.py L94, eval_transfer.py L96, run_e1a_l2_shift_full.py L340 等）均未传 `deterministic=True`
- **对 SCI Q2 的影响**: 严重。论文声称"5-seed coverage"和"51/60 seed experiments"，但若 cuDNN 非确定性导致同种子不可复现，则 seed 实验的**可复现性根基被动摇**。审稿人重跑 seed=42 可能得到不同的 ΔECE_OOD，进而 51/60 的计数可能变化。这是种子控制维度的**核心缺陷**。

---

### Attack-ID: R9-Repro-6
- **严重级别**: P2
- **方面**: B. 种子控制
- **攻击描述**: `create_dataloader()` 函数创建 DataLoader 时未接受/传递 `generator` 参数。训练集 DataLoader 使用 `shuffle=True`，其 shuffle 随机性隐式依赖全局 `torch` RNG。虽然 `set_seed` 设置了全局种子，但最佳实践是显式传入 `generator=torch.Generator().manual_seed(seed)`，尤其在 `num_workers > 0` 时可避免 worker 进程的 RNG 状态不确定。
- **证据**:
  - `scripts/train.py` L107-L122:
    ```python
    def create_dataloader(dataset, batch_size=32, num_workers=0,
                          shuffle=True, drop_last=False):
        return DataLoader(dataset, batch_size=batch_size, shuffle=shuffle,
                          num_workers=num_workers, pin_memory=True,
                          drop_last=drop_last)   # 无 generator 参数
    ```
  - `scripts/train.py` L621: `'train': create_dataloader(..., shuffle=True, ...)` — 无 generator
  - 对比：`SyntheticECGDataset` L96 正确使用了 `g = torch.Generator().manual_seed(seed)`，说明作者知道最佳实践，但未在 DataLoader 层面应用
- **对 SCI Q2 的影响**: 中等。当前 `num_workers=0`（默认）时影响较小，但若审稿人用 `num_workers>0` 重跑，shuffle 顺序可能不同。

---

### Attack-ID: R9-Repro-7
- **严重级别**: P2
- **方面**: B. 种子控制
- **攻击描述**: `torch.backends.cudnn.benchmark` 未显式设置为 `False`。虽然 PyTorch 默认为 `False`，但未显式声明意味着若用户环境曾全局开启 benchmark，卷积算法选择将不确定。`set_seed` 的 `deterministic=True` 分支会设置 `benchmark=False`，但该分支从未被激活。
- **证据**: `scripts/train.py` L51-L60，`benchmark` 仅在 `deterministic=True` 分支内设置
- **对 SCI Q2 的影响**: 较低。默认值正确，但缺乏防御性编程。

---

### Attack-ID: R9-Repro-8
- **严重级别**: P1
- **方面**: C. 数据可复现性
- **攻击描述**: CPSC2018+2019 数据集未指定具体版本号或下载链接。PTB-XL 明确标注 "v1.0.3"（L335），Chapman-Shaoxing 标注 "version 1.0.0"（L2220 bibitem），但 CPSC2018+2019 仅写"CPSC2018+2019"（L346），无版本号、无 PhysioNet/figshare DOI、无下载日期。CPSC2018 和 CPSC2019 是两个独立挑战赛数据集，其"合并"方式（拼接？去重？）也未说明。
- **证据**:
  - `main.tex` L346: "\item \textbf{CPSC2018+2019}: patient-wise split; HYP class extremely rare..." — 无版本/链接
  - `main.tex` L335: PTB-XL 有 "v1.0.3"
  - `main.tex` L2220: Chapman 有 "version 1.0.0"
  - grep `CPSC2018|CPSC2019|cpsc.*download` 在 main.tex 中无版本/链接匹配
- **对 SCI Q2 的影响**: 严重。审稿人无法确定下载哪个版本的 CPSC 数据。CPSC2018 有 6 个导联子集和 12 导联版本，版本不明确将导致预处理输出不同。三个数据集中**唯一未指定版本**的，不对称的可复现性声明。

---

### Attack-ID: R9-Repro-9
- **严重级别**: P2
- **方面**: C. 数据可复现性
- **攻击描述**: PTB-XL 官方发布 21,837 条记录，但论文使用的下载副本仅 21,799 条（38条缺失）。虽然论文披露了这一"provenance limitation"（L337），但这38条缺失记录的**具体身份未记录**，审稿人无法验证是否为随机缺失或系统性缺失（如某类记录缺失将影响类别平衡）。
- **证据**:
  - `main.tex` L335-L338: "the official release contains 21,837 records; the downloaded `ptbxl_database.csv` copy contains 21,799 (a 38-record deficit in the source CSV, disclosed as a provenance limitation)"
  - 缺失记录的 ecg_id 列表未在 supplementary 中提及
- **对 SCI Q2 的影响**: 中等。38/21837 ≈ 0.17%，影响较小，但缺失记录的身份不透明，无法排除系统性偏差。

---

### Attack-ID: R9-Repro-10
- **严重级别**: P2
- **方面**: C. 数据可复现性
- **攻击描述**: 预处理脚本（preprocess_ptbxl.py, preprocess_chapman.py, preprocess_cpsc.py）存在于 `scripts/` 目录，但 Data availability 声明（L1956-L1965）未明确提及这些脚本。Honesty Declaration item 5（L1948-L1952）仅提及 `preprocess_cinc2021.py` 是第三方 SafeECGMatch 的脚本，未说明本仓库的三个预处理脚本的可复现性。
- **证据**:
  - 预处理脚本存在：`scripts/preprocess_ptbxl.py`, `scripts/preprocess_chapman.py`, `scripts/preprocess_cpsc.py`
  - Data availability 声明（L1956-L1965）未提及任何预处理脚本
  - Honesty Declaration item 5 仅提及 `preprocess_cinc2021.py`（第三方）
- **对 SCI Q2 的影响**: 中等。审稿人需自行发现预处理脚本。从原始 PhysioNet 数据到 npy 格式的转换链未在可复现性声明中显式化。

---

### Attack-ID: R9-Repro-11
- **严重级别**: P2
- **方面**: D. BiMamba 失败
- **攻击描述**: BiMamba 因 OOM 失败已在论文中透明披露（L383, L1693），处理方式合理。但 mamba 的 2 个 transfer_result.json（ptbxl_chapman/mamba/seed42, seed43）缺少 `meta` 字段，无法审计其 bootstrap 参数（n_bootstrap, bci_method）。60 个主实验的 transfer_result.json 均含 meta 字段，但 mamba 的 2 个不含，存在元数据不一致。
- **证据**:
  - 统计：62 个 transfer_result.json，60 个含 meta 字段，2 个不含
  - 不含 meta 的 2 个：`checkpoints/transfer/ptbxl_chapman/mamba/seed42/transfer_result.json`, `seed43/transfer_result.json`
  - BiMamba 失败披露：L383, L1693
- **对 SCI Q2 的影响**: 较低。mamba 不进入主分析，但元数据不一致违反"所有实验同等审计"原则。

---

### Attack-ID: R9-Repro-12
- **严重级别**: P1
- **方面**: E. Checkpoints
- **攻击描述**: transfer_result.json 包含实验结果元数据（source/target/arch/seed/methods/ts/meta），但**缺少环境元数据**：GPU 型号、CUDA 版本、PyTorch 版本、训练时间、数据集版本哈希。`meta` 字段仅记录 bootstrap 参数（n_bootstrap=10000, bci_method=bca, ts_fit, metric），不记录计算环境。这意味着即使有 checkpoint，也无法验证其产生环境是否与当前环境一致。
- **证据** (transfer_result.json 样本字段):
  ```json
  {
    "source": "chapman", "target": "cpsc", "arch": "inceptiontime", "seed": 42,
    "num_classes": 4, "subspace": [...], "label_map": {...},
    "n_id": 3958, "n_ood": 2057, "id_acc": ..., "ood_acc": ...,
    "methods": { "ts": { ..., "meta": {
      "n_bootstrap": 10000, "bci_method": "bca",
      "ts_fit": "source_cal", "metric": "smooth_ece_0.45*(n/2000)^-0.2"
    }}}
  }
  ```
  缺少：`gpu`, `cuda_version`, `torch_version`, `train_time_sec`, `dataset_hash`, `code_commit`
- **对 SCI Q2 的影响**: 严重。可复现性的核心是"环境-代码-数据-结果"四元组可追溯。transfer_result.json 仅记录结果和部分算法参数，不记录环境，无法构成完整 provenance 链。

---

### Attack-ID: R9-Repro-13
- **严重级别**: P2
- **方面**: E. Checkpoints
- **攻击描述**: 62 个 best_model.pt 文件存在，但缺少独立的模型架构/超参数元数据文件。模型架构信息隐含在代码中（`src/models/ecg_classifier.py`），但 checkpoint 本身不记录：模型参数量、n_filters（32 vs 48）、训练超参数（lr, epochs, batch_size, weight_decay）。论文 L1754 提到 n_filters 从 48 降级到 32，但这一关键架构选择未记录在 checkpoint 元数据中。
- **证据**:
  - 62 个 best_model.pt 存在（统计确认）
  - 无独立的 `model_config.json` 或 `hparams.yaml` 与每个 checkpoint 配对
  - n_filters=32 降级仅在论文 L1754 文本中记录
- **对 SCI Q2 的影响**: 中等。审稿人加载 best_model.pt 后需逆向推断架构，增加复现门槛。

---

### Attack-ID: R9-Repro-14
- **严重级别**: P1
- **方面**: F. 计算环境
- **攻击描述**: 论文未记录 PyTorch、CUDA、Python 版本。GPU 型号（RTX 5060, 8GB）已记录，但软件栈版本缺失。PyTorch 2.4 vs 2.6 的 cuDNN 行为差异可能影响数值结果。`requirements.txt` 仅给出 `torch>=2.4.0`，未记录实际使用版本。
- **证据**:
  - grep `PyTorch|torch.*2\.|cuda.*1[0-9]|python.*3\.|Python 3` 在 main.tex 中无匹配
  - `requirements.txt`: `torch>=2.4.0`（未固定实际版本）
  - GPU 已记录：RTX 5060, 8GB（L383, L1693, L1754）
- **对 SCI Q2 的影响**: 严重。可复现性声明的标准要求是完整计算环境记录。软件版本缺失是 Q2 期刊 reproducibility checklist 的常见拒稿点。

---

### Attack-ID: R9-Repro-15
- **严重级别**: P1
- **方面**: F. 计算环境
- **攻击描述**: 论文未报告训练时间（wall-clock time per experiment）。60 个实验的总计算成本、单实验训练时间、推理时间均未提及。这影响：(1) 审稿人评估复现所需的计算资源；(2) 读者判断方法的实际部署成本；(3) 与 Baseline 的效率比较。
- **证据**:
  - grep `training time|wall.clock|runtime|compute time|GPU hours` 在 main.tex 中无匹配
  - transfer_result.json 无 `train_time_sec` 字段
- **对 SCI Q2 的影响**: 严重。Q2 期刊通常要求报告计算成本。缺失训练时间使读者无法评估复现可行性——"60 个实验"听起来不多，但若每个需 24 小时，总成本 1440 GPU-hours，并非 trivial。

---

## 4. 七维度攻击总结

| 攻击维度 | 发现攻击点 | 最严重级别 | 状态 |
|---|---|---|---|
| 1. 反例构造 | 0 | — | 未发现可复现性声明的直接反例（声明本身是真实的） |
| 2. 逻辑断链 | 1 (R9-Repro-1) | P1 | "a public repository will accompany acceptance" → 实际可用代码：逻辑断链 |
| 3. 隐含假设 | 3 (R9-Repro-5,6,7) | P1 | 隐含假设"set_seed 足够保证可复现"，但 cuDNN 非确定性打破此假设 |
| 4. 边界失效 | 2 (R9-Repro-2,4) | P1 | Windows/其他机器边界：hardcoded 路径失效 |
| 5. 自相矛盾 | 1 (R9-Repro-8) | P1 | PTB-XL/Chapman 有版本号，CPSC 无：可复现性声明内部不一致 |
| 6. 量级错误 | 1 (R9-Repro-15) | P1 | 未报告训练时间，无法评估复现成本量级 |
| 7. 语义偏移 | 1 (R9-Repro-12) | P1 | "per-experiment result files" 暗示完整 provenance，实际缺环境元数据 |

---

## 5. 对 SCI Q2 投稿的总体影响评估

### 5.1 致命问题（P0）：无
未发现导致可复现性声明完全虚假的致命问题。论文的核心可复现性资产（60 个 transfer_result.json + best_model.pt + 预处理脚本）确实存在。

### 5.2 严重问题（P1）：6 个
- **R9-Repro-1** (无 Code availability)：可能触发 desk reject 或 major revision
- **R9-Repro-2** (hardcoded 路径)：阻断图表复现
- **R9-Repro-5** (cudnn.deterministic=False)：动摇 seed 实验的可复现根基
- **R9-Repro-8** (CPSC 无版本)：数据可复现性缺口
- **R9-Repro-12** (缺环境元数据)：provenance 链不完整
- **R9-Repro-14** (软件版本未记录)：reproducibility checklist 常见拒稿点
- **R9-Repro-15** (训练时间未报告)：计算成本不透明

### 5.3 修复建议（反方提出，供正方参考）

1. **立即提供可访问的代码仓库**（GitHub + Zenodo DOI），将 "will accompany acceptance" 改为实际 URL
2. **将所有 hardcoded 路径替换为 `Path(__file__).parent.parent` 或环境变量**
3. **在 `set_seed` 调用时传 `deterministic=True`**，或在论文中声明"bit-level 可复现性非本工作目标，seed 可复现性指统计意义上的可复现"
4. **补充 CPSC2018+2019 的版本号、下载链接、合并方式**
5. **在 transfer_result.json 中增加环境元数据字段**（gpu, cuda_version, torch_version, train_time_sec, code_commit, dataset_hash）
6. **在论文中报告 PyTorch/CUDA/Python 版本和训练时间**
7. **提供 `requirements.lock.txt` 或 `environment.yml`** 固定全部依赖版本

---

## 6. 反方声明

我尝试了全部 7 个攻击维度，发现 **15 个攻击点**（6 个 P1，8 个 P2，1 个 P3），未发现 P0 级致命问题。论文的可复现性**基础设施存在**（checkpoints、预处理脚本、种子函数），但在**可复现性声明的完整性、种子控制的严格性、计算环境的记录、代码可用性的实际性**四个方面存在严重缺口。

**核心结论**：论文的可复现性声明是"部分可复现"而非"完全可复现"。最严重的缺陷是 **R9-Repro-1**（无独立 Code availability 声明，仅有条件承诺）和 **R9-Repro-5**（cuDNN 非确定性未禁用，seed 实验的 bit-level 可复现性不保证）。这两个问题组合起来意味着：即使审稿人获得代码，重跑同一 seed 也可能得到不同的 51/60 计数。

**对 SCI Q2 的判断**：当前状态可能触发 major revision。若修复 R9-Repro-1, 2, 5, 8, 14, 15 六个 P1 问题，可复现性可达到 Q2 期刊要求。

---

*报告生成时间：2026-09-13*
*反方代理：GLM-5.2，session 42f2965a-a2e6-4b3e-b425-abaa86d00706*
