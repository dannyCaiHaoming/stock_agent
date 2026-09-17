from __future__ import annotations

import unittest

from product.runtime.company_valuation_report import (
    CompanyValuationReportError,
    build_pit_ttm_eps_versions,
    normalized_daily_rows,
    valuation_price_rows,
)


class CompanyValuationReportTests(unittest.TestCase):
    def market_fact(self, field, value, evidence_id):
        return {
            "security_id": "US:COMMON_STOCK:T", "semantic_field": field,
            "value": value, "source_id": "yahoo-daily", "as_of": "2026-09-01T20:00:00Z",
            "retrieved_at": "2026-09-02T00:00:00Z", "evidence_id": evidence_id,
            "metadata": {"trading_date": "2026-09-01"},
        }

    def test_daily_rows_keep_close_and_adjusted_close_separate(self):
        facts = [self.market_fact(field, value, f"ev-{field}") for field, value in (
            ("open_price", "10"), ("high_price", "12"), ("low_price", "9"),
            ("historical_close_price", "11"), ("adjusted_close_price", "10.5"),
            ("share_volume", "100"),
        )]
        rows = normalized_daily_rows(facts, security_id="US:COMMON_STOCK:T")
        self.assertEqual("11", rows[0]["close"])
        self.assertEqual("10.5", rows[0]["adjusted_close"])
        price = valuation_price_rows(rows, security_id="US:COMMON_STOCK:T")[0]
        self.assertFalse(price["dividend_adjusted"])

    def test_conflicting_market_fact_is_rejected(self):
        facts = [self.market_fact("historical_close_price", value, f"ev-{value}") for value in ("10", "11")]
        with self.assertRaisesRegex(CompanyValuationReportError, "MARKET_FIELD_CONFLICT"):
            normalized_daily_rows(facts, security_id="US:COMMON_STOCK:T")

    def test_pit_ttm_uses_only_independent_quarters(self):
        facts = []
        starts = ("2025-01-01", "2025-04-01", "2025-07-01", "2025-10-01")
        ends = ("2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31")
        for index, (start, end) in enumerate(zip(starts, ends)):
            facts.append({
                "security_id": "US:COMMON_STOCK:T", "semantic_field": "us-gaap.EarningsPerShareDiluted",
                "value": str(index + 1), "published_at": f"2025-{4 + index * 2:02d}-15T00:00:00Z",
                "retrieved_at": "2026-01-01T00:00:00Z", "evidence_id": f"ev-q{index}",
                "metadata": {"period_start": start, "period_end": end, "unit": "USD/shares"},
            })
        # 累计期间不能混入季度求和。
        facts.append({**facts[-1], "evidence_id": "ev-ytd", "value": "99", "metadata": {"period_start": "2025-01-01", "period_end": "2025-12-31", "unit": "USD/shares"}})
        versions = build_pit_ttm_eps_versions(
            facts, security_id="US:COMMON_STOCK:T", decision_cutoff="2026-01-02T00:00:00Z",
        )
        self.assertEqual("10", versions[-1]["value"])
        self.assertNotIn("ev-ytd", versions[-1]["evidence_refs"])
        self.assertIn("未从累计 EPS 相减", versions[-1]["limitation"])


if __name__ == "__main__":
    unittest.main()
