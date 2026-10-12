"""多维度深度分析：大盘与个股。每个维度给出 状态（利多/利空/中性/无数据）+ 具体理由，
没有数据或近期没有发生（例如没有机构调研、没上龙虎榜）也会明确写出来。"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from . import data
from . import datacenter as dc
from .strategy import prepare, sell_warnings

BULL, BEAR, NEU, NA = "利多", "利空", "中性", "无数据"
ICON = {BULL: "🟢", BEAR: "🔴", NEU: "⚪", NA: "⚫"}


@dataclass
class Dim:
    name: str
    status: str
    detail: str
    score: int = 0          # -2 ~ +2
    facts: dict = field(default_factory=dict)


def _yi(x) -> str:
    return "—" if x is None or pd.isna(x) else f"{x / 1e8:+.2f}亿" if abs(x) < 1e12 else f"{x / 1e12:.2f}万亿"


def _amt(x) -> str:
    return "—" if x is None or pd.isna(x) else f"{x / 1e8:.2f}亿"


def _safe(fn, *a, **k):
    try:
        return fn(*a, **k), None
    except Exception as e:
        return None, f"{type(e).__name__}: {str(e)[:80]}"


def _now():
    return pd.Timestamp.now(tz="Asia/Shanghai").tz_localize(None)


def _cached_df(name, fn, hours):
    return data._cached(name, fn, max_age_hours=hours)


# ======================= 公共数据（带缓存） =======================
def industry_survey_heat(days: int = 30) -> tuple[pd.DataFrame | None, str | None]:
    """近 N 天各行业机构调研次数与参与机构数。"""
    start = (_now() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    sv, err = _safe(lambda: _cached_df(f"surveys_{start}", lambda: dc.surveys(start), 6))
    if sv is None or sv.empty:
        return None, err or "近期无调研数据"
    imap, err = _safe(lambda: _cached_df("industry_map", dc.industry_map, 24 * 7))
    if imap is None:
        return None, f"行业映射获取失败（{err}）"
    sv["SECURITY_CODE"] = sv["SECURITY_CODE"].astype(str).str.zfill(6)
    imap["code"] = imap["code"].astype(str).str.zfill(6)
    m = sv.merge(imap[["code", "industry"]], left_on="SECURITY_CODE", right_on="code", how="left")
    g = m.groupby("industry").agg(调研次数=("SECURITY_CODE", "size"), 涉及公司=("SECURITY_CODE", "nunique"),
                                  机构人次=("SUM", "sum")).sort_values("调研次数", ascending=False)
    g["排名"] = range(1, len(g) + 1)
    return g, None


def _imap():
    df, _ = _safe(lambda: _cached_df("industry_map", dc.industry_map, 24 * 7))
    if df is not None:
        df["code"] = df["code"].astype(str).str.zfill(6)
    return df


def _boards():
    return _safe(data.industry_boards)


# ======================= 大盘 =======================
def market_analysis(cfg: dict) -> dict:
    dims: list[Dim] = []
    now = _now()
    intraday = now.weekday() < 5 and 9 <= now.hour < 15

    # 1 指数趋势
    sh, err = _safe(data.index_hist, "sh000001")
    if sh is None:
        dims.append(Dim("指数趋势", NA, f"上证指数日线获取失败：{err}"))
    else:
        c = sh["close"]; last = c.iloc[-1]
        ma5, ma20, ma60 = (c.rolling(n).mean().iloc[-1] for n in (5, 20, 60))
        above = [n for n, v in (("MA5", ma5), ("MA20", ma20), ("MA60", ma60)) if last > v]
        sc = len(above) - 1 if len(above) else -2
        st = BULL if sc > 0 else BEAR if sc < 0 else NEU
        dims.append(Dim("指数趋势", st, f"上证 {last:.2f}（{sh['date'].iloc[-1].date()}），MA5 {ma5:.0f} / MA20 {ma20:.0f} / MA60 {ma60:.0f}；"
                        f"站上 {', '.join(above) if above else '无'}。" + ("短中期均线之下，趋势偏弱。" if sc < 0 else "趋势偏强。" if sc > 0 else "多空均衡。"),
                        sc, {"close": last}))
    # 2 两市成交额
    sz, _ = _safe(data.index_hist, "sz399001")
    if sh is not None and sz is not None and "amount" in sh and "amount" in sz:
        tot = sh.set_index("date")["amount"].add(sz.set_index("date")["amount"], fill_value=0).dropna()
        r = tot.iloc[-1] / tot.iloc[-21:-1].mean()
        sc = 1 if r >= 1.1 else -1 if r < 0.8 else 0
        note = "（盘中未走完，偏低属正常）" if intraday else ""
        if "amount_estimated" in sh:
            note += "（东财限流，改用腾讯：今日为实际成交额，历史按成交量折算，倍数等同量能倍数）"
        dims.append(Dim("两市成交额", BULL if sc > 0 else BEAR if sc < 0 else NEU,
                        f"{_amt(tot.iloc[-1])}，为前20日均值的 {r:.2f} 倍{note}。" +
                        ("放量，增量资金在场。" if sc > 0 else "缩量，资金观望。" if sc < 0 else "量能平稳。"), 0 if intraday else sc))
    else:
        dims.append(Dim("两市成交额", NA, "深成指成交额获取失败，无法计算两市合计。"))
    # 3 涨跌停情绪
    day = (sh["date"].iloc[-1] if sh is not None else now).strftime("%Y%m%d")
    zt, _ = _safe(data.limit_up_pool, day); dt_, _ = _safe(data.limit_down_pool, day); zb, _ = _safe(data.broken_pool, day)
    if zt is not None:
        nzt, ndt, nzb = len(zt), len(dt_) if dt_ is not None else None, len(zb) if zb is not None else None
        high = int(zt["连板数"].max()) if "连板数" in zt and len(zt) else 0
        br = nzb / (nzt + nzb) if nzb is not None and nzt + nzb else None
        sc = (1 if nzt >= cfg["market"]["hot_limit_up"] else 0) - (1 if (ndt or 0) >= cfg["market"]["cold_limit_down"] else 0) \
             - (1 if br is not None and br >= cfg["market"]["high_break_rate"] else 0)
        dims.append(Dim("涨跌停情绪", BULL if sc > 0 else BEAR if sc < 0 else NEU,
                        f"涨停 {nzt} 家、跌停 {ndt} 家、炸板率 {br:.0%}，最高连板 {high} 板。" if br is not None else f"涨停 {nzt} 家。", sc))
    else:
        dims.append(Dim("涨跌停情绪", NA, "涨停池获取失败。"))
    # 4 融资
    mm, err = _safe(lambda: _cached_df("margin_market", lambda: dc.margin_market(30), 6))
    if mm is not None and len(mm) >= 6:
        mm["date"] = pd.to_datetime(mm["date"])
        l = mm.iloc[-1]
        chg5 = l["RZYE"] - mm["RZYE"].iloc[-6]
        chg20 = l["RZYE"] - mm["RZYE"].iloc[-21] if len(mm) >= 21 else None
        sc = 1 if chg5 > 0 and l["RZJME"] > 0 else -1 if chg5 < 0 else 0
        dims.append(Dim("融资余额（杠杆资金）", BULL if sc > 0 else BEAR if sc < 0 else NEU,
                        f"截至 {l['date'].date()}：融资余额 {_amt(l['RZYE'])}，当日净买入 {_yi(l['RZJME'])}，"
                        f"近5日变化 {_yi(chg5)}" + (f"，近20日 {_yi(chg20)}" if chg20 is not None else "") + "。" +
                        ("杠杆资金回流。" if sc > 0 else "杠杆资金持续撤离，风险偏好下降。" if sc < 0 else "杠杆资金分歧。") +
                        "（两融数据 T+1 公布，不含今天。）", sc))
    else:
        dims.append(Dim("融资余额（杠杆资金）", NA, f"两融数据获取失败：{err}"))
    # 5 龙虎榜机构席位
    lhb_day = None
    if mm is not None and len(mm):
        lhb_day = mm["date"].iloc[-1]
    inst, err = _safe(lambda: _cached_df(f"lhb_inst_{lhb_day:%Y%m%d}", lambda: dc.lhb_institution_net(lhb_day), 24)) if lhb_day is not None else (None, "无日期")
    if inst is not None and len(inst):
        inst["NET"] = pd.to_numeric(inst["NET"], errors="coerce")
        inst["SECURITY_CODE"] = inst["SECURITY_CODE"].astype(str).str.zfill(6)
        net = inst["NET"].sum()
        im = _imap()
        names = dict(zip(im["code"], im["name"])) if im is not None else {}
        inst["label"] = inst["SECURITY_CODE"].map(lambda c: f"{names.get(c, '')}{c}")
        per = inst.groupby("label")["NET"].sum().sort_values()
        top_b = "、".join(f"{k}({_yi(v)})" for k, v in per.tail(3)[::-1].items())
        top_s = "、".join(f"{k}({_yi(v)})" for k, v in per.head(3).items())
        sc = 1 if net > 3e8 else -1 if net < -3e8 else 0
        dims.append(Dim("龙虎榜机构席位", BULL if sc > 0 else BEAR if sc < 0 else NEU,
                        f"{lhb_day.date()} 机构专用席位合计净买 {_yi(net)}，涉及 {inst['SECURITY_CODE'].nunique()} 只。"
                        f"净买前三：{top_b}；净卖前三：{top_s}。", sc))
    else:
        dims.append(Dim("龙虎榜机构席位", NA, f"最近交易日无机构席位数据或获取失败（{err or '空'}）。"))
    # 6 机构调研热度
    heat, err = industry_survey_heat(30)
    if heat is not None:
        top = "、".join(f"{i}({r.调研次数}次/{r.机构人次:.0f}家次)" for i, r in heat.head(5).iterrows())
        dims.append(Dim("机构调研热度（近30天）", NEU, f"共 {int(heat['调研次数'].sum())} 次调研。最热行业：{top}。"
                        "调研反映中长期关注方向，对次日涨跌影响有限，仅作选股方向参考。", 0, {"heat": heat}))
    else:
        dims.append(Dim("机构调研热度（近30天）", NA, f"调研数据不可用：{err}"))
    # 7 板块
    b, err = _boards()
    if b is not None and len(b):
        b = b.sort_values("pct_chg", ascending=False)
        up_ratio = (b["pct_chg"] > 0).mean()
        top = "、".join(f"{r.board}({r.pct_chg:+.2f}%)" for r in b.head(5).itertuples())
        flow = ""
        if "net_inflow" in b:
            f = b.sort_values("net_inflow", ascending=False)
            flow = "；主力净流入前三：" + "、".join(f"{r.board}({_yi(r.net_inflow)})" for r in f.head(3).itertuples())
        sc = 1 if up_ratio >= 0.6 else -1 if up_ratio <= 0.35 else 0
        dims.append(Dim("板块广度与主线", BULL if sc > 0 else BEAR if sc < 0 else NEU,
                        f"{up_ratio:.0%} 的行业上涨。领涨：{top}{flow}。", sc))
    else:
        dims.append(Dim("板块广度与主线", NA, f"板块数据获取失败：{err}"))

    total = sum(d.score for d in dims)
    valid = [d for d in dims if d.status != NA]
    pos = "5-8成" if total >= 4 else "3-5成" if total >= 1 else "1-3成" if total >= -2 else "0-1成（空仓观望）"
    periods = None
    if cfg.get("_history", True):
        periods, perr = _safe(multi_period)
        if periods is None:
            periods = {"error": perr}
        else:
            _enrich_dims(dims, periods)
    return {"dims": dims, "total": total, "position": pos, "intraday": intraday, "valid": len(valid), "periods": periods}


def multi_period() -> dict:
    """情绪 / 融资 / 板块 / 指数 / 成交额 的 20日、3个月、6个月、1年 对比表。"""
    from . import history as h
    out = {}
    out["indexes"], _ = _safe(h.index_windows)
    out["amount"], _ = _safe(h.amount_windows)
    m, err = _safe(h.margin_windows)
    out["margin"], out["margin_meta"] = (m if m is not None else (None, {"error": err}))
    mat, err = _safe(h.stock_matrix)
    if mat is not None:
        pct, hp, names = mat
        sent = h.sentiment_history(pct, hp, names)
        out["sentiment_daily"] = sent
        out["sentiment"] = h.window_table(sent, ["涨停", "跌停", "炸板", "炸板率%", "最高连板", "上涨占比%", "涨停次日溢价%"])
        sec, _ = _safe(h.sector_windows, pct)
        out["sectors"], out["sector_types"] = sec if sec is not None else (None, None)
    else:
        out["matrix_error"] = err
    out["sector_flow"], _ = _safe(h.sector_flow_windows)
    return out


def _enrich_dims(dims: list, p: dict) -> None:
    """把多周期位置补进各维度依据，便于一句话看出“今天在历史上算高还是低”。"""
    by = {d.name: d for d in dims}
    ix = p.get("indexes")
    if ix is not None and "指数趋势" in by and "今日%" in ix:
        by["指数趋势"].detail += " 其他指数：" + "；".join(
            f"{r['指数']} {r['收盘']}（{r['今日%']:+.2f}%，近20日 {r['近20日%']:+.1f}%，站上 {r['站上均线']}）"
            for _, r in ix.iterrows() if r["指数"] != "上证指数" and isinstance(r.get("今日%"), (int, float)))
    st = p.get("sentiment")
    if st is not None and "涨跌停情绪" in by:
        z = st.set_index("指标")
        by["涨跌停情绪"].detail += (f" 自算口径：涨停 {z.loc['涨停','今日']:.0f}（20日均 {z.loc['涨停','近20日均值']}，1年均 {z.loc['涨停','近1年均值']}，"
                                 f"1年分位 {z.loc['涨停','近1年分位']}），炸板率 {z.loc['炸板率%','今日']}%（20日均 {z.loc['炸板率%','近20日均值']}%），"
                                 f"昨日涨停今日平均 {z.loc['涨停次日溢价%','今日']:+.2f}%。")
    mg, meta = p.get("margin"), p.get("margin_meta") or {}
    if mg is not None and "融资余额（杠杆资金）" in by:
        by["融资余额（杠杆资金）"].detail += " " + "；".join(f"{r['区间']} {r['变化(亿)']:+.0f}亿（{r['变化%']:+.2f}%）" for _, r in mg.iterrows()) + \
            (f"；余额处于近1年 {meta['pctl']:.0f}% 分位。" if "pctl" in meta else "")


def _md(df) -> str:
    if df is None or len(df) == 0:
        return "（无数据）"
    cols = list(df.columns)
    fmt = lambda v: "" if v is None or (isinstance(v, float) and pd.isna(v)) else (f"{v:,.2f}".rstrip("0").rstrip(".") if isinstance(v, float) else str(v))
    return "\n".join(["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)] +
                     ["| " + " | ".join(fmt(v) for v in row) + " |" for row in df.itertuples(index=False)])


def render_periods(p: dict | None) -> str:
    if not p:
        return ""
    if "error" in p:
        return f"\n\n## 多周期对比\n\n多周期数据获取失败：{p['error']}"
    out = ["\n\n## 多周期对比（20日 / 3个月 / 6个月 / 1年）"]
    out += ["\n### 指数（区间涨跌幅）", _md(p.get("indexes"))]
    out += ["\n### 两市成交额", _md(p.get("amount"))]
    out += ["\n### 情绪（全市场日K自算：涨停≥涨幅限制的98.5%，炸板=盘中触及未封住）", _md(p.get("sentiment"))]
    if p.get("matrix_error"):
        out.append(f"情绪历史获取失败：{p['matrix_error']}")
    meta = p.get("margin_meta") or {}
    out += [f"\n### 融资余额（截至 {pd.Timestamp(meta['date']).date() if 'date' in meta else '—'}，T+1）", _md(p.get("margin"))]
    if "pctl" in meta:
        out.append(f"\n当前余额 {meta['balance']:.0f} 亿，处于近1年 {meta['pctl']:.0f}% 分位。")
    out += ["\n### 行业涨跌（东财行业，成分股等权）", _md(p.get("sectors")), "", _md(p.get("sector_types"))]
    out += ["\n### 行业主力净流入（东财板块资金）", _md(p.get("sector_flow")) if p.get("sector_flow") is not None else "东财板块资金接口不可用，本次缺失。"]
    return "\n".join(out)


# ======================= 个股 =======================
def stock_analysis(code: str, cfg: dict, cost: float | None = None, market: dict | None = None) -> dict:
    code = str(code).zfill(6)
    now = _now()
    dims: list[Dim] = []
    prof, perr = _safe(dc.stock_profile, code)
    prof = prof or {"code": code, "name": None}
    im = _imap()
    row = im[im["code"] == code] if im is not None else None
    if row is not None and len(row):
        prof["name"] = prof.get("name") or row["name"].iloc[0]
        prof["industry"] = prof.get("industry") or row["industry"].iloc[0]
    name, ind = prof.get("name") or code, prof.get("industry")

    # K 线与技术
    start = (now - pd.Timedelta(days=300)).strftime("%Y%m%d")
    hist, err = _safe(data.stock_hist, code, start, now.strftime("%Y%m%d"))
    d = None
    if hist is not None and len(hist) >= 60:
        d = prepare(hist, cfg)
        L = d.iloc[-1]
        bull = L["ma5"] > L["ma10"] > L["ma20"]
        pos = [n for n in ("ma5", "ma10", "ma20", "ma60") if L["close"] > L[n]]
        sc = 2 if bull and "ma5" in pos else 1 if len(pos) >= 3 else -2 if not pos or len(pos) <= 1 else 0
        dims.append(Dim("趋势与均线", BULL if sc > 0 else BEAR if sc < 0 else NEU,
                        f"收盘 {L['close']:.2f}；MA5 {L['ma5']:.2f} / MA10 {L['ma10']:.2f} / MA20 {L['ma20']:.2f} / MA60 {L['ma60']:.2f}。"
                        f"{'均线多头排列' if bull else '均线未形成多头'}，站上 {len(pos)}/4 条均线。", sc))
        hi20 = d["high"].shift(1).rolling(cfg["strategy"]["breakout_window"]).max().iloc[-1]
        sig = bool(L["entry"])
        vr, bias = L["vol_ratio5"], L["bias5"]
        if sig:
            txt, sc = f"触发放量突破：收盘 {L['close']:.2f} 突破前20日最高 {hi20:.2f}，量为5日均量 {vr:.2f} 倍，偏离MA5 {bias:.1%}（≤7% 不算追高）。", 2
        else:
            why = []
            if L["close"] <= hi20: why.append(f"未突破前20日高点 {hi20:.2f}（差 {hi20 / L['close'] - 1:.1%}）")
            if vr < cfg["strategy"]["vol_mult"]: why.append(f"量能不足（{int(vr * 100) / 100:.2f} 倍 < {cfg['strategy']['vol_mult']} 倍）")
            if bias > cfg["strategy"]["max_ma5_bias"]: why.append(f"偏离MA5 {bias:.1%}，过高不追")
            if not bull: why.append("均线未多头")
            txt, sc = "未触发买入信号：" + "；".join(why or ["条件未同时满足"]) + "。", -1 if bias > 0.1 else 0
        dims.append(Dim("突破与量能（买点）", BULL if sc > 0 else BEAR if sc < 0 else NEU, txt, sc,
                        {"signal": sig, "hi20": hi20, "close": L["close"], "ma5": L["ma5"], "ma10": L["ma10"]}))
        w = sell_warnings(d, cfg).iloc[-1]
        flags = [k for k, v in w.items() if v]
        dims.append(Dim("卖出预警（技术）", BEAR if flags else BULL, ("出现：" + "、".join(flags) + "。") if flags else "无顶部或破位信号。",
                        -min(2, len(flags)) if flags else 1))
    else:
        dims.append(Dim("趋势与均线", NA, f"日线不足或获取失败：{err or '上市不足60日'}"))

    # 主力资金
    ff, err = _safe(dc.fund_flow, code, 10)
    if ff is not None and len(ff):
        m1, m5 = ff["main"].iloc[-1], ff["main"].tail(5).sum()
        days_in = int((ff["main"].tail(5) > 0).sum())
        sc = 1 if m5 > 0 and m1 > 0 else -1 if m5 < 0 and m1 < 0 else 0
        dims.append(Dim("主力资金", BULL if sc > 0 else BEAR if sc < 0 else NEU,
                        f"最近一日主力净流入 {_yi(m1)}，近5日合计 {_yi(m5)}（5天中 {days_in} 天净流入）。"
                        "注：主力=超大单+大单，口径为东财统计，大资金可拆单，仅作参考。", sc))
    else:
        dims.append(Dim("主力资金", NA, f"资金流获取失败：{err}"))

    # 融资
    ms, err = _safe(dc.margin_stock, code, 30)
    if ms is None:
        dims.append(Dim("融资（杠杆资金）", NA, f"两融数据获取失败：{err}"))
    elif ms.empty:
        dims.append(Dim("融资（杠杆资金）", NA, "该股不是两融标的（或近期无两融记录），无法从杠杆资金角度判断。"))
    else:
        l = ms.iloc[-1]
        base = ms["RZYE"].iloc[-6] if len(ms) >= 6 else ms["RZYE"].iloc[0]
        chg = l["RZYE"] / base - 1
        zb_ = l.get("RZYEZB")
        sc = 1 if chg > 0.03 else -1 if chg < -0.03 else 0
        crowd = ""
        if zb_ is not None and zb_ >= 8:
            sc -= 1; crowd = f"融资余额占流通市值 {zb_:.1f}%，杠杆拥挤，下跌时易踩踏。"
        dims.append(Dim("融资（杠杆资金）", BULL if sc > 0 else BEAR if sc < 0 else NEU,
                        f"截至 {l['date'].date()}：融资余额 {_amt(l['RZYE'])}，占流通市值 {zb_:.2f}%；当日净买入 {_yi(l['RZJME'])}，"
                        f"近5日余额变化 {chg:+.1%}。{crowd}" + ("杠杆资金加仓。" if chg > 0.03 else "杠杆资金减仓。" if chg < -0.03 else "杠杆资金变化不大。"),
                        sc))

    # 龙虎榜
    lstart = (now - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
    lb, err = _safe(dc.lhb_stock, code, lstart)
    if lb is None:
        dims.append(Dim("龙虎榜", NA, f"龙虎榜获取失败：{err}"))
    elif lb.empty:
        dims.append(Dim("龙虎榜", NEU, "近30个交易日未上龙虎榜：没有游资、机构或北向席位的公开交易数据，"
                        "说明近期没有出现异常波动，也无法从席位角度确认主力动向。", 0))
    else:
        lb["TRADE_DATE"] = pd.to_datetime(lb["TRADE_DATE"])
        days_ = lb["TRADE_DATE"].dt.date.unique()
        last_day = lb["TRADE_DATE"].max()
        last = lb[lb["TRADE_DATE"] == last_day].iloc[0]
        seats, _ = _safe(dc.lhb_seats, code, last_day)
        parts = [f"近30个交易日上榜 {len(days_)} 次，最近 {last_day.date()}（{last.get('EXPLANATION', '')}），龙虎榜净买 {_yi(last.get('BILLBOARD_NET_AMT'))}。"]
        sc = 1 if (last.get("BILLBOARD_NET_AMT") or 0) > 0 else -1
        if seats is not None and len(seats):
            seats = seats.drop_duplicates(subset=["OPERATEDEPT_NAME"])
            seats["NET"] = pd.to_numeric(seats["NET"], errors="coerce")
            inst = seats[seats["OPERATEDEPT_NAME"].str.contains("机构专用")]["NET"].sum()
            north = seats[seats["OPERATEDEPT_NAME"].str.contains("股通专用")]["NET"].sum()
            has_inst = seats["OPERATEDEPT_NAME"].str.contains("机构专用").any()
            has_north = seats["OPERATEDEPT_NAME"].str.contains("股通专用").any()
            parts.append(f"机构专用席位：{'净买 ' + _yi(inst) if has_inst else '未出现'}；北向（沪/深股通）：{'净买 ' + _yi(north) if has_north else '未出现'}。")
            topb = seats[seats["side"] == "买"].sort_values("BUY", ascending=False).head(3)["OPERATEDEPT_NAME"].tolist()
            parts.append("买入前三席位：" + "、".join(topb) + "。")
            if has_inst:
                sc += 1 if inst > 0 else -1
        dims.append(Dim("龙虎榜", BULL if sc > 0 else BEAR if sc < 0 else NEU, "".join(parts), max(-2, min(2, sc))))

    # 机构调研（个股 + 所属行业）
    s90 = (now - pd.Timedelta(days=90)).strftime("%Y-%m-%d")
    sv, err = _safe(dc.surveys_stock, code, s90)
    heat, herr = industry_survey_heat(30)
    ind_txt = ""
    if heat is not None and ind:
        if ind in heat.index:
            r = heat.loc[ind]
            ind_txt = f"所属行业「{ind}」近30天被调研 {int(r['调研次数'])} 次（{int(r['涉及公司'])} 家公司，{r['机构人次']:.0f} 家次机构），在 {len(heat)} 个行业中排第 {int(r['排名'])}。"
        else:
            ind_txt = f"所属行业「{ind}」近30天没有任何公司被机构调研，机构对该板块关注度低。"
    elif ind:
        ind_txt = f"行业调研统计不可用（{herr}）。"
    if sv is None:
        dims.append(Dim("机构调研", NA, f"个股调研数据获取失败：{err}。{ind_txt}"))
    elif sv.empty:
        dims.append(Dim("机构调研", NEU, f"近90天该股没有机构调研记录：缺少机构实地调研带来的关注度和信息催化。{ind_txt}", 0))
    else:
        n, orgs = len(sv), pd.to_numeric(sv["SUM"], errors="coerce").sum()
        lastd = sv["date"].max().date()
        types = sv.get("RECEIVE_WAY_EXPLAIN")
        sc = 1 if n >= 2 or orgs >= 20 else 0
        dims.append(Dim("机构调研", BULL if sc else NEU,
                        f"近90天被调研 {n} 次，合计 {orgs:.0f} 家次机构，最近一次 {lastd}"
                        + (f"（{types.iloc[0]}）" if types is not None and len(types) else "") + f"。{ind_txt}", sc))

    # 板块强度
    b, err = _boards()
    if b is not None and ind and ind in set(b["board"]):
        b = b.sort_values("pct_chg", ascending=False).reset_index(drop=True)
        r = b[b["board"] == ind].iloc[0]; rank = int(b.index[b["board"] == ind][0]) + 1
        flow = f"，主力净流入 {_yi(r['net_inflow'])}" if "net_inflow" in b else ""
        sc = 1 if rank <= len(b) * 0.2 else -1 if rank >= len(b) * 0.8 else 0
        dims.append(Dim("所属板块强度", BULL if sc > 0 else BEAR if sc < 0 else NEU,
                        f"「{ind}」今日 {r['pct_chg']:+.2f}%，{len(b)} 个行业中排第 {rank}{flow}，上涨 {r.get('up', '—')} 家 / 下跌 {r.get('down', '—')} 家。"
                        + ("属于今日强势板块。" if sc > 0 else "板块弱势，个股缺少板块效应。" if sc < 0 else "板块表现居中。"), sc))
    else:
        dims.append(Dim("所属板块强度", NA, f"未能匹配行业板块（行业：{ind or '未知'}{'；' + err if err else ''}）。"))

    # 事件与基本面风险（系统能识别的部分）
    risk = []
    if "ST" in str(name).upper(): risk.append("ST 股，涨跌幅 5%，退市风险")
    pe = prof.get("pe_ttm")
    if pe is not None and pe < 0: risk.append(f"市盈率为负（{pe}），公司亏损")
    fmv = prof.get("float_mv")
    dims.append(Dim("基本面与事件", BEAR if risk else NEU,
                    ("；".join(risk) + "。" if risk else "未发现ST或亏损标记。") +
                    "重组、停牌、减持、解禁等公告系统无法自动识别，需另查公告。"
                    + (f" 流通市值 {_amt(fmv)}。" if fmv else ""), -1 if risk else 0))

    # ---------------- 结论 ----------------
    total = sum(x.score for x in dims)
    tech = next((x for x in dims if x.name == "突破与量能（买点）"), None)
    sig = bool(tech and tech.facts.get("signal"))
    mkt_total = market["total"] if market else None
    reasons_buy = [f"{x.name}：{x.detail}" for x in dims if x.score > 0]
    reasons_risk = [f"{x.name}：{x.detail}" for x in dims if x.score < 0]
    missing = [f"{x.name}：{x.detail}" for x in dims if x.status in (NA,) or (x.status == NEU and x.score == 0 and ("没有" in x.detail or "未上" in x.detail))]
    plan = {}
    if tech:
        f = tech.facts
        # 买入参考价：持仓用成本；未突破用触发价；已在触发价上方用收盘价（避免止损高于触发价）
        ref = cost or max(f["hi20"], f["close"])
        plan = {"突破触发价": round(f["hi20"], 2), "止损（-7%，按买入参考价）": round(ref * (1 - cfg["exit"]["stop_loss"]), 2),
                "MA5 防守位": round(f["ma5"], 2), "MA10 防守位": round(f["ma10"], 2),
                "止盈1（+10%）": round(ref * 1.10, 2), "止盈2（+20%）": round(ref * 1.20, 2),
                "买入参考价": round(ref, 2)}
    if cost:
        pnl = (tech.facts["close"] / cost - 1) if tech else None
        warn = next((x for x in dims if x.name == "卖出预警（技术）"), None)
        broke = tech and tech.facts["close"] < tech.facts["ma5"]
        if pnl is not None and pnl <= -cfg["exit"]["stop_loss"]:
            action = "卖出（触发止损）"
        elif broke and (warn and warn.score < 0):
            action = "卖出/减仓（跌破MA5且有顶部信号）"
        elif pnl is not None and pnl >= cfg["exit"]["take_profit_1"]:
            action = "分批止盈（先卖1/3，其余用MA5跟踪）"
        elif total <= -3:
            action = "减仓（多维度转弱）"
        else:
            action = "持有（未触发卖出条件）"
        plan["持仓盈亏"] = f"{pnl:+.1%}" if pnl is not None else "—"
    else:
        if sig and total >= 2 and (mkt_total is None or mkt_total >= -2):
            action = "买入（小仓位，次日开盘不追高于触发价+3%）"
        elif sig:
            action = "谨慎买入/观察（有信号但其他维度或大盘偏弱）"
        elif total >= 2:
            action = "观察（多维度偏多，等待放量突破触发价）"
        else:
            action = "回避（无信号且多维度不支持）"
    return {"code": code, "name": name, "industry": ind, "concepts": prof.get("concepts"), "dims": dims, "total": total,
            "action": action, "plan": plan, "reasons_buy": reasons_buy, "reasons_risk": reasons_risk, "missing": missing,
            "market_total": mkt_total}


# ======================= 输出 =======================
def _dims_table(dims) -> str:
    rows = ["| 维度 | 状态 | 依据 |", "|---|---|---|"]
    rows += [f"| {d.name} | {ICON[d.status]} {d.status}（{d.score:+d}） | {d.detail.replace('|', '/')} |" for d in dims]
    return "\n".join(rows)


def render_market(r: dict) -> str:
    head = f"## 大盘综合研判\n\n**综合得分 {r['total']:+d}，建议仓位 {r['position']}**"
    if r["intraday"]:
        head += "（盘中运行：成交量、涨停数据未走完；两融与龙虎榜为上一交易日）"
    return head + "\n\n" + _dims_table(r["dims"]) + render_periods(r.get("periods"))


def render_stock(r: dict) -> str:
    out = [f"## {r['name']}（{r['code']}）· {r['industry'] or '行业未知'}",
           f"\n**结论：{r['action']}**　多维度得分 {r['total']:+d}" + (f"，大盘得分 {r['market_total']:+d}" if r["market_total"] is not None else ""),
           "\n" + _dims_table(r["dims"])]
    out.append("\n**支持理由**\n" + ("\n".join(f"- {x}" for x in r["reasons_buy"]) or "- 无"))
    out.append("\n**风险与反对理由**\n" + ("\n".join(f"- {x}" for x in r["reasons_risk"]) or "- 无"))
    out.append("\n**缺失或近期未发生的维度**\n" + ("\n".join(f"- {x}" for x in r["missing"]) or "- 无"))
    if r["plan"]:
        out.append("\n**价位计划**\n" + "\n".join(f"- {k}：{v}" for k, v in r["plan"].items()))
    return "\n".join(out)
