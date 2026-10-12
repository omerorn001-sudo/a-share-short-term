"""命令行入口：python -m ashare.cli <命令>。"""
from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path

import pandas as pd

from . import data
from .backtest import forward_returns, portfolio, simulate_stock, stats
from .config import load_config
from .strategy import prepare, sell_warnings
from .universe import load_universe

REPORT_DIR = Path(__file__).resolve().parent.parent / "reports"


def _today():
    return pd.Timestamp.now(tz="Asia/Shanghai").strftime("%Y%m%d")


def _save(df: pd.DataFrame, name: str) -> Path:
    REPORT_DIR.mkdir(exist_ok=True)
    p = REPORT_DIR / f"{name}.csv"
    df.to_csv(p, index=False, encoding="utf-8-sig")
    return p


def _print(obj):
    if isinstance(obj, pd.DataFrame):
        with pd.option_context("display.max_rows", 100, "display.width", 200, "display.unicode.east_asian_width", True):
            print(obj.to_string(index=False))
    else:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def _load_hist(codes, start, end, verbose=True):
    out = {}
    for i, c in enumerate(codes, 1):
        try:
            out[c] = data.stock_hist(c, start, end)
        except Exception as e:
            if verbose:
                print(f"[跳过] {c}: {e!r}"[:120])
        if verbose and i % 20 == 0:
            print(f"已加载 {i}/{len(codes)}")
    return out


def cmd_market(a, cfg):
    from .market import market_report
    _print(market_report(cfg, a.date))


def cmd_boards(a, cfg):
    from .market import hot_boards
    _print(hot_boards(a.top))


def cmd_screen(a, cfg):
    from .screener import screen
    df = screen(cfg, a.date)
    _print(df.head(a.top))
    print("已保存:", _save(df, f"screen_{a.date or _today()}"))


def cmd_check(a, cfg):
    """持仓体检：code:成本价 ..."""
    end = a.date or _today()
    start = (pd.Timestamp(end) - pd.Timedelta(days=200)).strftime("%Y%m%d")
    e = cfg["exit"]
    rows = []
    for item in a.holdings:
        code, _, cost = item.partition(":")
        d = prepare(data.stock_hist(code, start, end), cfg)
        w = sell_warnings(d, cfg).iloc[-1]
        last = d.iloc[-1]
        flags = [k for k, v in w.items() if v]
        pnl = last["close"] / float(cost) - 1 if cost else None
        action = "持有"
        if pnl is not None and pnl <= -e["stop_loss"]:
            action = "止损离场"
        elif len(flags) >= 2 or any(f.startswith("跌破") for f in flags):
            action = "减仓/离场"
        elif pnl is not None and pnl >= e["take_profit_1"]:
            action = "分批止盈"
        elif flags:
            action = "警惕"
        rows.append({"代码": code, "日期": str(last["date"].date()), "收盘": last["close"],
                     "盈亏": None if pnl is None else round(pnl, 4),
                     "MA5": round(last["ma5"], 2), "MA10": round(last["ma10"], 2),
                     "信号": "、".join(flags) or "无", "建议": action})
    _print(pd.DataFrame(rows))


def run_backtest(hist: dict, cfg: dict):
    trades = []
    for code, df in hist.items():
        trades += simulate_stock(df, code, cfg)
    acc, eq = portfolio(trades, cfg)
    return acc, eq, stats(acc, eq, cfg["backtest"]["init_cash"])


def cmd_backtest(a, cfg):
    codes = load_universe(a.universe)[: a.limit or None]
    hist = _load_hist(codes, a.start, a.end)
    acc, eq, st = run_backtest(hist, cfg)
    _print(st)
    if not acc.empty:
        print("成交明细:", _save(acc, f"trades_{a.start}_{a.end}"))
        print("权益曲线:", _save(eq.rename("equity").reset_index(), f"equity_{a.start}_{a.end}"))


def cmd_study(a, cfg):
    codes = load_universe(a.universe)[: a.limit or None]
    hist = _load_hist(codes, a.start, a.end)
    ev = pd.concat([forward_returns(df, cfg).assign(code=c) for c, df in hist.items()], ignore_index=True)
    if ev.empty:
        print("无信号"); return
    hs = [h for h in ev.columns if h.startswith("r")]
    summary = pd.DataFrame([{"持有期": f"{h[1:]}日", "样本": int(ev[h].count()), "平均收益": round(ev[h].mean(), 4),
                             "中位数": round(ev[h].median(), 4), "胜率": round((ev[h] > 0).mean(), 4)} for h in hs])
    _print(summary)
    print("事件明细:", _save(ev, f"study_{a.start}_{a.end}"))


def cmd_sweep(a, cfg):
    """参数网格：--grid exit.stop_loss=0.05,0.07 exit.exit_below_ma=5,10"""
    codes = load_universe(a.universe)[: a.limit or None]
    hist = _load_hist(codes, a.start, a.end)
    keys, values = [], []
    for g in a.grid:
        k, v = g.split("=")
        keys.append(k); values.append([json.loads(x) for x in v.split(",")])
    rows = []
    for combo in itertools.product(*values):
        c = load_config(a.config, dict(zip(keys, combo)))
        _, _, st = run_backtest(hist, c)
        st.pop("退出原因", None)
        rows.append({**dict(zip(keys, combo)), **st})
    df = pd.DataFrame(rows).sort_values("年化收益", ascending=False)
    _print(df)
    print("已保存:", _save(df, f"sweep_{a.start}_{a.end}"))


def main(argv=None):
    p = argparse.ArgumentParser(prog="ashare", description="A股短线选股、择时与回测")
    p.add_argument("--config", default=None, help="配置文件路径，默认 config.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("market", help="大环境评分与建议仓位"); s.add_argument("--date")
    s = sub.add_parser("boards", help="行业板块强度排名"); s.add_argument("--top", type=int, default=10)
    s = sub.add_parser("screen", help="全市场短线选股"); s.add_argument("--date"); s.add_argument("--top", type=int, default=20)
    s = sub.add_parser("check", help="持仓卖点体检"); s.add_argument("holdings", nargs="+", help="代码:成本价"); s.add_argument("--date")
    for name, h in [("backtest", "策略回测"), ("study", "信号事件研究"), ("sweep", "参数网格回测")]:
        s = sub.add_parser(name, help=h)
        s.add_argument("--start", default="20210101"); s.add_argument("--end", default=_today())
        s.add_argument("--universe", default="sample", help="sample / hs300 / zz500 / zz1000 / 代码文件")
        s.add_argument("--limit", type=int, default=0, help="只取前 N 只（调试用）")
        if name == "sweep":
            s.add_argument("--grid", nargs="+", required=True)

    a = p.parse_args(argv)
    cfg = load_config(a.config)
    globals()[f"cmd_{a.cmd}"](a, cfg)


if __name__ == "__main__":
    main()
