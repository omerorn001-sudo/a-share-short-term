"""每日游资动向：抓东财龙虎榜营业部明细，按 youzi_seats.yaml 把营业部映射为游资外号，输出“谁买了什么、卖了什么”。

数据：RPT_DAILYBILLBOARD_DETAILSNEW（上榜股）+ RPT_BILLBOARD_DAILYDETAILSBUY/SELL（买卖前 5 营业部）。
盘后约 17:00–18:30 更新。“3日”表示按“连续三个交易日累计偏离”上榜的 3 日累计金额。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from . import datacenter as dc

SEATS_FILE = Path(__file__).with_name("youzi_seats.yaml")


def load_seats(path: Path | None = None) -> list[tuple[str, list[str]]]:
    d = yaml.safe_load(open(path or SEATS_FILE, encoding="utf-8")) or {}
    return [(k, [str(x) for x in v]) for k, v in d.items()]


def tag_seat(name: str, seats: list[tuple[str, list[str]]]) -> str:
    name = str(name)
    if name == "机构专用":
        return "机构"
    if "股通专用" in name:
        return "北向"
    if any(k in name for k in ("高盛", "摩根", "瑞银", "野村", "汇丰前海", "花旗", "瑞信", "德意志")):
        return "外资"
    for nick, kws in seats:
        if any(k in name for k in kws):
            return nick
    return ""


def latest_date() -> str:
    x = dc.query("RPT_DAILYBILLBOARD_DETAILSNEW", sort="TRADE_DATE", page_size=1, max_pages=1, columns="TRADE_DATE")
    return str(pd.Timestamp(x["TRADE_DATE"].iloc[0]).date())


def fetch(start: str, end: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回 (上榜股, 营业部明细)。明细每行一个 (股票, 营业部, 方向)。"""
    end = end or start
    f = f"(TRADE_DATE>='{start}')(TRADE_DATE<='{end}')"
    det = dc.query("RPT_DAILYBILLBOARD_DETAILSNEW", filt=f, sort="TRADE_DATE", page_size=500, max_pages=40,
                   columns="TRADE_DATE,SECURITY_CODE,SECURITY_NAME_ABBR,CLOSE_PRICE,CHANGE_RATE,TURNOVERRATE,EXPLANATION,"
                           "BILLBOARD_NET_AMT,D1_CLOSE_ADJCHRATE,D2_CLOSE_ADJCHRATE,D5_CLOSE_ADJCHRATE")
    cols = "TRADE_DATE,SECURITY_CODE,OPERATEDEPT_NAME,EXPLANATION,BUY,SELL,NET"
    parts = []
    for rep, side in (("RPT_BILLBOARD_DAILYDETAILSBUY", "买"), ("RPT_BILLBOARD_DAILYDETAILSSELL", "卖")):
        parts.append(dc.query(rep, filt=f, sort="TRADE_DATE", page_size=500, max_pages=80, columns=cols).assign(side=side))
    s = pd.concat(parts, ignore_index=True)
    if s.empty:
        return det, s
    for c in ("BUY", "SELL", "NET"):
        s[c] = pd.to_numeric(s[c], errors="coerce").fillna(0)
    s["date"] = pd.to_datetime(s["TRADE_DATE"]).dt.strftime("%Y-%m-%d")
    det["date"] = pd.to_datetime(det["TRADE_DATE"]).dt.strftime("%Y-%m-%d")
    s["3日"] = s["EXPLANATION"].astype(str).str.contains("连续三个交易日")
    # 同一股票既按单日又按 3 日上榜时，优先保留单日数据
    s = s.sort_values("3日").drop_duplicates(["date", "SECURITY_CODE", "OPERATEDEPT_NAME", "side"])
    name = det.drop_duplicates(["date", "SECURITY_CODE"]).set_index(["date", "SECURITY_CODE"])["SECURITY_NAME_ABBR"]
    s["name"] = [name.get((d, c), c) for d, c in zip(s["date"], s["SECURITY_CODE"])]
    seats = load_seats()
    s["游资"] = s["OPERATEDEPT_NAME"].map(lambda x: tag_seat(x, seats))
    return det, s


def _amt(x: float) -> str:
    return f"{x / 1e8:.2f}亿" if abs(x) >= 1e8 else f"{x / 1e4:.0f}万"


def seat_table(s: pd.DataFrame, max_items: int = 8) -> pd.DataFrame:
    """游资 → 买入/卖出清单（与公众号“龙虎榜游资动向”表同格式）。"""
    k = s[~s["游资"].isin(["", "机构", "北向", "外资"])]
    rows = []
    for nick, g in k.groupby("游资", sort=False):
        def lst(side, col):
            x = g[g.side == side].groupby(["name", "3日"]).agg(v=(col, "sum"), n=(col, "size")).reset_index()
            x = x.sort_values("v", ascending=False)
            items = [f"{r['name']}{'3日' if r['3日'] else ''}{f'{r.n}席' if r.n > 1 else ''}{_amt(r.v)}" for _, r in x.head(max_items).iterrows()]
            return "、".join(items) + (f" 等{len(x)}只" if len(x) > max_items else ""), x.v.sum()
        (b, bv), (se, sv) = lst("买", "BUY"), lst("卖", "SELL")
        rows.append({"游资": nick, "买入": b, "卖出": se, "净买": bv - sv})
    return pd.DataFrame(rows).sort_values("净买", ascending=False).reset_index(drop=True) if rows else pd.DataFrame()


def stock_table(det: pd.DataFrame, s: pd.DataFrame) -> pd.DataFrame:
    """按股票汇总：知名游资净买、买方/卖方游资、机构、北向。"""
    s = s.copy()
    s["amt"] = s["BUY"].where(s.side == "买", -s["SELL"])
    out = []
    for (code, nm), g in s.groupby(["SECURITY_CODE", "name"]):
        y = g[~g["游资"].isin(["", "机构", "北向", "外资"])]
        d = det[det.SECURITY_CODE == code].iloc[0] if (det.SECURITY_CODE == code).any() else None
        out.append({"代码": code, "名称": nm, "涨跌幅%": None if d is None else round(float(d.CHANGE_RATE), 2),
                    "上榜原因": "" if d is None else str(d.EXPLANATION)[:18],
                    "游资净买": y["amt"].sum(), "买方游资": "、".join(sorted(set(y[y.side == "买"]["游资"]))),
                    "卖方游资": "、".join(sorted(set(y[y.side == "卖"]["游资"]))),
                    "机构净买": g[g["游资"] == "机构"]["amt"].sum(), "北向净买": g[g["游资"] == "北向"]["amt"].sum(), "外资净买": g[g["游资"] == "外资"]["amt"].sum(),
                    "龙虎榜净买": None if d is None else float(d.BILLBOARD_NET_AMT or 0)})
    t = pd.DataFrame(out)
    return t.sort_values("游资净买", ascending=False).reset_index(drop=True) if len(t) else t


def unknown_big(s: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """未识别但金额大的营业部，便于补充 youzi_seats.yaml。"""
    u = s[(s["游资"] == "") & (s.side == "买")].groupby("OPERATEDEPT_NAME").agg(
        买入=("BUY", "sum"), 股票=("name", lambda x: "、".join(x)))
    return u.sort_values("买入", ascending=False).head(n).reset_index()


def stats(days: int = 20, end: str | None = None) -> pd.DataFrame:
    """近 N 个上榜日，各游资买入（买方席位）后该股次日/2日/5日收盘涨跌幅（东财复权口径，相对上榜日收盘）。"""
    end = end or latest_date()
    start = (pd.Timestamp(end) - pd.Timedelta(days=int(days * 1.6) + 7)).strftime("%Y-%m-%d")
    det, s = fetch(start, end)
    ds = sorted(s["date"].unique())[-days:]
    s = s[s["date"].isin(ds) & (s.side == "买") & ~s["游资"].isin(["", "北向"])]
    r = det.drop_duplicates(["date", "SECURITY_CODE"]).set_index(["date", "SECURITY_CODE"])
    for k in ("D1", "D2", "D5"):
        s[k] = [pd.to_numeric(r[f"{k}_CLOSE_ADJCHRATE"].get((d, c)), errors="coerce") for d, c in zip(s["date"], s["SECURITY_CODE"])]
    s = s.drop_duplicates(["游资", "date", "SECURITY_CODE"])
    g = s.groupby("游资").agg(出手次数=("SECURITY_CODE", "size"), 次日均涨=("D1", "mean"), 次日胜率=("D1", lambda x: (x > 0).mean() * 100),
                              二日均涨=("D2", "mean"), 五日均涨=("D5", "mean"))
    g = g[g["出手次数"] >= 3]
    return g.sort_values("出手次数", ascending=False).round(2)


def report(date: str | None = None, with_stats: int = 0) -> tuple[str, dict]:
    date = date or latest_date()
    det, s = fetch(date)
    if s.empty:
        return f"# 游资动向 {date}\n\n当日无龙虎榜数据（非交易日或尚未更新，约 17:00–18:30 发布）。\n", {}
    st, sk, uk = seat_table(s), stock_table(det, s), unknown_big(s)
    md = [f"# 游资动向 {date}", "", f"上榜 {det.SECURITY_CODE.nunique()} 只；识别到知名游资 {len(st)} 个。", "",
          "## 游资席位买卖", "", "| 游资 | 买入 | 卖出 | 净买 |", "|---|---|---|---|"]
    md += [f"| {r.游资} | {r.买入 or '—'} | {r.卖出 or '—'} | {_amt(r.净买)} |" for r in st.itertuples()]
    top = sk[(sk["买方游资"] != "") | (sk["卖方游资"] != "")]
    md += ["", "## 个股：游资合力（按游资净买排序）", "", "| 股票 | 涨跌幅 | 游资净买 | 买方游资 | 卖方游资 | 机构净买 | 北向净买 | 外资净买 | 上榜原因 |", "|---|---|---|---|---|---|---|---|---|"]
    md += [f"| {r.名称} {r.代码} | {r._3}% | {_amt(r.游资净买)} | {r.买方游资 or '—'} | {r.卖方游资 or '—'} | {_amt(r.机构净买)} | {_amt(r.北向净买)} | {_amt(r.外资净买)} | {r.上榜原因} |"
           for r in top.itertuples()]
    inst = sk.sort_values("机构净买", ascending=False)
    inst = inst[inst["机构净买"] != 0]
    md += ["", "## 机构专用席位净买前 5 / 净卖前 5", ""]
    md += ["- 净买：" + "、".join(f"{r.名称}{_amt(r.机构净买)}" for r in inst.head(5).itertuples()),
           "- 净卖：" + "、".join(f"{r.名称}{_amt(r.机构净买)}" for r in inst.tail(5)[::-1].itertuples() if r.机构净买 < 0)]
    md += ["", "## 未识别的大额买入席位（可补充到 youzi_seats.yaml）", ""]
    md += [f"- {r.OPERATEDEPT_NAME}：{_amt(r.买入)}（{r.股票}）" for r in uk.itertuples()]
    if with_stats:
        t = stats(with_stats, date)
        md += ["", f"## 近 {with_stats} 个上榜日游资战绩（上榜日收盘→N 日后收盘，%）", "",
               "| 游资 | 出手次数 | 次日均涨 | 次日胜率 | 2日均涨 | 5日均涨 |", "|---|---|---|---|---|---|"]
        fm = lambda v: "—" if pd.isna(v) else f"{v:+.2f}"
        md += [f"| {i} | {int(r.出手次数)} | {fm(r.次日均涨)} | {r.次日胜率:.0f}% | {fm(r.二日均涨)} | {fm(r.五日均涨)} |" for i, r in t.iterrows()]
        md += ["", "注：次日/2日/5日为上榜日收盘到之后收盘的涨跌幅（尚未走完的日期不计入）；实际跟买只能次日开盘买，收益通常更低。出手少于 3 次的不列出。"]
    md += ["", "> 龙虎榜为盘后数据，只含异动股的买卖前 5 席位；外号与营业部的对应为市场惯例，同一营业部也有大量普通客户。仅供研究，不构成投资建议。"]
    return "\n".join(md) + "\n", {"seats": st, "stocks": sk, "raw": s}
