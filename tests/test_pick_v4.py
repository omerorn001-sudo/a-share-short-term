import pandas as pd
from ashare.batch import rank_v4


def test_rank_v4_prefers_pullback_low_turnover_high_vol():
    df = pd.DataFrame({"code": list("abcd"), "近20日%": [.1, -.1, 0, .2], "量能趋势": [1, .6, .8, 2],
                       "turnover": [5, 3, 4, 9], "20日波动": [.02, .05, .03, .01]})
    r = rank_v4(df, 3)
    assert list(r["code"]) == ["b", "c", "a"] and list(r["买入顺位"]) == [1, 2, 3]
