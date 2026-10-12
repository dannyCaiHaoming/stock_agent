from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from product.broker.tiger.contracts import validate_contract
from product.broker.tiger.ledger import PrivateBrokerLedger
from product.broker.tiger.sync import date_windows, sync_history


RETRIEVED = "2026-09-23T12:00:00Z"


def contract(symbol="AAPL", market="US", currency="USD", contract_id=101):
    return {
        "symbol": symbol,
        "market": market,
        "currency": currency,
        "sec_type": "STK",
        "contract_id": contract_id,
    }


def order(order_id, *, filled, status="FILLED", symbol="AAPL"):
    return {
        "id": order_id,
        "order_id": order_id,
        "contract": contract(symbol=symbol),
        "action": "BUY",
        "quantity": 3,
        "filled": filled,
        "remaining": 3 - filled,
        "avg_fill_price": 100,
        "status": status,
        "order_time": 1780000000000,
        "update_time": 1780000300000,
    }


class FakeSyncAdapter:
    def __init__(self):
        self.calls = []
        self.fail_order_window_start = None
        self.repeat_cursor = False
        self.rate_limit_once = False

    def orders(self, **kwargs):
        self.calls.append(("orders", kwargs.copy()))
        if kwargs["start_time"] == self.fail_order_window_start:
            raise TimeoutError("provider timed out")
        if self.rate_limit_once:
            self.rate_limit_once = False
            raise RuntimeError("429 rate limit")
        token = kwargs["page_token"]
        if self.repeat_cursor:
            return {"result": [order(1, filled=1)], "next_page_token": "same"}
        if token == "":
            return {"result": [order(1, filled=2)], "next_page_token": "next-orders"}
        return {"result": [order(2, filled=1, status="CANCELLED", symbol="MSFT")]}

    def transactions(self, **kwargs):
        self.calls.append(("transactions", kwargs.copy()))
        order_id = kwargs["order_id"]
        return {
            "result": [{
                "transaction_id": f"trade-{order_id}",
                "order_id": order_id,
                "contract": contract(symbol="AAPL" if order_id == 1 else "MSFT", contract_id=order_id),
                "action": "BUY",
                "quantity": 2 if order_id == 1 else 1,
                "price": 100,
                "trade_time": 1780000200000,
            }]
        }

    def order_with_charges(self, **kwargs):
        self.calls.append(("order_with_charges", kwargs.copy()))
        item = order(kwargs["order_id"], filled=1)
        item["charges"] = {"details": [{"type": "COMMISSION", "after_discount_amount": 1.25}]}
        return item

    def analytics_asset(self, **kwargs):
        self.calls.append(("analytics_asset", kwargs.copy()))
        return {"history": [{"dt": kwargs["start_date"], "asset": 10000, "cash_balance": 1000, "deposit_withdraw": 0}]}

    def fund_details(self, **kwargs):
        self.calls.append(("fund_details", kwargs.copy()))
        return [{
            "id": "dividend-1", "type": "DIVIDEND", "business_date": "2026-01-15",
            "currency": "USD", "market": "US", "symbol": "AAPL", "amount": 10,
        }]

    def funding_history(self):
        self.calls.append(("funding_history", {}))
        return [{
            "id": "deposit-1", "type": "DEPOSIT", "date": "2026-01-01",
            "currency": "USD", "amount": 5000, "status": "COMPLETED",
        }]


class TigerSyncTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.repository = base / "repo"
        self.repository.mkdir(mode=0o700)
        self.ledger = PrivateBrokerLedger(base / "private", repository_root=self.repository, create=True)
        self.account_ref = self.ledger.get_or_create_account_ref()

    def tearDown(self):
        self.temporary.cleanup()

    def run_sync(self, adapter, *, start="2026-01-01", end="2026-01-31"):
        return sync_history(
            adapter, self.ledger, account_ref=self.account_ref,
            history_start=start, history_start_accuracy="APPROXIMATE", window_end=end,
            retrieved_at=RETRIEVED, sleeper=lambda _seconds: None,
        )

    def test_windows_are_bounded_to_ninety_days(self):
        self.assertEqual(
            date_windows("2026-01-01", "2026-07-01"),
            [("2026-01-01", "2026-03-31"), ("2026-04-01", "2026-06-29"), ("2026-06-30", "2026-07-01")],
        )

    def test_sync_paginates_all_states_and_saves_partial_fills_fees_and_cash(self):
        adapter = FakeSyncAdapter()
        manifest = self.run_sync(adapter)
        validate_contract(manifest)
        self.assertEqual(manifest["coverage_status"], "API_COMPLETE_WITHIN_DECLARED_WINDOW")
        first_order_call = next(kwargs for name, kwargs in adapter.calls if name == "orders")
        self.assertEqual(first_order_call["end_time"], "2026-02-01")
        self.assertTrue(any(receipt["next_token_seen"] for receipt in manifest["windows"] if receipt["category"] == "ORDERS_EXECUTIONS_CHARGES"))
        activities = self.ledger.read_current_activities(account_ref=self.account_ref, cutoff="2026-09-24T00:00:00Z")
        types = [item["activity_type"] for item in activities]
        self.assertEqual(types.count("ORDER"), 2)
        self.assertEqual(types.count("EXECUTION"), 2)
        self.assertEqual(types.count("CHARGE"), 2)
        self.assertIn("DIVIDEND", types)
        self.assertIn("FUNDING_ACTIVITY", types)
        cancelled = next(item for item in activities if item["activity_type"] == "ORDER" and item["status"] == "CANCELLED")
        self.assertEqual(cancelled["filled_quantity"], 1)
        self.assertEqual(self.ledger.latest_complete_window_end(account_ref=self.account_ref, category="ORDERS_EXECUTIONS_CHARGES"), "2026-01-31")

    def test_repeat_sync_observes_instead_of_duplicating_economic_activity(self):
        adapter = FakeSyncAdapter()
        first = self.run_sync(adapter)
        before = len(self.ledger.read_current_activities(account_ref=self.account_ref, cutoff="2026-09-24T00:00:00Z"))
        second = sync_history(
            adapter, self.ledger, account_ref=self.account_ref,
            history_start="2026-01-01", history_start_accuracy="APPROXIMATE", window_end="2026-01-31",
            retrieved_at="2026-09-24T12:00:00Z", sleeper=lambda _seconds: None,
        )
        after = len(self.ledger.read_current_activities(account_ref=self.account_ref, cutoff="2026-09-25T00:00:00Z"))
        self.assertEqual(before, after)
        self.assertGreater(second["duplicate_count"], 0)
        self.assertNotEqual(first["content_hash"], second["content_hash"])

    def test_repeated_cursor_and_middle_failure_leave_gap_and_do_not_advance_watermark(self):
        adapter = FakeSyncAdapter()
        adapter.fail_order_window_start = "2026-04-01"
        manifest = self.run_sync(adapter, start="2026-01-01", end="2026-07-01")
        self.assertEqual(manifest["coverage_status"], "PARTIAL")
        self.assertTrue(any(gap["start"] == "2026-04-01" for gap in manifest["gaps"]))
        self.assertEqual(self.ledger.latest_complete_window_end(account_ref=self.account_ref, category="ORDERS_EXECUTIONS_CHARGES"), "2026-03-31")

        other = FakeSyncAdapter()
        other.repeat_cursor = True
        repeated = self.run_sync(other, start="2025-01-01", end="2025-01-31")
        self.assertTrue(any(gap["error_code"] == "TIGER_SYNC_REPEATED_CURSOR" for gap in repeated["gaps"]))

    def test_rate_limit_is_retried_with_bounded_policy(self):
        adapter = FakeSyncAdapter()
        adapter.rate_limit_once = True
        manifest = self.run_sync(adapter)
        self.assertEqual(manifest["coverage_status"], "API_COMPLETE_WITHIN_DECLARED_WINDOW")
        self.assertGreaterEqual(sum(name == "orders" for name, _ in adapter.calls), 3)


if __name__ == "__main__":
    unittest.main()
