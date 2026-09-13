"""Synthetic-injection validation of the three-component decomposition v3:
27-cell full factorial grid + Fisher identifiability + sample-size-adaptive gate.

(preregistered protocol docs/EXPERIMENT_PROTOCOL.md, §8-2 / §8-3)

Design governance:
- Output filenames include the sample size (decomposition_validation_n{n}.csv /
  decomposition_error_map_n{n}.png) so n=500 does not overwrite n=20000; --output
  redirects writes (tests write to tmp, not results/); CSV self-describes (n/seed columns).
- Honesty: the gate(n) = max(10%, 3*MAPE_REF*sqrt(N_REF/n)) is a heuristic scaling
  (MAPE_REF is a single-seed single-run measurement); the measured violation rate at
  n=500 is ~22% (see archived n=500 CSV); --seeds N (default 1) provides multi-seed
  violation-rate measurements.
- The MAPE_pi column is renamed mape_pi_design_pct and documented: prev_hat is the
  resampled label frequency, a design-constant readback (one of the three gate components
  is always satisfied); pi is recovered independently (BBSE/EM), a legacy item, see protocol §13.
- Shapley: the CSV reports both absolute values (shapley_val_*) and shares; a
  share_reliable column flags cells where |delta_total| < 3/sqrt(n) (uninterpretable);
  share CIs are not reported (denominator can cross zero), absolute CIs come from --boot.
- --boot B (default 1000): per-cell attribution bootstrap CI over 27 cells; the
  entanglement demo (entangle_demo_cases) runs by default and asserts the entangled
  branch is reachable.
- Exit codes: identifiable cell FAIL -> 1 (preregistered n) / -> 2 (informative mode n<20000,
  no longer always 0); all entangled (design-failure signal) -> 3; entanglement demo
  failure -> 5; PASS -> 0.
- CSV also adds chain_residual column (protocol §8-1 explicit interaction-residual report);
  gate column stores a fraction (same scale as mape_b_abs), mape_*_pct are percentages.

Preregistered design (hard-coded; deviation from the registered protocol §8-2 revision note):
- Baseline: n=20000, p~Uniform(0.05,0.95), y~Bernoulli(p), seed=42.
- Grid: slope{0.5,1,2} x intercept{-1,0,1} x prev_target{0.15,0.3,0.6} = 27 cells
  (the protocol's prevalence x{0.5,1,2} multiplicative grid is infeasible: x2 -> pi=1.0
  exhausts positives, x1 ~ baseline does not trigger resampling; reason and date in the
  protocol revision log).
- Per cell: inject -> resample -> (post-resample) recover + KZ correction -> error.
- Identifiability: det(FI) >= tau = 1e-6; det < tau is the entangled region, only recorded.
- Gate (preregistered decision at n=20000): MAPE_s < gate and MAPE_pi < gate and |b_hat - b| < gate
  (gate is a fraction; s/pi sides compared as percentages).
- Exit codes: see above.

Usage:
    python scripts/validate_decomposition.py                     # n=20000, boot=1000
    python scripts/validate_decomposition.py --n 500             # real calibration-set scale (informative mode)
    python scripts/validate_decomposition.py --boot 0            # disable bootstrap CI (fast)
    python scripts/validate_decomposition.py --seeds 8           # multi-seed violation-rate measurement
    python scripts/validate_decomposition.py --output DIR        # redirect output (for tests)
"""

import argparse
import csv
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from src.utils.calibration import ece
from src.utils.decomposition import (
    decompose_benefit,
    bootstrap_decomposition,
    entangle_demo_cases,
    identifiability_gate,
    IDENTIFIABILITY_TAU,
)

SLOPES = [0.5, 1.0, 2.0]
INTERCEPTS = [-1.0, 0.0, 1.0]
TARGET_PREVS = [0.15, 0.3, 0.6]
N_BASE = 20000
SEED = 42

EXIT_OK = 0
EXIT_FAIL_PREREG = 1
EXIT_FAIL_INFO = 2
EXIT_ALL_ENTANGLED = 3
EXIT_ENTANGLE_DEMO_FAILED = 5


def build_baseline(n=N_BASE, seed=SEED):
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.05, 0.95, n)
    y = rng.binomial(1, p).astype(float)
    return p, y


def run_grid(p_base, y_base, n, n_boot, boot_seed=SEED):
    rows = []
    cell = 0
    gate = identifiability_gate(n)          # fraction (0.10~0.23)
    gate_pct = gate * 100.0                 # MAPE_s/MAPE_pi compared as percentages
    gate_b_abs = gate                       # MAPE_b compared as absolute value (n=20000 -> 0.1 = protocol original value)
    for target_prev in TARGET_PREVS:
        for slope in SLOPES:
            for intercept in INTERCEPTS:
                cell += 1
                rng = np.random.default_rng([SEED, cell])
                out = decompose_benefit(
                    p_base, y_base, slope, intercept, target_prev,
                    rng=rng, metric=ece,
                )
                s_hat = out['recovery']['s_hat']
                b_hat = out['recovery']['b_hat']
                prev_hat = out['recovery']['prev_hat']

                det = out['fisher_det']
                identifiable = bool(det >= IDENTIFIABILITY_TAU)

                if not out['recovery_failed']:
                    mape_s = abs(s_hat - slope) / abs(slope) * 100.0
                    mape_b = abs(b_hat - intercept)
                    mape_pi = abs(prev_hat - target_prev) / target_prev * 100.0
                    gate_ok = (mape_s < gate_pct and mape_pi < gate_pct
                               and mape_b < gate_b_abs)
                else:
                    mape_s = mape_b = mape_pi = float('nan')
                    gate_ok = False

                passed = bool(identifiable and gate_ok)

                sh = out['shapley']
                row = {
                    'cell': cell,
                    'n': n,
                    'seed': SEED,
                    'slope': slope,
                    'intercept': intercept,
                    'target_prev': target_prev,
                    'det_fi': det,
                    'identifiable': identifiable,
                    'recovery_failed': out['recovery_failed'],
                    's_hat': s_hat,
                    'b_hat': b_hat,
                    'b_hat_raw': out['recovery']['b_hat_raw'],
                    'prev_hat': prev_hat,
                    'mape_s_pct': mape_s,
                    'mape_b_abs': mape_b,
                    'mape_pi_design_pct': mape_pi,  # Design check (constant readback), not an estimator-capability test.
                    'delta_total': out['delta_total'],
                    'delta_s_chain': out['chain']['delta_s'],
                    'delta_b_chain': out['chain']['delta_b'],
                    'delta_pi_chain': out['chain']['delta_pi'],
                    'chain_residual': out['chain']['residual'],  # Protocol §8-1 explicit report.
                    'I_sb': out['interactions']['I_sb'],
                    'I_s_pi': out['interactions']['I_s_pi'],
                    'I_b_pi': out['interactions']['I_b_pi'],
                    'I_3way': out['interactions']['I_3way'],
                    'shapley_val_s': sh['values']['s'],
                    'shapley_val_b': sh['values']['b'],
                    'shapley_val_pi': sh['values']['pi'],
                    'shapley_share_s': sh['shares']['s'],
                    'shapley_share_b': sh['shares']['b'],
                    'shapley_share_pi': sh['shares']['pi'],
                    'share_reliable': sh['shares_reliable'],
                    'share_floor': sh['share_floor'],
                    'delta_s_range_perms': (
                        max(v['s'] for v in out['permutations'].values())
                        - min(v['s'] for v in out['permutations'].values())
                    ),
                    'gate': gate,  # Fraction scale (same as mape_b_abs), not a percentage.
                    'passed': passed,
                }

                # Leg-3 synthesis: attribution bootstrap CI (absolute values; shares get no CI).
                if n_boot > 0 and identifiable and not out['recovery_failed']:
                    ci = bootstrap_decomposition(
                        p_base, y_base, slope, intercept, target_prev,
                        n_boot, np.random.default_rng([boot_seed, cell, 999]),
                        metric=ece,
                    )
                    for key in ['shap_s', 'shap_b', 'shap_pi', 'delta_total', 'I_sb']:
                        row[f'{key}_lo'] = ci[f'{key}_ci'][0]
                        row[f'{key}_hi'] = ci[f'{key}_ci'][1]
                else:
                    for key in ['shap_s', 'shap_b', 'shap_pi', 'delta_total', 'I_sb']:
                        row[f'{key}_lo'] = float('nan')
                        row[f'{key}_hi'] = float('nan')

                rows.append(row)
    return rows, gate, gate_b_abs


def run_multi_seed(n, n_seeds, n_boot):
    """Multi-seed violation-rate measurement (replaces the fabricated p95 narrative with data)."""
    all_rows = []
    for rep in range(n_seeds):
        seed = SEED + rep
        rng = np.random.default_rng(seed)
        p_base = rng.uniform(0.05, 0.95, n)
        y_base = rng.binomial(1, p_base).astype(float)
        rows, gate, gate_b = run_grid(p_base, y_base, n, n_boot, seed)
        for r in rows:
            r['seed'] = seed
        all_rows.extend(rows)
    return all_rows, gate, gate_b


def write_csv(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def plot_error_map(rows, path):
    worst = {tp: np.full((len(SLOPES), len(INTERCEPTS)), np.nan) for tp in TARGET_PREVS}
    marks = {tp: np.empty((len(SLOPES), len(INTERCEPTS)), dtype=object) for tp in TARGET_PREVS}
    for r in rows:
        i = SLOPES.index(r['slope'])
        j = INTERCEPTS.index(r['intercept'])
        tp = r['target_prev']
        worst[tp][i, j] = max(r['mape_s_pct'], r['mape_pi_design_pct'],
                              r['mape_b_abs'] * 100.0)
        if r['recovery_failed'] or not r['identifiable']:
            marks[tp][i, j] = "E"
        elif not r['passed']:
            marks[tp][i, j] = "F"
        else:
            marks[tp][i, j] = ""

    finite = [w[np.isfinite(w)] for w in worst.values()]
    vmax = np.percentile(np.concatenate(finite), 95)  # 95th percentile
    fig, axes = plt.subplots(1, len(TARGET_PREVS), figsize=(14, 4.6), sharey=True)
    for ax, tp in zip(axes, TARGET_PREVS):
        im = ax.imshow(worst[tp], origin="lower", cmap="RdYlGn_r",
                       vmin=0.0, vmax=vmax, aspect="auto")
        ax.set_xticks(range(len(INTERCEPTS)))
        ax.set_xticklabels([f"{b:g}" for b in INTERCEPTS])
        ax.set_yticks(range(len(SLOPES)))
        ax.set_yticklabels([f"{s:g}" for s in SLOPES])
        ax.set_xlabel("Intercept b")
        ax.set_title(f"target_prev={tp:g}")
        for i in range(len(SLOPES)):
            for j in range(len(INTERCEPTS)):
                txt = f"{worst[tp][i, j]:.2f}"
                mk = marks[tp][i, j]
                if mk:
                    txt += f"\n[{mk}]"
                ax.text(j, i, txt, ha="center", va="center", fontsize=8)
    axes[0].set_ylabel("Slope s")
    fig.colorbar(im, ax=axes, shrink=0.85, label="Worst recovery MAPE (%)")
    fig.suptitle(f"Three-component decomposition recovery error map "
                 f"(King-Zeng corrected, entangled/failed det<tau={IDENTIFIABILITY_TAU:g} marked E)")
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def run_entangle_demo():
    """Leg-3 synthesis demo: entangled branch is reachable and the recovery-failure path is unified (no exception leaks)."""
    print(f"\n{'='*60}\nEntanglement-region demo (leg-3 synthesis validation, preregistered protocol §8-3)\n{'='*60}")
    ok = True
    for i, (name, (p, y, s, b, tp)) in enumerate(entangle_demo_cases().items()):
        rng = np.random.default_rng([7, i])
        out = decompose_benefit(p, y, s, b, tp, rng=rng, metric=ece)
        det = out['fisher_det']
        ent = out['entangled']
        failed = out['recovery_failed']
        status = "OK" if (ent or det < IDENTIFIABILITY_TAU) else "UNEXPECTED"
        if not (ent or det < IDENTIFIABILITY_TAU):
            ok = False
        print(f"  {name:>16}: det={det:.3e} entangled={ent} "
              f"recovery_failed={failed} [{status}]")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=N_BASE,
                    help='Baseline sample size (default 20000; pass 500 to test the real calibration-set scale).')
    ap.add_argument('--boot', type=int, default=1000,
                    help='Attribution bootstrap repeats (default 1000; 0 disables CI columns).')
    ap.add_argument('--seeds', type=int, default=1,
                    help='Multi-seed repeats (default 1; >1 emits a violation-rate summary).')
    ap.add_argument('--output', type=str, default=None,
                    help='Output directory (default results/; tests should pass a tmp dir).')
    args = ap.parse_args()

    out_dir = Path(args.output) if args.output else PROJECT_ROOT / "results"
    csv_path = out_dir / f"decomposition_validation_n{args.n}.csv"
    png_path = out_dir / f"decomposition_error_map_n{args.n}.png"

    if args.seeds > 1:
        rows, gate, gate_b = run_multi_seed(args.n, args.seeds, args.boot)
    else:
        p_base, y_base = build_baseline(n=args.n)
        rows, gate, gate_b = run_grid(p_base, y_base, args.n, args.boot, SEED)

    n_rows = len(rows)
    n_ident = sum(r['identifiable'] for r in rows)
    n_entangled = n_rows - n_ident
    n_failed_rec = sum(r['recovery_failed'] for r in rows)
    n_passed = sum(r['passed'] for r in rows)
    n_share_unreliable = sum(not r['share_reliable'] for r in rows)

    mode = "preregistered" if args.n >= N_BASE else "informative"
    print(f"[{mode} mode] baseline n={args.n}  "
          f"gate: MAPE_s/pi<{gate*100:.1f}%  MAPE_b<{gate_b:.3f}  "
          f"boot={'off' if args.boot == 0 else args.boot}  seeds={args.seeds}")
    print(f"{'cell':>4} {'s':>4} {'b':>5} {'prev':>5} | {'det(FI)':>10} | "
          f"{'MAPE_s%':>8} {'MAPE_b':>8} {'MAPE_πd%':>8} | "
          f"{'shap_s':>8} {'shap_b':>8} {'shap_pi':>8} rel | pass")
    for r in rows:
        flag = "" if r['passed'] else ("[E]" if (not r['identifiable'] or r['recovery_failed']) else "[F]")
        rel = "Y" if r['share_reliable'] else "N"
        print(f"{r['cell']:>4} {r['slope']:>4g} {r['intercept']:>5g} "
              f"{r['target_prev']:>5g} | {r['det_fi']:>10.3e} | "
              f"{r['mape_s_pct']:>8.3f} {r['mape_b_abs']:>8.4f} "
              f"{r['mape_pi_design_pct']:>8.3f} | "
              f"{r['shapley_val_s']:>8.4f} {r['shapley_val_b']:>8.4f} "
              f"{r['shapley_val_pi']:>8.4f} {rel} | "
              f"{'PASS' if r['passed'] else 'FAIL'}{flag}")

    print(f"\nSummary: {n_passed}/{n_rows} PASS  identifiable cells={n_ident}  "
          f"entangled/recovery-failed cells={n_entangled} (recovery failed={n_failed_rec})")
    print(f"Shapley: uninterpretable-share cells={n_share_unreliable}/{n_rows}"
          f" (|delta_total|<3/sqrt(n) or sign-cancellation gives negative shares -- share semantics break down, rank by absolute value)")
    print("Note: MAPE_pi(design) is a design check (resampling constant readback), not an estimator-capability test.")

    if args.seeds > 1:
        fails = [r for r in rows if not r['passed']]
        print(f"Multi-seed violation-rate measurement: {len(fails)}/{n_rows} cells FAIL "
              f" ({args.seeds} seeds x 27 cells)")
        reps_csv = out_dir / f"decomposition_validation_n{args.n}_seeds{args.seeds}.csv"
        write_csv(rows, reps_csv)
        print(f"multi-seed CSV: {reps_csv}")
    else:
        write_csv(rows, csv_path)
        plot_error_map(rows, png_path)
        print(f"\nCSV: {csv_path}")
        print(f"plot:  {png_path}")

    # Entanglement demo (leg-3, runs by default)
    demo_ok = run_entangle_demo()

    # Exit codes
    if n_entangled == n_rows and n_rows > 0:
        print("\nExit code 3: all cells entangled/recovery-failed -- identifiability design-failure signal")
        sys.exit(EXIT_ALL_ENTANGLED)
    if not demo_ok:
        print("\nExit code 5: entanglement demo failed -- leg-3 branch unreachable, per protocol §8 the mechanism wording must be withdrawn")
        sys.exit(EXIT_ENTANGLE_DEMO_FAILED)
    if args.n >= N_BASE:
        sys.exit(EXIT_OK if n_passed == n_ident else EXIT_FAIL_PREREG)
    else:
        # Informative mode: FAIL is no longer silent; exit code 2 for CI assertions
        if n_passed < n_ident:
            print(f"\n[EXIT_INFO_MODE_FAIL] n={args.n} < {N_BASE}:preregistered gate not applied,"
                  f"but {n_ident - n_passed} cells FAIL reported as-is (dominated by real-scale statistical noise,"
                  f" see identifiability_gate docs for the honest semantics)")
        sys.exit(EXIT_OK if n_passed == n_ident else EXIT_FAIL_INFO)


if __name__ == '__main__':
    main()
