exec(open("/data/tmp/bt/engine.py").read())
A,mk,t30=pickle.load(open("result.pkl","rb"))
A["gap"]=[O.iloc[dates.get_loc(T)+1][c]/C.at[T,c]-1 for T,c in zip(A["T"],A.code)]
A["intra1"]=[C.iloc[dates.get_loc(T)+1][c]/O.iloc[dates.get_loc(T)+1][c]-1 for T,c in zip(A["T"],A.code)]
P=pd.concat([g.sort_values(["7条满足","总分","amount"],ascending=False).head(10) for _,g in A.groupby("T")])
print("A组 隔夜跳空均值%",round(P.gap.mean()*100,2),"T+1日内(开→收)%",round(P.intra1.mean()*100,2),"| 池",round(A.gap.mean()*100,2),round(A.intra1.mean()*100,2))
# 分日
d=P.groupby("T").agg(次日均涨=("次日涨幅",lambda x:x.mean()*100),T3=("ret3",lambda x:x.mean()*100),命中=("次日前30","sum"),全满足=("买入信号","sum"))
idx=pd.read_csv(data.CACHE_DIR/"index_sh000001.csv",parse_dates=["date"]).set_index("date")["close"]
ma20=idx.rolling(20).mean()
d["上证"]=idx.reindex(d.index).round(0); d["上证在MA20上"]=(idx>ma20).reindex(d.index)
d["池T3"]=A.groupby("T")["ret3"].mean()*100
pass
# 因子 IC（池内，T+3）
fac=["总分","7条满足","资金分","技术满足","技术分","分_主力","分_融资","分_龙虎榜","分_机构持仓","调研分","板块分","基本面分","bias5","gap"]
ic={f:A.groupby("T").apply(lambda g:g[f].astype(float).rank().corr(g["ret3"].rank())).mean() for f in fac}
print("因子与T+3收益的秩相关(日均)",{k:round(v,3) for k,v in ic.items()})
for f in ["7条满足","资金分","技术满足"]:
    print(f, A.groupby(f)["ret3"].agg(["count","mean"]).assign(mean=lambda x:(x["mean"]*100).round(2)).to_dict("index"))
pickle.dump((P,d,ic),open("an2.pkl","wb"))
