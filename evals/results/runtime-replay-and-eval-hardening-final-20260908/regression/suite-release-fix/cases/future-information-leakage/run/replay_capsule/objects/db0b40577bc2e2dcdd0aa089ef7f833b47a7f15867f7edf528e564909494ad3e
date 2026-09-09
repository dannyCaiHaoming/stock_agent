"""Canonical structural contract for CIO decisions.

This module interprets machine-checkable fields only. It never selects an
investment action or assigns thesis/confidence content.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .hashing import canonical_hash


CONTRACT_VERSION = "council-decision-contract/1.0.0"
DECISION_SCHEMA_VERSION = "cio-decision-draft/2.1.0"
SUPPORTED_CONSTRAINTS = {
    "const",
    "non_null",
    "non_empty_string",
    "non_empty_array",
}


class DecisionContractError(ValueError):
    """Raised when the canonical contract or a decision violates structure."""


def contract_path(product_root: Path) -> Path:
    return product_root.resolve() / "contracts" / "council-decision-contract.json"


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise DecisionContractError(
            f"{name}_KEYS_INVALID:missing={sorted(expected - value.keys())},"
            f"extra={sorted(value.keys() - expected)}"
        )


def validate_contract(value: Mapping[str, Any]) -> dict[str, Any]:
    contract = dict(value)
    _require_exact_keys(
        contract,
        {
            "schema_version",
            "decision_schema_version",
            "actions",
            "action_profiles",
            "prompt_examples",
        },
        "DECISION_CONTRACT",
    )
    if contract["schema_version"] != CONTRACT_VERSION:
        raise DecisionContractError("DECISION_CONTRACT_VERSION_INVALID")
    if contract["decision_schema_version"] != DECISION_SCHEMA_VERSION:
        raise DecisionContractError("DECISION_SCHEMA_VERSION_INVALID")
    actions = contract["actions"]
    if not isinstance(actions, list) or not actions or len(set(actions)) != len(actions):
        raise DecisionContractError("DECISION_ACTIONS_INVALID")
    if any(not isinstance(action, str) or not action for action in actions):
        raise DecisionContractError("DECISION_ACTIONS_INVALID")

    covered: list[str] = []
    profiles = contract["action_profiles"]
    if not isinstance(profiles, list) or not profiles:
        raise DecisionContractError("DECISION_ACTION_PROFILES_INVALID")
    for profile in profiles:
        if not isinstance(profile, Mapping):
            raise DecisionContractError("DECISION_ACTION_PROFILE_INVALID")
        _require_exact_keys(
            profile, {"profile_id", "actions", "constraints"}, "ACTION_PROFILE"
        )
        if not isinstance(profile["profile_id"], str) or not profile["profile_id"]:
            raise DecisionContractError("ACTION_PROFILE_ID_INVALID")
        profile_actions = profile["actions"]
        if not isinstance(profile_actions, list) or not profile_actions:
            raise DecisionContractError("ACTION_PROFILE_ACTIONS_INVALID")
        covered.extend(profile_actions)
        constraints = profile["constraints"]
        if not isinstance(constraints, list) or not constraints:
            raise DecisionContractError("ACTION_PROFILE_CONSTRAINTS_INVALID")
        for constraint in constraints:
            if not isinstance(constraint, Mapping):
                raise DecisionContractError("ACTION_CONSTRAINT_INVALID")
            _require_exact_keys(
                constraint, {"rule_code", "fields"}, "ACTION_CONSTRAINT"
            )
            if (
                not isinstance(constraint["rule_code"], str)
                or not constraint["rule_code"]
                or not isinstance(constraint["fields"], Mapping)
                or not constraint["fields"]
            ):
                raise DecisionContractError("ACTION_CONSTRAINT_INVALID")
            for field, rule in constraint["fields"].items():
                if not isinstance(field, str) or not isinstance(rule, Mapping):
                    raise DecisionContractError("ACTION_FIELD_CONSTRAINT_INVALID")
                kind = rule.get("kind")
                expected_keys = {"kind", "value"} if kind == "const" else {"kind"}
                _require_exact_keys(rule, expected_keys, "ACTION_FIELD_CONSTRAINT")
                if kind not in SUPPORTED_CONSTRAINTS:
                    raise DecisionContractError("ACTION_CONSTRAINT_KIND_INVALID")
    if sorted(covered) != sorted(actions) or len(covered) != len(set(covered)):
        raise DecisionContractError("ACTION_PROFILE_COVERAGE_INVALID")

    examples = contract["prompt_examples"]
    if not isinstance(examples, list) or len(examples) < 3:
        raise DecisionContractError("DECISION_PROMPT_EXAMPLES_INVALID")
    seen_examples: set[str] = set()
    for example in examples:
        if not isinstance(example, Mapping):
            raise DecisionContractError("DECISION_PROMPT_EXAMPLE_INVALID")
        expected = {"example_id", "valid", "value"}
        if example.get("valid") is False:
            expected.add("rule_code")
        _require_exact_keys(example, expected, "DECISION_PROMPT_EXAMPLE")
        example_id = example["example_id"]
        if not isinstance(example_id, str) or not example_id or example_id in seen_examples:
            raise DecisionContractError("DECISION_PROMPT_EXAMPLE_ID_INVALID")
        seen_examples.add(example_id)
        if not isinstance(example["valid"], bool) or not isinstance(
            example["value"], Mapping
        ):
            raise DecisionContractError("DECISION_PROMPT_EXAMPLE_INVALID")
    return contract


def load_decision_contract(product_root: Path) -> dict[str, Any]:
    path = contract_path(product_root)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DecisionContractError("DECISION_CONTRACT_UNREADABLE") from exc
    if not isinstance(value, Mapping):
        raise DecisionContractError("DECISION_CONTRACT_NOT_OBJECT")
    return validate_contract(value)


def decision_contract_hash(contract: Mapping[str, Any]) -> str:
    return canonical_hash(contract)


def _condition_schema(rule: Mapping[str, Any]) -> dict[str, Any]:
    kind = rule["kind"]
    if kind == "const":
        return {"const": rule["value"]}
    if kind == "non_null":
        return {"not": {"type": "null"}}
    if kind == "non_empty_string":
        return {"type": "string", "minLength": 1}
    if kind == "non_empty_array":
        return {"type": "array", "minItems": 1}
    raise DecisionContractError("ACTION_CONSTRAINT_KIND_INVALID")


def derive_action_schema_conditions(
    contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    checked = validate_contract(contract)
    conditions: list[dict[str, Any]] = []
    for profile in checked["action_profiles"]:
        then_rules = [
            {
                "properties": {
                    field: _condition_schema(rule)
                    for field, rule in constraint["fields"].items()
                }
            }
            for constraint in profile["constraints"]
        ]
        conditions.append(
            {
                "if": {
                    "properties": {"action": {"enum": profile["actions"]}},
                    "required": ["action"],
                },
                "then": {"allOf": then_rules},
            }
        )
    return conditions


def generated_schema_metadata(contract: Mapping[str, Any]) -> dict[str, str]:
    checked = validate_contract(contract)
    return {
        "contract": "contracts/council-decision-contract.json",
        "contract_version": checked["schema_version"],
        "contract_hash": decision_contract_hash(checked),
    }


def verify_cio_schema(product_root: Path, contract: Mapping[str, Any]) -> None:
    schema_path = product_root.resolve() / "schemas" / "runtime" / "cio-decision-draft.schema.json"
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DecisionContractError("CIO_SCHEMA_UNREADABLE") from exc
    if not isinstance(schema, Mapping):
        raise DecisionContractError("CIO_SCHEMA_NOT_OBJECT")
    if schema.get("$id") != f"portfolio-council/{contract['decision_schema_version']}":
        raise DecisionContractError("CIO_SCHEMA_ID_DRIFT")
    if schema.get("x-generated-from") != generated_schema_metadata(contract):
        raise DecisionContractError("CIO_SCHEMA_CONTRACT_METADATA_DRIFT")
    if schema.get("allOf") != derive_action_schema_conditions(contract):
        raise DecisionContractError("CIO_SCHEMA_ACTION_CONDITIONS_DRIFT")


def _constraint_satisfied(value: Any, rule: Mapping[str, Any]) -> bool:
    kind = rule["kind"]
    if kind == "const":
        return value == rule["value"] and type(value) is type(rule["value"])
    if kind == "non_null":
        return value is not None
    if kind == "non_empty_string":
        return isinstance(value, str) and bool(value.strip())
    if kind == "non_empty_array":
        return isinstance(value, list) and bool(value)
    raise DecisionContractError("ACTION_CONSTRAINT_KIND_INVALID")


def validate_decision_action(
    value: Mapping[str, Any], contract: Mapping[str, Any]
) -> None:
    checked = validate_contract(contract)
    action = value.get("action")
    if action not in checked["actions"]:
        raise DecisionContractError("INVALID_ACTION")
    profile = next(
        item for item in checked["action_profiles"] if action in item["actions"]
    )
    for constraint in profile["constraints"]:
        if any(
            not _constraint_satisfied(value.get(field), rule)
            for field, rule in constraint["fields"].items()
        ):
            raise DecisionContractError(str(constraint["rule_code"]))


def render_cio_action_prompt(contract: Mapping[str, Any]) -> str:
    checked = validate_contract(contract)
    lines = [
        f"必须遵守 canonical decision contract `{checked['schema_version']}`。",
        "当 action == NO_TRADE 时，target_weight_range 和 maximum_notional 必须都是 JSON null；数值 0 不等于 JSON null。",
        "以下示例由 canonical contract 生成：",
    ]
    for example in checked["prompt_examples"]:
        label = "合法" if example["valid"] else f"非法（{example['rule_code']}）"
        rendered = json.dumps(example["value"], ensure_ascii=False, sort_keys=True)
        lines.append(f"- {label} `{example['example_id']}`: {rendered}")
    return "\n".join(lines)


def contract_record(product_root: Path) -> dict[str, str]:
    contract = load_decision_contract(product_root)
    return {
        "version": str(contract["schema_version"]),
        "path": str(contract_path(product_root)),
        "sha256": decision_contract_hash(contract),
    }


def validate_no_investment_policy_keys(value: Any) -> None:
    """Guard that the contract stays structural rather than choosing outcomes."""

    forbidden = {
        "confidence_threshold",
        "preferred_action",
        "recommended_action",
        "thesis_template",
        "investment_score",
    }

    def walk(item: Any) -> None:
        if isinstance(item, Mapping):
            overlap = forbidden & {str(key) for key in item}
            if overlap:
                raise DecisionContractError(
                    f"INVESTMENT_POLICY_KEY_FORBIDDEN:{','.join(sorted(overlap))}"
                )
            for child in item.values():
                walk(child)
        elif isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            for child in item:
                walk(child)

    walk(value)
