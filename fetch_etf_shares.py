#!/usr/bin/env python3
"""增量抓取交易所公开 ETF 份额，并在网络失败时保留历史缓存。

上交所提供指定交易日份额，按周留档并始终刷新最新交易日；深交所只提供
当前快照，因此从每次流水线开始累积快照。只有连续两个快照才计算申赎方向。
"""
from __future__ import annotations

import io
import json
import os
from datetime import datetime

import pandas as pd
import requests

from etf_universe import SECTOR_ETF_MAP


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(BASE_DIR, "data", "etf_shares.json")
PRICE_FILE = os.path.join(BASE_DIR, "data", "etf_history.json")
START_DATE = "2025-01-01"
SSE_URL = "https://query.sse.com.cn/commonQuery.do"
SZSE_URL = "https://fund.szse.cn/api/report/ShowReport"
HEADERS = {
    "Referer": "https://www.sse.com.cn/",
    "User-Agent": "Mozilla/5.0 (compatible; fucketf-research/5.0)",
}


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError, TypeError):
        return default


def price_trade_dates():
    """使用已下载行情的真实日期，避免为交易日历再发一次无界网络请求。"""
    prices = load_json(PRICE_FILE, {})
    rows = prices.get("510300", {}).get("data", [])
    return sorted({str(row.get("date", ""))[:10] for row in rows if str(row.get("date", ""))[:10] >= START_DATE})


def fetch_sse_day(date_str):
    params = {
        "isPagination": "true",
        "pageHelp.pageSize": "10000",
        "pageHelp.pageNo": "1",
        "pageHelp.beginPage": "1",
        "pageHelp.cacheSize": "1",
        "pageHelp.endPage": "1",
        "sqlId": "COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L",
        "STAT_DATE": date_str,
    }
    response = requests.get(SSE_URL, params=params, headers=HEADERS, timeout=(5, 15))
    response.raise_for_status()
    targets = {code for code in SECTOR_ETF_MAP if code.startswith("5")}
    values = {}
    for row in response.json().get("result", []):
        code = str(row.get("SEC_CODE", "")).zfill(6)
        if code not in targets:
            continue
        try:
            # SSE 的 TOT_VOL 单位为万份。
            values[code] = float(str(row.get("TOT_VOL", "0")).replace(",", "")) * 10000
        except (TypeError, ValueError):
            continue
    return values


def update_sse_history(old_history, dates):
    history = {str(day): dict(values) for day, values in old_history.items() if isinstance(values, dict)}
    if not dates:
        return history, 0, "无行情日期"
    if history:
        last_cached = max(history)
        pending = [day for day in dates if day > last_cached]
        # 跨多个未运行日时仍按每五个交易日留一档。
        candidates = pending[::5]
    else:
        candidates = dates[::5]
    if dates[-1] not in candidates:
        candidates.append(dates[-1])

    successes = 0
    errors = []
    for day in candidates:
        try:
            values = fetch_sse_day(day)
            if values:
                history[day] = values
                successes += 1
                print(f"  上交所 {day}: {len(values)} 只")
            else:
                errors.append(f"{day}为空")
        except Exception as exc:  # 网络错误不得清空既有历史
            errors.append(f"{day}: {type(exc).__name__}")
            print(f"  [WARN] 上交所 {day}: {exc}")
    status = "可用" if successes else ("沿用缓存" if history else "失败")
    if errors:
        status += f"；{len(errors)}次请求未更新"
    return history, successes, status


def fetch_szse_snapshot():
    params = {
        "SHOWTYPE": "xlsx",
        "CATALOGID": "1000_lf",
        "TABKEY": "tab1",
        "random": "0.5",
    }
    headers = dict(HEADERS, Referer="https://fund.szse.cn/marketdata/fundslist/index.html")
    response = requests.get(SZSE_URL, params=params, headers=headers, timeout=(5, 20))
    response.raise_for_status()
    frame = pd.read_excel(io.BytesIO(response.content), engine="openpyxl", dtype={"基金代码": str})
    targets = {code for code in SECTOR_ETF_MAP if code.startswith("1")}
    values = {}
    share_col = "当前规模(份)" if "当前规模(份)" in frame.columns else "基金份额"
    for _, row in frame.iterrows():
        code = str(row.get("基金代码", "")).zfill(6)
        if code not in targets:
            continue
        try:
            values[code] = float(str(row.get(share_col, "0")).replace(",", ""))
        except (TypeError, ValueError):
            continue
    return values


def main():
    old = load_json(OUT_FILE, {})
    dates = price_trade_dates()
    effective_date = dates[-1] if dates else datetime.now().date().isoformat()

    history, sse_updates, sse_status = update_sse_history(old.get("history", {}), dates)
    szse_history = {
        str(day): dict(values)
        for day, values in old.get("szse_snapshot", {}).items()
        if isinstance(values, dict)
    }
    try:
        values = fetch_szse_snapshot()
        if values:
            szse_history[effective_date] = values
            szse_status = "可用"
            print(f"  深交所 {effective_date}: {len(values)} 只")
        else:
            szse_status = "返回为空；沿用缓存"
    except Exception as exc:
        szse_status = "沿用缓存" if szse_history else "失败"
        print(f"  [WARN] 深交所当前快照: {exc}")

    # 只保留最近120次深交所快照，足以计算申赎变化且不会无限增长。
    szse_history = dict(sorted(szse_history.items())[-120:])
    if not history and not szse_history:
        raise SystemExit("ETF份额抓取失败且没有可用缓存")

    payload = {
        "updated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "coverage": {
            "sse": "weekly historical snapshots plus latest refresh",
            "szse": "pipeline snapshots; flow requires two distinct dates",
        },
        "source_health": {
            "sse": {"status": sse_status, "new_snapshots": sse_updates},
            "szse": {"status": szse_status},
        },
        "history": history,
        # 保留旧字段名以兼容现有读取器；现在实际是可累积历史，而非单期值。
        "szse_snapshot": szse_history,
    }
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    print(f"保存完成: 上交所{len(history)}期、深交所{len(szse_history)}期；失败不会覆盖历史")


if __name__ == "__main__":
    main()
