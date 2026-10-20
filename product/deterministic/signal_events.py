"""Deterministic signal events and forward outcomes (no judgement).

Technical signals are evaluated on each trading day from adjusted closes; fundamental signals at the first
session after a 10-Q/10-K became public. Outcomes are excess returns versus a benchmark (the sector ETF)
over fixed session horizons, entered at the close of the session after the signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

HORIZONS = (20, 60, 126)
EVENT_HORIZONS = (1, 5, 20, 60)  # 8-K and other dated events

# SEC Form 8-K items (9.01 exhibits only is not an event).
FORM_8K_ITEMS = {
    "1.01": "签订重大协议", "1.02": "终止重大协议", "1.03": "破产或接管", "1.05": "重大网络安全事件",
    "2.01": "完成收购或处置资产", "2.02": "公布经营业绩（财报）", "2.03": "产生直接财务义务（发债、借款）",
    "2.04": "加速或增加财务义务的触发事件", "2.05": "退出或处置活动相关成本（重组）", "2.06": "重大减值",
    "3.01": "退市或不符合上市标准通知", "3.02": "未登记的股权销售", "3.03": "证券持有人权利重大变更",
    "4.01": "更换审计师", "4.02": "此前财报不可依赖（需重述）", "5.01": "控制权变更",
    "5.02": "董事或高管离任、任命与薪酬安排", "5.03": "公司章程或财年变更", "5.07": "股东大会表决结果",
    "7.01": "Regulation FD 披露", "8.01": "其他重要事件",
}

TECHNICAL_SIGNALS = {
    "trend_stage2_entry": "收盘价上穿 150 日均线且该均线较 20 个交易日前上升（此前至少 20 个交易日不满足）",
    "ma_bull_alignment_entry": "收盘价 > 50 日均线 > 200 日均线首次成立（此前至少 20 个交易日不满足）",
    "trend_stage4_entry": "收盘价跌破 150 日均线且该均线较 20 个交易日前下降（此前至少 20 个交易日不满足）",
    "baseline_days": "对照组：每 5 个交易日取一次，不加任何条件",
}
FUNDAMENTAL_SIGNALS = {
    "revenue_growth_acceleration": "最新季度营收同比增速比上一季度高 1 个百分点以上",
    "revenue_growth_deceleration": "最新季度营收同比增速比上一季度低 1 个百分点以上",
    "operating_margin_expansion": "最新季度 GAAP 营业利润率比去年同季高 0.5 个百分点以上",
    "operating_margin_contraction": "最新季度 GAAP 营业利润率比去年同季低 0.5 个百分点以上",
    "baseline_filings": "对照组：所有 10-Q/10-K 公布后的交易日，不加条件",
}


@dataclass(frozen=True)
class Event:
    signal: str
    ticker: str
    signal_date: str
    entry_date: str
    benchmark: str
    excess: dict          # horizon -> excess return (decimal) or None
    exit_dates: dict      # horizon -> exit date or None
    detail: dict


def _sma(values: list[float], end: int, n: int) -> float | None:
    if end + 1 < n:
        return None
    return sum(values[end + 1 - n:end + 1]) / n


def forward_excess(dates: list[str], closes: list[float], bench: dict[str, float], start_index: int,
                   horizons: tuple[int, ...] = HORIZONS) -> tuple[dict, dict]:
    """Excess return from the close at start_index to start_index + h, versus the benchmark on the same dates."""
    excess, exits = {}, {}
    base_date = dates[start_index]
    for h in horizons:
        j = start_index + h
        if j >= len(dates) or base_date not in bench or dates[j] not in bench:
            excess[h], exits[h] = None, None
            continue
        stock = closes[j] / closes[start_index] - 1
        index = bench[dates[j]] / bench[base_date] - 1
        excess[h], exits[h] = stock - index, dates[j]
    return excess, exits


def technical_events(ticker: str, dates: list[str], closes: list[float], bench_closes: dict[str, float],
                     benchmark: str, quiet: int = 20) -> list[Event]:
    """Entry events for the technical signals plus a 5-day baseline sample."""
    states: dict[str, list[bool]] = {"trend_stage2_entry": [], "ma_bull_alignment_entry": [],
                                     "trend_stage4_entry": []}
    for i in range(len(closes)):
        s150, s150_prev = _sma(closes, i, 150), _sma(closes, i - 20, 150) if i >= 20 else None
        s50, s200 = _sma(closes, i, 50), _sma(closes, i, 200)
        c = closes[i]
        states["trend_stage2_entry"].append(bool(s150 and s150_prev and c > s150 and s150 > s150_prev))
        states["trend_stage4_entry"].append(bool(s150 and s150_prev and c < s150 and s150 < s150_prev))
        states["ma_bull_alignment_entry"].append(bool(s50 and s200 and c > s50 > s200))
    events = []
    for name, flags in states.items():
        for i in range(quiet, len(flags) - 1):
            if flags[i] and not any(flags[i - quiet:i]):
                excess, exits = forward_excess(dates, closes, bench_closes, i + 1)
                events.append(Event(name, ticker, dates[i], dates[i + 1], benchmark, excess, exits, {}))
    for i in range(200, len(dates) - 1, 5):
        excess, exits = forward_excess(dates, closes, bench_closes, i + 1)
        events.append(Event("baseline_days", ticker, dates[i], dates[i + 1], benchmark, excess, exits, {}))
    return events


def fundamental_events(ticker: str, quarters: Iterable[dict], dates: list[str], closes: list[float],
                       bench_closes: dict[str, float], benchmark: str) -> list[Event]:
    """quarters: {public_at (YYYY-MM-DD), q_end, growth_delta_pp, margin_delta_pp} as known at public_at."""
    events = []
    for q in quarters:
        start = next((i for i, d in enumerate(dates) if d > q["public_at"]), None)  # first session after
        if start is None:
            continue
        excess, exits = forward_excess(dates, closes, bench_closes, start)
        detail = {k: q.get(k) for k in ("q_end", "growth_delta_pp", "margin_delta_pp")}
        names = ["baseline_filings"]
        g, m = q.get("growth_delta_pp"), q.get("margin_delta_pp")
        if g is not None:
            names.append("revenue_growth_acceleration" if g > 1 else "revenue_growth_deceleration" if g < -1 else "")
        if m is not None:
            names.append("operating_margin_expansion" if m > 0.5 else "operating_margin_contraction" if m < -0.5 else "")
        for name in filter(None, names):
            events.append(Event(name, ticker, q["public_at"], dates[start], benchmark, excess, exits, detail))
    return events


def form_8k_events(ticker: str, filings: Iterable[dict], dates: list[str], closes: list[float],
                   bench_closes: dict[str, float], benchmark: str) -> list[Event]:
    """One event per 8-K item. Entry at the first close at or after acceptance: the same session's close when
    accepted before 16:00 New York time on a trading day, otherwise the next session's close."""
    events = []
    for f in filings:
        accepted = f["accepted_ny"]  # "YYYY-MM-DDTHH:MM" New York time
        day, hhmm = accepted[:10], accepted[11:16]
        start = next((i for i, d in enumerate(dates) if d > day or (d == day and hhmm < "16:00")), None)
        if start is None:
            continue
        excess, exits = forward_excess(dates, closes, bench_closes, start, EVENT_HORIZONS)
        for item in f["items"]:
            if item in FORM_8K_ITEMS:
                events.append(Event(f"8k_item_{item}", ticker, day, dates[start], benchmark, excess, exits,
                                    {"accession": f["accession"], "items": f["items"], "accepted_ny": accepted}))
    return events


def baseline_events(ticker: str, dates: list[str], closes: list[float], bench_closes: dict[str, float],
                    benchmark: str, horizons: tuple[int, ...], name: str, step: int = 5) -> list[Event]:
    events = []
    for i in range(200, len(dates) - 1, step):
        excess, exits = forward_excess(dates, closes, bench_closes, i + 1, horizons)
        events.append(Event(name, ticker, dates[i], dates[i + 1], benchmark, excess, exits, {}))
    return events
