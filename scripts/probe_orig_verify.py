"""VERIFY the exact definition from scripts/eval_transfer.py L262-265.

    ood_ben = benefit_inference(
        _maxprob(ood_probs),                 # probs_raw  = maxprob of RAW
        _maxprob(ood_cal),                   # probs_cal  = maxprob of CAL
        _bin(ood_cal, ood_labels),           # labels     = correct-mask from CAL
        metric=smooth_ece)
    raw = smooth_ece(maxprob(raw), correct_mask_from_cal)
    cal = smooth_ece(maxprob(cal), correct_mask_from_cal)
    delta = raw - cal

Key quirk: correctness mask is derived from the CALIBRATED argmax and
reused for the RAW metric.
"""
import json
import os
import sys

import numpy as np

ROOT = r"D:/A1/ecg-lab-v2"
sys.path.insert(0, ROOT)
from src.utils.calibration import smooth_ece, benefit_inference  # noqa
from src.utils.calibration_methods import (  # noqa
    fit_temperature_multiclass, apply_temperature_multiclass)

CACHE = os.path.join(ROOT, "checkpoints", "e2_probs_cache")
TR = os.path.join(ROOT, "checkpoints", "transfer")


def _maxprob(p):
    return np.asarray(p).max(axis=1)


def _bin(p, labels):
    return (np.asarray(p).argmax(1) == np.asarray(labels)).astype(float)


def check(cell, exp_raw, exp_cal, exp_delta):
    npz = os.path.join(CACHE, cell + ".npz")
    d = np.load(npz, allow_pickle=True)
    cal_p, cal_y = d["cal_probs"], d["cal_labels"]
    tgt_p, tgt_y = d["test_probs"], d["test_labels"]

    tp = fit_temperature_multiclass(cal_p, cal_y)
    ood_cal = apply_temperature_multiclass(tgt_p, tp)
    # also platt-like? eval_transfer fit_apply_method for 'ts'
    ood_probs = tgt_p

    raw = smooth_ece(_maxprob(ood_probs), _bin(ood_cal, tgt_y))
    cal = smooth_ece(_maxprob(ood_cal), _bin(ood_cal, tgt_y))
    delta = raw - cal
    print("%-42s raw=%.6f(exp %.6f d=%.2e)  cal=%.6f(exp %.6f d=%.2e)  delta=%.6f(exp %.6f d=%.2e)"
          % (cell, raw, exp_raw, abs(raw - exp_raw), cal, exp_cal, abs(cal - exp_cal),
             delta, exp_delta, abs(delta - exp_delta)))
    # cross-check: raw with raw-derived mask (the 'obvious' definition)
    raw_alt = smooth_ece(_maxprob(ood_probs), _bin(ood_probs, tgt_y))
    cal_alt = smooth_ece(_maxprob(ood_cal), _bin(ood_cal, tgt_y))
    print("    [alt raw-mask] raw=%.6f  delta=%.6f" % (raw_alt, raw_alt - cal_alt))
    return raw, cal, delta


def main():
    # ground truth straight from the checkpoints
    cases = []
    for pair, arch, seed in [("chapman_cpsc", "inceptiontime", 42),
                             ("cpsc_chapman", "resnet1d", 44),
                             ("ptbxl_cpsc", "inceptiontime", 45),
                             ("chapman_ptbxl", "resnet1d", 43),
                             ("ptbxl_chapman", "inceptiontime", 42)]:
        p = os.path.join(TR, pair, arch, "seed%d" % seed, "transfer_result.json")
        if not os.path.exists(p):
            print("missing", p)
            continue
        t = json.loads(open(p, encoding="utf-8").read())["methods"]["ts"]["ood"]
        cell = "%s_%s_%s_seed%d" % (pair.split("_")[0], pair.split("_")[1], arch, seed)
        cases.append((cell, t["raw"], t["cal"], t["deltaECE"]))

    print("=" * 118)
    print("HYPOTHESIS: raw = smooth_ece(maxprob(raw_probs), correct_mask_from_CAL)")
    print("=" * 118)
    for cell, r, c, dl in cases:
        check(cell, r, c, dl)


if __name__ == "__main__":
    main()
