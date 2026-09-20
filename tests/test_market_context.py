from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from product.mcp.live.market_context import (
    SERIES, collect_market_context_snapshot, normalize_chart, normalize_news,
)
from product.mcp.live.sec_client import Response
from product.runtime.common_stock_data import merge_market_context_evidence
from product.runtime.hashing import canonical_hash


ROOT = Path(__file__).resolve().parents[1]


def chart_payload(timestamp: int, close: float) -> bytes:
    return json.dumps({
        "chart": {"result": [{
            "timestamp": [timestamp],
            "indicators": {"quote": [{"close": [close]}]},
        }]},
    }).encode()


class MarketContextTests(unittest.TestCase):
    def test_chart_marks_etf_proxy_and_preserves_series_role(self) -> None:
        result = normalize_chart(
            chart_payload(1789660800, 100.25), symbol="HYG",
            retrieved_at="2026-09-18T20:00:00Z",
            endpoint="https://query1.finance.yahoo.com/example",
            decision_cutoff="2026-09-19T00:00:00Z",
        )
        fact = result["evidence"][0]
        self.assertEqual(fact["security_id"], "US:MARKET:HYG")
        self.assertEqual(fact["metadata"]["series_role"], "CREDIT_HIGH_YIELD_PROXY")
        self.assertTrue(fact["metadata"]["proxy"])
        self.assertIn("not spot", fact["metadata"]["proxy_limit"])

    def test_news_is_24_hour_deduplicated_and_title_only(self) -> None:
        raw = json.dumps({"news": [
            {
                "title": "Market closes higher", "publisher": "Example",
                "link": "https://example.com/story?utm_source=yahoo",
                "providerPublishTime": 1789790400,
            },
            {
                "title": "Market closes higher", "publisher": "Example",
                "link": "https://example.com/story?other=1",
                "providerPublishTime": 1789790400,
            },
            {
                "title": "Old story", "publisher": "Example",
                "link": "https://example.com/old",
                "providerPublishTime": 1789600000,
            },
        ]}).encode()
        result = normalize_news(
            raw, retrieved_at="2026-09-19T14:00:00Z",
            endpoint="https://query1.finance.yahoo.com/v1/finance/search",
            decision_cutoff="2026-09-19T14:00:00Z",
        )
        self.assertEqual(len(result["evidence"]), 1)
        value = json.loads(result["evidence"][0]["value"])
        self.assertEqual(value["content_tier"], "TITLE_ONLY")
        self.assertEqual(value["original_url"], "https://example.com/story")

    def test_one_series_failure_does_not_block_other_series_or_news(self) -> None:
        cutoff = datetime(2026, 9, 19, 14, 0, tzinfo=timezone.utc)
        timestamp = int(datetime(2026, 9, 18, 20, 0, tzinfo=timezone.utc).timestamp())
        responses = []
        for index, _symbol in enumerate(SERIES):
            responses.append(Response(503, b"") if index == 1 else Response(200, chart_payload(timestamp, 100 + index)))
        responses.append(Response(200, json.dumps({"news": []}).encode()))
        iterator = iter(responses)
        with tempfile.TemporaryDirectory() as temp:
            snapshot = collect_market_context_snapshot(
                policy_path=ROOT / "product/mcp/live/research-source-policy.json",
                output_path=Path(temp) / "market.json", cache_root=Path(temp) / "cache",
                decision_cutoff="2026-09-19T14:00:00Z", now=lambda: cutoff,
                transport=lambda _request: next(iterator),
            )
        self.assertEqual(snapshot["status"], "FROZEN")
        self.assertTrue(snapshot["evidence"])
        self.assertIn({"dataset": "series:XLC", "reason": "MARKET_CONTEXT_CHART_HTTP_503"}, snapshot["gaps"])
        self.assertIn({"reason": "MARKET_NEWS_WINDOW_EMPTY", "window_hours": 24}, snapshot["gaps"])

    def test_market_context_merges_into_formal_gate_with_snapshot_lineage(self) -> None:
        fact = normalize_chart(
            chart_payload(1789660800, 100.25), symbol="SPY",
            retrieved_at="2026-09-18T20:00:00Z",
            endpoint="https://query1.finance.yahoo.com/example",
            decision_cutoff="2026-09-19T00:00:00Z",
        )["evidence"][0]
        prepared = {
            "gate": {
                "decision_cutoff": "2026-09-18T19:00:00Z",
                "input_evidence_ids": [], "allowed_evidence": [],
                "allowed_evidence_ids": [], "bundle_hash": "a" * 64,
            },
            "preparation": {"common_cutoff": "2026-09-18T19:00:00Z", "preparation_hash": "b" * 64},
        }
        snapshot = {
            "status": "FROZEN", "decision_cutoff": "2026-09-18T20:00:00Z",
            "adapter_version": "yahoo-public-market-context/1.0.0",
            "snapshot_hash": "c" * 64, "evidence": [fact], "gaps": [],
        }
        merged = merge_market_context_evidence(prepared, market_context=snapshot)
        self.assertEqual(merged["gate"]["allowed_evidence_ids"], [fact["evidence_id"]])
        self.assertEqual(merged["preparation"]["market_context"]["snapshot_hash"], "c" * 64)
        self.assertEqual(
            merged["gate"]["bundle_hash"],
            canonical_hash({key: value for key, value in merged["gate"].items() if key != "bundle_hash"}),
        )

    def test_live_snapshot_cutoff_covers_actual_retrieval_completion(self) -> None:
        current = datetime(2026, 9, 19, 14, 0, tzinfo=timezone.utc)
        timestamp = int(datetime(2026, 9, 18, 20, 0, tzinfo=timezone.utc).timestamp())

        def now():
            nonlocal current
            value = current
            current = current.replace(microsecond=current.microsecond + 1)
            return value

        responses = [Response(200, chart_payload(timestamp, 100.0)) for _ in SERIES]
        responses.append(Response(200, json.dumps({"news": []}).encode()))
        iterator = iter(responses)
        with tempfile.TemporaryDirectory() as temp:
            snapshot = collect_market_context_snapshot(
                policy_path=ROOT / "product/mcp/live/research-source-policy.json",
                output_path=Path(temp) / "market.json", cache_root=Path(temp) / "cache",
                now=now, transport=lambda _request: next(iterator),
            )
        self.assertGreaterEqual(
            datetime.fromisoformat(snapshot["decision_cutoff"].replace("Z", "+00:00")),
            max(
                datetime.fromisoformat(item["retrieved_at"].replace("Z", "+00:00"))
                for item in snapshot["evidence"]
            ),
        )
        self.assertGreaterEqual(
            datetime.fromisoformat(snapshot["decision_cutoff"].replace("Z", "+00:00")),
            max(
                datetime.fromisoformat(item["completed_at"].replace("Z", "+00:00"))
                for item in snapshot["events"]
            ),
        )

    def test_timeout_rate_limit_auth_and_field_drift_are_dataset_local(self) -> None:
        cutoff = datetime(2026, 9, 19, 14, 0, tzinfo=timezone.utc)
        timestamp = int(datetime(2026, 9, 18, 20, 0, tzinfo=timezone.utc).timestamp())
        calls = 0

        def transport(_request):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ValueError("MARKET_CONTEXT_TRANSPORT_FAILURE")
            if calls == 2:
                return Response(429, b"")
            if calls == 3:
                return Response(200, b"{}")
            if calls == 4:
                return Response(401, b"")
            if calls == len(SERIES) + 1:
                return Response(403, b"")
            return Response(200, chart_payload(timestamp, 100 + calls))

        with tempfile.TemporaryDirectory() as temp:
            snapshot = collect_market_context_snapshot(
                policy_path=ROOT / "product/mcp/live/research-source-policy.json",
                output_path=Path(temp) / "market.json", cache_root=Path(temp) / "cache",
                decision_cutoff="2026-09-19T14:00:00Z", now=lambda: cutoff,
                transport=transport,
            )
        reasons = {item["reason"] for item in snapshot["gaps"]}
        self.assertEqual(snapshot["status"], "FROZEN")
        self.assertTrue({
            "MARKET_CONTEXT_TRANSPORT_FAILURE", "MARKET_CONTEXT_CHART_HTTP_429",
            "MARKET_CONTEXT_CHART_INVALID", "MARKET_CONTEXT_CHART_HTTP_401",
            "MARKET_NEWS_HTTP_403",
        } <= reasons)
        self.assertTrue(snapshot["evidence"])


if __name__ == "__main__":
    unittest.main()
