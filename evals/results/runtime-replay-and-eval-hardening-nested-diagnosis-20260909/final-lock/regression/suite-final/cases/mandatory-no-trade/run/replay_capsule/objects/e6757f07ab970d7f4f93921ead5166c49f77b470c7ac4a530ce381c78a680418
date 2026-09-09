"""Structured specialist research artifact contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar

from .base import (
    ArtifactContract,
    ArtifactEnvelope,
    ContractValidationError,
    JsonContract,
    require_finite_number,
    require_fraction,
    require_identifier,
    require_iso_date_or_datetime,
    require_non_empty_sequence,
    require_text,
    require_unique,
)


def _validate_ids(values: tuple[str, ...], field_name: str, *, required: bool = False) -> None:
    if required:
        require_non_empty_sequence(values, field_name)
    for index, value in enumerate(values):
        require_identifier(value, f"{field_name}[{index}]")
    require_unique(values, field_name)


def _validate_texts(values: tuple[str, ...], field_name: str, *, required: bool = False) -> None:
    if required:
        require_non_empty_sequence(values, field_name)
    for index, value in enumerate(values):
        require_text(value, f"{field_name}[{index}]")


@dataclass(frozen=True, slots=True)
class AgentResearchReport(ArtifactContract):
    schema_name: ClassVar[str] = "agent-research-report"

    envelope: ArtifactEnvelope
    scope: str
    security_ids: tuple[str, ...]
    claim_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    assumption_ids: tuple[str, ...]
    counter_evidence_fact_ids: tuple[str, ...]
    uncertainties: tuple[str, ...]
    data_gaps: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    confidence: int | float
    confidence_rationale: str

    def __post_init__(self) -> None:
        require_text(self.scope, "research scope")
        _validate_ids(self.security_ids, "security_ids", required=True)
        _validate_ids(self.claim_ids, "claim_ids", required=True)
        _validate_ids(self.fact_ids, "fact_ids")
        _validate_ids(self.assumption_ids, "assumption_ids")
        _validate_ids(self.counter_evidence_fact_ids, "counter_evidence_fact_ids")
        _validate_texts(self.uncertainties, "uncertainties")
        _validate_texts(self.data_gaps, "data_gaps")
        _validate_texts(self.invalidation_conditions, "invalidation_conditions", required=True)
        require_fraction(self.confidence, "confidence")
        require_text(self.confidence_rationale, "confidence_rationale")
        if not self.fact_ids and not self.assumption_ids:
            raise ContractValidationError(
                "research claims must remain distinguishable from facts and assumptions"
            )


@dataclass(frozen=True, slots=True)
class ValuationScenario(JsonContract):
    schema_name: ClassVar[str] = "valuation-scenario"

    name: str
    deterministic_method: str
    input_fact_ids: tuple[str, ...]
    assumption_ids: tuple[str, ...]
    result_value: int | float
    currency: str

    def __post_init__(self) -> None:
        require_text(self.name, "valuation scenario name")
        require_text(self.deterministic_method, "deterministic_method")
        _validate_ids(self.input_fact_ids, "input_fact_ids")
        _validate_ids(self.assumption_ids, "assumption_ids")
        if not self.input_fact_ids and not self.assumption_ids:
            raise ContractValidationError("valuation scenario requires facts or explicit assumptions")
        require_finite_number(self.result_value, "valuation result_value")
        require_text(self.currency, "valuation currency")


@dataclass(frozen=True, slots=True)
class ValuationAssessment(ArtifactContract):
    schema_name: ClassVar[str] = "valuation-assessment"

    envelope: ArtifactEnvelope
    security_id: str
    scenarios: tuple[ValuationScenario, ...]
    interpretation_claim_ids: tuple[str, ...]
    uncertainties: tuple[str, ...]
    data_gaps: tuple[str, ...]

    def __post_init__(self) -> None:
        require_identifier(self.security_id, "security_id")
        require_non_empty_sequence(self.scenarios, "valuation scenarios")
        _validate_ids(self.interpretation_claim_ids, "interpretation_claim_ids", required=True)
        _validate_texts(self.uncertainties, "valuation uncertainties")
        _validate_texts(self.data_gaps, "valuation data_gaps")
        names = [scenario.name for scenario in self.scenarios]
        if len(names) != len(set(names)):
            raise ContractValidationError("valuation scenario names must be unique")


@dataclass(frozen=True, slots=True)
class CatalystEvent(JsonContract):
    schema_name: ClassVar[str] = "catalyst-event"

    event_id: str
    description: str
    window_start: str
    window_end: str
    supporting_fact_ids: tuple[str, ...]
    interpretation: str

    def __post_init__(self) -> None:
        require_identifier(self.event_id, "event_id")
        require_text(self.description, "catalyst description")
        require_iso_date_or_datetime(self.window_start, "window_start")
        require_iso_date_or_datetime(self.window_end, "window_end")
        _validate_ids(self.supporting_fact_ids, "supporting_fact_ids", required=True)
        require_text(self.interpretation, "catalyst interpretation")


@dataclass(frozen=True, slots=True)
class CatalystMap(ArtifactContract):
    schema_name: ClassVar[str] = "catalyst-map"

    envelope: ArtifactEnvelope
    security_id: str
    events: tuple[CatalystEvent, ...]
    counter_evidence_fact_ids: tuple[str, ...]
    uncertainties: tuple[str, ...]
    data_gaps: tuple[str, ...]

    def __post_init__(self) -> None:
        require_identifier(self.security_id, "security_id")
        require_non_empty_sequence(self.events, "catalyst events")
        event_ids = [event.event_id for event in self.events]
        if len(event_ids) != len(set(event_ids)):
            raise ContractValidationError("catalyst event IDs must be unique")
        _validate_ids(self.counter_evidence_fact_ids, "counter_evidence_fact_ids")
        _validate_texts(self.uncertainties, "catalyst uncertainties")
        _validate_texts(self.data_gaps, "catalyst data_gaps")


@dataclass(frozen=True, slots=True)
class CounterThesisReport(ArtifactContract):
    schema_name: ClassVar[str] = "counter-thesis-report"

    envelope: ArtifactEnvelope
    security_id: str
    challenged_claim_ids: tuple[str, ...]
    counter_claim_ids: tuple[str, ...]
    supporting_fact_ids: tuple[str, ...]
    assumption_ids: tuple[str, ...]
    unresolved_conflicts: tuple[str, ...]
    data_gaps: tuple[str, ...]
    invalidation_conditions: tuple[str, ...]
    confidence: int | float
    confidence_rationale: str

    def __post_init__(self) -> None:
        require_identifier(self.security_id, "security_id")
        _validate_ids(self.challenged_claim_ids, "challenged_claim_ids", required=True)
        _validate_ids(self.counter_claim_ids, "counter_claim_ids", required=True)
        _validate_ids(self.supporting_fact_ids, "supporting_fact_ids")
        _validate_ids(self.assumption_ids, "assumption_ids")
        if not self.supporting_fact_ids and not self.assumption_ids:
            raise ContractValidationError("counter-thesis requires facts or explicit assumptions")
        _validate_texts(self.unresolved_conflicts, "unresolved_conflicts")
        _validate_texts(self.data_gaps, "counter-thesis data_gaps")
        _validate_texts(self.invalidation_conditions, "counter-thesis invalidation_conditions")
        require_fraction(self.confidence, "counter-thesis confidence")
        require_text(self.confidence_rationale, "counter-thesis confidence_rationale")
