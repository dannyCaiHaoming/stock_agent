"""Run-scoped, fixture-only MCP tools backed by an Evidence Gate artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from decimal import Decimal, DivisionByZero, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    # Repository execution: ``python -m product.runtime.fixture_mcp``.
    from product.mcp.provenance import canonical_json, content_hash
    from product.runtime.monetary import convert_monetary_value
except ModuleNotFoundError as exc:
    # Installed-plugin execution: the cachebuster directory is the import root,
    # so the same module is addressed as ``runtime.fixture_mcp``.
    if exc.name != "product":
        raise
    from mcp.provenance import canonical_json, content_hash
    from runtime.monetary import convert_monetary_value


MCP_ADAPTER_VERSION = "fixture-gate-scoped/2.3.0"
SUPPORTED_TOOLS = {
    "fixture_evidence.query", "fixture_math.calculate",
    "public_research.search", "public_research.fetch",
    "equity_research_attachments.query",
}
MONETARY_MENTION = re.compile(
    r"(?P<currency>\$|USD\s*)(?P<value>[+-]?\d+(?:\.\d+)?)\s*"
    r"(?P<scale>billion|million|thousand|亿|万)\b",
    re.IGNORECASE,
)


class ToolAccessError(ValueError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise ToolAccessError("INVALID_JSON_OBJECT")
    return dict(value)


def _tool_manifest(
    *, stateless: bool = False, include_research_tools: bool = False,
    include_attachment_tool: bool = False,
) -> tuple[dict[str, Any], ...]:
    common_properties: dict[str, Any] = {
        "run_id": {"type": "string"},
        "agent": {"type": "string"},
        "invocation_id": {"type": "string"},
        "evidence_ids": {"type": "array", "items": {"type": "string"}},
    }
    common_required = ["run_id", "agent", "invocation_id", "evidence_ids"]
    if stateless:
        common_properties = {"run_dir": {"type": "string"}, **common_properties}
        common_required = ["run_dir", *common_required]
    run_binding = (
        "Pass exactly run_dir, run_id, agent, invocation_id, and evidence_ids"
        if stateless else
        "run_dir is launcher-bound and MUST NOT be passed; pass exactly run_id, agent, "
        "invocation_id, and evidence_ids"
    )
    tools = [
        {
            "name": "query",
            "description": (
                "Read Gate-allowed fixture evidence for one verified invocation. "
                + run_binding + " as an array where applicable. Never pass singular "
                "evidence_id or omit the invocation identity."
            ),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "openWorldHint": False,
            },
            "inputSchema": {
                "type": "object",
                "required": common_required,
                "properties": common_properties,
                "additionalProperties": False,
            },
        },
        {
            "name": "calculate",
            "description": (
                "Calculate only from Gate-allowed Evidence. Required "
                "identity arguments follow the query tool's run-directory binding; also pass "
                "calculation_id, operation ('ratio', 'percent_change', or 'monetary_scale'), "
                "and evidence_ids. "
                "For ratio, evidence_ids are in numerator-then-denominator sequence; for "
                "percent_change, earlier then later. monetary_scale accepts exactly one Evidence "
                "ID plus target_scale and deterministically extracts supported disclosed monetary "
                "mentions. Do not send operands or expression."
            ),
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "openWorldHint": False,
            },
            "inputSchema": {
                "type": "object",
                "required": [
                    *common_required[:-1],
                    "calculation_id",
                    "operation",
                    "evidence_ids",
                ],
                "properties": {
                    **common_properties,
                    "calculation_id": {"type": "string", "minLength": 1},
                    "operation": {"enum": ["ratio", "percent_change", "monetary_scale"]},
                    "evidence_ids": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 2,
                        "items": {"type": "string"},
                    },
                    "target_scale": {
                        "enum": ["one", "thousand", "million", "billion", "万", "亿"]
                    },
                },
                "allOf": [
                    {
                        "if": {"properties": {"operation": {"const": "monetary_scale"}}},
                        "then": {
                            "required": ["target_scale"],
                            "properties": {"evidence_ids": {"minItems": 1, "maxItems": 1}},
                        },
                        "else": {
                            "properties": {"evidence_ids": {"minItems": 2, "maxItems": 2}},
                        },
                    }
                ],
                "additionalProperties": False,
            },
        },
    ]
    if stateless or include_research_tools or include_attachment_tool:
        identity = {
            "run_id": {"type": "string"},
            "agent": {"type": "string"}, "invocation_id": {"type": "string"},
        }
        if stateless:
            identity = {"run_dir": {"type": "string"}, **identity}
        additional_tools = [
            {
                "name": "equity_research_attachments.query",
                "description": (
                    "Read only the Gate-bound valuation snapshot/history, fundamental supplement, "
                    "or peer comparison attached to this common-stock invocation."
                ),
                "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
                "inputSchema": {
                    "type": "object", "additionalProperties": False,
                    "required": [*identity, "security_id", "decision_cutoff", "kinds"],
                    "properties": {
                        **identity, "security_id": {"type": "string"},
                        "decision_cutoff": {"type": "string"},
                        "kinds": {
                            "type": "array", "minItems": 1, "uniqueItems": True,
                            "items": {"enum": [
                                "valuation_snapshot", "valuation_history",
                                "fundamental_supplement", "peer_comparison",
                            ]},
                        },
                    },
                },
            },
            {
                "name": "research_search",
                "description": (
                    "Search public research for one authorized material-preparation invocation. "
                    "Results are LEAD_ONLY and cannot be cited as verified facts. Pass the exact "
                    "run identity, security_id, decision_cutoff and one bounded query."
                ),
                "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True},
                "inputSchema": {
                    "type": "object", "additionalProperties": False,
                    "required": [*identity, "security_id", "decision_cutoff", "query"],
                    "properties": {
                        **identity, "security_id": {"type": "string"},
                        "decision_cutoff": {"type": "string"},
                        "query": {"type": "string", "minLength": 1, "maxLength": 240},
                    },
                },
            },
            {
                "name": "research_fetch",
                "description": (
                    "Fetch and parse one candidate returned by research_search for the same "
                    "authorized invocation. A BODY_VERIFIED result may be used by formal research; "
                    "login, paywall, missing API key or unavailable content remain explicit errors."
                ),
                "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": True},
                "inputSchema": {
                    "type": "object", "additionalProperties": False,
                    "required": [*identity, "security_id", "candidate_id"],
                    "properties": {
                        **identity, "security_id": {"type": "string"},
                        "candidate_id": {"type": "string"},
                    },
                },
            },
        ]
        # The attachment reader is specific to a launcher-bound common-stock
        # run.  The unbound fixture/live servers still expose research tools,
        # but must not widen their historical attachment surface.
        if include_attachment_tool:
            tools.append(additional_tools[0])
        if stateless or include_research_tools:
            tools.extend(additional_tools[1:])
    return tuple(tools)


class GateScopedFixtureTools:
    """Expose only Gate-admitted facts for one immutable invocation identity."""

    adapter_version = MCP_ADAPTER_VERSION

    def __init__(
        self,
        gate_artifact: Mapping[str, Any],
        *,
        run_id: str,
        agent: str,
        invocation_id: str,
        allowed_tools: Sequence[str] = (
            "fixture_evidence.query",
            "fixture_math.calculate",
        ),
        allowed_evidence_ids: Sequence[str] | None = None,
    ) -> None:
        if gate_artifact.get("run_id") != run_id:
            raise ToolAccessError("CROSS_RUN_GATE")
        if not agent or not invocation_id:
            raise ToolAccessError("MISSING_INVOCATION_IDENTITY")
        if not set(allowed_tools) <= SUPPORTED_TOOLS:
            raise ToolAccessError("UNSUPPORTED_TOOL_PERMISSION")
        self.run_id = run_id
        self.agent = agent
        self.invocation_id = invocation_id
        self.allowed_tools = frozenset(allowed_tools)
        self._facts = {
            str(item["evidence_id"]): dict(item)
            for item in gate_artifact.get("allowed_evidence", [])
        }
        self._excluded = set(gate_artifact.get("excluded_evidence_ids", []))
        if set(self._facts) != set(gate_artifact.get("allowed_evidence_ids", [])):
            raise ToolAccessError("INVALID_GATE_ARTIFACT")
        if allowed_evidence_ids is not None and not set(allowed_evidence_ids) <= set(self._facts):
            raise ToolAccessError("INVOCATION_EVIDENCE_OUTSIDE_GATE")
        self._invocation_evidence_ids = (
            frozenset(allowed_evidence_ids) if allowed_evidence_ids is not None else None
        )
        self.events: list[dict[str, Any]] = []
        self.dynamic_event_log: Path | None = None

    @staticmethod
    def tool_manifest() -> tuple[dict[str, Any], ...]:
        return _tool_manifest()

    def available_tools(self) -> tuple[dict[str, Any], ...]:
        logical_names = {
            "query": "fixture_evidence.query",
            "calculate": "fixture_math.calculate",
        }
        return tuple(
            tool
            for tool in self.tool_manifest()
            if logical_names[tool["name"]] in self.allowed_tools
        )

    def _authorize_identity(self, *, agent: str, invocation_id: str) -> None:
        if agent != self.agent or invocation_id != self.invocation_id:
            raise ToolAccessError("INVOCATION_IDENTITY_MISMATCH")

    def _authorize_evidence(
        self, run_id: str, evidence_ids: Sequence[str]
    ) -> list[dict[str, Any]]:
        if run_id != self.run_id:
            raise ToolAccessError("CROSS_RUN_QUERY")
        if not evidence_ids:
            raise ToolAccessError("EMPTY_EVIDENCE_QUERY")
        facts: list[dict[str, Any]] = []
        for evidence_id in evidence_ids:
            if (self._invocation_evidence_ids is not None
                    and evidence_id not in self._invocation_evidence_ids):
                raise ToolAccessError(f"INVOCATION_EVIDENCE_NOT_AUTHORIZED:{evidence_id}")
            if evidence_id in self._excluded:
                raise ToolAccessError(f"EXCLUDED_EVIDENCE:{evidence_id}")
            fact = self._facts.get(evidence_id)
            if fact is None:
                raise ToolAccessError(f"UNKNOWN_EVIDENCE:{evidence_id}")
            facts.append(dict(fact))
        return facts

    def _record(
        self, tool: str, inputs: Mapping[str, Any], output: Mapping[str, Any]
    ) -> None:
        event = {
                "event_type": "mcp_tool_result",
                "adapter_version": self.adapter_version,
                "run_id": self.run_id,
                "agent": inputs["agent"],
                "invocation_id": inputs["invocation_id"],
                "tool": tool,
                "input_hash": content_hash(inputs),
                "output_hash": content_hash(output),
                "evidence_ids": list(inputs.get("evidence_ids", [])),
                "access_mode": "read",
            }
        if "calculation_id" in inputs:
            event["calculation_id"] = inputs["calculation_id"]
        if "operation" in inputs:
            event["operation"] = inputs["operation"]
        if "target_scale" in inputs:
            event["target_scale"] = inputs["target_scale"]
        event["event_hash"] = content_hash(event)
        self.events.append(event)

    def query(
        self,
        *,
        run_id: str,
        agent: str,
        invocation_id: str,
        evidence_ids: Sequence[str],
    ) -> dict[str, Any]:
        self._authorize_identity(agent=agent, invocation_id=invocation_id)
        if "fixture_evidence.query" not in self.allowed_tools:
            raise ToolAccessError("TOOL_NOT_AUTHORIZED:fixture_evidence.query")
        inputs = {
            "run_id": run_id,
            "agent": agent,
            "invocation_id": invocation_id,
            "evidence_ids": list(evidence_ids),
        }
        facts = self._authorize_evidence(run_id, evidence_ids)
        output = {
            "adapter_version": self.adapter_version,
            "run_id": self.run_id,
            "evidence": facts,
            "result_hash": content_hash(facts),
        }
        self._record("fixture_evidence.query", inputs, output)
        return output

    def calculate(
        self,
        *,
        run_id: str,
        agent: str,
        invocation_id: str,
        calculation_id: str,
        operation: str,
        evidence_ids: Sequence[str],
        target_scale: str | None = None,
    ) -> dict[str, Any]:
        self._authorize_identity(agent=agent, invocation_id=invocation_id)
        if "fixture_math.calculate" not in self.allowed_tools:
            raise ToolAccessError("TOOL_NOT_AUTHORIZED:fixture_math.calculate")
        if not isinstance(calculation_id, str) or not calculation_id.strip():
            raise ToolAccessError("INVALID_CALCULATION_ID")
        inputs = {
            "run_id": run_id,
            "agent": agent,
            "invocation_id": invocation_id,
            "calculation_id": calculation_id,
            "operation": operation,
            "evidence_ids": list(evidence_ids),
        }
        if target_scale is not None:
            inputs["target_scale"] = target_scale
        facts = self._authorize_evidence(run_id, evidence_ids)
        if operation == "monetary_scale":
            if len(facts) != 1 or target_scale is None:
                raise ToolAccessError("MONETARY_SCALE_REQUIRES_ONE_FACT_AND_TARGET_SCALE")
            fact = facts[0]
            value = fact.get("value")
            mentions = []
            if isinstance(value, str):
                for match in MONETARY_MENTION.finditer(value):
                    context = value[max(0, match.start() - 24):min(len(value), match.end() + 24)]
                    converted_value = convert_monetary_value(
                        value=match.group("value"),
                        source_scale=match.group("scale").lower(),
                        target_scale=target_scale,
                    )
                    lowered = context.casefold()
                    tax_basis = (
                        "PRE_TAX" if "pre-tax" in lowered or "pretax" in lowered
                        else "AFTER_TAX" if "after-tax" in lowered or "post-tax" in lowered
                        else "UNSPECIFIED"
                    )
                    mentions.append({
                        "source_text": match.group(0),
                        "source_value": match.group("value"),
                        "source_scale": match.group("scale").lower(),
                        "target_scale": target_scale,
                        "converted_value": converted_value,
                        "currency": "USD",
                        "tax_basis": tax_basis,
                        "conversion_hash": content_hash({
                            "evidence_id": fact["evidence_id"],
                            "source_text": match.group(0),
                            "source_value": match.group("value"),
                            "source_scale": match.group("scale").lower(),
                            "target_scale": target_scale,
                            "converted_value": converted_value,
                        }),
                    })
            if not mentions:
                raise ToolAccessError("MONETARY_MENTION_NOT_FOUND")
            output = {
                "adapter_version": self.adapter_version,
                "run_id": self.run_id,
                "calculation_id": calculation_id,
                "operation": operation,
                "evidence_ids": list(evidence_ids),
                "target_scale": target_scale,
                "conversions": mentions,
                "calculation_hash": content_hash({
                    "operation": operation,
                    "facts": facts,
                    "target_scale": target_scale,
                    "conversions": mentions,
                }),
            }
            self._record("fixture_math.calculate", inputs, output)
            return output
        if len(facts) != 2:
            raise ToolAccessError("CALCULATION_REQUIRES_TWO_FACTS")
        if target_scale is not None:
            raise ToolAccessError("TARGET_SCALE_ONLY_VALID_FOR_MONETARY_SCALE")
        try:
            first, second = (Decimal(str(fact["value"])) for fact in facts)
            if operation == "ratio":
                result = first / second
            elif operation == "percent_change":
                result = (second - first) / first
            else:
                raise ToolAccessError(f"UNKNOWN_CALCULATION:{operation}")
        except (DivisionByZero, InvalidOperation, KeyError) as exc:
            raise ToolAccessError("INVALID_NUMERIC_EVIDENCE") from exc
        output = {
            "adapter_version": self.adapter_version,
            "run_id": self.run_id,
            "calculation_id": calculation_id,
            "operation": operation,
            "evidence_ids": list(evidence_ids),
            "value": format(result, "f"),
            "calculation_hash": content_hash(
                {"operation": operation, "facts": facts, "value": format(result, "f")}
            ),
        }
        self._record("fixture_math.calculate", inputs, output)
        return output


class StatelessFixtureTools:
    """Resolve a verified immutable run package per tool call."""

    def __init__(self, *, default_run_dir: Path | str | None = None) -> None:
        self.events: list[dict[str, Any]] = []
        self.dynamic_event_log: Path | None = None
        self.default_run_dir = (
            Path(default_run_dir).resolve() if default_run_dir is not None else None
        )
        self._last_root: Path | None = None
        self._last_invocation: dict[str, Any] | None = None

    @staticmethod
    def tool_manifest() -> tuple[dict[str, Any], ...]:
        return _tool_manifest(stateless=True)

    def available_tools(self) -> tuple[dict[str, Any], ...]:
        # A launcher-bound run directory removes ``run_dir`` from every public
        # tool schema, but it must not hide the material-preparation tools. The
        # previous implementation coupled these two concerns and caused real
        # Codex agents to see only query/calculate during research discovery.
        return _tool_manifest(
            stateless=self.default_run_dir is None,
            include_research_tools=True,
            include_attachment_tool=self.default_run_dir is not None,
        )

    def _bound_tools(
        self, *, run_dir: str | None, run_id: str, agent: str, invocation_id: str
    ) -> GateScopedFixtureTools:
        requested = Path(run_dir).resolve() if run_dir else None
        if self.default_run_dir is not None:
            if requested is not None and requested != self.default_run_dir:
                raise ToolAccessError("RUN_DIRECTORY_OVERRIDE_REJECTED")
            root = self.default_run_dir
        elif requested is not None:
            root = requested
        else:
            raise ToolAccessError("RUN_DIRECTORY_MISSING")
        run_manifest_path = root / "run_manifest.json"
        gate_path = root / "evidence" / "gate.json"
        run_manifest = _load_object(run_manifest_path)
        skeptic_scope = None
        if run_manifest.get("stage") == "INDEPENDENT_COUNTER_THESIS_RESEARCH" and agent == "runtime_skeptic":
            from product.runtime.independent_skeptic_stage import resolve_skeptic_tool_scope
            skeptic_scope = resolve_skeptic_tool_scope(
                root, run_id=run_id, invocation_id=invocation_id,
                gate=_load_object(gate_path),
                index_ref=os.environ.get("STOCK_AGENT_SKEPTIC_DISPATCH_INDEX"),
            )
        invocation_path = root / "invocations" / f"{agent}.json"
        if skeptic_scope is not None:
            invocation_path = skeptic_scope[0]
        elif not invocation_path.is_file():
            invocation_path = (
                root / "invocations" / "by-id"
                / (hashlib.sha256(invocation_id.encode("utf-8")).hexdigest() + ".json")
            )
        if not invocation_path.is_file():
            matches = []
            for candidate in (root / "invocations" / "by-id").glob("*.json"):
                try:
                    value = _load_object(candidate)
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
                if value.get("invocation_id") == invocation_id:
                    matches.append(candidate)
            if len(matches) == 1:
                invocation_path = matches[0]
            elif len(matches) > 1:
                raise ToolAccessError("INVOCATION_BINDING_AMBIGUOUS")
        if not all(
            path.is_file()
            for path in (run_manifest_path, gate_path, invocation_path)
        ):
            raise ToolAccessError("RUN_PACKAGE_BINDING_MISSING")
        gate = _load_object(gate_path)
        invocation = _load_object(invocation_path)
        if Path(str(run_manifest.get("output_dir", ""))).resolve() != root:
            raise ToolAccessError("RUN_DIRECTORY_MISMATCH")
        invocation_agent = (
            invocation.get("agent", {}).get("name")
            if isinstance(invocation.get("agent"), Mapping)
            else None
        )
        if invocation_agent is None and isinstance(invocation.get("agent_binding"), Mapping):
            invocation_agent = invocation["agent_binding"].get("name")
        if (
            run_manifest.get("run_id") != run_id
            or gate.get("run_id") != run_id
            or invocation.get("run_id") != run_id
            or invocation.get("invocation_id") != invocation_id
            or invocation_agent != agent
        ):
            raise ToolAccessError("INVOCATION_IDENTITY_MISMATCH")
        self._last_root = root
        self._last_invocation = invocation
        product_root = Path(
            str(run_manifest.get("discovery", {}).get("product_root", ""))
        ).resolve()
        repository_root = product_root.parent
        if product_root.name != "product":
            raise ToolAccessError("INVALID_PRODUCT_DISCOVERY_ROOT")
        if run_manifest.get("stage") in {
            "MULTI_DIMENSIONAL_HOLDING_RESEARCH",
            "INDEPENDENT_COUNTER_THESIS_RESEARCH",
            "MULTIDIMENSIONAL_MATERIAL_PREPARATION",
        }:
            if (
                run_manifest.get("source_mode") != "frozen-gate"
                or gate.get("source_mode") not in {
                    "live-read-only", "provider-neutral-read-only", "fixture",
                }
            ):
                raise ToolAccessError("NON_FROZEN_RESEARCH_DATA_SOURCE")
        else:
            fixture_path = Path(str(run_manifest.get("fixture", ""))).resolve()
            fixture_root = (
                repository_root / "evals" / "fixtures" / "codex-native"
            ).resolve()
            if not fixture_path.is_relative_to(fixture_root):
                raise ToolAccessError("NON_FIXTURE_DATA_SOURCE")
        self.dynamic_event_log = root / "events" / "mcp" / "events.jsonl"
        return GateScopedFixtureTools(
            gate,
            run_id=run_id,
            agent=agent,
            invocation_id=invocation_id,
            allowed_tools=invocation.get("tool_permissions", []),
            allowed_evidence_ids=skeptic_scope[1] if skeptic_scope is not None else None,
        )

    def _research_context(self, arguments: dict[str, Any], permission: str) -> tuple[Path, dict[str, Any]]:
        run_dir = (
            arguments.pop("run_dir", None)
            if self.default_run_dir is not None else arguments.pop("run_dir")
        )
        self._bound_tools(
            run_dir=run_dir,
            **{key: str(arguments[key]) for key in ("run_id", "agent", "invocation_id")},
        )
        if self._last_root is None or self._last_invocation is None:
            raise ToolAccessError("RUN_PACKAGE_BINDING_MISSING")
        manifest = _load_object(self._last_root / "run_manifest.json")
        if manifest.get("stage") != "MULTIDIMENSIONAL_MATERIAL_PREPARATION":
            raise ToolAccessError("RESEARCH_PREPARATION_STAGE_REQUIRED")
        if permission not in self._last_invocation.get("tool_permissions", []):
            raise ToolAccessError(f"TOOL_NOT_AUTHORIZED:{permission}")
        task_path = self._last_root / str(self._last_invocation.get("task_path", ""))
        task = _load_object(task_path)
        if task.get("security_id") != arguments.get("security_id"):
            raise ToolAccessError("RESEARCH_PREPARATION_SECURITY_MISMATCH")
        return self._last_root, task

    def research_search(self, **arguments: Any) -> dict[str, Any]:
        root, task = self._research_context(arguments, "public_research.search")
        if task.get("preparation_kind") not in {
            "RESEARCH_REPORT_DISCOVERY", "MACRO_RESEARCH_DISCOVERY",
            "MARKET_RESEARCH_DISCOVERY",
        }:
            raise ToolAccessError("RESEARCH_SEARCH_TASK_KIND_INVALID")
        if arguments.get("decision_cutoff") != task.get("decision_cutoff"):
            raise ToolAccessError("RESEARCH_SEARCH_CUTOFF_MISMATCH")
        directory = root / "research/materials" / hashlib.sha256(
            str(arguments["invocation_id"]).encode("utf-8")
        ).hexdigest()[:16]
        directory.mkdir(parents=True, exist_ok=True)
        existing = sorted(directory.glob("search-*.json"))
        policy_root = Path(__file__).resolve().parents[1] / "mcp/live/research-source-policy.json"
        policy = _load_object(policy_root)["sources"]["openalex"]
        if len(existing) >= int(policy["request_budget"]["searches_per_security"]):
            raise ToolAccessError("PUBLIC_RESEARCH_SEARCH_BUDGET_EXHAUSTED")
        try:
            from product.mcp.live.cache import SnapshotCache
            from product.mcp.live.public_research import OpenAlexResearchClient
        except ModuleNotFoundError:
            from mcp.live.cache import SnapshotCache
            from mcp.live.public_research import OpenAlexResearchClient
        client = OpenAlexResearchClient(
            policy, SnapshotCache(root / ".material-cache"),
            api_key=os.environ.get("OPENALEX_API_KEY"),
        )
        artifact = directory / f"search-{len(existing) + 1}.json"
        try:
            result = client.search(
                query=str(arguments["query"]), security_id=str(arguments["security_id"]),
                decision_cutoff=str(arguments["decision_cutoff"]),
            )
            result = {
                **result, "query": str(arguments["query"]),
                "attempt_status": "COMPLETED", "failure_code": None,
                "provider_events": client.events,
            }
        except ValueError as exc:
            failure_code = str(exc).split(":", 1)[0]
            if not (
                failure_code.startswith("PUBLIC_RESEARCH_SEARCH_HTTP_")
                or failure_code in {
                    "PUBLIC_RESEARCH_TRANSPORT_FAILURE",
                    "PUBLIC_RESEARCH_SEARCH_RESPONSE_INVALID",
                }
            ):
                raise
            result = {
                "query": str(arguments["query"]), "candidates": [], "excluded": [],
                "raw_content_hash": None, "attempt_status": "SOURCE_LIMITED",
                "failure_code": failure_code, "provider_events": client.events,
            }
        with artifact.open("x", encoding="utf-8") as stream:
            json.dump(result, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
        output = {
            **result, "status": result["attempt_status"],
            "artifact_ref": str(artifact.relative_to(root)),
        }
        event = {
            "event_type": "mcp_tool_result", "adapter_version": MCP_ADAPTER_VERSION,
            "run_id": arguments["run_id"], "agent": arguments["agent"],
            "invocation_id": arguments["invocation_id"], "tool": "public_research.search",
            "input_hash": content_hash(arguments), "output_hash": content_hash(output),
            "artifact_ref": output["artifact_ref"], "access_mode": "read",
            "provider_events": client.events,
        }
        self.events.append(event)
        return output

    def equity_research_attachments_query(self, **arguments: Any) -> dict[str, Any]:
        run_dir = (
            arguments.pop("run_dir", None)
            if self.default_run_dir is not None else arguments.pop("run_dir")
        )
        self._bound_tools(
            run_dir=run_dir,
            **{
                key: str(arguments[key])
                for key in ("run_id", "agent", "invocation_id")
            },
        )
        if self._last_root is None or self._last_invocation is None:
            raise ToolAccessError("RUN_PACKAGE_BINDING_MISSING")
        if "equity_research_attachments.query" not in self._last_invocation.get("tool_permissions", []):
            raise ToolAccessError("TOOL_NOT_AUTHORIZED:equity_research_attachments.query")
        manifest = _load_object(self._last_root / "run_manifest.json")
        if manifest.get("stage") != "COMMON_STOCK_RESEARCH":
            raise ToolAccessError("COMMON_STOCK_STAGE_REQUIRED")
        index = _load_object(self._last_root / "research/dispatch-index.json")
        tasks = [
            item for item in index.get("tasks", [])
            if item.get("invocation_id") == arguments.get("invocation_id")
            and item.get("security_id") == arguments.get("security_id")
        ]
        if len(tasks) != 1 or not tasks[0].get("equity_research_package_path"):
            raise ToolAccessError("EQUITY_ATTACHMENT_INVOCATION_BINDING_MISSING")
        package = _load_object(self._last_root / tasks[0]["equity_research_package_path"])
        gate = _load_object(self._last_root / "evidence/gate.json")
        try:
            from product.runtime.equity_research_package import GateScopedEquityResearchTools
        except ModuleNotFoundError:
            from runtime.equity_research_package import GateScopedEquityResearchTools
        tools = GateScopedEquityResearchTools(
            package=package, gate=gate,
            run_id=str(arguments["run_id"]), agent=str(arguments["agent"]),
            invocation_id=str(arguments["invocation_id"]),
        )
        result = tools.query(**arguments)
        self.events.append(tools.events[-1])
        return result

    def research_fetch(self, **arguments: Any) -> dict[str, Any]:
        root, task = self._research_context(arguments, "public_research.fetch")
        if task.get("preparation_kind") not in {
            "RESEARCH_REPORT_DISCOVERY", "MACRO_RESEARCH_DISCOVERY",
            "MARKET_RESEARCH_DISCOVERY",
        }:
            raise ToolAccessError("RESEARCH_FETCH_TASK_KIND_INVALID")
        directory = root / "research/materials" / hashlib.sha256(
            str(arguments["invocation_id"]).encode("utf-8")
        ).hexdigest()[:16]
        candidate_matches = []
        for path in directory.glob("search-*.json"):
            search = _load_object(path)
            candidate_matches.extend(
                item for item in search.get("candidates", [])
                if item.get("candidate_id") == arguments.get("candidate_id")
                and item.get("security_id") == arguments.get("security_id")
            )
        if len(candidate_matches) != 1:
            raise ToolAccessError("PUBLIC_RESEARCH_CANDIDATE_NOT_BOUND")
        existing = directory / f"document-{arguments['candidate_id']}.json"
        attempt = directory / (
            "fetch-" + hashlib.sha256(str(arguments["candidate_id"]).encode("utf-8")).hexdigest()[:16] + ".json"
        )
        if existing.is_file():
            document = _load_object(existing)
            output = {
                "status": "READY", "document": document,
                "artifact_ref": str(existing.relative_to(root)), "cache_hit": True,
            }
            self.events.append({
                "event_type": "mcp_tool_result", "adapter_version": MCP_ADAPTER_VERSION,
                "run_id": arguments["run_id"], "agent": arguments["agent"],
                "invocation_id": arguments["invocation_id"], "tool": "public_research.fetch",
                "input_hash": content_hash(arguments), "output_hash": content_hash(output),
                "artifact_ref": output["artifact_ref"], "access_mode": "read", "cache_hit": True,
            })
            return output
        if attempt.is_file():
            previous = _load_object(attempt)
            output = {**previous, "artifact_ref": str(attempt.relative_to(root)), "cache_hit": True}
            self.events.append({
                "event_type": "mcp_tool_result", "adapter_version": MCP_ADAPTER_VERSION,
                "run_id": arguments["run_id"], "agent": arguments["agent"],
                "invocation_id": arguments["invocation_id"], "tool": "public_research.fetch",
                "input_hash": content_hash(arguments), "output_hash": content_hash(output),
                "artifact_ref": output["artifact_ref"], "access_mode": "read", "cache_hit": True,
            })
            return output
        policy = _load_object(
            Path(__file__).resolve().parents[1] / "mcp/live/research-source-policy.json"
        )["sources"]["openalex"]
        if len(list(directory.glob("fetch-*.json"))) >= int(
            policy["request_budget"]["content_attempts_per_security"]
        ):
            raise ToolAccessError("PUBLIC_RESEARCH_CONTENT_BUDGET_EXHAUSTED")
        try:
            from product.mcp.live.cache import SnapshotCache
            from product.mcp.live.public_research import OpenAlexResearchClient
        except ModuleNotFoundError:
            from mcp.live.cache import SnapshotCache
            from mcp.live.public_research import OpenAlexResearchClient
        client = OpenAlexResearchClient(
            policy, SnapshotCache(root / ".material-cache"),
            api_key=os.environ.get("OPENALEX_API_KEY"),
        )
        try:
            document = client.fetch(candidate_matches[0])
        except ValueError as exc:
            failure_code = str(exc).split(":", 1)[0]
            if failure_code == "PUBLIC_RESEARCH_CONTENT_API_KEY_REQUIRED":
                attempt_status = "BLOCKED_CONFIGURATION"
            elif (
                failure_code.startswith("PUBLIC_RESEARCH_CONTENT_HTTP_")
                or failure_code in {
                    "PUBLIC_RESEARCH_TRANSPORT_FAILURE",
                    "PUBLIC_RESEARCH_CONTENT_NOT_AVAILABLE",
                    "PUBLIC_RESEARCH_CONTENT_GZIP_INVALID",
                    "PUBLIC_RESEARCH_CONTENT_XML_INVALID",
                    "PUBLIC_RESEARCH_CONTENT_EMPTY",
                }
            ):
                attempt_status = "SOURCE_LIMITED"
            else:
                raise
            failed = {
                "status": attempt_status, "attempt_status": attempt_status,
                "candidate_id": arguments["candidate_id"],
                "security_id": arguments["security_id"], "failure_code": failure_code,
                "provider_events": client.events, "document": None,
            }
            with attempt.open("x", encoding="utf-8") as stream:
                json.dump(failed, stream, ensure_ascii=False, sort_keys=True)
                stream.write("\n")
            output = {**failed, "artifact_ref": str(attempt.relative_to(root)), "cache_hit": False}
            self.events.append({
                "event_type": "mcp_tool_result", "adapter_version": MCP_ADAPTER_VERSION,
                "run_id": arguments["run_id"], "agent": arguments["agent"],
                "invocation_id": arguments["invocation_id"], "tool": "public_research.fetch",
                "input_hash": content_hash(arguments), "output_hash": content_hash(output),
                "artifact_ref": output["artifact_ref"], "access_mode": "read",
                "provider_events": client.events,
            })
            return output
        with existing.open("x", encoding="utf-8") as stream:
            json.dump(document, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
        successful_attempt = {
            "status": "READY", "attempt_status": "COMPLETED",
            "candidate_id": arguments["candidate_id"], "security_id": arguments["security_id"],
            "failure_code": None, "provider_events": client.events,
            "document_id": document["document_id"],
        }
        with attempt.open("x", encoding="utf-8") as stream:
            json.dump(successful_attempt, stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
        output = {
            "status": "READY", "document": document,
            "artifact_ref": str(existing.relative_to(root)),
            "attempt_ref": str(attempt.relative_to(root)), "cache_hit": False,
        }
        self.events.append({
            "event_type": "mcp_tool_result", "adapter_version": MCP_ADAPTER_VERSION,
            "run_id": arguments["run_id"], "agent": arguments["agent"],
            "invocation_id": arguments["invocation_id"], "tool": "public_research.fetch",
            "input_hash": content_hash(arguments), "output_hash": content_hash(output),
            "artifact_ref": output["artifact_ref"], "access_mode": "read",
            "provider_events": client.events,
        })
        return output

    def query(self, **arguments: Any) -> dict[str, Any]:
        run_dir = (
            arguments.pop("run_dir", None)
            if self.default_run_dir is not None else arguments.pop("run_dir")
        )
        tools = self._bound_tools(
            run_dir=run_dir,
            **{
                key: str(arguments[key])
                for key in ("run_id", "agent", "invocation_id")
            },
        )
        result = tools.query(**arguments)
        self.events.append(tools.events[-1])
        return result

    def calculate(self, **arguments: Any) -> dict[str, Any]:
        run_dir = (
            arguments.pop("run_dir", None)
            if self.default_run_dir is not None else arguments.pop("run_dir")
        )
        tools = self._bound_tools(
            run_dir=run_dir,
            **{
                key: str(arguments[key])
                for key in ("run_id", "agent", "invocation_id")
            },
        )
        result = tools.calculate(**arguments)
        self.events.append(tools.events[-1])
        return result


def _write_event(path: Path | None, event: Mapping[str, Any]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(canonical_json(event) + "\n")


def serve_stdio(
    *,
    gate_path: Path | None = None,
    run_id: str | None = None,
    agent: str | None = None,
    invocation_id: str | None = None,
    allowed_tools: Sequence[str] = (),
    event_log: Path | None = None,
    stateless: bool = False,
    default_run_dir: Path | None = None,
    tools_override=None,
) -> int:
    if tools_override is not None:
        tools = tools_override
    elif stateless:
        tools: GateScopedFixtureTools | StatelessFixtureTools = StatelessFixtureTools(
            default_run_dir=(
                default_run_dir or os.environ.get("STOCK_AGENT_FIXTURE_MCP_RUN_DIR")
            )
        )
    else:
        if gate_path is None or run_id is None:
            raise ToolAccessError("MISSING_BOUND_SERVER_ARGUMENTS")
        tools = GateScopedFixtureTools(
            _load_object(gate_path),
            run_id=run_id,
            agent=agent or "",
            invocation_id=invocation_id or "",
            allowed_tools=allowed_tools,
        )
    for line in sys.stdin:
        if not line.strip():
            continue
        request = json.loads(line)
        request_id = request.get("id")
        method = request.get("method")
        if method == "notifications/initialized":
            continue
        called_tool: str | None = None
        called_arguments: Mapping[str, Any] = {}
        try:
            if method == "initialize":
                result: dict[str, Any] = {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "live-gate-scoped" if tools_override is not None else "fixture-gate-scoped",
                        "version": tools.adapter_version if tools_override is not None else "2.0.0",
                    },
                }
            elif method == "tools/list":
                result = {"tools": list(tools.available_tools())}
            elif method == "tools/call":
                params = request.get("params", {})
                name = params.get("name")
                arguments = params.get("arguments", {})
                called_tool = str(name)
                called_arguments = arguments if isinstance(arguments, Mapping) else {}
                if name == "query":
                    value = tools.query(**arguments)
                elif name == "calculate":
                    value = tools.calculate(**arguments)
                elif name == "research_search":
                    value = tools.research_search(**arguments)
                elif name == "research_fetch":
                    value = tools.research_fetch(**arguments)
                elif name == "equity_research_attachments.query":
                    value = tools.equity_research_attachments_query(**arguments)
                else:
                    raise ToolAccessError(f"UNKNOWN_TOOL:{name}")
                result = {
                    "content": [{"type": "text", "text": canonical_json(value)}],
                    "structuredContent": value,
                    "isError": False,
                }
                _write_event(
                    event_log or tools.dynamic_event_log,
                    tools.events[-1],
                )
            else:
                raise ToolAccessError(f"UNKNOWN_METHOD:{method}")
            response = {"jsonrpc": "2.0", "id": request_id, "result": result}
        except (KeyError, TypeError, ValueError, ToolAccessError) as exc:
            error_message = (
                f"MISSING_TOOL_ARGUMENT:{exc.args[0]}"
                if isinstance(exc, KeyError) and exc.args
                else str(exc)
            )
            if called_tool is not None:
                _write_event(
                    event_log or tools.dynamic_event_log,
                    {
                        "event_type": "mcp_tool_error",
                        "adapter_version": getattr(tools, "adapter_version", MCP_ADAPTER_VERSION),
                        "tool": called_tool,
                        "input_hash": content_hash(called_arguments),
                        "error": error_message,
                        "access_mode": "read",
                    },
                )
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32001, "message": error_message},
            }
        sys.stdout.write(canonical_json(response) + "\n")
        sys.stdout.flush()
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the gate-scoped fixture MCP server")
    parser.add_argument("--stateless", action="store_true")
    parser.add_argument("--gate", type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--agent")
    parser.add_argument("--invocation-id")
    parser.add_argument(
        "--allowed-tool",
        action="append",
        choices=tuple(sorted(SUPPORTED_TOOLS)),
        default=[],
    )
    parser.add_argument("--event-log", type=Path)
    parser.add_argument("--default-run-dir", type=Path)
    args = parser.parse_args(argv)
    if not args.stateless and (
        args.gate is None
        or not args.run_id
        or not args.agent
        or not args.invocation_id
        or not args.allowed_tool
    ):
        parser.error("bound mode requires gate, run, identity, and allowed tools")
    return serve_stdio(
        gate_path=args.gate,
        run_id=args.run_id,
        agent=args.agent,
        invocation_id=args.invocation_id,
        allowed_tools=args.allowed_tool,
        event_log=args.event_log,
        stateless=args.stateless,
        default_run_dir=args.default_run_dir,
    )


if __name__ == "__main__":
    raise SystemExit(main())
