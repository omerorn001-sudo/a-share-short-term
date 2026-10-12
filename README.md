# A股短线选股与回测系统（a-share-short-term）

把"大环境 → 板块 → 个股 → 买点 → 卖点 → 风控"这套短线框架落成可执行、可回测的代码。数据来自 [AKShare](https://akshare.akfamily.xyz/)（免费），带本地缓存和多源回退。

> ⚠️ 仅供研究学习，不构成投资建议。默认参数是经验值，必须用回测校准。

## 功能

| 命令 | 作用 | 对应框架 |
|---|---|---|
| `market` | 指数趋势 + 量能 + 涨停/跌停/炸板率 → 0-100 分与建议仓位 | 大环境 |
| `boards` | 行业板块涨幅、涨跌家数、领涨股 | 板块 |
| `screen` | 全市场快照初筛（市值/换手/量比/成交额）→ 日线技术复核 → 涨停连板标签 → 评分 | 个股 + 买点 |
| `check` | 持仓卖点体检：跌破均线、长上影、放量滞涨、量价背离、MACD 顶背离、RSI/KDJ 超买 | 卖点 |
| `backtest` | 事件驱动回测（T+1、涨停买不进、跌停卖不出、佣金印花税滑点、分档止盈、止损） | 验证 |
| `study` | 信号事件研究：信号后 1/3/5/10 日收益与胜率 | 验证信号本身 |
| `sweep` | 参数网格回测，比较不同止损/均线/阈值 | 校准参数 |

## 安装

```bash
git clone <本仓库地址> && cd a-share-short-term
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 用法

```bash
python -m ashare.cli market                       # 今日大环境评分
python -m ashare.cli boards --top 10              # 板块强度
python -m ashare.cli screen --top 20              # 选股（盘后运行最准确）
python -m ashare.cli check 600519:1250 300750:300 # 持仓体检（代码:成本价）

# 回测与验证（首次会下载并缓存日线）
python -m ashare.cli backtest --start 20210101 --universe hs300
python -m ashare.cli study    --start 20210101 --universe zz500
python -m ashare.cli sweep    --start 20210101 --universe sample \
    --grid exit.exit_below_ma=0,5,10 exit.stop_loss=0.05,0.07
```

`--universe` 可选 `sample`（内置 40 只）、`hs300`、`zz500`、`zz1000`，或每行一个代码的文本文件。结果 CSV 保存在 `reports/`。

## 策略规则（默认，见 `config.yaml`）

**买入**（T 日收盘判定，T+1 开盘成交）：收盘创 20 日新高；成交量 ≥ 前 5 日均量 1.5 倍；站上 MA5，且 MA5 > MA10 > MA20；偏离 MA5 ≤ 7%；开盘涨停则放弃。

**卖出**（优先级从高到低）：
1. 硬止损：盘中跌破成本 −7%
2. 分档止盈：+10% 卖 1/3，+20% 再卖 1/3
3. 收盘信号，次日开盘执行：持有满 10 天 / 从最高收盘回撤 8% / 收盘跌破 MA5 / 3 天未盈利

**组合**：最多 5 仓，每仓 1/5，同日信号按量比排序。

## 示例结果（仅说明工具用法）

内置 40 只大盘股，2023-01 至 2026-10，默认参数：321 笔，胜率 31%，盈亏比 2.08，利润因子 0.94，年化 −2.8%，最大回撤 −21%。

结论：放量突破策略在大盘蓝筹上没有正期望，胜率太低。这正说明框架必须先验证再使用。可以换成中小盘股票池（`zz1000`），叠加 `market` 评分过滤，或者调整参数再测。

## 项目结构

```
ashare/
  data.py        数据层（AKShare 封装、缓存、东财→新浪/腾讯/同花顺回退）
  rules.py       涨跌停幅度、板块识别
  indicators.py  MA、量比、MACD、RSI、KDJ、K 线形态
  strategy.py    买入信号与卖出预警
  market.py      大环境评分、板块排名
  screener.py    选股
  backtest.py    回测引擎、组合与统计、事件研究
  universe.py    股票池
  cli.py         命令行
config.yaml      全部参数
tests/           离线单元测试（pytest）
skill/SKILL.md   Notion AI 技能说明
```

## 已知局限

- **幸存者偏差**：成分股用的是当前名单，回测结果会偏乐观。严谨研究应使用历史成分并包含退市股。
- **权益曲线**按已实现收益计算，持仓期间的浮亏没有计入回撤。
- 资金流、筹码分布等口径不一，未纳入回测；龙虎榜、情绪数据只用于盘后参考。
- 东方财富部分接口在海外或云服务器上可能被拒，系统会自动回退到其他数据源，但字段会变少（例如新浪快照没有量比）。

## 测试

```bash
pytest -q
```

## License

MIT
