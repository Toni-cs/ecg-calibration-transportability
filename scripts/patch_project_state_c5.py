#!/usr/bin/env python
"""Patch docs/PROJECT_STATE_2026-09-17.md with the C5 gate facts settled on
2026-09-18 evening, and fix the stale '9 counter-examples' count.

Byte-level: docs/*.md has no .gitattributes rule and core.autocrlf=true here.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "PROJECT_STATE_2026-09-17.md")

S5_ANCHOR = """- \U0001f511 **论文自身锚点证明其 raw ECE 口径本就是 OLD**：case study 引用的 `0.3160/0.3144/0.0649`
  与 OLD 重算一致（污染 CSV 给的是 `0.3747/0.3685/0.0832`）。

## 6. 已裁决事项"""

S5_NEW = """- \U0001f511 **论文自身锚点证明其 raw ECE 口径本就是 OLD**：case study 引用的 `0.3160/0.3144/0.0649`
  与 OLD 重算一致（污染 CSV 给的是 `0.3747/0.3685/0.0832`）。
- **C5 门控名册（2026-09-18 晚定稿）**：通过层 = `chapman→cpsc/RN`、`chapman→ptbxl/IT`、
  `chapman→ptbxl/RN`、`cpsc→ptbxl/IT`、`cpsc→ptbxl/RN`、`ptbxl→cpsc/IT`、`ptbxl→cpsc/RN`（**7/12**）。
  **Layer 2 基线 = 目标域多数类、取 OOD 测试划分**：cpsc **0.5280**(K4)｜ptbxl **0.4085**(K4)/
  **0.3987**(K5)｜chapman **0.7125**(K4)/**0.6963**(K5)。
  ⚠️ **`0.411` 是 PTB-XL 源域 cal 划分值（0.4107），不是目标 OOD 值 —— 已全部改为 `0.409`。**
  逐格分解：**L1 拒 10 + L1 过 L2 拒 26 + 两层都过 24 = 60**；全 5 seed 通过层 **1/12**。
  10 个反例 = **全部 Layer-1 拒绝**，其中 **7 个**同时不过 Layer 2。
- **准确率统计（重训后，2026-09-18 晚改）**：OOD acc mean **0.540**／median **0.546**／range
  **0.348–0.701**；ID−OOD 平均降幅 **0.234**（max **0.412**）；`cpsc→ptbxl` 均值 **0.423**。
  ⚠️ 旧值 `0.388–0.701`／`0.236`／`0.424` 是**重训前**的，**已作废**（传播时漏了准确率段）。

## 6. 已裁决事项"""

S6_ANCHOR = """- ⚠️ **K=5 恰当且仅当 pair = {chapman, ptbxl}**（任何含 cpsc 的 pair 一律 K=4）。
  源为 chapman/ptbxl 时 `cal_labels` 跨目标不同，**是 K 不同所致，不是缺陷**。

## 7. 已推翻（勿沿用）"""

S6_NEW = """- ⚠️ **K=5 恰当且仅当 pair = {chapman, ptbxl}**（任何含 cpsc 的 pair 一律 K=4）。
  源为 chapman/ptbxl 时 `cal_labels` 跨目标不同，**是 K 不同所致，不是缺陷**。
- ✅ **C5 名册已修 + 「stratum-mean」口径已写死（2026-09-18 晚）**：原名册在**任何阈值下都不可能成立**
  （要求 `Chapman→CPSC/IT` 通过而 `Chapman→CPSC/RN` 不通过 ⇒ 需 `b ≤ 0.4882` 且 `b > 0.5316`）。
  ⚠️ **「7/12」是口径依赖的**：层内**指标均值**过阈值 → **7/12**（论文现用）／
  逐 seed 通过率（各层分别）→ **6/12**／（两层联合）→ **5/12**。差异格 `cpsc→ptbxl/RN`。
  ⚠️ 层均值口径下 **12/12 层**平均 ΔECE 均为正（最小 +0.00232）⇒ **Layer 1 在层级空转**，
  层级门控实质是**单层**门控 —— 已在正文披露。
  复算：`scripts/verify_c5_gate_roster.py`、`scripts/compare_gate_definitions.py`；
  完整清单 `docs/CMPB_SUBMISSION_READINESS_2026-09-18.md` §8。
- ✅ **OSF DOI（2026-09-18 实测）**：项目 `10.17605/OSF.IO/53H64` ✅200；
  注册 `10.17605/OSF.IO/WJZ3Y` ✅200（OSF Preregistration，2026-09-14，公开）。
  ⚠️ 截图上的 `10.17605/OSF.IO/NGJE2Y` **❌404 不解析，不得引用**（项目 53h64 下只有 wjz3y 一个注册）。
  论文与 cover letter 引项目 DOI `53H64`。

## 7. 已推翻（勿沿用）"""


def main() -> int:
    raw = open(DOC, "rb").read()
    if b"\r\n" in raw:
        print("ABORT: document contains CRLF")
        return 1
    text = raw.decode("utf-8")

    # 1. stale counter-example count in section 5
    old_count = "；9 反例 raw ECE"
    if text.count(old_count) != 1:
        print(f"ABORT: counter-example count matched {text.count(old_count)} times")
        return 1
    text = text.replace(old_count, "；10 反例 raw ECE")

    # 2. section 5 additions
    if text.count(S5_ANCHOR) != 1:
        print(f"ABORT: S5 anchor matched {text.count(S5_ANCHOR)} times")
        return 1
    text = text.replace(S5_ANCHOR, S5_NEW)

    # 3. section 6 additions
    if text.count(S6_ANCHOR) != 1:
        print(f"ABORT: S6 anchor matched {text.count(S6_ANCHOR)} times")
        return 1
    text = text.replace(S6_ANCHOR, S6_NEW)

    out = text.encode("utf-8")
    if b"\r\n" in out:
        print("ABORT: result would contain CRLF")
        return 1
    open(DOC, "wb").write(out)
    print(f"written: {DOC} ({len(raw)} -> {len(out)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
