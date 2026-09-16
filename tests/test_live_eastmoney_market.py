"""新源价格经冻结、PIT、估值的零网络接缝。证券身份仅为合成测试输入。"""
from copy import deepcopy
from datetime import datetime, UTC
import hashlib
import json
from types import SimpleNamespace
import unittest

from product.mcp.live.eastmoney_market import normalize_record, collect_daily
from product.mcp.live.eastmoney_transport import ADAPTER_VERSION, AKSHARE_VERSION, ENDPOINT
from product.mcp.provenance import content_hash
from product.runtime.live_input import freeze_snapshot, value_portfolio
from product.runtime.evidence_gate import run_live_evidence_gate
from tests.test_live_eastmoney_contracts import access
from tests.test_live_eastmoney_transport import payload
from tests import test_live_contracts_gate as legacy_examples


class Calendar(legacy_examples.Calendar):
    def session_close(self, day):
        return {"2026-09-08": "2026-09-08T20:00:00Z", "2026-09-09": "2026-09-09T20:00:00Z"}.get(day)


class EastmoneyMarketTests(unittest.TestCase):
    def sample(self):
        raw = json.dumps(payload()).encode()
        record = {"key": {"provider": "eastmoney", "client": "akshare", "client_version": AKSHARE_VERSION,
            "adapter_version": ADAPTER_VERSION, "provider_symbol": "105.MSFT", "start": "2026-09-08", "end": "2026-09-09",
            "interval": "daily", "adjust": "", "klt": "101", "fqt": "0", "endpoint": ENDPOINT},
            "raw_content_hash": hashlib.sha256(raw).hexdigest(), "retrieved_at": "2026-09-10T00:00:00Z"}
        return record, raw

    def normalize(self, record, raw):
        return normalize_record(record, raw, security_id="TEST", provider_symbol="105.MSFT", calendar=Calendar())

    def test_facts_keep_provider_raw_time_and_unknown_actions(self):
        record, raw = self.sample()
        facts = self.normalize(record, raw)["evidence"]
        self.assertEqual([f["value"] for f in facts], ["101", "102"])
        for fact in facts:
            self.assertEqual(fact["source_type"], "eastmoney")
            self.assertEqual(fact["raw_content_hash"], record["raw_content_hash"])
            self.assertIsNone(fact["metadata"]["dividends"])
            self.assertIsNone(fact["metadata"]["stock_splits"])
            self.assertFalse(fact["metadata"]["historical_return_eligible"])
        record["retrieved_at"] = "2026-09-09T19:59:00Z"
        result = self.normalize(record, raw)
        self.assertEqual(len(result["evidence"]), 1)
        self.assertEqual(result["gaps"][0]["reason"], "NOT_COMPLETED_REGULAR_SESSION")

    def test_wrong_provider_adjustment_or_raw_fails(self):
        for changes in ({"provider": "yahoo"}, {"fqt": "1"}, {"client_version": "unknown"}):
            record, raw = self.sample(); record["key"].update(changes)
            with self.assertRaisesRegex(ValueError, "SOURCE_DRIFT"): self.normalize(record, raw)
        record, raw = self.sample()
        with self.assertRaisesRegex(ValueError, "RAW_HASH_MISMATCH"): self.normalize(record, raw+b" ")

    def test_freeze_gate_and_full_valuation_never_use_future_price(self):
        setup = legacy_examples.LiveContractGateTests(); setup.setUp()
        record, raw = self.sample()
        facts = self.normalize(record, raw)["evidence"]
        def freeze(values):
            return freeze_snapshot(snapshot_id="synthetic-eastmoney", portfolio=setup.portfolio,
                request_started_at="2026-09-10T00:00:00Z", decision_cutoff="2026-09-10T01:00:00Z",
                facts=values, source_access=[access(), access("sec")], raw_records=[], collection_events=[], gaps=[])
        snapshot = freeze(facts)
        self.assertEqual(snapshot["schema_version"], "live-snapshot/2.0.0")
        gate = run_live_evidence_gate(snapshot, run_id="eastmoney-test", calendar=Calendar()).artifact
        valuation = value_portfolio(setup.portfolio, snapshot, gate, calendar=Calendar())
        self.assertEqual(valuation["positions"][0]["price"], "102")
        self.assertEqual(valuation["total_value"], "1120")
        for field in ("as_of", "published_at", "retrieved_at"):
            bad = deepcopy(facts)
            for fact in bad: fact[field] = "2026-09-11T20:00:00Z"
            bad_snapshot = freeze(bad)
            excluded = run_live_evidence_gate(bad_snapshot, run_id="future-test", calendar=Calendar()).artifact
            self.assertEqual(excluded["allowed_evidence_ids"], [])
            with self.assertRaises(ValueError): value_portfolio(setup.portfolio, bad_snapshot, excluded, calendar=Calendar())

    def test_collection_deduplicates_and_requires_identity_before_request(self):
        record, raw = self.sample(); calls = []
        client = SimpleNamespace(requests=0, cache=SimpleNamespace(read=lambda _:raw))
        def fetch(**kwargs): calls.append(kwargs); client.requests += 1; return record
        client.fetch = fetch
        security = dict(security_id="TEST", provider_symbol="105.MSFT", currency="USD", identity_verified=True)
        result = collect_daily([security, security], start="2026-09-08", end="2026-09-09", client=client, calendar=Calendar())
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["actual_http_requests"], 1)
        for bad in (dict(security, currency="EUR"), dict(security, identity_verified=False), dict(security, quantity=10)):
            with self.assertRaises(ValueError):
                collect_daily([bad], start="2026-09-08", end="2026-09-09", client=client, calendar=Calendar())
        self.assertEqual(len(calls), 1)


if __name__ == "__main__": unittest.main()
