exec(open("opt2.py").read())
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
plt.rcParams["font.sans-serif"]=["Noto Sans SC","Noto Sans CJK SC"]; plt.rcParams["axes.unicode_minus"]=False
n4=[("f_r20",-1),("f_vtrend",-1),("f_turn",-1),("f_vol20",1)]
SC={"原系统 7条件":lambda g:g["7条满足"]*100+g["总分"],"低吸v4 4因子":lambda g:sum(zr(g,f,s) for f,s in n4)}
A=pd.concat([D["8月"],D["9月"]]); Ts=sorted(A["T"].unique())
fig,ax=plt.subplots(1,2,figsize=(13,4.6))
for nm,sc in SC.items():
    picks={T:g.assign(s=sc(g)).sort_values("s",ascending=False) for T,g in A.groupby("T")}
    eq,i,xs,ys=1.0,0,[Ts[0]],[0]
    while i+3<len(Ts)+3 and i<len(Ts):
        eq*=1+picks[Ts[i]].iloc[0].ret3; i+=3; xs.append(Ts[min(i,len(Ts)-1)]); ys.append((eq-1)*100)
    ax[0].plot(xs,ys,marker="o",label=f"{nm}（{ys[-1]:+.1f}%）")
    b=[]
    for a,bb in ((0,1),(1,3),(3,10),(10,30),(-30,None)):
        b.append(np.mean([p.iloc[a:bb].ret3.mean() for p in picks.values()])*100)
    ax[1].bar(np.arange(5)+(0 if nm.startswith("原") else 0.4),b,0.4,label=nm)
ax[0].axhline(0,color="gray",lw=.8); ax[0].set_title("单仓顺序交易：每次只买第1名，T+3卖（8-03~9-29，已扣成本）"); ax[0].legend(); ax[0].tick_params(axis="x",rotation=30)
ax[1].set_xticks(np.arange(5)+0.2,["第1名","第2-3","第4-10","第11-30","末30"]); ax[1].axhline(0,color="gray",lw=.8)
ax[1].set_title("按排名分组的平均 T+3 收益%（8+9月）"); ax[1].legend()
plt.tight_layout(); plt.savefig("opt_v4.png",dpi=130); print("ok")
