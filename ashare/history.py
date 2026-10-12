"""多周期历史对比：情绪（涨跌停/炸板/连板）、融资、板块、指数在 20日 / 3个月 / 6个月 / 1年 的位置。

情绪历史：东财涨停池只提供当天，故用全市场个股日 K（腾讯源，前复权涨跌幅）自行统计每日涨跌停，
结果按日缓存，次日只增量抓取最近 10 天。
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from . import data
from . import datacenter as dc
from .tencent import prefixed

WINDOWS = [("近20日", 20), ("近3个月", 60), ("近6个月", 120), ("近1年", 250)]
INDEXES = [("上证指数", "sh000001"), ("深证成指", "sz399001"), ("创业板指", "sz399006"), ("科创50", "sh000688")]
CACHE = data.CACHE_DIR
_S = requests.Session()
_S.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"})


_fail = {"tencent": 0, "sina": 0, "eastmoney": 0}


def _ohlc_tencent(code, n):
    sym = prefixed(code)
    r = _S.get("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get", params={"param": f"{sym},day,,,{n + 1},qfq"}, timeout=10)
    d = r.json()["data"][sym]                       # 被 WAF 拦截时返回 HTML，这里会抛错
    rows = d.get("qfqday") or d.get("day") or []
    return pd.DataFrame([x[:5] for x in rows], columns=["date", "open", "close", "high", "low"])


def _ohlc_sina(code, n):
    import json
    r = _S.get("https://quotes.sina.cn/cn/api/jsonp_v2.php/var%20_x=/CN_MarketDataService.getKLineData",
               params={"symbol": prefixed(code), "scale": 240, "ma": "no", "datalen": n + 1}, timeout=10)
    t = r.text
    rows = json.loads(t[t.index("(") + 1: t.rindex(")")])     # 不复权；除权日涨跌幅会失真（影响很小）
    return pd.DataFrame(rows).rename(columns={"day": "date"})[["date", "open", "close", "high", "low"]]


def _ohlc_eastmoney(code, n):
    from . import eastmoney as em
    j = em._get("/api/qt/stock/kline/get", {"secid": em.secid_of(code), "klt": 101, "fqt": 1, "lmt": n + 1,
                "end": "20500101", "fields1": "f1", "fields2": "f51,f52,f53,f54,f55"}, hosts=em.HIS_HOSTS, tries=2, timeout=6)
    rows = [x.split(",") for x in (j["data"] or {}).get("klines", [])]
    return pd.DataFrame(rows, columns=["date", "open", "close", "high", "low"])


_SRC = {"eastmoney": _ohlc_eastmoney, "sina": _ohlc_sina, "tencent": _ohlc_tencent}


def _k(code: str, n: int):
    """三个源轮流分摊请求（降低单一源被限流的概率），某源连续失败 8 次后跳过。"""
    names = list(_SRC)
    k = hash(code) % len(names)
    order = names[k:] + names[:k]
    for src in order:
        if _fail[src] >= 8:
            continue
        try:
            a = _SRC[src](code, n)
            if a.empty:
                return code, None
            _fail[src] = 0
            a["date"] = pd.to_datetime(a["date"])
            a = a.set_index("date").astype(float)
            prev = a["close"].shift(1)
            pct = (a["close"] / prev - 1) * 100
            # 收在最高价=1，收在最低价=-1（一字板按涨跌方向），用于区分“封板”与“盘中触及”
            flag = np.where(a["close"] >= a["high"] - 1e-6, 1, np.where(a["close"] <= a["low"] + 1e-6, -1, 0))
            flag = np.where((a["high"] - a["low"]).abs() < 1e-6, np.sign(pct.fillna(0)), flag)
            return code, pd.DataFrame({"pct": pct, "hpct": (a["high"] / prev - 1) * 100 + flag * 1000}).iloc[1:]
        except Exception:
            _fail[src] += 1
            time.sleep(0.2)
    return code, None


def _limit(code: str, name: str) -> float:
    # 注：沪深主板 ST 股涨跌幅限制已与主板一致（10%），实测 *ST 股今日 -10% 跌停
    if code.startswith(("300", "301", "688", "689")):
        return 20.0
    if code.startswith(("8", "4", "92")):
        return 30.0
    return 10.0


def stock_matrix(n: int = 260, workers: int = 6) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """全市场 涨跌幅 / 最高涨幅 矩阵（行=日期，列=代码），带增量缓存。"""
    today = data._today()
    p_pct, p_h = CACHE / f"mat2_pct_{today}.csv.gz", CACHE / f"mat2_hpct_{today}.csv.gz"
    sp = data.spot()
    names = sp.set_index("code")["name"]
    if p_pct.exists() and not data._intraday_stale(p_pct):
        return pd.read_csv(p_pct, index_col=0, parse_dates=True), pd.read_csv(p_h, index_col=0, parse_dates=True), names
    old = sorted(CACHE.glob("mat2_pct_*.csv.gz"))
    base_p = base_h = None
    if old:
        base_p = pd.read_csv(old[-1], index_col=0, parse_dates=True)
        base_h = pd.read_csv(str(old[-1]).replace("mat2_pct_", "mat2_hpct_"), index_col=0, parse_dates=True)
        if len(base_p) >= n - 5:
            n = 10                                   # 增量：只补最近 10 天
        else:
            base_p = base_h = None
    codes = [c for c in sp["code"] if not str(c).startswith(("9", "2"))]   # 去掉 B 股
    with ThreadPoolExecutor(workers) as ex:
        res = dict(ex.map(lambda c: _k(c, n), codes))
    pct = pd.DataFrame({c: d["pct"] for c, d in res.items() if d is not None})
    hp = pd.DataFrame({c: d["hpct"] for c, d in res.items() if d is not None})
    if base_p is not None:
        pct = pct.combine_first(base_p).sort_index()
        hp = hp.combine_first(base_h).sort_index()
    pct, hp = pct.iloc[-max(n, 260):].round(3), hp.iloc[-max(n, 260):].round(3)
    pct.to_csv(p_pct); hp.to_csv(p_h)
    for f in old:                                    # 只保留最新一份
        if f != p_pct:
            f.unlink(missing_ok=True); Path(str(f).replace("mat2_pct_", "mat2_hpct_")).unlink(missing_ok=True)
    return pct, hp, names


def sentiment_history(pct: pd.DataFrame, hp: pd.DataFrame, names: pd.Series) -> pd.DataFrame:
    keep = [c for c in pct.columns if not str(names.get(c, "")).startswith(("N", "C"))]   # 新股无涨跌幅限制
    pct, hp = pct[keep], hp[keep]
    flag = np.round(hp / 1000)
    hp = hp - flag * 1000
    lim = pd.Series({c: _limit(c, names.get(c, "")) for c in pct.columns})
    thr = lim * 0.985
    zt = pct.ge(thr, axis=1) & flag.eq(1)
    dt = pct.le(-thr, axis=1) & flag.eq(-1)
    touch = hp.ge(thr, axis=1)
    zb = touch & ~zt
    # 连板：连续涨停天数
    streak = _streak(zt)
    prem = (pct.where(zt.shift(1).fillna(False).astype(bool))).mean(axis=1)    # 昨日涨停股今日平均涨幅
    out = pd.DataFrame({
        "上涨家数": pct.gt(0).sum(axis=1), "下跌家数": pct.lt(0).sum(axis=1),
        "涨停": zt.sum(axis=1), "跌停": dt.sum(axis=1), "炸板": zb.sum(axis=1),
        "最高连板": streak.max(axis=1), "涨停次日溢价%": prem.round(2)})
    out["炸板率%"] = (out["炸板"] / (out["涨停"] + out["炸板"]).replace(0, np.nan) * 100).round(1)
    out["上涨占比%"] = (out["上涨家数"] / (out["上涨家数"] + out["下跌家数"]) * 100).round(1)
    return out[pct.notna().sum(axis=1) > len(pct.columns) * 0.5]


def _streak(zt: pd.DataFrame) -> pd.DataFrame:
    a = zt.to_numpy().astype(int)
    s = np.zeros_like(a)
    for i in range(len(a)):
        s[i] = (s[i - 1] + 1) * a[i] if i else a[i]
    return pd.DataFrame(s, index=zt.index, columns=zt.columns)


def window_table(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """每列：今日值 + 各窗口均值 + 今日在近1年的分位。"""
    rows = []
    for c in cols:
        s = df[c].dropna()
        r = {"指标": c, "今日": s.iloc[-1]}
        for lab, n in WINDOWS:
            r[f"{lab}均值"] = round(s.iloc[-n:].mean(), 1)
        r["近1年分位"] = f"{(s.iloc[-250:] < s.iloc[-1]).mean() * 100:.0f}%"
        rows.append(r)
    return pd.DataFrame(rows)


def margin_windows() -> tuple[pd.DataFrame, dict]:
    m = dc.margin_market(270).sort_values("date").reset_index(drop=True)
    bal = m["RZYE"] / 1e8
    net = pd.to_numeric(m["RZJME"], errors="coerce") / 1e8 if "RZJME" in m else bal.diff()
    rows = []
    for lab, n in WINDOWS:
        if len(bal) > n:
            rows.append({"区间": lab, "期初余额(亿)": round(bal.iloc[-n - 1], 0), "期末余额(亿)": round(bal.iloc[-1], 0),
                         "变化(亿)": round(bal.iloc[-1] - bal.iloc[-n - 1], 0),
                         "变化%": round((bal.iloc[-1] / bal.iloc[-n - 1] - 1) * 100, 2),
                         "日均净买(亿)": round(net.iloc[-n:].mean(), 1),
                         "区间最高(亿)": round(bal.iloc[-n:].max(), 0), "区间最低(亿)": round(bal.iloc[-n:].min(), 0)})
    pctl = (bal.iloc[-250:] < bal.iloc[-1]).mean() * 100
    return pd.DataFrame(rows), {"date": m["date"].iloc[-1], "balance": bal.iloc[-1], "pctl": pctl}


def index_windows() -> pd.DataFrame:
    rows = []
    for name, sym in INDEXES:
        try:
            d = data.index_hist(sym)
        except Exception as e:
            rows.append({"指数": name, "收盘": f"获取失败 {e!r}"[:40]}); continue
        c = d["close"].reset_index(drop=True)
        last = c.iloc[-1]
        r = {"指数": name, "日期": d["date"].iloc[-1].strftime("%m-%d"), "收盘": round(last, 2),
             "今日%": round((last / c.iloc[-2] - 1) * 100, 2)}
        for lab, n in WINDOWS:
            r[f"{lab}%"] = round((last / c.iloc[-n - 1] - 1) * 100, 1) if len(c) > n else None
        hi, lo = c.iloc[-250:].max(), c.iloc[-250:].min()
        r["1年区间位置"] = f"{(last - lo) / (hi - lo) * 100:.0f}%"
        ma = {n: c.rolling(n).mean().iloc[-1] for n in (5, 20, 60, 250)}
        r["站上均线"] = "/".join(f"MA{n}" for n, v in ma.items() if last > v) or "无"
        rows.append(r)
    return pd.DataFrame(rows)


def amount_windows() -> pd.DataFrame | None:
    try:
        sh, sz = data.index_hist("sh000001"), data.index_hist("sz399001")
    except Exception:
        return None
    tot = (sh.set_index("date")["amount"].add(sz.set_index("date")["amount"], fill_value=0) / 1e8).dropna()
    r = {"指标": "两市成交额(亿)", "今日": round(tot.iloc[-1], 0)}
    for lab, n in WINDOWS:
        r[f"{lab}均值"] = round(tot.iloc[-n - 1:-1].mean(), 0)
    r["近1年分位"] = f"{(tot.iloc[-250:] < tot.iloc[-1]).mean() * 100:.0f}%"
    return pd.DataFrame([r])


def sector_windows(pct: pd.DataFrame, top: int = 5) -> tuple[pd.DataFrame, pd.DataFrame]:
    """行业（东财 121 个）等权指数：各窗口累计涨幅前/后 N，以及主线持续性。"""
    imap = dc.industry_map()
    imap = imap.drop_duplicates("code").set_index("code")["industry"]
    cols = [c for c in pct.columns if c in imap.index]
    ind_ret = pct[cols].T.groupby(imap.loc[cols]).mean().T / 100        # 日度等权收益
    nav = (1 + ind_ret.fillna(0)).cumprod()
    rows, ranks = [], {}
    for lab, n in [("今日", 1)] + WINDOWS:
        ret = (nav.iloc[-1] / nav.iloc[-n - 1] - 1) * 100 if len(nav) > n else None
        if ret is None:
            continue
        ret = ret.sort_values(ascending=False)
        ranks[lab] = ret.rank(ascending=False)
        rows.append({"区间": lab, "领涨": "、".join(f"{k}({v:+.1f}%)" for k, v in ret.head(top).items()),
                     "领跌": "、".join(f"{k}({v:+.1f}%)" for k, v in ret.tail(top)[::-1].items())})
    rk = pd.DataFrame(ranks)
    n = len(rk)
    # 主线：今日和近20日都在前 20%；补涨/反转：今日前 20% 但近3个月后 50%
    strong = rk[(rk["今日"] <= n * 0.2) & (rk["近20日"] <= n * 0.2)].index.tolist()
    rebound = rk[(rk["今日"] <= n * 0.2) & (rk["近3个月"] > n * 0.5)].index.tolist()
    fading = rk[(rk["今日"] > n * 0.8) & (rk["近20日"] <= n * 0.2)].index.tolist()
    summary = pd.DataFrame([{"类型": "持续主线（今日+近20日均前20%）", "行业": "、".join(strong) or "无"},
                            {"类型": "超跌反弹（今日前20%、近3个月后50%）", "行业": "、".join(rebound) or "无"},
                            {"类型": "前期强势今日掉队（近20日前20%、今日后20%）", "行业": "、".join(fading) or "无"}])
    return pd.DataFrame(rows), summary


def sector_flow_windows(top: int = 5) -> pd.DataFrame | None:
    """行业主力净流入（东财板块资金日线，接口可用时）。"""
    from . import eastmoney as em
    try:
        b = data.industry_boards()
        if "board_code" not in b:
            return None
        codes = b[["board_code", "board"]].dropna().values.tolist()
    except Exception:
        return None

    def one(x):
        code, name = x
        try:
            j = em._get("/api/qt/stock/fflow/daykline/get", {"secid": f"90.{code}", "lmt": 0, "klt": 101,
                        "fields1": "f1,f2,f3,f7", "fields2": "f51,f52"}, hosts=em.HIS_HOSTS, tries=3)
            k = [r.split(",") for r in (j["data"] or {}).get("klines", [])]
            return name, pd.Series([float(v) for _, v in k], index=pd.to_datetime([d for d, _ in k]))
        except Exception:
            return name, None
    with ThreadPoolExecutor(4) as ex:
        res = {k: v for k, v in ex.map(one, codes) if v is not None}
    if len(res) < len(codes) * 0.5:
        return None
    f = pd.DataFrame(res).sort_index() / 1e8
    rows = []
    for lab, n in [("今日", 1)] + WINDOWS:
        if len(f) < min(n, 20):
            continue
        s = f.iloc[-n:].sum().sort_values(ascending=False)
        rows.append({"区间": lab + ("" if len(f) >= n else f"(仅{len(f)}天)"),
                     "净流入前列": "、".join(f"{k}({v:+.0f}亿)" for k, v in s.head(top).items()),
                     "净流出前列": "、".join(f"{k}({v:+.0f}亿)" for k, v in s.tail(top)[::-1].items())})
    return pd.DataFrame(rows)
