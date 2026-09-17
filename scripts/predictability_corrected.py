"""可预测性分析（修正口径）：标签无关特征能否预测 ΔECE_OOD？

背景
----
论文原称 "T yields $R^2=-0.13$ ... no label-free feature, including $T$,
predicts ΔECE_OOD above $R^2=0.5$"。该组数字是**跨标签编码错配**产物：
y 用 OLD 编码的 ΔECE_OOD，T 却取自 results/temperature_distribution_analysis.csv
（NEW 编码拟合）。两种编码的 T 相关仅 +0.15，近似独立，回归因此退化为噪声。

本脚本在**同一编码**下重算，并同时给出三种折单元的 LOO R² 与 bootstrap CI。

口径
----
y      = ΔECE_OOD = ECE_raw − ECE_TS（旧编码，论文主终点）
         results/robustness_validation_5seeds.csv  method=ts  ood_deltaECE
T      = 源侧拟合温度（旧编码）
         results/ablation_ts_components.OLD_ENCODING.csv  stage=stage1_ts  T_global
wass   = 源/目标 logit 分布的 Wasserstein-1 距离（不依赖标签，编码无关）
ent    = 类间熵差（不依赖标签，编码无关）
         二者取自 results/strengthening_battle_corrected.json

自洽性互校（脚本内强制）
------------------------
对每个 cell 断言  smooth_ece(stage=raw) − smooth_ece(stage1_ts)
                == ood_deltaECE，容差 1e-9。二者若不同源，说明编码再次错位。

输出
----
results/predictability_corrected.csv
"""
from __future__ import annotations
import csv
import json
import sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent

MAIN_CSV = ROOT / "results/robustness_validation_5seeds.csv"
ABL_CSV = ROOT / "results/ablation_ts_components.OLD_ENCODING.csv"
CORR_JSON = ROOT / "results/strengthening_battle_corrected.json"
OUT_CSV = ROOT / "results/predictability_corrected.csv"

ALPHA = 1.0          # 岭回归正则（与 step2_predictability.py 一致）
N_BOOT = 4000
BOOT_SEED = 42
TOL = 1e-9


def read_csv(p: Path):
    if not p.exists():
        raise SystemExit(f"[致命] 缺少输入 {p} —— 不静默回退。")
    with open(p, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def build():
    """返回 keys, y, 特征字典, pair 数组, arch 数组。"""
    main = {}
    for r in read_csv(MAIN_CSV):
        if r["method"] != "ts":
            continue
        main[(r["pair"], r["arch"], r["seed"])] = float(r["ood_deltaECE"])

    raw_s, ts_s = {}, {}
    for r in read_csv(ABL_CSV):
        if "mamba" in r["arch"]:
            continue
        k = (f'{r["source"]}_{r["target"]}', r["arch"], r["seed"])
        if r["stage"] == "raw":
            raw_s[k] = float(r["smooth_ece"])
        elif r["stage"] == "stage1_ts" and r["T_global"]:
            ts_s[k] = (float(r["T_global"]), float(r["smooth_ece"]))

    free = {}
    for r in json.loads(CORR_JSON.read_text(encoding="utf-8")):
        free[(f'{r["source"]}_{r["target"]}', r["arch"], str(r["seed"]))] = \
            (r["wasserstein"], r["entropy_diff"])

    keys = sorted(k for k in main if k in raw_s and k in ts_s and k in free)
    if not keys:
        raise SystemExit("[致命] 三个数据源无交集 cell —— 口径已漂移。")

    # 自洽性互校：消融表的 raw−ts 必须等于主表的 ood_deltaECE
    bad = []
    for k in keys:
        d = raw_s[k] - ts_s[k][1]
        if abs(d - main[k]) > TOL:
            bad.append((k, d, main[k]))
    if bad:
        raise SystemExit(
            f"[致命] 消融表与主表口径不一致，{len(bad)} 个 cell 超差。"
            f"首个：{bad[0][0]} 消融Δ={bad[0][1]:.10f} 主表Δ={bad[0][2]:.10f}")
    print(f"[自洽] {len(keys)} 个 cell 的 (raw−ts) 与 ood_deltaECE 逐格一致（tol {TOL:g}）")

    y = np.array([main[k] for k in keys])
    T = np.array([ts_s[k][0] for k in keys])
    W = np.array([free[k][0] for k in keys])
    E = np.array([free[k][1] for k in keys])
    pair = np.array([k[0] for k in keys])
    arch = np.array([k[1] for k in keys])
    return keys, y, T, W, E, pair, arch


def loo_r2(y, X, groups, alpha=ALPHA):
    """留一组外的岭回归 R²。X: (n, d)。"""
    pred = np.full(len(y), np.nan)
    for g in sorted(set(groups)):
        te, tr = groups == g, groups != g
        if tr.sum() < 2 or te.sum() == 0:
            continue
        Xa = np.hstack([X[tr], np.ones((tr.sum(), 1))])
        Xb = np.hstack([X[te], np.ones((te.sum(), 1))])
        A = Xa.T @ Xa + alpha * np.eye(X.shape[1] + 1)
        A[-1, -1] -= alpha
        try:
            pred[te] = Xb @ np.linalg.solve(A, Xa.T @ y[tr])
        except np.linalg.LinAlgError:
            continue
    ok = ~np.isnan(pred)
    if ok.sum() < 3:
        return np.nan
    return 1 - np.sum((y[ok] - pred[ok]) ** 2) / np.sum((y[ok] - y[ok].mean()) ** 2)


def boot_ci(y, X, ap, n_boot=N_BOOT, seed=BOOT_SEED):
    """按 (arch,pair) 聚类重采样的 LOO R² 95% CI（两种折单元）。"""
    rng = np.random.RandomState(seed)
    groups = sorted(set(ap))
    bc, ba = [], []
    for _ in range(n_boot):
        bg = [groups[rng.randint(0, len(groups))] for _ in groups]
        idx = np.concatenate([np.where(ap == g)[0] for g in bg])
        yy, XX, pp = y[idx], X[idx], ap[idx]
        c = loo_r2(yy, XX, np.arange(len(yy)))
        a = loo_r2(yy, XX, pp)
        if np.isfinite(c):
            bc.append(c)
        if np.isfinite(a):
            ba.append(a)
    out = {}
    for nm, b in (("cell", bc), ("arch_pair", ba)):
        b = np.array(b)
        out[nm] = (float(np.percentile(b, 2.5)), float(np.percentile(b, 97.5))) if len(b) else (np.nan, np.nan)
    return out


def main():
    keys, y, T, W, E, pair, arch = build()
    ap = np.array([f"{a}|{p}" for a, p in zip(arch, pair)])
    cell = np.arange(len(y))

    print(f"\nn = {len(y)}   y mean = {y.mean():+.6f}   T median = {np.median(T):.4f} "
          f"range = [{T.min():.4f}, {T.max():.4f}]")

    feats = {
        "T": T.reshape(-1, 1),
        "wasserstein": W.reshape(-1, 1),
        "entropy_diff": E.reshape(-1, 1),
        "T+wass+ent": np.c_[T, W, E],
    }

    rows = []
    print("\n" + "=" * 92)
    print(f"{'特征集':<14} {'corr':>9} {'R²(corr²)':>10} {'LOO cell':>10} {'LOO pair':>10} "
          f"{'LOO (a,p)':>10} {'CI(a,p) lo':>11} {'CI(a,p) hi':>11}")
    print("=" * 92)
    for nm, X in feats.items():
        c = float(np.corrcoef(y, X[:, 0])[0, 1]) if X.shape[1] == 1 else np.nan
        r_cell = loo_r2(y, X, cell)
        r_pair = loo_r2(y, X, pair)
        r_ap = loo_r2(y, X, ap)
        ci = boot_ci(y, X, ap)
        print(f"{nm:<14} {c:>+9.4f} {c**2:>10.4f} {r_cell:>+10.4f} {r_pair:>+10.4f} "
              f"{r_ap:>+10.4f} {ci['arch_pair'][0]:>+11.4f} {ci['arch_pair'][1]:>+11.4f}")
        rows.append(dict(feature_set=nm, corr=c, r2_corr2=c ** 2, loo_cell=r_cell,
                         loo_pair=r_pair, loo_arch_pair=r_ap,
                         ci_arch_pair_lo=ci["arch_pair"][0], ci_arch_pair_hi=ci["arch_pair"][1],
                         ci_cell_lo=ci["cell"][0], ci_cell_hi=ci["cell"][1]))

    # 符号预测
    acc = float((np.sign(y) == np.sign(T - 1.0)).mean())
    base = float((y > 0).mean())
    print("\n" + "=" * 92)
    print("符号预测（T 为源侧拟合量，不需目标域标签）")
    print("=" * 92)
    print(f"  sign(ΔECE_OOD) == sign(T−1) : {int(acc*len(y))}/{len(y)} = {acc:.1%}")
    print(f"  常数恒正基线               : {int((y>0).sum())}/{len(y)} = {base:.1%}")
    print(f"  T>=1 的 cell: {int((T>=1).sum())} 个, 其中 ΔECE>0: {int(((T>=1)&(y>0)).sum())}")
    print(f"  T< 1 的 cell: {int((T<1).sum())} 个, 其中 ΔECE<0: {int(((T<1)&(y<0)).sum())}")

    verdict = "失败分支触发" if rows[0]["ci_arch_pair_hi"] < 0.5 else "失败分支【不】触发"
    print(f"\n预注册判据（(arch,pair) 折，CI 上界 < 0.5 → 失败分支）：{verdict}")
    print(f"  T 的 CI 上界 = {rows[0]['ci_arch_pair_hi']:+.4f}；"
          f"cell 折 CI 上界 = {rows[0]['ci_cell_hi']:+.4f}"
          f"（{'>= 0.5，会翻转判定' if rows[0]['ci_cell_hi'] >= 0.5 else '< 0.5'}）")

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["# ECG-Lab 可预测性分析（修正口径，单一编码）"])
        w.writerow(["# y", "ood_deltaECE (OLD encoding, robustness_validation_5seeds.csv method=ts)"])
        w.writerow(["# T", "T_global (OLD encoding, ablation_ts_components.OLD_ENCODING.csv stage1_ts)"])
        w.writerow(["# wass/ent", "strengthening_battle_corrected.json（标签无关）"])
        w.writerow(["# n", len(y)])
        w.writerow(["# ridge alpha", ALPHA, "# bootstrap B", N_BOOT, "# cluster", "(arch,pair)"])
        w.writerow(["# sign_accuracy", f"{acc:.6f}", "# const_positive_baseline", f"{base:.6f}"])
        w.writerow(["# verdict", verdict])
        w.writerow([])
        w.writerow(["feature_set", "corr", "r2_corr2", "loo_cell", "loo_pair",
                    "loo_arch_pair", "ci_arch_pair_lo", "ci_arch_pair_hi",
                    "ci_cell_lo", "ci_cell_hi"])
        for r in rows:
            w.writerow([r["feature_set"], f"{r['corr']:.6f}", f"{r['r2_corr2']:.6f}",
                        f"{r['loo_cell']:.6f}", f"{r['loo_pair']:.6f}",
                        f"{r['loo_arch_pair']:.6f}", f"{r['ci_arch_pair_lo']:.6f}",
                        f"{r['ci_arch_pair_hi']:.6f}", f"{r['ci_cell_lo']:.6f}",
                        f"{r['ci_cell_hi']:.6f}"])
    print(f"\n结果已保存到 {OUT_CSV}")


if __name__ == "__main__":
    main()
