import pandas as pd
from ashare.youzi import load_seats, tag_seat, seat_table


def test_tag_seat():
    seats = load_seats()
    assert tag_seat("国泰海通证券股份有限公司南京太平南路证券营业部", seats) == "作手新一"
    assert tag_seat("东方财富证券股份有限公司拉萨团结路第二证券营业部", seats) == "拉萨天团"
    assert tag_seat("机构专用", seats) == "机构" and tag_seat("深股通专用", seats) == "北向"
    assert tag_seat("某某证券某某营业部", seats) == ""


def test_seat_table_aggregates():
    s = pd.DataFrame({"游资": ["拉萨天团"] * 3, "side": ["买", "买", "卖"], "name": ["A", "A", "B"], "3日": [False] * 3,
                      "BUY": [1e7, 2e7, 0], "SELL": [0, 0, 5e6]})
    t = seat_table(s)
    assert t.loc[0, "买入"] == "A2席3000万" and t.loc[0, "卖出"] == "B500万" and t.loc[0, "净买"] == 2.5e7
