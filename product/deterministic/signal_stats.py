"""Statistics for signal events against a date-matched control (deterministic, no judgement).

Each event's excess return (vs its sector ETF) is compared with the average excess of the whole universe's
control sample on the matching date (the latest control sampling date on or before the entry date, within
7 calendar days). Confidence intervals come from cluster bootstraps: resampling tickers (repeated signals in
one stock) and resampling calendar months (overlapping holding windows across stocks).
"""

from __future__ import annotations

import random
import statistics
from bisect import bisect_right
from datetime import date

SIGNAL_DEFINITIONS_VERSION = 1


def _control_by_date(controls: list[dict], h: str) -> tuple[list[str], dict[str, float]]:
    by_date: dict[str, list[float]] = {}
    for c in controls:
        if c["excess"].get(h) is not None:
            by_date.setdefault(c["entry_date"], []).append(c["excess"][h])
    means = {d: statistics.mean(v) for d, v in by_date.items() if len(v) >= 10}
    return sorted(means), means


def matched(events: list[dict], controls: list[dict], h: str) -> list[dict]:
    """Events with `abnormal` = excess − same-date universe control mean (events without a match are dropped)."""
    dates, means = _control_by_date(controls, h)
    out = []
    for e in events:
        x = e["excess"].get(h)
        if x is None:
            continue
        i = bisect_right(dates, e["entry_date"]) - 1
        if i < 0 or (date.fromisoformat(e["entry_date"]) - date.fromisoformat(dates[i])).days > 7:
            continue
        out.append({**e, "abnormal": x - means[dates[i]], "control": means[dates[i]]})
    return out


def _bootstrap(rows: list[dict], key: str, reps: int, seed: int) -> tuple[float, float] | None:
    groups: dict[str, list[float]] = {}
    for r in rows:
        groups.setdefault(r[key], []).append(r["abnormal"])
    names = list(groups)
    if len(names) < 5:
        return None
    rng = random.Random(seed)
    stats = []
    for _ in range(reps):
        sample = [v for n in (rng.choice(names) for _ in names) for v in groups[n]]
        stats.append(statistics.mean(sample))
    stats.sort()
    return round(stats[int(0.025 * reps)] * 100, 2), round(stats[int(0.975 * reps)] * 100, 2)


def summarize(rows: list[dict], cost_pct: float, reps: int = 1000, seed: int = 0) -> dict:
    """rows from matched(); percentages in percent units."""
    if not rows:
        return {"n": 0}
    excess = [r["excess_h"] * 100 for r in rows]
    abnormal = [r["abnormal"] * 100 for r in rows]
    wins = [x for x in excess if x > 0]
    losses = [x for x in excess if x <= 0]
    for r in rows:
        r["month"] = r["entry_date"][:7]
    return {
        "n": len(rows), "distinct_tickers": len({r["ticker"] for r in rows}),
        "distinct_months": len({r["month"] for r in rows}),
        "mean_excess_pct": round(statistics.mean(excess), 2), "median_excess_pct": round(statistics.median(excess), 2),
        "hit_rate": round(len(wins) / len(excess), 3),
        "avg_win_pct": round(statistics.mean(wins), 2) if wins else None,
        "avg_loss_pct": round(statistics.mean(losses), 2) if losses else None,
        "payoff_ratio": round(statistics.mean(wins) / -statistics.mean(losses), 2) if wins and losses and statistics.mean(losses) < 0 else None,
        "mean_vs_matched_control_pp": round(statistics.mean(abnormal), 2),
        "ci95_cluster_by_ticker_pp": _bootstrap(rows, "ticker", reps, seed),
        "ci95_cluster_by_month_pp": _bootstrap(rows, "month", reps, seed + 1),
        "mean_excess_after_cost_pct": round(statistics.mean(excess) - cost_pct, 2),
    }
