import pickle, pandas as pd, numpy as np
s=pd.read_pickle("seats_sep.pkl"); det=pd.read_pickle("det_sep.pkl"); K=pickle.load(open("k30.pkl","rb"))
s=s[(s.side=="买")&~s["游资"].isin(["","机构","北向","外资"])&~s.SECURITY_CODE.str.startswith(("4","8","9"))].copy()
s["date"]=pd.to_datetime(s["date"]).dt.normalize()
g=s.groupby(["游资","SECURITY_CODE","date"],as_index=False).agg(BUY=("BUY","sum"),SELL=("SELL","sum"),name=("name","first"))
days=pd.DatetimeIndex(sorted(set(d.normalize() for k in K.values() for d in k.index)))
CB,CS=0.00125,0.00175
def lim(c,n):
    if "ST" in str(n): return .05
    return .2 if c.startswith(("30","68")) else .1
cache={}
def trade(c,T,n):
    key=(c,T)
    if key in cache: return cache[key]
    k=K.get(c); r=None
    if k is not None:
        i=days.searchsorted(T)
        if i<len(days) and days[i]==T and i+2<len(days):
            d1,d2=days[i+1],days[i+2]
            def bar(d,t):
                x=d+pd.Timedelta(t); return k.loc[x] if x in k.index else None
            pc=bar(days[i],"15:00:00"); o1=bar(d1,"10:00:00"); b=bar(d1,"10:30:00"); o2=bar(d2,"10:00:00"); m2=bar(d2,"10:30:00"); c2=bar(d2,"15:00:00")
            if all(v is not None for v in [pc,o1,b,o2,m2,c2]):
                up=round(pc.close*(1+lim(c,n)),2); buy=b.close
                blocked= buy>=up*0.998 and b.low>=up*0.998
                f=lambda p: p/buy*(1-CS)/(1+CB)-1
                r=dict(T1_open_gap=o1.open/pc.close-1, blocked=blocked, r_open=f(o2.open), r_1030=f(m2.close), r_close=f(c2.close), d1=d1, buy_vs_pc=buy/pc.close-1)
    cache[key]=r; return r
rows=[]
for x in g.itertuples():
    r=trade(x.SECURITY_CODE,x.date,x.name)
    if r: rows.append(dict(游资=x.游资,code=x.SECURITY_CODE,name=x.name,T=x.date,net=(x.BUY-x.SELL)/1e4,**r))
R=pd.DataFrame(rows); R.to_pickle("R.pkl")
print("信号",len(g),"可算",len(R),"封板买不到",int(R.blocked.sum()))
E=R[~R.blocked]
def st(df):
    return pd.Series({"n":len(df),"开盘卖%":df.r_open.mean()*100,"1030卖%":df.r_1030.mean()*100,"收盘卖%":df.r_close.mean()*100,"收盘胜率%":(df.r_close>0).mean()*100,"收盘中位%":df.r_close.median()*100})
print("== 全部(席位×股票)\n",st(E).round(2).to_string())
U=E.drop_duplicates(["code","T"]); print("== 按股票去重\n",st(U).round(2).to_string())
cnt=E.groupby(["code","T"]).游资.nunique().rename("k"); E2=E.join(cnt,on=["code","T"])
print("== 合力≥2\n",st(E2[E2.k>=2].drop_duplicates(["code","T"])).round(2).to_string())
top=E.groupby(["T","code"]).net.sum().reset_index().sort_values("net",ascending=False).groupby("T").head(1)
print("== 每日净买第1\n",st(top[["T","code"]].merge(U,on=["T","code"])).round(2).to_string())
by=E.groupby("游资").apply(st).round(2).sort_values("n",ascending=False); print(by.to_string()); by.to_csv("by_seat.csv")
dly=U.groupby("d1").r_close.mean(); print("日度等权收盘卖 累计%",round(((1+dly).prod()-1)*100,2),"正收益天",(dly>0).sum(),"/",len(dly))
print("T+1高开均值%",round(E.T1_open_gap.mean()*100,2),"买价较T收盘%",round(E.buy_vs_pc.mean()*100,2))
