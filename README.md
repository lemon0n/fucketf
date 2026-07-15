# fucketf

ETF 预测模型 — 规则模型 + 计量交叉验证，每日自动迭代。

## 数据源
- ETF 行情：腾讯财经 API（前复权，`qfq`）
- 四大报：同花顺 https://stock.10jqka.com.cn/bktt_list/

## 模型架构（三层）

### 第一层 · 报纸情绪评判
四大证券报标题 → 看涨/看跌关键词计数 → 情绪分 → 板块热点排名
- 情绪分 = (看涨次数 - 看跌次数) / (总信号 + 1)
- 26个看涨关键词 + 26个看跌关键词
- 板块匹配：标题关键词 → ETF板块
- 情绪信号在模型中享有 **3倍权重**

### 第二层 · 规则模型
五信号加权评分，选前3只ETF：
```
总分 = 3×S(情绪) + M(动量) + V(量比) + R(均值回归) + E(经验)
```
- 防偷看设计：价格类信号用前一日数据，情绪用当日报纸，收益=当日日内

### 第三层 · 计量交叉验证
- **Logit 回归**：预测涨跌方向 P(涨) 和概率
- **OLS 回归**：预测收益率 + 因子显著性检验
- **Lasso**：变量选择，剔除无效因子
- 看好板块：P(涨)最高的3个ETF + 建议文字
- 看空预警：P(跌)最高的3个ETF + 建议文字

## 每日流水线 (daily_pipeline.py)
1. 增量更新 ETF 行情 → data/etf_history.json
2. 抓取四大报 → data/newspapers.json
3. 运行规则模型 → data/model_results.json
4. 运行计量模型 → data/econometric_results.json
5. 生成看板 → etf-dashboard/dashboard.html

## 运行
```bash
pip install -r requirements.txt
python3 daily_pipeline.py
```

## 修复摘要

### 2026-07-15 修复记录
- **数据源切换**：东方财富(akshare) → 腾讯财经API（前复权），解决复权价格跳变和代理连接问题
- **存储迁移**：`/data/user/work/` → `/workspace/etf-scripts/`（持久化），解决沙箱清理导致数据丢失
- **GitHub集成**：代码+数据托管在 GitHub，每日自动 clone → 运行 → push 数据回传
- **经验库排序**：修复显示最早20条 → 改为最新20条在前
- **推荐/预警分离**：看好板块（P(涨)最高3个）+ 看空预警（P(跌)最高3个），数据来源切换为Logit概率排序
- **建议文字**：每个ETF给出操作建议（谨慎参与/重点关注/建议回避等）
- **四大报简化**：去掉总结文本，直接4个报纸卡片
- **公式排版**：模型公式区改为自上而下Word式排列
- **规则模型修复**：补全 `report_date`、`hs300_return`、`avg_profit`、`avg_loss` 字段
- **推荐数量**：规则模型从2只改为3只ETF

## 文件结构
```
fucketf/
├── daily_pipeline.py          # 每日流水线入口
├── fetch_etf_data.py          # ETF数据获取（腾讯API·前复权）
├── scrape_newspapers.py       # 四大报抓取（同花顺）
├── etf_model_run.py           # 规则模型
├── econometric_model.py       # 计量模型（Logit+OLS+Lasso）
├── generate_dashboard.py      # 看板生成器
├── requirements.txt           # Python依赖
├── data/                      # 数据文件
│   ├── etf_history.json       # ETF日K数据
│   ├── newspapers.json        # 四大报标题
│   ├── model_results.json     # 规则模型输出
│   └── econometric_results.json # 计量模型输出
└── _shared/                   # ECharts库 + 字体
```
