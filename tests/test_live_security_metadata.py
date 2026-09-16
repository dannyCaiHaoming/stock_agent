import hashlib
import json
import unittest

from product.mcp.live.security_metadata import parse_chart_identity, parse_eastmoney_identity, eastmoney_symbol, bind_disclosure_security


class SecurityMetadataTests(unittest.TestCase):
    def eastmoney_quote(self, *, changes=None, record_changes=None, raw_suffix=b""):
        from product.mcp.live.eastmoney_transport import ADAPTER_VERSION, AKSHARE_VERSION, ENDPOINT
        raw = json.dumps({"rc": 0, "data": dict(code="TEST", market=105, **{}) | (changes or {})}).encode()
        record = {"raw_content_hash": hashlib.sha256(raw).hexdigest(), "retrieved_at": "2026-09-10T00:00:00Z",
                  "key": dict(provider="eastmoney", provider_symbol="105.TEST", client_version=AKSHARE_VERSION,
                              adapter_version=ADAPTER_VERSION, endpoint=ENDPOINT) | (record_changes or {})}
        return parse_eastmoney_identity(raw + raw_suffix, ticker="TEST", exchange="XNAS", record=record)

    def test_eastmoney_identity_and_sec_cover_bind_without_yahoo_fields(self):
        quote = self.eastmoney_quote()
        bound = bind_disclosure_security(*self.cover(title="Class A Common Stock"), quote)
        self.assertEqual(bound["share_class"], "A")
        self.assertEqual(bound["currency"], "USD")
        self.assertEqual(bound["quote_identity"]["provider_symbol"], "105.TEST")
        self.assertEqual(bound["metadata_version"], "us-equity-security-metadata/2.0.0")
        self.assertNotIn("yahoo", json.dumps(bound))

    def test_eastmoney_identity_rejects_market_symbol_version_and_raw_drift(self):
        for changes in ({"code": "OTHER"}, {"market": 106}, {"market": "105"}, {"market": True}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "RESPONSE_MISMATCH"):
                self.eastmoney_quote(changes=changes)
        for changes in ({"provider": "yahoo"}, {"provider_symbol": "106.TEST"}, {"client_version": "old"},
                        {"adapter_version": "old"}, {"endpoint": "https://example.invalid"}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "SOURCE_MISMATCH"):
                self.eastmoney_quote(record_changes=changes)
        with self.assertRaisesRegex(ValueError, "SOURCE_MISMATCH"):
            self.eastmoney_quote(raw_suffix=b" ")

    def test_eastmoney_no_punctuation_mapping_or_unsupported_exchange_guess(self):
        for ticker, exchange in (("BRK/B", "XNYS"), ("BRK.B", "XNYS"), ("BRK-B", "XNYS"),
                                 ("TEST", "OTC"), ("test", "XNAS")):
            with self.subTest(ticker=ticker, exchange=exchange), self.assertRaises(ValueError):
                eastmoney_symbol(ticker, exchange)

    def test_eastmoney_cover_rejects_adr_exchange_and_ambiguous_class(self):
        for changes in ({"title": "American Depositary Shares representing common stock"},
                        {"title": "Preferred Stock"}, {"exchange": "NYSE"}, {"symbol": "OTHER"},
                        {"title": "Class A and Class B Common Stock"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                bind_disclosure_security(*self.cover(**changes), self.eastmoney_quote())

    def quote(self, **changes):
        metadata = dict(dict(symbol="TEST", instrumentType="EQUITY", currency="USD", exchangeName="NMS",
                        exchangeTimezoneName="America/New_York"), **changes)
        raw = json.dumps({"chart": {"error": None, "result": [{"meta": metadata}]}}).encode()
        record = {"raw_content_hash": hashlib.sha256(raw).hexdigest(), "retrieved_at": "2026-09-10T00:00:00Z",
                  "key": {"endpoint": "https://query1.finance.yahoo.com/v8/finance/chart/TEST"}}
        return parse_chart_identity(raw, ticker="TEST", record=record)

    def cover(self, title="Common Stock", symbol="TEST", exchange="NASDAQ", other=""):
        raw = (f'<ix:nonNumeric name="dei:Security12bTitle" contextRef="C">{title}</ix:nonNumeric>'
               f'<ix:nonNumeric name="dei:TradingSymbol" contextRef="C">{symbol}</ix:nonNumeric>'
               f'<ix:nonNumeric name="dei:SecurityExchangeName" contextRef="C">{exchange}</ix:nonNumeric>{other}').encode()
        document = {"form": "10-K", "raw_content_hash": hashlib.sha256(raw).hexdigest(),
                    "retrieved_at": "2026-09-09T00:00:00Z", "published_at": "2026-08-01T00:00:00Z",
                    "cik": "0000000001", "accession": "0000000001-26-000001",
                    "source_id": "sec-test", "source_locator": "https://www.sec.gov/synthetic"}
        return raw, document

    def test_common_share_class_requires_both_sources(self):
        for title, expected in (("Common Stock, par value $0.01", "common"), ("Class A Common Stock", "A")):
            result = bind_disclosure_security(*self.cover(title=title), self.quote())
            self.assertEqual(result["share_class"], expected)
            self.assertEqual(result["security_type"], "COMMON_STOCK")
            self.assertIn("quote_identity", result)

    def test_exact_nasdaq_legal_name_alias_preserves_exchange_validation(self):
        for quote in (self.quote(), self.eastmoney_quote()):
            self.assertEqual(bind_disclosure_security(*self.cover(exchange="The Nasdaq Stock Market LLC"), quote)["exchange"], "XNAS")
            self.assertEqual(bind_disclosure_security(*self.cover(exchange="The Nasdaq Global Select Market"), quote)["exchange"], "XNAS")
            for exchange in ("The Nasdaq Stock Market LLC Other", "The Nasdaq Global Select Market Other", "NASDAQ UNKNOWN", "NYSE"):
                with self.subTest(exchange=exchange), self.assertRaisesRegex(ValueError, "EXCHANGE_CONFLICT"):
                    bind_disclosure_security(*self.cover(exchange=exchange), quote)
        with self.assertRaisesRegex(ValueError, "EXCHANGE_CONFLICT"):
            bind_disclosure_security(*self.cover(exchange="The Nasdaq Stock Market LLC"), self.quote(exchangeName="NYQ"))

    def test_exact_nyse_legal_name_alias_preserves_exchange_validation(self):
        quote = self.quote(exchangeName="NYQ")
        for exchange in ("NYSE", "New York Stock Exchange"):
            with self.subTest(exchange=exchange):
                self.assertEqual(bind_disclosure_security(*self.cover(exchange=exchange), quote)["exchange"], "XNYS")
        for exchange in ("New York Stock Exchange Other", "NYSE UNKNOWN", "NASDAQ"):
            with self.subTest(exchange=exchange), self.assertRaisesRegex(ValueError, "EXCHANGE_CONFLICT"):
                bind_disclosure_security(*self.cover(exchange=exchange), quote)

    def test_quote_does_not_admit_etf_otc_foreign_currency_or_wrong_ticker(self):
        for changes in ({"instrumentType": "ETF"}, {"exchangeName": "PNK"}, {"currency": "EUR"}, {"symbol": "OTHER"}):
            with self.subTest(changes=changes), self.assertRaisesRegex(ValueError, "UNSUPPORTED"):
                self.quote(**changes)

    def test_adr_preferred_wrong_symbol_exchange_and_foreign_form_rejected(self):
        for changes in ({"title": "American Depositary Shares representing common stock"},
                        {"title": "Preferred Stock"}, {"symbol": "OTHER"}, {"exchange": "NYSE"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                bind_disclosure_security(*self.cover(**changes), self.quote())
        raw, document = self.cover()
        with self.assertRaisesRegex(ValueError, "DOMESTIC"):
            bind_disclosure_security(raw, dict(document, form="20-F"), self.quote())

    def test_ambiguous_cover_and_hash_mismatch_rejected(self):
        other = '<ix:nonNumeric name="dei:Security12bTitle" contextRef="C">Class B Common Stock</ix:nonNumeric>'
        with self.assertRaisesRegex(ValueError, "AMBIGUOUS"):
            bind_disclosure_security(*self.cover(other=other), self.quote())
        raw, document = self.cover()
        with self.assertRaisesRegex(ValueError, "HASH"):
            bind_disclosure_security(raw + b"x", document, self.quote())

    def test_common_share_and_explicit_notes_same_symbol_use_unique_equity_context(self):
        notes, _ = self.cover(title="3.125% Notes due 2028")
        other = notes.decode().replace('contextRef="C"', 'contextRef="Debt"')
        bound = bind_disclosure_security(*self.cover(other=other), self.quote())
        self.assertEqual(bound["cover_context"], "C")
        self.assertEqual(bound["security_type"], "COMMON_STOCK")
        with self.assertRaisesRegex(ValueError, "MISSING"):
            bind_disclosure_security(*self.cover(title="3.125% Notes due 2028"), self.quote())

    def test_other_common_context_and_unknown_security_still_rejected(self):
        for title in ("Class B Common Stock", "Unclassified security", "Preferred Stock",
                      "American Depositary Shares representing common stock"):
            other, _ = self.cover(title=title)
            other = other.decode().replace('contextRef="C"', 'contextRef="Other"')
            with self.subTest(title=title), self.assertRaises(ValueError):
                bind_disclosure_security(*self.cover(other=other), self.quote())


if __name__ == "__main__":
    unittest.main()
