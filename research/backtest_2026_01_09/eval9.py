exec(open("opt2.py").read())
M=[("1月","jan"),("2月","feb"),("3月","mar"),("4月","apr"),("5月","may"),("6月","jun"),("7月","jul"),("8月","aug"),("9月","")]
D={m:load(f"feat_{s}.pkl" if s else "feat.pkl") for m,s in M}
RS={m:pickle.load(open(f"result_{s}.pkl" if s else "result.pkl","rb"))[1] for m,s in M}
n4=[("f_r20",-1),("f_vtrend",-1),("f_turn",-1),("f_vol20",1)]
S={"原系统":lambda g:g["7条满足"]*100+g["总分"],"低吸v4":lambda g:sum(zr(g,f,s) for f,s in n4)}
rows=[]
for m,A in D.items():
    r={"月":m,"交易日":A["T"].nunique(),"市场中位T3":np.mean(RS[m][3])*100,"池均T3":A.ret3.mean()*100}
    for nm,sc in S.items():
        o=run(A,sc,None); r[f"{nm}T3"]=o["T3top1"]; r[f"{nm}胜率"]=o["T3胜率"]; r[f"{nm}前10"]=o["T3top10"]; r[f"{nm}单仓"]=o["T3单仓"]; r[f"{nm}T2"]=o["T2top1"]; r[f"{nm}T4"]=o["T4top1"]
    rows.append(r)
R=pd.DataFrame(rows).round(2); pd.set_option("display.width",300); pd.set_option("display.max_columns",40); print(R.to_string())
fs=["f_r20","f_vtrend","f_turn","f_vol20","f_pos20","7条满足","技术分","资金分"]
print(pd.DataFrame({m:{f:round(A.groupby("T").apply(lambda g:g[f].rank().corr(g.ret3.rank())).mean(),3) for f in fs} for m,A in D.items()}).to_string())
A=pd.concat(D.values()); Ts=sorted(A["T"].unique())
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
plt.rcParams["font.sans-serif"]=["Noto Sans SC","Noto Sans CJK SC"]; plt.rcParams["axes.unicode_minus"]=False
fig,ax=plt.subplots(figsize=(12,4.4)); summ={}
for nm,sc in S.items():
    P={T:g.assign(s=sc(g)).sort_values("s",ascending=False) for T,g in A.groupby("T")}
    r1=[P[T].iloc[0].ret3 for T in Ts]
    eq,i,xs,ys,mx,dd,n,w=1.0,0,[Ts[0]],[0],1,0,0,0
    while i<len(Ts):
        r=P[Ts[i]].iloc[0].ret3; eq*=1+r; n+=1; w+=r>0; i+=3; xs.append(Ts[min(i,len(Ts)-1)]); ys.append((eq-1)*100); mx=max(mx,eq); dd=min(dd,eq/mx-1)
    summ[nm]=dict(日均第1名T3=np.mean(r1)*100,胜率=np.mean(np.array(r1)>0)*100,单仓=(eq-1)*100,最大回撤=dd*100,笔数=n,正收益月=int((R[f"{nm}T3"]>0).sum()))
    ax.plot(xs,ys,marker=".",label=f"{nm}（{ys[-1]:+.1f}%）")
print(pd.DataFrame(summ).round(2).to_string())
for d in pd.date_range("2026-02-01","2026-09-01",freq="MS"): ax.axvline(d,color="lightgray",ls="--",lw=.8)
ax.axhline(0,color="gray",lw=.8); ax.legend(); ax.set_title("2026年1–9月单仓顺序交易：每次只买第1名，T+1开盘买、T+3收盘卖（已扣成本）")
plt.tight_layout(); plt.savefig("eval9.png",dpi=130); pickle.dump((R,summ),open("eval9.pkl","wb"))
