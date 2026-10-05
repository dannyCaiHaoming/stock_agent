"""普通股研究阶段的聚焦 Eval 作业。

本模块只冻结并校验真实研究产物，语义评分由既有 dev_eval Agent 完成。
它不生成公司判断，也不调用完整 Council Eval。
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.council.common_stock_research import validate_equity_research_report
from product.council.common_stock_research import validate_research_coverage
from product.council.research_output import validate_persisted_equity_research_pair
from product.runtime.hashing import canonical_hash, file_hash, legacy_envelope_hash, verify_legacy_envelope_hash, HashContractError
from product.runtime.schema_validation import (
    SchemaValidationError,
    validate_schema_definition,
    validate_schema_instance,
)
from .model_routing import DEFAULT_GRADER_MODEL


EVAL_JOB_VERSION = "common-stock-research-eval-job/1.2.0"
EVAL_RESULT_VERSION = "common-stock-research-eval-result/1.0.0"
EVAL_RUNTIME_VERSION = "common-stock-research-eval-runtime/1.0.0"
EVAL_DRAFT_VERSION = "common-stock-research-eval-draft/1.0.0"
DIMENSIONS = (
    "business_understanding",
    "comparable_financial_analysis",
    "thesis_causal_chain",
    "valuation_grounding",
    "catalyst_or_gap",
    "counterevidence_quality",
    "reevaluation_conditions",
    "confidence_evidence_alignment",
    "action_boundary",
)


class CommonStockEvalError(ValueError):
    """聚焦 Eval 的 fail-closed 错误。"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CommonStockEvalError(f"COMMON_STOCK_EVAL_INPUT_INVALID:{path.name}") from exc
    if not isinstance(value, Mapping):
        raise CommonStockEvalError(f"COMMON_STOCK_EVAL_INPUT_NOT_OBJECT:{path.name}")
    return dict(value)


def _write_object(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        raise CommonStockEvalError(f"COMMON_STOCK_EVAL_OUTPUT_EXISTS:{path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def prepare_common_stock_eval_job(
    *,
    report_path: Path,
    request_path: Path,
    gate_path: Path,
    rubric_path: Path,
    output_dir: Path,
    eval_id: str,
    calculation_artifact_ids: Sequence[str] = (),
    mcp_events_path: Path | None = None,
) -> dict[str, Any]:
    """从真实报告和冻结 Gate 创建不可冒充的语义评分输入。"""

    report_path = Path(report_path).resolve()
    request_path = Path(request_path).resolve()
    gate_path = Path(gate_path).resolve()
    rubric_path = Path(rubric_path).resolve()
    output_dir = Path(output_dir).resolve()
    if output_dir.exists():
        raise CommonStockEvalError("COMMON_STOCK_EVAL_DIRECTORY_EXISTS")
    report = _read_object(report_path)
    request = _read_object(request_path)
    gate = _read_object(gate_path)
    rubric = _read_object(rubric_path)
    if mcp_events_path is not None:
        event_path = Path(mcp_events_path).resolve()
        identifiers: list[str] = []
        for line in event_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            event = json.loads(line)
            if (
                event.get("event_type") == "mcp_tool_result"
                and event.get("invocation_id") == report.get("invocation_id")
                and event.get("tool") == "fixture_math.calculate"
                and isinstance(event.get("calculation_id"), str)
            ):
                identifiers.append(event["calculation_id"])
        calculation_artifact_ids = sorted(set(identifiers))
    validate_equity_research_report(
        report, request=request, calculation_artifact_ids=calculation_artifact_ids
    )
    if set(request["allowed_evidence_ids"]) - set(gate.get("allowed_evidence_ids", [])):
        raise CommonStockEvalError("COMMON_STOCK_EVAL_GATE_BINDING_INVALID")
    if (
        not isinstance(rubric.get("dimensions"), Mapping)
        or set(rubric["dimensions"]) != set(DIMENSIONS)
    ):
        raise CommonStockEvalError("COMMON_STOCK_EVAL_RUBRIC_INVALID")
    allowed_evidence = [
        item for item in gate.get("allowed_evidence", [])
        if item.get("evidence_id") in set(request["allowed_evidence_ids"])
    ]
    source_hashes = {
        "report": file_hash(report_path),
        "request": file_hash(request_path),
        "gate": file_hash(gate_path),
        "rubric": file_hash(rubric_path),
    }
    if mcp_events_path is not None:
        source_hashes["mcp_events"] = file_hash(Path(mcp_events_path).resolve())
    report_markdown = None
    report_markdown_path = report_path.with_suffix(".md")
    if report_markdown_path.is_file():
        validate_persisted_equity_research_pair(
            json_path=report_path,
            markdown_path=report_markdown_path,
            request=request,
            evidence=allowed_evidence,
            calculation_artifact_ids=calculation_artifact_ids,
        )
        report_markdown = report_markdown_path.read_text(encoding="utf-8")
        source_hashes["report_markdown"] = file_hash(report_markdown_path)
    coverage_binding = None
    try:
        candidate_run_dir = report_path.parents[3]
        report_ref = str(report_path.relative_to(candidate_run_dir))
        output_ref = str(output_dir.relative_to(candidate_run_dir))
        coverage_path = candidate_run_dir / "research/coverage.json"
        handoff_path = candidate_run_dir / "audit/portfolio-handoff.json"
        council_request_path = candidate_run_dir / "council-request.json"
        if all(path.is_file() for path in (coverage_path, handoff_path, council_request_path)):
            coverage_binding = {
                "run_dir": str(candidate_run_dir),
                "report_ref": report_ref,
                "eval_output_ref": output_ref,
                "report_content_hash": canonical_hash(report),
            }
    except (IndexError, ValueError):
        coverage_binding = None
    payload = {
        "schema_version": EVAL_JOB_VERSION,
        "grader_model": DEFAULT_GRADER_MODEL,
        "eval_id": eval_id,
        "run_id": report["run_id"],
        "invocation_id": report["invocation_id"],
        "security_id": report["security"]["security_id"],
        "source_hashes": source_hashes,
        "coverage_binding": coverage_binding,
        "rubric_id": rubric["rubric_id"],
        "rubric": rubric,
        "hard_gates": {
            "schema": "PASS",
            "evidence_closure": "PASS",
            "pit_input_binding": "PASS",
            "action_boundary": "PASS",
        },
        "report": report,
        "allowed_evidence": allowed_evidence,
        "semantic_output_delivery": EVAL_DRAFT_VERSION,
    }
    if report_markdown is not None:
        payload["report_markdown"] = report_markdown
    payload["input_hash"] = legacy_envelope_hash(payload, hash_field="input_hash")
    output_dir.mkdir(parents=True)
    _write_object(output_dir / "input-manifest.json", payload)
    return payload


def build_common_stock_eval_result_schema(
    manifest: Mapping[str, Any], *, expected_model: str | None = None
) -> dict[str, Any]:
    from product.runtime.versioning import load_version_manifest, approved_component_version
    approved_component_version(
        load_version_manifest(Path(__file__).resolve().parents[1] / "version-manifest.json"),
        "schemas", "common-stock-research-eval", observed=EVAL_RESULT_VERSION.rsplit("/", 1)[-1])
    dimension = {
        "type": "object", "additionalProperties": False,
        "required": ["status", "grade", "claim_refs", "evidence_refs", "rationale"],
        "properties": {
            "status": {"type": "string", "enum": ["PASS", "FAIL"]},
            "grade": {"type": "integer", "minimum": 0, "maximum": 3},
            "claim_refs": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
            "evidence_refs": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
            "rationale": {"type": "string", "minLength": 1},
        },
    }
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object", "additionalProperties": False,
        "required": [
            "schema_version", "eval_id", "run_id", "invocation_id", "security_id",
            "input_hash", "rubric_id", "model", "status", "dimensions", "result_hash",
        ],
        "properties": {
            "schema_version": {"type": "string", "const": EVAL_RESULT_VERSION},
            "eval_id": {"type": "string", "const": manifest["eval_id"]},
            "run_id": {"type": "string", "const": manifest["run_id"]},
            "invocation_id": {"type": "string", "const": manifest["invocation_id"]},
            "security_id": {"type": "string", "const": manifest["security_id"]},
            "input_hash": {"type": "string", "const": manifest["input_hash"]},
            "rubric_id": {"type": "string", "const": manifest["rubric_id"]},
            "model": (
                {"type": "string", "const": expected_model}
                if expected_model is not None
                else {"type": "string", "minLength": 1}
            ),
            "status": {"type": "string", "enum": ["PASS", "FAIL"]},
            "dimensions": {
                "type": "object", "additionalProperties": False,
                "required": list(DIMENSIONS),
                "properties": {name: dimension for name in DIMENSIONS},
            },
            "result_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        },
    }
    validate_schema_definition(schema)
    return schema


def build_common_stock_eval_draft_schema(manifest: Mapping[str, Any]) -> dict[str, Any]:
    schema = build_common_stock_eval_result_schema(manifest)
    schema["required"] = ["schema_version", "status", "dimensions"]
    schema["properties"] = {key: schema["properties"][key] for key in schema["required"]}
    schema["properties"]["schema_version"] = {"type": "string", "const": EVAL_DRAFT_VERSION}
    validate_schema_definition(schema)
    return schema


def _validated_eval_manifest(eval_dir: Path) -> dict[str, Any]:
    manifest = _read_object(eval_dir / "input-manifest.json")
    try:
        verify_legacy_envelope_hash(manifest, hash_field="input_hash", location="input-manifest.json")
    except HashContractError as exc:
        raise CommonStockEvalError(f"COMMON_STOCK_EVAL_INPUT_HASH_INVALID:{exc}") from exc
    if manifest.get("schema_version") == EVAL_JOB_VERSION and manifest.get("grader_model") != DEFAULT_GRADER_MODEL:
        raise CommonStockEvalError("COMMON_STOCK_EVAL_MODEL_LOCK_INVALID")
    return manifest


def envelope_common_stock_eval_draft(draft: Mapping[str, Any], *, manifest: Mapping[str, Any],
                                     actual_model: str, input_binding_hash: str) -> dict[str, Any]:
    if manifest.get("semantic_output_delivery") != EVAL_DRAFT_VERSION:
        raise CommonStockEvalError("COMMON_STOCK_EVAL_LEGACY_WRITE_RETIRED")
    if manifest.get("schema_version") == EVAL_JOB_VERSION and manifest.get("grader_model") != DEFAULT_GRADER_MODEL:
        raise CommonStockEvalError("COMMON_STOCK_EVAL_MODEL_LOCK_INVALID")
    if not isinstance(actual_model, str) or not actual_model.strip():
        raise CommonStockEvalError("COMMON_STOCK_EVAL_MODEL_PROOF_MISSING")
    if input_binding_hash != manifest["input_hash"]:
        raise CommonStockEvalError("COMMON_STOCK_EVAL_INPUT_BINDING_INVALID")
    if "grader_model" in manifest and actual_model != manifest["grader_model"]:
        raise CommonStockEvalError("COMMON_STOCK_EVAL_MODEL_MISMATCH")
    try:
        validate_schema_instance(draft, build_common_stock_eval_draft_schema(manifest))
    except SchemaValidationError as exc:
        raise CommonStockEvalError(f"COMMON_STOCK_EVAL_RESULT_SCHEMA_INVALID:{exc}") from exc
    result = {"schema_version": EVAL_RESULT_VERSION, "model": actual_model,
              **{key: manifest[key] for key in ("eval_id", "run_id", "invocation_id", "security_id",
                                                "input_hash", "rubric_id")},
              "status": draft["status"], "dimensions": draft["dimensions"]}
    result["result_hash"] = legacy_envelope_hash(result, hash_field="result_hash")
    validate_common_stock_eval_result(result, manifest=manifest)
    return result


def build_common_stock_eval_prompt(
    eval_dir: Path, *, expected_model: str | None = None
) -> str:
    """生成供既有 dev_eval Agent 使用的最小提示，不补充外部事实。"""

    eval_dir = Path(eval_dir).resolve()
    manifest = _validated_eval_manifest(eval_dir)
    if expected_model is not None and "grader_model" in manifest and expected_model != manifest["grader_model"]:
        raise CommonStockEvalError("COMMON_STOCK_EVAL_MODEL_MISMATCH")
    return (
        "读取本次普通股研究 Eval 输入，并使用已加载的 runtime-eval-grading 方法，"
        "只依据冻结报告和 Evidence 对 rubric 的九个维度逐项评分。输入若包含由同一份"
        "合法 JSON 确定性渲染的 report_markdown，必须与结构化 report 一并评价，不能忽略"
        "其中面向用户的限定说明。不得补充外部事实、"
        "修改报告、推导买卖动作或启动完整 Council Eval。每项 status 只能为 PASS 或 FAIL，"
        "grade 只能为 0、1、2、3，并提供 report 中的 claim_refs/evidence_refs 和简短中文理由。"
        "本版本化聚焦阶段按设计停止于公司报告集，不生成 decision_trace、Artifact Replay、"
        "CIO 或 Risk 产物；不得因这些不适用产物缺失而拒绝评分。"
        "只返回符合 common-stock-research-eval-draft/1.0.0 的 JSON，字段只有 schema_version、status、dimensions；claim_refs 只能使用"
        "报告内原始 claim_id，evidence_refs 只能使用本包 allowed_evidence 内原始 evidence_id。"
        "身份、模型、input_hash、rubric_id 和 result_hash 由运行层依据实际任务装配，不要填写或计算。\n"
        + "\n输入文件：" + str(eval_dir / "input-manifest.json")
    )


def build_common_stock_eval_packet(
    eval_dir: Path, *, expected_model: str | None = None
) -> dict[str, Any]:
    eval_dir = Path(eval_dir).resolve()
    manifest = _validated_eval_manifest(eval_dir)
    if manifest.get("semantic_output_delivery") != EVAL_DRAFT_VERSION:
        raise CommonStockEvalError("COMMON_STOCK_EVAL_LEGACY_WRITE_RETIRED")
    return {
        "runtime_contract": EVAL_RUNTIME_VERSION,
        "instruction": build_common_stock_eval_prompt(
            eval_dir, expected_model=expected_model
        ),
        "input_manifest": manifest,
        "output_schema": build_common_stock_eval_draft_schema(manifest),
    }


def build_common_stock_eval_dispatch_message(eval_dir: Path) -> str:
    manifest = _read_object(Path(eval_dir).resolve() / "input-manifest.json")
    return (
        f"普通股研究聚焦评分 {manifest['eval_id']}。等待 SubagentStart Hook 注入冻结 Eval 包；"
        "不得补充外部事实或修改研究报告。"
    )


def common_stock_eval_model_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    """评分内容投影：完整输入和技术锁留在运行层，研究正文/引用/限制不裁剪。"""
    import copy
    manifest = packet["input_manifest"]
    report = copy.deepcopy(manifest["report"])
    # 保留报告原文整体（包括其必要上下文），只删外围重复的锁/路径/身份包装。
    # 不按键名递归删除 hash/source 字段，以免删掉事实或报告内有意义的内容。
    materials = {"run_id": manifest["run_id"], "security_id": manifest["security_id"],
                 "report": report, "rubric": copy.deepcopy(manifest["rubric"]),
                 "allowed_evidence": copy.deepcopy(manifest["allowed_evidence"]),
                 "hard_gates": copy.deepcopy(manifest["hard_gates"])}
    if "report_markdown" in manifest:
        materials["report_markdown"] = manifest["report_markdown"]
    return {"runtime_contract": packet["runtime_contract"], "model_view_version": "common-stock-eval-model-view/1.0.0",
            "instruction": packet["instruction"], "input": materials,
            "output_schema": copy.deepcopy(packet["output_schema"])}


def validate_common_stock_eval_result(
    result: Mapping[str, Any], *, manifest: Mapping[str, Any]
) -> None:
    required = {
        "schema_version", "eval_id", "run_id", "invocation_id", "security_id",
        "input_hash", "rubric_id", "model", "status", "dimensions", "result_hash",
    }
    if set(result) != required or result.get("schema_version") != EVAL_RESULT_VERSION:
        raise CommonStockEvalError("COMMON_STOCK_EVAL_RESULT_SCHEMA_INVALID")
    for key in ("eval_id", "run_id", "invocation_id", "security_id", "input_hash", "rubric_id"):
        if result.get(key) != manifest.get(key):
            raise CommonStockEvalError(f"COMMON_STOCK_EVAL_RESULT_BINDING_INVALID:{key}")
    if manifest.get("schema_version") == EVAL_JOB_VERSION and manifest.get("grader_model") != DEFAULT_GRADER_MODEL:
        raise CommonStockEvalError("COMMON_STOCK_EVAL_MODEL_LOCK_INVALID")
    if "grader_model" in manifest and result.get("model") != manifest["grader_model"]:
        raise CommonStockEvalError("COMMON_STOCK_EVAL_MODEL_MISMATCH")
    if not isinstance(result.get("model"), str) or not result["model"]:
        raise CommonStockEvalError("COMMON_STOCK_EVAL_MODEL_MISSING")
    dimensions = result.get("dimensions")
    if not isinstance(dimensions, Mapping) or set(dimensions) != set(DIMENSIONS):
        raise CommonStockEvalError("COMMON_STOCK_EVAL_DIMENSIONS_INVALID")
    report = manifest.get("report")
    allowed_evidence = manifest.get("allowed_evidence")
    if not isinstance(report, Mapping) or not isinstance(allowed_evidence, list):
        raise CommonStockEvalError("COMMON_STOCK_EVAL_MANIFEST_CONTENT_INVALID")
    allowed_claim_ids = {
        item.get("claim_id") for item in report.get("claims", [])
        if isinstance(item, Mapping) and isinstance(item.get("claim_id"), str)
    }
    allowed_evidence_ids = {
        item.get("evidence_id") for item in allowed_evidence
        if isinstance(item, Mapping) and isinstance(item.get("evidence_id"), str)
    }
    statuses = []
    for name, value in dimensions.items():
        if not isinstance(value, Mapping) or set(value) != {
            "status", "grade", "claim_refs", "evidence_refs", "rationale"
        }:
            raise CommonStockEvalError(f"COMMON_STOCK_EVAL_DIMENSION_INVALID:{name}")
        if value.get("status") not in {"PASS", "FAIL"} or value.get("grade") not in {0, 1, 2, 3}:
            raise CommonStockEvalError(f"COMMON_STOCK_EVAL_DIMENSION_GRADE_INVALID:{name}")
        if value["status"] != ("PASS" if value["grade"] >= 2 else "FAIL"):
            raise CommonStockEvalError(f"COMMON_STOCK_EVAL_DIMENSION_STATUS_INVALID:{name}")
        for key in ("claim_refs", "evidence_refs"):
            if not isinstance(value.get(key), list) or any(not isinstance(item, str) for item in value[key]):
                raise CommonStockEvalError(f"COMMON_STOCK_EVAL_DIMENSION_REFS_INVALID:{name}")
            if len(value[key]) != len(set(value[key])):
                raise CommonStockEvalError(f"COMMON_STOCK_EVAL_DIMENSION_REFS_DUPLICATE:{name}")
        if not set(value["claim_refs"]) <= allowed_claim_ids:
            raise CommonStockEvalError(f"COMMON_STOCK_EVAL_CLAIM_REF_INVALID:{name}")
        if not set(value["evidence_refs"]) <= allowed_evidence_ids:
            raise CommonStockEvalError(f"COMMON_STOCK_EVAL_EVIDENCE_REF_INVALID:{name}")
        if not isinstance(value.get("rationale"), str) or not value["rationale"].strip():
            raise CommonStockEvalError(f"COMMON_STOCK_EVAL_DIMENSION_RATIONALE_MISSING:{name}")
        statuses.append(value["status"])
    expected_status = "PASS" if all(item == "PASS" for item in statuses) else "FAIL"
    if result.get("status") != expected_status:
        raise CommonStockEvalError("COMMON_STOCK_EVAL_AGGREGATE_INVALID")
    try:
        verify_legacy_envelope_hash(result, hash_field="result_hash", location="eval/result.json")
    except HashContractError as exc:
        raise CommonStockEvalError(f"COMMON_STOCK_EVAL_RESULT_HASH_INVALID:{exc}") from exc
    try:
        validate_schema_instance(result, build_common_stock_eval_result_schema(manifest))
    except SchemaValidationError as exc:
        raise CommonStockEvalError(f"COMMON_STOCK_EVAL_RESULT_SCHEMA_INVALID:{exc}") from exc


def _attach_eval_to_coverage(
    *, eval_dir: Path, manifest: Mapping[str, Any], result: Mapping[str, Any]
) -> None:
    """把显式 Eval 结果绑定到同一运行的证券覆盖项；无运行绑定时不猜测。"""

    binding = manifest.get("coverage_binding")
    if binding is None:
        return
    if not isinstance(binding, Mapping):
        raise CommonStockEvalError("COMMON_STOCK_EVAL_COVERAGE_BINDING_INVALID")
    run_dir = Path(str(binding.get("run_dir", ""))).resolve()
    coverage_path = run_dir / "research/coverage.json"
    handoff_path = run_dir / "audit/portfolio-handoff.json"
    council_request_path = run_dir / "council-request.json"
    report_path = run_dir / str(binding.get("report_ref", ""))
    if not all(path.is_file() for path in (coverage_path, handoff_path, council_request_path, report_path)):
        raise CommonStockEvalError("COMMON_STOCK_EVAL_COVERAGE_ARTIFACT_MISSING")
    report = _read_object(report_path)
    report_hash = canonical_hash(report)
    if (
        report_hash != binding.get("report_content_hash")
        or file_hash(report_path) != manifest.get("source_hashes", {}).get("report")
        or report.get("invocation_id") != manifest.get("invocation_id")
    ):
        raise CommonStockEvalError("COMMON_STOCK_EVAL_REPORT_DRIFT")
    coverage = _read_object(coverage_path)
    handoff = _read_object(handoff_path)
    council_request = _read_object(council_request_path)
    matches = [
        item for item in coverage.get("items", [])
        if item.get("security_id") == manifest.get("security_id")
    ]
    if len(matches) != 1:
        raise CommonStockEvalError("COMMON_STOCK_EVAL_COVERAGE_ITEM_MISSING")
    item = matches[0]
    if item.get("report_ref") != binding.get("report_ref") or item.get("report_hash") != report_hash:
        raise CommonStockEvalError("COMMON_STOCK_EVAL_COVERAGE_REPORT_MISMATCH")
    result_path = eval_dir / "eval/result.json"
    try:
        eval_ref = str(result_path.relative_to(run_dir))
    except ValueError as exc:
        raise CommonStockEvalError("COMMON_STOCK_EVAL_OUTPUT_OUTSIDE_RUN") from exc
    item.update({
        "eval_status": result["status"],
        "eval_ref": eval_ref,
        "eval_result_hash": result["result_hash"],
        "evaluated_report_hash": report_hash,
    })
    coverage["coverage_hash"] = legacy_envelope_hash(coverage, hash_field="coverage_hash")
    validate_research_coverage(coverage, handoff=handoff, council_request=council_request)
    coverage_path.write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def finalize_common_stock_eval_job(
    *, eval_dir: Path, semantic_result_path: Path,
    actual_model: str | None = None, input_binding_hash: str | None = None,
) -> dict[str, Any]:
    """验证 dev_eval 原始结果并生成 result.json/report.md。"""

    eval_dir = Path(eval_dir).resolve()
    manifest = _validated_eval_manifest(eval_dir)
    draft = _read_object(Path(semantic_result_path).resolve())
    invocation_path = eval_dir / "invocation/invocation-manifest.json"
    if invocation_path.is_file():
        invocation = _read_object(invocation_path)
        try:
            verify_legacy_envelope_hash(invocation, hash_field="manifest_hash", location="invocation/invocation-manifest.json")
        except HashContractError as exc:
            raise CommonStockEvalError(f"COMMON_STOCK_EVAL_INVOCATION_BINDING_INVALID:{exc}") from exc
        if (invocation.get("input_hash") != manifest["input_hash"]
                or invocation.get("eval_id") != manifest["eval_id"]
                or invocation.get("agent") != "dev_eval"
                or invocation.get("model") != actual_model):
            raise CommonStockEvalError("COMMON_STOCK_EVAL_INVOCATION_BINDING_INVALID")
    result = envelope_common_stock_eval_draft(draft, manifest=manifest,
                                             actual_model=actual_model,
                                             input_binding_hash=input_binding_hash)
    _write_object(eval_dir / "eval" / "result.json", result)
    lines = [
        f"# {result['security_id']} 普通股研究 Eval", "",
        f"- 状态：`{result['status']}`", f"- 模型：`{result['model']}`", "",
    ]
    for name in DIMENSIONS:
        item = result["dimensions"][name]
        lines.extend([
            f"## {name}", "", f"- 结果：`{item['status']}`；分数：`{item['grade']}`",
            f"- 理由：{item['rationale']}", "",
        ])
    report_path = eval_dir / "eval" / "report.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")
    _attach_eval_to_coverage(eval_dir=eval_dir, manifest=manifest, result=result)
    return result


def launch_common_stock_eval(
    repository_root: Path, *, eval_dir: Path, model: str = DEFAULT_GRADER_MODEL,
    codex_binary: str = "codex", timeout_seconds: int = 900,
) -> tuple[dict[str, Any], int]:
    """通过现有 Codex 原生 Agent 派发运行一次真实聚焦 Eval。"""

    from product.runtime.nested_codex import build_verified_nested_codex_command, integrity_snapshot

    repository_root = Path(repository_root).resolve()
    eval_dir = Path(eval_dir).resolve()
    manifest = _validated_eval_manifest(eval_dir)
    if manifest.get("semantic_output_delivery") != EVAL_DRAFT_VERSION:
        raise CommonStockEvalError("COMMON_STOCK_EVAL_LEGACY_WRITE_RETIRED")
    if model != manifest.get("grader_model", "gpt-5.6-terra"):
        raise CommonStockEvalError("COMMON_STOCK_EVAL_MODEL_MISMATCH")
    import tomllib
    with (repository_root / ".codex/agents/dev_eval.toml").open("rb") as stream:
        if tomllib.load(stream).get("model") != model:
            raise CommonStockEvalError("COMMON_STOCK_EVAL_AGENT_MODEL_MISMATCH")
    invocation_dir = eval_dir / "invocation"
    if invocation_dir.exists():
        raise CommonStockEvalError("COMMON_STOCK_EVAL_ALREADY_LAUNCHED")
    invocation_dir.mkdir()
    runtime_root = eval_dir / ".codex-runtime"
    sqlite_home, log_dir, tmp_dir = (
        runtime_root / "sqlite", runtime_root / "logs", runtime_root / "tmp"
    )
    for path in (sqlite_home, log_dir, tmp_dir):
        path.mkdir(parents=True, exist_ok=False)
    prompt = f"""你是普通股研究 Eval 的父调度线程，不执行评分。
使用 Agent 工具启动且只启动一个 dev_eval，task_name=grade_common_stock_report，fork_turns=none，message 使用以下启动提示：
{build_common_stock_eval_dispatch_message(eval_dir)}
等待 dev_eval 结束。评分结果由 Hook 直接验证和保存；不得自行评分、改写或补充结果。
最后只返回：{{"stage":"COMMON_STOCK_RESEARCH_EVAL","eval_id":"{manifest['eval_id']}","evaluated":1}}。
"""
    prompt_path = invocation_dir / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    parent_schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object", "additionalProperties": False,
        "required": ["stage", "eval_id", "evaluated"],
        "properties": {
            "stage": {"type": "string", "const": "COMMON_STOCK_RESEARCH_EVAL"},
            "eval_id": {"type": "string", "const": manifest["eval_id"]},
            "evaluated": {"type": "integer", "const": 1},
        },
    }
    schema_path = invocation_dir / "parent-output.schema.json"
    _write_object(schema_path, parent_schema)
    events_path = invocation_dir / "codex-events.jsonl"
    hook_events_path = invocation_dir / "subagent-events.jsonl"
    dispatch_path = invocation_dir / "subagent-dispatches.jsonl"
    stderr_path = invocation_dir / "codex-stderr.log"
    raw_final_path = tmp_dir / "final-message.json"
    command = build_verified_nested_codex_command(
        runtime_binding_path=invocation_dir / "codex-runtime.json",
        codex_binary=codex_binary, product_root=repository_root, run_dir=eval_dir,
        model=model, sqlite_home=sqlite_home, log_dir=log_dir,
        final_message_path=raw_final_path,
        hook_recorder_path=repository_root / "product/runtime/codex_hook_recorder.py",
        output_schema_path=schema_path, hook_agent_matcher="^dev_eval$",
    )
    agent_path = repository_root / ".codex/agents/dev_eval.toml"
    skill_path = repository_root / ".agents/skills/runtime-eval-grading/SKILL.md"
    invocation_manifest = {
        "schema_version": "common-stock-research-eval-invocation/1.0.0",
        "eval_id": manifest["eval_id"],
        "run_id": manifest["run_id"],
        "input_hash": manifest["input_hash"],
        "agent": "dev_eval",
        "agent_config_hash": file_hash(agent_path),
        "skill": "runtime-eval-grading",
        "skill_hash": file_hash(skill_path),
        "model": model,
        "prompt_hash": file_hash(prompt_path),
        "output_schema_hash": file_hash(schema_path),
        "hook_recorder_hash": file_hash(
            repository_root / "product/runtime/codex_hook_recorder.py"
        ),
        "command": command,
    }
    invocation_manifest["manifest_hash"] = legacy_envelope_hash(invocation_manifest, hash_field="manifest_hash")
    _write_object(invocation_dir / "invocation-manifest.json", invocation_manifest)
    environment = dict(os.environ)
    environment.update({
        "TMPDIR": str(tmp_dir), "PYTHONDONTWRITEBYTECODE": "1",
        "STOCK_AGENT_RUN_DIR": str(eval_dir),
        "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(hook_events_path),
        "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(dispatch_path),
        "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": "dev_eval",
        "STOCK_AGENT_COMMON_STOCK_EVAL": EVAL_RUNTIME_VERSION,
        "STOCK_AGENT_COMMON_STOCK_EVAL_MODEL": model,
    })
    before = integrity_snapshot(repository_root)
    started_at = _utc_now()
    try:
        process = subprocess.run(
            command, input=prompt, text=True, cwd=repository_root, env=environment,
            capture_output=True, timeout=timeout_seconds, check=False,
        )
        process_code, stdout, stderr, timed_out = (
            process.returncode, process.stdout, process.stderr, False
        )
    except subprocess.TimeoutExpired as exc:
        process_code, timed_out = 124, True
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
    events_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    failure_code = None
    try:
        if timed_out:
            raise CommonStockEvalError("COMMON_STOCK_EVAL_TIMEOUT")
        if process_code != 0:
            raise CommonStockEvalError("COMMON_STOCK_EVAL_CODEX_PROCESS_FAILED")
        final_message = _read_object(raw_final_path)
        _write_object(invocation_dir / "final-message.json", final_message)
        if final_message != {
            "stage": "COMMON_STOCK_RESEARCH_EVAL",
            "eval_id": manifest["eval_id"], "evaluated": 1,
        }:
            raise CommonStockEvalError("COMMON_STOCK_EVAL_FINAL_MESSAGE_INVALID")
        result = _read_object(eval_dir / "eval/result.json")
        validate_common_stock_eval_result(result, manifest=manifest)
        status = "PASSED" if result["status"] == "PASS" else "FAILED"
        if status != "PASSED":
            failure_code = "COMMON_STOCK_RESEARCH_QUALITY_FAILED"
    except (OSError, ValueError, KeyError, CommonStockEvalError) as exc:
        status = "FAILED"
        failure_code = str(exc).split(":", 1)[0]
        result = None
    after = integrity_snapshot(repository_root)
    process_result = {
        "schema_version": EVAL_RUNTIME_VERSION,
        "eval_id": manifest["eval_id"], "run_id": manifest["run_id"],
        "started_at": started_at, "completed_at": _utc_now(),
        "process_exit_code": process_code, "timed_out": timed_out,
        "status": status, "failure_code": failure_code,
        "source_integrity_unchanged": before == after,
    }
    _write_object(invocation_dir / "process-result.json", process_result)
    summary = {
        "status": status, "eval_id": manifest["eval_id"],
        "security_id": manifest["security_id"], "failure_code": failure_code,
    }
    return summary, 0 if status == "PASSED" and before == after else 7
