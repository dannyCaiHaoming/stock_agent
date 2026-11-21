"""classify_decision_event: which decision event group (E2 / E1 / E0) a stock is in at as_of (protocol v1 §2)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, time as dtime, timedelta
from typing import Any

from product.deterministic import decision_events as de
from product.deterministic import key_moments as km
from product.mcp import data_tools, settings
from product.mcp.data_tools import NEW_YORK, DataToolError, _cutoff
from product.mcp.provenance import iso_utc, parse_timestamp

FILINGS_LIMIT = 40  # 8-Ks, newest first; a 3-session lookback needs far fewer
MAX_LOOKBACK = 20


def _benchmark(ticker: str) -> str:
    """Sector ETF from signals meta.json (same read as scripts/sample-idiosyncratic-moments.py), else no_sector."""
    path = settings.cache().root / "derived" / "signals" / "meta.json"
    mapping = json.loads(path.read_text(encoding="utf-8")).get("benchmarks", {}) if path.exists() else {}
    return mapping.get(ticker) or de.NO_SECTOR


def _closes(ticker: str, start: str, end: str, as_of: str | None, last_complete: str) -> tuple[dict[str, float], dict]:
    """Adjusted closes by date up to the last completed session on or before as_of, plus the price provenance."""
    result = data_tools.get_price_history(ticker, start=start, end=end, as_of=as_of, max_rows=1200)
    return ({r[0]: float(r[5] or r[4]) for r in result["rows"] if (r[5] or r[4]) and r[0] <= last_complete},
            result["provenance"])


def classify_decision_event(ticker: str, as_of: str | None = None, lookback_sessions: int = 3) -> dict[str, Any]:
    """Decision event group for `ticker` as of the last completed session on or before as_of.

    E2 = key moment with 5-session deviation vs the sector ETF |z| >= 2 (60 sessions); E1 = earnings 8-K (2.02)
    whose D0 excess vs the sector ETF < -5% (20 sessions), only D0-close data used; both -> E2 with overlap;
    otherwise E0 (60 sessions). Window = the last `lookback_sessions` sessions including the as_of session.
    """
    ticker = data_tools._ticker(ticker).replace(".", "-")
    if not 1 <= int(lookback_sessions) <= MAX_LOOKBACK:
        raise DataToolError(f"LOOKBACK_INVALID: 1-{MAX_LOOKBACK} sessions")
    cutoff = _cutoff(as_of)
    cutoff_ny = cutoff.astimezone(NEW_YORK)
    # a session's close is only known after 16:00 New York
    last_day = cutoff_ny.date() if cutoff_ny.time() >= dtime(16, 0) else cutoff_ny.date() - timedelta(days=1)
    last_complete, end = last_day.isoformat(), cutoff_ny.date().isoformat()
    start = str(int(end[:4]) - 3) + end[4:]
    benchmark = _benchmark(ticker)
    closes, price_prov = _closes(ticker, start, end, as_of, last_complete)
    dates = sorted(closes)
    if len(dates) < 2:
        raise DataToolError("HISTORY_TOO_SHORT: needs prices")
    e2_available = len(dates) > km.MIN_HISTORY  # key moments need about 260 sessions; E1 does not
    inputs = [price_prov]
    bench = None
    if benchmark != de.NO_SECTOR:
        bench, bench_prov = _closes(benchmark, start, end, as_of, last_complete)
        inputs.append(bench_prov)
    moments = km.detect(dates, [closes[d] for d in dates]) if e2_available else []
    filings = data_tools.list_filings(ticker, forms=["8-K"], limit=FILINGS_LIMIT, as_of=as_of)
    inputs.append(filings["provenance"])
    earnings = [{"accession": row[0],
                 "accepted_ny": parse_timestamp(row[3]).astimezone(NEW_YORK).strftime("%Y-%m-%dT%H:%M")}
                for row in filings["rows"] if "2.02" in (row[5] or "").split(",")]
    out = de.classify(dates, closes, bench, moments, earnings, lookback_sessions=int(lookback_sessions))
    return {
        "ticker": ticker, "as_of": dates[-1], "benchmark": benchmark, "lookback_sessions": int(lookback_sessions),
        "history_sessions": len(dates), "e2_available": e2_available,
        **out,
        "provenance": {
            "source_id": "decision-events-v1", "as_of": dates[-1], "retrieved_at": iso_utc(datetime.now(UTC)),
            "inputs": [{k: p.get(k) for k in ("source_id", "as_of", "retrieved_at")} for p in inputs],
            "notes": "Protocol v1 section 2. E2 = key_moments.detect moment with |5-session deviation vs sector ETF "
                     "in daily vol| >= 2; E1 = Item 2.02 8-K with D0 excess vs sector ETF < -5% (D0 per EDGAR "
                     "acceptance time), only data up to D0 close; both -> E2, overlap flagged. No sector mapping "
                     "-> benchmark no_sector, neither E2 nor E1. e2_available = false when the history is too short for key "
                     "moments (E1 and E0 still work). late_sessions = sessions from the event date to "
                     "as_of. horizon_days is fixed by group, not chosen.",
        },
    }
