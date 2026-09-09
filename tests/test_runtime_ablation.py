from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from evals.ablation.runtime import (
    RuntimeAblationError,
    compare_runtime_ablation_set,
    compare_runtime_variants,
    verify_runtime_ablation_result,
)
from product.runtime.hashing import canonical_hash
from product.runtime.release_gate import check_run
from product.runtime.run_package import finalize_cio, prepare_cio, prepare_run
from product.runtime.runtime_eval import finalize_eval_job, prepare_eval_job
from tests.test_native_run_package import FIXTURES, ROOT, read_json, specialist_outputs, write_json
from tests.test_runtime_eval_job import semantic_result


def analyst_output(run_dir: Path) -> None:
    manifest = read_json(run_dir / "invocations" / "runtime_company_analyst.json")
    write_json(
        run_dir / "agents" / "runtime_company_analyst.json",
        {
            "schema_version": "agent-research-report/2.0.0",
            "run_id": manifest["run_id"],
            "invocation_id": manifest["invocation_id"],
            "status": "COMPLETE",
            "agent": "runtime_company_analyst",
            "scope": "Ablation fixture research",
            "claims": [{"claim_id": "c1", "statement": "Fixture price is available.", "kind": "FACT", "evidence_refs": [manifest["evidence_ids"][0]], "assumption_ids": []}],
            "assumptions": [],
            "counter_evidence_refs": [],
            "uncertainties": [],
            "data_gaps": [],
            "invalidation_conditions": ["Evidence changes."],
            "confidence": 0.5,
            "confidence_rationale": "Bounded fixture evidence.",
            "skill_execution": manifest["skill_execution"],
            "artifact_refs": [],
        },
    )


def generic_specialist_outputs(run_dir: Path) -> None:
    analyst_output(run_dir)
    manifest = read_json(run_dir / "invocations" / "runtime_skeptic.json")
    evidence_id = manifest["evidence_ids"][-1]
    write_json(
        run_dir / "agents" / "runtime_skeptic.json",
        {
            "schema_version": "counter-thesis-report/2.0.0",
            "run_id": manifest["run_id"],
            "invocation_id": manifest["invocation_id"],
            "status": "COMPLETE",
            "agent": "runtime_skeptic",
            "mode": "INDEPENDENT_FIRST_PASS",
            "scope": "Ablation fixture challenge",
            "challenges": [{"challenge_id": "s1", "statement": "Fixture uncertainty remains.", "evidence_refs": [evidence_id], "assumption_ids": [], "resolution_evidence_needed": ["Additional evidence"]}],
            "evidence_refs": [evidence_id],
            "counter_evidence_refs": [],
            "uncertainties": ["Fixture-only evidence."],
            "data_gaps": [],
            "invalidation_conditions": ["Evidence changes."],
            "confidence": 0.4,
            "confidence_rationale": "Bounded fixture evidence.",
            "skill_execution": manifest["skill_execution"],
            "artifact_refs": [],
        },
    )


def ablation_cio_output(run_dir: Path) -> dict:
    manifest = read_json(run_dir / "invocations" / "runtime_cio.json")
    cio_input = read_json(run_dir / "inputs" / "runtime_cio.json")
    refs = manifest["evidence_ids"]
    return {
        "schema_version": "cio-decision-draft/2.1.0",
        "run_id": manifest["run_id"],
        "invocation_id": manifest["invocation_id"],
        "status": "COMPLETE",
        "agent": "runtime_cio",
        "consumed_reports": [
            {"agent": name, "output_hash": digest}
            for name, digest in cio_input["validated_report_hashes"].items()
        ],
        "action": "HOLD",
        "security_id": "SEC-AAA",
        "current_weight": 0.5,
        "target_weight_range": [0.5, 0.5],
        "maximum_notional": None,
        "time_horizon": "fixture horizon",
        "thesis": "The Gate-scoped fixture supports monitoring.",
        "counter_thesis": "The evidence remains limited.",
        "consensus": [],
        "conflicts": [],
        "unresolved_questions": ["More evidence is needed."],
        "invalidation_conditions": ["Evidence changes."],
        "confidence": 0.5,
        "confidence_rationale": "Ablation fixture only.",
        "evidence_refs": refs[:1],
        "no_trade_reason": None,
        "no_trade_explanation": None,
        "reevaluation_conditions": [],
        "skill_execution": manifest["skill_execution"],
        "advisory_only": True,
    }


def build_variant(
    root: Path,
    profile: str,
    *,
    fixture: str = "normal-research.json",
    case_id: str = "normal-research",
    repository_root: Path = ROOT,
) -> dict:
    run_dir = root / profile
    result = prepare_run(
        repository_root,
        fixture_path=repository_root / "evals" / "fixtures" / "codex-native" / fixture,
        run_dir=run_dir,
        run_id=f"ablation-{root.parent.name}-{root.name}-{profile}",
        model="gpt-5.6-terra",
        research_question="Ablation fixture。",
        authenticity_required=False,
        run_mode="EVAL_ABLATION",
        ablation_profile=profile,
    )
    if profile == "analyst-cio":
        analyst_output(run_dir)
        prepare_cio(repository_root, run_dir=run_dir, model="gpt-5.6-terra")
    elif profile == "full-council":
        if fixture == "normal-research.json":
            specialist_outputs(run_dir)
        else:
            generic_specialist_outputs(run_dir)
        prepare_cio(repository_root, run_dir=run_dir, model="gpt-5.6-terra")
    else:
        assert result["next_state"] == "CIO_SYNTHESIS_REQUIRED"
    if fixture == "risk-veto.json":
        from tests.test_native_eval import scenario_cio_output

        cio_draft = scenario_cio_output(run_dir)
        cio_draft.update(
            action="BUY",
            target_weight_range=[0.94, 0.98],
            maximum_notional=8000,
            no_trade_reason=None,
            no_trade_explanation=None,
            reevaluation_conditions=[],
        )
    else:
        cio_draft = ablation_cio_output(run_dir)
    write_json(run_dir / "cio" / "runtime_cio.json", cio_draft)
    finalized = finalize_cio(repository_root, run_dir=run_dir)
    assert finalized["next_state"] in {"COMPLETED", "SAFE_NO_TRADE"}, finalized
    eval_dir = root / f"eval-{profile}"
    prepare_eval_job(repository_root, run_dir=run_dir, eval_dir=eval_dir, eval_id=f"eval-{profile}")
    grader = root / f"grader-{profile}.json"
    semantic = semantic_result(eval_dir)
    semantic["grader"]["model"] = "gpt-5.6-terra"
    semantic.pop("output_hash")
    semantic["output_hash"] = canonical_hash(semantic)
    write_json(grader, semantic)
    evaluation = finalize_eval_job(repository_root, eval_dir=eval_dir, semantic_result_path=grader)
    return {
        "run_dir": str(run_dir),
        "eval_result": str(eval_dir / "eval" / "result.json"),
        "case_id": case_id,
        "model": "gpt-5.6-terra",
        "input_tokens": 100,
        "output_tokens": 50,
        "latency_ms": 1000,
        "eval_hash": evaluation["eval_hash"],
    }


class RuntimeAblationTests(unittest.TestCase):
    def test_three_isolated_real_artifact_profiles_report_honest_no_gain(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            variants = {profile: build_variant(root, profile) for profile in ("cio-only", "analyst-cio", "full-council")}
            result = compare_runtime_variants(
                ROOT,
                ablation_id="ablation-1",
                variants=variants,
                output_dir=root / "comparison",
            )
            self.assertEqual(result["comparability"]["status"], "PASS")
            self.assertEqual(result["conclusion"], "NO_MEASURABLE_GAIN")
            self.assertEqual([case["case_id"] for case in result["cases"]], ["normal-research"])
            self.assertIn("NO_MEASURABLE_GAIN", result["reason_codes"])
            for record in result["profiles"]:
                self.assertTrue(record["run_id"])
                self.assertTrue(record["trace_hash"])
                self.assertTrue(record["eval_hash"])
                report = (root / "comparison" / "report.md").read_text(encoding="utf-8")
                self.assertIn(record["run_id"], report)
                self.assertIn(record["trace_hash"], report)

    def test_four_case_set_reports_per_case_and_aggregate_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_ids = [
                "normal-research",
                "insufficient-evidence",
                "analyst-skeptic-strong-conflict",
                "mandatory-no-trade",
            ]
            cases = {
                case_id: {
                    profile: build_variant(root / case_id, profile, case_id=case_id)
                    for profile in ("cio-only", "analyst-cio", "full-council")
                }
                for case_id in case_ids
            }
            result = compare_runtime_ablation_set(
                ROOT,
                ablation_id="ablation-four-case",
                cases=cases,
                output_dir=root / "comparison",
            )
            self.assertEqual(result["comparability"]["status"], "PASS")
            self.assertEqual([case["case_id"] for case in result["cases"]], case_ids)
            self.assertEqual(len(result["profiles"]), 3)
            self.assertEqual(len(result["profiles"][0]["run_ids"]), 4)
            report = (root / "comparison" / "report.md").read_text(encoding="utf-8")
            self.assertIn("## 逐案例", report)
            self.assertIn("## 聚合 Profile", report)
            self.assertEqual(
                verify_runtime_ablation_result(ROOT, root / "comparison" / "result.json"),
                result,
            )

    def test_mutated_eval_summary_is_rejected_instead_of_becoming_not_comparable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            case_ids = [
                "normal-research",
                "insufficient-evidence",
                "analyst-skeptic-strong-conflict",
                "mandatory-no-trade",
            ]
            cases = {
                case_id: {
                    profile: build_variant(root / case_id, profile, case_id=case_id)
                    for profile in ("cio-only", "analyst-cio", "full-council")
                }
                for case_id in case_ids
            }
            missing_eval = Path(cases["insufficient-evidence"]["full-council"]["eval_result"])
            value = read_json(missing_eval)
            for dimension in value["semantic_rubric"].values():
                dimension.update(status="NOT_APPLICABLE", grade=None)
            value.pop("eval_hash")
            value["eval_hash"] = canonical_hash(value)
            write_json(missing_eval, value)
            with self.assertRaisesRegex(
                RuntimeAblationError,
                "ABLATION_EVAL_VERIFICATION_FAILED",
            ):
                compare_runtime_ablation_set(
                    ROOT,
                    ablation_id="ablation-incomplete-quality",
                    cases=cases,
                    output_dir=root / "comparison",
                )

    def test_static_scores_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            variants = {profile: {"score": 1.0} for profile in ("cio-only", "analyst-cio", "full-council")}
            with self.assertRaisesRegex(RuntimeAblationError, "STATIC_VARIANT_SCORE_FORBIDDEN"):
                compare_runtime_variants(
                    ROOT,
                    ablation_id="static",
                    variants=variants,
                    output_dir=Path(directory) / "out",
                )

    def test_different_frozen_evidence_is_not_comparable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            variants = {
                "cio-only": build_variant(root, "cio-only"),
                "analyst-cio": build_variant(root, "analyst-cio"),
                "full-council": build_variant(root, "full-council", fixture="evidence-conflict.json"),
            }
            result = compare_runtime_variants(
                ROOT,
                ablation_id="different-evidence",
                variants=variants,
                output_dir=root / "comparison",
            )
            self.assertEqual(result["comparability"]["status"], "FAIL")
            self.assertEqual(result["conclusion"], "NOT_COMPARABLE")

    def test_different_version_lock_is_not_comparable(self):
        records = []
        for profile in ("cio-only", "analyst-cio", "full-council"):
            records.append(
                {
                    "profile": profile,
                    "run_id": f"run-{profile}",
                    "run_dir": f"/tmp/{profile}",
                    "trace_hash": "a" * 64,
                    "eval_hash": "b" * 64,
                    "eval_artifact_hash": "c" * 64,
                    "comparison_lock": {
                        "portfolio_hash": "d" * 64,
                        "gate_context_hash": "e" * 64,
                        "version_lock_hash": ("f" if profile != "full-council" else "0") * 64,
                        "model": "gpt-5.6-terra",
                        "risk_policy": "fixture-risk/1.0.0",
                        "rubric_hash": "1" * 64,
                        "case_id": "normal-research",
                    },
                    "metrics": {
                        "semantic_quality": 1.0,
                        "evidence_grounding": 3,
                        "counter_evidence": 3,
                        "no_trade_quality": 3,
                        "conflict_handling": 3,
                        "risk_violations": 0,
                        "schema_failures": 0,
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "latency_ms": 1,
                        "telemetry_status": "AVAILABLE",
                    },
                }
            )
        with tempfile.TemporaryDirectory() as directory, patch(
            "evals.ablation.runtime._variant", side_effect=records
        ):
            variants = {
                profile: {"run_dir": f"/tmp/{profile}", "eval_result": f"/tmp/{profile}.json", "case_id": "normal-research"}
                for profile in ("cio-only", "analyst-cio", "full-council")
            }
            result = compare_runtime_variants(
                ROOT,
                ablation_id="different-version",
                variants=variants,
                output_dir=Path(directory) / "comparison",
            )
            self.assertEqual(result["comparability"]["status"], "FAIL")
            self.assertEqual(result["conclusion"], "NOT_COMPARABLE")

    def test_missing_telemetry_is_explicit_and_never_coerced_to_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            variants = {profile: build_variant(root, profile) for profile in ("cio-only", "analyst-cio", "full-council")}
            variants["analyst-cio"].pop("latency_ms")
            result = compare_runtime_variants(
                ROOT,
                ablation_id="missing-telemetry",
                variants=variants,
                output_dir=root / "comparison",
            )
            record = next(item for item in result["profiles"] if item["profile"] == "analyst-cio")
            self.assertEqual(record["metrics"]["telemetry_status"], "MISSING_TELEMETRY")
            self.assertIsNone(record["metrics"]["latency_ms"])

    def test_identical_pre_agent_safe_stops_are_comparable_without_semantic_dimensions(self):
        records = []
        for profile in ("cio-only", "analyst-cio", "full-council"):
            records.append(
                {
                    "profile": profile,
                    "run_id": f"safe-stop-{profile}",
                    "run_dir": f"/tmp/{profile}",
                    "trace_hash": "a" * 64,
                    "eval_hash": "b" * 64,
                    "eval_artifact_hash": "c" * 64,
                    "comparison_lock": {
                        "portfolio_hash": "d" * 64,
                        "gate_context_hash": "e" * 64,
                        "version_lock_hash": "f" * 64,
                        "model": "gpt-5.6-terra",
                        "risk_policy": "fixture-risk/1.0.0",
                        "rubric_hash": "1" * 64,
                        "case_id": "normal-research",
                    },
                    "metrics": {
                        "semantic_quality": None,
                        "evidence_grounding": None,
                        "counter_evidence": None,
                        "no_trade_quality": None,
                        "conflict_handling": None,
                        "risk_violations": 0,
                        "schema_failures": 0,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "latency_ms": 0,
                        "telemetry_status": "AVAILABLE",
                    },
                }
            )
        with tempfile.TemporaryDirectory() as directory, patch(
            "evals.ablation.runtime._variant", side_effect=records
        ):
            variants = {
                profile: {
                    "run_dir": f"/tmp/{profile}",
                    "eval_result": f"/tmp/{profile}.json",
                    "case_id": "normal-research",
                }
                for profile in ("cio-only", "analyst-cio", "full-council")
            }
            result = compare_runtime_variants(
                ROOT,
                ablation_id="safe-stop",
                variants=variants,
                output_dir=Path(directory) / "comparison",
            )
            self.assertEqual(result["comparability"]["status"], "PASS")
            self.assertEqual(result["conclusion"], "NO_MEASURABLE_GAIN")
            self.assertEqual(result["reason_codes"], ["NO_SEMANTIC_DIMENSIONS_APPLICABLE"])

    def test_partial_semantic_dimensions_remain_not_comparable(self):
        records = []
        for index, profile in enumerate(("cio-only", "analyst-cio", "full-council")):
            records.append(
                {
                    "profile": profile,
                    "run_id": f"partial-{profile}",
                    "run_dir": f"/tmp/{profile}",
                    "trace_hash": "a" * 64,
                    "eval_hash": "b" * 64,
                    "eval_artifact_hash": "c" * 64,
                    "comparison_lock": {
                        "portfolio_hash": "d" * 64,
                        "gate_context_hash": "e" * 64,
                        "version_lock_hash": "f" * 64,
                        "model": "gpt-5.6-terra",
                        "risk_policy": "fixture-risk/1.0.0",
                        "rubric_hash": "1" * 64,
                        "case_id": "normal-research",
                    },
                    "metrics": {
                        "semantic_quality": None if index == 0 else 1.0,
                        "evidence_grounding": None if index == 0 else 3,
                        "counter_evidence": None,
                        "no_trade_quality": None,
                        "conflict_handling": None,
                        "risk_violations": 0,
                        "schema_failures": 0,
                        "input_tokens": 0,
                        "output_tokens": 0,
                        "latency_ms": 0,
                        "telemetry_status": "AVAILABLE",
                    },
                }
            )
        with tempfile.TemporaryDirectory() as directory, patch(
            "evals.ablation.runtime._variant", side_effect=records
        ):
            variants = {
                profile: {
                    "run_dir": f"/tmp/{profile}",
                    "eval_result": f"/tmp/{profile}.json",
                    "case_id": "normal-research",
                }
                for profile in ("cio-only", "analyst-cio", "full-council")
            }
            result = compare_runtime_variants(
                ROOT,
                ablation_id="partial-semantic",
                variants=variants,
                output_dir=Path(directory) / "comparison",
            )
            self.assertEqual(result["comparability"]["status"], "PASS")
            self.assertEqual(result["conclusion"], "NOT_COMPARABLE")

    def test_ablation_profile_cannot_pass_product_release_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            entry = build_variant(root, "cio-only")
            result, exit_code = check_run(ROOT, run_dir=Path(entry["run_dir"]))
            self.assertEqual(exit_code, 5)
            self.assertEqual(result["category"], "ABLATION_PROFILE_NOT_PUBLISHABLE")


if __name__ == "__main__":
    unittest.main()
