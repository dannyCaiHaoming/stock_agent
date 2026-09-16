from __future__ import annotations

from copy import deepcopy
import unittest

from product.mcp.live.peer_candidates import (
    build_peer_candidate_pool,
    validate_peer_candidate_pool,
)
from product.mcp.provenance import content_hash


def universe():
    base = {
        "schema_version": "live-universe/1.0.0", "provider": "nasdaq",
        "source_id": "nasdaq-screener",
        "source_locator": "https://api.nasdaq.com/api/screener/stocks",
        "request_started_at": "2026-09-15T01:00:00Z",
        "as_of": "2026-09-15T01:00:01Z", "retrieved_at": "2026-09-15T01:00:01Z",
        "completeness": "COMPLETE",
    }
    rows = []
    for symbol, name, cap, industry in (
        ("MRVL", "Marvell Technology Inc.", "100", "Semiconductors"),
        ("AVGO", "Broadcom Inc.", "180", "Semiconductors"),
        ("NVDA", "NVIDIA Corporation", "300", "Semiconductors"),
        ("TESTW", "Test Warrants", "90", "Semiconductors"),
        ("MSFT", "Microsoft Corporation", "500", "Software"),
    ):
        rows.append({
            "symbol": symbol, "name": name, "market_cap": cap,
            "country": "United States", "ipo_year": 2000,
            "sector": "Technology", "industry": industry,
            "source_id": "nasdaq-screener", "as_of": base["as_of"],
            "retrieved_at": base["retrieved_at"], "raw_content_hash": "a" * 64,
        })
    base["rows"] = rows
    base["snapshot_hash"] = content_hash({"rows": rows, "as_of": base["as_of"]})
    return base


class PeerCandidateTests(unittest.TestCase):
    def test_pool_is_candidate_only_and_does_not_pick_peer(self):
        pool = build_peer_candidate_pool(
            [{"security_id": "US:COMMON_STOCK:MRVL", "ticker": "MRVL"}],
            universe=universe(), max_candidates_per_holding=2,
        )
        group = pool["groups"][0]
        self.assertEqual(group["status"], "READY")
        self.assertEqual(group["match_basis"], "industry")
        self.assertEqual([item["symbol"] for item in group["candidates"]], ["AVGO", "NVDA"])
        self.assertTrue(all(item["candidate_only"] for item in group["candidates"]))
        self.assertTrue(all(item["selection_authority"] == "LLM_REQUIRED" for item in group["candidates"]))
        self.assertNotIn("TESTW", [item["symbol"] for item in group["candidates"]])
        validate_peer_candidate_pool(pool)

    def test_partial_universe_and_missing_holding_fail_closed(self):
        partial = universe()
        partial["completeness"] = "PARTIAL"
        pool = build_peer_candidate_pool(
            [{"security_id": "US:COMMON_STOCK:MRVL", "ticker": "MRVL"}],
            universe=partial,
        )
        self.assertEqual(pool["groups"][0]["gaps"], ["UNIVERSE_NOT_COMPLETE"])
        missing = build_peer_candidate_pool(
            [{"security_id": "US:COMMON_STOCK:ALB", "ticker": "ALB"}],
            universe=universe(),
        )
        self.assertEqual(missing["groups"][0]["gaps"], ["HOLDING_NOT_IN_DIRECTORY"])

    def test_hash_and_authority_tampering_are_rejected(self):
        pool = build_peer_candidate_pool(
            [{"security_id": "US:COMMON_STOCK:MRVL", "ticker": "MRVL"}],
            universe=universe(),
        )
        bad = deepcopy(pool)
        bad["groups"][0]["candidates"][0]["selection_authority"] = "PYTHON_SELECTED"
        bad["pool_hash"] = content_hash({k: v for k, v in bad.items() if k != "pool_hash"})
        with self.assertRaisesRegex(ValueError, "AUTHORITY"):
            validate_peer_candidate_pool(bad)
        bad = deepcopy(pool)
        bad["pool_hash"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "HASH"):
            validate_peer_candidate_pool(bad)


if __name__ == "__main__":
    unittest.main()
