"""最小回归检查：行为信号范围、启动和撤退方向不能被后续改动破坏。"""
from datetime import date, timedelta

from etf_model_run import compute_behavior_signals, compute_market_state


def _series(code, prices, volumes):
    start = date(2026, 1, 1)
    data = []
    for i, (price, volume) in enumerate(zip(prices, volumes)):
        data.append({'date': str(start + timedelta(days=i)), 'open': price * 0.998,
                     'close': price, 'high': price * 1.01, 'low': price * 0.99,
                     'volume': volume})
    return {code: {'name': code, 'data': data}}


def main():
    prices = [100 + i * 0.35 for i in range(35)]
    volumes = [1000 + i * 8 for i in range(35)]
    data = _series('510300', prices, volumes)
    latest = data['510300']['data'][-1]['date']
    signal = compute_behavior_signals(data, '510300', latest)
    assert signal['early_entry'] >= 0
    assert 0 <= signal['crowding'] <= 1
    assert compute_market_state(data, latest)['name'] == 'risk_on'

    prices[-1] *= 0.94
    volumes[-1] *= 4
    stressed = _series('510300', prices, volumes)
    exit_signal = compute_behavior_signals(stressed, '510300', latest)
    assert exit_signal['withdrawal_risk'] > signal['withdrawal_risk']
    print('behavior signal checks passed')


if __name__ == '__main__':
    main()
