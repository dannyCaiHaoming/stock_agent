"""Candidate version-manifest validation."""

from __future__ import annotations

import json
from pathlib import Path
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
