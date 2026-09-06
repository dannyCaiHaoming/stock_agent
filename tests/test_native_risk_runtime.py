import json
import unittest
from pathlib import Path

from product.runtime.evidence_gate import load_fixture
from product.runtime.risk_runtime import check_cio_draft


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "evals" / "fixtures" / "codex-native"


class NativeRiskRuntimeTests(unittest.TestCase):
    def test_boundary_fixture_is_stably_rejected_without_llm_provenance(self):
        fixture = load_fixture(FIXTURES / "risk-veto.json")
        draft = json.loads((FIXTURES / "risk-boundary-draft.json").read_text())
        first = check_cio_draft(fixture, draft, run_id="risk-boundary")
        second = check_cio_draft(fixture, draft, run_id="risk-boundary")
        self.assertEqual(first, second)
        self.assertEqual(draft["producer"], "fixture")
        self.assertTrue(draft["not_llm_output"])
        self.assertEqual(first["check"]["status"], "REJECTED")
        self.assertEqual(first["final_action"], "NO_TRADE")
        self.assertEqual(first["veto_reason"], "RISK_VETO")
        self.assertIn("POSITION_LIMIT", first["check"]["veto_codes"])

    def test_same_draft_and_policy_produce_same_approved_result(self):
        fixture = load_fixture(FIXTURES / "normal-research.json")
        draft = {
            "action": "HOLD",
            "security_id": "SEC-AAA",
            "target_weight_range": [0.5, 0.5],
        }
        first = check_cio_draft(fixture, draft, run_id="risk-normal")
        second = check_cio_draft(fixture, draft, run_id="risk-normal")
        self.assertEqual(first, second)
        self.assertEqual(first["check"]["status"], "APPROVED")
        self.assertEqual(first["original_action"], "HOLD")
        self.assertEqual(first["final_action"], "HOLD")


if __name__ == "__main__":
    unittest.main()
