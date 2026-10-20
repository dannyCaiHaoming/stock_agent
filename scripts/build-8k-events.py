"""8-K 事项代码事件表：每份 8-K 的每个事项（Item）一个事件，按可交易时点入场，持有 1/5/20/60 个交易日。

用法：.venv/bin/python -I scripts/build-8k-events.py [--tickers AAPL,MSFT] [--start 2019-01-01]
对照：同一股票池每个交易日的样本（baseline_days_daily），用于同日对照。
输出：.local/cache/derived/signals/events-8k.jsonl 与 meta-8k.json。
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
from product.mcp import data_tools, settings  # noqa: E402
from product.mcp.live.sec_client import SecClient  # noqa: E402
from product.mcp.provenance import parse_timestamp  # noqa: E402


def closes(ticker: str, start: str) -> tuple[list[str], list[float]]:
    rows = data_tools.get_price_history(ticker, start=start, max_rows=6000)["rows"]
    pairs = [(r[0], float(r[5] or r[4])) for r in rows if (r[5] or r[4])]
    return [d for d, _ in pairs], [c for _, c in pairs]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers")
    parser.add_argument("--start", default="2019-01-01")
    args = parser.parse_args()
    out_dir = settings.cache().root / "derived" / "signals"
    meta_main = json.loads((out_dir / "meta.json").read_text())  # sector ETF mapping from build-signal-events
    tickers = args.tickers.split(",") if args.tickers else meta_main["tickers"]
    bench_map = meta_main["benchmarks"]
    bench_cache: dict[str, dict[str, float]] = {}
    events, errors, counts = [], {}, {}
    now = datetime.now(UTC)
    for i, ticker in enumerate(tickers):
        try:
            etf = bench_map.get(ticker, "SPY")
            if etf not in bench_cache:
                d, c = closes(etf, "2018-01-01")
                bench_cache[etf] = dict(zip(d, c))
            dates, prices = closes(ticker, "2018-01-01")
            identity = data_tools.resolve_company(ticker)
            client = SecClient(settings.cache(), user_agent=settings.sec_user_agent(), request_budget=200)
            filings, _ = data_tools._submissions(identity, client, now, history_years=8)
            rows = []
            for f in filings.values():
                if f["form"] not in ("8-K", "8-K/A") or f["published_at"][:10] < args.start:
                    continue
                accepted = parse_timestamp(f["published_at"]).astimezone(data_tools.NEW_YORK)
                rows.append({"accession": f["accession"], "items": f.get("items") or [],
                             "accepted_ny": accepted.strftime("%Y-%m-%dT%H:%M")})
            counts[ticker] = len(rows)
            events += signal_events.form_8k_events(ticker, rows, dates, prices, bench_cache[etf], etf)
            events += [e for e in signal_events.baseline_events(ticker, dates, prices, bench_cache[etf], etf,
                                                                signal_events.EVENT_HORIZONS, "baseline_days_daily",
                                                                step=1) if e.signal_date >= args.start]
        except Exception as exc:  # noqa: BLE001 - record and continue
            errors[ticker] = f"{type(exc).__name__}: {exc}"[:200]
        print(f"{i + 1}/{len(tickers)} {ticker} 8-K={counts.get(ticker)} events={len(events)}", file=sys.stderr, flush=True)
    with (out_dir / "events-8k.jsonl").open("w") as handle:
        for e in events:
            handle.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
    (out_dir / "meta-8k.json").write_text(json.dumps({
        "built_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "start": args.start, "tickers": tickers, "filings_8k": counts,
        "errors": errors, "horizons": list(signal_events.EVENT_HORIZONS), "items": signal_events.FORM_8K_ITEMS,
        "entry_rule": "8-K accepted before 16:00 New York on a trading day: that close; otherwise next session close",
        "universe_note": meta_main.get("universe_note"),
    }, ensure_ascii=False, indent=2))
    print(out_dir / "events-8k.jsonl", len(events), "events;", len(errors), "errors")


if __name__ == "__main__":
    main()
