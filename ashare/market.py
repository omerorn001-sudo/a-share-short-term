"""大环境评分：指数趋势 + 量能 + 涨跌停情绪 → 0-100 分与建议仓位。"""
import pandas as pd

from . import data


def score_environment(idx: pd.DataFrame, zt: int | None, dt: int | None, zb: int | None, cfg: dict) -> dict:
    m = cfg["market"]
    c = idx["close"]
    vol_col = "amount" if "amount" in idx and idx["amount"].notna().all() else "volume"
    v = idx[vol_col]
    last = idx.iloc[-1]
    ma_s, ma_l = c.rolling(m["ma_short"]).mean().iloc[-1], c.rolling(m["ma_long"]).mean().iloc[-1]
    vol_ratio = v.iloc[-1] / v.iloc[-21:-1].mean()
    score, notes = 0, []
    if last["close"] > ma_s: score += 20; notes.append(f"指数站上MA{m['ma_short']}")
    else: notes.append(f"指数在MA{m['ma_short']}下方")
    if last["close"] > ma_l: score += 20; notes.append(f"指数站上MA{m['ma_long']}")
    else: notes.append(f"指数在MA{m['ma_long']}下方")
    if vol_ratio >= 1.1: score += 20; notes.append(f"放量（{vol_ratio:.2f}倍20日均量）")
    elif vol_ratio >= 0.9: score += 10; notes.append(f"量能平稳（{vol_ratio:.2f}倍）")
    else: notes.append(f"缩量（{vol_ratio:.2f}倍）")
    break_rate = None
    if zt is not None:
        if zt >= m["hot_limit_up"]: score += 15; notes.append(f"涨停{zt}家，情绪偏热")
        elif zt >= 30: score += 8; notes.append(f"涨停{zt}家，情绪中性")
        else: notes.append(f"涨停{zt}家，情绪偏弱")
    if dt is not None:
        if dt < 5: score += 10
        elif dt >= m["cold_limit_down"]: score -= 10; notes.append(f"跌停{dt}家，亏钱效应明显")
    if zt is not None and zb is not None and zt + zb > 0:
        break_rate = zb / (zt + zb)
        if break_rate < 0.25: score += 15
        elif break_rate >= m["high_break_rate"]: notes.append(f"炸板率{break_rate:.0%}，追高风险大")
        else: score += 7
    score = max(0, min(100, score))
    position = "5-8成" if score >= 70 else "3-5成" if score >= 50 else "0-3成"
    return {"日期": str(pd.Timestamp(last["date"]).date()), "收盘": round(float(last["close"]), 2),
            "评分": score, "建议仓位": position, "涨停": zt, "跌停": dt,
            "炸板率": None if break_rate is None else round(break_rate, 3), "要点": notes}


def market_report(cfg: dict, date: str | None = None) -> dict:
    idx = data.index_hist(cfg["market"]["index"])
    if date:
        idx = idx[idx["date"] <= pd.Timestamp(date)]
    day = pd.Timestamp(idx.iloc[-1]["date"]).strftime("%Y%m%d")

    def count(fn):
        try:
            return len(fn(day))
        except Exception:
            return None
    return score_environment(idx, count(data.limit_up_pool), count(data.limit_down_pool), count(data.broken_pool), cfg)


def hot_boards(top: int = 10) -> pd.DataFrame:
    df = data.industry_boards()
    cols = [c for c in ["board", "pct_chg", "up", "down", "leader", "net_inflow", "turnover"] if c in df]
    return df[cols].sort_values("pct_chg", ascending=False).head(top).reset_index(drop=True)
