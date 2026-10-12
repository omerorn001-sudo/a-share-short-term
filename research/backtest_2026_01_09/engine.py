"""一个月滚动回测：T 日收盘后用 7 条件系统选分最高 10 只，T+1 开盘买，T+2/T+3/T+4 收盘卖。"""
import pickle, json, sys
import numpy as np, pandas as pd
sys.path.insert(0, "/data/a-share-short-term")
from ashare.config import load_config
from ashare.strategy import prepare, sell_warnings
from ashare import funds, data
from ashare.batch import conclude
cfg = load_config(None); S = cfg["screen"]; ST = cfg["strategy"]
import os; P = pickle.load(open(os.environ.get("KP","/data/tmp/bt/kpanel.pkl"), "rb"))
import os.path as _p
if _p.exists("/data/tmp/bt/spot.pkl"): sp = pickle.load(open("/data/tmp/bt/spot.pkl","rb"))
else: sp = data.spot().set_index("code"); pickle.dump(sp, open("/data/tmp/bt/spot.pkl","wb"))
O, H, L, C, V = [pd.DataFrame({c: d[k] for c, d in P.items()}).sort_index() for k in ["open", "high", "low", "close", "volume"]]
dates = C.index
codes = [c for c in C.columns if c in sp.index]
fs = (sp["float_mv"] / sp["price"]).reindex(C.columns)
ts = (sp["total_mv"] / sp["price"]).reindex(C.columns)
names = sp["name"].reindex(C.columns)
AMT = V * (O + H + L + C) / 4
FMV = C * fs; TMV = C * ts
TURN = V / fs * 100
VR = V / V.shift(1).rolling(5).mean()
PCT = C / C.shift(1) - 1

def candidates(T):
    i = dates.get_loc(T)
    ok = (AMT.loc[T] >= S["min_amount"]) & FMV.loc[T].between(S["min_float_mv"], S["max_float_mv"]) \
         & TURN.loc[T].between(S["min_turnover"], S["max_turnover"]) & VR.loc[T].between(S["min_volume_ratio"], S["max_volume_ratio"])
    ok &= ~names.str.contains("ST|退", na=False)
    return [c for c in ok[ok].index]

def tech(c, T):
    h = pd.DataFrame({"date": dates, "open": O[c], "high": H[c], "low": L[c], "close": C[c], "volume": V[c]}).set_index(dates)
    h = h.loc[:T].dropna().reset_index(drop=True)
    if len(h) < 60: return None
    d = prepare(h, cfg); x = d.iloc[-1]
    hi = float(d["high"].shift(1).rolling(ST["breakout_window"]).max().iloc[-1])
    cc = {"①突破": x["close"] > hi, "②放量": x["vol_ratio5"] >= ST["vol_mult"], "③站上MA5": x["close"] > x["ma5"],
          "④偏离≤7%": x["bias5"] <= ST["max_ma5_bias"], "⑤均线多头": (x["ma5"] > x["ma10"]) and (x["ma10"] > x["ma20"])}
    pos = sum(x["close"] > x[n] for n in ("ma5", "ma10", "ma20", "ma60"))
    trend = 2 if cc["⑤均线多头"] and cc["③站上MA5"] else 1 if pos >= 3 else -2 if pos <= 1 else 0
    w = sell_warnings(d, cfg).iloc[-1]; flags = [k for k, v in w.items() if v]
    return {"code": c, "close": float(x["close"]), "hi20": hi, "gap": hi / x["close"] - 1, "bias5": float(x["bias5"]),
            **{k: bool(v) for k, v in cc.items()}, "技术满足": int(sum(cc.values())), "趋势分": trend,
            "预警": "、".join(flags), "预警分": -min(2, len(flags)) if flags else 1,
            "买点分": 2 if all(cc.values()) else (-1 if x["bias5"] > 0.10 else 0)}
