from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from product.mcp.live.market import MARKET_VERSION, YFINANCE_VERSION
from product.mcp.live.options import (
    _parse_option_wire, collect_option_snapshot, collect_portfolio_option_snapshots,
    normalize_option_rows, select_option_contract_evidence, select_option_expirations,
)
from product.runtime.common_stock_data import merge_option_research_evidence


class OptionSnapshotTests(unittest.TestCase):
    def test_snapshot_preserves_volume_open_interest_spread_and_time(self):
        rows = [{
            "contractSymbol": "TEST261218C00100000", "strike": 100,
            "lastPrice": 4.5, "bid": 4.4, "ask": 4.6,
            "volume": 12, "openInterest": 120, "impliedVolatility": 0.35,
            "inTheMoney": False, "lastTradeDate": "2026-09-14T19:20:00Z",
        }]
        fact = normalize_option_rows(
            rows, security_id="US:COMMON_STOCK:TEST", ticker="TEST",
            expiration="2026-12-18", option_type="CALL",
            retrieved_at="2026-09-15T20:00:00Z", raw_content_hash="a" * 64,
        )["evidence"][0]
        self.assertEqual(fact["value"]["volume"], "12")
        self.assertEqual(fact["value"]["open_interest"], "120")
        self.assertEqual(fact["value"]["bid"], "4.4")
        self.assertEqual(fact["value"]["ask"], "4.6")
        self.assertTrue(fact["metadata"]["snapshot_only"])
        self.assertFalse(fact["metadata"]["trade_direction_available"])
        self.assertEqual(fact["value"]["quote_observed_at"], "2026-09-15T20:00:00Z")
        self.assertEqual(fact["metadata"]["greeks_status"], "PARTIAL")

    def test_expired_or_crossed_quote_is_not_accepted(self):
        expired = normalize_option_rows(
            [], security_id="TEST", ticker="TEST", expiration="2025-01-01",
            option_type="PUT", retrieved_at="2026-09-15T20:00:00Z", raw_content_hash="b" * 64,
        )
        self.assertEqual(expired["gaps"][0]["reason"], "OPTION_EXPIRATION_PASSED")
        with self.assertRaisesRegex(ValueError, "CROSSED_QUOTE"):
            normalize_option_rows(
                [{"contractSymbol": "X", "strike": 1, "bid": 2, "ask": 1}],
                security_id="TEST", ticker="TEST", expiration="2026-12-18",
                option_type="PUT", retrieved_at="2026-09-15T20:00:00Z",
                raw_content_hash="c" * 64,
            )

    def test_missing_quote_is_explicit_and_not_converted_to_flow(self):
        result = normalize_option_rows(
            [{"contractSymbol": "X", "strike": 1, "volume": 5, "openInterest": 9}],
            security_id="TEST", ticker="TEST", expiration="2026-12-18",
            option_type="PUT", retrieved_at="2026-09-15T20:00:00Z",
            raw_content_hash="d" * 64,
        )
        self.assertEqual(result["gaps"][0]["reason"], "OPTION_QUOTE_SIDE_MISSING")
        self.assertNotIn("flow", result["evidence"][0]["value"])
        self.assertTrue(any(item["reason"] == "OPTION_MULTIPLIER_MISSING" for item in result["gaps"]))
        self.assertTrue(any(item["reason"] == "OPTION_GREEKS_MISSING" for item in result["gaps"]))

    def test_reported_multiplier_and_greeks_are_preserved_not_inferred(self):
        result = normalize_option_rows(
            [{
                "contractSymbol": "TEST261218C00100000", "strike": 100,
                "bid": 4, "ask": 5, "contractSize": "REGULAR", "contractMultiplier": 100,
                "delta": 0.5, "gamma": 0.02, "theta": 0.03, "vega": 0.1, "rho": 0.01,
            }],
            security_id="TEST", ticker="TEST", expiration="2026-12-18",
            option_type="CALL", retrieved_at="2026-09-15T20:00:00Z",
            raw_content_hash="f" * 64,
        )
        fact = result["evidence"][0]
        self.assertEqual(fact["value"]["contract_multiplier"], "100")
        self.assertEqual(fact["value"]["greeks"]["delta"], "0.5")
        self.assertEqual(fact["metadata"]["greeks_status"], "REPORTED_NOT_RECALCULATED")
        self.assertFalse(any(item["reason"] == "OPTION_MULTIPLIER_MISSING" for item in result["gaps"]))

    def test_future_last_trade_and_zero_multiplier_fail_closed(self):
        base = {"contractSymbol": "TEST261218C00100000", "strike": 100, "bid": 4, "ask": 5}
        with self.assertRaisesRegex(ValueError, "LAST_TRADE_IN_FUTURE"):
            normalize_option_rows(
                [dict(base, lastTradeDate="2026-09-16T00:00:00Z")], security_id="TEST",
                ticker="TEST", expiration="2026-12-18", option_type="CALL",
                retrieved_at="2026-09-15T20:00:00Z", raw_content_hash="a" * 64,
            )
        with self.assertRaisesRegex(ValueError, "MULTIPLIER_INVALID"):
            normalize_option_rows(
                [dict(base, contractMultiplier=0)], security_id="TEST", ticker="TEST",
                expiration="2026-12-18", option_type="CALL",
                retrieved_at="2026-09-15T20:00:00Z", raw_content_hash="a" * 64,
            )

    def test_bounded_wire_parser_binds_underlying_dates_and_dynamic_fields(self):
        raw = json.dumps({"optionChain": {"error": None, "result": [{
            "underlyingSymbol": "AAPL",
            "quote": {
                "symbol": "AAPL", "quoteType": "EQUITY", "regularMarketPrice": 250,
            },
            "expirationDates": [1797552000, 1798156800],
            "options": [{
                "expirationDate": 1797552000,
                "calls": [{
                    "contractSymbol": "AAPL261218C00100000", "strike": 100,
                    "lastTradeDate": 1797000000, "bid": 4, "ask": 5,
                    "volume": 12, "openInterest": 120, "impliedVolatility": 0.3,
                }],
                "puts": [],
            }],
        }]}}).encode()
        parsed = _parse_option_wire(raw, ticker="AAPL")
        self.assertEqual(parsed["expiration"], "2026-12-18")
        self.assertEqual(parsed["calls"][0]["lastTradeDate"], "2026-12-11T14:40:00Z")
        self.assertEqual(parsed["calls"][0]["openInterest"], 120)
        self.assertEqual(parsed["underlying_price"], "250")
        body = json.loads(raw)
        body["optionChain"]["result"][0]["underlyingSymbol"] = "MSFT"
        with self.assertRaisesRegex(ValueError, "SECURITY_MISMATCH"):
            _parse_option_wire(json.dumps(body).encode(), ticker="AAPL")

    def test_expiry_selector_replaces_farthest_non_holding_expiry(self):
        selected = select_option_expirations(
            ["2026-09-25", "2026-10-16", "2026-12-18", "2027-06-18"],
            decision_date="2026-09-20",
            held_contracts=["US.AAPL270618C00100000"],
        )
        self.assertEqual(
            selected["selected_expirations"],
            ["2026-09-25", "2026-10-16", "2027-06-18"],
        )
        self.assertEqual(selected["held_expirations_missing"], [])
        shortage = select_option_expirations(
            ["2026-09-25"], decision_date="2026-09-20",
        )
        self.assertEqual(shortage["selected_expirations"], ["2026-09-25"])

    def test_contract_selector_deduplicates_atm_and_never_expands_holding_budget(self):
        evidence = []
        for option_type, letter in (("CALL", "C"), ("PUT", "P")):
            for strike in range(90, 111, 2):
                symbol = f"AAPL261218{letter}{strike * 1000:08d}"
                evidence.append({"value": {
                    "contract_symbol": symbol, "option_type": option_type,
                    "expiration": "2026-12-18", "strike": str(strike),
                }})
        selected = select_option_contract_evidence(
            evidence, underlying_price=100, decision_date="2026-09-20",
        )
        self.assertEqual(selected["selected_count"], 14)
        self.assertEqual(
            len(selected["selected_contract_symbols"]),
            len(set(selected["selected_contract_symbols"])),
        )
        with self.assertRaisesRegex(ValueError, "UNDERLYING_PRICE_INVALID"):
            select_option_contract_evidence(
                evidence, underlying_price=None, decision_date="2026-09-20",
            )

        held_evidence = []
        held = []
        for strike in range(100, 149):
            symbol = f"AAPL261218C{strike * 1000:08d}"
            held.append(symbol)
            held_evidence.append({"value": {
                "contract_symbol": symbol, "option_type": "CALL",
                "expiration": "2026-12-18", "strike": str(strike),
            }})
        over_budget = select_option_contract_evidence(
            held_evidence, underlying_price=100, decision_date="2026-09-20",
            held_contracts=held,
        )
        self.assertEqual(over_budget["selected_count"], 48)
        self.assertEqual(len(over_budget["held_contracts_missing"]), 1)

    def test_yahoo_main_collector_selects_representative_near_money_contracts(self):
        class Frame:
            def __init__(self, rows):
                self.rows = rows
            def to_dict(self, orient):
                self.assert_orient = orient
                return list(self.rows)

        class Target:
            options = ("2026-09-25", "2026-10-16", "2026-12-18", "2027-06-18")
            fast_info = {"last_price": 100}
            def option_chain(self, expiration):
                suffix = datetime.fromisoformat(expiration).strftime("%y%m%d")
                def rows(letter):
                    return [{
                        "contractSymbol": f"AAPL{suffix}{letter}{strike * 1000:08d}",
                        "strike": strike, "bid": 1, "ask": 2,
                    } for strike in range(91, 110, 2)]
                return SimpleNamespace(calls=Frame(rows("C")), puts=Frame(rows("P")))

        access = {
            "schema_version": "live-source-access/3.0.0", "provider": "yahoo",
            "data_role": "primary_market", "client_version": f"yfinance/{YFINANCE_VERSION}",
            "adapter_version": MARKET_VERSION, "status": "AUTHORIZED",
            "purpose": "personal-research", "terms_url": "https://example.test/terms",
            "checked_at": "2026-09-14T00:00:00Z", "free_features": ["synthetic"],
            "limitations": ["synthetic"], "domains": ["query2.finance.yahoo.com"],
            "request_budget": 4,
        }
        session = SimpleNamespace(live_boundary=SimpleNamespace(events=[]))
        with patch("product.mcp.live.options.version", return_value=YFINANCE_VERSION):
            result = collect_option_snapshot(
                security_id="US:COMMON_STOCK:AAPL", ticker="AAPL",
                source_access=access, session=session,
                retrieved_at=lambda: datetime(2026, 9, 20, 12, tzinfo=timezone.utc),
                ticker_factory=lambda ticker, session: Target(),
                held_contracts=["AAPL270618C00101000"],
            )
        self.assertEqual(result["expirations"], [
            "2026-09-25", "2026-10-16", "2027-06-18",
        ])
        self.assertLessEqual(len(result["evidence"]), 48)
        self.assertIn(
            "AAPL270618C00101000",
            {item["value"]["contract_symbol"] for item in result["evidence"]},
        )
        coverage = next(
            item for item in result["gaps"]
            if item["reason"] == "YAHOO_OPTION_SELECTION_COVERAGE"
        )
        self.assertEqual(coverage["available_expiration_count"], 4)
        self.assertEqual(coverage["held_contracts_missing"], [])

    def test_portfolio_collection_isolates_security_failure_and_merge_keeps_scope(self):
        access = [{
            "schema_version": "live-source-access/3.0.0", "provider": "yahoo",
            "data_role": "primary_market", "client_version": f"yfinance/{YFINANCE_VERSION}",
            "adapter_version": MARKET_VERSION, "status": "AUTHORIZED",
            "purpose": "personal-research", "terms_url": "https://example.test/terms",
            "checked_at": "2026-09-14T00:00:00Z", "free_features": ["synthetic"],
            "limitations": ["synthetic"], "domains": ["query2.finance.yahoo.com"],
            "request_budget": 2,
        }]
        fact = normalize_option_rows(
            [{"contractSymbol": "AAPL261218C00100000", "strike": 100, "bid": 4, "ask": 5}],
            security_id="US:COMMON_STOCK:AAPL", ticker="AAPL", expiration="2026-12-18",
            option_type="CALL", retrieved_at="2026-09-15T10:00:00Z", raw_content_hash="e" * 64,
        )["evidence"][0]
        class Session:
            def __init__(self):
                self.live_boundary = SimpleNamespace(option_records=[], events=[])
            def close(self):
                pass
        def collector(**kwargs):
            if kwargs["ticker"] == "MSFT":
                raise ValueError("YAHOO_HTTP_503")
            return {"status": "FROZEN", "evidence": [fact], "gaps": [], "expirations": ["2026-12-18"]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            access_path = root / "access.json"
            access_path.write_text(json.dumps(access), encoding="utf-8")
            snapshot = collect_portfolio_option_snapshots(
                securities=[
                    {"security_id": "US:COMMON_STOCK:AAPL", "ticker": "AAPL"},
                    {"security_id": "US:COMMON_STOCK:MSFT", "ticker": "MSFT"},
                ],
                access_path=access_path, output_path=root / "options.json",
                state_root=root / "state", cache_root=root / "cache",
                now=lambda: datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc),
                session_factory=lambda *args, **kwargs: Session(), option_collector=collector,
            )
        self.assertEqual(snapshot["status"], "FROZEN")
        self.assertEqual(len(snapshot["evidence"]), 1)
        self.assertEqual(snapshot["gaps"][0]["security_id"], "US:COMMON_STOCK:MSFT")
        prepared = {
            "gate": {"decision_cutoff": "2026-09-14T00:00:00Z", "input_evidence_ids": [],
                     "allowed_evidence": [], "allowed_evidence_ids": [], "bundle_hash": "a" * 64},
            "preparation": {"common_cutoff": "2026-09-14T00:00:00Z", "preparation_hash": "b" * 64},
        }
        merged = merge_option_research_evidence(prepared, options=snapshot)
        self.assertEqual(merged["gate"]["allowed_evidence_ids"], [fact["evidence_id"]])
        self.assertEqual(merged["preparation"]["options"]["status"], "FROZEN")


if __name__ == "__main__":
    unittest.main()
