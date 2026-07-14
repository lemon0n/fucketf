#!/usr/bin/env python3
"""
四大证券报头版标题抓取 — 从同花顺报刊头条列表页获取
数据源: https://stock.10jqka.com.cn/bktt_list/
输出: data/newspapers.json
"""
import json
import os
import re
import time
from datetime import date, timedelta
import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
OUT_FILE = os.path.join(DATA_DIR, 'newspapers.json')

LIST_BASE = "https://stock.10jqka.com.cn/bktt_list/"
LIST_PAGE_URL = "https://stock.10jqka.com.cn/bktt_list/index_{p}.shtml"
PAPERS = ["中国证券报", "上海证券报", "证券时报", "证券日报"]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://stock.10jqka.com.cn/bktt_list/",
}

def decode_content(resp):
    raw = resp.content
    if not raw:
        return ""
    head = raw[:2048]
    m = re.search(rb'charset=["\']?\s*([a-zA-Z0-9\-]+)', head, re.I)
    meta_enc = m.group(1).decode("ascii", "ignore").lower() if m else None
    candidates = []
    for e in (meta_enc, resp.apparent_encoding, resp.encoding):
        if e:
            e = e.lower().replace("gb2312", "gbk")
            if e not in candidates:
                candidates.append(e)
    for e in ("utf-8", "gbk"):
        if e not in candidates:
            candidates.append(e)
    for e in candidates:
        try:
            return raw.decode(e)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="ignore")

def fetch(url, session=None):
    s = session or requests.Session()
    s.headers.update(HEADERS)
    for attempt in range(4):
        try:
            resp = s.get(url, timeout=25)
            if resp.status_code == 200 and resp.content:
                return decode_content(resp)
        except:
            pass
        time.sleep(1.5 ** attempt)
    return None

# 列表页文章链接
LIST_RE = re.compile(r'href="(https?://stock\.10jqka\.com\.cn/(\d{8})/c\d+\.shtml)"', re.I)

def collect_urls(days=5):
    """收集最近N天的文章URL"""
    collected = {}
    session = requests.Session()
    session.headers.update(HEADERS)
    for p in range(1, 5):
        url = LIST_BASE if p == 1 else LIST_PAGE_URL.format(p=p)
        html = fetch(url, session)
        if not html:
            continue
        for m in LIST_RE.finditer(html):
            art_url, ymd = m.group(1), m.group(2)
            if ymd not in collected:
                try:
                    d = date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:8]))
                    collected[ymd] = (d, art_url)
                except ValueError:
                    continue
    ordered = sorted(collected.items(), key=lambda kv: kv[1][0], reverse=True)
    return [(d, ymd, url) for ymd, (d, url) in ordered[:days]]

# 文章页解析
CONTENT_RE = re.compile(r'<div class="news-content-parsed">(.*?)</div>\s*<div', re.S)
HEADER_RE = re.compile(r'<span[^>]*style="[^"]*color:\s*red[^"]*"[^>]*>\s*([^<]+?)\s*</span>', re.I)
ARTICLE_RE = re.compile(r'<a[^>]*href="([^"]*10jqka\.com\.cn/(?:[a-z]+/)*\d{8}/c\d+\.shtml)"[^>]*>([^<]+)</a>', re.I)
TAG_RE = re.compile(r'<[^>]+>')
STOCKCODE_RE = re.compile(r'^[^（）]*[（(][0-9A-Za-z]{4,}[)）]$')

def normalize(text):
    if not text:
        return ""
    text = text.replace("&nbsp;", " ").replace("\u3000", " ").replace("\xa0", " ")
    text = TAG_RE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()

def extract_headlines(seg, name):
    cands = [(g[0], normalize(g[1])) for g in ARTICLE_RE.findall(seg)]
    out, seen = [], set()
    for href, t in cands:
        if t and t != name and not STOCKCODE_RE.match(t) and t not in seen:
            seen.add(t)
            out.append(t)
    return out

def parse_article(html):
    if not html:
        return None
    m = CONTENT_RE.search(html)
    block = m.group(1) if m else html
    headers = list(HEADER_RE.finditer(block))
    result = {p: [] for p in PAPERS}

    if headers:
        for i, h in enumerate(headers):
            name = normalize(h.group(1))
            if name not in result:
                continue
            seg_start = h.end()
            seg_end = headers[i + 1].start() if i + 1 < len(headers) else len(block)
            result[name] = extract_headlines(block[seg_start:seg_end], name)
    else:
        # fallback
        idxs = []
        for p in PAPERS:
            m2 = re.search(r'>\s*(' + re.escape(p) + r')\s*<', block)
            if m2:
                idxs.append((m2.start(), p))
        idxs.sort()
        for i, (start, p) in enumerate(idxs):
            end = idxs[i + 1][0] if i + 1 < len(idxs) else len(block)
            result[p] = extract_headlines(block[start:end], p)

    return {p: list(titles) for p, titles in result.items()}

def scrape_newspapers(days=5):
    """抓取最近N天的四大报"""
    print(f'=== 抓取四大证券报（最近{days}天）===')
    os.makedirs(DATA_DIR, exist_ok=True)

    # 加载已有数据
    if os.path.exists(OUT_FILE):
        with open(OUT_FILE) as f:
            results = json.load(f)
    else:
        results = {}
    print(f'已有 {len(results)} 天数据')

    articles = collect_urls(days)
    print(f'列表页收集到 {len(articles)} 篇文章')

    session = requests.Session()
    session.headers.update(HEADERS)

    for d, ymd, art_url in articles:
        key = f'{d.year:04d}-{d.month:02d}-{d.day:02d}'
        if key in results and results[key] and any(results[key].values()):
            print(f'  {key}: 已有数据, 跳过')
            continue

        print(f'  抓取 {key}...')
        html = fetch(art_url, session)
        time.sleep(0.5)
        if not html:
            print(f'    [WARN] 抓取失败')
            continue

        parsed = parse_article(html)
        if not parsed or not any(parsed.values()):
            print(f'    [WARN] 未解析出标题')
            results[key] = {p: [] for p in PAPERS}
        else:
            results[key] = {p: parsed.get(p, []) for p in PAPERS}
            counts = {p: len(parsed.get(p, [])) for p in PAPERS}
            print(f'    {counts}')

    with open(OUT_FILE, 'w') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    have_data = sum(1 for v in results.values() if v and any(v.values()))
    print(f'保存完成: {have_data} 天有数据')
    return results

if __name__ == '__main__':
    scrape_newspapers(days=10)
