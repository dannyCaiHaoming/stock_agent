"""多维研究的显式资料准备阶段；只选择和取得资料，不形成投资结论。"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import tomllib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from product.intake.v3 import validate_handoff
from product.mcp.live.peer_candidates import validate_peer_candidate_pool
from product.mcp.provenance import parse_timestamp
from product.runtime.hashing import canonical_hash, file_hash, legacy_envelope_hash
from product.runtime.schema_validation import validate_schema_definition, validate_schema_instance
from product.mcp.provenance import content_hash

from .multidimensional_stage import (
    _agent_binding,
    _bounded_latest_facts,
    _facts_for_capability,
    _read_object,
    _skill_binding,
    _write_object,
)


STAGE_VERSION = "multidimensional-material-preparation-runtime/1.1.0"
DISPATCH_VERSION = "multidimensional-material-preparation-dispatch/1.2.0"
SEMANTIC_OUTPUT_VERSION = "research-material-semantic-draft/1.0.0"
MATERIAL_START_CONTEXT_MAX_BYTES = 256 * 1024
DISCOVERY_KINDS = {
    "RESEARCH_REPORT_DISCOVERY",
    "MACRO_RESEARCH_DISCOVERY",
    "MARKET_RESEARCH_DISCOVERY",
}


def _parent_output_schema(run_id: str, task_count: int) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object", "additionalProperties": False,
        "required": ["stage", "run_id", "dispatched", "completed"],
        "properties": {
            "stage": {"type": "string", "const": "MULTIDIMENSIONAL_MATERIAL_PREPARATION"},
            "run_id": {"type": "string", "const": run_id},
            "dispatched": {"type": "integer", "const": task_count},
            "completed": {"type": "integer", "const": task_count},
        },
    }


class ResearchMaterialsStageError(ValueError):
    pass


def serialize_research_materials_dispatch_context(packet: Mapping[str, Any]) -> str:
    if packet.get("task", {}).get("semantic_output_version") == SEMANTIC_OUTPUT_VERSION:
        # 仅剔除已在 identity 中交付的任务身份及内部完整性字段。
        # 不递归清理同名字段：证券、来源、期间和用户资料仍是研究输入。
        packet = {**packet, "task": {key: value for key, value in packet["task"].items()
                                    if key not in {"task_hash", "agent", "run_id", "invocation_id",
                                                   "task_id", "task_name"}}}
        packet = {**packet, "submission_guidance": {
            "format": "semantic-draft",
            "instructions": "只按 output_schema 提交状态、检索意图、材料选择、理由和缺口。"
                            "身份、实际查询/获取尝试、文件路径及 hash 由运行记录装配；不要填写。"
                            "query_intents 解释已实际执行查询的目的；重复查询只需一条意图，"
                            "每次尝试由工具审计保留。PEER_SELECTION 的 query_intents 必须为空。"
                            "不得把搜索线索或来源失败当作已取得正文。",
        }}
    context = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(context.encode("utf-8")) > MATERIAL_START_CONTEXT_MAX_BYTES:
        raise ResearchMaterialsStageError(
            "RESEARCH_MATERIALS_START_CONTEXT_TOO_LARGE: "
            f"kind={packet.get('task', {}).get('preparation_kind', 'UNKNOWN')} "
            f"bytes={len(context.encode('utf-8'))} limit={MATERIAL_START_CONTEXT_MAX_BYTES} "
            f"catalog_items={len(packet.get('evidence_catalog', []))}"
        )
    return context


def _read_object_list(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_SOURCE_ACCESS_INVALID") from exc
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_SOURCE_ACCESS_INVALID")
    return [dict(item) for item in value]


def _verify_merged_peer_gate_time(
    base_gate: Mapping[str, Any], peer_gate: Mapping[str, Any],
    allowed: list[Mapping[str, Any]], excluded: list[Mapping[str, Any]],
    *, observed_at: str, calendar=None,
) -> str:
    """Fail closed at the final cutoff after both independently gated captures."""
    base_cutoff = parse_timestamp(base_gate["decision_cutoff"])
    peer_cutoff = parse_timestamp(peer_gate["decision_cutoff"])
    final_cutoff = max(base_cutoff, peer_cutoff)
    if final_cutoff > parse_timestamp(observed_at):
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_CUTOFF_IN_FUTURE")
    if (base_gate.get("calendar_lock") and peer_gate.get("calendar_lock")
            and base_gate["calendar_lock"] != peer_gate["calendar_lock"]):
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_CALENDAR_MISMATCH")
    allowed_ids = [fact.get("evidence_id") for fact in allowed]
    excluded_ids = [fact.get("evidence_id") for fact in excluded]
    if (len(allowed_ids) != len(set(allowed_ids))
            or set(allowed_ids) & set(excluded_ids)):
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_EVIDENCE_DUPLICATE")
    for fact in allowed:
        if not all(isinstance(fact.get(field), str) for field in (
            "source_id", "as_of", "retrieved_at"
        )):
            raise ResearchMaterialsStageError("PEER_MATERIALIZATION_PROVENANCE_INVALID")
        time_fields = ["as_of", "retrieved_at"]
        if "published_at" in fact:
            time_fields.append("published_at")
        if any(parse_timestamp(fact[field]) > final_cutoff for field in time_fields):
            raise ResearchMaterialsStageError("PEER_MATERIALIZATION_FINAL_PIT_LEAKAGE")
        if fact.get("freshness_status") == "FRESH" and fact.get("source_type") != "derived":
            if fact.get("kind") == "price":
                if calendar is not None:
                    sessions = sorted(parse_timestamp(item)
                                      for item in calendar.completed_sessions(final_cutoff))
                    if parse_timestamp(fact["as_of"]) not in sessions[-2:]:
                        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_FINAL_PRICE_STALE")
            else:
                form = (fact.get("metadata") or {}).get("form", "")
                threshold = 800 if fact.get("usage") == "comparison" else (
                    450 if form in {"10-K", "10-K/A"}
                    else 200 if form in {"10-Q", "10-Q/A"}
                    else 90 if form in {"8-K", "8-K/A"}
                    else 90 if fact.get("kind") == "ownership" and form in {
                        "3", "3/A", "4", "4/A", "5", "5/A"
                    } else None
                )
                if threshold is not None and (
                    final_cutoff - parse_timestamp(fact["as_of"]) > timedelta(days=threshold)
                ):
                    raise ResearchMaterialsStageError("PEER_MATERIALIZATION_FINAL_FACT_STALE")
    return final_cutoff.isoformat().replace("+00:00", "Z")


def _output_schema(*, run_id: str, invocation_id: str, agent: str, kind: str) -> dict[str, Any]:
    selection = {
        "type": "object", "additionalProperties": False,
        "required": ["candidate_id", "document_id", "rationale"],
        "properties": {
            "candidate_id": {"type": "string", "minLength": 1},
            "document_id": {"type": ["string", "null"], "minLength": 1},
            "rationale": {"type": "string", "minLength": 1},
        },
    }
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "research-material-preparation-draft/1.0.0",
        "type": "object", "additionalProperties": False,
        "required": [
            "run_id", "invocation_id", "agent", "preparation_kind", "security_id",
            "status", "summary", "queries", "selections", "gaps", "artifact_refs",
        ],
        "properties": {
            "run_id": {"type": "string", "const": run_id},
            "invocation_id": {"type": "string", "const": invocation_id},
            "agent": {"type": "string", "const": agent},
            "preparation_kind": {"type": "string", "const": kind},
            "security_id": {"type": "string", "minLength": 1},
            "status": {"type": "string", "enum": ["READY", "SOURCE_LIMITED", "BLOCKED_CONFIGURATION"]},
            "summary": {"type": "string", "minLength": 1},
            "queries": {
                "type": "array", "maxItems": 3,
                "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["query", "purpose"],
                    "properties": {
                        "query": {"type": "string", "minLength": 1, "maxLength": 240},
                        "purpose": {"type": "string", "minLength": 1},
                    },
                },
            },
            "selections": {"type": "array", "maxItems": 5 if kind in DISCOVERY_KINDS else 3, "items": selection},
            "gaps": {
                "type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["reason_code", "description", "impact"],
                    "properties": {
                        "reason_code": {"type": "string", "minLength": 1},
                        "description": {"type": "string", "minLength": 1},
                        "impact": {"type": "string", "minLength": 1},
                    },
                },
            },
            "artifact_refs": {"type": "array", "uniqueItems": True, "items": {"type": "string", "minLength": 1}},
        },
    }
    validate_schema_definition(schema)
    return schema


def material_semantic_schema(task: Mapping[str, Any]) -> dict[str, Any]:
    """从原业务结构派生草稿，不要求模型填写固定身份或工具审计。"""
    schema = _output_schema(run_id=task["run_id"], invocation_id=task["invocation_id"],
                            agent=task["agent"], kind=task["preparation_kind"])
    removed = {"run_id", "invocation_id", "agent", "security_id", "preparation_kind", "artifact_refs", "queries"}
    schema["$id"] = SEMANTIC_OUTPUT_VERSION
    schema["required"] = [key for key in schema["required"] if key not in removed] + ["query_intents"]
    queries = schema["properties"]["queries"]
    for key in removed:
        schema["properties"].pop(key)
    schema["properties"]["query_intents"] = queries
    if task["preparation_kind"] == "PEER_SELECTION":
        queries["maxItems"] = 0
    validate_schema_definition(schema)
    return schema


def _material_path(root: Path, ref: str) -> Path:
    if not isinstance(ref, str) or not ref:
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_AUDIT_PATH_INVALID")
    path = root / ref
    if (Path(ref).is_absolute() or not path.resolve().is_relative_to(root.resolve())
            or any(p.is_symlink() for p in (path, *path.parents) if p != root)
            or not path.is_file()):
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_AUDIT_PATH_INVALID")
    return path


def build_material_tool_audit(run_dir: Path, task: Mapping[str, Any]) -> dict[str, Any]:
    """从实际工具事件及原始产物生成审计；不是模型自报或目录存在证明。"""
    root = Path(run_dir).resolve()
    directory = root / "research/materials" / hashlib.sha256(task["invocation_id"].encode()).hexdigest()[:16]
    attempts, artifact_refs = [], []
    if task["preparation_kind"] in DISCOVERY_KINDS:
        event_path = _material_path(root, "events/mcp/events.jsonl")
        try:
            events = [json.loads(line) for line in event_path.read_text().splitlines() if line.strip()]
        except (OSError, ValueError) as exc:
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_TOOL_EVENT_INVALID") from exc
        proven_refs: set[str] = set()
        for event in events:
            if not isinstance(event, dict):
                raise ResearchMaterialsStageError("RESEARCH_MATERIALS_TOOL_EVENT_INVALID")
            if event.get("invocation_id") != task["invocation_id"] or event.get("event_type") != "mcp_tool_result":
                continue
            if (event.get("run_id") != task["run_id"] or event.get("agent") != task["agent"]
                    or event.get("tool") not in {"public_research.search", "public_research.fetch"}):
                raise ResearchMaterialsStageError("RESEARCH_MATERIALS_TOOL_EVENT_BINDING_INVALID")
            if "artifact_ref" not in event:
                raise ResearchMaterialsStageError("RESEARCH_MATERIALS_TOOL_EVENT_BINDING_INVALID")
            for key, hash_key in (("artifact_ref", "artifact_sha256"), ("attempt_ref", "attempt_sha256")):
                if key in event:
                    ref = event[key]
                    if (not isinstance(ref, str) or not _material_path(root, ref).parent == directory
                            or file_hash(root / ref) != event.get(hash_key)):
                        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_ARTIFACT_HASH_MISMATCH")
                    proven_refs.add(ref)
            ref = event["artifact_ref"]
            path = _material_path(root, ref)
            artifact = _read_object(path)
            args = {key: task[key] for key in ("run_id", "agent", "invocation_id", "security_id")}
            if path.name.startswith("search-"):
                args.update(decision_cutoff=task["decision_cutoff"], query=artifact.get("query"))
                output = {**artifact, "status": artifact.get("attempt_status"), "artifact_ref": ref}
                operation = "public_research.search"
            elif path.name.startswith("document-"):
                args["candidate_id"] = artifact.get("candidate_id")
                if (artifact.get("verification_status") != "BODY_VERIFIED"
                        or artifact.get("security_id") != task["security_id"]
                        or not all(isinstance(artifact.get(key), str) and artifact[key]
                                   for key in ("source_id", "as_of", "retrieved_at"))):
                    raise ResearchMaterialsStageError("RESEARCH_MATERIALS_DOCUMENT_PROVENANCE_INVALID")
                output = {"status": "READY", "document": artifact, "artifact_ref": ref,
                          "cache_hit": event.get("cache_hit", False)}
                if event.get("attempt_ref"):
                    attempt = _read_object(_material_path(root, event["attempt_ref"]))
                    if (attempt.get("status") != "READY"
                            or attempt.get("security_id") != task["security_id"]
                            or attempt.get("candidate_id") != artifact.get("candidate_id")
                            or attempt.get("document_id") != artifact.get("document_id")):
                        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_TOOL_EVENT_BINDING_INVALID")
                    output["attempt_ref"] = event["attempt_ref"]
                elif event.get("cache_hit") is not True:
                    raise ResearchMaterialsStageError("RESEARCH_MATERIALS_TOOL_EVENT_BINDING_INVALID")
                operation = "public_research.fetch"
            elif path.name.startswith("fetch-"):
                args["candidate_id"] = artifact.get("candidate_id")
                if artifact.get("status") not in {"SOURCE_LIMITED", "BLOCKED_CONFIGURATION"}:
                    raise ResearchMaterialsStageError("RESEARCH_MATERIALS_TOOL_EVENT_BINDING_INVALID")
                output = {**artifact, "artifact_ref": ref, "cache_hit": event.get("cache_hit", False)}
                operation = "public_research.fetch"
            else:
                raise ResearchMaterialsStageError("RESEARCH_MATERIALS_AUDIT_ARTIFACT_KIND_INVALID")
            if (event.get("tool") != operation or event.get("input_hash") != content_hash(args)
                    or event.get("output_hash") != content_hash(output)):
                raise ResearchMaterialsStageError("RESEARCH_MATERIALS_TOOL_EVENT_BINDING_INVALID:" + ref)
            # 保留每次真实调用，包括重复查询和缓存命中，不从唯一文件数推断尝试次数。
            attempts.append({"ordinal": len(attempts) + 1, "operation": operation,
                             "artifact_ref": ref, "artifact_sha256": file_hash(path),
                             "query": artifact.get("query"), "candidate_id": artifact.get("candidate_id"),
                             "status": output["status"], "failure_code": artifact.get("failure_code"),
                             "cache_hit": event.get("cache_hit", False),
                             "event_hash": canonical_hash(event),
                             "input_hash": event["input_hash"], "output_hash": event["output_hash"]})
        artifact_refs = sorted(proven_refs)
        for path in directory.glob("*.json"):
            if str(path.relative_to(root)) not in proven_refs:
                raise ResearchMaterialsStageError("RESEARCH_MATERIALS_TOOL_EVENT_MISSING:" + str(path.relative_to(root)))
        if not any(item["operation"] == "public_research.search" for item in attempts):
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_SEARCH_PROOF_MISSING")
    elif task["preparation_kind"] != "PEER_SELECTION":
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_KIND_INVALID")
    audit = {"schema_version": "research-material-tool-audit/1.0.0",
             **{key: task[key] for key in ("run_id", "invocation_id", "task_id", "agent", "security_id")},
             "attempts": attempts, "artifact_refs": artifact_refs}
    audit["audit_hash"] = legacy_envelope_hash(audit, hash_field="audit_hash")
    return audit


def assemble_material_semantic_draft(draft: Mapping[str, Any], *, task: Mapping[str, Any], run_dir: Path) -> tuple[dict, dict]:
    """只装配真实审计与固定身份；不替模型决定正文相关性或来源充分性。"""
    if task.get("semantic_output_version") != SEMANTIC_OUTPUT_VERSION:
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_SEMANTIC_PROTOCOL_INVALID")
    validate_schema_instance(draft, material_semantic_schema(task))
    audit = build_material_tool_audit(run_dir, task)
    actual = list(dict.fromkeys(item["query"] for item in audit["attempts"] if item["operation"] == "public_research.search"))
    intents = {item["query"]: item["purpose"] for item in draft["query_intents"]}
    if len(intents) != len(draft["query_intents"]) or set(intents) != set(actual):
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_QUERY_INTENT_NOT_EXECUTED")
    result = {key: copy.deepcopy(value) for key, value in draft.items() if key != "query_intents"}
    result.update({key: task[key] for key in ("run_id", "invocation_id", "agent", "preparation_kind", "security_id")})
    result["queries"] = [{"query": query, "purpose": intents[query]} for query in actual]
    result["artifact_refs"] = audit["artifact_refs"]
    validate_material_preparation_output(result, task=task, run_dir=run_dir)
    return result, audit


def verify_material_tool_audit(run_dir: Path, task: Mapping[str, Any], output: Mapping[str, Any],
                               capture: Mapping[str, Any]) -> dict[str, Any]:
    """新提交的消费者重验底层审计；未标记的历史格式仍按原契约读取。"""
    if task.get("semantic_output_version") != SEMANTIC_OUTPUT_VERSION:
        return {}
    expected_output = "research/material-results/" + canonical_hash({"task_id": task["task_id"]})[:16] + "/preparation-result.json"
    if capture.get("path") != expected_output:
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_OUTPUT_PATH_INVALID")
    expected_ref = str(Path(capture["path"]).parent / "tool-audit.json")
    if capture.get("tool_audit_ref") != expected_ref:
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_TOOL_AUDIT_MISSING")
    saved = _read_object(_material_path(run_dir, expected_ref))
    actual = build_material_tool_audit(run_dir, task)
    if (saved != actual or capture.get("tool_audit_hash") != actual["audit_hash"]
            or output.get("artifact_refs") != actual["artifact_refs"]
            or capture.get("output_hash") != canonical_hash(output)):
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_TOOL_AUDIT_BINDING_INVALID")
    return {"tool_audit_ref": expected_ref, "tool_audit_hash": actual["audit_hash"]}


def prepare_research_materials_stage(
    repository_root: Path, *, handoff_path: Path, gate_path: Path,
    peer_candidate_pool_path: Path, run_dir: Path, run_id: str,
    model: str, target_concurrency: int = 3,
    reuse_frozen_gate: bool = False,
) -> dict[str, Any]:
    """准备 Company/Market 两类资料任务；不启动模型或网络。"""

    repository_root = Path(repository_root).resolve()
    product_root = repository_root / "product"
    from product.runtime.versioning import load_version_manifest, validate_current_component_versions
    validate_current_component_versions(product_root, load_version_manifest(product_root / "version-manifest.json"),
                                        skill_names=("research-report-analysis",),
                                        schema_names=("research-dimension-report",),
                                        adapter_scopes=("fixture-gate-scoped",), check_risk=False)
    run_dir = Path(run_dir).resolve()
    if run_dir.exists():
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_RUN_EXISTS")
    if type(target_concurrency) is not int or target_concurrency < 1:
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_CONCURRENCY_INVALID")
    from product.runtime.model_routing import select_product_runtime_model
    selected_model = select_product_runtime_model(product_root, requested_model=model)
    handoff = _read_object(Path(handoff_path).resolve())
    validate_handoff(handoff)
    gate = _read_object(Path(gate_path).resolve())
    gate_input_binding = None
    if reuse_frozen_gate:
        from product.runtime.evidence_gate import bind_frozen_gate_to_run
        gate, gate_input_binding = bind_frozen_gate_to_run(Path(gate_path), run_id=run_id)
    elif gate.get("run_id") not in {None, run_id}:
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_GATE_RUN_MISMATCH")
    gate["run_id"] = run_id
    gate["source_mode"] = gate.get("source_mode", "fixture")
    gate["bundle_hash"] = legacy_envelope_hash(gate, hash_field="bundle_hash")
    cutoff = gate.get("decision_cutoff")
    if not isinstance(cutoff, str):
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_CUTOFF_MISSING")
    cutoff_time = parse_timestamp(cutoff)
    for fact in gate.get("allowed_evidence", []):
        if any(
            not isinstance(fact.get(key), str) or parse_timestamp(fact[key]) > cutoff_time
            for key in ("as_of", "retrieved_at")
        ):
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_GATE_PIT_INVALID")
    pool = _read_object(Path(peer_candidate_pool_path).resolve())
    validate_peer_candidate_pool(pool)
    if parse_timestamp(pool["retrieved_at"]) > cutoff_time:
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_PEER_POOL_AFTER_CUTOFF")
    common = [
        item for item in handoff["portfolio"]["positions"]
        if item["asset_type"] == "COMMON_STOCK"
    ]
    groups = {item["security_id"]: item for item in pool["groups"]}
    if set(groups) != {item["security_id"] for item in common}:
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_PEER_SCOPE_INVALID")
    agents = {
        name: _agent_binding(product_root, name)
        for name in ("runtime_company_analyst", "runtime_market_catalyst")
    }
    skills = {
        name: _skill_binding(product_root, name)
        for name in ("research-report-analysis", "industry-comparison", "macro-market-analysis")
    }
    run_dir.mkdir(parents=True)
    if gate_input_binding is not None:
        source_copy = run_dir / gate_input_binding["source_ref"]
        source_copy.parent.mkdir(parents=True, exist_ok=True)
        source_copy.write_bytes(Path(gate_path).read_bytes())
    _write_object(run_dir / "audit/portfolio-handoff.json", handoff)
    _write_object(run_dir / "evidence/gate.json", gate)
    _write_object(run_dir / "research/peer-candidate-pool.json", pool)
    tasks = []
    ordinal = 0
    for position in common:
        security_id = position["security_id"]
        for kind, agent, skill in (
            ("RESEARCH_REPORT_DISCOVERY", "runtime_company_analyst", "research-report-analysis"),
            ("PEER_SELECTION", "runtime_market_catalyst", "industry-comparison"),
        ):
            ordinal += 1
            task_id = f"material:{kind.lower()}:{security_id.replace(':', '_').lower()}"
            invocation_id = f"{run_id}:{agent}:{task_id}"
            task_name = f"research_material_preparation_{ordinal}"
            task = {
                "task_id": task_id, "task_name": task_name, "run_id": run_id,
                "invocation_id": invocation_id, "preparation_kind": kind,
                "agent": agent, "skill_name": skill, "security_id": security_id,
                "security": {
                    key: position.get(key) for key in ("security_id", "display_symbol", "display_name", "market", "asset_type")
                },
                "decision_cutoff": cutoff,
                "semantic_output_version": SEMANTIC_OUTPUT_VERSION,
                "peer_candidate_group": groups[security_id] if kind == "PEER_SELECTION" else None,
            }
            task["task_hash"] = legacy_envelope_hash(task, hash_field="task_hash")
            task_path = f"research/tasks/{canonical_hash({'task_id': task_id})}.json"
            _write_object(run_dir / task_path, task)
            instruction = (
                "这是资料准备而非正式投资研究。根据证券身份与当前公司问题构造至多三条精确查询，"
                "实际调用 research_search；只对返回候选调用 research_fetch。搜索标题/摘要只是线索，"
                "只有 BODY_VERIFIED 正文可选择。不得使用通用 Web、模型记忆或输出投资动作；来源受限时"
                "保留实际错误和影响。缺少正文 API key 等配置问题必须输出 BLOCKED_CONFIGURATION，"
                "不得写成 SOURCE_LIMITED；保留检索意图 query_intents 和真实限制的影响。"
                "运行身份、工具查询/获取审计及路径由程序从实际记录装配，不填写 artifact_refs。"
                if kind == "RESEARCH_REPORT_DISCOVERY" else
                "这是同行候选选择，不是正式同行比较。只能从 peer_candidate_group 选择至多三个 candidate_id，"
                "逐项说明商业可比理由；候选目录字段不是已核实研究事实。不得输出赢家、评级或投资动作。"
            )
            permissions = (
                ["public_research.search", "public_research.fetch"]
                if kind == "RESEARCH_REPORT_DISCOVERY" else []
            )
            invocation = {
                "schema_version": "research-material-preparation-invocation/1.0.0",
                "run_id": run_id, "invocation_id": invocation_id,
                "agent_binding": agents[agent], "skill": skills[skill],
                "model": selected_model, "prompt_hash": canonical_hash({"instruction": instruction}),
                "task_path": task_path, "tool_permissions": permissions,
                "analysis_mode": "MATERIAL_PREPARATION_ONLY",
                "semantic_output_version": SEMANTIC_OUTPUT_VERSION,
            }
            invocation["manifest_hash"] = legacy_envelope_hash(invocation, hash_field="manifest_hash")
            invocation_path = f"invocations/by-id/{canonical_hash({'invocation_id': invocation_id})}.json"
            _write_object(run_dir / invocation_path, invocation)
            facts = _facts_for_capability(
                gate.get("allowed_evidence", []), capability="FUNDAMENTAL_EVENT",
                security_ids=[security_id], benchmark_id=None,
            )
            # 材料发现只需有界目录；完整财务历史仍在 Gate，正式研究不受影响。
            facts = _bounded_latest_facts(facts)
            packet = {
                "dispatch_contract": DISPATCH_VERSION,
                "identity": {
                    "run_id": run_id, "invocation_id": invocation_id, "task_id": task_id,
                    "task_name": task_name, "agent": agent, "security_id": security_id,
                },
                "instruction": instruction, "task": task,
                "evidence_catalog": [
                    {key: fact.get(key) for key in ("evidence_id", "semantic_field", "source_id", "as_of", "retrieved_at")}
                    for fact in facts
                ],
                "peer_candidate_group": groups[security_id] if kind == "PEER_SELECTION" else None,
                "tool_context": {
                    "mcp_server": "fixture_runtime", "logical_permissions": permissions,
                    "required_identity_arguments": {
                        "run_id": run_id, "agent": agent,
                        "invocation_id": invocation_id,
                    },
                },
                "output_schema": material_semantic_schema(task),
            }
            packet_path = f"research/dispatch-packets/{canonical_hash({'packet': invocation_id})}.json"
            serialize_research_materials_dispatch_context(packet)
            _write_object(run_dir / packet_path, packet)
            tasks.append({
                **task, "task_path": task_path, "invocation_path": invocation_path,
                "packet_path": packet_path, "packet_hash": canonical_hash(packet), "depends_on": [],
            })
    for kind, capability, security_id, display_name in (
        ("MACRO_RESEARCH_DISCOVERY", "MACRO_CONTEXT", "US:MACRO", "美国宏观环境"),
        ("MARKET_RESEARCH_DISCOVERY", "MARKET_STATE", "US:MARKET", "美国市场状态"),
    ):
        ordinal += 1
        agent, skill = "runtime_market_catalyst", "macro-market-analysis"
        task_id = f"material:{kind.lower()}:shared"
        invocation_id = f"{run_id}:{agent}:{task_id}"
        task_name = f"research_material_preparation_{ordinal}"
        task = {
            "task_id": task_id, "task_name": task_name, "run_id": run_id,
            "invocation_id": invocation_id, "preparation_kind": kind,
            "agent": agent, "skill_name": skill, "security_id": security_id,
            "security": {
                "security_id": security_id, "display_symbol": None,
                "display_name": display_name, "market": "US", "asset_type": "RESEARCH_SCOPE",
            },
            "decision_cutoff": cutoff, "peer_candidate_group": None,
            "semantic_output_version": SEMANTIC_OUTPUT_VERSION,
            "target_capabilities": [capability],
        }
        task["task_hash"] = legacy_envelope_hash(task, hash_field="task_hash")
        task_path = f"research/tasks/{canonical_hash({'task_id': task_id})}.json"
        _write_object(run_dir / task_path, task)
        boundary = (
            "只搜索宏观策略与官方政策解读，围绕利率、通胀、就业、经济活动和已公布日历；"
            if capability == "MACRO_CONTEXT" else
            "只搜索市场策略正文，围绕大盘、板块、跨资产、波动、信用/流动性和市场风险状态；"
        )
        instruction = (
            "这是资料准备而非正式投资研究。" + boundary +
            "根据当前持仓与截止时点构造至多三条精确查询，实际调用 research_search；"
            "只对返回候选调用 research_fetch。搜索标题/摘要只是线索，只有 BODY_VERIFIED 正文"
            "可选择。不得使用通用 Web、模型记忆或输出投资动作；来源受限时保留实际错误"
            "和影响。缺少正文 API key 等配置问题必须输出 BLOCKED_CONFIGURATION。"
            "保留 query_intents 和实际限制；身份、查询/获取审计及路径由程序装配，不填写 artifact_refs。"
        )
        invocation = {
            "schema_version": "research-material-preparation-invocation/1.1.0",
            "run_id": run_id, "invocation_id": invocation_id,
            "agent_binding": agents[agent], "skill": skills[skill],
            "model": selected_model,
            "prompt_hash": canonical_hash({"instruction": instruction}),
            "task_path": task_path,
            "tool_permissions": ["public_research.search", "public_research.fetch"],
            "analysis_mode": "MATERIAL_PREPARATION_ONLY",
            "semantic_output_version": SEMANTIC_OUTPUT_VERSION,
        }
        invocation["manifest_hash"] = legacy_envelope_hash(invocation, hash_field="manifest_hash")
        invocation_path = f"invocations/by-id/{canonical_hash({'invocation_id': invocation_id})}.json"
        _write_object(run_dir / invocation_path, invocation)
        facts = _facts_for_capability(
            gate.get("allowed_evidence", []), capability=capability,
            security_ids=[item["security_id"] for item in common], benchmark_id=None,
        )
        if capability == "MARKET_STATE":
            facts = _bounded_latest_facts(facts)
        packet = {
            "dispatch_contract": DISPATCH_VERSION,
            "identity": {
                "run_id": run_id, "invocation_id": invocation_id, "task_id": task_id,
                "task_name": task_name, "agent": agent, "security_id": security_id,
            },
            "instruction": instruction, "task": task,
            "evidence_catalog": [
                {key: fact.get(key) for key in (
                    "evidence_id", "semantic_field", "source_id", "as_of", "retrieved_at"
                )}
                for fact in facts
            ],
            "peer_candidate_group": None,
            "tool_context": {
                "mcp_server": "fixture_runtime",
                "logical_permissions": ["public_research.search", "public_research.fetch"],
                "required_identity_arguments": {
                    "run_id": run_id, "agent": agent, "invocation_id": invocation_id,
                },
            },
            "output_schema": material_semantic_schema(task),
        }
        packet_path = f"research/dispatch-packets/{canonical_hash({'packet': invocation_id})}.json"
        serialize_research_materials_dispatch_context(packet)
        _write_object(run_dir / packet_path, packet)
        tasks.append({
            **task, "task_path": task_path, "invocation_path": invocation_path,
            "packet_path": packet_path, "packet_hash": canonical_hash(packet), "depends_on": [],
        })
    index = {
        "schema_version": DISPATCH_VERSION, "run_id": run_id,
        "target_concurrency": target_concurrency, "tasks": tasks,
    }
    index["index_hash"] = legacy_envelope_hash(index, hash_field="index_hash")
    _write_object(run_dir / "research/dispatch-index.json", index)
    manifest = {
        "schema_version": STAGE_VERSION, "run_id": run_id,
        "stage": "MULTIDIMENSIONAL_MATERIAL_PREPARATION", "source_mode": "frozen-gate",
        **({"gate_input_binding": gate_input_binding} if gate_input_binding is not None else {}),
        "model": selected_model, "parent_model": selected_model, "output_dir": str(run_dir),
        "discovery": {"product_root": str(product_root)},
        "agent_bindings": agents, "skill_bindings": skills,
        "handoff_hash": handoff["handoff_hash"], "portfolio_hash": handoff["portfolio_hash"],
        "gate_hash": gate["bundle_hash"], "peer_candidate_pool_hash": pool["pool_hash"],
        "dispatch_index_hash": index["index_hash"], "target_concurrency": target_concurrency,
        "complete_portfolio_decision": False, "downstream_stages_started": [],
    }
    manifest["manifest_hash"] = legacy_envelope_hash(manifest, hash_field="manifest_hash")
    from product.runtime.evidence_gate import validate_frozen_gate_binding
    validate_frozen_gate_binding(run_dir, manifest, gate)
    _write_object(run_dir / "run_manifest.json", manifest)
    return {"status": "PREPARED", "run_id": run_id, "run_dir": str(run_dir), "task_count": len(tasks)}


def build_research_materials_dispatch_packet(
    repository_root: Path, run_dir: Path, task_name: str, *, include_dependency_reports: bool = True,
) -> dict[str, Any]:
    del repository_root, include_dependency_reports
    run_dir = Path(run_dir).resolve()
    index = _read_object(run_dir / "research/dispatch-index.json")
    matches = [item for item in index["tasks"] if item["task_name"] == task_name]
    if len(matches) != 1:
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_TASK_UNKNOWN")
    packet = _read_object(run_dir / matches[0]["packet_path"])
    if canonical_hash(packet) != matches[0]["packet_hash"]:
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_PACKET_HASH_MISMATCH")
    return packet


def build_research_materials_dispatch_message(
    repository_root: Path, run_dir: Path, task_name: str,
) -> str:
    del repository_root, run_dir
    return f"资料准备任务 {task_name}。等待 Hook 注入冻结任务包；只执行包内准备能力。"


def build_research_materials_stage_prompt(repository_root: Path, run_dir: Path) -> str:
    del repository_root
    index = _read_object(Path(run_dir).resolve() / "research/dispatch-index.json")
    task_map = {
        item["task_name"]: {
            "agent_type": item["agent"], "depends_on_task_names": [],
            "message": build_research_materials_dispatch_message(Path(), Path(run_dir), item["task_name"]),
        }
        for item in index["tasks"]
    }
    return f"""你是多维研究资料准备阶段的 Codex 主线程，只负责有界派发和归集，不开展正式研究或 CIO 决策。
读取 product/AGENTS.md；严格使用以下任务映射：
{json.dumps(task_map, ensure_ascii=False, sort_keys=True)}

使用 Agent 工具，agent_type、task_name、message 必须逐字复制任务映射，fork_turns=none；task_name 是映射中的裸名，不得改成 Agent 返回的 /root/... canonical 名称。先派发首批最多 {min(index['target_concurrency'], len(task_map))} 个任务，再用 wait_agent(timeout_ms=600000) 等待真实终态；有空位才按映射补派剩余任务。活跃任务期间不得调用 list_agents、followup_task、interrupt_agent 或短时 wait。不得启动 Skeptic、CIO、Risk，不得代替子 Agent 选择查询或同行。不得把已启动计作已完成；在仍有活跃 Subagent、缺少 SubagentStop 或任一任务尚无终态时禁止返回。等待全部结束后只返回：{{"stage":"MULTIDIMENSIONAL_MATERIAL_PREPARATION","run_id":"{index['run_id']}","dispatched":{len(task_map)},"completed":{len(task_map)}}}。
"""


def validate_material_preparation_output(
    value: Mapping[str, Any], *, task: Mapping[str, Any], run_dir: Path,
) -> None:
    from product.runtime.schema_validation import SchemaValidationError, validate_schema_instance
    try:
        validate_schema_instance(
            value,
            _output_schema(
                run_id=task["run_id"], invocation_id=task["invocation_id"],
                agent=task["agent"], kind=task["preparation_kind"],
            ),
        )
    except SchemaValidationError as exc:
        raise ResearchMaterialsStageError(f"RESEARCH_MATERIALS_OUTPUT_SCHEMA_INVALID:{exc}") from exc
    if value.get("security_id") != task.get("security_id"):
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_OUTPUT_SECURITY_INVALID")
    candidates = (
        task.get("peer_candidate_group", {}).get("candidates", [])
        if task["preparation_kind"] == "PEER_SELECTION" else []
    )
    candidate_ids = {item.get("candidate_id") for item in candidates}
    if task["preparation_kind"] == "PEER_SELECTION":
        if value["status"] == "BLOCKED_CONFIGURATION" or value["queries"] or any(
            item["candidate_id"] not in candidate_ids or item["document_id"] is not None
            for item in value["selections"]
        ):
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_PEER_SELECTION_INVALID")
    elif task["preparation_kind"] in DISCOVERY_KINDS:
        # fixture_mcp uses raw sha256(invocation_id) for the run-scoped directory.
        import hashlib
        material_root = run_dir / "research/materials" / hashlib.sha256(
            task["invocation_id"].encode("utf-8")
        ).hexdigest()[:16]
        searches = [_read_object(path) for path in material_root.glob("search-*.json")]
        documents = [_read_object(path) for path in material_root.glob("document-*.json")]
        fetch_attempts = [_read_object(path) for path in material_root.glob("fetch-*.json")]
        if not searches:
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_SEARCH_PROOF_MISSING")
        known_candidates = {
            item["candidate_id"] for result in searches for item in result.get("candidates", [])
        }
        known_documents = {item["document_id"]: item for item in documents}
        actual_queries = {item.get("query") for item in searches}
        declared_queries = {item["query"] for item in value["queries"]}
        if len(declared_queries) != len(value["queries"]) or actual_queries != declared_queries:
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_QUERY_PROOF_MISMATCH")
        for ordinal, item in enumerate(value["selections"]):
            if (item["candidate_id"] not in known_candidates
                    or item["document_id"] not in known_documents
                    or known_documents[item["document_id"]].get("candidate_id") != item["candidate_id"]):
                raise ResearchMaterialsStageError(
                    f"RESEARCH_MATERIALS_DOCUMENT_SELECTION_INVALID:selections[{ordinal}]"
                )
        expected_refs = {
            str(path.relative_to(run_dir))
            for path in material_root.glob("*.json")
        }
        unknown_refs = sorted(set(value["artifact_refs"]) - expected_refs)
        if unknown_refs:
            import hashlib
            fingerprint = hashlib.sha256(unknown_refs[0].encode("utf-8")).hexdigest()[:16]
            raise ResearchMaterialsStageError(
                f"RESEARCH_MATERIALS_ARTIFACT_REF_INVALID:first_unknown_sha256={fingerprint}"
            )
        event_path = run_dir / "events/mcp/events.jsonl"
        if event_path.is_file():
            artifact_hashes = {}
            for line in event_path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ResearchMaterialsStageError("RESEARCH_MATERIALS_TOOL_EVENT_INVALID") from exc
                if event.get("invocation_id") == task["invocation_id"] \
                        and isinstance(event.get("artifact_sha256"), str):
                    artifact_hashes.setdefault(event.get("artifact_ref"), set()).add(
                        event["artifact_sha256"]
                    )
                    if isinstance(event.get("attempt_sha256"), str):
                        artifact_hashes.setdefault(event.get("attempt_ref"), set()).add(
                            event["attempt_sha256"]
                        )
            if any(ref in artifact_hashes
                   and file_hash(run_dir / ref) not in artifact_hashes[ref]
                   for ref in value["artifact_refs"]):
                raise ResearchMaterialsStageError("RESEARCH_MATERIALS_ARTIFACT_HASH_MISMATCH")
        selected_document_refs = {
            str(path.relative_to(run_dir))
            for path in material_root.glob("document-*.json")
            if _read_object(path).get("document_id") in {
                item["document_id"] for item in value["selections"]
            }
        }
        if not selected_document_refs <= set(value["artifact_refs"]):
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_SELECTED_DOCUMENT_REF_MISSING")
        blocked_configuration = any(
            item.get("attempt_status") == "BLOCKED_CONFIGURATION"
            for item in [*searches, *fetch_attempts]
        )
        if value["status"] == "READY" and not value["selections"]:
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_READY_WITHOUT_DOCUMENT")
        if value["status"] == "BLOCKED_CONFIGURATION" and (
            value["selections"] or not blocked_configuration
        ):
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_CONFIGURATION_STATE_INVALID")
        if value["status"] == "SOURCE_LIMITED" and blocked_configuration and not value["selections"]:
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_CONFIGURATION_MASQUERADED_AS_SOURCE_LIMITED")
        if value["status"] != "READY" and not value["gaps"]:
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_LIMITATION_GAP_REQUIRED")
    else:
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_KIND_INVALID")


def finalize_research_materials_stage(repository_root: Path, run_dir: Path) -> dict[str, Any]:
    del repository_root
    run_dir = Path(run_dir).resolve()
    manifest = _read_object(run_dir / "run_manifest.json")
    index = _read_object(run_dir / "research/dispatch-index.json")
    event_path = run_dir / "invocation/subagent-events.jsonl"
    dispatch_path = run_dir / "invocation/subagent-dispatches.jsonl"
    if not event_path.is_file() or not dispatch_path.is_file():
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_EXECUTION_EVENTS_MISSING")
    events = [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    dispatches = [json.loads(line) for line in dispatch_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    expected_names = {item["task_name"] for item in index["tasks"]}
    if {item.get("task_name") for item in dispatches if item.get("decision") == "ALLOW"} != expected_names:
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_DISPATCH_PROOF_INCOMPLETE")
    captures = {
        item.get("output_capture", {}).get("task_id"): item.get("output_capture", {})
        for item in events
        if item.get("hook_event_name") == "SubagentStop"
        and item.get("output_capture", {}).get("status") == "SAVED"
    }
    failed_captures = {
        item.get("output_binding", {}).get("invocation_id"): item.get("output_capture", {})
        for item in events
        if item.get("hook_event_name") == "SubagentStop"
        and isinstance(item.get("output_binding"), Mapping)
        and item.get("output_capture", {}).get("status") == "FAILED"
    }
    outputs = []
    for task in index["tasks"]:
        capture = captures.get(task["task_id"])
        if capture is None:
            failed = failed_captures.get(task["invocation_id"])
            if failed is None:
                raise ResearchMaterialsStageError(
                    f"RESEARCH_MATERIALS_OUTPUT_MISSING:{task['task_id']}"
                )
            failure_code = str(failed.get("failure_code") or "RESEARCH_MATERIALS_OUTPUT_INVALID")
            outputs.append({
                "task_id": task["task_id"],
                "preparation_kind": task["preparation_kind"],
                "security_id": task["security_id"],
                "status": "FAILED",
                "output_ref": None,
                "output_hash": failed.get("rejected_output_hash"),
                "failure_code": failure_code,
                "selections": [],
                "gaps": [{
                    "reason_code": "RUNTIME_VALIDATION_FAILED",
                    "description": failure_code,
                    "impact": "该资料准备任务未形成可供正式研究消费的有效材料。",
                }],
                "artifact_refs": [],
            })
            continue
        output = _read_object(run_dir / capture["path"])
        validate_material_preparation_output(output, task=task, run_dir=run_dir)
        audit_binding = verify_material_tool_audit(run_dir, task, output, capture)
        outputs.append({
            "task_id": task["task_id"], "preparation_kind": task["preparation_kind"],
            "security_id": task["security_id"], "status": output["status"],
            "output_ref": capture["path"], "output_hash": canonical_hash(output),
            "selections": output["selections"], "gaps": output["gaps"],
            "artifact_refs": output["artifact_refs"],
            **audit_binding,
        })
    result = {
        "schema_version": "research-material-preparation-manifest/1.0.0",
        "run_id": manifest["run_id"], "handoff_hash": manifest["handoff_hash"],
        "portfolio_hash": manifest["portfolio_hash"], "gate_hash": manifest["gate_hash"],
        "gate_content_hash": canonical_hash({
            key: value for key, value in _read_object(run_dir / "evidence/gate.json").items()
            if key not in {"run_id", "bundle_hash"}
        }),
        "peer_candidate_pool_hash": manifest["peer_candidate_pool_hash"],
        "outputs": outputs, "complete_portfolio_decision": False,
    }
    result["manifest_hash"] = legacy_envelope_hash(result, hash_field="manifest_hash")
    _write_object(run_dir / "research/material-preparation-manifest.json", result)
    failed = [item for item in outputs if item["status"] == "FAILED"]
    return {
        "status": "PASSED", "run_id": manifest["run_id"],
        "completed": len(outputs) - len(failed), "expected": len(index["tasks"]),
        "coverage_complete": len(outputs) == len(index["tasks"]),
        "failed": [
            {"task_id": item["task_id"], "failure_code": item["failure_code"]}
            for item in failed
        ],
    }


def require_complete_research_materials_stage(run_dir: Path) -> None:
    """严格宿主验收：所有冻结资料任务均有唯一、合法的实际结果。"""
    run_dir = Path(run_dir).resolve()
    manifest = _read_object(run_dir / "run_manifest.json")
    index = _read_object(run_dir / "research/dispatch-index.json")
    preparation = _read_object(run_dir / "research/material-preparation-manifest.json")
    process = _read_object(run_dir / "invocation/process-result.json")
    tasks = index.get("tasks")
    outputs = preparation.get("outputs")
    if not isinstance(tasks, list) or not tasks or not isinstance(outputs, list):
        raise ResearchMaterialsStageError("REQUIRED_MATERIAL_TASK_SET_INVALID")
    expected = {item["task_id"]: item for item in tasks}
    if len(expected) != len(tasks):
        raise ResearchMaterialsStageError("REQUIRED_MATERIAL_TASK_SET_INVALID")
    if (
        manifest.get("manifest_hash") != legacy_envelope_hash(manifest, hash_field="manifest_hash")
        or index.get("index_hash") != legacy_envelope_hash(index, hash_field="index_hash")
        or manifest.get("dispatch_index_hash") != index.get("index_hash")
        or index.get("run_id") != manifest.get("run_id")
        or preparation.get("run_id") != manifest.get("run_id")
        or process.get("run_id") != manifest.get("run_id")
        or preparation.get("schema_version") != "research-material-preparation-manifest/1.0.0"
        or preparation.get("manifest_hash") != legacy_envelope_hash(preparation, hash_field="manifest_hash")
        or any(preparation.get(key) != manifest.get(key) for key in (
            "handoff_hash", "portfolio_hash", "gate_hash", "peer_candidate_pool_hash"
        ))
        or process.get("process_exit_code") != 0
        or process.get("timed_out") is not False
        or process.get("stage_status") != "PASSED"
        or process.get("source_integrity_unchanged") is not True
    ):
        raise ResearchMaterialsStageError("REQUIRED_MATERIAL_STAGE_BINDING_INVALID")
    if len(outputs) != len(tasks):
        raise ResearchMaterialsStageError("REQUIRED_MATERIAL_TASKS_INCOMPLETE")
    if any(not isinstance(item, Mapping) for item in outputs):
        raise ResearchMaterialsStageError("REQUIRED_MATERIAL_TASK_SET_INVALID")
    if any(item.get("status") not in {
        "READY", "SOURCE_LIMITED", "BLOCKED_CONFIGURATION"
    } for item in outputs):
        raise ResearchMaterialsStageError("REQUIRED_MATERIAL_TASK_FAILED")
    events = [json.loads(line) for line in (
        run_dir / "invocation/subagent-events.jsonl"
    ).read_text(encoding="utf-8").splitlines() if line.strip()]
    captures: dict[str, dict[str, Any]] = {}
    for event in events:
        if event.get("hook_event_name") != "SubagentStop":
            continue
        capture = event.get("output_capture")
        if not isinstance(capture, Mapping) or capture.get("status") != "SAVED":
            continue
        task_id = capture.get("task_id")
        if task_id not in expected or task_id in captures:
            raise ResearchMaterialsStageError("REQUIRED_MATERIAL_TASKS_INCOMPLETE")
        binding = event.get("output_binding")
        if not isinstance(binding, Mapping) or binding.get("invocation_id") != expected[task_id]["invocation_id"]:
            raise ResearchMaterialsStageError("REQUIRED_MATERIAL_OUTPUT_BINDING_INVALID")
        captures[task_id] = dict(capture)
    if set(captures) != set(expected):
        raise ResearchMaterialsStageError("REQUIRED_MATERIAL_TASKS_INCOMPLETE")
    seen: set[str] = set()
    for item in outputs:
        task_id = item.get("task_id")
        if task_id not in expected or task_id in seen:
            raise ResearchMaterialsStageError("REQUIRED_MATERIAL_TASKS_INCOMPLETE")
        seen.add(task_id)
        task = expected[task_id]
        ref = item.get("output_ref")
        if not isinstance(ref, str) or not ref:
            raise ResearchMaterialsStageError("REQUIRED_MATERIAL_OUTPUT_MISSING")
        if captures[task_id].get("path") != ref:
            raise ResearchMaterialsStageError("REQUIRED_MATERIAL_OUTPUT_BINDING_INVALID")
        path = (run_dir / ref).resolve()
        if not path.is_relative_to(run_dir / "research/material-results") or not path.is_file():
            raise ResearchMaterialsStageError("REQUIRED_MATERIAL_OUTPUT_REF_INVALID")
        result = _read_object(path)
        if (
            canonical_hash(result) != item.get("output_hash")
            or result.get("status") != item["status"]
            or item.get("preparation_kind") != task["preparation_kind"]
            or item.get("security_id") != task["security_id"]
        ):
            raise ResearchMaterialsStageError("REQUIRED_MATERIAL_OUTPUT_BINDING_INVALID")
        validate_material_preparation_output(result, task=task, run_dir=run_dir)
        binding = verify_material_tool_audit(run_dir, task, result, captures[task_id])
        if any(item.get(key) != value for key, value in binding.items()):
            raise ResearchMaterialsStageError("REQUIRED_MATERIAL_OUTPUT_BINDING_INVALID")


def materialize_selected_peers(
    materials_run: Path, *, source_access_path: Path, cache_root: Path,
    sec_user_agent: str, output_dir: Path,
    collector=None, peer_supplement_collector=None, memory_root: Path | None = None,
    now=lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """用现有只读采集器核实并冻结 LLM 选择的有限同行资料。"""

    from product.mcp.live.contracts import validate_contract
    from product.mcp.provenance import content_hash, iso_utc
    from product.runtime.evidence_gate import run_live_evidence_gate
    from product.mcp.live.market import load_locked_calendar
    from product.runtime.research_memory import ResearchMemory, resolve_memory_root

    materials_run = Path(materials_run).resolve()
    output_dir = Path(output_dir).resolve()
    cache_root = Path(cache_root).resolve()
    memory = (
        ResearchMemory(resolve_memory_root(Path(__file__).resolve().parents[2], memory_root))
        if memory_root is not None else None
    )
    if output_dir.exists():
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_OUTPUT_EXISTS")
    manifest = _read_object(materials_run / "research/material-preparation-manifest.json")
    if manifest.get("manifest_hash") != legacy_envelope_hash(manifest, hash_field="manifest_hash"):
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_MANIFEST_INVALID")
    pool = _read_object(materials_run / "research/peer-candidate-pool.json")
    validate_peer_candidate_pool(pool)
    candidates = {
        item["candidate_id"]: item
        for group in pool["groups"] for item in group["candidates"]
    }
    selected_candidates = []
    for output in manifest["outputs"]:
        if output["preparation_kind"] != "PEER_SELECTION":
            continue
        for selection in output["selections"]:
            candidate = candidates.get(selection["candidate_id"])
            if candidate is None:
                raise ResearchMaterialsStageError("PEER_MATERIALIZATION_CANDIDATE_UNKNOWN")
            selected_candidates.append({
                "holding_security_id": output["security_id"],
                "candidate_id": candidate["candidate_id"], "symbol": candidate["symbol"],
                "name": candidate["name"], "country": candidate.get("country"),
                "rationale": selection["rationale"],
                "materialized_security_id": f"US:COMMON_STOCK:{candidate['symbol']}",
            })
    access_records = _read_object_list(Path(source_access_path).resolve())
    approved_limits = [
        record.get("operator_approval", {}).get("record", {}).get("scope", {}).get("max_positions")
        for record in access_records
    ]
    approved_limits = [
        item for item in approved_limits
        if isinstance(item, int) and not isinstance(item, bool) and item > 0
    ]
    max_positions = min(approved_limits) if approved_limits else len(selected_candidates)
    unsupported = [
        {**item, "skip_reason": "SEC_IDENTITY_SCOPE_UNSUPPORTED"}
        for item in selected_candidates
        if item.get("country") not in {"United States", "US", "USA"}
    ]
    eligible_candidates = [
        item for item in selected_candidates
        if item.get("country") in {"United States", "US", "USA"}
    ]
    by_holding: dict[str, list[dict[str, Any]]] = {}
    holding_order: list[str] = []
    for item in eligible_candidates:
        holding = item["holding_security_id"]
        if holding not in by_holding:
            by_holding[holding] = []
            holding_order.append(holding)
        by_holding[holding].append(item)
    selected = []
    ordinal = 0
    while len(selected) < max_positions:
        added = False
        for holding in holding_order:
            values = by_holding[holding]
            if ordinal < len(values) and len(selected) < max_positions:
                selected.append(values[ordinal])
                added = True
        if not added:
            break
        ordinal += 1
    selected_keys = {
        (item["holding_security_id"], item["candidate_id"]) for item in selected
    }
    skipped = [
        {**item, "skip_reason": "SOURCE_ACCESS_POSITION_LIMIT"}
        for item in eligible_candidates
        if (item["holding_security_id"], item["candidate_id"]) not in selected_keys
    ] + unsupported
    unique = {item["materialized_security_id"]: item for item in selected}
    if not unique:
        result = {
            "schema_version": "peer-materialization/1.0.0", "status": "SOURCE_LIMITED",
            "materials_run_id": manifest["run_id"], "selected": [],
            "gaps": [{"reason_code": "NO_PEER_SELECTED", "impact": "正式同行比较没有已核实同行资料。"}],
        }
        result["materialization_hash"] = legacy_envelope_hash(result, hash_field="materialization_hash")
        output_dir.mkdir(parents=True)
        _write_object(output_dir / "peer-materialization-manifest.json", result)
        return result
    base_gate = _read_object(materials_run / "evidence/gate.json")
    base_content_hash = canonical_hash({
        key: value for key, value in base_gate.items() if key not in {"run_id", "bundle_hash"}
    })
    base_allowed = list(base_gate.get("allowed_evidence", []))
    existing = set(base_gate.get("input_evidence_ids", base_gate.get("allowed_evidence_ids", [])))
    existing_security_ids = {
        item.get("security_id") for item in base_allowed
        if isinstance(item.get("security_id"), str)
    }
    reused_security_ids = set(unique) & existing_security_ids
    collect_unique = {
        security_id: item for security_id, item in unique.items()
        if security_id not in reused_security_ids
    }
    selected = [{
        **item,
        "materialization_source": (
            "REUSED_FROZEN_GATE"
            if item["materialized_security_id"] in reused_security_ids
            else "COLLECTED_CURRENT_RUN"
        ),
    } for item in selected]
    timestamp = iso_utc(now())
    output_dir.mkdir(parents=True)
    portfolio = None
    snapshot = {"snapshot_hash": None, "gaps": []}
    peer_gate = {
        "bundle_hash": None,
        "decision_cutoff": base_gate["decision_cutoff"],
        "input_evidence_ids": [], "allowed_evidence": [],
        "excluded": [],
    }
    if collect_unique:
        portfolio = {
            "schema_version": "live-portfolio/2.0.0", "purpose": "COMMON_STOCK_DATA_COLLECTION",
            "base_currency": "USD", "source_id": f"peer-selection:{manifest['run_id']}",
            "as_of": timestamp, "retrieved_at": timestamp,
            "positions": [
                {"security_id": security_id, "ticker": item["symbol"], "exchange": None, "share_class": None}
                for security_id, item in sorted(collect_unique.items())
            ],
        }
        validate_contract("portfolio", portfolio)
        portfolio_path = output_dir / "peer-collection-input.json"
        _write_object(portfolio_path, portfolio)
        supplement_results = {}
        reused_bundle = None
        source_access = None
        if collector is None or peer_supplement_collector is not None:
            from product.mcp.live.collection import validate_live_collection_configuration
            from product.mcp.live.research_supplement_collection import (
                capture_external_research_results, capture_public_company_news_result,
            )
            source_access = validate_live_collection_configuration(
                Path(source_access_path).resolve(), at=now(),
            )
            if memory is not None and collector is None:
                from product.runtime.common_stock_data import _snapshot_bundle_cache_valid
                plans = [memory.plan(security_id, "live", "live_snapshot", planning_as_of=timestamp)
                         for security_id in collect_unique]
                if all(plan["mode"] == "SKIP_FRESH" for plan in plans):
                    first = memory.checkpoint(next(iter(collect_unique)), "live", "live_snapshot")
                    try:
                        candidate = memory.load_snapshot_bundle(first)
                        prior_ids = {item["security_id"] for item in candidate["portfolio"]["positions"]}
                        if (prior_ids == set(collect_unique)
                            and candidate.get("cache_root") == str(cache_root)
                            and candidate.get("source_item", {}).get("access_hash") == content_hash(source_access)
                            and isinstance(candidate.get("source_item", {}).get("supplement_results"), dict)
                            and _snapshot_bundle_cache_valid(candidate, cache_root=cache_root)
                            and all(memory.checkpoint(security_id, "live", "live_snapshot")
                                    .get("state", {}).get("snapshot_hash") == candidate["snapshot"]["snapshot_hash"]
                                    for security_id in collect_unique)):
                            reused_bundle = candidate
                    except (OSError, ValueError, KeyError, TypeError, AttributeError):
                        reused_bundle = None
            if reused_bundle is not None:
                supplement_results = reused_bundle["source_item"]["supplement_results"]
            else:
                supplement_results = (peer_supplement_collector or capture_external_research_results)(
                    portfolio["positions"], access=source_access, cache_root=cache_root,
                    state_root=output_dir / "peer-source-state", peer_scope=True,
                    now=lambda: iso_utc(now()),
                )
                for security_id, item in collect_unique.items():
                    supplement_results.setdefault(security_id, []).append(
                        capture_public_company_news_result(
                            security_id=security_id, ticker=item["symbol"],
                            issuer_name=item["name"], cache_root=cache_root,
                            decision_cutoff=base_gate["decision_cutoff"], now=now,
                        )
                    )
        collection_dir = output_dir / "source-snapshot"
        if reused_bundle is None:
            default_collector = collector is None
            collector = collector or __import__(
                "product.mcp.live.collection", fromlist=["collect_live_snapshot"]
            ).collect_live_snapshot
            collected = collector(
                portfolio_path, access_path=source_access_path, output_dir=collection_dir,
                cache_root=cache_root, sec_user_agent=sec_user_agent,
                **({"peer_scope": True} if default_collector else {}),
            )
            snapshot = _read_object(Path(collected["snapshot_path"]))
            calendar_record = _read_object(Path(collected["calendar_lock"]))
        else:
            from product.runtime.live_input import freeze_snapshot
            previous = reused_bundle["snapshot"]
            snapshot = freeze_snapshot(
                snapshot_id=f"peer-snapshot:{manifest['run_id']}",
                portfolio=portfolio, request_started_at=previous["request_started_at"],
                decision_cutoff=iso_utc(now()), facts=previous["facts"],
                source_access=previous["source_access"], raw_records=previous["raw_records"],
                collection_events=previous["collection_events"], gaps=previous["gaps"],
                identity=previous.get("identity"), universe=previous.get("universe"),
                source_selections=previous.get("source_selections"),
            )
            calendar_record = reused_bundle["calendar"]
            collection_dir.mkdir()
            _write_object(collection_dir / "snapshot.json", snapshot)
            _write_object(collection_dir / "calendar.json", calendar_record)
        peer_gate = run_live_evidence_gate(
            snapshot, run_id=manifest["run_id"], calendar=load_locked_calendar(calendar_record)
        ).artifact
        if supplement_results:
            from product.mcp.live.research_supplement_collection import build_research_supplements
            from product.runtime.common_stock_data import merge_research_supplement_evidence
            supplement_dir = output_dir / "peer-supplements"
            supplement_dir.mkdir()
            packages = build_research_supplements(
                portfolio["positions"], gate=peer_gate,
                external_results=supplement_results, run_id=manifest["run_id"],
            )
            prepared = {
                "gate": peer_gate,
                "preparation": {"common_cutoff": peer_gate["decision_cutoff"]},
            }
            for package in packages:
                security_id = package["security_id"]
                prepared = merge_research_supplement_evidence(
                    prepared, background=package["background"],
                    batch=package["batch"], package=package["package"],
                    allowed_security_ids={security_id},
                )
                _write_object(supplement_dir / f"{package['ticker']}-background.json", package["background"])
                _write_object(supplement_dir / f"{package['ticker']}-batch.json", package["batch"])
                _write_object(supplement_dir / f"{package['ticker']}-package.json", package["package"])
            peer_gate = prepared["gate"]
        if memory is not None:
            from product.runtime.research_memory import infer_dataset, infer_provider
            source_item = {
                "access_hash": content_hash(source_access),
                "supplement_results": supplement_results,
            }
            for security_id in collect_unique:
                if reused_bundle is None:
                    with memory.dataset_lock(security_id, "live", "live_snapshot"):
                        plan = memory.plan(
                            security_id, "live", "live_snapshot",
                            planning_as_of=iso_utc(now()),
                        )
                        stored = memory.store_snapshot_bundle(
                            security_id=security_id, portfolio=portfolio,
                            snapshot=snapshot, calendar=calendar_record,
                            source_item=source_item, cache_root=cache_root,
                        )
                        memory.ingest_dataset(
                            plan=plan, facts=[],
                            status=("FETCHED_BOOTSTRAP" if plan["mode"] == "BOOTSTRAP"
                                    else "FETCHED_INCREMENTAL"),
                            completed_at=snapshot["decision_cutoff"],
                            details={"request_count": len(snapshot.get("collection_events", [])),
                                     "source_result": "PEER_SNAPSHOT_FROZEN"},
                            state={"object_ref": stored["object_ref"],
                                   "object_hash": stored["object_hash"],
                                   "snapshot_hash": snapshot["snapshot_hash"]},
                        )
                facts = [fact for fact in peer_gate["allowed_evidence"]
                         if fact.get("security_id") == security_id]
                grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
                for fact in facts:
                    grouped.setdefault((infer_provider(fact), infer_dataset(fact)), []).append(fact)
                for (provider, dataset), dataset_facts in sorted(grouped.items()):
                    with memory.dataset_lock(security_id, provider, dataset):
                        plan = memory.plan(
                            security_id, provider, dataset,
                            planning_as_of=iso_utc(now()),
                        )
                        new_versions = memory.new_version_count(dataset_facts)
                        if plan["mode"] == "SKIP_FRESH" and not new_versions:
                            continue
                        memory.ingest_dataset(
                            plan=plan, facts=dataset_facts,
                            status=("FETCHED_BOOTSTRAP" if plan["mode"] == "BOOTSTRAP"
                                    else "FETCHED_INCREMENTAL" if new_versions
                                    else "CHECKED_NO_CHANGE"),
                            completed_at=snapshot["decision_cutoff"],
                            watermark=max((fact["as_of"] for fact in dataset_facts),
                                          key=parse_timestamp),
                            details={"request_count": 0,
                                     "source_result": "PEER_GATE_VERSIONED"},
                        )
                view = memory.save_view(
                    run_id=manifest["run_id"], security_id=security_id,
                    decision_cutoff=peer_gate["decision_cutoff"], facts=facts,
                    gaps=snapshot.get("gaps", []), conflicts=[],
                )
                view_dir = output_dir / "peer-views"
                view_dir.mkdir(exist_ok=True)
                _write_object(view_dir / f"{collect_unique[security_id]['symbol']}.json", view)
            if reused_bundle is not None:
                selected = [
                    {**item, "materialization_source": "REUSED_RESEARCH_MEMORY"}
                    if item["materialized_security_id"] in collect_unique else item
                    for item in selected
                ]
    peer_facts = [
        item for item in peer_gate["allowed_evidence"]
        if item.get("security_id") in set(collect_unique)
    ]
    if any(item["evidence_id"] in existing for item in peer_facts):
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_EVIDENCE_DUPLICATE")
    reused_facts = [
        item for item in base_allowed
        if item.get("security_id") in reused_security_ids
    ]
    allowed = [*base_gate.get("allowed_evidence", []), *peer_facts]
    excluded = [*base_gate.get("excluded", []), *peer_gate.get("excluded", [])]
    final_cutoff = _verify_merged_peer_gate_time(
        base_gate, peer_gate, allowed, excluded, observed_at=iso_utc(now()),
        calendar=(load_locked_calendar(calendar_record) if collect_unique else None),
    )
    merged_gate = {
        **base_gate,
        "decision_cutoff": final_cutoff,
        "peer_gate_hash": peer_gate["bundle_hash"],
        "base_gate_content_hash": base_content_hash,
        "input_evidence_ids": sorted(existing | set(peer_gate.get("input_evidence_ids", []))),
        "allowed_evidence": sorted(allowed, key=lambda item: item["evidence_id"]),
        "allowed_evidence_ids": sorted(item["evidence_id"] for item in allowed),
        "excluded": sorted(excluded, key=lambda item: item["evidence_id"]),
        "excluded_evidence_ids": sorted(item["evidence_id"] for item in excluded),
    }
    merged_gate["bundle_hash"] = legacy_envelope_hash(merged_gate, hash_field="bundle_hash")
    _write_object(output_dir / "gate.json", merged_gate)
    final_view = {
        "schema_version": "peer-final-evidence-view/1.0.0",
        "run_id": manifest["run_id"], "decision_cutoff": final_cutoff,
        "gate_hash": merged_gate["bundle_hash"],
        "allowed_evidence_ids": merged_gate["allowed_evidence_ids"],
        "excluded_evidence_ids": merged_gate["excluded_evidence_ids"],
        "selected_peer_security_ids": sorted(unique),
    }
    final_view["view_hash"] = legacy_envelope_hash(final_view, hash_field="view_hash")
    _write_object(output_dir / "final-view.json", final_view)
    result = {
        "schema_version": "peer-materialization/1.0.0", "status": "FROZEN",
        "materials_run_id": manifest["run_id"], "selected": selected,
        "portfolio_hash": content_hash(portfolio) if portfolio is not None else None,
        "snapshot_hash": snapshot["snapshot_hash"],
        "peer_gate_hash": peer_gate["bundle_hash"], "merged_gate_hash": merged_gate["bundle_hash"],
        "final_view_hash": final_view["view_hash"],
        "base_gate_content_hash": base_content_hash,
        "evidence_ids": sorted(item["evidence_id"] for item in [*reused_facts, *peer_facts]),
        "skipped": [{
            "holding_security_id": item["holding_security_id"],
            "candidate_id": item["candidate_id"],
            "symbol": item["symbol"],
            "reason_code": item["skip_reason"],
        } for item in skipped],
        "gaps": [
            *list(snapshot.get("gaps", [])),
            *([{
                "reason_code": "PEER_MATERIALIZATION_BOUNDED",
                "impact": (
                    f"本批访问批准最多覆盖 {max_positions} 个证券；其余 "
                    f"{len(skipped)} 个已选候选因访问上限或当前 SEC 身份范围未物化，"
                    "也未进入正式比较 Evidence。"
                ),
            }] if skipped else []),
        ],
    }
    result["materialization_hash"] = legacy_envelope_hash(result, hash_field="materialization_hash")
    _write_object(output_dir / "peer-materialization-manifest.json", result)
    return result


def launch_research_materials_stage(
    repository_root: Path, *, run_dir: Path, codex_binary: str = "codex",
    timeout_seconds: int = 1800,
) -> tuple[dict[str, Any], int]:
    from product.runtime.nested_codex import (
        build_nested_codex_command,
        fixture_mcp_runtime_environment,
        integrity_snapshot,
    )
    repository_root = Path(repository_root).resolve()
    product_root = repository_root / "product"
    run_dir = Path(run_dir).resolve()
    manifest = _read_object(run_dir / "run_manifest.json")
    if manifest.get("schema_version") != STAGE_VERSION or manifest.get("stage") != "MULTIDIMENSIONAL_MATERIAL_PREPARATION":
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_MANIFEST_INVALID")
    from product.runtime.evidence_gate import validate_frozen_gate_binding
    validate_frozen_gate_binding(run_dir, manifest, _read_object(run_dir / "evidence/gate.json"))
    for task in _read_object(run_dir / "research/dispatch-index.json")["tasks"]:
        packet = build_research_materials_dispatch_packet(repository_root, run_dir, task["task_name"])
        invocation = _read_object(run_dir / task["invocation_path"])
        if any(not isinstance(item, Mapping) or item.get("semantic_output_version") != SEMANTIC_OUTPUT_VERSION
               for item in (task, packet.get("task"), invocation)):
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_LEGACY_OUTPUT_EXECUTION_RETIRED")
        serialize_research_materials_dispatch_context(packet)
    invocation_dir = run_dir / "invocation"
    if invocation_dir.exists():
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_ALREADY_LAUNCHED")
    invocation_dir.mkdir()
    runtime_root = run_dir / ".codex-runtime"
    sqlite_home, log_dir, tmp_dir = runtime_root / "sqlite", runtime_root / "logs", runtime_root / "tmp"
    for path in (sqlite_home, log_dir, tmp_dir):
        path.mkdir(parents=True, exist_ok=False)
    prompt = build_research_materials_stage_prompt(repository_root, run_dir)
    prompt_path = invocation_dir / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    task_count = len(_read_object(run_dir / "research/dispatch-index.json")["tasks"])
    schema = _parent_output_schema(manifest["run_id"], task_count)
    schema_path = invocation_dir / "parent-output.schema.json"
    _write_object(schema_path, schema)
    raw_final_path = tmp_dir / "final-message.json"
    command = build_nested_codex_command(
        codex_binary=codex_binary, product_root=product_root, run_dir=run_dir,
        model=manifest["parent_model"], sqlite_home=sqlite_home, log_dir=log_dir,
        final_message_path=raw_final_path,
        hook_recorder_path=product_root / "runtime/codex_hook_recorder.py",
        output_schema_path=schema_path, fixture_mcp_run_dir=run_dir,
        hook_agent_matcher="^(runtime_company_analyst|runtime_market_catalyst)$",
    )
    # Match the formal multidimensional stage's frozen specialist loading.
    # Desktop-only user MCP fields are not accepted by the strict host CLI.
    command.insert(command.index("exec") + 1, "--ignore-user-config")
    product_agents = tomllib.loads(
        (product_root / ".codex/config.toml").read_text(encoding="utf-8")
    )["agents"]
    index = _read_object(run_dir / "research/dispatch-index.json")
    for agent_name in sorted({item["agent"] for item in index["tasks"]}):
        agent_config = product_agents.get(agent_name)
        if not isinstance(agent_config, Mapping):
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_AGENT_CONFIG_MISSING")
        agent_path = (product_root / ".codex" / agent_config["config_file"]).resolve()
        if not agent_path.is_relative_to(product_root / ".codex") or not agent_path.is_file():
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_AGENT_CONFIG_INVALID")
        command.extend((
            "-c", f"agents.{agent_name}={{"
            f"description={json.dumps(agent_config['description'], ensure_ascii=False)},"
            f"config_file={json.dumps(str(agent_path))}}}",
        ))
    command.extend(("-c", f"agents.max_threads={product_agents['max_threads']}"))
    events_path = invocation_dir / "codex-events.jsonl"
    stderr_path = invocation_dir / "codex-stderr.log"
    hook_events = invocation_dir / "subagent-events.jsonl"
    dispatch_events = invocation_dir / "subagent-dispatches.jsonl"
    environment = dict(os.environ)
    environment.update({
        "TMPDIR": str(tmp_dir), "PYTHONDONTWRITEBYTECODE": "1",
        "STOCK_AGENT_RUN_DIR": str(run_dir), "STOCK_AGENT_FIXTURE_MCP_RUN_DIR": str(run_dir),
        "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(hook_events),
        "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(dispatch_events),
        "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": "runtime_company_analyst,runtime_market_catalyst",
        "STOCK_AGENT_RESEARCH_MATERIALS_STAGE": STAGE_VERSION,
        **fixture_mcp_runtime_environment(),
    })
    environment.pop("STOCK_AGENT_START_CONTEXT", None)
    environment.pop("STOCK_AGENT_CAPTURE_SPECIALIST_OUTPUT", None)
    before = integrity_snapshot(repository_root)
    try:
        process = subprocess.run(
            command, input=prompt, text=True, cwd=product_root, env=environment,
            capture_output=True, timeout=timeout_seconds, check=False,
        )
        stdout, stderr, code, timed_out = process.stdout, process.stderr, process.returncode, False
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        code, timed_out = 124, True
    events_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    failure_code = None
    try:
        if timed_out or code != 0 or not raw_final_path.is_file():
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_CODEX_FAILED")
        final = _read_object(raw_final_path)
        _write_object(invocation_dir / "final-message.json", final)
        if final != {
            "stage": "MULTIDIMENSIONAL_MATERIAL_PREPARATION",
            "run_id": manifest["run_id"], "dispatched": task_count,
            "completed": task_count,
        }:
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_FINAL_MESSAGE_INVALID")
        result = finalize_research_materials_stage(repository_root, run_dir)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        failure_code = str(exc).split(":", 1)[0]
        result = {"status": "FAILED", "run_id": manifest["run_id"], "failure_code": failure_code}
    after = integrity_snapshot(repository_root)
    _write_object(invocation_dir / "process-result.json", {
        "schema_version": "research-materials-process/1.0.0", "run_id": manifest["run_id"],
        "process_exit_code": code, "timed_out": timed_out, "stage_status": result["status"],
        "failure_code": failure_code, "source_integrity_unchanged": before == after,
        "prompt_hash": file_hash(prompt_path),
    })
    return result, 0 if result["status"] == "PASSED" and before == after else 7
