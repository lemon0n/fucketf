"""关键正确性回归：未结算交易、风险权重、样本外比较和交易日交接。"""
import sys
import unittest
from unittest.mock import patch

import pandas as pd

from econometric_model import cross_validate_models
from etf_model_run import holding_end_index, risk_adjusted_score
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
        logit = {'oof_pred_direction': [None, 1]}
        rule = {'all_daily_summaries': [
            {'date': '2026-01-02', 'etf_names': ['A'], 'trend': 'bullish'},
        ]}
        result = cross_validate_models(frame, logit, rule)
        self.assertEqual(result['n_compared'], 1)
        self.assertEqual(result['agreement_rate'], 1.0)

    def test_weekday_calendar_fallback_handles_weekend(self):
        with patch.dict(sys.modules, {'akshare': None}):
            dates, quality = future_trading_days('2026-08-07', 2)
        self.assertEqual(dates, ['2026-08-10', '2026-08-11'])
        self.assertEqual(quality, 'weekday_fallback')


if __name__ == '__main__':
    unittest.main()
