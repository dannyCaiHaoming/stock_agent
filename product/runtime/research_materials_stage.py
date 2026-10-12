"""多维研究的显式资料准备阶段；只选择和取得资料，不形成投资结论。"""

from __future__ import annotations

import copy
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from product.runtime.research_input import (
    artifact_input_binding, is_single_stock, load_research_input,
    research_input_binding, research_input_ref, research_subjects, validate_research_input,
)
from product.mcp.live.peer_candidates import validate_peer_candidate_pool
from product.mcp.provenance import parse_timestamp
from product.runtime.hashing import canonical_hash, file_hash, legacy_envelope_hash
from product.runtime.schema_validation import validate_schema_definition, validate_schema_instance
from product.tools.material_contracts import _output_schema
from product.tools.peer_materialization import (
    _read_object_list, _verify_merged_peer_gate_time, materialize_selected_peers,
)
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
SINGLE_STOCK_STAGE_VERSION = "multidimensional-material-preparation-runtime/2.0.0"
DISPATCH_VERSION = "multidimensional-material-preparation-dispatch/1.2.0"
SEMANTIC_OUTPUT_VERSION = "research-material-semantic-draft/1.0.0"
MATERIAL_START_CONTEXT_MAX_BYTES = 256 * 1024
DISCOVERY_KINDS = {
    "RESEARCH_REPORT_DISCOVERY",
    "MACRO_RESEARCH_DISCOVERY",
    "MARKET_RESEARCH_DISCOVERY",
}


from product.tools.peer_materialization import PeerMaterializationError as ResearchMaterialsStageError


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
    repository_root: Path, *, handoff_path: Path | None = None, research_input_path: Path | None = None, gate_path: Path,
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
    if (handoff_path is None) == (research_input_path is None):
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_INPUT_PATH_INVALID")
    handoff = _read_object(Path(research_input_path or handoff_path).resolve())
    validate_research_input(handoff)
    if research_input_path is not None and not is_single_stock(handoff):
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_SINGLE_STOCK_REQUIRED")
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
    if is_single_stock(handoff) and cutoff != handoff["resolved_cutoff"]:
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_INPUT_CUTOFF_MISMATCH")
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
        item for item in research_subjects(handoff)
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
    _write_object(run_dir / research_input_ref(handoff), handoff)
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
                    **(research_input_binding(handoff) if is_single_stock(handoff) else {}),
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
        if is_single_stock(handoff):
            instruction = instruction.replace('根据当前持仓与截止时点', '根据当前研究标的与截止时点')
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
                **(research_input_binding(handoff) if is_single_stock(handoff) else {}),
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
        "schema_version": SINGLE_STOCK_STAGE_VERSION if is_single_stock(handoff) else STAGE_VERSION, "run_id": run_id,
        "stage": "MULTIDIMENSIONAL_MATERIAL_PREPARATION", "source_mode": "frozen-gate",
        **({"gate_input_binding": gate_input_binding} if gate_input_binding is not None else {}),
        "model": selected_model, "parent_model": selected_model, "output_dir": str(run_dir),
        "discovery": {"product_root": str(product_root)},
        "agent_bindings": agents, "skill_bindings": skills,
        **(research_input_binding(handoff) if is_single_stock(handoff) else {
            "handoff_hash": handoff["handoff_hash"], "portfolio_hash": handoff["portfolio_hash"]}),
        "gate_hash": gate["bundle_hash"], "peer_candidate_pool_hash": pool["pool_hash"],
        "dispatch_index_hash": index["index_hash"], "target_concurrency": target_concurrency,
        "complete_portfolio_decision": False, "downstream_stages_started": [],
    }
    if is_single_stock(handoff):
        from product.runtime.research_input import single_stock_contract_locks
        manifest["input_contract_locks"] = single_stock_contract_locks(product_root)
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
        "schema_version": "research-material-preparation-manifest/2.0.0" if is_single_stock(manifest) else "research-material-preparation-manifest/1.0.0",
        "run_id": manifest["run_id"],
        **(artifact_input_binding(manifest) if is_single_stock(manifest) else {
            "handoff_hash": manifest["handoff_hash"], "portfolio_hash": manifest["portfolio_hash"]}),
        "gate_hash": manifest["gate_hash"],
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
    if is_single_stock(manifest):
        load_research_input(run_dir, manifest=manifest)
        from product.runtime.research_input import single_stock_contract_locks
        if manifest.get("input_contract_locks") != single_stock_contract_locks(Path(__file__).resolve().parents[1]):
            raise ResearchMaterialsStageError("SINGLE_STOCK_CONTRACT_LOCK_DRIFT")
    binding_keys = (tuple(artifact_input_binding(manifest)) if is_single_stock(manifest) else (
        "handoff_hash", "portfolio_hash")) + ("gate_hash", "peer_candidate_pool_hash")
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
        or preparation.get("schema_version") != ("research-material-preparation-manifest/2.0.0" if is_single_stock(manifest) else "research-material-preparation-manifest/1.0.0")
        or preparation.get("manifest_hash") != legacy_envelope_hash(preparation, hash_field="manifest_hash")
        or any(preparation.get(key) != manifest.get(key) for key in binding_keys)
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





def launch_research_materials_stage(
    repository_root: Path, *, run_dir: Path, codex_binary: str = "codex",
    timeout_seconds: int = 1800,
) -> tuple[dict[str, Any], int]:
    """旧正常模型启动已退役；历史读取不依赖此入口。"""
    raise ResearchMaterialsStageError("NATIVE_HOST_EXECUTION_REQUIRED:使用当前宿主portfolio-council原生会话；旧执行维护仅限明确批准的冻结版本。")
