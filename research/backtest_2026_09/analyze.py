import pickle, pandas as pd, numpy as np
A,mk,t30=pickle.load(open("result.pkl","rb"))
A["次日涨幅"]=A["次日涨幅"]*100
strat={
 "A 7条件打分前10":lambda g:g.sort_values(["7条满足","总分","amount"],ascending=False).head(10),
 "B 总分前10":lambda g:g.sort_values(["总分","7条满足","amount"],ascending=False).head(10),
 "C 仅技术5条打分前10":lambda g:g.sort_values(["技术满足","技术分","amount"],ascending=False).head(10),
 "D 仅7条全满足":lambda g:g[g["买入信号"]],
 "E 初筛池全部":lambda g:g,
}
rows=[];daily={}
for n,f in strat.items():
    P=pd.concat([f(g) for _,g in A.groupby("T")])
    r={"策略":n,"交易日":P["T"].nunique(),"选股次数":len(P),"次日涨幅前30命中":int(P["次日前30"].sum()),
       "次日平均涨幅%":P["次日涨幅"].mean(),"可买入":int(P["可买"].sum())}
    for k in (2,3,4):
        x=P[f"ret{k}"].dropna()
        b=P.groupby("T")[f"ret{k}"].mean().reindex(sorted(A["T"].unique())).fillna(0)
        r[f"T+{k}卖 平均%"]=x.mean()*100; r[f"T+{k} 胜率%"]=(x>0).mean()*100
        r[f"T+{k} 资金曲线%"]=(np.prod(1+b/k)-1)*100
        daily[(n,k)]=b
    rows.append(r)
R=pd.DataFrame(rows)
mkt={f"T+{k}卖 平均%":np.nanmean(mk[k])*100 for k in (2,3,4)}
pd.set_option("display.width",250); pd.set_option("display.max_columns",30)
print(R.round(2).to_string()); print("全市场中位数",{k:round(v,2) for k,v in mkt.items()})
mk_eq={k:(np.prod(1+np.array(mk[k])/k)-1)*100 for k in (2,3,4)}; print("全市场资金曲线",{k:round(v,2) for k,v in mk_eq.items()})
print(t30.assign(T=t30["T"].dt.strftime("%m-%d")).to_string())
pickle.dump((R,daily,mkt,mk_eq),open("summary.pkl","wb"))
