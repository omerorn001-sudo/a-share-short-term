import numpy as np
import pandas as pd

from ashare import history as h


def test_sentiment_limit_detection():
    idx = pd.date_range("2026-01-01", periods=3)
    pct = pd.DataFrame({"600001": [10.0, 10.0, -10.0], "300001": [19.9, 5.0, 0.0], "000001": [-9.99, 9.9, 1.0]}, index=idx)
    high = pd.DataFrame({"600001": [10.0, 10.0, -9.0], "300001": [19.9, 20.0, 1.0], "000001": [-9.0, 9.9, 2.0]}, index=idx)
    # flag: 1 收在最高，-1 收在最低
    flag = pd.DataFrame({"600001": [1, 1, -1], "300001": [1, 0, 0], "000001": [-1, 1, 0]}, index=idx)
    hp = high + flag * 1000
    names = pd.Series({"600001": "甲", "300001": "乙", "000001": "丙"})
    s = h.sentiment_history(pct, hp, names)
    assert s["涨停"].tolist() == [2, 2, 0]
    assert s["跌停"].tolist() == [1, 0, 1]
    assert s["炸板"].tolist() == [0, 1, 0]          # 300001 第二天盘中触及 20% 未封住
    assert s["最高连板"].tolist() == [1, 2, 0]


def test_window_table():
    df = pd.DataFrame({"x": np.arange(300, dtype=float)})
    t = h.window_table(df, ["x"]).iloc[0]
    assert t["今日"] == 299 and t["近20日均值"] == 289.5 and t["近1年分位"] == "100%"
