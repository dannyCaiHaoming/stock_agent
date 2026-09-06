"""Immutable invocation manifests and isolated Agent input packages."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any, Mapping, Sequence

from .discovery import discover_product_resources
from .hashing import canonical_hash, file_hash


INVOCATION_SCHEMA_VERSION = "invocation-manifest/2.0.0"
AGENT_FILES = {
    "runtime_company_analyst": ".codex/agents/runtime_company_analyst.toml",
    "runtime_skeptic": ".codex/agents/runtime_skeptic.toml",
    "runtime_cio": ".codex/agents/runtime_cio.toml",
}
AGENT_MANIFEST_KEYS = {
    "runtime_company_analyst": "runtime-company-analyst",
    "runtime_skeptic": "runtime-skeptic",
    "runtime_cio": "runtime-cio",
}
OUTPUT_SCHEMAS = {
    "runtime_company_analyst": "schemas/runtime/agent-research-report.schema.json",
    "runtime_skeptic": "schemas/runtime/counter-thesis-report.schema.json",
    "runtime_cio": "schemas/runtime/cio-decision-draft.schema.json",
}


def build_specialist_inputs(
    *,
    run_id: str,
    fixture: Mapping[str, Any],
    allowed_evidence_ids: Sequence[str],
    research_question: str,
) -> dict[str, dict[str, Any]]:
    """Build isolated inputs containing references but no raw Evidence values."""

    portfolio = fixture["portfolio"]
    summary = {
        "base_currency": portfolio["base_currency"],
        "cash": portfolio["cash"],
        "positions": [
            {
                "security_id": item["security_id"],
                "quantity": item["quantity"],
                "price": item["price"],
            }
            for item in portfolio["positions"]
        ],
        "mandate": dict(portfolio["mandate"]),
    }
    common = {
        "run_id": run_id,
        "decision_cutoff": fixture["decision_cutoff"],
        "research_scope": research_question,
        "portfolio_summary": summary,
        "allowed_evidence_ids": sorted(allowed_evidence_ids),
        "evidence_access": "fixture_evidence.query",
    }
    return {
        "runtime_company_analyst": {
            **common,
            "agent": "runtime_company_analyst",
            "security_id": portfolio["positions"][0]["security_id"],
        },
        "runtime_skeptic": {
            **common,
            "agent": "runtime_skeptic",
            "mode": "INDEPENDENT_FIRST_PASS",
            "security_id": portfolio["positions"][0]["security_id"],
        },
    }


def validate_skeptic_first_pass_input(value: Mapping[str, Any]) -> None:
    forbidden = {
        "analyst_output",
        "analyst_report",
        "analyst_summary",
        "analyst_hash",
        "cio_draft",
        "cio_conclusion",
        "peer_agent_conclusion",
    }

    def walk(item: Any) -> None:
        if isinstance(item, Mapping):
            overlap = forbidden & {str(key).casefold() for key in item}
            if overlap:
                raise ValueError(
                    f"CONTEXT_ISOLATION_VIOLATION:{','.join(sorted(overlap))}"
                )
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    if value.get("agent") != "runtime_skeptic" or value.get("mode") != "INDEPENDENT_FIRST_PASS":
        raise ValueError("invalid skeptic first-pass identity or mode")
    walk(value)


def _load_agent(path: Path) -> dict[str, Any]:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _skill_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"skill has no frontmatter: {path}")
    frontmatter = text[4:].split("\n---\n", 1)[0]
    metadata = False
    version: str | None = None
    for line in frontmatter.splitlines():
        if line == "metadata:":
            metadata = True
            continue
        if line and not line[0].isspace():
            metadata = False
        if metadata and line.startswith("  version:"):
            version = line.split(":", 1)[1].strip().strip("\"'")
            break
    if not version:
        raise ValueError(f"skill has no metadata.version: {path}")
    return version


def create_invocation_manifest(
    repository_root: Path,
    *,
    run_id: str,
    agent_name: str,
    agent_input: Mapping[str, Any],
    task_prompt: str,
    model: str,
    evidence_ids: Sequence[str],
) -> dict[str, Any]:
    if agent_name not in AGENT_FILES:
        raise ValueError(f"unknown runtime agent: {agent_name}")
    discovery = discover_product_resources(repository_root)
    product_root = Path(discovery.product_root)
    version_manifest = discovery.version_manifest
    if model != version_manifest["model"]:
        raise ValueError("model differs from candidate manifest")

    agent_path = (product_root / AGENT_FILES[agent_name]).resolve()
    agent = _load_agent(agent_path)
    expected_agent_version = version_manifest["agents"][AGENT_MANIFEST_KEYS[agent_name]]
    if agent.get("name") != agent_name:
        raise ValueError("agent identity/version differs from candidate manifest")

    runtime_profile = json.loads((product_root / "runtime-profile.json").read_text(encoding="utf-8"))
    profile_agent = runtime_profile["agents"].get(agent_name)
    if not isinstance(profile_agent, Mapping):
        raise ValueError("agent is not in the locked runtime profile")
    if profile_agent.get("version") != expected_agent_version:
        raise ValueError("agent profile version differs from candidate manifest")

    skill_records: list[dict[str, Any]] = []
    for entry in agent.get("skills", {}).get("config", []):
        relative = Path(entry["path"])
        skill_path = (product_root / relative / "SKILL.md").resolve()
        if not skill_path.is_relative_to(product_root) or not skill_path.is_file():
            raise ValueError(f"agent skill is not repository product-owned: {relative}")
        skill_name = relative.name
        version = _skill_version(skill_path)
        if version_manifest["skills"].get(skill_name) != version:
            raise ValueError(f"skill version differs from candidate manifest: {skill_name}")
        skill_records.append(
            {
                "name": skill_name,
                "version": version,
                "path": str(skill_path),
                "sha256": file_hash(skill_path),
            }
        )

    configured_skill_names = [item["name"] for item in skill_records]
    if configured_skill_names != profile_agent["skills"]:
        raise ValueError("agent skills differ from the locked runtime profile")
    tools = sorted(profile_agent["tool_permissions"])
    output_schema_path = (product_root / OUTPUT_SCHEMAS[agent_name]).resolve()
    if not output_schema_path.is_file():
        raise FileNotFoundError(f"missing output schema: {output_schema_path}")
    input_hash = canonical_hash(agent_input)
    prompt_hash = canonical_hash({"task_prompt": task_prompt})
    instruction_hash = canonical_hash(
        {
            "agent_instructions": agent["developer_instructions"],
            "agent_sha256": file_hash(agent_path),
            "skills": skill_records,
            "task_prompt_hash": prompt_hash,
        }
    )
    invocation_id = f"inv_{canonical_hash({'run_id': run_id, 'agent': agent_name, 'input_hash': input_hash})[:24]}"
    skill_execution = [
        {
            "skill_name": item["name"],
            "version": item["version"],
            "invocation_hash": canonical_hash(
                {
                    "invocation_id": invocation_id,
                    "skill_sha256": item["sha256"],
                    "instruction_bundle_hash": instruction_hash,
                }
            ),
        }
        for item in skill_records
    ]
    body: dict[str, Any] = {
        "schema_version": INVOCATION_SCHEMA_VERSION,
        "run_id": run_id,
        "invocation_id": invocation_id,
        "agent": {
            "name": agent_name,
            "version": profile_agent["version"],
            "path": str(agent_path),
            "sha256": file_hash(agent_path),
        },
        "skills": skill_records,
        "skill_execution": skill_execution,
        "task_prompt_hash": prompt_hash,
        "task_prompt_artifact": f"prompts/{agent_name}.txt",
        "instruction_bundle_hash": instruction_hash,
        "model": model,
        "codex_runtime": version_manifest["codex_runtime"],
        "evidence_ids": sorted(evidence_ids),
        "tool_permissions": tools,
        "input_artifact": f"inputs/{agent_name}.json",
        "input_hash": input_hash,
        "output_schema": str(output_schema_path),
        "output_schema_hash": file_hash(output_schema_path),
    }
    body["manifest_hash"] = canonical_hash(body)
    return body


def verify_invocation_manifest(
    repository_root: Path,
    manifest: Mapping[str, Any],
    *,
    agent_input: Mapping[str, Any],
) -> None:
    body = dict(manifest)
    claimed_hash = body.pop("manifest_hash", None)
    if claimed_hash != canonical_hash(body):
        raise ValueError("invocation manifest hash mismatch")
    if manifest.get("input_hash") != canonical_hash(agent_input):
        raise ValueError("invocation input hash mismatch")
    agent = manifest.get("agent", {})
    path = Path(str(agent.get("path", ""))).resolve()
    product_root = (repository_root.resolve() / "product").resolve()
    if not path.is_relative_to(product_root) or file_hash(path) != agent.get("sha256"):
        raise ValueError("invocation agent resource mismatch")
    output_schema = Path(str(manifest.get("output_schema", ""))).resolve()
    if not output_schema.is_relative_to(product_root) or file_hash(output_schema) != manifest.get("output_schema_hash"):
        raise ValueError("invocation output schema mismatch")
    for skill in manifest.get("skills", []):
        skill_path = Path(str(skill.get("path", ""))).resolve()
        if not skill_path.is_relative_to(product_root) or file_hash(skill_path) != skill.get("sha256"):
            raise ValueError("invocation skill resource mismatch")
