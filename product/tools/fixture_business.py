"""fixture原研究/决策语义与原硬Risk；不装配伪造的旧执行身份。"""
from __future__ import annotations
import copy
import json
from pathlib import Path
from typing import Mapping

from product.runtime.hashing import canonical_hash
from product.runtime.validation import validate_evidence_closure
from product.runtime.decision_contract import load_decision_contract, validate_decision_action
from product.tools.calculation_choices import SELECTION_SCHEMA
from product.tools.fixture_risk import build_risk_snapshot, check_cio_draft

ROOT = Path(__file__).resolve().parents[1]
COMPANY = "FIXTURE_COMPANY_RESEARCH"
CIO = "FIXTURE_COUNCIL_DECISION"


def semantic_schema(capability):
    name = "agent-research-report.schema.json" if capability == COMPANY else "cio-decision-draft.schema.json"
    schema = json.loads((ROOT/"schemas/runtime"/name).read_text())
    technical = {"schema_version", "run_id", "invocation_id", "agent", "skill_execution", "artifact_refs", "consumed_reports"}
    if capability == CIO:
        technical |= {"security_id", "current_weight"}
    schema["$id"] = "native-fixture-semantic/"+capability.lower()+"/1.0.0"
    schema["required"] = [k for k in schema["required"] if k not in technical]
    for key in technical:
        schema["properties"].pop(key, None)
    if capability == COMPANY:
        schema["properties"]["calculation_selections"] = copy.deepcopy(SELECTION_SCHEMA)
        schema["required"].append("calculation_selections")
    else:
        schema["properties"]["report_selections"] = {"type": "array", "minItems": 2, "maxItems": 2,
            "uniqueItems": True, "items": {"type": "string", "minLength": 1}}
        schema["required"].append("report_selections")
    return schema


def validate_company(value, *, allowed_evidence_ids):
    assumptions = {a["assumption_id"] for a in value["assumptions"]}
    for claim in value["claims"]:
        if not claim["evidence_refs"] and not claim["assumption_ids"] and not claim.get("calculation_refs"):
            raise ValueError("UNGROUNDED_CLAIM")
        if set(claim["assumption_ids"]) - assumptions:
            raise ValueError("UNKNOWN_ASSUMPTION")
    return validate_evidence_closure(value, allowed_evidence_ids=allowed_evidence_ids)


def fixture_risk(tools, draft, *, attempt):
    from product.tools.report_reading import read_report_ids
    task, _gate = tools._authorize()
    reports = task["dependency_reports"]
    allowed = {r["report_id"]: r for r in reports}
    if (set(draft["report_selections"]) != set(allowed)
            or not set(allowed) <= read_report_ids(tools)):
        raise ValueError("NATIVE_CIO_REPORT_CONSUMPTION_INVALID")
    original = json.loads((tools.root/"input.json").read_text())["fixture"]
    snapshot = build_risk_snapshot(original, run_id=task["task_id"])
    selected = next(p for p in snapshot.positions if p.security_id == task["security"]["security_id"])
    value = {**copy.deepcopy(draft), "security_id": selected.security_id, "current_weight": float(selected.weight)}
    validate_cio_content(value, allowed_evidence_ids=task["allowed_evidence_ids"])
    risk = check_cio_draft(original, value, run_id=task["task_id"])
    # 原Risk对象保持原样；原两稿上限耗尽时只按已有硬否决规则收尾。
    needs_revision = risk["check"]["status"] == "REVISE_REQUIRED" and attempt == 1
    final_action = None if needs_revision else value["action"] if risk["check"]["status"] == "APPROVED" else "NO_TRADE"
    decision = {"final_action": final_action, "advisory_only": True, "risk_result_hash": canonical_hash(risk),
                "terminal_state": "ONE_CIO_REVISION_REQUIRED" if needs_revision else "SAFE_NO_TRADE" if final_action == "NO_TRADE" else "COMPLETED",
                "reason_code": "RISK_VETO" if final_action == "NO_TRADE" and risk["check"]["status"] != "APPROVED" else None}
    return value, risk, decision, ["/action", "/target_weight_range", "/maximum_notional", "/no_trade_reason", "/no_trade_explanation", "/reevaluation_conditions"] if needs_revision else []


def validate_cio_content(value, *, allowed_evidence_ids):
    from product.runtime.validation import CIO_CONFLICT_REQUIRED, _require_exact_keys, ArtifactValidationError
    from product.runtime.decision_contract import DecisionContractError
    if value.get("status") not in {"COMPLETE", "INSUFFICIENT_EVIDENCE", "LOW_CONFIDENCE"}:
        raise ArtifactValidationError("ILLEGAL_CIO_STATUS")
    if value.get("advisory_only") is not True:
        raise ArtifactValidationError("ADVISORY_ONLY_REQUIRED")
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
    try:
        validate_decision_action(value, load_decision_contract(ROOT))
    except DecisionContractError as exc:
        raise ArtifactValidationError(str(exc)) from exc
    return validate_evidence_closure(value, allowed_evidence_ids=allowed_evidence_ids)
