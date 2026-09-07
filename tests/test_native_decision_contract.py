from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from product.runtime.decision_contract import (
    DecisionContractError,
    derive_action_schema_conditions,
    load_decision_contract,
    render_cio_action_prompt,
    validate_decision_action,
    validate_no_investment_policy_keys,
    verify_cio_schema,
)
from product.runtime.discovery import discover_product_resources
from product.runtime.run_package import prepare_cio, prepare_run
from tests.test_native_run_package import FIXTURES, specialist_outputs


ROOT = Path(__file__).resolve().parents[1]
PRODUCT_ROOT = ROOT / "product"


class CanonicalDecisionContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = load_decision_contract(PRODUCT_ROOT)

    def test_contract_declares_null_semantics_and_has_no_investment_policy(self):
        validate_no_investment_policy_keys(self.contract)
        no_trade = next(
            profile
            for profile in self.contract["action_profiles"]
            if profile["actions"] == ["NO_TRADE"]
        )
        execution = next(
            item
            for item in no_trade["constraints"]
            if item["rule_code"] == "NO_TRADE_EXECUTION_FIELDS_FORBIDDEN"
        )
        self.assertIsNone(execution["fields"]["target_weight_range"]["value"])
        self.assertIsNone(execution["fields"]["maximum_notional"]["value"])
        examples = {item["example_id"]: item for item in self.contract["prompt_examples"]}
        self.assertEqual(
            examples["invalid-no-trade-zero-notional"]["value"]["maximum_notional"],
            0,
        )

    def test_schema_conditions_and_prompt_are_derived_from_contract(self):
        verify_cio_schema(PRODUCT_ROOT, self.contract)
        conditions = derive_action_schema_conditions(self.contract)
        no_trade = conditions[0]["then"]["allOf"][0]["properties"]
        self.assertEqual(no_trade["maximum_notional"], {"const": None})
        self.assertEqual(no_trade["target_weight_range"], {"const": None})
        prompt = render_cio_action_prompt(self.contract)
        self.assertIn("0 不等于 JSON null", prompt)
        self.assertIn("valid-no-trade", prompt)
        self.assertIn("invalid-no-trade-zero-notional", prompt)
        self.assertIn("invalid-no-trade-target-range", prompt)

    def test_action_matrix_rejects_zero_and_nonnull_no_trade_fields(self):
        valid = {
            "action": "NO_TRADE",
            "target_weight_range": None,
            "maximum_notional": None,
            "no_trade_reason": "EVIDENCE_CONFLICT",
            "no_trade_explanation": "冲突尚未解决。",
            "reevaluation_conditions": ["获得新证据。"],
        }
        validate_decision_action(valid, self.contract)

        zero = dict(valid, maximum_notional=0)
        with self.assertRaisesRegex(
            DecisionContractError, "NO_TRADE_EXECUTION_FIELDS_FORBIDDEN"
        ):
            validate_decision_action(zero, self.contract)

        ranged = dict(valid, target_weight_range=[0, 0])
        with self.assertRaisesRegex(
            DecisionContractError, "NO_TRADE_EXECUTION_FIELDS_FORBIDDEN"
        ):
            validate_decision_action(ranged, self.contract)

        action = {
            "action": "HOLD",
            "security_id": "SEC-AAA",
            "current_weight": 0.5,
            "target_weight_range": [0.5, 0.5],
            "thesis": "由 LLM 生成的结构占位值。",
            "evidence_refs": ["ev-1"],
            "invalidation_conditions": ["条件变化。"],
            "no_trade_reason": None,
            "no_trade_explanation": None,
        }
        validate_decision_action(action, self.contract)

    def test_schema_or_contract_tampering_fails_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            shutil.copytree(PRODUCT_ROOT, repo / "product")
            schema_path = (
                repo / "product" / "schemas" / "runtime" / "cio-decision-draft.schema.json"
            )
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            schema["allOf"][0]["then"]["allOf"][0]["properties"][
                "maximum_notional"
            ] = {"const": 0}
            schema_path.write_text(json.dumps(schema), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "CIO_SCHEMA_ACTION_CONDITIONS_DRIFT"):
                discover_product_resources(repo)

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            shutil.copytree(PRODUCT_ROOT, repo / "product")
            contract_path = repo / "product" / "contracts" / "council-decision-contract.json"
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            contract["prompt_examples"][0]["example_id"] = "tampered-example"
            contract_path.write_text(json.dumps(contract), encoding="utf-8")
            with self.assertRaisesRegex(
                ValueError, "CIO_SCHEMA_CONTRACT_METADATA_DRIFT|resource hash mismatch"
            ):
                discover_product_resources(repo)

        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            shutil.copytree(PRODUCT_ROOT, repo / "product")
            (repo / "product" / "contracts" / "council-decision-contract.json").unlink()
            with self.assertRaises(FileNotFoundError):
                discover_product_resources(repo)

        broken = copy.deepcopy(self.contract)
        broken["recommended_action"] = "BUY"
        with self.assertRaises(DecisionContractError):
            validate_no_investment_policy_keys(broken)

    def test_runtime_cio_prompt_contains_the_canonical_render_without_duplication(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "prompt"
            prepare_run(
                ROOT,
                fixture_path=FIXTURES / "normal-research.json",
                run_dir=run_dir,
                run_id="contract-prompt",
                model="gpt-5.6-terra",
                research_question="验证 canonical prompt。",
                authenticity_required=False,
            )
            specialist_outputs(run_dir)
            prepare_cio(ROOT, run_dir=run_dir, model="gpt-5.6-terra")
            prompt = (run_dir / "prompts" / "runtime_cio.txt").read_text(
                encoding="utf-8"
            )
            fragment = render_cio_action_prompt(self.contract)
            self.assertEqual(prompt.count(fragment), 1)
            self.assertIn("CIODecisionDraft 2.1.0", prompt)


if __name__ == "__main__":
    unittest.main()
