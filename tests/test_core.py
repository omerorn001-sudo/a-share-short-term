import numpy as np
import pandas as pd

from ashare.backtest import portfolio, simulate_stock, stats
from ashare.config import load_config
from ashare.market import score_environment
from ashare.rules import limit_pct, limit_prices
from ashare.strategy import prepare

CFG = load_config()


def make_df(closes, vols=None):
    closes = np.asarray(closes, float)
    n = len(closes)
    opens = np.r_[closes[0], closes[:-1]]
    return pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=n), "open": opens,
                         "high": np.maximum(opens, closes) * 1.005, "low": np.minimum(opens, closes) * 0.995,
                         "close": closes, "volume": vols if vols is not None else np.full(n, 1e6)})


def breakout_series():
    base = list(10 + 0.02 * np.arange(40))          # 缓慢上行，均线多头
    closes = base + [base[-1] * 1.05] + [base[-1] * 1.05 * (1.02 ** k) for k in range(1, 6)] + [base[-1] * 0.9] * 5
    vols = [1e6] * 40 + [3e6] + [1.2e6] * 10
    return make_df(closes, vols)


def test_limit_rules():
    assert limit_pct("600000") == 0.10 and limit_pct("300750") == 0.20 and limit_pct("688981") == 0.20
    assert limit_pct("000001", "*ST某某") == 0.05
    assert limit_prices(10, 0.1) == (11.0, 9.0)


def test_entry_signal_fires_on_breakout():
    d = prepare(breakout_series(), CFG)
    assert d["entry"].iloc[40]
    assert not d["entry"].iloc[:40].any()


def test_backtest_trade_and_t_plus_1():
    trades = simulate_stock(breakout_series(), "600000", CFG)
    assert trades, "应产生交易"
    t = trades[0]
    assert t.entry_date > t.signal_date and t.exit_date > t.entry_date   # T+1
    acc, eq = portfolio(trades, CFG)
    st = stats(acc, eq, CFG["backtest"]["init_cash"])
    assert st["成交笔数"] >= 1 and -1 < st["平均收益"] < 1


def test_stop_loss_triggers():
    df = breakout_series()
    df.loc[42:, ["open", "close"]] = df.loc[41, "close"] * 0.9
    df.loc[42:, "high"] = df.loc[42:, "open"] * 1.001
    df.loc[42:, "low"] = df.loc[42:, "open"] * 0.999
    t = simulate_stock(df, "300001", CFG)[0]
    assert t.reason == "止损" and t.ret < -0.05


def test_limit_up_open_cannot_buy():
    df = breakout_series()
    df.loc[41, "open"] = round(df.loc[40, "close"] * 1.1, 2)
    df.loc[41, "high"] = df.loc[41, "open"]
    trades = simulate_stock(df, "600000", CFG)
    assert all(t.entry_date != df.loc[41, "date"] for t in trades)


def test_market_score_range():
    idx = make_df(list(3000 + np.arange(30) * 5))
    r = score_environment(idx, zt=80, dt=2, zb=10, cfg=CFG)
    assert 70 <= r["评分"] <= 100 and r["建议仓位"] == "5-8成"
