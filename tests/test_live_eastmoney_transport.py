"""合成响应的零网络接缝；真实 SDK 测试也只使用内存 transport。"""
from datetime import datetime, UTC
from importlib.util import find_spec
from io import BytesIO
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from product.mcp.live.eastmoney_transport import (
    DailyRequestBoundary, ENDPOINT, FIELDS1, FIELDS2, MAX_BYTES,
    parse_with_locked_sdk, read_bounded,
)


def payload():
    return {"rc": 0, "data": {"code": "MSFT", "klines": [
        "2026-09-08,100,101,102,99,1000,101000,3,1,1,0.01",
        "2026-09-09,101,102,103,100,1000,102000,3,1,1,0.01"]}}


def response(data=None, status=200):
    return SimpleNamespace(status=status, body=json.dumps(payload() if data is None else data).encode())


class EastmoneyTransportTests(unittest.TestCase):
    def boundary(self, transport=None, **overrides):
        self.calls, self.sleeps = [], []
        def default(url, **kwargs):
            self.calls.append((url, kwargs))
            return response()
        args = dict(symbol="105.MSFT", start="2026-09-08", end="2026-09-09", request_budget=3,
                    transport=transport or default, now=lambda: datetime(2026, 9, 10, tzinfo=UTC),
                    monotonic=lambda: 0, sleep=self.sleeps.append)
        return DailyRequestBoundary(**dict(args, **overrides))

    def params(self):
        return dict(secid="105.MSFT", fields1=FIELDS1, fields2=FIELDS2,
                    klt="101", fqt="0", end="20500000", lmt="1000000")

    def get(self, boundary, params=None):
        return boundary.get(ENDPOINT, timeout=15, params=self.params() if params is None else params)

    def test_bounded_before_send_and_raw_lineage(self):
        b = self.boundary()
        original = self.params()
        self.get(b, original)
        actual = self.calls[0][1]["params"]
        self.assertEqual((actual["beg"], actual["end"], actual["lmt"]), ("20260908", "20260909", "2"))
        self.assertEqual(original, self.params())
        self.assertEqual(b.requests, 1)
        self.assertEqual(b.raw, response().body)
        self.assertEqual(len(b.events[0]["raw_content_hash"]), 64)

    def test_request_drift_and_private_fields_rejected_before_send(self):
        for change in ({"fqt": "1"}, {"quantity": 10}, {"secid": "105.AAPL"}):
            with self.subTest(change=change):
                b = self.boundary()
                with self.assertRaisesRegex(ValueError, "SDK_REQUEST_DRIFT"):
                    self.get(b, dict(self.params(), **change))
                self.assertEqual(b.requests, 0)

    def test_access_denials_sticky_without_retry(self):
        for status in (401, 403, 429, 302):
            with self.subTest(status=status):
                b = self.boundary(lambda *a, **k: response(status=status))
                for _ in range(2):
                    with self.assertRaisesRegex(ValueError, f"HTTP_{status}"):
                        self.get(b)
                self.assertEqual(b.requests, 1)

    def test_retry_budget_rate_and_count(self):
        replies = iter([response(status=503), response(status=502), response()])
        b = self.boundary(lambda *a, **k: next(replies))
        self.get(b)
        self.assertEqual(b.requests, 3)
        self.assertEqual(self.sleeps, [1, 1])
        b = self.boundary(lambda *a, **k: response(status=503), request_budget=1)
        with self.assertRaisesRegex(ValueError, "BUDGET_EXHAUSTED"):
            self.get(b)
        self.assertEqual(b.requests, 1)

    def test_timeout_is_bounded_and_unexpected_exception_redacted(self):
        b = self.boundary(lambda *a, **k: (_ for _ in ()).throw(TimeoutError()))
        with self.assertRaisesRegex(ValueError, "HTTP_0"):
            self.get(b)
        self.assertEqual(b.requests, 3)
        b = self.boundary(lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret")))
        with self.assertRaisesRegex(ValueError, "TRANSPORT_FAILURE"):
            self.get(b)
        self.assertNotIn("secret", json.dumps(b.events))

    def test_invalid_payload_rejected_not_sliced_away(self):
        variants = []
        for value in ("NaN", "0", "-2"):
            p = payload()
            p["data"]["klines"][0] = p["data"]["klines"][0].replace(",101,102,", f",{value},102,")
            variants.append(p)
        p = payload(); p["data"]["code"] = "AAPL"; variants.append(p)
        p = payload(); p["data"]["klines"][0] = p["data"]["klines"][0].replace("2026-09-08", "2026-09-07"); variants.append(p)
        p = payload(); p["data"]["klines"].append(p["data"]["klines"][0]); variants.append(p)
        p = payload(); p["data"]["klines"][1] = p["data"]["klines"][0]; variants.append(p)
        variants.extend([{"data": None}, {"rc": 1, "data": payload()["data"]}])
        for p in variants:
            with self.subTest(payload=p):
                b = self.boundary(lambda *a, **k: response(p))
                with self.assertRaises(ValueError): self.get(b)
                self.assertIsNone(b.raw)
                self.assertEqual(b.requests, 1)

    def test_html_challenge_and_empty_response(self):
        b = self.boundary(lambda *a, **k: SimpleNamespace(status=200, body=b"<html>captcha</html>"))
        with self.assertRaisesRegex(ValueError, "PAYLOAD_INVALID"): self.get(b)
        self.assertEqual(b.requests, 1)
        p = payload(); p["data"]["klines"] = []
        self.assertEqual(self.get(self.boundary(lambda *a, **k: response(p))).json()["data"]["klines"], [])

    def test_size_limit_during_read(self):
        stream = BytesIO(b"x" * (MAX_BYTES + 100))
        with self.assertRaisesRegex(ValueError, "TOO_LARGE"): read_bounded(stream)
        self.assertEqual(stream.tell(), MAX_BYTES + 1)
        self.assertEqual(read_bounded(BytesIO(b"abc")), b"abc")

    def test_invalid_scope(self):
        for overrides in ({"start": "2024-01-01"}, {"symbol": "105.MSFT?secret"},
                          {"request_budget": True}, {"end": "2026-09-07"}):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                self.boundary(**overrides)

    def test_client_drift_rejected_before_sdk_import(self):
        b = self.boundary()
        with patch("product.mcp.live.eastmoney_transport.version", return_value="unexpected"):
            with self.assertRaisesRegex(ValueError, "CLIENT_VERSION_MISMATCH"):
                parse_with_locked_sdk(b)
        self.assertEqual(b.requests, 0)

    @unittest.skipUnless(find_spec("akshare"), "live SDK 未安装；在隔离 AKShare 环境执行")
    def test_actual_sdk_scoped_globals_no_network(self):
        from akshare.stock_feature.stock_hist_em import stock_us_hist
        import requests
        original = stock_us_hist.__globals__["requests"]
        with patch.object(requests.sessions.Session, "request", side_effect=AssertionError("NETWORK_FORBIDDEN")):
            first, second = self.boundary(), self.boundary()
            frames = [parse_with_locked_sdk(b) for b in (first, second)]
        self.assertIs(stock_us_hist.__globals__["requests"], original)
        self.assertEqual([b.requests for b in (first, second)], [1, 1])
        self.assertEqual(frames[0]["收盘"].tolist(), [101, 102])
        self.assertEqual(frames[1]["日期"].tolist(), ["2026-09-08", "2026-09-09"])
        with patch("product.mcp.live.eastmoney_transport.inspect.getsource", return_value="drift"):
            untouched = self.boundary()
            with self.assertRaisesRegex(ValueError, "SDK_SOURCE_DRIFT"):
                parse_with_locked_sdk(untouched)
            self.assertEqual(untouched.requests, 0)


if __name__ == "__main__":
    unittest.main()
