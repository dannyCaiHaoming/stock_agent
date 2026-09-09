"""Two-stage deterministic checks using one immutable RiskPolicy."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Iterable, Mapping

from product.mcp.provenance import parse_timestamp

from .metrics import METRIC_DEFINITION_VERSION, calculate_portfolio_metrics
from .policy import RiskPolicy
from .portfolio import ONE, ZERO, PortfolioSnapshot


class RiskStatus(StrEnum):
    APPROVED = "APPROVED"
    REVISE_REQUIRED = "REVISE_REQUIRED"
    REJECTED = "REJECTED"


class VetoCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    POLICY_VERSION_MISMATCH = "POLICY_VERSION_MISMATCH"
    STALE_PRICE = "STALE_PRICE"
    POSITION_LIMIT = "POSITION_LIMIT"
    CASH_LIMIT = "CASH_LIMIT"
    SECTOR_LIMIT = "SECTOR_LIMIT"
    TURNOVER_LIMIT = "TURNOVER_LIMIT"
    LIQUIDITY_LIMIT = "LIQUIDITY_LIMIT"
    MISSING_LIQUIDITY_DATA = "MISSING_LIQUIDITY_DATA"
    LONG_ONLY = "LONG_ONLY"
    LEVERAGE = "LEVERAGE"


@dataclass(frozen=True, slots=True)
class TargetWeightRange:
    security_id: str
    minimum: Decimal
    maximum: Decimal

    def __post_init__(self) -> None:
        if not self.minimum.is_finite() or not self.maximum.is_finite():
            raise ValueError("target weights must be finite")
        if self.minimum > self.maximum:
            raise ValueError("target minimum cannot exceed maximum")


@dataclass(frozen=True, slots=True)
class WeightBounds:
    minimum: Decimal
    maximum: Decimal


@dataclass(frozen=True, slots=True)
class RiskViolation:
    code: VetoCode
    policy_rule: str
    metric: str
    observed: Decimal | str
    limit: Decimal | str
    remediable_within_range: bool


@dataclass(frozen=True, slots=True)
class RiskCheckReport:
    stage: str
    status: RiskStatus
    policy_version: str
    mandate_version: str
    metric_definition_version: str
    pre_trade_metrics: Mapping[str, object]
    post_trade_metrics: Mapping[str, object] | None
    feasible_bounds: Mapping[str, WeightBounds]
    violations: tuple[RiskViolation, ...]
    veto_codes: tuple[VetoCode, ...]


class RiskEngine:
    """Validates objective constraints; it never creates a thesis or selects assets."""

    def __init__(self, policy: RiskPolicy) -> None:
        self.policy = policy
        self.policy.rules()

    def _version_violation(self, snapshot: PortfolioSnapshot) -> RiskViolation | None:
        if snapshot.mandate_version == self.policy.mandate_version:
            return None
        return RiskViolation(
            VetoCode.POLICY_VERSION_MISMATCH,
            "POLICY_MANDATE_VERSION",
            "mandate_version",
            snapshot.mandate_version,
            self.policy.mandate_version,
            False,
        )

    def _liquidity_bounds(self, snapshot: PortfolioSnapshot) -> dict[str, WeightBounds]:
        bounds: dict[str, WeightBounds] = {}
        for position in snapshot.positions:
            if position.average_daily_value is None or position.average_daily_value <= ZERO:
                bounds[position.security_id] = WeightBounds(position.weight, position.weight)
                continue
            delta = (
                position.average_daily_value
                * self.policy.max_adv_participation
                / snapshot.total_value
            )
            bounds[position.security_id] = WeightBounds(
                max(ZERO, position.weight - delta),
                min(self.policy.max_position_weight, position.weight + delta),
            )
        return bounds

    def _report(
        self,
        *,
        stage: str,
        snapshot: PortfolioSnapshot,
        pre_metrics: Mapping[str, object],
        post_metrics: Mapping[str, object] | None,
        bounds: Mapping[str, WeightBounds],
        violations: list[RiskViolation],
    ) -> RiskCheckReport:
        status = RiskStatus.APPROVED
        if violations:
            status = (
                RiskStatus.REVISE_REQUIRED
                if all(item.remediable_within_range for item in violations)
                else RiskStatus.REJECTED
            )
        return RiskCheckReport(
            stage=stage,
            status=status,
            policy_version=self.policy.version,
            mandate_version=self.policy.mandate_version,
            metric_definition_version=METRIC_DEFINITION_VERSION,
            pre_trade_metrics=pre_metrics,
            post_trade_metrics=post_metrics,
            feasible_bounds=dict(sorted(bounds.items())),
            violations=tuple(violations),
            veto_codes=tuple(dict.fromkeys(item.code for item in violations)),
        )

    def preflight(self, snapshot: PortfolioSnapshot) -> RiskCheckReport:
        metrics = calculate_portfolio_metrics(snapshot)
        bounds = self._liquidity_bounds(snapshot)
        violations: list[RiskViolation] = []
        mismatch = self._version_violation(snapshot)
        if mismatch:
            violations.append(mismatch)
        cutoff = parse_timestamp(snapshot.as_of)
        for position in snapshot.positions:
            age = cutoff - parse_timestamp(position.price_as_of)
            if age > self.policy.max_price_age:
                violations.append(
                    RiskViolation(
                        VetoCode.STALE_PRICE,
                        "PRICE_FRESHNESS",
                        f"price_age:{position.security_id}",
                        str(age),
                        str(self.policy.max_price_age),
                        False,
                    )
                )
            if position.weight > self.policy.max_position_weight:
                violations.append(
                    RiskViolation(
                        VetoCode.POSITION_LIMIT,
                        "POSITION_LIMIT",
                        f"position_weight:{position.security_id}",
                        position.weight,
                        self.policy.max_position_weight,
                        True,
                    )
                )
        for sector, weight in metrics["sector_exposure"].items():
            if weight > self.policy.max_sector_weight:
                violations.append(
                    RiskViolation(
                        VetoCode.SECTOR_LIMIT,
                        "SECTOR_LIMIT",
                        f"sector_weight:{sector}",
                        weight,
                        self.policy.max_sector_weight,
                        True,
                    )
                )
        if snapshot.cash_weight < self.policy.min_cash_weight:
            violations.append(
                RiskViolation(
                    VetoCode.CASH_LIMIT,
                    "CASH_FLOOR",
                    "cash_weight",
                    snapshot.cash_weight,
                    self.policy.min_cash_weight,
                    True,
                )
            )
        return self._report(
            stage="PREFLIGHT",
            snapshot=snapshot,
            pre_metrics=metrics,
            post_metrics=None,
            bounds=bounds,
            violations=violations,
        )

    def final_check(
        self,
        snapshot: PortfolioSnapshot,
        targets: Iterable[TargetWeightRange],
    ) -> RiskCheckReport:
        pre_metrics = calculate_portfolio_metrics(snapshot)
        bounds = self._liquidity_bounds(snapshot)
        violations: list[RiskViolation] = []
        mismatch = self._version_violation(snapshot)
        if mismatch:
            violations.append(mismatch)

        ranges: dict[str, TargetWeightRange] = {}
        for target in targets:
            if target.security_id in ranges:
                violations.append(
                    RiskViolation(
                        VetoCode.INVALID_INPUT,
                        "UNIQUE_TARGETS",
                        "duplicate_target",
                        target.security_id,
                        "unique security_id",
                        False,
                    )
                )
                continue
            ranges[target.security_id] = target

        known = {position.security_id: position for position in snapshot.positions}
        for security_id in ranges.keys() - known.keys():
            violations.append(
                RiskViolation(
                    VetoCode.INVALID_INPUT,
                    "KNOWN_SECURITY",
                    "security_id",
                    security_id,
                    "normalized portfolio security",
                    False,
                )
            )
        for security_id, position in known.items():
            ranges.setdefault(
                security_id,
                TargetWeightRange(security_id, position.weight, position.weight),
            )

        for security_id, target in ranges.items():
            if security_id not in known:
                continue
            if target.minimum < ZERO or target.maximum > ONE:
                violations.append(
                    RiskViolation(
                        VetoCode.LONG_ONLY,
                        "LONG_ONLY",
                        f"target_range:{security_id}",
                        f"{target.minimum}:{target.maximum}",
                        "0:1",
                        False,
                    )
                )
                continue
            feasible = bounds[security_id]
            position_ceiling = self.policy.max_position_weight
            intersection_min = max(target.minimum, feasible.minimum, ZERO)
            intersection_max = min(target.maximum, feasible.maximum, position_ceiling)
            if target.maximum > position_ceiling:
                violations.append(
                    RiskViolation(
                        VetoCode.POSITION_LIMIT,
                        "POSITION_LIMIT",
                        f"target_max:{security_id}",
                        target.maximum,
                        position_ceiling,
                        intersection_min <= intersection_max,
                    )
                )
            position = known[security_id]
            if position.average_daily_value is None or position.average_daily_value <= ZERO:
                if target.minimum != position.weight or target.maximum != position.weight:
                    violations.append(
                        RiskViolation(
                            VetoCode.MISSING_LIQUIDITY_DATA,
                            "LIQUIDITY_LIMIT",
                            f"average_daily_value:{security_id}",
                            "missing",
                            "positive value",
                            False,
                        )
                    )
            elif target.minimum < feasible.minimum or target.maximum > feasible.maximum:
                violations.append(
                    RiskViolation(
                        VetoCode.LIQUIDITY_LIMIT,
                        "LIQUIDITY_LIMIT",
                        f"target_range:{security_id}",
                        f"{target.minimum}:{target.maximum}",
                        f"{feasible.minimum}:{feasible.maximum}",
                        intersection_min <= intersection_max,
                    )
                )

        valid_ranges = {
            key: value for key, value in ranges.items() if key in known
        }
        lower_invested = sum((target.minimum for target in valid_ranges.values()), ZERO)
        upper_invested = sum((target.maximum for target in valid_ranges.values()), ZERO)
        max_invested = ONE - self.policy.min_cash_weight
        if lower_invested > ONE:
            violations.append(
                RiskViolation(
                    VetoCode.LEVERAGE,
                    "NO_LEVERAGE",
                    "minimum_invested_weight",
                    lower_invested,
                    ONE,
                    False,
                )
            )
        elif upper_invested > max_invested:
            violations.append(
                RiskViolation(
                    VetoCode.CASH_LIMIT,
                    "CASH_FLOOR",
                    "maximum_invested_weight",
                    upper_invested,
                    max_invested,
                    lower_invested <= max_invested,
                )
            )

        by_sector: dict[str, list[TargetWeightRange]] = {}
        for security_id, target in valid_ranges.items():
            by_sector.setdefault(known[security_id].industry, []).append(target)
        for sector, sector_targets in by_sector.items():
            lower = sum((target.minimum for target in sector_targets), ZERO)
            upper = sum((target.maximum for target in sector_targets), ZERO)
            if upper > self.policy.max_sector_weight:
                violations.append(
                    RiskViolation(
                        VetoCode.SECTOR_LIMIT,
                        "SECTOR_LIMIT",
                        f"sector_range:{sector}",
                        f"{lower}:{upper}",
                        self.policy.max_sector_weight,
                        lower <= self.policy.max_sector_weight,
                    )
                )

        midpoint_weights = {
            security_id: (target.minimum + target.maximum) / Decimal("2")
            for security_id, target in valid_ranges.items()
        }
        minimum_change_weights = {
            security_id: min(max(position.weight, valid_ranges[security_id].minimum), valid_ranges[security_id].maximum)
            for security_id, position in known.items()
        }
        minimum_metrics = calculate_portfolio_metrics(
            snapshot,
            target_weights=minimum_change_weights,
            cost_bps=self.policy.simulated_cost_bps,
        )
        post_metrics = calculate_portfolio_metrics(
            snapshot,
            target_weights=midpoint_weights,
            cost_bps=self.policy.simulated_cost_bps,
        )
        if post_metrics["turnover"] > self.policy.max_turnover:
            violations.append(
                RiskViolation(
                    VetoCode.TURNOVER_LIMIT,
                    "TURNOVER_LIMIT",
                    "turnover",
                    post_metrics["turnover"],
                    self.policy.max_turnover,
                    minimum_metrics["turnover"] <= self.policy.max_turnover,
                )
            )

        return self._report(
            stage="FINAL",
            snapshot=snapshot,
            pre_metrics=pre_metrics,
            post_metrics=post_metrics,
            bounds=bounds,
            violations=violations,
        )
