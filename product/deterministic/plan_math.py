"""Trade-plan arithmetic (pure math, no network, no files): position sizing and the three-line settlement.

Rules: fucxxx-codex-spec/designs/position-lifecycle.md ("三线结算"), plan task H1. Records: plan/v1
(product/mcp/plan_ledger.py). Prices are unadjusted open/close lists aligned to one trading calendar
(`Bars.dates`, ascending ISO dates); a missing price is None or NaN. `adj_close` is used only for the
corporate-action check.

Entry (rework 3): a plan with `entry_valid_sessions` is a limit buy order valid for that many sessions from the first
regular session after the freeze (see `_scan_entry`); a plan without the field (old records) is the original rule:
only the first session's open, filled when it lies inside the band. `Bars.low` is optional; without it the
"filled at the band top" rule cannot apply.

Three lines on the same fill: `plan` (stop, reviews, revisions, cap), `hold` (cap only), `simple_exit`
(initial stop and cap only). Money is in dollars, R = net / r0. Everything is computed from unrounded numbers and
rounded once at the end (money 0.01, R 0.001), so a hand calculation from the legs agrees up to rounding.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Sequence

from product.deterministic.decision_scoring import NY, entry_index, num, parse_utc

COST_BPS_PER_SIDE = 10
CORP_ACTION_TOL = 0.015
MAX_HORIZON_DAYS = 120
CLOSE_NY = time(16, 0)
EARLY_CLOSE_NY = time(13, 0)        # earliest regular early close; a revision between this and 16:00 needs a manual check
ACTIONS = ("HOLD", "REDUCE", "EXIT")
LINE_NAMES = ("plan", "hold", "simple_exit")
SETTLED = ("closed", "open")
MAX_ENTRY_SESSIONS = 10


class PlanMathError(ValueError):
    """Message starts with an upper-case error code, e.g. "STOP_NOT_BELOW_ENTRY: ..."."""


# ---------------------------------------------------------------- sizing

def _positive_finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise PlanMathError(f"INVALID_NUMBER: {name} must be a finite number > 0, got {value!r}")
    return float(value)


def size_position(entry_ref: float, price_invalidation: float, risk_budget: float) -> dict:
    """{"risk_per_share", "shares", "r0"}; shares = floor(risk_budget / (entry_ref - price_invalidation)).
    Decimal arithmetic on the shortest repr of the inputs, so 1000 / (10.1 - 10.0) is exactly 10000.
    Errors: INVALID_NUMBER, STOP_NOT_BELOW_ENTRY, RISK_BUDGET_TOO_SMALL (shares < 1)."""
    entry = _positive_finite(entry_ref, "entry_ref")
    stop = _positive_finite(price_invalidation, "price_invalidation")
    budget = _positive_finite(risk_budget, "risk_budget")
    if stop >= entry:
        raise PlanMathError(f"STOP_NOT_BELOW_ENTRY: price_invalidation {stop} must be below entry_ref {entry}")
    per_share = Decimal(repr(entry)) - Decimal(repr(stop))
    shares = int(Decimal(repr(budget)) // per_share)
    if shares < 1:
        raise PlanMathError(f"RISK_BUDGET_TOO_SMALL: risk_budget {budget} buys less than one share at risk "
                            f"{per_share} per share")
    return {"risk_per_share": float(per_share), "shares": shares, "r0": float(per_share * shares)}


# ---------------------------------------------------------------- inputs

@dataclass
class Bars:
    dates: list[str]                 # ascending ISO dates (trading calendar)
    open: list[float | None]
    close: list[float | None]
    adj_close: list[float | None]    # corporate-action check only
    low: list[float | None] | None = None    # session lows (optional); needed only for the limit-fill rule


def _check_bars(bars: Bars, as_of: str) -> tuple[list[str], list[float | None], list[float | None],
                                                 list[float | None], list[float | None]]:
    """Validate and cut to date <= as_of; prices cleaned with decision_scoring.num (missing / NaN / <= 0 → None).
    The low list is all None when `bars.low` is not given."""
    n = len(bars.dates)
    if not (len(bars.open) == len(bars.close) == len(bars.adj_close) == n) or \
            (bars.low is not None and len(bars.low) != n):
        raise PlanMathError("INVALID_BARS: dates, open, close, adj_close (and low when given) must have the same length")
    prev = None
    for d in bars.dates:
        try:
            date.fromisoformat(d)
        except (TypeError, ValueError):
            raise PlanMathError(f"INVALID_BARS: bad date {d!r}") from None
        if prev is not None and d <= prev:
            raise PlanMathError(f"INVALID_BARS: dates must be strictly ascending ({prev} then {d})")
        prev = d
    k = sum(1 for d in bars.dates if d <= as_of)
    lows = [None] * k if bars.low is None else [num(x) for x in bars.low[:k]]
    return (list(bars.dates[:k]), [num(x) for x in bars.open[:k]], [num(x) for x in bars.close[:k]],
            [num(x) for x in bars.adj_close[:k]], lows)


def _int_field(value: Any, name: str, lo: int, hi: int | None = None) -> int:
    ok = (not isinstance(value, bool)) and isinstance(value, (int, float)) and math.isfinite(value) \
        and float(value).is_integer() and value >= lo and (hi is None or value <= hi)
    if not ok:
        raise PlanMathError(f"INVALID_PLAN: {name} must be an integer in [{lo}, {hi if hi is not None else 'inf'}], "
                            f"got {value!r}")
    return int(value)


def _stamp(value: Any, what: str) -> datetime:
    try:
        return parse_utc(value)
    except (TypeError, ValueError, AttributeError):
        raise PlanMathError(f"INVALID_PLAN: {what} is not an ISO timestamp: {value!r}") from None


# ---------------------------------------------------------------- one line

def _leg(day: str, side: str, price: float, shares: int, reason: str, **extra: Any) -> dict[str, Any]:
    return {"date": day, "side": side, "price": price, "shares": shares, "reason": reason, **extra}


def _run_line(dates: Sequence[str], opens: Sequence[float | None], closes: Sequence[float | None], i: int,
              shares: int, stop_at: Any, reviews: dict[int, list[tuple[str, str]]], cap_idx: int | None,
              fill_price: float | None = None) -> dict[str, Any]:
    """Walk one line from the fill day. `stop_at(d)` → stop in force for the close of day d (None: no stop rule);
    `reviews` maps execution-open index (> fill index) → [(action, review_id)] (REDUCE / EXIT only); `cap_idx` is
    the cap trading day or None when the cap has not been reached by as_of. `fill_price` defaults to the open of day i
    (a limit fill passes the limit). The stop check starts at the close of the fill day. Returns raw (unrounded) legs
    and bookkeeping; money is computed by `_money`."""
    n = len(dates)
    if fill_price is None:
        fill_price = opens[i]
    held = shares
    legs = [_leg(dates[i], "buy", fill_price, shares, "fill")]
    flags: set[str] = set()
    pending: list[tuple[str, str, dict[str, Any]]] = []     # (kind exit|stop|reduce, ref, extra)
    held_closes: list[float] = []
    end_idx = i
    for d in range(i, n):
        for action, rid in reviews.get(d, []):
            pending.append(("exit" if action == "EXIT" else "reduce", rid, {"review_id": rid}))
        # 1. exits scheduled for this open
        if pending:
            o = opens[d]
            if o is None:
                flags.add("delayed_exit")
            else:
                full = [p for p in pending if p[0] in ("exit", "stop")]
                if full:
                    kind, _, extra = next((p for p in full if p[0] == "exit"), full[0])
                    legs.append(_leg(dates[d], "sell", o, held, "review" if kind == "exit" else "stop", **extra))
                    held = 0
                else:
                    if len(pending) > 1:
                        flags.add("multiple_reduce_same_open")
                    qty = held // 2 or held
                    legs.append(_leg(dates[d], "sell", o, qty, "review", **pending[0][2]))
                    held -= qty
                pending = []
                end_idx = d
                if held == 0:
                    break
        # 2. close of day d, still held
        c = closes[d]
        if c is not None:
            held_closes.append(c)
        if cap_idx is not None and d >= cap_idx:
            if c is not None:
                legs.append(_leg(dates[d], "sell", c, held, "cap"))
                held = 0
                end_idx = d
                break
            flags.add("delayed_cap")
            continue
        if stop_at is None:
            continue
        if c is None:
            flags.add("missing_close")
        elif not any(p[0] == "stop" for p in pending):
            level = stop_at(d)
            if c <= level:
                pending.append(("stop", "", {"trigger_date": dates[d], "trigger_close": c, "stop": level}))
    status = "closed"
    unrealized = False
    if held > 0:
        status, unrealized, end_idx = "open", True, n - 1
        if pending:
            flags.add("exit_pending_at_as_of")
        valued = [k for k in range(i, n) if closes[k] is not None]
        if not valued:
            flags.add("no_close_to_value")
            status = "not_settleable"
        else:
            k = valued[-1]
            if k != n - 1:
                flags.add("stale_valuation")
            legs.append(_leg(dates[k], "sell", closes[k], held, "value"))
    return {"status": status, "legs": legs, "flags": flags, "held_closes": held_closes, "unrealized": unrealized,
            "end_idx": end_idx, "fill_price": fill_price, "shares": shares}


def _money(line: dict[str, Any], r0: float, bps: float) -> None:
    """Add gross, costs, net, r, return_pct, min_close_r (unrounded) to a run line."""
    gross = costs = 0.0
    for leg in line["legs"]:
        value = leg["price"] * leg["shares"]
        gross += value if leg["side"] == "sell" else -value
        if leg["reason"] != "value":
            costs += value * bps / 10000.0
    net = gross - costs
    cost_basis = line["fill_price"] * line["shares"]
    mn = min(line["held_closes"]) if line["held_closes"] else None
    line.update(gross=gross, costs=costs, net=net, r=net / r0, return_pct=net / cost_basis * 100.0,
                min_close_r=None if mn is None else (mn - line["fill_price"]) * line["shares"] / r0)


def _empty_line(status: str, flags: Sequence[str] = ()) -> dict[str, Any]:
    return {"status": status, "legs": [], "flags": set(flags), "gross": None, "costs": None, "net": None, "r": None,
            "return_pct": None, "min_close_r": None, "unrealized": False, "end_idx": None}


def _r(x: float | None, nd: int) -> float | None:
    if x is None:
        return None
    v = round(x, nd)
    return 0.0 if v == 0 else v


def _public(line: dict[str, Any], dates: Sequence[str]) -> dict[str, Any]:
    end = line.get("end_idx")
    return {"status": line["status"], "legs": [dict(leg) for leg in line["legs"]], "gross": _r(line["gross"], 2), "costs": _r(line["costs"], 2),
            "net": _r(line["net"], 2), "r": _r(line["r"], 3), "return_pct": _r(line["return_pct"], 2),
            "min_close_r": _r(line["min_close_r"], 3), "unrealized": bool(line["unrealized"]),
            "end_date": dates[end] if end is not None and line["status"] != "unfilled" else None,
            "flags": sorted(line["flags"])}


# ---------------------------------------------------------------- entry order

def _scan_entry(dates: Sequence[str], opens: Sequence[float | None], lows: Sequence[float | None],
                closes: Sequence[float | None], i: int, valid: int, lo: float, hi: float, stop0: float,
                cap_date: str, as_of: str) -> dict[str, Any]:
    """Walk the limit buy order over at most `valid` completed sessions from index `i` (the first session after the
    freeze). Per session: open in [lo, hi] → fill at the open (method "open"); open above hi and low <= hi → fill at hi
    (method "limit"; needs a low); open below lo, or above hi without touching hi → no fill, next session; a missing open
    skips the session (flag missing_open). After an unfilled session whose close is <= the initial stop the order is
    cancelled (kind cancelled_stop_before_fill). Sessions after `cap_date` are not scanned.

    kind: filled | cancelled_stop_before_fill | not_fillable (every session of the full window has no open) | unfilled
    (full window scanned, nothing filled) | expired_unfilled (the cap date ended the window early) | pending (the
    window is not complete in the calendar yet). `last` = index of the last session scanned."""
    n = len(dates)
    flags: set[str] = set()
    scanned = missing = 0
    last = i
    truncated = False
    result: dict[str, Any] = {}
    for j in range(i, min(i + valid, n)):
        if dates[j] > cap_date:
            truncated = True
            break
        last, scanned = j, scanned + 1
        o = opens[j]
        if o is None:
            missing += 1
            flags.add("missing_open")
        elif lo <= o <= hi:
            result = {"kind": "filled", "index": j, "price": o, "method": "open"}
            break
        elif o > hi and lows[j] is not None and lows[j] <= hi:
            result = {"kind": "filled", "index": j, "price": hi, "method": "limit"}
            break
        c = closes[j]
        if c is not None and c <= stop0:
            result = {"kind": "cancelled_stop_before_fill", "index": None, "price": None, "method": None}
            break
    if not result:
        if scanned == valid:
            kind = "not_fillable" if missing == valid else "unfilled"
        elif truncated or as_of >= cap_date:
            kind = "expired_unfilled"
        else:
            kind = "pending"
        result = {"kind": kind, "index": None, "price": None, "method": None}
    if result["kind"] == "not_fillable":
        flags.discard("missing_open")
    result.update(last=last, scanned=scanned, flags=flags)
    return result


# ---------------------------------------------------------------- settlement

def _split_dates(splits: Any) -> list[str]:
    """Ex-dates of the `splits` argument ([[date, ratio], ...]); the ratio is informational only here."""
    if splits is None:
        return []
    out = []
    for item in splits:
        try:
            day = item[0]
            date.fromisoformat(day)
        except (TypeError, ValueError, IndexError, KeyError):
            raise PlanMathError(f"INVALID_SPLITS: each split is [YYYY-MM-DD, ratio], got {item!r}") from None
        out.append(day)
    return sorted(out)


def settle(plan: dict, revisions: list[dict], reviews: list[dict], bars: Bars, as_of: str,
           cost_bps_per_side: float = COST_BPS_PER_SIDE, splits: Sequence[Sequence[Any]] | None = None,
           unparsed_splits: Sequence[str] | None = None) -> dict:
    """Three-line settlement of one plan as of `as_of` (only bars with date <= as_of are used, and only revisions
    and reviews effective no later than the 16:00 New York close of `as_of`; later ones are ignored everywhere,
    including `stop_versions`).

    `bars` hold prices as they traded (split-adjusted data must be restored by the caller). `splits` = [[ex_date,
    ratio], ...]: a split dated from the freeze day to the end of the longest line makes all three lines
    not_settleable (flag split_in_window); a split after the end does not matter. `unparsed_splits` = ex-dates of
    splits whose ratio the caller could not read (so earlier bars could not be restored): one dated after the freeze
    day makes all three lines not_settleable (flag split_ratio_unparsed), whatever the window.

    Entry: `plan["entry_valid_sessions"]` (integer 1..10) makes the plan a limit buy order valid that many sessions from
    the first session after the freeze (`_scan_entry`; the fill is the open when it lies in the band, else the band top
    when the session traded down to it; `fill` then also carries price, method, valid_sessions, sessions_scanned). A plan
    WITHOUT the field (old records) is settled exactly as before: first session's open only, no limit fill, a missing
    open is not_fillable. Stops, reviews and the cap work from the fill session on.

    Returns {"as_of", "fill", "cap_date", "cap_trading_day", "stop_versions", "lines": {plan, hold, simple_exit},
    "pairs": {plan_minus_hold, plan_minus_simple}}. Line status: closed | open | unfilled | expired_unfilled |
    not_fillable | pending | cancelled_before_fill | cancelled_stop_before_fill | not_settleable. Errors (PlanMathError): INVALID_AS_OF,
    INVALID_BARS, INVALID_PLAN, INVALID_REVISION, INVALID_REVIEW, INVALID_NUMBER, INVALID_SPLITS."""
    try:
        date.fromisoformat(as_of)
    except (TypeError, ValueError):
        raise PlanMathError(f"INVALID_AS_OF: {as_of!r} is not an ISO date") from None
    bps = float(cost_bps_per_side)
    if not math.isfinite(bps) or bps < 0:
        raise PlanMathError(f"INVALID_NUMBER: cost_bps_per_side must be finite and >= 0, got {cost_bps_per_side!r}")
    frozen = _stamp(plan.get("frozen_at"), "frozen_at")
    band = plan.get("entry_band")
    if not isinstance(band, (list, tuple)) or len(band) != 2:
        raise PlanMathError("INVALID_PLAN: entry_band must be [lo, hi]")
    lo, hi = _positive_finite(band[0], "entry_band[0]"), _positive_finite(band[1], "entry_band[1]")
    if lo > hi:
        raise PlanMathError(f"INVALID_PLAN: entry_band lo {lo} > hi {hi}")
    stop0 = _positive_finite(plan.get("price_invalidation"), "price_invalidation")
    shares = _int_field(plan.get("shares_planned"), "shares_planned", 1)
    r0 = _positive_finite(plan.get("r0"), "r0")
    horizon = _int_field(plan.get("horizon_cap_days"), "horizon_cap_days", 1, MAX_HORIZON_DAYS)
    legacy = "entry_valid_sessions" not in plan
    valid = 1 if legacy else _int_field(plan["entry_valid_sessions"], "entry_valid_sessions", 1, MAX_ENTRY_SESSIONS)

    split_days = _split_dates(splits)
    cutoff = datetime.combine(date.fromisoformat(as_of), CLOSE_NY, tzinfo=NY)   # nothing effective later is known

    # stop versions: initial + every revision that changes price_invalidation (version = revision order + 2)
    chain: list[tuple[datetime, float, int]] = []
    for k, rev in enumerate(revisions):
        changes = rev.get("changes") or {}
        if not isinstance(changes, dict):
            raise PlanMathError(f"INVALID_REVISION: revision {k + 2} changes must be an object")
        at = _stamp(rev.get("effective_at"), f"revision {k + 2} effective_at")
        if "price_invalidation" in changes:
            try:
                value = _positive_finite(changes["price_invalidation"], "revision price_invalidation")
            except PlanMathError as e:
                raise PlanMathError(f"INVALID_REVISION: revision {k + 2}: {e}") from None
            if at <= cutoff:
                chain.append((at, value, k + 2))
    chain.sort(key=lambda t: (t[0], t[2]))
    stop_versions = [{"version": 1, "effective_at": frozen.isoformat(), "price_invalidation": stop0}] + \
        [{"version": v, "effective_at": at.isoformat(), "price_invalidation": p} for at, p, v in chain]

    def stop_in_force(d_idx: int) -> float:
        threshold = datetime.combine(date.fromisoformat(dates[d_idx]), CLOSE_NY, tzinfo=NY)
        value = stop0
        for at, p, _ in chain:
            if at < threshold:
                value = p
        return value

    exec_reviews: list[tuple[str, str, datetime]] = []
    for rv in reviews:
        action = rv.get("action")
        if action not in ACTIONS:
            raise PlanMathError(f"INVALID_REVIEW: action must be one of {ACTIONS}, got {action!r}")
        if not rv.get("review_id"):
            raise PlanMathError("INVALID_REVIEW: review_id missing")
        at = _stamp(rv.get("reviewed_at_effective"), f"review {rv.get('review_id')} reviewed_at_effective")
        if at <= cutoff:
            exec_reviews.append((action, str(rv["review_id"]), at))

    dates, opens, closes, adjs, lows = _check_bars(bars, as_of)
    n = len(dates)

    cap_date = (frozen.astimezone(NY).date() + timedelta(days=horizon)).isoformat()
    out: dict[str, Any] = {"as_of": as_of, "cap_date": cap_date, "cap_trading_day": None,
                           "stop_versions": stop_versions, "cost_bps_per_side": bps}

    def no_fill(status: str, fill_info: dict[str, Any], flags: Sequence[str] = ()) -> dict[str, Any]:
        out["fill"] = fill_info
        out["lines"] = {k: _public(_empty_line(status, flags), dates) for k in LINE_NAMES}
        out["pairs"] = {"plan_minus_hold": None, "plan_minus_simple": None}
        return out

    blank = {"index": None, "date": None, "open": None, "shares": None, "entry_band": [lo, hi]}
    if not legacy:
        blank.update(price=None, method=None, valid_sessions=valid, sessions_scanned=0)
    i = entry_index(plan["frozen_at"], dates)
    if i is None:
        # No session after the freeze in the calendar. Once the cap date has been reached, no open on or before it
        # can ever exist (the calendar reaches the freeze day, so it is not simply missing): expired, not pending.
        frozen_day_early = frozen.astimezone(NY).date().isoformat()
        if as_of >= cap_date and dates and dates[-1] >= frozen_day_early:
            return no_fill("expired_unfilled", {**blank, "status": "expired_unfilled"})
        return no_fill("pending", {**blank, "status": "pending"})
    fill_open = opens[i]
    fill_info = {"status": "filled", "index": i, "date": dates[i], "open": fill_open, "shares": shares,
                 "entry_band": [lo, hi]}
    if not legacy:
        fill_info.update(price=None, method=None, valid_sessions=valid, sessions_scanned=0)
    frozen_day = frozen.astimezone(NY).date().isoformat()
    if dates[i] > cap_date:       # the holding cap passed before any session could open the position
        return no_fill("expired_unfilled", {**fill_info, "status": "expired_unfilled", "shares": None})
    entry_flags: set[str] = set()
    fill_price = None
    scan: dict[str, Any] = {"last": i, "kind": "filled"}
    if not legacy:
        scan = _scan_entry(dates, opens, lows, closes, i, valid, lo, hi, stop0, cap_date, as_of)
        fill_info["sessions_scanned"] = scan["scanned"]
        if scan["kind"] in ("pending", "expired_unfilled"):
            return no_fill(scan["kind"], {**fill_info, "status": scan["kind"], "shares": None}, scan["flags"])
        entry_flags = scan["flags"]
    unparsed = _split_dates([[d] for d in unparsed_splits or ()])
    split_flags = (["split_in_window"] if any(frozen_day <= d <= dates[scan["last"]] for d in split_days) else []) + \
                  (["split_ratio_unparsed"] if any(d > frozen_day for d in unparsed) else [])
    if split_flags:     # band and fill open (or later bars) on different per-share bases
        return no_fill("not_settleable", {**fill_info, "status": "not_settleable", "shares": None}, split_flags)
    if legacy:
        if fill_open is None:
            return no_fill("not_fillable", {**fill_info, "status": "not_fillable", "shares": None})
        if not (lo <= fill_open <= hi):
            return no_fill("unfilled", {**fill_info, "status": "unfilled", "shares": None})
    else:
        if scan["kind"] != "filled":
            return no_fill(scan["kind"], {**fill_info, "status": scan["kind"], "shares": None}, entry_flags)
        i = scan["index"]
        fill_price = scan["price"]
        fill_info.update(index=i, date=dates[i], open=opens[i], price=fill_price, method=scan["method"])
    out["fill"] = fill_info

    # cap trading day: only known once as_of has reached the cap calendar date
    cap_idx = None
    if as_of >= cap_date:
        cap_idx = max(k for k in range(n) if dates[k] <= cap_date)     # >= i: dates[i] <= cap_date was checked above
        out["cap_trading_day"] = dates[cap_idx]

    # reviews → execution open index
    plan_flags: set[str] = set()
    if any(EARLY_CLOSE_NY <= at.astimezone(NY).time() < CLOSE_NY for at, _, _ in chain):
        plan_flags.add("revision_same_day_check")      # early-close days are not modelled (L1): check by hand
    by_idx: dict[int, list[tuple[str, str]]] = {}
    cancelled = False
    for action, rid, at in sorted(exec_reviews, key=lambda t: (t[2], t[1])):
        j = entry_index(at, dates)
        if j is None:
            plan_flags.add("review_pending_execution")
            continue
        if j <= i:
            if action == "EXIT":
                cancelled = True
            elif action == "REDUCE":
                plan_flags.add("review_ignored_before_fill")
            continue
        if action != "HOLD":
            by_idx.setdefault(j, []).append((action, rid))

    runs: dict[str, dict[str, Any]] = {}
    if cancelled:
        runs["plan"] = _empty_line("cancelled_before_fill", plan_flags)
    else:
        runs["plan"] = _run_line(dates, opens, closes, i, shares, stop_in_force, by_idx, cap_idx, fill_price)
        runs["plan"]["flags"] |= plan_flags
    runs["hold"] = _run_line(dates, opens, closes, i, shares, None, {}, cap_idx, fill_price)
    runs["simple_exit"] = _run_line(dates, opens, closes, i, shares, lambda _d: stop0, {}, cap_idx, fill_price)
    for ln in runs.values():
        ln["flags"] |= entry_flags

    # corporate action: adj_close / close drift from the fill day to the latest line end
    ends = [ln["end_idx"] for ln in runs.values() if ln.get("end_idx") is not None]
    ratios = [adjs[k] / closes[k] for k in range(i, max(ends) + 1) if adjs[k] is not None and closes[k] is not None]
    suspect = len(ratios) >= 2 and max(ratios) / min(ratios) - 1.0 > CORP_ACTION_TOL
    last_day = dates[max(ends)] if ends else dates[i]
    split_hit = any(frozen_day <= d <= last_day for d in split_days)

    for name, ln in runs.items():
        if ln["status"] in SETTLED:
            _money(ln, r0, bps)
        if suspect or split_hit:
            if suspect:
                ln["flags"].add("corporate_action_suspect")
            if split_hit:
                ln["flags"].add("split_in_window")
            if ln["status"] != "cancelled_before_fill":
                ln["status"] = "not_settleable"
                for key in ("gross", "costs", "net", "r", "return_pct", "min_close_r"):
                    ln[key] = None
    # not_settleable for other reasons (no close to value) carries no money either
    for ln in runs.values():
        if ln["status"] == "not_settleable" and "net" not in ln:
            for key in ("gross", "costs", "net", "r", "return_pct", "min_close_r"):
                ln[key] = None

    def pair(a: str, b: str) -> dict[str, float] | None:
        la, lb = runs[a], runs[b]
        if la["status"] not in SETTLED or lb["status"] not in SETTLED:
            return None
        return {"usd": _r(la["net"] - lb["net"], 2), "r": _r((la["net"] - lb["net"]) / r0, 3)}

    out["pairs"] = {"plan_minus_hold": pair("plan", "hold"), "plan_minus_simple": pair("plan", "simple_exit")}
    out["lines"] = {k: _public(v, dates) for k, v in runs.items()}
    return out
