"""Semantic validation for Decision Trace 2.0.0."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .hashing import file_hash


TRACE_KEYS = {
    "schema_version",
    "run_id",
    "terminal_state",
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
    if trace.get("schema_version") != "decision-trace/2.0.0":
        raise TraceValidationError("TRACE_SCHEMA_VERSION_INVALID")
    if trace.get("terminal_state") not in TERMINAL_STATES:
        raise TraceValidationError("TRACE_TERMINAL_STATE_INVALID")
    if not isinstance(trace.get("events"), list) or not isinstance(trace.get("risk_lineage"), list):
        raise TraceValidationError("TRACE_EVENT_OR_RISK_LINEAGE_INVALID")
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
    published = trace.get("terminal_state") in {"COMPLETED", "SAFE_NO_TRADE"}
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
        if set(by_name) != CHAIN_AGENTS:
            raise TraceValidationError("TRACE_AGENT_SET_INVALID")
        required_agent_fields = {
            "version",
            "invocation_id",
            "manifest_hash",
            "agent_sha256",
            "model",
            "codex_runtime",
            "input_hash",
            "output_hash",
            "task_prompt_hash",
            "instruction_bundle_hash",
            "evidence_ids",
            "skills",
            "tool_permissions",
        }
        for name, item in by_name.items():
            if not required_agent_fields <= set(item):
                raise TraceValidationError(f"TRACE_AGENT_LINEAGE_INCOMPLETE:{name}")
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
        if not trace.get("risk_lineage"):
            raise TraceValidationError("TRACE_RISK_LINEAGE_MISSING")
        if manifest is not None and manifest.get("authenticity_required") is not False:
            proof = trace.get("codex_execution")
            if not isinstance(proof, Mapping) or not proof.get("proof_hash"):
                raise TraceValidationError("TRACE_CODEX_PROOF_MISSING")
            if not trace.get("mcp_events"):
                raise TraceValidationError("TRACE_MCP_LINEAGE_MISSING")
    elif agents or trace.get("risk_lineage") or trace.get("codex_execution"):
        raise TraceValidationError("TRACE_PRE_AGENT_TERMINATION_HAS_RUNTIME_ACTIVITY")
