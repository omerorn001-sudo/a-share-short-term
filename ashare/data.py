"""数据层：封装 AKShare，带本地 CSV 缓存与多源回退。

统一输出列名（英文）：date, open, high, low, close, volume, amount, turnover。
"""
from __future__ import annotations

import time
from pathlib import Path

import pandas as pd

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"

_HIST_COLS = {"日期": "date", "开盘": "open", "收盘": "close", "最高": "high", "最低": "low",
              "成交量": "volume", "成交额": "amount", "换手率": "turnover", "涨跌幅": "pct_chg"}
_SPOT_COLS = {"代码": "code", "名称": "name", "最新价": "price", "涨跌幅": "pct_chg",
              "成交额": "amount", "换手率": "turnover", "量比": "volume_ratio",
              "流通市值": "float_mv", "总市值": "total_mv", "今开": "open", "昨收": "prev_close"}


def _ak():
    import akshare as ak  # 延迟导入，离线测试不依赖网络库
    return ak


def _retry(fn, tries=3, wait=1.5):
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:  # 网络抖动
            last = e
            time.sleep(wait * (i + 1))
    raise last


def _cached(name: str, fetch, max_age_hours: float | None = 12) -> pd.DataFrame:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{name}.csv"
    if path.exists() and (max_age_hours is None or time.time() - path.stat().st_mtime < max_age_hours * 3600):
        return pd.read_csv(path, dtype={"code": str})
    df = fetch()
    df.to_csv(path, index=False)
    return df


def _norm_hist(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns=_HIST_COLS)
    df["date"] = pd.to_datetime(df["date"])
    keep = [c for c in ["date", "open", "high", "low", "close", "volume", "amount", "turnover", "pct_chg"] if c in df]
    return df[keep].sort_values("date").reset_index(drop=True)


def _prefixed(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith(("6", "9")):
        return "sh" + code
    if code.startswith(("8", "4")):
        return "bj" + code
    return "sz" + code


def stock_hist(code: str, start: str, end: str, adjust: str = "qfq", cache: bool = True) -> pd.DataFrame:
    """个股日线（默认前复权）。start/end 形如 20230101。"""
    code = str(code).zfill(6)

    def fetch():
        ak = _ak()
        try:
            raw = _retry(lambda: ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start,
                                                     end_date=end, adjust=adjust))
            return _norm_hist(raw)
        except Exception:
            raw = _retry(lambda: ak.stock_zh_a_hist_tx(symbol=_prefixed(code), start_date=start,
                                                        end_date=end, adjust=adjust))
            df = raw.rename(columns={"turnover": "turnover_ratio"})
            df["date"] = pd.to_datetime(df["date"])
            df["volume"] = df["volume"] * 100  # 腾讯源单位为手
            return df[["date", "open", "high", "low", "close", "volume", "amount"]]

    if not cache:
        return fetch()
    df = _cached(f"hist_{code}_{start}_{end}_{adjust}", fetch, max_age_hours=None if end < _today() else 6)
    df["date"] = pd.to_datetime(df["date"])
    return df


def index_hist(symbol: str = "sh000001") -> pd.DataFrame:
    """指数日线，含成交额（元）。"""
    def fetch():
        ak = _ak()
        try:
            raw = _retry(lambda: ak.stock_zh_index_daily_em(symbol=symbol), tries=2)
            return raw.rename(columns={"date": "date"})
        except Exception:
            return _retry(lambda: ak.stock_zh_index_daily(symbol=symbol))
    df = _cached(f"index_{symbol}", fetch, max_age_hours=6)
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def spot() -> pd.DataFrame:
    """全市场实时快照。东方财富优先，失败回退新浪（较慢，无量比和市值）。"""
    def fetch():
        ak = _ak()
        try:
            return _retry(lambda: ak.stock_zh_a_spot_em(), tries=2).rename(columns=_SPOT_COLS)
        except Exception:
            raw = _retry(lambda: ak.stock_zh_a_spot())
            df = raw.rename(columns={"代码": "code", "名称": "name", "最新价": "price", "涨跌幅": "pct_chg",
                                     "成交额": "amount", "昨收": "prev_close", "今开": "open"})
            df["code"] = df["code"].str[-6:]
            return df
    df = _cached(f"spot_{_today()}", fetch, max_age_hours=0.25)
    df["code"] = df["code"].astype(str).str.zfill(6)
    return df


def limit_up_pool(date: str) -> pd.DataFrame:
    return _cached(f"zt_{date}", lambda: _retry(lambda: _ak().stock_zt_pool_em(date=date)), None if date < _today() else 0.25)


def limit_down_pool(date: str) -> pd.DataFrame:
    return _cached(f"dt_{date}", lambda: _retry(lambda: _ak().stock_zt_pool_dtgc_em(date=date)), None if date < _today() else 0.25)


def broken_pool(date: str) -> pd.DataFrame:
    """炸板池。"""
    return _cached(f"zb_{date}", lambda: _retry(lambda: _ak().stock_zt_pool_zbgc_em(date=date)), None if date < _today() else 0.25)


def dragon_tiger(date: str) -> pd.DataFrame:
    """龙虎榜明细。"""
    return _cached(f"lhb_{date}", lambda: _retry(lambda: _ak().stock_lhb_detail_em(start_date=date, end_date=date)), None if date < _today() else 1)


def industry_boards() -> pd.DataFrame:
    """行业板块强度。东方财富优先，失败回退同花顺。"""
    def fetch():
        ak = _ak()
        try:
            df = _retry(lambda: ak.stock_board_industry_name_em(), tries=2)
            return df.rename(columns={"板块名称": "board", "涨跌幅": "pct_chg", "上涨家数": "up", "下跌家数": "down",
                                      "领涨股票": "leader", "换手率": "turnover"})
        except Exception:
            df = _retry(lambda: ak.stock_board_industry_summary_ths())
            return df.rename(columns={"板块": "board", "涨跌幅": "pct_chg", "上涨家数": "up", "下跌家数": "down",
                                      "领涨股": "leader", "净流入": "net_inflow"})
    return _cached(f"boards_{_today()}", fetch, max_age_hours=0.25)


def _today() -> str:
    return pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y%m%d")
