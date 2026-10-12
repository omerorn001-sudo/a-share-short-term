"""腾讯行情备用源（qt.gtimg.cn / web.ifzq.gtimg.cn）。东财 push2 被限流时使用。

quotes：批量实时快照，含成交额、换手率、量比、流通市值（东财快照的主要替代）。
kline：日 K（含当天），无成交额；当天成交额由 quotes 补齐。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

_S = requests.Session()
_S.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"})


def prefixed(code: str) -> str:
    c = str(code).lower()
    if c[:2] in ("sh", "sz", "bj"):
        return c
    c = c.zfill(6)
    return ("sh" if c.startswith(("6", "9", "5")) else "bj" if c.startswith(("8", "4")) else "sz") + c


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _quote_batch(syms: list[str]) -> list[dict]:
    for _ in range(3):
        try:
            t = _S.get("https://qt.gtimg.cn/q=" + ",".join(syms), timeout=10).content.decode("gbk", "ignore")
            break
        except Exception:
            continue
    else:
        return []
    out = []
    for line in t.split(";"):
        if '="' not in line:
            continue
        s = line.split('="', 1)[1].rstrip('"\n').split("~")
        if len(s) < 50:
            continue
        amt = _num(s[37])
        fmv, tmv = _num(s[44]), _num(s[45])
        out.append({"code": s[2], "name": s[1], "price": _num(s[3]), "prev_close": _num(s[4]), "open": _num(s[5]),
                    "volume": (_num(s[6]) or 0) * 100, "pct_chg": _num(s[32]), "high": _num(s[33]), "low": _num(s[34]),
                    "amount": amt * 1e4 if amt is not None else None, "turnover": _num(s[38]), "pe_ttm": _num(s[39]),
                    "float_mv": fmv * 1e8 if fmv else None, "total_mv": tmv * 1e8 if tmv else None,
                    "pb": _num(s[46]), "limit_up": _num(s[47]), "limit_down": _num(s[48]),
                    "volume_ratio": _num(s[49]), "time": s[30]})
    return out


def quotes(codes, batch: int = 60, workers: int = 4) -> pd.DataFrame:
    syms = [prefixed(c) for c in codes]
    chunks = [syms[i:i + batch] for i in range(0, len(syms), batch)]
    with ThreadPoolExecutor(workers) as ex:
        rows = [r for part in ex.map(_quote_batch, chunks) for r in part]
    return pd.DataFrame(rows)


def kline(code: str, n: int = 640, fq: str = "qfq") -> pd.DataFrame:
    """日 K（前复权默认）。volume 单位：股。amount 只有当天（来自实时快照），历史为空。"""
    sym = prefixed(code)
    j = _S.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
               params={"param": f"{sym},day,,,{n},{fq}"}, timeout=10).json()
    d = j["data"][sym]
    rows = d.get(f"{fq}day") or d.get("day") or []
    df = pd.DataFrame([r[:6] for r in rows], columns=["date", "open", "close", "high", "low", "volume"])
    df["date"] = pd.to_datetime(df["date"])
    for c in ["open", "close", "high", "low", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["volume"] = df["volume"] * 100
    df["pct_chg"] = df["close"].pct_change() * 100
    df["amount"] = float("nan")
    q = quotes([sym])
    if len(q) and len(df) and str(q["time"].iloc[0])[:8] == df["date"].iloc[-1].strftime("%Y%m%d"):
        df.loc[df.index[-1], "amount"] = q["amount"].iloc[0]
        if q["turnover"].iloc[0] is not None:
            df["turnover"] = float("nan")
            df.loc[df.index[-1], "turnover"] = q["turnover"].iloc[0]
    return df[[c for c in ["date", "open", "high", "low", "close", "volume", "amount", "turnover", "pct_chg"] if c in df]]
