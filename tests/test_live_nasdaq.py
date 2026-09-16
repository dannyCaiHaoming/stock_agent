"""NASDAQ 离线接缝；AUTHORIZED 仅为合成配置，不是实际来源准入。"""
from copy import deepcopy
from datetime import datetime, UTC, timedelta
from io import BytesIO
import json
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from product.mcp.live.cache import SnapshotCache
from product.mcp.live.contracts import validate_contract
from product.mcp.live.nasdaq import (NasdaqClient, CLIENT_VERSION, ADAPTER_VERSION,
    MAX_BYTES, read_bounded, validate_universe, http_get)
from product.mcp.live.sec_client import Response
from product.mcp.provenance import content_hash

NOW = datetime(2026, 9, 10, tzinfo=UTC)


def access():
    return {"schema_version": "live-source-access/3.0.0", "provider": "nasdaq",
            "data_role": "universe", "client_version": CLIENT_VERSION, "adapter_version": ADAPTER_VERSION,
            "status": "AUTHORIZED", "purpose": "personal-research", "terms_url": "https://example.test/terms",
            "checked_at": "2026-09-09T00:00:00Z", "free_features": ["synthetic-test"],
            "limitations": ["not-real-authorization"], "domains": ["api.nasdaq.com"], "request_budget": 5}


def page(symbols, total, *, asof="Last price as of Sep 9, 2026"):
    return Response(200, json.dumps({"status": {"rCode": 200}, "data": {"asof": asof,
        "totalrecords": total, "table": {"asOf": None, "rows": [
            {"symbol": s, "name": f"Synthetic {s}", "lastsale": "$100"} for s in symbols]}}}).encode())


def download_page(rows):
    return Response(200, json.dumps({"status": {"rCode": 200}, "data": {
        "asof": "Last price as of Sep 9, 2026", "totalrecords": len(rows),
        "table": {"rows": rows},
    }}).encode())


def actual_download_shape(rows):
    """2026-09-15 实际 download 响应：rows 位于 data 根且不含 totalrecords。"""
    return Response(200, json.dumps({"status": {"rCode": 200}, "data": {
        "asOf": None,
        "headers": {"symbol": "Symbol", "name": "Name"},
        "rows": rows,
    }}).encode())


class NasdaqTests(unittest.TestCase):
    @unittest.skipUnless(importlib.util.find_spec("certifi"), "证书接缝在锁定 live 环境执行")
    def test_https_context_loads_locked_ca_and_keeps_verification(self):
        import ssl
        from product.mcp.live.nasdaq import verified_https_context
        context = verified_https_context()
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertGreater(context.cert_store_stats()["x509_ca"], 0)
        with patch("importlib.metadata.version", return_value="wrong"):
            with self.assertRaisesRegex(ValueError, "CERTIFI_VERSION_MISMATCH"):
                verified_https_context()

    @unittest.skipUnless(importlib.util.find_spec("certifi"), "证书接缝在锁定 live 环境执行")
    def test_real_opener_receives_verified_context_and_no_redirect_handler(self):
        import ssl
        from urllib.request import HTTPSHandler
        from product.mcp.live.sec_client import _NoRedirect
        body = BytesIO(page(["MSFT"], 1).body)
        body.status = 200
        opener = Mock()
        opener.open.return_value = body
        with patch("product.mcp.live.nasdaq.build_opener", return_value=opener) as build:
            reply = http_get("https://api.nasdaq.com/api/screener/stocks", params={"limit": 1, "offset": 0})
        self.assertEqual(reply.status, 200)
        handlers = build.call_args.args
        self.assertTrue(any(isinstance(h, _NoRedirect) for h in handlers))
        context = next(h._context for h in handlers if isinstance(h, HTTPSHandler))
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 20)

    @unittest.skipUnless(importlib.util.find_spec("certifi"), "证书接缝在锁定 live 环境执行")
    def test_transport_error_categories_survive_without_private_messages(self):
        import socket
        import ssl
        from urllib.error import URLError
        from product.mcp.live.nasdaq import NasdaqTransportError
        causes = [(ssl.SSLCertVerificationError(1, "private token"), "TLS_CERTIFICATE_VERIFY_FAILED"),
                  (ssl.SSLError(1, "private token"), "TLS_ERROR"),
                  (socket.gaierror(-2, "private token"), "DNS_ERROR"),
                  (ConnectionRefusedError(61, "private token"), "CONNECTION_REFUSED"),
                  (TimeoutError("private token"), "TIMEOUT"),
                  (OSError("private token"), "NETWORK_ERROR")]
        for cause, category in causes:
            opener = Mock()
            opener.open.side_effect = URLError(cause)
            with patch("product.mcp.live.nasdaq.build_opener", return_value=opener):
                with self.assertRaises(NasdaqTransportError) as caught:
                    http_get("https://api.nasdaq.com/api/screener/stocks", params={"limit": 1, "offset": 0})
            self.assertEqual(caught.exception.details["category"], category)
            client = self.client([caught.exception])
            snapshot = client.collect()
            self.assertEqual(snapshot["events"][0]["transport_error"]["category"], category)
            self.assertNotIn("private token", json.dumps(snapshot))
            with self.assertRaisesRegex(ValueError, "TRANSPORT_FAILURE"):
                client.collect()
            self.assertEqual(client.requests, 1)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cache = SnapshotCache(Path(self.temp.name))
        self.calls, self.sleeps = [], []

    def client(self, replies, **kwargs):
        replies = iter(replies)
        def transport(url, **params):
            self.calls.append((url, params))
            reply = next(replies)
            if isinstance(reply, Exception):
                raise reply
            return reply
        return NasdaqClient(kwargs.pop("access", access()), self.cache, transport=transport,
                            now=kwargs.pop("now", lambda: NOW), monotonic=lambda: 0,
                            sleep=self.sleeps.append, **kwargs)

    def test_pagination_and_original_evidence(self):
        c = self.client([page(["MSFT", "AAPL"], "3"), page(["BRK/B"], 3)])
        s = c.collect(page_size=2, max_pages=2, max_rows=3)
        self.assertEqual(s["completeness"], "COMPLETE")
        self.assertEqual([call[1]["params"] for call in self.calls], [{"limit": 2, "offset": 0}, {"limit": 1, "offset": 2}])
        self.assertEqual(s["rows"][-1]["symbol"], "BRK/B")
        self.assertTrue(all(r["identity_status"] == "UNVERIFIED" for r in s["rows"]))
        self.assertNotIn("lastsale", s["rows"][0])
        self.assertEqual(s["pages"][0]["source_asof"], "Last price as of Sep 9, 2026")
        self.assertNotEqual(s["rows"][0]["as_of"], s["pages"][0]["source_asof"])
        self.assertIsNone(s["membership_effective_at"])
        self.assertEqual(self.sleeps, [1])
        validate_contract("universe", s)
        validate_universe(s, self.cache)

    def test_download_directory_preserves_peer_candidate_fields_without_price(self):
        response = download_page([
            {"symbol": "MRVL", "name": "Marvell Technology Inc.", "lastsale": "$100",
             "marketCap": "100000", "country": "United States", "ipoyear": "2000",
             "sector": "Technology", "industry": "Semiconductors", "volume": "123"},
            {"symbol": "AVGO", "name": "Broadcom Inc.", "lastsale": "$200",
             "marketCap": "200000", "country": "United States", "ipoyear": "2009",
             "sector": "Technology", "industry": "Semiconductors", "volume": "456"},
        ])
        snapshot = self.client([response]).collect_download(max_rows=8000)
        self.assertEqual(snapshot["completeness"], "COMPLETE")
        self.assertEqual(snapshot["rows"][0]["industry"], "Semiconductors")
        self.assertEqual(snapshot["rows"][0]["market_cap"], "100000")
        self.assertNotIn("lastsale", snapshot["rows"][0])
        self.assertNotIn("volume", snapshot["rows"][0])
        self.assertTrue(snapshot["pages"][0]["download"])

    def test_actual_download_shape_without_totalrecords_is_complete(self):
        rows = [
            {"symbol": "ALB           ", "name": "Albemarle Corporation Common Stock",
             "marketCap": "10400000000.00", "country": "United States",
             "ipoyear": "1994", "sector": "Industrials", "industry": "Chemicals"},
            {"symbol": "MRVL", "name": "Marvell Technology Inc. Common Stock",
             "marketCap": "80000000000.00", "country": "United States",
             "ipoyear": "2000", "sector": "Technology", "industry": "Semiconductors"},
        ]
        snapshot = self.client([actual_download_shape(rows)]).collect_download(max_rows=8000)
        self.assertEqual(snapshot["completeness"], "COMPLETE")
        self.assertEqual(snapshot["totalrecords"], 2)
        self.assertEqual(snapshot["row_count"], 2)
        self.assertEqual(snapshot["rows"][0]["symbol"], "ALB")
        self.assertIsNone(snapshot["pages"][0]["source_asof"])
        validate_universe(snapshot, self.cache)

    def test_default_partial_not_full_universe(self):
        s = self.client([page([f"S{i}" for i in range(20)], 7139)]).collect()
        self.assertEqual(s["completeness"], "PARTIAL")
        self.assertEqual(s["row_count"], 20)
        self.assertIn("SHORT_OR_EMPTY_PAGE", s["gaps"])

    def test_page_and_row_budget(self):
        s = self.client([page(["MSFT"], 3)]).collect(page_size=1, max_pages=1)
        self.assertIn("PAGE_BUDGET_EXHAUSTED", s["gaps"])
        s = self.client([]).collect(page_size=1, max_pages=3, max_rows=1)
        self.assertIn("ROW_BUDGET_EXHAUSTED", s["gaps"])
        self.assertEqual(len(self.calls), 1)

    def test_empty_duplicate_changed_total(self):
        variants = [([page([], 3)], "SHORT_OR_EMPTY_PAGE"),
                    ([page(["MSFT", "MSFT"], 2)], "DUPLICATE_SYMBOL")]
        for replies, expected in variants:
            with self.subTest(expected=expected):
                # 每个案例独立缓存，避免前一个合成响应参与本次输入。
                with tempfile.TemporaryDirectory() as temp:
                    self.cache = SnapshotCache(Path(temp))
                    s = self.client(replies).collect(page_size=2)
                    self.assertEqual(s["completeness"], "PARTIAL")
                    self.assertIn(expected, s["gaps"])
        with tempfile.TemporaryDirectory() as temp:
            self.cache = SnapshotCache(Path(temp))
            s = self.client([page(["MSFT"], 2), page(["AAPL"], 3)]).collect(page_size=1, max_pages=2)
            self.assertIn("TOTAL_CHANGED", s["gaps"])

    def test_denial_stops_sticky_no_retry(self):
        for status in (401, 403, 429, 302):
            with self.subTest(status=status):
                c = self.client([Response(status, b"private error")])
                s = c.collect(max_pages=3)
                self.assertIn(f"NASDAQ_HTTP_{status}", s["gaps"])
                with self.assertRaisesRegex(ValueError, f"NASDAQ_HTTP_{status}"):
                    c.collect()
                self.assertEqual(c.requests, 1)
                self.assertNotIn("private error", json.dumps(s))

    def test_invalid_payload_and_timeout_not_complete(self):
        for reply in (Response(200, b"<html>challenge</html>"), TimeoutError()):
            with tempfile.TemporaryDirectory() as temp:
                self.cache = SnapshotCache(Path(temp))
                s = self.client([reply]).collect()
                self.assertEqual(s["completeness"], "PARTIAL")
                self.assertTrue(s["gaps"])
                self.assertEqual(s["rows"], [])

    def test_cache_preserves_original_observation(self):
        first = self.client([page(["TSM"], 1, asof=None)]).collect()
        second = self.client([], now=lambda: NOW + timedelta(hours=1)).collect()
        self.assertEqual(second["rows"], first["rows"])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(second["rows"][0]["identity_status"], "UNVERIFIED")
        self.assertNotEqual(second["retrieved_at"], first["retrieved_at"])

    def test_cache_future_not_retried(self):
        self.client([page(["MSFT"], 1)]).collect()
        s = self.client([], now=lambda: NOW - timedelta(hours=1)).collect()
        self.assertIn("NASDAQ_CACHE_FROM_FUTURE", s["gaps"])
        self.assertEqual(len(self.calls), 1)

    def test_completion_summary_tampering_rejected(self):
        s = self.client([page(["MSFT"], 3)]).collect(page_size=1)
        for changes in ({"completeness": "COMPLETE"}, {"row_count": 3}):
            bad = dict(s, **changes)
            bad["snapshot_hash"] = content_hash({k: v for k, v in bad.items() if k != "snapshot_hash"})
            with self.assertRaises(ValueError):
                validate_contract("universe", bad)
        bad = deepcopy(s)
        bad["rows"][0]["name"] = "forged"
        bad["snapshot_hash"] = content_hash({k: v for k, v in bad.items() if k != "snapshot_hash"})
        with self.assertRaisesRegex(ValueError, "CONTENT_MISMATCH"):
            validate_universe(bad, self.cache)

    def test_raw_hash_mutation_rejected(self):
        s = self.client([page(["MSFT"], 1)]).collect()
        raw = self.cache._path("objects", s["pages"][0]["record"]["raw_content_hash"])
        raw.write_bytes(b"tampered synthetic test")
        with self.assertRaisesRegex(ValueError, "CACHE_OBJECT_HASH_MISMATCH"):
            validate_universe(s, self.cache)

    def test_no_authority_or_wrong_role_no_calls(self):
        for change in ({"status": "UNCONFIRMED"}, {"data_role": "primary_market"},
                       {"domains": ["example.test"]}, {"checked_at": "2027-01-01T00:00:00Z"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.client([], access=dict(access(), **change))
        self.assertEqual(self.calls, [])

    def test_request_budget_stops_before_next_page(self):
        c = self.client([page(["MSFT"], 3)], access=dict(access(), request_budget=1))
        s = c.collect(page_size=1, max_pages=3)
        self.assertIn("NASDAQ_REQUEST_BUDGET_EXHAUSTED", s["gaps"])
        self.assertEqual(c.requests, 1)
        self.assertEqual(s["row_count"], 1)

    def test_repeated_page_and_symbol_aliases_not_silently_merged(self):
        c = self.client([page(["MSFT"], 2), page(["MSFT"], 2)])
        s = c.collect(page_size=1, max_pages=2)
        self.assertIn("DUPLICATE_SYMBOL", s["gaps"])
        self.assertEqual(s["completeness"], "PARTIAL")
        with tempfile.TemporaryDirectory() as temp:
            self.cache = SnapshotCache(Path(temp))
            s = self.client([page(["BRK/B", "BRK.B"], 2)]).collect()
            self.assertEqual([r["symbol"] for r in s["rows"]], ["BRK/B", "BRK.B"])
            self.assertTrue(all(r["identity_status"] == "UNVERIFIED" for r in s["rows"]))

    def test_forged_lineage_and_historical_time_fail(self):
        s = self.client([page(["MSFT"], 1)]).collect()
        for target in ("row_time", "page_hash", "membership_time"):
            bad = deepcopy(s)
            if target == "row_time":
                bad["rows"][0]["as_of"] = "2020-01-01T00:00:00Z"
            elif target == "page_hash":
                bad["pages"][0]["record"]["raw_content_hash"] = "0" * 64
            else:
                bad["membership_effective_at"] = "2020-01-01T00:00:00Z"
            bad["snapshot_hash"] = content_hash({k: v for k, v in bad.items() if k != "snapshot_hash"})
            with self.subTest(target=target), self.assertRaises(ValueError):
                validate_contract("universe", bad)

    def test_read_and_scope_limits(self):
        stream = BytesIO(b"x" * (MAX_BYTES + 2))
        with self.assertRaisesRegex(ValueError, "TOO_LARGE"):
            read_bounded(stream, deadline=1, monotonic=lambda: 0)
        self.assertEqual(stream.tell(), MAX_BYTES + 1)
        with self.assertRaisesRegex(TimeoutError, "TIMEOUT"):
            read_bounded(BytesIO(b"x"), deadline=0, monotonic=lambda: 0)
        for change in ({"page_size": 0}, {"max_pages": True}, {"max_rows": 0}, {"max_age_seconds": -1}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "SCOPE_INVALID"):
                self.client([]).collect(**change)
        with self.assertRaisesRegex(ValueError, "SCOPE_INVALID"):
            http_get("https://example.test", params={"quantity": 1})
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
