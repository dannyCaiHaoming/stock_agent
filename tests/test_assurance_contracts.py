from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from product.runtime.architecture_guard import inspect_product_python
from product.runtime.model_routing import load_model_routing, select_model
from product.runtime.schema_validation import SchemaValidationError, validate_schema_instance


ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "product" / "schemas" / "runtime"
SHA = "a" * 64


def load_schema(name: str) -> dict:
    return json.loads((SCHEMAS / name).read_text(encoding="utf-8"))


def valid_examples() -> dict[str, dict]:
    return {
        "replay-capsule.schema.json": {
            "schema_version": "replay-capsule/1.0.0",
            "run_id": "run-1",
            "created_at": "2026-09-07T00:00:00Z",
            "locked_context": {
                "candidate_version": "candidate",
                "model": "gpt-5.6-terra",
                "codex_runtime": "codex-cli/0.153.4",
                "python_runtime": "python/3.13.0",
                "runtime_profile": "fixture-council/3.0.0",
                "run_mode": "PRODUCT_COUNCIL",
                "ablation_profile": None,
                "trigger_reason": "runtime_acceptance",
                "research_question": "fixture question",
                "decision_cutoff": "2026-01-01T00:00:00Z",
                "fixture_hash": SHA,
                "gate_hash": SHA,
                "version_manifest_hash": SHA,
                "product_integrity_hash": SHA,
            },
            "objects": [{
                "logical_path": "product/AGENTS.md",
                "sha256": SHA,
                "bytes": 1,
                "media_type": "text/markdown",
                "role": "runtime-policy",
                "executable": False,
            }],
            "root_hash": SHA,
            "manifest_hash": SHA,
        },
        "execution-replay.schema.json": {
            "schema_version": "execution-replay/1.0.0",
            "source_run_id": "source",
            "new_run_id": "new",
            "source_capsule_hash": SHA,
            "workspace": "/tmp/workspace",
            "locked_inputs": {},
            "locked_input_hash": SHA,
            "source_manifest_hash": SHA,
            "new_manifest_hash": SHA,
            "llm_output_equality_required": False,
            "contract_and_semantic_eval_required": True,
            "status": "PREPARED",
        },
        "runtime-eval-job.schema.json": {
            "schema_version": "runtime-eval-job/1.0.0",
            "eval_id": "eval-1",
            "run_id": "run-1",
            "terminal_state": "COMPLETED",
            "status": "PASS",
            "hard_gates": {},
            "semantic_rubric": {},
            "grader": {},
            "source_hashes": {},
            "reason_codes": [],
            "eval_hash": SHA,
        },
        "semantic-rubric-result.schema.json": {
            "schema_version": "semantic-rubric-result/1.0.0",
            "eval_id": "eval-1",
            "grader": {
                "agent": "dev_eval",
                "model": "gpt-5.6-terra",
                "prompt_hash": SHA,
                "rubric_hash": SHA,
                "input_hash": SHA,
            },
            "dimensions": {
                name: {
                    "status": "PASS",
                    "grade": 2,
                    "evidence_refs": ["ev-1"],
                    "rationale": "评分理由。",
                }
                for name in (
                    "no_trade_reasoning",
                    "analyst_thesis_grounding",
                    "skeptic_counter_evidence",
                    "cio_conflict_handling",
                    "confidence_calibration",
                )
            },
            "output_hash": SHA,
        },
        "regression-suite.schema.json": {
            "schema_version": "regression-suite/1.0.0",
            "suite_id": "suite-1",
            "candidate_hash": SHA,
            "set_hash": SHA,
            "case_results": [{}],
            "status": "PASS",
            "reason_codes": [],
            "suite_hash": SHA,
        },
        "ablation-report.schema.json": {
            "schema_version": "ablation-report/1.0.0",
            "ablation_id": "ablation-1",
            "cases": [{"case_id": "normal-research", "profiles": [{}, {}, {}]}],
            "profiles": [{}, {}, {}],
            "comparability": {},
            "metrics": {},
            "configuration": {},
            "conclusion": "NO_MEASURABLE_GAIN",
            "reason_codes": [],
            "report_hash": SHA,
        },
        "promotion-gate.schema.json": {
            "schema_version": "promotion-gate/1.0.0",
            "gate_id": "gate-1",
            "candidate_version": "candidate",
            "baseline_version": "baseline",
            "status": "PASS",
            "hard_gates": {},
            "soft_metrics": {},
            "reason_codes": [],
            "prior_result": None,
            "input_hashes": {},
            "result_hash": SHA,
        },
    }


class AssuranceSchemaTests(unittest.TestCase):
    def test_all_assurance_schemas_are_strict_and_accept_valid_examples(self):
        for name, example in valid_examples().items():
            schema = load_schema(name)
            self.assertFalse(schema["additionalProperties"], name)
            validate_schema_instance(example, schema)

    def test_missing_unknown_and_wrong_type_fail_closed(self):
        for name, example in valid_examples().items():
            schema = load_schema(name)
            missing = dict(example)
            missing.pop(next(iter(schema["required"])))
            with self.assertRaises(SchemaValidationError, msg=name):
                validate_schema_instance(missing, schema)
            unknown = dict(example)
            unknown["unexpected"] = True
            with self.assertRaises(SchemaValidationError, msg=name):
                validate_schema_instance(unknown, schema)
            wrong = dict(example)
            wrong[next(iter(schema["required"]))] = 7
            with self.assertRaises(SchemaValidationError, msg=name):
                validate_schema_instance(wrong, schema)

    def test_semantic_dimension_contract_rejects_legacy_fields_and_out_of_range_grade(self):
        schema = load_schema("semantic-rubric-result.schema.json")
        legacy = valid_examples()["semantic-rubric-result.schema.json"]
        legacy["dimensions"]["no_trade_reasoning"] = {
            "status": "PASS",
            "grade": 2,
            "claim_evidence_refs": ["ev-1"],
            "reason": "旧字段。",
        }
        with self.assertRaisesRegex(SchemaValidationError, "SCHEMA_REQUIRED_MISSING"):
            validate_schema_instance(legacy, schema)

        out_of_range = valid_examples()["semantic-rubric-result.schema.json"]
        out_of_range["dimensions"]["no_trade_reasoning"]["grade"] = 4
        with self.assertRaisesRegex(SchemaValidationError, "SCHEMA_MAXIMUM"):
            validate_schema_instance(out_of_range, schema)


class ModelRoutingTests(unittest.TestCase):
    def test_required_routes_are_versioned(self):
        policy = load_model_routing(ROOT / "product")
        self.assertEqual(policy["development_default"], "gpt-5.6-sol")
        self.assertEqual(policy["runtime_repeated"], "gpt-5.6-terra")
        self.assertEqual(select_model(ROOT / "product", route="runtime_repeated"), "gpt-5.6-terra")

    def test_astra_requires_dispute_and_human_approval(self):
        with self.assertRaisesRegex(ValueError, "ASTRA_APPROVAL_MISSING"):
            select_model(ROOT / "product", route="architecture_dispute")
        with tempfile.TemporaryDirectory() as directory:
            approval = Path(directory) / "approval.json"
            approval.write_text("{}", encoding="utf-8")
            self.assertEqual(
                select_model(
                    ROOT / "product",
                    route="architecture_dispute",
                    dispute_id="dispute-1",
                    human_approval_artifact=approval,
                ),
                "gpt-6-astra",
            )

    def test_unknown_route_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "MODEL_ROUTE_INVALID"):
            select_model(ROOT / "product", route="cheap")


class AssuranceBoundaryTests(unittest.TestCase):
    def test_no_python_llm_backend_or_hardcoded_investment_conclusion(self):
        self.assertEqual(inspect_product_python(ROOT / "product"), [])

    def test_action_contract_does_not_add_reduce(self):
        contract = json.loads(
            (ROOT / "product" / "contracts" / "council-decision-contract.json").read_text(encoding="utf-8")
        )
        actions = set(contract["actions"])
        self.assertEqual(actions, {"BUY", "ADD", "HOLD", "TRIM", "EXIT", "NO_TRADE"})
        self.assertNotIn("REDUCE", actions)


if __name__ == "__main__":
    unittest.main()
