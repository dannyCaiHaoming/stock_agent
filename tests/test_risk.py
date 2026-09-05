from __future__ import annotations

import random
import unittest
from datetime import timedelta
from decimal import Decimal

from product.deterministic.metrics import (
    METRIC_DEFINITION_VERSION,
    calculate_portfolio_metrics,
)
from product.deterministic.policy import (
    ALLOWED_POLICY_METRICS,
    Mandate,
    RiskPolicy,
    RuleBasis,
    validate_rule_metric,
)
from product.deterministic.portfolio import (
    PortfolioValidationError,
    PriceObservation,
    SecurityRecord,
    normalize_portfolio,
)
from product.deterministic.risk import (
    RiskEngine,
    RiskStatus,
    TargetWeightRange,
    VetoCode,
)


D = Decimal


def fixture_securities(*, same_sector: bool = False) -> tuple[SecurityRecord, ...]:
    return (
        SecurityRecord("SEC-AAA", ("AAA",), "Technology"),
        SecurityRecord(
            "SEC-BBB",
            ("BBB",),
            "Technology" if same_sector else "Healthcare",
        ),
    )


def fixture_prices(
    *, stale: bool = False, missing_liquidity: bool = False
) -> dict[str, PriceObservation]:
    as_of = "2025-01-01T21:00:00Z" if stale else "2026-01-02T21:00:00Z"
    return {
        "SEC-AAA": PriceObservation(
            "SEC-AAA",
            D("100"),
            as_of,
            "fixture-market",
            "USD",
            None if missing_liquidity else D("100000"),
        ),
        "SEC-BBB": PriceObservation(
            "SEC-BBB",
            D("100"),
            as_of,
            "fixture-market",
            "USD",
            D("100000"),
        ),
    }


def fixture_input() -> dict[str, object]:
    return {
        "snapshot_id": "snapshot-1",
        "as_of": "2026-01-02T22:00:00Z",
        "base_currency": "USD",
        "benchmark": "FIXTURE-INDEX",
        "mandate_version": "mandate/1",
        "cash": "2500",
        "declared_total_value": "10000",
        "positions": [
            {"identifier": "AAA", "quantity": "50"},
            {"identifier": "BBB", "quantity": "25"},
        ],
    }


def fixture_snapshot(*, same_sector: bool = False, missing_liquidity: bool = False):
    return normalize_portfolio(
        fixture_input(),
        securities=fixture_securities(same_sector=same_sector),
        prices=fixture_prices(missing_liquidity=missing_liquidity),
        cutoff="2026-01-02T22:00:00Z",
        max_price_age=timedelta(days=1),
    )


def fixture_policy(**overrides: object) -> RiskPolicy:
    values: dict[str, object] = {
        "version": "risk/1",
        "mandate_version": "mandate/1",
        "max_position_weight": D("0.65"),
        "max_sector_weight": D("0.80"),
        "min_cash_weight": D("0.10"),
        "max_turnover": D("0.40"),
        "max_adv_participation": D("0.20"),
        "max_price_age": timedelta(days=1),
        "simulated_cost_bps": D("10"),
    }
    values.update(overrides)
    return RiskPolicy(**values)


class PortfolioNormalizationTests(unittest.TestCase):
    def test_normalization_resolves_and_conserves_amounts(self) -> None:
        snapshot = fixture_snapshot()
        self.assertEqual(snapshot.total_value, D("10000"))
        self.assertEqual(snapshot.cash, D("2500"))
        self.assertEqual(snapshot.cash_weight, D("0.25"))
        self.assertEqual(
            {position.security_id: position.weight for position in snapshot.positions},
            {"SEC-AAA": D("0.5"), "SEC-BBB": D("0.25")},
        )

    def test_duplicate_unknown_missing_cash_stale_and_conservation_fail(self) -> None:
        cases: list[tuple[str, dict[str, object], dict[str, PriceObservation]]] = []
        duplicate = fixture_input()
        duplicate["positions"] = [
            {"identifier": "AAA", "quantity": "50"},
            {"identifier": "SEC-AAA", "quantity": "1"},
        ]
        cases.append(("DUPLICATE_POSITION", duplicate, fixture_prices()))
        unknown = fixture_input()
        unknown["positions"] = [{"identifier": "UNKNOWN", "quantity": "1"}]
        cases.append(("UNKNOWN_SECURITY", unknown, fixture_prices()))
        missing_cash = fixture_input()
        del missing_cash["cash"]
        cases.append(("MISSING_CASH", missing_cash, fixture_prices()))
        conservation = fixture_input()
        conservation["declared_total_value"] = "9999"
        cases.append(("AMOUNT_CONSERVATION_FAILED", conservation, fixture_prices()))
        cases.append(("STALE_PRICE", fixture_input(), fixture_prices(stale=True)))

        for expected_code, portfolio, prices in cases:
            with self.subTest(expected_code=expected_code):
                with self.assertRaises(PortfolioValidationError) as caught:
                    normalize_portfolio(
                        portfolio,
                        securities=fixture_securities(),
                        prices=prices,
                        cutoff="2026-01-02T22:00:00Z",
                        max_price_age=timedelta(days=1),
                    )
                self.assertEqual(caught.exception.code, expected_code)

    def test_ambiguous_identifier_is_not_guessed(self) -> None:
        ambiguous = (
            SecurityRecord("SEC-AAA", ("DUP",), "Technology"),
            SecurityRecord("SEC-BBB", ("DUP",), "Healthcare"),
        )
        portfolio = fixture_input()
        portfolio["positions"] = [{"identifier": "DUP", "quantity": "1"}]
        with self.assertRaises(PortfolioValidationError) as caught:
            normalize_portfolio(
                portfolio,
                securities=ambiguous,
                prices=fixture_prices(),
                cutoff="2026-01-02T22:00:00Z",
                max_price_age=timedelta(days=1),
            )
        self.assertEqual(caught.exception.code, "AMBIGUOUS_SECURITY")


class PortfolioMetricTests(unittest.TestCase):
    def test_golden_metrics(self) -> None:
        snapshot = fixture_snapshot()
        current = calculate_portfolio_metrics(snapshot)
        self.assertEqual(current["cash_weight"], D("0.25"))
        self.assertEqual(current["sector_exposure"]["Technology"], D("0.5"))
        self.assertEqual(current["max_position_weight"], D("0.5"))
        self.assertEqual(current["concentration_hhi"], D("0.3125"))
        self.assertEqual(current["average_daily_value"]["SEC-AAA"], D("100000"))

        target = calculate_portfolio_metrics(
            snapshot,
            target_weights={"SEC-AAA": D("0.4"), "SEC-BBB": D("0.3")},
            cost_bps=D("10"),
        )
        self.assertEqual(target["cash_weight"], D("0.3"))
        self.assertEqual(target["turnover"], D("0.10"))
        self.assertEqual(target["trade_notionals"]["SEC-AAA"], D("1000.0"))
        self.assertEqual(target["trade_notionals"]["SEC-BBB"], D("500.00"))
        self.assertEqual(target["liquidity_participation"]["SEC-AAA"], D("0.01"))
        self.assertEqual(target["simulated_cost"], D("1.500"))


class PolicyBoundaryTests(unittest.TestCase):
    def test_mandate_and_policy_are_versioned_and_objective(self) -> None:
        mandate = Mandate("mandate/1", "USD", ("FIXTURE",))
        self.assertTrue(mandate.long_only)
        policy = fixture_policy()
        self.assertEqual(policy.mandate_version, mandate.version)
        self.assertTrue(policy.rules())
        self.assertTrue(
            all(
                rule.metric in ALLOWED_POLICY_METRICS
                and rule.basis
                in {
                    RuleBasis.ACCOUNTING_IDENTITY,
                    RuleBasis.MATHEMATICAL_DEFINITION,
                    RuleBasis.DATA_QUALITY,
                    RuleBasis.EXPLICIT_MANDATE,
                }
                for rule in policy.rules()
            )
        )

    def test_subjective_investment_rules_are_rejected(self) -> None:
        for subjective_metric in (
            "company_quality",
            "valuation_attractiveness",
            "news_meaning",
            "market_sentiment",
            "buy_signal",
        ):
            with self.subTest(metric=subjective_metric):
                with self.assertRaisesRegex(ValueError, "not an accounting"):
                    validate_rule_metric(subjective_metric)


class RiskEngineTests(unittest.TestCase):
    def test_preflight_and_final_share_policy_and_metric_versions(self) -> None:
        snapshot = fixture_snapshot()
        engine = RiskEngine(fixture_policy())
        preflight = engine.preflight(snapshot)
        final = engine.final_check(
            snapshot,
            (
                TargetWeightRange("SEC-AAA", D("0.45"), D("0.50")),
                TargetWeightRange("SEC-BBB", D("0.25"), D("0.30")),
            ),
        )
        self.assertEqual(preflight.status, RiskStatus.APPROVED)
        self.assertEqual(final.status, RiskStatus.APPROVED)
        self.assertEqual(preflight.policy_version, final.policy_version)
        self.assertEqual(
            preflight.metric_definition_version,
            final.metric_definition_version,
        )
        self.assertEqual(final.metric_definition_version, METRIC_DEFINITION_VERSION)

    def test_position_and_cash_violations_return_revise_with_bounds(self) -> None:
        snapshot = fixture_snapshot()
        report = RiskEngine(fixture_policy()).final_check(
            snapshot,
            (
                TargetWeightRange("SEC-AAA", D("0.60"), D("0.70")),
                TargetWeightRange("SEC-BBB", D("0.20"), D("0.25")),
            ),
        )
        self.assertEqual(report.status, RiskStatus.REVISE_REQUIRED)
        self.assertIn(VetoCode.POSITION_LIMIT, report.veto_codes)
        self.assertIn("SEC-AAA", report.feasible_bounds)
        self.assertLessEqual(
            report.feasible_bounds["SEC-AAA"].maximum,
            fixture_policy().max_position_weight,
        )

        cash_report = RiskEngine(fixture_policy()).final_check(
            snapshot,
            (
                TargetWeightRange("SEC-AAA", D("0.50"), D("0.60")),
                TargetWeightRange("SEC-BBB", D("0.35"), D("0.35")),
            ),
        )
        self.assertEqual(cash_report.status, RiskStatus.REVISE_REQUIRED)
        self.assertIn(VetoCode.CASH_LIMIT, cash_report.veto_codes)

    def test_sector_concentration_violation_is_detected(self) -> None:
        snapshot = fixture_snapshot(same_sector=True)
        policy = fixture_policy(
            max_position_weight=D("0.80"), max_sector_weight=D("0.80")
        )
        report = RiskEngine(policy).final_check(
            snapshot,
            (
                TargetWeightRange("SEC-AAA", D("0.30"), D("0.50")),
                TargetWeightRange("SEC-BBB", D("0.30"), D("0.40")),
            ),
        )
        self.assertEqual(report.status, RiskStatus.REVISE_REQUIRED)
        self.assertIn(VetoCode.SECTOR_LIMIT, report.veto_codes)

    def test_liquidity_violation_can_require_revision_or_rejection(self) -> None:
        snapshot = fixture_snapshot()
        policy = fixture_policy(
            max_position_weight=D("0.90"),
            max_sector_weight=D("0.90"),
            max_adv_participation=D("0.01"),
        )
        revisable = RiskEngine(policy).final_check(
            snapshot,
            (
                TargetWeightRange("SEC-AAA", D("0.55"), D("0.65")),
                TargetWeightRange("SEC-BBB", D("0.20"), D("0.25")),
            ),
        )
        self.assertEqual(revisable.status, RiskStatus.REVISE_REQUIRED)
        self.assertIn(VetoCode.LIQUIDITY_LIMIT, revisable.veto_codes)
        self.assertEqual(revisable.feasible_bounds["SEC-AAA"].maximum, D("0.60"))

        impossible = RiskEngine(policy).final_check(
            snapshot,
            (
                TargetWeightRange("SEC-AAA", D("0.65"), D("0.70")),
                TargetWeightRange("SEC-BBB", D("0.20"), D("0.25")),
            ),
        )
        self.assertEqual(impossible.status, RiskStatus.REJECTED)
        self.assertIn(VetoCode.LIQUIDITY_LIMIT, impossible.veto_codes)

    def test_missing_liquidity_data_rejects_a_changed_target(self) -> None:
        snapshot = fixture_snapshot(missing_liquidity=True)
        report = RiskEngine(fixture_policy()).final_check(
            snapshot,
            (TargetWeightRange("SEC-AAA", D("0.45"), D("0.55")),),
        )
        self.assertEqual(report.status, RiskStatus.REJECTED)
        self.assertIn(VetoCode.MISSING_LIQUIDITY_DATA, report.veto_codes)

    def test_hard_constraint_property_approved_never_contains_a_violation(self) -> None:
        randomizer = random.Random(20260904)
        snapshot = fixture_snapshot()
        policy = fixture_policy(max_adv_participation=D("0.05"))
        engine = RiskEngine(policy)
        for _ in range(250):
            aaa = D(str(round(randomizer.uniform(0, 0.8), 4)))
            bbb = D(str(round(randomizer.uniform(0, 0.8), 4)))
            report = engine.final_check(
                snapshot,
                (
                    TargetWeightRange("SEC-AAA", aaa, aaa),
                    TargetWeightRange("SEC-BBB", bbb, bbb),
                ),
            )
            if report.status is not RiskStatus.APPROVED:
                continue
            self.assertFalse(report.violations)
            self.assertLessEqual(aaa, policy.max_position_weight)
            self.assertLessEqual(bbb, policy.max_position_weight)
            self.assertLessEqual(aaa + bbb, D("1") - policy.min_cash_weight)
            self.assertLessEqual(report.post_trade_metrics["turnover"], policy.max_turnover)
            for participation in report.post_trade_metrics["liquidity_participation"].values():
                self.assertIsNotNone(participation)
                self.assertLessEqual(participation, policy.max_adv_participation)

    def test_extreme_boundaries_and_policy_mismatch_never_approve(self) -> None:
        snapshot = fixture_snapshot()
        mismatch = fixture_policy(mandate_version="mandate/other")
        report = RiskEngine(mismatch).final_check(snapshot, ())
        self.assertEqual(report.status, RiskStatus.REJECTED)
        self.assertIn(VetoCode.POLICY_VERSION_MISMATCH, report.veto_codes)

        leveraged = RiskEngine(fixture_policy()).final_check(
            snapshot,
            (
                TargetWeightRange("SEC-AAA", D("0.8"), D("0.8")),
                TargetWeightRange("SEC-BBB", D("0.4"), D("0.4")),
            ),
        )
        self.assertEqual(leveraged.status, RiskStatus.REJECTED)
        self.assertIn(VetoCode.LEVERAGE, leveraged.veto_codes)


if __name__ == "__main__":
    unittest.main()
