#!/usr/bin/env python3
"""抓取可量化的中国宏观指标并保留发布日期。

宏观数据只用于当期八模块研判；在没有完整“发布日期历史”前不进入回测特征，
避免把后来公布的数据回填到过去。接口失败时保留缓存，不用空文件覆盖历史。
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime

import requests


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_FILE = os.path.join(BASE_DIR, "data", "macro_data.json")
API_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
    "Referer": "https://data.eastmoney.com/cjsj/",
}

REPORTS = [
    {
        "report": "RPT_ECONOMY_PMI",
        "columns": "REPORT_DATE,TIME,MAKE_INDEX,NMAKE_INDEX",
        "metrics": {"MAKE_INDEX": "manufacturing_pmi", "NMAKE_INDEX": "non_manufacturing_pmi"},
        "unit": "index",
        "reference": "https://www.stats.gov.cn/sj/zxfb/",
    },
    {
        "report": "RPT_ECONOMY_CPI",
        "columns": "REPORT_DATE,TIME,NATIONAL_SAME,NATIONAL_SEQUENTIAL",
        "metrics": {"NATIONAL_SAME": "cpi_yoy", "NATIONAL_SEQUENTIAL": "cpi_mom"},
        "unit": "%",
        "reference": "https://www.stats.gov.cn/sj/zxfb/",
    },
    {
        "report": "RPT_ECONOMY_PPI",
        "columns": "REPORT_DATE,TIME,BASE_SAME",
        "metrics": {"BASE_SAME": "ppi_yoy"},
        "unit": "%",
        "reference": "https://www.stats.gov.cn/sj/zxfb/",
    },
    {
        "report": "RPT_ECONOMY_INDUS_GROW",
        "columns": "REPORT_DATE,TIME,BASE_SAME,BASE_ACCUMULATE",
        "metrics": {"BASE_SAME": "industrial_value_added_yoy"},
        "unit": "%",
        "reference": "https://www.stats.gov.cn/sj/zxfb/",
    },
    {
        "report": "RPT_ECONOMY_TOTAL_RETAIL",
        "columns": "REPORT_DATE,TIME,RETAIL_TOTAL_SAME,RETAIL_ACCUMULATE_SAME",
        "metrics": {"RETAIL_TOTAL_SAME": "retail_sales_yoy"},
        "unit": "%",
        "reference": "https://www.stats.gov.cn/sj/zxfb/",
    },
    {
        "report": "RPT_ECONOMY_CURRENCY_SUPPLY",
        "columns": "REPORT_DATE,TIME,BASIC_CURRENCY_SAME,CURRENCY_SAME",
        "metrics": {"BASIC_CURRENCY_SAME": "m2_yoy", "CURRENCY_SAME": "m1_yoy"},
        "unit": "%",
        "reference": "https://www.pbc.gov.cn/diaochatongjisi/116219/index.html",
    },
    {
        "report": "RPT_ECONOMY_GDP",
        "columns": "REPORT_DATE,TIME,SUM_SAME",
        "metrics": {"SUM_SAME": "gdp_yoy"},
        "unit": "%",
        "reference": "https://www.stats.gov.cn/sj/zxfb/",
    },
]


def load_cache():
    try:
        with open(OUT_FILE, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {"indicators": {}}


def fetch_report(spec):
    params = {
        "columns": spec["columns"],
        "pageNumber": "1",
        "pageSize": "120",
        "sortColumns": "REPORT_DATE",
        "sortTypes": "-1",
        "source": "WEB",
        "client": "WEB",
        "reportName": spec["report"],
    }
    last_error = None
    for attempt in range(2):
        try:
            response = requests.get(API_URL, params=params, headers=HEADERS, timeout=(5, 12))
            response.raise_for_status()
            payload = response.json()
            return (payload.get("result") or {}).get("data") or []
        except Exception as exc:
            last_error = exc
            time.sleep(1 + attempt)
    raise RuntimeError(f"{spec['report']}: {last_error}")


def as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize(spec, records):
    output = {}
    for record in records:
        release_date = str(record.get("REPORT_DATE", ""))[:10]
        period = str(record.get("TIME", "") or release_date)
        if not release_date:
            continue
        for raw_key, metric in spec["metrics"].items():
            value = as_float(record.get(raw_key))
            if value is None:
                continue
            output.setdefault(metric, []).append({
                "release_date": release_date,
                "period": period,
                "value": value,
                "unit": spec["unit"],
                "collector": "东方财富宏观数据接口",
                "authoritative_reference": spec["reference"],
                "report_name": spec["report"],
            })
    return output


def merge_rows(old_rows, new_rows):
    merged = {
        (str(row.get("release_date", "")), str(row.get("period", ""))): row
        for row in old_rows
    }
    for row in new_rows:
        merged[(row["release_date"], row["period"])] = row
    rows = sorted(merged.values(), key=lambda row: (row.get("release_date", ""), row.get("period", "")))
    return rows[-120:]


def main():
    cache = load_cache()
    indicators = {name: list(rows) for name, rows in cache.get("indicators", {}).items()}
    health, success = {}, 0
    for spec in REPORTS:
        try:
            records = fetch_report(spec)
            normalized = normalize(spec, records)
            for name, rows in normalized.items():
                indicators[name] = merge_rows(indicators.get(name, []), rows)
            health[spec["report"]] = {"status": "ok", "records": len(records)}
            success += 1
            print(f"  {spec['report']}: {len(records)} 条")
        except Exception as exc:
            health[spec["report"]] = {"status": "cached", "error": str(exc)[:180]}
            print(f"  [WARN] {spec['report']}: {exc}")

    if not success and not any(indicators.values()):
        raise SystemExit("宏观接口全部失败且无可用缓存")
    payload = {
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "indicators": indicators,
        "source_health": health,
        "usage_policy": "只按release_date使用；没有历史发布日期的指标不回填计量模型。",
    }
    os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
    print(f"保存完成: {len(indicators)} 个指标 → {OUT_FILE}")


if __name__ == "__main__":
    main()
