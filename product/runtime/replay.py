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
from .validation import (
    validate_cio_draft,
    validate_company_report,
    validate_skeptic_report,
)


REPLAY_VERSION = "native-artifact-replay/2.0.0"


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
    manifest = _read_object(run_dir / "run_manifest.json")
    trace = _read_object(run_dir / "decision_trace.json")
    matrix = validate_artifact_matrix(run_dir, require_eval=False)
    validate_decision_trace(trace, run_dir=run_dir)
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


def write_replay_result(result: Mapping[str, Any], *, output_path: Path) -> None:
    if output_path.exists():
        raise ReplayError("REPLAY_OUTPUT_ALREADY_EXISTS")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
