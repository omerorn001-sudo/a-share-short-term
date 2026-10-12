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


def _final_today(path: Path) -> bool:
    """当天收盘后写入的行情缓存已是终值，当天内一直有效。"""
    now = pd.Timestamp.now(tz="Asia/Shanghai")
    close = now.normalize() + pd.Timedelta(hours=15, minutes=1)
    mtime = pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC").tz_convert("Asia/Shanghai")
    return now >= close and mtime >= close


def _cached(name: str, fetch, max_age_hours: float | None = 12, final_after_close: bool = False) -> pd.DataFrame:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{name}.csv"
    if path.exists() and final_after_close and _final_today(path):
        return pd.read_csv(path, dtype={"code": str})
    if path.exists() and (max_age_hours is None or (time.time() - path.stat().st_mtime < max_age_hours * 3600
                                                    and not _intraday_stale(path))):
        return pd.read_csv(path, dtype={"code": str})
    df = fetch()
    df.to_csv(path, index=False)
    return df


def _intraday_stale(path: Path) -> bool:
    """盘中写入的缓存在收盘后（15:00 起）一律视为过期，避免收盘复盘用到盘中数据。"""
    now = pd.Timestamp.now(tz="Asia/Shanghai")
    close = now.normalize() + pd.Timedelta(hours=15, minutes=1)
    mtime = pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC").tz_convert("Asia/Shanghai")
    return now >= close and mtime < close


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
        from . import eastmoney
        try:
            fq = {"qfq": 1, "hfq": 2, "": 0}.get(adjust, 1)
            df = eastmoney.kline(eastmoney.secid_of(code), beg=start, end=end, fqt=fq)
            if len(df):
                return df[["date", "open", "high", "low", "close", "volume", "amount", "turnover", "pct_chg"]]
        except Exception:
            pass
        try:                                     # 腾讯日 K（含当天），东财限流时的主力备用
            from . import tencent
            days = (pd.Timestamp(end) - pd.Timestamp(start)).days
            df = tencent.kline(code, n=min(int(days * 0.75) + 30, 2000), fq=adjust or "qfq")
            df = df[(df["date"] >= pd.Timestamp(start)) & (df["date"] <= pd.Timestamp(end))]
            if len(df):
                return df.reset_index(drop=True)
        except Exception:
            pass
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
    df = _cached(f"hist_{code}_{start}_{end}_{adjust}", fetch, max_age_hours=None if end < _today() else 6, final_after_close=True)
    df["date"] = pd.to_datetime(df["date"])
    return df


def index_hist(symbol: str = "sh000001") -> pd.DataFrame:
    """指数日线，含成交额（元）。"""
    def fetch():
        from . import eastmoney
        try:
            return eastmoney.kline(eastmoney.secid_of(symbol, is_index=True), fqt=0)
        except Exception:
            pass
        try:                                     # 腾讯：历史无成交额，按当天均价估算（只用于量能倍数）
            from . import tencent
            df = tencent.kline(symbol, n=640, fq="")
            last = df.iloc[-1]
            if pd.notna(last["amount"]) and last["volume"]:
                px = last["amount"] / last["volume"]
                df["amount"] = df["amount"].fillna(df["volume"] * px)
                df["amount_estimated"] = True
                df.loc[df.index[-1], "amount_estimated"] = False
            return df
        except Exception:
            pass
        ak = _ak()
        try:
            return _retry(lambda: ak.stock_zh_index_daily_em(symbol=symbol), tries=2)
        except Exception:
            return _retry(lambda: ak.stock_zh_index_daily(symbol=symbol))
    df = _cached(f"index_{symbol}", fetch, max_age_hours=6, final_after_close=True)
    if "amount" not in df:                      # 旧缓存来自新浪源，没有成交额
        (CACHE_DIR / f"index_{symbol}.csv").unlink(missing_ok=True)
        df = _cached(f"index_{symbol}", fetch, max_age_hours=6)
    df["date"] = pd.to_datetime(df["date"])
    df = _patch_today(df.sort_values("date").reset_index(drop=True), symbol)
    return df


def _patch_today(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """备用源日线可能缺当天（如东财 K 线停在上一交易日），用腾讯实时快照补上当天这一根。"""
    try:
        from . import tencent
        q = tencent.quotes([symbol])
        if q.empty:
            return df
        q = q.iloc[0]
        d = pd.Timestamp(str(q["time"])[:8])
        if len(df) and d > df["date"].iloc[-1] and q["price"]:
            row = {"date": d, "open": q["open"], "high": q["high"], "low": q["low"], "close": q["price"],
                   "volume": q["volume"], "amount": q["amount"], "pct_chg": q["pct_chg"]}
            df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    except Exception:
        pass
    return df


def spot() -> pd.DataFrame:
    """全市场实时快照。东财网页接口直连爬虫 → AKShare 东财 → 新浪（无量比和市值）。"""
    def fetch():
        from . import eastmoney
        try:
            return eastmoney.spot()
        except Exception as e:
            print(f"[提示] 东财直连失败，改用 新浪代码表+腾讯快照（含量比/市值）: {e!r}"[:150])
        ak = _ak()
        try:
            from . import tencent
            codes = _retry(lambda: ak.stock_zh_a_spot())["代码"].astype(str).str[-6:].tolist()
            df = tencent.quotes(codes)
            if len(df) > len(codes) * 0.9:
                return df.drop(columns=["time"])
        except Exception as e:
            print(f"[提示] 腾讯快照失败: {e!r}"[:120])
        try:
            return _retry(lambda: ak.stock_zh_a_spot_em(), tries=2).rename(columns=_SPOT_COLS)
        except Exception:
            raw = _retry(lambda: ak.stock_zh_a_spot())
            df = raw.rename(columns={"代码": "code", "名称": "name", "最新价": "price", "涨跌幅": "pct_chg",
                                     "成交额": "amount", "昨收": "prev_close", "今开": "open"})
            df["code"] = df["code"].str[-6:]
            return df
    df = _cached(f"spot_{_today()}", fetch, max_age_hours=0.25, final_after_close=True)
    df["code"] = df["code"].astype(str).str.zfill(6)
    return df


def _pool(kind: str, date: str, ak_fn: str) -> pd.DataFrame:
    def fetch():
        from . import eastmoney
        try:
            return eastmoney.limit_pool(kind, date)
        except Exception:
            return _retry(lambda: getattr(_ak(), ak_fn)(date=date))
    df = _cached(f"{kind}_{date}", fetch, None if date < _today() else 0.25)
    if "代码" in df:
        df["代码"] = df["代码"].astype(str).str.zfill(6)
    return df


def limit_up_pool(date: str) -> pd.DataFrame:
    return _pool("zt", date, "stock_zt_pool_em")


def limit_down_pool(date: str) -> pd.DataFrame:
    return _pool("dt", date, "stock_zt_pool_dtgc_em")


def broken_pool(date: str) -> pd.DataFrame:
    """炸板池。"""
    return _pool("zb", date, "stock_zt_pool_zbgc_em")


def dragon_tiger(date: str) -> pd.DataFrame:
    """龙虎榜明细。"""
    return _cached(f"lhb_{date}", lambda: _retry(lambda: _ak().stock_lhb_detail_em(start_date=date, end_date=date)), None if date < _today() else 1)


def industry_boards() -> pd.DataFrame:
    """行业板块强度（含主力净流入）。东财直连 → AKShare 东财 → 同花顺。"""
    def fetch():
        from . import eastmoney
        try:
            return eastmoney.boards("industry")
        except Exception:
            pass
        ak = _ak()
        try:
            df = _retry(lambda: ak.stock_board_industry_name_em(), tries=2)
            return df.rename(columns={"板块名称": "board", "涨跌幅": "pct_chg", "上涨家数": "up", "下跌家数": "down",
                                      "领涨股票": "leader", "换手率": "turnover"})
        except Exception:
            df = _retry(lambda: ak.stock_board_industry_summary_ths())
            return df.rename(columns={"板块": "board", "涨跌幅": "pct_chg", "上涨家数": "up", "下跌家数": "down",
                                      "领涨股": "leader", "净流入": "net_inflow"}).assign(
                net_inflow=lambda d: pd.to_numeric(d["net_inflow"], errors="coerce") * 1e8)  # 同花顺单位为亿
    return _cached(f"boards_{_today()}", fetch, max_age_hours=0.25, final_after_close=True)


def _today() -> str:
    return pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y%m%d")
