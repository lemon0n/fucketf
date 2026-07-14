#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETF计量模型 — 在规则模型基础上构建面板数据，运行 Logit / OLS / Lasso 回归

面板结构: 每行 = 一个 (ETF, 交易日) 观测
规避 look-ahead bias:
  * 价格类特征统一使用【前一日 T-1】数据 (prev_change_pct / prev_volume_ratio / prev_intraday_return)
  * 情绪类特征使用【当日 T】四大报 (晨报在开盘前可得，不构成偷看)
  * 目标 today_return / today_direction 为【当日 T】日内收益(开盘->收盘)
  => 所有特征在 T 开盘前均已知

输出: data/econometric_results.json
"""
import json
import os
import warnings

import numpy as np
import pandas as pd
import statsmodels.api as sm
from sklearn.linear_model import LassoCV, LogisticRegression, LogisticRegressionCV
from sklearn.preprocessing import StandardScaler

# 复用规则模型中的常量与基础工具 (避免重复定义)
from etf_model_run import (
    SECTOR_ETF_MAP, HS300_CODE, ETF_HISTORY_PATH, NEWSPAPERS_PATH,
    load_json, get_trading_days, find_record, get_index, get_prev_date,
    compute_volume_ratio, analyze_newspaper_sentiment,
)

warnings.filterwarnings('ignore')

OUTPUT_PATH = os.path.join(os.path.dirname(ETF_HISTORY_PATH), 'econometric_results.json')
MODEL_RESULTS_PATH = os.path.join(os.path.dirname(ETF_HISTORY_PATH), 'model_results.json')

# 特征列 (全部为 T 开盘前可知)
FEATURES = [
    'sentiment_score', 'bullish_count', 'bearish_count',
    'prev_change_pct', 'prev_volume_ratio', 'prev_intraday_return',
    'sector_mentioned', 'sector_mention_count',
]


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


# ----------------------------- 1. 构建面板数据 -----------------------------
def build_dataset(etf_data, news_data):
    """
    构建面板数据: 每行一个 ETF-日期观测。
    特征用前一日数据(价格类) + 当日四大报(情绪类), 目标为当日日内收益。
    """
    trading_days = get_trading_days(etf_data)
    rows = []
    for i in range(2, len(trading_days)):  # 需要 T-1 与 T-2
        T = trading_days[i]
        Tm1 = trading_days[i - 1]
        Tm2 = trading_days[i - 2]

        # 当日四大报情绪 (开盘前可得)
        news_T = news_data.get(T, {})
        sent = analyze_newspaper_sentiment(news_T)

        # 各板块当日提及情况
        mention = {code: sector_mention_count(news_T, info) for code, info in SECTOR_ETF_MAP.items()}

        for code, info in SECTOR_ETF_MAP.items():
            rec_T = find_record(etf_data, code, T)
            rec_Tm1 = find_record(etf_data, code, Tm1)
            rec_Tm2 = find_record(etf_data, code, Tm2)
            if not (rec_T and rec_Tm1 and rec_Tm2):
                continue
            if not (rec_T['open'] and rec_Tm1['open'] and rec_Tm2['close']):
                continue

            # 目标: 当日日内收益(开盘->收盘)
            today_return = (rec_T['close'] - rec_T['open']) / rec_T['open'] * 100
            today_direction = 1 if today_return > 0 else 0

            # 前一日价格特征
            prev_change_pct = (rec_Tm1['close'] - rec_Tm2['close']) / rec_Tm2['close'] * 100
            prev_volume_ratio = compute_volume_ratio(etf_data, code, Tm1)
            prev_intraday_return = (rec_Tm1['close'] - rec_Tm1['open']) / rec_Tm1['open'] * 100

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
                'today_return': round(today_return, 4),
                'today_direction': int(today_direction),
            })

    df = pd.DataFrame(rows)
    return df


def build_latest_features(etf_data, news_data):
    """构建最新一日(最新四大报日)11个ETF的特征行, 用于 latest_predictions"""
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

    rows = []
    for code, info in SECTOR_ETF_MAP.items():
        rec_Tm1 = find_record(etf_data, code, Tm1)
        rec_Tm2 = find_record(etf_data, code, Tm2) if Tm2 else None
        if not (rec_Tm1 and rec_Tm2):
            continue
        prev_change_pct = (rec_Tm1['close'] - rec_Tm2['close']) / rec_Tm2['close'] * 100
        prev_volume_ratio = compute_volume_ratio(etf_data, code, Tm1)
        prev_intraday_return = (rec_Tm1['close'] - rec_Tm1['open']) / rec_Tm1['open'] * 100
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
        })
    return pd.DataFrame(rows), T


# ----------------------------- 时序交叉验证 -----------------------------
def time_series_cv(df, target, is_classifier=True):
    """5折时序交叉验证 (expanding window), 返回各折准确率/R² 与样本外预测"""
    dates = sorted(df['date'].unique())
    n = len(dates)
    k = 5
    fold_size = max(1, n // k)
    scores = []
    oof_pred = np.full(len(df), np.nan)
    for f in range(1, k):
        train_dates = dates[: f * fold_size]
        if f < k - 1:
            test_dates = dates[f * fold_size: (f + 1) * fold_size]
        else:
            test_dates = dates[f * fold_size:]
        tr = df['date'].isin(train_dates)
        te = df['date'].isin(test_dates)
        if tr.sum() == 0 or te.sum() == 0:
            continue
        Xtr = df.loc[tr, FEATURES].values.astype(float)
        ytr = df.loc[tr, target].values
        Xte = df.loc[te, FEATURES].values.astype(float)
        yte = df.loc[te, target].values
        if is_classifier:
            m = LogisticRegression(max_iter=2000)
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
    """Logit 回归预测涨跌方向"""
    X = df[FEATURES].values.astype(float)
    y = df['today_direction'].values.astype(int)
    Xc = add_const(X)

    res = None
    for method in (None, 'bfgs', 'lbfgs', 'powell'):
        try:
            if method is None:
                res = sm.Logit(y, Xc).fit(disp=False, maxiter=500)
            else:
                res = sm.Logit(y, Xc).fit(disp=False, maxiter=500, method=method)
            if res.mle_retvals.get('converged', True):
                break
        except Exception:
            res = None
            continue

    feature_names = ['const'] + FEATURES
    if res is not None:
        params = res.params
        pvalues = res.pvalues
        pseudo_r2 = float(res.prsquared)
        llf = float(res.llf)
        pred_prob = res.predict(Xc)
        pred_dir = (pred_prob > 0.5).astype(int)
        coefs = [{'feature': feature_names[i],
                  'coef': round(float(params[i]), 6),
                  'pvalue': round(float(pvalues[i]), 6)} for i in range(len(feature_names))]
    else:
        # 回退到 sklearn
        m = LogisticRegression(maxiter=2000)
        m.fit(X, y)
        pred_prob = m.predict_proba(X)[:, 1]
        pred_dir = (pred_prob > 0.5).astype(int)
        pseudo_r2 = 0.0
        llf = 0.0
        coefs = [{'feature': feature_names[0], 'coef': round(float(m.intercept_[0]), 6), 'pvalue': None}]
        coefs += [{'feature': FEATURES[i], 'coef': round(float(m.coef_[0][i]), 6), 'pvalue': None}
                  for i in range(len(FEATURES))]

    accuracy = float((pred_dir == y).mean())
    pos_rate = float(y.mean())

    # 5折时序交叉验证
    cv_scores, oof_pred = time_series_cv(df, 'today_direction', is_classifier=True)
    cv_mean = float(np.mean(cv_scores)) if cv_scores else 0.0

    # Lasso (L1) 变量选择: 先用 LogisticRegressionCV 选 C, 再用更小 C (更强正则) 做筛选
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    cv_c = None
    try:
        l1cv = LogisticRegressionCV(Cs=10, penalty='l1', solver='liblinear', cv=5, max_iter=5000)
        l1cv.fit(Xs, y)
        cv_c = float(l1cv.C_[0])
    except Exception:
        cv_c = 1.0
    sel_c = max(cv_c / 3.0, 1e-3)  # 更强正则化以剔除弱变量
    l1 = LogisticRegression(penalty='l1', solver='liblinear', C=sel_c, max_iter=5000)
    l1.fit(Xs, y)
    l1_coefs = l1.coef_[0]
    lasso_selection = sorted([
        {'feature': FEATURES[i], 'coef': round(float(l1_coefs[i]), 6),
         'selected': bool(abs(l1_coefs[i]) > 1e-6)}
        for i in range(len(FEATURES))
    ], key=lambda d: -abs(d['coef']))
    selected_features = [s['feature'] for s in lasso_selection if s['selected']]
    dropped_features = [s['feature'] for s in lasso_selection if not s['selected']]

    # latest_predictions: 11个ETF今日预测
    latest_X = latest_df[FEATURES].values.astype(float)
    latest_Xc = add_const(latest_X) if res is not None else latest_X
    if res is not None:
        latest_prob = res.predict(latest_Xc)
    else:
        latest_prob = l1.predict_proba(scaler.transform(latest_X))[:, 1]
    latest_pred_dir = (latest_prob > 0.5).astype(int)

    latest_predictions = []
    for i, row in latest_df.iterrows():
        latest_predictions.append({
            'etf_code': row['etf_code'], 'etf_name': row['etf_name'], 'sector': row['sector'],
            'prob_up': round(float(latest_prob[i]), 4),
            'predicted_direction': 'up' if latest_pred_dir[i] == 1 else 'down',
            'features': {f: row[f] for f in FEATURES},
        })

    return {
        'model': 'Logit (Binary: today_direction)',
        'n_obs': int(len(df)),
        'feature_names': feature_names,
        'coefficients': coefs,
        'pseudo_r2': round(pseudo_r2, 6),
        'log_likelihood': round(llf, 4),
        'accuracy': round(accuracy, 6),
        'positive_rate': round(pos_rate, 6),
        'time_series_cv': {
            'n_folds': len(cv_scores),
            'fold_scores': [round(s, 6) for s in cv_scores],
            'mean_cv_accuracy': round(cv_mean, 6),
        },
        'lasso_variable_selection': lasso_selection,
        'selected_features': selected_features,
        'dropped_features': dropped_features,
        'lasso_cv_C': round(cv_c, 6),
        'lasso_selection_C': round(sel_c, 6),
        'latest_predictions': latest_predictions,
        'latest_predict_date': latest_date,
        'in_sample_pred_direction': [int(p) for p in pred_dir],
        'oof_pred_direction': [None if np.isnan(p) else int(p) for p in oof_pred],
    }


# ----------------------------- 3. OLS 模型 -----------------------------
def run_ols_model(df, latest_df, latest_date):
    """OLS 回归预测收益率"""
    X = df[FEATURES].values.astype(float)
    y = df['today_return'].values.astype(float)
    Xc = add_const(X)

    res = sm.OLS(y, Xc).fit()
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

    # Lasso 变量选择 + 因子重要性 (标准化 X 与 y; 用更保守的正则化做筛选)
    scaler = StandardScaler()
    Xs = scaler.fit_transform(X)
    ys = (y - y.mean()) / (y.std() if y.std() > 0 else 1.0)
    lasso_cv = LassoCV(cv=5, max_iter=50000, n_alphas=200)
    lasso_cv.fit(Xs, ys)
    # 变量筛选采用 CV 最优 alpha 的 3 倍 (更保守), 剔除弱信号变量
    from sklearn.linear_model import Lasso
    alpha_sel = max(lasso_cv.alpha_ * 3, 1e-4)
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
            'predicted_return_pct': round(float(latest_pred[i]), 4),
            'predicted_direction': 'up' if latest_pred[i] > 0 else 'down',
            'features': {f: row[f] for f in FEATURES},
        })

    # OLS 时序CV R² (补充)
    cv_scores, _ = time_series_cv(df, 'today_return', is_classifier=False)

    return {
        'model': 'OLS (today_return %)',
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
        'lasso_cv_alpha': round(float(lasso_cv.alpha_), 6),
        'lasso_selection_alpha': round(float(alpha_sel), 6),
        'factor_importance': factor_importance,
        'latest_predictions': latest_predictions,
        'latest_predict_date': latest_date,
        'in_sample_pred_return': [round(float(p), 4) for p in pred],
    }


# ----------------------------- 4. 规则模型 vs Logit 一致性 -----------------------------
def cross_validate_models(df, logit_result, rule_result):
    """规则模型 vs Logit 一致性比较 (直接传入规则模型结果, 避免依赖外部文件格式)"""
    agreement_total = 0
    compared = 0
    bought = 0
    bought_logit_up = 0
    notbought = 0
    notbought_logit_up = 0

    rule = rule_result
    if not rule:
        return {'status': '规则模型结果为空', 'agreement_rate': None}

    # 当日规则模型买入的ETF集合 {date: set(etf_name)}
    rule_bought_map = {}
    for d in rule.get('all_daily_summaries', []):
        rule_bought_map[d['date']] = set(d.get('etf_names', []))

    logit_pred = logit_result.get('in_sample_pred_direction', [])
    if len(logit_pred) != len(df):
        return {'status': 'Logit预测与面板行数不匹配', 'agreement_rate': None}

    # 逐行比较
    per_day = {}  # date -> {rule_trend, logit_up_frac, n}
    for idx, (_, row) in enumerate(df.iterrows()):
        date = row['date']
        etf_name = row['etf_name']
        logit_up = (logit_pred[idx] == 1)
        rb = etf_name in rule_bought_map.get(date, set())

        # 一致性: 规则买入<->Logit看涨 ; 规则未买<->Logit看跌
        agree = (rb and logit_up) or ((not rb) and (not logit_up))
        agreement_total += int(agree)
        compared += 1
        if rb:
            bought += 1
            if logit_up:
                bought_logit_up += 1
        else:
            notbought += 1
            if logit_up:
                notbought_logit_up += 1

        pd_day = per_day.setdefault(date, {'rule_buys': 0, 'logit_ups': 0, 'n': 0,
                                           'rule_trend': rule_bought_map.get(date, set())})
        pd_day['n'] += 1
        if rb:
            pd_day['rule_buys'] += 1
        if logit_up:
            pd_day['logit_ups'] += 1

    # 趋势层面一致性: 规则趋势 vs Logit看涨比例
    trend_map = {d['date']: d.get('trend') for d in rule.get('all_daily_summaries', [])}
    trend_agree = 0
    trend_compared = 0
    for date, info in per_day.items():
        if info['n'] == 0:
            continue
        up_frac = info['logit_ups'] / info['n']
        rt = trend_map.get(date)
        if rt is None:
            continue
        trend_compared += 1
        if rt == 'bullish' and up_frac > 0.5:
            trend_agree += 1
        elif rt == 'bearish' and up_frac < 0.5:
            trend_agree += 1
        elif rt == 'neutral' and 0.4 <= up_frac <= 0.6:
            trend_agree += 1

    bought_up_rate = bought_logit_up / bought if bought > 0 else 0.0
    notbought_up_rate = notbought_logit_up / notbought if notbought > 0 else 0.0

    return {
        'n_compared': compared,
        'rule_buy_count': bought,
        'rule_notbuy_count': notbought,
        'agreement_rate': round(agreement_total / compared, 6) if compared else 0.0,
        'bought_logit_up_rate': round(bought_up_rate, 6),
        'notbought_logit_up_rate': round(notbought_up_rate, 6),
        'directional_consistency': round(bought_up_rate - notbought_up_rate, 6),
        'trend_level_agreement': round(trend_agree / trend_compared, 6) if trend_compared else 0.0,
        'trend_compared_days': trend_compared,
        'interpretation': (
            f"规则模型买入的ETF中Logit看涨比例 {bought_up_rate:.1%}，"
            f"未买入的 {notbought_up_rate:.1%}，方向一致性差 "
            f"{bought_up_rate - notbought_up_rate:.1%}。"
            f"逐ETF-日整体一致率 {agreement_total / compared:.1%}。"
            if compared else '无比较数据'
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

    # 数据集描述
    desc = {
        'n_obs': int(len(df)),
        'n_etfs': int(df['etf_code'].nunique()),
        'n_dates': int(df['date'].nunique()),
        'date_range': [df['date'].min(), df['date'].max()],
        'features': FEATURES,
        'targets': ['today_return', 'today_direction'],
        'lookahead_note': '价格特征用前一日T-1数据; 情绪特征用当日T四大报(开盘前可得); 目标为当日T日内收益',
        'today_direction_balance': {
            'up': int((df['today_direction'] == 1).sum()),
            'down': int((df['today_direction'] == 0).sum()),
            'up_rate': round(float(df['today_direction'].mean()), 4),
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
    print(f"涨跌平衡: 涨{di['today_direction_balance']['up']}/跌{di['today_direction_balance']['down']} "
          f"(涨率{di['today_direction_balance']['up_rate']:.1%})")
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
