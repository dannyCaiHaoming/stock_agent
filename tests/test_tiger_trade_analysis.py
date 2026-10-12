from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from product.broker.tiger.analysis import analyze_history, assemble_analysis_input
from product.broker.tiger.contracts import validate_contract
from product.broker.tiger.ledger import PrivateBrokerLedger


RETRIEVED = "2026-09-20T00:00:00Z"
CUTOFF = "2026-09-21T00:00:00Z"


class TigerTradeAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        base = Path(self.temporary.name)
        self.repository = base / "repo"
        self.repository.mkdir(mode=0o700)
        self.ledger = PrivateBrokerLedger(base / "private", repository_root=self.repository, create=True)
        self.account_ref = self.ledger.get_or_create_account_ref()

    def tearDown(self):
        self.temporary.cleanup()

    def activity(self, activity_type, provider_id, occurred, **overrides):
        value = {
            "activity_type": activity_type,
            "account_ref": self.account_ref,
            "provider_id": provider_id,
            "source_id": f"tiger:tbhk:{activity_type.lower()}",
            "as_of": occurred,
            "retrieved_at": RETRIEVED,
            "batch_id": "batch-analysis",
            "raw_time": occurred,
            "raw_timezone": "UTC",
            "occurred_at_utc": occurred,
            "market_date": occurred[:10],
            "instrument_key": "tiger:aapl",
            "display_symbol": "AAPL",
            "market": "US",
            "currency": "USD",
            "asset_type": "COMMON_STOCK",
            "direction": "BUY",
            "status": "FILLED",
            "quantity": 1,
            "price": 100,
            "amount": 100,
            "order_id": provider_id,
        }
        value.update(overrides)
        return value

    def complete_coverage(self):
        for category in (
            "ORDERS_EXECUTIONS_CHARGES", "ASSET_POINTS", "FUND_DETAILS", "FUNDING_HISTORY",
        ):
            self.ledger.record_sync_window({
                "account_ref": self.account_ref,
                "category": category,
                "window_start": "2026-01-01",
                "window_end": "2026-01-31",
                "status": "COMPLETE",
                "history_start": "2026-01-01",
                "history_start_accuracy": "EXACT",
                "page_count": 1,
                "record_count": 9,
                "duplicate_count": 0,
                "revision_count": 0,
                "retrieved_at": RETRIEVED,
            })

    def populate_closed_trades(self, *, include_coverage=True):
        if include_coverage:
            self.complete_coverage()
        executions = [
            self.activity("EXECUTION", "exec-buy", "2026-01-01T15:00:00Z", order_id="buy", quantity=10, price=100, direction="BUY", reported_realized_pnl=0),
            self.activity("EXECUTION", "exec-sell-win", "2026-01-10T15:00:00Z", order_id="sell-win", quantity=4, price=120, direction="SELL", reported_realized_pnl=80),
            self.activity("EXECUTION", "exec-sell-loss", "2026-01-20T15:00:00Z", order_id="sell-loss", quantity=6, price=90, direction="SELL", reported_realized_pnl=-60),
        ]
        for item in executions:
            self.ledger.append_activity(item)
        for order_id, occurred, status in (
            ("buy", "2026-01-01T14:59:00Z", "FILLED"),
            ("sell-win", "2026-01-10T14:59:00Z", "FILLED"),
            ("sell-loss", "2026-01-20T14:59:00Z", "CANCELLED"),
        ):
            self.ledger.append_activity(self.activity("ORDER", f"order-{order_id}", occurred, order_id=order_id, status=status))
            self.ledger.append_activity(self.activity("CHARGE", f"charge-{order_id}", occurred, order_id=order_id, amount=1, quantity=None, price=None, status="REPORTED"))
        for business_date, asset, flow in (
            ("2026-01-01", 10000, 0),
            ("2026-01-02", 11000, 500),
            ("2026-01-03", 10500, -500),
        ):
            self.ledger.append_asset_point({
                "account_ref": self.account_ref,
                "source_id": "tiger:tbhk:analytics-asset",
                "as_of": f"{business_date}T00:00:00Z",
                "retrieved_at": RETRIEVED,
                "business_date": business_date,
                "currency": "USD",
                "asset_value": asset,
                "cash_balance": None,
                "net_external_flow": flow,
                "batch_id": "batch-analysis",
            })

    @staticmethod
    def metric(analysis, metric_id):
        return next(item for item in analysis["metrics"] if item["metric_id"] == metric_id)

    def test_formula_v1_fifo_metrics_returns_and_six_charts(self):
        self.populate_closed_trades()
        analysis = analyze_history(
            self.ledger, account_ref=self.account_ref, cutoff=CUTOFF,
            retrieved_at="2026-09-21T00:01:00Z",
        )
        validate_contract(analysis)
        self.assertEqual(analysis["coverage_status"], "API_COMPLETE_WITHIN_DECLARED_WINDOW")
        self.assertEqual(len(analysis["episodes"]), 2)
        self.assertAlmostEqual(self.metric(analysis, "realized_pnl")["value"], 17.0)
        self.assertAlmostEqual(self.metric(analysis, "broker_reported_realized_pnl")["value"], 20.0)
        self.assertAlmostEqual(self.metric(analysis, "fees")["value"], 3.0)
        self.assertAlmostEqual(self.metric(analysis, "win_rate")["value"], 0.5)
        self.assertAlmostEqual(self.metric(analysis, "profit_factor")["value"], 78.6 / 61.6)
        self.assertAlmostEqual(self.metric(analysis, "expectancy")["value"], 8.5)
        self.assertAlmostEqual(self.metric(analysis, "cumulative_return")["value"], 0.05)
        self.assertAlmostEqual(self.metric(analysis, "max_drawdown")["value"], 0.0)
        self.assertEqual(len(analysis["charts"]), 6)
        self.assertEqual({item["chart_id"] for item in analysis["charts"]}, {
            "equity-flow-return", "drawdown", "monthly-return", "security-pnl-fees",
            "holding-period", "activity-timeline",
        })
        self.assertEqual(analysis["by_month"][0]["return_unit"], "RATIO")
        self.assertEqual(analysis["by_month"][0]["pnl_unit"], "USD")
        self.assertEqual(analysis["by_security"][0]["system_review_net_pnl"], 17.0)
        self.assertEqual(analysis["by_security"][0]["broker_reported_realized_pnl"], 20.0)

    def test_mixed_market_and_unknown_records_are_counted_but_not_aggregated(self):
        self.populate_closed_trades()
        self.ledger.append_activity(self.activity(
            "EXECUTION", "hk-trade", "2026-01-21T02:00:00Z",
            market="HK", currency="HKD", display_symbol="00700", instrument_key="tiger:00700",
        ))
        self.ledger.append_activity(self.activity(
            "EXECUTION", "unknown-trade", "2026-01-22T02:00:00Z",
            market="UNKNOWN", currency="UNKNOWN", display_symbol="UNKNOWN", instrument_key=None,
        ))
        frozen = assemble_analysis_input(self.ledger, account_ref=self.account_ref, cutoff=CUTOFF)
        self.assertEqual((frozen.excluded_count, frozen.unknown_count), (1, 1))
        analysis = analyze_history(self.ledger, account_ref=self.account_ref, cutoff=CUTOFF, retrieved_at="2026-09-21T00:01:00Z")
        self.assertEqual((analysis["excluded_count"], analysis["unknown_count"]), (1, 1))
        self.assertTrue(any("非 US/非 USD" in item for item in analysis["limitations"]))

    def test_missing_fee_coverage_open_position_and_short_window_are_explicitly_unavailable(self):
        self.ledger.append_activity(self.activity(
            "EXECUTION", "open-buy", "2026-01-01T15:00:00Z", order_id="open", quantity=5, price=100,
        ))
        self.ledger.append_asset_point({
            "account_ref": self.account_ref, "source_id": "tiger:tbhk:analytics-asset",
            "as_of": "2026-01-01T00:00:00Z", "retrieved_at": RETRIEVED,
            "business_date": "2026-01-01", "currency": "USD", "asset_value": 1000,
            "cash_balance": 500, "net_external_flow": 0, "batch_id": "batch",
        })
        analysis = analyze_history(self.ledger, account_ref=self.account_ref, cutoff=CUTOFF, retrieved_at="2026-09-21T00:01:00Z")
        self.assertEqual(analysis["episodes"][0]["status"], "OPEN")
        self.assertEqual(self.metric(analysis, "fees")["status"], "UNAVAILABLE")
        self.assertEqual(self.metric(analysis, "dividends")["status"], "UNAVAILABLE")
        self.assertEqual(self.metric(analysis, "taxes")["status"], "UNAVAILABLE")
        self.assertEqual(self.metric(analysis, "cumulative_return")["status"], "UNAVAILABLE")
        self.assertEqual(next(item for item in analysis["charts"] if item["chart_id"] == "equity-flow-return")["status"], "UNAVAILABLE")

    def test_latest_successful_receipt_supersedes_failed_attempt_for_coverage(self):
        categories = (
            "ORDERS_EXECUTIONS_CHARGES", "ASSET_POINTS", "FUND_DETAILS", "FUNDING_HISTORY",
        )
        for category in categories:
            self.ledger.record_sync_window({
                "account_ref": self.account_ref,
                "category": category,
                "window_start": "2026-01-01",
                "window_end": "2026-01-31",
                "status": "FAILED",
                "history_start": "2026-01-01",
                "history_start_accuracy": "EXACT",
                "page_count": 0,
                "record_count": 0,
                "duplicate_count": 0,
                "revision_count": 0,
                "gap_code": "TIGER_SYNC_TIMEOUT",
                "retrieved_at": "2026-09-19T00:00:00Z",
            })
            self.ledger.record_sync_window({
                "account_ref": self.account_ref,
                "category": category,
                "window_start": "2026-01-01",
                "window_end": "2026-01-31",
                "status": "COMPLETE",
                "history_start": "2026-01-01",
                "history_start_accuracy": "EXACT",
                "page_count": 1,
                "record_count": 0,
                "duplicate_count": 0,
                "revision_count": 0,
                "retrieved_at": RETRIEVED,
            })
        frozen = assemble_analysis_input(self.ledger, account_ref=self.account_ref, cutoff=CUTOFF)
        self.assertEqual(frozen.coverage_status, "API_COMPLETE_WITHIN_DECLARED_WINDOW")
        self.assertEqual(len(frozen.sync_windows), 4)

    def test_partial_coverage_marks_nonempty_return_charts_limited(self):
        for business_date, asset in (("2026-01-01", 1000), ("2026-01-02", 1010)):
            self.ledger.append_asset_point({
                "account_ref": self.account_ref, "source_id": "tiger:tbhk:analytics-asset",
                "as_of": f"{business_date}T00:00:00Z", "retrieved_at": RETRIEVED,
                "business_date": business_date, "currency": "USD", "asset_value": asset,
                "cash_balance": None, "net_external_flow": 0, "batch_id": "batch",
            })
        analysis = analyze_history(
            self.ledger, account_ref=self.account_ref, cutoff=CUTOFF,
            retrieved_at="2026-09-21T00:01:00Z",
        )
        for chart_id in ("equity-flow-return", "drawdown", "monthly-return"):
            chart = next(item for item in analysis["charts"] if item["chart_id"] == chart_id)
            self.assertEqual(chart["status"], "LIMITED")

    def test_frozen_cutoff_does_not_change_after_later_revision(self):
        self.populate_closed_trades()
        before = analyze_history(self.ledger, account_ref=self.account_ref, cutoff=CUTOFF, retrieved_at="2026-09-21T00:01:00Z")
        revised = self.activity(
            "EXECUTION", "exec-sell-win", "2026-01-10T15:00:00Z",
            order_id="sell-win", quantity=4, price=130, direction="SELL",
            retrieved_at="2026-09-22T00:00:00Z", batch_id="revision",
        )
        self.ledger.append_activity(revised)
        after_same_cutoff = analyze_history(self.ledger, account_ref=self.account_ref, cutoff=CUTOFF, retrieved_at="2026-09-22T00:01:00Z")
        after_new_cutoff = analyze_history(
            self.ledger, account_ref=self.account_ref, cutoff="2026-09-23T00:00:00Z",
            retrieved_at="2026-09-23T00:01:00Z",
        )
        self.assertEqual(before["ledger_hash"], after_same_cutoff["ledger_hash"])
        self.assertEqual(self.metric(before, "realized_pnl")["value"], self.metric(after_same_cutoff, "realized_pnl")["value"])
        self.assertNotEqual(before["ledger_hash"], after_new_cutoff["ledger_hash"])
        self.assertNotEqual(self.metric(before, "realized_pnl")["value"], self.metric(after_new_cutoff, "realized_pnl")["value"])

    def test_short_partial_close_and_corporate_action_do_not_force_close_open_lots(self):
        self.complete_coverage()
        self.ledger.append_activity(self.activity(
            "EXECUTION", "short-open", "2026-02-01T15:00:00Z",
            order_id="short-open", direction="SELL", quantity=5, price=50,
        ))
        self.ledger.append_activity(self.activity(
            "EXECUTION", "short-cover", "2026-02-02T15:00:00Z",
            order_id="short-cover", direction="BUY", quantity=2, price=40,
        ))
        for order_id in ("short-open", "short-cover"):
            self.ledger.append_activity(self.activity(
                "CHARGE", f"charge-{order_id}", "2026-02-02T14:00:00Z",
                order_id=order_id, amount=0, quantity=None, price=None,
            ))
        self.ledger.append_activity(self.activity(
            "CORPORATE_ACTION", "option-assignment-missing-leg", "2026-02-03T15:00:00Z",
            asset_type="LISTED_OPTION", description="assignment leg unavailable",
            quantity=None, price=None, amount=None,
        ))
        analysis = analyze_history(self.ledger, account_ref=self.account_ref, cutoff=CUTOFF, retrieved_at="2026-09-21T00:01:00Z")
        statuses = [item["status"] for item in analysis["episodes"]]
        self.assertEqual(statuses.count("CLOSED"), 1)
        self.assertEqual(statuses.count("OPEN"), 1)
        closed = next(item for item in analysis["episodes"] if item["status"] == "CLOSED")
        opened = next(item for item in analysis["episodes"] if item["status"] == "OPEN")
        self.assertEqual((closed["gross_pnl"], opened["quantity"]), (20.0, -3.0))
        self.assertTrue(any("公司行动" in item for item in analysis["limitations"]))

    def test_unrealized_pnl_uses_only_positions_in_latest_account_snapshot(self):
        self.complete_coverage()
        for batch_id, observed_at, unrealized in (
            ("snapshot-old", "2026-01-01T00:00:00Z", 125),
            ("snapshot-new", "2026-01-02T00:00:00Z", None),
        ):
            self.ledger.append_activity(self.activity(
                "ACCOUNT_SNAPSHOT", batch_id, observed_at,
                batch_id=batch_id, instrument_key=None, display_symbol=None,
                market=None, currency=None, asset_type=None, direction=None,
                status=None, quantity=None, price=None, amount=None, order_id=None,
            ))
            if unrealized is not None:
                self.ledger.append_activity(self.activity(
                    "POSITION", "current-position:tiger:aapl", observed_at,
                    batch_id=batch_id, direction=None, status=None,
                    quantity=10, price=100, amount=1000, order_id=None,
                    position={"unrealized_pnl": unrealized},
                ))
        analysis = analyze_history(
            self.ledger, account_ref=self.account_ref, cutoff=CUTOFF,
            retrieved_at="2026-09-21T00:01:00Z",
        )
        self.assertEqual(self.metric(analysis, "unrealized_pnl")["status"], "UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
