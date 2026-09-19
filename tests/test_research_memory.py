from __future__ import annotations

import json
import multiprocessing
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

from product.runtime.research_memory import (
    ResearchMemory,
    ResearchMemoryError,
    fact_content_hash,
    logical_fact_key,
    report_reuse_key,
    research_input_fingerprint,
    resolve_memory_root,
)
from product.runtime.common_stock_data import (
    CommonStockDataError,
    _dataset_request_evidence,
    _failed_dataset_statuses,
    _preflight_repaired_raw_closure,
    _snapshot_bundle_cache_valid,
    _structured_snapshot_gaps,
    _yahoo_pending_from_gaps,
)


def _hold_lock(root: str, ready: multiprocessing.Queue) -> None:
    memory = ResearchMemory(Path(root))
    with memory.dataset_lock("US:MRVL", "yahoo", "yahoo_daily"):
        ready.put(True)
        time.sleep(0.35)


def _commit_under_lock(root: str, ready: multiprocessing.Queue) -> None:
    memory = ResearchMemory(Path(root))
    with memory.dataset_lock("US:MRVL", "yahoo", "yahoo_daily"):
        plan = memory.plan(
            "US:MRVL", "yahoo", "yahoo_daily",
            planning_as_of="2026-09-10T21:00:00Z",
        )
        fact = ResearchMemoryTests.fact(
            evidence_id="ev-yahoo-process", source_id="yahoo-daily",
            semantic_field="adjusted_close_price", value="75", unit="USD",
            as_of="2026-09-10T20:00:00Z",
            published_at="2026-09-10T20:00:00Z",
            retrieved_at="2026-09-10T21:00:00Z",
        )
        memory.ingest_dataset(
            plan=plan, facts=[fact], status="FETCHED_BOOTSTRAP",
            completed_at="2026-09-10T21:00:00Z", watermark=fact["as_of"],
        )
        ready.put(True)


class ResearchMemoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "memory"
        self.root.mkdir(mode=0o700)
        self.memory = ResearchMemory(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def fact(**updates):
        value = {
            "evidence_id": "ev-first",
            "security_id": "US:MRVL",
            "source_id": "sec-companyfacts-0001835632",
            "source_locator": "https://data.sec.gov/example",
            "semantic_field": "revenue",
            "value": "100",
            "unit": "USD",
            "currency": "USD",
            "as_of": "2026-01-31T00:00:00Z",
            "published_at": "2026-03-01T00:00:00Z",
            "retrieved_at": "2026-03-02T00:00:00Z",
            "raw_content_hash": "a" * 64,
            "metadata": {"tag": "Revenues", "period_end": "2026-01-31", "accession": "0001"},
        }
        value.update(updates)
        return value

    def test_external_root_precedence_and_rejection(self):
        repository = Path(__file__).resolve().parents[1]
        explicit = Path(self.temporary.name) / "explicit"
        env = Path(self.temporary.name) / "environment"
        self.assertEqual(explicit.resolve(), resolve_memory_root(repository, explicit, environment={"RESEARCH_MEMORY_ROOT": str(env)}))
        self.assertEqual(env.resolve(), resolve_memory_root(repository, None, environment={"RESEARCH_MEMORY_ROOT": str(env)}))
        with self.assertRaisesRegex(ResearchMemoryError, "RESEARCH_MEMORY_ROOT_REQUIRED"):
            resolve_memory_root(repository, None, environment={})
        with self.assertRaisesRegex(ResearchMemoryError, "RESEARCH_MEMORY_MUST_BE_EXTERNAL"):
            resolve_memory_root(repository, repository / ".private-memory")

    def test_snapshot_bundle_is_bound_to_its_canonical_cache_root(self):
        first = Path(self.temporary.name) / "cache-a"
        second = Path(self.temporary.name) / "cache-b"
        bundle = {
            "cache_root": str(first.resolve()),
            "snapshot": {"snapshot_hash": "a" * 64},
        }
        self.assertTrue(_snapshot_bundle_cache_valid(bundle, cache_root=first))
        self.assertFalse(_snapshot_bundle_cache_valid(bundle, cache_root=second))

    def test_collection_failure_maps_affected_and_unattempted_datasets(self):
        plans = {
            dataset: {"dataset": dataset}
            for dataset in (
                "live_snapshot", "company_profile", "sec_companyfacts",
                "sec_documents", "sec_identity", "current_snapshot",
                "yahoo_daily",
            )
        }
        snapshot_dir = Path(self.temporary.name) / "failed-snapshot"
        snapshot_dir.mkdir()
        (snapshot_dir / "collection-error.json").write_text(json.dumps({
            "failure_code": "YAHOO_TRANSPORT_FAILURE",
            "failed_stage": "YAHOO_COLLECTION",
        }))
        statuses = _failed_dataset_statuses(
            plans, snapshot_dir=snapshot_dir,
            failure_code="YAHOO_TRANSPORT_FAILURE",
        )
        self.assertEqual("SOURCE_LIMITED", statuses["live_snapshot"])
        self.assertEqual("SOURCE_LIMITED", statuses["current_snapshot"])
        self.assertEqual("SOURCE_LIMITED", statuses["yahoo_daily"])
        self.assertEqual("NOT_ATTEMPTED", statuses["sec_documents"])
        (snapshot_dir / "collection-error.json").write_text(json.dumps({
            "failure_code": "LIVE_SELECTION_EVIDENCE_MISMATCH",
            "failed_stage": "FREEZE",
        }))
        statuses = _failed_dataset_statuses(
            plans, snapshot_dir=snapshot_dir,
            failure_code="LIVE_SELECTION_EVIDENCE_MISMATCH",
        )
        self.assertEqual("FAILED_VALIDATION", statuses["live_snapshot"])
        self.assertEqual("NOT_ATTEMPTED", statuses["yahoo_daily"])

    def test_schema_restart_integrity_and_backup(self):
        self.memory.integrity_check()
        restarted = ResearchMemory(self.root)
        restarted.integrity_check()
        stored = restarted.store_object({"backup": "referenced-object"})
        backup = restarted.backup(Path(self.temporary.name) / "backup")
        self.assertTrue((backup / "research-memory.sqlite3").is_file())
        self.assertTrue((backup / "objects").is_dir())
        restored = ResearchMemory(backup)
        self.assertEqual(
            {"backup": "referenced-object"},
            json.loads(restored.read_object(
                stored["object_ref"], stored["object_hash"]
            )),
        )
        with restarted.session() as connection:
            connection.execute("PRAGMA user_version = 999")
        with self.assertRaisesRegex(ResearchMemoryError, "SCHEMA_NEWER"):
            ResearchMemory(self.root)

    def test_version_one_report_index_migrates_transactionally(self):
        with self.memory.session() as connection:
            connection.executescript("""
                PRAGMA foreign_keys = OFF;
                DROP TABLE reuse_events;
                DROP TABLE reports;
                CREATE TABLE reports (
                    reuse_key TEXT PRIMARY KEY,
                    security_id TEXT NOT NULL,
                    research_input_fingerprint TEXT NOT NULL,
                    report_hash TEXT NOT NULL,
                    package_hash TEXT NOT NULL,
                    package_ref TEXT NOT NULL,
                    original_run_id TEXT NOT NULL,
                    original_invocation_id TEXT NOT NULL,
                    original_report_cutoff TEXT NOT NULL,
                    research_status TEXT NOT NULL,
                    stored_at TEXT NOT NULL,
                    metadata_json TEXT NOT NULL
                );
                CREATE TABLE reuse_events (
                    event_hash TEXT PRIMARY KEY,
                    reuse_key TEXT NOT NULL REFERENCES reports(reuse_key),
                    run_id TEXT NOT NULL,
                    checked_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                PRAGMA user_version = 1;
                PRAGMA foreign_keys = ON;
            """)
            connection.execute(
                "INSERT INTO reports VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "reuse-1", "US:MRVL", "fingerprint-1", "a" * 64,
                    "b" * 64, "objects/" + "b" * 64, "run-1", "inv-1",
                    "2026-09-10T00:00:00Z", "VALID_RESEARCH",
                    "2026-09-11T00:00:00Z", "{}",
                ),
            )
            connection.execute(
                "INSERT INTO reuse_events VALUES(?,?,?,?,?)",
                (
                    "event-1", "reuse-1", "run-2",
                    "2026-09-12T00:00:00Z", "{}",
                ),
            )
        with patch(
            "product.runtime.research_memory.report_entry_id",
            side_effect=RuntimeError("synthetic migration failure"),
        ):
            with self.assertRaises(sqlite3.OperationalError):
                ResearchMemory(self.root)
        with closing(sqlite3.connect(self.root / "research-memory.sqlite3")) as connection:
            self.assertEqual(1, connection.execute("PRAGMA user_version").fetchone()[0])
            self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM reports").fetchone()[0])
            self.assertIsNone(connection.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='reports_v1'"
            ).fetchone())
        migrated = ResearchMemory(self.root)
        with migrated.session() as connection:
            self.assertEqual(2, connection.execute("PRAGMA user_version").fetchone()[0])
            columns = {
                row[1] for row in connection.execute("PRAGMA table_info(reports)")
            }
            self.assertEqual(
                (1, 1),
                (
                    connection.execute("SELECT COUNT(*) FROM reports").fetchone()[0],
                    connection.execute("SELECT COUNT(*) FROM reuse_events").fetchone()[0],
                ),
            )
        self.assertIn("entry_id", columns)

    def test_semantic_dedup_separates_observations_and_revisions(self):
        plan = self.memory.plan("US:MRVL", "sec", "sec_companyfacts", planning_as_of="2026-03-02T00:00:00Z")
        first = self.fact()
        outcome = self.memory.ingest_dataset(
            plan=plan, facts=[first], status="FETCHED_BOOTSTRAP",
            completed_at="2026-03-02T00:00:00Z", watermark=first["as_of"],
        )
        self.assertEqual(1, outcome["inserted_versions"])
        plan = self.memory.plan("US:MRVL", "sec", "sec_companyfacts", planning_as_of="2026-03-04T00:00:00Z")
        second = self.fact(
            evidence_id="ev-retrieved-again", retrieved_at="2026-03-04T00:00:00Z",
            raw_content_hash="b" * 64, source_locator="https://data.sec.gov/reordered",
        )
        self.assertEqual(logical_fact_key(first), logical_fact_key(second))
        self.assertEqual(fact_content_hash(first), fact_content_hash(second))
        outcome = self.memory.ingest_dataset(
            plan=plan, facts=[second], status="CHECKED_NO_CHANGE",
            completed_at="2026-03-04T00:00:00Z", watermark=first["as_of"],
        )
        self.assertEqual(0, outcome["inserted_versions"])
        self.assertEqual(1, outcome["observations"])
        plan = self.memory.plan("US:MRVL", "sec", "sec_companyfacts", planning_as_of="2026-03-06T00:00:00Z")
        revision = self.fact(
            evidence_id="ev-revision", value="110", published_at="2026-03-05T00:00:00Z",
            retrieved_at="2026-03-06T00:00:00Z", raw_content_hash="c" * 64,
        )
        self.assertEqual(1, self.memory.revision_count([revision]))
        outcome = self.memory.ingest_dataset(
            plan=plan, facts=[revision], status="FETCHED_INCREMENTAL",
            completed_at="2026-03-06T00:00:00Z", watermark=revision["as_of"],
        )
        self.assertEqual(1, outcome["inserted_versions"])
        plan = self.memory.plan(
            "US:MRVL", "sec", "sec_companyfacts",
            planning_as_of="2026-03-08T00:00:00Z",
        )
        new_accession = self.fact(
            evidence_id="ev-new-accession", value="120",
            published_at="2026-03-07T00:00:00Z",
            retrieved_at="2026-03-08T00:00:00Z",
            raw_content_hash="d" * 64,
            metadata={
                "tag": "Revenues", "period_end": "2026-01-31",
                "accession": "0002",
            },
        )
        self.assertEqual(0, self.memory.revision_count([new_accession]))
        outcome = self.memory.ingest_dataset(
            plan=plan, facts=[new_accession], status="FETCHED_INCREMENTAL",
            completed_at="2026-03-08T00:00:00Z",
            watermark=new_accession["as_of"],
        )
        self.assertEqual(1, outcome["inserted_versions"])
        current = self.memory.current_facts("US:MRVL", "2026-03-06T23:59:59Z")
        self.assertEqual(["110"], [item["value"] for item in current])
        later = self.memory.current_facts("US:MRVL", "2026-03-09T00:00:00Z")
        self.assertEqual({"110", "120"}, {item["value"] for item in later})

    def test_raw_closure_preflight_only_exempts_a_winning_new_version(self):
        plan = self.memory.plan(
            "US:MRVL", "sec", "sec_companyfacts",
            planning_as_of="2026-03-02T00:00:00Z",
        )
        known_old = self.fact(
            evidence_id="ev-known-old", value="90",
            published_at="2026-02-01T00:00:00Z",
            retrieved_at="2026-02-02T00:00:00Z",
            raw_content_hash="b" * 64,
        )
        current = self.fact(evidence_id="ev-current")
        self.memory.ingest_dataset(
            plan=plan, facts=[known_old, current], status="FETCHED_BOOTSTRAP",
            completed_at="2026-03-02T00:00:00Z", watermark=current["as_of"],
        )
        cache_root = Path(self.temporary.name) / "raw-cache"
        cache_root.mkdir()

        def preflight(candidate):
            _preflight_repaired_raw_closure(
                memory=self.memory,
                security_id="US:MRVL",
                snapshot={
                    "decision_cutoff": "2026-05-01T00:00:00Z",
                    "facts": [candidate],
                    "raw_records": [],
                },
                prior_bundle=None,
                cache_root=cache_root,
            )

        with self.assertRaisesRegex(
            CommonStockDataError,
            "RESEARCH_MEMORY_RAW_CLOSURE_REPAIR_INCOMPLETE",
        ):
            preflight(known_old)

        lower_rank_new = self.fact(
            evidence_id="ev-lower-rank-new", value="80",
            published_at="2026-01-01T00:00:00Z",
            retrieved_at="2026-04-01T00:00:00Z",
            raw_content_hash="c" * 64,
        )
        with self.assertRaisesRegex(
            CommonStockDataError,
            "RESEARCH_MEMORY_RAW_CLOSURE_REPAIR_INCOMPLETE",
        ):
            preflight(lower_rank_new)

        winning_new = self.fact(
            evidence_id="ev-winning-new", value="110",
            published_at="2026-04-01T00:00:00Z",
            retrieved_at="2026-04-02T00:00:00Z",
            raw_content_hash="d" * 64,
        )
        preflight(winning_new)

    def test_yahoo_window_and_response_order_do_not_create_false_versions(self):
        plan = self.memory.plan(
            "US:MRVL", "yahoo", "yahoo_daily",
            planning_as_of="2026-09-10T21:00:00Z",
        )
        facts = [
            self.fact(
                evidence_id=f"ev-yahoo-{day}", source_id="yahoo-daily",
                semantic_field="adjusted_close_price", value=value, unit="USD",
                as_of=f"2026-09-{day}T20:00:00Z",
                published_at=f"2026-09-{day}T20:00:00Z",
                retrieved_at="2026-09-10T21:00:00Z",
                metadata={"trading_date": f"2026-09-{day}"},
            )
            for day, value in (("09", "74"), ("10", "75"))
        ]
        first = self.memory.ingest_dataset(
            plan=plan, facts=facts, status="FETCHED_BOOTSTRAP",
            completed_at="2026-09-10T21:00:00Z", watermark=facts[-1]["as_of"],
        )
        self.assertEqual(2, first["inserted_versions"])
        overlap = self.memory.plan(
            "US:MRVL", "yahoo", "yahoo_daily",
            planning_as_of="2026-09-12T22:00:00Z",
        )
        reordered = [
            dict(
                fact,
                evidence_id=f"{fact['evidence_id']}-again",
                retrieved_at="2026-09-12T22:00:00Z",
                raw_content_hash="e" * 64,
            )
            for fact in reversed(facts)
        ]
        second = self.memory.ingest_dataset(
            plan=overlap, facts=reordered, status="CHECKED_NO_CHANGE",
            completed_at="2026-09-12T22:00:00Z", watermark=facts[-1]["as_of"],
        )
        self.assertEqual(0, second["inserted_versions"])
        self.assertEqual(2, second["observations"])

    def test_checkpoint_failure_does_not_advance(self):
        plan = self.memory.plan("US:MRVL", "yahoo", "yahoo_daily", planning_as_of="2026-09-10T00:00:00Z")
        self.memory.record_failed_attempt(
            plan=plan, status="SOURCE_LIMITED", completed_at="2026-09-10T00:01:00Z",
        )
        self.assertIsNone(self.memory.checkpoint("US:MRVL", "yahoo", "yahoo_daily"))
        successful = self.fact(
            evidence_id="ev-yahoo", source_id="yahoo-MRVL", semantic_field="adjusted_close_price",
            value="75", unit="USD", as_of="2026-09-10T20:00:00Z",
            published_at="2026-09-10T20:00:00Z", retrieved_at="2026-09-10T21:00:00Z",
        )
        self.memory.ingest_dataset(
            plan=plan, facts=[successful], status="FETCHED_BOOTSTRAP",
            completed_at="2026-09-10T21:00:00Z", watermark=successful["as_of"],
            coverage=[{"start": "2025-09-10", "end": "2026-09-10"}],
            pending=[{"start": "2026-01-02", "end": "2026-01-02"}],
        )
        checkpoint = self.memory.checkpoint("US:MRVL", "yahoo", "yahoo_daily")
        self.assertEqual(1, checkpoint["revision"])
        self.assertEqual(1, len(checkpoint["pending"]))
        repair = self.memory.plan(
            "US:MRVL", "yahoo", "yahoo_daily",
            planning_as_of="2026-09-12T22:00:00Z",
        )
        self.assertEqual("KNOWN_GAP", repair["reason"])
        self.assertEqual("2026-01-02", repair["request_range"]["start"])

    def test_frozen_string_gaps_drive_pending_and_unknowns_remain_diagnostic(self):
        structured, diagnostics = _structured_snapshot_gaps([
            json.dumps({
                "security_id": "US:MRVL", "date": "2026-09-08",
                "reason": "YAHOO_COMPLETED_SESSION_MISSING",
            }),
            "provider returned an unstructured warning",
            json.dumps({"security_id": "US:OTHER", "date": "2026-09-09"}),
        ], security_id="US:MRVL")
        self.assertEqual(["2026-09-08"], [item["date"] for item in structured])
        self.assertEqual(["SNAPSHOT_GAP_NOT_JSON"], diagnostics)
        self.assertEqual(
            [{
                "start": "2026-09-08", "end": "2026-09-08",
                "reason": "YAHOO_COMPLETED_SESSION_MISSING",
            }],
            _yahoo_pending_from_gaps([
                *structured,
                {"date": "2026-09-12", "reason": "NOT_COMPLETED_REGULAR_SESSION"},
            ]),
        )

        evidence = _dataset_request_evidence({
            "collection_events": [
                {
                    "producer": "yahoo-daily-collector", "status": "checked",
                    "sdk_calls": 1, "actual_http_requests": 2,
                },
                {
                    "endpoint": "https://query1.finance.yahoo.com/v8/finance/chart/MRVL",
                    "status": "fetched", "request_number": 1,
                },
            ],
        }, "yahoo_daily")
        self.assertTrue(evidence["attempted"])
        self.assertEqual(1, evidence["logical_request_count"])
        self.assertEqual(2, evidence["actual_http_requests"])
        self.assertEqual(1, evidence["retry_count"])

        eastmoney_evidence = _dataset_request_evidence({
            "collection_events": [{
                "producer": "live-market-routing",
                "status": "checked",
                "source_selection": {"selected_provider": "eastmoney"},
            }, {
                "endpoint": "https://63.push2his.eastmoney.com/api/qt/stock/kline/get",
                "provider": "eastmoney", "status": "fetched",
                "request_number": 1,
            }],
            "source_selections": [{
                "security_id": "US:MRVL", "selected_provider": "eastmoney",
            }],
        }, "current_snapshot")
        self.assertEqual(["eastmoney"], eastmoney_evidence["actual_providers"])
        self.assertEqual(1, eastmoney_evidence["logical_request_count"])
        self.assertEqual(1, eastmoney_evidence["actual_http_requests"])
        self.assertEqual(0, eastmoney_evidence["retry_count"])

        market_plan = self.memory.plan(
            "US:MRVL", "market", "current_snapshot",
            planning_as_of="2026-09-10T21:00:00Z",
        )
        market_fact = self.fact(
            evidence_id="ev-eastmoney-close", source_id="eastmoney-kline",
            semantic_field="close_price", value="74", unit="USD",
            as_of="2026-09-10T20:00:00Z",
            published_at="2026-09-10T20:00:00Z",
            retrieved_at="2026-09-10T21:00:00Z",
        )
        outcome = self.memory.ingest_dataset(
            plan=market_plan, facts=[market_fact], status="FETCHED_BOOTSTRAP",
            completed_at="2026-09-10T21:00:00Z",
            details=eastmoney_evidence,
        )
        self.assertEqual(1, outcome["inserted_versions"])
        self.assertIsNotNone(self.memory.checkpoint(
            "US:MRVL", "market", "current_snapshot",
        ))
        self.assertIsNone(self.memory.checkpoint(
            "US:MRVL", "yahoo", "current_snapshot",
        ))

    def test_not_attempted_is_audit_only_and_does_not_create_checkpoint(self):
        plan = self.memory.plan(
            "US:MRVL", "public", "company_profile",
            planning_as_of="2026-09-10T00:00:00Z",
        )
        attempt_id = self.memory.record_attempt_only(
            plan=plan, status="NOT_ATTEMPTED",
            completed_at="2026-09-10T00:00:01Z",
            details={"failure_code": "COMPANY_PROFILE_SOURCE_NOT_IN_CORE_COLLECTION"},
        )
        self.assertTrue(attempt_id)
        self.assertIsNone(self.memory.checkpoint(
            "US:MRVL", "public", "company_profile",
        ))

    def test_ingest_rejects_failure_status_and_cross_bound_facts(self):
        plan = self.memory.plan(
            "US:MRVL", "sec", "sec_companyfacts",
            planning_as_of="2026-03-02T00:00:00Z",
        )
        with self.assertRaisesRegex(
            ResearchMemoryError, "INGEST_STATUS_NOT_SUCCESS",
        ):
            self.memory.ingest_dataset(
                plan=plan, facts=[], status="SOURCE_LIMITED",
                completed_at="2026-03-02T00:00:01Z",
            )
        self.assertIsNone(self.memory.checkpoint(
            "US:MRVL", "sec", "sec_companyfacts",
        ))
        cases = (
            (dict(self.fact(), security_id="US:OTHER"), plan, "SECURITY_MISMATCH"),
            (
                dict(self.fact(), source_id="sec-filing-0001"), plan,
                "DATASET_MISMATCH",
            ),
            (
                self.fact(),
                self.memory.plan(
                    "US:MRVL", "other", "sec_companyfacts",
                    planning_as_of="2026-03-02T00:00:00Z",
                ),
                "PROVIDER_MISMATCH",
            ),
        )
        for fact, bound_plan, error in cases:
            with self.subTest(error=error), self.assertRaisesRegex(
                ResearchMemoryError, error,
            ):
                self.memory.ingest_dataset(
                    plan=bound_plan, facts=[fact], status="FETCHED_BOOTSTRAP",
                    completed_at="2026-03-02T00:00:01Z",
                )

    def test_fresh_restart_skips_and_stale_checkpoint_plans_bounded_delta(self):
        plan = self.memory.plan(
            "US:MRVL", "yahoo", "yahoo_daily",
            planning_as_of="2026-09-10T21:00:00Z",
        )
        fact = self.fact(
            evidence_id="ev-yahoo-daily", source_id="yahoo-daily",
            semantic_field="adjusted_close_price", value="75", unit="USD",
            as_of="2026-09-10T20:00:00Z",
            published_at="2026-09-10T20:00:00Z",
            retrieved_at="2026-09-10T21:00:00Z",
        )
        self.memory.ingest_dataset(
            plan=plan, facts=[fact], status="FETCHED_BOOTSTRAP",
            completed_at="2026-09-10T21:00:00Z", watermark=fact["as_of"],
        )
        restarted = ResearchMemory(self.root)
        fresh = restarted.plan(
            "US:MRVL", "yahoo", "yahoo_daily",
            planning_as_of="2026-09-11T20:59:00Z",
        )
        self.assertEqual("SKIP_FRESH", fresh["mode"])
        stale = restarted.plan(
            "US:MRVL", "yahoo", "yahoo_daily",
            planning_as_of="2026-09-12T22:00:00Z",
        )
        self.assertEqual("DELTA", stale["mode"])
        self.assertEqual(5, stale["policy"]["overlap_sessions"])
        self.assertGreater(stale["request_range"]["start"], "2025-09-10")
        self.assertEqual("2026-09-13", stale["request_range"]["end"])

    def test_atomic_ingest_rolls_back_versions_attempt_and_checkpoint(self):
        initial = self.memory.plan(
            "US:MRVL", "sec", "sec_companyfacts",
            planning_as_of="2026-03-02T00:00:00Z",
        )
        original = self.fact()
        self.memory.ingest_dataset(
            plan=initial, facts=[original], status="FETCHED_BOOTSTRAP",
            completed_at="2026-03-02T00:00:00Z", watermark=original["as_of"],
        )
        revision = self.memory.plan(
            "US:MRVL", "sec", "sec_companyfacts",
            planning_as_of="2026-03-04T00:00:00Z",
        )
        conflicting = self.fact(
            value="999", published_at="2026-03-03T00:00:00Z",
            retrieved_at="2026-03-04T00:00:00Z",
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.memory.ingest_dataset(
                plan=revision, facts=[conflicting], status="FETCHED_INCREMENTAL",
                completed_at="2026-03-04T00:00:00Z",
                watermark=conflicting["as_of"],
            )
        checkpoint = self.memory.checkpoint(
            "US:MRVL", "sec", "sec_companyfacts"
        )
        self.assertEqual(1, checkpoint["revision"])
        self.assertEqual(
            ["100"],
            [item["value"] for item in self.memory.current_facts(
                "US:MRVL", "2026-03-05T00:00:00Z"
            )],
        )

    def test_checkpoint_object_state_commits_atomically_and_stale_plan_cannot_replace_it(self):
        initial = self.memory.plan(
            "US:MRVL", "sec", "sec_companyfacts",
            planning_as_of="2026-03-02T00:00:00Z",
        )
        stale = dict(initial)
        first_object = self.memory.store_object({"generation": "first"})
        original = self.fact()
        self.memory.ingest_dataset(
            plan=initial, facts=[original], status="FETCHED_BOOTSTRAP",
            completed_at="2026-03-02T00:00:00Z", watermark=original["as_of"],
            state=first_object,
        )
        checkpoint = self.memory.checkpoint(
            "US:MRVL", "sec", "sec_companyfacts"
        )
        self.assertEqual(first_object, checkpoint["state"])

        replacement = self.memory.store_object({"generation": "stale"})
        with self.assertRaisesRegex(
            ResearchMemoryError, "RESEARCH_MEMORY_CHECKPOINT_REVISION_CONFLICT",
        ):
            self.memory.ingest_dataset(
                plan=stale, facts=[], status="CHECKED_NO_CHANGE",
                completed_at="2026-03-03T00:00:00Z", state=replacement,
            )
        self.assertEqual(
            first_object,
            self.memory.checkpoint(
                "US:MRVL", "sec", "sec_companyfacts"
            )["state"],
        )

        current = self.memory.plan(
            "US:MRVL", "sec", "sec_companyfacts",
            planning_as_of="2026-03-04T00:00:00Z",
        )
        orphan = self.memory.store_object({"generation": "orphan-after-rollback"})
        revision = self.fact(
            evidence_id="ev-atomic-state-revision", value="101",
            published_at="2026-03-03T00:00:00Z",
            retrieved_at="2026-03-04T00:00:00Z",
            raw_content_hash="d" * 64,
        )
        with self.memory.session() as connection:
            attempts_before = connection.execute(
                "SELECT COUNT(*) FROM attempts"
            ).fetchone()[0]
            connection.execute("""
                CREATE TRIGGER fail_atomic_checkpoint_update
                BEFORE UPDATE ON dataset_state
                BEGIN
                    SELECT RAISE(ABORT, 'synthetic checkpoint failure');
                END
            """)
        with self.assertRaisesRegex(sqlite3.IntegrityError, "synthetic checkpoint failure"):
            self.memory.ingest_dataset(
                plan=current, facts=[revision], status="FETCHED_INCREMENTAL",
                completed_at="2026-03-04T00:00:00Z", watermark=revision["as_of"],
                state=orphan,
            )
        with self.memory.session() as connection:
            attempts_after = connection.execute(
                "SELECT COUNT(*) FROM attempts"
            ).fetchone()[0]
        self.assertEqual(attempts_before, attempts_after)
        self.assertEqual(
            first_object,
            self.memory.checkpoint(
                "US:MRVL", "sec", "sec_companyfacts"
            )["state"],
        )
        self.assertEqual(
            ["100"],
            [item["value"] for item in self.memory.current_facts(
                "US:MRVL", "2026-03-05T00:00:00Z"
            )],
        )
        self.assertEqual(
            {"generation": "orphan-after-rollback"},
            json.loads(self.memory.read_object(
                orphan["object_ref"], orphan["object_hash"]
            )),
        )

    def test_file_lock_has_bounded_timeout_and_process_release(self):
        ready: multiprocessing.Queue = multiprocessing.Queue()
        process = multiprocessing.Process(target=_hold_lock, args=(str(self.root), ready))
        process.start()
        self.assertTrue(ready.get(timeout=2))
        with self.assertRaisesRegex(ResearchMemoryError, "LOCK_TIMEOUT"):
            with self.memory.dataset_lock("US:MRVL", "yahoo", "yahoo_daily", timeout_seconds=0.05):
                pass
        process.join(timeout=2)
        self.assertEqual(0, process.exitcode)
        with self.memory.dataset_lock("US:MRVL", "yahoo", "yahoo_daily", timeout_seconds=0.2):
            pass

    def test_lock_then_replan_prevents_duplicate_refresh_and_stale_commit(self):
        stale_plan = self.memory.plan(
            "US:MRVL", "yahoo", "yahoo_daily",
            planning_as_of="2026-09-10T21:00:00Z",
        )
        ready: multiprocessing.Queue = multiprocessing.Queue()
        process = multiprocessing.Process(
            target=_commit_under_lock, args=(str(self.root), ready)
        )
        process.start()
        self.assertTrue(ready.get(timeout=2))
        process.join(timeout=2)
        self.assertEqual(0, process.exitcode)
        with self.memory.dataset_lock(
            "US:MRVL", "yahoo", "yahoo_daily", timeout_seconds=0.2,
        ):
            replanned = self.memory.plan(
                "US:MRVL", "yahoo", "yahoo_daily",
                planning_as_of="2026-09-11T20:00:00Z",
            )
        self.assertEqual("SKIP_FRESH", replanned["mode"])
        with self.assertRaisesRegex(ResearchMemoryError, "REVISION_CONFLICT"):
            self.memory.ingest_dataset(
                plan=stale_plan, facts=[], status="CHECKED_NO_CHANGE",
                completed_at="2026-09-11T20:00:00Z",
            )

    def test_fingerprint_is_closed_and_includes_user_and_attachment_inputs(self):
        base = {
            "security": {"security_id": "US:MRVL"}, "evidence": ["v1"],
            "gaps": [], "conflicts": [], "attachments": ["a1"], "calculations": [],
            "research_question": "分析持仓", "holding_horizon": "三年",
            "user_context": {"user_thesis": "AI demand", "user_questions": []},
            "model": {"name": "gpt"}, "agent_binding": {"hash": "a"},
            "skill_bindings": [{"hash": "s"}], "schema_hash": "schema",
            "prompt_policy": "p1", "data_policy": "d1", "risk_policy": "r1",
            "adapter_versions": ["v1"], "time_context": {"age_bucket": "fresh"},
        }
        first = research_input_fingerprint(base)
        changed = dict(base, attachments=["a2"])
        self.assertNotEqual(first, research_input_fingerprint(changed))
        self.assertNotEqual(report_reuse_key("US:MRVL", first), report_reuse_key("US:MRVL", research_input_fingerprint(changed)))
        with self.assertRaisesRegex(ResearchMemoryError, "FIELDS_INVALID"):
            research_input_fingerprint(dict(base, unclassified_new_input=True))

    def test_snapshot_object_and_view_survive_restart(self):
        snapshot = {"snapshot_hash": "a" * 64, "decision_cutoff": "2026-09-17T00:00:00Z"}
        stored = self.memory.store_snapshot_bundle(
            security_id="US:MRVL", portfolio={"id": "p"}, snapshot=snapshot,
            calendar={"version": "c"},
        )
        raw = self.memory.read_object(stored["object_ref"], stored["object_hash"])
        self.assertEqual(snapshot, json.loads(raw)["snapshot"])
        view = self.memory.save_view(
            run_id="run-1", security_id="US:MRVL", decision_cutoff="2026-09-17T00:00:00Z",
            facts=[self.fact()], gaps=[], conflicts=[],
        )
        self.assertEqual(64, len(view["view_manifest_hash"]))


if __name__ == "__main__":
    unittest.main()
