"""回测股票池。优先读取中证指数成分股（含历史退市风险提示），失败用内置样本。"""
from pathlib import Path

SAMPLE = ["600519", "000858", "601318", "600036", "000333", "002594", "300750", "601012", "600276", "000001",
          "002415", "300059", "601888", "600030", "002475", "300124", "688981", "601899", "600900", "000725",
          "002230", "300274", "600809", "002714", "601166", "000568", "600887", "300015", "002352", "600031",
          "688111", "300760", "601919", "000063", "002371", "300308", "600438", "601138", "300502", "002460"]


def load_universe(name_or_file: str = "sample") -> list[str]:
    p = Path(name_or_file)
    if p.exists():
        return [l.strip().zfill(6) for l in p.read_text().splitlines() if l.strip() and not l.startswith("#")]
    if name_or_file in ("hs300", "zz500", "zz1000"):
        import akshare as ak
        sym = {"hs300": "000300", "zz500": "000905", "zz1000": "000852"}[name_or_file]
        df = ak.index_stock_cons_csindex(symbol=sym)
        return df["成分券代码"].astype(str).str.zfill(6).tolist()
    return SAMPLE
