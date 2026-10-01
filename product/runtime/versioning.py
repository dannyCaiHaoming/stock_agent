"""Candidate version-manifest validation."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping


REQUIRED_SCALAR_FIELDS = (
    "manifest_version",
    "candidate_version",
    "codex_runtime",
    "model",
    "runtime_profile",
    "decision_contract",
    "risk_policy",
    "data_snapshot",
)
REQUIRED_MAPPING_FIELDS = (
    "resource_hashes",
    "skills",
    "agents",
    "schemas",
    "mcp_adapters",
    "assurance",
    "assurance_hashes",
)
FORBIDDEN_MODEL_MARKERS = ("fixture-model", "placeholder", "unknown", "mock")

# These are current contract locations, not a registry of historical readers.
# Broad legacy groups (research/decision-risk/etc.) are not concrete Schema IDs.
CURRENT_SCHEMA_FILES = {
    "agent-research-report": "schemas/runtime/agent-research-report.schema.json",
    "cio-decision-draft": "schemas/runtime/cio-decision-draft.schema.json",
    "equity-research-report": "schemas/runtime/equity-research-report.schema.json",
    "research-coverage": "schemas/runtime/research-coverage.schema.json",
    "research-dimension-report": "schemas/runtime/research-dimension-report-v2.schema.json",
    "holding-research-bundle": "schemas/runtime/holding-research-bundle-v2.schema.json",
    "counter-thesis-report": "schemas/runtime/counter-thesis-report-v2.1.schema.json",
    "pre-decision-research-package": "schemas/runtime/pre-decision-research-package.schema.json",
    "predecision-cio-synthesis": "schemas/runtime/predecision-cio-synthesis.schema.json",
    "semantic-rubric-result": "schemas/runtime/semantic-rubric-result.schema.json",
}


def approved_component_version(
    manifest: Mapping[str, Any], category: str, name: str, *, observed: str | None = None
) -> str:
    """Resolve the approved value; reject drift rather than selecting a newer one."""
    versions = manifest.get(category)
    expected = versions.get(name) if isinstance(versions, Mapping) else None
    if not isinstance(expected, str) or not expected:
        raise ValueError(f"COMPONENT_VERSION_UNAPPROVED:{category}:{name}")
    if observed is not None and observed != expected:
        raise ValueError(f"COMPONENT_VERSION_DRIFT:{category}:{name}:{observed}:{expected}")
    return expected


def read_skill_version(path: Path) -> str:
    """Read the one supported metadata.version mirror without parsing the body."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n") or "\n---\n" not in text[4:]:
        raise ValueError(f"SKILL_FRONTMATTER_INVALID:{path}")
    frontmatter = text[4:].split("\n---\n", 1)[0]
    metadata = re.findall(r"(?m)^metadata:\s*\n((?:[ \t]+[^\n]*\n?|\n)*)", frontmatter)
    versions = re.findall(r"(?m)^  version:\s*[\"']?([^\"'\n]+)[\"']?\s*$", metadata[0]) if len(metadata) == 1 else []
    if len(versions) != 1 or not versions[0].strip():
        raise ValueError(f"SKILL_VERSION_INVALID:{path}")
    return versions[0].strip()


def derive_skill_version(manifest: Mapping[str, Any], name: str, path: Path) -> str:
    """Render just the approved metadata mirror; preserve every method/body byte."""
    read_skill_version(path)
    expected = approved_component_version(manifest, "skills", name)
    text = path.read_text(encoding="utf-8")
    frontmatter, body = text[4:].split("\n---\n", 1)
    metadata = re.search(r"(?m)^metadata:\s*\n((?:[ \t]+[^\n]*\n?|\n)*)", frontmatter)
    assert metadata is not None  # The supported frontmatter has been validated.
    start, end = metadata.span(1)
    replacement = re.sub(r"(?m)^  version:[^\n]*", "  version: " + json.dumps(expected),
                         frontmatter[start:end], count=1)
    return "---\n" + frontmatter[:start] + replacement + frontmatter[end:] + "\n---\n" + body


def validate_current_component_versions(
    product_root: Path, manifest: Mapping[str, Any], *,
    skill_names: tuple[str, ...] | None = None,
    schema_names: tuple[str, ...] | None = None,
    adapter_scopes: tuple[str, ...] | None = None,
    check_risk: bool = True,
) -> None:
    """Check actual current declarations before dispatch; this is not load proof."""
    if adapter_scopes is not None and set(adapter_scopes) - {
        "fixture-gate-scoped", "common-stock-field-query", "independent-skeptic-query",
    }:
        raise ValueError("COMPONENT_ADAPTER_SCOPE_UNKNOWN")
    for name in manifest["skills"] if skill_names is None else skill_names:
        approved_component_version(manifest, "skills", name,
                                   observed=read_skill_version(product_root / "skills" / name / "SKILL.md"))
    for name in CURRENT_SCHEMA_FILES if schema_names is None else schema_names:
        if name not in CURRENT_SCHEMA_FILES:
            raise ValueError(f"COMPONENT_SCHEMA_UNMAPPED:{name}")
        relative = CURRENT_SCHEMA_FILES[name]
        schema = json.loads((product_root / relative).read_text(encoding="utf-8"))
        declared = schema.get("properties", {}).get("schema_version", {}).get("const")
        if not isinstance(declared, str) or not declared.startswith(name + "/"):
            raise ValueError(f"COMPONENT_SCHEMA_ID_INVALID:{relative}:{declared}")
        approved_component_version(manifest, "schemas", name, observed=declared[len(name) + 1:])
    # Explicit stage scopes: the highest adapter number is not every stage's API.
    from .fixture_mcp import (
        MCP_ADAPTER_VERSION, COMMON_STOCK_FIELD_QUERY_ADAPTER_VERSION, SKEPTIC_ADAPTER_VERSION,
    )
    for scope, actual in (
        ("fixture-gate-scoped", MCP_ADAPTER_VERSION),
        ("common-stock-field-query", COMMON_STOCK_FIELD_QUERY_ADAPTER_VERSION),
        ("independent-skeptic-query", SKEPTIC_ADAPTER_VERSION),
    ):
        if adapter_scopes is not None and scope not in adapter_scopes:
            continue
        approved_component_version(manifest, "mcp_adapters", scope, observed=actual.rsplit("/", 1)[-1])
    from .risk_runtime import REFERENCE_RISK_POLICY_VERSION
    if check_risk and manifest.get("risk_policy") != REFERENCE_RISK_POLICY_VERSION:
        raise ValueError(f"COMPONENT_VERSION_DRIFT:risk_policy:{REFERENCE_RISK_POLICY_VERSION}:{manifest.get('risk_policy')}")


def validate_version_manifest(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Validate fields needed to attribute a native acceptance run."""

    candidate = dict(manifest)
    for field in REQUIRED_SCALAR_FIELDS:
        value = candidate.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"version manifest requires non-empty {field}")
    for field in REQUIRED_MAPPING_FIELDS:
        value = candidate.get(field)
        if not isinstance(value, Mapping) or not value:
            raise ValueError(f"version manifest requires non-empty {field}")
        if any(not isinstance(key, str) or not isinstance(item, str) or not item for key, item in value.items()):
            raise ValueError(f"version manifest {field} entries must be non-empty strings")
    if "data_adapters" in candidate:
        adapters = candidate["data_adapters"]
        if not isinstance(adapters, Mapping) or not adapters or any(
            not isinstance(key, str) or not isinstance(value, str) or not value for key, value in adapters.items()
        ):
            raise ValueError("version manifest data_adapters must be a non-empty version mapping")
    model = candidate["model"].casefold()
    if any(marker in model for marker in FORBIDDEN_MODEL_MARKERS):
        raise ValueError("native candidate manifest requires an explicit non-fixture model")
    if not candidate["codex_runtime"].startswith("codex-cli/"):
        raise ValueError("codex_runtime must identify the verified Codex CLI")
    expected_resources = {
        "plugin",
        "plugin_mcp",
        "runtime_config",
        "runtime_profile",
        "decision_contract",
        "council_skill",
        "cio_agent",
        "company_agent",
        "skeptic_agent",
    }
    if set(candidate["resource_hashes"]) != expected_resources:
        raise ValueError("resource_hashes must lock every Codex-native product resource")
    if any(
        len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest)
        for digest in candidate["resource_hashes"].values()
    ):
        raise ValueError("resource hashes must be lowercase SHA-256 values")
    expected_assurance = {
        "model_routing_policy",
        "runtime_eval_rubric",
        "runtime_eval_grader_skill",
        "runtime_eval_grader_agent",
        "runtime_eval_calibration",
        "regression_set",
        "ablation_profiles",
        "promotion_policy",
    }
    if set(candidate["assurance_hashes"]) != expected_assurance:
        raise ValueError("assurance_hashes must lock every replay/eval assurance resource")
    if any(
        len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest)
        for digest in candidate["assurance_hashes"].values()
    ):
        raise ValueError("assurance hashes must be lowercase SHA-256 values")
    return candidate


def load_version_manifest(path: Path) -> dict[str, Any]:
    """Load and validate a candidate manifest from disk."""

    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise ValueError("version manifest must be an object")
    return validate_version_manifest(value)


def validate_profile_agent_versions(
    manifest: Mapping[str, Any], profile: Mapping[str, Any]
) -> None:
    """Reject stale profile mirrors before dispatch; never update a frozen lock."""

    approved = manifest["agents"]
    agents = profile.get("agents")
    if not isinstance(agents, Mapping):
        raise ValueError("PROFILE_AGENTS_INVALID")
    for agent_name, record in agents.items():
        key = str(agent_name).replace("_", "-")
        expected = approved.get(key)
        actual = record.get("version") if isinstance(record, Mapping) else None
        if not isinstance(expected, str) or actual != expected:
            raise ValueError(f"PROFILE_AGENT_VERSION_DRIFT:{agent_name}:{actual}:{expected}")
    stage = profile.get("multidimensional_holding_research_stage")
    if isinstance(stage, Mapping):
        agent_name = stage.get("market_agent")
        key = agent_name.replace("_", "-") if isinstance(agent_name, str) else None
        expected = approved.get(key) if key else None
        actual = stage.get("market_agent_version")
        if not isinstance(expected, str) or actual != expected:
            raise ValueError(f"PROFILE_AGENT_VERSION_DRIFT:{agent_name}:{actual}:{expected}")


def derive_profile_agent_versions(
    manifest: Mapping[str, Any], profile: Mapping[str, Any]
) -> dict[str, Any]:
    """Render current profile version mirrors from the approved manifest only."""

    derived = deepcopy(dict(profile))
    approved = manifest["agents"]
    agents = derived.get("agents")
    if not isinstance(agents, dict):
        raise ValueError("PROFILE_AGENTS_INVALID")
    for agent_name, record in agents.items():
        key = str(agent_name).replace("_", "-")
        if not isinstance(record, dict) or key not in approved:
            raise ValueError(f"PROFILE_AGENT_UNAPPROVED:{agent_name}")
        record["version"] = approved[key]
    stage = derived.get("multidimensional_holding_research_stage")
    if isinstance(stage, dict):
        agent_name = stage.get("market_agent")
        key = agent_name.replace("_", "-") if isinstance(agent_name, str) else None
        if key not in approved:
            raise ValueError(f"PROFILE_AGENT_UNAPPROVED:{agent_name}")
        stage["market_agent_version"] = approved[key]
    return derived


def main(argv: list[str] | None = None) -> int:
    """Read-only fixture mirror check or deterministic render for reviewed edits."""

    parser = argparse.ArgumentParser(description="Check or render current fixture profile version mirrors")
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--skill", help="Explicitly render one approved Skill metadata mirror; never writes")
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--check", action="store_true")
    operation.add_argument("--render", action="store_true")
    args = parser.parse_args(argv)
    try:
        product_root = args.repo.resolve() / "product"
        manifest = load_version_manifest(product_root / "version-manifest.json")
        profile_path = product_root / "runtime-profile.json"
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        if not isinstance(profile, Mapping):
            raise ValueError("PROFILE_INVALID")
        if profile.get("profile_id") != manifest["runtime_profile"]:
            raise ValueError("PROFILE_ID_DRIFT:fixture")
        if args.render:
            if args.skill:
                approved_component_version(manifest, "skills", args.skill)
                print(derive_skill_version(manifest, args.skill, product_root / "skills" / args.skill / "SKILL.md"), end="")
                return 0
            print(json.dumps(derive_profile_agent_versions(manifest, profile), ensure_ascii=False, indent=2))
            return 0
        if args.skill:
            raise ValueError("SKILL_RENDER_REQUIRES_EXPLICIT_RENDER")
        validate_profile_agent_versions(manifest, profile)
        validate_current_component_versions(product_root, manifest)
        from .hashing import file_hash
        if file_hash(profile_path) != manifest["resource_hashes"]["runtime_profile"]:
            raise ValueError("PROFILE_RESOURCE_HASH_DRIFT:fixture")
        print("PROFILE_VERSION_MIRRORS_OK")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
