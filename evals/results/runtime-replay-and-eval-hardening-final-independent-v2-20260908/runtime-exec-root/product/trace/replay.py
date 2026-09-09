"""Point-in-time evidence selection for historical replay."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, ClassVar, Iterable, TypeVar

from product.contracts.base import JsonContract, require_iso_datetime
from product.contracts.evidence import FactEnvelope

from .models import TraceValidationError


T = TypeVar("T")


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


@dataclass(frozen=True, slots=True)
class ReplaySelection(JsonContract):
    schema_name: ClassVar[str] = "point-in-time-replay-selection"

    decision_cutoff: str
    facts: tuple[FactEnvelope, ...]
    excluded_future_fact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        require_iso_datetime(self.decision_cutoff, "decision_cutoff")
        cutoff = _instant(self.decision_cutoff)
        if any(_instant(fact.retrieved_at) > cutoff for fact in self.facts):
            raise TraceValidationError("replay selection contains evidence retrieved after decision_cutoff")


class PointInTimeReplay:
    """Select only records that the system had retrieved by the decision cutoff."""

    @staticmethod
    def select_facts(facts: Iterable[FactEnvelope], decision_cutoff: str) -> ReplaySelection:
        require_iso_datetime(decision_cutoff, "decision_cutoff")
        cutoff = _instant(decision_cutoff)
        eligible: list[FactEnvelope] = []
        excluded: list[str] = []
        for fact in facts:
            if _instant(fact.retrieved_at) <= cutoff:
                eligible.append(fact)
            else:
                excluded.append(fact.fact_id)
        eligible.sort(key=lambda item: (_instant(item.retrieved_at), item.fact_id))
        return ReplaySelection(decision_cutoff, tuple(eligible), tuple(sorted(excluded)))

    @staticmethod
    def select_records(
        records: Iterable[T], decision_cutoff: str, *, retrieved_at: Callable[[T], str]
    ) -> tuple[T, ...]:
        require_iso_datetime(decision_cutoff, "decision_cutoff")
        cutoff = _instant(decision_cutoff)
        selected = [record for record in records if _instant(retrieved_at(record)) <= cutoff]
        return tuple(sorted(selected, key=lambda record: _instant(retrieved_at(record))))
