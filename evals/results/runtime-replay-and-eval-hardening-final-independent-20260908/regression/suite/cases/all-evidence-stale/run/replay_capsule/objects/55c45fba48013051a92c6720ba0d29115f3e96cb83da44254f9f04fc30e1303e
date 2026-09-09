"""Deterministic artifact replay for a completed native Council run."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .artifact_matrix import validate_artifact_matrix
from .evidence_gate import run_evidence_gate
from .hashing import canonical_hash, file_hash
from .invocation import verify_invocation_manifest
from .risk_runtime import check_cio_draft
from .run_package import _render_report
from .trace_validation import validate_decision_trace
from .replay_capsule import validate_replay_capsule
from .terminal_contract import FailureStage
from .validation import (
    validate_cio_draft,
    validate_company_report,
    validate_skeptic_report,
)
from .runtime_profiles import validate_runtime_mode


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


def _tree_hash(run_dir: Path) -> str:
    return canonical_hash(
        {
            str(path.relative_to(run_dir)): file_hash(path)
            for path in sorted(run_dir.rglob("*"))
            if path.is_file()
        }
    )


def _capsule_hashes(capsule: Mapping[str, Any]) -> dict[str, str]:
    return {str(item["logical_path"]): str(item["sha256"]) for item in capsule["objects"]}


def _frozen_logical_path(path: str, *, product_root: str) -> str:
    candidate = Path(path)
    source_root = Path(product_root)
    try:
        relative = candidate.relative_to(source_root)
    except ValueError as exc:
        raise ReplayError(f"REPLAY_RESOURCE_OUTSIDE_FROZEN_PRODUCT:{path}") from exc
    return (Path("product") / relative).as_posix()


def _verify_frozen_invocation(
    invocation: Mapping[str, Any],
    *,
    agent_input: Mapping[str, Any],
    source_product_root: str,
    capsule: Mapping[str, Any],
    run_dir: Path,
) -> None:
    body = dict(invocation)
    claimed = body.pop("manifest_hash", None)
    if claimed != canonical_hash(body) or invocation.get("input_hash") != canonical_hash(agent_input):
        raise ReplayError("REPLAY_INVOCATION_HASH_MISMATCH")
    frozen = _capsule_hashes(capsule)
    agent = invocation.get("agent")
    if not isinstance(agent, Mapping):
        raise ReplayError("REPLAY_AGENT_RESOURCE_INVALID")
    if frozen.get(_frozen_logical_path(str(agent.get("path", "")), product_root=source_product_root)) != agent.get("sha256"):
        raise ReplayError("REPLAY_AGENT_RESOURCE_MISMATCH")
    for skill in invocation.get("skills", []):
        if not isinstance(skill, Mapping) or frozen.get(
            _frozen_logical_path(str(skill.get("path", "")), product_root=source_product_root)
        ) != skill.get("sha256"):
            raise ReplayError("REPLAY_SKILL_RESOURCE_MISMATCH")
    contract = invocation.get("decision_contract")
    contract_logical = (
        _frozen_logical_path(str(contract.get("path", "")), product_root=source_product_root)
        if isinstance(contract, Mapping)
        else ""
    )
    contract_object_hash = frozen.get(contract_logical)
    contract_payload = (
        _read_object(run_dir / "replay_capsule" / "objects" / contract_object_hash)
        if contract_object_hash
        else None
    )
    if not isinstance(contract, Mapping) or contract_payload is None or canonical_hash(contract_payload) != contract.get("sha256"):
        raise ReplayError("REPLAY_DECISION_CONTRACT_MISMATCH")
    output_schema = Path(str(invocation.get("output_schema", ""))).resolve()
    if output_schema.is_relative_to(run_dir):
        actual_hash = file_hash(output_schema)
    else:
        logical = _frozen_logical_path(str(output_schema), product_root=source_product_root)
        actual_hash = frozen.get(logical)
    if actual_hash != invocation.get("output_schema_hash"):
        raise ReplayError("REPLAY_OUTPUT_SCHEMA_MISMATCH")


def replay_run(repository_root: Path, *, run_dir: Path) -> dict[str, Any]:
    """Re-run deterministic gates without invoking an LLM or changing the run."""

    run_dir = run_dir.resolve()
    source_tree_hash = _tree_hash(run_dir)
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
    capsule: dict[str, Any] | None = None
    if manifest.get("execution_replay_supported") is True:
        capsule = validate_replay_capsule(
            run_dir / "replay_capsule", expected_run_id=str(manifest["run_id"])
        )
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
        topology = validate_runtime_mode(
            run_mode=str(manifest.get("run_mode", "PRODUCT_COUNCIL")),
            ablation_profile=manifest.get("ablation_profile"),
        )
        specialists = tuple(agent for agent in topology if agent != "runtime_cio")
        specialist_validators = {
            "runtime_company_analyst": validate_company_report,
            "runtime_skeptic": validate_skeptic_report,
        }
        reports: dict[str, dict[str, Any]] = {}
        for agent_name in specialists:
            validator = specialist_validators[agent_name]
            agent_input = _read_object(run_dir / "inputs" / f"{agent_name}.json")
            invocation = _read_object(
                run_dir / "invocations" / f"{agent_name}.json"
            )
            if capsule is None:
                verify_invocation_manifest(repository_root, invocation, agent_input=agent_input)
            else:
                _verify_frozen_invocation(
                    invocation,
                    agent_input=agent_input,
                    source_product_root=str(manifest["discovery"]["product_root"]),
                    capsule=capsule,
                    run_dir=run_dir,
                )
            report = _read_object(run_dir / "agents" / f"{agent_name}.json")
            validator(report, run_id=str(manifest["run_id"]), manifest=invocation)
            reports[agent_name] = report
        cio_input = _read_object(run_dir / "inputs" / "runtime_cio.json")
        cio_invocation = _read_object(run_dir / "invocations" / "runtime_cio.json")
        if capsule is None:
            verify_invocation_manifest(repository_root, cio_invocation, agent_input=cio_input)
        else:
            _verify_frozen_invocation(
                cio_invocation,
                agent_input=cio_input,
                source_product_root=str(manifest["discovery"]["product_root"]),
                capsule=capsule,
                run_dir=run_dir,
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
            expected_report_agents=specialists,
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
        "mode": "ARTIFACT_REPLAY",
        "llm_calls": 0,
        "source_run_dir": str(run_dir),
        "source_run_id": manifest["run_id"],
        "terminal_state": decision["terminal_state"],
        "status": "PASSED",
        "checks": checks,
        "decision_hash": canonical_hash(decision),
        "report_hash": canonical_hash({"report": rendered}),
        "trace_hash": canonical_hash(trace),
        "source_tree_hash": source_tree_hash,
        "capsule_manifest_hash": capsule["manifest_hash"] if capsule else None,
        "execution_replay_ready": capsule is not None,
    }
    if _tree_hash(run_dir) != source_tree_hash:
        raise ReplayError("REPLAY_SOURCE_MUTATED")
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
    capsule: dict[str, Any] | None = None
    if manifest is not None and manifest.get("execution_replay_supported") is True:
        capsule = validate_replay_capsule(
            run_dir / "replay_capsule", expected_run_id=str(trace["run_id"])
        )

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
        if capsule is None:
            verify_invocation_manifest(repository_root, invocation, agent_input=agent_input)
        else:
            _verify_frozen_invocation(
                invocation,
                agent_input=agent_input,
                source_product_root=str(manifest["discovery"]["product_root"]),
                capsule=capsule,
                run_dir=run_dir,
            )
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
        if capsule is None:
            verify_invocation_manifest(
                repository_root, cio_invocation, agent_input=cio_input
            )
        else:
            _verify_frozen_invocation(
                cio_invocation,
                agent_input=cio_input,
                source_product_root=str(manifest["discovery"]["product_root"]),
                capsule=capsule,
                run_dir=run_dir,
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
                if specialist_reports else {},
                expected_report_agents=tuple(specialist_reports),
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
        "mode": "ARTIFACT_REPLAY",
        "llm_calls": 0,
        "source_run_dir": str(run_dir),
        "source_run_id": trace["run_id"],
        "source_terminal_state": "FAILED_VALIDATION",
        "failed_stage": failed_stage,
        "original_error_code": error["code"],
        "status": "PASSED",
        "checks": checks,
        "trace_hash": canonical_hash(trace),
        "source_tree_hash": _tree_hash(run_dir),
        "capsule_manifest_hash": capsule["manifest_hash"] if capsule else None,
        "execution_replay_ready": capsule is not None,
    }
    result["replay_hash"] = canonical_hash(result)
    return result


def write_replay_result(result: Mapping[str, Any], *, output_path: Path) -> None:
    if output_path.exists():
        raise ReplayError("REPLAY_OUTPUT_ALREADY_EXISTS")
    source_dir = Path(str(result.get("source_run_dir", ""))).resolve()
    if output_path.resolve().is_relative_to(source_dir):
        raise ReplayError("REPLAY_OUTPUT_MUST_BE_EXTERNAL")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
