import pickle, requests, time, json
from concurrent.futures import ThreadPoolExecutor
Ts,U=pickle.load(open("/data/tmp/bt/cands.pkl","rb"))
allc=sorted(set(sum(U.values(),[])))
S=requests.Session(); S.headers.update({"User-Agent":"Mozilla/5.0","Referer":"https://vip.stock.finance.sina.com.cn/"})
u="https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/MoneyFlow.ssl_qsfx_zjlrqs"
def f(c):
    sym=("sh" if c.startswith(("6","9")) else "sz")+c
    for i in range(4):
        try:
            r=S.get(u,params={"page":1,"num":60,"sort":"opendate","asc":0,"daima":sym},timeout=10)
            j=json.loads(r.text)
            return c,[(x["opendate"],float(x["netamount"]),float(x["r0_net"])) for x in j]
        except Exception: time.sleep(1.5*(i+1))
    return c,None
t=time.time()
with ThreadPoolExecutor(4) as ex: res=dict(ex.map(f,allc))
ok={c:v for c,v in res.items() if v}
print("ok",len(ok),"of",len(allc),round(time.time()-t),"s")
pickle.dump(ok,open("/data/tmp/bt/sina_flow.pkl","wb"))
