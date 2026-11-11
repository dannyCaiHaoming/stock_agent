"""关键图形时刻：建事件表、出统计报告、扫描最近出现关键时刻的股票。

用法：
  .venv/bin/python -I scripts/build-key-moments.py                 # 建表（股票池 evals/replay/universe.txt，2012 年起）
  .venv/bin/python -I scripts/build-key-moments.py --report 文件.md  # 建表并写统计报告
  .venv/bin/python -I scripts/build-key-moments.py --scan [--days 5] [--date YYYY-MM-DD]
        # 不建表：列出最近 N 个交易日内出现关键时刻的股票（用来决定本周研究哪几只）

定义见 product/deterministic/key_moments.py。入场 = 信号日的下一个交易日收盘；基准 = 所属板块 ETF
（.local/cache/derived/signals/meta.json 的映射，缺省 SPY）。对照 = 同一批股票每 5 个交易日取一次、不加条件。
输出 .local/cache/derived/signals/key-moments.jsonl 与 key-moments-meta.json，供 get_key_moments 按“当时已知”统计。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from product.deterministic import key_moments as km  # noqa: E402
from product.mcp import data_tools, settings  # noqa: E402


def universe() -> list[str]:
    text = (REPO / "evals/replay/universe.txt").read_text()
    return list(dict.fromkeys(t for line in text.splitlines() if not line.startswith("#") for t in line.split()))


def closes(ticker: str, start: str, end: str | None = None) -> tuple[list[str], list[float]]:
    rows = data_tools.get_price_history(ticker, start=start, end=end, as_of=end, max_rows=6000)["rows"]
    pairs = [(r[0], float(r[5] or r[4])) for r in rows if (r[5] or r[4])]
    return [d for d, _ in pairs], [c for _, c in pairs]


def scan(days: int, date: str | None) -> None:
    hits = []
    for ticker in universe():
        try:
            d, c = closes(ticker, str(int((date or datetime.now(UTC).date().isoformat())[:4]) - 2) + "-01-01", date)
        except Exception as exc:  # noqa: BLE001
            print(f"WARN {ticker}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        for m in km.detect(d, c):
            if m["index"] >= len(d) - days:
                hits.append((m["date"], ticker, m["moment"]))
    by_ticker: dict[str, list[str]] = {}
    for day, ticker, moment in sorted(hits):
        by_ticker.setdefault(ticker, []).append(f"{day} {moment}")
    print(json.dumps({"as_of": date or "latest", "days": days, "tickers": by_ticker}, ensure_ascii=False, indent=1))


def report(events: list[dict], path: Path, meta: dict) -> None:
    lines = ["# 关键图形时刻之后的收益分布", "",
             f"{len(meta['tickers'])} 只股票，{meta['start']} 起，建表于 {meta['built_at']}。定义见 `product/deterministic/key_moments.py`。",
             "入场为信号日的下一个交易日收盘。“期望”= 上涨概率 × 平均涨幅 + 下跌概率 × 平均跌幅。对照为同一批股票每 5 个交易日取一次。",
             "名单按 2026-10 的认知挑选，有幸存者偏差：所有数字（含对照）都偏高，应与对照行比较，而不是看绝对值。", ""]
    for h in km.HORIZONS:
        lines += [f"## 之后 {h} 个交易日", "",
                  "| 时刻 | 次数 | 上涨概率 | 平均涨幅 | 平均跌幅 | 期望 | 收益 25%/中位/75% | 相对板块 25%/中位/75% | 跑赢板块概率 | 途中最大回撤 中位/最差一成 |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for name in [km.BASELINE, *km.MOMENTS]:
            s = km.summarize([e["outcome"] for e in events if e["moment"] == name], h)
            if not s:
                continue
            f = lambda v: "/".join("—" if x is None else f"{x:+.1f}" for x in v)  # noqa: E731
            lines.append(f"| {name} | {s['n']} | {s['p_up']:.0%} | {s['avg_gain_pct']:+.1f} | {s['avg_loss_pct']:+.1f} | "
                         f"{s['expectancy_pct']:+.1f} | {f(s['ret_pct_q25_median_q75'])} | "
                         f"{f(s['excess_vs_benchmark_pct_q25_median_q75'])} | {s['p_excess_positive']:.0%} | "
                         f"{f(s['worst_drawdown_pct_median_q10'])} |")
        lines.append("")
    lines += ["## 时刻定义", ""] + [f"- `{k}`：{v}" for k, v in km.MOMENTS.items()] + [""]
    path.write_text("\n".join(lines), encoding="utf-8")
    print(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2012-01-01")
    parser.add_argument("--report")
    parser.add_argument("--scan", action="store_true")
    parser.add_argument("--days", type=int, default=5)
    parser.add_argument("--date")
    args = parser.parse_args()
    if args.scan:
        scan(args.days, args.date)
        return
    out_dir = settings.cache().root / "derived" / "signals"
    out_dir.mkdir(parents=True, exist_ok=True)
    benchmarks = json.loads((out_dir / "meta.json").read_text()).get("benchmarks", {}) if (out_dir / "meta.json").exists() else {}
    bench_cache: dict[str, dict[str, float]] = {}
    events, errors, tickers = [], {}, universe()
    price_start = str(int(args.start[:4]) - 2) + args.start[4:]
    for n, ticker in enumerate(tickers):
        try:
            etf = benchmarks.get(ticker, "SPY")
            if etf not in bench_cache:
                bench_cache[etf] = dict(zip(*closes(etf, price_start)))
            d, c = closes(ticker, price_start)
            for m in km.detect(d, c):
                if m["date"] >= args.start and m["index"] + 1 < len(d):
                    events.append({"moment": m["moment"], "ticker": ticker, "date": m["date"], "benchmark": etf,
                                   "detail": m["detail"], "outcome": km.outcome(d, c, bench_cache[etf], m["index"])})
            for i in range(km.MIN_HISTORY, len(d) - 1, 5):
                if d[i] >= args.start:
                    events.append({"moment": km.BASELINE, "ticker": ticker, "date": d[i], "benchmark": etf,
                                   "detail": {}, "outcome": km.outcome(d, c, bench_cache[etf], i)})
        except Exception as exc:  # noqa: BLE001 - record and continue
            errors[ticker] = f"{type(exc).__name__}: {exc}"[:200]
        print(f"{n + 1}/{len(tickers)} {ticker} events={len(events)}", file=sys.stderr, flush=True)
    with (out_dir / "key-moments.jsonl").open("w") as handle:
        for e in events:
            handle.write(json.dumps(e, ensure_ascii=False) + "\n")
    meta = {"built_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "start": args.start, "tickers": tickers,
            "errors": errors, "horizons": list(km.HORIZONS), "moments": km.MOMENTS,
            "note": "股票池按 2026-10 的认知挑选，存在幸存者偏差；板块 ETF 按当前板块映射。"}
    (out_dir / "key-moments-meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    print(out_dir / "key-moments.jsonl", len(events), "events;", len(errors), "errors")
    if args.report:
        report(events, Path(args.report), meta)


if __name__ == "__main__":
    main()
