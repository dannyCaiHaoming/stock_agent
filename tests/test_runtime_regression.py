from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from evals.regression.runner import (
    REGRESSION_CASE_IDS,
    RegressionError,
    case_cache_key,
    execute_deterministic_case,
    _check_invariant,
    load_regression_set,
    run_regression_suite,
)
from product.runtime.hashing import canonical_hash
from product.runtime.regression_invariants import (
    INVARIANT_REGISTRY,
    evaluate_expected_invariant,
    expected_invariant_schema,
    validate_invariant_schema_binding,
)
from product.runtime.schema_validation import SchemaValidationError
from product.runtime.runtime_eval import _future_injection_check
from product.runtime.run_package import RunPackageError, prepare_run


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_HASH = canonical_hash(json.loads((ROOT / "product" / "version-manifest.json").read_text(encoding="utf-8")))


class RuntimeRegressionTests(unittest.TestCase):
    def test_risk_veto_requires_an_actual_rejected_risk_result(self):
        invariant = {"type": "EXPECT_RISK_VETO", "value": True, "hard": True}
        self.assertFalse(_check_invariant(invariant, {"action": "NO_TRADE", "risk_status": "APPROVED"}))
        self.assertTrue(_check_invariant(invariant, {"action": "NO_TRADE", "risk_status": "REJECTED"}))

    def test_every_typed_invariant_has_positive_and_negative_evaluation(self):
        semantic_pass = {
            name: {"status": "PASS"} for name in (
                "no_trade_reasoning",
                "analyst_thesis_grounding",
                "skeptic_counter_evidence",
                "cio_conflict_handling",
                "confidence_calibration",
            )
        }
        samples = {
            "TERMINAL_STATE_IN": (["COMPLETED"], {"terminal_state": "COMPLETED"}, {"terminal_state": "FAILED_VALIDATION"}),
            "AGENTS_INCLUDE": (["runtime_cio"], {"agents_run": ["runtime_cio"]}, {"agents_run": []}),
            "AGENTS_EXCLUDE": (["runtime_skeptic"], {"agents_run": []}, {"agents_run": ["runtime_skeptic"]}),
            "RISK_NOT_BYPASSED": (True, {"risk_bypassed": False}, {"risk_bypassed": True}),
            "EXPECT_RISK_PASS": (True, {"risk_status": "APPROVED"}, {"risk_status": "REJECTED"}),
            "EXPECT_RISK_VETO": (True, {"risk_status": "REJECTED"}, {"risk_status": "APPROVED"}),
            "EXPECT_NO_TRADE": (True, {"action": "NO_TRADE"}, {"action": "HOLD"}),
            "NO_FUTURE_EVIDENCE": (True, {"no_future_evidence": True}, {"no_future_evidence": False}),
            "EVIDENCE_CLOSURE": (True, {"evidence_closure": True}, {"evidence_closure": False}),
            "TRACE_COMPLETE": (True, {"trace_complete": True}, {"trace_complete": False}),
            "SPECIALIST_OUTPUT_VALID": (True, {"specialist_output_valid": True}, {"specialist_output_valid": False}),
            "CIO_CONFLICT_HANDLED": (True, {"cio_conflict_handled": True}, {"cio_conflict_handled": False}),
            "EXPECT_FAILED_STAGE": ("SPECIALIST_VALIDATION", {"failed_stage": "SPECIALIST_VALIDATION"}, {"failed_stage": "RISK_ENGINE"}),
            "EVIDENCE_SUBSET_OF_GATE": (True, {"evidence_subset_of_gate": True}, {"evidence_subset_of_gate": False}),
            "SEMANTIC_DIMENSIONS_APPLICABLE": (
                ["cio_conflict_handling"],
                {"semantic_dimensions": semantic_pass},
                {"semantic_dimensions": {"cio_conflict_handling": {"status": "NOT_APPLICABLE"}}},
            ),
            "EXPECT_VALIDATION_REJECTION": (
                "SCHEMA_INVALID",
                {"validator_rejection": "SCHEMA_INVALID"},
                {"validator_rejection": "EVIDENCE_CLOSURE_FAILED"},
            ),
            "LLM_CALLS_EQUAL": (0, {"llm_calls": 0}, {"llm_calls": 1}),
            "VALID_ACTION_SET": (
                ["BUY", "HOLD", "TRIM", "EXIT"],
                {"valid_action_set": ["BUY", "HOLD", "TRIM", "EXIT"]},
                {"valid_action_set": ["HOLD"]},
            ),
            "FORBIDDEN_ACTION": ("REDUCE", {"forbidden_actions": ["REDUCE"]}, {"forbidden_actions": []}),
        }
        self.assertEqual(set(samples), set(INVARIANT_REGISTRY))
        for name, (value, positive, negative) in samples.items():
            invariant = {"type": name, "value": value, "hard": True}
            with self.subTest(invariant=name, polarity="positive"):
                self.assertTrue(evaluate_expected_invariant(invariant, positive))
            with self.subTest(invariant=name, polarity="negative"):
                self.assertFalse(evaluate_expected_invariant(invariant, negative))

    def test_unknown_or_mistyped_invariant_fails_closed(self):
        with self.assertRaisesRegex(SchemaValidationError, "SCHEMA_ONE_OF_INVALID"):
            evaluate_expected_invariant(
                {"type": "UNKNOWN_INVARIANT", "value": True, "hard": True},
                {},
            )
        with self.assertRaisesRegex(SchemaValidationError, "SCHEMA_ONE_OF_INVALID"):
            evaluate_expected_invariant(
                {"type": "LLM_CALLS_EQUAL", "value": "zero", "hard": True},
                {},
            )

    def test_checked_in_schema_is_generated_from_canonical_registry(self):
        schema = json.loads(
            (ROOT / "product" / "schemas" / "runtime" / "regression-case.schema.json").read_text()
        )
        validate_invariant_schema_binding(schema)
        self.assertEqual(
            schema["properties"]["expected_invariants"]["items"],
            expected_invariant_schema(),
        )

    def test_set_contains_exactly_twelve_invariant_cases_with_provenance(self):
        regression = load_regression_set(ROOT)
        self.assertEqual({case["case_id"] for case in regression["cases"]}, REGRESSION_CASE_IDS)
        self.assertEqual(len(regression["cases"]), 12)
        for case in regression["cases"]:
            self.assertNotIn("ACTION_EQUALS", {item["type"] for item in case["expected_invariants"]})
            fixture = json.loads((ROOT / case["fixture"]).read_text(encoding="utf-8"))
            for fact in fixture["evidence"]:
                self.assertTrue(fact["source_id"])
                self.assertTrue(fact["as_of"])
                self.assertTrue(fact["retrieved_at"])

    def test_all_deterministic_injections_execute_with_zero_llm_calls(self):
        regression = load_regression_set(ROOT)
        for case in regression["cases"]:
            if not case["llm_required"]:
                result = execute_deterministic_case(ROOT, case)
                self.assertEqual(result["llm_calls"], 0, case["case_id"])
                self.assertTrue(result["not_llm_output"])

    def test_fixed_investment_answer_invariant_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            copied = Path(directory) / "v1"
            shutil.copytree(ROOT / "evals" / "regression" / "v1", copied)
            path = copied / "cases" / "normal-research.json"
            case = json.loads(path.read_text(encoding="utf-8"))
            case["expected_invariants"].append({"type": "action_equals", "value": "BUY", "hard": True})
            path.write_text(json.dumps(case), encoding="utf-8")
            with self.assertRaisesRegex(RegressionError, "FIXED_INVESTMENT_ANSWER"):
                load_regression_set(ROOT, set_root=copied)

    def test_cache_key_changes_with_any_versioned_input(self):
        case = load_regression_set(ROOT)["cases"][0]
        values = {
            "candidate_hash": "a" * 64,
            "model": "gpt-5.6-terra",
            "codex_runtime": "codex-cli/0.153.4",
            "runtime_profile_hash": "b" * 64,
            "gate_context_hash": "f" * 64,
            "rubric_hash": "c" * 64,
            "grader_hash": "d" * 64,
        }
        first = case_cache_key(case, **values)
        changed = dict(values, rubric_hash="e" * 64)
        self.assertNotEqual(first, case_cache_key(case, **changed))

    def test_suite_does_not_accept_missing_static_llm_claims(self):
        with tempfile.TemporaryDirectory() as directory:
            result = run_regression_suite(
                ROOT,
                output_dir=Path(directory) / "suite",
                suite_id="suite-missing-real-runs",
                candidate_hash=CANDIDATE_HASH,
                run_index={},
            )
            self.assertEqual(result["status"], "FAIL")
            deterministic = [item for item in result["case_results"] if not item["llm_required"]]
            self.assertTrue(all(item["status"] == "PASS" for item in deterministic))
            llm = [item for item in result["case_results"] if item["llm_required"]]
            self.assertTrue(all(item["status"] == "FAIL" for item in llm))

    def test_verified_cache_hit_reuses_hash_bound_runtime_artifacts(self):
        from tests.test_runtime_ablation import build_variant

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = build_variant(root, "full-council")
            cache = root / "cache"
            first = run_regression_suite(
                ROOT,
                output_dir=root / "suite-1",
                suite_id="suite-cache-miss",
                candidate_hash=CANDIDATE_HASH,
                run_index={"normal-research": entry},
                cache_dir=cache,
            )
            normal = next(item for item in first["case_results"] if item["case_id"] == "normal-research")
            self.assertEqual(normal["cache_provenance"]["status"], "MISS")
            proof = json.loads(
                Path(normal["execution_proof"]["path"]).read_text(encoding="utf-8")
            )
            self.assertEqual(
                proof["executed_operations"],
                ["trace_integrity_report", "artifact_replay", "runtime_eval_verify"],
            )
            self.assertTrue(proof["hashes"]["artifact_replay"])
            self.assertTrue(proof["hashes"]["runtime_eval"])
            cache_path = next(cache.glob("*.json"))
            second = run_regression_suite(
                ROOT,
                output_dir=root / "suite-2",
                suite_id="suite-cache-hit",
                candidate_hash=CANDIDATE_HASH,
                run_index={"normal-research": {"cache_record": str(cache_path)}},
            )
            reused = next(item for item in second["case_results"] if item["case_id"] == "normal-research")
            self.assertEqual(reused["cache_provenance"]["status"], "HIT")
            self.assertEqual(normal["outcome"], reused["outcome"])

            record = json.loads(cache_path.read_text(encoding="utf-8"))
            record["inputs"]["rubric_hash"] = "0" * 64
            cache_path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(RegressionError, "CACHE_RECORD_HASH_INVALID"):
                run_regression_suite(
                    ROOT,
                    output_dir=root / "suite-3",
                    suite_id="suite-cache-invalid",
                    candidate_hash=CANDIDATE_HASH,
                    run_index={"normal-research": {"cache_record": str(cache_path)}},
                )

    def test_runtime_artifact_must_match_declared_candidate_manifest(self):
        from tests.test_runtime_ablation import build_variant

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = build_variant(root, "full-council")
            with self.assertRaisesRegex(RegressionError, "REGRESSION_CANDIDATE_VERSION_MISMATCH"):
                run_regression_suite(
                    ROOT,
                    output_dir=root / "suite-drift",
                    suite_id="suite-candidate-drift",
                    candidate_hash="f" * 64,
                    run_index={"normal-research": entry},
                )
    def test_duplicate_runtime_run_id_is_rejected_before_suite_execution(self):
        from tests.test_runtime_ablation import build_variant

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shared = build_variant(root, "full-council")
            with self.assertRaisesRegex(RegressionError, "DUPLICATE_RUN_ID"):
                run_regression_suite(
                    ROOT,
                    output_dir=root / "suite-duplicate",
                    suite_id="suite-duplicate",
                    candidate_hash=CANDIDATE_HASH,
                    run_index={
                        "normal-research": shared,
                        "insufficient-evidence": shared,
                    },
                )

    def test_every_case_records_unique_run_id_and_execution_artifacts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_regression_suite(
                ROOT,
                output_dir=root / "suite",
                suite_id="suite-unique-evidence",
                candidate_hash=CANDIDATE_HASH,
                run_index={},
            )
            run_ids = [item["outcome"]["run_id"] for item in result["case_results"]]
            self.assertEqual(len(run_ids), len(set(run_ids)))
            for item in result["case_results"]:
                self.assertTrue(Path(item["execution_proof"]["path"]).is_file())
                self.assertTrue(Path(item["outcome_artifact"]["path"]).is_file())
                if not item["llm_required"]:
                    proof = json.loads(
                        Path(item["execution_proof"]["path"]).read_text(encoding="utf-8")
                    )
                    self.assertEqual(proof["producer"], "deterministic-injection")
                    self.assertEqual(
                        proof["executed_operations"],
                        [
                            "deterministic_injection",
                            "trace_integrity_report",
                            "artifact_replay",
                            "runtime_eval_verify",
                        ],
                    )
                    self.assertTrue(Path(proof["artifacts"]["run_dir"]).is_dir())
                    self.assertTrue(Path(proof["artifacts"]["decision_trace"]).is_file())
                    self.assertTrue(Path(proof["artifacts"]["eval_result"]).is_file())
                    self.assertIn("deterministic_outcome", proof["hashes"])
                    self.assertEqual(proof["llm_calls_during_verification"], 0)
                    run_dir = Path(proof["artifacts"]["run_dir"])
                    if item["case_id"] == "future-information-leakage":
                        gate = json.loads(
                            (run_dir / "evidence" / "gate.json").read_text(encoding="utf-8")
                        )
                        trace = json.loads(
                            (run_dir / "decision_trace.json").read_text(encoding="utf-8")
                        )
                        injection = json.loads(
                            (run_dir / "audit" / "regression-injection.json").read_text(encoding="utf-8")
                        )
                        self.assertEqual(item["outcome"]["future_leak_count"], 0)
                        self.assertEqual(item["outcome"]["terminal_state"], "SAFE_NO_TRADE")
                        self.assertTrue(item["outcome"]["future_injection_verified"])
                        self.assertTrue(
                            set(item["outcome"]["injected_evidence_ids"])
                            <= set(gate["excluded_evidence_ids"])
                        )
                        event = next(
                            event for event in trace["events"]
                            if event.get("stage") == "REGRESSION_FIXTURE_INJECTED"
                        )
                        self.assertEqual(event["producer"], "regression-fixture-injector")
                        self.assertEqual(event["injection_version"], "future-evidence-injection/1.0.0")
                        self.assertEqual(event["injected_evidence"], injection["injected_evidence"])
                        self.assertEqual(event["decision_cutoff"], gate["decision_cutoff"])
                        self.assertIn("regression_injection", proof["hashes"])
                    if item["case_id"] == "valid-action-contract":
                        trace = json.loads(
                            (run_dir / "decision_trace.json").read_text(encoding="utf-8")
                        )
                        self.assertEqual(item["outcome"]["terminal_state"], "COMPLETED")
                        self.assertEqual(item["outcome"]["action"], "HOLD")
                        self.assertFalse(item["outcome"]["risk_bypassed"])
                        self.assertTrue(trace["risk_lineage"])
                        self.assertEqual(
                            trace["risk_lineage"][-1]["result"]["check"]["status"],
                            "APPROVED",
                        )
                        risk_types = {
                            invariant["type"]
                            for invariant in next(
                                case for case in load_regression_set(ROOT)["cases"]
                                if case["case_id"] == "valid-action-contract"
                            )["expected_invariants"]
                        }
                        self.assertTrue(
                            {"EXPECT_RISK_PASS", "RISK_NOT_BYPASSED"} <= risk_types
                        )

    def test_future_injection_eval_rejects_missing_trace_event_and_gate_bypass(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = run_regression_suite(
                ROOT,
                output_dir=root / "suite",
                suite_id="suite-future-injection-negative",
                candidate_hash=CANDIDATE_HASH,
                run_index={},
            )
            item = next(
                case for case in result["case_results"]
                if case["case_id"] == "future-information-leakage"
            )
            run_dir = Path(item["execution_proof"]["path"]).parent / "run"
            trace = json.loads((run_dir / "decision_trace.json").read_text())
            gate = json.loads((run_dir / "evidence" / "gate.json").read_text())
            without_event = copy.deepcopy(trace)
            without_event["events"] = [
                event for event in without_event["events"]
                if event.get("stage") != "REGRESSION_FIXTURE_INJECTED"
            ]
            self.assertFalse(
                _future_injection_check(
                    run_dir, trace=without_event, gate=gate
                )["injection_verified"]
            )
            bypassed_gate = copy.deepcopy(gate)
            bypassed_gate["allowed_evidence_ids"].append("ev-future-asof")
            self.assertFalse(
                _future_injection_check(
                    run_dir, trace=trace, gate=bypassed_gate
                )["injection_verified"]
            )

    def test_regression_injection_fixture_exception_is_scoped_to_its_case_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "case" / "run"
            unrelated = root / "unrelated" / "injected-fixture.json"
            unrelated.parent.mkdir(parents=True)
            shutil.copyfile(
                ROOT / "evals" / "fixtures" / "codex-native" / "future-or-stale.json",
                unrelated,
            )
            with self.assertRaisesRegex(
                RunPackageError,
                "fixture must come from the versioned codex-native fixture root",
            ):
                prepare_run(
                    ROOT,
                    fixture_path=unrelated,
                    run_dir=run_dir,
                    run_id="regression-injection-path-escape",
                    model="gpt-5.6-terra",
                    research_question="验证回归注入路径边界。",
                    authenticity_required=False,
                    trigger_reason="regression_deterministic_injection",
                )


if __name__ == "__main__":
    unittest.main()
