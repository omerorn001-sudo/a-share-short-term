exec(open("opt2.py").read())
D={"6月":load("feat_jun.pkl"),"7月":load("feat_jul.pkl"),"8月":load("feat_aug.pkl"),"9月":load("feat.pkl")}
n4=[("f_r20",-1),("f_vtrend",-1),("f_turn",-1),("f_vol20",1)]
S={"原系统7条件":lambda g:g["7条满足"]*100+g["总分"],"低吸v4":lambda g:sum(zr(g,f,s) for f,s in n4)}
rows=[]
for m,A in D.items():
    for nm,sc in S.items():
        o=run(A,sc,None); rows.append({"月":m,"方案":nm,**{k:round(v,2) for k,v in o.items()}})
    rows.append({"月":m,"方案":"池内全买","T3top1":round(A.ret3.mean()*100,2),"T2top1":round(A.ret2.mean()*100,2),"T4top1":round(A.ret4.mean()*100,2)})
R=pd.DataFrame(rows); pd.set_option("display.width",300); pd.set_option("display.max_columns",40); print(R.to_string())
for fn,m in (("result_jun.pkl","6月"),("result_jul.pkl","7月")):
    A,mk,_=pickle.load(open(fn,"rb")); print(m,"市场中位T2/3/4",[round(np.mean(mk[k])*100,2) for k in (2,3,4)])
for m,A in D.items():
    for nm,sc in S.items():
        G=[g.assign(s=sc(g)).sort_values("s",ascending=False) for _,g in A.groupby("T")]
        print(m,nm,"分组T3",[round(np.mean([g.iloc[a:b].ret3.mean() for g in G])*100,2) for a,b in ((0,1),(1,3),(3,10),(10,30),(-30,None))])
pickle.dump(R,open("eval4.pkl","wb"))
