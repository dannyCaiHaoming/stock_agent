"""只使用响应替身；不请求 Yahoo，不测试或证明上游准入。"""
from datetime import datetime, UTC
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import importlib.util
from pathlib import Path
import tempfile

from product.mcp.live.yahoo_transport import (
    RequestBoundary, YahooTransportError, acquire_anonymous_crumb,
)
from product.mcp.live.market import download_daily, MARKET_VERSION, YFINANCE_VERSION


def access():
    return {"schema_version": "live-source-access/1.0.0", "provider": "yahoo", "status": "AUTHORIZED",
            "client_version": f"yfinance/{YFINANCE_VERSION}", "adapter_version": MARKET_VERSION,
            "purpose": "personal-research", "terms_url": "https://example.invalid/terms", "checked_at": "2026-09-10T00:00:00Z",
            "free_features": ["synthetic"], "limitations": ["not real authorization"],
            "domains": ["query1.finance.yahoo.com", "fc.yahoo.com"], "request_budget": 5}


def response(status, retry_after=None):
    return SimpleNamespace(status_code=status, content=b"synthetic", headers={} if retry_after is None else {"Retry-After": retry_after})


class YahooTransportTests(unittest.TestCase):
    def test_server_range_rejected_before_send(self):
        for params in ({"range": "max"}, {"interval": "1m"}, {"includePrePost": True},
                       {"period1": 1, "period2": 9999999999}, {"period1": 1},
                       {"period1": True, "period2": 10}, {"range": "1d", "period1": 1, "period2": 10}):
            send = Mock()
            with self.subTest(params=params), self.assertRaisesRegex(YahooTransportError, "RANGE_INVALID"):
                self.boundary().request(send, "GET", "https://query1.finance.yahoo.com/v8/finance/chart/TEST", params=params)
            send.assert_not_called()

    def test_company_background_modules_are_exact_and_path_scoped(self):
        modules = "assetProfile,price,calendarEvents,earningsTrend,recommendationTrend,defaultKeyStatistics,summaryDetail"
        send = Mock(return_value=response(200))
        self.boundary().request(
            send, "GET", "https://query1.finance.yahoo.com/v10/finance/quoteSummary/TEST",
            params={"modules": modules},
        )
        self.assertEqual(send.call_count, 1)
        for url, params, code in (
            ("https://query1.finance.yahoo.com/v10/finance/quoteSummary/TEST", {"modules": "assetProfile,insiderTransactions"}, "MODULES_INVALID"),
            ("https://query1.finance.yahoo.com/v10/finance/quoteSummary/OTHER", {"modules": "assetProfile"}, "ENDPOINT_NOT_AUTHORIZED"),
            ("https://query1.finance.yahoo.com/v8/finance/chart/TEST", {"modules": "assetProfile"}, "FIELDS_NOT_AUTHORIZED"),
        ):
            attempted = Mock()
            with self.subTest(url=url, params=params), self.assertRaisesRegex(YahooTransportError, code):
                self.boundary().request(attempted, "GET", url, params=params)
            attempted.assert_not_called()

    @unittest.skipUnless(importlib.util.find_spec("curl_cffi"), "live 可选依赖未安装")
    def test_streaming_limit_stops_on_oversize_chunk_without_retry(self):
        from product.mcp.live.yahoo_transport import bounded_send
        from curl_cffi.curl import CURL_WRITEFUNC_ERROR, ffi, write_callback
        delivered = []
        def backend(method, url, **kwargs):
            self.assertFalse(kwargs["stream"])
            for chunk in (b"1234", b"5678", b"must-not-read"):
                delivered.append(chunk)
                callback_handle = ffi.new_handle(SimpleNamespace(callback=kwargs["content_callback"]))
                actual = write_callback(ffi.new("char[]", chunk), 1, len(chunk), callback_handle)
                if actual != len(chunk):
                    self.assertEqual(actual, CURL_WRITEFUNC_ERROR)
                    raise OSError("synthetic libcurl write error")
            return response(200)
        boundary = self.boundary()
        with patch("product.mcp.live.yahoo_transport.MAX_BYTES", 6):
            for _ in range(2):
                with self.assertRaisesRegex(YahooTransportError, "RESPONSE_TOO_LARGE"):
                    boundary.request(lambda m, u, **kw: bounded_send(backend, m, u, **kw),
                                     "GET", "https://query1.finance.yahoo.com/v8/finance/chart/TEST")
        self.assertEqual(delivered, [b"1234", b"5678"])
        self.assertEqual(boundary.requests, 1)
        self.assertEqual(boundary.events[-1]["failure_code"], "YAHOO_RESPONSE_TOO_LARGE")

    @unittest.skipUnless(importlib.util.find_spec("curl_cffi"), "live 可选依赖未安装")
    def test_streamed_body_preserved_for_sdk(self):
        from product.mcp.live.yahoo_transport import bounded_send
        def backend(method, url, **kwargs):
            for chunk in (b'{"ok":', b'true}'):
                self.assertEqual(kwargs["content_callback"](chunk), len(chunk))
            return response(200)
        self.assertEqual(bounded_send(backend, "GET", "https://synthetic").content, b'{"ok":true}')

    @unittest.skipUnless(importlib.util.find_spec("yfinance"), "live 可选依赖未安装")
    def test_installed_sdk_accepts_bounded_session_without_network(self):
        from product.mcp.live.yahoo_transport import create_yahoo_session
        from product.mcp.live.cache import SnapshotCache
        from yfinance._http import is_supported_session
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            session = create_yahoo_session(access(), tickers=["TEST"], state_dir=directory / "state", cache=SnapshotCache(directory / "cache"))
            try:
                self.assertTrue(is_supported_session(session))
                self.assertEqual(session.live_boundary.requests, 0)
            finally:
                session.close()

    @unittest.skipUnless(importlib.util.find_spec("yfinance"), "live 可选依赖未安装")
    def test_actual_session_uses_read_callback_without_network(self):
        from curl_cffi.requests import Session
        from product.mcp.live.yahoo_transport import create_yahoo_session
        from product.mcp.live.cache import SnapshotCache
        calls = []
        def backend(instance, method, url, **kwargs):
            calls.append(kwargs)
            kwargs["content_callback"](b'{"synthetic":true}')
            return response(200)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            session = create_yahoo_session(access(), tickers=["TEST"], state_dir=root / "state", cache=SnapshotCache(root / "cache"))
            try:
                with patch.object(Session, "request", backend):
                    result = session.request("GET", "https://query1.finance.yahoo.com/v8/finance/chart/TEST",
                                             params={"range": "1d", "interval": "1d"})
                self.assertEqual(result.content, b'{"synthetic":true}')
                self.assertEqual(session.live_boundary.requests, 1)
                self.assertFalse(calls[0]["allow_redirects"])
                self.assertEqual(calls[0]["timeout"], 20)
                self.assertTrue(session.live_boundary.chart_records)
            finally:
                session.close()

    def test_anonymous_crumb_is_ephemeral_and_shape_checked(self):
        class Session:
            def __init__(self, value=b"safe-crumb"):
                self.live_boundary = self_boundary
                self.value = value
                self.urls = []
            def get(self, url):
                self.urls.append(url)
                return SimpleNamespace(content=(b"" if "fc.yahoo" in url else self.value))
        self_boundary = self.boundary()
        session = Session()
        self.assertEqual(acquire_anonymous_crumb(session), "safe-crumb")
        self.assertEqual(session.urls, [
            "https://fc.yahoo.com/", "https://query1.finance.yahoo.com/v1/test/getcrumb",
        ])
        self.assertNotIn("safe-crumb", str(self_boundary.events))
        with self.assertRaisesRegex(YahooTransportError, "CRUMB_INVALID"):
            acquire_anonymous_crumb(Session(b"<html>"))

    def boundary(self, **changes):
        return RequestBoundary(dict(access(), **changes), tickers=["TEST"], sleep=Mock(),
                               now=lambda: datetime(2026, 9, 10, tzinfo=UTC))

    def test_scope_and_paused_sources_stop_before_transport(self):
        with self.assertRaisesRegex(YahooTransportError, "NOT_AUTHORIZED"):
            self.boundary(status="PAUSED")
        for method, url, extra in (("POST", "https://query1.finance.yahoo.com/v8/finance/chart/TEST", {}),
                ("GET", "https://query1.finance.yahoo.com/v8/finance/chart/OTHER", {}),
                ("GET", "https://consent.yahoo.com/v2/collectConsent", {}),
                ("GET", "https://query1.finance.yahoo.com/v8/finance/chart/TEST", {"params": {"quantity": 10}}),
                ("GET", "https://query1.finance.yahoo.com/v8/finance/chart/TEST?cost=12", {}),
                ("GET", "https://query1.finance.yahoo.com/v8/finance/chart/TEST", {"json": {"question": "private"}})):
            send = Mock()
            with self.subTest(url=url, method=method), self.assertRaises(YahooTransportError):
                self.boundary().request(send, method, url, **extra)
            send.assert_not_called()

    def test_authentication_and_redirect_failure_are_sticky(self):
        for status in (401, 403, 429, 302):
            boundary, send = self.boundary(), Mock(return_value=response(status))
            for _ in range(2):
                with self.assertRaisesRegex(YahooTransportError, f"HTTP_{status}"):
                    boundary.request(send, "GET", "https://query1.finance.yahoo.com/v8/finance/chart/TEST")
            self.assertEqual(send.call_count, 1)

    def test_retry_after_and_actual_request_budget(self):
        boundary = self.boundary()
        send = Mock(side_effect=[response(503, "3"), response(200)])
        boundary.request(send, "GET", "https://query1.finance.yahoo.com/v8/finance/chart/TEST", allow_redirects=True,
                         params={"crumb": "private-cookie-token"})
        self.assertEqual(boundary.requests, 2)
        boundary.sleep.assert_called_once_with(3)
        self.assertFalse(send.call_args.kwargs["allow_redirects"])
        self.assertNotIn("private-cookie-token", str(boundary.events))
        boundary = self.boundary(request_budget=1)
        send = Mock(return_value=response(503))
        with self.assertRaisesRegex(YahooTransportError, "BUDGET_EXHAUSTED"):
            boundary.request(send, "GET", "https://query1.finance.yahoo.com/v8/finance/chart/TEST")
        self.assertEqual(send.call_count, 1)

    def test_timeouts_and_excess_retry_after_stop(self):
        boundary = self.boundary()
        send = Mock(side_effect=TimeoutError("secret network message"))
        with self.assertRaisesRegex(YahooTransportError, "TRANSPORT_FAILURE"):
            boundary.request(send, "GET", "https://query1.finance.yahoo.com/v8/finance/chart/TEST")
        self.assertEqual(send.call_count, 3)
        self.assertNotIn("secret", str(boundary.events))
        for value in ("999", "nan", "invalid"):
            with self.assertRaisesRegex(YahooTransportError, "RETRY_AFTER"):
                self.boundary().request(Mock(return_value=response(503, value)), "GET", "https://query1.finance.yahoo.com/v8/finance/chart/TEST")

    def test_sdk_cannot_swallow_hard_failure(self):
        boundary = self.boundary()
        session = SimpleNamespace(live_boundary=boundary)
        def sdk(**kwargs):
            try:
                boundary.request(Mock(return_value=response(403)), "GET", "https://query1.finance.yahoo.com/v8/finance/chart/TEST")
            except YahooTransportError:
                return {}  # 模拟 SDK 吞掉异常并返回空表。
        with self.assertRaisesRegex(YahooTransportError, "HTTP_403"):
            download_daily(tickers=["TEST"], start="2026-09-01", end="2026-09-10", source_access=access(), downloader=sdk, session=session)

    def test_real_path_requires_bounded_session_before_import_or_request(self):
        with self.assertRaisesRegex(ValueError, "BOUNDED_SESSION_REQUIRED"):
            download_daily(tickers=["TEST"], start="2026-09-01", end="2026-09-10", source_access=access())


if __name__ == "__main__":
    unittest.main()
