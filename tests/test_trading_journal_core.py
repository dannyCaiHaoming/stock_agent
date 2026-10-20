"""Synthetic only: no broker application, account, model, or network access."""

from copy import deepcopy
from decimal import Decimal
import json
import hashlib
from pathlib import Path
import sqlite3
import tempfile
import unittest

from product.trading_journal.analysis import analyze_records
from product.trading_journal.common import JournalError
from product.trading_journal.ledger import Ledger
from product.trading_journal.normalization import parse_csv
from product.trading_journal.windows import record_in_window, resolve_window

AS_OF = "2026-10-01T01:00:00Z"


def record(number, *, side="BUY", qty="10", price="100", fees="1", currency="USD", symbol="ABC", key=None,
           day="2026-09-01", asset="STOCK", market="US", multiplier="1", activity="FILL", precision="SECOND", effect=None):
    return {
        "record_id": f"record-synthetic-{number}", "source_record_id": f"fill-{number}", "activity_type": activity,
        "account_ref": "account-synthetic-one", "instrument": {"key": key or f"instrument-{market}-{currency}-{symbol}-{asset}",
            "symbol": symbol, "asset_type": asset, "market": market, "currency": currency,
            "exchange_timezone": "America/New_York" if market == "US" else "Asia/Hong_Kong",
            "underlying": "ABC" if asset == "OPTION" else None, "expiry": "2026-12-18" if asset == "OPTION" else None,
            "strike": "100" if asset == "OPTION" else None, "right": "CALL" if asset == "OPTION" else None,
            "multiplier": multiplier, "adjustment_status": "STANDARD" if asset == "OPTION" else None},
        "side": side, "quantity": qty, "price": price, "fees": fees, "fees_complete": fees is not None,
        "currency": currency, "position_effect": effect, "occurred_at": day if precision == "DATE" else day + "T14:30:00Z",
        "time_precision": precision, "source_timezone": "America/New_York", "source_id": "source-synthetic-one",
        "as_of": AS_OF, "retrieved_at": AS_OF, "source_hash": "hash-one", "source_location": {"row": number + 1},
        "identity_status": "SOURCE_STABLE_ID",
    }


class WindowTests(unittest.TestCase):
    def test_calendar_month_end_and_leap_year(self):
        self.assertEqual(resolve_window("一个月", now="2024-03-31T08:00:00Z")["start"], "2024-02-29T17:00:00+09:00")
        self.assertEqual(resolve_window("一年", now="2024-02-29T08:00:00Z")["start"], "2023-02-28T17:00:00+09:00")
        self.assertEqual(resolve_window("半年", now="2026-08-31T08:00:00Z")["start"], "2026-02-28T17:00:00+09:00")

    def test_week_and_custom_inclusive_local_date(self):
        window = resolve_window("一周", now="2026-10-01T00:00:00Z")
        self.assertEqual(window["start"], "2026-09-24T09:00:00+09:00")
        window = resolve_window("custom", start="2026-09-01", end="2026-09-30", now=AS_OF)
        self.assertTrue(record_in_window(record(1, day="2026-09-30"), window))
        self.assertFalse(record_in_window(record(1, day="2026-08-31"), window))

    def test_lifetime_unknown_and_explicit_choice(self):
        self.assertIsNone(resolve_window("lifetime", now=AS_OF)["start"])
        self.assertFalse(resolve_window("lifetime", now=AS_OF)["account_opened_at_known"])
        with self.assertRaises(JournalError) as caught:
            resolve_window("", now=AS_OF)
        self.assertEqual(caught.exception.code, "WINDOW_CHOICE_REQUIRED")
        with self.assertRaises(JournalError):
            resolve_window("custom", start="2026-10-03", end="2026-10-02", now=AS_OF)

    def test_custom_end_never_after_cutoff(self):
        value = resolve_window("custom", start="2026-09-01", end="2026-12-31", now=AS_OF)
        self.assertEqual(value["end"], "2026-10-01T10:00:00+09:00")


class NormalizationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "official.csv"

    def tearDown(self):
        self.temp.cleanup()

    def parse(self, value, **kwargs):
        self.path.write_text(value, encoding="utf-8")
        return parse_csv(self.path, account_ref="account-synthetic-one", source_id="source-synthetic-one",
                         as_of=AS_OF, retrieved_at=AS_OF, **kwargs)

    def test_english_fills_and_redaction(self):
        values = self.parse("Account Name,Account Number,Symbol,Asset Type,Market,Currency,Side,Quantity,Price,Trade Time,Execution ID,Total Fees\nPrivate Name,99887766,ABC,STOCK,US,USD,BUY,10,100,2026-09-01T14:30:00Z,e1,1\n")
        self.assertEqual(values[0]["activity_type"], "FILL")
        self.assertEqual(values[0]["fees"], "1")
        self.assertIsNone(values[0]["position_effect"])
        self.assertNotIn("99887766", json.dumps(values))
        self.assertNotIn("Private Name", json.dumps(values))

    def test_chinese_etf_source_and_exchange_time_separate(self):
        values = self.parse("代码,资产类型,市场,币种,买卖方向,成交数量,成交价格,成交时间,成交编号,总费用,来源时区\nSPY,ETF,美股,USD,卖出,2,500,2026-09-01 22:30:00,c1,0.5,Asia/Shanghai\n")
        item = values[0]
        self.assertEqual(item["instrument"]["asset_type"], "ETF")
        self.assertEqual(item["occurred_at"], "2026-09-01T14:30:00Z")
        self.assertEqual(item["source_timezone"], "Asia/Shanghai")
        self.assertEqual(item["instrument"]["exchange_timezone"], "America/New_York")

    def test_naive_market_not_source_timezone_proof(self):
        with self.assertRaises(JournalError) as caught:
            self.parse("Symbol,Asset Type,Market,Currency,Side,Quantity,Price,Trade Time\nABC,STOCK,US,USD,BUY,1,5,2026-09-01 14:30:00\n")
        self.assertEqual(caught.exception.code, "TIMEZONE_REQUIRED")

    def test_orders_not_filled_executions(self):
        values = self.parse("Symbol,Asset Type,Market,Currency,Side,Quantity,Average Price,Order Time,Order ID,Status\nABC,STOCK,US,USD,BUY,100,99,2026-09-01T14:30:00Z,o1,CANCELLED\n")
        self.assertEqual(values[0]["activity_type"], "ORDER")
        self.assertEqual(values[0]["status"], "CANCELLED")
        with self.assertRaises(JournalError) as caught:
            self.parse("Symbol,Side,Quantity,Average Price,Order Time,Status\nABC,BUY,10,100,2026-09-01T14:30:00Z,FILLED\n", activity_type="FILL")
        self.assertEqual(caught.exception.code, "BUSINESS_TIME_REQUIRED")

    def test_occ_distinct_contracts_and_no_default_multiplier(self):
        values = self.parse("Symbol,Market,Currency,Side,Quantity,Price,Trade Date,Execution ID\nABC261218C00100000,US,USD,BUY,1,2,2026-09-01,c1\nABC261218C00110000,US,USD,BUY,1,1,2026-09-01,c2\n")
        self.assertEqual(values[0]["instrument"]["underlying"], "ABC")
        self.assertEqual(values[0]["instrument"]["strike"], "100")
        self.assertEqual(values[0]["time_precision"], "DATE")
        self.assertIsNone(values[0]["instrument"]["multiplier"])
        self.assertNotEqual(values[0]["instrument"]["key"], values[1]["instrument"]["key"])

    def test_nonstandard_option_and_bto_position_effect(self):
        values = self.parse("Symbol,Asset Type,Market,Currency,Side,Quantity,Price,Trade Date,Underlying,Expiry,Strike,Right,Multiplier,Adjustment Status\nABC261218C00100000,OPTION,US,USD,BTO,1,2,2026-09-01,ABC,2026-12-18,100,CALL,25,ADJUSTED\n")
        self.assertEqual(values[0]["instrument"]["multiplier"], "25")
        self.assertEqual(values[0]["position_effect"], "OPEN")
        self.assertEqual(values[0]["side"], "BUY")

    def test_option_identity_conflict_rejects_batch(self):
        with self.assertRaises(JournalError) as caught:
            self.parse("Symbol,Side,Quantity,Price,Trade Date,Strike\nABC261218C00100000,BUY,1,2,2026-09-01,101\n")
        self.assertEqual(caught.exception.code, "OPTION_IDENTITY_CONFLICT")

    def test_same_second_and_no_source_id_preserve_rows(self):
        values = self.parse("Symbol,Asset Type,Market,Currency,Side,Quantity,Price,Trade Time\nABC,STOCK,US,USD,BUY,1,5,2026-09-01T14:30:00Z\nABC,STOCK,US,USD,BUY,1,5,2026-09-01T14:30:00Z\n")
        self.assertEqual(len(values), 2)
        self.assertNotEqual(values[0]["record_id"], values[1]["record_id"])
        self.assertEqual(values[0]["identity_status"], "FILE_ROW_ONLY")

    def test_event_not_fake_fill(self):
        values = self.parse("Activity Type,Symbol,Asset Type,Market,Currency,Date,Quantity\nEXPIRY,ABC261218C00100000,OPTION,US,USD,2026-12-18,1\n")
        self.assertEqual(values[0]["activity_type"], "EXPIRY")
        self.assertIsNone(values[0]["side"])
        self.assertIsNone(values[0]["price"])

    def test_cash_fee_event_amount_retained_separate(self):
        values = self.parse("Activity Type,Currency,Date,Amount,Transaction ID\nDIVIDEND,HKD,2026-09-01,12.34,event1\nFEE,USD,2026-09-01,-1.2,event2\n")
        self.assertEqual(values[0]["amount"], "12.34")
        self.assertEqual(values[1]["amount"], "-1.2")
        self.assertIsNone(values[1]["price"])

    def test_unknown_and_empty_csv_rejected(self):
        for value in ("Name,Balance\nUser,1000\n", "Symbol,Side,Quantity,Price,Trade Date\n"):
            with self.subTest(value=value), self.assertRaises(JournalError):
                self.parse(value)

    def test_dst_ambiguous_and_nonexistent_time_rejected(self):
        for value in ("2026-11-01 01:30:00", "2026-03-08 02:30:00"):
            with self.subTest(value=value), self.assertRaises(JournalError) as caught:
                self.parse(f"Symbol,Side,Quantity,Price,Trade Time\nABC,BUY,1,5,{value}\n", source_timezone="America/New_York")
            self.assertEqual(caught.exception.code, "AMBIGUOUS_LOCAL_TIME")

    def test_fee_subtotals_do_not_prove_all_charges(self):
        values = self.parse("Symbol,Side,Quantity,Price,Trade Date,Commission,Platform Fee\nABC,BUY,1,5,2026-09-01,1,0.5\n")
        self.assertEqual(values[0]["fees"], "1.5")
        self.assertFalse(values[0]["fees_complete"])

    def test_generic_fee_labels_neither_prove_total_nor_add_commission(self):
        for header in ("Fees", "Fee", "Transaction Fees", "费用", "交易费用", "費用", "交易費用"):
            for commission in (False, True):
                with self.subTest(header=header, commission=commission):
                    suffix = ",Commission,Platform Fee" if commission else ""
                    amounts = ",1,0.5" if commission else ""
                    values = self.parse(f"Symbol,Side,Quantity,Price,Trade Date,{header}{suffix}\nABC,BUY,1,5,2026-09-01,1.5{amounts}\n")
                    self.assertIsNone(values[0]["fees"])
                    self.assertFalse(values[0]["fees_complete"])

    def test_explicit_total_fee_is_not_added_to_component_or_generic_columns(self):
        for header in ("Total Fees", "Total Fee", "总费用", "總費用"):
            with self.subTest(header=header):
                values = self.parse(f"Symbol,Side,Quantity,Price,Trade Date,{header},Fees,Commission,Platform Fee\nABC,BUY,1,5,2026-09-01,1.5,1.5,1,0.5\n")
                self.assertEqual(values[0]["fees"], "1.5")
                self.assertTrue(values[0]["fees_complete"])

    def test_generic_fee_zero_cannot_prove_no_commission(self):
        values = self.parse("Symbol,Asset Type,Market,Currency,Side,Quantity,Price,Trade Date,Fees\nABC,STOCK,US,USD,BUY,1,100,2026-09-01,0\nABC,STOCK,US,USD,SELL,1,110,2026-09-02,0\n")
        result = analyze_records(values, history_complete=True)
        self.assertEqual(result["episodes"][0]["gross_pnl"], "10")
        self.assertIsNone(result["episodes"][0]["net_pnl"])
        self.assertIn("FEES_INCOMPLETE", result["episodes"][0]["reasons"])

    def test_source_preamble_and_utf16(self):
        self.path.write_bytes("Account Name: Private Name\nSymbol,Asset Type,Market,Currency,Side,Quantity,Price,Trade Date\nABC,STOCK,US,USD,BUY,1,5,2026-09-01\n".encode("utf-16"))
        values = parse_csv(self.path, account_ref="account-synthetic-one", source_id="source-synthetic-one", as_of=AS_OF, retrieved_at=AS_OF)
        self.assertEqual(len(values), 1)
        self.assertNotIn("Private", json.dumps(values))


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.ledger = Ledger(self.root)

    def tearDown(self):
        self.ledger.close()
        self.temp.cleanup()

    def file_state(self):
        return {path.name: (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_mtime_ns,
                            path.stat().st_ctime_ns, path.stat().st_mode & 0o777)
                for path in self.root.iterdir() if path.is_file()}

    def test_read_only_all_list_apis_preserve_files_and_sqlite_enforces_boundary(self):
        self.ledger.import_records([record(1)])
        snapshot = self.ledger.freeze_snapshot("account-synthetic-one")
        before = self.file_state()
        with Ledger(self.root, read_only=True) as reader:
            self.assertEqual(reader.accounts(), ["account-synthetic-one"])
            self.assertEqual(len(reader.batches()), 1)
            self.assertEqual(len(reader.snapshots()), 1)
            self.assertEqual(len(reader.current_records("account-synthetic-one")), 1)
            self.assertEqual(len(reader.revisions("record-synthetic-1")), 1)
            self.assertEqual(reader.load_snapshot(snapshot["snapshot_id"]), snapshot)
            self.assertEqual(reader._db.execute("PRAGMA query_only").fetchone()[0], 1)
            with self.assertRaises(sqlite3.OperationalError):
                reader._db.execute("CREATE TABLE forbidden (value TEXT)")
        self.assertEqual(before, self.file_state())

    def test_read_only_missing_root_or_database_does_not_create(self):
        for root in (self.root / "not-created", self.root / "existing-empty"):
            if root.name == "existing-empty":
                root.mkdir(mode=0o700)
            previous = root.exists()
            with self.subTest(root=root.name), self.assertRaises(JournalError) as caught:
                Ledger(root, read_only=True)
            self.assertEqual(caught.exception.code, "JOURNAL_NOT_INITIALIZED")
            self.assertEqual(root.exists(), previous)
            if root.exists():
                self.assertEqual(list(root.iterdir()), [])

    def test_read_only_write_apis_rejected_without_failure_receipt(self):
        self.ledger.import_records([record(1)])
        snapshot = self.ledger.freeze_snapshot("account-synthetic-one")
        before = self.file_state()
        with Ledger(self.root, read_only=True) as reader:
            actions = (
                lambda: reader.import_records([record(2)]),
                lambda: reader.record_failed_batch("PARSE_FAILED"),
                lambda: reader.freeze_snapshot("account-synthetic-one"),
                lambda: reader.derive_snapshot(snapshot["snapshot_id"], []),
            )
            for action in actions:
                with self.assertRaises(JournalError) as caught:
                    action()
                self.assertEqual(caught.exception.code, "JOURNAL_READ_ONLY")
            self.assertEqual(len(reader.batches()), 1)
            self.assertEqual(len(reader.snapshots()), 1)
        self.assertEqual(before, self.file_state())

    def test_read_only_foreign_wal_rejected_without_sidecars(self):
        self.ledger.close()
        with sqlite3.connect(self.root / "journal.sqlite") as writer:
            writer.execute("PRAGMA journal_mode = WAL")
        writer.close()
        before = self.file_state()
        with self.assertRaises(JournalError) as caught:
            Ledger(self.root, read_only=True)
        self.assertEqual(caught.exception.code, "JOURNAL_READ_ONLY_WAL_UNSUPPORTED")
        self.assertEqual(before, self.file_state())

    def test_read_only_unknown_schema_is_not_initialized_or_migrated(self):
        self.ledger.close()
        with sqlite3.connect(self.root / "journal.sqlite") as writer:
            writer.executescript("DROP TABLE records; DROP TABLE batches; DROP TABLE snapshots; CREATE TABLE foreign_table (id TEXT);")
        writer.close()
        before = self.file_state()
        with self.assertRaises(JournalError) as caught:
            Ledger(self.root, read_only=True)
        self.assertEqual(caught.exception.code, "JOURNAL_SCHEMA_UNSUPPORTED")
        self.assertEqual(before, self.file_state())

    def test_market_derivation_preserves_parent_records_despite_newer_revision(self):
        self.ledger.import_records([record(1)])
        parent = self.ledger.freeze_snapshot("account-synthetic-one")
        self.ledger.import_records([record(1, fees="99")])
        market = [{"source_id": "market-synthetic", "as_of": AS_OF, "retrieved_at": AS_OF, "candles": []}]
        derived = self.ledger.derive_snapshot(parent["snapshot_id"], market)
        self.assertNotEqual(derived["snapshot_id"], parent["snapshot_id"])
        self.assertNotEqual(derived["input_hash"], parent["input_hash"])
        self.assertEqual(derived["parent_snapshot_id"], parent["snapshot_id"])
        self.assertEqual(derived["parent_input_hash"], parent["input_hash"])
        for field in ("records", "context_records", "opening_positions", "coverage", "analysis"):
            self.assertEqual(derived[field], parent[field])
        self.assertEqual(derived["records"][0]["fees"], "1")
        self.assertEqual(self.ledger.current_records("account-synthetic-one")[0]["fees"], "99")
        self.assertEqual(self.ledger.load_snapshot(parent["snapshot_id"]), parent)
        self.assertEqual(self.ledger.load_snapshot(derived["snapshot_id"]), derived)

    def test_window_context_preserves_intermediate_events_and_later_linked_fee(self):
        opening = record(1)
        transfer = record(2, activity="TRANSFER", day="2026-09-02")
        closing = record(3, side="SELL", price="110", day="2026-09-10")
        fee = record(4, activity="FEE", day="2026-09-12", fees="5")
        fee.update(amount="-5", related_source_record_id=closing["source_record_id"])
        self.ledger.import_records([opening, transfer, closing, fee])
        initial = {opening["instrument"]["key"]: {"quantity": "0", "source_id": "source-synthetic-zero", "as_of": "2026-08-31T14:30:00Z", "retrieved_at": AS_OF}}
        window = resolve_window("custom", now=AS_OF, start="2026-09-09", end="2026-09-11")
        snapshot = self.ledger.freeze_snapshot("account-synthetic-one", window=window, opening_positions=initial)
        self.assertEqual({item["record_id"] for item in snapshot["context_records"]}, {opening["record_id"], transfer["record_id"], fee["record_id"]})
        recomputed = analyze_records(snapshot["records"] + snapshot["context_records"], window=window, opening_positions=initial)
        for field in ("records_hash", "source_id", "episodes", "fee_record_refs", "by_currency", "scope"):
            self.assertEqual(snapshot["analysis"][field], recomputed[field])

    def test_repeat_and_revision_preserve_old_snapshot(self):
        first = record(1)
        self.assertEqual(self.ledger.import_records([first])["inserted"], 1)
        snapshot = self.ledger.freeze_snapshot(first["account_ref"])
        same = deepcopy(first)
        same.update(source_id="source-synthetic-repeat", retrieved_at="2026-10-01T02:00:00Z")
        self.assertEqual(self.ledger.import_records([same])["unchanged"], 1)
        same["fees"] = "2"
        self.assertEqual(self.ledger.import_records([same])["revised"], 1)
        self.assertEqual(len(self.ledger.revisions(first["record_id"])), 2)
        self.assertEqual(self.ledger.load_snapshot(snapshot["snapshot_id"])["records"][0]["fees"], "1")
        self.assertEqual(self.ledger.current_records(first["account_ref"])[0]["fees"], "2")
        self.assertEqual(self.ledger.path.stat().st_mode & 0o777, 0o600)

    def test_batch_failure_no_partial_data_or_old_version_overwrite(self):
        self.ledger.import_records([record(1)])
        bad = record(3)
        bad["quantity"] = "-1"
        revised = record(1, fees="100")
        with self.assertRaises(JournalError):
            self.ledger.import_records([revised, record(2), bad])
        self.assertEqual(len(self.ledger.current_records("account-synthetic-one")), 1)
        self.assertEqual(self.ledger.current_records("account-synthetic-one")[0]["fees"], "1")
        self.assertEqual(self.ledger.batches()[-1]["status"], "FAILED")

    def test_source_identity_collision_rejected(self):
        with self.assertRaises(JournalError) as caught:
            self.ledger.import_records([record(1), record(1, qty="2")])
        self.assertEqual(caught.exception.code, "SOURCE_ID_COLLISION")

    def test_same_second_stable_distinct_fills_preserved(self):
        self.ledger.import_records([record(1), record(2)])
        self.assertEqual(len(self.ledger.current_records("account-synthetic-one")), 2)
        self.assertFalse(any(item["duplicate_candidate"] for item in self.ledger.current_records("account-synthetic-one")))

    def test_unproved_cross_file_duplicates_retained_excluded(self):
        first = record(1)
        first["source_record_id"] = None
        second = record(2)
        second.update(source_record_id=None, source_hash="hash-two")
        self.ledger.import_records([first])
        self.ledger.import_records([second])
        values = self.ledger.current_records(first["account_ref"])
        self.assertEqual(len(values), 2)
        self.assertTrue(all(item["duplicate_candidate"] for item in values))
        result = analyze_records(values, history_complete=True)
        self.assertTrue(any(item["reason"] == "DUPLICATE_IDENTITY_UNCERTAIN" for item in result["excluded_records"]))

    def test_unknown_start_empty_and_missing_asset_never_complete(self):
        coverage = {"status": "LIFETIME_RECONCILED", "gaps": []}
        request = resolve_window("lifetime", now=AS_OF)
        receipt = self.ledger.import_records([record(1)], coverage=coverage, requested_window=request)
        self.assertEqual(receipt["coverage"]["status"], "PARTIAL")
        self.assertFalse(receipt["coverage"]["automatic_client_collection"])
        empty = self.ledger.import_records([], coverage=coverage, requested_window=request)
        self.assertEqual(empty["coverage"]["status"], "PARTIAL")

    def complete_coverage(self, request):
        return {"categories": {asset: {"status": "COMPLETE", "termination_proven": True, "reconciled": True,
                                      "expected_rows": 1 if asset == "STOCK" else 0, "observed_rows": 1 if asset == "STOCK" else 0}
                                for asset in ("STOCK", "ETF", "OPTION")},
                "requested_range_reconciled": True, "segments": [{"start": request["start"], "end": request["end"], "termination_proven": True, "reconciled": True}]}

    def test_complete_window_requires_counts_and_continuous_range(self):
        request = resolve_window("month", now=AS_OF)
        coverage = self.complete_coverage(request)
        receipt = self.ledger.import_records([record(1)], coverage=coverage, requested_window=request)
        self.assertEqual(receipt["coverage"]["status"], "SOURCE_COMPLETE_FOR_WINDOW")
        coverage["categories"]["STOCK"]["observed_rows"] = 10
        receipt = self.ledger.import_records([record(1)], coverage=coverage, requested_window=request)
        self.assertEqual(receipt["coverage"]["status"], "PARTIAL")
        coverage = self.complete_coverage(request)
        coverage["segments"][0]["start"] = "2026-09-15T00:00:00Z"
        self.assertEqual(self.ledger.import_records([record(1)], coverage=coverage, requested_window=request)["coverage"]["status"], "PARTIAL")

    def test_collection_receipt_binds_hash_chain_without_completeness_claim(self):
        receipt = {"receipt_id": "receipt-synthetic-one", "content_hash": "a" * 64, "source_id": "source-synthetic-receipt",
                   "as_of": AS_OF, "retrieved_at": AS_OF, "original_source_hash": "b" * 64, "normalized_csv_hash": "c" * 64}
        saved = self.ledger.import_records([record(1)], coverage={"collection_receipt": receipt})
        self.assertEqual(saved["coverage"]["collection_receipt"], receipt)
        self.assertEqual(saved["coverage"]["status"], "PARTIAL")
        frozen = self.ledger.freeze_snapshot("account-synthetic-one")
        self.assertEqual(frozen["coverage"]["observations"][0]["collection_receipt"], receipt)

    def test_computer_use_export_mode_requires_lineage_without_any_ledger_mutation(self):
        before = self.file_state()
        for coverage in (None, {}, {"collection_receipt": None}):
            with self.subTest(coverage=coverage), self.assertRaises(JournalError) as failure:
                self.ledger.import_records([record(1)], mode="COMPUTER_USE_EXPORT", coverage=coverage)
            self.assertEqual(failure.exception.code, "COMPUTER_USE_RECEIPT_REQUIRED")
        self.assertEqual(self.ledger.current_records("account-synthetic-one"), [])
        self.assertEqual(self.ledger.batches(), [])
        self.assertEqual(self.file_state(), before)

    def test_computer_use_export_empty_records_with_valid_lineage_refuse_without_mutation(self):
        lineage = {"receipt_id": "collection-synthetic-empty", "content_hash": "a" * 64,
                   "source_id": "tiger-computer-use:" + "b" * 32, "as_of": AS_OF,
                   "retrieved_at": AS_OF, "original_source_hash": "c" * 64, "normalized_csv_hash": "c" * 64}
        requested = resolve_window("custom", start="2026-09-01", end=AS_OF, now=AS_OF)
        before = self.file_state()
        with self.assertRaises(JournalError) as failure:
            self.ledger.import_records([], mode="COMPUTER_USE_EXPORT",
                                       source_hash=lineage["original_source_hash"], requested_window=requested,
                                       coverage={"collection_receipt": lineage})
        self.assertEqual(failure.exception.code, "NO_RECORDS_IN_WINDOW")
        self.assertEqual(self.ledger.current_records("account-synthetic-one"), [])
        self.assertEqual(self.ledger.batches(), [])
        self.assertEqual(self.file_state(), before)

    def test_computer_use_export_mode_retains_only_safe_lineage_and_is_not_automatic_or_complete(self):
        lineage = {"receipt_id": "collection-synthetic-one", "content_hash": "a" * 64,
                   "source_id": "tiger-computer-use:" + "b" * 32, "as_of": AS_OF,
                   "retrieved_at": AS_OF, "original_source_hash": "c" * 64, "normalized_csv_hash": "c" * 64}
        imported = record(1)
        imported.update(source_id=lineage["source_id"], source_hash=lineage["original_source_hash"])
        requested = resolve_window("custom", start="2026-09-01", end=AS_OF, now=AS_OF)
        saved = self.ledger.import_records([imported], mode="COMPUTER_USE_EXPORT",
                                          source_hash=lineage["original_source_hash"], requested_window=requested,
                                          coverage={"status": "LIFETIME_RECONCILED", "collection_receipt": lineage})
        self.assertEqual(saved["coverage"]["collection_mode"], "COMPUTER_USE_EXPORT")
        self.assertFalse(saved["coverage"]["automatic_client_collection"])
        self.assertEqual(saved["coverage"]["status"], "PARTIAL")
        self.assertEqual(saved["coverage"]["collection_receipt"], lineage)
        manual = self.ledger.import_records([record(2)])
        self.assertEqual(manual["coverage"]["collection_mode"], "USER_ASSISTED")

    def test_collection_receipt_unknown_private_fields_bad_hash_and_missing_time_rejected(self):
        receipt = {"receipt_id": "receipt-synthetic-one", "content_hash": "a" * 64, "source_id": "source-synthetic-receipt",
                   "as_of": AS_OF, "retrieved_at": AS_OF, "original_source_hash": "b" * 64, "normalized_csv_hash": "c" * 64}
        cases = []
        private = deepcopy(receipt)
        private["raw_account_number"] = "99887766"
        cases.append(private)
        invalid = deepcopy(receipt)
        invalid["content_hash"] = "not-a-sha256"
        cases.append(invalid)
        missing = deepcopy(receipt)
        del missing["retrieved_at"]
        cases.append(missing)
        for value in cases:
            with self.subTest(value=list(value)), self.assertRaises(JournalError):
                self.ledger.import_records([record(1)], coverage={"collection_receipt": value})
        self.assertEqual(self.ledger.current_records("account-synthetic-one"), [])

    def test_lifetime_full_proof_and_later_uncovered_fill(self):
        request = resolve_window("lifetime", now=AS_OF, account_opened_at="2026-08-01")
        coverage = self.complete_coverage(request)
        coverage["lifetime_proof"] = {"official_opening_source_id": "source-synthetic-open", "official_opened_at": "2026-08-01", "lifecycle_reconciled": True,
            "monthly_reconciliation": [{"month": month, "statement_source_id": "source-synthetic-statement", "statement_hash": "a" * 64,
                                         "expected_rows": 1 if month == "2026-09" else 0, "observed_rows": 1 if month == "2026-09" else 0,
                                         "quantity_reconciled": True, "reconciled_categories": ["STOCK", "ETF", "OPTION"]} for month in ("2026-08", "2026-09", "2026-10")]}
        result = self.ledger.import_records([record(1)], coverage=coverage, requested_window=request)
        self.assertEqual(result["coverage"]["status"], "LIFETIME_RECONCILED")
        self.assertEqual(self.ledger.freeze_snapshot("account-synthetic-one")["coverage"]["status"], "LIFETIME_RECONCILED")
        self.ledger.import_records([record(2, day="2026-10-02")])
        self.assertEqual(self.ledger.freeze_snapshot("account-synthetic-one")["coverage"]["status"], "PARTIAL")

    def test_window_snapshot_binds_pairing_context(self):
        opening, closing = record(1), record(2, side="SELL", day="2026-09-10", price="110")
        self.ledger.import_records([opening, closing])
        window = resolve_window("custom", now=AS_OF, start="2026-09-09", end="2026-09-11")
        initial = {opening["instrument"]["key"]: {"quantity": "0", "source_id": "source-synthetic-zero", "as_of": "2026-08-31T14:30:00Z", "retrieved_at": AS_OF}}
        snapshot = self.ledger.freeze_snapshot("account-synthetic-one", window=window, opening_positions=initial)
        self.assertEqual([item["record_id"] for item in snapshot["records"]], [closing["record_id"]])
        self.assertEqual([item["record_id"] for item in snapshot["context_records"]], [opening["record_id"]])
        self.assertEqual(snapshot["analysis"]["episodes"][0]["net_pnl"], "98")
        self.assertEqual(self.ledger.load_snapshot(snapshot["snapshot_id"])["input_hash"], snapshot["input_hash"])


class AnalysisTests(unittest.TestCase):
    def test_future_opening_position_not_accepted_as_historical_zero(self):
        initial = {"instrument-US-USD-ABC-STOCK": {"quantity": "0", "source_id": "source-synthetic-position", "as_of": AS_OF, "retrieved_at": AS_OF}}
        with self.assertRaises(JournalError) as caught:
            analyze_records([record(1), record(2, side="SELL", price="110", day="2026-09-02")], opening_positions=initial)
        self.assertEqual(caught.exception.code, "OPENING_POSITION_TIME_NOT_PRIOR")

    def test_date_precision_opening_state_requires_before_entire_uncertain_day(self):
        initial = {"instrument-US-USD-ABC-STOCK": {"quantity": "0", "source_id": "source-synthetic-position", "as_of": "2026-09-01T12:00:00Z", "retrieved_at": AS_OF}}
        with self.assertRaises(JournalError) as caught:
            analyze_records([record(1, precision="DATE"), record(2, side="SELL", price="110", day="2026-09-02")], opening_positions=initial)
        self.assertEqual(caught.exception.code, "OPENING_POSITION_TIME_NOT_PRIOR")

    def test_linked_independent_fee_cannot_be_silently_ignored_or_double_counted(self):
        opening = record(1, fees="0")
        closing = record(2, side="SELL", price="110", fees="0", day="2026-09-02")
        fee = record(3, activity="FEE", fees="5", day="2026-09-02")
        fee.update(amount="-5", related_source_record_id=closing["record_id"], occurred_at="2026-09-02T16:00:00Z")
        result = analyze_records([opening, closing, fee], history_complete=True)
        self.assertEqual(result["episodes"][0]["gross_pnl"], "100")
        self.assertIsNone(result["episodes"][0]["net_pnl"])
        self.assertIn("FEES_UNRECONCILED", result["episodes"][0]["reasons"])
        self.assertEqual(result["fee_record_refs"][0]["affected_record_ids"], [closing["record_id"]])

    def test_order_linked_fee_blocks_each_related_fill_without_order_allocation_guess(self):
        opening = record(1, qty="3", fees="0")
        second = record(2, qty="2", fees="0", day="2026-09-02")
        opening["order_id"] = second["order_id"] = "order-synthetic-one"
        closing = record(3, side="SELL", qty="5", price="110", day="2026-09-03", fees="0")
        fee = record(4, activity="FEE", day="2026-09-04", fees="5")
        fee["order_id"] = "order-synthetic-one"
        result = analyze_records([opening, second, closing, fee], history_complete=True)
        self.assertEqual(len(result["episodes"]), 2)
        self.assertTrue(all(item["net_pnl"] is None and "FEES_UNRECONCILED" in item["reasons"] for item in result["episodes"]))

    def test_later_posted_linked_fee_still_affects_window_closing_trade(self):
        opening = record(1, fees="0")
        closing = record(2, side="SELL", price="110", fees="0", day="2026-09-02")
        fee = record(3, activity="FEE", fees="5", day="2026-09-03")
        fee["related_source_record_id"] = closing["source_record_id"]
        window = resolve_window("custom", now=AS_OF, start="2026-09-02", end="2026-09-02")
        result = analyze_records([opening, closing, fee], history_complete=True, window=window)
        self.assertIsNone(result["episodes"][0]["net_pnl"])
        self.assertIn("FEES_UNRECONCILED", result["episodes"][0]["reasons"])
        self.assertEqual(result["fee_record_refs"][0]["fee_record_id"], fee["record_id"])

    def test_mixed_date_and_precise_same_day_does_not_invent_profitable_sequence(self):
        result = analyze_records([record(1, precision="DATE"), record(2, side="SELL", price="110")], history_complete=True)
        self.assertEqual(result["episodes"], [])
        self.assertTrue(all(item["reason"] == "SAME_TIME_SEQUENCE_UNCERTAIN" for item in result["excluded_records"]))

    def test_minute_and_second_overlap_does_not_invent_sequence(self):
        opening = record(1, precision="MINUTE")
        closing = record(2, side="SELL", price="110")
        closing["occurred_at"] = "2026-09-01T14:30:25Z"
        result = analyze_records([opening, closing], history_complete=True)
        self.assertEqual(result["episodes"], [])
        self.assertTrue(all(item["reason"] == "SAME_TIME_SEQUENCE_UNCERTAIN" for item in result["excluded_records"]))

    def test_minute_precision_does_not_claim_exact_holding_seconds(self):
        result = analyze_records([record(1, precision="MINUTE"), record(2, side="SELL", price="110", day="2026-09-02")], history_complete=True)
        self.assertEqual(result["episodes"][0]["net_pnl"], "98")
        self.assertIsNone(result["episodes"][0]["holding_seconds"])
        self.assertEqual(result["episodes"][0]["holding_status"], "UNAVAILABLE")

    def test_timezone_day_order_does_not_use_lexical_date_before_utc_instant(self):
        # NY date Sep 1 starts 04:00Z. The 02:00Z sell precedes the date-only buy.
        opening = record(1, precision="DATE", price="90")
        selling = record(2, side="SELL", price="100")
        selling["occurred_at"] = "2026-09-01T02:00:00Z"
        result = analyze_records([opening, selling], history_complete=True)
        self.assertEqual(result["episodes"][0]["direction"], "SHORT")
        self.assertEqual(result["episodes"][0]["gross_pnl"], "100")

    def test_long_partial_close_decimal_fees(self):
        trades = [record(1, qty="10", price="100", fees="2"), record(2, side="SELL", qty="4", price="110", fees="1", day="2026-09-02"), record(3, side="SELL", qty="6", price="90", fees="1.5", day="2026-09-03")]
        result = analyze_records(trades, history_complete=True)
        self.assertEqual([item["net_pnl"] for item in result["episodes"]], ["38.2", "-62.7"])
        self.assertEqual(result["by_currency"][0]["net_pnl"], "-24.5")
        self.assertEqual(result["by_currency"][0]["fees"], "4.5")
        self.assertEqual(result["episodes"][0]["holding_seconds"], "86400")

    def test_short_and_cross_zero_fee_allocation(self):
        trades = [record(1, side="SELL", qty="5", price="100", fees="1"), record(2, side="BUY", qty="8", price="90", fees="1.6", day="2026-09-02"), record(3, side="SELL", qty="3", price="95", fees="0.6", day="2026-09-03")]
        result = analyze_records(trades, history_complete=True)
        self.assertEqual([item["direction"] for item in result["episodes"]], ["SHORT", "LONG"])
        self.assertEqual([item["net_pnl"] for item in result["episodes"]], ["48", "13.8"])
        self.assertEqual(result["by_currency"][0]["fees"], "3.2")

    def test_initial_sell_unknown_not_invented_short(self):
        result = analyze_records([record(1, side="SELL", price="110"), record(2, price="90", day="2026-09-02")])
        self.assertIsNone(result["episodes"][0]["net_pnl"])
        self.assertEqual(result["episodes"][0]["direction"], "UNKNOWN")
        self.assertIn("SELL_NOT_PROVEN_SHORT_OPEN", result["episodes"][0]["reasons"])
        self.assertEqual(result["by_currency"][0]["available_episodes"], 0)

    def test_unknown_initial_position_even_buy_first_not_zero_assumed(self):
        result = analyze_records([record(1), record(2, side="SELL", price="110", day="2026-09-02")])
        episode = result["episodes"][0]
        self.assertIsNone(episode["net_pnl"])
        self.assertIsNone(episode["gross_pnl"])
        self.assertIn("OPENING_POSITION_UNKNOWN", episode["reasons"])

    def test_known_opening_inventory_and_pre_window_pair(self):
        initial = {"instrument-US-USD-ABC-STOCK": {"quantity": "10", "price": "100", "fees": "2", "fees_complete": True,
                     "occurred_at": "2026-08-01T14:30:00Z", "time_precision": "SECOND", "source_id": "source-synthetic-position", "as_of": "2026-08-31T14:30:00Z", "retrieved_at": AS_OF}}
        result = analyze_records([record(1, side="SELL", price="110")], opening_positions=initial)
        self.assertEqual(result["episodes"][0]["net_pnl"], "97")
        self.assertEqual(result["episodes"][0]["holding_seconds"], str(31 * 86400))
        bad_initial = deepcopy(initial)
        del bad_initial["instrument-US-USD-ABC-STOCK"]["source_id"]
        with self.assertRaises(JournalError):
            analyze_records([record(1)], opening_positions=bad_initial)

    def test_incomplete_fees_not_treated_as_zero(self):
        result = analyze_records([record(1, fees=None), record(2, side="SELL", price="110", day="2026-09-02")], history_complete=True)
        self.assertIsNone(result["episodes"][0]["net_pnl"])
        self.assertEqual(result["episodes"][0]["gross_pnl"], "100")
        self.assertIn("FEES_INCOMPLETE", result["episodes"][0]["reasons"])

    def test_option_25_multiplier_not_100(self):
        trades = [record(1, asset="OPTION", qty="2", price="2", fees="1", multiplier="25"), record(2, asset="OPTION", qty="2", price="3", fees="1", multiplier="25", side="SELL", day="2026-09-02")]
        result = analyze_records(trades, history_complete=True)
        self.assertEqual(result["episodes"][0]["net_pnl"], "48")
        trades[0]["instrument"]["multiplier"] = None
        self.assertTrue(any(item["reason"] == "MULTIPLIER_UNKNOWN" for item in analyze_records(trades, history_complete=True)["excluded_records"]))

    def test_lifecycle_gap_prevents_later_synthetic_pairing(self):
        trades = [record(1), record(2, activity="TRANSFER", day="2026-09-02"), record(3, side="SELL", price="110", day="2026-09-03")]
        result = analyze_records(trades, history_complete=True)
        self.assertIsNone(result["episodes"][0]["net_pnl"])
        self.assertIsNone(result["episodes"][0]["gross_pnl"])
        self.assertIn("LIFECYCLE_OR_POSITION_CHANGE_UNRECONCILED", result["episodes"][0]["reasons"])

    def test_option_assignment_does_not_manufacture_unlinked_underlying_short(self):
        trades = [record(1, asset="OPTION", activity="ASSIGNMENT", day="2026-09-01"), record(2, side="SELL", day="2026-09-02"), record(3, price="90", day="2026-09-03")]
        result = analyze_records(trades, history_complete=True)
        self.assertEqual(result["episodes"][0]["direction"], "UNKNOWN")
        self.assertIsNone(result["episodes"][0]["net_pnl"])
        self.assertIn("OPTION_LIFECYCLE_UNDERLYING_POSITION_UNCERTAIN", result["episodes"][0]["reasons"])

    def test_explicit_close_cannot_create_opposite_open(self):
        trades = [record(1, qty="5"), record(2, side="SELL", qty="8", price="110", day="2026-09-02", effect="CLOSE")]
        result = analyze_records(trades, history_complete=True)
        self.assertEqual(result["episodes"][0]["quantity"], "5")
        self.assertEqual(result["episodes"][1]["quantity"], "3")
        self.assertIsNone(result["episodes"][1]["net_pnl"])
        self.assertEqual(result["open_positions"], [])

    def test_multi_currency_never_totalled(self):
        trades = [record(1), record(2, side="SELL", price="110", day="2026-09-02"), record(3, currency="HKD", market="HK", symbol="00700", price="300"), record(4, currency="HKD", market="HK", symbol="00700", price="310", side="SELL", day="2026-09-02")]
        result = analyze_records(trades, history_complete=True)
        self.assertEqual({item["currency"] for item in result["by_currency"]}, {"USD", "HKD"})
        self.assertNotIn("total_pnl", result)

    def test_daily_time_not_fabricated_holding_seconds(self):
        result = analyze_records([record(1, precision="DATE"), record(2, side="SELL", price="110", day="2026-09-02", precision="DATE")], history_complete=True)
        self.assertEqual(result["episodes"][0]["net_pnl"], "98")
        self.assertIsNone(result["episodes"][0]["holding_seconds"])

    def test_date_record_at_intraday_window_boundary_not_counted_as_exact(self):
        window = resolve_window("custom", start="2026-09-01T00:00:00Z", end="2026-09-02T15:00:00Z", now=AS_OF)
        result = analyze_records([record(1, precision="DATE"), record(2, side="SELL", price="110", day="2026-09-02", precision="DATE")], history_complete=True, window=window)
        self.assertIsNone(result["episodes"][0]["net_pnl"])
        self.assertIn("WINDOW_BOUNDARY_TIME_UNCERTAIN", result["episodes"][0]["reasons"])

    def test_known_cost_without_original_timestamp_can_still_compute_pnl(self):
        initial = {"instrument-US-USD-ABC-STOCK": {"quantity": "10", "price": "100", "fees": "2", "fees_complete": True,
                     "source_id": "source-synthetic-position", "as_of": "2026-08-31T14:30:00Z", "retrieved_at": AS_OF}}
        result = analyze_records([record(1, side="SELL", price="110")], opening_positions=initial)
        self.assertEqual(result["episodes"][0]["net_pnl"], "97")
        self.assertIsNone(result["episodes"][0]["holding_seconds"])

    def test_same_time_uncertain_sequence_not_sorted_into_fact(self):
        result = analyze_records([record(1), record(2, side="SELL", price="110")], history_complete=True)
        self.assertEqual(result["episodes"], [])
        self.assertTrue(all(item["reason"] == "SAME_TIME_SEQUENCE_UNCERTAIN" for item in result["excluded_records"]))

    def test_fee_residual_conserved_with_thirds(self):
        trades = [record(1, qty="3", fees="1"), record(2, qty="1", side="SELL", fees="0", day="2026-09-02"), record(3, qty="1", side="SELL", fees="0", day="2026-09-03"), record(4, qty="1", side="SELL", fees="0", day="2026-09-04")]
        result = analyze_records(trades, history_complete=True)
        self.assertEqual(Decimal(result["by_currency"][0]["fees"]), Decimal("1"))
        self.assertEqual(Decimal(result["by_currency"][0]["net_pnl"]), Decimal("-1"))

    def test_partial_cancelled_order_not_duplicate_fees(self):
        trades = [record(1, qty="2", fees="0.2"), record(2, qty="3", fees="0.3", day="2026-09-02"), record(3, activity="ORDER", qty="10", fees="99", day="2026-09-03"), record(4, side="SELL", qty="5", price="110", fees="0.5", day="2026-09-04")]
        result = analyze_records(trades, history_complete=True)
        self.assertEqual(result["by_currency"][0]["net_pnl"], "49")
        self.assertEqual(result["by_currency"][0]["fees"], "1")
        self.assertEqual(result["excluded_records"][0]["reason"], "NOT_AN_EXECUTION")


if __name__ == "__main__":
    unittest.main()
