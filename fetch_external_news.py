#!/usr/bin/env python3
"""抓取无需 API Key 的公开信息，并以原文日期建立可审计的事件缓存。

列表页的抓取日期绝不再作为文章发布日期。日期证据优先级：原文页元数据/正文、URL、列表页。
没有可靠日期的条目只保留为 unknown，不进入时间敏感的模型计算。
"""
import html
import json
import os
import re
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

from etf_universe import SECTOR_ETF_MAP

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(BASE_DIR, 'data', 'external_news.json')
HEADERS = {'User-Agent': 'Mozilla/5.0 ETF research bot/2.0'}
SOURCES = [
    {'name': '证监会', 'category': 'policy', 'url': 'https://www.csrc.gov.cn/', 'keywords': ['通知', '公告', '意见', '监管', '证券', '基金', '期权', '资本市场', '交易']},
    {'name': '工信部', 'category': 'industry', 'url': 'https://wap.miit.gov.cn/RRSdy/', 'keywords': ['芯片', '半导体', '人工智能', 'AI', '软件', '电子', '通信', '汽车', '光伏', '新能源', '储能', '工业']},
    {'name': '国家统计局', 'category': 'macro', 'url': 'https://www.stats.gov.cn/sj/zxfb/', 'keywords': ['经济', '工业', '消费', '投资', '价格', '就业', 'PMI', '增长', '统计', '国民经济']},
    {'name': '深交所', 'category': 'exchange', 'url': 'https://www.szse.cn/disclosure/notice/fund/', 'keywords': ['ETF', '基金', '指数', '交易', '市场', '公告', '债券', '期权']},
]


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(); self.links, self.href, self.buf = [], None, []
    def handle_starttag(self, tag, attrs):
        if tag == 'a': self.href, self.buf = dict(attrs).get('href'), []
    def handle_data(self, data):
        if self.href is not None: self.buf.append(data)
    def handle_endtag(self, tag):
        if tag == 'a' and self.href is not None:
            title = re.sub(r'\s+', ' ', html.unescape(''.join(self.buf))).strip()
            if title and self.href: self.links.append((title, self.href))
            self.href, self.buf = None, []


def clean(text):
    return re.sub(r'\s+', ' ', html.unescape(text or '')).strip()


def parse_date(text):
    text = clean(text)
    patterns = [r'(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?', r'(20\d{2})(\d{2})(\d{2})']
    for pattern in patterns:
        found = re.search(pattern, text)
        if found:
            try:
                candidate = date(int(found.group(1)), int(found.group(2)), int(found.group(3)))
                return candidate.isoformat()
            except ValueError:
                pass
    return None


def date_from_detail(body):
    # 官方页面常把发布时间放在 meta，随后才看正文，避免抓到统计期而不是发布日期。
    patterns = [
        r'<meta[^>]+(?:article:published_time|publishdate|pubdate|发布日期|发布时间)[^>]+content=["\']([^"\']+)',
        r'<time[^>]+datetime=["\']([^"\']+)',
        r'(?:发布时间|发布日期|成文日期|发布时间：|发布日期：)\s*([^<]{8,24})',
    ]
    for pattern in patterns:
        found = re.search(pattern, body, flags=re.I)
        if found:
            parsed = parse_date(found.group(1))
            if parsed: return parsed, 'detail_page'
    # 正文中最后再查带完整年份的日期；不使用“今天”兜底。
    parsed = parse_date(body[:12000])
    return (parsed, 'detail_page_text') if parsed else (None, None)


def classify(title, category):
    t = title.lower()
    bullish = ['增长', '回升', '扩张', '放宽', '加快', '改善', '创新高', '超预期', '支持', '促进', '突破']
    # “风险管理/风险提示”常出现在中性政策标题中，不能仅凭“风险”二字判负。
    bearish = ['下滑', '收紧', '处罚', '下跌', '下降', '放缓', '违约', '亏损', '削减', '减少', '恶化']
    b, s = sum(k.lower() in t for k in bullish), sum(k.lower() in t for k in bearish)
    direction = '偏正' if b > s else '偏负' if s > b else '中性'
    high = any(k in title for k in ['重大', '重磅', '政策', '规划', '数据发布', '指数', '监管', '处罚', '降准', '降息'])
    impact = '高' if high else '中' if b or s else '低'
    event_type = {'policy': '政策/监管事件', 'industry': '行业景气事件', 'macro': '宏观数据事件', 'exchange': '交易结构事件'}.get(category, '公开信息事件')
    sectors = []
    for info in SECTOR_ETF_MAP.values():
        if any(k.lower() in t for k in info.get('keywords', [])) and info['sector'] not in sectors:
            sectors.append(info['sector'])
    if not sectors:
        sectors = ['宽基/市场整体'] if category in ('policy', 'macro', 'exchange') else ['待确认']
    if category == 'macro': implication = f'{event_type}：{direction}，先影响市场风险偏好；需由价格、成交和 ETF 份额确认，不能把单次数据直接当成趋势。'
    elif category == 'policy': implication = f'{event_type}：{direction}，影响估值与预期；政策落地前只提高观察权，不直接追涨。'
    elif category == 'exchange': implication = f'{event_type}：主要影响交易结构与产品供给，方向为{direction}；需观察份额变化和成交是否同步。'
    else: implication = f'{event_type}：{direction}，可能改变相关行业预期；需观察行业 ETF 相对宽基的强弱是否持续。'
    return {'event_type': event_type, 'direction': direction, 'impact': impact, 'sectors': sectors[:5], 'implication': implication}


def fetch(url):
    resp = requests.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.content.decode(resp.apparent_encoding or resp.encoding or 'utf-8', errors='ignore')


def collect_source(source, today):
    try: body = fetch(source['url'])
    except Exception as exc:
        print(f"  [WARN] {source['name']}: {exc}"); return []
    parser = LinkParser(); parser.feed(body)
    rows, seen = [], set()
    for title, href in parser.links:
        if len(title) < 8 or not any(k.lower() in title.lower() for k in source['keywords']): continue
        full_url = urljoin(source['url'], href)
        if full_url in seen: continue
        seen.add(full_url)
        published, quality = None, None
        try:
            detail = fetch(full_url)
            published, quality = date_from_detail(detail)
        except Exception:
            pass
        if not published:
            published = parse_date(full_url)
            quality = 'url' if published else 'unknown'
        if not published: continue
        published_day = date.fromisoformat(published)
        if published_day < today - timedelta(days=14) or published_day > today: continue
        info = classify(clean(title), source['category'])
        rows.append({'source': source['name'], 'category': source['category'], 'title': clean(title), 'url': full_url,
                     'published_at': published, 'date_quality': quality, 'fetched_at': datetime.now().isoformat(timespec='seconds'), **info})
        if len(rows) >= 25: break
    return rows


def main():
    today = date.today(); old = {}
    if os.path.exists(OUT_FILE):
        try:
            with open(OUT_FILE, encoding='utf-8') as f: old = json.load(f)
        except Exception: old = {}
    rows = []
    for source in SOURCES:
        fresh = collect_source(source, today); rows.extend(fresh); print(f"  {source['name']}: {len(fresh)} 条有效事件")
    by_url = {r['url']: r for r in old.get('items', []) if r.get('date_quality') not in (None, 'unknown')}
    by_url.update({r['url']: r for r in rows})
    cutoff = today - timedelta(days=30); items = []
    for row in by_url.values():
        try: published = date.fromisoformat(row.get('published_at', ''))
        except (TypeError, ValueError): continue
        if cutoff <= published <= today:
            row['age_days'] = (today - published).days
            items.append(row)
    items.sort(key=lambda r: (r.get('published_at', ''), r.get('fetched_at', '')), reverse=True)
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump({'updated_at': datetime.now().isoformat(timespec='seconds'), 'items': items[:500]}, f, ensure_ascii=False, indent=2)
    print(f'保存完成: {len(items[:500])} 条 → {OUT_FILE}')


if __name__ == '__main__': main()
