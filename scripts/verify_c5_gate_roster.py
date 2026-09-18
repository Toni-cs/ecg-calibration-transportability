#!/usr/bin/env python
"""Independently recompute the C5 two-layer gate roster and the counter-example
split, from the authoritative per-cell transfer_result.json files.

No file is written. Prints a full audit trail so the manuscript claims can be
checked line by line.

Layer 1 : delta_ECE_OOD > 0
Layer 2 : ood_acc >= target-corpus majority-class accuracy
"""
from __future__ import annotations

import glob
import json
import os
from collections import defaultdict

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRANSFER = os.path.join(ROOT, "checkpoints", "transfer")
CACHE = os.path.join(ROOT, "checkpoints", "e2_probs_cache")

ARCHS = ["inceptiontime", "resnet1d"]
SEEDS = [42, 43, 44, 45, 46]


def load_cells():
    cells = []
    for path in sorted(glob.glob(os.path.join(TRANSFER, "*", "*", "*", "transfer_result.json"))):
        d = json.load(open(path, encoding="utf-8"))
        src, tgt, arch, seed = d["source"], d["target"], d["arch"], d["seed"]
        if arch not in ARCHS:
            continue  # BiMamba orphans are outside the 60-cell grid
        cells.append(
            dict(
                path=path,
                pair=f"{src}->{tgt}",
                src=src,
                tgt=tgt,
                arch=arch,
                seed=seed,
                K=d["num_classes"],
                ood_acc=d["ood_acc"],
                id_acc=d["id_acc"],
                d_ece=d["methods"]["ts"]["ood"]["deltaECE"],
            )
        )
    return cells


def majority_baseline_from_cache():
    """Recompute the target-domain majority-class accuracy from the repaired
    label arrays in the probs cache (independent of the manuscript's table)."""
    acc = defaultdict(list)
    files = sorted(glob.glob(os.path.join(CACHE, "*.npz")))
    for path in files:
        name = os.path.basename(path)[:-4]
        try:
            src, tgt, arch, seed = name.split("_")
        except ValueError:
            continue  # BiMamba orphan / other naming
        try:
            z = np.load(path, allow_pickle=True)
        except Exception:
            continue
        if "test_labels" not in z.files:
            continue
        y = np.asarray(z["test_labels"])
        if y.ndim != 1:
            continue
        # majority-class share = max class frequency
        _, cnt = np.unique(y, return_counts=True)
        acc[(src, tgt, arch)].append(cnt.max() / cnt.sum())
    return {k: float(np.mean(v)) for k, v in acc.items()}


def main():
    cells = load_cells()
    print(f"cells loaded: {len(cells)}")
    pairs = sorted({c["pair"] for c in cells})
    print(f"pairs: {pairs}")

    # ---- baselines ----
    cache_base = majority_baseline_from_cache()
    print("\n=== target majority-class baseline, recomputed from cache labels ===")
    base_by_target_K = defaultdict(list)
    for (src, tgt, arch), v in cache_base.items():
        K = 5 if {src, tgt} == {"chapman", "ptbxl"} else 4
        base_by_target_K[(tgt, K)].append(v)
    for (tgt, K), vs in sorted(base_by_target_K.items()):
        print(f"  target={tgt:8s} K={K}  baseline={np.mean(vs):.4f}  (n={len(vs)})")
    baseline = {k: float(np.mean(v)) for k, v in base_by_target_K.items()}

    def bl(c):
        return baseline[(c["tgt"], c["K"])]

    # ---- per-cell gate ----
    print("\n=== per-cell gate ===")
    n_l1_fail = n_l1_pass_l2_fail = n_both_pass = 0
    for c in cells:
        l1 = c["d_ece"] > 0
        l2 = c["ood_acc"] >= bl(c)
        if not l1:
            n_l1_fail += 1
        elif not l2:
            n_l1_pass_l2_fail += 1
        else:
            n_both_pass += 1
    print(f"  Layer1 fail                 : {n_l1_fail}")
    print(f"  Layer1 pass, Layer2 fail    : {n_l1_pass_l2_fail}")
    print(f"  both pass                   : {n_both_pass}")
    print(f"  sum                         : {n_l1_fail + n_l1_pass_l2_fail + n_both_pass}")

    # ---- stratum level ----
    print("\n=== stratum level (pair x arch, 12 strata) ===")
    strata = defaultdict(list)
    for c in cells:
        strata[(c["pair"], c["arch"])].append(c)
    passed_strata, failed_strata = [], []
    for key in sorted(strata):
        cs = strata[key]
        m_l1 = np.mean([c["d_ece"] > 0 for c in cs])
        m_l2 = np.mean([c["ood_acc"] >= bl(c) for c in cs])
        ok = (m_l1 >= 0.5) and (m_l2 >= 0.5)
        all5 = all((c["d_ece"] > 0) and (c["ood_acc"] >= bl(c)) for c in cs)
        (passed_strata if ok else failed_strata).append(key)
        print(
            f"  {key[0]:22s} {key[1]:14s} "
            f"L1={m_l1:.2f} L2={m_l2:.2f} "
            f"{'PASS' if ok else 'FAIL'}  all5={all5}"
        )
    print(f"\n  passed strata: {len(passed_strata)}/12")
    for k in passed_strata:
        print(f"    + {k[0]} / {k[1]}")
    print(f"  failed strata: {len(failed_strata)}/12")
    for k in failed_strata:
        print(f"    - {k[0]} / {k[1]}")
    n_all5 = sum(
        1
        for key in strata
        if all((c["d_ece"] > 0) and (c["ood_acc"] >= bl(c)) for c in strata[key])
    )
    print(f"  strata passing in all 5 seeds: {n_all5}/12")

    # ---- counter-examples ----
    print("\n=== counter-example set (delta_ECE_OOD <= 0) ===")
    ce = [c for c in cells if c["d_ece"] <= 0]
    print(f"  count: {len(ce)}")
    for c in ce:
        print(
            f"    {c['pair']:22s} {c['arch']:14s} seed{c['seed']} "
            f"dECE={c['d_ece']:+.5f} ood_acc={c['ood_acc']:.4f} "
            f"bl={bl(c):.4f} gap={bl(c) - c['ood_acc']:+.4f}"
        )
    n_acc_le_50 = sum(1 for c in ce if c["ood_acc"] <= 0.50)
    n_below_bl = sum(1 for c in ce if c["ood_acc"] < bl(c))
    n_gap_ge_018 = sum(1 for c in ce if (bl(c) - c["ood_acc"]) >= 0.18)
    print(f"\n  of the {len(ce)} counter-examples:")
    print(f"    ood_acc <= 0.50        : {n_acc_le_50}")
    print(f"    ood_acc < baseline     : {n_below_bl}")
    print(f"    gap >= 0.18            : {n_gap_ge_018}")


if __name__ == "__main__":
    main()
