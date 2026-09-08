"""三成分分解估计器 v3（对抗审查R轮修复版）

数学定义（二分类，概率p，二值标签y）：
- 注入：p' = sigmoid(s·logit(p) + b)；prevalence注入=按目标先验重采样
- 恢复：在**重采样后**数据上恢复，并做King-Zeng case-control校正：
    重采样后拟合 logit(y) = a·x' + c（x'=logit(p')），
    case-control偏移：重采样使 b̂_raw 带上 −(logit(π_resampled) − logit(π_injected))/a，
    校正：b̂ = b̂_raw + (logit(π_resampled) − logit(π_injected))/a   [实现为准]
  其中 π_injected=注入后（重采样前）数据的正类频率，π_resampled=重采样后正类频率。
  注意：prev_hat=重采样后标签频率是**设计常量回读**（重采样精确控制正类数），
  MAPE_π 是设计校验（design check），不是估计量能力检验。π 的独立恢复
  需 BBSE/EM 类无标签估计器，本模块未实现（协议§8遗留项，见EXPERIMENT_PROTOCOL）。

v3变化（R轮对抗审查修复）：
- [R8] FI在**恢复实际所处设计**（重采样后子集）上计算；此前用重采样前全量
  （错位~1.1×，因det余量9400×未造成布尔判定差异，但语义不实）
- [R8] 恢复退化（logistic斜率≈0）不再raise穿透：decompose_benefit捕获并置
  recovery_failed=True、entangled=True——统一"纠缠区只记录"与"恢复崩溃"两条路径
- [R5] Shapley shares附可靠性标志：|Δ_total| < 3/√n（10-bin ECE噪声底3σ启发式）
  时 shares 不可作占比解读；绝对Shapley值（values）始终可报。负占比是效应互抵的
  代数结果（效率公理 Σ=Δ_total 的推论），非bug，但占比语义在互抵时失效
- [R1d] 删除死代码 _ece_chain
- 新增 bootstrap_decomposition：归因量的样本级bootstrap CI（协议§8-3腿3，
  合成环境可兑现部分：重采样→8子集ECE→链式/排列/Shapley/交互，B次percentile）
- 新增 entangle_demo_cases：构造 det<τ 病态基线，验证纠缠分支与恢复失败路径

入口校验（v2修复反例6，保持）：labels必须∈{0,1}，probs必须1维——多分类top-label
场景需调用方先做二值化并在结果中注明语义（置信度-正确性映射，含基线失准污染）。
"""

import warnings
import math
import itertools
from typing import Dict, Optional

import numpy as np
from scipy.special import expit
from sklearn.linear_model import LogisticRegression

IDENTIFIABILITY_TAU = 1e-6  # 预注册阈值（协议§8）
N_REF = 20000               # 参考样本量（门槛标定）
MAPE_REF = 0.0123           # n=N_REF时单种子实测MAPE_s参考值（建造者报告1.23%）
GATE_BASE = 0.10            # 协议原门槛
GATE_FLOOR = 0.10           # 门槛下限（不低于原预注册值）


def _validate_binary(probs: np.ndarray, labels: np.ndarray):
    """入口校验（反例6）：labels∈{0,1}，probs一维"""
    probs = np.asarray(probs, dtype=float)
    labels = np.asarray(labels)
    if probs.ndim != 1:
        raise ValueError(f"probs必须1维（二分类），得到shape={probs.shape}。"
                         f"多分类top-label场景请先二值化（max_prob + correct_mask）"
                         f"并注明语义。")
    if labels.size and not np.isin(labels, [0, 1]).all():
        raise ValueError(f"labels必须∈{{0,1}}，实际值域"
                         f"[{labels.min()},{labels.max()}]——多分类类索引会静默产生垃圾结果")
    return probs, labels.astype(float)


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-7, 1 - 1e-7)
    return np.log(p / (1 - p))


def inject_transform(probs: np.ndarray, slope: float = 1.0,
                     intercept: float = 0.0) -> np.ndarray:
    """logit空间注入变换：p' = sigmoid(s·logit(p)+b)"""
    probs, _ = _validate_binary(probs, np.zeros(0, dtype=int))
    return expit(slope * _logit(probs) + intercept)


def resample_prevalence(probs: np.ndarray, labels: np.ndarray,
                        target_prev: float, rng: np.random.Generator) -> np.ndarray:
    """按target_prev重采样索引（有放回，保持(p,y)配对）

    边界（反例8）：target_prev clip到[0.01,0.99]并warn；正类不足时复制并warn。
    """
    probs, labels = _validate_binary(probs, labels)
    if not (0 < target_prev < 1):
        warnings.warn(f"target_prev={target_prev}越界，clip到[0.01,0.99]")
        target_prev = float(np.clip(target_prev, 0.01, 0.99))
    n = len(labels)
    pos_idx = np.where(labels == 1)[0]
    neg_idx = np.where(labels == 0)[0]
    if len(pos_idx) == 0:
        raise ValueError("无正类样本，无法重采样")
    n_pos = max(int(round(target_prev * n)), 1)
    if n_pos > 5 * len(pos_idx):
        warnings.warn(f"正类样本({len(pos_idx)})将被复制{n_pos/len(pos_idx):.0f}倍，"
                      f"重采样样本不独立，ECE的不确定性被低估")
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
    """在（重采样后）数据上恢复(s,b)，带King-Zeng case-control校正

    数学：注入p'=σ(s·x+b)，y~Bern(σ(x))（基线校准）。恢复回归logit(y)=a·x'+c。
    反演：ŝ=1/a, b̂_raw=−c/a。
    case-control偏移（建造者实测验证）：重采样使b̂_raw带上
        −(logit(π_resampled) − logit(π_injected))/a，
    校正：b̂ = b̂_raw + (logit(π_resampled) − logit(π_injected))/a   [实现为准]。
    恢复退化（斜率≈0，数据无信息）时raise ValueError——调用方决定处理方式
    （decompose_benefit捕获并标记recovery_failed，见R8修复）。
    """
    probs_injected, labels = _validate_binary(probs_injected, labels)
    x_prime = _logit(probs_injected).reshape(-1, 1)
    if float(np.var(x_prime)) < 1e-12:
        # R8补强：x'常数设计（注入概率被钳位/无方差）下logistic沿参数流形退化，
        # 斜率可收敛到任意小值而非精确0——|a|判据不足，方差判据才是本质
        raise ValueError("x'=logit(p')方差≈0（注入概率钳位/常数），"
                         "恢复退化（数据无信息）")
    lr = LogisticRegression(C=1e4, solver='lbfgs', max_iter=5000)
    lr.fit(x_prime, labels.astype(int))
    a, c = float(lr.coef_[0, 0]), float(lr.intercept_[0])
    if abs(a) < 1e-12:
        raise ValueError("logistic回归斜率≈0，恢复退化（数据无信息）")
    s_hat = 1.0 / a
    b_hat_raw = -c / a

    b_hat = b_hat_raw
    if pi_reference is not None and pi_resampled is not None:
        # King-Zeng case-control校正（实证验证：b̂=b̂_raw+L/a，真值0.5恢复为0.494）
        L = (np.log(pi_resampled / (1 - pi_resampled))
             - np.log(pi_reference / (1 - pi_reference)))
        b_hat = b_hat_raw + L / a

    return {'s_hat': s_hat, 'b_hat': b_hat, 'b_hat_raw': b_hat_raw}


def fisher_information_det(probs_injected: np.ndarray,
                           probs_baseline: np.ndarray) -> float:
    """恢复似然的Fisher信息行列式（v2修复反例5权重错配）

    恢复问题：y|x' ~ Bern(σ((x'−b)/s))，x'=logit(p_injected)，x_base=logit(p_baseline)。
    设计矩阵[1, x']，权重 w_i = σ(x_base_i)(1−σ(x_base_i))（基线Bernoulli方差——
    注入是协变量的确定性重参数化，y条件分布不变，故该权重正是真值处的精确
    Fisher权重）。det独立于b、随x'设计缩放 ∝ s²（2×2信息矩阵单维缩放律，实测验证）。
    v3（R8）：调用方应在恢复实际所处设计（重采样后子集）上调用本函数。
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
    """MAPE门槛随样本量缩放（v2修复反例2：n=500时57%失败→统计容差）

    gate(n) = max(GATE_FLOOR, 3 × MAPE_REF × sqrt(N_REF/n))

    诚实语义（R2修复）：MAPE_REF 是**单种子单次实测**的点观测（非标准差），
    "3×"是启发式放大因子，**不是3σ统计容差**。实测标定（存档
    results/decomposition_validation_n500_*.csv）：n=500 时 mape_s p50=13.2%、
    p95=33.2%、max=42.1%，违率 6/27≈22%——gate(500)=23.3% 实际位于 mape_s
    分布 ~p74，并非 p99.87。该门槛只应在预注册 n=20000 处作硬判定，
    小样本仅作信息报告（validate脚本的信息模式退出码已相应区分）。
    """
    gate = 3 * MAPE_REF * np.sqrt(N_REF / max(n, 1))
    return float(max(GATE_FLOOR, gate))


def ece_metric_safe(probs: np.ndarray, labels: np.ndarray) -> float:
    """二分类ECE（10等宽bin），供decompose_benefit默认metric

    注意（R9）：与协议主估计量SmoothECE（calibration.smooth_ece）不同估计量。
    合成验证自洽即可，但27格结论不可外推到主终点量纲（协议§11已注记）。
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
    """8子集全枚举ECE（Shapley/析因/排列共用）"""
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
    """由8子集ECE计算链式/排列/析因交互/Shapley（纯组合，无重采样）"""
    e0, e_s, e_b, e_pi = vals[''], vals['s'], vals['b'], vals['pi']
    e_sb, e_spi, e_bpi, e_sbpi = vals['sb'], vals['spi'], vals['bpi'], vals['sbpi']

    delta_total = e_sbpi - e0
    delta_s = e_s - e0
    delta_b = e_sb - e_s
    delta_pi = e_sbpi - e_sb
    # 残差按链式定义恒为0（套叠恒等式）——真实交互用析因项：
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
    """完整三成分分解（v3）

    v3变化：
    - FI在重采样后子集上计算（R8）
    - 恢复退化捕获为recovery_failed=True+entangled=True，不再raise穿透（R8）
    - Shapley附shares_reliable可靠性标志（R5）
    """
    probs_base, labels_base = _validate_binary(probs_base, labels_base)

    # 注入
    p_inj = inject_transform(probs_base, slope, intercept)
    prev_idx = None
    if target_prev is not None and abs(target_prev - labels_base.mean()) > 1e-9:
        prev_idx = resample_prevalence(p_inj, labels_base, target_prev, rng)

    # 各子集ECE（8子集全枚举：用于Shapley+析因交互）
    vals = _ece_subsets(probs_base, labels_base, slope, intercept, prev_idx, metric)
    attrib = _attribution_from_subsets(vals)

    # 恢复（重采样后 + King-Zeng校正，反例1；R8：退化不再raise穿透）
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
        prev_hat = pi_resampled_val  # 设计常量回读（重采样精确控制正类数）
        prev_true = float(target_prev)
    else:
        prev_hat = pi_injected
        prev_true = pi_injected

    # FI（基线权重；R8：在恢复实际所处设计=重采样后子集上计算）
    if prev_idx is not None:
        det = fisher_information_det(p_inj[prev_idx], probs_base[prev_idx])
    else:
        det = fisher_information_det(p_inj, probs_base)
    entangled = bool(det < IDENTIFIABILITY_TAU or recovery_failed)

    # Shapley占比可靠性（R5）：|Δ_total|低于10-bin ECE噪声底3σ启发式 → 不可解读
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
    """归因量的样本级bootstrap CI（协议§8-3腿3，合成环境可兑现部分）

    每次重复：对基线有放回重采样 → 注入 → （如需）按target_prev重采样 →
    8子集ECE → 链式/析因/Shapley（纯组合）。恢复(logistic)不进bootstrap
    （CI用于归因排序合法性，协议§8-3"CI重叠不得排序主因"）。

    返回 percentile CI（绝对量纲）：delta_total、chain三分量、shapley三绝对值、
    I_sb。占比（shares）不设CI——分母可跨0，percentile无意义（R5修复的一部分：
    排序判定应基于绝对Shapley值的CI）。
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
    """构造 det<τ 的病态基线，验证纠缠分支与恢复失败路径（腿3合成演示）

    三案例：
    1. narrow: p集中于logit空间极窄带（Var(x_base)≈(0.0005)²）→ det≈1.6e-8<τ
    2. tiny_slope: s=0.001 → x'=s·x≈常数 → det∝s²≈1.8e-7<τ
    3. deep_intercept: b=−30 → p'全钳位 → x'常数 → det≈0 且恢复raise
       （验证R8统一路径：recovery_failed=True而非异常穿透）
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
