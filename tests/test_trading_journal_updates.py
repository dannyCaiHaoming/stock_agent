"""Fictional local-workspace facts and bounded updates; no network or models."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from product.trading_journal.common import JournalError, canonical_hash
from product.trading_journal.ledger import Ledger
from product.trading_journal.normalization import parse_csv
from product.trading_journal.privacy import private_root
from product.trading_journal.privacy import write_private
from product.trading_journal.updates import JournalUpdates
from product.trading_journal.windows import resolve_window
from tests.test_trading_journal_charts import candle, market
from tests.test_trading_journal_statement import single_group, header as statement_header, detail, encode

NOW = "2026-10-03T12:00:00Z"
ACCOUNT = "account-fictional"
OTHER = "account-unrelated"
HEADER = "Execution ID,Trade Time,Symbol,Asset Type,Market,Currency,Side,Quantity,Price,Total Fees\n"


def csv_rows(*rows, stable=True):
    text = HEADER if stable else HEADER.replace("Execution ID,", "")
    for row in rows:
        text += row + "\n" if stable else row.split(",", 1)[1] + "\n"
    return text.encode()


OLD = "old,2026-09-01T09:00:00-04:00,ACME,STOCK,US,USD,BUY,2,100,1"
NEW = "new,2026-09-25T09:00:00-04:00,ACME,STOCK,US,USD,SELL,1,110,1"


class JournalUpdatesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name) / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / ".gitignore").write_text("/product/.private/\n")
        (self.repo / "product").mkdir()
        self.storage = private_root(self.repo, create=True)
        with Ledger(self.storage):
            pass
        self.clock = patch("product.trading_journal.updates.utc_now", return_value=NOW)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.updates = JournalUpdates(self.repo, ACCOUNT, real=False)
        self.updates.import_csv(csv_rows(OLD), start="2026-09-01", end="2026-09-01")

    def fingerprint(self):
        return {str(path.relative_to(self.storage)): (hashlib.sha256(path.read_bytes()).hexdigest(),
                path.stat().st_mtime_ns, path.stat().st_mode & 0o777)
                for path in self.storage.rglob("*") if path.is_file()}

    def saved(self):
        with Ledger(self.storage, read_only=True) as ledger:
            return ledger.current_records(ACCOUNT), ledger.snapshots(ACCOUNT), ledger.batches(ACCOUNT)

    def seed_window(self, raw, start, end, account=ACCOUNT, market_package=None):
        source = Path(self.temp.name) / "seed.csv"
        source.write_bytes(raw)
        window = resolve_window("custom", start=start, end=end, now=NOW)
        records = parse_csv(source, account_ref=account, source_id="source-fictional",
                            as_of=window["end"], retrieved_at=NOW, source_timezone="America/New_York")
        with Ledger(self.storage) as ledger:
            ledger.import_records(records, source_hash=hashlib.sha256(raw).hexdigest(), requested_window=window)
            return ledger.freeze_snapshot(account, window=window, market=[market_package] if market_package else [])

    def fetch(self, *args, **kwargs):
        return market(candles=[candle("2026-09-01"), candle("2026-10-02")],
                      as_of="2026-10-03", retrieved_at=NOW, segments=[{"status": "FETCHED"}])

    def test_read_and_refresh_are_read_only_and_full_history_after_short_latest_window(self):
        self.seed_window(csv_rows(NEW), "2026-09-25", "2026-09-25")
        before = self.fingerprint()
        snapshot = self.updates.read_timeline()
        self.assertEqual(len(snapshot["records"]), 2)
        self.assertEqual(snapshot["context_records"], [])
        self.assertEqual(snapshot["coverage"]["all_saved_record_count"], 2)
        self.assertEqual(snapshot["coverage"]["status"], "PARTIAL")
        self.assertEqual(self.updates.refresh()["record_count"], 2)
        self.assertEqual(self.updates.read_timeline()["snapshot_id"], snapshot["snapshot_id"])
        self.assertEqual(self.fingerprint(), before)

    def test_same_instance_can_read_on_different_threads_without_shared_ledger(self):
        before = self.fingerprint()
        with ThreadPoolExecutor(max_workers=3) as pool:
            results = list(pool.map(lambda _: self.updates.read_timeline(), range(6)))
        self.assertTrue(all(len(item["records"]) == 1 for item in results))
        self.assertEqual(self.fingerprint(), before)

    def test_same_source_reimport_has_no_batch_snapshot_or_source_write(self):
        before = self.fingerprint()
        result = self.updates.import_csv(csv_rows(OLD), start="2026-09-01", end="2026-09-01")
        self.assertEqual(result["status"], "UNCHANGED")
        self.assertEqual(result["receipt"]["inserted"], 0)
        self.assertEqual(self.fingerprint(), before)

    def test_file_row_overlap_rejects_before_any_private_write(self):
        before = self.fingerprint()
        with self.assertRaises(JournalError) as failure:
            self.updates.import_csv(csv_rows(OLD, stable=False), start="2026-09-01", end="2026-09-01")
        self.assertEqual(failure.exception.code, "CSV_OVERLAP_UNPROVEN")
        self.assertEqual(self.fingerprint(), before)

    def test_declared_period_overlap_rejects_even_without_same_trading_day(self):
        before = self.fingerprint()
        with self.assertRaises(JournalError) as failure:
            self.updates.import_csv(csv_rows(NEW, stable=False), start="2026-09-01", end="2026-09-25")
        self.assertEqual(failure.exception.code, "CSV_OVERLAP_UNPROVEN")
        self.assertEqual(self.fingerprint(), before)

    def test_new_file_row_batch_retains_identical_same_second_fills_as_two_rows(self):
        result = self.updates.import_csv(csv_rows(NEW, NEW, stable=False), start="2026-09-25", end="2026-09-25")
        self.assertEqual(result["receipt"]["inserted"], 2)
        self.assertEqual(len(result["snapshot"]["records"]), 3)
        rows = [row for row in result["snapshot"]["records"] if row["occurred_at"].startswith("2026-09-25")]
        self.assertEqual(len({row["record_id"] for row in rows}), 2)
        self.assertTrue(all(not row["duplicate_candidate"] for row in rows))
        for path in (self.storage / "sources").glob("*.csv"):
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_stable_id_fee_revision_preserves_old_snapshot_and_revision(self):
        parent = self.updates.read_timeline()
        result = self.updates.import_csv(csv_rows(OLD[:-1] + "2"), start="2026-09-01", end="2026-09-01")
        self.assertEqual(result["receipt"]["revised"], 1)
        self.assertEqual(len(result["snapshot"]["records"]), 1)
        with Ledger(self.storage, read_only=True) as ledger:
            self.assertEqual(ledger.load_snapshot(parent["snapshot_id"])["records"][0]["fees"], "1")
            self.assertEqual(len(ledger.revisions(parent["records"][0]["record_id"])), 2)

    def test_outside_declared_period_future_period_and_duplicate_id_reject_without_write(self):
        for raw, start, end, expected in (
            (csv_rows(NEW), "2026-09-01", "2026-09-01", "CSV_OUTSIDE_DECLARED_WINDOW"),
            (csv_rows(NEW), "2026-09-25", "2026-10-04", "FUTURE_IMPORT_WINDOW"),
            (csv_rows(NEW, NEW), "2026-09-25", "2026-09-25", "SOURCE_ID_COLLISION"),
        ):
            with self.subTest(expected=expected):
                before = self.fingerprint()
                with self.assertRaises(JournalError) as failure:
                    self.updates.import_csv(raw, start=start, end=end)
                self.assertEqual(failure.exception.code, expected)
                self.assertEqual(self.fingerprint(), before)

    def test_account_scope_excludes_other_saved_account(self):
        self.seed_window(csv_rows(NEW), "2026-09-25", "2026-09-25", account=OTHER)
        self.assertTrue(all(row["account_ref"] == ACCOUNT for row in self.updates.read_timeline()["records"]))

    def test_market_update_uses_public_fields_and_preserves_old_snapshot(self):
        parent = self.updates.read_timeline()
        calls = []
        def fetch(identity, start, end, **kwargs):
            calls.append((identity, start, end, kwargs))
            return self.fetch(identity, start, end, **kwargs)
        self.updates.market_fetch = fetch
        result = self.updates.update_market(snapshot_id=parent["snapshot_id"])
        self.assertEqual(result["status"], "UPDATED")
        identity, start, end, kwargs = calls[0]
        self.assertEqual(start, "2026-09-01")
        self.assertEqual(end, "2026-10-03")
        self.assertNotIn("account_ref", identity)
        self.assertNotIn("price", identity)
        self.assertLessEqual(kwargs["request_budget"], 24)
        self.assertEqual(result["snapshot"]["parent_snapshot_id"], parent["snapshot_id"])
        with Ledger(self.storage, read_only=True) as ledger:
            self.assertEqual(ledger.load_snapshot(parent["snapshot_id"]), parent)

    def test_memory_timeline_can_update_without_missing_snapshot_error(self):
        self.seed_window(csv_rows(NEW), "2026-09-25", "2026-09-25")
        parent = self.updates.read_timeline()
        self.assertTrue(parent["snapshot_id"].startswith("snapshot-memory-"))
        self.updates.market_fetch = self.fetch
        result = self.updates.update_market(snapshot_id=parent["snapshot_id"])
        self.assertEqual(len(result["snapshot"]["records"]), 2)
        with Ledger(self.storage, read_only=True) as ledger:
            self.assertEqual(len(ledger.load_snapshot(result["snapshot"]["parent_snapshot_id"])["records"]), 2)

    def test_stock_and_multiple_options_request_underlying_once(self):
        self.updates.import_csv(csv_rows(
            "option1,2026-09-25T09:00:00-04:00,ACME261016C00100000,OPTION,US,USD,BUY,1,2,1",
            "option2,2026-09-25T09:00:00-04:00,ACME261120P00100000,OPTION,US,USD,SELL,1,3,1"),
            start="2026-09-25", end="2026-09-25")
        calls = []
        self.updates.market_fetch = lambda *args, **kwargs: calls.append(args) or self.fetch(*args, **kwargs)
        result = self.updates.update_market()
        self.assertEqual(result["status"], "UPDATED")
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(result["snapshot"]["market"]), 1)

    def test_network_failure_retains_previous_market_and_does_not_write(self):
        self.seed_window(csv_rows(NEW), "2026-09-25", "2026-09-25", market_package=market())
        before = self.fingerprint()
        def fail(*args, **kwargs):
            raise OSError("arbitrary sensitive upstream data")
        self.updates.market_fetch = fail
        result = self.updates.update_market()
        self.assertEqual(result["status"], "UNCHANGED")
        self.assertEqual(result["retained_symbols"], ["ACME"])
        self.assertNotIn("sensitive", json.dumps(result))
        self.assertEqual(self.fingerprint(), before)

    def test_partial_segment_update_keeps_old_candles_and_appends_new(self):
        self.seed_window(csv_rows(NEW), "2026-09-25", "2026-09-25", market_package=market())
        self.updates.market_fetch = lambda *args, **kwargs: market(
            candles=[candle("2026-10-02")], as_of="2026-10-03", retrieved_at=NOW,
            segments=[{"status": "FAILED"}, {"status": "FETCHED"}], gaps=[{"reason": "MARKET_TRANSPORT_FAILED"}])
        result = self.updates.update_market()
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual([row["date"] for row in result["snapshot"]["market"][0]["candles"]],
                         ["2026-09-01", "2026-10-02"])

    def test_price_basis_conflict_keeps_old_reliable_market(self):
        self.seed_window(csv_rows(NEW), "2026-09-25", "2026-09-25", market_package=market())
        before = self.fingerprint()
        self.updates.market_fetch = lambda *args, **kwargs: market(price_basis="PROVIDER_UNVERIFIED", candles=[candle("2026-10-02")])
        result = self.updates.update_market()
        self.assertEqual(result["status"], "UNCHANGED")
        self.assertEqual(result["failed_symbols"][0]["code"], "MARKET_BASIS_CONFLICT")
        self.assertEqual(self.fingerprint(), before)

    def test_future_candle_rejected_and_future_availability_not_upgraded_to_close(self):
        self.updates.market_fetch = lambda *args, **kwargs: market(candles=[candle("2026-10-04")])
        before = self.fingerprint()
        result = self.updates.update_market()
        self.assertEqual(result["status"], "UNCHANGED")
        self.assertEqual(self.fingerprint(), before)
        self.updates.market_fetch = lambda *args, **kwargs: market(candles=[candle("2026-10-03")])
        result = self.updates.update_market()
        self.assertIsNone(result["snapshot"]["market"][0]["candles"][0]["available_at"])

    def test_invalid_market_hash_rejected(self):
        self.updates.market_fetch = lambda *args, **kwargs: market(content_hash="a" * 64)
        self.assertEqual(self.updates.update_market()["failed_symbols"][0]["code"], "MARKET_HASH_MISMATCH")

    def test_declared_reliable_basis_requires_source_proof(self):
        self.updates.market_fetch = lambda *args, **kwargs: market(price_basis_evidence=None)
        before = self.fingerprint()
        self.assertEqual(self.updates.update_market()["failed_symbols"][0]["code"], "MARKET_BASIS_UNPROVEN")
        self.assertEqual(self.fingerprint(), before)

    def test_market_start_uses_exchange_day_when_hong_kong_display_date_is_next_day(self):
        self.updates.import_csv(csv_rows(NEW.replace("T09:00", "T15:00")),
                                start="2026-09-26", end="2026-09-26")
        calls = []
        self.updates.market_fetch = lambda *args, **kwargs: calls.append(args) or self.fetch(*args, **kwargs)
        self.updates.update_market()
        self.assertEqual(calls[0][1], "2026-09-01")
        # Isolate the late-only account so its day cannot be masked by Sep 1.
        late = JournalUpdates(self.repo, OTHER, real=False, market_fetch=self.updates.market_fetch)
        late.import_csv(csv_rows(NEW.replace("T09:00", "T15:00")), start="2026-09-26", end="2026-09-26")
        calls.clear()
        late.update_market()
        self.assertEqual(calls[0][1], "2026-09-25")

    def test_market_budget_exhaustion_keeps_failed_symbol_and_finite_calls(self):
        self.updates.import_csv(csv_rows(NEW.replace("ACME", "BETA")), start="2026-09-25", end="2026-09-25")
        calls = []
        def fetch(identity, *args, **kwargs):
            calls.append(identity)
            return market(symbol=identity["symbol"], instrument_key=identity["key"],
                          segments=[{"status": "FETCHED"} for _ in range(kwargs["request_budget"])])
        self.updates.market_fetch = fetch
        with patch("product.trading_journal.updates.MAX_MARKET_REQUESTS", 1):
            result = self.updates.update_market()
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["failed_symbols"][0]["code"], "MARKET_REQUEST_BUDGET_EXHAUSTED")

    def test_short_window_opening_positions_are_not_reused_as_full_history_opening(self):
        self.seed_window(csv_rows(NEW), "2026-09-25", "2026-09-25")
        with Ledger(self.storage) as ledger:
            window = resolve_window("custom", start="2026-09-25", end="2026-09-25", now=NOW)
            ledger.freeze_snapshot(ACCOUNT, window=window, opening_positions={"arbitrary-window-key": {"quantity": "9"}})
        self.assertEqual(self.updates.read_timeline()["opening_positions"], {})

    def test_short_window_containing_all_records_is_not_reused_as_full_history(self):
        with Ledger(self.storage) as ledger:
            window = resolve_window("custom", start="2026-09-01", end="2026-09-01", now=NOW)
            scoped = ledger.freeze_snapshot(ACCOUNT, window=window,
                                           opening_positions={"scoped-only": {"quantity": "9"}})
        self.assertEqual(scoped["context_records"], [])
        before = self.fingerprint()
        full = self.updates.read_timeline()
        self.assertNotEqual(full["snapshot_id"], scoped["snapshot_id"])
        self.assertEqual(full["opening_positions"], {})
        self.assertIsNone(full["coverage"]["requested_window"])
        self.assertEqual(len(full["records"]), 1)
        self.assertEqual(self.fingerprint(), before)

    def test_real_write_guard_required_before_any_saved_source_or_market_fetch(self):
        updates = JournalUpdates(self.repo, ACCOUNT, real=True, market_fetch=self.fetch)
        before = self.fingerprint()
        with patch("product.trading_journal.updates.assert_real_write_ready", side_effect=JournalError("BLOCKED", "blocked")):
            with self.assertRaises(JournalError):
                updates.import_csv(csv_rows(NEW), start="2026-09-25", end="2026-09-25")
            with self.assertRaises(JournalError):
                updates.update_market()
        self.assertEqual(self.fingerprint(), before)

    def test_stale_snapshot_market_update_rejects_instead_of_replacing_new_facts(self):
        parent = self.updates.read_timeline()
        self.updates.import_csv(csv_rows(NEW), start="2026-09-25", end="2026-09-25")
        before = self.fingerprint()
        self.updates.market_fetch = self.fetch
        with self.assertRaises(JournalError) as failure:
            self.updates.update_market(snapshot_id=parent["snapshot_id"])
        self.assertEqual(failure.exception.code, "TIMELINE_VERSION_CHANGED")
        self.assertEqual(self.fingerprint(), before)

    def test_failed_snapshot_freeze_rolls_back_import_and_removes_only_new_source(self):
        before = self.fingerprint()
        before_saved = self.saved()
        with patch.object(Ledger, "freeze_snapshot", side_effect=JournalError("FREEZE_FAILED", "freeze failed")):
            with self.assertRaises(JournalError):
                self.updates.import_csv(csv_rows(NEW), start="2026-09-25", end="2026-09-25")
        self.assertEqual(self.saved(), before_saved)
        self.assertEqual(self.fingerprint(), before)

    def test_failed_freeze_preserves_an_existing_verified_source(self):
        raw = csv_rows(NEW)
        destination = self.storage / "sources" / (hashlib.sha256(raw).hexdigest() + ".csv")
        write_private(destination, raw)
        before = self.fingerprint()
        with patch.object(Ledger, "freeze_snapshot", side_effect=JournalError("FREEZE_FAILED", "freeze failed")):
            with self.assertRaises(JournalError):
                self.updates.import_csv(raw, start="2026-09-25", end="2026-09-25")
        self.assertTrue(destination.exists())
        self.assertEqual(self.fingerprint(), before)

    def test_failed_source_cleanup_holds_lock_and_same_source_can_then_succeed(self):
        raw = csv_rows(NEW)
        destination = self.storage / "sources" / (hashlib.sha256(raw).hexdigest() + ".csv")
        original_unlink = Path.unlink
        locked_cleanup = []
        def unlink(path, *args, **kwargs):
            if path == destination:
                external = sqlite3.connect(self.storage / "journal.sqlite", timeout=0)
                try:
                    with self.assertRaises(sqlite3.OperationalError) as failure:
                        external.execute("INSERT INTO snapshots VALUES (?, ?, ?, ?, ?)",
                                         ("external-cleanup-test", ACCOUNT, "0" * 64, NOW, "{}"))
                    self.assertIn("locked", str(failure.exception))
                    locked_cleanup.append(True)
                finally:
                    external.close()
            return original_unlink(path, *args, **kwargs)
        with patch.object(Path, "unlink", new=unlink), patch.object(Ledger, "freeze_snapshot", side_effect=JournalError("FREEZE_FAILED", "freeze failed")):
            with self.assertRaises(JournalError):
                self.updates.import_csv(raw, start="2026-09-25", end="2026-09-25")
        self.assertEqual(locked_cleanup, [True])
        self.assertFalse(destination.exists())
        result = self.updates.import_csv(raw, start="2026-09-25", end="2026-09-25")
        self.assertEqual(result["status"], "SAVED")
        self.assertTrue(destination.exists())
        self.assertEqual(destination.read_bytes(), raw)
        self.assertEqual(len(result["snapshot"]["records"]), 2)

    def test_import_transaction_remains_locked_through_snapshot_freeze(self):
        original = Ledger.freeze_snapshot
        blocked = []
        def freeze(ledger, *args, **kwargs):
            external = sqlite3.connect(ledger.path, timeout=0)
            try:
                with self.assertRaises(sqlite3.OperationalError) as failure:
                    external.execute("INSERT INTO snapshots VALUES (?, ?, ?, ?, ?)",
                                     ("external-test", ACCOUNT, "0" * 64, NOW, "{}"))
                self.assertIn("locked", str(failure.exception))
                blocked.append(True)
            finally:
                external.close()
            return original(ledger, *args, **kwargs)
        with patch.object(Ledger, "freeze_snapshot", new=freeze):
            result = self.updates.import_csv(csv_rows(NEW), start="2026-09-25", end="2026-09-25")
        self.assertEqual(result["status"], "SAVED")
        self.assertEqual(blocked, [True])

    def test_market_memory_parent_rolls_back_when_child_write_fails(self):
        self.seed_window(csv_rows(NEW), "2026-09-25", "2026-09-25")
        self.updates.market_fetch = self.fetch
        before = self.fingerprint()
        with patch.object(Ledger, "derive_snapshot", side_effect=JournalError("CHILD_FAILED", "child failed")):
            with self.assertRaises(JournalError):
                self.updates.update_market()
        self.assertEqual(self.fingerprint(), before)

    def test_per_row_statement_requires_explicit_range_timezone_and_preserves_mixed_zones(self):
        rows = single_group()
        rows += [statement_header(), detail(code="示例港股 (01191)", timestamp="2026-06-16 15:18:21, GMT+8", market="HK", currency="HKD"),
                 detail(timestamp="2026-06-16 15:18:21, GMT+8", market="HK", currency="HKD")]
        before = self.fingerprint()
        with self.assertRaises(JournalError) as failure:
            self.updates.import_csv(encode(rows), start="2026-06-16", end="2026-07-01", source_timezone="PER_ROW")
        self.assertEqual(failure.exception.code, "IMPORT_RANGE_TIMEZONE_REQUIRED")
        self.assertEqual(self.fingerprint(), before)
        result = self.updates.import_csv(encode(rows), start="2026-06-16", end="2026-07-01",
                                         source_timezone="PER_ROW", range_timezone="Asia/Hong_Kong")
        imported = [row for row in result["snapshot"]["records"] if row["source_timezone"] != "Asia/Hong_Kong"]
        self.assertEqual({row["source_timezone"] for row in imported}, {"America/New_York", "Etc/GMT-8"})
        self.assertEqual(result["receipt"]["coverage"]["request"]["timezone"], "Asia/Hong_Kong")

    def test_per_row_generic_csv_is_rejected_before_writes(self):
        before = self.fingerprint()
        with self.assertRaises(JournalError) as failure:
            self.updates.import_csv(csv_rows(NEW), start="2026-09-25", end="2026-09-25",
                                    source_timezone="PER_ROW", range_timezone="America/New_York")
        self.assertEqual(failure.exception.code, "INVALID_TIMEZONE")
        self.assertEqual(self.fingerprint(), before)

    def test_single_source_zone_is_the_default_range_zone(self):
        late = csv_rows(NEW.replace("T09:00", "T15:00"))
        result = self.updates.import_csv(late, start="2026-09-25", end="2026-09-25", source_timezone="America/New_York")
        self.assertEqual(result["receipt"]["coverage"]["request"]["timezone"], "America/New_York")
        self.assertTrue(result["snapshot"]["records"][-1]["occurred_at"].startswith("2026-09-25T19:00"))

    def test_file_row_overlap_compares_instant_across_source_display_zones(self):
        self.updates.import_csv(csv_rows(NEW.replace("T09:00", "T15:00")), start="2026-09-25", end="2026-09-25", source_timezone="America/New_York")
        incoming = csv_rows(NEW.replace("T09:00:00-04:00", "T03:00:00+08:00").replace("2026-09-25", "2026-09-26"), stable=False)
        before = self.fingerprint()
        with self.assertRaises(JournalError) as failure:
            self.updates.import_csv(incoming, start="2026-09-26", end="2026-09-26", source_timezone="Asia/Hong_Kong")
        self.assertEqual(failure.exception.code, "CSV_OVERLAP_UNPROVEN")
        self.assertEqual(self.fingerprint(), before)

    def test_open_start_receipt_period_is_not_ignored(self):
        with Ledger(self.storage) as ledger:
            records = ledger.current_records(ACCOUNT)
            ledger.import_records(records, source_hash="b" * 64,
                                  requested_window={"start": None, "end": "2026-09-30T00:00:00Z", "timezone": "Asia/Hong_Kong"})
        before = self.fingerprint()
        with self.assertRaises(JournalError) as failure:
            self.updates.import_csv(csv_rows(NEW, stable=False), start="2026-09-25", end="2026-09-25")
        self.assertEqual(failure.exception.code, "CSV_OVERLAP_UNPROVEN")
        self.assertEqual(self.fingerprint(), before)

    def test_receipt_only_concurrent_period_is_rechecked_under_lock(self):
        external_state = []
        def add_receipt():
            with Ledger(self.storage) as ledger:
                records = ledger.current_records(ACCOUNT)
                ledger.import_records(records, source_hash="c" * 64,
                                      requested_window=resolve_window("custom", start="2026-09-25", end="2026-09-25", now=NOW))
            external_state.append(self.fingerprint())
        with patch.object(self.updates, "_write_guard", side_effect=add_receipt):
            with self.assertRaises(JournalError) as failure:
                self.updates.import_csv(csv_rows(NEW, stable=False), start="2026-09-25", end="2026-09-25")
        self.assertEqual(failure.exception.code, "CSV_OVERLAP_UNPROVEN")
        self.assertEqual(self.fingerprint(), external_state[0])

    def test_receipt_only_concurrent_same_source_is_rechecked_under_lock(self):
        raw = csv_rows(NEW, stable=False)
        external_state = []
        def add_receipt():
            with Ledger(self.storage) as ledger:
                records = ledger.current_records(ACCOUNT)
                ledger.import_records(records, source_hash=hashlib.sha256(raw).hexdigest(),
                                      requested_window=resolve_window("custom", start="2026-09-25", end="2026-09-25", now=NOW))
            external_state.append(self.fingerprint())
        with patch.object(self.updates, "_write_guard", side_effect=add_receipt):
            result = self.updates.import_csv(raw, start="2026-09-25", end="2026-09-25")
        self.assertEqual(result["status"], "UNCHANGED")
        self.assertEqual(self.fingerprint(), external_state[0])


if __name__ == "__main__":
    unittest.main()
