#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""情绪信号全面评估: 权重占比 / 统计有效性 / 数据覆盖 / 信号质量"""
import json, os, sys
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from etf_model_run import (
    SECTOR_ETF_MAP, HS300_CODE, ETF_HISTORY_PATH, NEWSPAPERS_PATH,
    load_json, get_trading_days, find_record, get_index, get_prev_date,
    analyze_newspaper_sentiment, BULLISH_KEYWORDS, BEARISH_KEYWORDS,
)

etf_data = load_json(ETF_HISTORY_PATH)
news_data = load_json(NEWSPAPERS_PATH)
trading_days = get_trading_days(etf_data)

print('='*90)
print('情绪信号全面评估')
print('='*90)

# ============ 1. 规则模型中情绪权重占比 ============
print('\n【1】规则模型中情绪信号权重占比')
print('-'*60)
# 总分 = 3*sent + 1*mom + 1*vol + 1*mr + 1*exp
# 最大可能: sentiment[-1,1]*3=3, mom[-1,1]=1, vol[-1,1]=1, mr[-1,1]=1, exp[-1,1]=1
# 但实际情绪score范围0~0.875, 非板块时*0.3
weights = {'sentiment(3x)':3, 'momentum(1x)':1, 'volume(1x)':1, 'meanrev(1x)':1, 'experience(1x)':1}
total_w = sum(weights.values())
print(f'  理论最大权重: 情绪={weights["sentiment(3x)"]}/{total_w} = {weights["sentiment(3x)"]/total_w*100:.0f}%')
print(f'  其他四信号合计: {total_w-weights["sentiment(3x)"]}/{total_w} = {(total_w-weights["sentiment(3x)"])/total_w*100:.0f}%')

# 实际score分布
all_scores = []
for date in news_data:
    sent = analyze_newspaper_sentiment(news_data[date])
    all_scores.append(sent['score'])
all_scores = np.array(all_scores)
print(f'\n  情绪score实际分布(有报纸的{len(all_scores)}天):')
print(f'    均值={np.mean(all_scores):.4f} 中位数={np.median(all_scores):.4f}')
print(f'    min={np.min(all_scores):.4f} max={np.max(all_scores):.4f} std={np.std(all_scores):.4f}')
print(f'    >0(偏多)占比={np.mean(all_scores>0)*100:.1f}%  =0(中性)占比={np.mean(all_scores==0)*100:.1f}%')

# 实际贡献: 情绪信号实际值范围 vs 其他信号
print(f'\n  情绪信号实际值范围: [{np.min(all_scores)*3:.3f}, {np.max(all_scores)*3:.3f}] (score*3)')
print(f'  其他信号实际值范围: [-1, 1] (各1x)')
print(f'  => 情绪实际最大贡献: {np.max(all_scores)*3:.3f}, 占总分的{np.max(all_scores)*3/(np.max(all_scores)*3+4)*100:.1f}%')

# ============ 2. 数据覆盖率 ============
print('\n【2】四大报数据覆盖率')
print('-'*60)
news_dates = set(news_data.keys())
etf_dates = set(trading_days)
overlap = news_dates & etf_dates
print(f'  ETF交易日总数: {len(etf_dates)}')
print(f'  有四大报的天数: {len(news_dates)}')
print(f'  覆盖率: {len(overlap)}/{len(etf_dates)} = {len(overlap)/len(etf_dates)*100:.1f}%')
print(f'  缺失天数: {len(etf_dates)-len(overlap)}天 ({(len(etf_dates)-len(overlap))/len(etf_dates)*100:.1f}%)')
print(f'  报纸日期范围: {min(news_dates)} ~ {max(news_dates)}')
print(f'  ETF日期范围: {min(etf_dates)} ~ {max(etf_dates)}')

# 每报纸每天标题数
print(f'\n  各报每日标题数:')
for paper in ['中国证券报','上海证券报','证券时报','证券日报']:
    counts = [len(news_data[d].get(paper,[])) for d in news_data if paper in news_data[d]]
    if counts:
        print(f'    {paper}: 均值={np.mean(counts):.1f} 范围=[{min(counts)},{max(counts)}]')

# ============ 3. 情绪信号统计有效性 ============
print('\n【3】情绪信号统计有效性 (计量模型结果)')
print('-'*60)
import statsmodels.api as sm
from sklearn.linear_model import LogisticRegression

# 构建面板
rows = []
for i in range(2, len(trading_days)):
    T, Tm1, Tm2 = trading_days[i], trading_days[i-1], trading_days[i-2]
    news_T = news_data.get(T, {})
    sent = analyze_newspaper_sentiment(news_T)
    for code, info in SECTOR_ETF_MAP.items():
        rT = find_record(etf_data, code, T); r1 = find_record(etf_data, code, Tm1); r2 = find_record(etf_data, code, Tm2)
        if not (rT and r1 and r2 and rT['open'] and r1['open'] and r2['close']): continue
        today_return = (rT['close']-rT['open'])/rT['open']*100
        today_direction = 1 if today_return>0 else 0
        rows.append({
            'date':T,'code':code,
            'sentiment_score':float(sent['score']),
            'bullish_count':int(sent['bullish_count']),
            'bearish_count':int(sent['bearish_count']),
            'today_return':today_return,'today_direction':today_direction,
        })
df = pd.DataFrame(rows)

# 单变量Logit: sentiment_score -> today_direction
X = df[['sentiment_score']].values.astype(float)
y = df['today_direction'].values
Xc = sm.add_constant(X)
try:
    res = sm.Logit(y, Xc).fit(disp=False)
    print(f'  情绪score单变量Logit: coef={res.params[1]:.4f} p={res.pvalues[1]:.4f} 伪R²={res.prsquared:.6f}')
except Exception as e:
    print(f'  情绪score单变量Logit拟合失败: {e}')

# 情绪分与收益的相关性
corr = df['sentiment_score'].corr(df['today_return'])
print(f'  情绪score与当日收益相关系数: {corr:.4f} (接近0=无相关)')

# 分组: 高情绪 vs 低情绪 的胜率
high = df[df['sentiment_score'] > df['sentiment_score'].median()]
low = df[df['sentiment_score'] <= df['sentiment_score'].median()]
print(f'  高情绪组胜率: {high["today_direction"].mean()*100:.1f}% (n={len(high)})')
print(f'  低情绪组胜率: {low["today_direction"].mean()*100:.1f}% (n={len(low)})')
print(f'  差异: {(high["today_direction"].mean()-low["today_direction"].mean())*100:.1f}pp (正=情绪有效)')

# ============ 4. 关键词匹配质量 ============
print('\n【4】关键词匹配质量分析')
print('-'*60)
total_titles = 0
matched_bull = matched_bear = matched_sector = 0
for date in news_data:
    for paper, titles in news_data[date].items():
        for title in titles:
            total_titles += 1
            if any(kw in title for kw in BULLISH_KEYWORDS): matched_bull += 1
            if any(kw in title for kw in BEARISH_KEYWORDS): matched_bear += 1
            for code, info in SECTOR_ETF_MAP.items():
                if any(kw in title for kw in info['keywords']):
                    matched_sector += 1
                    break
print(f'  总标题数: {total_titles}')
print(f'  匹配看涨词: {matched_bull} ({matched_bull/total_titles*100:.1f}%)')
print(f'  匹配看跌词: {matched_bear} ({matched_bear/total_titles*100:.1f}%)')
print(f'  匹配板块词: {matched_sector} ({matched_sector/total_titles*100:.1f}%)')
print(f'  未匹配任何: {total_titles-matched_bull-matched_bear} ({(total_titles-matched_bull-matched_bear)/total_titles*100:.1f}%)')

# 看涨/看跌词命中频率top
bull_hits = {kw:0 for kw in BULLISH_KEYWORDS}
bear_hits = {kw:0 for kw in BEARISH_KEYWORDS}
for date in news_data:
    for paper, titles in news_data[date].items():
        for title in titles:
            for kw in BULLISH_KEYWORDS:
                if kw in title: bull_hits[kw]+=1
            for kw in BEARISH_KEYWORDS:
                if kw in title: bear_hits[kw]+=1
print(f'\n  看涨词命中Top5:')
for kw,c in sorted(bull_hits.items(),key=lambda x:-x[1])[:5]:
    print(f'    "{kw}": {c}次')
print(f'  看跌词命中Top5:')
for kw,c in sorted(bear_hits.items(),key=lambda x:-x[1])[:5]:
    print(f'    "{kw}": {c}次')

# ============ 5. 情绪在有无报纸日的表现差异 ============
print('\n【5】有报纸日 vs 无报纸日 的模型表现')
print('-'*60)
with_news = df[df['date'].isin(news_dates)]
without_news = df[~df['date'].isin(news_dates)]
print(f'  有报纸日: {with_news["date"].nunique()}天, 胜率={with_news["today_direction"].mean()*100:.1f}%, 均收益={with_news["today_return"].mean():.4f}%')
print(f'  无报纸日: {without_news["date"].nunique()}天, 胜率={without_news["today_direction"].mean()*100:.1f}%, 均收益={without_news["today_return"].mean():.4f}%')
print(f'  (差异小说明报纸情绪对涨跌无区分度)')

print('\n'+'='*90)
print('结论见下方分析')
print('='*90)
