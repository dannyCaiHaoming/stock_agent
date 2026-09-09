"""Point-in-time fact, claim, assumption, and evidence contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, ClassVar

from .base import (
    ArtifactContract,
    ArtifactEnvelope,
    ContractValidationError,
    JsonContract,
    require_identifier,
    require_iso_date_or_datetime,
    require_iso_datetime,
    require_non_empty_sequence,
    require_text,
    require_unique,
)


class FreshnessStatus(str, Enum):
    CURRENT = "CURRENT"
    STALE = "STALE"
    UNKNOWN = "UNKNOWN"


class ClaimKind(str, Enum):
    FACTUAL = "FACTUAL"
    INTERPRETIVE = "INTERPRETIVE"


@dataclass(frozen=True, slots=True)
class FactEnvelope(JsonContract):
    schema_name: ClassVar[str] = "fact-envelope"

    fact_id: str
    security_id: str
    field_or_statement: str
    value: Any
    unit: str
    source_id: str
    source_type: str
    source_locator: str
    as_of: str
    retrieved_at: str
    source_version_or_hash: str
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN
    quality_flags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.freshness_status, FreshnessStatus):
            raise ContractValidationError("freshness_status must be a FreshnessStatus value")
        require_identifier(self.fact_id, "fact_id")
        require_identifier(self.security_id, "security_id")
        require_text(self.field_or_statement, "field_or_statement")
        require_text(self.unit, "unit")
        require_identifier(self.source_id, "source_id")
        require_text(self.source_type, "source_type")
        require_text(self.source_locator, "source_locator")
        require_iso_date_or_datetime(self.as_of, "as_of")
        require_iso_datetime(self.retrieved_at, "retrieved_at")
        require_text(self.source_version_or_hash, "source_version_or_hash")
        for index, flag in enumerate(self.quality_flags):
            require_identifier(flag, f"quality_flags[{index}]")
        require_unique(self.quality_flags, "quality_flags")
        # Serialization is also the authoritative JSON-compatibility check for value.
        self.to_dict()


@dataclass(frozen=True, slots=True)
class Assumption(JsonContract):
    schema_name: ClassVar[str] = "assumption"

    assumption_id: str
    statement: str
    rationale: str

    def __post_init__(self) -> None:
        require_identifier(self.assumption_id, "assumption_id")
        require_text(self.statement, "assumption statement")
        require_text(self.rationale, "assumption rationale")


@dataclass(frozen=True, slots=True)
class Claim(JsonContract):
    schema_name: ClassVar[str] = "claim"

    claim_id: str
    statement: str
    kind: ClaimKind
    evidence_fact_ids: tuple[str, ...] = ()
    assumption_ids: tuple[str, ...] = ()
    counter_evidence_fact_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ClaimKind):
            raise ContractValidationError("claim kind must be a ClaimKind value")
        require_identifier(self.claim_id, "claim_id")
        require_text(self.statement, "claim statement")
        for field_name, values in (
            ("evidence_fact_ids", self.evidence_fact_ids),
            ("assumption_ids", self.assumption_ids),
            ("counter_evidence_fact_ids", self.counter_evidence_fact_ids),
        ):
            for index, value in enumerate(values):
                require_identifier(value, f"{field_name}[{index}]")
            require_unique(values, field_name)
        if not self.evidence_fact_ids and not self.assumption_ids:
            raise ContractValidationError(
                "a claim must reference at least one fact or be explicitly grounded in an assumption"
            )


@dataclass(frozen=True, slots=True)
class EvidenceBundle(ArtifactContract):
    schema_name: ClassVar[str] = "evidence-bundle"

    envelope: ArtifactEnvelope
    facts: tuple[FactEnvelope, ...]
    claims: tuple[Claim, ...]
    assumptions: tuple[Assumption, ...] = ()

    def __post_init__(self) -> None:
        require_non_empty_sequence(self.facts, "facts")
        fact_ids = [fact.fact_id for fact in self.facts]
        claim_ids = [claim.claim_id for claim in self.claims]
        assumption_ids = [assumption.assumption_id for assumption in self.assumptions]
        require_unique(fact_ids, "fact IDs")
        require_unique(claim_ids, "claim IDs")
        require_unique(assumption_ids, "assumption IDs")

        known_facts = set(fact_ids)
        known_assumptions = set(assumption_ids)
        for claim in self.claims:
            missing_facts = (
                set(claim.evidence_fact_ids) | set(claim.counter_evidence_fact_ids)
            ) - known_facts
            missing_assumptions = set(claim.assumption_ids) - known_assumptions
            if missing_facts:
                raise ContractValidationError(
                    f"claim {claim.claim_id} references unknown facts: {sorted(missing_facts)}"
                )
            if missing_assumptions:
                raise ContractValidationError(
                    f"claim {claim.claim_id} references unknown assumptions: {sorted(missing_assumptions)}"
                )
