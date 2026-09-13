"""Calibration method library extension (preregistered protocol §5 method pool M1-M13).

Unified interface: fit_X(input, labels) -> params; apply_X(input, params) -> calibrated_probs_2d.
logit discipline: probability inputs are clipped to [1e-12,1] internally before taking log
(saturation-region guard).

Method list:
- isotonic:  per-class OvR IsotonicRegression (small-sample guard: returns None when n_cal < 10K)
- vector:    diagonal scale + bias (2K parameters)
- matrix:    full-matrix scale + bias (K^2+K parameters, expected to fail at small sample sizes)
- dirichlet: Kull et al. 2019, affine map in log-probability space (feature augmentation +
            multinomial LR)
- saerens:   Saerens et al. 2002 EM prior estimation (unlabeled) + prior correction
- oracle:    temperature fit on the target-domain cal (upper bound)

Registry CALIBRATION_METHODS is iterated over by the experiment runner.
"""

import warnings
from typing import Dict, Optional, Tuple, Callable

import numpy as np
from scipy.optimize import minimize
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

EPS = 1e-12
SCALE_MIN, SCALE_MAX = 0.05, 20.0
BIAS_MIN, BIAS_MAX = -10.0, 10.0


def _to_logits(probs: np.ndarray) -> np.ndarray:
    """Probabilities -> logits (2D, row-independent, saturation guard)."""
    p = np.clip(np.asarray(probs, dtype=float), EPS, 1.0)
    return np.log(p)


def _to_probs(logits: np.ndarray) -> np.ndarray:
    """Logits -> probabilities (numerically stable softmax)."""
    z = np.asarray(logits, dtype=float)
    z = z - z.max(axis=-1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=-1, keepdims=True)


def _nll(logits: np.ndarray, labels_onehot: np.ndarray) -> float:
    """Multiclass NLL (logits, one-hot (n,K))."""
    z = logits - logits.max(axis=1, keepdims=True)
    logp = z - np.log(np.exp(z).sum(axis=1, keepdims=True))
    return float(-(logp * labels_onehot).sum(axis=1).mean())


# =====================================================================
# 1. Isotonic (OvR)
# =====================================================================

def fit_isotonic(val_probs: np.ndarray, val_labels: np.ndarray,
                 min_per_class: int = 10) -> Optional[dict]:
    """Per-class one-vs-rest isotonic regression.

    Small-sample guard (preregistered protocol: isotonic fails when n_cal <= 100). The guard uses
    <= to avoid an off-by-one where the original n < 10*K guard did not trigger at n_cal=50, K=5.
    """
    val_probs = np.asarray(val_probs, dtype=float)
    val_labels = np.asarray(val_labels)
    n, K = val_probs.shape
    _assert_labels_valid(val_labels, K)
    if n <= min_per_class * K:  # guard uses <= to prevent off-by-one
        warnings.warn(f"fit_isotonic: n_cal={n} <= 10*K={min_per_class*K}, "
                      f"isotonic overfitting risk (preregistered failure region), returning None")
        return None
    models = {}
    total_steps = 0
    for k in range(K):
        ir = IsotonicRegression(out_of_bounds='clip', y_min=0.0, y_max=1.0)
        ir.fit(val_probs[:, k], (val_labels == k).astype(float))
        models[k] = ir
        # report actual degrees of freedom (number of steps), not a linear function of n
        total_steps += max(len(ir.X_thresholds_) - 1, 0)
    return {'models': models, 'n_params': total_steps}


def apply_isotonic(probs: np.ndarray, params: dict) -> np.ndarray:
    """apply: map per class then renormalize (note: breaks rank invariance, declared in docstring).

    Fall back to raw probs when the renormalized row sum is 0 (prevents an all-zero row from
    silently being assigned the wrong class).
    """
    if params is None:
        raise ValueError("fit_isotonic returned None (small sample); cannot apply -- runner should skip")
    probs = np.asarray(probs, dtype=float)
    out = np.stack(
        [params['models'][k].predict(probs[:, k]) for k in range(probs.shape[1])],
        axis=1,
    )
    out = np.clip(out, 0.0, 1.0)
    s = out.sum(axis=1, keepdims=True)
    fallback = s[:, 0] <= 0
    out[fallback] = probs[fallback]  # all-zero row falls back to raw
    s = out.sum(axis=1, keepdims=True)
    s[s <= 0] = 1.0
    return out / s


# =====================================================================
# 2. Vector scaling
# =====================================================================

def fit_vector_scaling(val_probs: np.ndarray, val_labels: np.ndarray) -> dict:
    """Diagonal scale w(K) + bias b(K): logit' = w * logit + b (2K parameters)."""
    val_probs = np.asarray(val_probs, dtype=float)
    K = val_probs.shape[1]
    val_labels = np.asarray(val_labels)
    _assert_labels_valid(val_labels, K)
    labels_onehot = np.eye(K)[val_labels]
    z = _to_logits(val_probs)

    def objective(theta):
        w, b = theta[:K], theta[K:]
        if np.any(w < SCALE_MIN) or np.any(w > SCALE_MAX):
            return 1e10
        return _nll(w * z + b, labels_onehot)

    x0 = np.concatenate([np.ones(K), np.zeros(K)])
    res = minimize(objective, x0, method='L-BFGS-B',
                   bounds=[(SCALE_MIN, SCALE_MAX)] * K + [(BIAS_MIN, BIAS_MAX)] * K)
    w, b = res.x[:K], res.x[K:]
    return {'w': w, 'b': b, 'n_params': 2 * K}


def apply_vector_scaling(probs: np.ndarray, params: dict) -> np.ndarray:
    z = _to_logits(probs)
    return _to_probs(params['w'] * z + params['b'])


# =====================================================================
# 3. Matrix scaling
# =====================================================================

def fit_matrix_scaling(val_probs: np.ndarray, val_labels: np.ndarray,
                       ridge: float = 1e-6, min_cal_per_param: float = 2.0) -> Optional[dict]:
    """Full matrix M(KxK) + b: logit' = M * logit + b (K^2+K parameters).

    Protocol expectation: collapses (over-parameterized) when n_cal <= 100.
    Guard: return None+warn when n_cal < 2*(K^2+K) (statistical-failure prevention); when
    optimization fails (res.success=False) return None+warn, never silently return garbage
    parameters.
    """
    val_probs = np.asarray(val_probs, dtype=float)
    val_labels = np.asarray(val_labels)
    _assert_labels_valid(val_labels, val_probs.shape[1])
    K = val_probs.shape[1]
    nP = K * K + K
    n = len(val_probs)
    if n < min_cal_per_param * nP:
        warnings.warn(f"fit_matrix_scaling: n_cal={n} < 2*(K^2+K)={min_cal_per_param*nP}, "
                      f"over-parameterized (preregistered failure region), returning None")
        return None
    labels_onehot = np.eye(K)[val_labels]
    z = _to_logits(val_probs)

    def objective(theta):
        M = theta[:K * K].reshape(K, K)
        b = theta[K * K:]
        out = z @ M.T + b
        if not np.isfinite(out).all() or np.abs(out).max() > 50:
            return 1e10
        return _nll(out, labels_onehot)

    x0 = np.concatenate([np.eye(K).ravel(), np.zeros(K)])
    bounds = [(None, None)] * (K * K) + [(BIAS_MIN, BIAS_MAX)] * K
    res = minimize(objective, x0, method='L-BFGS-B',
                   bounds=bounds, options={'maxiter': 500})
    if not res.success:  # never silently fail
        warnings.warn(f"fit_matrix_scaling: optimization did not converge (status={res.status}), returning None")
        return None
    M = res.x[:K * K].reshape(K, K) + ridge * np.eye(K)
    b = res.x[K * K:]
    return {'M': M, 'b': b, 'n_params': nP, 'converged': True}


def apply_matrix_scaling(probs: np.ndarray, params: dict) -> np.ndarray:
    if params is None:
        raise ValueError("fit_matrix_scaling returned None (small sample / not converged); "
                         "cannot apply -- runner should skip this cell")
    z = _to_logits(probs)
    return _to_probs(z @ params['M'].T + params['b'])


# =====================================================================
# 4. Dirichlet calibration (Kull et al. 2019)
# =====================================================================

def _assert_labels_valid(labels: np.ndarray, K: int):
    """Label validity assertion (guards against silent garbage such as label wraparound)."""
    labels = np.asarray(labels)
    if labels.size and (labels.min() < 0 or labels.max() >= K):
        raise ValueError(f"label out of range: valid range [0,{K}), "
                         f"actual range [{labels.min()},{labels.max()}] -- "
                         f"check for an injected -1 (unlabeled sentinel)")


def _dirichlet_features(probs: np.ndarray) -> np.ndarray:
    """phi(p) = [log p_1..log p_K, log p_1..log p_{K-1}] ((2K-1)-dimensional).

    Kull 2019 section 4: Dirichlet calibration = affine map in log-probability space + softmax.
    """
    lp = _to_logits(probs)  # log p
    return np.concatenate([lp, lp[:, :-1]], axis=1)


def fit_dirichlet(val_probs: np.ndarray, val_labels: np.ndarray,
                  C: float = 1e4) -> dict:
    """Dirichlet calibration: feature augmentation + multinomial logistic regression.

    Note: sklearn's LR applies L2 regularization (with C=1e4 it approximates unregularized MLE),
    so this is an approximation, declared in the docstring. n_params = K*(2K-1) + K.
    """
    val_probs = np.asarray(val_probs, dtype=float)
    val_labels = np.asarray(val_labels)
    X = _dirichlet_features(val_probs)
    lr = LogisticRegression(solver='lbfgs', C=C, max_iter=5000)
    lr.fit(X, val_labels)
    return {'lr': lr, 'n_params': lr.coef_.size + lr.intercept_.size}


def apply_dirichlet(probs: np.ndarray, params: dict) -> np.ndarray:
    """apply (reorder into K columns by lr.classes_, zeroing absent classes then renormalize)."""
    probs = np.asarray(probs, dtype=float)
    K = probs.shape[1]
    X = _dirichlet_features(probs)
    raw = params['lr'].predict_proba(X)          # (n, len(classes_)), may be < K
    classes = params['lr'].classes_
    out = np.zeros((probs.shape[0], K))
    for j, c in enumerate(classes):
        out[:, int(c)] = raw[:, j]
    s = out.sum(axis=1, keepdims=True)
    s[s <= 0] = 1.0
    return out / s


# =====================================================================
# 5. Saerens EM prior adaptation (unlabeled)
# =====================================================================

def fit_saerens_em(target_probs_unlabeled: np.ndarray,
                   prior_train: np.ndarray,
                   max_iter: int = 1000,
                   tol: float = 1e-8) -> np.ndarray:
    """Saerens et al. 2002 EM estimation of the target prior (no target labels needed).

    Iteration: s_ik ~ pi_k * p_k(x_i) / pi_train_k -> pi_k = mean_i(s_ik)
    converges to the target-domain prior pi_target.

    Guards:
    - zero discriminative power (predicted distribution row variance ~= 0): EM is not
      identifiable, return a copy of prior_train and warn (the original implementation collapsed
      to the one-hot argmin(prior_train) vertex, making downstream prior correction classify all
      samples as one class)
    - not converged within max_iter: warn
    """
    P = np.clip(np.asarray(target_probs_unlabeled, dtype=float), EPS, 1.0)
    pi_train = np.asarray(prior_train, dtype=float)
    pi = np.clip(pi_train, EPS, 1.0).copy()

    # zero-discriminative-power detection: inter-row variance of predicted distribution ~= 0
    # -> EM not identifiable
    if P.std(axis=0).max() < 1e-9:
        warnings.warn("fit_saerens_em: target predictions have no discriminative power "
                      "(row variance ~= 0), prior not identifiable, returning copy of prior_train")
        return pi_train.copy()

    converged = False
    for _ in range(max_iter):
        # E step: s_ik ~ (pi_k / pi_train_k) * p_ik
        ratios = (pi / pi_train)[None, :] * P  # (n, K)
        s = ratios / ratios.sum(axis=1, keepdims=True)
        # M step
        pi_new = s.mean(axis=0)
        pi_new = pi_new / pi_new.sum()
        if np.abs(pi_new - pi).max() < tol:
            pi = pi_new
            converged = True
            break
        pi = pi_new

    if not converged:
        warnings.warn(f"fit_saerens_em: not converged within {max_iter} iterations (tol={tol}), "
                      f"returning current estimate (under-converged)")
    return pi


def apply_prior_correction(probs: np.ndarray, pi_train: np.ndarray,
                           pi_target: np.ndarray) -> np.ndarray:
    """Prior correction (BCTS-style): logit' = logit + log(pi_target / pi_train)."""
    z = _to_logits(probs)
    shift = np.log(np.clip(np.asarray(pi_target, dtype=float), EPS, 1.0)
                   / np.clip(np.asarray(pi_train, dtype=float), EPS, 1.0))
    return _to_probs(z + shift[None, :])


# =====================================================================
# 6. Oracle (temperature fit on target-domain cal, upper bound)
# =====================================================================

def fit_oracle(target_cal_probs: np.ndarray, target_cal_labels: np.ndarray) -> dict:
    """Oracle upper bound: fit a global temperature on the target cal split (protocol §6 definition)."""
    K = np.asarray(target_cal_probs).shape[1]
    onehot = np.eye(K)[np.asarray(target_cal_labels)]

    def objective(theta):
        T = theta[0]
        if T < 0.01 or T > 100.0:
            return 1e10
        return _nll(_to_logits(target_cal_probs) / T, onehot)

    res = minimize(objective, np.array([1.0]), method='L-BFGS-B',
                   bounds=[(0.01, 100.0)])
    return {'T': float(res.x[0]), 'n_params': 1}


def apply_oracle(probs: np.ndarray, params: dict) -> np.ndarray:
    return _to_probs(_to_logits(probs) / params['T'])


# =====================================================================
# 7. none / ts / platt + registry
# =====================================================================

def apply_none(probs: np.ndarray, params: dict = None) -> np.ndarray:
    return np.asarray(probs, dtype=float).copy()


def fit_temperature_multiclass(val_probs: np.ndarray,
                               val_labels: np.ndarray) -> dict:
    """Standard multiclass temperature scaling (Guo et al. 2017)."""
    K = np.asarray(val_probs).shape[1]
    onehot = np.eye(K)[np.asarray(val_labels)]

    def objective(theta):
        T = theta[0]
        if T < 0.01 or T > 100.0:
            return 1e10
        return _nll(_to_logits(val_probs) / T, onehot)

    res = minimize(objective, np.array([1.0]), method='L-BFGS-B',
                   bounds=[(0.01, 100.0)])
    return {'T': float(res.x[0]), 'n_params': 1}


def apply_temperature_multiclass(probs: np.ndarray, params: dict) -> np.ndarray:
    return _to_probs(_to_logits(probs) / params['T'])


def fit_platt_multiclass(val_probs: np.ndarray, val_labels: np.ndarray) -> dict:
    """Per-class Platt (OvR, per-class (s,b), logit space: sigmoid(s * logit(p) + b))."""
    from scipy.special import expit
    val_probs = np.asarray(val_probs, dtype=float)
    val_labels = np.asarray(val_labels)
    K = val_probs.shape[1]
    _assert_labels_valid(val_labels, K)
    params = {}
    for k in range(K):
        y = (val_labels == k).astype(float)
        p = np.clip(val_probs[:, k], EPS, 1 - EPS)
        z = np.log(p / (1 - p))  # logit

        def objective(ab):
            s, b = ab
            if s < SCALE_MIN or s > SCALE_MAX:
                return 1e10
            pred = expit(s * z + b)  # same form as apply (logit space)
            pred = np.clip(pred, 1e-12, 1 - 1e-12)
            return float(-(y * np.log(pred) + (1 - y) * np.log(1 - pred)).mean())

        res = minimize(objective, np.array([1.0, 0.0]), method='L-BFGS-B',
                       bounds=[(SCALE_MIN, SCALE_MAX), (BIAS_MIN, BIAS_MAX)])
        params[k] = (float(res.x[0]), float(res.x[1]))
    return {'models': params, 'n_params': 2 * K}


def apply_platt_multiclass(probs: np.ndarray, params: dict) -> np.ndarray:
    """apply is isomorphic to fit: sigmoid(s * logit(p) + b), per class then renormalize."""
    from scipy.special import expit
    probs = np.asarray(probs, dtype=float)
    p = np.clip(probs, EPS, 1 - EPS)
    z = np.log(p / (1 - p))  # logit (the original implementation misused odds)
    out = np.stack([
        expit(params['models'][k][0] * z[:, k] + params['models'][k][1])
        for k in range(probs.shape[1])
    ], axis=1)
    out = out / out.sum(axis=1, keepdims=True)
    return out


# Method registry: (fit_fn, apply_fn, needs_labels)
# saerens is included in the registry (needs_labels=False; special fit signature:
#   _fit_saerens_entry(target_probs_unlabeled, prior_train) -> pi_train=prior_train used as the
#   train prior; the runner routes by needs_labels: when False it passes the second argument as
#   "train prior" rather than labels)
def _fit_saerens_entry(target_probs_unlabeled, prior_train, **kw):
    return {'pi_target': fit_saerens_em(target_probs_unlabeled, prior_train, **kw),
            'pi_train': np.asarray(prior_train, dtype=float), 'n_params': 0}


def _apply_saerens_entry(probs, params):
    return apply_prior_correction(probs, params['pi_train'], params['pi_target'])


CALIBRATION_METHODS: Dict[str, Tuple[Callable, Callable, bool]] = {
    'none': (lambda p, y=None: {'n_params': 0}, apply_none, False),
    'ts': (fit_temperature_multiclass, apply_temperature_multiclass, True),
    'platt': (fit_platt_multiclass, apply_platt_multiclass, True),
    'isotonic': (fit_isotonic, apply_isotonic, True),
    'vector': (fit_vector_scaling, apply_vector_scaling, True),
    'matrix': (fit_matrix_scaling, apply_matrix_scaling, True),
    'dirichlet': (fit_dirichlet, apply_dirichlet, True),
    'saerens': (_fit_saerens_entry, _apply_saerens_entry, False),
    'oracle': (fit_oracle, apply_oracle, True),
}
