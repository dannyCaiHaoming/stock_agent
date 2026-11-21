"""Decision event groups (protocol v1 §2): E2 stock deviation, E1 earnings drop, E0 routine.

Pure functions over prices and filing times; no network, no judgement. The window is frozen by the group
(E2 60 sessions, E1 20, E0 60), never chosen by a model. Definitions are moved, not changed, from
scripts/sample-idiosyncratic-moments.py (`deviation`) and scripts/build-pead-events-v2.py (`locate`).

Convention: `dates` ends at the as_of session's close. Nothing after its last element is ever read.
"""

from __future__ import annotations

import statistics
from bisect import bisect_left, bisect_right
from typing import Any, Mapping, Sequence

WINDOW = 5            # sessions of relative move
THRESHOLD = 2.0       # |z| for E2
VOL_WINDOW = 120      # sessions of daily returns behind the volatility
REACTION_CUT = -0.05  # E1: D0 excess vs sector ETF below this
HORIZON = {"E2": 60, "E1": 20, "E0": 60}
NO_SECTOR = "no_sector"


def deviation_z(stock_closes: Mapping[str, float], bench_closes: Mapping[str, float],
                dates: Sequence[str], i: int) -> float | None:
    """5-session stock-minus-benchmark return ending at dates[i], over daily vol x sqrt(5); None if not computable.

    `dates` is the sorted date list of `stock_closes`. Volatility = population stdev of the daily returns that
    end between dates[i-120] and dates[i-5]; only data up to dates[i] is used.
    """
    day = dates[i]
    if day not in stock_closes or i < VOL_WINDOW + 1:
        return None
    p, b = stock_closes, bench_closes
    rets = [p[dates[k]] / p[dates[k - 1]] - 1 for k in range(i - VOL_WINDOW, i - WINDOW + 1)]
    vol = statistics.pstdev(rets)
    d0 = dates[i - WINDOW]
    if not vol or d0 not in b or day not in b:
        return None
    excess = (p[day] / p[d0] - 1) - (b[day] / b[d0] - 1)
    return excess / (vol * WINDOW ** 0.5)


def pead_d0(accepted_ny: str, dates: Sequence[str]) -> tuple[int, int] | str:
    """(P index, D0 index) from an EDGAR acceptance time in New York ('YYYY-MM-DDTHH:MM'), or an exclusion reason.

    Before 09:30 on a trading day: P = previous session, D0 = that day. 09:30-16:00: P = previous, D0 = next session.
    16:00 or later, or a non-trading day: P = that day or the last session before it, D0 = the next session.
    D0 may equal len(dates), i.e. not yet observed; the caller decides what that means.
    """
    day, hhmm = accepted_ny[:10], accepted_ny[11:16]
    if not hhmm or len(accepted_ny) < 16:
        return "no_time"
    if day < dates[0] or day > dates[-1]:
        return "outside_price_calendar"
    pos = bisect_left(dates, day)
    if pos < len(dates) and dates[pos] == day:
        if hhmm < "09:30":
            p, d0 = pos - 1, pos
        elif hhmm < "16:00":
            p, d0 = pos - 1, pos + 1
        else:
            p, d0 = pos, pos + 1
    else:
        p = bisect_right(dates, day) - 1
        d0 = p + 1
    return (p, d0) if p >= 0 else "insufficient_history"


def _e2_candidates(dates, closes, bench, moments, first_index: int) -> list[dict]:
    """Key moments at or after `first_index` whose deviation |z| >= 2, latest first; same day -> detect() order."""
    out = []
    seen_days: set[int] = set()
    for m in moments:
        i = m["index"]
        if i < first_index or i in seen_days or m["moment"] == "baseline_days":
            continue
        z = deviation_z(closes, bench, dates, i)
        if z is not None and abs(z) >= THRESHOLD:
            seen_days.add(i)
            out.append({"moment": m["moment"], "date": dates[i], "index": i, "deviation_z": round(z, 4),
                        "direction": "down" if z < 0 else "up"})
    return sorted(out, key=lambda c: -c["index"])  # stable: same index keeps detect() order (already deduped)


def _e1_candidates(dates, closes, bench, earnings, first_index: int) -> list[dict]:
    """Earnings 8-Ks (Item 2.02) whose D0 is observed, inside the window, and whose D0 excess < -5%, latest D0 first."""
    n = len(dates)
    out, seen_d0 = [], set()
    for e in sorted(earnings, key=lambda x: x["accepted_ny"]):  # earliest acceptance first: 8-K/A duplicates dropped
        loc = pead_d0(e["accepted_ny"], dates)
        if isinstance(loc, str):
            continue
        p, d0 = loc
        if d0 >= n or d0 < first_index or d0 in seen_d0:
            continue
        dp, dd = dates[p], dates[d0]
        if dp not in closes or dd not in closes or dp not in bench or dd not in bench:
            continue
        seen_d0.add(d0)
        reaction = (closes[dd] / closes[dp] - 1) - (bench[dd] / bench[dp] - 1)
        if reaction < REACTION_CUT:
            out.append({"accession": e.get("accession"), "accepted_ny": e["accepted_ny"], "d0": dd, "index": d0,
                        "p_date": dp, "reaction_excess": round(reaction, 6)})
    return sorted(out, key=lambda c: -c["index"])


def classify(dates: Sequence[str], closes: Mapping[str, float], bench_closes: Mapping[str, float] | None,
             moments: Sequence[Mapping[str, Any]], earnings: Sequence[Mapping[str, Any]],
             lookback_sessions: int = 3) -> dict[str, Any]:
    """Event group at the last session of `dates` (protocol §2).

    - `closes`: adjusted closes by date; `bench_closes`: sector ETF closes by date, or None when the stock has no
      sector mapping (then neither E2 nor E1 is possible: both are defined against the sector).
    - `moments`: key_moments.detect() output on the same series ({moment, date, index, ...}).
    - `earnings`: Item 2.02 8-Ks as {accession, accepted_ny}.
    - Window: the last `lookback_sessions` sessions (late_sessions 0 .. lookback_sessions-1), so that a decision
      made at as_of and filled at the next open is still within 3 sessions of the event by default.
    - The most recent event day in the window decides. E2 and E1 on that same session -> E2 with overlap = True
      (e1 kept); only E1 -> E1; only E2 -> E2 with e1 = None, even if an older event of the other group is in the window.
    - Nothing -> E0, event_date = the last session.
    """
    n = len(dates)
    if n == 0 or lookback_sessions < 1:
        raise ValueError("classify needs prices and lookback_sessions >= 1")
    first_index = n - lookback_sessions
    bench = bench_closes or {}
    e2 = _e2_candidates(dates, closes, bench, moments, first_index) if bench_closes else []
    e1 = _e1_candidates(dates, closes, bench, earnings, first_index) if bench_closes else []
    # the most recent event day decides; E1 and E2 only overlap when they fall on that same session
    latest = max([c["index"] for c in e2[:1] + e1[:1]], default=None)
    e2c = e2[0] if e2 and e2[0]["index"] == latest else None
    e1c = e1[0] if e1 and e1[0]["index"] == latest else None
    group = "E2" if e2c else "E1" if e1c else "E0"
    event_index = latest if latest is not None else n - 1
    if group == "E2":
        b1 = "REDUCE" if e2c["direction"] == "down" else "HOLD"
    else:
        b1 = "REDUCE" if group == "E1" else "HOLD"
    strip = lambda c: None if c is None else {k: v for k, v in c.items() if k != "index"}  # noqa: E731
    return {"group": group, "horizon_days": HORIZON[group], "event_date": dates[event_index],
            "overlap": bool(e2c and e1c), "late_sessions": n - 1 - event_index, "b1_action": b1,
            "e2": strip(e2c), "e1": strip(e1c)}
