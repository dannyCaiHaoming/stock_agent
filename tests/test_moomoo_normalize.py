from __future__ import annotations

import unittest

from product.mcp.live.moomoo_normalize import (
    normalize_company_profile,
    normalize_institutional_rows,
    normalize_money_flow_rows,
    normalize_option_rows,
    normalize_research_rows,
    normalize_expectation_rows,
    normalize_opend_company_profile,
    normalize_opend_capital_flow,
    normalize_opend_analyst_consensus,
    normalize_opend_morningstar_report,
    normalize_opend_institutional_aggregate,
    normalize_opend_insider_holders,
    normalize_opend_insider_trades,
    normalize_opend_option_chain,
    normalize_opend_rating_summary,
    normalize_opend_short_interest,
)


COMMON = {
    "security_id": "US:COMMON_STOCK:AAPL", "ticker": "AAPL",
    "retrieved_at": "2026-09-15T12:00:00Z", "raw_content_hash": "a" * 64,
    "source_locator": "https://www.moomoo.com/sg/research/synthetic",
}


class MoomooNormalizationTests(unittest.TestCase):
    def capture(self, *, method, payload):
        return {
            "method": method, "region": "SG", "security_market": "US",
            "security_code": "US.AAPL", "sdk_version": "10.10.7008",
            "server_version": "1010",
            "manifest_hash": "b" * 64, "retrieved_at": "2026-09-16T13:15:01Z",
            "raw_content_hash": "c" * 64, "payload": payload,
        }

    def test_profile_keeps_classification_and_current_snapshot_limitation(self):
        result = normalize_company_profile({
            "symbol": "AAPL", "legal_name": "Apple Inc.", "business_summary": "Devices and services",
            "sector": "Technology", "industry": "Consumer Electronics",
            "classification_system": "MOOMOO_VENDOR", "employees": 100,
        }, **COMMON)
        fact = result["evidence"][0]
        self.assertEqual(fact["value"]["classification_system"], "MOOMOO_VENDOR")
        self.assertIn("缺少明确时点", " ".join(fact["limitations"]))
        with self.assertRaisesRegex(ValueError, "SECURITY_MISMATCH"):
            normalize_company_profile({
                "symbol": "MSFT", "legal_name": "Microsoft", "business_summary": "Software",
            }, **COMMON)

    def test_money_flow_requires_time_unit_definition_and_keeps_provider_semantics(self):
        result = normalize_money_flow_rows([{
            "category": "large_order", "amount": "100", "currency": "USD", "unit": "USD",
            "period_start": "2026-09-15T09:30:00Z", "period_end": "2026-09-15T10:00:00Z",
            "as_of": "2026-09-15T10:00:00Z", "definition": "provider-defined large order",
            "direction_label": "net_inflow",
        }], **COMMON)
        fact = result["evidence"][0]
        self.assertEqual(fact["value"]["definition"], "provider-defined large order")
        self.assertIn("不证明", " ".join(fact["limitations"]))
        with self.assertRaisesRegex(ValueError, "FIELDS_MISSING"):
            normalize_money_flow_rows([{"category": "large_order", "amount": 1}], **COMMON)

    def test_institutional_single_period_is_explicit_and_secondary(self):
        result = normalize_institutional_rows([{
            "holder_name": "Example Manager", "report_period": "2026-06-30",
            "position": 100, "unit": "shares", "as_of": "2026-06-30T00:00:00Z",
            "published_at": "2026-08-15T00:00:00Z", "source_declaration": "Vendor cites public filing",
        }], **COMMON)
        self.assertEqual(result["coverage"], "SUPPLEMENTAL_NOT_AUTHORITATIVE")
        self.assertEqual(result["gaps"][0]["reason"], "MOOMOO_INSTITUTION_SINGLE_PERIOD_ONLY")

    def test_options_do_not_synchronize_sources_or_infer_direction(self):
        result = normalize_option_rows([{
            "contract_symbol": "AAPL261218C00100000", "option_type": "CALL",
            "expiration": "2026-12-18", "strike": 100, "bid": 4, "ask": 5,
            "volume": 10, "open_interest": 100, "as_of": "2026-09-15T10:00:00Z",
        }], **COMMON)
        self.assertEqual(result["gaps"][0]["reason"], "MOOMOO_OPTION_QUOTE_TIME_MISSING")
        self.assertIn("不得", " ".join(result["evidence"][0]["limitations"]))
        with self.assertRaisesRegex(ValueError, "CROSSED_QUOTE"):
            normalize_option_rows([{
                "contract_symbol": "X", "option_type": "PUT", "expiration": "2026-12-18",
                "strike": 100, "bid": 5, "ask": 4, "as_of": "2026-09-15T10:00:00Z",
            }], **COMMON)

    def test_research_tiers_and_full_text_permission_are_enforced(self):
        result = normalize_research_rows([{
            "title": "Synthetic report", "publisher": "Example Research",
            "published_at": "2026-09-14T10:00:00Z", "as_of": "2026-09-14T10:00:00Z",
            "content_tier": "ABSTRACT", "summary": "Public abstract",
        }], **COMMON)
        self.assertEqual(result["gaps"][0]["reason"], "RESEARCH_COMPARISON_NOT_COMPLETE")
        with self.assertRaisesRegex(ValueError, "PERMISSION_REQUIRED"):
            normalize_research_rows([{
                "title": "Private", "publisher": "Example", "published_at": "2026-09-14T10:00:00Z",
                "as_of": "2026-09-14T10:00:00Z", "content_tier": "FULL_TEXT",
            }], **COMMON)

    def test_expectations_preserve_period_basis_and_unknown_vintage(self):
        result = normalize_expectation_rows([{
            "fiscal_period": "2026-Q4", "metric": "EPS", "average": "-0.5",
            "accounting_basis": "UNKNOWN", "as_of": "2026-09-14T10:00:00Z",
        }], **COMMON)
        fact = result["evidence"][0]
        self.assertEqual(fact["value"]["fiscal_period"], "2026-Q4")
        self.assertEqual(fact["value"]["average"], "-0.5")
        self.assertIn("vintage", " ".join(fact["limitations"]))

    def test_real_opend_profile_long_form_is_bound_without_claiming_legal_name(self):
        result = normalize_opend_company_profile(self.capture(
            method="get_company_profile", payload={
                "kind": "DATAFRAME", "columns": ["name", "value", "field_type"],
                "dtypes": {}, "rows": [
                    {"name": "公司代码", "value": "AAPL", "field_type": 0},
                    {"name": "公司名称", "value": "苹果", "field_type": 0},
                    {"name": "公司简介", "value": "Devices and services", "field_type": 2},
                    {"name": "员工数量", "value": "166000", "field_type": 0},
                ],
            },
        ), security_id=COMMON["security_id"], ticker="AAPL")
        fact = result["evidence"][0]
        self.assertEqual(fact["value"]["provider_display_name"], "苹果")
        self.assertNotIn("legal_name", fact["value"])
        self.assertIn("sdk/10.10.7008", fact["source_version"])

    def test_real_opend_flow_keeps_vendor_categories_time_and_unavailable_block_flow(self):
        capture = self.capture(method="get_capital_flow", payload={
            "kind": "DATAFRAME", "columns": [
                "last_valid_time", "in_flow", "super_in_flow", "big_in_flow",
                "mid_in_flow", "sml_in_flow", "main_in_flow", "capital_flow_item_time",
            ], "dtypes": {}, "rows": [{
                "last_valid_time": "2026-09-16 09:14:44", "in_flow": 1,
                "super_in_flow": 2, "big_in_flow": 3, "mid_in_flow": 4,
                "sml_in_flow": 5, "main_in_flow": "N/A",
                "capital_flow_item_time": "2026-09-15 09:30:00",
            }, {
                "last_valid_time": "2026-09-16 09:14:44", "in_flow": 10,
                "super_in_flow": 20, "big_in_flow": 30, "mid_in_flow": 40,
                "sml_in_flow": 50, "main_in_flow": "N/A",
                "capital_flow_item_time": "2026-09-15 16:00:00",
            }],
        })
        result = normalize_opend_capital_flow(
            capture, security_id=COMMON["security_id"], ticker="AAPL",
        )
        self.assertEqual(len(result["evidence"]), 5)
        self.assertEqual(len({fact["evidence_id"] for fact in result["evidence"]}), 5)
        self.assertEqual(result["coverage"]["market_timezone"], "America/New_York")
        self.assertEqual(result["gaps"][0]["field"], "main_in_flow")
        self.assertTrue(all(fact["value"]["currency"] == "USD" for fact in result["evidence"]))

    def test_opend_flow_excludes_provider_minute_after_retrieval_for_pit(self):
        capture = self.capture(method="get_capital_flow", payload={
            "kind": "DATAFRAME", "columns": [], "dtypes": {}, "attrs": {}, "rows": [{
                "last_valid_time": "2026-09-16 09:15:30", "in_flow": 1,
                "super_in_flow": 2, "big_in_flow": 3, "mid_in_flow": 4,
                "sml_in_flow": 5, "main_in_flow": "N/A",
                "capital_flow_item_time": "2026-09-16 09:16:00",
            }],
        })
        result = normalize_opend_capital_flow(
            capture, security_id=COMMON["security_id"], ticker="AAPL",
        )
        self.assertEqual(result["evidence"], [])
        self.assertEqual(result["gaps"][0]["reason"], "MOOMOO_FLOW_NO_COMPLETED_INTERVAL")

    def test_opend_flow_uses_last_completed_bucket_and_quarantines_future_clock(self):
        capture = self.capture(method="get_capital_flow", payload={
            "kind": "DATAFRAME", "columns": [], "dtypes": {}, "attrs": {}, "rows": [{
                "last_valid_time": "2026-09-16 09:15:30", "in_flow": 1,
                "super_in_flow": 2, "big_in_flow": 3, "mid_in_flow": 4,
                "sml_in_flow": 5, "main_in_flow": "N/A",
                "capital_flow_item_time": "2026-09-16 09:15:00",
            }, {
                "last_valid_time": "2026-09-16 09:15:30", "in_flow": 10,
                "super_in_flow": 20, "big_in_flow": 30, "mid_in_flow": 40,
                "sml_in_flow": 50, "main_in_flow": "N/A",
                "capital_flow_item_time": "2026-09-16 09:16:00",
            }],
        })
        result = normalize_opend_capital_flow(
            capture, security_id=COMMON["security_id"], ticker="AAPL",
        )
        self.assertTrue(all(fact["as_of"] == "2026-09-16T13:15:00Z" for fact in result["evidence"]))
        self.assertTrue(all(fact["value"]["provider_valid_time"] is None for fact in result["evidence"]))
        reasons = {gap["reason"] for gap in result["gaps"]}
        self.assertIn("MOOMOO_FLOW_INCOMPLETE_INTERVAL_EXCLUDED", reasons)
        self.assertIn("MOOMOO_PROVIDER_CLOCK_AHEAD_OF_RETRIEVAL", reasons)

    def test_opend_flow_accepts_unavailable_provider_valid_time(self):
        capture = self.capture(method="get_capital_flow", payload={
            "kind": "DATAFRAME", "columns": [], "dtypes": {}, "attrs": {}, "rows": [{
                "last_valid_time": "N/A", "in_flow": 10,
                "super_in_flow": 20, "big_in_flow": 30, "mid_in_flow": 40,
                "sml_in_flow": 50, "main_in_flow": "N/A",
                "capital_flow_item_time": "2026-09-16 09:14:00",
            }],
        })
        result = normalize_opend_capital_flow(
            capture, security_id=COMMON["security_id"], ticker="AAPL",
        )
        self.assertEqual(len(result["evidence"]), 5)
        self.assertIsNone(result["coverage"]["last_valid_time"])
        self.assertTrue(all(
            fact["value"]["provider_valid_time"] is None
            for fact in result["evidence"]
        ))
        self.assertIn(
            "MOOMOO_PROVIDER_VALID_TIME_UNAVAILABLE",
            {gap["reason"] for gap in result["gaps"]},
        )

    def test_real_opend_consensus_is_current_opinion_not_fiscal_expectation(self):
        result = normalize_opend_analyst_consensus(self.capture(
            method="get_research_analyst_consensus", payload={"kind": "DICT", "value": {
                "highest": 400, "average": 348.19, "lowest": 245, "rating": "BUY",
                "total": 25, "update_time": 1789515001, "update_time_str": "2026-09-15",
                "buy": 60, "hold": 24, "sell": 16,
            }},
        ), security_id=COMMON["security_id"], ticker="AAPL")
        fact = result["evidence"][0]
        self.assertEqual(fact["value"]["rating"], "BUY")
        self.assertIn("FISCAL_PERIOD", result["gaps"][0]["reason"])
        self.assertIn("不是发行人指引", " ".join(fact["limitations"]))

    def test_real_opend_morningstar_content_stays_vendor_opinion_and_internal_only(self):
        result = normalize_opend_morningstar_report(self.capture(
            method="get_research_morningstar_report", payload={"kind": "DICT", "value": {
                "rating_type": "QUALITATIVE", "star_rating": 2,
                "star_update_time": 1789507200, "fair_value": 290,
                "fair_value_content": "Fair value", "economic_moat_label": "NARROW",
                "economic_moat_content": "Moat", "uncertainty_label": "MEDIUM",
                "uncertainty_content": "Uncertainty", "financial_health_content": "Health",
                "capital_allocation_label": "STANDARD", "capital_allocation_content": "Capital",
                "investment_thesis_content": "Thesis", "bull_say": "Bull", "bear_say": "Bear",
                "analyst_note_title": "Note", "analyst_note_content": "Note body",
                "analyst_report_update_time": 1788985740,
                "analyst_report_update_time_str": "2026-09-09",
            }},
        ), security_id=COMMON["security_id"], ticker="AAPL")
        fact = result["evidence"][0]
        self.assertEqual(fact["value"]["content_tier"], "LICENSED_API_CONTENT")
        self.assertIn("不声明再分发许可", " ".join(fact["limitations"]))

    def test_real_opend_institutional_rows_are_aggregate_periods_not_manager_13f(self):
        result = normalize_opend_institutional_aggregate(self.capture(
            method="get_shareholders_institutional", payload={
                "kind": "DATAFRAME", "columns": [], "dtypes": {}, "attrs": {}, "rows": [{
                    "period_text": "2026/Q2", "institution_quantity": 10,
                    "institution_quantity_change": 1, "holder_quantity": 1000,
                    "holder_quantity_change": 100, "holder_pct": 70,
                    "holder_pct_change": 1, "next_key": "-1",
                    "update_time": 1789560000, "update_time_str": "2026-09-16 08:00:00",
                }, {
                    "period_text": "2026/Q1", "institution_quantity": 9,
                    "institution_quantity_change": 0, "holder_quantity": 900,
                    "holder_quantity_change": 0, "holder_pct": 69,
                    "holder_pct_change": 0, "next_key": "-1",
                    "update_time": 1789560000, "update_time_str": "2026-09-16 08:00:00",
                }],
            },
        ), security_id=COMMON["security_id"], ticker="AAPL")
        self.assertEqual(len(result["evidence"]), 2)
        self.assertEqual(result["coverage"], "SECONDARY_VENDOR_AGGREGATE_NOT_13F")
        self.assertIn("不是逐管理人 13F", " ".join(result["evidence"][0]["limitations"]))

    def test_real_opend_insider_holders_and_trades_preserve_secondary_and_pagination_semantics(self):
        holders = normalize_opend_insider_holders(self.capture(
            method="get_insider_holder_list", payload={
                "kind": "DATAFRAME", "columns": [], "dtypes": {}, "attrs": {}, "rows": [{
                    "holder_id": 1, "holder_quantity": 100, "holder_pct": 0.1,
                    "name": "Public Person", "title": "Officer", "all_count": 1,
                    "next_key": "-1", "insider_total_count": 1,
                    "insider_bought_count": 0, "insider_sold_count": 1,
                }],
            },
        ), security_id=COMMON["security_id"], ticker="AAPL")
        self.assertEqual(holders["evidence"][0]["value"]["public_name"], "Public Person")
        self.assertIn("AS_OF_NOT_PROVIDED", holders["gaps"][0]["reason"])

        trades = normalize_opend_insider_trades(self.capture(
            method="get_insider_trade_list", payload={
                "kind": "DATAFRAME", "columns": [], "dtypes": {},
                "attrs": {"all_count": 199, "next_key": "20"}, "rows": [{
                    "trade_shares": 10, "min_trade_date": 1788796800,
                    "min_trade_date_str": "2026-09-07", "max_trade_date": 1788796800,
                    "max_trade_date_str": "2026-09-07", "min_price": 200,
                    "max_price": 200, "security_holder_quantity": 90,
                    "is_proposed_sale_of_securities": False, "holder_id": 1,
                    "name": "Public Person", "title": "Officer",
                    "security_description": "Common Stock", "transaction_type": "卖出",
                    "source_group_name": "Form 4",
                }],
            },
        ), security_id=COMMON["security_id"], ticker="AAPL")
        self.assertEqual(trades["coverage"]["all_count"], 199)
        self.assertEqual(trades["gaps"][0]["reason"], "MOOMOO_INSIDER_TRADES_MORE_PAGES")
        self.assertIn("不推断", " ".join(trades["evidence"][0]["limitations"]))

    def test_real_opend_option_chain_is_static_and_never_fills_dynamic_fields(self):
        result = normalize_opend_option_chain(self.capture(
            method="get_option_chain", payload={
                "kind": "DATAFRAME", "columns": [], "dtypes": {}, "attrs": {}, "rows": [{
                    "code": "US.AAPL260918C00250000", "name": "AAPL Call",
                    "lot_size": 100, "stock_type": "OPTION", "option_type": "CALL",
                    "stock_owner": "US.AAPL", "strike_time": "2026-09-18",
                    "strike_price": 250, "suspension": False, "stock_id": 1,
                    "index_option_type": "N/A", "expiration_cycle": "WEEK",
                    "option_standard_type": "STANDARD", "option_settlement_mode": "N/A",
                }],
            },
        ), security_id=COMMON["security_id"], ticker="AAPL")
        value = result["evidence"][0]["value"]
        self.assertEqual(value["snapshot_kind"], "STATIC_CONTRACT_CHAIN")
        self.assertIsNone(value["open_interest"])
        self.assertEqual(result["gaps"][0]["reason"], "MOOMOO_OPTION_DYNAMIC_FIELDS_UNAVAILABLE")
        with self.assertRaisesRegex(ValueError, "OPTION_FIELDS_INVALID"):
            bad = self.capture(method="get_option_chain", payload={
                "kind": "DATAFRAME", "columns": [], "dtypes": {}, "attrs": {},
                "rows": [{"stock_owner": "US.MSFT"}],
            })
            normalize_opend_option_chain(bad, security_id=COMMON["security_id"], ticker="AAPL")

    def test_real_opend_rating_summary_is_opinion_metadata_not_report_body(self):
        result = normalize_opend_rating_summary(self.capture(
            method="get_research_rating_summary", payload={"kind": "DICT", "value": {
                "inst_rating_summary_list": [{
                    "institution_info": {
                        "institution_uid": 1, "institution_name": "Research Co",
                        "institution_source_name": "Research Co",
                    },
                    "rating_item_list": [{
                        "recommendation_date": 1789448400,
                        "recommendation_date_str": "2026-09-15", "rating": "BUY",
                        "target_price": 365, "update_time": 1789482701110206,
                        "update_time_str": "2026-09-15",
                    }],
                }], "next_key": "2",
            }},
        ), security_id=COMMON["security_id"], ticker="AAPL")
        fact = result["evidence"][0]
        self.assertEqual(fact["value"]["content_tier"], "RATING_SUMMARY")
        self.assertIn("不是研报正文", " ".join(fact["limitations"]))
        self.assertEqual(result["gaps"][0]["reason"], "MOOMOO_RATING_MORE_PAGES")

    def test_real_opend_short_interest_is_not_short_volume_or_borrow_fee(self):
        result = normalize_opend_short_interest(self.capture(
            method="get_short_interest", payload={
                "kind": "DATAFRAME", "columns": [], "dtypes": {},
                "attrs": {"next_key": "-1"}, "rows": [{
                    "timestamp": 1788148800, "timestamp_str": "2026-08-31",
                    "shares_short": 100, "short_percent": 1.5,
                    "avg_daily_share_volume": 50, "days_to_cover": 2,
                    "close_price": 200, "last_close_price": 199,
                }],
            },
        ), security_id=COMMON["security_id"], ticker="AAPL")
        value = result["evidence"][0]["value"]
        self.assertEqual(value["statistic_type"], "SHORT_INTEREST")
        self.assertIsNone(value["borrow_fee"])
        self.assertIn("不得互换", " ".join(result["evidence"][0]["limitations"]))


if __name__ == "__main__":
    unittest.main()
