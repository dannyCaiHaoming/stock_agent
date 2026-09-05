"""Transparent structured grader for evidence and reasoning quality."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Iterable


def _fraction(value: float, name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError(f"{name} must be finite")
    if not 0 <= value <= 1:
        raise ValueError(f"{name} must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class EvidenceReasoningCase:
    case_id: str
    citation_support: tuple[bool, ...]
    thesis_present: bool
    counter_thesis_present: bool
    conflict_handled: bool
    invalidation_conditions: tuple[str, ...]
    confidence: float
    outcome_label: bool | None
    human_accept: bool

    def __post_init__(self) -> None:
        if not self.case_id.strip():
            raise ValueError("case_id must not be empty")
        if not self.citation_support:
            raise ValueError("citation_support must contain human-labelled citations")
        if any(not condition.strip() for condition in self.invalidation_conditions):
            raise ValueError("invalidation conditions must not be blank")
        _fraction(self.confidence, "confidence")


@dataclass(frozen=True, slots=True)
class EvidenceReasoningGrade:
    case_id: str
    citation_support_score: float
    thesis_score: float
    counter_thesis_score: float
    conflict_score: float
    invalidation_score: float
    calibration_loss: float | None
    accepted: bool

    @property
    def quality_score(self) -> float:
        components = (
            self.citation_support_score,
            self.thesis_score,
            self.counter_thesis_score,
            self.conflict_score,
            self.invalidation_score,
        )
        return sum(components) / len(components)


@dataclass(frozen=True, slots=True)
class GraderValidationReport:
    grades: tuple[EvidenceReasoningGrade, ...]
    human_agreement: float
    accepted: bool


class EvidenceReasoningGrader:
    """Grades explicit dimensions without deriving investment truth from returns."""

    def __init__(self, *, minimum_quality: float = 0.8, minimum_human_agreement: float = 0.8):
        _fraction(minimum_quality, "minimum_quality")
        _fraction(minimum_human_agreement, "minimum_human_agreement")
        self.minimum_quality = minimum_quality
        self.minimum_human_agreement = minimum_human_agreement

    def grade(self, case: EvidenceReasoningCase) -> EvidenceReasoningGrade:
        citation = sum(case.citation_support) / len(case.citation_support)
        calibration = None
        if case.outcome_label is not None:
            calibration = (case.confidence - float(case.outcome_label)) ** 2
        components = (
            citation,
            float(case.thesis_present),
            float(case.counter_thesis_present),
            float(case.conflict_handled),
            float(bool(case.invalidation_conditions)),
        )
        return EvidenceReasoningGrade(
            case_id=case.case_id,
            citation_support_score=citation,
            thesis_score=components[1],
            counter_thesis_score=components[2],
            conflict_score=components[3],
            invalidation_score=components[4],
            calibration_loss=calibration,
            accepted=sum(components) / len(components) >= self.minimum_quality,
        )

    def validate_against_human_labels(
        self, cases: Iterable[EvidenceReasoningCase]
    ) -> GraderValidationReport:
        labelled = tuple(cases)
        if not labelled:
            raise ValueError("at least one human-labelled case is required")
        grades = tuple(self.grade(case) for case in labelled)
        agreement = sum(
            grade.accepted == case.human_accept for grade, case in zip(grades, labelled, strict=True)
        ) / len(labelled)
        return GraderValidationReport(
            grades=grades,
            human_agreement=agreement,
            accepted=agreement >= self.minimum_human_agreement,
        )
