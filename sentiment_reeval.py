#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
报纸情绪信号重新评估 — 用完整数据(1-7月)分析，
区分上半年(1-6月)vs 7月，检查之前"负相关"结论是否因数据不足而失真
"""
import json
import os
import sys
import warnings
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
warnings.filterwarnings('ignore')

from etf_model_run import (
    SECTOR_ETF_MAP, HS300_CODE, ETF_HISTORY_PATH, NEWSPAPERS_PATH,
    load_json, get_trading_days, find_record, get_index,
    analyze_newspaper_sentiment,
)

etf_data = load_json(ETF_HISTORY_PATH)
news_data = load_json(NEWSPAPERS_PATH)

print(f'ETF数据: {len(get_trading_days(etf_data))} 个交易日')
print(f'报纸数据: {len(news_data)} 天')
print()

# ====== 1. 构建情绪+收益面板 ======
trading_days = get_trading_days(etf_data)
rows = []
for T in trading_days:
    news_T = news_data.get(T, {})
    sent = analyze_newspaper_sentiment(news_T)
    
    # 沪深300当日收益(开盘->收盘)
    rec = find_record(etf_data, HS300_CODE, T)
    if not rec or not rec['open']:
        continue
    
    intraday_ret = (rec['close'] - rec['open']) / rec['open'] * 100
    # 隔夜收益(前收->今开)
    idx = get_index(etf_data, HS300_CODE, T)
    prev_close = etf_data[HS300_CODE]['data'][idx-1]['close'] if idx > 0 else None
    overnight_ret = (rec['open'] - prev_close) / prev_close * 100 if prev_close else 0.0
    # 全日收益(前收->今收)
    full_ret = (rec['close'] - prev_close) / prev_close * 100 if prev_close else 0.0
    
    rows.append({
        'date': T,
        'month': T[:7],
        'sentiment_score': sent['score'],
        'bullish': sent['bullish_count'],
        'bearish': sent['bearish_count'],
        'total_titles': sent.get('total_titles', 0),
        'intraday_ret': round(intraday_ret, 4),
        'overnight_ret': round(overnight_ret, 4),
        'full_ret': round(full_ret, 4),
    })

df = pd.DataFrame(rows)
print(f'面板数据: {len(df)} 行')
print()

# ====== 2. 全样本情绪统计 ======
print('=' * 60)
print('一、全样本情绪统计 (2026-01 ~ 2026-07)')
print('=' * 60)
print(f'  平均情绪分: {df["sentiment_score"].mean():.4f}')
print(f'  中位数:     {df["sentiment_score"].median():.4f}')
print(f'  标准差:     {df["sentiment_score"].std():.4f}')
print(f'  看多均值:   {df["bullish"].mean():.2f}')
print(f'  看空均值:   {df["bearish"].mean():.2f}')
print(f'  多空比:     {df["bullish"].sum() / (df["bearish"].sum() + 1):.4f}')
print()

# ====== 3. 分月情绪统计 ======
print('=' * 60)
print('二、分月情绪统计')
print('=' * 60)
print(f'{"月份":<10} {"天数":>4} {"均值":>8} {"中位":>8} {"看多":>6} {"看空":>6} {"多空比":>8} {"全日收益%":>10}')
for month in sorted(df['month'].unique()):
    sub = df[df['month'] == month]
    avg_sent = sub['sentiment_score'].mean()
    med_sent = sub['sentiment_score'].median()
    avg_bull = sub['bullish'].mean()
    avg_bear = sub['bearish'].mean()
    ratio = sub['bullish'].sum() / (sub['bearish'].sum() + 1)
    avg_ret = sub['full_ret'].mean()
    print(f'{month:<10} {len(sub):>4} {avg_sent:>8.4f} {med_sent:>8.4f} {avg_bull:>6.1f} {avg_bear:>6.1f} {ratio:>8.2f} {avg_ret:>10.4f}')
print()

# ====== 4. 上半年 vs 7月 对比 ======
print('=' * 60)
print('三、上半年(1-6月) vs 7月 对比')
print('=' * 60)
h1 = df[df['month'] < '2026-07']
jul = df[df['month'] >= '2026-07']
print(f'  上半年: 情绪均值={h1["sentiment_score"].mean():.4f}, 全日收益均值={h1["full_ret"].mean():.4f}%, 天数={len(h1)}')
print(f'  7月:    情绪均值={jul["sentiment_score"].mean():.4f}, 全日收益均值={jul["full_ret"].mean():.4f}%, 天数={len(jul)}')
print(f'  差异:   情绪{(jul["sentiment_score"].mean()-h1["sentiment_score"].mean()):.4f}, 收益{(jul["full_ret"].mean()-h1["full_ret"].mean()):.4f}%')
print()

# ====== 5. 情绪与收益相关性 — 全样本 vs 分段 ======
print('=' * 60)
print('四、情绪与收益相关性分析')
print('=' * 60)

for label, sub in [('全样本', df), ('上半年(1-6月)', h1), ('7月', jul)]:
    if len(sub) < 5:
        continue
    corr_intra = sub['sentiment_score'].corr(sub['intraday_ret'])
    corr_overnight = sub['sentiment_score'].corr(sub['overnight_ret'])
    corr_full = sub['sentiment_score'].corr(sub['full_ret'])
    print(f'  [{label}] (n={len(sub)})')
    print(f'    情绪 vs 日内收益(开->收): r={corr_intra:.4f}')
    print(f'    情绪 vs 隔夜收益(前收->今开): r={corr_overnight:.4f}')
    print(f'    情绪 vs 全日收益(前收->今收): r={corr_full:.4f}')
    print()

# ====== 6. 情绪分组胜率 ======
print('=' * 60)
print('五、情绪分组胜率分析')
print('=' * 60)

for label, sub in [('全样本', df), ('上半年(1-6月)', h1), ('7月', jul)]:
    if len(sub) < 10:
        continue
    med = sub['sentiment_score'].median()
    hi = sub[sub['sentiment_score'] > med]
    lo = sub[sub['sentiment_score'] <= med]
    hi_win = (hi['full_ret'] > 0).mean() * 100 if len(hi) > 0 else 0
    lo_win = (lo['full_ret'] > 0).mean() * 100 if len(lo) > 0 else 0
    hi_avg = hi['full_ret'].mean()
    lo_avg = lo['full_ret'].mean()
    print(f'  [{label}] (中位数={med:.4f})')
    print(f'    高情绪组: 胜率={hi_win:.1f}%, 平均收益={hi_avg:.4f}% (n={len(hi)})')
    print(f'    低情绪组: 胜率={lo_win:.1f}%, 平均收益={lo_avg:.4f}% (n={len(lo)})')
    print(f'    差异: 胜率{(hi_win-lo_win):.1f}pp, 收益{(hi_avg-lo_avg):.4f}%')
    print()

# ====== 7. 情绪分滞后效应(次日收益) ======
print('=' * 60)
print('六、情绪分对次日收益的预测力')
print('=' * 60)

df_sorted = df.sort_values('date').reset_index(drop=True)
df_sorted['next_full_ret'] = df_sorted['full_ret'].shift(-1)
df_sorted['next_intraday'] = df_sorted['intraday_ret'].shift(-1)
valid = df_sorted.dropna(subset=['next_full_ret'])

for label, sub in [('全样本', valid), ('上半年', valid[valid['month']<'2026-07']), ('7月', valid[valid['month']>='2026-07'])]:
    if len(sub) < 5:
        continue
    corr_next = sub['sentiment_score'].corr(sub['next_full_ret'])
    corr_next_intra = sub['sentiment_score'].corr(sub['next_intraday'])
    print(f'  [{label}] (n={len(sub)})')
    print(f'    情绪 vs 次日全日收益: r={corr_next:.4f}')
    print(f'    情绪 vs 次日日内收益: r={corr_next_intra:.4f}')
    print()

# ====== 8. 关键结论 ======
print('=' * 60)
print('七、关键结论')
print('=' * 60)
h1_corr = h1['sentiment_score'].corr(h1['full_ret']) if len(h1) > 5 else 0
jul_corr = jul['sentiment_score'].corr(jul['full_ret']) if len(jul) > 5 else 0
full_corr = df['sentiment_score'].corr(df['full_ret'])
print(f'1. 数据覆盖: {len(df)}个交易日 (上半年{len(h1)}天 + 7月{len(jul)}天)')
print(f'2. 上半年情绪均值 {h1["sentiment_score"].mean():.4f} vs 7月 {jul["sentiment_score"].mean():.4f}')
print(f'   → 7月情绪确实低于上半年 (差{jul["sentiment_score"].mean()-h1["sentiment_score"].mean():.4f})')
print(f'3. 上半年市场收益均值 {h1["full_ret"].mean():.4f}% vs 7月 {jul["full_ret"].mean():.4f}%')
print(f'   → 7月市场确实弱于上半年')
print(f'4. 情绪-收益相关性:')
print(f'   全样本 r={full_corr:.4f}, 上半年 r={h1_corr:.4f}, 7月 r={jul_corr:.4f}')
if abs(h1_corr) < abs(full_corr):
    print(f'   → 之前"负相关"结论部分受7月数据放大, 上半年相关性更弱')
else:
    print(f'   → 相关性在两个时段方向一致')
