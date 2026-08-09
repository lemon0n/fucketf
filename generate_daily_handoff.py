#!/usr/bin/env python3
"""生成次交易日交接单；只记录待验证事项，不把未结算预测当成经验。"""
import json
import os
from datetime import date, timedelta

from etf_model_run import HOLDING_PERIOD

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, 'data')

def load(name, default):
    try:
        with open(os.path.join(DATA, name), encoding='utf-8') as f: return json.load(f)
    except Exception: return default


def future_trading_days(as_of, count):
    """优先使用交易所日历；网络不可用时退化为工作日并显式标记。"""
    try:
        import akshare as ak
        calendar = [str(x)[:10] for x in ak.tool_trade_date_hist_sina()['trade_date']]
        future = [x for x in calendar if x > as_of][:count]
        if len(future) == count:
            return future, 'exchange_calendar'
    except Exception:
        pass
    future, current = [], date.fromisoformat(as_of)
    while len(future) < count:
        current += timedelta(days=1)
        if current.weekday() < 5:
            future.append(current.isoformat())
    return future, 'weekday_fallback'

def main():
    model = load('model_results.json', {})
    ext = load('external_news.json', {})
    margin = load('margin_trading.json', {})
    shares = load('etf_shares.json', {})
    previous = load('next_day_handoff.json', {})
    latest = model.get('latest_decision', {})
    as_of = latest.get('date') or date.today().isoformat()
    future, calendar_quality = future_trading_days(as_of, HOLDING_PERIOD - 1)
    next_day = future[0]
    settle_day = future[-1]
    state = latest.get('market_state', {})
    items = ext.get('items', []) if isinstance(ext, dict) else []
    valid = [x for x in items if x.get('published_at', '')[:10] <= as_of and x.get('date_quality') not in (None, 'unknown', 'listing')]
    pending = [p for p in previous.get('pending_labels', [])
               if p.get('status') == 'pending' and p.get('settle_after') and p['settle_after'] > as_of]
    if latest.get('etf_selection') and not any(p.get('decision_date') == as_of for p in pending):
        pending.append({'decision_date': as_of, 'settle_after': settle_day, 'status': 'pending',
                        'rule': '完整持有期结束后才计算净收益并写入经验库'})
    share_snapshots = len(shares.get('history', {})) + len(shares.get('szse_snapshot', {})) if isinstance(shares, dict) else 0
    handoff = {
        'as_of_date': as_of, 'decision_date': as_of, 'next_trading_date': next_day,
        'settlement_date': settle_day, 'calendar_quality': calendar_quality,
        'cutoff_policy': '价格/成交截至前一交易日；外部事件必须有原文或URL日期且published_at<=decision_date；未结算预测不得进入经验库。',
        'market_state': {'name': state.get('name'), 'risk_budget': state.get('risk_budget'), 'breadth': state.get('breadth'), 'volatility_20d': state.get('volatility_20d')},
        'selected_etfs': latest.get('etf_selection', latest.get('rankings', [])[:3]),
        'monitor': ['crowding', 'withdrawal_risk', 'share_flow_signal', 'news_price_gap', 'news_flow_gap', 'market_breadth', 'volatility_20d'],
        'external_event_count': len(valid),
        'external_latest_dates': sorted({x.get('published_at', '')[:10] for x in valid}, reverse=True)[:5],
        'pending_labels': pending,
        'source_health': {'external_news': len(valid), 'margin_records': len(margin.get('records', [])) if isinstance(margin, dict) else len(margin), 'share_snapshots': share_snapshots},
        'experience_policy': '只用真实成交/结算后的结果更新经验；不使用手工输入跌幅、不按单日噪声自动改权重；参数仅在滚动样本外验证通过后升级。'
    }
    with open(os.path.join(DATA, 'next_day_handoff.json'), 'w', encoding='utf-8') as f:
        json.dump(handoff, f, ensure_ascii=False, indent=2)
    print('次交易日交接单已生成:', os.path.join(DATA, 'next_day_handoff.json'))

if __name__ == '__main__': main()
