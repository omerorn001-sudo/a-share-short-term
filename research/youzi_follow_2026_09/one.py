"""单持仓：每次只买一只。T日按规则选1只→T+1 10:30买(封板买不到则顺延下一候选)→T+2卖；卖出后才能开下一笔。"""
import pandas as pd, numpy as np
R=pd.read_pickle("R.pkl"); R["T"]=pd.to_datetime(R["T"])
days=sorted(R["T"].unique())
agg=R.groupby(["T","code"]).agg(name=("name","first"),net=("net","sum"),k=("游资","nunique"),blocked=("blocked","first"),
    r_open=("r_open","first"),r_1030=("r_1030","first"),r_close=("r_close","first"),d1=("d1","first"),
    lasa=("游资",lambda x:(x=="拉萨天团").any()),ht=("游资",lambda x:(x=="华泰总部").any())).reset_index()
rules={"净买额最大":lambda d:d.sort_values("net",ascending=False),
       "合力游资最多":lambda d:d.sort_values(["k","net"],ascending=False),
       "仅华泰总部(净买最大)":lambda d:d[d.ht].sort_values("net",ascending=False),
       "排除拉萨天团(净买最大)":lambda d:d[~d.lasa].sort_values("net",ascending=False)}
alld=sorted(set(agg.d1)|set(agg["T"]))
def run(rule,col,rng=None):
    eq=1;tr=[];free=None  # free: 可以再次买入的最早d1
    for T in days:
        d=agg[(agg["T"]==T)&~agg.blocked]
        if rng is not None: d=d.sample(frac=1,random_state=rng.integers(1e9))
        else: d=rules[rule](d)
        if d.empty: continue
        x=d.iloc[0]
        if free is not None and x.d1<free: continue
        r=x[col]; eq*=1+r; tr.append((x.d1.date(),x.code,x["name"],round(r*100,2)))
        i=alld.index(x.d1) if x.d1 in alld else None
        nxt=[t for t in sorted(R.d1.unique()) if t>x.d1]   # T+2
        d2=nxt[0] if nxt else x.d1
        free=d2 if col!="r_close" else (nxt[1] if len(nxt)>1 else d2+pd.Timedelta(days=99))
    return eq,tr
out=[]
for col,lab in [("r_open","T+2开盘卖"),("r_1030","T+2 10:30卖"),("r_close","T+2收盘卖")]:
    for rule in rules:
        eq,tr=run(rule,col); rs=np.array([t[3] for t in tr])
        c=np.cumprod(1+rs/100); dd=(c/np.maximum.accumulate(np.r_[1,c])[1:]-1).min()*100
        out.append(dict(卖出=lab,选股=rule,笔数=len(tr),累计=round((eq-1)*100,1),单笔均值=round(rs.mean(),2),胜率=round((rs>0).mean()*100,0),最大回撤=round(dd,1)))
        if rule=="净买额最大" and col=="r_1030": T0=tr
    rng=np.random.default_rng(0); sims=[run(None,col,rng)[0]-1 for _ in range(300)]
    out.append(dict(卖出=lab,选股="随机1只(300次中位)",笔数=None,累计=round(np.median(sims)*100,1),单笔均值=None,胜率=round((np.array(sims)>0).mean()*100,0),最大回撤=None))
O=pd.DataFrame(out); print(O.to_string(index=False)); O.to_csv("one_stock.csv",index=False)
print("\n净买额最大/10:30卖 逐笔:");[print(*t) for t in T0]
