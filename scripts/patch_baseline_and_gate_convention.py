#!/usr/bin/env python
"""Byte-level patch for paper/main_bspc.tex.

Why not the editor: paper/*.tex has no .gitattributes rule and this machine
runs core.autocrlf=true, so a text-mode edit would rewrite all 2559 lines as
CRLF. Read bytes, replace bytes, write bytes.

Every replacement asserts exactly one occurrence.
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEX = os.path.join(ROOT, "paper", "main_bspc.tex")

REPLACEMENTS = [
    # ---- R1: Layer 2 definition -- pin the evaluation set, fix PTB-XL ----
    (
        """    \\item \\textbf{Layer 2 (Discrimination):} $\\text{acc}_{\\text{OOD}} \\geq
    \\text{acc}_{\\text{majority}}$, the target-corpus majority-class
    accuracy (CPSC $0.528$; PTB-XL $0.411$; Chapman-Shaoxing $0.713$;
    the two $K{=}5$ pairs use $0.399$ and $0.696$ instead, which
    changes no gate verdict).""",
        """    \\item \\textbf{Layer 2 (Discrimination):} $\\text{acc}_{\\text{OOD}} \\geq
    \\text{acc}_{\\text{majority}}$, the target-corpus majority-class
    accuracy measured on the same OOD evaluation set as
    $\\text{acc}_{\\text{OOD}}$ (CPSC $0.528$; PTB-XL $0.409$;
    Chapman-Shaoxing $0.713$; the two $K{=}5$ pairs use $0.399$ and
    $0.696$ instead, which changes no gate verdict).""",
    ),
    # ---- R2: roster paragraph -- spell out the convention, disclose that
    #      Layer 1 is vacuous at the stratum-mean level, fix 0.713 -> 0.696 ----
    (
        """Across 12 pair$\\times$architecture strata (6 pairs $\\times$ 2
architectures), 7/12 pass both layers at the stratum-mean level and are
deployable: CPSC$\\rightarrow$PTB-XL, PTB-XL$\\rightarrow$CPSC, and
Chapman$\\rightarrow$PTB-XL (both architectures each), plus
Chapman$\\rightarrow$CPSC ResNet1D. The other 5/12 fail Layer 2:
Chapman$\\rightarrow$CPSC InceptionTime,
CPSC$\\rightarrow$Chapman (both architectures), and
PTB-XL$\\rightarrow$Chapman (both architectures), where the mean OOD
accuracy falls below the target majority-class baseline despite positive
$\\Delta\\text{ECE}_{\\text{OOD}}$ in some seeds. The strongest rejection
is PTB-XL$\\rightarrow$Chapman ResNet1D ($\\Delta\\text{ECE}=+0.029$ but
$\\text{acc}=0.657 < 0.713$): TS improves calibration but""",
        """Across 12 pair$\\times$architecture strata (6 pairs $\\times$ 2
architectures), 7/12 pass both layers at the stratum-mean level and are
deployable: CPSC$\\rightarrow$PTB-XL, PTB-XL$\\rightarrow$CPSC, and
Chapman$\\rightarrow$PTB-XL (both architectures each), plus
Chapman$\\rightarrow$CPSC ResNet1D. Here ``stratum-mean level'' means
each threshold is applied to the stratum mean of its own metric (mean
$\\Delta\\text{ECE}_{\\text{OOD}} > 0$ and mean
$\\text{acc}_{\\text{OOD}} \\geq \\text{acc}_{\\text{majority}}$); a
per-seed majority reading of the same two thresholds gives 6/12 (each
layer separately) or 5/12 (both jointly) instead of 7/12. At the
stratum-mean level Layer 1 is cleared by all 12 strata, so the stratum
verdicts are driven entirely by Layer 2. The other 5/12 fail Layer 2:
Chapman$\\rightarrow$CPSC InceptionTime,
CPSC$\\rightarrow$Chapman (both architectures), and
PTB-XL$\\rightarrow$Chapman (both architectures), where the mean OOD
accuracy falls below the target majority-class baseline despite positive
$\\Delta\\text{ECE}_{\\text{OOD}}$ in some seeds. The strongest rejection
is PTB-XL$\\rightarrow$Chapman ResNet1D ($\\Delta\\text{ECE}=+0.029$ but
$\\text{acc}=0.657 < 0.696$): TS improves calibration but""",
    ),
    # ---- R3: abstract contribution item C5 -- same K=5 baseline fix ----
    (
        """    $\\text{acc}=0.657 < 0.713$). The gate reframes the 10/60""",
        """    $\\text{acc}=0.657 < 0.696$). The gate reframes the 10/60""",
    ),
    # ---- R4: accuracy statistics paragraph -- post-retrain values + baseline ----
    (
        """experiments, mean OOD accuracy is 0.540 (median 0.546; range
0.388--0.701) and the mean ID--OOD drop is 0.236 (maximum 0.412).
Against each target corpus's majority-class baseline (CPSC 0.528,
PTB-XL 0.411, Chapman-Shaoxing 0.713), mean OOD accuracy is
\\emph{below} baseline in 3 of 6 directions, with a fourth essentially
at baseline: Chapman$\\rightarrow$CPSC
0.510 vs.\\ 0.528; CPSC$\\rightarrow$PTB-XL 0.424 vs.\\ 0.411 (0.013
above baseline); CPSC$\\rightarrow$Chapman 0.619 and
PTB-XL$\\rightarrow$Chapman 0.620 (both well below 0.713). In those""",
        """experiments, mean OOD accuracy is 0.540 (median 0.546; range
0.348--0.701) and the mean ID--OOD drop is 0.234 (maximum 0.412).
Against each target corpus's majority-class baseline (CPSC 0.528,
PTB-XL 0.409, Chapman-Shaoxing 0.713; the two $K{=}5$ pairs use
0.399 and 0.696), mean OOD accuracy is
\\emph{below} baseline in 3 of 6 directions, with a fourth essentially
at baseline: Chapman$\\rightarrow$CPSC
0.510 vs.\\ 0.528; CPSC$\\rightarrow$PTB-XL 0.423 vs.\\ 0.409 (0.014
above baseline); CPSC$\\rightarrow$Chapman 0.619 vs.\\ 0.713 and
PTB-XL$\\rightarrow$Chapman 0.620 vs.\\ 0.696, both well below their
baselines. In those""",
    ),
]


def main() -> int:
    raw = open(TEX, "rb").read()
    if b"\r\n" in raw:
        print("ABORT: file already contains CRLF")
        return 1
    text = raw.decode("utf-8")
    for i, (old, new) in enumerate(REPLACEMENTS, 1):
        n = text.count(old)
        if n != 1:
            print(f"ABORT: replacement {i} matched {n} times (expected 1)")
            print("--- pattern head ---")
            print(old[:200])
            return 1
        text = text.replace(old, new)
        print(f"replacement {i}: ok")
    out = text.encode("utf-8")
    if b"\r\n" in out:
        print("ABORT: result would contain CRLF")
        return 1
    open(TEX, "wb").write(out)
    print(f"written: {TEX}  ({len(raw)} -> {len(out)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
