# fucketf

ETF 预测模型 — 规则模型 + 计量交叉验证，每日自动迭代。

## 数据源
- ETF 行情：腾讯财经 API（前复权）
- 四大报：同花顺 https://stock.10jqka.com.cn/bktt_list/

## 模型
- 规则模型：报纸情绪(3x) + 板块动量 + 量比 + 均值回归 + 经验自适应
- 计量模型：Logit + OLS + Lasso 变量选择 + 时序交叉验证

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
