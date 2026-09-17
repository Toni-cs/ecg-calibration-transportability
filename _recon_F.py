"""侦查F：决定性实验——LOO cross-fitting 比较若干 ΔECE 预测器

对照（论文现状）：3成分线性模型，mean error +0.29
候选：
  P1: 常数预测（用训练均值）—— 下界/基线
  P2: 3成分线性 (ŝ,b̂,π̂) —— 论文现状（我用 cal-logistic 复刻）
  P3: 仅 T（温度本身）
  P4: cal-ECE（源域误校准量，无需任何恢复）
  P5: T + cal-ECE
  P6: 理论修正：ΔECE ≈ f(cal-ECE, T) 的二维拟合
评估：LOO（留一 cell）预测误差，与论文 +0.29 对比
"""
import json, warnings, itertools
import numpy as np
from sklearn.linear_model import LogisticRegression, LinearRegression
warnings.filterwarnings('ignore')

def logit(p):
    p=np.clip(p,1e-12,1-1e-12); return np.log(p/(1-p))
def sm(z):
    z=z-z.max(-1,keepdims=True); e=np.exp(z); return e/e.sum(-1,keepdims=True)
def ece_mc(p2d,y,nbin=10):
    c=p2d.max(1); corr=(p2d.argmax(1)==y).astype(float)
    v=0.;n=len(c)
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
            cp,cl,tp,tl=z['cal_probs'],z['cal_labels'],z['test_probs'],z['test_labels']
            K=int(z['num_classes'])
            pi_cal=np.bincount(cl,minlength=K)/len(cl); pi_tst=np.bincount(tl,minlength=K)/len(tl)
            from src.utils.calibration_methods import fit_temperature_multiclass as ft, apply_temperature_multiclass as ap
            pa=ft(cp,cl); T=pa['T']
            e_raw=ece_mc(tp,tl); e_ts=ece_mc(ap(tp,pa),tl); d_obs=e_raw-e_ts
            # P2 的输入：cal-logistic 恢复
            ccal=cp.max(1); ycal=(cp.argmax(1)==cl).astype(float)
            lr=LogisticRegression(C=1e4,max_iter=5000).fit(logit(ccal).reshape(-1,1),ycal)
            a,b=float(lr.coef_[0,0]),float(lr.intercept_[0])
            s_hat,b_hat=1.0/a,-b/a
            rows.append(dict(src=src,tgt=tgt,arch=arch,seed=seed,d_obs=d_obs,
                T=T, ece_cal=ece_mc(cp,cl), s_hat=s_hat, b_hat=b_hat,
                pi_l1=np.abs(pi_cal-pi_tst).sum(),
                gap_cal=float(cp.max(1).mean()-ycal.mean()),
                e_raw=e_raw))

import pandas as pd
df=pd.DataFrame(rows).reset_index(drop=True)
print(f"n={len(df)}  d_obs mean={df.d_obs.mean():+.4f} std={df.d_obs.std():.4f}\n")

def loo_eval(feats, name):
    """留一 cell 的 LOO：每次用一个 cell 作测试，其余拟合线性模型"""
    X=df[feats].values if feats else np.zeros((len(df),0)); y=df.d_obs.values
    preds=np.empty(len(df)); 
    for i in range(len(df)):
        m=np.ones(len(df),bool); m[i]=False
        if not feats:
            preds[i]=y[m].mean()
        else:
            lr=LinearRegression().fit(X[m],y[m])
            preds[i]=lr.predict(X[i:i+1])[0]
    err=preds-y
    sign=np.mean(np.sign(preds)==np.sign(y))
    print(f"{name:>28} | mean_err={err.mean():+.4f} | |err|={np.abs(err).mean():.4f} "
          f"| RMSE={np.sqrt((err**2).mean()):.4f} | sign_acc={sign:.3f} | corr={np.corrcoef(preds,y)[0,1]:+.3f}")
    return preds

print("=== LOO cross-fitting: 预测 d_obs ===")
p_const=loo_eval([], 'P1: 常数(训练均值)')
p_full =loo_eval(['s_hat','b_hat','pi_l1'], 'P2: 3成分 (ŝ,b̂,π̂) [论文]')
p_T    =loo_eval(['T'], 'P3: 仅T')
p_ecal =loo_eval(['ece_cal'], 'P4: 仅 cal-ECE')
p_Tecal=loo_eval(['T','ece_cal'], 'P5: T + cal-ECE')
p_all  =loo_eval(['T','ece_cal','s_hat','b_hat','pi_l1'], 'P6: T+calECE+3成分')
p_gap  =loo_eval(['T','gap_cal'], 'P7: T + cal-overconf-gap')
p_T2   =loo_eval(['T','ece_cal','gap_cal'], 'P8: T+calECE+gap')

print("\n=== 按方向分组 LOO (看是否有方向特异性) ===")
# 方向内 LOO（同方向内留一，仅 10 cell）
for name,feats in [('P2:3成分',['s_hat','b_hat','pi_l1']),('P5:T+calECE',['T','ece_cal'])]:
    allerr=[]
    for s,g in df.groupby('src'):
        g=g.reset_index(drop=True); X=g[feats].values; y=g.d_obs.values
        pr=np.empty(len(g))
        for i in range(len(g)):
            m=np.ones(len(g),bool); m[i]=False
            pr[i]=LinearRegression().fit(X[m],y[m]).predict(X[i:i+1])[0]
        allerr.extend((pr-y).tolist())
    allerr=np.array(allerr)
    print(f"  方向内LOO {name:>12}: mean_err={allerr.mean():+.4f} |err|={np.abs(allerr).mean():.4f} RMSE={np.sqrt((allerr**2).mean()):.4f}")
df.to_csv('_recon_F.csv',index=False)
