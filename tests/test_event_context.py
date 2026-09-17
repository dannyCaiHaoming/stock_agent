from __future__ import annotations

import unittest

from product.mcp.live.event_context import normalize_event_rows, normalize_short_rows


COMMON = {
    "security_id": "US:COMMON_STOCK:AAPL", "ticker": "AAPL",
    "retrieved_at": "2026-09-15T12:00:00Z", "raw_content_hash": "a" * 64,
    "source_locator": "https://finance.yahoo.com/quote/AAPL/news",
}


class EventContextTests(unittest.TestCase):
    def test_duplicates_estimated_dates_title_only_and_fourth_party_are_limited(self):
        rows = [{
            "title": "Earnings date", "published_at": "2026-09-14T10:00:00Z",
            "as_of": "2026-09-14T10:00:00Z", "content_tier": "TITLE_ONLY",
            "event_type": "EARNINGS", "event_date": "2026-10-30",
            "event_date_estimated": True, "original_url": "https://finance.yahoo.com/news/1",
        }, {
            "title": "Earnings date duplicate", "published_at": "2026-09-14T11:00:00Z",
            "as_of": "2026-09-14T11:00:00Z", "content_tier": "TITLE_ONLY",
            "event_type": "EARNINGS", "original_url": "https://finance.yahoo.com/news/1",
        }, {
            "title": "Fourth party", "published_at": "2026-09-14T12:00:00Z",
            "as_of": "2026-09-14T12:00:00Z", "content_tier": "SUMMARY",
            "event_type": "NEWS", "original_url": "https://fourth.example/story",
        }]
        result = normalize_event_rows(
            rows, source_family="yahoo", allowed_original_hosts=["finance.yahoo.com"], **COMMON
        )
        self.assertEqual(len(result["evidence"]), 1)
        fact = result["evidence"][0]
        self.assertEqual(fact["value"]["event_date_status"], "ESTIMATED")
        self.assertEqual(fact["value"]["transcript_status"], "NOT_AVAILABLE")
        self.assertEqual(
            {item["reason"] for item in result["gaps"]},
            {"EVENT_DUPLICATE_EXCLUDED", "EVENT_FOURTH_PARTY_LINK_EXCLUDED"},
        )

    def test_transcript_locator_does_not_claim_transcript_content(self):
        result = normalize_event_rows([{
            "title": "Earnings call", "published_at": "2026-09-14T10:00:00Z",
            "as_of": "2026-09-14T10:00:00Z", "content_tier": "TRANSCRIPT_LOCATOR",
            "event_type": "EARNINGS_CALL", "original_url": "https://www.moomoo.com/sg/call/1",
        }], source_family="moomoo_sg", allowed_original_hosts=["www.moomoo.com"],
            **{**COMMON, "source_locator": "https://www.moomoo.com/sg/call/1"})
        self.assertEqual(result["evidence"][0]["value"]["transcript_status"], "LOCATOR_ONLY")
        self.assertIsNone(result["evidence"][0]["value"]["summary"])

    def test_short_interest_and_volume_are_distinct_and_never_invent_borrow_fee(self):
        result = normalize_short_rows([{
            "statistic_type": "SHORT_INTEREST", "value": 1000, "unit": "shares",
            "as_of": "2026-09-12T00:00:00Z", "days_to_cover": 1.2,
        }, {
            "statistic_type": "SHORT_VOLUME", "value": 200, "unit": "shares",
            "period_start": "2026-09-12", "period_end": "2026-09-12",
            "as_of": "2026-09-12T20:00:00Z",
        }], source_family="yahoo", **COMMON)
        self.assertEqual(
            {item["semantic_field"] for item in result["evidence"]},
            {"short_interest_snapshot", "short_volume_snapshot"},
        )
        self.assertTrue(all(item["value"]["borrow_fee"] is None for item in result["evidence"]))


if __name__ == "__main__":
    unittest.main()
