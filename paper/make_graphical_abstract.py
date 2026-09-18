# -*- coding: utf-8 -*-
"""Graphical abstract for the CMPB submission.

Elsevier spec: minimum 531 x 1328 px (h x w), readable at 5 x 13 cm.
We render landscape at 2x the minimum: 2656 x 1062 px
(dpi=200, figsize 13.28 x 5.31 in, aspect 2.5:1).

Maintained copy. Supersedes the archived generator at
_paper_cleanup_backup_2026-09-16/D_scripts_logs/_make_graphical_abstract.py,
which carried stale values: 51/60 (now 50/60), 85.0% (now 83.3%),
+0.0159 (now +0.0154), 7/14 strata (now 7/12), and the corpus name
"CPSC2018+2019" (the corpus contains no CPSC2019; amendment A3).

Every text element is auto-shrunk to the width actually available to it,
so no label can overflow its chip or panel.

Run:  C:/python/python.exe paper/make_graphical_abstract.py
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_PNG = os.path.join(HERE, "graphical_abstract.png")
OUT_PDF = os.path.join(HERE, "graphical_abstract.pdf")

INK      = "#1a2733"
SUB      = "#44576a"
BLUE     = "#2b6cb0"
TEAL     = "#0f766e"
AMBER    = "#b45309"
GREEN    = "#15803d"
RED      = "#b91c1c"
BG       = "#ffffff"
PANEL_BG = "#f4f7fa"
PANEL_ED = "#c9d6e2"

plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": INK})

fig, ax = plt.subplots(figsize=(13.28, 5.31), dpi=200)
ax.set_xlim(0, 1328)
ax.set_ylim(0, 531)
ax.invert_yaxis()
ax.axis("off")
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

PY, PH = 95, 390
M = 22
GAP = 40
W1, W2, W3, W4 = 250, 230, 270, 414
X1 = M
X2 = X1 + W1 + GAP
X3 = X2 + W2 + GAP
X4 = X3 + W3 + GAP
assert X4 + W4 + M == 1328

_inv = ax.transData.inverted()


def fit_fs(text, maxw, fs, weight="normal", style="normal"):
    """Shrink fontsize until the rendered text fits inside maxw data units."""
    t = ax.text(0, 0, text, fontsize=fs, fontweight=weight, style=style)
    for _ in range(20):
        fig.canvas.draw()
        bb = t.get_window_extent(renderer=fig.canvas.get_renderer())
        (x0, _), (x1, _) = _inv.transform([(bb.x0, bb.y0), (bb.x1, bb.y1)])
        wd = abs(x1 - x0)
        if wd <= maxw or wd <= 0:
            break
        fs *= maxw / wd
        t.set_fontsize(fs)
    t.remove()
    return fs


def text(x, y, s, color, fs, maxw, ha="center", va="center",
         weight="normal", style="normal"):
    fs = fit_fs(s, maxw, fs, weight, style)
    return ax.text(x, y, s, ha=ha, va=va, fontsize=fs, color=color,
                   fontweight=weight, style=style, zorder=3)


def panel(x, w, title, tcolor):
    ax.add_patch(FancyBboxPatch((x, PY), w, PH,
                                boxstyle="round,pad=0,rounding_size=10",
                                fc=PANEL_BG, ec=PANEL_ED, lw=1.6, zorder=1))
    text(x + w / 2, PY + 24, title, tcolor, 11.5, w - 24, weight="bold")
    return PY + 44


def chip(x, y, w, h, s, color, fs=10, bold=False, fc="white"):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle="round,pad=0,rounding_size=6",
                                fc=fc, ec=color, lw=1.4, zorder=2))
    text(x + w / 2, y + h / 2, s, color, fs, w - 14,
         weight="bold" if bold else "normal")


def arrow(x0, x1):
    mid = PY + PH / 2
    ax.add_patch(FancyArrowPatch((x0, mid), (x1, mid),
                                 arrowstyle="-|>", mutation_scale=20,
                                 lw=2.4, color=SUB, zorder=4))


# ---- title ------------------------------------------------------------------
text(664, 32, "When Does Temperature Scaling Pay Off in Cross-Corpus ECG Transfer?",
     INK, 16, 1328 - 2 * M, weight="bold")
text(664, 60, "A multi-seed calibration boundary study: 6 transfer pairs \u00d7 2 architectures \u00d7 5 seeds",
     SUB, 10.5, 1328 - 2 * M)

# ---- panel 1: experiment grid ------------------------------------------------
top = panel(X1, W1, "1  Experiment grid", BLUE)
cw, ch, step = 206, 36, 46
cx = X1 + (W1 - cw) / 2
for i, name in enumerate(["Chapman\u2013Shaoxing", "CPSC2018", "PTB-XL"]):
    chip(cx, top + 6 + i * step, cw, ch, name, BLUE, fs=10, bold=True)
yy = top + 6 + 3 * step + 12
for j, s in enumerate(["6 directed pairs", "patient-level splits",
                       "InceptionTime | ResNet1D", "seeds 42\u201346"]):
    text(X1 + W1 / 2, yy + j * 18, s, INK, 9, W1 - 24)
chip(X1 + (W1 - 150) / 2, PY + PH - 52, 150, 32, "60 experiments", BLUE, fs=10, bold=True)

# ---- panel 2: deployment shift -----------------------------------------------
top = panel(X2, W2, "2  Deployment shift", TEAL)
text(X2 + W2 / 2, top + 2, "(L2, eval-time, no retraining)", SUB, 8.8, W2 - 24, style="italic")
items = [
    ("Sampling rate", "500 \u2192 250 \u2192 125 Hz"),
    ("Leads", "12 \u2192 6 \u2192 3 \u2192 2 \u2192 1"),
    ("Noise (BWL/MA/EM)", "SNR 24 \u2192 \u22126 dB"),
    ("Gain", "\u00d70.5 / \u00d72"),
]
y0 = top + 26
for i, (k, v) in enumerate(items):
    yk = y0 + i * 72
    text(X2 + 22, yk, k, SUB, 9, W2 - 44, ha="left")
    chip(X2 + 22, yk + 9, W2 - 44, 30, v, TEAL, fs=9.5)

# ---- panel 3: post-hoc recalibration ------------------------------------------
top = panel(X3, W3, "3  Post-hoc recalibration", AMBER)
cwid = W3 - 20
cxx = X3 + 10
chip(cxx, top + 6, cwid, 34, "Raw model (no recalibration)", SUB, fs=9.2, bold=True)
text(X3 + W3 / 2, top + 54, "vs", SUB, 9.5, W3 - 24, style="italic")
chip(cxx, top + 64, cwid, 34, "Temperature Scaling (TS)", AMBER, fs=9.4, bold=True)
text(X3 + W3 / 2, top + 132,
     "+ 7 further methods:\nPlatt \u00b7 Isotonic \u00b7 Vector \u00b7 Matrix\nDirichlet \u00b7 Saerens EM \u00b7 BBSE",
     INK, 8.8, W3 - 20)
text(X3 + W3 / 2, top + 200, "endpoint:  \u0394ECE_OOD = ECE_raw \u2212 ECE_TS", INK, 8.8, W3 - 20)
text(X3 + W3 / 2, top + 234, "patient-level cluster paired bootstrap\n(BCa, B = 10,000)",
     SUB, 8.6, W3 - 20)

# ---- panel 4: findings ---------------------------------------------------------
top = panel(X4, W4, "4  When does TS pay off?", INK)
bx = X4 + 16
tx = bx + 26
avail = X4 + W4 - 14 - tx
rows = [
    (GREEN, "\u2713", "OOD calibration benefit in 50/60 seed experiments (83.3%)", None),
    (GREEN, "\u2713", "OOD benefit \u2248 1.9 \u00d7 ID benefit  (+0.0154 vs +0.0082 ECE)", None),
    (RED,   "\u2717", "Benefit is NOT predictable across architectures",
     "(LOO R\u00b2 CI \u2264 0.104 \u2192 registered failure branch)"),
    (GREEN, "\u2713", "Discrimination-aware gate (C5): 7/12 strata pass both layers",
     "(stratum mean; 24/60 cells, 1/12 strata pass in all 5 seeds)"),
]
yy = top + 16
for color, mark, main, detail in rows:
    ax.text(bx + 8, yy, mark, ha="center", va="center", fontsize=12,
            color=color, fontweight="bold", zorder=3)
    text(tx, yy, main, INK, 9.4, avail, ha="left")
    if detail:
        text(tx, yy + 21, detail, SUB, 8.6, avail, ha="left")
        yy += 60
    else:
        yy += 44

# ---- footer --------------------------------------------------------------------
text(664, 505, "Pre-specified protocol with registered, dated amendments; publicly archived with per-file checksums",
     SUB, 8.6, 1328 - 2 * M, style="italic")
text(664, 522, "OSF project DOI 10.17605/OSF.IO/53H64", SUB, 8.6, 1328 - 2 * M, style="italic")

# ---- arrows --------------------------------------------------------------------
arrow(X1 + W1 + 6, X2 - 8)
arrow(X2 + W2 + 6, X3 - 8)
arrow(X3 + W3 + 6, X4 - 8)

fig.savefig(OUT_PNG, dpi=200, facecolor=BG, bbox_inches=None)
fig.savefig(OUT_PDF, facecolor=BG, bbox_inches=None)
print("saved:", OUT_PNG, os.path.getsize(OUT_PNG), "bytes")
print("saved:", OUT_PDF, os.path.getsize(OUT_PDF), "bytes")
