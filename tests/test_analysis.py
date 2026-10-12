import pandas as pd

from ashare import analysis as an
from ashare.config import load_config
import numpy as np

from tests.test_core import make_df

CFG = load_config()


def test_stock_analysis_reports_missing_dimensions(monkeypatch):
    base = list(10 + 0.02 * np.arange(70))
    df = make_df(base + [base[-1] * 1.05], [1e6] * 70 + [3e6])
    monkeypatch.setattr(an.data, "stock_hist", lambda *a, **k: df)
    monkeypatch.setattr(an.dc, "stock_profile", lambda c: {"code": c, "name": "测试股", "industry": "软件开发", "pe_ttm": 20, "float_mv": 5e9})
    monkeypatch.setattr(an.dc, "fund_flow", lambda c, n=10: pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=5), "main": [1e7] * 5}))
    monkeypatch.setattr(an.dc, "margin_stock", lambda c, n=30: pd.DataFrame())
    monkeypatch.setattr(an.dc, "lhb_stock", lambda c, s: pd.DataFrame())
    monkeypatch.setattr(an.dc, "surveys_stock", lambda c, s: pd.DataFrame())
    monkeypatch.setattr(an, "industry_survey_heat", lambda days=30: (pd.DataFrame(), None))
    monkeypatch.setattr(an, "_imap", lambda: None)
    monkeypatch.setattr(an, "_boards", lambda: (pd.DataFrame({"board": ["软件开发", "银行"], "pct_chg": [2.0, -1.0]}), None))
    r = an.stock_analysis("600000", CFG)
    names = {d.name: d for d in r["dims"]}
    assert "未上龙虎榜" in names["龙虎榜"].detail
    assert "没有机构调研" in names["机构调研"].detail and "没有任何公司被机构调研" in names["机构调研"].detail
    assert "不是两融标的" in names["融资（杠杆资金）"].detail
    assert any("龙虎榜" in m for m in r["missing"]) and any("机构调研" in m for m in r["missing"])
    assert r["dims"][1].facts["signal"] and r["action"].startswith(("买入", "谨慎买入"))
    text = an.render_stock(r)
    assert "缺失或近期未发生的维度" in text and "价位计划" in text
