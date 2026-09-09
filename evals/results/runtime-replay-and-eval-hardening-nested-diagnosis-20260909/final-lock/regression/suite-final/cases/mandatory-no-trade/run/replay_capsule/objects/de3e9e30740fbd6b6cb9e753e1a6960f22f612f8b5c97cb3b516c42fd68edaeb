"""Versioned portfolio metric definitions used by both risk stages."""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping

from .portfolio import ONE, ZERO, PortfolioSnapshot


METRIC_DEFINITION_VERSION = "portfolio-metrics/1.0.0"


def _weights(snapshot: PortfolioSnapshot) -> dict[str, Decimal]:
    return {position.security_id: position.weight for position in snapshot.positions}


def calculate_turnover(
    current_weights: Mapping[str, Decimal],
    current_cash_weight: Decimal,
    target_weights: Mapping[str, Decimal],
) -> Decimal:
    securities = set(current_weights) | set(target_weights)
    asset_change = sum(
        (abs(target_weights.get(key, ZERO) - current_weights.get(key, ZERO)) for key in securities),
        ZERO,
    )
    target_cash = ONE - sum(target_weights.values(), ZERO)
    return (asset_change + abs(target_cash - current_cash_weight)) / Decimal("2")


def calculate_portfolio_metrics(
    snapshot: PortfolioSnapshot,
    *,
    target_weights: Mapping[str, Decimal] | None = None,
    cost_bps: Decimal = Decimal("10"),
) -> dict[str, object]:
    current = _weights(snapshot)
    weights = dict(target_weights) if target_weights is not None else current
    industries = {position.security_id: position.industry for position in snapshot.positions}
    sector_exposure: dict[str, Decimal] = {}
    for security_id, weight in weights.items():
        sector = industries.get(security_id, "UNKNOWN")
        sector_exposure[sector] = sector_exposure.get(sector, ZERO) + weight

    cash_weight = ONE - sum(weights.values(), ZERO)
    result: dict[str, object] = {
        "definition_version": METRIC_DEFINITION_VERSION,
        "total_value": snapshot.total_value,
        "cash": cash_weight * snapshot.total_value,
        "cash_weight": cash_weight,
        "position_weights": dict(sorted(weights.items())),
        "sector_exposure": dict(sorted(sector_exposure.items())),
        "max_position_weight": max(weights.values(), default=ZERO),
        "concentration_hhi": sum((weight * weight for weight in weights.values()), ZERO),
        "average_daily_value": {
            position.security_id: position.average_daily_value
            for position in snapshot.positions
        },
    }

    if target_weights is not None:
        turnover = calculate_turnover(current, snapshot.cash_weight, weights)
        trade_notionals: dict[str, Decimal] = {}
        liquidity_participation: dict[str, Decimal | None] = {}
        total_traded = ZERO
        for position in snapshot.positions:
            delta = abs(weights.get(position.security_id, ZERO) - position.weight)
            notional = delta * snapshot.total_value
            trade_notionals[position.security_id] = notional
            total_traded += notional
            liquidity_participation[position.security_id] = (
                notional / position.average_daily_value
                if position.average_daily_value not in (None, ZERO)
                else None
            )
        result.update(
            turnover=turnover,
            trade_notionals=dict(sorted(trade_notionals.items())),
            liquidity_participation=dict(sorted(liquidity_participation.items())),
            simulated_cost=total_traded * cost_bps / Decimal("10000"),
            cost_bps=cost_bps,
        )
    return result
