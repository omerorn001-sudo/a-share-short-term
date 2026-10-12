"""A股交易规则：涨跌停幅度、板块识别。"""


def board_of(code: str) -> str:
    code = str(code).zfill(6)
    if code.startswith(("688", "689")):
        return "star"       # 科创板
    if code.startswith(("300", "301")):
        return "chinext"    # 创业板
    if code.startswith(("8", "4", "92")):
        return "bj"         # 北交所
    return "main"


def limit_pct(code: str, name: str = "") -> float:
    if "ST" in str(name).upper():
        return 0.05
    return {"star": 0.20, "chinext": 0.20, "bj": 0.30}.get(board_of(code), 0.10)


def limit_prices(prev_close: float, pct: float):
    up = round(prev_close * (1 + pct) + 1e-9, 2)
    down = round(prev_close * (1 - pct) + 1e-9, 2)
    return up, down
