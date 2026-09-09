"""Deterministic fixture adapter for contract tests and offline evaluation."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Final

from .provenance import FactEnvelope, content_hash, normalize_fact


ADAPTER_VERSION: Final[str] = "reference/1.0.0"


def _raw(
    field: str,
    value: object,
    *,
    source_id: str,
    as_of: str,
    retrieved_at: str,
    source_version: str = "1",
    unit: str | None = None,
    currency: str | None = None,
    source_type: str = "fixture",
) -> dict[str, object]:
    return {
        "security_id": "SEC-AAA",
        "semantic_field": field,
        "value": value,
        "value_type": "number" if isinstance(value, (int, float)) else "string",
        "unit": unit,
        "currency": currency,
        "source_timezone": "America/New_York",
        "source_id": source_id,
        "source_type": source_type,
        "source_locator": f"fixture://{source_id}/{field}/{source_version}",
        "source_version": source_version,
        "as_of": as_of,
        "retrieved_at": retrieved_at,
    }


_BASE_PRICE = _raw(
    "close_price",
    100.0,
    source_id="fixture-market-a",
    as_of="2026-01-02T21:00:00Z",
    retrieved_at="2026-01-02T21:05:00Z",
    unit="per_share",
    currency="USD",
)
_BASE_REVENUE = _raw(
    "revenue_ttm",
    1_000_000,
    source_id="fixture-fundamentals-a",
    as_of="2025-12-31T00:00:00Z",
    retrieved_at="2026-01-15T13:00:00Z",
    unit="currency",
    currency="USD",
)


class ReferenceAdapter:
    """A provider-neutral adapter whose outputs are stable across runs."""

    version = ADAPTER_VERSION
    scenarios: Final[tuple[str, ...]] = (
        "normal",
        "stale",
        "missing",
        "conflict",
        "revision",
    )

    def _rows(self, scenario: str) -> tuple[dict[str, object], ...]:
        if scenario not in self.scenarios:
            raise KeyError(f"unknown fixture scenario: {scenario}")
        if scenario == "normal":
            return (dict(_BASE_PRICE), dict(_BASE_REVENUE))
        if scenario == "stale":
            stale = dict(_BASE_PRICE)
            stale.update(
                as_of="2025-01-02T21:00:00Z",
                retrieved_at="2025-01-02T21:05:00Z",
            )
            return (stale, dict(_BASE_REVENUE))
        if scenario == "missing":
            return (dict(_BASE_PRICE),)
        if scenario == "conflict":
            conflicting = _raw(
                "revenue_ttm",
                1_250_000,
                source_id="fixture-fundamentals-b",
                as_of="2025-12-31T00:00:00Z",
                retrieved_at="2026-01-15T14:00:00Z",
                unit="currency",
                currency="USD",
            )
            return (dict(_BASE_REVENUE), conflicting)
        original = dict(_BASE_REVENUE)
        revised = _raw(
            "revenue_ttm",
            980_000,
            source_id="fixture-fundamentals-a",
            as_of="2025-12-31T00:00:00Z",
            retrieved_at="2026-02-01T13:00:00Z",
            source_version="2",
            unit="currency",
            currency="USD",
        )
        return (original, revised)

    def facts(self, scenario: str) -> tuple[FactEnvelope, ...]:
        facts = tuple(
            normalize_fact(row, adapter_version=self.version) for row in self._rows(scenario)
        )
        return tuple(sorted(facts, key=lambda fact: (fact.retrieved_at, fact.fact_id)))

    def evidence_artifact(self, scenario: str) -> dict[str, Any]:
        facts = self.facts(scenario)
        missing_fields = ("revenue_ttm",) if scenario == "missing" else ()
        body = {
            "adapter_version": self.version,
            "scenario": scenario,
            "facts": [asdict(fact) for fact in facts],
            "missing_fields": list(missing_fields),
        }
        return {
            "artifact_id": f"evidence_{content_hash(body)[:24]}",
            **body,
        }
