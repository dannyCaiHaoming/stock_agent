"""Read-only, run-scoped evidence delivery and report-reference audit."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from .hashing import canonical_hash, file_hash


CAPABILITY_DOMAIN = {
    "COMPANY_RESEARCH": "COMPANY", "FUNDAMENTAL_EVENT": "COMPANY",
    "RESEARCH_REPORT": "COMPANY", "MACRO_CONTEXT": "MACRO",
    "MARKET_STATE": "MARKET",
    "INDUSTRY_COMPARISON": "MARKET", "TECHNICAL_STRUCTURE": "MARKET",
    "OPTIONS_FLOW": "MARKET", "OWNERSHIP_DISCLOSURE": "COMPANY",
}
CORE_ITEMS = {
    "COMPANY": ("financial_history", "identity_profile", "business_segments"),
    "MACRO": ("us_treasury_10y_yield", "us_cpi_all_items", "us_unemployment_rate"),
    "MARKET": ("close_price", "historical_close_price", "market_context_close"),
}
DATASET_DOMAIN = {
    "financial_history": "COMPANY", "identity_profile": "COMPANY",
    "business_segments": "COMPANY", "management_governance": "COMPANY",
    "capital_allocation": "COMPANY", "earnings_guidance": "COMPANY",
    "analyst_expectations": "COMPANY", "event_context": "COMPANY",
    "research_discovery": "COMPANY", "macro_history": "MACRO",
    "economic_calendar": "MACRO", "dot_plot": "MACRO",
    "market_breadth": "MARKET", "fedwatch_expectations": "MARKET",
}


def _domain(dataset: str, source: str) -> str:
    if dataset in DATASET_DOMAIN:
        return DATASET_DOMAIN[dataset]
    if source.startswith(("bls-", "us-treasury-", "federal-reserve-", "bea-", "fred-", "official-macro")):
        return "MACRO"
    if source.startswith(("yahoo-market-context", "yahoo-daily", "yahoo-options", "market-context")):
        return "MARKET"
    return "COMPANY"


def _read(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    return value if isinstance(value, dict) else None


def _refs(value: Any, field: str) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            if key == field and isinstance(child, list):
                found.update(item for item in child if isinstance(item, str))
            elif isinstance(child, (Mapping, list)):
                found.update(_refs(child, field))
    elif isinstance(value, list):
        for item in value:
            found.update(_refs(item, field))
    return found


def _events(run_dir: Path) -> tuple[bool, dict[str, dict[str, Any]]]:
    path = run_dir / "events/mcp/events.jsonl"
    if not path.is_file():
        return False, {}
    result: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"evidence": set(), "calculations": {}}
    )
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("event_type") != "mcp_tool_result":
            continue
        invocation = event.get("invocation_id")
        if not isinstance(invocation, str) or not invocation:
            continue
        tool = event.get("tool")
        evidence = {item for item in event.get("evidence_ids", []) if isinstance(item, str)}
        if tool in {"fixture_evidence.query", "live_evidence.query", "equity_research_attachments.query"}:
            result[invocation]["evidence"].update(evidence)
        calculation = event.get("calculation_id")
        if tool in {"fixture_math.calculate", "live_math.calculate"} and isinstance(calculation, str):
            result[invocation]["calculations"][calculation] = evidence
        if tool == "equity_research_attachments.query":
            for item in event.get("calculation_ids", []):
                if isinstance(item, str):
                    result[invocation]["calculations"][item] = evidence
    return True, result


def _reports(run_dir: Path) -> list[dict[str, Any]]:
    paths = [
        *run_dir.glob("research/reports/**/equity-research.json"),
        *run_dir.glob("research/reports/**/dimension-report.json"),
        *run_dir.glob("research/imported-company-research/**/equity-research.json"),
        *run_dir.glob("research/skeptic/reports/**/counter-thesis.json"),
    ]
    return [
        {"path": str(path.relative_to(run_dir)), "file_hash": file_hash(path), "value": _read(path)}
        for path in sorted(set(paths))
    ]


def _verify_company_binding(run_dir: Path, company_dir: Path, gate: Mapping[str, Any]) -> None:
    imported = _read(run_dir / "research/imported-company-research/import-manifest.json")
    source_manifest = _read(company_dir / "run_manifest.json")
    source_gate = _read(company_dir / "evidence/gate.json")
    source_proof = company_dir / "research/execution-proof.json"
    if not imported or not source_manifest or not source_gate or not source_proof.is_file():
        raise ValueError("RESEARCH_AUDIT_COMPANY_BINDING_INVALID")
    if (
        not isinstance(imported.get("source_run"), str)
        or Path(imported["source_run"]).resolve() != company_dir
        or imported.get("source_run_id") != source_manifest.get("run_id")
        or source_gate.get("run_id") != source_manifest.get("run_id")
        or imported.get("target_decision_cutoff") != gate.get("decision_cutoff")
        or imported.get("source_manifest_file_hash") != file_hash(company_dir / "run_manifest.json")
        or imported.get("source_execution_proof_file_hash") != file_hash(source_proof)
    ):
        raise ValueError("RESEARCH_AUDIT_COMPANY_BINDING_INVALID")
    if not isinstance(imported.get("reports"), list) or not imported["reports"]:
        raise ValueError("RESEARCH_AUDIT_COMPANY_BINDING_INVALID")
    source_reports = {
        item["value"].get("report_id"): item
        for item in _reports(company_dir) if isinstance(item["value"], dict)
    }
    for link in imported.get("reports", []):
        source = source_reports.get(link.get("report_id")) if isinstance(link, dict) else None
        target_ref = link.get("artifact_ref") if isinstance(link, dict) else None
        target_path = (run_dir / target_ref).resolve() if isinstance(target_ref, str) else run_dir
        target = _read(target_path) if target_path.is_relative_to(run_dir) else None
        if (
            source is None or target is None
            or source["file_hash"] != link.get("source_json_file_hash")
            or canonical_hash(source["value"]) != link.get("report_hash")
            or target.get("report_id") != link.get("report_id")
            or canonical_hash(target) != link.get("report_hash")
            or link.get("source_gate_hash") != source_gate.get("bundle_hash")
            or link.get("source_decision_cutoff") != source_gate.get("decision_cutoff")
            or link.get("source_run_id") != source_manifest.get("run_id")
        ):
            raise ValueError("RESEARCH_AUDIT_COMPANY_BINDING_INVALID")


def _verify_cio_binding(run_dir: Path, cio_dir: Path, gate: Mapping[str, Any]) -> None:
    manifest = _read(cio_dir / "run_manifest.json")
    request = _read(cio_dir / "predecision-cio-request.json")
    synthesis = _read(cio_dir / "cio-research-synthesis.json")
    package_path = run_dir / "research/skeptic/pre-decision-research-package.json"
    copied_package = cio_dir / "source-inputs/research/skeptic/pre-decision-research-package.json"
    copied_gate = cio_dir / "source-inputs/evidence/gate.json"
    package = _read(package_path)
    if (
        not manifest or not request or not synthesis or not package
        or not copied_package.is_file() or not copied_gate.is_file()
    ):
        raise ValueError("RESEARCH_AUDIT_CIO_BINDING_INVALID")
    package_hash = package.get("package_hash")
    if (
        not isinstance(manifest.get("source_run_dir"), str)
        or Path(manifest["source_run_dir"]).resolve() != run_dir
        or manifest.get("source_run_id") != gate.get("run_id")
        or request.get("source_run_id") != gate.get("run_id")
        or synthesis.get("source_run_id") != gate.get("run_id")
        or request.get("decision_cutoff") != gate.get("decision_cutoff")
        or synthesis.get("decision_cutoff") != gate.get("decision_cutoff")
        or package.get("decision_cutoff") != gate.get("decision_cutoff")
        or package.get("gate_hash") != gate.get("bundle_hash")
        or manifest.get("source_package_hash") != package_hash
        or request.get("source_package_hash") != package_hash
        or synthesis.get("source_package_hash") != package_hash
        or synthesis.get("run_id") != manifest.get("run_id")
        or request.get("run_id") != manifest.get("run_id")
        or file_hash(package_path) != file_hash(copied_package)
        or file_hash(run_dir / "evidence/gate.json") != file_hash(copied_gate)
    ):
        raise ValueError("RESEARCH_AUDIT_CIO_BINDING_INVALID")


def build_research_consumption_audit(
    run_dir: Path, *, company_run: Path | None = None, cio_run: Path | None = None,
) -> dict[str, Any]:
    """Summarize only observable delivery/reference paths; never infer model attention."""
    run_dir = Path(run_dir).resolve()
    gate_path = run_dir / "evidence/gate.json"
    gate = _read(gate_path)
    if gate is None:
        raise ValueError("RESEARCH_AUDIT_GATE_MISSING")
    company_dir = Path(company_run).resolve() if company_run is not None else None
    cio_dir = Path(cio_run).resolve() if cio_run is not None else None
    if company_dir is not None:
        _verify_company_binding(run_dir, company_dir, gate)
    if cio_dir is not None:
        _verify_cio_binding(run_dir, cio_dir, gate)
    event_sources = [run_dir] + ([company_dir] if company_dir is not None else [])
    events: dict[str, dict[str, Any]] = {}
    event_file_presence: dict[str, bool] = {}
    for source in event_sources:
        present, entries = _events(source)
        event_file_presence[str(source)] = present
        events.update(entries)
    report_sources = [run_dir] + ([company_dir] if company_dir is not None else [])
    reports = [{**item, "source_dir": source}
               for source in report_sources for item in _reports(source)]
    references: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: {"direct": set(), "calculation": set(), "attachment_parents": set()}
    )
    report_list: list[dict[str, Any]] = []
    for item in reports:
        value = item["value"]
        if not isinstance(value, dict):
            continue
        invocation = value.get("invocation_id")
        if not isinstance(invocation, str):
            continue
        references[invocation]["direct"].update(_refs(value, "evidence_refs"))
        references[invocation]["calculation"].update(_refs(value, "calculation_refs"))
        if references[invocation]["calculation"]:
            for ref in value.get("artifact_refs", []):
                if not isinstance(ref, str) or not ref.endswith("-calculation.json"):
                    continue
                attachment = (item["source_dir"] / ref).resolve()
                if not attachment.is_relative_to(item["source_dir"]):
                    continue
                artifact = _read(attachment)
                if artifact and artifact.get("schema_version") in {
                    "technical-calculation/1.0.0", "market-state-calculation/1.0.0",
                }:
                    references[invocation]["attachment_parents"].update(
                        evidence_id for evidence_id in artifact.get("evidence_fact_ids", [])
                        if isinstance(evidence_id, str)
                    )
        report_list.append({
            "report_id": value.get("report_id"), "invocation_id": invocation,
            "capability": value.get("capability", "COMPANY_RESEARCH" if "equity-research" in item["path"] else None),
            "status": value.get("status"), "report_hash": value.get("report_hash"),
            "file_hash": item["file_hash"], "artifact_ref": item["path"],
        })
    by_id = {
        item["evidence_id"]: item for item in gate.get("allowed_evidence", [])
        if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
    }
    excluded = {
        item["evidence_id"]: item for item in gate.get("excluded", [])
        if isinstance(item, dict) and isinstance(item.get("evidence_id"), str)
    }
    # An actually cited calculation makes its recorded input Evidence indirect support.
    direct_by_invocation: dict[str, set[str]] = {}
    indirect_by_invocation: dict[str, set[str]] = {}
    attachment_by_invocation: dict[str, set[str]] = {}
    for invocation, refs in references.items():
        direct = refs["direct"]
        indirect: set[str] = set()
        for calculation in refs["calculation"]:
            indirect.update(events.get(invocation, {}).get("calculations", {}).get(calculation, set()))
        frontier = list(direct | indirect)
        while frontier:
            evidence_id = frontier.pop()
            fact = by_id.get(evidence_id)
            if fact is None:
                continue
            for parent in fact.get("parent_ids", []):
                if parent not in direct and parent not in indirect:
                    indirect.add(parent)
                    frontier.append(parent)
        direct_by_invocation[invocation] = direct
        indirect_by_invocation[invocation] = indirect - direct
        attachment_by_invocation[invocation] = refs["attachment_parents"] - direct - indirect
    coverage = _read(run_dir / "audit/provider-coverage.json") or {}
    source_plan = _read(Path(__file__).resolve().parents[1] / "mcp/live/research-supplement-source-plan.json") or {}
    routed_domains = {
        item["dataset"]: CAPABILITY_DOMAIN.get(item.get("target_capability"), "COMPANY")
        for item in coverage.get("capability_routing", {}).get("dataset_observations", [])
        if isinstance(item, Mapping) and isinstance(item.get("dataset"), str)
    }
    observed: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    observed_dataset_by_id: dict[str, str] = {}
    for provider in coverage.get("providers", []):
        for observation in provider.get("dataset_observations", []):
            dataset = observation.get("dataset")
            if isinstance(dataset, str):
                observed[(provider.get("provider", ""), dataset)].append(observation)
                for evidence_id in observation.get("evidence_ids", []):
                    if isinstance(evidence_id, str):
                        observed_dataset_by_id.setdefault(evidence_id, dataset)
    datasets: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for fact in [*by_id.values(), *excluded.values()]:
        metadata = fact.get("metadata") or {}
        field = fact.get("semantic_field") or "unknown"
        dataset = (
            observed_dataset_by_id.get(fact["evidence_id"])
            or metadata.get("dataset")
            or ("financial_history" if str(field).startswith(("us-gaap.", "dei.")) else None)
            or field
        )
        source = fact.get("source_id") or "unknown"
        datasets[(str(dataset), str(source), str(field))].append(fact)
    rows = []
    for (dataset, source, field), facts in sorted(datasets.items()):
        ids = {item["evidence_id"] for item in facts}
        allowed = ids & by_id.keys()
        delivered = {inv: sorted(ids & record["evidence"]) for inv, record in events.items() if ids & record["evidence"]}
        direct = {inv: sorted(ids & refs) for inv, refs in direct_by_invocation.items() if ids & refs}
        indirect = {inv: sorted(ids & refs) for inv, refs in indirect_by_invocation.items() if ids & refs}
        attachment = {inv: sorted(ids & refs) for inv, refs in attachment_by_invocation.items() if ids & refs}
        if direct or indirect:
            use_status = "REPORT_REFERENCED"
        elif attachment:
            use_status = "ATTACHMENT_PARENT_LINKED"
        elif delivered:
            use_status = "DELIVERED_UNREFERENCED"
        elif not all(event_file_presence.values()):
            use_status = "NOT_VERIFIED"
        elif allowed:
            use_status = "AVAILABLE_NOT_QUERIED"
        else:
            use_status = "GATE_EXCLUDED"
        sample = sorted(facts, key=lambda item: item["evidence_id"])[0]
        delivered_ids = {evidence_id for values in delivered.values() for evidence_id in values}
        unqueried = [item for item in facts if item["evidence_id"] in allowed - delivered_ids]
        unqueried_limit = 24 if "EarningsPerShareDiluted" in field else 3
        rows.append({
            "domain": routed_domains.get(dataset, _domain(dataset, source)),
            "dataset": dataset, "source_id": source, "semantic_field": field,
            "as_of": sample.get("as_of"), "retrieved_at": sample.get("retrieved_at"),
            "sample_evidence_id": sample["evidence_id"], "sample_raw_content_hash": sample.get("raw_content_hash"),
            "gate_allowed_count": len(allowed), "gate_excluded_count": len(ids - allowed),
            "available_not_delivered_count": len(unqueried),
            "available_not_delivered_samples": [
                {
                    "evidence_id": item["evidence_id"],
                    "as_of": item.get("as_of"),
                    "period_start": (item.get("metadata") or {}).get("period_start"),
                    "period_end": (item.get("metadata") or {}).get("period_end"),
                    "form": (item.get("metadata") or {}).get("form"),
                }
                for item in sorted(unqueried, key=lambda item: item["evidence_id"])[:unqueried_limit]
            ],
            "delivered_by_invocation": delivered, "direct_refs_by_invocation": direct,
            "indirect_refs_by_invocation": indirect,
            "attachment_parent_refs_by_invocation": attachment,
            "use_status": use_status,
        })
    cio = _read(cio_dir / "cio-research-synthesis.json") if cio_dir is not None else None
    trace = _read(cio_dir / "decision_trace.json") if cio_dir is not None else None
    consumed = cio.get("consumed_reports", []) if cio is not None else []
    report_status_by_id = {
        item["report_id"]: item["status"]
        for item in report_list if isinstance(item.get("report_id"), str)
    }
    report_status_by_invocation = {
        item["invocation_id"]: item["status"]
        for item in report_list if isinstance(item.get("invocation_id"), str)
    }
    consumed_by_id = {
        item["report_id"]: item
        for item in consumed if isinstance(item.get("report_id"), str)
    }
    consumed_report_statuses = [
        {
            "report_id": report_id,
            "status": report_status_by_id.get(
                report_id,
                report_status_by_invocation.get(item.get("invocation_id"), "NOT_VERIFIED"),
            ),
        }
        for report_id, item in sorted(consumed_by_id.items())
    ]
    expected = {
        (domain, dataset)
        for domain, datasets_in_domain in CORE_ITEMS.items()
        for dataset in datasets_in_domain
    }
    expected.update(
        (
            routed_domains.get(item["dataset"], DATASET_DOMAIN.get(item["dataset"], "COMPANY")),
            item["dataset"],
        )
        for item in source_plan.get("datasets", [])
        if isinstance(item, Mapping) and isinstance(item.get("dataset"), str)
    )
    coverage_items = []
    for domain, dataset in sorted(expected):
        matching = [row for row in rows if row["domain"] == domain and row["dataset"] == dataset]
        observations = [
            {"provider": provider, **observation}
            for (provider, observed_dataset), items in observed.items()
            if observed_dataset == dataset
            for observation in items
        ]
        source_states = {item.get("status") for item in observations}
        if any(item["gate_allowed_count"] for item in matching):
            source_status = "FROZEN_FACT_AVAILABLE"
        elif not observations:
            source_status = "NOT_VERIFIED"
        elif source_states <= {"NOT_ATTEMPTED"}:
            source_status = "NOT_ATTEMPTED"
        elif source_states <= {"SOURCE_LIMITED", "FAILED"}:
            source_status = "SOURCE_LIMITED"
        else:
            source_status = "OBSERVED_NO_FROZEN_FACT"
        coverage_items.append({
            "domain": domain, "dataset": dataset,
            "priority": "CORE" if dataset in CORE_ITEMS.get(domain, ()) else "AUXILIARY",
            "frozen_fact_count": sum(row["gate_allowed_count"] + row["gate_excluded_count"] for row in matching),
            "gate_allowed_count": sum(row["gate_allowed_count"] for row in matching),
            "source_observations": observations,
            "source_status": source_status,
            "use_statuses": sorted({row["use_status"] for row in matching}) or ["NO_FROZEN_FACT"],
        })
    return {
        "schema_version": "research-consumption-audit/1.0.0",
        "run_id": gate.get("run_id"), "decision_cutoff": gate.get("decision_cutoff"),
        "gate_file_hash": file_hash(gate_path), "gate_hash": gate.get("bundle_hash"),
        "source_binding": {
            "company": "VERIFIED" if company_dir is not None else "NOT_REQUESTED",
            "cio": "VERIFIED" if cio_dir is not None else "NOT_REQUESTED",
        },
        "event_file_presence": event_file_presence, "expected_core_items": CORE_ITEMS,
        "provider_observations": [
            {"provider": provider, "dataset": dataset, "observations": items}
            for (provider, dataset), items in sorted(observed.items())
        ],
        "coverage_items": coverage_items, "rows": rows, "reports": report_list,
        "cio": {
            "run_id": cio.get("run_id") if cio else None,
            "status": cio.get("status") if cio else "NOT_VERIFIED",
            "consumed_report_ids": sorted({item.get("report_id") for item in consumed if item.get("report_id")}),
            "consumed_report_statuses": consumed_report_statuses,
            "trace_hash": trace.get("trace_hash") if trace else None,
        },
    }


def render_audit_summary(audit: Mapping[str, Any]) -> str:
    lines = ["# 三域资料消费核对", "", f"Run：{audit['run_id']}；截止：{audit['decision_cutoff']}", ""]
    for domain, items in CORE_ITEMS.items():
        lines.extend([f"## {domain}", ""])
        domain_rows = [row for row in audit["rows"] if row["domain"] == domain]
        lines.append(
            f"Gate 允许 {sum(row['gate_allowed_count'] for row in domain_rows)} 项；"
            f"有交付记录 {sum(bool(row['delivered_by_invocation']) for row in domain_rows)} 组；"
            f"报告直接或间接引用 {sum(bool(row['direct_refs_by_invocation'] or row['indirect_refs_by_invocation']) for row in domain_rows)} 组；"
            f"计算附件父资料关联 {sum(bool(row['attachment_parent_refs_by_invocation']) for row in domain_rows)} 组。"
        )
        for dataset in items:
            matching = next(
                (item for item in audit["coverage_items"] if item["domain"] == domain and item["dataset"] == dataset),
                None,
            )
            state = ", ".join(matching["use_statuses"]) if matching else "NOT_VERIFIED"
            lines.append(f"- 核心资料项 {dataset}：{state}")
        lines.append("")
    failed_reports = sum(
        item["status"] == "FAILED" for item in audit["cio"]["consumed_report_statuses"]
    )
    lines.append(
        f"CIO：{audit['cio']['status']}；来源报告清单 {len(audit['cio']['consumed_report_ids'])} 份"
        f"（其中 FAILED {failed_reports} 份；列入清单不等于有效研究依据）。"
    )
    lines.append("事件文件存在不证明 invocation 完整执行；工具成功事件仅证明交付，正式报告引用证明已表达依据；未验证项保持未验证。")
    lines.append("计算附件父资料仅证明整体输入关联，不能精确归因至单个指标或模型注意。")
    return "\n".join(lines) + "\n"
