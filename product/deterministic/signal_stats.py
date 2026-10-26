"""Statistics for signal events against the same-date cross-section (deterministic, no judgement).

Each event's excess return (vs its sector ETF) is ranked inside the pool of control excess returns of the whole
universe on the matching date (the latest control sampling date on or before the entry date, within 7 calendar
days, with at least 10 control values). The rank is the mid-rank percentile
pct = (bisect_left + bisect_right) / 2 / len(pool); the statistic is pct - 0.5 (reported in percentile points).
A rank is robust to extreme winners, which skew a same-date mean. Confidence intervals come from cluster
bootstraps: resampling tickers (repeated signals in one stock) and resampling calendar months (overlapping
holding windows across stocks).
"""

from __future__ import annotations

import random
import statistics
from bisect import bisect_left, bisect_right
from datetime import date

SIGNAL_DEFINITIONS_VERSION = 2  # 2: same-date cross-sectional percentile rank (1 used the same-date control mean)
MIN_POOL = 10
MAX_GAP_DAYS = 7


def build_pools(controls: list[dict], h: str) -> dict[str, list[float]]:
    """Sorted control excess returns per entry date (dates with fewer than MIN_POOL values are dropped)."""
    by_date: dict[str, list[float]] = {}
    for c in controls:
        if c["excess"].get(h) is not None:
            by_date.setdefault(c["entry_date"], []).append(c["excess"][h])
    return {d: sorted(v) for d, v in by_date.items() if len(v) >= MIN_POOL}


def percentile(pool: list[float], x: float) -> float:
    """Mid-rank percentile of x inside a sorted pool (ties share the middle rank)."""
    return (bisect_left(pool, x) + bisect_right(pool, x)) / 2 / len(pool)


def matched(events: list[dict], controls: list[dict] | dict[str, list[float]], h: str) -> list[dict]:
    """Events with `pct_minus_50` = same-date control percentile - 0.5 (events without a match are dropped).

    `controls` is a list of control events or prebuilt sorted pools from build_pools()."""
    pools = controls if isinstance(controls, dict) else build_pools(controls, h)
    dates = sorted(d for d, p in pools.items() if len(p) >= MIN_POOL)
    out = []
    for e in events:
        x = e["excess"].get(h)
        if x is None:
            continue
        i = bisect_right(dates, e["entry_date"]) - 1
        if i < 0 or (date.fromisoformat(e["entry_date"]) - date.fromisoformat(dates[i])).days > MAX_GAP_DAYS:
            continue
        pct = percentile(pools[dates[i]], x)
        out.append({**e, "excess_h": x, "percentile": pct, "pct_minus_50": pct - 0.5})
    return out


def _bootstrap(rows: list[dict], key: str, reps: int, seed: int) -> tuple[float, float] | None:
    groups: dict[str, list[float]] = {}
    for r in rows:
        groups.setdefault(r[key], []).append(r["pct_minus_50"])
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
    """rows from matched(); percentages in percent units, percentile fields in percentile points."""
    if not rows:
        return {"n": 0}
    excess = [r["excess_h"] * 100 for r in rows]
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
        "mean_percentile_minus_50": round(statistics.mean(r["pct_minus_50"] for r in rows) * 100, 2),
        "ci95_cluster_by_ticker_pts": _bootstrap(rows, "ticker", reps, seed),
        "ci95_cluster_by_month_pts": _bootstrap(rows, "month", reps, seed),
        "mean_excess_after_cost_pct": round(statistics.mean(excess) - cost_pct, 2),
    }
