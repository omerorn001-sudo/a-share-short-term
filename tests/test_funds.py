import pandas as pd

from ashare import funds
from ashare.batch import conclude


def test_fund_score_rules():
    df = pd.DataFrame([{"code": "000001", "main5": 1e8, "float_mv": 1e10, "rz_bal": 1e9, "rz_chg5": 0.05, "rz_ratio": 3.0,
                        "lhb_n": 1, "lhb_inst_n": 2, "lhb_inst": -5e7, "lhb_net": 1e7, "org_ratio": 5.0, "org_ratio_chg": 1.0},
                       {"code": "000002", "main5": -1e8, "float_mv": 1e10, "rz_bal": None, "lhb_n": None,
                        "org_ratio_chg": None}])
    s = funds.score(df)
    assert list(s["分_主力"]) == [1, -1]
    assert s.loc[0, "分_融资"] == 1 and s.loc[0, "分_龙虎榜"] == -1 and s.loc[0, "分_机构持仓"] == 1
    assert s.loc[0, "资金分"] == 2 and bool(s.loc[0, "⑦资金分≥1"]) and bool(s.loc[0, "⑥主力5日净流入"])
    assert s.loc[1, "资金分"] == -1 and not s.loc[1, "⑥主力5日净流入"]


def test_crowded_margin_penalty():
    s = funds.score(pd.DataFrame([{"code": "1", "main5": 1, "rz_bal": 1, "rz_chg5": 0.0, "rz_ratio": 9.0}]))
    assert s.loc[0, "分_融资"] == -1


def test_conclude_requires_fund_conditions():
    base = {"code": "1", "name": "x", "amount": 1e9, "趋势分": 2, "买点分": 2, "预警分": 1, "技术满足": 5, "①突破": True,
            "⑤均线多头": True, "gap": 0, "调研次数": 0, "调研家次": 0, "板块排名": 50, "净利": 1, "净利同比": 0, "pe_ttm": 20}
    ok = conclude(pd.DataFrame([{**base, "资金分": 2, "⑥主力5日净流入": True, "⑦资金分≥1": True}]), 100, 0)
    assert ok.loc[0, "结论"] == "买入" and ok.loc[0, "7条满足"] == 7
    weak = conclude(pd.DataFrame([{**base, "资金分": 2, "⑥主力5日净流入": True, "⑦资金分≥1": True}]), 100, -6)
    assert weak.loc[0, "结论"] == "信号成立·大盘偏弱观察"
    nofund = conclude(pd.DataFrame([{**base, "资金分": 0, "⑥主力5日净流入": True, "⑦资金分≥1": False}]), 100, 0)
    assert nofund.loc[0, "结论"] == "技术触发·资金不支持"
