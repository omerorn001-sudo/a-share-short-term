exec(open("opt2.py").read())
D={"6月":load("feat_jun.pkl"),"7月":load("feat_jul.pkl"),"8月":load("feat_aug.pkl"),"9月":load("feat.pkl")}
fs=["f_r20","f_vtrend","f_turn","f_vol20","f_pos20","7条满足","技术分","资金分","f_main5r"]
print(pd.DataFrame({m:{f:round(A.groupby("T").apply(lambda g:g[f].rank().corr(g.ret3.rank())).mean(),3) for f in fs} for m,A in D.items()}).to_string())
n4=[("f_r20",-1),("f_vtrend",-1),("f_turn",-1),("f_vol20",1)]
S={"原系统7条件":lambda g:g["7条满足"]*100+g["总分"],"低吸v4":lambda g:sum(zr(g,f,s) for f,s in n4)}
A=pd.concat(D.values()); Ts=sorted(A["T"].unique())
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
plt.rcParams["font.sans-serif"]=["Noto Sans SC","Noto Sans CJK SC"]; plt.rcParams["axes.unicode_minus"]=False
fig,ax=plt.subplots(figsize=(10,4.2))
for nm,sc in S.items():
    P={T:g.assign(s=sc(g)).sort_values("s",ascending=False) for T,g in A.groupby("T")}
    eq,i,xs,ys,mx,dd=1.0,0,[Ts[0]],[0],1,0
    while i<len(Ts):
        eq*=1+P[Ts[i]].iloc[0].ret3; i+=3; xs.append(Ts[min(i,len(Ts)-1)]); ys.append((eq-1)*100); mx=max(mx,eq); dd=min(dd,eq/mx-1)
    print(nm,"4个月单仓T3 %.1f%% 最大回撤 %.1f%%"%((eq-1)*100,dd*100))
    ax.plot(xs,ys,marker=".",label=f"{nm}（{ys[-1]:+.1f}%）")
for d in ("2026-07-01","2026-08-01","2026-09-01"): ax.axvline(pd.Timestamp(d),color="lightgray",ls="--")
ax.axhline(0,color="gray",lw=.8); ax.legend(); ax.set_title("6–9月单仓顺序交易：每次只买第1名，T+1开盘买、T+3收盘卖（已扣成本）")
plt.tight_layout(); plt.savefig("eval4.png",dpi=130)
