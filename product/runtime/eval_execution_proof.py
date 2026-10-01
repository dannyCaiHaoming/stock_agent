"""Privacy-minimized proof that dev_eval and its Skill produced semantic grades."""

from __future__ import annotations

import json
import re
import shlex
import tomllib
from pathlib import Path
from typing import Any, Mapping

from .execution_proof import (
    _final_structured_output,
    _function_calls,
    _is_protected_dispatch_message,
    _load_jsonl,
    _message_texts,
    _rollout_telemetry,
    _session_telemetry_summary,
    _session_meta,
    _turn_context,
)
from .hashing import canonical_hash, file_hash, legacy_envelope_hash, verify_legacy_envelope_hash, HashContractError


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
        if meta.get("parent_thread_id"):
            if meta.get("agent_role") == "dev_eval":
                children[str(meta.get("parent_thread_id"))] = path
            continue
        user_text = "\n".join(_message_texts(records, role="user"))
        if eval_id not in user_text or str(eval_dir.resolve()) not in user_text:
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


def normalize_native_grade(final, manifest, *, model):
    """Envelope real LLM grades with runtime metadata; never repair a legacy result."""
    if manifest.get("semantic_output_delivery") != "native-draft/1.0.0":
        return final
    if (not isinstance(final, Mapping) or set(final) != {"schema_version", "eval_id", "dimensions"}
            or final["schema_version"] != "semantic-rubric-draft/1.0.0"
            or final["eval_id"] != manifest["eval_id"] or model != "gpt-5.6-terra"):
        raise EvalExecutionProofError("EVAL_NATIVE_DRAFT_INVALID")
    hashes = manifest["source_hashes"]
    value = {"schema_version": "semantic-rubric-result/1.0.0", "eval_id": final["eval_id"],
             "dimensions": final["dimensions"], "grader": {"agent": "dev_eval", "model": model,
             "prompt_hash": hashes["grader_prompt"], "rubric_hash": hashes["rubric"],
             "input_hash": hashes["semantic_input"]}}
    value["output_hash"] = legacy_envelope_hash(value, hash_field="output_hash")
    from .runtime_eval import validate_semantic_result
    return validate_semantic_result(value, eval_id=manifest["eval_id"], input_manifest=manifest)


def _native_manifest_read(records, path):
    """Bind the frozen hashes to an actual child tool result, not generated text."""
    expected = path.read_text(encoding="utf-8").strip()
    target = path.resolve()

    def names_target(arguments):
        if isinstance(arguments, str):
            # Tool wrappers may contain a nested command in a `code` field;
            # retain exact-path proof without accepting a longer lookalike name.
            if re.search(re.escape(str(target)) + r"(?=$|[\s'\"\\},;])", arguments):
                return True
            try:
                parsed = json.loads(arguments)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, (dict, list)):
                return names_target(parsed)
            # functions.exec 的真实 rollout 使用 JS 包裹 JSON 参数；仅解码
            # exec_command 的实参，不执行 JS，也不靠反斜杠/前缀模糊匹配路径。
            for match in re.finditer(r"\btools\.exec_command\s*\(\s*", arguments):
                try:
                    wrapped, _ = json.JSONDecoder().raw_decode(arguments, match.end())
                except json.JSONDecodeError:
                    continue
                if isinstance(wrapped, Mapping) and names_target(wrapped.get("cmd", "")):
                    return True
            try:
                tokens = shlex.split(arguments)
            except ValueError:
                return False
            for token in tokens:
                candidate = Path(token)
                if candidate.is_absolute() and candidate.resolve() == target:
                    return True
            return False
        if isinstance(arguments, Mapping):
            return any(names_target(value) for key, value in arguments.items()
                       if key in {"cmd", "code", "path", "file", "input"})
        if isinstance(arguments, list):
            return any(names_target(value) for value in arguments)
        return False

    calls = set()
    for record in records:
        payload = record.get("payload", {})
        if payload.get("type") in {"function_call", "custom_tool_call"}:
            if names_target(payload.get("arguments", payload.get("input", ""))):
                calls.add(payload.get("call_id"))
        if payload.get("type") in {"function_call_output", "custom_tool_call_output"} and payload.get("call_id") in calls:
            output = payload.get("output", "")
            text = output if isinstance(output, str) else "\n".join(str(x.get("text", "")) for x in output if isinstance(x, dict))
            if expected in text:
                return True
    return False


def collect_native_eval_output(repository_root, *, eval_dir, semantic_result_path, parent_rollout, child_rollout):
    manifest = _read(eval_dir / "input-manifest.json")
    if manifest.get("semantic_output_delivery") != "native-draft/1.0.0":
        raise EvalExecutionProofError("EVAL_NATIVE_COLLECTION_NOT_ENABLED")
    if semantic_result_path.resolve() != (eval_dir / "semantic-result.json").resolve():
        raise EvalExecutionProofError("EVAL_NATIVE_OUTPUT_PATH_INVALID")
    context = _eval_context(repository_root, eval_dir=eval_dir, parent_rollout=parent_rollout, child_rollout=child_rollout)
    from .eval_local_revision import collect
    final, feedback = collect(repository_root, eval_dir=eval_dir, parent_rollout=parent_rollout,
                              child_rollout=child_rollout, context=context)
    if feedback is not None:
        return feedback
    value = normalize_native_grade(final, manifest, model=_turn_context(context["child_records"]).get("model"))
    # Preserve the raw draft separately. No overwrite or silent legacy hash fix.
    for path, content in ((eval_dir / "semantic-native-draft.json", final), (semantic_result_path, value)):
        with path.open("x", encoding="utf-8") as stream:
            json.dump(content, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.write("\n")
    return build_eval_execution_proof(repository_root, eval_dir=eval_dir, semantic_result_path=semantic_result_path,
                                     parent_rollout=parent_rollout, child_rollout=child_rollout)


def _eval_context(repository_root: Path, *, eval_dir: Path, parent_rollout: Path, child_rollout: Path) -> dict:
    """共同使用真实身份/隔离/模型/方法及 manifest 读取证明，先于存稿。"""
    repository_root = repository_root.resolve()
    eval_dir = eval_dir.resolve()
    manifest = _read(eval_dir / "input-manifest.json")
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
    if manifest.get("semantic_output_delivery") == "native-draft/1.0.0" and not _native_manifest_read(child_records, eval_dir / "input-manifest.json"):
        raise EvalExecutionProofError("EVAL_NATIVE_MANIFEST_READ_MISSING")
    if manifest.get("local_revision_contract"):
        from .runtime_eval import verify_runtime_eval_model_input
        verify_runtime_eval_model_input(eval_dir, manifest)
        if not _native_manifest_read(child_records, eval_dir / "grader-model-input.json"):
            raise EvalExecutionProofError("EVAL_MODEL_INPUT_READ_MISSING")
    if any(_rollout_telemetry(records)["status"] != "AVAILABLE" for records in (parent_records, child_records)):
        raise EvalExecutionProofError("EVAL_GRADER_TELEMETRY_MISSING")
    return {"manifest": manifest, "parent_records": parent_records, "child_records": child_records,
            "parent_meta": parent_meta, "child_meta": child_meta, "child_context": child_context,
            "agent_path": agent_path, "skill_path": skill_path, "arguments": arguments}


def build_eval_execution_proof(
    repository_root: Path, *, eval_dir: Path, semantic_result_path: Path,
    parent_rollout: Path, child_rollout: Path,
    semantic_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    repository_root, eval_dir = repository_root.resolve(), eval_dir.resolve()
    semantic = dict(semantic_result) if semantic_result is not None else _read(semantic_result_path.resolve())
    context = _eval_context(repository_root, eval_dir=eval_dir, parent_rollout=parent_rollout, child_rollout=child_rollout)
    manifest = context["manifest"]
    parent_records, child_records = context["parent_records"], context["child_records"]
    parent_meta, child_meta = context["parent_meta"], context["child_meta"]
    child_context, arguments = context["child_context"], context["arguments"]
    agent_path, skill_path = context["agent_path"], context["skill_path"]
    child_user = "\n".join(_message_texts(child_records, role="user"))
    required_bindings = [
        str(manifest["eval_id"]),
        str(manifest["source_hashes"]["grader_prompt"]),
        str(manifest["source_hashes"]["rubric"]),
        str(manifest["source_hashes"]["semantic_input"]),
    ]
    from .eval_local_revision import resolved
    final = resolved(repository_root, eval_dir=eval_dir, parent_rollout=parent_rollout,
                     child_rollout=child_rollout, context=context)
    final = normalize_native_grade(final, manifest, model=child_context.get("model"))
    plaintext_binding = all(item in child_user for item in required_bindings)
    protected_binding = _is_protected_dispatch_message(arguments.get("message")) and (
        final.get("eval_id") == manifest["eval_id"]
        and final.get("grader", {}).get("prompt_hash") == manifest["source_hashes"]["grader_prompt"]
        and final.get("grader", {}).get("rubric_hash") == manifest["source_hashes"]["rubric"]
        and final.get("grader", {}).get("input_hash") == manifest["source_hashes"]["semantic_input"]
    )
    native_read = False
    if manifest.get("semantic_output_delivery") == "native-draft/1.0.0":
        native_read = _native_manifest_read(child_records, eval_dir / "input-manifest.json")
        if not native_read:
            raise EvalExecutionProofError("EVAL_NATIVE_MANIFEST_READ_MISSING")
    if not plaintext_binding and not protected_binding and not native_read:
        raise EvalExecutionProofError("EVAL_GRADER_TASK_BINDING_MISSING")
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
        "telemetry": _session_telemetry_summary(parent_records, {"dev_eval": child_records}),
        "raw_prompt_or_reasoning_retained": False,
        "task_binding_method": (
            "native_manifest_read" if native_read else
            "plaintext_child_input" if plaintext_binding else "protected_dispatch_plus_structured_output"
        ),
    }
    if manifest.get("local_revision_contract"):
        from .eval_local_revision import VERSION, RECORD
        if manifest["local_revision_contract"] != VERSION:
            raise EvalExecutionProofError("EVAL_LOCAL_REVISION_CONTRACT_INVALID")
        proof["local_revision"] = {
            "version": VERSION,
            "status": "REVISED" if (eval_dir / RECORD).exists() else "FIRST_DRAFT",
            "parent_rollout": str(parent_rollout.resolve()),
            "child_rollout": str(child_rollout.resolve()),
        }
        full_bytes = len((eval_dir / "grader-input.json").read_bytes())
        view_bytes = len((eval_dir / "grader-model-input.json").read_bytes())
        proof["input_delivery_diagnostics"] = {
            "scope": "CHILD_VERIFIED_GRADER_INPUT_FILE_READ_ONLY",
            "comparison_status": "SAME_FROZEN_INPUT",
            "full_input_bytes": full_bytes, "model_input_bytes": view_bytes,
            "byte_delta": view_bytes - full_bytes,
            "model_input_hash": manifest["model_input_projection"]["input_hash"],
            "token_count_status": "NOT_OBSERVED_FOR_THIS_FILE",
            "full_context_tokens": None, "total_cost": None,
        }
    proof["proof_hash"] = legacy_envelope_hash(proof, hash_field="proof_hash")
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
    try:
        verify_legacy_envelope_hash(proof, hash_field="proof_hash", location="grader-execution-proof.json")
    except HashContractError as exc:
        raise EvalExecutionProofError(f"EVAL_PROOF_HASH_INVALID:{exc}") from exc
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
    if manifest.get("local_revision_contract"):
        source = proof.get("local_revision", {})
        if (source.get("version") != manifest["local_revision_contract"]
                or not all(isinstance(source.get(key), str) and Path(source[key]).is_absolute()
                           for key in ("parent_rollout", "child_rollout"))):
            raise EvalExecutionProofError("EVAL_LOCAL_REVISION_PROOF_MISSING")
        # 当前写入契约重读真实事件与两版原稿；历史无此标记的结果保持只读兼容。
        rebuilt = build_eval_execution_proof(
            repository_root, eval_dir=eval_dir, semantic_result_path=eval_dir / "semantic-result.json",
            semantic_result=semantic_result,
            parent_rollout=Path(source["parent_rollout"]), child_rollout=Path(source["child_rollout"]))
        if rebuilt != proof:
            raise EvalExecutionProofError("EVAL_LOCAL_REVISION_PROOF_DRIFT")
    return proof
