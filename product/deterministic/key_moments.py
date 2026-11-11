"""Key chart moments from daily adjusted closes, and what followed them (deterministic, no judgement).

A "platform" is a tight range: the highest and lowest close of the previous PLATFORM sessions are no more than
PLATFORM_WIDTH daily standard deviations apart (a random walk would span about 10 over 40 sessions). Daily
volatility is the standard deviation of the previous VOL_WINDOW daily returns, so the same definitions fit quiet
and volatile stocks. Every moment is detected with data up to that session's close only.
"""

from __future__ import annotations

import statistics

PLATFORM = 40          # sessions that form the range
PLATFORM_WIDTH = 7.0   # range / close, in daily standard deviations
VOL_WINDOW = 120
TREND_WINDOW = 100     # sessions used to call a prior up/down trend
TREND_SHARE = 0.8      # share of those sessions above (below) the 150-day average
FAIL_WINDOW = 10       # sessions within which a break is reversed
REVERSAL_LOOKBACK = 120
REVERSAL_WINDOW = 10
REVERSAL_MOVE = 6.0    # move off the extreme, in daily standard deviations
QUIET = 20             # sessions before the same moment can be recorded again
HORIZONS = (5, 20, 60)
MIN_HISTORY = 260

MOMENTS = {
    "platform_breakdown": "跌破平台：此前 40 个交易日收盘价波动很窄（高低差不超过 7 倍日波动），当日收盘低于这 40 日的最低收盘",
    "platform_breakdown_new_low": "跌破平台并创新低：同上，且当日收盘是 252 个交易日以来的最低收盘",
    "platform_breakout": "突破平台：此前 40 个交易日窄幅波动，当日收盘高于这 40 日的最高收盘",
    "platform_breakout_new_high": "突破平台并创新高：同上，且当日收盘是 252 个交易日以来的最高收盘",
    "failed_breakdown": "跌破失败：10 个交易日内出现过“跌破平台”，当日收盘回到原平台的中点之上",
    "failed_breakout": "突破失败：10 个交易日内出现过“突破平台”，当日收盘回到原平台的中点之下",
    "uptrend_break": "上升趋势失败：此前 100 个交易日有八成以上收在 150 日均线上方且均线上升，当日收盘低于此前 40 日的最低收盘",
    "downtrend_break": "下跌趋势反转：此前 100 个交易日有八成以上收在 150 日均线下方且均线下降，当日收盘高于此前 40 日的最高收盘",
    "sharp_reversal_up": "急速反转向上：10 个交易日内创过 120 日最低收盘，当日收盘已从该低点上涨 6 倍日波动以上",
    "sharp_reversal_down": "急速反转向下：10 个交易日内创过 120 日最高收盘，当日收盘已从该高点下跌 6 倍日波动以上",
}
BASELINE = "baseline_days"  # every 5th session of every ticker, no condition


def _daily_vol(closes: list[float], i: int) -> float | None:
    if i < VOL_WINDOW:
        return None
    rets = [closes[k] / closes[k - 1] - 1 for k in range(i - VOL_WINDOW + 1, i + 1)]
    return statistics.pstdev(rets) or None


def detect(dates: list[str], closes: list[float]) -> list[dict]:
    """All key moments in the series: {moment, date, index, detail}. The same moment is not repeated within QUIET sessions."""
    n = len(closes)
    prefix = [0.0]
    for c in closes:
        prefix.append(prefix[-1] + c)

    def sma(i: int, k: int) -> float | None:
        return (prefix[i + 1] - prefix[i + 1 - k]) / k if i + 1 >= k else None

    found: list[dict] = []
    last: dict[str, int] = {}
    breaks: list[tuple[int, str, float]] = []  # (index, kind, platform midpoint)

    def add(moment: str, i: int, **detail) -> None:
        if i - last.get(moment, -10 ** 9) >= QUIET:
            last[moment] = i
            found.append({"moment": moment, "date": dates[i], "index": i,
                          "detail": {k: round(v, 4) if isinstance(v, float) else v for k, v in detail.items()}})

    for i in range(MIN_HISTORY, n):
        vol = _daily_vol(closes, i - 1)
        if not vol:
            continue
        c = closes[i]
        window = closes[i - PLATFORM:i]
        hi, lo = max(window), min(window)
        width = (hi - lo) / closes[i - 1] / vol
        platform = width <= PLATFORM_WIDTH
        year = closes[i - 252:i]
        if platform and c < lo:
            add("platform_breakdown", i, platform_low=lo, platform_high=hi, width_in_daily_vol=width)
            breaks.append((i, "down", (hi + lo) / 2))
            if c < min(year):
                add("platform_breakdown_new_low", i, platform_low=lo, platform_high=hi)
        if platform and c > hi:
            add("platform_breakout", i, platform_low=lo, platform_high=hi, width_in_daily_vol=width)
            breaks.append((i, "up", (hi + lo) / 2))
            if c > max(year):
                add("platform_breakout_new_high", i, platform_low=lo, platform_high=hi)
        for j, kind, mid in breaks[-4:]:
            if 0 < i - j <= FAIL_WINDOW:
                if kind == "down" and c > mid:
                    add("failed_breakdown", i, break_date=dates[j], platform_mid=mid)
                if kind == "up" and c < mid:
                    add("failed_breakout", i, break_date=dates[j], platform_mid=mid)
        s_now, s_then = sma(i - 1, 150), sma(i - 21, 150)
        if s_now and s_then and i - TREND_WINDOW - 150 >= 0:
            above = sum(closes[k] > sma(k, 150) for k in range(i - TREND_WINDOW, i)) / TREND_WINDOW
            if above >= TREND_SHARE and s_now > s_then and c < lo:
                add("uptrend_break", i, share_above_150d=above, low_40d=lo)
            if 1 - above >= TREND_SHARE and s_now < s_then and c > hi:
                add("downtrend_break", i, share_below_150d=1 - above, high_40d=hi)
        recent = closes[i - REVERSAL_WINDOW:i]
        base = closes[i - REVERSAL_LOOKBACK:i]
        r_lo, r_hi = min(recent), max(recent)
        if r_lo <= min(base) and c / r_lo - 1 >= REVERSAL_MOVE * vol:
            add("sharp_reversal_up", i, low=r_lo, move_in_daily_vol=(c / r_lo - 1) / vol)
        if r_hi >= max(base) and 1 - c / r_hi >= REVERSAL_MOVE * vol:
            add("sharp_reversal_down", i, high=r_hi, move_in_daily_vol=(1 - c / r_hi) / vol)
    return found


def outcome(dates: list[str], closes: list[float], bench: dict[str, float], index: int) -> dict:
    """What followed a moment at `index`: entered at the next session's close, for each horizon the return, the
    return minus the benchmark's, the lowest close on the way (worst drawdown from entry) and the exit date."""
    start = index + 1
    out: dict = {"entry_date": dates[start] if start < len(dates) else None}
    for h in HORIZONS:
        j = start + h
        if j >= len(dates):
            out[str(h)] = None
            continue
        ret = closes[j] / closes[start] - 1
        b0, b1 = bench.get(dates[start]), bench.get(dates[j])
        out[str(h)] = {"exit_date": dates[j], "ret": round(ret, 5),
                       "excess": round(ret - (b1 / b0 - 1), 5) if b0 and b1 else None,
                       "worst": round(min(closes[start:j + 1]) / closes[start] - 1, 5)}
    return out


def state(dates: list[str], closes: list[float]) -> dict | None:
    """Where the last close sits: platform bounds if the last PLATFORM sessions form one, distance to the 40-day and
    252-day extremes, and the trend share."""
    i = len(closes) - 1
    if i < MIN_HISTORY:
        return None
    vol = _daily_vol(closes, i)
    window = closes[i - PLATFORM + 1:i + 1]
    hi, lo, c = max(window), min(window), closes[i]
    year = closes[i - 251:i + 1]
    sma150 = [sum(closes[k - 149:k + 1]) / 150 for k in range(i - TREND_WINDOW + 1, i + 1)]
    above = sum(closes[k] > s for k, s in zip(range(i - TREND_WINDOW + 1, i + 1), sma150)) / TREND_WINDOW
    width = (hi - lo) / c / vol if vol else None
    return {"date": dates[i], "close": c, "daily_vol_pct": round(vol * 100, 2) if vol else None,
            "range_40d": [lo, hi], "range_40d_width_in_daily_vol": round(width, 1) if width else None,
            "in_platform": bool(width is not None and width <= PLATFORM_WIDTH),
            "pct_above_40d_low": round((c / lo - 1) * 100, 2), "pct_below_40d_high": round((1 - c / hi) * 100, 2),
            "pct_above_252d_low": round((c / min(year) - 1) * 100, 2),
            "pct_below_252d_high": round((1 - c / max(year)) * 100, 2),
            "share_of_100d_above_150d_avg": round(above, 2),
            "avg_150d_rising": sma150[-1] > sma150[-21]}


def summarize(rows: list[dict], horizon: int) -> dict | None:
    """Distribution of outcomes for one moment and horizon. rows: outcome dicts whose horizon entry is not None."""
    cells = [r[str(horizon)] for r in rows if r.get(str(horizon))]
    if not cells:
        return None
    rets = sorted(c["ret"] * 100 for c in cells)
    exc = sorted(c["excess"] * 100 for c in cells if c["excess"] is not None)
    worst = sorted(c["worst"] * 100 for c in cells)
    ups, downs = [r for r in rets if r > 0], [r for r in rets if r <= 0]

    def q(values: list[float], p: float) -> float | None:
        if not values:
            return None
        k = (len(values) - 1) * p
        f = int(k)
        return round(values[f] + (values[min(f + 1, len(values) - 1)] - values[f]) * (k - f), 1)

    p_up = len(ups) / len(rets)
    avg_up = statistics.mean(ups) if ups else 0.0
    avg_down = statistics.mean(downs) if downs else 0.0
    return {"n": len(rets), "p_up": round(p_up, 2), "avg_gain_pct": round(avg_up, 1), "avg_loss_pct": round(avg_down, 1),
            "expectancy_pct": round(p_up * avg_up + (1 - p_up) * avg_down, 1),
            "ret_pct_q25_median_q75": [q(rets, 0.25), q(rets, 0.5), q(rets, 0.75)],
            "excess_vs_benchmark_pct_q25_median_q75": [q(exc, 0.25), q(exc, 0.5), q(exc, 0.75)],
            "p_excess_positive": round(sum(e > 0 for e in exc) / len(exc), 2) if exc else None,
            "worst_drawdown_pct_median_q10": [q(worst, 0.5), q(worst, 0.1)]}
