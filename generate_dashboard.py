#!/usr/bin/env python3
"""
ETF预测模型看板生成脚本
================================
读取 model_results.json 和 econometric_results.json，
生成 HTML 看板 (dashboard.html) 和 图表JS (assets/charts.js)。

数据来源:
  data/model_results.json       — 规则模型输出
  data/econometric_results.json — 计量模型输出

输出:
  etf-dashboard/dashboard.html   — 单页滚动看板
  etf-dashboard/assets/charts.js — ECharts 图表代码 (外部文件)
"""

import json
import os
import html
from datetime import datetime
from zoneinfo import ZoneInfo

from etf_model_run import BUY_THRESHOLD, HOLDING_PERIOD

# ============================================================
#  路径配置
# ============================================================
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR     = os.path.join(SCRIPT_DIR, 'data')
DASHBOARD_DIR = os.path.join(SCRIPT_DIR, 'dashboard')

MODEL_RESULTS_PATH  = os.path.join(DATA_DIR, 'model_results.json')
ECON_RESULTS_PATH   = os.path.join(DATA_DIR, 'econometric_results.json')
DIAGNOSTICS_PATH    = os.path.join(DATA_DIR, 'market_diagnostics.json')
EXTERNAL_NEWS_PATH  = os.path.join(DATA_DIR, 'external_news.json')
HANDOFF_PATH        = os.path.join(DATA_DIR, 'next_day_handoff.json')
HTML_OUT            = os.path.join(DASHBOARD_DIR, 'dashboard.html')
CHARTS_JS_OUT       = os.path.join(DASHBOARD_DIR, 'assets', 'charts.js')
ECHARTS_JS_REF      = '_shared/js/echarts.min.js'
WITHDRAWAL_WATCH_THRESHOLD = 0.35

# ============================================================
#  变量说明字典
# ============================================================
FACTOR_DESC = {
    'sentiment_score':      '媒体叙事净分（有方向标题÷去重标题总数）',
    'bullish_count':        '看涨关键词出现次数',
    'bearish_count':        '看跌关键词出现次数',
    'prev_change_pct':      '前日涨跌幅%',
    'prev_volume_ratio':    '前日量比（今日量/前5日均量）',
    'prev_intraday_return': '前日日内收益率%（开盘→收盘）',
    'sector_mentioned':     '板块是否被报纸提及（0/1）',
    'sector_mention_count': '板块被提及次数',
    'hs300_mom_5d':         '沪深300 5日动量（近5日涨跌幅%）',
    'vol_10d':              '10日波动率%（近10日收益率标准差）',
    'retail_sentiment':     '大众情绪综合分（融资融券z-score加权, [-1,1]）',
    'rzjme_yi':             '融资净买入额（亿元）',
    'sentiment_divergence': '媒体叙事与融资情绪的绝对分歧度',
    'const':                '常数项/截距',
}

# 公式中使用的变量简称
VAR_SHORT = {
    'const':                '',
    'sentiment_score':      'S',
    'bullish_count':        'B',
    'bearish_count':        'D',
    'prev_change_pct':      'P',
    'prev_volume_ratio':    'VR',
    'prev_intraday_return': 'I',
    'sector_mentioned':     'M',
    'sector_mention_count': 'C',
    'hs300_mom_5d':         'M5',
    'vol_10d':              'V10',
    'retail_sentiment':     'RS',
    'rzjme_yi':             'RZ',
    'sentiment_divergence': 'DIV',
}

# ============================================================
#  辅助函数
# ============================================================
def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def esc(text):
    """HTML 转义"""
    if text is None:
        return ''
    return html.escape(str(text))


def fmt_pct(v, sign=True):
    """3.64 -> '+3.64%'  /  -1.21 -> '-1.21%'"""
    if v is None:
        return 'N/A'
    s = '+' if sign and v >= 0 else ''
    return f'{s}{v:.2f}%'


def fmt_coef(v, decimals=4):
    """0.4529 -> '+0.4529'  /  -0.3271 -> '-0.3271'"""
    if v is None:
        return 'N/A'
    s = '+' if v >= 0 else ''
    return f'{s}{v:.{decimals}f}'


def fmt_num(v, decimals=4):
    """0.4288 -> '0.4288' (无符号)"""
    if v is None:
        return 'N/A'
    return f'{v:.{decimals}f}'


def cls_val(v):
    """根据正负返回 CSS 类名 up / down"""
    if v is None:
        return ''
    return 'up' if v >= 0 else 'down'


def trend_tag(trend):
    """趋势标签 HTML"""
    tag_map = {'看涨': 't-bull', '看跌': 't-bear', '震荡': 't-neutral'}
    cls = tag_map.get(trend, 't-neutral')
    return f'<span class="tag {cls}">{esc(trend)}</span>'


def js_arr(lst):
    """Python 列表 -> JavaScript 数组字面量"""
    return json.dumps(lst, ensure_ascii=False)


def fmt_money(v):
    """1000000 -> '1,000,000'"""
    return f'{v:,}'


# ============================================================
#  数据标准化（适配实际JSON数据结构）
# ============================================================
TREND_MAP = {'bullish': '看涨', 'bearish': '看跌', 'neutral': '震荡'}


def _sig_stars(p):
    """p值 → 显著性星号"""
    if p is None:
        return ''
    if p < 0.01:
        return '***'
    if p < 0.05:
        return '**'
    if p < 0.1:
        return '*'
    return ''


def _calc_etf_performance(experiences):
    """从经验记录计算各ETF的推荐绩效"""
    from collections import defaultdict
    stats = defaultdict(lambda: {'rec_count': 0, 'returns': [], 'wins': 0})
    for e in experiences:
        name = e['etf_name']
        stats[name]['rec_count'] += 1
        ret = e.get('net_return', 0) * 100
        stats[name]['returns'].append(ret)
        if e.get('result') == 'win':
            stats[name]['wins'] += 1
    result = []
    for name, s in sorted(stats.items(), key=lambda x: -x[1]['rec_count']):
        avg_ret = sum(s['returns']) / len(s['returns']) if s['returns'] else 0
        wr = s['wins'] / s['rec_count'] * 100 if s['rec_count'] > 0 else 0
        if avg_ret > 0.5 and wr >= 60:
            assessment = '优秀'
        elif avg_ret > 0:
            assessment = '良好'
        elif wr >= 40:
            assessment = '一般'
        else:
            assessment = '较差'
        result.append({
            'name': name, 'rec_count': s['rec_count'],
            'avg_return': avg_ret, 'win_rate': wr, 'assessment': assessment,
        })
    return result


def _build_chart_data(raw, daily):
    """从 all_daily_summaries 构建图表数据"""
    from collections import defaultdict, OrderedDict

    # 累计收益率走势
    dates, cum_model, cum_hs300 = [], [], []
    mc, hc = 0, 0
    for d in daily:
        dates.append(d['date'][5:])
        mc += d.get('return', 0)
        hc += d.get('hs300', 0)
        cum_model.append(round(mc, 2))
        cum_hs300.append(round(hc, 2))

    # 月度收益对比
    m_model, m_hs300 = OrderedDict(), OrderedDict()
    for d in daily:
        month = d['date'][:7]
        m_model[month] = m_model.get(month, 0) + d.get('return', 0)
        m_hs300[month] = m_hs300.get(month, 0) + d.get('hs300', 0)
    months = [m[5:] for m in m_model]
    mv_model = [round(m_model[m], 2) for m in m_model]
    mv_hs300 = [round(m_hs300[m], 2) for m in m_hs300]

    # ETF 胜率分布
    etf_stats = defaultdict(lambda: {'rec': 0, 'win': 0})
    for e in raw.get('experiences', []):
        nm = e['etf_name']
        etf_stats[nm]['rec'] += 1
        if e.get('result') == 'win':
            etf_stats[nm]['win'] += 1
    etf_names, etf_values = [], []
    for nm in sorted(etf_stats):
        s = etf_stats[nm]
        wr = s['win'] / s['rec'] * 100 if s['rec'] > 0 else 0
        etf_names.append(nm)
        etf_values.append(round(wr, 1))

    # 近15日每日收益对比
    rec = daily[-15:] if len(daily) >= 15 else daily
    rec_dates = [d['date'][5:] for d in rec]
    rec_model = [round(d.get('return', 0), 2) for d in rec]
    rec_hs300 = [round(d.get('hs300', 0), 2) for d in rec]

    return {
        'cumulative': {'dates': dates, 'model': cum_model, 'hs300': cum_hs300},
        'monthly': {'months': months, 'model': mv_model, 'hs300': mv_hs300},
        'etf_winrate': {'names': etf_names, 'values': etf_values},
        'recent': {'dates': rec_dates, 'model': rec_model, 'hs300': rec_hs300},
    }


def _build_market_review(raw):
    """构建市场回顾数据"""
    ld = raw['latest_decision']
    sent = ld.get('sentiment', {})
    sp = ld.get('sector_performance', {})
    daily = raw.get('all_daily_summaries', [])
    last = daily[-1] if daily else {}
    gainers = sp.get('top5', [])[:3]
    losers = sp.get('bottom5', [])[:3]
    return {
        'hs300_prev_return': last.get('hs300', 0),
        'sentiment_score': sent.get('score', 0),
        'bullish_count': sent.get('bullish_count', 0),
        'bearish_count': sent.get('bearish_count', 0),
        'judgment': sent.get('summary', ''),
        'gainers': [{'name': g['name'], 'return': g.get('change_pct', 0)} for g in gainers],
        'losers': [{'name': l['name'], 'return': l.get('change_pct', 0)} for l in losers],
    }


def _build_weekly_performance(daily):
    """构建本周表现（最近5个交易日）"""
    if not daily:
        return {'trading_days': 0, 'model_return': 0, 'hs300_return': 0, 'alpha': 0, 'wins': 0, 'total': 0}
    week = daily[-5:]
    mr = sum(d.get('return', 0) for d in week)
    hr = sum(d.get('hs300', 0) for d in week)
    wins = sum(1 for d in week if d.get('return', 0) > 0)
    return {'trading_days': len(week), 'model_return': mr, 'hs300_return': hr, 'alpha': mr - hr, 'wins': wins, 'total': len(week)}


def _build_last_week_performance(daily):
    """构建上周表现（倒数第6~10个交易日）"""
    if len(daily) < 10:
        return {'model_return': 0, 'hs300_return': 0, 'alpha': 0}
    week = daily[-10:-5]
    mr = sum(d.get('return', 0) for d in week)
    hr = sum(d.get('hs300', 0) for d in week)
    return {'model_return': mr, 'hs300_return': hr, 'alpha': mr - hr}


def _build_external_review(decision_date):
    """按决策日切分已纳入事件与盘后新增事件，避免展示时点混淆。"""
    try:
        raw = load_json(EXTERNAL_NEWS_PATH)
        items = raw.get('items', []) if isinstance(raw, dict) else []
    except (OSError, ValueError):
        items = []
    source_counts = {}
    source_categories = {}
    category_counts = {}
    for item in items:
        source = item.get('source', '未知来源')
        category = item.get('category', 'other')
        source_counts[source] = source_counts.get(source, 0) + 1
        source_categories[source] = item.get('category', 'other')
        category_counts[category] = category_counts.get(category, 0) + 1
    valid = [x for x in items if x.get('date_quality') not in (None, 'unknown', 'listing')
             and x.get('published_at')]
    unique_events = []
    seen_events = set()
    for item in sorted(valid, key=lambda x: x['published_at'], reverse=True):
        published_date = str(item['published_at'])[:10]
        key = (published_date, item.get('source', ''), item.get('title', '').strip())
        if key in seen_events:
            continue
        seen_events.add(key)
        unique_events.append(item)
    model_inputs = sorted((x for x in unique_events
                           if str(x['published_at'])[:10] <= decision_date),
                          key=lambda x: x['published_at'], reverse=True)
    post_decision = sorted((x for x in unique_events
                            if str(x['published_at'])[:10] > decision_date),
                           key=lambda x: x['published_at'], reverse=True)
    return {
        'updated_at': raw.get('updated_at', '') if isinstance(raw, dict) else '',
        'count': len(items),
        'source_counts': source_counts,
        'source_categories': source_categories,
        'category_counts': category_counts,
        'decision_date': decision_date,
        'headlines': model_inputs[:8],
        'events': model_inputs[:3],
        'post_decision_events': post_decision[:3],
    }


def _build_adaptation_review(daily, summary):
    """用历史结果做轻量回顾；只提出可验证调优，不凭小样本自动改权重。"""
    def window(rows):
        model_equity = bench_equity = 1.0
        for row in rows:
            model_equity *= 1 + float(row.get('return', 0)) / 100
            bench_equity *= 1 + float(row.get('hs300', 0)) / 100
        model = (model_equity - 1) * 100
        bench = (bench_equity - 1) * 100
        trades = [x for x in rows if x.get('decision') == 'buy']
        wins = sum(float(x.get('return', 0)) > 0 for x in trades)
        return {'days': len(rows), 'trades': len(trades), 'model': model,
                'bench': bench, 'alpha': model - bench,
                'win_rate': wins / len(trades) * 100 if trades else 0}

    windows = {'近20个交易日': window(daily[-20:]), '近40个交易日': window(daily[-40:]), '全样本': window(daily)}
    # 全样本基准必须与摘要中的同期买入持有口径一致；滚动窗口仍使用
    # 与模型决策日匹配的基准收益，避免两种基准在同一行混用。
    full = windows['全样本']
    full['bench'] = float(summary.get('hs300_return', full['bench']))
    full['alpha'] = full['model'] - full['bench']
    full['win_rate'] = float(summary.get('win_rate', full['win_rate']))
    equity = peak = 1.0
    max_drawdown = 0.0
    for row in daily:
        equity *= 1 + float(row.get('return', 0)) / 100
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, (equity / peak - 1) * 100)

    if summary.get('alpha', 0) < 0:
        action = '暂停放大仓位：当前全样本跑输基准，优先做滚动样本外验证。'
    else:
        action = '维持当前风险预算：全样本仍有超额，再用滚动窗口确认稳定性。'
    recent = windows['近20个交易日']
    if recent['alpha'] < 0:
        action += ' 近20日超额仍为负，下一轮应提高交易成本与拥挤撤退惩罚。'
    elif recent['alpha'] > 0:
        action += ' 近20日超额转正，可观察是否连续两个窗口成立。'
    max_drawdown = float(summary.get('max_drawdown', max_drawdown))
    return {'windows': windows, 'max_drawdown': max_drawdown, 'action': action,
            'guardrail': '只有在滚动样本外超额、回撤和换手同时改善时，才自动采用新参数。'}


def normalize_model_data(raw):
    """将实际 model_results.json 结构标准化为生成器所需格式"""
    m = dict(raw)
    summary = dict(raw['summary'])
    daily = raw.get('all_daily_summaries', [])

    # 补充 summary 缺失字段
    summary['report_date'] = raw['latest_decision']['date']
    summary['hs300_return'] = summary.get('hs300_cumulative_return', 0)
    summary['start_date'] = daily[0]['date'] if daily else ''
    summary['end_date'] = daily[-1]['date'] if daily else ''
    summary['experience_limit'] = 200

    # 计算平均盈亏
    returns = [d['return'] for d in daily if d.get('return') is not None]
    profits = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    summary['avg_profit'] = sum(profits) / len(profits) if profits else 0
    summary['avg_loss'] = sum(losses) / len(losses) if losses else 0
    m['summary'] = summary

    # 标准化 latest_decision
    ld = raw['latest_decision']
    sent = ld.get('sentiment', {})
    m['latest_decision'] = {
        'date': ld['date'],
        'trend': TREND_MAP.get(ld['trend'], ld['trend']),
        'decision': {'buy': '建议配置', 'hold': '观望'}.get(ld.get('decision'), ld.get('decision', '')),
        'picks': [
            {'code': p['code'], 'name': p['name'], 'sector': p.get('sector', ''),
             'weight': p['weight'], 'score': p.get('total_score', 0),
             'early_entry': p.get('early_entry', 0), 'crowding': p.get('crowding', 0),
             'withdrawal_risk': p.get('withdrawal_risk', 0),
             'external_signal': p.get('external_signal', 0),
             'news_price_gap': p.get('news_price_gap', 0),
             'news_flow_gap': p.get('news_flow_gap', 0)}
            for p in ld.get('etf_selection', [])
        ],
        'reason': ld.get('reason', ''),
        'risk_budget': float(ld.get('market_state', {}).get('risk_budget', 0)),
        'confidence': '未单独校准',
        'bull_signals': sent.get('bullish_count', 0),
        'bear_signals': sent.get('bearish_count', 0),
        'sentiment_score': sent.get('score', 0),
        'hot_sectors': [{'name': s['sector'], 'count': s['count']} for s in sent.get('hot_sectors', [])],
        'etf_performance': _calc_etf_performance(raw.get('experiences', [])),
        'market_state': ld.get('market_state', {}),
        'sector_performance': ld.get('sector_performance', {}),
        'rankings': ld.get('rankings', []),
        'external_sentiment': ld.get('external_sentiment', {}),
        'universe_count': len(ld.get('rankings', [])),
    }

    # 标准化 experiences（最近20条，最新在前，构造可读文本）
    recent_exp = raw.get('experiences', [])[-20:][::-1]
    m['experiences'] = [
        {
            'date': e['date'],
            'text': f'{e["etf_name"]}({e["sector"]}) {TREND_MAP.get(e["trend"], e["trend"])} | '
                    f'评分{e.get("total_score", 0):.2f} | 情绪{e.get("sentiment_score", 0):.2f} | '
                    f'日内{e.get("intraday_return", 0):.2f}% | 净收益{e.get("net_return", 0)*100:.2f}% | {e.get("result", "")}'
        }
        for e in recent_exp
    ]

    # 标准化 all_daily_summaries
    m['all_daily_summaries'] = [
        {
            'date': d['date'],
            'trend': TREND_MAP.get(d['trend'], d['trend']),
            'etfs': ', '.join(d.get('etf_names', [])),
            'return': d.get('return', 0),
            'hs300': d.get('hs300', 0),
            'alpha': d.get('alpha', 0),
            'sentiment': f'{d.get("sentiment_score", 0):.2f}',
        }
        for d in daily
    ]

    # 生成 chart_data / market_review / weekly_performance
    m['chart_data'] = _build_chart_data(raw, daily)
    m['market_review'] = _build_market_review(raw)
    m['weekly_performance'] = _build_weekly_performance(daily)
    m['last_week_performance'] = _build_last_week_performance(daily)
    m['external_review'] = _build_external_review(ld['date'])
    m['adaptation_review'] = _build_adaptation_review(daily, summary)
    m['handoff'] = load_json(HANDOFF_PATH) if os.path.exists(HANDOFF_PATH) else {}
    m['diagnostics'] = load_json(DIAGNOSTICS_PATH) if os.path.exists(DIAGNOSTICS_PATH) else {}

    return m


def normalize_econ_data(raw, model_data):
    """将实际 econometric_results.json 结构标准化为生成器所需格式"""
    e = {}
    fs = raw.get('dataset_info', {}).get('feature_stats', {})

    # ── Logit ──
    lm = raw['logit_model']
    tscv = lm.get('time_series_cv', {})

    logit_coefs = []
    for c in lm['coefficients']:
        p = c.get('pvalue', 1)
        logit_coefs.append({
            'variable': c['feature'], 'coef': c['coef'],
            'std_err': None, 'z': None, 'p': p, 'sig': _sig_stars(p),
        })

    logit_preds = []
    for p in lm.get('latest_predictions', []):
        prob_pct = p.get('prob_alpha_positive', p.get('prob_up', 0)) * 100
        action_map = {
            'buy_candidate': 'Shadow候选', 'avoid': 'Shadow回避',
            'abstain': 'Shadow观望', 'diagnostic_only': '仅诊断',
        }
        logit_preds.append({
            # prob语义为完整持有期成本后净Alpha为正的概率。
            'code': p.get('etf_code', ''),
            'name': p.get('etf_name', ''),
            'etf': p.get('etf_name', ''),
            'sector': p.get('sector', ''),
            'prob': round(prob_pct, 1),
            'direction': '正Alpha' if p.get('predicted_direction') == 'up' else '非正Alpha',
            'confidence': f'{abs(prob_pct - 50) * 2:.0f}%',
            'action': action_map.get(p.get('production_action'), '仅诊断'),
        })

    e['logit'] = {
        'n': lm['n_obs'],
        'pseudo_r2': lm.get('pseudo_r2') if lm.get('pseudo_r2') is not None else 'N/A（正则化模型）',
        'accuracy': lm.get('accuracy', 0) * 100,
        'cv_accuracy': tscv.get('mean_cv_accuracy', 0) * 100,
        'baseline_accuracy': lm.get('baseline_accuracy', 0) * 100,
        'in_sample_accuracy': lm.get('in_sample_accuracy', 0) * 100,
        'accuracy_note': lm.get('accuracy_note', ''),
        'accuracy_ci_95': lm.get('accuracy_ci_95', [None, None]),
        'brier_score': lm.get('brier_score'),
        'baseline_brier_score': lm.get('baseline_brier_score'),
        'has_predictive_skill': lm.get('has_predictive_skill', False),
        'production_eligible': lm.get('production_eligible', False),
        'eligibility_checks': lm.get('eligibility_checks', {}),
        'selective': lm.get('selective_evaluation', {}),
        'target': lm.get('target', ''),
        'cv_auc': 'N/A',
        'lasso_features': lm.get('selected_features', []),
        'lasso_note': f"C={lm.get('lasso_selection_C', 'N/A')}",
        'coefficients': logit_coefs,
        'latest_predictions': logit_preds,
    }

    # ── OLS ──
    om = raw['ols_model']
    coef_lookup = {c['feature']: c for c in om['coefficients']}

    ols_coefs = []
    for c in om['coefficients']:
        p = c.get('pvalue', 1)
        ols_coefs.append({
            'variable': c['feature'], 'coef': c['coef'],
            'std_err': None, 't': c.get('tvalue'), 'p': p, 'sig': _sig_stars(p),
        })

    fi_list = []
    for f in om.get('factor_importance', []):
        feat = f['feature']
        cd = coef_lookup.get(feat, {})
        p = cd.get('pvalue', 1)
        fi_list.append({
            'factor': feat,
            'beta': f.get('lasso_std_coef', 0),
            'p': p,
            'sigma': fs.get(feat, {}).get('std', 0),
            'importance': f.get('abs_importance', 0),
            'sig': _sig_stars(p),
        })

    ols_preds = []
    for p in om.get('latest_predictions', []):
        ols_preds.append({
            'etf': p.get('etf_name', ''), 'sector': p.get('sector', ''),
            'predicted_return': p.get('predicted_net_alpha_pct', p.get('predicted_return_pct', 0)),
        })

    e['ols'] = {
        'n': om['n_obs'],
        'r2': om.get('r_squared', 0),
        'adj_r2': om.get('adj_r_squared', 0),
        'f_stat': om.get('f_statistic', 0),
        'f_p': om.get('f_pvalue', 0),
        'cv_r2': om.get('time_series_cv_r2', {}).get('mean_cv_r2', 0),
        'target': om.get('target', ''),
        'covariance': om.get('covariance', ''),
        'lasso_alpha': om.get('lasso_selection_alpha', 'N/A'),
        'lasso_features': om.get('selected_features', []),
        'lasso_removed': om.get('dropped_features', []),
        'coefficients': ols_coefs,
        'factor_importance': fi_list,
        'latest_predictions': ols_preds,
    }

    # ── Cross Validation ──
    cv_raw = raw.get('cross_validation', {})

    # 趋势验证（从 daily summaries 计算）
    daily = model_data['all_daily_summaries']
    trend_stats = {}
    for d in daily:
        t = d['trend']
        if t not in trend_stats:
            trend_stats[t] = {'days': 0, 'up': 0}
        trend_stats[t]['days'] += 1
        if d.get('return', 0) > 0:
            trend_stats[t]['up'] += 1

    bull = trend_stats.get('看涨', {'days': 0, 'up': 0})
    bear = trend_stats.get('看跌', {'days': 0, 'up': 0})
    neutral = trend_stats.get('震荡', {'days': 0, 'up': 0})

    # 一致性表（Logit vs 规则模型）
    rule_codes = set(p['code'] for p in model_data['latest_decision']['picks'])
    rule_names = set(p['name'] for p in model_data['latest_decision']['picks'])
    consistency = []
    for p in lm.get('latest_predictions', []):
        etf_name = p.get('etf_name', '')
        etf_code = p.get('etf_code', '')
        prob = p.get('prob_alpha_positive', p.get('prob_up', 0)) * 100
        direction = '正Alpha' if p.get('predicted_direction') == 'up' else '非正Alpha'
        rule_rec = etf_code in rule_codes or etf_name in rule_names
        consistent = (direction == '正Alpha' and rule_rec) or (direction == '非正Alpha' and not rule_rec)
        consistency.append({
            'etf': etf_name,
            'logit_prob': f'{prob:.1f}',
            'logit_dir': direction,
            'rule_rec': rule_rec,
            'consistent': consistent,
        })

    e['cross_validation'] = {
        'trend_validation': {
            'bull_days': bull['days'],
            'bear_days': bear['days'],
            'neutral_days': neutral['days'],
            'bull_up_ratio': bull['up'] / bull['days'] if bull['days'] > 0 else None,
            'bear_up_ratio': bear['up'] / bear['days'] if bear['days'] > 0 else None,
            'neutral_up_ratio': neutral['up'] / neutral['days'] if neutral['days'] > 0 else None,
        },
        'conclusion': cv_raw.get('interpretation', ''),
        'consistency': consistency,
    }

    return e


# ============================================================
#  CSS
# ============================================================
CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Instrument+Sans:wght@400;500;600;700&display=swap');

@font-face{font-family:'InstrumentSans';src:url('_shared/fonts/InstrumentSans-Regular.ttf') format('truetype');font-weight:400;font-style:normal;font-display:swap}
@font-face{font-family:'InstrumentSans';src:url('_shared/fonts/InstrumentSans-Bold.ttf') format('truetype');font-weight:700;font-style:normal;font-display:swap}
@font-face{font-family:'InstrumentSans';src:url('_shared/fonts/InstrumentSans-Italic.ttf') format('truetype');font-weight:400;font-style:italic;font-display:swap}
@font-face{font-family:'JetBrainsMono';src:url('_shared/fonts/JetBrainsMono-Regular.ttf') format('truetype');font-weight:400;font-style:normal;font-display:swap}
@font-face{font-family:'JetBrainsMono';src:url('_shared/fonts/JetBrainsMono-Bold.ttf') format('truetype');font-weight:700;font-style:normal;font-display:swap}

:root{
  --bg:#ffffff;--bg2:#f5f5f7;--bg3:#fbfbfd;
  --ink:#1d1d1f;--muted:#86868b;--rule:#d2d2d7;
  --accent:#0071e3;--green:#34c759;--accent2:#ff3b30;--gold:#d29922;
  --positive:#34c759;--negative:#ff3b30;--warn:#ff9f0a;
  --radius:16px;--radius-sm:10px;
  --maxw:980px;
  --ease-out:cubic-bezier(0.23,1,0.32,1);
  --ease-in-out:cubic-bezier(0.77,0,0.175,1);
  --shadow-sm:0 1px 3px rgba(0,0,0,0.04),0 1px 2px rgba(0,0,0,0.02);
  --shadow-md:0 4px 12px rgba(0,0,0,0.06),0 1px 3px rgba(0,0,0,0.04);
  --shadow-lg:0 12px 40px rgba(0,0,0,0.08),0 4px 12px rgba(0,0,0,0.04);
  --IS:'InstrumentSans',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  --JM:'JetBrainsMono',ui-monospace,'SF Mono',Menlo,monospace;
}

*{margin:0;padding:0;box-sizing:border-box}
body{background:radial-gradient(ellipse 600px 400px at 15% 5%,rgba(0,113,227,0.15),transparent 60%),radial-gradient(ellipse 500px 350px at 85% 15%,rgba(0,113,227,0.10),transparent 60%),radial-gradient(ellipse 700px 500px at 50% 45%,rgba(0,113,227,0.08),transparent 70%),var(--bg);background-attachment:fixed;color:var(--ink);font-family:var(--IS);font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased;min-height:100vh}

.container{max-width:var(--maxw);margin:0 auto;padding:24px 20px 60px}

.date-bar{text-align:center;margin-bottom:28px}
.badge{display:inline-block;background:var(--bg2);border-radius:100px;padding:6px 16px;font-family:var(--JM);font-size:0.82rem;color:var(--ink);font-weight:500}
.date-bar .sub{margin-top:6px;font-size:0.72rem;color:var(--muted)}

.sec-title{font-size:0.7rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin:28px 0 10px;padding-left:2px}

.card{background:var(--bg3);border:1px solid var(--rule);border-radius:var(--radius);padding:18px 20px;margin-bottom:12px;box-shadow:var(--shadow-sm);transition:box-shadow 200ms var(--ease-out),transform 200ms var(--ease-out)}
.card:hover{box-shadow:var(--shadow-md);transform:translateY(-1px)}
.card-title{font-size:0.9rem;font-weight:600;margin-bottom:12px;color:var(--ink)}

.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:4px}
.metric{background:var(--bg3);border:1px solid var(--rule);border-radius:var(--radius-sm);padding:14px 16px;box-shadow:var(--shadow-sm);transition:box-shadow 200ms var(--ease-out),transform 200ms var(--ease-out)}
.metric:hover{box-shadow:var(--shadow-md);transform:translateY(-1px)}
.ml{font-size:0.72rem;color:var(--muted);margin-bottom:4px}
.mv{font-family:var(--JM);font-size:1.3rem;font-weight:600;color:var(--ink)}
.mv.up{color:var(--green)}
.mv.down{color:var(--accent2)}
.ms{font-size:0.68rem;color:var(--muted);margin-top:3px}

.formula-box{background:var(--bg);border:1px solid var(--rule);border-radius:var(--radius-sm);padding:14px 16px;margin-top:10px}
.formula{font-family:var(--JM);font-size:0.8rem;color:var(--ink);line-height:1.9;white-space:nowrap;overflow-x:auto}
.formula .coef{color:var(--accent)}
.formula .coef.sig{color:var(--accent2);font-weight:600}
.formula .var{color:var(--muted)}
.formula .op{color:var(--muted)}
.f-title{font-size:0.78rem;font-weight:600;color:var(--muted);margin-bottom:6px}
.formula-legend{font-size:0.72rem;color:var(--muted);line-height:1.9;margin-top:8px}
.formula-legend b{color:var(--ink)}

.rec-2col{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px}

table{width:100%;border-collapse:collapse;font-size:0.8rem}
thead th{text-align:left;font-weight:600;color:var(--muted);padding:6px 8px;border-bottom:2px solid var(--rule);font-size:0.72rem;text-transform:uppercase;letter-spacing:0.5px}
tbody td{padding:5px 8px;border-bottom:1px solid var(--bg2)}
tbody tr:last-child td{border-bottom:none}
td.up,span.up{color:var(--green)}
td.down,span.down{color:var(--accent2)}

.decision{background:var(--bg3);border:1px solid var(--rule);border-radius:var(--radius);padding:18px 20px}
.dec-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.tag{display:inline-block;padding:2px 10px;border-radius:6px;font-size:0.74rem;font-weight:600}
.t-bull{background:rgba(52,199,89,0.12);color:var(--green)}
.t-bear{background:rgba(255,59,48,0.12);color:var(--accent2)}
.t-neutral{background:var(--bg2);color:var(--muted)}
.conf-pill{background:var(--bg2);border-radius:100px;padding:2px 10px;font-size:0.72rem;color:var(--muted)}
.sig-bar{display:flex;gap:16px;font-size:0.78rem;color:var(--muted);margin-bottom:12px}
.dot{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:3px;vertical-align:middle}
.dot.bull{background:var(--green)}
.dot.bear{background:var(--accent2)}
.picks{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.pick{background:var(--bg);border:1px solid var(--rule);border-radius:var(--radius-sm);padding:8px 12px;display:flex;align-items:center;gap:8px}
.pick-code{font-family:var(--JM);font-size:0.72rem;color:var(--muted)}
.pick-name{font-size:0.82rem;font-weight:500}
.pick-score{font-family:var(--JM);font-size:0.68rem;color:var(--muted);margin-left:4px}
.pick-logit{font-size:0.7rem;color:var(--muted);margin-left:4px}
.pick-w{font-family:var(--JM);font-size:0.78rem;color:var(--accent);font-weight:600}
.reason{font-size:0.8rem;color:var(--ink);line-height:1.7;background:var(--bg);border-radius:var(--radius-sm);padding:10px 12px}

.np-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-top:10px}
.np-card{background:var(--bg);border:1px solid var(--rule);border-radius:var(--radius-sm);padding:12px 14px}
.np-src{font-size:0.78rem;font-weight:600;color:var(--accent);margin-bottom:6px}
.np-card ul{list-style:none;padding:0}
.np-card li{font-size:0.74rem;color:var(--ink);padding:2px 0;border-bottom:1px solid var(--bg2)}
.np-card li:last-child{border-bottom:none}

.rpt{background:var(--bg3);border:1px solid var(--rule);border-radius:var(--radius);padding:16px 20px;margin-bottom:10px}
.rpt h3{font-size:0.82rem;font-weight:600;margin-bottom:6px;color:var(--ink)}
.rpt p{font-size:0.78rem;color:var(--ink);line-height:1.7;margin-bottom:3px}
.rpt .hl{color:var(--green);font-weight:600}
.rpt .wl{color:var(--accent2);font-weight:600}

.chart-card{background:var(--bg3);border:1px solid var(--rule);border-radius:var(--radius);padding:16px 20px;margin-bottom:12px;box-shadow:var(--shadow-sm);transition:box-shadow 200ms var(--ease-out),transform 200ms var(--ease-out)}
.chart-card:hover{box-shadow:var(--shadow-md);transform:translateY(-1px)}
.chart-card .card-title{margin-bottom:8px}
.chart{width:100%;height:300px}

.exp-list{display:grid;grid-template-columns:1fr;gap:4px}
.exp-row{display:flex;gap:10px;padding:6px 0;border-bottom:1px solid var(--bg2);font-size:0.76rem}
.exp-row:last-child{border-bottom:none}
.exp-d{font-family:var(--JM);color:var(--muted);min-width:90px}
.exp-t{color:var(--ink)}

/* Top Summary Section */
.top-summary{margin-bottom:16px}
.core-view{background:var(--bg3);border:1px solid var(--accent);border-radius:var(--radius);padding:18px 22px;margin-bottom:12px;text-align:center;box-shadow:var(--shadow-md)}
.core-view .cv-label{font-size:0.68rem;color:var(--accent);font-weight:700;text-transform:uppercase;letter-spacing:2px;margin-bottom:8px}
.core-view .cv-text{font-size:1rem;color:var(--ink);font-weight:500;line-height:1.7;letter-spacing:-0.005em}.core-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:16px;text-align:left}.core-note{padding:11px 12px;background:var(--bg);border:1px solid var(--rule);border-radius:var(--radius-sm)}.core-note b{display:block;color:var(--accent);font-size:.72rem;margin-bottom:5px}.core-note span{display:block;color:var(--muted);font-size:.72rem;line-height:1.55}.core-note.risk{border-left:3px solid var(--accent2)}
.signal-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.signal-card{background:var(--bg3);border-radius:var(--radius);padding:14px 18px;border:1px solid var(--rule);box-shadow:var(--shadow-sm);transition:box-shadow 200ms var(--ease-out),transform 200ms var(--ease-out)}
.signal-card:hover{box-shadow:var(--shadow-md);transform:translateY(-1px)}
.signal-card.long{border-left:4px solid var(--green)}
.signal-card.short{border-left:4px solid var(--accent2)}
.signal-card .sig-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;padding-bottom:8px;border-bottom:1px solid var(--rule)}
.signal-card .sig-title{font-size:0.92rem;font-weight:700;letter-spacing:-0.005em}
.signal-card.long .sig-title{color:var(--green)}
.signal-card.short .sig-title{color:var(--accent2)}
.signal-card .sig-tag{font-size:0.68rem;padding:2px 10px;border-radius:100px;font-weight:600;letter-spacing:0.02em}
.signal-card.long .sig-tag{background:rgba(52,199,89,0.12);color:var(--green)}
.signal-card.short .sig-tag{background:rgba(255,59,48,0.12);color:var(--accent2)}
.signal-card .sig-item{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--rule);font-size:0.84rem}
.signal-card .sig-item:last-child{border-bottom:none}
.signal-card .sig-item .sig-name{font-weight:600;color:var(--ink)}
.signal-card .sig-item .sig-meta{font-size:0.72rem;color:var(--muted);font-variant-numeric:tabular-nums}
.signal-card .sig-item .sig-score{font-family:var(--JM);font-weight:700;font-size:0.88rem;font-variant-numeric:tabular-nums}

footer{text-align:center;font-size:0.7rem;color:var(--muted);margin-top:36px;padding-top:16px;border-top:1px solid var(--rule)}

@media(max-width:760px){
  .metrics{grid-template-columns:repeat(2,1fr)}
  .np-grid{grid-template-columns:1fr}
  .rec-2col{grid-template-columns:1fr}
  .signal-grid{grid-template-columns:1fr}
}

/* Research-note skin: quiet, editorial, information-first. */
:root{
  --bg:#f5f3ee;--bg2:#ebe8e1;--bg3:#fcfbf8;--ink:#25231f;--muted:#77736b;--rule:#d9d4ca;
  --accent:#9a4d2d;--green:#2f6f52;--accent2:#a84b43;--gold:#a87524;
  --positive:#2f6f52;--negative:#a84b43;--warn:#a87524;--radius:4px;--radius-sm:3px;--maxw:1120px;
  --shadow-sm:0 1px 2px rgba(53,45,35,.05);--shadow-md:0 8px 24px rgba(53,45,35,.08);
  --IS:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB',sans-serif;
  --JM:'SFMono-Regular',Consolas,'Liberation Mono',monospace;
}
body{background:var(--bg);color:var(--ink);font-size:14px;line-height:1.72}
.container{max-width:var(--maxw);padding:28px 32px 64px}
.report-masthead{border-bottom:1px solid var(--ink);padding:10px 0 20px;margin-bottom:28px}
.report-kicker{color:var(--accent);font-size:.72rem;font-weight:700;letter-spacing:.16em;text-transform:uppercase}
.report-title{font-family:Georgia,'Songti SC','STSong',serif;font-size:2.25rem;line-height:1.15;letter-spacing:-.03em;margin:8px 0 6px}
.report-subtitle{color:var(--muted);font-size:.86rem;display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap}
.report-meta{font-family:var(--JM);font-size:.72rem;color:var(--muted)}
.date-bar{display:none}
.sec-title{font-family:Georgia,'Songti SC','STSong',serif;text-transform:none;letter-spacing:-.01em;color:var(--ink);font-size:1.22rem;font-weight:700;margin:34px 0 12px;padding:0;border-bottom:1px solid var(--rule);padding-bottom:7px}
.sec-title:first-letter{color:var(--accent)}
.card,.chart-card,.rpt,.decision,.core-view,.signal-card,.metric,.callout,.formula-box,.pick,.reason{background:var(--bg3)!important;border:1px solid var(--rule)!important;box-shadow:var(--shadow-sm)!important;border-radius:var(--radius)!important}
.card:hover,.chart-card:hover,.metric:hover,.signal-card:hover{transform:none;box-shadow:var(--shadow-md)!important}
.card,.chart-card,.rpt{padding:18px 20px;margin-bottom:14px}
.card-title{font-size:.78rem;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:700;margin-bottom:13px}
.metrics{gap:1px;background:var(--rule);border:1px solid var(--rule);border-radius:var(--radius);overflow:hidden}
.metric{border:0!important;border-radius:0!important;padding:16px 18px;min-height:88px}
.ml{font-size:.7rem;color:var(--muted);letter-spacing:.04em}.mv{font-size:1.32rem}.ms{font-size:.68rem}
.core-view{text-align:left;padding:22px 24px;border-top:3px solid var(--accent)!important;margin-bottom:14px}
.core-view .cv-label{color:var(--accent);font-size:.68rem;letter-spacing:.14em}.core-view .cv-text{font-family:Georgia,'Songti SC','STSong',serif;font-size:1.16rem;line-height:1.7}
.strategy-strip{display:grid;grid-template-columns:repeat(5,1fr);gap:1px;background:var(--rule);border:1px solid var(--rule);margin-top:18px}.strategy-cell{background:var(--bg3);padding:11px 12px}.strategy-cell span{display:block;color:var(--muted);font-size:.68rem}.strategy-cell b{display:block;font-family:var(--JM);font-size:.94rem;margin-top:3px}
.signal-grid,.rec-2col{gap:14px}.signal-card{padding:17px 20px}.signal-card.long{border-left:3px solid var(--green)!important}.signal-card.short{border-left:3px solid var(--accent2)!important}
.signal-card .sig-header{border-bottom:1px solid var(--rule)}.signal-card .sig-title{font-size:.9rem}.signal-card .sig-item{border-bottom:1px solid var(--bg2);padding:10px 0}.trade-item{gap:16px}.sig-copy{display:grid;gap:2px;min-width:132px}.sig-copy .sig-meta{display:block}.sig-facts{display:grid;grid-template-columns:auto auto;justify-content:end;align-items:center;gap:2px 12px;text-align:right;font-family:var(--JM);font-size:.7rem;color:var(--muted)}.sig-facts b{grid-row:1 / span 2;color:var(--ink);font-size:.78rem}.signal-card.long .sig-facts b{color:var(--green)}.signal-card.short .sig-facts b{color:var(--accent2)}
.execution-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:12px}.execution-note{background:var(--bg3);border:1px solid var(--rule);padding:13px 14px}.execution-note b{display:block;color:var(--accent);font-size:.72rem;margin-bottom:5px}.execution-note span{display:block;color:var(--muted);font-size:.72rem;line-height:1.55}.execution-note.caution{border-left:3px solid var(--accent2)}
.pick{box-shadow:none!important}.reason{box-shadow:none!important}
table{font-size:.78rem}thead th{border-bottom:1px solid var(--ink);padding:8px}tbody td{padding:7px 8px;border-bottom:1px solid var(--bg2)}
.tag{border-radius:3px}.t-bull{background:#e5efe8;color:var(--green)}.t-bear{background:#f4e5e2;color:var(--accent2)}.t-neutral{background:var(--bg2);color:var(--muted)}
.chart{height:280px}.formula-box{background:#f8f6f1!important}.formula{font-size:.76rem}
footer{font-size:.68rem;border-top:1px solid var(--ink);text-align:left;padding-top:12px}
.state-grid{display:grid;grid-template-columns:repeat(6,1fr);gap:1px;background:var(--rule);border:1px solid var(--rule);border-radius:var(--radius);overflow:hidden}
.state-cell{background:var(--bg3);padding:15px 14px;min-height:105px}.state-label{font-size:.7rem;color:var(--muted);letter-spacing:.04em}.state-value{font-family:var(--JM);font-size:1.15rem;font-weight:700;margin:7px 0 3px}.state-note{font-size:.66rem;color:var(--muted);line-height:1.45}
.section-note{font-size:.76rem;color:var(--muted);padding:10px 2px 0}.external-layout{display:grid;grid-template-columns:1.15fr .85fr;gap:14px}.gap-list{display:grid;gap:9px}.gap-list div{border-left:2px solid var(--accent);padding:7px 10px;background:var(--bg2)}.gap-list b{display:block;font-size:.76rem}.gap-list span{font-size:.72rem;color:var(--muted)}.headline-card ul{list-style:none}.headline-card li{padding:7px 0;border-bottom:1px solid var(--bg2);font-size:.75rem}.headline-card li:last-child{border-bottom:0}.headline-card li span{font-family:var(--JM);color:var(--muted);margin-right:8px}.headline-card a{color:var(--accent);margin-left:6px;text-decoration:none}
.adapt-grid,.model-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.adapt-box,.model-box{background:var(--bg3);border:1px solid var(--rule);padding:16px 18px}.adapt-box b{font-size:.78rem;color:var(--accent)}.adapt-box p,.model-box p{font-size:.78rem;margin-top:6px}.model-number{font-family:var(--JM);font-size:1.6rem;font-weight:700;margin:8px 0}.formula{font-family:var(--JM);line-height:1.8;color:var(--ink)}.event-card{padding:12px 0;border-bottom:1px solid var(--rule)}.event-card:last-child{border-bottom:0}.event-meta{font-size:.7rem;color:var(--muted);letter-spacing:.02em}.event-title{font-weight:700;margin:6px 0}.event-title a{font-size:.7rem;color:var(--accent);font-weight:400}.event-card p{font-size:.78rem;line-height:1.65;margin:4px 0}.post-news{margin-top:12px;border-top:1px solid var(--rule);padding-top:10px}.post-news summary{cursor:pointer;color:var(--accent);font-weight:700;font-size:.74rem}.empty-note{color:var(--muted);padding:18px 0;font-size:.8rem}.model-fold,.inner-fold,.detail-fold{background:var(--bg3);border:1px solid var(--rule);padding:15px 18px}.model-fold summary,.inner-fold summary,.detail-fold summary{cursor:pointer;color:var(--accent);font-weight:700;font-size:.8rem}.model-fold[open]{box-shadow:var(--shadow-md)}.inner-fold{margin-top:14px;background:var(--bg)}.detail-fold{margin-top:14px}.detail-fold .card{margin-top:14px}
.today-brief{background:var(--ink);color:var(--bg3);padding:24px 26px;border-radius:var(--radius);margin-bottom:18px}.today-status{font-size:.7rem;letter-spacing:.12em;color:#d9d4ca;font-weight:700}.today-brief h2{font-family:Georgia,'Songti SC','STSong',serif;font-size:1.35rem;line-height:1.55;margin:8px 0}.today-action{font-size:.9rem;line-height:1.7;color:#f2eee6}.four-lines{display:grid;grid-template-columns:1fr 1fr;gap:1px;background:#575149;margin-top:18px}.brief-line{background:#312e29;padding:12px 14px}.brief-line b{display:block;color:#d8a581;font-size:.7rem;margin-bottom:4px}.brief-line span{display:block;font-size:.76rem;line-height:1.55;color:#eee9df}
.module-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.module-card{background:var(--bg3);border:1px solid var(--rule);border-top:3px solid var(--muted);padding:17px 18px}.module-card.positive{border-top-color:var(--green)}.module-card.negative{border-top-color:var(--accent2)}.module-head{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}.module-title{font-family:Georgia,'Songti SC','STSong',serif;font-size:1.02rem;font-weight:700}.module-state{white-space:nowrap;font-size:.67rem;padding:2px 7px;background:var(--bg2);color:var(--muted)}.module-conclusion{font-weight:700;font-size:.85rem;line-height:1.55;margin:11px 0}.evidence-list{list-style:none;border-top:1px solid var(--rule)}.evidence-list li{padding:8px 0;border-bottom:1px solid var(--bg2)}.evidence-label{display:block;color:var(--muted);font-size:.67rem}.evidence-value{display:block;font-size:.78rem;font-weight:600;line-height:1.5}.evidence-meta{display:block;color:var(--muted);font-size:.64rem}.evidence-meta a{color:var(--accent);text-decoration:none}.module-meaning,.module-watch{padding:9px 10px;margin-top:9px;font-size:.73rem;line-height:1.55}.module-meaning{background:#f1eee7}.module-watch{border-left:2px solid var(--accent);padding-left:10px}.module-meaning b,.module-watch b{display:block;font-size:.67rem;color:var(--accent);margin-bottom:2px}.module-limit{margin-top:9px;font-size:.67rem;color:var(--muted)}.module-limit summary{cursor:pointer}
.daily-alert-bar{display:flex;justify-content:space-between;gap:14px;align-items:center;background:#312e29;color:#f5f3ee;padding:13px 16px;margin-bottom:10px}.daily-alert-title{font-family:Georgia,'Songti SC','STSong',serif;font-size:1.08rem;font-weight:700}.daily-alert-meta{font-size:.68rem;color:#d9d4ca;text-align:right}.focus-panel.recommend-panel{border-top:4px solid var(--green)}.focus-panel.avoid-panel{border-top:4px solid var(--accent2)}
.focus-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.focus-panel{background:var(--bg3);border:1px solid var(--rule);padding:16px 18px}.focus-panel-head{display:flex;justify-content:space-between;gap:10px;align-items:baseline;margin-bottom:10px}.focus-panel-head b{font-family:Georgia,'Songti SC','STSong',serif;font-size:1rem}.focus-panel-head span{font-size:.66rem;color:var(--muted)}.focus-list{display:grid;gap:9px}.focus-card{border:1px solid var(--rule);border-left:4px solid var(--muted);padding:12px 13px;background:var(--bg)}.focus-card.recommend{border-left-color:var(--green)}.focus-card.avoid{border-left-color:var(--accent2)}.focus-top{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.focus-name{font-weight:700}.focus-name small{font-family:var(--JM);color:var(--muted);font-weight:400}.focus-action{font-size:.68rem;font-weight:700;text-align:right}.recommend .focus-action{color:var(--green)}.avoid .focus-action{color:var(--accent2)}.focus-why{font-size:.74rem;line-height:1.55;margin:7px 0}.focus-facts{display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--rule)}.focus-facts span{display:block;background:var(--bg3);padding:6px 7px;font-size:.65rem;color:var(--muted)}.focus-facts b{display:block;color:var(--ink);font-family:var(--JM);font-size:.68rem}.deep-dive-wrap{display:grid;gap:13px}.deep-card{background:var(--bg3);border:1px solid var(--rule);border-top:4px solid var(--muted);padding:17px 18px}.deep-card.recommend{border-top-color:var(--green)}.deep-card.avoid{border-top-color:var(--accent2)}.deep-head{display:flex;justify-content:space-between;gap:14px;align-items:flex-start}.deep-role{font-size:.66rem;font-weight:700;letter-spacing:.08em}.deep-card.recommend .deep-role{color:var(--green)}.deep-card.avoid .deep-role{color:var(--accent2)}.deep-title{font-family:Georgia,'Songti SC','STSong',serif;font-size:1.08rem;font-weight:700}.deep-title small{font-family:var(--JM);font-size:.68rem;color:var(--muted);font-weight:400}.deep-action{text-align:right;font-size:.72rem;font-weight:700;max-width:42%}.deep-columns{display:grid;grid-template-columns:1fr 1fr;gap:11px;margin-top:13px}.deep-box{background:var(--bg);border:1px solid var(--rule);padding:11px 12px}.deep-box h4{font-size:.72rem;color:var(--accent);margin:0 0 6px}.deep-box p{font-size:.73rem;line-height:1.55;margin:4px 0}.deep-metrics{display:grid;grid-template-columns:repeat(2,1fr);gap:5px;margin-top:8px}.deep-metrics span{background:var(--bg3);padding:6px 7px;font-size:.65rem;color:var(--muted)}.deep-metrics b{display:block;color:var(--ink);font-family:var(--JM)}.news-list{list-style:none;margin-top:7px}.news-list li{padding:7px 0;border-top:1px solid var(--rule);font-size:.7rem;line-height:1.5}.news-list a{color:var(--ink);font-weight:600;text-decoration:none}.news-meta{display:block;color:var(--muted);font-size:.63rem}.context-badge{color:var(--accent);font-weight:700}.deep-cross{margin-top:10px;border-left:3px solid var(--accent);background:#f1eee7;padding:9px 11px;font-size:.73rem}.deep-next{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:9px}.deep-next div{padding:8px 10px;background:var(--bg2);font-size:.69rem}.deep-next b{display:block;color:var(--accent);margin-bottom:2px}.quality-fold{margin-top:12px;background:var(--bg3);border:1px solid var(--rule);padding:12px 14px}.quality-fold summary{cursor:pointer;color:var(--accent);font-weight:700;font-size:.75rem}.quality-table{margin-top:10px}
@media(max-width:760px){.container{padding:20px 16px 48px}.report-title{font-size:1.75rem}.report-subtitle{display:block}.report-subtitle>span{display:block}.report-meta{margin-top:5px}.metrics{grid-template-columns:repeat(2,1fr)!important}.metric{min-height:78px;padding:12px}.mv{font-size:1.08rem}.state-grid,.strategy-strip{grid-template-columns:repeat(2,1fr)}.strategy-cell:last-child{grid-column:1/-1}.external-layout,.adapt-grid,.model-grid,.core-grid,.execution-grid,.module-grid,.four-lines,.focus-grid,.deep-columns,.deep-next{grid-template-columns:1fr}.focus-facts{grid-template-columns:1fr}.deep-action{max-width:48%}.trade-item{align-items:flex-start}.sig-facts{grid-template-columns:1fr;gap:2px}.sig-facts b{grid-row:auto}.today-brief{padding:20px 18px}}
@media(max-width:760px){.daily-alert-bar{display:block}.daily-alert-meta{text-align:left;margin-top:5px}}
@media(prefers-reduced-motion:reduce){.card,.chart-card,.metric,.signal-card{transition:none!important}}
"""

# ============================================================
#  生成 charts.js
# ============================================================
def generate_charts_js(model_data, econ_data):
    """生成 charts.js 文件内容 (IIFE, makeChart 辅助函数)"""
    cd = model_data['chart_data']
    fi = econ_data['ols']['factor_importance']

    cum   = cd['cumulative']
    month = cd['monthly']
    etfwr = cd['etf_winrate']
    rec   = cd['recent']
    fi_factors = [f['factor'] for f in fi]
    fi_values  = [f['importance'] for f in fi]

    # 使用占位符 + replace 避免 f-string 大括号转义问题
    js = r"""(function(){
  var style = getComputedStyle(document.documentElement);
  var accent = style.getPropertyValue('--accent').trim();
  var green = style.getPropertyValue('--green').trim();
  var red = style.getPropertyValue('--accent2').trim();
  var muted = style.getPropertyValue('--muted').trim();
  var rule = style.getPropertyValue('--rule').trim();
  var gold = style.getPropertyValue('--gold').trim();
  var ink = style.getPropertyValue('--ink').trim();
  var warn = style.getPropertyValue('--warn').trim() || gold;
  var positive = style.getPropertyValue('--positive').trim() || green;
  var negative = style.getPropertyValue('--negative').trim() || red;
  var charts = [];

  function makeChart(id, option){
    var el = document.getElementById(id);
    if(!el) return;
    var c = echarts.init(el, null, {renderer:'svg'});
    c.setOption(option);
    charts.push(c);
  }

  // 1. 累计收益率走势
  makeChart('chart-cum', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true},
    legend:{data:['模型累计','沪深300'],textStyle:{color:ink},top:5},
    grid:{left:'3%',right:'4%',bottom:'3%',containLabel:true},
    xAxis:{type:'category',data:__CUM_DATES__,axisLabel:{color:muted,fontSize:10,interval:9},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型累计',type:'line',data:__CUM_MODEL__,smooth:true,lineStyle:{color:green,width:2},itemStyle:{color:green},
        areaStyle:{color:{type:'linear',x:0,y:0,x2:0,y2:1,colorStops:[{offset:0,color:'rgba(52,199,89,0.15)'},{offset:1,color:'rgba(52,199,89,0)'}]}}},
      {name:'沪深300',type:'line',data:__CUM_HS300__,smooth:true,lineStyle:{color:accent,width:1.5,type:'dashed'},itemStyle:{color:accent}}
    ]
  });

  // 2. 月度收益对比
  makeChart('chart-month', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true,formatter:function(p){
      var s=p[0].name+'月<br/>';
      p.forEach(function(i){s+=i.marker+i.seriesName+':'+i.value+'%<br/>'});
      return s;
    }},
    legend:{data:['模型','沪深300'],textStyle:{color:ink},top:5},
    grid:{left:'3%',right:'4%',bottom:'3%',containLabel:true},
    xAxis:{type:'category',data:__MONTH_MONTHS__,axisLabel:{color:muted,fontSize:11},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型',type:'bar',data:__MONTH_MODEL__,itemStyle:{color:function(p){return p.value>=0?green:red}},barWidth:'30%'},
      {name:'沪深300',type:'bar',data:__MONTH_HS300__,itemStyle:{color:function(p){return p.value>=0?'rgba(0,113,227,0.6)':'rgba(255,59,48,0.6)'}},barWidth:'30%'}
    ]
  });

  // 3. ETF 胜率分布
  makeChart('chart-etf', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true,formatter:function(p){return p[0].name+':'+p[0].value+'%'}},
    grid:{left:'3%',right:'4%',bottom:'10%',containLabel:true},
    xAxis:{type:'category',data:__ETF_NAMES__,axisLabel:{color:muted,fontSize:9,rotate:30},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',max:100,axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[{
      type:'bar',
      data:__ETF_VALUES__,
      itemStyle:{color:function(p){return p.value>=55?green:p.value>=45?gold:red}},
      barWidth:'45%',
      label:{show:true,position:'top',formatter:'{c}%',color:muted,fontSize:9}
    }]
  });

  // 4. 近15日每日收益对比
  makeChart('chart-rec', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true},
    legend:{data:['模型','沪深300'],textStyle:{color:ink},top:5},
    grid:{left:'3%',right:'4%',bottom:'3%',containLabel:true},
    xAxis:{type:'category',data:__REC_DATES__,axisLabel:{color:muted,fontSize:10,rotate:30},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted,formatter:'{value}%'},splitLine:{lineStyle:{color:rule}}},
    series:[
      {name:'模型',type:'bar',data:__REC_MODEL__,itemStyle:{color:function(p){return p.value>=0?green:red}},barWidth:'30%'},
      {name:'沪深300',type:'bar',data:__REC_HS300__,itemStyle:{color:function(p){return p.value>=0?'rgba(0,113,227,0.5)':'rgba(255,59,48,0.5)'}},barWidth:'30%'}
    ]
  });

  // 5. 因素重要性
  makeChart('chart-imp', {
    animation:false,
    tooltip:{trigger:'axis',appendToBody:true},
    grid:{left:'3%',right:'4%',bottom:'10%',containLabel:true},
    xAxis:{type:'category',data:__IMP_FACTORS__,axisLabel:{color:muted,fontSize:9,rotate:25},axisLine:{lineStyle:{color:rule}}},
    yAxis:{type:'value',axisLabel:{color:muted},splitLine:{lineStyle:{color:rule}}},
    series:[{
      type:'bar',
      data:__IMP_VALUES__,
      itemStyle:{color:gold},
      barWidth:'45%',
      label:{show:true,position:'top',formatter:'{c}',color:muted,fontSize:9}
    }]
  });

  window.addEventListener('resize', function(){
    charts.forEach(function(c){ c.resize(); });
  });
})();
"""
    js = js.replace('__CUM_DATES__',  js_arr(cum['dates']))    \
           .replace('__CUM_MODEL__',  js_arr(cum['model']))    \
           .replace('__CUM_HS300__',  js_arr(cum['hs300']))    \
           .replace('__MONTH_MONTHS__', js_arr(month['months'])) \
           .replace('__MONTH_MODEL__',  js_arr(month['model']))  \
           .replace('__MONTH_HS300__',  js_arr(month['hs300']))  \
           .replace('__ETF_NAMES__',  js_arr(etfwr['names']))   \
           .replace('__ETF_VALUES__', js_arr(etfwr['values']))  \
           .replace('__REC_DATES__',  js_arr(rec['dates']))     \
           .replace('__REC_MODEL__',  js_arr(rec['model']))     \
           .replace('__REC_HS300__',  js_arr(rec['hs300']))     \
           .replace('__IMP_FACTORS__', js_arr(fi_factors))      \
           .replace('__IMP_VALUES__',  js_arr(fi_values))
    return js


# ============================================================
#  HTML 各段生成
# ============================================================

def build_signal_views(model_data):
    """把实际多头组合与相对弱势观察分开；当前模型不产生空头交易。"""
    decision = model_data['latest_decision']
    long_candidates = [p for p in decision.get('picks', []) if float(p.get('weight', 0)) > 0]
    long_codes = {p.get('code') for p in long_candidates}
    avoid_watch = [
        item for item in decision.get('rankings', [])
        if item.get('code') not in long_codes
        and (float(item.get('score', 0)) < 0
             or float(item.get('withdrawal_risk', 0)) >= WITHDRAWAL_WATCH_THRESHOLD)
    ]
    avoid_watch.sort(key=lambda item: (float(item.get('score', 0)),
                                       -float(item.get('withdrawal_risk', 0))))
    return {
        'long_candidates': long_candidates,
        'avoid_watch': avoid_watch[:3],
        'short_candidates': [],
    }


def gen_eight_module_brief(model_data, econ_data):
    """固定输出推荐、回避、逐只深挖和八项诊断；不依赖生成式模型补结论。"""
    diagnostics = model_data.get('diagnostics', {})
    overall = diagnostics.get('overall', {})
    modules = sorted(diagnostics.get('modules', []), key=lambda row: row.get('order', 99))
    recommendations = diagnostics.get('recommendations', diagnostics.get('candidates', []))
    avoids = diagnostics.get('avoid_etfs', [])
    daily_alerts = diagnostics.get('daily_etf_alerts', {})
    deep_dives = diagnostics.get('etf_deep_dives', recommendations + avoids)
    if not modules:
        return '''<section class="report-section"><div class="sec-title">今天先看结论</div>
<div class="card"><b>八模块诊断尚未生成。</b><p>请先运行 market_diagnostics.py；缺失时不使用旧版泛化摘要代替。</p></div></section>'''

    first_candidate = recommendations[0] if recommendations else {}
    conflict = first_candidate.get('reason') or '当前没有通过规则门槛的候选。'

    four_lines = [
        ('市场判断', overall.get('conclusion', '数据不足')),
        ('当前动作', overall.get('action', '等待下一次数据确认')),
        ('模型能否执行', f"{overall.get('model_status', '研究观察')}：{overall.get('model_reason', '未完成样本外检验')}") ,
        ('最大矛盾', conflict),
    ]
    lines_html = ''.join(
        f'<div class="brief-line"><b>{esc(label)}</b><span>{esc(value)}</span></div>'
        for label, value in four_lines
    )

    def signed(value, suffix=''):
        return '数据不足' if value is None else f'{float(value):+.2f}{suffix}'

    def focus_card(row, kind):
        fund = row.get('fund_flow', {})
        news = row.get('news_flow', {})
        is_recommend = kind == 'recommend'
        if is_recommend:
            why = row.get('why_selected') or row.get('reason', '数据不足')
            action = f"{row.get('alert_level', '待确认')}｜{row.get('verdict', '推荐观察')}"
        else:
            why = f"回避分{float(row.get('avoid_score', 0)):.1f}；{row.get('reason', '数据不足')}"
            action = f"{row.get('alert_level', '中')}预警｜{row.get('action', '谨慎观察，不追涨')}"
        share_fact = (
            f"{fund.get('status', '数据不足')} {signed(fund.get('share_change_pct'), '%')}"
            if fund.get('share_available') else '真实申赎 数据不足'
        )
        return f'''<article class="focus-card {kind}">
  <div class="focus-top"><span class="focus-name">{esc(row.get('name', ''))} <small>{esc(row.get('code', ''))}</small></span><span class="focus-action">{esc(action)}</span></div>
  <p class="focus-why">{esc(why)}</p>
  <div class="focus-facts"><span>ETF份额<b>{esc(share_fact)}</b></span><span>5日相对沪深300<b>{esc(signed(fund.get('relative_5d'), 'pct'))}</b></span><span>近14日直接新闻<b>{int(news.get('direct_count', 0))}条 · {esc(news.get('status', '数据不足'))}</b></span></div>
</article>'''

    recommend_cards = ''.join(focus_card(row, 'recommend') for row in recommendations)
    avoid_cards = ''.join(focus_card(row, 'avoid') for row in avoids)
    if not recommend_cards:
        recommend_cards = '<div class="empty-note">当前没有规则候选，不用排名靠前的ETF强行补位。</div>'
    if not avoid_cards:
        avoid_cards = '<div class="empty-note">当前没有达到回避阈值的ETF，不为凑数生成名单。</div>'

    def news_items_html(news):
        items = news.get('top_items', [])[:3]
        if not items:
            return '<li>未检索到直接匹配原文；新闻证据不足，不等于利空。</li>'
        result = ''
        for item in items:
            usage = '已进入规则口径' if item.get('used_in_rule') else '报告补充·未回填规则'
            title = esc(item.get('title', ''))
            if item.get('url'):
                title = f'<a href="{esc(item.get("url"))}" target="_blank" rel="noopener">{title} ↗</a>'
            result += (
                f'<li>{title}<span class="news-meta">{esc(item.get("published_at", "缺失"))} · '
                f'{esc(item.get("source", "未知来源"))} · {esc(item.get("source_tier", "公开媒体"))} · '
                f'<span class="context-badge">{esc(usage)}</span></span></li>'
            )
        return result

    def deep_card(row):
        fund = row.get('fund_flow', {})
        news = row.get('news_flow', {})
        is_recommend = row.get('role') == '推荐关注ETF'
        kind = 'recommend' if is_recommend else 'avoid'
        if is_recommend:
            why = row.get('why_selected') or row.get('reason', '数据不足')
            action = f"{row.get('alert_level', '待确认')}｜{row.get('verdict', '推荐观察')}｜{row.get('action', '等待确认')}"
            next_left_label, next_left = '转为可跟踪条件', row.get('confirm_next', '数据不足')
            next_right_label, next_right = '失效条件', row.get('invalidate', '数据不足')
        else:
            why = f"回避分{float(row.get('avoid_score', 0)):.1f}；{row.get('reason', '数据不足')}"
            action = f"{row.get('alert_level', '中')}预警｜{row.get('action', '谨慎观察，不追涨')}"
            next_left_label, next_left = '移出回避名单条件', row.get('reconsider', '数据不足')
            next_right_label, next_right = '已有仓位说明', row.get('position_note', '只限制新增，不生成卖出指令。')
        return f'''<article class="deep-card {kind}" data-etf-code="{esc(row.get('code', ''))}">
  <div class="deep-head"><div><div class="deep-role">{esc(row.get('role', '研究观察'))}</div><div class="deep-title">{esc(row.get('name', ''))} <small>{esc(row.get('code', ''))}</small></div></div><div class="deep-action">{esc(action)}</div></div>
  <p class="focus-why"><b>为什么：</b>{esc(why)}</p>
  <div class="deep-columns">
    <div class="deep-box"><h4>资金流｜先看真实份额，再看量价代理（行情截至 {esc(fund.get('price_as_of', '缺失'))}）</h4><p><b>{esc(fund.get('conclusion', '数据不足'))}</b></p><p>{esc(fund.get('share_evidence', '数据不足'))}</p><div class="deep-metrics"><span>5日相对沪深300<b>{esc(signed(fund.get('relative_5d'), 'pct'))}</b></span><span>20日相对沪深300<b>{esc(signed(fund.get('relative_20d'), 'pct'))}</b></span><span>20日量比<b>{esc(signed(fund.get('volume_ratio_20d'), 'x'))}</b></span><span>撤退风险<b>{esc(signed(fund.get('withdrawal_risk')))}</b></span></div><p>{esc(fund.get('market_leverage_context', '全市场两融数据不足。'))}</p></div>
    <div class="deep-box"><h4>新闻流｜{esc(news.get('window_start', '缺失'))} 至 {esc(news.get('as_of_date', '缺失'))}，最多列3条原文</h4><p><b>{esc(news.get('conclusion', '新闻证据不足，不等于利空。'))}</b></p><ul class="news-list">{news_items_html(news)}</ul><p>{esc(news.get('limitation', '新闻不等于资金。'))}</p></div>
  </div>
  <div class="deep-cross"><b>资金×新闻交叉判断：</b>{esc(row.get('cross_read', '数据不足'))}</div>
  <div class="deep-next"><div><b>{esc(next_left_label)}</b>{esc(next_left)}</div><div><b>{esc(next_right_label)}</b>{esc(next_right)}</div></div>
</article>'''

    deep_html = ''.join(deep_card(row) for row in deep_dives)
    if not deep_html:
        deep_html = '<div class="empty-note">暂无达到固定筛选阈值的ETF，逐只深挖不强行补位。</div>'

    module_cards = ''
    for item in modules:
        evidence_html = ''
        for row in item.get('evidence', []):
            source_link = esc(row.get('source', ''))
            if row.get('url'):
                source_link = f'<a href="{esc(row.get("url"))}" target="_blank" rel="noopener">{source_link} ↗</a>'
            evidence_html += (
                '<li>'
                f'<span class="evidence-label">{esc(row.get("label", ""))}</span>'
                f'<span class="evidence-value">{esc(row.get("value", "数据不足"))}</span>'
                f'<span class="evidence-meta">{esc(row.get("kind", "真实数据"))} · {source_link} · 截至 {esc(row.get("as_of", "缺失"))}</span>'
                '</li>'
            )
        limitation = item.get('limitation') or '无额外限制说明。'
        module_cards += f'''<article class="module-card {esc(item.get('tone', 'neutral'))}">
  <div class="module-head"><div class="module-title">{int(item.get('order', 0))}. {esc(item.get('title', ''))}</div><div class="module-state">{esc(item.get('status', '中性'))} · 置信{esc(item.get('confidence', '低'))}</div></div>
  <p class="module-conclusion">{esc(item.get('conclusion', '数据不足'))}</p>
  <ul class="evidence-list">{evidence_html}</ul>
  <div class="module-meaning"><b>对持仓意味着什么</b>{esc(item.get('implication', ''))}</div>
  <div class="module-watch"><b>下一次看什么才算确认</b>{esc(item.get('watch', ''))}</div>
  <details class="module-limit"><summary>口径与限制</summary><p>{esc(limitation)}</p></details>
</article>'''

    quality_rows = ''.join(
        f'<tr><td>{esc(row.get("source", ""))}</td><td>{esc(row.get("latest") or "缺失")}</td><td>{esc(row.get("status", ""))}</td><td>{esc(row.get("use", ""))}</td></tr>'
        for row in diagnostics.get('data_quality', [])
    )
    return f'''<section class="report-section evidence-first">
<div class="sec-title">今天先看结论</div>
<div class="today-brief"><div class="today-status">{esc(overall.get('model_status', '研究观察'))} · 市场{esc(overall.get('status', '中性'))} · 截至{esc(diagnostics.get('market_data_date', diagnostics.get('as_of_date', '')))}</div>
<h2>{esc(overall.get('conclusion', '数据不足'))}</h2><p class="today-action">{esc(overall.get('action', ''))}</p><div class="four-lines">{lines_html}</div></div>
<div class="sec-title">每日ETF推荐与回避预警</div>
<div class="daily-alert-bar"><div class="daily-alert-title">{esc(daily_alerts.get('display_title', f'今日推荐关注 {len(recommendations)} 只｜今日回避预警 {len(avoids)} 只'))}</div><div class="daily-alert-meta">预警日 {esc(daily_alerts.get('date', diagnostics.get('as_of_date', '缺失')))}<br>每日流水线重新计算，名单不固定</div></div>
<div class="focus-grid"><section class="focus-panel recommend-panel"><div class="focus-panel-head"><b>今日推荐关注 · {len(recommendations)}只</b><span>研究名单，不等于自动买入</span></div><div class="focus-list">{recommend_cards}</div></section><section class="focus-panel avoid-panel"><div class="focus-panel-head"><b>今日回避预警 · {len(avoids)}只</b><span>限制新增，不等于卖出或做空</span></div><div class="focus-list">{avoid_cards}</div></section></div>
<div class="sec-title">逐只ETF资金流与新闻流深挖</div><div class="deep-dive-wrap">{deep_html}</div>
<div class="sec-title">0–7 八项市场诊断</div><div class="module-grid">{module_cards}</div>
<details class="quality-fold"><summary>数据新鲜度与缺口</summary><table class="quality-table"><thead><tr><th>来源</th><th>最新日期</th><th>状态</th><th>用途</th></tr></thead><tbody>{quality_rows}</tbody></table></details>
</section>'''

def gen_top_summary(model_data, econ_data):
    """生成信息优先的今日执行摘要：实际多头组合、弱势观察与交易边界。"""
    d = model_data['latest_decision']
    state = d.get('market_state', {})
    views = build_signal_views(model_data)
    longs = views['long_candidates']
    avoids = views['avoid_watch']
    planned_position = min(1.0, sum(float(p.get('weight', 0)) for p in longs))
    risk_cap = float(state.get('risk_budget', d.get('risk_budget', 0)) or 0)
    cash_position = max(0.0, 1.0 - planned_position)
    handoff = model_data.get('handoff', {})
    state_name = {'risk_on': '风险偏好', 'neutral': '中性轮动', 'stress': '压力防守'}.get(state.get('name'), state.get('name', '未知'))
    long_names = '、'.join(p.get('name', '') for p in longs) or '暂无实际入选ETF'
    avoid_names = '、'.join(p.get('name', '') for p in avoids) or '暂无达到回避条件的ETF'
    if longs:
        core_text = (f'{state_name}：执行{d.get("decision", "观望")}，计划仓位{planned_position:.1%}，'
                     f'做多{long_names}；{avoid_names}列入弱势观察。')
    else:
        core_text = (f'{state_name}：当前没有通过规则门槛的多头仓位，保持观望；'
                     f'{avoid_names}列入弱势观察。')

    long_items = ""
    for lp in longs:
        long_items += (
            f'<div class="sig-item trade-item">'
            f'<span class="sig-copy"><span class="sig-name">{esc(lp.get("name", ""))}</span>'
            f'<span class="sig-meta">{esc(lp.get("code", ""))} · {esc(lp.get("sector", ""))}</span></span>'
            f'<span class="sig-facts"><b>仓位 {float(lp.get("weight", 0)):.1%}</b>'
            f'<span>评分 {float(lp.get("score", 0)):+.2f}</span>'
            f'<span>启动 {float(lp.get("early_entry", 0)):.2f} · 拥挤 {float(lp.get("crowding", 0)):.2f}</span></span>'
            f'</div>\n'
        )
    if not long_items:
        long_items = '<div class="empty-note">当前无实际多头仓位；不会用全池排名前三自动补位。</div>'

    short_items = ""
    for lp in avoids:
        withdrawal = float(lp.get('withdrawal_risk', 0))
        action = '降低暴露' if withdrawal >= WITHDRAWAL_WATCH_THRESHOLD else '暂不新增'
        short_items += (
            f'<div class="sig-item trade-item">'
            f'<span class="sig-copy"><span class="sig-name">{esc(lp.get("name", ""))}</span>'
            f'<span class="sig-meta">{esc(lp.get("code", ""))} · {esc(lp.get("sector", ""))}</span></span>'
            f'<span class="sig-facts"><b>{action}</b>'
            f'<span>评分 {float(lp.get("score", 0)):+.2f}</span>'
            f'<span>撤退风险 {withdrawal:.2f}</span></span>'
            f'</div>\n'
        )
    if not short_items:
        short_items = '<div class="empty-note">当前无达到回避条件的ETF，也无已验证空头信号。</div>'

    return f"""<div class="top-summary">
  <div class="core-view">
    <div class="cv-label">今日执行摘要</div>
    <div class="cv-text">{esc(core_text)}</div>
    <div class="strategy-strip">
      <div class="strategy-cell"><span>市场状态</span><b>{esc(state_name)}</b></div>
      <div class="strategy-cell"><span>组合决策</span><b>{esc(d.get('decision', '观望'))}</b></div>
      <div class="strategy-cell"><span>计划仓位</span><b>{planned_position:.1%}</b></div>
      <div class="strategy-cell"><span>风险上限</span><b>{risk_cap:.0%}</b></div>
      <div class="strategy-cell"><span>现金/未配置</span><b>{cash_position:.1%}</b></div>
    </div>
  </div>
  <div class="signal-grid">
    <div class="signal-card long">
      <div class="sig-header">
        <span class="sig-title">做多计划 · 规则主模型</span>
        <span class="sig-tag">目标 {planned_position:.1%}</span>
      </div>
{long_items}    </div>
    <div class="signal-card short">
      <div class="sig-header">
        <span class="sig-title">做空观察 / 回避</span>
        <span class="sig-tag">非空头交易</span>
      </div>
{short_items}    </div>
  </div>
  <div class="execution-grid">
    <div class="execution-note"><b>复核与结算</b><span>下一流水线复核日 {esc(handoff.get('next_trading_date', '待确认'))}；本条决策按历史标签口径自 {esc(d.get('date', ''))} 起算，持有 {HOLDING_PERIOD} 个交易日，预计 {esc(handoff.get('settlement_date', '待确认'))} 结算。若到下一交易日才首次执行，必须先重跑流水线。</span></div>
    <div class="execution-note"><b>失效与退出</b><span>下一次日更若不再进入实际多头组合，则取消新增；当前模型没有盘中止损价，不在页面虚构价格点位。</span></div>
    <div class="execution-note caution"><b>做空边界</b><span>弱势排名只表示回避或降低暴露，不代表可直接融券做空；当前模型未验证券源、借券成本及空头收益。</span></div>
  </div>
</div>"""


def gen_market_state(model_data, econ_data):
    """市场状态与动态风险预算：把原本埋在模型输出里的状态显式呈现。"""
    d = model_data['latest_decision']
    state = d.get('market_state', {})
    name = {'risk_on': '风险偏好', 'neutral': '中性轮动', 'stress': '压力防守'}.get(state.get('name'), state.get('name', '未知'))
    budget = float(state.get('risk_budget', 0))
    cards = [
        ('市场状态', name, '由宽度、动量、波动和回撤共同判定'),
        ('风险预算', f'{budget:.0%}', '状态为压力时自动收缩总仓位'),
        ('市场宽度', f'{float(state.get("breadth", 0)):.0%}', '可用风险资产上涨占比'),
        ('5日动量', fmt_pct(float(state.get('momentum_5d', 0))), '沪深300近5日动量'),
        ('20日波动', f'{float(state.get("volatility_20d", 0)):.1f}%', '波动上升时降低追涨权重'),
        ('20日回撤', f'{float(state.get("drawdown_20d", 0)):.1f}%', '回撤触发防守观察'),
    ]
    html_cards = ''.join(f'<div class="state-cell"><div class="state-label">{esc(k)}</div><div class="state-value">{esc(v)}</div><div class="state-note">{esc(n)}</div></div>' for k, v, n in cards)
    return f'''<section class="report-section"><div class="sec-title">一、市场状态与风险预算</div>
<div class="state-grid">{html_cards}</div>
<div class="section-note">风险预算不是收益预测，而是对市场环境的仓位上限；当前模型覆盖 <strong>{int(d.get('universe_count', 0))} 只 ETF</strong>，按同类组限制重复持仓。</div>
</section>'''


def gen_external_review(model_data, econ_data):
    """外部政策、行业、宏观与交易所数据源摘要。"""
    d = model_data['latest_decision']
    ext = d.get('external_sentiment', {})
    review = model_data.get('external_review', {})
    events = review.get('events', [])[:3]
    post_events = review.get('post_decision_events', [])[:3]

    def render_event(x, status):
        return f'''<article class="event-card"><div class="event-meta">{esc(x.get('published_at',''))} · {esc(x.get('source',''))} · {esc(x.get('event_type',''))} · 影响{esc(x.get('impact','未知'))} · {esc(status)}</div>
<div class="event-title">{esc(x.get('title',''))} <a href="{esc(x.get('url','#'))}" target="_blank" rel="noopener">原文 ↗</a></div>
<p><b>判断：</b>{esc(x.get('implication',''))}</p><p><b>涉及：</b>{esc('、'.join(x.get('sectors', [])))} · <b>方向：</b>{esc(x.get('direction','中性'))}</p></article>'''

    event_cards = ''.join(render_event(x, '已纳入本次信息集') for x in events)
    if not event_cards: event_cards = '<div class="empty-note">暂无通过日期校验的近期事件；本日不使用无法确认日期的标题。</div>'
    post_cards = ''.join(render_event(x, '盘后新增 · 未进入本次信号') for x in post_events)
    post_section = (f'<details class="post-news"><summary>盘后新增观察（{len(post_events)}条，未进入本次信号）</summary>{post_cards}</details>'
                    if post_cards else '')
    newspapers = model_data.get('latest_newspapers', {})
    paper_names = ['中国证券报', '上海证券报', '证券时报', '证券日报']
    newspaper_date = d.get('date', model_data.get('summary', {}).get('report_date', ''))
    paper_cards = ''
    for paper in paper_names:
        titles = newspapers.get(paper, [])
        items = ''.join(f'<li>{esc(title)}</li>' for title in titles) or '<li style="color:var(--muted)">今日暂无数据</li>'
        paper_cards += f'<div class="np-card"><div class="np-src">{esc(paper)}</div><ul>{items}</ul></div>'
    return f'''<section class="report-section"><div class="sec-title">二、外部信息与资金行为</div>
<div class="external-layout"><div class="card"><div class="card-title">本次模型输入 · 发布日≤{esc(d.get('date', ''))}</div>{event_cards}{post_section}
<div class="section-note">外部情绪分 <strong class="{cls_val(ext.get('score', 0))}">{float(ext.get('score', 0)):.3f}</strong> · 盘后新增事件单独展示，不回填本次决策；无法确认日期的内容不进入模型。</div></div>
<div class="card"><div class="card-title">四大报 · 当日全部标题（{esc(newspaper_date)}）</div>
<div class="np-grid compact-paper-grid">{paper_cards}</div>
<div class="section-note">四大报只作为公开叙事参考，不代表机构仓位，也不单独触发买入；需要与价格、成交和资金行为交叉确认。</div></div></div>
</section>'''


def gen_adaptation_review(model_data, econ_data):
    review = model_data.get('adaptation_review', {})
    rows = ''.join(f'<tr><td>{esc(k)}</td><td class="{cls_val(v["model"])}">{fmt_pct(v["model"])}</td><td>{fmt_pct(v["bench"])}</td><td class="{cls_val(v["alpha"])}">{fmt_pct(v["alpha"])}</td><td>{v["win_rate"]:.1f}%</td></tr>' for k, v in review.get('windows', {}).items())
    return f'''<section class="report-section"><div class="sec-title">模型迭代：先看样本外是否真的改善</div>
<div class="card"><div class="card-title">滚动样本外回顾</div><table><thead><tr><th>窗口</th><th>模型</th><th>沪深300</th><th>Alpha</th><th>胜率</th></tr></thead><tbody>{rows}</tbody></table>
<div class="section-note">全样本基准采用同期买入持有；滚动窗口采用决策日匹配收益。最大复合净值回撤约 <strong>{float(review.get('max_drawdown', 0)):.2f}%</strong>。{esc(review.get('action', ''))}</div></div>
<div class="adapt-grid"><div class="adapt-box"><b>当前结论</b><p>{esc(review.get('action', '暂不调参'))}</p></div><div class="adapt-box"><b>调优护栏</b><p>{esc(review.get('guardrail', ''))}</p></div></div>
</section>'''


def gen_model_fold(model_data, econ_data):
    logit, ols = econ_data['logit'], econ_data['ols']
    selective = logit.get('selective', {})
    eligible = bool(logit.get('production_eligible'))
    status = '通过生产护栏' if eligible else 'Shadow观察'
    skill = '通过' if logit.get('has_predictive_skill') else '未通过'
    brier = logit.get('brier_score')
    base_brier = logit.get('baseline_brier_score')
    brier_text = (f'{float(brier):.4f} vs 基准 {float(base_brier):.4f}'
                  if brier is not None and base_brier is not None else '暂无')
    trades = int(selective.get('trade_count', selective.get('selected_dates', 0)) or 0)
    oof_dates = int(selective.get('oof_trade_dates', selective.get('oof_dates', 0)) or 0)
    coverage = float(selective.get('trade_date_coverage', selective.get('date_coverage', 0)) or 0)
    win_rate = selective.get('portfolio_win_rate', selective.get('win_rate'))
    win_text = f'{float(win_rate) * 100:.1f}%' if win_rate is not None else '暂无'
    ci = selective.get('portfolio_win_rate_ci_95', selective.get('win_rate_ci_95', [None, None]))
    ci_text = (f'{float(ci[0]) * 100:.1f}%–{float(ci[1]) * 100:.1f}%'
               if len(ci) == 2 and ci[0] is not None and ci[1] is not None else '暂无')
    mean_alpha = selective.get('mean_portfolio_net_alpha', selective.get('mean_net_alpha'))
    alpha_text = f'{float(mean_alpha):+.2f}%' if mean_alpha is not None else '暂无'
    return f'''<section class="report-section"><div class="sec-title">技术模型附录（可展开）</div>
<details class="model-fold"><summary>模型卡片：规则模型负责组合，Logit/OLS负责诊断（点击展开）</summary>
<div class="model-grid"><div class="model-box"><div class="card-title">规则模型 · 实际决策公式</div><p class="formula">Score = 状态化趋势/回归 + 启动/资金代理 + 新闻预期差 + 市场一致性 − 陈旧拥挤 − 撤退风险</p><p>价格和资金使用 T-1；外部事件必须满足真实日期≤决策日。风险预算由宽度、20日动量、波动和回撤决定，持仓再按逆波动率分配。</p></div><div class="model-box"><div class="card-title">路径 A · 三日净Alpha模型</div><div class="model-number">{status}</div><p>目标为ETF从 T 开盘持有至 T+2 收盘，相对沪深300并扣除0.05%往返成本。样本外能力检验{skill}；未过护栏时不参与主推荐。</p></div></div>
<div class="model-grid"><div class="model-box"><div class="card-title">当前参数护栏</div><p>买入门槛 {BUY_THRESHOLD:.2f} · 持有期 {HOLDING_PERIOD} 日 · 情绪滞后系数 -1.0 · 份额流向暂只作诊断。</p></div><div class="model-box"><div class="card-title">日间交接</div><p>当日预测先进入 pending；持有期结束、收益和成本结算后，才允许写入经验库并参与滚动 OOS 复核。</p></div></div>
<div class="model-grid"><div class="model-box"><div class="card-title">Logit · Purged Walk-Forward</div><div class="model-number">OOF {logit.get('cv_accuracy', 0):.1f}% · 基准 {logit.get('baseline_accuracy', 0):.1f}%</div><p>Brier（越低越好）：{brier_text}。训练与验证之间隔离2个交易日，并只用过去的OOF结果校准概率。</p></div><div class="model-box"><div class="card-title">高置信组合 · P(净Alpha&gt;0) ≥ 60%</div><div class="model-number">{win_text} · {trades}笔</div><p>只统计最多3只、持有期不重叠的组合交易；95%区间 {ci_text}，平均净Alpha {alpha_text}，覆盖 {trades}/{oof_dates} 个OOF日期（{coverage:.1%}）。</p></div></div>
<div class="model-grid"><div class="model-box"><div class="card-title">概率模型状态</div><div class="model-number">{status}</div><p>准确率需领先基准至少2个百分点、Brier优于基准、至少40个不重叠结算日，且4折中至少3折平均净Alpha为正。</p></div><div class="model-box"><div class="card-title">OLS · 净Alpha诊断</div><div class="model-number">OOS R² {float(ols.get('cv_r2', 0)):.3f}</div><p>标准误按决策日聚类；线性模型只用于观察因子方向和稳定性，不负责顶部推荐。</p></div></div>
<details class="inner-fold"><summary>展开系数、因素重要性与图表</summary>{gen_section_5_features(model_data, econ_data)}</details>
</details></section>'''


def gen_section_1_conclusion(model_data, econ_data):
    """一、核心结论 — callout + 4个关键指标卡片"""
    s = model_data['summary']
    d = model_data['latest_decision']
    ret = s['cumulative_return']
    win_rate = s['win_rate']
    pl_ratio = s['profit_loss_ratio']
    sent = d.get('sentiment_score', 0)

    # callout
    callout = f'''<h2>一、核心结论</h2>
<div class="callout warning">
  <p><strong>模型决策：{esc(d.get("decision", "持币观望"))}</strong>。基于Walk-Forward回测，胜率{win_rate:.1f}%，累计收益{fmt_pct(ret)}。</p>
  <p><strong>情绪信号</strong>：四大报情绪{sent:.2f}（看多{d.get("bull_signals",0)}/看空{d.get("bear_signals",0)}），趋势{esc(d.get("trend","震荡"))}。</p>
</div>'''

    # 4 metric cards
    cards = f'''<div class="metrics" style="grid-template-columns:repeat(4,1fr)">
  <div class="metric"><div class="ml">累计收益</div><div class="mv {cls_val(ret)}">{fmt_pct(ret)}</div></div>
  <div class="metric"><div class="ml">胜率</div><div class="mv">{win_rate:.1f}%</div><div class="ms">{s["wins"]}胜/{s["losses"]}负</div></div>
  <div class="metric"><div class="ml">盈亏比</div><div class="mv">{pl_ratio:.2f}</div></div>
  <div class="metric"><div class="ml">情绪分</div><div class="mv {cls_val(sent)}">{sent:.3f}</div></div>
</div>'''

    return callout + '\n' + cards


def gen_section_3_sentiment(model_data, econ_data):
    """媒体叙事与融资情绪诊断 — 情绪卡片 + 四大报标题"""
    d = model_data['latest_decision']
    newspapers = model_data.get('latest_newspapers', {})
    sent = d.get('sentiment_score', 0)
    bull = d.get('bull_signals', 0)
    bear = d.get('bear_signals', 0)
    ext = d.get('external_sentiment', {})

    paper_names = ['中国证券报', '上海证券报', '证券时报', '证券日报']
    np_rows = ""
    for name in paper_names:
        titles = newspapers.get(name, [])
        title_str = ' / '.join(titles[:3]) if titles else '今日暂无数据'
        np_rows += f'<tr><td>{esc(name)}</td><td style="font-size:0.78rem">{esc(title_str)}</td></tr>\n'

    return f'''<h2>媒体叙事与融资情绪诊断</h2>
<div class="card">
  <div class="card-title">外部政策/行业/宏观情绪</div>
  <div class="metrics" style="grid-template-columns:repeat(3,1fr)">
    <div class="metric"><div class="ml">外部情绪分</div><div class="mv {cls_val(ext.get('score', 0))}">{float(ext.get('score', 0)):.3f}</div></div>
    <div class="metric"><div class="ml">有效标题</div><div class="mv">{int(ext.get('count', 0))}</div></div>
    <div class="metric"><div class="ml">来源类别</div><div class="mv">{len(ext.get('categories', {}))}</div></div>
  </div>
</div>
<div class="card">
  <div class="card-title">媒体叙事（四大报）</div>
  <div class="metrics" style="grid-template-columns:repeat(3,1fr)">
    <div class="metric"><div class="ml">情绪分</div><div class="mv {cls_val(sent)}">{sent:.3f}</div></div>
    <div class="metric"><div class="ml">看多标题</div><div class="mv" style="color:var(--green)">{bull}</div></div>
    <div class="metric"><div class="ml">看空标题</div><div class="mv" style="color:var(--accent2)">{bear}</div></div>
  </div>
</div>
<div class="card">
  <div class="card-title">今日四大报标题摘要</div>
  <table>
    <thead><tr><th>报纸</th><th>代表性标题</th></tr></thead>
    <tbody>
{np_rows}    </tbody>
  </table>
</div>'''


def gen_section_4_performance(model_data, econ_data):
    """四、模型表现回顾 — 指标 + 图表 + 交易记录"""
    s = model_data['summary']
    d = model_data['latest_decision']
    ret = s['cumulative_return']
    alpha = s['alpha']

    # 6个指标卡片
    cards = f'''<div class="metric"><div class="ml">累计收益率</div><div class="mv {cls_val(ret)}">{fmt_pct(ret)}</div><div class="ms">¥{fmt_money(s["initial_capital"])} → ¥{fmt_money(s["final_capital"])}</div></div>
<div class="metric"><div class="ml">Alpha vs 沪深300</div><div class="mv {cls_val(alpha)}">{fmt_pct(alpha)}</div><div class="ms">沪深300: {fmt_pct(s["hs300_return"])}</div></div>
<div class="metric"><div class="ml">胜率</div><div class="mv">{s["win_rate"]:.1f}%</div><div class="ms">{s["wins"]}胜 / {s["losses"]}负</div></div>
<div class="metric"><div class="ml">盈亏比</div><div class="mv">{s["profit_loss_ratio"]:.2f}</div><div class="ms">均盈{fmt_pct(s["avg_profit"])} / 均亏{fmt_pct(s["avg_loss"])}</div></div>
<div class="metric"><div class="ml">交易日数</div><div class="mv">{s["trading_days"]}</div></div>
<div class="metric"><div class="ml">总交易次数</div><div class="mv">{s["experience_count"]}</div></div>
<div class="metric"><div class="ml">年化收益</div><div class="mv {cls_val(s.get("annualized_return", 0))}">{fmt_pct(s.get("annualized_return", 0))}</div></div>
<div class="metric"><div class="ml">最大回撤</div><div class="mv {cls_val(s.get("max_drawdown", 0))}">{fmt_pct(s.get("max_drawdown", 0))}</div><div class="ms">复合净值口径</div></div>
<div class="metric"><div class="ml">往返成本</div><div class="mv">{s.get("round_trip_cost_rate", 0) * 100:.2f}%</div><div class="ms">佣金+价差/滑点</div></div>'''

    # 图表
    charts = '''<div class="chart-card"><div class="card-title">累计收益率走势</div><div id="chart-cum" class="chart"></div></div>
<div class="chart-card"><div class="card-title">月度收益对比</div><div id="chart-month" class="chart"></div></div>
<div class="chart-card"><div class="card-title">ETF 胜率分布</div><div id="chart-etf" class="chart"></div></div>'''

    # ETF绩效表
    perf = d.get('etf_performance', [])
    perf_rows = ""
    for e in perf:
        perf_rows += f'<tr><td>{esc(e["name"])}</td><td>{e["rec_count"]}</td><td class="{cls_val(e["avg_return"])}">{fmt_pct(e["avg_return"])}</td><td>{e["win_rate"]:.1f}%</td><td>{esc(e["assessment"])}</td></tr>\n'

    perf_table = f'''<div class="card">
  <div class="card-title">各ETF回测表现</div>
  <table>
    <thead><tr><th>ETF名称</th><th>推荐次数</th><th>平均收益</th><th>胜率</th><th>评估</th></tr></thead>
    <tbody>
{perf_rows}    </tbody>
  </table>
</div>'''

    # 最近交易记录
    summaries = model_data.get('all_daily_summaries', [])
    recent = summaries[-20:][::-1]
    rec_rows = ""
    for sm in recent:
        rec_rows += f'<tr><td>{esc(sm["date"])}</td><td>{trend_tag(sm["trend"])}</td><td>{esc(sm["etfs"])}</td><td class="{cls_val(sm["return"])}">{fmt_pct(sm["return"])}</td><td class="{cls_val(sm["hs300"])}">{fmt_pct(sm["hs300"])}</td></tr>\n'

    rec_table = f'''<div class="card">
  <div class="card-title">最近交易记录</div>
  <table>
    <thead><tr><th>日期</th><th>研判</th><th>推荐ETF</th><th>收益</th><th>沪深300</th></tr></thead>
    <tbody>
{rec_rows}    </tbody>
  </table>
</div>'''

    return f'''<section class="report-section"><div class="sec-title">历史表现与回测（已结算至{esc(s["end_date"])}）</div>
<div class="metrics" style="grid-template-columns:repeat(3,1fr)">
{cards}
</div>
{charts}
<details class="detail-fold"><summary>展开各ETF表现与最近20条交易</summary>{perf_table}{rec_table}</details>
</section>'''


def gen_section_5_features(model_data, econ_data):
    """五、特征显著性与模型诊断 — Logit系数 + 因素重要性 + 公式"""
    logit = econ_data['logit']
    ols = econ_data['ols']

    # Logit系数表（精简，只显示显著的前10个）
    logit_rows = ""
    for c in logit['coefficients'][:10]:
        var = c['variable']
        sig = c.get('sig', '')
        logit_rows += f'<tr><td>{esc(var)}</td><td class="{cls_val(c["coef"])}">{fmt_coef(c["coef"])}</td><td>{fmt_num(c["p"])}</td><td><b>{esc(sig)}</b></td></tr>\n'

    logit_table = f'''<div class="card">
  <div class="card-title">净Alpha正则化 Logit 系数（样本外准确率={logit["accuracy"]}%）</div>
  <table>
    <thead><tr><th>特征</th><th>系数</th><th>p值</th><th>显著性</th></tr></thead>
    <tbody>
{logit_rows}    </tbody>
  </table>
</div>'''

    # 因素重要性
    fi = ols['factor_importance']
    fi_rows = ""
    for f in fi[:8]:
        sig = f.get('sig', '')
        fi_rows += f'<tr><td>{esc(f["factor"])}</td><td class="{cls_val(f["beta"])}">{fmt_coef(f["beta"])}</td><td>{fmt_num(f["p"])}</td><td>{fmt_num(f["importance"])}</td></tr>\n'

    fi_table = f'''<div class="card">
  <div class="card-title">因素重要性（|β|×σ）</div>
  <table>
    <thead><tr><th>因素</th><th>β</th><th>p值</th><th>重要性</th></tr></thead>
    <tbody>
{fi_rows}    </tbody>
  </table>
</div>'''

    # 图表
    charts = '''<div class="chart-card"><div class="card-title">因素重要性排名</div><div id="chart-imp" class="chart"></div></div>'''

    return f'''<h2>附录：特征显著性与模型诊断</h2>
{logit_table}
{fi_table}
{charts}'''


def gen_date_badge(model_data):
    date = model_data['summary']['report_date']
    return f"""<div class="date-bar">
  <span class="badge">{esc(date)}</span>
  <div class="sub">规则模型 + 计量交叉验证 · 每日自动迭代</div>
</div>"""


def gen_overview(model_data):
    s = model_data['summary']
    ret = s['cumulative_return']
    alpha = s['alpha']
    cards = [
        f'<div class="metric"><div class="ml">累计收益率</div><div class="mv {cls_val(ret)}">{fmt_pct(ret)}</div><div class="ms">¥{fmt_money(s["initial_capital"])} → ¥{fmt_money(s["final_capital"])}</div></div>',
        f'<div class="metric"><div class="ml">Alpha vs 沪深300</div><div class="mv {cls_val(alpha)}">{fmt_pct(alpha)}</div><div class="ms">沪深300: {fmt_pct(s["hs300_return"])}</div></div>',
        f'<div class="metric"><div class="ml">胜率</div><div class="mv">{s["win_rate"]:.1f}%</div><div class="ms">{s["wins"]}胜 / {s["losses"]}负</div></div>',
        f'<div class="metric"><div class="ml">盈亏比</div><div class="mv">{s["profit_loss_ratio"]:.2f}</div><div class="ms">均盈{fmt_pct(s["avg_profit"])} / 均亏{fmt_pct(s["avg_loss"])}</div></div>',
        f'<div class="metric"><div class="ml">交易日数</div><div class="mv">{s["trading_days"]}</div><div class="ms">{s["start_date"]} ~ {s["end_date"]}</div></div>',
        f'<div class="metric"><div class="ml">经验库</div><div class="mv">{s["experience_count"]}</div><div class="ms">上限{s["experience_limit"]}条</div></div>',
        f'<div class="metric"><div class="ml">年化收益</div><div class="mv {cls_val(s.get("annualized_return", 0))}">{fmt_pct(s.get("annualized_return", 0))}</div></div>',
        f'<div class="metric"><div class="ml">最大回撤</div><div class="mv {cls_val(s.get("max_drawdown", 0))}">{fmt_pct(s.get("max_drawdown", 0))}</div><div class="ms">复合净值口径</div></div>',
    ]
    return f"""<div class="sec-title">概况</div>
<div class="metrics">
{chr(10).join(cards)}
</div>"""


def _gen_equation(coefs, lhs, terms_per_line, suffix=None):
    """生成公式 HTML (可分行)"""
    terms = []
    for c in coefs:
        var = c['variable']
        short = VAR_SHORT.get(var, var)
        coef_str = fmt_coef(c['coef'])
        sig = c.get('sig', '')
        cls = 'coef'
        if sig:
            cls += ' sig'
            coef_str += sig
        if var == 'const':
            terms.append(f'<span class="{cls}">{coef_str}</span>')
        else:
            terms.append(f'<span class="{cls}">{coef_str}</span>·<span class="var">{short}</span>')
    if suffix:
        terms.append(suffix)

    lines_html = []
    idx = 0
    for line_num, n in enumerate(terms_per_line):
        chunk = terms[idx:idx + n]
        idx += n
        if not chunk:
            break
        if line_num == 0:
            line = f'{lhs} = ' + ' <span class="op">+</span> '.join(chunk)
        else:
            indent = '&nbsp;' * 7
            line = f'{indent} <span class="op">+</span> ' + ' <span class="op">+</span> '.join(chunk)
        lines_html.append(f'<div class="formula">{line}</div>')
    while idx < len(terms):
        n = terms_per_line[-1]
        chunk = terms[idx:idx + n]
        idx += n
        indent = '&nbsp;' * 7
        line = f'{indent} <span class="op">+</span> ' + ' <span class="op">+</span> '.join(chunk)
        lines_html.append(f'<div class="formula">{line}</div>')
    return '\n'.join(lines_html)


def gen_formulas(model_data, econ_data):
    logit = econ_data['logit']
    ols = econ_data['ols']

    # ── 规则模型公式（精简） ──
    rule_card = """<div class="card">
  <div class="card-title">规则模型 · 评分逻辑</div>
  <div class="formula-box">
    <div class="f-title">走势研判</div>
    <div class="formula">Bull<sub>s</sub> = f(S, &Delta;HS300, S&times;&Delta;HS300, Exp)</div>
    <div class="formula" style="margin-top:4px">Bear<sub>s</sub> = g(S, &Delta;HS300, &Delta;Vol)</div>
    <div class="formula" style="margin-top:4px">Trend = argmax(Bull<sub>s</sub>, Bear<sub>s</sub>, Neutral)</div>
    <div class="formula-legend"><b>S</b>=情绪分 <b>&Delta;HS300</b>=前日涨跌 <b>Exp</b>=经验信号 <b>&Delta;Vol</b>=量比变化</div>
  </div>
  <div class="formula-box">
    <div class="f-title">选基评分</div>
    <div class="formula">Score<sub>ETF</sub> = 3&middot;Sent + Mom + Vol + MR + Exp</div>
    <div class="formula-legend"><b>Sent</b>=情绪热点(3x) <b>Mom</b>=动量 <b>Vol</b>=量比 <b>MR</b>=均值回归 <b>Exp</b>=经验 | 选前3只高分ETF</div>
  </div>
</div>"""

    # ── OLS 公式（精简 + 附带因素重要性） ──
    ols_eq = _gen_equation(
        ols['coefficients'], 'r&#770;<sub>i,t</sub>',
        terms_per_line=[5, 4],
        suffix='&epsilon;<sub>i,t</sub>'
    )
    lasso_kept = ols.get('lasso_features', [])
    lasso_kept_str = ' + '.join(
        f'&beta;<sub>{i+1}</sub>&middot;{VAR_SHORT.get(v, v)}'
        for i, v in enumerate(lasso_kept)
    )
    lasso_removed = ols.get('lasso_removed', [])
    lasso_removed_str = '、'.join(VAR_SHORT.get(v, v) for v in lasso_removed) if lasso_removed else '无'

    # 因素重要性表（精简，合并到OLS卡片下方）
    fi = ols['factor_importance']
    fi_rows = ""
    for f in fi:
        sig_str = f" {f['sig']}" if f.get('sig') else ''
        fi_rows += (
            f'<tr>'
            f'<td>{esc(f["factor"])}</td>'
            f'<td class="{cls_val(f["beta"])}">{fmt_coef(f["beta"])}</td>'
            f'<td>{fmt_num(f["p"], 4)}{sig_str}</td>'
            f'<td>{fmt_num(f["sigma"])}</td>'
            f'<td>{fmt_num(f["importance"])}</td>'
            f'</tr>\n'
        )
    sig_factors = [f for f in fi if f.get('sig')]
    if sig_factors:
        fi_conclusion = '显著: ' + '、'.join(f'{f["factor"]}({f["sig"]})' for f in sig_factors)
    else:
        fi_conclusion = '所有因素均不显著(p>=0.1)'

    ols_card = f"""<div class="card">
  <div class="card-title">OLS 回归 &middot; 收益率预测</div>
  <div class="formula-box">
    <div class="f-title">拟合方程（N={ols["n"]}, R&sup2;={ols["r2"]}, F={ols["f_stat"]}）</div>
{ols_eq}
    <div class="formula-legend">变量: <b>S</b>=情绪 <b>B</b>=看涨 <b>D</b>=看跌 <b>P</b>=涨跌% <b>VR</b>=量比 <b>I</b>=日内% <b>M</b>=提及 <b>C</b>=次数 | ***p&lt;0.01 **p&lt;0.05 *p&lt;0.1</div>
  </div>
  <div class="formula-box">
    <div class="f-title">Lasso（&alpha;={ols.get("lasso_alpha", "N/A")}）</div>
    <div class="formula">r&#770; = &beta;<sub>0</sub> + {lasso_kept_str}</div>
    <div class="formula-legend">剔除: {lasso_removed_str}</div>
  </div>
  <div class="formula-box">
    <div class="f-title">因素重要性 |&beta;|&times;&sigma;</div>
    <table style="margin-top:6px;width:100%;font-size:0.78rem">
      <tr style="border-bottom:2px solid var(--rule)">
        <td style="font-weight:600;color:var(--muted)">因素</td>
        <td style="font-weight:600;color:var(--muted)">&beta;</td>
        <td style="font-weight:600;color:var(--muted)">p</td>
        <td style="font-weight:600;color:var(--muted)">&sigma;</td>
        <td style="font-weight:600;color:var(--muted)">重要性</td>
      </tr>
{fi_rows}    </table>
    <div class="formula-legend" style="margin-top:6px">{fi_conclusion}</div>
  </div>
</div>"""

    # ── Logit 公式（精简） ──
    logit_eq = _gen_equation(
        logit['coefficients'], 'z',
        terms_per_line=[5, 4]
    )
    logit_card = f"""<div class="card">
  <div class="card-title">Logit 回归 &middot; 涨跌方向预测</div>
  <div class="formula-box">
    <div class="f-title">预测方程（N={logit["n"]}, 样本外准确率={logit["accuracy"]}%）</div>
    <div class="formula">P(y=1) = 1 / (1 + e<sup>&minus;z</sup>)</div>
{logit_eq}
    <div class="formula-legend">
      <b>y=1</b>=当日上涨 &nbsp; {esc(logit.get("accuracy_note", ""))} &nbsp; Lasso={logit.get("lasso_note", "N/A")}
    </div>
  </div>
</div>"""

    return f"""<div class="sec-title">模型公式</div>
{rule_card}
{logit_card}
{ols_card}"""


def _bull_advice(prob):
    """看好板块建议文字，prob 为 P(涨) 百分比"""
    if prob >= 65:
        return '模型看好，可重点关注'
    if prob >= 55:
        return '模型偏多，适量参与'
    if prob >= 45:
        return '多空均衡，观望为主'
    return '模型看涨概率较低，谨慎参与'


def _bear_advice(bear_prob):
    """看空预警建议文字，bear_prob 为 P(跌) 百分比"""
    if bear_prob >= 85:
        return '强烈看空，建议回避'
    if bear_prob >= 75:
        return '看空，建议减仓'
    if bear_prob >= 65:
        return '偏空，谨慎持有'
    return '略偏空，注意风险'


def gen_recommendation(model_data, econ_data):
    d = model_data['latest_decision']
    s = model_data['summary']
    date = s['report_date']

    # Logit 预测（已标准化：code/name/sector/prob[百分比数值]/direction）
    logit_preds = econ_data['logit'].get('latest_predictions', [])
    # 按名称建立查找表，供规则模型对比交叉验证使用
    logit_lookup = {}
    for lp in logit_preds:
        logit_lookup[lp.get('etf', '')] = lp

    # ── 看好板块：Logit 预测 P(涨) 最高的 3 个（概率从高到低） ──
    top3_bullish = sorted(
        logit_preds, key=lambda x: float(x.get('prob', 0)), reverse=True
    )[:3]
    bullish_items = ""
    for lp in top3_bullish:
        prob_val = float(lp.get('prob', 0))
        advice = _bull_advice(prob_val)
        name = lp.get('name', '') or lp.get('etf', '')
        bullish_items += (
            f'<div class="pick" style="flex-direction:column;align-items:stretch;gap:4px;width:100%">'
            f'<div style="display:flex;align-items:center;gap:8px">'
            f'<span class="pick-code">{esc(lp.get("code", ""))}</span>'
            f'<span class="pick-name">{esc(name)}</span>'
            f'<span class="pick-w" style="margin-left:auto">P(涨){prob_val:.1f}%</span>'
            f'</div>'
            f'<div style="display:flex;justify-content:space-between;gap:8px;font-size:0.72rem;color:var(--muted)">'
            f'<span>板块: {esc(lp.get("sector", ""))}</span>'
            f'<span>{esc(advice)}</span>'
            f'</div>'
            f'</div>\n'
        )

    # ── 看空预警：Logit 预测 P(涨) 最低（即 P(跌) 最高）的 3 个 ──
    top3_bearish = sorted(
        logit_preds, key=lambda x: float(x.get('prob', 0))
    )[:3]
    bearish_items = ""
    for lp in top3_bearish:
        prob_val = float(lp.get('prob', 0))
        bear_prob = round(100 - prob_val, 1)
        advice = _bear_advice(bear_prob)
        name = lp.get('name', '') or lp.get('etf', '')
        bearish_items += (
            f'<div class="pick" style="flex-direction:column;align-items:stretch;gap:4px;width:100%">'
            f'<div style="display:flex;align-items:center;gap:8px">'
            f'<span class="pick-code">{esc(lp.get("code", ""))}</span>'
            f'<span class="pick-name">{esc(name)}</span>'
            f'<span class="pick-w" style="margin-left:auto;background:var(--accent2);color:#fff">P(跌){bear_prob:.1f}%</span>'
            f'</div>'
            f'<div style="display:flex;justify-content:space-between;gap:8px;font-size:0.72rem;color:var(--muted)">'
            f'<span>板块: {esc(lp.get("sector", ""))}</span>'
            f'<span>{esc(advice)}</span>'
            f'</div>'
            f'</div>\n'
        )

    # ── 规则模型推荐（作为对比参考） ──
    rule_picks_html = ""
    for p in d['picks']:
        w_pct = int(p['weight'] * 100)
        lp = logit_lookup.get(p['name'], {})
        logit_dir = lp.get('direction', '')
        logit_prob = lp.get('prob', '')
        rule_picks_html += (
            f'<div class="pick">'
            f'<span class="pick-code">{esc(p["code"])}</span>'
            f'<span class="pick-name">{esc(p["name"])}<span class="pick-score">评分{p["score"]:.2f}</span></span>'
            f'<span class="pick-w">{w_pct}%</span>'
            f'<span class="pick-logit">Logit:{esc(logit_dir)}({logit_prob}%)</span>'
            f'</div>\n'
        )

    # 趋势标签与信号
    trend = trend_tag(d['trend'])
    conf = esc(d.get('confidence', ''))
    bull = d.get('bull_signals', 0)
    bear = d.get('bear_signals', 0)
    sent = d.get('sentiment_score', 0)
    # 理由与热点板块
    reason = esc(d.get('reason', ''))
    sectors = d.get('hot_sectors', [])
    sectors_str = ', '.join(f'{esc(s_["name"])}({s_["count"]})' for s_ in sectors)

    # ETF 绩效表
    perf = d.get('etf_performance', [])
    perf_rows = ""
    for e in perf:
        perf_rows += (
            f'<tr>'
            f'<td>{esc(e["name"])}</td>'
            f'<td>{e["rec_count"]}</td>'
            f'<td class="{cls_val(e["avg_return"])}">{fmt_pct(e["avg_return"])}</td>'
            f'<td>{e["win_rate"]:.1f}%</td>'
            f'<td>{esc(e["assessment"])}</td>'
            f'</tr>\n'
        )

    perf_html = f"""<div class="card">
  <div class="card-title">ETF 历史推荐绩效</div>
  <table>
    <thead><tr><th>ETF名称</th><th>推荐次数</th><th>平均收益</th><th>胜率</th><th>评估</th></tr></thead>
    <tbody>
{perf_rows}    </tbody>
  </table>
</div>"""

    # 看好板块卡片：Logit 预测 P(涨) 最高的 3 个（按概率从高到低）
    bullish_html = f"""<div class="card" style="border-color:var(--green);border-width:1.5px">
  <div class="card-title" style="color:var(--green)">看好板块 · Logit P(涨) 最高</div>
  <div class="picks" style="flex-direction:column">
{bullish_items}  </div>
</div>"""

    # 看空预警卡片：Logit 预测 P(跌) 最高的 3 个（即 P(涨) 最低）
    bearish_html = f"""<div class="card" style="border-color:var(--accent2);border-width:1.5px">
  <div class="card-title" style="color:var(--accent2)">看空预警 · Logit P(跌) 最高</div>
  <div class="picks" style="flex-direction:column">
{bearish_items}  </div>
</div>"""

    # 规则模型推荐（作为对比参考，置于看好板块下方）
    rule_compare_html = f"""<div class="card">
  <div class="card-title">规则模型推荐（对比参考）</div>
  <div class="picks">
{rule_picks_html}  </div>
  <div class="reason" style="margin-top:8px">{reason}</div>
  <div style="margin-top:8px;font-size:0.75rem;color:var(--muted)"><strong style="color:var(--accent)">报纸热点:</strong> {sectors_str}</div>
</div>"""

    # 趋势+信号概要
    signal_bar = f"""<div style="display:flex;align-items:center;gap:16px;margin-bottom:16px;flex-wrap:wrap">
  <div>{trend}</div>
  <span class="conf-pill">置信度 {conf}</span>
  <span style="font-size:0.8rem;color:var(--muted)"><span class="dot bull"></span> 多头{bull}</span>
  <span style="font-size:0.8rem;color:var(--muted)"><span class="dot bear"></span> 空头{bear}</span>
  <span style="font-size:0.8rem;color:var(--gold)">情绪分 {sent}</span>
  <span style="font-size:0.75rem;color:var(--muted)">基于 {esc(date)} 四大报 + 前日行情</span>
</div>"""

    return f"""<div class="sec-title">今日推荐</div>
{signal_bar}
<div class="rec-2col">
{bullish_html}
{bearish_html}
</div>
{rule_compare_html}
{perf_html}"""


def gen_econometric(model_data, econ_data):
    logit = econ_data['logit']
    ols = econ_data['ols']

    # ── Logit 系数表 ──
    logit_rows = ""
    for c in logit['coefficients']:
        var = c['variable']
        desc = FACTOR_DESC.get(var, '')
        sig = c.get('sig', '')
        logit_rows += (
            f'<tr>'
            f'<td>{esc(var)}</td>'
            f'<td class="{cls_val(c["coef"])}">{fmt_coef(c["coef"])}</td>'
            f'<td>{fmt_num(c["std_err"])}</td>'
            f'<td class="{cls_val(c["z"])}">{fmt_coef(c["z"], 2)}</td>'
            f'<td>{fmt_num(c["p"])}</td>'
            f'<td><b>{esc(sig)}</b></td>'
            f'<td style="font-size:0.75rem;color:var(--muted)">{esc(desc)}</td>'
            f'</tr>\n'
        )
    lasso_features_str = ', '.join(logit.get('lasso_features', []))
    logit_card = f"""<div class="card">
  <div class="card-title">Logit 回归系数表</div>
  <div class="metrics" style="grid-template-columns:repeat(2,1fr);margin-bottom:10px">
    <div class="metric"><div class="ml">正则化强度</div><div class="mv" style="font-size:1rem">L2</div></div>
    <div class="metric"><div class="ml">样本外准确率</div><div class="mv" style="font-size:1rem">{logit["accuracy"]}%</div></div>
    <div class="metric"><div class="ml">样本内诊断</div><div class="mv" style="font-size:1rem">{logit.get("in_sample_accuracy", 0)}%</div></div>
    <div class="metric"><div class="ml">验证方式</div><div class="mv" style="font-size:1rem">逐日展开</div></div>
  </div>
  <div style="font-size:0.75rem;color:var(--muted);margin-bottom:6px">Lasso保留: {esc(lasso_features_str)}</div>
  <table>
    <thead><tr><th>变量</th><th>系数</th><th>标准误</th><th>z</th><th>p值</th><th>显著</th><th>变量说明</th></tr></thead>
    <tbody>
{logit_rows}    </tbody>
  </table>
</div>"""

    # ── OLS 系数表 ──
    ols_rows = ""
    for c in ols['coefficients']:
        var = c['variable']
        desc = FACTOR_DESC.get(var, '')
        sig = c.get('sig', '')
        ols_rows += (
            f'<tr>'
            f'<td>{esc(var)}</td>'
            f'<td class="{cls_val(c["coef"])}">{fmt_coef(c["coef"])}</td>'
            f'<td>{fmt_num(c["std_err"])}</td>'
            f'<td class="{cls_val(c["t"])}">{fmt_coef(c["t"], 2)}</td>'
            f'<td>{fmt_num(c["p"])}</td>'
            f'<td><b>{esc(sig)}</b></td>'
            f'<td style="font-size:0.75rem;color:var(--muted)">{esc(desc)}</td>'
            f'</tr>\n'
        )
    ols_lasso_str = ', '.join(ols.get('lasso_features', []))
    ols_card = f"""<div class="card">
  <div class="card-title">OLS 回归系数表</div>
  <div class="metrics" style="grid-template-columns:repeat(2,1fr);margin-bottom:10px">
    <div class="metric"><div class="ml">R&sup2;</div><div class="mv" style="font-size:1rem">{ols["r2"]}</div></div>
    <div class="metric"><div class="ml">调整 R&sup2;</div><div class="mv" style="font-size:1rem">{ols["adj_r2"]}</div></div>
    <div class="metric"><div class="ml">F 统计量</div><div class="mv" style="font-size:1rem">{ols["f_stat"]}</div></div>
    <div class="metric"><div class="ml">F p值</div><div class="mv" style="font-size:1rem">{ols["f_p"]}</div></div>
  </div>
  <div style="font-size:0.75rem;color:var(--muted);margin-bottom:6px">Lasso保留: {esc(ols_lasso_str)} &nbsp; N = {ols["n"]}</div>
  <table>
    <thead><tr><th>变量</th><th>系数</th><th>标准误</th><th>t</th><th>p值</th><th>显著</th><th>变量说明</th></tr></thead>
    <tbody>
{ols_rows}    </tbody>
  </table>
</div>"""

    # ── 最新预测表 ──
    logit_preds = logit.get('latest_predictions', [])
    ols_preds = ols.get('latest_predictions', [])
    max_rows = max(len(logit_preds), len(ols_preds))
    pred_rows = ""
    for i in range(max_rows):
        lp = logit_preds[i] if i < len(logit_preds) else {}
        op = ols_preds[i] if i < len(ols_preds) else {}
        lp_prob = f'<strong>{lp.get("prob", "")}%</strong>' if lp else ''
        lp_dir_cls = 'up' if lp.get('direction') == '涨' else 'down' if lp.get('direction') == '跌' else ''
        op_ret = op.get('predicted_return')
        op_ret_str = fmt_pct(op_ret) if op_ret is not None else ''
        pred_rows += (
            f'<tr>'
            f'<td>{esc(lp.get("etf") or op.get("etf", ""))}</td>'
            f'<td>{esc(lp.get("sector") or op.get("sector", ""))}</td>'
            f'<td>{lp_prob}</td>'
            f'<td class="{lp_dir_cls}">{esc(lp.get("direction", ""))}</td>'
            f'<td>{esc(lp.get("confidence", ""))}</td>'
            f'<td class="{cls_val(op_ret)}">{op_ret_str}</td>'
            f'</tr>\n'
        )

    pred_card = f"""<div class="card">
  <div class="card-title">最新预测（{model_data["summary"]["report_date"]}）</div>
  <table>
    <thead><tr><th>ETF</th><th>板块</th><th>Logit P(涨)</th><th>方向</th><th>置信</th><th>OLS 预测收益</th></tr></thead>
    <tbody>
{pred_rows}    </tbody>
  </table>
</div>"""

    return f"""<div class="sec-title">计量验证</div>
{logit_card}
{ols_card}
{pred_card}"""


def gen_cross_validation(model_data, econ_data):
    cv = econ_data['cross_validation']
    tv = cv['trend_validation']

    # 趋势验证指标
    bull_ratio_str = f'{tv["bull_up_ratio"]:.2f}' if tv['bull_up_ratio'] is not None else 'N/A'
    bear_ratio_str = f'{tv["bear_up_ratio"]:.2f}' if tv['bear_up_ratio'] is not None else 'N/A'
    neutral_ratio_str = f'{tv["neutral_up_ratio"]:.2f}' if tv['neutral_up_ratio'] is not None else 'N/A'

    metrics_html = f"""<div class="metrics">
  <div class="metric"><div class="ml">看涨天数</div><div class="mv">{tv["bull_days"]}</div><div class="ms">上涨比例: {bull_ratio_str}</div></div>
  <div class="metric"><div class="ml">看跌天数</div><div class="mv">{tv["bear_days"]}</div><div class="ms">上涨比例: {bear_ratio_str}</div></div>
  <div class="metric"><div class="ml">震荡天数</div><div class="mv">{tv["neutral_days"]}</div><div class="ms">上涨比例: {neutral_ratio_str}</div></div>
</div>"""

    # 一致性表
    consistency = cv.get('consistency', [])
    cons_rows = ""
    for c in consistency:
        rec_str = '&#10003;' if c.get('rule_rec') else '&mdash;'
        cons_str = '一致' if c.get('consistent') else '分歧'
        cons_cls = 'up' if c.get('consistent') else 'down'
        cons_rows += (
            f'<tr>'
            f'<td>{esc(c["etf"])}</td>'
            f'<td>{c["logit_prob"]}%</td>'
            f'<td class="{"up" if c["logit_dir"]=="涨" else "down"}">{esc(c["logit_dir"])}</td>'
            f'<td>{rec_str}</td>'
            f'<td><b class="{cons_cls}">{cons_str}</b></td>'
            f'</tr>\n'
        )

    cons_html = f"""<div class="card">
  <div class="card-title">Logit 与规则模型一致性</div>
  <table>
    <thead><tr><th>ETF</th><th>Logit P(涨)</th><th>Logit方向</th><th>规则推荐</th><th>一致性</th></tr></thead>
    <tbody>
{cons_rows}    </tbody>
  </table>
</div>"""

    conclusion = cv.get('conclusion', '')

    return f"""<div class="sec-title">交叉验证</div>
{metrics_html}
{cons_html}
<div class="rpt">
  <h3>结论</h3>
  <p>{conclusion}</p>
</div>"""


def gen_research(model_data):
    newspapers = model_data.get('latest_newspapers', {})
    d = model_data['latest_decision']
    paper_names = ['中国证券报', '上海证券报', '证券时报', '证券日报']

    # 四大报卡片（无数据时显示"今日暂无数据"）
    np_cards = ""
    for name in paper_names:
        titles = newspapers.get(name, [])
        if titles:
            items = ''.join(f'<li>{esc(t)}</li>' for t in titles)
            np_cards += f'<div class="np-card"><div class="np-src">{esc(name)}</div><ul>{items}</ul></div>\n'
        else:
            np_cards += f'<div class="np-card"><div class="np-src">{esc(name)}</div><ul><li style="color:var(--muted)">今日暂无数据</li></ul></div>\n'

    np_grid = f"""<div class="np-grid">
{np_cards}</div>"""

    return f"""<div class="sec-title">专业研报</div>
{np_grid}"""


def gen_charts_section():
    charts = [
        ('chart-cum',   '累计收益率走势'),
        ('chart-month', '月度收益对比'),
        ('chart-etf',   'ETF 胜率分布'),
        ('chart-rec',   '近15日每日收益对比'),
        ('chart-imp',   '因素重要性'),
    ]
    cards = ""
    for cid, title in charts:
        cards += f"""<div class="chart-card">
  <div class="card-title">{title}</div>
  <div id="{cid}" class="chart"></div>
</div>
"""
    return f"""<div class="sec-title">绩效图表</div>
{cards}"""


def gen_experience(model_data):
    # 经验记录 (已在 normalize_model_data 中按最新在前排序)
    experiences = model_data.get('experiences', [])[:20]
    exp_items = ""
    for e in experiences:
        exp_items += f'<div class="exp-row"><span class="exp-d">{esc(e["date"])}</span><span class="exp-t">{esc(e["text"])}</span></div>\n'

    # 最近交易记录表（最新在前）
    summaries = model_data.get('all_daily_summaries', [])
    recent_summaries = summaries[-20:][::-1]
    rec_rows = ""
    for s in recent_summaries:
        rec_rows += (
            f'<tr>'
            f'<td>{esc(s["date"])}</td>'
            f'<td>{trend_tag(s["trend"])}</td>'
            f'<td>{esc(s["etfs"])}</td>'
            f'<td class="{cls_val(s["return"])}">{fmt_pct(s["return"])}</td>'
            f'<td class="{cls_val(s["hs300"])}">{fmt_pct(s["hs300"])}</td>'
            f'<td class="{cls_val(s["alpha"])}">{fmt_pct(s["alpha"])}</td>'
            f'<td>{s.get("sentiment", "")}</td>'
            f'</tr>\n'
        )

    return f"""<div class="sec-title">经验库</div>
<div class="card">
  <div class="card-title">最近经验记录 ({len(experiences)} 条)</div>
  <div class="exp-list">
{exp_items}  </div>
</div>
<div class="card">
  <div class="card-title">最近交易记录</div>
  <table>
    <thead><tr><th>日期</th><th>研判</th><th>推荐ETF</th><th>收益</th><th>沪深300</th><th>Alpha</th><th>情绪</th></tr></thead>
    <tbody>
{rec_rows}    </tbody>
  </table>
</div>"""


# ============================================================
#  生成完整 HTML
# ============================================================
def generate_html(model_data, econ_data):
    now = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M')
    report_date = model_data['summary']['report_date']

    sections = [
        gen_eight_module_brief(model_data, econ_data),
        gen_section_4_performance(model_data, econ_data),
        gen_adaptation_review(model_data, econ_data),
        gen_model_fold(model_data, econ_data),
    ]

    body = '\n\n'.join(sections)
    masthead = f'''<header class="report-masthead">
  <div class="report-kicker">FUCKETF · DAILY RESEARCH NOTE</div>
  <h1 class="report-title">老林的ETF量化模型</h1>
  <div class="report-subtitle"><span>推荐/回避ETF · 逐只资金与新闻深挖 · 八项市场诊断</span><span class="report-meta">报告日 {esc(report_date)} · 生成于 {esc(now)}</span></div>
</header>'''

    return f"""<!-- Generated by Trae Work -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>老林的ETF量化模型 · {report_date}</title>
<style>
{CSS}
</style>
</head>
<body>

<div class="container">
{masthead}
{body}
<footer>研究用途，不构成投资建议。推荐关注不等于自动买入，回避ETF不等于卖出或做空；真实申赎、价格成交代理和新闻叙事分开标注。历史回测不代表未来收益。</footer>
</div>
<script src="{ECHARTS_JS_REF}"></script>
<script src="assets/charts.js"></script>
</body>
</html>"""


# ============================================================
#  主函数
# ============================================================
def main():
    # 加载数据
    print(f'读取规则模型数据: {MODEL_RESULTS_PATH}')
    model_raw = load_json(MODEL_RESULTS_PATH)
    print(f'读取计量模型数据: {ECON_RESULTS_PATH}')
    econ_raw = load_json(ECON_RESULTS_PATH)

    # 标准化数据结构
    print('标准化数据结构...')
    model_data = normalize_model_data(model_raw)
    econ_data = normalize_econ_data(econ_raw, model_data)

    # 生成 charts.js
    print(f'生成图表JS: {CHARTS_JS_OUT}')
    os.makedirs(os.path.dirname(CHARTS_JS_OUT), exist_ok=True)
    charts_js = generate_charts_js(model_data, econ_data)
    with open(CHARTS_JS_OUT, 'w', encoding='utf-8') as f:
        f.write(charts_js)

    # 生成 HTML
    print(f'生成看板HTML: {HTML_OUT}')
    os.makedirs(DASHBOARD_DIR, exist_ok=True)
    html_content = generate_html(model_data, econ_data)
    with open(HTML_OUT, 'w', encoding='utf-8') as f:
        f.write(html_content)

    print(f'\n看板已生成完成:')
    print(f'  HTML: {HTML_OUT}')
    print(f'  JS:   {CHARTS_JS_OUT}')


if __name__ == '__main__':
    main()
