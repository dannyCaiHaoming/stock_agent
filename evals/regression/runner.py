"""Regression runner that consumes real Runtime/Eval artifacts or explicit injections."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.mcp.provenance import parse_timestamp
from product.runtime.decision_contract import load_decision_contract, validate_decision_action
from product.runtime.evidence_gate import run_evidence_gate
from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.regression_invariants import (
    derive_runtime_invariant_facts,
    evaluate_expected_invariant,
    validate_invariant_schema_binding,
)
from product.runtime.replay import replay_run
from product.runtime.run_package import finalize_cio, prepare_cio, prepare_run
from product.runtime.runtime_eval import (
    SEMANTIC_DIMENSIONS,
    finalize_eval_job,
    prepare_eval_job,
    verify_runtime_eval_job,
)
from product.runtime.schema_validation import validate_schema_instance
from product.runtime.trace_validation import trace_integrity_report
from product.runtime.validation import validate_company_report, validate_evidence_closure


REGRESSION_CASE_IDS = {
    "normal-research",
    "insufficient-evidence",
    "all-evidence-stale",
    "future-information-leakage",
    "analyst-skeptic-strong-conflict",
    "dangling-evidence-reference",
    "risk-veto",
    "high-concentration-portfolio",
    "llm-overconfidence",
    "mandatory-no-trade",
    "valid-action-contract",
    "invalid-specialist-output",
}
FORBIDDEN_FIXED_INVARIANTS = {
    "action_equals", "confidence_equals", "thesis_equals",
    "ACTION_EQUALS", "CONFIDENCE_EQUALS", "THESIS_EQUALS",
}


class RegressionError(ValueError):
    pass


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegressionError(f"REGRESSION_ARTIFACT_INVALID:{path}") from exc
    if not isinstance(value, Mapping):
        raise RegressionError(f"REGRESSION_ARTIFACT_NOT_OBJECT:{path}")
    return dict(value)


def _write(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        raise RegressionError(f"REGRESSION_OUTPUT_EXISTS:{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _validate_fixture(repository_root: Path, case: Mapping[str, Any]) -> tuple[dict[str, Any], str]:
    fixture_path = (repository_root / str(case["fixture"])).resolve()
    fixture_root = (repository_root / "evals" / "fixtures" / "codex-native").resolve()
    if not fixture_path.is_relative_to(fixture_root):
        raise RegressionError("REGRESSION_FIXTURE_PATH_FORBIDDEN")
    fixture = _read(fixture_path)
    cutoff = fixture.get("decision_cutoff")
    evidence = fixture.get("evidence")
    if not isinstance(cutoff, str) or not isinstance(evidence, list):
        raise RegressionError("REGRESSION_FIXTURE_INVALID")
    for fact in evidence:
        if not isinstance(fact, Mapping) or any(
            not isinstance(fact.get(field), str) or not fact[field]
            for field in ("evidence_id", "source_id", "as_of", "retrieved_at")
        ):
            raise RegressionError("REGRESSION_EVIDENCE_PROVENANCE_INVALID")
    return fixture, file_hash(fixture_path)


def load_regression_set(repository_root: Path, *, set_root: Path | None = None) -> dict[str, Any]:
    root = (set_root or repository_root / "evals" / "regression" / "v1").resolve()
    manifest = _read(root / "manifest.json")
    if set(manifest) != {"schema_version", "set_id", "default_model_route", "cases"}:
        raise RegressionError("REGRESSION_MANIFEST_KEYS_INVALID")
    if manifest["schema_version"] != "regression-set/1.0.0" or manifest["default_model_route"] != "runtime_repeated":
        raise RegressionError("REGRESSION_MANIFEST_VERSION_INVALID")
    schema = _read(repository_root / "product" / "schemas" / "runtime" / "regression-case.schema.json")
    validate_invariant_schema_binding(schema)
    cases: list[dict[str, Any]] = []
    for filename in manifest["cases"]:
        path = (root / "cases" / str(filename)).resolve()
        if not path.is_relative_to(root / "cases"):
            raise RegressionError("REGRESSION_CASE_PATH_FORBIDDEN")
        case = _read(path)
        if any(
            isinstance(item, Mapping)
            and item.get("type") in FORBIDDEN_FIXED_INVARIANTS
            for item in case.get("expected_invariants", [])
        ):
            raise RegressionError("REGRESSION_FIXED_INVESTMENT_ANSWER_FORBIDDEN")
        validate_schema_instance(case, schema)
        fixture, fixture_hash = _validate_fixture(repository_root, case)
        injected_ids = case["injection_evidence_ids"]
        if case["injection"] == "future-information-leakage":
            if not injected_ids or not set(injected_ids) <= {
                str(item["evidence_id"]) for item in fixture["evidence"]
            }:
                raise RegressionError("REGRESSION_FUTURE_INJECTION_IDS_INVALID")
        elif injected_ids:
            raise RegressionError("REGRESSION_INJECTION_EVIDENCE_IDS_NOT_APPLICABLE")
        case["case_hash"] = canonical_hash({"case": case, "fixture_hash": fixture_hash})
        case["fixture_hash"] = fixture_hash
        case["fixture_id"] = fixture["fixture_id"]
        cases.append(case)
    ids = [case["case_id"] for case in cases]
    if set(ids) != REGRESSION_CASE_IDS or len(ids) != len(set(ids)):
        raise RegressionError("REGRESSION_CASE_SET_INCOMPLETE_OR_DUPLICATE")
    return {**manifest, "cases": cases, "set_hash": canonical_hash(cases)}


def case_cache_key(
    case: Mapping[str, Any],
    *,
    candidate_hash: str,
    model: str,
    codex_runtime: str,
    runtime_profile_hash: str,
    gate_context_hash: str,
    rubric_hash: str,
    grader_hash: str,
) -> str:
    return canonical_hash(
        {
            "case_hash": case["case_hash"],
            "candidate_hash": candidate_hash,
            "model": model,
            "codex_runtime": codex_runtime,
            "runtime_profile_hash": runtime_profile_hash,
            "gate_context_hash": gate_context_hash,
            "rubric_hash": rubric_hash,
            "grader_hash": grader_hash,
        }
    )


def _tree_hash(root: Path) -> str:
    return canonical_hash(
        {
            str(path.relative_to(root)): file_hash(path)
            for path in sorted(root.rglob("*"))
            if path.is_file()
        }
    )


def _cache_inputs(
    case: Mapping[str, Any],
    *,
    candidate_hash: str,
    run_dir: Path,
    eval_result: Mapping[str, Any],
) -> dict[str, str]:
    manifest = _read(run_dir / "run_manifest.json")
    trace = _read(run_dir / "decision_trace.json")
    risk_entries = trace.get("risk_lineage", [])
    last_risk = risk_entries[-1].get("result", {}) if risk_entries else {}
    version_lock = trace.get("runtime", {}).get("version_lock", {})
    resource_hashes = version_lock.get("resource_hashes", {})
    gate = _read(run_dir / "evidence" / "gate.json")
    gate_context_hash = canonical_hash(
        {key: value for key, value in gate.items() if key not in {"run_id", "bundle_hash"}}
    )
    values = {
        "candidate_hash": candidate_hash,
        "model": str(manifest.get("model", "")),
        "codex_runtime": str(manifest.get("codex_runtime", "")),
        "runtime_profile_hash": str(resource_hashes.get("runtime_profile", "")),
        "gate_context_hash": gate_context_hash,
        "rubric_hash": str(eval_result.get("source_hashes", {}).get("rubric", "")),
        "grader_hash": canonical_hash(eval_result.get("grader", {})),
    }
    if any(not value for value in values.values()):
        raise RegressionError(f"REGRESSION_CACHE_INPUT_INCOMPLETE:{case['case_id']}")
    return values


def _cache_record(
    case: Mapping[str, Any],
    *,
    candidate_hash: str,
    run_dir: Path,
    eval_path: Path,
    eval_result: Mapping[str, Any],
    outcome: Mapping[str, Any],
) -> dict[str, Any]:
    inputs = _cache_inputs(
        case,
        candidate_hash=candidate_hash,
        run_dir=run_dir,
        eval_result=eval_result,
    )
    record: dict[str, Any] = {
        "schema_version": "regression-cache/1.0.0",
        "cache_key": case_cache_key(case, **inputs),
        "case_id": case["case_id"],
        "case_hash": case["case_hash"],
        "inputs": inputs,
        "source": {
            "run_dir": str(run_dir.resolve()),
            "run_tree_hash": _tree_hash(run_dir.resolve()),
            "eval_result": str(eval_path.resolve()),
            "eval_artifact_hash": file_hash(eval_path.resolve()),
        },
        "outcome": dict(outcome),
    }
    record["record_hash"] = canonical_hash(record)
    return record


def _load_cache_hit(
    repository_root: Path,
    case: Mapping[str, Any],
    *,
    candidate_hash: str,
    cache_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    record = _read(cache_path.resolve())
    body = dict(record)
    if body.pop("record_hash", None) != canonical_hash(body):
        raise RegressionError("REGRESSION_CACHE_RECORD_HASH_INVALID")
    if (
        record.get("schema_version") != "regression-cache/1.0.0"
        or record.get("case_id") != case["case_id"]
        or record.get("case_hash") != case["case_hash"]
    ):
        raise RegressionError("REGRESSION_CACHE_CASE_MISMATCH")
    source = record.get("source", {})
    run_dir = Path(str(source.get("run_dir", ""))).resolve()
    eval_path = Path(str(source.get("eval_result", ""))).resolve()
    if _tree_hash(run_dir) != source.get("run_tree_hash") or file_hash(eval_path) != source.get("eval_artifact_hash"):
        raise RegressionError("REGRESSION_CACHE_SOURCE_HASH_MISMATCH")
    eval_result = _read(eval_path)
    inputs = _cache_inputs(
        case,
        candidate_hash=candidate_hash,
        run_dir=run_dir,
        eval_result=eval_result,
    )
    if record.get("inputs") != inputs or record.get("cache_key") != case_cache_key(case, **inputs):
        raise RegressionError("REGRESSION_CACHE_KEY_MISMATCH")
    execution = _verify_runtime_case(
        repository_root,
        case=case,
        run_dir=run_dir,
        eval_path=eval_path,
        source_command="verified regression cache",
        candidate_hash=candidate_hash,
    )
    outcome = _actual_outcome(
        run_dir,
        eval_result,
        {
            "model": record.get("outcome", {}).get("model"),
            "input_tokens": record.get("outcome", {}).get("input_tokens"),
            "output_tokens": record.get("outcome", {}).get("output_tokens"),
            "cached_tokens": record.get("outcome", {}).get("cached_tokens"),
            "latency_ms": record.get("outcome", {}).get("latency_ms"),
            "llm_calls": record.get("outcome", {}).get("llm_calls"),
        },
        expected_fixture_id=str(case["fixture_id"]),
    )
    if canonical_hash(outcome) != canonical_hash(record.get("outcome")):
        raise RegressionError("REGRESSION_CACHE_OUTCOME_MISMATCH")
    return outcome, {
        "status": "HIT",
        "cache_key": record["cache_key"],
        "reused_from": str(cache_path.resolve()),
    }, execution


def _verify_runtime_case(
    repository_root: Path,
    *,
    case: Mapping[str, Any],
    run_dir: Path,
    eval_path: Path,
    source_command: str,
    candidate_hash: str,
    producer: str = "codex-native-runtime",
    pre_operations: Sequence[str] = (),
    extra_hashes: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Execute the required Trace -> Artifact Replay -> Runtime Eval verification chain."""

    run_dir = run_dir.resolve()
    eval_path = eval_path.resolve()
    trace = _read(run_dir / "decision_trace.json")
    version_lock = trace.get("runtime", {}).get("version_lock", {})
    actual_candidate_hash = canonical_hash(version_lock)
    if actual_candidate_hash != candidate_hash:
        raise RegressionError(
            f"REGRESSION_CANDIDATE_VERSION_MISMATCH:{case['case_id']}:{actual_candidate_hash}"
        )
    trace_report = trace_integrity_report(trace, run_dir=run_dir)
    replay = replay_run(repository_root, run_dir=run_dir)
    evaluation = verify_runtime_eval_job(repository_root, eval_result_path=eval_path)
    proof: dict[str, Any] = {
        "schema_version": "regression-case-execution-proof/1.0.0",
        "case_id": case["case_id"],
        "run_id": trace["run_id"],
        "producer": producer,
        "source_command": source_command,
        "executed_operations": [
            *pre_operations,
            "trace_integrity_report",
            "artifact_replay",
            "runtime_eval_verify",
        ],
        "artifacts": {
            "run_dir": str(run_dir),
            "decision_trace": str((run_dir / "decision_trace.json").resolve()),
            "eval_result": str(eval_path),
        },
        "hashes": {
            "trace": trace_report["trace_hash"],
            "trace_report": trace_report["report_hash"],
            "artifact_replay": replay["replay_hash"],
            "runtime_eval": evaluation["eval_hash"],
            "grader_execution_proof": evaluation["grader_execution_proof_hash"],
            "candidate_version_manifest": actual_candidate_hash,
            **dict(extra_hashes or {}),
        },
        "llm_calls_during_verification": 0,
        "status": "PASS",
    }
    proof["proof_hash"] = canonical_hash(proof)
    return proof


def _specialist_injection_outputs(run_dir: Path, *, dangling: bool) -> None:
    analyst = _read(run_dir / "invocations" / "runtime_company_analyst.json")
    if not dangling:
        _write(run_dir / "agents" / "runtime_company_analyst.json", {})
        _write(run_dir / "agents" / "runtime_skeptic.json", {})
        return
    _write(
        run_dir / "agents" / "runtime_company_analyst.json",
        {
            "schema_version": "agent-research-report/2.0.0",
            "run_id": analyst["run_id"],
            "invocation_id": analyst["invocation_id"],
            "status": "COMPLETE",
            "agent": "runtime_company_analyst",
            "scope": "Deterministic dangling Evidence injection.",
            "claims": [{
                "claim_id": "injected-claim",
                "statement": "This fixture intentionally references a missing Evidence ID.",
                "kind": "FACT",
                "evidence_refs": ["missing-id"],
                "assumption_ids": [],
            }],
            "assumptions": [],
            "counter_evidence_refs": [],
            "uncertainties": [],
            "data_gaps": [],
            "invalidation_conditions": ["The validator rejects the payload."],
            "confidence": 0.0,
            "confidence_rationale": "Deterministic negative fixture, not an investment conclusion.",
            "skill_execution": analyst["skill_execution"],
            "artifact_refs": [],
        },
    )
    _write(run_dir / "agents" / "runtime_skeptic.json", {})


def _valid_specialist_contract_outputs(run_dir: Path) -> None:
    """Write grounded, non-investment reports for the action-contract fixture."""

    analyst = _read(run_dir / "invocations" / "runtime_company_analyst.json")
    skeptic = _read(run_dir / "invocations" / "runtime_skeptic.json")
    evidence_ids = list(analyst["evidence_ids"])
    if not evidence_ids:
        raise RegressionError("VALID_ACTION_FIXTURE_REQUIRES_EVIDENCE")
    primary = evidence_ids[0]
    secondary = evidence_ids[1] if len(evidence_ids) > 1 else primary
    _write(
        run_dir / "agents" / "runtime_company_analyst.json",
        {
            "schema_version": "agent-research-report/2.0.0",
            "run_id": analyst["run_id"],
            "invocation_id": analyst["invocation_id"],
            "status": "COMPLETE",
            "agent": "runtime_company_analyst",
            "scope": "确定性 action 契约夹具；不构成投资结论。",
            "claims": [{
                "claim_id": "contract-claim-1",
                "statement": "引用的 Evidence 已通过当前运行的 PIT Gate。",
                "kind": "FACT",
                "evidence_refs": [primary],
                "assumption_ids": [],
            }],
            "assumptions": [],
            "counter_evidence_refs": [secondary],
            "uncertainties": ["本案例只验证结构化 action 与 Risk 边界。"],
            "data_gaps": [],
            "invalidation_conditions": ["任一契约或 Evidence 版本发生变化。"],
            "confidence": 0.5,
            "confidence_rationale": "置信度只描述契约夹具的证据闭包，不表达投资观点。",
            "skill_execution": analyst["skill_execution"],
            "artifact_refs": [],
        },
    )
    _write(
        run_dir / "agents" / "runtime_skeptic.json",
        {
            "schema_version": "counter-thesis-report/2.0.0",
            "run_id": skeptic["run_id"],
            "invocation_id": skeptic["invocation_id"],
            "status": "COMPLETE",
            "agent": "runtime_skeptic",
            "mode": "INDEPENDENT_FIRST_PASS",
            "scope": "确定性 action 契约夹具的独立边界检查。",
            "challenges": [{
                "challenge_id": "contract-challenge-1",
                "statement": "合法 Schema 不代表可以绕过确定性 Risk Engine。",
                "evidence_refs": [secondary],
                "assumption_ids": [],
                "resolution_evidence_needed": ["Risk Engine 的实际 lineage"],
            }],
            "evidence_refs": [secondary],
            "counter_evidence_refs": [primary],
            "uncertainties": ["本案例不评价证券方向。"],
            "data_gaps": [],
            "invalidation_conditions": ["Risk lineage 缺失或契约校验失败。"],
            "confidence": 0.5,
            "confidence_rationale": "仅用于证明独立报告及 Evidence 闭包。",
            "skill_execution": skeptic["skill_execution"],
            "artifact_refs": [],
        },
    )


def _valid_cio_contract_output(run_dir: Path) -> dict[str, Any]:
    """Build a legal HOLD draft whose only purpose is exercising Risk."""

    invocation = _read(run_dir / "invocations" / "runtime_cio.json")
    cio_input = _read(run_dir / "inputs" / "runtime_cio.json")
    reports = cio_input["validated_reports"]
    position = _read(run_dir / "audit" / "fixture_snapshot.json")["portfolio"]["positions"][0]
    portfolio = _read(run_dir / "audit" / "fixture_snapshot.json")["portfolio"]
    position_value = float(position["quantity"]) * float(position["price"])
    total_value = position_value + float(portfolio["cash"])
    current_weight = position_value / total_value
    return {
        "schema_version": "cio-decision-draft/2.1.0",
        "run_id": invocation["run_id"],
        "invocation_id": invocation["invocation_id"],
        "status": "COMPLETE",
        "agent": "runtime_cio",
        "consumed_reports": [
            {"agent": name, "output_hash": canonical_hash(report)}
            for name, report in sorted(reports.items())
        ],
        "action": "HOLD",
        "security_id": str(position["security_id"]),
        "current_weight": current_weight,
        "target_weight_range": [current_weight, current_weight],
        "maximum_notional": None,
        "time_horizon": "确定性契约验收周期",
        "thesis": "该输出只验证合法 action 能经过完整 Runtime 与 Risk Engine。",
        "counter_thesis": "契约合法不能替代 Risk Engine 的确定性校验。",
        "consensus": ["两份报告均只引用当前 Gate 允许的 Evidence。"],
        "conflicts": [],
        "unresolved_questions": ["本夹具不生成主观投资判断。"],
        "invalidation_conditions": ["契约、Evidence 或 Risk Policy 任一发生变化。"],
        "confidence": 0.5,
        "confidence_rationale": "仅表达对契约闭包的有限确定性。",
        "evidence_refs": list(cio_input["allowed_evidence_ids"]),
        "no_trade_reason": None,
        "no_trade_explanation": None,
        "reevaluation_conditions": [],
        "skill_execution": invocation["skill_execution"],
        "advisory_only": True,
    }


def _not_applicable_semantic_result(eval_dir: Path) -> dict[str, Any]:
    """Create an explicit N/A rubric for a zero-LLM contract-only Runtime run."""

    manifest = _read(eval_dir / "input-manifest.json")
    value: dict[str, Any] = {
        "schema_version": "semantic-rubric-result/1.0.0",
        "eval_id": manifest["eval_id"],
        "grader": {
            "agent": "dev_eval",
            "model": "deterministic-contract-fixture/no-llm",
            "prompt_hash": manifest["source_hashes"]["grader_prompt"],
            "rubric_hash": manifest["source_hashes"]["rubric"],
            "input_hash": manifest["source_hashes"]["semantic_input"],
        },
        "dimensions": {
            name: {
                "status": "NOT_APPLICABLE",
                "grade": None,
                "evidence_refs": [],
                "rationale": "该零 LLM 夹具只验证 action 契约、Evidence 闭包与 Risk lineage。",
            }
            for name in SEMANTIC_DIMENSIONS
        },
    }
    value["output_hash"] = canonical_hash(value)
    return value


def _materialize_deterministic_case(
    repository_root: Path,
    *,
    case: Mapping[str, Any],
    suite_id: str,
    candidate_hash: str,
    case_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Create and reverify a real zero-LLM diagnostic Run and Eval for one injection."""

    deterministic = execute_deterministic_case(repository_root, case)
    run_id = f"regression-{suite_id}-{case['case_id']}-{case['case_hash'][:12]}"
    run_dir = case_dir / "run"
    fixture_path = (repository_root / str(case["fixture"])).resolve()
    future_injection: dict[str, Any] | None = None
    if case.get("injection") == "future-information-leakage":
        fixture_path, future_injection = _materialize_future_evidence_injection(
            repository_root,
            case=case,
            case_dir=case_dir,
            deterministic=deterministic,
        )
    prepared = prepare_run(
        repository_root,
        fixture_path=fixture_path,
        run_dir=run_dir,
        run_id=run_id,
        model="gpt-5.6-terra",
        research_question=f"Regression deterministic injection: {case['case_id']}",
        authenticity_required=False,
        trigger_reason="regression_deterministic_injection",
    )
    if future_injection is not None:
        _record_future_evidence_injection(run_dir, future_injection)
    if prepared.get("next_state") == "DISPATCH_REQUIRED":
        _write(
            run_dir / "audit" / "regression-injection.json",
            {
                "schema_version": "regression-injection/1.0.0",
                "case_id": case["case_id"],
                "injection": case["injection"],
                "deterministic_outcome_hash": deterministic["outcome_hash"],
                "llm_calls": 0,
            },
        )
        if case.get("injection") == "valid-action-contract":
            _valid_specialist_contract_outputs(run_dir)
        else:
            _specialist_injection_outputs(
                run_dir,
                dangling=case.get("injection") == "dangling-evidence-reference",
            )
        prepared = prepare_cio(repository_root, run_dir=run_dir, model="gpt-5.6-terra")
        if prepared.get("next_state") == "ONE_SPECIALIST_FORMAT_REPAIR_REQUIRED":
            repaired_output = Path(str(prepared["repaired_output"]))
            _write(repaired_output, {})
            prepared = prepare_cio(repository_root, run_dir=run_dir, model="gpt-5.6-terra")
        if (
            case.get("injection") == "valid-action-contract"
            and prepared.get("next_state") == "CIO_SYNTHESIS_REQUIRED"
        ):
            _write(run_dir / "cio" / "runtime_cio.json", _valid_cio_contract_output(run_dir))
            prepared = finalize_cio(repository_root, run_dir=run_dir)
    if case.get("injection") == "future-information-leakage":
        gate = _read(run_dir / "evidence" / "gate.json")
        excluded = {
            str(item["evidence_id"]): set(item.get("reason_codes", []))
            for item in gate.get("excluded", [])
            if isinstance(item, Mapping)
        }
        expected = set(deterministic["injected_evidence_ids"])
        if not expected <= set(gate.get("excluded_evidence_ids", [])) or any(
            not ({"FUTURE_AS_OF", "FUTURE_RETRIEVAL"} & excluded.get(evidence_id, set()))
            for evidence_id in expected
        ):
            raise RegressionError("DETERMINISTIC_PIT_OUTCOME_NOT_BOUND_TO_RUNTIME_GATE")
        if gate.get("input_hash") != canonical_hash(_read(run_dir / "audit" / "fixture_snapshot.json")):
            raise RegressionError("DETERMINISTIC_PIT_GATE_INPUT_MISMATCH")
    terminal_marker = prepared.get("next_state") or prepared.get("terminal_state")
    if terminal_marker not in {"COMPLETED", "SAFE_NO_TRADE", "FAILED_VALIDATION"}:
        raise RegressionError(
            f"REGRESSION_DETERMINISTIC_RUN_NOT_TERMINAL:{case['case_id']}:{terminal_marker}"
        )
    trace = _read(run_dir / "decision_trace.json")
    risk_entries = trace.get("risk_lineage", [])
    last_risk = risk_entries[-1].get("result", {}) if risk_entries else {}
    eval_dir = case_dir / "runtime-eval"
    prepare_eval_job(
        repository_root,
        run_dir=run_dir,
        eval_dir=eval_dir,
        eval_id=f"regression-eval-{suite_id}-{case['case_id']}",
        expected_terminal_states=(str(trace["terminal_state"]),),
    )
    semantic_result_path: Path | None = None
    if case.get("injection") == "valid-action-contract":
        semantic_result_path = eval_dir / "semantic-result.json"
        _write(semantic_result_path, _not_applicable_semantic_result(eval_dir))
    evaluation = finalize_eval_job(
        repository_root,
        eval_dir=eval_dir,
        semantic_result_path=semantic_result_path,
    )
    eval_path = eval_dir / "eval" / "result.json"
    injection_hashes = _regression_injection_hashes(run_dir)
    proof = _verify_runtime_case(
        repository_root,
        case=case,
        run_dir=run_dir,
        eval_path=eval_path,
        source_command=f"execute_deterministic_case:{case['case_id']}",
        candidate_hash=candidate_hash,
        producer="deterministic-injection",
        pre_operations=("deterministic_injection",),
        extra_hashes={"deterministic_outcome": deterministic["outcome_hash"], **injection_hashes},
    )
    decision_path = run_dir / "decision.json"
    decision = _read(decision_path) if decision_path.is_file() else None
    outcome = {
        **deterministic,
        "run_id": run_id,
        "terminal_state": trace["terminal_state"],
        "failed_stage": trace["failed_stage"],
        "action": decision["decisions"][0]["action"] if decision else None,
        "agents_run": [str(item.get("name")) for item in trace.get("agents", [])],
        "risk_bypassed": bool((run_dir / "cio" / "runtime_cio.json").is_file() and not trace.get("risk_lineage")),
        "risk_status": last_risk.get("check", {}).get("status"),
        "future_leak_count": evaluation["hard_gates"]["pit_leakage"].get("leak_count", 0),
        "eval_status": evaluation["status"],
        "llm_calls": 0,
        **derive_runtime_invariant_facts(
            hard_gates=evaluation["hard_gates"],
            semantic_dimensions=evaluation["semantic_rubric"],
        ),
    }
    outcome["specialist_output_valid"] = case.get("injection") != "invalid-specialist-output"
    if case.get("injection") == "future-information-leakage":
        pit = evaluation["hard_gates"]["pit_leakage"]
        outcome["future_injection_verified"] = pit.get("injection_verified") is True
    return outcome, proof


def _materialize_future_evidence_injection(
    repository_root: Path,
    *,
    case: Mapping[str, Any],
    case_dir: Path,
    deterministic: Mapping[str, Any],
) -> tuple[Path, dict[str, Any]]:
    """Build an explicit baseline→injected fixture before the Runtime PIT Gate."""

    source_path = (repository_root / str(case["fixture"])).resolve()
    source = _read(source_path)
    injected_ids = set(str(item) for item in case["injection_evidence_ids"])
    records = [copy.deepcopy(item) for item in source["evidence"] if item["evidence_id"] in injected_ids]
    if {str(item["evidence_id"]) for item in records} != injected_ids:
        raise RegressionError("REGRESSION_FUTURE_INJECTION_SOURCE_INCOMPLETE")
    baseline = copy.deepcopy(source)
    baseline["evidence"] = [
        copy.deepcopy(item) for item in source["evidence"] if item["evidence_id"] not in injected_ids
    ]
    if not baseline["evidence"]:
        raise RegressionError("REGRESSION_FUTURE_INJECTION_BASELINE_EMPTY")
    injected = copy.deepcopy(baseline)
    injected["evidence"].extend(records)
    injection_dir = case_dir / "injection"
    baseline_path = injection_dir / "baseline-fixture.json"
    injected_path = injection_dir / "injected-fixture.json"
    _write(baseline_path, baseline)
    _write(injected_path, injected)
    evidence = [
        {
            "evidence_id": str(item["evidence_id"]),
            "original_as_of": str(item["as_of"]),
            "original_published_at": str(item["published_at"]),
            "original_retrieved_at": str(item["retrieved_at"]),
        }
        for item in records
    ]
    record = {
        "schema_version": "regression-injection/1.1.0",
        "case_id": case["case_id"],
        "producer": "regression-fixture-injector",
        "injection_type": "FUTURE_EVIDENCE",
        "injection_mechanism": "append_declared_evidence_before_pit_gate",
        "injection_version": "future-evidence-injection/1.0.0",
        "decision_cutoff": source["decision_cutoff"],
        "injected_evidence": evidence,
        "source_fixture_hash": file_hash(source_path),
        "baseline_fixture_hash": file_hash(baseline_path),
        "injected_fixture_hash": file_hash(injected_path),
        "deterministic_plan_hash": deterministic["outcome_hash"],
        "llm_calls": 0,
    }
    record["record_hash"] = canonical_hash(record)
    return injected_path, record


def _record_future_evidence_injection(run_dir: Path, record: Mapping[str, Any]) -> None:
    """Bind the pre-Gate injection record into both Trace events and artifact closure."""

    record_path = run_dir / "audit" / "regression-injection.json"
    _write(record_path, record)
    artifact_hash = file_hash(record_path)
    trace_path = run_dir / "decision_trace.json"
    trace = _read(trace_path)
    trace["events"].append(
        {
            "stage": "REGRESSION_FIXTURE_INJECTED",
            "status": "RECORDED",
            "producer": record["producer"],
            "injection_type": record["injection_type"],
            "injection_mechanism": record["injection_mechanism"],
            "injection_version": record["injection_version"],
            "decision_cutoff": record["decision_cutoff"],
            "injected_evidence": record["injected_evidence"],
            "artifact_hash": artifact_hash,
        }
    )
    trace["artifacts"]["audit/regression-injection.json"] = artifact_hash
    trace_path.write_text(json.dumps(trace, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _regression_injection_hashes(run_dir: Path) -> dict[str, str]:
    path = run_dir / "audit" / "regression-injection.json"
    return {"regression_injection": file_hash(path)} if path.is_file() else {}


def _indexed_run_id(entry: Mapping[str, Any]) -> str | None:
    if isinstance(entry.get("cache_record"), str):
        record = _read(Path(str(entry["cache_record"])).resolve())
        return str(record.get("outcome", {}).get("run_id") or "") or None
    if isinstance(entry.get("run_dir"), str):
        trace = _read(Path(str(entry["run_dir"])).resolve() / "decision_trace.json")
        return str(trace.get("run_id") or "") or None
    return None


def _reject_duplicate_runtime_run_ids(
    regression: Mapping[str, Any], run_index: Mapping[str, Mapping[str, Any]]
) -> None:
    seen: dict[str, str] = {}
    for case in regression["cases"]:
        if not case["llm_required"]:
            continue
        entry = run_index.get(case["case_id"])
        if not isinstance(entry, Mapping):
            continue
        run_id = _indexed_run_id(entry)
        if run_id is None:
            continue
        previous = seen.get(run_id)
        if previous is not None and previous != case["case_id"]:
            raise RegressionError(
                f"REGRESSION_DUPLICATE_RUN_ID:{run_id}:{previous}:{case['case_id']}"
            )
        seen[run_id] = case["case_id"]


def _action_sample(action: str) -> dict[str, Any]:
    return {
        "action": action,
        "security_id": "SEC-AAA",
        "current_weight": 0.5,
        "target_weight_range": [0.4, 0.5],
        "maximum_notional": None,
        "thesis": "Deterministic contract fixture; not an investment conclusion.",
        "evidence_refs": ["ev-contract"],
        "invalidation_conditions": ["Contract fixture ends."],
        "no_trade_reason": None,
        "no_trade_explanation": None,
        "reevaluation_conditions": [],
    }


def execute_deterministic_case(repository_root: Path, case: Mapping[str, Any]) -> dict[str, Any]:
    injection = case.get("injection")
    fixture = _read(repository_root / str(case["fixture"]))
    outcome: dict[str, Any] = {"producer": "fixture", "not_llm_output": True, "llm_calls": 0}
    if injection == "all-evidence-stale":
        gate = run_evidence_gate(fixture, run_id=f"regression-{case['case_id']}").artifact
        if gate["allowed_evidence_ids"]:
            raise RegressionError("DETERMINISTIC_STALE_GATE_DID_NOT_CLOSE")
        outcome.update(
            terminal_state="SAFE_NO_TRADE",
            action="NO_TRADE",
            agents_run=[],
            risk_bypassed=False,
            future_leak_count=0,
        )
    elif injection == "future-information-leakage":
        cutoff = parse_timestamp(str(fixture["decision_cutoff"]))
        declared = set(str(item) for item in case["injection_evidence_ids"])
        future_records = [
            item for item in fixture["evidence"] if str(item["evidence_id"]) in declared
        ]
        if {str(item["evidence_id"]) for item in future_records} != declared:
            raise RegressionError("DETERMINISTIC_PIT_FIXTURE_INVALID")
        if any(
            "published_at" not in item
            or not (
                parse_timestamp(str(item["as_of"])) > cutoff
                or parse_timestamp(str(item["retrieved_at"])) > cutoff
                or parse_timestamp(str(item["published_at"])) > cutoff
            )
            for item in future_records
        ):
            raise RegressionError("DETERMINISTIC_PIT_INJECTION_NOT_FUTURE")
        outcome.update(
            injection_type="FUTURE_EVIDENCE",
            injection_mechanism="append_declared_evidence_before_pit_gate",
            injection_version="future-evidence-injection/1.0.0",
            injected_evidence_ids=sorted(declared),
            terminal_state="SAFE_NO_TRADE",
            action="NO_TRADE",
            agents_run=[],
            risk_bypassed=False,
        )
    elif injection == "dangling-evidence-reference":
        try:
            validate_evidence_closure({"evidence_refs": ["missing-id"]}, allowed_evidence_ids=["ev-present"])
        except ValueError:
            outcome["validator_rejection"] = "EVIDENCE_CLOSURE_FAILED"
        else:
            raise RegressionError("DETERMINISTIC_DANGLING_REFERENCE_ACCEPTED")
    elif injection == "valid-action-contract":
        contract = load_decision_contract(repository_root / "product")
        valid: list[str] = []
        for action in ("BUY", "HOLD", "TRIM", "EXIT"):
            candidate = _action_sample(action)
            if action == "BUY":
                candidate["current_weight"] = 0.0
                candidate["target_weight_range"] = [0.01, 0.05]
            elif action == "EXIT":
                candidate["target_weight_range"] = [0.0, 0.0]
            validate_decision_action(candidate, contract)
            valid.append(action)
        try:
            validate_decision_action({**_action_sample("HOLD"), "action": "REDUCE"}, contract)
        except ValueError:
            pass
        else:
            raise RegressionError("DETERMINISTIC_REDUCE_ACTION_ACCEPTED")
        outcome.update(valid_action_set=valid, forbidden_actions=["REDUCE"])
    elif injection == "invalid-specialist-output":
        try:
            validate_company_report({}, run_id="fixture", manifest={})
        except ValueError:
            outcome["validator_rejection"] = "SCHEMA_INVALID"
        else:
            raise RegressionError("DETERMINISTIC_INVALID_SPECIALIST_ACCEPTED")
    else:
        raise RegressionError(f"UNKNOWN_DETERMINISTIC_INJECTION:{injection}")
    outcome["outcome_hash"] = canonical_hash(outcome)
    return outcome


def _actual_outcome(
    run_dir: Path,
    eval_result: Mapping[str, Any],
    telemetry: Mapping[str, Any],
    *,
    expected_fixture_id: str,
) -> dict[str, Any]:
    trace = _read(run_dir / "decision_trace.json")
    trace_integrity_report(trace, run_dir=run_dir)
    manifest = _read(run_dir / "run_manifest.json")
    if manifest.get("fixture_id") != expected_fixture_id:
        raise RegressionError("REGRESSION_RUN_FIXTURE_MISMATCH")
    if eval_result.get("schema_version") != "runtime-eval-job/1.0.0" or eval_result.get("run_id") != trace["run_id"]:
        raise RegressionError("REGRESSION_RUNTIME_EVAL_INVALID")
    decision_path = run_dir / "decision.json"
    decision = _read(decision_path) if decision_path.is_file() else None
    agents = [str(item.get("name")) for item in trace.get("agents", []) if isinstance(item, Mapping)]
    risk_entries = trace.get("risk_lineage", [])
    last_risk = risk_entries[-1].get("result", {}) if risk_entries else {}
    saved_telemetry = trace.get("codex_execution", {}).get("telemetry", {}) if isinstance(trace.get("codex_execution"), Mapping) else {}
    measured = saved_telemetry if manifest.get("authenticity_required") is not False else telemetry
    if manifest.get("authenticity_required") is not False and saved_telemetry.get("status") != "AVAILABLE":
        raise RegressionError("REGRESSION_RUNTIME_TELEMETRY_MISSING")
    invariant_facts = derive_runtime_invariant_facts(
        hard_gates=eval_result["hard_gates"],
        semantic_dimensions=eval_result["semantic_rubric"],
    )
    return {
        "run_id": trace["run_id"],
        "terminal_state": trace["terminal_state"],
        "failed_stage": trace["failed_stage"],
        "action": decision["decisions"][0]["action"] if decision else None,
        "agents_run": agents,
        "risk_bypassed": bool((run_dir / "cio" / "runtime_cio.json").exists() and not risk_entries),
        "risk_status": last_risk.get("check", {}).get("status"),
        "future_leak_count": eval_result["hard_gates"]["pit_leakage"].get("leak_count", 0),
        "semantic_dimensions": eval_result["semantic_rubric"],
        "eval_status": eval_result["status"],
        "trace_hash": canonical_hash(trace),
        "eval_hash": eval_result["eval_hash"],
        "model": measured.get("model"),
        "input_tokens": measured.get("input_tokens"),
        "output_tokens": measured.get("output_tokens"),
        "cached_tokens": measured.get("cached_tokens"),
        "latency_ms": measured.get("latency_ms"),
        "llm_calls": measured.get("llm_calls"),
        "specialist_output_valid": trace.get("failed_stage") != "SPECIALIST_VALIDATION",
        **invariant_facts,
    }


def _check_invariant(invariant: Mapping[str, Any], outcome: Mapping[str, Any]) -> bool:
    try:
        return evaluate_expected_invariant(invariant, outcome)
    except ValueError as exc:
        raise RegressionError(str(exc)) from exc


def run_regression_suite(
    repository_root: Path,
    *,
    output_dir: Path,
    suite_id: str,
    candidate_hash: str,
    run_index: Mapping[str, Mapping[str, Any]],
    cache_dir: Path | None = None,
    force: bool = False,
) -> dict[str, Any]:
    if output_dir.exists():
        raise RegressionError("REGRESSION_OUTPUT_EXISTS")
    regression = load_regression_set(repository_root)
    _reject_duplicate_runtime_run_ids(regression, run_index)
    output_dir.mkdir(parents=True)
    results: list[dict[str, Any]] = []
    for case in regression["cases"]:
        if case["llm_required"]:
            entry = run_index.get(case["case_id"])
            if not isinstance(entry, Mapping):
                outcome = {"missing_runtime_artifact": True}
                cache_provenance = {"status": "MISS", "cache_key": None, "reused_from": None}
            elif isinstance(entry.get("cache_record"), str) and not force:
                outcome, cache_provenance, execution_proof = _load_cache_hit(
                    repository_root,
                    case,
                    candidate_hash=candidate_hash,
                    cache_path=Path(str(entry["cache_record"])),
                )
            else:
                if entry.get("model") != "gpt-5.6-terra":
                    raise RegressionError(f"REGRESSION_MODEL_ROUTE_INVALID:{case['case_id']}")
                run_dir = Path(str(entry["run_dir"])).resolve()
                eval_path = Path(str(entry["eval_result"])).resolve()
                eval_result = _read(eval_path)
                execution_proof = _verify_runtime_case(
                    repository_root,
                    case=case,
                    run_dir=run_dir,
                    eval_path=eval_path,
                    source_command=str(
                        entry.get("command")
                        or f"codex-native runtime run_id={_read(run_dir / 'decision_trace.json')['run_id']}"
                    ),
                    candidate_hash=candidate_hash,
                )
                outcome = _actual_outcome(
                    run_dir,
                    eval_result,
                    entry,
                    expected_fixture_id=str(case["fixture_id"]),
                )
                record = _cache_record(
                    case,
                    candidate_hash=candidate_hash,
                    run_dir=run_dir,
                    eval_path=eval_path,
                    eval_result=eval_result,
                    outcome=outcome,
                )
                cache_provenance = {
                    "status": "BYPASSED_FORCE" if force else "MISS",
                    "cache_key": record["cache_key"],
                    "reused_from": None,
                }
                if cache_dir is not None and not force:
                    cache_path = cache_dir.resolve() / f"{record['cache_key']}.json"
                    cache_path.parent.mkdir(parents=True, exist_ok=True)
                    if not cache_path.exists():
                        _write(cache_path, record)
        else:
            outcome, execution_proof = _materialize_deterministic_case(
                repository_root,
                case=case,
                suite_id=suite_id,
                candidate_hash=candidate_hash,
                case_dir=output_dir / "cases" / case["case_id"],
            )
            cache_provenance = {"status": "NOT_APPLICABLE", "cache_key": None, "reused_from": None}
        if case["llm_required"] and not isinstance(entry, Mapping):
            execution_proof = {
                "schema_version": "regression-case-execution-proof/1.0.0",
                "case_id": case["case_id"],
                "run_id": f"regression-{suite_id}-{case['case_id']}-missing",
                "producer": "missing-runtime-input",
                "source_command": "none",
                "executed_operations": [],
                "artifacts": {},
                "hashes": {},
                "llm_calls_during_verification": 0,
                "status": "FAIL",
            }
            execution_proof["proof_hash"] = canonical_hash(execution_proof)
            outcome = {**outcome, "run_id": execution_proof["run_id"]}
        proof_path = output_dir / "cases" / case["case_id"] / "execution-proof.json"
        _write(proof_path, execution_proof)
        outcome_path = output_dir / "cases" / case["case_id"] / "outcome.json"
        _write(outcome_path, outcome)
        invariant_results = [
            {
                "type": invariant["type"],
                "hard": invariant["hard"],
                "status": "PASS" if _check_invariant(invariant, outcome) else "FAIL",
            }
            for invariant in case["expected_invariants"]
        ]
        status = "PASS" if all(item["status"] == "PASS" for item in invariant_results) else "FAIL"
        results.append(
            {
                "case_id": case["case_id"],
                "case_hash": case["case_hash"],
                "llm_required": case["llm_required"],
                "status": status,
                "invariants": invariant_results,
                "outcome": outcome,
                "cache_provenance": cache_provenance,
                "execution_proof": {
                    "path": str(proof_path.resolve()),
                    "sha256": file_hash(proof_path),
                    "proof_hash": execution_proof["proof_hash"],
                },
                "outcome_artifact": {
                    "path": str(outcome_path.resolve()),
                    "sha256": file_hash(outcome_path),
                },
            }
        )
    run_ids = [str(item["outcome"].get("run_id", "")) for item in results]
    if any(not run_id for run_id in run_ids) or len(run_ids) != len(set(run_ids)):
        raise RegressionError("REGRESSION_CASE_RUN_ID_NOT_GLOBALLY_UNIQUE")
    failures = [item["case_id"] for item in results if item["status"] != "PASS"]
    result: dict[str, Any] = {
        "schema_version": "regression-suite/1.0.0",
        "suite_id": suite_id,
        "candidate_hash": candidate_hash,
        "set_hash": regression["set_hash"],
        "case_results": results,
        "status": "FAIL" if failures else "PASS",
        "reason_codes": [f"REGRESSION_CASE_FAILED:{case_id}" for case_id in failures],
    }
    result["suite_hash"] = canonical_hash(result)
    schema = _read(repository_root / "product" / "schemas" / "runtime" / "regression-suite.schema.json")
    validate_schema_instance(result, schema)
    _write(output_dir / "result.json", result)
    _write(
        output_dir / "input-manifest.json",
        {
            "schema_version": "regression-input/1.0.0",
            "set_id": regression["set_id"],
            "set_hash": regression["set_hash"],
            "candidate_hash": candidate_hash,
            "run_artifact_hashes": {
                case_id: canonical_hash(dict(entry)) for case_id, entry in sorted(run_index.items())
            },
        },
    )
    lines = ["# Runtime Regression 报告", "", f"- Suite：`{suite_id}`", f"- 结果：`{result['status']}`", ""]
    lines.extend(f"- {item['case_id']}: `{item['status']}`" for item in results)
    lines.extend(["", "## Reason Codes", ""])
    lines.extend([f"- `{code}`" for code in result["reason_codes"]] or ["- 无"])
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def verify_regression_suite(repository_root: Path, result_path: Path) -> dict[str, Any]:
    """Re-execute every case proof and invariant instead of trusting suite summaries."""

    saved = _read(result_path.resolve())
    body = dict(saved)
    if body.pop("suite_hash", None) != canonical_hash(body):
        raise RegressionError("REGRESSION_SUITE_HASH_INVALID")
    regression = load_regression_set(repository_root)
    if saved.get("set_hash") != regression["set_hash"]:
        raise RegressionError("REGRESSION_SET_HASH_MISMATCH")
    cases_by_id = {case["case_id"]: case for case in regression["cases"]}
    if {item.get("case_id") for item in saved.get("case_results", [])} != set(cases_by_id):
        raise RegressionError("REGRESSION_RESULT_CASE_SET_INVALID")
    rebuilt_results: list[dict[str, Any]] = []
    run_ids: set[str] = set()
    for item in saved["case_results"]:
        case = cases_by_id[item["case_id"]]
        proof_record = item.get("execution_proof", {})
        outcome_record = item.get("outcome_artifact", {})
        proof_path = Path(str(proof_record.get("path", ""))).resolve()
        outcome_path = Path(str(outcome_record.get("path", ""))).resolve()
        if not proof_path.is_file() or file_hash(proof_path) != proof_record.get("sha256"):
            raise RegressionError(f"REGRESSION_EXECUTION_PROOF_INVALID:{case['case_id']}")
        if not outcome_path.is_file() or file_hash(outcome_path) != outcome_record.get("sha256"):
            raise RegressionError(f"REGRESSION_OUTCOME_ARTIFACT_INVALID:{case['case_id']}")
        proof = _read(proof_path)
        proof_body = dict(proof)
        if proof_body.pop("proof_hash", None) != canonical_hash(proof_body):
            raise RegressionError(f"REGRESSION_EXECUTION_PROOF_HASH_INVALID:{case['case_id']}")
        if proof.get("proof_hash") != proof_record.get("proof_hash"):
            raise RegressionError(f"REGRESSION_EXECUTION_PROOF_BINDING_INVALID:{case['case_id']}")
        persisted_outcome = _read(outcome_path)
        if persisted_outcome != item.get("outcome"):
            raise RegressionError(f"REGRESSION_OUTCOME_SUMMARY_DRIFT:{case['case_id']}")
        if case["llm_required"]:
            if proof.get("producer") != "codex-native-runtime" or proof.get("status") != "PASS":
                raise RegressionError(f"REGRESSION_RUNTIME_EXECUTION_MISSING:{case['case_id']}")
            artifacts = proof.get("artifacts", {})
            rebuilt_proof = _verify_runtime_case(
                repository_root,
                case=case,
                run_dir=Path(str(artifacts.get("run_dir", ""))),
                eval_path=Path(str(artifacts.get("eval_result", ""))),
                source_command=str(proof.get("source_command", "")),
                candidate_hash=str(saved["candidate_hash"]),
            )
            if rebuilt_proof != proof:
                raise RegressionError(f"REGRESSION_EXECUTION_PROOF_REPLAY_MISMATCH:{case['case_id']}")
            evaluation = _read(Path(str(artifacts["eval_result"])))
            rebuilt_outcome = _actual_outcome(
                Path(str(artifacts["run_dir"])),
                evaluation,
                persisted_outcome,
                expected_fixture_id=str(case["fixture_id"]),
            )
        else:
            if proof.get("producer") != "deterministic-injection" or proof.get("status") != "PASS":
                raise RegressionError(f"REGRESSION_DETERMINISTIC_EXECUTION_MISSING:{case['case_id']}")
            deterministic = execute_deterministic_case(repository_root, case)
            artifacts = proof.get("artifacts", {})
            run_dir = Path(str(artifacts.get("run_dir", "")))
            rebuilt_proof = _verify_runtime_case(
                repository_root,
                case=case,
                run_dir=run_dir,
                eval_path=Path(str(artifacts.get("eval_result", ""))),
                source_command=str(proof.get("source_command", "")),
                candidate_hash=str(saved["candidate_hash"]),
                producer="deterministic-injection",
                pre_operations=("deterministic_injection",),
                extra_hashes={
                    "deterministic_outcome": deterministic["outcome_hash"],
                    **_regression_injection_hashes(run_dir),
                },
            )
            if rebuilt_proof != proof:
                raise RegressionError(f"REGRESSION_DETERMINISTIC_PROOF_REPLAY_MISMATCH:{case['case_id']}")
            evaluation = _read(Path(str(artifacts["eval_result"])))
            trace = _read(run_dir / "decision_trace.json")
            risk_entries = trace.get("risk_lineage", [])
            last_risk = risk_entries[-1].get("result", {}) if risk_entries else {}
            decision_path = run_dir / "decision.json"
            decision = _read(decision_path) if decision_path.is_file() else None
            rebuilt_outcome = {
                **deterministic,
                "run_id": proof["run_id"],
                "terminal_state": trace["terminal_state"],
                "failed_stage": trace["failed_stage"],
                "action": decision["decisions"][0]["action"] if decision else None,
                "agents_run": [str(agent.get("name")) for agent in trace.get("agents", [])],
                "risk_bypassed": False,
                "risk_status": last_risk.get("check", {}).get("status"),
                "future_leak_count": evaluation["hard_gates"]["pit_leakage"].get("leak_count", 0),
                "eval_status": evaluation["status"],
                "llm_calls": 0,
                "specialist_output_valid": case.get("injection") != "invalid-specialist-output",
                **derive_runtime_invariant_facts(
                    hard_gates=evaluation["hard_gates"],
                    semantic_dimensions=evaluation["semantic_rubric"],
                ),
            }
            if case.get("injection") == "future-information-leakage":
                pit = evaluation["hard_gates"]["pit_leakage"]
                rebuilt_outcome["future_injection_verified"] = pit.get("injection_verified") is True
        if rebuilt_outcome != persisted_outcome:
            raise RegressionError(f"REGRESSION_OUTCOME_RECOMPUTE_MISMATCH:{case['case_id']}")
        run_id = str(rebuilt_outcome.get("run_id", ""))
        if not run_id or run_id in run_ids:
            raise RegressionError(f"REGRESSION_CASE_RUN_ID_NOT_GLOBALLY_UNIQUE:{run_id}")
        run_ids.add(run_id)
        invariant_results = [
            {
                "type": invariant["type"],
                "hard": invariant["hard"],
                "status": "PASS" if _check_invariant(invariant, rebuilt_outcome) else "FAIL",
            }
            for invariant in case["expected_invariants"]
        ]
        status = "PASS" if all(result["status"] == "PASS" for result in invariant_results) else "FAIL"
        rebuilt = dict(item)
        rebuilt.update(
            case_hash=case["case_hash"],
            llm_required=case["llm_required"],
            status=status,
            invariants=invariant_results,
            outcome=rebuilt_outcome,
        )
        rebuilt_results.append(rebuilt)
    failures = [item["case_id"] for item in rebuilt_results if item["status"] != "PASS"]
    rebuilt_suite = {
        "schema_version": "regression-suite/1.0.0",
        "suite_id": saved["suite_id"],
        "candidate_hash": saved["candidate_hash"],
        "set_hash": regression["set_hash"],
        "case_results": rebuilt_results,
        "status": "FAIL" if failures else "PASS",
        "reason_codes": [f"REGRESSION_CASE_FAILED:{case_id}" for case_id in failures],
    }
    rebuilt_suite["suite_hash"] = canonical_hash(rebuilt_suite)
    if rebuilt_suite != saved:
        raise RegressionError("REGRESSION_SUITE_RECOMPUTE_MISMATCH")
    return rebuilt_suite
