"""Decision ledger scoring (pure math, no network): fill, window return, action gain, baselines, block bootstrap,
verdict and funnel. Rules: evals/forward/decision-protocol-v1.md §3–§6; records: decision/v2 (product/mcp/decision_ledger.py).

Units: returns, Δ and costs are in percentage points per one standard position (= 100). Prices are lists aligned to
one trading calendar (`Prices.dates`, ascending ISO dates); a missing price is None or NaN.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any, Callable, Sequence
from zoneinfo import ZoneInfo

import numpy as np

NY = ZoneInfo("America/New_York")
SEED = 20261122
REPS = 10_000
COST_PER_LEG_PP = 0.2        # per unit of turnover, round trip, per leg (protocol §4)
MUE_PP = 0.20                # minimum useful edge (protocol §6)
LATE_SESSIONS = 3            # fill more than 3 sessions after event_date → late (protocol §3)
BLOCK_WEEKS = {"E2": 12, "E1": 4}
MIN_BLOCKS = 3               # interval usable only when W >= 3L
INTERIM_N = 100
FINAL_N = 255
FINAL_DATE = "2028-06-30"
MISSING_RATE_FLAG = 0.10
B1_Z = -2.0
REDUCE_FACTOR = 0.5          # REDUCE keeps half the position (protocol §4)
OPEN_NY = time(9, 30)


# ---------------------------------------------------------------- prices

@dataclass
class Prices:
    dates: list[str]
    open: list[float | None]
    close: list[float | None]
    adj: list[float | None]


def num(x: Any) -> float | None:
    """Price as float (get_price_history returns numeric strings); None when missing, NaN or not positive."""
    if x is None:
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def adj_open(open_: Any, close: Any, adj_close: Any) -> float | None:
    """Adjusted open = open × adj_close / close (same day); None if any of the three is missing."""
    o, c, a = num(open_), num(close), num(adj_close)
    return None if o is None or c is None or a is None else o * a / c


def align_prices(calendar: Sequence[str], rows: Sequence[Sequence[Any]] | None) -> Prices | None:
    """Place one series ([date, open, high, low, close, adj_close, volume] rows) on the independent trading calendar
    (SPY session dates, see scripts/score-decisions.py). A calendar day the series has no row for stays in the
    calendar with missing prices — it never disappears, so it cannot delay a fill or an exit (protocol §3).
    Rows on dates outside the calendar are ignored. `rows=None` (no series) returns None."""
    if rows is None:
        return None
    table = {r[0]: r for r in rows}
    cal = list(calendar)
    return Prices(cal,
                  [table[d][1] if d in table else None for d in cal],
                  [table[d][4] if d in table else None for d in cal],
                  [table[d][5] if d in table else None for d in cal])


# ---------------------------------------------------------------- fill and returns

def parse_utc(stamp: str | datetime) -> datetime:
    if isinstance(stamp, datetime):
        value = stamp
    else:
        value = datetime.fromisoformat(stamp.strip().replace("Z", "+00:00"))
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def entry_index(decided_at_utc: str | datetime, dates: Sequence[str]) -> int | None:
    """Calendar index of the first regular session open after `decided_at_utc` (before 09:30 New York → that day),
    or None when the calendar has no such session yet. Looks at the calendar only, never at prices."""
    ny = parse_utc(decided_at_utc).astimezone(NY)
    day = ny.date().isoformat()
    start = bisect_left(dates, day) if ny.time() < OPEN_NY else bisect_right(dates, day)
    return start if start < len(dates) else None


def matured(decided_at_utc: str | datetime, dates: Sequence[str], h: int) -> bool:
    """Has the h-day window (entry session = day 1) ended on the calendar? Independent of whether the fill or the
    prices are usable (protocol §6: an unmatured event is in neither part of the missing rate)."""
    i = entry_index(decided_at_utc, dates)
    return i is not None and i + h - 1 < len(dates)


def fill(decided_at_utc: str | datetime, dates: Sequence[str], opens: Sequence[Any], closes: Sequence[Any],
         adj_closes: Sequence[Any]) -> dict[str, Any]:
    """First regular session open after `decided_at_utc` (before 09:30 New York → that day's open).
    status: ok (index, date, adj_open) | not_fillable (open/close/adj_close missing that day, never replaced by
    the close) | pending (no later session in the calendar yet)."""
    start = entry_index(decided_at_utc, dates)
    if start is None:
        return {"status": "pending"}
    entry = adj_open(opens[start], closes[start], adj_closes[start])
    if entry is None:
        return {"status": "not_fillable", "index": start, "date": dates[start]}
    return {"status": "ok", "index": start, "date": dates[start], "adj_open": entry}


def window_return(opens: Sequence[Any], closes: Sequence[Any], adj_closes: Sequence[Any], entry_index: int,
                  h: int) -> float | None:
    """Percentage-point return from the entry day's adjusted open to the adjusted close of day h (entry day = day 1,
    so the exit index is entry_index + h − 1). None when the window is beyond the data or a price is missing."""
    j = entry_index + h - 1
    if j >= len(adj_closes) or entry_index < 0:
        return None
    entry = adj_open(opens[entry_index], closes[entry_index], adj_closes[entry_index])
    exit_price = num(adj_closes[j])
    if entry is None or exit_price is None:
        return None
    return (exit_price / entry - 1.0) * 100.0


def path_min(opens: Sequence[Any], closes: Sequence[Any], adj_closes: Sequence[Any], entry_index: int,
             h: int) -> float | None:
    """Lowest adjusted close over days 1..h relative to the entry adjusted open, in percentage points."""
    j = entry_index + h - 1
    if j >= len(adj_closes):
        return None
    entry = adj_open(opens[entry_index], closes[entry_index], adj_closes[entry_index])
    path = [v for v in (num(adj_closes[k]) for k in range(entry_index, j + 1)) if v is not None]
    if entry is None or not path:
        return None
    return (min(path) / entry - 1.0) * 100.0


def delta(w0: float, w1: float, r_stock: float, r_alt: float | None, dest: str) -> tuple[float, float]:
    """(Δ, cost) in percentage points, protocol §4: Δ = (w1 − w0)(R_stock − R_alt) − cost,
    cost = 0.2 × |w1 − w0| × legs (sector ETF: 2 legs, cash: 1 leg, R_alt = 0)."""
    if dest == "cash":
        r_alt, legs = 0.0, 1
    elif dest == "sector_etf":
        if r_alt is None:
            raise ValueError("sector_etf needs r_alt")
        legs = 2
    else:
        raise ValueError(f"unknown destination {dest!r}")
    move = w1 - w0
    cost = COST_PER_LEG_PP * abs(move) * legs
    return move * (r_stock - r_alt) - cost, cost


# ---------------------------------------------------------------- baselines

def baselines(record: dict[str, Any]) -> dict[str, float | None]:
    """w1 of B0 / B1 / B2 (protocol §5), same event and fill time. B0 holds; B1 (E2: z ≤ −2, E1: always)
    and B2 (explicit_guidance_cut) halve; otherwise hold. B1 is None when an E2 record has no deviation_z."""
    w0 = float(record["w0"])
    reduce_w, hold_w = REDUCE_FACTOR * w0, w0
    group = record.get("group")
    if group == "E1":
        b1: float | None = reduce_w
    elif group == "E2":
        z = (record.get("event") or {}).get("deviation_z")
        b1 = None if z is None else (reduce_w if z <= B1_Z else hold_w)
    else:
        b1 = hold_w
    cut = (record.get("attribution") or {}).get("explicit_guidance_cut") is True
    return {"B0": hold_w, "B1": b1, "B2": reduce_w if cut else hold_w}


# ---------------------------------------------------------------- one record

def fill_time(record: dict[str, Any]) -> str:
    """Replay records fill from decided_at_effective (just after 16:00 New York on the replay day)."""
    return record.get("decided_at_effective") or record["decided_at"]


def score_record(record: dict[str, Any], calendar: Sequence[str], stock: Prices | None,
                 bench: Prices | None) -> dict[str, Any]:
    """Status and Δ of one decision/v2 record. `calendar` is the independent session calendar; `stock` and `bench`
    are on it (see `align_prices`). `stock=None` means the stock's prices could not be fetched.
    status (checked in this order):
      pending        entry session or day-h session not yet on the calendar (maturity ignores prices)
      price_error    matured, but the stock series could not be fetched
      not_fillable   stock open/close/adj_close missing on the entry day
      unscorable     stock adj_close missing on day h (no basis scores)
      etf_unscorable ETF (or no ETF) missing at entry/exit; the cash basis is still scored
      late           scored, fill more than 3 sessions after event_date (not in the main sample)
      scored"""
    h = int(record["horizon_days"])
    w0, w1 = float(record["w0"]), float(record["w1"])
    out: dict[str, Any] = {"decision_id": record.get("decision_id"), "ticker": record.get("ticker"),
                           "group": record.get("group"), "source": record.get("source"),
                           "replay": bool(record.get("replay")), "action": record.get("action"),
                           "w0": w0, "w1": w1, "horizon_days": h, "status": "pending", "late": False}
    i = entry_index(fill_time(record), calendar)
    if i is None:
        return out
    out["fill_date"] = calendar[i]                      # known as soon as the entry session exists
    if i + h - 1 >= len(calendar):
        return out
    out["exit_date"] = calendar[i + h - 1]
    event_date = (record.get("event") or {}).get("event_date")
    if event_date:
        e = max(bisect_right(calendar, event_date) - 1, 0)
        out["late_sessions"] = i - e
        out["late"] = (i - e) > LATE_SESSIONS
    if stock is None:
        out["status"] = "price_error"
        return out
    if fill(fill_time(record), calendar, stock.open, stock.close, stock.adj)["status"] != "ok":
        out["status"] = "not_fillable"
        return out
    r_stock = window_return(stock.open, stock.close, stock.adj, i, h)
    if r_stock is None:
        out["status"] = "unscorable"
        return out
    r_etf = None
    if bench is not None:
        r_etf = window_return(bench.open, bench.close, bench.adj, i, h)
    out.update(r_stock=r_stock, r_etf=r_etf,
               path_min=path_min(stock.open, stock.close, stock.adj, i, h))
    base = baselines(record)
    out["w1_b1"], out["w1_b2"] = base["B1"], base["B2"]
    for tag, w in (("", w1), ("_b1", base["B1"]), ("_b2", base["B2"])):
        out[f"delta{tag}_cash"] = None if w is None else delta(w0, w, r_stock, None, "cash")[0]
        out[f"delta{tag}_etf"] = (None if w is None or r_etf is None
                                  else delta(w0, w, r_stock, r_etf, "sector_etf")[0])
    out["delta_cost_etf"] = None if r_etf is None else delta(w0, w1, r_stock, r_etf, "sector_etf")[1]
    out["delta_cost_cash"] = delta(w0, w1, r_stock, None, "cash")[1]
    if r_etf is None:
        out["status"] = "etf_unscorable"
    else:
        out["outperformed"] = r_stock > r_etf
        out["status"] = "late" if out["late"] else "scored"
    # Overlap with E1 (record carries E1 facts): keep a 20-day Δ as an auxiliary result (protocol §2).
    ev = record.get("event") or {}
    if record.get("group") == "E2" and h != 20 and (ev.get("accession") or ev.get("d0")):
        r20 = window_return(stock.open, stock.close, stock.adj, i, 20)
        b20 = window_return(bench.open, bench.close, bench.adj, i, 20) if bench is not None else None
        if r20 is not None:
            out["aux20_cash"] = delta(w0, w1, r20, None, "cash")[0]
            out["aux20_etf"] = None if b20 is None else delta(w0, w1, r20, b20, "sector_etf")[0]
    return out


# ---------------------------------------------------------------- block bootstrap

def week_index(day: str | date) -> int:
    """Consecutive Monday-start week number (ISO weeks, continuous across years)."""
    d = date.fromisoformat(day) if isinstance(day, str) else day
    return (d.toordinal() - 1) // 7


def block_bootstrap(events: Sequence[float], week_of: Sequence[int], L: int, reps: int = REPS,
                    seed: int = SEED, level: float = 0.90) -> tuple[float, float] | None:
    """Circular moving block bootstrap interval of the event-weighted mean (protocol §6).

    `events` are per-event values, `week_of` the parallel fill-week numbers (see `week_index`). Weeks run from the
    first to the last fill week (W weeks, empty weeks included); each replicate draws ceil(W/L) start weeks uniformly
    with replacement, takes L consecutive weeks from each (wrapping around), pools every event in the drawn weeks
    (repeats count repeatedly) and averages. Returns the (5th, 95th) percentile (numpy linear), or None when
    W < 3L. The draws depend only on (W, L, reps, seed), so two statistics over the same events share them."""
    if len(events) != len(week_of):
        raise ValueError("events and week_of must be parallel")
    if not events:
        return None
    first, last = min(week_of), max(week_of)
    W = last - first + 1
    if W < MIN_BLOCKS * L:
        return None
    sums = np.zeros(W)
    counts = np.zeros(W)
    for value, wk in zip(events, week_of):
        sums[wk - first] += float(value)
        counts[wk - first] += 1
    rng = np.random.default_rng(seed)
    k = -(-W // L)
    starts = rng.integers(0, W, size=(reps, k))
    idx = (starts[:, :, None] + np.arange(L)[None, None, :]) % W
    s = sums[idx].sum(axis=(1, 2))
    c = counts[idx].sum(axis=(1, 2))
    means = np.where(c > 0, s / np.where(c > 0, c, 1), np.nan)
    tail = (1.0 - level) / 2.0 * 100.0
    lo, hi = np.nanpercentile(means, [tail, 100.0 - tail])
    return float(lo), float(hi)


def verdict(ci_delta: tuple[float, float] | None, ci_diff: tuple[float, float] | None, mue: float = MUE_PP,
            interim: bool = False) -> str:
    """Protocol §6, first match wins (mutually exclusive):
    1 not_worth: upper bound of mean Δ < MUE;  2 supported: lower bound of mean Δ > 0 and of Δ − Δ_B1 > 0;
    3 insufficient: everything else, including an unusable interval. At the interim look only rule 1 may fire:
    returns stop_not_worth or continue (never "supported")."""
    if ci_delta is None:
        return "continue" if interim else "insufficient"
    if ci_delta[1] < mue:
        return "stop_not_worth" if interim else "not_worth"
    if interim:
        return "continue"
    if ci_delta[0] > 0 and ci_diff is not None and ci_diff[0] > 0:
        return "supported"
    return "insufficient"


def is_final(n_matured: int, as_of: str) -> bool:
    """Final analysis: 255 matured main-sample events, or the calendar has reached 2028-06-30 (protocol §6)."""
    return n_matured >= FINAL_N or as_of >= FINAL_DATE


def summarize(rows: Sequence[dict[str, Any]], key: str, L: int, key_b1: str | None = None) -> dict[str, Any]:
    """Event-weighted mean and block-bootstrap interval of rows[key]; with `key_b1`, also of the paired difference
    key - key_b1 (events that have a B1 value only)."""
    have = [r for r in rows if r.get(key) is not None]
    vals = [r[key] for r in have]
    weeks = [week_index(r["fill_date"]) for r in have]
    out: dict[str, Any] = {"n": len(vals), "mean": mean(vals),
                           "ci": block_bootstrap(vals, weeks, L) if vals else None}
    if key_b1:
        pairs = [r for r in have if r.get(key_b1) is not None]
        d = [r[key] - r[key_b1] for r in pairs]
        out["diff"] = {"n": len(d), "mean": mean(d),
                       "ci": block_bootstrap(d, [week_index(r["fill_date"]) for r in pairs], L) if d else None}
    return out


def interim_snapshot(scored: Sequence[dict[str, Any]], L: int, pending: Sequence[dict[str, Any]] = (),
                     n_min: int = INTERIM_N) -> dict[str, Any] | None:
    """The single interim look (protocol §6), taken on whole fill weeks so it cannot move between runs.

    Trigger week = the first fill week such that the main sample (matured events, weeks up to and including it) has
    at least n_min events and W (first main fill week .. this week, inclusive) >= 3L. Snapshot sample = every
    main-sample event with fill week <= trigger week. `pending` are decided events with a known fill date whose
    window has not ended; if any has a fill week <= the trigger week the look is not yet taken (state `pending`,
    no interval, no verdict). Once every event of those weeks has matured the state is `ready` and carries the
    interval and the verdict (`stop_not_worth` or `continue`; never "supported"); later runs, with more events,
    reproduce the same snapshot because only weeks <= trigger week enter it. Returns None before the trigger."""
    ordered = sorted(scored, key=lambda r: (r["fill_date"], r.get("decision_id") or ""))
    if not ordered:
        return None
    first_week = week_index(ordered[0]["fill_date"])
    per_week: dict[int, int] = {}
    for r in ordered:
        wk = week_index(r["fill_date"])
        per_week[wk] = per_week.get(wk, 0) + 1
    cum, trigger = 0, None
    for wk in sorted(per_week):
        cum += per_week[wk]
        if cum >= n_min and wk - first_week + 1 >= MIN_BLOCKS * L:
            trigger = wk
            break
    if trigger is None:
        return None
    sample = [r for r in ordered if week_index(r["fill_date"]) <= trigger]
    open_ = [r for r in pending if r.get("fill_date") and week_index(r["fill_date"]) <= trigger]
    monday = date.fromordinal(trigger * 7 + 1)
    base = {"trigger_week_start": monday.isoformat(), "n": len(sample), "W": trigger - first_week + 1,
            "cutoff_fill_date": sample[-1]["fill_date"], "n_pending": len(open_)}
    if open_:
        return {**base, "state": "pending"}
    st = summarize(sample, "delta_etf", L, "delta_b1_etf")
    return {**base, "state": "ready", "mean": st["mean"], "ci_delta": st["ci"], "diff_mean": st["diff"]["mean"],
            "ci_diff": st["diff"]["ci"], "verdict": verdict(st["ci"], st["diff"]["ci"], interim=True)}


def cap_sample(scored: list[dict[str, Any]], cap: int = FINAL_N) -> list[dict[str, Any]]:
    """Order by fill date; keep the first `cap` plus every event on the fill day of the cap-th one (protocol §6)."""
    ordered = sorted(scored, key=lambda r: (r["fill_date"], r.get("decision_id") or ""))
    if len(ordered) <= cap:
        return ordered
    last_day = ordered[cap - 1]["fill_date"]
    return [r for r in ordered if r["fill_date"] <= last_day]


def mean(values: Sequence[float]) -> float | None:
    return float(np.mean(values)) if len(values) else None


# ---------------------------------------------------------------- funnel

def build_events(rows: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Join ledger rows into one dict per (ticker, event_date). `decision` rows are decision/v2 records; optional
    `selection` rows ({ticker, group, event_date, selected}) and `failure` rows ({ticker, group, event_date}) come from
    the P2 scan; `not_fillable` rows are ignored (fillability is derived from prices). A scan decision without a
    selection row keeps selected = None (the funnel lists it as no selection record, never in the main sample). Replays and on-demand cards are separate events; duplicate scan decisions for
    one event keep the earliest."""
    events: dict[tuple, dict[str, Any]] = {}

    def slot(ticker, event_date, replay=False, key_extra="scan"):
        key = (str(ticker).upper().replace(".", "-"), event_date, replay, key_extra)
        return events.setdefault(key, {"ticker": key[0], "event_date": event_date, "group": None, "source": None,
                                       "selected": None, "decision": None, "failure": False, "replay": replay,
                                       "stamp": None})
    for row in rows:
        kind = row.get("kind") or ("decision" if row.get("schema") == "decision/v2" else None)
        if kind == "decision":
            replay = bool(row.get("replay"))
            # scan events are one per (ticker, event_date); on-demand cards are independent decisions
            extra = "scan" if row.get("source") == "scan" else row.get("decision_id")
            ev = slot(row["ticker"], (row.get("event") or {}).get("event_date"), replay, extra)
            if ev["decision"] is not None and fill_time(row) >= fill_time(ev["decision"]):
                continue
            ev["decision"] = row
            ev["group"], ev["source"] = row.get("group"), row.get("source")
        elif kind == "selection":
            ev = slot(row["ticker"], row.get("event_date"))
            ev["selected"] = bool(row.get("selected", True))
            ev["group"] = ev["group"] or row.get("group")
            ev["source"] = "scan"
            ev["stamp"] = ev["stamp"] or row.get("decided_at") or row.get("selected_at")
        elif kind == "failure":
            ev = slot(row["ticker"], row.get("event_date"))
            ev["failure"] = True
            ev["group"] = ev["group"] or row.get("group")
            ev["source"] = "scan"
            ev["stamp"] = row.get("decided_at") or ev["stamp"]
    out = list(events.values())
    return out


def funnel(events: Sequence[dict[str, Any]], group: str = "E2") -> dict[str, Any]:
    """Counts and missing rate for scan events of `group` (replays excluded), protocol §6.

    Each event dict needs: group, source, replay, selected (True / False / None = no selection row), decision,
    failure, and for decided events `scored` (the `score_record` result); for events with no decision
    `no_decision_matured` (bool: the window the decision would have had has ended on the calendar).
    Layers: candidates -> selected -> decided -> matured -> priced -> fillable -> scorable -> not late (main sample).
    Each layer lists what it dropped. Missing rate = (no decision + price_error + not_fillable + ETF-unscorable)
    / (selected and matured); unmatured events are in neither part; maturity does not depend on fillability."""
    pool = [e for e in events if e["group"] == group and e["source"] == "scan" and not e["replay"]]
    ex = {"not_selected": 0, "no_selection": 0, "failure": 0, "awaiting_decision": 0, "no_decision_unmatured": 0,
          "pending": 0, "price_error": 0, "not_fillable": 0, "unscorable": 0, "late": 0}
    main, no_selection, pending = [], [], []
    matured_selected = missing = 0
    selected = decided = matured = priced = fillable = scorable = 0
    for e in pool:
        if e["selected"] is None:
            ex["no_selection"] += 1
            no_selection.append(e)
            continue
        if not e["selected"]:
            ex["not_selected"] += 1
            continue
        selected += 1
        if e["decision"] is None:
            ex["failure" if e["failure"] else "awaiting_decision"] += 1
            if e.get("no_decision_matured"):
                matured_selected += 1
                missing += 1
            else:
                ex["no_decision_unmatured"] += 1
            continue
        decided += 1
        s = e["scored"]["status"]
        if s == "pending":
            ex["pending"] += 1
            pending.append(e["scored"])
            continue
        matured += 1
        matured_selected += 1
        if s == "price_error":
            ex["price_error"] += 1
            missing += 1
            continue
        priced += 1
        if s == "not_fillable":
            ex["not_fillable"] += 1
            missing += 1
            continue
        fillable += 1
        if s in ("unscorable", "etf_unscorable"):
            ex["unscorable"] += 1
            missing += 1
            continue
        scorable += 1
        if s == "late":
            ex["late"] += 1
            continue
        main.append(e["scored"])
    rate = missing / matured_selected if matured_selected else None
    return {"candidates": len(pool), "selected": selected, "decided": decided, "matured": matured, "priced": priced,
            "fillable": fillable, "scorable": scorable, "main": main, "pending": pending, "excluded": ex, "no_selection": no_selection,
            "matured_selected": matured_selected, "missing": missing, "missing_rate": rate,
            "missing_high": rate is not None and rate > MISSING_RATE_FLAG}
