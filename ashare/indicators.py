"""技术指标。输入为含 open/high/low/close/volume 列、按日期升序的 DataFrame。"""
import numpy as np
import pandas as pd


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    c, v = d["close"], d["volume"]
    for n in (5, 10, 20, 60):
        d[f"ma{n}"] = c.rolling(n).mean()
    d["vol_ma5"] = v.rolling(5).mean()
    d["vol_ratio5"] = v / d["vol_ma5"].shift(1)          # 相对前 5 日均量
    d["bias5"] = c / d["ma5"] - 1
    # MACD(12,26,9)
    ema12, ema26 = c.ewm(span=12, adjust=False).mean(), c.ewm(span=26, adjust=False).mean()
    d["dif"] = ema12 - ema26
    d["dea"] = d["dif"].ewm(span=9, adjust=False).mean()
    d["macd"] = 2 * (d["dif"] - d["dea"])
    # RSI(6)
    delta = c.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 6, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 6, adjust=False).mean()
    d["rsi6"] = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
    # KDJ(9,3,3)
    low9, high9 = d["low"].rolling(9).min(), d["high"].rolling(9).max()
    rsv = (c - low9) / (high9 - low9).replace(0, np.nan) * 100
    d["k"] = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    d["d"] = d["k"].ewm(alpha=1 / 3, adjust=False).mean()
    d["j"] = 3 * d["k"] - 2 * d["d"]
    # K 线形态
    body = (c - d["open"]).abs()
    d["upper_shadow"] = d["high"] - d[["open", "close"]].max(axis=1)
    d["long_upper"] = (d["upper_shadow"] > 2 * body) & (d["upper_shadow"] / c > 0.03)
    return d


def macd_top_divergence(d: pd.DataFrame, window: int = 20) -> pd.Series:
    """价格创 window 日新高，但 MACD 柱低于前一个高点时的柱值。"""
    new_high = d["close"] >= d["close"].rolling(window).max()
    prev_macd_max = d["macd"].shift(1).rolling(window).max()
    return new_high & (d["macd"] < prev_macd_max) & (d["macd"] > 0)
