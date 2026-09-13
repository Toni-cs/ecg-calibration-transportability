"""Statistical analysis module: DeLong test / threshold search / exact McNemar / multi-seed aggregation.

Implemented statistical protocol:
    1. Paired DeLong test + AUROC 95% CI (standard method for comparing models on the same subjects).
    2. Threshold search: performed only on the validation set; the test set only applies the chosen
       thresholds (prevents leakage). Operating points: Youden J optimum + sens>=95% (screening
       constraint) + spec>=95% (confirmation constraint).
    3. Exact McNemar: compares positive-detection differences between two configurations
       (binomial exact version when b+c < 25).
    4. Multi-seed aggregation: mean +/- std (ddof=1) + raw value per seed (never report only the
       mean when n is small).
"""

import sys
from pathlib import Path

import numpy as np
from scipy import stats as sps

ROOT = Path(__file__).resolve().parents[1]


# ---------------- DeLong: CI and paired comparison for AUROC ----------------

def _delong_components(y: np.ndarray, p: np.ndarray):
    """DeLong V10/V01 structural components (location components for cases and controls)."""
    pos = p[y == 1]
    neg = p[y == 0]
    m, n = len(pos), len(neg)
    # V10[i]: how much the i-th case exceeds controls (with 0.5 for ties)
    higher = (pos[:, None] > neg[None, :]).astype(float)
    ties = (pos[:, None] == neg[None, :]).astype(float)
    v10 = (higher + 0.5 * ties).mean(axis=1)
    v01 = (higher + 0.5 * ties).mean(axis=0)
    return v10, v01, m, n


def delong_paired(y, p1, p2) -> dict:
    """Paired DeLong test for two models' AUROC on the same samples.

    Returns: each model's AUROC + SE + 95% CI, the difference + 95% CI, and the z-test p-value.
    """
    v10_1, v01_1, m, n = _delong_components(y, p1)
    v10_2, v01_2, _, _ = _delong_components(y, p2)
    a1, a2 = v10_1.mean(), v10_2.mean()

    # DeLong 1988 standard formula: Cov(AUC) = S10/m + S01/n
    # (S10 = case-component covariance, S01 = control-component covariance).
    def _var(x: np.ndarray) -> float:
        return float(np.var(x, ddof=1)) if len(x) > 1 else 0.0

    s11 = _var(v10_1) / m + _var(v01_1) / n
    s22 = _var(v10_2) / m + _var(v01_2) / n
    # paired covariance: cross-component correlation
    c10 = (float(np.cov(np.stack([v10_1, v10_2]), ddof=1)[0, 1])
           if m > 1 else 0.0)
    c01 = (float(np.cov(np.stack([v01_1, v01_2]), ddof=1)[0, 1])
           if n > 1 else 0.0)
    s12 = c10 / m + c01 / n

    se1, se2 = np.sqrt(s11), np.sqrt(s22)
    diff = a1 - a2
    se_diff = np.sqrt(max(s11 + s22 - 2 * s12, 1e-15))
    z = diff / se_diff
    pval = 2 * sps.norm.sf(abs(z))

    return {
        "auroc1": round(float(a1), 4), "auroc1_ci95": [
            round(float(a1 - 1.96 * se1), 4), round(float(a1 + 1.96 * se1), 4)],
        "auroc2": round(float(a2), 4), "auroc2_ci95": [
            round(float(a2 - 1.96 * se2), 4), round(float(a2 + 1.96 * se2), 4)],
        "delta": round(float(diff), 4),
        "delta_ci95": [round(float(diff - 1.96 * se_diff), 4),
                       round(float(diff + 1.96 * se_diff), 4)],
        "z": round(float(z), 3), "p_value": float(f"{pval:.2e}"),
    }


# ---------------- Threshold search (validation set only) ----------------

def search_thresholds(y_val, p_val) -> dict:
    """Search multiple clinical operating points on the validation set (test set only applies them)."""
    grids = np.unique(np.concatenate([p_val, [0.5]]))

    best_j, th_j = -1, 0.5
    best_s95, th_s95 = -1, None     # maximize spec under sens>=95% constraint
    best_p95, th_p95 = -1, None     # maximize sens under spec>=95% constraint
    for th in grids:
        pred = (p_val >= th).astype(int)
        tp = int(((pred == 1) & (y_val == 1)).sum())
        fn = int(((pred == 0) & (y_val == 1)).sum())
        tn = int(((pred == 0) & (y_val == 0)).sum())
        fp = int(((pred == 1) & (y_val == 0)).sum())
        sens = tp / (tp + fn) if (tp + fn) else 0.0
        spec = tn / (tn + fp) if (tn + fp) else 0.0
        j = sens + spec - 1
        if j > best_j:
            best_j, th_j = j, float(th)
        if sens >= 0.95 and spec > best_s95:
            best_s95, th_s95 = spec, float(th)
        if spec >= 0.95 and sens > best_p95:
            best_p95, th_p95 = sens, float(th)
    return {
        "youden_j": {"threshold": round(th_j, 4), "val_j": round(best_j, 4)},
        "sens95": ({"threshold": round(th_s95, 4), "val_spec": round(best_s95, 4)}
                   if th_s95 is not None else None),
        "spec95": ({"threshold": round(th_p95, 4), "val_sens": round(best_p95, 4)}
                   if th_p95 is not None else None),
    }


# ---------------- Exact McNemar ----------------

def mcnemar_exact(y, pred1, pred2) -> dict:
    """Exact McNemar (binomial): difference in positive calls between two models on the same subjects.

    Note: this implementation counts b/c only over positive cases (y==1), measuring
    "case-detection disagreement", which is not the textbook full-sample McNemar. The
    paper reports both side by side (see mcnemar_standard for the full-sample version)
    and explicitly states the scope difference.
    """
    b = int(((pred1 == 1) & (pred2 == 0) & (y == 1)).sum())
    c = int(((pred1 == 0) & (pred2 == 1) & (y == 1)).sum())
    n = b + c
    if n == 0:
        return {"b": 0, "c": 0, "p_value": 1.0}
    pval = min(1.0, 2 * sps.binom.cdf(min(b, c), n, 0.5))
    # keep scientific notation: round(...,4) would truncate 5e-13 to 0.0, misread as p=0 in the paper
    return {"b": b, "c": c, "p_value": float(f"{pval:.2e}")}


def mcnemar_standard(y, pred1, pred2) -> dict:
    """Standard McNemar (full sample, textbook definition): test of directional disagreement
    between two classifiers' predictions.

    b = all samples the first model calls positive and the second negative, c = the reverse
    (regardless of true label y). A significant p-value means the two classifiers' decision
    boundaries differ systematically. The y argument is kept only for interface consistency
    and does not enter the statistic.
    """
    b = int(((pred1 == 1) & (pred2 == 0)).sum())
    c = int(((pred1 == 0) & (pred2 == 1)).sum())
    n = b + c
    if n == 0:
        return {"b": 0, "c": 0, "p_value": 1.0}
    pval = min(1.0, 2 * sps.binom.cdf(min(b, c), n, 0.5))
    return {"b": b, "c": c, "p_value": float(f"{pval:.2e}")}


# ---------------- Multi-seed aggregation ----------------

def aggregate_seeds(values: list[float]) -> dict:
    """mean +/- std (ddof=1) + median/IQR + all raw values (bimodal alert relies on raw values)."""
    v = np.asarray(values, dtype=float)
    out = {
        "n": len(v), "mean": round(float(v.mean()), 4),
        "std": round(float(v.std(ddof=1)), 4) if len(v) > 1 else None,
        "median": round(float(np.median(v)), 4),
        "iqr": [round(float(np.percentile(v, 25)), 4),
                round(float(np.percentile(v, 75)), 4)] if len(v) > 1 else None,
        "min": round(float(v.min()), 4), "max": round(float(v.max()), 4),
        "raw": [round(float(x), 4) for x in v],
    }
    # bimodal heuristic: flag when range > 3*std, since mean would mislead
    if len(v) > 2 and out["std"] and (out["max"] - out["min"]) > 3 * out["std"]:
        out["bimodal_warning"] = True
    return out


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    # self-test: synthetic data with known AUROC
    rng = np.random.default_rng(0)
    y = np.concatenate([np.ones(400), np.zeros(600)])
    p_good = np.concatenate([rng.beta(5, 2, 400), rng.beta(2, 5, 600)])
    p_weak = np.concatenate([rng.beta(3, 2, 400), rng.beta(2, 3, 600)])
    r = delong_paired(y, p_good, p_weak)
    assert r["auroc1"] > r["auroc2"], "DeLong direction incorrect"
    print("[self-test] DeLong paired test:", {k: r[k] for k in ("auroc1", "auroc2", "p_value")})

    # self-test: DeLong single-model SE vs Bootstrap SE (the old formula's ~2x underestimate would surface here)
    from sklearn.metrics import roc_auc_score
    v10, v01, m_, n_ = _delong_components(y, p_good)
    se_delong = float(np.sqrt(
        np.var(v10, ddof=1) / m_ + np.var(v01, ddof=1) / n_))
    rng_b = np.random.default_rng(1)
    aucs = []
    for _ in range(500):
        idx = rng_b.integers(0, len(y), len(y))
        yb = y[idx]
        if yb.sum() in (0, len(yb)):
            continue
        aucs.append(roc_auc_score(yb, p_good[idx]))
    se_boot = float(np.std(aucs, ddof=1))
    print(f"[self-test] DeLong SE={se_delong:.4f} vs Bootstrap SE={se_boot:.4f}")
    assert abs(se_delong - se_boot) / se_boot < 0.25, \
        f"DeLong SE({se_delong:.4f}) and Bootstrap SE({se_boot:.4f}) diverge too much"

    th = search_thresholds(y, p_good)
    print("[self-test] threshold search:", th)
    m = mcnemar_exact(y, (p_good > 0.5).astype(int), (p_weak > 0.5).astype(int))
    print("[self-test] exact McNemar:", m)
    print("[self-test] all passed")
