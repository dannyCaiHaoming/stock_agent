from unittest import TestCase, mock
from importlib.util import find_spec

from product.mcp.live.market import normalize_daily_rows, download_daily, collect_daily, ExchangeCalendar, MARKET_VERSION, YFINANCE_VERSION
from product.mcp.live.cache import SnapshotCache
from pathlib import Path
import tempfile


class SyntheticCalendar:
    version = "synthetic/1"
    content_hash = "c" * 64

    def session_close(self, day):
        return {"2026-11-27": "2026-11-27T18:00:00Z", "2026-11-30": "2026-11-30T21:00:00Z"}.get(day)


class LiveMarketTests(TestCase):
    def normalize(self, rows, **changes):
        kwargs = dict(security_id="TEST", ticker="TEST", retrieved_at="2026-11-30T20:00:00Z",
                      calendar=SyntheticCalendar(), raw_content_hash="a" * 64, currency="USD")
        kwargs.update(changes)
        return normalize_daily_rows(rows, **kwargs)

    def test_incomplete_holiday_and_weekend_excluded(self):
        result = self.normalize([{"date": day, "close": 20} for day in ("2026-11-26", "2026-11-27", "2026-11-28", "2026-11-30")])
        self.assertEqual(len(result["evidence"]), 1)
        self.assertEqual(len(result["gaps"]), 3)
        self.assertEqual(result["evidence"][0]["as_of"], "2026-11-27T18:00:00Z")

    def test_adjusted_close_not_used_for_valuation(self):
        fact = self.normalize([{"date": "2026-11-27", "close": 20, "adjusted_close": 10, "stock_splits": 2, "dividends": 1}])["evidence"][0]
        self.assertEqual(fact["value"], "20")
        self.assertFalse(fact["metadata"]["historical_return_eligible"])
        self.assertEqual(fact["metadata"]["stock_splits"], 2)

    def test_bad_prices_currency_and_duplicate(self):
        for price in (None, "nan", float("inf"), -1, 0):
            with self.subTest(price=price), self.assertRaises(ValueError):
                self.normalize([{"date": "2026-11-27", "close": price}])
        with self.assertRaises(ValueError):
            self.normalize([], currency="EUR")
        with self.assertRaises(ValueError):
            self.normalize([{"date": "2026-11-27", "close": 20}] * 2)

    def test_paused_rejects_before_sdk_and_explicit_parameters(self):
        access = {"schema_version": "live-source-access/1.0.0", "provider": "yahoo", "client_version": f"yfinance/{YFINANCE_VERSION}",
            "adapter_version": MARKET_VERSION, "status": "PAUSED", "purpose": "personal-research", "terms_url": "synthetic",
            "checked_at": "2026-09-10T00:00:00Z", "free_features": ["test"], "limitations": ["synthetic permission only"],
            "domains": ["example.invalid"], "request_budget": 1}
        downloader = mock.Mock(return_value="synthetic-data")
        with self.assertRaisesRegex(ValueError, "NOT_AUTHORIZED"):
            download_daily(tickers=["TEST"], start="2026-01-01", end="2026-09-01", source_access=access, downloader=downloader)
        downloader.assert_not_called()
        access["status"] = "AUTHORIZED"
        result = download_daily(tickers=["TEST", "TEST"], start="2026-01-01", end="2026-09-01", source_access=access, downloader=downloader)
        self.assertEqual(downloader.call_args.kwargs["tickers"], ["TEST"])
        self.assertFalse(downloader.call_args.kwargs["auto_adjust"])
        self.assertFalse(downloader.call_args.kwargs["threads"])
        self.assertIsNone(result["actual_http_requests"])

    def test_real_calendar_holiday_early_close_and_dst(self):
        if find_spec("exchange_calendars") is None:
            self.skipTest("live optional calendar not installed; not calendar acceptance")
        calendar = ExchangeCalendar(start="2026-01-01", end="2026-12-31")
        self.assertIsNone(calendar.session_close("2026-11-26"))
        self.assertEqual(calendar.session_close("2026-11-27"), "2026-11-27T18:00:00Z")
        self.assertEqual(calendar.session_close("2026-03-06"), "2026-03-06T21:00:00Z")
        self.assertEqual(calendar.session_close("2026-03-09"), "2026-03-09T20:00:00Z")
        self.assertIsNone(calendar.session_close("2026-11-28"))

    def test_sdk_signature_is_compatible_without_request(self):
        if find_spec("yfinance") is None:
            self.skipTest("live optional client not installed")
        import inspect
        import yfinance
        inspect.signature(yfinance.download).bind(tickers=["TEST"], start="2026-01-01", end="2026-09-01",
            interval="1d", auto_adjust=False, back_adjust=False, repair=False, actions=True,
            threads=False, progress=False, group_by="ticker", timeout=20)

    def test_partial_batch_cache_and_incremental_requests(self):
        if find_spec("pandas") is None:
            self.skipTest("live optional dataframe dependency not installed")
        import pandas as pd
        frame = pd.DataFrame({("TEST", "Close"): [20.0], ("TEST", "Adj Close"): [10.0]}, index=pd.to_datetime(["2026-11-27"]))
        access = {"schema_version": "live-source-access/1.0.0", "provider": "yahoo", "client_version": f"yfinance/{YFINANCE_VERSION}",
            "adapter_version": MARKET_VERSION, "status": "AUTHORIZED", "purpose": "personal-research", "terms_url": "synthetic",
            "checked_at": "2026-09-10T00:00:00Z", "free_features": ["test"], "limitations": ["synthetic permission only"],
            "domains": ["example.invalid"], "request_budget": 1}
        targets = [{"ticker": ticker, "security_id": ticker, "currency": "USD"} for ticker in ("TEST", "SECOND")]
        with tempfile.TemporaryDirectory() as temp:
            cache = SnapshotCache(Path(temp))
            downloader = mock.Mock(return_value=frame)
            kwargs = dict(start="2026-01-01", end="2026-11-28", source_access=access, cache=cache,
                          calendar=SyntheticCalendar(), retrieved_at="2026-11-30T20:00:00Z", max_age_seconds=100, downloader=downloader)
            first = collect_daily(targets + [targets[0]], **kwargs)
            self.assertEqual(downloader.call_args.kwargs["tickers"], ["SECOND", "TEST"])
            self.assertEqual(len(first["evidence"]), 1)
            self.assertEqual(first["gaps"][0]["reason"], "YAHOO_SYMBOL_RESPONSE_MISSING")
            second = collect_daily(targets, **kwargs)
            self.assertEqual(downloader.call_args.kwargs["tickers"], ["SECOND"])
            self.assertEqual(second["cache_hits"], 1)
            self.assertEqual(second["evidence"][0]["retrieved_at"], first["evidence"][0]["retrieved_at"])
