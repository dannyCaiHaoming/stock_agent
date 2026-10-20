"""财报后漂移事件表：以 8-K 2.02（财报）为事件，按公告反应的方向与幅度、入场时的趋势阶段、公告日成交量放大倍数分组，
统计反应之后 5/20/60/126/252 个交易日相对板块 ETF 的超额收益。

用法：.venv/bin/python -I scripts/build-pead-events.py   （先运行 scripts/build-8k-events.py）
- 反应：公告前最后一个收盘（入场日的前两个交易日收盘，覆盖盘前与盘后公告）到入场日收盘，相对板块 ETF 的超额涨跌。
- 入场：8-K 受理后的第一个可交易收盘（16:00 前受理用当天收盘，否则次日收盘），即反应已经可见之后。
- 分组门槛事先固定：大涨 > +5%、小涨 +2%～+5%、持平 ±2%、小跌 −5%～−2%、大跌 < −5%。
- 趋势阶段（只用入场日及之前的价格）：stage2 = 收盘 > 150 日均线且均线较 20 日前上升；stage4 = 收盘 < 150 日均线且均线下降；其他。
- 对照：每个交易日、每只股票一条（同样记录趋势阶段），用于同日对照与同日同阶段对照。
输出：.local/cache/derived/signals/events-pead.jsonl 与 meta-pead.json。
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if not os.environ.get("SEC_USER_AGENT"):
    os.environ["SEC_USER_AGENT"] = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["stock-data"]["env"]["SEC_USER_AGENT"]

from product.mcp import data_tools, settings  # noqa: E402

HORIZONS = (5, 20, 60, 126, 252)
BUCKETS = (("strong_up", 0.05, None), ("up", 0.02, 0.05), ("flat", -0.02, 0.02), ("down", -0.05, -0.02),
           ("strong_down", None, -0.05))


def bucket(x: float) -> str:
    for name, lo, hi in BUCKETS:
        if (lo is None or x > lo) and (hi is None or x <= hi):
            return name
    return "flat"


def series(ticker: str) -> tuple[list[str], list[float], list[float]]:
    rows = data_tools.get_price_history(ticker, start="2018-01-01", max_rows=6000)["rows"]
    rows = [r for r in rows if (r[5] or r[4])]
    return [r[0] for r in rows], [float(r[5] or r[4]) for r in rows], [float(r[6] or 0) for r in rows]


def stages(closes: list[float]) -> list[str]:
    out, run = [], 0.0
    sma = []
    for i, c in enumerate(closes):
        run += c
        if i >= 150:
            run -= closes[i - 150]
        sma.append(run / 150 if i >= 149 else None)
    for i, c in enumerate(closes):
        s, p = sma[i], sma[i - 20] if i >= 20 else None
        out.append("stage2" if s and p and c > s and s > p else "stage4" if s and p and c < s and s < p else "other")
    return out


def forward(dates, closes, bench, i) -> dict:
    out = {}
    for h in HORIZONS:
        j = i + h
        if j < len(dates) and dates[i] in bench and dates[j] in bench:
            out[str(h)] = (closes[j] / closes[i] - 1) - (bench[dates[j]] / bench[dates[i]] - 1)
            out[f"exit_{h}"] = dates[j]
    return out


def main() -> None:
    root = settings.cache().root / "derived" / "signals"
    meta8k = json.loads((root / "meta.json").read_text())
    earnings: dict[str, list[dict]] = {}
    for line in (root / "events-8k.jsonl").open():
        e = json.loads(line)
        if e["signal"] == "8k_item_2.02":
            earnings.setdefault(e["ticker"], []).append(e)
    out = (root / "events-pead.jsonl").open("w")
    counts, bench_cache = {}, {}
    for k, (ticker, evs) in enumerate(sorted(earnings.items())):
        etf = meta8k["benchmarks"].get(ticker, "SPY")
        if etf not in bench_cache:
            d, c, _ = series(etf)
            bench_cache[etf] = dict(zip(d, c))
        bench = bench_cache[etf]
        dates, closes, volume = series(ticker)
        stage = stages(closes)
        index = {d: i for i, d in enumerate(dates)}
        seen = set()
        n = 0
        for e in evs:
            i = index.get(e["entry_date"])
            if i is None or i < 152 or e["entry_date"] in seen or dates[i - 2] not in bench or dates[i] not in bench:
                continue
            seen.add(e["entry_date"])  # one event per earnings date (8-K/A duplicates)
            reaction = (closes[i] / closes[i - 2] - 1) - (bench[dates[i]] / bench[dates[i - 2]] - 1)
            avg_vol = sum(volume[i - 52:i - 2]) / 50 if i >= 52 else 0
            vol_ratio = max(volume[i - 1], volume[i]) / avg_vol if avg_vol else None
            row = {"kind": "event", "ticker": ticker, "entry_date": dates[i], "benchmark": etf,
                   "reaction": round(reaction, 6), "bucket": bucket(reaction), "stage": stage[i],
                   "volume_ratio": round(vol_ratio, 2) if vol_ratio else None,
                   "accession": e["detail"].get("accession"), **forward(dates, closes, bench, i)}
            out.write(json.dumps(row) + "\n")
            n += 1
        for i in range(152, len(dates)):
            if dates[i] < "2019-01-01" or dates[i] not in bench:
                continue
            out.write(json.dumps({"kind": "control", "ticker": ticker, "entry_date": dates[i], "stage": stage[i],
                                  **forward(dates, closes, bench, i)}) + "\n")
        counts[ticker] = n
        print(f"{k + 1}/{len(earnings)} {ticker} earnings={n}", file=sys.stderr, flush=True)
    out.close()
    (root / "meta-pead.json").write_text(json.dumps({
        "built_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "horizons": list(HORIZONS),
        "buckets": [b[0] for b in BUCKETS], "earnings_events": counts,
        "definition": __doc__, "universe_note": meta8k.get("universe_note"),
    }, ensure_ascii=False, indent=2))
    print(root / "events-pead.jsonl", sum(counts.values()), "earnings events")


if __name__ == "__main__":
    main()
