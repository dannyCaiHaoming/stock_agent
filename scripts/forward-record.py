"""前瞻纸面预测：把一次已结束的研究运行记入 evals/forward/ledger.jsonl（只追加）。

用法：.venv/bin/python -I scripts/forward-record.py <run-dir> [--date YYYY-MM-DD]
成功：kind=prediction（含决策与报告 sha256）；运行失败或没有保存决策：kind=failure，使 missing 可见。
拒绝：同一 run_id 已有记录。账本只用 O_APPEND 追加，从不改写已有行。
--date：对应 forward-select 的选择日（默认取 run.json 的 started_at 的纽约日期）。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "evals" / "forward" / "ledger.jsonl"
NY = ZoneInfo("America/New_York")
PAPER_RULE = {
    "entry": "prediction_time 之后的下一个交易日开盘（09:30 前做出的预测用当天开盘）",
    "exits": "入场后第 20、60 个交易日收盘",
    "excess": "个股同窗口收益减 benchmark_etf 同窗口收益",
    "cost_round_trip_pct": 0.2,
}


def parse_utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def first_paragraph(text: str, limit: int = 800) -> str:
    para = next((p.strip() for p in text.split("\n\n") if p.strip()), "")
    return para[:limit]


def build(run_dir: Path, date_arg: str | None, lines: list[dict]) -> dict:
    run_id = run_dir.name
    meta = json.loads((run_dir / "run.json").read_text()) if (run_dir / "run.json").exists() else {}
    ticker = meta.get("ticker") or run_id.split("-")[2]
    started = meta.get("started_at")
    sel_date = date_arg or (parse_utc(started).astimezone(NY).date().isoformat() if started else None)
    selection = next((x for x in lines if x.get("kind") == "selection" and x["date"] == sel_date), None)
    reason = next((t["reason"] for t in (selection or {}).get("tickers", []) if t["ticker"] == ticker), None)
    base = {"ledger_version": 1, "recorded_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), "run_id": run_id,
            "selection_date": sel_date, "ticker": ticker, "selection_reason": reason, "host": meta.get("host"),
            "model": meta.get("observed_model") or meta.get("model"), "started_at": started,
            "research_prompt": "我目前未持有。"}
    decisions = []
    if (run_dir / "decisions.jsonl").exists():
        decisions = [json.loads(x) for x in (run_dir / "decisions.jsonl").read_text().splitlines() if x.strip()]
    decisions = [d for d in decisions if d.get("ticker") == ticker]
    if meta.get("exit_code", 0) != 0 or not decisions:
        why = "run_failed" if meta.get("exit_code", 0) != 0 else "no_decision_saved"
        if not meta:
            why = "run_json_missing"
        return dict(base, kind="failure", status=why, exit_code=meta.get("exit_code"))
    d = decisions[-1]
    report = Path(d["report_path"])
    if not report.is_absolute():
        report = run_dir / report
    if not report.exists():
        return dict(base, kind="failure", status="report_missing", decision_id=d.get("decision_id"))
    archive = REPO / "evals" / "forward" / "reports" / d["decided_at"][:10] / f"{ticker}-{d['decision_id']}.md"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        with archive.open("xb") as handle:  # frozen copy committed with the ledger
            handle.write(report.read_bytes())
    benchmarks = json.loads((REPO / ".local/cache/derived/signals/meta.json").read_text()).get("benchmarks", {})
    return dict(base, kind="prediction", status="ok", decision_id=d["decision_id"], prediction_time=d["decided_at"],
                info_cutoff=d["data_as_of"], code_version=d.get("code_version"), methods=d.get("methods"),
                action=d["action"], confidence=d["confidence"], horizon=d["horizon"], forecasts=d["forecasts"],
                expected_return_pct=d.get("expected_return_pct"), price_at_decision=d.get("price_at_decision"),
                key_reason=first_paragraph(d["thesis"]), invalidation=d.get("invalidation"),
                no_trade_reason=d.get("no_trade_reason"), benchmark_etf=benchmarks.get(ticker, "SPY"),
                paper_rule=PAPER_RULE, report_path=str(archive.relative_to(REPO)),
                report_sha256=hashlib.sha256(report.read_bytes()).hexdigest())


def append(line: dict, ledger: Path) -> None:
    ledger.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(ledger, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        os.write(fd, (json.dumps(line, ensure_ascii=False, sort_keys=True) + "\n").encode())
    finally:
        os.close(fd)


def main() -> int:
    global LEDGER
    parser = argparse.ArgumentParser()
    parser.add_argument("run_dir")
    parser.add_argument("--date")
    parser.add_argument("--ledger", help="仅测试用：改写账本路径")
    args = parser.parse_args()
    if args.ledger:
        LEDGER = Path(args.ledger)
    run_dir = Path(args.run_dir).resolve()
    lines = [json.loads(x) for x in LEDGER.read_text().splitlines() if x.strip()] if LEDGER.exists() else []
    if any(x.get("run_id") == run_dir.name for x in lines):
        print(f"DUPLICATE_RUN_ID: {run_dir.name} 已在账本中，拒绝重复记录", file=sys.stderr)
        return 3
    line = build(run_dir, args.date, lines)
    append(line, LEDGER)
    print(json.dumps({k: line.get(k) for k in ("kind", "status", "run_id", "ticker", "action", "confidence", "report_sha256")},
                     ensure_ascii=False))
    return 0 if line["kind"] == "prediction" else 1


if __name__ == "__main__":
    raise SystemExit(main())
