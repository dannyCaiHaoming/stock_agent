"""Translate validated fixture portfolio data into the deterministic Risk Engine."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import timedelta
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from product.deterministic.policy import RiskPolicy
from product.deterministic.portfolio import NormalizedPosition, PortfolioSnapshot
from product.deterministic.risk import RiskEngine, TargetWeightRange

from .hashing import canonical_hash


RISK_RESULT_VERSION = "native-risk-result/2.0.0"


def _primitive(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value)
    if is_dataclass(value):
        return _primitive(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_primitive(item) for item in value]
    return value


def build_risk_snapshot(fixture: Mapping[str, Any], *, run_id: str) -> PortfolioSnapshot:
    portfolio = fixture["portfolio"]
    total = Decimal(str(portfolio["cash"])) + sum(
        Decimal(str(item["quantity"])) * Decimal(str(item["price"]))
        for item in portfolio["positions"]
    )
    price_by_security = {
        fact["security_id"]: fact
        for fact in fixture["evidence"]
        if fact["semantic_field"] == "close_price"
        and fact["as_of"] <= fixture["decision_cutoff"]
        and fact["retrieved_at"] <= fixture["decision_cutoff"]
    }
    positions = []
    for item in portfolio["positions"]:
        security_id = item["security_id"]
        market_value = Decimal(str(item["quantity"])) * Decimal(str(item["price"]))
        price_fact = price_by_security.get(security_id)
        price_as_of = price_fact["as_of"] if price_fact else fixture["decision_cutoff"]
        price_source_id = price_fact["source_id"] if price_fact else "portfolio-fixture-input"
        positions.append(
            NormalizedPosition(
                security_id=security_id,
                quantity=Decimal(str(item["quantity"])),
                price=Decimal(str(item["price"])),
                price_as_of=price_as_of,
                price_source_id=price_source_id,
                market_value=market_value,
                weight=market_value / total,
                industry=str(item.get("industry", "Unclassified")),
                average_daily_value=(
                    Decimal(str(item["average_daily_value"]))
                    if item.get("average_daily_value") is not None
                    else None
                ),
            )
        )
    return PortfolioSnapshot(
        snapshot_id=f"snapshot-{run_id}",
        as_of=fixture["decision_cutoff"],
        base_currency=portfolio["base_currency"],
        benchmark=None,
        mandate_version="mandate/fixture/2.0.0",
        cash=Decimal(str(portfolio["cash"])),
        total_value=total,
        positions=tuple(positions),
    )


def build_risk_policy(fixture: Mapping[str, Any]) -> RiskPolicy:
    mandate = fixture["portfolio"]["mandate"]
    return RiskPolicy(
        version="risk/reference/1.0.0",
        mandate_version="mandate/fixture/2.0.0",
        max_position_weight=Decimal(str(mandate["max_position_weight"])),
        max_sector_weight=Decimal(str(mandate["max_position_weight"])),
        min_cash_weight=Decimal(str(mandate["minimum_cash_weight"])),
        max_turnover=Decimal("0.50"),
        max_adv_participation=Decimal("0.10"),
        max_price_age=timedelta(days=7),
        simulated_cost_bps=Decimal("10"),
    )


def check_cio_draft(
    fixture: Mapping[str, Any], draft: Mapping[str, Any], *, run_id: str
) -> dict[str, Any]:
    snapshot = build_risk_snapshot(fixture, run_id=run_id)
    policy = build_risk_policy(fixture)
    targets: tuple[TargetWeightRange, ...] = ()
    if draft["action"] != "NO_TRADE":
        target = draft["target_weight_range"]
        targets = (
            TargetWeightRange(
                security_id=draft["security_id"],
                minimum=Decimal(str(target[0])),
                maximum=Decimal(str(target[1])),
            ),
        )
    report = RiskEngine(policy).final_check(snapshot, targets)
    primitive_report = _primitive(report)
    final_action = "NO_TRADE" if primitive_report["status"] == "REJECTED" else draft["action"]
    return {
        "schema_version": RISK_RESULT_VERSION,
        "run_id": run_id,
        "producer": "deterministic_risk_engine",
        "policy_version": policy.version,
        "draft_hash": canonical_hash(draft),
        "original_action": draft["action"],
        "modifications": [],
        "check": primitive_report,
        "final_action": final_action,
        "veto_reason": "RISK_VETO" if primitive_report["status"] == "REJECTED" else None,
    }
