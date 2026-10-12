import pickle, sys
import pandas as pd
sys.path.insert(0, "/data/a-share-short-term")
from ashare import datacenter as dc
Ts,U=pickle.load(open("/data/tmp/bt/cands.pkl","rb"))
allc=sorted(set(sum(U.values(),[])))
inl=lambda p: ",".join(f'"{c}"' for c in p)
ch=lambda xs,n: [xs[i:i+n] for i in range(0,len(xs),n)]
out={}
def q(rep, f, cols, sort, ps=500, mp=50):
    return dc.query(rep, filt=f, sort=sort, columns=cols, page_size=ps, max_pages=mp)
out["margin"]=pd.concat([q("RPTA_WEB_RZRQ_GGMX",f"(SCODE in ({inl(p)}))(DATE>='2026-07-20')","DATE,SCODE,RZYE,RZJME,RZYEZB","DATE") for p in ch(allc,50)],ignore_index=True); print("margin",len(out["margin"]),flush=True)
det,seats=[],[]
for p in ch(allc,80):
    f=f"(SECURITY_CODE in ({inl(p)}))(TRADE_DATE>='2026-07-25')"
    det.append(q("RPT_DAILYBILLBOARD_DETAILSNEW",f,"SECURITY_CODE,TRADE_DATE,EXPLANATION,BILLBOARD_NET_AMT","TRADE_DATE"))
    for rep in ("RPT_BILLBOARD_DAILYDETAILSBUY","RPT_BILLBOARD_DAILYDETAILSSELL"):
        seats.append(q(rep,f,"SECURITY_CODE,TRADE_DATE,OPERATEDEPT_NAME,BUY,SELL,NET","TRADE_DATE"))
out["lhb"]=pd.concat(det,ignore_index=True); out["seats"]=pd.concat(seats,ignore_index=True); print("lhb",len(out["lhb"]),len(out["seats"]),flush=True)
out["org"]=pd.concat([q("RPT_MAIN_ORGHOLD",f'(SECURITY_CODE in ({inl(p)}))(ORG_TYPE="00")(REPORT_DATE>=\'2026-03-31\')',"SECURITY_CODE,REPORT_DATE,HOULD_NUM,FREESHARES_RATIO,HOLDCHA_NUM","REPORT_DATE") for p in ch(allc,80)],ignore_index=True); print("org",len(out["org"]),flush=True)
sec=[c+(".SH" if c.startswith(("6","9")) else ".SZ") for c in allc]
out["fin"]=pd.concat([q("RPT_F10_FINANCE_MAINFINADATA",f"(SECUCODE in ({inl(p)}))(REPORT_DATE>='2025-12-31')","SECURITY_CODE,REPORT_DATE,REPORT_DATE_NAME,NOTICE_DATE,PARENTNETPROFIT,PARENTNETPROFITTZ","REPORT_DATE") for p in ch(sec,50)],ignore_index=True); print("fin",len(out["fin"]),flush=True)
out["sv"]=dc.surveys("2026-05-25"); print("sv",len(out["sv"]))
pickle.dump(out,open("/data/tmp/bt/fund_hist.pkl","wb"))
