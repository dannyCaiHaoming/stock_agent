"""Offline tests for the stock-data MCP tools (no network)."""
import json
import os
import tempfile
import unittest
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

from product.mcp import calc_tools, data_tools, decision_log


def fact(tag, start, end, value, published, accession, unit="USD", form="10-Q"):
    return {"taxonomy": "us-gaap", "tag": tag, "unit": unit, "value": value, "form": form,
            "period_start": start, "period_end": end, "context_type": "duration" if start else "instant",
            "published_at": published, "accession": accession}


def company_data(facts):
    return ({"ticker": "AAA", "cik": "0000000001", "name": "AAA Corp"},
            {"evidence": facts, "raw_content_hash": "h", "coverage": "ALL_LISTED_HISTORY",
             "companyfacts_record": {"retrieved_at": "2026-01-01T00:00:00Z"}})


FACTS = [
    # FY2024 and FY2025 annual revenue; FY2025 later restated in the FY2026-era filing is not needed here.
    fact("Revenues", "2024-01-01", "2024-12-31", "400", "2025-02-01T00:00:00Z", "a-10k-24", form="10-K"),
    fact("Revenues", "2025-01-01", "2025-12-31", "480", "2026-02-01T00:00:00Z", "a-10k-25", form="10-K"),
    # FY2024 restated in the FY2025 10-K
    fact("Revenues", "2024-01-01", "2024-12-31", "410", "2026-02-01T00:00:00Z", "a-10k-25", form="10-K"),
    # FY2025 quarters: Q1-Q3 discrete, plus nine-month YTD
    fact("Revenues", "2025-01-01", "2025-03-31", "100", "2025-04-30T00:00:00Z", "a-q1"),
    fact("Revenues", "2025-04-01", "2025-06-30", "110", "2025-07-30T00:00:00Z", "a-q2"),
    fact("Revenues", "2025-07-01", "2025-09-30", "120", "2025-10-30T00:00:00Z", "a-q3"),
    fact("Revenues", "2025-01-01", "2025-09-30", "330", "2025-10-30T00:00:00Z", "a-q3"),
    fact("Revenues", "2024-10-01", "2024-12-31", "95", "2025-02-01T00:00:00Z", "a-10k-24", form="10-K"),
    fact("Assets", None, "2025-12-31", "900", "2026-02-01T00:00:00Z", "a-10k-25", form="10-K"),
    # cash flow reported only as YTD in 10-Qs
    fact("NetCashProvidedByUsedInOperatingActivities", "2025-01-01", "2025-03-31", "30", "2025-04-30T00:00:00Z", "a-q1"),
    fact("NetCashProvidedByUsedInOperatingActivities", "2025-01-01", "2025-06-30", "70", "2025-07-30T00:00:00Z", "a-q2"),
    fact("NetCashProvidedByUsedInOperatingActivities", "2025-01-01", "2025-09-30", "100", "2025-10-30T00:00:00Z", "a-q3"),
    fact("NetCashProvidedByUsedInOperatingActivities", "2025-01-01", "2025-12-31", "150", "2026-02-01T00:00:00Z", "a-10k-25", form="10-K"),
]


class StatementTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(data_tools, "_company", return_value=company_data(FACTS))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_annual_uses_latest_version_and_reports_restatement(self):
        result = data_tools.get_financial_statements("AAA", period="annual")
        self.assertEqual([p["end"] for p in result["periods"]], ["2024-12-31", "2025-12-31"])
        self.assertEqual(result["lines"]["revenue"], ["410", "480"])
        self.assertEqual(result["lines"]["total_assets"], [None, "900"])  # missing is null, not zero
        self.assertEqual(result["restatements"][0]["period_end"], "2024-12-31")

    def test_quarterly_derives_q4_and_ttm(self):
        result = data_tools.get_financial_statements("AAA", period="quarterly", limit=4)
        self.assertEqual([p["end"] for p in result["periods"]],
                         ["2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31"])
        self.assertEqual(result["lines"]["revenue"], ["100", "110", "120", "150"])
        self.assertEqual(result["derived_cells"][0]["period_end"], "2025-12-31")
        self.assertEqual(result["ttm"]["values"]["revenue"], "480")
        self.assertEqual(result["lines"]["operating_cash_flow"], ["30", "40", "30", "50"])
        self.assertEqual(result["ttm"]["values"]["operating_cash_flow"], "150")

    def test_as_of_excludes_later_publications(self):
        result = data_tools.get_financial_statements("AAA", period="annual", as_of="2025-12-31")
        self.assertEqual([p["end"] for p in result["periods"]], ["2024-12-31"])
        self.assertEqual(result["lines"]["revenue"], ["400"])  # original, pre-restatement value


CHART = {"chart": {"result": [{
    "meta": {"currency": "USD", "fullExchangeName": "NasdaqGS", "instrumentType": "EQUITY"},
    "timestamp": [int(datetime(2025, 1, d, 9, 30, tzinfo=ZoneInfo("America/New_York")).timestamp()) for d in (2, 3, 6)],
    "indicators": {"quote": [{"open": [1, 2, 3], "high": [1, 2, 3], "low": [1, 2, 3], "close": [10, None, 12],
                              "volume": [100, 0, 300]}],
                   "adjclose": [{"adjclose": [9.5, None, 11.4]}]},
    "events": {"dividends": {"1735828200": {"amount": 0.5}}},
}]}}


class PriceTests(unittest.TestCase):
    def test_price_rows_skip_missing_close_and_respect_as_of(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"STOCK_AGENT_DATA_DIR": root}), \
                mock.patch.object(data_tools, "_yahoo_get", return_value=json.dumps(CHART).encode()):
            data_tools.settings.cache.cache_clear()
            result = data_tools.get_price_history("AAA", start="2024-12-01", as_of="2025-01-03")
            data_tools.settings.cache.cache_clear()
        self.assertEqual([r[0] for r in result["rows"]], ["2025-01-02"])
        self.assertEqual(result["rows"][0][4:], ["10", "9.5", "100"])
        self.assertEqual(result["provenance"]["source_id"], "yahoo-chart:AAA")

    def test_invalid_ticker_rejected(self):
        with self.assertRaises(data_tools.DataToolError):
            data_tools.get_price_history("aa$")


class CalcTests(unittest.TestCase):
    def test_calculations_require_evidence_refs(self):
        with self.assertRaises(calc_tools.CalcToolError):
            calc_tools.percent_change("1", "2", "a", "b", "USD", [])

    def test_valuation_multiples_do_not_zero_fill_ev(self):
        result = calc_tools.valuation_multiples("100", "10", "2025-01-02", "FY2024", ["src"], ttm_eps="5")
        metrics = {m["name"]: m for m in result["metrics"]}
        self.assertEqual(metrics["trailing_pe"]["value"], "20")
        self.assertEqual(metrics["enterprise_value"]["status"], "INPUT_MISSING")


class ServerErrorTests(unittest.TestCase):
    def test_tool_errors_reach_the_model(self):
        from mcp.server.mcpserver.exceptions import ToolError
        from product.mcp import server
        with self.assertRaises(ToolError) as caught:
            server.percent_change("1", "2", "a", "b", "USD", [])
        self.assertIn("EVIDENCE_REFS_REQUIRED", str(caught.exception))


class DecisionLogTests(unittest.TestCase):
    def save(self, **overrides):
        args = dict(ticker="AAA", action="HOLD", confidence="medium", horizon="12 months", thesis="t",
                    key_evidence=["e"], risks=["r"], invalidation=["i"], data_as_of="2025-01-02",
                    report_markdown="# report", price_at_decision="10")
        args.update(overrides)
        return decision_log.save_decision(**args)

    def test_writes_report_and_appends_record(self):
        with tempfile.TemporaryDirectory() as root, mock.patch.dict(os.environ, {"STOCK_AGENT_DATA_DIR": root}):
            first, second = self.save(), self.save(action="NO_TRADE", no_trade_reason="data gap",
                                                    price_at_decision=None)
            with open(os.path.join(root, "decisions.jsonl")) as handle:
                lines = handle.read().splitlines()
            self.assertEqual(len(lines), 2)
            self.assertTrue(os.path.exists(first["report_path"]))
            self.assertEqual(json.loads(lines[1])["action"], "NO_TRADE")
            self.assertNotEqual(first["decision_id"], second["decision_id"])

    def test_rejects_invalid_records(self):
        for overrides in ({"action": "SELL"}, {"confidence": "0.8"}, {"risks": []},
                          {"action": "NO_TRADE", "price_at_decision": None},
                          {"price_at_decision": None}, {"price_at_decision": "541.15（收盘）"},
                          {"data_as_of": "2026-10-12（价格）；财务截至 FY2026"}):
            with self.subTest(overrides=overrides), self.assertRaises(decision_log.DecisionLogError):
                self.save(**overrides)


if __name__ == "__main__":
    unittest.main()
