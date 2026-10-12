"""真实解析/冻结路径＋内存 HTTP 响应；禁止以本测试宣称真实取数。"""
from datetime import datetime, timedelta, UTC
import json
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from product.mcp.live.collection import collect_live_snapshot, collect_single_stock_snapshot
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

    def test_single_stock_uses_same_collection_and_gate_without_portfolio(self):
        self.collect_case(routed=True, single_stock=True)

    def test_single_stock_source_package_reconstructs_and_memory_has_no_account(self):
        self.collect_case(routed=True, single_stock=True, single_package=True)

    def test_single_stock_final_materials_package_is_consumed_by_company_and_eight(self):
        self.collect_case(routed=True, single_stock=True, single_package=True, final_package=True)

    def test_single_stock_shared_context_keeps_benchmark_macro_provenance_and_pit(self):
        self.collect_case(routed=True, single_stock=True, single_package=True, shared_context=True)

    def test_single_stock_source_package_preserves_excluded_source_facts(self):
        self.collect_case(routed=True, single_stock=True, single_package=True, future_financial=True)

    def test_missing_history_document_is_frozen_as_gap_not_evidence(self):
        self.collect_case(routed=True, missing_history=True)

    def test_collection_resolves_sec_xsl_ownership_document_to_raw_xml(self):
        self.collect_case(routed=True, ownership=True)

    def test_peer_scope_omits_unneeded_ownership_fetch(self):
        self.collect_case(routed=True, ownership=True, peer_scope=True)

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
                     missing_history=False, collection_only=False, ownership=False,
                     peer_scope=False, single_stock=False, single_package=False, final_package=False, shared_context=False,
                     future_financial=False):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp).resolve()
            ticker = "ALB" if single_stock else "TEST"
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
                    return page([ticker], 1)
                factories = {"universe_factory": lambda a, c: NasdaqClient(a, c,
                    transport=directory_transport, now=lambda: NOW, sleep=lambda _: None),
                    "backup_factory": lambda a, c: EastmoneyClient(a, c,
                    transport=lambda *args, **kw: Response(200, raw), now=lambda: NOW, sleep=lambda _: None)}
            mapping = {"fields": ["cik", "name", "ticker", "exchange"], "data": [[1, "Synthetic", ticker, "NYSE" if single_stock else "Nasdaq"]]}
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
            if future_financial:
                financials['facts']['us-gaap']['Revenues']['units']['USD'].append({
                    'val': 1000, 'start': '2026-01-01', 'end': '2027-12-31',
                    'accn': '0000000001-26-000001', 'form': '10-K',
                })
            historical = {"accessionNumber": ["0000000001-00-000001"], "form": ["10-K"],
                "primaryDocument": [""], "reportDate": ["1999-12-31"],
                "acceptanceDateTime": ["2000-02-01T12:00:00Z"]}
            if missing_history:
                submissions["filings"]["files"] = [{"name": "CIK0000000001-submissions-001.json"}]
            html = ('<ix:nonNumeric name="dei:Security12bTitle" contextRef="C">Common Stock</ix:nonNumeric>'
                    f'<ix:nonNumeric name="dei:TradingSymbol" contextRef="C">{ticker}</ix:nonNumeric>'
                    f'<ix:nonNumeric name="dei:SecurityExchangeName" contextRef="C">{"NYSE" if single_stock else "NASDAQ"}</ix:nonNumeric>'
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
                self.assertEqual(kwargs["start"], (NOW.date() - timedelta(days=550)).isoformat())
                raw = json.dumps({"chart": {"error": None, "result": [{"meta": {"symbol": ticker, "instrumentType": "EQUITY",
                    "currency": "USD", "exchangeName": "NYQ" if wrong_exchange or single_stock else "NMS", "exchangeTimezoneName": "America/New_York"}}]}}).encode()
                session.live_boundary.request(Mock(return_value=SimpleNamespace(status_code=200, content=raw, headers={})),
                    "GET", f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}")
                record = cache.store({"synthetic": "price", "provider": "yahoo"}, b"synthetic price", retrieved_at=NOW.isoformat())
                prices = normalize_daily_rows([{"date": "2026-09-09", "close": 20}], security_id=securities[0]["security_id"], ticker=ticker,
                    retrieved_at=NOW.isoformat(), calendar=calendar, raw_content_hash=record["raw_content_hash"], currency="USD")
                return dict(prices, records={"TEST": record})
            try:
                from product.mcp.live.market import ExchangeCalendar
                calendar_factory = ExchangeCalendar if importlib.util.find_spec("exchange_calendars") else FrozenCalendar
                collector = collect_single_stock_snapshot if single_stock else collect_live_snapshot
                result = collector(ticker if single_stock else portfolio, access_path=source, output_dir=directory / "out", cache_root=directory / "cache",
                    sec_user_agent="synthetic contact@example.invalid", now=lambda: NOW, sec_factory=sec_factory,
                    session_factory=session_factory, market_collector=market, calendar_factory=calendar_factory,
                    peer_scope=peer_scope, **factories)
            except ValueError:
                if not routed or directory_failure == "corrupt" or wrong_exchange:
                    raise
                self.fail((directory / "out/collection-error.json").read_text())
            self.assertEqual(result["status"], "FROZEN")
            snapshot = json.loads(Path(result["snapshot_path"]).read_text())
            if routed:
                self.assertEqual(snapshot["schema_version"], "live-research-snapshot/1.0.0" if single_stock else "live-snapshot/4.0.0")
                chosen = snapshot["source_selections"][0]
                self.assertEqual(chosen["selected_provider"], "eastmoney" if fail_primary else "yahoo")
                self.assertEqual(len(chosen["attempts"]), 2 if fail_primary else 1)
            self.assertEqual(snapshot["decision_cutoff"], "2026-09-10T10:00:00Z")
            self.assertEqual(len(calls), 5 if missing_history or (ownership and not peer_scope) else 4)
            if missing_history:
                event = next(e for e in snapshot["collection_events"] if e.get("producer") == "sec-history-parser")
                self.assertEqual(event["coverage"], "PARTIAL_LISTED_HISTORY")
                self.assertEqual(event["excluded"][0]["accession"], "0000000001-00-000001")
                self.assertTrue(any("SEC_HISTORY_DOCUMENT_MISSING" in gap for gap in snapshot["gaps"]))
                self.assertFalse(any(f.get("accession") == "0000000001-00-000001" for f in snapshot["facts"]))
            if not future_financial:
                self.assertTrue(any(f["kind"] == "derived" for f in snapshot["facts"]))
            self.assertTrue(any(f["kind"] == "disclosure" for f in snapshot["facts"]))
            if ownership and not peer_scope:
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
            if peer_scope:
                self.assertFalse(any(event.get("producer") == "sec-ownership-parser"
                                     for event in snapshot["collection_events"]))
            if single_stock:
                from product.runtime.evidence_gate import run_live_evidence_gate
                gate = run_live_evidence_gate(snapshot, run_id="synthetic-single-alb",
                    calendar=calendar_factory(start="2025-01-01", end="2026-09-12"))
                self.assertTrue(gate.artifact["allowed_evidence_ids"])
                self.assertEqual(snapshot["research_request"]["security"]["exchange"], "XNYS")
                self.assertFalse((directory / "out/portfolio.json").exists())
                self.assertNotIn("portfolio_hash", snapshot)
                self.assertNotIn("identity", snapshot)
            else:
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
            if single_package:
                from product.runtime.common_stock_data import collect_single_stock_research_data, validate_common_stock_source_bundle
                from product.mcp.live.research_supplement_collection import _failure
                options = dict(now=lambda: NOW, sec_factory=sec_factory, session_factory=session_factory,
                    market_collector=market, calendar_factory=calendar_factory, **factories)
                from contextlib import ExitStack
                with ExitStack() as context:
                    if shared_context:
                        from product.mcp.live.macro import normalize_treasury_csv
                        from product.runtime.hashing import canonical_hash
                        treasury = normalize_treasury_csv(b'Date,10-Year\n09/09/2026,4.25\n',
                            retrieved_at=NOW.isoformat(), endpoint='https://home.treasury.gov/synthetic')
                        macro_facts = treasury['evidence']
                        market_fact = dict(snapshot['facts'][0], evidence_id='synthetic-benchmark', security_id='US:SPY')
                        def writer(value):
                            def freeze(**kwargs):
                                value['snapshot_hash'] = canonical_hash({k: v for k, v in value.items() if k != 'snapshot_hash'})
                                kwargs['output_path'].write_text(json.dumps(value))
                                return value
                            return freeze
                        for target, value in (
                            ('product.runtime.common_stock_data.collect_benchmark_research_series', {
                                'benchmark_id': 'US:SPY', 'status': 'AVAILABLE', 'evidence': [market_fact], 'gaps': []}),
                            ('product.mcp.live.macro.collect_official_macro_snapshot', {
                                'status': 'AVAILABLE', 'decision_cutoff': NOW.isoformat(), 'evidence': macro_facts, 'gaps': [], 'excluded': []}),
                            ('product.mcp.live.market_context.collect_market_context_snapshot', {
                                'status': 'SOURCE_LIMITED', 'decision_cutoff': NOW.isoformat(), 'evidence': [], 'gaps': []}),
                            ('product.mcp.live.options.collect_portfolio_option_snapshots', {
                                'status': 'SOURCE_LIMITED', 'decision_cutoff': NOW.isoformat(), 'security_ids': ['US:COMMON_STOCK:ALB'], 'evidence': [], 'gaps': []}),
                        ):
                            context.enter_context(patch(target, side_effect=writer(value)))
                    context.enter_context(patch('product.mcp.live.research_supplement_collection.capture_external_research_results', return_value={'US:COMMON_STOCK:ALB': []}))
                    context.enter_context(patch('product.mcp.live.research_supplement_collection.capture_shared_research_results', return_value=[]))
                    context.enter_context(patch('product.mcp.live.research_supplement_collection.capture_public_company_news_result', return_value=_failure('moomoo_sg', 'event_context', 'SYNTHETIC_SOURCE_LIMITED')))
                    package_result = collect_single_stock_research_data('ALB', access_path=source,
                        output_dir=directory / 'data', sec_user_agent='synthetic contact@example.invalid',
                        run_id='single-package-test', repository_root=ROOT, memory_root=directory / 'memory',
                        benchmark_id='US:SPY' if shared_context else None,
                        benchmark_ticker='SPY' if shared_context else None, collection_options=options)
                request = json.loads(Path(package_result['research_request']).read_text())
                gate = json.loads(Path(package_result['gate']).read_text())
                preparation = json.loads(Path(package_result['data_preparation']).read_text())
                validate_common_stock_source_bundle(request, gate=gate, preparation=preparation,
                    source_bundle_path=Path(package_result['source_bundle']))
                self.assertNotIn('handoff_hash', preparation)
                self.assertNotIn('portfolio_hash', preparation)
                self.assertNotIn('account_source_as_of', preparation)
                if future_financial:
                    self.assertTrue(gate['excluded_evidence_ids'])
                    self.assertTrue(set(gate['excluded_evidence_ids']).issubset(gate['input_evidence_ids']))
                    self.assertTrue(set(gate['excluded_evidence_ids']).isdisjoint(gate['allowed_evidence_ids']))
                if shared_context:
                    admitted = {fact['evidence_id']: fact for fact in gate['allowed_evidence']}
                    self.assertEqual(admitted[market_fact['evidence_id']], market_fact)
                    for fact in macro_facts:
                        self.assertEqual(admitted[fact['evidence_id']], fact)
                        self.assertTrue(all(key in fact for key in ('source_id', 'as_of', 'retrieved_at')))
                    self.assertEqual(preparation['market_context']['status'], 'SOURCE_LIMITED')
                    self.assertNotIn('handoff_hash', request)
                if final_package:
                    from product.runtime.research_materials_stage import prepare_research_materials_stage
                    from product.runtime.common_stock_data import finalize_single_stock_research_data
                    from product.runtime.common_stock_stage import prepare_common_stock_stage_run, validate_common_stock_stage_run_package
                    from product.runtime.multidimensional_stage import prepare_multidimensional_stage_run
                    from tests.test_research_materials_stage import ResearchMaterialsStageTests, FakeOpenAlexClient
                    from datetime import datetime as Timestamp, timedelta as Duration
                    from product.mcp.provenance import content_hash
                    late_time = (Timestamp.fromisoformat(request['resolved_cutoff'].replace('Z', '+00:00'))
                                 + Duration(seconds=5)).isoformat().replace('+00:00', 'Z')
                    class LateBodyClient(FakeOpenAlexClient):
                        def fetch(self, candidate):
                            document = super().fetch(candidate)
                            document['retrieved_at'] = late_time
                            return document
                    materials = directory / 'materials'
                    original_hash = Path(package_result['research_request']).read_bytes()
                    prepare_research_materials_stage(ROOT, research_input_path=Path(package_result['research_request']),
                        gate_path=Path(package_result['gate']), peer_candidate_pool_path=Path(package_result['peer_candidate_pool']),
                        run_dir=materials, run_id=gate['run_id'], model='gpt-6-luna', target_concurrency=8)
                    with patch('product.mcp.live.public_research.OpenAlexResearchClient', LateBodyClient):
                        helper = ResearchMaterialsStageTests()
                        helper.write_historical_fixture(materials)
                        helper.mark_material_process_success(materials)
                    result = finalize_single_stock_research_data(data_dir=directory / 'data', materials_run=materials,
                                                                output_dir=directory / 'final-data')
                    self.assertEqual(Path(package_result['research_request']).read_bytes(), original_hash)
                    self.assertEqual(result['resolved_cutoff'], late_time)
                    final_request = json.loads(Path(result['research_request_path']).read_text())
                    self.assertEqual(final_request['preparation_request_hash'], request['request_hash'])
                    self.assertNotEqual(final_request['request_hash'], request['request_hash'])
                    prepare_common_stock_stage_run(ROOT, research_input_path=Path(result['research_request_path']),
                        gate_path=Path(result['gate_path']), data_preparation_path=Path(result['data_preparation_path']),
                        source_bundle_path=Path(result['source_bundle_path']), run_dir=directory / 'company-plan',
                        run_id=gate['run_id'], model='gpt-6-luna')
                    validate_common_stock_stage_run_package(ROOT, directory / 'company-plan')
                    prepared = prepare_multidimensional_stage_run(ROOT, research_input_path=Path(result['research_request_path']),
                        gate_path=Path(result['gate_path']), peer_candidate_pool_path=Path(package_result['peer_candidate_pool']),
                        research_materials_run_path=materials, run_dir=directory / 'eight-plan',
                        run_id=gate['run_id'], model='gpt-6-luna', structured_report_submission=True, task_bound_tools=True)
                    self.assertEqual(prepared['task_count'], 8)
                    # Altering a copied original preparation request must not be
                    # repairable by resigning the final delivery envelope.
                    original_copy = directory / 'final-data/materials-source/audit/single-stock-request.json'
                    copied = json.loads(original_copy.read_text())
                    copied['research_question'] = 'different synthetic research scope'
                    copied['request_hash'] = content_hash({k: v for k, v in copied.items() if k != 'request_hash'})
                    original_copy.write_text(json.dumps(copied))
                    with self.assertRaises(ValueError):
                        validate_common_stock_source_bundle(final_request,
                            gate=json.loads(Path(result['gate_path']).read_text()),
                            preparation=json.loads(Path(result['data_preparation_path']).read_text()),
                            source_bundle_path=Path(result['source_bundle_path']))


if __name__ == "__main__":
    unittest.main()
