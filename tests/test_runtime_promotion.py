from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from evals.ablation.runtime import compare_runtime_ablation_set
from evals.grading.calibration import EXPECTED_CALIBRATION_GRADER, run_calibration
from evals.promotion.runtime_gate import RuntimePromotionError, run_promotion_gate
from evals.promotion.test_evidence import run_deterministic_test_evidence
from evals.regression.runner import run_regression_suite
from product.runtime.execution_replay import finalize_execution_replay, prepare_execution_replay
from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.run_package import finalize_cio, prepare_cio, prepare_run
from product.runtime.runtime_eval import finalize_eval_job, prepare_eval_job
from product.runtime.trace_validation import trace_integrity_report
from tests.test_eval_calibration import execution_proof_record
from tests.test_replay_capsule import complete_run
from tests.test_runtime_ablation import ablation_cio_output, build_variant
from tests.test_runtime_eval_job import semantic_result, write_json
from tests.test_native_run_package import specialist_outputs
from tests.test_eval_execution_proof import rollouts
from product.runtime.eval_execution_proof import build_eval_execution_proof, persist_eval_execution_proof


ROOT = Path(__file__).resolve().parents[1]


class PromotionEvidenceSmokeTests(unittest.TestCase):
    def test_probe(self):
        self.assertEqual(2 + 2, 4)


def write(path: Path, value: dict) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
    return {"path": str(path), "sha256": file_hash(path)}


def self_hashed(value: dict, field: str) -> dict:
    result = dict(value)
    result[field] = canonical_hash(result)
    return result


def baseline_repository(root: Path, candidate: dict) -> tuple[Path, dict]:
    repository = root / "baseline-repository"
    shutil.copytree(ROOT / "product", repository / "product")
    shutil.copytree(ROOT / "evals" / "grading", repository / "evals" / "grading")
    shutil.copytree(ROOT / "evals" / "ablation", repository / "evals" / "ablation")
    shutil.copytree(ROOT / "evals" / "fixtures", repository / "evals" / "fixtures")
    baseline = dict(candidate)
    baseline["candidate_version"] = "0.2.0-approved"
    (repository / "product" / "version-manifest.json").write_text(
        json.dumps(baseline, sort_keys=True), encoding="utf-8"
    )
    return repository, baseline


def complete_run_for_repository(repository_root: Path, run_dir: Path, run_id: str) -> None:
    prepare_run(
        repository_root,
        fixture_path=repository_root / "evals" / "fixtures" / "codex-native" / "normal-research.json",
        run_dir=run_dir,
        run_id=run_id,
        model="gpt-5.6-terra",
        research_question="研究 fixture。",
        authenticity_required=False,
    )
    specialist_outputs(run_dir)
    prepare_cio(repository_root, run_dir=run_dir, model="gpt-5.6-terra")
    write_json(run_dir / "cio" / "runtime_cio.json", ablation_cio_output(run_dir))
    finalize_cio(repository_root, run_dir=run_dir)


def promotion_input(
    root: Path,
    *,
    pit_pass: bool = True,
    topology_change: bool = False,
    calibration_pass: bool = True,
    baseline_complete: bool = True,
    legacy_baseline: bool = False,
) -> Path:
    candidate = json.loads((ROOT / "product" / "version-manifest.json").read_text(encoding="utf-8"))
    baseline_root, baseline = baseline_repository(root, candidate)
    if legacy_baseline:
        baseline = {
            "schema_version": "legacy-version-manifest/0.2.0",
            "version": "0.2.0-approved",
        }
    def create_eval(run_dir: Path, name: str, repository_root: Path = ROOT) -> tuple[Path, Path]:
        eval_dir = root / "runtime-evals" / name
        prepare_eval_job(repository_root, run_dir=run_dir, eval_dir=eval_dir, eval_id=f"promotion-{name}")
        semantic = semantic_result(eval_dir)
        semantic["grader"]["model"] = "gpt-5.6-terra"
        semantic.pop("output_hash")
        semantic["output_hash"] = canonical_hash(semantic)
        semantic_path = root / "grader-results" / f"{name}.json"
        write_json(semantic_path, semantic)
        logs = root / "eval-proof-logs" / name
        logs.mkdir(parents=True)
        parent_rollout, child_rollout = rollouts(logs, eval_dir, semantic)
        proof = build_eval_execution_proof(
            ROOT,
            eval_dir=eval_dir,
            semantic_result_path=semantic_path,
            parent_rollout=parent_rollout,
            child_rollout=child_rollout,
        )
        proof_path = persist_eval_execution_proof(proof, eval_dir=eval_dir)
        finalize_eval_job(repository_root, eval_dir=eval_dir, semantic_result_path=semantic_path)
        return eval_dir / "eval" / "result.json", proof_path

    runtime_dir = root / "runtime" / "source"
    complete_run(runtime_dir, "promotion-source")
    source_eval, source_proof = create_eval(runtime_dir, "source")
    replay_dir = root / "runtime" / "replay"
    prepared = prepare_execution_replay(
        source_run_dir=runtime_dir,
        new_run_dir=replay_dir,
        new_run_id="promotion-replay",
    )
    workspace = Path(prepared["workspace"])
    specialist_outputs(replay_dir)
    prepare_cio(workspace, run_dir=replay_dir, model="gpt-5.6-terra")
    write_json(replay_dir / "cio" / "runtime_cio.json", ablation_cio_output(replay_dir))
    finalize_cio(workspace, run_dir=replay_dir)
    execution_dir = root / "execution-replay"
    finalize_execution_replay(source_run_dir=runtime_dir, replay_run_dir=replay_dir, output_dir=execution_dir)
    replay_eval, replay_proof = create_eval(replay_dir, "replay")
    run_deterministic_test_evidence(
        ROOT,
        output_dir=root / "test-evidence",
        tmpdir=root / "test-tmp",
        test_targets=("tests.test_runtime_promotion.PromotionEvidenceSmokeTests.test_probe",),
    )

    fixture_by_case = {
        "normal-research": "normal-research.json",
        "insufficient-evidence": "insufficient-evidence.json",
        "analyst-skeptic-strong-conflict": "evidence-conflict.json",
        "risk-veto": "risk-veto.json",
        "high-concentration-portfolio": "risk-veto.json",
        "llm-overconfidence": "insufficient-evidence.json",
    }
    run_index = {
        case_id: build_variant(root / "regression-runs" / case_id, "full-council", fixture=fixture, case_id=case_id)
        for case_id, fixture in fixture_by_case.items()
    }
    regression_dir = root / "regression"
    run_regression_suite(
        ROOT,
        output_dir=regression_dir,
        suite_id="promotion-suite",
        candidate_hash=canonical_hash(candidate),
        run_index=run_index,
        force=True,
    )

    case_ids = ["normal-research", "insufficient-evidence", "analyst-skeptic-strong-conflict", "mandatory-no-trade"]
    ablation_cases = {
        case_id: {
            profile: build_variant(
                root / "ablation-runs" / case_id,
                profile,
                fixture=fixture_by_case.get(case_id, "normal-research.json"),
                case_id=case_id,
            )
            for profile in ("cio-only", "analyst-cio", "full-council")
        }
        for case_id in case_ids
    }
    ablation_dir = root / "ablation"
    compare_runtime_ablation_set(ROOT, ablation_id="promotion-ablation", cases=ablation_cases, output_dir=ablation_dir)

    baseline_eval = None
    baseline_ablation_dir = None
    if baseline_complete and not legacy_baseline:
        baseline_run = root / "baseline-runtime" / "source"
        complete_run_for_repository(baseline_root, baseline_run, "promotion-baseline-source")
        baseline_eval, _ = create_eval(baseline_run, "baseline-source", baseline_root)
        baseline_cases = {
            case_id: {
                profile: build_variant(
                    root / "baseline-ablation-runs" / case_id,
                    profile,
                    fixture=fixture_by_case.get(case_id, "normal-research.json"),
                    case_id=case_id,
                    repository_root=baseline_root,
                )
                for profile in ("cio-only", "analyst-cio", "full-council")
            }
            for case_id in case_ids
        }
        baseline_ablation_dir = root / "baseline-ablation"
        compare_runtime_ablation_set(
            ROOT,
            ablation_id="promotion-baseline-ablation",
            cases=baseline_cases,
            output_dir=baseline_ablation_dir,
        )

    labels_path = ROOT / "evals" / "grading" / "calibration" / "v1" / "labels.json"
    labels = json.loads(labels_path.read_text(encoding="utf-8"))
    calibration_cases = {}
    for case in labels["cases"]:
        dimensions = {
            name: {"status": expected["status"], "grade": expected["grade_min"]}
            for name, expected in case["human_labels"].items()
        }
        records = []
        for repeat in (1, 2):
            if not calibration_pass and case["case_id"] == labels["cases"][0]["case_id"] and repeat == 2:
                dimensions = dict(dimensions)
                dimensions["confidence_calibration"] = {"status": "FAIL", "grade": 0}
            value = {
                "schema_version": "semantic-rubric-result/1.0.0",
                "eval_id": f"{case['case_id']}-{repeat}",
                "grader": EXPECTED_CALIBRATION_GRADER,
                "dimensions": dimensions,
            }
            value["output_hash"] = canonical_hash(value)
            output_path = root / "calibration" / "outputs" / f"{case['case_id']}-{repeat}.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json.dumps(value), encoding="utf-8")
            records.append({
                "path": str(output_path),
                "sha256": file_hash(output_path),
                "execution_proof": execution_proof_record(root / "calibration", case["case_id"], repeat, output_path),
            })
        calibration_cases[case["case_id"]] = records
    calibration_index = root / "calibration" / "index.json"
    calibration_index.write_text(json.dumps({"schema_version": "semantic-calibration-index/1.0.0", "cases": calibration_cases}))
    calibration_dir = root / "calibration" / "result"
    run_calibration(ROOT, labels_path=labels_path, grader_index_path=calibration_index, output_dir=calibration_dir)

    source_trace_value = json.loads((runtime_dir / "decision_trace.json").read_text(encoding="utf-8"))
    replay_trace_value = json.loads((replay_dir / "decision_trace.json").read_text(encoding="utf-8"))
    source_trace = trace_integrity_report(source_trace_value, run_dir=runtime_dir)
    replay_trace = trace_integrity_report(replay_trace_value, run_dir=replay_dir)
    if not pit_pass:
        gate_path = runtime_dir / "evidence" / "gate.json"
        gate = json.loads(gate_path.read_text(encoding="utf-8"))
        future = dict(gate["allowed_evidence"][0])
        future.update(
            evidence_id="injected-future-evidence",
            as_of="2027-01-01T00:00:00Z",
            retrieved_at="2027-01-01T00:01:00Z",
        )
        gate["allowed_evidence"].append(future)
        gate["allowed_evidence_ids"].append("injected-future-evidence")
        gate_path.write_text(json.dumps(gate), encoding="utf-8")
    artifacts = {
        "candidate_manifest": write(root / "candidate.json", candidate),
        "baseline_manifest": write(root / "baseline.json", baseline),
        "model_policy": write(root / "model-policy.json", json.loads((ROOT / "product" / "model-routing.json").read_text(encoding="utf-8"))),
        "deterministic_tests": {
            "path": str(root / "test-evidence" / "result.json"),
            "sha256": file_hash(root / "test-evidence" / "result.json"),
        },
        "semantic_calibration": {"path": str(calibration_dir / "result.json"), "sha256": file_hash(calibration_dir / "result.json")},
        "regression": {"path": str(regression_dir / "result.json"), "sha256": file_hash(regression_dir / "result.json")},
        "execution_replay": {"path": str(execution_dir / "result.json"), "sha256": file_hash(execution_dir / "result.json")},
        "runtime_evals": [{"path": str(path), "sha256": file_hash(path)} for path in (source_eval, replay_eval)],
        "grader_proofs": [{"path": str(path), "sha256": file_hash(path)} for path in (source_proof, replay_proof)],
        "baseline_runtime_evals": (
            [{"path": str(baseline_eval), "sha256": file_hash(baseline_eval)}]
            if baseline_eval is not None else []
        ),
        "ablation": {"path": str(ablation_dir / "result.json"), "sha256": file_hash(ablation_dir / "result.json")},
        "baseline_ablation": (
            {
                "path": str(baseline_ablation_dir / "result.json"),
                "sha256": file_hash(baseline_ablation_dir / "result.json"),
            }
            if baseline_ablation_dir is not None else None
        ),
        "trace_integrity": [write(root / "trace-source.json", source_trace), write(root / "trace-replay.json", replay_trace)],
    }
    inputs = {
        "schema_version": "promotion-input/1.0.0",
        "gate_id": "gate-1",
        "candidate_version": candidate["candidate_version"],
        "baseline_version": baseline.get("candidate_version") or baseline["version"],
        "candidate_changes_default_topology": topology_change,
        "artifacts": artifacts,
    }
    path = root / "promotion-input.json"
    path.write_text(json.dumps(inputs), encoding="utf-8")
    return path


class RuntimePromotionTests(unittest.TestCase):
    def test_valid_real_evidence_graph_passes_without_mutating_product(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = promotion_input(root)
            before = {str(path.relative_to(ROOT / "product")): file_hash(path) for path in (ROOT / "product").rglob("*") if path.is_file()}
            result = run_promotion_gate(ROOT, input_manifest_path=input_path, output_dir=root / "out")
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["soft_metrics"]["semantic"]["status"], "WITHIN_TOLERANCE")
            self.assertEqual(result["soft_metrics"]["cost_and_latency"]["status"], "AVAILABLE")
            self.assertTrue((root / "out" / "PASS").is_file())
            self.assertFalse((root / "out" / "FAIL").exists())
            after = {str(path.relative_to(ROOT / "product")): file_hash(path) for path in (ROOT / "product").rglob("*") if path.is_file()}
            self.assertEqual(before, after)

    def test_pit_hard_failure_cannot_be_overridden_by_high_semantic_scores(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_promotion_gate(
                ROOT,
                input_manifest_path=promotion_input(root, pit_pass=False),
                output_dir=root / "out",
            )
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("PROMOTION_HARD_GATE_FAILED:pit_leakage", result["reason_codes"])
            self.assertTrue((root / "out" / "FAIL").is_file())

    def test_dangling_evidence_is_injected_in_runtime_artifact_and_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = promotion_input(root)
            inputs = json.loads(input_path.read_text(encoding="utf-8"))
            trace_report = json.loads(Path(inputs["artifacts"]["trace_integrity"][0]["path"]).read_text(encoding="utf-8"))
            run_dir = Path(trace_report["source_run_dir"])
            decision_path = run_dir / "decision.json"
            decision = json.loads(decision_path.read_text(encoding="utf-8"))
            decision["decisions"][0]["evidence_refs"].append("injected-dangling-evidence")
            decision_path.write_text(json.dumps(decision), encoding="utf-8")
            result = run_promotion_gate(ROOT, input_manifest_path=input_path, output_dir=root / "out")
            self.assertEqual(result["status"], "FAIL")
            self.assertEqual(result["hard_gates"]["evidence_closure"]["status"], "FAIL")

    def test_risk_lineage_bypass_is_injected_in_trace_and_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = promotion_input(root)
            inputs = json.loads(input_path.read_text(encoding="utf-8"))
            trace_report = json.loads(Path(inputs["artifacts"]["trace_integrity"][0]["path"]).read_text(encoding="utf-8"))
            trace_path = Path(trace_report["source_run_dir"]) / "decision_trace.json"
            trace = json.loads(trace_path.read_text(encoding="utf-8"))
            trace["risk_lineage"] = []
            trace_path.write_text(json.dumps(trace), encoding="utf-8")
            result = run_promotion_gate(ROOT, input_manifest_path=input_path, output_dir=root / "out")
            self.assertEqual(result["hard_gates"]["risk_bypass"]["status"], "FAIL")

    def test_missing_trace_is_rejected_from_bottom_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = promotion_input(root)
            inputs = json.loads(input_path.read_text(encoding="utf-8"))
            trace_report = json.loads(Path(inputs["artifacts"]["trace_integrity"][0]["path"]).read_text(encoding="utf-8"))
            (Path(trace_report["source_run_dir"]) / "decision_trace.json").unlink()
            result = run_promotion_gate(ROOT, input_manifest_path=input_path, output_dir=root / "out")
            self.assertEqual(result["hard_gates"]["trace_completeness"]["status"], "FAIL")

    def test_execution_configuration_drift_is_recomputed_and_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = promotion_input(root)
            inputs = json.loads(input_path.read_text(encoding="utf-8"))
            execution = json.loads(Path(inputs["artifacts"]["execution_replay"]["path"]).read_text(encoding="utf-8"))
            skill = Path(execution["workspace"]) / "product" / "skills" / "portfolio-council" / "SKILL.md"
            skill.chmod(0o644)
            skill.write_text(skill.read_text(encoding="utf-8") + "\nconfiguration drift\n", encoding="utf-8")
            result = run_promotion_gate(ROOT, input_manifest_path=input_path, output_dir=root / "out")
            self.assertEqual(result["hard_gates"]["execution_replay"]["status"], "FAIL")

    def test_actual_subprocess_assertion_failure_blocks_promotion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = promotion_input(root)
            inputs = json.loads(input_path.read_text(encoding="utf-8"))
            run_deterministic_test_evidence(
                ROOT,
                output_dir=root / "failed-test-evidence",
                tmpdir=root / "failed-test-tmp",
                test_targets=(
                    "evals.promotion.assertion_failure_fixture."
                    "IntentionalPromotionAssertionFailure."
                    "test_intentional_assertion_failure",
                ),
            )
            report_path = root / "failed-test-evidence" / "result.json"
            inputs["artifacts"]["deterministic_tests"] = {
                "path": str(report_path),
                "sha256": file_hash(report_path),
            }
            input_path.write_text(json.dumps(inputs), encoding="utf-8")
            result = run_promotion_gate(ROOT, input_manifest_path=input_path, output_dir=root / "out")
            detail = result["hard_gates"]["deterministic_tests"]["detail"]
            self.assertEqual(result["hard_gates"]["deterministic_tests"]["status"], "FAIL")
            self.assertEqual(detail["assertion_failures"], 1)
            self.assertEqual(detail["test_errors"], 0)
            self.assertNotEqual(detail["exit_code"], 0)

    def test_topology_change_requires_measurable_ablation_gain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_promotion_gate(
                ROOT,
                input_manifest_path=promotion_input(root, topology_change=True),
                output_dir=root / "out",
            )
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("PROMOTION_ABLATION_GAIN_REQUIRED", result["reason_codes"])

    def test_failed_semantic_calibration_blocks_promotion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_promotion_gate(
                ROOT,
                input_manifest_path=promotion_input(root, calibration_pass=False),
                output_dir=root / "out",
            )
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("PROMOTION_HARD_GATE_FAILED:semantic_calibration", result["reason_codes"])

    def test_missing_new_format_baseline_evidence_returns_auditable_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_promotion_gate(
                ROOT,
                input_manifest_path=promotion_input(root, baseline_complete=False),
                output_dir=root / "out",
            )
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("PROMOTION_HARD_GATE_FAILED:version_completeness", result["reason_codes"])
            self.assertEqual(result["soft_metrics"]["semantic"]["status"], "NOT_COMPARABLE")

    def test_legacy_baseline_manifest_returns_auditable_fail_instead_of_crashing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_promotion_gate(
                ROOT,
                input_manifest_path=promotion_input(root, legacy_baseline=True),
                output_dir=root / "out",
            )
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("PROMOTION_HARD_GATE_FAILED:version_completeness", result["reason_codes"])
            detail = result["hard_gates"]["version_completeness"]["detail"]
            self.assertFalse(detail["baseline_manifest_valid"])
            self.assertIn("manifest_version", detail["baseline_manifest_diagnostic"])

    def test_static_candidate_without_evidence_graph_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "static.json"
            path.write_text(json.dumps({"schema_version": "promotion-input/1.0.0", "passed": True}), encoding="utf-8")
            with self.assertRaises(ValueError):
                run_promotion_gate(ROOT, input_manifest_path=path, output_dir=root / "out")

    def test_same_immutable_inputs_produce_same_result(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = promotion_input(root)
            first = run_promotion_gate(ROOT, input_manifest_path=input_path, output_dir=root / "out-1")
            second_inputs = json.loads(input_path.read_text(encoding="utf-8"))
            second_inputs["gate_id"] = "gate-2"
            second_path = root / "promotion-input-2.json"
            second_path.write_text(json.dumps(second_inputs), encoding="utf-8")
            second = run_promotion_gate(ROOT, input_manifest_path=second_path, output_dir=root / "out-2")
            self.assertEqual(first["status"], second["status"])
            self.assertEqual(first["hard_gates"], second["hard_gates"])
            self.assertEqual(first["reason_codes"], second["reason_codes"])
            self.assertEqual(first["soft_metrics"], second["soft_metrics"])
            self.assertNotEqual(first["gate_id"], second["gate_id"])
            self.assertIsNone(first["prior_result"])
            self.assertEqual(second["prior_result"]["gate_id"], first["gate_id"])

    def test_duplicate_gate_id_is_rejected_without_overwriting_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = promotion_input(root)
            run_promotion_gate(ROOT, input_manifest_path=input_path, output_dir=root / "out-1")
            with self.assertRaisesRegex(RuntimePromotionError, "PROMOTION_GATE_ID_ALREADY_EXISTS"):
                run_promotion_gate(ROOT, input_manifest_path=input_path, output_dir=root / "out-2")

    def test_candidate_artifacts_cannot_masquerade_as_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = promotion_input(root)
            inputs = json.loads(input_path.read_text(encoding="utf-8"))
            inputs["artifacts"]["baseline_runtime_evals"] = list(inputs["artifacts"]["runtime_evals"][:1])
            inputs["artifacts"]["baseline_ablation"] = dict(inputs["artifacts"]["ablation"])
            input_path.write_text(json.dumps(inputs), encoding="utf-8")
            result = run_promotion_gate(ROOT, input_manifest_path=input_path, output_dir=root / "out")
            self.assertEqual(result["status"], "FAIL")
            detail = result["hard_gates"]["version_completeness"]["detail"]
            self.assertTrue(any("BASELINE_EVAL_VERSION_MISMATCH" in item for item in detail["version_binding_errors"]))

    def test_missing_named_eval_hard_gate_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = promotion_input(root)
            inputs = json.loads(input_path.read_text(encoding="utf-8"))
            eval_path = Path(inputs["artifacts"]["runtime_evals"][0]["path"])
            evaluation = json.loads(eval_path.read_text(encoding="utf-8"))
            evaluation.pop("eval_hash")
            evaluation["hard_gates"].pop("evidence_closure")
            evaluation["eval_hash"] = canonical_hash(evaluation)
            eval_path.write_text(json.dumps(evaluation), encoding="utf-8")
            inputs["artifacts"]["runtime_evals"][0]["sha256"] = file_hash(eval_path)
            for record in inputs["artifacts"]["baseline_runtime_evals"]:
                if Path(record["path"]).resolve() == eval_path.resolve():
                    record["sha256"] = file_hash(eval_path)
            input_path.write_text(json.dumps(inputs), encoding="utf-8")
            result = run_promotion_gate(ROOT, input_manifest_path=input_path, output_dir=root / "out")
            self.assertEqual(result["hard_gates"]["evidence_closure"]["status"], "FAIL")
            self.assertEqual(result["status"], "FAIL")

    def test_missing_cost_telemetry_is_reported_as_unavailable_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            input_path = promotion_input(root)
            inputs = json.loads(input_path.read_text(encoding="utf-8"))
            for key in ("ablation", "baseline_ablation"):
                path = Path(inputs["artifacts"][key]["path"])
                value = json.loads(path.read_text(encoding="utf-8"))
                value.pop("report_hash")
                for profile in value["profiles"]:
                    profile["metrics"]["telemetry_status"] = "MISSING_TELEMETRY"
                    profile["metrics"]["latency_ms"] = None
                value["report_hash"] = canonical_hash(value)
                path.write_text(json.dumps(value), encoding="utf-8")
                inputs["artifacts"][key]["sha256"] = file_hash(path)
            input_path.write_text(json.dumps(inputs), encoding="utf-8")
            result = run_promotion_gate(ROOT, input_manifest_path=input_path, output_dir=root / "out")
            cost = result["soft_metrics"]["cost_and_latency"]
            self.assertEqual(cost["status"], "FAIL_COST_COMPARISON")
            self.assertIsNone(cost["candidate_tokens"])


if __name__ == "__main__":
    unittest.main()
