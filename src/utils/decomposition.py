"""Three-component decomposition estimator.

Mathematical definition (binary classification, probability p, binary label y):
- injection: p' = sigmoid(s * logit(p) + b); prevalence injection = resample to target prior
- recovery: on the resampled data, with King-Zeng case-control correction:
      fit logit(y) = a * x' + c  (x' = logit(p')),
      case-control offset: resampling makes b_hat_raw carry
          -(logit(pi_resampled) - logit(pi_injected)) / a,
      correction: b_hat = b_hat_raw + (logit(pi_resampled) - logit(pi_injected)) / a  [as implemented]
  where pi_injected = positive-class frequency of the injected (pre-resampling) data,
  pi_resampled = positive-class frequency after resampling.
  Note: prev_hat = post-resampling label frequency is a design-constant readback
  (resampling exactly controls the positive count), so MAPE_pi is a design check,
  not an estimator-capability test. Independent recovery of pi requires a BBSE/EM-style
  unlabeled estimator, which is not implemented here (preregistered protocol §8 leftover
  item; see EXPERIMENT_PROTOCOL).

Entry validation (preserved): labels must be in {0,1}, probs must be 1-D. Multiclass
top-label scenarios require the caller to binarize first and annotate the semantics
(confidence-correctness mapping, including baseline miscalibration contamination).
"""

import warnings
import math
import itertools
from typing import Dict, Optional

import numpy as np
from scipy.special import expit
from sklearn.linear_model import LogisticRegression

IDENTIFIABILITY_TAU = 1e-6  # preregistered identifiability threshold (protocol §8)
N_REF = 20000               # reference sample size (gate calibration)
MAPE_REF = 0.0123           # single-seed measured MAPE_s reference at n=N_REF (1.23%)
GATE_BASE = 0.10            # original protocol gate
GATE_FLOOR = 0.10           # gate floor (not below preregistered value)


def _validate_binary(probs: np.ndarray, labels: np.ndarray):
    """Entry validation: labels in {0,1}, probs 1-D."""
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels)
    if probs.ndim != 1:
        raise ValueError(f"probs must be 1-D (binary classification), got shape={probs.shape}."
                         f" Multiclass top-label scenarios must be binarized first"
                         f" (max_prob + correct_mask) and annotated.")
    if labels.size and not np.isin(labels, [0, 1]).all():
        raise ValueError(f"labels must be in {{0,1}}, got range "
                         f"[{labels.min()},{labels.max()}] -- multiclass indices would "
                         f"silently produce garbage.")
    return probs, labels.astype(float)


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return np.log(p / (1 - p))


def inject_transform(probs: np.ndarray, slope: float = 1.0,
                     intercept: float = 0.0) -> np.ndarray:
    """logit-space injection transform: p' = sigmoid(s * logit(p) + b)"""
    probs, _ = _validate_binary(probs, np.zeros(0, dtype=int))
    return expit(slope * _logit(probs) + intercept)


def resample_prevalence(probs: np.ndarray, labels: np.ndarray,
                        target_prev: float, rng: np.random.Generator) -> np.ndarray:
    """Resample indices by target_prev (with replacement, preserving (p,y) pairing).

    Boundary: target_prev is clipped to [0.01,0.99] with a warning; when positives are
    insufficient they are copied with a warning.
    """
    probs, labels = _validate_binary(probs, labels)
    if not (0 < target_prev < 1):
        warnings.warn(f"target_prev={target_prev} out of range, clipped to [0.01,0.99]")
        target_prev = float(np.clip(target_prev, 0.01, 0.99))
    n = len(labels)
    pos_idx = np.where(labels == 1)[0]
    neg_idx = np.where(labels == 0)[0]
    if len(pos_idx) == 0:
        raise ValueError("No positive samples; cannot resample")
    n_pos = max(int(round(target_prev * n)), 1)
    if n_pos > 5 * len(pos_idx):
        warnings.warn(f"Positive samples ({len(pos_idx)}) will be copied "
                      f"{n_pos/len(pos_idx):.0f}x; the resampled set is not independent "
                      f"and ECE uncertainty is underestimated")
    pos_sampled = rng.choice(pos_idx, size=n_pos, replace=True)
    n_neg = n - n_pos
    neg_sampled = rng.choice(neg_idx, size=n_neg, replace=True)
    idx = np.concatenate([pos_sampled, neg_sampled])
    rng.shuffle(idx)
    return idx


def recover_slope_intercept(probs_injected: np.ndarray, labels: np.ndarray,
                            pi_reference: Optional[float] = None,
                            pi_resampled: Optional[float] = None,
                            slope_hint: Optional[float] = None) -> Dict[str, float]:
    """Recover (s,b) on the (resampled) data with King-Zeng case-control correction.

    Math: inject p' = sigma(s*x + b), y ~ Bern(sigma(x)) (baseline calibration).
    Recover regression logit(y) = a*x' + c. Inversion: s_hat = 1/a, b_hat_raw = -c/a.
    case-control offset (empirically verified): resampling makes b_hat_raw carry
        -(logit(pi_resampled) - logit(pi_injected)) / a,
    correction: b_hat = b_hat_raw + (logit(pi_resampled) - logit(pi_injected)) / a  [as implemented].
    When recovery degenerates (slope ~= 0, data uninformative) raise ValueError; the
    caller decides how to handle it (decompose_benefit catches it and flags recovery_failed).
    """
    probs_injected, labels = _validate_binary(probs_injected, labels)
    x_prime = _logit(probs_injected).reshape(-1, 1)
    if float(np.var(x_prime)) < 1e-12:
        # x' constant design (injected probs clipped / no variance): logistic degenerates
        # along the parameter manifold; |a| criterion is insufficient, variance is essential
        raise ValueError("x' = logit(p') variance ~= 0 (injected probs clipped / constant), "
                         "recovery degenerates (data uninformative)")
    lr = LogisticRegression(C=1e4, solver='lbfgs', max_iter=5000)
    lr.fit(x_prime, labels.astype(int))
    a, c = float(lr.coef_[0, 0]), float(lr.intercept_[0])
    if abs(a) < 1e-12:
        raise ValueError("logistic regression slope ~= 0, recovery degenerates (data uninformative)")
    s_hat = 1.0 / a
    b_hat_raw = -c / a

    b_hat = b_hat_raw
    if pi_reference is not None and pi_resampled is not None:
        # King-Zeng case-control correction (empirically verified: b_hat = b_hat_raw + L/a,
        # true value 0.5 recovers to 0.494)
        L = (np.log(pi_resampled / (1 - pi_resampled))
             - np.log(pi_reference / (1 - pi_reference)))
        b_hat = b_hat_raw + L / a

    return {'s_hat': s_hat, 'b_hat': b_hat, 'b_hat_raw': b_hat_raw}


def fisher_information_det(probs_injected: np.ndarray,
                           probs_baseline: np.ndarray) -> float:
    """Fisher information determinant of the recovery likelihood.

    Recovery problem: y|x' ~ Bern(sigma((x'-b)/s)), x'=logit(p_injected),
    x_base=logit(p_baseline). Design matrix [1, x'], weights
    w_i = sigma(x_base_i)(1-sigma(x_base_i)) (baseline Bernoulli variance; injection is a
    deterministic reparameterization of covariates, the conditional y distribution is unchanged,
    so this weight is exactly the true Fisher weight). det is independent of b and scales with
    the x' design as ~ s^2 (single-dimension scaling of a 2x2 information matrix, verified).
    """
    probs_injected, _ = _validate_binary(probs_injected, np.zeros(0, dtype=int))
    probs_baseline, _ = _validate_binary(probs_baseline, np.zeros(0, dtype=int))
    x_prime = _logit(probs_injected)
    x_base = _logit(probs_baseline)
    w = expit(x_base) * (1 - expit(x_base))
    n = len(x_prime)
    sw = w.sum()
    swx = (w * x_prime).sum()
    swxx = (w * x_prime ** 2).sum()
    det = (sw * swxx - swx ** 2) / (n ** 2)
    return float(max(det, 0.0))


def identifiability_gate(n: int) -> float:
    """MAPE gate scales with sample size.

    gate(n) = max(GATE_FLOOR, 3 * MAPE_REF * sqrt(N_REF / n))

    Honest semantics: MAPE_REF is a single-seed single-run point observation (not a standard
    deviation); the "3x" factor is a heuristic amplification, not a 3-sigma tolerance.
    Calibration (archived results/decomposition_validation_n500_*.csv): at n=500, mape_s
    p50=13.2%, p95=33.2%, max=42.1%, violation rate 6/27 ~ 22%; gate(500)=23.3% sits around
    mape_s p74, not p99.87. The gate should be used as a hard decision only at the preregistered
    n=20000; at small sample sizes it is reported as information only.
    """
    gate = 3 * MAPE_REF * np.sqrt(N_REF / max(n, 1))
    return float(max(GATE_FLOOR, gate))


def ece_metric_safe(probs: np.ndarray, labels: np.ndarray) -> float:
    """Binary ECE (10 equal-width bins), default metric for decompose_benefit.

    Note: this is a different estimator from the protocol's primary SmoothECE
    (calibration.smooth_ece). Internal synthetic validation is self-consistent, but the
    27-cell conclusions do not extrapolate to the primary endpoint's metric (protocol §11 noted).
    """
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels, dtype=float)
    ece_val = 0.0
    n = len(probs)
    for i in range(10):
        lo, hi = i / 10, (i + 1) / 10
        mask = (probs >= lo) & (probs < hi) if i < 9 else (probs >= lo) & (probs <= hi)
        if mask.sum() == 0:
            continue
        ece_val += mask.sum() / n * abs(probs[mask].mean() - labels[mask].mean())
    return float(ece_val)


def _ece_subsets(probs_base, labels_base, slope, intercept, prev_idx, metric):
    """Full enumeration of 8-subset ECE (shared by Shapley / factorial / permutation)."""
    def ece_subset(s, b, use_prev):
        p = inject_transform(probs_base, s, b)
        if use_prev and prev_idx is not None:
            return float(metric(p[prev_idx], labels_base[prev_idx]))
        return float(metric(p, labels_base))

    return {
        '': ece_subset(1.0, 0.0, False),
        's': ece_subset(slope, 0.0, False),
        'b': ece_subset(1.0, intercept, False),
        'pi': ece_subset(1.0, 0.0, prev_idx is not None),
        'sb': ece_subset(slope, intercept, False),
        'spi': ece_subset(slope, 0.0, prev_idx is not None),
        'bpi': ece_subset(1.0, intercept, prev_idx is not None),
        'sbpi': ece_subset(slope, intercept, prev_idx is not None),
    }


_CANON = {'s': 0, 'b': 1, 'pi': 2}


def _attribution_from_subsets(vals: Dict[str, float]) -> Dict:
    """Compute chain / permutation / factorial-interaction / Shapley from the 8-subset ECE
    (pure combinatorics, no resampling)."""
    e0, e_s, e_b, e_pi = vals[''], vals['s'], vals['b'], vals['pi']
    e_sb, e_spi, e_bpi, e_sbpi = vals['sb'], vals['spi'], vals['bpi'], vals['sbpi']

    delta_total = e_sbpi - e0
    delta_s = e_s - e0
    delta_b = e_sb - e_s
    delta_pi = e_sbpi - e_sb
    # Chain residual is identically 0 by definition (nested identity);
    # true interactions use the factorial terms:
    chain_residual = delta_total - (delta_s + delta_b + delta_pi)

    interactions = {
        'I_sb': e_sb - e_s - e_b + e0,
        'I_s_pi': e_spi - e_s - e_pi + e0,
        'I_b_pi': e_bpi - e_b - e_pi + e0,
        'I_3way': e_sbpi - e_sb - e_spi - e_bpi + e_s + e_b + e_pi - e0,
    }

    def chain_decomp(order):
        current = e0
        comps = {}
        steps = {'s': e_s, 'b': e_b, 'pi': e_pi,
                 'sb': e_sb, 'spi': e_spi, 'bpi': e_bpi, 'sbpi': e_sbpi}
        done = set()
        for comp in order:
            target_key = ''.join(sorted(done | {comp}, key=lambda c: _CANON[c]))
            e_next = steps[target_key]
            comps[comp] = e_next - current
            current = e_next
            done.add(comp)
        return comps

    permutations = {}
    for order in itertools.permutations(['s', 'b', 'pi']):
        permutations[''.join(order)] = chain_decomp(order)

    def shapley(comp):
        total = 0.0
        others = [c for c in ['s', 'b', 'pi'] if c != comp]
        for r in range(len(others) + 1):
            for subset in itertools.combinations(others, r):
                key_with = ''.join(sorted(subset + (comp,), key=lambda c: _CANON[c]))
                key_without = ''.join(sorted(subset, key=lambda c: _CANON[c]))
                weight = (math.factorial(len(subset))
                          * math.factorial(3 - len(subset) - 1) / 6)
                total += weight * (vals[key_with] - vals[key_without])
        return total

    shap_s = shapley('s')
    shap_b = shapley('b')
    shap_pi = shapley('pi')
    shap_sum = shap_s + shap_b + shap_pi
    shares = {
        's': shap_s / shap_sum if shap_sum != 0 else 0.0,
        'b': shap_b / shap_sum if shap_sum != 0 else 0.0,
        'pi': shap_pi / shap_sum if shap_sum != 0 else 0.0,
    }

    return {
        'delta_total': delta_total,
        'chain': {'delta_s': delta_s, 'delta_b': delta_b, 'delta_pi': delta_pi,
                  'residual': chain_residual},
        'interactions': interactions,
        'permutations': permutations,
        'shapley': {'values': {'s': shap_s, 'b': shap_b, 'pi': shap_pi},
                    'shares': shares},
    }


def decompose_benefit(probs_base: np.ndarray, labels_base: np.ndarray,
                      slope: float, intercept: float,
                      target_prev: Optional[float], rng: np.random.Generator,
                      metric=ece_metric_safe) -> Dict:
    """Full three-component decomposition.

    Performs injection, 8-subset ECE attribution, recovery (resampled + King-Zeng correction),
    Fisher information, and Shapley reliability gating.
    """
    probs_base, labels_base = _validate_binary(probs_base, labels_base)

    # injection
    p_inj = inject_transform(probs_base, slope, intercept)
    prev_idx = None
    if target_prev is not None and abs(target_prev - labels_base.mean()) > 1e-9:
        prev_idx = resample_prevalence(p_inj, labels_base, target_prev, rng)

    # per-subset ECE (full 8-subset enumeration: used for Shapley + factorial interactions)
    vals = _ece_subsets(probs_base, labels_base, slope, intercept, prev_idx, metric)
    attrib = _attribution_from_subsets(vals)

    # recovery (post-resampling + King-Zeng correction; degeneracy caught, not raised through)
    pi_injected = float(labels_base.mean())
    recovery_failed = False
    pi_resampled_val = pi_injected
    try:
        if prev_idx is not None:
            labels_resampled = labels_base[prev_idx]
            p_resampled = p_inj[prev_idx]
            pi_resampled_val = float(labels_resampled.mean())
            rec = recover_slope_intercept(
                p_resampled, labels_resampled,
                pi_reference=pi_injected, pi_resampled=pi_resampled_val,
            )
        else:
            rec = recover_slope_intercept(p_inj, labels_base,
                                          pi_reference=pi_injected,
                                          pi_resampled=pi_injected)
    except ValueError:
        recovery_failed = True
        rec = {'s_hat': float('nan'), 'b_hat': float('nan'),
               'b_hat_raw': float('nan')}

    if recovery_failed:
        prev_hat = float('nan')
        prev_true = float(target_prev) if target_prev is not None else pi_injected
    elif prev_idx is not None:
        prev_hat = pi_resampled_val  # design-constant readback (resampling controls positive count)
        prev_true = float(target_prev)
    else:
        prev_hat = pi_injected
        prev_true = pi_injected

    # Fisher information (baseline weights; evaluated on the actual design = resampled subset)
    if prev_idx is not None:
        det = fisher_information_det(p_inj[prev_idx], probs_base[prev_idx])
    else:
        det = fisher_information_det(p_inj, probs_base)
    entangled = bool(det < IDENTIFIABILITY_TAU or recovery_failed)

    # Shapley share reliability: |delta_total| below the 10-bin ECE noise floor
    # (3-sigma heuristic) -> shares not interpretable
    share_floor = 3.0 / math.sqrt(max(len(probs_base), 1))
    shares_reliable = bool(abs(attrib['delta_total']) >= share_floor)

    return {
        'delta_total': attrib['delta_total'],
        'chain': attrib['chain'],
        'interactions': attrib['interactions'],
        'permutations': attrib['permutations'],
        'shapley': {**attrib['shapley'], 'shares_reliable': shares_reliable,
                    'share_floor': share_floor},
        'recovery': {'s_hat': rec['s_hat'], 'b_hat': rec['b_hat'],
                     'b_hat_raw': rec['b_hat_raw'],
                     'prev_hat': prev_hat, 'prev_true': prev_true},
        'recovery_failed': recovery_failed,
        'fisher_det': det,
        'entangled': entangled,
        'ece_subsets': vals,
    }


def bootstrap_decomposition(probs_base: np.ndarray, labels_base: np.ndarray,
                            slope: float, intercept: float,
                            target_prev: Optional[float],
                            n_bootstrap: int, rng: np.random.Generator,
                            metric=ece_metric_safe, confidence: float = 0.95) -> Dict:
    """Sample-level bootstrap CI for attribution quantities.

    Each repetition: resample baseline with replacement -> inject -> (if needed) resample by
    target_prev -> 8-subset ECE -> chain / factorial / Shapley (pure combinatorics). Recovery
    (logistic) is excluded from the bootstrap; the CI supports attribution ranking validity.

    Returns percentile CI (absolute scale): delta_total, the three chain components, the three
    absolute Shapley values, I_sb. Shares (ratios) carry no CI: the denominator can cross
    zero, making percentile meaningless; ranking decisions should use the CI of absolute Shapley
    values.
    """
    probs_base, labels_base = _validate_binary(probs_base, labels_base)
    n = len(labels_base)

    keys_num = ['delta_total', 'delta_s', 'delta_b', 'delta_pi',
                'shap_s', 'shap_b', 'shap_pi', 'I_sb']
    samples = {k: np.empty(n_bootstrap) for k in keys_num}

    for b in range(n_bootstrap):
        idx = rng.choice(n, n, replace=True)
        pb, yb = probs_base[idx], labels_base[idx]
        p_inj = inject_transform(pb, slope, intercept)
        prev_idx_b = None
        if target_prev is not None and abs(target_prev - yb.mean()) > 1e-9:
            prev_idx_b = resample_prevalence(p_inj, yb, target_prev, rng)
        vals = _ece_subsets(pb, yb, slope, intercept, prev_idx_b, metric)
        a = _attribution_from_subsets(vals)
        samples['delta_total'][b] = a['delta_total']
        samples['delta_s'][b] = a['chain']['delta_s']
        samples['delta_b'][b] = a['chain']['delta_b']
        samples['delta_pi'][b] = a['chain']['delta_pi']
        samples['shap_s'][b] = a['shapley']['values']['s']
        samples['shap_b'][b] = a['shapley']['values']['b']
        samples['shap_pi'][b] = a['shapley']['values']['pi']
        samples['I_sb'][b] = a['interactions']['I_sb']

    alpha = (1 - confidence) / 2 * 100
    out = {}
    for k, arr in samples.items():
        lo, hi = np.percentile(arr, [alpha, 100 - alpha])
        out[f'{k}_ci'] = (float(lo), float(hi))
    return out


def entangle_demo_cases(seed: int = 7) -> Dict[str, Dict]:
    """Construct degenerate baselines with det < tau to exercise the entanglement branch and
    recovery-failure path (synthetic demonstration).

    Three cases:
    1. narrow: p concentrated in a very narrow logit band (Var(x_base) ~ (0.0005)^2) -> det ~ 1.6e-8 < tau
    2. tiny_slope: s=0.001 -> x' = s*x ~ constant -> det ~ s^2 ~ 1.8e-7 < tau
    3. deep_intercept: b=-30 -> p' fully clipped -> x' constant -> det ~ 0 and recovery raises
       (verifies the unified path: recovery_failed=True rather than an exception propagating)
    """
    n = 2000
    cases = {}
    rng = np.random.default_rng(seed)

    p_narrow = np.clip(0.5 + 0.0005 * rng.standard_normal(n), 1e-3, 1 - 1e-3)
    y_narrow = (rng.uniform(0, 1, n) < p_narrow).astype(float)
    cases['narrow_band'] = (p_narrow, y_narrow, 1.0, 0.0, None)

    rng2 = np.random.default_rng(seed + 1)
    p_wide = rng2.uniform(0.05, 0.95, n)
    y_wide = (rng2.uniform(0, 1, n) < p_wide).astype(float)
    cases['tiny_slope'] = (p_wide, y_wide, 0.001, 0.0, None)
    cases['deep_intercept'] = (p_wide, y_wide, 1.0, -30.0, None)
    return cases
