"""三成分分解的合成注入验证 v3：27格全因子 + Fisher可辨识性 + 样本量自适应门槛
（协议 docs/EXPERIMENT_PROTOCOL.md §8-2/§8-3）

v3变化（R轮对抗审查修复）：
- [R3] 结果治理：输出文件名含样本量（decomposition_validation_n{n}.csv /
  decomposition_error_map_n{n}.png）——n500 不再覆盖 n20000；--output 重定向
  （测试写入tmp，不再污染results/）；CSV自述（n/seed列）
- [R2] 诚实化：撤回"3σ容差/p95=19.6%"叙事。gate(n)=max(10%, 3×MAPE_REF×sqrt(N_REF/n))
  是启发式缩放（MAPE_REF为单种子单次实测），n=500实测违率≈22%（存档n500 CSV可查）；
  --seeds N（默认1）提供多种子重复的违率实测
- [R4] MAPE_π列更名mape_pi_design_pct并明示：prev_hat=重采样后标签频率是设计
  常量回读（门槛三分量之一永真），π独立恢复（BBSE/EM）为遗留项，见协议§13
- [R5] Shapley：CSV同时输出绝对值（shapley_val_*）与占比；share_reliable列标记
  |Δ_total|<3/√n的不可解读格；占比CI不设（分母可跨0），绝对值CI由--boot提供
- [R1/腿3] --boot B（默认1000）：27格归因量样本级bootstrap CI；纠缠区演示
  （entangle_demo_cases）默认执行并断言entangled分支可达
- [R6] 退出码：可辨识格FAIL→1（预注册n）/→2（信息模式n<20000，不再恒0）；
  全纠缠（设计失效信号）→3；纠缠演示失败→5；PASS→0
- [R10] CSV补chain_residual列（协议§8-1"交互残差显式报告"）；gate列存小数
  （与mape_b_abs同量纲），mape_*_pct为百分数——列名与语义一致

预注册设计（写死，偏离已登记协议§8-2修订注记）：
- 基线：n=20000，p~Uniform(0.05,0.95)，y~Bernoulli(p)，seed=42
- 网格：slope{0.5,1,2}×intercept{-1,0,1}×prev_target{0.15,0.3,0.6}，共27格
  （协议原文prevalence×{0.5,1,2}乘性网格不可行：×2→π=1.0正类耗尽、×1≈基线
  先验不触发重采样；偏离理由与日期见协议修订记录）
- 每格：注入→重采样→（重采样后）恢复+KZ校正→误差
- 可辨识性：det(FI)≥τ=1e-6；det<τ为纠缠区只记录
- 门槛（n=20000预注册判定）：MAPE_s<gate 且 MAPE_π<gate 且 |b̂−b|<gate
  （gate为小数；s/π侧按百分数同值比较）
- 退出码：见上[R6]

用法：
    python scripts/validate_decomposition.py                     # n=20000, boot=1000
    python scripts/validate_decomposition.py --n 500             # 真实校准集量级（信息模式）
    python scripts/validate_decomposition.py --boot 0            # 关闭bootstrap CI（快速）
    python scripts/validate_decomposition.py --seeds 8           # 多种子违率实测
    python scripts/validate_decomposition.py --output DIR        # 重定向输出（测试用）
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
    gate = identifiability_gate(n)          # 小数（0.10~0.23）
    gate_pct = gate * 100.0                 # MAPE_s/MAPE_π用百分数比较
    gate_b_abs = gate                       # MAPE_b用绝对值比较（n=20000时=0.1=协议原值）
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
                    'mape_pi_design_pct': mape_pi,  # R4：设计校验（常量回读），非估计量检验
                    'delta_total': out['delta_total'],
                    'delta_s_chain': out['chain']['delta_s'],
                    'delta_b_chain': out['chain']['delta_b'],
                    'delta_pi_chain': out['chain']['delta_pi'],
                    'chain_residual': out['chain']['residual'],  # R10：协议§8-1显式报告
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
                    'gate': gate,  # R10：小数量纲（与mape_b_abs同），非百分数
                    'passed': passed,
                }

                # 腿3合成兑现（R1）：归因量bootstrap CI（绝对值；占比不设CI）
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
    """多种子违率实测（R2修复：以数据代替虚假p95叙事）"""
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
    vmax = np.percentile(np.concatenate(finite), 95)  # 反例9：95分位
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
    """腿3合成演示（R1）：纠缠分支可达 + 恢复失败路径统一（不穿透异常）"""
    print(f"\n{'='*60}\n纠缠区演示（腿3合成验证，协议§8-3）\n{'='*60}")
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
                    help='基线样本量（默认20000；传500检验真实校准集量级）')
    ap.add_argument('--boot', type=int, default=1000,
                    help='归因量bootstrap重复数（默认1000；0=关闭CI列）')
    ap.add_argument('--seeds', type=int, default=1,
                    help='多种子重复数（默认1；>1时输出违率实测汇总）')
    ap.add_argument('--output', type=str, default=None,
                    help='输出目录（默认results/；测试应传入tmp目录）')
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

    mode = "预注册" if args.n >= N_BASE else "信息"
    print(f"[{mode}模式] 基线 n={args.n}  "
          f"门槛: MAPE_s/π<{gate*100:.1f}%  MAPE_b<{gate_b:.3f}  "
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

    print(f"\n汇总: {n_passed}/{n_rows} PASS  可辨识格={n_ident}  "
          f"纠缠/恢复失败格={n_entangled}（其中恢复失败={n_failed_rec}）")
    print(f"Shapley: shares不可解读格={n_share_unreliable}/{n_rows}"
          f"（|Δ_total|<3/√n 或互抵致负占比——占比语义失效，用绝对值排序）")
    print("注: MAPE_π(design)=设计校验（重采样常量回读），非估计量能力检验（R4）")

    if args.seeds > 1:
        fails = [r for r in rows if not r['passed']]
        print(f"多种子违率实测（R2）: {len(fails)}/{n_rows} 格FAIL "
              f"（{args.seeds}种子×27格）")
        reps_csv = out_dir / f"decomposition_validation_n{args.n}_seeds{args.seeds}.csv"
        write_csv(rows, reps_csv)
        print(f"多种子CSV: {reps_csv}")
    else:
        write_csv(rows, csv_path)
        plot_error_map(rows, png_path)
        print(f"\nCSV: {csv_path}")
        print(f"图:  {png_path}")

    # 纠缠演示（腿3，默认执行）
    demo_ok = run_entangle_demo()

    # 退出码（R6）
    if n_entangled == n_rows and n_rows > 0:
        print("\n退出码3：全部格子纠缠/恢复失败——可辨识性设计失效信号")
        sys.exit(EXIT_ALL_ENTANGLED)
    if not demo_ok:
        print("\n退出码5：纠缠演示失败——腿3分支不可达，按协议§8须撤回机制措辞")
        sys.exit(EXIT_ENTANGLE_DEMO_FAILED)
    if args.n >= N_BASE:
        sys.exit(EXIT_OK if n_passed == n_ident else EXIT_FAIL_PREREG)
    else:
        # 信息模式（R6）：FAIL不再静默，退出码2供CI断言
        if n_passed < n_ident:
            print(f"\n[EXIT_INFO_MODE_FAIL] n={args.n} < {N_BASE}：不执行预注册门槛，"
                  f"但{n_ident - n_passed}格FAIL如实报告（真实量级统计噪声主导，"
                  f"见identifiability_gate文档的诚实语义）")
        sys.exit(EXIT_OK if n_passed == n_ident else EXIT_FAIL_INFO)


if __name__ == '__main__':
    main()
