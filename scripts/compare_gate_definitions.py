#!/usr/bin/env python
"""Compare the three plausible readings of "pass both layers at the
stratum-mean level" for the C5 gate, so the manuscript wording can be pinned
to exactly one of them.

Def A: fraction of seeds passing each layer >= 0.5
Def B: fraction of seeds passing BOTH layers >= 0.5
Def C: stratum MEAN of the metric satisfies the threshold
       (mean delta_ECE > 0  AND  mean ood_acc >= baseline)
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

BASELINE = {
    ("cpsc", 4): 0.5280,
    ("ptbxl", 4): 0.4085,
    ("ptbxl", 5): 0.3987,
    ("chapman", 4): 0.7125,
    ("chapman", 5): 0.6963,
}


def main():
    cells = []
    for path in sorted(glob.glob(os.path.join(TRANSFER, "*", "*", "*", "transfer_result.json"))):
        d = json.load(open(path, encoding="utf-8"))
        if d["arch"] not in ARCHS:
            continue
        cells.append(dict(pair=f"{d['source']}->{d['target']}", tgt=d["target"],
                          arch=d["arch"], seed=d["seed"], K=d["num_classes"],
                          ood_acc=d["ood_acc"], d_ece=d["methods"]["ts"]["ood"]["deltaECE"]))
    strata = defaultdict(list)
    for c in cells:
        strata[(c["pair"], c["arch"])].append(c)

    print(f"{'stratum':42s} {'A(fr>=.5)':>9s} {'B(joint>=.5)':>12s} "
          f"{'C(mean)':>8s} | {'mean_dECE':>10s} {'mean_acc':>9s} {'base':>7s} {'margin':>8s}")
    resA, resB, resC = [], [], []
    for key in sorted(strata):
        cs = sorted(strata[key], key=lambda c: c["seed"])
        base = BASELINE[(cs[0]["tgt"], cs[0]["K"])]
        f1 = np.mean([c["d_ece"] > 0 for c in cs])
        f2 = np.mean([c["ood_acc"] >= base for c in cs])
        joint = np.mean([(c["d_ece"] > 0) and (c["ood_acc"] >= base) for c in cs])
        m_de = np.mean([c["d_ece"] for c in cs])
        m_ac = np.mean([c["ood_acc"] for c in cs])
        A = f1 >= 0.5 and f2 >= 0.5
        B = joint >= 0.5
        C = m_de > 0 and m_ac >= base
        (resA if A else resA), None
        for flag, bucket in ((A, resA), (B, resB), (C, resC)):
            if flag:
                bucket.append(key)
        print(f"{key[0]+' / '+key[1]:42s} {'PASS' if A else 'fail':>9s} "
              f"{'PASS' if B else 'fail':>12s} {'PASS' if C else 'fail':>8s} | "
              f"{m_de:>+10.5f} {m_ac:>9.4f} {base:>7.4f} {m_ac - base:>+8.4f}")

    for name, bucket in (("A  fraction-per-layer >= 0.5", resA),
                         ("B  joint fraction >= 0.5", resB),
                         ("C  stratum MEAN meets threshold", resC)):
        print(f"\n{name}: {len(bucket)}/12 pass")
        for k in bucket:
            print(f"    + {k[0]} / {k[1]}")


if __name__ == "__main__":
    main()
