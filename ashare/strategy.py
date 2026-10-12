"""买入与卖出信号。全部基于收盘后可得数据，次日执行，避免未来函数。"""
import pandas as pd

from .indicators import add_indicators, macd_top_divergence


def entry_signal(d: pd.DataFrame, cfg: dict) -> pd.Series:
    """放量平台突破：收盘创 N 日新高 + 放量 + 站上 MA5（可选均线多头）+ 不过度偏离。"""
    s = cfg["strategy"]
    n = s["breakout_window"]
    prior_high = d["high"].shift(1).rolling(n).max()
    sig = (d["close"] > prior_high) & (d["vol_ratio5"] >= s["vol_mult"]) & (d["close"] > d["ma5"])
    sig &= d["bias5"] <= s["max_ma5_bias"]
    if s.get("require_ma_bull", True):
        sig &= (d["ma5"] > d["ma10"]) & (d["ma10"] > d["ma20"])
    return sig.fillna(False)


def sell_warnings(d: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """持仓卖出预警（逐日布尔列），供 check 命令和人工复盘使用。"""
    e = cfg["exit"]
    w = pd.DataFrame(index=d.index)
    ma = e.get("exit_below_ma") or 5
    w[f"跌破MA{ma}"] = d["close"] < d[f"ma{ma}"]
    w["高位长上影"] = d["long_upper"] & (d["close"] >= d["close"].rolling(20).max() * 0.95)
    w["放量滞涨"] = (d["vol_ratio5"] >= 3) & (d["close"].pct_change().abs() < 0.01)
    w["量价背离"] = (d["close"] >= d["close"].rolling(20).max()) & (d["volume"] < d["vol_ma5"])
    w["MACD顶背离"] = macd_top_divergence(d)
    w["偏离MA5过大"] = d["bias5"] > 0.10
    w["RSI超买拐头"] = (d["rsi6"].shift(1) > 80) & (d["rsi6"] < d["rsi6"].shift(1))
    w["KDJ高位死叉"] = (d["k"].shift(1) > d["d"].shift(1)) & (d["k"] < d["d"]) & (d["k"] > 80)
    return w.fillna(False)


def prepare(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    d = add_indicators(df)
    d["entry"] = entry_signal(d, cfg)
    return d
