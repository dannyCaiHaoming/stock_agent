"""正式研究的冻结正文消费；目录与实际读取分开，不获取外部来源。"""
from __future__ import annotations

import copy
import json
from typing import Mapping

from product.mcp.provenance import parse_timestamp
from product.runtime.hashing import canonical_hash
from product.runtime.schema_validation import validate_schema_instance
from product.tools.report_contracts import SCHEMA_ROOT
from product.tools.research import ResearchAccessError, MAX_QUERY_BYTES, _read_json

DOCUMENT_CAPABILITIES = {
    "RESEARCH_REPORT_DISCOVERY": "RESEARCH_REPORT",
    "MACRO_RESEARCH_DISCOVERY": "MACRO_CONTEXT",
    "MARKET_RESEARCH_DISCOVERY": "MARKET_STATE",
}


def freeze_documents(documents, *, security_id, cutoff):
    schema = json.loads((SCHEMA_ROOT / "research-dimension-report-v2.schema.json").read_text())
    document_schema = {**schema["$defs"]["document"], "$defs": schema["$defs"]}
    metadata, bodies = [], {}
    for document in documents:
        value = copy.deepcopy(dict(document))
        sections = value.pop("sections", None)
        value.pop("schema_version", None)
        value.pop("record_hash", None)
        value.pop("candidate_id", None)
        sid = value.pop("security_id", security_id)
        value.pop("untrusted_content", None)
        if value.get("interest_disclosure") == "UNKNOWN":
            value["interest_disclosure"] = {"status": "UNKNOWN", "statement": None, "location": None}
        validate_schema_instance(value, document_schema)
        if sid != security_id:
            raise ResearchAccessError("NATIVE_RESEARCH_DOCUMENT_TARGET_INVALID")
        if any(parse_timestamp(value[key]) > parse_timestamp(cutoff) for key in ("published_at", "as_of", "retrieved_at")):
            raise ResearchAccessError("NATIVE_RESEARCH_DOCUMENT_AFTER_CUTOFF")
        if value["verification_status"] == "BODY_VERIFIED":
            if (not isinstance(sections, list) or not sections
                    or any(not isinstance(s, Mapping) or not isinstance(s.get("text"), str) or not s["text"]
                           or not isinstance(s.get("section"), str) for s in sections)
                    or [s["section"] for s in sections] != value["locations"]):
                raise ResearchAccessError("NATIVE_RESEARCH_DOCUMENT_BODY_REQUIRED")
            bodies[value["document_id"]] = copy.deepcopy(sections)
        metadata.append(value)
    if len({d["document_id"] for d in metadata}) != len(metadata):
        raise ResearchAccessError("NATIVE_RESEARCH_DOCUMENT_AMBIGUOUS")
    return metadata, bodies


def preparation_documents(reports, *, capability, input_binding, gate_hash, security_id, cutoff):
    from product.tools.report_reading import validate_report
    documents = []
    for report in reports:
        validate_report(report, input_binding=input_binding, gate_hash=gate_hash, security_id=security_id, cutoff=cutoff)
        if DOCUMENT_CAPABILITIES.get(report["capability"]) != capability:
            raise ResearchAccessError("NATIVE_MATERIAL_DEPENDENCY_CAPABILITY_INVALID")
        if report["research"]["status"] == "BLOCKED_CONFIGURATION":
            raise ResearchAccessError("NATIVE_MATERIAL_DEPENDENCY_BLOCKED_CONFIGURATION")
        documents.extend(copy.deepcopy((report.get("material_support") or {}).get("documents", [])))
    return documents


def read_documents(tools, *, document_ids):
    task, _gate = tools._authorize()
    if "read_documents" not in task["permissions"]:
        raise ResearchAccessError("NATIVE_RESEARCH_DOCUMENT_READ_FORBIDDEN")
    if (not isinstance(document_ids, list) or not document_ids or len(document_ids) > 5
            or any(not isinstance(ref, str) for ref in document_ids)
            or len(document_ids) != len(set(document_ids))):
        raise ResearchAccessError("NATIVE_RESEARCH_DOCUMENT_SELECTION_INVALID")
    bodies = task.get("document_bodies", {})
    if not set(document_ids) <= set(bodies):
        raise ResearchAccessError("NATIVE_RESEARCH_DOCUMENT_NOT_ALLOWED")
    result = {"documents": [{"document": copy.deepcopy(next(d for d in task["allowed_documents"] if d["document_id"] == ref)),
                              "sections": copy.deepcopy(bodies[ref]), "untrusted_content": True}
                             for ref in document_ids]}
    if len(json.dumps(result, ensure_ascii=False).encode()) > MAX_QUERY_BYTES:
        raise ResearchAccessError("NATIVE_RESEARCH_DOCUMENT_RESPONSE_TOO_LARGE")
    tools._record(task, "read_documents", {"document_ids": document_ids}, result)
    return result


def read_document_ids(tools):
    task, _gate = tools._authorize()
    result = set()
    for path in (tools.root / "tools").glob("*.json"):
        event = _read_json(path)
        if (event.get("event_hash") != canonical_hash({k: v for k, v in event.items() if k != "event_hash"})
                or event.get("task_hash") != task["task_hash"]):
            raise ResearchAccessError("NATIVE_RESEARCH_TOOL_RECORD_INVALID")
        if event["tool"] == "read_documents":
            result.update(event["document_ids"])
    return result
