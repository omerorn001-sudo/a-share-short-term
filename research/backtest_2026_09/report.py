import pickle, pandas as pd, numpy as np
R,daily,mkt,mk_eq=pickle.load(open("summary.pkl","rb"))
P,d,ic=pickle.load(open("an2.pkl","rb"))
A,mk,t30=pickle.load(open("result.pkl","rb"))
f=lambda x,n=2: "—" if pd.isna(x) else f"{x:+.{n}f}"
L=[]
L.append("| 策略（每个交易日） | 选股次数 | 次日涨幅前30命中 | 次日平均涨幅 | T+2卖 平均 / 胜率 | T+3卖 平均 / 胜率 | T+4卖 平均 / 胜率 | 资金曲线 T+2 / T+3 / T+4 |\n| --- | --- | --- | --- | --- | --- | --- | --- |")
for _,r in R.iterrows():
    L.append(f"| {r['策略']} | {r['选股次数']} | {r['次日涨幅前30命中']} | {f(r['次日平均涨幅%'])}% | {f(r['T+2卖 平均%'])}% / {r['T+2 胜率%']:.0f}% | {f(r['T+3卖 平均%'])}% / {r['T+3 胜率%']:.0f}% | {f(r['T+4卖 平均%'])}% / {r['T+4 胜率%']:.0f}% | {f(r['T+2 资金曲线%'],1)}% / {f(r['T+3 资金曲线%'],1)}% / {f(r['T+4 资金曲线%'],1)}% |")
L.append(f"| 全市场（中位数） | — | — | — | {f(mkt['T+2卖 平均%'])}% | {f(mkt['T+3卖 平均%'])}% | {f(mkt['T+4卖 平均%'])}% | {f(mk_eq[2],1)}% / {f(mk_eq[3],1)}% / {f(mk_eq[4],1)}% |")
open("tab_summary.md","w").write("\n".join(L))
L=["| T日 | 上证 | 上证在MA20上 | 7条全满足只数 | 前10次日平均涨幅 | 前10命中次日前30 | 前10 T+3卖 | 初筛池 T+3卖 | 全市场前30在初筛池 |\n| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
t30=t30.set_index("T")
for T,r in d.iterrows():
    L.append(f"| {T:%m-%d} | {r['上证']:.0f} | {'是' if r['上证在MA20上'] else '否'} | {int(r['全满足'])} | {f(r['次日均涨'])}% | {int(r['命中'])} | {f(r['T3'])}% | {f(r['池T3'])}% | {int(t30.at[T,'前30在初筛池'])}/30 |")
open("tab_daily.md","w").write("\n".join(L))
names={"总分":"总分","7条满足":"7条满足数","资金分":"资金面综合分","技术满足":"技术5条满足数","分_主力":"主力资金分","分_融资":"融资分","分_龙虎榜":"龙虎榜分","分_机构持仓":"机构持仓分","调研分":"调研分","板块分":"板块分","基本面分":"基本面分","bias5":"偏离MA5","gap":"T+1开盘跳空"}
L=["| 因子 | 与 T+3 收益的秩相关（日均） |\n| --- | --- |"]+[f"| {names[k]} | {ic[k]:+.3f} |" for k in names]
open("tab_ic.md","w").write("\n".join(L))
g=A.groupby("7条满足")["ret3"].agg(["count","mean",lambda x:(x>0).mean()])
L=["| 满足条件数 | 样本 | T+3卖 平均 | 胜率 |\n| --- | --- | --- | --- |"]+[f"| {k} | {int(r['count'])} | {r['mean']*100:+.2f}% | {r['<lambda_0>']*100:.0f}% |" for k,r in g.iterrows()]
open("tab_cnt.md","w").write("\n".join(L))
print(open("tab_summary.md").read()); print(open("tab_cnt.md").read())
