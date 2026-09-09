"""Artifact-driven evaluation for native fixture Council runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .artifact_matrix import validate_artifact_matrix
from .execution_proof import verify_specialist_execution_proof
from .hashing import canonical_hash, file_hash
from .replay import replay_run
from .risk_runtime import check_cio_draft
from .trace_validation import validate_decision_trace
from .validation import collect_evidence_refs


EVAL_VERSION = "native-council-eval/2.0.0"
EVAL_SCOPE = (
    "仅验证结构化正确性、证据血缘、Skeptic 独立非重复贡献、CIO 显式消费与硬风控；"
    "不评价市场收益、Alpha 或统计预测能力。"
)


class NativeEvalError(ValueError):
    """Raised when an actual run does not satisfy fixture invariants."""


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise NativeEvalError(f"EVAL_ARTIFACT_INVALID:{path.name}") from exc
    if not isinstance(value, Mapping):
        raise NativeEvalError(f"EVAL_ARTIFACT_NOT_OBJECT:{path.name}")
    return dict(value)


def _read_events(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise NativeEvalError("EVAL_MCP_EVENTS_MISSING") from exc
    events = []
    for line in lines:
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise NativeEvalError("EVAL_MCP_EVENT_INVALID")
        events.append(dict(value))
    return events


def _nonduplicate_skeptic_contribution(
    analyst: Mapping[str, Any], skeptic: Mapping[str, Any]
) -> bool:
    analyst_text = {
        str(item.get("statement", "")).strip().casefold()
        for item in analyst.get("claims", [])
        if isinstance(item, Mapping)
    } | {str(item).strip().casefold() for item in analyst.get("data_gaps", [])}
    skeptic_text = {
        str(item.get("statement", "")).strip().casefold()
        for item in skeptic.get("challenges", [])
        if isinstance(item, Mapping)
    } | {str(item).strip().casefold() for item in skeptic.get("data_gaps", [])}
    return bool({item for item in skeptic_text if item} - analyst_text)


def validate_native_eval_result(result: Mapping[str, Any]) -> None:
    required = {
        "schema_version",
        "run_id",
        "fixture_id",
        "terminal_state",
        "status",
        "scope",
        "checks",
        "source_hashes",
        "eval_hash",
    }
    if set(result) != required:
        raise NativeEvalError("EVAL_RESULT_KEYS_INVALID")
    if result.get("schema_version") != EVAL_VERSION or result.get("status") != "PASSED":
        raise NativeEvalError("EVAL_RESULT_STATUS_INVALID")
    if result.get("terminal_state") not in {"COMPLETED", "SAFE_NO_TRADE"}:
        raise NativeEvalError("EVAL_TERMINAL_STATE_INVALID")
    if result.get("scope") != EVAL_SCOPE:
        raise NativeEvalError("EVAL_SCOPE_OVERCLAIM_OR_DRIFT")
    checks = result.get("checks")
    if not isinstance(checks, Mapping) or len(checks) < 5:
        raise NativeEvalError("EVAL_CHECKS_INVALID")
    forbidden_claims = {
        "market_outperformance",
        "alpha_improvement",
        "predictive_gain",
        "statistical_significance",
    }
    if forbidden_claims & set(str(key) for key in checks):
        raise NativeEvalError("EVAL_PERFORMANCE_CLAIM_FORBIDDEN")
    hashes = result.get("source_hashes")
    if not isinstance(hashes, Mapping) or set(hashes) != {
        "matrix",
        "replay",
        "trace",
        "decision",
    }:
        raise NativeEvalError("EVAL_SOURCE_HASHES_INVALID")
    if any(
        not isinstance(digest, str)
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        for digest in hashes.values()
    ):
        raise NativeEvalError("EVAL_SOURCE_HASH_INVALID")
    body = dict(result)
    claimed_hash = body.pop("eval_hash", None)
    if claimed_hash != canonical_hash(body):
        raise NativeEvalError("EVAL_HASH_MISMATCH")


def evaluate_run(
    repository_root: Path,
    *,
    run_dir: Path,
    allow_test_artifacts: bool = False,
) -> dict[str, Any]:
    """Evaluate actual files; never infer success from directory structure alone."""

    run_dir = run_dir.resolve()
    manifest = _read_object(run_dir / "run_manifest.json")
    trace = _read_object(run_dir / "decision_trace.json")
    validate_decision_trace(trace, run_dir=run_dir)
    matrix = validate_artifact_matrix(run_dir, require_eval=False)
    replay = replay_run(repository_root, run_dir=run_dir)
    gate_path = run_dir / "evidence" / "gate.json"
    gate = _read_object(gate_path) if gate_path.is_file() else None
    checks: dict[str, Any] = {
        "artifact_matrix": "PASSED",
        "trace_lineage": "PASSED",
        "artifact_replay": "PASSED",
        "advisory_only": "PASSED",
        "no_fixed_investment_outcome": "PASSED",
    }
    decision = _read_object(run_dir / "decision.json")
    if decision.get("advisory_only") is not True:
        raise NativeEvalError("EVAL_ADVISORY_ONLY_FAILED")

    has_chain = (run_dir / "invocations").is_dir()
    if has_chain:
        if manifest.get("authenticity_required") is False and not allow_test_artifacts:
            raise NativeEvalError("TEST_ONLY_RUN_CANNOT_PASS_NATIVE_EVAL")
        manifests = {
            agent: _read_object(run_dir / "invocations" / f"{agent}.json")
            for agent in ("runtime_company_analyst", "runtime_skeptic")
        }
        reports = {
            agent: _read_object(run_dir / "agents" / f"{agent}.json")
            for agent in manifests
        }
        if manifest.get("authenticity_required") is not False:
            proof = _read_object(
                run_dir / "events" / "codex" / "specialist-execution-proof.json"
            )
            events = _read_events(run_dir / "events" / "mcp" / "events.jsonl")
            verify_specialist_execution_proof(
                proof,
                invocation_manifests=manifests,
                reports=reports,
                mcp_events=events,
            )
            checks["native_agent_skill_mcp_authenticity"] = "PASSED"
        else:
            checks["native_agent_skill_mcp_authenticity"] = "TEST_ONLY_BYPASS"
        if not _nonduplicate_skeptic_contribution(
            reports["runtime_company_analyst"], reports["runtime_skeptic"]
        ):
            raise NativeEvalError("SKEPTIC_NONDUPLICATE_CONTRIBUTION_MISSING")
        checks["skeptic_independent_contribution"] = "PASSED"
        if not trace.get("risk_lineage"):
            raise NativeEvalError("ACTUAL_COUNCIL_RISK_PASSAGE_MISSING")
        checks["actual_council_risk_passage"] = "PASSED"

    fixture_id = str(manifest.get("fixture_id", ""))
    if fixture_id == "future-or-stale-v1":
        if gate is None or not gate.get("excluded_evidence_ids"):
            raise NativeEvalError("FUTURE_STALE_FILTERING_NOT_PROVEN")
        if decision.get("terminal_state") != "SAFE_NO_TRADE" or has_chain:
            raise NativeEvalError("FUTURE_STALE_SAFE_TERMINATION_FAILED")
        reasons = {
            str(item.get("evidence_id")): set(item.get("reason_codes", []))
            for item in gate.get("excluded", [])
            if isinstance(item, Mapping)
        }
        expected = {
            "ev-future-asof": {"FUTURE_AS_OF", "FUTURE_RETRIEVAL"},
            "ev-future-retrieval": {"FUTURE_RETRIEVAL"},
            "ev-stale-update": {"STALE"},
        }
        if reasons != expected:
            raise NativeEvalError("FUTURE_STALE_REASON_CODES_INEXACT")
        checks["future_stale_exact_filtering"] = "PASSED"
    elif fixture_id == "evidence-conflict-v1":
        cio = _read_object(run_dir / "cio" / "runtime_cio.json")
        if gate is None or not gate.get("conflicts") or not cio.get("conflicts"):
            raise NativeEvalError("CONFLICT_CONSUMPTION_NOT_PROVEN")
        conflict_ids = {
            str(evidence_id)
            for conflict in gate["conflicts"]
            if isinstance(conflict, Mapping)
            for evidence_id in conflict.get("evidence_ids", [])
        }
        source_ids = {
            str(source_id)
            for conflict in gate["conflicts"]
            if isinstance(conflict, Mapping)
            for source_id in conflict.get("source_ids", [])
        }
        if len(conflict_ids) < 2 or len(source_ids) < 2:
            raise NativeEvalError("INDEPENDENT_CONFLICT_SOURCES_MISSING")
        if any(
            not (collect_evidence_refs(report) & conflict_ids)
            for report in reports.values()
        ):
            raise NativeEvalError("SPECIALIST_CONFLICT_SOURCE_COVERAGE_MISSING")
        cio_conflict_refs = {
            str(evidence_id)
            for conflict in cio["conflicts"]
            if isinstance(conflict, Mapping)
            for evidence_id in conflict.get("evidence_refs", [])
        }
        if not conflict_ids <= cio_conflict_refs:
            raise NativeEvalError("CIO_CONFLICT_EVIDENCE_CONSUMPTION_MISSING")
        if not cio.get("unresolved_questions") or not cio.get("invalidation_conditions"):
            raise NativeEvalError("CIO_CONFLICT_DECISION_IMPACT_MISSING")
        checks["conflict_preserved_and_consumed"] = "PASSED"
    elif fixture_id == "risk-veto-v1":
        fixture = _read_object(run_dir / "audit" / "fixture_snapshot.json")
        boundary_name = fixture.get("boundary_draft_fixture")
        boundary_path = Path(str(manifest["fixture"])).resolve().parent / str(boundary_name)
        boundary = _read_object(boundary_path)
        if boundary.get("producer") != "fixture" or boundary.get("not_llm_output") is not True:
            raise NativeEvalError("RISK_BOUNDARY_PRODUCER_INVALID")
        first = check_cio_draft(fixture, boundary, run_id="eval-risk-boundary")
        second = check_cio_draft(fixture, boundary, run_id="eval-risk-boundary")
        if first != second or first.get("check", {}).get("status") != "REJECTED":
            raise NativeEvalError("RISK_BOUNDARY_NOT_DETERMINISTICALLY_VETOED")
        if first.get("final_action") != "NO_TRADE" or first.get("veto_reason") != "RISK_VETO":
            raise NativeEvalError("RISK_BOUNDARY_VETO_OUTPUT_INVALID")
        checks["deterministic_risk_boundary"] = "PASSED"
        checks["risk_boundary_result_hash"] = canonical_hash(first)
    elif fixture_id == "normal-research-v1":
        if not has_chain:
            raise NativeEvalError("NORMAL_FIXTURE_FULL_CHAIN_MISSING")
        checks["normal_full_chain"] = "PASSED"
    else:
        raise NativeEvalError("UNSUPPORTED_EVAL_FIXTURE")

    result = {
        "schema_version": EVAL_VERSION,
        "run_id": manifest["run_id"],
        "fixture_id": fixture_id,
        "terminal_state": decision["terminal_state"],
        "status": "PASSED",
        "scope": EVAL_SCOPE,
        "checks": checks,
        "source_hashes": {
            "matrix": matrix["matrix_hash"],
            "replay": replay["replay_hash"],
            "trace": canonical_hash(trace),
            "decision": canonical_hash(decision),
        },
    }
    result["eval_hash"] = canonical_hash(result)
    validate_native_eval_result(result)
    return result


def persist_eval_result(result: Mapping[str, Any], *, run_dir: Path) -> None:
    validate_native_eval_result(result)
    output = run_dir / "eval" / "result.json"
    if output.exists():
        raise NativeEvalError("EVAL_RESULT_ALREADY_EXISTS")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    trace_path = run_dir / "decision_trace.json"
    trace = _read_object(trace_path)
    trace["artifacts"]["eval/result.json"] = file_hash(output)
    trace["events"].append(
        {"stage": "ACTUAL_ARTIFACT_EVAL", "status": "PASSED", "eval_hash": result["eval_hash"]}
    )
    trace_path.write_text(
        json.dumps(trace, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    validate_decision_trace(trace, run_dir=run_dir)
    validate_artifact_matrix(run_dir)
