"""Run-scoped, fixture-only MCP tools backed by an Evidence Gate artifact."""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, DivisionByZero, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    # Repository execution: ``python -m product.runtime.fixture_mcp``.
    from product.mcp.provenance import canonical_json, content_hash
except ModuleNotFoundError as exc:
    # Installed-plugin execution: the cachebuster directory is the import root,
    # so the same module is addressed as ``runtime.fixture_mcp``.
    if exc.name != "product":
        raise
    from mcp.provenance import canonical_json, content_hash


MCP_ADAPTER_VERSION = "fixture-gate-scoped/2.1.1"
SUPPORTED_TOOLS = {"fixture_evidence.query", "fixture_math.calculate"}


class ToolAccessError(ValueError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, Mapping):
        raise ToolAccessError("INVALID_JSON_OBJECT")
    return dict(value)


def _tool_manifest(*, stateless: bool = False) -> tuple[dict[str, Any], ...]:
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
    return (
        {
            "name": "query",
            "description": "Read Gate-allowed fixture evidence for one verified invocation.",
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
                "Calculate from exactly two Gate-allowed numeric Evidence IDs. Required "
                "arguments are run_dir (stateless mode), run_id, agent, invocation_id, "
                "calculation_id, operation ('ratio' or 'percent_change'), and evidence_ids. "
                "For ratio, evidence_ids are in numerator-then-denominator sequence; for "
                "percent_change, earlier then later. Do not send operands or expression."
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
                    "operation": {"enum": ["ratio", "percent_change"]},
                    "evidence_ids": {
                        "type": "array",
                        "minItems": 2,
                        "maxItems": 2,
                        "items": {"type": "string"},
                    },
                },
                "additionalProperties": False,
            },
        },
    )


class GateScopedFixtureTools:
    """Expose only Gate-admitted facts for one immutable invocation identity."""

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
                "adapter_version": MCP_ADAPTER_VERSION,
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
            "adapter_version": MCP_ADAPTER_VERSION,
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
        facts = self._authorize_evidence(run_id, evidence_ids)
        if len(facts) != 2:
            raise ToolAccessError("CALCULATION_REQUIRES_TWO_FACTS")
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
            "adapter_version": MCP_ADAPTER_VERSION,
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

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []
        self.dynamic_event_log: Path | None = None

    @staticmethod
    def tool_manifest() -> tuple[dict[str, Any], ...]:
        return _tool_manifest(stateless=True)

    def available_tools(self) -> tuple[dict[str, Any], ...]:
        return self.tool_manifest()

    def _bound_tools(
        self, *, run_dir: str, run_id: str, agent: str, invocation_id: str
    ) -> GateScopedFixtureTools:
        root = Path(run_dir).resolve()
        run_manifest_path = root / "run_manifest.json"
        gate_path = root / "evidence" / "gate.json"
        invocation_path = root / "invocations" / f"{agent}.json"
        if not all(
            path.is_file()
            for path in (run_manifest_path, gate_path, invocation_path)
        ):
            raise ToolAccessError("RUN_PACKAGE_BINDING_MISSING")
        run_manifest = _load_object(run_manifest_path)
        gate = _load_object(gate_path)
        invocation = _load_object(invocation_path)
        if Path(str(run_manifest.get("output_dir", ""))).resolve() != root:
            raise ToolAccessError("RUN_DIRECTORY_MISMATCH")
        if (
            run_manifest.get("run_id") != run_id
            or gate.get("run_id") != run_id
            or invocation.get("run_id") != run_id
            or invocation.get("invocation_id") != invocation_id
            or invocation.get("agent", {}).get("name") != agent
        ):
            raise ToolAccessError("INVOCATION_IDENTITY_MISMATCH")
        fixture_path = Path(str(run_manifest.get("fixture", ""))).resolve()
        product_root = Path(
            str(run_manifest.get("discovery", {}).get("product_root", ""))
        ).resolve()
        repository_root = product_root.parent
        if product_root.name != "product":
            raise ToolAccessError("INVALID_PRODUCT_DISCOVERY_ROOT")
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
        )

    def query(self, **arguments: Any) -> dict[str, Any]:
        run_dir = str(arguments.pop("run_dir"))
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
        run_dir = str(arguments.pop("run_dir"))
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
) -> int:
    if stateless:
        tools: GateScopedFixtureTools | StatelessFixtureTools = StatelessFixtureTools()
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
                        "name": "fixture-gate-scoped",
                        "version": "2.0.0",
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
        except (TypeError, ValueError, ToolAccessError) as exc:
            if called_tool is not None:
                _write_event(
                    event_log or tools.dynamic_event_log,
                    {
                        "event_type": "mcp_tool_error",
                        "adapter_version": MCP_ADAPTER_VERSION,
                        "tool": called_tool,
                        "input_hash": content_hash(called_arguments),
                        "error": str(exc),
                        "access_mode": "read",
                    },
                )
            response = {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32001, "message": str(exc)},
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
    )


if __name__ == "__main__":
    raise SystemExit(main())
