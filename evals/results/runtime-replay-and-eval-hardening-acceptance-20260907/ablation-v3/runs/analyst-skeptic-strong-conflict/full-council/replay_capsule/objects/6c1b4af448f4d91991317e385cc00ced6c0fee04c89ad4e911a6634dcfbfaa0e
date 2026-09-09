"""Immutable invocation manifests and isolated Agent input packages."""

from __future__ import annotations

import copy
import json
import tomllib
from pathlib import Path
from typing import Any, Mapping, Sequence

from .decision_contract import contract_record
from .discovery import discover_product_resources
from .hashing import canonical_hash, file_hash


INVOCATION_SCHEMA_VERSION = "invocation-manifest/2.1.0"
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
SPECIALIST_AGENTS = {"runtime_company_analyst", "runtime_skeptic"}


def _evidence_id_schema(allowed_evidence_ids: Sequence[str]) -> dict[str, Any]:
    allowed = sorted(set(allowed_evidence_ids))
    if not allowed or any(not isinstance(item, str) or not item.strip() for item in allowed):
        raise ValueError("allowed Evidence IDs must be non-empty canonical strings")
    return {
        "type": "string",
        "enum": allowed,
        "description": (
            "必须逐字选择当前 Gate 的 allowed_evidence_ids；只能填写原始 evidence_id，"
            "禁止拼接 source_id、as_of、retrieved_at 或说明文字。"
        ),
    }


def build_specialist_output_schema(
    repository_root: Path,
    *,
    agent_name: str,
    allowed_evidence_ids: Sequence[str],
) -> dict[str, Any]:
    """Compile a run-scoped specialist schema with Gate-bound Evidence ID enums."""

    if agent_name not in SPECIALIST_AGENTS:
        raise ValueError(f"not a specialist agent: {agent_name}")
    product_root = (repository_root.resolve() / "product").resolve()
    source_path = (product_root / OUTPUT_SCHEMAS[agent_name]).resolve()
    schema = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(schema, Mapping):
        raise ValueError(f"specialist output schema is not an object: {source_path}")
    schema = copy.deepcopy(dict(schema))
    evidence_id = _evidence_id_schema(allowed_evidence_ids)
    schema["x-evidence-id-constraint"] = {
        "source": "agent_input.allowed_evidence_ids",
        "allowed_evidence_ids_hash": canonical_hash(sorted(set(allowed_evidence_ids))),
        "mode": "enum",
    }
    if agent_name == "runtime_company_analyst":
        schema["properties"]["counter_evidence_refs"]["items"] = copy.deepcopy(
            evidence_id
        )
        schema["$defs"]["claim"]["properties"]["evidence_refs"]["items"] = (
            copy.deepcopy(evidence_id)
        )
    else:
        schema["properties"]["evidence_refs"]["items"] = copy.deepcopy(evidence_id)
        schema["properties"]["counter_evidence_refs"]["items"] = copy.deepcopy(
            evidence_id
        )
        schema["properties"]["challenges"]["items"]["properties"][
            "evidence_refs"
        ]["items"] = copy.deepcopy(evidence_id)
    return schema


def build_cio_ablation_output_schema(
    repository_root: Path,
    *,
    expected_report_agents: Sequence[str],
) -> dict[str, Any]:
    """Compile a run-scoped CIO schema for an evaluation-only topology."""

    allowed = list(expected_report_agents)
    if any(item not in SPECIALIST_AGENTS for item in allowed) or len(allowed) != len(set(allowed)):
        raise ValueError("invalid ablation report-agent set")
    source = repository_root.resolve() / "product" / OUTPUT_SCHEMAS["runtime_cio"]
    schema = copy.deepcopy(json.loads(source.read_text(encoding="utf-8")))
    consumed = schema["properties"]["consumed_reports"]
    consumed["minItems"] = len(allowed)
    consumed["maxItems"] = len(allowed)
    consumed["items"]["properties"]["agent"]["enum"] = allowed
    schema["x-eval-ablation"] = {
        "expected_report_agents": allowed,
        "expected_report_agents_hash": canonical_hash(allowed),
        "publishable": False,
    }
    return schema


def build_specialist_task_prompt(
    *, agent_name: str, allowed_evidence_ids: Sequence[str]
) -> str:
    if agent_name not in SPECIALIST_AGENTS:
        raise ValueError(f"not a specialist agent: {agent_name}")
    schema_name = (
        "AgentResearchReport 2.0.0"
        if agent_name == "runtime_company_analyst"
        else "CounterThesisReport 2.0.0"
    )
    allowed = sorted(set(allowed_evidence_ids))
    if not allowed:
        raise ValueError("specialist task prompt requires allowed Evidence IDs")
    rendered_ids = json.dumps(allowed, ensure_ascii=False)
    return (
        f"读取 Invocation Manifest，使用授权只读工具，并只返回符合 {schema_name} 的单个 JSON 对象。\n"
        f"allowed_evidence_ids: {rendered_ids}\n"
        "所有 evidence_refs 与 counter_evidence_refs 只能逐字填写上述集合中的原始 evidence_id。\n"
        "禁止在 evidence_id 后拼接 source_id、as_of、retrieved_at、分隔符、来源说明或任何其他文字。\n"
        "需要描述来源与时间时，应写入 statement、scope、uncertainties、data_gaps 或其他说明字段，"
        "不得污染 evidence_refs。非法引用必须 fail closed，不得自行截断或猜测修复。"
    )


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
    output_schema_path: Path | None = None,
    expected_report_agents: Sequence[str] | None = None,
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
    if agent_name in SPECIALIST_AGENTS:
        if output_schema_path is None:
            raise ValueError("specialist invocation requires a run-scoped output schema")
        output_schema_path = output_schema_path.resolve()
        expected_schema = build_specialist_output_schema(
            repository_root,
            agent_name=agent_name,
            allowed_evidence_ids=evidence_ids,
        )
        try:
            actual_schema = json.loads(output_schema_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("specialist output schema is missing or invalid") from exc
        if actual_schema != expected_schema:
            raise ValueError("specialist output schema differs from Gate constraints")
        input_evidence_ids = agent_input.get("allowed_evidence_ids")
        if input_evidence_ids != sorted(set(evidence_ids)):
            raise ValueError("specialist input Evidence IDs differ from invocation")
    else:
        if output_schema_path is not None:
            expected_schema = build_cio_ablation_output_schema(
                repository_root,
                expected_report_agents=expected_report_agents or (),
            )
            actual_schema = json.loads(output_schema_path.read_text(encoding="utf-8"))
            if actual_schema != expected_schema:
                raise ValueError("CIO ablation output schema differs from topology")
        else:
            if expected_report_agents is not None:
                raise ValueError("CIO ablation topology requires run-scoped output schema")
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
        "decision_contract": contract_record(product_root),
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
    agent_name = str(agent.get("name", ""))
    output_schema = Path(str(manifest.get("output_schema", ""))).resolve()
    if file_hash(output_schema) != manifest.get("output_schema_hash"):
        raise ValueError("invocation output schema mismatch")
    if agent_name in SPECIALIST_AGENTS:
        allowed = agent_input.get("allowed_evidence_ids")
        if not isinstance(allowed, list) or allowed != sorted(set(manifest.get("evidence_ids", []))):
            raise ValueError("specialist input Evidence IDs differ from invocation")
        expected_schema = build_specialist_output_schema(
            repository_root,
            agent_name=agent_name,
            allowed_evidence_ids=allowed,
        )
        try:
            actual_schema = json.loads(output_schema.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("specialist output schema is missing or invalid") from exc
        if actual_schema != expected_schema:
            raise ValueError("specialist output schema differs from Gate constraints")
        if (
            output_schema.parent.name != "schemas"
            or output_schema.name != Path(OUTPUT_SCHEMAS[agent_name]).name
        ):
            raise ValueError("specialist output schema path is not canonical")
    elif not output_schema.is_relative_to(product_root):
        expected_agents = sorted(agent_input.get("validated_reports", {}).keys())
        expected_schema = build_cio_ablation_output_schema(
            repository_root, expected_report_agents=expected_agents
        )
        try:
            actual_schema = json.loads(output_schema.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("CIO ablation output schema is missing or invalid") from exc
        if (
            actual_schema != expected_schema
            or output_schema.parent.name != "schemas"
            or output_schema.name != Path(OUTPUT_SCHEMAS[agent_name]).name
        ):
            raise ValueError("CIO ablation output schema mismatch")
    expected_contract = contract_record(product_root)
    if manifest.get("decision_contract") != expected_contract:
        raise ValueError("invocation decision contract mismatch")
    for skill in manifest.get("skills", []):
        skill_path = Path(str(skill.get("path", ""))).resolve()
        if not skill_path.is_relative_to(product_root) or file_hash(skill_path) != skill.get("sha256"):
            raise ValueError("invocation skill resource mismatch")
