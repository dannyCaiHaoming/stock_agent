"""Yahoo QuoteSummary 的有限公司档案、预期、事件与空头背景标准化。"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

from product.mcp.live.research_supplement import build_supplement_fact
from product.mcp.live.yahoo_transport import TRANSPORT_VERSION
from product.mcp.provenance import iso_utc


ADAPTER_VERSION = "yahoo-company-background/1.0.0"
MODULES = (
    "assetProfile", "price", "calendarEvents", "earningsTrend",
    "recommendationTrend", "defaultKeyStatistics", "summaryDetail",
)


def _raw(value: Any) -> Any:
    if isinstance(value, Mapping) and "raw" in value:
        return value["raw"]
    return value


def _present(mapping: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {field: _raw(mapping[field]) for field in fields if field in mapping and _raw(mapping[field]) is not None}


def normalize_quote_summary(
    raw: bytes, *, security_id: str, ticker: str, retrieved_at: str,
) -> dict[str, Any]:
    if not raw or len(raw) > 32 * 1024 * 1024:
        raise ValueError("YAHOO_RESEARCH_RESPONSE_SIZE_INVALID")
    try:
        body = json.loads(raw)
        root = body["quoteSummary"]
        results = root["result"]
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("YAHOO_RESEARCH_RESPONSE_INVALID") from exc
    if root.get("error") is not None or not isinstance(results, list) or len(results) != 1:
        raise ValueError("YAHOO_RESEARCH_RESULT_INVALID")
    result = results[0]
    if not isinstance(result, Mapping):
        raise ValueError("YAHOO_RESEARCH_RESULT_INVALID")
    price = result.get("price", {})
    if _raw(price.get("symbol")) not in (None, ticker) or _raw(price.get("quoteType")) not in (None, "EQUITY"):
        raise ValueError("YAHOO_RESEARCH_SECURITY_MISMATCH")
    retrieved = iso_utc(retrieved_at)
    raw_hash = hashlib.sha256(raw).hexdigest()
    locator = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
    facts, gaps = [], []

    def add(dataset: str, semantic_field: str, value: Mapping[str, Any], limitations: list[str]):
        if not value:
            gaps.append({"dataset": dataset, "reason": "YAHOO_RESEARCH_FIELDS_MISSING", "field": semantic_field})
            return
        facts.append(build_supplement_fact(
            security_id=security_id, dataset=dataset, semantic_field=semantic_field,
            value=dict(value), source_id=f"yahoo-quote-summary:{ticker}",
            source_family="yahoo", source_locator=locator,
            source_version=f"{TRANSPORT_VERSION}/{ADAPTER_VERSION}",
            as_of=retrieved, published_at=retrieved, retrieved_at=retrieved,
            raw_content_hash=raw_hash, limitations=limitations,
        ))

    profile = result.get("assetProfile", {})
    identity = {
        **_present(price, ("longName", "shortName", "exchange", "exchangeName", "currency", "quoteType")),
        **_present(profile, (
            "sector", "industry", "industryKey", "sectorKey", "longBusinessSummary",
            "city", "state", "country", "website", "fullTimeEmployees",
        )),
    }
    add(
        "identity_profile", "yahoo_company_profile", identity,
        ["当前可见公司档案；Yahoo 未提供字段历史 vintage，不可冒充历史资料"],
    )

    calendar = result.get("calendarEvents", {})
    earnings = calendar.get("earnings", {}) if isinstance(calendar, Mapping) else {}
    earnings_value = _present(earnings, (
        "earningsDate", "earningsAverage", "earningsLow", "earningsHigh",
        "revenueAverage", "revenueLow", "revenueHigh",
    ))
    add(
        "event_context", "yahoo_earnings_calendar", earnings_value,
        ["日期可能为估计区间；属于 Yahoo 当前快照，不代表发行人指引"],
    )

    trends = result.get("earningsTrend", {}).get("trend", [])
    if isinstance(trends, list):
        normalized_trends = []
        for row in trends:
            if not isinstance(row, Mapping):
                continue
            normalized_trends.append({
                "period": row.get("period"), "end_date": row.get("endDate"),
                "growth": _raw(row.get("growth")),
                "accounting_basis": "UNKNOWN",
                "vintage_status": "RETRIEVAL_SNAPSHOT_HISTORY_UNKNOWN",
                "earnings_estimate": _present(row.get("earningsEstimate", {}), (
                    "numberOfAnalysts", "avg", "low", "high", "yearAgoEps", "growth",
                )),
                "revenue_estimate": _present(row.get("revenueEstimate", {}), (
                    "numberOfAnalysts", "avg", "low", "high", "yearAgoRevenue", "growth",
                )),
                "eps_trend": _present(row.get("epsTrend", {}), (
                    "current", "7daysAgo", "30daysAgo", "60daysAgo", "90daysAgo",
                )),
                "eps_revisions": _present(row.get("epsRevisions", {}), (
                    "upLast7days", "upLast30days", "downLast7Days", "downLast30days",
                )),
            })
        add(
            "analyst_expectations", "yahoo_earnings_trend",
            {"periods": normalized_trends} if normalized_trends else {},
            ["第三方一致预期；检索前的历史 vintage 未知", "不得与 SEC 实际值或发行人指引混同"],
        )
    recommendations = result.get("recommendationTrend", {}).get("trend", [])
    if isinstance(recommendations, list):
        rows = [
            _present(row, ("period", "strongBuy", "buy", "hold", "sell", "strongSell"))
            for row in recommendations if isinstance(row, Mapping)
        ]
        add(
            "analyst_expectations", "yahoo_recommendation_trend",
            {"periods": rows} if rows else {},
            ["评级分布为第三方快照；券商样本、口径和历史 vintage 可能不完整"],
        )

    short = result.get("defaultKeyStatistics", {})
    short_value = _present(short, (
        "sharesOutstanding", "floatShares", "sharesShort", "sharesShortPriorMonth",
        "dateShortInterest", "sharesPercentSharesOut", "shortPercentOfFloat", "shortRatio",
    ))
    add(
        "share_short_context", "yahoo_share_short_snapshot", short_value,
        ["short interest 与 short volume 不同；无借券费率时不得推算借券成本或方向"],
    )

    # 供应商统计没有逐字段发布时间。这里只保留首次观测输入和原始响应
    # hash，后续 EquityValuationSnapshot 会把 published_at 保持为 null，
    # 不能将 retrieved_at 当作历史可知时间。
    valuation_fields = {
        **_present(price, ("regularMarketPrice", "marketCap", "currency")),
        **_present(short, (
            "trailingPE", "forwardPE", "priceToBook", "enterpriseValue",
            "enterpriseToRevenue", "enterpriseToEbitda", "sharesOutstanding",
            "bookValue", "forwardEps", "trailingEps",
        )),
        **_present(result.get("summaryDetail", {}), (
            "trailingPE", "forwardPE", "priceToSalesTrailing12Months",
            "priceToBook", "marketCap", "enterpriseValue",
        )),
    }
    valuation_snapshot = {
        "schema_version": "yahoo-valuation-inputs/1.0.0",
        "security_id": security_id,
        "source_id": f"yahoo-quote-summary:{ticker}",
        "source_locator": locator,
        "source_version": f"{TRANSPORT_VERSION}/{ADAPTER_VERSION}",
        "as_of": retrieved,
        "retrieved_at": retrieved,
        "published_at": None,
        "availability_status": "FIRST_OBSERVED_AT_RETRIEVAL",
        "raw_content_hash": raw_hash,
        "fields": valuation_fields,
        "missing_fields": sorted({
            "trailingPE", "forwardPE", "priceToSalesTrailing12Months",
            "priceToBook", "marketCap", "enterpriseValue", "enterpriseToEbitda",
        } - set(valuation_fields)),
        "limitations": [
            "Yahoo 未提供这些当前统计的逐字段发布时间或历史 vintage",
            "供应商报告值须与系统派生值分列，不能用于首次观测之前的 PIT 历史",
        ],
    }

    summary = result.get("summaryDetail", {})
    allocation = _present(summary, (
        "dividendRate", "dividendYield", "exDividendDate", "payoutRatio",
        "fiveYearAvgDividendYield",
    ))
    add(
        "capital_allocation", "yahoo_dividend_snapshot", allocation,
        ["供应商当前快照；实际分红与回购以 SEC 披露为主"],
    )
    return {
        "adapter_version": ADAPTER_VERSION,
        "source_modules": list(MODULES),
        "security_id": security_id,
        "evidence": sorted(facts, key=lambda item: item["evidence_id"]),
        "valuation_snapshot": valuation_snapshot,
        "gaps": gaps,
        "raw_content_hash": raw_hash,
    }


def collect_quote_summary(
    *, session: Any, cache: Any, security_id: str, ticker: str, retrieved_at: str,
    crumb: str | None = None,
) -> dict[str, Any]:
    """通过既有 Yahoo 有界 session 读取固定 modules；不接受调用方 URL。"""
    if crumb is None:
        from product.mcp.live.yahoo_transport import acquire_anonymous_crumb
        crumb = acquire_anonymous_crumb(session)
    url = f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
    response = session.get(url, params={"modules": ",".join(MODULES), "crumb": crumb})
    raw_hash = hashlib.sha256(response.content).hexdigest()
    records = [
        item["record"] for item in session.live_boundary.research_records
        if item["ticker"] == ticker and item["record"]["raw_content_hash"] == raw_hash
    ]
    if len(records) != 1:
        raise ValueError("YAHOO_RESEARCH_CACHE_BINDING_MISSING")
    cache.read(records[0])
    normalized = normalize_quote_summary(
        response.content, security_id=security_id, ticker=ticker,
        retrieved_at=records[0]["retrieved_at"],
    )
    normalized["requested_at"] = iso_utc(retrieved_at)
    normalized["record"] = records[0]
    return normalized
