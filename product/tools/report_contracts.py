"""从既有业务Schema派生原生语义草稿；不创建宿主执行协议。"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.tools.material_contracts import MATERIAL_ROLES, material_schema
from product.tools.research_scope import RESEARCH_CAPABILITIES
from product.tools.calculation_choices import SELECTION_SCHEMA
from product.runtime.schema_validation import validate_schema_definition, validate_schema_instance
from product.runtime.validation import collect_evidence_refs, validate_evidence_closure
from product.tools.research_content import (
    validate_company_content, validate_dimension_content, validate_skeptic_content,
)

SCHEMA_ROOT = Path(__file__).resolve().parents[1] / "schemas/runtime"
COMPANY_TECHNICAL = {
    "schema_version", "run_id", "invocation_id", "report_id", "agent", "bindings",
    "security", "research_scope", "skill_execution", "artifact_refs",
}
DIMENSION_TECHNICAL = {
    "schema_version", "report_id", "run_id", "invocation_id", "capability", "scope",
    "security_ids", "evaluation_status", "bindings", "time_context", "execution",
    "artifact_refs", "report_hash",
}
SKEPTIC_TECHNICAL = {
    "schema_version", "run_id", "invocation_id", "agent", "mode", "skill_execution", "artifact_refs",
}
CIO_TECHNICAL = {
    "schema_version", "run_id", "invocation_id", "source_run_id", "source_package_hash",
    "target_security_id", "requested_level", "actual_level", "decision_cutoff", "generated_at",
    "advisory_only", "complete_portfolio_decision", "risk_status", "consumed_reports", "account_fit",
}
ACTION_FIELDS = {
    "action", "trade_action", "target_weight", "target_weight_range", "maximum_notional",
    "recommended_quantity", "order", "order_id", "order_quantity",
}


def semantic_schema(capability: str) -> dict[str, Any]:
    if capability in {"FIXTURE_COMPANY_RESEARCH", "FIXTURE_COUNCIL_DECISION"}:
        from product.tools.fixture_business import semantic_schema as fixture_schema
        schema = fixture_schema(capability)
        validate_schema_definition(schema)
        return schema
    if capability in MATERIAL_ROLES:
        return material_schema(capability)
    if capability == "COMPANY_RESEARCH":
        name, technical = "equity-research-report.schema.json", COMPANY_TECHNICAL
    elif capability in RESEARCH_CAPABILITIES:
        name, technical = "research-dimension-report-v2.schema.json", DIMENSION_TECHNICAL
    elif capability == "INDEPENDENT_FIRST_PASS":
        name, technical = "counter-thesis-report-v2.1.schema.json", SKEPTIC_TECHNICAL
    elif capability == "RESEARCH_SYNTHESIS":
        name, technical = "predecision-cio-synthesis-v2.schema.json", CIO_TECHNICAL
    else:
        raise ValueError("NATIVE_RESEARCH_REPORT_CAPABILITY_UNSUPPORTED")
    schema = json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))
    schema["$id"] = f"native-research-semantic/{capability.lower()}/1.0.0"
    schema["required"] = [key for key in schema["required"] if key not in technical]
    for key in technical:
        schema["properties"].pop(key, None)
    if capability == "COMPANY_RESEARCH" or capability in RESEARCH_CAPABILITIES:
        claim = schema["$defs"]["claim"]
        claim["properties"].pop("calculation_refs", None)
        claim["required"] = [key for key in claim["required"] if key != "calculation_refs"]
        schema["properties"]["calculation_selections"] = copy.deepcopy(SELECTION_SCHEMA)
        schema["required"].append("calculation_selections")
    if capability in RESEARCH_CAPABILITIES:
        # Authors select successful objects; they do not transcribe their lineage.
        for key in ("documents", "calculations"):
            schema["properties"].pop(key)
            schema["required"].remove(key)
        schema["properties"]["document_selections"] = {
            "type": "array", "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        }
        schema["required"].append("document_selections")
    if capability == "INDEPENDENT_FIRST_PASS":
        schema["properties"]["challenges"]["items"]["anyOf"] = [
            {"properties": {"evidence_refs": {"minItems": 1}}},
            {"properties": {"assumption_ids": {"minItems": 1}}},
        ]
    if capability == "RESEARCH_SYNTHESIS":
        schema["properties"]["report_selections"] = {
            "type": "array", "minItems": 1, "uniqueItems": True,
            "items": {"type": "string", "minLength": 1},
        }
        schema["required"].append("report_selections")
    validate_schema_definition(schema)
    return schema


def reject_actions(value: Any) -> None:
    if isinstance(value, Mapping):
        if ACTION_FIELDS & value.keys():
            raise ValueError("NATIVE_RESEARCH_ACTION_FORBIDDEN")
        for child in value.values():
            reject_actions(child)
    elif isinstance(value, list):
        for child in value:
            reject_actions(child)


def validate_semantic_draft(
    draft: Mapping[str, Any], *, capability: str, allowed_evidence_ids: Sequence[str],
    queried_evidence_ids: Sequence[str], calculation_ids: Sequence[str] = (),
    assembled: Mapping[str, Any] | None = None,
    allowed_documents: Sequence[Mapping[str, Any]] = (), known_claim_ids: Sequence[str] = (),
    calculation_evidence_ids: Sequence[str] = (),
) -> set[str]:
    if capability != "FIXTURE_COUNCIL_DECISION":
        reject_actions(draft)
    validate_schema_instance(draft, semantic_schema(capability))
    value = copy.deepcopy(dict(assembled if assembled is not None else draft))
    if capability in MATERIAL_ROLES:
        return set()
    if capability == "FIXTURE_COMPANY_RESEARCH":
        from product.tools.fixture_business import validate_company
        refs = validate_company(value, allowed_evidence_ids=allowed_evidence_ids)
    elif capability == "FIXTURE_COUNCIL_DECISION":
        refs = validate_evidence_closure(value, allowed_evidence_ids=allowed_evidence_ids)
    elif capability == "COMPANY_RESEARCH":
        value["artifact_refs"] = list(calculation_ids)
        refs = validate_company_content(value, allowed_evidence_ids=allowed_evidence_ids,
                                        calculation_artifact_ids=calculation_ids)
    elif capability in RESEARCH_CAPABILITIES:
        refs = validate_dimension_content(value, capability=capability,
            allowed_evidence_ids=allowed_evidence_ids, known_research_claim_ids=known_claim_ids,
            allowed_calculation_evidence_ids=calculation_evidence_ids,
            allowed_documents=allowed_documents)
    elif capability == "INDEPENDENT_FIRST_PASS":
        refs = validate_skeptic_content(value, allowed_evidence_ids=allowed_evidence_ids)
    else:
        refs = validate_evidence_closure(value, allowed_evidence_ids=allowed_evidence_ids)
    # Calculation lineage comes from successful receipts, not fabricated query events.
    if not collect_evidence_refs(draft) <= set(queried_evidence_ids):
        raise ValueError("NATIVE_RESEARCH_EVIDENCE_NOT_QUERIED")
    return refs
