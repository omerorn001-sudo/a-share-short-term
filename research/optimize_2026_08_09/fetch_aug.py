import pickle, sys, json, time, requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/data/a-share-short-term")
from ashare import datacenter as dc
Ts,U=pickle.load(open("cands_aug.pkl","rb"))
allc=sorted(set(sum(U.values(),[]))); new=json.load(open("new_aug.json"))
inl=lambda p: ",".join(f'"{c}"' for c in p)
ch=lambda xs,n: [xs[i:i+n] for i in range(0,len(xs),n)]
q=lambda rep,f,cols,sort: dc.query(rep, filt=f, sort=sort, columns=cols, page_size=500, max_pages=50)
FH=pickle.load(open("fund_hist.pkl","rb")); out={}
out["margin"]=pd.concat([q("RPTA_WEB_RZRQ_GGMX",f"(SCODE in ({inl(p)}))(DATE>='2026-06-25')(DATE<='2026-09-05')","DATE,SCODE,RZYE,RZJME,RZYEZB","DATE") for p in ch(allc,30)],ignore_index=True); print("margin",len(out["margin"]),flush=True)
det,seats=[],[]
for p in ch(allc,80):
    f=f"(SECURITY_CODE in ({inl(p)}))(TRADE_DATE>='2026-07-01')(TRADE_DATE<='2026-09-05')"
    det.append(q("RPT_DAILYBILLBOARD_DETAILSNEW",f,"SECURITY_CODE,TRADE_DATE,EXPLANATION,BILLBOARD_NET_AMT","TRADE_DATE"))
    for rep in ("RPT_BILLBOARD_DAILYDETAILSBUY","RPT_BILLBOARD_DAILYDETAILSSELL"):
        seats.append(q(rep,f,"SECURITY_CODE,TRADE_DATE,OPERATEDEPT_NAME,BUY,SELL,NET","TRADE_DATE"))
out["lhb"]=pd.concat(det,ignore_index=True); out["seats"]=pd.concat(seats,ignore_index=True); print("lhb",len(out["lhb"]),len(out["seats"]),flush=True)
og=[q("RPT_MAIN_ORGHOLD",f'(SECURITY_CODE in ({inl(p)}))(ORG_TYPE="00")(REPORT_DATE>=\'2026-03-31\')',"SECURITY_CODE,REPORT_DATE,HOULD_NUM,FREESHARES_RATIO,HOLDCHA_NUM","REPORT_DATE") for p in ch(new,80)]
out["org"]=pd.concat([FH["org"]]+og,ignore_index=True)
sec=[c+(".SH" if c.startswith(("6","9")) else ".SZ") for c in new]
fn=[q("RPT_F10_FINANCE_MAINFINADATA",f"(SECUCODE in ({inl(p)}))(REPORT_DATE>='2025-09-30')","SECURITY_CODE,REPORT_DATE,REPORT_DATE_NAME,NOTICE_DATE,PARENTNETPROFIT,PARENTNETPROFITTZ","REPORT_DATE") for p in ch(sec,50)]
out["fin"]=pd.concat([FH["fin"]]+fn,ignore_index=True); print("org/fin",len(out["org"]),len(out["fin"]),flush=True)
out["sv"]=FH["sv"]
pickle.dump(out,open("fund_hist_aug.pkl","wb"))
S=requests.Session(); S.headers.update({"User-Agent":"Mozilla/5.0","Referer":"https://vip.stock.finance.sina.com.cn/"})
u="https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_qsfx_zjlrqs"
def f(c):
    sym=("sh" if c.startswith(("6","9")) else "sz")+c
    for i in range(4):
        try:
            j=json.loads(S.get(u,params={"page":1,"num":70,"sort":"opendate","asc":0,"daima":sym},timeout=10).text)
            return c,[(x["opendate"],float(x["netamount"]),float(x["r0_net"])) for x in j]
        except Exception: time.sleep(1.5*(i+1))
    return c,None
with ThreadPoolExecutor(4) as ex: res=dict(ex.map(f,new))
MH=pickle.load(open("sina_flow.pkl","rb")); MH.update({c:v for c,v in res.items() if v})
print("flow ok",sum(1 for v in res.values() if v),"of",len(new),flush=True)
pickle.dump(MH,open("sina_flow_aug.pkl","wb"))
