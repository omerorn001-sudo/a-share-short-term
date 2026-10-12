import pickle, sys, json, time, requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/data/a-share-short-term")
from ashare import datacenter as dc
allc=sorted(set(c for s in ("jun","jul") for v in pickle.load(open(f"cands_{s}.pkl","rb"))[1].values() for c in v)); print("union",len(allc),flush=True)
inl=lambda p: ",".join(f'"{c}"' for c in p)
ch=lambda xs,n: [xs[i:i+n] for i in range(0,len(xs),n)]
q=lambda rep,f,cols,sort: dc.query(rep, filt=f, sort=sort, columns=cols, page_size=500, max_pages=80)
out={}
out["margin"]=pd.concat([q("RPTA_WEB_RZRQ_GGMX",f"(SCODE in ({inl(p)}))(DATE>='2026-04-20')(DATE<='2026-08-05')","DATE,SCODE,RZYE,RZJME,RZYEZB","DATE") for p in ch(allc,20)],ignore_index=True); print("margin",len(out["margin"]),flush=True)
det,seats=[],[]
for p in ch(allc,60):
    f=f"(SECURITY_CODE in ({inl(p)}))(TRADE_DATE>='2026-04-28')(TRADE_DATE<='2026-08-05')"
    det.append(q("RPT_DAILYBILLBOARD_DETAILSNEW",f,"SECURITY_CODE,TRADE_DATE,EXPLANATION,BILLBOARD_NET_AMT","TRADE_DATE"))
    for rep in ("RPT_BILLBOARD_DAILYDETAILSBUY","RPT_BILLBOARD_DAILYDETAILSSELL"):
        seats.append(q(rep,f,"SECURITY_CODE,TRADE_DATE,OPERATEDEPT_NAME,BUY,SELL,NET","TRADE_DATE"))
out["lhb"]=pd.concat(det,ignore_index=True); out["seats"]=pd.concat(seats,ignore_index=True); print("lhb",len(out["lhb"]),len(out["seats"]),flush=True)
out["org"]=pd.concat([q("RPT_MAIN_ORGHOLD",f'(SECURITY_CODE in ({inl(p)}))(ORG_TYPE="00")(REPORT_DATE>=\'2025-12-31\')',"SECURITY_CODE,REPORT_DATE,HOULD_NUM,FREESHARES_RATIO,HOLDCHA_NUM","REPORT_DATE") for p in ch(allc,80)],ignore_index=True)
sec=[c+(".SH" if c.startswith(("6","9")) else ".SZ") for c in allc]
out["fin"]=pd.concat([q("RPT_F10_FINANCE_MAINFINADATA",f"(SECUCODE in ({inl(p)}))(REPORT_DATE>='2025-06-30')","SECURITY_CODE,REPORT_DATE,REPORT_DATE_NAME,NOTICE_DATE,PARENTNETPROFIT,PARENTNETPROFITTZ","REPORT_DATE") for p in ch(sec,50)],ignore_index=True); print("org/fin",len(out["org"]),len(out["fin"]),flush=True)
out["sv"]=dc.surveys("2026-02-25"); print("sv",len(out["sv"]),flush=True)
pickle.dump(out,open("fund_hist_jj.pkl","wb"))
S=requests.Session(); S.headers.update({"User-Agent":"Mozilla/5.0","Referer":"https://vip.stock.finance.sina.com.cn/"})
u="https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_qsfx_zjlrqs"
def f(c):
    sym=("sh" if c.startswith(("6","9")) else "sz")+c
    for i in range(4):
        try:
            j=json.loads(S.get(u,params={"page":1,"num":130,"sort":"opendate","asc":0,"daima":sym},timeout=10).text)
            return c,[(x["opendate"],float(x["netamount"]),float(x["r0_net"])) for x in j]
        except Exception: time.sleep(1.5*(i+1))
    return c,None
with ThreadPoolExecutor(4) as ex: res=dict(ex.map(f,allc))
print("flow ok",sum(1 for v in res.values() if v),"of",len(allc),flush=True)
pickle.dump({c:v for c,v in res.items() if v},open("sina_flow_jj.pkl","wb"))
