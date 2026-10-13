"""GitHub 5 个策略在 2026-01~09 的统一回测：T 收盘出信号，T+1 开盘买（开盘涨停不买），T+3 收盘卖，扣成本。"""
import pickle, numpy as np, pandas as pd, random
P=pickle.load(open("/data/tmp/bt/kpanel420.pkl","rb")); sp=pickle.load(open("/data/tmp/bt/spot.pkl","rb"))
O,H,L,C,V=[pd.DataFrame({c:d[k] for c,d in P.items()}).sort_index() for k in ["open","high","low","close","volume"]]
dates=C.index; cols=C.columns
ts=(sp["total_mv"]/sp["price"]).reindex(cols); fs=(sp["float_mv"]/sp["price"]).reindex(cols)
name=sp["name"].reindex(cols).fillna("")
TMV=C*ts; FMV=C*fs; AMT=V*(O+H+L+C)/4; PCT=C/C.shift(1)-1
lim=pd.Series([0.2 if c.startswith(("300","301","688","689")) else 0.1 for c in cols],index=cols)
LUP=(C.shift(1)*(1+lim)).round(2)          # 当日涨停价
isLU=C>=LUP-0.005
okname=~name.str.contains("ST|退"); notbj=pd.Series([not c.startswith(("4","8","9")) for c in cols],index=cols)
age=C.notna().cumsum()
COST_B=0.00025+0.001; COST_S=0.00025+0.0005+0.001
Ts=sorted(set(T for s in ["jan","feb","mar","apr","may","jun","jul","aug",""] for T in pickle.load(open(f"cands_{s}.pkl" if s else "cands.pkl","rb"))[0]))
def fwd(T,k):
    i=dates.get_loc(T); ent=O.iloc[i+1]; ok=(ent>0)&(ent<LUP.iloc[i+1]*0.998)
    if i+k>=len(dates): return pd.Series(np.nan,index=cols)
    r=(C.iloc[i+k]*(1-COST_S))/(ent*(1+COST_B))-1; return r.where(ok)
R={k:{T:fwd(T,k) for T in Ts} for k in (2,3,4)}
base=lambda T: okname&notbj&(age.loc[T]>=120)&(AMT.loc[T]>0)
# ---- 1 碗口反弹 ----
def ema(x,n): return x.ewm(span=n,adjust=False).mean()
STT=ema(ema(C,10),10); BBL=(C.rolling(14).mean()+C.rolling(28).mean()+C.rolling(57).mean()+C.rolling(114).mean())/4
LLV9=L.rolling(9).min(); HHV9=H.rolling(9).max(); RSV=(C-LLV9)/(HHV9-LLV9)*100
K=RSV.ewm(alpha=1/3,adjust=False).mean(); D=K.ewm(alpha=1/3,adjust=False).mean(); J=3*K-2*D
key=(V>=V.shift(1)*4)&(C>O)&(TMV>4e9)
abn=key.rolling(15).max()>0
# 最大量那天是阴线则剔除
vmax_idx=V.rolling(15).apply(np.argmax,raw=True)
def bowl(T):
    i=dates.get_loc(T); m=base(T)&(STT.loc[T]>BBL.loc[T])&(J.loc[T]<=30)&abn.loc[T]&(J.iloc[i-29:i+1].abs().mean()<=80)
    c=C.loc[T]; cat=pd.Series(0,index=cols)
    cat[(c>=BBL.loc[T])&(c<=STT.loc[T])]=3
    cat[(cat==0)&(c.between(BBL.loc[T]*0.97,BBL.loc[T]*1.03))]=2
    cat[(cat==0)&(c.between(STT.loc[T]*0.98,STT.loc[T]*1.02))]=1
    m&=cat>0
    cs=[x for x in m[m].index]
    keep=[]
    for x in cs:
        w=slice(i-14,i+1); vv=V[x].iloc[w]; j=int(np.nanargmax(vv.values)); 
        if C[x].iloc[w].iloc[j]>=O[x].iloc[w].iloc[j]: keep.append(x)
    s=(cat[keep]*1000-J.loc[T,keep]); return s.sort_values(ascending=False)
# ---- 2 小市值 ----
def small(T):
    i=dates.get_loc(T); m=base(T)&pd.Series([c.startswith(("00","60")) for c in cols],index=cols)&(O.iloc[i+1]>=1.8)
    return (-TMV.loc[T][m]).dropna().sort_values(ascending=False)
# ---- 3 打板（日线近似：T 日盘中触及涨停价即以涨停价买入，T+1 收盘卖）----
def daban(T):
    i=dates.get_loc(T); m=base(T)&(H.loc[T]>=LUP.loc[T]-0.005)&(O.loc[T]<LUP.loc[T]-0.005)&(~isLU.iloc[i-1])
    return (-FMV.loc[T][m]).dropna().sort_values(ascending=False)
def daban_ret(T,k=1,at="close"):
    i=dates.get_loc(T); ent=LUP.loc[T]; ex=(C if at=="close" else O).iloc[i+k]
    return (ex*(1-COST_S))/(ent*(1+COST_B))-1
# ---- 4 quantdash matcher_b：近 2~6 日内有涨停、今日站上 MA5 且涨幅≤5% ----
MA5=C.rolling(5).mean(); big=PCT>0.095
def qd_b(T):
    i=dates.get_loc(T); hl=big.iloc[i-6:i-1].any(); m=base(T)&(C.loc[T]>=MA5.loc[T])&(PCT.loc[T]<=0.05)&hl
    return AMT.loc[T][m].sort_values(ascending=False)
# ---- 5 quantdash matcher_d：涨停→次日放量上影(E日)→1~7日内缩量(≤E日量50%)且不破涨停日低点 ----
E=isLU.shift(1,fill_value=False)&(H>C)&(V>V.shift(1))
def qd_d(T):
    i=dates.get_loc(T); out={}
    m=base(T)
    for x in m[m].index:
        e=E[x].iloc[i-7:i]  # 最近8日内（不含今日？原代码 gap>=1）
        if not e.any(): continue
        if not isLU[x].iloc[i-7:i+1].any(): continue
        le=e[e].index[-1]; li=dates.get_loc(le); gap=i-li
        if gap<1 or gap>7: continue
        if L[x].iloc[i]>=L[x].iloc[li-1] and V[x].iloc[i]<=V[x].iloc[li]*0.5: out[x]=AMT[x].iloc[i]
    return pd.Series(out,dtype=float).sort_values(ascending=False)
S={"碗口反弹(#5)":bowl,"小市值(#19)":small,"quantdash涨停回踩MA5(#14-B)":qd_b,"quantdash涨停缩量回踩(#14-D)":qd_d,"打板-首板(#7)":daban}
picks={nm:{} for nm in S}
for T in Ts:
    for nm,f in S.items(): picks[nm][T]=f(T)
pickle.dump((Ts,picks),open("ext_picks.pkl","wb"))
rows=[]
for nm in S:
    for T in Ts:
        p=picks[nm][T]
        if nm.startswith("打板"):
            r=daban_ret(T).reindex(p.index); r2=daban_ret(T,1,"open").reindex(p.index)
            rows.append({"策略":nm,"T":T,"n":len(p),"top1":r.iloc[0] if len(p) else np.nan,"top10":r.head(10).mean() if len(p) else np.nan,"all":r.mean() if len(p) else np.nan,"top1_open":r2.iloc[0] if len(p) else np.nan})
            continue
        d={"策略":nm,"T":T,"n":len(p)}
        for k in (2,3,4):
            r=R[k][T].reindex(p.index).dropna()   # 开盘涨停买不到 → 顺延
            d[f"top1_{k}"]=r.iloc[0] if len(r) else np.nan; d[f"top10_{k}"]=r.head(10).mean() if len(r) else np.nan; d[f"all_{k}"]=r.mean() if len(r) else np.nan
        rows.append(d)
X=pd.DataFrame(rows); pickle.dump(X,open("ext_rows.pkl","wb")); print(X.groupby("策略").agg(日均信号=("n","mean")).round(1))
