#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
融资融券数据抓取 — 东方财富数据中心API
数据源: https://datacenter-web.eastmoney.com/api/data/v1/get
输出: data/margin_trading.json

融资融券是A股散户杠杆交易的直接体现，作为"大众视角"情绪指标:
  - 融资净买入额(RZJME) > 0: 散户加杠杆看多
  - 融资净买入额(RZJME) < 0: 散户降杠杆看空
  - 融资余额变化趋势: 反映大众情绪的持续方向
"""
import json
import os
import time
import requests
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
OUT_FILE = os.path.join(DATA_DIR, 'margin_trading.json')

API_URL = 'https://datacenter-web.eastmoney.com/api/data/v1/get'
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
    'Accept': 'application/json',
    'Referer': 'https://emdata.eastmoney.com/rzrq/index.html',
}


def fetch_page(page=1, page_size=500):
    """获取一页融资融券历史数据"""
    params = {
        'reportName': 'RPTA_RZRQ_LSHJ',
        'columns': 'ALL',
        'source': 'WEB',
        'sortColumns': 'dim_date',
        'sortTypes': '-1',
        'pageNumber': str(page),
        'pageSize': str(page_size),
        'filter': '',
        'pageNo': str(page),
        'p': str(page),
        'pageNum': str(page),
    }
    for attempt in range(3):
        try:
            resp = requests.get(API_URL, params=params, headers=HEADERS, timeout=20)
            if resp.status_code == 200:
                data = resp.json()
                if data.get('result') and data['result'].get('data'):
                    return data['result']['data']
            return []
        except Exception:
            time.sleep(1.5 ** attempt)
    return []


def fetch_all_margin_data(start_date='2026-01-01'):
    """抓取从start_date开始的全部融资融券数据"""
    print(f'=== 抓取融资融券数据 (从 {start_date}) ===')
    all_records = []
    page = 1
    while True:
        records = fetch_page(page, page_size=200)
        if not records:
            break
        
        filtered = []
        for r in records:
            date_str = r.get('DIM_DATE', '')[:10]
            if date_str >= start_date:
                filtered.append({
                    'date': date_str,
                    # 融资余额(元) — 散户杠杆多头头寸
                    'rzye': r.get('RZYE', 0),
                    # 融资买入额(元) — 当日新增融资买入
                    'rzmre': r.get('RZMRE', 0),
                    # 融资偿还额(元) — 当日融资偿还
                    'rzche': r.get('RZCHE', 0),
                    # 融资净买入额(元) = 买入 - 偿还
                    'rzjme': r.get('RZJME', 0),
                    # 融券余额(元) — 散户做空头寸
                    'rqye': r.get('RQYE', 0),
                    # 融券卖出量(股)
                    'rqmcl': r.get('RQMCL', 0),
                    # 融券偿还量(股)
                    'rqchl': r.get('RQCHL', 0),
                    # 融券净卖出(股)
                    'rqjmg': r.get('RQJMG', 0),
                    # 融资融券总余额(元)
                    'rzrqye': r.get('RZRQYE', 0),
                    # 上证指数
                    'index': r.get('NEW', 0),
                    # 指数涨跌幅
                    'index_change': r.get('ZDF', 0),
                })
        
        all_records.extend(filtered)
        print(f'  页{page}: {len(records)}条, 过滤后{len(filtered)}条 (累计{len(all_records)}条)')
        
        # 检查是否已到达起始日期之前
        if records and records[-1].get('DIM_DATE', '')[:10] < start_date:
            break
        
        page += 1
        time.sleep(0.3)
        if page > 20:  # 安全限制
            break
    
    # 按日期升序排列
    all_records.sort(key=lambda x: x['date'])
    
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_records, f, ensure_ascii=False, indent=2)
    
    print(f'保存完成: {len(all_records)} 条记录 → {OUT_FILE}')
    if all_records:
        print(f'  日期范围: {all_records[0]["date"]} ~ {all_records[-1]["date"]}')
    
    return all_records


if __name__ == '__main__':
    fetch_all_margin_data(start_date='2026-01-01')
