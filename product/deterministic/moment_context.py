"""Context of key moments: grouping, feature vectors and nearest historical analogs (deterministic)."""

from __future__ import annotations

import statistics

DOWN = ("platform_breakdown", "platform_breakdown_new_low", "uptrend_break", "failed_breakout", "sharp_reversal_down")
UP = ("platform_breakout", "platform_breakout_new_high", "downtrend_break", "failed_breakdown", "sharp_reversal_up")
FEATURES = ("pct_below_252d_high", "ret_60d", "ret_252d", "daily_vol", "sector_ret_20d", "rel_strength_60d",
            "vix_ratio", "real_rate_chg20", "sessions_since_earnings", "last_earnings_reaction", "growth_delta_pp",
            "margin_delta_pp", "short_percentile", "has_company_filing")


def direction(moment: str) -> str | None:
    return "down" if moment in DOWN else "up" if moment in UP else None


def dedupe(rows: list[dict]) -> list[dict]:
    """One row per ticker and day (several moments of the same direction can fire together)."""
    seen, out = set(), []
    for r in rows:
        key = (r["ticker"], r["date"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def raw(context: dict) -> list[float | None]:
    values = []
    for name in FEATURES:
        if name == "has_company_filing":
            values.append(1.0 if context.get("company_8k_items_5d") else 0.0)
        elif name == "sessions_since_earnings":
            v = context.get(name)
            values.append(None if v is None else float(min(v, 60)))
        else:
            v = context.get(name)
            values.append(None if v is None else float(v))
    return values


def fit_scaler(rows: list[dict]) -> list[tuple[float, float, float]]:
    """Per feature (median for missing values, mean, standard deviation) from the fitting rows."""
    columns = list(zip(*(raw(r["context"]) for r in rows)))
    out = []
    for col in columns:
        present = [v for v in col if v is not None] or [0.0]  # a feature absent everywhere stays neutral
        out.append((statistics.median(present), statistics.mean(present), statistics.pstdev(present) or 1.0))
    return out


def vector(context: dict, scaler: list[tuple[float, float, float]]) -> list[float]:
    return [((median if v is None else v) - mean) / sd for v, (median, mean, sd) in zip(raw(context), scaler)]


def nearest(target: list[float], pool: list[tuple[dict, list[float]]], k: int) -> list[tuple[dict, float]]:
    scored = [(sum((a - b) ** 2 for a, b in zip(target, v)), i) for i, (_, v) in enumerate(pool)]
    scored.sort()
    return [(pool[i][0], d ** 0.5) for d, i in scored[:k]]


def spearman(a: list[float], b: list[float]) -> float:
    def rank(values):
        order = sorted(range(len(values)), key=lambda i: values[i])
        out = [0.0] * len(values)
        for position, i in enumerate(order):
            out[i] = position
        return out
    return statistics.correlation(rank(a), rank(b))
