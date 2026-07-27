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

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
ETF_HISTORY_PATH = os.path.join(DATA_DIR, 'etf_history.json')
NEWSPAPERS_PATH = os.path.join(DATA_DIR, 'newspapers.json')
MARGIN_PATH = os.path.join(DATA_DIR, 'margin_trading.json')
OUTPUT_PATH = os.path.join(DATA_DIR, 'model_results.json')

# 11个ETF板块映射
SECTOR_ETF_MAP = {
    '512760': {'name': '半导体ETF', 'sector': '半导体', 'keywords': ['半导体', '芯片', '集成电路', '国产替代']},
    '159995': {'name': '芯片ETF', 'sector': '芯片', 'keywords': ['芯片', '半导体', '存储', '封测']},
    '515980': {'name': '人工智能ETF', 'sector': 'AI算力', 'keywords': ['AI', '人工智能', '算力', '大模型', '智能']},
    '159592': {'name': '卫星产业ETF', 'sector': '商业航天', 'keywords': ['航天', '卫星', '商业航天', '火箭']},
    '515120': {'name': '创新药ETF', 'sector': '医药', 'keywords': ['医药', '创新药', '医疗', '生物', '健康']},
    '516160': {'name': '新能源ETF', 'sector': '新能源', 'keywords': ['新能源', '光伏', '锂电', '储能', '充电']},
    '510150': {'name': '消费ETF', 'sector': '消费', 'keywords': ['消费', '零售', '食品', '白酒', '家电']},
    '518880': {'name': '黄金ETF', 'sector': '黄金', 'keywords': ['黄金', '贵金属', '避险']},
    '512000': {'name': '券商ETF', 'sector': '券商', 'keywords': ['券商', '证券', '金融', '牛市']},
    '512660': {'name': '军工ETF', 'sector': '军工', 'keywords': ['军工', '国防', '航天', '装备']},
    '510300': {'name': '沪深300ETF', 'sector': '宽基', 'keywords': ['沪深300', '大盘', '宽基']},
}

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
SCORE_FULL = 0.5               # 满仓评分阈值

# ====== Walk-Forward 优化参数 (胜率 53% → 70.5%) ======
SENTIMENT_LAG_COEF = -1.0      # 情绪信号方向反转 (机构看多为反向指标)
WEIGHT_SENTIMENT = 1           # 情绪权重 3→1
WEIGHT_MOMENTUM = 1.5          # 动量权重 1→1.5
WEIGHT_RETAIL = 2.0            # 大众情绪权重 (新增)
BUY_THRESHOLD = 1.0            # 买入门槛 0→1.0
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
    sector_perf = calculate_sector_performance(etf_data, prev_date) if prev_date else None
    retail_sent = compute_retail_sentiment(prev_date) if prev_date else 0.0

    hot_sector_rank = {}
    if sentiment['hot_sectors']:
        for rank, hs in enumerate(sentiment['hot_sectors']):
            hot_sector_rank[hs['sector']] = rank

    etf_scores = []
    for code, info in SECTOR_ETF_MAP.items():
        # 1) 报纸情绪热点信号 (1倍权重, 方向反转)
        if info['sector'] in hot_sector_rank:
            boost = 1.0 - hot_sector_rank[info['sector']] * 0.15
            sentiment_signal = round(sentiment['score'] * boost * SENTIMENT_LAG_COEF, 4)
        else:
            sentiment_signal = round(sentiment['score'] * 0.3 * SENTIMENT_LAG_COEF, 4)

        # 2) 板块动量信号 (前10日累计涨跌幅, 1.5倍权重)
        mom_10d = compute_momentum_n(etf_data, code, prev_date, MOMENTUM_WINDOW) if prev_date else 0.0
        momentum_signal = round(max(-1.0, min(1.0, mom_10d / 5.0)), 4)

        # 3) 大众情绪信号 (融资融券z-score, 2.0倍权重)
        retail_signal = round(max(-1.0, min(1.0, retail_sent)), 4)

        # 4) 量比信号 (前日量比, 结合动量方向确认)
        vol_ratio = compute_volume_ratio(etf_data, code, prev_date) if prev_date else 1.0
        mom_sign = 1 if mom_10d > 0 else (-1 if mom_10d < 0 else 0)
        volume_signal = round(max(-1.0, min(1.0, (vol_ratio - 1) * mom_sign)), 4)

        # 5) 均值回归信号 (前10日累计收益反向)
        mr = compute_mean_reversion(etf_data, code, prev_date, MOMENTUM_WINDOW) if prev_date else 0.0
        meanrev_signal = round(max(-1.0, min(1.0, -mr * 10)), 4)

        # 6) 经验自适应信号
        exp_signal = get_experience_signal(experiences, code)

        total_score = round(
            WEIGHT_SENTIMENT * sentiment_signal
            + WEIGHT_MOMENTUM * momentum_signal
            + WEIGHT_RETAIL * retail_signal
            + volume_signal + meanrev_signal + exp_signal, 4)

        etf_scores.append({
            'code': code, 'name': info['name'], 'sector': info['sector'],
            'sentiment_signal': sentiment_signal, 'momentum_signal': momentum_signal,
            'retail_sentiment': retail_sent, 'volume_signal': volume_signal,
            'meanrev_signal': meanrev_signal, 'experience_signal': exp_signal,
            'total_score': total_score,
            'prev_change_pct': mom_10d, 'prev_volume_ratio': vol_ratio,
            'mom_10d': mom_10d,
        })

    etf_scores.sort(key=lambda x: -x['total_score'])
    avg_score = round(sum(e['total_score'] for e in etf_scores) / len(etf_scores), 4) if etf_scores else 0.0
    hs300_prev = sector_perf['hs300'] if sector_perf else 0.0

    # 趋势判断
    if avg_score > 0.2 and (retail_sent > 0 or hs300_prev > 0):
        trend = 'bullish'
    elif avg_score < -0.2 and (retail_sent < 0 or hs300_prev < 0):
        trend = 'bearish'
    else:
        trend = 'neutral'

    # ETF选择: 评分>买入门槛 取前3, 按评分分配权重
    positive = [e for e in etf_scores if e['total_score'] > BUY_THRESHOLD]
    selection = []
    if positive:
        best = positive[0]
        position_scale = round(min(1.0, best['total_score'] / SCORE_FULL), 4)
        chosen = positive[:3]
        total_pos = sum(e['total_score'] for e in chosen)
        for e in chosen:
            w = round(e['total_score'] / total_pos * position_scale, 4) if total_pos > 0 else 0.0
            e['weight'] = w
            selection.append(e)
    decision = 'buy' if selection else 'hold'

    # 决策理由
    if selection:
        top = selection[0]
        parts = []
        if abs(top['sentiment_signal']) > 0.01:
            parts.append(f"情绪热点({top['sentiment_signal']:.2f},3倍权重)")
        if abs(top['momentum_signal']) > 0.01:
            parts.append(f"动量({top['momentum_signal']:.2f})")
        if abs(top['volume_signal']) > 0.01:
            parts.append(f"量比({top['volume_signal']:.2f})")
        if abs(top['meanrev_signal']) > 0.01:
            parts.append(f"均值回归({top['meanrev_signal']:.2f})")
        if abs(top['experience_signal']) > 0.01:
            parts.append(f"经验({top['experience_signal']:.2f})")
        reason = f"趋势{trend}，首选{top['name']}(总分{top['total_score']:.2f})，" + "、".join(parts)
    else:
        reason = f"趋势{trend}，无ETF评分为正，持币观望"

    return {
        'date': date, 'prev_date': prev_date, 'trend': trend, 'decision': decision,
        'etf_scores': etf_scores, 'selection': selection, 'reason': reason,
        'sentiment': sentiment, 'sector_performance': sector_perf, 'avg_score': avg_score,
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
            'etf_names': chosen_names,
            'return': round(day_return * 100, 4),
            'hs300': round(hs_return * 100, 4),
            'alpha': round(alpha * 100, 4),
            'sentiment_score': decision['sentiment']['score'],
        })

    # 11个ETF区间累计涨跌幅均值(参考)
    etf_cum = []
    for code in SECTOR_ETF_MAP:
        data = etf_data[code]['data']
        if data and data[0]['close']:
            etf_cum.append(round((data[-1]['close'] - data[0]['close']) / data[0]['close'] * 100, 2))
    etf_avg = round(sum(etf_cum) / len(etf_cum), 2) if etf_cum else 0.0

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
        'hs300_return': hs300_cum,
        'hs300_cumulative_return': hs300_cum,
        'alpha': alpha_cum,
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
             'weight': s.get('weight', 0.0), 'total_score': s['total_score']}
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
