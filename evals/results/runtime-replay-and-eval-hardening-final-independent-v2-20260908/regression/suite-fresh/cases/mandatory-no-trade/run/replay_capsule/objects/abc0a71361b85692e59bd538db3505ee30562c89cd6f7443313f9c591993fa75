"""Versioned terminal-state and failure-stage contracts."""

from __future__ import annotations

from enum import StrEnum
from typing import Iterable

from .hashing import canonical_hash

TRACE_VERSION = "decision-trace/2.1.0"
RUN_ERROR_VERSION = "run-error/2.1.0"
RISK_LINEAGE_VERSION = "risk-lineage/2.1.0"


class FailureStage(StrEnum):
    PREFLIGHT = "PREFLIGHT"
    EVIDENCE_GATE = "EVIDENCE_GATE"
    SPECIALIST_EXECUTION = "SPECIALIST_EXECUTION"
    SPECIALIST_VALIDATION = "SPECIALIST_VALIDATION"
    CIO_SYNTHESIS = "CIO_SYNTHESIS"
    EXECUTION_PROOF = "EXECUTION_PROOF"
    CIO_VALIDATION = "CIO_VALIDATION"
    RISK_ENGINE = "RISK_ENGINE"
    PUBLICATION_VALIDATION = "PUBLICATION_VALIDATION"


FAILURE_STAGE_ORDER = {stage.value: index for index, stage in enumerate(FailureStage)}


def normalize_failure_stage(stage: FailureStage | str) -> str:
    value = stage.value if isinstance(stage, FailureStage) else str(stage)
    if value not in FAILURE_STAGE_ORDER:
        raise ValueError(f"UNKNOWN_FAILED_STAGE:{value}")
    return value


def stage_at_or_after(stage: FailureStage | str, boundary: FailureStage) -> bool:
    return FAILURE_STAGE_ORDER[normalize_failure_stage(stage)] >= FAILURE_STAGE_ORDER[
        boundary.value
    ]


def failure_stage_required_files(stage: FailureStage | str) -> set[str]:
    """Return artifacts completed before entering the named failed stage."""

    value = normalize_failure_stage(stage)
    required_by_stage: dict[str, set[str]] = {
        FailureStage.PREFLIGHT.value: set(),
        FailureStage.EVIDENCE_GATE.value: {
            "run_manifest.json",
            "audit/fixture_snapshot.json",
        },
        FailureStage.SPECIALIST_EXECUTION.value: {
            "run_manifest.json",
            "audit/fixture_snapshot.json",
            "evidence/gate.json",
        },
        FailureStage.SPECIALIST_VALIDATION.value: {
            "run_manifest.json",
            "audit/fixture_snapshot.json",
            "evidence/gate.json",
            "inputs/runtime_company_analyst.json",
            "inputs/runtime_skeptic.json",
            "invocations/runtime_company_analyst.json",
            "invocations/runtime_skeptic.json",
            "prompts/runtime_company_analyst.txt",
            "prompts/runtime_skeptic.txt",
        },
        FailureStage.CIO_SYNTHESIS.value: {
            "agents/runtime_company_analyst.json",
            "agents/runtime_skeptic.json",
        },
        FailureStage.EXECUTION_PROOF.value: {
            "inputs/runtime_cio.json",
            "invocations/runtime_cio.json",
            "prompts/runtime_cio.txt",
            "cio/runtime_cio.json",
        },
        FailureStage.CIO_VALIDATION.value: set(),
        FailureStage.RISK_ENGINE.value: set(),
        FailureStage.PUBLICATION_VALIDATION.value: {
            "risk/check-1.json",
        },
    }
    cumulative: set[str] = set()
    for candidate in FailureStage:
        cumulative.update(required_by_stage[candidate.value])
        if candidate.value == value:
            return cumulative
    raise AssertionError("unreachable failure stage")


def risk_lineage_required(*, terminal_state: str, failed_stage: str | None, has_chain: bool) -> bool:
    if terminal_state in {"COMPLETED", "SAFE_NO_TRADE"}:
        return has_chain
    if terminal_state == "FAILED_VALIDATION" and failed_stage is not None:
        return stage_at_or_after(failed_stage, FailureStage.RISK_ENGINE)
    return False


def validate_risk_lineage_entries(entries: Iterable[object]) -> None:
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("TRACE_RISK_LINEAGE_ENTRY_INVALID")
        required = {
            "schema_version",
            "run_id",
            "attempt",
            "status",
            "policy_version",
            "input_hash",
            "result_hash",
            "result",
            "error",
        }
        if set(entry) != required:
            raise ValueError("TRACE_RISK_LINEAGE_ENTRY_INVALID")
        if entry["schema_version"] != RISK_LINEAGE_VERSION:
            raise ValueError("TRACE_RISK_LINEAGE_VERSION_INVALID")
        if (
            not isinstance(entry["run_id"], str)
            or not entry["run_id"]
            or not isinstance(entry["attempt"], int)
            or isinstance(entry["attempt"], bool)
            or entry["attempt"] < 1
            or not isinstance(entry["policy_version"], str)
            or not entry["policy_version"]
            or not isinstance(entry["input_hash"], str)
            or len(entry["input_hash"]) != 64
        ):
            raise ValueError("TRACE_RISK_LINEAGE_IDENTITY_INVALID")
        if entry["status"] not in {"COMPLETED", "FAILED"}:
            raise ValueError("TRACE_RISK_LINEAGE_STATUS_INVALID")
        if entry["status"] == "COMPLETED":
            if not isinstance(entry["result"], dict) or not entry["result_hash"]:
                raise ValueError("TRACE_RISK_LINEAGE_RESULT_MISSING")
            if canonical_hash(entry["result"]) != entry["result_hash"]:
                raise ValueError("TRACE_RISK_LINEAGE_RESULT_HASH_INVALID")
            if entry["error"] is not None:
                raise ValueError("TRACE_RISK_LINEAGE_ERROR_INVALID")
        else:
            if entry["result"] is not None or entry["result_hash"] is not None:
                raise ValueError("TRACE_RISK_LINEAGE_FAILED_RESULT_FORBIDDEN")
            if not isinstance(entry["error"], str) or not entry["error"]:
                raise ValueError("TRACE_RISK_LINEAGE_ERROR_MISSING")
