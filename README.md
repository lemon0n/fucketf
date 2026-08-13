# fucketf v5

一份“先给当前名单、再逐只深挖、最后展示模型”的 ETF 日报。首屏固定列出
推荐关注 ETF 与回避 ETF，随后逐只拆解真实资金、量价代理和直接新闻，再回答
八项市场问题，避免用术语或综合评分掩盖证据冲突。

## 当前推荐、回避和逐只深挖

- 推荐关注最多 3 只，只来自规则候选；它是研究名单，不等于自动买入。
- 回避 ETF 最多 3 只，与推荐名单严格去重；它只表示限制新增，不等于卖出或做空。
- 回避分固定使用：真实净赎回 40%、弱规则评分 25%、5 日相对弱势 15%、
  20 日相对弱势 10%、撤退风险 10%。低于 25 分不为凑数入选，同组只留 1 只。
- 每只推荐和回避 ETF 都固定回答：真实份额变化及估算金额、1/5/20 日收益、
  5/20 日相对沪深300、20 日量比、近 14 日直接新闻、近 3 日热度、
  资金与新闻是共振还是背离，以及下一步确认/移出条件。
- 新闻检索在规则模型选出候选之后运行，只补充报告，不回填当日交易评分；
  同日信息会标记“报告补充·未回填规则”，搜索失败则保留旧缓存。
- 看板首屏设有独立的“每日ETF推荐与回避预警”板块，明确显示当天推荐数、
  回避数、报告日和每只ETF的预警状态；名单由每日流水线重新计算，不是固定名单。

## 日报固定回答什么

| 顺序 | 问题 | 主要证据 | 不会冒充什么 |
|---:|---|---|---|
| 0 | 市场情绪 | ETF 上涨宽度、融资情绪、去重后的媒体方向 | 四大报不等于机构仓位 |
| 1 | 资金流向 | ETF 份额变化估算资金、融资净买入、量价代理 | 量价代理不等于真实净流入 |
| 2 | ETF 申赎 | 交易所份额变化 × ETF 收盘价 | 金额是估算，份额方向是真实快照 |
| 3 | 板块轮动 | 每组一只高流动性代表的 5/20 日相对强度 | 单日冲高不等于持续主线 |
| 4 | 宏观周期 | 按发布日期使用的 PMI/CPI/PPI/工业/消费/货币指标 | 宏观改善不等于股价已确认 |
| 5 | 风险偏好 | 攻守资产强弱、权益与防守 ETF 申赎、宽度/波动 | 风险预算不等于上涨概率 |
| 6 | 机构资金 | 核心宽基、债券和黄金 ETF 的“机构型产品”申赎代理 | ETF 持有人不能直接识别为机构 |
| 7 | 成交结构 | 成交活跃度、上涨成交占比、头部集中度、放量下跌数 | 收盘价×量仅作相对结构代理 |

每一项严格按以下顺序输出：

1. 一句话结论；
2. 至少一个数值、截止日和数据属性；
3. 对当前持仓意味着什么；
4. 下一次出现什么才算确认；
5. 口径和限制。

## 最重要的护栏

- 缺失数据写“数据不足”，不能用 `0` 假装真实中性。
- ETF 申赎、价格成交代理和媒体叙事必须分栏，不得互相替代。
- 四大报是公开叙事，不再命名为“机构情绪”。情绪分为
  `(明确看多标题数 - 明确看空标题数) / 去重标题总数`，中性标题进入分母。
- 2024-08-19 后不继续套用旧北向日度持仓披露口径；没有可审计数据时不声称
  “北向/机构今日净流入”。
- 外部事件只使用决策日以前、能确认发布日期的内容；不精确区分盘前/盘后时，
  统一滞后一日进入规则信号。
- 规则模型相对沪深300为负，或 Logit 未通过样本外准确率、Brier、交易数与
  分折 Alpha 护栏时，候选只能标记为“研究观察/等待确认”，不能写成买卖指令。
- 新因子先进入 Shadow。只有滚动样本外 Alpha、Brier、回撤和交易次数同时改善，
  才允许升级到交易评分。

这些结论由 `market_diagnostics.py` 的固定计算和句式生成，不依赖大模型自由发挥；
因此即使下游只使用较弱模型，也只能压缩或转述结构化证据，不能捏造结论。
若仍需用低能力模型生成文字，必须使用
[`prompts/etf_report_renderer.md`](prompts/etf_report_renderer.md) 的固定字段映射、
禁用词和发布前自检；网页本身则直接由 Python 渲染，不经过大模型。

## 数据与时间口径

- 行情：腾讯财经前复权日线；并发增量更新、有限超时，失败保留缓存。
- ETF 份额：[上交所 ETF 规模](https://www.sse.com.cn/market/funddata/volumn/etfvolumn/)
  与[深交所基金列表](https://fund.szse.cn/marketdata/fundslist/index.html)。上交所按周和
  最新日留档；深交所由流水线逐日累积快照。只有两个不同日期才计算流量。
- 融资融券：东方财富公开数据，只作为杠杆/大众风险偏好。
- 四大报：[同花顺四大报](https://stock.10jqka.com.cn/bktt_list/)，只作为媒体叙事。
- 宏观：采集宏观接口，同时把[国家统计局发布页](https://www.stats.gov.cn/sj/zxfb/)
  或人民银行作为权威核对链接。宏观指标只按 `release_date` 使用；不完整的历史发布日
  不回填回测。
- 北向披露限制：[港交所 Stock Connect 页面](https://www.hkex.com.hk/Mutual-Market/Stock-Connect/Top-Stock-Connect-Shareholdings/Northbound-SZ?sc_lang=zh-HK)。

日报同时显示行情日、各数据最新日和缺口。抓取失败不会用空文件覆盖已有历史。

## 流水线

```text
ETF行情/份额 ─┐
媒体/事件/宏观 ├─→ 规则候选 ─→ 逐只新闻检索 ─→ 样本外护栏
两融/成交结构 ┘                                  ↓
                    推荐/回避 + 逐只深挖 + 八项诊断 ─→ 交接单/看板
```

主要输出：

- `data/model_results.json`：规则模型与已结算回测；
- `data/econometric_results.json`：Logit/OLS/Lasso 诊断和生产资格；
- `data/targeted_news.json`：逐只 ETF 的近 14 日定向新闻缓存，仅作报告补充；
- `data/market_diagnostics.json`：推荐/回避、逐只深挖、八项结论与输出契约；
- `data/next_day_handoff.json`：下一交易日复核和未结算标签；
- `dashboard/dashboard.html`：结论优先的研究看板；技术模型放在折叠附录。
- `dashboard/fucketf_daily_alert_final_2026-08-13.html`：本次独立交付的每日推荐/回避预警看板快照。

## 运行与验证

```bash
pip install -r requirements.txt
python3 daily_pipeline.py --dry-run
python3 -m unittest discover -v
```

确认数据日期、八项卡片和回测护栏无误后，再运行生产流程：

```bash
python3 daily_pipeline.py
```

流水线会提交并推送。GitHub 凭据应通过系统凭据管理器、GitHub App、Actions secret
或已配置的安全认证提供；不要把个人访问令牌写进命令、远程 URL、README 或日志。

## 代码地图

```text
daily_pipeline.py           每日入口、超时和失败策略
fetch_etf_data.py           行情增量更新
fetch_etf_shares.py         ETF 份额增量快照
fetch_macro_data.py         带发布日期的宏观快照
etf_model_run.py            规则候选与历史结算
fetch_targeted_news.py      候选确定后的逐只ETF定向新闻检索
econometric_model.py        样本外诊断和生产护栏
market_diagnostics.py       推荐/回避、逐只深挖与八项确定性结论
generate_daily_handoff.py   下一交易日交接单
generate_dashboard.py       HTML 看板
prompts/etf_report_renderer.md  低能力模型固定渲染规则
test_model_integrity.py     正确性与输出契约回归测试
```

本项目仅用于研究，不构成投资建议。历史回测不代表未来收益。
