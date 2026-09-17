from __future__ import annotations

import unittest

from product.mcp.live.fundamental_supplement import (
    build_actual_expectation_record,
    build_debt_liquidity_record,
    build_earnings_quality_record,
    build_operating_kpi_item,
    normalize_financial_fields,
    select_disclosure_documents,
    verified_disclosure_item,
)


CUTOFF = "2026-09-17T12:00:00Z"


def fact(identifier, tag, value="100", *, period="2026-06-30"):
    return {
        "evidence_id": identifier, "value": value, "unit": "USD",
        "metadata": {
            "tag": tag, "period_start": "2026-01-01", "period_end": period,
            "context_type": "duration", "unit": "USD",
        },
    }


class DocumentSelectionTests(unittest.TestCase):
    def test_budget_dedup_cutoff_and_no_disclosure_claim(self):
        docs = []
        for index in range(5):
            docs.append({
                "accession": f"q-{index}", "form": "10-Q",
                "published_at": f"2026-0{index + 1}-01T00:00:00Z",
            })
        docs += [
            dict(docs[0]),
            {"accession": "future", "form": "10-K", "published_at": "2026-10-01T00:00:00Z"},
        ]
        result = select_disclosure_documents(docs, decision_cutoff=CUTOFF)
        self.assertEqual(4, len(result["selected"]))
        self.assertEqual(1, result["omitted_counts"]["quarterly"])
        self.assertEqual("BUDGET_TRUNCATED", result["category_status"]["quarterly"])
        self.assertEqual("NO_DOCUMENT_FOUND_IN_BOUNDED_SEARCH", result["category_status"]["proxy"])
        self.assertIn("DOES_NOT_PROVE_NOT_DISCLOSED", result["coverage_limitation"])
        self.assertTrue(any(item["reason"] == "AFTER_CUTOFF" for item in result["rejected"]))


class FinancialNormalizationTests(unittest.TestCase):
    def test_alternative_tags_same_value_are_not_double_counted(self):
        result = normalize_financial_fields([
            fact("ev-revenue-specific", "RevenueFromContractWithCustomerExcludingAssessedTax"),
            fact("ev-revenues", "Revenues"),
        ])
        revenue = next(item for item in result["fields"] if item["semantic_field"] == "revenue")
        self.assertEqual("100", revenue["value"])
        self.assertEqual(2, len(revenue["evidence_refs"]))
        self.assertEqual("RevenueFromContractWithCustomerExcludingAssessedTax", revenue["source_tag"])

    def test_alternative_tags_conflict_is_preserved(self):
        result = normalize_financial_fields([
            fact("ev-one", "Revenues", "100"),
            fact("ev-two", "SalesRevenueNet", "110"),
        ])
        self.assertTrue(any(item["semantic_field"] == "revenue" for item in result["conflicts"]))
        self.assertFalse(any(item["semantic_field"] == "revenue" for item in result["fields"]))


class DisclosureNormalizationTests(unittest.TestCase):
    def candidate(self):
        return {
            "evidence_id": "ev-candidate", "source_id": "sec:accession",
            "source_locator": "https://www.sec.gov/Archives/test",
            "as_of": "2026-06-30T00:00:00Z", "published_at": "2026-08-01T00:00:00Z",
            "retrieved_at": CUTOFF,
            "value": {"accession": "0001", "section": "management_discussion", "raw_character_spans": [[10, 40]]},
        }

    def test_candidate_requires_locator_and_separate_review_evidence(self):
        item = verified_disclosure_item(
            self.candidate(), item_id="guidance-1", definition="FY2027 revenue guidance",
            period="FY2027", unit="USDm", review_evidence_refs=["ev-review"],
        )
        self.assertEqual("VERIFIED_FACT", item["claim_status"])
        self.assertEqual(["ev-candidate", "ev-review"], item["evidence_refs"])
        broken = self.candidate()
        broken["value"]["raw_character_spans"] = []
        with self.assertRaisesRegex(ValueError, "LOCATOR_MISSING"):
            verified_disclosure_item(
                broken, item_id="bad", definition="bad", period=None, unit=None,
                review_evidence_refs=["ev-review"],
            )

    def test_kpi_preserves_definition_and_anonymity(self):
        item = build_operating_kpi_item(
            item_id="customer-concentration", name="single customer revenue share",
            value="18", unit="percent", period="FY2026", definition="issuer disclosed percentage",
            definition_version="FY2026", scope="consolidated revenue",
            source_id="sec:10-k", as_of="2026-06-30T00:00:00Z",
            published_at="2026-08-01T00:00:00Z", retrieved_at=CUTOFF,
            evidence_refs=["ev-kpi"], anonymous_counterparty=True,
        )
        self.assertTrue(item["anonymous_counterparty"])
        self.assertEqual("FY2026", item["definition_version"])


class DebtAndExpectationTests(unittest.TestCase):
    def test_sbc_repurchase_and_share_counts_stay_separate(self):
        record = build_earnings_quality_record(
            stock_based_compensation={"value": "10", "unit": "USDm", "period": "FY2026", "evidence_refs": ["ev-sbc"]},
            repurchases={"value": "30", "unit": "USDm", "period": "FY2026", "evidence_refs": ["ev-repurchase"]},
            actual_shares_outstanding={"value": "100", "unit": "million_shares", "period": "2026-12-31", "evidence_refs": ["ev-actual"]},
            weighted_average_diluted_shares={"value": "105", "unit": "million_shares", "period": "FY2026", "evidence_refs": ["ev-weighted"]},
        )
        self.assertIsNone(record["net_dilution"])
        self.assertEqual("ACTUAL_PERIOD_END_SHARES", record["actual_shares_outstanding"]["kind"])
        self.assertEqual("WEIGHTED_AVERAGE_DILUTED_SHARES", record["weighted_average_diluted_shares"]["kind"])
        self.assertIn("不构成净稀释", record["limitations"][0])

    def test_debt_schedule_keeps_unexplained_difference_and_restricted_cash(self):
        record = build_debt_liquidity_record(
            facts=[
                fact("ev-debt-1", "LongTermDebtMaturitiesRepaymentsOfPrincipalInNextTwelveMonths", "20"),
                fact("ev-debt-2", "LongTermDebtMaturitiesRepaymentsOfPrincipalInYearTwo", "30"),
            ],
            carrying_debt="60", unrestricted_cash="10", restricted_cash="5",
            lease_scope="excluded", principal_scope="senior notes only",
        )
        self.assertEqual("-10", record["unexplained_difference"])
        self.assertEqual("UNEXPLAINED_DIFFERENCE", record["reconciliation_status"])
        self.assertIn("未从债务中自动抵扣", record["limitations"][0])

    def test_expectation_without_vintage_stays_provider_reported(self):
        record = build_actual_expectation_record(
            provider_reported={"surprise": "0.1", "published_at": None}, comparison=None,
        )
        self.assertEqual("PROVIDER_REPORTED_UNVERIFIED", record["status"])
        self.assertIsNone(record["comparison"])


if __name__ == "__main__":
    unittest.main()
