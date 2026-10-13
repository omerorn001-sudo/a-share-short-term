"""AlphaGPT 式滚动因子挖掘（用其本地因子模板随机生成，按前 2 个月 IC 选 5 个，下月样本外使用）。池=初筛池。"""
import pickle, random, numpy as np, pandas as pd
M=["jan","feb","mar","apr","may","jun","jul","aug",""]
A=pd.concat([pickle.load(open(f"feat_{s}.pkl" if s else "feat.pkl","rb")) for s in M],ignore_index=True)
A=A[A["可买"]].copy(); A["m"]=pd.to_datetime(A["T"]).dt.month
feats=[c for c in A.columns if c.startswith("f_") and c not in ("f_gap1","f_org")]
# 每日截面百分位化，便于组合
for f in feats: A["r_"+f]=A.groupby("T")[f].rank(pct=True)
random.seed(42); fs=["r_"+f for f in feats]
tmpl=[lambda a,b,c:(f"{a}+{b}*{c}",lambda d:d[a]+d[b]*d[c]),
      lambda a,b,c:(f"NEG({a})*{b}",lambda d:-d[a]*d[b]),
      lambda a,b,c:(f"{a}/({b}+1e-6)",lambda d:d[a]/(d[b]+1e-6)),
      lambda a,b,c:(f"({a}*{b})/({c}+1e-6)",lambda d:d[a]*d[b]/(d[c]+1e-6)),
      lambda a,b,c:(f"{a}-{b}",lambda d:d[a]-d[b])]
lib=[]
for _ in range(400):
    a,b,c=random.sample(fs,3); lib.append(random.choice(tmpl)(a,b,c))
lib+= [(f,lambda d,f=f:d[f]) for f in fs]
for j,(nm,fn) in enumerate(lib): A[f"x{j}"]=fn(A)
xs=[f"x{j}" for j in range(len(lib))]
def ic(df,x): return df.groupby("T").apply(lambda g:g[x].rank().corr(g.ret3.rank())).mean()
out=[]; chosen={}
Ts=sorted(A["T"].unique())
for m in range(3,10):
    tr=A[A.m.isin([m-2,m-1])]; last=sorted(tr["T"].unique())[:-3]; tr=tr[tr["T"].isin(last)]   # 去掉最后3天，避免标签穿越
    ics=pd.Series({x:ic(tr,x) for x in xs}); top=ics.abs().sort_values(ascending=False).head(5).index
    chosen[m]=[(lib[int(x[1:])][0],round(ics[x],3)) for x in top]
    te=A[A.m==m].copy(); te["s"]=sum(te.groupby("T")[x].rank(pct=True)*np.sign(ics[x]) for x in top)
    for T,g in te.groupby("T"):
        g=g.sort_values("s",ascending=False); out.append({"T":T,"top1_3":g.ret3.iloc[0],"top10_3":g.ret3.head(10).mean(),"top1_2":g.ret2.iloc[0],"top1_4":g.ret4.iloc[0],"n":len(g)})
pickle.dump((pd.DataFrame(out),chosen),open("alpha_rows.pkl","wb"))
for m,v in chosen.items(): print(m,v[:3])
