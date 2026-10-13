"""跟游资席位：T 日龙虎榜知名游资买入 → T+1 10:30 买入 → T+2 卖出（开盘/10:30/收盘三种），2026-09 信号日。"""
import sys, json, time, pickle, requests, numpy as np, pandas as pd
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, "/data/a-share-short-term")
from ashare.youzi import fetch
det, s = fetch("2026-09-01", "2026-09-30")
s.to_pickle("seats_sep.pkl"); det.to_pickle("det_sep.pkl")
s = s[(s.side == "买") & ~s["游资"].isin(["", "机构", "北向", "外资"]) & ~s.SECURITY_CODE.str.startswith(("4", "8", "9"))]
codes = sorted(s.SECURITY_CODE.unique()); print("信号行", len(s), "股票", len(codes), flush=True)
S = requests.Session(); S.headers.update({"User-Agent": "Mozilla/5.0"})
def k(c):
    sym = ("sh" if c.startswith("6") else "sz") + c
    for i in range(4):
        try:
            t = S.get("https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_x=/CN_MarketDataService.getKLineData",
                      params={"symbol": sym, "scale": 30, "ma": "no", "datalen": 1023}, timeout=10).text
            d = pd.DataFrame(json.loads(t[t.index("(") + 1:t.rindex(")")]))
            d["day"] = pd.to_datetime(d["day"]); return c, d.set_index("day")[["open", "high", "low", "close"]].astype(float)
        except Exception:
            time.sleep(1 + i)
    return c, None
with ThreadPoolExecutor(6) as ex: K = {c: d for c, d in ex.map(k, codes) if d is not None}
pickle.dump(K, open("k30.pkl", "wb")); print("分钟线", len(K), flush=True)
