"""Agent Package Demo 的最小版本化契约与 fail-closed 校验。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.runtime.decision_contract import (
    load_decision_contract,
    validate_decision_action,
)
from product.runtime.evidence_gate import validate_fixture
from product.runtime.hashing import canonical_hash
from product.runtime.validation import (
    collect_evidence_refs,
    validate_cio_draft,
    validate_company_report,
    validate_evidence_closure,
    validate_skeptic_report,
)


DEMO_INPUT_VERSION = "agent-package-demo-input/1.0.0"
REQUEST_VERSION = "demo-agent-request/1.0.0"
RESPONSE_VERSION = "demo-agent-response/1.0.0"
DISPATCH_VERSION = "demo-dispatch-record/1.0.0"
DECISION_ENVELOPE_VERSION = "demo-decision-envelope/1.0.0"
TOPOLOGY_VERSION = "agent-package-topology/1.0.0"
RUN_VERSION = "agent-package-demo-run/1.0.0"

AGENTS = (
    "runtime_company_analyst",
    "runtime_skeptic",
    "runtime_cio",
)
SPECIALISTS = AGENTS[:2]
DOMAIN_STATUSES = {
    "COMPLETE",
    "INSUFFICIENT_EVIDENCE",
    "LOW_CONFIDENCE",
    "TIMEOUT",
}
TERMINAL_STATES = {
    "DEMO_COMPLETED",
    "DEMO_SAFE_NO_TRADE",
    "DEMO_FAILED_VALIDATION",
}


class DemoValidationError(ValueError):
    """Demo 输入、身份、传递或产物不满足约定。"""


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    missing = sorted(expected - value.keys())
    extra = sorted(value.keys() - expected)
    if missing or extra:
        raise DemoValidationError(
            f"{label}_KEYS_INVALID:missing={missing},extra={extra}"
        )


def _require_text(value: Any, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DemoValidationError(code)
    return value


def _forbidden_keys(value: Any, forbidden: set[str]) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        found.update(forbidden & set(value))
        for child in value.values():
            found.update(_forbidden_keys(child, forbidden))
    elif isinstance(value, list):
        for child in value:
            found.update(_forbidden_keys(child, forbidden))
    return found


def load_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DemoValidationError(f"JSON_OBJECT_UNREADABLE:{path}") from exc
    if not isinstance(value, Mapping):
        raise DemoValidationError("JSON_OBJECT_REQUIRED")
    return dict(value)


def validate_demo_input(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "profile",
        "synthetic",
        "advisory_only",
        "llm_used",
        "fixture_version",
        "fixture_id",
        "scenario_type",
        "run_id",
        "research_question",
        "decision_cutoff",
        "freshness_policy",
        "conflict_policy_version",
        "portfolio",
        "evidence",
        "role_samples",
        "domain_status_examples",
        "risk_veto_cio_sample",
    }
    _require_exact_keys(value, expected, "DEMO_INPUT")
    if value.get("schema_version") != DEMO_INPUT_VERSION:
        raise DemoValidationError("DEMO_INPUT_VERSION_INVALID")
    if value.get("profile") != "DEMO_SCAFFOLD":
        raise DemoValidationError("DEMO_PROFILE_REQUIRED")
    if (
        value.get("synthetic") is not True
        or value.get("advisory_only") is not True
        or value.get("llm_used") is not False
    ):
        raise DemoValidationError("DEMO_IDENTITY_FLAGS_INVALID")
    _require_text(value.get("run_id"), "DEMO_RUN_ID_REQUIRED")
    _require_text(value.get("research_question"), "RESEARCH_QUESTION_REQUIRED")
    if value.get("scenario_type") != "agent_package_demo":
        raise DemoValidationError("DEMO_SCENARIO_TYPE_INVALID")
    try:
        validate_fixture(value)
    except ValueError as exc:
        raise DemoValidationError(str(exc)) from exc

    samples = value.get("role_samples")
    if not isinstance(samples, Mapping):
        raise DemoValidationError("ROLE_SAMPLES_REQUIRED")
    _require_exact_keys(samples, {"analyst", "skeptic", "cio"}, "ROLE_SAMPLES")
    for role, sample in samples.items():
        if not isinstance(sample, Mapping):
            raise DemoValidationError(f"ROLE_SAMPLE_INVALID:{role}")
        if sample.get("status") not in DOMAIN_STATUSES:
            raise DemoValidationError(f"ROLE_STATUS_INVALID:{role}")
    forbidden = {"action", "target_weight_range", "maximum_notional"}
    for role in ("analyst", "skeptic"):
        leaked = _forbidden_keys(samples[role], forbidden)
        if leaked:
            raise DemoValidationError(
                f"SPECIALIST_DECISION_FIELD_FORBIDDEN:{role}:{','.join(sorted(leaked))}"
            )
    statuses = value.get("domain_status_examples")
    if not isinstance(statuses, list) or set(statuses) != DOMAIN_STATUSES:
        raise DemoValidationError("DOMAIN_STATUS_EXAMPLES_INCOMPLETE")
    veto_sample = value.get("risk_veto_cio_sample")
    if not isinstance(veto_sample, Mapping) or veto_sample.get("status") not in DOMAIN_STATUSES:
        raise DemoValidationError("RISK_VETO_SAMPLE_INVALID")
    return dict(value)


def load_demo_input(path: Path) -> dict[str, Any]:
    return validate_demo_input(load_json_object(path))


def artifact_ref(artifact_id: str, value: Mapping[str, Any]) -> dict[str, str]:
    return {
        "artifact_id": _require_text(artifact_id, "ARTIFACT_ID_REQUIRED"),
        "artifact_hash": canonical_hash(value),
    }


def validate_artifact_ref(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise DemoValidationError("ARTIFACT_REF_INVALID")
    _require_exact_keys(value, {"artifact_id", "artifact_hash"}, "ARTIFACT_REF")
    _require_text(value.get("artifact_id"), "ARTIFACT_ID_REQUIRED")
    digest = value.get("artifact_hash")
    if not isinstance(digest, str) or len(digest) != 64 or any(
        char not in "0123456789abcdef" for char in digest
    ):
        raise DemoValidationError("ARTIFACT_HASH_INVALID")
    return dict(value)


def validate_agent_request(value: Mapping[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version",
        "run_id",
        "invocation_id",
        "sender",
        "recipient",
        "input_refs",
        "portfolio_summary",
        "research_question",
        "decision_cutoff",
        "allowed_evidence_ids",
        "demo_payload",
        "upstream_responses",
    }
    _require_exact_keys(value, expected, "AGENT_REQUEST")
    if value.get("schema_version") != REQUEST_VERSION:
        raise DemoValidationError("AGENT_REQUEST_VERSION_INVALID")
    _require_text(value.get("run_id"), "REQUEST_RUN_ID_REQUIRED")
    _require_text(value.get("invocation_id"), "INVOCATION_ID_REQUIRED")
    if value.get("sender") != "demo_orchestrator" or value.get("recipient") not in AGENTS:
        raise DemoValidationError("REQUEST_ROUTE_INVALID")
    refs = value.get("input_refs")
    if not isinstance(refs, list) or not refs:
        raise DemoValidationError("REQUEST_INPUT_REFS_REQUIRED")
    for ref in refs:
        validate_artifact_ref(ref)
    evidence_ids = value.get("allowed_evidence_ids")
    if not isinstance(evidence_ids, list) or any(
        not isinstance(item, str) or not item for item in evidence_ids
    ) or len(evidence_ids) != len(set(evidence_ids)):
        raise DemoValidationError("ALLOWED_EVIDENCE_IDS_INVALID")
    if not isinstance(value.get("portfolio_summary"), Mapping):
        raise DemoValidationError("PORTFOLIO_SUMMARY_REQUIRED")
    _require_text(value.get("research_question"), "RESEARCH_QUESTION_REQUIRED")
    _require_text(value.get("decision_cutoff"), "DECISION_CUTOFF_REQUIRED")
    if not isinstance(value.get("demo_payload"), Mapping):
        raise DemoValidationError("DEMO_PAYLOAD_REQUIRED")
    upstream = value.get("upstream_responses")
    if not isinstance(upstream, list):
        raise DemoValidationError("UPSTREAM_RESPONSES_INVALID")
    if value["recipient"] in SPECIALISTS and upstream:
        raise DemoValidationError("SPECIALIST_CONTEXT_ISOLATION_VIOLATION")
    if value["recipient"] == "runtime_cio" and len(upstream) != 2:
        raise DemoValidationError("CIO_REQUIRES_TWO_SPECIALIST_RESPONSES")
    return dict(value)


def validate_agent_response(
    value: Mapping[str, Any], *, request: Mapping[str, Any]
) -> dict[str, Any]:
    expected = {
        "schema_version",
        "run_id",
        "invocation_id",
        "agent_name",
        "status",
        "input_refs",
        "output",
        "producer_type",
        "llm_used",
        "skill_reasoning_executed",
    }
    _require_exact_keys(value, expected, "AGENT_RESPONSE")
    validate_agent_request(request)
    if value.get("schema_version") != RESPONSE_VERSION:
        raise DemoValidationError("AGENT_RESPONSE_VERSION_INVALID")
    if value.get("run_id") != request.get("run_id"):
        raise DemoValidationError("CROSS_RUN_OUTPUT")
    if value.get("invocation_id") != request.get("invocation_id"):
        raise DemoValidationError("INVOCATION_ID_MISMATCH")
    if value.get("agent_name") != request.get("recipient"):
        raise DemoValidationError("AGENT_IDENTITY_MISMATCH")
    if value.get("status") not in DOMAIN_STATUSES:
        raise DemoValidationError("ILLEGAL_DOMAIN_STATUS")
    if value.get("input_refs") != request.get("input_refs"):
        raise DemoValidationError("INPUT_REFERENCE_MISMATCH")
    if (
        value.get("producer_type") != "deterministic_demo"
        or value.get("llm_used") is not False
        or value.get("skill_reasoning_executed") is not False
    ):
        raise DemoValidationError("DEMO_PRODUCER_IDENTITY_INVALID")
    if not isinstance(value.get("output"), Mapping):
        raise DemoValidationError("AGENT_OUTPUT_REQUIRED")
    if "next_recipient" in value or "next_recipient" in value["output"]:
        raise DemoValidationError("AGENT_ROUTING_DECISION_FORBIDDEN")
    return dict(value)


def role_manifest(
    response: Mapping[str, Any], *, allowed_evidence_ids: Sequence[str]
) -> dict[str, Any]:
    output = response["output"]
    return {
        "invocation_id": response["invocation_id"],
        "evidence_ids": list(allowed_evidence_ids),
        "skill_execution": output["skill_execution"],
    }


def validate_role_response(
    value: Mapping[str, Any], *, request: Mapping[str, Any]
) -> set[str]:
    response = validate_agent_response(value, request=request)
    output = response["output"]
    manifest = role_manifest(response, allowed_evidence_ids=request["allowed_evidence_ids"])
    try:
        if response["agent_name"] == "runtime_company_analyst":
            return validate_company_report(output, run_id=response["run_id"], manifest=manifest)
        if response["agent_name"] == "runtime_skeptic":
            return validate_skeptic_report(output, run_id=response["run_id"], manifest=manifest)
        report_hashes = {
            item["agent_name"]: canonical_hash(item["output"])
            for item in request["upstream_responses"]
        }
        return validate_cio_draft(
            output,
            run_id=response["run_id"],
            manifest=manifest,
            report_hashes=report_hashes,
        )
    except ValueError as exc:
        raise DemoValidationError(str(exc)) from exc


def validate_dispatch_record(
    value: Mapping[str, Any],
    *,
    expected_run_id: str | None = None,
    expected_sender: str | None = None,
    expected_recipient: str | None = None,
) -> dict[str, Any]:
    _require_exact_keys(
        value,
        {
            "schema_version",
            "run_id",
            "dispatch_id",
            "from",
            "to",
            "artifact_ref",
            "validation_status",
        },
        "DISPATCH_RECORD",
    )
    if value.get("schema_version") != DISPATCH_VERSION:
        raise DemoValidationError("DISPATCH_VERSION_INVALID")
    if expected_run_id is not None and value.get("run_id") != expected_run_id:
        raise DemoValidationError("DISPATCH_RUN_ID_MISMATCH")
    if expected_sender is not None and value.get("from") != expected_sender:
        raise DemoValidationError("DISPATCH_SENDER_MISMATCH")
    if expected_recipient is not None and value.get("to") != expected_recipient:
        raise DemoValidationError("DISPATCH_RECIPIENT_MISMATCH")
    if value.get("from") not in {*AGENTS, "demo_orchestrator"}:
        raise DemoValidationError("DISPATCH_SENDER_INVALID")
    if value.get("to") not in {*AGENTS, "deterministic_risk_engine"}:
        raise DemoValidationError("DISPATCH_RECIPIENT_INVALID")
    _require_text(value.get("dispatch_id"), "DISPATCH_ID_REQUIRED")
    validate_artifact_ref(value.get("artifact_ref"))
    if value.get("validation_status") != "VALIDATED":
        raise DemoValidationError("UNVALIDATED_DISPATCH_FORBIDDEN")
    return dict(value)


def validate_final_decision(
    decision: Mapping[str, Any], *, allowed_evidence_ids: Sequence[str]
) -> set[str]:
    try:
        validate_decision_action(
            decision,
            load_decision_contract(Path(__file__).resolve().parents[1]),
        )
        return validate_evidence_closure(
            decision, allowed_evidence_ids=allowed_evidence_ids
        )
    except ValueError as exc:
        raise DemoValidationError(str(exc)) from exc


def referenced_evidence(value: Mapping[str, Any]) -> list[str]:
    return sorted(collect_evidence_refs(value))
