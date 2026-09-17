"""侦查E：定位根因——recover_slope_intercept 的估计对象与目标量不匹配

假设：decomposition 在 cal split 上用 (logit(p), correctness) 做 logistic 恢复，
得到的是 **cal split 自身的校准曲线斜率**（≈1，因为 cal 就是训练域，模型已近校准），
而预测 OOD ΔECE 需要的是 **target split 的校准曲线斜率**。
两者是不同分布上的量，因此 ŝ 对 s_OOD 无预测力（corr=-0.03）。

验证：直接看 source/target 校准曲线斜率的差异。
"""
import warnings, numpy as np
from sklearn.linear_model import LogisticRegression
warnings.filterwarnings('ignore')
def logit(p):
    p=np.clip(p,1e-12,1-1e-12); return np.log(p/(1-p))

print("=== 假设1: cal 与 test 的校准曲线斜率确实不同 ===")
print(f"{'方向':>16} {'arch':>13} {'s_cal(binary)':>14} {'s_test(binary)':>15} {'差异':>9}")
diffs=[]
for src,tgt in [('chapman','cpsc'),('cpsc','chapman'),('chapman','ptbxl'),('ptbxl','cpsc')]:
    for arch in ['inceptiontime','resnet1d']:
        z=np.load(f"checkpoints/e2_probs_cache/{src}_{tgt}_{arch}_seed42.npz")
        cp,cl,tp,tl=z['cal_probs'],z['cal_labels'],z['test_probs'],z['test_labels']
        def fit_s(p,y):
            c=p.max(1); yy=(p.argmax(1)==y).astype(float)
            lr=LogisticRegression(C=1e4,max_iter=5000).fit(logit(c).reshape(-1,1),yy)
            a,cc=float(lr.coef_[0,0]),float(lr.intercept_[0])
            return 1.0/a
        sc=fit_s(cp,cl); st=fit_s(tp,tl)
        diffs.append(st-sc)
        print(f"{src+'->'+tgt:>16} {arch:>13} {sc:>14.3f} {st:>15.3f} {st-sc:>+9.3f}")
print(f"\n斜率差异均值 {np.mean(diffs):+.3f}（跨分布量级相当，故 cal 的 ŝ 无外推力）")

print("\n=== 假设2: 关键区分——是'斜率'错了还是'基线'错了？ ===")
print("检查 cal 上恢复的 (ŝ,b̂) 是否能复现 cal 自身的 ECE（拟合优度）")
print("以及它作用到 test 后的预测 ECE vs 真实 ECE")
for src,tgt in [('chapman','cpsc'),('ptbxl','cpsc')]:
    z=np.load(f"checkpoints/e2_probs_cache/{src}_{tgt}_resnet1d_seed42.npz")
    cp,cl,tp,tl=z['cal_probs'],z['cal_labels'],z['test_probs'],z['test_labels']
    def fit_sb(p,y):
        c=p.max(1); yy=(p.argmax(1)==y).astype(float)
        lr=LogisticRegression(C=1e4,max_iter=5000).fit(logit(c).reshape(-1,1),yy)
        a,cc=float(lr.coef_[0,0]),float(lr.intercept_[0])
        return 1.0/a, -cc/a
    s,b=fit_sb(cp,cl)
    st,bt=fit_sb(tp,tl)
    print(f"  {src}->{tgt}: cal(ŝ={s:.3f},b̂={b:+.3f})  test真(s={st:.3f},b={bt:+.3f})  "
          f"→ b̂ 完全无关于 bt (差 {b-bt:+.3f})")

print("\n=== 假设3: 真正可预测 ΔECE 的量是什么？（在 cal 上就能算的） ===")
print("候选: cal上ECE、cal上overconfidence gap、cal-test logit Wasserstein、T")
rows=[]
for src,tgt in [('chapman','cpsc'),('cpsc','chapman'),('chapman','ptbxl'),('ptbxl','chapman'),('cpsc','ptbxl'),('ptbxl','cpsc')]:
    for arch in ['inceptiontime','resnet1d']:
        for seed in [42,43,44,45,46]:
            try: z=np.load(f"checkpoints/e2_probs_cache/{src}_{tgt}_{arch}_seed{seed}.npz")
            except FileNotFoundError: continue
            cp,cl,tp,tl=z['cal_probs'],z['cal_labels'],z['test_probs'],z['test_labels']
            def ece(p,y,nb=10):
                c=p.max(1); corr=(p.argmax(1)==y).astype(float)
                v=0.;n=len(c)
                for i in range(nb):
                    lo,hi=i/nb,(i+1)/nb
                    m=(c>=lo)&(c<hi) if i<nb-1 else (c>=lo)&(c<=hi)
                    if m.sum()==0: continue
                    v+=m.sum()/n*abs(c[m].mean()-corr[m].mean())
                return v
            from src.utils.calibration_methods import fit_temperature_multiclass as ft, apply_temperature_multiclass as ap
            pa=ft(cp,cl)
            d_obs=ece(tp,tl)-ece(ap(tp,pa),tl)
            gap_cal=cp.max(1).mean()-(cp.argmax(1)==cl).astype(float).mean()
            # logit 分布位移
            lc=logit(cp.max(1)); lt=logit(tp.max(1))
            rows.append(dict(src=src,arch=arch,seed=seed,d_obs=d_obs,T=pa['T'],
                gap_cal=float(gap_cal), ece_cal=ece(cp,cl),
                logit_shift=float(lt.mean()-lc.mean()),
                logit_std_ratio=float(lt.std()/lc.std()),
                pred_conf_shift=float(tp.max(1).mean()-cp.max(1).mean())))
import pandas as pd
df=pd.DataFrame(rows)
print(f"n={len(df)}")
for c in ['T','gap_cal','ece_cal','logit_shift','logit_std_ratio','pred_conf_shift']:
    print(f"  corr(d_obs, {c:>16}) = {np.corrcoef(df.d_obs,df[c])[0,1]:+.3f}")
print("\n多元线性回归 (d_obs ~ T + logit_shift + logit_std_ratio + pred_conf_shift):")
X=np.c_[df['T'],df.logit_shift,df.logit_std_ratio,df.pred_conf_shift,np.ones(len(df))]
beta,*_=np.linalg.lstsq(X,df.d_obs.values,rcond=None)
pred=X@beta
ss=1-((df.d_obs-pred)**2).sum()/((df.d_obs-df.d_obs.mean())**2).sum()
print(f"  R²={ss:.3f}  beta={np.round(beta,4)}")
