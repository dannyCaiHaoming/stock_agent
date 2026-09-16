"""双状态准入接缝：纯合成响应，不访问 Provider 或模型。"""
from copy import deepcopy
from datetime import datetime, UTC
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from product.mcp.live.contracts import require_source_admission, validate_contract
from product.mcp.provenance import content_hash

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 16, 10, tzinfo=UTC)


def approved_access(old):
    value = deepcopy(old)
    value.pop("status", None)
    value["schema_version"] = "live-source-access/4.0.0"
    value["data_role"] = {"nasdaq": "universe", "yahoo": "primary_market", "eastmoney": "backup_market", "sec": "disclosure"}[value["provider"]]
    record = json.loads((ROOT / "docs/data/personal-research-approval.json").read_text())
    value["operator_approval"] = {"status": "APPROVED", "record": record, "record_hash": content_hash(record)}
    value["upstream_permission"] = {"status": "UNVERIFIED", "checked_at": "2026-09-10T00:00:00Z",
                                    "basis": ["synthetic-test-only"], "limitations": ["未核实；合成测试不证明上游许可"]}
    return value


class AdmissionTests(unittest.TestCase):
    def test_packaged_approval_matches_original_record_and_is_version_locked(self):
        from product.mcp.live.contracts import APPROVAL_RECORD
        from product.runtime.live_context import live_resource_hashes
        from product.runtime.hashing import file_hash
        self.assertEqual(APPROVAL_RECORD.read_bytes(),
                         (ROOT / "docs/data/personal-research-approval.json").read_bytes())
        self.assertEqual(live_resource_hashes(ROOT)[APPROVAL_RECORD.relative_to(ROOT).as_posix()],
                         file_hash(APPROVAL_RECORD))
        require_source_admission(self.access(), at=NOW.isoformat())

    def test_packaged_approval_missing_or_modified_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            record = Path(temp) / "approval.json"
            with patch("product.mcp.live.contracts.APPROVAL_RECORD", record):
                with self.assertRaises(FileNotFoundError):
                    require_source_admission(self.access(), at=NOW.isoformat())
                record.write_text('{}')
                with self.assertRaisesRegex(ValueError, "APPROVAL_RECORD_MISMATCH"):
                    require_source_admission(self.access(), at=NOW.isoformat())

    def test_current_collector_rejects_legacy_and_bad_v4_before_clients(self):
        from product.mcp.live.collection import collect_live_snapshot
        rows = json.loads((ROOT / "docs/product/examples/live-source-access-v3.synthetic.json").read_text())
        sample = json.loads((ROOT / "docs/product/examples/live-source-access-v4.synthetic.json").read_text())
        for entry in sample: validate_contract("source-access", entry)
        for case in ("legacy", "paused", "denied", "hash"):
            policies = [dict(r, status="AUTHORIZED") for r in rows] if case == "legacy" else [approved_access(r) for r in rows]
            if case == "paused": policies[0]["operator_approval"]["status"] = "PAUSED"
            elif case == "denied": policies[0]["upstream_permission"]["status"] = "DENIED"
            elif case == "hash": policies[0]["operator_approval"]["record_hash"] = "0" * 64
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                portfolio = root / "portfolio.json"
                portfolio.write_bytes((ROOT / "docs/product/examples/live-portfolio.synthetic.json").read_bytes())
                source = root / "source.json"
                source.write_text(json.dumps(policies))
                client = Mock(side_effect=AssertionError("不得创建客户端"))
                with self.subTest(case=case), self.assertRaises(ValueError):
                    collect_live_snapshot(portfolio, access_path=source, output_dir=root / "out", cache_root=root / "cache",
                                          sec_user_agent="unused", now=lambda: NOW, universe_factory=client, sec_factory=client)
                client.assert_not_called()
                self.assertFalse((root / "out").exists())

    def access(self):
        from tests.test_live_yahoo_transport import access
        return approved_access(access())

    def test_approved_unverified_passes_without_fabricated_authorized(self):
        value = self.access()
        require_source_admission(value, at=NOW.isoformat())
        self.assertNotIn("status", value)
        self.assertEqual(value["upstream_permission"]["status"], "UNVERIFIED")

    def test_missing_unknown_paused_denied_scope_hash_and_future_fail(self):
        for mutation in ("missing", "unknown", "paused", "denied", "scope", "hash", "record", "future", "future_check", "legacy_status"):
            value = self.access()
            op = value["operator_approval"]
            if mutation == "missing": del value["operator_approval"]
            elif mutation == "unknown": value["upstream_permission"]["status"] = "MAYBE"
            elif mutation == "paused": op["status"] = "PAUSED"
            elif mutation == "denied": value["upstream_permission"]["status"] = "DENIED"
            elif mutation == "scope": op["record"]["scope"]["position_policy"] = "FIXED_LIMIT"
            elif mutation == "hash": op["record_hash"] = "0" * 64
            elif mutation == "record":
                op["record"]["statement"] = "未经批准的声明"
                op["record_hash"] = content_hash(op["record"])
            elif mutation == "future":
                op["record"]["approved_at"] = "2027-01-01T00:00:00Z"
                op["record_hash"] = content_hash(op["record"])
            elif mutation == "future_check": value["upstream_permission"]["checked_at"] = "2027-01-01T00:00:00Z"
            else: value["status"] = "AUTHORIZED"
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                require_source_admission(value, at=NOW.isoformat())
        with self.assertRaisesRegex(ValueError, "FUTURE"):
            require_source_admission(self.access(), at="2026-09-10T08:00:00Z")

    def test_request_boundaries_use_same_contract_and_denial_stays_sticky(self):
        from product.mcp.live.yahoo_transport import RequestBoundary
        from types import SimpleNamespace
        for status in (401, 403, 429):
            boundary = RequestBoundary(self.access(), tickers=["TEST"], now=lambda: NOW, sleep=lambda _: None)
            send = Mock(return_value=SimpleNamespace(status_code=status, content=b"denied", headers={}))
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, str(status)):
                    boundary.request(send, "GET", "https://query1.finance.yahoo.com/v8/finance/chart/TEST")
            send.assert_called_once()
        denied = self.access()
        denied["upstream_permission"]["status"] = "DENIED"
        with self.assertRaisesRegex(ValueError, "UPSTREAM_DENIED"):
            RequestBoundary(denied, tickers=["TEST"], now=lambda: NOW)

    def test_legacy_status_not_reinterpreted(self):
        from tests.test_live_yahoo_transport import access
        value = access()
        require_source_admission(value, at=NOW.isoformat())
        value["status"] = "UNCONFIRMED"
        with self.assertRaisesRegex(ValueError, "NOT_AUTHORIZED"):
            require_source_admission(value, at=NOW.isoformat())

    def test_current_sec_denial_does_not_retry_or_send_next_request(self):
        from product.mcp.live.sec_client import SecClient, Response
        from product.mcp.live.cache import SnapshotCache
        row = json.loads((ROOT / "docs/product/examples/live-source-access-v3.synthetic.json").read_text())[-1]
        value = approved_access(row)
        with tempfile.TemporaryDirectory() as temp:
            for status in (401, 403, 429):
                send = Mock(return_value=Response(status, b"", "1"))
                client = SecClient(SnapshotCache(Path(temp)), user_agent="synthetic example@example.invalid",
                                   request_budget=value["request_budget"], source_access=value,
                                   transport=send, now=lambda: NOW, sleep=lambda _: None)
                for _ in range(2):
                    with self.assertRaisesRegex(ValueError, f"SEC_HTTP_{status}"):
                        client.fetch("https://www.sec.gov/files/company_tickers_exchange.json", max_age_seconds=0)
                send.assert_called_once()

    def test_v4_gate_revalidates_approval_even_with_rehashed_snapshot(self):
        from tests.test_live_source_routing import RoutingTests, Calendar
        from product.runtime.evidence_gate import run_live_evidence_gate
        from product.runtime.live_context import source_topology_lock
        case = RoutingTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        _, snapshot = case.snapshot()
        snapshot.update(schema_version="live-snapshot/4.0.0", request_started_at=NOW.isoformat(), decision_cutoff=NOW.isoformat(),
                        source_access=[approved_access(a) for a in snapshot["source_access"]])
        def seal(s): s["snapshot_hash"] = content_hash({k:v for k,v in s.items() if k != "snapshot_hash"})
        seal(snapshot)
        gate = run_live_evidence_gate(snapshot, run_id="v4-test", calendar=Calendar()).artifact
        self.assertTrue(gate["allowed_evidence_ids"])
        from product.runtime.live_report import render_live_report
        item = {"action": "NO_TRADE", "security_id": "TEST", "target_weight_range": None,
                "maximum_notional": None, "evidence_refs": gate["allowed_evidence_ids"],
                "no_trade_reason": "synthetic", "no_trade_explanation": "合成接缝，非研究证明",
                "reevaluation_conditions": ["补齐披露"]}
        decision = {"run_id": "v4-test", "terminal_state": "SAFE_NO_TRADE", "advisory_only": True,
                    "decisions": [item], "risk_report": {"status": "APPROVED"}}
        report = render_live_report(decision, gate=gate, reports={}, holding_horizon="六个月",
                                   portfolio=case.snapshot()[0], snapshot=snapshot, calendar=Calendar())
        self.assertIn("UNVERIFIED", report)
        self.assertIn("个人批准不代表上游授权", report)
        self.assertIn(snapshot["source_access"][0]["operator_approval"]["record_hash"], report)
        lock = source_topology_lock(snapshot)
        self.assertEqual(lock["source_access_hash"], content_hash(snapshot["source_access"]))
        for field in ("record_hash", "status"):
            bad = deepcopy(snapshot)
            bad["source_access"][0]["operator_approval"][field] = "0" * 64 if field == "record_hash" else "PAUSED"
            seal(bad)
            with self.assertRaises(ValueError):
                run_live_evidence_gate(bad, run_id="v4-test", calendar=Calendar())

    def test_each_provider_uses_canonical_admission_before_io(self):
        from product.mcp.live.nasdaq import NasdaqClient
        from product.mcp.live.eastmoney_transport import EastmoneyClient
        from product.mcp.live.cache import SnapshotCache
        rows = json.loads((ROOT / "docs/product/examples/live-source-access-v3.synthetic.json").read_text())
        with tempfile.TemporaryDirectory() as temp:
            cache = SnapshotCache(Path(temp))
            for row in rows:
                value = approved_access(row)
                require_source_admission(value, at=NOW.isoformat())
                if value["provider"] not in ("nasdaq", "eastmoney"): continue
                client = NasdaqClient if value["provider"] == "nasdaq" else EastmoneyClient
                send = Mock(side_effect=AssertionError("不得联网"))
                client(value, cache, transport=send, now=lambda: NOW)
                value["operator_approval"]["status"] = "PAUSED"
                with self.assertRaises(ValueError): client(value, cache, transport=send, now=lambda: NOW)
                send.assert_not_called()
