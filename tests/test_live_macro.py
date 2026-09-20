from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest

from product.mcp.live.macro import (
    BLS_CALENDAR_VERSION, BLS_VERSION, FED_POLICY_VERSION, TREASURY_VERSION,
    collect_official_macro_snapshot, load_research_source_policy,
    normalize_bls_calendar_ics, normalize_bls_response,
    normalize_federal_reserve_document, normalize_federal_reserve_feed,
    normalize_treasury_csv,
)
from product.mcp.live.sec_client import Response
from product.runtime.common_stock_data import merge_macro_research_evidence
from product.runtime.hashing import canonical_hash


ROOT = Path(__file__).resolve().parents[1]


class OfficialMacroTests(unittest.TestCase):
    def test_policy_is_exact_and_keyless(self):
        policy = load_research_source_policy(
            ROOT / "product/mcp/live/research-source-policy.json"
        )
        self.assertEqual(policy["sources"]["bls"]["adapter_version"], BLS_VERSION)
        self.assertEqual(policy["sources"]["treasury"]["adapter_version"], TREASURY_VERSION)
        self.assertEqual(policy["sources"]["federal_reserve"]["adapter_version"], FED_POLICY_VERSION)
        self.assertEqual(policy["sources"]["bls_calendar"]["adapter_version"], BLS_CALENDAR_VERSION)
        self.assertTrue(all(
            policy["sources"][name]["authentication"] == "none"
            for name in ("bls", "treasury", "federal_reserve", "bls_calendar")
        ))

    def test_bls_uses_retrieval_as_conservative_publication_time(self):
        raw = json.dumps({
            "status": "REQUEST_SUCCEEDED",
            "Results": {"series": [{
                "seriesID": "CUUR0000SA0",
                "data": [{"year": "2026", "period": "M08", "periodName": "August", "value": "323.5", "footnotes": []}],
            }]},
        }).encode()
        result = normalize_bls_response(
            raw, retrieved_at="2026-09-15T10:00:00Z",
            endpoint="https://api.bls.gov/publicAPI/v1/timeseries/data/",
        )
        fact = result["evidence"][0]
        self.assertEqual(fact["as_of"], "2026-08-31T00:00:00Z")
        self.assertEqual(fact["published_at"], "2026-09-15T10:00:00Z")
        self.assertFalse(fact["metadata"]["historical_vintage_available"])

    def test_treasury_preserves_observation_day_and_conservative_publication(self):
        raw = b"Date,1 Mo,10-Year\n09/14/2026,4.10,4.25\n09/15/2026,4.11,4.30\n"
        fact = normalize_treasury_csv(
            raw, retrieved_at="2026-09-15T20:00:00Z", endpoint="https://home.treasury.gov/example"
        )["evidence"][0]
        self.assertEqual(fact["value"], "4.30")
        self.assertEqual(fact["as_of"], "2026-09-15T00:00:00Z")
        self.assertEqual(fact["published_at"], "2026-09-15T20:00:00Z")

    def test_federal_reserve_policy_uses_official_publication_and_body(self):
        feed = b"""<?xml version='1.0'?><rss><channel><item>
        <title>Federal Reserve issues FOMC statement</title>
        <link>https://www.federalreserve.gov/newsevents/pressreleases/monetary20260910a.htm</link>
        <pubDate>Thu, 10 Sep 2026 18:00:00 GMT</pubDate>
        </item></channel></rss>"""
        candidate = normalize_federal_reserve_feed(
            feed, decision_cutoff="2026-09-15T00:00:00Z"
        )
        result = normalize_federal_reserve_document(
            ("<html><body><main><h1>FOMC statement</h1><p>" + "Policy text. " * 20
             + "</p></main></body></html>").encode(),
            candidate=candidate, retrieved_at="2026-09-15T10:00:00Z",
        )
        fact = result["evidence"][0]
        self.assertEqual(fact["published_at"], "2026-09-10T18:00:00Z")
        self.assertEqual(fact["metadata"]["document_kind"], "OFFICIAL_POLICY_TEXT")
        self.assertIn("Policy text", fact["value"])

    def test_bls_calendar_keeps_only_announced_bounded_events(self):
        raw = b"""BEGIN:VCALENDAR\r\nBEGIN:VEVENT\r\nUID:cpi-1\r\nDTSTART;TZID=America/New_York:20260920T083000\r\nSUMMARY:Consumer Price Index\r\nSTATUS:CONFIRMED\r\nEND:VEVENT\r\nEND:VCALENDAR\r\n"""
        fact = normalize_bls_calendar_ics(
            raw, retrieved_at="2026-09-15T10:00:00Z",
            endpoint="https://www.bls.gov/schedule/news_release/bls.ics",
            decision_cutoff="2026-09-15T10:00:00Z",
        )["evidence"][0]
        events = json.loads(fact["value"])
        self.assertEqual(events[0]["scheduled_at"], "2026-09-20T12:30:00Z")
        self.assertTrue(fact["metadata"]["announced_not_predicted"])

    def test_future_retrieval_is_really_excluded_and_source_failures_are_isolated(self):
        bls = json.dumps({
            "status": "REQUEST_SUCCEEDED",
            "Results": {"series": [{
                "seriesID": "LNS14000000",
                "data": [{"year": "2026", "period": "M08", "periodName": "August", "value": "4.2", "footnotes": []}],
            }]},
        }).encode()
        replies = iter([
            Response(200, bls), Response(503, b""), Response(503, b""),
            Response(503, b""),
        ])
        with tempfile.TemporaryDirectory() as temp:
            result = collect_official_macro_snapshot(
                policy_path=ROOT / "product/mcp/live/research-source-policy.json",
                output_path=Path(temp) / "macro.json", cache_root=Path(temp) / "cache",
                decision_cutoff="2026-09-15T09:59:59Z",
                now=lambda: datetime(2026, 9, 15, 10, 0, tzinfo=timezone.utc),
                transport=lambda request: next(replies),
            )
        self.assertEqual(result["status"], "SOURCE_LIMITED")
        self.assertEqual(len(result["excluded"]), 1)
        self.assertEqual(result["excluded"][0]["reason"], "PIT_AFTER_DECISION_CUTOFF")
        self.assertEqual(result["events"][1]["failure_code"], "TREASURY_HTTP_503")

    def test_macro_merge_preserves_shared_scope_and_snapshot_lineage(self):
        raw = json.dumps({
            "status": "REQUEST_SUCCEEDED",
            "Results": {"series": [{
                "seriesID": "LNS14000000",
                "data": [{"year": "2026", "period": "M08", "periodName": "August", "value": "4.2", "footnotes": []}],
            }]},
        }).encode()
        fact = normalize_bls_response(
            raw, retrieved_at="2026-09-15T10:00:00Z", endpoint="https://api.bls.gov/example"
        )["evidence"][0]
        macro = {
            "status": "FROZEN", "decision_cutoff": "2026-09-15T10:00:00Z",
            "evidence": [fact], "excluded": [], "gaps": [],
            "policy_hash": "a" * 64, "snapshot_hash": "b" * 64,
        }
        gate = {
            "decision_cutoff": "2026-09-14T10:00:00Z", "input_evidence_ids": [],
            "allowed_evidence": [], "allowed_evidence_ids": [], "excluded": [],
            "excluded_evidence_ids": [], "bundle_hash": "c" * 64,
        }
        prepared = {
            "gate": gate,
            "preparation": {"common_cutoff": gate["decision_cutoff"], "preparation_hash": "d" * 64},
        }
        merged = merge_macro_research_evidence(prepared, macro=macro)
        self.assertEqual(merged["gate"]["allowed_evidence_ids"], [fact["evidence_id"]])
        self.assertEqual(merged["preparation"]["official_macro"]["snapshot_hash"], "b" * 64)
        self.assertEqual(
            merged["gate"]["bundle_hash"],
            canonical_hash({key: value for key, value in merged["gate"].items() if key != "bundle_hash"}),
        )


if __name__ == "__main__":
    unittest.main()
