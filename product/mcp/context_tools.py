"""Macro, market-state and peer tools for the stock-data MCP server (read-only, free sources).

Reuses product.mcp.live.macro (BLS, Treasury, Federal Reserve, BLS calendar) and
product.mcp.live.market_context (sector/cross-asset ETFs, VIX, market headlines), and
Yahoo public endpoints for related symbols and peer key statistics. Outputs are compact
tables with provenance; numbers are deterministic, interpretation is left to the agent.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import re
from pathlib import Path
from typing import Any
from urllib.request import Request

from product.mcp import data_tools, settings
from product.mcp.data_tools import DataToolError, _cutoff, _num, _pick, _raw, _ticker
from product.mcp.live import macro, market_context
from product.mcp.live.cache import SnapshotCache
from product.mcp.provenance import iso_utc, parse_timestamp

POLICY = Path(__file__).resolve().parent / "live" / "research-source-policy.json"
BLS_SERIES = {"cpi_all_items": "CUUR0000SA0", "cpi_core": "CUUR0000SA0L1E"}
BLS_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/{series}"


def _now() -> str:
    return iso_utc(datetime.now(UTC))


def _snapshot_path(kind: str) -> Path:
    directory = settings.data_dir() / "snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{kind}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}.json"


def _pct(new: Decimal, old: Decimal) -> str | None:
    return None if old == 0 else format(round((new / old - 1) * 100, 2), "f")


def _bls_history(series: str, cutoff: datetime) -> dict[str, Any]:
    cache: SnapshotCache = settings.cache()
    key = {"provider": "bls-v1", "series": series, "day": cutoff.date().isoformat()}
    record = cache.lookup(key)
    if record is None:
        response = macro._http(Request(BLS_URL.format(series=series),
                                       headers={"User-Agent": "stock-agent-readonly/1.0"}, method="GET"))
        if response.status != 200:
            raise DataToolError(f"BLS_HTTP_{response.status}")
        record = cache.store(key, response.body, retrieved_at=_now())
    body = json.loads(cache.read(record))
    if body.get("status") != "REQUEST_SUCCEEDED":
        raise DataToolError("BLS_REQUEST_REJECTED")
    rows = [r for r in body["Results"]["series"][0]["data"] if r["period"].startswith("M") and r["period"] != "M13"
            and re.fullmatch(r"-?\d+(?:\.\d+)?", str(r.get("value", "")).strip())]  # BLS marks missing months "-"
    points = sorted(((int(r["year"]), int(r["period"][1:]), Decimal(r["value"])) for r in rows))
    return {"points": points, "retrieved_at": record["retrieved_at"], "raw_content_hash": record["raw_content_hash"]}


def _yoy_rows(points: list[tuple[int, int, Decimal]], months: int = 6) -> list[list[str]]:
    by_month = {(y, m): v for y, m, v in points}
    out = []
    for y, m, v in points[-months:]:
        prior = by_month.get((y - 1, m))
        out.append([f"{y}-{m:02d}", format(v, "f"), _pct(v, prior) if prior else None])
    return out


_MEMO: dict[tuple, tuple[datetime, dict]] = {}
MEMO_TTL = timedelta(minutes=30)


def _memo(kind: str, as_of: str | None, build):
    """Reuse a recent snapshot in this server process (both collectors make ~10-20 HTTP requests)."""
    key = (kind, as_of)
    hit = _MEMO.get(key)
    if hit and datetime.now(UTC) - hit[0] < MEMO_TTL:
        return {**hit[1], "reused_from_memo_at": iso_utc(hit[0])}
    value = build()
    _MEMO[key] = (datetime.now(UTC), value)
    return value


def get_macro_snapshot(as_of: str | None = None) -> dict[str, Any]:
    """US rates, labor, inflation (YoY computed), latest Fed communication title and BLS release calendar."""
    return _memo("macro", as_of, lambda: _macro_snapshot(as_of))


def _macro_snapshot(as_of: str | None) -> dict[str, Any]:
    cutoff = _cutoff(as_of)
    snap = macro.collect_official_macro_snapshot(
        policy_path=POLICY, output_path=_snapshot_path("macro"), cache_root=settings.cache().root,
        decision_cutoff=iso_utc(cutoff) if as_of else None)
    facts, calendar, fed = [], [], None
    for e in snap["evidence"]:
        if e["semantic_field"] == "bls_announced_release_calendar":
            for event in json.loads(e["value"]) if isinstance(e["value"], str) else e["value"]:
                when = parse_timestamp(event["scheduled_at"])
                if cutoff <= when <= cutoff + timedelta(days=45):
                    calendar.append([event["scheduled_at"], event["summary"]])
        elif e["semantic_field"] == "federal_reserve_monetary_policy_text":
            text = " ".join(str(e["value"]).split())
            marker = text.find("Minutes of the Federal Open Market Committee") if "Minutes" in text else -1
            fed = {"published_at": e["published_at"], "source_locator": e["source_locator"],
                   "excerpt": text[max(0, marker):max(0, marker) + 600] if marker >= 0 else text[:600],
                   "note": "Title/press-release text only; read the linked document for policy content."}
        else:
            facts.append([e["semantic_field"], e["value"], e["unit"], e["as_of"][:10], e["published_at"][:10],
                          e["source_id"]])
    inflation = {}
    for name, series in BLS_SERIES.items():
        try:
            history = _bls_history(series, cutoff)
            visible = [p for p in history["points"]
                       if datetime(p[0], p[1], 1, tzinfo=UTC) + timedelta(days=40) <= cutoff + timedelta(days=40)]
            inflation[name] = {"series_id": series, "columns": ["month", "index", "yoy_percent"],
                               "rows": _yoy_rows(visible), "retrieved_at": history["retrieved_at"],
                               "source_locator": BLS_URL.format(series=series)}
        except Exception as exc:  # noqa: BLE001 - report as a gap, keep the rest of the snapshot
            inflation[name] = {"error": f"{type(exc).__name__}: {exc}"}
    return {
        "as_of": iso_utc(cutoff),
        "columns": ["field", "value", "unit", "observation_date", "published_or_retrieved", "source_id"],
        "facts": facts, "inflation": inflation, "fed_latest": fed,
        "upcoming_releases_45d": calendar[:20], "gaps": snap.get("gaps", []),
        "provenance": {"sources": ["BLS public API v1", "U.S. Treasury yield curve CSV", "Federal Reserve RSS",
                                   "BLS release calendar"],
                       "retrieved_at": _now(),
                       "notes": "Official current values, not historical vintages: revised data may differ from "
                                "what was known at the time. yoy_percent is computed from the BLS index levels."},
    }


def _returns(closes: list[tuple[str, Decimal]], sessions: int) -> str | None:
    if len(closes) <= sessions:
        return None
    return _pct(closes[-1][1], closes[-1 - sessions][1])


def get_market_context(as_of: str | None = None) -> dict[str, Any]:
    """S&P 500 (SPY), 11 sector ETFs, Treasuries (TLT), dollar (UUP), gold, oil, high yield (HYG) and VIX:
    last close and 5/20/60-session % change, plus recent market headlines."""
    return _memo("market", as_of, lambda: _market_context(as_of))


def _market_context(as_of: str | None) -> dict[str, Any]:
    cutoff = _cutoff(as_of)
    snap = market_context.collect_market_context_snapshot(
        policy_path=POLICY, output_path=_snapshot_path("market"), cache_root=settings.cache().root,
        decision_cutoff=iso_utc(cutoff) if as_of else None)
    series: dict[str, list[tuple[str, Decimal]]] = {}
    roles: dict[str, tuple[str, bool]] = {}
    headlines = []
    for e in snap["evidence"]:
        if e["semantic_field"] == "market_context_close":
            symbol = e["metadata"]["symbol"]
            series.setdefault(symbol, []).append((e["as_of"][:10], Decimal(e["value"])))
            roles[symbol] = (e["metadata"]["series_role"], e["metadata"]["proxy"])
        elif e["semantic_field"] == "market_news_item":
            try:
                item = json.loads(e["value"]) if isinstance(e["value"], str) else dict(e["value"])
            except (TypeError, ValueError):
                item = {"title": str(e["value"])}
            headlines.append([e["published_at"], item.get("title"), item.get("publisher"),
                              item.get("original_url") or e["source_locator"]])
    rows = []
    for symbol, closes in series.items():
        closes.sort()
        rows.append([symbol, roles[symbol][0], closes[-1][0], _num(closes[-1][1], 2),
                     _returns(closes, 5), _returns(closes, 20), _returns(closes, 60), roles[symbol][1]])
    rows.sort(key=lambda r: (r[1] != "BROAD_EQUITY", r[1]))
    headlines.sort(reverse=True)
    return {
        "as_of": iso_utc(cutoff),
        "columns": ["symbol", "role", "last_date", "last_close", "chg_5d_pct", "chg_20d_pct", "chg_60d_pct",
                    "is_proxy"],
        "rows": rows, "headlines": headlines[:12], "gaps": snap.get("gaps", []),
        "provenance": {"source_id": "yahoo-market-context", "retrieved_at": _now(),
                       "notes": "ETF prices are proxies (not index levels, spot prices or fund flows). "
                                "VIX is an equity implied-volatility index, not a credit measure. "
                                "% changes are computed from daily closes in the window."},
    }


def get_peer_candidates(ticker: str) -> dict[str, Any]:
    """Unverified peer candidates: Yahoo related symbols plus the target's sector/industry. The agent must
    verify business similarity and drop irrelevant names before comparing."""
    ticker = _ticker(ticker)
    url = f"https://query2.finance.yahoo.com/v6/finance/recommendationsbysymbol/{ticker}"
    raw = data_tools._yahoo_get(url, {})
    try:
        related = [x["symbol"] for x in json.loads(raw)["finance"]["result"][0]["recommendedSymbols"]]
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise DataToolError("YAHOO_RELATED_INVALID") from exc
    return {"ticker": ticker, "candidates": related,
            "provenance": {"source_id": f"yahoo-related:{ticker}", "source_locator": url, "retrieved_at": _now(),
                           "notes": "Yahoo 'people also watch' style list: popularity-based, often includes "
                                    "unrelated names. Use get_peer_snapshot to check sector/industry and choose "
                                    "2-3 (max 5) peers with a stated reason."}}


PEER_FIELDS = (
    ("sector", "assetProfile", "sector"), ("industry", "assetProfile", "industry"),
    ("currency", "price", "currency"), ("price", "price", "regularMarketPrice"),
    ("market_cap", "price", "marketCap"), ("trailing_pe", "summaryDetail", "trailingPE"),
    ("forward_pe", "summaryDetail", "forwardPE"), ("ev_to_revenue", "defaultKeyStatistics", "enterpriseToRevenue"),
    ("ev_to_ebitda", "defaultKeyStatistics", "enterpriseToEbitda"), ("price_to_book", "defaultKeyStatistics", "priceToBook"),
    ("revenue_growth", "financialData", "revenueGrowth"), ("gross_margin", "financialData", "grossMargins"),
    ("operating_margin", "financialData", "operatingMargins"), ("profit_margin", "financialData", "profitMargins"),
    ("roe", "financialData", "returnOnEquity"), ("debt_to_equity", "financialData", "debtToEquity"),
    ("change_52w", "defaultKeyStatistics", "52WeekChange"),
)


def get_peer_snapshot(tickers: list[str]) -> dict[str, Any]:
    """Provider-reported key statistics for up to 6 tickers side by side (Yahoo, current snapshot)."""
    symbols = [_ticker(t) for t in tickers][:6]
    if not symbols:
        raise DataToolError("TICKERS_REQUIRED")
    modules = "assetProfile,price,summaryDetail,defaultKeyStatistics,financialData"
    rows, errors = [], {}
    for symbol in symbols:
        try:
            raw = data_tools._yahoo_get(data_tools.YAHOO_SUMMARY.format(ticker=symbol), {"modules": modules},
                                        crumb=True)
            result = json.loads(raw)["quoteSummary"]["result"][0]
            rows.append([symbol] + [_num(_raw(result.get(module, {}).get(field)), 4)
                                    if not isinstance(_raw(result.get(module, {}).get(field)), str)
                                    else _raw(result.get(module, {}).get(field))
                                    for _, module, field in PEER_FIELDS])
        except Exception as exc:  # noqa: BLE001 - per-ticker failure is reported, others continue
            errors[symbol] = f"{type(exc).__name__}: {exc}"
    return {"columns": ["ticker"] + [name for name, _, _ in PEER_FIELDS], "rows": rows, "errors": errors,
            "provenance": {"source_id": "yahoo-quote-summary", "retrieved_at": _now(),
                           "notes": "PROVIDER_REPORTED current values (Yahoo definitions; TTM unless noted; ratios as "
                                    "decimals, 0.25 = 25%). Not point-in-time. For accounting-consistent comparison "
                                    "use get_financial_statements on each peer."}}
