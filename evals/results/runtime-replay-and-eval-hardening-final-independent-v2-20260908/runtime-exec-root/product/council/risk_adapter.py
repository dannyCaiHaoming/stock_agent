"""Protocol adapter between dictionary council artifacts and the Risk Kernel."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping

from product.deterministic.portfolio import PortfolioSnapshot
from product.deterministic.risk import RiskEngine, TargetWeightRange


def _json_primitive(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value)
    if is_dataclass(value):
        return _json_primitive(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_primitive(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_primitive(item) for item in value]
    return value


class DeterministicRiskAdapter:
    """Expose the real deterministic engine through the Council mapping protocol.

    The adapter translates structure and numeric types only. It never creates,
    ranks, or alters an investment thesis or security selection.
    """

    def __init__(self, snapshot: PortfolioSnapshot, engine: RiskEngine) -> None:
        self.snapshot = snapshot
        self.engine = engine

    def _validate_portfolio_identity(self, portfolio: Mapping[str, Any]) -> None:
        supplied = portfolio.get("snapshot_id")
        if supplied is not None and supplied != self.snapshot.snapshot_id:
            raise ValueError("council portfolio does not match the normalized risk snapshot")

    @staticmethod
    def _targets(draft: Mapping[str, Any]) -> tuple[TargetWeightRange, ...]:
        targets: list[TargetWeightRange] = []
        decisions = draft.get("decisions", ())
        if not isinstance(decisions, list):
            raise ValueError("council draft decisions must be a list")
        for decision in decisions:
            if not isinstance(decision, Mapping):
                raise ValueError("each council decision must be an object")
            if decision.get("action") == "NO_TRADE":
                continue
            target = decision.get("target_weight_range")
            if not isinstance(target, list) or len(target) != 2:
                raise ValueError("actionable council decisions require a two-value target range")
            security_id = decision.get("security_id")
            if not isinstance(security_id, str) or not security_id:
                raise ValueError("actionable council decisions require security_id")
            targets.append(
                TargetWeightRange(
                    security_id=security_id,
                    minimum=Decimal(str(target[0])),
                    maximum=Decimal(str(target[1])),
                )
            )
        return tuple(targets)

    def preflight(self, portfolio: Mapping[str, Any]) -> Mapping[str, Any]:
        self._validate_portfolio_identity(portfolio)
        return _json_primitive(self.engine.preflight(self.snapshot))

    def final_check(
        self, portfolio: Mapping[str, Any], draft: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        self._validate_portfolio_identity(portfolio)
        return _json_primitive(self.engine.final_check(self.snapshot, self._targets(draft)))
