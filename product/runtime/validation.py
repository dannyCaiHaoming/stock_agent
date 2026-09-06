"""Strict structured-output and Evidence Closure validation."""

from __future__ import annotations

from typing import Any, Mapping, Sequence


DOMAIN_STATUSES = {"COMPLETE", "TIMEOUT", "INSUFFICIENT_EVIDENCE", "LOW_CONFIDENCE"}
DECISION_ACTIONS = {"BUY", "ADD", "HOLD", "TRIM", "EXIT", "NO_TRADE"}
RESEARCH_REQUIRED = {
    "schema_version", "run_id", "invocation_id", "status", "agent", "scope",
    "claims", "assumptions", "counter_evidence_refs", "uncertainties", "data_gaps",
    "invalidation_conditions", "confidence", "confidence_rationale", "skill_execution",
    "artifact_refs",
}
SKEPTIC_REQUIRED = {
    "schema_version", "run_id", "invocation_id", "status", "agent", "mode", "scope",
    "challenges", "evidence_refs", "counter_evidence_refs", "uncertainties", "data_gaps",
    "invalidation_conditions", "confidence", "confidence_rationale", "skill_execution",
    "artifact_refs",
}
CIO_REQUIRED = {
    "schema_version", "run_id", "invocation_id", "status", "agent", "consumed_reports",
    "action", "security_id", "current_weight", "target_weight_range", "maximum_notional",
    "time_horizon", "thesis", "counter_thesis", "consensus", "conflicts",
    "unresolved_questions", "invalidation_conditions", "confidence", "confidence_rationale",
    "evidence_refs", "no_trade_reason", "no_trade_explanation", "reevaluation_conditions",
    "skill_execution", "advisory_only",
}
CIO_CONFLICT_REQUIRED = {
    "conflict_key",
    "evidence_refs",
    "summary",
    "unresolved",
    "decision_impact",
    "confidence_impact",
}


class ArtifactValidationError(ValueError):
    pass


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    missing = sorted(expected - value.keys())
    extra = sorted(value.keys() - expected)
    if missing or extra:
        raise ArtifactValidationError(f"{name} keys invalid; missing={missing}, extra={extra}")


def _validate_common(
    value: Mapping[str, Any], *, run_id: str, manifest: Mapping[str, Any], agent: str
) -> None:
    if value.get("run_id") != run_id:
        raise ArtifactValidationError("CROSS_RUN_OUTPUT")
    if value.get("invocation_id") != manifest.get("invocation_id"):
        raise ArtifactValidationError("INVOCATION_ID_MISMATCH")
    if value.get("agent") != agent:
        raise ArtifactValidationError("AGENT_IDENTITY_MISMATCH")
    if value.get("status") not in DOMAIN_STATUSES:
        raise ArtifactValidationError("ILLEGAL_DOMAIN_STATUS")
    confidence = value.get("confidence")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
        raise ArtifactValidationError("INVALID_CONFIDENCE")
    if value.get("skill_execution") != manifest.get("skill_execution"):
        raise ArtifactValidationError("SKILL_EXECUTION_PROOF_MISMATCH")


def collect_evidence_refs(value: Any) -> set[str]:
    refs: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in {"evidence_refs", "counter_evidence_refs"}:
                if not isinstance(item, list) or any(not isinstance(ref, str) for ref in item):
                    raise ArtifactValidationError(f"{key} must be a string array")
                refs.update(item)
            else:
                refs.update(collect_evidence_refs(item))
    elif isinstance(value, list):
        for item in value:
            refs.update(collect_evidence_refs(item))
    return refs


def validate_evidence_closure(
    value: Mapping[str, Any], *, allowed_evidence_ids: Sequence[str]
) -> set[str]:
    refs = collect_evidence_refs(value)
    unknown = refs - set(allowed_evidence_ids)
    if unknown:
        raise ArtifactValidationError(f"EVIDENCE_CLOSURE_FAILED:{','.join(sorted(unknown))}")
    return refs


def validate_company_report(
    value: Mapping[str, Any], *, run_id: str, manifest: Mapping[str, Any]
) -> set[str]:
    _require_exact_keys(value, RESEARCH_REQUIRED, "AgentResearchReport")
    if value.get("schema_version") != "agent-research-report/2.0.0":
        raise ArtifactValidationError("SCHEMA_VERSION_MISMATCH")
    _validate_common(value, run_id=run_id, manifest=manifest, agent="runtime_company_analyst")
    assumptions = {
        item.get("assumption_id") for item in value["assumptions"] if isinstance(item, Mapping)
    }
    for claim in value["claims"]:
        if not isinstance(claim, Mapping):
            raise ArtifactValidationError("INVALID_CLAIM")
        refs = claim.get("evidence_refs", [])
        assumption_ids = claim.get("assumption_ids", [])
        if not refs and not assumption_ids:
            raise ArtifactValidationError("UNGROUNDED_CLAIM")
        if set(assumption_ids) - assumptions:
            raise ArtifactValidationError("UNKNOWN_ASSUMPTION")
    return validate_evidence_closure(value, allowed_evidence_ids=manifest["evidence_ids"])


def validate_skeptic_report(
    value: Mapping[str, Any], *, run_id: str, manifest: Mapping[str, Any]
) -> set[str]:
    _require_exact_keys(value, SKEPTIC_REQUIRED, "CounterThesisReport")
    if value.get("schema_version") != "counter-thesis-report/2.0.0":
        raise ArtifactValidationError("SCHEMA_VERSION_MISMATCH")
    _validate_common(value, run_id=run_id, manifest=manifest, agent="runtime_skeptic")
    if value.get("mode") != "INDEPENDENT_FIRST_PASS":
        raise ArtifactValidationError("CONTEXT_ISOLATION_VIOLATION")
    for challenge in value["challenges"]:
        if not isinstance(challenge, Mapping):
            raise ArtifactValidationError("INVALID_CHALLENGE")
        if not challenge.get("evidence_refs") and not challenge.get("assumption_ids"):
            raise ArtifactValidationError("UNGROUNDED_CHALLENGE")
    return validate_evidence_closure(value, allowed_evidence_ids=manifest["evidence_ids"])


def validate_cio_draft(
    value: Mapping[str, Any],
    *,
    run_id: str,
    manifest: Mapping[str, Any],
    report_hashes: Mapping[str, str] | None = None,
) -> set[str]:
    _require_exact_keys(value, CIO_REQUIRED, "CIODecisionDraft")
    if value.get("schema_version") != "cio-decision-draft/2.0.0":
        raise ArtifactValidationError("SCHEMA_VERSION_MISMATCH")
    _validate_common(value, run_id=run_id, manifest=manifest, agent="runtime_cio")
    if value.get("status") not in {"COMPLETE", "INSUFFICIENT_EVIDENCE", "LOW_CONFIDENCE"}:
        raise ArtifactValidationError("ILLEGAL_CIO_STATUS")
    if value.get("action") not in DECISION_ACTIONS:
        raise ArtifactValidationError("INVALID_ACTION")
    if value.get("advisory_only") is not True:
        raise ArtifactValidationError("ADVISORY_ONLY_REQUIRED")
    consumed = value.get("consumed_reports", [])
    if len(consumed) != 2 or any(not isinstance(item, Mapping) for item in consumed):
        raise ArtifactValidationError("BOTH_SPECIALIST_REPORTS_REQUIRED")
    consumed_hashes = {
        str(item.get("agent")): str(item.get("output_hash")) for item in consumed
    }
    if set(consumed_hashes) != {"runtime_company_analyst", "runtime_skeptic"}:
        raise ArtifactValidationError("SPECIALIST_REPORT_IDENTITY_INVALID")
    if any(len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest) for digest in consumed_hashes.values()):
        raise ArtifactValidationError("SPECIALIST_REPORT_HASH_INVALID")
    if report_hashes is not None and consumed_hashes != dict(report_hashes):
        raise ArtifactValidationError("SPECIALIST_REPORT_HASH_MISMATCH")
    for conflict in value.get("conflicts", []):
        if not isinstance(conflict, Mapping):
            raise ArtifactValidationError("CIO_CONFLICT_NOT_OBJECT")
        _require_exact_keys(conflict, CIO_CONFLICT_REQUIRED, "CIOConflict")
        if (
            not isinstance(conflict.get("evidence_refs"), list)
            or len(set(conflict["evidence_refs"])) < 2
        ):
            raise ArtifactValidationError("CIO_CONFLICT_REQUIRES_MULTIPLE_EVIDENCE")
        if conflict.get("unresolved") is not True:
            raise ArtifactValidationError("CIO_CONFLICT_MUST_RETAIN_UNRESOLVED_STATE")
        for field in (
            "conflict_key",
            "summary",
            "decision_impact",
            "confidence_impact",
        ):
            if not isinstance(conflict.get(field), str) or not conflict[field].strip():
                raise ArtifactValidationError(f"CIO_CONFLICT_FIELD_REQUIRED:{field}")
    if value["action"] == "NO_TRADE":
        if not value.get("no_trade_reason") or not value.get("no_trade_explanation") or not value.get("reevaluation_conditions"):
            raise ArtifactValidationError("NO_TRADE_FIELDS_REQUIRED")
        if value.get("target_weight_range") is not None or value.get("maximum_notional") is not None:
            raise ArtifactValidationError("NO_TRADE_EXECUTION_FIELDS_FORBIDDEN")
    else:
        if value.get("security_id") is None or value.get("current_weight") is None or value.get("target_weight_range") is None:
            raise ArtifactValidationError("ACTION_WEIGHT_FIELDS_REQUIRED")
        if not value.get("thesis") or not value.get("evidence_refs") or not value.get("invalidation_conditions"):
            raise ArtifactValidationError("ACTION_RATIONALE_FIELDS_REQUIRED")
        if value.get("no_trade_reason") is not None or value.get("no_trade_explanation") is not None:
            raise ArtifactValidationError("ACTION_NO_TRADE_FIELDS_FORBIDDEN")
    return validate_evidence_closure(value, allowed_evidence_ids=manifest["evidence_ids"])
