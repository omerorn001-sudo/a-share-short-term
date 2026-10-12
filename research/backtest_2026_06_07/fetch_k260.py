import time, json, requests, pickle
import pandas as pd
from concurrent.futures import ThreadPoolExecutor
from ashare.tencent import prefixed
from ashare import data
S=requests.Session(); S.headers.update({"User-Agent":"Mozilla/5.0"})
def f(c):
    for i in range(3):
        try:
            r=S.get("https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_x=/CN_MarketDataService.getKLineData",params={"symbol":prefixed(c),"scale":240,"ma":"no","datalen":260},timeout=10)
            t=r.text; rows=json.loads(t[t.index("(")+1:t.rindex(")")])
            d=pd.DataFrame(rows).rename(columns={"day":"date"})
            d["date"]=pd.to_datetime(d["date"])
            return c,d.set_index("date")[["open","high","low","close","volume"]].astype(float)
        except Exception: time.sleep(1+i)
    return c,None
sp=data.spot()
codes=[c for c in sp.code if not c.startswith(("9","2","8","4"))]
t=time.time()
with ThreadPoolExecutor(6) as ex: res=dict(ex.map(f,codes))
ok={c:d for c,d in res.items() if d is not None and len(d)}
print("ok",len(ok),"of",len(codes),round(time.time()-t),"s",flush=True)
pickle.dump(ok,open("/data/tmp/bt/kpanel260.pkl","wb"))
