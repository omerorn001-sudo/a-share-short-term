exec(open("/data/tmp/bt/engine.py").read())
Ts,U=pickle.load(open("/data/tmp/bt/cands_jan.pkl","rb"))
tdf=pickle.load(open("/data/tmp/bt/tech_jan.pkl","rb"))
FH=pickle.load(open("/data/tmp/bt/fund_hist_h1.pkl","rb"))
MH=pickle.load(open("/data/tmp/bt/sina_flow_h1.pkl","rb"))
FIELD=int(open("/data/tmp/bt/field.txt").read())
# --- 预处理 ---
main=pd.DataFrame({c:pd.Series({pd.Timestamp(x[0]):x[FIELD] for x in rows}) for c,rows in MH.items()}).sort_index()
mg=FH["margin"].copy(); mg["date"]=pd.to_datetime(mg["DATE"]); mg=mg.sort_values("date")
for k in ("RZYE","RZJME","RZYEZB"): mg[k]=pd.to_numeric(mg[k],errors="coerce")
mgg={c:g for c,g in mg.groupby("SCODE")}
lh=FH["lhb"].copy(); lh["d"]=pd.to_datetime(lh["TRADE_DATE"]); lh=lh.drop_duplicates(["SECURITY_CODE","d"])
lh["net"]=pd.to_numeric(lh["BILLBOARD_NET_AMT"],errors="coerce")
se=FH["seats"].copy(); se["d"]=pd.to_datetime(se["TRADE_DATE"])
se=se.drop_duplicates(["SECURITY_CODE","d","OPERATEDEPT_NAME","BUY","SELL"]); se["NET"]=pd.to_numeric(se["NET"],errors="coerce").fillna(0)
se["inst"]=se["OPERATEDEPT_NAME"].astype(str).str.contains("机构专用"); se["north"]=se["OPERATEDEPT_NAME"].astype(str).str.contains("股通专用")
og=FH["org"].copy(); og["rd"]=pd.to_datetime(og["REPORT_DATE"]); og=og[og.rd<=pd.Timestamp("2025-09-30")].sort_values("rd")
org={}
for c,g in og.groupby("SECURITY_CODE"):
    l=g.iloc[-1]; p=g.iloc[-2] if len(g)>1 else None
    org[c]={"org_ratio":float(l.FREESHARES_RATIO or 0),"org_n":int(l.HOULD_NUM or 0),
            "org_ratio_chg":(float(l.FREESHARES_RATIO or 0)-float(p.FREESHARES_RATIO or 0)) if p is not None else None}
fin=FH["fin"].copy(); fin["nd"]=pd.to_datetime(fin["NOTICE_DATE"]); fin=fin.sort_values("nd")
sv=FH["sv"].copy(); sv["SECURITY_CODE"]=sv["SECURITY_CODE"].astype(str).str.zfill(6); sv["nd"]=pd.to_datetime(sv["NOTICE_DATE"]); sv["SUM"]=pd.to_numeric(sv["SUM"],errors="coerce")
im=data._cached("industry_map", None, max_age_hours=1e9) if False else pd.read_csv(data.CACHE_DIR/"industry_map.csv",dtype={"code":str})
im["code"]=im["code"].str.zfill(6); ind=im.set_index("code")["industry"]
def fund_row(c,T):
    r={"code":c,"float_mv":FMV.at[T,c]}
    if c in main and T in main.index:
        s=main[c].loc[:T].dropna()
        if len(s) and s.index[-1]==T: r.update(main1=s.iloc[-1],main5=s.tail(5).sum(),main10=s.tail(10).sum())
    g=mgg.get(c)
    if g is not None:
        g=g[g.date<T]
        if len(g):
            y=g.RZYE.reset_index(drop=True); l=g.iloc[-1]
            b5=y.iloc[-6] if len(y)>=6 else y.iloc[0]; b20=y.iloc[-21] if len(y)>=21 else y.iloc[0]
            r.update(rz_bal=l.RZYE,rz_chg5=y.iloc[-1]/b5-1,rz_chg20=y.iloc[-1]/b20-1,rz_ratio=l.RZYEZB or 0)
    w0=T-pd.Timedelta(days=30)
    l2=lh[(lh.SECURITY_CODE==c)&(lh.d>w0)&(lh.d<=T)]
    if len(l2):
        s2=se[(se.SECURITY_CODE==c)&(se.d>w0)&(se.d<=T)]
        r.update(lhb_n=len(l2),lhb_net=l2.net.sum(),lhb_inst=s2.loc[s2.inst,"NET"].sum(),lhb_inst_n=int(s2.inst.sum()),lhb_north=s2.loc[s2.north,"NET"].sum())
    if c in org: r.update(org[c])
    s3=sv[(sv.SECURITY_CODE==c)&(sv.nd<=T)&(sv.nd>T-pd.Timedelta(days=90))]
    r.update(调研次数=len(s3),调研家次=s3.SUM.sum())
    f=fin[(fin.SECURITY_CODE==c)&(fin.nd<=T)]
    if len(f): l=f.iloc[-1]; r.update(净利=l.PARENTNETPROFIT,净利同比=l.PARENTNETPROFITTZ,报告期=l.REPORT_DATE_NAME)
    return r
COST_B=0.00025+0.001; COST_S=0.00025+0.0005+0.001
def lim(c): return 0.2 if c.startswith(("300","301","688","689")) else 0.1
res=[]; picks_all=[]
for T in Ts:
    i=dates.get_loc(T)
    t=tdf[tdf["T"]==T].copy()
    fr=pd.DataFrame([fund_row(c,T) for c in t.code])
    df=t.merge(fr,on="code",how="left")
    df["amount"]=[AMT.at[T,c] for c in df.code]
    bp=PCT.loc[T].groupby(ind.reindex(PCT.columns)).mean().sort_values(ascending=False)
    rk=pd.Series(range(1,len(bp)+1),index=bp.index)
    df["industry"]=df.code.map(ind); df["板块排名"]=df.industry.map(rk)
    df=conclude(funds.score(df),len(bp),None)
    df["技术分"]=df["趋势分"]+df["买点分"]+df["预警分"]
    df["T"]=T
    T1,=dates[i+1:i+2]
    nxt=PCT.loc[T1].dropna(); top30=set(nxt.sort_values(ascending=False).head(30).index)
    for c in df.code:
        ent=O.at[T1,c]; prev=C.at[T,c]
        row={"T":T,"code":c}
        row["次日涨幅"]=nxt.get(c)
        row["次日前30"]=c in top30
        row["可买"]=bool(ent>0 and ent<prev*(1+lim(c))*0.998)
        for k in (2,3,4):
            ex=C.at[dates[i+k],c]
            row[f"ret{k}"]=(ex*(1-COST_S))/(ent*(1+COST_B))-1 if row["可买"] else None
        res.append(row)
    picks_all.append(df)
R=pd.DataFrame(res); A=pd.concat(picks_all,ignore_index=True).merge(R,on=["T","code"])
# 全市场基准：T+1 开盘买、T+k 收盘卖
mk={}
for T in Ts:
    i=dates.get_loc(T); e=O.iloc[i+1]
    for k in (2,3,4): mk.setdefault(k,[]).append(((C.iloc[i+k]*(1-COST_S))/(e*(1+COST_B))-1).replace([np.inf,-np.inf],np.nan).median())
top30cnt=[]
for T in Ts:
    i=dates.get_loc(T); nxt=PCT.iloc[i+1].dropna().sort_values(ascending=False).head(30)
    top30cnt.append({"T":T,"前30在初筛池":int(sum(c in set(U[T]) for c in nxt.index)),"前30最低涨幅":nxt.iloc[-1]})
pickle.dump((A,mk,pd.DataFrame(top30cnt)),open("/data/tmp/bt/result_jan.pkl","wb"))
print("done",len(A))
