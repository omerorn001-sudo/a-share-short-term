import pytest

from ashare import eastmoney as em


def fake_get_factory(total=250, fail_once=(3,)):
    calls = {}

    def fake_get(path, params, hosts=None, tries=10, timeout=8):
        pn = params.get("pn", 1)
        if path.endswith("kline/get"):
            return {"data": {"klines": ["2026-10-09,10,11,11.5,9.8,1000,1.1e6,17,10,1,2.5"]}}
        calls[pn] = calls.get(pn, 0) + 1
        if pn in fail_once and calls[pn] == 1:
            raise RuntimeError("502")
        start = (pn - 1) * params["pz"]
        rows = [{"f12": f"{i:06d}", "f14": f"股{i}", "f2": 10.0, "f10": "-", "f21": 3e9}
                for i in range(start, min(start + params["pz"], total))]
        return {"data": {"total": total, "diff": rows}}
    return fake_get


def test_clist_pagination_retry(monkeypatch):
    monkeypatch.setattr(em, "_get", fake_get_factory())
    monkeypatch.setattr(em.time, "sleep", lambda s: None)
    df = em.spot()
    assert len(df) == 250 and df["code"].is_unique
    assert df["volume_ratio"].isna().all()           # "-" → 缺失
    assert df["float_mv"].iloc[0] == 3e9


def test_clist_incomplete_raises(monkeypatch):
    monkeypatch.setattr(em, "_get", fake_get_factory(fail_once=()))
    monkeypatch.setattr(em.time, "sleep", lambda s: None)
    original = em._get

    def always_fail_page2(path, params, **kw):
        if params.get("pn") == 2:
            raise RuntimeError("502")
        return original(path, params, **kw)
    monkeypatch.setattr(em, "_get", always_fail_page2)
    with pytest.raises(RuntimeError):
        em.spot()


def test_kline_parse(monkeypatch):
    monkeypatch.setattr(em, "_get", fake_get_factory())
    df = em.kline("1.000001")
    assert df.iloc[0]["close"] == 11 and df.iloc[0]["volume"] == 100000


def test_secid():
    assert em.secid_of("600519") == "1.600519"
    assert em.secid_of("000001") == "0.000001"
    assert em.secid_of("000001", is_index=True) == "1.000001"
    assert em.secid_of("sz399006") == "0.399006"
