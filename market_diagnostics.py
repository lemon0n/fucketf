#!/usr/bin/env python3
"""生成面向交易判断的八模块市场诊断。

本文件刻意不调用大模型。所有结论都由结构化数据、固定阈值和固定句式生成，
从而保证较弱模型或完全没有模型时，报告仍能回答：发生了什么、意味着什么、
接下来验证什么。真实资金、代理指标和数据缺口必须分开呈现。
"""
from __future__ import annotations

import json
import math
import os
import re
from datetime import date, datetime, timedelta
from statistics import median
from urllib.parse import urlparse

from etf_model_run import (
    HS300_CODE,
    SECTOR_ETF_MAP,
    analyze_newspaper_sentiment,
    compute_behavior_signals,
    compute_market_state,
    get_index,
    get_trading_days,
)


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_PATH = os.path.join(DATA_DIR, "market_diagnostics.json")

PATHS = {
    "prices": os.path.join(DATA_DIR, "etf_history.json"),
    "model": os.path.join(DATA_DIR, "model_results.json"),
    "econometric": os.path.join(DATA_DIR, "econometric_results.json"),
    "newspapers": os.path.join(DATA_DIR, "newspapers.json"),
    "margin": os.path.join(DATA_DIR, "margin_trading.json"),
    "shares": os.path.join(DATA_DIR, "etf_shares.json"),
    "external": os.path.join(DATA_DIR, "external_news.json"),
    "targeted_news": os.path.join(DATA_DIR, "targeted_news.json"),
    "macro": os.path.join(DATA_DIR, "macro_data.json"),
}

SOURCE_URLS = {
    "sse_shares": "https://www.sse.com.cn/market/funddata/volumn/etfvolumn/",
    "sse_market": "https://etf.sse.com.cn/marketdata/",
    "szse_funds": "https://fund.szse.cn/marketdata/fundslist/index.html",
    "margin": "https://data.eastmoney.com/rzrq/",
    "newspapers": "https://stock.10jqka.com.cn/bktt_list/",
    "nbs": "https://www.stats.gov.cn/sj/zxfb/",
    "northbound_policy": "https://www.hkex.com.hk/Mutual-Market/Stock-Connect/Top-Stock-Connect-Shareholdings/Northbound-SZ?sc_lang=zh-HK",
}

DEFENSIVE_GROUPS = {"dividend", "gold", "bond", "cash"}
OVERSEAS_GROUPS = {"hk_tech", "us_equity"}
INSTITUTION_PROXY_GROUPS = {"large_cap", "mid_cap", "small_cap", "dividend", "bond", "gold"}

# 只用于逐只ETF新闻检索，不改动历史交易模型的关键词，避免一次报告优化
# 悄悄改变回测。别名按同类组维护，命中标题后仍必须展示原文和日期。
NEWS_ALIASES_BY_GROUP = {
    "large_cap": ["沪深300", "上证50", "蓝筹", "大盘"],
    "mid_cap": ["中证500", "中盘"],
    "small_cap": ["中证1000", "小盘", "微盘"],
    "dividend": ["红利", "高股息", "股息", "分红", "回购", "增持"],
    "chips": ["半导体", "芯片", "集成电路", "存储", "封测"],
    "ai": ["人工智能", "AI服务器", "AI 服务器", "算力", "大模型", "具身智能", "液冷", "宇树"],
    "aerospace": ["商业航天", "航天", "卫星", "火箭"],
    "healthcare": ["创新药", "医药", "医疗", "生物医药", "医保目录", "药品审评"],
    "new_energy": ["新能源", "光伏", "锂电", "储能", "太阳能"],
    "consumption": ["消费", "零售", "食品", "白酒", "家电"],
    "broker": ["券商", "证券公司", "资本市场", "两融"],
    "bank": ["银行", "息差", "信贷"],
    "property": ["房地产", "地产", "楼市", "住房", "公积金", "带押过户"],
    "defense": ["军工", "国防", "军贸", "装备"],
    "hk_tech": ["中概", "恒生科技", "港股科技", "平台经济", "互联网平台"],
    "us_equity": ["纳斯达克", "标普500", "美股科技", "美国股市"],
    "gold": ["黄金", "贵金属", "避险"],
    "bond": ["国债", "长债", "债券", "利率", "降息"],
    "cash": ["货币基金", "现金管理", "流动性"],
}

NEWS_POSITIVE = ["增长", "回升", "扩张", "改善", "创新高", "超预期", "支持", "促进", "突破", "放量", "增持", "回购", "分红", "提高", "优化"]
NEWS_NEGATIVE = ["下滑", "收紧", "处罚", "下跌", "下降", "放缓", "违约", "亏损", "削减", "恶化", "限制", "暂停"]
OFFICIAL_DOMAINS = ("gov.cn", "csrc.gov.cn", "stats.gov.cn", "pbc.gov.cn", "nhsa.gov.cn", "nmpa.gov.cn", "sse.com.cn", "szse.cn")
# 这些词单独出现时歧义太大。例如“互联网券商”不代表中概互联网，普通“智能”
# 也不自动归入AI算力；只有同时命中更具体的同组词才保留。
AMBIGUOUS_NEWS_TERMS_BY_GROUP = {
    "hk_tech": {"互联网"},
    "ai": {"智能"},
    "healthcare": {"健康", "生物"},
}


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def save_json(path, payload):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def clip(value, low=-1.0, high=1.0):
    return max(low, min(high, value))


def mean(values):
    return sum(values) / len(values) if values else 0.0


def safe_pct(numerator, denominator):
    return numerator / denominator * 100 if denominator else 0.0


def score_status(score):
    if score >= 45:
        return "明显偏强", "positive"
    if score >= 15:
        return "略偏强", "positive"
    if score > -15:
        return "中性", "neutral"
    if score > -45:
        return "略偏弱", "negative"
    return "明显偏弱", "negative"


def evidence(label, value, source, as_of, kind="真实数据", url=None):
    return {
        "label": label,
        "value": value,
        "source": source,
        "as_of": as_of,
        "kind": kind,
        "url": url,
    }


def module(module_id, order, title, score, confidence, conclusion, evidence_rows,
           implication, watch, limitation=""):
    status, tone = score_status(score)
    return {
        "id": module_id,
        "order": order,
        "title": title,
        "score": round(float(score), 1),
        "status": status,
        "tone": tone,
        "confidence": confidence,
        "conclusion": conclusion,
        "evidence": evidence_rows,
        "implication": implication,
        "watch": watch,
        "limitation": limitation,
    }


def records_on_or_before(etf_data, code, as_of):
    return [row for row in etf_data.get(code, {}).get("data", []) if row.get("date", "") <= as_of]


def return_pct(etf_data, code, as_of, window):
    rows = records_on_or_before(etf_data, code, as_of)
    if len(rows) <= window or not rows[-window - 1].get("close"):
        return None
    return (rows[-1]["close"] / rows[-window - 1]["close"] - 1) * 100


def day_return_pct(etf_data, code, as_of):
    return return_pct(etf_data, code, as_of, 1)


def volume_ratio(etf_data, code, as_of, window=20):
    rows = records_on_or_before(etf_data, code, as_of)
    if len(rows) <= window:
        return None
    previous = [float(row.get("volume", 0) or 0) for row in rows[-window - 1:-1]]
    base = mean(previous)
    return float(rows[-1].get("volume", 0) or 0) / base if base > 0 else None


def close_location(row):
    high, low, close = float(row.get("high", 0)), float(row.get("low", 0)), float(row.get("close", 0))
    return (close - low) / (high - low) if high > low else 0.5


def latest_margin_detail(rows, as_of):
    usable = sorted((row for row in rows if row.get("date", "") <= as_of), key=lambda row: row["date"])
    if len(usable) < 11:
        return {"available": False, "score": 0.0}
    window = usable[-60:]
    net = [float(row.get("rzjme", 0) or 0) / 1e8 for row in window]
    balance_change = [0.0] + [
        (float(window[i].get("rzye", 0) or 0) - float(window[i - 1].get("rzye", 0) or 0)) / 1e8
        for i in range(1, len(window))
    ]
    buy_sell = [
        float(row.get("rzmre", 0) or 0) / (float(row.get("rzche", 0) or 0) + 1)
        for row in window
    ]

    def zscore(value, values):
        avg = mean(values)
        std = math.sqrt(mean([(item - avg) ** 2 for item in values]))
        return clip((value - avg) / std, -3, 3) if std > 1e-8 else 0.0

    z_net = zscore(net[-1], net)
    z_balance = zscore(balance_change[-1], balance_change)
    z_ratio = zscore(buy_sell[-1], buy_sell)
    score = (0.5 * z_net + 0.3 * z_balance + 0.2 * z_ratio) / 3
    five_day_change = 0.0
    if len(usable) >= 6 and float(usable[-6].get("rzye", 0) or 0):
        five_day_change = (
            float(usable[-1].get("rzye", 0) or 0) / float(usable[-6].get("rzye", 0) or 0) - 1
        ) * 100
    return {
        "available": True,
        "date": usable[-1]["date"],
        "score": round(score, 4),
        "net_buy_yi": round(net[-1], 2),
        "balance_5d_pct": round(five_day_change, 3),
        "buy_sell_ratio": round(buy_sell[-1], 4),
        "z_components": {
            "net_buy": round(z_net, 3),
            "balance_change": round(z_balance, 3),
            "buy_sell_ratio": round(z_ratio, 3),
        },
    }


def merge_share_history(raw):
    history = {str(day): dict(values) for day, values in raw.get("history", {}).items()}
    for day, values in raw.get("szse_snapshot", {}).items():
        history.setdefault(str(day), {}).update(values)
    return history


def share_flow_rows(etf_data, shares_raw, as_of):
    history = merge_share_history(shares_raw if isinstance(shares_raw, dict) else {})
    result = []
    for code, info in SECTOR_ETF_MAP.items():
        dates = sorted(day for day, values in history.items() if day <= as_of and code in values)
        if len(dates) < 2:
            continue
        previous_date, current_date = dates[-2], dates[-1]
        previous = float(history[previous_date].get(code, 0) or 0)
        current = float(history[current_date].get(code, 0) or 0)
        if previous <= 0:
            continue
        price_rows = records_on_or_before(etf_data, code, current_date)
        if not price_rows:
            continue
        close = float(price_rows[-1].get("close", 0) or 0)
        delta = current - previous
        result.append({
            "code": code,
            "name": info["name"],
            "sector": info["sector"],
            "group": info.get("group", info["sector"]),
            "previous_date": previous_date,
            "current_date": current_date,
            "interval_days": (date.fromisoformat(current_date) - date.fromisoformat(previous_date)).days,
            "share_change_pct": round(delta / previous * 100, 4),
            "estimated_flow_yi": round(delta * close / 1e8, 4),
            "shares": current,
        })
    return sorted(result, key=lambda row: row["estimated_flow_yi"], reverse=True)


def group_representatives(etf_data, as_of):
    candidates = {}
    for code, info in SECTOR_ETF_MAP.items():
        group = info.get("group", info["sector"])
        if info.get("risk_on") != 1 or group in OVERSEAS_GROUPS:
            continue
        rows = records_on_or_before(etf_data, code, as_of)
        if len(rows) < 21:
            continue
        avg_turnover = mean([
            float(row.get("close", 0) or 0) * float(row.get("volume", 0) or 0)
            for row in rows[-20:]
        ])
        current = candidates.get(group)
        if current is None or avg_turnover > current[0]:
            candidates[group] = (avg_turnover, code, info)
    return [(code, info) for _, code, info in candidates.values()]


def rotation_rows(etf_data, as_of):
    hs5 = return_pct(etf_data, HS300_CODE, as_of, 5) or 0.0
    hs20 = return_pct(etf_data, HS300_CODE, as_of, 20) or 0.0
    rows = []
    for code, info in group_representatives(etf_data, as_of):
        r1 = day_return_pct(etf_data, code, as_of) or 0.0
        r5 = return_pct(etf_data, code, as_of, 5) or 0.0
        r20 = return_pct(etf_data, code, as_of, 20) or 0.0
        vr = volume_ratio(etf_data, code, as_of, 20) or 1.0
        relative5, relative20 = r5 - hs5, r20 - hs20
        score = 0.55 * clip(relative5 / 5) + 0.30 * clip(relative20 / 10) + 0.15 * clip((vr - 1) / 1.5)
        rows.append({
            "code": code,
            "name": info["name"],
            "sector": info["sector"],
            "group": info.get("group", info["sector"]),
            "return_1d": round(r1, 3),
            "return_5d": round(r5, 3),
            "return_20d": round(r20, 3),
            "relative_5d": round(relative5, 3),
            "relative_20d": round(relative20, 3),
            "volume_ratio_20d": round(vr, 3),
            "rotation_score": round(score, 4),
        })
    return sorted(rows, key=lambda row: row["rotation_score"], reverse=True)


def trading_structure(etf_data, as_of):
    codes = [code for code, info in SECTOR_ETF_MAP.items() if info.get("risk_on") == 1 and info.get("group") not in OVERSEAS_GROUPS]
    current = []
    daily_totals = []
    trading_days = [day for day in get_trading_days(etf_data) if day <= as_of]
    for day in trading_days[-21:]:
        total = 0.0
        for code in codes:
            rows = records_on_or_before(etf_data, code, day)
            if rows and rows[-1].get("date") == day:
                total += float(rows[-1].get("close", 0) or 0) * float(rows[-1].get("volume", 0) or 0)
        daily_totals.append(total)
    for code in codes:
        rows = records_on_or_before(etf_data, code, as_of)
        if len(rows) < 2:
            continue
        row, previous = rows[-1], rows[-2]
        turnover = float(row.get("close", 0) or 0) * float(row.get("volume", 0) or 0)
        ret = (float(row.get("close", 0)) / float(previous.get("close", 0)) - 1) * 100 if previous.get("close") else 0.0
        current.append({
            "code": code,
            "name": SECTOR_ETF_MAP[code]["name"],
            "turnover": turnover,
            "return_1d": ret,
            "close_location": close_location(row),
            "volume_ratio": volume_ratio(etf_data, code, as_of, 20) or 1.0,
        })
    total = sum(row["turnover"] for row in current)
    prior_mean = mean(daily_totals[:-1]) if len(daily_totals) > 1 else 0.0
    top3 = sorted(current, key=lambda row: row["turnover"], reverse=True)[:3]
    up_turnover = sum(row["turnover"] for row in current if row["return_1d"] > 0)
    down_on_volume = [row for row in current if row["return_1d"] < 0 and row["volume_ratio"] > 1.2]
    return {
        "turnover_ratio_20d": round(total / prior_mean, 4) if prior_mean else 1.0,
        "top3_concentration": round(sum(row["turnover"] for row in top3) / total, 4) if total else 0.0,
        "up_turnover_share": round(up_turnover / total, 4) if total else 0.5,
        "median_close_location": round(median([row["close_location"] for row in current]), 4) if current else 0.5,
        "high_volume_decliners": len(down_on_volume),
        "top3": [{"code": row["code"], "name": row["name"], "share": round(row["turnover"] / total, 4) if total else 0.0} for row in top3],
    }


def parse_macro_from_news(external_raw, as_of):
    items = [
        row for row in external_raw.get("items", [])
        if row.get("category") == "macro" and row.get("published_at", "")[:10] <= as_of
    ]
    items.sort(key=lambda row: row.get("published_at", ""), reverse=True)
    metrics = {}
    patterns = {
        "ppi_yoy": r"工业生产者出厂价格同比(?:上涨|增长)([-+]?\d+(?:\.\d+)?)%",
        "cpi_yoy": r"居民消费价格同比(?:上涨|增长)([-+]?\d+(?:\.\d+)?)%",
        "industrial_profit_yoy": r"规模以上工业企业利润(?:增长|同比增长)([-+]?\d+(?:\.\d+)?)%",
    }
    for row in items:
        title = row.get("title", "")
        for key, pattern in patterns.items():
            if key in metrics:
                continue
            found = re.search(pattern, title)
            if found:
                metrics[key] = {
                    "value": float(found.group(1)),
                    "title": title,
                    "date": row.get("published_at", "")[:10],
                    "url": row.get("url"),
                }
    return metrics, items[:3]


def macro_snapshot(macro_raw, external_raw, etf_data, margin_detail, as_of):
    indicators = macro_raw.get("indicators", {}) if isinstance(macro_raw, dict) else {}
    parsed, latest_items = parse_macro_from_news(external_raw, as_of)

    def latest_value(name, fallback=None):
        rows = indicators.get(name, [])
        usable = [row for row in rows if row.get("release_date", "") <= as_of]
        if usable:
            usable.sort(key=lambda row: row.get("release_date", ""))
            return usable[-1]
        return parsed.get(name, fallback)

    pmi = latest_value("manufacturing_pmi")
    cpi = latest_value("cpi_yoy")
    ppi = latest_value("ppi_yoy")
    industrial = latest_value("industrial_value_added_yoy")
    retail = latest_value("retail_sales_yoy")
    profits = latest_value("industrial_profit_yoy")
    m1 = latest_value("m1_yoy")
    m2 = latest_value("m2_yoy")

    cyclical_codes = ["510300", "510500", "512000", "512800", "510150", "516160"]
    defensive_codes = ["510880", "512890", "518880", "511010", "511260"]
    cyclical20 = mean([return_pct(etf_data, code, as_of, 20) or 0.0 for code in cyclical_codes])
    defensive20 = mean([return_pct(etf_data, code, as_of, 20) or 0.0 for code in defensive_codes])
    market_growth_proxy = clip((cyclical20 - defensive20) / 8)

    growth_inputs = []
    if pmi:
        growth_inputs.append(clip((float(pmi.get("value", 50)) - 50) / 3))
    if industrial:
        growth_inputs.append(clip(float(industrial.get("value", 0)) / 8))
    if retail:
        growth_inputs.append(clip(float(retail.get("value", 0)) / 8))
    if profits:
        growth_inputs.append(clip(float(profits.get("value", 0)) / 20))
    fundamental_growth = mean(growth_inputs) if growth_inputs else 0.0
    growth_score = 0.65 * fundamental_growth + 0.35 * market_growth_proxy if growth_inputs else market_growth_proxy

    inflation_inputs = []
    if cpi:
        inflation_inputs.append(clip((float(cpi.get("value", 0)) - 1.0) / 3))
    if ppi:
        inflation_inputs.append(clip(float(ppi.get("value", 0)) / 5))
    inflation_score = mean(inflation_inputs)

    liquidity_inputs = [margin_detail.get("score", 0.0)] if margin_detail.get("available") else []
    if m1 and m2:
        liquidity_inputs.append(clip((float(m1.get("value", 0)) - float(m2.get("value", 0))) / 8))
    liquidity_score = mean(liquidity_inputs)

    # 数据改善但周期ETF仍明显跑输防守资产时，先写明分歧，不能把宏观
    # 数据直接翻译成市场已经进入扩张。
    if growth_inputs and fundamental_growth > 0.20 and market_growth_proxy < -0.20:
        phase = "基本面改善 / 市场未确认"
    elif growth_score > 0.20 and inflation_score > 0.15:
        phase = "扩张 / 再通胀"
    elif growth_score > 0.20:
        phase = "温和修复"
    elif growth_score < -0.20 and inflation_score > 0.20:
        phase = "滞胀压力"
    elif growth_score < -0.20:
        phase = "放缓 / 防守"
    else:
        phase = "数据与市场定价分歧"
    return {
        "phase": phase,
        "fundamental_growth_score": round(fundamental_growth, 4),
        "market_growth_proxy": round(market_growth_proxy, 4),
        "growth_score": round(growth_score, 4),
        "inflation_score": round(inflation_score, 4),
        "liquidity_score": round(liquidity_score, 4),
        "cyclical_20d": round(cyclical20, 3),
        "defensive_20d": round(defensive20, 3),
        "values": {key: value for key, value in {
            "manufacturing_pmi": pmi,
            "cpi_yoy": cpi,
            "ppi_yoy": ppi,
            "industrial_value_added_yoy": industrial,
            "retail_sales_yoy": retail,
            "industrial_profit_yoy": profits,
            "m1_yoy": m1,
            "m2_yoy": m2,
        }.items() if value},
        "latest_items": latest_items,
        "actual_count": len(growth_inputs) + len(inflation_inputs) + int(bool(m1 and m2)),
    }


def fmt_signed(value, suffix=""):
    return f"{value:+.2f}{suffix}"


def target_news_keywords(info):
    """返回逐只ETF新闻匹配词；短词去重，避免改变交易模型关键词。"""
    group = info.get("group", info.get("sector", ""))
    values = [info.get("name", "").replace("ETF", ""), info.get("sector", "")]
    values.extend(info.get("keywords", []))
    values.extend(NEWS_ALIASES_BY_GROUP.get(group, []))
    result = []
    for value in values:
        value = str(value).strip()
        if len(value) >= 2 and value not in result:
            result.append(value)
    return result


def match_target_news_keywords(title, info):
    """标题直接匹配；过滤只有歧义短词的伪相关结果。"""
    lowered = str(title).lower()
    matches = [word for word in target_news_keywords(info) if word.lower() in lowered]
    ambiguous = AMBIGUOUS_NEWS_TERMS_BY_GROUP.get(info.get("group"), set())
    if matches and all(word in ambiguous for word in matches):
        return []
    return matches


def news_direction(title, explicit=None):
    if explicit in {"偏正", "正面", "利好"}:
        return "偏正", 1
    if explicit in {"偏负", "负面", "利空"}:
        return "偏负", -1
    if explicit == "中性":
        return "中性", 0
    positive = sum(word.lower() in title.lower() for word in NEWS_POSITIVE)
    negative = sum(word.lower() in title.lower() for word in NEWS_NEGATIVE)
    if positive > negative:
        return "偏正", 1
    if negative > positive:
        return "偏负", -1
    return "中性", 0


def news_source_tier(row):
    if row.get("source_tier"):
        return row["source_tier"]
    host = urlparse(row.get("url", "")).netloc.lower()
    if any(host.endswith(domain) for domain in OFFICIAL_DOMAINS):
        return "官方原文"
    if row.get("origin") == "newspaper":
        return "四大报叙事"
    return "公开媒体"


def collect_target_news(code, info, external_raw, targeted_raw, newspapers, as_of, lookback_days=14):
    """收集与单只ETF直接匹配的新闻，并显式区分模型输入与报告补充。

    市场级宏观新闻不会自动分配给所有ETF；必须命中板块、代码目标或标题关键词。
    未命中时输出“证据不足”，而不是把零条新闻解释为利空。
    """
    cutoff = date.fromisoformat(as_of) - timedelta(days=lookback_days - 1)
    rows = []

    def valid_day(value):
        try:
            parsed = date.fromisoformat(str(value)[:10])
            return cutoff <= parsed <= date.fromisoformat(as_of)
        except ValueError:
            return False

    def title_match(title):
        return match_target_news_keywords(title, info)

    def append(raw, origin, forced_matches=None):
        title = " ".join(str(raw.get("title", "")).split()).strip()
        published = str(raw.get("published_at", ""))[:10]
        matched = forced_matches or title_match(title)
        if not title or not matched or not valid_day(published):
            return
        direction, direction_value = news_direction(title, raw.get("direction"))
        item = {
            "title": title,
            "source": raw.get("source", "未知来源"),
            "url": raw.get("url") or SOURCE_URLS["newspapers"],
            "published_at": published,
            "direction": direction,
            "direction_value": direction_value,
            "impact": raw.get("impact", "中" if direction_value else "低"),
            "category": raw.get("category", "media"),
            "origin": origin,
            "matched_keywords": matched[:4],
            "source_tier": news_source_tier({**raw, "origin": origin}),
            "used_in_rule": bool(origin == "external" and published < as_of)
                            or bool(origin == "newspaper" and published == as_of),
        }
        rows.append(item)

    for raw in external_raw.get("items", []) if isinstance(external_raw, dict) else []:
        sectors = raw.get("sectors", [])
        matched = title_match(raw.get("title", ""))
        if info.get("sector") in sectors and not matched:
            matched = [info.get("sector")]
        # “宽基/市场整体”不能作为给所有ETF分配新闻的理由。
        if matched:
            append(raw, "external", matched)

    for raw in targeted_raw.get("items", []) if isinstance(targeted_raw, dict) else []:
        target_codes = raw.get("target_codes", [])
        matched = title_match(raw.get("title", ""))
        if code in target_codes and not matched:
            matched = [info.get("sector")]
        if matched:
            append(raw, "targeted_search", matched)

    for day, papers in newspapers.items() if isinstance(newspapers, dict) else []:
        if not valid_day(day):
            continue
        for paper, titles in papers.items():
            for title in titles:
                matched = title_match(title)
                if matched:
                    append({
                        "title": title,
                        "source": paper,
                        "url": SOURCE_URLS["newspapers"],
                        "published_at": day,
                        "category": "media",
                        "impact": "中",
                    }, "newspaper", matched)

    # 同标题优先保留有直接原文、来源等级更高的一条。
    tier_order = {"官方原文": 3, "交易所/监管": 3, "专业媒体": 2, "公开媒体": 1, "四大报叙事": 1}
    deduped = {}
    for row in rows:
        key = re.sub(r"\W+", "", row["title"]).lower()
        current = deduped.get(key)
        candidate_rank = (tier_order.get(row["source_tier"], 1), row["url"] != SOURCE_URLS["newspapers"])
        current_rank = (tier_order.get(current["source_tier"], 1), current["url"] != SOURCE_URLS["newspapers"]) if current else (-1, False)
        if current is None or candidate_rank > current_rank:
            deduped[key] = row
    rows = list(deduped.values())

    impact_weight = {"高": 1.0, "中": 0.70, "低": 0.40}
    tier_weight = {"官方原文": 1.0, "交易所/监管": 1.0, "专业媒体": 0.75, "公开媒体": 0.60, "四大报叙事": 0.55}
    weighted_sum = weight_total = 0.0
    recent_count = 0
    for row in rows:
        age = (date.fromisoformat(as_of) - date.fromisoformat(row["published_at"])).days
        row["age_days"] = age
        row["report_context_only"] = not row["used_in_rule"]
        weight = impact_weight.get(row["impact"], 0.5) * tier_weight.get(row["source_tier"], 0.6) / (1 + age / 5)
        weighted_sum += row["direction_value"] * weight
        weight_total += weight
        recent_count += age <= 2
    score = weighted_sum / weight_total if weight_total else 0.0
    positive = sum(row["direction_value"] > 0 for row in rows)
    negative = sum(row["direction_value"] < 0 for row in rows)
    neutral = len(rows) - positive - negative
    if not rows:
        status = "无直接新闻"
        attention = "数据不足"
        conclusion = f"近{lookback_days}日未检索到与{info.get('sector')}直接匹配的有效新闻；新闻证据不足，不等于利空。"
    else:
        status = "偏正" if score >= 0.15 else "偏负" if score <= -0.15 else "中性"
        prior_count = len(rows) - recent_count
        recent_rate = recent_count / 3
        prior_rate = prior_count / max(lookback_days - 3, 1)
        if recent_count and not prior_count:
            attention = "新出现"
        elif recent_rate > prior_rate * 1.5:
            attention = "升温"
        elif prior_count and recent_rate < prior_rate * 0.6:
            attention = "降温"
        else:
            attention = "平稳"
        conclusion = (f"近{lookback_days}日直接相关新闻{len(rows)}条（偏正{positive}/偏负{negative}/中性{neutral}），"
                      f"新闻流{status}；近3日{recent_count}条，关注度{attention}。")

    rows.sort(key=lambda row: (
        row["published_at"],
        {"高": 3, "中": 2, "低": 1}.get(row["impact"], 0),
        abs(row["direction_value"]),
    ), reverse=True)
    return {
        "as_of_date": as_of,
        "window_start": cutoff.isoformat(),
        "lookback_days": lookback_days,
        "status": status,
        "score": round(score, 4),
        "direct_count": len(rows),
        "positive_count": positive,
        "negative_count": negative,
        "neutral_count": neutral,
        "recent_3d_count": recent_count,
        "attention": attention,
        "latest_date": rows[0]["published_at"] if rows else None,
        "conclusion": conclusion,
        "top_items": rows[:4],
        "limitation": "新闻流衡量公开信息方向与关注度，不等于资金流；同日搜索补充只作报告语境，不回填规则信号。",
    }


def target_fund_flow(code, info, etf_data, share_map, margin, as_of):
    """逐只ETF的真实申赎、相对强弱和量价资金代理，三者分栏返回。"""
    price_rows = records_on_or_before(etf_data, code, as_of)
    price_as_of = price_rows[-1].get("date") if price_rows else None
    share = share_map.get(code)
    r1 = return_pct(etf_data, code, as_of, 1) or 0.0
    r5 = return_pct(etf_data, code, as_of, 5) or 0.0
    r20 = return_pct(etf_data, code, as_of, 20) or 0.0
    hs5 = return_pct(etf_data, HS300_CODE, as_of, 5) or 0.0
    hs20 = return_pct(etf_data, HS300_CODE, as_of, 20) or 0.0
    relative5, relative20 = r5 - hs5, r20 - hs20
    vr = volume_ratio(etf_data, code, as_of, 20) or 1.0
    behavior = compute_behavior_signals(etf_data, code, as_of)
    if share:
        pct = float(share["share_change_pct"])
        amount = float(share["estimated_flow_yi"])
        share_status = "净申购" if pct >= 1 else "净赎回" if pct <= -1 else "基本稳定"
        share_text = (f"{share['previous_date']}→{share['current_date']}份额{pct:+.2f}%，"
                      f"估算资金{amount:+.2f}亿元")
    else:
        pct = amount = None
        share_status = "数据不足"
        share_text = "缺少两个不同日期的交易所份额快照，不能计算真实申赎。"

    if share and pct <= -1 and relative5 > 0:
        conclusion = "价格相对走强但ETF份额净赎回，量价启动尚未得到真实申赎确认。"
    elif share and pct <= -1 and relative5 <= 0:
        conclusion = "ETF份额净赎回且5日相对收益为负，资金与价格同时偏弱。"
    elif share and pct >= 1 and relative5 > 0:
        conclusion = "ETF份额净申购且5日跑赢基准，真实资金与价格形成正向共振。"
    elif share and pct >= 1 and relative5 <= 0:
        conclusion = "ETF份额净申购但价格尚未跑赢基准，属于资金先行、价格待确认。"
    elif not share:
        conclusion = "真实申赎数据不足，只能观察价格成交代理，不能声称资金净流入。"
    else:
        conclusion = "ETF份额变化不大，当前方向主要由价格相对强弱决定。"

    score = (
        0.55 * clip((pct or 0) / 5)
        + 0.25 * clip(relative5 / 5)
        + 0.20 * float(behavior.get("flow_proxy", 0))
    )
    return {
        "price_as_of": price_as_of,
        "status": share_status,
        "score": round(score, 4),
        "conclusion": conclusion,
        "share_available": bool(share),
        "share_change_pct": round(pct, 4) if pct is not None else None,
        "estimated_flow_yi": round(amount, 4) if amount is not None else None,
        "share_period": f"{share['previous_date']}→{share['current_date']}" if share else None,
        "share_evidence": share_text,
        "return_1d": round(r1, 3),
        "return_5d": round(r5, 3),
        "return_20d": round(r20, 3),
        "relative_5d": round(relative5, 3),
        "relative_20d": round(relative20, 3),
        "volume_ratio_20d": round(vr, 3),
        "price_volume_proxy": round(float(behavior.get("flow_proxy", 0)), 4),
        "early_entry": round(float(behavior.get("early_entry", 0)), 4),
        "withdrawal_risk": round(float(behavior.get("withdrawal_risk", 0)), 4),
        "market_leverage_context": (f"全市场融资净买入{float(margin.get('net_buy_yi', 0)):+.1f}亿元（{margin.get('date', '缺失')}）；"
                                    "该数据不能归因到单只ETF。"),
        "limitation": "申赎金额=份额变化×期末收盘价，为估算值；融资融券为全市场背景，不是该ETF专属资金。",
    }


def cross_readthrough(fund, news):
    if news["direct_count"] == 0:
        return "缺少直接新闻证据，当前判断以真实申赎和价格结构为主。"
    if news["score"] >= 0.15 and fund["status"] == "净赎回":
        return "新闻流偏正但真实份额净赎回，属于叙事—资金背离；不把利好标题直接写成买点。"
    if news["score"] >= 0.15 and fund["score"] >= 0.15:
        return "新闻流与资金/价格方向同向，但仍需下一交易日继续确认，不能据一次共振追涨。"
    if news["score"] <= -0.15 and fund["score"] < 0:
        return "新闻流与资金方向同时偏弱，回避新增的证据较完整。"
    if news["score"] <= -0.15 and fund["score"] >= 0:
        return "新闻偏负但资金未同步转弱，暂按分歧处理，不直接做空。"
    return "新闻方向中性或与资金不一致，交易判断以真实申赎、相对强度和成交确认为先。"


def select_avoid_etfs(latest, recommendation_codes, etf_data, share_map, margin,
                      external_raw, targeted_raw, newspapers, as_of, limit=3):
    """选择回避新增名单；结果是风险提示，不是空头组合。"""
    ranked = []
    for row in latest.get("rankings", []):
        code = row.get("code")
        info = SECTOR_ETF_MAP.get(code, {})
        if not info or code in recommendation_codes or info.get("risk_on") != 1:
            continue
        fund = target_fund_flow(code, info, etf_data, share_map, margin, as_of)
        news = collect_target_news(code, info, external_raw, targeted_raw, newspapers, as_of)
        rule_score = float(row.get("score", 0))
        withdrawal = float(row.get("withdrawal_risk", 0))
        redemption = clip(-(fund["share_change_pct"] or 0) / 5, 0, 1) if fund["share_available"] else 0.0
        avoid_score = 100 * (
            0.40 * redemption
            + 0.25 * clip(-rule_score / 0.5, 0, 1)
            + 0.15 * clip(-fund["relative_5d"] / 5, 0, 1)
            + 0.10 * clip(-fund["relative_20d"] / 10, 0, 1)
            + 0.10 * clip(withdrawal / 0.35, 0, 1)
        )
        reasons = []
        if fund["share_available"] and fund["share_change_pct"] <= -5:
            reasons.append(f"份额{fund['share_change_pct']:+.2f}%（估算{fund['estimated_flow_yi']:+.2f}亿元）")
        if fund["relative_5d"] <= -1:
            reasons.append(f"5日跑输沪深300 {abs(fund['relative_5d']):.2f}个百分点")
        if fund["relative_20d"] <= -5:
            reasons.append(f"20日跑输沪深300 {abs(fund['relative_20d']):.2f}个百分点")
        if rule_score <= -0.20:
            reasons.append(f"规则评分{rule_score:+.2f}")
        if withdrawal >= 0.15:
            reasons.append(f"撤退风险{withdrawal:.2f}")
        if news["score"] >= 0.15 and fund["relative_5d"] < 0:
            reasons.append("新闻偏正但价格未确认")
        ranked.append({
            "code": code,
            "name": row.get("name", info.get("name")),
            "sector": row.get("sector", info.get("sector")),
            "group": info.get("group", info.get("sector")),
            "role": "回避ETF",
            "action": "回避新增" if avoid_score >= 40 else "谨慎观察，不追涨",
            "alert_level": "高" if avoid_score >= 40 else "中",
            "avoid_score": round(avoid_score, 1),
            "rule_score": rule_score,
            "reason": "；".join(reasons[:4]) or "多项信号缺少确认，暂不新增",
            "reasons": reasons,
            "fund_flow": fund,
            "news_flow": news,
            "cross_read": cross_readthrough(fund, news),
            "reconsider": "份额止跌转增、5日相对收益转正且规则评分回到0以上后，再移出回避名单。",
            "position_note": "不知道用户是否持有；这里只限制新增，不自动生成卖出或做空指令。",
        })
    ranked.sort(key=lambda row: row["avoid_score"], reverse=True)
    selected, used_groups = [], set()
    for row in ranked:
        if row["avoid_score"] < 25 or row["group"] in used_groups:
            continue
        selected.append(row)
        used_groups.add(row["group"])
        if len(selected) == limit:
            break
    return selected


def build_diagnostics():
    etf_data = load_json(PATHS["prices"], {})
    model_data = load_json(PATHS["model"], {})
    econ_data = load_json(PATHS["econometric"], {})
    newspapers = load_json(PATHS["newspapers"], {})
    margin_rows = load_json(PATHS["margin"], [])
    shares_raw = load_json(PATHS["shares"], {})
    external_raw = load_json(PATHS["external"], {})
    targeted_raw = load_json(PATHS["targeted_news"], {})
    macro_raw = load_json(PATHS["macro"], {})
    if not etf_data:
        raise ValueError("缺少 ETF 行情，无法生成八模块诊断")

    trading_days = get_trading_days(etf_data)
    market_date = trading_days[-1]
    latest = model_data.get("latest_decision", {})
    decision_date = latest.get("date") or market_date
    state = latest.get("market_state") or compute_market_state(etf_data, market_date)
    news_for_day = newspapers.get(decision_date, {})
    sentiment = analyze_newspaper_sentiment(news_for_day)
    margin = latest_margin_detail(margin_rows if isinstance(margin_rows, list) else list(margin_rows.values()), market_date)
    shares = share_flow_rows(etf_data, shares_raw, market_date)
    rotation = rotation_rows(etf_data, market_date)
    structure = trading_structure(etf_data, market_date)
    macro = macro_snapshot(macro_raw, external_raw, etf_data, margin, market_date)

    modules = []

    # 0. 市场情绪：媒体叙事只占20%，不再冒充机构资金。
    breadth_component = clip((float(state.get("breadth", 0.5)) - 0.5) * 2)
    momentum_component = clip(float(state.get("momentum_5d", 0)) / 3)
    sentiment_score = 100 * (
        0.35 * float(margin.get("score", 0))
        + 0.35 * breadth_component
        + 0.20 * float(sentiment.get("score", 0))
        + 0.10 * momentum_component
    )
    directional = int(sentiment.get("bullish_count", 0)) + int(sentiment.get("bearish_count", 0))
    total_titles = int(sentiment.get("total_titles", 0))
    if sentiment_score >= 15:
        sentiment_conclusion = "情绪略偏暖，但尚未形成一致性亢奋。"
    elif sentiment_score <= -15:
        sentiment_conclusion = "情绪降温，杠杆与市场宽度未给出积极共振。"
    else:
        sentiment_conclusion = "情绪中性，媒体、杠杆和价格宽度没有形成单边共识。"
    modules.append(module(
        "market_sentiment", 0, "市场情绪", sentiment_score,
        "中" if margin.get("available") and total_titles >= 8 else "低",
        sentiment_conclusion,
        [
            evidence("上涨宽度", f"{float(state.get('breadth', 0)):.0%}", "ETF价格横截面", market_date),
            evidence("融资情绪", f"{float(margin.get('score', 0)):+.2f}；净买入{float(margin.get('net_buy_yi', 0)):+.1f}亿元", "融资融券", margin.get("date", "缺失"), url=SOURCE_URLS["margin"]),
            evidence("四大报方向", f"{directional}/{total_titles}条有明确方向，净分{float(sentiment.get('score', 0)):+.2f}", "媒体叙事代理", decision_date, kind="叙事代理", url=SOURCE_URLS["newspapers"]),
        ],
        "情绪只支持观察仓，不足以单独触发买入；媒体标题权重被限制，避免少数关键词把结论推到极端。",
        "观察融资余额是否连续5日上升，以及上涨宽度能否稳定在60%以上。",
        "四大报反映公开叙事，不等于机构真实仓位。",
    ))

    # 1. 资金流向：真实份额变化 + 杠杆资金 + 价格成交代理分层。
    real_net = sum(row["estimated_flow_yi"] for row in shares)
    real_positive = sum(row["estimated_flow_yi"] > 0 for row in shares)
    behavior_rows = []
    for code, info in SECTOR_ETF_MAP.items():
        if info.get("risk_on") != 1:
            continue
        signal = compute_behavior_signals(etf_data, code, market_date)
        behavior_rows.append(signal.get("flow_proxy", 0.0))
    proxy_positive = sum(value > 0.15 for value in behavior_rows) / len(behavior_rows) if behavior_rows else 0.5
    share_component = clip(real_net / 150) if shares else 0.0
    flow_score = 100 * (0.55 * share_component + 0.25 * float(margin.get("score", 0)) + 0.20 * (proxy_positive * 2 - 1))
    flow_conclusion = (
        f"真实ETF份额资金偏流出：覆盖{len(shares)}只，最近区间合计估算净赎回{abs(real_net):.1f}亿元。"
        if real_net < 0 else
        f"真实ETF份额资金偏流入：覆盖{len(shares)}只，最近区间合计估算净申购{real_net:.1f}亿元。"
    )
    top_in = shares[0] if shares else None
    top_out = shares[-1] if shares else None
    modules.append(module(
        "capital_flow", 1, "资金流向", flow_score, "中" if len(shares) >= 15 else "低",
        flow_conclusion,
        [
            evidence("ETF份额资金", f"{real_net:+.1f}亿元；流入{real_positive}/{len(shares)}只", "交易所ETF份额×收盘价估算", shares[0]["current_date"] if shares else "缺失", url=SOURCE_URLS["sse_shares"]),
            evidence("最大流入", f"{top_in['name']} {top_in['estimated_flow_yi']:+.1f}亿元" if top_in else "数据不足", "真实份额变化", top_in["current_date"] if top_in else "缺失"),
            evidence("最大流出", f"{top_out['name']} {top_out['estimated_flow_yi']:+.1f}亿元" if top_out else "数据不足", "真实份额变化", top_out["current_date"] if top_out else "缺失"),
            evidence("价格成交代理", f"{proxy_positive:.0%}风险ETF出现正向资金冲击", "OHLCV代理", market_date, kind="代理指标"),
        ],
        "真实份额流出与局部价格启动并存，说明更像存量资金短线轮动，而不是全面增量资金入场。",
        "等待权益ETF净赎回收窄，且正向成交冲击覆盖率升至50%以上。",
        "估算金额=份额变化×同期收盘价；可识别申赎方向，不能识别投资者身份。",
    ))

    # 2. ETF申赎：单列真实份额，不让成交量代理混入。
    share_breadth = real_positive / len(shares) if shares else 0.5
    share_score = 100 * (0.60 * clip(real_net / 150) + 0.40 * (share_breadth * 2 - 1))
    interval = f"{shares[0]['previous_date']}→{shares[0]['current_date']}" if shares else "无连续快照"
    selected_flows = {row["code"]: row for row in shares}
    selected = latest.get("etf_selection", [])
    selected_text = []
    for pick in selected:
        row = selected_flows.get(pick.get("code"))
        if row:
            selected_text.append(f"{pick.get('name')} {row['share_change_pct']:+.2f}%（{row['estimated_flow_yi']:+.2f}亿元）")
    share_conclusion = (
        f"申赎广度偏弱，仅{real_positive}/{len(shares)}只份额增加；{interval}。"
        if shares else "缺少两期连续份额快照，不能判断真实申赎。"
    )
    modules.append(module(
        "etf_creation_redemption", 2, "ETF申赎资金", share_score,
        "中" if len(shares) >= 15 and max(row["interval_days"] for row in shares) <= 10 else "低",
        share_conclusion,
        [
            evidence("申赎覆盖", f"{len(shares)}/{len(SECTOR_ETF_MAP)}只；正流入{share_breadth:.0%}", "上交所/深交所份额", shares[0]["current_date"] if shares else "缺失", url=SOURCE_URLS["sse_shares"]),
            evidence("当前候选", "；".join(selected_text) if selected_text else "候选暂无两期真实份额", "真实份额变化", shares[0]["current_date"] if shares else "缺失"),
        ],
        "候选ETF若价格走强但份额继续下降，应视为资金冲突，先等待而非追涨。",
        "优先看候选ETF份额是否止跌转增；深市ETF只有单期快照时不得写成净申购。",
        "当前历史快照以周度为主，报告展示实际快照区间，不伪装成单日流量。",
    ))

    # 3. 板块轮动。
    leaders = rotation[:3]
    laggards = rotation[-3:]
    positive5 = sum(row["relative_5d"] > 0 for row in rotation)
    persistent = [row for row in rotation if row["relative_5d"] > 0 and row["relative_20d"] > 0]
    rotation_score = 100 * mean([row["rotation_score"] for row in leaders]) if leaders else 0.0
    leader_names = "、".join(row["name"] for row in leaders)
    laggard_names = "、".join(row["name"] for row in laggards)
    rotation_conclusion = f"轮动领先为{leader_names}；{positive5}/{len(rotation)}个代表板块近5日跑赢沪深300。"
    modules.append(module(
        "sector_rotation", 3, "板块轮动", rotation_score, "中",
        rotation_conclusion,
        [
            evidence("持续领先", f"{len(persistent)}个板块同时跑赢5日和20日基准", "分组代表ETF相对强度", market_date),
            evidence("领先三项", "；".join(f"{row['name']} 5日{row['return_5d']:+.1f}%/相对{row['relative_5d']:+.1f}%" for row in leaders), "价格+成交", market_date),
            evidence("落后三项", laggard_names, "价格相对强度", market_date),
        ],
        "优先跟踪同时具备5日与20日相对强度的板块；只有单日冲高的不列为稳定主线。",
        "领先板块需继续跑赢沪深300且量比不低于1；跌出前五则视为轮动失效。",
        "同类ETF只保留20日成交更活跃的代表，避免重复产品放大同一板块。",
    ))

    # 4. 宏观周期。
    macro_score = 100 * (0.50 * macro["growth_score"] + 0.20 * macro["inflation_score"] + 0.30 * macro["liquidity_score"])
    macro_values = macro["values"]
    macro_evidence = []
    labels = {
        "manufacturing_pmi": "制造业PMI",
        "cpi_yoy": "CPI同比",
        "ppi_yoy": "PPI同比",
        "industrial_value_added_yoy": "工业增加值同比",
        "retail_sales_yoy": "社零同比",
        "industrial_profit_yoy": "工业利润同比",
        "m1_yoy": "M1同比",
        "m2_yoy": "M2同比",
    }
    for key in labels:
        row = macro_values.get(key)
        if not row:
            continue
        suffix = "" if key == "manufacturing_pmi" else "%"
        macro_evidence.append(evidence(labels[key], f"{float(row.get('value', 0)):.1f}{suffix}", "宏观数据", row.get("release_date", row.get("date", "")), url=row.get("url") or SOURCE_URLS["nbs"]))
        if len(macro_evidence) == 3:
            break
    macro_evidence.append(evidence("市场定价", f"周期资产20日{macro['cyclical_20d']:+.1f}% vs 防守资产{macro['defensive_20d']:+.1f}%", "ETF价格代理", market_date, kind="市场代理"))
    macro_conclusion = f"宏观阶段判断为“{macro['phase']}”；基本面信号与市场资金必须分开验证。"
    modules.append(module(
        "macro_cycle", 4, "宏观周期", macro_score,
        "中" if macro["actual_count"] >= 3 else "低",
        macro_conclusion,
        macro_evidence,
        "宏观数据偏强不等于ETF立即上涨；若权益份额仍流出，市场可能先交易防守或等待政策兑现。",
        "跟踪PMI、工业/消费、M1-M2剪刀差，并要求周期ETF相对防守资产转强后再确认。",
        "缺少可按发布日期回放的指标时，只用于当期判断，不回填历史模型，避免宏观数据偷看。",
    ))

    # 5. 风险偏好。
    risk_on_codes = [code for code, info in SECTOR_ETF_MAP.items() if info.get("risk_on") == 1 and info.get("group") not in OVERSEAS_GROUPS]
    defensive_codes = [code for code, info in SECTOR_ETF_MAP.items() if info.get("risk_on") == -1]
    risk5 = mean([return_pct(etf_data, code, market_date, 5) or 0.0 for code in risk_on_codes])
    defense5 = mean([return_pct(etf_data, code, market_date, 5) or 0.0 for code in defensive_codes])
    relative_risk = risk5 - defense5
    equity_share_flow = sum(row["estimated_flow_yi"] for row in shares if row["group"] not in {"gold", "bond", "cash"})
    defense_share_flow = sum(row["estimated_flow_yi"] for row in shares if row["group"] in {"gold", "bond"})
    risk_score = 100 * (
        0.30 * breadth_component
        + 0.20 * clip(float(state.get("momentum_20d", 0)) / 5)
        + 0.15 * clip(relative_risk / 5)
        + 0.20 * clip((equity_share_flow - defense_share_flow) / 150)
        + 0.15 * float(margin.get("score", 0))
    )
    risk_conclusion = (
        "短线宽度尚可，但中期动量、权益申赎与防守资产流入显示风险偏好仍不稳。"
        if float(state.get("breadth", 0.5)) >= 0.55 and risk_score < 15 else
        "风险资产与资金方向基本一致。"
    )
    modules.append(module(
        "risk_appetite", 5, "风险偏好", risk_score, "中",
        risk_conclusion,
        [
            evidence("风险状态", f"{state.get('name', 'unknown')}；预算{float(state.get('risk_budget', 0)):.0%}", "市场状态模型", market_date, kind="规则判断"),
            evidence("中期趋势", f"沪深300 20日{float(state.get('momentum_20d', 0)):+.2f}%；波动{float(state.get('volatility_20d', 0)):.1f}%", "价格", market_date),
            evidence("攻守资金", f"权益ETF{equity_share_flow:+.1f}亿元 vs 黄金/债券{defense_share_flow:+.1f}亿元", "真实份额变化", shares[0]["current_date"] if shares else "缺失"),
        ],
        "宽度改善但资金仍偏防守时，不应把单日普涨解释成全面risk-on。",
        "确认条件：20日动量转正、权益ETF份额回流、风险资产5日跑赢黄金与债券。",
        "风险预算是仓位上限，不是收益概率。",
    ))

    # 6. 机构资金：只报告可审计代理，并明确北向日度缺口。
    institutional_rows = [row for row in shares if row["group"] in INSTITUTION_PROXY_GROUPS]
    institutional_net = sum(row["estimated_flow_yi"] for row in institutional_rows)
    core_equity = sum(row["estimated_flow_yi"] for row in institutional_rows if row["group"] in {"large_cap", "mid_cap", "small_cap"})
    safe_assets = sum(row["estimated_flow_yi"] for row in institutional_rows if row["group"] in {"bond", "gold"})
    institutional_score = 100 * clip((core_equity - safe_assets) / 150)
    institution_conclusion = (
        f"机构型资金代理偏防守：核心宽基估算{core_equity:+.1f}亿元，黄金/债券{safe_assets:+.1f}亿元。"
        if core_equity < safe_assets else
        f"机构型资金代理偏进攻：核心宽基估算{core_equity:+.1f}亿元。"
    )
    modules.append(module(
        "institutional_flow", 6, "机构资金", institutional_score, "低",
        institution_conclusion,
        [
            evidence("核心宽基份额资金", f"{core_equity:+.1f}亿元", "宽基ETF申赎代理", institutional_rows[0]["current_date"] if institutional_rows else "缺失", kind="机构型代理", url=SOURCE_URLS["sse_shares"]),
            evidence("黄金/债券份额资金", f"{safe_assets:+.1f}亿元", "防守ETF申赎代理", institutional_rows[0]["current_date"] if institutional_rows else "缺失", kind="机构型代理"),
            evidence("北向日度净流入", "不使用：原日度持仓口径已调整", "港交所披露规则", "2024-08-19起", kind="数据缺口", url=SOURCE_URLS["northbound_policy"]),
            evidence("四大报", f"只作叙事参考，不计入机构资金金额", "媒体标题", decision_date, kind="叙事代理"),
        ],
        "当前只能判断机构型产品的申赎方向，不能把ETF持有人直接识别为机构。",
        "后续若接入基金季报、保险/公募持仓或季度北向持股，再单列中期机构配置变化。",
        "ETF申赎含个人、做市和套利资金，因此本模块置信度固定不高于“低”。",
    ))

    # 7. 成交结构。
    structure_score = 100 * (
        0.40 * clip((structure["up_turnover_share"] - 0.5) * 2)
        + 0.25 * clip((structure["turnover_ratio_20d"] - 1) / 0.8)
        + 0.20 * clip((structure["median_close_location"] - 0.5) * 2)
        - 0.15 * clip(structure["high_volume_decliners"] / 5)
        - 0.15 * clip((structure["top3_concentration"] - 0.40) / 0.30, 0, 1)
    )
    if structure["turnover_ratio_20d"] < 0.75 and structure["up_turnover_share"] > 0.55:
        structure_conclusion = "缩量上涨且成交集中，反弹质量有限，尚不能确认增量买盘。"
    elif structure["turnover_ratio_20d"] > 1.1 and structure["up_turnover_share"] > 0.55:
        structure_conclusion = "成交放大且上涨成交占优，短线结构偏健康。"
    elif structure["turnover_ratio_20d"] > 1.1 and structure["up_turnover_share"] < 0.45:
        structure_conclusion = "成交放大但下跌成交占优，属于撤退结构。"
    elif structure["top3_concentration"] > 0.55:
        structure_conclusion = "成交集中在少数ETF，行情广度可能被头部品种放大。"
    else:
        structure_conclusion = "成交结构中性，尚无全面放量或集中撤退。"
    modules.append(module(
        "trading_structure", 7, "成交结构", structure_score, "中",
        structure_conclusion,
        [
            evidence("成交活跃度", f"为20日均值的{structure['turnover_ratio_20d']:.2f}倍", "价格×成交量代理", market_date, kind="相对指标"),
            evidence("上涨成交占比", f"{structure['up_turnover_share']:.0%}", "风险ETF成交结构", market_date),
            evidence("头部集中度", f"前三只占{structure['top3_concentration']:.0%}", "成交结构", market_date),
            evidence("放量下跌ETF", f"{structure['high_volume_decliners']}只", "量价异常", market_date),
        ],
        "只有上涨成交占优且成交活跃度同步提升，才把放量解释为增量买盘。",
        "警惕上涨成交占比跌破45%、前三集中度超过55%或放量下跌ETF明显增加。",
        "行情源只有成交量，金额采用收盘价×成交量做相对代理，不展示伪精确绝对金额。",
    ))

    # 组合结论与模型护栏。
    weights = {
        "market_sentiment": 0.10,
        "capital_flow": 0.15,
        "etf_creation_redemption": 0.20,
        "sector_rotation": 0.15,
        "macro_cycle": 0.10,
        "risk_appetite": 0.15,
        "institutional_flow": 0.10,
        "trading_structure": 0.05,
    }
    overall_score = sum(item["score"] * weights[item["id"]] for item in modules)
    overall_status, overall_tone = score_status(overall_score)
    rule_summary = model_data.get("summary", {})
    logit = econ_data.get("logit_model", {})
    production_eligible = bool(logit.get("production_eligible", False))
    rule_alpha = float(rule_summary.get("alpha", 0) or 0)
    guardrail_pass = production_eligible and rule_alpha > 0
    model_status = "可执行" if guardrail_pass else "研究观察"
    model_reason = (
        "规则模型相对基准为正且计量模型通过样本外护栏。"
        if guardrail_pass else
        f"规则模型相对沪深300 Alpha {rule_alpha:+.1f}%，计量模型{'已' if production_eligible else '未'}通过样本外护栏。"
    )

    share_map = {row["code"]: row for row in shares}
    candidate_rows = []
    for pick in latest.get("etf_selection", [])[:3]:
        code = pick.get("code")
        info = SECTOR_ETF_MAP.get(code, {})
        share = share_map.get(code)
        behavior = compute_behavior_signals(etf_data, code, market_date)
        fund = target_fund_flow(code, info, etf_data, share_map, margin, market_date)
        news = collect_target_news(code, info, external_raw, targeted_raw, newspapers, decision_date)
        conflicts = []
        confirms = []
        if behavior.get("early_entry", 0) >= 0.45:
            confirms.append("价格与成交出现启动")
        if fund["relative_5d"] > 1 and fund["relative_20d"] > 0:
            confirms.append(f"5日跑赢沪深300 {fund['relative_5d']:.2f}个百分点")
        if share and share["share_change_pct"] > 0.5:
            confirms.append(f"份额增加{share['share_change_pct']:.2f}%")
        if share and share["share_change_pct"] < -1.0:
            conflicts.append(f"份额下降{abs(share['share_change_pct']):.2f}%（估算{share['estimated_flow_yi']:+.2f}亿元）")
        if behavior.get("withdrawal_risk", 0) >= 0.35:
            conflicts.append(f"撤退风险{behavior['withdrawal_risk']:.2f}")
        if not guardrail_pass or conflicts:
            verdict = "推荐观察｜等待确认"
        elif len(confirms) >= 2:
            verdict = "可小仓跟踪"
        else:
            verdict = "推荐观察"
        action_line = (
            "列入推荐关注，但样本外护栏未通过，当前不新增仓位。"
            if not guardrail_pass else
            "列入推荐关注；只在确认条件同时满足时按诊断仓位执行。"
        )
        candidate_rows.append({
            "code": code,
            "name": pick.get("name"),
            "sector": pick.get("sector"),
            "group": info.get("group", pick.get("sector")),
            "role": "推荐关注ETF",
            "alert_level": "待确认" if (not guardrail_pass or conflicts) else "跟踪",
            "action": action_line,
            "model_weight": float(pick.get("weight", 0)),
            "model_score": float(pick.get("total_score", 0)),
            "verdict": verdict,
            "confirmations": confirms,
            "conflicts": conflicts,
            "reason": "；".join(confirms + conflicts) or "缺少足够的资金与成交确认",
            "why_selected": (f"规则评分{float(pick.get('total_score', 0)):+.2f}；"
                             f"5日相对沪深300 {fund['relative_5d']:+.2f}个百分点；"
                             f"启动强度{fund['early_entry']:.2f}。"),
            "fund_flow": fund,
            "news_flow": news,
            "cross_read": cross_readthrough(fund, news),
            "confirm_next": "份额止跌转增、5日相对强度保持为正且撤退风险低于0.35",
            "invalidate": "跌出轮动前五、放量收低或撤退风险升至0.35以上",
        })

    recommendation_codes = {row["code"] for row in candidate_rows}
    avoid_rows = select_avoid_etfs(
        latest, recommendation_codes, etf_data, share_map, margin,
        external_raw, targeted_raw, newspapers, decision_date,
    )

    key_positive = [item["conclusion"] for item in modules if item["score"] >= 15][:2]
    key_risks = [item["conclusion"] for item in sorted(modules, key=lambda item: item["score"])[:3]]
    recommendation_names = "、".join(row["name"] for row in candidate_rows) or "暂无"
    avoid_names = "、".join(row["name"] for row in avoid_rows) or "暂无"
    if overall_score < 15 or not guardrail_pass:
        action = (f"推荐关注：{recommendation_names}，均先等待确认；回避新增：{avoid_names}。"
                  "不把单一价格启动或利好标题直接写成买点。")
    else:
        action = (f"推荐关注：{recommendation_names}；回避新增：{avoid_names}。"
                  "只跟踪资金、轮动和成交同时确认的候选，任何单一模块转弱都不自动加仓。")
    conclusion = (
        f"市场{overall_status}：短线存在局部轮动，但真实ETF份额和机构型代理未确认全面增量资金。"
    )

    data_quality = [
        {"source": "ETF行情", "latest": market_date, "status": "可用", "use": "价格、成交、轮动与风险状态"},
        {"source": "ETF份额", "latest": shares[0]["current_date"] if shares else None, "status": "部分覆盖", "use": f"{len(shares)}只有连续快照；深市单期不计算流量"},
        {"source": "融资融券", "latest": margin.get("date"), "status": "可用" if margin.get("available") else "缺失", "use": "杠杆资金与大众风险偏好"},
        {"source": "四大报", "latest": decision_date if total_titles else None, "status": "叙事代理", "use": "只分析公开叙事，不代表机构仓位"},
        {"source": "定向新闻检索", "latest": targeted_raw.get("updated_at"), "status": "补充证据" if targeted_raw.get("items") else "无缓存", "use": "只进入逐只ETF新闻深挖；同日补充不回填规则信号"},
        {"source": "宏观指标", "latest": max((row.get("release_date", row.get("date", "")) for row in macro_values.values()), default=None), "status": "可用" if macro["actual_count"] else "代理为主", "use": "当前周期判断；不回填历史"},
        {"source": "北向资金", "latest": None, "status": "不使用旧口径", "use": "官方调整后不伪造日度净流入"},
    ]

    payload = {
        "schema_version": "5.1",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "as_of_date": decision_date,
        "market_data_date": market_date,
        "overall": {
            "score": round(overall_score, 1),
            "status": overall_status,
            "tone": overall_tone,
            "confidence": "中",
            "conclusion": conclusion,
            "action": action,
            "positives": key_positive or ["暂无形成多模块共振的积极信号。"],
            "risks": key_risks,
            "model_status": model_status,
            "model_reason": model_reason,
            "original_model_position": round(sum(float(row.get("weight", 0)) for row in latest.get("etf_selection", [])), 4),
            "execution_position": None if not guardrail_pass else round(sum(float(row.get("weight", 0)) for row in latest.get("etf_selection", [])), 4),
            "upgrade_rule": "新增因子先进入Shadow记录；只有滚动样本外Alpha、Brier、回撤和交易次数同时过线，才允许进入交易评分。",
        },
        "final_decision": {
            "action": "按诊断后仓位执行" if guardrail_pass else "等待确认",
            "execution_allowed": guardrail_pass,
            "position": round(sum(float(row.get("weight", 0)) for row in latest.get("etf_selection", [])), 4) if guardrail_pass else 0.0,
            "reason": action,
            "rule_output_role": "候选生成器；model_results.json中的buy不等于最终执行指令",
            "canonical_source": "data/market_diagnostics.json",
        },
        "modules": modules,
        "recommendations": candidate_rows,
        "avoid_etfs": avoid_rows,
        "daily_etf_alerts": {
            "date": decision_date,
            "recommendation_count": len(candidate_rows),
            "avoid_count": len(avoid_rows),
            "recommendation_codes": [row["code"] for row in candidate_rows],
            "avoid_codes": [row["code"] for row in avoid_rows],
            "display_title": f"今日推荐关注 {len(candidate_rows)} 只｜今日回避预警 {len(avoid_rows)} 只",
            "refresh_policy": "每日流水线按最新行情、真实ETF份额、相对强弱、成交结构和直接新闻重新计算；不沿用固定名单。",
        },
        "etf_deep_dives": candidate_rows + avoid_rows,
        "etf_selection_rules": {
            "recommendation_limit": 3,
            "recommendation_source": "latest_decision.etf_selection；只作研究名单，最终执行受样本外护栏控制",
            "avoid_limit": 3,
            "avoid_min_score": 25,
            "avoid_distinct_group": True,
            "avoid_weights": {
                "real_share_redemption": 0.40,
                "weak_rule_score": 0.25,
                "weak_relative_5d": 0.15,
                "weak_relative_20d": 0.10,
                "withdrawal_risk": 0.10,
            },
        },
        # 兼容旧版看板与下游读取器；新代码应读取recommendations。
        "candidates": candidate_rows,
        "rotation_table": rotation,
        "share_flow_table": shares,
        "trading_structure": structure,
        "macro_snapshot": macro,
        "data_quality": data_quality,
        "hard_rules": [
            "真实申赎、价格成交代理和媒体叙事必须分栏，不得互相替代。",
            "缺失数据写“数据不足”，不得按0解释为真实中性。",
            "每个结论必须至少包含一个数值、截止日和数据属性（真实/代理/缺口）。",
            "报告顺序固定为：结论→证据→持仓含义→下次确认条件；技术模型放在折叠附录。",
            "北向日度旧口径不再使用；没有可审计来源时不得声称机构净流入。",
            "样本外护栏未通过时只能输出研究候选，不能把概率或评分写成确定买卖指令。",
            "推荐关注ETF与回避ETF不得重叠；推荐关注不等于买入，回避不等于做空。",
            "逐只ETF必须分别回答真实申赎、量价代理、相对强度和直接新闻；全市场两融不得冒充单只ETF资金。",
            "未检索到直接新闻只能写新闻证据不足，不得写成没有利好或确定利空。",
        ],
        "downstream_output_contract": {
            "canonical_source": "data/market_diagnostics.json",
            "renderer_prompt": "prompts/etf_report_renderer.md",
            "required_order": ["最终判断", "推荐关注ETF", "回避ETF", "逐只资金与新闻深挖", "八项逐项结论", "数据缺口", "技术附录"],
            "required_candidate_fields": ["verdict", "why_selected", "fund_flow", "news_flow", "cross_read", "confirm_next", "invalidate"],
            "required_avoid_fields": ["action", "reason", "fund_flow", "news_flow", "cross_read", "reconsider", "position_note"],
            "forbidden_phrases_without_execution_permission": ["建议买入", "强烈推荐", "确定上涨", "必涨", "立即卖出", "建议做空", "机构正在大举流入", "北向今日净流入"],
            "missing_value_rule": "缺失写数据不足，并附最后可用日期；不得填0后解释为真实中性。",
            "compression_rule": "篇幅不足时保留结论、数字、截止日、数据属性和确认条件；优先删除术语解释与模型公式。",
            "role_definitions": {
                "推荐关注ETF": "规则候选且值得继续核验；只有execution_allowed=true并满足确认条件时才可转为执行。",
                "回避ETF": "限制新增或提示已有仓位复核；不知道用户持仓时不得生成卖出指令，也不代表做空。",
            },
            "fixed_etf_template": [
                "{角色}｜{ETF名称}（{代码}）｜{动作}",
                "为什么：必须含至少一个价格/相对强度数字。",
                "资金流：先写真实份额变化与估算金额；缺失时明确数据不足，再写量价代理。",
                "新闻流：写近14日直接新闻数量、方向、近3日热度和最多3条原文；无直接新闻不得推断利空。",
                "交叉判断：明确资金与新闻是共振、背离还是证据不足。",
                "下一步：推荐写确认与失效条件；回避写移出回避名单条件。",
            ],
            "render_protocol": {
                "mode": "只转述结构化字段，不重新选ETF、不重新打分、不补写事实",
                "language": "中文短句；先给结论，再给数字；不用公式，不堆叠专业术语",
                "max_items": {"recommendations": 3, "avoid_etfs": 3, "news_per_etf": 3},
                "allowed_recommend_actions": ["推荐观察", "推荐观察｜等待确认", "可小仓跟踪"],
                "allowed_avoid_actions": ["回避新增", "谨慎观察，不追涨"],
                "fail_closed": "字段缺失就写数据不足；角色或执行权限不清楚时，一律输出等待确认，不生成买卖指令",
                "pre_publish_checks": [
                    "推荐与回避代码没有重叠",
                    "每只ETF同时有资金流、新闻流、交叉判断和下一步",
                    "每个资金结论含期间或截止日，且未把全市场两融冒充单只ETF资金",
                    "每条新闻含日期和来源；报告补充已标注未回填规则",
                    "execution_allowed=false时全文没有确定买入、卖出或做空措辞",
                ],
            },
        },
    }
    save_json(OUTPUT_PATH, payload)
    return payload


def main():
    result = build_diagnostics()
    print(f"八模块诊断已生成: {OUTPUT_PATH}")
    print(f"综合判断: {result['overall']['status']} ({result['overall']['score']:+.1f})")
    print("推荐关注:", "、".join(row["name"] for row in result.get("recommendations", [])) or "暂无")
    print("回避新增:", "、".join(row["name"] for row in result.get("avoid_etfs", [])) or "暂无")
    for item in result["modules"]:
        print(f"  {item['order']}. {item['title']}: {item['status']} | {item['conclusion']}")


if __name__ == "__main__":
    main()
