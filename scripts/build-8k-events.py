"""8-K 事项代码事件表：每份 8-K 的每个事项（Item）一个事件，按可交易时点入场，持有 1/5/20/60 个交易日。

用法：.venv/bin/python -I scripts/build-8k-events.py [--tickers AAPL,MSFT] [--start 2019-01-01]
对照：同一股票池每个交易日的样本（baseline_days_daily），用于同日对照。
输出：.local/cache/derived/signals/events-8k.jsonl 与 meta-8k.json。
"""

from __future__ import annotations

import argparse
import json
import os
import random
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
from product.mcp.live.sec import parse_index_accepted  # noqa: E402
from product.mcp.live.sec_client import SecClient  # noqa: E402
from product.mcp.provenance import parse_timestamp  # noqa: E402


def closes(ticker: str, start: str) -> tuple[list[str], list[float]]:
    rows = data_tools.get_price_history(ticker, start=start, max_rows=6000)["rows"]
    pairs = [(r[0], float(r[5] or r[4])) for r in rows if (r[5] or r[4])]
    return [d for d, _ in pairs], [c for _, c in pairs]


def verify_acceptance_sample(client: SecClient, samples: list[tuple[str, str, str, str]], n: int) -> list[str]:
    """抽样核对 acceptanceDateTime：与 EDGAR 索引页 “Accepted”（纽约时间）逐秒一致，否则返回不一致清单。

    2026-10 中旬 SEC 曾把部分响应的该字段整体多加一次纽约时差，缓存后被事件表沿用（见
    evals/signals/data-correction-8k-timestamps-2026-10-27.md）；JSON 自身无法识别，所以建表前必须抽样核对。
    """
    bad = []
    for ticker, cik, accession, published_at in random.Random(20261027).sample(samples, min(n, len(samples))):
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{accession}-index.htm"
        record = client.fetch(url, max_age_seconds=0, stable_document=True)
        if abs((parse_timestamp(published_at) - parse_index_accepted(client.cache.read(record))).total_seconds()) > 1:
            bad.append(f"{ticker} {accession} json={published_at} index={parse_index_accepted(client.cache.read(record)).isoformat()}")
    return bad


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tickers")
    parser.add_argument("--start", default="2019-01-01")
    parser.add_argument("--verify-sample", type=int, default=60, help="抽样核对受理时间的申报数（0 = 不核对）")
    args = parser.parse_args()
    out_dir = settings.cache().root / "derived" / "signals"
    meta_main = json.loads((out_dir / "meta.json").read_text())  # sector ETF mapping from build-signal-events
    tickers = args.tickers.split(",") if args.tickers else meta_main["tickers"]
    bench_map = meta_main["benchmarks"]
    bench_cache: dict[str, dict[str, float]] = {}
    events, errors, counts, samples = [], {}, {}, []
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
                samples.append((ticker, identity["cik"], f["accession"], f["published_at"]))
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
    bad = verify_acceptance_sample(SecClient(settings.cache(), user_agent=settings.sec_user_agent(), request_budget=1000),
                                   samples, args.verify_sample) if args.verify_sample else []
    if bad:
        raise SystemExit("acceptanceDateTime 与 EDGAR 索引页不一致，未写出事件表（先刷新 SEC 缓存）：\n" + "\n".join(bad[:10]))
    print(f"acceptance sample check passed: {min(args.verify_sample, len(samples))} filings", file=sys.stderr)
    with (out_dir / "events-8k.jsonl").open("w") as handle:
        for e in events:
            handle.write(json.dumps(asdict(e), ensure_ascii=False) + "\n")
    (out_dir / "meta-8k.json").write_text(json.dumps({
        "built_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "start": args.start, "tickers": tickers, "filings_8k": counts,
        "errors": errors, "acceptance_sample_checked": min(args.verify_sample, len(samples)), "horizons": list(signal_events.EVENT_HORIZONS), "items": signal_events.FORM_8K_ITEMS,
        "entry_rule": "8-K accepted before 16:00 New York on a trading day: that close; otherwise next session close",
        "universe_note": meta_main.get("universe_note"),
    }, ensure_ascii=False, indent=2))
    print(out_dir / "events-8k.jsonl", len(events), "events;", len(errors), "errors")


if __name__ == "__main__":
    main()
