#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量补爬四大报历史数据 (2026-01 ~ 2026-06)"""
import json, os, re, time
from datetime import date
import requests

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'data')
OUT_FILE = os.path.join(DATA_DIR, 'newspapers.json')

HEADERS = {'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
           'Accept-Language':'zh-CN,zh;q=0.9','Referer':'https://stock.10jqka.com.cn/bktt_list/'}
PAPERS = ["中国证券报","上海证券报","证券时报","证券日报"]
LIST_RE = re.compile(r'href="(https?://stock\.10jqka\.com\.cn/(\d{8})/c\d+\.shtml)"', re.I)
CONTENT_RE = re.compile(r'<div class="news-content-parsed">(.*?)</div>\s*<div', re.S)
HEADER_RE = re.compile(r'<span[^>]*style="[^"]*color:\s*red[^"]*"[^>]*>\s*([^<]+?)\s*</span>', re.I)
ARTICLE_RE = re.compile(r'<a[^>]*href="([^"]*10jqka\.com\.cn/(?:[a-z]+/)*\d{8}/c\d+\.shtml)"[^>]*>([^<]+)</a>', re.I)
TAG_RE = re.compile(r'<[^>]+>')
STOCKCODE_RE = re.compile(r'^[^（）]*[（(][0-9A-Za-z]{4,}[)）]$')

def decode(resp):
    raw = resp.content
    for e in ('gbk','utf-8'):
        try: return raw.decode(e)
        except: pass
    return raw.decode('utf-8',errors='ignore')

def fetch(url):
    for _ in range(3):
        try:
            r = requests.get(url, headers=HEADERS, timeout=20)
            if r.status_code==200 and r.content: return decode(r)
        except: pass
        time.sleep(1)
    return None

def normalize(text):
    if not text: return ""
    text = text.replace("&nbsp;"," ").replace("\u3000"," ").replace("\xa0"," ")
    text = TAG_RE.sub("",text)
    return re.sub(r"\s+"," ",text).strip()

def extract_headlines(seg, name):
    cands = [(g[0],normalize(g[1])) for g in ARTICLE_RE.findall(seg)]
    out,seen = [],set()
    for href,t in cands:
        if t and t!=name and not STOCKCODE_RE.match(t) and t not in seen:
            seen.add(t); out.append(t)
    return out

def parse_article(html):
    if not html: return None
    m = CONTENT_RE.search(html)
    block = m.group(1) if m else html
    headers = list(HEADER_RE.finditer(block))
    result = {p:[] for p in PAPERS}
    if headers:
        for i,h in enumerate(headers):
            name = normalize(h.group(1))
            if name not in result: continue
            seg_end = headers[i+1].start() if i+1<len(headers) else len(block)
            result[name] = extract_headlines(block[h.end():seg_end], name)
    else:
        idxs = []
        for p in PAPERS:
            m2 = re.search(r'>\s*('+re.escape(p)+r')\s*<', block)
            if m2: idxs.append((m2.start(),p))
        idxs.sort()
        for i,(start,p) in enumerate(idxs):
            end = idxs[i+1][0] if i+1<len(idxs) else len(block)
            result[p] = extract_headlines(block[start:end], p)
    return {p:list(t) for p,t in result.items()}

# 收集所有1-6月文章URL
print('=== 收集历史文章URL ===')
all_articles = {}
seen_urls = set()
for p in range(1, 12):  # 翻前11页足够覆盖半年
    url = 'https://stock.10jqka.com.cn/bktt_list/' if p==1 else f'https://stock.10jqka.com.cn/bktt_list/index_{p}.shtml'
    html = fetch(url)
    if not html: continue
    for m in LIST_RE.finditer(html):
        art_url, ymd = m.group(1), m.group(2)
        # 只要2026-01-01到2026-06-30
        if '20260101' <= ymd <= '20260630' and art_url not in seen_urls:
            seen_urls.add(art_url)
            try:
                d = date(int(ymd[:4]),int(ymd[4:6]),int(ymd[6:8]))
                all_articles[d] = art_url
            except: pass
    print(f'  页{p}: 累计收集 {len(all_articles)} 篇 (1-6月)')
    time.sleep(0.3)

print(f'\n共收集 {len(all_articles)} 天文章待抓取')

# 加载已有数据
if os.path.exists(OUT_FILE):
    with open(OUT_FILE) as f:
        results = json.load(f)
else:
    results = {}
have = sum(1 for v in results.values() if v and any(v.values()))
print(f'已有 {len(results)} 天({have}天有数据)')

# 批量抓取
new_count = 0
fail_count = 0
for d in sorted(all_articles.keys()):
    key = f'{d.year:04d}-{d.month:02d}-{d.day:02d}'
    if key in results and results[key] and any(results[key].values()):
        continue
    html = fetch(all_articles[d])
    time.sleep(0.3)
    if not html:
        fail_count += 1; continue
    parsed = parse_article(html)
    if parsed and any(parsed.values()):
        results[key] = {p:parsed.get(p,[]) for p in PAPERS}
        new_count += 1
        if new_count % 10 == 0:
            print(f'  已抓取 {new_count} 天... (最新: {key})')
            with open(OUT_FILE,'w') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
    else:
        results[key] = {p:[] for p in PAPERS}
        fail_count += 1

# 保存
with open(OUT_FILE,'w') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)

have = sum(1 for v in results.values() if v and any(v.values()))
total = len(results)
# 统计覆盖
months = {}
for k in sorted(results.keys()):
    m = k[:7]
    months[m] = months.get(m, 0) + (1 if results[k] and any(results[k].values()) else 0)
print(f'\n=== 完成 ===')
print(f'新增 {new_count} 天, 失败 {fail_count} 天')
print(f'总计 {total} 天, 有数据 {have} 天')
print(f'\n各月覆盖:')
for m in sorted(months.keys()):
    print(f'  {m}: {months[m]}天')
