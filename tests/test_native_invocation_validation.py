from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from product.runtime.evidence_gate import load_fixture, run_evidence_gate
from product.runtime.invocation import (
    OUTPUT_SCHEMAS,
    build_specialist_inputs,
    build_specialist_output_schema,
    build_specialist_task_prompt,
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


def write_specialist_schema(directory: Path, agent: str, allowed_ids) -> Path:
    path = directory / Path(OUTPUT_SCHEMAS[agent]).name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            build_specialist_output_schema(
                ROOT,
                agent_name=agent,
                allowed_evidence_ids=allowed_ids,
            ),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


class InvocationManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.schema_dir = Path(self.temp_dir.name) / "schemas"
        self.fixture = load_fixture(FIXTURE)
        gate = run_evidence_gate(self.fixture, run_id="run-invocation")
        self.inputs = build_specialist_inputs(
            run_id="run-invocation",
            fixture=self.fixture,
            allowed_evidence_ids=gate.allowed_ids,
            research_question="分析公司基本面并寻找反证。",
        )
        self.schema_paths = {
            agent: write_specialist_schema(
                self.schema_dir,
                agent,
                self.inputs[agent]["allowed_evidence_ids"],
            )
            for agent in ("runtime_company_analyst", "runtime_skeptic")
        }

    def tearDown(self):
        self.temp_dir.cleanup()

    def _manifest(self, agent: str):
        return create_invocation_manifest(
            ROOT,
            run_id="run-invocation",
            agent_name=agent,
            agent_input=self.inputs[agent],
            task_prompt="只返回指定 Schema JSON。",
            model="gpt-5.6-terra",
            evidence_ids=self.inputs[agent]["allowed_evidence_ids"],
            output_schema_path=self.schema_paths[agent],
        )

    def test_manifests_lock_agent_skill_prompt_model_tools_input_and_schema(self):
        analyst = self._manifest("runtime_company_analyst")
        skeptic = self._manifest("runtime_skeptic")
        for manifest, agent in (
            (analyst, "runtime_company_analyst"),
            (skeptic, "runtime_skeptic"),
        ):
            self.assertEqual(manifest["agent"]["name"], agent)
            expected_version = (
                "2.1.0" if agent == "runtime_company_analyst" else "2.0.0"
            )
            self.assertEqual(manifest["agent"]["version"], expected_version)
            self.assertEqual(
                manifest["decision_contract"]["version"],
                "council-decision-contract/1.0.0",
            )
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

    def test_run_scoped_schema_and_prompt_bind_raw_gate_evidence_ids(self):
        allowed = self.inputs["runtime_company_analyst"]["allowed_evidence_ids"]
        schema = json.loads(
            self.schema_paths["runtime_company_analyst"].read_text(encoding="utf-8")
        )
        self.assertEqual(
            schema["$defs"]["claim"]["properties"]["evidence_refs"]["items"][
                "enum"
            ],
            allowed,
        )
        self.assertEqual(
            schema["properties"]["counter_evidence_refs"]["items"]["enum"],
            allowed,
        )
        prompt = build_specialist_task_prompt(
            agent_name="runtime_company_analyst",
            allowed_evidence_ids=allowed,
        )
        for expected in (
            "allowed_evidence_ids",
            "原始 evidence_id",
            "禁止在 evidence_id 后拼接 source_id、as_of、retrieved_at",
            "不得污染 evidence_refs",
            "不得自行截断",
        ):
            self.assertIn(expected, prompt)


class StructuredArtifactValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        schema_dir = Path(self.temp_dir.name) / "schemas"
        fixture = load_fixture(FIXTURE)
        gate = run_evidence_gate(fixture, run_id="run-validation")
        inputs = build_specialist_inputs(
            run_id="run-validation",
            fixture=fixture,
            allowed_evidence_ids=gate.allowed_ids,
            research_question="研究公司并独立反证。",
        )
        schema_paths = {
            agent: write_specialist_schema(schema_dir, agent, gate.allowed_ids)
            for agent in ("runtime_company_analyst", "runtime_skeptic")
        }
        self.analyst_manifest = create_invocation_manifest(
            ROOT,
            run_id="run-validation",
            agent_name="runtime_company_analyst",
            agent_input=inputs["runtime_company_analyst"],
            task_prompt="只返回 JSON。",
            model="gpt-5.6-terra",
            evidence_ids=gate.allowed_ids,
            output_schema_path=schema_paths["runtime_company_analyst"],
        )
        self.skeptic_manifest = create_invocation_manifest(
            ROOT,
            run_id="run-validation",
            agent_name="runtime_skeptic",
            agent_input=inputs["runtime_skeptic"],
            task_prompt="只返回 JSON。",
            model="gpt-5.6-terra",
            evidence_ids=gate.allowed_ids,
            output_schema_path=schema_paths["runtime_skeptic"],
        )

    def tearDown(self):
        self.temp_dir.cleanup()

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

    def test_specialist_evidence_id_contract_matrix(self):
        correct = self.valid_company()
        correct["counter_evidence_refs"] = []
        validate_company_report(
            correct, run_id="run-validation", manifest=self.analyst_manifest
        )

        multiple = self.valid_company()
        multiple["claims"][0]["evidence_refs"] = [
            "ev-normal-revenue",
            "ev-normal-debt",
        ]
        multiple["counter_evidence_refs"] = []
        validate_company_report(
            multiple, run_id="run-validation", manifest=self.analyst_manifest
        )

        invalid_refs = (
            "ev-normal-revenue|fixture-filing",
            "ev-normal-revenue|as_of=2025-12-31T00:00:00Z",
            "ev-does-not-exist",
        )
        for invalid_ref in invalid_refs:
            with self.subTest(invalid_ref=invalid_ref):
                report = self.valid_company()
                report["claims"][0]["evidence_refs"] = [invalid_ref]
                with self.assertRaisesRegex(
                    ArtifactValidationError, "EVIDENCE_CLOSURE_FAILED"
                ):
                    validate_company_report(
                        report,
                        run_id="run-validation",
                        manifest=self.analyst_manifest,
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
