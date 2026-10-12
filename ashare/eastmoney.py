"""东方财富网页版行情接口直连爬虫（与 quote.eastmoney.com 网页同源）。

AKShare 的东财快照一次请求 5000 条，云服务器上常被直接断开；这里模拟网页请求：
每页 100 条分页并发、浏览器请求头、多节点轮换、失败重试。
"""
from __future__ import annotations

import random
import time
from concurrent.futures import ThreadPoolExecutor

import pandas as pd
import requests

HOSTS = ["push2.eastmoney.com", "push2delay.eastmoney.com", "48.push2.eastmoney.com", "17.push2.eastmoney.com",
         "82.push2.eastmoney.com"]
HIS_HOSTS = ["push2his.eastmoney.com", "63.push2his.eastmoney.com", "33.push2his.eastmoney.com"]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/126.0 Safari/537.36",
    "Referer": "https://quote.eastmoney.com/center/gridlist.html",
    "Accept": "application/json, text/plain, */*",
}
FS_A = "m:0 t:6,m:0 t:80,m:1 t:2,m:1 t:23,m:0 t:81 s:2048"      # 沪深京 A 股
FS_INDUSTRY = "m:90 t:2 f:!50"
FS_CONCEPT = "m:90 t:3 f:!50"

SPOT_FIELDS = {"f12": "code", "f14": "name", "f2": "price", "f3": "pct_chg", "f5": "volume", "f6": "amount",
               "f8": "turnover", "f10": "volume_ratio", "f15": "high", "f16": "low", "f17": "open",
               "f18": "prev_close", "f20": "total_mv", "f21": "float_mv", "f9": "pe_ttm", "f23": "pb"}
BOARD_FIELDS = {"f12": "board_code", "f14": "board", "f3": "pct_chg", "f8": "turnover", "f62": "net_inflow",
                "f104": "up", "f105": "down", "f128": "leader", "f136": "leader_pct", "f20": "total_mv"}

_session = requests.Session()
_session.headers.update(HEADERS)


def _get(path: str, params: dict, hosts=HOSTS, tries: int = 10, timeout: float = 8) -> dict:
    """东财节点时好时坏（502/断开/空响应），按 节点×协议 轮换重试。"""
    targets = [(sch, h) for h in hosts for sch in ("https", "http")]
    random.shuffle(targets)
    last = None
    for i in range(tries):
        sch, host = targets[i % len(targets)]
        try:
            r = _session.get(f"{sch}://{host}{path}", params=params, timeout=timeout)
            if r.status_code == 200 and r.text.lstrip().startswith("{"):
                j = r.json()
                if j.get("data") is not None:
                    return j
            last = RuntimeError(f"{host} HTTP {r.status_code}")
        except Exception as e:
            last = e
        time.sleep(0.3 * (i + 1) + random.random() * 0.3)
    raise last


def clist(fs: str, fields: dict, page_size: int = 100, workers: int = 2, sort_field: str = "f3",
          max_rows: int | None = None, passes: int = 4) -> pd.DataFrame:
    """分页抓取列表。失败页面会在后续轮次重试（东财对云服务器 IP 间歇性返回 502）。"""
    base = {"pz": page_size, "po": 1, "np": 1, "fltt": 2, "invt": 2, "fid": sort_field, "fs": fs,
            "fields": ",".join(fields), "ut": "bd1d9ddb04089700cf9c27f6f7426281"}
    first = _get("/api/qt/clist/get", {**base, "pn": 1}, tries=20)["data"]
    total = first["total"] if max_rows is None else min(first["total"], max_rows)
    got = {1: first["diff"]}
    todo = list(range(2, -(-total // page_size) + 1))

    def fetch(pn):
        time.sleep(random.random() * 0.5)
        try:
            return pn, _get("/api/qt/clist/get", {**base, "pn": pn}, tries=6)["data"]["diff"]
        except Exception:
            return pn, None

    for k in range(passes):
        if not todo:
            break
        if k:
            time.sleep(5 * k)
        with ThreadPoolExecutor(workers) as ex:
            for pn, part in ex.map(fetch, todo):
                if part is not None:
                    got[pn] = part
        todo = [pn for pn in todo if pn not in got]
    if todo:
        raise RuntimeError(f"东财分页 {len(todo)} 页抓取失败: {todo[:10]}")
    rows = [r for pn in sorted(got) for r in got[pn]]
    df = pd.DataFrame(rows).rename(columns=fields)
    df = df.replace("-", pd.NA)
    for c in df.columns:
        if c not in ("code", "name", "board", "board_code", "leader"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
    key = "code" if "code" in df else "board_code" if "board_code" in df else None
    if key:
        df = df.drop_duplicates(subset=[key]).reset_index(drop=True)
    if max_rows is None and len(df) < total * 0.98:
        raise RuntimeError(f"东财分页结果不完整: {len(df)}/{total}")
    return df.head(max_rows) if max_rows else df


def spot() -> pd.DataFrame:
    """全市场快照，含量比、换手率、流通市值、总市值（单位：元）。

    按代码排序分页（排序键盘中不变，分页不会错位或漏股）。
    """
    df = clist(FS_A, SPOT_FIELDS, sort_field="f12")
    df["code"] = df["code"].astype(str).str.zfill(6)
    return df


def boards(kind: str = "industry") -> pd.DataFrame:
    """板块排行。kind: industry / concept。net_inflow 为主力净流入（元）。"""
    return clist(FS_INDUSTRY if kind == "industry" else FS_CONCEPT, BOARD_FIELDS)


def kline(secid: str, beg: str = "19900101", end: str = "20500101", fqt: int = 1) -> pd.DataFrame:
    """日 K。secid 例：1.000001 上证指数、0.399006 创业板指、1.600519 茅台；fqt 0 不复权 1 前复权 2 后复权。"""
    j = _get("/api/qt/stock/kline/get", {
        "secid": secid, "klt": 101, "fqt": fqt, "beg": beg, "end": end, "lmt": 100000,
        "fields1": "f1,f2,f3,f4,f5,f6", "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        "ut": "fa5fd1943c7b386f172d6893dbfba10b"}, hosts=HIS_HOSTS)
    rows = [k.split(",") for k in (j["data"] or {}).get("klines", [])]
    cols = ["date", "open", "close", "high", "low", "volume", "amount", "amplitude", "pct_chg", "chg", "turnover"]
    df = pd.DataFrame(rows, columns=cols)
    df["date"] = pd.to_datetime(df["date"])
    for c in cols[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["volume"] = df["volume"] * 100       # 手 → 股
    return df


def secid_of(code: str, is_index: bool = False) -> str:
    code = str(code).lower().replace("sh", "1.").replace("sz", "0.")
    if "." in code:
        return code
    if is_index:
        return ("1." if code.startswith("000") else "0.") + code
    return ("1." if code.startswith(("6", "9")) else "0.") + code
