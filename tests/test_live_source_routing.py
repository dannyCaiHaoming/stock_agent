"""纯数据路由测试；不运行模型，也不访问行情服务。"""
from copy import deepcopy
from datetime import datetime, timedelta, UTC
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from product.mcp.live.cache import SnapshotCache
from product.mcp.live.contracts import validate_contract
from product.mcp.live.market import normalize_daily_rows
from product.mcp.live.source_routing import (
    LEGACY_POLICY_LOCK, collect_selected_market, provider_versions, validate_selection,
)
from product.mcp.provenance import content_hash
from tests.test_live_yahoo_transport import access as yahoo_access

NOW = datetime(2026, 9, 10, tzinfo=UTC)


class Calendar:
    version, content_hash = "synthetic", "c" * 64

    def session_close(self, day):
        return day + "T20:00:00Z"

    def completed_sessions(self, cutoff):
        return ["2026-09-08T20:00:00Z", "2026-09-09T20:00:00Z"]


class RoutingTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.cache = SnapshotCache(Path(temp.name))
        self.access = {}
        for provider, versions in provider_versions().items():
            self.access[provider] = dict(yahoo_access(), schema_version="live-source-access/3.0.0",
                provider=provider, client_version=versions[0], adapter_version=versions[1],
                data_role="primary_market" if provider == "yahoo" else "backup_market")
            if provider == "eastmoney":
                self.access[provider]["domains"] = ["63.push2his.eastmoney.com"]
        self.primary = Mock(return_value=self.market("yahoo"))
        self.backup = Mock(return_value=self.market("eastmoney"))

    def market(self, provider, day="2026-09-09"):
        record = self.cache.store({"provider": provider, "day": day}, provider.encode(),
                                  retrieved_at="2026-09-10T00:00:00Z")
        fact = normalize_daily_rows([{"date": day, "close": 100}], security_id="TEST", ticker="TEST",
            retrieved_at=record["retrieved_at"], raw_content_hash=record["raw_content_hash"],
            calendar=Calendar(), currency="USD")["evidence"][0]
        if provider == "eastmoney":
            fact.update(schema_version="live-fact/2.0.0", source_type="eastmoney", source_id="eastmoney-daily",
                        source_version="/".join(provider_versions()[provider]))
        return {"evidence": [fact], "records": {"TEST": record}, "gaps": []}

    def run_route(self):
        return collect_selected_market(security_id="TEST", start="2026-09-01", end="2026-09-10",
            access=self.access, fetchers={"yahoo": self.primary, "eastmoney": self.backup},
            cache=self.cache, calendar=Calendar(), now=lambda: NOW)

    def test_primary_success_no_backup_and_binding(self):
        r = self.run_route()
        self.assertEqual(r["selection"]["selected_provider"], "yahoo")
        self.backup.assert_not_called()
        validate_selection(r["selection"], r["market"]["evidence"])

    def test_research_window_extends_to_550_days_without_invalidating_old_lock(self):
        start = (NOW.date() - timedelta(days=550)).isoformat()
        current = collect_selected_market(
            security_id="TEST", start=start, end="2026-09-11",
            access=self.access, fetchers={"yahoo": self.primary, "eastmoney": self.backup},
            cache=self.cache, calendar=Calendar(), now=lambda: NOW,
        )["selection"]
        self.assertEqual(current["window"]["start"], start)
        validate_selection(current)

        legacy = deepcopy(self.run_route()["selection"])
        legacy["routing_policy"] = LEGACY_POLICY_LOCK
        legacy["selection_hash"] = content_hash({
            key: value for key, value in legacy.items() if key != "selection_hash"
        })
        validate_selection(legacy)

    def test_transient_failures_allow_one_backup(self):
        for error in ("YAHOO_TRANSPORT_FAILURE", "YAHOO_HTTP_500", "YAHOO_HTTP_502", "YAHOO_HTTP_503", "YAHOO_HTTP_504"):
            self.primary.side_effect = ValueError(error)
            self.backup.reset_mock()
            r = self.run_route()
            self.assertEqual(r["selection"]["selected_provider"], "eastmoney")
            self.assertEqual(r["selection"]["attempts"][0]["failure_code"], error)
            self.backup.assert_called_once()

    def test_denial_identity_integrity_unknown_error_never_fallback(self):
        for error in ("YAHOO_HTTP_401", "YAHOO_HTTP_403", "YAHOO_HTTP_429", "YAHOO_ENDPOINT_NOT_AUTHORIZED",
                      "YAHOO_METADATA_HASH_MISMATCH", "SEC_YAHOO_EXCHANGE_CONFLICT", "UNRECOGNIZED_ERROR"):
            self.primary.side_effect = ValueError(error)
            r = self.run_route()
            self.assertEqual(r["status"], "FAILED")
            self.assertEqual(r["failure_code"], error)
            self.backup.assert_not_called()

    def test_empty_and_stale_primary_choose_whole_backup(self):
        for primary in ({"evidence": [], "records": {}, "gaps": []}, self.market("yahoo", "2026-09-01")):
            self.primary.return_value = primary
            r = self.run_route()
            self.assertEqual(r["market"], self.backup.return_value)
            self.assertEqual(r["selection"]["selected_provider"], "eastmoney")

    def test_both_missing_is_failure_not_fake_decision(self):
        self.primary.return_value = self.backup.return_value = {"evidence": [], "records": {}, "gaps": []}
        r = self.run_route()
        self.assertEqual(r["status"], "FAILED")
        self.assertIsNone(r["selection"]["selected_provider"])
        self.assertEqual(r["selection"]["evidence_ids"], [])
        self.assertNotIn("action", r)

    def test_stale_primary_raw_is_retained_but_not_used_as_evidence(self):
        self.primary.return_value = self.market("yahoo", "2026-09-01")
        r = self.run_route()
        self.assertEqual({record["key"]["provider"] for record in r["audit_records"].values()},
                         {"yahoo", "eastmoney"})
        self.assertEqual({f["source_type"] for f in r["market"]["evidence"]}, {"eastmoney"})
        self.assertEqual(r["selection"]["raw_hashes"],
                         sorted({f["raw_content_hash"] for f in self.backup.return_value["evidence"]}))

    def test_source_approval_missing_no_requests(self):
        self.access["yahoo"]["status"] = "UNCONFIRMED"
        r = self.run_route()
        self.assertEqual(r["failure_code"], "LIVE_SOURCE_NOT_AUTHORIZED")
        self.primary.assert_not_called()
        self.backup.assert_not_called()

    def test_backup_approval_missing_after_allowed_failure(self):
        self.primary.side_effect = ValueError("YAHOO_HTTP_503")
        self.access["eastmoney"]["status"] = "UNCONFIRMED"
        self.assertEqual(self.run_route()["failure_code"], "LIVE_SOURCE_NOT_AUTHORIZED")
        self.backup.assert_not_called()

    def test_future_unknown_duplicate_mixed_refs_are_fatal(self):
        for kind in ("future", "unknown", "duplicate", "mixed", "wrong_security", "retrieval"):
            bad = deepcopy(self.primary.return_value)
            fact = bad["evidence"][0]
            if kind == "future": fact["published_at"] = "2027-01-01T00:00:00Z"
            elif kind == "unknown": fact["raw_content_hash"] = "0" * 64
            elif kind == "duplicate": bad["evidence"].append(deepcopy(fact))
            elif kind == "mixed": bad["evidence"].extend(self.backup.return_value["evidence"])
            elif kind == "wrong_security": fact["security_id"] = "OTHER"
            else: fact["retrieved_at"] = "2026-09-09T23:00:00Z"
            self.primary.return_value = bad
            with self.subTest(kind=kind):
                self.assertEqual(self.run_route()["status"], "FAILED")
                self.backup.assert_not_called()
            self.primary.return_value = self.market("yahoo")

    def test_rehashed_illegal_fallback_or_changed_ids_rejected(self):
        self.primary.side_effect = ValueError("YAHOO_HTTP_503")
        r = self.run_route()
        bad = deepcopy(r["selection"])
        bad["attempts"][0]["failure_code"] = "YAHOO_HTTP_429"
        bad["selection_hash"] = content_hash({k: v for k, v in bad.items() if k != "selection_hash"})
        with self.assertRaisesRegex(ValueError, "FALLBACK_FORBIDDEN"):
            validate_contract("source-selection", bad)
        bad = deepcopy(r["selection"])
        bad["evidence_ids"] = ["nonexistent"]
        bad["selection_hash"] = content_hash({k: v for k, v in bad.items() if k != "selection_hash"})
        with self.assertRaisesRegex(ValueError, "EVIDENCE_MISMATCH"):
            validate_selection(bad, r["market"]["evidence"])

    def test_versions_rejected_before_callbacks(self):
        self.access["yahoo"]["client_version"] = "unknown"
        with self.assertRaisesRegex(ValueError, "VERSION_MISMATCH"):
            self.run_route()
        self.primary.assert_not_called()
        self.backup.assert_not_called()

    def test_access_contract_rejects_role_domain_version_and_trial_drift(self):
        for field, value in (("data_role", "disclosure"), ("domains", ["*.com"]),
                             ("adapter_version", "unknown"), ("purpose", "TECHNICAL_TRIAL")):
            bad = dict(self.access["eastmoney"], **{field: value})
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_contract("source-access", bad)

    def test_stale_price_cannot_hide_version_integrity_failure_by_fallback(self):
        self.primary.return_value = self.market("yahoo", "2026-09-01")
        self.primary.return_value["evidence"][0]["source_version"] = "unknown"
        result = self.run_route()
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failure_code"], "LIVE_SELECTION_FACT_VERSION_MISMATCH")
        self.backup.assert_not_called()

    def snapshot(self):
        from tests.test_live_contracts_gate import LiveContractGateTests
        from tests.test_live_nasdaq import access, page
        from product.mcp.live.nasdaq import NasdaqClient
        from product.runtime.live_input import freeze_snapshot
        inputs = LiveContractGateTests()
        inputs.setUp()
        self.primary.side_effect = ValueError("YAHOO_HTTP_503")
        routed = self.run_route()
        universe = NasdaqClient(access(), self.cache, transport=lambda *a, **k: page(["TEST"], 1),
                                now=lambda: NOW, sleep=lambda _: None).collect()
        from product.mcp.live.sec_client import CLIENT_VERSION
        from product.mcp.live.sec import ADAPTER_VERSION
        sec = dict(yahoo_access(), schema_version="live-source-access/3.0.0", provider="sec", data_role="disclosure",
                   client_version=CLIENT_VERSION, adapter_version=ADAPTER_VERSION,
                   domains=["data.sec.gov", "www.sec.gov"])
        records = [*routed["market"]["records"].values(), *[p["record"] for p in universe["pages"]]]
        snapshot = freeze_snapshot(snapshot_id="synthetic-routed", portfolio=inputs.portfolio,
            request_started_at="2026-09-10T00:00:00Z", decision_cutoff="2026-09-10T01:00:00Z",
            facts=routed["market"]["evidence"], source_access=[*self.access.values(), access(), sec],
            raw_records=records, collection_events=[], gaps=[], universe=universe,
            source_selections=[routed["selection"]])
        return inputs.portfolio, snapshot

if __name__ == "__main__":
    unittest.main()
