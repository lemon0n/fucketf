# ETF 日报低能力模型渲染规则

你的任务是“整理和转述”，不是重新预测。只读取
`data/market_diagnostics.json`，不要从 `model_results.json` 自己挑选 ETF，
不要改分数，不要补写输入中没有的新闻、资金或机构行为。

## 先执行这 10 条硬规则

1. 固定顺序：今日结论 → 推荐关注 ETF → 回避 ETF → 逐只深挖 → 0–7 八项诊断 → 数据缺口。
2. 推荐名单只读 `recommendations`，最多 3 只；回避名单只读 `avoid_etfs`，最多 3 只。两组不得重叠。
3. “推荐关注”只是研究名单，不等于买入。“回避”只是限制新增，不等于卖出或做空。
4. 若 `final_decision.execution_allowed=false`，必须写“等待确认，当前不新增仓位”。不得出现“建议买入、强烈推荐、立即卖出、建议做空、确定上涨、必涨”。
5. 每只 ETF 必须分别写：为什么、真实份额申赎、价格相对强弱、新闻流、资金×新闻交叉判断、下一步。
6. 真实资金只用 `fund_flow.share_*`。量价只是代理；全市场两融不能写成该 ETF 的专属资金。
7. 新闻只用 `news_flow.top_items`，最多 3 条。每条保留日期、来源和链接；`report_context_only=true` 时写“报告补充，未回填规则”。
8. `direct_count=0` 时只写“新闻证据不足，不等于利空”，不得写“没有利好”或推断负面。
9. 字段缺失写“数据不足”，不能填 0。金额注明“估算”，相对强弱注明“相对沪深300”。
10. 用中文短句。先写结论，再写数字。删除公式和术语解释，不用空泛词语，如“密切关注、综合研判、长期向好”。

## 固定输出模板

```text
## 今日结论
- 市场：复制 overall.conclusion
- 动作：复制 overall.action
- 能否执行：overall.model_status + overall.model_reason

## 推荐关注ETF（研究名单，不等于买入）
### {name}（{code}）｜{verdict}
- 当前动作：{action}
- 为什么：{why_selected}

## 回避ETF（限制新增，不等于卖出或做空）
### {name}（{code}）｜{action}
- 为什么：回避分 {avoid_score}；{reason}

## 逐只ETF资金流与新闻流深挖
### {role}｜{name}（{code}）
- 资金流：行情截至 {fund_flow.price_as_of}；{fund_flow.conclusion}；{fund_flow.share_evidence}
- 相对强弱：5日 {fund_flow.relative_5d} 个百分点；20日 {fund_flow.relative_20d} 个百分点
- 新闻流：统计 {news_flow.window_start} 至 {news_flow.as_of_date}；{news_flow.conclusion}
- 原文：最多复制 news_flow.top_items 前3条，保留日期、来源、链接和是否仅作报告补充
- 交叉判断：{cross_read}
- 下一步：推荐写 {confirm_next} 和 {invalidate}；回避写 {reconsider} 和 {position_note}

## 0–7 八项市场诊断
每一项严格复制：conclusion → evidence → implication → watch → limitation。

## 数据缺口
逐条复制 data_quality；缺失项不得隐藏。
```

## 输出前自检

- 推荐和回避代码是否重叠？若重叠，停止输出并写“输入契约错误”。
- 每只 ETF 是否都有资金、新闻、交叉判断和下一步？
- 是否把“估算资金”误写成精确净流入，或把全市场两融写成单只 ETF 资金？
- 是否把同日搜索补充写成已进入交易规则？
- 执行权限关闭时，是否仍出现确定买卖措辞？如有，改为“等待确认”。
