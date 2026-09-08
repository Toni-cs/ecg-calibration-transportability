"""统计所有 transfer_result.json 的 decay 显著性分布。"""
import json
from pathlib import Path
from collections import Counter, defaultdict

root = Path(r'D:\A1\ecg-lab-v2\checkpoints\transfer')

# 收集所有 transfer_result.json
all_files = list(root.rglob('transfer_result.json'))
print(f'Total transfer_result.json files: {len(all_files)}')

# 文件级覆盖矩阵
file_matrix = defaultdict(set)  # (arch, direction) -> set(seeds)
for tr in all_files:
    with open(tr, 'r') as f:
        d = json.load(f)
    src = d['source']
    tgt = d['target']
    arch = d['arch']
    seed = d['seed']
    file_matrix[(arch, src + '->' + tgt)].add(seed)

print('\n=== 文件级覆盖矩阵 (arch x direction -> seeds) ===')
archs = ['inceptiontime', 'resnet1d', 'mamba']
dirs = ['chapman->cpsc', 'chapman->ptbxl', 'cpsc->chapman', 'cpsc->ptbxl',
        'ptbxl->chapman', 'ptbxl->cpsc']
print(f'{"":15s}', end='')
for d in dirs:
    print(f'{d:18s}', end='')
print()
for a in archs:
    print(f'{a:15s}', end='')
    for d in dirs:
        seeds = sorted(file_matrix.get((a, d), set()))
        print(f'{str(seeds):18s}', end='')
    print()

# 方法级统计
records = []
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
        ood = mdata['ood']
        decay = mdata.get('decay')
        ci = ood.get('ci')
        if decay is None or ci is None:
            continue
        sig_pos = ci[0] > 0
        sig_neg = ci[1] < 0
        records.append({
            'src': src, 'tgt': tgt, 'arch': arch, 'seed': seed,
            'method': mname, 'decay': decay, 'ci_lo': ci[0], 'ci_hi': ci[1],
            'sig_pos': sig_pos, 'sig_neg': sig_neg
        })

print(f'\nTotal method-level records: {len(records)}')

# 实验级（每个 transfer_result.json 算一个实验）
exp_count = len(all_files)
print(f'Total experiments (files): {exp_count}')

# 每个实验是否"显著为正"=所有方法的 ood decay CI 下界>0
exp_results = []
for tr in all_files:
    with open(tr, 'r') as f:
        d = json.load(f)
    src = d['source']
    tgt = d['target']
    arch = d['arch']
    seed = d['seed']
    methods = d.get('methods', {})
    all_pos = True
    n_methods = 0
    n_pos = 0
    n_neg = 0
    for mname, mdata in methods.items():
        if not isinstance(mdata, dict) or 'ood' not in mdata:
            continue
        ood = mdata['ood']
        ci = ood.get('ci')
        if ci is None:
            continue
        n_methods += 1
        if ci[0] > 0:
            n_pos += 1
        elif ci[1] < 0:
            n_neg += 1
    exp_results.append({
        'src': src, 'tgt': tgt, 'arch': arch, 'seed': seed,
        'n_methods': n_methods, 'n_pos': n_pos, 'n_neg': n_neg,
        'all_pos': (n_pos == n_methods and n_methods > 0)
    })

print('\n=== 实验级"所有方法显著为正"统计 ===')
n_all_pos = sum(1 for e in exp_results if e['all_pos'])
print(f'全方法显著为正的实验: {n_all_pos}/{len(exp_results)} = {100*n_all_pos/len(exp_results):.1f}%')

# 反例实验
print('\n=== 反例实验（非全方法显著为正） ===')
for e in exp_results:
    if not e['all_pos']:
        print(f"  {e['src']:8s}->{e['tgt']:8s} {e['arch']:13s} seed{e['seed']} "
              f"pos={e['n_pos']}/{e['n_methods']} neg={e['n_neg']}")

# 反例的方向/架构分布
print('\n=== 反例按方向分布 ===')
neg_by_dir = Counter()
for e in exp_results:
    if not e['all_pos']:
        neg_by_dir[e['src'] + '->' + e['tgt']] += 1
for k, v in sorted(neg_by_dir.items()):
    print(f'  {k}: {v}')

print('\n=== 反例按架构分布 ===')
neg_by_arch = Counter()
for e in exp_results:
    if not e['all_pos']:
        neg_by_arch[e['arch']] += 1
for k, v in sorted(neg_by_arch.items()):
    print(f'  {k}: {v}')

# 方法级反例
print('\n=== 方法级反例（CI 下界<=0 的方法-实验组合） ===')
neg_methods = [r for r in records if not r['sig_pos']]
print(f'方法级非显著为正: {len(neg_methods)}/{len(records)}')
neg_by_method = Counter(r['method'] for r in neg_methods)
for k, v in sorted(neg_by_method.items(), key=lambda x: -x[1]):
    print(f'  {k:15s}: {v}')

# 互逆方向对比
print('\n=== 互逆方向对比（inceptiontime，全方法显著为正率） ===')
pairs = [('chapman', 'cpsc'), ('chapman', 'ptbxl'), ('cpsc', 'ptbxl')]
for a, b in pairs:
    fwd = [e for e in exp_results if e['src'] == a and e['tgt'] == b and e['arch'] == 'inceptiontime']
    rev = [e for e in exp_results if e['src'] == b and e['tgt'] == a and e['arch'] == 'inceptiontime']
    fwd_pos = sum(1 for e in fwd if e['all_pos'])
    rev_pos = sum(1 for e in rev if e['all_pos'])
    print(f'  {a}->{b}: {fwd_pos}/{len(fwd)} vs {b}->{a}: {rev_pos}/{len(rev)}')