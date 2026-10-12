"""受限研究任务、资料查询与计算；没有模型启动或任务调度。"""
from __future__ import annotations

import copy
import json
import os
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from product.mcp.provenance import content_hash, parse_timestamp
from product.runtime.hashing import canonical_hash, canonical_json, legacy_envelope_hash
from product.tools.research_input import research_input_binding, research_subjects, validate_research_input, is_fixture
from product.tools.research_scope import CAPABILITY_BINDINGS, capability_tools, select_capability_facts
from product.tools.evidence import EvidenceTools
from product.tools.material_contracts import MATERIAL_ROLES, DISCOVERY_KINDS

VERSION = "native-research-task/1.0.0"
ADAPTER_VERSION = "native-research-tools/1.0.0"
SOURCE_ROOT = Path(__file__).resolve().parents[2]
ROLES = {
    "COMPANY_RESEARCH": "runtime_company_analyst",
    "INDEPENDENT_FIRST_PASS": "runtime_skeptic",
    "RESEARCH_SYNTHESIS": "runtime_cio",
    "FIXTURE_COMPANY_RESEARCH": "runtime_company_analyst",
    "FIXTURE_COUNCIL_DECISION": "runtime_cio",
    **{key: value[0] for key, value in CAPABILITY_BINDINGS.items()},
    **MATERIAL_ROLES,
}
MAX_QUERY_IDS = 64
MAX_QUERY_BYTES = 65536
_UNSET = object()


class ResearchAccessError(ValueError):
    pass


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _private_root(root: Path, *, create: bool = False) -> Path:
    root = Path(root).absolute()
    if any(part.is_symlink() for part in (root, *root.parents)):
        raise ResearchAccessError("NATIVE_RESEARCH_PATH_UNSAFE")
    resolved = root.resolve()
    if resolved.is_relative_to(SOURCE_ROOT):
        raise ResearchAccessError("NATIVE_RESEARCH_OUTPUT_MUST_BE_EXTERNAL")
    if create:
        resolved.mkdir(parents=True, mode=0o700, exist_ok=False)
    if not resolved.is_dir() or resolved.stat().st_mode & 0o077:
        raise ResearchAccessError("NATIVE_RESEARCH_DIRECTORY_PERMISSIONS_INVALID")
    return resolved


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.is_symlink():
        raise ResearchAccessError("NATIVE_RESEARCH_PATH_UNSAFE")
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _read_json(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077:
        raise ResearchAccessError("NATIVE_RESEARCH_FILE_PERMISSIONS_INVALID")
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ResearchAccessError("NATIVE_RESEARCH_ARTIFACT_TOO_LARGE")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ResearchAccessError("NATIVE_RESEARCH_OBJECT_REQUIRED")
    return value


def validate_gate(gate: Mapping[str, Any]) -> None:
    if gate.get("bundle_hash") != legacy_envelope_hash(gate, hash_field="bundle_hash"):
        raise ResearchAccessError("NATIVE_RESEARCH_GATE_HASH_INVALID")
    facts, allowed = gate.get("allowed_evidence"), gate.get("allowed_evidence_ids")
    if not isinstance(facts, list) or not isinstance(allowed, list):
        raise ResearchAccessError("NATIVE_RESEARCH_GATE_INVALID")
    ids = [fact.get("evidence_id") for fact in facts if isinstance(fact, Mapping)]
    if len(ids) != len(facts) or len(set(ids)) != len(ids) or set(ids) != set(allowed):
        raise ResearchAccessError("NATIVE_RESEARCH_GATE_SCOPE_INVALID")
    excluded = gate.get("excluded_evidence_ids", [])
    if set(ids) & set(excluded):
        raise ResearchAccessError("NATIVE_RESEARCH_GATE_SCOPE_INVALID")
    cutoff = parse_timestamp(gate["decision_cutoff"])
    for fact in facts:
        if any(not fact.get(key) for key in ("source_id", "as_of", "retrieved_at")):
            raise ResearchAccessError("NATIVE_RESEARCH_PROVENANCE_REQUIRED")
        as_of, retrieved = parse_timestamp(fact["as_of"]), parse_timestamp(fact["retrieved_at"])
        if as_of > cutoff or retrieved > cutoff or retrieved < as_of:
            raise ResearchAccessError("NATIVE_RESEARCH_PIT_INVALID")
    canonical_hash(gate)  # Also rejects nonfinite or non-JSON values.


def _company_facts(facts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    # Reuse the existing Company data boundary, not a new investment filter.
    from product.tools.research_scope import is_company_research_evidence
    return [dict(fact) for fact in facts if is_company_research_evidence(fact)]


def prepare_task(
    root: Path, *, research_input: Mapping[str, Any], gate: Mapping[str, Any],
    security_id: str, capability: str, benchmark_id: str | None = None,
    research_question: str | None = None, allowed_documents: Sequence[Mapping[str, Any]] = (),
    dependency_reports: Sequence[Mapping[str, Any]] = (),
    connection_binding: Mapping[str, str] | None = None,
    public_research_authorized: bool = False, peer_candidate_pool: Mapping[str, Any] | None = None,
    peer_materialization: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """确定性授权输入；返回操作方私有凭据，不运行 Agent 或返回研究判断。"""
    validate_research_input(research_input)
    validate_gate(gate)
    if capability not in ROLES:
        raise ResearchAccessError("NATIVE_RESEARCH_CAPABILITY_UNSUPPORTED")
    if is_fixture(research_input):
        from product.tools.fixture_input import CAPABILITIES
        from product.runtime.evidence_gate import run_evidence_gate
        if capability not in CAPABILITIES or gate != run_evidence_gate(research_input["fixture"], run_id=research_input["request_id"]).artifact:
            raise ResearchAccessError("NATIVE_FIXTURE_GATE_OR_CAPABILITY_INVALID")
    elif capability.startswith("FIXTURE_"):
        raise ResearchAccessError("NATIVE_FIXTURE_INPUT_REQUIRED")
    subjects = research_subjects(research_input)
    securities = {item["security_id"]: item for item in subjects}
    target = securities.get(security_id)
    if target is None or target["asset_type"] != "COMMON_STOCK":
        raise ResearchAccessError("NATIVE_RESEARCH_TARGET_UNSUPPORTED")
    security_fields = ("security_id", "display_symbol", "display_name", "market", "asset_type", "identity_status")
    target = {key: copy.deepcopy(target.get(key)) for key in security_fields}
    if research_input.get("resolved_cutoff", gate["decision_cutoff"]) != gate["decision_cutoff"]:
        raise ResearchAccessError("NATIVE_RESEARCH_CUTOFF_MISMATCH")
    question = research_question or research_input.get("research_question")
    if not isinstance(question, str) or not question.strip():
        raise ResearchAccessError("NATIVE_RESEARCH_QUESTION_REQUIRED")
    peer_ids = []
    if peer_materialization is not None:
        if (peer_materialization.get("materialization_hash") != legacy_envelope_hash(peer_materialization, hash_field="materialization_hash")
                or peer_materialization.get("status") != "FROZEN"
                or peer_materialization.get("merged_gate_hash") != gate["bundle_hash"]
                or not set(peer_materialization.get("evidence_ids", [])) <= set(gate["allowed_evidence_ids"])):
            raise ResearchAccessError("NATIVE_MATERIAL_PEER_BINDING_INVALID")
        if capability in {"INDUSTRY_COMPARISON", "INDEPENDENT_FIRST_PASS", "RESEARCH_SYNTHESIS"}:
            peer_ids = sorted({item["materialized_security_id"] for item in peer_materialization["selected"]
                               if item["holding_security_id"] == security_id})
    facts = [fact for fact in gate["allowed_evidence"] if fact.get("security_id") in {
        security_id, "MARKET", "US:MARKET", "US:MACRO", benchmark_id, *peer_ids,
    }]
    if capability in {"COMPANY_RESEARCH", "FIXTURE_COMPANY_RESEARCH"}:
        selected = _company_facts(facts)
        permissions = ["query", "calculate"]
    elif capability in CAPABILITY_BINDINGS:
        selected = select_capability_facts(
            facts, capability=capability, security_ids=[security_id, *peer_ids], benchmark_id=benchmark_id,
        )
        permissions = ["query"]
        if "fixture_math.calculate" in capability_tools(capability):
            permissions.append("calculate")
    else:
        selected = [dict(fact) for fact in facts]
        permissions = ["query"]
    from product.tools.precomputed import prepare_statistics
    precomputed = prepare_statistics(gate, capability=capability, security_id=security_id, benchmark_id=benchmark_id)
    calculation_evidence_ids = sorted({ref for item in precomputed for ref in item["evidence_fact_ids"]})
    allowed = sorted(fact["evidence_id"] for fact in selected)
    if capability == "TECHNICAL_STRUCTURE":
        allowed = []
    if precomputed or capability == "TECHNICAL_STRUCTURE":
        permissions.append("calculation_catalog")
    if not allowed and capability not in CAPABILITY_BINDINGS:
        raise ResearchAccessError("NATIVE_RESEARCH_NO_AUTHORIZED_EVIDENCE")
    if type(public_research_authorized) is not bool:
        raise ResearchAccessError("NATIVE_MATERIAL_SOURCE_AUTHORIZATION_INVALID")
    peers = []
    if capability == "PEER_SELECTION":
        from product.mcp.live.peer_candidates import validate_peer_candidate_pool
        if peer_candidate_pool is None:
            raise ResearchAccessError("NATIVE_MATERIAL_PEER_POOL_REQUIRED")
        validate_peer_candidate_pool(peer_candidate_pool)
        if any(parse_timestamp(peer_candidate_pool[key]) > parse_timestamp(gate["decision_cutoff"]) for key in ("as_of", "retrieved_at")):
            raise ResearchAccessError("NATIVE_MATERIAL_PEER_POOL_AFTER_CUTOFF")
        groups = [group for group in peer_candidate_pool["groups"] if group["security_id"] == security_id]
        if len(groups) != 1:
            raise ResearchAccessError("NATIVE_MATERIAL_PEER_POOL_SCOPE_INVALID")
        peers = copy.deepcopy(groups[0]["candidates"])
    if capability in DISCOVERY_KINDS and public_research_authorized:
        permissions.extend(["search", "fetch"])
    from product.tools.documents import freeze_documents
    documents, document_bodies = freeze_documents(allowed_documents, security_id=security_id, cutoff=gate["decision_cutoff"])
    if document_bodies:
        if capability not in {"RESEARCH_REPORT", "MACRO_CONTEXT", "MARKET_STATE"}:
            raise ResearchAccessError("NATIVE_RESEARCH_DOCUMENT_CAPABILITY_INVALID")
        permissions.append("read_documents")
    from product.tools.report_reading import validate_dependencies, known_claims
    dependencies = validate_dependencies(dependency_reports, capability=capability,
        input_binding=research_input_binding(research_input), gate_hash=gate["bundle_hash"],
        security_id=security_id, cutoff=gate["decision_cutoff"])
    if dependencies:
        permissions.append("read_reports")
    token = secrets.token_urlsafe(32)
    created = _utc_now()
    shared_market = capability in {"MACRO_CONTEXT", "MARKET_STATE"}
    task_securities = [{key: copy.deepcopy(item.get(key)) for key in security_fields} for item in subjects if item["asset_type"] == "COMMON_STOCK"] if shared_market else [copy.deepcopy(target)]
    from product.tools.resource_bindings import resource_bindings
    task = {
        "schema_version": VERSION, "task_id": f"research-{uuid4()}",
        "resource_bindings": resource_bindings(capability, ROLES[capability]),
        "role": ROLES[capability], "capability": capability,
        "input_binding": research_input_binding(research_input),
        "input_hash": canonical_hash(research_input),
        "connection_binding": copy.deepcopy(dict(connection_binding)) if connection_binding is not None else None,
        "security": copy.deepcopy(target), "research_question": question.strip(),
        "security_ids": sorted(item["security_id"] for item in task_securities),
        "securities": task_securities, "research_scope": "SHARED_MARKET" if shared_market else "PER_SECURITY",
        "decision_cutoff": gate["decision_cutoff"], "gate_hash": gate["bundle_hash"],
        "allowed_evidence_ids": allowed, "permissions": [*permissions, "submit", "read_submission"],
        "allowed_documents": documents, "document_bodies": document_bodies, "peer_candidates": peers,
        "precomputed": precomputed, "calculation_evidence_ids": calculation_evidence_ids,
        "peer_materialization": copy.deepcopy(dict(peer_materialization)) if peer_materialization is not None else None,
        "peer_candidate_pool": copy.deepcopy(dict(peer_candidate_pool)) if peer_candidate_pool is not None else None,
        "fixture_portfolio": copy.deepcopy(research_input["fixture"]["portfolio"]) if capability == "FIXTURE_COUNCIL_DECISION" else None,
        "dependency_reports": dependencies, "known_claim_ids": known_claims(dependencies),
        "caller_authentication": "UNVERIFIED", "host_execution": "UNVERIFIED",
        "source_id": f"native-research-preparation:{gate['run_id']}",
        "as_of": gate["decision_cutoff"], "retrieved_at": created,
    }
    task["task_hash"] = canonical_hash(task)
    path = _private_root(root, create=True)
    _write_json(path / "input.json", research_input)
    _write_json(path / "gate.json", gate)
    _write_json(path / "task.json", task)
    _write_json(path / "access.json", {"task_id": task["task_id"], "task_hash": task["task_hash"], "token": token})
    if precomputed:
        (path / "precomputed").mkdir(mode=0o700)
        for artifact in precomputed:
            _write_json(path / "precomputed" / (artifact["artifact_hash"] + ".json"), artifact)
    return {"task": copy.deepcopy(task), "access_token": token}


class ResearchTools:
    """MCP连接仅绑定一个任务；访问能力不代表原生作者身份已验证。"""

    def __init__(self, root: Path, *, access_token: str | None = None) -> None:
        self.root = _private_root(root)
        self.access_token = access_token

    def _authorize(self) -> tuple[dict[str, Any], dict[str, Any]]:
        access = _read_json(self.root / "access.json")
        expected = access.get("token")
        if (not isinstance(expected, str) or len(expected) < 32
                or not isinstance(self.access_token, str)
                or not secrets.compare_digest(expected.encode(), self.access_token.encode())):
            raise ResearchAccessError("NATIVE_RESEARCH_ACCESS_INVALID")
        task = _read_json(self.root / "task.json")
        if (task.get("schema_version") != VERSION or task.get("task_id") != access.get("task_id")
                or task.get("task_hash") != access.get("task_hash")
                or task.get("task_hash") != canonical_hash({k: v for k, v in task.items() if k != "task_hash"})):
            raise ResearchAccessError("NATIVE_RESEARCH_TASK_BINDING_INVALID")
        original = _read_json(self.root / "input.json")
        validate_research_input(original)
        if canonical_hash(original) != task["input_hash"] or research_input_binding(original) != task["input_binding"]:
            raise ResearchAccessError("NATIVE_RESEARCH_INPUT_BINDING_INVALID")
        gate = _read_json(self.root / "gate.json")
        validate_gate(gate)
        if gate["bundle_hash"] != task["gate_hash"] or gate["decision_cutoff"] != task["decision_cutoff"]:
            raise ResearchAccessError("NATIVE_RESEARCH_GATE_BINDING_INVALID")
        if not set(task["allowed_evidence_ids"]) <= set(gate["allowed_evidence_ids"]):
            raise ResearchAccessError("NATIVE_RESEARCH_TASK_SCOPE_INVALID")
        if "resource_bindings" in task:
            from product.tools.resource_bindings import resource_bindings
            if task["resource_bindings"] != resource_bindings(task["capability"], task["role"]):
                raise ResearchAccessError("NATIVE_RESEARCH_RESOURCE_DRIFT")
        return task, gate

    def context(self, *, evidence_offset: int = 0, evidence_limit: int = 32) -> dict[str, Any]:
        task, _gate = self._authorize()
        if (type(evidence_offset) is not int or type(evidence_limit) is not int
                or evidence_offset < 0 or not 1 <= evidence_limit <= 64):
            raise ResearchAccessError("NATIVE_RESEARCH_PAGE_INVALID")
        from product.tools.report_contracts import semantic_schema
        result = copy.deepcopy(task)
        allowed = result["allowed_evidence_ids"]
        result["allowed_evidence_ids"] = allowed[evidence_offset:evidence_offset + evidence_limit]
        result["allowed_evidence_total"] = len(allowed)
        result["evidence_offset"] = evidence_offset
        result["next_evidence_offset"] = (evidence_offset + evidence_limit
                                          if evidence_offset + evidence_limit < len(allowed) else None)
        result["directory_is_not_evidence_query"] = True
        result["query_limits"] = {"max_ids": MAX_QUERY_IDS, "max_bytes": MAX_QUERY_BYTES,
                                  "default_offset": 0, "default_limit": MAX_QUERY_IDS}
        result["query_format"] = "query按选中ID顺序返回完整事实；大响应或显式offset/limit返回total/offset/next_offset，需继续时用同一ID列表和next_offset翻页；仅返回的事实记为已查询，单事实超限拒绝，不自动翻页。"
        result["calculation_evidence_count"] = len(result.pop("calculation_evidence_ids", []))
        result["calculation_catalog_format"] = ("calculations读取真实精确k引用/数值/单位/方法；大型目录用offset/limit及next_offset显式翻页，"
            "每页最多65536 UTF-8字节。长输入血缘仅为数量/hash摘要；用calculation_ref和evidence_offset/evidence_limit读取完整ID页，"
            "依next_evidence_offset显式继续。ID目录不是原始事实query，不自动选指标或翻页；正式提交由可信完整目录展开明确选择。")
        result.pop("dependency_reports", None)
        result.pop("peer_candidate_pool", None)
        result.pop("document_bodies", None)
        result.pop("resource_bindings", None)
        peer_materialization = result.pop("peer_materialization", None)
        result["selected_peers"] = [copy.deepcopy(item) for item in (peer_materialization or {}).get("selected", [])
                                    if item["holding_security_id"] == task["security"]["security_id"]]
        result["precomputed"] = [{k:v for k,v in item.items() if k != "evidence_fact_ids"} for item in task.get("precomputed", [])]
        result["report_catalog"] = [{"report_id": report["report_id"], "capability": report["capability"],
                                    "report_hash": report["report_hash"]}
                                   for report in task.get("dependency_reports", [])]
        return {**result, "output_schema": semantic_schema(task["capability"]),
                "submission_format": "首稿仅提交研究字段；修订用base_draft_ref与changes精确补丁。MCP精确回读的大报告按Unicode字符offset/limit返回report_json_fragment，以同一回执沿next_offset显式读完并拼接，payload_hash绑定完整JSON；片段不是完整报告。"}

    def search(self, *, query: str) -> dict[str, Any]:
        from product.tools.materials import search
        return search(self, query=query)

    def fetch(self, *, candidate_id: str) -> dict[str, Any]:
        from product.tools.materials import fetch
        return fetch(self, candidate_id=candidate_id)

    def read_documents(self, *, document_ids: list[str]) -> dict[str, Any]:
        from product.tools.documents import read_documents
        return read_documents(self, document_ids=document_ids)

    def read_reports(self, *, report_ids: list[str]) -> dict[str, Any]:
        from product.tools.report_reading import read_reports
        return read_reports(self, report_ids=report_ids)

    def calculations(self, *, offset: Any = _UNSET, limit: Any = _UNSET,
                     calculation_ref: Any = _UNSET, evidence_offset: Any = _UNSET,
                     evidence_limit: Any = _UNSET) -> dict[str, Any]:
        task, _gate = self._authorize()
        if not {"calculate", "calculation_catalog"} & set(task["permissions"]):
            raise ResearchAccessError("NATIVE_RESEARCH_CALCULATION_FORBIDDEN")
        from product.tools.report_submission import calculation_catalog
        catalog = calculation_catalog(self)
        detail = calculation_ref is not _UNSET
        if detail:
            if (not isinstance(calculation_ref, str) or calculation_ref not in catalog
                    or offset is not _UNSET or limit is not _UNSET):
                raise ResearchAccessError("NATIVE_RESEARCH_CALCULATION_SELECTION_INVALID")
            entries = [catalog[calculation_ref]]
            values = entries[0]["calculation"]["input_evidence_refs"]
            start = 0 if evidence_offset is _UNSET else evidence_offset
            count = 32 if evidence_limit is _UNSET else evidence_limit
        else:
            if evidence_offset is not _UNSET or evidence_limit is not _UNSET:
                raise ResearchAccessError("NATIVE_RESEARCH_PAGE_INVALID")
            entries = list(catalog.values())
            values = entries
            start = 0 if offset is _UNSET else offset
            count = 32 if limit is _UNSET else limit
        total = len(values)
        if (type(start) is not int or type(count) is not int
                or start < 0 or (start >= total and (start != 0 or total != 0))
                or not 1 <= count <= 64):
            raise ResearchAccessError("NATIVE_RESEARCH_PAGE_INVALID")
        def fits(value):
            return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")) <= MAX_QUERY_BYTES
        original = {"calculations": entries}
        if not detail and offset is _UNSET and limit is _UNSET and fits(original):
            return original
        stamp = _utc_now()
        envelope = {"source_id": f"native-research-calculations:{task['task_id']}",
                    "as_of": task["decision_cutoff"], "retrieved_at": stamp,
                    "directory_is_not_evidence_query": True}
        ends = range(min(start + count, total), start, -1) if total else (0,)
        for end in ends:
            selected = entries if detail else entries[start:end]
            projected = []
            for entry in selected:
                item = copy.deepcopy(entry)
                refs = item["calculation"].pop("input_evidence_refs")
                item.update(input_evidence_total=len(refs), input_evidence_hash=canonical_hash(refs),
                            input_evidence_complete=not refs)
                if detail:
                    item["calculation"]["input_evidence_refs"] = refs[start:end]
                    item.update(evidence_offset=start, next_evidence_offset=end if end < total else None,
                                input_evidence_complete=start == 0 and end == total)
                projected.append(item)
            page = {**envelope, "calculations": projected,
                    "mode": "INPUT_LINEAGE" if detail else "CATALOG"}
            if not detail:
                page.update(total=total, offset=start, next_offset=end if end < total else None)
            if fits(page):
                return page
        raise ResearchAccessError("NATIVE_RESEARCH_RESPONSE_TOO_LARGE")

    def submit(self, *, draft: dict[str, Any]) -> dict[str, Any]:
        from product.tools.report_submission import submit
        return submit(self, draft=draft)

    def read_submission_page(self, *, draft_ref: str, offset: Any = _UNSET, limit: Any = _UNSET) -> dict[str, Any]:
        # MCP transport only; internal dependency/archive readers keep full reports.
        report = self.read_submission(draft_ref=draft_ref)
        start, count = 0 if offset is _UNSET else offset, 8192 if limit is _UNSET else limit
        payload = canonical_json(report)
        if (type(start) is not int or type(count) is not int
                or not 0 <= start < len(payload) or not 1 <= count <= 8192):
            raise ResearchAccessError("NATIVE_RESEARCH_PAGE_INVALID")
        if (offset is _UNSET and limit is _UNSET
                and len(json.dumps(report, ensure_ascii=False, allow_nan=False).encode("utf-8")) <= MAX_QUERY_BYTES):
            return report
        end = min(start + count, len(payload))
        page = {key: report[key] for key in ("source_id", "as_of", "retrieved_at", "report_id", "report_hash")}
        page.update(mode="REPORT_JSON_PAGE", draft_ref=draft_ref, payload_hash=canonical_hash(report),
                    offset=start, total=len(payload), next_offset=end if end < len(payload) else None,
                    offset_unit="UNICODE_CODE_POINT", report_complete=start == 0 and end == len(payload),
                    report_json_fragment=payload[start:end])
        if len(json.dumps(page, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_QUERY_BYTES:
            raise ResearchAccessError("NATIVE_RESEARCH_RESPONSE_TOO_LARGE")
        return page

    def read_submission(self, *, draft_ref: str) -> dict[str, Any]:
        from product.tools.report_submission import read_submission
        return read_submission(self, draft_ref=draft_ref)

    def _record(self, task: Mapping[str, Any], tool: str, inputs: Any, output: Any) -> None:
        stamp = _utc_now()
        evidence_ids = ([fact["evidence_id"] for fact in output["evidence"]]
                        if tool == "query" else inputs.get("evidence_ids", []))
        event = {
            "task_id": task["task_id"], "task_hash": task["task_hash"], "tool": tool,
            "input_hash": canonical_hash(inputs), "output_hash": canonical_hash(output),
            "evidence_ids": evidence_ids, "report_ids": inputs.get("report_ids", []),
            "document_ids": inputs.get("document_ids", []),
            "source_id": f"native-research-tool:{task['task_id']}",
            "as_of": stamp, "retrieved_at": stamp,
            "caller_authentication": "UNVERIFIED",
        }
        event["event_hash"] = canonical_hash(event)
        directory = self.root / "tools"
        if directory.is_symlink():
            raise ResearchAccessError("NATIVE_RESEARCH_PATH_UNSAFE")
        directory.mkdir(mode=0o700, exist_ok=True)
        _write_json(directory / f"{uuid4()}.json", event)

    def _evidence(self, task: Mapping[str, Any], gate: Mapping[str, Any]) -> EvidenceTools:
        permitted = ["fixture_evidence.query"]
        if "calculate" in task["permissions"]:
            permitted.append("fixture_math.calculate")
        return EvidenceTools(
            gate, run_id=gate["run_id"], agent=task["role"], invocation_id=task["task_id"],
            allowed_tools=permitted, allowed_evidence_ids=task["allowed_evidence_ids"],
            adapter_version=ADAPTER_VERSION, structured_sec_amounts=True,
        )

    def catalog(self, *, offset: int = 0, limit: int = 32) -> dict[str, Any]:
        task, gate = self._authorize()
        if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 64:
            raise ResearchAccessError("NATIVE_RESEARCH_PAGE_INVALID")
        fields = ("evidence_id", "security_id", "semantic_field", "unit", "source_id", "as_of", "retrieved_at")
        facts = {fact["evidence_id"]: fact for fact in gate["allowed_evidence"]}
        selected = task["allowed_evidence_ids"][offset:offset + limit]
        return {
            "records": [{key: copy.deepcopy(facts[ref].get(key)) for key in fields} for ref in selected],
            "total": len(task["allowed_evidence_ids"]),
            "next_offset": offset + limit if offset + limit < len(task["allowed_evidence_ids"]) else None,
            "directory_is_not_evidence_query": True,
        }

    def query(self, *, evidence_ids: list[str], offset: Any = _UNSET, limit: Any = _UNSET) -> dict[str, Any]:
        task, gate = self._authorize()
        if (not isinstance(evidence_ids, list) or not 1 <= len(evidence_ids) <= MAX_QUERY_IDS
                or any(not isinstance(item, str) for item in evidence_ids)
                or len(evidence_ids) != len(set(evidence_ids))):
            raise ResearchAccessError("NATIVE_RESEARCH_QUERY_INVALID")
        inputs: dict[str, Any] = {"evidence_ids": evidence_ids}
        if offset is not _UNSET:
            inputs["offset"] = offset
        if limit is not _UNSET:
            inputs["limit"] = limit
        start = 0 if offset is _UNSET else offset
        count = MAX_QUERY_IDS if limit is _UNSET else limit
        if (type(start) is not int or type(count) is not int
                or not 0 <= start < len(evidence_ids) or not 1 <= count <= MAX_QUERY_IDS):
            raise ResearchAccessError("NATIVE_RESEARCH_PAGE_INVALID")
        # Authorize the entire selection, including facts outside this page.
        result = self._evidence(task, gate).query(
            run_id=gate["run_id"], agent=task["role"], invocation_id=task["task_id"], evidence_ids=evidence_ids,
        )
        if (offset is _UNSET and limit is _UNSET
                and len(json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")) <= MAX_QUERY_BYTES):
            self._record(task, "query", inputs, result)
            return result
        facts = result["evidence"]
        for end in range(min(start + count, len(facts)), start, -1):
            page = {**result, "evidence": facts[start:end], "result_hash": content_hash(facts[start:end]),
                    "total": len(facts), "offset": start, "next_offset": end if end < len(facts) else None}
            if len(json.dumps(page, ensure_ascii=False, allow_nan=False).encode("utf-8")) <= MAX_QUERY_BYTES:
                self._record(task, "query", inputs, page)
                return page
        raise ResearchAccessError("NATIVE_RESEARCH_RESPONSE_TOO_LARGE")

    def calculate(self, *, operation: str, evidence_ids: list[str], target_scale: str | None = None) -> dict[str, Any]:
        task, gate = self._authorize()
        if "calculate" not in task["permissions"]:
            raise ResearchAccessError("NATIVE_RESEARCH_CALCULATION_FORBIDDEN")
        if not isinstance(evidence_ids, list) or any(not isinstance(item, str) for item in evidence_ids):
            raise ResearchAccessError("NATIVE_RESEARCH_QUERY_INVALID")
        result = self._evidence(task, gate).calculate(
            run_id=gate["run_id"], agent=task["role"], invocation_id=task["task_id"],
            calculation_id=f"calculation-{uuid4()}", operation=operation,
            evidence_ids=evidence_ids, target_scale=target_scale,
        )
        directory = self.root / "calculations"
        if directory.is_symlink():
            raise ResearchAccessError("NATIVE_RESEARCH_PATH_UNSAFE")
        directory.mkdir(mode=0o700, exist_ok=True)
        _write_json(directory / f"{result['calculation_id']}.json", result)
        self._record(task, "calculate", {"evidence_ids": evidence_ids, "operation": operation}, result)
        return result
