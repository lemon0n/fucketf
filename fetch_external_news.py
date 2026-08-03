#!/usr/bin/env python3
"""抓取无需 API Key 的公开政策/行业/宏观新闻，失败时保留旧数据。"""
import html
import json
import os
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(BASE_DIR, 'data', 'external_news.json')
HEADERS = {'User-Agent': 'Mozilla/5.0 ETF research bot/1.0'}

SOURCES = [
    {'name': '证监会', 'category': 'policy', 'url': 'https://www.csrc.gov.cn/',
     'keywords': ['通知', '公告', '意见', '监管', '证券', '基金', '期权', '资本市场', '交易']},
    {'name': '工信部', 'category': 'industry', 'url': 'https://wap.miit.gov.cn/RRSdy/',
     'keywords': ['芯片', '半导体', '人工智能', 'AI', '软件', '电子', '通信', '汽车', '光伏', '新能源', '储能', '工业']},
    {'name': '国家统计局', 'category': 'macro', 'url': 'https://www.stats.gov.cn/sj/zxfb/',
     'keywords': ['经济', '工业', '消费', '投资', '价格', '就业', 'PMI', '增长', '统计', '国民经济']},
    {'name': '深交所', 'category': 'exchange', 'url': 'https://www.szse.cn/disclosure/notice/fund/',
     'keywords': ['ETF', '基金', '指数', '交易', '市场', '公告', '债券', '期权']},
]


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.href, self.buf = [], None, []

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.href = dict(attrs).get('href')
            self.buf = []

    def handle_data(self, data):
        if self.href is not None:
            self.buf.append(data)

    def handle_endtag(self, tag):
        if tag == 'a' and self.href is not None:
            title = re.sub(r'\s+', ' ', html.unescape(''.join(self.buf))).strip()
            if title and self.href:
                self.links.append((title, self.href))
            self.href, self.buf = None, []


def clean(text):
    return re.sub(r'\s+', ' ', html.unescape(text or '')).strip()


def infer_date(text, fallback):
    patterns = [
        r'(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})',
        r'(20\d{2})年(\d{1,2})月(\d{1,2})日',
    ]
    for pattern in patterns:
        found = re.search(pattern, text)
        if found:
            candidate = f'{int(found.group(1)):04d}-{int(found.group(2)):02d}-{int(found.group(3)):02d}'
            try:
                date.fromisoformat(candidate)
                return candidate
            except ValueError:
                pass
    found = re.search(r'(?<!\d)(\d{1,2})[-/.](\d{1,2})(?!\d)', text)
    if found:
        candidate = f'{fallback.year:04d}-{int(found.group(1)):02d}-{int(found.group(2)):02d}'
        try:
            date.fromisoformat(candidate)
            return candidate
        except ValueError:
            pass
    return fallback.isoformat()


def fetch(url):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    encoding = resp.apparent_encoding or resp.encoding or 'utf-8'
    return resp.content.decode(encoding, errors='ignore')


def collect_source(source, today):
    try:
        body = fetch(source['url'])
    except Exception as exc:
        print(f"  [WARN] {source['name']}: {exc}")
        return []
    parser = LinkParser()
    parser.feed(body)
    rows, seen = [], set()
    for title, href in parser.links:
        if len(title) < 8 or not any(k.lower() in title.lower() for k in source['keywords']):
            continue
        full_url = urljoin(source['url'], href)
        if full_url in seen:
            continue
        seen.add(full_url)
        published = infer_date(title, today)
        try:
            published_day = date.fromisoformat(published)
        except ValueError:
            published_day = today
        if published_day < today - timedelta(days=14) or published_day > today + timedelta(days=1):
            continue
        rows.append({'source': source['name'], 'category': source['category'],
                     'title': clean(title), 'url': full_url,
                     'published_at': published, 'fetched_at': datetime.now().isoformat(timespec='seconds')})
        if len(rows) >= 40:
            break
    return rows


def main():
    today = date.today()
    old = {}
    if os.path.exists(OUT_FILE):
        try:
            with open(OUT_FILE, encoding='utf-8') as f:
                old = json.load(f)
        except Exception:
            old = {}
    rows = []
    for source in SOURCES:
        fresh = collect_source(source, today)
        rows.extend(fresh)
        print(f"  {source['name']}: {len(fresh)} 条")
    by_url = {r['url']: r for r in old.get('items', [])}
    by_url.update({r['url']: r for r in rows})
    cutoff = today - timedelta(days=30)
    items = []
    for row in by_url.values():
        try:
            published = date.fromisoformat(row.get('published_at', ''))
        except (TypeError, ValueError):
            continue
        if cutoff <= published <= today + timedelta(days=1):
            items.append(row)
    items.sort(key=lambda r: (r.get('published_at', ''), r.get('fetched_at', '')), reverse=True)
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump({'updated_at': datetime.now().isoformat(timespec='seconds'), 'items': items[:500]}, f, ensure_ascii=False, indent=2)
    print(f'保存完成: {len(items[:500])} 条 → {OUT_FILE}')


if __name__ == '__main__':
    main()
