"""从仓库实际资源构建并验证最小 Agent Package 拓扑。"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any, Mapping

from product.runtime.hashing import canonical_hash, file_hash

from .contracts import DemoValidationError, TOPOLOGY_VERSION


ROLE_BINDINGS = {
    "runtime_company_analyst": {
        "skills": ("evidence-grounding", "company-research", "valuation"),
        "tools": ("fixture_evidence.query", "fixture_math.calculate"),
        "output_schema": "schemas/runtime/agent-research-report.schema.json",
        "adapter": "CompanyAnalystDemoAdapter",
    },
    "runtime_skeptic": {
        "skills": ("evidence-grounding", "counter-thesis"),
        "tools": ("fixture_evidence.query",),
        "output_schema": "schemas/runtime/counter-thesis-report.schema.json",
        "adapter": "IndependentSkepticDemoAdapter",
    },
    "runtime_cio": {
        "skills": ("portfolio-council",),
        "tools": ("fixture_evidence.query",),
        "output_schema": "schemas/runtime/cio-decision-draft.schema.json",
        "adapter": "CioDemoAdapter",
    },
}


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DemoValidationError(f"PACKAGE_RESOURCE_UNREADABLE:{path}") from exc
    if not isinstance(value, Mapping):
        raise DemoValidationError(f"PACKAGE_RESOURCE_NOT_OBJECT:{path}")
    return dict(value)


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise DemoValidationError(f"PACKAGE_RESOURCE_UNREADABLE:{path}") from exc


def _skill_version(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DemoValidationError(f"PACKAGE_RESOURCE_UNREADABLE:{path}") from exc
    match = re.search(r'^\s*version:\s*["\']?([^"\'\n]+)', text, re.MULTILINE)
    if match is None:
        raise DemoValidationError(f"SKILL_VERSION_MISSING:{path}")
    return match.group(1).strip()


def _require_file(path: Path) -> None:
    if not path.is_file():
        raise DemoValidationError(f"PACKAGE_BINDING_MISSING:{path}")


def build_agent_package_topology(repository_root: Path) -> dict[str, Any]:
    root = repository_root.resolve()
    product = root / "product"
    plugin_path = product / ".codex-plugin" / "plugin.json"
    profile_path = product / "runtime-profile.json"
    mcp_path = product / ".mcp.json"
    entry_skill_path = product / "skills" / "portfolio-council" / "SKILL.md"
    for path in (plugin_path, profile_path, mcp_path, entry_skill_path):
        _require_file(path)

    plugin = _read_json(plugin_path)
    profile = _read_json(profile_path)
    mcp = _read_json(mcp_path)
    if plugin.get("skills") != "./skills/" or plugin.get("mcpServers") != "./.mcp.json":
        raise DemoValidationError("PLUGIN_PACKAGE_BINDING_DRIFT")
    if profile.get("entry_skill") != "portfolio-council":
        raise DemoValidationError("ENTRY_SKILL_BINDING_DRIFT")
    fixture_server = mcp.get("mcpServers", {}).get("fixture_runtime")
    if not isinstance(fixture_server, Mapping) or fixture_server.get("enabled") is not True:
        raise DemoValidationError("FIXTURE_MCP_BINDING_MISSING")
    if set(fixture_server.get("enabled_tools", [])) != {"query", "calculate"}:
        raise DemoValidationError("FIXTURE_MCP_TOOL_DRIFT")

    resource_paths: set[Path] = {plugin_path, profile_path, mcp_path, entry_skill_path}
    agents: dict[str, Any] = {}
    for role, expected in ROLE_BINDINGS.items():
        profile_agent = profile.get("agents", {}).get(role)
        if not isinstance(profile_agent, Mapping):
            raise DemoValidationError(f"AGENT_PROFILE_BINDING_MISSING:{role}")
        config_path = product / str(profile_agent.get("config_file", ""))
        schema_path = product / str(expected["output_schema"])
        _require_file(config_path)
        _require_file(schema_path)
        config = _read_toml(config_path)
        if config.get("name") != role:
            raise DemoValidationError(f"AGENT_IDENTITY_DRIFT:{role}")
        configured_skills = tuple(
            str(item.get("path", "")).rstrip("/").split("/")[-1]
            for item in config.get("skills", {}).get("config", [])
            if item.get("enabled") is True
        )
        profile_skills = tuple(profile_agent.get("skills", []))
        profile_tools = tuple(profile_agent.get("tool_permissions", []))
        if configured_skills != expected["skills"] or profile_skills != expected["skills"]:
            raise DemoValidationError(f"AGENT_SKILL_BINDING_DRIFT:{role}")
        if profile_tools != expected["tools"]:
            raise DemoValidationError(f"AGENT_TOOL_BINDING_DRIFT:{role}")
        skill_records = []
        for skill_name in expected["skills"]:
            skill_path = product / "skills" / skill_name / "SKILL.md"
            _require_file(skill_path)
            resource_paths.add(skill_path)
            skill_records.append(
                {
                    "name": skill_name,
                    "version": _skill_version(skill_path),
                    "path": str(skill_path.relative_to(product)),
                    "binding_verified": True,
                    "reasoning_executed": False,
                }
            )
        resource_paths.update({config_path, schema_path})
        agents[role] = {
            "version": profile_agent.get("version"),
            "definition": str(config_path.relative_to(product)),
            "demo_adapter": expected["adapter"],
            "skills": skill_records,
            "tools": list(expected["tools"]),
            "output_schema": str(schema_path.relative_to(product)),
            "binding_verified": True,
            "llm_used": False,
            "skill_reasoning_executed": False,
        }

    excluded = profile.get("excluded_agents", [])
    market_path = product / ".codex" / "agents" / "runtime_market_catalyst.toml"
    if "runtime_market_catalyst" not in excluded or not market_path.is_file():
        raise DemoValidationError("MARKET_CATALYST_EXCLUSION_MISSING")
    resource_paths.add(market_path)

    risk_path = product / "runtime" / "risk_runtime.py"
    decision_contract = product / "contracts" / "council-decision-contract.json"
    final_schema = product / "schemas" / "demo" / "demo-decision-envelope.schema.json"
    for path in (risk_path, decision_contract, final_schema):
        _require_file(path)
        resource_paths.add(path)

    capability_map = {
        "evidence_gate": {
            "input": "DemoInput.evidence + decision_cutoff",
            "tool_data": "Evidence Store / point-in-time Gate",
            "skill_reasoning": "deterministic provenance and freshness checks",
            "structured_output": "GateResult",
            "mvp_check": "future/stale Evidence is excluded before Agent requests",
        },
        "runtime_company_analyst": {
            "input": "DemoAgentRequest",
            "tool_data": "fixture_evidence.query + fixture_math.calculate",
            "skill_reasoning": "skill bindings verified; reasoning not executed",
            "structured_output": "AgentResearchReport in DemoAgentResponse",
            "mvp_check": "independent response with canonical Evidence IDs",
        },
        "runtime_skeptic": {
            "input": "DemoAgentRequest without Analyst output",
            "tool_data": "fixture_evidence.query",
            "skill_reasoning": "skill bindings verified; reasoning not executed",
            "structured_output": "CounterThesisReport in DemoAgentResponse",
            "mvp_check": "independent counter-thesis response",
        },
        "runtime_cio": {
            "input": "two validated Specialist responses",
            "tool_data": "fixture_evidence.query",
            "skill_reasoning": "CIO role binding verified; main-thread reasoning not executed",
            "structured_output": "CIODecisionDraft in DemoAgentResponse",
            "mvp_check": "consumes unchanged upstream objects",
        },
        "deterministic_risk_engine": {
            "input": "validated CIODecisionDraft",
            "tool_data": "portfolio snapshot + RiskPolicy",
            "skill_reasoning": "deterministic hard constraints",
            "structured_output": "RiskResult",
            "mvp_check": "draft cannot bypass a Risk veto",
        },
        "final_output": {
            "input": "Agent responses + RiskResult",
            "tool_data": "validated artifacts only",
            "skill_reasoning": "deterministic rendering",
            "structured_output": "decision.json + report.md + demo_run.json",
            "mvp_check": "synthetic/non-LLM/advisory limitations are visible",
        },
    }
    if any(set(item) != {"input", "tool_data", "skill_reasoning", "structured_output", "mvp_check"}
           for item in capability_map.values()):
        raise DemoValidationError("CAPABILITY_MAP_INCOMPLETE")

    hashes = {
        str(path.relative_to(root)): file_hash(path)
        for path in sorted(resource_paths)
    }
    body = {
        "schema_version": TOPOLOGY_VERSION,
        "profile": "DEMO_SCAFFOLD",
        "binding_verified": True,
        "reasoning_executed": False,
        "package": {
            "name": plugin.get("name"),
            "version": plugin.get("version"),
            "manifest": str(plugin_path.relative_to(root)),
        },
        "entry_skill": {
            "name": "portfolio-council",
            "version": _skill_version(entry_skill_path),
            "path": str(entry_skill_path.relative_to(product)),
            "binding_verified": True,
            "reasoning_executed": False,
        },
        "cio_role_policy": agents["runtime_cio"]["definition"],
        "agents": agents,
        "mcp": {
            "manifest": str(mcp_path.relative_to(product)),
            "server": "fixture_runtime",
            "tools": ["fixture_evidence.query", "fixture_math.calculate"],
            "access_mode": "read",
        },
        "risk": {
            "implementation": str(risk_path.relative_to(product)),
            "decision_contract": str(decision_contract.relative_to(product)),
        },
        "final_output": {
            "schema": str(final_schema.relative_to(product)),
            "artifacts": ["decision.json", "report.md", "demo_run.json"],
        },
        "excluded_agents": [
            {
                "name": "runtime_market_catalyst",
                "definition": str(market_path.relative_to(product)),
                "reason": "Milestone 0 仅装配 Company Analyst、Independent Skeptic 与 CIO",
                "instantiated": False,
            }
        ],
        "capability_map": capability_map,
        "resource_hashes": hashes,
    }
    body["topology_hash"] = canonical_hash(body)
    return body
