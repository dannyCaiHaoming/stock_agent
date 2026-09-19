"""Research Memory 双时点生产契约链路；所有外部传输均为合成替身。"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock

from product.intake import build_handoff, build_manual_draft
from product.mcp.live.cache import SnapshotCache
from product.mcp.live.eastmoney_transport import (
    ADAPTER_VERSION as EASTMONEY_ADAPTER_VERSION,
    AKSHARE_VERSION,
    EastmoneyClient,
)
from product.mcp.live.market import normalize_daily_rows
from product.mcp.live.nasdaq import NasdaqClient
from product.mcp.live.sec import ADAPTER_VERSION as SEC_ADAPTER_VERSION
from product.mcp.live.sec_client import CLIENT_VERSION as SEC_CLIENT_VERSION
from product.mcp.live.sec_client import Response, SecClient
from product.mcp.live.yahoo_transport import RequestBoundary
from product.runtime.common_stock_data import collect_common_stock_data_from_handoff
from product.runtime.common_stock_stage import (
    build_common_stock_dispatch_packet,
    prepare_common_stock_stage_run,
    validate_common_stock_stage_run_package,
)
from product.runtime.fixture_mcp import StatelessFixtureTools
from product.runtime.research_memory import ResearchMemory
from tests.test_live_admission import approved_access
from tests.test_live_nasdaq import access as nasdaq_access
from tests.test_live_nasdaq import page as nasdaq_page
from tests.test_live_yahoo_transport import access as yahoo_access


ROOT = Path(__file__).resolve().parents[1]
CIK = "0001835632"
ANNUAL = "0001835632-26-000001"
QUARTER = "0001835632-26-000002"


class SyntheticClock:
    def __init__(self, value: datetime):
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def mrvl_handoff() -> dict:
    draft = build_manual_draft({
        "draft_id": "synthetic-mrvl-memory-chain",
        "portfolio_scope": "USER_DEFINED_PORTFOLIO",
        "portfolio_complete": True,
        "source_id": "synthetic-mrvl-memory-chain",
        "as_of": "2026-09-09T20:00:00Z",
        "retrieved_at": "2026-09-09T20:01:00Z",
        "base_currency": "USD",
        "cash": 1000,
        "synthetic": True,
        "positions": [{"ticker": "MRVL", "quantity": 10, "cost_basis": 70}],
    })
    return build_handoff(
        draft, confirmed=True, confirmed_at="2026-09-09T20:02:00Z",
    )


def source_access() -> list[dict]:
    yahoo = approved_access(dict(
        yahoo_access(), checked_at="2026-09-10T00:00:00Z",
    ))
    sec = approved_access(dict(
        yahoo_access(), provider="sec", data_role="disclosure",
        client_version=SEC_CLIENT_VERSION, adapter_version=SEC_ADAPTER_VERSION,
        domains=["data.sec.gov", "www.sec.gov"], request_budget=30,
        checked_at="2026-09-10T00:00:00Z",
    ))
    nasdaq = approved_access(dict(
        nasdaq_access(), checked_at="2026-09-10T00:00:00Z",
    ))
    eastmoney = approved_access(dict(
        yahoo_access(), provider="eastmoney", data_role="backup_market",
        client_version=f"akshare/{AKSHARE_VERSION}",
        adapter_version=EASTMONEY_ADAPTER_VERSION,
        domains=["63.push2his.eastmoney.com"], request_budget=5,
        checked_at="2026-09-10T00:00:00Z",
    ))
    return [yahoo, sec, nasdaq, eastmoney]


class SyntheticProviders:
    def __init__(self, clock: SyntheticClock):
        self.clock = clock
        self.phase = "T0"
        self.sec_calls: list[str] = []
        self.market_ranges: list[tuple[str, str]] = []

    def submissions(self) -> dict:
        filings = [(ANNUAL, "10-K", "2026-03-10T12:00:00Z", "annual.htm", "2026-01-31")]
        if self.phase != "T0":
            filings.append((
                QUARTER, "10-Q", "2026-09-12T12:00:00Z",
                "quarter.htm", "2026-07-31",
            ))
        return {
            "cik": int(CIK),
            "filings": {
                "files": [],
                "recent": {
                    "accessionNumber": [item[0] for item in filings],
                    "form": [item[1] for item in filings],
                    "acceptanceDateTime": [item[2] for item in filings],
                    "primaryDocument": [item[3] for item in filings],
                    "reportDate": [item[4] for item in filings],
                },
            },
        }

    def companyfacts(self) -> dict:
        rows = [{
            "accn": ANNUAL, "form": "10-K", "val": 100,
            "start": "2025-02-01", "end": "2026-01-31",
            "fy": 2026, "fp": "FY",
        }]
        if self.phase != "T0":
            rows.append({
                "accn": QUARTER, "form": "10-Q", "val": 38,
                "start": "2026-05-01", "end": "2026-07-31",
                "fy": 2027, "fp": "Q2",
            })
        return {
            "cik": int(CIK),
            "facts": {"us-gaap": {"Revenues": {"units": {"USD": rows}}}},
        }

    @staticmethod
    def filing_html(label: str) -> bytes:
        return (
            '<ix:nonNumeric name="dei:Security12bTitle" contextRef="C">'
            'Common Stock</ix:nonNumeric>'
            '<ix:nonNumeric name="dei:TradingSymbol" contextRef="C">'
            'MRVL</ix:nonNumeric>'
            '<ix:nonNumeric name="dei:SecurityExchangeName" contextRef="C">'
            'NASDAQ</ix:nonNumeric>'
            f'<h2>Item 1. Business</h2><p>{label} synthetic products.</p>'
            '<h2>Item 1A. Risk Factors</h2><p>Synthetic supplier risk.</p>'
            '<h2>Item 7. Management Discussion</h2><p>Synthetic expansion.</p>'
        ).encode()

    def sec_transport(self, url: str, _contact: str) -> Response:
        self.sec_calls.append(url)
        if url.endswith("company_tickers_exchange.json"):
            body = {
                "fields": ["cik", "name", "ticker", "exchange"],
                "data": [[int(CIK), "Marvell Technology, Inc.", "MRVL", "Nasdaq"]],
            }
            return Response(200, json.dumps(body).encode())
        if "/submissions/" in url:
            return Response(200, json.dumps(self.submissions()).encode())
        if "/companyfacts/" in url:
            return Response(200, json.dumps(self.companyfacts()).encode())
        if url.endswith("annual.htm"):
            return Response(200, self.filing_html("annual"))
        if url.endswith("quarter.htm"):
            return Response(200, self.filing_html("quarter"))
        raise AssertionError(url)

    def sec_factory(self, cache, **kwargs):
        return SecClient(
            cache, **kwargs, transport=self.sec_transport,
            now=self.clock, sleep=lambda _seconds: None, monotonic=lambda: 0,
        )

    def session_factory(self, policy, *, tickers, state_dir, cache):
        return SimpleNamespace(
            live_boundary=RequestBoundary(
                policy, tickers=tickers, cache=cache, now=self.clock,
                sleep=lambda _seconds: None,
            ),
            close=lambda: None,
        )

    def market_collector(
        self, securities, *, start, end, cache, calendar, session, **_kwargs,
    ):
        self.market_ranges.append((start, end))
        raw_quote = json.dumps({
            "chart": {"error": None, "result": [{"meta": {
                "symbol": "MRVL", "instrumentType": "EQUITY",
                "currency": "USD", "exchangeName": "NMS",
                "exchangeTimezoneName": "America/New_York",
            }}]},
        }).encode()
        session.live_boundary.request(
            Mock(return_value=SimpleNamespace(
                status_code=200, content=raw_quote, headers={},
            )),
            "GET", "https://query1.finance.yahoo.com/v8/finance/chart/MRVL",
        )
        available = [
            {
                "date": "2026-09-09", "open": 70, "high": 72, "low": 69,
                "close": 71, "adjusted_close": 71, "volume": 1000,
                "dividends": 0, "stock_splits": 0,
            },
        ]
        if self.phase != "T0":
            available.append({
                "date": "2026-09-14", "open": 72, "high": 75, "low": 71,
                "close": 73 if self.phase != "T1" else 74,
                "adjusted_close": 73 if self.phase != "T1" else 74,
                "volume": 1200,
                "dividends": 0, "stock_splits": 0,
            })
        repair_phases = {
            "REVISION", "REPAIRED", "STALE_REPAIR", "CACHE_SWITCH",
            "REPAIR_INCOMPLETE",
        }
        if self.phase in repair_phases:
            for day in (
                "2026-09-10", "2026-09-11", "2026-09-15", "2026-09-16",
                "2026-09-17", "2026-09-18", "2026-09-21", "2026-09-22",
                "2026-09-23",
            ):
                if day > self.clock().date().isoformat():
                    continue
                available.append({
                    "date": day, "open": 74, "high": 76, "low": 73,
                    "close": 75, "adjusted_close": 75, "volume": 1300,
                    "dividends": 0, "stock_splits": 0,
                })
        if self.phase == "REPAIR_INCOMPLETE":
            available = [row for row in available if row["date"] != "2026-09-09"]
        rows = [item for item in available if start <= item["date"] < end]
        raw = json.dumps(rows, sort_keys=True).encode()
        key = {
            "provider": "yahoo", "ticker": "MRVL",
            "security_id": securities[0]["security_id"], "currency": "USD",
            "start": start, "end": end, "interval": "1d",
            "adapter_version": "yahoo-eod-adapter/0.2.0",
            "synthetic_transport": True,
        }
        record = cache.store(key, raw, retrieved_at=self.clock().isoformat())
        normalized = normalize_daily_rows(
            rows, security_id=securities[0]["security_id"], ticker="MRVL",
            retrieved_at=self.clock().isoformat(), calendar=calendar,
            raw_content_hash=record["raw_content_hash"], currency="USD",
        )
        return {
            **normalized, "records": {"MRVL": record},
            "sdk_calls": 1, "cache_hits": 0, "fetched_symbols": 1,
            "actual_http_requests": 1,
        }

    def universe_factory(self, access, cache):
        return NasdaqClient(
            access, cache, transport=lambda *_args, **_kwargs: nasdaq_page(["MRVL"], 1),
            now=self.clock, sleep=lambda _seconds: None,
        )

    def backup_factory(self, access, cache):
        raw = json.dumps({
            "rc": 0,
            "data": {"code": "MRVL", "market": 105, "klines": []},
        }).encode()
        return EastmoneyClient(
            access, cache,
            transport=lambda *_args, **_kwargs: Response(200, raw),
            now=self.clock, sleep=lambda _seconds: None,
        )

    def options(self) -> dict:
        return {
            "now": self.clock,
            "sec_factory": self.sec_factory,
            "session_factory": self.session_factory,
            "market_collector": self.market_collector,
            "universe_factory": self.universe_factory,
            "backup_factory": self.backup_factory,
        }


class ResearchMemoryChainTests(unittest.TestCase):
    def test_t0_restart_and_t1_incremental_chain_without_model(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temporary:
            root = Path(temporary)
            memory_root = root / "stable-memory"
            handoff_path = root / "mrvl-handoff.json"
            access_path = root / "source-access.json"
            handoff_path.write_text(json.dumps(mrvl_handoff()), encoding="utf-8")
            access_path.write_text(json.dumps(source_access()), encoding="utf-8")
            clock = SyntheticClock(datetime(2026, 9, 10, 22, tzinfo=UTC))
            providers = SyntheticProviders(clock)

            def collect(
                run_id: str, name: str, *, cache_override: Path | None = None,
            ) -> dict:
                return collect_common_stock_data_from_handoff(
                    handoff_path, access_path=access_path,
                    output_dir=root / name, cache_root=cache_override,
                    sec_user_agent="synthetic-chain contact@example.invalid",
                    run_id=run_id, repository_root=ROOT,
                    memory_root=memory_root,
                    collection_options=providers.options(),
                    planning_now=clock,
                )

            t0 = collect("synthetic-mrvl-t0", "data-t0")
            memory = ResearchMemory(memory_root)
            with memory.session() as connection:
                t0_versions = connection.execute(
                    "SELECT COUNT(*) FROM fact_versions"
                ).fetchone()[0]
                t0_checkpoints = connection.execute(
                    "SELECT COUNT(*) FROM dataset_state"
                ).fetchone()[0]
            self.assertGreater(
                t0_versions, 0,
                msg="\n".join(
                    path.read_text()
                    for path in (root / "data-t0").rglob("*error.json")
                ) or (root / "data-t0/source-bundle.json").read_text(),
            )
            self.assertGreaterEqual(t0_checkpoints, 6)
            t0_calls = list(providers.sec_calls)
            t0_ranges = list(providers.market_ranges)

            # A fresh process/run directory reads the persisted snapshot bundle;
            # no provider boundary is entered and no fact version is duplicated.
            clock.value = datetime(2026, 9, 10, 23, tzinfo=UTC)
            restarted = collect("synthetic-mrvl-t0-restart", "data-t0-restart")
            self.assertEqual(t0_calls, providers.sec_calls)
            self.assertEqual(t0_ranges, providers.market_ranges)
            restart_manifest = json.loads(
                (root / "data-t0-restart/research-memory/manifest.json").read_text()
            )
            self.assertEqual(
                {"CACHE_HIT"},
                {item["mode"] for item in restart_manifest["results"]},
            )
            with memory.session() as connection:
                self.assertEqual(t0_versions, connection.execute(
                    "SELECT COUNT(*) FROM fact_versions"
                ).fetchone()[0])

            t0_bundle = json.loads((root / "data-t0/source-bundle.json").read_text())
            snapshot_t0 = json.loads(
                (root / "data-t0" / t0_bundle["items"][0]["snapshot_ref"]).read_text()
            )
            cache = SnapshotCache(memory_root / "raw-cache")

            # Cross the freshness boundary and add one completed session and one
            # accession.  The request remains a bounded tail and the immutable
            # annual filing is served from verified cache.
            providers.phase = "T1"
            clock.value = datetime(2026, 9, 15, 22, tzinfo=UTC)
            t1 = collect("synthetic-mrvl-t1", "data-t1")
            t1_bundle = json.loads((root / "data-t1/source-bundle.json").read_text())
            self.assertEqual(
                {"FROZEN"}, {item["status"] for item in t1_bundle["items"]},
                msg="\n".join(
                    path.read_text()
                    for path in (root / "data-t1").rglob("*error.json")
                ) or json.dumps(t1_bundle, ensure_ascii=False),
            )
            with memory.session() as connection:
                t1_versions = connection.execute(
                    "SELECT COUNT(*) FROM fact_versions"
                ).fetchone()[0]
                t1_checkpoints = connection.execute(
                    "SELECT COUNT(*) FROM dataset_state"
                ).fetchone()[0]
            self.assertGreater(t1_versions, t0_versions)
            self.assertEqual(t0_checkpoints, t1_checkpoints)
            t1_yahoo_checkpoint = memory.checkpoint(
                "US:COMMON_STOCK:MRVL", "yahoo", "yahoo_daily",
            )
            self.assertTrue(any(
                item.get("reason") == "YAHOO_COMPLETED_SESSION_MISSING"
                for item in t1_yahoo_checkpoint["pending"]
            ))
            self.assertGreater(providers.market_ranges[-1][0], "2025-09-10")
            annual_url = f"/{ANNUAL.replace('-', '')}/annual.htm"
            quarter_url = f"/{QUARTER.replace('-', '')}/quarter.htm"
            self.assertEqual(1, sum(annual_url in url for url in providers.sec_calls))
            self.assertEqual(1, sum(quarter_url in url for url in providers.sec_calls))

            self.assertTrue(snapshot_t0["raw_records"])
            for record in snapshot_t0["raw_records"]:
                self.assertTrue(cache.read(record))

            t1_snapshot = json.loads(
                (root / "data-t1" / t1_bundle["items"][0]["snapshot_ref"]).read_text()
            )
            t1_records = {
                record["raw_content_hash"]: record
                for record in t1_snapshot["raw_records"]
            }
            required_raw = {
                fact["raw_content_hash"]
                for fact in t1_snapshot["facts"]
                if fact["kind"] != "derived"
            }
            self.assertLessEqual(required_raw, set(t1_records))
            for digest in required_raw:
                self.assertTrue(cache.read(t1_records[digest]))

            # Both frozen runs prepare a real Company task and pass the exact
            # pre-launch package validator.  No model process is started here.
            for label, data, result in (
                ("t0", root / "data-t0", t0),
                ("t1", root / "data-t1", t1),
            ):
                run_dir = root / f"company-{label}"
                run_id = f"synthetic-mrvl-{label}"
                prepared = prepare_common_stock_stage_run(
                    ROOT, handoff_path=handoff_path,
                    gate_path=Path(result["gate"]),
                    data_preparation_path=Path(result["data_preparation"]),
                    source_bundle_path=Path(result["source_bundle"]),
                    run_dir=run_dir, run_id=run_id,
                    model="gpt-5.6-terra", memory_root=memory_root,
                    research_question="合成 MRVL 双时点持久化链路验证。",
                )
                self.assertEqual(1, prepared["task_count"], msg=(label, prepared))
                validation = validate_common_stock_stage_run_package(ROOT, run_dir)
                self.assertEqual("PREPARED", validation["status"])
                self.assertEqual(1, validation["dispatch_count"])
                self.assertEqual(0, validation["llm_calls"])
                request_path = next((run_dir / "research/requests").glob("*.json"))
                request = json.loads(request_path.read_text())
                self.assertTrue(request["allowed_evidence_ids"])

            t1_request = json.loads(next(
                (root / "company-t1/research/requests").glob("*.json")
            ).read_text())
            self.assertTrue(any(
                evidence_id not in json.dumps(snapshot_t0)
                for evidence_id in t1_request["allowed_evidence_ids"]
            ))
            dispatch = json.loads(
                (root / "company-t1/research/dispatch-index.json").read_text()
            )
            packet = build_common_stock_dispatch_packet(
                ROOT, root / "company-t1", dispatch["tasks"][0]["task_name"],
            )
            new_evidence_id = next(
                evidence_id for evidence_id in t1_request["allowed_evidence_ids"]
                if evidence_id not in {fact["evidence_id"] for fact in snapshot_t0["facts"]}
            )
            identity = packet["identity"]
            queried = StatelessFixtureTools(
                default_run_dir=root / "company-t1",
            ).query(
                run_id=identity["run_id"], agent=identity["agent"],
                invocation_id=identity["invocation_id"],
                evidence_ids=[new_evidence_id],
            )
            self.assertEqual(
                new_evidence_id, queried["evidence"][0]["evidence_id"],
            )

            # A retroactive price-basis revision is withheld from dependent
            # consumers until the bounded bootstrap repair succeeds.
            providers.phase = "REVISION"
            clock.value = datetime(2026, 9, 16, 23, tzinfo=UTC)
            revised = collect("synthetic-mrvl-revision", "data-revision")
            revised_bundle = json.loads(
                (root / "data-revision/source-bundle.json").read_text()
            )
            self.assertEqual(
                {"FROZEN"},
                {item["status"] for item in revised_bundle["items"]},
                msg=revised_bundle,
            )
            revised_checkpoint = memory.checkpoint(
                "US:COMMON_STOCK:MRVL", "yahoo", "yahoo_daily",
            )
            with memory.session() as connection:
                revised_attempt = json.loads(connection.execute(
                    "SELECT details_json FROM attempts WHERE dataset='yahoo_daily' "
                    "ORDER BY completed_at DESC LIMIT 1"
                ).fetchone()[0])
            self.assertTrue(any(
                item.get("reason") == "PRICE_BASIS_REVISION"
                for item in revised_checkpoint["pending"]
            ), msg=(revised_checkpoint, revised_attempt))
            self.assertFalse(any(
                item.get("reason") == "YAHOO_COMPLETED_SESSION_MISSING"
                for item in revised_checkpoint["pending"]
            ))
            revised_snapshot = json.loads(
                (root / "data-revision" / revised_bundle["items"][0]["snapshot_ref"]).read_text()
            )
            self.assertTrue(any(
                "YAHOO_PRICE_SERIES_REPAIR_PENDING" in gap
                for gap in revised_snapshot["gaps"]
            ))
            self.assertFalse(any(
                fact.get("semantic_field") == "adjusted_close_price"
                for fact in revised_snapshot["facts"]
            ))
            self.assertEqual("FROZEN", revised["status"])

            providers.phase = "REPAIRED"
            clock.value = datetime(2026, 9, 16, 23, 30, tzinfo=UTC)
            repaired = collect("synthetic-mrvl-repaired", "data-repaired")
            repaired_checkpoint = memory.checkpoint(
                "US:COMMON_STOCK:MRVL", "yahoo", "yahoo_daily",
            )
            self.assertEqual([], repaired_checkpoint["pending"])
            repaired_bundle = json.loads(
                (root / "data-repaired/source-bundle.json").read_text()
            )
            repaired_snapshot = json.loads(
                (root / "data-repaired" / repaired_bundle["items"][0]["snapshot_ref"]).read_text()
            )
            self.assertTrue(any(
                fact.get("semantic_field") == "adjusted_close_price"
                and str(fact.get("value")) == "73"
                for fact in repaired_snapshot["facts"]
            ))
            self.assertFalse(any(
                "YAHOO_PRICE_SERIES_REPAIR_PENDING" in gap
                for gap in repaired_snapshot["gaps"]
            ))
            self.assertEqual("FROZEN", repaired["status"])

            # A stale DELTA plan with a missing historical aggregate is
            # promoted to an explicit full-window repair before any checkpoint
            # advances. The rebuilt View must retain the old 9 September fact.
            repaired_old_fact = next(
                fact for fact in repaired_snapshot["facts"]
                if fact.get("semantic_field") == "adjusted_close_price"
                and fact.get("metadata", {}).get("trading_date") == "2026-09-09"
            )
            repaired_record = next(
                record for record in repaired_snapshot["raw_records"]
                if record["raw_content_hash"] == repaired_old_fact["raw_content_hash"]
            )
            (cache.root / "objects" / repaired_record["raw_content_hash"]).unlink()
            providers.phase = "STALE_REPAIR"
            clock.value = datetime(2026, 9, 18, 22, tzinfo=UTC)
            stale_repair = collect("synthetic-mrvl-stale-repair", "data-stale-repair")
            stale_bundle = json.loads(
                (root / "data-stale-repair/source-bundle.json").read_text()
            )
            self.assertEqual(
                "FROZEN", stale_bundle["items"][0]["status"],
                msg=stale_bundle,
            )
            stale_manifest = json.loads(
                (root / "data-stale-repair/research-memory/manifest.json").read_text()
            )
            stale_plan = stale_manifest["results"][0]["plans"]["yahoo_daily"]
            self.assertEqual("RAW_CLOSURE_REPAIR", stale_plan["reason"])
            self.assertLessEqual(stale_plan["request_range"]["start"], "2025-09-18")
            stale_snapshot = json.loads(
                (root / "data-stale-repair" / stale_bundle["items"][0]["snapshot_ref"]).read_text()
            )
            self.assertTrue(any(
                fact.get("semantic_field") == "adjusted_close_price"
                and fact.get("metadata", {}).get("trading_date") == "2026-09-09"
                for fact in stale_snapshot["facts"]
            ))

            # Switching cache A→B cannot reuse A's bundle. Because the current
            # bounded sources cannot reconstruct every retained fact in an
            # empty B cache, the security fails without advancing success.
            alternate_cache_root = root / "alternate-cache"
            revision_before_switch = memory.checkpoint(
                "US:COMMON_STOCK:MRVL", "yahoo", "yahoo_daily",
            )["revision"]
            providers.phase = "CACHE_SWITCH"
            clock.value = datetime(2026, 9, 21, 22, tzinfo=UTC)
            collect(
                "synthetic-mrvl-cache-switch", "data-cache-switch",
                cache_override=alternate_cache_root,
            )
            switch_bundle = json.loads(
                (root / "data-cache-switch/source-bundle.json").read_text()
            )
            self.assertEqual("FAILED", switch_bundle["items"][0]["status"])
            self.assertEqual(
                "RESEARCH_MEMORY_RAW_CLOSURE_REPAIR_INCOMPLETE",
                switch_bundle["items"][0]["failure_code"],
            )
            self.assertEqual(
                revision_before_switch,
                memory.checkpoint(
                    "US:COMMON_STOCK:MRVL", "yahoo", "yahoo_daily",
                )["revision"],
            )

            # If a corrupt A object cannot be reconstructed because the repair
            # response omits a retained old fact, fail before advancing the
            # successful yahoo checkpoint.
            stale_old_fact = next(
                fact for fact in stale_snapshot["facts"]
                if fact.get("semantic_field") == "adjusted_close_price"
                and fact.get("metadata", {}).get("trading_date") == "2026-09-09"
            )
            stale_old_record = next(
                record for record in stale_snapshot["raw_records"]
                if record["raw_content_hash"] == stale_old_fact["raw_content_hash"]
            )
            (cache.root / "objects" / stale_old_record["raw_content_hash"]).write_bytes(
                b"tampered"
            )
            revision_before_incomplete = memory.checkpoint(
                "US:COMMON_STOCK:MRVL", "yahoo", "yahoo_daily",
            )["revision"]
            providers.phase = "REPAIR_INCOMPLETE"
            clock.value = datetime(2026, 9, 23, 22, tzinfo=UTC)
            collect(
                "synthetic-mrvl-incomplete-repair", "data-incomplete-repair",
            )
            incomplete_bundle = json.loads(
                (root / "data-incomplete-repair/source-bundle.json").read_text()
            )
            self.assertEqual("FAILED", incomplete_bundle["items"][0]["status"])
            self.assertEqual(
                "RESEARCH_MEMORY_RAW_CLOSURE_REPAIR_INCOMPLETE",
                incomplete_bundle["items"][0]["failure_code"],
            )
            self.assertEqual(
                revision_before_incomplete,
                memory.checkpoint(
                    "US:COMMON_STOCK:MRVL", "yahoo", "yahoo_daily",
                )["revision"],
            )
            self.assertEqual("FROZEN", stale_repair["status"])
            self.assertEqual("FROZEN", restarted["status"])
            self.assertEqual("FROZEN", t1["status"])


if __name__ == "__main__":
    unittest.main()
