#!/usr/bin/env python3
"""生成次交易日交接单；只记录待验证事项，不把未结算预测当成经验。"""
import json
import os
from datetime import date, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')

def load(name, default):
    try:
        with open(os.path.join(DATA, name), encoding='utf-8') as f: return json.load(f)
    except Exception: return default

def main():
    model = load('model_results.json', {})
    ext = load('external_news.json', {})
    margin = load('margin_trading.json', {})
    shares = load('etf_shares.json', {})
    latest = model.get('latest_decision', {})
    as_of = latest.get('date') or date.today().isoformat()
    all_days = sorted({r.get('date') for v in load('etf_history.json', {}).values() for r in v.get('data', []) if r.get('date')})
    future = [d for d in all_days if d > as_of]
    next_day = future[0] if future else None
    state = latest.get('market_state', {})
    items = ext.get('items', []) if isinstance(ext, dict) else []
    valid = [x for x in items if x.get('published_at', '')[:10] <= as_of and x.get('date_quality') not in (None, 'unknown', 'listing')]
    handoff = {
        'as_of_date': as_of, 'decision_date': as_of, 'next_trading_date': next_day,
        'cutoff_policy': '价格/成交截至前一交易日；外部事件必须有原文或URL日期且published_at<=decision_date；未结算预测不得进入经验库。',
        'market_state': {'name': state.get('name'), 'risk_budget': state.get('risk_budget'), 'breadth': state.get('breadth'), 'volatility_20d': state.get('volatility_20d')},
        'selected_etfs': latest.get('etf_selection', latest.get('rankings', [])[:3]),
        'monitor': ['crowding', 'withdrawal_risk', 'share_flow_signal', 'news_price_gap', 'news_flow_gap', 'market_breadth', 'volatility_20d'],
        'external_event_count': len(valid),
        'external_latest_dates': sorted({x.get('published_at', '')[:10] for x in valid}, reverse=True)[:5],
        'pending_labels': [{'decision_date': as_of, 'settle_after': next_day, 'status': 'pending', 'rule': '持有期结束后才计算净收益并写入经验库'}],
        'source_health': {'external_news': len(valid), 'margin_records': len(margin.get('records', [])) if isinstance(margin, dict) else len(margin), 'share_snapshots': len(shares.get('snapshots', shares.get('records', []))) if isinstance(shares, dict) else len(shares)},
        'experience_policy': '只用真实成交/结算后的结果更新经验；不使用手工输入跌幅、不按单日噪声自动改权重；参数仅在滚动样本外验证通过后升级。'
    }
    with open(os.path.join(DATA, 'next_day_handoff.json'), 'w', encoding='utf-8') as f:
        json.dump(handoff, f, ensure_ascii=False, indent=2)
    print('次交易日交接单已生成:', os.path.join(DATA, 'next_day_handoff.json'))

if __name__ == '__main__': main()
