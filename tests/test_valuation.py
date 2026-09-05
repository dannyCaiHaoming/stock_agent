import unittest
from decimal import Decimal

from product.deterministic.valuation import equity_value_per_share, present_value


class ValuationTests(unittest.TestCase):
    def test_present_value_matches_golden_case_and_records_lineage(self):
        artifact = present_value(cash_flow="110.00", discount_rate="0.10", periods=1,
            as_of="2026-01-01", assumption_ids=("assumption-discount-rate",),
            evidence_fact_ids=("fact-cash-flow",))
        self.assertEqual(Decimal("100.00"), Decimal(artifact.outputs["present_value"]))
        self.assertTrue(artifact.artifact_id.startswith("calc:present-value:"))
        self.assertEqual(("fact-cash-flow",), artifact.evidence_fact_ids)

    def test_equity_bridge_matches_golden_case(self):
        artifact = equity_value_per_share(enterprise_value="1200.00", cash="200.00",
            debt="400.00", shares="100.00", as_of="2026-01-01", assumption_ids=(),
            evidence_fact_ids=("fact-ev", "fact-cash", "fact-debt", "fact-shares"))
        self.assertEqual("1000.00", artifact.outputs["equity_value"])
        self.assertEqual("10", artifact.outputs["value_per_share"])

    def test_calculator_refuses_non_numeric_judgment_inputs(self):
        with self.assertRaises(ValueError):
            present_value(cash_flow="excellent company", discount_rate="0.10", periods=1,
                as_of="2026-01-01", assumption_ids=(), evidence_fact_ids=())


if __name__ == "__main__":
    unittest.main()
