#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF规则模型 — 基于四大报情绪 + 板块动量/量比/均值回归/经验自适应的多信号决策

关键修复 look-ahead bias:
  决策使用【前一日】板块表现(动量/量比/均值回归) + 【当日】四大报(情绪)，
  收益以【当日】开盘->收盘的日内收益实现(开盘买入、收盘卖出)，
  避免使用决策时尚未可知的当日收盘数据做信号。

输出: data/model_results.json
"""
import json
import os
from datetime import datetime, timedelta
from math import sqrt
from etf_universe import SECTOR_ETF_MAP

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
ETF_HISTORY_PATH = os.path.join(DATA_DIR, 'etf_history.json')
NEWSPAPERS_PATH = os.path.join(DATA_DIR, 'newspapers.json')
MARGIN_PATH = os.path.join(DATA_DIR, 'margin_trading.json')
OUTPUT_PATH = os.path.join(DATA_DIR, 'model_results.json')
EXTERNAL_NEWS_PATH = os.path.join(DATA_DIR, 'external_news.json')
SHARES_PATH = os.path.join(DATA_DIR, 'etf_shares.json')

EXTERNAL_BULLISH = ['支持', '利好', '增长', '回升', '扩张', '放宽', '加快', '突破', '改善', '创新高', '超预期']
# “监管/风险/警示”在官方标题中常是中性语境，不能直接视为利空。
EXTERNAL_BEARISH = ['下滑', '收紧', '处罚', '下跌', '下降', '放缓', '违约', '亏损', '削减', '减少']

BULLISH_KEYWORDS = ['看好', '利好', '上涨', '增长', '突破', '机遇', '提升', '回升', '修复', '牛市',
                    '反弹', '强势', '提振', '催化', '加速', '爆发', '高增长', '超预期', '增持', '买入',
                    '布局', '价值', '信心', '乐观', '繁荣', '需求旺盛']
BEARISH_KEYWORDS = ['下跌', '风险', '下降', '利空', '下滑', '收紧', '警惕', '回调', '熊市', '压力',
                    '减持', '卖出', '规避', '萎缩', '亏损', '违约', '爆雷', '退市', '监管', '处罚',
                    '下挫', '暴跌', '恐慌', '担忧', '不确定性', '收缩']

HS300_CODE = '510300'
INITIAL_CAPITAL = 1_000_000.0
COMMISSION_RATE = 0.00005      # 万0.5 (买卖各一次)
MAX_EXPERIENCES = 200
SCORE_FULL = 1.2               # 满仓评分阈值，必须高于买入阈值

def _date_shift(date_str, days):
    return (datetime.strptime(date_str, '%Y-%m-%d').date() + timedelta(days=days)).isoformat()

# ====== Walk-Forward 优化参数 (胜率 53% → 70.5%) ======
SENTIMENT_LAG_COEF = -1.0      # 情绪信号方向反转 (机构看多为反向指标)
WEIGHT_SENTIMENT = 1           # 情绪权重 3→1
WEIGHT_MOMENTUM = 1.5          # 动量权重 1→1.5
WEIGHT_RETAIL = 2.0            # 大众情绪权重 (新增)
BUY_THRESHOLD = 0.35           # 新评分已归一化到约[-2,2]
HOLDING_PERIOD = 3             # 持仓天数 1→3
MOMENTUM_WINDOW = 10           # 动量窗口 5→10


# ----------------------------- 基础工具 -----------------------------
def load_json(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)


def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def get_trading_days(etf_data):
    days = set()
    for info in etf_data.values():
        for rec in info['data']:
            days.add(rec['date'])
    return sorted(days)


def find_record(etf_data, code, date):
    for rec in etf_data.get(code, {}).get('data', []):
        if rec['date'] == date:
            return rec
    return None


def get_index(etf_data, code, date):
    for i, rec in enumerate(etf_data.get(code, {}).get('data', [])):
        if rec['date'] == date:
            return i
    return -1


def get_prev_date(trading_days, date):
    if date not in trading_days:
        return None
    i = trading_days.index(date)
    return trading_days[i - 1] if i > 0 else None


# ----------------------------- 情绪分析 -----------------------------
def analyze_newspaper_sentiment(newspapers):
    """分析四大报情绪，返回 score/bullish_count/bearish_count/hot_sectors/summary"""
    if not newspapers:
        return {
            'score': 0.0, 'bullish_count': 0, 'bearish_count': 0,
            'hot_sectors': [], 'summary': '当日无四大报数据，情绪中性',
            'total_titles': 0, 'paper_counts': {}
        }

    all_titles = []
    paper_counts = {}
    for paper, titles in newspapers.items():
        paper_counts[paper] = len(titles)
        all_titles.extend(titles)

    bullish_count = 0
    bearish_count = 0
    sector_counts = {info['sector']: 0 for info in SECTOR_ETF_MAP.values()}

    for title in all_titles:
        if any(kw in title for kw in BULLISH_KEYWORDS):
            bullish_count += 1
        if any(kw in title for kw in BEARISH_KEYWORDS):
            bearish_count += 1
        for code, info in SECTOR_ETF_MAP.items():
            for kw in info['keywords']:
                if kw in title:
                    sector_counts[info['sector']] += 1
                    break  # 每个板块每条标题只计一次

    total = bullish_count + bearish_count
    score = round((bullish_count - bearish_count) / (total + 1), 4)
    hot_sectors = [
        {'sector': s, 'count': c}
        for s, c in sorted(sector_counts.items(), key=lambda x: -x[1]) if c > 0
    ]
    top_names = ', '.join(s['sector'] for s in hot_sectors[:3]) or '无'
    summary = (f"四大报共{len(all_titles)}条标题(看多{bullish_count}/看空{bearish_count})，"
               f"情绪分{score}，热点板块: {top_names}")

    return {
        'score': score, 'bullish_count': bullish_count, 'bearish_count': bearish_count,
        'hot_sectors': hot_sectors, 'summary': summary,
        'total_titles': len(all_titles), 'paper_counts': paper_counts
    }


def load_external_news():
    if not os.path.exists(EXTERNAL_NEWS_PATH):
        return []
    try:
        raw = load_json(EXTERNAL_NEWS_PATH)
        return raw.get('items', raw) if isinstance(raw, dict) else raw
    except Exception:
        return []


def analyze_external_sentiment(items, date_str):
    """官方/行业/宏观标题的轻量事件情绪；只使用发布时间不晚于决策日的数据。"""
    usable = []
    for x in items:
        published = x.get('published_at', '')[:10]
        # unknown/列表抓取日不参与时间敏感模型；只使用近14日且不晚于决策日的事件。
        if x.get('date_quality') in (None, 'unknown', 'listing'):
            continue
        if published and date_str >= published >= _date_shift(date_str, -14):
            usable.append(x)
    bullish = bearish = 0
    categories = {}
    sector_scores = {info['sector']: 0.0 for info in SECTOR_ETF_MAP.values()}
    for item in usable:
        title = item.get('title', '')
        b = sum(k in title for k in EXTERNAL_BULLISH)
        s = sum(k in title for k in EXTERNAL_BEARISH)
        bullish += b > 0
        bearish += s > 0
        category = item.get('category', 'other')
        bucket = categories.setdefault(category, {'count': 0, 'bullish': 0, 'bearish': 0})
        bucket['count'] += 1
        bucket['bullish'] += int(b > 0)
        bucket['bearish'] += int(s > 0)
        direction = _clip((b - s) / 2)
        for info in SECTOR_ETF_MAP.values():
            if any(k.lower() in title.lower() for k in info['keywords']):
                sector_scores[info['sector']] += direction
    total = bullish + bearish
    score = (bullish - bearish) / (total + 1) if total else 0.0
    return {'score': round(_clip(score), 4), 'bullish_count': int(bullish),
            'bearish_count': int(bearish), 'count': len(usable),
            'categories': categories, 'sector_scores': sector_scores}


# ----------------------------- 板块表现 -----------------------------
def calculate_sector_performance(etf_data, date):
    """计算指定日期各ETF板块涨跌幅(close vs prev close)，返回 top5/bottom5/hs300"""
    trading_days = get_trading_days(etf_data)
    prev_date = get_prev_date(trading_days, date)
    results = []
    for code, info in SECTOR_ETF_MAP.items():
        rec = find_record(etf_data, code, date)
        prev_rec = find_record(etf_data, code, prev_date) if prev_date else None
        if rec and prev_rec and prev_rec['close']:
            change_pct = round((rec['close'] - prev_rec['close']) / prev_rec['close'] * 100, 4)
        else:
            change_pct = 0.0
        results.append({
            'code': code, 'name': info['name'], 'sector': info['sector'],
            'change_pct': change_pct,
            'close': rec['close'] if rec else None,
            'volume': rec['volume'] if rec else None,
        })
    results.sort(key=lambda x: -x['change_pct'])
    top5 = results[:5]
    bottom5 = list(reversed(results[-5:]))
    hs300 = next((r['change_pct'] for r in results if r['code'] == HS300_CODE), 0.0)
    avg = round(sum(r['change_pct'] for r in results) / len(results), 4) if results else 0.0
    return {
        'date': date, 'prev_date': prev_date,
        'all': results, 'top5': top5, 'bottom5': bottom5,
        'hs300': hs300, 'avg': avg
    }


def compute_volume_ratio(etf_data, code, date, window=5):
    """前日量比 = 当日成交量 / 前 window 日均量"""
    idx = get_index(etf_data, code, date)
    if idx <= 0:
        return 1.0
    rec = etf_data[code]['data'][idx]
    start = max(0, idx - window)
    prev_vols = [etf_data[code]['data'][j]['volume'] for j in range(start, idx)]
    if not prev_vols:
        return 1.0
    avg = sum(prev_vols) / len(prev_vols)
    return round(rec['volume'] / avg, 4) if avg > 0 else 1.0


def compute_mean_reversion(etf_data, code, date, window=5):
    """前 window 日累计收益率(分数)"""
    idx = get_index(etf_data, code, date)
    if idx <= 0:
        return 0.0
    start = max(0, idx - window)
    base = etf_data[code]['data'][start]['close']
    cur = etf_data[code]['data'][idx]['close']
    if not base:
        return 0.0
    return round((cur - base) / base, 4)


def compute_momentum_n(etf_data, code, date, window=10):
    """前 window 日累计涨跌幅(%) — 10日动量信号"""
    idx = get_index(etf_data, code, date)
    if idx < window:
        return 0.0
    base = etf_data[code]['data'][idx - window]['close']
    cur = etf_data[code]['data'][idx]['close']
    if not base:
        return 0.0
    return round((cur - base) / base * 100, 4)


def _clip(value, low=-1.0, high=1.0):
    return max(low, min(high, value))


def _mean(values):
    return sum(values) / len(values) if values else 0.0


def _std(values):
    if len(values) < 2:
        return 0.0
    m = _mean(values)
    return sqrt(sum((v - m) ** 2 for v in values) / len(values))


def _return_between(records, start, end):
    if start < 0 or end >= len(records) or not records[start]['close']:
        return 0.0
    return (records[end]['close'] / records[start]['close'] - 1) * 100


def compute_market_state(etf_data, date):
    """用前一交易日可知数据识别风险状态，控制总仓位而非猜顶部。"""
    records = etf_data.get(HS300_CODE, {}).get('data', [])
    idx = get_index(etf_data, HS300_CODE, date)
    if idx < 20:
        return {'name': 'neutral', 'risk_budget': 0.65, 'breadth': 0.5,
                'momentum_5d': 0.0, 'momentum_20d': 0.0, 'volatility_20d': 0.0}

    mom5 = _return_between(records, idx - 5, idx)
    mom20 = _return_between(records, idx - 20, idx)
    daily = [_return_between(records, j - 1, j) / 100 for j in range(idx - 19, idx + 1)]
    vol20 = _std(daily) * sqrt(252) * 100
    high20 = max(r['close'] for r in records[idx - 19:idx + 1])
    drawdown = (records[idx]['close'] / high20 - 1) * 100 if high20 else 0.0

    breadth_values = []
    for code, info in SECTOR_ETF_MAP.items():
        if info.get('risk_on') != 1:
            continue
        j = get_index(etf_data, code, date)
        recs = etf_data.get(code, {}).get('data', [])
        if j > 0 and recs[j - 1]['close']:
            breadth_values.append(recs[j]['close'] > recs[j - 1]['close'])
    breadth = sum(breadth_values) / len(breadth_values) if breadth_values else 0.5

    # 状态判定使用前一日数据；允许短期回撤发生在中期上升趋势中，避免把正常波动误判成 neutral。
    if (mom20 < -4 or drawdown < -7) and breadth < 0.40:
        name, risk_budget = 'stress', 0.35
    elif (mom20 > 2 and breadth >= 0.55) or (mom20 > 4 and breadth >= 0.45):
        name, risk_budget = 'risk_on', 1.0
    else:
        name = 'neutral'
        risk_budget = 0.85 if mom20 > 2 and breadth >= 0.50 else (0.50 if mom20 < -2 or drawdown < -3 else 0.65)
    return {
        'name': name, 'risk_budget': risk_budget, 'breadth': round(breadth, 4),
        'momentum_5d': round(mom5, 4), 'momentum_20d': round(mom20, 4),
        'volatility_20d': round(vol20, 4), 'drawdown_20d': round(drawdown, 4),
    }


def compute_behavior_signals(etf_data, code, date):
    """从现有OHLCV提取资金冲击代理、拥挤和撤退风险；不冒充真实申赎数据。"""
    records = etf_data.get(code, {}).get('data', [])
    idx = get_index(etf_data, code, date)
    if idx < 20:
        return {k: 0.0 for k in ('momentum', 'acceleration', 'volume_z', 'flow_proxy',
                                         'crowding', 'withdrawal_risk', 'early_entry', 'volatility')}

    mom5 = _return_between(records, idx - 5, idx)
    mom10 = _return_between(records, idx - 10, idx)
    mom20 = _return_between(records, idx - 20, idx)
    prior5 = _return_between(records, idx - 10, idx - 5)
    acceleration = _clip((mom5 - prior5) / 4)

    previous_volumes = [r['volume'] for r in records[max(0, idx - 20):idx]]
    volume_std = _std(previous_volumes)
    volume_z = _clip((records[idx]['volume'] - _mean(previous_volumes)) / volume_std / 3) if volume_std else 0.0

    daily = [_return_between(records, j - 1, j) / 100 for j in range(idx - 19, idx + 1)]
    volatility = _std(daily) * sqrt(252) * 100
    last_return = daily[-1] * 100
    intraday = ((records[idx]['close'] / records[idx]['open'] - 1) * 100
                if records[idx]['open'] else 0.0)

    momentum = _clip(0.45 * mom5 / 4 + 0.35 * mom10 / 6 + 0.20 * mom20 / 10)
    flow_proxy = _clip(0.55 * acceleration + 0.45 * volume_z * (1 if mom5 >= 0 else -1))
    crowding = _clip(0.50 * max(0.0, mom20 / 10)
                     + 0.30 * max(0.0, volume_z)
                     + 0.20 * max(0.0, volatility - 18) / 25, 0.0, 1.0)
    deterioration = _clip((max(0.0, -acceleration)
                           + max(0.0, -last_return / 2)
                           + max(0.0, -intraday / 1.5)) / 3, 0.0, 1.0)
    withdrawal = round(crowding * deterioration, 4)
    early_entry = _clip(0.50 * max(0.0, acceleration)
                        + 0.35 * max(0.0, flow_proxy)
                        + 0.15 * max(0.0, momentum)
                        - 0.35 * crowding, 0.0, 1.0)
    return {
        'momentum': round(momentum, 4), 'acceleration': round(acceleration, 4),
        'volume_z': round(volume_z, 4), 'flow_proxy': round(flow_proxy, 4),
        'crowding': round(crowding, 4), 'withdrawal_risk': withdrawal,
        'early_entry': round(early_entry, 4), 'volatility': round(volatility, 4),
        'mom_5d': round(mom5, 4), 'mom_10d': round(mom10, 4), 'mom_20d': round(mom20, 4),
    }


def compute_news_expectation_gaps(external_signal, behavior):
    """新闻信号相对价格动量、成交量资金代理的预期差。"""
    return {
        'news_price_gap': round(_clip(external_signal - behavior.get('momentum', 0.0)), 4),
        'news_flow_gap': round(_clip(external_signal - behavior.get('flow_proxy', 0.0)), 4),
    }


def compute_news_surprise(newspapers, date, info, window=20):
    """当前板块提及次数相对过去窗口的异常度，区分新信息与重复叙事。"""
    dates = sorted(d for d in newspapers if d <= date)
    counts = []
    for d in dates[-window:]:
        titles = [t for ts in newspapers.get(d, {}).values() for t in ts]
        counts.append(sum(any(k in title for k in info['keywords']) for title in titles))
    if not counts:
        return 0.0
    current = counts[-1]
    history = counts[:-1]
    scale = _std(history)
    return round(_clip((current - _mean(history)) / scale / 3), 4) if scale else float(current > 0)


_margin_cache = None
def load_margin_data():
    global _margin_cache
    if _margin_cache is not None:
        return _margin_cache
    if not os.path.exists(MARGIN_PATH):
        return {}
    raw = load_json(MARGIN_PATH)
    if isinstance(raw, list):
        _margin_cache = {r['date']: r for r in raw}
    else:
        _margin_cache = raw
    return _margin_cache


def compute_retail_sentiment(date_str):
    """
    大众情绪综合评分 — 基于融资融券数据 z-score 加权
    返回: [-1, 1], 正值=大众看多, 负值=大众看空
    时效: T-1日数据在T日开盘前可得
    """
    margin_map = load_margin_data()
    if not margin_map:
        return 0.0

    dates_sorted = sorted(margin_map.keys())
    idx = None
    for i, d in enumerate(dates_sorted):
        if d <= date_str:
            idx = i
        else:
            break
    if idx is None or idx < 10:
        return 0.0

    window = dates_sorted[max(0, idx - 59):idx + 1]
    records = [margin_map[d] for d in window]

    rzjme_list = [r['rzjme'] / 1e8 for r in records]
    rzye_chg_list = [0.0] + [(records[j]['rzye'] - records[j - 1]['rzye']) / 1e8 for j in range(1, len(records))]
    buy_sell_list = [r['rzmre'] / (r['rzche'] + 1) for r in records]

    cur_rzjme = rzjme_list[-1]
    cur_rzye_chg = rzye_chg_list[-1]
    cur_bs_ratio = buy_sell_list[-1]

    def safe_z(val, vals):
        if len(vals) < 5:
            return 0.0
        m = sum(vals) / len(vals)
        var = sum((v - m) ** 2 for v in vals) / len(vals)
        s = var ** 0.5
        if s < 1e-8:
            return 0.0
        return max(-3, min(3, (val - m) / s))

    z_rzjme = safe_z(cur_rzjme, rzjme_list)
    z_rzye = safe_z(cur_rzye_chg, rzye_chg_list)
    z_bs = safe_z(cur_bs_ratio, buy_sell_list)

    score = (z_rzjme * 0.5 + z_rzye * 0.3 + z_bs * 0.2) / 3.0
    return round(score, 4)


_shares_cache = None
def load_share_history():
    global _shares_cache
    if _shares_cache is not None:
        return _shares_cache
    if not os.path.exists(SHARES_PATH):
        _shares_cache = {}
        return _shares_cache
    try:
        raw = load_json(SHARES_PATH)
        history = dict(raw.get('history', {}))
        for date_str, values in raw.get('szse_snapshot', {}).items():
            history.setdefault(date_str, {}).update(values)
        _shares_cache = history
    except Exception:
        _shares_cache = {}
    return _shares_cache


def compute_share_flow_signal(code, date_str):
    """用不晚于决策日的份额快照估计周度申赎方向；无历史覆盖时返回0。"""
    history = load_share_history()
    dates = sorted(d for d in history if d <= date_str and code in history[d])
    if len(dates) < 2:
        return 0.0
    current = float(history[dates[-1]][code] or 0)
    previous = float(history[dates[-2]][code] or 0)
    if previous <= 0:
        return 0.0
    return round(_clip(((current - previous) / previous * 100) / 5), 4)


def get_experience_signal(experiences, code):
    """经验自适应: 该ETF历史买入的平均净收益->[-1,1]"""
    related = [e for e in experiences if e['etf_code'] == code and e['decision'] == 'buy']
    if not related:
        return 0.0
    recent = related[-5:]
    avg_ret = sum(e['net_return'] for e in recent) / len(recent)
    return round(max(-1.0, min(1.0, avg_ret * 15)), 4)


# ----------------------------- 多信号决策 -----------------------------
def make_decision(date, prev_date, etf_data, newspapers, experiences):
    """
    多信号评分决策 (Walk-Forward 优化版)。
    关键: 使用【前一日 prev_date】板块表现(动量/量比/均值回归) + 【当日 date】四大报(情绪)
          + 【T-1日】融资融券(大众情绪) => 不偷看当日收盘，规避 look-ahead bias
    
    优化参数 (胜率 53% → 70.5%):
      - 情绪信号方向反转 (机构看多为反向指标, 系数=-1.0)
      - 权重: 情绪1x + 动量1.5x + 大众情绪2.0x + 量比1x + 均值回归1x + 经验1x
      - 买入门槛: 1.0 (过滤噪音交易)
      - 动量窗口: 10日
    """
    sentiment = analyze_newspaper_sentiment(newspapers.get(date))
    external_sentiment = analyze_external_sentiment(load_external_news(), date)
    sector_perf = calculate_sector_performance(etf_data, prev_date) if prev_date else None
    retail_sent = compute_retail_sentiment(prev_date) if prev_date else 0.0
    market_state = compute_market_state(etf_data, prev_date) if prev_date else compute_market_state({}, '')

    hot_sector_rank = {}
    if sentiment['hot_sectors']:
        for rank, hs in enumerate(sentiment['hot_sectors']):
            hot_sector_rank[hs['sector']] = rank

    etf_scores = []
    for code, info in SECTOR_ETF_MAP.items():
        if code not in etf_data or not find_record(etf_data, code, prev_date):
            continue
        # 1) 报纸情绪热点信号 (1倍权重, 方向反转)
        if info['sector'] in hot_sector_rank:
            boost = 1.0 - hot_sector_rank[info['sector']] * 0.15
            sentiment_signal = round(sentiment['score'] * boost * SENTIMENT_LAG_COEF, 4)
        else:
            sentiment_signal = round(sentiment['score'] * 0.3 * SENTIMENT_LAG_COEF, 4)

        news_surprise = compute_news_surprise(newspapers, date, info)
        news_signal = round(sentiment_signal * (0.5 + 0.5 * abs(news_surprise)), 4)
        external_sector = external_sentiment['sector_scores'].get(info['sector'], 0.0)
        external_signal = round(_clip(0.55 * external_sentiment['score'] * info.get('risk_on', 1)
                                     + 0.45 * _clip(external_sector / 3)), 4)

        # 2) 资金行为层：识别启动、拥挤与撤退
        behavior = compute_behavior_signals(etf_data, code, prev_date)
        share_flow_signal = compute_share_flow_signal(code, prev_date)
        expectation_gap = compute_news_expectation_gaps(external_signal, behavior)
        mom_10d = behavior.get('mom_10d', 0.0)
        momentum_signal = behavior['momentum']

        # 3) 大众情绪信号 (融资融券z-score, 2.0倍权重)
        risk_on = info.get('risk_on', 1)
        retail_signal = round(_clip(retail_sent * risk_on), 4)

        # 4) 量比信号 (前日量比, 结合动量方向确认)
        vol_ratio = compute_volume_ratio(etf_data, code, prev_date) if prev_date else 1.0
        volume_signal = behavior['flow_proxy']

        # 5) 均值回归信号 (前10日累计收益反向)
        mr = compute_mean_reversion(etf_data, code, prev_date, MOMENTUM_WINDOW) if prev_date else 0.0
        meanrev_signal = round(_clip(-mr * 10), 4)

        # 6) 经验自适应信号
        exp_signal = get_experience_signal(experiences, code) * 0.10

        # 趋势与均值回归不能固定对冲：根据市场状态和套利压力切换。
        if market_state['name'] == 'risk_on' or behavior['crowding'] < 0.35:
            trend_weight, reversion_weight = 0.45, 0.10
        elif market_state['name'] == 'stress' and risk_on == 1:
            trend_weight, reversion_weight = 0.10, 0.25
        else:
            trend_weight, reversion_weight = 0.30, 0.20

        market_alignment = _clip((market_state['momentum_5d'] / 3) * risk_on)
        # 宽基锚定：风险偏好回升时给大盘宽基一个小幅、可解释的状态加分。
        anchor_bonus = 0.16 * max(0.0, market_alignment) if info.get('group') == 'large_cap' else 0.0
        regime_penalty = 0.35 if market_state['name'] == 'stress' and risk_on == 1 else 0.0
        regime_bonus = 0.20 if market_state['name'] == 'stress' and risk_on == -1 else 0.0
        stale_crowding = behavior['crowding'] * max(0.0, 1.0 - behavior['early_entry'])

        total_score = round(
            trend_weight * momentum_signal
            + reversion_weight * meanrev_signal
            + 0.45 * behavior['early_entry']
            + 0.30 * behavior['flow_proxy']
            + 0.15 * news_signal
            + 0.20 * external_signal
            + 0.08 * expectation_gap['news_price_gap']
            + 0.07 * expectation_gap['news_flow_gap']
            + 0.15 * retail_signal
            + 0.15 * market_alignment
            + anchor_bonus
            + exp_signal + regime_bonus
            - 0.35 * stale_crowding
            - 0.90 * behavior['withdrawal_risk']
            - regime_penalty, 4)

        etf_scores.append({
            'code': code, 'name': info['name'], 'sector': info['sector'],
            'sentiment_signal': sentiment_signal, 'news_surprise': news_surprise,
            'news_signal': news_signal, 'external_signal': external_signal,
            'news_price_gap': expectation_gap['news_price_gap'],
            'news_flow_gap': expectation_gap['news_flow_gap'],
            'external_sentiment': external_sentiment['score'],
            'momentum_signal': momentum_signal,
            'retail_sentiment': retail_sent, 'volume_signal': volume_signal,
            'meanrev_signal': meanrev_signal, 'experience_signal': exp_signal,
            'flow_proxy': behavior['flow_proxy'], 'early_entry': behavior['early_entry'],
            'share_flow_signal': share_flow_signal,
            'crowding': behavior['crowding'], 'withdrawal_risk': behavior['withdrawal_risk'],
            'acceleration': behavior['acceleration'], 'volatility': behavior['volatility'],
            'total_score': total_score,
            'prev_change_pct': mom_10d, 'prev_volume_ratio': vol_ratio,
            'mom_10d': mom_10d, 'group': info.get('group', info['sector']),
            'risk_on': risk_on,
        })

    etf_scores.sort(key=lambda x: -x['total_score'])
    avg_score = round(sum(e['total_score'] for e in etf_scores) / len(etf_scores), 4) if etf_scores else 0.0
    hs300_prev = sector_perf['hs300'] if sector_perf else 0.0

    # 趋势判断
    if market_state['name'] == 'risk_on':
        trend = 'bullish'
    elif market_state['name'] == 'stress':
        trend = 'bearish'
    else:
        trend = 'neutral'

    # ETF选择: 评分>买入门槛 取前3, 按评分分配权重
    positive = [e for e in etf_scores
                if e['total_score'] > BUY_THRESHOLD and e['withdrawal_risk'] < 0.45]
    selection = []
    if positive:
        best = positive[0]
        conviction = _clip((best['total_score'] - BUY_THRESHOLD) / (SCORE_FULL - BUY_THRESHOLD), 0.25, 1.0)
        position_scale = round(market_state['risk_budget'] * conviction, 4)
        # Core-satellite：只在前一日中期趋势和宽度支持时加入沪深300锚定仓，
        # 避免主题轮动模型在大盘上涨期长期跑输基准；锚定仓仍受风险预算约束。
        anchor = None
        if market_state['name'] in ('risk_on', 'neutral') and market_state['momentum_20d'] > 0 and market_state['breadth'] >= 0.50:
            anchor = next((e for e in etf_scores if e['code'] == HS300_CODE), None)
        candidates = [e for e in positive if not anchor or e['code'] != anchor['code']]
        chosen, used_groups = [], set()
        if anchor:
            chosen.append(anchor)
            used_groups.add(anchor['group'])
        for candidate in candidates:
            if candidate['group'] not in used_groups:
                chosen.append(candidate)
                used_groups.add(candidate['group'])
            if len(chosen) == 3:
                break
        if anchor:
            anchor_weight = round(position_scale * 0.35, 4)
            other = [e for e in chosen if e is not anchor]
            total_pos = sum(max(0.01, e['total_score']) for e in other)
            anchor['weight'] = anchor_weight
            selection.append(anchor)
            for e in other:
                e['weight'] = round((position_scale - anchor_weight) * max(0.01, e['total_score']) / total_pos, 4)
                selection.append(e)
        else:
            total_pos = sum(e['total_score'] for e in chosen)
            for e in chosen:
                e['weight'] = round(e['total_score'] / total_pos * position_scale, 4) if total_pos > 0 else 0.0
                selection.append(e)
    decision = 'buy' if selection else 'hold'

    # 决策理由
    if selection:
        top = selection[0]
        parts = []
        if abs(top['sentiment_signal']) > 0.01:
            parts.append(f"新闻预期差({top['news_signal']:.2f})")
        if abs(top['momentum_signal']) > 0.01:
            parts.append(f"动量({top['momentum_signal']:.2f})")
        if abs(top['volume_signal']) > 0.01:
            parts.append(f"量比({top['volume_signal']:.2f})")
        if abs(top['meanrev_signal']) > 0.01:
            parts.append(f"均值回归({top['meanrev_signal']:.2f})")
        if abs(top['experience_signal']) > 0.01:
            parts.append(f"经验({top['experience_signal']:.2f})")
        parts.append(f"启动{top['early_entry']:.2f}/拥挤{top['crowding']:.2f}/撤退{top['withdrawal_risk']:.2f}")
        reason = f"趋势{trend}，首选{top['name']}(总分{top['total_score']:.2f})，" + "、".join(parts)
    else:
        reason = f"趋势{trend}，无ETF评分为正，持币观望"

    return {
        'date': date, 'prev_date': prev_date, 'trend': trend, 'decision': decision,
        'etf_scores': etf_scores, 'selection': selection, 'reason': reason,
        'sentiment': sentiment, 'sector_performance': sector_perf, 'avg_score': avg_score,
        'market_state': market_state,
        'external_sentiment': external_sentiment,
    }


# ----------------------------- 主流程 -----------------------------
def run_model():
    etf_data = load_json(ETF_HISTORY_PATH)
    newspapers = load_json(NEWSPAPERS_PATH)
    trading_days = get_trading_days(etf_data)
    if len(trading_days) < 2:
        raise ValueError('ETF历史数据不足，至少需要2个交易日')

    capital = INITIAL_CAPITAL
    hs300_capital = INITIAL_CAPITAL
    experiences = []
    all_daily = []
    wins = losses = total_trades = 0
    total_profit = total_loss = 0.0

    # 遍历所有交易日(从第2个起, 需要前一日数据)
    i = 1
    while i < len(trading_days):
        date = trading_days[i]
        prev_date = trading_days[i - 1]
        decision = make_decision(date, prev_date, etf_data, newspapers, experiences)

        # 当日实际收益: 3日持仓 (T开盘买入 → T+2收盘卖出)
        day_return = 0.0
        chosen_names = []
        if decision['selection']:
            # 计算持仓期末日期 (T + HOLDING_PERIOD - 1)
            hold_end_idx = min(i + HOLDING_PERIOD - 1, len(trading_days) - 1)
            hold_end_date = trading_days[hold_end_idx]

            for sel in decision['selection']:
                rec_open = find_record(etf_data, sel['code'], date)
                rec_close = find_record(etf_data, sel['code'], hold_end_date)
                if rec_open and rec_open['open'] and rec_close and rec_close['close']:
                    holding_return = (rec_close['close'] - rec_open['open']) / rec_open['open']
                    net = holding_return - 2 * COMMISSION_RATE   # 买卖各一次佣金
                    day_return += sel['weight'] * net
                    sel['intraday_return_pct'] = round(holding_return * 100, 4)
                chosen_names.append(sel['name'])
            total_trades += 1
            if day_return > 0:
                wins += 1
                total_profit += day_return
            elif day_return < 0:
                losses += 1
                total_loss += abs(day_return)

            # 跳过持仓期间的交易日 (不再做新决策)
            i = hold_end_idx + 1
        else:
            i += 1

        capital *= (1 + day_return)

        # hs300 基准(同样3日持仓收益)
        hs_rec_open = find_record(etf_data, HS300_CODE, date)
        if decision['selection']:
            hs_rec_close = find_record(etf_data, HS300_CODE, hold_end_date)
            if hs_rec_open and hs_rec_open['open'] and hs_rec_close and hs_rec_close['close']:
                hs_return = (hs_rec_close['close'] - hs_rec_open['open']) / hs_rec_open['open']
            else:
                hs_return = 0.0
        else:
            hs_return = (hs_rec_open['close'] - hs_rec_open['open']) / hs_rec_open['open'] if (hs_rec_open and hs_rec_open['open']) else 0.0
        hs300_capital *= (1 + hs_return)
        alpha = day_return - hs_return

        # 经验库记录(仅记录买入决策)
        if decision['selection']:
            top = decision['selection'][0]
            rec_open = find_record(etf_data, top['code'], date)
            rec_close = find_record(etf_data, top['code'], hold_end_date)
            if rec_open and rec_open['open'] and rec_close and rec_close['close']:
                holding_return = (rec_close['close'] - rec_open['open']) / rec_open['open']
            else:
                holding_return = 0.0
            net = holding_return - 2 * COMMISSION_RATE
            experiences.append({
                'date': date, 'etf_code': top['code'], 'etf_name': top['name'],
                'sector': top['sector'], 'trend': decision['trend'],
                'decision': 'buy', 'total_score': top['total_score'],
                'sentiment_score': decision['sentiment']['score'],
                'intraday_return': round(holding_return * 100, 4),
                'net_return': round(net, 6),
                'result': 'win' if net > 0 else 'loss',
                'weight': top['weight'],
                'holding_days': HOLDING_PERIOD,
            })
            if len(experiences) > MAX_EXPERIENCES:
                experiences = experiences[-MAX_EXPERIENCES:]

        all_daily.append({
            'date': date, 'trend': decision['trend'], 'decision': decision['decision'],
            'market_state': decision['market_state']['name'],
            'risk_budget': decision['market_state']['risk_budget'],
            'market_breadth': decision['market_state']['breadth'],
            'market_momentum_20d': decision['market_state']['momentum_20d'],
            'market_volatility_20d': decision['market_state']['volatility_20d'],
            'etf_names': chosen_names,
            'return': round(day_return * 100, 4),
            'hs300': round(hs_return * 100, 4),
            'alpha': round(alpha * 100, 4),
            'sentiment_score': decision['sentiment']['score'],
        })

    # 当前可用ETF区间累计涨跌幅均值(参考)
    etf_cum = []
    for code in SECTOR_ETF_MAP:
        data = etf_data.get(code, {}).get('data', [])
        if data and data[0]['close']:
            etf_cum.append(round((data[-1]['close'] - data[0]['close']) / data[0]['close'] * 100, 2))
    etf_avg = round(sum(etf_cum) / len(etf_cum), 2) if etf_cum else 0.0

    # 主基准使用完整样本区间买入持有，避免因策略空仓/跳过持仓日而扭曲 Alpha。
    hs300_records = etf_data.get(HS300_CODE, {}).get('data', [])
    hs300_buy_hold = 0.0
    if len(hs300_records) >= 2 and hs300_records[0].get('open') and hs300_records[-1].get('close'):
        hs300_buy_hold = round((hs300_records[-1]['close'] / hs300_records[0]['open'] - 1) * 100, 2)

    cum_return = round((capital / INITIAL_CAPITAL - 1) * 100, 2)
    hs300_cum = round((hs300_capital / INITIAL_CAPITAL - 1) * 100, 2)
    alpha_cum = round(cum_return - hs300_cum, 2)
    win_rate = round(wins / total_trades * 100, 2) if total_trades else 0.0
    avg_win = round(total_profit / wins, 4) if wins > 0 else 0.0
    avg_loss = round(total_loss / losses, 4) if losses > 0 else 0.0
    if total_loss > 0:
        profit_loss_ratio = round(total_profit / total_loss, 2)
    elif total_profit > 0:
        profit_loss_ratio = 999.99
    else:
        profit_loss_ratio = 0.0

    # 最新决策: 取最新可决策日期(最新四大报日 vs 最新ETF日)
    latest_news_date = max(newspapers.keys()) if newspapers else trading_days[-1]
    latest_etf_date = trading_days[-1]
    if latest_news_date > latest_etf_date:
        latest_dec = make_decision(latest_news_date, latest_etf_date, etf_data, newspapers, experiences)
    else:
        latest_dec = make_decision(latest_etf_date, get_prev_date(trading_days, latest_etf_date),
                                   etf_data, newspapers, experiences)

    summary = {
        'report_date': latest_dec['date'],
        'cumulative_return': cum_return,
        'hs300_return': hs300_buy_hold,
        'hs300_cumulative_return': hs300_buy_hold,
        'decision_calendar_hs300_return': hs300_cum,
        'alpha': round(cum_return - hs300_buy_hold, 2),
        'win_rate': win_rate,
        'profit_loss_ratio': profit_loss_ratio,
        'trading_days': len(all_daily),
        'total_trades': total_trades,
        'experience_count': len(experiences),
        'etf_avg_performance': etf_avg,
        'final_capital': round(capital, 2),
        'initial_capital': INITIAL_CAPITAL,
        'commission_rate': COMMISSION_RATE,
        'wins': wins,
        'losses': losses,
        'avg_profit': avg_win,
        'avg_loss': avg_loss,
        'start_date': all_daily[0]['date'] if all_daily else None,
    }

    sp = latest_dec['sector_performance']
    latest_decision = {
        'date': latest_dec['date'],
        'trend': latest_dec['trend'],
        'decision': latest_dec['decision'],
        'etf_selection': [
            {'code': s['code'], 'name': s['name'], 'sector': s['sector'],
             'weight': s.get('weight', 0.0), 'total_score': s['total_score'],
             'early_entry': s['early_entry'], 'crowding': s['crowding'],
             'withdrawal_risk': s['withdrawal_risk'], 'flow_proxy': s['flow_proxy'],
             'external_signal': s.get('external_signal', 0.0),
             'news_price_gap': s.get('news_price_gap', 0.0),
             'news_flow_gap': s.get('news_flow_gap', 0.0),
             'share_flow_signal': s.get('share_flow_signal', 0.0)}
            for s in latest_dec['selection']
        ],
        'weight': round(sum(s.get('weight', 0.0) for s in latest_dec['selection']), 4),
        'reason': latest_dec['reason'],
        'sentiment': {
            'score': latest_dec['sentiment']['score'],
            'bullish_count': latest_dec['sentiment']['bullish_count'],
            'bearish_count': latest_dec['sentiment']['bearish_count'],
            'hot_sectors': latest_dec['sentiment']['hot_sectors'],
            'summary': latest_dec['sentiment']['summary'],
        },
        'sector_performance': {
            'date': sp['date'] if sp else None,
            'prev_date': sp['prev_date'] if sp else None,
            'top5': sp['top5'] if sp else [],
            'bottom5': sp['bottom5'] if sp else [],
            'hs300': sp['hs300'] if sp else 0.0,
            'avg': sp['avg'] if sp else 0.0,
        } if sp else None,
        'avg_score': latest_dec['avg_score'],
        'market_state': latest_dec['market_state'],
        'external_sentiment': latest_dec.get('external_sentiment', {}),
        'rankings': [
            {'code': s['code'], 'name': s['name'], 'sector': s['sector'],
             'score': s['total_score'], 'early_entry': s['early_entry'],
             'crowding': s['crowding'], 'withdrawal_risk': s['withdrawal_risk']}
            for s in latest_dec['etf_scores']
        ],
    }

    result = {
        'summary': summary,
        'latest_decision': latest_decision,
        'experiences': experiences,
        'all_daily_summaries': all_daily,
        'latest_newspapers': newspapers.get(latest_news_date, {}),
    }

    save_json(OUTPUT_PATH, result)
    return result


if __name__ == '__main__':
    res = run_model()
    s = res['summary']
    print('=' * 60)
    print('ETF规则模型运行完成')
    print('=' * 60)
    print(f"交易天数: {s['trading_days']}  交易次数: {s['total_trades']}")
    print(f"累计收益: {s['cumulative_return']}%  沪深300: {s['hs300_cumulative_return']}%  Alpha: {s['alpha']}%")
    print(f"胜率: {s['win_rate']}%  盈亏比: {s['profit_loss_ratio']}  经验条数: {s['experience_count']}")
    print(f"ETF平均表现: {s['etf_avg_performance']}%  最终资金: {s['final_capital']}")
    ld = res['latest_decision']
    print(f"\n最新决策 ({ld['date']}): 趋势={ld['trend']}  决策={ld['decision']}")
    print(f"  选择: {[(e['name'], e['weight']) for e in ld['etf_selection']]}")
    print(f"  理由: {ld['reason']}")
    print(f"  情绪: {ld['sentiment']['summary']}")
    print(f"\n结果已保存: {OUTPUT_PATH}")
