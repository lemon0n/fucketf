"""关键正确性回归：未结算交易、风险权重、样本外比较和交易日交接。"""
import sys
import unittest
from unittest.mock import patch

import pandas as pd

from econometric_model import (
    build_dataset, compute_net_alpha_target, cross_validate_models,
    purged_walk_forward_splits, simulate_selective_portfolio,
)
from etf_model_run import (
    ETF_HISTORY_PATH, HS300_CODE, HOLDING_PERIOD, NEWSPAPERS_PATH,
    get_trading_days, holding_end_index, load_json, risk_adjusted_score,
)
from generate_daily_handoff import future_trading_days


class ModelIntegrityTests(unittest.TestCase):
    def test_incomplete_holding_period_stays_pending(self):
        self.assertEqual(holding_end_index(3, 6, 3), 5)
        self.assertIsNone(holding_end_index(4, 6, 3))

    def test_risk_adjustment_penalizes_volatility(self):
        low = risk_adjusted_score({'total_score': 0.8, 'volatility': 10})
        high = risk_adjusted_score({'total_score': 0.8, 'volatility': 30})
        self.assertGreater(low, high)

    def test_model_agreement_uses_only_oof_predictions(self):
        frame = pd.DataFrame([
            {'date': '2026-01-01', 'etf_name': 'A'},
            {'date': '2026-01-02', 'etf_name': 'A'},
        ])
        logit = {
            'oof_pred_direction': [1, 1],
            'oof_pred_probability': [0.9, 0.7],
        }
        rule = {'all_daily_summaries': [
            {'date': '2026-01-02', 'etf_names': ['A'], 'trend': 'bullish'},
        ]}
        result = cross_validate_models(frame, logit, rule)
        self.assertEqual(result['n_compared'], 1)
        self.assertEqual(result['agreement_rate'], 1.0)

    def test_net_alpha_target_matches_holding_period_and_cost(self):
        target = compute_net_alpha_target(100, 110, 100, 105)
        self.assertAlmostEqual(target, 4.95, places=8)

    def test_alpha_panel_excludes_benchmark_and_unsettled_tail(self):
        etf_data = load_json(ETF_HISTORY_PATH)
        frame = build_dataset(etf_data, load_json(NEWSPAPERS_PATH))
        trading_days = get_trading_days(etf_data)
        self.assertNotIn(HS300_CODE, set(frame['etf_code']))
        self.assertEqual(frame['target_end_date'].max(), trading_days[-1])
        day_index = {date: i for i, date in enumerate(trading_days)}
        self.assertTrue(all(day_index[end] - day_index[start] == HOLDING_PERIOD - 1
                            for start, end in zip(frame['date'], frame['target_end_date'])))

    def test_walk_forward_purges_overlapping_labels(self):
        frame = pd.DataFrame({'date': [f'2026-01-{i:02d}' for i in range(1, 26)]})
        index = {date: i for i, date in enumerate(frame['date'])}
        for _, train_dates, test_dates in purged_walk_forward_splits(frame):
            gap = index[test_dates[0]] - index[train_dates[-1]]
            self.assertGreaterEqual(gap, HOLDING_PERIOD)

    def test_selective_portfolio_skips_overlapping_trade_dates(self):
        frame = pd.DataFrame({
            'date': [f'2026-01-{i:02d}' for i in range(1, 7)],
            'target_return': [1.0, -1.0, 2.0, 0.5, -0.5, 1.5],
        })
        result = simulate_selective_portfolio(frame, [0.9] * len(frame))
        self.assertEqual(result['trade_dates'], ['2026-01-01', '2026-01-04'])
        self.assertEqual(int(result['selected_mask'].sum()), 2)

    def test_weekday_calendar_fallback_handles_weekend(self):
        with patch.dict(sys.modules, {'akshare': None}):
            dates, quality = future_trading_days('2026-08-07', 2)
        self.assertEqual(dates, ['2026-08-10', '2026-08-11'])
        self.assertEqual(quality, 'weekday_fallback')


if __name__ == '__main__':
    unittest.main()
