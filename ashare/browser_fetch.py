"""通过外部浏览器（CDP，如 Notion 云电脑共享浏览器或你本机 Chrome --remote-debugging-port）取东财数据。

云服务器 IP 被东财 push2 限流时，换一个出口 IP 的浏览器直接打开接口地址读取 JSON。
用法：设置环境变量 AGENT_BROWSER_CDP（或 ASHARE_CDP）为 CDP 地址。
"""
from __future__ import annotations

import json
import os


def fetch_json(urls: list[str], cdp: str | None = None) -> dict:
    from playwright.sync_api import sync_playwright
    cdp = cdp or os.environ.get("ASHARE_CDP") or os.environ.get("AGENT_BROWSER_CDP")
    if not cdp:
        raise RuntimeError("未配置浏览器 CDP 地址")
    out = {}
    with sync_playwright() as p:
        br = p.chromium.connect_over_cdp(cdp)
        ctx = br.contexts[0] if br.contexts else br.new_context()
        pg = ctx.new_page()
        try:
            for i, u in enumerate(urls):
                if i:
                    pg.wait_for_timeout(800)          # 节流：东财按 IP 频率限流，连续上百次请求会被断开
                try:
                    pg.goto(u, timeout=20000)
                    t = pg.evaluate("() => document.body.innerText")
                    out[u] = json.loads(t[t.find("{"): t.rfind("}") + 1])
                except Exception as e:
                    out[u] = e
        finally:
            pg.close()
    return out


def fund_flow_url(secid: str, days: int = 10) -> str:
    return ("https://push2his.eastmoney.com/api/qt/stock/fflow/daykline/get?secid=" + secid +
            f"&lmt={days}&klt=101&fields1=f1,f2,f3,f7&fields2=f51,f52,f53,f54,f55,f56,f57")
