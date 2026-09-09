"""Versioned freshness and conflict detection without investment interpretation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Mapping

from product.mcp.provenance import FactEnvelope, canonical_json, parse_timestamp


@dataclass(frozen=True, slots=True)
class FreshnessPolicy:
    version: str
    default_max_age: timedelta
    field_max_age: Mapping[str, timedelta]

    def threshold_for(self, semantic_field: str) -> timedelta:
        return self.field_max_age.get(semantic_field, self.default_max_age)


@dataclass(frozen=True, slots=True)
class FreshnessAssessment:
    fact_id: str
    policy_version: str
    status: str
    age_seconds: int
    threshold_seconds: int


@dataclass(frozen=True, slots=True)
class Conflict:
    security_id: str
    semantic_field: str
    as_of: str
    fact_ids: tuple[str, ...]
    source_ids: tuple[str, ...]
    reason_code: str = "MATERIAL_VALUE_CONFLICT"


def assess_freshness(
    fact: FactEnvelope, *, decision_time: str, policy: FreshnessPolicy
) -> FreshnessAssessment:
    age = parse_timestamp(decision_time) - parse_timestamp(fact.as_of)
    threshold = policy.threshold_for(fact.semantic_field)
    if age.total_seconds() < 0:
        status = "FUTURE_DATED"
    elif age > threshold:
        status = "STALE"
    else:
        status = "FRESH"
    return FreshnessAssessment(
        fact_id=fact.fact_id,
        policy_version=policy.version,
        status=status,
        age_seconds=int(age.total_seconds()),
        threshold_seconds=int(threshold.total_seconds()),
    )


def detect_missing_fields(
    facts: tuple[FactEnvelope, ...], expected_fields: tuple[str, ...]
) -> tuple[str, ...]:
    observed = {fact.semantic_field for fact in facts}
    return tuple(sorted(set(expected_fields) - observed))


def detect_conflicts(facts: tuple[FactEnvelope, ...]) -> tuple[Conflict, ...]:
    """Flag incompatible current source observations; never select a winner."""

    latest_by_source: dict[tuple[str, str, str, str], FactEnvelope] = {}
    for fact in facts:
        key = (fact.security_id, fact.semantic_field, fact.as_of, fact.source_id)
        current = latest_by_source.get(key)
        if current is None or parse_timestamp(fact.retrieved_at) > parse_timestamp(
            current.retrieved_at
        ):
            latest_by_source[key] = fact

    grouped: dict[tuple[str, str, str], list[FactEnvelope]] = {}
    for fact in latest_by_source.values():
        grouped.setdefault(
            (fact.security_id, fact.semantic_field, fact.as_of), []
        ).append(fact)

    conflicts: list[Conflict] = []
    for (security_id, field, as_of), candidates in grouped.items():
        signatures = {
            canonical_json((fact.value, fact.unit, fact.currency)) for fact in candidates
        }
        if len(signatures) <= 1:
            continue
        conflicts.append(
            Conflict(
                security_id=security_id,
                semantic_field=field,
                as_of=as_of,
                fact_ids=tuple(sorted(fact.fact_id for fact in candidates)),
                source_ids=tuple(sorted(fact.source_id for fact in candidates)),
            )
        )
    return tuple(sorted(conflicts, key=lambda item: (item.security_id, item.semantic_field)))
