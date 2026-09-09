"""Deterministic preparation and finalization for Codex-native execution replay."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .hashing import canonical_hash, file_hash
from .replay import replay_run
from .replay_capsule import materialize_replay_capsule, validate_replay_capsule
from .run_package import prepare_run
from .schema_validation import validate_schema_instance
from .trace_validation import trace_integrity_report


EXECUTION_REPLAY_VERSION = "execution-replay/1.0.0"


class ExecutionReplayError(ValueError):
    pass


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ExecutionReplayError(f"EXECUTION_REPLAY_ARTIFACT_INVALID:{path.name}") from exc
    if not isinstance(value, Mapping):
        raise ExecutionReplayError(f"EXECUTION_REPLAY_ARTIFACT_NOT_OBJECT:{path.name}")
    return dict(value)


def _locked_inputs(manifest: Mapping[str, Any], *, fixture: Mapping[str, Any], gate: Mapping[str, Any]) -> dict[str, Any]:
    discovery = manifest.get("discovery")
    if not isinstance(discovery, Mapping) or not isinstance(discovery.get("version_manifest"), Mapping):
        raise ExecutionReplayError("VERSION_LOCK_MISSING")
    return {
        "candidate_version": manifest.get("candidate_version"),
        "codex_runtime": manifest.get("codex_runtime"),
        "model": manifest.get("model"),
        "runtime_profile": manifest.get("runtime_profile"),
        "fixture_id": manifest.get("fixture_id"),
        "decision_cutoff": manifest.get("decision_cutoff"),
        "research_question": manifest.get("research_question"),
        "fixture_hash": canonical_hash(fixture),
        "gate_context_hash": canonical_hash(
            {key: value for key, value in gate.items() if key not in {"run_id", "bundle_hash"}}
        ),
        "version_manifest": discovery["version_manifest"],
    }


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        raise ExecutionReplayError(f"EXECUTION_REPLAY_OUTPUT_EXISTS:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def prepare_execution_replay(
    *,
    source_run_dir: Path,
    new_run_dir: Path,
    new_run_id: str,
    workspace_root: Path | None = None,
) -> dict[str, Any]:
    source_run_dir = source_run_dir.resolve()
    new_run_dir = new_run_dir.resolve()
    if new_run_dir.exists() or new_run_dir == source_run_dir:
        raise ExecutionReplayError("EXECUTION_REPLAY_OUTPUT_MUST_BE_NEW")
    source_manifest = _read_object(source_run_dir / "run_manifest.json")
    if source_manifest.get("run_mode", "PRODUCT_COUNCIL") not in {"PRODUCT_COUNCIL", "EXECUTION_REPLAY"}:
        raise ExecutionReplayError("EXECUTION_REPLAY_SOURCE_PROFILE_UNSUPPORTED")
    source_trace = _read_object(source_run_dir / "decision_trace.json")
    trace_integrity_report(source_trace, run_dir=source_run_dir)
    reference = source_manifest.get("replay_capsule")
    if source_manifest.get("execution_replay_supported") is not True or not isinstance(reference, Mapping):
        raise ExecutionReplayError("EXECUTION_REPLAY_UNSUPPORTED")
    capsule = validate_replay_capsule(
        source_run_dir / "replay_capsule", expected_run_id=str(source_manifest["run_id"])
    )
    if reference.get("manifest_hash") != capsule["manifest_hash"]:
        raise ExecutionReplayError("CAPSULE_HASH_MISMATCH:reference")
    context = capsule["locked_context"]
    if any(
        source_manifest.get(field) != context.get(field)
        for field in (
            "candidate_version",
            "model",
            "codex_runtime",
            "runtime_profile",
            "run_mode",
            "ablation_profile",
            "trigger_reason",
            "research_question",
            "decision_cutoff",
        )
    ):
        raise ExecutionReplayError("EXECUTION_REPLAY_SOURCE_CONTEXT_MISMATCH")
    workspace = (
        workspace_root.resolve()
        if workspace_root is not None
        else new_run_dir.parent / f".{new_run_id}-replay-workspace"
    )
    if workspace.exists():
        raise ExecutionReplayError("EXECUTION_REPLAY_WORKSPACE_EXISTS")
    materialize_replay_capsule(source_run_dir / "replay_capsule", target_root=workspace)
    frozen_fixture = _read_object(workspace / "frozen" / "audit" / "fixture_snapshot.json")
    frozen_gate = _read_object(workspace / "frozen" / "evidence" / "gate.json")
    fixture_path = workspace / "evals" / "fixtures" / "codex-native" / "execution-replay-source.json"
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(
        json.dumps(frozen_fixture, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    result = prepare_run(
        workspace,
        fixture_path=fixture_path,
        run_dir=new_run_dir,
        run_id=new_run_id,
        model=str(context["model"]),
        research_question=str(context["research_question"]),
        authenticity_required=source_manifest.get("authenticity_required") is not False,
        run_mode="EXECUTION_REPLAY",
        trigger_reason="execution_replay",
    )
    if result.get("terminal_state") == "FAILED_VALIDATION":
        raise ExecutionReplayError("EXECUTION_REPLAY_PREPARATION_FAILED")
    new_manifest_path = new_run_dir / "run_manifest.json"
    new_manifest = _read_object(new_manifest_path)
    new_fixture = _read_object(new_run_dir / "audit" / "fixture_snapshot.json")
    new_gate = _read_object(new_run_dir / "evidence" / "gate.json")
    source_lock = _locked_inputs(source_manifest, fixture=frozen_fixture, gate=frozen_gate)
    new_lock = _locked_inputs(new_manifest, fixture=new_fixture, gate=new_gate)
    if source_lock != new_lock:
        raise ExecutionReplayError("EXECUTION_REPLAY_NOT_COMPARABLE")
    new_manifest["execution_replay"] = {
        "source_run_id": source_manifest["run_id"],
        "source_capsule_hash": capsule["manifest_hash"],
        "source_terminal_state": source_trace["terminal_state"],
        "workspace": str(workspace),
    }
    new_manifest_path.write_text(
        json.dumps(new_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    replay_manifest: dict[str, Any] = {
        "schema_version": EXECUTION_REPLAY_VERSION,
        "source_run_id": source_manifest["run_id"],
        "new_run_id": new_run_id,
        "source_capsule_hash": capsule["manifest_hash"],
        "workspace": str(workspace),
        "locked_inputs": source_lock,
        "locked_input_hash": canonical_hash(source_lock),
        "source_manifest_hash": canonical_hash(source_manifest),
        "new_manifest_hash": canonical_hash(new_manifest),
        "llm_output_equality_required": False,
        "contract_and_semantic_eval_required": True,
        "status": "PREPARED",
    }
    schema = _read_object(workspace / "product" / "schemas" / "runtime" / "execution-replay.schema.json")
    validate_schema_instance(replay_manifest, schema)
    replay_path = new_run_dir / "execution-replay.json"
    _write_json(replay_path, replay_manifest)
    trace_path = new_run_dir / "decision_trace.json"
    trace = _read_object(trace_path)
    trace["runtime"]["execution_replay"] = {
        "source_run_id": source_manifest["run_id"],
        "source_capsule_hash": capsule["manifest_hash"],
        "locked_input_hash": replay_manifest["locked_input_hash"],
    }
    trace["artifacts"]["run_manifest.json"] = file_hash(new_manifest_path)
    trace["artifacts"]["execution-replay.json"] = file_hash(replay_path)
    trace["events"].append({"stage": "EXECUTION_REPLAY_PREPARED", "source_run_id": source_manifest["run_id"]})
    trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "run_id": new_run_id,
        "source_run_id": source_manifest["run_id"],
        "next_state": result["next_state"],
        "workspace": str(workspace),
        "execution_replay_manifest_hash": canonical_hash(replay_manifest),
    }


def finalize_execution_replay(
    *,
    source_run_dir: Path,
    replay_run_dir: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise ExecutionReplayError("EXECUTION_REPLAY_OUTPUT_EXISTS")
    source_run_dir = source_run_dir.resolve()
    replay_run_dir = replay_run_dir.resolve()
    source_trace = _read_object(source_run_dir / "decision_trace.json")
    replay_trace = _read_object(replay_run_dir / "decision_trace.json")
    source_integrity = trace_integrity_report(source_trace, run_dir=source_run_dir)
    replay_integrity = trace_integrity_report(replay_trace, run_dir=replay_run_dir)
    manifest = _read_object(replay_run_dir / "execution-replay.json")
    if (
        manifest.get("source_run_id") != source_trace.get("run_id")
        or manifest.get("new_run_id") != replay_trace.get("run_id")
    ):
        raise ExecutionReplayError("EXECUTION_REPLAY_SOURCE_MISMATCH")
    replay_check = replay_run(Path(manifest["workspace"]), run_dir=replay_run_dir)
    result: dict[str, Any] = {
        "schema_version": "execution-replay-result/1.0.0",
        "source_run_id": source_trace["run_id"],
        "replay_run_id": replay_trace["run_id"],
        "status": "PASS",
        "configuration_equivalent": True,
        "byte_identical_output_required": False,
        "source_terminal_state": source_trace["terminal_state"],
        "replay_terminal_state": replay_trace["terminal_state"],
        "source_trace_hash": source_integrity["trace_hash"],
        "replay_trace_hash": replay_integrity["trace_hash"],
        "artifact_replay_hash": replay_check["replay_hash"],
    }
    result["result_hash"] = canonical_hash(result)
    output_dir.mkdir(parents=True)
    _write_json(output_dir / "result.json", result)
    report = (
        "# Execution Replay 比较报告\n\n"
        f"- 来源 Run：`{result['source_run_id']}`\n"
        f"- 重放 Run：`{result['replay_run_id']}`\n"
        f"- 状态：`{result['status']}`\n"
        "- 输入、Evidence、受控配置与版本闭包：一致\n"
        "- LLM 输出逐字一致：不要求\n"
    )
    (output_dir / "report.md").write_text(report, encoding="utf-8")
    return result
