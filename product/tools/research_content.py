"""从现有报告校验抽出的研究内容与精确引用规则。"""
from __future__ import annotations
import re
from typing import Any, Mapping
from product.runtime.validation import ArtifactValidationError, validate_evidence_closure

class ResearchContentError(ValueError):
    pass

CommonStockResearchError = ResearchContentError
MultiDimensionalResearchError = ResearchContentError
CANONICAL_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")
SECTION_NAMES = (
    "company_and_core_questions", "business_competition_financials",
    "thesis_and_valuation", "catalysts_and_counterevidence",
    "invalidation_and_monitoring", "gaps_and_confidence",
)

def _equity_ids(values: Any, field: str, *, unique: bool = True) -> list[str]:
    if not isinstance(values, list):
        raise CommonStockResearchError(f"RESEARCH_ID_ARRAY_INVALID:{field}")
    if any(not isinstance(item, str) or not CANONICAL_ID.fullmatch(item) for item in values):
        raise CommonStockResearchError(f"RESEARCH_CANONICAL_ID_INVALID:{field}")
    if unique and len(values) != len(set(values)):
        raise CommonStockResearchError(f"RESEARCH_ID_DUPLICATE:{field}")
    return values

def _dimension_ids(values: Any, field: str) -> list[str]:
    if not isinstance(values, list):
        raise MultiDimensionalResearchError(f"DIMENSION_ID_ARRAY_INVALID:{field}")
    if any(not isinstance(item, str) or not CANONICAL_ID.fullmatch(item) for item in values):
        raise MultiDimensionalResearchError(f"DIMENSION_ID_INVALID:{field}")
    if len(values) != len(set(values)):
        raise MultiDimensionalResearchError(f"DIMENSION_ID_DUPLICATE:{field}")
    return values

def validate_company_content(value, *, allowed_evidence_ids, calculation_artifact_ids=()):
    """原Company内容及引用规则，不填造宿主/Skill执行证明。"""
    allowed_gap_reasons = {"NOT_FETCHED", "NOT_YET_DISCLOSED", "SOURCE_UNSUPPORTED", "UNKNOWN"}
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
        ids = _equity_ids([item.get(id_key) for item in items], name)
        indexes[name] = set(ids)
    claim_ids = indexes["claims"]
    assumption_ids = indexes["assumptions"]
    condition_ids = indexes["invalidation_conditions"]
    gap_ids = indexes["data_gaps"]
    known_calculations = set(calculation_artifact_ids)
    report_artifacts = set(value.get("artifact_refs", []))
    for claim_index, claim in enumerate(claims):
        evidence_refs = _equity_ids(claim.get("evidence_refs"), "claim.evidence_refs")
        claim_assumptions = set(_equity_ids(claim.get("assumption_ids"), "claim.assumption_ids"))
        calculations = set(_equity_ids(claim.get("calculation_refs"), "claim.calculation_refs"))
        counter_claims = set(_equity_ids(claim.get("counter_claim_refs"), "claim.counter_claim_refs"))
        invalidations = set(_equity_ids(claim.get("invalidation_condition_ids"), "claim.invalidation_condition_ids"))
        if claim_assumptions - assumption_ids or counter_claims - claim_ids or invalidations - condition_ids:
            raise CommonStockResearchError("EQUITY_RESEARCH_INTERNAL_REFERENCE_DANGLING")
        if calculations - known_calculations or calculations - report_artifacts:
            raise CommonStockResearchError(
                f"EQUITY_RESEARCH_CALCULATION_REFERENCE_DANGLING:claims[{claim_index}].calculation_refs:{claim['claim_id']}"
            )
        if not evidence_refs and not claim_assumptions and not calculations:
            raise CommonStockResearchError(
                f"EQUITY_RESEARCH_CLAIM_UNGROUNDED:claims[{claim_index}]:{claim['claim_id']}"
            )
    summary = value.get("research_summary")
    sections = value.get("sections")
    if not isinstance(summary, Mapping) or not isinstance(sections, Mapping) or set(sections) != set(SECTION_NAMES):
        raise CommonStockResearchError("EQUITY_RESEARCH_SECTIONS_INVALID")
    if set(_equity_ids(summary.get("claim_refs"), "summary.claim_refs")) - claim_ids:
        raise CommonStockResearchError("EQUITY_RESEARCH_SUMMARY_REFERENCE_DANGLING")
    if set(_equity_ids(summary.get("primary_invalidation_condition_ids"), "summary.invalidation")) - condition_ids:
        raise CommonStockResearchError("EQUITY_RESEARCH_SUMMARY_REFERENCE_DANGLING")
    for name in SECTION_NAMES:
        section = sections[name]
        if not isinstance(section, Mapping):
            raise CommonStockResearchError(f"EQUITY_RESEARCH_SECTION_INVALID:{name}")
        if set(_equity_ids(section.get("claim_refs"), f"sections.{name}.claim_refs")) - claim_ids:
            raise CommonStockResearchError("EQUITY_RESEARCH_SECTION_REFERENCE_DANGLING")
        if set(_equity_ids(section.get("data_gap_ids"), f"sections.{name}.data_gap_ids")) - gap_ids:
            raise CommonStockResearchError("EQUITY_RESEARCH_SECTION_REFERENCE_DANGLING")
    for condition in conditions:
        if set(_equity_ids(condition.get("claim_refs"), "condition.claim_refs")) - claim_ids:
            raise CommonStockResearchError("EQUITY_RESEARCH_CONDITION_REFERENCE_DANGLING")
    for trigger in triggers:
        if set(_equity_ids(trigger.get("claim_refs"), "trigger.claim_refs")) - claim_ids:
            raise CommonStockResearchError("EQUITY_RESEARCH_TRIGGER_REFERENCE_DANGLING")
    for indicator in indicators:
        for field in ("baseline", "unit", "comparison_period", "reevaluation_rule"):
            if field in indicator and indicator[field] is not None and (
                not isinstance(indicator[field], str) or not indicator[field].strip()
            ):
                raise CommonStockResearchError(
                    f"EQUITY_RESEARCH_MONITORING_CONTEXT_INVALID:{field}"
                )
    for gap in gaps:
        if "reason_code" in gap and gap["reason_code"] not in allowed_gap_reasons:
            raise CommonStockResearchError("EQUITY_RESEARCH_GAP_REASON_INVALID")
    try:
        return validate_evidence_closure(value, allowed_evidence_ids=allowed_evidence_ids)
    except ArtifactValidationError as exc:
        raise CommonStockResearchError(str(exc)) from exc


def validate_dimension_content(value, *, capability, allowed_evidence_ids,
                               allowed_calculation_evidence_ids=(), known_research_claim_ids=(),
                               allowed_documents=None):
    """原维度内容/关系/计算/来源闭合规则，技术信封独立验证。"""
    status = value.get("status")
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
        indexes[field] = set(_dimension_ids([item.get(id_key) for item in items], field))

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
        if not isinstance(claim.get("question"), str) or not claim["question"].strip():
            raise MultiDimensionalResearchError("DIMENSION_REPORT_CLAIM_QUESTION_INVALID")
        if not isinstance(claim.get("statement"), str) or not claim["statement"].strip():
            raise MultiDimensionalResearchError("DIMENSION_REPORT_CLAIM_STATEMENT_INVALID")
        if claim.get("kind") not in {"FACT", "INTERPRETATION", "COMPARISON"}:
            raise MultiDimensionalResearchError("DIMENSION_REPORT_CLAIM_KIND_INVALID")
        evidence_refs = set(_dimension_ids(claim.get("evidence_refs"), "claim.evidence_refs"))
        research_refs = set(
            _dimension_ids(claim.get("research_claim_refs"), "claim.research_claim_refs")
        )
        claim_assumptions = set(
            _dimension_ids(claim.get("assumption_ids"), "claim.assumption_ids")
        )
        claim_calculations = set(
            _dimension_ids(claim.get("calculation_refs"), "claim.calculation_refs")
        )
        claim_documents = set(
            _dimension_ids(claim.get("document_refs"), "claim.document_refs")
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
        target_refs = set(_dimension_ids(
            relationship.get("target_claim_refs"), "research_relationship.target_claim_refs"
        ))
        result_refs = set(_dimension_ids(
            relationship.get("resulting_claim_refs"), "research_relationship.resulting_claim_refs"
        ))
        if target_refs - (claim_ids | external_claim_ids):
            raise MultiDimensionalResearchError("DIMENSION_REPORT_RELATIONSHIP_TARGET_DANGLING")
        if result_refs - claim_ids:
            raise MultiDimensionalResearchError("DIMENSION_REPORT_RELATIONSHIP_RESULT_DANGLING")
        if relationship.get("effect") != "NO_NEW_INFORMATION" and not result_refs:
            raise MultiDimensionalResearchError("DIMENSION_REPORT_RELATIONSHIP_RESULT_REQUIRED")
    document_capabilities = {"RESEARCH_REPORT", "MACRO_CONTEXT", "MARKET_STATE"}
    if capability not in document_capabilities and (documents or relationships):
        raise MultiDimensionalResearchError("DIMENSION_REPORT_DOCUMENTS_CAPABILITY_MISMATCH")
    if (
        status == "COMPLETE"
        and (capability == "RESEARCH_REPORT" or documents)
        and capability in document_capabilities
        and not any(item.get("verification_status") == "BODY_VERIFIED" for item in documents)
    ):
        raise MultiDimensionalResearchError("DIMENSION_REPORT_VERIFIED_DOCUMENT_REQUIRED")
    for calculation in calculations:
        input_refs = set(
            _dimension_ids(
                calculation.get("input_evidence_refs"), "calculation.input_evidence_refs"
            )
        )
        extra_evidence_refs.update(input_refs)
        if calculation.get("artifact_ref") not in artifact_refs:
            raise MultiDimensionalResearchError("DIMENSION_REPORT_CALCULATION_ARTIFACT_DANGLING")
    for condition in conditions:
        if set(_dimension_ids(condition.get("claim_refs"), "condition.claim_refs")) - claim_ids:
            raise MultiDimensionalResearchError("DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING")
    for gap in gaps:
        for field in ("reason_code", "description", "impact"):
            if not isinstance(gap.get(field), str) or not gap[field].strip():
                raise MultiDimensionalResearchError(
                    f"DIMENSION_REPORT_GAP_FIELD_INVALID:{field}"
                )

    try:
        refs = validate_evidence_closure(value, allowed_evidence_ids=allowed_evidence_ids)
    except ArtifactValidationError as exc:
        raise MultiDimensionalResearchError(str(exc)) from exc
    unknown_calculation_inputs = extra_evidence_refs - (
        set(allowed_evidence_ids) | set(allowed_calculation_evidence_ids)
    )
    if unknown_calculation_inputs:
        raise MultiDimensionalResearchError(
            "EVIDENCE_CLOSURE_FAILED:" + ",".join(sorted(unknown_calculation_inputs))
        )
    return refs | extra_evidence_refs


def validate_skeptic_content(value, *, allowed_evidence_ids, version="counter-thesis-report/2.1.0"):
    """原独立挑战与假设闭合规则，不补写投资语义。"""
    assumption_ids: set[str] = set()
    if version.endswith("2.1.0"):
        for assumption in value["assumptions"]:
            if (not isinstance(assumption, Mapping)
                    or set(assumption) != {"assumption_id", "statement"}
                    or not isinstance(assumption["assumption_id"], str)
                    or not assumption["assumption_id"].strip()
                    or not isinstance(assumption["statement"], str)
                    or not assumption["statement"].strip()):
                raise ArtifactValidationError("INVALID_ASSUMPTION")
            if assumption["assumption_id"] in assumption_ids:
                raise ArtifactValidationError("DUPLICATE_ASSUMPTION")
            assumption_ids.add(assumption["assumption_id"])
    for challenge in value["challenges"]:
        if not isinstance(challenge, Mapping):
            raise ArtifactValidationError("INVALID_CHALLENGE")
        if not challenge.get("evidence_refs") and not challenge.get("assumption_ids"):
            raise ArtifactValidationError("UNGROUNDED_CHALLENGE")
        if version.endswith("2.1.0"):
            references = challenge.get("assumption_ids", [])
            if not isinstance(references, list) or any(
                not isinstance(item, str) for item in references
            ) or set(references) - assumption_ids:
                raise ArtifactValidationError("UNKNOWN_ASSUMPTION")
    return validate_evidence_closure(value, allowed_evidence_ids=allowed_evidence_ids)
