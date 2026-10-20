"""生成信号事件表，供 get_signal_stats 按“当时已知”统计。

用法：.venv/bin/python -I scripts/build-signal-events.py [--tickers AAPL,MSFT] [--start 2019-01-01] [--skip-fundamental]
股票池默认 evals/replay/universe.txt；基准为所属板块 ETF（按 Yahoo 当前板块，存在误差）。
输出 .local/cache/derived/signals/events.jsonl（覆盖重写）与 meta.json。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if not os.environ.get("SEC_USER_AGENT"):
    os.environ["SEC_USER_AGENT"] = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["stock-data"]["env"]["SEC_USER_AGENT"]

from product.deterministic import signal_events  # noqa: E402
from product.mcp import context_tools, data_tools, settings  # noqa: E402

SECTOR_ETF = {"Technology": "XLK", "Communication Services": "XLC", "Consumer Cyclical": "XLY",
              "Consumer Defensive": "XLP", "Healthcare": "XLV", "Financial Services": "XLF", "Industrials": "XLI",
              "Energy": "XLE", "Basic Materials": "XLB", "Utilities": "XLU", "Real Estate": "XLRE"}


def universe() -> list[str]:
    text = (REPO / "evals/replay/universe.txt").read_text()
    return list(dict.fromkeys(t for line in text.splitlines() if not line.startswith("#") for t in line.split()))


def closes(ticker: str, start: str) -> tuple[list[str], list[float]]:
    rows = data_tools.get_price_history(ticker, start=start, max_rows=6000)["rows"]
    pairs = [(r[0], float(r[5] or r[4])) for r in rows if (r[5] or r[4])]
    return [d for d, _ in pairs], [c for _, c in pairs]


def quarters_as_known(ticker: str, start: str) -> list[dict]:
    """Per 10-Q/10-K: growth and margin deltas computed only from data published by that filing time."""
    filings = data_tools.list_filings(ticker, forms=["10-Q", "10-K"], limit=100)["rows"]
    out = []
    for accession, form, report_date, published_at, _ in filings:
        if not report_date or published_at[:10] < start:
            continue
        try:
            st = data_tools.get_financial_statements(ticker, period="quarterly", limit=9, as_of=published_at)
        except Exception:  # noqa: BLE001 - banks/foreign filers without standard tags
            continue
        ends = [p["end"] for p in st["periods"]]
        if not ends or ends[-1] != report_date or len(ends) < 6:
            continue
        rev, oi = st["lines"].get("revenue") or [], st["lines"].get("operating_income") or []

        def v(row, k):
            return float(row[k]) if -len(row) <= k < 0 and row[k] is not None else None
        r0, r1, r4, r5 = v(rev, -1), v(rev, -2), v(rev, -5), v(rev, -6)
        growth = None
        if all(x for x in (r0, r1, r4, r5)):
            growth = round(((r0 / r4 - 1) - (r1 / r5 - 1)) * 100, 2)
        o0, o4 = v(oi, -1), v(oi, -5)
        margin = round((o0 / r0 - o4 / r4) * 100, 2) if None not in (o0, o4) and r0 and r4 else None
        out.append({"public_at": published_at[:10], "q_end": report_date, "form": form,
                    "growth_delta_pp": growth, "margin_delta_pp": margin, "accession": accession})
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers")
    parser.add_argument("--start", default="2019-01-01")
    parser.add_argument("--skip-fundamental", action="store_true")
    args = parser.parse_args()
    tickers = args.tickers.split(",") if args.tickers else universe()
    out_dir = settings.cache().root / "derived" / "signals"
    out_dir.mkdir(parents=True, exist_ok=True)
    price_start = "2018-01-01"
    bench_cache: dict[str, dict[str, float]] = {}
    sectors = {}
    events, errors = [], {}
    for i, ticker in enumerate(tickers):
        try:
            rows = context_tools.get_peer_snapshot([ticker])["rows"]
            etf = SECTOR_ETF.get(rows[0][1] if rows else "", "SPY")
            sectors[ticker] = etf
            if etf not in bench_cache:
                d, c = closes(etf, price_start)
                bench_cache[etf] = dict(zip(d, c))
            dates, prices = closes(ticker, price_start)
            evs = signal_events.technical_events(ticker, dates, prices, bench_cache[etf], etf)
            evs = [e for e in evs if e.signal_date >= args.start]
            if not args.skip_fundamental:
                evs += signal_events.fundamental_events(ticker, quarters_as_known(ticker, args.start), dates, prices,
                                                        bench_cache[etf], etf)
            events.extend(evs)
        except Exception as exc:  # noqa: BLE001 - record and continue
            errors[ticker] = f"{type(exc).__name__}: {exc}"[:200]
        print(f"{i + 1}/{len(tickers)} {ticker} events={len(events)}", file=sys.stderr, flush=True)
    with (out_dir / "events.jsonl").open("w") as handle:
        for e in events:
            handle.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
    (out_dir / "meta.json").write_text(json.dumps({
        "built_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "start": args.start, "tickers": tickers,
        "benchmarks": sectors, "errors": errors, "horizons": list(signal_events.HORIZONS),
        "signals": {**signal_events.TECHNICAL_SIGNALS, **signal_events.FUNDAMENTAL_SIGNALS},
        "universe_note": "82 只大盘股，按 2026-10 的认知挑选，存在幸存者偏差；板块 ETF 按当前板块映射。",
    }, ensure_ascii=False, indent=2))
    print(out_dir / "events.jsonl", len(events), "events;", len(errors), "errors")


if __name__ == "__main__":
    main()
