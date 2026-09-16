"""多维持仓研究的确定性交接契约。

本模块只验证身份、引用、覆盖和状态，不做投资判断，也不调用模型。
"""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.runtime.hashing import canonical_hash
from product.runtime.schema_validation import SchemaValidationError, validate_schema_instance
from product.runtime.validation import ArtifactValidationError, validate_evidence_closure


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = REPO_ROOT / "product" / "schemas" / "runtime"
DIMENSION_REPORT_VERSION = "research-dimension-report/1.1.0"
HOLDING_RESEARCH_BUNDLE_VERSION = "holding-research-bundle/1.1.0"

RESEARCH_CAPABILITIES = (
    "TECHNICAL_STRUCTURE",
    "FUNDAMENTAL_EVENT",
    "RESEARCH_REPORT",
    "INDUSTRY_COMPARISON",
    "MACRO_MARKET",
    "OWNERSHIP_DISCLOSURE",
    "OPTIONS_FLOW",
)
BUNDLE_CAPABILITIES = ("COMPANY_RESEARCH", *RESEARCH_CAPABILITIES)
REPORT_STATUSES = {
    "COMPLETE",
    "LOW_CONFIDENCE",
    "INSUFFICIENT_EVIDENCE",
    "SOURCE_LIMITED",
    "FAILED",
    "TIMEOUT",
}
FORBIDDEN_RESEARCH_KEYS = {
    "action",
    "trade_action",
    "target_weight",
    "target_weight_range",
    "maximum_notional",
    "recommended_quantity",
    "order",
    "order_id",
    "order_quantity",
}
CANONICAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


class MultiDimensionalResearchError(ValueError):
    """多维研究产物违反 fail-closed 契约。"""


def _schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))


def _without_hash(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result.pop(key, None)
    return result


def _canonical_ids(values: Any, field: str) -> list[str]:
    if not isinstance(values, list):
        raise MultiDimensionalResearchError(f"DIMENSION_ID_ARRAY_INVALID:{field}")
    if any(not isinstance(item, str) or not CANONICAL_ID.fullmatch(item) for item in values):
        raise MultiDimensionalResearchError(f"DIMENSION_ID_INVALID:{field}")
    if len(values) != len(set(values)):
        raise MultiDimensionalResearchError(f"DIMENSION_ID_DUPLICATE:{field}")
    return values


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


def validate_research_dimension_report(
    value: Mapping[str, Any],
    *,
    expected_bindings: Mapping[str, Any],
    allowed_security_ids: Sequence[str],
    allowed_evidence_ids: Sequence[str],
    known_research_claim_ids: Sequence[str] = (),
    allowed_documents: Sequence[Mapping[str, Any]] | None = None,
) -> set[str]:
    """验证一个维度报告及其原始 Evidence / 派生主张引用。"""

    try:
        validate_schema_instance(value, _schema("research-dimension-report.schema.json"))
    except SchemaValidationError as exc:
        raise MultiDimensionalResearchError(f"DIMENSION_REPORT_SCHEMA_INVALID:{exc}") from exc
    forbidden = _find_forbidden_keys(value)
    if forbidden:
        raise MultiDimensionalResearchError(
            f"DIMENSION_REPORT_ACTION_FIELD_FORBIDDEN:{','.join(sorted(forbidden))}"
        )
    if value.get("schema_version") != DIMENSION_REPORT_VERSION:
        raise MultiDimensionalResearchError("DIMENSION_REPORT_VERSION_INVALID")
    if value.get("capability") not in RESEARCH_CAPABILITIES:
        raise MultiDimensionalResearchError("DIMENSION_REPORT_CAPABILITY_INVALID")
    expected = dict(expected_bindings)
    if value.get("bindings") != expected:
        raise MultiDimensionalResearchError("DIMENSION_REPORT_BINDING_INVALID")

    security_ids = _canonical_ids(value.get("security_ids"), "security_ids")
    if not set(security_ids) <= set(allowed_security_ids):
        raise MultiDimensionalResearchError("DIMENSION_REPORT_SECURITY_BINDING_INVALID")
    scope = value.get("scope")
    if scope == "PER_SECURITY" and len(security_ids) != 1:
        raise MultiDimensionalResearchError("DIMENSION_REPORT_SINGLE_SECURITY_REQUIRED")
    if scope in {"PER_SECURITY", "SECURITY_GROUP"} and not security_ids:
        raise MultiDimensionalResearchError("DIMENSION_REPORT_SECURITY_REQUIRED")

    status = value.get("status")
    if status not in REPORT_STATUSES:
        raise MultiDimensionalResearchError("DIMENSION_REPORT_STATUS_INVALID")
    evaluation = value.get("evaluation_status")
    if status == "SOURCE_LIMITED" and evaluation != "SOURCE_LIMITED":
        raise MultiDimensionalResearchError("DIMENSION_REPORT_SOURCE_LIMITED_STATE_INVALID")
    if status in {"FAILED", "TIMEOUT"} and evaluation == "PASS":
        raise MultiDimensionalResearchError("DIMENSION_REPORT_FAILED_EVALUATION_INVALID")

    execution = value.get("execution")
    if not isinstance(execution, Mapping):
        raise MultiDimensionalResearchError("DIMENSION_REPORT_EXECUTION_INVALID")
    capability = str(value["capability"])
    agent_name = execution.get("agent_name")
    if capability == "FUNDAMENTAL_EVENT" and agent_name != "runtime_company_analyst":
        raise MultiDimensionalResearchError("DIMENSION_REPORT_AGENT_CAPABILITY_MISMATCH")
    if capability in {
        "TECHNICAL_STRUCTURE", "INDUSTRY_COMPARISON", "MACRO_MARKET",
        "OWNERSHIP_DISCLOSURE", "OPTIONS_FLOW",
    } and agent_name != "runtime_market_catalyst":
        raise MultiDimensionalResearchError("DIMENSION_REPORT_AGENT_CAPABILITY_MISMATCH")
    if capability == "RESEARCH_REPORT" and agent_name not in {
        "runtime_company_analyst", "runtime_market_catalyst"
    }:
        raise MultiDimensionalResearchError("DIMENSION_REPORT_AGENT_CAPABILITY_MISMATCH")

    claims = value.get("claims")
    assumptions = value.get("assumptions")
    calculations = value.get("calculations")
    conditions = value.get("observation_conditions")
    gaps = value.get("data_gaps")
    documents = value.get("documents")
    relationships = value.get("research_relationships")
    if any(not isinstance(items, list) for items in (
        claims, assumptions, calculations, documents, relationships, conditions, gaps
    )):
        raise MultiDimensionalResearchError("DIMENSION_REPORT_COLLECTION_INVALID")
    collections = (
        (claims, "claim_id", "claims"),
        (assumptions, "assumption_id", "assumptions"),
        (calculations, "calculation_id", "calculations"),
        (documents, "document_id", "documents"),
        (relationships, "relationship_id", "research_relationships"),
        (conditions, "condition_id", "observation_conditions"),
        (gaps, "gap_id", "data_gaps"),
    )
    indexes: dict[str, set[str]] = {}
    for items, id_key, field in collections:
        if any(not isinstance(item, Mapping) for item in items):
            raise MultiDimensionalResearchError(f"DIMENSION_REPORT_ITEM_INVALID:{field}")
        indexes[field] = set(_canonical_ids([item.get(id_key) for item in items], field))

    claim_ids = indexes["claims"]
    assumption_ids = indexes["assumptions"]
    calculation_ids = indexes["calculations"]
    document_ids = indexes["documents"]
    if allowed_documents is not None:
        expected_documents = {
            str(item.get("document_id")): dict(item) for item in allowed_documents
        }
        if len(expected_documents) != len(allowed_documents):
            raise MultiDimensionalResearchError("DIMENSION_REPORT_ALLOWED_DOCUMENTS_INVALID")
        if set(document_ids) - set(expected_documents):
            raise MultiDimensionalResearchError("DIMENSION_REPORT_DOCUMENT_NOT_ALLOWED")
        for document in documents:
            if dict(document) != expected_documents[document["document_id"]]:
                raise MultiDimensionalResearchError("DIMENSION_REPORT_DOCUMENT_METADATA_DRIFT")
    external_claim_ids = set(known_research_claim_ids)
    artifact_refs = set(value.get("artifact_refs", []))
    extra_evidence_refs: set[str] = set()
    for claim in claims:
        evidence_refs = set(_canonical_ids(claim.get("evidence_refs"), "claim.evidence_refs"))
        research_refs = set(
            _canonical_ids(claim.get("research_claim_refs"), "claim.research_claim_refs")
        )
        claim_assumptions = set(
            _canonical_ids(claim.get("assumption_ids"), "claim.assumption_ids")
        )
        claim_calculations = set(
            _canonical_ids(claim.get("calculation_refs"), "claim.calculation_refs")
        )
        claim_documents = set(
            _canonical_ids(claim.get("document_refs"), "claim.document_refs")
        )
        if research_refs - (claim_ids | external_claim_ids):
            raise MultiDimensionalResearchError("DIMENSION_REPORT_RESEARCH_CLAIM_DANGLING")
        if (
            claim_assumptions - assumption_ids
            or claim_calculations - calculation_ids
            or claim_documents - document_ids
        ):
            raise MultiDimensionalResearchError("DIMENSION_REPORT_INTERNAL_REFERENCE_DANGLING")
        if (
            not evidence_refs and not research_refs and not claim_documents
            and not claim_assumptions and not claim_calculations
        ):
            raise MultiDimensionalResearchError("DIMENSION_REPORT_CLAIM_UNGROUNDED")
    for document in documents:
        for field in ("duplicate_of", "revision_of"):
            reference = document.get(field)
            if reference is not None and reference not in document_ids:
                raise MultiDimensionalResearchError(
                    f"DIMENSION_REPORT_DOCUMENT_REFERENCE_DANGLING:{field}"
                )
    for relationship in relationships:
        if relationship.get("document_id") not in document_ids:
            raise MultiDimensionalResearchError("DIMENSION_REPORT_RELATIONSHIP_DOCUMENT_DANGLING")
        target_refs = set(_canonical_ids(
            relationship.get("target_claim_refs"), "research_relationship.target_claim_refs"
        ))
        result_refs = set(_canonical_ids(
            relationship.get("resulting_claim_refs"), "research_relationship.resulting_claim_refs"
        ))
        if target_refs - (claim_ids | external_claim_ids):
            raise MultiDimensionalResearchError("DIMENSION_REPORT_RELATIONSHIP_TARGET_DANGLING")
        if result_refs - claim_ids:
            raise MultiDimensionalResearchError("DIMENSION_REPORT_RELATIONSHIP_RESULT_DANGLING")
        if relationship.get("effect") != "NO_NEW_INFORMATION" and not result_refs:
            raise MultiDimensionalResearchError("DIMENSION_REPORT_RELATIONSHIP_RESULT_REQUIRED")
    if capability != "RESEARCH_REPORT" and (documents or relationships):
        raise MultiDimensionalResearchError("DIMENSION_REPORT_DOCUMENTS_CAPABILITY_MISMATCH")
    if capability == "RESEARCH_REPORT" and status == "COMPLETE" and not any(
        item.get("verification_status") == "BODY_VERIFIED" for item in documents
    ):
        raise MultiDimensionalResearchError("DIMENSION_REPORT_VERIFIED_DOCUMENT_REQUIRED")
    for calculation in calculations:
        input_refs = set(
            _canonical_ids(
                calculation.get("input_evidence_refs"), "calculation.input_evidence_refs"
            )
        )
        extra_evidence_refs.update(input_refs)
        if calculation.get("artifact_ref") not in artifact_refs:
            raise MultiDimensionalResearchError("DIMENSION_REPORT_CALCULATION_ARTIFACT_DANGLING")
    for condition in conditions:
        if set(_canonical_ids(condition.get("claim_refs"), "condition.claim_refs")) - claim_ids:
            raise MultiDimensionalResearchError("DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING")

    try:
        refs = validate_evidence_closure(value, allowed_evidence_ids=allowed_evidence_ids)
    except ArtifactValidationError as exc:
        raise MultiDimensionalResearchError(str(exc)) from exc
    unknown_calculation_inputs = extra_evidence_refs - set(allowed_evidence_ids)
    if unknown_calculation_inputs:
        raise MultiDimensionalResearchError(
            "EVIDENCE_CLOSURE_FAILED:" + ",".join(sorted(unknown_calculation_inputs))
        )
    if value.get("report_hash") != canonical_hash(_without_hash(value, "report_hash")):
        raise MultiDimensionalResearchError("DIMENSION_REPORT_HASH_MISMATCH")
    return refs | extra_evidence_refs


def validate_holding_research_bundle(
    value: Mapping[str, Any],
    *,
    expected_bindings: Mapping[str, Any],
    expected_common_stock_ids: Sequence[str],
    dimension_reports: Sequence[Mapping[str, Any]] = (),
    equity_reports: Sequence[Mapping[str, Any]] = (),
) -> None:
    """验证研究包完整覆盖与报告身份；缺口可以存在，但必须显式。"""

    schema_version = value.get("schema_version")
    schema_name = (
        "holding-research-bundle-v1.1.schema.json"
        if schema_version == HOLDING_RESEARCH_BUNDLE_VERSION
        else "holding-research-bundle.schema.json"
    )
    try:
        validate_schema_instance(value, _schema(schema_name))
    except SchemaValidationError as exc:
        raise MultiDimensionalResearchError(f"HOLDING_RESEARCH_BUNDLE_SCHEMA_INVALID:{exc}") from exc
    if value.get("bindings") != dict(expected_bindings):
        raise MultiDimensionalResearchError("HOLDING_RESEARCH_BUNDLE_BINDING_INVALID")
    common_ids = _canonical_ids(value.get("common_stock_security_ids"), "common_stock_security_ids")
    if set(common_ids) != set(expected_common_stock_ids):
        raise MultiDimensionalResearchError("HOLDING_RESEARCH_BUNDLE_SECURITY_SET_INVALID")

    report_refs = value.get("report_refs", [])
    report_ids = _canonical_ids([item.get("report_id") for item in report_refs], "report_refs")
    refs_by_id = {item["report_id"]: item for item in report_refs}
    actual_reports = {str(item.get("report_id")): item for item in dimension_reports}
    actual_equity_reports = {str(item.get("report_id")): item for item in equity_reports}
    if len(actual_reports) != len(dimension_reports) or len(actual_equity_reports) != len(equity_reports):
        raise MultiDimensionalResearchError("HOLDING_RESEARCH_BUNDLE_REPORT_ID_DUPLICATE")
    if set(actual_reports) & set(actual_equity_reports):
        raise MultiDimensionalResearchError("HOLDING_RESEARCH_BUNDLE_REPORT_ID_DUPLICATE")
    if set(report_ids) != set(actual_reports) | set(actual_equity_reports):
        raise MultiDimensionalResearchError("HOLDING_RESEARCH_BUNDLE_REPORT_MISSING")
    for report_id, report in actual_reports.items():
        ref = refs_by_id[report_id]
        if (
            ref.get("report_type") != "RESEARCH_DIMENSION_REPORT"
            or ref.get("report_hash") != report.get("report_hash")
            or ref.get("capability") != report.get("capability")
            or set(ref.get("security_ids", [])) != set(report.get("security_ids", []))
        ):
            raise MultiDimensionalResearchError("HOLDING_RESEARCH_BUNDLE_REPORT_BINDING_INVALID")
    for report_id, report in actual_equity_reports.items():
        ref = refs_by_id[report_id]
        security_id = report.get("security", {}).get("security_id")
        if (
            ref.get("report_type") != "EQUITY_RESEARCH_REPORT"
            or ref.get("report_hash") != canonical_hash(report)
            or ref.get("capability") != "COMPANY_RESEARCH"
            or ref.get("security_ids") != [security_id]
        ):
            raise MultiDimensionalResearchError("HOLDING_RESEARCH_BUNDLE_EQUITY_REPORT_BINDING_INVALID")

    coverage = value.get("coverage", [])
    expected_pairs = {
        (security_id, capability)
        for security_id in common_ids
        for capability in BUNDLE_CAPABILITIES
    }
    actual_pairs = [(item.get("security_id"), item.get("capability")) for item in coverage]
    if len(actual_pairs) != len(set(actual_pairs)) or set(actual_pairs) != expected_pairs:
        raise MultiDimensionalResearchError("HOLDING_RESEARCH_BUNDLE_COVERAGE_INVALID")
    for item in coverage:
        report_id = item.get("report_id")
        status = item.get("status")
        gap_reason = item.get("gap_reason")
        if report_id is not None:
            report_ref = refs_by_id.get(report_id)
            if report_ref is None:
                raise MultiDimensionalResearchError("HOLDING_RESEARCH_BUNDLE_COVERAGE_REPORT_DANGLING")
            if (
                item["security_id"] not in report_ref.get("security_ids", [])
                or item["capability"] != report_ref.get("capability")
            ):
                raise MultiDimensionalResearchError("HOLDING_RESEARCH_BUNDLE_COVERAGE_REPORT_MISMATCH")
        if status == "COMPLETE" and report_id is None:
            raise MultiDimensionalResearchError("HOLDING_RESEARCH_BUNDLE_COMPLETE_REPORT_REQUIRED")
        if report_id is None and not gap_reason:
            raise MultiDimensionalResearchError("HOLDING_RESEARCH_BUNDLE_GAP_REASON_REQUIRED")

    known_claim_ids = {
        claim.get("claim_id")
        for report in (*dimension_reports, *equity_reports)
        for claim in report.get("claims", [])
        if isinstance(claim, Mapping)
    }
    known_report_ids = set(report_ids)
    for question in value.get("unresolved_cross_dimension_questions", []):
        if set(question.get("security_ids", [])) - set(common_ids):
            raise MultiDimensionalResearchError("HOLDING_RESEARCH_BUNDLE_QUESTION_SECURITY_DANGLING")
        if set(question.get("capabilities", [])) - set(BUNDLE_CAPABILITIES):
            raise MultiDimensionalResearchError("HOLDING_RESEARCH_BUNDLE_QUESTION_CAPABILITY_DANGLING")
        if set(question.get("claim_refs", [])) - known_claim_ids:
            raise MultiDimensionalResearchError("HOLDING_RESEARCH_BUNDLE_QUESTION_CLAIM_DANGLING")
        if set(question.get("report_refs", [])) - known_report_ids:
            raise MultiDimensionalResearchError("HOLDING_RESEARCH_BUNDLE_QUESTION_REPORT_DANGLING")
    if schema_version == HOLDING_RESEARCH_BUNDLE_VERSION:
        questions = value.get("unresolved_cross_dimension_questions", [])
        no_unresolved_reason = value.get("no_unresolved_reason")
        if questions and no_unresolved_reason is not None:
            raise MultiDimensionalResearchError(
                "HOLDING_RESEARCH_BUNDLE_UNRESOLVED_REASON_CONFLICT"
            )
        if not questions and not isinstance(no_unresolved_reason, str):
            raise MultiDimensionalResearchError(
                "HOLDING_RESEARCH_BUNDLE_UNRESOLVED_REASON_REQUIRED"
            )
        provenance = value.get("package_provenance", {})
        if provenance.get("base_run_id") != value.get("run_id"):
            raise MultiDimensionalResearchError(
                "HOLDING_RESEARCH_BUNDLE_BASE_RUN_MISMATCH"
            )
        for item in provenance.get("company_research_imports", []):
            report_id = item.get("report_id")
            ref = refs_by_id.get(report_id)
            if ref is None or ref.get("capability") != "COMPANY_RESEARCH":
                raise MultiDimensionalResearchError(
                    "HOLDING_RESEARCH_BUNDLE_COMPANY_IMPORT_DANGLING"
                )
        for item in provenance.get("incorporated_supplements", []):
            if item.get("report_id") not in refs_by_id:
                raise MultiDimensionalResearchError(
                    "HOLDING_RESEARCH_BUNDLE_SUPPLEMENT_DANGLING"
                )
        company_coverage = [
            item for item in coverage if item.get("capability") == "COMPANY_RESEARCH"
        ]
        company_ready = len(company_coverage) == len(common_ids) and all(
            isinstance(item.get("report_id"), str)
            and item.get("status") not in {"FAILED", "TIMEOUT", "NOT_RESEARCHED"}
            for item in company_coverage
        )
        if value.get("consumability") == "DOWNSTREAM_READY" and not company_ready:
            raise MultiDimensionalResearchError(
                "HOLDING_RESEARCH_BUNDLE_COMPANY_RESEARCH_NOT_READY"
            )
    if value.get("bundle_hash") != canonical_hash(_without_hash(value, "bundle_hash")):
        raise MultiDimensionalResearchError("HOLDING_RESEARCH_BUNDLE_HASH_MISMATCH")


def derive_unresolved_research_questions(
    *,
    dimension_reports: Sequence[Mapping[str, Any]],
    equity_reports: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """从报告已经写明的观察/失效条件归集待反证问题，不创造新判断。"""

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    report_items: list[tuple[Mapping[str, Any], str, Sequence[Mapping[str, Any]]]] = []
    report_items.extend(
        (report, str(report.get("capability")), report.get("observation_conditions", []))
        for report in dimension_reports
    )
    report_items.extend(
        (report, "COMPANY_RESEARCH", report.get("invalidation_conditions", []))
        for report in equity_reports
    )
    for report, capability, conditions in report_items:
        report_id = report.get("report_id")
        security_ids = (
            list(report.get("security_ids", []))
            if capability != "COMPANY_RESEARCH"
            else [report.get("security", {}).get("security_id")]
        )
        claim_ids = {
            item.get("claim_id") for item in report.get("claims", [])
            if isinstance(item, Mapping)
        }
        for condition in conditions:
            if not isinstance(condition, Mapping):
                continue
            description = condition.get("description")
            claim_refs = condition.get("claim_refs", [])
            if (
                not isinstance(report_id, str)
                or not isinstance(description, str)
                or not description.strip()
                or not isinstance(claim_refs, list)
                or not claim_refs
                or set(claim_refs) - claim_ids
                or any(not isinstance(item, str) for item in security_ids)
            ):
                continue
            identity = canonical_hash({
                "report_id": report_id,
                "condition_id": condition.get("condition_id"),
                "description": description,
                "claim_refs": claim_refs,
            })
            if identity in seen:
                continue
            seen.add(identity)
            result.append({
                "question_id": f"unresolved:{identity[:24]}",
                "security_ids": sorted(set(security_ids)),
                "capabilities": [capability],
                "question": description,
                "report_refs": [report_id],
                "claim_refs": sorted(set(claim_refs)),
            })
    return sorted(result, key=lambda item: item["question_id"])


def finalize_research_dimension_report(value: Mapping[str, Any]) -> dict[str, Any]:
    """为已完成内容添加确定性 report_hash，不修复模型内容。"""

    report = copy.deepcopy(dict(value))
    report["report_hash"] = canonical_hash(_without_hash(report, "report_hash"))
    return report


def finalize_holding_research_bundle(value: Mapping[str, Any]) -> dict[str, Any]:
    """为已组装研究包添加确定性 bundle_hash。"""

    bundle = copy.deepcopy(dict(value))
    bundle["bundle_hash"] = canonical_hash(_without_hash(bundle, "bundle_hash"))
    return bundle


DIMENSION_DRAFT_KEYS = {
    "run_id", "invocation_id", "agent", "status", "sufficiency",
    "evaluation_status", "summary", "claims", "assumptions", "calculations",
    "documents", "research_relationships",
    "limitations", "observation_conditions", "data_gaps", "artifact_refs",
}


def envelope_research_dimension_draft(
    draft: Mapping[str, Any], *, task: Mapping[str, Any], invocation: Mapping[str, Any],
    expected_bindings: Mapping[str, Any], allowed_security_ids: Sequence[str],
    allowed_evidence_ids: Sequence[str], known_research_claim_ids: Sequence[str] = (),
    allowed_documents: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """添加冻结的身份与执行元数据；不修复模型主张、状态或引用。"""

    if not isinstance(draft, Mapping) or set(draft) != DIMENSION_DRAFT_KEYS:
        raise MultiDimensionalResearchError("DIMENSION_DRAFT_KEYS_INVALID")
    if (
        draft.get("run_id") != task.get("run_id")
        or draft.get("invocation_id") != task.get("invocation_id")
        or draft.get("agent") != task.get("agent")
        or invocation.get("run_id") != task.get("run_id")
        or invocation.get("invocation_id") != task.get("invocation_id")
    ):
        raise MultiDimensionalResearchError("DIMENSION_DRAFT_BINDING_INVALID")
    skill = invocation.get("skill")
    agent = invocation.get("agent_binding")
    if not isinstance(skill, Mapping) or not isinstance(agent, Mapping):
        raise MultiDimensionalResearchError("DIMENSION_DRAFT_EXECUTION_BINDING_INVALID")
    preparation = task.get("material_preparation")
    if (
        task.get("capability") == "RESEARCH_REPORT"
        and isinstance(preparation, Mapping)
        and preparation.get("status") == "BLOCKED_CONFIGURATION"
        and (draft.get("status") != "FAILED" or draft.get("evaluation_status") != "FAIL")
    ):
        raise MultiDimensionalResearchError("DIMENSION_DRAFT_CONFIGURATION_BLOCK_STATE_INVALID")
    raw_hash = canonical_hash(draft)
    report = {
        "schema_version": DIMENSION_REPORT_VERSION,
        "report_id": f"dimension-report:{task['task_id']}",
        "run_id": task["run_id"],
        "invocation_id": task["invocation_id"],
        "capability": task["capability"],
        "scope": task["scope"],
        "security_ids": copy.deepcopy(task["security_ids"]),
        "status": draft["status"],
        "sufficiency": draft["sufficiency"],
        "evaluation_status": draft["evaluation_status"],
        "bindings": copy.deepcopy(dict(expected_bindings)),
        "time_context": copy.deepcopy(task["time_context"]),
        "execution": {
            "agent_name": agent["name"],
            "agent_version": agent["version"],
            "skill_name": skill["name"],
            "skill_version": skill["version"],
            "skill_hash": skill["content_hash"],
            "model": invocation["model"],
            "prompt_hash": invocation["prompt_hash"],
            "input_refs": copy.deepcopy(invocation["input_refs"]),
            "raw_output_hash": raw_hash,
        },
        "summary": draft["summary"],
        "claims": copy.deepcopy(draft["claims"]),
        "assumptions": copy.deepcopy(draft["assumptions"]),
        "calculations": copy.deepcopy(draft["calculations"]),
        "documents": copy.deepcopy(draft["documents"]),
        "research_relationships": copy.deepcopy(draft["research_relationships"]),
        "limitations": copy.deepcopy(draft["limitations"]),
        "observation_conditions": copy.deepcopy(draft["observation_conditions"]),
        "data_gaps": copy.deepcopy(draft["data_gaps"]),
        "artifact_refs": copy.deepcopy(draft["artifact_refs"]),
    }
    report = finalize_research_dimension_report(report)
    validate_research_dimension_report(
        report,
        expected_bindings=expected_bindings,
        allowed_security_ids=allowed_security_ids,
        allowed_evidence_ids=allowed_evidence_ids,
        known_research_claim_ids=known_research_claim_ids,
        allowed_documents=allowed_documents,
    )
    return report
