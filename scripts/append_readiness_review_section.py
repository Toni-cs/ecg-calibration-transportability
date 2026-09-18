#!/usr/bin/env python
"""Append the 2026-09-18 evening review section to the CMPB readiness report.

Byte-level append: docs/*.md has no .gitattributes rule and this machine runs
core.autocrlf=true, so a text-mode edit would flip every line to CRLF.
"""
from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "CMPB_SUBMISSION_READINESS_2026-09-18.md")

SECTION = """
---

## 8. 【2026-09-18 晚】复审轮：口径定死 + 两处重训遗漏

用户附 OSF 截图后要求「补全 + 全部可改的都改 + 再审查一遍」。本轮结果如下。

### 8.1 已改（`paper/main_bspc.tex`，21 增 11 删，行尾保持 LF）

| 处 | 原文 | 改为 | 依据 |
|---|---|---|---|
| `:1533` Layer 2 定义 | `PTB-XL $0.411$` | `PTB-XL $0.409$` | §8.2 |
| `:1533` Layer 2 定义 | `the target-corpus majority-class accuracy (` | 加 `measured on the same OOD evaluation set as acc_OOD` | 钉死口径 |
| `:1544` 名册段 | `7/12 pass both layers at the stratum-mean level` | 显式写出「层内**指标均值**过阈值」，并披露逐 seed 口径给 6/12（分层）或 5/12（联合） | §8.3 |
| `:1544` 名册段 | （无） | 加「**层均值口径下 Layer 1 被全部 12 层通过**，层级判定完全由 Layer 2 决定」 | §8.3 |
| `:1550` 最强拒绝例 | `acc=0.657 < 0.713` | `< 0.696` | `ptbxl→chapman` 是 **K=5** 对 |
| `:192` 摘要 C5 | `acc=0.657 < 0.713` | `< 0.696` | 同上 |
| `:1943` 准确率段 | `range 0.388--0.701` | `0.348--0.701` | §8.4 |
| `:1944` 准确率段 | `drop is 0.236` | `0.234` | §8.4 |
| `:1946` | `PTB-XL 0.411` | `0.409` | §8.2 |
| `:1949` | `0.424 vs.\\ 0.411 (0.013` | `0.423 vs.\\ 0.409 (0.014` | 重训后均值 + 正确基线 |
| `:1951` | `(both well below 0.713)` | `0.619 vs.\\ 0.713 and ... 0.620 vs.\\ 0.696, both well below their baselines` | 两方向基线不同（K4 / K5） |

**编译复验**：两遍 `pdflatex` → **68 页、0 undefined、0 warning、0 error、2 Overfull**（与改前逐项一致）。

### 8.2 【新发现】PTB-XL 基线 `0.411` 是**源域 cal 划分**的值，不是目标 OOD 划分

| PTB-XL K=4 | 值 | 性质 |
|---|---|---|
| OOD **test** 划分多数类（应采用的） | **0.4085** | 与 `acc_OOD` 同一集合 |
| 源域 **cal** 划分多数类 | 0.4107 ≈ **0.411** | 论文现用值 ⇒ 源域残留 |

旁证：CPSC 用的是 **0.5280**（目标 test 划分），而非 cal 划分的 0.5287 ⇒ 论文既定口径本就是**目标 OOD 测试划分**，只有 PTB-XL 一格脱轨。

**判定无变化**（`cpsc→ptbxl` 两层余量 +0.0244 / +0.0041，换基线后仍为正），故这是精度修正而非结论修正。

### 8.3 【新发现】「7/12」对口径极敏感：7 / 6 / 5 三种都成立

| 口径 | 通过层数 |
|---|---|
| **C：层内指标均值过阈值**（论文现用，已在正文写死） | **7/12** |
| A：逐 seed 通过率的层内多数（各层分别） | 6/12 |
| B：逐 seed 两层**联合**通过率的层内多数 | 5/12 |

差异格：`cpsc→ptbxl/ResNet1D`（C 过：均值 acc 0.4126 ≥ 0.4085，余量 +0.0041；A 不过：L2 通过率仅 0.40）。

**已在正文显式披露 A / B 两个数**，避免审稿人换口径复算得 6/12 而判为不一致。

**并披露**：层均值口径下 **12/12 层**的平均 ΔECE 均为正（最小 `cpsc→chapman/ResNet1D` **+0.00232**），
即 Layer 1 在层级不筛任何东西 ⇒ 层级门控实质是**单层（Layer 2）**门控。逐格层面 Layer 1 仍有 10 个拒绝。

### 8.4 【新发现】准确率统计段是**重训前的**，重训后未同步

用重训前的 2 格（`checkpoints/_retrain_backup_20260917/seed{42,43}`）替换后复算得
`mean 0.5402 / median 0.5459 / range 0.388–0.701 / drop_mean 0.2356 / drop_max 0.4122`
—— **与论文原文逐一吻合** ⇒ 确认该段停留在重训前。

| 量 | 重训前（论文原值） | 重训后（已改） |
|---|---|---|
| OOD acc range | 0.388–0.701 | **0.348–0.701** |
| ID−OOD 平均降幅 | 0.236 | **0.234** |
| `cpsc→ptbxl` 均值 | 0.424 | **0.423** |
| mean / median / drop_max | 0.540 / 0.546 / 0.412 | 不变 |

根因：`cpsc→ptbxl/InceptionTime/seed42` 的 `ood_acc` 由 **0.4264 → 0.3481**（seed43 由 0.4009 → 0.4656），
而重训传播当时只覆盖 ΔECE 类数字，**未覆盖准确率统计段**。

### 8.5 本轮新增复算脚本

- `scripts/verify_c5_gate_roster.py` —— 从 60 个 `transfer_result.json` 独立复算门控分解（10 / 26 / 24）与反例集，基线由修复后的 npz 标签重推。
- `scripts/compare_gate_definitions.py` —— 三口径对照（7 / 6 / 5）。
- `scripts/patch_baseline_and_gate_convention.py` —— 本轮 4 处补丁（唯一命中断言 + LF 保持）。

**逐项复算通过**：10 反例｜`ood_acc ≤ 0.50` 7/10｜ID−OOD gap ≥ 0.18 8/10｜raw ECE > 0.25 5/10｜
逐格两层都过 24/60｜L1 过但 L2 不过 26｜全 5 seed 通过层 1/12｜3 of 6 方向低于基线。

### 8.6 仍未改

- 🔴 **#49**：§real_shapley 的 +0.29 / +0.31 / 20.86×（`decompose_benefit` 的 `(slope, intercept)` 口径未定）。
- ⏳ 链路 **E2 已死**（见 §4.1），验收② 仍不可执行。

> §7 优先级表第 2、3 项（C5 名册 + 基线口径、反例切分判据）**已由本轮结清**，见 §8.1。
"""


def main() -> int:
    raw = open(DOC, "rb").read()
    if b"\r\n" in raw:
        print("ABORT: document already contains CRLF")
        return 1
    if b"## 8. " in raw:
        print("ABORT: section 8 already present")
        return 1
    out = raw + SECTION.encode("utf-8")
    if b"\r\n" in out:
        print("ABORT: result would contain CRLF")
        return 1
    open(DOC, "wb").write(out)
    print(f"appended {len(SECTION.encode('utf-8'))} bytes -> {DOC}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
