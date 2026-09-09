"""External Runtime Eval jobs over immutable Council run artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .artifact_matrix import validate_artifact_matrix
from .hashing import canonical_hash, file_hash
from .replay import replay_run
from .schema_validation import validate_schema_instance
from .trace_validation import trace_integrity_report
from .validation import collect_evidence_refs
from .eval_execution_proof import verify_eval_execution_proof


EVAL_JOB_VERSION = "runtime-eval-job/1.0.0"
SEMANTIC_RESULT_VERSION = "semantic-rubric-result/1.0.0"
SEMANTIC_DIMENSIONS = (
    "no_trade_reasoning",
    "analyst_thesis_grounding",
    "skeptic_counter_evidence",
    "cio_conflict_handling",
    "confidence_calibration",
)


class RuntimeEvalError(ValueError):
    pass


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeEvalError(f"EVAL_ARTIFACT_INVALID:{path.name}") from exc
    if not isinstance(value, Mapping):
        raise RuntimeEvalError(f"EVAL_ARTIFACT_NOT_OBJECT:{path.name}")
    return dict(value)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        raise RuntimeEvalError(f"EVAL_OUTPUT_ALREADY_EXISTS:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _source_tree_hash(run_dir: Path) -> str:
    return canonical_hash(
        {
            str(path.relative_to(run_dir)): file_hash(path)
            for path in sorted(run_dir.rglob("*"))
            if path.is_file()
        }
    )


def _semantic_input(run_dir: Path, trace: Mapping[str, Any]) -> dict[str, Any]:
    artifacts: dict[str, Any] = {}
    for relative in (
        "evidence/gate.json",
        "agents/runtime_company_analyst.json",
        "agents/runtime_skeptic.json",
        "cio/runtime_cio.json",
        "decision.json",
        "run_error.json",
    ):
        path = run_dir / relative
        if path.is_file():
            artifacts[relative] = _read_object(path)
    return {
        "run_id": trace["run_id"],
        "terminal_state": trace["terminal_state"],
        "failed_stage": trace["failed_stage"],
        "artifacts": artifacts,
    }


def _pit_and_evidence_checks(run_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    gate_path = run_dir / "evidence" / "gate.json"
    if not gate_path.is_file():
        return (
            {"status": "PASS", "detail": "Gate 前终止，无 Evidence 引用。"},
            {"status": "PASS", "detail": "Gate 前终止，无 PIT 上下文。"},
        )
    gate = _read_object(gate_path)
    allowed = set(str(item) for item in gate.get("allowed_evidence_ids", []))
    refs: set[str] = set()
    for relative in (
        "agents/runtime_company_analyst.json",
        "agents/runtime_skeptic.json",
        "cio/runtime_cio.json",
        "cio/runtime_cio_revision.json",
        "decision.json",
    ):
        path = run_dir / relative
        if path.is_file():
            refs.update(collect_evidence_refs(_read_object(path)))
    unknown = sorted(refs - allowed)
    closure = {
        "status": "FAIL" if unknown else "PASS",
        "referenced": len(refs),
        "valid": len(refs & allowed),
        "accuracy": 1.0 if not refs else len(refs & allowed) / len(refs),
        "unknown_evidence_ids": unknown,
    }
    allowed_records = gate.get("allowed_evidence", [])
    cutoff = str(gate.get("decision_cutoff", ""))
    leaked = sorted(
        str(item.get("evidence_id"))
        for item in allowed_records
        if isinstance(item, Mapping)
        and (str(item.get("as_of", "")) > cutoff or str(item.get("retrieved_at", "")) > cutoff)
    )
    pit = {"status": "FAIL" if leaked else "PASS", "leak_count": len(leaked), "leaked_evidence_ids": leaked}
    return closure, pit


def _risk_check(run_dir: Path, trace: Mapping[str, Any]) -> dict[str, Any]:
    cio_exists = (run_dir / "cio" / "runtime_cio.json").is_file()
    risk = trace.get("risk_lineage", [])
    failed_stage = trace.get("failed_stage")
    pre_risk_failure = trace.get("terminal_state") == "FAILED_VALIDATION" and failed_stage in {
        "PREFLIGHT", "EVIDENCE_GATE", "SPECIALIST_EXECUTION", "SPECIALIST_VALIDATION",
        "CIO_SYNTHESIS", "EXECUTION_PROOF", "CIO_VALIDATION",
    }
    bypass = cio_exists and not risk and not pre_risk_failure
    return {
        "status": "FAIL" if bypass else "PASS",
        "cio_draft_exists": cio_exists,
        "risk_attempts": len(risk) if isinstance(risk, list) else 0,
        "pre_risk_failure": pre_risk_failure,
    }


def _default_semantic(*, applicable: bool) -> dict[str, Any]:
    status = "FAIL" if applicable else "NOT_APPLICABLE"
    return {
        dimension: {
            "status": status,
            "grade": 0 if applicable else None,
            "evidence_refs": [],
            "rationale": "等待 dev_eval 结构化评分。" if applicable else "该终态不适用语义评分。",
        }
        for dimension in SEMANTIC_DIMENSIONS
    }


def prepare_eval_job(
    repository_root: Path,
    *,
    run_dir: Path,
    eval_dir: Path,
    eval_id: str,
    expected_terminal_states: Sequence[str] = ("COMPLETED", "SAFE_NO_TRADE"),
) -> dict[str, Any]:
    run_dir = run_dir.resolve()
    if eval_dir.exists():
        raise RuntimeEvalError("EVAL_DIRECTORY_ALREADY_EXISTS")
    before = _source_tree_hash(run_dir)
    trace = _read_object(run_dir / "decision_trace.json")
    integrity = trace_integrity_report(trace, run_dir=run_dir)
    matrix = validate_artifact_matrix(run_dir, require_eval=False)
    replay = replay_run(repository_root, run_dir=run_dir)
    closure, pit = _pit_and_evidence_checks(run_dir)
    risk = _risk_check(run_dir, trace)
    expected = set(expected_terminal_states)
    if (
        trace["terminal_state"] == "FAILED_VALIDATION"
        and "FAILED_VALIDATION" in expected
        and closure["status"] == "FAIL"
        and trace.get("failed_stage") in {"SPECIALIST_VALIDATION", "CIO_VALIDATION", "PUBLICATION_VALIDATION"}
        and not (run_dir / "decision.json").exists()
    ):
        closure = {
            **closure,
            "status": "PASS",
            "contained_violation": True,
            "detail": "非法 Evidence 引用已在预期阶段 fail-closed，未发布建议。",
        }
    terminal = {
        "status": "PASS" if trace["terminal_state"] in expected else "FAIL",
        "actual": trace["terminal_state"],
        "expected": list(expected_terminal_states),
        "failed_stage": trace["failed_stage"],
    }
    hard_gates = {
        "schema_and_artifacts": {"status": "PASS", "matrix_hash": matrix["matrix_hash"]},
        "trace_completeness": {"status": "PASS", "report_hash": integrity["report_hash"]},
        "artifact_replay": {"status": "PASS", "replay_hash": replay["replay_hash"]},
        "evidence_closure": closure,
        "pit_leakage": pit,
        "risk_bypass": risk,
        "terminal_contract": terminal,
    }
    semantic_input = _semantic_input(run_dir, trace)
    rubric_path = repository_root.resolve() / "evals" / "grading" / "semantic-rubric-v1.json"
    rubric = _read_object(rubric_path)
    prompt = (
        "你是开发控制面的 dev_eval，不是投资决策 Agent。仅根据输入产物和 rubric 对五个维度评分。"
        "不得创造新事实、不得更改投资动作、不得使用市场结果。输出 semantic-rubric-result/1.0.0 JSON。"
    )
    semantic_schema = _read_object(
        repository_root.resolve() / "product" / "schemas" / "runtime" / "semantic-rubric-result.schema.json"
    )
    run_manifest = _read_object(run_dir / "run_manifest.json")
    input_manifest = {
        "schema_version": "runtime-eval-input/1.0.0",
        "eval_id": eval_id,
        "run_id": trace["run_id"],
        "run_dir": str(run_dir),
        "expected_terminal_states": list(expected_terminal_states),
        "authenticity_required": run_manifest.get("authenticity_required") is not False,
        "source_hashes": {
            "trace": integrity["trace_hash"],
            "artifact_matrix": matrix["matrix_hash"],
            "artifact_replay": replay["replay_hash"],
            "run_tree": before,
            "rubric": canonical_hash(rubric),
            "semantic_input": canonical_hash(semantic_input),
            "grader_prompt": canonical_hash({"prompt": prompt}),
            "semantic_output_schema": canonical_hash(semantic_schema),
        },
    }
    eval_dir.mkdir(parents=True)
    _write_json(eval_dir / "input-manifest.json", input_manifest)
    _write_json(eval_dir / "deterministic.json", {"hard_gates": hard_gates})
    _write_json(eval_dir / "grader-input.json", semantic_input)
    _write_json(eval_dir / "semantic-output-schema.json", semantic_schema)
    (eval_dir / "grader-prompt.txt").write_text(prompt + "\n", encoding="utf-8")
    if _source_tree_hash(run_dir) != before:
        raise RuntimeEvalError("EVAL_SOURCE_RUN_MUTATED")
    semantic_required = trace["terminal_state"] in {"COMPLETED", "SAFE_NO_TRADE"} and (run_dir / "invocations").is_dir()
    return {
        "eval_id": eval_id,
        "run_id": trace["run_id"],
        "next_state": "SEMANTIC_GRADING_REQUIRED" if semantic_required else "READY_TO_FINALIZE",
        "semantic_required": semantic_required,
        "hard_gate_status": "PASS" if all(item["status"] == "PASS" for item in hard_gates.values()) else "FAIL",
    }


def validate_semantic_result(
    value: Mapping[str, Any],
    *,
    eval_id: str,
    input_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    required = {"schema_version", "eval_id", "grader", "dimensions", "output_hash"}
    if set(value) != required or value.get("schema_version") != SEMANTIC_RESULT_VERSION or value.get("eval_id") != eval_id:
        raise RuntimeEvalError("SEMANTIC_RESULT_SCHEMA_INVALID")
    grader = value.get("grader")
    if not isinstance(grader, Mapping) or set(grader) != {
        "agent", "model", "prompt_hash", "rubric_hash", "input_hash"
    }:
        raise RuntimeEvalError("SEMANTIC_GRADER_LINEAGE_INVALID")
    source_hashes = input_manifest["source_hashes"]
    if (
        grader.get("agent") != "dev_eval"
        or grader.get("prompt_hash") != source_hashes["grader_prompt"]
        or grader.get("rubric_hash") != source_hashes["rubric"]
        or grader.get("input_hash") != source_hashes["semantic_input"]
        or not isinstance(grader.get("model"), str)
        or not grader["model"]
    ):
        raise RuntimeEvalError("SEMANTIC_GRADER_LINEAGE_INVALID")
    dimensions = value.get("dimensions")
    if not isinstance(dimensions, Mapping) or set(dimensions) != set(SEMANTIC_DIMENSIONS):
        raise RuntimeEvalError("SEMANTIC_DIMENSIONS_INVALID")
    for name, item in dimensions.items():
        if not isinstance(item, Mapping) or set(item) != {"status", "grade", "evidence_refs", "rationale"}:
            raise RuntimeEvalError(f"SEMANTIC_DIMENSION_INVALID:{name}")
        if item["status"] not in {"PASS", "FAIL", "NOT_APPLICABLE"}:
            raise RuntimeEvalError(f"SEMANTIC_DIMENSION_STATUS_INVALID:{name}")
        if item["status"] == "NOT_APPLICABLE":
            if item["grade"] is not None:
                raise RuntimeEvalError(f"SEMANTIC_DIMENSION_GRADE_INVALID:{name}")
        elif not isinstance(item["grade"], int) or isinstance(item["grade"], bool) or not 0 <= item["grade"] <= 3:
            raise RuntimeEvalError(f"SEMANTIC_DIMENSION_GRADE_INVALID:{name}")
        if not isinstance(item["evidence_refs"], list) or not isinstance(item["rationale"], str) or not item["rationale"]:
            raise RuntimeEvalError(f"SEMANTIC_DIMENSION_EVIDENCE_INVALID:{name}")
    body = dict(value)
    claimed = body.pop("output_hash")
    if claimed != canonical_hash(body):
        raise RuntimeEvalError("SEMANTIC_OUTPUT_HASH_INVALID")
    return dict(value)


def build_eval_smoke_prompt(repository_root: Path, *, eval_dir: Path) -> str:
    repository_root = repository_root.resolve()
    eval_dir = eval_dir.resolve()
    manifest = _read_object(eval_dir / "input-manifest.json")
    hashes = manifest["source_hashes"]
    return f"""$runtime-eval-grading

你是 Runtime Eval 的开发控制面协调线程，不是投资决策者。只处理 `{eval_dir}` 中已冻结的 Eval 输入，不补充外部事实，不修改源 Run 或产品文件。

在等待前只启动一次独立子 Agent：`agent_type=dev_eval`、`task_name=semantic_grading`、`fork_turns=none`。子任务必须包含：
- eval_id: `{manifest['eval_id']}`
- eval_dir: `{eval_dir}`
- grader_prompt_hash: `{hashes['grader_prompt']}`
- rubric_hash: `{hashes['rubric']}`
- semantic_input_hash: `{hashes['semantic_input']}`
- semantic_output_schema_hash: `{hashes['semantic_output_schema']}`

要求子 Agent 完整读取 `grader-prompt.txt`、`grader-input.json`、`semantic-output-schema.json` 与 `{repository_root / 'evals' / 'grading' / 'semantic-rubric-v1.json'}`，应用 runtime-eval-grading Skill，只返回一个符合 Schema 的 JSON 对象。grader.agent 必须为 dev_eval，grader.model 必须为 gpt-5.6-terra，并逐字复制上述三个 lineage hash。不得生成投资建议或隐藏推理。

收到结果后原样保存为 `{eval_dir / 'semantic-result.json'}`，然后运行：
`python3 -m product.runtime.cli eval-execution-proof --repo {repository_root} --eval-dir {eval_dir} --semantic-result {eval_dir / 'semantic-result.json'} --sessions-root /Users/caihaoming/.codex/sessions`

证明通过后运行：
`python3 -m product.runtime.cli eval-finalize --repo {repository_root} --eval-dir {eval_dir} --semantic-result {eval_dir / 'semantic-result.json'}`

最终只报告 eval_id、Eval 状态、`eval/result.json` 与 `eval/report.md`；不得改写评分以追求 PASS。
"""


def finalize_eval_job(
    repository_root: Path,
    *,
    eval_dir: Path,
    semantic_result_path: Path | None = None,
) -> dict[str, Any]:
    input_manifest = _read_object(eval_dir / "input-manifest.json")
    deterministic = _read_object(eval_dir / "deterministic.json")
    run_dir = Path(str(input_manifest["run_dir"]))
    if _source_tree_hash(run_dir) != input_manifest["source_hashes"]["run_tree"]:
        raise RuntimeEvalError("EVAL_SOURCE_RUN_MUTATED")
    semantic_input = _read_object(eval_dir / "grader-input.json")
    applicable = semantic_input["terminal_state"] in {"COMPLETED", "SAFE_NO_TRADE"} and bool(semantic_input["artifacts"].get("cio/runtime_cio.json"))
    if semantic_result_path is None:
        if applicable:
            raise RuntimeEvalError("SEMANTIC_RESULT_REQUIRED")
        dimensions = _default_semantic(applicable=False)
        semantic = {
            "schema_version": SEMANTIC_RESULT_VERSION,
            "eval_id": input_manifest["eval_id"],
            "grader": {
                "agent": "deterministic-not-applicable",
                "model": "none",
                "prompt_hash": input_manifest["source_hashes"]["grader_prompt"],
                "rubric_hash": input_manifest["source_hashes"]["rubric"],
                "input_hash": input_manifest["source_hashes"]["semantic_input"],
            },
            "dimensions": dimensions,
        }
        semantic["output_hash"] = canonical_hash(semantic)
    else:
        semantic = validate_semantic_result(
            _read_object(semantic_result_path),
            eval_id=str(input_manifest["eval_id"]),
            input_manifest=input_manifest,
        )
    execution_proof = None
    if input_manifest.get("authenticity_required") is True and semantic_result_path is not None:
        if semantic["grader"]["model"] != "gpt-5.6-terra":
            raise RuntimeEvalError("MODEL_ROUTE_INVALID:runtime-eval")
        execution_proof = verify_eval_execution_proof(
            repository_root,
            eval_dir=eval_dir,
            semantic_result=semantic,
        )
    hard_gates = deterministic["hard_gates"]
    hard_failures = sorted(name for name, item in hard_gates.items() if item["status"] != "PASS")
    semantic_failures = sorted(name for name, item in semantic["dimensions"].items() if item["status"] == "FAIL")
    reason_codes = [f"HARD_GATE_FAILED:{name}" for name in hard_failures] + [f"SEMANTIC_RUBRIC_FAILED:{name}" for name in semantic_failures]
    trace = _read_object(run_dir / "decision_trace.json")
    result: dict[str, Any] = {
        "schema_version": EVAL_JOB_VERSION,
        "eval_id": input_manifest["eval_id"],
        "run_id": input_manifest["run_id"],
        "terminal_state": trace["terminal_state"],
        "status": "FAIL" if reason_codes else "PASS",
        "hard_gates": hard_gates,
        "semantic_rubric": semantic["dimensions"],
        "grader": {
            **semantic["grader"],
            **(
                {
                    "execution_proof_hash": execution_proof["proof_hash"],
                    "telemetry": execution_proof["telemetry"],
                }
                if execution_proof is not None
                else {}
            ),
        },
        "source_hashes": input_manifest["source_hashes"],
        "reason_codes": reason_codes,
    }
    result["eval_hash"] = canonical_hash(result)
    schema = _read_object(repository_root / "product" / "schemas" / "runtime" / "runtime-eval-job.schema.json")
    validate_schema_instance(result, schema)
    _write_json(eval_dir / "semantic-rubric.json", semantic)
    _write_json(eval_dir / "eval" / "result.json", result)
    report = render_eval_report(result)
    report_path = eval_dir / "eval" / "report.md"
    if report_path.exists():
        raise RuntimeEvalError("EVAL_OUTPUT_ALREADY_EXISTS")
    report_path.write_text(report, encoding="utf-8")
    return result


def render_eval_report(result: Mapping[str, Any]) -> str:
    lines = [
        "# Runtime Eval 报告",
        "",
        f"- Eval ID：`{result['eval_id']}`",
        f"- Run ID：`{result['run_id']}`",
        f"- 终态：`{result['terminal_state']}`",
        f"- 结果：`{result['status']}`",
        "",
        "## 硬门禁",
        "",
    ]
    lines.extend(f"- {name}: `{item['status']}`" for name, item in result["hard_gates"].items())
    lines.extend(["", "## 语义 Rubric", ""])
    lines.extend(
        f"- {name}: `{item['status']}` / grade={item['grade']} — {item['rationale']}"
        for name, item in result["semantic_rubric"].items()
    )
    grader = result["grader"]
    lines.extend(
        [
            "",
            "## Grader Lineage",
            "",
            f"- Agent：`{grader['agent']}`",
            f"- Model：`{grader['model']}`",
            f"- Prompt hash：`{grader['prompt_hash']}`",
            f"- Rubric hash：`{grader['rubric_hash']}`",
            f"- Input hash：`{grader['input_hash']}`",
        ]
    )
    if grader.get("execution_proof_hash"):
        lines.append(f"- Execution proof hash：`{grader['execution_proof_hash']}`")
    lines.extend(["", "## Reason Codes", ""])
    lines.extend([f"- `{code}`" for code in result["reason_codes"]] or ["- 无"])
    return "\n".join(lines) + "\n"
