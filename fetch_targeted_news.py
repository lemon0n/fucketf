#!/usr/bin/env python3
"""按当前推荐/回避候选补充逐只ETF新闻流。

该步骤在规则模型之后运行，只服务于报告深挖，不回填当日交易评分。使用无Key的
Bing News RSS做发现，结果必须满足：14日内、标题直接命中ETF关键词、来源在可信
域名表内。搜索失败保留缓存，不能用空结果覆盖已有证据。
"""
from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, urlencode, urlparse

import requests

from etf_universe import SECTOR_ETF_MAP
from fetch_external_news import classify
from market_diagnostics import match_target_news_keywords, share_flow_rows, target_news_keywords


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUT_FILE = os.path.join(DATA_DIR, "targeted_news.json")
MODEL_FILE = os.path.join(DATA_DIR, "model_results.json")
PRICE_FILE = os.path.join(DATA_DIR, "etf_history.json")
SHARE_FILE = os.path.join(DATA_DIR, "etf_shares.json")
BING_RSS = "https://www.bing.com/news/search"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; fucketf-targeted-research/5.1)"}
TRUSTED_DOMAINS = (
    "gov.cn", "csrc.gov.cn", "stats.gov.cn", "pbc.gov.cn", "nhsa.gov.cn",
    "nmpa.gov.cn", "cde.org.cn", "miit.gov.cn", "ndrc.gov.cn", "nea.gov.cn",
    "sse.com.cn", "szse.cn", "xinhuanet.com", "news.cn", "people.com.cn",
    "cctv.com", "stcn.com", "cs.com.cn", "cnpharm.com",
)
PROFESSIONAL_MEDIA = ("stcn.com", "cs.com.cn", "cnpharm.com", "xinhuanet.com", "news.cn", "people.com.cn", "cctv.com")

QUERY_HINTS = {
    "dividend": "分红 回购 增持 A股",
    "healthcare": "创新药 医保目录 药品审评",
    "property": "房地产 公积金 住房 政策",
    "ai": "人工智能 AI服务器 算力 液冷",
    "chips": "半导体 芯片 集成电路 政策",
    "small_cap": "中证1000 小盘 ETF 资金",
    "mid_cap": "中证500 中盘 ETF 资金",
    "large_cap": "沪深300 上证50 ETF 资金",
    "hk_tech": "中概互联网 恒生科技 平台经济",
    "new_energy": "新能源 光伏 储能 政策",
    "broker": "券商 证券 资本市场 政策",
    "bank": "银行 信贷 息差 政策",
    "gold": "黄金 贵金属 避险",
    "bond": "国债 长债 利率",
}


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def original_link(link):
    """尽量从搜索跳转URL中恢复原文；无法恢复时保留搜索结果链接。"""
    query = parse_qs(urlparse(link).query)
    for key in ("url", "u", "target"):
        value = query.get(key, [None])[0]
        if value and value.startswith("http"):
            return value
    return link


def trusted_source(url):
    host = urlparse(url).netloc.lower().split(":")[0]
    return any(host == domain or host.endswith("." + domain) for domain in TRUSTED_DOMAINS)


def source_tier(url):
    host = urlparse(url).netloc.lower().split(":")[0]
    if any(host == domain or host.endswith("." + domain) for domain in PROFESSIONAL_MEDIA):
        return "专业媒体"
    return "官方原文"


def parse_rss(xml_text, code, info, today=None):
    today = today or date.today()
    cutoff = today - timedelta(days=13)
    root = ET.fromstring(xml_text)
    rows = []
    for item in root.findall(".//item"):
        title = " ".join((item.findtext("title") or "").split()).strip()
        link = original_link((item.findtext("link") or "").strip())
        published_raw = (item.findtext("pubDate") or "").strip()
        if not title or not link or not published_raw:
            continue
        try:
            published_dt = parsedate_to_datetime(published_raw)
            if published_dt.tzinfo is None:
                published_dt = published_dt.replace(tzinfo=timezone.utc)
            published = published_dt.date()
        except (TypeError, ValueError, OverflowError):
            continue
        matched = match_target_news_keywords(title, info)
        if not matched or not (cutoff <= published <= today) or not trusted_source(link):
            continue
        source = ""
        for child in item:
            if child.tag.rsplit("}", 1)[-1].lower() == "source":
                source = (child.text or "").strip()
                break
        classified = classify(title, "industry")
        rows.append({
            "source": source or urlparse(link).netloc,
            "source_tier": source_tier(link),
            "category": "targeted_search",
            "event_type": classified["event_type"],
            "title": title,
            "url": link,
            "published_at": published.isoformat(),
            "date_quality": "rss_published",
            "fetched_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "direction": classified["direction"],
            "impact": classified["impact"],
            "target_codes": [code],
            "matched_keywords": matched[:5],
            "retrieval_kind": "targeted_search_discovery",
            "usage_policy": "报告补充；不回填当日规则信号",
        })
    return rows


def fetch_target(code, info):
    group = info.get("group", info.get("sector", ""))
    query = QUERY_HINTS.get(group) or " ".join(target_news_keywords(info)[:4])
    params = {"q": query, "format": "rss", "setlang": "zh-hans"}
    response = requests.get(f"{BING_RSS}?{urlencode(params)}", headers=HEADERS, timeout=(5, 15))
    response.raise_for_status()
    return parse_rss(response.text, code, info)


def target_codes(model, prices, shares, limit=9):
    latest = model.get("latest_decision", {})
    result = []

    def add(code):
        if code in SECTOR_ETF_MAP and code not in result:
            result.append(code)

    for row in latest.get("etf_selection", []):
        add(row.get("code"))
    for row in reversed(latest.get("rankings", [])):
        code = row.get("code")
        if SECTOR_ETF_MAP.get(code, {}).get("risk_on") == 1:
            add(code)
        if len(result) >= 6:
            break
    market_days = sorted({row.get("date") for value in prices.values() for row in value.get("data", []) if row.get("date")})
    if market_days:
        for row in sorted(share_flow_rows(prices, shares, market_days[-1]), key=lambda x: x["estimated_flow_yi"]):
            if SECTOR_ETF_MAP.get(row["code"], {}).get("risk_on") == 1:
                add(row["code"])
            if len(result) >= limit:
                break
    return result[:limit]


def main():
    model = load_json(MODEL_FILE, {})
    prices = load_json(PRICE_FILE, {})
    shares = load_json(SHARE_FILE, {})
    old = load_json(OUT_FILE, {"items": []})
    codes = target_codes(model, prices, shares)
    fresh, health = [], {}
    with ThreadPoolExecutor(max_workers=min(5, max(1, len(codes)))) as pool:
        futures = {pool.submit(fetch_target, code, SECTOR_ETF_MAP[code]): code for code in codes}
        for future in as_completed(futures):
            code = futures[future]
            try:
                rows = future.result()
                fresh.extend(rows)
                health[code] = {"status": "ok", "records": len(rows)}
                print(f"  {code} {SECTOR_ETF_MAP[code]['name']}: {len(rows)} 条")
            except Exception as exc:
                health[code] = {"status": "cached", "error": f"{type(exc).__name__}: {exc}"[:180]}
                print(f"  [WARN] {code} {SECTOR_ETF_MAP[code]['name']}: {exc}")

    cutoff = date.today() - timedelta(days=30)
    merged = {}
    for row in list(old.get("items", [])) + fresh:
        try:
            published = date.fromisoformat(str(row.get("published_at", ""))[:10])
        except ValueError:
            continue
        if not cutoff <= published <= date.today():
            continue
        key = (re.sub(r"\W+", "", row.get("title", "")).lower(), tuple(sorted(row.get("target_codes", []))))
        merged[key] = row
    items = sorted(merged.values(), key=lambda row: row.get("published_at", ""), reverse=True)[:250]
    payload = {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "target_codes": codes,
        "source_health": health,
        "items": items,
        "usage_policy": "定向搜索只补充逐只ETF报告；不进入当日规则评分。",
    }
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    print(f"保存完成: {len(items)} 条 → {OUT_FILE}")


if __name__ == "__main__":
    main()
