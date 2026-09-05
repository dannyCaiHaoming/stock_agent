"""Typed, append-only human feedback observations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from product.contracts.base import (
    ContractValidationError,
    JsonContract,
    require_identifier,
    require_iso_datetime,
    require_text,
)
from product.trace import VersionLock


class FeedbackCategory(str, Enum):
    FACT_ERROR = "FACT_ERROR"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    REASONING_GAP = "REASONING_GAP"
    MANDATE_MISUNDERSTANDING = "MANDATE_MISUNDERSTANDING"
    USABILITY = "USABILITY"
    JUDGMENT_DISAGREEMENT = "JUDGMENT_DISAGREEMENT"
    OUTCOME_EVALUATION = "OUTCOME_EVALUATION"


@dataclass(frozen=True, slots=True)
class HumanFeedback(JsonContract):
    schema_name: ClassVar[str] = "human-feedback"

    feedback_id: str
    run_id: str
    artifact_id: str
    category: FeedbackCategory
    submitted_at: str
    author_id: str
    details: str
    versions: VersionLock
    claim_id: str | None = None
    fact_id: str | None = None
    agent_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("feedback_id", "run_id", "artifact_id", "author_id"):
            require_identifier(getattr(self, name), name)
        require_iso_datetime(self.submitted_at, "submitted_at")
        require_text(self.details, "details")
        for name in ("claim_id", "fact_id", "agent_id"):
            value = getattr(self, name)
            if value is not None:
                require_identifier(value, name)
        if self.category is FeedbackCategory.FACT_ERROR and not (self.fact_id or self.claim_id):
            raise ContractValidationError("FACT_ERROR feedback must identify a fact or claim")


class HumanFeedbackLog:
    """Process-local append-only log; callers may persist serialized records externally."""

    def __init__(self) -> None:
        self._records: list[HumanFeedback] = []

    def append(self, feedback: HumanFeedback) -> None:
        if any(item.feedback_id == feedback.feedback_id for item in self._records):
            raise ContractValidationError(f"duplicate feedback_id: {feedback.feedback_id}")
        self._records.append(feedback)

    @property
    def records(self) -> tuple[HumanFeedback, ...]:
        return tuple(self._records)
