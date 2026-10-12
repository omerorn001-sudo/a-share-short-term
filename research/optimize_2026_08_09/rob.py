exec(open("opt2.py").read())
n4=[("f_r20",-1),("f_vtrend",-1),("f_turn",-1),("f_vol20",1)]
sc=lambda g:sum(zr(g,f,s) for f,s in n4)
for fn in ("result.pkl","result_aug.pkl"):
    A,mk,_=pickle.load(open(fn,"rb")); print(fn,"市场中位T2/3/4",[round(np.mean(mk[k])*100,2) for k in (2,3,4)])
for m,A in D.items():
    G=[g.assign(s=sc(g)).sort_values("s",ascending=False).reset_index(drop=True) for _,g in A.groupby("T")]
    print(m,"名次1-10/11-30/末30 T3:",[round(np.mean([g.iloc[a:b].ret3.mean() for g in G])*100,2) for a,b in ((0,1),(1,3),(3,10),(10,30),(-30,None))])
    t1=pd.DataFrame([{**g.iloc[0][["T","code","f_r20","f_turn","f_vtrend","f_vol20"]].to_dict(),"ret3":g.iloc[0].ret3} for g in G])
    t1["wk"]=pd.to_datetime(t1["T"]).dt.isocalendar().week
    print(" 周度top1 T3均值%",t1.groupby("wk").ret3.mean().mul(100).round(2).tolist(),"最差",round(t1.ret3.min()*100,1),"最好",round(t1.ret3.max()*100,1))
    print(" top1特征中位: r20 %.3f turn %.2f vtrend %.2f vol20 %.3f"%tuple(t1[["f_r20","f_turn","f_vtrend","f_vol20"]].median()))
    # 参数敏感: 去掉一个因子
    for drop in n4:
        ff=[x for x in n4 if x!=drop]; o=run(A,lambda g:sum(zr(g,f,s) for f,s in ff),None)
        print("  去掉",drop[0],"T3top1 %.2f top10 %.2f"%(o["T3top1"],o["T3top10"]))
