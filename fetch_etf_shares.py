#!/usr/bin/env python3
"""抓取交易所公开 ETF 份额：上交所历史快照，深交所当前快照。"""
import json
import os
import time
from datetime import date

import akshare as ak

from etf_universe import SECTOR_ETF_MAP

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(BASE_DIR, 'data', 'etf_shares.json')
START_DATE = '2025-01-01'


def trade_dates():
    calendar = ak.tool_trade_date_hist_sina()
    values = [str(x)[:10] for x in calendar['trade_date']]
    today = date.today().isoformat()
    return [x for x in values if START_DATE <= x <= today]


def fetch_sse_history():
    targets = {code for code in SECTOR_ETF_MAP if code.startswith('5')}
    dates = trade_dates()
    # 每周一个公开快照，兼顾历史覆盖和站点请求压力；最新交易日始终保留。
    sampled = dates[::5]
    if dates and dates[-1] not in sampled:
        sampled.append(dates[-1])
    history = {}
    for date_str in sampled:
        try:
            frame = ak.fund_etf_scale_sse(date=date_str.replace('-', ''))
            values = {}
            for _, row in frame.iterrows():
                code = str(row['基金代码']).zfill(6)
                if code in targets:
                    values[code] = float(row['基金份额'])
            if values:
                history[date_str] = values
                print(f'  上交所 {date_str}: {len(values)} 只')
        except Exception as exc:
            print(f'  [WARN] 上交所 {date_str}: {exc}')
        time.sleep(0.15)
    return history


def fetch_szse_snapshot():
    targets = {code for code in SECTOR_ETF_MAP if code.startswith('1')}
    frame = ak.fund_etf_scale_szse()
    values = {}
    for _, row in frame.iterrows():
        code = str(row['基金代码']).zfill(6)
        if code in targets:
            values[code] = float(row['基金份额'])
    return {date.today().isoformat(): values}


def main():
    history = fetch_sse_history()
    snapshot = fetch_szse_snapshot()
    payload = {
        'updated_at': date.today().isoformat(),
        'coverage': {'sse': 'weekly historical snapshots', 'szse': 'latest snapshot only'},
        'history': history,
        'szse_snapshot': snapshot,
    }
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f'保存完成: {len(history)} 个上交所历史快照、{len(next(iter(snapshot.values()), {}))} 个深交所当前快照')


if __name__ == '__main__':
    main()
