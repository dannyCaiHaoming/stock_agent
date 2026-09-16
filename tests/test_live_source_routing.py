"""纯数据路由测试；不运行模型，也不访问行情服务。"""
from copy import deepcopy
from datetime import datetime, UTC
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from product.mcp.live.cache import SnapshotCache
from product.mcp.live.contracts import validate_contract
from product.mcp.live.market import normalize_daily_rows
from product.mcp.live.source_routing import collect_selected_market, provider_versions, validate_selection
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

    def test_rehashed_fact_client_version_drift_is_rejected(self):
        _, snapshot = self.snapshot()
        snapshot["facts"][0]["source_version"] = "yfinance/old"
        snapshot["snapshot_hash"] = content_hash({k: v for k, v in snapshot.items() if k != "snapshot_hash"})
        with self.assertRaisesRegex(ValueError, "FACT_VERSION_MISMATCH"):
            validate_contract("snapshot", snapshot)

    def test_stale_price_cannot_hide_version_integrity_failure_by_fallback(self):
        self.primary.return_value = self.market("yahoo", "2026-09-01")
        self.primary.return_value["evidence"][0]["source_version"] = "unknown"
        result = self.run_route()
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["failure_code"], "LIVE_SELECTION_FACT_VERSION_MISMATCH")
        self.backup.assert_not_called()

    def test_report_shows_selected_source_and_failure(self):
        from product.runtime.evidence_gate import run_live_evidence_gate
        from product.runtime.live_report import render_live_report
        portfolio, snapshot = self.snapshot()
        gate = run_live_evidence_gate(snapshot, run_id="synthetic-report", calendar=Calendar()).artifact
        item = {"action": "NO_TRADE", "security_id": "TEST", "target_weight_range": None,
                "maximum_notional": None, "evidence_refs": gate["allowed_evidence_ids"],
                "no_trade_reason": "synthetic", "no_trade_explanation": "合成测试，不是研究验收",
                "reevaluation_conditions": ["补齐披露"]}
        decision = {"run_id": "synthetic-report", "terminal_state": "SAFE_NO_TRADE", "advisory_only": True,
                    "decisions": [item], "risk_report": {"status": "APPROVED"}}
        text = render_live_report(decision, gate=gate, reports={}, holding_horizon="六个月",
                                  portfolio=portfolio, snapshot=snapshot, calendar=Calendar())
        for expected in ("eastmoney", "akshare/1.18.94", "行情来源与回退记录", "股票池覆盖范围"):
            self.assertIn(expected, text)
        self.assertIn("YAHOO\\_HTTP\\_503", text)

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

    def test_route_freeze_gate_valuation_and_raw_page_chain(self):
        from product.runtime.evidence_gate import run_live_evidence_gate
        from product.runtime.live_input import value_portfolio
        from product.runtime.live_context import validate_raw_records
        portfolio, snapshot = self.snapshot()
        self.assertEqual(snapshot["schema_version"], "live-snapshot/3.0.0")
        objects = {r["raw_content_hash"]: self.cache.read(r) for r in snapshot["raw_records"]}
        validate_raw_records(snapshot, objects.__getitem__)
        gate = run_live_evidence_gate(snapshot, run_id="synthetic-routed", calendar=Calendar()).artifact
        value = value_portfolio(portfolio, snapshot, gate, calendar=Calendar())
        self.assertEqual(value["total_value"], "1100")
        self.assertEqual(gate["allowed_evidence"][0]["source_type"], "eastmoney")
        bad = deepcopy(snapshot)
        bad["raw_records"] = [r for r in bad["raw_records"] if r["key"]["provider"] != "nasdaq"]
        with self.assertRaisesRegex(ValueError, "OBJECT_MISSING"):
            validate_raw_records(bad, objects.__getitem__)

    def test_comparison_price_series_does_not_mutate_source_selection_closure(self):
        _, snapshot = self.snapshot()
        research = deepcopy(snapshot["facts"][0])
        research.update(
            evidence_id="ev-research-comparison",
            semantic_field="adjusted_close_price",
            usage="comparison",
            source_version=research["source_version"] + "/yahoo-research-series/1.0.0",
        )
        snapshot["facts"].append(research)
        snapshot["snapshot_hash"] = content_hash({
            key: value for key, value in snapshot.items() if key != "snapshot_hash"
        })
        validate_contract("snapshot", snapshot)
        self.assertNotIn(
            research["evidence_id"], snapshot["source_selections"][0]["evidence_ids"]
        )

    def test_snapshot_missing_or_dangling_selection_rejected(self):
        _, snapshot = self.snapshot()
        for change in ("missing", "dangling", "late"):
            bad = deepcopy(snapshot)
            if change == "missing": bad["source_selections"] = []
            elif change == "dangling": bad["source_selections"][0]["evidence_ids"] = ["nonexistent"]
            else: bad["source_selections"][0]["attempts"][-1]["completed_at"] = "2027-01-01T00:00:00Z"
            if bad["source_selections"]:
                selected = bad["source_selections"][0]
                selected["selection_hash"] = content_hash({k: v for k, v in selected.items() if k != "selection_hash"})
            bad["snapshot_hash"] = content_hash({k: v for k, v in bad.items() if k != "snapshot_hash"})
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_contract("snapshot", bad)

    def test_current_v4_snapshot_accepts_more_than_three_source_selections(self):
        from tests.test_live_admission import approved_access

        _, original = self.snapshot()
        fact_template = original["facts"][0]
        selection_template = original["source_selections"][0]
        facts, selections = [], []
        for number in range(4):
            security_id = f"US:TEST{number}"
            fact = deepcopy(fact_template)
            fact["security_id"] = security_id
            fact["evidence_id"] = f"ev-v4-{number}"
            facts.append(fact)
            selection = deepcopy(selection_template)
            selection["security_id"] = security_id
            selection["evidence_ids"] = [fact["evidence_id"]]
            selection["selection_hash"] = content_hash({
                key: value for key, value in selection.items() if key != "selection_hash"
            })
            selections.append(selection)
        snapshot = deepcopy(original)
        snapshot.update(
            schema_version="live-snapshot/4.0.0",
            request_started_at="2026-09-16T09:00:00Z",
            decision_cutoff="2026-09-16T10:00:00Z",
            facts=facts,
            source_selections=selections,
            source_access=[approved_access(item) for item in original["source_access"]],
        )
        snapshot["snapshot_hash"] = content_hash({
            key: value for key, value in snapshot.items() if key != "snapshot_hash"
        })
        validate_contract("snapshot", snapshot)
        self.assertEqual(4, len(snapshot["source_selections"]))


if __name__ == "__main__":
    unittest.main()
