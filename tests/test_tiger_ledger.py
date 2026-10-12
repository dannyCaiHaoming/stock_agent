from __future__ import annotations

from copy import deepcopy
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from product.broker.tiger.contracts import TigerContractError, finalize_contract, validate_contract
from product.broker.tiger.ledger import (
    LEDGER_APPLICATION_ID,
    LEDGER_FILENAME,
    PrivateBrokerLedger,
    PrivateBrokerLedgerError,
)
from product.runtime.schema_validation import SchemaValidationError


RETRIEVED = "2026-09-23T12:00:00Z"


def snapshot_contract() -> dict:
    return {
        "schema_version": "tiger-account-snapshot/1.0.0",
        "snapshot_id": "snapshot:test",
        "account_ref": "tiger-account:opaque",
        "source_id": "tiger:tbhk:account-snapshot",
        "as_of": RETRIEVED,
        "retrieved_at": RETRIEVED,
        "license": "TBHK",
        "coverage_status": "COMPLETE",
        "account_scope": "BROKER_ACCOUNT",
        "account_values": [],
        "positions": [],
        "coverage": {
            "visible_position_count": 0,
            "supported_position_count": 0,
            "excluded_position_count": 0,
            "excluded_assets": [],
            "limitations": [],
        },
    }


def sync_contract() -> dict:
    return {
        "schema_version": "broker-sync-manifest/1.0.0",
        "sync_id": "sync:test",
        "account_ref": "tiger-account:opaque",
        "source_id": "tiger:tbhk:history-sync",
        "as_of": RETRIEVED,
        "retrieved_at": RETRIEVED,
        "provider": "TIGER_TBHK",
        "sdk_version": "3.8.0",
        "history_start": "2026-01-01",
        "history_start_accuracy": "APPROXIMATE",
        "window_start": "2026-01-01",
        "window_end": "2026-09-23",
        "coverage_status": "PARTIAL",
        "category_counts": [],
        "windows": [],
        "duplicate_count": 0,
        "revision_count": 0,
        "gaps": [],
        "limitations": [],
    }


def analysis_contract() -> dict:
    return {
        "schema_version": "trade-history-analysis/1.0.0",
        "analysis_id": "analysis:test",
        "account_ref": "tiger-account:opaque",
        "source_id": "private-broker-ledger:analysis",
        "as_of": RETRIEVED,
        "retrieved_at": RETRIEVED,
        "ledger_hash": "0" * 64,
        "formula_version": "trade-history-formula/1.0.0",
        "window_start": "2026-01-01",
        "window_end": "2026-09-23",
        "coverage_status": "PARTIAL",
        "included_count": 0,
        "excluded_count": 0,
        "unknown_count": 0,
        "metrics": [],
        "episodes": [],
        "by_security": [],
        "by_month": [],
        "charts": [],
        "limitations": [],
        "advisory_only": True,
        "tax_report": False,
        "broker_statement": False,
        "backtest": False,
    }


class TigerContractTests(unittest.TestCase):
    def test_all_three_contracts_validate_and_hash(self):
        for value in (snapshot_contract(), sync_contract(), analysis_contract()):
            finalized = finalize_contract(value)
            self.assertEqual(len(finalized["content_hash"]), 64)
            validate_contract(finalized)

    def test_contracts_reject_unknown_fields_and_hash_mutation(self):
        unknown = snapshot_contract()
        unknown["raw_account"] = "must-not-cross-boundary"
        with self.assertRaisesRegex(SchemaValidationError, "SCHEMA_EXTRA_PROPERTY"):
            finalize_contract(unknown)

        finalized = finalize_contract(sync_contract())
        finalized["coverage_status"] = "API_COMPLETE_WITHIN_DECLARED_WINDOW"
        with self.assertRaisesRegex(TigerContractError, "HASH_MISMATCH"):
            validate_contract(finalized)

    def test_manifest_cannot_claim_future_reconciled_status(self):
        value = sync_contract()
        value["coverage_status"] = "FULL_HISTORY_RECONCILED"
        with self.assertRaisesRegex(SchemaValidationError, "SCHEMA_ENUM_INVALID"):
            finalize_contract(value)


class TigerLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repository = self.base / "repo"
        self.repository.mkdir(mode=0o700)
        self.root = self.base / "private-ledger"
        self.ledger = PrivateBrokerLedger(self.root, repository_root=self.repository, create=True)
        self.account_ref = self.ledger.get_or_create_account_ref()

    def tearDown(self):
        self.temporary.cleanup()

    def activity(self, **overrides) -> dict:
        value = {
            "activity_type": "EXECUTION",
            "account_ref": self.account_ref,
            "provider_id": "transaction-1",
            "source_id": "tiger:tbhk:transactions",
            "as_of": "2026-01-02T15:30:00Z",
            "retrieved_at": RETRIEVED,
            "batch_id": "batch-1",
            "raw_time": "2026-01-02 10:30:00",
            "raw_timezone": "America/New_York",
            "occurred_at_utc": "2026-01-02T15:30:00Z",
            "market_date": "2026-01-02",
            "instrument_key": "tiger:contract:1",
            "display_symbol": "AAPL",
            "market": "US",
            "currency": "USD",
            "asset_type": "COMMON_STOCK",
            "direction": "BUY",
            "status": "FILLED",
            "quantity": 10,
            "price": 100,
            "amount": 1000,
            "order_id": "order-1",
        }
        value.update(overrides)
        return value

    def test_schema_has_exactly_four_tables_and_opaque_reference_is_stable(self):
        diagnostic = self.ledger.diagnostic()
        self.assertEqual(
            diagnostic["tables"],
            ["activity_revisions", "analysis_packages", "asset_points", "sync_windows"],
        )
        self.assertEqual(self.account_ref, self.ledger.get_or_create_account_ref())
        self.assertNotIn("private-account", self.account_ref)
        self.assertEqual(self.root.stat().st_mode & 0o077, 0)
        self.assertEqual((self.root / LEDGER_FILENAME).stat().st_mode & 0o077, 0)

    def test_activity_is_append_only_with_observation_and_revision(self):
        inserted = self.ledger.append_activity(self.activity())
        observed = self.ledger.append_activity(self.activity(retrieved_at="2026-09-24T00:00:00Z", batch_id="batch-2"))
        revised = self.ledger.append_activity(self.activity(price=101, amount=1010, retrieved_at="2026-09-25T00:00:00Z", batch_id="batch-3"))
        self.assertEqual((inserted.status, inserted.revision), ("INSERTED", 1))
        self.assertEqual((observed.status, observed.revision), ("OBSERVED", 1))
        self.assertEqual((revised.status, revised.revision), ("REVISED", 2))
        current = self.ledger.read_current_activities(account_ref=self.account_ref, cutoff="2026-09-26T00:00:00Z")
        self.assertEqual(len(current), 1)
        self.assertEqual((current[0]["price"], current[0]["_ledger"]["revision"]), (101, 2))
        with self.ledger.read_connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM activity_revisions").fetchone()[0], 2)

    def test_derived_key_deduplicates_and_sensitive_keys_are_rejected(self):
        first = self.activity(provider_id=None)
        second = deepcopy(first)
        second["retrieved_at"] = "2026-09-24T00:00:00Z"
        self.assertEqual(self.ledger.append_activity(first).status, "INSERTED")
        self.assertEqual(self.ledger.append_activity(second).status, "OBSERVED")
        with self.assertRaisesRegex(PrivateBrokerLedgerError, "SENSITIVE_FIELD_REJECTED"):
            self.ledger.append_activity(self.activity(token="secret"))

    def test_asset_points_retain_revisions(self):
        point = {
            "account_ref": self.account_ref,
            "source_id": "tiger:tbhk:analytics-asset",
            "as_of": "2026-01-02T00:00:00Z",
            "retrieved_at": RETRIEVED,
            "business_date": "2026-01-02",
            "currency": "USD",
            "asset_value": 1000,
            "cash_balance": 100,
            "net_external_flow": 0,
            "batch_id": "batch-1",
        }
        self.assertEqual(self.ledger.append_asset_point(point).status, "INSERTED")
        observed = {**point, "retrieved_at": "2026-09-24T00:00:00Z", "batch_id": "batch-2"}
        self.assertEqual(self.ledger.append_asset_point(observed).status, "OBSERVED")
        revised = {**point, "asset_value": 1010, "retrieved_at": "2026-09-25T00:00:00Z", "batch_id": "batch-3"}
        self.assertEqual(self.ledger.append_asset_point(revised).status, "REVISED")
        rows = self.ledger.read_current_asset_points(account_ref=self.account_ref, cutoff="2026-09-26T00:00:00Z")
        self.assertEqual((len(rows), rows[0]["asset_value"], rows[0]["_ledger"]["revision"]), (1, 1010, 2))

    def test_rejects_inside_repository_symlink_open_permissions_and_unknown_version(self):
        with self.assertRaisesRegex(PrivateBrokerLedgerError, "MUST_BE_EXTERNAL"):
            PrivateBrokerLedger(self.repository / "ledger", repository_root=self.repository, create=True)

        linked = self.base / "linked-ledger"
        linked.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(PrivateBrokerLedgerError, "SYMLINK_REJECTED"):
            PrivateBrokerLedger(linked, repository_root=self.repository)

        os.chmod(self.root, 0o755)
        with self.assertRaisesRegex(PrivateBrokerLedgerError, "PERMISSIONS_TOO_OPEN"):
            PrivateBrokerLedger(self.root, repository_root=self.repository)
        os.chmod(self.root, 0o700)

        with closing(sqlite3.connect(self.root / LEDGER_FILENAME)) as connection:
            connection.execute(f"PRAGMA application_id = {LEDGER_APPLICATION_ID}")
            connection.execute("PRAGMA user_version = 999")
            connection.commit()
        with self.assertRaisesRegex(PrivateBrokerLedgerError, "VERSION_UNSUPPORTED"):
            PrivateBrokerLedger(self.root, repository_root=self.repository)

    def test_read_connection_is_query_only_and_busy_is_stable(self):
        with self.ledger.read_connection() as connection:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("DELETE FROM sync_windows")

        blocker = sqlite3.connect(self.root / LEDGER_FILENAME, timeout=0.1)
        try:
            blocker.execute("BEGIN IMMEDIATE")
            with self.assertRaisesRegex(PrivateBrokerLedgerError, "BROKER_LEDGER_BUSY"):
                self.ledger.append_activity(self.activity())
        finally:
            blocker.rollback()
            blocker.close()


if __name__ == "__main__":
    unittest.main()
