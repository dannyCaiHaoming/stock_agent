"""独立反证阶段的确定性前置门禁与第一轮 Evidence 授权。"""

from __future__ import annotations

import json
import hashlib
import copy
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.council.intake_planning import validate_council_request
from product.intake.v3 import validate_handoff
from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.multidimensional_stage import check_multidimensional_bundle_consumable
from product.runtime.validation import collect_evidence_refs


STAGE = "INDEPENDENT_COUNTER_THESIS_RESEARCH"
DISPATCH_VERSION = "independent-skeptic-dispatch/1.0.0"
INITIAL_INDEX_REF = "research/skeptic/dispatch-index.json"
CORE_CAPABILITIES = frozenset({
    "COMPANY_RESEARCH", "TECHNICAL_STRUCTURE", "FUNDAMENTAL_EVENT",
    "INDUSTRY_COMPARISON", "MACRO_CONTEXT", "MARKET_STATE",
})
READY_CORE_STATUSES = frozenset({
    "COMPLETE", "LOW_CONFIDENCE", "INSUFFICIENT_EVIDENCE", "SOURCE_LIMITED",
})
FIRST_PASS_KEYS = frozenset({
    "run_id", "agent", "mode", "source_mode", "security_id", "research_question",
    "holding_horizon", "decision_cutoff", "request_id", "gate_hash",
    "allowed_evidence_ids", "scope_limitations", "report_schema_version", "attempt_id",
})


class IndependentSkepticStageError(ValueError):
    pass


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IndependentSkepticStageError(f"COUNTER_INPUT_INVALID:{path.name}") from exc
    if not isinstance(value, dict):
        raise IndependentSkepticStageError(f"COUNTER_INPUT_INVALID:{path.name}")
    return value


def _without_hash(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    return {name: item for name, item in value.items() if name != key}


def validate_report_query_closure(
    report: Mapping[str, Any], queries: Sequence[Mapping[str, Any]],
) -> set[str]:
    """要求报告所引事实均由同一 Invocation 的已认证查询实际读取。"""

    queried_evidence_ids = {
        evidence_id
        for query in queries
        for evidence_id in query.get("evidence_ids", [])
        if isinstance(evidence_id, str)
    }
    unqueried_refs = collect_evidence_refs(report) - queried_evidence_ids
    if unqueried_refs:
        raise IndependentSkepticStageError(
            "COUNTER_REPORT_EVIDENCE_NOT_QUERIED:"
            + ",".join(sorted(unqueried_refs))
        )
    return queried_evidence_ids


def _index_ref(attempt: int) -> str:
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise IndependentSkepticStageError("COUNTER_ATTEMPT_INVALID")
    return INITIAL_INDEX_REF if attempt == 1 else f"research/skeptic/attempts/{attempt}/dispatch-index.json"


def read_dispatch_index(run_dir: Path, index_ref: str | None = None) -> dict[str, Any]:
    relative = INITIAL_INDEX_REF if index_ref is None else index_ref
    if relative != INITIAL_INDEX_REF and re.fullmatch(
        r"research/skeptic/attempts/(?:[2-9]|[1-9][0-9]+)/dispatch-index\.json", relative
    ) is None:
        raise IndependentSkepticStageError("COUNTER_DISPATCH_INDEX_PATH_INVALID")
    root = Path(run_dir).resolve()
    index = _read(root / relative)
    if (index.get("schema_version") != DISPATCH_VERSION
            or index.get("index_hash") != canonical_hash(_without_hash(index, "index_hash"))):
        raise IndependentSkepticStageError("COUNTER_DISPATCH_INDEX_INVALID")
    if _index_ref(index.get("attempt")) != relative:
        raise IndependentSkepticStageError("COUNTER_DISPATCH_ATTEMPT_INVALID")
    return index


def resolve_skeptic_tool_scope(
    run_dir: Path, *, run_id: str, invocation_id: str, gate: Mapping[str, Any],
    index_ref: str | None = None,
) -> tuple[Path, list[str]]:
    """服务端从可信映射解析权限；调用者不能提交任意路径或 Evidence 集合。"""

    root = Path(run_dir).resolve()
    index = read_dispatch_index(root, index_ref)
    if index.get("run_id") != run_id:
        raise IndependentSkepticStageError("COUNTER_DISPATCH_INDEX_INVALID")
    matches = [task for task in index.get("tasks", []) if task.get("invocation_id") == invocation_id]
    if len(matches) != 1:
        raise IndependentSkepticStageError("COUNTER_INVOCATION_UNKNOWN")
    task = matches[0]
    security_id = task.get("security_id")
    if not isinstance(security_id, str) or task.get("agent") != "runtime_skeptic":
        raise IndependentSkepticStageError("COUNTER_TASK_BINDING_INVALID")
    slug = hashlib.sha256(security_id.encode("utf-8")).hexdigest()[:24]
    attempt = task.get("attempt", 1)
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise IndependentSkepticStageError("COUNTER_ATTEMPT_INVALID")
    attempt_root = (
        "research/skeptic" if attempt == 1 else f"research/skeptic/attempts/{attempt}"
    )
    invocation_path = root / f"{attempt_root}/invocations/{slug}.json"
    input_path = root / f"{attempt_root}/inputs/{slug}.json"
    if (task.get("invocation_ref") != str(invocation_path.relative_to(root))
            or task.get("input_ref") != str(input_path.relative_to(root))
            or task.get("schema_ref") != f"{attempt_root}/{slug}/schemas/counter-thesis-report.schema.json"
            or task.get("prompt_ref") != f"{attempt_root}/prompts/{slug}.txt"
            or task.get("packet_ref") != f"{attempt_root}/packets/{slug}.json"
            or task.get("report_ref") != f"{attempt_root}/reports/{slug}/counter-thesis.json"
            or task.get("markdown_ref") != f"{attempt_root}/reports/{slug}/counter-thesis.md"
            or task.get("task_id") != f"skeptic:{security_id}"):
        raise IndependentSkepticStageError("COUNTER_TASK_PATH_INVALID")
    invocation = _read(invocation_path)
    agent_input = _read(input_path)
    allowed = task.get("allowed_evidence_ids")
    if (not isinstance(allowed, list) or not allowed or allowed != sorted(set(allowed))
            or not set(allowed) <= set(gate.get("allowed_evidence_ids", []))
            or invocation.get("manifest_hash") != canonical_hash(_without_hash(invocation, "manifest_hash"))
            or invocation.get("run_id") != run_id
            or invocation.get("invocation_id") != invocation_id
            or invocation.get("agent", {}).get("name") != "runtime_skeptic"
            or invocation.get("security_id") != security_id
            or invocation.get("evidence_ids") != allowed
            or invocation.get("input_hash") != canonical_hash(agent_input)
            or agent_input.get("security_id") != security_id
            or agent_input.get("run_id") != run_id):
        raise IndependentSkepticStageError("COUNTER_INVOCATION_BINDING_INVALID")
    if agent_input.get("attempt_id") != attempt:
        raise IndependentSkepticStageError("COUNTER_ATTEMPT_BINDING_INVALID")
    validate_first_pass_input(agent_input, allowed_ids=allowed)
    from product.runtime.invocation import verify_invocation_manifest
    product_root = Path(str(
        _read(root / "run_manifest.json").get("discovery", {}).get("product_root", "")
    )).resolve()
    if product_root.name != "product":
        raise IndependentSkepticStageError("COUNTER_PRODUCT_ROOT_INVALID")
    verify_invocation_manifest(product_root.parent, invocation, agent_input=agent_input)
    return invocation_path, allowed


def validate_core_coverage(bundle: Mapping[str, Any]) -> None:
    if bundle.get("consumability") != "DOWNSTREAM_READY":
        raise IndependentSkepticStageError("COUNTER_FORWARD_BUNDLE_NOT_READY")
    common_ids = bundle.get("common_stock_security_ids")
    coverage = bundle.get("coverage")
    if (not isinstance(common_ids, list) or not common_ids
            or len(common_ids) != len(set(common_ids)) or not isinstance(coverage, list)):
        raise IndependentSkepticStageError("COUNTER_FORWARD_COVERAGE_INVALID")
    expected = {(security_id, capability) for security_id in common_ids for capability in CORE_CAPABILITIES}
    actual = [
        (item.get("security_id"), item.get("capability"))
        for item in coverage if isinstance(item, Mapping) and item.get("capability") in CORE_CAPABILITIES
    ]
    if len(actual) != len(set(actual)) or set(actual) != expected:
        raise IndependentSkepticStageError("COUNTER_FORWARD_CORE_COVERAGE_INCOMPLETE")
    for item in coverage:
        if item.get("capability") not in CORE_CAPABILITIES:
            continue
        if item.get("status") not in READY_CORE_STATUSES or not item.get("report_id"):
            raise IndependentSkepticStageError(
                f"COUNTER_FORWARD_CORE_NOT_READY:{item['security_id']}:{item['capability']}"
            )


def validate_forward_gate(repository_root: Path, run_dir: Path) -> dict[str, Any]:
    """重验当前运行的正向包；不从历史目录补报告，也不写入消费证明。"""

    run_dir = Path(run_dir).resolve()
    manifest = _read(run_dir / "run_manifest.json")
    handoff = _read(run_dir / "audit/portfolio-handoff.json")
    request = _read(run_dir / "council-request.json")
    gate = _read(run_dir / "evidence/gate.json")
    bundle_path = run_dir / "research/holding-research-bundle.json"
    bundle = _read(bundle_path)
    if (manifest.get("manifest_hash") != canonical_hash(_without_hash(manifest, "manifest_hash"))
            or manifest.get("stage") != STAGE or request.get("stage") != STAGE
            or manifest.get("complete_portfolio_decision") is not False
            or manifest.get("downstream_stages_started") not in ([], ["FORWARD_MULTIDIMENSIONAL_RESEARCH"])):
        raise IndependentSkepticStageError("COUNTER_STAGE_BINDING_INVALID")
    validate_handoff(handoff)
    validate_council_request(request, handoff=handoff)
    if (manifest.get("run_id") != gate.get("run_id")
            or manifest.get("run_id") != bundle.get("run_id")
            or manifest.get("handoff_hash") != handoff.get("handoff_hash")
            or manifest.get("portfolio_hash") != handoff.get("portfolio_hash")
            or manifest.get("council_request_hash") != request.get("request_hash")
            or manifest.get("gate_hash") != gate.get("bundle_hash")
            or gate.get("bundle_hash") != canonical_hash({key: value for key, value in gate.items() if key != "bundle_hash"})
            or bundle.get("decision_cutoff") != gate.get("decision_cutoff")
            or bundle.get("bindings") != {
                "handoff_id": handoff["handoff_id"], "handoff_hash": handoff["handoff_hash"],
                "portfolio_hash": handoff["portfolio_hash"],
                "council_request_id": request["request_id"],
                "council_request_hash": request["request_hash"],
            }):
        raise IndependentSkepticStageError("COUNTER_FORWARD_BINDING_INVALID")
    proof = check_multidimensional_bundle_consumable(repository_root, run_dir, persist=False)
    validate_core_coverage(bundle)
    if any((run_dir / name).exists() for name in (
        "decision.json", "risk.json", "agents/runtime_cio.json", "outcome.json",
    )):
        raise IndependentSkepticStageError("COUNTER_DOWNSTREAM_ARTIFACT_FORBIDDEN")
    return {
        "run_id": manifest["run_id"], "decision_cutoff": gate["decision_cutoff"],
        "gate_hash": gate["bundle_hash"], "bundle_hash": bundle["bundle_hash"],
        "bundle_file_hash": file_hash(bundle_path), "consumption_proof_hash": proof["proof_hash"],
        "common_stock_security_ids": bundle["common_stock_security_ids"],
    }


def scope_evidence_ids(
    gate: Mapping[str, Any], *, security_id: str,
    shared_evidence_ids: Sequence[str] = (), peer_security_ids: Sequence[str] = (),
) -> list[str]:
    """只由冻结 Gate 与准备阶段关系决定，绝不读取正向报告引用。"""

    gate_ids = gate.get("allowed_evidence_ids")
    evidence = gate.get("allowed_evidence")
    if not isinstance(gate_ids, list) or not isinstance(evidence, list):
        raise IndependentSkepticStageError("COUNTER_GATE_INVALID")
    known = {item.get("evidence_id"): item for item in evidence if isinstance(item, Mapping)}
    if len(known) != len(evidence) or set(known) != set(gate_ids):
        raise IndependentSkepticStageError("COUNTER_GATE_INVALID")
    peers = set(peer_security_ids) - {security_id}
    shared = set(shared_evidence_ids)
    if shared - set(gate_ids):
        raise IndependentSkepticStageError("COUNTER_SHARED_EVIDENCE_OUTSIDE_GATE")
    selected = {
        evidence_id for evidence_id, fact in known.items()
        if fact.get("security_id") == security_id
        or fact.get("security_id") in peers
        or evidence_id in shared and fact.get("security_id") in {None, "US:MARKET", "US:MACRO", "US:SPY"}
    }
    return sorted(selected)


def validate_first_pass_input(value: Mapping[str, Any], *, allowed_ids: Sequence[str]) -> None:
    if set(value) != FIRST_PASS_KEYS:
        raise IndependentSkepticStageError("CONTEXT_ISOLATION_VIOLATION")
    if (value.get("agent") != "runtime_skeptic"
            or value.get("mode") != "INDEPENDENT_FIRST_PASS"
            or value.get("source_mode") != "frozen-gate"
            or value.get("report_schema_version") != "counter-thesis-report/2.1.0"
            or not isinstance(value.get("attempt_id"), int)
            or isinstance(value.get("attempt_id"), bool)
            or value["attempt_id"] < 1
            or value.get("allowed_evidence_ids") != sorted(set(allowed_ids))):
        raise IndependentSkepticStageError("CONTEXT_ISOLATION_VIOLATION")
    for field in ("run_id", "security_id", "research_question", "decision_cutoff", "request_id", "gate_hash"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise IndependentSkepticStageError("CONTEXT_ISOLATION_VIOLATION")
    if value.get("holding_horizon") is not None and not isinstance(value["holding_horizon"], str):
        raise IndependentSkepticStageError("CONTEXT_ISOLATION_VIOLATION")
    if not isinstance(value.get("scope_limitations"), list) or any(
        not isinstance(item, str) for item in value["scope_limitations"]
    ):
        raise IndependentSkepticStageError("CONTEXT_ISOLATION_VIOLATION")


def build_first_pass_input(
    *, run_id: str, security_id: str, request: Mapping[str, Any],
    gate: Mapping[str, Any], allowed_ids: Sequence[str], scope_limitations: Sequence[str] = (),
    attempt_id: int = 1,
) -> dict[str, Any]:
    value = {
        "run_id": run_id, "agent": "runtime_skeptic", "mode": "INDEPENDENT_FIRST_PASS",
        "source_mode": "frozen-gate", "security_id": security_id,
        "report_schema_version": "counter-thesis-report/2.1.0",
        "attempt_id": attempt_id,
        "research_question": request["research_question"],
        "holding_horizon": request.get("holding_horizon"),
        "decision_cutoff": gate["decision_cutoff"], "request_id": request["request_id"],
        "gate_hash": gate["bundle_hash"],
        "allowed_evidence_ids": sorted(set(allowed_ids)),
        "scope_limitations": list(scope_limitations),
    }
    validate_first_pass_input(value, allowed_ids=allowed_ids)
    return value


def _write(path: Path, value: Mapping[str, Any] | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        if isinstance(value, str):
            stream.write(value)
        else:
            json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")


def prepare_skeptic_phase(repository_root: Path, run_dir: Path) -> dict[str, Any]:
    """正向包通过门禁后，为每只普通股建立独立、只含 Gate 上下文的任务。"""

    from product.runtime.invocation import (
        build_specialist_output_schema, create_invocation_manifest,
        verify_invocation_manifest,
    )

    repository_root = Path(repository_root).resolve()
    run_dir = Path(run_dir).resolve()
    proof = validate_forward_gate(repository_root, run_dir)
    root = run_dir / "research/skeptic"
    if root.exists():
        raise IndependentSkepticStageError("COUNTER_PHASE_ALREADY_PREPARED")
    manifest = _read(run_dir / "run_manifest.json")
    request = _read(run_dir / "council-request.json")
    gate = _read(run_dir / "evidence/gate.json")
    forward_index = _read(run_dir / "research/dispatch-index.json")
    if (forward_index.get("run_id") != proof["run_id"]
            or forward_index.get("index_hash") != canonical_hash(_without_hash(forward_index, "index_hash"))
            or manifest.get("dispatch_index_hash") != forward_index["index_hash"]):
        raise IndependentSkepticStageError("COUNTER_FORWARD_DISPATCH_INVALID")
    shared_ids = sorted({
        evidence_id for task in forward_index["tasks"]
        if task.get("capability") in {"MACRO_CONTEXT", "MARKET_STATE"}
        for evidence_id in task.get("allowed_evidence_ids", [])
    })
    tasks = []
    for ordinal, security_id in enumerate(sorted(proof["common_stock_security_ids"]), start=1):
        slug = hashlib.sha256(security_id.encode("utf-8")).hexdigest()[:24]
        industry_tasks = [
            task for task in forward_index["tasks"]
            if task.get("capability") == "INDUSTRY_COMPARISON"
            and task.get("security_ids") == [security_id]
        ]
        if len(industry_tasks) != 1:
            raise IndependentSkepticStageError("COUNTER_PEER_RELATION_INVALID")
        peers = sorted({
            item["materialized_security_id"]
            for item in industry_tasks[0].get("selected_peer_candidates", [])
            if item.get("materialization_status") == "FROZEN"
            and isinstance(item.get("materialized_security_id"), str)
        })
        allowed = scope_evidence_ids(
            gate, security_id=security_id, shared_evidence_ids=shared_ids,
            peer_security_ids=peers,
        )
        if not allowed:
            raise IndependentSkepticStageError(f"COUNTER_EVIDENCE_EMPTY:{security_id}")
        limitations = [
            "同行资料仅来自本次资料准备中完成身份核验和 PIT 冻结的选择；不是同行全集。",
        ]
        if not peers:
            limitations.append("本次没有完成冻结的相关同行事实；不得推断不存在同行风险。")
        agent_input = build_first_pass_input(
            run_id=proof["run_id"], security_id=security_id,
            request=request, gate=gate, allowed_ids=allowed,
            scope_limitations=limitations,
        )
        schema = build_specialist_output_schema(
            repository_root, agent_name="runtime_skeptic",
            allowed_evidence_ids=allowed,
            report_schema_version="counter-thesis-report/2.1.0",
        )
        schema_ref = f"research/skeptic/{slug}/schemas/counter-thesis-report.schema.json"
        input_ref = f"research/skeptic/inputs/{slug}.json"
        prompt_ref = f"research/skeptic/prompts/{slug}.txt"
        invocation_ref = f"research/skeptic/invocations/{slug}.json"
        packet_ref = f"research/skeptic/packets/{slug}.json"
        task_name = f"independent_skeptic_{ordinal}"
        prompt = (
            f"独立研究 {security_id} 的公司特定失败路径与替代解释。"
            "第一轮不得读取或引用任何正向研究报告、摘要、未解决问题或其 hash；"
            "只能按冻结包给出的 Evidence IDs 使用只读 fixture_runtime.query 主动核验非空事实。"
            "事实性断言用 Evidence 支持；纯情景显式标注本报告 assumptions，"
            "说明传导逻辑、待补证据和可观察的推翻条件。"
            "无法完成研究则如实使用 INSUFFICIENT_EVIDENCE 或 TIMEOUT，"
            "不得编造风险或给出投资动作。只返回符合 2.1.0 Schema 的 JSON。"
        )
        _write(run_dir / input_ref, agent_input)
        _write(run_dir / schema_ref, schema)
        _write(run_dir / prompt_ref, prompt)
        invocation = create_invocation_manifest(
            repository_root, run_id=proof["run_id"], agent_name="runtime_skeptic",
            agent_input=agent_input, task_prompt=prompt, model=manifest["model"],
            evidence_ids=allowed, output_schema_path=run_dir / schema_ref,
        )
        invocation["security_id"] = security_id
        invocation["input_artifact"] = input_ref
        invocation["task_prompt_artifact"] = prompt_ref
        invocation["tool_permissions"] = ["fixture_evidence.query", "fixture_math.calculate"]
        invocation["manifest_hash"] = canonical_hash(_without_hash(invocation, "manifest_hash"))
        verify_invocation_manifest(repository_root, invocation, agent_input=agent_input)
        _write(run_dir / invocation_ref, invocation)
        packet = {
            "dispatch_contract": DISPATCH_VERSION,
            "identity": {
                "run_id": proof["run_id"], "task_name": task_name,
                "agent": "runtime_skeptic", "invocation_id": invocation["invocation_id"],
                "security_id": security_id,
            },
            "agent_input": agent_input,
            "invocation": invocation,
            "task_prompt": prompt,
            "output_schema": schema,
            "tool_context": {
                "mcp_server": "fixture_runtime", "query_tool": "fixture_runtime.query",
                "required_identity_arguments": {
                    "run_id": proof["run_id"], "agent": "runtime_skeptic",
                    "invocation_id": invocation["invocation_id"],
                },
            },
        }
        _write(run_dir / packet_ref, packet)
        tasks.append({
            "task_id": f"skeptic:{security_id}",
            "attempt": 1,
            "task_name": task_name, "security_id": security_id,
            "agent": "runtime_skeptic", "invocation_id": invocation["invocation_id"],
            "allowed_evidence_ids": allowed, "input_ref": input_ref,
            "invocation_ref": invocation_ref, "prompt_ref": prompt_ref,
            "schema_ref": schema_ref, "packet_ref": packet_ref,
            "packet_hash": canonical_hash(packet),
            "report_ref": f"research/skeptic/reports/{slug}/counter-thesis.json",
            "markdown_ref": f"research/skeptic/reports/{slug}/counter-thesis.md",
        })
    index = {
        "schema_version": DISPATCH_VERSION,
        "run_id": proof["run_id"], "attempt": 1,
        "forward_bundle_hash": proof["bundle_hash"],
        "forward_bundle_file_hash": proof["bundle_file_hash"],
        "gate_hash": proof["gate_hash"],
        "target_concurrency": min(manifest["target_concurrency"], len(tasks)),
        "tasks": tasks,
    }
    index["index_hash"] = canonical_hash(index)
    _write(root / "dispatch-index.json", index)
    return {"status": "PREPARED", "run_id": proof["run_id"], "task_count": len(tasks),
            "dispatch_index": str(root / "dispatch-index.json")}


def prepare_skeptic_resume(repository_root: Path, run_dir: Path) -> dict[str, Any]:
    """同一冻结运行只为未就绪股票生成一次新的不可变尝试。"""

    from product.runtime.invocation import create_invocation_manifest, verify_invocation_manifest

    repository_root = Path(repository_root).resolve()
    run_dir = Path(run_dir).resolve()
    forward = validate_forward_gate(repository_root, run_dir)
    latest = 1
    while (run_dir / _index_ref(latest + 1)).exists():
        latest += 1
    previous_index_ref = _index_ref(latest)
    previous_index = read_dispatch_index(run_dir, previous_index_ref)
    previous_package_ref = (
        "research/skeptic/pre-decision-research-package.json" if latest == 1
        else f"research/skeptic/attempts/{latest}/pre-decision-research-package.json"
    )
    previous_package = _read(run_dir / previous_package_ref)
    validate_predecision_package(repository_root, run_dir, previous_package)
    previous_process_ref = (
        "invocation/skeptic/process-result.json" if latest == 1
        else f"invocation/skeptic/attempt-{latest}/process-result.json"
    )
    previous_process = _read(run_dir / previous_process_ref)
    if (previous_process.get("source_integrity_unchanged") is not True
            or previous_process.get("run_id") != forward["run_id"]
            or previous_package["dispatch_index"]["content_hash"] != previous_index["index_hash"]
            or previous_index.get("forward_bundle_hash") != forward["bundle_hash"]
            or previous_index.get("forward_bundle_file_hash") != forward["bundle_file_hash"]
            or previous_index.get("gate_hash") != forward["gate_hash"]):
        raise IndependentSkepticStageError("COUNTER_RESUME_INPUT_DRIFT")
    entries = {item["security_id"]: item for item in previous_package["counter_theses"]}
    retry = [
        task for task in previous_index["tasks"]
        if not (entries[task["security_id"]]["status"] in {"COMPLETE", "LOW_CONFIDENCE"}
                and entries[task["security_id"]]["validation_status"] == "PASSED")
    ]
    if not retry:
        raise IndependentSkepticStageError("COUNTER_RESUME_NO_RETRY_NEEDED")
    attempt = latest + 1
    attempt_root = f"research/skeptic/attempts/{attempt}"
    tasks = []
    for old in previous_index["tasks"]:
        old_input = _read(run_dir / old["input_ref"])
        old_invocation = _read(run_dir / old["invocation_ref"])
        verify_invocation_manifest(repository_root, old_invocation, agent_input=old_input)
        if old not in retry:
            tasks.append(copy.deepcopy(old))
            continue
        slug = hashlib.sha256(old["security_id"].encode("utf-8")).hexdigest()[:24]
        agent_input = {**old_input, "attempt_id": attempt}
        validate_first_pass_input(agent_input, allowed_ids=old["allowed_evidence_ids"])
        input_ref = f"{attempt_root}/inputs/{slug}.json"
        schema_ref = f"{attempt_root}/{slug}/schemas/counter-thesis-report.schema.json"
        prompt_ref = f"{attempt_root}/prompts/{slug}.txt"
        invocation_ref = f"{attempt_root}/invocations/{slug}.json"
        packet_ref = f"{attempt_root}/packets/{slug}.json"
        prompt = (run_dir / old["prompt_ref"]).read_text(encoding="utf-8")
        schema = _read(run_dir / old["schema_ref"])
        _write(run_dir / input_ref, agent_input)
        _write(run_dir / schema_ref, schema)
        _write(run_dir / prompt_ref, prompt)
        invocation = create_invocation_manifest(
            repository_root, run_id=forward["run_id"], agent_name="runtime_skeptic",
            agent_input=agent_input, task_prompt=prompt, model=old_invocation["model"],
            evidence_ids=old["allowed_evidence_ids"], output_schema_path=run_dir / schema_ref,
        )
        invocation["security_id"] = old["security_id"]
        invocation["input_artifact"] = input_ref
        invocation["task_prompt_artifact"] = prompt_ref
        invocation["tool_permissions"] = ["fixture_evidence.query", "fixture_math.calculate"]
        invocation["manifest_hash"] = canonical_hash(_without_hash(invocation, "manifest_hash"))
        verify_invocation_manifest(repository_root, invocation, agent_input=agent_input)
        _write(run_dir / invocation_ref, invocation)
        packet = {
            "dispatch_contract": DISPATCH_VERSION,
            "identity": {
                "run_id": forward["run_id"], "task_name": old["task_name"],
                "agent": "runtime_skeptic", "invocation_id": invocation["invocation_id"],
                "security_id": old["security_id"],
            },
            "agent_input": agent_input, "invocation": invocation,
            "task_prompt": prompt, "output_schema": schema,
            "tool_context": {
                "mcp_server": "fixture_runtime", "query_tool": "fixture_runtime.query",
                "required_identity_arguments": {
                    "run_id": forward["run_id"], "agent": "runtime_skeptic",
                    "invocation_id": invocation["invocation_id"],
                },
            },
        }
        _write(run_dir / packet_ref, packet)
        tasks.append({
            **old, "attempt": attempt, "invocation_id": invocation["invocation_id"],
            "input_ref": input_ref, "schema_ref": schema_ref, "prompt_ref": prompt_ref,
            "invocation_ref": invocation_ref, "packet_ref": packet_ref,
            "packet_hash": canonical_hash(packet),
            "report_ref": f"{attempt_root}/reports/{slug}/counter-thesis.json",
            "markdown_ref": f"{attempt_root}/reports/{slug}/counter-thesis.md",
        })
    index = {
        **{key: value for key, value in previous_index.items() if key not in {"tasks", "index_hash", "attempt"}},
        "attempt": attempt, "tasks": tasks,
        "previous_package": _artifact_record(run_dir, previous_package_ref, previous_package["package_hash"]),
    }
    index["index_hash"] = canonical_hash(index)
    ref = _index_ref(attempt)
    _write(run_dir / ref, index)
    return {"status": "PREPARED", "run_id": forward["run_id"], "attempt": attempt,
            "retry_task_names": [task["task_name"] for task in retry], "dispatch_index": ref}


def build_skeptic_dispatch_packet(
    repository_root: Path, run_dir: Path, task_name: str, *, index_ref: str | None = None,
) -> dict[str, Any]:
    del repository_root
    run_dir = Path(run_dir).resolve()
    index = read_dispatch_index(run_dir, index_ref)
    matches = [item for item in index.get("tasks", []) if item.get("task_name") == task_name]
    if len(matches) != 1:
        raise IndependentSkepticStageError("COUNTER_TASK_UNKNOWN")
    task = matches[0]
    packet = _read(run_dir / task["packet_ref"])
    if (canonical_hash(packet) != task["packet_hash"]
            or packet.get("identity", {}).get("task_name") != task_name
            or packet.get("identity", {}).get("invocation_id") != task["invocation_id"]):
        raise IndependentSkepticStageError("COUNTER_PACKET_BINDING_INVALID")
    resolve_skeptic_tool_scope(
        run_dir, run_id=index["run_id"], invocation_id=task["invocation_id"],
        gate=_read(run_dir / "evidence/gate.json"), index_ref=index_ref,
    )
    return packet


def render_counter_thesis_markdown(
    report: Mapping[str, Any], *, security_id: str, decision_cutoff: str,
    evidence: Sequence[Mapping[str, Any]],
) -> str:
    """忠实展示反证原文与来源，不综合正反观点。"""

    from product.runtime.validation import collect_evidence_refs
    by_id = {item["evidence_id"]: item for item in evidence}
    if collect_evidence_refs(report) - set(by_id):
        raise IndependentSkepticStageError("COUNTER_RENDER_EVIDENCE_DANGLING")
    lines = [
        f"# {security_id} 独立反证研究", "",
        f"- 截止：`{decision_cutoff}`", f"- 状态：`{report['status']}`",
        f"- Invocation：`{report['invocation_id']}`", "",
        "## 研究范围", "", str(report["scope"]), "",
        "## 挑战与替代解释", "",
    ]
    if not report["challenges"]:
        lines.append("- 原报告未列出挑战；请结合下方限制和缺口阅读，不能推断无风险。")
    for challenge in report["challenges"]:
        lines.extend([
            f"### {challenge['challenge_id']}", "", str(challenge["statement"]), "",
            f"- Evidence：{', '.join(f'`{item}`' for item in challenge['evidence_refs']) or '无'}",
            f"- 假设：{', '.join(f'`{item}`' for item in challenge['assumption_ids']) or '无'}",
            f"- 待补证据：{'；'.join(challenge['resolution_evidence_needed']) or '未列明'}", "",
        ])
    lines.extend(["## 本报告假设", ""])
    lines.extend(
        f"- `{item['assumption_id']}`：{item['statement']}" for item in report["assumptions"]
    )
    if not report["assumptions"]:
        lines.append("- 无。")
    for title, values in (
        ("反向证据", report["counter_evidence_refs"]),
        ("不确定性", report["uncertainties"]),
        ("数据缺口", report["data_gaps"]),
        ("推翻条件", report["invalidation_conditions"]),
    ):
        lines.extend(["", f"## {title}", ""])
        lines.extend(f"- {item}" for item in values)
        if not values:
            lines.append("- 原报告未列明。")
    lines.extend(["", "## 依据来源", ""])
    for evidence_id in sorted(collect_evidence_refs(report)):
        fact = by_id[evidence_id]
        lines.append(
            f"- `{evidence_id}`：`{fact['source_id']}`；as_of `{fact['as_of']}`；"
            f"retrieved_at `{fact['retrieved_at']}`"
        )
    if not collect_evidence_refs(report):
        lines.append("- 未引用事实 Evidence；不得把纯假设情景当成观察事实。")
    lines.extend(["", "## 置信度", "", f"- `{report['confidence']}`：{report['confidence_rationale']}", ""])
    return "\n".join(lines)


def capture_skeptic_report(
    repository_root: Path, run_dir: Path, *, task_name: str,
    raw_message: str, model: str, index_ref: str | None = None,
) -> dict[str, Any]:
    """只封装 Invocation 技术字段；不改写 Agent 的研究内容。"""

    from product.runtime.invocation import envelope_specialist_draft
    from product.runtime.schema_validation import validate_schema_instance
    from product.runtime.validation import validate_skeptic_report

    run_dir = Path(run_dir).resolve()
    packet = build_skeptic_dispatch_packet(repository_root, run_dir, task_name, index_ref=index_ref)
    index = read_dispatch_index(run_dir, index_ref)
    task = next(item for item in index["tasks"] if item["task_name"] == task_name)
    invocation = packet["invocation"]
    if model != invocation["model"]:
        raise IndependentSkepticStageError("COUNTER_OUTPUT_MODEL_INVALID")
    try:
        raw = json.loads(raw_message)
    except json.JSONDecodeError as exc:
        raise IndependentSkepticStageError("COUNTER_OUTPUT_JSON_INVALID") from exc
    if not isinstance(raw, dict):
        raise IndependentSkepticStageError("COUNTER_OUTPUT_NOT_OBJECT")
    report = (
        envelope_specialist_draft(raw, invocation, model=model)
        if "skill_execution" not in raw else copy.deepcopy(raw)
    )
    if (report.get("schema_version") != "counter-thesis-report/2.1.0"
            or report.get("artifact_refs") != []
            or task["security_id"] not in str(report.get("scope", ""))):
        raise IndependentSkepticStageError("COUNTER_OUTPUT_SCOPE_INVALID")
    validate_schema_instance(report, packet["output_schema"])
    validate_skeptic_report(report, run_id=index["run_id"], manifest=invocation)
    allowed = set(task["allowed_evidence_ids"])
    gate = _read(run_dir / "evidence/gate.json")
    markdown = render_counter_thesis_markdown(
        report, security_id=task["security_id"], decision_cutoff=gate["decision_cutoff"],
        evidence=[item for item in gate["allowed_evidence"] if item["evidence_id"] in allowed],
    )
    _write(run_dir / task["report_ref"], report)
    _write(run_dir / task["markdown_ref"], markdown)
    return {
        "status": "SAVED", "task_id": task["task_id"], "security_id": task["security_id"],
        "path": task["report_ref"], "markdown_path": task["markdown_ref"],
        "output_hash": canonical_hash(report),
    }


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    try:
        values = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except json.JSONDecodeError as exc:
        raise IndependentSkepticStageError(f"COUNTER_EVENT_LOG_INVALID:{path.name}") from exc
    if any(not isinstance(item, dict) for item in values):
        raise IndependentSkepticStageError(f"COUNTER_EVENT_LOG_INVALID:{path.name}")
    return values


def _artifact_record(run_dir: Path, relative: str, content_hash: str) -> dict[str, str]:
    path = (run_dir / relative).resolve()
    if not path.is_relative_to(run_dir) or not path.is_file():
        raise IndependentSkepticStageError("COUNTER_ARTIFACT_MISSING")
    return {"artifact_ref": relative, "file_hash": file_hash(path), "content_hash": content_hash}


def _forbidden_downstream_artifacts(run_dir: Path) -> None:
    forbidden = (
        "decision.json", "risk.json", "agents/runtime_cio.json", "outcome.json",
        "research/cio", "research/risk", "evaluation", "replay",
    )
    if any((run_dir / name).exists() for name in forbidden):
        raise IndependentSkepticStageError("COUNTER_DOWNSTREAM_ARTIFACT_FORBIDDEN")


def validate_predecision_package(repository_root: Path, run_dir: Path, package: Mapping[str, Any]) -> None:
    """仅重验绑定与引用；不从原报告归纳共识或动作。"""

    from product.runtime.schema_validation import validate_schema_instance
    from product.runtime.validation import validate_skeptic_report

    run_dir = Path(run_dir).resolve()
    schema = _read(Path(repository_root) / "product/schemas/runtime/pre-decision-research-package.schema.json")
    validate_schema_instance(package, schema)
    if package.get("package_hash") != canonical_hash(_without_hash(package, "package_hash")):
        raise IndependentSkepticStageError("COUNTER_PACKAGE_HASH_MISMATCH")
    manifest = _read(run_dir / "run_manifest.json")
    handoff = _read(run_dir / "audit/portfolio-handoff.json")
    request = _read(run_dir / "council-request.json")
    gate = _read(run_dir / "evidence/gate.json")
    bundle = _read(run_dir / "research/holding-research-bundle.json")
    if (package["run_id"] != manifest["run_id"]
            or package["run_id"] != bundle["run_id"]
            or package["handoff_id"] != handoff["handoff_id"]
            or package["handoff_hash"] != handoff["handoff_hash"]
            or package["portfolio_hash"] != handoff["portfolio_hash"]
            or package["request_id"] != request["request_id"]
            or package["request_hash"] != request["request_hash"]
            or package["decision_cutoff"] != gate["decision_cutoff"]
            or package["gate_hash"] != gate["bundle_hash"]
            or package["forward_bundle"] != _artifact_record(
                run_dir, "research/holding-research-bundle.json", bundle["bundle_hash"]
            )):
        raise IndependentSkepticStageError("COUNTER_PACKAGE_BINDING_INVALID")
    common_ids = set(bundle["common_stock_security_ids"])
    entries = package["counter_theses"]
    if len(entries) != len(common_ids) or {item["security_id"] for item in entries} != common_ids:
        raise IndependentSkepticStageError("COUNTER_PACKAGE_SECURITY_COVERAGE_INVALID")
    index_ref = package["dispatch_index"]["artifact_ref"]
    index = read_dispatch_index(run_dir, index_ref)
    if package["dispatch_index"] != _artifact_record(run_dir, index_ref, index["index_hash"]):
        raise IndependentSkepticStageError("COUNTER_PACKAGE_INDEX_DRIFT")
    by_security = {item["security_id"]: item for item in index["tasks"]}
    if set(by_security) != common_ids:
        raise IndependentSkepticStageError("COUNTER_DISPATCH_COVERAGE_INVALID")
    for task in index["tasks"]:
        resolve_skeptic_tool_scope(
            run_dir, run_id=package["run_id"], invocation_id=task["invocation_id"],
            gate=gate, index_ref=index_ref,
        )
    if index.get("attempt", 1) > 1:
        previous_record = index.get("previous_package")
        if not isinstance(previous_record, dict):
            raise IndependentSkepticStageError("COUNTER_RESUME_CHAIN_MISSING")
        prior_ref = previous_record.get("artifact_ref")
        expected_prior_ref = (
            "research/skeptic/pre-decision-research-package.json" if index["attempt"] == 2
            else f"research/skeptic/attempts/{index['attempt'] - 1}/pre-decision-research-package.json"
        )
        if prior_ref != expected_prior_ref:
            raise IndependentSkepticStageError("COUNTER_RESUME_CHAIN_INVALID")
        prior = _read(run_dir / prior_ref)
        if previous_record != _artifact_record(run_dir, prior_ref, prior["package_hash"]):
            raise IndependentSkepticStageError("COUNTER_RESUME_CHAIN_DRIFT")
        validate_predecision_package(repository_root, run_dir, prior)
        prior_entries = {item["security_id"]: item for item in prior["counter_theses"]}
        prior_index = read_dispatch_index(run_dir, prior["dispatch_index"]["artifact_ref"])
        prior_tasks = {item["security_id"]: item for item in prior_index["tasks"]}
        for security_id, task in by_security.items():
            retained = prior_entries[security_id]["status"] in {"COMPLETE", "LOW_CONFIDENCE"} and prior_entries[security_id]["validation_status"] == "PASSED"
            if retained and task != prior_tasks[security_id]:
                raise IndependentSkepticStageError("COUNTER_RESUME_SUCCESS_CHANGED")
            if not retained and task.get("attempt") != index["attempt"]:
                raise IndependentSkepticStageError("COUNTER_RESUME_RETRY_MISSING")
    proof_ref = (
        "research/skeptic/execution-proof.json" if index.get("attempt", 1) == 1
        else f"research/skeptic/attempts/{index['attempt']}/execution-proof.json"
    )
    if package["execution_proof"]["artifact_ref"] != proof_ref:
        raise IndependentSkepticStageError("COUNTER_EXECUTION_PROOF_PATH_INVALID")
    proof_path = run_dir / proof_ref
    proof = _read(proof_path)
    if (proof.get("proof_hash") != canonical_hash(_without_hash(proof, "proof_hash"))
            or package["execution_proof"] != _artifact_record(run_dir, proof_ref, proof["proof_hash"])
            or proof.get("run_id") != package["run_id"]
            or proof.get("gate_hash") != package["gate_hash"]
            or proof.get("forward_bundle_hash") != bundle["bundle_hash"]):
        raise IndependentSkepticStageError("COUNTER_EXECUTION_PROOF_INVALID")
    proof_by_security = {item.get("security_id"): item for item in proof.get("tasks", [])}
    if len(proof_by_security) != len(common_ids) or set(proof_by_security) != common_ids:
        raise IndependentSkepticStageError("COUNTER_EXECUTION_COVERAGE_INVALID")
    for entry in entries:
        task = by_security[entry["security_id"]]
        if entry["invocation_id"] != task["invocation_id"]:
            raise IndependentSkepticStageError("COUNTER_PACKAGE_INVOCATION_INVALID")
        if entry["report"] is None:
            if (entry["validation_status"] == "PASSED" or entry["markdown_ref"] is not None
                    or entry["status"] in {"COMPLETE", "LOW_CONFIDENCE"}):
                raise IndependentSkepticStageError("COUNTER_PACKAGE_MISSING_REPORT_READY")
            continue
        report_ref = entry["report"]["artifact_ref"]
        if report_ref != task["report_ref"]:
            raise IndependentSkepticStageError("COUNTER_PACKAGE_REPORT_PATH_INVALID")
        report = _read(run_dir / report_ref)
        invocation = _read(run_dir / task["invocation_ref"])
        output_schema = _read(Path(str(invocation["output_schema"])))
        validate_schema_instance(report, output_schema)
        if (report.get("schema_version") != "counter-thesis-report/2.1.0"
                or entry["report"] != _artifact_record(run_dir, report_ref, canonical_hash(report))
                or entry["status"] != report["status"]
                or entry["validation_status"] != "PASSED"
                or entry["markdown_ref"] != task["markdown_ref"]
                or not (run_dir / entry["markdown_ref"]).is_file()):
            raise IndependentSkepticStageError("COUNTER_PACKAGE_REPORT_BINDING_INVALID")
        validate_skeptic_report(report, run_id=package["run_id"], manifest=invocation)
        task_proof = proof_by_security[entry["security_id"]]
        if (task_proof.get("invocation_id") != entry["invocation_id"]
                or task_proof.get("input_hash") != invocation["input_hash"]
                or task_proof.get("status") != "PASSED"
                or task_proof.get("gate_scoped_nonempty_query_count", 0) < 1
                or not collect_evidence_refs(report) <= set(
                    task_proof.get("queried_evidence_ids", [])
                )):
            raise IndependentSkepticStageError("COUNTER_EXECUTION_QUERY_PROOF_MISSING")
    positions = {item["security_id"]: item for item in handoff["portfolio"]["positions"]}
    if (len(package["coverage"]) != len(positions)
            or {item["security_id"] for item in package["coverage"]} != set(positions)):
        raise IndependentSkepticStageError("COUNTER_PACKAGE_PORTFOLIO_COVERAGE_INVALID")
    for item in package["coverage"]:
        if item["asset_type"] != positions[item["security_id"]]["asset_type"]:
            raise IndependentSkepticStageError("COUNTER_PACKAGE_ASSET_TYPE_INVALID")
    ready = all(
        item["status"] in {"COMPLETE", "LOW_CONFIDENCE"}
        and item["validation_status"] == "PASSED"
        for item in entries
    )
    if package["consumability"] != ("DOWNSTREAM_READY" if ready else "STRUCTURALLY_CONSUMABLE"):
        raise IndependentSkepticStageError("COUNTER_PACKAGE_READINESS_INVALID")
    for relative in package["artifact_refs"]:
        path = (run_dir / relative).resolve()
        if not path.is_relative_to(run_dir) or not path.is_file():
            raise IndependentSkepticStageError("COUNTER_PACKAGE_ARTIFACT_MISSING")
    _forbidden_downstream_artifacts(run_dir)


def finalize_skeptic_phase(
    repository_root: Path, run_dir: Path, *, index_ref: str | None = None,
) -> dict[str, Any]:
    """核验逐股执行事实并形成仅引用原报告的正反研究交接包。"""

    from product.runtime.validation import validate_skeptic_report

    repository_root = Path(repository_root).resolve()
    run_dir = Path(run_dir).resolve()
    forward = validate_forward_gate(repository_root, run_dir)
    relative_index = INITIAL_INDEX_REF if index_ref is None else index_ref
    index = read_dispatch_index(run_dir, relative_index)
    if (index.get("run_id") != forward["run_id"]
            or index.get("gate_hash") != forward["gate_hash"]
            or index.get("forward_bundle_hash") != forward["bundle_hash"]
            or index.get("forward_bundle_file_hash") != forward["bundle_file_hash"]):
        raise IndependentSkepticStageError("COUNTER_DISPATCH_FORWARD_DRIFT")
    _forbidden_downstream_artifacts(run_dir)
    attempt = index.get("attempt", 1)
    tool_events = _read_jsonl(run_dir / "events/mcp/events.jsonl")
    handoff = _read(run_dir / "audit/portfolio-handoff.json")
    request = _read(run_dir / "council-request.json")
    gate = _read(run_dir / "evidence/gate.json")
    entries = []
    execution = []
    for task in index["tasks"]:
        resolve_skeptic_tool_scope(
            run_dir, run_id=forward["run_id"], invocation_id=task["invocation_id"],
            gate=_read(run_dir / "evidence/gate.json"), index_ref=relative_index,
        )
        task_attempt = task.get("attempt", 1)
        event_dir = run_dir / "invocation/skeptic"
        if task_attempt > 1:
            event_dir = event_dir / f"attempt-{task_attempt}"
        dispatches = _read_jsonl(event_dir / "subagent-dispatches.jsonl")
        events = _read_jsonl(event_dir / "subagent-events.jsonl")
        invocation_id = task["invocation_id"]
        allowed = set(task["allowed_evidence_ids"])
        invocation = _read(run_dir / task["invocation_ref"])
        if invocation.get("input_hash") != canonical_hash(_read(run_dir / task["input_ref"])):
            raise IndependentSkepticStageError("COUNTER_INPUT_HASH_DRIFT")
        dispatch = [item for item in dispatches if item.get("decision") == "ALLOW" and item.get("task_name") == task["task_name"]]
        starts = [item for item in events if item.get("hook_event_name") == "SubagentStart"
                  and item.get("context_binding", {}).get("status") == "DELIVERED"
                  and item.get("context_binding", {}).get("invocation_id") == invocation_id]
        stops = [item for item in events if item.get("hook_event_name") == "SubagentStop"
                 and item.get("output_binding", {}).get("invocation_id") == invocation_id]
        queries = [item for item in tool_events if item.get("run_id") == forward["run_id"]
                   and item.get("agent") == "runtime_skeptic"
                   and item.get("invocation_id") == invocation_id
                   and item.get("tool") == "fixture_evidence.query"
                   and isinstance(item.get("evidence_ids"), list)
                   and item["evidence_ids"] and set(item["evidence_ids"]) <= allowed
                   and item.get("access_mode") == "read"
                   and item.get("adapter_version") == "fixture-gate-scoped/2.3.0"
                   and isinstance(item.get("input_hash"), str)
                   and len(item["input_hash"]) == 64
                   and isinstance(item.get("output_hash"), str)
                   and len(item["output_hash"]) == 64
                   and item.get("event_hash") == canonical_hash(_without_hash(item, "event_hash"))]
        authenticated = (
            len(dispatch) == 1 and len(starts) == 1 and len(stops) == 1
            and starts[0].get("child_session_id") == stops[0].get("child_session_id")
            and starts[0].get("agent_type") == stops[0].get("agent_type") == "runtime_skeptic"
            and len(queries) >= 1
        )
        report_path = run_dir / task["report_ref"]
        report = None
        validation_status = "MISSING"
        if report_path.is_file() and authenticated:
            report = _read(report_path)
            try:
                validate_skeptic_report(report, run_id=forward["run_id"], manifest=invocation)
                validate_report_query_closure(report, queries)
                if (report.get("schema_version") != "counter-thesis-report/2.1.0"
                        or stops[0].get("output_capture", {}).get("status") != "SAVED"
                        or stops[0].get("output_capture", {}).get("output_hash") != canonical_hash(report)):
                    raise IndependentSkepticStageError("COUNTER_CAPTURE_HASH_INVALID")
                validation_status = "PASSED"
            except ValueError:
                validation_status = "FAILED"
        elif report_path.is_file():
            validation_status = "FAILED"
        status = report["status"] if report is not None and validation_status == "PASSED" else (
            "SYSTEM_FAILED" if validation_status == "FAILED" else "NOT_RESEARCHED"
        )
        entries.append({
            "security_id": task["security_id"], "invocation_id": invocation_id,
            "status": status, "validation_status": validation_status,
            "report": (
                _artifact_record(run_dir, task["report_ref"], canonical_hash(report))
                if report is not None and validation_status == "PASSED" else None
            ),
            "markdown_ref": task["markdown_ref"] if validation_status == "PASSED" else None,
        })
        execution.append({
            "security_id": task["security_id"], "invocation_id": invocation_id,
            "input_hash": invocation["input_hash"], "dispatch_count": len(dispatch),
            "start_count": len(starts), "stop_count": len(stops),
            "gate_scoped_nonempty_query_count": len(queries),
            "queried_evidence_ids": sorted({
                evidence_id for query in queries for evidence_id in query["evidence_ids"]
            }),
            "status": validation_status,
        })
    proof = {
        "schema_version": "independent-skeptic-execution-proof/1.0.0",
        "run_id": forward["run_id"], "gate_hash": forward["gate_hash"],
        "forward_bundle_hash": forward["bundle_hash"], "tasks": execution,
        "complete_portfolio_decision": False,
    }
    proof["proof_hash"] = canonical_hash(proof)
    proof_ref = (
        "research/skeptic/execution-proof.json" if attempt == 1
        else f"research/skeptic/attempts/{attempt}/execution-proof.json"
    )
    _write(run_dir / proof_ref, proof)
    by_security = {item["security_id"]: item for item in entries}
    coverage = []
    for position in handoff["portfolio"]["positions"]:
        security_id = position["security_id"]
        if position["asset_type"] != "COMMON_STOCK":
            coverage.append({
                "security_id": security_id, "asset_type": position["asset_type"],
                "status": "CAPABILITY_GAP", "gap_reason": "本阶段不研究该资产类别。",
            })
            continue
        entry = by_security[security_id]
        completed = entry["validation_status"] == "PASSED" and entry["status"] in {"COMPLETE", "LOW_CONFIDENCE"}
        coverage.append({
            "security_id": security_id, "asset_type": "COMMON_STOCK",
            "status": "READY" if completed else "PARTIAL",
            "gap_reason": None if completed else f"独立反证未完成：{entry['status']} / {entry['validation_status']}",
        })
    ready = all(item["status"] == "READY" for item in coverage if item["asset_type"] == "COMMON_STOCK")
    package = {
        "schema_version": "pre-decision-research-package/1.0.0",
        "package_id": f"pre-decision:{forward['run_id']}", "run_id": forward["run_id"],
        "handoff_id": handoff["handoff_id"], "handoff_hash": handoff["handoff_hash"],
        "portfolio_hash": handoff["portfolio_hash"],
        "request_id": request["request_id"], "request_hash": request["request_hash"],
        "decision_cutoff": forward["decision_cutoff"], "gate_hash": forward["gate_hash"],
        "forward_bundle": _artifact_record(
            run_dir, "research/holding-research-bundle.json", forward["bundle_hash"]
        ),
        "dispatch_index": _artifact_record(run_dir, relative_index, index["index_hash"]),
        "execution_proof": _artifact_record(run_dir, proof_ref, proof["proof_hash"]),
        "counter_theses": entries, "coverage": coverage,
        "consumability": "DOWNSTREAM_READY" if ready else "STRUCTURALLY_CONSUMABLE",
        "complete_portfolio_decision": False,
        "artifact_refs": sorted({
            "research/holding-research-bundle.json", "research/holding-research-bundle.md",
            relative_index, proof_ref,
            *(item["report"]["artifact_ref"] for item in entries if item["report"] is not None),
            *(item["markdown_ref"] for item in entries if item["markdown_ref"] is not None),
        }),
    }
    package["package_hash"] = canonical_hash(package)
    validate_predecision_package(repository_root, run_dir, package)
    package_ref = (
        "research/skeptic/pre-decision-research-package.json" if attempt == 1
        else f"research/skeptic/attempts/{attempt}/pre-decision-research-package.json"
    )
    _write(run_dir / package_ref, package)
    summary = [
        "# 正向研究与独立反证交接", "",
        f"- 截止：`{package['decision_cutoff']}`",
        f"- 状态：`{package['consumability']}`；不代表投资建议或研究质量通过。",
        "- 正向报告：[HoldingResearchBundle]("
        + os.path.relpath(
            "research/holding-research-bundle.md", start=Path(package_ref).parent
        )
        + ")", "",
        "## 逐证券反证", "",
    ]
    for item in entries:
        label = item["security_id"]
        if item["markdown_ref"]:
            link = os.path.relpath(item["markdown_ref"], start=Path(package_ref).parent)
            summary.append(f"- {label}：`{item['status']}`；[阅读反证正文]({link})")
        else:
            summary.append(f"- {label}：`{item['status']}`；没有合法反证正文。")
    summary.extend(["", "## 非普通股覆盖", ""])
    summary.extend(
        f"- {item['security_id']}：{item['gap_reason']}"
        for item in coverage if item["asset_type"] != "COMMON_STOCK"
    )
    markdown_ref = package_ref.removesuffix(".json") + ".md"
    _write(run_dir / markdown_ref, "\n".join(summary) + "\n")
    return {"status": "PASSED" if ready else "PARTIAL", "run_id": forward["run_id"],
            "consumability": package["consumability"], "package_hash": package["package_hash"],
            "package_ref": package_ref}


def build_skeptic_stage_prompt(
    repository_root: Path, run_dir: Path, *, index_ref: str | None = None,
    task_names: Sequence[str] | None = None,
) -> str:
    """主线程只调度；逐股冻结输入由 SubagentStart Hook 独立交付。"""

    del repository_root
    index = read_dispatch_index(run_dir, index_ref)
    selected = set(task_names) if task_names is not None else {task["task_name"] for task in index["tasks"]}
    if not selected or not selected <= {task["task_name"] for task in index["tasks"]}:
        raise IndependentSkepticStageError("COUNTER_RETRY_TASK_SET_INVALID")
    mapping = {
        task["task_name"]: {
            "agent_type": "runtime_skeptic", "security_id": task["security_id"],
            "message": "启动本次冻结的独立反证研究；完整上下文由 SubagentStart Hook 交付。",
        }
        for task in index["tasks"] if task["task_name"] in selected
    }
    return f"""你是独立反证阶段的宿主调度主线程，不是 CIO，也不产生研究结论。运行 ID：{index['run_id']}。

仅按以下映射使用 collaboration spawn_agent；每项必须传 agent_type=runtime_skeptic、对应 task_name、给定 message、fork_turns=none。不得把正向报告、bundle、未解决问题或报告 hash 放入 message；逐股冻结包由 Hook 交付。最多同时保持 {index['target_concurrency']} 个活跃 Agent；先填满槽位，结束一个后补位。只使用 wait_agent 等待所有任务真实终态；不得派发 CIO、Market Catalyst、Company Analyst 或 Risk，不得自行修改报告或查询包外资料。

任务映射：{json.dumps(mapping, ensure_ascii=False, sort_keys=True)}

全部任务形成终态后，只返回 JSON：{{"stage":"{STAGE}","run_id":"{index['run_id']}","dispatched":{len(mapping)},"completed":{len(mapping)}}}。completed 只表示子任务结束；报告合法性和交接状态由确定性 finalizer 决定。"""


def launch_skeptic_phase(
    repository_root: Path, *, run_dir: Path, codex_binary: str = "codex",
    timeout_seconds: int = 2400, index_ref: str | None = None,
    task_names: Sequence[str] | None = None,
) -> tuple[dict[str, Any], int]:
    """仅供宿主 launcher 调用一次；不运行 CIO、Risk 或任何决策层。"""

    from product.runtime.nested_codex import (
        build_nested_codex_command, fixture_mcp_runtime_environment, integrity_snapshot,
    )

    repository_root = Path(repository_root).resolve()
    run_dir = Path(run_dir).resolve()
    manifest = _read(run_dir / "run_manifest.json")
    if (manifest.get("stage") != STAGE or manifest.get("complete_portfolio_decision") is not False
            or Path(str(manifest.get("output_dir", ""))).resolve() != run_dir):
        raise IndependentSkepticStageError("COUNTER_RUN_MANIFEST_INVALID")
    validate_forward_gate(repository_root, run_dir)
    index = read_dispatch_index(run_dir, index_ref)
    selected = set(task_names) if task_names is not None else {task["task_name"] for task in index["tasks"]}
    if not selected or not selected <= {task["task_name"] for task in index["tasks"]}:
        raise IndependentSkepticStageError("COUNTER_RETRY_TASK_SET_INVALID")
    attempt = index.get("attempt", 1)
    invocation_dir = run_dir / "invocation/skeptic"
    if attempt > 1:
        invocation_dir = invocation_dir / f"attempt-{attempt}"
    if invocation_dir.exists():
        raise IndependentSkepticStageError("COUNTER_ALREADY_LAUNCHED")
    invocation_dir.mkdir(parents=True)
    runtime_root = run_dir / (".codex-runtime-skeptic" if attempt == 1 else f".codex-runtime-skeptic-{attempt}")
    sqlite_home, log_dir, tmp_dir = (
        runtime_root / "sqlite", runtime_root / "logs", runtime_root / "tmp"
    )
    for path in (sqlite_home, log_dir, tmp_dir):
        path.mkdir(parents=True, exist_ok=False)
    prompt = build_skeptic_stage_prompt(repository_root, run_dir, index_ref=index_ref, task_names=sorted(selected))
    prompt_path = invocation_dir / "prompt.txt"
    _write(prompt_path, prompt)
    parent_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object", "additionalProperties": False,
        "required": ["stage", "run_id", "dispatched", "completed"],
        "properties": {
            "stage": {"type": "string", "const": STAGE},
            "run_id": {"type": "string", "const": index["run_id"]},
            "dispatched": {"type": "integer", "const": len(selected)},
            "completed": {"type": "integer", "const": len(selected)},
        },
    }
    schema_path = invocation_dir / "parent-output.schema.json"
    _write(schema_path, parent_schema)
    command = build_nested_codex_command(
        codex_binary=codex_binary, product_root=repository_root / "product",
        run_dir=run_dir, model=manifest["parent_model"],
        sqlite_home=sqlite_home, log_dir=log_dir,
        final_message_path=tmp_dir / "final-message.json",
        hook_recorder_path=repository_root / "product/runtime/codex_hook_recorder.py",
        output_schema_path=schema_path, fixture_mcp_run_dir=run_dir,
        hook_agent_matcher="^runtime_skeptic$",
    )
    events_path = invocation_dir / "codex-events.jsonl"
    hook_events_path = invocation_dir / "subagent-events.jsonl"
    dispatch_events_path = invocation_dir / "subagent-dispatches.jsonl"
    stderr_path = invocation_dir / "codex-stderr.log"
    environment = dict(os.environ)
    environment.update({
        "TMPDIR": str(tmp_dir), "PYTHONDONTWRITEBYTECODE": "1",
        "STOCK_AGENT_RUN_DIR": str(run_dir),
        "STOCK_AGENT_FIXTURE_MCP_RUN_DIR": str(run_dir),
        "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(hook_events_path),
        "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(dispatch_events_path),
        "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": "runtime_skeptic",
        "STOCK_AGENT_INDEPENDENT_SKEPTIC_STAGE": "independent-skeptic-runtime/1.0.0",
        "STOCK_AGENT_SKEPTIC_DISPATCH_INDEX": INITIAL_INDEX_REF if index_ref is None else index_ref,
        **fixture_mcp_runtime_environment(),
    })
    for key in ("STOCK_AGENT_START_CONTEXT", "STOCK_AGENT_CAPTURE_SPECIALIST_OUTPUT",
                "STOCK_AGENT_MULTIDIMENSIONAL_STAGE", "STOCK_AGENT_RESEARCH_TASK_NAME",
                "STOCK_AGENT_RESEARCH_TASK_NAMES"):
        environment.pop(key, None)
    environment["STOCK_AGENT_RESEARCH_TASK_NAMES"] = json.dumps(sorted(selected))
    before = integrity_snapshot(repository_root)
    _write(invocation_dir / "environment-manifest.json", {
        "schema_version": "independent-skeptic-environment/1.0.0",
        "run_id": index["run_id"], "repo_root": str(repository_root),
        "product_root": str(repository_root / "product"), "run_dir": str(run_dir),
        "command": command, "model": manifest["parent_model"],
        "sandbox": "workspace-write", "approval_policy": "never",
        "prompt_hash": file_hash(prompt_path), "source_integrity_before": before,
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    })
    try:
        process = subprocess.run(
            command, input=prompt, text=True, cwd=repository_root / "product",
            env=environment, capture_output=True, timeout=timeout_seconds, check=False,
        )
        stdout, stderr, process_code, timed_out = (
            process.stdout, process.stderr, process.returncode, False
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        process_code, timed_out = 124, True
    _write(events_path, stdout)
    _write(stderr_path, stderr)
    failure_code = None
    try:
        if not timed_out and process_code == 0:
            raw_final = _read(tmp_dir / "final-message.json")
            if raw_final != {
                "stage": STAGE, "run_id": index["run_id"],
                "dispatched": len(selected), "completed": len(selected),
            }:
                raise IndependentSkepticStageError("COUNTER_FINAL_MESSAGE_INVALID")
            _write(invocation_dir / "final-message.json", raw_final)
        result = finalize_skeptic_phase(repository_root, run_dir, index_ref=index_ref)
        if timed_out:
            failure_code = "COUNTER_STAGE_TIMEOUT"
        elif process_code != 0:
            failure_code = "COUNTER_CODEX_PROCESS_FAILED"
    except (OSError, ValueError, KeyError, TypeError) as exc:
        failure_code = str(exc).split(":", 1)[0]
        result = {"status": "FAILED", "run_id": index["run_id"], "failure_code": failure_code}
    after = integrity_snapshot(repository_root)
    _write(invocation_dir / "process-result.json", {
        "schema_version": "independent-skeptic-process/1.0.0",
        "run_id": index["run_id"], "process_exit_code": process_code,
        "timed_out": timed_out, "stage_status": result["status"],
        "failure_code": failure_code, "source_integrity_unchanged": before == after,
    })
    return result, 0 if result["status"] == "PASSED" and failure_code is None and before == after else 7
