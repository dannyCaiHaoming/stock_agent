"""Validation and safe finalization for advisory-only council output."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


ACTIONS = frozenset({"BUY", "ADD", "HOLD", "TRIM", "EXIT", "NO_TRADE"})
NO_TRADE_REASONS = frozenset(
    {
        "INSUFFICIENT_EVIDENCE",
        "STALE_DATA",
        "MATERIAL_SOURCE_CONFLICT",
        "UNRESOLVED_THESIS_CONFLICT",
        "LOW_CONVICTION",
        "INPUT_INVALID",
        "MANDATE_VIOLATION",
        "LIQUIDITY_LIMIT",
        "RISK_VETO",
    }
)
FORBIDDEN_EXECUTION_KEYS = frozenset(
    {
        "account_id",
        "account_credentials",
        "broker",
        "broker_token",
        "order_id",
        "order_status",
        "sent_at",
        "execution_authorization",
    }
)


class FinalPlanError(ValueError):
    """Raised when a plan is unsafe or fails its public contract."""


def _walk_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            keys.add(str(key))
            keys.update(_walk_keys(child))
    elif isinstance(value, list):
        for child in value:
            keys.update(_walk_keys(child))
    return keys


def validate_final_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Return a defensive copy after enforcing the advisory output contract."""

    candidate = deepcopy(dict(plan))
    if candidate.get("advisory_only") is not True:
        raise FinalPlanError("final plan must set advisory_only to true")
    if not isinstance(candidate.get("risk_report"), Mapping):
        raise FinalPlanError("final plan requires a risk_report")
    decisions = candidate.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        raise FinalPlanError("final plan requires at least one decision")
    forbidden = _walk_keys(candidate) & FORBIDDEN_EXECUTION_KEYS
    if forbidden:
        raise FinalPlanError(f"executable order fields are forbidden: {sorted(forbidden)}")

    for decision in decisions:
        if not isinstance(decision, Mapping):
            raise FinalPlanError("each decision must be an object")
        action = decision.get("action")
        if action not in ACTIONS:
            raise FinalPlanError(f"unsupported action: {action!r}")
        if action == "NO_TRADE":
            if decision.get("no_trade_reason") not in NO_TRADE_REASONS:
                raise FinalPlanError("NO_TRADE requires a standard reason code")
            if not decision.get("reevaluation_conditions"):
                raise FinalPlanError("NO_TRADE requires reevaluation conditions")
            continue
        target = decision.get("target_weight_range")
        if not (
            isinstance(target, list)
            and len(target) == 2
            and all(isinstance(item, (int, float)) for item in target)
            and 0 <= target[0] <= target[1] <= 1
        ):
            raise FinalPlanError("trade intent requires a valid target_weight_range")
        for field in ("thesis", "counter_thesis", "evidence_refs", "invalidation_conditions"):
            if not decision.get(field):
                raise FinalPlanError(f"trade intent requires {field}")
    return candidate


def force_no_trade(
    draft: Mapping[str, Any], risk_report: Mapping[str, Any], reason: str = "RISK_VETO"
) -> dict[str, Any]:
    """Replace rejected intents without altering the recorded CIO draft."""

    if reason not in NO_TRADE_REASONS:
        raise FinalPlanError(f"unknown NO_TRADE reason: {reason}")
    securities = [item.get("security_id", "PORTFOLIO") for item in draft.get("decisions", [])]
    if not securities:
        securities = ["PORTFOLIO"]
    return {
        "schema_version": "1.0.0",
        "advisory_only": True,
        "risk_report": deepcopy(dict(risk_report)),
        "decisions": [
            {
                "security_id": security,
                "action": "NO_TRADE",
                "no_trade_reason": reason,
                "reevaluation_conditions": ["Resolve the recorded risk violations and rerun the council."],
            }
            for security in securities
        ],
        "rejected_draft": deepcopy(dict(draft)),
    }
