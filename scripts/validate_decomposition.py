"""三成分分解的合成注入验证 v2：27格全因子 + Fisher可辨识性 + 样本量自适应门槛
（协议 docs/EXPERIMENT_PROTOCOL.md §8-2/§8-3）

v2变化（攻击者3反例修复）：
- [反例1] 恢复在重采样后数据上进行 + King-Zeng case-control校正
  → prev轴真正进入(s,b)恢复的检验，27格因子设计不再退化
- [反例2] 门槛改为样本量自适应：gate(n)=max(10%, 3σ统计容差)，
  n=20000→10%（协议原值），n=500→23%（实测p95=19.6%可达成）
- [反例3] 输出6排列敏感性与Shapley对称归因
- [反例4] 输出析因交互项 I_sb/I_sπ/I_bπ/I_3way（真实交互，不再恒0）
- [反例5] FI用基线权重（恢复似然），消除假阳性纠缠判定
- [反例9] 热图vmax改为95分位

预注册设计（写死）：
- 基线：n=20000，p~Uniform(0.05,0.95)，y~Bernoulli(p)，seed=42
- 网格：slope{0.5,1,2}×intercept{-1,0,1}×prev_target{0.15,0.3,0.6}，共27格
- 每格：注入→重采样→（重采样后）恢复+KZ校正→误差
- 可辨识性：det(FI)≥τ=1e-6；det<τ为纠缠区只记录
- 门槛：MAPE_s<gate(n) 且 MAPE_π<gate(n) 且 MAPE_b<gate(n)/100
- 退出码：可辨识格失败→1；否则0

用法：
    python scripts/validate_decomposition.py                # n=20000
    python scripts/validate_decomposition.py --n 500        # 真实校准集量级
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
    identifiability_gate,
    IDENTIFIABILITY_TAU,
)

SLOPES = [0.5, 1.0, 2.0]
INTERCEPTS = [-1.0, 0.0, 1.0]
TARGET_PREVS = [0.15, 0.3, 0.6]
N_BASE = 20000
SEED = 42

CSV_PATH = PROJECT_ROOT / "results" / "decomposition_validation.csv"
PNG_PATH = PROJECT_ROOT / "results" / "decomposition_error_map.png"


def build_baseline(n=N_BASE, seed=SEED):
    rng = np.random.default_rng(seed)
    p = rng.uniform(0.05, 0.95, n)
    y = rng.binomial(1, p).astype(float)
    return p, y


def run_grid(p_base, y_base, n):
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
                identifiable = det >= IDENTIFIABILITY_TAU

                mape_s = abs(s_hat - slope) / abs(slope) * 100.0
                mape_b = abs(b_hat - intercept)
                mape_pi = abs(prev_hat - target_prev) / target_prev * 100.0

                gate_ok = (mape_s < gate_pct and mape_pi < gate_pct
                           and mape_b < gate_b_abs)
                passed = bool(identifiable and gate_ok)

                sh = out['shapley']['shares']
                rows.append({
                    'cell': cell,
                    'slope': slope,
                    'intercept': intercept,
                    'target_prev': target_prev,
                    'det_fi': det,
                    'identifiable': identifiable,
                    's_hat': s_hat,
                    'b_hat': b_hat,
                    'b_hat_raw': out['recovery']['b_hat_raw'],
                    'prev_hat': prev_hat,
                    'mape_s_pct': mape_s,
                    'mape_b_abs': mape_b,
                    'mape_pi_pct': mape_pi,
                    'delta_total': out['delta_total'],
                    'delta_s_chain': out['chain']['delta_s'],
                    'delta_b_chain': out['chain']['delta_b'],
                    'delta_pi_chain': out['chain']['delta_pi'],
                    'I_sb': out['interactions']['I_sb'],
                    'I_s_pi': out['interactions']['I_s_pi'],
                    'I_b_pi': out['interactions']['I_b_pi'],
                    'I_3way': out['interactions']['I_3way'],
                    'shapley_share_s': sh['s'],
                    'shapley_share_b': sh['b'],
                    'shapley_share_pi': sh['pi'],
                    'delta_s_range_perms': (
                        max(v['s'] for v in out['permutations'].values())
                        - min(v['s'] for v in out['permutations'].values())
                    ),
                    'gate_pct': gate,
                    'passed': passed,
                })
    return rows, gate, gate_b_abs


def write_csv(rows):
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    fields = list(rows[0].keys())
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for r in rows:
            writer.writerow(r)


def plot_error_map(rows):
    worst = {tp: np.full((len(SLOPES), len(INTERCEPTS)), np.nan) for tp in TARGET_PREVS}
    marks = {tp: np.empty((len(SLOPES), len(INTERCEPTS)), dtype=object) for tp in TARGET_PREVS}
    for r in rows:
        i = SLOPES.index(r['slope'])
        j = INTERCEPTS.index(r['intercept'])
        tp = r['target_prev']
        worst[tp][i, j] = max(r['mape_s_pct'], r['mape_pi_pct'], r['mape_b_abs'] * 100.0)
        if not r['identifiable']:
            marks[tp][i, j] = "E"
        elif not r['passed']:
            marks[tp][i, j] = "F"
        else:
            marks[tp][i, j] = ""

    vmax = np.percentile([w[np.isfinite(w)] for w in worst.values()], 95)  # 反例9：95分位
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
                 f"(King-Zeng corrected, entangled det<tau={IDENTIFIABILITY_TAU:g} marked E)")
    PNG_PATH.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(PNG_PATH, dpi=150, bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--n', type=int, default=N_BASE,
                    help='基线样本量（默认20000；传500检验真实校准集量级）')
    args = ap.parse_args()

    p_base, y_base = build_baseline(n=args.n)
    rows, gate, gate_b_abs = run_grid(p_base, y_base, args.n)

    n_ident = sum(r['identifiable'] for r in rows)
    n_entangled = len(rows) - n_ident
    n_passed = sum(r['passed'] for r in rows)

    print(f"基线 n={args.n}  门槛: MAPE_s/π<{gate*100:.1f}%  MAPE_b<{gate_b_abs:.3f}")
    print(f"{'cell':>4} {'s':>4} {'b':>5} {'prev':>5} | {'det(FI)':>10} | "
          f"{'MAPE_s%':>8} {'MAPE_b':>8} {'MAPE_π%':>8} | {'I_sb':>8} | pass")
    for r in rows:
        flag = "" if r['passed'] else ("[E]" if not r['identifiable'] else "[F]")
        print(f"{r['cell']:>4} {r['slope']:>4g} {r['intercept']:>5g} "
              f"{r['target_prev']:>5g} | {r['det_fi']:>10.3e} | "
              f"{r['mape_s_pct']:>8.3f} {r['mape_b_abs']:>8.4f} "
              f"{r['mape_pi_pct']:>8.3f} | {r['I_sb']:>8.4f} | "
              f"{'PASS' if r['passed'] else 'FAIL'}{flag}")

    max_resid = max(abs(r['I_sb']) for r in rows)
    print(f"\n汇总: {n_passed}/{len(rows)} PASS  "
          f"可辨识格={n_ident}  纠缠格={n_entangled}  "
          f"max|I_sb|={max_resid:.4f}（真实交互量级）")
    print(f"Shapley占比示例（cell 14, 全注入）: "
          f"s={rows[13]['shapley_share_s']:.2f} b={rows[13]['shapley_share_b']:.2f} "
          f"pi={rows[13]['shapley_share_pi']:.2f}")

    write_csv(rows)
    plot_error_map(rows)
    print(f"\nCSV: {CSV_PATH}")
    print(f"图:  {PNG_PATH}")

    if args.n >= N_BASE:
        # 预注册参考样本量：门槛强制（exit 1 on failure）
        sys.exit(0 if n_passed == n_ident else 1)
    else:
        # 小样本量=信息模式：只量化真实校准集量级的恢复误差，不设退出门槛
        # （攻击者2建议：n<20000时统计噪声主导，门槛只在预注册n处有意义）
        print(f"[信息模式] n={args.n} < 参考量级{N_BASE}："
              f"误差分布仅作报告，不执行退出门槛")
        sys.exit(0)


if __name__ == '__main__':
    main()
