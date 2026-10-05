"""独立反证阶段的确定性前置门禁与第一轮 Evidence 授权。"""

from __future__ import annotations

import json
import hashlib
import copy
import fcntl
import os
import re
import subprocess
import tomllib
from datetime import datetime, timezone
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.council.intake_planning import validate_council_request
from product.runtime.research_input import (
    is_single_stock, load_research_input, research_input_binding, research_subjects, validate_research_input,
)
from product.runtime.hashing import canonical_hash, file_hash, legacy_envelope_hash, verify_legacy_envelope_hash, HashContractError
from product.runtime.fixture_mcp import SKEPTIC_ADAPTER_VERSION
from product.runtime.multidimensional_stage import check_multidimensional_bundle_consumable
from product.runtime.validation import collect_evidence_refs
from product.runtime.invocation import SPECIALIST_SEMANTIC_DRAFT, specialist_semantic_schema
from product.runtime.multidimensional_references import (
    VERSION as REFERENCE_TRANSPORT_VERSION, build_reference_map,
    reference_output_schema, translate_references, validate_reference_map,
)


STAGE = "INDEPENDENT_COUNTER_THESIS_RESEARCH"
DISPATCH_VERSION = "independent-skeptic-dispatch/1.0.0"
DELIVERY_VERSION = "skeptic-grounding-delivery/1.0.0"
CATALOG_MAX_BYTES = 64 * 1024
DELIVERY_MAX_BYTES = 320 * 1024
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


def _resolve_artifact(root: Path, relative: str) -> Path:
    """只读依赖不得借原绝对路径或符号链接读取包外文件。"""
    if (not isinstance(relative, str) or not relative
            or Path(relative).is_absolute() or ".." in Path(relative).parts):
        raise IndependentSkepticStageError(f"COUNTER_ARTIFACT_PATH_INVALID:{relative}")
    candidate = root / relative
    if any(path.is_symlink() for path in (candidate, *candidate.parents)
           if path == root or path.is_relative_to(root)):
        raise IndependentSkepticStageError(f"COUNTER_ARTIFACT_PATH_INVALID:{relative}")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root) or not resolved.is_file():
        raise IndependentSkepticStageError(f"COUNTER_ARTIFACT_MISSING:{relative}")
    return resolved


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
    index = _read(_resolve_artifact(root, relative))
    if (index.get("schema_version") != DISPATCH_VERSION
            or index.get("index_hash") != legacy_envelope_hash(index, hash_field="index_hash")):
        raise IndependentSkepticStageError("COUNTER_DISPATCH_INDEX_INVALID")
    if _index_ref(index.get("attempt")) != relative:
        raise IndependentSkepticStageError("COUNTER_DISPATCH_ATTEMPT_INVALID")
    if (not isinstance(index.get("tasks"), list)
            or any(not isinstance(task, dict) for task in index["tasks"])
            or index.get("semantic_output_version") not in {None, SPECIALIST_SEMANTIC_DRAFT}
            or any(task.get("semantic_output_version") != index.get("semantic_output_version")
                   for task in index["tasks"])):
        raise IndependentSkepticStageError("COUNTER_OUTPUT_PROTOCOL_BINDING_INVALID")
    if (index.get("reference_transport_version") not in {None, REFERENCE_TRANSPORT_VERSION}
            or any(task.get("reference_transport_version") != index.get("reference_transport_version")
                   for task in index["tasks"])):
        raise IndependentSkepticStageError("COUNTER_REFERENCE_PROTOCOL_BINDING_INVALID")
    return index


def resolve_skeptic_tool_scope(
    run_dir: Path, *, run_id: str, invocation_id: str, gate: Mapping[str, Any],
    index_ref: str | None = None,
    for_execution: bool = True,
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
    invocation_path = _resolve_artifact(root, task["invocation_ref"])
    invocation = _read(invocation_path)
    if invocation.get("semantic_output_version") != task.get("semantic_output_version"):
        raise IndependentSkepticStageError("COUNTER_OUTPUT_PROTOCOL_BINDING_INVALID")
    if invocation.get("reference_transport_version") != task.get("reference_transport_version"):
        raise IndependentSkepticStageError("COUNTER_REFERENCE_PROTOCOL_BINDING_INVALID")
    agent_input = _read(_resolve_artifact(root, task["input_ref"]))
    allowed = task.get("allowed_evidence_ids")
    if (not isinstance(allowed, list) or not allowed or allowed != sorted(set(allowed))
            or not set(allowed) <= set(gate.get("allowed_evidence_ids", []))
            or invocation.get("manifest_hash") != legacy_envelope_hash(invocation, hash_field="manifest_hash")
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
    if not for_execution:
        # 只验证已冻结的输入/契约，不授予工具权限、不检查当前 Agent 文件。
        # 老绝对 output_schema 留作历史记录；实际读取 task 的包内相对路径。
        from product.runtime.schema_validation import validate_schema_definition
        schema_path = _resolve_artifact(root, task["schema_ref"])
        if file_hash(schema_path) != invocation.get("output_schema_hash"):
            raise IndependentSkepticStageError("COUNTER_ARTIFACT_SCHEMA_DRIFT")
        schema = _read(schema_path)
        if schema.get("$id") != "portfolio-council/counter-thesis-report/2.1.0":
            raise IndependentSkepticStageError("COUNTER_ARTIFACT_SCHEMA_UNSUPPORTED_VERSION")
        validate_schema_definition(schema, schema_resources={})
        prompt = _resolve_artifact(root, task["prompt_ref"]).read_text(encoding="utf-8")
        if canonical_hash({"task_prompt": prompt}) != invocation.get("task_prompt_hash"):
            raise IndependentSkepticStageError("COUNTER_ARTIFACT_PROMPT_DRIFT")
        if (invocation.get("input_artifact") != task["input_ref"]
                or invocation.get("task_prompt_artifact") != task["prompt_ref"]
                or invocation.get("tool_permissions") != ["fixture_evidence.query", "fixture_math.calculate"]):
            raise IndependentSkepticStageError("COUNTER_ARTIFACT_INVOCATION_INVALID")
        return invocation_path, allowed
    from product.runtime.invocation import verify_invocation_manifest
    product_root = Path(str(
        _read(root / "run_manifest.json").get("discovery", {}).get("product_root", "")
    )).resolve()
    if product_root.name != "product":
        raise IndependentSkepticStageError("COUNTER_PRODUCT_ROOT_INVALID")
    verify_invocation_manifest(product_root.parent, invocation, agent_input=agent_input)
    return invocation_path, allowed


def validate_core_coverage(bundle: Mapping[str, Any]) -> None:
    # 显式反证读取已验证结构，不要求作者先自认证“研究通过”。
    # 具体输入资格仍由下面的核心覆盖和真实绑定检查决定。
    if bundle.get("consumability") not in {"DOWNSTREAM_READY", "STRUCTURALLY_CONSUMABLE"}:
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
    handoff = load_research_input(run_dir)
    request = _read(run_dir / "council-request.json")
    gate = _read(run_dir / "evidence/gate.json")
    bundle_path = run_dir / "research/holding-research-bundle.json"
    bundle = _read(bundle_path)
    if (manifest.get("manifest_hash") != legacy_envelope_hash(manifest, hash_field="manifest_hash")
            or manifest.get("stage") != STAGE or request.get("stage") != STAGE
            or manifest.get("complete_portfolio_decision") is not False
            or manifest.get("downstream_stages_started") not in ([], ["FORWARD_MULTIDIMENSIONAL_RESEARCH"])):
        raise IndependentSkepticStageError("COUNTER_STAGE_BINDING_INVALID")
    validate_research_input(handoff)
    validate_council_request(request, handoff=handoff)
    if (manifest.get("run_id") != gate.get("run_id")
            or manifest.get("run_id") != bundle.get("run_id")
            or any(manifest.get(k) != v for k, v in research_input_binding(handoff).items() if k != "handoff_id")
            or manifest.get("council_request_hash") != request.get("request_hash")
            or manifest.get("gate_hash") != gate.get("bundle_hash")
            or gate.get("bundle_hash") != legacy_envelope_hash(gate, hash_field="bundle_hash")
            or bundle.get("decision_cutoff") != gate.get("decision_cutoff")
            or bundle.get("bindings") != {
                **research_input_binding(handoff),
                "council_request_id": request["request_id"],
                "council_request_hash": request["request_hash"],
            }):
        raise IndependentSkepticStageError("COUNTER_FORWARD_BINDING_INVALID")
    proof = check_multidimensional_bundle_consumable(repository_root, run_dir, persist=False)
    validate_core_coverage(bundle)
    if proof["status_projection"]["agent_declared_content_failure"]:
        raise IndependentSkepticStageError("COUNTER_FORWARD_DECLARED_CONTENT_FAILURE")
    if any((run_dir / name).exists() for name in (
        "decision.json", "risk.json", "agents/runtime_cio.json", "outcome.json",
    )):
        raise IndependentSkepticStageError("COUNTER_DOWNSTREAM_ARTIFACT_FORBIDDEN")
    return {
        "run_id": manifest["run_id"], "decision_cutoff": gate["decision_cutoff"],
        "gate_hash": gate["bundle_hash"], "bundle_hash": bundle["bundle_hash"],
        "bundle_file_hash": file_hash(bundle_path), "consumption_proof_hash": proof["proof_hash"],
        "common_stock_security_ids": bundle["common_stock_security_ids"],
        "status_projection": proof["status_projection"],
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


def _skeptic_task_prompt(security_id: str, *, catalog_enabled: bool = False) -> str:
    discovery = (
        "本任务已启用 fixture_runtime.evidence_catalog：先用 view=fields 按证券/semantic_field_prefix 分页发现指标，"
        "再用 view=records、精确 semantic_field 读取引用、期间、来源及章节类型；"
        "可直接筛选你需要核验的已知指标，不必遍历全目录。返回 total/next_offset，未读页不是来源不存在。"
        "目录没有事实值，目录读取不算 Evidence query，选出短引用后必须调用原 query 读取完整事实。"
        "SEC同名章节可能同时有HEADING_ONLY目录项和SECTION_EXCERPT截断正文；核验实际正文，"
        "不能把目录行当正文或把片段称完整全文。任何估值资料缺口须区分价格/EPS/股数的可读取性与"
        "正常化预测/估值模型未知；不要仅因未读取就宣称来源缺失。"
        "首稿若仅有空依据挑战，会收到唯一一次原作者局部纠正；自行核实、改写或将纯缺口保留在data_gaps，"
        "不得编造假设或贴不支持陈述的引用，其余挑战、身份、状态与置信度不得更改。"
        if catalog_enabled else "先主动查询需要核验的事实，未查询不等于来源没有该数据。"
    )
    return discovery + (
        "工具调用与输出身份分工：fixture_runtime.query 调用必须携带本上下文 "
        "tool_context.required_identity_arguments 中的 run_id、agent、invocation_id 原值；"
        "identity 亦列出相同可信身份。它们已交付，不需要从省略的 invocation 或 agent_input 中找。"
        "输出 JSON 不填这些身份，并不表示工具调用可以省略身份。"
        "先从 allowed_evidence_ids 选择非空引用并调用 query 核验，再形成研究结论；"
        "不得在没有核对 tool_context 和 identity 的情况下宣称身份缺失。"
        f"独立研究 {security_id} 的公司特定失败路径与替代解释。"
        "第一轮不得读取或引用本系统 Company Analyst、Market Catalyst、CIO 等 Agent 的正向研究报告、摘要、未解决问题或其 hash；"
        "本系统 Agent 产物与原始来源不同：Gate 已允许的发行人披露、行情、第三方 Morningstar 等来源资料"
        "不是本系统 Analyst 结论。第三方投资观点只能标为来源观点或待验证推断，不得升级成公司事实；"
        "不能只因原始资料字段名含 investment_thesis 而宣称本系统上下文隔离被破坏。"
        "允许引用在本任务上下文顶层 allowed_evidence_ids，"
        "不在已机械省略的 invocation 内；请先读取这份非空清单再选择需要核验的引用。"
        "query 的 evidence_ids 必须来自该清单；空列表不是发现接口，不要用空查询代替读取清单。"
        "只能按冻结包给出的任务短 Evidence 引用使用只读 fixture_runtime.query 主动核验非空事实。"
        "引用仅从 allowed_evidence_ids 选择，不拼接来源、时间或说明；正式 ID 由运行时精确装配。"
        "事实性断言用 Evidence 支持；纯情景显式标注本报告 assumptions，"
        "说明传导逻辑、待补证据和可观察的推翻条件。"
        "每项 challenges 必须有实际查阅的 evidence_refs 或本报告已定义的 assumption_ids，"
        "两者均空会被既有 UNGROUNDED_CHALLENGE 门禁拒绝。"
        "纯资料缺口或无法形成反证写入 data_gaps/uncertainties，不冒充独立挑战；"
        "不得为过门禁附上不支持陈述的引用或编造假设。"
        "核对本任务实际交付的资料索引及适用字段，再主动查询需要的事实；"
        "目录存在不等于已查阅，尚未查询也不等于来源没有该数据。"
        "无法完成研究则如实使用 INSUFFICIENT_EVIDENCE 或 TIMEOUT，"
        "不得编造风险或给出投资动作。只按交付的 output_schema 返回研究语义 JSON；"
        "不要填运行身份、schema_version、Skill 执行元数据、hash 或 artifact_refs，"
        "这些由可信运行记录装配。原报告 2.1.0 的研究、引用与信息隔离要求不变。"
        f"scope 是字符串，不是对象；例如 \"{security_id}：冻结截止点下的独立失败路径研究\"，"
        "必须包含本任务原始 security_id 并说明独立研究范围；"
        "该研究范围标识不是 Evidence 短引用，不能用 ticker 或 e.* 替代。"
        "assumptions 每项必须使用 assumption_id 和 statement；例如 "
        "{\"assumption_id\":\"A1\",\"statement\":\"待检验的条件性假设\"}，不得使用 id 替代 assumption_id。"
        "challenges.assumption_ids 仅引用本稿已声明的 assumption_id。"
        "confidence 按交付 Schema 的数值类型填写，理由放 confidence_rationale；不得填 LOW 等等级字符串。"
    )


def _skeptic_semantic_schema(schema, invocation):
    result = specialist_semantic_schema(schema)
    if invocation.get("skeptic_delivery_version") == DELIVERY_VERSION:
        # Mirror an existing hard gate; do not weaken the authoritative report validator.
        result["properties"]["challenges"]["items"]["anyOf"] = [
            {"properties": {"evidence_refs": {"minItems": 1}}},
            {"properties": {"assumption_ids": {"minItems": 1}}},
        ]
    elif invocation.get("skeptic_delivery_version") is not None:
        raise IndependentSkepticStageError("COUNTER_DELIVERY_VERSION_INVALID")
    return result


def _catalog_facts(packet, gate):
    allowed = packet["agent_input"]["allowed_evidence_ids"]
    facts = {item["evidence_id"]: item for item in gate["allowed_evidence"]}
    if len(facts) != len(gate["allowed_evidence"]) or set(allowed) - set(facts):
        raise IndependentSkepticStageError("COUNTER_CATALOG_GATE_INVALID")
    return [facts[identifier] for identifier in allowed]


def _catalog_summary(packet, gate):
    facts = _catalog_facts(packet, gate)
    counts = {}
    for item in facts:
        security = item.get("security_id")
        counts[security] = counts.get(security, 0) + 1
    return {"version": DELIVERY_VERSION, "record_count": len(facts),
            "securities": [{"security_id": key, "count": counts[key]} for key in sorted(counts, key=str)],
            "tool": "fixture_runtime.evidence_catalog", "rule": "Metadata only; query selected references before citing."}


def read_skeptic_evidence_catalog(packet, gate, *, view="fields", security_id=None,
                                 semantic_field=None, semantic_field_prefix=None, offset=0, limit=32):
    """Bounded metadata discovery over the exact task allowlist, never source selection."""
    if packet["invocation"].get("skeptic_delivery_version") != DELIVERY_VERSION:
        raise IndependentSkepticStageError("COUNTER_CATALOG_NOT_AUTHORIZED")
    if (view not in {"fields", "records"} or isinstance(offset, bool) or not isinstance(offset, int)
            or offset < 0 or isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 64):
        raise IndependentSkepticStageError("COUNTER_CATALOG_SELECTOR_INVALID")
    if semantic_field is not None and semantic_field_prefix is not None:
        raise IndependentSkepticStageError("COUNTER_CATALOG_SELECTOR_INVALID")
    for selector in (semantic_field, semantic_field_prefix):
        if selector is not None and (not isinstance(selector, str) or not selector.strip() or len(selector) > 256):
            raise IndependentSkepticStageError("COUNTER_CATALOG_SELECTOR_INVALID")
    facts = _catalog_facts(packet, gate)
    if security_id is not None and security_id not in {item.get("security_id") for item in facts}:
        raise IndependentSkepticStageError("COUNTER_CATALOG_SECURITY_OUTSIDE_SCOPE")
    selected = [item for item in facts if (security_id is None or item.get("security_id") == security_id)
                and (semantic_field is None or item.get("semantic_field") == semantic_field)
                and (semantic_field_prefix is None or str(item.get("semantic_field", "")).startswith(semantic_field_prefix))]
    if view == "fields":
        groups = {}
        for item in selected:
            key = (item.get("security_id"), item.get("semantic_field"))
            groups[key] = groups.get(key, 0) + 1
        rows = [{"security_id": key[0], "semantic_field": key[1], "count": groups[key]}
                for key in sorted(groups, key=lambda key: tuple(map(str, key)))]
    else:
        from product.runtime.multidimensional_stage import _text_locator
        inverse = {value: ref for ref, value in packet["reference_map"]["evidence"].items()}
        rows = []
        for item in sorted(selected, key=lambda item: (str(item.get("as_of")), item["evidence_id"])):
            metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
            row = {key: item.get(key) for key in ("security_id", "semantic_field", "source_id", "as_of", "retrieved_at", "unit")}
            row.update({key: metadata.get(key) for key in ("period_start", "period_end", "fiscal_period", "context_type", "form")})
            row.update(_text_locator(item))
            row["evidence_id"] = inverse[item["evidence_id"]]
            rows.append({key: value for key, value in row.items() if value is not None})
    if offset > len(rows):
        raise IndependentSkepticStageError("COUNTER_CATALOG_OFFSET_INVALID")
    page = rows[offset:offset + limit]
    result = {"version": DELIVERY_VERSION, "view": view, "total": len(rows), "offset": offset,
              "next_offset": offset + len(page) if offset + len(page) < len(rows) else None,
              "rows": page, "facts_read": False}
    if len(json.dumps(result, ensure_ascii=False, separators=(",", ":")).encode()) > CATALOG_MAX_BYTES:
        raise IndependentSkepticStageError("COUNTER_CATALOG_RESPONSE_TOO_LARGE:use smaller limit")
    return result


def _skeptic_packet(run_dir, *, identity, agent_input, invocation, prompt, schema):
    """首轮和恢复共用冻结 packet；不接收正向报告或主张。"""
    packet = {
        "dispatch_contract": DISPATCH_VERSION, "identity": dict(identity),
        "agent_input": agent_input, "invocation": invocation, "task_prompt": prompt,
        "output_schema": _skeptic_semantic_schema(schema, invocation),
        "tool_context": {
            "mcp_server": "fixture_runtime", "query_tool": "fixture_runtime.query",
            "required_identity_arguments": {key: identity[key] for key in ("run_id", "agent", "invocation_id")},
        },
    }
    if invocation.get("skeptic_delivery_version") == DELIVERY_VERSION:
        packet["evidence_catalog"] = _catalog_summary(packet, _read(Path(run_dir) / "evidence/gate.json"))
        packet["tool_context"]["catalog_tool"] = "fixture_runtime.evidence_catalog"
    if invocation.get("reference_transport_version") == REFERENCE_TRANSPORT_VERSION:
        packet["reference_transport_version"] = REFERENCE_TRANSPORT_VERSION
        packet["allowed_evidence_ids"] = list(agent_input["allowed_evidence_ids"])
        packet["reference_map"] = build_reference_map(
            packet, canonical_hash(_read(Path(run_dir) / "evidence/gate.json")), str(Path(run_dir).resolve()),
        )
    return packet


def skeptic_model_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    """只投影机械包装及引用；事实、限制、问题和研究结构保持原样。"""
    version = packet.get("reference_transport_version")
    mapping = packet.get("reference_map")
    if version is None and mapping is None:
        return copy.deepcopy(dict(packet))  # 历史读取不迁移、不改写。
    if version != REFERENCE_TRANSPORT_VERSION or not isinstance(mapping, dict):
        raise IndependentSkepticStageError("COUNTER_REFERENCE_PROTOCOL_BINDING_INVALID")
    validate_reference_map(mapping)
    base = {key: value for key, value in packet.items() if key != "reference_map"}
    if mapping != build_reference_map(base, mapping["binding"]["gate_hash"], mapping["binding"]["run_dir"]):
        raise IndependentSkepticStageError("COUNTER_REFERENCE_MAP_BINDING_INVALID")
    result = translate_references(base, mapping, to_model=True)
    result.pop("invocation")
    result["agent_input"] = {key: value for key, value in result["agent_input"].items()
                             if key not in {"run_id", "agent", "gate_hash", "request_id", "report_schema_version"}}
    result["output_schema"] = reference_output_schema(packet["output_schema"], mapping)
    return result


def serialize_skeptic_dispatch_context(packet: Mapping[str, Any]) -> str:
    model = skeptic_model_packet(packet)
    if packet.get("reference_transport_version") == REFERENCE_TRANSPORT_VERSION:
        from product.runtime.invocation import compact_specialist_schema
        allowed = model["allowed_evidence_ids"]
        if model["agent_input"].get("allowed_evidence_ids") != allowed:
            raise IndependentSkepticStageError("COUNTER_CONTEXT_ALLOWED_SET_MISMATCH")
        model["output_schema"] = compact_specialist_schema(
            model["output_schema"], allowed,
            evidence_schema=model["output_schema"]["properties"]["evidence_refs"]["items"],
        )
        model["agent_input"].pop("allowed_evidence_ids")
    # Keep schema shape before its shared ID enum and the reference inventory.
    # The authoritative frozen schema and server-side validation are unchanged.
    leading = ("tool_context", "identity", "task_prompt", "output_schema")
    ordered = {key: model[key] for key in leading if key in model}
    ordered.update({key: value for key, value in model.items() if key not in leading})
    serialized = json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))
    if (packet["invocation"].get("skeptic_delivery_version") == DELIVERY_VERSION
            and len(serialized.encode()) > DELIVERY_MAX_BYTES):
        raise IndependentSkepticStageError("COUNTER_START_CONTEXT_TOO_LARGE")
    return serialized


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
            or forward_index.get("index_hash") != legacy_envelope_hash(forward_index, hash_field="index_hash")
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
        if is_single_stock(request):
            limitations.append('本任务仅为非持仓单股研究，没有账户或数量资料，不推断持有或空仓。')
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
        prompt = _skeptic_task_prompt(security_id, catalog_enabled=is_single_stock(request))
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
        invocation["semantic_output_version"] = SPECIALIST_SEMANTIC_DRAFT
        invocation["reference_transport_version"] = REFERENCE_TRANSPORT_VERSION
        if is_single_stock(request):
            invocation["skeptic_delivery_version"] = DELIVERY_VERSION
        invocation["manifest_hash"] = legacy_envelope_hash(invocation, hash_field="manifest_hash")
        verify_invocation_manifest(repository_root, invocation, agent_input=agent_input)
        _write(run_dir / invocation_ref, invocation)
        packet = _skeptic_packet(run_dir, identity={
                "run_id": proof["run_id"], "task_name": task_name,
                "agent": "runtime_skeptic", "invocation_id": invocation["invocation_id"],
                "security_id": security_id,
            }, agent_input=agent_input, invocation=invocation, prompt=prompt, schema=schema)
        _write(run_dir / packet_ref, packet)
        tasks.append({
            "task_id": f"skeptic:{security_id}",
            "semantic_output_version": SPECIALIST_SEMANTIC_DRAFT,
            "reference_transport_version": REFERENCE_TRANSPORT_VERSION,
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
        "semantic_output_version": SPECIALIST_SEMANTIC_DRAFT,
        "reference_transport_version": REFERENCE_TRANSPORT_VERSION,
        "run_id": proof["run_id"], "attempt": 1,
        "forward_bundle_hash": proof["bundle_hash"],
        "forward_bundle_file_hash": proof["bundle_file_hash"],
        "gate_hash": proof["gate_hash"],
        "target_concurrency": min(manifest["target_concurrency"], len(tasks)),
        "tasks": tasks,
    }
    index["index_hash"] = legacy_envelope_hash(index, hash_field="index_hash")
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
    if previous_index.get("reference_transport_version") != REFERENCE_TRANSPORT_VERSION:
        raise IndependentSkepticStageError("COUNTER_LEGACY_REFERENCE_RESUME_RETIRED")
    previous_package_ref = (
        "research/skeptic/pre-decision-research-package.json" if latest == 1
        else f"research/skeptic/attempts/{latest}/pre-decision-research-package.json"
    )
    previous_package = _read(run_dir / previous_package_ref)
    # 单股旧尝试是历史证据，不是下一次调用的权限来源。
    historical_single_stock = is_single_stock(previous_package)
    validate_predecision_package(
        repository_root, run_dir, previous_package,
        for_execution=not historical_single_stock,
    )
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
        if historical_single_stock:
            resolve_skeptic_tool_scope(
                run_dir, run_id=forward["run_id"], invocation_id=old["invocation_id"],
                gate=_read(run_dir / "evidence/gate.json"), index_ref=previous_index_ref,
                for_execution=False,
            )
        else:
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
        # 新尝试生成当前语义协议说明，既有尝试的 Prompt/锁不回写。
        prompt = _skeptic_task_prompt(old["security_id"], catalog_enabled=historical_single_stock)
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
        invocation["semantic_output_version"] = SPECIALIST_SEMANTIC_DRAFT
        invocation["reference_transport_version"] = REFERENCE_TRANSPORT_VERSION
        if historical_single_stock:
            invocation["skeptic_delivery_version"] = DELIVERY_VERSION
        invocation["manifest_hash"] = legacy_envelope_hash(invocation, hash_field="manifest_hash")
        verify_invocation_manifest(repository_root, invocation, agent_input=agent_input)
        _write(run_dir / invocation_ref, invocation)
        packet = _skeptic_packet(run_dir, identity={
                "run_id": forward["run_id"], "task_name": old["task_name"],
                "agent": "runtime_skeptic", "invocation_id": invocation["invocation_id"],
                "security_id": old["security_id"],
            }, agent_input=agent_input, invocation=invocation, prompt=prompt, schema=schema)
        _write(run_dir / packet_ref, packet)
        tasks.append({
            **old, "attempt": attempt, "invocation_id": invocation["invocation_id"],
            "semantic_output_version": SPECIALIST_SEMANTIC_DRAFT,
            "reference_transport_version": REFERENCE_TRANSPORT_VERSION,
            "input_ref": input_ref, "schema_ref": schema_ref, "prompt_ref": prompt_ref,
            "invocation_ref": invocation_ref, "packet_ref": packet_ref,
            "packet_hash": canonical_hash(packet),
            "report_ref": f"{attempt_root}/reports/{slug}/counter-thesis.json",
            "markdown_ref": f"{attempt_root}/reports/{slug}/counter-thesis.md",
        })
    index = {
        **{key: value for key, value in previous_index.items() if key not in {"tasks", "index_hash", "attempt"}},
        "attempt": attempt, "tasks": tasks,
        "semantic_output_version": SPECIALIST_SEMANTIC_DRAFT,
        "previous_package": _artifact_record(run_dir, previous_package_ref, previous_package["package_hash"]),
    }
    index["index_hash"] = legacy_envelope_hash(index, hash_field="index_hash")
    ref = _index_ref(attempt)
    _write(run_dir / ref, index)
    return {"status": "PREPARED", "run_id": forward["run_id"], "attempt": attempt,
            "retry_task_names": [task["task_name"] for task in retry], "dispatch_index": ref}


def validate_prepared_skeptic_resume(repository_root: Path, run_dir: Path, index_ref: str) -> dict[str, Any]:
    """显式消费未执行的新尝试；不准备、不补写、不自动选择下一次。"""
    repository_root = Path(repository_root).resolve()
    run_dir = Path(run_dir).resolve()
    forward = validate_forward_gate(repository_root, run_dir)
    index = read_dispatch_index(run_dir, index_ref)
    attempt = index["attempt"]
    if attempt < 2 or any(
        path.name.isdecimal() and int(path.name) > attempt
        for path in (run_dir / "research/skeptic/attempts").iterdir()
    ):
        raise IndependentSkepticStageError("COUNTER_PREPARED_ATTEMPT_NOT_LATEST")
    if (index.get("run_id") != forward["run_id"]
            or index.get("forward_bundle_hash") != forward["bundle_hash"]
            or index.get("forward_bundle_file_hash") != forward["bundle_file_hash"]
            or index.get("gate_hash") != forward["gate_hash"]):
        raise IndependentSkepticStageError("COUNTER_DISPATCH_FORWARD_DRIFT")
    prior_attempt = attempt - 1
    prior_ref = ("research/skeptic/pre-decision-research-package.json" if prior_attempt == 1
                 else f"research/skeptic/attempts/{prior_attempt}/pre-decision-research-package.json")
    prior = _read(_resolve_artifact(run_dir, prior_ref))
    if index.get("previous_package") != _artifact_record(run_dir, prior_ref, prior["package_hash"]):
        raise IndependentSkepticStageError("COUNTER_RESUME_CHAIN_DRIFT")
    validate_predecision_package(repository_root, run_dir, prior, for_execution=not is_single_stock(prior))
    prior_index = read_dispatch_index(run_dir, _index_ref(prior_attempt))
    prior_process_ref = ("invocation/skeptic/process-result.json" if prior_attempt == 1
                         else f"invocation/skeptic/attempt-{prior_attempt}/process-result.json")
    prior_process = _read(_resolve_artifact(run_dir, prior_process_ref))
    if (prior_process.get("source_integrity_unchanged") is not True
            or prior_process.get("run_id") != forward["run_id"]
            or prior["dispatch_index"] != _artifact_record(run_dir, _index_ref(prior_attempt), prior_index["index_hash"])):
        raise IndependentSkepticStageError("COUNTER_RESUME_INPUT_DRIFT")
    if (run_dir / f"invocation/skeptic/attempt-{attempt}").exists() or (run_dir / f".codex-runtime-skeptic-{attempt}").exists():
        raise IndependentSkepticStageError("COUNTER_ALREADY_LAUNCHED")
    attempt_root = run_dir / f"research/skeptic/attempts/{attempt}"
    if any((attempt_root / name).exists() for name in ("execution-proof.json", "pre-decision-research-package.json")):
        raise IndependentSkepticStageError("COUNTER_ALREADY_LAUNCHED")
    old_tasks = {task["security_id"]: task for task in prior_index["tasks"]}
    entries = {entry["security_id"]: entry for entry in prior["counter_theses"]}
    if (len(index["tasks"]) != len(old_tasks)
            or {task["security_id"] for task in index["tasks"]} != set(old_tasks)):
        raise IndependentSkepticStageError("COUNTER_DISPATCH_COVERAGE_INVALID")
    retry = []
    for task in index["tasks"]:
        old = old_tasks[task["security_id"]]
        entry = entries[task["security_id"]]
        retained = entry["status"] in {"COMPLETE", "LOW_CONFIDENCE"} and entry["validation_status"] == "PASSED"
        if retained:
            if task != old:
                raise IndependentSkepticStageError("COUNTER_RESUME_SUCCESS_CHANGED")
            continue
        if task.get("attempt") != attempt:
            raise IndependentSkepticStageError("COUNTER_RESUME_RETRY_MISSING")
        if any((run_dir / task[key]).exists() for key in ("report_ref", "markdown_ref")):
            raise IndependentSkepticStageError("COUNTER_ALREADY_LAUNCHED")
        packet = build_skeptic_dispatch_packet(repository_root, run_dir, task["task_name"], index_ref=index_ref)
        old_input = _read(_resolve_artifact(run_dir, old["input_ref"]))
        if (packet["agent_input"] != {**old_input, "attempt_id": attempt}
                or task["allowed_evidence_ids"] != old["allowed_evidence_ids"]
                or packet["invocation"]["model"] != _read(_resolve_artifact(run_dir, old["invocation_ref"]))["model"]):
            raise IndependentSkepticStageError("COUNTER_RESUME_INPUT_DRIFT")
        retry.append(task["task_name"])
    if not retry or len(retry) != len(set(retry)):
        raise IndependentSkepticStageError("COUNTER_RETRY_TASK_SET_INVALID")
    return {"status": "PREPARED", "run_id": forward["run_id"], "attempt": attempt,
            "dispatch_index": index_ref, "retry_task_names": retry}


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
    if task.get("semantic_output_version") == SPECIALIST_SEMANTIC_DRAFT:
        if (packet.get("invocation") != _read(run_dir / task["invocation_ref"])
                or packet.get("agent_input") != _read(run_dir / task["input_ref"])
                or packet.get("task_prompt") != (run_dir / task["prompt_ref"]).read_text(encoding="utf-8")
                or packet.get("identity") != {
                    "run_id": index["run_id"], "task_name": task_name,
                    "agent": "runtime_skeptic", "invocation_id": task["invocation_id"],
                    "security_id": task["security_id"],
                }):
            raise IndependentSkepticStageError("COUNTER_PACKET_CONTEXT_BINDING_INVALID")
        formal_schema = _read(run_dir / task["schema_ref"])
        if packet.get("output_schema") != _skeptic_semantic_schema(formal_schema, packet["invocation"]):
            raise IndependentSkepticStageError("COUNTER_SEMANTIC_SCHEMA_BINDING_INVALID")
    if task.get("reference_transport_version") == REFERENCE_TRANSPORT_VERSION:
        if task.get("semantic_output_version") != SPECIALIST_SEMANTIC_DRAFT:
            raise IndependentSkepticStageError("COUNTER_REFERENCE_PROTOCOL_BINDING_INVALID")
        expected = _skeptic_packet(
            run_dir, identity=packet["identity"], agent_input=_read(run_dir / task["input_ref"]),
            invocation=_read(run_dir / task["invocation_ref"]),
            prompt=(run_dir / task["prompt_ref"]).read_text(encoding="utf-8"),
            schema=_read(run_dir / task["schema_ref"]),
        )
        if packet != expected:
            raise IndependentSkepticStageError("COUNTER_REFERENCE_MAP_BINDING_INVALID")
    elif packet.get("reference_map") is not None or packet.get("reference_transport_version") is not None:
        raise IndependentSkepticStageError("COUNTER_REFERENCE_PROTOCOL_BINDING_INVALID")
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

    from product.runtime.invocation import envelope_specialist_semantic_draft
    from product.runtime.schema_validation import validate_schema_instance
    from product.runtime.validation import validate_skeptic_report

    run_dir = Path(run_dir).resolve()
    packet = build_skeptic_dispatch_packet(repository_root, run_dir, task_name, index_ref=index_ref)
    index = read_dispatch_index(run_dir, index_ref)
    task = next(item for item in index["tasks"] if item["task_name"] == task_name)
    invocation = packet["invocation"]
    if task.get("semantic_output_version") != SPECIALIST_SEMANTIC_DRAFT:
        raise IndependentSkepticStageError("COUNTER_LEGACY_OUTPUT_WRITE_RETIRED")
    if task.get("reference_transport_version") != REFERENCE_TRANSPORT_VERSION:
        raise IndependentSkepticStageError("COUNTER_LEGACY_REFERENCE_WRITE_RETIRED")
    if model != invocation["model"]:
        raise IndependentSkepticStageError("COUNTER_OUTPUT_MODEL_INVALID")
    try:
        raw = json.loads(raw_message)
    except json.JSONDecodeError as exc:
        raise IndependentSkepticStageError("COUNTER_OUTPUT_JSON_INVALID") from exc
    if not isinstance(raw, dict):
        raise IndependentSkepticStageError("COUNTER_OUTPUT_NOT_OBJECT")
    validate_schema_instance(raw, skeptic_model_packet(packet)["output_schema"])
    raw = translate_references(raw, packet["reference_map"])
    formal_schema = _read(run_dir / task["schema_ref"])
    report = envelope_specialist_semantic_draft(raw, invocation, model=model, formal_schema=formal_schema)
    if (report.get("schema_version") != "counter-thesis-report/2.1.0"
            or report.get("artifact_refs") != []
            or task["security_id"] not in str(report.get("scope", ""))):
        raise IndependentSkepticStageError("COUNTER_OUTPUT_SCOPE_INVALID")
    validate_schema_instance(report, formal_schema)
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
        "reference_map_hash": packet["reference_map"]["map_hash"],
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
    path = _resolve_artifact(run_dir, relative)
    return {"artifact_ref": relative, "file_hash": file_hash(path), "content_hash": content_hash}


def _forbidden_downstream_artifacts(run_dir: Path) -> None:
    forbidden = (
        "decision.json", "risk.json", "agents/runtime_cio.json", "outcome.json",
        "research/cio", "research/risk", "evaluation", "replay",
    )
    if any((run_dir / name).exists() for name in forbidden):
        raise IndependentSkepticStageError("COUNTER_DOWNSTREAM_ARTIFACT_FORBIDDEN")


def validate_predecision_package(
    repository_root: Path, run_dir: Path, package: Mapping[str, Any], *,
    for_execution: bool = True, artifact_schema: Mapping[str, Any] | None = None,
) -> None:
    """仅重验绑定与引用；不从原报告归纳共识或动作。"""

    from product.runtime.schema_validation import validate_schema_instance
    from product.runtime.validation import validate_skeptic_report

    run_dir = Path(run_dir).resolve()
    if for_execution and artifact_schema is not None:
        raise IndependentSkepticStageError("COUNTER_EXECUTION_SCHEMA_OVERRIDE_FORBIDDEN")
    schema_name = "pre-decision-research-package-v2.schema.json" if is_single_stock(package) else "pre-decision-research-package.schema.json"
    expected_version = "pre-decision-research-package/2.0.0" if is_single_stock(package) else "pre-decision-research-package/1.0.0"
    schema = artifact_schema if artifact_schema is not None else _read(Path(repository_root) / "product/schemas/runtime" / schema_name)
    if (package.get("schema_version") != expected_version
            or schema.get("$id") != expected_version):
        raise IndependentSkepticStageError("COUNTER_ARTIFACT_SCHEMA_UNSUPPORTED_VERSION")
    validate_schema_instance(package, schema, schema_resources=None if for_execution else {})
    try:
        verify_legacy_envelope_hash(package, hash_field="package_hash", location="product/runtime/independent_skeptic_stage.py:package.package_hash")
    except HashContractError as exc:
        raise IndependentSkepticStageError(f"COUNTER_PACKAGE_HASH_MISMATCH:{exc}") from exc
    manifest = _read(_resolve_artifact(run_dir, "run_manifest.json"))
    handoff = load_research_input(run_dir, manifest=manifest)
    request = _read(_resolve_artifact(run_dir, "council-request.json"))
    gate = _read(_resolve_artifact(run_dir, "evidence/gate.json"))
    bundle = _read(_resolve_artifact(run_dir, "research/holding-research-bundle.json"))
    if (package["run_id"] != manifest["run_id"]
            or package["run_id"] != bundle["run_id"]
            or any(package.get(k) != v for k, v in research_input_binding(handoff).items())
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
            gate=gate, index_ref=index_ref, for_execution=for_execution,
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
        prior = _read(_resolve_artifact(run_dir, prior_ref))
        if previous_record != _artifact_record(run_dir, prior_ref, prior["package_hash"]):
            raise IndependentSkepticStageError("COUNTER_RESUME_CHAIN_DRIFT")
        validate_predecision_package(repository_root, run_dir, prior,
                                     for_execution=for_execution and not is_single_stock(package),
                                     artifact_schema=artifact_schema)
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
    proof_path = _resolve_artifact(run_dir, proof_ref)
    proof = _read(proof_path)
    if (proof.get("proof_hash") != legacy_envelope_hash(proof, hash_field="proof_hash")
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
        report = _read(_resolve_artifact(run_dir, report_ref))
        invocation = _read(_resolve_artifact(run_dir, task["invocation_ref"]))
        output_schema = _read(Path(str(invocation["output_schema"])) if for_execution
                              else _resolve_artifact(run_dir, task["schema_ref"]))
        validate_schema_instance(report, output_schema, schema_resources=None if for_execution else {})
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
    positions = {item["security_id"]: item for item in research_subjects(handoff)}
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
        _resolve_artifact(run_dir, relative)
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
    handoff = load_research_input(run_dir)
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
                   and item.get("adapter_version") == SKEPTIC_ADAPTER_VERSION
                   and isinstance(item.get("input_hash"), str)
                   and len(item["input_hash"]) == 64
                   and isinstance(item.get("output_hash"), str)
                   and len(item["output_hash"]) == 64
                   and item.get("event_hash") == legacy_envelope_hash(item, hash_field="event_hash")]
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
    proof["proof_hash"] = legacy_envelope_hash(proof, hash_field="proof_hash")
    proof_ref = (
        "research/skeptic/execution-proof.json" if attempt == 1
        else f"research/skeptic/attempts/{attempt}/execution-proof.json"
    )
    _write(run_dir / proof_ref, proof)
    by_security = {item["security_id"]: item for item in entries}
    coverage = []
    for position in research_subjects(handoff):
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
        "schema_version": "pre-decision-research-package/2.0.0" if is_single_stock(handoff) else "pre-decision-research-package/1.0.0",
        "package_id": f"pre-decision:{forward['run_id']}", "run_id": forward["run_id"],
        **research_input_binding(handoff),
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
    package["package_hash"] = legacy_envelope_hash(package, hash_field="package_hash")
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


def read_skeptic_task_state(run_dir: Path, *, index_ref: str) -> dict[str, Any]:
    """Only this new Skeptic attempt's trusted lifecycle, never forward content or a verdict."""
    root = Path(run_dir).resolve()
    index = read_dispatch_index(root, index_ref)
    manifest = _read(root / "run_manifest.json")
    if (not is_single_stock(manifest) or manifest.get("stage") != STAGE
            or manifest.get("run_id") != index["run_id"]
            or manifest.get("manifest_hash") != legacy_envelope_hash(manifest, hash_field="manifest_hash")):
        raise IndependentSkepticStageError("COUNTER_TASK_STATE_NOT_AUTHORIZED")
    tasks = index["tasks"]
    packets = {task["task_name"]: build_skeptic_dispatch_packet(Path(), root, task["task_name"], index_ref=index_ref)
               for task in tasks}
    if (len(packets) != len(tasks) or not tasks
            or any(p["invocation"].get("skeptic_delivery_version") != DELIVERY_VERSION for p in packets.values())):
        raise IndependentSkepticStageError("COUNTER_TASK_STATE_NOT_AUTHORIZED")
    base = "invocation/skeptic" + (f"/attempt-{index['attempt']}" if index.get("attempt", 1) > 1 else "")
    paths = [root / base / name for name in ("subagent-dispatches.jsonl", "subagent-events.jsonl")]
    with ExitStack() as stack:
        for path in paths:  # The same dispatch -> event order as the existing Hooks.
            lock = path.with_suffix(path.suffix + ".lock")
            if lock.exists():
                _resolve_artifact(root, str(lock.relative_to(root)))
                handle = stack.enter_context(lock.open("r", encoding="utf-8"))
                fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            elif path.exists():
                raise IndependentSkepticStageError("COUNTER_TASK_STATE_LOG_UNBOUND")
        rows = []
        for path in paths:
            if path.exists():
                _resolve_artifact(root, str(path.relative_to(root)))
            rows.append(_read_jsonl(path))
        dispatches, events = rows
    if any(row.get("event_hash") != legacy_envelope_hash(row, hash_field="event_hash")
           for row in [*dispatches, *events]):
        raise IndependentSkepticStageError("COUNTER_TASK_STATE_LOG_DRIFT")
    allowed = [d for d in dispatches if d.get("decision") == "ALLOW"]
    if (len({d.get("parent_session_id") for d in allowed}) > 1
            or len({d.get("task_name") for d in allowed}) != len(allowed)
            or any(d.get("task_name") not in packets or not d.get("parent_session_id") for d in allowed)):
        raise IndependentSkepticStageError("COUNTER_TASK_STATE_BINDING_INVALID")
    states, bound_children = [], set()
    for task in tasks:
        name = task["task_name"]
        state = {"task_name": name, "execution_status": "PENDING", "outcome": None, "research_status": None}
        dispatch = next((d for d in allowed if d["task_name"] == name), None)
        starts = [e for e in events if e.get("hook_event_name") == "SubagentStart"
                  and e.get("context_binding", {}).get("task_name") == name]
        if (starts and dispatch is None) or len(starts) > 1:
            raise IndependentSkepticStageError("COUNTER_TASK_STATE_BINDING_INVALID")
        if dispatch:
            state["execution_status"] = "RUNNING"
            if (dispatch.get("agent_type") != "runtime_skeptic" or dispatch.get("fork_turns") != "none"
                    or dispatch.get("dispatch_binding", {}).get("matched") is not True
                    or dispatch.get("dispatch_binding", {}).get("packet_hash") != canonical_hash(packets[name])):
                raise IndependentSkepticStageError("COUNTER_TASK_STATE_BINDING_INVALID")
        if starts:
            start = starts[0]
            binding = start["context_binding"]
            if (binding.get("status") != "DELIVERED" or binding.get("packet_hash") != canonical_hash(packets[name])
                    or binding.get("invocation_id") != task["invocation_id"] or binding.get("run_id") != index["run_id"]
                    or start.get("parent_session_id") != dispatch["parent_session_id"]
                    or start.get("agent_type") != "runtime_skeptic" or not start.get("child_session_id")
                    or start.get("model") != packets[name]["invocation"]["model"]):
                raise IndependentSkepticStageError("COUNTER_TASK_STATE_BINDING_INVALID")
            bound_children.add(start["child_session_id"])
            stops = [e for e in events if e.get("hook_event_name") in {"SubagentStop", "SubagentStopBlocked"}
                     and e.get("trusted_task_binding", {}).get("task_name") == name]
            terminal = []
            for stop in stops:
                expected = {"task_name": name, "task_id": task["task_id"], "run_id": index["run_id"],
                            "invocation_id": task["invocation_id"], "agent": "runtime_skeptic"}
                if (stop.get("trusted_task_binding") != expected or stop.get("parent_session_id") != start["parent_session_id"]
                        or stop.get("identity_binding", {}).get("status") != "BOUND"
                        or stop.get("child_session_id") != start["child_session_id"]
                        or stop.get("agent_type") != start["agent_type"] or stop.get("model") != start["model"]):
                    raise IndependentSkepticStageError("COUNTER_TASK_STATE_BINDING_INVALID")
                capture = stop.get("output_capture", {})
                if capture.get("repair_state") != "REPAIR_REQUESTED" and stop.get("hook_decision") != "BLOCK" and capture.get("status") in {"SAVED", "FAILED"}:
                    terminal.append(stop)
            if len(terminal) > 1:
                raise IndependentSkepticStageError("COUNTER_TASK_STATE_BINDING_INVALID")
            if terminal:
                capture = terminal[0]["output_capture"]
                state.update(execution_status="TERMINAL", outcome=capture["status"])
                if capture["status"] == "SAVED":
                    if capture.get("path") != task["report_ref"]:
                        raise IndependentSkepticStageError("COUNTER_TASK_STATE_BINDING_INVALID")
                    report = _read(_resolve_artifact(root, task["report_ref"]))
                    if (canonical_hash(report) != capture.get("output_hash") or report.get("run_id") != index["run_id"]
                            or report.get("invocation_id") != task["invocation_id"]):
                        raise IndependentSkepticStageError("COUNTER_TASK_STATE_REPORT_DRIFT")
                    state["research_status"] = report["status"]
        states.append(state)
    if any(e.get("hook_event_name") not in {"SubagentStart", "SubagentStop", "SubagentStopBlocked"}
           or e.get("child_session_id") not in bound_children
           or (e.get("context_binding", {}) if e.get("hook_event_name") == "SubagentStart"
               else e.get("trusted_task_binding", {})).get("task_name") not in packets for e in events):
        raise IndependentSkepticStageError("COUNTER_TASK_STATE_BINDING_INVALID")
    return {"schema_version": "independent-skeptic-task-state/1.0.0", "run_id": index["run_id"],
            "index_hash": index["index_hash"], "tasks": states, "expected": len(states),
            "terminal_count": sum(s["execution_status"] == "TERMINAL" for s in states),
            "all_tasks_terminal": all(s["execution_status"] == "TERMINAL" for s in states),
            "content_acceptance": "NOT_EVALUATED"}


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
    state_guidance = ""
    if all(_read(Path(run_dir) / task["invocation_ref"]).get("skeptic_delivery_version") == DELIVERY_VERSION
           for task in index["tasks"] if task["task_name"] in selected):
        state_guidance = ("\n本新尝试可用fixture_runtime.research_task_state只读核对本阶段可信任务状态。"
                          "等待前、每次wait返回后核对；all_tasks_terminal=true时结束执行归集，不再空等通知。"
                          "SAVED/TERMINAL不是研究通过；不足或失败不重派，交原finalizer判PARTIAL/FAILED。\n")
    return f"""你是独立反证阶段的宿主调度主线程，不是 CIO，也不产生研究结论。运行 ID：{index['run_id']}。

仅按以下映射使用 collaboration spawn_agent；每项必须传 agent_type=runtime_skeptic、对应 task_name、给定 message、fork_turns=none。不得把正向报告、bundle、未解决问题或报告 hash 放入 message；逐股冻结包由 Hook 交付。最多同时保持 {index['target_concurrency']} 个活跃 Agent；先填满槽位，结束一个后补位。只使用 wait_agent 等待所有任务真实终态；不得派发 CIO、Market Catalyst、Company Analyst 或 Risk，不得自行修改报告或查询包外资料。

{state_guidance}
任务映射：{json.dumps(mapping, ensure_ascii=False, sort_keys=True)}

全部任务形成终态后，只返回 JSON：{{"stage":"{STAGE}","run_id":"{index['run_id']}","dispatched":{len(mapping)},"completed":{len(mapping)}}}。completed 只表示子任务结束；报告合法性和交接状态由确定性 finalizer 决定。"""


def launch_skeptic_phase(
    repository_root: Path, *, run_dir: Path, codex_binary: str = "codex",
    timeout_seconds: int = 2400, index_ref: str | None = None,
    task_names: Sequence[str] | None = None,
) -> tuple[dict[str, Any], int]:
    """仅供宿主 launcher 调用一次；不运行 CIO、Risk 或任何决策层。"""

    from product.runtime.nested_codex import (
        build_verified_nested_codex_command, fixture_mcp_runtime_environment, integrity_snapshot,
    )

    repository_root = Path(repository_root).resolve()
    run_dir = Path(run_dir).resolve()
    manifest = _read(run_dir / "run_manifest.json")
    if (manifest.get("stage") != STAGE or manifest.get("complete_portfolio_decision") is not False
            or Path(str(manifest.get("output_dir", ""))).resolve() != run_dir):
        raise IndependentSkepticStageError("COUNTER_RUN_MANIFEST_INVALID")
    validate_forward_gate(repository_root, run_dir)
    index = read_dispatch_index(run_dir, index_ref)
    if index.get("semantic_output_version") != SPECIALIST_SEMANTIC_DRAFT:
        raise IndependentSkepticStageError("COUNTER_LEGACY_EXECUTION_RETIRED")
    if index.get("reference_transport_version") != REFERENCE_TRANSPORT_VERSION:
        raise IndependentSkepticStageError("COUNTER_LEGACY_REFERENCE_EXECUTION_RETIRED")
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
    command = build_verified_nested_codex_command(
        runtime_binding_path=invocation_dir / "codex-runtime.json",
        codex_binary=codex_binary, product_root=repository_root / "product",
        run_dir=run_dir, model=manifest["parent_model"],
        sqlite_home=sqlite_home, log_dir=log_dir,
        final_message_path=tmp_dir / "final-message.json",
        hook_recorder_path=repository_root / "product/runtime/codex_hook_recorder.py",
        output_schema_path=schema_path, fixture_mcp_run_dir=run_dir,
        fixture_mcp_skeptic_dispatch_index=INITIAL_INDEX_REF if index_ref is None else index_ref,
        hook_agent_matcher="^runtime_skeptic$",
    )
    if is_single_stock(manifest):
        # 与单股Company/正向宿主一致：隔离桌面字段，明确加载原Skeptic。
        command.insert(command.index("exec") + 1, "--ignore-user-config")
        product = repository_root / "product"
        agents = tomllib.loads((product / ".codex/config.toml").read_text())["agents"]
        agent = agents["runtime_skeptic"]
        config_path = (product / ".codex" / agent["config_file"]).resolve()
        if not config_path.is_relative_to(product / ".codex") or not config_path.is_file():
            raise IndependentSkepticStageError("COUNTER_AGENT_CONFIG_INVALID")
        command.extend(("-c", "agents.runtime_skeptic={"
            f"description={json.dumps(agent['description'], ensure_ascii=False)},"
            f"config_file={json.dumps(str(config_path))}}}",
            "-c", f"agents.max_threads={agents['max_threads']}"))
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
