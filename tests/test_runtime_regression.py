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
    def _contract_cio(self, root: Path, *, trigger="regression_deterministic_injection") -> Path:
        from evals.regression.runner import _valid_specialist_contract_outputs
        from product.runtime.run_package import prepare_cio
        case = next(x for x in load_regression_set(ROOT)["cases"] if x["case_id"] == "valid-action-contract")
        run = root / "run"
        prepare_run(ROOT, fixture_path=ROOT / case["fixture"], run_dir=run,
                    run_id="contract-handoff", model="gpt-6-luna", research_question="契约检查",
                    authenticity_required=False, trigger_reason=trigger)
        _valid_specialist_contract_outputs(run)
        record = {"schema_version": "regression-injection/1.0.0", "case_id": case["case_id"],
                  "injection": case["injection"], "llm_calls": 0,
                  "deterministic_outcome_hash": execute_deterministic_case(ROOT, case)["outcome_hash"]}
        (run / "audit/regression-injection.json").write_text(json.dumps(record))
        self.assertEqual(prepare_cio(ROOT, run_dir=run, model="gpt-6-luna")["next_state"], "CIO_SYNTHESIS_REQUIRED")
        (run / "cio").mkdir()
        return run

    def test_contract_handoff_rejects_report_drift_unread_unknown_and_wrong_identity(self):
        from evals.regression.runner import _valid_cio_contract_output
        from product.runtime.run_package import finalize_cio
        for defect in ("drift", "unread", "unknown", "identity"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                run = self._contract_cio(Path(directory).resolve())
                if defect == "drift":
                    path = run / "agents/runtime_company_analyst.json"
                    path.write_text(path.read_text() + " ")
                    with self.assertRaisesRegex(RegressionError, "CIO_REPORT_DRIFT"):
                        _valid_cio_contract_output(run)
                    continue
                draft = _valid_cio_contract_output(run)
                events_path = run / "events/mcp/events.jsonl"
                events = [json.loads(line) for line in events_path.read_text().splitlines()]
                if defect == "unknown":
                    draft["report_selections"] = ["p.outside-current-run"]
                elif defect == "unread":
                    events = [event for event in events if event.get("tool") not in {"research_reports.read", "read_reports"}]
                else:
                    for event in events:
                        if event.get("tool") == "research_reports.read":
                            event["invocation_id"] = "other-invocation"
                events_path.write_text("".join(json.dumps(event) + "\n" for event in events))
                (run / "cio/runtime_cio.json").write_text(json.dumps(draft))
                outcome = finalize_cio(ROOT, run_dir=run)
                self.assertEqual(outcome["terminal_state"], "FAILED_VALIDATION")
                self.assertEqual(json.loads((run / "run_error.json").read_text())["code"], "CIO_VALIDATION_FAILED")
                self.assertFalse((run / "decision.json").exists())

    def test_contract_only_scoring_is_explicit_and_reverified(self):
        from evals.regression.runner import _materialize_deterministic_case
        from product.runtime.runtime_eval import RuntimeEvalError, prepare_eval_job, finalize_eval_job, verify_runtime_eval_job, build_eval_smoke_prompt
        from tests.test_runtime_eval_job import semantic_result
        case = next(x for x in load_regression_set(ROOT)["cases"] if x["case_id"] == "valid-action-contract")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            _materialize_deterministic_case(ROOT, case=case, suite_id="contract-semantic", candidate_hash=CANDIDATE_HASH, case_dir=root / "case")
            run = root / "case/run"
            eval_dir = root / "case/runtime-eval"
            # 当前 native 草稿交给实际 finalizer，技术身份只存在于正式产物。
            native = json.loads((run / "cio/native-draft.json").read_text())
            formal = json.loads((run / "cio/runtime_cio.json").read_text())
            self.assertEqual(native["schema_version"], "native-cio-draft/1.0.0")
            self.assertNotIn("consumed_reports", native)
            self.assertEqual(len(formal["consumed_reports"]), 2)
            result_path = eval_dir / "eval/result.json"
            self.assertEqual(verify_runtime_eval_job(ROOT, eval_result_path=result_path)["status"], "PASS")
            result = json.loads(result_path.read_text())
            self.assertEqual(result["grader"]["model"], "none")
            self.assertEqual(result["grader"]["agent"], "deterministic-not-applicable")
            self.assertEqual({v["status"] for v in result["semantic_rubric"].values()}, {"NOT_APPLICABLE"})
            ordinary = root / "ordinary-eval"
            prepared = prepare_eval_job(ROOT, run_dir=run, eval_dir=ordinary, eval_id="ordinary")
            self.assertTrue(prepared["semantic_required"])
            with self.assertRaisesRegex(RuntimeEvalError, "SEMANTIC_RESULT_REQUIRED"):
                finalize_eval_job(ROOT, eval_dir=ordinary)
            contract = root / "contract-eval"
            prepared = prepare_eval_job(ROOT, run_dir=run, eval_dir=contract, eval_id="contract", contract_only=True)
            self.assertFalse(prepared["semantic_required"])
            with self.assertRaisesRegex(RuntimeEvalError, "CONTRACT_ONLY_MODEL_EXECUTION_FORBIDDEN"):
                build_eval_smoke_prompt(ROOT, eval_dir=contract)
            grade_path = root / "fake-model-grade.json"
            grade_path.write_text(json.dumps(semantic_result(contract)))
            with self.assertRaisesRegex(RuntimeEvalError, "NOT_APPLICABLE_MODEL_RESULT_FORBIDDEN"):
                finalize_eval_job(ROOT, eval_dir=contract, semantic_result_path=grade_path)
            # 冻结作业不能篡改声明以伪装真实模型作业。
            manifest_path = eval_dir / "input-manifest.json"
            manifest = json.loads(manifest_path.read_text())
            for key, value, error in (("authenticity_required", True, "CONTRACT_ONLY_NOT_AUTHORIZED"),
                                      ("semantic_evaluation_mode", "unknown", "SEMANTIC_MODE_INVALID")):
                bad = {**manifest, key: value}
                manifest_path.write_text(json.dumps(bad))
                with self.assertRaisesRegex(RuntimeEvalError, error):
                    verify_runtime_eval_job(ROOT, eval_result_path=result_path)
            manifest_path.write_text(json.dumps(manifest))
            without_mode = dict(manifest)
            without_mode.pop("semantic_evaluation_mode")
            manifest_path.write_text(json.dumps(without_mode))
            with self.assertRaisesRegex(RuntimeEvalError, "SEMANTIC_GRADER_LINEAGE_INVALID"):
                verify_runtime_eval_job(ROOT, eval_result_path=result_path)
            manifest_path.write_text(json.dumps(manifest))

    def test_ordinary_run_cannot_request_contract_only_scoring(self):
        from evals.regression.runner import _valid_cio_contract_output
        from product.runtime.run_package import finalize_cio
        from product.runtime.runtime_eval import RuntimeEvalError, prepare_eval_job
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            run = self._contract_cio(root, trigger="product_council")
            (run / "cio/runtime_cio.json").write_text(json.dumps(_valid_cio_contract_output(run)))
            self.assertEqual(finalize_cio(ROOT, run_dir=run)["next_state"], "COMPLETED")
            with self.assertRaisesRegex(RuntimeEvalError, "CONTRACT_ONLY_NOT_AUTHORIZED"):
                prepare_eval_job(ROOT, run_dir=run, eval_dir=root / "eval", eval_id="forged", contract_only=True)
            self.assertFalse((root / "eval").exists())

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

    def test_new_deterministic_run_uses_current_luna_candidate(self):
        from evals.regression.runner import _materialize_deterministic_case
        case = next(x for x in load_regression_set(ROOT)["cases"] if x["case_id"] == "all-evidence-stale")
        with tempfile.TemporaryDirectory() as directory:
            case_dir = Path(directory).resolve() / "case"
            _materialize_deterministic_case(ROOT, case=case, suite_id="luna-route",
                candidate_hash=CANDIDATE_HASH, case_dir=case_dir)
            manifest = json.loads((case_dir / "run/run_manifest.json").read_text())
            self.assertEqual(manifest["model"], "gpt-6-luna")
            self.assertFalse((case_dir / "run/invocation/codex-events.jsonl").exists())

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
            "model": "gpt-6-luna",
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
                    model="gpt-6-luna",
                    research_question="验证回归注入路径边界。",
                    authenticity_required=False,
                    trigger_reason="regression_deterministic_injection",
                )


if __name__ == "__main__":
    unittest.main()
