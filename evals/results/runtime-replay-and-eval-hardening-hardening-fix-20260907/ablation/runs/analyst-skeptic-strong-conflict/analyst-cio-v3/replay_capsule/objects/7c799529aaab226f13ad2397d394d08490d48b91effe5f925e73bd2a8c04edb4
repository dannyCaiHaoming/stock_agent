"""Versioned mandate and objective hard-risk policy contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from typing import Final


class RuleBasis(StrEnum):
    ACCOUNTING_IDENTITY = "accounting_identity"
    MATHEMATICAL_DEFINITION = "mathematical_definition"
    DATA_QUALITY = "data_quality"
    EXPLICIT_MANDATE = "explicit_mandate"


@dataclass(frozen=True, slots=True)
class Mandate:
    version: str
    base_currency: str
    allowed_markets: tuple[str, ...]
    allowed_security_types: tuple[str, ...] = ("COMMON_STOCK",)
    long_only: bool = True
    allow_leverage: bool = False

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("mandate version is required")
        if not self.long_only or self.allow_leverage:
            raise ValueError("MVP mandate must be long-only and unlevered")
        if not self.allowed_markets:
            raise ValueError("at least one allowed market is required")


@dataclass(frozen=True, slots=True)
class PolicyRule:
    code: str
    metric: str
    basis: RuleBasis
    comparator: str
    limit: Decimal | timedelta


ALLOWED_POLICY_METRICS: Final[frozenset[str]] = frozenset(
    {
        "amount_conservation",
        "price_age",
        "position_weight",
        "sector_weight",
        "cash_weight",
        "turnover",
        "adv_participation",
        "long_only",
        "leverage",
    }
)


def validate_rule_metric(metric: str) -> None:
    if metric not in ALLOWED_POLICY_METRICS:
        raise ValueError(
            f"risk policy metric is not an accounting, mathematical, data-quality, "
            f"or explicit mandate constraint: {metric}"
        )


@dataclass(frozen=True, slots=True)
class RiskPolicy:
    version: str
    mandate_version: str
    max_position_weight: Decimal
    max_sector_weight: Decimal
    min_cash_weight: Decimal
    max_turnover: Decimal
    max_adv_participation: Decimal
    max_price_age: timedelta
    simulated_cost_bps: Decimal = Decimal("10")

    def __post_init__(self) -> None:
        if not self.version or not self.mandate_version:
            raise ValueError("policy and mandate versions are required")
        unit_interval = (
            self.max_position_weight,
            self.max_sector_weight,
            self.min_cash_weight,
            self.max_turnover,
            self.max_adv_participation,
        )
        if any(value < Decimal("0") or value > Decimal("1") for value in unit_interval):
            raise ValueError("weight and participation limits must be within [0, 1]")
        if self.max_position_weight > self.max_sector_weight:
            raise ValueError("position limit cannot exceed sector limit")
        if self.max_price_age < timedelta(0):
            raise ValueError("max_price_age cannot be negative")
        if self.simulated_cost_bps < Decimal("0"):
            raise ValueError("simulated_cost_bps cannot be negative")

    def rules(self) -> tuple[PolicyRule, ...]:
        rules = (
            PolicyRule(
                "AMOUNT_CONSERVATION",
                "amount_conservation",
                RuleBasis.ACCOUNTING_IDENTITY,
                "==",
                Decimal("0"),
            ),
            PolicyRule(
                "PRICE_FRESHNESS",
                "price_age",
                RuleBasis.DATA_QUALITY,
                "<=",
                self.max_price_age,
            ),
            PolicyRule(
                "POSITION_LIMIT",
                "position_weight",
                RuleBasis.EXPLICIT_MANDATE,
                "<=",
                self.max_position_weight,
            ),
            PolicyRule(
                "SECTOR_LIMIT",
                "sector_weight",
                RuleBasis.EXPLICIT_MANDATE,
                "<=",
                self.max_sector_weight,
            ),
            PolicyRule(
                "CASH_FLOOR",
                "cash_weight",
                RuleBasis.EXPLICIT_MANDATE,
                ">=",
                self.min_cash_weight,
            ),
            PolicyRule(
                "TURNOVER_LIMIT",
                "turnover",
                RuleBasis.MATHEMATICAL_DEFINITION,
                "<=",
                self.max_turnover,
            ),
            PolicyRule(
                "LIQUIDITY_LIMIT",
                "adv_participation",
                RuleBasis.MATHEMATICAL_DEFINITION,
                "<=",
                self.max_adv_participation,
            ),
            PolicyRule(
                "LONG_ONLY",
                "long_only",
                RuleBasis.EXPLICIT_MANDATE,
                "==",
                Decimal("1"),
            ),
            PolicyRule(
                "NO_LEVERAGE",
                "leverage",
                RuleBasis.EXPLICIT_MANDATE,
                "==",
                Decimal("0"),
            ),
        )
        for rule in rules:
            validate_rule_metric(rule.metric)
        return rules
