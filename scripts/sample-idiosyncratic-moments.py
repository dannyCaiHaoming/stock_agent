"""抽取“个股走势明显偏离板块”的关键时刻，供消息面复盘使用。

偏离 = 时刻当日之前 5 个交易日（含当日）个股收益减板块 ETF 收益，除以个股日波动 × √5。
|偏离| ≥ 2 视为个股自身因素（消息类型不限：公告、传闻、对手、评级、政策、资金面……由复盘去查）。
阈值事先固定，不按结果调整。只用时刻当日收盘前的价格，抽样不看之后的结果，只要求 60 日结果已经可知（便于事后对照）。

用法：
  .venv/bin/python -I scripts/sample-idiosyncratic-moments.py --n 20 --seed 7 --out 文件.json [--exclude 已用样本.json]
  .venv/bin/python -I scripts/sample-idiosyncratic-moments.py --recent 5
        # 前瞻用：不读事件表，按最新价格找最近 N 个交易日内出现、且满足偏离条件的时刻，JSON 输出到标准输出
"""

from __future__ import annotations

import argparse
import json
import random
from datetime import date
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from product.deterministic import decision_events as de  # noqa: E402
from product.deterministic import key_moments as km  # noqa: E402
from product.mcp import data_tools, settings  # noqa: E402

WINDOW = de.WINDOW
THRESHOLD = de.THRESHOLD
START = "2019-01-01"

_prices: dict[str, dict[str, float]] = {}


def prices(ticker: str) -> tuple[list[str], dict[str, float]]:
    if ticker not in _prices:
        rows = data_tools.get_price_history(ticker, start="2017-01-01", max_rows=6000)["rows"]
        _prices[ticker] = {r[0]: float(r[5] or r[4]) for r in rows if (r[5] or r[4])}
    p = _prices[ticker]
    return sorted(p), p


def deviation(ticker: str, bench: str, day: str) -> float | None:
    dates, p = prices(ticker)
    _, b = prices(bench)
    if day not in p:
        return None
    return de.deviation_z(p, b, dates, dates.index(day))


def recent(days: int) -> list[dict]:
    text = (REPO / "evals/replay/universe.txt").read_text()
    tickers = list(dict.fromkeys(t for line in text.splitlines() if not line.startswith("#") for t in line.split()))
    meta = settings.cache().root / "derived/signals/meta.json"
    benchmarks = json.loads(meta.read_text()).get("benchmarks", {}) if meta.exists() else {}
    out = []
    for ticker in tickers:
        try:
            dates, p = prices(ticker)
            bench = benchmarks.get(ticker, "SPY")
            for m in km.detect(dates, [p[d] for d in dates]):
                if m["index"] < len(dates) - days:
                    continue
                z = deviation(ticker, bench, m["date"])
                if z is not None and abs(z) >= THRESHOLD:
                    out.append({"ticker": ticker, "moment": m["moment"], "date": m["date"], "benchmark": bench,
                                "deviation_vs_sector": round(z, 2)})
        except Exception as exc:  # noqa: BLE001 - one bad ticker must not stop the scan
            print(f"WARN {ticker}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out")
    parser.add_argument("--recent", type=int, help="前瞻：最近 N 个交易日内的偏离时刻，输出 JSON")
    parser.add_argument("--exclude", nargs="*", default=[])
    parser.add_argument("--per-ticker", type=int, default=1, help="每只股票最多几个时刻（相隔至少 90 天）")
    args = parser.parse_args()
    if args.recent:
        print(json.dumps(recent(args.recent), ensure_ascii=False, indent=1))
        return
    if not args.out:
        parser.error("--out is required unless --recent is given")
    used = {(x["ticker"], x["date"]) for f in args.exclude for x in json.loads(Path(f).read_text())}
    events = [json.loads(l) for l in (settings.cache().root / "derived/signals/key-moments.jsonl").open()]
    events = [e for e in events if e["moment"] != "baseline_days" and e["date"] >= START
              and (e["ticker"], e["date"]) not in used and (e["outcome"] or {}).get("60")]
    random.Random(args.seed).shuffle(events)
    picked, tickers, days, checked = [], {}, set(), 0
    for e in events:
        if len(picked) >= args.n:
            break
        prior = tickers.get(e["ticker"], [])
        if len(prior) >= args.per_ticker or (e["ticker"], e["date"]) in days \
                or any(abs((date.fromisoformat(e["date"]) - date.fromisoformat(p)).days) < 90 for p in prior):
            continue
        checked += 1
        z = deviation(e["ticker"], e["benchmark"], e["date"])
        if z is None or abs(z) < THRESHOLD:
            continue
        picked.append({"ticker": e["ticker"], "moment": e["moment"], "date": e["date"], "benchmark": e["benchmark"],
                       "deviation_vs_sector": round(z, 2)})
        tickers.setdefault(e["ticker"], []).append(e["date"])
        days.add((e["ticker"], e["date"]))
    Path(args.out).write_text(json.dumps(picked, ensure_ascii=False, indent=1))
    print(f"checked {checked}, picked {len(picked)} (share passing {len(picked) / max(checked, 1):.0%})", file=sys.stderr)
    for x in picked:
        print(x["ticker"], x["moment"], x["date"], x["deviation_vs_sector"])


if __name__ == "__main__":
    main()
