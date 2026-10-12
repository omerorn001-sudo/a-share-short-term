"""东方财富数据中心（data.eastmoney.com）接口：融资融券、龙虎榜、机构调研，以及个股资料与资金流。"""
from __future__ import annotations

import random
import time

import pandas as pd
import requests

from . import eastmoney as em

DC_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
_s = requests.Session()
_s.headers.update({**em.HEADERS, "Referer": "https://data.eastmoney.com/"})


def query(report: str, filt: str = "", sort: str = "", desc: bool = True, page_size: int = 500,
          max_pages: int = 20, columns: str = "ALL") -> pd.DataFrame:
    rows, page = [], 1
    while page <= max_pages:
        p = {"reportName": report, "columns": columns, "pageNumber": page, "pageSize": page_size,
             "source": "WEB", "client": "WEB"}
        if filt:
            p["filter"] = filt
        if sort:
            p["sortColumns"], p["sortTypes"] = sort, -1 if desc else 1
        j, last = None, None
        for i in range(6):
            try:
                j = _s.get(DC_URL, params=p, timeout=10).json()
                break
            except Exception as e:
                last = e
                time.sleep(0.5 * (i + 1) + random.random() * 0.3)
        if j is None:
            raise last
        res = j.get("result") or {}
        data = res.get("data") or []
        rows += data
        if page >= (res.get("pages") or 1) or not data:
            break
        page += 1
    return pd.DataFrame(rows)


def _d(date) -> str:
    return pd.Timestamp(date).strftime("%Y-%m-%d")


# ---------- 融资融券 ----------
def margin_market(n: int = 30) -> pd.DataFrame:
    """两市融资融券合计（日）。RZYE 融资余额，RZJME 融资净买入，单位元。"""
    df = query("RPTA_RZRQ_LSHJ", sort="DIM_DATE", page_size=n, max_pages=1)
    df["date"] = pd.to_datetime(df["DIM_DATE"])
    return df.sort_values("date").reset_index(drop=True)


def margin_stock(code: str, n: int = 30) -> pd.DataFrame:
    """个股融资融券明细（日）。RZYEZB 融资余额占流通市值 %。"""
    df = query("RPTA_WEB_RZRQ_GGMX", filt=f'(SCODE="{code}")', sort="DATE", page_size=n, max_pages=1)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["DATE"])
    return df.sort_values("date").reset_index(drop=True)


# ---------- 龙虎榜 ----------
def lhb_daily(start, end=None) -> pd.DataFrame:
    filt = f"(TRADE_DATE>='{_d(start)}')" + (f"(TRADE_DATE<='{_d(end)}')" if end else "")
    return query("RPT_DAILYBILLBOARD_DETAILSNEW", filt=filt, sort="TRADE_DATE")


def lhb_stock(code: str, start) -> pd.DataFrame:
    """个股近期上榜记录（同一天多个上榜原因会有多行）。"""
    return query("RPT_DAILYBILLBOARD_DETAILSNEW", filt=f'(SECURITY_CODE="{code}")(TRADE_DATE>=\'{_d(start)}\')',
                 sort="TRADE_DATE")


def lhb_seats(code: str, date) -> pd.DataFrame:
    """某日上榜席位（买入前五 + 卖出前五），含 side 列。"""
    f = f'(SECURITY_CODE="{code}")(TRADE_DATE=\'{_d(date)}\')'
    buy = query("RPT_BILLBOARD_DAILYDETAILSBUY", filt=f, sort="BUY").assign(side="买")
    sell = query("RPT_BILLBOARD_DAILYDETAILSSELL", filt=f, sort="SELL").assign(side="卖")
    df = pd.concat([buy, sell], ignore_index=True)
    if not df.empty:
        df = df.drop_duplicates(subset=["OPERATEDEPT_NAME", "side"])
    return df


def lhb_institution_net(date) -> pd.DataFrame:
    """某日全市场机构专用席位买卖（用于大盘机构情绪）。"""
    f = f"(TRADE_DATE='{_d(date)}')"
    buy = query("RPT_BILLBOARD_DAILYDETAILSBUY", filt=f, sort="BUY")
    sell = query("RPT_BILLBOARD_DAILYDETAILSSELL", filt=f, sort="SELL")
    df = pd.concat([buy, sell], ignore_index=True)
    if df.empty:
        return df
    df = df.drop_duplicates(subset=["SECURITY_CODE", "OPERATEDEPT_NAME", "TRADE_ID"])
    return df[df["OPERATEDEPT_NAME"].astype(str).str.contains("机构专用")]


# ---------- 机构调研 ----------
def surveys(start) -> pd.DataFrame:
    """机构调研事件（每次调研一行，SUM 为参与机构数）。按公告日筛选。"""
    df = query("RPT_ORG_SURVEYNEW", filt=f'(NUMBERNEW="1")(NOTICE_DATE>=\'{_d(start)}\')', sort="NOTICE_DATE")
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["RECEIVE_START_DATE"].fillna(df["NOTICE_DATE"]))
    return df


def surveys_stock(code: str, start) -> pd.DataFrame:
    df = query("RPT_ORG_SURVEYNEW", filt=f'(SECURITY_CODE="{code}")(NUMBERNEW="1")(NOTICE_DATE>=\'{_d(start)}\')',
               sort="NOTICE_DATE")
    if not df.empty:
        df["date"] = pd.to_datetime(df["RECEIVE_START_DATE"].fillna(df["NOTICE_DATE"]))
    return df


# ---------- 个股资料与资金流（push2） ----------
def stock_profile(code: str) -> dict:
    """行业、地区、概念、市值、PE、换手率、量比。"""
    j = em._get("/api/qt/stock/get", {"secid": em.secid_of(code), "fltt": 2, "invt": 2,
                                      "fields": "f43,f50,f57,f58,f116,f117,f127,f128,f129,f162,f168,f170"}, tries=5)
    d = j["data"] or {}
    return {"code": d.get("f57"), "name": d.get("f58"), "price": d.get("f43"), "pct_chg": d.get("f170"),
            "volume_ratio": d.get("f50"), "turnover": d.get("f168"), "total_mv": d.get("f116"),
            "float_mv": d.get("f117"), "industry": d.get("f127"), "region": d.get("f128"),
            "concepts": d.get("f129"), "pe_ttm": d.get("f162")}


def fund_flow(code: str, days: int = 10) -> pd.DataFrame:
    """个股日度主力资金净流入（元）。接口直连 → 网页版爬虫（无头浏览器打开资金流向页，截获页面自身请求）。"""
    try:
        return _fund_flow_api(code, days)
    except Exception as e:
        api_err = e
    try:
        return _fund_flow_page(code, days)
    except Exception as e:
        page_err = e
    try:                                            # 第三层：外部浏览器（不同出口 IP）
        from . import browser_fetch as bf
        u = bf.fund_flow_url(em.secid_of(code), days)
        j = bf.fetch_json([u])[u]
        if isinstance(j, Exception):
            raise j
        return _parse_fflow(j, days)
    except Exception as e:
        raise RuntimeError(f"接口失败({api_err!r:.50})；网页版失败({page_err!r:.40})；外部浏览器失败({e!r:.40})")


def _fund_flow_page(code: str, days: int = 10) -> pd.DataFrame:
    import json
    import re
    from playwright.sync_api import sync_playwright
    code = str(code).zfill(6)
    got = {}
    with sync_playwright() as p:
        import shutil
        exe = shutil.which("chromium") or shutil.which("chromium-browser") or shutil.which("google-chrome")
        br = p.chromium.launch(headless=True, args=["--no-sandbox"], executable_path=exe)
        pg = br.new_page(user_agent=em.HEADERS["User-Agent"])

        def on_resp(r):
            if "fflow/daykline" in r.url and "body" not in got:
                try:
                    got["body"] = r.text()
                except Exception:
                    pass
        pg.on("response", on_resp)
        pg.goto(f"https://data.eastmoney.com/zjlx/{code}.html", wait_until="domcontentloaded", timeout=30000)
        for _ in range(30):
            if "body" in got:
                break
            pg.wait_for_timeout(500)
        br.close()
    if "body" not in got:
        raise RuntimeError("网页未返回资金流数据")
    txt = got["body"]
    txt = txt[txt.find("{"): txt.rfind("}") + 1]
    j = json.loads(txt)
    return _parse_fflow(j, days)


def _parse_fflow(j: dict, days: int) -> pd.DataFrame:
    rows = [k.split(",")[:7] for k in ((j.get("data") or {}).get("klines") or [])][-days:]
    df = pd.DataFrame(rows, columns=["date", "main", "small", "mid", "l", "xl", "_"])
    for c in ["main", "small", "mid", "l", "xl"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    if df.empty:
        raise RuntimeError("资金流为空")
    return df.drop(columns="_")


def _fund_flow_api(code: str, days: int = 10) -> pd.DataFrame:
    j = em._get("/api/qt/stock/fflow/daykline/get", {
        "secid": em.secid_of(code), "lmt": days, "klt": 101,
        "fields1": "f1,f2,f3,f7", "fields2": "f51,f52,f53,f54,f55,f56,f57"}, hosts=em.HIS_HOSTS + em.HOSTS, tries=5)
    return _parse_fflow(j, days)


def industry_map() -> pd.DataFrame:
    """全市场 代码→行业 映射（东财行业），用于把调研/龙虎榜聚合到板块。

    优先用数据中心财报表的行业字段（约 15 秒），失败再用行情列表（60 页，较慢）。
    """
    now = pd.Timestamp.now()
    ends = [q for q in pd.date_range(now - pd.Timedelta(days=400), now - pd.Timedelta(days=45), freq="QE")][::-1]
    for q in ends[:3]:
        try:
            df = query("RPT_LICO_FN_CPD", filt=f"(REPORTDATE='{q:%Y-%m-%d}')",
                       columns="SECURITY_CODE,SECURITY_NAME_ABBR,PUBLISHNAME", page_size=500, max_pages=30)
            if len(df) > 3000:
                return (df.rename(columns={"SECURITY_CODE": "code", "SECURITY_NAME_ABBR": "name", "PUBLISHNAME": "industry"})
                        .drop_duplicates("code").reset_index(drop=True))
        except Exception:
            continue
    return em.clist(em.FS_A, {"f12": "code", "f14": "name", "f100": "industry"}, sort_field="f12")
