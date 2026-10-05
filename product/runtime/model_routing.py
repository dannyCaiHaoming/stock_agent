"""Versioned model routing and LLM-cost policy validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


POLICY_VERSION = "model-routing-policy/1.1.0"
ROUTES = {"development_default", "runtime_repeated", "architecture_dispute"}
AGENT_DEVELOPMENT_TEST_MODEL = "gpt-6-luna"
DEFAULT_GRADER_MODEL = AGENT_DEVELOPMENT_TEST_MODEL
LEGACY_GRADER_MODEL = "gpt-5.6-terra"


def eval_model_from_manifest(manifest: Mapping[str, Any]) -> str:
    """Frozen new-job model; absent field retains the historical Terra contract."""
    if manifest.get("schema_version") == "runtime-eval-input/1.1.0" and "grader_model" not in manifest:
        raise ValueError("MODEL_ROUTE_INVALID:eval-grader-lock-missing")
    model = manifest.get("grader_model", LEGACY_GRADER_MODEL)
    if not isinstance(model, str) or model not in {DEFAULT_GRADER_MODEL, LEGACY_GRADER_MODEL}:
        raise ValueError("MODEL_ROUTE_INVALID:eval-grader-lock")
    return str(model)


def agent_development_test_model() -> str:
    """Repository-pinned model for real product-Agent development tests."""

    return AGENT_DEVELOPMENT_TEST_MODEL


def load_model_routing(product_root: Path) -> dict[str, Any]:
    value = json.loads((product_root / "model-routing.json").read_text(encoding="utf-8"))
    if not isinstance(value, Mapping) or value.get("schema_version") != POLICY_VERSION:
        raise ValueError("MODEL_ROUTE_INVALID:policy")
    if any(not isinstance(value.get(route), str) or not value[route] for route in ROUTES):
        raise ValueError("MODEL_ROUTE_INVALID:route")
    if value["development_default"] != "gpt-5.6-sol" or value["runtime_repeated"] != AGENT_DEVELOPMENT_TEST_MODEL:
        raise ValueError("MODEL_ROUTE_INVALID:required-models")
    if value["architecture_dispute"] != "gpt-6-astra":
        raise ValueError("MODEL_ROUTE_INVALID:architecture-model")
    required = value.get("architecture_dispute_requires")
    if required != ["dispute_id", "human_approval_artifact"]:
        raise ValueError("MODEL_ROUTE_INVALID:astra-controls")
    return dict(value)


def select_model(
    product_root: Path,
    *,
    route: str,
    dispute_id: str | None = None,
    human_approval_artifact: Path | None = None,
) -> str:
    policy = load_model_routing(product_root)
    if route not in ROUTES:
        raise ValueError(f"MODEL_ROUTE_INVALID:{route}")
    if route == "architecture_dispute":
        if not dispute_id or human_approval_artifact is None or not human_approval_artifact.is_file():
            raise ValueError("ASTRA_APPROVAL_MISSING")
    return str(policy[route])


def select_product_runtime_model(
    product_root: Path, *, requested_model: str | None,
    default_route: str = "runtime_repeated",
) -> str:
    """Resolve an explicit product-run model without changing global routing policy."""

    policy = load_model_routing(product_root)
    if requested_model is None:
        return select_model(product_root, route=default_route)
    supported = {str(policy[route]) for route in ROUTES}
    supported.update({AGENT_DEVELOPMENT_TEST_MODEL, LEGACY_GRADER_MODEL})
    # Explicit historical consumption is supported; Terra is never a new default.
    if requested_model not in supported:
        raise ValueError(f"PRODUCT_RUNTIME_MODEL_UNSUPPORTED:{requested_model}")
    return requested_model
