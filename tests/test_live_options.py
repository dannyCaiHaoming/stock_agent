from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from product.mcp.live.market import MARKET_VERSION, YFINANCE_VERSION
from product.mcp.live.options import collect_portfolio_option_snapshots, normalize_option_rows
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
