"""Shared reference tools: signal statistics and historical cases, both filtered to what was known at as_of.

Signal statistics come from the event table built by scripts/build-signal-events.py; a sample counts only if
its outcome window ended before the cutoff. Cases are product/references/cases/*.md with front matter;
a case is returned only if its outcome was known (outcome_known_at) before the cutoff.
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path
from typing import Any

from product.deterministic.signal_events import FUNDAMENTAL_SIGNALS, HORIZONS, TECHNICAL_SIGNALS
from product.mcp import settings
from product.mcp.data_tools import NEW_YORK, DataToolError, _cutoff
from product.mcp.provenance import iso_utc

CASES_DIR = Path(__file__).resolve().parents[1] / "references" / "cases"
ROUND_TRIP_COST_PCT = 0.2  # 10bp each side
MIN_EVENTS = 30
_EVENTS: dict[str, Any] = {}


def _events() -> tuple[list[dict], dict]:
    root = settings.cache().root / "derived" / "signals"
    path = root / "events.jsonl"
    if not path.exists():
        raise DataToolError("SIGNAL_EVENTS_NOT_BUILT: run scripts/build-signal-events.py")
    mtime = path.stat().st_mtime
    if _EVENTS.get("mtime") != mtime:
        _EVENTS.update(mtime=mtime, rows=[json.loads(line) for line in path.open()],
                       meta=json.loads((root / "meta.json").read_text()))
    return _EVENTS["rows"], _EVENTS["meta"]


def _summary(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"n": 0}
    pct = sorted(v * 100 for v in values)

    def q(p: float) -> float:
        return round(pct[min(len(pct) - 1, int(p * (len(pct) - 1)))], 2)
    return {"n": len(values), "mean_pct": round(statistics.mean(pct), 2), "median_pct": q(0.5),
            "hit_rate": round(sum(v > 0 for v in pct) / len(pct), 3), "p10_pct": q(0.1), "p25_pct": q(0.25),
            "p75_pct": q(0.75), "p90_pct": q(0.9)}


def get_signal_stats(signal: str, horizon_days: int = 60, as_of: str | None = None) -> dict[str, Any]:
    signals = {**TECHNICAL_SIGNALS, **FUNDAMENTAL_SIGNALS}
    if signal not in signals:
        raise DataToolError(f"SIGNAL_UNKNOWN: one of {sorted(signals)}")
    if horizon_days not in HORIZONS:
        raise DataToolError(f"HORIZON_INVALID: one of {list(HORIZONS)}")
    cutoff = _cutoff(as_of).astimezone(NEW_YORK).date().isoformat()  # New York trading date
    rows, meta = _events()
    h = str(horizon_days)
    baseline = "baseline_days" if signal in TECHNICAL_SIGNALS else "baseline_filings"

    def known(name: str) -> list[dict]:
        # Only samples whose whole outcome window ended before the cutoff.
        return [e for e in rows if e["signal"] == name and e["exit_dates"].get(h) and e["exit_dates"][h] < cutoff
                and e["excess"].get(h) is not None]
    hits, base = known(signal), known(baseline)
    values = [e["excess"][h] for e in hits]
    by_year: dict[str, list[float]] = {}
    for e in hits:
        by_year.setdefault(e["signal_date"][:4], []).append(e["excess"][h])
    summary, base_summary = _summary(values), _summary([e["excess"][h] for e in base])
    status = "需要验证" if summary["n"] < MIN_EVENTS else "可参考"
    return {
        "signal": signal, "definition": signals[signal], "horizon_days": horizon_days, "as_of": cutoff,
        "status": status, "events": summary, "distinct_tickers": len({e["ticker"] for e in hits}),
        "baseline": {"signal": baseline, **base_summary},
        "mean_minus_baseline_pct": round(summary["mean_pct"] - base_summary["mean_pct"], 2)
        if summary["n"] and base_summary["n"] else None,
        "mean_after_round_trip_cost_pct": round(summary["mean_pct"] - ROUND_TRIP_COST_PCT, 2) if summary["n"] else None,
        "by_year": {y: _summary(v) for y, v in sorted(by_year.items())},
        "provenance": {"source_id": "signal-events", "built_at": meta.get("built_at"),
                       "notes": "Excess return vs the stock's sector ETF from the close of the session after the "
                                "signal. Only samples whose outcome window ended before as_of. Overlapping windows "
                                "across tickers and dates are not independent. " + meta.get("universe_note", "")
                                + f" status=需要验证 when fewer than {MIN_EVENTS} events."},
    }


def _front_matter(text: str) -> tuple[dict[str, Any], str]:
    match = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not match:
        return {}, text
    meta = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            value = value.strip()
            meta[key.strip()] = [v.strip() for v in value.strip("[]").split(",") if v.strip()] \
                if value.startswith("[") else value
    return meta, match.group(2)


def get_reference_cases(method: str | None = None, as_of: str | None = None) -> dict[str, Any]:
    cutoff = _cutoff(as_of).astimezone(NEW_YORK).date().isoformat()  # New York trading date
    cases, hidden = [], 0
    for path in sorted(CASES_DIR.glob("*.md")):
        meta, body = _front_matter(path.read_text())
        if method and method not in meta.get("methods", []):
            continue
        if not meta.get("outcome_known_at") or meta["outcome_known_at"] >= cutoff:
            hidden += 1  # outcome not yet known at the cutoff
            continue
        cases.append({"id": meta.get("id", path.stem), "ticker": meta.get("ticker"), "case_date": meta.get("case_date"),
                      "methods": meta.get("methods", []), "result": meta.get("result"), "text": body.strip()})
    return {"as_of": cutoff, "method": method, "cases": cases, "hidden_not_yet_known": hidden,
            "provenance": {"source_id": "reference-cases", "source_locator": str(CASES_DIR),
                           "notes": "Cases explain mechanisms (why a method worked or failed); they are not statistics. "
                                    "Only cases whose outcome was known before as_of are returned."},
            "retrieved_at": iso_utc(__import__("datetime").datetime.now(__import__("datetime").UTC))}
