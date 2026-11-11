import copy
import unittest

from product.mcp.live.financials import compare_year_over_year


class FinancialComparisonTests(unittest.TestCase):
    def setUp(self):
        base = {"security_id": "TEST", "cik": "0000000001", "taxonomy": "us-gaap", "tag": "Revenues",
                "unit": "USD", "context_type": "duration", "source_id": "synthetic", "source_locator": "synthetic",
                "as_of": "2026-06-30T00:00:00Z", "published_at": "2026-08-01T00:00:00Z",
                "retrieved_at": "2026-09-10T00:00:00Z", "period_start": "2026-01-01", "period_end": "2026-06-30"}
        self.evidence = {"current": dict(base, evidence_id="current", value="120"),
                         "prior": dict(base, evidence_id="prior", value="100", period_start="2025-01-01",
                                       period_end="2025-06-30", as_of="2025-06-30T00:00:00Z")}

    def test_comparison_provenance(self):
        result = compare_year_over_year("current", "prior", self.evidence)
        self.assertEqual(result["value"], {"absolute_change": "20", "percent_change": "20.0"})
        self.assertEqual(result["parent_ids"], ["current", "prior"])
        self.assertEqual(len(result["parent_hashes"]), 2)
        self.assertEqual(result["retrieved_at"], self.evidence["current"]["retrieved_at"])
        self.assertEqual(result["calculation_version"], "sec-comparison/1.2.0")
        self.assertEqual(result["accounting_basis_status"], "UNVERIFIED")
        self.assertEqual(result["trend_interpretation_status"], "REQUIRES_EVIDENCE_REVIEW")
        self.assertIn("arithmetic change only", result["comparison_limitation"])

    def test_noncomparable_cases(self):
        for mutation in ({"unit": "EUR"}, {"period_start": "2025-04-01"}, {"tag": "NetIncomeLoss"},
                         {"context_type": "instant"}, {"security_id": "OTHER"}, {"value": "NaN"},
                         {"period_end": "2026-06-30"}):
            evidence = copy.deepcopy(self.evidence)
            evidence["prior"].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                compare_year_over_year("current", "prior", evidence)

    def test_nonpositive_base_preserves_delta(self):
        for value in ("0", "-100"):
            self.evidence["prior"]["value"] = value
            result = compare_year_over_year("current", "prior", self.evidence)
            self.assertIsNone(result["value"]["percent_change"])
            self.assertEqual(result["percentage_unavailable_reason"], "NON_POSITIVE_BASE")

    def test_missing_or_duplicate_parent(self):
        for pair in (("absent", "prior"), ("current", "current")):
            with self.assertRaises(ValueError):
                compare_year_over_year(*pair, self.evidence)

    def fiscal_pair(self):
        pair = copy.deepcopy(self.evidence)
        pair["current"].update(form="10-K", accession="same", period_start="2024-09-29", period_end="2025-09-27")
        pair["prior"].update(form="10-K", accession="same", period_start="2023-10-01", period_end="2024-09-28")
        return pair

    def test_same_filing_fiscal_weeks(self):
        pair = self.fiscal_pair()
        result = compare_year_over_year("current", "prior", pair)
        self.assertEqual(result["period_day_counts"], [364, 364])
        self.assertFalse(result["period_length_adjusted"])
        self.assertEqual(result["calculation_version"], "sec-comparison/1.2.0")
        self.assertEqual(result["parent_ids"], ["current", "prior"])
        self.assertEqual(result["accounting_basis_status"], "UNVERIFIED")
        self.assertEqual(result["comparability_scope"], "MATCHED_METRIC_UNIT_AND_PERIOD_STRUCTURE_ONLY")
        self.assertIn("before interpreting a trend", result["comparison_limitation"])

    def test_fiscal_dates_alone_do_not_prove_comparability(self):
        for change in ({"accession": "other"}, {"form": "10-Q"}, {"period_start": "2024-01-01"},
                       {"period_end": "2024-09-27"}, {"unit": "EUR"}):
            pair = self.fiscal_pair()
            pair["prior"].update(change)
            with self.subTest(change=change), self.assertRaises(ValueError):
                compare_year_over_year("current", "prior", pair)

    def test_fiscal_quarter_and_ytd_not_mixed(self):
        pair = self.fiscal_pair()
        pair["current"].update(form="10-Q", period_start="2026-04-27", period_end="2026-07-26")
        pair["prior"].update(form="10-Q", period_start="2025-04-28", period_end="2025-07-27")
        self.assertEqual(compare_year_over_year("current", "prior", pair)["period_day_counts"], [91, 91])
        pair["prior"]["period_start"] = "2025-01-27"
        with self.assertRaises(ValueError):
            compare_year_over_year("current", "prior", pair)

    def test_equal_length_eps_does_not_claim_share_denominator_comparability(self):
        pair = self.fiscal_pair()
        for item in pair.values():
            item.update(form="10-Q", tag="EarningsPerShareDiluted", unit="USD/shares")
        pair["current"].update(period_start="2025-12-29", period_end="2026-03-29", value="-3.05")
        pair["prior"].update(period_start="2024-12-30", period_end="2025-03-30", value="-1.86")
        result = compare_year_over_year("current", "prior", pair)
        self.assertEqual(result["period_day_counts"], [91, 91])
        self.assertEqual(result["share_denominator_status"], "UNVERIFIED")
        self.assertEqual(result["accounting_basis_status"], "UNVERIFIED")
        self.assertEqual(result["value"]["absolute_change"], "-1.19")

    def test_future_parent_not_backdated(self):
        self.evidence["prior"]["published_at"] = "2026-12-01T00:00:00Z"
        result = compare_year_over_year("current", "prior", self.evidence)
        self.assertEqual(result["published_at"], "2026-12-01T00:00:00Z")

    def test_instant_comparison_and_invalid_start(self):
        for parent in self.evidence.values():
            parent.update(context_type="instant", period_start=None)
        self.assertEqual(compare_year_over_year("current", "prior", self.evidence)["value"]["absolute_change"], "20")
        self.evidence["current"]["period_start"] = "2026-01-01"
        with self.assertRaisesRegex(ValueError, "INSTANT_WITH_START"):
            compare_year_over_year("current", "prior", self.evidence)

    def selection(self, repeated_value):
        facts = [dict(f, raw_content_hash="a" * 64, adapter_version="synthetic/1",
                      form="10-Q", accession="original") for f in self.evidence.values()]
        facts.append(dict(facts[1], evidence_id="prior-repeated", accession="repeated",
                          value=repeated_value))
        return research_financials(facts, security_id="TEST", selection_time="2026-09-10T00:00:00Z")

