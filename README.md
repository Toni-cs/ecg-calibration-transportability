# ECG 校准修复边界研究

预注册协议驱动的 ECG 分类"校准修复收益 ID→OOD 衰减"研究：
把修复收益的衰减分解为 **slope / intercept / prevalence** 三个可干预成分，
量化其贡献占比，并输出"移位类型 × 主导成分 × 推荐再校准策略"的部署判据。

- 预注册协议：`docs/EXPERIMENT_PROTOCOL.md`（v2.0，含修订记录与对抗审查轮次记录）
- 目标叙事与 claim 边界：协议 §0（novelty 三步链的安全表述）
- 状态：**真实数据已预处理（PTB-XL 21522条 + Chapman 20243条），主架构S1冒烟跑通，正式pilot进行中**

## 目录结构

```text
docs/
  EXPERIMENT_PROTOCOL.md     预注册协议（主文档，先读这个）
  vendor_safeecgmatch.md     第三方论文 SafeECGMatch 的原 README（本仓库复用其运行时代码）
src/
  data/                      数据加载与患者级划分（190码表/泄漏断言/四分割）
  models/                    BiMamba 主干 + ECG 分类头（T≡1 冻结训练）
  utils/
    calibration.py           校准原语：TS/Platt/ECE/SmoothECE/BCa benefit_inference/两层bootstrap
    calibration_methods.py   9 方法注册表（isotonic/dirichlet/saerens/oracle/...）
    decomposition.py         三成分分解估计器 v3（KZ校正/析因/Shapley/bootstrap CI/纠缠演示）
scripts/
  train.py                   端到端训练 + 主终点（ΔECE 配对 BCa bootstrap，B=10,000）
  validate_decomposition.py  27 格合成验证（结果治理见下）
  preprocess_cinc2021.py     [vendor] CINC2021 预处理
  run_paper_benchmarks.py    [vendor] SafeECGMatch 基准入口（与本协议网格无关）
results/                     产物（gitignore；命名规范见下）
```

## 快速开始

```bash
pip install -r requirements.txt

# 27 格合成验证（含 bootstrap CI 与纠缠区演示，约 4 分钟）
python scripts/validate_decomposition.py --boot 500

# 真实校准集量级（信息模式：FAIL → exit 2）
python scripts/validate_decomposition.py --n 500 --boot 0

# 端到端训练 + 主终点推断（合成 smoke）
python scripts/train.py --epochs 5 --two-layer

# 全量测试（输出写 tmp，不触碰 results/）
python -m pytest tests/ -q
```

## 结果治理规范（R 轮修复后生效）

- 产物文件名**必须含样本量**：`decomposition_validation_n{n}.csv`、
  `decomposition_error_map_n{n}.png`——不同 n 的运行互不覆盖
- CSV 自述（含 `n`/`seed` 列）；`decomposition_validation.csv`（无 n 后缀）是
  2026-08 覆盖事故的遗留物，内容为 n=500 运行，**勿引用**
- `*_rerun_*` / `*_postfix_*` 为事故期间的手工存档（两者哈希相同，v2 版本结果）
- 测试通过 `--output tmp` 隔离，pytest 不再覆盖 `results/`

## 诚实性声明（对抗审查产物，投稿前须维持）

0. **R8 独立对抗审计（2026-09-07）**：三轮对抗审计（6 路攻击→交叉对质→端到端重演封口）确认底层数据真实（最难反例全栈重演一致至 ~1e-17）、主终点计量链合规，但发现预注册"写死"条款兑现率低（percentile 替代 BCa、TOST/G/两层 bootstrap 缺席、边界判据 48.3% 未通过却宣称 robust 等）与论文叙事失实若干处——21 处论文修复已执行（main.tex 重编译通过），偏离已登记协议 §11.5-A2 行，遗留事项与命令见 `docs/ROUND8_AUDIT_AND_FIXES.md`。

1. `MAPE_π` 是**设计校验**（重采样常量回读），非估计量能力检验；π 的独立恢复
   （BBSE/EM）为遗留项（协议 §13）
2. Shapley 占比在 `share_reliable=False` 格**不可作占比解读**；排序判定用绝对值 CI
3. 门槛 `gate(n)` 是启发式缩放，**不是 3σ 容差**；n=500 实测违率约 22%（信息模式）
4. "机制"措辞以 §8 三条腿全部兑现为条件：腿 1/2 已兑现，腿 3 的合成部分
   （bootstrap CI + 纠缠演示）已兑现，**cross-fitting 待真实数据**（§13 已登记）
5. 本仓库 `scripts/preprocess_cinc2021.py`、`run_paper_benchmarks.py`、
   `resources/`、`assets/` 来自第三方 SafeECGMatch 发布（原 README 见
   `docs/vendor_safeecgmatch.md`），与本协议实验网格无关

## 引用与相关

协议强制引用锚点与最近邻对比清单见 `docs/EXPERIMENT_PROTOCOL.md` §0。