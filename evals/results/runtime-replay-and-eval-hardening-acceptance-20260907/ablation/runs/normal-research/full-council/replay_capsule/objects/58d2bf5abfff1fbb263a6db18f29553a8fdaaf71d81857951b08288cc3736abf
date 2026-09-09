"""Transparent valuation arithmetic with immutable calculation artifacts."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping


def _decimal(value: object, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"invalid decimal input: {name}") from exc
    if not result.is_finite():
        raise ValueError(f"non-finite decimal input: {name}")
    return result


def _artifact_id(method: str, inputs: Mapping[str, object], outputs: Mapping[str, str]) -> str:
    payload = json.dumps(
        {"method": method, "inputs": dict(inputs), "outputs": dict(outputs)},
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return f"calc:{method}:{hashlib.sha256(payload).hexdigest()[:16]}"


@dataclass(frozen=True, slots=True)
class CalculationArtifact:
    artifact_id: str
    method: str
    inputs: Mapping[str, object]
    outputs: Mapping[str, str]
    as_of: str
    assumption_ids: tuple[str, ...]
    evidence_fact_ids: tuple[str, ...]


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
    return CalculationArtifact(
        _artifact_id("present-value", inputs, outputs), "present-value", inputs, outputs,
        as_of, assumption_ids, evidence_fact_ids,
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
    return CalculationArtifact(
        _artifact_id("equity-value-per-share", inputs, outputs), "equity-value-per-share",
        inputs, outputs, as_of, assumption_ids, evidence_fact_ids,
    )
