"""Claim-to-fact closure checks used as a gate before CIO synthesis."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from product.mcp.provenance import FactEnvelope


@dataclass(frozen=True, slots=True)
class Claim:
    claim_id: str
    statement: str
    evidence_refs: tuple[str, ...] = ()
    is_assumption: bool = False
    assumption_rationale: str | None = None
    material: bool = True


@dataclass(frozen=True, slots=True)
class ClosureReport:
    eligible_for_cio: bool
    unsupported_claim_ids: tuple[str, ...]
    unknown_fact_refs: tuple[str, ...]
    resolved_source_ids: tuple[str, ...]


def validate_claim_evidence_closure(
    claims: Iterable[Claim], facts: Iterable[FactEnvelope]
) -> ClosureReport:
    fact_index = {fact.fact_id: fact for fact in facts}
    unsupported: set[str] = set()
    unknown: set[str] = set()
    source_ids: set[str] = set()

    for claim in claims:
        if not claim.material:
            continue
        if claim.is_assumption:
            if not claim.assumption_rationale:
                unsupported.add(claim.claim_id)
            continue
        if not claim.evidence_refs:
            unsupported.add(claim.claim_id)
            continue
        for fact_id in claim.evidence_refs:
            fact = fact_index.get(fact_id)
            if fact is None:
                unknown.add(fact_id)
            else:
                source_ids.add(fact.source_id)

    return ClosureReport(
        eligible_for_cio=not unsupported and not unknown,
        unsupported_claim_ids=tuple(sorted(unsupported)),
        unknown_fact_refs=tuple(sorted(unknown)),
        resolved_source_ids=tuple(sorted(source_ids)),
    )
