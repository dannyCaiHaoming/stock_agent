"""Read-only, run-scoped evidence delivery and report-reference audit."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping

from .hashing import canonical_hash, file_hash, verify_legacy_envelope_hash, HashContractError


from .research_input_topology import (
    CAPABILITY_DOMAIN, DATASET_DOMAIN, EIGHT_DIMENSION_INPUTS,
    dataset_consumers, dataset_domain, fact_dataset,
)
CORE_ITEMS = {
    "COMPANY": ("financial_history", "identity_profile", "business_segments"),
    "MACRO": ("us_treasury_10y_yield", "us_cpi_all_items", "us_unemployment_rate"),
    "MARKET": ("close_price", "historical_close_price", "market_context_close"),
}


def _domain(dataset: str, source: str) -> str:
    return dataset_domain(dataset)


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


def _events(run_dir: Path) -> tuple[bool, dict[str, dict[str, Any]], str]:
    path = run_dir / "events/mcp/events.jsonl"
    if not path.is_file():
        return False, {}, "NOT_OBSERVED"
    gate = _read(run_dir / "evidence/gate.json") or {}
    unsigned = False
    result: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"evidence": set(), "calculations": {}}
    )
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, Mapping):
            raise ValueError("RESEARCH_AUDIT_EVENT_INVALID")
        if "event_hash" not in event:
            unsigned = True
            continue
        try:
            verify_legacy_envelope_hash(event, hash_field="event_hash", location=str(path))
        except HashContractError as exc:
            raise ValueError(f"RESEARCH_AUDIT_EVENT_HASH_MISMATCH:{exc}") from exc
        event_run_id = event.get("run_id")
        if event.get("tool") == "research_report.submit":
            from .research_submission import submission_event_identity
            try:
                identity = submission_event_identity(
                    run_dir, event.get("invocation_id"), event.get("submission"), event.get("output_hash"),
                )
            except (ValueError, KeyError, TypeError, OSError, StopIteration) as exc:
                raise ValueError("RESEARCH_AUDIT_SUBMISSION_BINDING_INVALID") from exc
            legacy = "run_id" not in event and "event_type" not in event
            if (any(event[field] != value for field, value in identity.items() if field in event)
                    or not legacy and (event.get("event_type") != "research_submission" or any(
                        event.get(field) != value for field, value in identity.items()
                    ))):
                raise ValueError("RESEARCH_AUDIT_SUBMISSION_BINDING_INVALID")
            event_run_id = identity["run_id"]
        if event_run_id != gate.get("run_id"):
            raise ValueError("RESEARCH_AUDIT_EVENT_RUN_MISMATCH")
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
    return True, result, "UNVERIFIED_LEGACY_EVENTS" if unsigned else "HASH_VERIFIED"


def _query_diagnostics(run_dir: Path) -> dict[str, Any]:
    """Count observed Gate reads without copying tool payloads into the audit."""

    path = run_dir / "events/mcp/events.jsonl"
    if not path.is_file():
        return {"status": "NOT_OBSERVED", "by_invocation": [], "by_tool": []}
    by_invocation: dict[str, dict[str, Any]] = {}
    by_tool: dict[tuple[str, str], dict[str, Any]] = {}
    tool_names = {
        "query": "query", "fixture_evidence.query": "query", "live_evidence.query": "query",
        "calculate": "calculate", "fixture_math.calculate": "calculate", "live_math.calculate": "calculate",
    }
    for position, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        event = json.loads(line)
        raw_tool = event.get("tool")
        tool = tool_names.get(raw_tool, raw_tool)
        invocation_id = event.get("invocation_id")
        if (not isinstance(tool, str) or not tool or not isinstance(invocation_id, str)
                or not invocation_id or event.get("event_type") not in {
                    "mcp_tool_result", "mcp_tool_error", "mcp_reference_transport"}):
            continue
        if event.get("event_type") == "mcp_reference_transport":
            tool_row = by_tool.setdefault((invocation_id, tool), {
                "invocation_id": invocation_id, "tool": tool,
                "success_count": 0, "errors": [], "calculation_results": [],
                "result_bytes_observed": 0, "result_bytes_missing_count": 0,
            })
            size = event.get("output_bytes")
            tool_row["model_transport_count"] = tool_row.get("model_transport_count", 0) + 1
            if type(size) is int and size >= 0:
                tool_row["model_transport_bytes_observed"] = tool_row.get("model_transport_bytes_observed", 0) + size
            else:
                tool_row["model_transport_bytes_missing_count"] = tool_row.get("model_transport_bytes_missing_count", 0) + 1
            row = by_invocation.setdefault(invocation_id, {
                "invocation_id": invocation_id, "query_count": 0,
                "result_bytes_observed": 0, "result_bytes_missing_count": 0,
                "repeated_evidence_ids": [], "first_error_code": None,
            })
            if tool == "query":
                size = event.get("output_bytes")
                if type(size) is int and size >= 0:
                    row["model_transport_bytes_observed"] = row.get("model_transport_bytes_observed", 0) + size
                else:
                    row["model_transport_bytes_missing_count"] = row.get("model_transport_bytes_missing_count", 0) + 1
                row["model_transport_count"] = row.get("model_transport_count", 0) + 1
            continue
        tool_row = by_tool.setdefault((invocation_id, tool), {
            "invocation_id": invocation_id, "tool": tool,
            "success_count": 0, "errors": [], "calculation_results": [],
            "result_bytes_observed": 0, "result_bytes_missing_count": 0,
        })
        if event.get("event_type") == "mcp_tool_error":
            tool_row["errors"].append({
                "event_position": position,
                "error_code": str(event.get("error", "UNKNOWN")).split(":", 1)[0],
                "operation": event.get("operation") or "NOT_OBSERVED",
            })
        elif event.get("event_type") == "mcp_tool_result":
            tool_row["success_count"] += 1
            size = event.get("output_bytes")
            if type(size) is int and size >= 0:
                tool_row["result_bytes_observed"] += size
            else:
                tool_row["result_bytes_missing_count"] += 1
            if tool == "calculate":
                tool_row["calculation_results"].append({
                    "event_position": position,
                    "operation": event.get("operation") or "NOT_OBSERVED",
                    "calculation_id": event.get("calculation_id") or "NOT_OBSERVED",
                })
        if tool != "query":
            continue
        row = by_invocation.setdefault(invocation_id, {
            "invocation_id": invocation_id, "query_count": 0,
            "result_bytes_observed": 0, "result_bytes_missing_count": 0,
            "repeated_evidence_ids": [], "first_error_code": None,
        })
        if event.get("event_type") == "mcp_tool_error":
            if row["first_error_code"] is None:
                row["first_error_code"] = str(event.get("error", "UNKNOWN")).split(":", 1)[0]
            continue
        if event.get("event_type") != "mcp_tool_result":
            continue
        row["query_count"] += 1
        response_bytes = event.get("output_bytes")
        if type(response_bytes) is int and response_bytes >= 0:
            row["result_bytes_observed"] += response_bytes
        else:
            row["result_bytes_missing_count"] += 1
        seen = row.setdefault("_seen", set())
        for evidence_id in event.get("evidence_ids", []):
            if not isinstance(evidence_id, str):
                continue
            if evidence_id in seen and evidence_id not in row["repeated_evidence_ids"]:
                row["repeated_evidence_ids"].append(evidence_id)
            seen.add(evidence_id)
    for row in by_invocation.values():
        row.pop("_seen", None)
        row["repeated_evidence_ids"].sort()
    return {"status": "OBSERVED", "by_invocation": [
        by_invocation[key] for key in sorted(by_invocation)
    ], "by_tool": [by_tool[key] for key in sorted(by_tool)]}


def _cost_diagnostics(run_dir: Path, queries: Mapping[str, Any]) -> dict[str, Any]:
    """Read existing delivery events; bytes never substitute for token usage."""
    deliveries = []
    for relative in ("invocation/subagent-events.jsonl", "invocation/skeptic/subagent-events.jsonl",
                     "invocation/cio-stop-events.jsonl"):
        hook_path = run_dir / relative
        if not hook_path.is_file():
            continue
        for position, line in enumerate(hook_path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            event = json.loads(line)
            try:
                verify_legacy_envelope_hash(event, hash_field="event_hash", location=str(hook_path))
            except HashContractError as exc:
                raise ValueError(f"RESEARCH_AUDIT_DELIVERY_HASH_MISMATCH:{exc}") from exc
            main_start = event.get("hook_event_name") == "SessionStart" and event.get("execution_context") == "MAIN_THREAD"
            if event.get("hook_event_name") != "SubagentStart" and not main_start:
                continue
            binding = event.get("context_binding", {})
            diagnostics = event.get("delivery_diagnostics", binding.get("delivery_diagnostics"))
            if not main_start and binding.get("status") not in {"DELIVERED", "EMITTED"}:
                continue
            deliveries.append({
                "event_path": relative, "execution_context": "MAIN_THREAD" if main_start else "SUBAGENT",
                "event_position": position, "event_hash": event["event_hash"],
                "agent": "runtime_cio" if main_start else event.get("agent_type"),
                "child_session_id": event.get("child_session_id"),
                "invocation_id": binding.get("invocation_id"),
                "diagnostics": diagnostics,
                "measurement_status": "OBSERVED" if isinstance(diagnostics, Mapping) else "NOT_OBSERVED",
            })
    parent = _observed_parent_usage(run_dir)
    # Canonical responses and reference-transport replacements describe two
    # representations of ONE response. Keep both columns, never add them.
    return {
        "scope": "OBSERVED_DELIVERY_AND_QUERY_REPRESENTATIONS_NOT_FULL_CHAIN_COST",
        "initial_contexts": deliveries,
        "query_representations": queries["by_invocation"],
        "tool_return_representations": queries["by_tool"],
        "byte_accounting": "CANONICAL_AND_MODEL_TRANSPORT_ARE_NOT_ADDITIVE",
        "token_usage": None, "token_usage_status": "NOT_OBSERVED",
        "parent_usage": parent, "parent_usage_status": parent["status"] if parent else "NOT_OBSERVED",
        "child_usage": None, "child_usage_status": "NOT_OBSERVED",
        "total_cost": None, "total_cost_status": "NOT_OBSERVED",
        "baseline_scope": "SAME_FROZEN_REPRESENTATION_WHEN_MEASURED_NOT_MODEL_BENCHMARK",
    }


def _observed_parent_usage(run_dir: Path) -> dict[str, Any] | None:
    """读取父 CLI 实际可见的每 turn 使用量；不将其当子会话或全链费用。"""
    path = run_dir / "invocation/codex-events.jsonl"
    if not path.is_file():
        return None
    from .execution_proof import ExecutionProofError, _public_codex_telemetry
    turns = []
    for position, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        event = json.loads(line)
        if event.get("type") != "turn.completed":
            continue
        try:
            measured = _public_codex_telemetry([event], latency_ms=None, llm_calls=None)
        except ExecutionProofError as exc:
            measured = {"status": "NOT_OBSERVED", "reason_code": str(exc).split(":", 1)[0],
                        "input_tokens": None, "output_tokens": None, "cached_tokens": None}
        turns.append({"event_position": position, "event_hash": canonical_hash(event), **measured})
    if not turns:
        return None
    return {"scope": "PARENT_CLI_REPORTED_PER_TURN_NOT_CHILD_OR_FULL_CHAIN",
            "source_path": "invocation/codex-events.jsonl", "source_hash": file_hash(path),
            "cache_accounting": "SUBSET_OF_INPUT_TOKENS", "by_turn": turns,
            "status": "AVAILABLE" if all(row["status"] == "AVAILABLE" for row in turns) else "MISSING_TELEMETRY",
            **{key: sum(row[key] for row in turns) if all(row[key] is not None for row in turns) else None
               for key in ("input_tokens", "output_tokens", "cached_tokens")},
            "llm_calls": None, "total_cost": None}


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


def _allowed_catalogs(run_dir: Path, gate: Mapping[str, Any]) -> tuple[dict[str, dict[str, Any]], str]:
    """读实际绑定的任务允许目录；允许访问不冒称 Agent 已读取。"""
    index = _read(run_dir / "research/dispatch-index.json")
    manifest = _read(run_dir / "run_manifest.json")
    if not index or not manifest or "index_hash" not in index:
        return {}, "NOT_VERIFIED"
    if index.get("schema_version") not in {
        "multidimensional-research-dispatch/2.0.0", "multidimensional-research-dispatch/2.1.0",
    }:
        # 此投影只读取已有八维任务允许目录，不伪造其它阶段的加载或访问证明。
        return {}, "NOT_PROJECTED_FOR_THIS_DISPATCH_VERSION"
    if (index["index_hash"] != canonical_hash({k: v for k, v in index.items() if k != "index_hash"})
            or index.get("run_id") != gate.get("run_id")
            or manifest.get("dispatch_index_hash") != index["index_hash"]
            or manifest.get("gate_hash") != gate.get("bundle_hash")):
        raise ValueError("RESEARCH_AUDIT_CATALOG_BINDING_INVALID")
    allowed = {fact["evidence_id"] for fact in gate.get("allowed_evidence", [])}
    catalogs = {}
    for task in index.get("tasks", []):
        invocation = task.get("invocation_id")
        ids = task.get("allowed_evidence_ids")
        if (not isinstance(invocation, str) or invocation in catalogs
                or not isinstance(ids, list) or any(not isinstance(item, str) for item in ids)
                or not set(ids) <= allowed):
            raise ValueError("RESEARCH_AUDIT_CATALOG_SCOPE_INVALID")
        catalogs[invocation] = {"capability": task.get("capability"), "evidence": set(ids)}
    return catalogs, "HASH_VERIFIED_ALLOWED_CATALOG"


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
    event_integrity: dict[str, str] = {}
    for source in event_sources:
        present, entries, integrity = _events(source)
        event_file_presence[str(source)] = present
        event_integrity[str(source)] = integrity
        if set(events) & set(entries):
            raise ValueError("RESEARCH_AUDIT_INVOCATION_COLLISION")
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
                    "market-breadth-calculation/1.0.0",
                }:
                    references[invocation]["attachment_parents"].update(
                        evidence_id for evidence_id in artifact.get("evidence_fact_ids", [])
                        if isinstance(evidence_id, str)
                    )
        report_list.append({
            "report_id": value.get("report_id"), "invocation_id": invocation,
            "capability": value.get("capability", "COMPANY_RESEARCH" if "equity-research" in item["path"] else None),
            "status": value.get("status"), "sufficiency": value.get("sufficiency"),
            "evaluation_status": value.get("evaluation_status"),
            "report_hash": value.get("report_hash"),
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
    routing = coverage.get("capability_routing", {}).get("dataset_observations", [])
    catalogs, catalog_status = _allowed_catalogs(run_dir, gate)
    observed: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    observed_dataset_by_id: dict[str, str] = {}
    for provider in coverage.get("providers", []):
        for observation in provider.get("dataset_observations", []):
            dataset = observation.get("dataset")
            if isinstance(dataset, str):
                observed[(provider.get("provider", ""), dataset)].append(observation)
                for evidence_id in observation.get("evidence_ids", []):
                    if isinstance(evidence_id, str):
                        previous = observed_dataset_by_id.setdefault(evidence_id, dataset)
                        if previous != dataset:
                            raise ValueError("RESEARCH_AUDIT_DATASET_BINDING_AMBIGUOUS")
    datasets: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for fact in [*by_id.values(), *excluded.values()]:
        field = fact.get("semantic_field") or "unknown"
        observed_dataset = observed_dataset_by_id.get(fact["evidence_id"])
        declared_dataset = fact.get("dataset") or (fact.get("metadata") or {}).get("dataset")
        if observed_dataset and declared_dataset and observed_dataset != declared_dataset:
            raise ValueError("RESEARCH_AUDIT_DATASET_BINDING_MISMATCH")
        dataset = observed_dataset or fact_dataset(fact)
        source = fact.get("source_id") or "unknown"
        datasets[(str(dataset), str(source), str(field))].append(fact)
    rows = []
    for (dataset, source, field), facts in sorted(datasets.items()):
        ids = {item["evidence_id"] for item in facts}
        allowed = ids & by_id.keys()
        delivered = {inv: sorted(ids & record["evidence"]) for inv, record in events.items() if ids & record["evidence"]}
        catalog_allowed = {inv: sorted(ids & record["evidence"]) for inv, record in catalogs.items()
                           if ids & record["evidence"]}
        direct = {inv: sorted(ids & refs) for inv, refs in direct_by_invocation.items() if ids & refs}
        indirect = {inv: sorted(ids & refs) for inv, refs in indirect_by_invocation.items() if ids & refs}
        attachment = {inv: sorted(ids & refs) for inv, refs in attachment_by_invocation.items() if ids & refs}
        if direct or indirect:
            use_status = "REPORT_REFERENCED"
        elif attachment:
            use_status = "ATTACHMENT_PARENT_LINKED"
        elif delivered:
            use_status = "DELIVERED_UNREFERENCED"
        elif not all(state == "HASH_VERIFIED" for state in event_integrity.values()):
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
            "domain": dataset_domain(dataset),
            "mapping_status": "MAPPED" if dataset_domain(dataset) != "UNMAPPED" else "UNMAPPED",
            "allowed_consumers": list(dataset_consumers(dataset)),
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
            "queried_by_invocation": delivered,
            "catalog_allowed_by_invocation": catalog_allowed,
            "routing_observations": [dict(item) for item in routing if item.get("dataset") == dataset],
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
            dataset_domain(item["dataset"]),
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
    handoff = _read(run_dir / "audit/portfolio-handoff.json") or {}
    holding_ids = {
        item.get("security_id") for item in handoff.get("portfolio", {}).get("positions", [])
        if isinstance(item, Mapping)
    }
    dimension_rows = []
    execution_proof = _read(run_dir / "research/execution-proof.json") or {}
    dispatch = _read(run_dir / "research/dispatch-index.json") or {}
    invocations_by_capability: dict[str, set[str]] = defaultdict(set)
    for item in [*dispatch.get("tasks", []), *report_list]:
        if isinstance(item.get("invocation_id"), str) and isinstance(item.get("capability"), str):
            invocations_by_capability[item["capability"]].add(item["invocation_id"])
    failed_capabilities = set()
    if execution_proof:
        if (execution_proof.get("proof_hash") != canonical_hash({
                k: v for k, v in execution_proof.items() if k != "proof_hash"})
                or execution_proof.get("run_id") != gate.get("run_id")
                or execution_proof.get("gate_hash") != gate.get("bundle_hash")):
            raise ValueError("RESEARCH_AUDIT_EXECUTION_PROOF_BINDING_INVALID")
        failed_ids = {
            item["task_id"] for item in execution_proof.get("failed_tasks", [])
            if item.get("failure_source") == "SUBAGENT_STOP_OUTPUT_VALIDATION"
        }
        failed_capabilities = {t["capability"] for t in dispatch.get("tasks", [])
                               if t.get("task_id") in failed_ids}
    for capability, input_datasets in EIGHT_DIMENSION_INPUTS.items():
        invocations = invocations_by_capability[capability]
        matching = [row for row in rows if capability in row["allowed_consumers"]
                    or any(inv in invocations for key in (
                        "catalog_allowed_by_invocation", "queried_by_invocation",
                        "direct_refs_by_invocation", "indirect_refs_by_invocation",
                    ) for inv in row[key])]
        matching_reports = [item for item in report_list if item["capability"] == capability]
        statuses = sorted({item["status"] for item in matching_reports if item["status"]})
        sufficiencies = sorted({item["sufficiency"] for item in matching_reports
                                if item["sufficiency"]})
        if not matching_reports:
            research_coverage = ("FAILED_NO_VALID_REPORT" if capability in failed_capabilities else "NOT_RUN")
        elif "INSUFFICIENT_EVIDENCE" in statuses or "INSUFFICIENT" in sufficiencies:
            research_coverage = "INSUFFICIENT_EVIDENCE"
        elif any(status in {"PARTIAL", "LOW_CONFIDENCE", "SOURCE_LIMITED",
                            "FAILED", "TIMEOUT"} for status in statuses) \
                or "PARTIAL" in sufficiencies:
            research_coverage = "PARTIAL_OR_FAILED"
        else:
            research_coverage = "CONTENT_REVIEW_REQUIRED"
        selected_peer_ids = {item["evidence_id"] for item in by_id.values()
                             if holding_ids and item.get("security_id") not in holding_ids | {"US:MARKET"}
                             and observed_dataset_by_id.get(item["evidence_id"]) in input_datasets}
        dimension_rows.append({
            "capability": capability,
            "expected_datasets": list(input_datasets),
            "gate_allowed_count": sum(item["gate_allowed_count"] for item in matching),
            "catalog_allowed_count": (len(set().union(*(set(ids) for item in matching
                for inv, ids in item["catalog_allowed_by_invocation"].items() if inv in invocations)))
                if catalog_status == "HASH_VERIFIED_ALLOWED_CATALOG" else None),
            "queried_count": len(set().union(*(set(ids) for item in matching
                for inv, ids in item["queried_by_invocation"].items() if inv in invocations))),
            "direct_or_indirect_reference_count": len(set().union(*(
                set(ids) for item in matching for field in (
                    "direct_refs_by_invocation", "indirect_refs_by_invocation"
                ) for inv, ids in item[field].items() if inv in invocations))),
            "peer_gate_allowed_count": len(selected_peer_ids),
            "report_statuses": statuses,
            "report_sufficiencies": sufficiencies,
            "research_coverage": research_coverage,
        })
    queries = _query_diagnostics(run_dir)
    return {
        "schema_version": "research-consumption-audit/1.0.0",
        "run_id": gate.get("run_id"), "decision_cutoff": gate.get("decision_cutoff"),
        "gate_file_hash": file_hash(gate_path), "gate_hash": gate.get("bundle_hash"),
        "source_binding": {
            "company": "VERIFIED" if company_dir is not None else "NOT_REQUESTED",
            "cio": "VERIFIED" if cio_dir is not None else "NOT_REQUESTED",
        },
        "event_file_presence": event_file_presence, "event_integrity": event_integrity,
        "catalog_status": catalog_status,
        "unmapped_datasets": sorted({row["dataset"] for row in rows if row["mapping_status"] == "UNMAPPED"}),
        "expected_core_items": CORE_ITEMS,
        "query_diagnostics": queries,
        "cost_diagnostics": _cost_diagnostics(run_dir, queries),
        "provider_observations": [
            {"provider": provider, "dataset": dataset, "observations": items}
            for (provider, dataset), items in sorted(observed.items())
        ],
        "coverage_items": coverage_items, "dimension_rows": dimension_rows,
        "rows": rows, "reports": report_list,
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
    lines.extend(["## 八维研究", ""])
    for item in audit["dimension_rows"]:
        lines.append(
            f"- {item['capability']}：Gate {item['gate_allowed_count']} 项，"
            f"查询 {item['queried_count']} 项，直接/间接引用 {item['direct_or_indirect_reference_count']} 项，"
            f"报告覆盖 {item['research_coverage']}。"
        )
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
    if audit.get("unmapped_datasets"):
        lines.append("未登记数据集（UNMAPPED）：" + ", ".join(audit["unmapped_datasets"])
                     + "；保留原件并明确未映射，不据此声称路由闭合。")
    return "\n".join(lines) + "\n"
