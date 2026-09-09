"""Semantic validation for Decision Trace 2.1.0."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .hashing import canonical_hash, file_hash
from .evidence_gate import run_evidence_gate
from .replay_capsule import validate_replay_capsule
from .runtime_profiles import validate_runtime_mode
from .validation import collect_evidence_refs
from .terminal_contract import (
    FailureStage,
    RUN_ERROR_VERSION,
    TRACE_VERSION,
    normalize_failure_stage,
    risk_lineage_required,
    stage_at_or_after,
    validate_risk_lineage_entries,
)


TRACE_KEYS = {
    "schema_version",
    "run_id",
    "terminal_state",
    "failed_stage",
    "runtime",
    "agents",
    "events",
    "risk_lineage",
    "artifacts",
    "codex_execution",
    "mcp_events",
    "evidence_lineage",
}
TERMINAL_STATES = {"COMPLETED", "SAFE_NO_TRADE", "FAILED_VALIDATION"}
CHAIN_AGENTS = {
    "runtime_company_analyst",
    "runtime_skeptic",
    "runtime_cio",
}


class TraceValidationError(ValueError):
    """Raised when trace lineage cannot be traversed or verified."""


def validate_decision_trace(trace: Mapping[str, Any], *, run_dir: Path) -> None:
    if set(trace) != TRACE_KEYS:
        raise TraceValidationError("TRACE_TOP_LEVEL_KEYS_INVALID")
    if trace.get("schema_version") != TRACE_VERSION:
        raise TraceValidationError("TRACE_SCHEMA_VERSION_INVALID")
    terminal_state = str(trace.get("terminal_state"))
    if terminal_state not in TERMINAL_STATES:
        raise TraceValidationError("TRACE_TERMINAL_STATE_INVALID")
    if not isinstance(trace.get("events"), list) or not isinstance(
        trace.get("risk_lineage"), list
    ):
        raise TraceValidationError("TRACE_EVENT_OR_RISK_LINEAGE_INVALID")
    failed_stage = trace.get("failed_stage")
    if terminal_state == "FAILED_VALIDATION":
        try:
            failed_stage = normalize_failure_stage(str(failed_stage))
        except ValueError as exc:
            raise TraceValidationError("TRACE_FAILED_STAGE_INVALID") from exc
        error_path = run_dir / "run_error.json"
        try:
            error = json.loads(error_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TraceValidationError("TRACE_RUN_ERROR_MISSING_OR_INVALID") from exc
        if not isinstance(error, Mapping) or (
            error.get("schema_version") != RUN_ERROR_VERSION
            or error.get("run_id") != trace.get("run_id")
            or error.get("terminal_state") != terminal_state
            or error.get("failed_stage") != failed_stage
        ):
            raise TraceValidationError("TRACE_RUN_ERROR_MISMATCH")
        failed_events = [
            item
            for item in trace.get("events", [])
            if isinstance(item, Mapping) and item.get("stage") == "VALIDATION_FAILED"
        ]
        if not failed_events or (
            failed_events[-1].get("failed_stage") != failed_stage
            or failed_events[-1].get("code") != error.get("code")
        ):
            raise TraceValidationError("TRACE_FAILED_EVENT_MISMATCH")
    elif failed_stage is not None:
        raise TraceValidationError("TRACE_PUBLISHED_FAILED_STAGE_FORBIDDEN")
    artifacts = trace.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise TraceValidationError("TRACE_ARTIFACTS_INVALID")
    for relative, digest in artifacts.items():
        path = run_dir / str(relative)
        if not path.is_file() or digest != file_hash(path):
            raise TraceValidationError(f"TRACE_ARTIFACT_UNRESOLVED:{relative}")

    manifest_path = run_dir / "run_manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file()
        else None
    )
    if manifest is not None and manifest.get("run_id") != trace.get("run_id"):
        raise TraceValidationError("TRACE_RUN_ID_MISMATCH")
    runtime = trace.get("runtime")
    if manifest is not None and manifest.get("execution_replay_supported") is True:
        reference = manifest.get("replay_capsule")
        if not isinstance(reference, Mapping):
            raise TraceValidationError("TRACE_CAPSULE_REFERENCE_MISSING")
        try:
            capsule = validate_replay_capsule(
                run_dir / "replay_capsule", expected_run_id=str(trace.get("run_id"))
            )
        except ValueError as exc:
            raise TraceValidationError(str(exc)) from exc
        if (
            reference.get("manifest_hash") != capsule.get("manifest_hash")
            or reference.get("root_hash") != capsule.get("root_hash")
            or not isinstance(runtime, Mapping)
            or runtime.get("replay_capsule") != reference
        ):
            raise TraceValidationError("TRACE_CAPSULE_REFERENCE_MISMATCH")
    published = terminal_state in {"COMPLETED", "SAFE_NO_TRADE"}
    if published:
        required_runtime = {
            "model",
            "codex_runtime",
            "candidate_version",
            "discovery_hash",
            "version_lock",
        }
        if not isinstance(runtime, Mapping) or not required_runtime <= set(runtime):
            raise TraceValidationError("TRACE_RUNTIME_LINEAGE_INCOMPLETE")

    has_chain = (run_dir / "invocations").is_dir()
    agents = trace.get("agents")
    if not isinstance(agents, list):
        raise TraceValidationError("TRACE_AGENTS_INVALID")
    if has_chain:
        try:
            topology = set(
                validate_runtime_mode(
                    run_mode=str(manifest.get("run_mode", "PRODUCT_COUNCIL")) if manifest else "PRODUCT_COUNCIL",
                    ablation_profile=manifest.get("ablation_profile") if manifest else None,
                )
            )
        except ValueError as exc:
            raise TraceValidationError(str(exc)) from exc
        specialist_topology = topology - {"runtime_cio"}
        by_name = {
            str(item.get("name")): item
            for item in agents
            if isinstance(item, Mapping)
        }
        actual_agents = set(by_name)
        if published:
            expected_agents = topology
        elif failed_stage is not None and stage_at_or_after(
            failed_stage, FailureStage.EXECUTION_PROOF
        ):
            expected_agents = topology
        elif failed_stage in {
            FailureStage.SPECIALIST_VALIDATION.value,
            FailureStage.CIO_SYNTHESIS.value,
        }:
            expected_agents = specialist_topology
        elif failed_stage == FailureStage.SPECIALIST_EXECUTION.value:
            if not actual_agents or not actual_agents <= specialist_topology:
                raise TraceValidationError("TRACE_AGENT_SET_INVALID")
            expected_agents = actual_agents
        else:
            raise TraceValidationError("TRACE_STAGE_HAS_UNEXPECTED_CHAIN")
        if actual_agents != expected_agents:
            raise TraceValidationError("TRACE_AGENT_SET_INVALID")
        required_agent_fields = {
            "version",
            "invocation_id",
            "manifest_hash",
            "agent_sha256",
            "model",
            "codex_runtime",
            "input_hash",
            "task_prompt_hash",
            "instruction_bundle_hash",
            "evidence_ids",
            "skills",
            "tool_permissions",
            "decision_contract",
            "output_schema",
            "output_schema_hash",
        }
        for name, item in by_name.items():
            if not required_agent_fields <= set(item):
                raise TraceValidationError(f"TRACE_AGENT_LINEAGE_INCOMPLETE:{name}")
            output_required = published or (
                failed_stage is not None
                and stage_at_or_after(failed_stage, FailureStage.CIO_SYNTHESIS)
            )
            if output_required and "output_hash" not in item:
                raise TraceValidationError(f"TRACE_AGENT_OUTPUT_LINEAGE_MISSING:{name}")
            invocation_path = run_dir / "invocations" / f"{name}.json"
            input_path = run_dir / "inputs" / f"{name}.json"
            prompt_path = run_dir / "prompts" / f"{name}.txt"
            try:
                invocation = json.loads(invocation_path.read_text(encoding="utf-8"))
                agent_input = json.loads(input_path.read_text(encoding="utf-8"))
                prompt = prompt_path.read_text(encoding="utf-8")
            except (OSError, json.JSONDecodeError) as exc:
                raise TraceValidationError(f"TRACE_AGENT_ARTIFACT_INVALID:{name}") from exc
            if not isinstance(invocation, Mapping) or not isinstance(agent_input, Mapping):
                raise TraceValidationError(f"TRACE_AGENT_ARTIFACT_INVALID:{name}")
            if (
                item.get("manifest_hash") != invocation.get("manifest_hash")
                or item.get("version") != invocation.get("agent", {}).get("version")
                or item.get("agent_sha256") != invocation.get("agent", {}).get("sha256")
                or item.get("model") != invocation.get("model")
                or item.get("input_hash") != canonical_hash(agent_input)
                or item.get("input_hash") != invocation.get("input_hash")
                or item.get("task_prompt_hash") != canonical_hash({"task_prompt": prompt})
                or item.get("task_prompt_hash") != invocation.get("task_prompt_hash")
                or item.get("instruction_bundle_hash") != invocation.get("instruction_bundle_hash")
                or item.get("evidence_ids") != invocation.get("evidence_ids")
                or item.get("skills") != invocation.get("skills")
                or item.get("tool_permissions") != invocation.get("tool_permissions")
                or item.get("decision_contract") != invocation.get("decision_contract")
                or item.get("output_schema") != invocation.get("output_schema")
                or item.get("output_schema_hash") != invocation.get("output_schema_hash")
            ):
                raise TraceValidationError(f"TRACE_AGENT_LINEAGE_HASH_MISMATCH:{name}")
            output_root = "cio" if name == "runtime_cio" else "agents"
            output_path = run_dir / output_root / f"{name}.json"
            if output_path.is_file():
                output = json.loads(output_path.read_text(encoding="utf-8"))
                if item.get("output_hash") != canonical_hash(output):
                    raise TraceValidationError(f"TRACE_AGENT_OUTPUT_HASH_MISMATCH:{name}")
        evidence = trace.get("evidence_lineage")
        if not isinstance(evidence, Mapping) or not {
            "decision_cutoff",
            "allowed_evidence_ids",
            "excluded_evidence_ids",
            "bundle_hash",
            "freshness_policy_version",
            "conflict_policy_version",
        } <= set(evidence):
            raise TraceValidationError("TRACE_EVIDENCE_LINEAGE_INCOMPLETE")
        fixture_path = run_dir / "audit" / "fixture_snapshot.json"
        gate_path = run_dir / "evidence" / "gate.json"
        try:
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            gate = json.loads(gate_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise TraceValidationError("TRACE_PIT_ARTIFACT_MISSING_OR_INVALID") from exc
        expected_gate = run_evidence_gate(fixture, run_id=str(trace["run_id"])).artifact
        if canonical_hash(gate) != canonical_hash(expected_gate):
            raise TraceValidationError("TRACE_PIT_GATE_MISMATCH")
        expected_lineage = {
            "decision_cutoff": gate["decision_cutoff"],
            "allowed_evidence_ids": gate["allowed_evidence_ids"],
            "excluded_evidence_ids": gate["excluded_evidence_ids"],
            "bundle_hash": gate["bundle_hash"],
            "freshness_policy_version": gate["freshness_policy_version"],
            "conflict_policy_version": gate["conflict_policy_version"],
        }
        if evidence != expected_lineage:
            raise TraceValidationError("TRACE_EVIDENCE_LINEAGE_MISMATCH")
        allowed_ids = set(gate["allowed_evidence_ids"])
        evidence_refs: set[str] = set()
        for relative in (
            "agents/runtime_company_analyst.json",
            "agents/runtime_skeptic.json",
            "cio/runtime_cio.json",
            "cio/runtime_cio_revision.json",
            "decision.json",
        ):
            path = run_dir / relative
            if path.is_file():
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    raise TraceValidationError(f"TRACE_EVIDENCE_ARTIFACT_INVALID:{relative}") from exc
                evidence_refs.update(collect_evidence_refs(payload))
        unknown = sorted(evidence_refs - allowed_ids)
        contained_evidence_failure = (
            terminal_state == "FAILED_VALIDATION"
            and failed_stage in {
                FailureStage.SPECIALIST_VALIDATION.value,
                FailureStage.CIO_VALIDATION.value,
                FailureStage.PUBLICATION_VALIDATION.value,
            }
            and not (run_dir / "decision.json").exists()
            and any(item in str(error.get("message", "")) for item in unknown)
        )
        if unknown and not contained_evidence_failure:
            raise TraceValidationError(f"TRACE_EVIDENCE_CLOSURE_FAILED:{','.join(unknown)}")
        if risk_lineage_required(
            terminal_state=terminal_state,
            failed_stage=str(failed_stage) if failed_stage is not None else None,
            has_chain=has_chain,
        ) and not trace.get("risk_lineage"):
            raise TraceValidationError("TRACE_RISK_LINEAGE_MISSING")
        if trace.get("risk_lineage"):
            try:
                validate_risk_lineage_entries(trace["risk_lineage"])
            except ValueError as exc:
                raise TraceValidationError(str(exc)) from exc
            if [item["attempt"] for item in trace["risk_lineage"]] != list(
                range(1, len(trace["risk_lineage"]) + 1)
            ) or any(
                item["run_id"] != trace.get("run_id")
                for item in trace["risk_lineage"]
            ):
                raise TraceValidationError("TRACE_RISK_LINEAGE_SEQUENCE_INVALID")
            if runtime and isinstance(runtime, Mapping):
                version_lock = runtime.get("version_lock")
                expected_policy = (
                    version_lock.get("risk_policy")
                    if isinstance(version_lock, Mapping)
                    else None
                )
                if expected_policy and any(
                    item.get("policy_version") != expected_policy
                    for item in trace["risk_lineage"]
                ):
                    raise TraceValidationError("TRACE_RISK_POLICY_VERSION_MISMATCH")
        proof_required = published or (
            failed_stage is not None
            and stage_at_or_after(failed_stage, FailureStage.CIO_VALIDATION)
        )
        if (
            proof_required
            and manifest is not None
            and manifest.get("authenticity_required") is not False
        ):
            proof = trace.get("codex_execution")
            if not isinstance(proof, Mapping) or not proof.get("proof_hash"):
                raise TraceValidationError("TRACE_CODEX_PROOF_MISSING")
            proof_path = run_dir / "events" / "codex" / "specialist-execution-proof.json"
            try:
                saved_proof = json.loads(proof_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise TraceValidationError("TRACE_CODEX_PROOF_MISSING") from exc
            expected_proof = {
                "schema_version": saved_proof["schema_version"],
                "proof_hash": saved_proof["proof_hash"],
                "parent": saved_proof["parent"],
                "dispatches": saved_proof["dispatches"],
                "children": saved_proof["children"],
                "parallel_dispatch_proven": saved_proof["parallel_dispatch_proven"],
                "independent_sessions_proven": saved_proof["independent_sessions_proven"],
                "specialist_topology": saved_proof.get("specialist_topology", []),
                "portfolio_council_skill_bound": saved_proof.get("portfolio_council_skill_bound"),
                "telemetry": saved_proof.get("telemetry"),
            }
            if proof != expected_proof:
                raise TraceValidationError("TRACE_CODEX_PROOF_MISMATCH")
            telemetry = proof.get("telemetry")
            required_telemetry = {
                "status", "input_tokens", "output_tokens", "cached_tokens", "latency_ms",
                "llm_calls", "model", "trigger_reason", "cache_provenance",
            }
            if (
                not isinstance(telemetry, Mapping)
                or set(telemetry) != required_telemetry
                or telemetry.get("status") != "AVAILABLE"
                or telemetry.get("model") != runtime.get("model")
                or telemetry.get("trigger_reason") != runtime.get("trigger_reason")
                or any(
                    not isinstance(telemetry.get(field), int) or isinstance(telemetry.get(field), bool) or telemetry[field] < 0
                    for field in ("input_tokens", "output_tokens", "cached_tokens", "latency_ms", "llm_calls")
                )
                or telemetry.get("llm_calls", 0) <= 0
            ):
                raise TraceValidationError("TRACE_LLM_TELEMETRY_INCOMPLETE")
            if not trace.get("mcp_events"):
                raise TraceValidationError("TRACE_MCP_LINEAGE_MISSING")
    elif agents or trace.get("risk_lineage") or trace.get("codex_execution"):
        raise TraceValidationError("TRACE_PRE_AGENT_TERMINATION_HAS_RUNTIME_ACTIVITY")


def trace_integrity_report(trace: Mapping[str, Any], *, run_dir: Path) -> dict[str, Any]:
    """Return the canonical report used by every downstream assurance flow."""

    validate_decision_trace(trace, run_dir=run_dir)
    report = {
        "schema_version": "trace-integrity-report/1.0.0",
        "source_run_dir": str(run_dir.resolve()),
        "run_id": trace["run_id"],
        "terminal_state": trace["terminal_state"],
        "failed_stage": trace["failed_stage"],
        "status": "PASS",
        "trace_hash": canonical_hash(trace),
    }
    report["report_hash"] = canonical_hash(report)
    return report
