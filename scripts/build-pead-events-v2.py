"""财报后漂移事件表 v2：按 evals/signals/pead-v2-definition-2026-10-26.md 重算（时点、入场、收益口径）。

用法：.venv/bin/python -I scripts/build-pead-events-v2.py   （先运行 scripts/build-8k-events.py）
- 时点：8-K 2.02 的 EDGAR 受理时间（纽约）。09:30 前 → P=前一交易日、D0=当天；09:30–16:00 → P=前一交易日、D0=下一交易日；
  16:00（含）之后或非交易日 → P=受理日或之前最后一个交易日、D0=下一交易日。无时间则排除。
- 信号只用 D0 收盘及之前：反应 = P→D0 收盘相对板块 ETF 的超额；放量倍数 = P 之后到 D0 的最大成交量 ÷ P 及之前 50 日均量；
  pre_run_60 = P 之前 60 日到 P 的超额；stage 用 D0 及之前收盘（150 日均线，规则同 v1）。
- 入场 D1 开盘（D0 之后第一个交易日），退出 D_h 收盘（h=5/20/60，D1..D_h 共 h 个交易日）；开盘价乘复权系数（复权收盘 ÷ 收盘）。
  超额 = 个股同窗口总收益 − 板块 ETF 同窗口总收益；path_min_h = D1..D_h 各收盘的累计超额最小值（自 D1 开盘起算）。
- 一个 (ticker, D0) 一条事件，8-K/A 重复取最早受理。对照行：每只股票每个交易日（2019-01-01 起）一条，D0=当天，同口径。
输出：.local/cache/derived/signals/events-pead-v2.jsonl 与 meta-pead-v2.json（不覆盖 v1 events-pead.jsonl）。
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if not os.environ.get("SEC_USER_AGENT"):
    os.environ["SEC_USER_AGENT"] = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["stock-data"]["env"]["SEC_USER_AGENT"]

from product.mcp import data_tools, settings  # noqa: E402

HORIZONS = (5, 20, 60)
BUCKETS = (("strong_up", 0.05, None), ("up", 0.02, 0.05), ("flat", -0.02, 0.02), ("down", -0.05, -0.02),
           ("strong_down", None, -0.05))
MIN_INDEX = 152  # same history requirement as v1 (150-day average + 20-day slope)


def bucket(x: float) -> str:
    for name, lo, hi in BUCKETS:
        if (lo is None or x > lo) and (hi is None or x <= hi):
            return name
    return "flat"


class Series:
    def __init__(self, ticker: str):
        rows = data_tools.get_price_history(ticker, start="2018-01-01", max_rows=6000)["rows"]
        rows = [r for r in rows if r[4]]
        self.dates = [r[0] for r in rows]
        self.index = {d: i for i, d in enumerate(self.dates)}
        close = np.array([float(r[4]) for r in rows])
        adj = np.array([float(r[5]) if r[5] else float(r[4]) for r in rows])
        self.adj_close = adj
        self.adj_open = np.array([float(r[1]) * a / c if r[1] else np.nan for r, a, c in zip(rows, adj, close)])
        self.volume = np.array([float(r[6] or 0) for r in rows])

    def aligned(self, dates: list[str]) -> tuple[np.ndarray, np.ndarray]:
        """(adj_open, adj_close) on the given dates; NaN where this series has no row."""
        o, c = np.full(len(dates), np.nan), np.full(len(dates), np.nan)
        for k, d in enumerate(dates):
            j = self.index.get(d)
            if j is not None:
                o[k], c[k] = self.adj_open[j], self.adj_close[j]
        return o, c


def stages(closes: np.ndarray) -> list[str]:
    n = len(closes)
    cs = np.concatenate([[0.0], np.cumsum(closes)])
    sma = [None] * n
    for i in range(149, n):
        sma[i] = (cs[i + 1] - cs[i - 149]) / 150
    out = []
    for i in range(n):
        s, p = sma[i], sma[i - 20] if i >= 20 else None
        c = closes[i]
        out.append("stage2" if s and p and c > s and s > p else "stage4" if s and p and c < s and s < p else "other")
    return out


def holding(so, sc, bo, bc, i: int, h: int) -> dict:
    """Excess return D1 open -> D_h close (D0 = index i) and the minimum cumulative excess over D1..D_h closes."""
    j = i + h
    if j >= len(sc) or np.isnan(so[i + 1]) or np.isnan(bo[i + 1]) or np.isnan(sc[j]) or np.isnan(bc[j]):
        return {}
    path = (sc[i + 1:j + 1] / so[i + 1] - 1) - (bc[i + 1:j + 1] / bo[i + 1] - 1)
    return {"x": float(path[-1]), "min": float(np.nanmin(path)), "exit_idx": j}


def locate(accepted: str, dates: list[str], index: dict[str, int]) -> tuple[int, int] | str:
    """(P index, D0 index) from the NY acceptance timestamp, or an exclusion reason."""
    day, hhmm = accepted[:10], accepted[11:16]
    if not hhmm or len(accepted) < 16:
        return "no_time"
    if day < dates[0] or day > dates[-1]:
        return "outside_price_calendar"
    pos = index.get(day)
    if pos is not None:
        if hhmm < "09:30":
            p, d0 = pos - 1, pos
        elif hhmm < "16:00":
            p, d0 = pos - 1, pos + 1
        else:
            p, d0 = pos, pos + 1
    else:  # non-trading day: last trading day on or before, then the next one
        from bisect import bisect_right
        p = bisect_right(dates, day) - 1
        d0 = p + 1
    return (p, d0) if p >= 0 else "insufficient_history"


def main() -> None:
    root = settings.cache().root / "derived" / "signals"
    meta8k = json.loads((root / "meta.json").read_text())
    earnings: dict[str, list[dict]] = {}
    for line in (root / "events-8k.jsonl").open():
        e = json.loads(line)
        if e["signal"] == "8k_item_2.02":
            earnings.setdefault(e["ticker"], []).append(e)
    excl, kept, per_ticker = Counter(), 0, {}
    bench_cache: dict[str, Series] = {}
    out = (root / "events-pead-v2.jsonl").open("w")
    total_controls = 0
    for k, (ticker, evs) in enumerate(sorted(earnings.items())):
        etf = meta8k["benchmarks"].get(ticker, "SPY")
        if etf not in bench_cache:
            bench_cache[etf] = Series(etf)
        s = Series(ticker)
        n = len(s.dates)
        bo, bc = bench_cache[etf].aligned(s.dates)
        so, sc = s.adj_open, s.adj_close
        stage = stages(sc)
        # earliest acceptance first so that 8-K/A duplicates of the same D0 are the ones dropped
        seen: set[int] = set()
        n_events = 0
        for e in sorted(evs, key=lambda x: x["detail"].get("accepted_ny") or ""):
            accepted = e["detail"].get("accepted_ny") or ""
            loc = locate(accepted, s.dates, s.index) if accepted else "no_time"
            if isinstance(loc, str):
                excl[loc] += 1
                continue
            p, d0 = loc
            if d0 >= n:
                excl["no_d1_yet"] += 1  # D0 not yet observed in the price data
                continue
            if p < MIN_INDEX or d0 < MIN_INDEX:
                excl["insufficient_history"] += 1
                continue
            if d0 in seen:
                excl["duplicate_d0"] += 1
                continue
            if d0 + 1 >= n:
                excl["no_d1_yet"] += 1
                continue
            if np.isnan(so[d0 + 1]) or np.isnan(bo[d0 + 1]):
                excl["missing_d1_open"] += 1
                continue
            if np.isnan(bc[p]) or np.isnan(bc[d0]) or np.isnan(bc[p - 60]):
                excl["missing_benchmark_close"] += 1
                continue
            seen.add(d0)
            reaction = (sc[d0] / sc[p] - 1) - (bc[d0] / bc[p] - 1)
            avg_vol = s.volume[p - 49:p + 1].mean()
            vol_ratio = s.volume[p + 1:d0 + 1].max() / avg_vol if avg_vol else None
            pre_run = (sc[p] / sc[p - 60] - 1) - (bc[p] / bc[p - 60] - 1)
            row = {"kind": "event", "ticker": ticker, "accepted_ny": accepted, "p_date": s.dates[p],
                   "signal_date": s.dates[d0], "entry_date": s.dates[d0 + 1], "benchmark": etf,
                   "reaction": round(float(reaction), 6), "bucket": bucket(reaction),
                   "volume_ratio": round(float(vol_ratio), 2) if vol_ratio else None,
                   "pre_run_60": round(float(pre_run), 6), "stage": stage[d0],
                   "accession": e["detail"].get("accession")}
            for h in HORIZONS:
                r = holding(so, sc, bo, bc, d0, h)
                if r:
                    row[str(h)] = round(r["x"], 6)
                    row[f"exit_{h}"] = s.dates[r["exit_idx"]]
                    row[f"path_min_{h}"] = round(r["min"], 6)
            out.write(json.dumps(row) + "\n")
            n_events += 1
        for i in range(MIN_INDEX, n - 1):
            if s.dates[i] < "2019-01-01":
                continue
            row = {"kind": "control", "ticker": ticker, "signal_date": s.dates[i], "entry_date": s.dates[i + 1],
                   "stage": stage[i]}
            for h in HORIZONS:
                r = holding(so, sc, bo, bc, i, h)
                if r:
                    row[str(h)] = round(r["x"], 6)
                    row[f"exit_{h}"] = s.dates[r["exit_idx"]]
            if len(row) > 5:
                out.write(json.dumps(row) + "\n")
                total_controls += 1
        kept += n_events
        per_ticker[ticker] = n_events
        print(f"{k + 1}/{len(earnings)} {ticker} earnings={n_events}", file=sys.stderr, flush=True)
    out.close()
    (root / "meta-pead-v2.json").write_text(json.dumps({
        "built_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "horizons": list(HORIZONS),
        "buckets": [b[0] for b in BUCKETS], "earnings_events": per_ticker, "n_events": kept,
        "n_controls": total_controls, "exclusions": dict(excl),
        "source_events_2_02": sum(len(v) for v in earnings.values()),
        "definition": __doc__, "universe_note": meta8k.get("universe_note"),
    }, ensure_ascii=False, indent=2))
    print(root / "events-pead-v2.jsonl", kept, "events", total_controls, "controls", dict(excl))


if __name__ == "__main__":
    main()
