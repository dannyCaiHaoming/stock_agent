from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile
import unittest

from product.broker.tiger.contracts import validate_contract
from product.broker.tiger.ledger import PrivateBrokerLedger
from product.broker.tiger.normalization import (
    TigerNormalizationError,
    build_account_snapshot,
    normalize_fund_detail,
    normalize_funding,
    normalize_position,
    persist_snapshot,
)


RETRIEVED = "2026-09-23T12:00:00Z"


@dataclass
class FakeContract:
    symbol: str
    currency: str
    sec_type: str
    market: str
    contract_id: int | None
    name: str | None = None
    is_etf: bool = False
    expiry: str | None = None
    strike: float | None = None
    put_call: str | None = None
    multiplier: float | None = None
    local_symbol: str | None = None


@dataclass
class FakePosition:
    contract: FakeContract
    quantity: float
    average_cost: float
    market_price: float
    market_value: float
    unrealized_pnl: float
    salable_qty: float


class FakeCurrencyAsset:
    currency = "USD"
    cash_balance = 1500.0
    cash_available_for_trade = 1200.0
    gross_position_value = 9000.0


class FakeSegment:
    currency = "USD"
    net_liquidation = 10500.0
    buying_power = 22000.0
    unrealized_pl = 500.0
    realized_pl = 120.0
    currency_assets = {"USD": FakeCurrencyAsset()}


class FakeAssets:
    update_timestamp = 1789992000000
    segments = {"S": FakeSegment()}


class FakeSnapshotAdapter:
    def __init__(self, by_type):
        self.by_type = by_type
        self.calls = []

    def managed_accounts(self):
        self.calls.append("managed_accounts")
        return [{"account": "must-not-persist"}]

    def prime_assets(self, **kwargs):
        self.calls.append(("prime_assets", kwargs))
        return FakeAssets()

    def positions(self, *, sec_type, currency, market):
        self.calls.append(("positions", sec_type, currency, market))
        return self.by_type.get(sec_type, [])


def us_stock(symbol="AAPL"):
    return FakePosition(
        FakeContract(symbol, "USD", "STK", "US", 101, name="Apple"),
        10, 100, 110, 1100, 100, 10,
    )


def hk_stock():
    return FakePosition(
        FakeContract("00700", "HKD", "STK", "HK", 202, name="Tencent"),
        100, 300, 310, 31000, 1000, 100,
    )


def us_option():
    return FakePosition(
        FakeContract(
            "AAPL", "USD", "OPT", "US", 303, expiry="20261218",
            strike=200, put_call="CALL", multiplier=100, local_symbol="AAPL261218C00200000",
        ),
        1, 12, 15, 1500, 300, 1,
    )


class TigerNormalizationTests(unittest.TestCase):
    def test_mixed_snapshot_keeps_hk_coverage_and_supported_us_assets(self):
        adapter = FakeSnapshotAdapter({"STK": [us_stock(), hk_stock()], "OPT": [us_option()]})
        snapshot = build_account_snapshot(adapter, account_ref="tiger-account:opaque", retrieved_at=RETRIEVED)
        validate_contract(snapshot)
        self.assertEqual(snapshot["account_scope"], "MIXED_MARKET_ACCOUNT")
        self.assertEqual(snapshot["coverage"]["visible_position_count"], 3)
        self.assertEqual(snapshot["coverage"]["supported_position_count"], 2)
        self.assertEqual(snapshot["coverage"]["excluded_position_count"], 1)
        self.assertEqual(snapshot["coverage"]["excluded_assets"][0]["display_symbol"], "00700")
        self.assertEqual(snapshot["positions"][2]["option"]["raw_contract_symbol"], "AAPL261218C00200000")
        self.assertTrue(all(item["scope"] in {"WHOLE_ACCOUNT", "US_USD_SEGMENT"} for item in snapshot["account_values"]))
        self.assertNotIn("must-not-persist", str(snapshot))

    def test_empty_and_pure_us_accounts_have_honest_scope(self):
        empty = build_account_snapshot(FakeSnapshotAdapter({}), account_ref="tiger-account:empty", retrieved_at=RETRIEVED)
        self.assertEqual((empty["account_scope"], empty["coverage"]["visible_position_count"]), ("BROKER_ACCOUNT", 0))
        pure = build_account_snapshot(FakeSnapshotAdapter({"STK": [us_stock()]}), account_ref="tiger-account:us", retrieved_at=RETRIEVED)
        self.assertEqual((pure["account_scope"], pure["coverage"]["excluded_position_count"]), ("BROKER_ACCOUNT", 0))

    def test_position_requires_contract_and_unknown_identity_is_explicit(self):
        with self.assertRaisesRegex(TigerNormalizationError, "CONTRACT_MISSING"):
            normalize_position({}, source_id="source", as_of=RETRIEVED, retrieved_at=RETRIEVED)
        position = normalize_position(
            {"contract": {"symbol": "MYSTERY", "currency": "XXX", "sec_type": "OTHER"}, "quantity": 1},
            source_id="source", as_of=RETRIEVED, retrieved_at=RETRIEVED,
        )
        self.assertEqual((position["identity_status"], position["intake_status"]), ("AMBIGUOUS", "UNCLASSIFIED"))

    def test_snapshot_is_persisted_without_provider_account_identifier(self):
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            repository = base / "repo"
            repository.mkdir(mode=0o700)
            ledger = PrivateBrokerLedger(base / "private", repository_root=repository, create=True)
            account_ref = ledger.get_or_create_account_ref()
            snapshot = build_account_snapshot(
                FakeSnapshotAdapter({"STK": [us_stock(), hk_stock()]}),
                account_ref=account_ref,
                retrieved_at=RETRIEVED,
            )
            results = persist_snapshot(ledger, snapshot, batch_id="snapshot-batch")
            self.assertEqual(len(results), 3)
            activities = ledger.read_current_activities(account_ref=account_ref, cutoff="2026-09-24T00:00:00Z")
            self.assertEqual({item["activity_type"] for item in activities}, {"ACCOUNT_SNAPSHOT", "POSITION"})
            self.assertNotIn("must-not-persist", str(activities))

            newer = build_account_snapshot(
                FakeSnapshotAdapter({"STK": [us_stock(), hk_stock()]}),
                account_ref=account_ref,
                retrieved_at="2026-09-24T00:00:00Z",
            )
            revised = persist_snapshot(ledger, newer, batch_id=newer["snapshot_id"])
            self.assertEqual([item.status for item in revised[1:]], ["REVISED", "REVISED"])
            current = ledger.read_current_activities(account_ref=account_ref, cutoff="2026-09-25T00:00:00Z")
            self.assertEqual(sum(item["activity_type"] == "POSITION" for item in current), 2)

    def test_fund_semantics_and_currencies_remain_distinct(self):
        cases = (
            ("DIVIDEND", "DIVIDEND", "USD"),
            ("WITHHOLDING TAX", "TAX", "USD"),
            ("STOCK SPLIT", "CORPORATE_ACTION", "HKD"),
            ("FOREX EXCHANGE", "FOREX_ACTIVITY", "HKD"),
            ("INTEREST", "CASH_ACTIVITY", "USD"),
        )
        for observed, expected, currency in cases:
            record = normalize_fund_detail(
                {
                    "id": f"id-{observed}", "type": observed, "business_date": "2026-01-01",
                    "currency": currency, "amount": 12,
                },
                account_ref="tiger-account:opaque", retrieved_at=RETRIEVED, batch_id="batch",
            )
            self.assertEqual((record["activity_type"], record["currency"]), (expected, currency))
        funding = normalize_funding(
            {"id": "withdrawal", "type": "WITHDRAWAL", "date": "2026-01-02", "currency": "HKD", "amount": -100},
            account_ref="tiger-account:opaque", retrieved_at=RETRIEVED, batch_id="batch",
        )
        self.assertEqual((funding["activity_type"], funding["currency"], funding["amount"]), ("FUNDING_ACTIVITY", "HKD", -100))


if __name__ == "__main__":
    unittest.main()
