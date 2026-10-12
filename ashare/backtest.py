"""事件驱动回测。

规则：T 日收盘出信号 → T+1 开盘买（开盘即涨停则放弃）；T+1 制度下买入当天不卖；
跌停开盘卖不出顺延；含佣金、印花税、滑点；分档止盈 + 硬止损 + 移动止盈 + 均线/时间止损。
组合层：最多 max_positions 个仓位，每笔占 1/max_positions，按已实现收益计算权益曲线。
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd

from .rules import limit_pct, limit_prices
from .strategy import prepare


@dataclass
class Trade:
    code: str
    signal_date: pd.Timestamp
    entry_date: pd.Timestamp
    entry_price: float
    exit_date: pd.Timestamp
    exit_price: float
    ret: float          # 扣费后收益
    hold_days: int
    reason: str
    strength: float     # 信号强度（量比），同日排序用


def _sell_cost(cost):
    return cost["commission"] + cost["stamp_tax"] + cost["slippage"]


def simulate_stock(df: pd.DataFrame, code: str, cfg: dict, name: str = "") -> list[Trade]:
    d = prepare(df, cfg).reset_index(drop=True)
    e, cost = cfg["exit"], cfg["cost"]
    pct = limit_pct(code, name)
    trades, i, n = [], 1, len(d)
    while i < n - 1:
        if not d.at[i, "entry"]:
            i += 1
            continue
        b = i + 1
        up, _ = limit_prices(d.at[i, "close"], pct)
        if d.at[b, "open"] >= up - 1e-6:          # 一字/开盘涨停买不进
            i += 1
            continue
        entry = d.at[b, "open"] * (1 + cost["slippage"])
        buy_cost = cost["commission"]
        remaining, proceeds = 1.0, 0.0             # 仓位比例、已卖出所得（相对买入价的倍数之和）
        tp_done = [False, False]
        max_close, pending, reason = d.at[b, "close"], None, None
        j = b + 1
        while j < n and remaining > 1e-9:
            o, h, l, c = d.at[j, "open"], d.at[j, "high"], d.at[j, "low"], d.at[j, "close"]
            _, down = limit_prices(d.at[j - 1, "close"], pct)
            locked_down = l <= down + 1e-6 and h <= down + 1e-6
            hold = j - b
            if pending and not (o <= down + 1e-6 and locked_down):
                proceeds += remaining * o * (1 - _sell_cost(cost)); remaining = 0; reason = pending
                break
            stop_px = entry * (1 - e["stop_loss"])
            if l <= stop_px and not locked_down:
                px = min(o, stop_px)
                proceeds += remaining * px * (1 - _sell_cost(cost)); remaining = 0; reason = "止损"
                break
            for k, key in enumerate(("take_profit_1", "take_profit_2")):
                tp = e.get(key)
                if tp and not tp_done[k] and h >= entry * (1 + tp):
                    part = 1 / 3
                    proceeds += part * max(o, entry * (1 + tp)) * (1 - _sell_cost(cost))
                    remaining -= part; tp_done[k] = True
            max_close = max(max_close, c)
            ma_n = e.get("exit_below_ma")
            if hold >= e["max_hold_days"]:
                pending = "到期"
            elif c <= max_close * (1 - e["trailing_stop"]):
                pending = "移动止盈"
            elif ma_n and c < d.at[j, f"ma{ma_n}"]:
                pending = f"跌破MA{ma_n}"
            elif e.get("time_stop_days") and hold >= e["time_stop_days"] and c <= entry and not any(tp_done):
                pending = "时间止损"
            j += 1
        if remaining > 1e-9:                       # 数据结束，按最后收盘结算
            j = n - 1
            proceeds += remaining * d.at[j, "close"] * (1 - _sell_cost(cost)); reason = reason or "数据结束"
        exit_px = proceeds                         # 加权卖出价
        ret = exit_px / (entry * (1 + buy_cost)) - 1
        trades.append(Trade(code, d.at[i, "date"], d.at[b, "date"], round(entry, 3), d.at[j, "date"],
                            round(exit_px, 3), ret, j - b, reason, float(d.at[i, "vol_ratio5"])))
        i = j                                      # 平仓后再找下一个信号
    return trades


def portfolio(trades: list[Trade], cfg: dict) -> tuple[pd.DataFrame, pd.Series]:
    """按仓位上限筛选成交，返回实际成交与已实现权益曲线。"""
    if not trades:
        return pd.DataFrame(), pd.Series(dtype=float)
    k = cfg["backtest"]["max_positions"]
    tdf = pd.DataFrame([asdict(t) for t in trades]).sort_values(["entry_date", "strength"], ascending=[True, False])
    open_exits, taken = [], []
    for idx, t in tdf.iterrows():
        open_exits = [x for x in open_exits if x > t.entry_date]   # 卖出当日释放仓位，次日可用
        if len(open_exits) < k:
            open_exits.append(t.exit_date); taken.append(idx)
    acc = tdf.loc[taken].sort_values("exit_date")
    equity = cfg["backtest"]["init_cash"] * (1 + acc.groupby("exit_date")["ret"].sum() / k).cumprod()
    return acc.reset_index(drop=True), equity


def stats(acc: pd.DataFrame, equity: pd.Series, init_cash: float = 1_000_000) -> dict:
    if acc.empty:
        return {"成交笔数": 0}
    r = acc["ret"]
    wins, losses = r[r > 0], r[r <= 0]
    years = max((acc["exit_date"].max() - acc["entry_date"].min()).days / 365.25, 1 / 365)
    curve = pd.concat([pd.Series([init_cash]), equity.reset_index(drop=True)])
    dd = (curve / curve.cummax() - 1).min()
    return {
        "成交笔数": int(len(r)),
        "胜率": round(len(wins) / len(r), 4),
        "平均收益": round(r.mean(), 4),
        "平均盈利": round(wins.mean(), 4) if len(wins) else 0,
        "平均亏损": round(losses.mean(), 4) if len(losses) else 0,
        "盈亏比": round(wins.mean() / -losses.mean(), 2) if len(wins) and len(losses) and losses.mean() < 0 else np.inf,
        "利润因子": round(wins.sum() / -losses.sum(), 2) if losses.sum() < 0 else np.inf,
        "平均持仓天数": round(acc["hold_days"].mean(), 2),
        "最大回撤": round(dd, 4),
        "期末权益": round(float(equity.iloc[-1]), 2),
        "年化收益": round((equity.iloc[-1] / init_cash) ** (1 / years) - 1, 4),
        "退出原因": acc["reason"].value_counts().to_dict(),
    }


def forward_returns(df: pd.DataFrame, cfg: dict, horizons=(1, 3, 5, 10)) -> pd.DataFrame:
    """事件研究：信号次日开盘买入后 N 日收盘的收益（不含止损），用于验证信号本身是否有效。"""
    d = prepare(df, cfg).reset_index(drop=True)
    rows = []
    for i in d.index[d["entry"]]:
        if i + 1 >= len(d):
            continue
        base = d.at[i + 1, "open"]
        row = {"date": d.at[i, "date"]}
        for h in horizons:
            k = i + h
            row[f"r{h}"] = d.at[k, "close"] / base - 1 if k < len(d) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)
