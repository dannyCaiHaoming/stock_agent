"""抽取“个股走势明显偏离板块”的关键时刻，供消息面复盘使用。

偏离 = 时刻当日之前 5 个交易日（含当日）个股收益减板块 ETF 收益，除以个股日波动 × √5。
|偏离| ≥ 2 视为个股自身因素（消息类型不限：公告、传闻、对手、评级、政策、资金面……由复盘去查）。
阈值事先固定，不按结果调整。只用时刻当日收盘前的价格，抽样不看之后的结果，只要求 60 日结果已经可知（便于事后对照）。

用法：
  .venv/bin/python -I scripts/sample-idiosyncratic-moments.py --n 20 --seed 7 --out 文件.json [--exclude 已用样本.json]
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
from datetime import date
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from product.mcp import data_tools, settings  # noqa: E402

WINDOW = 5
THRESHOLD = 2.0
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
    i = dates.index(day)
    if i < 121:
        return None
    rets = [p[dates[k]] / p[dates[k - 1]] - 1 for k in range(i - 120, i - WINDOW + 1)]
    vol = statistics.pstdev(rets)
    d0 = dates[i - WINDOW]
    if not vol or d0 not in b or day not in b:
        return None
    excess = (p[day] / p[d0] - 1) - (b[day] / b[d0] - 1)
    return excess / (vol * WINDOW ** 0.5)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--out", required=True)
    parser.add_argument("--exclude", nargs="*", default=[])
    parser.add_argument("--per-ticker", type=int, default=1, help="每只股票最多几个时刻（相隔至少 90 天）")
    args = parser.parse_args()
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
