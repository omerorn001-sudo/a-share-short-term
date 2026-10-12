"""选股：快照初筛（市值/换手/量比/成交额）→ 日线技术复核（突破/均线/偏离）→ 情绪标签。"""
import pandas as pd

from . import data
from .rules import board_of
from .strategy import prepare


def prefilter(snap: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    s = cfg["screen"]
    df = snap.copy()
    df = df[df["price"].notna() & (df["price"] > 0)]
    if s["exclude_st"]:
        df = df[~df["name"].str.contains("ST|退", na=False)]
    if s["exclude_bj"]:
        df = df[df["code"].map(board_of) != "bj"]
    df = df[df["amount"] >= s["min_amount"]]
    if "float_mv" in df:
        df = df[df["float_mv"].between(s["min_float_mv"], s["max_float_mv"])]
    if "turnover" in df:
        df = df[df["turnover"].between(s["min_turnover"], s["max_turnover"])]
    if "volume_ratio" in df:
        df = df[df["volume_ratio"].between(s["min_volume_ratio"], s["max_volume_ratio"])]
    df = df.sort_values("amount", ascending=False)
    return df.head(s["top_n"]) if s.get("top_n") else df


def technical_check(code: str, cfg: dict, end: str) -> dict | None:
    start = (pd.Timestamp(end) - pd.Timedelta(days=200)).strftime("%Y%m%d")
    df = data.stock_hist(code, start, end)
    if len(df) < 60:
        return None
    d = prepare(df, cfg).iloc[-1]
    return {"突破信号": bool(d["entry"]), "MA多头": bool(d["ma5"] > d["ma10"] > d["ma20"]),
            "偏离MA5": round(float(d["bias5"]), 4), "5日量比": round(float(d["vol_ratio5"]), 2),
            "RSI6": round(float(d["rsi6"]), 1)}


def screen(cfg: dict, date: str | None = None) -> pd.DataFrame:
    end = date or pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y%m%d")
    cands = prefilter(data.spot(), cfg)
    try:
        zt = data.limit_up_pool(end)[["代码", "连板数", "所属行业"]].rename(columns={"代码": "code"})
        zt["code"] = zt["code"].astype(str).str.zfill(6)
    except Exception:
        zt = pd.DataFrame(columns=["code", "连板数", "所属行业"])
    rows = []
    for _, r in cands.iterrows():
        try:
            tech = technical_check(r["code"], cfg, end)
        except Exception:
            tech = None
        if tech is None:
            continue
        rows.append({"代码": r["code"], "名称": r["name"], "涨跌幅": r.get("pct_chg"), "成交额(亿)": round(r["amount"] / 1e8, 2),
                     "换手率": r.get("turnover"), "量比": r.get("volume_ratio"), **tech})
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out = out.merge(zt, left_on="代码", right_on="code", how="left").drop(columns="code")
    out["评分"] = out["突破信号"] * 40 + out["MA多头"] * 20 + out["连板数"].notna() * 20 + (out["偏离MA5"] < 0.07) * 20
    return out.sort_values(["评分", "成交额(亿)"], ascending=False).reset_index(drop=True)


def signal_breakdown(code: str, cfg: dict, end: str) -> dict:
    """逐条列出“放量平台突破”买入信号的 5 个条件是否满足，便于解释为什么没触发。"""
    start = (pd.Timestamp(end) - pd.Timedelta(days=200)).strftime("%Y%m%d")
    df = data.stock_hist(code, start, end)
    s = cfg["strategy"]
    d = prepare(df, cfg)
    prior_high = d["high"].shift(1).rolling(s["breakout_window"]).max().iloc[-1]
    x = d.iloc[-1]
    conds = {
        f"①收盘>前{s['breakout_window']}日最高": (x["close"] > prior_high, f"{x['close']:.2f} vs {prior_high:.2f}"),
        f"②量≥5日均量×{s['vol_mult']}": (x["vol_ratio5"] >= s["vol_mult"], f"{x['vol_ratio5']:.2f}倍"),
        "③收盘>MA5": (x["close"] > x["ma5"], f"MA5 {x['ma5']:.2f}"),
        f"④偏离MA5≤{s['max_ma5_bias']:.0%}": (x["bias5"] <= s["max_ma5_bias"], f"{x['bias5']:.1%}"),
        "⑤MA5>MA10>MA20": ((x["ma5"] > x["ma10"]) and (x["ma10"] > x["ma20"]), f"{x['ma5']:.2f}/{x['ma10']:.2f}/{x['ma20']:.2f}"),
    }
    return {k: ("✅ " if ok else "❌ ") + v for k, (ok, v) in conds.items()} | {"满足": sum(bool(ok) for ok, _ in conds.values())}
