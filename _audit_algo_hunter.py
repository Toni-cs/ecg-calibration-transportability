"""Audit of algo-hunter's three candidate directions.

Verifies: A (the +0.29 error), B (85% direction accuracy), C (direction 1 RMSE 0.0769),
and the target-variable confusion between `delta_obs` and `delta_obs_orig`.
"""
import json, warnings
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression

warnings.filterwarnings("ignore")

J = "results/strengthening_battle_corrected.json"
D = json.load(open(J))
MAIN = [r for r in D if r["arch"] != "mamba"]          # 60 main-grid cells


def col(rs, f):
    return np.array([r[f] for r in rs], dtype=float)


def sign(v):
    return np.sign(v)


print("=" * 78)
print("STEP 0: which field is the paper's primary endpoint?")
print("=" * 78)
dp, do, doo = col(MAIN, "delta_pred"), col(MAIN, "delta_obs"), col(MAIN, "delta_obs_orig")
raw, cal = col(MAIN, "raw_ood_orig"), col(MAIN, "cal_ood_orig")
print(f"max|(raw_ood_orig - cal_ood_orig) - delta_obs_orig| = {np.abs((raw-cal)-doo).max():.2e}")
print(f"  -> delta_obs_orig == raw - post  (paper's convention, line 1101)")
print(f"60-main mean delta_obs_orig = {doo.mean():+.6f}   (paper reports +0.0159)")
print(f"60-main mean delta_obs      = {do.mean():+.4f}   ({do.mean()/doo.mean():.0f}x larger)")
print(f"corr(delta_obs, delta_obs_orig) = {np.corrcoef(do, doo)[0,1]:+.4f}  <- near-independent")

T = col(MAIN, "T")
print("\nT-stratification (paper's own noise floor is 0.10-0.16 for T>3):")
for lo, hi in [(0, 1.5), (1.5, 2), (2, 3), (3, 5)]:
    k = (T >= lo) & (T < hi)
    if k.sum():
        print(f"  T in [{lo},{hi}) n={k.sum():2d} | delta_obs={do[k].mean():+.4f}"
              f"  delta_obs_orig={doo[k].mean():+.4f}")
print("  -> delta_obs scales monotonically with T == noise-floor signature")
print("  -> delta_obs_orig is T-invariant == the real endpoint")

print()
print("=" * 78)
print("STEP 1 (Discovery A): the '+0.29' figure")
print("=" * 78)
for tag, rs in [("60 main", MAIN), ("62 all", D)]:
    a, b, c = col(rs, "delta_pred"), col(rs, "delta_obs"), col(rs, "delta_obs_orig")
    e1, e2 = a - b, a - c
    print(f"--- {tag} (n={len(rs)}) ---")
    print(f"  delta_pred mean = {a.mean():+.4f}")
    print(f"  pred-err vs delta_obs      : mean={e1.mean():+.4f} median={np.median(e1):+.4f}")
    print(f"  pred-err vs delta_obs_orig : mean={e2.mean():+.4f} median={np.median(e2):+.4f}")
print("\npaper says '+0.29, median +0.29'")
print("  -> 60-main pred-err vs delta_obs_orig = mean +0.2856, median +0.2913  == MATCH")
print("  -> algo-hunter's '+0.1906' used delta_obs (wrong target)")

print()
print("=" * 78)
print("STEP 2 (Discovery B): 85% direction accuracy")
print("=" * 78)
print(f"dir-acc(delta_pred vs delta_obs_orig) = {(sign(dp)==sign(doo)).sum()}/{len(doo)}"
      f" = {(sign(dp)==sign(doo)).mean()*100:.1f}%")
print(f"constant 'always positive' baseline   = {(doo>0).sum()}/{len(doo)}"
      f" = {(doo>0).mean()*100:.1f}%")
print("  -> B CONFIRMED: 85% == 85% constant baseline, zero information")

print("\nrecon_F target alignment:")
F = pd.read_csv("_recon_F.csv")
j = {(r["source"], r["target"], r["arch"], r["seed"]): r for r in D}
fdo = np.array([j[(r["src"], r["tgt"], r["arch"], int(r["seed"]))]["delta_obs"] for _, r in F.iterrows()])
foo = np.array([j[(r["src"], r["tgt"], r["arch"], int(r["seed"]))]["delta_obs_orig"] for _, r in F.iterrows()])
print(f"  recon_F d_obs vs JSON delta_obs      corr={np.corrcoef(F.d_obs, fdo)[0,1]:.4f}")
print(f"  recon_F d_obs vs JSON delta_obs_orig corr={np.corrcoef(F.d_obs, foo)[0,1]:.4f}")
print("  -> recon_F/H/D/E all target the WRONG field (delta_obs)")

print()
print("=" * 78)
print("STEP 3 (Discovery C): direction 1, RMSE 0.0769")
print("=" * 78)
H = pd.read_csv("_recon_H.csv")
y_lab = H.d_obs.values
y_true = np.array([j[(r["src"], r["tgt"], r["arch"], int(r["seed"]))]["delta_obs_orig"]
                   for _, r in H.iterrows()])
G = ["T", "ece_cal", "ent_ratio", "conf_tgt", "conf_cal", "gap_cal", "pi_l1"]
G_PURE = ["T", "ent_ratio", "conf_tgt", "conf_cal", "pi_l1"]


def loo(feats, target, groups=None):
    X = H[feats].values if feats else np.zeros((len(H), 0))
    pr = np.empty(len(target))
    blocks = [np.arange(len(target))] if groups is None else \
             [H.index[H[groups] == g].values for g in H[groups].unique()]
    for blk in blocks:
        for i in blk:
            m = np.ones(len(target), bool)
            m[i] = False
            pr[i] = target[m].mean() if not feats else \
                LinearRegression().fit(X[m], target[m]).predict(X[i:i + 1])[0]
    e = pr - target
    return dict(rmse=np.sqrt((e ** 2).mean()), mae=np.abs(e).mean(),
                sign=np.mean(sign(pr) == sign(target)))


print("target = delta_obs (algo-hunter's, WRONG):")
for nm, f in [("constant", []), ("G (all 7)", G), ("G-pure (5 label-free)", G_PURE)]:
    r = loo(f, y_lab)
    print(f"  {nm:24s} RMSE={r['rmse']:.4f}  |err|={r['mae']:.4f}  sign={r['sign']:.3f}")

print("\ntarget = delta_obs_orig (paper's, CORRECT):")
for nm, f in [("constant", []), ("G (all 7)", G), ("G-pure (5 label-free)", G_PURE)]:
    r = loo(f, y_true)
    print(f"  {nm:24s} RMSE={r['rmse']:.4f}  |err|={r['mae']:.4f}  sign={r['sign']:.3f}")
print(f"\n  y(std) = {y_true.std():.4f}; constant RMSE must equal this")
print("  -> 0.0769 reproduces ONLY against the wrong target (+-0.0000)")
print("  -> against the real endpoint: 0.0121 vs constant 0.0148, sign UNCHANGED at 0.833 vs 0.850")

print("\nleave-one-direction-out (real deployment scenario):")
for nm, f in [("G-pure", G_PURE), ("T only", ["T"])]:
    r = loo(f, y_true, groups="src")
    print(f"  {nm:10s} RMSE={r['rmse']:.4f}  sign={r['sign']:.3f}")

print()
print("=" * 78)
print("STEP 4: feature correlations")
print("=" * 78)
for nm, v in [("ood_acc", col(MAIN, "ood_acc")), ("T", T), ("cal_ood_orig", cal),
              ("wasserstein", col(MAIN, "wasserstein"))]:
    print(f"  corr(delta_obs,      {nm:14s}) = {np.corrcoef(do, v)[0,1]:+.4f}")
    print(f"  corr(delta_obs_orig, {nm:14s}) = {np.corrcoef(doo, v)[0,1]:+.4f}")
print("  -> ood_acc -0.81 -> +0.13 under the correct target; claim is an artifact")

print()
print("=" * 78)
print("STEP 5: is delta_pred itself a T-driven artifact?")
print("=" * 78)
sh = np.array([[r["shapley"]["s"], r["shapley"]["b"], r["shapley"]["pi"]] for r in MAIN])
print(f"mean shapley: s={sh[:,0].mean():+.4f} b={sh[:,1].mean():+.4f} pi={sh[:,2].mean():+.4f}"
      f"  sum={sh.sum(1).mean():+.4f}")
print(f"corr(sh_pi, T)          = {np.corrcoef(sh[:,2], T)[0,1]:+.4f}")
print(f"corr(delta_pred, T)     = {np.corrcoef(sh.sum(1), T)[0,1]:+.4f}")
print(f"corr(sh_pi, do_orig)    = {np.corrcoef(sh[:,2], doo)[0,1]:+.4f}")
print("  -> pi component is 108% of delta_pred and is a T-proxy, not a shift signal")

print()
print("=" * 78)
print("STEP 6: paper's error-cluster / Wasserstein claims")
print("=" * 78)
err = [r for r in MAIN if sign(r["delta_pred"]) != sign(r["delta_obs_orig"])]
ok = [r for r in MAIN if sign(r["delta_pred"]) == sign(r["delta_obs_orig"])]
from collections import Counter
print("actual error clusters:", dict(Counter((r["source"], r["target"]) for r in err)))
print("paper claims CPSC->Chapman + Chapman->PTB-XL dominate: actual 2 each;")
print("  largest are Chapman->CPSC (2) and CPSC->PTB-XL (2) -> claim FALSE")
we = np.mean([r["wasserstein"] for r in err])
wo = np.mean([r["wasserstein"] for r in ok])
print(f"Wasserstein err={we:.3f} ok={wo:.3f} (paper reports 0.75 vs 0.53) -> FALSE")

print()
print("=" * 78)
print("VERDICT")
print("=" * 78)
print("""
Discovery A: HALF TRUE, WRONG NUMBERS. The paper's +0.29 IS delta_pred-mean, but
  the correct prediction error is +0.2856 mean / +0.2913 median vs delta_obs_orig
  -- which MATCHES the paper. algo-hunter's +0.1906 used delta_obs (wrong field).
  => The paper is NOT wrong about +0.29. It is only a wording lapse ("prediction
     error" for what it computed as pred - obs, sign convention consistent).

Discovery B: TRUE AND FATAL, but for a different reason than stated.
  85% == 85% constant baseline. Confirmed exactly. BUT the deeper problem is that
  the real endpoint's signal (0.0159) is 7x SMALLER than delta_obs (0.1068), which
  is a T-driven SmoothECE noise artifact. The paper's own noise floor for T>3 is
  0.10-0.16, and delta_obs hits 0.231 there.

Discovery C: FALSE. RMSE 0.0769 reproduces exactly, but only against the wrong
  target variable (delta_obs). Against the paper's real endpoint, features give
  0.0121 vs constant 0.0148 and do NOT improve direction accuracy (0.833 < 0.850).
  The claimed corr -0.814 with ood_acc is +0.13 under the correct target.
  Direction 1 is measuring the noise artifact, not the finding. RECOMMEND REJECT.
""")
