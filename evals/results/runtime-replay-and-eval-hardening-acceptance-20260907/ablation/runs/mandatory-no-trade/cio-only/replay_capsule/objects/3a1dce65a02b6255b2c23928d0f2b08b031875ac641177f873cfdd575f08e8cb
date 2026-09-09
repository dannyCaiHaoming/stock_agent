"""Product and evaluation-only Council topology contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


PRODUCT_AGENTS = ("runtime_company_analyst", "runtime_skeptic", "runtime_cio")
ABLATION_AGENTS = {
    "cio-only": ("runtime_cio",),
    "analyst-cio": ("runtime_company_analyst", "runtime_cio"),
    "full-council": PRODUCT_AGENTS,
}


def validate_runtime_mode(
    *,
    run_mode: str,
    ablation_profile: str | None,
) -> tuple[str, ...]:
    if run_mode == "PRODUCT_COUNCIL":
        if ablation_profile is not None:
            raise ValueError("PRODUCT_PROFILE_CANNOT_USE_ABLATION_TOPOLOGY")
        return PRODUCT_AGENTS
    if run_mode == "EXECUTION_REPLAY":
        if ablation_profile is not None:
            raise ValueError("EXECUTION_REPLAY_CANNOT_USE_ABLATION_TOPOLOGY")
        return PRODUCT_AGENTS
    if run_mode == "EVAL_ABLATION" and ablation_profile in ABLATION_AGENTS:
        return ABLATION_AGENTS[str(ablation_profile)]
    raise ValueError("RUNTIME_PROFILE_INVALID")


def load_ablation_profiles(repository_root: Path) -> dict[str, Any]:
    value = json.loads(
        (repository_root / "evals" / "ablation" / "profiles-v1.json").read_text(encoding="utf-8")
    )
    if not isinstance(value, Mapping) or value.get("schema_version") != "ablation-profiles/1.0.0":
        raise ValueError("ABLATION_PROFILES_INVALID")
    for profile, agents in ABLATION_AGENTS.items():
        record = value.get("profiles", {}).get(profile)
        if not isinstance(record, Mapping) or record.get("publishable") is not False or tuple(record.get("agents", [])) != agents:
            raise ValueError(f"ABLATION_PROFILE_INVALID:{profile}")
    product = value.get("product_profile")
    if not isinstance(product, Mapping) or product.get("publishable") is not True or tuple(product.get("agents", [])) != PRODUCT_AGENTS:
        raise ValueError("PRODUCT_PROFILE_INVALID")
    return dict(value)
