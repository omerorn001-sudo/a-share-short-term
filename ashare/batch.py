"""全量候选深度分析：初筛通过的股票全部分析（不再按成交额截取前 N）。

维度：技术（趋势/买点5条/卖出预警）+ 资金（主力/融资/龙虎榜机构/机构持仓）+ 机构调研 + 板块 + 基本面。
买入信号 = 技术 5 条 + 资金 2 条（⑥主力近5日净流入>0、⑦资金面综合分≥+1），7 条全部满足。
数据尽量批量获取（一次请求覆盖全部候选），避免东财按 IP 限流。
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pandas as pd

from . import data
from . import datacenter as dc
from . import funds
from .screener import prefilter
from .strategy import prepare, sell_warnings


def funnel(snap: pd.DataFrame, cfg: dict) -> list[tuple[str, int]]:
    s = cfg["screen"]
    df = snap[snap["price"].notna() & (snap["price"] > 0)]
    out = [("全市场（当日有成交）", len(df))]
    df = df[~df["name"].str.contains("ST|退", na=False)]; out.append(("排除 ST/退市", len(df)))
    from .rules import board_of
    df = df[df["code"].map(board_of) != "bj"]; out.append(("排除北交所", len(df)))
    df = df[df["amount"] >= s["min_amount"]]; out.append((f"成交额 ≥ {s['min_amount'] / 1e8:.0f} 亿", len(df)))
    df = df[df["float_mv"].between(s["min_float_mv"], s["max_float_mv"])]
    out.append((f"流通市值 {s['min_float_mv'] / 1e8:.0f}–{s['max_float_mv'] / 1e8:.0f} 亿", len(df)))
    df = df[df["turnover"].between(s["min_turnover"], s["max_turnover"])]
    out.append((f"换手率 {s['min_turnover']}–{s['max_turnover']}%", len(df)))
    df = df[df["volume_ratio"].between(s["min_volume_ratio"], s["max_volume_ratio"])]
    out.append((f"量比 {s['min_volume_ratio']}–{s['max_volume_ratio']}", len(df)))
    return out


def tech_one(code: str, cfg: dict, end: str) -> dict | None:
    start = (pd.Timestamp(end) - pd.Timedelta(days=300)).strftime("%Y%m%d")
    h = data.stock_hist(code, start, end)
    if len(h) < 60:
        return None
    s = cfg["strategy"]
    d = prepare(h, cfg)
    x = d.iloc[-1]
    hi = float(d["high"].shift(1).rolling(s["breakout_window"]).max().iloc[-1])
    c = {"①突破": x["close"] > hi, "②放量": x["vol_ratio5"] >= s["vol_mult"], "③站上MA5": x["close"] > x["ma5"],
         "④偏离≤7%": x["bias5"] <= s["max_ma5_bias"], "⑤均线多头": (x["ma5"] > x["ma10"]) and (x["ma10"] > x["ma20"])}
    pos = sum(x["close"] > x[n] for n in ("ma5", "ma10", "ma20", "ma60"))
    trend = 2 if c["⑤均线多头"] and c["③站上MA5"] else 1 if pos >= 3 else -2 if pos <= 1 else 0
    w = sell_warnings(d, cfg).iloc[-1]
    flags = [k for k, v in w.items() if v]
    cl = d["close"]
    return {"code": code, "date": str(x["date"].date()), "close": float(x["close"]), "hi20": hi, "gap": hi / x["close"] - 1,
            "vr5": float(x["vol_ratio5"]), "bias5": float(x["bias5"]), "ma5": float(x["ma5"]), "ma10": float(x["ma10"]),
            "ma20": float(x["ma20"]), "rsi6": float(x["rsi6"]), **{k: bool(v) for k, v in c.items()},
            "技术满足": int(sum(c.values())), "趋势分": trend, "预警": "、".join(flags),
            "预警分": -min(2, len(flags)) if flags else 1, "买点分": 2 if all(c.values()) else (-1 if x["bias5"] > 0.10 else 0),
            "近20日%": float(cl.iloc[-1] / cl.iloc[-21] - 1) if len(cl) > 21 else None,
            "近60日%": float(cl.iloc[-1] / cl.iloc[-61] - 1) if len(cl) > 61 else None}


def finance_latest(codes: list[str]) -> pd.DataFrame:
    sec = [c + (".SH" if c.startswith(("6", "9")) else ".SZ") for c in codes]
    parts = []
    for i in range(0, len(sec), 50):
        inl = ",".join(f'"{s}"' for s in sec[i:i + 50])
        parts.append(dc.query("RPT_F10_FINANCE_MAINFINADATA", filt=f"(SECUCODE in ({inl}))", sort="REPORT_DATE",
                              columns="SECURITY_CODE,REPORT_DATE,REPORT_DATE_NAME,TOTALOPERATEREVE,TOTALOPERATEREVETZ,"
                                      "PARENTNETPROFIT,PARENTNETPROFITTZ,ROEJQ,ZCFZL", page_size=500, max_pages=3))
    f = pd.concat(parts, ignore_index=True)
    f["REPORT_DATE"] = pd.to_datetime(f["REPORT_DATE"])
    f = f.sort_values("REPORT_DATE").groupby("SECURITY_CODE").tail(1)
    return f.rename(columns={"SECURITY_CODE": "code", "REPORT_DATE_NAME": "报告期", "TOTALOPERATEREVE": "营收",
                             "TOTALOPERATEREVETZ": "营收同比", "PARENTNETPROFIT": "净利", "PARENTNETPROFITTZ": "净利同比",
                             "ROEJQ": "ROE", "ZCFZL": "负债率"}).drop(columns="REPORT_DATE")


def run(cfg: dict, end: str | None = None, mkt_total: int | None = None, workers: int = 4) -> tuple[pd.DataFrame, dict]:
    end = end or pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y%m%d")
    snap = data.spot()
    cfg2 = {**cfg, "screen": {**cfg["screen"], "top_n": 0}}
    cands = prefilter(snap, cfg2)
    codes = cands["code"].tolist()
    meta = {"funnel": funnel(snap, cfg), "errors": {}}
    with ThreadPoolExecutor(workers) as ex:
        tech = [t for t in ex.map(lambda c: _safe_tech(c, cfg, end), codes) if t]
    df = cands[["code", "name", "pct_chg", "amount", "turnover", "volume_ratio", "float_mv", "total_mv", "pe_ttm", "pb"]]
    df = df.merge(pd.DataFrame(tech), on="code", how="inner")
    fz = funds.fund_table(df["code"].tolist(), end)
    meta["errors"].update(fz.attrs.get("errors", {}))
    df = df.merge(fz.drop(columns=[c for c in ("float_mv", "total_mv") if c in fz]), on="code", how="left")
    # 调研（近90天，全市场一次取回）
    try:
        sv = dc.surveys((pd.Timestamp(end) - pd.Timedelta(days=90)).strftime("%Y-%m-%d"))
        sv["SECURITY_CODE"] = sv["SECURITY_CODE"].astype(str).str.zfill(6)
        g = sv.groupby("SECURITY_CODE").agg(调研次数=("SECURITY_CODE", "size"),
                                            调研家次=("SUM", lambda x: pd.to_numeric(x, errors="coerce").sum()))
        df = df.merge(g, left_on="code", right_index=True, how="left")
    except Exception as e:
        meta["errors"]["surveys"] = repr(e)[:80]
    df[["调研次数", "调研家次"]] = df.reindex(columns=["调研次数", "调研家次"]).fillna(0)
    # 行业与板块强度：用全市场快照按东财行业等权计算，保证每只股票都能匹配
    try:
        im = data._cached("industry_map", dc.industry_map, max_age_hours=24 * 7)
        im["code"] = im["code"].astype(str).str.zfill(6)
        s2 = snap.merge(im[["code", "industry"]], on="code", how="inner")
        b = s2.groupby("industry")["pct_chg"].mean().sort_values(ascending=False)
        rank = pd.DataFrame({"板块涨跌%": b.round(2), "板块排名": range(1, len(b) + 1)})
        meta["n_boards"] = len(b)
        df = df.merge(im[["code", "industry"]], on="code", how="left").merge(rank, left_on="industry", right_index=True, how="left")
    except Exception as e:
        meta["errors"]["boards"] = repr(e)[:80]
    try:
        df = df.merge(finance_latest(df["code"].tolist()), on="code", how="left")
    except Exception as e:
        meta["errors"]["finance"] = repr(e)[:80]
    df = conclude(df, meta.get("n_boards") or 1, mkt_total)
    return df, meta


def _safe_tech(c, cfg, end):
    try:
        return tech_one(c, cfg, end)
    except Exception as e:
        print(f"[跳过] {c}: {e!r}"[:100])
        return None


def conclude(df: pd.DataFrame, nb: int, mkt_total: int | None) -> pd.DataFrame:
    out = []
    for _, r in df.iterrows():
        r = r.to_dict()
        sv = 1 if (r.get("调研次数", 0) >= 2 or r.get("调研家次", 0) >= 20) else 0
        rk = r.get("板块排名")
        bd = 0 if pd.isna(rk) else 1 if rk <= nb * 0.2 else -1 if rk >= nb * 0.8 else 0
        fd, risk = 0, []
        np_, npy, pe = r.get("净利"), r.get("净利同比"), r.get("pe_ttm")
        if np_ is not None and not pd.isna(np_) and np_ < 0:
            fd -= 1; risk.append(f"{r.get('报告期')}亏损 {np_ / 1e8:.2f}亿")
        elif npy is not None and not pd.isna(npy):
            fd += 1 if npy >= 30 else -1 if npy <= -30 else 0
        if pe is not None and not pd.isna(pe) and pe > 150:
            risk.append(f"PE {pe:.0f}倍")
        tech = r["趋势分"] + r["买点分"] + r["预警分"]
        fund = r.get("资金分") or 0
        total = tech + fund + sv + bd + fd
        sig = r["技术满足"] == 5 and bool(r.get("⑥主力5日净流入")) and bool(r.get("⑦资金分≥1"))
        tech_only = r["技术满足"] == 5
        near = r["技术满足"] == 4 and not r["①突破"] and r["gap"] <= 0.05
        if sig and total >= 3 and (mkt_total is None or mkt_total > -3):
            act = "买入"
        elif sig:
            act = "信号成立·大盘偏弱观察"
        elif tech_only:
            act = "技术触发·资金不支持"
        elif near and fund >= 1 and total >= 3:
            act = "重点观察"
        elif total >= 2 and r["⑤均线多头"]:
            act = "观察"
        else:
            act = "回避"
        out.append({**r, "调研分": sv, "板块分": bd, "基本面分": fd, "技术分": tech, "总分": total,
                    "7条满足": r["技术满足"] + int(bool(r.get("⑥主力5日净流入"))) + int(bool(r.get("⑦资金分≥1"))),
                    "买入信号": sig, "结论": act, "风险": "；".join(risk)})
    res = pd.DataFrame(out)
    order = {"买入": 0, "信号成立·大盘偏弱观察": 1, "技术触发·资金不支持": 2, "重点观察": 3, "观察": 4, "回避": 5}
    res["_o"] = res["结论"].map(order)
    return res.sort_values(["_o", "总分", "amount"], ascending=[True, False, False]).drop(columns="_o").reset_index(drop=True)
