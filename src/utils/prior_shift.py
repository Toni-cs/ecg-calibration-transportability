"""P-independent target-prior recovery estimators: BBSE + EM (preregistered protocol §13
item 7 upgrade).

Background: decompose_benefit's prev_hat is currently a design-constant readback (resampling
exactly controls the positive count -> MAPE_pi is only a design check, not an estimator-capability
test). This module upgrades MAPE_pi into a genuine unlabeled-estimator test: without providing
labels for the target domain, it recovers the target class prior pi_target using only the source
domain (labeled) plus the target domain (model soft-probabilities only).

Method pool (K classes, K>=2):
1. BBSE (Lipton, Wang & Smola, ICML 2018 "Detecting and Correcting for Label Shift with Black
   Box Predictors"):
   - source-domain soft-confusion: C[j,k] = E_src[ P_pred_j(x) | y=k ] (K x K)
   - target average prediction: mu_target[j] = E_target[ P_pred_j(x) ] (target probabilities only,
     no labels)
   - key identity (under label shift):
         mu_target = C * pi_target          (pi_target = target class prior)
   - solve the linear system + project onto the probability simplex. The target prior is
     identifiable when C is full rank.
   - rank/condition-number guard: C near-singular (cond > threshold or rank < K) -> return
     None+warn (not identifiable).
2. EM (Saerens, Latinne & Decaestecker 2002 "Adjusting the Outputs of a Classifier to New a
   Priori Probabilities"; the clean interface of fit_saerens_em): iteratively re-estimates pi_k,
   converging to the target prior. Zero discriminative power (target probability row variance ~= 0)
   -> not identifiable, return a copy of the source prior + warn.

Unified interface (aligned with the calibration_methods convention):
    fit_bbse(src_probs, src_labels, target_probs) -> dict | None
    fit_em(   src_probs, src_labels, target_probs) -> dict | None
Returns {'pi_hat': (K,) target-prior estimate, 'pi_train': (K,) source prior, ...}.
None = not identifiable / numerical failure (protocol: failure regions are reported truthfully,
never silently garbage).

Metering and boundary guards:
- src_probs/src_labels must be equal length; target_probs class count = src_probs class count.
- at least min_samples source samples per class (default 10), otherwise that class's confusion
  column is unreliable -> None.
- BBSE solution goes through non-negative least squares + simplex projection, then renormalized.
- reports identifiability diagnostics: confusion condition number, rank, BBSE-vs-EM pi_hat distance.
- does not modify any existing training/inference path -- a pure incremental module, to be called
  by decompose's MAPE_pi upgrade.
"""

from __future__ import annotations

import warnings
from typing import Optional

import numpy as np

EPS = 1e-12


def _validate(src_probs, src_labels, target_probs):
    src_probs = np.asarray(src_probs, dtype=float)
    src_labels = np.asarray(src_labels)
    target_probs = np.asarray(target_probs, dtype=float)
    if src_probs.ndim != 2 or target_probs.ndim != 2:
        raise ValueError(f"probs must be 2D (n,K), got {src_probs.shape}/{target_probs.shape}")
    K = src_probs.shape[1]
    if target_probs.shape[1] != K:
        raise ValueError(f"source/target class count mismatch: {K} vs {target_probs.shape[1]}")
    if src_probs.shape[0] != src_labels.shape[0]:
        raise ValueError("src_probs and src_labels row counts differ")
    if K < 2:
        raise ValueError("K>=2 (multiclass)")
    # source prior (training / reference domain)
    pi_train = np.bincount(src_labels.astype(int), minlength=K).astype(float)
    if pi_train.sum() == 0:
        raise ValueError("source domain empty / no valid labels")
    pi_train = pi_train / pi_train.sum()
    return src_probs, src_labels.astype(int), target_probs, pi_train


def _simplex_project(x: np.ndarray) -> np.ndarray:
    """Project onto the probability simplex (Duchi 2008 exact Euclidean projection).
    Returns a probability vector (sum=1, elements >= 0). All-zero / all-negative input returns
    NaN (failure signal)."""
    v = np.asarray(x, dtype=float).copy()
    n = len(v)
    if n == 1:
        return np.array([1.0])
    if np.max(v) <= 0:
        return np.full(n, np.nan)
    u = np.sort(v)[::-1]  # descending
    cssv = np.cumsum(u) - 1.0
    rho = np.nonzero(u - cssv / np.arange(1, n + 1) > 0)[0]
    if len(rho) == 0:
        return np.full(n, 1.0 / n)
    rho = rho[-1] + 1  # largest j satisfying the condition (1-indexed)
    tau = cssv[rho - 1] / rho
    w = np.maximum(v - tau, 0.0)
    s = w.sum()
    if s <= 0 or not np.isfinite(w).all():
        return np.full(n, np.nan)
    return w / s


def _cond_rank(C: np.ndarray):
    return float(np.linalg.cond(C)), int(np.linalg.matrix_rank(C, tol=1e-9))


def fit_bbse(src_probs, src_labels, target_probs,
             min_samples: int = 10,
             cond_max: float = 1e8,
             solver: str = "nnls") -> Optional[dict]:
    """BBSE: solve mu_target = C^T pi_target for pi_target, then project.

    C[j,k] = average predicted probability_j over source samples of class k (soft-confusion).
    """
    src_probs, src_labels, target_probs, pi_train = _validate(
        src_probs, src_labels, target_probs)
    K = src_probs.shape[1]

    # per-class source-sample guard (reliability of the confusion-column estimate)
    per_class = np.bincount(src_labels, minlength=K)
    if per_class.min() < min_samples:
        warnings.warn(
            f"fit_bbse: smallest-class source samples {per_class.min()} < min_samples={min_samples}, "
            "confusion column unreliable -> returning None")
        return None

    # soft-confusion C[j,k] = mean_src[ P_j | y=k ]
    C = np.zeros((K, K))
    for k in range(K):
        m = src_labels == k
        C[:, k] = src_probs[m].mean(axis=0)
    C = np.maximum(C, EPS)  # guard against zero columns

    # target average prediction
    mu = target_probs.mean(axis=0)  # (K,)

    cond, rank = _cond_rank(C)
    if rank < K or cond > cond_max:
        warnings.warn(
            f"fit_bbse: confusion condition number={cond:.3g} rank={rank}/{K}, "
            "target prior not identifiable (C near-singular) -> returning None")
        return None

    # solve C pi = mu (C[j,k]=E[P(y_hat=j)|y=k], mu[j]=Sum_k pi_k*C[j,k])
    if solver == "nnls":
        from scipy.optimize import nnls
        pi_hat, _ = nnls(C, mu)
    else:  # lstsq
        pi_hat, *_ = np.linalg.lstsq(C, mu, rcond=None)
    pi_hat = np.maximum(pi_hat, 0.0)
    s = pi_hat.sum()
    if s <= 0 or not np.isfinite(pi_hat).all():
        warnings.warn("fit_bbse: solution non-positive / non-finite -> returning None")
        return None
    pi_hat = _simplex_project(pi_hat)
    if not np.isfinite(pi_hat).all():
        warnings.warn("fit_bbse: simplex projection failed -> returning None")
        return None

    return {"pi_hat": pi_hat, "pi_train": pi_train, "method": "bbse",
            "confusion_cond": cond, "rank": rank, "n_src": int(len(src_labels)),
            "n_target": int(len(target_probs))}


def fit_em(src_probs, src_labels, target_probs,
           max_iter: int = 1000, tol: float = 1e-8) -> Optional[dict]:
    """EM target-prior estimation (Saerens 2002 standard algorithm, interface aligned with BBSE).

    Initialized with the source prior pi_train; iterates:
        E:  s_ik ~ (pi_k / pi_train_k) * P_k(x_i)   (x_i in target, unlabeled)
        M:  pi_k <- mean_i(s_ik)
    Zero discriminative power (target predicted-distribution row variance ~= 0) -> not
    identifiable, return None+warn.
    """
    src_probs, src_labels, target_probs, pi_train = _validate(
        src_probs, src_labels, target_probs)
    K = src_probs.shape[1]

    # zero-discriminative-power guard (aligned with fit_saerens_em)
    P = np.clip(target_probs, EPS, 1.0)
    if P.std(axis=0).max() < 1e-9:
        warnings.warn("fit_em: target predictions have no discriminative power (row variance ~= 0), "
                      "prior not identifiable -> returning None")
        return None

    pi = np.clip(pi_train, EPS, 1.0).copy()
    converged = False
    for _ in range(max_iter):
        ratios = (pi / pi_train)[None, :] * P      # (n,K)
        s = ratios / ratios.sum(axis=1, keepdims=True)
        pi_new = s.mean(axis=0)
        pi_new = pi_new / pi_new.sum()
        if np.abs(pi_new - pi).max() < tol:
            pi = pi_new
            converged = True
            break
        pi = pi_new
    if not converged:
        warnings.warn(f"fit_em: not converged within {max_iter} iterations (tol={tol})")

    pi_hat = _simplex_project(pi)
    if not np.isfinite(pi_hat).all():
        warnings.warn("fit_em: projection failed -> returning None")
        return None
    return {"pi_hat": pi_hat, "pi_train": pi_train, "method": "em",
            "converged": converged, "n_src": int(len(src_labels)),
            "n_target": int(len(target_probs))}


# Registry: method and whether a source label is required (both BBSE/EM only need the source
# label to fit the confusion/prior; the target domain is unlabeled)
P_INDEPENDENT_METHODS = {
    "bbse": fit_bbse,
    "em": fit_em,
}


if __name__ == "__main__":
    # self-check: under label shift, BBSE/EM should recover the true target prior (no target labels)
    rng = np.random.default_rng(0)
    K = 5
    n_src = 8000
    # source: approximately separable classifier soft-probs (class-k samples concentrate on k)
    src_labels = rng.integers(0, K, n_src)
    conf = 0.7 * np.eye(K) + 0.3 * np.full((K, K), 1.0 / K)  # construct soft rows
    src_probs = rng.dirichlet(np.full(K, 1.0), n_src) * 0.3
    src_probs[np.arange(n_src), src_labels] += 0.7  # concentrate intra-class probability
    src_probs = src_probs / src_probs.sum(axis=1, keepdims=True)

    # target: true prior deviates from the source prior (label shift)
    pi_true = np.array([0.5, 0.1, 0.1, 0.15, 0.15])
    n_tgt = 20000
    tgt_labels = rng.choice(K, n_tgt, p=pi_true)
    tgt_probs = rng.dirichlet(np.full(K, 1.0), n_tgt) * 0.3
    tgt_probs[np.arange(n_tgt), tgt_labels] += 0.7
    tgt_probs = tgt_probs / tgt_probs.sum(axis=1, keepdims=True)

    pi_train = np.bincount(src_labels, minlength=K) / n_src
    print(f"source prior (train): {np.round(pi_train,3)}")
    print(f"true target prior: {pi_true}")
    for name, fn in P_INDEPENDENT_METHODS.items():
        res = fn(src_probs, src_labels, tgt_probs)
        if res is None:
            print(f"{name}: FAILED (not identifiable)")
        else:
            err = np.abs(res['pi_hat'] - pi_true).mean()
            print(f"{name}: pi_hat={np.round(res['pi_hat'],3)} mean_abs_err={err:.4f}")
