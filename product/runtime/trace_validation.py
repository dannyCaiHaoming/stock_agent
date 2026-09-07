"""Semantic validation for Decision Trace 2.1.0."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .hashing import file_hash
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
    published = terminal_state in {"COMPLETED", "SAFE_NO_TRADE"}
    runtime = trace.get("runtime")
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
        by_name = {
            str(item.get("name")): item
            for item in agents
            if isinstance(item, Mapping)
        }
        actual_agents = set(by_name)
        if published:
            expected_agents = CHAIN_AGENTS
        elif failed_stage is not None and stage_at_or_after(
            failed_stage, FailureStage.EXECUTION_PROOF
        ):
            expected_agents = CHAIN_AGENTS
        elif failed_stage in {
            FailureStage.SPECIALIST_VALIDATION.value,
            FailureStage.CIO_SYNTHESIS.value,
        }:
            expected_agents = CHAIN_AGENTS - {"runtime_cio"}
        elif failed_stage == FailureStage.SPECIALIST_EXECUTION.value:
            if not actual_agents or not actual_agents <= CHAIN_AGENTS - {"runtime_cio"}:
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
            if not trace.get("mcp_events"):
                raise TraceValidationError("TRACE_MCP_LINEAGE_MISSING")
    elif agents or trace.get("risk_lineage") or trace.get("codex_execution"):
        raise TraceValidationError("TRACE_PRE_AGENT_TERMINATION_HAS_RUNTIME_ACTIVITY")
