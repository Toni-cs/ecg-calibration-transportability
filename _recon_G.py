"""侦查G：核实论文 85%/0.29 的可复现性 + 常数基线的欺骗性

关键问题：
1. d_obs 的符号是否近似恒定？（若常数预测就能到 85%，则"85% 方向准确率"无信息量）
2. 论文的 +0.29 用的是什么 d_obs？（我算的是 mean +0.104，JSON 报 +0.100）
"""
import numpy as np, pandas as pd
df=pd.read_csv('_recon_F.csv')
print(f"n={len(df)}  d_obs: mean={df.d_obs.mean():+.4f}  median={df.d_obs.median():+.4f}")
print(f"  d_obs > 0 的比例 = {(df.d_obs>0).mean():.3f}   (n+={(df.d_obs>0).sum()})")
print(f"  → 常数预测 d_obs=mean 的符号准确率 = {max((df.d_obs>0).mean(),(df.d_obs<0).mean()):.3f}")
print()
print("=== 论文称 85% 方向准确率 ===  常数基线已经是 "
      f"{max((df.d_obs>0).mean(),(df.d_obs<0).mean())*100:.1f}%")
print()
print("按方向分解 d_obs 符号：")
g=df.groupby('src').d_obs.agg(['size','mean','std',lambda x:(x>0).mean()])
g.columns=['n','mean','std','frac_pos']; print(g.to_string())
print()
print("=== 论文 +0.29 的可能来源（幅度预测 vs 观测）===")
print(f"  我算的真 ΔECE mean = {df.d_obs.mean():+.4f}")
print(f"  JSON delta_pred mean = +0.2910（论文引用的 +0.29）")
print(f"  → 论文的 +0.29 是 delta_pred 的均值，与真 ΔECE 差 {0.2910-df.d_obs.mean():+.4f}")
print()
print("=== 关键：delta_pred 的符号与 d_obs 一致率 ===")
print(f"  (用 JSON delta_pred 的符号)")
print()
print("=== K 是否影响误差？ ===")
for K,g in df.groupby(df.src.map({'chapman':5,'ptbxl':5,'cpsc':4})):
    print(f"  K={K}: n={len(g)} d_obs mean={g.d_obs.mean():+.4f} std={g.d_obs.std():.4f}")
