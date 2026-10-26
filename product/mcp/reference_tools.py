"""Shared reference tools: signal statistics and historical cases, both filtered to what was known at as_of.

Signal statistics come from the event tables built by scripts/build-*-events.py; a sample counts only if
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
LONG_HORIZONS = (5, 20, 60, 126, 252)  # PEAD / insider / congress tables
_EVENTS: dict[str, dict[str, Any]] = {}
EVENT_FILES = {"main": ("events.jsonl", "meta.json", "scripts/build-signal-events.py"),
               "8k": ("events-8k.jsonl", "meta-8k.json", "scripts/build-8k-events.py"),
               "pead": ("events-pead.jsonl", "meta-pead.json", "scripts/build-pead-events.py"),
               "insider": ("events-insider.jsonl", "meta-insider.json", "scripts/build-insider-events.py"),
               "congress": ("events-congress.jsonl", "meta-congress.json", "scripts/build-congress-events.py")}
CONTROL_SIGNAL = {"main": "baseline_days", "8k": "baseline_days_daily"}
PEAD_BUCKETS = {
    "strong_up": "大涨 >+5%", "up": "小涨 +2%～+5%", "flat": "持平 ±2%", "down": "小跌 −5%～−2%",
    "strong_down": "大跌 <−5%"}
PEAD_SIGNALS = {
    **{f"pead_{b}": f"财报后漂移：8-K 2.02 财报公告反应{label}（公告前收盘到入场收盘的板块超额涨跌），"
                    "入场在反应可见后的收盘；对照为同日全股票池每日对照行" for b, label in PEAD_BUCKETS.items()},
    "pead_strong_up_high_volume": "财报后漂移：反应大涨 >+5% 且公告日成交量放大 ≥2 倍",
    "pead_strong_down_high_volume": "财报后漂移：反应大跌 <−5% 且公告日成交量放大 ≥2 倍"}
INSIDER_SIGNALS = {
    "insider_buy": "任一内部人公开市场买入（Form 4 交易代码 P），申报日次一交易日收盘入场",
    "insider_buy_large": "单次申报买入金额 ≥ $100k",
    "insider_buy_officer": "CEO/CFO/总裁/首席执行或财务官买入",
    "insider_buy_cluster": "30 天内 ≥2 位不同内部人公开市场买入（在第二位申报日触发）",
    "insider_sell_cluster": "30 天内 ≥3 位不同内部人公开市场卖出且不属于 10b5-1 计划（计划标记 2023 年起才有）"}
CONGRESS_SIGNALS = {
    "congress_buy": "众议院议员买入（申报日次一交易日收盘入场）",
    "congress_buy_skilled": "高胜率议员买入：申报日之前已走完 252 日的历史买入至少 10 笔、胜率 ≥55%、中位超额 >0",
    "congress_buy_large": "议员买入，金额下限 ≥ $50,001",
    "congress_buy_cluster": "30 天内 ≥2 位不同议员买入（在第二位申报日触发）",
    "congress_sell": "众议院议员卖出"}


def _flat_row(r: dict) -> dict:
    """Normalise rows with flat '5','20',... / 'exit_5',... fields to the excess/exit_dates layout."""
    hs = [h for h in map(str, LONG_HORIZONS) if h in r]
    return {**{k: v for k, v in r.items() if k not in hs and not k.startswith("exit_")},
            "excess": {h: r[h] for h in hs}, "exit_dates": {h: r.get(f"exit_{h}") for h in hs}}


def _controls_of(rows: list[dict]) -> dict[str, dict[str, tuple[list[float], str]]]:
    """horizon -> entry_date -> (sorted control values, latest exit date), built once per load."""
    acc: dict[str, dict[str, list]] = {}
    for r in rows:
        for h, x in r["excess"].items():
            exit_date = r["exit_dates"].get(h)
            if x is None or not exit_date:
                continue
            slot = acc.setdefault(h, {}).setdefault(r["entry_date"], [[], ""])
            slot[0].append(x)
            slot[1] = max(slot[1], exit_date)
    return {h: {d: (sorted(v[0]), v[1]) for d, v in by_date.items()} for h, by_date in acc.items()}


def _events(kind: str = "main") -> tuple[dict[str, list[dict]], dict, dict]:
    """(events by signal, control pools, meta) for one event table, cached by file mtime.

    Event rows have `excess` / `exit_dates` dicts keyed by horizon; control pools are
    {horizon: {entry_date: (sorted values, latest exit date)}}. The insider and congress tables have no controls
    of their own: get_signal_stats uses the daily control rows stored in the PEAD table."""
    root = settings.cache().root / "derived" / "signals"
    name, meta_name, script = EVENT_FILES[kind]
    path = root / name
    if not path.exists():
        raise DataToolError(f"SIGNAL_EVENTS_NOT_BUILT: run {script}")
    mtime = path.stat().st_mtime
    cached = _EVENTS.setdefault(kind, {})
    if cached.get("mtime") != mtime:
        by_signal: dict[str, list[dict]] = {}
        controls: list[dict] = []
        with path.open() as f:
            for line in f:
                r = json.loads(line)
                if kind in ("main", "8k"):
                    if r["signal"] == CONTROL_SIGNAL[kind]:
                        controls.append(r)
                    else:
                        by_signal.setdefault(r["signal"], []).append(r)
                elif kind == "pead":
                    r = _flat_row(r)
                    if r["kind"] == "control":
                        controls.append({"entry_date": r["entry_date"], "excess": r["excess"],
                                         "exit_dates": r["exit_dates"]})
                        continue
                    big = r["bucket"] in ("strong_up", "strong_down") and (r.get("volume_ratio") or 0) >= 2
                    for sig in (f"pead_{r['bucket']}",) + ((f"pead_{r['bucket']}_high_volume",) if big else ()):
                        by_signal.setdefault(sig, []).append(r)
                else:
                    by_signal.setdefault(r["signal"], []).append(_flat_row(r))
        if kind in ("main", "8k"):
            controls = [{"entry_date": c["entry_date"], "excess": c["excess"], "exit_dates": c["exit_dates"]}
                        for c in controls]
        cached.update(mtime=mtime, events=by_signal, controls=_controls_of(controls),
                      meta=json.loads((root / meta_name).read_text()))
    return cached["events"], cached["controls"], cached["meta"]


def _signal_catalog() -> dict[str, tuple[str, str, tuple[int, ...]]]:
    """signal -> (definition, event table kind, horizons)."""
    out = {}
    for k, v in {**TECHNICAL_SIGNALS, **FUNDAMENTAL_SIGNALS}.items():
        if not k.startswith("baseline"):
            out[k] = (v, "main", HORIZONS)
    for k, v in FORM_8K_ITEMS.items():
        out[f"8k_item_{k}"] = (f"8-K 事项 {k}：{v}", "8k", EVENT_HORIZONS)
    for kind, table in (("pead", PEAD_SIGNALS), ("insider", INSIDER_SIGNALS), ("congress", CONGRESS_SIGNALS)):
        for k, v in table.items():
            out[k] = (v, kind, LONG_HORIZONS)
    return out


def get_signal_stats(signal: str, horizon_days: int = 60, as_of: str | None = None) -> dict[str, Any]:
    from product.deterministic import signal_stats
    catalog = _signal_catalog()
    if signal not in catalog:
        raise DataToolError(f"SIGNAL_UNKNOWN: one of {sorted(catalog)}")
    definition, kind, horizons = catalog[signal]
    if horizon_days not in horizons:
        raise DataToolError(f"HORIZON_INVALID: one of {list(horizons)}")
    cutoff = _cutoff(as_of).astimezone(NEW_YORK).date().isoformat()  # New York trading date
    events, controls, meta = _events(kind)
    if kind in ("insider", "congress"):
        _, controls, _ = _events("pead")  # daily control rows live in the PEAD table
    h = str(horizon_days)
    # Only samples whose whole outcome window ended before the cutoff.
    pools = {d: v for d, (v, last_exit) in controls.get(h, {}).items() if last_exit < cutoff}
    known = [e for e in events.get(signal, []) if e["exit_dates"].get(h) and e["exit_dates"][h] < cutoff
             and e["excess"].get(h) is not None]
    hits = signal_stats.matched(known, pools, h)
    summary = signal_stats.summarize(hits, ROUND_TRIP_COST_PCT)
    by_year = {}
    for year in sorted({e["entry_date"][:4] for e in hits}):
        group = [e for e in hits if e["entry_date"][:4] == year]
        by_year[year] = {"n": len(group),
                         "mean_percentile_minus_50": round(statistics.mean(e["pct_minus_50"] for e in group) * 100, 2)}
    cis = [summary.get("ci95_cluster_by_ticker_pts"), summary.get("ci95_cluster_by_month_pts")]
    if summary["n"] < MIN_EVENTS or None in cis:
        status = "需要验证"
    elif all(lo > 0 for lo, _ in cis):
        status = "高于对照（平均百分位高于 50，两种置信区间都在 0 以上）"
    elif all(hi < 0 for _, hi in cis):
        status = "低于对照（平均百分位低于 50，两种置信区间都在 0 以下）"
    else:
        status = "与对照无可靠差异"
    return {
        "signal": signal, "definition": definition, "horizon_days": horizon_days, "as_of": cutoff,
        "definitions_version": signal_stats.SIGNAL_DEFINITIONS_VERSION, "status": status, "summary": summary,
        "by_year_percentile_minus_50": by_year,
        "provenance": {"source_id": "signal-events", "built_at": meta.get("built_at"),
                       "notes": "Excess return vs the stock's sector ETF from the first tradable close after the "
                                "signal, before costs; mean_excess_after_cost_pct subtracts a 0.2pp round trip. "
                                "mean_percentile_minus_50 is the event's mid-rank percentile inside the whole "
                                "universe's control excess returns on the same entry date, minus 50 (percentile "
                                "points; 0 = no better than a random stock that day), robust to extreme winners. "
                                "95% intervals from cluster bootstraps by ticker (repeat signals) and by month "
                                "(overlapping windows); reliable only if both exclude 0. Only samples whose "
                                "outcome window ended before as_of. " + meta.get("universe_note", "")},
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
