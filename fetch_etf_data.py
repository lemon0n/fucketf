#!/usr/bin/env python3
"""
ETF数据获取 — 使用腾讯财经API（支持前复权，稳定可靠）
API: http://web.ifzq.gtimg.cn/appstock/app/fqkline/get
支持增量更新和全量拉取
"""
import json
import os
import time
import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
ETF_HISTORY_PATH = os.path.join(DATA_DIR, 'etf_history.json')

# 腾讯API: sh=上海, sz=深圳
ETF_SYMBOLS = {
    'sh512760': {'name': '半导体ETF', 'code': '512760'},
    'sz159995': {'name': '芯片ETF', 'code': '159995'},
    'sh515980': {'name': '人工智能ETF', 'code': '515980'},
    'sz159592': {'name': '卫星产业ETF', 'code': '159592'},
    'sh515120': {'name': '创新药ETF', 'code': '515120'},
    'sh516160': {'name': '新能源ETF', 'code': '516160'},
    'sh510150': {'name': '消费ETF', 'code': '510150'},
    'sh518880': {'name': '黄金ETF', 'code': '518880'},
    'sh512000': {'name': '券商ETF', 'code': '512000'},
    'sh512660': {'name': '军工ETF', 'code': '512660'},
    'sh510300': {'name': '沪深300ETF', 'code': '510300'},
}

START_DATE = '2026-01-05'
TENCENT_API = 'http://web.ifzq.gtimg.cn/appstock/app/fqkline/get'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
}

def fetch_kline(symbol, start_date='2026-01-05', end_date='2026-12-31', max_retries=5):
    """从腾讯API获取前复权日K数据
    
    Args:
        symbol: sh512760 或 sz159995
        start_date: 开始日期
        end_date: 结束日期
    Returns:
        list of {date, open, close, high, low, volume}
    """
    # 参数格式: param=symbol,day,start,end,datalen,qfq
    param = f'{symbol},day,{start_date},{end_date},640,qfq'
    url = f'{TENCENT_API}?param={param}'

    for attempt in range(max_retries):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                # 腾讯API返回 qfqday 或 day（取决于是否有复权数据）
                klines = (data.get('data', {}).get(symbol, {}).get('qfqday')
                          or data.get('data', {}).get(symbol, {}).get('day')
                          or [])
                if klines:
                    records = []
                    for k in klines:
                        d = k[0]
                        if d >= START_DATE:
                            records.append({
                                'date': d,
                                'open': round(float(k[1]), 3),
                                'close': round(float(k[2]), 3),
                                'high': round(float(k[3]), 3),
                                'low': round(float(k[4]), 3),
                                'volume': int(float(k[5])) if k[5] else 0,
                            })
                    return records
            time.sleep(2 * (attempt + 1))
        except Exception as e:
            if attempt == max_retries - 1:
                print(f'  [ERROR] {symbol}: {e}')
            time.sleep(2 * (attempt + 1))
    return []

def incremental_update():
    """增量更新：只拉最近15天，覆盖重叠+追加新日期"""
    from datetime import date
    print('=== ETF数据增量更新（腾讯财经API · 前复权）===')

    if os.path.exists(ETF_HISTORY_PATH):
        with open(ETF_HISTORY_PATH) as f:
            existing = json.load(f)
    else:
        existing = {}

    today_str = date.today().strftime('%Y-%m-%d')

    for symbol, info in ETF_SYMBOLS.items():
        code = info['code']
        name = info['name']

        # 检查是否已是最新
        if code in existing and existing[code].get('data'):
            last_date = existing[code]['data'][-1]['date']
            if last_date >= today_str:
                print(f'  {name}: 已是最新 ({last_date}), 跳过')
                continue

        # 增量模式：拉最近30天数据（覆盖周末+节假日）
        start = '2026-06-01' if code in existing else START_DATE
        records = fetch_kline(symbol, start_date=start, end_date='2026-12-31')

        if not records:
            print(f'  [WARN] {name}: 获取失败')
            if code in existing:
                print(f'         保留旧数据 ({len(existing[code]["data"])}条)')
            continue

        if code not in existing or not existing[code].get('data'):
            existing[code] = {'name': name, 'data': records}
            print(f'  {name}: 首次拉取 {len(records)}条 ({records[0]["date"]}~{records[-1]["date"]})')
        else:
            # 增量合并：覆盖重叠日期 + 追加新日期
            old_data = existing[code]['data']
            old_map = {d['date']: i for i, d in enumerate(old_data)}
            replaced = appended = 0
            for rec in records:
                if rec['date'] in old_map:
                    old_data[old_map[rec['date']]] = rec
                    replaced += 1
                elif rec['date'] >= START_DATE:
                    old_data.append(rec)
                    appended += 1
            old_data.sort(key=lambda x: x['date'])
            # 截取2026-01-05起
            old_data = [d for d in old_data if d['date'] >= START_DATE]
            existing[code] = {'name': name, 'data': old_data}
            print(f'  {name}: 覆盖{replaced}+新增{appended}, 共{len(old_data)}条 ({old_data[-1]["date"]})')

        time.sleep(0.3)

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ETF_HISTORY_PATH, 'w') as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    print(f'保存完成: {len(existing)}/{len(ETF_SYMBOLS)} 个ETF')
    return existing

def full_fetch():
    """全量拉取所有ETF历史数据（前复权）"""
    print('=== ETF数据全量拉取（腾讯财经API · 前复权）===')
    result = {}
    for symbol, info in ETF_SYMBOLS.items():
        code = info['code']
        name = info['name']
        records = fetch_kline(symbol, start_date=START_DATE, end_date='2026-12-31')
        if records:
            result[code] = {'name': name, 'data': records}
            print(f'  {name}: {len(records)}条 ({records[0]["date"]}~{records[-1]["date"]})')
        else:
            print(f'  [ERROR] {name}: 获取失败')
        time.sleep(0.3)

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(ETF_HISTORY_PATH, 'w') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f'保存完成: {len(result)}/{len(ETF_SYMBOLS)} 个ETF')
    return result

if __name__ == '__main__':
    import sys
    if '--full' in sys.argv:
        full_fetch()
    else:
        incremental_update()
