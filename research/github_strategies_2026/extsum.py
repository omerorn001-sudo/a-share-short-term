import pickle, numpy as np, pandas as pd
X=pickle.load(open("ext_rows.pkl","rb")); X["m"]=pd.to_datetime(X["T"]).dt.month
al,ch=pickle.load(open("alpha_rows.pkl","rb")); al["m"]=pd.to_datetime(al["T"]).dt.month; al["策略"]="AlphaGPT式滚动挖掘(#10)"
exec(open("opt2.py").read())
M=[(1,"jan"),(2,"feb"),(3,"mar"),(4,"apr"),(5,"may"),(6,"jun"),(7,"jul"),(8,"aug"),(9,"")]
n4=[("f_r20",-1),("f_vtrend",-1),("f_turn",-1),("f_vol20",1)]
own=[]
for m,s in M:
    A=load(f"feat_{s}.pkl" if s else "feat.pkl")
    for nm,sc in (("原7条件",lambda g:g["7条满足"]*100+g["总分"]),("低吸v4",lambda g:sum(zr(g,f,s) for f,s in n4))):
        for T,g in A.groupby("T"):
            g=g.assign(s=sc(g)).sort_values("s",ascending=False); own.append({"策略":nm,"T":T,"m":m,"top1_3":g.ret3.iloc[0],"top10_3":g.ret3.head(10).mean(),"all_3":g.ret3.mean(),"top1_2":g.ret2.iloc[0],"top1_4":g.ret4.iloc[0]})
own=pd.DataFrame(own)
db=X[X.策略.str.startswith("打板")].copy(); db["top1_3"]=db["top1"]; db["top10_3"]=db["top10"]; db["all_3"]=db["all"]
Y=pd.concat([own,X[~X.策略.str.startswith("打板")],al,db],ignore_index=True)
mon=Y.pivot_table(index="策略",columns="m",values="top1_3",aggfunc="mean")*100
tot=Y.groupby("策略").agg(第1名均值=("top1_3","mean"),第1名中位=("top1_3","median"),胜率=("top1_3",lambda x:(x>0).mean()),前10均值=("top10_3","mean"),全部信号均值=("all_3","mean"),天数=("top1_3","count"))
tot[["第1名均值","第1名中位","前10均值","全部信号均值"]]*=100; tot["胜率"]*=100
tot["正收益月"]=(mon>0).sum(axis=1)
pd.set_option("display.width",250); print(mon.round(2).to_string()); print(tot.round(2).sort_values("第1名均值",ascending=False).to_string())
# 小市值原生：每日开盘调仓 top10，开盘→次日开盘，含/不含成本
P=pickle.load(open("ext_picks.pkl","rb"))[1]["小市值(#19)"]
import pickle as pk
K=pk.load(open("kpanel420.pkl","rb")); O=pd.DataFrame({c:d["open"] for c,d in K.items()}).sort_index(); dates=O.index
r=[]; prev=set()
for T,p in P.items():
    i=dates.get_loc(T); top=list(p.index[:10]); rr=(O.iloc[i+2][top]/O.iloc[i+1][top]-1).mean()
    chg=len(set(top)-prev)/10; prev=set(top); r.append((T,rr,rr-chg*(0.00025*2+0.0005+0.002)))
r=pd.DataFrame(r,columns=["T","gross","net"]); print("小市值原生(每日开盘调仓Top10) 日均毛%.3f%% 净%.3f%% 累计净%.1f%%"%(r.gross.mean()*100,r.net.mean()*100,((1+r.net).prod()-1)*100))
print("打板 T+1开盘卖 第1名均值 %.2f%% 全部 %.2f%%"%(db.top1_open.mean()*100, np.nan))
pickle.dump((mon,tot,r,ch),open("extsum.pkl","wb"))
