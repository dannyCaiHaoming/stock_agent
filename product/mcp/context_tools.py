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

BLS_SERIES = {"cpi_all_items": "CUUR0000SA0", "cpi_core": "CUUR0000SA0L1E",
              "unemployment_rate": "LNS14000000", "nonfarm_payrolls_thousands": "CES0000000001"}
# Conservative release lags (BLS publishes month M data in month M+1): Employment Situation on the first
# Friday (by day 7), CPI around mid-month. Data for month M counts as known only from these days of M+1.
BLS_RELEASE_DAY = {"cpi_all_items": 16, "cpi_core": 16, "unemployment_rate": 8, "nonfarm_payrolls_thousands": 8}
# BLS data via FRED's public CSV (no API key or daily quota; current revised values, not vintages).
FRED_SERIES = {"cpi_all_items": "CPIAUCNS", "cpi_core": "CPILFENS", "unemployment_rate": "UNRATE",
               "nonfarm_payrolls_thousands": "PAYEMS"}
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
TREASURY_CSV = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
                "{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&_format=csv")
FOMC_CALENDAR = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
FOMC_STATEMENT = "https://www.federalreserve.gov/newsevents/pressreleases/monetary{day}a.htm"
BLS_CALENDAR = "https://www.bls.gov/schedule/news_release/bls.ics"
HEADERS = {"User-Agent": "stock-agent-readonly/1.0"}


def _now() -> str:
    return iso_utc(datetime.now(UTC))


def _snapshot_path(kind: str) -> Path:
    directory = settings.data_dir() / "snapshots"
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{kind}-{datetime.now(UTC).strftime('%Y%m%dT%H%M%S%fZ')}.json"


def _pct(new: Decimal, old: Decimal) -> str | None:
    return None if old == 0 else format(round((new / old - 1) * 100, 2), "f")


def _fetch(key: dict, request: Request, *, final: bool, valid=lambda raw: True) -> tuple[bytes, dict]:
    """Cached GET/POST. `final` responses (closed past periods) are reused forever; others for the same day.
    Responses failing `valid` are not cached."""
    cache: SnapshotCache = settings.cache()
    key = {**key, "fetched_on": "final" if final else datetime.now(UTC).date().isoformat()}
    record = cache.lookup(key)
    if record is None:
        response = macro._http(request)
        if response.status != 200:
            raise DataToolError(f"HTTP_{response.status}")
        if not valid(response.body):
            return response.body, {"retrieved_at": _now()}
        record = cache.store(key, response.body, retrieved_at=_now())
    return cache.read(record), record


def _treasury(cutoff: datetime) -> dict[str, Any]:
    """Daily Treasury par yields up to the cutoff (Treasury does not revise these)."""
    import csv
    from io import StringIO
    day = cutoff.astimezone(data_tools.NEW_YORK).date()
    rows = []
    for year in sorted({day.year - 1, day.year}):
        url = TREASURY_CSV.format(year=year)
        raw, _ = _fetch({"provider": "treasury-yield-csv", "year": year},
                        Request(url, headers={**HEADERS, "Accept": "text/csv"}), final=year < datetime.now(UTC).year)
        for row in csv.DictReader(StringIO(raw.decode("utf-8-sig"))):
            d = datetime.strptime(row["Date"], "%m/%d/%Y").date()
            if d <= day:
                rows.append((d, {k: row.get(k) for k in ("3 Mo", "2 Yr", "10 Yr", "30 Yr")}))
    rows.sort()
    if not rows:
        raise DataToolError("TREASURY_NO_ROWS_BEFORE_CUTOFF")

    def at(back: int) -> tuple:
        return rows[max(0, len(rows) - 1 - back)]
    table = []
    for label, back in (("latest", 0), ("20_sessions_earlier", 20), ("60_sessions_earlier", 60), ("250_sessions_earlier", 250)):
        d, r = at(back)
        ten, two = r.get("10 Yr"), r.get("2 Yr")
        spread = format(Decimal(ten) - Decimal(two), "f") if ten and two else None
        table.append([label, d.isoformat(), r.get("3 Mo"), r.get("2 Yr"), ten, r.get("30 Yr"), spread])
    return {"columns": ["point", "date", "3m", "2y", "10y", "30y", "10y_minus_2y"], "rows": table,
            "unit": "percent", "source_id": "us-treasury-daily-yield-curve", "source_locator": TREASURY_CSV.format(year=day.year)}


def _bls(cutoff: datetime) -> dict[str, Any]:
    """BLS monthly series via FRED public CSV (no key, full history); only months released by the cutoff."""
    import csv
    from io import StringIO
    out = {}
    retrieved = None
    for name, fred_id in FRED_SERIES.items():
        url = FRED_CSV.format(series=fred_id)
        raw, record = _fetch({"provider": "fred-csv", "series": fred_id}, Request(url, headers=HEADERS), final=False,
                             valid=lambda body: body[:200].count(b",") > 0)
        retrieved = record["retrieved_at"]
        points = []
        for row in csv.reader(StringIO(raw.decode("utf-8-sig"))):
            if len(row) != 2 or not re.fullmatch(r"-?\d+(?:\.\d+)?", row[1].strip()):
                continue  # header and missing values (".")
            y, m = int(row[0][:4]), int(row[0][5:7])
            release = datetime(y + (m == 12), m % 12 + 1, BLS_RELEASE_DAY[name], 13, 0, tzinfo=UTC)
            if release <= cutoff:
                points.append((y, m, Decimal(row[1])))
        points.sort()
        by_month = {(y, m): v for y, m, v in points}
        rows = []
        for y, m, v in points[-6:]:
            prior_year = by_month.get((y - 1, m))
            prior_month = by_month.get((y, m - 1) if m > 1 else (y - 1, 12))
            if name.startswith("cpi"):
                rows.append([f"{y}-{m:02d}", format(v, "f"), _pct(v, prior_year) if prior_year else None])
            elif name == "nonfarm_payrolls_thousands":
                rows.append([f"{y}-{m:02d}", format(v, "f"), format(v - prior_month, "f") if prior_month else None])
            else:
                rows.append([f"{y}-{m:02d}", format(v, "f"), None])
        third = {"cpi": "yoy_percent", "non": "mom_change_thousands"}.get(name[:3], "-")
        out[name] = {"fred_series": fred_id, "bls_series": BLS_SERIES[name], "columns": ["month", "value", third],
                     "rows": rows, "source_locator": url}
    return {"series": out, "retrieved_at": retrieved,
            "release_rule": "month M counted as known from day 8 (jobs) / day 16 (CPI) of month M+1"}


def _fomc(cutoff: datetime) -> dict[str, Any]:
    """Latest FOMC statement released on or before the cutoff (statements are at 14:00 ET)."""
    raw, _ = _fetch({"provider": "fomc-calendar"}, Request(FOMC_CALENDAR, headers=HEADERS), final=False)
    days = sorted(set(re.findall(r"pressreleases/monetary(\d{8})a\.htm", raw.decode("utf-8", "replace"))))
    cutoff_day = cutoff.astimezone(data_tools.NEW_YORK)
    eligible = [d for d in days if datetime.strptime(d, "%Y%m%d").date() < cutoff_day.date()
                or (datetime.strptime(d, "%Y%m%d").date() == cutoff_day.date() and cutoff_day.hour >= 14)]
    if not eligible:
        raise DataToolError("FOMC_STATEMENT_NOT_FOUND_BEFORE_CUTOFF (calendar page covers about five years)")
    day = eligible[-1]
    url = FOMC_STATEMENT.format(day=day)
    page, _ = _fetch({"provider": "fomc-statement", "day": day}, Request(url, headers=HEADERS), final=True)
    text = " ".join(macro._visible_text(page).split())
    marker = re.search(r"For release at .{0,30}?(?:EDT|EST)(?: Share)?", text)
    start = marker.end() if marker else 0
    return {"date": f"{day[:4]}-{day[4:6]}-{day[6:]}", "source_locator": url, "excerpt": text[start:start + 1500],
            "previous_statements": [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in eligible[-4:-1]]}


def _bls_calendar(cutoff: datetime) -> list[list[str]]:
    # bls.gov rejects anonymous clients; it asks for contact details in the User-Agent.
    raw, record = _fetch({"provider": "bls-calendar"},
                         Request(BLS_CALENDAR, headers={"User-Agent": settings.sec_user_agent()}), final=False)
    try:
        events = macro.normalize_bls_calendar_ics(raw, retrieved_at=record["retrieved_at"], endpoint=BLS_CALENDAR,
                                                  decision_cutoff=iso_utc(cutoff))["evidence"][0]["value"]
    except ValueError:
        return []
    out = []
    for event in json.loads(events):
        when = parse_timestamp(event["scheduled_at"])
        if cutoff <= when <= cutoff + timedelta(days=45):
            out.append([event["scheduled_at"], event["summary"]])
    return out[:20]


_MEMO: dict[tuple, tuple[datetime, dict]] = {}
MEMO_TTL = timedelta(minutes=30)


def _memo(kind: str, as_of: str | None, build):
    """Reuse a recent snapshot in this server process (both collectors make several HTTP requests)."""
    key = (kind, as_of)
    hit = _MEMO.get(key)
    if hit and datetime.now(UTC) - hit[0] < MEMO_TTL:
        return {**hit[1], "reused_from_memo_at": iso_utc(hit[0])}
    value = build()
    _MEMO[key] = (datetime.now(UTC), value)
    return value


def get_macro_snapshot(as_of: str | None = None) -> dict[str, Any]:
    """US rates, labor, inflation (YoY computed), latest FOMC statement and upcoming BLS releases."""
    return _memo("macro", as_of, lambda: _macro_snapshot(as_of))


def _macro_snapshot(as_of: str | None) -> dict[str, Any]:
    cutoff = _cutoff(as_of)
    result: dict[str, Any] = {"as_of": iso_utc(cutoff)}
    gaps = []
    for name, build in (("treasury_yields", _treasury), ("bls", _bls), ("fomc_latest_statement", _fomc),
                        ("upcoming_bls_releases_45d", _bls_calendar)):
        try:
            result[name] = build(cutoff)
        except Exception as exc:  # noqa: BLE001 - one source failing must not hide the others
            result[name] = None
            gaps.append({"source": name, "reason": f"{type(exc).__name__}: {exc}"[:300]})
    if as_of and result.get("upcoming_bls_releases_45d") == []:
        gaps.append({"source": "upcoming_bls_releases_45d", "reason": "BLS calendar only lists current/upcoming dates"})
    result["gaps"] = gaps
    result["provenance"] = {
        "sources": ["U.S. Treasury daily par yield curve CSV", "BLS series via FRED public CSV", "Federal Reserve FOMC statements",
                    "BLS release calendar"],
        "retrieved_at": _now(),
        "notes": "Treasury yields are not revised. BLS values are current revised values (payrolls revise "
                 "materially), shown only for months already released by the cutoff. FOMC statement is the latest "
                 "one released by the cutoff."}
    return result


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
