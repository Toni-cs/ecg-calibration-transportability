"""侦查A：真实数据上 delta_pred vs delta_obs 的结构 + 真Shapley枚举

关键问题：strengthening_battle_corrected.json 里 delta_pred ≈ +0.29 而
delta_obs ≈ +0.02。delta_pred 是 Shapley 三分量之和（预测 ECE 变化），
delta_obs 是真实 ECE 变化。差异 = ?
"""
import json, itertools, math
import numpy as np
from scipy.special import expit

d = json.load(open('results/strengthening_battle_corrected.json'))

def logit(p): 
    p = np.clip(p, 1e-7, 1-1e-7); return np.log(p/(1-p))

def ece(p, y, nbin=10):
    v=0.0; n=len(p)
    for i in range(nbin):
        lo,hi=i/nbin,(i+1)/nbin
        m=(p>=lo)&(p<hi) if i<nbin-1 else (p>=lo)&(p<=hi)
        if m.sum()==0: continue
        v += m.sum()/n*abs(p[m].mean()-y[m].mean())
    return v

rows=[]
for x in d:
    # 载入该 cell 的概率
    fn=f"checkpoints/e2_probs_cache/{x['source']}_{x['target']}_{x['arch']}_seed{x['seed']}.npz"
    try: z=np.load(fn)
    except FileNotFoundError: continue
    cp, cl = z['cal_probs'], z['cal_labels']
    tp, tl = z['test_probs'], z['test_labels']
    K=z['num_classes']
    prev_cal = np.bincount(cl,minlength=K)/len(cl)
    prev_test= np.bincount(tl,minlength=K)/len(tl)

    # top-label ECE (confidence-correctness)
    def topl(p,y):
        c=p.max(1); correct=(p.argmax(1)==y).astype(float)
        return c, correct
    c_raw, corr_raw = topl(tp, tl)
    # TS 校准
    T=x['T']
    tp_ts = np.exp(logit(tp)/T); tp_ts/=tp_ts.sum(1,keepdims=True)
    c_ts, _ = topl(tp_ts, tl)
    e_raw = ece(c_raw, corr_raw); e_ts = ece(c_ts, corr_raw)

    # 8子集 Shapley：s(斜率,用T反推 a=1/T), b(截距), pi(先验重加权)
    s_true = 1.0/T          # 注入斜率真值 proxy
    b_true = 0.0            # TS 没有截距
    # 先验成分：用 cal 先验 → test 先验 的 logit 平移
    pi_shift = np.log(np.clip(prev_test,1e-9,1)/np.clip(prev_cal,1e-9,1))

    def subset(slope, intercept, use_pi):
        zz = logit(tp)*slope + intercept
        if use_pi: zz = zz + pi_shift[None,:]
        pp = np.exp(zz - zz.max(1,keepdims=True)); pp/=pp.sum(1,keepdims=True)
        c,corr = topl(pp, tl)
        return ece(c, corr)

    vals = {k: subset(*a) for k,a in {
        '':(1,0,False),'s':(s_true,0,False),'b':(1,b_true,False),'pi':(1,0,True),
        'sb':(s_true,b_true,False),'spi':(s_true,0,True),'bpi':(1,b_true,True),
        'sbpi':(s_true,b_true,True)}.items()}

    _CANON={'s':0,'b':1,'pi':2}
    def key(cs): return ''.join(sorted(cs, key=lambda c:_CANON[c]))
    def shap(comp):
        tot=0.0; others=[c for c in ['s','b','pi'] if c!=comp]
        for r in range(3):
            for sub in itertools.combinations(others,r):
                kw=key(sub+(comp,)); kwo=key(sub)
                tot += math.factorial(r)*math.factorial(2-r)/6*(vals[kw]-vals[kwo])
        return tot

    sh = {c: shap(c) for c in ['s','b','pi']}
    d_pred = sum(sh.values())
    d_obs_true = e_raw - e_ts   # 真值 ΔECE
    rows.append(dict(src=x['source'],tgt=x['target'],arch=x['arch'],seed=x['seed'],
        K=K, e_raw=e_raw, e_ts=e_ts, d_obs_true=d_obs_true,
        d_obs_json=x['delta_obs'], d_pred_json=x['delta_pred'],
        d_pred_enum=d_pred, ece_sub_raw=vals[''], ece_sub_sbpi=vals['sbpi'],
        sh_s=sh['s'],sh_b=sh['b'],sh_pi=sh['pi'],
        prev_l1=x['prev_l1'], T=T, ood_acc=x['ood_acc']))

import pandas as pd
df=pd.DataFrame(rows)
df.to_csv('_recon_A_real_shapley.csv',index=False)
print(f"n={len(df)}")
print("\n=== 真值 vs JSON 报的 delta_pred ===")
print(df[['src','tgt','arch','seed','d_obs_json','d_obs_true','d_pred_json','d_pred_enum','ece_sub_raw','ece_sub_sbpi']].to_string())
print("\n=== 汇总 ===")
print(f"mean d_obs_true  = {df.d_obs_true.mean():+.4f}")
print(f"mean d_pred_json = {df.d_pred_json.mean():+.4f}")
print(f"mean d_pred_enum = {df.d_pred_enum.mean():+.4f}")
print(f"偏差 (d_pred_json - d_obs_true).mean() = {(df.d_pred_json-d.d_obs_true).mean():+.4f}" if False else
      f"偏差 (d_pred_json - d_obs_true).mean() = {(df.d_pred_json-df.d_obs_true).mean():+.4f}")
print(f"Shapley mean: s={df.sh_s.mean():+.4f} b={df.sh_b.mean():+.4f} pi={df.sh_pi.mean():+.4f}")
