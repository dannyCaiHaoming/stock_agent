from __future__ import annotations

import hashlib
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from product.broker.tiger.analysis import analyze_history
from product.broker.tiger.ledger import LEDGER_FILENAME, PrivateBrokerLedger
from product.web.app import ResearchBrowser
from product.web.read_only import ArtifactCatalog, BrowserDataError
from product.web.trades import ReadOnlyTradeLedger


RETRIEVED = "2026-09-20T00:00:00Z"
CUTOFF = "2026-09-21T00:00:00Z"


class TigerWebTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.repository = Path(__file__).resolve().parents[1]
        self.root = self.base / "private"
        self.ledger = PrivateBrokerLedger(self.root, repository_root=self.repository, create=True)
        self.account_ref = self.ledger.get_or_create_account_ref()

    def tearDown(self):
        self.temporary.cleanup()

    def activity(self, activity_type, provider_id, occurred, **updates):
        value = {
            "activity_type": activity_type, "account_ref": self.account_ref,
            "provider_id": provider_id, "source_id": f"tiger:tbhk:{activity_type.lower()}",
            "as_of": occurred, "retrieved_at": RETRIEVED, "batch_id": "web-fixture",
            "raw_time": occurred, "raw_timezone": "UTC", "occurred_at_utc": occurred,
            "market_date": occurred[:10], "instrument_key": "tiger:aapl",
            "display_symbol": "AAPL", "market": "US", "currency": "USD",
            "asset_type": "COMMON_STOCK", "direction": "BUY", "status": "FILLED",
            "quantity": 1, "price": 100, "amount": 100, "order_id": provider_id,
        }
        value.update(updates)
        return value

    def populate(self, *, many=False):
        self.ledger.record_sync_window({
            "account_ref": self.account_ref, "category": "ORDERS_EXECUTIONS_CHARGES",
            "window_start": "2026-01-01", "window_end": "2026-01-31", "status": "COMPLETE",
            "history_start": "2026-01-01", "history_start_accuracy": "EXACT",
            "page_count": 1, "record_count": 5, "duplicate_count": 0, "revision_count": 0,
            "retrieved_at": RETRIEVED,
        })
        self.ledger.record_sync_window({
            "account_ref": self.account_ref, "category": "FUND_DETAILS",
            "window_start": "2026-01-01", "window_end": "2026-01-31", "status": "FAILED",
            "history_start": "2026-01-01", "history_start_accuracy": "EXACT",
            "page_count": 0, "record_count": 0, "duplicate_count": 0, "revision_count": 0,
            "gap_code": "TIGER_SYNC_TIMEOUT", "retrieved_at": RETRIEVED,
        })
        self.ledger.append_activity(self.activity("EXECUTION", "buy", "2026-01-01T15:00:00Z", order_id="buy", quantity=2, price=100))
        self.ledger.append_activity(self.activity("EXECUTION", "sell", "2026-01-10T15:00:00Z", order_id="sell", quantity=2, price=120, direction="SELL"))
        for order_id in ("buy", "sell"):
            self.ledger.append_activity(self.activity("CHARGE", f"charge-{order_id}", "2026-01-10T14:00:00Z", order_id=order_id, amount=1, quantity=None, price=None))
        if many:
            for index in range(55):
                self.ledger.append_activity(self.activity(
                    "ORDER", f"order-{index}", f"2026-01-{(index % 28) + 1:02d}T13:00:00Z",
                    status="CANCELLED" if index % 2 else "FILLED",
                ))
        for business_date, asset, flow in (("2026-01-01", 1000, 0), ("2026-01-02", 1100, 0)):
            self.ledger.append_asset_point({
                "account_ref": self.account_ref, "source_id": "tiger:tbhk:analytics-asset",
                "as_of": f"{business_date}T00:00:00Z", "retrieved_at": RETRIEVED,
                "business_date": business_date, "currency": "USD", "asset_value": asset,
                "cash_balance": 100, "net_external_flow": flow, "batch_id": "web-fixture",
            })
        return analyze_history(self.ledger, account_ref=self.account_ref, cutoff=CUTOFF, retrieved_at="2026-09-21T00:01:00Z")

    def reader(self):
        return ReadOnlyTradeLedger(self.root, repository_root=self.repository)

    def test_unconfigured_trade_page_does_not_scan_and_health_is_independent(self):
        app = ResearchBrowser(None, ArtifactCatalog(), memory_error="BROWSER_MEMORY_UNAVAILABLE")
        page = app.dispatch("GET", "/trades", {"Host": "localhost"})
        self.assertEqual(page.status, 200)
        self.assertIn("未配置私人账本", page.body.decode())
        health = app.dispatch("GET", "/healthz", {"Host": "localhost"}).body.decode()
        self.assertIn('"trades": {"code": null, "status": "UNCONFIGURED"}', health)

    def test_page_renders_six_inline_svgs_filters_and_pagination_without_raw_payload(self):
        analysis = self.populate(many=True)
        reader = self.reader()
        model = reader.page(query={"category": "ORDER", "page": "1"})
        self.assertEqual((model["total"], model["pages"], len(model["items"])), (55, 2, 50))
        second = reader.page(query={"category": "ORDER", "page": "2"})
        self.assertEqual(len(second["items"]), 5)
        filtered = reader.page(query={"category": "ORDER", "direction": "BUY", "status": "CANCELLED"})
        self.assertGreater(filtered["total"], 0)
        app = ResearchBrowser(None, ArtifactCatalog(), trades=reader, memory_error="BROWSER_MEMORY_UNAVAILABLE")
        html = app.dispatch("GET", f"/trades?analysis={analysis['analysis_id']}", {"Host": "127.0.0.1:8765"}).body.decode()
        self.assertGreaterEqual(html.count("<svg"), 6)
        for phrase in ("资产、净入金与现金流调整收益", "月度现金流调整收益率", "交易活动时间线", "实际窗口", "LIMITED"):
            self.assertIn(phrase, html)
        self.assertNotIn("private_key", html)
        self.assertNotIn("token", html.casefold())
        self.assertNotIn("payload_json", html)
        self.assertEqual(app.dispatch("GET", "/trades/export", {"Host": "localhost"}).status, 404)

    def test_html_svg_escape_and_read_only_browsing_preserve_database_hash(self):
        self.populate()
        database = self.root / LEDGER_FILENAME
        before = hashlib.sha256(database.read_bytes()).hexdigest()
        app = ResearchBrowser(None, ArtifactCatalog(), trades=self.reader(), memory_error="BROWSER_MEMORY_UNAVAILABLE")
        page = app.dispatch("GET", "/trades?symbol=%3Cscript%3Ealert(1)%3C%2Fscript%3E", {"Host": "localhost"})
        html = page.body.decode()
        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertEqual(before, hashlib.sha256(database.read_bytes()).hexdigest())

    def test_bad_or_busy_trade_ledger_degrades_only_trade_domain(self):
        with closing(sqlite3.connect(self.root / LEDGER_FILENAME)) as connection:
            connection.execute("PRAGMA user_version=999")
            connection.commit()
        with self.assertRaisesRegex(BrowserDataError, "VERSION_UNSUPPORTED"):
            self.reader()
        app = ResearchBrowser(None, ArtifactCatalog(), memory_error="BROWSER_MEMORY_UNAVAILABLE", trades_error="BROKER_LEDGER_VERSION_UNSUPPORTED")
        self.assertEqual(app.dispatch("GET", "/trades", {"Host": "localhost"}).status, 503)
        self.assertEqual(app.dispatch("GET", "/market", {"Host": "localhost"}).status, 200)

        class Busy:
            def diagnostic(self):
                return {"status": "READY"}

            def page(self, **_kwargs):
                raise BrowserDataError("BROKER_LEDGER_BUSY")

        busy = ResearchBrowser(None, ArtifactCatalog(), memory_error="BROWSER_MEMORY_UNAVAILABLE", trades=Busy())
        self.assertEqual(busy.dispatch("GET", "/trades", {"Host": "localhost"}).status, 503)

    def test_symlink_ledger_is_rejected(self):
        linked = self.base / "linked"
        linked.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(BrowserDataError, "SYMLINK_REJECTED"):
            ReadOnlyTradeLedger(linked, repository_root=self.repository)


if __name__ == "__main__":
    unittest.main()
