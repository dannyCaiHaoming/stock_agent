from __future__ import annotations

import copy
import unittest
from pathlib import Path

from product.runtime.evidence_gate import load_fixture, run_evidence_gate
from product.runtime.invocation import (
    build_specialist_inputs,
    create_invocation_manifest,
    validate_skeptic_first_pass_input,
    verify_invocation_manifest,
)
from product.runtime.validation import (
    ArtifactValidationError,
    validate_company_report,
    validate_skeptic_report,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "evals" / "fixtures" / "codex-native" / "normal-research.json"


class InvocationManifestTests(unittest.TestCase):
    def setUp(self):
        self.fixture = load_fixture(FIXTURE)
        gate = run_evidence_gate(self.fixture, run_id="run-invocation")
        self.inputs = build_specialist_inputs(
            run_id="run-invocation",
            fixture=self.fixture,
            allowed_evidence_ids=gate.allowed_ids,
            research_question="分析公司基本面并寻找反证。",
        )

    def _manifest(self, agent: str):
        return create_invocation_manifest(
            ROOT,
            run_id="run-invocation",
            agent_name=agent,
            agent_input=self.inputs[agent],
            task_prompt="只返回指定 Schema JSON。",
            model="gpt-5.6-terra",
            evidence_ids=self.inputs[agent]["allowed_evidence_ids"],
        )

    def test_manifests_lock_agent_skill_prompt_model_tools_input_and_schema(self):
        analyst = self._manifest("runtime_company_analyst")
        skeptic = self._manifest("runtime_skeptic")
        for manifest, agent in (
            (analyst, "runtime_company_analyst"),
            (skeptic, "runtime_skeptic"),
        ):
            self.assertEqual(manifest["agent"]["name"], agent)
            self.assertEqual(manifest["agent"]["version"], "2.0.0")
            self.assertEqual(manifest["model"], "gpt-5.6-terra")
            self.assertTrue(manifest["skills"])
            self.assertTrue(manifest["tool_permissions"])
            for field in (
                "task_prompt_hash",
                "instruction_bundle_hash",
                "input_hash",
                "output_schema_hash",
                "manifest_hash",
            ):
                self.assertEqual(len(manifest[field]), 64)
            verify_invocation_manifest(ROOT, manifest, agent_input=self.inputs[agent])
        self.assertNotEqual(analyst["manifest_hash"], skeptic["manifest_hash"])

    def test_input_or_manifest_tampering_fails(self):
        manifest = self._manifest("runtime_company_analyst")
        altered_input = copy.deepcopy(self.inputs["runtime_company_analyst"])
        altered_input["research_scope"] = "tampered"
        with self.assertRaisesRegex(ValueError, "input hash mismatch"):
            verify_invocation_manifest(ROOT, manifest, agent_input=altered_input)

        altered_manifest = copy.deepcopy(manifest)
        altered_manifest["instruction_bundle_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "manifest hash mismatch"):
            verify_invocation_manifest(
                ROOT,
                altered_manifest,
                agent_input=self.inputs["runtime_company_analyst"],
            )

    def test_skeptic_input_is_independent_and_contains_no_evidence_values(self):
        skeptic = self.inputs["runtime_skeptic"]
        validate_skeptic_first_pass_input(skeptic)
        self.assertNotIn("evidence", skeptic)
        self.assertIn("allowed_evidence_ids", skeptic)
        broken = copy.deepcopy(skeptic)
        broken["analyst_summary"] = "peer conclusion"
        with self.assertRaisesRegex(ValueError, "CONTEXT_ISOLATION_VIOLATION"):
            validate_skeptic_first_pass_input(broken)


class StructuredArtifactValidationTests(unittest.TestCase):
    def setUp(self):
        fixture = load_fixture(FIXTURE)
        gate = run_evidence_gate(fixture, run_id="run-validation")
        inputs = build_specialist_inputs(
            run_id="run-validation",
            fixture=fixture,
            allowed_evidence_ids=gate.allowed_ids,
            research_question="研究公司并独立反证。",
        )
        self.analyst_manifest = create_invocation_manifest(
            ROOT,
            run_id="run-validation",
            agent_name="runtime_company_analyst",
            agent_input=inputs["runtime_company_analyst"],
            task_prompt="只返回 JSON。",
            model="gpt-5.6-terra",
            evidence_ids=gate.allowed_ids,
        )
        self.skeptic_manifest = create_invocation_manifest(
            ROOT,
            run_id="run-validation",
            agent_name="runtime_skeptic",
            agent_input=inputs["runtime_skeptic"],
            task_prompt="只返回 JSON。",
            model="gpt-5.6-terra",
            evidence_ids=gate.allowed_ids,
        )

    def valid_company(self):
        return {
            "schema_version": "agent-research-report/2.0.0",
            "run_id": "run-validation",
            "invocation_id": self.analyst_manifest["invocation_id"],
            "status": "COMPLETE",
            "agent": "runtime_company_analyst",
            "scope": "SEC-AAA company research",
            "claims": [{
                "claim_id": "claim-1",
                "statement": "Reported revenue is one million USD.",
                "kind": "FACT",
                "evidence_refs": ["ev-normal-revenue"],
                "assumption_ids": [],
            }],
            "assumptions": [],
            "counter_evidence_refs": ["ev-normal-debt"],
            "uncertainties": ["Only fixture evidence is available."],
            "data_gaps": [],
            "invalidation_conditions": ["A later filing revises revenue."],
            "confidence": 0.6,
            "confidence_rationale": "The cited fixture facts are internally traceable.",
            "skill_execution": self.analyst_manifest["skill_execution"],
            "artifact_refs": [],
        }

    def valid_skeptic(self):
        return {
            "schema_version": "counter-thesis-report/2.0.0",
            "run_id": "run-validation",
            "invocation_id": self.skeptic_manifest["invocation_id"],
            "status": "COMPLETE",
            "agent": "runtime_skeptic",
            "mode": "INDEPENDENT_FIRST_PASS",
            "scope": "SEC-AAA independent counter-thesis",
            "challenges": [{
                "challenge_id": "challenge-1",
                "statement": "Debt can constrain optionality.",
                "evidence_refs": ["ev-normal-debt"],
                "assumption_ids": [],
                "resolution_evidence_needed": ["Maturity schedule"],
            }],
            "evidence_refs": ["ev-normal-debt"],
            "counter_evidence_refs": ["ev-normal-margin"],
            "uncertainties": [],
            "data_gaps": ["No debt maturity schedule."],
            "invalidation_conditions": ["Net debt falls materially."],
            "confidence": 0.5,
            "confidence_rationale": "The challenge uses one cited fact and names the gap.",
            "skill_execution": self.skeptic_manifest["skill_execution"],
            "artifact_refs": [],
        }

    def test_valid_specialist_reports_close_all_references(self):
        self.assertEqual(
            validate_company_report(
                self.valid_company(),
                run_id="run-validation",
                manifest=self.analyst_manifest,
            ),
            {"ev-normal-revenue", "ev-normal-debt"},
        )
        self.assertEqual(
            validate_skeptic_report(
                self.valid_skeptic(),
                run_id="run-validation",
                manifest=self.skeptic_manifest,
            ),
            {"ev-normal-debt", "ev-normal-margin"},
        )

    def test_missing_field_unknown_filtered_and_cross_run_references_fail(self):
        missing = self.valid_company()
        del missing["confidence_rationale"]
        with self.assertRaisesRegex(ArtifactValidationError, "missing"):
            validate_company_report(
                missing, run_id="run-validation", manifest=self.analyst_manifest
            )

        dangling = self.valid_company()
        dangling["claims"][0]["evidence_refs"] = ["unknown-evidence"]
        with self.assertRaisesRegex(ArtifactValidationError, "EVIDENCE_CLOSURE_FAILED"):
            validate_company_report(
                dangling, run_id="run-validation", manifest=self.analyst_manifest
            )

        cross_run = self.valid_skeptic()
        cross_run["run_id"] = "another-run"
        with self.assertRaisesRegex(ArtifactValidationError, "CROSS_RUN_OUTPUT"):
            validate_skeptic_report(
                cross_run, run_id="run-validation", manifest=self.skeptic_manifest
            )

    def test_agent_self_report_without_matching_skill_proof_fails(self):
        report = self.valid_company()
        report["skill_execution"] = [{"skill_name": "company-research"}]
        with self.assertRaisesRegex(ArtifactValidationError, "SKILL_EXECUTION_PROOF_MISMATCH"):
            validate_company_report(
                report, run_id="run-validation", manifest=self.analyst_manifest
            )

    def test_legal_timeout_is_domain_state_but_failed_is_system_error(self):
        legal = self.valid_skeptic()
        legal["status"] = "TIMEOUT"
        validate_skeptic_report(
            legal, run_id="run-validation", manifest=self.skeptic_manifest
        )
        illegal = self.valid_skeptic()
        illegal["status"] = "FAILED"
        with self.assertRaisesRegex(ArtifactValidationError, "ILLEGAL_DOMAIN_STATUS"):
            validate_skeptic_report(
                illegal, run_id="run-validation", manifest=self.skeptic_manifest
            )


if __name__ == "__main__":
    unittest.main()
