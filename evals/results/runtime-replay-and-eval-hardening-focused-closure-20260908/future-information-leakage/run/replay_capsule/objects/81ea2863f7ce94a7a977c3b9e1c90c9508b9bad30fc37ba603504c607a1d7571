"""Versioned model routing and LLM-cost policy validation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


POLICY_VERSION = "model-routing-policy/1.0.0"
ROUTES = {"development_default", "runtime_repeated", "architecture_dispute"}


def load_model_routing(product_root: Path) -> dict[str, Any]:
    value = json.loads((product_root / "model-routing.json").read_text(encoding="utf-8"))
    if not isinstance(value, Mapping) or value.get("schema_version") != POLICY_VERSION:
        raise ValueError("MODEL_ROUTE_INVALID:policy")
    if any(not isinstance(value.get(route), str) or not value[route] for route in ROUTES):
        raise ValueError("MODEL_ROUTE_INVALID:route")
    if value["development_default"] != "gpt-5.6-sol" or value["runtime_repeated"] != "gpt-5.6-terra":
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
