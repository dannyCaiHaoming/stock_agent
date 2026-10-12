"""Translate validated fixture portfolio data into the deterministic Risk Engine."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import timedelta
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from product.deterministic.policy import RiskPolicy
from product.deterministic.portfolio import NormalizedPosition, PortfolioSnapshot
from product.deterministic.risk import RiskEngine, TargetWeightRange

from .hashing import canonical_hash
from product.tools.fixture_risk import _primitive, build_risk_snapshot, build_risk_policy, check_cio_draft


RISK_RESULT_VERSION = "native-risk-result/2.0.0"
REFERENCE_RISK_POLICY_VERSION = "risk/reference/1.0.0"










def check_live_cio_draft(portfolio: dict, evidence_snapshot: dict, gate: dict,
                         draft: dict, *, run_id: str, calendar, focus_security_id: str | None = None) -> dict:
    """从重验过的 live Gate 估值构造现有 Risk Engine 输入，不接受手填 price。"""
    from dataclasses import replace
    from product.runtime.live_input import value_portfolio
    from product.runtime.decision_contract import load_decision_contract, validate_decision_action
    from product.runtime.validation import validate_evidence_closure

    validate_decision_action(draft, load_decision_contract(Path(__file__).resolve().parents[1]))
    if draft["action"] not in ("HOLD", "TRIM", "EXIT", "NO_TRADE"):
        raise ValueError("LIVE_ACTION_NOT_AUTHORIZED")
    focus = focus_security_id if focus_security_id is not None else portfolio["focus_security_id"]
    if focus not in {p["security_id"] for p in portfolio["positions"]}:
        raise ValueError("LIVE_RISK_FOCUS_UNKNOWN")
    legal_unscoped_no_trade = draft["action"] == "NO_TRADE" and draft["security_id"] is None
    if (not legal_unscoped_no_trade and draft["security_id"] != focus) or gate["run_id"] != run_id:
        raise ValueError("LIVE_RISK_FOCUS_OR_RUN_MISMATCH")
    validate_evidence_closure(draft, allowed_evidence_ids=gate["allowed_evidence_ids"])
    snapshot, valuation = build_live_risk_snapshot(portfolio, evidence_snapshot, gate, run_id=run_id, calendar=calendar)
    policy = replace(build_risk_policy({"portfolio": portfolio}), mandate_version=portfolio["mandate"]["version"])
    targets = () if draft["action"] == "NO_TRADE" else (TargetWeightRange(
        security_id=draft["security_id"], minimum=Decimal(str(draft["target_weight_range"][0])),
        maximum=Decimal(str(draft["target_weight_range"][1]))),)
    report = _primitive(RiskEngine(policy).final_check(snapshot, targets))
    result = {"schema_version": "live-risk-result/1.0.0", "source_mode": "live", "run_id": run_id,
              "producer": "deterministic_risk_engine", "policy_version": policy.version,
              "draft_hash": canonical_hash(draft), "original_action": draft["action"], "modifications": [],
              "check": report, "final_action": "NO_TRADE" if report["status"] == "REJECTED" else draft["action"],
              "veto_reason": "RISK_VETO" if report["status"] == "REJECTED" else None,
              "valuation_hash": valuation["valuation_hash"], "gate_hash": gate["bundle_hash"],
              "data_gaps": ["SECTOR_CLASSIFICATION_UNAVAILABLE", "LIQUIDITY_DATA_UNAVAILABLE"]}
    result["result_hash"] = canonical_hash(result)
    return result


def build_live_risk_snapshot(portfolio: dict, evidence_snapshot: dict, gate: dict, *, run_id: str, calendar):
    from product.runtime.live_input import value_portfolio
    if gate["run_id"] != run_id:
        raise ValueError("LIVE_RISK_RUN_MISMATCH")
    valuation = value_portfolio(portfolio, evidence_snapshot, gate, calendar=calendar)
    by_id = {f["evidence_id"]: f for f in gate["allowed_evidence"]}
    positions = tuple(NormalizedPosition(
        security_id=row["security_id"], quantity=Decimal(str(row["quantity"])), price=Decimal(row["price"]),
        price_as_of=by_id[row["price_evidence_id"]]["as_of"], price_source_id=by_id[row["price_evidence_id"]]["source_id"],
        market_value=Decimal(row["market_value"]), weight=Decimal(row["weight"]), industry="Unclassified",
        average_daily_value=None,
    ) for row in valuation["positions"])
    snapshot = PortfolioSnapshot(snapshot_id=f"snapshot-{run_id}", as_of=evidence_snapshot["decision_cutoff"],
        base_currency="USD", benchmark=None, mandate_version=portfolio["mandate"]["version"],
        cash=Decimal(str(portfolio["cash"])), total_value=Decimal(valuation["total_value"]), positions=positions)
    return snapshot, valuation
