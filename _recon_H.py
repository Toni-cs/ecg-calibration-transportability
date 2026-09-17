"""侦查H：最有希望的真实算法方向验证

核心洞察（来自侦查D/E/F）：
- 失败原因不是"估计量不准"，而是**用源域(cal)恢复的(s,b)去外推目标域**，
  而 cal→target 的校准曲线斜率变化可达 1→87（非线性、不可外推）。
- d_obs 与 ood_acc 相关 -0.814，与 ece_cal 相关 +0.637，与 T 相关 +0.688。
  => ΔECE 的本质是"目标域判别力下降 × 源域误校准"的交互，不是 s,b 的线性泛函。

方向：**同方向内可预测性远高于跨方向**（方向内 LOO |err|=0.0235 vs 跨方向 0.0805，
3.4×）。因为同方向共享 target 语料，其校准结构相似。

测试：分级贝叶斯/混合效应式的"方向内池化"预测器能否实质改进?
  - 完全池化（跨方向）：|err|=0.0805 (P2)
  - 方向内 LOO：|err|=0.0235
  - 真实场景：新方向无数据 → 必须跨方向泛化。这是可证伪的边界。
"""
import numpy as np, pandas as pd, warnings
from sklearn.linear_model import LinearRegression
warnings.filterwarnings('ignore')
df=pd.read_csv('_recon_F.csv')
y=df.d_obs.values

def loo(featsX, name, groups=None):
    X=featsX; pr=np.empty(len(df)); nf=X.shape[1]
    def make(m):
        return LinearRegression().fit(X[m],y[m]) if nf else None
    if groups is None:
        for i in range(len(df)):
            m=np.ones(len(df),bool); m[i]=False
            pr[i]=make(m).predict(X[i:i+1])[0] if nf else y[m].mean()
    else:
        for g in df[groups].unique():
            idx=df.index[df[groups]==g].values
            for i in idx:
                m=np.ones(len(df),bool); m[i]=False
                pr[i]=make(m).predict(X[i:i+1])[0] if nf else y[m].mean()
    err=pr-y
    print(f"{name:>34} | mean={err.mean():+.4f} |err|={np.abs(err).mean():.4f} RMSE={np.sqrt((err**2).mean()):.4f}")
    return pr

print("=== 相对论文 +0.29 的改进幅度 ===")
print(f"{'论文报告 (JSON delta_pred)':>34} | mean=+0.2910 与真值差=+0.1867 |err|未报")
print()
print("=== 诚实基线 ===")
loo(np.zeros((len(df),0)), '常数(全局均值)')
print()
print("=== 可用的真实特征（全部可在无目标标签下算）===")
# 加入新的无标签特征
def extra(r):
    z=np.load(f"checkpoints/e2_probs_cache/{r.src}_{r.tgt}_{r.arch}_seed{int(r.seed)}.npz")
    cp,cl,tp,tl=z['cal_probs'],z['cal_labels'],z['test_probs'],z['test_labels']
    # 目标域熵（无需标签）
    ent=-(tp*np.log(np.clip(tp,1e-12,1))).sum(1).mean()
    ent_cal=-(cp*np.log(np.clip(cp,1e-12,1))).sum(1).mean()
    return pd.Series(dict(ent_tgt=ent, ent_cal=ent_cal, ent_ratio=ent/ent_cal,
        conf_tgt=tp.max(1).mean(), conf_cal=cp.max(1).mean()))
ex=df.apply(extra,axis=1)
df=pd.concat([df,ex],axis=1)
df.to_csv('_recon_H.csv',index=False)

F_sets={
 'A: 3成分(论文)':      ['s_hat','b_hat','pi_l1'],
 'B: 仅T':              ['T'],
 'C: T+calECE':         ['T','ece_cal'],
 'D: T+calECE+ent_ratio':['T','ece_cal','ent_ratio'],
 'E: T+calECE+conf_tgt': ['T','ece_cal','conf_tgt'],
 'F: T+ent_ratio+conf_tgt':['T','ent_ratio','conf_tgt'],
 'G: 全部无标签特征':    ['T','ece_cal','ent_ratio','conf_tgt','conf_cal','gap_cal','pi_l1'],
 'H: 全部+3成分':        ['T','ece_cal','ent_ratio','conf_tgt','conf_cal','gap_cal','pi_l1','s_hat','b_hat'],
}
for n,f in F_sets.items(): loo(df[f].values, n)

print("\n=== 关键：新方向(留一方向)泛化 —— 最诚实的评估 ===")
for n,f in list(F_sets.items()):
    loo(df[f].values, n, groups='src')
