"""Promotion gate over a hash-bound graph of real assurance artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.schema_validation import validate_schema_instance
from product.runtime.versioning import validate_version_manifest
from product.runtime.trace_validation import trace_integrity_report
from product.runtime.eval_execution_proof import verify_eval_execution_proof
from product.runtime.execution_replay import verify_execution_replay_result
from product.runtime.runtime_eval import verify_runtime_eval_job
from evals.ablation.runtime import verify_runtime_ablation_result
from evals.grading.calibration import verify_calibration_result
from evals.regression.runner import verify_regression_suite
from evals.promotion.test_evidence import verify_deterministic_test_evidence


class RuntimePromotionError(ValueError):
    pass


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimePromotionError(f"PROMOTION_ARTIFACT_INVALID:{path}") from exc
    if not isinstance(value, Mapping):
        raise RuntimePromotionError(f"PROMOTION_ARTIFACT_NOT_OBJECT:{path}")
    return dict(value)


def _artifact(record: Mapping[str, Any], *, name: str) -> tuple[Path, dict[str, Any]]:
    if set(record) != {"path", "sha256"} or not isinstance(record.get("path"), str):
        raise RuntimePromotionError(f"PROMOTION_INPUT_INVALID:{name}")
    path = Path(record["path"]).resolve()
    if not path.is_file() or file_hash(path) != record.get("sha256"):
        raise RuntimePromotionError(f"PROMOTION_ARTIFACT_HASH_MISMATCH:{name}")
    return path, _read(path)


def _self_hash(value: Mapping[str, Any], field: str, *, code: str) -> None:
    body = dict(value)
    claimed = body.pop(field, None)
    if claimed != canonical_hash(body):
        raise RuntimePromotionError(code)


def _gate(status: bool, detail: Any) -> dict[str, Any]:
    return {"status": "PASS" if status else "FAIL", "detail": detail}


def _semantic_mean(evaluations: list[dict[str, Any]]) -> float | None:
    grades = [
        item["grade"]
        for evaluation in evaluations
        for item in evaluation.get("semantic_rubric", {}).values()
        if item.get("status") != "NOT_APPLICABLE" and isinstance(item.get("grade"), int)
    ]
    return (sum(grades) / (3 * len(grades))) if grades else None


def _profile_metrics(ablation: Mapping[str, Any], profile: str = "full-council") -> Mapping[str, Any]:
    records = [item for item in ablation.get("profiles", []) if item.get("profile") == profile]
    return records[0].get("metrics", {}) if len(records) == 1 else {}


def _eval_gate_all(evaluations: list[dict[str, Any]], name: str, predicate) -> bool:
    return bool(evaluations) and all(
        isinstance(evaluation.get("hard_gates", {}).get(name), Mapping)
        and predicate(evaluation["hard_gates"][name])
        for evaluation in evaluations
    )


def _verify_deterministic_tests(repository_root: Path, report_path: Path) -> dict[str, Any]:
    report = verify_deterministic_test_evidence(report_path, repository_root=repository_root)
    return {
        "status": report["status"],
        "event_id": report["event_id"],
        "command": report["command"],
        "cwd": report["cwd"],
        "tmpdir": report["tmpdir"],
        "started_at": report["started_at"],
        "completed_at": report["completed_at"],
        "tests_run": report["tests_run"],
        "exit_code": report["exit_code"],
        "assertion_failures": report["assertion_failures"],
        "test_errors": report["test_errors"],
        "environment_errors": report["environment_errors"],
        "event_path": report["event"]["path"],
        "event_hash": report["event"]["sha256"],
    }


def _assert_unique_gate_id(repository_root: Path, output_dir: Path, gate_id: str) -> None:
    roots = {output_dir.parent.resolve(), (repository_root / "evals" / "results").resolve()}
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("result.json"):
            if output_dir in path.parents:
                continue
            try:
                value = _read(path)
            except RuntimePromotionError:
                continue
            if value.get("schema_version") == "promotion-gate/1.0.0" and value.get("gate_id") == gate_id:
                raise RuntimePromotionError(f"PROMOTION_GATE_ID_ALREADY_EXISTS:{gate_id}:{path}")


def _find_prior_gate(repository_root: Path, output_dir: Path, inputs: Mapping[str, Any]) -> dict[str, str] | None:
    current = dict(inputs)
    current.pop("gate_id", None)
    roots = {output_dir.parent.resolve(), (repository_root / "evals" / "results").resolve()}
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("result.json")):
            if output_dir in path.parents:
                continue
            try:
                result = _read(path)
                prior_inputs = _read(path.parent / "input-manifest.json")
            except RuntimePromotionError:
                continue
            if result.get("schema_version") != "promotion-gate/1.0.0":
                continue
            prior_inputs.pop("gate_id", None)
            if prior_inputs == current:
                return {
                    "gate_id": str(result.get("gate_id")),
                    "path": str(path.resolve()),
                    "sha256": file_hash(path),
                }
    return None


def _run_version(run_dir: Path) -> str | None:
    trace = _read(run_dir.resolve() / "decision_trace.json")
    runtime = trace.get("runtime", {})
    return runtime.get("candidate_version") if isinstance(runtime, Mapping) else None


def _run_version_lock_hash(run_dir: Path) -> str:
    trace = _read(run_dir.resolve() / "decision_trace.json")
    runtime = trace.get("runtime", {})
    version_lock = runtime.get("version_lock", {}) if isinstance(runtime, Mapping) else {}
    if not isinstance(version_lock, Mapping) or not version_lock:
        raise RuntimePromotionError(f"PROMOTION_RUN_VERSION_LOCK_MISSING:{run_dir}")
    return canonical_hash(version_lock)


def _eval_version(eval_path: Path) -> tuple[str | None, Path]:
    manifest = _read(eval_path.resolve().parent.parent / "input-manifest.json")
    run_dir = Path(str(manifest.get("run_dir", ""))).resolve()
    return _run_version(run_dir), run_dir


def _ablation_versions(ablation: Mapping[str, Any]) -> set[str | None]:
    return {
        _run_version(Path(str(profile.get("run_dir", ""))))
        for case in ablation.get("cases", [])
        for profile in case.get("profiles", [])
        if isinstance(profile, Mapping)
        }


def _ablation_version_lock_hashes(ablation: Mapping[str, Any]) -> set[str]:
    return {
        _run_version_lock_hash(Path(str(profile.get("run_dir", ""))))
        for case in ablation.get("cases", [])
        for profile in case.get("profiles", [])
        if isinstance(profile, Mapping)
    }


def run_promotion_gate(
    repository_root: Path,
    *,
    input_manifest_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    if output_dir.exists():
        raise RuntimePromotionError("PROMOTION_OUTPUT_EXISTS")
    inputs = _read(input_manifest_path)
    schema = _read(repository_root / "product" / "schemas" / "runtime" / "promotion-input.schema.json")
    validate_schema_instance(inputs, schema)
    _assert_unique_gate_id(repository_root.resolve(), output_dir.resolve(), str(inputs["gate_id"]))
    prior_result = _find_prior_gate(repository_root.resolve(), output_dir.resolve(), inputs)
    artifacts = inputs["artifacts"]
    candidate_path, candidate = _artifact(artifacts["candidate_manifest"], name="candidate_manifest")
    _, baseline = _artifact(artifacts["baseline_manifest"], name="baseline_manifest")
    _, model_policy = _artifact(artifacts["model_policy"], name="model_policy")
    tests_path, tests = _artifact(artifacts["deterministic_tests"], name="deterministic_tests")
    calibration_path, calibration = _artifact(artifacts["semantic_calibration"], name="semantic_calibration")
    regression_path, regression = _artifact(artifacts["regression"], name="regression")
    execution_path, execution = _artifact(artifacts["execution_replay"], name="execution_replay")
    ablation_path, ablation = _artifact(artifacts["ablation"], name="ablation")
    baseline_ablation_record = artifacts["baseline_ablation"]
    baseline_ablation_pair = (
        _artifact(baseline_ablation_record, name="baseline_ablation")
        if baseline_ablation_record is not None
        else None
    )
    baseline_ablation = baseline_ablation_pair[1] if baseline_ablation_pair else None
    eval_pairs = [_artifact(record, name=f"runtime_eval_{index}") for index, record in enumerate(artifacts["runtime_evals"])]
    evals = [item[1] for item in eval_pairs]
    grader_proofs = [_artifact(record, name=f"grader_proof_{index}")[1] for index, record in enumerate(artifacts["grader_proofs"])]
    baseline_evals = [_artifact(record, name=f"baseline_runtime_eval_{index}")[1] for index, record in enumerate(artifacts["baseline_runtime_evals"])]
    traces = [_artifact(record, name=f"trace_integrity_{index}")[1] for index, record in enumerate(artifacts["trace_integrity"])]
    validate_version_manifest(candidate)
    baseline_manifest_valid = True
    baseline_manifest_diagnostic: str | None = None
    try:
        validate_version_manifest(baseline)
    except ValueError as exc:
        # 旧 baseline 仍可作为显式、带 hash 的诊断输入，但绝不能被当作
        # 当前版本闭包完整的晋升证据，也不能让 Gate 直接崩溃。
        baseline_manifest_valid = False
        baseline_manifest_diagnostic = str(exc)
    if candidate.get("candidate_version") != inputs["candidate_version"]:
        raise RuntimePromotionError("PROMOTION_CANDIDATE_VERSION_MISMATCH")
    baseline_id = baseline.get("candidate_version") or baseline.get("version")
    if baseline_id != inputs["baseline_version"]:
        raise RuntimePromotionError("PROMOTION_BASELINE_VERSION_MISMATCH")
    if model_policy.get("schema_version") != "model-routing-policy/1.0.0":
        raise RuntimePromotionError("PROMOTION_MODEL_POLICY_INVALID")
    try:
        test_verification = _verify_deterministic_tests(repository_root, tests_path)
    except (ValueError, OSError) as exc:
        test_verification = {"status": "FAIL", "verification_errors": [str(exc)]}
    verification_errors: dict[str, list[str]] = {
        "semantic_calibration": [],
        "runtime_regression": [],
        "execution_replay": [],
        "runtime_eval": [],
        "baseline_runtime_eval": [],
        "ablation": [],
        "baseline_ablation": [],
        "trace_completeness": [],
        "version_binding": [],
    }
    try:
        calibration = verify_calibration_result(repository_root, calibration_path)
    except (ValueError, OSError) as exc:
        verification_errors["semantic_calibration"].append(str(exc))
    try:
        regression = verify_regression_suite(repository_root, regression_path)
    except (ValueError, OSError) as exc:
        verification_errors["runtime_regression"].append(str(exc))
    try:
        execution = verify_execution_replay_result(execution_path)
    except (ValueError, OSError) as exc:
        verification_errors["execution_replay"].append(str(exc))
    verified_evals: list[dict[str, Any]] = []
    for eval_path, raw_evaluation in eval_pairs:
        try:
            verify_runtime_eval_job(repository_root, eval_result_path=eval_path)
            verified_evals.append(raw_evaluation)
        except (ValueError, OSError) as exc:
            verification_errors["runtime_eval"].append(str(exc))
    verified_baseline_evals: list[dict[str, Any]] = []
    for index, record in enumerate(artifacts["baseline_runtime_evals"]):
        path = Path(str(record["path"])).resolve()
        try:
            verify_runtime_eval_job(repository_root, eval_result_path=path)
            verified_baseline_evals.append(_read(path))
        except (ValueError, OSError) as exc:
            verification_errors["baseline_runtime_eval"].append(f"{index}:{exc}")
    try:
        ablation = verify_runtime_ablation_result(repository_root, ablation_path)
    except (ValueError, OSError) as exc:
        verification_errors["ablation"].append(str(exc))
    if baseline_ablation_pair is not None:
        try:
            baseline_ablation = verify_runtime_ablation_result(repository_root, baseline_ablation_pair[0])
        except (ValueError, OSError) as exc:
            verification_errors["baseline_ablation"].append(str(exc))
    evals = verified_evals
    baseline_evals = verified_baseline_evals
    if len(grader_proofs) != len(eval_pairs):
        raise RuntimePromotionError("PROMOTION_GRADER_PROOF_SET_INVALID")
    for (eval_path, evaluation), proof in zip(eval_pairs, grader_proofs):
        _self_hash(proof, "proof_hash", code="PROMOTION_GRADER_PROOF_HASH_INVALID")
        eval_dir = eval_path.parent.parent
        semantic = _read(eval_dir / "semantic-rubric.json")
        verified = verify_eval_execution_proof(
            repository_root,
            eval_dir=eval_dir,
            semantic_result=semantic,
        )
        if verified != proof or proof.get("eval_id") != evaluation.get("eval_id"):
            raise RuntimePromotionError("PROMOTION_GRADER_PROOF_MISMATCH")
    verified_traces: list[dict[str, Any]] = []
    for trace in traces:
        try:
            _self_hash(trace, "report_hash", code="PROMOTION_TRACE_HASH_INVALID")
            run_dir = Path(str(trace.get("source_run_dir", ""))).resolve()
            runtime_trace = _read(run_dir / "decision_trace.json")
            rebuilt_trace = trace_integrity_report(runtime_trace, run_dir=run_dir)
            if rebuilt_trace != trace:
                raise RuntimePromotionError("PROMOTION_TRACE_SOURCE_MISMATCH")
            verified_traces.append(rebuilt_trace)
        except (ValueError, OSError) as exc:
            verification_errors["trace_completeness"].append(str(exc))
    traces = verified_traces
    baseline_eval_paths = [Path(str(record["path"])).resolve() for record in artifacts["baseline_runtime_evals"]]
    candidate_eval_versions: set[str | None] = set()
    baseline_eval_versions: set[str | None] = set()
    candidate_ablation_versions: set[str | None] = set()
    baseline_ablation_versions: set[str | None] = set()
    candidate_trace_versions: set[str | None] = set()
    execution_versions: set[str | None] = set()
    candidate_lock_hashes: set[str] = set()
    baseline_lock_hashes: set[str] = set()
    try:
        candidate_eval_versions = {_eval_version(path)[0] for path, _ in eval_pairs}
    except (ValueError, OSError) as exc:
        verification_errors["version_binding"].append(f"PROMOTION_CANDIDATE_EVAL_VERSION_UNREADABLE:{exc}")
    try:
        baseline_eval_versions = {_eval_version(path)[0] for path in baseline_eval_paths}
    except (ValueError, OSError) as exc:
        verification_errors["version_binding"].append(f"PROMOTION_BASELINE_EVAL_VERSION_UNREADABLE:{exc}")
    try:
        candidate_ablation_versions = _ablation_versions(ablation)
    except (ValueError, OSError) as exc:
        verification_errors["version_binding"].append(f"PROMOTION_CANDIDATE_ABLATION_VERSION_UNREADABLE:{exc}")
    try:
        baseline_ablation_versions = _ablation_versions(baseline_ablation or {})
    except (ValueError, OSError) as exc:
        verification_errors["version_binding"].append(f"PROMOTION_BASELINE_ABLATION_VERSION_UNREADABLE:{exc}")
    try:
        candidate_trace_versions = {
            _run_version(Path(str(item["source_run_dir"]))) for item in traces
        }
    except (ValueError, OSError) as exc:
        verification_errors["version_binding"].append(f"PROMOTION_TRACE_VERSION_UNREADABLE:{exc}")
    try:
        execution_versions = {
            _run_version(Path(str(execution.get("source_run_dir", "")))),
            _run_version(Path(str(execution.get("replay_run_dir", "")))),
        }
    except (ValueError, OSError) as exc:
        verification_errors["version_binding"].append(f"PROMOTION_EXECUTION_VERSION_UNREADABLE:{exc}")
    try:
        candidate_lock_hashes = {
            *(_run_version_lock_hash(_eval_version(path)[1]) for path, _ in eval_pairs),
            *_ablation_version_lock_hashes(ablation),
            *(_run_version_lock_hash(Path(str(item["source_run_dir"]))) for item in traces),
            _run_version_lock_hash(Path(str(execution.get("source_run_dir", "")))),
            _run_version_lock_hash(Path(str(execution.get("replay_run_dir", "")))),
        }
    except (ValueError, OSError) as exc:
        verification_errors["version_binding"].append(f"PROMOTION_CANDIDATE_VERSION_LOCK_UNREADABLE:{exc}")
    try:
        baseline_lock_hashes = {
            *(_run_version_lock_hash(_eval_version(path)[1]) for path in baseline_eval_paths),
            *_ablation_version_lock_hashes(baseline_ablation or {}),
        }
    except (ValueError, OSError) as exc:
        verification_errors["version_binding"].append(f"PROMOTION_BASELINE_VERSION_LOCK_UNREADABLE:{exc}")
    expected_versions = {
        "candidate_eval": (candidate_eval_versions, inputs["candidate_version"]),
        "candidate_ablation": (candidate_ablation_versions, inputs["candidate_version"]),
        "candidate_trace": (candidate_trace_versions, inputs["candidate_version"]),
        "execution_replay": (execution_versions, inputs["candidate_version"]),
    }
    if baseline_eval_paths:
        expected_versions["baseline_eval"] = (baseline_eval_versions, inputs["baseline_version"])
    if baseline_ablation is not None:
        expected_versions["baseline_ablation"] = (baseline_ablation_versions, inputs["baseline_version"])
    for name, (observed, expected) in expected_versions.items():
        if observed != {expected}:
            verification_errors["version_binding"].append(
                f"PROMOTION_{name.upper()}_VERSION_MISMATCH:{sorted(str(item) for item in observed)}"
            )
    if candidate_lock_hashes != {canonical_hash(candidate)}:
        verification_errors["version_binding"].append(
            f"PROMOTION_CANDIDATE_VERSION_LOCK_MISMATCH:{sorted(candidate_lock_hashes)}"
        )
    if (baseline_eval_paths or baseline_ablation is not None) and baseline_lock_hashes != {canonical_hash(baseline)}:
        verification_errors["version_binding"].append(
            f"PROMOTION_BASELINE_VERSION_LOCK_MISMATCH:{sorted(baseline_lock_hashes)}"
        )
    if inputs["candidate_version"] != inputs["baseline_version"]:
        candidate_eval_paths = {path.resolve() for path, _ in eval_pairs}
        candidate_eval_hashes = {file_hash(path) for path in candidate_eval_paths}
        baseline_eval_hashes = {file_hash(path) for path in baseline_eval_paths}
        if candidate_eval_paths & set(baseline_eval_paths) or candidate_eval_hashes & baseline_eval_hashes:
            verification_errors["version_binding"].append("PROMOTION_BASELINE_CANDIDATE_EVAL_REUSE")
        if baseline_ablation_pair is not None and (
            ablation_path.resolve() == baseline_ablation_pair[0].resolve()
            or file_hash(ablation_path) == file_hash(baseline_ablation_pair[0])
        ):
            verification_errors["version_binding"].append("PROMOTION_BASELINE_CANDIDATE_ABLATION_REUSE")
    for artifact, schema_name in (
        (regression, "regression-suite.schema.json"),
        (ablation, "ablation-report.schema.json"),
        (calibration, "semantic-calibration-result.schema.json"),
    ):
        validate_schema_instance(
            artifact,
            _read(repository_root / "product" / "schemas" / "runtime" / schema_name),
        )
    if baseline_ablation is not None:
        validate_schema_instance(
            baseline_ablation,
            _read(repository_root / "product" / "schemas" / "runtime" / "ablation-report.schema.json"),
        )
    eval_schema = _read(repository_root / "product" / "schemas" / "runtime" / "runtime-eval-job.schema.json")
    for evaluation in evals + baseline_evals:
        validate_schema_instance(evaluation, eval_schema)
    regression_cases = {item["case_id"]: item for item in regression.get("case_results", [])}
    mandatory = [regression_cases.get(name) for name in ("all-evidence-stale", "mandatory-no-trade")]
    trace_run_ids = {str(item.get("run_id")) for item in traces if item.get("status") == "PASS"}
    eval_run_ids = {str(item.get("run_id")) for item in evals}
    replay_run_ids = {str(execution.get("source_run_id")), str(execution.get("replay_run_id"))}
    policy = _read(repository_root / "evals" / "promotion" / "policy-v1.json")
    assurance_hashes = candidate.get("assurance_hashes", {})
    version_graph_ok = (
        not any(verification_errors.values())
        and
        regression.get("candidate_hash") == canonical_hash(candidate)
        and regression.get("set_hash") == assurance_hashes.get("regression_set")
        and canonical_hash(model_policy) == assurance_hashes.get("model_routing_policy")
        and canonical_hash(policy) == assurance_hashes.get("promotion_policy")
        and calibration.get("input_hashes", {}).get("labels") == file_hash(
            repository_root / "evals" / "grading" / "calibration" / "v1" / "labels.json"
        )
        and canonical_hash(
            _read(repository_root / "evals" / "grading" / "calibration" / "v1" / "labels.json")
        ) == assurance_hashes.get("runtime_eval_calibration")
        and all(item.get("agent_hash") == assurance_hashes.get("runtime_eval_grader_agent") for item in grader_proofs)
        and all(item.get("skill_hash") == assurance_hashes.get("runtime_eval_grader_skill") for item in grader_proofs)
        and ablation.get("configuration", {}).get("profiles_hash") == assurance_hashes.get("ablation_profiles")
        and all(
            item.get("source_hashes", {}).get("rubric") == assurance_hashes.get("runtime_eval_rubric")
            for item in evals
        )
        and eval_run_ids <= trace_run_ids
        and replay_run_ids <= trace_run_ids
        and replay_run_ids <= eval_run_ids
    )
    hard_gates = {
        "deterministic_tests": _gate(test_verification["status"] == "PASS", test_verification),
        "semantic_calibration": _gate(
            not verification_errors["semantic_calibration"] and calibration.get("status") == "PASS",
            {"agreement": calibration.get("agreement"), "verification_errors": verification_errors["semantic_calibration"]},
        ),
        "runtime_regression": _gate(
            not verification_errors["runtime_regression"] and regression.get("status") == "PASS",
            {"reason_codes": regression.get("reason_codes", []), "verification_errors": verification_errors["runtime_regression"]},
        ),
        "execution_replay": _gate(
            not verification_errors["execution_replay"]
            and execution.get("status") == "PASS"
            and execution.get("configuration_equivalent") is True,
            {"status": execution.get("status"), "verification_errors": verification_errors["execution_replay"]},
        ),
        "evidence_closure": _gate(
            not verification_errors["runtime_eval"]
            and _eval_gate_all(evals, "evidence_closure", lambda item: item.get("status") == "PASS"),
            {"scope": "all runtime evals", "verification_errors": verification_errors["runtime_eval"]},
        ),
        "pit_leakage": _gate(
            not verification_errors["runtime_eval"]
            and _eval_gate_all(evals, "pit_leakage", lambda item: item.get("status") == "PASS" and item.get("leak_count", 0) == 0),
            {"expected": "zero leaks", "verification_errors": verification_errors["runtime_eval"]},
        ),
        "risk_bypass": _gate(
            not verification_errors["runtime_eval"]
            and _eval_gate_all(evals, "risk_bypass", lambda item: item.get("status") == "PASS"),
            {"scope": "all runtime evals", "verification_errors": verification_errors["runtime_eval"]},
        ),
        "schema_success": _gate(
            not verification_errors["runtime_eval"]
            and _eval_gate_all(evals, "schema_and_artifacts", lambda item: item.get("status") == "PASS"),
            {"scope": "all runtime evals", "verification_errors": verification_errors["runtime_eval"]},
        ),
        "mandatory_no_trade": _gate(
            not verification_errors["runtime_regression"]
            and all(item and item.get("status") == "PASS" for item in mandatory),
            [item.get("case_id") if item else None for item in mandatory],
        ),
        "trace_completeness": _gate(
            not verification_errors["trace_completeness"] and bool(traces)
            and all(item.get("status") == "PASS" for item in traces),
            {"run_ids": [item.get("run_id") for item in traces], "verification_errors": verification_errors["trace_completeness"]},
        ),
        "version_completeness": _gate(
            baseline_manifest_valid
            and version_graph_ok
            and bool(baseline_evals)
            and baseline_ablation is not None,
            {
                "candidate": inputs["candidate_version"],
                "baseline": inputs["baseline_version"],
                "baseline_manifest_valid": baseline_manifest_valid,
                "baseline_manifest_diagnostic": baseline_manifest_diagnostic,
                "baseline_runtime_evals": len(baseline_evals),
                "baseline_ablation": baseline_ablation is not None,
                "candidate_eval_versions": sorted(str(item) for item in candidate_eval_versions),
                "baseline_eval_versions": sorted(str(item) for item in baseline_eval_versions),
                "candidate_ablation_versions": sorted(str(item) for item in candidate_ablation_versions),
                "baseline_ablation_versions": sorted(str(item) for item in baseline_ablation_versions),
                "candidate_trace_versions": sorted(str(item) for item in candidate_trace_versions),
                "execution_versions": sorted(str(item) for item in execution_versions),
                "candidate_version_lock_hashes": sorted(candidate_lock_hashes),
                "baseline_version_lock_hashes": sorted(baseline_lock_hashes),
                "version_binding_errors": verification_errors["version_binding"],
            },
        ),
        "ablation_comparability": _gate(
            not verification_errors["ablation"]
            and ablation.get("comparability", {}).get("status") == "PASS",
            {"conclusion": ablation.get("conclusion"), "verification_errors": verification_errors["ablation"]},
        ),
    }
    if set(hard_gates) != set(policy["hard_gates"]):
        raise RuntimePromotionError("PROMOTION_POLICY_GATE_DRIFT")
    reason_codes = [f"PROMOTION_HARD_GATE_FAILED:{name}" for name, item in hard_gates.items() if item["status"] != "PASS"]
    conclusion = ablation.get("conclusion")
    if inputs["candidate_changes_default_topology"] and conclusion != "MEASURABLE_GAIN":
        reason_codes.append("PROMOTION_ABLATION_GAIN_REQUIRED")
    candidate_semantic = _semantic_mean(evals)
    baseline_semantic = _semantic_mean(baseline_evals)
    semantic_delta = (
        candidate_semantic - baseline_semantic
        if candidate_semantic is not None and baseline_semantic is not None
        else None
    )
    candidate_cost = _profile_metrics(ablation)
    baseline_cost = _profile_metrics(baseline_ablation or {})
    telemetry = [record["metrics"].get("telemetry_status") for record in ablation.get("profiles", [])]
    baseline_telemetry = [
        record["metrics"].get("telemetry_status")
        for record in (baseline_ablation or {}).get("profiles", [])
    ]
    telemetry_available = bool(telemetry and baseline_telemetry) and all(
        item == "AVAILABLE" for item in telemetry + baseline_telemetry
    )
    candidate_tokens = (
        candidate_cost.get("input_tokens", 0) + candidate_cost.get("output_tokens", 0)
        if telemetry_available else None
    )
    baseline_tokens = (
        baseline_cost.get("input_tokens", 0) + baseline_cost.get("output_tokens", 0)
        if telemetry_available else None
    )
    soft_metrics = {
        "semantic": {
            "candidate_mean": candidate_semantic,
            "baseline_mean": baseline_semantic,
            "delta": semantic_delta,
            "tolerance": policy["semantic_baseline_tolerance"],
            "status": (
                "NOT_COMPARABLE" if semantic_delta is None
                else "DEGRADED" if semantic_delta < -float(policy["semantic_baseline_tolerance"])
                else "WITHIN_TOLERANCE"
            ),
        },
        "cost_and_latency": {
            "status": "AVAILABLE" if telemetry_available else policy["missing_telemetry"],
            "candidate_tokens": candidate_tokens,
            "baseline_tokens": baseline_tokens,
            "token_delta": candidate_tokens - baseline_tokens if telemetry_available else None,
            "candidate_latency_ms": candidate_cost.get("latency_ms") if telemetry_available else None,
            "baseline_latency_ms": baseline_cost.get("latency_ms") if telemetry_available else None,
            "latency_delta_ms": candidate_cost.get("latency_ms") - baseline_cost.get("latency_ms") if telemetry_available else None,
        },
        "ablation_conclusion": conclusion,
        "ablation_gain_required": inputs["candidate_changes_default_topology"],
        "telemetry_status": "AVAILABLE" if telemetry_available else "MISSING_TELEMETRY",
    }
    result: dict[str, Any] = {
        "schema_version": "promotion-gate/1.0.0",
        "gate_id": inputs["gate_id"],
        "candidate_version": inputs["candidate_version"],
        "baseline_version": inputs["baseline_version"],
        "status": "FAIL" if reason_codes else "PASS",
        "hard_gates": hard_gates,
        "soft_metrics": soft_metrics,
        "reason_codes": sorted(reason_codes),
        "prior_result": prior_result,
        "input_hashes": {
            "input_manifest": file_hash(input_manifest_path),
            "candidate_manifest": file_hash(candidate_path),
            **{
                name: record["sha256"]
                for name, record in artifacts.items()
                if isinstance(record, Mapping) and "sha256" in record
            },
            **{
                f"runtime_eval_{index}": record["sha256"]
                for index, record in enumerate(artifacts["runtime_evals"])
            },
            **{
                f"baseline_runtime_eval_{index}": record["sha256"]
                for index, record in enumerate(artifacts["baseline_runtime_evals"])
            },
            **{
                f"grader_proof_{index}": record["sha256"]
                for index, record in enumerate(artifacts["grader_proofs"])
            },
            **{
                f"trace_integrity_{index}": record["sha256"]
                for index, record in enumerate(artifacts["trace_integrity"])
            },
        },
    }
    result["result_hash"] = canonical_hash(result)
    output_schema = _read(repository_root / "product" / "schemas" / "runtime" / "promotion-gate.schema.json")
    validate_schema_instance(result, output_schema)
    output_dir.mkdir(parents=True)
    (output_dir / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_dir / "input-manifest.json").write_text(json.dumps(inputs, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sentinel = output_dir / result["status"]
    sentinel.write_bytes(b"")
    lines = ["# Promotion Gate 报告", "", f"- Gate ID：`{result['gate_id']}`", f"- 结果：`{result['status']}`", "", "## 硬门禁", ""]
    lines.extend(f"- {name}: `{item['status']}`" for name, item in hard_gates.items())
    lines.extend(["", "## Reasons", ""])
    lines.extend([f"- `{code}`" for code in result["reason_codes"]] or ["- 无"])
    lines.extend(
        [
            "",
            "## 软指标与限制",
            "",
            f"- 语义基线比较：`{soft_metrics['semantic']['status']}`，delta={soft_metrics['semantic']['delta']}",
            f"- 成本/延迟比较：`{soft_metrics['cost_and_latency']['status']}`",
            f"- Ablation：`{soft_metrics['ablation_conclusion']}`；增益是否强制：`{soft_metrics['ablation_gain_required']}`",
        ]
    )
    (output_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result
