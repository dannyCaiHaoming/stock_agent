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
REQUIRED_SECTIONS = ("结论", "选用方法与证据", "正向论点", "反向论点与前提检验", "估值与情景", "行情与技术",
                     "消息面与持仓变动", "宏观与市场背景", "CIO 权衡", "改判条件", "第三方观点", "数据缺口与限制", "来源")
CONFIDENCE = ("low", "medium", "high")


class DecisionLogError(ValueError):
    pass


def _text_list(name: str, value: Any, *, required: bool = True) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(v, str) or not v.strip() for v in value):
        raise DecisionLogError(f"{name.upper()}_MUST_BE_LIST_OF_TEXT")
    if required and not value:
        raise DecisionLogError(f"{name.upper()}_REQUIRED")
    return [v.strip() for v in value]


# Structured direction forecasts, scored later against SEC quarterly data and sector-relative returns.
# Q0 = the latest fiscal quarter reported by data_as_of; Q2 = the second fiscal quarter after Q0.
FORECAST_TARGETS = {
    "revenue_growth": ("accelerate", "decelerate", "flat"),     # YoY growth in Q2 minus YoY growth in Q0 (±1pp)
    "operating_margin": ("expand", "contract", "flat"),         # GAAP margin in Q2 vs the same quarter a year earlier (±0.5pp)
    "relative_return_126d": ("outperform", "underperform"),     # 126 sessions after data_as_of vs the sector ETF
}
OPTIONAL_TARGETS = {"guidance": ("raise", "cut", "maintain", "not_applicable")}  # next company guidance vs prior


def _forecasts(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise DecisionLogError("FORECASTS_REQUIRED: list of {target, direction, probability, basis}; targets: "
                               + ", ".join(FORECAST_TARGETS))
    out, seen = [], set()
    for item in value:
        if not isinstance(item, dict):
            raise DecisionLogError("FORECAST_INVALID: each item is an object {target, direction, probability, basis}")
        target, direction = str(item.get("target", "")).strip(), str(item.get("direction", "")).strip()
        allowed = FORECAST_TARGETS.get(target) or OPTIONAL_TARGETS.get(target)
        if allowed is None:
            raise DecisionLogError(f"FORECAST_TARGET_INVALID: {target!r}; one of {list(FORECAST_TARGETS) + list(OPTIONAL_TARGETS)}")
        if direction not in allowed:
            raise DecisionLogError(f"FORECAST_DIRECTION_INVALID: {target} direction one of {allowed}")
        try:
            probability = Decimal(str(item.get("probability")).strip())
        except InvalidOperation:
            raise DecisionLogError("FORECAST_PROBABILITY_INVALID: number between 0 and 1, e.g. '0.6'") from None
        if probability > 1:
            probability = probability / 100
        if not probability.is_finite() or not 0 <= probability <= 1:
            raise DecisionLogError("FORECAST_PROBABILITY_INVALID: number between 0 and 1")
        basis = str(item.get("basis", "")).strip()
        if not basis:
            raise DecisionLogError(f"FORECAST_BASIS_REQUIRED: one sentence of evidence for {target}")
        if target in seen:
            raise DecisionLogError(f"FORECAST_DUPLICATE: {target}")
        seen.add(target)
        out.append({"target": target, "direction": direction, "probability": format(probability, "f"), "basis": basis})
    missing = [t for t in FORECAST_TARGETS if t not in seen]
    if missing:
        raise DecisionLogError("FORECASTS_MISSING: " + ", ".join(missing) + " (give a direction even for NO_TRADE)")
    return out


def save_decision(ticker: str, action: str, confidence: str, horizon: str, thesis: str,
                  key_evidence: list[str], risks: list[str], invalidation: list[str],
                  data_as_of: str, report_markdown: str, price_at_decision: str | None = None,
                  no_trade_reason: str | None = None, host: str | None = None,
                  model: str | None = None, forecasts: list[dict[str, Any]] | None = None,
                  expected_return_pct: str | None = None, variant: str | None = None,
                  methods: list[str] | None = None) -> dict[str, Any]:
    ticker = str(ticker).strip().upper()
    if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,9}", ticker):
        raise DecisionLogError("TICKER_INVALID")
    if action not in ACTIONS:
        raise DecisionLogError(f"ACTION_INVALID: one of {ACTIONS}")
    if confidence not in CONFIDENCE:
        raise DecisionLogError(f"CONFIDENCE_INVALID: one of {CONFIDENCE}")
    if price_at_decision is not None and not str(price_at_decision).strip():
        price_at_decision = None  # NO_TRADE may leave the price empty
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
    forecasts = _forecasts(forecasts)
    if expected_return_pct is not None and str(expected_return_pct).strip():
        try:
            expected_return_pct = format(Decimal(str(expected_return_pct).strip().rstrip("%")), "f")
        except InvalidOperation:
            raise DecisionLogError("EXPECTED_RETURN_PCT_INVALID: plain number, e.g. '12.5'") from None
    else:
        expected_return_pct = None
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
        "forecasts": forecasts, "expected_return_pct": expected_return_pct, "variant": variant,
        "methods": [str(m).strip() for m in (methods or []) if str(m).strip()],
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
