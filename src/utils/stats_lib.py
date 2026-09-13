"""统计分析模块: DeLong检验 / 阈值搜索 / 精确McNemar / 多种子聚合

实现对抗审查后确定的统计协议:
    1. DeLong配对检验+AUROC 95%CI（同批受试者的模型比较标准方法）
    2. 阈值搜索: 仅在验证集上做，测试集只套用（杜绝泄漏）
       工作点: Youden J 最优点 + sens>=95%(筛查约束) + spec>=95%(确认约束)
    3. 精确McNemar: 比较两配置的阳性检出差异（b+c<25时二项精确版）
    4. 多种子聚合: mean±std(ddof=1) + 每种子原始值（n小时禁止只看均值）
"""

import sys
from pathlib import Path

import numpy as np
from scipy import stats as sps

ROOT = Path(__file__).resolve().parents[1]


# ---------------- DeLong: AUROC的CI与配对比较 ----------------

def _delong_components(y: np.ndarray, p: np.ndarray):
    """DeLong的V10/V01结构成分（cases与controls的位置分量）"""
    pos = p[y == 1]
    neg = p[y == 0]
    m, n = len(pos), len(neg)
    # V10[i]: 第i个case比controls大的程度（含0.5并列）
    higher = (pos[:, None] > neg[None, :]).astype(float)
    ties = (pos[:, None] == neg[None, :]).astype(float)
    v10 = (higher + 0.5 * ties).mean(axis=1)
    v01 = (higher + 0.5 * ties).mean(axis=0)
    return v10, v01, m, n


def delong_paired(y, p1, p2) -> dict:
    """同批样本上两个模型AUROC的配对DeLong检验

    返回: 每个模型的AUROC+SE+95%CI，差异+95%CI+z检验p值
    """
    v10_1, v01_1, m, n = _delong_components(y, p1)
    v10_2, v01_2, _, _ = _delong_components(y, p2)
    a1, a2 = v10_1.mean(), v10_2.mean()

    # DeLong 1988标准公式: Cov(AUC) = S10/m + S01/n
    # (S10=case成分协方差, S01=control成分协方差; 旧版误用合并方差/(m+n-1),
    #  单模型方差低估~4x, 使s11+s22-2*s12变负被钳位, p值错误地下溢为0)
    def _var(x: np.ndarray) -> float:
        return float(np.var(x, ddof=1)) if len(x) > 1 else 0.0

    s11 = _var(v10_1) / m + _var(v01_1) / n
    s22 = _var(v10_2) / m + _var(v01_2) / n
    # 配对协方差: 成分间相关性
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


# ---------------- 阈值搜索（仅验证集） ----------------

def search_thresholds(y_val, p_val) -> dict:
    """在验证集上搜索多个临床工作点（测试集只套用）"""
    grids = np.unique(np.concatenate([p_val, [0.5]]))

    best_j, th_j = -1, 0.5
    best_s95, th_s95 = -1, None     # sens>=95% 约束下 spec 最大化
    best_p95, th_p95 = -1, None     # spec>=95% 约束下 sens 最大化
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


# ---------------- 精确McNemar ----------------

def mcnemar_exact(y, pred1, pred2) -> dict:
    """精确McNemar（二项分布）: 同批受试者两模型阳性判定差异

    注意: 本实现仅在阳性病例(y==1)上统计b/c，衡量的是"病例检出不一致性"，
    不是教科书定义的全样本McNemar——论文中并列报告两者（全样本版见
    mcnemar_standard），并明确说明口径差异。
    """
    b = int(((pred1 == 1) & (pred2 == 0) & (y == 1)).sum())
    c = int(((pred1 == 0) & (pred2 == 1) & (y == 1)).sum())
    n = b + c
    if n == 0:
        return {"b": 0, "c": 0, "p_value": 1.0}
    pval = min(1.0, 2 * sps.binom.cdf(min(b, c), n, 0.5))
    # 保留科学计数法: round(...,4)会把5e-13舍成0.0, 论文中会误读为p=0
    return {"b": b, "c": c, "p_value": float(f"{pval:.2e}")}


def mcnemar_standard(y, pred1, pred2) -> dict:
    """标准McNemar（全样本，教科书定义）: 两分类器判定的方向不一致检验

    b = 模型1判阳/模型2判阴的全部样本数, c = 反之（不限真实标签y）。
    显著的p值意味着两分类器的判定边界系统性不同。
    y参数仅为接口一致性保留（不参与统计）。
    """
    b = int(((pred1 == 1) & (pred2 == 0)).sum())
    c = int(((pred1 == 0) & (pred2 == 1)).sum())
    n = b + c
    if n == 0:
        return {"b": 0, "c": 0, "p_value": 1.0}
    pval = min(1.0, 2 * sps.binom.cdf(min(b, c), n, 0.5))
    return {"b": b, "c": c, "p_value": float(f"{pval:.2e}")}


# ---------------- 多种子聚合 ----------------

def aggregate_seeds(values: list[float]) -> dict:
    """mean±std(ddof=1) + 中位数/IQR + 全部原始值（双峰警报依赖原始值）"""
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
    # 双峰启发式检查: 极差 > 3*std 时提示分布可能双峰，mean会误导
    if len(v) > 2 and out["std"] and (out["max"] - out["min"]) > 3 * out["std"]:
        out["bimodal_warning"] = True
    return out


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    # 自检: 已知AUROC的合成数据
    rng = np.random.default_rng(0)
    y = np.concatenate([np.ones(400), np.zeros(600)])
    p_good = np.concatenate([rng.beta(5, 2, 400), rng.beta(2, 5, 600)])
    p_weak = np.concatenate([rng.beta(3, 2, 400), rng.beta(2, 3, 600)])
    r = delong_paired(y, p_good, p_weak)
    assert r["auroc1"] > r["auroc2"], "DeLong方向错误"
    print("[自检] DeLong配对检验:", {k: r[k] for k in ("auroc1", "auroc2", "p_value")})

    # 对抗自检: DeLong单模型SE vs Bootstrap SE（旧公式低估~2x会在此暴露）
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
    print(f"[自检] DeLong SE={se_delong:.4f} vs Bootstrap SE={se_boot:.4f}")
    assert abs(se_delong - se_boot) / se_boot < 0.25, \
        f"DeLong SE({se_delong:.4f})与Bootstrap SE({se_boot:.4f})偏差过大"

    th = search_thresholds(y, p_good)
    print("[自检] 阈值搜索:", th)
    m = mcnemar_exact(y, (p_good > 0.5).astype(int), (p_weak > 0.5).astype(int))
    print("[自检] 精确McNemar:", m)
    print("[自检] 全部通过")
