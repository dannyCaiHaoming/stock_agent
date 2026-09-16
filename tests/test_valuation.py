import unittest
from decimal import Decimal

from product.deterministic.valuation import (
    comparable_period_change,
    convert_monetary_scale,
    equity_value_per_share,
    financial_ratio,
    operating_scenario_value_per_share,
    present_value,
    free_cash_flow_bridge,
    net_debt_bridge,
    share_count_change,
    validate_monetary_scale_equivalence,
)


class ValuationTests(unittest.TestCase):
    def test_fundamental_bridges_use_raw_values_without_judging_company(self):
        fcf = free_cash_flow_bridge(
            operating_cash_flow="150", capital_expenditure="40", period="FY2025",
            currency="USD million", as_of="2025-12-31",
            evidence_fact_ids=("ocf", "capex"),
        )
        self.assertEqual(fcf.outputs["free_cash_flow_bridge"], "110")
        net_debt = net_debt_bridge(
            debt="250", cash="100", period="2025-12-31", currency="USD million",
            as_of="2025-12-31", evidence_fact_ids=("debt", "cash"),
        )
        self.assertEqual(net_debt.outputs["net_debt"], "150")
        dilution = share_count_change(
            earlier_shares="100", later_shares="105", earlier_period="FY2024",
            later_period="FY2025", as_of="2025-12-31",
            evidence_fact_ids=("shares-2024", "shares-2025"),
        )
        self.assertEqual(dilution.outputs["percent_change"], "0.05")
        self.assertEqual(dilution.evidence_fact_ids, ("shares-2024", "shares-2025"))

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

    def test_comparable_change_records_formula_period_units_and_hash(self):
        artifact = comparable_period_change(
            earlier_value="100", later_value="125", earlier_period="FY2024",
            later_period="FY2025", unit="USD million", as_of="2026-01-01T00:00:00Z",
            assumption_ids=(), evidence_fact_ids=("fact-fy2024", "fact-fy2025"),
        )
        self.assertEqual("0.25", artifact.outputs["percent_change"])
        self.assertEqual("FY2024", artifact.periods["earlier_value"])
        self.assertEqual("USD million", artifact.units["absolute_change"])
        self.assertEqual(64, len(artifact.artifact_hash))

    def test_ratio_rejects_period_or_unit_mismatch(self):
        for period, unit in (("FY2024", "USD million"), ("FY2025", "shares")):
            with self.subTest(period=period, unit=unit), self.assertRaises(ValueError):
                financial_ratio(
                    numerator="20", denominator="100", numerator_period="FY2025",
                    denominator_period=period, numerator_unit="USD million",
                    denominator_unit=unit, as_of="2026-01-01T00:00:00Z",
                    assumption_ids=(), evidence_fact_ids=("fact-a", "fact-b"),
                )

    def test_explicit_operating_scenario_is_deterministic_and_auditable(self):
        artifact = operating_scenario_value_per_share(
            revenue="1000", operating_margin="0.20", valuation_multiple="12",
            net_cash="100", shares="100", period="FY2027E", currency="USD million",
            as_of="2026-01-01T00:00:00Z",
            assumption_ids=("assumption-margin", "assumption-multiple"),
            evidence_fact_ids=("fact-revenue", "fact-cash", "fact-shares"),
        )
        self.assertEqual("25.00", artifact.outputs["value_per_share"])
        self.assertIn("operating_margin", artifact.formula)
        self.assertEqual("USD million/share", artifact.units["value_per_share"])

    def test_monetary_scale_conversion_preserves_exact_magnitude_and_lineage(self):
        cases = (
            ("1.8", "billion", "亿", "18"),
            ("180", "million", "亿", "1.8"),
            ("-1.8", "billion", "亿", "-18"),
            ("18", "亿", "亿", "18"),
        )
        for value, source_scale, target_scale, expected in cases:
            with self.subTest(value=value, source_scale=source_scale):
                artifact = convert_monetary_scale(
                    value=value,
                    source_scale=source_scale,
                    target_scale=target_scale,
                    currency="USD",
                    as_of="2026-01-31",
                    evidence_fact_ids=("fact-disclosed-amount",),
                )
                self.assertEqual(expected, artifact.outputs["converted_value"])
                self.assertEqual(
                    f"USD {target_scale}", artifact.units["converted_value"]
                )
                self.assertEqual(
                    ("fact-disclosed-amount",), artifact.evidence_fact_ids
                )

    def test_monetary_scale_equivalence_rejects_tenfold_mistranslation(self):
        validate_monetary_scale_equivalence(
            source_value="1.8", source_scale="billion",
            reported_value="18", reported_scale="亿",
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            validate_monetary_scale_equivalence(
                source_value="1.8", source_scale="billion",
                reported_value="1.8", reported_scale="亿",
            )
        with self.assertRaisesRegex(ValueError, "unsupported monetary scale"):
            validate_monetary_scale_equivalence(
                source_value="1", source_scale="trillion",
                reported_value="1", reported_scale="亿",
            )


if __name__ == "__main__":
    unittest.main()
