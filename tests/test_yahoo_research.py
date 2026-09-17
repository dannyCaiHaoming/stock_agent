from __future__ import annotations

import json
import unittest

from product.mcp.live.yahoo_research import normalize_quote_summary


class YahooResearchTests(unittest.TestCase):
    def payload(self):
        return json.dumps({
            "quoteSummary": {"error": None, "result": [{
                "price": {"symbol": "AAPL", "quoteType": "EQUITY", "longName": "Apple Inc.", "currency": "USD", "exchange": "NMS", "regularMarketPrice": {"raw": 250}},
                "assetProfile": {"sector": "Technology", "industry": "Consumer Electronics", "website": "https://apple.com", "fullTimeEmployees": 100},
                "calendarEvents": {"earnings": {"earningsDate": [{"raw": 1790000000}], "earningsAverage": {"raw": 2.1}}},
                "earningsTrend": {"trend": [{
                    "period": "+1q", "endDate": "2026-12-31",
                    "earningsEstimate": {"numberOfAnalysts": {"raw": 20}, "avg": {"raw": 2.1}, "low": {"raw": 1.9}, "high": {"raw": 2.3}},
                    "epsTrend": {"current": {"raw": 2.1}, "30daysAgo": {"raw": 2.0}},
                }]},
                "recommendationTrend": {"trend": [{"period": "0m", "buy": 20, "hold": 10, "sell": 1}]},
                "defaultKeyStatistics": {"sharesShort": {"raw": 1000}, "shortPercentOfFloat": {"raw": 0.01}, "shortRatio": {"raw": 1.2}, "trailingPE": {"raw": 31.25}, "forwardPE": {"raw": 28.5}, "priceToBook": {"raw": 45}, "enterpriseValue": {"raw": 4000000000000}, "enterpriseToEbitda": {"raw": 24}, "sharesOutstanding": {"raw": 15000000000}},
                "summaryDetail": {"dividendRate": {"raw": 1.0}, "payoutRatio": {"raw": 0.2}, "priceToSalesTrailing12Months": {"raw": 9.5}}
            }]}
        }).encode()

    def test_profile_expectations_events_and_short_context_keep_semantics(self):
        result = normalize_quote_summary(
            self.payload(), security_id="US:COMMON_STOCK:AAPL", ticker="AAPL",
            retrieved_at="2026-09-15T12:00:00Z",
        )
        datasets = {item["dataset"] for item in result["evidence"]}
        self.assertTrue({
            "identity_profile", "event_context", "analyst_expectations",
            "share_short_context", "capital_allocation",
        } <= datasets)
        expectations = next(item for item in result["evidence"] if item["semantic_field"] == "yahoo_earnings_trend")
        self.assertIn("vintage", " ".join(expectations["limitations"]))
        short = next(item for item in result["evidence"] if item["dataset"] == "share_short_context")
        self.assertIn("short interest", " ".join(short["limitations"]))
        valuation = result["valuation_snapshot"]
        self.assertEqual("FIRST_OBSERVED_AT_RETRIEVAL", valuation["availability_status"])
        self.assertIsNone(valuation["published_at"])
        self.assertEqual(31.25, valuation["fields"]["trailingPE"])
        self.assertNotIn("trailingPE", valuation["missing_fields"])

    def test_wrong_security_and_bad_shape_fail_closed(self):
        body = json.loads(self.payload())
        body["quoteSummary"]["result"][0]["price"]["symbol"] = "MSFT"
        with self.assertRaisesRegex(ValueError, "SECURITY_MISMATCH"):
            normalize_quote_summary(
                json.dumps(body).encode(), security_id="US:COMMON_STOCK:AAPL", ticker="AAPL",
                retrieved_at="2026-09-15T12:00:00Z",
            )
        with self.assertRaisesRegex(ValueError, "RESPONSE_INVALID"):
            normalize_quote_summary(
                b"{}", security_id="US:COMMON_STOCK:AAPL", ticker="AAPL",
                retrieved_at="2026-09-15T12:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
