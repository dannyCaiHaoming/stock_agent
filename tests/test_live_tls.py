"""真实 opener 的零网络接缝，不用 mock 返回成功冒充真实取数。"""
from io import BytesIO
import importlib.util
import json
import ssl
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
import unittest
from urllib.error import URLError
from urllib.request import HTTPSHandler


@unittest.skipUnless(importlib.util.find_spec("certifi"), "在锁定 live 依赖环境验证")
class LiveTlsTests(unittest.TestCase):
    def test_sec_and_backup_actual_openers_verify_certificates(self):
        from product.mcp.live.sec_client import http_get as sec_get, _NoRedirect
        from product.mcp.live.eastmoney_transport import http_get as em_get, ENDPOINT
        for module, invoke in (
            ("product.mcp.live.sec_client.build_opener", lambda: sec_get("https://www.sec.gov/files/company_tickers_exchange.json", "synthetic contact@example.invalid")),
            ("urllib.request.build_opener", lambda: em_get(ENDPOINT, params={}, timeout=15)),
        ):
            body = BytesIO(b"{}")
            body.status, body.headers = 200, {}
            opener = Mock()
            opener.open.return_value = body
            with patch(module, return_value=opener) as build:
                self.assertEqual(invoke().status, 200)
            handlers = build.call_args.args
            self.assertTrue(any(isinstance(h, _NoRedirect) for h in handlers))
            context = next(h._context for h in handlers if isinstance(h, HTTPSHandler))
            self.assertTrue(context.check_hostname)
            self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
            self.assertGreater(context.cert_store_stats()["x509_ca"], 0)

    def test_sec_tls_failure_is_sanitized_sticky_and_not_retried(self):
        from product.mcp.live.sec_client import http_get, SecClient, SecTransportError
        from product.mcp.live.cache import SnapshotCache
        opener = Mock()
        opener.open.side_effect = URLError(ssl.SSLCertVerificationError(1, "private credential"))
        with patch("product.mcp.live.sec_client.build_opener", return_value=opener):
            with self.assertRaises(SecTransportError) as caught:
                http_get("https://www.sec.gov/files/company_tickers_exchange.json", "synthetic contact@example.invalid")
        with tempfile.TemporaryDirectory() as temp:
            send = Mock(side_effect=caught.exception)
            client = SecClient(SnapshotCache(Path(temp)), user_agent="synthetic contact@example.invalid", transport=send)
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, "SEC_TLS_CERTIFICATE_VERIFY_FAILED"):
                    client.read_ticker_map(max_age_seconds=0)
            send.assert_called_once()
            self.assertEqual(client.events[0]["transport_error"]["category"], "TLS_CERTIFICATE_VERIFY_FAILED")
            self.assertNotIn("private credential", json.dumps(client.events))
