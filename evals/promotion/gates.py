"""Fail-closed promotion gates with a fixed, disjoint holdout set."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite


@dataclass(frozen=True, slots=True)
class HoldoutStrategy:
    strategy_id: str
    training_case_ids: tuple[str, ...]
    holdout_case_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.strategy_id.strip() or not self.training_case_ids or not self.holdout_case_ids:
            raise ValueError("strategy and non-empty training/holdout cases are required")
        if len(self.training_case_ids) != len(set(self.training_case_ids)):
            raise ValueError("training case IDs must be unique")
        if len(self.holdout_case_ids) != len(set(self.holdout_case_ids)):
            raise ValueError("holdout case IDs must be unique")
        overlap = set(self.training_case_ids) & set(self.holdout_case_ids)
        if overlap:
            raise ValueError(f"training and holdout sets overlap: {sorted(overlap)}")


@dataclass(frozen=True, slots=True)
class SplitMetrics:
    baseline_quality: float
    candidate_quality: float

    def __post_init__(self) -> None:
        for name in ("baseline_quality", "candidate_quality"):
            value = getattr(self, name)
            if not isfinite(value) or not 0 <= value <= 1:
                raise ValueError(f"{name} must be between 0 and 1")

    @property
    def delta(self) -> float:
        return self.candidate_quality - self.baseline_quality


@dataclass(frozen=True, slots=True)
class CandidateEvaluation:
    candidate_version: str
    strategy: HoldoutStrategy
    training: SplitMetrics
    holdout: SplitMetrics
    deterministic_gates_passed: bool
    hard_constraint_regressions: int
    adversarial_passed: bool
    ablation_passed: bool

    def __post_init__(self) -> None:
        if not self.candidate_version.strip():
            raise ValueError("candidate_version is required")
        if self.hard_constraint_regressions < 0:
            raise ValueError("hard_constraint_regressions must not be negative")


@dataclass(frozen=True, slots=True)
class PromotionDecision:
    candidate_version: str
    accepted: bool
    reasons: tuple[str, ...]


class PromotionGate:
    """Reject candidates that regress holdout or any non-negotiable gate."""

    @staticmethod
    def evaluate(evaluation: CandidateEvaluation) -> PromotionDecision:
        failures: list[str] = []
        if not evaluation.deterministic_gates_passed:
            failures.append("deterministic gates failed")
        if evaluation.hard_constraint_regressions:
            failures.append("hard-constraint regression detected")
        if not evaluation.adversarial_passed:
            failures.append("adversarial evaluation failed")
        if not evaluation.ablation_passed:
            failures.append("ablation gain threshold failed")
        if evaluation.holdout.delta < 0:
            failures.append("holdout quality regressed")
        return PromotionDecision(
            candidate_version=evaluation.candidate_version,
            accepted=not failures,
            reasons=tuple(failures) if failures else ("all predeclared promotion gates passed",),
        )
