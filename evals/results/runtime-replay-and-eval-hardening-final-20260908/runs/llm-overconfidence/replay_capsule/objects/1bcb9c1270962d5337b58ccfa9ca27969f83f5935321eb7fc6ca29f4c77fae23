"""Deterministic point-in-time gate for versioned fixture evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.mcp.provenance import canonical_json, content_hash, parse_timestamp


GATE_SCHEMA_VERSION = "evidence-gate/2.0.0"
REQUIRED_FACT_FIELDS = (
    "evidence_id",
    "security_id",
    "semantic_field",
    "value",
    "unit",
    "source_id",
    "source_type",
    "source_locator",
    "source_version",
    "as_of",
    "retrieved_at",
)


class FixtureValidationError(ValueError):
    """The fixture cannot safely enter the product runtime."""


@dataclass(frozen=True, slots=True)
class GateResult:
    artifact: dict[str, Any]

    @property
    def allowed_ids(self) -> tuple[str, ...]:
        return tuple(self.artifact["allowed_evidence_ids"])

    @property
    def excluded_ids(self) -> tuple[str, ...]:
        return tuple(item["evidence_id"] for item in self.artifact["excluded"])


def load_fixture(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise FixtureValidationError("fixture must be a JSON object")
    fixture = dict(value)
    validate_fixture(fixture)
    return fixture


def validate_fixture(fixture: Mapping[str, Any]) -> None:
    required = {
        "fixture_version",
        "fixture_id",
        "scenario_type",
        "decision_cutoff",
        "freshness_policy",
        "conflict_policy_version",
        "portfolio",
        "evidence",
    }
    missing = sorted(required - fixture.keys())
    if missing:
        raise FixtureValidationError(f"fixture missing fields: {','.join(missing)}")
    parse_timestamp(str(fixture["decision_cutoff"]))

    portfolio = fixture["portfolio"]
    if not isinstance(portfolio, Mapping):
        raise FixtureValidationError("portfolio must be an object")
    if not isinstance(portfolio.get("cash"), (int, float)) or portfolio["cash"] < 0:
        raise FixtureValidationError("portfolio cash must be non-negative")
    positions = portfolio.get("positions")
    if not isinstance(positions, list) or not positions:
        raise FixtureValidationError("portfolio positions must be non-empty")
    for position in positions:
        if not isinstance(position, Mapping):
            raise FixtureValidationError("portfolio position must be an object")
        if not position.get("security_id"):
            raise FixtureValidationError("portfolio position requires security_id")
        if not isinstance(position.get("quantity"), (int, float)) or position["quantity"] <= 0:
            raise FixtureValidationError("portfolio position quantity must be positive")

    policy = fixture["freshness_policy"]
    if not isinstance(policy, Mapping) or not policy.get("version"):
        raise FixtureValidationError("freshness_policy requires version")
    default_days = policy.get("default_max_age_days")
    if not isinstance(default_days, int) or default_days < 0:
        raise FixtureValidationError("default_max_age_days must be non-negative integer")
    field_days = policy.get("field_max_age_days", {})
    if not isinstance(field_days, Mapping) or any(
        not isinstance(value, int) or value < 0 for value in field_days.values()
    ):
        raise FixtureValidationError("field_max_age_days values must be non-negative integers")

    evidence = fixture["evidence"]
    if not isinstance(evidence, list) or not evidence:
        raise FixtureValidationError("fixture evidence must be non-empty")
    identifiers: set[str] = set()
    for index, fact in enumerate(evidence):
        if not isinstance(fact, Mapping):
            raise FixtureValidationError(f"evidence[{index}] must be an object")
        absent = [field for field in REQUIRED_FACT_FIELDS if fact.get(field) is None]
        if absent:
            raise FixtureValidationError(
                f"evidence[{index}] missing provenance: {','.join(absent)}"
            )
        evidence_id = str(fact["evidence_id"])
        if evidence_id in identifiers:
            raise FixtureValidationError(f"duplicate evidence_id: {evidence_id}")
        identifiers.add(evidence_id)
        as_of = parse_timestamp(str(fact["as_of"]))
        retrieved_at = parse_timestamp(str(fact["retrieved_at"]))
        if retrieved_at < as_of:
            raise FixtureValidationError(
                f"retrieved_at precedes as_of for {evidence_id}"
            )


def _conflict_key(fact: Mapping[str, Any]) -> str:
    components = (
        str(fact["security_id"]).strip().casefold(),
        str(fact["semantic_field"]).strip().casefold(),
        parse_timestamp(str(fact["as_of"])).isoformat(),
    )
    return "|".join(components)


def _fact_signature(fact: Mapping[str, Any]) -> str:
    return canonical_json(
        {
            "value": fact["value"],
            "unit": fact["unit"],
            "currency": fact.get("currency"),
        }
    )


def _detect_conflicts(facts: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for fact in facts:
        grouped.setdefault(_conflict_key(fact), []).append(fact)
    conflicts: list[dict[str, Any]] = []
    for key, candidates in sorted(grouped.items()):
        if len({_fact_signature(fact) for fact in candidates}) <= 1:
            continue
        conflicts.append(
            {
                "conflict_key": key,
                "reason_code": "INCOMPATIBLE_NORMALIZED_VALUES",
                "evidence_ids": sorted(str(fact["evidence_id"]) for fact in candidates),
                "source_ids": sorted(str(fact["source_id"]) for fact in candidates),
                "observations": sorted(
                    (
                        {
                            "evidence_id": str(fact["evidence_id"]),
                            "source_id": str(fact["source_id"]),
                            "value": fact["value"],
                            "unit": fact["unit"],
                            "currency": fact.get("currency"),
                        }
                        for fact in candidates
                    ),
                    key=lambda item: item["evidence_id"],
                ),
            }
        )
    return conflicts


def run_evidence_gate(fixture: Mapping[str, Any], *, run_id: str) -> GateResult:
    validate_fixture(fixture)
    cutoff = parse_timestamp(str(fixture["decision_cutoff"]))
    policy = fixture["freshness_policy"]
    default_days = int(policy["default_max_age_days"])
    field_days = policy.get("field_max_age_days", {})

    allowed: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for raw_fact in fixture["evidence"]:
        fact = dict(raw_fact)
        reasons: list[str] = []
        as_of = parse_timestamp(str(fact["as_of"]))
        retrieved_at = parse_timestamp(str(fact["retrieved_at"]))
        if as_of > cutoff:
            reasons.append("FUTURE_AS_OF")
        if retrieved_at > cutoff:
            reasons.append("FUTURE_RETRIEVAL")
        threshold_days = int(field_days.get(str(fact["semantic_field"]), default_days))
        age = cutoff - as_of
        if age >= timedelta(0) and age > timedelta(days=threshold_days):
            reasons.append("STALE")
        if reasons:
            excluded.append(
                {
                    "evidence_id": fact["evidence_id"],
                    "reason_codes": reasons,
                    "as_of": fact["as_of"],
                    "retrieved_at": fact["retrieved_at"],
                    "threshold_days": threshold_days,
                }
            )
        else:
            fact["freshness_status"] = "FRESH"
            fact["freshness_policy_version"] = policy["version"]
            allowed.append(fact)

    allowed.sort(key=lambda item: str(item["evidence_id"]))
    excluded.sort(key=lambda item: str(item["evidence_id"]))
    input_ids = sorted(str(item["evidence_id"]) for item in fixture["evidence"])
    body: dict[str, Any] = {
        "schema_version": GATE_SCHEMA_VERSION,
        "run_id": run_id,
        "fixture_id": fixture["fixture_id"],
        "decision_cutoff": fixture["decision_cutoff"],
        "freshness_policy_version": policy["version"],
        "conflict_policy_version": fixture["conflict_policy_version"],
        "input_evidence_ids": input_ids,
        "allowed_evidence_ids": [item["evidence_id"] for item in allowed],
        "excluded_evidence_ids": [item["evidence_id"] for item in excluded],
        "excluded": excluded,
        "conflicts": _detect_conflicts(allowed),
        "allowed_evidence": allowed,
        "input_hash": content_hash(fixture),
    }
    body["bundle_hash"] = content_hash(body)
    return GateResult(body)
