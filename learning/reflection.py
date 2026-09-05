"""Reflection contracts that can only produce non-production proposals."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import ClassVar, Mapping

from product.contracts.base import (
    ContractValidationError,
    JsonContract,
    require_identifier,
    require_iso_datetime,
    require_text,
)

from .attribution import AttributionDataset


class ImprovementTarget(str, Enum):
    SKILL = "SKILL"
    AGENT_CONFIG = "AGENT_CONFIG"
    SCHEMA = "SCHEMA"
    DATA_SOURCE = "DATA_SOURCE"
    EVAL = "EVAL"


@dataclass(frozen=True, slots=True)
class ReflectionRequest:
    proposal_id: str
    created_at: str
    failure_pattern: str
    evidence_artifact_ids: tuple[str, ...]
    root_cause_hypotheses: tuple[str, ...]
    target: ImprovementTarget
    proposed_change: str
    expected_metrics: Mapping[str, float]
    degradation_risks: tuple[str, ...]
    replay_plan: str
    rollback_plan: str


@dataclass(frozen=True, slots=True)
class ImprovementProposal(JsonContract):
    schema_name: ClassVar[str] = "improvement-proposal"

    proposal_id: str
    created_at: str
    source_dataset_id: str
    source_sample_ids: tuple[str, ...]
    failure_pattern: str
    evidence_artifact_ids: tuple[str, ...]
    root_cause_hypotheses: tuple[str, ...]
    target: ImprovementTarget
    proposed_change: str
    expected_metrics: Mapping[str, float]
    degradation_risks: tuple[str, ...]
    replay_plan: str
    rollback_plan: str
    production_write_authorized: bool = False

    def __post_init__(self) -> None:
        require_identifier(self.proposal_id, "proposal_id")
        require_iso_datetime(self.created_at, "created_at")
        require_identifier(self.source_dataset_id, "source_dataset_id")
        if not self.source_sample_ids or not self.evidence_artifact_ids:
            raise ContractValidationError("proposal requires source samples and evidence")
        for field_name in ("source_sample_ids", "evidence_artifact_ids"):
            for value in getattr(self, field_name):
                require_identifier(value, field_name)
        for field_name in (
            "failure_pattern",
            "proposed_change",
            "replay_plan",
            "rollback_plan",
        ):
            require_text(getattr(self, field_name), field_name)
        if not self.root_cause_hypotheses or not self.degradation_risks or not self.expected_metrics:
            raise ContractValidationError(
                "proposal requires root-cause hypotheses, expected metrics, and degradation risks"
            )
        if any(not item.strip() for item in (*self.root_cause_hypotheses, *self.degradation_risks)):
            raise ContractValidationError("proposal list entries must not be blank")
        metrics: dict[str, float] = {}
        for name, value in self.expected_metrics.items():
            require_identifier(name, "expected metric name")
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ContractValidationError("expected metric values must be numeric")
            metrics[name] = float(value)
        object.__setattr__(self, "expected_metrics", metrics)
        if self.production_write_authorized:
            raise ContractValidationError("ImprovementProposal cannot authorize production writes")


class ReflectionEngine:
    """Transforms attribution into an ImprovementProposal, never a production change."""

    @staticmethod
    def reflect(dataset: AttributionDataset, request: ReflectionRequest) -> ImprovementProposal:
        if not request.evidence_artifact_ids:
            raise ContractValidationError("reflection must cite concrete evidence artifacts")
        return ImprovementProposal(
            proposal_id=request.proposal_id,
            created_at=request.created_at,
            source_dataset_id=dataset.dataset_id,
            source_sample_ids=tuple(sample.sample_id for sample in dataset.samples),
            failure_pattern=request.failure_pattern,
            evidence_artifact_ids=request.evidence_artifact_ids,
            root_cause_hypotheses=request.root_cause_hypotheses,
            target=request.target,
            proposed_change=request.proposed_change,
            expected_metrics=request.expected_metrics,
            degradation_risks=request.degradation_risks,
            replay_plan=request.replay_plan,
            rollback_plan=request.rollback_plan,
        )
