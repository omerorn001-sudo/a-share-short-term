import pickle, pandas as pd, numpy as np, sys
def load(fn):
    A=pickle.load(open(fn,"rb")); return A[A["可买"]].copy()
D={"9月":load("feat.pkl"),"8月":load("feat_aug.pkl")}
def zr(g,f,s): return g[f].rank(pct=True)*s
def run(A,score,filt):
    Ts=sorted(A["T"].unique()); picks={}
    for T,g in A.groupby("T"):
        if filt is not None: g=g[filt(g)]
        picks[T]=g.assign(s=score(g)).sort_values("s",ascending=False) if len(g) else g
    o={}
    for k in (2,3,4):
        r1=[p.iloc[0][f"ret{k}"] for p in picks.values() if len(p)]
        r10=[p.head(10)[f"ret{k}"].mean() for p in picks.values() if len(p)]
        o[f"T{k}top1"]=np.mean(r1)*100; o[f"T{k}胜率"]=np.mean(np.array(r1)>0)*100; o[f"T{k}top10"]=np.mean(r10)*100
        eq,i,n=1.0,0,0
        while i<len(Ts):
            p=picks[Ts[i]]
            if len(p)==0: i+=1; continue
            eq*=1+p.iloc[0][f"ret{k}"]; n+=1; i+=k
        o[f"T{k}单仓"]=(eq-1)*100
    o["可选日"]=sum(1 for p in picks.values() if len(p))
    return o
