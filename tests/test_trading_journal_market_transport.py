"""匿名行情 transport 的离线 TLS/端点边界，不接触账户或真实网络。"""
from contextlib import contextmanager, ExitStack
import json
import os
import ssl
import stat
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit
from urllib.request import HTTPSHandler

from product.trading_journal.common import JournalError
from product.trading_journal import market


QUERY = {"symbol": "ACME", "start": "2026-09-01", "end": "2026-09-30"}
DEFAULT_FILE = "/python-default/cert.pem"
DEFAULT_DIR = "/python-default/certs"
SYSTEM_CA = "/etc/ssl/cert.pem"


class Response:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self, size):
        return json.dumps({"chart": {"result": [{"meta": {}}]}}).encode()


@contextmanager
def transport_fixture(*, platform="darwin", files=(), directories=(), environment=None,
                      path_errors=None, unreadable=(), context_error=None, request_error=None):
    """保留真实 SSLContext 安全属性，其余依赖均以合成路径/HTTP 响应代替。"""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    paths = SimpleNamespace(
        cafile=DEFAULT_FILE if DEFAULT_FILE in files else None,
        capath=DEFAULT_DIR if DEFAULT_DIR in directories else None,
        openssl_cafile=DEFAULT_FILE, openssl_capath=DEFAULT_DIR,
    )
    path_errors = path_errors or {}

    def path_stat(path):
        key = str(path)
        if key in path_errors:
            raise path_errors[key]
        if key in files:
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o444)
        if key in directories:
            return SimpleNamespace(st_mode=stat.S_IFDIR | 0o555)
        raise FileNotFoundError(key)

    opener = Mock()
    opener.open.return_value = Response()
    if request_error:
        opener.open.side_effect = request_error
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, environment or {}, clear=True))
        stack.enter_context(patch.object(market.sys, "platform", platform))
        default_paths = stack.enter_context(patch.object(market.ssl, "get_default_verify_paths", return_value=paths))
        stack.enter_context(patch.object(market.Path, "stat", autospec=True, side_effect=path_stat))
        stack.enter_context(patch.object(market.os, "access", side_effect=lambda path, mode: path not in unreadable))
        factory = stack.enter_context(patch.object(market.ssl, "create_default_context", return_value=context))
        if context_error:
            factory.side_effect = context_error
        builder = stack.enter_context(patch.object(market, "build_opener", return_value=opener))
        yield SimpleNamespace(context=context, default_paths=default_paths, factory=factory,
                              builder=builder, opener=opener)


class MarketTransportTests(unittest.TestCase):
    def assert_secure_handler(self, fixture):
        handlers = fixture.builder.call_args.args
        self.assertEqual(len(handlers), 2)
        self.assertIsInstance(handlers[0], market._NoRedirect)
        self.assertIsInstance(handlers[1], HTTPSHandler)
        self.assertIs(handlers[1]._context, fixture.context)
        self.assertEqual(fixture.context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(fixture.context.check_hostname)

    def assert_transport_failure(self, fixture):
        with self.assertRaises(JournalError) as failure:
            market.yahoo_get(dict(QUERY))
        self.assertEqual(failure.exception.code, "MARKET_TRANSPORT_FAILED")
        self.assertNotIn("sensitive upstream", str(failure.exception))

    def test_available_default_ca_file_keeps_default_verified_context(self):
        with transport_fixture(files=(DEFAULT_FILE, SYSTEM_CA)) as fixture:
            market.yahoo_get(dict(QUERY))
            fixture.factory.assert_called_once_with()
            self.assert_secure_handler(fixture)

    def test_available_default_ca_directory_keeps_default_verified_context(self):
        with transport_fixture(files=(SYSTEM_CA,), directories=(DEFAULT_DIR,)) as fixture:
            market.yahoo_get(dict(QUERY))
            fixture.factory.assert_called_once_with()
            self.assert_secure_handler(fixture)

    def test_missing_mac_default_ca_uses_only_fixed_system_bundle(self):
        original_environment = dict(os.environ)
        with transport_fixture(files=(SYSTEM_CA,)) as fixture:
            environment_before = dict(os.environ)
            market.yahoo_get(dict(QUERY))
            fixture.factory.assert_called_once_with(cafile=SYSTEM_CA)
            self.assert_secure_handler(fixture)
            self.assertEqual(dict(os.environ), environment_before)
        self.assertEqual(dict(os.environ), original_environment)

    def test_non_mac_missing_defaults_does_not_select_mac_bundle(self):
        for platform in ("linux", "win32"):
            with self.subTest(platform=platform), transport_fixture(platform=platform, files=(SYSTEM_CA,)) as fixture:
                market.yahoo_get(dict(QUERY))
                fixture.factory.assert_called_once_with()
                fixture.default_paths.assert_not_called()
                self.assert_secure_handler(fixture)

    def test_explicit_user_ca_settings_are_never_overridden_even_if_empty(self):
        for environment in ({"SSL_CERT_FILE": "/user/ca.pem"}, {"SSL_CERT_DIR": "/user/certs"},
                            {"SSL_CERT_FILE": ""}, {"SSL_CERT_DIR": ""}):
            with self.subTest(environment=environment), transport_fixture(files=(SYSTEM_CA,), environment=environment) as fixture:
                market.yahoo_get(dict(QUERY))
                fixture.factory.assert_called_once_with()
                fixture.default_paths.assert_not_called()
                self.assertEqual(dict(os.environ), environment)
                self.assert_secure_handler(fixture)

    def test_default_path_error_fails_without_loading_another_ca_or_http(self):
        for error in (PermissionError("sensitive upstream"), OSError("sensitive upstream"),
                      NotADirectoryError("sensitive upstream")):
            with self.subTest(error=type(error).__name__), transport_fixture(
                files=(SYSTEM_CA,), path_errors={DEFAULT_FILE: error}
            ) as fixture:
                self.assert_transport_failure(fixture)
                fixture.factory.assert_not_called()
                fixture.builder.assert_not_called()

    def test_unreadable_default_ca_fails_without_system_fallback(self):
        with transport_fixture(files=(DEFAULT_FILE, SYSTEM_CA), unreadable=(DEFAULT_FILE,)) as fixture:
            self.assert_transport_failure(fixture)
            fixture.factory.assert_not_called()
            fixture.builder.assert_not_called()

    def test_missing_or_unreadable_system_bundle_fails_before_http(self):
        for files, unreadable in (((), ()), ((SYSTEM_CA,), (SYSTEM_CA,))):
            with self.subTest(files=files, unreadable=unreadable), transport_fixture(files=files, unreadable=unreadable) as fixture:
                self.assert_transport_failure(fixture)
                fixture.factory.assert_not_called()
                fixture.builder.assert_not_called()

    def test_system_ca_load_error_fails_without_retry_or_unverified_context(self):
        with transport_fixture(files=(SYSTEM_CA,), context_error=ssl.SSLError("sensitive upstream")) as fixture:
            self.assert_transport_failure(fixture)
            fixture.factory.assert_called_once_with(cafile=SYSTEM_CA)
            fixture.builder.assert_not_called()

    def test_certificate_verification_failure_is_not_retried(self):
        error = URLError(ssl.SSLCertVerificationError("sensitive upstream"))
        with transport_fixture(files=(SYSTEM_CA,), request_error=error) as fixture:
            self.assert_transport_failure(fixture)
            fixture.factory.assert_called_once_with(cafile=SYSTEM_CA)
            fixture.opener.open.assert_called_once()
            self.assert_secure_handler(fixture)

    def test_fixed_anonymous_get_query_and_fields_are_unchanged(self):
        with transport_fixture(files=(SYSTEM_CA,)) as fixture:
            result = market.yahoo_get(dict(QUERY))
            request = fixture.opener.open.call_args.args[0]
            parts = urlsplit(request.full_url)
            self.assertEqual(parts.scheme, "https")
            self.assertEqual(parts.netloc, "query1.finance.yahoo.com")
            self.assertEqual(parts.path, "/v8/finance/chart/ACME")
            self.assertEqual(parse_qs(parts.query), {
                "period1": ["1788220800"], "period2": ["1790812800"], "interval": ["1d"],
                "events": ["div,splits"], "includePrePost": ["false"], "includeAdjustedClose": ["true"],
            })
            self.assertEqual(request.get_method(), "GET")
            self.assertIsNone(request.data)
            self.assertEqual(set(key.lower() for key in request.headers), {"accept", "user-agent"})
            self.assertEqual(fixture.opener.open.call_args.kwargs, {"timeout": 20})
            fixture.opener.open.assert_called_once()
            self.assertEqual(set(result), {"provider_result", "raw_content_hash"})
            self.assert_secure_handler(fixture)

    def test_private_fields_arbitrary_url_ca_input_and_symbol_injection_rejected_before_tls(self):
        queries = [
            {**QUERY, "account_ref": "private"}, {**QUERY, "url": "https://other.example/"},
            {**QUERY, "cafile": "/user/ca.pem"}, {**QUERY, "symbol": "ACME/../secret"},
            {**QUERY, "symbol": "ACME?token=secret"}, {**QUERY, "symbol": "https://other.example/"},
        ]
        with transport_fixture(files=(SYSTEM_CA,)) as fixture:
            for query in queries:
                with self.subTest(query=query), self.assertRaises(JournalError) as failure:
                    market.yahoo_get(query)
                self.assertEqual(failure.exception.code, "MARKET_QUERY_REJECTED")
            fixture.factory.assert_not_called()
            fixture.builder.assert_not_called()

    def test_redirect_rejection_survives_explicit_https_handler(self):
        with transport_fixture(files=(SYSTEM_CA,)) as fixture:
            def redirect(request, timeout):
                handler = fixture.builder.call_args.args[0]
                return handler.redirect_request(request, None, 302, "Found", {}, "https://other.example/")

            fixture.opener.open.side_effect = redirect
            with self.assertRaises(JournalError) as failure:
                market.yahoo_get(dict(QUERY))
            self.assertEqual(failure.exception.code, "MARKET_REDIRECT_REJECTED")
            fixture.opener.open.assert_called_once()
            self.assert_secure_handler(fixture)


class MarketHKIdentityTests(unittest.TestCase):
    @staticmethod
    def instrument(symbol, *, market_name="HK", **fields):
        return {"key": "synthetic-instrument", "asset_type": "STOCK", "symbol": symbol,
                "market": market_name, "currency": "HKD", "exchange_timezone": "Asia/Hong_Kong", **fields}

    def fetch(self, instrument, returned_symbol):
        calls = []

        def transport(query):
            calls.append(query)
            return {"provider_result": {"meta": {"symbol": returned_symbol,
                    "exchangeTimezoneName": "Asia/Hong_Kong", "currency": "HKD"}}}

        result = market.fetch_market(instrument, "2026-09-01", "2026-09-30", transport=transport,
                                     now="2026-10-01T00:00:00Z", context_sessions=0)
        return result, calls

    def test_hk_numeric_identity_maps_leading_zeroes_without_mutating_trade_instrument(self):
        cases = {"00006": "0006.HK", "01234": "1234.HK", "12345": "12345.HK",
                 "0006": "0006.HK", "1234": "1234.HK", "99999": "99999.HK"}
        for market_name in ("HK", "HONG_KONG", "HKEX"):
            for original_symbol, expected_symbol in cases.items():
                with self.subTest(market=market_name, symbol=original_symbol):
                    instrument = self.instrument(original_symbol, market_name=market_name)
                    original = dict(instrument)
                    result, calls = self.fetch(instrument, expected_symbol)
                    self.assertEqual(calls, [{**QUERY, "symbol": expected_symbol}])
                    self.assertEqual(result["symbol"], expected_symbol)
                    self.assertEqual(result["segments"][0]["status"], "FETCHED")
                    self.assertEqual(instrument, original)

    def test_non_hk_numeric_symbols_are_not_rewritten(self):
        for symbol in ("00006", "01234", "12345"):
            with self.subTest(symbol=symbol):
                result, calls = self.fetch(self.instrument(symbol, market_name="US"), symbol)
                self.assertEqual(calls[0]["symbol"], symbol)
                self.assertEqual(result["symbol"], symbol)

    def test_explicit_hk_provider_code_is_preserved(self):
        result, calls = self.fetch(self.instrument("0006.HK"), "0006.HK")
        self.assertEqual(calls[0]["symbol"], "0006.HK")
        self.assertEqual(result["symbol"], "0006.HK")

    def test_missing_zero_or_over_range_hk_codes_fail_before_transport(self):
        for symbol in (None, "", "0", "00000", "100000", "999999", "1000000000000000000000000"):
            with self.subTest(symbol=symbol), self.assertRaises(JournalError) as failure:
                market.fetch_market(self.instrument(symbol), QUERY["start"], QUERY["end"],
                                    transport=Mock(side_effect=AssertionError("must not contact provider")))
            self.assertEqual(failure.exception.code, "MARKET_SYMBOL_UNSUPPORTED")

    def test_cn_numeric_symbol_does_not_gain_a_guessed_exchange(self):
        with self.assertRaises(JournalError) as failure:
            self.fetch(self.instrument("00006", market_name="CN"), "0006.HK")
        self.assertEqual(failure.exception.code, "MARKET_SYMBOL_MAPPING_UNKNOWN")

    def test_provider_symbol_mismatch_is_still_rejected_after_mapping(self):
        result, calls = self.fetch(self.instrument("01234"), "01234.HK")
        self.assertEqual(calls[0]["symbol"], "1234.HK")
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["candles"], [])
        self.assertEqual(result["segments"][0]["status"], "FAILED")
        self.assertEqual(result["segments"][0]["reason"], "MARKET_SYMBOL_MISMATCH")

    def test_option_underlying_mapping_preserves_full_contract_code(self):
        instrument = self.instrument("synthetic-contract", asset_type="OPTION", underlying="00006")
        original = dict(instrument)
        result, calls = self.fetch(instrument, "0006.HK")
        self.assertEqual(calls[0]["symbol"], "0006.HK")
        self.assertEqual(result["symbol"], "0006.HK")
        self.assertEqual(instrument, original)


if __name__ == "__main__":
    unittest.main()
