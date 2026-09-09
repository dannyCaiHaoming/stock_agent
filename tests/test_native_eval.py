from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from product.runtime.artifact_matrix import validate_artifact_matrix
from product.runtime.hashing import canonical_hash
from product.runtime.native_eval import (
    EVAL_SCOPE,
    NativeEvalError,
    evaluate_run,
    persist_eval_result,
    validate_native_eval_result,
)
from product.runtime.run_package import finalize_cio, prepare_cio, prepare_run
from tests.test_native_run_package import FIXTURES, ROOT, cio_output, specialist_outputs, write_json


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def scenario_specialist_outputs(run_dir: Path):
    gate = read_json(run_dir / "evidence" / "gate.json")
    evidence_ids = gate["allowed_evidence_ids"]
    analyst_evidence = next(
        (item for item in evidence_ids if item.endswith("revenue-a")), evidence_ids[0]
    )
    skeptic_evidence = next(
        (item for item in evidence_ids if item.endswith("revenue-b")), evidence_ids[-1]
    )
    analyst = read_json(run_dir / "invocations" / "runtime_company_analyst.json")
    skeptic = read_json(run_dir / "invocations" / "runtime_skeptic.json")
    write_json(
        run_dir / "agents" / "runtime_company_analyst.json",
        {
            "schema_version": "agent-research-report/2.0.0",
            "run_id": analyst["run_id"],
            "invocation_id": analyst["invocation_id"],
            "status": "COMPLETE",
            "agent": "runtime_company_analyst",
            "scope": "Fixture company research",
            "claims": [{
                "claim_id": "claim-scenario",
                "statement": "One Gate-admitted observation supports the company analysis.",
                "kind": "FACT",
                "evidence_refs": [analyst_evidence],
                "assumption_ids": [],
            }],
            "assumptions": [],
            "counter_evidence_refs": [],
            "uncertainties": ["The fixture is intentionally bounded."],
            "data_gaps": [],
            "invalidation_conditions": ["A later point-in-time record changes the observation."],
            "confidence": 0.55,
            "confidence_rationale": "Confidence is limited to the admitted fixture evidence.",
            "skill_execution": analyst["skill_execution"],
            "artifact_refs": [],
        },
    )
    write_json(
        run_dir / "agents" / "runtime_skeptic.json",
        {
            "schema_version": "counter-thesis-report/2.0.0",
            "run_id": skeptic["run_id"],
            "invocation_id": skeptic["invocation_id"],
            "status": "COMPLETE",
            "agent": "runtime_skeptic",
            "mode": "INDEPENDENT_FIRST_PASS",
            "scope": "Independent fixture challenge",
            "challenges": [{
                "challenge_id": "challenge-scenario",
                "statement": "A separate admitted observation creates an unresolved limitation.",
                "evidence_refs": [skeptic_evidence],
                "assumption_ids": [],
                "resolution_evidence_needed": ["A reconciled point-in-time source."],
            }],
            "evidence_refs": [skeptic_evidence],
            "counter_evidence_refs": [],
            "uncertainties": [],
            "data_gaps": ["No reconciled source is available in the fixture."],
            "invalidation_conditions": ["The source conflict is reconciled."],
            "confidence": 0.45,
            "confidence_rationale": "The challenge is independent and evidence-linked.",
            "skill_execution": skeptic["skill_execution"],
            "artifact_refs": [],
        },
    )


def scenario_cio_output(run_dir: Path, *, include_conflict: bool = True):
    manifest = read_json(run_dir / "invocations" / "runtime_cio.json")
    run_manifest = read_json(run_dir / "run_manifest.json")
    reports = [
        read_json(run_dir / "agents" / "runtime_company_analyst.json"),
        read_json(run_dir / "agents" / "runtime_skeptic.json"),
    ]
    refs = sorted({
        ref
        for report in reports
        for key in ("evidence_refs", "counter_evidence_refs")
        for ref in report.get(key, [])
    } | {
        ref
        for claim in reports[0]["claims"]
        for ref in claim["evidence_refs"]
    } | {
        ref
        for challenge in reports[1]["challenges"]
        for ref in challenge["evidence_refs"]
    })
    is_conflict = run_manifest["fixture_id"] == "evidence-conflict-v1"
    is_risk = run_manifest["fixture_id"] == "risk-veto-v1"
    conflicts = []
    if is_conflict and include_conflict:
        conflicts = [{
            "conflict_key": "SEC-AAA:revenue_ttm:2025-12-31",
            "evidence_refs": ["ev-conflict-revenue-a", "ev-conflict-revenue-b"],
            "summary": "Two admitted sources report incompatible revenue values.",
            "unresolved": True,
            "decision_impact": "Do not increase exposure until the values are reconciled.",
            "confidence_impact": "The unresolved conflict lowers confidence.",
        }]
    current_weight = 0.9 if is_risk else 0.5
    return {
        "schema_version": "cio-decision-draft/2.1.0",
        "run_id": manifest["run_id"],
        "invocation_id": manifest["invocation_id"],
        "status": "COMPLETE",
        "agent": "runtime_cio",
        "consumed_reports": [
            {"agent": report["agent"], "output_hash": canonical_hash(report)}
            for report in reports
        ],
        "action": "NO_TRADE" if is_risk else "HOLD",
        "security_id": "SEC-AAA",
        "current_weight": current_weight,
        "target_weight_range": None if is_risk else [0.5, 0.5],
        "maximum_notional": None,
        "time_horizon": "fixture evaluation horizon",
        "thesis": "The admitted evidence supports a bounded monitoring decision.",
        "counter_thesis": "The independent challenge limits conviction.",
        "consensus": ["Both reports are limited to Gate-admitted evidence."],
        "conflicts": conflicts,
        "unresolved_questions": ["A reconciled source remains unavailable."],
        "invalidation_conditions": ["A later point-in-time record changes the evidence."],
        "confidence": 0.45,
        "confidence_rationale": "Unresolved evidence limitations reduce confidence.",
        "evidence_refs": refs,
        "no_trade_reason": "RISK_OR_MANDATE_CONSTRAINT" if is_risk else None,
        "no_trade_explanation": (
            "The existing fixture position already breaches deterministic limits."
            if is_risk else None
        ),
        "reevaluation_conditions": (
            ["Re-evaluate after the position is within mandate limits."]
            if is_risk else []
        ),
        "skill_execution": manifest["skill_execution"],
        "advisory_only": True,
    }


class NativeArtifactEvalTests(unittest.TestCase):
    def test_eval_schema_pins_bounded_non_performance_scope(self):
        schema = read_json(
            ROOT / "product" / "schemas" / "runtime" / "native-eval.schema.json"
        )
        self.assertEqual(schema["properties"]["scope"]["const"], EVAL_SCOPE)
        self.assertNotIn("market_outperformance", schema["properties"]["checks"])

    def _complete_scenario(self, directory: str, fixture: str, *, include_conflict=True):
        run_dir = Path(directory) / fixture.removesuffix(".json")
        prepare_run(
            ROOT,
            fixture_path=FIXTURES / fixture,
            run_dir=run_dir,
            run_id=f"eval-{fixture.removesuffix('.json')}",
            model="gpt-5.6-terra",
            research_question="研究 fixture。",
            authenticity_required=False,
        )
        if fixture != "future-or-stale.json":
            scenario_specialist_outputs(run_dir)
            prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")
            write_json(
                run_dir / "cio" / "runtime_cio.json",
                scenario_cio_output(run_dir, include_conflict=include_conflict),
            )
            finalize_cio(ROOT, run_dir=run_dir)
        return run_dir

    def test_eval_consumes_real_files_and_test_only_chain_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=run_dir,
                run_id="eval-chain",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
                authenticity_required=False,
            )
            specialist_outputs(run_dir)
            prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")
            write_json(run_dir / "cio" / "runtime_cio.json", cio_output(run_dir))
            finalize_cio(ROOT, run_dir=run_dir)
            with self.assertRaisesRegex(NativeEvalError, "TEST_ONLY_RUN"):
                evaluate_run(ROOT, run_dir=run_dir)
            result = evaluate_run(
                ROOT, run_dir=run_dir, allow_test_artifacts=True
            )
            persist_eval_result(result, run_dir=run_dir)
            self.assertEqual(result["status"], "PASSED")
            self.assertEqual(
                result["checks"]["native_agent_skill_mcp_authenticity"],
                "TEST_ONLY_BYPASS",
            )
            self.assertEqual(validate_artifact_matrix(run_dir)["status"], "PASSED")

    def test_future_stale_fixture_runs_actual_eval_without_agents(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "safe"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "future-or-stale.json",
                run_dir=run_dir,
                run_id="eval-safe",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
            )
            result = evaluate_run(ROOT, run_dir=run_dir)
            persist_eval_result(result, run_dir=run_dir)
            self.assertEqual(result["checks"]["future_stale_exact_filtering"], "PASSED")

    def test_eval_fails_when_a_consumed_artifact_is_deleted(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "safe"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "future-or-stale.json",
                run_dir=run_dir,
                run_id="eval-missing",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
            )
            (run_dir / "evidence" / "gate.json").unlink()
            with self.assertRaises(ValueError):
                evaluate_run(ROOT, run_dir=run_dir)

    def test_fixture_invariants_use_actual_artifacts_without_fixed_actions(self):
        expected_checks = {
            "normal-research.json": "normal_full_chain",
            "insufficient-evidence.json": "insufficient_evidence_full_chain",
            "future-or-stale.json": "future_stale_exact_filtering",
            "evidence-conflict.json": "conflict_preserved_and_consumed",
            "risk-veto.json": "deterministic_actual_risk_replay",
        }
        with tempfile.TemporaryDirectory() as directory:
            for fixture, expected_check in expected_checks.items():
                run_dir = self._complete_scenario(directory, fixture)
                result = evaluate_run(
                    ROOT,
                    run_dir=run_dir,
                    allow_test_artifacts=fixture != "future-or-stale.json",
                )
                self.assertEqual(result["checks"][expected_check], "PASSED")
                validate_native_eval_result(result)

    def test_risk_eval_rejects_persisted_result_that_does_not_match_reexecution(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self._complete_scenario(directory, "risk-veto.json")
            trace_path = run_dir / "decision_trace.json"
            trace = read_json(trace_path)
            trace["risk_lineage"][-1]["result"]["final_action"] = "HOLD"
            write_json(trace_path, trace)
            with self.assertRaisesRegex(
                (NativeEvalError, ValueError),
                "TRACE|RISK|risk",
            ):
                evaluate_run(ROOT, run_dir=run_dir, allow_test_artifacts=True)

    def test_conflict_fixture_fails_when_cio_does_not_explicitly_consume_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self._complete_scenario(
                directory, "evidence-conflict.json", include_conflict=False
            )
            with self.assertRaisesRegex(NativeEvalError, "CONFLICT_CONSUMPTION"):
                evaluate_run(ROOT, run_dir=run_dir, allow_test_artifacts=True)

    def test_eval_contract_rejects_market_performance_overclaim(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = self._complete_scenario(directory, "normal-research.json")
            result = evaluate_run(ROOT, run_dir=run_dir, allow_test_artifacts=True)
            result["scope"] = "验证 Alpha 提升。"
            result["eval_hash"] = canonical_hash(
                {key: value for key, value in result.items() if key != "eval_hash"}
            )
            with self.assertRaisesRegex(NativeEvalError, "SCOPE_OVERCLAIM"):
                validate_native_eval_result(result)


if __name__ == "__main__":
    unittest.main()
