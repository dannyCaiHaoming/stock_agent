"""Deterministic artifact replay for a completed native Council run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .artifact_matrix import validate_artifact_matrix
from .evidence_gate import run_evidence_gate
from .hashing import canonical_hash
from .invocation import verify_invocation_manifest
from .risk_runtime import check_cio_draft
from .run_package import _render_report
from .trace_validation import validate_decision_trace
from .terminal_contract import FailureStage
from .validation import (
    validate_cio_draft,
    validate_company_report,
    validate_skeptic_report,
)


REPLAY_VERSION = "native-artifact-replay/2.1.0"


class ReplayError(ValueError):
    """Raised when saved artifacts cannot be reproduced deterministically."""


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReplayError(f"REPLAY_ARTIFACT_INVALID:{path.name}") from exc
    if not isinstance(value, Mapping):
        raise ReplayError(f"REPLAY_ARTIFACT_NOT_OBJECT:{path.name}")
    return dict(value)


def replay_run(repository_root: Path, *, run_dir: Path) -> dict[str, Any]:
    """Re-run deterministic gates without invoking an LLM or changing the run."""

    run_dir = run_dir.resolve()
    trace = _read_object(run_dir / "decision_trace.json")
    matrix = validate_artifact_matrix(run_dir, require_eval=False)
    validate_decision_trace(trace, run_dir=run_dir)
    if trace.get("terminal_state") == "FAILED_VALIDATION":
        return _replay_failed_run(
            repository_root,
            run_dir=run_dir,
            trace=trace,
            matrix=matrix,
        )
    manifest = _read_object(run_dir / "run_manifest.json")
    decision = _read_object(run_dir / "decision.json")
    if manifest.get("run_id") != decision.get("run_id"):
        raise ReplayError("REPLAY_RUN_ID_MISMATCH")
    checks: dict[str, Any] = {
        "artifact_matrix": matrix["matrix_hash"],
        "trace_lineage": "PASSED",
        "report_render": "PASSED",
    }
    rendered = _render_report(decision)
    if rendered != (run_dir / "report.md").read_text(encoding="utf-8"):
        raise ReplayError("REPLAY_REPORT_MISMATCH")

    fixture_path = run_dir / "audit" / "fixture_snapshot.json"
    gate_path = run_dir / "evidence" / "gate.json"
    if fixture_path.is_file() and gate_path.is_file():
        fixture = _read_object(fixture_path)
        gate = _read_object(gate_path)
        replayed_gate = run_evidence_gate(fixture, run_id=str(manifest["run_id"])).artifact
        if canonical_hash(replayed_gate) != canonical_hash(gate):
            raise ReplayError("REPLAY_EVIDENCE_GATE_MISMATCH")
        checks["evidence_gate_hash"] = canonical_hash(replayed_gate)

    if (run_dir / "invocations").is_dir():
        specialist_validators = {
            "runtime_company_analyst": validate_company_report,
            "runtime_skeptic": validate_skeptic_report,
        }
        reports: dict[str, dict[str, Any]] = {}
        for agent_name, validator in specialist_validators.items():
            agent_input = _read_object(run_dir / "inputs" / f"{agent_name}.json")
            invocation = _read_object(
                run_dir / "invocations" / f"{agent_name}.json"
            )
            verify_invocation_manifest(
                repository_root,
                invocation,
                agent_input=agent_input,
            )
            report = _read_object(run_dir / "agents" / f"{agent_name}.json")
            validator(report, run_id=str(manifest["run_id"]), manifest=invocation)
            reports[agent_name] = report
        cio_input = _read_object(run_dir / "inputs" / "runtime_cio.json")
        cio_invocation = _read_object(run_dir / "invocations" / "runtime_cio.json")
        verify_invocation_manifest(
            repository_root,
            cio_invocation,
            agent_input=cio_input,
        )
        draft_path = (
            run_dir / "cio" / "runtime_cio_revision.json"
            if (run_dir / "risk" / "check-2.json").is_file()
            else run_dir / "cio" / "runtime_cio.json"
        )
        risk_path = (
            run_dir / "risk" / "check-2.json"
            if draft_path.name == "runtime_cio_revision.json"
            else run_dir / "risk" / "check-1.json"
        )
        draft = _read_object(draft_path)
        validate_cio_draft(
            draft,
            run_id=str(manifest["run_id"]),
            manifest=cio_invocation,
            report_hashes={
                name: canonical_hash(report) for name, report in reports.items()
            },
        )
        fixture = _read_object(fixture_path)
        replayed_risk = check_cio_draft(
            fixture,
            draft,
            run_id=str(manifest["run_id"]),
        )
        saved_risk = _read_object(risk_path)
        if canonical_hash(replayed_risk) != canonical_hash(saved_risk):
            raise ReplayError("REPLAY_RISK_RESULT_MISMATCH")
        checks.update(
            {
                "specialist_outputs": {
                    name: canonical_hash(report) for name, report in reports.items()
                },
                "cio_draft_hash": canonical_hash(draft),
                "risk_result_hash": canonical_hash(replayed_risk),
            }
        )

    result = {
        "schema_version": REPLAY_VERSION,
        "source_run_id": manifest["run_id"],
        "terminal_state": decision["terminal_state"],
        "status": "PASSED",
        "checks": checks,
        "decision_hash": canonical_hash(decision),
        "report_hash": canonical_hash({"report": rendered}),
        "trace_hash": canonical_hash(trace),
    }
    result["replay_hash"] = canonical_hash(result)
    return result


def _replay_failed_run(
    repository_root: Path,
    *,
    run_dir: Path,
    trace: Mapping[str, Any],
    matrix: Mapping[str, Any],
) -> dict[str, Any]:
    """Diagnose a failed package without inventing downstream artifacts."""

    error = _read_object(run_dir / "run_error.json")
    failed_stage = str(error["failed_stage"])
    checks: dict[str, Any] = {
        "artifact_matrix": matrix["matrix_hash"],
        "trace_lineage": "PASSED",
        "run_error_consistency": "PASSED",
        "published_artifacts_absent": "PASSED",
    }
    manifest_path = run_dir / "run_manifest.json"
    manifest = _read_object(manifest_path) if manifest_path.is_file() else None
    if manifest is not None and manifest.get("run_id") != trace.get("run_id"):
        raise ReplayError("REPLAY_RUN_ID_MISMATCH")

    fixture_path = run_dir / "audit" / "fixture_snapshot.json"
    gate_path = run_dir / "evidence" / "gate.json"
    if fixture_path.is_file() and gate_path.is_file():
        fixture = _read_object(fixture_path)
        gate = _read_object(gate_path)
        replayed_gate = run_evidence_gate(
            fixture, run_id=str(trace["run_id"])
        ).artifact
        if canonical_hash(replayed_gate) != canonical_hash(gate):
            raise ReplayError("REPLAY_EVIDENCE_GATE_MISMATCH")
        checks["evidence_gate_hash"] = canonical_hash(replayed_gate)

    specialist_errors: list[str] = []
    specialist_reports: dict[str, dict[str, Any]] = {}
    for agent_name, validator in {
        "runtime_company_analyst": validate_company_report,
        "runtime_skeptic": validate_skeptic_report,
    }.items():
        input_path = run_dir / "inputs" / f"{agent_name}.json"
        invocation_path = run_dir / "invocations" / f"{agent_name}.json"
        report_path = run_dir / "agents" / f"{agent_name}.json"
        if not (input_path.is_file() and invocation_path.is_file()):
            continue
        agent_input = _read_object(input_path)
        invocation = _read_object(invocation_path)
        verify_invocation_manifest(repository_root, invocation, agent_input=agent_input)
        if not report_path.is_file():
            specialist_errors.append(f"MISSING_REPORT:{agent_name}")
            continue
        report = _read_object(report_path)
        try:
            validator(report, run_id=str(trace["run_id"]), manifest=invocation)
        except ValueError as exc:
            specialist_errors.append(str(exc))
        else:
            specialist_reports[agent_name] = report
    if specialist_reports:
        checks["specialist_outputs"] = {
            name: canonical_hash(report)
            for name, report in sorted(specialist_reports.items())
        }
    if failed_stage == FailureStage.SPECIALIST_VALIDATION.value:
        if not specialist_errors:
            raise ReplayError("REPLAY_SPECIALIST_FAILURE_NOT_REPRODUCED")
        checks["specialist_failure"] = specialist_errors

    cio_error: str | None = None
    cio_path = run_dir / "cio" / "runtime_cio.json"
    cio_input_path = run_dir / "inputs" / "runtime_cio.json"
    cio_invocation_path = run_dir / "invocations" / "runtime_cio.json"
    if cio_path.is_file() and cio_input_path.is_file() and cio_invocation_path.is_file():
        cio_input = _read_object(cio_input_path)
        cio_invocation = _read_object(cio_invocation_path)
        verify_invocation_manifest(
            repository_root, cio_invocation, agent_input=cio_input
        )
        draft = _read_object(cio_path)
        try:
            validate_cio_draft(
                draft,
                run_id=str(trace["run_id"]),
                manifest=cio_invocation,
                report_hashes={
                    name: canonical_hash(report)
                    for name, report in specialist_reports.items()
                }
                if len(specialist_reports) == 2
                else None,
            )
        except ValueError as exc:
            cio_error = str(exc)
        else:
            checks["cio_draft_hash"] = canonical_hash(draft)
    if failed_stage == FailureStage.CIO_VALIDATION.value:
        if cio_error is None:
            raise ReplayError("REPLAY_CIO_FAILURE_NOT_REPRODUCED")
        if cio_error not in str(error.get("message", "")):
            raise ReplayError("REPLAY_CIO_FAILURE_CATEGORY_MISMATCH")
        checks["cio_failure"] = cio_error

    if failed_stage == FailureStage.RISK_ENGINE.value:
        entries = trace.get("risk_lineage", [])
        if not entries or entries[-1].get("status") != "FAILED":
            raise ReplayError("REPLAY_RISK_FAILURE_LINEAGE_MISSING")
        checks["risk_failure"] = entries[-1]["error"]

    result = {
        "schema_version": REPLAY_VERSION,
        "source_run_id": trace["run_id"],
        "source_terminal_state": "FAILED_VALIDATION",
        "failed_stage": failed_stage,
        "original_error_code": error["code"],
        "status": "PASSED",
        "checks": checks,
        "trace_hash": canonical_hash(trace),
    }
    result["replay_hash"] = canonical_hash(result)
    return result


def write_replay_result(result: Mapping[str, Any], *, output_path: Path) -> None:
    if output_path.exists():
        raise ReplayError("REPLAY_OUTPUT_ALREADY_EXISTS")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
