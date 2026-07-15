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

# ============================================================
#  路径配置
# ============================================================
SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
DATA_DIR     = os.path.join(SCRIPT_DIR, 'data')
PROJECT_DIR  = os.path.dirname(SCRIPT_DIR)
DASHBOARD_DIR = os.path.join(PROJECT_DIR, 'etf-dashboard')

MODEL_RESULTS_PATH  = os.path.join(DATA_DIR, 'model_results.json')
ECON_RESULTS_PATH   = os.path.join(DATA_DIR, 'econometric_results.json')
HTML_OUT            = os.path.join(DASHBOARD_DIR, 'dashboard.html')
CHARTS_JS_OUT       = os.path.join(DASHBOARD_DIR, 'assets', 'charts.js')
ECHARTS_JS_REF      = '_shared/js/echarts.min.js'

# ============================================================
#  变量说明字典
# ============================================================
FACTOR_DESC = {
    'sentiment_score':      '情绪分（看涨−看跌次数）',
    'bullish_count':        '看涨关键词出现次数',
    'bearish_count':        '看跌关键词出现次数',
    'prev_change_pct':      '前日涨跌幅%',
    'prev_volume_ratio':    '前日量比（今日量/前5日均量）',
    'prev_intraday_return': '前日日内收益率%（开盘→收盘）',
    'sector_mentioned':     '板块是否被报纸提及（0/1）',
    'sector_mention_count': '板块被提及次数',
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
        'decision': ld.get('decision', ''),
        'picks': [
            {'code': p['code'], 'name': p['name'], 'sector': p.get('sector', ''),
             'weight': p['weight'], 'score': p.get('total_score', 0)}
            for p in ld.get('etf_selection', [])
        ],
        'reason': ld.get('reason', ''),
        'confidence': f'{ld.get("avg_score", 0):.2f}',
        'bull_signals': sent.get('bullish_count', 0),
        'bear_signals': sent.get('bearish_count', 0),
        'sentiment_score': sent.get('score', 0),
        'hot_sectors': [{'name': s['sector'], 'count': s['count']} for s in sent.get('hot_sectors', [])],
        'etf_performance': _calc_etf_performance(raw.get('experiences', [])),
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
        prob_pct = p.get('prob_up', 0) * 100
        logit_preds.append({
            'etf': p.get('etf_name', ''), 'sector': p.get('sector', ''),
            'prob': f'{prob_pct:.1f}',
            'direction': '涨' if p.get('predicted_direction') == 'up' else '跌',
            'confidence': f'{abs(prob_pct - 50) * 2:.0f}%',
        })

    e['logit'] = {
        'n': lm['n_obs'],
        'pseudo_r2': lm.get('pseudo_r2', 0),
        'accuracy': lm.get('accuracy', 0) * 100,
        'cv_accuracy': tscv.get('mean_cv_accuracy', 0) * 100,
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
            'predicted_return': p.get('predicted_return_pct', 0),
        })

    e['ols'] = {
        'n': om['n_obs'],
        'r2': om.get('r_squared', 0),
        'adj_r2': om.get('adj_r_squared', 0),
        'f_stat': om.get('f_statistic', 0),
        'f_p': om.get('f_pvalue', 0),
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
        prob = p.get('prob_up', 0) * 100
        direction = '涨' if p.get('predicted_direction') == 'up' else '跌'
        rule_rec = etf_code in rule_codes or etf_name in rule_names
        consistent = (direction == '涨' and rule_rec) or (direction == '跌' and not rule_rec)
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
  --radius:16px;--radius-sm:10px;
  --maxw:980px;
  --IS:'InstrumentSans',-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
  --JM:'JetBrainsMono',ui-monospace,'SF Mono',Menlo,monospace;
}

*{margin:0;padding:0;box-sizing:border-box}
body{background:var(--bg);color:var(--ink);font-family:var(--IS);font-size:15px;line-height:1.6;-webkit-font-smoothing:antialiased}
.container{max-width:var(--maxw);margin:0 auto;padding:24px 20px 60px}

.date-bar{text-align:center;margin-bottom:28px}
.badge{display:inline-block;background:var(--bg2);border-radius:100px;padding:6px 16px;font-family:var(--JM);font-size:0.82rem;color:var(--ink);font-weight:500}
.date-bar .sub{margin-top:6px;font-size:0.72rem;color:var(--muted)}

.sec-title{font-size:0.7rem;font-weight:600;color:var(--muted);text-transform:uppercase;letter-spacing:1px;margin:28px 0 10px;padding-left:2px}

.card{background:var(--bg3);border:1px solid var(--rule);border-radius:var(--radius);padding:18px 20px;margin-bottom:12px}
.card-title{font-size:0.9rem;font-weight:600;margin-bottom:12px;color:var(--ink)}

.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:4px}
.metric{background:var(--bg3);border:1px solid var(--rule);border-radius:var(--radius-sm);padding:14px 16px}
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

.formula-2col{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px}
.formula-col{min-width:0}

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

.chart-card{background:var(--bg3);border:1px solid var(--rule);border-radius:var(--radius);padding:16px 20px;margin-bottom:12px}
.chart-card .card-title{margin-bottom:8px}
.chart{width:100%;height:300px}

.exp-list{display:grid;grid-template-columns:1fr;gap:4px}
.exp-row{display:flex;gap:10px;padding:6px 0;border-bottom:1px solid var(--bg2);font-size:0.76rem}
.exp-row:last-child{border-bottom:none}
.exp-d{font-family:var(--JM);color:var(--muted);min-width:90px}
.exp-t{color:var(--ink)}

footer{text-align:center;font-size:0.7rem;color:var(--muted);margin-top:36px;padding-top:16px;border-top:1px solid var(--rule)}

@media(max-width:760px){
  .metrics{grid-template-columns:repeat(2,1fr)}
  .np-grid{grid-template-columns:1fr}
  .formula-2col{grid-template-columns:1fr}
}
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
    <div class="f-title">拟合方程（N={logit["n"]}, 伪R&sup2;={logit["pseudo_r2"]}, 准确率={logit["accuracy"]}%）</div>
    <div class="formula">P(y=1) = 1 / (1 + e<sup>&minus;z</sup>)</div>
{logit_eq}
    <div class="formula-legend">
      <b>y=1</b>=次日上涨 &nbsp; CV准确率={logit["cv_accuracy"]}% &nbsp; Lasso={logit.get("lasso_note", "N/A")}
    </div>
  </div>
</div>"""

    return f"""<div class="sec-title">模型公式</div>
<div class="formula-2col">
<div class="formula-col">{rule_card}</div>
<div class="formula-col">{logit_card}</div>
</div>
{ols_card}"""


def gen_recommendation(model_data, econ_data):
    d = model_data['latest_decision']
    s = model_data['summary']
    date = s['report_date']

    # 构建 Logit 预测查找表
    logit_preds = econ_data['logit'].get('latest_predictions', [])
    logit_lookup = {}
    for lp in logit_preds:
        logit_lookup[lp.get('etf', '')] = lp

    # 构建预警列表：Logit预测看跌概率最高的3个ETF（按prob_up升序=看跌概率降序）
    bearish_preds = [lp for lp in logit_preds if lp.get('direction') == '跌']
    bearish_preds_sorted = sorted(bearish_preds, key=lambda x: float(x.get('prob', '50')))
    top3_warnings = bearish_preds_sorted[:3]
    if len(top3_warnings) < 3:
        # 补充非看跌但概率最低的ETF
        remaining = [lp for lp in logit_preds if lp not in top3_warnings]
        remaining_sorted = sorted(remaining, key=lambda x: float(x.get('prob', '50')))
        top3_warnings.extend(remaining_sorted[:3 - len(top3_warnings)])

    # 趋势标签
    trend = trend_tag(d['trend'])
    # 置信度
    conf = esc(d.get('confidence', ''))
    # 信号
    bull = d.get('bull_signals', 0)
    bear = d.get('bear_signals', 0)
    sent = d.get('sentiment_score', 0)
    # ETF 选择卡片（含交叉验证）
    picks_html = ""
    for p in d['picks']:
        w_pct = int(p['weight'] * 100)
        # 交叉验证：检查Logit预测
        lp = logit_lookup.get(p['name'], {})
        logit_dir = lp.get('direction', '')
        logit_prob = lp.get('prob', '')
        warning_tag = ''
        if logit_dir == '跌' and float(logit_prob) < 45:  # prob_up < 45% => bearish > 55%
            warning_tag = f' <span class="tag t-bear" style="margin-left:6px">⚠ 计量分歧</span>'
        logit_info = f'<span class="pick-logit">Logit:{esc(logit_dir)}({logit_prob}%)</span>'
        picks_html += f'<div class="pick"><span class="pick-code">{esc(p["code"])}</span><span class="pick-name">{esc(p["name"])}<span class="pick-score">评分{p["score"]:.2f}</span></span><span class="pick-w">{w_pct}%</span>{logit_info}{warning_tag}</div>\n'

    # 理由
    reason = esc(d.get('reason', ''))
    # 热点板块
    sectors = d.get('hot_sectors', [])
    sectors_str = ', '.join(f'{esc(s_["name"])}({s_["count"]})' for s_ in sectors)

    decision_html = f"""<div class="decision">
  <div class="dec-head">
    <div>
      {trend}
      <span class="conf-pill" style="margin-left:8px">置信度 {conf}</span>
    </div>
    <div style="font-size:0.78rem;color:var(--muted)">基于 {esc(date)} 四大报 + 前日行情</div>
  </div>
  <div class="sig-bar">
    <span><span class="dot bull"></span>多头信号: {bull}</span>
    <span><span class="dot bear"></span>空头信号: {bear}</span>
    <span style="color:var(--gold)">情绪分: {sent}</span>
  </div>
  <div class="picks">
{picks_html}  </div>
  <div class="reason">{reason}</div>
  <div style="margin-top:12px;font-size:0.78rem;color:var(--muted)"><strong style="color:var(--accent)">报纸热点:</strong> {sectors_str}</div>
</div>"""

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

    # 预警关注区域：Logit预测看跌概率最高的3个ETF
    warning_rows = ""
    for wp in top3_warnings:
        prob_val = float(wp.get('prob', '50'))
        bear_prob = round(100 - prob_val, 1)
        warning_rows += (
            f'<tr>'
            f'<td>{esc(wp.get("etf", ""))}</td>'
            f'<td>{esc(wp.get("sector", ""))}</td>'
            f'<td class="down">{prob_val}%</td>'
            f'<td class="down">{bear_prob}%</td>'
            f'<td class="down">{esc(wp.get("direction", ""))}</td>'
            f'</tr>\n'
        )

    warning_html = f"""<div class="card" style="border-color:var(--accent2);border-width:1px">
  <div class="card-title" style="color:var(--accent2)">预警关注 · Logit看跌概率最高</div>
  <table>
    <thead><tr><th>ETF</th><th>板块</th><th>P(涨)</th><th>P(跌)</th><th>方向</th></tr></thead>
    <tbody>
{warning_rows}    </tbody>
  </table>
</div>"""

    return f"""<div class="sec-title">今日推荐</div>
{decision_html}
{perf_html}
{warning_html}"""


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
    <div class="metric"><div class="ml">伪 R&sup2;</div><div class="mv" style="font-size:1rem">{logit["pseudo_r2"]}</div></div>
    <div class="metric"><div class="ml">准确率</div><div class="mv" style="font-size:1rem">{logit["accuracy"]}%</div></div>
    <div class="metric"><div class="ml">CV 准确率</div><div class="mv" style="font-size:1rem">{logit["cv_accuracy"]}%</div></div>
    <div class="metric"><div class="ml">CV AUC</div><div class="mv" style="font-size:1rem">{logit["cv_auc"]}</div></div>
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
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    report_date = model_data['summary']['report_date']

    sections = [
        gen_date_badge(model_data),
        gen_overview(model_data),
        gen_formulas(model_data, econ_data),
        gen_recommendation(model_data, econ_data),
        gen_econometric(model_data, econ_data),
        gen_cross_validation(model_data, econ_data),
        gen_research(model_data),
        gen_charts_section(),
        gen_experience(model_data),
    ]

    body = '\n\n'.join(sections)

    return f"""<!-- Generated by Trae Work -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ETF 预测模型看板 · {report_date}</title>
<style>
{CSS}
</style>
</head>
<body>
<div class="container">
{body}
<footer>ETF 预测模型看板 &middot; 规则模型 + 计量交叉验证 &middot; 同花顺API + 四大报(10jqka) &middot; {now}</footer>
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
