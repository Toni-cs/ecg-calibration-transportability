"""侦查C：还原论文 §real_shapley 的 linear 预测模型，检验 +0.29 是否真实

论文描述: ΔECE ≈ ŝ·slope + b̂·intercept + π̂·prevalence，
(ŝ,b̂) 在 cal split 估，ΔECE 在 target test split 预。
"""
import json, itertools, math, warnings
import numpy as np
from scipy.special import expit
from scipy.optimize import minimize
warnings.filterwarnings('ignore')

d = json.load(open('results/strengthening_battle_corrected.json'))

def logit(p):
    p=np.clip(p,1e-12,1-1e-12); return np.log(p/(1-p))
def sm(z):
    z=z-z.max(-1,keepdims=True); e=np.exp(z); return e/e.sum(-1,keepdims=True)
def ece_mc(p2d,y,K,nbin=10):
    """top-label ECE, multiclass softmax probs"""
    c=p2d.max(1); corr=(p2d.argmax(1)==y).astype(float)
    v=0.0;n=len(c)
    for i in range(nbin):
        lo,hi=i/nbin,(i+1)/nbin
        m=(c>=lo)&(c<hi) if i<nbin-1 else (c>=lo)&(c<=hi)
        if m.sum()==0: continue
        v+=m.sum()/n*abs(c[m].mean()-corr[m].mean())
    return float(v)
def ts(p2d,T): return sm(logit(p2d)/T)

res=[]
for x in d:
    fn=f"checkpoints/e2_probs_cache/{x['source']}_{x['target']}_{x['arch']}_seed{x['seed']}.npz"
    try: z=np.load(fn)
    except FileNotFoundError: continue
    cp,cl=z['cal_probs'],z['cal_labels']
    tp,tl=z['test_probs'],z['test_labels']; K=int(z['num_classes'])
    T=x['T']
    # ---- 在 cal split 上估 (ŝ,b̂)：用 (logit(p_cal), correct) 做二值 logistic ----
    ccal=cp.max(1); ycal=(cp.argmax(1)==cl).astype(float)
    xp=logit(ccal).reshape(-1,1)
    from sklearn.linear_model import LogisticRegression
    lr=LogisticRegression(C=1e4,max_iter=5000).fit(xp,ycal)
    a,cc=float(lr.coef_[0,0]),float(lr.intercept_[0])
    s_hat=1.0/a; b_hat=-cc/a
    # prevalence 分量
    pi_cal=np.bincount(cl,minlength=K)/len(cl); pi_tst=np.bincount(tl,minlength=K)/len(tl)
    # ---- 目标 test split 真 ΔECE ----
    e_raw=ece_mc(tp,tl,K); e_ts=ece_mc(ts(tp,T),tl,K)
    d_obs=e_raw-e_ts
    # ---- 论文线性预测：ŝ·slope + b̂·intercept + π̂·prevalence ----
    # 用 s_hat,b_hat 作用于 test 的 *全局* 温度算子，产生预测ΔECE
    def d_ece_of(sl,b_):
        return ece_mc(tp,tl,K) - ece_mc(sm(logit(tp)*sl+b_),tl,K)
    # 一阶线性化（论文的 linear approx）
    eps=1e-3
    dsl=(d_ece_of(1+eps,0)-d_ece_of(1-eps,0))/(2*eps)
    dbb=(d_ece_of(1,eps)-d_ece_of(1,-eps))/(2*eps)
    # 预测：假设注入为 (slope=s_hat, intercept=b_hat)，线性外推
    d_pred_lin = dsl*(s_hat-1) + dbb*(b_hat-0)
    d_pred_full= d_ece_of(s_hat,b_hat)
    res.append(dict(src=x['source'],tgt=x['target'],arch=x['arch'],seed=x['seed'],
        T=float(T),s_hat=s_hat,b_hat=b_hat,pi_l1=np.abs(pi_cal-pi_tst).sum(),
        d_obs=d_obs, d_obs_json=x['delta_obs'], d_pred_json=x['delta_pred'],
        d_pred_lin=d_pred_lin, d_pred_full=d_pred_full,
        e_raw=e_raw,e_ts=e_ts, ood_acc=x['ood_acc'],
        wass=x['wasserstein']))

import pandas as pd
df=pd.DataFrame(res); df.to_csv('_recon_C.csv',index=False)
print(f"n={len(df)}")
for c in ['d_obs','d_obs_json','d_pred_json','d_pred_lin','d_pred_full']:
    print(f"  {c:>14}: mean={df[c].mean():+.4f} med={df[c].median():+.4f} std={df[c].std():.4f}")
print()
for c in ['d_pred_json','d_pred_lin','d_pred_full']:
    err=df[c]-df.d_obs
    errj=df[c]-df.d_obs_json
    print(f"{c:>14}: vs d_obs 误差 mean={err.mean():+.4f} |err|={err.abs().mean():.4f} "
          f"sign_acc={np.mean(np.sign(df[c])==np.sign(df.d_obs)):.3f} | vs json 误差 mean={errj.mean():+.4f}")
print(f"\nd_obs vs d_obs_json 一致性: mean diff={ (df.d_obs-df.d_obs_json).mean():+.4f} |diff|={ (df.d_obs-df.d_obs_json).abs().mean():.4f} corr={np.corrcoef(df.d_obs,df.d_obs_json)[0,1]:+.3f}")
print(f"\n相关性 s_hat~pi_l1: {np.corrcoef(df.s_hat,df.pi_l1)[0,1]:+.3f}")
print(f"相关性 b_hat~pi_l1: {np.corrcoef(df.b_hat,df.pi_l1)[0,1]:+.3f}")
print(f"相关性 T~pi_l1    : {np.corrcoef(df['T'],df.pi_l1)[0,1]:+.3f}")
print(f"相关性 s_hat~1/T  : {np.corrcoef(df.s_hat,1/df.T)[0,1]:+.3f}")
print(f"相关性 d_obs~wass : {np.corrcoef(df.d_obs,df.wass)[0,1]:+.3f}")
print(f"相关性 d_obs~acc  : {np.corrcoef(df.d_obs,df.ood_acc)[0,1]:+.3f}")
