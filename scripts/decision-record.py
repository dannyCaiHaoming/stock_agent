"""决策账本：把一条 decision/v2 记录追加到 evals/forward/decision-ledger.jsonl（只追加、同一 id 不重复）。

用法：.venv/bin/python -I scripts/decision-record.py <decision_id> [--data-dir DIR] [--ledger FILE]
记录取自 <data dir>/trade_decisions.jsonl（默认 STOCK_AGENT_DATA_DIR，否则 <repo>/.local/data）；
追加前核对：schema 为 decision/v2、报告文件存在且 sha256 与记录一致、账本里没有同一 decision_id。
账本只用 O_APPEND 追加，从不改写已有行；加 flock 防并发重复。
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LEDGER = REPO / "evals" / "forward" / "decision-ledger.jsonl"


def data_dir(arg: str | None) -> Path:
    configured = arg or os.environ.get("STOCK_AGENT_DATA_DIR")
    return Path(configured).expanduser().resolve() if configured else REPO / ".local" / "data"


def find_record(root: Path, decision_id: str) -> dict:
    path = root / "trade_decisions.jsonl"
    if not path.exists():
        raise SystemExit(f"REFUSED: {path} does not exist")
    found = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    found = [r for r in found if r.get("decision_id") == decision_id]
    if not found:
        raise SystemExit(f"REFUSED: decision_id {decision_id} is not in {path}")
    return found[-1]


def append(record: dict, ledger: Path) -> dict:
    if record.get("schema") != "decision/v2":
        raise SystemExit(f"REFUSED: schema {record.get('schema')!r} is not decision/v2")
    report = Path(record.get("report_path", ""))
    if not report.is_file():
        raise SystemExit(f"REFUSED: report file missing: {report}")
    sha = hashlib.sha256(report.read_bytes()).hexdigest()
    if sha != record.get("report_sha256"):
        raise SystemExit("REFUSED: report sha256 does not match the record (report changed after saving)")
    ledger.parent.mkdir(parents=True, exist_ok=True)
    row = dict(record, kind="decision", recorded_at=datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"))
    line = (json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(ledger, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        with open(fd, "rb", closefd=False) as reader:
            existing = reader.read().decode("utf-8").splitlines()
        if any(x.strip() and json.loads(x).get("decision_id") == record["decision_id"] for x in existing):
            raise SystemExit(f"REFUSED: decision_id {record['decision_id']} already in {ledger}")
        os.write(fd, line)
    finally:
        os.close(fd)  # also releases the lock
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("decision_id")
    parser.add_argument("--data-dir")
    parser.add_argument("--ledger", type=Path, default=LEDGER)
    args = parser.parse_args()
    row = append(find_record(data_dir(args.data_dir), args.decision_id), args.ledger)
    print(f"recorded {row['decision_id']} {row['ticker']} {row['group']} {row['action']} -> {args.ledger}")


if __name__ == "__main__":
    sys.exit(main())
