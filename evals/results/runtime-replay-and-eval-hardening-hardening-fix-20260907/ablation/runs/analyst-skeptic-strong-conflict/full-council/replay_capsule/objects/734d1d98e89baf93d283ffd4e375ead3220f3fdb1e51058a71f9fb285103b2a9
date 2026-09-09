"""Decision trace, feedback, outcome, proposal, and promotion contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar, Mapping

from .base import (
    ArtifactContract,
    ArtifactEnvelope,
    ContractValidationError,
    JsonContract,
    require_finite_number,
    require_identifier,
    require_iso_datetime,
    require_lineage_member,
    require_non_empty_sequence,
    require_text,
    require_unique,
)


class FeedbackType(str, Enum):
    FACT_ERROR = "FACT_ERROR"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    REASONING_GAP = "REASONING_GAP"
    MANDATE_MISUNDERSTANDING = "MANDATE_MISUNDERSTANDING"
    USABILITY = "USABILITY"
    JUDGMENT_DISAGREEMENT = "JUDGMENT_DISAGREEMENT"
    OUTCOME_ASSESSMENT = "OUTCOME_ASSESSMENT"


class ThesisEventStatus(str, Enum):
    REALIZED = "REALIZED"
    NOT_REALIZED = "NOT_REALIZED"
    PARTIAL = "PARTIAL"
    UNOBSERVABLE = "UNOBSERVABLE"


class ImprovementTarget(str, Enum):
    SKILL = "SKILL"
    AGENT_CONFIGURATION = "AGENT_CONFIGURATION"
    SCHEMA = "SCHEMA"
    DATA_SOURCE = "DATA_SOURCE"
    EVAL = "EVAL"


class PromotionStatus(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    ROLLED_BACK = "ROLLED_BACK"


@dataclass(frozen=True, slots=True)
class VersionManifest(JsonContract):
    schema_name: ClassVar[str] = "version-manifest"

    model_snapshot: str
    skill_versions: Mapping[str, str]
    agent_versions: Mapping[str, str]
    schema_versions: Mapping[str, str]
    mcp_adapter_versions: Mapping[str, str]
    risk_policy_version: str
    data_snapshot_version: str

    def __post_init__(self) -> None:
        require_text(self.model_snapshot, "model_snapshot")
        require_text(self.risk_policy_version, "risk_policy_version")
        require_text(self.data_snapshot_version, "data_snapshot_version")
        for field_name, versions in (
            ("skill_versions", self.skill_versions),
            ("agent_versions", self.agent_versions),
            ("schema_versions", self.schema_versions),
            ("mcp_adapter_versions", self.mcp_adapter_versions),
        ):
            for component, version in versions.items():
                require_identifier(component, f"{field_name} component")
                require_text(version, f"{field_name}.{component}")


@dataclass(frozen=True, slots=True)
class TraceEvent(JsonContract):
    schema_name: ClassVar[str] = "trace-event"

    sequence: int
    occurred_at: str
    event_type: str
    artifact_ids: tuple[str, ...]
    details: Mapping[str, Any]

    def __post_init__(self) -> None:
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise ContractValidationError("trace event sequence must be a non-negative integer")
        require_iso_datetime(self.occurred_at, "trace event occurred_at")
        require_identifier(self.event_type, "trace event_type")
        for index, artifact_id in enumerate(self.artifact_ids):
            require_identifier(artifact_id, f"trace event artifact_ids[{index}]")
        require_unique(self.artifact_ids, "trace event artifact_ids")
        self.to_dict()


@dataclass(frozen=True, slots=True)
class DecisionTrace(ArtifactContract):
    schema_name: ClassVar[str] = "decision-trace"

    envelope: ArtifactEnvelope
    decision_cutoff: str
    versions: VersionManifest
    artifact_ids: tuple[str, ...]
    events: tuple[TraceEvent, ...]

    def __post_init__(self) -> None:
        require_iso_datetime(self.decision_cutoff, "decision_cutoff")
        require_non_empty_sequence(self.artifact_ids, "trace artifact_ids")
        for index, artifact_id in enumerate(self.artifact_ids):
            require_identifier(artifact_id, f"trace artifact_ids[{index}]")
            require_lineage_member(self.envelope, artifact_id, f"trace artifact_ids[{index}]")
        require_unique(self.artifact_ids, "trace artifact_ids")
        require_non_empty_sequence(self.events, "trace events")
        sequences = [event.sequence for event in self.events]
        if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
            raise ContractValidationError("trace event sequences must be unique and ascending")
        unknown_event_artifacts = {
            artifact_id
            for event in self.events
            for artifact_id in event.artifact_ids
            if artifact_id not in self.artifact_ids
        }
        if unknown_event_artifacts:
            raise ContractValidationError(
                f"trace events reference unlisted artifacts: {sorted(unknown_event_artifacts)}"
            )


@dataclass(frozen=True, slots=True)
class HumanFeedback(ArtifactContract):
    schema_name: ClassVar[str] = "human-feedback"

    envelope: ArtifactEnvelope
    target_artifact_id: str
    feedback_type: FeedbackType
    submitted_at: str
    notes: str
    target_claim_id: str | None = None
    target_fact_id: str | None = None
    target_agent_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.feedback_type, FeedbackType):
            raise ContractValidationError("feedback_type must be a FeedbackType value")
        require_lineage_member(self.envelope, self.target_artifact_id, "target_artifact_id")
        require_iso_datetime(self.submitted_at, "feedback submitted_at")
        require_text(self.notes, "feedback notes")
        for field_name, value in (
            ("target_claim_id", self.target_claim_id),
            ("target_fact_id", self.target_fact_id),
            ("target_agent_id", self.target_agent_id),
        ):
            if value is not None:
                require_identifier(value, field_name)


@dataclass(frozen=True, slots=True)
class MarketOutcome(ArtifactContract):
    schema_name: ClassVar[str] = "market-outcome"

    envelope: ArtifactEnvelope
    decision_artifact_id: str
    observed_at: str
    horizon_days: int
    portfolio_return: int | float
    benchmark_return: int | float
    thesis_event_status: ThesisEventStatus
    observations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.thesis_event_status, ThesisEventStatus):
            raise ContractValidationError("thesis_event_status must be a ThesisEventStatus value")
        require_lineage_member(self.envelope, self.decision_artifact_id, "decision_artifact_id")
        require_iso_datetime(self.observed_at, "outcome observed_at")
        if isinstance(self.horizon_days, bool) or not isinstance(self.horizon_days, int) or self.horizon_days <= 0:
            raise ContractValidationError("horizon_days must be a positive integer")
        require_finite_number(self.portfolio_return, "portfolio_return")
        require_finite_number(self.benchmark_return, "benchmark_return")
        for index, observation in enumerate(self.observations):
            require_text(observation, f"observations[{index}]")


@dataclass(frozen=True, slots=True)
class ImprovementProposal(ArtifactContract):
    schema_name: ClassVar[str] = "improvement-proposal"

    envelope: ArtifactEnvelope
    trace_artifact_ids: tuple[str, ...]
    observation_artifact_ids: tuple[str, ...]
    failure_mode: str
    root_cause_hypothesis: str
    target: ImprovementTarget
    proposed_change: str
    expected_metrics: tuple[str, ...]
    regression_risks: tuple[str, ...]
    replay_plan: str
    rollback_plan: str

    def __post_init__(self) -> None:
        if not isinstance(self.target, ImprovementTarget):
            raise ContractValidationError("target must be an ImprovementTarget value")
        require_non_empty_sequence(self.trace_artifact_ids, "trace_artifact_ids")
        require_non_empty_sequence(self.observation_artifact_ids, "observation_artifact_ids")
        linked_ids = self.trace_artifact_ids + self.observation_artifact_ids
        require_unique(linked_ids, "improvement proposal linked artifact IDs")
        for index, artifact_id in enumerate(linked_ids):
            require_lineage_member(self.envelope, artifact_id, f"linked_artifact_ids[{index}]")
        for field_name, value in (
            ("failure_mode", self.failure_mode),
            ("root_cause_hypothesis", self.root_cause_hypothesis),
            ("proposed_change", self.proposed_change),
            ("replay_plan", self.replay_plan),
            ("rollback_plan", self.rollback_plan),
        ):
            require_text(value, field_name)
        for field_name, values in (
            ("expected_metrics", self.expected_metrics),
            ("regression_risks", self.regression_risks),
        ):
            require_non_empty_sequence(values, field_name)
            for index, value in enumerate(values):
                require_text(value, f"{field_name}[{index}]")


@dataclass(frozen=True, slots=True)
class PromotionRecord(ArtifactContract):
    schema_name: ClassVar[str] = "promotion-record"

    envelope: ArtifactEnvelope
    proposal_artifact_id: str
    evaluation_artifact_ids: tuple[str, ...]
    previous_versions: VersionManifest
    candidate_versions: VersionManifest
    status: PromotionStatus
    approved_by: str
    decided_at: str
    rollback_conditions: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.status, PromotionStatus):
            raise ContractValidationError("status must be a PromotionStatus value")
        require_lineage_member(self.envelope, self.proposal_artifact_id, "proposal_artifact_id")
        require_non_empty_sequence(self.evaluation_artifact_ids, "evaluation_artifact_ids")
        for index, artifact_id in enumerate(self.evaluation_artifact_ids):
            require_lineage_member(self.envelope, artifact_id, f"evaluation_artifact_ids[{index}]")
        require_unique(self.evaluation_artifact_ids, "evaluation_artifact_ids")
        require_identifier(self.approved_by, "approved_by")
        require_iso_datetime(self.decided_at, "promotion decided_at")
        require_non_empty_sequence(self.rollback_conditions, "rollback_conditions")
        for index, condition in enumerate(self.rollback_conditions):
            require_text(condition, f"rollback_conditions[{index}]")
