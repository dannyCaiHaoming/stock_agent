"""多维研究的显式资料准备阶段；只选择和取得资料，不形成投资结论。"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from product.intake.v3 import validate_handoff
from product.mcp.live.peer_candidates import validate_peer_candidate_pool
from product.mcp.provenance import parse_timestamp
from product.runtime.hashing import canonical_hash, file_hash

from .multidimensional_stage import (
    _agent_binding,
    _facts_for_capability,
    _read_object,
    _skill_binding,
    _write_object,
)


STAGE_VERSION = "multidimensional-material-preparation-runtime/1.0.0"
DISPATCH_VERSION = "multidimensional-material-preparation-dispatch/1.0.0"


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


def _read_object_list(path: Path) -> list[dict[str, Any]]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_SOURCE_ACCESS_INVALID") from exc
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_SOURCE_ACCESS_INVALID")
    return [dict(item) for item in value]


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
    return {
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
            "selections": {"type": "array", "maxItems": 5 if kind == "RESEARCH_REPORT_DISCOVERY" else 3, "items": selection},
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


def prepare_research_materials_stage(
    repository_root: Path, *, handoff_path: Path, gate_path: Path,
    peer_candidate_pool_path: Path, run_dir: Path, run_id: str,
    model: str, target_concurrency: int = 3,
) -> dict[str, Any]:
    """准备 Company/Market 两类资料任务；不启动模型或网络。"""

    repository_root = Path(repository_root).resolve()
    product_root = repository_root / "product"
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
    if gate.get("run_id") not in {None, run_id}:
        raise ResearchMaterialsStageError("RESEARCH_MATERIALS_GATE_RUN_MISMATCH")
    gate["run_id"] = run_id
    gate["source_mode"] = gate.get("source_mode", "fixture")
    gate["bundle_hash"] = canonical_hash({key: value for key, value in gate.items() if key != "bundle_hash"})
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
        for name in ("research-report-analysis", "industry-comparison")
    }
    run_dir.mkdir(parents=True)
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
                "peer_candidate_group": groups[security_id] if kind == "PEER_SELECTION" else None,
            }
            task["task_hash"] = canonical_hash(task)
            task_path = f"research/tasks/{canonical_hash({'task_id': task_id})}.json"
            _write_object(run_dir / task_path, task)
            instruction = (
                "这是资料准备而非正式投资研究。根据证券身份与当前公司问题构造至多三条精确查询，"
                "实际调用 research_search；只对返回候选调用 research_fetch。搜索标题/摘要只是线索，"
                "只有 BODY_VERIFIED 正文可选择。不得使用通用 Web、模型记忆或输出投资动作；来源受限时"
                "保留实际错误和影响。缺少正文 API key 等配置问题必须输出 BLOCKED_CONFIGURATION，"
                "不得写成 SOURCE_LIMITED；每个受限结论必须引用工具返回的实际尝试产物。"
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
            }
            invocation["manifest_hash"] = canonical_hash(invocation)
            invocation_path = f"invocations/by-id/{canonical_hash({'invocation_id': invocation_id})}.json"
            _write_object(run_dir / invocation_path, invocation)
            facts = _facts_for_capability(
                gate.get("allowed_evidence", []), capability="FUNDAMENTAL_EVENT",
                security_ids=[security_id], benchmark_id=None,
            )
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
                "output_schema": _output_schema(
                    run_id=run_id, invocation_id=invocation_id, agent=agent, kind=kind,
                ),
            }
            packet_path = f"research/dispatch-packets/{canonical_hash({'packet': invocation_id})}.json"
            _write_object(run_dir / packet_path, packet)
            tasks.append({
                **task, "task_path": task_path, "invocation_path": invocation_path,
                "packet_path": packet_path, "packet_hash": canonical_hash(packet), "depends_on": [],
            })
    index = {
        "schema_version": DISPATCH_VERSION, "run_id": run_id,
        "target_concurrency": target_concurrency, "tasks": tasks,
    }
    index["index_hash"] = canonical_hash(index)
    _write_object(run_dir / "research/dispatch-index.json", index)
    manifest = {
        "schema_version": STAGE_VERSION, "run_id": run_id,
        "stage": "MULTIDIMENSIONAL_MATERIAL_PREPARATION", "source_mode": "frozen-gate",
        "model": selected_model, "parent_model": selected_model, "output_dir": str(run_dir),
        "discovery": {"product_root": str(product_root)},
        "agent_bindings": agents, "skill_bindings": skills,
        "handoff_hash": handoff["handoff_hash"], "portfolio_hash": handoff["portfolio_hash"],
        "gate_hash": gate["bundle_hash"], "peer_candidate_pool_hash": pool["pool_hash"],
        "dispatch_index_hash": index["index_hash"], "target_concurrency": target_concurrency,
        "complete_portfolio_decision": False, "downstream_stages_started": [],
    }
    manifest["manifest_hash"] = canonical_hash(manifest)
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

使用 Agent 工具，agent_type、task_name、message 来自映射，fork_turns=none；最多同时保持 {min(index['target_concurrency'], len(task_map))} 个活跃 Subagent。不得启动 Skeptic、CIO、Risk，不得代替子 Agent 选择查询或同行。每次派发后必须通过 wait 等待终态；并发槽位不足时先等待再补位，不得把已启动计作已完成。在仍有活跃 Subagent、缺少 SubagentStop 或任一任务尚无终态时禁止返回。等待全部结束后只返回：{{"stage":"MULTIDIMENSIONAL_MATERIAL_PREPARATION","run_id":"{index['run_id']}","dispatched":{len(task_map)},"completed":{len(task_map)}}}。
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
    else:
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
        if any(
            item["candidate_id"] not in known_candidates
            or item["document_id"] not in known_documents
            or known_documents[item["document_id"]].get("candidate_id") != item["candidate_id"]
            for item in value["selections"]
        ):
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_DOCUMENT_SELECTION_INVALID")
        expected_refs = {
            str(path.relative_to(run_dir))
            for path in material_root.glob("*.json")
        }
        if not set(value["artifact_refs"]) <= expected_refs:
            raise ResearchMaterialsStageError("RESEARCH_MATERIALS_ARTIFACT_REF_INVALID")
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
        outputs.append({
            "task_id": task["task_id"], "preparation_kind": task["preparation_kind"],
            "security_id": task["security_id"], "status": output["status"],
            "output_ref": capture["path"], "output_hash": canonical_hash(output),
            "selections": output["selections"], "gaps": output["gaps"],
            "artifact_refs": output["artifact_refs"],
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
    result["manifest_hash"] = canonical_hash(result)
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


def materialize_selected_peers(
    materials_run: Path, *, source_access_path: Path, cache_root: Path,
    sec_user_agent: str, output_dir: Path,
    collector=None, now=lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """用现有只读采集器核实并冻结 LLM 选择的有限同行资料。"""

    from product.mcp.live.contracts import validate_contract
    from product.mcp.provenance import content_hash, iso_utc
    from product.runtime.evidence_gate import run_live_evidence_gate
    from product.mcp.live.market import load_locked_calendar

    materials_run = Path(materials_run).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise ResearchMaterialsStageError("PEER_MATERIALIZATION_OUTPUT_EXISTS")
    manifest = _read_object(materials_run / "research/material-preparation-manifest.json")
    if manifest.get("manifest_hash") != canonical_hash({
        key: value for key, value in manifest.items() if key != "manifest_hash"
    }):
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
        result["materialization_hash"] = canonical_hash(result)
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
        collector = collector or __import__(
            "product.mcp.live.collection", fromlist=["collect_live_snapshot"]
        ).collect_live_snapshot
        collection_dir = output_dir / "source-snapshot"
        collected = collector(
            portfolio_path, access_path=source_access_path, output_dir=collection_dir,
            cache_root=cache_root, sec_user_agent=sec_user_agent,
        )
        snapshot = _read_object(Path(collected["snapshot_path"]))
        calendar_record = _read_object(Path(collected["calendar_lock"]))
        peer_gate = run_live_evidence_gate(
            snapshot, run_id=manifest["run_id"], calendar=load_locked_calendar(calendar_record)
        ).artifact
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
    merged_gate = {
        **base_gate,
        "decision_cutoff": max(
            parse_timestamp(base_gate["decision_cutoff"]), parse_timestamp(peer_gate["decision_cutoff"])
        ).isoformat().replace("+00:00", "Z"),
        "base_gate_content_hash": base_content_hash,
        "input_evidence_ids": sorted(existing | set(peer_gate.get("input_evidence_ids", []))),
        "allowed_evidence": sorted(allowed, key=lambda item: item["evidence_id"]),
        "allowed_evidence_ids": sorted(item["evidence_id"] for item in allowed),
        "excluded": sorted(excluded, key=lambda item: item["evidence_id"]),
        "excluded_evidence_ids": sorted(item["evidence_id"] for item in excluded),
    }
    merged_gate["bundle_hash"] = canonical_hash({
        key: value for key, value in merged_gate.items() if key != "bundle_hash"
    })
    _write_object(output_dir / "gate.json", merged_gate)
    result = {
        "schema_version": "peer-materialization/1.0.0", "status": "FROZEN",
        "materials_run_id": manifest["run_id"], "selected": selected,
        "portfolio_hash": content_hash(portfolio) if portfolio is not None else None,
        "snapshot_hash": snapshot["snapshot_hash"],
        "peer_gate_hash": peer_gate["bundle_hash"], "merged_gate_hash": merged_gate["bundle_hash"],
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
    result["materialization_hash"] = canonical_hash(result)
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
