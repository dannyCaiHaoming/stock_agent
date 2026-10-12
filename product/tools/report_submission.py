"""有界业务报告提交与精确回执；不捕获或管理宿主生命周期。"""
from __future__ import annotations

import copy
import fcntl
import json
import os
from pathlib import Path
import re
import secrets
from typing import Any, Mapping

from product.tools.research_scope import RESEARCH_CAPABILITIES
from product.runtime.hashing import canonical_hash
from product.runtime.schema_validation import schema_issue_locations
from product.tools.report_contracts import semantic_schema, validate_semantic_draft
from product.tools.revision import _apply, located_paths
from product.tools.research import ResearchAccessError, ResearchTools, _read_json, _write_json, _utc_now

VERSION = "native-research-report/1.0.0"
MAX_DRAFT_BYTES = 256 * 1024
REF_PATTERN = re.compile(r"r[12]\.[A-Za-z0-9_-]{24}")


def _directory(root: Path, name: str) -> Path:
    path = root/name
    if path.is_symlink():
        raise ResearchAccessError("NATIVE_RESEARCH_PATH_UNSAFE")
    path.mkdir(mode=0o700, exist_ok=True)
    return path


def calculation_catalog(tools: ResearchTools) -> dict[str, dict[str, Any]]:
    task, _gate = tools._authorize()
    directory = tools.root/"calculations"
    if directory.is_symlink():
        raise ResearchAccessError("NATIVE_RESEARCH_PATH_UNSAFE")
    from product.tools.precomputed import statistics_catalog
    result = statistics_catalog(task, root=tools.root)
    for path in sorted(directory.glob("calculation-*.json")):
        record = _read_json(path)
        identifier = record.get("calculation_id")
        if path.name != f"{identifier}.json" or not set(record.get("evidence_ids", [])) <= set(task["allowed_evidence_ids"]):
            raise ResearchAccessError("NATIVE_RESEARCH_CALCULATION_BINDING_INVALID")
        # Every successful object has a matching actual tool receipt.
        events = tools.root/"tools"
        matched = False
        for event_path in events.glob("*.json"):
            event = _read_json(event_path)
            if (event.get("event_hash") != canonical_hash({k: v for k, v in event.items() if k != "event_hash"})
                    or event.get("task_hash") != task["task_hash"]):
                raise ResearchAccessError("NATIVE_RESEARCH_TOOL_RECORD_INVALID")
            if event.get("tool") == "calculate" and event.get("output_hash") == canonical_hash(record):
                matched = True
        if not matched:
            raise ResearchAccessError("NATIVE_RESEARCH_CALCULATION_NOT_EXECUTED")
        values: list[tuple[str, Any, str | None]] = []
        if "value" in record:
            values.append(("value", record["value"], "ratio"))
        for index, item in enumerate(record.get("conversions", [])):
            values.append((f"conversions/{index}/converted_value", item["converted_value"], f"USD/{item['target_scale']}"))
        for field, changes in record.get("changes", {}).items():
            for metric, value in changes.items():
                values.append((f"changes/{field}/{metric}", value,
                               "ratio" if metric == "relative_change" else field))
        for location, value, unit in values:
            binding = {"task_hash": task["task_hash"], "calculation_hash": canonical_hash(record), "result_path": location}
            ref = f"k.{task['task_hash'][:12]}.{canonical_hash(binding)[:24]}"
            result[ref] = {
                "calculation_ref": ref,
                "calculation": {"calculation_id": f"calculation-{canonical_hash(binding)[:24]}",
                    "method": f"{record['operation']}:{location}", "value": value, "unit": unit,
                    "input_evidence_refs": copy.deepcopy(record["evidence_ids"]),
                    "artifact_ref": f"calculations/{path.name}"},
                "receipt_hash": canonical_hash(record),
            }
    return result


def queried_evidence(tools: ResearchTools) -> set[str]:
    task, _gate = tools._authorize()
    result = set()
    directory = tools.root/"tools"
    if directory.is_symlink():
        raise ResearchAccessError("NATIVE_RESEARCH_PATH_UNSAFE")
    for path in directory.glob("*.json"):
        event = _read_json(path)
        if (event.get("event_hash") != canonical_hash({k: v for k, v in event.items() if k != "event_hash"})
                or event.get("task_hash") != task["task_hash"]):
            raise ResearchAccessError("NATIVE_RESEARCH_TOOL_RECORD_INVALID")
        if event.get("tool") == "query":
            result.update(event["evidence_ids"])
    if not result <= set(task["allowed_evidence_ids"]):
        raise ResearchAccessError("NATIVE_RESEARCH_QUERY_SCOPE_INVALID")
    return result


def _expand_choices(tools: ResearchTools, draft: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    task, _gate = tools._authorize()
    value = copy.deepcopy(dict(draft))
    capability = task["capability"]
    if capability not in {"COMPANY_RESEARCH", "FIXTURE_COMPANY_RESEARCH", *RESEARCH_CAPABILITIES}:
        return value, []
    catalog = calculation_catalog(tools)
    choices = value.pop("calculation_selections", [])
    claims = {claim["claim_id"]: claim for claim in value["claims"]}
    if len(claims) != len(value["claims"]):
        raise ValueError("NATIVE_RESEARCH_CLAIM_DUPLICATE")
    for claim in claims.values():
        claim["calculation_refs"] = []
    selected, seen = [], set()
    for choice in choices:
        ref = choice["calculation_ref"]
        if ref not in catalog or ref in seen:
            raise ValueError("NATIVE_RESEARCH_CALCULATION_SELECTION_INVALID")
        seen.add(ref)
        entry = catalog[ref]
        for claim_id in choice["claim_ids"]:
            if claim_id not in claims:
                raise ValueError("NATIVE_RESEARCH_CALCULATION_CLAIM_INVALID")
            claims[claim_id]["calculation_refs"].append(entry["calculation"]["calculation_id"])
        selected.append(copy.deepcopy(entry))
    value["artifact_refs"] = [item["calculation"]["calculation_id"] for item in selected]
    if capability in RESEARCH_CAPABILITIES:
        value["calculations"] = [item["calculation"] for item in selected]
        value["artifact_refs"] = [item["calculation"]["artifact_ref"] for item in selected]
        choices = value.pop("document_selections", [])
        documents = task.get("allowed_documents", [])
        by_id = {item["document_id"]: item for item in documents}
        if len(by_id) != len(documents) or len(choices) != len(set(choices)) or not set(choices) <= set(by_id):
            raise ValueError("NATIVE_RESEARCH_DOCUMENT_SELECTION_INVALID")
        from product.tools.documents import read_document_ids
        if not set(choices) <= read_document_ids(tools):
            raise ValueError("NATIVE_RESEARCH_DOCUMENT_NOT_READ")
        value["documents"] = [copy.deepcopy(by_id[ref]) for ref in choices]
    return value, selected


def _findings(tools: ResearchTools, draft: dict[str, Any], error: ValueError) -> list[dict[str, str]]:
    task, gate = tools._authorize()
    if str(error).split(":", 1)[0] == "EQUITY_RESEARCH_FACT_PERIOD_LINEAGE_INCOMPLETE":
        from product.council.research_output import _validate_fact_period_lineage
        evidence = {fact["evidence_id"]: fact for fact in gate["allowed_evidence"]}
        findings = []
        for index, claim in enumerate(draft["claims"]):
            try:
                _validate_fact_period_lineage({"claims": [claim]}, evidence_by_id=evidence)
            except ValueError as exc:
                if str(exc).split(":", 1)[0] != "EQUITY_RESEARCH_FACT_PERIOD_LINEAGE_INCOMPLETE":
                    raise
                findings.append({"code": "EQUITY_RESEARCH_FACT_PERIOD_LINEAGE_INCOMPLETE",
                                 "path": f"/claims/{index}/statement"})
        return findings[:32]
    findings = schema_issue_locations(draft, semantic_schema(task["capability"]))
    allowed, queried = set(task["allowed_evidence_ids"]), queried_evidence(tools)

    def walk(value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                child = path + "/" + key.replace("~", "~0").replace("/", "~1")
                if key in {"evidence_refs", "counter_evidence_refs"} and isinstance(item, list):
                    for index, ref in enumerate(item):
                        if isinstance(ref, str) and (ref not in allowed or ref not in queried):
                            findings.append({"code": "NATIVE_RESEARCH_EVIDENCE_NOT_QUERIED", "path": f"{child}/{index}"})
                else:
                    walk(item, child)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                walk(item, f"{path}/{index}")
    walk(draft)
    # Only complete validator locators can open a revision; never guess from prose.
    match = re.search(r"claims\[(\d+)\]", str(error))
    if match:
        index = int(match.group(1))
        if index < len(draft.get("claims", [])):
            findings.append({"code": str(error).split(":", 1)[0], "path": f"/claims/{index}"})
    return findings[:32]


def submit(tools: ResearchTools, *, draft: dict[str, Any]) -> dict[str, Any]:
    task, gate = tools._authorize()  # Before any draft slot or lock is created.
    if "submit" not in task["permissions"]:
        raise ResearchAccessError("NATIVE_RESEARCH_SUBMISSION_FORBIDDEN")
    if not isinstance(draft, dict) or len(json.dumps(draft, ensure_ascii=False, allow_nan=False).encode()) > MAX_DRAFT_BYTES:
        raise ValueError("NATIVE_RESEARCH_DRAFT_INVALID")
    directory = _directory(tools.root, "submissions")
    lock_path = directory/".lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ResearchAccessError("NATIVE_RESEARCH_SUBMISSION_BUSY") from exc
        tools._authorize()
        first_path, second_path = directory/"1.json", directory/"2.json"
        if second_path.exists():
            raise ValueError("NATIVE_RESEARCH_SUBMISSION_EXHAUSTED")
        base, revision_error = None, None
        if first_path.exists():
            base = _read_json(first_path)
            risk_revision = ((base.get("report") or {}).get("fixture_decision") or {}).get("terminal_state") == "ONE_CIO_REVISION_REQUIRED"
            if (base.get("accepted") is True and not risk_revision) or not base.get("allowed_paths"):
                raise ValueError("NATIVE_RESEARCH_SUBMISSION_CLOSED")
            if base["content_hash"] != canonical_hash({k: v for k, v in base.items() if k != "content_hash"}):
                raise ValueError("NATIVE_RESEARCH_REVISION_BASE_DRIFT")
            number = 2
            try:
                if set(draft) != {"base_draft_ref", "changes"} or draft["base_draft_ref"] != base["draft_ref"]:
                    raise ValueError("NATIVE_RESEARCH_REVISION_BASE_INVALID")
                candidate = _apply(base["draft"], draft["changes"], base["allowed_paths"])
            except ValueError as exc:
                candidate, revision_error = None, exc
        else:
            if {"base_draft_ref", "changes"} & draft.keys():
                raise ValueError("NATIVE_RESEARCH_REVISION_BASE_INVALID")
            candidate, number = copy.deepcopy(draft), 1
        reference = f"r{number}." + secrets.token_urlsafe(18)
        accepted, validation_error, paths, report = False, None, [], None
        identity_fields = {"run_id", "invocation_id", "agent", "model", "role", "schema_version", "skill_execution", "task_id", "task_hash"}
        identity_conflict = isinstance(candidate, dict) and bool(identity_fields & candidate.keys())
        try:
            if revision_error is not None:
                raise revision_error
            if identity_conflict:
                raise ValueError("NATIVE_RESEARCH_IDENTITY_FIELD_FORBIDDEN")
            from product.runtime.schema_validation import validate_schema_instance
            validate_schema_instance(candidate, semantic_schema(task["capability"]))
            expanded, selected = _expand_choices(tools, candidate)
            calculation_ids = [item["calculation"]["calculation_id"] for item in selected]
            refs = validate_semantic_draft(candidate, capability=task["capability"],
                allowed_evidence_ids=task["allowed_evidence_ids"], queried_evidence_ids=queried_evidence(tools),
                calculation_ids=calculation_ids, assembled=expanded,
                allowed_documents=task.get("allowed_documents", []),
                known_claim_ids=task.get("known_claim_ids", []),
                calculation_evidence_ids=task.get("calculation_evidence_ids", []))
            material_support = None
            from product.tools.material_contracts import MATERIAL_ROLES
            if task["capability"] in MATERIAL_ROLES:
                from product.tools.materials import validate_selection
                material_support = validate_selection(tools, expanded)
            if task["capability"] == "RESEARCH_SYNTHESIS":
                from product.tools.report_reading import validate_synthesis, read_report_ids
                validate_synthesis(expanded, reports=task["dependency_reports"],
                                   read_report_ids=read_report_ids(tools))
            risk_support, fixture_decision = None, None
            if task["capability"] == "FIXTURE_COUNCIL_DECISION":
                from product.tools.fixture_business import fixture_risk
                expanded, risk_support, fixture_decision, paths = fixture_risk(tools, expanded, attempt=number)
            if task["capability"] == "COMPANY_RESEARCH":
                from product.council.research_output import _validate_fact_period_lineage
                _validate_fact_period_lineage(expanded, evidence_by_id={f["evidence_id"]: f for f in gate["allowed_evidence"]})
            if task["capability"] == "INDEPENDENT_FIRST_PASS" and task["security"]["security_id"] not in expanded["scope"]:
                raise ValueError("NATIVE_RESEARCH_SKEPTIC_SCOPE_INVALID")
            timestamp = _utc_now()
            report = {
                "schema_version": VERSION, "report_id": f"report-{secrets.token_hex(12)}",
                "task_id": task["task_id"], "task_hash": task["task_hash"],
                "role_scope": task["role"], "capability": task["capability"],
                "input_binding": copy.deepcopy(task["input_binding"]), "gate_hash": task["gate_hash"],
                "security": copy.deepcopy(task["security"]), "decision_cutoff": task["decision_cutoff"],
                "security_ids": copy.deepcopy(task.get("security_ids", [task["security"]["security_id"]])),
                "research": expanded, "evidence_refs": sorted(refs),
                "calculation_support": selected, "material_support": material_support, "business_validation": "VALIDATED",
                "caller_authentication": "UNVERIFIED", "host_execution": "UNVERIFIED",
                "content_verdict": "NOT_REVIEWED", "advisory_only": True,
                "risk_status": risk_support["check"]["status"] if risk_support is not None else "NOT_RUN",
                "risk_support": {"result": risk_support, "source_id": "native-fixture-risk:"+task["task_id"],
                                 "as_of": task["decision_cutoff"], "retrieved_at": timestamp} if risk_support is not None else None,
                "fixture_decision": fixture_decision,
                "source_id": f"native-research-report:{task['task_id']}",
                "as_of": task["decision_cutoff"], "retrieved_at": timestamp,
            }
            report["report_hash"] = canonical_hash(report)
            accepted = True
        except ValueError as exc:
            validation_error = str(exc).split(":", 1)[0]
            if number == 1 and not identity_conflict:
                paths = located_paths(_findings(tools, candidate, exc), exact_fields=True)
                paths = [p for p in paths if p.split("/")[1] in semantic_schema(task["capability"])["properties"]]
        record = {
            "task_hash": task["task_hash"], "draft_ref": reference, "draft": candidate,
            "original_submission": copy.deepcopy(draft), "accepted": accepted,
            "validation_error": validation_error, "allowed_paths": paths,
            "base_draft_ref": base["draft_ref"] if base is not None else None,
            "report": report,
        }
        record["content_hash"] = canonical_hash(record)
        _write_json(directory/f"{number}.json", record)
        return {"draft_ref": reference, "accepted": accepted, "validation_error": validation_error,
                "allowed_paths": paths, "remaining_submissions": 2-number,
                "report_id": report["report_id"] if report is not None else None,
                "business_validation": "VALIDATED" if accepted else "REJECTED",
                "host_execution": "UNVERIFIED", "content_verdict": "NOT_REVIEWED"}


def read_submission(tools: ResearchTools, *, draft_ref: str) -> dict[str, Any]:
    task, _gate = tools._authorize()
    if not isinstance(draft_ref, str) or REF_PATTERN.fullmatch(draft_ref) is None:
        raise ValueError("NATIVE_RESEARCH_RECEIPT_INVALID")
    record = _read_json(tools.root/"submissions"/f"{draft_ref[1]}.json")
    if (record.get("draft_ref") != draft_ref or record.get("task_hash") != task["task_hash"]
            or record.get("content_hash") != canonical_hash({k: v for k, v in record.items() if k != "content_hash"})
            or record.get("accepted") is not True):
        raise ValueError("NATIVE_RESEARCH_RECEIPT_BINDING_INVALID")
    report = record["report"]
    if report.get("report_hash") != canonical_hash({k: v for k, v in report.items() if k != "report_hash"}):
        raise ValueError("NATIVE_RESEARCH_REPORT_HASH_INVALID")
    return copy.deepcopy(report)
