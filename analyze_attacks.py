"""只看TS方法，验证42/48结论，并分析5个攻击点。"""
import json
from pathlib import Path
from collections import defaultdict, Counter

root = Path(r'D:\A1\ecg-lab-v2\checkpoints\transfer')
all_files = list(root.rglob('transfer_result.json'))

# 只看TS方法，每个seed的CI下界>0为支持
ts_records = []
for tr in all_files:
    with open(tr, 'r') as f:
        d = json.load(f)
    src = d['source']
    tgt = d['target']
    arch = d['arch']
    seed = d['seed']
    methods = d.get('methods', {})
    ts = methods.get('ts', {})
    if 'ood' not in ts:
        continue
    ood = ts['ood']
    delta = ood.get('deltaECE')
    ci = ood.get('ci')
    decay = ts.get('decay')
    if ci is None:
        continue
    ts_records.append({
        'src': src, 'tgt': tgt, 'arch': arch, 'seed': seed,
        'delta': delta, 'ci_lo': ci[0], 'ci_hi': ci[1], 'decay': decay,
        'sig_pos': ci[0] > 0
    })

# 排除mamba（论文的48个不含mamba）
ts_no_mamba = [r for r in ts_records if r['arch'] != 'mamba']
ts_mamba = [r for r in ts_records if r['arch'] == 'mamba']

print('=' * 80)
print('TS方法验证（排除mamba）')
print('=' * 80)
n_total = len(ts_no_mamba)
n_pos = sum(1 for r in ts_no_mamba if r['sig_pos'])
print(f'总实验数: {n_total}')
print(f'显著为正: {n_pos}/{n_total} = {100*n_pos/n_total:.1f}%')

# 按架构
print('\n按架构:')
for arch in ['inceptiontime', 'resnet1d']:
    arch_r = [r for r in ts_no_mamba if r['arch'] == arch]
    arch_pos = sum(1 for r in arch_r if r['sig_pos'])
    print(f'  {arch}: {arch_pos}/{len(arch_r)} = {100*arch_pos/len(arch_r):.1f}%')

# 反例
print('\n反例（TS方法，排除mamba）:')
counterexamples = [r for r in ts_no_mamba if not r['sig_pos']]
for r in counterexamples:
    print(f"  {r['src']:8s}->{r['tgt']:8s} {r['arch']:13s} seed{r['seed']} "
          f"delta={r['delta']:+.4f} CI=[{r['ci_lo']:+.4f}, {r['ci_hi']:+.4f}]")

# mamba情况
print('\nmamba（被论文排除）:')
for r in ts_mamba:
    print(f"  {r['src']:8s}->{r['tgt']:8s} {r['arch']:13s} seed{r['seed']} "
          f"delta={r['delta']:+.4f} CI=[{r['ci_lo']:+.4f}, {r['ci_hi']:+.4f}]")

# ===== 攻击1: resnet1d覆盖不完整 =====
print('\n' + '=' * 80)
print('攻击1: resnet1d覆盖不完整')
print('=' * 80)
resnet_by_dir = defaultdict(list)
for r in ts_no_mamba:
    if r['arch'] == 'resnet1d':
        resnet_by_dir[f"{r['src']}->{r['tgt']}"].append(r['seed'])

print('resnet1d各方向seed覆盖:')
for d in ['chapman->cpsc', 'chapman->ptbxl', 'cpsc->chapman', 'cpsc->ptbxl',
          'ptbxl->chapman', 'ptbxl->cpsc']:
    seeds = sorted(resnet_by_dir.get(d, []))
    print(f'  {d}: {seeds} ({len(seeds)}seed)')

n_5seed = sum(1 for d, s in resnet_by_dir.items() if len(s) >= 5)
n_2seed = sum(1 for d, s in resnet_by_dir.items() if len(s) <= 2)
print(f'\n5seed方向: {n_5seed}/6')
print(f'2seed方向: {n_2seed}/6')
print(f'resnet1d总实验: {sum(len(s) for s in resnet_by_dir.values())}')

# resnet1d在2seed方向的反例率
print('\nresnet1d在2seed方向的反例:')
for d in ['chapman->ptbxl', 'cpsc->chapman', 'cpsc->ptbxl', 'ptbxl->chapman']:
    recs = [r for r in ts_no_mamba if r['arch'] == 'resnet1d' and f"{r['src']}->{r['tgt']}" == d]
    for r in recs:
        status = '支持' if r['sig_pos'] else '反例'
        print(f'  {d} seed{r["seed"]}: {status} delta={r["delta"]:+.4f}')

# ===== 攻击2: mamba架构缺失 =====
print('\n' + '=' * 80)
print('攻击2: mamba架构缺失')
print('=' * 80)
mamba_files = list(root.rglob('transfer_result.json'))
mamba_files = [f for f in mamba_files if 'mamba' in str(f)]
print(f'mamba实验文件数: {len(mamba_files)}')
mamba_by_dir = defaultdict(list)
for r in ts_mamba:
    mamba_by_dir[f"{r['src']}->{r['tgt']}"].append(r['seed'])
print('mamba各方向seed覆盖:')
for d in ['chapman->cpsc', 'chapman->ptbxl', 'cpsc->chapman', 'cpsc->ptbxl',
          'ptbxl->chapman', 'ptbxl->cpsc']:
    seeds = sorted(mamba_by_dir.get(d, []))
    print(f'  {d}: {seeds} ({len(seeds)}seed)')

# mamba的样本量
print('\nmamba样本量:')
for tr in mamba_files:
    with open(tr, 'r') as f:
        d = json.load(f)
    print(f"  {d['source']}->{d['target']} seed{d['seed']}: n_id={d['n_id']}, n_ood={d['n_ood']}, "
          f"id_acc={d['id_acc']:.3f}, ood_acc={d['ood_acc']:.3f}")

# 对比inceptiontime/resnet1d的样本量
print('\n对比inceptiontime样本量（取一个）:')
it_file = next(root.rglob('inceptiontime/seed42/transfer_result.json'))
with open(it_file, 'r') as f:
    d = json.load(f)
print(f"  {d['source']}->{d['target']} seed{d['seed']}: n_id={d['n_id']}, n_ood={d['n_ood']}")

# ===== 攻击3: 反例分布偏差 =====
print('\n' + '=' * 80)
print('攻击3: 反例分布偏差')
print('=' * 80)
print('反例按方向分布:')
neg_by_dir = Counter()
total_by_dir = Counter()
for r in ts_no_mamba:
    d = f"{r['src']}->{r['tgt']}"
    total_by_dir[d] += 1
    if not r['sig_pos']:
        neg_by_dir[d] += 1
for d in sorted(total_by_dir.keys()):
    print(f'  {d}: {neg_by_dir[d]}/{total_by_dir[d]} 反例')

print('\n反例按架构分布:')
neg_by_arch = Counter()
total_by_arch = Counter()
for r in ts_no_mamba:
    a = r['arch']
    total_by_arch[a] += 1
    if not r['sig_pos']:
        neg_by_arch[a] += 1
for a in sorted(total_by_arch.keys()):
    print(f'  {a}: {neg_by_arch[a]}/{total_by_arch[a]} 反例')

print('\n反例按源域分布:')
neg_by_src = Counter()
total_by_src = Counter()
for r in ts_no_mamba:
    s = r['src']
    total_by_src[s] += 1
    if not r['sig_pos']:
        neg_by_src[s] += 1
for s in sorted(total_by_src.keys()):
    print(f'  {s}作为源: {neg_by_src[s]}/{total_by_src[s]} 反例')

print('\n反例按目标域分布:')
neg_by_tgt = Counter()
total_by_tgt = Counter()
for r in ts_no_mamba:
    t = r['tgt']
    total_by_tgt[t] += 1
    if not r['sig_pos']:
        neg_by_tgt[t] += 1
for t in sorted(total_by_tgt.keys()):
    print(f'  {t}作为目标: {neg_by_tgt[t]}/{total_by_tgt[t]} 反例')

# ===== 攻击4: inceptiontime的seed覆盖 =====
print('\n' + '=' * 80)
print('攻击4: inceptiontime的seed覆盖')
print('=' * 80)
it_by_dir = defaultdict(list)
for r in ts_no_mamba:
    if r['arch'] == 'inceptiontime':
        it_by_dir[f"{r['src']}->{r['tgt']}"].append(r['seed'])

print('inceptiontime各方向seed覆盖:')
for d in ['chapman->cpsc', 'chapman->ptbxl', 'cpsc->chapman', 'cpsc->ptbxl',
          'ptbxl->chapman', 'ptbxl->cpsc']:
    seeds = sorted(it_by_dir.get(d, []))
    print(f'  {d}: {seeds} ({len(seeds)}seed)')

print('\ninceptiontime覆盖完整: 6方向×5seed = 30 ✓')

# resnet1d的seed覆盖对比
print('\nresnet1d各方向seed覆盖（对比）:')
for d in ['chapman->cpsc', 'chapman->ptbxl', 'cpsc->chapman', 'cpsc->ptbxl',
          'ptbxl->chapman', 'ptbxl->cpsc']:
    seeds = sorted(resnet_by_dir.get(d, []))
    print(f'  {d}: {seeds} ({len(seeds)}seed)')

# ===== 攻击5: 方向对称性 =====
print('\n' + '=' * 80)
print('攻击5: 方向对称性（互逆方向对比）')
print('=' * 80)
pairs = [('chapman', 'cpsc'), ('chapman', 'ptbxl'), ('cpsc', 'ptbxl')]
for arch in ['inceptiontime', 'resnet1d']:
    print(f'\n{arch}:')
    for a, b in pairs:
        fwd = [r for r in ts_no_mamba if r['src'] == a and r['tgt'] == b and r['arch'] == arch]
        rev = [r for r in ts_no_mamba if r['src'] == b and r['tgt'] == a and r['arch'] == arch]
        fwd_pos = sum(1 for r in fwd if r['sig_pos'])
        rev_pos = sum(1 for r in rev if r['sig_pos'])
        fwd_mean = sum(r['delta'] for r in fwd) / len(fwd) if fwd else 0
        rev_mean = sum(r['delta'] for r in rev) / len(rev) if rev else 0
        sym = '✓对称' if (fwd_pos == rev_pos or (fwd_pos > 0 and rev_pos > 0)) else '✗不对称'
        print(f'  {a}->{b}: {fwd_pos}/{len(fwd)}支持, 均值={fwd_mean:+.4f} '
              f'vs {b}->{a}: {rev_pos}/{len(rev)}支持, 均值={rev_mean:+.4f} {sym}')