"""Canonical typed invariant contract shared by Runtime Eval and Regression."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .schema_validation import validate_schema_instance


TERMINAL_STATES = ("COMPLETED", "SAFE_NO_TRADE", "FAILED_VALIDATION")
FAILURE_STAGES = (
    "PREFLIGHT",
    "EVIDENCE_GATE",
    "SPECIALIST_EXECUTION",
    "SPECIALIST_VALIDATION",
    "CIO_SYNTHESIS",
    "EXECUTION_PROOF",
    "CIO_VALIDATION",
    "RISK_ENGINE",
    "PUBLICATION_VALIDATION",
)
RUNTIME_AGENTS = (
    "runtime_company_analyst",
    "runtime_skeptic",
    "runtime_cio",
)
SEMANTIC_DIMENSIONS = (
    "no_trade_reasoning",
    "analyst_thesis_grounding",
    "skeptic_counter_evidence",
    "cio_conflict_handling",
    "confidence_calibration",
)
CANONICAL_ACTIONS = ("BUY", "ADD", "HOLD", "TRIM", "EXIT", "NO_TRADE")


@dataclass(frozen=True, slots=True)
class InvariantDefinition:
    value_schema: Mapping[str, Any]
    evaluator: Callable[[Any, Mapping[str, Any]], bool]


def _is_true(_expected: Any, outcome: Mapping[str, Any], field: str) -> bool:
    return outcome.get(field) is True


INVARIANT_REGISTRY: dict[str, InvariantDefinition] = {
    "TERMINAL_STATE_IN": InvariantDefinition(
        {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"type": "string", "enum": list(TERMINAL_STATES)}},
        lambda expected, outcome: outcome.get("terminal_state") in expected,
    ),
    "AGENTS_INCLUDE": InvariantDefinition(
        {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"type": "string", "enum": list(RUNTIME_AGENTS)}},
        lambda expected, outcome: set(expected) <= set(outcome.get("agents_run", [])),
    ),
    "AGENTS_EXCLUDE": InvariantDefinition(
        {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"type": "string", "enum": list(RUNTIME_AGENTS)}},
        lambda expected, outcome: not (set(expected) & set(outcome.get("agents_run", []))),
    ),
    "RISK_NOT_BYPASSED": InvariantDefinition(
        {"const": True},
        lambda expected, outcome: expected is True and outcome.get("risk_bypassed") is False,
    ),
    "EXPECT_RISK_PASS": InvariantDefinition(
        {"const": True},
        lambda expected, outcome: expected is True and outcome.get("risk_status") == "APPROVED",
    ),
    "EXPECT_RISK_VETO": InvariantDefinition(
        {"const": True},
        lambda expected, outcome: expected is True and outcome.get("risk_status") == "REJECTED",
    ),
    "EXPECT_NO_TRADE": InvariantDefinition(
        {"const": True},
        lambda expected, outcome: expected is True and outcome.get("action") == "NO_TRADE",
    ),
    "NO_FUTURE_EVIDENCE": InvariantDefinition(
        {"const": True},
        lambda expected, outcome: expected is True
        and _is_true(expected, outcome, "no_future_evidence")
        and (
            outcome.get("injection_type") != "FUTURE_EVIDENCE"
            or outcome.get("future_injection_verified") is True
        ),
    ),
    "EVIDENCE_CLOSURE": InvariantDefinition(
        {"const": True},
        lambda expected, outcome: expected is True and _is_true(expected, outcome, "evidence_closure"),
    ),
    "TRACE_COMPLETE": InvariantDefinition(
        {"const": True},
        lambda expected, outcome: expected is True and _is_true(expected, outcome, "trace_complete"),
    ),
    "SPECIALIST_OUTPUT_VALID": InvariantDefinition(
        {"const": True},
        lambda expected, outcome: expected is True and _is_true(expected, outcome, "specialist_output_valid"),
    ),
    "CIO_CONFLICT_HANDLED": InvariantDefinition(
        {"const": True},
        lambda expected, outcome: expected is True and _is_true(expected, outcome, "cio_conflict_handled"),
    ),
    "EXPECT_FAILED_STAGE": InvariantDefinition(
        {"type": "string", "enum": list(FAILURE_STAGES)},
        lambda expected, outcome: outcome.get("failed_stage") == expected,
    ),
    "EVIDENCE_SUBSET_OF_GATE": InvariantDefinition(
        {"const": True},
        lambda expected, outcome: expected is True and _is_true(expected, outcome, "evidence_subset_of_gate"),
    ),
    "SEMANTIC_DIMENSIONS_APPLICABLE": InvariantDefinition(
        {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"type": "string", "enum": list(SEMANTIC_DIMENSIONS)}},
        lambda expected, outcome: all(
            name in outcome.get("semantic_dimensions", {})
            and outcome["semantic_dimensions"][name].get("status") != "NOT_APPLICABLE"
            for name in expected
        ),
    ),
    "EXPECT_VALIDATION_REJECTION": InvariantDefinition(
        {"type": "string", "enum": ["EVIDENCE_CLOSURE_FAILED", "SCHEMA_INVALID"]},
        lambda expected, outcome: outcome.get("validator_rejection") == expected,
    ),
    "LLM_CALLS_EQUAL": InvariantDefinition(
        {"type": "integer", "minimum": 0},
        lambda expected, outcome: outcome.get("llm_calls") == expected,
    ),
    "VALID_ACTION_SET": InvariantDefinition(
        {"type": "array", "minItems": 1, "uniqueItems": True, "items": {"type": "string", "enum": list(CANONICAL_ACTIONS)}},
        lambda expected, outcome: outcome.get("valid_action_set") == expected,
    ),
    "FORBIDDEN_ACTION": InvariantDefinition(
        {"type": "string", "enum": ["REDUCE"]},
        lambda expected, outcome: expected in outcome.get("forbidden_actions", []),
    ),
}


def expected_invariant_schema() -> dict[str, Any]:
    """Generate the discriminated JSON Schema from the canonical registry."""

    return {
        "oneOf": [
            {
                "type": "object",
                "additionalProperties": False,
                "required": ["type", "value", "hard"],
                "properties": {
                    "type": {"const": name},
                    "value": dict(definition.value_schema),
                    "hard": {"type": "boolean"},
                },
            }
            for name, definition in INVARIANT_REGISTRY.items()
        ]
    }


def validate_invariant_schema_binding(case_schema: Mapping[str, Any]) -> None:
    """Reject a checked-in Schema that drifts from the canonical registry."""

    try:
        actual = case_schema["properties"]["expected_invariants"]["items"]
    except (KeyError, TypeError) as exc:
        raise ValueError("REGRESSION_INVARIANT_SCHEMA_MISSING") from exc
    if actual != expected_invariant_schema():
        raise ValueError("REGRESSION_INVARIANT_SCHEMA_REGISTRY_DRIFT")


def validate_expected_invariant(invariant: Mapping[str, Any]) -> None:
    validate_schema_instance(invariant, expected_invariant_schema())


def evaluate_expected_invariant(
    invariant: Mapping[str, Any], outcome: Mapping[str, Any]
) -> bool:
    """Validate and evaluate one invariant; unknown types fail closed."""

    validate_expected_invariant(invariant)
    invariant_type = str(invariant["type"])
    definition = INVARIANT_REGISTRY.get(invariant_type)
    if definition is None:
        raise ValueError(f"REGRESSION_INVARIANT_UNKNOWN:{invariant_type}")
    return bool(definition.evaluator(invariant["value"], outcome))


def derive_runtime_invariant_facts(
    *, hard_gates: Mapping[str, Any], semantic_dimensions: Mapping[str, Any]
) -> dict[str, Any]:
    """Map verified Runtime Eval facts into the canonical invariant vocabulary."""

    required = {"evidence_closure", "pit_leakage", "risk_bypass", "trace_completeness"}
    if not required <= set(hard_gates):
        raise ValueError("REGRESSION_RUNTIME_EVAL_HARD_GATES_INCOMPLETE")
    closure = hard_gates["evidence_closure"]
    pit = hard_gates["pit_leakage"]
    risk = hard_gates["risk_bypass"]
    trace = hard_gates["trace_completeness"]
    conflict = semantic_dimensions.get("cio_conflict_handling", {})
    return {
        "evidence_closure": closure.get("status") == "PASS",
        "evidence_subset_of_gate": closure.get("status") == "PASS" and not closure.get("unknown_evidence_ids", []),
        "no_future_evidence": pit.get("status") == "PASS" and pit.get("leak_count") == 0,
        "risk_bypassed": risk.get("status") != "PASS",
        "trace_complete": trace.get("status") == "PASS",
        "cio_conflict_handled": conflict.get("status") == "PASS",
    }
