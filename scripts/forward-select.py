"""前瞻纸面预测：按预先固定的规则选出当天要研究的股票（最多 4 只）。

用法：.venv/bin/python -I scripts/forward-select.py [--date YYYY-MM-DD] [--write]
规则（详见 evals/forward/README.md）：
  1. 股票池 evals/replay/universe.txt 中，财报 8-K（Item 2.02）信号日 D0 等于“最近一个已收盘交易日”的股票，
     按 sha256("D0:代码") 排序取前 2 只（避免字母序偏向）。覆盖上次选择的信号日之后、到最近已收盘交易日之间的所有信号日，避免漏掉。D0 口径同 evals/signals/pead-v2-definition-2026-10-26.md。
  2. 剩余名额用轮转补齐：股票池按字母序去重，起点 = (date.toordinal() * 2) % 股票池大小，依次取、跳过已选。
--write：把选择结果（含每只的原因）作为 kind=selection 追加到 evals/forward/ledger.jsonl（同一天只能写一次；已写则直接输出已写内容）。
输出 JSON，其中 todo 为尚未有预测/失败记录的代码。日期按纽约时间。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
if not os.environ.get("SEC_USER_AGENT"):
    os.environ["SEC_USER_AGENT"] = json.loads((REPO / ".mcp.json").read_text())["mcpServers"]["stock-data"]["env"]["SEC_USER_AGENT"]

NY = ZoneInfo("America/New_York")
LEDGER = REPO / "evals" / "forward" / "ledger.jsonl"
MAX_TOTAL, MAX_EARNINGS = 4, 2


def universe() -> list[str]:
    names = set()
    for line in (REPO / "evals" / "replay" / "universe.txt").read_text().splitlines():
        if not line.strip().startswith("#"):
            names.update(line.split())
    return sorted(names)


def ledger_lines() -> list[dict]:
    if not LEDGER.exists():
        return []
    return [json.loads(x) for x in LEDGER.read_text().splitlines() if x.strip()]


def trading_days(run_date: date) -> list[str]:
    from product.mcp import data_tools
    rows = data_tools.get_price_history("SPY", start=(run_date - timedelta(days=30)).isoformat(),
                                        end=run_date.isoformat(), max_rows=100)["rows"]
    return sorted(r[0] for r in rows)


def signal_day(accepted: datetime, days: list[str]) -> str | None:
    """pead-v2：交易日 09:30 前受理 → 当天；否则 → 之后第一个交易日。days 中没有之后的交易日则返回 None。"""
    a = accepted.astimezone(NY)
    day = a.date().isoformat()
    if day in days and (a.hour, a.minute) < (9, 30):
        return day
    later = [d for d in days if d > day]
    return later[0] if later else None


def earnings_hits(tickers: list[str], d0s: set[str], days: list[str], cutoff: str) -> dict[str, str]:
    from product.mcp import data_tools
    from product.mcp.provenance import parse_timestamp
    hits = {}
    for i, t in enumerate(tickers):
        print(f"[{i + 1}/{len(tickers)}] {t}", file=sys.stderr, flush=True)
        try:
            rows = data_tools.list_filings(t, forms=["8-K"], limit=12, as_of=cutoff)["rows"]
        except Exception as exc:  # noqa: BLE001 - 单只失败不影响选择，记录在 errors
            hits.setdefault("_errors", {})[t] = f"{type(exc).__name__}: {exc}"[:120]
            continue
        for accession, _form, _rd, published, _url, items in rows:
            sd = signal_day(parse_timestamp(published), days)
            if "2.02" in (items or "").split(",") and sd in d0s:
                hits[t] = (sd, f"{accession} accepted {parse_timestamp(published).astimezone(NY):%Y-%m-%d %H:%M} NY")
                break
    return hits


def select(run_date: date, now_ny: datetime | None = None, prev_signal_day: str | None = None) -> dict:
    now_ny = now_ny or datetime.now(NY)
    days = trading_days(run_date)
    completed = [d for d in days if d < run_date.isoformat()
                 or (d == run_date.isoformat() and (run_date < now_ny.date() or now_ny.hour >= 16))]
    d0 = completed[-1]
    names = universe()
    cutoff = run_date.isoformat()
    # 覆盖上次选择之后到 d0 的所有信号日：价格缓存滞后、节假日或漏跑都不会跳过某个信号日。
    d0s = {d for d in completed if (prev_signal_day is None and d == d0) or (prev_signal_day is not None and prev_signal_day < d <= d0)}
    hits = earnings_hits(names, d0s, days, cutoff)
    errors = hits.pop("_errors", {})
    order = sorted(hits, key=lambda x: hashlib.sha256(f"{hits[x][0]}:{x}".encode()).hexdigest())
    chosen = [{"ticker": t, "reason": f"earnings_8k: Item 2.02, D0={hits[t][0]}, {hits[t][1]}"} for t in order[:MAX_EARNINGS]]
    start = (run_date.toordinal() * 2) % len(names)
    taken = {c["ticker"] for c in chosen}
    for i in range(len(names)):
        if len(chosen) >= MAX_TOTAL:
            break
        t = names[(start + i) % len(names)]
        if t not in taken:
            chosen.append({"ticker": t, "reason": f"rotation: index {(start + i) % len(names)} of {len(names)}, start {start}"})
            taken.add(t)
    return {"kind": "selection", "ledger_version": 1, "date": run_date.isoformat(), "signal_day": d0,
            "signal_days_covered": sorted(d0s),
            "earnings_hits_total": len(hits), "tickers": chosen, "list_errors": errors}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    run_date = date.fromisoformat(args.date) if args.date else datetime.now(NY).date()
    lines = ledger_lines()
    existing = next((x for x in lines if x.get("kind") == "selection" and x["date"] == run_date.isoformat()), None)
    prev = max((x["signal_day"] for x in lines if x.get("kind") == "selection" and x["date"] < run_date.isoformat()), default=None)
    result = existing or select(run_date, prev_signal_day=prev)
    if args.write and not existing:
        result["recorded_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        fd = os.open(LEDGER, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            os.write(fd, (json.dumps(result, ensure_ascii=False, sort_keys=True) + "\n").encode())
        finally:
            os.close(fd)
    done = {x["ticker"] for x in lines if x.get("kind") in ("prediction", "failure") and x.get("selection_date") == run_date.isoformat()}
    out = dict(result, todo=[t["ticker"] for t in result["tickers"] if t["ticker"] not in done])
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
