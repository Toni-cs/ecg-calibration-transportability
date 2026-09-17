"""侦查B：拆解 delta_pred 的构成，定位 +0.29 的真实来源

delta_pred 定义不明。假设：Shapley 三分量在**注入的合成变换**（s,b,pi）上算，
而注入变换本身（s_true=1/T, b_true, pi_shift）与真实校准算子的差异 = 误差。
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
    fn=f"checkpoints/e2_probs_cache/{x['source']}_{x['target']}_{x['arch']}_seed{x['seed']}.npz"
    try: z=np.load(fn)
    except FileNotFoundError: continue
    tp, tl = z['test_probs'], z['test_labels']; K=z['num_classes']
    cl=z['cal_labels']
    prev_cal=np.bincount(cl,minlength=K)/len(cl)
    prev_test=np.bincount(tl,minlength=K)/len(tl)
    T=x['T']; pi_shift=np.log(np.clip(prev_test,1e-9,1)/np.clip(prev_cal,1e-9,1))

    def evalset(slope, intercept, use_pi, base):
        zz=logit(base)*slope+intercept
        if use_pi: zz=zz+pi_shift[None,:]
        pp=np.exp(zz-zz.max(1,keepdims=True)); pp/=pp.sum(1,keepdims=True)
        return ece(pp.max(1),(pp.argmax(1)==tl).astype(float))

    # 关键：Shapley 在**什么 base** 上算？两个候选
    #  候选1: base = tp (目标域原始概率)   -> 注入变换直接作用于 test_probs
    #  候选2: base = tp 经 T 温度后         -> 注入是"残余"变换
    res={}
    for tag, base, s_t, b_t in [('inj_on_raw', tp, 1.0/T, 0.0),
                                 ('inj_on_ts',  np.exp(logit(tp)/T)/np.exp(logit(tp)/T).sum(1,keepdims=True), 1.0, 0.0)]:
        v={k:evalset(*a,base) for k,a in {
            '':(1,0,False),'s':(s_t,0,False),'b':(1,b_t,False),'pi':(1,0,True),
            'sb':(s_t,b_t,False),'spi':(s_t,0,True),'bpi':(1,b_t,True),'sbpi':(s_t,b_t,True)}.items()}
        _C={'s':0,'b':1,'pi':2}
        key=lambda cs:''.join(sorted(cs,key=lambda c:_C[c]))
        def sh(comp):
            tot=0.0; oth=[c for c in ['s','b','pi'] if c!=comp]
            for r in range(3):
                for sub in itertools.combinations(oth,r):
                    tot+=math.factorial(r)*math.factorial(2-r)/6*(v[key(sub+(comp,))]-v[key(sub)])
            return tot
        S={c:sh(c) for c in ['s','b','pi']}
        res[tag]=dict(sum=sum(S.values()), s=S['s'],b=S['b'],pi=S['pi'], e0=v[''], e_full=v['sbpi'])
    rows.append(dict(src=x['source'],tgt=x['target'],arch=x['arch'],seed=x['seed'],
        T=T, d_obs_true=x['delta_obs'], d_pred_json=x['delta_pred'],
        **{f'{k}_{kk}':vv for k,r in res.items() for kk,vv in r.items()}))

import pandas as pd
df=pd.DataFrame(rows)
df.to_csv('_recon_B.csv',index=False)
print(f"n={len(df)}\n")
for tag in ['inj_on_raw','inj_on_ts']:
    dif = (df[f'{tag}_sum'] - df.d_obs_true)
    print(f"[{tag}]  sum_shapley 均值={df[f'{tag}_sum'].mean():+.4f}  "
          f"vs d_obs_true={df.d_obs_true.mean():+.4f}  "
          f"偏差均值={dif.mean():+.4f}  |偏差|均值={dif.abs().mean():+.4f}")
    print(f"    分量: s={df[f'{tag}_s'].mean():+.4f} b={df[f'{tag}_b'].mean():+.4f} pi={df[f'{tag}_pi'].mean():+.4f}")
print(f"\nJSON delta_pred 均值 = {df.d_pred_json.mean():+.4f}")
print(f"d_obs_true 均值      = {df.d_obs_true.mean():+.4f}")
print(f"JSON - true 偏差均值 = {(df.d_pred_json-df.d_obs_true).mean():+.4f}")
print(f"JSON - true |偏差|   = {(df.d_pred_json-df.d_obs_true).abs().mean():+.4f}")
print("\n各候选与 JSON 的相关：")
for tag in ['inj_on_raw','inj_on_ts']:
    print(f"  corr({tag}_sum, d_pred_json) = {np.corrcoef(df[f'{tag}_sum'],df.d_pred_json)[0,1]:+.4f}")
