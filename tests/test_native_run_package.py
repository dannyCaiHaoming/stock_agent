from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from product.runtime.run_package import (
    RunPackageError,
    finalize_cio,
    integrity_snapshot,
    prepare_cio,
    prepare_run,
    verify_integrity,
)
from product.runtime.hashing import canonical_hash
from product.runtime.cli import main as runtime_cli_main
from product.runtime.fixture_mcp import StatelessFixtureTools, ToolAccessError


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals" / "fixtures" / "codex-native"


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def specialist_outputs(run_dir: Path):
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
            "scope": "SEC-AAA company research",
            "claims": [{
                "claim_id": "claim-1",
                "statement": "Revenue is reported in the cited fixture.",
                "kind": "FACT",
                "evidence_refs": ["ev-normal-revenue"],
                "assumption_ids": [],
            }],
            "assumptions": [],
            "counter_evidence_refs": ["ev-normal-debt"],
            "uncertainties": [],
            "data_gaps": [],
            "invalidation_conditions": ["A later filing revises revenue."],
            "confidence": 0.6,
            "confidence_rationale": "References close against the Gate.",
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
            "scope": "SEC-AAA independent challenge",
            "challenges": [{
                "challenge_id": "challenge-1",
                "statement": "Debt may constrain optionality.",
                "evidence_refs": ["ev-normal-debt"],
                "assumption_ids": [],
                "resolution_evidence_needed": ["Debt maturity schedule"],
            }],
            "evidence_refs": ["ev-normal-debt"],
            "counter_evidence_refs": ["ev-normal-margin"],
            "uncertainties": [],
            "data_gaps": ["No maturity schedule."],
            "invalidation_conditions": ["Debt falls materially."],
            "confidence": 0.5,
            "confidence_rationale": "The challenge is cited and bounded.",
            "skill_execution": skeptic["skill_execution"],
            "artifact_refs": [],
        },
    )


def cio_output(run_dir: Path, *, target=(0.5, 0.5)):
    manifest = read_json(run_dir / "invocations" / "runtime_cio.json")
    reports = [
        read_json(run_dir / "agents" / "runtime_company_analyst.json"),
        read_json(run_dir / "agents" / "runtime_skeptic.json"),
    ]
    return {
        "schema_version": "cio-decision-draft/2.1.0",
        "run_id": manifest["run_id"],
        "invocation_id": manifest["invocation_id"],
        "status": "COMPLETE",
        "agent": "runtime_cio",
        "consumed_reports": [
            {"agent": report["agent"], "output_hash": canonical_hash(report)} for report in reports
        ],
        "action": "HOLD",
        "security_id": "SEC-AAA",
        "current_weight": 0.5,
        "target_weight_range": list(target),
        "maximum_notional": None,
        "time_horizon": "fixture evaluation horizon",
        "thesis": "The cited report supports continued monitoring.",
        "counter_thesis": "Debt and missing maturity data limit conviction.",
        "consensus": ["Both reports use the Gate evidence."],
        "conflicts": [],
        "unresolved_questions": ["Debt maturity schedule remains unavailable."],
        "invalidation_conditions": ["A later filing materially revises revenue."],
        "confidence": 0.5,
        "confidence_rationale": "The conclusion preserves the specialist uncertainty.",
        "evidence_refs": ["ev-normal-revenue", "ev-normal-debt"],
        "no_trade_reason": None,
        "no_trade_explanation": None,
        "reevaluation_conditions": [],
        "skill_execution": manifest["skill_execution"],
        "advisory_only": True,
    }


class NativeRunPackageTests(unittest.TestCase):
    def test_prepare_emits_gate_scoped_specialist_schemas_and_prompts(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "gate-scoped-schema-run"
            prepared = prepare_run(
                ROOT,
                fixture_path=FIXTURES / "evidence-conflict.json",
                run_dir=run_dir,
                run_id="gate-scoped-schema-run",
                model="gpt-5.6-terra",
                research_question="研究冲突证据。",
                authenticity_required=False,
            )
            self.assertEqual(prepared["next_state"], "DISPATCH_REQUIRED")
            allowed = read_json(run_dir / "evidence" / "gate.json")[
                "allowed_evidence_ids"
            ]
            analyst_schema = read_json(
                run_dir / "schemas" / "agent-research-report.schema.json"
            )
            skeptic_schema = read_json(
                run_dir / "schemas" / "counter-thesis-report.schema.json"
            )
            enum_paths = (
                analyst_schema["$defs"]["claim"]["properties"]["evidence_refs"][
                    "items"
                ]["enum"],
                analyst_schema["properties"]["counter_evidence_refs"]["items"][
                    "enum"
                ],
                skeptic_schema["properties"]["evidence_refs"]["items"]["enum"],
                skeptic_schema["properties"]["counter_evidence_refs"]["items"][
                    "enum"
                ],
                skeptic_schema["properties"]["challenges"]["items"]["properties"][
                    "evidence_refs"
                ]["items"]["enum"],
            )
            for enum_values in enum_paths:
                self.assertEqual(enum_values, allowed)
            for agent in ("runtime_company_analyst", "runtime_skeptic"):
                agent_input = read_json(run_dir / "inputs" / f"{agent}.json")
                invocation = read_json(run_dir / "invocations" / f"{agent}.json")
                prompt = (run_dir / "prompts" / f"{agent}.txt").read_text(
                    encoding="utf-8"
                )
                self.assertEqual(agent_input["allowed_evidence_ids"], allowed)
                self.assertEqual(
                    Path(invocation["output_schema"]).parent.resolve(),
                    (run_dir / "schemas").resolve(),
                )
                self.assertIn("原始 evidence_id", prompt)
                self.assertIn("禁止在 evidence_id 后拼接 source_id、as_of、retrieved_at", prompt)
                self.assertIn("不得自行截断", prompt)

    def test_integrity_snapshot_detects_protected_file_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            runtime = repo / "product" / "runtime"
            runtime.mkdir(parents=True)
            protected = runtime / "boundary.py"
            protected.write_text("VALUE = 1\n", encoding="utf-8")
            (repo / "product" / "AGENTS.md").write_text("policy\n", encoding="utf-8")
            (repo / "product" / "version-manifest.json").write_text("{}\n", encoding="utf-8")
            snapshot = integrity_snapshot(repo)
            verify_integrity(repo, snapshot)
            protected.write_text("VALUE = 2\n", encoding="utf-8")
            with self.assertRaisesRegex(RunPackageError, "INTEGRITY_CHANGED"):
                verify_integrity(repo, snapshot)

    def test_future_or_stale_fixture_safely_stops_before_agents(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "safe-run"
            result = prepare_run(
                ROOT,
                fixture_path=FIXTURES / "future-or-stale.json",
                run_dir=run_dir,
                run_id="safe-run",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
                authenticity_required=False,
            )
            self.assertEqual(result["next_state"], "SAFE_NO_TRADE")
            self.assertFalse((run_dir / "invocations").exists())
            self.assertTrue((run_dir / "decision.json").is_file())
            self.assertTrue((run_dir / "report.md").is_file())
            trace = read_json(run_dir / "decision_trace.json")
            self.assertEqual(trace["terminal_state"], "SAFE_NO_TRADE")
            self.assertEqual(trace["events"][-1]["agent_calls"], 0)

    def test_invalid_portfolio_safely_stops_before_agents(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "invalid-input-run"
            result = prepare_run(
                ROOT,
                fixture_path=FIXTURES / "invalid-portfolio.json",
                run_dir=run_dir,
                run_id="invalid-input-run",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
                authenticity_required=False,
            )
            self.assertEqual(result["next_state"], "SAFE_NO_TRADE")
            decision = read_json(run_dir / "decision.json")
            self.assertEqual(decision["decisions"][0]["no_trade_reason"], "INPUT_INVALID")
            self.assertFalse((run_dir / "invocations").exists())

    def test_valid_fake_artifacts_exercise_complete_deterministic_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "complete-run"
            prepared = prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=run_dir,
                run_id="complete-run",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
                authenticity_required=False,
            )
            self.assertEqual(prepared["next_state"], "DISPATCH_REQUIRED")
            specialist_outputs(run_dir)
            self.assertEqual(
                prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")["next_state"],
                "CIO_SYNTHESIS_REQUIRED",
            )
            write_json(run_dir / "cio" / "runtime_cio.json", cio_output(run_dir))
            result = finalize_cio(ROOT, run_dir=run_dir)
            self.assertEqual(result["next_state"], "COMPLETED")
            decision = read_json(run_dir / "decision.json")
            self.assertEqual(decision["risk_report"]["status"], "APPROVED")
            self.assertEqual(decision["decisions"][0]["action"], "HOLD")
            report = (run_dir / "report.md").read_text()
            for expected in (
                "`HOLD`",
                "The cited report supports continued monitoring.",
                "ev-normal-revenue",
                "A later filing materially revises revenue.",
                "Risk 状态: `APPROVED`",
                "仅供建议: `true`",
            ):
                self.assertIn(expected, report)

    def test_cio_receives_only_validated_reports_references_and_gate_scoped_query(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "cio-boundary"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=run_dir,
                run_id="cio-boundary",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
                authenticity_required=False,
            )
            specialist_outputs(run_dir)
            result = prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")
            self.assertEqual(result["next_state"], "CIO_SYNTHESIS_REQUIRED")

            cio_input = read_json(run_dir / "inputs" / "runtime_cio.json")
            self.assertEqual(
                set(cio_input["validated_reports"]),
                {"runtime_company_analyst", "runtime_skeptic"},
            )
            self.assertEqual(
                cio_input["validated_report_hashes"],
                {
                    agent_name: canonical_hash(report)
                    for agent_name, report in cio_input["validated_reports"].items()
                },
            )
            serialized = json.dumps(cio_input, sort_keys=True)
            for forbidden in (
                "fixture_snapshot",
                "excluded_evidence_ids",
                "retrieved_at",
                "source_id",
                "hidden_reasoning",
                "chain_of_thought",
            ):
                self.assertNotIn(forbidden, serialized)

            invocation = read_json(run_dir / "invocations" / "runtime_cio.json")
            self.assertEqual(invocation["tool_permissions"], ["fixture_evidence.query"])
            tools = StatelessFixtureTools()
            evidence_id = cio_input["evidence_references"][0]
            queried = tools.query(
                run_dir=str(run_dir),
                run_id="cio-boundary",
                agent="runtime_cio",
                invocation_id=invocation["invocation_id"],
                evidence_ids=[evidence_id],
            )
            self.assertEqual(queried["evidence"][0]["evidence_id"], evidence_id)
            self.assertEqual(tools.events[-1]["agent"], "runtime_cio")
            with self.assertRaisesRegex(ToolAccessError, "TOOL_NOT_AUTHORIZED"):
                tools.calculate(
                    run_dir=str(run_dir),
                    run_id="cio-boundary",
                    agent="runtime_cio",
                    invocation_id=invocation["invocation_id"],
                    calculation_id="calc-cio-forbidden",
                    operation="ratio",
                    evidence_ids=["ev-normal-debt", "ev-normal-revenue"],
                )

    def test_production_finalization_fails_closed_without_native_execution_proof(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "authenticity-required"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=run_dir,
                run_id="authenticity-required",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
            )
            specialist_outputs(run_dir)
            prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")
            write_json(run_dir / "cio" / "runtime_cio.json", cio_output(run_dir))
            result = finalize_cio(ROOT, run_dir=run_dir)
            self.assertEqual(result["terminal_state"], "FAILED_VALIDATION")
            self.assertIn(
                "specialist-execution-proof.json",
                read_json(run_dir / "run_error.json")["message"],
            )
            self.assertFalse((run_dir / "decision.json").exists())
            self.assertFalse((run_dir / "report.md").exists())

    def test_execution_proof_cli_persists_failed_validation_and_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = root / "proof-failure"
            sessions = root / "sessions"
            sessions.mkdir()
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=run_dir,
                run_id="proof-failure",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
            )
            specialist_outputs(run_dir)
            prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")
            exit_code = runtime_cli_main(
                [
                    "execution-proof",
                    "--repo",
                    str(ROOT),
                    "--run-dir",
                    str(run_dir),
                    "--sessions-root",
                    str(sessions),
                ]
            )
            self.assertEqual(exit_code, 2)
            error = read_json(run_dir / "run_error.json")
            self.assertEqual(error["code"], "NATIVE_EXECUTION_PROOF_FAILED")
            self.assertFalse((run_dir / "decision.json").exists())

    def test_dangling_specialist_reference_becomes_failed_validation_without_advice(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "failed-run"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=run_dir,
                run_id="failed-run",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
                authenticity_required=False,
            )
            specialist_outputs(run_dir)
            report_path = run_dir / "agents" / "runtime_company_analyst.json"
            report = read_json(report_path)
            report["claims"][0]["evidence_refs"] = ["dangling"]
            report_path.write_text(json.dumps(report), encoding="utf-8")
            result = prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")
            self.assertEqual(result["terminal_state"], "FAILED_VALIDATION")
            self.assertTrue((run_dir / "run_error.json").is_file())
            self.assertFalse((run_dir / "decision.json").exists())
            self.assertFalse((run_dir / "report.md").exists())

    def test_specialist_format_repair_is_one_shot_and_preserves_fact_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "format-repair-run"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=run_dir,
                run_id="format-repair-run",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
                authenticity_required=False,
            )
            specialist_outputs(run_dir)
            report_path = run_dir / "agents" / "runtime_company_analyst.json"
            original = read_json(report_path)
            original["format_noise"] = "remove me"
            write_json(report_path, original)

            requested = prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")
            self.assertEqual(
                requested["next_state"], "ONE_SPECIALIST_FORMAT_REPAIR_REQUIRED"
            )
            repaired = dict(original)
            repaired.pop("format_noise")
            write_json(Path(requested["repaired_output"]), repaired)

            accepted = prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")
            self.assertEqual(accepted["next_state"], "CIO_SYNTHESIS_REQUIRED")
            self.assertEqual(read_json(report_path), repaired)
            self.assertTrue(
                (run_dir / "repairs" / "runtime_company_analyst-attempt-1.json").is_file()
            )
            trace = read_json(run_dir / "decision_trace.json")
            stages = [event["stage"] for event in trace["events"]]
            self.assertIn("SPECIALIST_FORMAT_REPAIR_REQUIRED", stages)
            self.assertIn("SPECIALIST_FORMAT_REPAIR_ACCEPTED", stages)

    def test_second_invalid_specialist_format_attempt_fails_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "format-repair-failure"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=run_dir,
                run_id="format-repair-failure",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
                authenticity_required=False,
            )
            specialist_outputs(run_dir)
            report_path = run_dir / "agents" / "runtime_company_analyst.json"
            original = read_json(report_path)
            original["format_noise"] = "still invalid"
            write_json(report_path, original)
            requested = prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")

            repaired = dict(original)
            repaired["claims"] = [dict(original["claims"][0])]
            repaired["claims"][0]["statement"] = "A newly invented factual claim."
            write_json(Path(requested["repaired_output"]), repaired)
            result = prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")

            self.assertEqual(result["terminal_state"], "FAILED_VALIDATION")
            self.assertIn(
                "FORMAT_REPAIR_ADDED_FACT_CONTENT",
                read_json(run_dir / "run_error.json")["message"],
            )
            self.assertFalse((run_dir / "decision.json").exists())
            self.assertFalse((run_dir / "report.md").exists())

    def test_risk_allows_at_most_one_cio_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "revision-run"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=run_dir,
                run_id="revision-run",
                model="gpt-5.6-terra",
                research_question="研究 fixture。",
                authenticity_required=False,
            )
            specialist_outputs(run_dir)
            prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")
            write_json(
                run_dir / "cio" / "runtime_cio.json",
                cio_output(run_dir, target=(0.55, 0.8)),
            )
            first = finalize_cio(ROOT, run_dir=run_dir)
            self.assertEqual(first["next_state"], "ONE_CIO_REVISION_REQUIRED")
            revised = cio_output(run_dir, target=(0.55, 0.6))
            write_json(run_dir / "cio" / "runtime_cio_revision.json", revised)
            second = finalize_cio(ROOT, run_dir=run_dir, revision=True)
            self.assertEqual(second["next_state"], "COMPLETED")
            trace = read_json(run_dir / "decision_trace.json")
            self.assertEqual(len(trace["risk_lineage"]), 2)


if __name__ == "__main__":
    unittest.main()
