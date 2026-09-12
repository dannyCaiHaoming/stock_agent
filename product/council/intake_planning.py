"""Deterministic planning seam between neutral Intake state and Portfolio Council.

This module belongs to Council because capability availability is a runtime
planning concern, not an account-intake fact.  It never loads Evidence or calls
an Agent/LLM.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

from product.intake.v3 import HANDOFF_SCHEMA_VERSION, IntakeV3ValidationError, validate_handoff
from product.runtime.hashing import canonical_hash
from product.runtime.schema_validation import SchemaValidationError, validate_schema_instance


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = REPO_ROOT / "product" / "schemas" / "intake"
REQUEST_SCHEMA_VERSION = "council-request/1.0.0"
PLAN_SCHEMA_VERSION = "council-research-plan/1.0.0"
RESEARCH_SCOPE = "ALL_INPUT_POSITIONS"
CAPABILITY_BY_ASSET = {
    "COMMON_STOCK": "company-research",
    "ETF": "etf-research",
    "OPTION": "options-research",
}
DEFAULT_AVAILABLE_CAPABILITIES = frozenset({"company-research"})


class CouncilPlanningError(ValueError):
    """Fail-closed CouncilRequest or planning contract violation."""


def _schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))


def _without_hash(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result.pop(key, None)
    return result


def build_council_request(
    handoff: Mapping[str, Any], *, request_id: str, research_question: str,
    holding_horizon: str, benchmark_id: str, mandate_artifact_id: str,
    constraints: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Bind one research intent to an immutable confirmed Handoff."""

    validate_handoff(handoff)
    for field, value in (
        ("request_id", request_id), ("research_question", research_question),
        ("holding_horizon", holding_horizon), ("benchmark_id", benchmark_id),
        ("mandate_artifact_id", mandate_artifact_id),
    ):
        if not isinstance(value, str) or not value.strip():
            raise CouncilPlanningError(f"COUNCIL_REQUEST_TEXT_REQUIRED:{field}")
    request: dict[str, Any] = {
        "schema_version": REQUEST_SCHEMA_VERSION,
        "request_id": request_id.strip(),
        "handoff_id": handoff["handoff_id"],
        "handoff_hash": handoff["handoff_hash"],
        "portfolio_hash": handoff["portfolio_hash"],
        "research_question": research_question.strip(),
        "holding_horizon": holding_horizon.strip(),
        "research_scope": RESEARCH_SCOPE,
        "research_security_ids": sorted(
            position["security_id"] for position in handoff["portfolio"]["positions"]
        ),
        "benchmark_id": benchmark_id.strip(),
        "mandate_artifact_id": mandate_artifact_id.strip(),
        "constraints": copy.deepcopy(dict(constraints or {})),
    }
    request["request_hash"] = canonical_hash(_without_hash(request, "request_hash"))
    validate_council_request(request, handoff=handoff)
    return request


def validate_council_request(
    request: Mapping[str, Any], *, handoff: Mapping[str, Any] | None = None
) -> None:
    try:
        validate_schema_instance(request, _schema("council-request.schema.json"))
    except SchemaValidationError as exc:
        raise CouncilPlanningError(f"COUNCIL_REQUEST_SCHEMA_INVALID:{exc}") from exc
    if request.get("request_hash") != canonical_hash(_without_hash(request, "request_hash")):
        raise CouncilPlanningError("COUNCIL_REQUEST_HASH_MISMATCH")
    if handoff is not None:
        validate_handoff(handoff)
        if handoff.get("schema_version") != HANDOFF_SCHEMA_VERSION:
            raise CouncilPlanningError("COUNCIL_REQUEST_HANDOFF_VERSION_INVALID")
        bindings = (
            ("handoff_id", handoff["handoff_id"]),
            ("handoff_hash", handoff["handoff_hash"]),
            ("portfolio_hash", handoff["portfolio_hash"]),
        )
        for field, expected in bindings:
            if request.get(field) != expected:
                raise CouncilPlanningError(f"COUNCIL_REQUEST_BINDING_INVALID:{field}")
        expected_ids = sorted(
            position["security_id"] for position in handoff["portfolio"]["positions"]
        )
        if sorted(request["research_security_ids"]) != expected_ids:
            raise CouncilPlanningError("COUNCIL_REQUEST_COVERAGE_INVALID")


def build_research_plan(
    handoff: Mapping[str, Any], request: Mapping[str, Any], *,
    available_capabilities: set[str] | frozenset[str] = DEFAULT_AVAILABLE_CAPABILITIES,
    batch_size: int = 5,
) -> dict[str, Any]:
    """Create a full-portfolio, planning-only capability map."""

    validate_handoff(handoff)
    validate_council_request(request, handoff=handoff)
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise CouncilPlanningError("COUNCIL_PLAN_BATCH_SIZE_INVALID")
    known = set(CAPABILITY_BY_ASSET.values())
    available = set(available_capabilities)
    if not available <= known:
        raise CouncilPlanningError("COUNCIL_PLAN_CAPABILITY_UNKNOWN")
    positions = sorted(handoff["portfolio"]["positions"], key=lambda item: item["security_id"])
    items: list[dict[str, Any]] = []
    for index, position in enumerate(positions):
        capability = CAPABILITY_BY_ASSET[position["asset_type"]]
        items.append({
            "security_id": position["security_id"], "asset_type": position["asset_type"],
            "required_capability": capability,
            "capability_status": "AVAILABLE" if capability in available else "MISSING",
            "batch_index": index // batch_size + 1,
        })
    gaps = sorted({item["required_capability"] for item in items if item["capability_status"] == "MISSING"})
    plan: dict[str, Any] = {
        "schema_version": PLAN_SCHEMA_VERSION, "planning_only": True,
        "handoff_id": handoff["handoff_id"], "handoff_hash": handoff["handoff_hash"],
        "portfolio_hash": handoff["portfolio_hash"], "request_id": request["request_id"],
        "request_hash": request["request_hash"], "total": len(items), "pending": len(items),
        "batch_size": batch_size, "coverage_status": RESEARCH_SCOPE,
        "capability_status": "CAPABILITY_GAP" if gaps else "READY",
        "capability_gaps": gaps, "items": items, "agent_invocations": 0, "llm_invocations": 0,
    }
    plan["plan_hash"] = canonical_hash(_without_hash(plan, "plan_hash"))
    validate_research_plan(plan, handoff=handoff, request=request)
    return plan


def validate_research_plan(
    plan: Mapping[str, Any], *, handoff: Mapping[str, Any], request: Mapping[str, Any]
) -> None:
    try:
        validate_schema_instance(plan, _schema("council-research-plan.schema.json"))
    except SchemaValidationError as exc:
        raise CouncilPlanningError(f"COUNCIL_PLAN_SCHEMA_INVALID:{exc}") from exc
    if plan.get("plan_hash") != canonical_hash(_without_hash(plan, "plan_hash")):
        raise CouncilPlanningError("COUNCIL_PLAN_HASH_MISMATCH")
    validate_council_request(request, handoff=handoff)
    if any(
        plan[field] != expected
        for field, expected in (
            ("handoff_id", handoff["handoff_id"]), ("handoff_hash", handoff["handoff_hash"]),
            ("portfolio_hash", handoff["portfolio_hash"]), ("request_id", request["request_id"]),
            ("request_hash", request["request_hash"]),
        )
    ):
        raise CouncilPlanningError("COUNCIL_PLAN_BINDING_INVALID")
    expected_ids = sorted(position["security_id"] for position in handoff["portfolio"]["positions"])
    plan_ids = sorted(item["security_id"] for item in plan["items"])
    if plan_ids != expected_ids or plan["total"] != len(expected_ids) or plan["pending"] != len(expected_ids):
        raise CouncilPlanningError("COUNCIL_PLAN_COVERAGE_INVALID")
    if plan["agent_invocations"] != 0 or plan["llm_invocations"] != 0:
        raise CouncilPlanningError("COUNCIL_PLAN_EXECUTION_FORBIDDEN")


def build_council_portfolio_input(
    handoff: Mapping[str, Any], request: Mapping[str, Any], *,
    available_capabilities: set[str] | frozenset[str] = DEFAULT_AVAILABLE_CAPABILITIES,
    batch_size: int = 5,
) -> dict[str, Any]:
    """Compatibility-named entry that returns only the planning seam output."""

    return build_research_plan(
        handoff, request, available_capabilities=available_capabilities, batch_size=batch_size
    )


def translate_error(exc: Exception) -> CouncilPlanningError:
    """Normalize Intake validation failures at the Council boundary."""

    if isinstance(exc, CouncilPlanningError):
        return exc
    if isinstance(exc, IntakeV3ValidationError):
        return CouncilPlanningError(f"COUNCIL_HANDOFF_INVALID:{exc}")
    return CouncilPlanningError(str(exc))
