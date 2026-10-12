"""原生报告的业务读取、依赖冻结与综合检查；不读取宿主会话数据库。"""
from __future__ import annotations

import copy
from typing import Any, Mapping, Sequence

from product.runtime.hashing import canonical_hash
from product.tools.references import scoped_claim_reference
from product.tools.report_contracts import reject_actions
from product.tools.research import ResearchAccessError, _read_json
from product.tools.report_submission import VERSION

CORE_FORWARD = {
    "COMPANY_RESEARCH", "TECHNICAL_STRUCTURE", "FUNDAMENTAL_EVENT",
    "INDUSTRY_COMPARISON", "MACRO_CONTEXT", "MARKET_STATE",
}


def validate_report(report: Mapping[str, Any], *, input_binding: Mapping[str, Any],
                    gate_hash: str, security_id: str, cutoff: str) -> None:
    if (report.get("schema_version") != VERSION
            or report.get("report_hash") != canonical_hash({k: v for k, v in report.items() if k != "report_hash"})):
        raise ResearchAccessError("NATIVE_RESEARCH_DEPENDENCY_HASH_INVALID")
    if (report.get("input_binding") != dict(input_binding) or report.get("gate_hash") != gate_hash
            or security_id not in report.get("security_ids", [report.get("security", {}).get("security_id")])
            or report.get("decision_cutoff") != cutoff or report.get("business_validation") != "VALIDATED"):
        raise ResearchAccessError("NATIVE_RESEARCH_DEPENDENCY_BINDING_INVALID")
    if any(not isinstance(report.get(key), str) or not report[key] for key in ("source_id", "as_of", "retrieved_at")):
        raise ResearchAccessError("NATIVE_RESEARCH_DEPENDENCY_PROVENANCE_REQUIRED")
    if report.get("advisory_only") is not True:
        raise ResearchAccessError("NATIVE_RESEARCH_DEPENDENCY_SCOPE_INVALID")
    fixture_cio = report.get("capability") == "FIXTURE_COUNCIL_DECISION" and report["input_binding"].get("input_kind") == "FIXTURE_COUNCIL"
    if not fixture_cio:
        if report.get("risk_status") != "NOT_RUN":
            raise ResearchAccessError("NATIVE_RESEARCH_DEPENDENCY_SCOPE_INVALID")
        reject_actions(report["research"])


def validate_dependencies(reports: Sequence[Mapping[str, Any]], *, capability: str,
                          input_binding: Mapping[str, Any], gate_hash: str,
                          security_id: str, cutoff: str) -> list[dict[str, Any]]:
    if capability == "INDEPENDENT_FIRST_PASS" and reports:
        raise ResearchAccessError("CONTEXT_ISOLATION_VIOLATION")
    ids = [r.get("report_id") for r in reports]
    if any(not isinstance(ref, str) or not ref for ref in ids) or len(ids) != len(set(ids)):
        raise ResearchAccessError("NATIVE_RESEARCH_DEPENDENCY_AMBIGUOUS")
    for report in reports:
        validate_report(report, input_binding=input_binding, gate_hash=gate_hash,
                        security_id=security_id, cutoff=cutoff)
        ready_statuses = {"COMPLETE", "LOW_CONFIDENCE", "SOURCE_LIMITED"}
        if capability == "FIXTURE_COUNCIL_DECISION":
            ready_statuses.add("INSUFFICIENT_EVIDENCE")
        if report["research"].get("status") not in ready_statuses:
            raise ResearchAccessError("NATIVE_RESEARCH_DEPENDENCY_NOT_READY")
    caps = {r["capability"] for r in reports}
    if capability == "RESEARCH_REPORT" and "FUNDAMENTAL_EVENT" not in caps:
        raise ResearchAccessError("NATIVE_RESEARCH_DEPENDENCY_MISSING")
    if capability == "FIXTURE_COUNCIL_DECISION" and caps != {"FIXTURE_COMPANY_RESEARCH", "INDEPENDENT_FIRST_PASS"}:
        raise ResearchAccessError("NATIVE_RESEARCH_DEPENDENCY_MISSING")
    if capability == "RESEARCH_SYNTHESIS" and not CORE_FORWARD | {"INDEPENDENT_FIRST_PASS"} <= caps:
        raise ResearchAccessError("NATIVE_RESEARCH_DEPENDENCY_MISSING")
    return copy.deepcopy(list(reports))


def known_claims(reports: Sequence[Mapping[str, Any]]) -> list[str]:
    return sorted(scoped_claim_reference(report, claim["claim_id"])
                  for report in reports for claim in report["research"].get("claims", []))


def validate_synthesis(draft: Mapping[str, Any], *, reports: Sequence[Mapping[str, Any]],
                       read_report_ids: Sequence[str]) -> None:
    allowed = {r["report_id"]: r for r in reports}
    selections = draft["report_selections"]
    if set(selections) != set(allowed) or not set(selections) <= set(read_report_ids):
        raise ResearchAccessError("NATIVE_CIO_REPORT_CONSUMPTION_INVALID")
    for fact in [*draft["key_facts"], *draft["macro_market_transmission"]]:
        if not set(fact["report_ids"]) <= set(allowed):
            raise ResearchAccessError("NATIVE_CIO_REPORT_REFERENCE_INVALID")
    challenges = {(r["report_id"], c["challenge_id"]) for r in reports
                  for c in r["research"].get("challenges", [])}
    seen = set()
    for disposition in draft["challenge_dispositions"]:
        pair = (disposition["report_id"], disposition["challenge_id"])
        if pair not in challenges or pair in seen:
            raise ResearchAccessError("NATIVE_CIO_CHALLENGE_REFERENCE_INVALID")
        seen.add(pair)
    if challenges and not seen:
        raise ResearchAccessError("NATIVE_CIO_CHALLENGE_DISPOSITION_MISSING")


def read_reports(tools, *, report_ids: list[str]) -> dict[str, Any]:
    task, _gate = tools._authorize()
    if "read_reports" not in task["permissions"]:
        raise ResearchAccessError("NATIVE_RESEARCH_REPORT_READ_FORBIDDEN")
    if (not isinstance(report_ids, list) or not report_ids or len(report_ids) != len(set(report_ids))
            or any(not isinstance(ref, str) for ref in report_ids)):
        raise ResearchAccessError("NATIVE_RESEARCH_REPORT_SELECTION_INVALID")
    allowed = {report["report_id"]: report for report in task.get("dependency_reports", [])}
    if not set(report_ids) <= set(allowed):
        raise ResearchAccessError("NATIVE_RESEARCH_REPORT_NOT_ALLOWED")
    reports = [copy.deepcopy(allowed[ref]) for ref in report_ids]
    for report in reports:
        validate_report(report, input_binding=task["input_binding"], gate_hash=task["gate_hash"],
                        security_id=task["security"]["security_id"], cutoff=task["decision_cutoff"])
    result = {"reports": reports, "execution_observation": "UNVERIFIED"}
    tools._record(task, "read_reports", {"report_ids": report_ids}, result)
    return result


def read_report_ids(tools) -> set[str]:
    task, _gate = tools._authorize()
    result = set()
    for path in (tools.root/"tools").glob("*.json"):
        event = _read_json(path)
        if (event.get("event_hash") != canonical_hash({k: v for k, v in event.items() if k != "event_hash"})
                or event.get("task_hash") != task["task_hash"]):
            raise ResearchAccessError("NATIVE_RESEARCH_TOOL_RECORD_INVALID")
        if event["tool"] == "read_reports":
            result.update(event["report_ids"])
    return result


def render_report(report: Mapping[str, Any]) -> str:
    """只展示已提交中文原文和明确验证范围，不写研究总评。"""
    risk_note = ("合成fixture，不是当前账户建议；Risk=" + report["risk_status"] + "，只表示原硬约束检查。"
                 if report["input_binding"].get("input_kind") == "FIXTURE_COUNCIL"
                 else "仅供研究参考，账户适配未评估，Risk未运行。")
    lines = [f"# {report['security']['display_symbol']} 研究报告", "",
             f"资料截止：{report['decision_cutoff']}",
             "业务结构与引用已校验；宿主执行、作者身份及内容裁定须分别查看。",
             risk_note, ""]
    if report.get("fixture_decision"):
        decision = report["fixture_decision"]
        lines.extend(["硬Risk业务终态："+decision["terminal_state"],
                      "最终fixture动作："+(decision["final_action"] or "待原作者唯一修订"),
                      "以下保留原作者草稿，不以草稿动作覆盖硬Risk否决。", ""])
    def walk(value: Any, label: str = "") -> None:
        if isinstance(value, str):
            if value:
                lines.append((label+"：" if label else "")+value)
        elif isinstance(value, list):
            for item in value:
                walk(item, label)
        elif isinstance(value, dict):
            for key, item in value.items():
                if key.endswith(("_id", "_ids", "_refs", "_selections")) or key in {"artifact_ref", "calculation_ref"}:
                    continue
                if isinstance(item, (dict, list)):
                    walk(item)
                elif isinstance(item, str):
                    walk(item)
                elif isinstance(item, (int, float)) and not isinstance(item, bool):
                    lines.append(str(item))
    walk(report["research"])
    return "\n\n".join(lines)+"\n"
