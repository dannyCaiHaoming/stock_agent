from __future__ import annotations

from copy import deepcopy
import unittest

from product.broker.tiger.contracts import finalize_contract
from product.intake.tiger import TigerIntakeError, build_tiger_draft, render_tiger_coverage
from product.intake.v3 import IntakeV3ValidationError, build_handoff, validate_draft, validate_handoff
from product.runtime.hashing import canonical_hash


AS_OF = "2026-09-23T11:59:00Z"
RETRIEVED = "2026-09-23T12:00:00Z"


def position(symbol, *, market="US", currency="USD", asset_type="COMMON_STOCK", position_id=None):
    basis = {"symbol": symbol, "market": market, "currency": currency, "asset_type": asset_type}
    return {
        "position_id": position_id or f"position:{canonical_hash(basis)}",
        "instrument_key": f"tiger:{canonical_hash(basis)}",
        "provider_contract_id": f"contract-{symbol}",
        "display_symbol": symbol,
        "display_name": symbol,
        "market": market,
        "currency": currency,
        "asset_type": asset_type,
        "identity_status": "OBSERVED",
        "quantity": 10,
        "available_quantity": 10,
        "average_cost": 100,
        "market_price": 110,
        "market_value": 1100,
        "unrealized_pnl": 100,
        "option": None,
        "intake_status": "SUPPORTED_US_USD" if market == "US" and currency == "USD" else "PENDING_FUTURE_RESEARCH",
        "source_id": "tiger:tbhk:account-snapshot",
        "as_of": AS_OF,
        "retrieved_at": RETRIEVED,
        "record_hash": canonical_hash(basis),
    }


def snapshot(*, mixed=True, supported=True, scoped_cash=True, suffix="one"):
    positions = [position("AAPL")] if supported else []
    excluded = []
    if mixed:
        hk = position("00700", market="HK", currency="HKD")
        positions.append(hk)
        excluded.append({
            "position_id": hk["position_id"], "display_symbol": "00700", "market": "HK",
            "currency": "HKD", "asset_type": "COMMON_STOCK",
            "reason": "UNSUPPORTED_FOR_PORTFOLIO_INTAKE", "status": "PENDING_FUTURE_RESEARCH",
        })
    account_values = [
        {
            "field": "cash_balance", "value": 500, "currency": "USD",
            "scope": "US_USD_SEGMENT" if scoped_cash else "WHOLE_ACCOUNT",
            "source_id": "tiger:tbhk:account-snapshot", "as_of": AS_OF, "retrieved_at": RETRIEVED,
        },
        {
            "field": "net_liquidation", "value": 9999, "currency": "USD", "scope": "WHOLE_ACCOUNT",
            "source_id": "tiger:tbhk:account-snapshot", "as_of": AS_OF, "retrieved_at": RETRIEVED,
        },
    ]
    return finalize_contract({
        "schema_version": "tiger-account-snapshot/1.0.0",
        "snapshot_id": f"snapshot:{suffix}",
        "account_ref": "tiger-account:****:local",
        "source_id": "tiger:tbhk:account-snapshot",
        "as_of": AS_OF,
        "retrieved_at": RETRIEVED,
        "license": "TBHK",
        "coverage_status": "COMPLETE",
        "account_scope": "MIXED_MARKET_ACCOUNT" if mixed else "BROKER_ACCOUNT",
        "account_values": account_values,
        "positions": positions,
        "coverage": {
            "visible_position_count": len(positions),
            "supported_position_count": int(supported),
            "excluded_position_count": len(excluded),
            "excluded_assets": excluded,
            "limitations": ["港股投研接入待定"] if excluded else [],
        },
    })


class TigerIntakeTests(unittest.TestCase):
    def test_mixed_account_creates_confirmable_user_defined_draft_without_blocking_hk(self):
        draft, coverage = build_tiger_draft(snapshot())
        validate_draft(draft)
        self.assertEqual(draft["portfolio_scope"], "USER_DEFINED_PORTFOLIO")
        self.assertTrue(draft["portfolio_complete"])
        self.assertEqual(len(draft["positions"]), 1)
        self.assertEqual(draft["positions"][0]["identity"]["display_symbol"]["status"], "EXTRACTED")
        self.assertEqual(draft["unsupported_assets"], [])
        self.assertNotIn("unsupported_assets", draft["unresolved_fields"])
        self.assertEqual(coverage["excluded_assets"][0]["display_symbol"], "00700")
        self.assertIn("投研接入待定", render_tiger_coverage(coverage))
        handoff = build_handoff(draft, confirmed=True, confirmed_at="2026-09-23T12:01:00Z")
        validate_handoff(handoff, source_draft=draft)
        self.assertEqual([item["display_symbol"] for item in handoff["portfolio"]["positions"]], ["AAPL"])

    def test_pure_us_account_uses_broker_scope_and_no_supported_position_stays_unconfirmable(self):
        pure, _ = build_tiger_draft(snapshot(mixed=False))
        self.assertEqual(pure["portfolio_scope"], "BROKER_ACCOUNT")
        self.assertEqual(pure["reconciliation"]["status"], "UNRECONCILED")
        self.assertEqual(pure["account_snapshot"]["margin_used"]["status"], "MISSING")
        empty, coverage = build_tiger_draft(snapshot(mixed=True, supported=False))
        self.assertFalse(empty["portfolio_complete"])
        self.assertIn("positions", empty["unresolved_fields"])
        self.assertEqual(coverage["supported_position_count"], 0)
        with self.assertRaisesRegex(IntakeV3ValidationError, "DRAFT_NOT_CONFIRMABLE"):
            build_handoff(empty, confirmed=True, confirmed_at="2026-09-23T12:01:00Z")

    def test_mixed_whole_account_cash_is_not_misrepresented_as_us_subset(self):
        draft, _ = build_tiger_draft(snapshot(scoped_cash=False))
        self.assertIsNone(draft["account_snapshot"]["cash_balance"]["value"])
        self.assertIn("account_snapshot.cash_balance", draft["unresolved_fields"])
        self.assertIsNone(draft["account_snapshot"]["net_liquidation_value"]["value"])
        self.assertTrue(any("WHOLE_ACCOUNT" in item["label"] for item in draft["account_snapshot"]["broker_reported_fields"]))

    def test_explicit_confirmation_and_snapshot_versioning_preserve_old_handoff(self):
        first, _ = build_tiger_draft(snapshot(suffix="one"))
        with self.assertRaisesRegex(IntakeV3ValidationError, "EXPLICIT_CONFIRMATION_REQUIRED"):
            build_handoff(first, confirmed=False, confirmed_at="2026-09-23T12:01:00Z")
        old_handoff = build_handoff(first, confirmed=True, confirmed_at="2026-09-23T12:01:00Z")

        second_snapshot = snapshot(suffix="two")
        second_snapshot["positions"][0]["quantity"] = 11
        second_snapshot = finalize_contract({key: value for key, value in second_snapshot.items() if key != "content_hash"})
        second, _ = build_tiger_draft(second_snapshot)
        self.assertNotEqual(first["draft_hash"], second["draft_hash"])
        self.assertEqual(old_handoff["portfolio"]["positions"][0]["quantity"], 10)
        self.assertEqual(first["positions"][0]["quantity"]["value"], 10)

    def test_ambiguous_identity_fails_closed_instead_of_inventing_candidates(self):
        value = snapshot()
        value["positions"][0]["identity_status"] = "AMBIGUOUS"
        value = finalize_contract({key: item for key, item in value.items() if key != "content_hash"})
        with self.assertRaises(IntakeV3ValidationError):
            build_tiger_draft(value)


if __name__ == "__main__":
    unittest.main()
