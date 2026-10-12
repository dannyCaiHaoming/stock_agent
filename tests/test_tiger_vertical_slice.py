from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from product.broker.tiger.analysis import analyze_history
from product.broker.tiger.ledger import LEDGER_FILENAME, PrivateBrokerLedger
from product.broker.tiger.normalization import build_account_snapshot, persist_snapshot
from product.broker.tiger.sync import sync_history
from product.intake.tiger import build_tiger_draft
from product.intake.v3 import build_handoff, validate_handoff
from product.web.app import ResearchBrowser
from product.web.read_only import ArtifactCatalog
from product.web.trades import ReadOnlyTradeLedger


RETRIEVED = "2026-09-23T12:00:00Z"


class VerticalFakeTiger:
    def managed_accounts(self):
        return [{"account": "never-persist-this"}]

    def prime_assets(self, **_kwargs):
        return {
            "update_timestamp": 1789991940000,
            "segments": {"S": {
                "currency": "USD", "net_liquidation": 12000,
                "currency_assets": {"USD": {
                    "currency": "USD", "cash_balance": 1000,
                    "cash_available_for_trade": 900,
                }},
            }},
        }

    def positions(self, *, sec_type, **_kwargs):
        if sec_type == "OPT":
            return []
        return [
            {
                "contract": {"symbol": "MRVL", "name": "Marvell", "currency": "USD", "sec_type": "STK", "market": "US", "contract_id": 1},
                "quantity": 10, "salable_qty": 10, "average_cost": 70,
                "market_price": 80, "market_value": 800, "unrealized_pnl": 100,
            },
            {
                "contract": {"symbol": "00700", "name": "Tencent", "currency": "HKD", "sec_type": "STK", "market": "HK", "contract_id": 2},
                "quantity": 100, "salable_qty": 100, "average_cost": 300,
                "market_price": 320, "market_value": 32000, "unrealized_pnl": 2000,
            },
        ]

    def orders(self, **_kwargs):
        return {"result": [{
            "id": 10, "order_id": 10,
            "contract": {"symbol": "MRVL", "currency": "USD", "sec_type": "STK", "market": "US", "contract_id": 1},
            "action": "BUY", "quantity": 10, "filled": 10, "remaining": 0,
            "avg_fill_price": 70, "status": "FILLED", "order_time": 1767283200000,
        }]}

    def transactions(self, **_kwargs):
        return {"result": [{
            "transaction_id": "trade-10", "order_id": 10,
            "contract": {"symbol": "MRVL", "currency": "USD", "sec_type": "STK", "market": "US", "contract_id": 1},
            "action": "BUY", "quantity": 10, "price": 70, "trade_time": 1767283260000,
        }]}

    def order_with_charges(self, **_kwargs):
        value = self.orders()["result"][0]
        value["charges"] = {"details": [{"type": "COMMISSION", "after_discount_amount": 1}]}
        return value

    def analytics_asset(self, **kwargs):
        return {"history": [
            {"dt": kwargs["start_date"], "asset": 10000, "cash_balance": 1000, "deposit_withdraw": 0},
            {"dt": kwargs["end_date"], "asset": 11000, "cash_balance": 1000, "deposit_withdraw": 0},
        ]}

    def fund_details(self, **_kwargs):
        return [{
            "id": "dividend-mrvl", "type": "DIVIDEND", "business_date": "2026-01-15",
            "market": "US", "currency": "USD", "symbol": "MRVL", "amount": 5,
        }]

    def funding_history(self):
        return [{
            "id": "hk-deposit", "type": "DEPOSIT", "date": "2026-01-01",
            "currency": "HKD", "amount": 1000, "status": "COMPLETED",
        }]


class TigerVerticalSliceTests(unittest.TestCase):
    def test_mixed_account_fixture_runs_snapshot_sync_confirm_analysis_and_trade_page(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository = Path(__file__).resolve().parents[1]
            ledger = PrivateBrokerLedger(base / "private", repository_root=repository, create=True)
            account_ref = ledger.get_or_create_account_ref()
            fake = VerticalFakeTiger()

            snapshot = build_account_snapshot(fake, account_ref=account_ref, retrieved_at=RETRIEVED)
            persist_snapshot(ledger, snapshot, batch_id=snapshot["snapshot_id"])
            draft, coverage = build_tiger_draft(snapshot)
            handoff = build_handoff(draft, confirmed=True, confirmed_at="2026-09-23T12:01:00Z")
            validate_handoff(handoff, source_draft=draft)

            manifest = sync_history(
                fake, ledger, account_ref=account_ref,
                history_start="2026-01-01", history_start_accuracy="APPROXIMATE",
                window_end="2026-01-31", retrieved_at=RETRIEVED, sleeper=lambda _seconds: None,
            )
            analysis = analyze_history(
                ledger, account_ref=account_ref, cutoff="2026-09-24T00:00:00Z",
                retrieved_at="2026-09-24T00:01:00Z",
            )

            self.assertEqual(snapshot["account_scope"], "MIXED_MARKET_ACCOUNT")
            self.assertEqual(coverage["excluded_assets"][0]["display_symbol"], "00700")
            self.assertEqual(handoff["portfolio_scope"], "USER_DEFINED_PORTFOLIO")
            self.assertEqual([item["display_symbol"] for item in handoff["portfolio"]["positions"]], ["MRVL"])
            self.assertEqual(manifest["coverage_status"], "API_COMPLETE_WITHIN_DECLARED_WINDOW")
            self.assertGreaterEqual(analysis["excluded_count"], 2)
            self.assertEqual(len(analysis["charts"]), 6)

            database = ledger.database
            database_hash = hashlib.sha256(database.read_bytes()).hexdigest()
            snapshot_hash, draft_hash, handoff_hash = snapshot["content_hash"], draft["draft_hash"], handoff["handoff_hash"]
            reader = ReadOnlyTradeLedger(base / "private", repository_root=repository)
            app = ResearchBrowser(None, ArtifactCatalog(), memory_error="BROWSER_MEMORY_UNAVAILABLE", trades=reader)
            desktop = app.dispatch("GET", "/trades", {"Host": "localhost"})
            html = desktop.body.decode()
            self.assertEqual(desktop.status, 200)
            self.assertGreaterEqual(html.count("<svg"), 3)
            self.assertIn('@media(max-width:720px)', html)
            self.assertIn('name="market"', html)
            self.assertNotIn("never-persist-this", html)
            self.assertEqual(hashlib.sha256(database.read_bytes()).hexdigest(), database_hash)
            self.assertEqual((snapshot["content_hash"], draft["draft_hash"], handoff["handoff_hash"]), (snapshot_hash, draft_hash, handoff_hash))


if __name__ == "__main__":
    unittest.main()
