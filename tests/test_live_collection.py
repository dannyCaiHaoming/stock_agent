"""真实解析/冻结路径＋内存 HTTP 响应；禁止以本测试宣称真实取数。"""
from datetime import datetime, UTC
import json
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from product.mcp.live.collection import collect_live_snapshot
from product.mcp.live.sec_client import SecClient, Response, CLIENT_VERSION
from product.mcp.live.sec import ADAPTER_VERSION
from product.mcp.live.market import normalize_daily_rows
from product.mcp.live.yahoo_transport import RequestBoundary
from product.runtime.live_context import validate_raw_records
from tests.test_live_yahoo_transport import access
from tests.test_live_contracts_gate import Calendar

ROOT = Path(__file__).resolve().parents[1]
NOW = datetime(2026, 9, 10, 10, tzinfo=UTC)


class FrozenCalendar(Calendar):
    def __init__(self, **kwargs):
        pass

    def session_close(self, day):
        return "2026-09-09T20:00:00Z"

    def lock_record(self):
        return {"version": self.version, "content_hash": self.content_hash}


class LiveCollectionTests(unittest.TestCase):
    def test_paused_access_does_not_create_client_or_output(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            portfolio = directory / "portfolio.json"
            portfolio.write_bytes((ROOT / "docs/product/examples/live-portfolio.synthetic.json").read_bytes())
            source = directory / "access.json"
            source.write_text(json.dumps([dict(access(), status="PAUSED"), dict(access(), provider="sec")]))
            client = Mock(side_effect=AssertionError("不应创建客户端"))
            with self.assertRaisesRegex(ValueError, "PAUSED_OR_NOT_AUTHORIZED"):
                collect_live_snapshot(portfolio, access_path=source, output_dir=directory / "out", cache_root=directory / "cache",
                                      sec_user_agent="unused", sec_factory=client)
            client.assert_not_called()
            self.assertFalse((directory / "out").exists())

    def test_collection_freezes_after_requests_and_binds_identity_raw_objects(self):
        with self.assertRaisesRegex(ValueError, "LIVE_CURRENT_SOURCE_TOPOLOGY_REQUIRED"):
            self.collect_case()

    def test_routed_primary_collection_freeze_prepare(self):
        self.collect_case(routed=True)

    def test_collection_only_portfolio_resolves_identity_without_fake_mandate(self):
        self.collect_case(routed=True, collection_only=True)

    def test_missing_history_document_is_frozen_as_gap_not_evidence(self):
        self.collect_case(routed=True, missing_history=True)

    def test_collection_resolves_sec_xsl_ownership_document_to_raw_xml(self):
        self.collect_case(routed=True, ownership=True)

    def test_directory_unavailable_does_not_block_verified_holding(self):
        for failure in ("http403", "transport"):
            with self.subTest(failure=failure):
                self.collect_case(routed=True, directory_failure=failure)

    def test_directory_corruption_still_fails_closed(self):
        with self.assertRaises(ValueError):
            self.collect_case(routed=True, directory_failure="corrupt")

    def test_directory_unavailable_does_not_weaken_identity_checks(self):
        with self.assertRaisesRegex(ValueError, "EXCHANGE_CONFLICT"):
            self.collect_case(routed=True, directory_failure="http403", wrong_exchange=True)

    @unittest.skipUnless(importlib.util.find_spec("akshare"), "真实 SDK 在合并 live 环境验证")
    def test_routed_backup_collection_freeze_prepare(self):
        self.collect_case(routed=True, fail_primary=True)

    def collect_case(self, *, routed=False, fail_primary=False, directory_failure=None, wrong_exchange=False,
                     missing_history=False, collection_only=False, ownership=False):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp).resolve()
            portfolio = directory / "portfolio.json"
            if collection_only:
                portfolio.write_text(json.dumps({
                    "schema_version": "live-portfolio/2.0.0",
                    "purpose": "COMMON_STOCK_DATA_COLLECTION",
                    "base_currency": "USD",
                    "source_id": "synthetic-confirmed-handoff",
                    "as_of": "2026-09-10T09:00:00Z",
                    "retrieved_at": "2026-09-10T09:01:00Z",
                    "positions": [{
                        "security_id": "TEST", "ticker": "TEST",
                        "exchange": None, "share_class": None,
                    }],
                }))
            else:
                portfolio.write_bytes((ROOT / "docs/product/examples/live-portfolio.synthetic.json").read_bytes())
            source = directory / "access.json"
            source.write_text(json.dumps([access(), dict(access(), provider="sec", client_version=CLIENT_VERSION,
                adapter_version=ADAPTER_VERSION, domains=["data.sec.gov", "www.sec.gov"], request_budget=20)]))
            factories = {}
            if routed:
                from tests.test_live_nasdaq import access as nasdaq_access, page
                from product.mcp.live.nasdaq import NasdaqClient
                from product.mcp.live.eastmoney_transport import EastmoneyClient, ADAPTER_VERSION as EM_VERSION, AKSHARE_VERSION
                policies = [dict(p, schema_version="live-source-access/3.0.0",
                    data_role="primary_market" if p["provider"] == "yahoo" else "disclosure") for p in json.loads(source.read_text())]
                policies.extend([nasdaq_access(), dict(access(), schema_version="live-source-access/3.0.0",
                    provider="eastmoney", data_role="backup_market", client_version=f"akshare/{AKSHARE_VERSION}",
                    adapter_version=EM_VERSION, domains=["63.push2his.eastmoney.com"])])
                from tests.test_live_admission import approved_access
                policies = [approved_access(p) for p in policies]
                source.write_text(json.dumps(policies))
                raw = json.dumps({"rc": 0, "data": {"code": "TEST", "market": 105,
                    "klines": ["2026-09-09,19,20,21,18,100,2000,1,1,1,1"]}}).encode()
                def directory_transport(*args, **kwargs):
                    if directory_failure == "transport":
                        raise TimeoutError("synthetic timeout")
                    if directory_failure == "http403":
                        return Response(403, b"denied")
                    if directory_failure == "corrupt":
                        return Response(200, b"not-json")
                    return page(["TEST"], 1)
                factories = {"universe_factory": lambda a, c: NasdaqClient(a, c,
                    transport=directory_transport, now=lambda: NOW, sleep=lambda _: None),
                    "backup_factory": lambda a, c: EastmoneyClient(a, c,
                    transport=lambda *args, **kw: Response(200, raw), now=lambda: NOW, sleep=lambda _: None)}
            mapping = {"fields": ["cik", "name", "ticker", "exchange"], "data": [[1, "Synthetic", "TEST", "Nasdaq"]]}
            submissions = {"cik": 1, "filings": {"files": [], "recent": {
                "accessionNumber": ["0000000001-26-000001"], "acceptanceDateTime": ["2026-02-01T12:00:00Z"],
                "form": ["10-K"], "primaryDocument": ["test.htm"], "reportDate": ["2025-12-31"]}}}
            if ownership:
                recent = submissions["filings"]["recent"]
                recent["accessionNumber"].append("0000000001-26-000002")
                recent["acceptanceDateTime"].append("2026-09-09T12:00:00Z")
                recent["form"].append("4")
                recent["primaryDocument"].append("xslF345X06/wk-form4.xml")
                recent["reportDate"].append("2026-09-08")
            financials = {"cik": 1, "facts": {"us-gaap": {"Revenues": {"units": {"USD": [
                {"val": 120, "start": "2025-01-01", "end": "2025-12-31", "accn": "0000000001-26-000001", "form": "10-K"},
                {"val": 100, "start": "2024-01-01", "end": "2024-12-31", "accn": "0000000001-26-000001", "form": "10-K"}]}}}}}
            historical = {"accessionNumber": ["0000000001-00-000001"], "form": ["10-K"],
                "primaryDocument": [""], "reportDate": ["1999-12-31"],
                "acceptanceDateTime": ["2000-02-01T12:00:00Z"]}
            if missing_history:
                submissions["filings"]["files"] = [{"name": "CIK0000000001-submissions-001.json"}]
            html = ('<ix:nonNumeric name="dei:Security12bTitle" contextRef="C">Common Stock</ix:nonNumeric>'
                    '<ix:nonNumeric name="dei:TradingSymbol" contextRef="C">TEST</ix:nonNumeric>'
                    '<ix:nonNumeric name="dei:SecurityExchangeName" contextRef="C">NASDAQ</ix:nonNumeric>'
                    '<p>Item 1. Business Synthetic manufacturing.</p><p>Item 1A. Risk Factors Supplier risk.</p>'
                    '<p>Item 7. Management Discussion Synthetic expansion.</p>').encode()
            ownership_xml = b"""<ownershipDocument>
<issuer><issuerCik>0000000001</issuerCik></issuer>
<reportingOwner><reportingOwnerId><rptOwnerCik>0000000002</rptOwnerCik><rptOwnerName>Synthetic Owner</rptOwnerName></reportingOwnerId></reportingOwner>
<nonDerivativeTable><nonDerivativeTransaction>
<securityTitle><value>Common Stock</value></securityTitle>
<transactionDate><value>2026-09-08</value></transactionDate>
<transactionCoding><transactionCode>P</transactionCode></transactionCoding>
<transactionAmounts><transactionShares><value>10</value></transactionShares><transactionPricePerShare><value>20</value></transactionPricePerShare><transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode></transactionAmounts>
</nonDerivativeTransaction></nonDerivativeTable></ownershipDocument>"""
            calls = []
            def transport(url, contact):
                calls.append(url)
                if url.endswith("/wk-form4.xml"):
                    return Response(200, ownership_xml)
                body = mapping if "/files/" in url else submissions if "/submissions/" in url else financials if "/companyfacts/" in url else None
                if "-submissions-001.json" in url:
                    body = historical
                return Response(200, json.dumps(body).encode() if body is not None else html)
            def sec_factory(cache, **kwargs):
                return SecClient(cache, **kwargs, transport=transport, now=lambda: NOW, sleep=lambda _: None, monotonic=lambda: 0)
            def session_factory(policy, *, tickers, state_dir, cache):
                return SimpleNamespace(live_boundary=RequestBoundary(policy, tickers=tickers, cache=cache, now=lambda: NOW, sleep=lambda _:None), close=lambda: None)
            def market(securities, *, cache, calendar, session, **kwargs):
                if fail_primary:
                    raise ValueError("YAHOO_HTTP_503")
                self.assertEqual(set(securities[0]), {"security_id", "ticker", "currency"})
                raw = json.dumps({"chart": {"error": None, "result": [{"meta": {"symbol": "TEST", "instrumentType": "EQUITY",
                    "currency": "USD", "exchangeName": "NYQ" if wrong_exchange else "NMS", "exchangeTimezoneName": "America/New_York"}}]}}).encode()
                session.live_boundary.request(Mock(return_value=SimpleNamespace(status_code=200, content=raw, headers={})),
                    "GET", "https://query1.finance.yahoo.com/v8/finance/chart/TEST")
                record = cache.store({"synthetic": "price", "provider": "yahoo"}, b"synthetic price", retrieved_at=NOW.isoformat())
                prices = normalize_daily_rows([{"date": "2026-09-09", "close": 20}], security_id="TEST", ticker="TEST",
                    retrieved_at=NOW.isoformat(), calendar=calendar, raw_content_hash=record["raw_content_hash"], currency="USD")
                return dict(prices, records={"TEST": record})
            try:
                from product.mcp.live.market import ExchangeCalendar
                calendar_factory = ExchangeCalendar if importlib.util.find_spec("exchange_calendars") else FrozenCalendar
                result = collect_live_snapshot(portfolio, access_path=source, output_dir=directory / "out", cache_root=directory / "cache",
                    sec_user_agent="synthetic contact@example.invalid", now=lambda: NOW, sec_factory=sec_factory,
                    session_factory=session_factory, market_collector=market, calendar_factory=calendar_factory, **factories)
            except ValueError:
                if not routed or directory_failure == "corrupt" or wrong_exchange:
                    raise
                self.fail((directory / "out/collection-error.json").read_text())
            self.assertEqual(result["status"], "FROZEN")
            snapshot = json.loads(Path(result["snapshot_path"]).read_text())
            if routed:
                self.assertEqual(snapshot["schema_version"], "live-snapshot/4.0.0")
                chosen = snapshot["source_selections"][0]
                self.assertEqual(chosen["selected_provider"], "eastmoney" if fail_primary else "yahoo")
                self.assertEqual(len(chosen["attempts"]), 2 if fail_primary else 1)
            self.assertEqual(snapshot["decision_cutoff"], "2026-09-10T10:00:00Z")
            self.assertEqual(len(calls), 5 if missing_history or ownership else 4)
            if missing_history:
                event = next(e for e in snapshot["collection_events"] if e.get("producer") == "sec-history-parser")
                self.assertEqual(event["coverage"], "PARTIAL_LISTED_HISTORY")
                self.assertEqual(event["excluded"][0]["accession"], "0000000001-00-000001")
                self.assertTrue(any("SEC_HISTORY_DOCUMENT_MISSING" in gap for gap in snapshot["gaps"]))
                self.assertFalse(any(f.get("accession") == "0000000001-00-000001" for f in snapshot["facts"]))
            self.assertTrue(any(f["kind"] == "derived" for f in snapshot["facts"]))
            self.assertTrue(any(f["kind"] == "disclosure" for f in snapshot["facts"]))
            if ownership:
                ownership_fact = next(
                    fact for fact in snapshot["facts"]
                    if fact.get("semantic_field") == "ownership_insider_transaction"
                )
                self.assertTrue(ownership_fact["source_locator"].endswith("/wk-form4.xml"))
                self.assertNotIn("/xslF345X06/", ownership_fact["source_locator"])
                self.assertIn(
                    "/xslF345X06/",
                    ownership_fact["metadata"]["submission_document_url"],
                )
                ownership_event = next(
                    event for event in snapshot["collection_events"]
                    if event.get("producer") == "sec-ownership-parser"
                )
                self.assertEqual(ownership_event["coverage"], "FORMS_3_4_5_TRANSACTION_TABLES_ONLY")
                self.assertNotIn("/xslF345X06/", ownership_event["raw_document_url"])
            self.assertEqual(snapshot["identity"]["security_metadata"][0]["security_type"], "COMMON_STOCK")
            if collection_only:
                binding = snapshot["identity"]["binding"]["bindings"][0]
                self.assertEqual("XNAS", binding["exchange"])
                self.assertEqual("common", binding["share_class"])
                frozen = json.loads(Path(result["portfolio_path"]).read_text())
                self.assertNotIn("mandate", frozen)
                self.assertNotIn("holding_horizon", frozen)
            self.assertNotIn("contact@example.invalid", json.dumps(snapshot))
            validate_raw_records(snapshot, lambda digest: (directory / "cache/objects" / digest).read_bytes())


if __name__ == "__main__":
    unittest.main()
