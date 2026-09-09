"""Deterministic comparison of repeated semantic grader outputs to human labels."""

from __future__ import annotations

import json
import tempfile
import tomllib
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.runtime.execution_proof import (
    _final_structured_output,
    _function_calls,
    _is_protected_dispatch_message,
    _load_jsonl,
    _message_texts,
    _session_meta,
    _turn_context,
)
from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.schema_validation import validate_schema_instance


EXPECTED_CALIBRATION_GRADER = {
    "agent": "dev_eval",
    "model": "gpt-5.6-terra",
    "grader_version": "runtime-eval-grading/1.0.0",
}


def _rollout_bounds(records: Sequence[Mapping[str, Any]]) -> tuple[str, str]:
    timestamps = [
        str(record["timestamp"])
        for record in records
        if isinstance(record.get("timestamp"), str)
    ]
    if len(timestamps) < 2:
        raise ValueError("CALIBRATION_EXECUTION_TIMESTAMPS_MISSING")
    try:
        parsed = [datetime.fromisoformat(item.replace("Z", "+00:00")) for item in timestamps]
    except ValueError as exc:
        raise ValueError("CALIBRATION_EXECUTION_TIMESTAMP_INVALID") from exc
    return timestamps[parsed.index(min(parsed))], timestamps[parsed.index(max(parsed))]


def build_calibration_execution_proof(
    repository_root: Path,
    *,
    case_id: str,
    repeat: int,
    grader_output_path: Path,
    parent_rollout: Path,
    child_rollout: Path,
    prompt_path: Path,
    input_path: Path,
) -> dict[str, Any]:
    """Build a replayable proof from one real, isolated dev_eval child session."""

    output = json.loads(grader_output_path.read_text(encoding="utf-8"))
    prompt_text = prompt_path.read_text(encoding="utf-8").rstrip("\n")
    input_value = json.loads(input_path.read_text(encoding="utf-8"))
    prompt_hash = canonical_hash({"prompt": prompt_text})
    input_hash = canonical_hash(input_value)
    parent_records = _load_jsonl(parent_rollout)
    child_records = _load_jsonl(child_rollout)
    parent_meta = _session_meta(parent_records)
    child_meta = _session_meta(child_records)
    parent_id = str(parent_meta.get("id", ""))
    child_id = str(child_meta.get("id", ""))
    calls = [
        call for call in _function_calls(parent_records)
        if call.get("namespace") == "collaboration" and call.get("name") == "spawn_agent"
    ]
    if len(calls) != 1 or calls[0].get("arguments", {}).get("agent_type") != "dev_eval":
        raise ValueError("CALIBRATION_DEV_EVAL_DISPATCH_INVALID")
    if child_meta.get("parent_thread_id") != parent_id or child_meta.get("agent_role") != "dev_eval":
        raise ValueError("CALIBRATION_DEV_EVAL_SESSION_INVALID")
    if _turn_context(child_records).get("model") != "gpt-5.6-terra":
        raise ValueError("CALIBRATION_MODEL_ROUTE_INVALID")
    agent_path = repository_root / ".codex" / "agents" / "dev_eval.toml"
    skill_path = repository_root / ".agents" / "skills" / "runtime-eval-grading" / "SKILL.md"
    with agent_path.open("rb") as handle:
        agent = tomllib.load(handle)
    instructions = str(agent.get("developer_instructions", ""))
    if not instructions or instructions not in "\n".join(_message_texts(child_records, role="developer")):
        raise ValueError("CALIBRATION_DEV_EVAL_INSTRUCTIONS_NOT_LOADED")
    if agent.get("skills", {}).get("config") != [
        {"path": ".agents/skills/runtime-eval-grading", "enabled": True}
    ]:
        raise ValueError("CALIBRATION_GRADER_SKILL_CONFIG_INVALID")
    final_document = _final_structured_output(child_records, agent_name="dev_eval")
    if final_document.get("schema_version") == "calibration-grader-batch/1.0.0":
        cases = final_document.get("cases", {})
        if not isinstance(cases, Mapping) or not isinstance(cases.get(case_id), Mapping):
            raise ValueError("CALIBRATION_BATCH_CASE_MISSING")
        final = dict(cases[case_id])
    else:
        final = final_document
    if canonical_hash(final) != canonical_hash(output):
        raise ValueError("CALIBRATION_GRADER_OUTPUT_MISMATCH")
    child_user = "\n".join(_message_texts(child_records, role="user"))
    parent_user = "\n".join(_message_texts(parent_records, role="user"))
    protected = _is_protected_dispatch_message(calls[0].get("arguments", {}).get("message"))
    explicit = all(item in child_user for item in (case_id, prompt_hash, input_hash))
    parent_bound = all(item in parent_user for item in (case_id, prompt_hash, input_hash))
    structured = (
        output.get("grader", {}).get("prompt_hash") == prompt_hash
        and output.get("grader", {}).get("input_hash") == input_hash
    )
    if not explicit and not (protected and (structured or parent_bound)):
        raise ValueError("CALIBRATION_TASK_BINDING_MISSING")
    started_at, completed_at = _rollout_bounds([*parent_records, *child_records])
    proof: dict[str, Any] = {
        "schema_version": "calibration-grader-execution-proof/1.0.0",
        "case_id": case_id,
        "repeat": repeat,
        "parent_session_id": parent_id,
        "session_id": child_id,
        "agent": "dev_eval",
        "model": "gpt-5.6-terra",
        "agent_hash": file_hash(agent_path),
        "skill_hash": file_hash(skill_path),
        "prompt_hash": prompt_hash,
        "input_hash": input_hash,
        "output_hash": output["output_hash"],
        "prompt_artifact": {"path": str(prompt_path.resolve()), "sha256": file_hash(prompt_path)},
        "input_artifact": {"path": str(input_path.resolve()), "sha256": file_hash(input_path)},
        "output_artifact": {"path": str(grader_output_path.resolve()), "sha256": file_hash(grader_output_path)},
        "parent_rollout": {"path": str(parent_rollout.resolve()), "sha256": file_hash(parent_rollout)},
        "child_rollout": {"path": str(child_rollout.resolve()), "sha256": file_hash(child_rollout)},
        "execution_events": [
            {"type": "DEV_EVAL_DISPATCHED", "session_id": parent_id, "at": started_at},
            {"type": "DEV_EVAL_COMPLETED", "session_id": child_id, "at": completed_at},
        ],
        "started_at": started_at,
        "completed_at": completed_at,
        "task_binding_method": (
            "plaintext_child_input"
            if explicit
            else (
                "protected_dispatch_plus_structured_output"
                if structured
                else "protected_dispatch_plus_parent_input"
            )
        ),
    }
    proof["proof_hash"] = canonical_hash(proof)
    return proof


def verify_calibration_execution_proof(
    repository_root: Path,
    *,
    proof_path: Path,
    case_id: str,
    repeat: int,
    grader_output_path: Path,
) -> dict[str, Any]:
    proof = json.loads(proof_path.read_text(encoding="utf-8"))
    body = dict(proof)
    if body.pop("proof_hash", None) != canonical_hash(body):
        raise ValueError(f"CALIBRATION_EXECUTION_PROOF_HASH_INVALID:{case_id}")
    expected_output_hash = file_hash(grader_output_path)
    output = json.loads(grader_output_path.read_text(encoding="utf-8"))
    expected = {
        "case_id": case_id,
        "repeat": repeat,
        "agent": "dev_eval",
        "model": "gpt-5.6-terra",
        "agent_hash": file_hash(repository_root / ".codex" / "agents" / "dev_eval.toml"),
        "skill_hash": file_hash(repository_root / ".agents" / "skills" / "runtime-eval-grading" / "SKILL.md"),
        "output_hash": output.get("output_hash"),
    }
    if any(proof.get(key) != value for key, value in expected.items()):
        raise ValueError(f"CALIBRATION_EXECUTION_PROOF_LINEAGE_INVALID:{case_id}")
    if proof.get("output_artifact") != {"path": str(grader_output_path.resolve()), "sha256": expected_output_hash}:
        raise ValueError(f"CALIBRATION_EXECUTION_OUTPUT_BINDING_INVALID:{case_id}")
    for name in ("parent_rollout", "child_rollout"):
        record = proof.get(name, {})
        path = Path(str(record.get("path", ""))).resolve()
        if not path.is_file() or file_hash(path) != record.get("sha256"):
            raise ValueError(f"CALIBRATION_EXECUTION_ROLLOUT_INVALID:{case_id}:{name}")
    for name in ("prompt_artifact", "input_artifact"):
        record = proof.get(name, {})
        path = Path(str(record.get("path", ""))).resolve()
        if not path.is_file() or file_hash(path) != record.get("sha256"):
            raise ValueError(f"CALIBRATION_EXECUTION_SOURCE_INVALID:{case_id}:{name}")
    rebuilt = build_calibration_execution_proof(
        repository_root,
        case_id=case_id,
        repeat=repeat,
        grader_output_path=grader_output_path,
        parent_rollout=Path(proof["parent_rollout"]["path"]),
        child_rollout=Path(proof["child_rollout"]["path"]),
        prompt_path=Path(proof["prompt_artifact"]["path"]),
        input_path=Path(proof["input_artifact"]["path"]),
    )
    if rebuilt != proof:
        raise ValueError(f"CALIBRATION_EXECUTION_PROOF_REPLAY_MISMATCH:{case_id}")
    return proof


def evaluate_calibration(
    labels: Mapping[str, Any],
    *,
    grader_runs: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    cases = labels.get("cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("CALIBRATION_LABELS_INVALID")
    total = 0
    matched = 0
    unstable: list[str] = []
    for case in cases:
        case_id = str(case["case_id"])
        runs = list(grader_runs.get(case_id, []))
        if len(runs) < 2:
            raise ValueError(f"CALIBRATION_REPEAT_MISSING:{case_id}")
        labels_by_dimension = case["human_labels"]
        for dimension, expected in labels_by_dimension.items():
            observed = [run["dimensions"][dimension] for run in runs]
            statuses = {item["status"] for item in observed}
            grades = [item["grade"] for item in observed if item["grade"] is not None]
            if len(statuses) > 1 or (
                grades and max(grades) - min(grades) > labels["maximum_repeat_grade_delta"]
            ):
                unstable.append(f"{case_id}:{dimension}")
            for item in observed:
                total += 1
                status_match = item["status"] == expected["status"]
                grade_match = (
                    item["grade"] is None
                    if expected["grade_min"] is None
                    else isinstance(item["grade"], (int, float))
                    and expected["grade_min"] <= item["grade"] <= expected["grade_max"]
                )
                matched += int(status_match and grade_match)
    agreement = matched / total
    status = "PASS" if agreement >= labels["agreement_threshold"] and not unstable else "FAIL"
    result = {
        "schema_version": "semantic-calibration-result/1.0.0",
        "calibration_id": labels["calibration_id"],
        "status": status,
        "agreement": agreement,
        "threshold": labels["agreement_threshold"],
        "unstable_dimensions": sorted(unstable),
        "observations": total,
    }
    result["result_hash"] = canonical_hash(result)
    return result


def run_calibration(
    repository_root: Path,
    *,
    labels_path: Path,
    grader_index_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    """Compare immutable repeated grader outputs with the human-label ranges."""

    if output_dir.exists():
        raise ValueError("CALIBRATION_OUTPUT_EXISTS")
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    index = json.loads(grader_index_path.read_text(encoding="utf-8"))
    if not isinstance(index, Mapping) or set(index) != {"schema_version", "cases"}:
        raise ValueError("CALIBRATION_INDEX_INVALID")
    grader_runs: dict[str, list[dict[str, Any]]] = {}
    input_hashes: dict[str, str] = {"labels": file_hash(labels_path), "grader_index": file_hash(grader_index_path)}
    for case_id, records in index["cases"].items():
        if not isinstance(records, list) or len(records) < 2:
            raise ValueError(f"CALIBRATION_REPEAT_MISSING:{case_id}")
        grader_runs[case_id] = []
        sessions: set[str] = set()
        for number, record in enumerate(records):
            if not isinstance(record, Mapping) or set(record) != {"path", "sha256", "execution_proof"}:
                raise ValueError(f"CALIBRATION_INDEX_INVALID:{case_id}")
            path = Path(str(record["path"])).resolve()
            if not path.is_file() or file_hash(path) != record["sha256"]:
                raise ValueError(f"CALIBRATION_ARTIFACT_HASH_MISMATCH:{case_id}")
            value = json.loads(path.read_text(encoding="utf-8"))
            if set(value) != {"schema_version", "eval_id", "grader", "dimensions", "output_hash"}:
                raise ValueError(f"CALIBRATION_GRADER_TOP_LEVEL_CONTRACT_INVALID:{case_id}")
            body = dict(value)
            claimed = body.pop("output_hash", None)
            if claimed != canonical_hash(body):
                raise ValueError(f"CALIBRATION_GRADER_OUTPUT_HASH_INVALID:{case_id}")
            if value.get("schema_version") != "semantic-rubric-result/1.0.0":
                raise ValueError(f"CALIBRATION_GRADER_SCHEMA_INVALID:{case_id}")
            if value.get("grader") != EXPECTED_CALIBRATION_GRADER:
                raise ValueError(f"CALIBRATION_GRADER_IDENTITY_INVALID:{case_id}")
            if set(value.get("dimensions", {})) != set(
                next(item["human_labels"] for item in labels["cases"] if item["case_id"] == case_id)
            ):
                raise ValueError(f"CALIBRATION_DIMENSION_SET_INVALID:{case_id}")
            grader_runs[case_id].append(value)
            input_hashes[f"{case_id}_{number + 1}"] = record["sha256"]
            proof_record = record["execution_proof"]
            if not isinstance(proof_record, Mapping) or set(proof_record) != {"path", "sha256"}:
                raise ValueError(f"CALIBRATION_EXECUTION_PROOF_INDEX_INVALID:{case_id}")
            proof_path = Path(str(proof_record["path"])).resolve()
            if not proof_path.is_file() or file_hash(proof_path) != proof_record["sha256"]:
                raise ValueError(f"CALIBRATION_EXECUTION_PROOF_ARTIFACT_INVALID:{case_id}")
            proof = verify_calibration_execution_proof(
                repository_root,
                proof_path=proof_path,
                case_id=case_id,
                repeat=number + 1,
                grader_output_path=path,
            )
            if proof["session_id"] in sessions:
                raise ValueError(f"CALIBRATION_SESSION_NOT_INDEPENDENT:{case_id}")
            sessions.add(proof["session_id"])
            input_hashes[f"{case_id}_{number + 1}_execution_proof"] = proof_record["sha256"]
    result = evaluate_calibration(labels, grader_runs=grader_runs)
    result["input_hashes"] = input_hashes
    result["source_artifacts"] = {
        "labels": {"path": str(labels_path.resolve()), "sha256": file_hash(labels_path)},
        "grader_index": {"path": str(grader_index_path.resolve()), "sha256": file_hash(grader_index_path)},
    }
    result["session_ids"] = sorted(
        {
            verify_calibration_execution_proof(
                repository_root,
                proof_path=Path(record["execution_proof"]["path"]),
                case_id=case_id,
                repeat=number + 1,
                grader_output_path=Path(record["path"]),
            )["session_id"]
            for case_id, records in index["cases"].items()
            for number, record in enumerate(records)
        }
    )
    result.pop("result_hash")
    result["result_hash"] = canonical_hash(result)
    schema = json.loads(
        (repository_root / "product" / "schemas" / "runtime" / "semantic-calibration-result.schema.json").read_text(encoding="utf-8")
    )
    validate_schema_instance(result, schema)
    output_dir.mkdir(parents=True)
    (output_dir / "result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    lines = [
        "# Runtime Eval 语义校准报告",
        "",
        f"- 校准集：`{result['calibration_id']}`",
        f"- 结果：`{result['status']}`",
        f"- 一致率：`{result['agreement']:.3f}`（门槛 `{result['threshold']:.3f}`）",
        f"- 观测数：`{result['observations']}`",
        "",
        "## 不稳定维度",
        "",
    ]
    lines.extend([f"- `{item}`" for item in result["unstable_dimensions"]] or ["- 无"])
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def verify_calibration_result(repository_root: Path, result_path: Path) -> dict[str, Any]:
    """Re-run calibration from its bound raw grader artifacts and compare exactly."""

    saved = json.loads(result_path.read_text(encoding="utf-8"))
    body = dict(saved)
    if body.pop("result_hash", None) != canonical_hash(body):
        raise ValueError("CALIBRATION_RESULT_HASH_INVALID")
    sources = saved.get("source_artifacts", {})
    for name in ("labels", "grader_index"):
        record = sources.get(name, {})
        path = Path(str(record.get("path", ""))).resolve()
        if not path.is_file() or file_hash(path) != record.get("sha256"):
            raise ValueError(f"CALIBRATION_SOURCE_ARTIFACT_INVALID:{name}")
    with tempfile.TemporaryDirectory(prefix="stock-agent-calibration-verify-") as directory:
        rebuilt = run_calibration(
            repository_root,
            labels_path=Path(sources["labels"]["path"]),
            grader_index_path=Path(sources["grader_index"]["path"]),
            output_dir=Path(directory) / "result",
        )
    if rebuilt != saved:
        raise ValueError("CALIBRATION_RESULT_RECOMPUTE_MISMATCH")
    return rebuilt
