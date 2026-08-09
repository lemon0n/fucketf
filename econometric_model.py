#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF计量模型 — 在规则模型基础上构建面板数据，运行 Logit / OLS / Lasso 回归

面板结构: 每行 = 一个 (ETF, 决策日) 观测
规避 look-ahead bias:
  * 价格类特征统一使用【前一日 T-1】数据 (prev_change_pct / prev_volume_ratio / prev_intraday_return)
  * 情绪类特征使用【当日 T】四大报 (晨报在开盘前可得，不构成偷看)
  * 外部事件在缺少精确时刻时仅使用【T-1及更早】信息
  * 目标 target_return / target_direction 为【T开盘->T+2收盘】相对沪深300、扣成本净Alpha
  => 所有特征在 T 开盘前均已知

输出: data/econometric_results.json
"""
import json
import os
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.linear_model import Lasso, LogisticRegression
from sklearn.preprocessing import StandardScaler

# 复用规则模型中的常量与基础工具 (避免重复定义)
from etf_model_run import (
    SECTOR_ETF_MAP, HS300_CODE, ETF_HISTORY_PATH, NEWSPAPERS_PATH,
    HOLDING_PERIOD, COMMISSION_RATE, SLIPPAGE_RATE,
    load_json, get_trading_days, find_record, get_index, get_prev_date,
    compute_volume_ratio, analyze_newspaper_sentiment,
    compute_behavior_signals, compute_market_state, compute_news_surprise,
    compute_news_expectation_gaps,
    compute_share_flow_signal, load_share_history,
    load_external_news, analyze_external_sentiment,
)

warnings.filterwarnings('ignore')

OUTPUT_PATH = os.path.join(os.path.dirname(ETF_HISTORY_PATH), 'econometric_results.json')
MODEL_RESULTS_PATH = os.path.join(os.path.dirname(ETF_HISTORY_PATH), 'model_results.json')
MARGIN_PATH = os.path.join(os.path.dirname(ETF_HISTORY_PATH), 'margin_trading.json')

# 特征列 (全部为 T 开盘前可知)
# 2026-07-27 新增 hs300_mom_5d / vol_10d (统计显著, p<0.01)
# retail_sentiment / rzjme_yi / sentiment_divergence 提供大众情绪诊断；
# 不沿用小样本相关率或胜率结论，是否有效只看严格时间样本外结果。
FEATURES = [
    'sentiment_score', 'bullish_count', 'bearish_count',
    'prev_change_pct', 'prev_volume_ratio', 'prev_intraday_return',
    'sector_mentioned', 'sector_mention_count',
    'hs300_mom_5d', 'vol_10d',
    'retail_sentiment', 'rzjme_yi', 'sentiment_divergence',
    'behavior_momentum', 'flow_proxy', 'acceleration', 'crowding',
    'withdrawal_risk', 'early_entry', 'news_surprise', 'market_breadth',
    'external_signal', 'external_news_count', 'news_price_gap', 'news_flow_gap', 'share_flow_signal',
]

# 预测器只使用在历史逐日样本外检验中稳定的市场/大众情绪因子；其余变量仍保留
# 在面板和 Lasso 诊断中，避免把小样本里的噪声带入每日概率预测。
PREDICTIVE_FEATURES = [
    'behavior_momentum', 'flow_proxy', 'acceleration', 'crowding',
    'withdrawal_risk', 'early_entry', 'news_surprise', 'market_breadth',
    'external_signal', 'news_price_gap', 'news_flow_gap', 'share_flow_signal',
]
PREDICTIVE_C = 0.3
PURGE_DAYS = HOLDING_PERIOD - 1
HIGH_CONFIDENCE_THRESHOLD = 0.60
LOW_CONFIDENCE_THRESHOLD = 0.40
MIN_SELECTIVE_OBS = 40


# ----------------------------- 工具 -----------------------------
def save_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)

    def default(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, (pd.Timestamp,)):
            return str(o)
        raise TypeError(f'不可序列化: {type(o)}')

    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=default)


def sector_mention_count(news_for_day, info):
    """该日四大报中提及某板块的标题数"""
    cnt = 0
    for paper, titles in news_for_day.items():
        for title in titles:
            if any(kw in title for kw in info['keywords']):
                cnt += 1
                break  # 每报每标题计一次
    return cnt


def add_const(X):
    """始终前置一列常数1, 避免 sm.add_constant 在单日面板(情绪列恒定)时跳过截距"""
    X = np.asarray(X, dtype=float)
    if X.ndim == 1:
        X = X.reshape(-1, 1)
    return np.column_stack([np.ones(X.shape[0]), X])


def compute_net_alpha_target(etf_entry_open, etf_exit_close,
                             benchmark_entry_open, benchmark_exit_close,
                             round_trip_cost_rate=None):
    """ETF相对沪深300的完整持有期净Alpha（百分点）。"""
    if round_trip_cost_rate is None:
        round_trip_cost_rate = 2 * (COMMISSION_RATE + SLIPPAGE_RATE)
    etf_return = etf_exit_close / etf_entry_open - 1
    benchmark_return = benchmark_exit_close / benchmark_entry_open - 1
    return (etf_return - benchmark_return - round_trip_cost_rate) * 100


def compute_hs300_mom_5d(etf_data, date):
    """沪深300前5日累计收益(%) — 市场状态信号, T-1收盘价相对5日前收盘价"""
    idx = get_index(etf_data, HS300_CODE, date)
    if idx < 5:
        return 0.0
    base = etf_data[HS300_CODE]['data'][idx - 5]['close']
    cur = etf_data[HS300_CODE]['data'][idx]['close']
    return round((cur - base) / base * 100, 4) if base else 0.0


def compute_vol_10d(etf_data, code, date):
    """个股前10日日收益波动率(%) — 风险溢价信号"""
    idx = get_index(etf_data, code, date)
    if idx < 10:
        return 0.0
    rets = []
    for j in range(idx - 9, idx + 1):
        a = etf_data[code]['data'][j - 1]['close']
        b = etf_data[code]['data'][j]['close']
        if a:
            rets.append((b - a) / a)
    if not rets:
        return 0.0
    return round(float(np.std(rets)) * 100, 4)


# ----------------------------- 大众情绪(融资融券) -----------------------------
_margin_cache = None

def load_margin_data():
    """加载融资融券数据, 带缓存"""
    global _margin_cache
    if _margin_cache is not None:
        return _margin_cache
    if not os.path.exists(MARGIN_PATH):
        return {}
    raw = load_json(MARGIN_PATH)
    _margin_cache = {r['date']: r for r in raw}
    return _margin_cache


def compute_retail_sentiment(date_str):
    """
    计算大众情绪综合评分 — 基于融资融券数据
    输入: 日期字符串 'YYYY-MM-DD'
    返回: (retail_sentiment, rzjme_yi) 或 (0.0, 0.0)
    
    评分逻辑:
      融资净买入额 z-score * 0.5 + 融资余额变化 z-score * 0.3 + 买卖比 z-score * 0.2
      范围 [-1, 1], 正值=大众看多, 负值=大众看空
    
    时效: T-1日的融资融券数据在T日开盘前可得(T-1盘后公布)
    """
    margin_map = load_margin_data()
    if not margin_map:
        return 0.0, 0.0
    
    # 获取该日及之前的数据用于z-score计算
    dates_sorted = sorted(margin_map.keys())
    idx = None
    for i, d in enumerate(dates_sorted):
        if d <= date_str:
            idx = i
        else:
            break
    if idx is None or idx < 10:
        return 0.0, 0.0
    
    # 用截至该日的窗口计算z-score (避免look-ahead)
    window = dates_sorted[max(0, idx-59):idx+1]
    records = [margin_map[d] for d in window]
    
    rzjme_list = [r['rzjme'] / 1e8 for r in records]  # 亿元
    rzye_chg_list = [0.0] + [(records[j]['rzye'] - records[j-1]['rzye']) / 1e8 for j in range(1, len(records))]
    buy_sell_list = [r['rzmre'] / (r['rzche'] + 1) for r in records]
    
    cur_rzjme = rzjme_list[-1]
    cur_rzye_chg = rzye_chg_list[-1]
    cur_bs_ratio = buy_sell_list[-1]
    
    def safe_z(val, vals):
        if len(vals) < 5:
            return 0.0
        m = np.mean(vals)
        s = np.std(vals)
        if s < 1e-8:
            return 0.0
        return max(-3, min(3, (val - m) / s))
    
    z_rzjme = safe_z(cur_rzjme, rzjme_list)
    z_rzye = safe_z(cur_rzye_chg, rzye_chg_list)
    z_bs = safe_z(cur_bs_ratio, buy_sell_list)
    
    score = (z_rzjme * 0.5 + z_rzye * 0.3 + z_bs * 0.2) / 3.0
    return round(float(score), 4), round(float(cur_rzjme), 2)


def compute_sentiment_divergence(inst_score, retail_score):
    """
    机构-大众情绪分歧度
    当两情绪方向相反时, 分歧度高 → 预测力最强
    返回值: |inst - retail| * sign(inst) * (-sign(retail))
    简化: 1 - inst*retail (两情绪同向时接近0, 反向时接近1)
    """
    return round(1.0 - float(inst_score) * float(retail_score), 4)


# ----------------------------- 1. 构建面板数据 -----------------------------
def build_dataset(etf_data, news_data):
    """
    构建面板数据: 每行一个 ETF-日期观测。
    特征用前一日数据(价格类) + 当日四大报(情绪类) + 前一日融资融券(大众情绪)。
    目标与正式交易一致：T开盘至T+2收盘的ETF收益，减同期沪深300收益和往返成本。
    """
    trading_days = get_trading_days(etf_data)
    round_trip_cost_pct = 2 * (COMMISSION_RATE + SLIPPAGE_RATE) * 100
    rows = []
    for i in range(2, len(trading_days) - HOLDING_PERIOD + 1):
        T = trading_days[i]
        Tm1 = trading_days[i - 1]
        Tm2 = trading_days[i - 2]
        target_end = trading_days[i + HOLDING_PERIOD - 1]

        # 当日四大报情绪 (开盘前可得) — 机构视角
        news_T = news_data.get(T, {})
        sent = analyze_newspaper_sentiment(news_T)

        # 各板块当日提及情况
        mention = {code: sector_mention_count(news_T, info) for code, info in SECTOR_ETF_MAP.items()}

        # 市场状态信号 (T-1可知, 全局共享)
        hs300_mom_5d = compute_hs300_mom_5d(etf_data, Tm1)
        market_state = compute_market_state(etf_data, Tm1)
        # 外部事件多数没有开盘前可见时刻；保守地仅使用T-1及更早信息。
        external_sent = analyze_external_sentiment(load_external_news(), Tm1)

        # 大众情绪 (T-1融资融券数据, T开盘前可得) — 大众视角
        retail_sent, rzjme_yi = compute_retail_sentiment(Tm1)
        sentiment_div = compute_sentiment_divergence(sent['score'], retail_sent)

        for code, info in SECTOR_ETF_MAP.items():
            if code == HS300_CODE:
                continue  # 基准自身的相对Alpha恒等于负交易成本，没有可学习标签。
            rec_T = find_record(etf_data, code, T)
            rec_end = find_record(etf_data, code, target_end)
            rec_Tm1 = find_record(etf_data, code, Tm1)
            rec_Tm2 = find_record(etf_data, code, Tm2)
            bench_T = find_record(etf_data, HS300_CODE, T)
            bench_end = find_record(etf_data, HS300_CODE, target_end)
            if not (rec_T and rec_end and rec_Tm1 and rec_Tm2 and bench_T and bench_end):
                continue
            if not (rec_T['open'] and rec_end['close'] and rec_Tm1['open'] and rec_Tm2['close']
                    and bench_T['open'] and bench_end['close']):
                continue

            # 旧当日日内目标仅保留作数据诊断；正式模型使用三日成本后净Alpha。
            today_return = (rec_T['close'] - rec_T['open']) / rec_T['open'] * 100
            today_direction = 1 if today_return > 0 else 0
            holding_return = (rec_end['close'] - rec_T['open']) / rec_T['open'] * 100
            benchmark_return = (bench_end['close'] - bench_T['open']) / bench_T['open'] * 100
            target_return = compute_net_alpha_target(
                rec_T['open'], rec_end['close'], bench_T['open'], bench_end['close'])
            target_direction = 1 if target_return > 0 else 0

            # 前一日价格特征
            prev_change_pct = (rec_Tm1['close'] - rec_Tm2['close']) / rec_Tm2['close'] * 100
            prev_volume_ratio = compute_volume_ratio(etf_data, code, Tm1)
            prev_intraday_return = (rec_Tm1['close'] - rec_Tm1['open']) / rec_Tm1['open'] * 100

            # 新增: 市场状态 + 个股波动率
            vol_10d = compute_vol_10d(etf_data, code, Tm1)
            behavior = compute_behavior_signals(etf_data, code, Tm1)
            news_surprise = compute_news_surprise(news_data, T, info)
            external_signal = float(np.clip(
                0.55 * external_sent['score'] * info.get('risk_on', 1)
                + 0.45 * np.clip(external_sent['sector_scores'].get(info['sector'], 0.0) / 3, -1, 1), -1, 1))
            expectation_gap = compute_news_expectation_gaps(external_signal, behavior)
            share_flow_signal = compute_share_flow_signal(code, Tm1)

            rows.append({
                'date': T, 'etf_code': code, 'etf_name': info['name'], 'sector': info['sector'],
                'sentiment_score': float(sent['score']),
                'bullish_count': int(sent['bullish_count']),
                'bearish_count': int(sent['bearish_count']),
                'prev_change_pct': round(prev_change_pct, 4),
                'prev_volume_ratio': float(prev_volume_ratio),
                'prev_intraday_return': round(prev_intraday_return, 4),
                'sector_mentioned': 1 if mention[code] > 0 else 0,
                'sector_mention_count': int(mention[code]),
                'hs300_mom_5d': hs300_mom_5d,
                'vol_10d': vol_10d,
                'retail_sentiment': retail_sent,
                'rzjme_yi': rzjme_yi,
                'sentiment_divergence': sentiment_div,
                'behavior_momentum': behavior['momentum'],
                'flow_proxy': behavior['flow_proxy'],
                'acceleration': behavior['acceleration'],
                'crowding': behavior['crowding'],
                'withdrawal_risk': behavior['withdrawal_risk'],
                'early_entry': behavior['early_entry'],
                'news_surprise': news_surprise,
                'market_breadth': market_state['breadth'],
                'external_signal': round(external_signal, 4),
                'external_news_count': external_sent['count'],
                'news_price_gap': expectation_gap['news_price_gap'],
                'news_flow_gap': expectation_gap['news_flow_gap'],
                'share_flow_signal': share_flow_signal,
                'target_end_date': target_end,
                'holding_return': round(holding_return, 4),
                'benchmark_return': round(benchmark_return, 4),
                'round_trip_cost': round(round_trip_cost_pct, 4),
                'target_return': round(target_return, 4),
                'target_direction': int(target_direction),
                'today_return': round(today_return, 4),
                'today_direction': int(today_direction),
            })

    df = pd.DataFrame(rows)
    return df


def build_latest_features(etf_data, news_data):
    """构建最新决策日的非基准ETF特征行，用于未来3日净Alpha诊断。"""
    trading_days = get_trading_days(etf_data)
    latest_news_date = max(news_data.keys()) if news_data else trading_days[-1]
    latest_etf_date = trading_days[-1]

    # 预测日 T = 最新四大报日; 前一日 = 最新ETF日(若四大报更新) 或 T-1
    if latest_news_date > latest_etf_date:
        T = latest_news_date
        Tm1 = latest_etf_date
        Tm2 = get_prev_date(trading_days, latest_etf_date)
    else:
        T = latest_etf_date
        Tm1 = get_prev_date(trading_days, T)
        Tm2 = get_prev_date(trading_days, Tm1) if Tm1 else None

    news_T = news_data.get(T, {})
    sent = analyze_newspaper_sentiment(news_T)
    mention = {code: sector_mention_count(news_T, info) for code, info in SECTOR_ETF_MAP.items()}

    # 市场状态信号 (T-1可知)
    hs300_mom_5d = compute_hs300_mom_5d(etf_data, Tm1) if Tm1 else 0.0
    market_state = compute_market_state(etf_data, Tm1) if Tm1 else {'breadth': 0.5}
    external_sent = analyze_external_sentiment(load_external_news(), Tm1) if Tm1 else {
        'score': 0.0, 'sector_scores': {}, 'count': 0}

    # 大众情绪 (T-1融资融券数据, T开盘前可得)
    retail_sent, rzjme_yi = compute_retail_sentiment(Tm1) if Tm1 else (0.0, 0.0)
    sentiment_div = compute_sentiment_divergence(sent['score'], retail_sent)

    rows = []
    for code, info in SECTOR_ETF_MAP.items():
        if code == HS300_CODE:
            continue
        rec_Tm1 = find_record(etf_data, code, Tm1)
        rec_Tm2 = find_record(etf_data, code, Tm2) if Tm2 else None
        if not (rec_Tm1 and rec_Tm2):
            continue
        prev_change_pct = (rec_Tm1['close'] - rec_Tm2['close']) / rec_Tm2['close'] * 100
        prev_volume_ratio = compute_volume_ratio(etf_data, code, Tm1)
        prev_intraday_return = (rec_Tm1['close'] - rec_Tm1['open']) / rec_Tm1['open'] * 100
        vol_10d = compute_vol_10d(etf_data, code, Tm1)
        behavior = compute_behavior_signals(etf_data, code, Tm1)
        news_surprise = compute_news_surprise(news_data, T, info)
        external_signal = float(np.clip(
            0.55 * external_sent['score'] * info.get('risk_on', 1)
            + 0.45 * np.clip(external_sent['sector_scores'].get(info['sector'], 0.0) / 3, -1, 1), -1, 1))
        expectation_gap = compute_news_expectation_gaps(external_signal, behavior)
        share_flow_signal = compute_share_flow_signal(code, Tm1)
        rows.append({
            'predict_date': T, 'prev_date': Tm1, 'etf_code': code,
            'etf_name': info['name'], 'sector': info['sector'],
            'sentiment_score': float(sent['score']),
            'bullish_count': int(sent['bullish_count']),
            'bearish_count': int(sent['bearish_count']),
            'prev_change_pct': round(prev_change_pct, 4),
            'prev_volume_ratio': float(prev_volume_ratio),
            'prev_intraday_return': round(prev_intraday_return, 4),
            'sector_mentioned': 1 if mention[code] > 0 else 0,
            'sector_mention_count': int(mention[code]),
            'hs300_mom_5d': hs300_mom_5d,
            'vol_10d': vol_10d,
            'retail_sentiment': retail_sent,
            'rzjme_yi': rzjme_yi,
            'sentiment_divergence': sentiment_div,
            'behavior_momentum': behavior['momentum'],
            'flow_proxy': behavior['flow_proxy'],
            'acceleration': behavior['acceleration'],
            'crowding': behavior['crowding'],
            'withdrawal_risk': behavior['withdrawal_risk'],
            'early_entry': behavior['early_entry'],
            'news_surprise': news_surprise,
            'market_breadth': market_state['breadth'],
            'external_signal': round(external_signal, 4),
            'external_news_count': external_sent['count'],
            'news_price_gap': expectation_gap['news_price_gap'],
            'news_flow_gap': expectation_gap['news_flow_gap'],
            'share_flow_signal': share_flow_signal,
        })
    return pd.DataFrame(rows), T


# ----------------------------- 时序交叉验证 -----------------------------
def purged_walk_forward_splits(df, k=5, purge_days=PURGE_DAYS):
    """按决策日展开训练窗口，并在训练/验证之间清除重叠标签。"""
    dates = sorted(df['date'].unique())
    fold_size = max(1, len(dates) // k)
    for fold in range(1, k):
        test_start = fold * fold_size
        test_end = (fold + 1) * fold_size if fold < k - 1 else len(dates)
        train_end = max(0, test_start - purge_days)
        train_dates = dates[:train_end]
        test_dates = dates[test_start:test_end]
        if train_dates and test_dates:
            yield fold, train_dates, test_dates


def _fit_platt_calibrator(probabilities, targets):
    """只用已经发生的OOF结果拟合一维Platt校准；样本不足时保持原概率。"""
    probabilities = np.asarray(probabilities, dtype=float)
    targets = np.asarray(targets, dtype=int)
    if len(probabilities) < MIN_SELECTIVE_OBS or len(np.unique(targets)) < 2:
        return None
    p = np.clip(probabilities, 1e-6, 1 - 1e-6)
    logits = np.log(p / (1 - p)).reshape(-1, 1)
    calibrator = LogisticRegression(C=1.0, max_iter=2000)
    calibrator.fit(logits, targets)
    return calibrator


def _apply_calibrator(calibrator, probabilities):
    probabilities = np.asarray(probabilities, dtype=float)
    if calibrator is None:
        return probabilities
    p = np.clip(probabilities, 1e-6, 1 - 1e-6)
    logits = np.log(p / (1 - p)).reshape(-1, 1)
    return calibrator.predict_proba(logits)[:, 1]


def wilson_interval(wins, total, z=1.96):
    """二项比例Wilson 95%区间，避免小样本显示虚假精确度。"""
    if total <= 0:
        return [None, None]
    p = wins / total
    denominator = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denominator
    margin = z * np.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return [round(float(max(0, centre - margin)), 6), round(float(min(1, centre + margin)), 6)]


def simulate_selective_portfolio(frame, probabilities,
                                 threshold=HIGH_CONFIDENCE_THRESHOLD, top_k=3):
    """高置信日最多选3只，并锁定完整持有期，避免把重叠标签冒充独立交易。"""
    probabilities = np.asarray(probabilities, dtype=float)
    dates = sorted(frame['date'].unique())
    selected = np.zeros(len(frame), dtype=bool)
    trade_dates, portfolio_returns = [], []
    locked_until = -1
    frame_dates = frame['date'].to_numpy()
    returns = frame['target_return'].to_numpy(dtype=float)
    for date_index, decision_date in enumerate(dates):
        if date_index <= locked_until:
            continue
        positions = np.flatnonzero(frame_dates == decision_date)
        candidates = positions[probabilities[positions] >= threshold]
        if not len(candidates):
            continue
        picks = candidates[np.argsort(probabilities[candidates])[-top_k:]]
        selected[picks] = True
        trade_dates.append(decision_date)
        portfolio_returns.append(float(returns[picks].mean()))
        locked_until = date_index + HOLDING_PERIOD - 1
    return {
        'selected_mask': selected,
        'trade_dates': trade_dates,
        'portfolio_returns': np.asarray(portfolio_returns, dtype=float),
    }


def purged_logit_oof(df, features=PREDICTIVE_FEATURES):
    """严格前向Logit：日期分组、2日purge、仅用过去OOF结果做概率校准。"""
    oof_raw = np.full(len(df), np.nan)
    oof_prob = np.full(len(df), np.nan)
    baseline_prob = np.full(len(df), np.nan)
    fold_ids = np.full(len(df), np.nan)
    fold_metrics = []
    calibration_prob, calibration_y = [], []

    for fold, train_dates, test_dates in purged_walk_forward_splits(df):
        tr = df['date'].isin(train_dates)
        te = df['date'].isin(test_dates)
        Xtr = df.loc[tr, features].values.astype(float)
        ytr = df.loc[tr, 'target_direction'].values.astype(int)
        Xte = df.loc[te, features].values.astype(float)
        yte = df.loc[te, 'target_direction'].values.astype(int)
        scaler = StandardScaler()
        model = LogisticRegression(C=PREDICTIVE_C, max_iter=5000)
        model.fit(scaler.fit_transform(Xtr), ytr)
        raw = model.predict_proba(scaler.transform(Xte))[:, 1]
        calibrator = _fit_platt_calibrator(calibration_prob, calibration_y)
        prob = _apply_calibrator(calibrator, raw)
        base = float(ytr.mean())
        positions = np.flatnonzero(te.to_numpy())
        oof_raw[positions] = raw
        oof_prob[positions] = prob
        baseline_prob[positions] = base
        fold_ids[positions] = fold

        test_frame = df.loc[te]
        simulation = simulate_selective_portfolio(test_frame, prob)
        selected = simulation['selected_mask']
        selected_returns = test_frame['target_return'].to_numpy()[selected]
        portfolio_returns = simulation['portfolio_returns']
        fold_metrics.append({
            'fold': fold,
            'train_start': train_dates[0], 'train_end': train_dates[-1],
            'test_start': test_dates[0], 'test_end': test_dates[-1],
            'purge_days': PURGE_DAYS,
            'n_test_dates': len(test_dates), 'n_test_obs': int(len(yte)),
            'accuracy': round(float(((prob >= 0.5) == yte).mean()), 6),
            'baseline_accuracy': round(float(((base >= 0.5) == yte).mean()), 6),
            'brier': round(float(np.mean((prob - yte) ** 2)), 6),
            'baseline_brier': round(float(np.mean((base - yte) ** 2)), 6),
            'selected_count': int(selected.sum()),
            'selected_trade_dates': len(simulation['trade_dates']),
            'opportunity_precision': (round(float((selected_returns > 0).mean()), 6)
                                      if len(selected_returns) else None),
            'portfolio_win_rate': (round(float((portfolio_returns > 0).mean()), 6)
                                   if len(portfolio_returns) else None),
            'portfolio_mean_net_alpha': (round(float(portfolio_returns.mean()), 6)
                                         if len(portfolio_returns) else None),
        })
        calibration_prob.extend(raw.tolist())
        calibration_y.extend(yte.tolist())

    final_calibrator = _fit_platt_calibrator(oof_raw[~np.isnan(oof_raw)],
                                              df.loc[~np.isnan(oof_raw), 'target_direction'])
    return {
        'raw_probability': oof_raw,
        'probability': oof_prob,
        'baseline_probability': baseline_prob,
        'fold_ids': fold_ids,
        'fold_metrics': fold_metrics,
        'final_calibrator': final_calibrator,
    }


def time_series_cv(df, target, is_classifier=True, features=None):
    """带标签隔离的5折时序交叉验证，供OLS等诊断模型复用。"""
    features = features or FEATURES
    scores = []
    oof_pred = np.full(len(df), np.nan)
    for _, train_dates, test_dates in purged_walk_forward_splits(df):
        tr = df['date'].isin(train_dates)
        te = df['date'].isin(test_dates)
        if tr.sum() == 0 or te.sum() == 0:
            continue
        Xtr = df.loc[tr, features].values.astype(float)
        ytr = df.loc[tr, target].values
        Xte = df.loc[te, features].values.astype(float)
        yte = df.loc[te, target].values
        if is_classifier:
            scaler = StandardScaler()
            Xtr = scaler.fit_transform(Xtr)
            Xte = scaler.transform(Xte)
            m = LogisticRegression(C=PREDICTIVE_C, max_iter=5000)
            m.fit(Xtr, ytr)
            pred = m.predict(Xte)
            scores.append(float((pred == yte).mean()))
        else:
            from sklearn.linear_model import LinearRegression
            m = LinearRegression()
            m.fit(Xtr, ytr)
            pred = m.predict(Xte)
            ss_res = float(((yte - pred) ** 2).sum())
            ss_tot = float(((yte - yte.mean()) ** 2).sum())
            scores.append(1 - ss_res / ss_tot if ss_tot > 0 else 0.0)
        oof_pred[np.where(te.values)[0]] = pred
    return scores, oof_pred


# ----------------------------- 2. Logit 模型 -----------------------------
def run_logit_model(df, latest_df, latest_date):
    """预测未来3日成本后净Alpha，并以严格OOF结果决定是否有资格产生建议。"""
    X = df[PREDICTIVE_FEATURES].values.astype(float)
    y = df['target_direction'].values.astype(int)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    model = LogisticRegression(C=PREDICTIVE_C, max_iter=5000)
    model.fit(Xs, y)
    pred_prob = model.predict_proba(Xs)[:, 1]
    pred_dir = (pred_prob >= 0.5).astype(int)
    in_sample_accuracy = float((pred_dir == y).mean())
    pos_rate = float(y.mean())

    # 唯一用于能力判断的指标：按交易日分组、清除重叠标签、前向概率校准后的OOF结果。
    oof = purged_logit_oof(df)
    valid = ~np.isnan(oof['probability'])
    oof_prob = oof['probability'][valid]
    oof_base = oof['baseline_probability'][valid]
    oof_y = y[valid]
    oof_pred = (oof_prob >= 0.5).astype(int)
    cv_accuracy = float((oof_pred == oof_y).mean()) if len(oof_y) else 0.0
    baseline_accuracy = float(((oof_base >= 0.5) == oof_y).mean()) if len(oof_y) else 0.0
    brier = float(np.mean((oof_prob - oof_y) ** 2)) if len(oof_y) else 1.0
    baseline_brier = float(np.mean((oof_base - oof_y) ** 2)) if len(oof_y) else 1.0

    valid_frame = df.loc[valid]
    simulation = simulate_selective_portfolio(valid_frame, oof_prob)
    selected = simulation['selected_mask']
    selected_returns = valid_frame['target_return'].to_numpy()[selected]
    portfolio_returns = simulation['portfolio_returns']
    opportunity_wins = int((selected_returns > 0).sum())
    portfolio_wins = int((portfolio_returns > 0).sum())
    selected_count = int(len(selected_returns))
    trade_count = int(len(portfolio_returns))
    oof_dates = int(valid_frame['date'].nunique())
    positive_folds = sum(
        m['portfolio_mean_net_alpha'] is not None and m['portfolio_mean_net_alpha'] > 0
        for m in oof['fold_metrics'])
    selective = {
        'threshold': HIGH_CONFIDENCE_THRESHOLD,
        'top_k_per_date': 3,
        'holding_period_days': HOLDING_PERIOD,
        'selected_observations': selected_count,
        'trade_count': trade_count,
        'settled_trade_dates': simulation['trade_dates'],
        'oof_observations': int(len(valid_frame)),
        'oof_trade_dates': oof_dates,
        'observation_coverage': round(selected_count / len(valid_frame), 6) if len(valid_frame) else 0.0,
        'trade_date_coverage': round(trade_count / oof_dates, 6) if oof_dates else 0.0,
        'opportunity_precision': (round(opportunity_wins / selected_count, 6)
                                  if selected_count else None),
        'portfolio_win_rate': (round(portfolio_wins / trade_count, 6)
                               if trade_count else None),
        'portfolio_win_rate_ci_95': wilson_interval(portfolio_wins, trade_count),
        'mean_portfolio_net_alpha': (round(float(portfolio_returns.mean()), 6)
                                     if trade_count else None),
        # 兼容旧消费者；win_rate现在明确采用不重叠组合交易口径。
        'selected_count': selected_count,
        'selected_dates': trade_count,
        'oof_dates': oof_dates,
        'date_coverage': round(trade_count / oof_dates, 6) if oof_dates else 0.0,
        'win_rate': (round(portfolio_wins / trade_count, 6) if trade_count else None),
        'win_rate_ci_95': wilson_interval(portfolio_wins, trade_count),
        'mean_net_alpha': (round(float(portfolio_returns.mean()), 6)
                           if trade_count else None),
        'positive_alpha_folds': int(positive_folds),
        'n_folds': len(oof['fold_metrics']),
    }
    has_predictive_skill = bool(
        cv_accuracy > baseline_accuracy + 0.02 and brier < baseline_brier)
    gate_checks = {
        'beats_accuracy_baseline_by_2pp': cv_accuracy > baseline_accuracy + 0.02,
        'beats_brier_baseline': brier < baseline_brier,
        'minimum_40_settled_trade_dates': trade_count >= MIN_SELECTIVE_OBS,
        'positive_net_alpha_in_3_of_4_folds': (
            len(oof['fold_metrics']) >= 4 and positive_folds >= 3),
    }
    production_eligible = bool(all(gate_checks.values()))

    # L1仅作稀疏诊断；固定强正则，避免在同一历史样本上再次随机CV调参。
    diagnostic_X = df[FEATURES].values.astype(float)
    diagnostic_scaler = StandardScaler()
    diagnostic_Xs = diagnostic_scaler.fit_transform(diagnostic_X)
    cv_c = None
    sel_c = 0.1
    l1 = LogisticRegression(penalty='l1', solver='liblinear', C=sel_c, max_iter=5000)
    l1.fit(diagnostic_Xs, y)
    l1_coefs = l1.coef_[0]
    lasso_selection = sorted([
        {'feature': FEATURES[i], 'coef': round(float(l1_coefs[i]), 6),
         'selected': bool(abs(l1_coefs[i]) > 1e-6)}
        for i in range(len(FEATURES))
    ], key=lambda d: -abs(d['coef']))
    selected_features = [s['feature'] for s in lasso_selection if s['selected']]
    dropped_features = [s['feature'] for s in lasso_selection if not s['selected']]

    # 最新预测仍为shadow；只有全部样本外护栏通过后才允许产生正式建议。
    latest_X = latest_df[PREDICTIVE_FEATURES].values.astype(float)
    latest_raw_prob = model.predict_proba(scaler.transform(latest_X))[:, 1]
    latest_prob = _apply_calibrator(oof['final_calibrator'], latest_raw_prob)
    latest_pred_dir = (latest_prob >= 0.5).astype(int)

    latest_predictions = []
    for i, (_, row) in enumerate(latest_df.iterrows()):
        prob = float(latest_prob[i])
        if prob >= HIGH_CONFIDENCE_THRESHOLD:
            shadow_action, band = 'buy_candidate', 'high'
        elif prob <= LOW_CONFIDENCE_THRESHOLD:
            shadow_action, band = 'avoid', 'low'
        else:
            shadow_action, band = 'abstain', 'medium'
        latest_predictions.append({
            'etf_code': row['etf_code'], 'etf_name': row['etf_name'], 'sector': row['sector'],
            'prob_up': round(prob, 4),  # 兼容旧看板；语义已改为P(净Alpha>0)
            'prob_alpha_positive': round(prob, 4),
            'predicted_direction': 'up' if latest_pred_dir[i] == 1 else 'down',
            'confidence_band': band,
            'shadow_action': shadow_action,
            'production_action': shadow_action if production_eligible else 'diagnostic_only',
            'features': {f: row[f] for f in PREDICTIVE_FEATURES},
        })

    return {
        'model': 'Regularized Logit (purged walk-forward, 3-day net alpha)',
        'target': 'T开盘至T+2收盘ETF收益 - 同期沪深300收益 - 往返成本',
        'n_obs': int(len(df)),
        'feature_names': ['const'] + PREDICTIVE_FEATURES,
        'coefficients': ([{'feature': 'const', 'coef': round(float(model.intercept_[0]), 6), 'pvalue': None}]
                         + [{'feature': f, 'coef': round(float(model.coef_[0][i]), 6), 'pvalue': None}
                            for i, f in enumerate(PREDICTIVE_FEATURES)]),
        'pseudo_r2': None,
        'log_likelihood': None,
        'accuracy': round(cv_accuracy, 6),
        'in_sample_accuracy': round(in_sample_accuracy, 6),
        'accuracy_note': 'accuracy为日期分组、清除重叠标签并前向校准后的OOF准确率；样本内仅作诊断。',
        'baseline_accuracy': round(baseline_accuracy, 6),
        'accuracy_ci_95': wilson_interval(int((oof_pred == oof_y).sum()), len(oof_y)),
        'brier_score': round(brier, 6),
        'baseline_brier_score': round(baseline_brier, 6),
        'has_predictive_skill': has_predictive_skill,
        'production_eligible': production_eligible,
        'eligibility_checks': gate_checks,
        'selective_evaluation': selective,
        'positive_rate': round(pos_rate, 6),
        'time_series_cv': {
            'method': 'date-grouped expanding walk-forward with 2-day purge and forward Platt calibration',
            'n_folds': len(oof['fold_metrics']),
            'purge_days': PURGE_DAYS,
            'fold_scores': [m['accuracy'] for m in oof['fold_metrics']],
            'mean_cv_accuracy': round(cv_accuracy, 6),
            'fold_details': oof['fold_metrics'],
        },
        'lasso_variable_selection': lasso_selection,
        'selected_features': selected_features,
        'dropped_features': dropped_features,
        'lasso_cv_C': cv_c,
        'lasso_selection_C': round(sel_c, 6),
        'predictive_features': PREDICTIVE_FEATURES,
        'predictive_C': PREDICTIVE_C,
        'latest_predictions': latest_predictions,
        'latest_predict_date': latest_date,
        'in_sample_pred_direction': [int(p) for p in pred_dir],
        'oof_pred_direction': [None if not valid[i] else int(oof['probability'][i] >= 0.5)
                               for i in range(len(df))],
        'oof_pred_probability': [None if not valid[i] else round(float(oof['probability'][i]), 6)
                                 for i in range(len(df))],
    }


# ----------------------------- 3. OLS 模型 -----------------------------
def run_ols_model(df, latest_df, latest_date):
    """OLS仅作未来3日成本后净Alpha的线性诊断。"""
    X = df[FEATURES].values.astype(float)
    y = df['target_return'].values.astype(float)
    Xc = add_const(X)

    res = sm.OLS(y, Xc).fit(cov_type='cluster', cov_kwds={'groups': df['date']})
    feature_names = ['const'] + FEATURES
    params = res.params
    pvalues = res.pvalues
    coefs = [{'feature': feature_names[i],
              'coef': round(float(params[i]), 6),
              'pvalue': round(float(pvalues[i]), 6),
              'tvalue': round(float(res.tvalues[i]), 4)} for i in range(len(feature_names))]

    pred = res.predict(Xc)
    ss_res = float(((y - pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())

    # Lasso仅作稀疏诊断；固定alpha避免用随机折叠在同一时序样本上反复调参。
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    ys = (y - y.mean()) / (y.std() if y.std() > 0 else 1.0)
    alpha_sel = 0.02
    lasso = Lasso(alpha=alpha_sel, max_iter=50000)
    lasso.fit(Xs, ys)
    lasso_coefs = lasso.coef_
    lasso_selection = sorted([
        {'feature': FEATURES[i], 'coef': round(float(lasso_coefs[i]), 6),
         'selected': bool(abs(lasso_coefs[i]) > 1e-6)}
        for i in range(len(FEATURES))
    ], key=lambda d: -abs(d['coef']))
    selected_features = [s['feature'] for s in lasso_selection if s['selected']]
    dropped_features = [s['feature'] for s in lasso_selection if not s['selected']]

    # 因子重要性: 基于 Lasso 标准化系数 (L1 正则化缓解情绪类特征间的多重共线性, 系数符号更稳定)
    factor_importance = sorted([
        {'feature': FEATURES[i],
         'lasso_std_coef': round(float(lasso_coefs[i]), 6),
         'abs_importance': round(abs(float(lasso_coefs[i])), 6)}
        for i in range(len(FEATURES))
    ], key=lambda d: -d['abs_importance'])
    for rank, fi in enumerate(factor_importance, 1):
        fi['rank'] = rank

    # latest_predictions
    latest_X = latest_df[FEATURES].values.astype(float)
    latest_Xc = add_const(latest_X)
    latest_pred = res.predict(latest_Xc)
    latest_predictions = []
    for i, row in latest_df.iterrows():
        latest_predictions.append({
            'etf_code': row['etf_code'], 'etf_name': row['etf_name'], 'sector': row['sector'],
            'predicted_return_pct': round(float(latest_pred[i]), 4),  # 兼容旧字段
            'predicted_net_alpha_pct': round(float(latest_pred[i]), 4),
            'predicted_direction': 'up' if latest_pred[i] > 0 else 'down',
            'features': {f: row[f] for f in FEATURES},
        })

    # OLS 时序CV R² (补充)
    cv_scores, _ = time_series_cv(df, 'target_return', is_classifier=False)

    return {
        'model': 'OLS (3-day net alpha %, purged walk-forward)',
        'target': 'T开盘至T+2收盘ETF收益 - 同期沪深300收益 - 往返成本',
        'covariance': 'decision-date clustered standard errors',
        'n_obs': int(len(df)),
        'feature_names': feature_names,
        'coefficients': coefs,
        'r_squared': round(float(res.rsquared), 6),
        'adj_r_squared': round(float(res.rsquared_adj), 6),
        'f_statistic': round(float(res.fvalue), 6),
        'f_pvalue': round(float(res.f_pvalue), 6),
        'rmse': round(float(np.sqrt(ss_res / len(y))), 6),
        'time_series_cv_r2': {
            'n_folds': len(cv_scores),
            'fold_scores': [round(s, 6) for s in cv_scores],
            'mean_cv_r2': round(float(np.mean(cv_scores)), 6) if cv_scores else 0.0,
        },
        'lasso_variable_selection': lasso_selection,
        'selected_features': selected_features,
        'dropped_features': dropped_features,
        'lasso_cv_alpha': None,
        'lasso_selection_alpha': round(float(alpha_sel), 6),
        'factor_importance': factor_importance,
        'latest_predictions': latest_predictions,
        'latest_predict_date': latest_date,
        'in_sample_pred_return': [round(float(p), 4) for p in pred],
    }


# ----------------------------- 4. 规则模型 vs Logit 一致性 -----------------------------
def cross_validate_models(df, logit_result, rule_result):
    """比较规则买入与Logit高置信净Alpha信号，忽略无交易日期和双重未买入。"""
    if not rule_result:
        return {'status': '规则模型结果为空', 'agreement_rate': None}

    rule_bought_map = {
        d['date']: set(d.get('etf_names', []))
        for d in rule_result.get('all_daily_summaries', [])}
    logit_pred = logit_result.get('oof_pred_direction', [])
    logit_prob = logit_result.get('oof_pred_probability', [])
    if len(logit_pred) != len(df):
        return {'status': 'Logit预测与面板行数不匹配', 'agreement_rate': None}

    union_count = overlap = rule_buy_count = high_signal_count = 0
    for idx, (_, row) in enumerate(df.iterrows()):
        date = row['date']
        if date not in rule_bought_map or logit_pred[idx] is None:
            continue
        rule_buy = row['etf_name'] in rule_bought_map[date]
        probability = logit_prob[idx] if len(logit_prob) == len(df) else None
        high_signal = (probability >= HIGH_CONFIDENCE_THRESHOLD
                       if probability is not None else logit_pred[idx] == 1)
        rule_buy_count += int(rule_buy)
        high_signal_count += int(high_signal)
        if rule_buy or high_signal:
            union_count += 1
            overlap += int(rule_buy and high_signal)

    rule_overlap = overlap / rule_buy_count if rule_buy_count else 0.0
    high_overlap = overlap / high_signal_count if high_signal_count else 0.0

    return {
        'n_compared': union_count,
        'rule_buy_count': rule_buy_count,
        'logit_high_confidence_count': high_signal_count,
        'overlap_count': overlap,
        'agreement_rate': round(overlap / union_count, 6) if union_count else 0.0,
        'rule_buy_overlap_rate': round(rule_overlap, 6),
        'logit_signal_overlap_rate': round(high_overlap, 6),
        'directional_consistency': round(rule_overlap, 6),
        'interpretation': (
            f"规则买入与Logit高置信净Alpha信号交集 {overlap} 个；"
            f"覆盖规则买入 {rule_overlap:.1%}，覆盖Logit高置信信号 {high_overlap:.1%}。"
            if union_count else '无可比较的高置信信号'
        ),
    }


# ----------------------------- 主流程 -----------------------------
def main():
    etf_data = load_json(ETF_HISTORY_PATH)
    news_data = load_json(NEWSPAPERS_PATH)

    # 直接运行规则模型, 获取其结果用于一致性比较 (同时刷新 model_results.json)
    from etf_model_run import run_model as run_rule_model
    rule_result = run_rule_model()

    df = build_dataset(etf_data, news_data)
    latest_df, latest_date = build_latest_features(etf_data, news_data)

    logit_result = run_logit_model(df, latest_df, latest_date)
    ols_result = run_ols_model(df, latest_df, latest_date)
    cv_result = cross_validate_models(df, logit_result, rule_result)

    def coverage(dates):
        dates = sorted(set(d for d in dates if d))
        return {'start': dates[0] if dates else None, 'end': dates[-1] if dates else None,
                'n_dates': len(dates)}

    margin_dates = load_margin_data().keys()
    external_dates = [x.get('published_at', '')[:10] for x in load_external_news()]
    share_dates = load_share_history().keys()
    news_dates = [d for d, papers in news_data.items() if papers and any(papers.values())]

    # 数据集描述
    desc = {
        'n_obs': int(len(df)),
        'n_etfs': int(df['etf_code'].nunique()),
        'n_dates': int(df['date'].nunique()),
        'date_range': [df['date'].min(), df['date'].max()],
        'features': FEATURES,
        'targets': ['target_return', 'target_direction'],
        'target_definition': 'ETF T开盘至T+2收盘收益 - 沪深300同期收益 - 0.05%往返成本',
        'benchmark_code': HS300_CODE,
        'holding_period_days': HOLDING_PERIOD,
        'purge_days': PURGE_DAYS,
        'round_trip_cost_rate': round(2 * (COMMISSION_RATE + SLIPPAGE_RATE), 6),
        'lookahead_note': ('价格/成交、两融、无精确时刻的外部事件仅用T-1及更早数据；'
                           '当日四大报须开盘前可得；目标为T开盘至T+2收盘成本后相对Alpha。'),
        'source_coverage': {
            'prices': coverage(df['date'].unique()),
            'newspapers': coverage(news_dates),
            'margin': coverage(margin_dates),
            'external_news': coverage(external_dates),
            'etf_shares': coverage(share_dates),
            'missing_policy': '缺失源当前按中性值0处理；评估时必须结合覆盖区间，不把缺失误解为真实中性。',
        },
        'target_direction_balance': {
            'positive': int((df['target_direction'] == 1).sum()),
            'non_positive': int((df['target_direction'] == 0).sum()),
            'positive_rate': round(float(df['target_direction'].mean()), 4),
        },
        'feature_stats': {
            f: {'mean': round(float(df[f].mean()), 4), 'std': round(float(df[f].std()), 4),
                'min': round(float(df[f].min()), 4), 'max': round(float(df[f].max()), 4)}
            for f in FEATURES
        },
    }

    result = {
        'dataset_info': desc,
        'logit_model': logit_result,
        'ols_model': ols_result,
        'cross_validation': cv_result,
    }

    save_json(OUTPUT_PATH, result)
    return result


if __name__ == '__main__':
    res = main()
    print('=' * 60)
    print('ETF计量模型运行完成')
    print('=' * 60)
    di = res['dataset_info']
    print(f"面板观测: {di['n_obs']}  ETF数: {di['n_etfs']}  日期数: {di['n_dates']}")
    print(f"日期范围: {di['date_range'][0]} ~ {di['date_range'][1]}")
    balance = di['target_direction_balance']
    print(f"净Alpha标签: 正{balance['positive']}/非正{balance['non_positive']} "
          f"(正Alpha率{balance['positive_rate']:.1%})")
    lm = res['logit_model']
    print(f"\n[Logit] 伪R²={lm['pseudo_r2']}  准确率={lm['accuracy']:.4f}  "
          f"时序CV均值={lm['time_series_cv']['mean_cv_accuracy']:.4f}")
    print(f"  Lasso入选特征: {lm['selected_features']}")
    om = res['ols_model']
    print(f"\n[OLS] R²={om['r_squared']}  调整R²={om['adj_r_squared']}  "
          f"F={om['f_statistic']}(p={om['f_pvalue']})  RMSE={om['rmse']}")
    print(f"  Lasso入选特征: {om['selected_features']}")
    print(f"  因子重要性Top3: {[f['feature'] for f in om['factor_importance'][:3]]}")
    cv = res['cross_validation']
    if cv.get('agreement_rate') is not None:
        print(f"\n[一致性] 规则vsLogit一致率={cv['agreement_rate']:.2%}  "
              f"方向一致性={cv['directional_consistency']:.2%}")
    print(f"\n最新预测日: {lm['latest_predict_date']}")
    print(f"  Logit看涨: {[p['etf_name'] for p in lm['latest_predictions'] if p['predicted_direction']=='up']}")
    print(f"  OLS看涨: {[p['etf_name'] for p in om['latest_predictions'] if p['predicted_direction']=='up']}")
    print(f"\n结果已保存: {OUTPUT_PATH}")
