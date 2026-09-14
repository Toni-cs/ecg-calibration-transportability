# -*- coding: utf-8 -*-
"""Graphical abstract for BSPC submission.

Elsevier graphical abstract spec: minimum 531 x 1328 px (h x w),
readable at 5 x 13 cm. We render at 2x: 2656 x 1062 px (dpi=200,
figsize 13.28 x 5.31 in, aspect 2.5:1).
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "graphical_abstract.png")

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

# geometry
PY, PH = 95, 390          # panel top / height
M = 22                    # side margin
GAP = 40                  # gap between panels
W1, W2, W3, W4 = 250, 230, 270, 414
X1 = M
X2 = X1 + W1 + GAP
X3 = X2 + W2 + GAP
X4 = X3 + W3 + GAP
assert X4 + W4 + M == 1328


def panel(x, w, title, tcolor):
    ax.add_patch(FancyBboxPatch((x, PY), w, PH,
                                boxstyle="round,pad=0,rounding_size=10",
                                fc=PANEL_BG, ec=PANEL_ED, lw=1.6, zorder=1))
    ax.text(x + w / 2, PY + 24, title, ha="center", va="center",
            fontsize=11.5, fontweight="bold", color=tcolor, zorder=3)
    return PY + 44


def chip(x, y, w, h, text, color, fs=10, bold=False, fc="white"):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                                boxstyle="round,pad=0,rounding_size=6",
                                fc=fc, ec=color, lw=1.4, zorder=2))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, color=color, zorder=3,
            fontweight="bold" if bold else "normal")


def arrow(x0, x1):
    mid = PY + PH / 2
    ax.add_patch(FancyArrowPatch((x0, mid), (x1, mid),
                                 arrowstyle="-|>", mutation_scale=20,
                                 lw=2.4, color=SUB, zorder=4))


# ---- title ------------------------------------------------------------------
ax.text(664, 32, "When Does Temperature Scaling Pay Off in Cross-Corpus ECG Transfer?",
        ha="center", va="center", fontsize=16, fontweight="bold", color=INK)
ax.text(664, 60, "A multi-seed calibration boundary study: 6 transfer pairs × 2 architectures × 5 seeds",
        ha="center", va="center", fontsize=10.5, color=SUB)

# ---- panel 1: experiment grid ------------------------------------------------
top = panel(X1, W1, "1  Experiment grid", BLUE)
cw, ch, step = 206, 36, 46
cx = X1 + (W1 - cw) / 2
for i, name in enumerate(["Chapman–Shaoxing", "CPSC2018+2019", "PTB-XL"]):
    chip(cx, top + 6 + i * step, cw, ch, name, BLUE, fs=10, bold=True)
yy = top + 6 + 3 * step + 12
ax.text(X1 + W1 / 2, yy, "6 directed pairs",
        ha="center", fontsize=9, color=INK)
ax.text(X1 + W1 / 2, yy + 18, "patient-level splits",
        ha="center", fontsize=9, color=INK)
ax.text(X1 + W1 / 2, yy + 36, "InceptionTime | ResNet1D",
        ha="center", fontsize=9, color=INK)
ax.text(X1 + W1 / 2, yy + 54, "seeds 42–46",
        ha="center", fontsize=9, color=INK)
chip(X1 + (W1 - 150) / 2, PY + PH - 52, 150, 32, "60 experiments", BLUE, fs=10, bold=True)

# ---- panel 2: deployment shift -----------------------------------------------
top = panel(X2, W2, "2  Deployment shift", TEAL)
ax.text(X2 + W2 / 2, top + 2, "(L2, eval-time, no retraining)",
        ha="center", fontsize=8.8, color=SUB, style="italic")
items = [
    ("Sampling rate", "500 → 250 → 125 Hz"),
    ("Leads", "12 → 6 → 3 → 2 → 1"),
    ("Noise (BWL/MA/EM)", "SNR 24 → −6 dB"),
    ("Gain", "×0.5 / ×2"),
]
y0 = top + 26
for i, (k, v) in enumerate(items):
    yy = y0 + i * 72
    ax.text(X2 + 22, yy, k, ha="left", fontsize=9, color=SUB)
    chip(X2 + 22, yy + 9, W2 - 44, 30, v, TEAL, fs=9.5)

# ---- panel 3: post-hoc recalibration ------------------------------------------
top = panel(X3, W3, "3  Post-hoc recalibration", AMBER)
cwid = W3 - 20
cxx = X3 + 10
chip(cxx, top + 6, cwid, 34, "Raw model (no recalibration)", SUB, fs=9.2, bold=True)
ax.text(X3 + W3 / 2, top + 54, "vs", ha="center", va="center",
        fontsize=9.5, color=SUB, style="italic")
chip(cxx, top + 64, cwid, 34, "Temperature Scaling (TS)", AMBER, fs=9.4, bold=True)
ax.text(X3 + W3 / 2, top + 132, "+ 7 further methods:\nPlatt · Isotonic · Vector · Matrix\nDirichlet · Saerens EM · BBSE",
        ha="center", va="center", fontsize=8.8, color=INK)
ax.text(X3 + W3 / 2, top + 200, "endpoint:  ΔECE_OOD = ECE_raw − ECE_TS",
        ha="center", fontsize=8.8, color=INK)
ax.text(X3 + W3 / 2, top + 234, "patient-level cluster paired bootstrap\n(BCa, B = 10,000)",
        ha="center", va="center", fontsize=8.6, color=SUB)

# ---- panel 4: findings ---------------------------------------------------------
top = panel(X4, W4, "4  When does TS pay off?", INK)
bx = X4 + 16
tx = bx + 26
rows = [
    (GREEN, "✓", "OOD calibration benefit in 51/60 seed experiments (85.0%)", None),
    (GREEN, "✓", "OOD benefit ≈ 1.9 × ID benefit  (+0.0159 vs +0.0083 ECE)", None),
    (RED,   "✗", "Benefit is NOT predictable across architectures",
     "(LOO R² CI ≤ 0.104 → registered failure branch)"),
    (GREEN, "✓", "Discrimination-aware gate (C5): 7/14 strata pass",
     "both the calibration and the discrimination layer"),
]
yy = top + 16
for color, mark, main, detail in rows:
    ax.text(bx + 8, yy, mark, ha="center", va="center", fontsize=12,
            color=color, fontweight="bold")
    ax.text(tx, yy, main, ha="left", va="center", fontsize=9.4, color=INK)
    if detail:
        ax.text(tx, yy + 21, detail, ha="left", va="center", fontsize=8.6, color=SUB)
        yy += 60
    else:
        yy += 44

# ---- footer --------------------------------------------------------------------
ax.text(664, 513, "Pre-specified protocol with registered, dated amendments; publicly archived with per-file checksums (OSF)",
        ha="center", va="center", fontsize=8.6, color=SUB, style="italic")

# ---- arrows --------------------------------------------------------------------
arrow(X1 + W1 + 6, X2 - 8)
arrow(X2 + W2 + 6, X3 - 8)
arrow(X3 + W3 + 6, X4 - 8)

fig.savefig(OUT, dpi=200, facecolor=BG, bbox_inches=None)
print("saved:", OUT, os.path.getsize(OUT), "bytes")
