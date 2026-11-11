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

    def test_packaged_approval_missing_or_modified_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            record = Path(temp) / "approval.json"
            with patch("product.mcp.live.contracts.APPROVAL_RECORD", record):
                with self.assertRaises(FileNotFoundError):
                    require_source_admission(self.access(), at=NOW.isoformat())
                record.write_text('{}')
                with self.assertRaisesRegex(ValueError, "APPROVAL_RECORD_MISMATCH"):
                    require_source_admission(self.access(), at=NOW.isoformat())

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

