"""Transparent valuation arithmetic with immutable calculation artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Mapping

try:
    from product.mcp.provenance import parse_timestamp
    from product.runtime.monetary import (
        convert_monetary_value,
        require_monetary_equivalence,
    )
except ModuleNotFoundError as exc:
    if exc.name != "product":
        raise
    from mcp.provenance import parse_timestamp
    from runtime.monetary import convert_monetary_value, require_monetary_equivalence


def _decimal(value: object, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid decimal input: {name}") from exc
    if not result.is_finite():
        raise ValueError(f"non-finite decimal input: {name}")
    return result


CALCULATION_SCHEMA_VERSION = "research-calculation/1.0.0"
def _artifact_digest(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        dict(payload),
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class CalculationArtifact:
    schema_version: str
    artifact_id: str
    artifact_hash: str
    method: str
    formula: str
    inputs: Mapping[str, object]
    outputs: Mapping[str, str]
    periods: Mapping[str, str]
    units: Mapping[str, str]
    as_of: str
    assumption_ids: tuple[str, ...]
    evidence_fact_ids: tuple[str, ...]


def _artifact(
    *, method: str, formula: str, inputs: Mapping[str, object], outputs: Mapping[str, str],
    periods: Mapping[str, str], units: Mapping[str, str], as_of: str,
    assumption_ids: tuple[str, ...], evidence_fact_ids: tuple[str, ...],
) -> CalculationArtifact:
    if "T" in as_of:
        parse_timestamp(as_of)
    else:
        date.fromisoformat(as_of)
    if len(evidence_fact_ids) != len(set(evidence_fact_ids)) or len(assumption_ids) != len(set(assumption_ids)):
        raise ValueError("calculation lineage identifiers must be unique")
    if not evidence_fact_ids and not assumption_ids:
        raise ValueError("calculation requires Evidence or explicit assumptions")
    payload = {
        "schema_version": CALCULATION_SCHEMA_VERSION,
        "method": method,
        "formula": formula,
        "inputs": dict(inputs),
        "outputs": dict(outputs),
        "periods": dict(periods),
        "units": dict(units),
        "as_of": as_of,
        "assumption_ids": list(assumption_ids),
        "evidence_fact_ids": list(evidence_fact_ids),
    }
    digest = _artifact_digest(payload)
    return CalculationArtifact(
        schema_version=CALCULATION_SCHEMA_VERSION,
        artifact_id=f"calc:{method}:{digest[:16]}",
        artifact_hash=digest,
        method=method,
        formula=formula,
        inputs=dict(inputs),
        outputs=dict(outputs),
        periods=dict(periods),
        units=dict(units),
        as_of=as_of,
        assumption_ids=assumption_ids,
        evidence_fact_ids=evidence_fact_ids,
    )


def convert_monetary_scale(
    *, value: object, source_scale: str, target_scale: str, currency: str,
    as_of: str, evidence_fact_ids: tuple[str, ...],
) -> CalculationArtifact:
    """Convert a disclosed monetary magnitude without adding interpretation."""

    amount = _decimal(value, "value")
    if not isinstance(currency, str) or not currency.strip():
        raise ValueError("currency is required")
    output = convert_monetary_value(
        value=amount, source_scale=source_scale, target_scale=target_scale
    )
    return _artifact(
        method="monetary-scale-conversion",
        formula="value * source_scale_factor / target_scale_factor",
        inputs={
            "value": str(amount),
            "source_scale": source_scale,
            "target_scale": target_scale,
            "currency": currency,
        },
        outputs={"converted_value": output},
        periods={"value": as_of},
        units={
            "value": f"{currency} {source_scale}",
            "converted_value": f"{currency} {target_scale}",
        },
        as_of=as_of,
        assumption_ids=(),
        evidence_fact_ids=evidence_fact_ids,
    )


def validate_monetary_scale_equivalence(
    *, source_value: object, source_scale: str,
    reported_value: object, reported_scale: str,
) -> None:
    """Reject a translated monetary amount whose magnitude is not equivalent."""

    require_monetary_equivalence(
        source_value=source_value,
        source_scale=source_scale,
        reported_value=reported_value,
        reported_scale=reported_scale,
    )


def present_value(
    *, cash_flow: object, discount_rate: object, periods: int, as_of: str,
    assumption_ids: tuple[str, ...], evidence_fact_ids: tuple[str, ...],
) -> CalculationArtifact:
    amount = _decimal(cash_flow, "cash_flow")
    rate = _decimal(discount_rate, "discount_rate")
    if periods < 0 or rate <= Decimal("-1"):
        raise ValueError("periods and discount_rate are outside the calculable domain")
    inputs = {"cash_flow": str(amount), "discount_rate": str(rate), "periods": periods}
    outputs = {"present_value": str(amount / ((Decimal("1") + rate) ** periods))}
    return _artifact(
        method="present-value", formula="cash_flow / (1 + discount_rate) ** periods",
        inputs=inputs, outputs=outputs, periods={"cash_flow": as_of},
        units={"cash_flow": "currency", "present_value": "currency"}, as_of=as_of,
        assumption_ids=assumption_ids, evidence_fact_ids=evidence_fact_ids,
    )


def equity_value_per_share(
    *, enterprise_value: object, cash: object, debt: object, shares: object,
    as_of: str, assumption_ids: tuple[str, ...], evidence_fact_ids: tuple[str, ...],
) -> CalculationArtifact:
    enterprise = _decimal(enterprise_value, "enterprise_value")
    cash_value = _decimal(cash, "cash")
    debt_value = _decimal(debt, "debt")
    share_count = _decimal(shares, "shares")
    if share_count <= 0:
        raise ValueError("shares must be positive")
    equity = enterprise + cash_value - debt_value
    inputs = {"enterprise_value": str(enterprise), "cash": str(cash_value), "debt": str(debt_value), "shares": str(share_count)}
    outputs = {"equity_value": str(equity), "value_per_share": str(equity / share_count)}
    return _artifact(
        method="equity-value-per-share",
        formula="(enterprise_value + cash - debt) / shares", inputs=inputs, outputs=outputs,
        periods={"enterprise_value": as_of, "cash": as_of, "debt": as_of, "shares": as_of},
        units={"enterprise_value": "currency", "cash": "currency", "debt": "currency", "shares": "shares", "equity_value": "currency", "value_per_share": "currency/share"},
        as_of=as_of, assumption_ids=assumption_ids, evidence_fact_ids=evidence_fact_ids,
    )


def comparable_period_change(
    *, earlier_value: object, later_value: object, earlier_period: str, later_period: str,
    unit: str, as_of: str, assumption_ids: tuple[str, ...],
    evidence_fact_ids: tuple[str, ...],
) -> CalculationArtifact:
    """Calculate an auditable absolute and percentage change for comparable periods."""

    earlier = _decimal(earlier_value, "earlier_value")
    later = _decimal(later_value, "later_value")
    if not earlier_period or not later_period or earlier_period == later_period:
        raise ValueError("comparable periods must be distinct and explicit")
    if not unit:
        raise ValueError("calculation unit is required")
    if earlier == 0:
        raise ValueError("percent change is undefined for a zero earlier value")
    inputs = {"earlier_value": str(earlier), "later_value": str(later)}
    outputs = {
        "absolute_change": str(later - earlier),
        "percent_change": str((later - earlier) / abs(earlier)),
    }
    return _artifact(
        method="comparable-period-change",
        formula="absolute = later - earlier; percent = (later - earlier) / abs(earlier)",
        inputs=inputs, outputs=outputs,
        periods={"earlier_value": earlier_period, "later_value": later_period},
        units={"earlier_value": unit, "later_value": unit, "absolute_change": unit, "percent_change": "ratio"},
        as_of=as_of, assumption_ids=assumption_ids, evidence_fact_ids=evidence_fact_ids,
    )


def financial_ratio(
    *, numerator: object, denominator: object, numerator_period: str, denominator_period: str,
    numerator_unit: str, denominator_unit: str, as_of: str,
    assumption_ids: tuple[str, ...], evidence_fact_ids: tuple[str, ...],
) -> CalculationArtifact:
    """Calculate a ratio only when its periods and units are explicitly compatible."""

    top = _decimal(numerator, "numerator")
    bottom = _decimal(denominator, "denominator")
    if bottom == 0:
        raise ValueError("ratio denominator cannot be zero")
    if numerator_period != denominator_period:
        raise ValueError("ratio periods must be comparable")
    if numerator_unit != denominator_unit:
        raise ValueError("ratio units must match")
    inputs = {"numerator": str(top), "denominator": str(bottom)}
    outputs = {"ratio": str(top / bottom)}
    return _artifact(
        method="financial-ratio", formula="numerator / denominator", inputs=inputs,
        outputs=outputs, periods={"numerator": numerator_period, "denominator": denominator_period},
        units={"numerator": numerator_unit, "denominator": denominator_unit, "ratio": "ratio"},
        as_of=as_of, assumption_ids=assumption_ids, evidence_fact_ids=evidence_fact_ids,
    )


def operating_scenario_value_per_share(
    *, revenue: object, operating_margin: object, valuation_multiple: object,
    net_cash: object, shares: object, period: str, currency: str, as_of: str,
    assumption_ids: tuple[str, ...], evidence_fact_ids: tuple[str, ...],
) -> CalculationArtifact:
    """Calculate one explicit operating-profit multiple scenario without judging it."""

    revenue_value = _decimal(revenue, "revenue")
    margin = _decimal(operating_margin, "operating_margin")
    multiple = _decimal(valuation_multiple, "valuation_multiple")
    net_cash_value = _decimal(net_cash, "net_cash")
    share_count = _decimal(shares, "shares")
    if not period or not currency:
        raise ValueError("scenario period and currency are required")
    if margin < -1 or margin > 1 or multiple < 0 or share_count <= 0:
        raise ValueError("scenario inputs are outside the calculable domain")
    operating_profit = revenue_value * margin
    enterprise_value = operating_profit * multiple
    equity_value = enterprise_value + net_cash_value
    inputs = {
        "revenue": str(revenue_value), "operating_margin": str(margin),
        "valuation_multiple": str(multiple), "net_cash": str(net_cash_value),
        "shares": str(share_count),
    }
    outputs = {
        "operating_profit": str(operating_profit), "enterprise_value": str(enterprise_value),
        "equity_value": str(equity_value), "value_per_share": str(equity_value / share_count),
    }
    return _artifact(
        method="operating-scenario-value-per-share",
        formula="((revenue * operating_margin) * valuation_multiple + net_cash) / shares",
        inputs=inputs, outputs=outputs,
        periods={"revenue": period, "net_cash": as_of, "shares": as_of},
        units={
            "revenue": currency, "operating_margin": "ratio", "valuation_multiple": "multiple",
            "net_cash": currency, "shares": "shares", "operating_profit": currency,
            "enterprise_value": currency, "equity_value": currency,
            "value_per_share": f"{currency}/share",
        },
        as_of=as_of, assumption_ids=assumption_ids, evidence_fact_ids=evidence_fact_ids,
    )


def free_cash_flow_bridge(
    *, operating_cash_flow: object, capital_expenditure: object, period: str,
    currency: str, as_of: str, evidence_fact_ids: tuple[str, ...],
) -> CalculationArtifact:
    """用披露原值计算 OCF - capex；不把该口径冒充公司自定义 FCF。"""

    operating = _decimal(operating_cash_flow, "operating_cash_flow")
    capex = _decimal(capital_expenditure, "capital_expenditure")
    if not period or not currency or capex < 0:
        raise ValueError("free cash flow inputs require period, currency and nonnegative capex")
    return _artifact(
        method="free-cash-flow-bridge",
        formula="operating_cash_flow - capital_expenditure",
        inputs={"operating_cash_flow": str(operating), "capital_expenditure": str(capex)},
        outputs={"free_cash_flow_bridge": str(operating - capex)},
        periods={"operating_cash_flow": period, "capital_expenditure": period},
        units={"operating_cash_flow": currency, "capital_expenditure": currency,
               "free_cash_flow_bridge": currency},
        as_of=as_of, assumption_ids=(), evidence_fact_ids=evidence_fact_ids,
    )


def net_debt_bridge(
    *, debt: object, cash: object, period: str, currency: str, as_of: str,
    evidence_fact_ids: tuple[str, ...],
) -> CalculationArtifact:
    """计算披露债务减现金，不推断现金受限或流动性充足性。"""

    debt_value = _decimal(debt, "debt")
    cash_value = _decimal(cash, "cash")
    if not period or not currency or debt_value < 0 or cash_value < 0:
        raise ValueError("net debt inputs require period, currency and nonnegative values")
    return _artifact(
        method="net-debt-bridge", formula="debt - cash",
        inputs={"debt": str(debt_value), "cash": str(cash_value)},
        outputs={"net_debt": str(debt_value - cash_value)},
        periods={"debt": period, "cash": period},
        units={"debt": currency, "cash": currency, "net_debt": currency},
        as_of=as_of, assumption_ids=(), evidence_fact_ids=evidence_fact_ids,
    )


def share_count_change(
    *, earlier_shares: object, later_shares: object, earlier_period: str,
    later_period: str, as_of: str, evidence_fact_ids: tuple[str, ...],
) -> CalculationArtifact:
    """计算可比稀释股数变化；经济原因仍由研究 Agent 判断。"""

    earlier = _decimal(earlier_shares, "earlier_shares")
    later = _decimal(later_shares, "later_shares")
    if earlier <= 0 or later <= 0 or not earlier_period or not later_period or earlier_period == later_period:
        raise ValueError("share count periods and positive values are required")
    return _artifact(
        method="share-count-change",
        formula="(later_shares - earlier_shares) / earlier_shares",
        inputs={"earlier_shares": str(earlier), "later_shares": str(later)},
        outputs={"absolute_change": str(later - earlier), "percent_change": str((later - earlier) / earlier)},
        periods={"earlier_shares": earlier_period, "later_shares": later_period},
        units={"earlier_shares": "shares", "later_shares": "shares",
               "absolute_change": "shares", "percent_change": "ratio"},
        as_of=as_of, assumption_ids=(), evidence_fact_ids=evidence_fact_ids,
    )
