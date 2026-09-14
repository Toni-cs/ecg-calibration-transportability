# Adversarial Review R9 — LaTeX/Formatting Quality Attack Report

**Reviewer**: Round 9 Adversarial Agent (反方挑刺代理)
**Target**: `D:\A1\ecg-lab-v2\paper\main.tex` (2187 lines, elsarticle template)
**Attack Dimension**: 8 — LaTeX/Formatting Quality
**Date**: 2026-09-13
**Verdict**: **ATTACK SUCCESSFUL** — 1 P0 (compile-breaking) + 6 P1 + 7 P2 + 4 P3 issues found

---

## Executive Summary

对 `main.tex` 执行了 7 个攻击维度的全量检查。发现 **1 个致命编译错误**（未定义引用导致 PDF 中显示 `??`），**6 个重要格式问题**（3 个图从未被引用、2 处重复句子、术语/表示法不一致），以及多个次要问题。论文在引用完整性（\cite/\bibitem 全匹配）、图片文件存在性（72/72 存在）、表格 caption 位置（7/7 正确）方面通过检查，但在交叉引用、术语一致性和数字格式方面存在显著缺陷。

---

## Attack Results by Severity

### P0 — 致命（编译失败 / PDF 不可发表）

#### R9-LaTeX-1: 未定义的交叉引用 `\ref{sec:ncv-methods}`

| Field | Value |
|-------|-------|
| **Severity** | P0 — Fatal |
| **Location** | Line 2194 |
| **Attack Type** | 逻辑断链 + 边界失效 |

**Evidence**:
```
Line 536:  \label{sec:ncv_methods}     ← underscore (actual label)
Line 2194: \ref{sec:ncv-methods}        ← hyphen (reference)
```

**Impact**: LaTeX 编译时产生 `undefined reference` 警告，PDF 中该引用位置显示为 `??`。这是 SCI Q2 期刊审稿的 **即时拒稿信号**——审稿人会在第一次翻阅时就注意到 `??` 并质疑全文的严谨性。

**Fix**: 将第 2194 行的 `sec:ncv-methods` 改为 `sec:ncv_methods`。

---

### P1 — 严重（需重大修补）

#### R9-LaTeX-2: 三个图有 label 但从未在正文中被引用

| Field | Value |
|-------|-------|
| **Severity** | P1 — Major |
| **Location** | Lines 832, 1382, 1430 |
| **Attack Type** | 隐含假设不成立 |

**Evidence**:
| Label | Line | Figure Content |
|-------|------|----------------|
| `fig:method_boundary` | 832 | Method-selection boundary 热图 |
| `fig:rel-chapman-ptbxl` | 1382 | Chapman→PTB-XL 可靠性图 |
| `fig:counterexamples` | 1430 | 9 个 counter-example 汇总图 |

**Impact**: 这三个图被创建并放置在正文中，但没有任何 `\ref{fig:...}` 指向它们。读者无法知道正文中何时应查看这些图。SCI Q2 审稿人会质疑："Figure X is never referenced in the text—why is it included?" 这表明作者可能遗漏了交叉引用，削弱了图文对应关系。

**Fix**: 在讨论对应内容时添加 `Figure~\ref{fig:method_boundary}`、`Figure~\ref{fig:rel-chapman-ptbxl}`、`Figure~\ref{fig:counterexamples}`。

---

#### R9-LaTeX-3: 重复句子 — 架构鲁棒性描述

| Field | Value |
|-------|-------|
| **Severity** | P1 — Major |
| **Location** | Lines 872 and 1807 |
| **Attack Type** | 自相矛盾（冗余） |

**Evidence**:
```
Line 872:  Architecture robustness is supported on both InceptionTime (27/30, 90.0\%)
Line 1807: Architecture robustness is supported on both InceptionTime (27/30, 90.0\%)
```

两行内容完全相同，出现在 Results 和 Conclusion 两个不同章节。

**Impact**: SCI Q2 审稿人会标记为 "redundant text across sections"。Conclusion 应总结而非复制 Results 的原文。

---

#### R9-LaTeX-4: 重复句子 — 85% 方向准确率描述

| Field | Value |
|-------|-------|
| **Severity** | P1 — Major |
| **Location** | Lines 1699 and 1858 |
| **Attack Type** | 自相矛盾（冗余） |

**Evidence**:
```
Line 1699: shows 85\% direction accuracy but systematic magnitude overestimation
Line 1858: shows 85\% direction accuracy but systematic magnitude overestimation
```

**Impact**: 同上，Discussion 和 Conclusion 中的重复文本。

---

#### R9-LaTeX-5: `$\Delta$ECE` 表示法不一致

| Field | Value |
|-------|-------|
| **Severity** | P1 — Major |
| **Location** | Lines 847, 1976, 1986 |
| **Attack Type** | 语义偏移 |

**Evidence**:
```
Line 847:  EM OOD $\Delta$ECE mean flips from $-0.0127$ to $+0.0024$
Line 1976: diagram, and $\Delta$ECE bar plot for one of the 60 seed experiments
Line 1986: the visual calibration evidence underlying the $\Delta$ECE values
```

其他 100+ 处使用 `$\Delta\text{ECE}$`（正确写法，ECE 在 `\text{}` 中），这 3 处使用 `$\Delta$ECE`（Δ 在数学模式中，ECE 在文本模式中）。

**Impact**: 排版上 `$\Delta$ECE` 会在 Δ 和 ECE 之间产生不正确的间距（缺少 `\text{}` 包裹导致字体和间距不一致）。审稿人会注意到符号格式不统一。

---

#### R9-LaTeX-6: `PTB-XL` vs `PTBXL` 数据集名称不一致

| Field | Value |
|-------|-------|
| **Severity** | P1 — Major |
| **Location** | 52 lines (99, 336, 353, 1346, 1367–1392, 1900, 2026–2214) |
| **Attack Type** | 语义偏移 |

**Evidence**: 52 处使用 `PTBXL`（无连字符），其余使用 `PTB-XL`（有连字符，标准名称）。

**Impact**: PTB-XL 是公开数据集的标准名称（Wagner et al., 2020）。混用 `PTBXL` 和 `PTB-XL` 会让审稿人质疑作者对数据集的熟悉程度。在 Supplementary Materials 中尤为密集（第 2026–2214 行）。

---

#### R9-LaTeX-7: `Mamba` vs `BiMamba` 术语不一致

| Field | Value |
|-------|-------|
| **Severity** | P1 — Major |
| **Location** | Line 1230 |
| **Attack Type** | 语义偏移 |

**Evidence**:
```
Line 380:  The BiMamba architecture is
Line 383:  BiMamba run exhausted memory on an RTX 5060
Line 985:  the BiMamba architecture is a toy
Line 1691: the BiMamba
Line 1230: including Mamba), 7/14 pass both layers    ← "Mamba" (without "Bi" prefix)
```

**Impact**: 论文统一使用 `BiMamba`（双向 Mamba），但第 1230 行突然使用 `Mamba`。审稿人会困惑这是否指不同的架构。

---

### P2 — 次要（需小修补）

#### R9-LaTeX-8: 3 条参考文献缺少持久标识符（DOI/arXiv）

| Field | Value |
|-------|-------|
| **Severity** | P2 — Minor |
| **Location** | Lines 2249, 2335, 2340 |
| **Attack Type** | 边界失效 |

**Evidence**:
| Cite Key | Line | Issue |
|----------|------|-------|
| `goldberger2000` | 2249 | No DOI |
| `lascal2024` | 2335 | No DOI/arXiv |
| `protocolv21a1` | 2340 | No DOI/URL |

其他 32 条参考文献都有 DOI 或 arXiv 标识符。

**Impact**: Elsevier 期刊要求所有可检索的参考文献提供 DOI。缺少 DOI 会在 production 阶段被编辑退回。

---

#### R9-LaTeX-9: 过长行可能导致 overfull hbox

| Field | Value |
|-------|-------|
| **Severity** | P2 — Minor |
| **Location** | Lines 24, 29, 471, 610, 892, 893, 1439 |
| **Attack Type** | 边界失效 |

**Evidence**:
| Line | Length (chars) | Content Preview |
|------|---------------|-----------------|
| 893 | 155 | `\textbf{Mean OOD ECE} & \multicolumn{2}{c}{$0.217 \rightarrow...` |
| 24 | 121 | Abstract 长行 |
| 29 | 115 | Abstract 长行 |
| 610 | 118 | Table 1 长行 |
| 1439 | 113 | Counter-example 描述 |

**Impact**: LaTeX 可能产生 `Overfull \hbox` 警告，导致文字超出页边距。第 893 行（155 字符）风险最高。

---

#### R9-LaTeX-10: 短语重复

| Field | Value |
|-------|-------|
| **Severity** | P2 — Minor |
| **Location** | Multiple |
| **Attack Type** | 自相矛盾（冗余） |

**Evidence**:
| Phrase | Count | Lines |
|--------|-------|-------|
| `exploratory + robustness validation` | 5 | 75, 500, 1646, 1825, 1847 |
| `All hypotheses are tagged` | 2 | 74, 1824 |

**Impact**: 同一声明在 Introduction、Methods、Discussion、Conclusion 中逐字重复，削弱了写作质量评分。

---

#### R9-LaTeX-11: `seed 42` vs `seed~42` 格式不一致

| Field | Value |
|-------|-------|
| **Severity** | P2 — Minor |
| **Location** | Lines 709, 918, 1426, 1433, 1443, 1451, 1458, 1465, 1471, 1485, 1491, 1498 |
| **Attack Type** | 语义偏移 |

**Evidence**: 12 处使用 `seed 42`（普通空格），其他地方使用 `seed~42`（波浪号，防止换行）。

**Impact**: 普通空格允许 LaTeX 在 `seed` 和数字之间换行，可能在行尾产生孤立的 `seed`。波浪号 `~` 是 LaTeX 标准做法。

---

#### R9-LaTeX-12: `\to` vs `\rightarrow` 箭头表示法不一致

| Field | Value |
|-------|-------|
| **Severity** | P2 — Minor |
| **Location** | 28 figure captions (Lines 1370–2179) |
| **Attack Type** | 语义偏移 |

**Evidence**: 正文使用 `\rightarrow`（103 处），图 caption 使用 `\to`（28 处）表示转移方向。

**Impact**: `\to` 和 `\rightarrow` 在视觉上相似但并非完全相同（`\to` 是关系符号，`\rightarrow` 是箭头符号）。混用影响符号一致性。

---

#### R9-LaTeX-13: `12 strata` vs `14 strata` 未明确区分

| Field | Value |
|-------|-------|
| **Severity** | P2 — Minor |
| **Location** | Lines 73, 159, 197, 755, 1228, 1230, 1898 |
| **Attack Type** | 隐含假设 |

**Evidence**:
```
Line 159:  Across all 12 pair×architecture strata        ← C2 (ID boundary)
Line 755:  (12 pair×architecture strata, 5 seeds each)   ← Table 2
Line 1228: Across 14 pair×architecture strata            ← C5 (deployment)
Line 1230: 7/14 pass both layers                         ← C5
Line 1898: (12 strata) retains 9/12 directions           ← BH correction
```

C2 使用 12 strata（6 pairs × 2 arch），C5 使用 14 strata（12 + 2 extra Mamba）。第 1228 行解释了 14 的来源，但 C2 和 C5 使用不同 strata 数量的逻辑未在首次出现时明确说明。

**Impact**: 审稿人可能困惑为什么同一概念（pair×architecture strata）在不同章节有不同数量。

---

#### R9-LaTeX-14: ECE 值小数位数不一致

| Field | Value |
|-------|-------|
| **Severity** | P2 — Minor |
| **Location** | Lines 201, 893, 1053, 1238, 1298, 1445, 1467, 1852 |
| **Attack Type** | 边界失效 |

**Evidence**:
| Location | Value | Decimals |
|----------|-------|----------|
| Abstract | +0.0159, +0.0083 | 4 |
| Line 201 | +0.029 | 3 |
| Line 893 | 0.217, 0.202 | 3 |
| Line 1053 | 0.127 | 3 |
| Line 1298 | +0.254, +0.260 | 3 |
| Line 1434 | -0.0057 | 4 |

**Impact**: 同一类型量（ECE）在不同位置使用不同精度，影响数据呈现一致性。

---

#### R9-LaTeX-15: 20 个未使用的 label

| Field | Value |
|-------|-------|
| **Severity** | P2 — Minor |
| **Location** | Multiple |
| **Attack Type** | 隐含假设 |

**Evidence**: 45 个 label 中有 20 个从未被 `\ref` 引用（排除 R9-LaTeX-2 中的 3 个图 label 后仍有 17 个 section label）。

**Impact**: 不会导致编译错误，但表明可能有遗漏的交叉引用。Section label 未引用是常见做法（用于后备），但图 label 未引用是问题（已在 R9-LaTeX-2 中报告）。

---

### P3 — 轻微（建议优化）

#### R9-LaTeX-16: `pre-registered` 过度使用

| Field | Value |
|-------|-------|
| **Severity** | P3 — Cosmetic |
| **Count** | 63 occurrences |

**Impact**: `pre-registered` 出现 63 次（平均每 35 行一次），可能让审稿人感到过度强调。建议在部分位置使用同义词（`registered`, `a priori`）。

---

#### R9-LaTeX-17: 双空格

| Field | Value |
|-------|-------|
| **Severity** | P3 — Cosmetic |
| **Count** | 191 lines |

**Impact**: 191 行存在双空格。LaTeX 会自动处理，但不规范。

---

#### R9-LaTeX-18: 注释中存在中文字符

| Field | Value |
|-------|-------|
| **Severity** | P3 — Cosmetic |
| **Location** | Lines 2–14 |

**Impact**: 注释中的 UTF-8 中文字符在某些 LaTeX 引擎（如 pdflatex）下可能产生警告。建议使用 XeLaTeX 或 LuaLaTeX 编译，或删除注释中的中文。

---

#### R9-LaTeX-19: 注释中重复文本

| Field | Value |
|-------|-------|
| **Severity** | P3 — Cosmetic |
| **Location** | Line 12 |

**Evidence**: 第 12 行注释中 "5 个独立贡献（OOD 收益量化 / ID 边界 / Shapley 验证 / 方法选择边界 / 判别感知校准门）" 重复了两次。

---

## Dimensions Where No Attack Found (通过检查)

| Dimension | Result | Evidence |
|-----------|--------|----------|
| **\cite/\bibitem 完整性** | ✅ PASS | 35 个 cite key，全部与 bibitem 匹配，0 个不匹配 |
| **\includegraphics 文件存在性** | ✅ PASS | 72 个引用，72 个文件存在，0 个缺失 |
| **非注释行中文字符** | ✅ PASS | 0 个中文字符在非注释行 |
| **占位符 (TODO/FIXME/XXX/???/TBD)** | ✅ PASS | 0 个占位符 |
| **表格 caption 位置** | ✅ PASS | 7 个表格，全部 caption 在 tabular 之前 |
| **图 caption 位置** | ✅ PASS | 33 个图，全部 caption 在 \includegraphics 之后 |
| **关键数字一致性** | ✅ PASS | 51/60, 85.0%, 38.3%, 48.3%, 7/14, 27/30, 24/30, 90.0%, 80.0% 在 abstract 和正文中完全一致 |
| **booktabs 使用** | ✅ PASS | 7 个表格全部使用 \toprule/\midrule/\bottomrule，无 \hline 混用 |
| **引用命令一致性** | ✅ PASS | 全部使用 \cite（42 处），无 \citep/\citet 混用 |
| **空引用** | ✅ PASS | 无 \cite{} 空引用 |
| **双句号** | ✅ PASS | 无双句号 |
| **pre-registered 拼写** | ✅ PASS | 63 处全部使用 "pre-registered"（有连字符），0 处 "preregistered" |
| **counter-example 拼写** | ✅ PASS | 67 处全部使用 "counter-example"（有连字符），文本中 0 处 "counterexample" |
| **one-sided/two-sided 拼写** | ✅ PASS | 全部使用连字符形式，一致 |

---

## Attack Dimension Coverage

| # | Dimension | Attempted | Attack Found |
|---|-----------|-----------|--------------|
| 1 | 反例构造 | ✅ | ✅ (R9-LaTeX-1: `\ref{sec:ncv-methods}` 是具体反例) |
| 2 | 逻辑断链 | ✅ | ✅ (R9-LaTeX-2: 图存在但引用链断裂) |
| 3 | 隐含假设 | ✅ | ✅ (R9-LaTeX-13: 12 vs 14 strata 假设未声明) |
| 4 | 边界失效 | ✅ | ✅ (R9-LaTeX-8, R9-LaTeX-9, R9-LaTeX-14: 边界值处理失效) |
| 5 | 自相矛盾 | ✅ | ✅ (R9-LaTeX-3, R9-LaTeX-4, R9-LaTeX-10: 重复内容) |
| 6 | 量级错误 | ✅ | ❌ (未发现量级估计错误) |
| 7 | 语义偏移 | ✅ | ✅ (R9-LaTeX-5, R9-LaTeX-6, R9-LaTeX-7, R9-LaTeX-11, R9-LaTeX-12: 术语/符号偏移) |

---

## SCI Q2 Impact Assessment

| Issue | Reviewer Reaction | Publication Risk |
|-------|-------------------|------------------|
| R9-LaTeX-1 (P0) | 即时发现 `??`，质疑全文严谨性 | **High** — 可能直接拒稿 |
| R9-LaTeX-2 (P1) | "Figure never referenced" | **Medium** — major revision |
| R9-LaTeX-3/4 (P1) | "Redundant text" | **Medium** — major revision |
| R9-LaTeX-5 (P1) | "Inconsistent notation" | **Medium** — minor revision |
| R9-LaTeX-6 (P1) | "Dataset name inconsistency" | **Medium** — minor revision |
| R9-LaTeX-7 (P1) | "Architecture name confusion" | **Medium** — minor revision |
| R9-LaTeX-8 (P2) | Production 阶段退回 | **Low** — production delay |
| Others (P2/P3) | 写作质量扣分 | **Low** |

**Overall Risk**: 如果不修复 R9-LaTeX-1，论文无法通过审稿。修复 P0 后，P1 问题合计可能导致 "major revision" 决定。

---

## Recommended Fix Priority

1. **Immediate**: Fix R9-LaTeX-1 (1 line change, P0)
2. **Before Submission**: Fix R9-LaTeX-2 through R9-LaTeX-7 (P1, ~30 min total)
3. **Polish**: Fix R9-LaTeX-8 through R9-LaTeX-15 (P2, ~1 hour total)
4. **Optional**: Address R9-LaTeX-16 through R9-LaTeX-19 (P3, cosmetic)

---

## Conclusion

我尝试了全部 7 个攻击维度，**找到 19 个有效攻击点**（1 P0 + 6 P1 + 7 P2 + 4 P3）。论文在引用完整性、图片文件存在性、表格格式等维度通过检查，但在交叉引用完整性（1 个未定义引用）、图引用遗漏（3 个图未被引用）、术语一致性（PTB-XL/PTBXL、Mamba/BiMamba、ΔECE 表示法）和内容重复（2 处重复句子）方面存在显著缺陷。**最致命的问题是第 2194 行的未定义引用 `\ref{sec:ncv-methods}`，这会导致 PDF 中显示 `??`，是即时拒稿信号。**
