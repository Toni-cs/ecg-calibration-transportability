"""侦查D：核心诊断——真实数据上的误差结构与 shift 严重程度/K/条件数的关系

目标：解释为什么幅度误差巨大，并定位可改进的数学机制。
"""
import json, warnings
import numpy as np
from sklearn.linear_model import LogisticRegression
warnings.filterwarnings('ignore')

def logit(p):
    p=np.clip(p,1e-12,1-1e-12); return np.log(p/(1-p))
def sm(z):
    z=z-z.max(-1,keepdims=True); e=np.exp(z); return e/e.sum(-1,keepdims=True)
def ece_mc(p2d,y,nbin=10):
    c=p2d.max(1); corr=(p2d.argmax(1)==y).astype(float)
    v=0.0;n=len(c)
    for i in range(nbin):
        lo,hi=i/nbin,(i+1)/nbin
        m=(c>=lo)&(c<hi) if i<nbin-1 else (c>=lo)&(c<=hi)
        if m.sum()==0: continue
        v+=m.sum()/n*abs(c[m].mean()-corr[m].mean())
    return float(v)

rows=[]
for src,tgt in [('chapman','cpsc'),('cpsc','chapman'),('chapman','ptbxl'),
                ('ptbxl','chapman'),('cpsc','ptbxl'),('ptbxl','cpsc')]:
    for arch in ['inceptiontime','resnet1d']:
        for seed in [42,43,44,45,46]:
            fn=f"checkpoints/e2_probs_cache/{src}_{tgt}_{arch}_seed{seed}.npz"
            try: z=np.load(fn)
            except FileNotFoundError: continue
            cp,cl=z['cal_probs'],z['cal_labels']
            tp,tl=z['test_probs'],z['test_labels']; K=int(z['num_classes'])
            pi_cal=np.bincount(cl,minlength=K)/len(cl)
            pi_tst=np.bincount(tl,minlength=K)/len(tl)
            # 温度（在 cal 上拟合）
            from src.utils.calibration_methods import (fit_temperature_multiclass,
                apply_temperature_multiclass)
            pa=fit_temperature_multiclass(cp,cl); T=pa['T']
            e_raw=ece_mc(tp,tl); e_ts=ece_mc(apply_temperature_multiclass(tp,pa),tl)
            d_obs=e_raw-e_ts
            # cal split 上的二值 logistic 恢复 (ŝ,b̂) —— 复刻 decomposition 恢复路径
            ccal=cp.max(1); ycal=(cp.argmax(1)==cl).astype(float)
            lr=LogisticRegression(C=1e4,max_iter=5000).fit(logit(ccal).reshape(-1,1),ycal)
            a,cc=float(lr.coef_[0,0]),float(lr.intercept_[0])
            s_hat,b_hat=1.0/a,-cc/a
            # 目标域真实'正确性'概率下, 校准增益的**充分统计**
            # 关键量：baseline 误校准的斜率偏离
            ct=tp.max(1); yt=(tp.argmax(1)==tl).astype(float)
            lr_t=LogisticRegression(C=1e4,max_iter=5000).fit(logit(ct).reshape(-1,1),yt)
            a_t,cc_t=float(lr_t.coef_[0,0]),float(lr_t.intercept_[0])
            s_true_t,b_true_t=1.0/a_t,-cc_t/a_t
            rows.append(dict(src=src,tgt=tgt,arch=arch,seed=seed,K=K,T=T,
                s_hat_cal=s_hat,b_hat_cal=b_hat,
                s_true_ood=s_true_t,b_true_ood=b_true_t,
                pi_l1=np.abs(pi_cal-pi_tst).sum(),
                d_obs=d_obs, e_raw=e_raw,e_ts=e_ts,
                ood_acc=float((tp.argmax(1)==tl).mean()),
                id_acc=float((cp.argmax(1)==cl).mean())))

import pandas as pd
df=pd.DataFrame(rows)
df['dT_from_true']=1.0-df.s_true_ood
df['err_s']=df.s_hat_cal-df.s_true_ood
print(f"n={len(df)}")
print("\n=== 按方向汇总 ===")
g=df.groupby('src').agg(n=('d_obs','size'),pi_l1=('pi_l1','mean'),
    d_obs=('d_obs','mean'),T=('T','mean'),
    s_cal=('s_hat_cal','mean'),s_ood_true=('s_true_ood','mean'),
    err_s=('err_s','mean'),ood_acc=('ood_acc','mean'))
print(g.to_string())
print("\n=== 关键相关性 ===")
for a,b in [('err_s','pi_l1'),('err_s','ood_acc'),('s_hat_cal','s_true_ood'),
            ('d_obs','pi_l1'),('d_obs','ood_acc'),('d_obs','s_true_ood'),
            ('T','ood_acc'),('s_true_ood','ood_acc')]:
    r=np.corrcoef(df[a],df[b])[0,1]
    print(f"  corr({a:>11}, {b:>11}) = {r:+.3f}")
print("\n=== 核心：ŝ(cal估) 能不能预测 s_true(OOD真值)? ===")
print(f"  mean s_hat_cal={df.s_hat_cal.mean():.3f} (std {df.s_hat_cal.std():.3f})")
print(f"  mean s_true_ood={df.s_true_ood.mean():.3f} (std {df.s_true_ood.std():.3f})")
print(f"  err_s 均值={df.err_s.mean():+.3f} |err_s|={df.err_s.abs().mean():.3f}")
print(f"  符号一致率={np.mean(np.sign(df.err_s)>0):.3f}  (>0.5 => s_hat 系统性偏高)")

# 关键：分解增益的真实驱动量
print("\n=== ΔECE 的真实驱动量（哪一个统计量最能解释 d_obs）===")
print(f"  corr(d_obs, 1-T)        = {np.corrcoef(df.d_obs,1-df['T'])[0,1]:+.3f}")
print(f"  corr(d_obs, |s_true-1|) = {np.corrcoef(df.d_obs,np.abs(df.s_true_ood-1))[0,1]:+.3f}")
print(f"  corr(d_obs, e_raw)      = {np.corrcoef(df.d_obs,df.e_raw)[0,1]:+.3f}")
df.to_csv('_recon_D.csv',index=False)
