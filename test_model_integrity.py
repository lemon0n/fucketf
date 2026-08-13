"""关键正确性回归：未结算交易、风险权重、样本外比较和交易日交接。"""
import unittest
from datetime import date
from unittest.mock import patch

import pandas as pd

from econometric_model import (
    build_dataset, compute_net_alpha_target, compute_sentiment_divergence, cross_validate_models,
    purged_walk_forward_splits, simulate_selective_portfolio,
)
from etf_model_run import (
    ETF_HISTORY_PATH, HS300_CODE, HOLDING_PERIOD, NEWSPAPERS_PATH,
    SECTOR_ETF_MAP, analyze_newspaper_sentiment, get_trading_days, holding_end_index, load_json,
    risk_adjusted_score,
)
from fetch_targeted_news import parse_rss
from generate_daily_handoff import future_trading_days
from market_diagnostics import (
    OUTPUT_PATH as DIAGNOSTICS_PATH, collect_target_news, share_flow_rows,
)
import generate_dashboard as dashboard


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
        with patch('requests.get', side_effect=RuntimeError('offline')):
            dates, quality = future_trading_days('2026-08-07', 2)
        self.assertEqual(dates, ['2026-08-10', '2026-08-11'])
        self.assertEqual(quality, 'weekday_fallback')

    def test_media_sentiment_is_diluted_by_neutral_titles(self):
        titles = ['增长改善一', '增长改善二'] + [f'普通资讯{i}' for i in range(14)]
        result = analyze_newspaper_sentiment({'测试报': titles})
        self.assertEqual(result['total_titles'], 16)
        self.assertEqual(result['bullish_count'], 2)
        self.assertEqual(result['bearish_count'], 0)
        self.assertAlmostEqual(result['score'], 0.125, places=4)
        self.assertAlmostEqual(result['directional_coverage'], 0.125, places=4)

    def test_sentiment_divergence_is_a_distance(self):
        self.assertEqual(compute_sentiment_divergence(0, 0), 0)
        self.assertEqual(compute_sentiment_divergence(1, -1), 1)
        self.assertEqual(compute_sentiment_divergence(0.2, -0.2), 0.2)

    def test_share_flow_uses_two_real_snapshots(self):
        prices = {'510300': {'data': [
            {'date': '2026-01-01', 'close': 4.0},
            {'date': '2026-01-02', 'close': 4.0},
        ]}}
        shares = {'history': {
            '2026-01-01': {'510300': 100_000_000},
            '2026-01-02': {'510300': 110_000_000},
        }}
        rows = share_flow_rows(prices, shares, '2026-01-02')
        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]['share_change_pct'], 10.0, places=4)
        self.assertAlmostEqual(rows[0]['estimated_flow_yi'], 0.4, places=4)

    def test_dashboard_leads_with_eight_evidence_modules(self):
        model = dashboard.normalize_model_data(
            dashboard.load_json(dashboard.MODEL_RESULTS_PATH)
        )
        econ = dashboard.normalize_econ_data(
            dashboard.load_json(dashboard.ECON_RESULTS_PATH), model
        )
        views = dashboard.build_signal_views(model)
        expected_longs = {
            item['code'] for item in model['latest_decision']['picks']
            if float(item.get('weight', 0)) > 0
        }
        actual_longs = {item['code'] for item in views['long_candidates']}
        avoid_codes = {item['code'] for item in views['avoid_watch']}
        self.assertEqual(actual_longs, expected_longs)
        self.assertTrue(actual_longs.isdisjoint(avoid_codes))
        self.assertEqual(views['short_candidates'], [])

        html = dashboard.gen_eight_module_brief(model, econ)
        diagnostics = model['diagnostics']
        self.assertLess(html.index('每日ETF推荐与回避预警'), html.index('0–7 八项市场诊断'))
        self.assertIn(f"今日推荐关注 · {len(diagnostics['recommendations'])}只", html)
        self.assertIn(f"今日回避预警 · {len(diagnostics['avoid_etfs'])}只", html)
        self.assertIn('高预警｜回避新增', html)
        self.assertLess(html.index('逐只ETF资金流与新闻流深挖'), html.index('0–7 八项市场诊断'))
        self.assertEqual(html.count('<article class="focus-card recommend">'), len(diagnostics['recommendations']))
        self.assertEqual(html.count('<article class="focus-card avoid">'), len(diagnostics['avoid_etfs']))
        self.assertEqual(html.count('<article class="deep-card '), len(diagnostics['etf_deep_dives']))
        self.assertIn('推荐关注不等于自动买入', dashboard.generate_html(model, econ))
        self.assertIn('回避ETF不等于卖出或做空', dashboard.generate_html(model, econ))
        for index, title in enumerate([
            '市场情绪', '资金流向', 'ETF申赎资金', '板块轮动',
            '宏观周期', '风险偏好', '机构资金', '成交结构',
        ]):
            self.assertIn(f'{index}. {title}', html)
        self.assertIn('对持仓意味着什么', html)
        self.assertIn('下一次看什么才算确认', html)
        self.assertIn('等待确认', html)
        self.assertIn('报告补充·未回填规则', html)
        self.assertNotIn('做多计划 · 规则主模型', html)

    def test_diagnostics_contract_distinguishes_evidence_types(self):
        diagnostics = load_json(DIAGNOSTICS_PATH)
        self.assertEqual(
            [row['id'] for row in diagnostics['modules']],
            ['market_sentiment', 'capital_flow', 'etf_creation_redemption',
             'sector_rotation', 'macro_cycle', 'risk_appetite',
             'institutional_flow', 'trading_structure'],
        )
        kinds = {
            evidence['kind']
            for module in diagnostics['modules']
            for evidence in module.get('evidence', [])
        }
        self.assertIn('真实数据', kinds)
        self.assertTrue(any('代理' in kind for kind in kinds))
        self.assertIn('数据缺口', kinds)
        self.assertTrue(all(evidence.get('as_of')
                            for module in diagnostics['modules']
                            for evidence in module.get('evidence', [])))
        final = diagnostics['final_decision']
        self.assertEqual(final['canonical_source'], 'data/market_diagnostics.json')
        if not diagnostics['overall']['model_status'] == '可执行':
            self.assertFalse(final['execution_allowed'])
            self.assertEqual(final['position'], 0.0)
        self.assertIn('compression_rule', diagnostics['downstream_output_contract'])
        self.assertEqual(
            diagnostics['downstream_output_contract']['renderer_prompt'],
            'prompts/etf_report_renderer.md',
        )

    def test_recommend_avoid_and_deep_dive_contract(self):
        diagnostics = load_json(DIAGNOSTICS_PATH)
        recommendations = diagnostics['recommendations']
        avoids = diagnostics['avoid_etfs']
        alerts = diagnostics['daily_etf_alerts']
        self.assertEqual(alerts['recommendation_count'], len(recommendations))
        self.assertEqual(alerts['avoid_count'], len(avoids))
        self.assertEqual(alerts['date'], diagnostics['as_of_date'])
        self.assertLessEqual(len(recommendations), 3)
        self.assertLessEqual(len(avoids), 3)
        self.assertTrue(
            {row['code'] for row in recommendations}.isdisjoint(
                {row['code'] for row in avoids}
            )
        )
        self.assertEqual(
            len(diagnostics['etf_deep_dives']),
            len(recommendations) + len(avoids),
        )
        for row in diagnostics['etf_deep_dives']:
            self.assertTrue(row['fund_flow']['price_as_of'])
            self.assertIn('share_evidence', row['fund_flow'])
            self.assertIn('relative_5d', row['fund_flow'])
            self.assertIn('relative_20d', row['fund_flow'])
            self.assertIn('conclusion', row['news_flow'])
            self.assertTrue(row['news_flow']['window_start'])
            self.assertEqual(row['news_flow']['as_of_date'], diagnostics['as_of_date'])
            self.assertIn('cross_read', row)
            self.assertLessEqual(len(row['news_flow']['top_items']), 4)
            for item in row['news_flow']['top_items']:
                self.assertLessEqual(item['published_at'][:10], diagnostics['as_of_date'])
                self.assertTrue(item['matched_keywords'])
        for row in avoids:
            self.assertIn(row['action'], {'回避新增', '谨慎观察，不追涨'})
            self.assertNotIn('做空', row['action'])
            self.assertIn('不自动生成卖出或做空指令', row['position_note'])
        if not diagnostics['final_decision']['execution_allowed']:
            self.assertTrue(all('建议买入' not in row['action'] for row in recommendations))

    def test_no_direct_news_is_insufficient_evidence_not_bearish(self):
        result = collect_target_news(
            '513050', SECTOR_ETF_MAP['513050'], {}, {}, {}, '2026-08-13'
        )
        self.assertEqual(result['direct_count'], 0)
        self.assertIn('新闻证据不足，不等于利空', result['conclusion'])

    def test_targeted_rss_requires_date_domain_and_direct_keyword(self):
        rss = '''<rss><channel>
          <item><title>创新药医保目录迎来新进展</title><link>https://www.stcn.com/article/ok.html</link><pubDate>Tue, 11 Aug 2026 08:00:00 GMT</pubDate><source>证券时报</source></item>
          <item><title>创新药公司发布新产品</title><link>https://example.com/no.html</link><pubDate>Tue, 11 Aug 2026 08:00:00 GMT</pubDate></item>
          <item><title>创新药旧闻</title><link>https://www.stcn.com/article/old.html</link><pubDate>Wed, 01 Jul 2026 08:00:00 GMT</pubDate></item>
        </channel></rss>'''
        rows = parse_rss(
            rss, '515120', SECTOR_ETF_MAP['515120'], today=date(2026, 8, 13)
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['category'], 'targeted_search')
        self.assertEqual(rows[0]['usage_policy'], '报告补充；不回填当日规则信号')

        ambiguous = '''<rss><channel><item><title>互联网券商推进数字金融</title><link>https://www.stcn.com/article/no.html</link><pubDate>Tue, 11 Aug 2026 08:00:00 GMT</pubDate></item></channel></rss>'''
        self.assertEqual(
            parse_rss(ambiguous, '513050', SECTOR_ETF_MAP['513050'], today=date(2026, 8, 13)),
            [],
        )

    def test_dashboard_external_news_respects_decision_cutoff(self):
        model = dashboard.normalize_model_data(
            dashboard.load_json(dashboard.MODEL_RESULTS_PATH)
        )
        cutoff = model['latest_decision']['date']
        review = model['external_review']
        self.assertTrue(all(item['published_at'][:10] <= cutoff
                            for item in review['events']))
        self.assertTrue(all(item['published_at'][:10] > cutoff
                            for item in review['post_decision_events']))
        keys = [(item['published_at'][:10], item.get('source'), item.get('title'))
                for item in review['events'] + review['post_decision_events']]
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == '__main__':
    unittest.main()
