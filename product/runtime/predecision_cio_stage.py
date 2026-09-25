"""Prepare an isolated CIO run from a validated forward/counter research package.

This module does not start a model or convert missing portfolio facts into advice.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.independent_skeptic_stage import (
    validate_forward_gate,
    validate_predecision_package,
)
from product.runtime.model_routing import agent_development_test_model, select_product_runtime_model
from product.runtime.schema_validation import validate_schema_instance


STAGE = "PREDECISION_CIO_SYNTHESIS"
RESEARCH_TARGET = "US:COMMON_STOCK:MRVL"
REQUEST_VERSION = "predecision-cio-request/1.0.0"
MANIFEST_VERSION = "predecision-cio-manifest/1.0.0"
LOCKED_RESOURCES = (
    "product/AGENTS.md", "product/skills/portfolio-council/SKILL.md",
    "product/.codex/agents/runtime_cio.toml", "product/version-manifest.json",
    "product/schemas/runtime/predecision-cio-request.schema.json",
    "product/schemas/runtime/predecision-cio-synthesis.schema.json",
    "product/runtime/predecision_cio_stage.py", "product/runtime/fixture_mcp.py",
    "product/runtime/nested_codex.py", "product/runtime/codex_hook_recorder.py",
)


class PredecisionCioStageError(ValueError):
    """A source, context, or output invariant is not satisfied."""


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PredecisionCioStageError(f"CIO_INPUT_INVALID:{path.name}") from exc
    if not isinstance(value, dict):
        raise PredecisionCioStageError(f"CIO_INPUT_INVALID:{path.name}")
    return value


def _resolve_ref(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise PredecisionCioStageError("CIO_SOURCE_REF_INVALID")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise PredecisionCioStageError(f"CIO_SOURCE_REF_INVALID:{relative}")
    return path


def _latest_package_ref(source_run: Path) -> str:
    root = source_run / "research/skeptic"
    refs = ["research/skeptic/pre-decision-research-package.json"]
    attempts = root / "attempts"
    if attempts.is_dir():
        for child in attempts.iterdir():
            if child.is_dir() and child.name.isdecimal() and int(child.name) >= 2:
                refs.append(f"research/skeptic/attempts/{child.name}/pre-decision-research-package.json")
    available = [ref for ref in refs if (source_run / ref).is_file()]
    if not available:
        raise PredecisionCioStageError("CIO_SOURCE_PACKAGE_MISSING")
    return available[-1] if len(available) == 1 else max(
        available, key=lambda ref: int(ref.split("/")[3]) if "/attempts/" in ref else 1
    )


def _parse_time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise PredecisionCioStageError(f"CIO_TIME_INVALID:{field}") from exc
    if parsed.tzinfo is None:
        raise PredecisionCioStageError(f"CIO_TIME_INVALID:{field}")
    return parsed.astimezone(timezone.utc)


def _report_catalog(source_run: Path, bundle: Mapping[str, Any],
                    package: Mapping[str, Any]) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ref in bundle["report_refs"]:
        relative = ref["artifact_ref"]
        report = _read(_resolve_ref(source_run, relative))
        report_id = ref["report_id"]
        if report_id in seen:
            raise PredecisionCioStageError("CIO_REPORT_ID_DUPLICATE")
        seen.add(report_id)
        catalog.append({
            "report_id": report_id, "role": ref["capability"],
            "security_ids": ref["security_ids"],
            "invocation_id": report.get("invocation_id"),
            "artifact_ref": relative, "content_hash": ref["report_hash"],
            "file_hash": file_hash(source_run / relative),
            "claim_ids": sorted({item["claim_id"] for item in report.get("claims", [])
                                 if isinstance(item, Mapping) and isinstance(item.get("claim_id"), str)}),
            "challenge_ids": [],
        })
    for entry in package["counter_theses"]:
        report_ref = entry["report"]
        if report_ref is None:
            raise PredecisionCioStageError("CIO_COUNTER_REPORT_MISSING")
        relative = report_ref["artifact_ref"]
        report = _read(_resolve_ref(source_run, relative))
        report_id = f"skeptic:{entry['security_id']}:{entry['invocation_id']}"
        if report_id in seen:
            raise PredecisionCioStageError("CIO_REPORT_ID_DUPLICATE")
        seen.add(report_id)
        catalog.append({
            "report_id": report_id, "role": "INDEPENDENT_SKEPTIC",
            "security_ids": [entry["security_id"]],
            "invocation_id": entry["invocation_id"],
            "artifact_ref": relative, "content_hash": report_ref["content_hash"],
            "file_hash": file_hash(source_run / relative),
            "claim_ids": [],
            "challenge_ids": sorted({item["challenge_id"] for item in report.get("challenges", [])
                                     if isinstance(item, Mapping) and isinstance(item.get("challenge_id"), str)}),
        })
    return catalog


def validate_predecision_cio_run(repository_root: Path, run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Reject post-prepare drift before a model or finalizer consumes the run."""

    root = Path(run_dir).resolve()
    manifest = _read(root / "run_manifest.json")
    request = _read(root / "predecision-cio-request.json")
    if manifest.get("manifest_hash") != canonical_hash({
        key: value for key, value in manifest.items() if key != "manifest_hash"
    }):
        raise PredecisionCioStageError("CIO_MANIFEST_DRIFT")
    if request.get("request_hash") != canonical_hash({
        key: value for key, value in request.items() if key != "request_hash"
    }):
        raise PredecisionCioStageError("CIO_REQUEST_DRIFT")
    if request.get("requested_level") == "PORTFOLIO_ADVICE" or request.get("actual_level") == "PORTFOLIO_ADVICE":
        raise PredecisionCioStageError("CIO_PORTFOLIO_ADVICE_NOT_AVAILABLE")
    if request.get("target_security_id") != RESEARCH_TARGET:
        raise PredecisionCioStageError("CIO_RESEARCH_TARGET_NOT_IN_SCOPE")
    schema = _read(Path(repository_root).resolve() / "product/schemas/runtime/predecision-cio-request.schema.json")
    validate_schema_instance(request, schema)
    if (manifest.get("stage") != STAGE or request["stage"] != STAGE
            or manifest.get("run_id") != request["run_id"]
            or manifest.get("request_hash") != request["request_hash"]
            or manifest.get("source_package_hash") != request["source_package_hash"]
            or Path(str(manifest.get("output_dir", ""))).resolve() != root):
        raise PredecisionCioStageError("CIO_RUN_BINDING_INVALID")
    repository_root = Path(repository_root).resolve()
    from product.runtime.discovery import discover_product_resources
    if manifest.get("product_discovery_hash") != discover_product_resources(repository_root).discovery_hash:
        raise PredecisionCioStageError("CIO_PRODUCT_DISCOVERY_DRIFT")
    expected_locks = {relative: file_hash(repository_root / relative) for relative in LOCKED_RESOURCES}
    if manifest.get("resource_locks") != expected_locks:
        raise PredecisionCioStageError("CIO_RUNTIME_RESOURCE_DRIFT")
    source = Path(str(manifest["source_run_dir"])).resolve()
    for item in manifest["frozen_inputs"]:
        relative = item["artifact_ref"]
        frozen = _resolve_ref(root / "source-inputs", relative)
        if file_hash(frozen) != item["file_hash"]:
            raise PredecisionCioStageError(f"CIO_FROZEN_INPUT_DRIFT:{relative}")
        if file_hash(_resolve_ref(source, relative)) != item["file_hash"]:
            raise PredecisionCioStageError(f"CIO_SOURCE_INPUT_DRIFT:{relative}")
    if (root / "mandate.json").exists():
        raise PredecisionCioStageError("CIO_UNEXPECTED_MANDATE")
    if (root / "risk-context.json").exists():
        raise PredecisionCioStageError("CIO_RESEARCH_RISK_CONTEXT_FORBIDDEN")
    catalog = _read(root / "report-catalog.json")
    if catalog.get("catalog_hash") != canonical_hash({"reports": catalog.get("reports")}) or catalog.get("reports") != manifest.get("report_catalog"):
        raise PredecisionCioStageError("CIO_REPORT_CATALOG_DRIFT")
    for item in catalog["reports"]:
        if file_hash(_resolve_ref(root / "source-inputs", item["artifact_ref"])) != item["file_hash"]:
            raise PredecisionCioStageError("CIO_REPORT_DRIFT")
    source_gate = _read(root / "source-inputs/evidence/gate.json")
    stage_gate = _read(root / "evidence/gate.json")
    expected_gate = {**source_gate, "run_id": request["run_id"]}
    expected_gate["bundle_hash"] = canonical_hash({
        key: value for key, value in expected_gate.items() if key != "bundle_hash"
    })
    if (stage_gate != expected_gate or source_gate.get("bundle_hash") != request["gate_hash"]):
        raise PredecisionCioStageError("CIO_FROZEN_GATE_DRIFT")
    invocation = _read(root / "invocations/runtime_cio.json")
    if (invocation.get("invocation_hash") != canonical_hash({
            key: value for key, value in invocation.items() if key != "invocation_hash"
        }) or invocation.get("run_id") != request["run_id"]
            or invocation.get("source_gate_hash") != request["gate_hash"]
            or invocation.get("gate_hash") != stage_gate["bundle_hash"]
            or invocation.get("allowed_evidence_ids") != stage_gate["allowed_evidence_ids"]
            or invocation.get("tool_permissions") != ["fixture_evidence.query"]):
        raise PredecisionCioStageError("CIO_INVOCATION_DRIFT")
    return manifest, request


def _report_identity(catalog_item: Mapping[str, Any]) -> dict[str, Any]:
    return {key: catalog_item[key] for key in (
        "report_id", "role", "security_ids", "invocation_id", "content_hash"
    )}


_STAGE_SECTION_START = "<!-- PREDECISION_CIO_INSTRUCTIONS_START -->"
_STAGE_SECTION_END = "<!-- PREDECISION_CIO_INSTRUCTIONS_END -->"


def _stage_instruction_section(text: str, source: str) -> str:
    """Extract one explicitly bounded section; never fall back to a full file."""

    if text.count(_STAGE_SECTION_START) != 1 or text.count(_STAGE_SECTION_END) != 1:
        raise PredecisionCioStageError(f"CIO_INSTRUCTION_SECTION_INVALID:{source}:MARKERS")
    start = text.index(_STAGE_SECTION_START) + len(_STAGE_SECTION_START)
    end = text.index(_STAGE_SECTION_END)
    if start >= end or not text[start:end].strip():
        raise PredecisionCioStageError(f"CIO_INSTRUCTION_SECTION_INVALID:{source}:CONTENT")
    return text[start:end].strip()


def _stage_instruction_bundle(product_root: Path) -> str:
    sections = (
        ("AGENTS.md", "locked_product_instructions"),
        ("skills/portfolio-council/SKILL.md", "locked_portfolio_council_skill"),
        (".codex/agents/runtime_cio.toml", "locked_runtime_cio_protocol"),
    )
    parts: list[str] = []
    for relative, label in sections:
        try:
            source_text = (product_root / relative).read_text(encoding="utf-8")
        except OSError as exc:
            raise PredecisionCioStageError(
                f"CIO_INSTRUCTION_SECTION_INVALID:{relative}:READ"
            ) from exc
        section = _stage_instruction_section(source_text, relative)
        parts.append(f"<{label}>\n{section}\n</{label}>")
    return "\n".join(parts)


def build_predecision_cio_prompt(repository_root: Path, run_dir: Path) -> str:
    """Give the main-thread CIO complete verified reports, without re-dispatching analysts."""

    _, request = validate_predecision_cio_run(repository_root, run_dir)
    root = Path(run_dir).resolve()
    product_root = Path(repository_root).resolve() / "product"
    stage_instructions = _stage_instruction_bundle(product_root)
    catalog = _read(root / "report-catalog.json")["reports"]
    reports = [{"identity": _report_identity(item), "report": _read(
        root / "source-inputs" / item["artifact_ref"]
    )} for item in catalog]
    context = {
        "request": request,
        "coverage": _read(root / "source-inputs" / request["source_package_ref"])["coverage"],
        "forward_coverage": _read(root / "source-inputs/research/holding-research-bundle.json")["coverage"],
        "reports": reports,
        "expected_consumed_reports": [_report_identity(item) for item in catalog],
    }
    return (
        "你是本次 PREDECISION_CIO_SYNTHESIS 的 Codex 主线程 CIO；用户已明确要求本阶段综合。"
        "前序正向研究和独立反证均已由来源运行完成、验证和冻结。只进行一次 CIO 综合，"
        "不得再次派发 Company Analyst、Market Catalyst、Skeptic 或其他 Agent，"
        "不得联网、读取原始缓存、券商资料、其他运行或修改产品文件。\n"
        "以下 JSON 内的 report 是通过来源哈希和执行证明重验的完整原始报告，"
        "identity 是唯一报告身份。必须实际综合而不是投票或机械复述，"
        "consumed_reports 原样复制 expected_consumed_reports。"
        "对重要 Skeptic challenge_id 给出接受/部分接受/驳回/未决及判断影响。"
        "报告应回答：综合判断与分析期限、关键事实如何支持判断、正反分歧取舍、"
        "Macro/Market 对目标证券的具体传导、可观察推翻条件、优先观察及重评事件。"
        "分别陈述业务前景、价格吸引力、账户适配；无证据时明确未知，不编目标价或数字阈值。"
        "用户持有期限未知时把分析期限标为分析假设。account_fit 必须写固定值“当前账户适配未评估”。"
        "只写中文，保留字段英文。\n"
        "每条 key_facts 必须是可由其 evidence_refs 支持的原子事实；若一句话比较两个科目，"
        "必须查询并引用两个科目各自的 Evidence ID，否则删去未闭合的比较。"
        "将上游 INTERPRETATION 与已披露 FACT 分开；来源标记的 MD&A 文本冲突未消解时，"
        "不得把数据中心需求已直接推动利润或增长的因果关系写成已验证事实，"
        "只能在明确限定下写为待验证的推断。"
        "Market 传导不能只写通用风险偏好；若冻结 Market/Technical 报告含可验证窗口，"
        "结合其具体市场状态、MRVL 对基准的相对表现及相反窗口解释为何能或不能传导，"
        "并保留缺少 beta、宽度或信用资料的边界。\n"
        f"所有最终输出中的 Evidence ID（包括 key_facts 和顶层 evidence_refs）都必须先通过"
        f" fixture_runtime.query 实际查询；可一次批量查询，不能只查一个却引用多个。"
        f"调用时仅可使用 run_id={request['run_id']}、"
        f"agent=runtime_cio、invocation_id=cio:{request['run_id']}，evidence_ids 必须取自原报告引用，"
        "且被冻结 Gate 允许。引用未查询的 ID 会使整个结果失败；不得查询 Gate 外事实。"
        "输出仅为符合给定 JSON Schema 的 JSON 对象，不写 Markdown 或解释。\n"
        "以下为本次锁定并交付的阶段适用产品指令、Skill 与 CIO 协议。\n"
        + stage_instructions + "\n"
        "<validated_research_context>\n"
        + json.dumps(context, ensure_ascii=False, sort_keys=True)
        + "\n</validated_research_context>"
    )


def _output_schema(repository_root: Path, request: Mapping[str, Any],
                   catalog: list[dict[str, Any]], *, run_dir: Path) -> dict[str, Any]:
    schema = _read(Path(repository_root) / "product/schemas/runtime/predecision-cio-synthesis.schema.json")
    exact = {
        "run_id": request["run_id"], "invocation_id": f"cio:{request['run_id']}",
        "source_run_id": request["source_run_id"],
        "source_package_hash": request["source_package_hash"],
        "target_security_id": request["target_security_id"],
        "requested_level": request["requested_level"],
        "decision_cutoff": request["decision_cutoff"],
        "consumed_reports": [_report_identity(item) for item in catalog],
    }
    for key, value in exact.items():
        schema["properties"][key]["const"] = value
    report_ids = [item["report_id"] for item in catalog]
    for field in ("key_facts", "macro_market_transmission"):
        schema["properties"][field]["items"]["properties"]["report_ids"]["items"]["enum"] = report_ids
    challenge_report_ids = [item["report_id"] for item in catalog if item["challenge_ids"]]
    if challenge_report_ids:
        schema["properties"]["challenge_dispositions"]["items"]["properties"]["report_id"]["enum"] = challenge_report_ids
    return schema


def _decoding_schema(authoritative: Mapping[str, Any]) -> dict[str, Any]:
    """Project the finalizer contract onto Codex Structured Outputs' subset.

    Exact array/object identities and other unsupported JSON Schema keywords
    remain enforced by the authoritative finalizer after model completion.
    """

    schema = copy.deepcopy(authoritative)
    schema.pop("$schema", None)
    schema.pop("$id", None)

    def project(node: dict[str, Any]) -> None:
        node.pop("uniqueItems", None)
        if "const" in node:
            value = node.pop("const")
            if not isinstance(value, (list, dict)):
                if "type" not in node:
                    node["type"] = ("boolean" if isinstance(value, bool) else
                                    "number" if isinstance(value, (int, float)) else "string")
                node["enum"] = [value]
        elif "enum" in node and "type" not in node:
            node["type"] = "string"
        for child in node.get("properties", {}).values():
            project(child)
        if isinstance(node.get("items"), dict):
            project(node["items"])

    project(schema)
    return schema


def _mcp_query_ids(run_dir: Path, request: Mapping[str, Any]) -> tuple[set[str], int]:
    path = run_dir / "events/mcp/events.jsonl"
    if not path.is_file():
        raise PredecisionCioStageError("CIO_QUERY_PROOF_MISSING")
    ids: set[str] = set()
    count = 0
    for ordinal, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PredecisionCioStageError(f"CIO_QUERY_EVENT_INVALID:{ordinal}") from exc
        if not isinstance(event, dict):
            raise PredecisionCioStageError(f"CIO_QUERY_EVENT_INVALID:{ordinal}")
        if (event.get("run_id") == request["run_id"]
                and event.get("agent") == "runtime_cio"
                and event.get("invocation_id") == f"cio:{request['run_id']}"
                and event.get("tool") == "fixture_evidence.query"):
            from product.mcp.provenance import content_hash
            if (event.get("event_hash") != content_hash({
                    key: value for key, value in event.items() if key != "event_hash"
                }) or event.get("access_mode") != "read"):
                raise PredecisionCioStageError("CIO_QUERY_EVENT_INTEGRITY_INVALID")
            event_ids = event.get("evidence_ids")
            if not isinstance(event_ids, list) or not event_ids:
                raise PredecisionCioStageError("CIO_QUERY_EVENT_EMPTY")
            ids.update(event_ids)
            count += 1
    if count < 1:
        raise PredecisionCioStageError("CIO_QUERY_PROOF_MISSING")
    return ids, count


def _model_execution_proof(repository_root: Path, root: Path,
                           request: Mapping[str, Any]) -> dict[str, Any]:
    """Bind final JSON to a completed parent Codex turn and locked invocation."""

    invocation = root / "invocation"
    environment = _read(invocation / "environment-manifest.json")
    command = environment.get("command")
    if not isinstance(command, list) or "--model" not in command:
        raise PredecisionCioStageError("CIO_MODEL_COMMAND_MISSING")
    model_index = command.index("--model")
    if ("--sandbox" not in command or command[command.index("--sandbox") + 1] != "workspace-write"
            or "-C" not in command or command[command.index("-C") + 1] != str(root)
            or "--skip-git-repo-check" not in command
            or "--dangerously-bypass-approvals-and-sandbox" in command):
        raise PredecisionCioStageError("CIO_SOURCE_READONLY_COMMAND_INVALID")
    for index, token in enumerate(command[:-1]):
        if token == "--add-dir":
            added = Path(command[index + 1]).resolve()
            if added == Path(repository_root).resolve() or added.is_relative_to(Path(repository_root).resolve()):
                raise PredecisionCioStageError("CIO_SOURCE_READONLY_COMMAND_INVALID")
    if (model_index + 1 >= len(command) or command[model_index + 1] != request["model"]
            or environment.get("run_id") != request["run_id"]
            or environment.get("model") != request["model"]
            or environment.get("prompt_hash") != file_hash(invocation / "prompt.txt")
            or environment.get("output_schema_hash") != file_hash(invocation / "cio-output.schema.json")):
        raise PredecisionCioStageError("CIO_MODEL_INVOCATION_DRIFT")
    if (environment.get("product_instructions_file_hash") != file_hash(
            Path(repository_root) / "product/AGENTS.md")
            or environment.get("skill_file_hash") != file_hash(
            Path(repository_root) / "product/skills/portfolio-council/SKILL.md")
            or environment.get("agent_file_hash") != file_hash(
                Path(repository_root) / "product/.codex/agents/runtime_cio.toml")
            or environment.get("stage_instructions_hash") != hashlib.sha256(
                _stage_instruction_bundle(Path(repository_root) / "product").encode("utf-8")
            ).hexdigest()
            or (invocation / "prompt.txt").read_text(encoding="utf-8")
            != build_predecision_cio_prompt(repository_root, root)):
        raise PredecisionCioStageError("CIO_LOCKED_INSTRUCTION_DELIVERY_INVALID")
    event_path = invocation / "codex-events.jsonl"
    try:
        events = [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, json.JSONDecodeError) as exc:
        raise PredecisionCioStageError("CIO_MODEL_EVENTS_INVALID") from exc
    if not events or events[-1].get("type") != "turn.completed" or not any(
        item.get("type") == "turn.started" for item in events
    ):
        raise PredecisionCioStageError("CIO_MODEL_TURN_NOT_COMPLETED")
    messages = [item.get("item", {}).get("text") for item in events
                if item.get("type") == "item.completed"
                and isinstance(item.get("item"), Mapping)
                and item["item"].get("type") == "agent_message"]
    final_text = (invocation / "final-message.json").read_text(encoding="utf-8")
    if not messages or not isinstance(messages[-1], str) or messages[-1].strip() != final_text.strip():
        raise PredecisionCioStageError("CIO_MODEL_FINAL_EVENT_MISMATCH")
    return {
        "model": request["model"], "event_file_hash": file_hash(event_path),
        "final_message_file_hash": file_hash(invocation / "final-message.json"),
        "environment_file_hash": file_hash(invocation / "environment-manifest.json"),
        "product_instructions_file_hash": environment["product_instructions_file_hash"],
        "skill_file_hash": environment["skill_file_hash"],
        "agent_file_hash": environment["agent_file_hash"],
        "stage_instructions_hash": environment["stage_instructions_hash"],
        "parent_turn_completed": True,
    }


def _host_generated_at(root: Path, request: Mapping[str, Any]) -> str:
    """Use the host finalizer clock, never an unverified model timestamp."""

    started = _parse_time(
        _read(root / "invocation/environment-manifest.json")["started_at"],
        "invocation.started_at",
    )
    completed = datetime.now(timezone.utc)
    if completed < started or completed < _parse_time(request["decision_cutoff"], "decision_cutoff"):
        raise PredecisionCioStageError("CIO_HOST_GENERATION_TIME_INVALID")
    return completed.isoformat().replace("+00:00", "Z")


def _render_research_synthesis(output: Mapping[str, Any], request: Mapping[str, Any]) -> str:
    def clause(value: str) -> str:
        return value.rstrip("。；")

    lines = [
        f"# {request['target_security_id']} 正反研究综合", "",
        f"- 研究截止点：`{request['decision_cutoff']}`",
        f"- 原请求：`{request['requested_level']}`；实际交付：`RESEARCH_SYNTHESIS`",
        f"- 生成时间：`{output['generated_at']}`",
        "- 完整组合决策：未完成；Risk：未运行；不包含交易动作或目标仓位。", "",
        "## 综合判断", "", output["judgment"], "",
        "## 分析期限及推理", "", output["analysis_horizon"], "", output["reasoning"], "",
        "## 正向与反向 Thesis", "",
        f"- 正向：{output['thesis']}", f"- 反向：{output['counter_thesis']}", "",
        "## 已形成共识", "",
        "\n".join(f"- {item}" for item in output["consensus"])
        if output["consensus"] else "暂无充分共识", "",
        "## 业务、价格与账户边界", "",
        f"- 业务前景：{output['business_outlook']}",
        f"- 价格吸引力：{output['price_attractiveness']}",
        f"- 账户适配：{output['account_fit']}", "",
        "## 关键事实与判断连接", "",
    ]
    for item in output["key_facts"]:
        lines.append(f"- {clause(item['fact'])}；推理：{clause(item['reasoning'])}；报告：{', '.join(item['report_ids'])}；证据：{', '.join(item['evidence_refs'])}")
    lines += ["", "## 重要反证与取舍", ""]
    for item in output["challenge_dispositions"]:
        lines.append(f"- `{item['challenge_id']}`（{item['disposition']}）：{clause(item['rationale'])}；影响：{clause(item['judgment_impact'])}；重评：{item['reevaluate_when']}")
    for item in output["conflicts"]:
        lines.append(f"- 尚存分歧：{item}")
    lines += ["", "## Macro / Market 传导", ""]
    for item in output["macro_market_transmission"]:
        lines.append(f"- {item['channel']}：{clause(item['mechanism'])}；判断：{clause(item['assessment'])}；限制：{item['limitations']}")
    lines += ["", "## 推翻与观察条件", ""]
    for item in output["invalidation_conditions"]:
        lines.append(f"- 失效：{item}")
    for item in output["watch_plan"]:
        lines.append(f"- 观察 {item['item']}；触发：{clause(item['trigger'])}；重评：{item['reassess_on']}")
    for item in output["reevaluation_conditions"]:
        lines.append(f"- 重评条件：{item}")
    lines += ["", "## 限制与待补", ""]
    for item in output["limitations"]:
        lines.append(f"- {item}")
    lines.append("- 用户在需求讨论中表示曾清仓 MRVL，系统未独立核验当前账户；本报告仅综合来源研究截止点，未评估当前账户适配。")
    lines += ["", f"置信度理由：{output['confidence_rationale']}", "",
              "本报告仅供研究参考，不构成投资或交易指令。", ""]
    return "\n".join(lines)


def _validate_cio_content_and_queries(
    root: Path, request: Mapping[str, Any], output: Mapping[str, Any],
    catalog: list[dict[str, Any]],
) -> tuple[set[str], int]:
    """Mechanical identity and Evidence closure; not a subjective quality score."""

    if output["consumed_reports"] != [_report_identity(item) for item in catalog]:
        raise PredecisionCioStageError("CIO_REPORT_CONSUMPTION_INVALID")
    allowed_report_ids = {item["report_id"] for item in catalog}
    challenge_pairs = {
        (item["report_id"], challenge)
        for item in catalog for challenge in item["challenge_ids"]
    }
    for item in output["key_facts"]:
        if not set(item["report_ids"]) <= allowed_report_ids:
            raise PredecisionCioStageError("CIO_REPORT_REF_INVALID")
    for item in output["macro_market_transmission"]:
        if not set(item["report_ids"]) <= allowed_report_ids:
            raise PredecisionCioStageError("CIO_REPORT_REF_INVALID")
    seen_challenges = set()
    for item in output["challenge_dispositions"]:
        pair = (item["report_id"], item["challenge_id"])
        if pair not in challenge_pairs or pair in seen_challenges:
            raise PredecisionCioStageError("CIO_CHALLENGE_REF_INVALID")
        seen_challenges.add(pair)
    target_challenges = {
        pair for pair in challenge_pairs
        if request["target_security_id"] in next(
            item["security_ids"] for item in catalog if item["report_id"] == pair[0]
        )
    }
    if target_challenges and not seen_challenges:
        raise PredecisionCioStageError("CIO_CHALLENGE_DISPOSITION_MISSING")
    from product.runtime.validation import collect_evidence_refs
    evidence_refs = collect_evidence_refs(output)
    gate = _read(root / "evidence/gate.json")
    if not evidence_refs <= set(gate["allowed_evidence_ids"]):
        raise PredecisionCioStageError("CIO_EVIDENCE_OUTSIDE_GATE")
    queried_ids, query_count = _mcp_query_ids(root, request)
    if not evidence_refs <= queried_ids:
        raise PredecisionCioStageError("CIO_EVIDENCE_NOT_QUERIED")
    generated = _parse_time(output["generated_at"], "generated_at")
    if generated < _parse_time(request["decision_cutoff"], "decision_cutoff"):
        raise PredecisionCioStageError("CIO_GENERATED_AT_INVALID")
    return queried_ids, query_count


def finalize_predecision_cio_research(repository_root: Path, run_dir: Path) -> dict[str, Any]:
    """Publish only a fully verified, query-backed non-action research synthesis."""

    root = Path(run_dir).resolve()
    manifest, request = validate_predecision_cio_run(repository_root, root)
    if request["actual_level"] != "RESEARCH_SYNTHESIS":
        raise PredecisionCioStageError("CIO_RESEARCH_FINALIZER_LEVEL_INVALID")
    if any((root / name).exists() for name in ("decision.json", "risk.json", "cio/decision-draft.json")):
        raise PredecisionCioStageError("CIO_RESEARCH_ACTION_ARTIFACT_FORBIDDEN")
    model_output = _read(root / "invocation/final-message.json")
    model_proof = _model_execution_proof(repository_root, root, request)
    catalog = manifest["report_catalog"]
    schema = _output_schema(repository_root, request, catalog, run_dir=root)
    validate_schema_instance(model_output, schema)
    output = {**model_output, "generated_at": _host_generated_at(root, request)}
    queried_ids, query_count = _validate_cio_content_and_queries(root, request, output, catalog)
    trace = {
        "schema_version": "predecision-cio-trace/1.0.0",
        "run_id": request["run_id"], "stage": STAGE,
        "requested_level": request["requested_level"], "actual_level": "RESEARCH_SYNTHESIS",
        "source_run_id": request["source_run_id"],
        "source_package_hash": request["source_package_hash"],
        "request_hash": request["request_hash"], "manifest_hash": manifest["manifest_hash"],
        "model": request["model"], "report_catalog_hash": canonical_hash({"reports": catalog}),
        "cio_output_hash": canonical_hash(model_output),
        "published_output_hash": canonical_hash(output), "cio_query_count": query_count,
        "generated_at": output["generated_at"], "generated_at_source": "HOST_FINALIZER",
        "cio_model_proof": model_proof,
        "queried_evidence_ids": sorted(queried_ids),
        "risk_status": "NOT_RUN", "risk_not_run_reason": manifest["risk_not_run_reason"],
        "terminal_state": "COMPLETED_RESEARCH_SYNTHESIS",
    }
    report_text = _render_research_synthesis(output, request)
    trace["report_file_hash"] = hashlib.sha256(report_text.encode("utf-8")).hexdigest()
    trace["trace_hash"] = canonical_hash(trace)
    if any((root / name).exists() for name in (
        "cio-research-synthesis.json", "report.md", "decision_trace.json"
    )):
        raise PredecisionCioStageError("CIO_OUTPUT_ALREADY_EXISTS")
    (root / "cio-research-synthesis.json").write_text(json.dumps(output, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (root / "report.md").write_text(report_text, encoding="utf-8")
    (root / "decision_trace.json").write_text(json.dumps(trace, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {"status": "COMPLETED_RESEARCH_SYNTHESIS", "run_id": request["run_id"],
            "core_conclusion": output["judgment"],
            "report": str(root / "report.md"), "trace_hash": trace["trace_hash"]}


def finalize_predecision_cio_advice(repository_root: Path, run_dir: Path) -> dict[str, Any]:
    """Retired entry point: never publish advice from this research stage."""

    raise PredecisionCioStageError("CIO_PORTFOLIO_ADVICE_NOT_AVAILABLE")


def check_predecision_cio_trace(repository_root: Path, run_dir: Path) -> dict[str, Any]:
    """Read-only post-run integrity check; no model or Risk side effects."""

    root = Path(run_dir).resolve()
    manifest, request = validate_predecision_cio_run(repository_root, root)
    trace = _read(root / "decision_trace.json")
    if (trace.get("trace_hash") != canonical_hash({
            key: value for key, value in trace.items() if key != "trace_hash"
        }) or trace.get("run_id") != request["run_id"]
            or trace.get("source_run_id") != request["source_run_id"]
            or trace.get("source_package_hash") != request["source_package_hash"]
            or trace.get("requested_level") != request["requested_level"]
            or trace.get("actual_level") != request["actual_level"]):
        raise PredecisionCioStageError("CIO_TRACE_BINDING_INVALID")
    terminal = trace.get("terminal_state")
    if terminal == "FAILED_VALIDATION":
        error = _read(root / "run_error.json")
        if (error.get("failure_code") != trace.get("failure_code")
                or any((root / ref).exists() for ref in (
                    "decision.json", "report.md", "cio-research-synthesis.json"
                ))):
            raise PredecisionCioStageError("CIO_FAILED_TRACE_INVALID")
        return {"status": "FAILED_VALIDATION", "run_id": request["run_id"],
                "failure_code": error["failure_code"], "trace_hash": trace["trace_hash"]}
    process = _read(root / "invocation/process-result.json")
    process_exit_code = process.get("process_exit_code")
    if (process.get("run_id") != request["run_id"]
            or type(process_exit_code) is not int or process_exit_code != 0
            or process.get("timed_out") is not False
            or "failure_code" not in process or process["failure_code"] is not None
            or process.get("stage_status") != "COMPLETED_RESEARCH_SYNTHESIS"
            or process.get("stage_status") != terminal
            or process.get("source_integrity_unchanged") is not True):
        raise PredecisionCioStageError("CIO_PROCESS_RESULT_INVALID")
    if trace.get("cio_model_proof") != _model_execution_proof(repository_root, root, request):
        raise PredecisionCioStageError("CIO_MODEL_PROOF_DRIFT")
    catalog = manifest["report_catalog"]
    if (trace.get("manifest_hash") != manifest["manifest_hash"]
            or trace.get("request_hash") != request["request_hash"]
            or trace.get("report_catalog_hash") != canonical_hash({"reports": catalog})
            or not (root / "report.md").is_file()
            or not (root / "report.md").read_text(encoding="utf-8").strip()
            or trace.get("report_file_hash") != file_hash(root / "report.md")):
        raise PredecisionCioStageError("CIO_TRACE_ARTIFACT_INVALID")
    queried_ids, count = _mcp_query_ids(root, request)
    if trace.get("cio_query_count") != count or trace.get("queried_evidence_ids") != sorted(queried_ids):
        raise PredecisionCioStageError("CIO_TRACE_QUERY_INVALID")
    raw = _read(root / "invocation/final-message.json")
    if trace.get("cio_output_hash") != canonical_hash(raw):
        raise PredecisionCioStageError("CIO_TRACE_OUTPUT_HASH_INVALID")
    generated_at = trace.get("generated_at")
    if trace.get("generated_at_source") != "HOST_FINALIZER" or not isinstance(generated_at, str):
        raise PredecisionCioStageError("CIO_HOST_GENERATION_PROOF_INVALID")
    generated_time = _parse_time(generated_at, "trace.generated_at")
    started_time = _parse_time(
        _read(root / "invocation/environment-manifest.json").get("started_at"),
        "invocation.started_at",
    )
    if (generated_time < started_time
            or generated_time < _parse_time(request["decision_cutoff"], "decision_cutoff")
            or generated_time > datetime.now(timezone.utc)):
        raise PredecisionCioStageError("CIO_HOST_GENERATION_PROOF_INVALID")
    published = _read(root / "cio-research-synthesis.json")
    if (terminal != "COMPLETED_RESEARCH_SYNTHESIS"
            or trace.get("risk_status") != "NOT_RUN"
            or trace.get("risk_not_run_reason") != manifest["risk_not_run_reason"]
            or published != {**raw, "generated_at": generated_at}
            or trace.get("published_output_hash") != canonical_hash(published)
            or any((root / ref).exists() for ref in (
                "decision.json", "risk.json", "cio/decision-draft.json"
            ))):
        raise PredecisionCioStageError("CIO_RESEARCH_TRACE_INVALID")
    return {"status": "PASSED", "run_id": request["run_id"],
            "terminal_state": terminal, "trace_hash": trace["trace_hash"]}


def launch_predecision_cio_run(
    repository_root: Path, *, run_dir: Path, codex_binary: str = "codex",
    timeout_seconds: int = 2400,
) -> tuple[dict[str, Any], int]:
    """Host-only single main-thread CIO invocation for a prepared delivery level."""

    if os.environ.get("STOCK_AGENT_PRODUCT_HOST_LAUNCH") != "1":
        raise PredecisionCioStageError("CIO_HOST_LAUNCH_REQUIRED")
    from product.runtime.nested_codex import (
        build_nested_codex_command, fixture_mcp_runtime_environment, integrity_snapshot,
    )

    repository_root = Path(repository_root).resolve()
    root = Path(run_dir).resolve()
    manifest, request = validate_predecision_cio_run(repository_root, root)
    invocation_dir = root / "invocation"
    if invocation_dir.exists():
        raise PredecisionCioStageError("CIO_ALREADY_LAUNCHED")
    prompt = build_predecision_cio_prompt(repository_root, root)
    schema = _decoding_schema(_output_schema(
        repository_root, request, manifest["report_catalog"], run_dir=root
    ))
    invocation_dir.mkdir()
    prompt_path = invocation_dir / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    schema_path = invocation_dir / "cio-output.schema.json"
    schema_path.write_text(json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    runtime_root = root / ".codex-runtime-cio"
    sqlite_home, log_dir, tmp_dir = (
        runtime_root / "sqlite", runtime_root / "logs", runtime_root / "tmp"
    )
    for path in (sqlite_home, log_dir, tmp_dir):
        path.mkdir(parents=True, exist_ok=False)
    final_path = tmp_dir / "final-message.json"
    command = build_nested_codex_command(
        codex_binary=codex_binary, product_root=repository_root / "product",
        run_dir=root, model=request["model"], sqlite_home=sqlite_home, log_dir=log_dir,
        final_message_path=final_path,
        hook_recorder_path=repository_root / "product/runtime/codex_hook_recorder.py",
        output_schema_path=schema_path, fixture_mcp_run_dir=root,
        hook_agent_matcher="^runtime_cio$",
        skip_git_repo_check=True,
    )
    # The child workspace is the external run directory. Under workspace-write
    # the repository remains readable but is not a writable root.
    command[command.index("-C") + 1] = str(root)
    # The current desktop user config contains app-only MCP fields that this
    # installed CLI rejects under --strict-config. Keep auth in CODEX_HOME,
    # but load the repository's product config instead of the unrelated UI config.
    command.insert(command.index("exec") + 1, "--ignore-user-config")
    environment = dict(os.environ)
    environment.update({
        "TMPDIR": str(tmp_dir), "PYTHONDONTWRITEBYTECODE": "1",
        "STOCK_AGENT_RUN_DIR": str(root), "STOCK_AGENT_FIXTURE_MCP_RUN_DIR": str(root),
        "STOCK_AGENT_PREDECISION_CIO_STAGE": "predecision-cio-runtime/1.0.0",
        **fixture_mcp_runtime_environment(),
    })
    for key in ("STOCK_AGENT_START_CONTEXT", "STOCK_AGENT_CAPTURE_SPECIALIST_OUTPUT",
                "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS", "STOCK_AGENT_MULTIDIMENSIONAL_STAGE",
                "STOCK_AGENT_INDEPENDENT_SKEPTIC_STAGE", "STOCK_AGENT_SKEPTIC_DISPATCH_INDEX"):
        environment.pop(key, None)
    before = integrity_snapshot(repository_root)
    (invocation_dir / "environment-manifest.json").write_text(json.dumps({
        "schema_version": "predecision-cio-environment/1.0.0",
        "run_id": request["run_id"], "model": request["model"],
        "command": command, "prompt_hash": file_hash(prompt_path),
        "output_schema_hash": file_hash(schema_path),
        "product_instructions_file_hash": file_hash(repository_root / "product/AGENTS.md"),
        "skill_file_hash": file_hash(repository_root / "product/skills/portfolio-council/SKILL.md"),
        "agent_file_hash": file_hash(repository_root / "product/.codex/agents/runtime_cio.toml"),
        "stage_instructions_hash": hashlib.sha256(
            _stage_instruction_bundle(repository_root / "product").encode("utf-8")
        ).hexdigest(),
        "source_integrity_before": before,
        "started_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    }, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
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
    (invocation_dir / "codex-events.jsonl").write_text(stdout, encoding="utf-8")
    (invocation_dir / "codex-stderr.log").write_text(stderr, encoding="utf-8")
    after = integrity_snapshot(repository_root)
    failure = None
    try:
        if timed_out:
            raise PredecisionCioStageError("CIO_STAGE_TIMEOUT")
        if process_code != 0:
            raise PredecisionCioStageError("CIO_CODEX_PROCESS_FAILED")
        if before != after:
            raise PredecisionCioStageError("CIO_PRODUCT_SOURCE_CHANGED")
        events = [json.loads(line) for line in stdout.splitlines() if line.strip()]
        if not events or events[-1].get("type") != "turn.completed":
            raise PredecisionCioStageError("CIO_FINAL_TURN_INCOMPLETE")
        final_text = final_path.read_text(encoding="utf-8")
        messages = [event.get("item", {}).get("text") for event in events
                    if event.get("type") == "item.completed"
                    and isinstance(event.get("item"), Mapping)
                    and event["item"].get("type") == "agent_message"]
        if not messages or messages[-1].strip() != final_text.strip():
            raise PredecisionCioStageError("CIO_FINAL_EVENT_MISMATCH")
        def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result: dict[str, Any] = {}
            for key, value in pairs:
                if key in result:
                    raise PredecisionCioStageError("CIO_FINAL_DUPLICATE_KEY")
                result[key] = value
            return result
        raw_output = json.loads(final_text, object_pairs_hook=unique_keys)
        if not isinstance(raw_output, dict):
            raise PredecisionCioStageError("CIO_FINAL_RESPONSE_NOT_OBJECT")
        (invocation_dir / "final-message.json").write_text(final_text, encoding="utf-8")
        result = finalize_predecision_cio_research(repository_root, root)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        failure = str(exc).split(":", 1)[0]
        result = {"status": "FAILED_VALIDATION", "run_id": request["run_id"],
                  "failure_code": failure}
        error = {"schema_version": "predecision-cio-error/1.0.0", "run_id": request["run_id"],
                 "failed_stage": "CIO" if process_code == 0 else "MODEL_PROCESS",
                 "failure_code": failure, "process_exit_code": process_code}
        (root / "run_error.json").write_text(json.dumps(error, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        trace = {"schema_version": "predecision-cio-trace/1.0.0", "run_id": request["run_id"],
                 "stage": STAGE, "requested_level": request["requested_level"],
                 "actual_level": request["actual_level"], "source_run_id": request["source_run_id"],
                 "source_package_hash": request["source_package_hash"],
                 "terminal_state": "FAILED_VALIDATION", "failed_stage": error["failed_stage"],
                 "failure_code": failure, "risk_status": "NOT_RUN"}
        trace["trace_hash"] = canonical_hash(trace)
        (root / "decision_trace.json").write_text(json.dumps(trace, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (invocation_dir / "process-result.json").write_text(json.dumps({
        "schema_version": "predecision-cio-process/1.0.0",
        "run_id": request["run_id"], "process_exit_code": process_code,
        "timed_out": timed_out, "stage_status": result["status"],
        "failure_code": failure, "source_integrity_unchanged": before == after,
    }, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return result, 0 if result["status"] == "COMPLETED_RESEARCH_SYNTHESIS" else 7


def prepare_predecision_cio_run(
    repository_root: Path, *, source_run_dir: Path, run_dir: Path, run_id: str,
    target_security_id: str, requested_level: str = "RESEARCH_SYNTHESIS",
    time_mode: str = "SOURCE_CUTOFF", max_research_age_days: int | None = None,
    mandate_path: Path | None = None, model: str | None = None,
) -> dict[str, Any]:
    """Revalidate and materialize immutable inputs before any CIO invocation."""

    if requested_level != "RESEARCH_SYNTHESIS":
        raise PredecisionCioStageError("CIO_PORTFOLIO_ADVICE_NOT_AVAILABLE")
    if mandate_path is not None:
        raise PredecisionCioStageError("CIO_MANDATE_NOT_APPLICABLE_TO_RESEARCH")
    if target_security_id != RESEARCH_TARGET:
        raise PredecisionCioStageError("CIO_RESEARCH_TARGET_NOT_IN_SCOPE")
    if time_mode != "SOURCE_CUTOFF" or max_research_age_days is not None:
        raise PredecisionCioStageError("CIO_CURRENT_RESEARCH_REQUIRES_NEW_SOURCE")
    repository_root = Path(repository_root).resolve()
    source_run_dir = Path(source_run_dir).resolve()
    run_dir = Path(run_dir).resolve()
    if (not source_run_dir.is_dir() or source_run_dir == run_dir
            or run_dir.is_relative_to(source_run_dir)
            or source_run_dir.is_relative_to(run_dir)):
        raise PredecisionCioStageError("CIO_SOURCE_RUN_INVALID")
    if source_run_dir.is_relative_to(repository_root) or run_dir.is_relative_to(repository_root):
        raise PredecisionCioStageError("CIO_RUN_MUST_BE_EXTERNAL")
    if run_dir.exists() and any(run_dir.iterdir()):
        raise PredecisionCioStageError("CIO_RUN_DIR_NOT_EMPTY")
    if not run_id or "/" in run_id or "\\" in run_id:
        raise PredecisionCioStageError("CIO_RUN_ID_INVALID")
    source_ref = _latest_package_ref(source_run_dir)
    source_package = _read(source_run_dir / source_ref)
    validate_forward_gate(repository_root, source_run_dir)
    validate_predecision_package(repository_root, source_run_dir, source_package)
    if source_package["consumability"] != "DOWNSTREAM_READY":
        raise PredecisionCioStageError("CIO_SOURCE_PACKAGE_NOT_READY")
    source_manifest = _read(source_run_dir / "run_manifest.json")
    if run_id == source_manifest["run_id"]:
        raise PredecisionCioStageError("CIO_RUN_ID_REUSED")
    bundle = _read(source_run_dir / "research/holding-research-bundle.json")
    if target_security_id not in bundle["common_stock_security_ids"]:
        raise PredecisionCioStageError("CIO_TARGET_NOT_RESEARCHED")
    source_gate = _read(source_run_dir / "evidence/gate.json")
    selected_model = select_product_runtime_model(
        repository_root / "product", requested_model=model or agent_development_test_model()
    )
    from product.runtime.discovery import discover_product_resources
    discovery = discover_product_resources(repository_root)
    _stage_instruction_bundle(repository_root / "product")
    catalog = _report_catalog(source_run_dir, bundle, source_package)
    report_refs = [ref["artifact_ref"] for ref in bundle["report_refs"]]
    report_refs.extend(
        item["report"]["artifact_ref"] for item in source_package["counter_theses"]
        if item["report"] is not None
    )
    refs = sorted(set([
        source_ref, "run_manifest.json", "audit/portfolio-handoff.json",
        "council-request.json", "evidence/gate.json",
        "research/holding-research-bundle.json", source_package["execution_proof"]["artifact_ref"],
        *report_refs,
    ]))
    frozen = [{"artifact_ref": ref, "file_hash": file_hash(_resolve_ref(source_run_dir, ref))} for ref in refs]
    request = {
        "schema_version": REQUEST_VERSION, "stage": STAGE, "run_id": run_id,
        "source_run_id": source_package["run_id"], "source_package_ref": source_ref,
        "source_package_hash": source_package["package_hash"],
        "source_request_id": source_package["request_id"],
        "source_request_hash": source_package["request_hash"],
        "handoff_id": source_package["handoff_id"], "handoff_hash": source_package["handoff_hash"],
        "portfolio_hash": source_package["portfolio_hash"],
        "gate_hash": source_package["gate_hash"],
        "decision_cutoff": source_package["decision_cutoff"],
        "target_security_id": target_security_id,
        "requested_level": "RESEARCH_SYNTHESIS", "actual_level": "RESEARCH_SYNTHESIS",
        "time_mode": "SOURCE_CUTOFF", "model": selected_model,
    }
    request["request_hash"] = canonical_hash(request)
    schema = _read(repository_root / "product/schemas/runtime/predecision-cio-request.schema.json")
    validate_schema_instance(request, schema)
    manifest = {
        "schema_version": MANIFEST_VERSION, "stage": STAGE, "run_id": run_id,
        "output_dir": str(run_dir), "source_mode": "frozen-gate",
        "discovery": {"product_root": str(repository_root / "product")},
        "product_discovery_hash": discovery.discovery_hash,
        "source_run_id": source_package["run_id"], "source_run_dir": str(source_run_dir),
        "source_package_hash": source_package["package_hash"],
        "request_hash": request["request_hash"], "frozen_inputs": frozen,
        "report_catalog": catalog,
        "resource_locks": {relative: file_hash(repository_root / relative) for relative in LOCKED_RESOURCES},
        "model": selected_model, "risk_status": "NOT_RUN",
        "risk_not_run_reason": "RESEARCH_ONLY",
    }
    manifest["manifest_hash"] = canonical_hash(manifest)
    # All validation precedes the first write. The source directory is never modified.
    run_dir.mkdir(parents=True, exist_ok=False) if not run_dir.exists() else None
    for ref in refs:
        target = run_dir / "source-inputs" / ref
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(_resolve_ref(source_run_dir, ref), target)
    report_catalog = {"reports": catalog}
    report_catalog["catalog_hash"] = canonical_hash(report_catalog)
    (run_dir / "report-catalog.json").write_text(json.dumps(report_catalog, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    source_gate["run_id"] = run_id
    source_gate["bundle_hash"] = canonical_hash({key: value for key, value in source_gate.items() if key != "bundle_hash"})
    (run_dir / "evidence").mkdir(exist_ok=True)
    (run_dir / "evidence/gate.json").write_text(json.dumps(source_gate, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    invocation = {
        "schema_version": "predecision-cio-invocation/1.0.0", "run_id": run_id,
        "invocation_id": f"cio:{run_id}", "agent": {"name": "runtime_cio"},
        "tool_permissions": ["fixture_evidence.query"],
        "source_gate_hash": source_package["gate_hash"],
        "gate_hash": source_gate["bundle_hash"],
        "allowed_evidence_ids": source_gate["allowed_evidence_ids"],
    }
    invocation["invocation_hash"] = canonical_hash(invocation)
    (run_dir / "invocations").mkdir(exist_ok=True)
    (run_dir / "invocations/runtime_cio.json").write_text(json.dumps(invocation, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (run_dir / "predecision-cio-request.json").write_text(json.dumps(request, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    return {"run_id": run_id, "run_dir": str(run_dir), "requested_level": requested_level,
            "actual_level": "RESEARCH_SYNTHESIS",
            "request_hash": request["request_hash"], "manifest_hash": manifest["manifest_hash"]}
