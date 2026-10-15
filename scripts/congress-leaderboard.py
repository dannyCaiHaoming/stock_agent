"""众议院议员交易的历史胜率排行（按申报日起算，相对 SPY 的超额收益）。

用法：.venv/bin/python -I scripts/congress-leaderboard.py 2025-01-01 [--horizon 252] [--min-trades 10]
只统计在 as_of 之前已经走完持有期的交易；输出 evals/replay/congress-leaderboard-<as_of>.md。
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if not os.environ.get("SEC_USER_AGENT"):
    os.environ["SEC_USER_AGENT"] = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["stock-data"]["env"]["SEC_USER_AGENT"]

from product.mcp import calc_tools, congress_tools  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("as_of")
parser.add_argument("--horizon", type=int, default=252)
parser.add_argument("--min-trades", type=int, default=10)
args = parser.parse_args()

known_until = date.fromisoformat(args.as_of) - timedelta(days=int(args.horizon * 1.45) + 7)
trades = [t for t in congress_tools._member_trades("", known_until)]
dates_by_ticker: dict[str, set[str]] = {}
for t in trades:
    dates_by_ticker.setdefault(t["ticker"], set()).add(t["filed"])
excess: dict[tuple[str, str], float] = {}
for i, (ticker, days) in enumerate(sorted(dates_by_ticker.items())):
    days = sorted(days)
    for chunk in range(0, len(days), 40):
        try:
            result = calc_tools.forward_returns(ticker, days[chunk:chunk + 40], horizons_days=[args.horizon],
                                                as_of=args.as_of)
        except Exception:  # noqa: BLE001 - delisted / unknown symbols
            break
        for row in result["rows"]:
            value = row.get(f"excess_{args.horizon}d_pct")
            if value is not None:
                excess[(ticker, row["date"])] = float(value)
    if i % 100 == 0:
        print(f"{i}/{len(dates_by_ticker)} tickers", file=sys.stderr, flush=True)

by_member: dict[str, dict[str, list[float]]] = {}
for t in trades:
    value = excess.get((t["ticker"], t["filed"]))
    if value is None:
        continue
    side = "buy" if t["type"] == "purchase" else "sell"
    by_member.setdefault(t["member"], {"buy": [], "sell": []})[side].append(value)


def stats(values: list[float], buy: bool) -> tuple[int, float | None, float | None]:
    if not values:
        return 0, None, None
    hits = sum((v > 0) if buy else (v < 0) for v in values)
    return len(values), round(hits / len(values), 2), round(statistics.median(values), 1)


all_buys = [v for m in by_member.values() for v in m["buy"]]
all_sells = [v for m in by_member.values() for v in m["sell"]]
lines = [f"# 众议院议员交易胜率排行（as_of {args.as_of}，申报日起 {args.horizon} 个交易日，相对 SPY）", "",
         f"只统计 {known_until} 之前申报、持有期已走完的股票/期权交易；索引年份见 `.local/cache/derived/house-ptr/`。",
         "", "## 全体基准", "",
         f"- 买入：n={stats(all_buys, True)[0]}，胜率 {stats(all_buys, True)[1]}，中位超额 {stats(all_buys, True)[2]}%",
         f"- 卖出：n={stats(all_sells, False)[0]}，卖对比例 {stats(all_sells, False)[1]}，中位超额 {stats(all_sells, False)[2]}%",
         "", f"## 买入笔数 ≥ {args.min_trades} 的议员（按买入胜率排序）", "",
         "| 议员 | 买入笔数 | 买入胜率 | 买入中位超额% | 卖出笔数 | 卖对比例 |", "|---|---|---|---|---|---|"]
rows = []
for member, sides in by_member.items():
    n, hit, med = stats(sides["buy"], True)
    if n >= args.min_trades:
        sn, shit, _ = stats(sides["sell"], False)
        rows.append((hit, med, member, n, sn, shit))
for hit, med, member, n, sn, shit in sorted(rows, reverse=True):
    lines.append(f"| {member} | {n} | {hit} | {med} | {sn} | {shit} |")
out = REPO / "evals/replay" / f"congress-leaderboard-{args.as_of}.md"
out.write_text("\n".join(lines) + "\n")
print(out)
