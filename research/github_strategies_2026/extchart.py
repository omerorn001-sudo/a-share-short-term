import pickle, numpy as np, pandas as pd, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
plt.rcParams["font.sans-serif"]=["Noto Sans SC","Noto Sans CJK SC"]; plt.rcParams["axes.unicode_minus"]=False
mon,tot,r,ch=pickle.load(open("extsum.pkl","rb")); o=tot.sort_values("第1名均值",ascending=False).index; mon=mon.loc[o]
fig,ax=plt.subplots(figsize=(11,4.8)); v=mon.values
im=ax.imshow(v,cmap="RdYlGn",vmin=-6,vmax=6,aspect="auto")
ax.set_xticks(range(9),[f"{m}月" for m in mon.columns]); ax.set_yticks(range(len(o)),o)
for i in range(v.shape[0]):
    for j in range(v.shape[1]):
        if not np.isnan(v[i,j]): ax.text(j,i,f"{v[i,j]:+.1f}",ha="center",va="center",fontsize=8)
ax.set_title("每日只买第1名、T+3卖出：各策略月度平均每笔收益%（已扣成本，2026年1–9月）"); plt.colorbar(im,ax=ax,shrink=.8)
plt.tight_layout(); plt.savefig("ext_heat.png",dpi=130)
