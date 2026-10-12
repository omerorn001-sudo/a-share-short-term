"""资金面批量数据（一次请求覆盖全部候选股）：主力资金、融资、龙虎榜（机构/北向）、机构持仓季度变化。

资金面条件用于买入信号：技术面 5 条 + 资金面 2 条（⑥主力近5日净流入>0，⑦资金面综合分≥+1）。
"""
from __future__ import annotations

import pandas as pd

from . import datacenter as dc
from . import eastmoney as em


def _inlist(codes) -> str:
    return ",".join(f'"{c}"' for c in codes)


def _chunks(xs, n):
    for i in range(0, len(xs), n):
        yield xs[i:i + n]


# ---------- 主力资金 + 市值（push2 ulist，一次 ≤100 只） ----------
def main_flow(codes: list[str]) -> pd.DataFrame:
    """今日/5日/10日主力净流入（元）与总市值/流通市值。沙箱直连 → 外部浏览器。"""
    fields = "f12,f14,f20,f21,f62,f164,f174"
    rows = []
    for part in _chunks(list(codes), 80):
        secids = ",".join(em.secid_of(c) for c in part)
        params = {"fltt": 2, "invt": 2, "secids": secids, "fields": fields}
        import os
        j = None
        try:
            if os.environ.get("AGENT_BROWSER_CDP") or os.environ.get("ASHARE_CDP"):
                raise RuntimeError("优先外部浏览器")
            j = em._get("/api/qt/ulist.np/get", params, tries=3)
        except Exception:
            from . import browser_fetch as bf
            u = "https://push2.eastmoney.com/api/qt/ulist.np/get?" + "&".join(f"{k}={v}" for k, v in params.items())
            j = bf.fetch_json([u])[u]
            if isinstance(j, Exception):
                raise j
        rows += (j.get("data") or {}).get("diff") or []
    df = pd.DataFrame(rows).rename(columns={"f12": "code", "f14": "name", "f20": "total_mv", "f21": "float_mv",
                                            "f62": "main1", "f164": "main5", "f174": "main10"})
    for c in ["total_mv", "float_mv", "main1", "main5", "main10"]:
        df[c] = pd.to_numeric(df.get(c), errors="coerce")
    return df


# ---------- 融资 ----------
def margin(codes: list[str], end) -> pd.DataFrame:
    start = (pd.Timestamp(end) - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
    parts = [dc.query("RPTA_WEB_RZRQ_GGMX", filt=f"(SCODE in ({_inlist(p)}))(DATE>='{start}')", sort="DATE",
                      columns="DATE,SCODE,RZYE,RZJME,RZYEZB") for p in _chunks(list(codes), 60)]
    m = pd.concat(parts, ignore_index=True)
    if m.empty:
        return pd.DataFrame(columns=["code"])
    m["date"] = pd.to_datetime(m["DATE"])
    out = []
    for c, g in m.sort_values("date").groupby("SCODE"):
        y = g["RZYE"].astype(float).reset_index(drop=True)
        l = g.iloc[-1]
        b5 = y.iloc[-6] if len(y) >= 6 else y.iloc[0]
        b20 = y.iloc[-21] if len(y) >= 21 else y.iloc[0]
        out.append({"code": c, "rz_date": l["date"].date(), "rz_bal": float(l["RZYE"]), "rz_net1": float(l["RZJME"] or 0),
                    "rz_chg5": y.iloc[-1] / b5 - 1 if b5 else None, "rz_chg20": y.iloc[-1] / b20 - 1 if b20 else None,
                    "rz_net5": float(g["RZJME"].astype(float).tail(5).sum()), "rz_ratio": float(l["RZYEZB"] or 0)})
    return pd.DataFrame(out)


# ---------- 龙虎榜 ----------
def lhb(codes: list[str], end, days: int = 30) -> tuple[pd.DataFrame, pd.DataFrame]:
    """近 days 个自然日：上榜次数、龙虎榜净买、机构专用净买、北向净买。返回 (汇总, 明细)。"""
    start = (pd.Timestamp(end) - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    det, seats = [], []
    for p in _chunks(list(codes), 60):
        f = f"(SECURITY_CODE in ({_inlist(p)}))(TRADE_DATE>='{start}')"
        det.append(dc.query("RPT_DAILYBILLBOARD_DETAILSNEW", filt=f, sort="TRADE_DATE",
                            columns="SECURITY_CODE,TRADE_DATE,EXPLANATION,BILLBOARD_NET_AMT,CHANGE_RATE"))
        for rep in ("RPT_BILLBOARD_DAILYDETAILSBUY", "RPT_BILLBOARD_DAILYDETAILSSELL"):
            seats.append(dc.query(rep, filt=f, sort="TRADE_DATE",
                                  columns="SECURITY_CODE,TRADE_DATE,OPERATEDEPT_NAME,BUY,SELL,NET"))
    det = pd.concat(det, ignore_index=True)
    seats = pd.concat(seats, ignore_index=True)
    if det.empty:
        return pd.DataFrame(columns=["code"]), det
    det["TRADE_DATE"] = pd.to_datetime(det["TRADE_DATE"]).dt.date
    day = det.drop_duplicates(["SECURITY_CODE", "TRADE_DATE"])
    if not seats.empty:
        seats["TRADE_DATE"] = pd.to_datetime(seats["TRADE_DATE"]).dt.date
        seats = seats.drop_duplicates(["SECURITY_CODE", "TRADE_DATE", "OPERATEDEPT_NAME", "BUY", "SELL"])
        seats["NET"] = pd.to_numeric(seats["NET"], errors="coerce").fillna(0)
        seats["inst"] = seats["OPERATEDEPT_NAME"].astype(str).str.contains("机构专用")
        seats["north"] = seats["OPERATEDEPT_NAME"].astype(str).str.contains("股通专用")
    out = []
    for c, g in day.groupby("SECURITY_CODE"):
        s = seats[seats["SECURITY_CODE"] == c] if not seats.empty else seats
        out.append({"code": c, "lhb_n": len(g), "lhb_last": max(g["TRADE_DATE"]),
                    "lhb_net": float(pd.to_numeric(g["BILLBOARD_NET_AMT"], errors="coerce").sum()),
                    "lhb_inst": float(s.loc[s["inst"], "NET"].sum()) if len(s) else 0.0,
                    "lhb_inst_n": int(s["inst"].sum()) if len(s) else 0,
                    "lhb_north": float(s.loc[s["north"], "NET"].sum()) if len(s) else 0.0})
    return pd.DataFrame(out), det


# ---------- 机构持仓（季报，机构汇总） ----------
def org_hold(codes: list[str]) -> pd.DataFrame:
    parts = [dc.query("RPT_MAIN_ORGHOLD", filt=f'(SECURITY_CODE in ({_inlist(p)}))(ORG_TYPE="00")', sort="REPORT_DATE",
                      columns="SECURITY_CODE,REPORT_DATE,HOULD_NUM,FREESHARES_RATIO,HOLDCHA_NUM", page_size=500, max_pages=4)
             for p in _chunks(list(codes), 60)]
    o = pd.concat(parts, ignore_index=True)
    if o.empty:
        return pd.DataFrame(columns=["code"])
    o["REPORT_DATE"] = pd.to_datetime(o["REPORT_DATE"])
    out = []
    for c, g in o.sort_values("REPORT_DATE").groupby("SECURITY_CODE"):
        l = g.iloc[-1]
        p = g.iloc[-2] if len(g) >= 2 else None
        out.append({"code": c, "org_date": l["REPORT_DATE"].date(), "org_n": int(l["HOULD_NUM"] or 0),
                    "org_ratio": float(l["FREESHARES_RATIO"] or 0),
                    "org_ratio_chg": float(l["FREESHARES_RATIO"] or 0) - float(p["FREESHARES_RATIO"] or 0) if p is not None else None,
                    "org_n_chg": int(l["HOULD_NUM"] or 0) - int(p["HOULD_NUM"] or 0) if p is not None else None})
    return pd.DataFrame(out)


# ---------- 汇总与打分 ----------
def fund_table(codes: list[str], end) -> pd.DataFrame:
    codes = [str(c).zfill(6) for c in codes]
    df = pd.DataFrame({"code": codes})
    errs = {}
    for name, fn in [("main", lambda: main_flow(codes)), ("rz", lambda: margin(codes, end)),
                     ("lhb", lambda: lhb(codes, end)[0]), ("org", lambda: org_hold(codes))]:
        try:
            part = fn()
            if "name" in part:
                part = part.drop(columns="name")
            df = df.merge(part, on="code", how="left")
        except Exception as e:
            errs[name] = repr(e)[:80]
    df.attrs["errors"] = errs
    return score(df)


MAIN_TH = 0.001     # 主力净流入需超过流通市值的 0.1% 才算有效（排除几十万元级的噪声）


def _sc_main(r):
    m5, fmv = r.get("main5"), r.get("float_mv")
    if pd.isna(m5):
        return 0, "主力资金缺失"
    th = (fmv or 0) * MAIN_TH
    sc = 1 if m5 > th else -1 if m5 < -th else 0
    return sc, f"主力5日 {m5 / 1e8:+.2f}亿"


def _sc_rz(r):
    if pd.isna(r.get("rz_bal")):
        return 0, "非两融"
    c5, zb = r["rz_chg5"], r["rz_ratio"]
    sc = 1 if c5 > 0.03 else -1 if c5 < -0.03 else 0
    if zb >= 8:
        sc -= 1
    return sc, f"融资5日 {c5:+.1%}（占流通 {zb:.1f}%）"


def _sc_lhb(r):
    if pd.isna(r.get("lhb_n")):
        return 0, "近30天未上榜"
    if r["lhb_inst_n"]:
        sc = 1 if r["lhb_inst"] > 0 else -1
        return sc, f"龙虎榜{int(r['lhb_n'])}次，机构 {r['lhb_inst'] / 1e8:+.2f}亿"
    sc = 1 if r["lhb_net"] > 0 else -1 if r["lhb_net"] < 0 else 0
    return sc, f"龙虎榜{int(r['lhb_n'])}次，无机构，净买 {r['lhb_net'] / 1e8:+.2f}亿"


def _sc_org(r):
    ch = r.get("org_ratio_chg")
    if pd.isna(ch) if ch is not None else True:
        return 0, "机构持仓缺失"
    sc = 1 if ch >= 0.5 else -1 if ch <= -0.5 else 0
    return sc, f"机构持仓 {r['org_ratio']:.1f}%（环比 {ch:+.1f}pct）"


def score(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, r in df.iterrows():
        r = r.to_dict()
        items = {k: f(r) for k, f in [("主力", _sc_main), ("融资", _sc_rz), ("龙虎榜", _sc_lhb), ("机构持仓", _sc_org)]}
        fs = sum(v[0] for v in items.values())
        c6 = (not pd.isna(r.get("main5"))) and r["main5"] > (r.get("float_mv") or 0) * MAIN_TH
        rows.append({**r, "资金分": fs, "⑥主力5日净流入": bool(c6), "⑦资金分≥1": fs >= 1,
                     **{f"资金_{k}": v[1] for k, v in items.items()}, **{f"分_{k}": v[0] for k, v in items.items()}})
    return pd.DataFrame(rows)
