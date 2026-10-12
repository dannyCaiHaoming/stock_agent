"""完整业务范围与报告覆盖；仅数据规划/引用归集，不派发或等待Agent。"""
from __future__ import annotations
import copy
from typing import Mapping, Sequence

from product.runtime.hashing import canonical_hash
from product.tools.research import validate_gate
from product.tools.research_input import research_subjects, research_input_binding, validate_research_input
from product.tools.research_scope import RESEARCH_CAPABILITIES
from product.tools.report_reading import validate_report

STAGE_CAPABILITIES = {
    "COMMON_STOCK_RESEARCH": ("COMPANY_RESEARCH",),
    "MULTI_DIMENSIONAL_HOLDING_RESEARCH": ("COMPANY_RESEARCH", *RESEARCH_CAPABILITIES),
    "INDEPENDENT_COUNTER_THESIS_RESEARCH": ("COMPANY_RESEARCH", *RESEARCH_CAPABILITIES, "INDEPENDENT_FIRST_PASS"),
    "PREDECISION_CIO_SYNTHESIS": ("COMPANY_RESEARCH", *RESEARCH_CAPABILITIES, "INDEPENDENT_FIRST_PASS", "RESEARCH_SYNTHESIS"),
}


def build_stage_scope(research_input: Mapping, gate: Mapping, *, stage: str) -> dict:
    validate_research_input(research_input)
    validate_gate(gate)
    if stage not in STAGE_CAPABILITIES:
        raise ValueError("NATIVE_RESEARCH_STAGE_UNSUPPORTED")
    subjects=research_subjects(research_input)
    value={"stage":stage,"planning_only":True,"input_binding":research_input_binding(research_input),
        "gate_hash":gate["bundle_hash"],"decision_cutoff":gate["decision_cutoff"],
        "items":[{"security_id":item["security_id"],"asset_type":item["asset_type"],
                  "required_capabilities":list(STAGE_CAPABILITIES[stage]) if item["asset_type"]=="COMMON_STOCK" else [],
                  "coverage":"NOT_RESEARCHED" if item["asset_type"]=="COMMON_STOCK" else "CAPABILITY_GAP"}
                 for item in subjects],"complete_portfolio_decision":False,"risk_status":"NOT_RUN"}
    value["scope_hash"]=canonical_hash(value)
    return value


def summarize_reports(scope: Mapping, reports: Sequence[Mapping]) -> dict:
    if scope.get("scope_hash")!=canonical_hash({k:v for k,v in scope.items() if k!="scope_hash"}):
        raise ValueError("NATIVE_RESEARCH_SCOPE_HASH_INVALID")
    ids=[r.get("report_id") for r in reports]
    if len(ids)!=len(set(ids)):
        raise ValueError("NATIVE_RESEARCH_REPORT_DUPLICATE")
    known={item["security_id"]:item for item in scope["items"]}
    for report in reports:
        for sid in report.get("security_ids",[report["security"]["security_id"]]):
            if sid not in known or report["capability"] not in known[sid]["required_capabilities"]:
                raise ValueError("NATIVE_RESEARCH_REPORT_OUTSIDE_STAGE")
            validate_report(report,input_binding=scope["input_binding"],gate_hash=scope["gate_hash"],
                            security_id=sid,cutoff=scope["decision_cutoff"])
    coverage=[]
    for item in scope["items"]:
        capabilities=[]
        for capability in item["required_capabilities"]:
            found=[r for r in reports if capability==r["capability"] and item["security_id"] in r.get("security_ids",[r["security"]["security_id"]])]
            if len(found)>1:
                raise ValueError("NATIVE_RESEARCH_REPORT_VERSION_SELECTION_REQUIRED")
            report=found[0] if found else None
            capabilities.append({"capability":capability,"report_id":report["report_id"] if report else None,
                                 "report_hash":report["report_hash"] if report else None,
                                 "research_status":report["research"]["status"] if report else "NOT_RESEARCHED"})
        coverage.append({**copy.deepcopy(item),"capabilities":capabilities})
    missing=any(any(c["report_id"] is None for c in item["capabilities"]) for item in coverage)
    gaps=any(item["coverage"]=="CAPABILITY_GAP" for item in coverage)
    return {"stage":scope["stage"],"coverage":coverage,
            "all_required_reports_saved":bool(reports) and not missing,
            "complete_input_research":bool(reports) and not missing and not gaps,
            "host_execution":"UNVERIFIED","content_verdict":"NOT_REVIEWED",
            "complete_portfolio_decision":False,"risk_status":"NOT_RUN"}
