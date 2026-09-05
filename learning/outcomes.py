"""Post-decision, multi-horizon market outcome observations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from math import isfinite
from typing import ClassVar

from product.contracts.base import (
    ContractValidationError,
    JsonContract,
    require_identifier,
    require_iso_datetime,
    require_text,
)


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class ThesisOutcome(str, Enum):
    REALIZED = "REALIZED"
    NOT_REALIZED = "NOT_REALIZED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class MarketOutcome(JsonContract):
    schema_name: ClassVar[str] = "market-outcome"

    outcome_id: str
    run_id: str
    decision_artifact_id: str
    benchmark_id: str
    horizon: str
    decision_at: str
    observed_at: str
    portfolio_return: float
    benchmark_return: float
    max_drawdown: float
    gross_exposure: float
    turnover: float
    simulated_cost: float
    thesis_outcome: ThesisOutcome
    research_input_eligible: bool = False

    def __post_init__(self) -> None:
        for name in ("outcome_id", "run_id", "decision_artifact_id", "benchmark_id"):
            require_identifier(getattr(self, name), name)
        require_text(self.horizon, "horizon")
        require_iso_datetime(self.decision_at, "decision_at")
        require_iso_datetime(self.observed_at, "observed_at")
        if _instant(self.observed_at) <= _instant(self.decision_at):
            raise ContractValidationError("MarketOutcome must be observed after the decision")
        for name in (
            "portfolio_return",
            "benchmark_return",
            "max_drawdown",
            "gross_exposure",
            "turnover",
            "simulated_cost",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                raise ContractValidationError(f"{name} must be a finite number")
        if self.max_drawdown > 0:
            raise ContractValidationError("max_drawdown must be zero or negative")
        if self.gross_exposure < 0 or self.turnover < 0 or self.simulated_cost < 0:
            raise ContractValidationError("exposure, turnover, and cost must not be negative")
        if self.research_input_eligible:
            raise ContractValidationError("MarketOutcome can never be a historical research input")


class MarketOutcomeLog:
    def __init__(self) -> None:
        self._records: list[MarketOutcome] = []

    def append(self, outcome: MarketOutcome) -> None:
        if any(item.outcome_id == outcome.outcome_id for item in self._records):
            raise ContractValidationError(f"duplicate outcome_id: {outcome.outcome_id}")
        if any(
            item.run_id == outcome.run_id and item.horizon == outcome.horizon
            for item in self._records
        ):
            raise ContractValidationError("a run can have only one immutable observation per horizon")
        self._records.append(outcome)

    @property
    def records(self) -> tuple[MarketOutcome, ...]:
        return tuple(self._records)
