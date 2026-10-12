"""个股档案：基本面简介、近1年走势图、近3个月机构调研明细、近3个月龙虎榜明细。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import requests

from . import data
from . import datacenter as dc

F10 = "https://datacenter.eastmoney.com/securities/api/data/v1/get"


def _secu(code: str) -> str:
    code = str(code).zfill(6)
    return code + (".SH" if code.startswith(("6", "9")) else ".BJ" if code.startswith(("8", "4")) else ".SZ")


def _f10(report: str, code: str, n: int = 1, sort: str | None = None) -> list[dict]:
    p = {"reportName": report, "columns": "ALL", "filter": f'(SECUCODE="{_secu(code)}")', "pageSize": n}
    if sort:
        p.update(sortColumns=sort, sortTypes="-1")
    j = requests.get(F10, params=p, timeout=12, headers={"User-Agent": "Mozilla/5.0"}).json()
    return (j.get("result") or {}).get("data") or []


def basic(code: str) -> dict:
    d = (_f10("RPT_F10_BASIC_ORGINFO", code) or [{}])[0]
    return {"公司": d.get("ORG_NAME"), "行业": d.get("EM2016"), "地区": d.get("PROVINCE"),
            "上市日期": str(d.get("LISTING_DATE") or "")[:10], "主营": d.get("MAIN_BUSINESS"),
            "简介": (d.get("ORG_PROFILE") or "").strip(), "实控人": d.get("ACTUAL_HOLDER"), "员工": d.get("EMP_NUM")}


def finance(code: str, n: int = 4) -> pd.DataFrame:
    rows = _f10("RPT_F10_FINANCE_MAINFINADATA", code, n, "REPORT_DATE")
    out = []
    for x in rows:
        out.append({"报告期": x.get("REPORT_DATE_NAME"),
                    "营收(亿)": round((x.get("TOTALOPERATEREVE") or 0) / 1e8, 2),
                    "营收同比%": round(x.get("TOTALOPERATEREVETZ") or 0, 1),
                    "归母净利(亿)": round((x.get("PARENTNETPROFIT") or 0) / 1e8, 2),
                    "净利同比%": round(x.get("PARENTNETPROFITTZ") or 0, 1),
                    "ROE%": round(x.get("ROEJQ") or 0, 2), "毛利率%": round(x.get("XSMLL") or 0, 1),
                    "资产负债率%": round(x.get("ZCFZL") or 0, 1)})
    return pd.DataFrame(out)


def valuation(code: str) -> dict:
    from . import tencent
    q = tencent.quotes([code])
    if q.empty:
        return {}
    r = q.iloc[0]
    return {"名称": r["name"], "收盘": r["price"], "涨跌%": r["pct_chg"], "PE(TTM)": r["pe_ttm"], "PB": r["pb"],
            "流通市值(亿)": round(r["float_mv"] / 1e8, 1) if r["float_mv"] else None,
            "总市值(亿)": round(r["total_mv"] / 1e8, 1) if r["total_mv"] else None, "换手%": r["turnover"], "量比": r["volume_ratio"]}


def year_hist(code: str) -> pd.DataFrame:
    end = data._today()
    start = (pd.Timestamp(end) - pd.Timedelta(days=380)).strftime("%Y%m%d")
    return data.stock_hist(code, start, end)


def year_stats(h: pd.DataFrame) -> dict:
    c = h["close"].reset_index(drop=True)
    last = c.iloc[-1]
    hi, lo = h["high"].max(), h["low"].min()
    st = {"近1年最高": round(hi, 2), "最高日": h.loc[h["high"].idxmax(), "date"].strftime("%Y-%m-%d"),
          "近1年最低": round(lo, 2), "最低日": h.loc[h["low"].idxmin(), "date"].strftime("%Y-%m-%d"),
          "1年区间位置": f"{(last - lo) / (hi - lo) * 100:.0f}%" if hi > lo else "—"}
    for lab, n in [("近20日%", 20), ("近3个月%", 60), ("近6个月%", 120), ("近1年%", min(len(c) - 1, 243))]:
        st[lab] = round((last / c.iloc[-n - 1] - 1) * 100, 1) if len(c) > n else None
    return st


def chart(code: str, name: str, h: pd.DataFrame, out_dir: Path, marks: dict | None = None) -> Path:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "Noto Sans SC", "WenQuanYi Zen Hei", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    h = h.copy().reset_index(drop=True)
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(10, 5.2), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    a1.plot(h["date"], h["close"], color="#222", lw=1.2, label="收盘")
    for n, col in [(20, "#f39c12"), (60, "#2980b9"), (120, "#8e44ad")]:
        a1.plot(h["date"], h["close"].rolling(n).mean(), color=col, lw=0.9, label=f"MA{n}")
    for lab, (d, px) in (marks or {}).items():
        a1.scatter([pd.Timestamp(d)], [px], s=28, zorder=5)
        a1.annotate(lab, (pd.Timestamp(d), px), fontsize=7, xytext=(3, 6), textcoords="offset points")
    for lab, px, col in [("触发价", (marks or {}).get("_trigger"), "#c0392b")]:
        pass
    a1.legend(fontsize=8, loc="upper left"); a1.grid(alpha=0.3)
    a1.set_title(f"{name}（{code}）近1年走势  收盘 {h['close'].iloc[-1]:.2f}", fontsize=11)
    up = h["close"] >= h["close"].shift(1)
    a2.bar(h["date"], h["volume"] / 1e4, color=["#e74c3c" if u else "#27ae60" for u in up], width=1.0)
    a2.set_ylabel("成交量(万股)", fontsize=8); a2.grid(alpha=0.3)
    fig.tight_layout()
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{code}_1y.png"
    fig.savefig(p, dpi=110); plt.close(fig)
    return p


def surveys_90d(code: str) -> tuple[pd.DataFrame, int]:
    start = (pd.Timestamp.now() - pd.Timedelta(days=92)).strftime("%Y-%m-%d")
    s = dc.query("RPT_ORG_SURVEYNEW", filt=f'(SECURITY_CODE="{code}")(NOTICE_DATE>=\'{start}\')', sort="NOTICE_DATE")
    if s.empty:
        return pd.DataFrame(), 0
    s["日期"] = pd.to_datetime(s["RECEIVE_START_DATE"].fillna(s["NOTICE_DATE"])).dt.strftime("%Y-%m-%d")
    g = s.groupby(["日期", "RECEIVE_WAY_EXPLAIN"]).agg(
        机构家数=("RECEIVE_OBJECT", "nunique"),
        机构类型=("ORG_TYPE", lambda x: "、".join(f"{k}{v}" for k, v in x.value_counts().head(4).items())),
        代表机构=("RECEIVE_OBJECT", lambda x: "、".join(list(dict.fromkeys(x))[:5]))).reset_index()
    g = g.rename(columns={"RECEIVE_WAY_EXPLAIN": "方式"}).sort_values("日期", ascending=False)
    return g, len(g)


def lhb_90d(code: str) -> pd.DataFrame:
    start = (pd.Timestamp.now() - pd.Timedelta(days=92)).strftime("%Y-%m-%d")
    l = dc.lhb_stock(code, start)
    if l.empty:
        return l
    rows = []
    for d, grp in l.groupby("TRADE_DATE", sort=False):
        try:
            seats = dc.lhb_seats(code, d)
        except Exception:
            seats = pd.DataFrame()
        inst = nb = None
        top = ""
        if not seats.empty:
            seats["NET"] = pd.to_numeric(seats["NET"], errors="coerce")
            name = seats["OPERATEDEPT_NAME"].astype(str)
            inst = seats.loc[name.str.contains("机构专用"), "NET"].sum() / 1e8
            nb = seats.loc[name.str.contains("沪股通|深股通"), "NET"].sum() / 1e8
            b = seats[seats["side"] == "买"].sort_values("BUY", ascending=False).head(3)
            top = "、".join(n.replace("股份有限公司", "").replace("证券营业部", "营业部")[:22] for n in b["OPERATEDEPT_NAME"])
        r = grp.iloc[0]
        rows.append({"日期": str(d)[:10], "涨跌%": round(float(r["CHANGE_RATE"]), 2),
                     "上榜原因": "；".join(grp["EXPLANATION"].astype(str).unique()),
                     "龙虎榜净买(亿)": round(grp["BILLBOARD_NET_AMT"].astype(float).iloc[0] / 1e8, 2),
                     "机构净买(亿)": None if inst is None else round(inst, 2),
                     "北向净买(亿)": None if nb is None else round(nb, 2), "买入前三": top,
                     "上榜后5日%": None if pd.isna(r.get("D5_CLOSE_ADJCHRATE")) else round(float(r["D5_CLOSE_ADJCHRATE"]), 1)})
    return pd.DataFrame(rows)
