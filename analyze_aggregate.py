"""按 (方向, 架构, 方法) 聚合，做 t 检验判断显著性。"""
import json
import math
from pathlib import Path
from collections import defaultdict
from scipy import stats

root = Path(r'D:\A1\ecg-lab-v2\checkpoints\transfer')
all_files = list(root.rglob('transfer_result.json'))

# 收集每个 (方向, 架构, 方法) 的 decay 列表
agg = defaultdict(list)  # (src, tgt, arch, method) -> [decay]
for tr in all_files:
    with open(tr, 'r') as f:
        d = json.load(f)
    src = d['source']
    tgt = d['target']
    arch = d['arch']
    seed = d['seed']
    methods = d.get('methods', {})
    for mname, mdata in methods.items():
        if not isinstance(mdata, dict) or 'ood' not in mdata:
            continue
        decay = mdata.get('decay')
        if decay is None:
            continue
        agg[(src, tgt, arch, mname)].append((seed, decay))

# 对每个组合做单样本 t 检验 (H0: mean=0, H1: mean>0)
print('=== (方向, 架构, 方法) 聚合 t 检验 ===')
print(f'{"方向":18s} {"架构":13s} {"方法":12s} {"n":3s} {"mean":8s} {"t":8s} {"p":10s} {"ci_lo":10s} {"显著为正":6s}')
results = []
for (src, tgt, arch, mname), seed_decays in sorted(agg.items()):
    decays = [sd[1] for sd in seed_decays]
    n = len(decays)
    mean = sum(decays) / n
    if n < 2:
        # 单样本无法做 t 检验
        t_stat = float('nan')
        p_val = float('nan')
        ci_lo = float('nan')
        sig = 'N/A'
    else:
        t_stat, p_val = stats.ttest_1samp(decays, 0)
        # 单侧检验 p 值
        if t_stat > 0:
            p_val = p_val / 2
        else:
            p_val = 1 - p_val / 2
        # 95% CI 下界
        se = stats.sem(decays)
        ci_lo = mean - stats.t.ppf(0.975, n - 1) * se
        sig = 'YES' if ci_lo > 0 else ('NEG' if mean < 0 else 'no')
    results.append({
        'dir': f'{src}->{tgt}', 'arch': arch, 'method': mname,
        'n': n, 'mean': mean, 't': t_stat, 'p': p_val, 'ci_lo': ci_lo,
        'sig_pos': bool(ci_lo > 0) if n >= 2 else None
    })
    print(f'{src+"->"+tgt:18s} {arch:13s} {mname:12s} {n:3d} {mean:8.4f} {t_stat:8.3f} {p_val:10.4f} {ci_lo:10.4f} {sig:6s}')

# 统计
n_total = len(results)
n_sig_pos = sum(1 for r in results if r['sig_pos'] is True)
n_not_sig = sum(1 for r in results if r['sig_pos'] is False)
n_na = sum(1 for r in results if r['sig_pos'] is None)
print(f'\n总组合数: {n_total}')
print(f'显著为正 (CI下界>0): {n_sig_pos}')
print(f'非显著为正: {n_not_sig}')
print(f'N/A (n<2): {n_na}')
print(f'显著为正率 (排除N/A): {n_sig_pos}/{n_sig_pos+n_not_sig} = {100*n_sig_pos/(n_sig_pos+n_not_sig):.1f}%')

# 按架构分组
print('\n=== 按架构分组 ===')
for arch in ['inceptiontime', 'resnet1d', 'mamba']:
    arch_results = [r for r in results if r['arch'] == arch]
    arch_sig = sum(1 for r in arch_results if r['sig_pos'] is True)
    arch_not = sum(1 for r in arch_results if r['sig_pos'] is False)
    arch_na = sum(1 for r in arch_results if r['sig_pos'] is None)
    print(f'{arch}: {arch_sig}显著为正 + {arch_not}非显著 + {arch_na} N/A = {len(arch_results)}总')

# 反例详情
print('\n=== 反例（非显著为正）详情 ===')
for r in results:
    if r['sig_pos'] is False:
        print(f"  {r['dir']:18s} {r['arch']:13s} {r['method']:12s} n={r['n']} mean={r['mean']:.4f} ci_lo={r['ci_lo']:.4f}")

# 互逆方向对比（按架构 inceptiontime）
print('\n=== 互逆方向对比（inceptiontime，按方法聚合后显著为正率） ===')
pairs = [('chapman', 'cpsc'), ('chapman', 'ptbxl'), ('cpsc', 'ptbxl')]
for a, b in pairs:
    fwd = [r for r in results if r['dir'] == f'{a}->{b}' and r['arch'] == 'inceptiontime']
    rev = [r for r in results if r['dir'] == f'{b}->{a}' and r['arch'] == 'inceptiontime']
    fwd_pos = sum(1 for r in fwd if r['sig_pos'] is True)
    rev_pos = sum(1 for r in rev if r['sig_pos'] is True)
    print(f'  {a}->{b}: {fwd_pos}/{len(fwd)} 显著为正 vs {b}->{a}: {rev_pos}/{len(rev)} 显著为正')

# 互逆方向对比（按架构 resnet1d）
print('\n=== 互逆方向对比（resnet1d，按方法聚合后显著为正率） ===')
for a, b in pairs:
    fwd = [r for r in results if r['dir'] == f'{a}->{b}' and r['arch'] == 'resnet1d']
    rev = [r for r in results if r['dir'] == f'{b}->{a}' and r['arch'] == 'resnet1d']
    fwd_pos = sum(1 for r in fwd if r['sig_pos'] is True)
    rev_pos = sum(1 for r in rev if r['sig_pos'] is True)
    print(f'  {a}->{b}: {fwd_pos}/{len(fwd)} 显著为正 vs {b}->{a}: {rev_pos}/{len(rev)} 显著为正')