"""Outcome decomposition that never reduces correctness to one price move."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from typing import Iterable


def _number(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be a finite number")


class ThesisEventStatus(str, Enum):
    REALIZED = "REALIZED"
    NOT_REALIZED = "NOT_REALIZED"
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class HorizonOutcome:
    horizon: str
    portfolio_return: float
    benchmark_return: float
    max_drawdown: float
    gross_exposure: float
    turnover: float
    simulated_cost: float
    thesis_event_status: ThesisEventStatus

    def __post_init__(self) -> None:
        if not self.horizon.strip():
            raise ValueError("horizon must not be empty")
        for field_name in (
            "portfolio_return",
            "benchmark_return",
            "max_drawdown",
            "gross_exposure",
            "turnover",
            "simulated_cost",
        ):
            _number(getattr(self, field_name), field_name)
        if self.max_drawdown > 0:
            raise ValueError("max_drawdown must be zero or negative")
        if self.gross_exposure < 0 or self.turnover < 0 or self.simulated_cost < 0:
            raise ValueError("exposure, turnover, and cost must not be negative")

    @property
    def relative_return(self) -> float:
        return self.portfolio_return - self.benchmark_return


@dataclass(frozen=True, slots=True)
class OutcomeEvaluationReport:
    observations: tuple[HorizonOutcome, ...]
    relative_returns: tuple[tuple[str, float], ...]
    thesis_event_realization_rate: float | None
    correctness_label: None = None


class MultiHorizonOutcomeEvaluator:
    @staticmethod
    def evaluate(outcomes: Iterable[HorizonOutcome]) -> OutcomeEvaluationReport:
        observations = tuple(outcomes)
        if len(observations) < 2:
            raise ValueError("outcome evaluation requires at least two horizons")
        horizons = [item.horizon for item in observations]
        if len(horizons) != len(set(horizons)):
            raise ValueError("outcome horizons must be unique")
        resolved = [
            item.thesis_event_status is ThesisEventStatus.REALIZED
            for item in observations
            if item.thesis_event_status is not ThesisEventStatus.UNRESOLVED
        ]
        rate = sum(resolved) / len(resolved) if resolved else None
        return OutcomeEvaluationReport(
            observations=observations,
            relative_returns=tuple((item.horizon, item.relative_return) for item in observations),
            thesis_event_realization_rate=rate,
        )
