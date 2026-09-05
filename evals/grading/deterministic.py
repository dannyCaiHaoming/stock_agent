"""Repeatable hard gates for deterministic product invariants."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class DeterministicGateInput:
    schema_valid: bool
    portfolio_math_valid: bool
    risk_constraints_valid: bool
    freshness_valid: bool
    conflicts_detected_and_preserved: bool
    evidence_closure_valid: bool


@dataclass(frozen=True, slots=True)
class GateCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class DeterministicGateReport:
    checks: tuple[GateCheck, ...]
    fingerprint: str

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def failed_gate_names(self) -> tuple[str, ...]:
        return tuple(check.name for check in self.checks if not check.passed)


class DeterministicGateSuite:
    """Converts upstream deterministic checks into one non-bypassable result."""

    _FIELDS: tuple[tuple[str, str], ...] = (
        ("schema_valid", "schema"),
        ("portfolio_math_valid", "portfolio_math"),
        ("risk_constraints_valid", "risk_engine"),
        ("freshness_valid", "freshness"),
        ("conflicts_detected_and_preserved", "conflict_detection"),
        ("evidence_closure_valid", "evidence_closure"),
    )

    @classmethod
    def evaluate(
        cls,
        inputs: DeterministicGateInput,
        *,
        details: Mapping[str, str] | None = None,
    ) -> DeterministicGateReport:
        detail_map = dict(details or {})
        checks = tuple(
            GateCheck(
                name=gate_name,
                passed=bool(getattr(inputs, field_name)),
                detail=detail_map.get(gate_name, "passed" if getattr(inputs, field_name) else "failed"),
            )
            for field_name, gate_name in cls._FIELDS
        )
        canonical = json.dumps(
            [(check.name, check.passed, check.detail) for check in checks],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        fingerprint = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        return DeterministicGateReport(checks=checks, fingerprint=fingerprint)
