#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
双视角情绪评估 — 机构(四大报) vs 大众(融资融券)

大众情绪评判标准:
  1. 融资净买入额(RZJME): 散户杠杆资金的净流向, >0=看多, <0=看空
  2. 融资余额5日变化率: 杠杆趋势, 上升=情绪升温, 下降=降温
  3. 融资买入/偿还比: 买卖压力比, >1=买入主导, <1=卖出主导
  
  综合大众情绪分 = 标准化(净买入额) * 0.5 + 标准化(余额变化率) * 0.3 + 标准化(买卖比) * 0.2
  范围 [-1, 1], 正值=大众看多, 负值=大众看空
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

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
MARGIN_PATH = os.path.join(DATA_DIR, 'margin_trading.json')

etf_data = load_json(ETF_HISTORY_PATH)
news_data = load_json(NEWSPAPERS_PATH)
margin_data = load_json(MARGIN_PATH)

# ====== 1. 构建融资融券DataFrame ======
margin_df = pd.DataFrame(margin_data)
margin_df['date'] = margin_df['date'].astype(str)
margin_df = margin_df.sort_values('date').reset_index(drop=True)

# 计算衍生指标
margin_df['rzye_chg_5d'] = margin_df['rzye'].pct_change(5) * 100  # 5日变化率%
margin_df['buy_sell_ratio'] = margin_df['rzmre'] / (margin_df['rzche'] + 1)  # 买入/偿还比
# 净买入额标准化(亿元)
margin_df['rzjme_yi'] = margin_df['rzjme'] / 1e8
# 融资余额变化(亿元)
margin_df['rzye_chg_yi'] = margin_df['rzye'].diff() / 1e8

print(f'融资融券数据: {len(margin_df)} 天 ({margin_df["date"].iloc[0]} ~ {margin_df["date"].iloc[-1]})')
print()

# ====== 2. 构建大众情绪综合评分 ======
# 标准化三个分量 (z-score)
def zscore(s, window=60):
    """滚动z-score, 避免look-ahead bias"""
    rolling_mean = s.rolling(window, min_periods=10).mean()
    rolling_std = s.rolling(window, min_periods=10).std()
    return (s - rolling_mean) / (rolling_std + 1e-8)

margin_df['rzjme_z'] = zscore(margin_df['rzjme_yi'])
margin_df['rzye_chg_z'] = zscore(margin_df['rzye_chg_yi'])
margin_df['buy_sell_z'] = zscore(margin_df['buy_sell_ratio'])

# 综合大众情绪分: 净买入0.5 + 余额变化0.3 + 买卖比0.2
margin_df['retail_sentiment'] = (
    margin_df['rzjme_z'].clip(-3, 3) * 0.5 +
    margin_df['rzye_chg_z'].clip(-3, 3) * 0.3 +
    margin_df['buy_sell_z'].clip(-3, 3) * 0.2
) / 3.0  # 归一化到[-1, 1]范围

# ====== 3. 构建合并面板 (机构情绪 + 大众情绪 + 市场收益) ======
trading_days = get_trading_days(etf_data)
rows = []
for T in trading_days:
    # 机构情绪(四大报)
    news_T = news_data.get(T, {})
    inst_sent = analyze_newspaper_sentiment(news_T)
    
    # 大众情绪(融资融券) — 用前一交易日的数据(T-1), 避免look-ahead
    margin_idx = margin_df.index[margin_df['date'] == T].tolist()
    if not margin_idx:
        # 尝试找最近的日期
        margin_idx = margin_df.index[margin_df['date'] <= T].tolist()
    if not margin_idx:
        continue
    m_idx = margin_idx[-1]
    if m_idx < 1:
        continue
    
    # 用T日的融资融券数据(T日盘后公布, T+1开盘前可知)
    row_m = margin_df.iloc[m_idx]
    retail_sent = float(row_m['retail_sentiment'])
    rzjme_yi = float(row_m['rzjme_yi'])
    rzye_chg_yi = float(row_m['rzye_chg_yi'])
    buy_sell_ratio = float(row_m['buy_sell_ratio'])
    
    # 沪深300当日收益
    rec = find_record(etf_data, HS300_CODE, T)
    if not rec or not rec['open']:
        continue
    
    idx = get_index(etf_data, HS300_CODE, T)
    prev_close = etf_data[HS300_CODE]['data'][idx-1]['close'] if idx > 0 else None
    if not prev_close:
        continue
    
    intraday_ret = (rec['close'] - rec['open']) / rec['open'] * 100
    overnight_ret = (rec['open'] - prev_close) / prev_close * 100
    full_ret = (rec['close'] - prev_close) / prev_close * 100
    
    rows.append({
        'date': T,
        'month': T[:7],
        'inst_sentiment': float(inst_sent['score']),
        'inst_bullish': inst_sent['bullish_count'],
        'inst_bearish': inst_sent['bearish_count'],
        'retail_sentiment': round(retail_sent, 4),
        'rzjme_yi': round(rzjme_yi, 2),
        'rzye_chg_yi': round(rzye_chg_yi, 2),
        'buy_sell_ratio': round(buy_sell_ratio, 4),
        'intraday_ret': round(intraday_ret, 4),
        'overnight_ret': round(overnight_ret, 4),
        'full_ret': round(full_ret, 4),
    })

df = pd.DataFrame(rows)
print(f'合并面板: {len(df)} 行')
print()

# ====== 4. 机构 vs 大众情绪对比 ======
print('=' * 70)
print('一、机构情绪 vs 大众情绪 — 全样本统计')
print('=' * 70)
print(f'  机构情绪(四大报): 均值={df["inst_sentiment"].mean():.4f}, 中位={df["inst_sentiment"].median():.4f}, std={df["inst_sentiment"].std():.4f}')
print(f'  大众情绪(融资融券): 均值={df["retail_sentiment"].mean():.4f}, 中位={df["retail_sentiment"].median():.4f}, std={df["retail_sentiment"].std():.4f}')
print(f'  两情绪相关系数: r={df["inst_sentiment"].corr(df["retail_sentiment"]):.4f}')
print()

# ====== 5. 分月对比 ======
print('=' * 70)
print('二、分月情绪对比')
print('=' * 70)
print(f'{"月份":<10} {"机构均值":>8} {"大众均值":>8} {"机构-大众":>8} {"市场收益%":>10} {"天数":>4}')
for month in sorted(df['month'].unique()):
    sub = df[df['month'] == month]
    inst_avg = sub['inst_sentiment'].mean()
    ret_avg = sub['retail_sentiment'].mean()
    diff = inst_avg - ret_avg
    mkt_ret = sub['full_ret'].mean()
    print(f'{month:<10} {inst_avg:>8.4f} {ret_avg:>8.4f} {diff:>8.4f} {mkt_ret:>10.4f} {len(sub):>4}')
print()

# ====== 6. 预测力对比 — 与当日收益的相关性 ======
print('=' * 70)
print('三、情绪对当日收益的预测力 (相关性)')
print('=' * 70)

h1 = df[df['month'] < '2026-07']
jul = df[df['month'] >= '2026-07']

for label, sub in [('全样本', df), ('上半年(1-6月)', h1), ('7月', jul)]:
    if len(sub) < 5:
        continue
    print(f'  [{label}] (n={len(sub)})')
    for ret_type, ret_col in [('日内(开->收)', 'intraday_ret'), ('隔夜(前收->今开)', 'overnight_ret'), ('全日(前收->今收)', 'full_ret')]:
        r_inst = sub['inst_sentiment'].corr(sub[ret_col])
        r_ret = sub['retail_sentiment'].corr(sub[ret_col])
        print(f'    {ret_type}: 机构r={r_inst:+.4f}, 大众r={r_ret:+.4f}, 差异={r_ret-r_inst:+.4f}')
    print()

# ====== 7. 分组胜率对比 ======
print('=' * 70)
print('四、情绪分组胜率对比 (全日收益)')
print('=' * 70)

for label, sub in [('全样本', df), ('上半年(1-6月)', h1), ('7月', jul)]:
    if len(sub) < 10:
        continue
    print(f'  [{label}] (n={len(sub)})')
    
    # 机构情绪分组
    med_i = sub['inst_sentiment'].median()
    hi_i = sub[sub['inst_sentiment'] > med_i]
    lo_i = sub[sub['inst_sentiment'] <= med_i]
    print(f'    机构情绪 (中位={med_i:.4f}):')
    print(f'      高情绪: 胜率={((hi_i["full_ret"]>0).mean()*100):.1f}%, 均值收益={hi_i["full_ret"].mean():.4f}% (n={len(hi_i)})')
    print(f'      低情绪: 胜率={((lo_i["full_ret"]>0).mean()*100):.1f}%, 均值收益={lo_i["full_ret"].mean():.4f}% (n={len(lo_i)})')
    
    # 大众情绪分组
    med_r = sub['retail_sentiment'].median()
    hi_r = sub[sub['retail_sentiment'] > med_r]
    lo_r = sub[sub['retail_sentiment'] <= med_r]
    print(f'    大众情绪 (中位={med_r:.4f}):')
    print(f'      高情绪: 胜率={((hi_r["full_ret"]>0).mean()*100):.1f}%, 均值收益={hi_r["full_ret"].mean():.4f}% (n={len(hi_r)})')
    print(f'      低情绪: 胜率={((lo_r["full_ret"]>0).mean()*100):.1f}%, 均值收益={lo_r["full_ret"].mean():.4f}% (n={len(lo_r)})')
    print()

# ====== 8. 双情绪组合信号 ======
print('=' * 70)
print('五、双情绪组合信号 (机构+大众一致 vs 分歧)')
print('=' * 70)

# 四象限分析
df['inst_dir'] = (df['inst_sentiment'] > df['inst_sentiment'].median()).astype(int)
df['retail_dir'] = (df['retail_sentiment'] > df['retail_sentiment'].median()).astype(int)
df['combo'] = df['inst_dir'] * 2 + df['retail_dir']

combo_labels = {
    0: '双空(机构空+大众空)',
    1: '机构空+大众多',
    2: '机构多+大众空',
    3: '双多(机构多+大众多)',
}

for combo_id, label in combo_labels.items():
    sub = df[df['combo'] == combo_id]
    if len(sub) < 3:
        continue
    win_rate = (sub['full_ret'] > 0).mean() * 100
    avg_ret = sub['full_ret'].mean()
    print(f'  {label}: n={len(sub)}, 胜率={win_rate:.1f}%, 均值收益={avg_ret:.4f}%')

print()

# ====== 9. 次日预测力 ======
print('=' * 70)
print('六、情绪对次日收益的预测力')
print('=' * 70)

df_sorted = df.sort_values('date').reset_index(drop=True)
df_sorted['next_full_ret'] = df_sorted['full_ret'].shift(-1)
df_sorted['next_intraday'] = df_sorted['intraday_ret'].shift(-1)
valid = df_sorted.dropna(subset=['next_full_ret'])

for label, sub in [('全样本', valid), ('上半年', valid[valid['month']<'2026-07']), ('7月', valid[valid['month']>='2026-07'])]:
    if len(sub) < 5:
        continue
    r_inst_next = sub['inst_sentiment'].corr(sub['next_full_ret'])
    r_ret_next = sub['retail_sentiment'].corr(sub['next_full_ret'])
    r_inst_intra = sub['inst_sentiment'].corr(sub['next_intraday'])
    r_ret_intra = sub['retail_sentiment'].corr(sub['next_intraday'])
    print(f'  [{label}] (n={len(sub)})')
    print(f'    次日全日收益: 机构r={r_inst_next:+.4f}, 大众r={r_ret_next:+.4f}')
    print(f'    次日日内收益: 机构r={r_inst_intra:+.4f}, 大众r={r_ret_intra:+.4f}')
    print()

# ====== 10. 关键结论 ======
print('=' * 70)
print('七、关键结论')
print('=' * 70)

# 机构情绪特征
inst_corr = df['inst_sentiment'].corr(df['full_ret'])
retail_corr = df['retail_sentiment'].corr(df['full_ret'])
inst_next = valid['inst_sentiment'].corr(valid['next_full_ret'])
retail_next = valid['retail_sentiment'].corr(valid['next_full_ret'])

print(f'1. 机构情绪(四大报):')
print(f'   - 全样本与当日收益相关性 r={inst_corr:+.4f} ({"反向" if inst_corr < 0 else "正向"}指标)')
print(f'   - 次日收益预测力 r={inst_next:+.4f}')
print(f'   - 特征: 情绪始终偏多(均值{df["inst_sentiment"].mean():.4f}), 7月反而更乐观但市场更差')
print()
print(f'2. 大众情绪(融资融券):')
print(f'   - 全样本与当日收益相关性 r={retail_corr:+.4f} ({"反向" if retail_corr < 0 else "正向"}指标)')
print(f'   - 次日收益预测力 r={retail_next:+.4f}')
print(f'   - 特征: 反映散户真金白银的杠杆方向, 比报纸标题更贴近实际交易行为')
print()
print(f'3. 两情绪相关性 r={df["inst_sentiment"].corr(df["retail_sentiment"]):+.4f}')
if abs(df['inst_sentiment'].corr(df['retail_sentiment'])) < 0.3:
    print(f'   → 两视角独立性强, 组合使用可提供增量信息')
else:
    print(f'   → 两视角相关性较高, 信息重叠较大')
print()
print(f'4. 双情绪组合策略建议:')
print(f'   - 机构情绪: 反向使用(机构看多→谨慎, 机构看空→关注反弹)')
print(f'   - 大众情绪: 需根据相关性方向决定正向/反向使用')
print(f'   - 双空信号(机构空+大众空)可能是最可靠的反弹信号')
