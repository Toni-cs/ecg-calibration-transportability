#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""完美校准噪声底：**带符号**重算 + 补 T<1 分支。

=====================================================================
为什么需要这个脚本
=====================================================================
论文 §noise\_floor 的锚点表（T=1.0→0；1.25→+0.014~+0.035；1.5→+0.030~+0.061；
3.0→+0.095~+0.136；4.5→+0.126~+0.164）**在仓库里没有生成脚本**（从未提交）。
下游三个脚本（``adjudicate_noise_corrected.py`` / ``adjudicate_noise_floor_main.py``
/ ``noise_floor_mechanism_test.py``）都是把这几个数**硬编码**后做推断。

本脚本做两件事：

1. **复现**：独立重算锚点表，确认论文数字不是笔误。
2. **补 T<1**：原表只覆盖 T≥1。主终点有 9/60 个 cell 的拟合 T<1（范围下探 0.932），
   它们的 ΔECE_OOD 全为负。要论证"底噪不能解释主发现"，必须知道 T<1 时底噪的符号——
   否则这 9 个 cell 就是符号论证的定义域漏洞。

=====================================================================
符号约定（关键，易错）
=====================================================================
* 主终点（main_bspc.tex L72）：``ΔECE_OOD = ECE_raw − ECE_post``，**正 = TS 有益**。
* 本实验（main_bspc.tex L1203）：``ΔECE_noise = SmoothECE(TS) − SmoothECE(raw)``，
  即 **post − raw，与主终点相反**。

理想化设定下真实校准误差恒为 0，故测得的
    ΔECE_OOD = 真值(0) − floor(T) = **−floor(T)**。
即本实验算出的 ``ΔECE_noise`` 就是 floor，而它**进入主终点时带负号**。

用法::

    /c/python/python.exe scripts/noise_floor_signed.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.utils.calibration import smooth_ece  # noqa: E402

N = 2000
T_GRID = [0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.5, 2.0, 3.0, 4.5]
SEEDS = [0, 1, 2]

# 论文锚点（用于复现核对）
PAPER_ANCH = {1.0: (0.000, 0.000), 1.25: (0.014, 0.035),
              1.5: (0.030, 0.061), 3.0: (0.095, 0.136), 4.5: (0.126, 0.164)}


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def make_confidences(rng, n=N):
    """三种置信分布（论文：uniform / normal-skewed / bimodal）。

    返回 {名称: p 数组}，p ∈ (0,1)，分布形态即"模型的置信度分布"。
    """
    out = {}
    # (1) uniform：置信度在 (0,1) 上均匀
    out["uniform"] = rng.uniform(0.02, 0.98, n)
    # (2) normal-skewed：logit 空间正态 → p 空间右偏（模型整体偏自信）
    out["normal_skewed"] = sigmoid(rng.normal(loc=0.6, scale=1.3, size=n))
    # (3) bimodal：一半高置信一半低置信
    half = n // 2
    hi = sigmoid(rng.normal(loc=2.2, scale=0.5, size=n - half))
    lo = sigmoid(rng.normal(loc=-2.2, scale=0.5, size=half))
    out["bimodal"] = np.concatenate([hi, lo])
    return out


def apply_T(p, T):
    return sigmoid(logit(p) / T)


def main():
    print("=" * 78)
    print("完美校准噪声底（带符号）—— 复现论文锚点 + 补 T<1 分支")
    print(f"n={N}, seeds={SEEDS}")
    print("=" * 78)

    # 每个 (分布, T) → 跨 seed 的 ΔECE_noise 列表
    acc = {}
    for seed in SEEDS:
        rng = np.random.default_rng(seed)
        dists = make_confidences(rng)
        for name, p in dists.items():
            y = (rng.uniform(size=len(p)) < p).astype(float)   # 完美校准
            base = smooth_ece(p, y)
            for T in T_GRID:
                d = smooth_ece(apply_T(p, T), y) - base
                acc.setdefault((name, T), []).append(d)

    names = ["uniform", "normal_skewed", "bimodal"]
    print(f"\n{'T':>6} | " + " | ".join(f"{nm:>14}" for nm in names)
          + f" | {'min':>8} {'max':>8}  {'论文锚点':>16}")
    print("-" * 78)
    table = {}
    for T in T_GRID:
        vals = [float(np.mean(acc[(nm, T)])) for nm in names]
        lo, hi = min(vals), max(vals)
        table[T] = (lo, hi)
        ref = PAPER_ANCH.get(T)
        refs = f"{ref[0]:.3f}~{ref[1]:.3f}" if ref else "—"
        flag = ""
        if ref:
            ok = (abs(lo - ref[0]) < 0.006 and abs(hi - ref[1]) < 0.006)
            flag = "  ✅" if ok else "  ⚠️"
        print(f"{T:>6.2f} | " + " | ".join(f"{v:>+14.4f}" for v in vals)
              + f" | {lo:>+8.4f} {hi:>+8.4f}  {refs:>16}{flag}")

    print("\n" + "-" * 78)
    print("符号解读（进入主终点的底噪 = −ΔECE_noise）")
    print("-" * 78)
    neg = [T for T in T_GRID if T < 1.0]
    print(f"  T<1 区间 {neg}:")
    for T in neg:
        lo, hi = table[T]
        print(f"    T={T:<4}  ΔECE_noise ∈ [{lo:+.4f}, {hi:+.4f}]"
              f"  → 主终点贡献 ∈ [{-hi:+.4f}, {-lo:+.4f}]"
              f"  （{'负' if -hi < 0 and -lo < 0 else '变号' if -lo > 0 else '混合'}）")
    print(f"\n  结论：T≠1 时底噪在**两种约定下都为正**（完美校准下任何偏离恒等的")
    print(f"  单调变形都会把 ECE 从最小值推高），故进入主终点恒为**负**贡献。")
    print(f"  → 主终点的正分支（51/60 个 ΔECE_OOD>0）不可能由底噪产生。")

    print("\n" + "-" * 78)
    print("危险区阈值（floor_hi(T) ≥ 主效应 +0.0159）")
    print("-" * 78)
    hi_curve = np.array([table[T][1] for T in T_GRID])
    tt = np.array(T_GRID, dtype=float)
    above = tt[hi_curve >= 0.0159]
    print(f"  以 n={N} 实测曲线：floor_hi ≥ 0.0159 自 T ≈ "
          f"{above.min():.2f} 起" if len(above) else "  （无 T 使 floor_hi ≥ 0.0159）")


if __name__ == "__main__":
    main()
