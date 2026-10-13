"""Append-only decision log: the basis for later forward-return evaluation.

Records go to <STOCK_AGENT_DATA_DIR>/decisions.jsonl (default <repo>/.local/data) and the full report to
<STOCK_AGENT_DATA_DIR>/reports/<YYYY-MM-DD>/<TICKER>-<decision_id>.md.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
import re
from typing import Any

from product.mcp import settings
from product.mcp.provenance import iso_utc

ACTIONS = ("BUY", "ADD", "HOLD", "REDUCE", "EXIT", "NO_TRADE")
# Report sections required by the investment-decision template (heading prefixes, "## " level).
REQUIRED_SECTIONS = ("结论", "核心问题与判断", "估值", "同业比较", "宏观与市场背景", "技术面", "反方论点与处置",
                     "第三方观点", "数据缺口与限制", "来源")
CONFIDENCE = ("low", "medium", "high")


class DecisionLogError(ValueError):
    pass


def _text_list(name: str, value: Any, *, required: bool = True) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise DecisionLogError(f"{name.upper()}_MUST_BE_LIST_OF_TEXT")
    if required and not value:
        raise DecisionLogError(f"{name.upper()}_REQUIRED")
    return [v.strip() for v in value]


def save_decision(ticker: str, action: str, confidence: str, horizon: str, thesis: str,
                  key_evidence: list[str], risks: list[str], invalidation: list[str],
                  data_as_of: str, report_markdown: str, price_at_decision: str | None = None,
                  no_trade_reason: str | None = None, host: str | None = None,
                  model: str | None = None) -> dict[str, Any]:
    ticker = str(ticker).strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", ticker):
        raise DecisionLogError("TICKER_INVALID")
    if action not in ACTIONS:
        raise DecisionLogError(f"ACTION_INVALID: one of {ACTIONS}")
    if confidence not in CONFIDENCE:
        raise DecisionLogError(f"CONFIDENCE_INVALID: one of {CONFIDENCE}")
    if action == "NO_TRADE" and not (no_trade_reason or "").strip():
        raise DecisionLogError("NO_TRADE_REASON_REQUIRED")
    if action != "NO_TRADE" and price_at_decision is None:
        raise DecisionLogError("PRICE_AT_DECISION_REQUIRED")
    if not isinstance(data_as_of, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data_as_of.strip()[:10]) \
            or len(data_as_of.strip()) not in (10, 20, 25):
        raise DecisionLogError("DATA_AS_OF_INVALID: use the data cutoff date as YYYY-MM-DD, e.g. '2026-10-12'")
    data_as_of = data_as_of.strip()
    date.fromisoformat(data_as_of[:10])
    if price_at_decision is not None:
        try:
            price = Decimal(str(price_at_decision).strip())
        except InvalidOperation:
            raise DecisionLogError("PRICE_AT_DECISION_INVALID: plain number only, e.g. '541.15'") from None
        if not price.is_finite() or price <= 0:
            raise DecisionLogError("PRICE_AT_DECISION_INVALID: must be a positive number")
        price_at_decision = format(price, "f")
    for name, value in (("horizon", horizon), ("thesis", thesis), ("report_markdown", report_markdown)):
        if not isinstance(value, str) or not value.strip():
            raise DecisionLogError(f"{name.upper()}_REQUIRED")
    headings = [line[3:].strip() for line in report_markdown.splitlines() if line.startswith("## ")]
    missing = [name for name in REQUIRED_SECTIONS if not any(h.startswith(name) for h in headings)]
    if missing:
        raise DecisionLogError("REPORT_SECTIONS_MISSING: rewrite the report with the investment-decision template "
                               "headings (\"## <name>\"), then save again. Missing: " + ", ".join(missing))
    decided_at = iso_utc(datetime.now(UTC))
    record = {
        "schema": "decision-record/1",
        "ticker": ticker, "decided_at": decided_at, "data_as_of": data_as_of[:10],
        "action": action, "confidence": confidence, "horizon": horizon.strip(),
        "price_at_decision": price_at_decision, "thesis": thesis.strip(),
        "key_evidence": _text_list("key_evidence", key_evidence),
        "risks": _text_list("risks", risks),
        "invalidation": _text_list("invalidation", invalidation),
        "no_trade_reason": (no_trade_reason or "").strip() or None,
        "host": host, "model": model,
    }
    record["decision_id"] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:12]
    root = settings.data_dir()
    report_dir = root / "reports" / decided_at[:10]
    report_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    report_path = report_dir / f"{ticker}-{record['decision_id']}.md"
    with report_path.open("x", encoding="utf-8") as handle:
        handle.write(report_markdown.rstrip() + "\n")
    record["report_path"] = str(report_path)
    line = json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
    fd = os.open(root / "decisions.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, line.encode("utf-8"))
    finally:
        os.close(fd)
    return {"saved": True, "decision_id": record["decision_id"], "report_path": str(report_path),
            "decision_log": str(root / "decisions.jsonl")}
