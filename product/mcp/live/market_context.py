"""有界美国市场上下文采集：大盘、板块、跨资产、波动/信用代理与 24 小时新闻线索。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import HTTPSHandler, Request, build_opener

from product.mcp.live.cache import SnapshotCache
from product.mcp.live.contracts import validate_contract
from product.mcp.live.sec_client import Response, _NoRedirect
from product.mcp.live.tls import verified_https_context
from product.mcp.provenance import content_hash, iso_utc, parse_timestamp


ADAPTER_VERSION = "yahoo-public-market-context/1.0.0"
MAX_BYTES = 4 * 1024 * 1024
SERIES = {
    "SPY": ("US:MARKET:SPY", "BROAD_EQUITY", False),
    "XLC": ("US:MARKET:XLC", "SECTOR_COMMUNICATION", True),
    "XLY": ("US:MARKET:XLY", "SECTOR_CONSUMER_DISCRETIONARY", True),
    "XLP": ("US:MARKET:XLP", "SECTOR_CONSUMER_STAPLES", True),
    "XLE": ("US:MARKET:XLE", "SECTOR_ENERGY", True),
    "XLF": ("US:MARKET:XLF", "SECTOR_FINANCIALS", True),
    "XLV": ("US:MARKET:XLV", "SECTOR_HEALTH_CARE", True),
    "XLI": ("US:MARKET:XLI", "SECTOR_INDUSTRIALS", True),
    "XLK": ("US:MARKET:XLK", "SECTOR_INFORMATION_TECHNOLOGY", True),
    "XLB": ("US:MARKET:XLB", "SECTOR_MATERIALS", True),
    "XLRE": ("US:MARKET:XLRE", "SECTOR_REAL_ESTATE", True),
    "XLU": ("US:MARKET:XLU", "SECTOR_UTILITIES", True),
    "TLT": ("US:MARKET:TLT", "CROSS_ASSET_LONG_TREASURY", True),
    "UUP": ("US:MARKET:UUP", "CROSS_ASSET_US_DOLLAR", True),
    "GLD": ("US:MARKET:GLD", "CROSS_ASSET_GOLD", True),
    "USO": ("US:MARKET:USO", "CROSS_ASSET_OIL", True),
    "HYG": ("US:MARKET:HYG", "CREDIT_HIGH_YIELD_PROXY", True),
    "^VIX": ("US:MARKET:VIX", "VOLATILITY_INDEX", False),
}


def _http(request: Request) -> Response:
    try:
        with build_opener(_NoRedirect(), HTTPSHandler(context=verified_https_context())).open(
            request, timeout=20
        ) as response:
            body = response.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise ValueError("MARKET_CONTEXT_RESPONSE_TOO_LARGE")
            return Response(response.status, body)
    except HTTPError as exc:
        exc.close()
        return Response(exc.code, b"")
    except (URLError, OSError) as exc:
        raise ValueError("MARKET_CONTEXT_TRANSPORT_FAILURE") from exc


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("MARKET_NEWS_URL_INVALID")
    return urlunsplit(("https", parsed.hostname.lower(), parsed.path.rstrip("/") or "/", "", ""))


def _fact(
    *, security_id: str, semantic_field: str, value: str, unit: str,
    source_id: str, source_locator: str, as_of: str, published_at: str,
    retrieved_at: str, raw_content_hash: str, kind: str, metadata: Mapping[str, Any],
) -> dict[str, Any]:
    fact = {
        "schema_version": "live-fact/1.0.0", "security_id": security_id,
        "semantic_field": semantic_field, "value": value, "unit": unit,
        "currency": None,
        "source_id": source_id, "source_type": "yahoo",
        "source_locator": source_locator, "source_version": ADAPTER_VERSION,
        "as_of": iso_utc(as_of), "published_at": iso_utc(published_at),
        "published_at_policy": "provider_timestamp" if kind == "news" else "retrieval_time_conservative",
        "retrieved_at": iso_utc(retrieved_at), "raw_content_hash": raw_content_hash,
        "kind": "research" if kind == "news" else kind,
        "usage": "current", "metadata": dict(metadata),
        "parent_ids": [], "parent_hashes": [],
    }
    fact["evidence_id"] = "ev-market-context-" + content_hash(fact)
    validate_contract("fact", fact)
    return fact


def normalize_chart(
    raw: bytes, *, symbol: str, retrieved_at: str, endpoint: str, decision_cutoff: str,
) -> dict[str, Any]:
    try:
        result = json.loads(raw)["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote_rows = result["indicators"]["quote"][0]["close"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, IndexError) as exc:
        raise ValueError("MARKET_CONTEXT_CHART_INVALID") from exc
    if symbol not in SERIES or not isinstance(timestamps, list) or len(timestamps) != len(quote_rows):
        raise ValueError("MARKET_CONTEXT_CHART_INVALID")
    cutoff = parse_timestamp(decision_cutoff)
    raw_hash = hashlib.sha256(raw).hexdigest()
    security_id, role, proxy = SERIES[symbol]
    evidence = []
    for stamp, close in zip(timestamps, quote_rows):
        if close is None:
            continue
        observed = datetime.fromtimestamp(int(stamp), tz=timezone.utc)
        if observed > cutoff:
            continue
        try:
            number = Decimal(str(close))
        except (InvalidOperation, TypeError) as exc:
            raise ValueError("MARKET_CONTEXT_CHART_VALUE_INVALID") from exc
        if not number.is_finite():
            raise ValueError("MARKET_CONTEXT_CHART_VALUE_INVALID")
        evidence.append(_fact(
            security_id=security_id, semantic_field="market_context_close",
            value=format(number, "f"), unit="index_or_fund_close",
            source_id=f"yahoo-market-context:{symbol}", source_locator=endpoint,
            as_of=observed, published_at=retrieved_at, retrieved_at=retrieved_at,
            raw_content_hash=raw_hash, kind="price",
            metadata={
                "symbol": symbol, "series_role": role, "proxy": proxy,
                "proxy_limit": (
                    "ETF market price is not spot, original index value, or fund flow"
                    if proxy else None
                ),
            },
        ))
    if not evidence:
        raise ValueError("MARKET_CONTEXT_CHART_EMPTY")
    return {"evidence": evidence, "raw_content_hash": raw_hash}


def normalize_news(
    raw: bytes, *, retrieved_at: str, endpoint: str, decision_cutoff: str,
) -> dict[str, Any]:
    try:
        rows = json.loads(raw).get("news", [])
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError) as exc:
        raise ValueError("MARKET_NEWS_RESPONSE_INVALID") from exc
    if not isinstance(rows, list):
        raise ValueError("MARKET_NEWS_RESPONSE_INVALID")
    cutoff = parse_timestamp(decision_cutoff)
    start = cutoff - timedelta(hours=24)
    raw_hash = hashlib.sha256(raw).hexdigest()
    evidence, seen = [], set()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        title, link, timestamp = row.get("title"), row.get("link"), row.get("providerPublishTime")
        if not isinstance(title, str) or not isinstance(link, str) or not isinstance(timestamp, int):
            continue
        published = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        if not start <= published <= cutoff:
            continue
        try:
            canonical = _canonical_url(link)
        except ValueError:
            continue
        key = (canonical, " ".join(title.casefold().split()))
        if key in seen:
            continue
        seen.add(key)
        evidence.append(_fact(
            security_id="US:MARKET", semantic_field="market_news_item",
            value=json.dumps({
                "title": title.strip(), "publisher": row.get("publisher"),
                "original_url": canonical, "content_tier": "TITLE_ONLY",
            }, ensure_ascii=False),
            unit="news_item", source_id="yahoo-market-news", source_locator=canonical,
            as_of=published, published_at=published, retrieved_at=retrieved_at,
            raw_content_hash=raw_hash, kind="news",
            metadata={
                "window_hours": 24, "content_tier": "TITLE_ONLY",
                "limitation": "headline locator only; not verified article body",
            },
        ))
    return {
        "evidence": evidence, "raw_content_hash": raw_hash,
        "gaps": [] if evidence else [{"reason": "MARKET_NEWS_WINDOW_EMPTY", "window_hours": 24}],
    }


def collect_market_context_snapshot(
    *, policy_path: Path, output_path: Path, cache_root: Path,
    decision_cutoff: str | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    transport: Callable[[Request], Response] = _http,
) -> dict[str, Any]:
    policy = json.loads(Path(policy_path).read_text(encoding="utf-8"))
    source = policy.get("sources", {}).get("yahoo_market_context", {})
    if (
        source.get("adapter_version") != ADAPTER_VERSION
        or source.get("authentication") != "none"
        or source.get("domains") != ["query1.finance.yahoo.com"]
        or source.get("request_budget", {}).get("series") != len(SERIES)
    ):
        raise ValueError("MARKET_CONTEXT_POLICY_INVALID")
    cutoff = parse_timestamp(decision_cutoff) if decision_cutoff else now()
    start = cutoff - timedelta(days=int(source["request_budget"]["days"]))
    cache = SnapshotCache(cache_root)
    evidence, gaps, events, records = [], [], [], []
    for number, symbol in enumerate(SERIES, 1):
        endpoint = source["chart_endpoint_template"].format(symbol=quote(symbol, safe=""))
        endpoint += "?" + urlencode({
            "period1": int(start.timestamp()), "period2": int(cutoff.timestamp()) + 1,
            "interval": "1d", "events": "history", "includeAdjustedClose": "true",
        })
        event = {"provider": "yahoo_market_context", "operation": "chart", "symbol": symbol,
                 "request_number": number, "started_at": iso_utc(now())}
        events.append(event)
        try:
            response = transport(Request(endpoint, headers={"Accept": "application/json", "User-Agent": "stock-agent-readonly/1.0"}, method="GET"))
            event.update(http_status=response.status, completed_at=iso_utc(now()))
            if response.status != 200:
                raise ValueError(f"MARKET_CONTEXT_CHART_HTTP_{response.status}")
            record = cache.store({"provider": "yahoo_market_context", "operation": "chart", "symbol": symbol,
                                  "adapter_version": ADAPTER_VERSION}, response.body, retrieved_at=event["completed_at"])
            normalized = normalize_chart(response.body, symbol=symbol, retrieved_at=record["retrieved_at"],
                                         endpoint=endpoint, decision_cutoff=iso_utc(cutoff))
            evidence.extend(normalized["evidence"])
            records.append(record["record_hash"])
            event.update(status="FETCHED", record_hash=record["record_hash"])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            code = str(exc).split(":", 1)[0]
            event.update(status="FAILED", failure_code=code, completed_at=event.get("completed_at", iso_utc(now())))
            gaps.append({"dataset": f"series:{symbol}", "reason": code})
    news_endpoint = source["news_endpoint"] + "?" + urlencode({
        "q": "US stock market", "quotesCount": 0, "newsCount": 40,
        "enableFuzzyQuery": "false",
    })
    news_event = {"provider": "yahoo_market_context", "operation": "news", "request_number": 1,
                  "started_at": iso_utc(now())}
    events.append(news_event)
    try:
        response = transport(Request(news_endpoint, headers={"Accept": "application/json", "User-Agent": "stock-agent-readonly/1.0"}, method="GET"))
        news_event.update(http_status=response.status, completed_at=iso_utc(now()))
        if response.status != 200:
            raise ValueError(f"MARKET_NEWS_HTTP_{response.status}")
        record = cache.store({"provider": "yahoo_market_context", "operation": "news",
                              "adapter_version": ADAPTER_VERSION}, response.body, retrieved_at=news_event["completed_at"])
        normalized = normalize_news(response.body, retrieved_at=record["retrieved_at"], endpoint=news_endpoint,
                                    decision_cutoff=iso_utc(cutoff))
        evidence.extend(normalized["evidence"])
        gaps.extend(normalized["gaps"])
        records.append(record["record_hash"])
        news_event.update(status="FETCHED", record_hash=record["record_hash"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        code = str(exc).split(":", 1)[0]
        news_event.update(status="FAILED", failure_code=code, completed_at=news_event.get("completed_at", iso_utc(now())))
        gaps.append({"dataset": "market_news_24h", "reason": code})
    snapshot_cutoff = cutoff
    if decision_cutoff is None:
        # 实时采集的查询窗口在首个请求前冻结，但 Evidence 的获取时间会自然晚于
        # 该时刻；最终 Gate cutoff 必须覆盖本批实际完成时间，不能制造 PIT 违规。
        observed_times = [
            parse_timestamp(str(item["retrieved_at"]))
            for item in evidence
            if isinstance(item, Mapping) and isinstance(item.get("retrieved_at"), str)
        ]
        observed_times.extend(
            parse_timestamp(str(item["completed_at"]))
            for item in events
            if isinstance(item, Mapping) and isinstance(item.get("completed_at"), str)
        )
        snapshot_cutoff = max([cutoff, *observed_times])
    snapshot = {
        "schema_version": "market-context-snapshot/1.0.0",
        "status": "FROZEN" if evidence else "SOURCE_LIMITED",
        "decision_cutoff": iso_utc(snapshot_cutoff),
        "evidence": sorted(evidence, key=lambda item: item["evidence_id"]),
        "gaps": gaps, "events": events, "record_hashes": sorted(records),
        "adapter_version": ADAPTER_VERSION,
    }
    snapshot["snapshot_hash"] = content_hash(snapshot)
    Path(output_path).write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return snapshot
