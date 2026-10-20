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

from product.deterministic.signal_events import (EVENT_HORIZONS, FORM_8K_ITEMS, FUNDAMENTAL_SIGNALS, HORIZONS,
                                                TECHNICAL_SIGNALS)
from product.mcp import settings
from product.mcp.data_tools import NEW_YORK, DataToolError, _cutoff
from product.mcp.provenance import iso_utc

CASES_DIR = Path(__file__).resolve().parents[1] / "references" / "cases"
ROUND_TRIP_COST_PCT = 0.2  # 10bp each side
MIN_EVENTS = 30
_EVENTS: dict[str, dict[str, Any]] = {}
EVENT_FILES = {"main": ("events.jsonl", "meta.json", "scripts/build-signal-events.py"),
               "8k": ("events-8k.jsonl", "meta-8k.json", "scripts/build-8k-events.py")}


def _events(kind: str = "main") -> tuple[list[dict], dict]:
    root = settings.cache().root / "derived" / "signals"
    name, meta_name, script = EVENT_FILES[kind]
    path = root / name
    if not path.exists():
        raise DataToolError(f"SIGNAL_EVENTS_NOT_BUILT: run {script}")
    mtime = path.stat().st_mtime
    cached = _EVENTS.setdefault(kind, {})
    if cached.get("mtime") != mtime:
        cached.update(mtime=mtime, rows=[json.loads(line) for line in path.open()],
                      meta=json.loads((root / meta_name).read_text()))
    return cached["rows"], cached["meta"]


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
    from product.deterministic import signal_stats
    signals = {**TECHNICAL_SIGNALS, **FUNDAMENTAL_SIGNALS,
               **{f"8k_item_{k}": f"8-K 事项 {k}：{v}" for k, v in FORM_8K_ITEMS.items()}}
    if signal not in signals or signal.startswith("baseline"):
        raise DataToolError(f"SIGNAL_UNKNOWN: one of {sorted(k for k in signals if not k.startswith('baseline'))}")
    is_8k = signal.startswith("8k_item_")
    horizons = EVENT_HORIZONS if is_8k else HORIZONS
    if horizon_days not in horizons:
        raise DataToolError(f"HORIZON_INVALID: one of {list(horizons)}")
    cutoff = _cutoff(as_of).astimezone(NEW_YORK).date().isoformat()  # New York trading date
    rows, meta = _events("8k" if is_8k else "main")
    control = "baseline_days_daily" if is_8k else "baseline_days"
    h = str(horizon_days)

    def known(name: str) -> list[dict]:
        # Only samples whose whole outcome window ended before the cutoff.
        return [e for e in rows if e["signal"] == name and e["exit_dates"].get(h) and e["exit_dates"][h] < cutoff
                and e["excess"].get(h) is not None]
    hits = signal_stats.matched(known(signal), known(control), h)
    for e in hits:
        e["excess_h"] = e["excess"][h]
    summary = signal_stats.summarize(hits, ROUND_TRIP_COST_PCT)
    by_year = {}
    for year in sorted({e["entry_date"][:4] for e in hits}):
        group = [e for e in hits if e["entry_date"][:4] == year]
        by_year[year] = {"n": len(group),
                         "mean_vs_matched_control_pp": round(statistics.mean(e["abnormal"] for e in group) * 100, 2)}
    cis = [summary.get("ci95_cluster_by_ticker_pp"), summary.get("ci95_cluster_by_month_pp")]
    if summary["n"] < MIN_EVENTS or None in cis:
        status = "需要验证"
    elif all(lo > 0 for lo, _ in cis):
        status = "高于同日对照（两种置信区间都在 0 以上）"
    elif all(hi < 0 for _, hi in cis):
        status = "低于同日对照（两种置信区间都在 0 以下）"
    else:
        status = "与同日对照无可靠差异"
    return {
        "signal": signal, "definition": signals[signal], "horizon_days": horizon_days, "as_of": cutoff,
        "definitions_version": signal_stats.SIGNAL_DEFINITIONS_VERSION, "status": status, "summary": summary,
        "by_year_vs_matched_control": by_year,
        "provenance": {"source_id": "signal-events", "built_at": meta.get("built_at"),
                       "notes": "Excess return vs the stock's sector ETF from the close of the session after the "
                                "signal, before costs; mean_excess_after_cost_pct subtracts a 0.2pp round trip. "
                                "mean_vs_matched_control_pp compares with the whole universe's average excess on the "
                                "same date. 95% intervals from cluster bootstraps by ticker (repeat signals) and by "
                                "month (overlapping windows). Only samples whose outcome window ended before as_of. "
                                + meta.get("universe_note", "")},
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
