"""Deterministic contracts for the common-stock research stage.

This module binds confirmed holdings, gated Evidence and structured research
artifacts.  It does not perform investment reasoning or call a model.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.intake.v3 import validate_handoff
from product.mcp.provenance import parse_timestamp
from product.runtime.hashing import canonical_hash
from product.runtime.schema_validation import SchemaValidationError, validate_schema_instance
from product.runtime.validation import ArtifactValidationError, validate_evidence_closure

from .intake_planning import (
    CAPABILITY_BY_ASSET,
    COMMON_STOCK_RESEARCH_STAGE,
    RESEARCH_REQUEST_SCHEMA_VERSION,
    build_research_plan,
    validate_council_request,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = REPO_ROOT / "product" / "schemas" / "runtime"
HOLDING_REQUEST_VERSION = "holding-research-request/1.0.0"
EQUITY_REPORT_VERSION = "equity-research-report/1.0.0"
COVERAGE_VERSION = "research-coverage/1.0.0"
REQUIRED_SKILLS = (
    "evidence-grounding",
    "company-research",
    "valuation",
    "catalyst-analysis",
)
SECTION_NAMES = (
    "company_and_core_questions",
    "business_competition_financials",
    "thesis_and_valuation",
    "catalysts_and_counterevidence",
    "invalidation_and_monitoring",
    "gaps_and_confidence",
)
FORBIDDEN_RESEARCH_KEYS = {
    "action",
    "trade_action",
    "target_weight",
    "target_weight_range",
    "maximum_notional",
    "order",
    "order_id",
    "order_quantity",
    "recommended_quantity",
}
CANONICAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


class CommonStockResearchError(ValueError):
    """Fail-closed research-stage contract error."""


def _schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))


def _without_hash(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result.pop(key, None)
    return result


def _exact_keys(value: Mapping[str, Any], expected: set[str], code: str) -> None:
    missing = sorted(expected - value.keys())
    extra = sorted(value.keys() - expected)
    if missing or extra:
        raise CommonStockResearchError(f"{code}:missing={missing}:extra={extra}")


def _canonical_ids(values: Any, field: str, *, unique: bool = True) -> list[str]:
    if not isinstance(values, list):
        raise CommonStockResearchError(f"RESEARCH_ID_ARRAY_INVALID:{field}")
    if any(not isinstance(item, str) or not CANONICAL_ID.fullmatch(item) for item in values):
        raise CommonStockResearchError(f"RESEARCH_CANONICAL_ID_INVALID:{field}")
    if unique and len(values) != len(set(values)):
        raise CommonStockResearchError(f"RESEARCH_ID_DUPLICATE:{field}")
    return values


def _skill_names(items: Any, *, key: str) -> list[str]:
    if not isinstance(items, list) or len(items) != len(REQUIRED_SKILLS):
        raise CommonStockResearchError("RESEARCH_SKILL_BINDING_COUNT_INVALID")
    names: list[str] = []
    for index, item in enumerate(items):
        if not isinstance(item, Mapping):
            raise CommonStockResearchError(f"RESEARCH_SKILL_BINDING_INVALID:{index}")
        name = item.get(key)
        version = item.get("version")
        digest_key = "content_hash" if key == "name" else "invocation_hash"
        digest = item.get(digest_key)
        if (
            not isinstance(name, str)
            or not isinstance(version, str)
            or not version
            or not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
        ):
            raise CommonStockResearchError(f"RESEARCH_SKILL_BINDING_INVALID:{index}")
        names.append(name)
    if set(names) != set(REQUIRED_SKILLS) or len(names) != len(set(names)):
        raise CommonStockResearchError("RESEARCH_SKILL_BINDINGS_INVALID")
    return names


def _scoped_evidence_ids(gate: Mapping[str, Any], security_id: str) -> list[str]:
    allowed = gate.get("allowed_evidence_ids")
    facts = gate.get("allowed_evidence")
    _canonical_ids(allowed, "gate.allowed_evidence_ids")
    if not isinstance(facts, list):
        raise CommonStockResearchError("RESEARCH_GATE_FACTS_INVALID")
    allowed_set = set(allowed)
    if gate.get("bundle_hash") != canonical_hash(_without_hash(gate, "bundle_hash")):
        raise CommonStockResearchError("RESEARCH_GATE_HASH_MISMATCH")
    fact_ids = [fact.get("evidence_id") for fact in facts if isinstance(fact, Mapping)]
    if len(fact_ids) != len(facts) or set(fact_ids) != allowed_set or len(fact_ids) != len(set(fact_ids)):
        raise CommonStockResearchError("RESEARCH_GATE_EVIDENCE_SET_INVALID")
    cutoff = parse_timestamp(str(gate.get("decision_cutoff")))
    for fact in facts:
        try:
            if parse_timestamp(str(fact["as_of"])) > cutoff or parse_timestamp(str(fact["retrieved_at"])) > cutoff:
                raise CommonStockResearchError(
                    f"RESEARCH_GATE_PIT_LEAKAGE:{fact['evidence_id']}"
                )
        except KeyError as exc:
            raise CommonStockResearchError("RESEARCH_GATE_PROVENANCE_INVALID") from exc
    excluded_ids = _canonical_ids(
        gate.get("excluded_evidence_ids", []), "gate.excluded_evidence_ids"
    )
    excluded = gate.get("excluded", [])
    if not isinstance(excluded, list) or [item.get("evidence_id") for item in excluded] != excluded_ids:
        raise CommonStockResearchError("RESEARCH_GATE_EXCLUDED_SET_INVALID")
    input_ids = _canonical_ids(gate.get("input_evidence_ids", allowed + excluded_ids), "gate.input_evidence_ids")
    if set(input_ids) != allowed_set | set(excluded_ids) or allowed_set & set(excluded_ids):
        raise CommonStockResearchError("RESEARCH_GATE_INPUT_SET_INVALID")
    scoped = sorted(
        str(fact["evidence_id"])
        for fact in facts
        if isinstance(fact, Mapping)
        and fact.get("evidence_id") in allowed_set
        and fact.get("security_id") in {security_id, "MARKET", "US:MARKET"}
    )
    return scoped


def build_holding_research_requests(
    handoff: Mapping[str, Any],
    council_request: Mapping[str, Any],
    gate: Mapping[str, Any],
    *,
    run_id: str,
    agent_binding: Mapping[str, Any],
    skill_bindings: Sequence[Mapping[str, Any]],
    user_theses: Mapping[str, str] | None = None,
    user_questions: Mapping[str, Sequence[str]] | None = None,
) -> list[dict[str, Any]]:
    """Derive one minimal request for every researchable common stock."""

    validate_handoff(handoff)
    validate_council_request(council_request, handoff=handoff)
    if (
        council_request.get("schema_version") != RESEARCH_REQUEST_SCHEMA_VERSION
        or council_request.get("stage") != COMMON_STOCK_RESEARCH_STAGE
    ):
        raise CommonStockResearchError("COMMON_STOCK_RESEARCH_STAGE_REQUIRED")
    if not isinstance(run_id, str) or not run_id.strip():
        raise CommonStockResearchError("RESEARCH_RUN_ID_REQUIRED")
    if gate.get("run_id") != run_id:
        raise CommonStockResearchError("RESEARCH_GATE_RUN_MISMATCH")
    if not isinstance(agent_binding, Mapping) or agent_binding.get("name") != "runtime_company_analyst":
        raise CommonStockResearchError("RESEARCH_AGENT_BINDING_INVALID")
    _skill_names(list(skill_bindings), key="name")
    cutoff = gate.get("decision_cutoff")
    if not isinstance(cutoff, str):
        raise CommonStockResearchError("RESEARCH_GATE_CUTOFF_REQUIRED")
    parse_timestamp(cutoff)
    if not isinstance(gate.get("bundle_hash"), str) or not re.fullmatch(
        r"[0-9a-f]{64}", str(gate["bundle_hash"])
    ):
        raise CommonStockResearchError("RESEARCH_GATE_HASH_INVALID")

    requests: list[dict[str, Any]] = []
    for position in handoff["portfolio"]["positions"]:
        if position["asset_type"] != "COMMON_STOCK":
            continue
        security_id = position["security_id"]
        request_id = f"holding-research:{run_id}:{security_id}"
        invocation_id = f"{run_id}:runtime_company_analyst:{security_id}"
        thesis = (user_theses or {}).get(security_id)
        questions = list((user_questions or {}).get(security_id, ()))
        value: dict[str, Any] = {
            "schema_version": HOLDING_REQUEST_VERSION,
            "request_id": request_id,
            "run_id": run_id,
            "invocation_id": invocation_id,
            "handoff_id": handoff["handoff_id"],
            "handoff_hash": handoff["handoff_hash"],
            "portfolio_hash": handoff["portfolio_hash"],
            "council_request_id": council_request["request_id"],
            "council_request_hash": council_request["request_hash"],
            "security": {
                "security_id": security_id,
                "display_symbol": position["display_symbol"],
                "display_name": position["display_name"],
                "market": position["market"],
                "asset_type": position["asset_type"],
                "identity_status": position["identity_status"],
            },
            "research_question": council_request["research_question"],
            "holding_horizon": council_request["holding_horizon"],
            "decision_cutoff": cutoff,
            "allowed_evidence_ids": _scoped_evidence_ids(gate, security_id),
            "evidence_bundle_hash": gate["bundle_hash"],
            "data_gaps": [],
            "user_context": {
                "user_thesis": thesis.strip() if isinstance(thesis, str) and thesis.strip() else None,
                "user_questions": [str(item).strip() for item in questions if str(item).strip()],
            },
            "agent_binding": copy.deepcopy(dict(agent_binding)),
            "skill_bindings": copy.deepcopy(list(skill_bindings)),
        }
        if not value["allowed_evidence_ids"]:
            value["data_gaps"].append("当前冻结资料没有该证券可用 Evidence。")
        value["request_hash"] = canonical_hash(_without_hash(value, "request_hash"))
        validate_holding_research_request(
            value, handoff=handoff, council_request=council_request, gate=gate
        )
        requests.append(value)
    return requests


def validate_holding_research_request(
    value: Mapping[str, Any], *, handoff: Mapping[str, Any],
    council_request: Mapping[str, Any], gate: Mapping[str, Any]
) -> None:
    try:
        validate_schema_instance(value, _schema("holding-research-request.schema.json"))
    except SchemaValidationError as exc:
        raise CommonStockResearchError(f"HOLDING_RESEARCH_REQUEST_SCHEMA_INVALID:{exc}") from exc
    validate_handoff(handoff)
    validate_council_request(council_request, handoff=handoff)
    expected = {
        "handoff_id": handoff["handoff_id"],
        "handoff_hash": handoff["handoff_hash"],
        "portfolio_hash": handoff["portfolio_hash"],
        "council_request_id": council_request["request_id"],
        "council_request_hash": council_request["request_hash"],
        "decision_cutoff": gate["decision_cutoff"],
        "evidence_bundle_hash": gate["bundle_hash"],
    }
    if any(value.get(field) != expected_value for field, expected_value in expected.items()):
        raise CommonStockResearchError("HOLDING_RESEARCH_REQUEST_BINDING_INVALID")
    positions = {item["security_id"]: item for item in handoff["portfolio"]["positions"]}
    security = value["security"]
    if security.get("security_id") not in positions or positions[security["security_id"]]["asset_type"] != "COMMON_STOCK":
        raise CommonStockResearchError("HOLDING_RESEARCH_SECURITY_INVALID")
    if any(
        security.get(field) != positions[security["security_id"]].get(field)
        for field in ("display_symbol", "display_name", "market", "asset_type", "identity_status")
    ):
        raise CommonStockResearchError("HOLDING_RESEARCH_SECURITY_BINDING_INVALID")
    scoped = _scoped_evidence_ids(gate, security["security_id"])
    if value["allowed_evidence_ids"] != scoped:
        raise CommonStockResearchError("HOLDING_RESEARCH_EVIDENCE_SCOPE_INVALID")
    _skill_names(value["skill_bindings"], key="name")
    if value.get("request_hash") != canonical_hash(_without_hash(value, "request_hash")):
        raise CommonStockResearchError("HOLDING_RESEARCH_REQUEST_HASH_MISMATCH")


def _find_forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key in FORBIDDEN_RESEARCH_KEYS:
                found.add(str(key))
            found.update(_find_forbidden_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_find_forbidden_keys(child))
    return found


def validate_equity_research_report(
    value: Mapping[str, Any], *, request: Mapping[str, Any],
    calculation_artifact_ids: Sequence[str] = ()
) -> set[str]:
    """Validate report bindings, internal references and Evidence Closure."""

    try:
        validate_schema_instance(value, _schema("equity-research-report.schema.json"))
    except SchemaValidationError as exc:
        raise CommonStockResearchError(f"EQUITY_RESEARCH_SCHEMA_INVALID:{exc}") from exc
    forbidden = _find_forbidden_keys(value)
    if forbidden:
        raise CommonStockResearchError(f"EQUITY_RESEARCH_ACTION_FIELD_FORBIDDEN:{','.join(sorted(forbidden))}")
    if value.get("schema_version") != EQUITY_REPORT_VERSION:
        raise CommonStockResearchError("EQUITY_RESEARCH_VERSION_INVALID")
    if (
        value.get("run_id") != request.get("run_id")
        or value.get("invocation_id") != request.get("invocation_id")
        or value.get("agent") != "runtime_company_analyst"
        or value.get("research_scope") != "SINGLE_COMMON_STOCK_HOLDING"
    ):
        raise CommonStockResearchError("EQUITY_RESEARCH_INVOCATION_BINDING_INVALID")
    expected_bindings = {
        "handoff_id": request["handoff_id"],
        "handoff_hash": request["handoff_hash"],
        "portfolio_hash": request["portfolio_hash"],
        "council_request_id": request["council_request_id"],
        "council_request_hash": request["council_request_hash"],
        "holding_research_request_id": request["request_id"],
        "holding_research_request_hash": request["request_hash"],
        "decision_cutoff": request["decision_cutoff"],
    }
    if value.get("bindings") != expected_bindings or value.get("security") != {
        key: request["security"][key]
        for key in ("security_id", "display_symbol", "display_name", "market", "asset_type")
    }:
        raise CommonStockResearchError("EQUITY_RESEARCH_SOURCE_BINDING_INVALID")
    _skill_names(value.get("skill_execution"), key="skill_name")
    requested_skills = {(item["name"], item["version"]) for item in request["skill_bindings"]}
    executed_skills = {(item["skill_name"], item["version"]) for item in value["skill_execution"]}
    if requested_skills != executed_skills:
        raise CommonStockResearchError("EQUITY_RESEARCH_SKILL_BINDING_INVALID")

    claims = value.get("claims")
    assumptions = value.get("assumptions")
    conditions = value.get("invalidation_conditions")
    triggers = value.get("reevaluation_triggers")
    indicators = value.get("monitoring_indicators")
    gaps = value.get("data_gaps")
    if any(not isinstance(items, list) for items in (claims, assumptions, conditions, triggers, indicators, gaps)):
        raise CommonStockResearchError("EQUITY_RESEARCH_COLLECTION_INVALID")
    collections = (
        (claims, "claim_id", "claims"),
        (assumptions, "assumption_id", "assumptions"),
        (conditions, "condition_id", "invalidation_conditions"),
        (triggers, "trigger_id", "reevaluation_triggers"),
        (indicators, "indicator_id", "monitoring_indicators"),
        (gaps, "gap_id", "data_gaps"),
    )
    indexes: dict[str, set[str]] = {}
    for items, id_key, name in collections:
        if any(not isinstance(item, Mapping) for item in items):
            raise CommonStockResearchError(f"EQUITY_RESEARCH_ITEM_INVALID:{name}")
        ids = _canonical_ids([item.get(id_key) for item in items], name)
        indexes[name] = set(ids)
    claim_ids = indexes["claims"]
    assumption_ids = indexes["assumptions"]
    condition_ids = indexes["invalidation_conditions"]
    gap_ids = indexes["data_gaps"]
    known_calculations = set(calculation_artifact_ids)
    report_artifacts = set(value.get("artifact_refs", []))
    for claim in claims:
        evidence_refs = _canonical_ids(claim.get("evidence_refs"), "claim.evidence_refs")
        claim_assumptions = set(_canonical_ids(claim.get("assumption_ids"), "claim.assumption_ids"))
        calculations = set(_canonical_ids(claim.get("calculation_refs"), "claim.calculation_refs"))
        counter_claims = set(_canonical_ids(claim.get("counter_claim_refs"), "claim.counter_claim_refs"))
        invalidations = set(_canonical_ids(claim.get("invalidation_condition_ids"), "claim.invalidation_condition_ids"))
        if claim_assumptions - assumption_ids or counter_claims - claim_ids or invalidations - condition_ids:
            raise CommonStockResearchError("EQUITY_RESEARCH_INTERNAL_REFERENCE_DANGLING")
        if calculations - known_calculations or calculations - report_artifacts:
            raise CommonStockResearchError("EQUITY_RESEARCH_CALCULATION_REFERENCE_DANGLING")
        if not evidence_refs and not claim_assumptions and not calculations:
            raise CommonStockResearchError("EQUITY_RESEARCH_CLAIM_UNGROUNDED")
    summary = value.get("research_summary")
    sections = value.get("sections")
    if not isinstance(summary, Mapping) or not isinstance(sections, Mapping) or set(sections) != set(SECTION_NAMES):
        raise CommonStockResearchError("EQUITY_RESEARCH_SECTIONS_INVALID")
    if set(_canonical_ids(summary.get("claim_refs"), "summary.claim_refs")) - claim_ids:
        raise CommonStockResearchError("EQUITY_RESEARCH_SUMMARY_REFERENCE_DANGLING")
    if set(_canonical_ids(summary.get("primary_invalidation_condition_ids"), "summary.invalidation")) - condition_ids:
        raise CommonStockResearchError("EQUITY_RESEARCH_SUMMARY_REFERENCE_DANGLING")
    for name in SECTION_NAMES:
        section = sections[name]
        if not isinstance(section, Mapping):
            raise CommonStockResearchError(f"EQUITY_RESEARCH_SECTION_INVALID:{name}")
        if set(_canonical_ids(section.get("claim_refs"), f"sections.{name}.claim_refs")) - claim_ids:
            raise CommonStockResearchError("EQUITY_RESEARCH_SECTION_REFERENCE_DANGLING")
        if set(_canonical_ids(section.get("data_gap_ids"), f"sections.{name}.data_gap_ids")) - gap_ids:
            raise CommonStockResearchError("EQUITY_RESEARCH_SECTION_REFERENCE_DANGLING")
    for condition in conditions:
        if set(_canonical_ids(condition.get("claim_refs"), "condition.claim_refs")) - claim_ids:
            raise CommonStockResearchError("EQUITY_RESEARCH_CONDITION_REFERENCE_DANGLING")
    for trigger in triggers:
        if set(_canonical_ids(trigger.get("claim_refs"), "trigger.claim_refs")) - claim_ids:
            raise CommonStockResearchError("EQUITY_RESEARCH_TRIGGER_REFERENCE_DANGLING")
    for indicator in indicators:
        for field in ("baseline", "unit", "comparison_period", "reevaluation_rule"):
            if field in indicator and indicator[field] is not None and (
                not isinstance(indicator[field], str) or not indicator[field].strip()
            ):
                raise CommonStockResearchError(
                    f"EQUITY_RESEARCH_MONITORING_CONTEXT_INVALID:{field}"
                )
    allowed_gap_reasons = {
        "NOT_FETCHED", "NOT_YET_DISCLOSED", "SOURCE_UNSUPPORTED", "UNKNOWN"
    }
    for gap in gaps:
        if "reason_code" in gap and gap["reason_code"] not in allowed_gap_reasons:
            raise CommonStockResearchError("EQUITY_RESEARCH_GAP_REASON_INVALID")
    try:
        return validate_evidence_closure(value, allowed_evidence_ids=request["allowed_evidence_ids"])
    except ArtifactValidationError as exc:
        raise CommonStockResearchError(str(exc)) from exc


def build_initial_research_coverage(
    handoff: Mapping[str, Any], council_request: Mapping[str, Any], *, batch_id: str,
    target_concurrency: int = 3, effective_concurrency: int = 3,
    execution_mode_reason: str | None = None,
    per_item_timeout_seconds: int = 900, batch_budget_seconds: int = 1800,
) -> dict[str, Any]:
    """Build full-portfolio coverage without claiming any research completed."""

    validate_handoff(handoff)
    validate_council_request(council_request, handoff=handoff)
    if not isinstance(target_concurrency, int) or isinstance(target_concurrency, bool) or target_concurrency < 1:
        raise CommonStockResearchError("RESEARCH_TARGET_CONCURRENCY_INVALID")
    if not isinstance(effective_concurrency, int) or isinstance(effective_concurrency, bool) or effective_concurrency < 0:
        raise CommonStockResearchError("RESEARCH_EFFECTIVE_CONCURRENCY_INVALID")
    if any(
        not isinstance(item, int) or isinstance(item, bool) or item < 1
        for item in (per_item_timeout_seconds, batch_budget_seconds)
    ):
        raise CommonStockResearchError("RESEARCH_TIME_BUDGET_INVALID")
    effective_concurrency = min(target_concurrency, effective_concurrency)
    items = []
    for position in handoff["portfolio"]["positions"]:
        common = position["asset_type"] == "COMMON_STOCK"
        items.append({
            "security_id": position["security_id"],
            "asset_type": position["asset_type"],
            "required_capability": CAPABILITY_BY_ASSET[position["asset_type"]],
            "execution_status": "QUEUED" if common else "NOT_STARTED",
            "research_status": "NOT_RESEARCHED",
            "eval_status": "NOT_EVALUATED",
            "coverage_status": "NOT_RESEARCHED" if common else "CAPABILITY_GAP",
            "invocation_id": None,
            "report_ref": None,
            "report_hash": None,
            "eval_ref": None,
            "eval_result_hash": None,
            "evaluated_report_hash": None,
            "failure_code": None,
        })
    has_common = any(item["asset_type"] == "COMMON_STOCK" for item in items)
    has_gap = any(item["coverage_status"] == "CAPABILITY_GAP" for item in items)
    value: dict[str, Any] = {
        "schema_version": COVERAGE_VERSION,
        "batch_id": batch_id,
        "handoff_id": handoff["handoff_id"],
        "handoff_hash": handoff["handoff_hash"],
        "portfolio_hash": handoff["portfolio_hash"],
        "council_request_id": council_request["request_id"],
        "council_request_hash": council_request["request_hash"],
        "stage_status": "PARTIAL_RESEARCH" if has_common and has_gap else "NO_COMMON_STOCKS" if not has_common else "PARTIAL_RESEARCH",
        "execution_mode": "NOT_STARTED" if not has_common else "PARALLEL" if effective_concurrency > 1 else "SERIAL",
        "target_concurrency": target_concurrency,
        "effective_concurrency": effective_concurrency if has_common else 0,
        "execution_mode_reason": (
            execution_mode_reason
            if has_common and effective_concurrency <= 1
            else None
        ),
        "per_item_timeout_seconds": per_item_timeout_seconds,
        "batch_budget_seconds": batch_budget_seconds,
        "batch_started_at": None,
        "cancelled_at": None,
        "items": items,
    }
    value["coverage_hash"] = canonical_hash(_without_hash(value, "coverage_hash"))
    validate_research_coverage(value, handoff=handoff, council_request=council_request)
    return value


def prepare_common_stock_research_stage(
    handoff: Mapping[str, Any], council_request: Mapping[str, Any], gate: Mapping[str, Any],
    *, run_id: str, batch_id: str, agent_binding: Mapping[str, Any],
    skill_bindings: Sequence[Mapping[str, Any]], target_concurrency: int = 3,
    effective_concurrency: int = 3, execution_mode_reason: str | None = None,
    per_item_timeout_seconds: int = 900, batch_budget_seconds: int = 1800,
    data_preparation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare the explicit research-only stage after full-portfolio planning.

    This function deliberately never calls portfolio valuation, CIO, Skeptic or
    Risk.  Unsupported assets remain in the plan and coverage artifact.
    """

    plan = build_research_plan(
        handoff, council_request, available_capabilities={"company-research"},
        batch_size=max(1, target_concurrency),
    )
    all_requests = build_holding_research_requests(
        handoff, council_request, gate, run_id=run_id, agent_binding=agent_binding,
        skill_bindings=skill_bindings,
    )
    preparation_by_security: dict[str, Mapping[str, Any]] = {}
    if data_preparation is not None:
        if data_preparation.get("preparation_hash") != canonical_hash(
            _without_hash(data_preparation, "preparation_hash")
        ):
            raise CommonStockResearchError("RESEARCH_DATA_PREPARATION_HASH_MISMATCH")
        expected_common_ids = {
            item["security_id"] for item in handoff["portfolio"]["positions"]
            if item["asset_type"] == "COMMON_STOCK"
        }
        if (
            data_preparation.get("run_id") != run_id
            or data_preparation.get("handoff_id") != handoff["handoff_id"]
            or data_preparation.get("handoff_hash") != handoff["handoff_hash"]
            or data_preparation.get("portfolio_hash") != handoff["portfolio_hash"]
            or data_preparation.get("common_cutoff") != gate["decision_cutoff"]
        ):
            raise CommonStockResearchError("RESEARCH_DATA_PREPARATION_BINDING_INVALID")
        rows = data_preparation.get("items")
        if (
            not isinstance(rows, list)
            or len(rows) != len(expected_common_ids)
            or {item.get("security_id") for item in rows} != expected_common_ids
        ):
            raise CommonStockResearchError("RESEARCH_DATA_PREPARATION_COVERAGE_INVALID")
        preparation_by_security = {item["security_id"]: item for item in rows}
        for security_id, row in preparation_by_security.items():
            evidence_ids = _canonical_ids(
                row.get("evidence_ids", []), f"data_preparation.items.{security_id}.evidence_ids"
            )
            expected_ids = _scoped_evidence_ids(gate, security_id)
            if evidence_ids != expected_ids:
                raise CommonStockResearchError("RESEARCH_DATA_PREPARATION_EVIDENCE_MISMATCH")
            if row.get("status") == "READY" and not evidence_ids:
                raise CommonStockResearchError("RESEARCH_DATA_PREPARATION_STATUS_INVALID")
            if row.get("status") == "INSUFFICIENT_EVIDENCE" and evidence_ids:
                raise CommonStockResearchError("RESEARCH_DATA_PREPARATION_STATUS_INVALID")
    all_by_security = {item["security"]["security_id"]: item for item in all_requests}
    ready_security_ids = {
        security_id for security_id, request in all_by_security.items()
        if (
            preparation_by_security.get(security_id, {}).get("status") == "READY"
            if data_preparation is not None
            else bool(request["allowed_evidence_ids"])
        )
    }
    requests = [item for item in all_requests if item["security"]["security_id"] in ready_security_ids]
    stage_effective_concurrency = min(effective_concurrency, len(requests))
    stage_execution_reason = execution_mode_reason
    if stage_effective_concurrency <= 1 and stage_execution_reason is None:
        stage_execution_reason = (
            "仅一项普通股资料满足派发条件。"
            if stage_effective_concurrency == 1
            else "没有普通股资料满足派发条件。"
        )
    coverage = build_initial_research_coverage(
        handoff, council_request, batch_id=batch_id,
        target_concurrency=target_concurrency,
        effective_concurrency=stage_effective_concurrency,
        execution_mode_reason=stage_execution_reason,
        per_item_timeout_seconds=per_item_timeout_seconds,
        batch_budget_seconds=batch_budget_seconds,
    )
    preparation = []
    by_security = {item["security"]["security_id"]: item for item in all_requests}
    for position in handoff["portfolio"]["positions"]:
        request = by_security.get(position["security_id"])
        prepared = preparation_by_security.get(position["security_id"])
        prepared_status = prepared.get("status") if prepared else None
        if position["asset_type"] == "COMMON_STOCK" and position["security_id"] not in ready_security_ids:
            item = next(row for row in coverage["items"] if row["security_id"] == position["security_id"])
            failed = prepared_status == "FAILED"
            item.update({
                "execution_status": "FAILED" if failed else "NOT_STARTED",
                "research_status": "FAILED" if failed else "INSUFFICIENT_EVIDENCE",
                "coverage_status": "FAILED" if failed else "NOT_RESEARCHED",
                "failure_code": (
                    prepared.get("failure_code") if failed else "INSUFFICIENT_EVIDENCE"
                ),
            })
        preparation.append({
            "security_id": position["security_id"],
            "asset_type": position["asset_type"],
            "status": (
                "READY" if position["security_id"] in ready_security_ids
                else prepared_status if prepared_status in {"FAILED", "INSUFFICIENT_EVIDENCE"}
                else "INSUFFICIENT_EVIDENCE" if request
                else "CAPABILITY_GAP"
            ),
            "allowed_evidence_ids": request["allowed_evidence_ids"] if request else [],
            "data_gaps": (
                list(prepared.get("data_gaps", [])) if prepared is not None
                else request["data_gaps"] if request else [
                f"当前版本尚未提供 {position['asset_type']} 研究能力。"
                ]
            ),
        })
    coverage["coverage_hash"] = canonical_hash(_without_hash(coverage, "coverage_hash"))
    validate_research_coverage(coverage, handoff=handoff, council_request=council_request)
    stage = {
        "schema_version": "common-stock-research-stage/1.0.0",
        "stage": COMMON_STOCK_RESEARCH_STAGE,
        "run_id": run_id,
        "planning": plan,
        "holding_requests": requests,
        "coverage": coverage,
        "data_preparation": preparation,
        "common_cutoff": gate["decision_cutoff"],
        "evidence_bundle_hash": gate["bundle_hash"],
        "downstream_stages_started": [],
        "complete_portfolio_decision": False,
    }
    stage["stage_hash"] = canonical_hash(stage)
    return stage


def validate_research_coverage(
    value: Mapping[str, Any], *, handoff: Mapping[str, Any], council_request: Mapping[str, Any]
) -> None:
    try:
        validate_schema_instance(value, _schema("research-coverage.schema.json"))
    except SchemaValidationError as exc:
        raise CommonStockResearchError(f"RESEARCH_COVERAGE_SCHEMA_INVALID:{exc}") from exc
    expected_bindings = {
        "handoff_id": handoff["handoff_id"],
        "handoff_hash": handoff["handoff_hash"],
        "portfolio_hash": handoff["portfolio_hash"],
        "council_request_id": council_request["request_id"],
        "council_request_hash": council_request["request_hash"],
    }
    if any(value.get(field) != expected for field, expected in expected_bindings.items()):
        raise CommonStockResearchError("RESEARCH_COVERAGE_BINDING_INVALID")
    positions = {item["security_id"]: item for item in handoff["portfolio"]["positions"]}
    items = value.get("items", [])
    if len(items) != len(positions) or {item.get("security_id") for item in items} != set(positions):
        raise CommonStockResearchError("RESEARCH_COVERAGE_POSITION_SET_INVALID")
    for item in items:
        position = positions[item["security_id"]]
        if item["asset_type"] != position["asset_type"] or item["required_capability"] != CAPABILITY_BY_ASSET[position["asset_type"]]:
            raise CommonStockResearchError("RESEARCH_COVERAGE_ASSET_BINDING_INVALID")
        if position["asset_type"] != "COMMON_STOCK" and item["coverage_status"] not in {"CAPABILITY_GAP", "NOT_RESEARCHED"}:
            raise CommonStockResearchError("RESEARCH_COVERAGE_UNSUPPORTED_ASSET_INVALID")
        if item["coverage_status"] == "RESEARCHED" and (
            item["execution_status"] != "COMPLETED"
            or item["research_status"] not in {"VALID_RESEARCH", "LOW_CONFIDENCE", "INSUFFICIENT_EVIDENCE"}
            or not item["report_ref"]
        ):
            raise CommonStockResearchError("RESEARCH_COVERAGE_COMPLETION_INVALID")
        if item["eval_status"] == "NOT_EVALUATED" and any(
            item[field] is not None
            for field in ("eval_ref", "eval_result_hash", "evaluated_report_hash")
        ):
            raise CommonStockResearchError("RESEARCH_COVERAGE_UNEVALUATED_BINDING_INVALID")
        if item["eval_status"] in {"PASS", "FAIL"} and any(
            not item[field]
            for field in ("eval_ref", "eval_result_hash", "evaluated_report_hash")
        ):
            raise CommonStockResearchError("RESEARCH_COVERAGE_EVAL_BINDING_MISSING")
    if value.get("coverage_hash") != canonical_hash(_without_hash(value, "coverage_hash")):
        raise CommonStockResearchError("RESEARCH_COVERAGE_HASH_MISMATCH")
    if value["execution_mode"] == "SERIAL" and not value.get("execution_mode_reason"):
        raise CommonStockResearchError("RESEARCH_SERIAL_REASON_REQUIRED")
    if value["execution_mode"] == "PARALLEL" and value["effective_concurrency"] < 2:
        raise CommonStockResearchError("RESEARCH_PARALLEL_CAPACITY_INVALID")


EQUITY_DRAFT_KEYS = {
    "status", "research_summary", "sections", "claims", "assumptions",
    "counter_evidence_refs", "invalidation_conditions", "reevaluation_triggers",
    "monitoring_indicators", "data_gaps", "confidence", "confidence_rationale",
    "artifact_refs",
}


def envelope_equity_research_draft(
    draft: Mapping[str, Any], *, request: Mapping[str, Any],
    skill_execution: Sequence[Mapping[str, Any]], report_id: str,
    calculation_artifact_ids: Sequence[str] = (),
) -> dict[str, Any]:
    """Add frozen technical bindings without repairing model research content."""

    if not isinstance(draft, Mapping):
        raise CommonStockResearchError("EQUITY_RESEARCH_DRAFT_INVALID")
    _exact_keys(draft, EQUITY_DRAFT_KEYS, "EQUITY_RESEARCH_DRAFT_KEYS_INVALID")
    if "skill_execution" in draft or "bindings" in draft or "security" in draft:
        raise CommonStockResearchError("EQUITY_RESEARCH_DRAFT_TECHNICAL_FIELD_FORBIDDEN")
    report = {
        "schema_version": EQUITY_REPORT_VERSION,
        "run_id": request["run_id"],
        "invocation_id": request["invocation_id"],
        "report_id": report_id,
        "agent": "runtime_company_analyst",
        "bindings": {
            "handoff_id": request["handoff_id"],
            "handoff_hash": request["handoff_hash"],
            "portfolio_hash": request["portfolio_hash"],
            "council_request_id": request["council_request_id"],
            "council_request_hash": request["council_request_hash"],
            "holding_research_request_id": request["request_id"],
            "holding_research_request_hash": request["request_hash"],
            "decision_cutoff": request["decision_cutoff"],
        },
        "security": {
            key: request["security"][key]
            for key in ("security_id", "display_symbol", "display_name", "market", "asset_type")
        },
        "research_scope": "SINGLE_COMMON_STOCK_HOLDING",
        **copy.deepcopy(dict(draft)),
        "skill_execution": copy.deepcopy(list(skill_execution)),
    }
    validate_equity_research_report(
        report, request=request, calculation_artifact_ids=calculation_artifact_ids
    )
    return report


def build_cio_equity_research_input(
    reports: Sequence[Mapping[str, Any]], *, requests: Mapping[str, Mapping[str, Any]],
    calculation_artifact_ids: Mapping[str, Sequence[str]] | None = None,
) -> dict[str, Any]:
    """Pass complete validated reports to CIO; never reduce them to summaries."""

    validated: list[dict[str, Any]] = []
    for report in reports:
        security_id = report.get("security", {}).get("security_id") if isinstance(report, Mapping) else None
        if security_id not in requests:
            raise CommonStockResearchError("CIO_EQUITY_REPORT_REQUEST_MISSING")
        validate_equity_research_report(
            report,
            request=requests[security_id],
            calculation_artifact_ids=(calculation_artifact_ids or {}).get(security_id, ()),
        )
        validated.append(copy.deepcopy(dict(report)))
    return {
        "schema_version": "cio-equity-research-input/1.0.0",
        "reports": validated,
        "report_hashes": {
            item["security"]["security_id"]: canonical_hash(item) for item in validated
        },
    }


def build_retry_request(request: Mapping[str, Any], *, retry_sequence: int) -> dict[str, Any]:
    """Create an explicit new invocation for one failed item; never overwrite it."""

    if not isinstance(retry_sequence, int) or isinstance(retry_sequence, bool) or retry_sequence < 1:
        raise CommonStockResearchError("RESEARCH_RETRY_SEQUENCE_INVALID")
    value = copy.deepcopy(dict(request))
    value["request_id"] = f"{request['request_id']}:retry-{retry_sequence}"
    value["invocation_id"] = f"{request['invocation_id']}:retry-{retry_sequence}"
    value["request_hash"] = canonical_hash(_without_hash(value, "request_hash"))
    return value


@dataclass(slots=True)
class BoundedResearchDispatch:
    """State-only seam used by the Codex parent to track Subagent dispatch.

    It intentionally has no callback, subprocess or model client.  Codex owns
    the actual ``spawn_agent``/wait lifecycle; this class validates and records
    the resulting state transitions.
    """

    requests: Mapping[str, Mapping[str, Any]]
    coverage: dict[str, Any]
    events: list[dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.requests = {key: copy.deepcopy(dict(value)) for key, value in self.requests.items()}
        self.coverage = copy.deepcopy(self.coverage)
        dispatchable_ids = {
            item["security_id"] for item in self.coverage["items"]
            if item["asset_type"] == "COMMON_STOCK"
            and item["execution_status"] in {"QUEUED", "RUNNING"}
        }
        if set(self.requests) != dispatchable_ids:
            raise CommonStockResearchError("RESEARCH_DISPATCH_REQUEST_COVERAGE_INVALID")

    def _item(self, security_id: str) -> dict[str, Any]:
        matches = [item for item in self.coverage["items"] if item["security_id"] == security_id]
        if len(matches) != 1:
            raise CommonStockResearchError("RESEARCH_DISPATCH_SECURITY_UNKNOWN")
        return matches[0]

    @property
    def active_count(self) -> int:
        return sum(item["execution_status"] == "RUNNING" for item in self.coverage["items"])

    def next_dispatches(self) -> list[dict[str, Any]]:
        if self.coverage.get("cancelled_at") is not None:
            return []
        slots = max(0, self.coverage["effective_concurrency"] - self.active_count)
        queued = [
            item["security_id"] for item in self.coverage["items"]
            if item["execution_status"] == "QUEUED"
        ]
        return [copy.deepcopy(self.requests[security_id]) for security_id in queued[:slots]]

    def record_started(self, security_id: str, *, child_session_id: str, started_at: str) -> None:
        item = self._item(security_id)
        if item["execution_status"] != "QUEUED" or self.active_count >= self.coverage["effective_concurrency"]:
            raise CommonStockResearchError("RESEARCH_DISPATCH_START_INVALID")
        parse_timestamp(started_at)
        if not child_session_id:
            raise CommonStockResearchError("RESEARCH_CHILD_SESSION_REQUIRED")
        item["execution_status"] = "RUNNING"
        item["invocation_id"] = self.requests[security_id]["invocation_id"]
        if self.coverage["batch_started_at"] is None:
            self.coverage["batch_started_at"] = started_at
        self.events.append({
            "event": "STARTED", "security_id": security_id,
            "invocation_id": item["invocation_id"], "child_session_id": child_session_id,
            "at": started_at,
        })
        self._rehash()

    def expire(self, *, observed_at: str) -> None:
        """Record item timeout or batch-budget exhaustion without retrying."""

        now = parse_timestamp(observed_at)
        batch_started = self.coverage.get("batch_started_at")
        if batch_started is not None and (
            now - parse_timestamp(batch_started)
        ).total_seconds() >= self.coverage["batch_budget_seconds"]:
            for item in self.coverage["items"]:
                if item["execution_status"] in {"QUEUED", "RUNNING"}:
                    item.update(
                        execution_status="TIMEOUT" if item["execution_status"] == "RUNNING" else "CANCELLED",
                        research_status="FAILED", coverage_status="FAILED",
                        failure_code="RESEARCH_BATCH_BUDGET_EXHAUSTED",
                    )
            self.events.append({"event": "BATCH_BUDGET_EXHAUSTED", "at": observed_at})
            self._rehash()
            return
        starts = {
            event["security_id"]: parse_timestamp(event["at"])
            for event in self.events if event.get("event") == "STARTED"
        }
        for item in self.coverage["items"]:
            started = starts.get(item["security_id"])
            if (
                item["execution_status"] == "RUNNING"
                and started is not None
                and (now - started).total_seconds() >= self.coverage["per_item_timeout_seconds"]
            ):
                item.update(
                    execution_status="TIMEOUT", research_status="FAILED",
                    coverage_status="FAILED", failure_code="RESEARCH_ITEM_TIMEOUT",
                )
                self.events.append({
                    "event": "FAILED", "security_id": item["security_id"],
                    "invocation_id": item["invocation_id"], "at": observed_at,
                    "failure_code": "RESEARCH_ITEM_TIMEOUT",
                })
        self._rehash()

    def record_completed(
        self, security_id: str, *, report: Mapping[str, Any], report_ref: str,
        completed_at: str, calculation_artifact_ids: Sequence[str] = (),
    ) -> None:
        item = self._item(security_id)
        if item["execution_status"] != "RUNNING":
            raise CommonStockResearchError("RESEARCH_DISPATCH_COMPLETION_INVALID")
        parse_timestamp(completed_at)
        validate_equity_research_report(
            report, request=self.requests[security_id],
            calculation_artifact_ids=calculation_artifact_ids,
        )
        status_map = {
            "COMPLETE": "VALID_RESEARCH",
            "LOW_CONFIDENCE": "LOW_CONFIDENCE",
            "INSUFFICIENT_EVIDENCE": "INSUFFICIENT_EVIDENCE",
            "TIMEOUT": "FAILED",
        }
        item.update(
            execution_status="TIMEOUT" if report["status"] == "TIMEOUT" else "COMPLETED",
            research_status=status_map[report["status"]],
            coverage_status="FAILED" if report["status"] == "TIMEOUT" else "RESEARCHED",
            report_ref=report_ref,
            report_hash=canonical_hash(report),
            failure_code="RESEARCH_TIMEOUT" if report["status"] == "TIMEOUT" else None,
        )
        self.events.append({
            "event": "COMPLETED", "security_id": security_id,
            "invocation_id": item["invocation_id"], "at": completed_at,
            "report_hash": canonical_hash(report), "research_status": item["research_status"],
        })
        self._rehash()

    def record_failed(self, security_id: str, *, failure_code: str, completed_at: str) -> None:
        item = self._item(security_id)
        if item["execution_status"] != "RUNNING" or not failure_code:
            raise CommonStockResearchError("RESEARCH_DISPATCH_FAILURE_INVALID")
        parse_timestamp(completed_at)
        item.update(
            execution_status="FAILED", research_status="FAILED", coverage_status="FAILED",
            failure_code=failure_code,
        )
        self.events.append({
            "event": "FAILED", "security_id": security_id,
            "invocation_id": item["invocation_id"], "at": completed_at,
            "failure_code": failure_code,
        })
        self._rehash()

    def cancel(self, *, cancelled_at: str) -> None:
        parse_timestamp(cancelled_at)
        self.coverage["cancelled_at"] = cancelled_at
        for item in self.coverage["items"]:
            if item["execution_status"] in {"QUEUED", "RUNNING"}:
                item.update(
                    execution_status="CANCELLED", research_status="NOT_RESEARCHED",
                    coverage_status="NOT_RESEARCHED", failure_code="RESEARCH_CANCELLED",
                )
        self.coverage["stage_status"] = "CANCELLED"
        self.events.append({"event": "BATCH_CANCELLED", "at": cancelled_at})
        self._rehash()

    def finalize(self) -> dict[str, Any]:
        unfinished = [
            item for item in self.coverage["items"]
            if item["asset_type"] == "COMMON_STOCK" and item["execution_status"] in {"QUEUED", "RUNNING"}
        ]
        if unfinished:
            raise CommonStockResearchError("RESEARCH_DISPATCH_UNFINISHED")
        if self.coverage["stage_status"] != "CANCELLED":
            complete = all(
                item["coverage_status"] == "RESEARCHED"
                for item in self.coverage["items"]
            )
            self.coverage["stage_status"] = "RESEARCH_COMPLETE" if complete else "PARTIAL_RESEARCH"
        self._rehash()
        return copy.deepcopy(self.coverage)

    def _rehash(self) -> None:
        self.coverage["coverage_hash"] = canonical_hash(
            _without_hash(self.coverage, "coverage_hash")
        )


def parallel_intervals_overlap(events: Sequence[Mapping[str, Any]]) -> bool:
    """Prove overlap from actual child start/end events, not parent dispatch time."""

    starts: dict[str, Any] = {}
    intervals: list[tuple[Any, Any]] = []
    for event in events:
        invocation_id = event.get("invocation_id")
        if event.get("event") == "STARTED" and isinstance(invocation_id, str):
            starts[invocation_id] = parse_timestamp(str(event["at"]))
        if event.get("event") in {"COMPLETED", "FAILED"} and invocation_id in starts:
            intervals.append((starts[invocation_id], parse_timestamp(str(event["at"]))))
    return any(
        first_start < second_end and second_start < first_end
        for index, (first_start, first_end) in enumerate(intervals)
        for second_start, second_end in intervals[index + 1 :]
    )
