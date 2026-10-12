exec(open("opt2.py").read())
M=[("1月","jan"),("2月","feb"),("3月","mar"),("4月","apr"),("5月","may"),("6月","jun"),("7月","jul"),("8月","aug"),("9月","")]
A=pd.concat([load(f"feat_{s}.pkl" if s else "feat.pkl") for m,s in M]); Ts=sorted(A["T"].unique())
n4=[("f_r20",-1),("f_vtrend",-1),("f_turn",-1),("f_vol20",1)]
S={"原系统":lambda g:g["7条满足"]*100+g["总分"],"低吸v4":lambda g:sum(zr(g,f,s) for f,s in n4)}
for nm,sc in S.items():
    P={T:g.assign(s=sc(g)).sort_values("s",ascending=False) for T,g in A.groupby("T")}
    r1=pd.Series([P[T].iloc[0].ret3 for T in Ts])
    out=[]
    for off in (0,1,2):
        eq=np.prod([1+(x if pd.notna(x) else 0) for x in r1.iloc[off::3]]); out.append(round((eq-1)*100,1))
    print(nm,"第1名T3日均 %.2f%% 中位 %.2f%%"%(r1.mean()*100,r1.median()*100),"三种起始日单仓",out,"top10日均 %.2f"%(np.mean([P[T].head(10).ret3.mean() for T in Ts])*100))
