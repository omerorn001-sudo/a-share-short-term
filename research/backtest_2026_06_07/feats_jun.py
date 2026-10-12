exec(open("/data/tmp/bt/engine.py").read())
A,mk,t30=pickle.load(open("result_jun.pkl","rb"))
MA5=C.rolling(5).mean(); MA10=C.rolling(10).mean(); MA20=C.rolling(20).mean(); MA60=C.rolling(60).mean()
HH20=H.shift(1).rolling(20).max(); LL20=L.rolling(20).min()
def lim(c): return 0.2 if c.startswith(("300","301","688","689")) else 0.1
rows=[]
for T,c in zip(A["T"],A.code):
    i=dates.get_loc(T); cl=C[c]; v=V[c]
    pc=cl.iloc[i-1]
    rng=H.at[T,c]-L.at[T,c]
    r={"T":T,"code":c,
       "f_pct":cl.iloc[i]/pc-1,
       "f_r5":cl.iloc[i]/cl.iloc[i-5]-1,"f_r10":cl.iloc[i]/cl.iloc[i-10]-1,"f_r20":cl.iloc[i]/cl.iloc[i-20]-1,"f_r60":cl.iloc[i]/cl.iloc[i-60]-1,
       "f_b5":cl.iloc[i]/MA5.at[T,c]-1,"f_b10":cl.iloc[i]/MA10.at[T,c]-1,"f_b20":cl.iloc[i]/MA20.at[T,c]-1,"f_b60":cl.iloc[i]/MA60.at[T,c]-1,
       "f_pos20":(cl.iloc[i]-LL20.at[T,c])/(max(HH20.at[T,c],H.at[T,c])-LL20.at[T,c]+1e-9),
       "f_clv":(cl.iloc[i]-L.at[T,c])/(rng+1e-9),           # 收盘在当日振幅的位置
       "f_upsh":(H.at[T,c]-max(cl.iloc[i],O.at[T,c]))/pc,    # 上影线
       "f_amp":rng/pc,
       "f_body":(cl.iloc[i]-O.at[T,c])/pc,
       "f_vr":VR.at[T,c],"f_turn":TURN.at[T,c],"f_fmv":np.log(FMV.at[T,c]),"f_amt":np.log(AMT.at[T,c]),
       "f_vtrend":v.iloc[i-4:i+1].mean()/v.iloc[i-20:i].mean(),
       "f_zt":float(cl.iloc[i]>=round(pc*(1+lim(c)),2)-0.005),
       "f_ma20slope":MA20.at[T,c]/MA20.iloc[i-5][c]-1,
       "f_vol20":(cl.pct_change().iloc[i-19:i+1]).std(), "f_gap1":O.iloc[i+1][c]/cl.iloc[i]-1}
    rows.append(r)
F=pd.DataFrame(rows)
A=A.merge(F,on=["T","code"])
A["f_main1r"]=A["main1"]/A["amount"]; A["f_main5r"]=A["main5"]/A["float_mv"]
A["f_rz5"]=A["rz_chg5"]; A["f_rzratio"]=A["rz_ratio"]; A["f_org"]=A["org_ratio_chg"]
pickle.dump(A,open("feat_jun.pkl","wb")); print(A.shape)
