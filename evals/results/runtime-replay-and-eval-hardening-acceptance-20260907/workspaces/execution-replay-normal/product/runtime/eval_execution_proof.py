"""Privacy-minimized proof that dev_eval and its Skill produced semantic grades."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any, Mapping

from .execution_proof import (
    _final_structured_output,
    _function_calls,
    _load_jsonl,
    _message_texts,
    _rollout_telemetry,
    _session_meta,
    _turn_context,
)
from .hashing import canonical_hash, file_hash


class EvalExecutionProofError(ValueError):
    pass


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise EvalExecutionProofError(f"EVAL_PROOF_INPUT_INVALID:{path.name}") from exc
    if not isinstance(value, Mapping):
        raise EvalExecutionProofError(f"EVAL_PROOF_INPUT_NOT_OBJECT:{path.name}")
    return dict(value)


def discover_eval_rollouts(sessions_root: Path, *, eval_dir: Path, eval_id: str) -> tuple[Path, Path]:
    if not sessions_root.is_dir():
        raise EvalExecutionProofError("CODEX_SESSIONS_ROOT_NOT_FOUND")
    earliest = (eval_dir / "input-manifest.json").stat().st_mtime - 60
    parents: list[tuple[Path, str]] = []
    children: dict[str, Path] = {}
    for path in sessions_root.rglob("*.jsonl"):
        if not path.is_file() or path.stat().st_mtime < earliest:
            continue
        try:
            records = _load_jsonl(path)
            meta = _session_meta(records)
        except ValueError:
            continue
        user_text = "\n".join(_message_texts(records, role="user"))
        if eval_id not in user_text or str(eval_dir.resolve()) not in user_text:
            continue
        if meta.get("parent_thread_id"):
            if meta.get("agent_role") == "dev_eval":
                children[str(meta.get("parent_thread_id"))] = path
            continue
        calls = [
            call for call in _function_calls(records)
            if call.get("namespace") == "collaboration"
            and call.get("name") == "spawn_agent"
            and call.get("arguments", {}).get("agent_type") == "dev_eval"
        ]
        if len(calls) == 1:
            parents.append((path, str(meta.get("id", ""))))
    matches = [(parent, children[parent_id]) for parent, parent_id in parents if parent_id in children]
    if len(matches) != 1:
        raise EvalExecutionProofError(f"EVAL_ROLLOUT_PAIR_COUNT_INVALID:{len(matches)}")
    return matches[0]


def build_eval_execution_proof(
    repository_root: Path,
    *,
    eval_dir: Path,
    semantic_result_path: Path,
    parent_rollout: Path,
    child_rollout: Path,
) -> dict[str, Any]:
    repository_root = repository_root.resolve()
    eval_dir = eval_dir.resolve()
    manifest = _read(eval_dir / "input-manifest.json")
    semantic = _read(semantic_result_path.resolve())
    parent_records = _load_jsonl(parent_rollout)
    child_records = _load_jsonl(child_rollout)
    parent_meta = _session_meta(parent_records)
    child_meta = _session_meta(child_records)
    parent_context = _turn_context(parent_records)
    child_context = _turn_context(child_records)
    calls = [
        call for call in _function_calls(parent_records)
        if call.get("namespace") == "collaboration" and call.get("name") == "spawn_agent"
    ]
    if len(calls) != 1 or calls[0].get("arguments", {}).get("agent_type") != "dev_eval":
        raise EvalExecutionProofError("EVAL_DEV_AGENT_DISPATCH_INVALID")
    arguments = calls[0]["arguments"]
    if arguments.get("task_name") != "semantic_grading" or arguments.get("fork_turns") != "none":
        raise EvalExecutionProofError("EVAL_DEV_AGENT_CONTEXT_INVALID")
    if child_meta.get("parent_thread_id") != parent_meta.get("id") or child_meta.get("agent_role") != "dev_eval":
        raise EvalExecutionProofError("EVAL_DEV_AGENT_IDENTITY_INVALID")
    if parent_context.get("model") != "gpt-5.6-terra" or child_context.get("model") != "gpt-5.6-terra":
        raise EvalExecutionProofError("MODEL_ROUTE_INVALID:eval-grader")
    agent_path = repository_root / ".codex" / "agents" / "dev_eval.toml"
    skill_path = repository_root / ".agents" / "skills" / "runtime-eval-grading" / "SKILL.md"
    with agent_path.open("rb") as handle:
        agent = tomllib.load(handle)
    instructions = str(agent.get("developer_instructions", ""))
    developer_text = "\n".join(_message_texts(child_records, role="developer"))
    if not instructions or instructions not in developer_text:
        raise EvalExecutionProofError("EVAL_DEV_AGENT_INSTRUCTIONS_NOT_LOADED")
    configured = agent.get("skills", {}).get("config", [])
    if configured != [{"path": ".agents/skills/runtime-eval-grading", "enabled": True}]:
        raise EvalExecutionProofError("EVAL_GRADER_SKILL_CONFIG_INVALID")
    child_user = "\n".join(_message_texts(child_records, role="user"))
    required_bindings = [
        str(manifest["eval_id"]),
        str(manifest["source_hashes"]["grader_prompt"]),
        str(manifest["source_hashes"]["rubric"]),
        str(manifest["source_hashes"]["semantic_input"]),
    ]
    if not all(item in child_user for item in required_bindings):
        raise EvalExecutionProofError("EVAL_GRADER_TASK_BINDING_MISSING")
    final = _final_structured_output(child_records, agent_name="dev_eval")
    if canonical_hash(final) != canonical_hash(semantic):
        raise EvalExecutionProofError("EVAL_GRADER_OUTPUT_MISMATCH")
    parent_telemetry = _rollout_telemetry(parent_records)
    child_telemetry = _rollout_telemetry(child_records)
    if parent_telemetry["status"] != "AVAILABLE" or child_telemetry["status"] != "AVAILABLE":
        raise EvalExecutionProofError("EVAL_GRADER_TELEMETRY_MISSING")
    proof: dict[str, Any] = {
        "schema_version": "eval-grader-execution-proof/1.0.0",
        "eval_id": manifest["eval_id"],
        "parent_session_id": parent_meta.get("id"),
        "child_session_id": child_meta.get("id"),
        "agent": "dev_eval",
        "model": "gpt-5.6-terra",
        "agent_hash": file_hash(agent_path),
        "skill_hash": file_hash(skill_path),
        "prompt_hash": manifest["source_hashes"]["grader_prompt"],
        "rubric_hash": manifest["source_hashes"]["rubric"],
        "input_hash": manifest["source_hashes"]["semantic_input"],
        "schema_hash": manifest["source_hashes"]["semantic_output_schema"],
        "output_hash": semantic["output_hash"],
        "parent_rollout_hash": file_hash(parent_rollout),
        "child_rollout_hash": file_hash(child_rollout),
        "telemetry": {
            "input_tokens": parent_telemetry["input_tokens"] + child_telemetry["input_tokens"],
            "output_tokens": parent_telemetry["output_tokens"] + child_telemetry["output_tokens"],
            "cached_tokens": parent_telemetry["cached_tokens"] + child_telemetry["cached_tokens"],
            "latency_ms": parent_telemetry["latency_ms"],
            "llm_calls": parent_telemetry["llm_calls"] + child_telemetry["llm_calls"],
        },
        "raw_prompt_or_reasoning_retained": False,
    }
    proof["proof_hash"] = canonical_hash(proof)
    return proof


def persist_eval_execution_proof(proof: Mapping[str, Any], *, eval_dir: Path) -> Path:
    path = eval_dir.resolve() / "grader-execution-proof.json"
    if path.exists():
        raise EvalExecutionProofError("EVAL_PROOF_ALREADY_EXISTS")
    path.write_text(json.dumps(proof, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def verify_eval_execution_proof(
    repository_root: Path,
    *,
    eval_dir: Path,
    semantic_result: Mapping[str, Any],
) -> dict[str, Any]:
    proof = _read(eval_dir.resolve() / "grader-execution-proof.json")
    body = dict(proof)
    if body.pop("proof_hash", None) != canonical_hash(body):
        raise EvalExecutionProofError("EVAL_PROOF_HASH_INVALID")
    manifest = _read(eval_dir.resolve() / "input-manifest.json")
    expected = {
        "agent": "dev_eval",
        "model": semantic_result["grader"]["model"],
        "prompt_hash": manifest["source_hashes"]["grader_prompt"],
        "rubric_hash": manifest["source_hashes"]["rubric"],
        "input_hash": manifest["source_hashes"]["semantic_input"],
        "schema_hash": manifest["source_hashes"]["semantic_output_schema"],
        "output_hash": semantic_result["output_hash"],
        "agent_hash": file_hash(repository_root.resolve() / ".codex" / "agents" / "dev_eval.toml"),
        "skill_hash": file_hash(repository_root.resolve() / ".agents" / "skills" / "runtime-eval-grading" / "SKILL.md"),
    }
    if any(proof.get(key) != value for key, value in expected.items()):
        raise EvalExecutionProofError("EVAL_PROOF_LINEAGE_MISMATCH")
    return proof
