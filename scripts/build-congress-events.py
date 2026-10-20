"""众议院议员交易事件表：以申报日为公开时点，次一交易日收盘入场，持有 5/20/60/126/252 日，相对板块 ETF。

用法：.venv/bin/python -I scripts/build-congress-events.py   （先建 PTR 索引与 build-signal-events 的 meta.json）
“高胜率议员”在每个事件当时判断：只用该申报日之前已走完 252 个交易日的历史买入（任意股票，相对 SPY），
至少 10 笔、胜率 ≥ 55%、中位超额 > 0。
事件：congress_buy、congress_buy_skilled、congress_buy_large（金额下限 ≥ $50,001）、
      congress_buy_cluster（30 天内 ≥ 2 位不同议员买入，在第二位申报日触发）、congress_sell。
输出：.local/cache/derived/signals/events-congress.jsonl 与 meta-congress.json。
"""

from __future__ import annotations

import bisect
import json
import os
import re
import statistics
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if not os.environ.get("SEC_USER_AGENT"):
    os.environ["SEC_USER_AGENT"] = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["stock-data"]["env"]["SEC_USER_AGENT"]

from product.mcp import congress_tools, data_tools, settings  # noqa: E402

HORIZONS = (5, 20, 60, 126, 252)
_PRICES: dict[str, tuple[list[str], list[float]] | None] = {}


def prices(ticker: str):
    if ticker not in _PRICES:
        try:
            rows = data_tools.get_price_history(ticker, start="2018-06-01", max_rows=6000)["rows"]
            rows = [r for r in rows if (r[5] or r[4])]
            _PRICES[ticker] = ([r[0] for r in rows], [float(r[5] or r[4]) for r in rows])
        except Exception:  # noqa: BLE001 - delisted / unknown symbols
            _PRICES[ticker] = None
    return _PRICES[ticker]


def forward(ticker: str, filed: str, bench_ticker: str, horizons=HORIZONS) -> tuple[str | None, dict]:
    p, b = prices(ticker), prices(bench_ticker)
    if not p or not b:
        return None, {}
    dates, closes = p
    bmap = dict(zip(*b))
    i = bisect.bisect_right(dates, filed)  # first session after the filing date
    if i >= len(dates) or dates[i] not in bmap:
        return None, {}
    out = {}
    for h in horizons:
        j = i + h
        if j < len(dates) and dates[j] in bmap and closes[i] > 0 and bmap[dates[i]] > 0:
            out[str(h)] = (closes[j] / closes[i] - 1) - (bmap[dates[j]] / bmap[dates[i]] - 1)
            out[f"exit_{h}"] = dates[j]
    return dates[i], out


def amount_low(text: str) -> int:
    m = re.search(r"\$([\d,]+)", text or "")
    return int(m.group(1).replace(",", "")) if m else 0


def main() -> None:
    root = settings.cache().root / "derived"
    meta = json.loads((root / "signals" / "meta.json").read_text())
    universe = set(meta["tickers"])
    trades = []
    for path in sorted((root / "house-ptr").glob("*.json")):
        for report in json.loads(path.read_text())["reports"].values():
            for row in report["rows"]:
                if row["asset_type"] in ("ST", "OP") and row["type"] in ("purchase", "sale", "partial_sale"):
                    trades.append({**row, "member": report["member"], "filed": report["filed"]})
    trades = [t for t in trades if t["filed"] >= "2019-01-01"]
    # member track record inputs: every purchase (any ticker) with its 252-session excess vs SPY
    record: dict[str, list[tuple[str, float]]] = {}
    buys = [t for t in trades if t["type"] == "purchase"]
    for k, t in enumerate(buys):
        _, out = forward(t["ticker"], t["filed"], "SPY", (252,))
        if "252" in out:
            record.setdefault(t["member"], []).append((out["exit_252"], out["252"]))
        if k % 500 == 0:
            print(f"track record {k}/{len(buys)}", file=sys.stderr, flush=True)
    for v in record.values():
        v.sort()

    def skilled(member: str, filed: str) -> bool:
        known = [x for exit_date, x in record.get(member, []) if exit_date < filed]
        return len(known) >= 10 and sum(x > 0 for x in known) / len(known) >= 0.55 and statistics.median(known) > 0

    out = (root / "signals" / "events-congress.jsonl").open("w")
    counts: dict[str, int] = {}
    mine = sorted((t for t in trades if t["ticker"] in universe), key=lambda t: t["filed"])
    last_cluster: dict[str, str] = {}
    for t in mine:
        etf = meta["benchmarks"].get(t["ticker"], "SPY")
        entry, fwd = forward(t["ticker"], t["filed"], etf)
        if not entry:
            continue
        base = {"kind": "event", "ticker": t["ticker"], "filed": t["filed"], "entry_date": entry, "benchmark": etf,
                "member": t["member"], "amount": t["amount"], "asset_type": t["asset_type"], **fwd}

        def emit(signal: str) -> None:
            out.write(json.dumps({**base, "signal": signal}) + "\n")
            counts[signal] = counts.get(signal, 0) + 1
        if t["type"] == "purchase":
            emit("congress_buy")
            if skilled(t["member"], t["filed"]):
                emit("congress_buy_skilled")
            if amount_low(t["amount"]) >= 50_001:
                emit("congress_buy_large")
            start = (date.fromisoformat(t["filed"]) - timedelta(days=30)).isoformat()
            others = {x["member"] for x in mine if x["ticker"] == t["ticker"] and x["type"] == "purchase"
                      and start <= x["filed"] <= t["filed"] and x["member"] != t["member"]}
            if others and last_cluster.get(t["ticker"], "0000") < start:
                last_cluster[t["ticker"]] = t["filed"]
                emit("congress_buy_cluster")
        else:
            emit("congress_sell")
    out.close()
    (root / "signals" / "meta-congress.json").write_text(json.dumps({
        "built_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "events": counts,
        "members_with_record": len(record), "definition": __doc__}, ensure_ascii=False, indent=2))
    print(counts)


if __name__ == "__main__":
    main()
