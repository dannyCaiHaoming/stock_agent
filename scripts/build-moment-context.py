"""关键时刻的情境快照：给 key-moments.jsonl 的每个时刻（2019 年起）附上当时已知的各维度情况。

用法：.venv/bin/python -I scripts/build-moment-context.py
输入都在 .local/cache/derived/：signals/key-moments.jsonl、events.jsonl（季报增速与利润率变化）、
events-pead-v2.jsonl（财报信号日与反应）、events-8k.jsonl、events-insider.jsonl、short/si.jsonl、macro/panel.jsonl。
输出 signals/key-moments-context.jsonl（每行 = 一个时刻或对照日 + context + outcome）。
特征定义见 evals/key-moments/context-plan-2026-11-11.md；每个特征只用时刻当日及之前已公开的数据。
"""

from __future__ import annotations

import bisect
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from product.deterministic import key_moments as km  # noqa: E402
from product.mcp import data_tools, settings  # noqa: E402

START = "2019-01-01"
ROUTINE_8K = {"2.02", "7.01", "9.01"}


def read(path: Path):
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                yield json.loads(line)


def closes(ticker: str) -> tuple[list[str], list[float]]:
    rows = data_tools.get_price_history(ticker, start="2016-06-01", max_rows=6000)["rows"]
    pairs = [(r[0], float(r[5] or r[4])) for r in rows if (r[5] or r[4])]
    return [d for d, _ in pairs], [c for _, c in pairs]


class Series:
    """Dated values per ticker; latest(ticker, day) = the last item dated on or before day."""

    def __init__(self):
        self.days: dict[str, list[str]] = defaultdict(list)
        self.items: dict[str, list] = defaultdict(list)

    def add(self, ticker: str, day: str, item) -> None:
        self.days[ticker].append(day)
        self.items[ticker].append(item)

    def freeze(self) -> "Series":
        for t in self.days:
            order = sorted(range(len(self.days[t])), key=lambda i: self.days[t][i])
            self.days[t] = [self.days[t][i] for i in order]
            self.items[t] = [self.items[t][i] for i in order]
        return self

    def latest(self, ticker: str, day: str):
        i = bisect.bisect_right(self.days.get(ticker, []), day)
        return (self.days[ticker][i - 1], self.items[ticker][i - 1]) if i else (None, None)

    def upto(self, ticker: str, day: str) -> list:
        return self.items.get(ticker, [])[:bisect.bisect_right(self.days.get(ticker, []), day)]

    def between(self, ticker: str, first: str, last: str) -> list:
        d = self.days.get(ticker, [])
        return self.items[ticker][bisect.bisect_left(d, first):bisect.bisect_right(d, last)] if d else []


def main() -> None:
    root = settings.cache().root / "derived"
    sig = root / "signals"
    quarters, earnings, filings, insiders, shorts = Series(), Series(), Series(), Series(), Series()
    seen = set()
    for e in read(sig / "events.jsonl"):
        if e["signal"] == "baseline_filings" or e["detail"].get("q_end"):
            key = (e["ticker"], e["signal_date"])
            if key not in seen and e["detail"].get("q_end"):
                seen.add(key)
                quarters.add(e["ticker"], e["signal_date"], e["detail"])
    for e in read(sig / "events-pead-v2.jsonl"):
        if e.get("kind") == "event":
            earnings.add(e["ticker"], e["signal_date"], e.get("reaction"))
    for e in read(sig / "events-8k.jsonl"):
        items = set(e.get("detail", {}).get("items") or [])
        if e["signal"].startswith("8k_item_") and items - ROUTINE_8K:
            filings.add(e["ticker"], e["signal_date"], sorted(items - ROUTINE_8K))
    for e in read(sig / "events-insider.jsonl"):
        if e.get("kind") == "event" and e.get("signal") == "insider_buy":
            insiders.add(e["ticker"], e["filed"], 1)
    for e in read(root / "short" / "si.jsonl"):
        if e.get("si_pct_shares_out") is not None:
            shorts.add(e["ticker"], e["publication_date"], e["si_pct_shares_out"])
    for s in (quarters, earnings, filings, insiders, shorts):
        s.freeze()
    macro = {r["date"]: r for r in read(root / "macro" / "panel.jsonl")}
    macro_days = sorted(macro)

    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for e in read(sig / "key-moments.jsonl"):
        if e["date"] >= START:
            by_ticker[e["ticker"]].append(e)
    bench_cache: dict[str, tuple[list[str], list[float]]] = {}
    out_path = sig / "key-moments-context.jsonl"
    n = 0
    with out_path.open("w", encoding="utf-8") as out:
        for k, (ticker, events) in enumerate(sorted(by_ticker.items())):
            dates, px = closes(ticker)
            index = {d: i for i, d in enumerate(dates)}
            etf = events[0]["benchmark"]
            if etf not in bench_cache:
                bench_cache[etf] = closes(etf)
            bd, bp = bench_cache[etf]
            bindex = {d: i for i, d in enumerate(bd)}
            for e in events:
                day = e["date"]
                i, j = index.get(day), bindex.get(day)
                if i is None or i < 252 or j is None or j < 60:
                    continue
                c = px[i]
                rets = [px[x] / px[x - 1] - 1 for x in range(i - 119, i + 1)]
                sector_20 = bp[j] / bp[j - 20] - 1
                ctx = {
                    "pct_below_252d_high": 1 - c / max(px[i - 251:i + 1]),
                    "ret_60d": c / px[i - 60] - 1, "ret_252d": c / px[i - 252] - 1,
                    "daily_vol": statistics.pstdev(rets),
                    "sector_ret_20d": sector_20,
                    "sector_below_50d_avg": bp[j] < sum(bp[j - 49:j + 1]) / 50,
                    "rel_strength_60d": (c / px[i - 60] - 1) - (bp[j] / bp[j - 60] - 1),
                }
                m_i = bisect.bisect_right(macro_days, day)
                m = macro[macro_days[m_i - 1]] if m_i else {}
                vix, vix3m = m.get("vix"), m.get("vix3m")
                ctx["vix_ratio"] = vix / vix3m if vix and vix3m else None
                ctx["real_rate_chg20"] = m.get("dfii10_chg20")
                e_day, reaction = earnings.latest(ticker, day)
                ctx["sessions_since_earnings"] = i - index[e_day] if e_day in index else None
                ctx["last_earnings_reaction"] = reaction
                _, q = quarters.latest(ticker, day)
                ctx["growth_delta_pp"] = (q or {}).get("growth_delta_pp")
                ctx["margin_delta_pp"] = (q or {}).get("margin_delta_pp")
                first = dates[max(0, i - 5)]
                recent = filings.between(ticker, first, day)
                ctx["company_8k_items_5d"] = sorted({x for items in recent for x in items})
                hist = shorts.upto(ticker, day)
                ctx["short_pct_of_shares"] = hist[-1] if hist else None
                ctx["short_percentile"] = (sum(v <= hist[-1] for v in hist[:-1]) / (len(hist) - 1)
                                           if len(hist) >= 13 else None)
                ctx["insider_buys_60d"] = len(insiders.between(ticker, dates[max(0, i - 60)], day))
                flags = {
                    "C1_sector_weak": sector_20 < 0 and ctx["sector_below_50d_avg"],
                    "C2_market_stress": None if ctx["vix_ratio"] is None else ctx["vix_ratio"] > 1,
                    "C3_just_reported": None if ctx["sessions_since_earnings"] is None and not earnings.days.get(ticker)
                    else (ctx["sessions_since_earnings"] is not None and ctx["sessions_since_earnings"] <= 5),
                    "C4_growth_slowing": None if ctx["growth_delta_pp"] is None else ctx["growth_delta_pp"] < -1,
                    "C5_margin_shrinking": None if ctx["margin_delta_pp"] is None else ctx["margin_delta_pp"] < -0.5,
                    "C6_company_filing": bool(ctx["company_8k_items_5d"]),
                    "C7_short_crowded": None if ctx["short_percentile"] is None else ctx["short_percentile"] >= 0.8,
                    "C8_big_run_up": ctx["ret_252d"] > 0.5,
                }
                flags["C9_no_clear_cause"] = (None if flags["C3_just_reported"] is None else
                                              not (flags["C1_sector_weak"] or flags["C3_just_reported"] or flags["C6_company_filing"]))
                ctx = {a: round(b, 5) if isinstance(b, float) else b for a, b in ctx.items()}
                out.write(json.dumps({"moment": e["moment"], "ticker": ticker, "date": day, "benchmark": etf,
                                      "context": ctx, "flags": flags, "outcome": e["outcome"]}, ensure_ascii=False) + "\n")
                n += 1
            print(f"{k + 1}/{len(by_ticker)} {ticker} rows={n}", file=sys.stderr, flush=True)
    print(out_path, n, "rows")


if __name__ == "__main__":
    main()
