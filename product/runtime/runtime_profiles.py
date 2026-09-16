"""Product and evaluation-only Council topology contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


PRODUCT_AGENTS = ("runtime_company_analyst", "runtime_skeptic", "runtime_cio")
LIVE_PROFILE_ID = "live-us-equity/4.0.0"
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


def load_source_profile(repository_root: Path, profile: str = "fixture") -> dict[str, Any]:
    """显式来源选择；未知名称不得退回 fixture 或跳过 live 检查。"""
    product_root = repository_root.resolve() / "product"
    if profile == "fixture":
        value = json.loads((product_root / "runtime-profile.json").read_text(encoding="utf-8"))
        if value.get("profile_id") != "fixture-council/3.1.0":
            raise ValueError("FIXTURE_SOURCE_PROFILE_INVALID")
        return value
    if profile != "live-us-equity":
        raise ValueError("UNKNOWN_SOURCE_PROFILE")
    value = json.loads((product_root / "profiles/live-us-equity.json").read_text(encoding="utf-8"))
    if (value.get("profile_id") != LIVE_PROFILE_ID or value.get("source_mode") != "live"
            or value.get("providers") != ["nasdaq", "yahoo", "eastmoney", "sec"]
            or value.get("allowed_actions") != ["HOLD", "TRIM", "EXIT", "NO_TRADE"]
            or value.get("parallel_first_pass") != list(PRODUCT_AGENTS[:2])
            or set(value.get("agents", {})) != set(PRODUCT_AGENTS)
            or value.get("max_positions") != 3 or value.get("base_currency") != "USD"):
        raise ValueError("LIVE_SOURCE_PROFILE_INVALID")
    expected_skills = {
        "runtime_company_analyst": ["evidence-grounding", "company-research", "valuation", "catalyst-analysis"],
        "runtime_skeptic": ["evidence-grounding", "counter-thesis"], "runtime_cio": ["portfolio-council"]}
    for name, agent in value["agents"].items():
        expected_tools = ["live_evidence.query", "live_math.calculate"] if name == "runtime_company_analyst" else ["live_evidence.query"]
        if (agent.get("config_file") != f".codex/agents/{name}.toml"
                or agent.get("skills") != expected_skills[name] or agent.get("tool_permissions") != expected_tools):
            raise ValueError("LIVE_AGENT_PROFILE_INVALID")
    schema_files = {kind: f"schemas/runtime/live-{kind}.schema.json"
                    for kind in ("portfolio", "fact", "fact-v2", "universe", "source-selection", "batch")}
    schema_files.update({"source-access": "schemas/runtime/live-source-access-v4.schema.json",
                         "snapshot": "schemas/runtime/live-snapshot-v4.schema.json"})
    if value.get("schema_files") != schema_files:
        raise ValueError("LIVE_SCHEMA_PROFILE_INVALID")
    return value
