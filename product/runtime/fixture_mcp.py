"""Run-scoped, fixture-only MCP tools backed by an Evidence Gate artifact."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import secrets
import sys
from decimal import Decimal, DivisionByZero, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    # Repository execution: ``python -m product.runtime.fixture_mcp``.
    from product.mcp.provenance import canonical_json, content_hash
    from product.runtime.hashing import canonical_hash, legacy_envelope_hash
    from product.runtime.monetary import convert_monetary_value, MONETARY_SCALE_FACTORS, scale_factor
    from product.runtime.schema_validation import validate_schema_instance
except ModuleNotFoundError as exc:
    # Installed-plugin execution: the cachebuster directory is the import root,
    # so the same module is addressed as ``runtime.fixture_mcp``.
    if exc.name != "product":
        raise
    from mcp.provenance import canonical_json, content_hash
    from runtime.hashing import canonical_hash, legacy_envelope_hash
    from runtime.monetary import convert_monetary_value, MONETARY_SCALE_FACTORS, scale_factor
    from runtime.schema_validation import validate_schema_instance


MCP_ADAPTER_VERSION = "fixture-gate-scoped/2.5.0"
TASK_TOOL_IDENTITY_VERSION = "research-tool-identity/1.0.0"
COMMON_STOCK_FIELD_QUERY_ADAPTER_VERSION = "fixture-gate-scoped/2.4.0"
SKEPTIC_ADAPTER_VERSION = "fixture-gate-scoped/2.3.0"
COMMON_STOCK_FIELD_QUERY_MAX_BYTES = 65536
SUPPORTED_TOOLS = {
    "fixture_evidence.query", "fixture_math.calculate",
    "public_research.search", "public_research.fetch",
    "equity_research_attachments.query",
    "research_report.submit",
    "research_reports.read",
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
    common_stock_field_query: bool = False,
    server_calculation_ids: bool = False,
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
                + ("operation (calculation_id is optional legacy compatibility), "
                   if server_calculation_ids else "calculation_id, operation ")
                + "('ratio', 'percent_change', "
                "'institutional_period_change', or 'monetary_scale'), "
                "and evidence_ids. "
                "For ratio, evidence_ids are in numerator-then-denominator sequence; for "
                "percent_change and institutional_period_change, earlier then later. "
                "institutional_period_change compares two completed periods from the same "
                "supplier and security. monetary_scale accepts exactly one Evidence "
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
                    "operation": {"enum": [
                        "ratio", "percent_change", "institutional_period_change",
                        "monetary_scale",
                    ]},
                    "evidence_ids": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 2,
                        "items": {"type": "string"},
                    },
                    "target_scale": {
                        "enum": list(MONETARY_SCALE_FACTORS)
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
    if server_calculation_ids:
        calculate = next(item for item in tools if item["name"] == "calculate")
        calculate["inputSchema"]["required"].remove("calculation_id")
        calculate["description"] = (
            "For reference_transport_version=multidimensional-references/2.0.0 tasks, "
            "omit calculation_id: the server assigns a unique ID after authorization. "
            "An explicit nonempty ID is supported only for existing call compatibility. "
            + calculate["description"]
        )
    if common_stock_field_query:
        query = tools[0]
        query["description"] = (
            "Read one verified common-stock invocation by either evidence_ids or one "
            "exact semantic_field. Field mode returns every authorized period or fails "
            "without partial results. " + run_binding + "."
        )
        query["inputSchema"] = {
            "type": "object",
            "required": common_required[:-1],
            "properties": {
                **common_properties,
                "semantic_field": {"type": "string", "minLength": 1},
            },
            "oneOf": [
                {"required": ["evidence_ids"], "not": {"required": ["semantic_field"]}},
                {"required": ["semantic_field"], "not": {"required": ["evidence_ids"]}},
            ],
            "additionalProperties": False,
        }
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
        field_evidence_ids: Sequence[str] | None = None,
        field_security_id: str | None = None,
        industry_peer_security_ids: Sequence[str] | None = None,
        adapter_version: str = MCP_ADAPTER_VERSION,
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
        self.adapter_version = adapter_version
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
        if field_evidence_ids is not None and (
            field_security_id is None or not set(field_evidence_ids) <= set(self._facts)
        ):
            raise ToolAccessError("FIELD_QUERY_SCOPE_INVALID")
        self._field_evidence_ids = (
            frozenset(field_evidence_ids) if field_evidence_ids is not None else None
        )
        self._field_security_id = field_security_id
        self._industry_peer_security_ids = frozenset(industry_peer_security_ids or ())
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
                "output_bytes": len(canonical_json(output).encode("utf-8")),
                "evidence_ids": list(inputs.get("evidence_ids", [])),
                "access_mode": "read",
            }
        if "calculation_id" in inputs:
            event["calculation_id"] = inputs["calculation_id"]
        if "operation" in inputs:
            event["operation"] = inputs["operation"]
        if "target_scale" in inputs:
            event["target_scale"] = inputs["target_scale"]
        event["event_hash"] = legacy_envelope_hash(event, hash_field="event_hash")
        self.events.append(event)

    def query(
        self,
        *,
        run_id: str,
        agent: str,
        invocation_id: str,
        evidence_ids: Sequence[str] | None = None,
        semantic_field: str | None = None,
    ) -> dict[str, Any]:
        self._authorize_identity(agent=agent, invocation_id=invocation_id)
        if "fixture_evidence.query" not in self.allowed_tools:
            raise ToolAccessError("TOOL_NOT_AUTHORIZED:fixture_evidence.query")
        if (evidence_ids is None) == (semantic_field is None):
            raise ToolAccessError("EVIDENCE_QUERY_SELECTOR_INVALID")
        if semantic_field is not None:
            if run_id != self.run_id:
                raise ToolAccessError("CROSS_RUN_QUERY")
            if not isinstance(semantic_field, str) or not semantic_field.strip():
                raise ToolAccessError("EVIDENCE_QUERY_FIELD_EMPTY")
            if self._field_evidence_ids is None or self._field_security_id is None:
                raise ToolAccessError("COMMON_STOCK_FIELD_QUERY_FORBIDDEN")
            selected_ids = sorted(
                evidence_id for evidence_id in self._field_evidence_ids
                if self._facts[evidence_id].get("security_id") == self._field_security_id
                and self._facts[evidence_id].get("semantic_field") == semantic_field
            )
            facts = self._authorize_evidence(run_id, selected_ids) if selected_ids else []
        else:
            selected_ids = list(evidence_ids or [])
            facts = self._authorize_evidence(run_id, selected_ids)
        if len({fact.get("security_id") for fact in facts} & self._industry_peer_security_ids) > 1:
            raise ToolAccessError("INDUSTRY_PEER_QUERY_MIXED:query one frozen peer at a time")
        inputs = {
            "run_id": run_id,
            "agent": agent,
            "invocation_id": invocation_id,
            "evidence_ids": selected_ids,
        }
        if semantic_field is not None:
            inputs["semantic_field"] = semantic_field
        output = {
            "adapter_version": self.adapter_version,
            "run_id": self.run_id,
            "evidence": facts,
            "result_hash": content_hash(facts),
        }
        if semantic_field is not None and len(canonical_json(output).encode("utf-8")) > COMMON_STOCK_FIELD_QUERY_MAX_BYTES:
            raise ToolAccessError("FIELD_QUERY_RESPONSE_TOO_LARGE:use evidence_ids batches")
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
            scale_factor(target_scale)
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
        if operation == "institutional_period_change":
            first, second = facts
            if (
                first.get("security_id") != second.get("security_id")
                or first.get("source_id") != second.get("source_id")
                or not all(
                    str(fact.get("semantic_field", "")).startswith("moomoo_institutional_aggregate:")
                    and isinstance(fact.get("value"), dict)
                    and fact["value"].get("period_provisional") is False
                    and isinstance(fact["value"].get("period_end"), str)
                    and isinstance(fact["value"].get("period_label"), str)
                    for fact in facts
                )
                or first["value"]["period_end"] >= second["value"]["period_end"]
            ):
                raise ToolAccessError("INSTITUTIONAL_PERIODS_NOT_COMPARABLE")
            changes = {}
            try:
                for field in (
                    "institution_count", "aggregate_holder_quantity",
                    "aggregate_holder_percent",
                ):
                    earlier = Decimal(str(first["value"][field]))
                    later = Decimal(str(second["value"][field]))
                    delta = later - earlier
                    changes[field] = {
                        "earlier": format(earlier, "f"),
                        "later": format(later, "f"),
                        "absolute_change": format(delta, "f"),
                        "relative_change": (
                            format(delta / earlier, "f") if earlier != 0 else None
                        ),
                    }
            except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
                raise ToolAccessError("INSTITUTIONAL_PERIOD_VALUE_INVALID") from exc
            output = {
                "adapter_version": self.adapter_version,
                "run_id": self.run_id,
                "calculation_id": calculation_id,
                "operation": operation,
                "evidence_ids": list(evidence_ids),
                "earlier_period": first["value"]["period_label"],
                "later_period": second["value"]["period_label"],
                "changes": changes,
            }
            output["calculation_hash"] = content_hash(output)
            self._record("fixture_math.calculate", inputs, output)
            return output
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
        self._last_reference_map: dict[str, Any] | None = None

    @staticmethod
    def tool_manifest() -> tuple[dict[str, Any], ...]:
        # 未绑定目录时尚不知道调用的协议。支持当前服务端编号参数，
        # 每次调用仍按真实任务版本/权限检查；旧协议无 ID 必须拒绝。
        return _tool_manifest(stateless=True, server_calculation_ids=True)

    def available_tools(self) -> tuple[dict[str, Any], ...]:
        # A launcher-bound run directory removes ``run_dir`` from every public
        # tool schema, but it must not hide the material-preparation tools. The
        # previous implementation coupled these two concerns and caused real
        # Codex agents to see only query/calculate during research discovery.
        server_calculation_ids = self.default_run_dir is None
        if self.default_run_dir is not None:
            run = _load_object(self.default_run_dir / "run_manifest.json")
            server_calculation_ids = run.get("reference_transport_version") == "multidimensional-references/2.0.0"
        manifest = _tool_manifest(
            stateless=self.default_run_dir is None,
            include_research_tools=True,
            include_attachment_tool=self.default_run_dir is not None,
            common_stock_field_query=(
                self.default_run_dir is not None
                and _load_object(self.default_run_dir / "run_manifest.json").get("stage")
                == "COMMON_STOCK_RESEARCH"
            ),
            server_calculation_ids=server_calculation_ids,
        )
        if self.default_run_dir is not None:
            # 工具目录可能在 prepare-cio 之前缓存；授权仍在每次调用时核验。
            identity = {key: {"type": "string"} for key in ("run_id", "agent", "invocation_id")}
            run = _load_object(self.default_run_dir / "run_manifest.json")
            report_description = "CIO only: read complete authorized reports by exact report_ids; runtime records delivery. Requires a prepared native CIO invocation with research_reports.read permission. Other roles cannot use this tool."
            if run.get("report_delivery_version") == "cio-report-delivery/1.0.0":
                report_description += (" Repeated calculation input_evidence_refs may be {input_evidence_ref_set: key};"
                    " the full ordered list is in this response's report_delivery.input_evidence_ref_sets[key]."
                    " This is lossless sharing, not a summary or an Evidence ID; do not query the shared key or reread to obtain duplicates.")
            if run.get("stage") in {None, "PREDECISION_CIO_SYNTHESIS"} and run.get("source_mode") != "live":
                manifest += ({
                    "name": "read_reports", "description": report_description,
                    "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
                    "inputSchema": {"type": "object", "additionalProperties": False,
                                    "required": [*identity, "report_ids"], "properties": {
                                        **identity, "report_ids": {"type": "array", "minItems": 1,
                                                                   "uniqueItems": True, "items": {"type": "string"}},
                                    }},
                },)
            index_path = self.default_run_dir / "research/dispatch-index.json"
            if index_path.is_file():
                from product.runtime.research_submission import WRITE_VERSIONS, tool_manifest
                if any(t.get("submission_version") in WRITE_VERSIONS for t in _load_object(index_path).get("tasks", [])):
                    manifest += (tool_manifest(),)
            from product.runtime.research_input import is_single_stock
            if is_single_stock(run) and run.get("stage") == "INDEPENDENT_COUNTER_THESIS_RESEARCH":
                from product.runtime.independent_skeptic_stage import DELIVERY_VERSION, read_dispatch_index
                try:
                    skeptic_index = read_dispatch_index(self.default_run_dir, os.environ.get("STOCK_AGENT_SKEPTIC_DISPATCH_INDEX"))
                except (OSError, ValueError):
                    skeptic_index = {"tasks": []}  # The forward-only stage has no skeptic invocation yet.
                if any(_load_object(self.default_run_dir / t["invocation_ref"]).get("skeptic_delivery_version") == DELIVERY_VERSION
                       for t in skeptic_index["tasks"]):
                    manifest += ({
                        "name": "evidence_catalog",
                        "description": "New independent Skeptic tasks only: discover task-authorized metadata, not facts or Analyst conclusions. Use view=fields to discover indicators, view=records to select IDs; then query the chosen IDs. Follow next_offset; unvisited pages are not missing sources. Bound identity required, no run_dir.",
                        "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
                        "inputSchema": {"type": "object", "additionalProperties": False,
                            "required": [*identity, "view"], "properties": {
                                **identity, "view": {"enum": ["fields", "records"]},
                                "security_id": {"type": "string", "minLength": 1},
                                "semantic_field": {"type": "string", "minLength": 1, "maxLength": 256},
                                "semantic_field_prefix": {"type": "string", "minLength": 1, "maxLength": 256},
                                "offset": {"type": "integer", "minimum": 0},
                                "limit": {"type": "integer", "minimum": 1, "maximum": 64},
                            }},
                    },)
            single_forward_state = (is_single_stock(run)
                                    and run.get("stage") == "INDEPENDENT_COUNTER_THESIS_RESEARCH")
            if single_forward_state or run.get("tool_identity_version") == TASK_TOOL_IDENTITY_VERSION:
                if not single_forward_state and run.get("stage") != "MULTI_DIMENSIONAL_HOLDING_RESEARCH":
                    raise ToolAccessError("TASK_TOOL_IDENTITY_STAGE_INVALID")
                # Preserve a rejected first routing attempt too, before any successful binding.
                self.dynamic_event_log = self.default_run_dir / "events/mcp/events.jsonl"
                manifest += ({
                    "name": "research_task_state",
                    "description": "Coordinator: read the bound run's verified Hook task states before dispatch, after wait and before completion. No report bodies or research decisions; TERMINAL/SAVED does not mean content PASS. No arguments, dispatch or retry side effects.",
                    "annotations": {"readOnlyHint": True, "destructiveHint": False, "openWorldHint": False},
                    "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}},
                },)
                if single_forward_state:
                    # State-only reuse: preserve the existing explicit Invocation
                    # identity and permissions for every research tool.
                    return manifest
                for item in manifest:
                    if item["name"] not in {"query", "calculate", "research_report_submit"}:
                        continue
                    schema = item["inputSchema"]
                    for key in ("run_id", "agent", "invocation_id", "run_dir"):
                        schema["properties"].pop(key, None)
                    schema["required"] = [key for key in schema["required"]
                                          if key not in {"run_id", "agent", "invocation_id", "run_dir"}]
                    schema["properties"]["task_name"] = {"type": "string", "minLength": 1}
                    schema["required"].append("task_name")
                    item["description"] = (
                        "Use the exact task_name from your frozen task as the sole technical routing argument; "
                        "do not pass run_id, agent, invocation_id or run_dir. Runtime binds the existing Invocation "
                        "and permissions; task_name is not caller authentication. "
                        + ("Choose operation and evidence_ids as specified by inputSchema; no operands/expression."
                           if item["name"] == "calculate" else
                           "Choose research fields as specified by inputSchema; all original gates remain active.")
                    )
        return manifest

    def research_task_state(self) -> dict[str, Any]:
        if self.default_run_dir is None:
            raise ToolAccessError("TASK_STATE_BOUND_RUN_REQUIRED")
        from product.runtime.multidimensional_stage import read_multidimensional_task_state
        from product.runtime.independent_skeptic_stage import DELIVERY_VERSION, read_dispatch_index, read_skeptic_task_state
        index_ref = os.environ.get("STOCK_AGENT_SKEPTIC_DISPATCH_INDEX")
        new_skeptic = False
        if index_ref is not None:
            index = read_dispatch_index(self.default_run_dir, index_ref)
            new_skeptic = bool(index["tasks"]) and all(
                _load_object(self.default_run_dir / task["invocation_ref"]).get("skeptic_delivery_version") == DELIVERY_VERSION
                for task in index["tasks"])
        result = (read_skeptic_task_state(self.default_run_dir, index_ref=index_ref) if new_skeptic
                  else read_multidimensional_task_state(self.default_run_dir))
        event = {"event_type": "mcp_tool_result", "tool": "research_task_state",
                 "run_id": result["run_id"], "invocation_id": None, "input_hash": canonical_hash({}),
                 "output_hash": canonical_hash(result), "output_bytes": len(canonical_json(result).encode("utf-8")),
                 "task_state_snapshot": result}
        event["event_hash"] = legacy_envelope_hash(event, hash_field="event_hash")
        self.events.append(event)
        self.dynamic_event_log = self.default_run_dir / "events/mcp/events.jsonl"
        return result

    def bind_task_tool_arguments(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Normalize a versioned task locator, not an Agent's research choices."""
        if self.default_run_dir is None or name not in {"query", "calculate", "research_report_submit"}:
            raise ToolAccessError("TASK_TOOL_IDENTITY_NOT_ENABLED")
        root = self.default_run_dir
        manifest = _load_object(root / "run_manifest.json")
        index = _load_object(root / "research/dispatch-index.json")
        if (manifest.get("tool_identity_version") != TASK_TOOL_IDENTITY_VERSION
                or manifest.get("stage") != "MULTI_DIMENSIONAL_HOLDING_RESEARCH"):
            raise ToolAccessError("TASK_TOOL_IDENTITY_NOT_ENABLED")
        if any(key in arguments for key in ("run_id", "agent", "invocation_id", "run_dir")):
            raise ToolAccessError("TASK_TOOL_IDENTITY_MIXED_ARGUMENTS")
        if (manifest.get("manifest_hash") != legacy_envelope_hash(manifest, hash_field="manifest_hash")
                or index.get("index_hash") != legacy_envelope_hash(index, hash_field="index_hash")
                or manifest.get("dispatch_index_hash") != index.get("index_hash")
                or manifest.get("run_id") != index.get("run_id")
                or Path(str(manifest.get("output_dir", ""))).resolve() != root):
            raise ToolAccessError("TASK_TOOL_IDENTITY_BINDING_INVALID")
        tasks = [t for t in index.get("tasks", []) if t.get("task_name") == arguments.get("task_name")]
        if len(tasks) != 1:
            raise ToolAccessError("TASK_TOOL_IDENTITY_UNKNOWN_OR_AMBIGUOUS")
        task = tasks[0]
        if task.get("tool_identity_version") != TASK_TOOL_IDENTITY_VERSION:
            raise ToolAccessError("TASK_TOOL_IDENTITY_BINDING_INVALID")
        identity = {key: task[key] for key in ("run_id", "agent", "invocation_id")}
        # Existing packet, Invocation, Gate, evidence scope and permissions remain authoritative.
        self._bound_tools(run_dir=None, **identity)
        from product.runtime.multidimensional_references import load_reference_packet
        packet = load_reference_packet(root, identity["invocation_id"])
        if packet["task"].get("tool_identity_version") != TASK_TOOL_IDENTITY_VERSION:
            raise ToolAccessError("TASK_TOOL_IDENTITY_BINDING_INVALID")
        invocation_path = (root / task["invocation_path"]).resolve()
        if not invocation_path.is_relative_to(root):
            raise ToolAccessError("TASK_TOOL_IDENTITY_BINDING_INVALID")
        invocation = _load_object(invocation_path)
        if (invocation.get("manifest_hash") != legacy_envelope_hash(invocation, hash_field="manifest_hash")
                or any(invocation.get(key) != identity[key] for key in ("run_id", "invocation_id"))
                or invocation != self._last_invocation):
            raise ToolAccessError("TASK_TOOL_IDENTITY_BINDING_INVALID")
        normalized = {key: value for key, value in arguments.items() if key != "task_name"}
        return {**normalized, **({"invocation_id": identity["invocation_id"]}
                                 if name == "research_report_submit" else identity)}

    def evidence_catalog(self, *, run_id: str, agent: str, invocation_id: str, **selectors) -> dict[str, Any]:
        if self.default_run_dir is None or agent != "runtime_skeptic":
            raise ToolAccessError("COUNTER_CATALOG_NOT_AUTHORIZED")
        bound = self._bound_tools(run_dir=None, run_id=run_id, agent=agent, invocation_id=invocation_id)
        from product.runtime.research_input import is_single_stock
        from product.runtime.independent_skeptic_stage import (
            build_skeptic_dispatch_packet, read_dispatch_index, read_skeptic_evidence_catalog,
        )
        root = self._last_root
        if not is_single_stock(_load_object(root / "run_manifest.json")) or "fixture_evidence.query" not in bound.allowed_tools:
            raise ToolAccessError("COUNTER_CATALOG_NOT_AUTHORIZED")
        index_ref = os.environ.get("STOCK_AGENT_SKEPTIC_DISPATCH_INDEX")
        task = next(t for t in read_dispatch_index(root, index_ref)["tasks"] if t["invocation_id"] == invocation_id)
        packet = build_skeptic_dispatch_packet(Path(__file__).resolve().parents[2], root, task["task_name"], index_ref=index_ref)
        result = read_skeptic_evidence_catalog(packet, _load_object(root / "evidence/gate.json"), **selectors)
        event = {"event_type": "mcp_tool_result", "tool": "fixture_evidence.catalog", "access_mode": "read",
                 "run_id": run_id, "agent": agent, "invocation_id": invocation_id,
                 "adapter_version": SKEPTIC_ADAPTER_VERSION, "input_hash": content_hash(selectors),
                 "output_hash": content_hash(result), "output_bytes": len(canonical_json(result).encode()),
                 "returned_rows": len(result["rows"])}
        self.events.append({**event, "event_hash": content_hash(event)})
        return result

    def read_reports(self, *, run_id: str, agent: str, invocation_id: str,
                     report_ids: list[str]) -> dict[str, Any]:
        if self.default_run_dir is None or agent != "runtime_cio":
            raise ToolAccessError("CIO_REPORT_READ_NOT_AUTHORIZED")
        self._bound_tools(run_dir=None, run_id=run_id, agent=agent, invocation_id=invocation_id)
        from product.runtime.cio_handoff import read_cio_reports
        root = self._last_root
        invocation = self._last_invocation
        manifest = _load_object(root / "run_manifest.json")
        predecision = manifest.get("stage") == "PREDECISION_CIO_SYNTHESIS"
        if not predecision:
            from product.runtime.invocation import verify_invocation_manifest
            repository = Path(manifest["discovery"]["product_root"]).resolve().parent
            verify_invocation_manifest(repository, invocation,
                                       agent_input=_load_object(root / "inputs/runtime_cio.json"))
        catalog = (manifest["report_catalog"] if predecision else invocation.get("report_catalog", []))
        mapping = self._last_reference_map
        if mapping is not None:
            if any(ref not in mapping.get("reports", {}) for ref in report_ids):
                raise ToolAccessError("CIO_REPORT_REFERENCE_UNKNOWN")
            from product.runtime.multidimensional_references import translate_references
            report_ids = translate_references({"report_ids": report_ids}, mapping)["report_ids"]
        output, event = read_cio_reports(root, invocation, catalog, report_ids,
                                        prefix="source-inputs" if predecision else "")
        self.events.append(event)
        from product.runtime.cio_handoff import cio_report_model_result
        return cio_report_model_result(output, event, invocation, mapping)

    def research_report_submit(self, *, invocation_id: str, draft: dict[str, Any], submission_token: str | None = None) -> dict[str, Any]:
        if self.default_run_dir is None:
            raise ToolAccessError("RESEARCH_SUBMISSION_BOUND_RUN_REQUIRED")
        from product.runtime.research_submission import submit, submission_event_identity
        result = submit(self.default_run_dir, invocation_id, draft, submission_token=submission_token)
        self.dynamic_event_log = self.default_run_dir / "events/mcp/events.jsonl"
        identity = submission_event_identity(self.default_run_dir, invocation_id,
                                             result["submission"], result["content_hash"],
                                             require_event=False)
        event = {**identity, "event_type": "research_submission", "tool": "research_report.submit",
                 "submission": result["submission"], "output_hash": result["content_hash"],
                 "review_hash": content_hash({
                     "citation_review": result["citation_review"],
                     "monetary_review": result["monetary_review"],
                     "source_evidence_review": result["source_evidence_review"],
                 }),
                 "citation_pair_count": result["citation_review"]["pair_count"],
                 "monetary_finding_count": result["monetary_review"].get("finding_count", 0),
                 "source_review_pair_count": result["source_evidence_review"]["pair_count"]}
        if "repair_binding_hash" in result:
            event["repair_binding_hash"] = result["repair_binding_hash"]
        self.events.append({**event, "event_hash": content_hash(event)})
        return result

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
        if run_manifest.get("stage") == "PREDECISION_CIO_SYNTHESIS":
            if agent != "runtime_cio":
                raise ToolAccessError("CIO_STAGE_AGENT_FORBIDDEN")
            from product.runtime.predecision_cio_stage import validate_predecision_cio_run
            validate_predecision_cio_run(Path(__file__).resolve().parents[2], root)
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
            "PREDECISION_CIO_SYNTHESIS",
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
        field_ids: list[str] | None = None
        field_security_id: str | None = None
        self._last_reference_map = None
        multidimensional_ids = None
        industry_peer_security_ids = None
        if run_manifest.get("stage") == "PREDECISION_CIO_SYNTHESIS":
            from product.runtime.cio_handoff import build_cio_reference_map
            self._last_reference_map = build_cio_reference_map(root, invocation, run_manifest["report_catalog"])
        elif agent == "runtime_cio" and invocation.get("draft_delivery") == "native-cio-draft/1.0.0":
            from product.runtime.cio_handoff import build_cio_reference_map, fixture_cio_model_input
            from product.runtime.invocation import verify_invocation_manifest
            agent_input = _load_object(root / "inputs/runtime_cio.json")
            verify_invocation_manifest(repository_root, invocation, agent_input=agent_input)
            if invocation.get("reference_transport_version") != run_manifest.get("cio_reference_transport_version"):
                raise ToolAccessError("CIO_REFERENCE_PROTOCOL_INVALID")
            self._last_reference_map = build_cio_reference_map(root, invocation, invocation["report_catalog"])
            if self._last_reference_map is not None:
                if _load_object(root / "inputs/runtime_cio.model.json") != fixture_cio_model_input(root, agent_input):
                    raise ToolAccessError("CIO_MODEL_INPUT_DRIFT")
                multidimensional_ids = invocation["evidence_ids"]
        if skeptic_scope is not None:
            from product.runtime.multidimensional_references import load_reference_packet
            packet = load_reference_packet(
                root, invocation_id, index_ref=os.environ.get("STOCK_AGENT_SKEPTIC_DISPATCH_INDEX"),
            )
            self._last_reference_map = packet.get("reference_map")
        if (run_manifest.get("stage") == "MULTI_DIMENSIONAL_HOLDING_RESEARCH"
                or (run_manifest.get("stage") == "INDEPENDENT_COUNTER_THESIS_RESEARCH"
                    and skeptic_scope is None)):
            from product.runtime.multidimensional_references import load_reference_packet
            packet = load_reference_packet(root, invocation_id)
            self._last_reference_map = packet.get("reference_map")
            if self._last_reference_map is not None:
                multidimensional_ids = packet["allowed_evidence_ids"]
            if packet.get("task", {}).get("industry_source_boundary") == "industry-source-boundary/1.0.0":
                industry_peer_security_ids = [
                    candidate["materialized_security_id"]
                    for candidate in packet["task"].get("selected_peer_candidates", [])
                    if candidate.get("materialization_status") == "FROZEN"
                    and isinstance(candidate.get("materialized_security_id"), str)
                ]
        if run_manifest.get("stage") == "COMMON_STOCK_RESEARCH":
            if agent != "runtime_company_analyst":
                raise ToolAccessError("COMMON_STOCK_AGENT_INVALID")
            from product.runtime.multidimensional_references import load_reference_packet
            packet = load_reference_packet(root, invocation_id)
            self._last_reference_map = packet.get("reference_map")
            if self._last_reference_map is not None:
                multidimensional_ids = packet["allowed_evidence_ids"]
            index = _load_object(root / "research/dispatch-index.json")
            tasks = [
                item for item in index.get("tasks", [])
                if item.get("invocation_id") == invocation_id
            ]
            if len(tasks) != 1:
                raise ToolAccessError("COMMON_STOCK_TASK_BINDING_INVALID")
            task = tasks[0]
            request_path = (root / str(task.get("request_path", ""))).resolve()
            if not request_path.is_relative_to(root) or not request_path.is_file():
                raise ToolAccessError("COMMON_STOCK_REQUEST_PATH_INVALID")
            request = _load_object(request_path)
            field_security_id = task.get("security_id")
            if (
                request.get("run_id") != run_id
                or request.get("invocation_id") != invocation_id
                or request.get("security", {}).get("security_id") != field_security_id
                or not isinstance(field_security_id, str)
                or task.get("request_path") != invocation.get("request_path")
            ):
                raise ToolAccessError("COMMON_STOCK_REQUEST_BINDING_INVALID")
            try:
                from product.runtime.common_stock_stage import _is_company_research_evidence
            except ModuleNotFoundError as exc:
                if exc.name != "product":
                    raise
                from runtime.common_stock_stage import _is_company_research_evidence
            requested = set(request["allowed_evidence_ids"])
            field_ids = [
                item["evidence_id"] for item in gate["allowed_evidence"]
                if item["evidence_id"] in requested
                and item.get("security_id") == field_security_id
                and _is_company_research_evidence(item)
            ]
        adapter_version = MCP_ADAPTER_VERSION
        if skeptic_scope is not None:
            adapter_version = SKEPTIC_ADAPTER_VERSION
        elif field_ids is not None:
            adapter_version = COMMON_STOCK_FIELD_QUERY_ADAPTER_VERSION
        try:
            from .versioning import approved_component_version, load_version_manifest
            scope = ("independent-skeptic-query" if skeptic_scope is not None else
                     "common-stock-field-query" if field_ids is not None else "fixture-gate-scoped")
            approved_component_version(load_version_manifest(product_root / "version-manifest.json"),
                                       "mcp_adapters", scope,
                                       observed=adapter_version.rsplit("/", 1)[-1])
        except ValueError as exc:
            raise ToolAccessError(str(exc)) from exc
        return GateScopedFixtureTools(
            gate,
            run_id=run_id,
            agent=agent,
            invocation_id=invocation_id,
            allowed_tools=invocation.get("tool_permissions", []),
            allowed_evidence_ids=(skeptic_scope[1] if skeptic_scope is not None else multidimensional_ids),
            field_evidence_ids=field_ids,
            field_security_id=field_security_id,
            industry_peer_security_ids=industry_peer_security_ids,
            adapter_version=adapter_version,
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
            "artifact_ref": output["artifact_ref"],
            "artifact_sha256": hashlib.sha256((root / output["artifact_ref"]).read_bytes()).hexdigest(),
            "access_mode": "read",
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
        if self._last_reference_map is not None:
            from product.runtime.multidimensional_references import translate_references
            # 保留原审计内容，另记录交付视图；不改冻结附件及其原 hash。
            self.events[-1]["event_hash"] = legacy_envelope_hash(self.events[-1], hash_field="event_hash")
            result = translate_references(result, self._last_reference_map, to_model=True)
            if self._last_invocation.get("calculation_selection_version") is not None:
                from product.runtime.calculation_handoff import build_common_stock_calculation_catalog, common_stock_calculation_view
                from product.runtime.multidimensional_references import load_reference_packet
                packet = load_reference_packet(self._last_root, arguments["invocation_id"])
                result = common_stock_calculation_view(result, build_common_stock_calculation_catalog(self._last_root, packet))
            result["canonical_result_hash"] = result["result_hash"]
            result["result_hash"] = content_hash(result["artifacts"])
            result["reference_map_hash"] = self._last_reference_map["map_hash"]
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
                "artifact_ref": output["artifact_ref"],
                "artifact_sha256": hashlib.sha256((root / output["artifact_ref"]).read_bytes()).hexdigest(),
                "access_mode": "read", "cache_hit": True,
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
                "artifact_ref": output["artifact_ref"],
                "artifact_sha256": hashlib.sha256((root / output["artifact_ref"]).read_bytes()).hexdigest(),
                "access_mode": "read", "cache_hit": True,
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
                "artifact_ref": output["artifact_ref"],
                "artifact_sha256": hashlib.sha256((root / output["artifact_ref"]).read_bytes()).hexdigest(),
                "access_mode": "read",
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
            "artifact_ref": output["artifact_ref"],
            "artifact_sha256": hashlib.sha256((root / output["artifact_ref"]).read_bytes()).hexdigest(),
            "attempt_ref": output["attempt_ref"],
            "attempt_sha256": hashlib.sha256((root / output["attempt_ref"]).read_bytes()).hexdigest(),
            "access_mode": "read",
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
        mapping = self._last_reference_map
        if mapping is not None:
            from product.runtime.multidimensional_references import translate_references
            arguments = translate_references(arguments, mapping)
        result = tools.query(**arguments)
        self.events.append(tools.events[-1])
        if mapping is not None:
            result = translate_references(result, mapping, to_model=True)
            result["canonical_result_hash"] = result["result_hash"]
            result["result_hash"] = content_hash(result["evidence"])
            result["reference_map_hash"] = mapping["map_hash"]
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
        mapping = self._last_reference_map
        if "calculation_id" not in arguments:
            from product.runtime.multidimensional_references import VERSION
            if mapping is None or mapping["binding"]["version"] != VERSION:
                raise ToolAccessError("CALCULATION_ID_REQUIRED_FOR_LEGACY_PROTOCOL")
            if "fixture_math.calculate" not in tools.allowed_tools:
                raise ToolAccessError("TOOL_NOT_AUTHORIZED:fixture_math.calculate")
            arguments["calculation_id"] = "calc-" + secrets.token_hex(16)
        if mapping is not None:
            from product.runtime.multidimensional_references import translate_references
            arguments = translate_references(arguments, mapping)
        result = tools.calculate(**arguments)
        if self._last_invocation is not None and self._last_root is not None:
            ledger_ref = self._last_invocation.get("calculation_ledger_ref")
            if ledger_ref is not None:
                expected = (
                    "research/calculations/"
                    + hashlib.sha256(str(arguments["invocation_id"]).encode("utf-8")).hexdigest()[:16]
                    + "/tool-results.jsonl"
                )
                ledger = (self._last_root / str(ledger_ref)).resolve()
                if (
                    ledger_ref != expected or not ledger.is_relative_to(self._last_root)
                    or not ledger.is_file()
                ):
                    raise ToolAccessError("CALCULATION_LEDGER_BINDING_INVALID")
                receipt = {
                    "run_id": arguments["run_id"],
                    "invocation_id": arguments["invocation_id"],
                    "agent": arguments["agent"],
                    "calculation_id": result["calculation_id"],
                    "operation": result["operation"],
                    "evidence_ids": result["evidence_ids"],
                    "output": result,
                    "tool_event_hash": tools.events[-1]["event_hash"],
                }
                receipt["receipt_hash"] = legacy_envelope_hash(
                    receipt, hash_field="receipt_hash"
                )
                descriptor = os.open(ledger, os.O_RDWR | os.O_NOFOLLOW)
                with os.fdopen(descriptor, "r+b") as stream:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
                    existing = stream.read().decode("utf-8")
                    duplicate = False
                    for line in existing.splitlines():
                        try:
                            prior = json.loads(line)
                        except json.JSONDecodeError as exc:
                            raise ToolAccessError("CALCULATION_LEDGER_CORRUPT") from exc
                        if prior.get("calculation_id") == receipt["calculation_id"]:
                            if prior != receipt:
                                raise ToolAccessError("CALCULATION_ID_COLLISION")
                            duplicate = True
                    if not duplicate:
                        stream.seek(0, os.SEEK_END)
                        stream.write((canonical_json(receipt) + "\n").encode("utf-8"))
                        stream.flush()
                        os.fsync(stream.fileno())
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                result = {**result, "artifact_ref": ledger_ref, "receipt_hash": receipt["receipt_hash"]}
                if mapping is not None and self._last_invocation.get("calculation_selection_version"):
                    from product.runtime.calculation_handoff import calculation_reference
                    result["calculation_ref"] = calculation_reference(mapping, receipt["receipt_hash"])
                    if self._last_root is not None and _load_object(self._last_root / "run_manifest.json").get("stage") == "COMMON_STOCK_RESEARCH":
                        # 正式收据留在本地；模型只获得业务结果及精确选择引用。
                        for key in ("calculation_id", "artifact_ref", "receipt_hash"):
                            result.pop(key, None)
        self.events.append(tools.events[-1])
        if mapping is not None:
            result = translate_references(result, mapping, to_model=True)
            result["reference_map_hash"] = mapping["map_hash"]
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
        wire_arguments: Mapping[str, Any] = {}
        task_transport_requested = False
        task_transport_bound = False
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
                if not isinstance(params, Mapping):
                    raise ToolAccessError("TOOL_PARAMS_INVALID")
                name = params.get("name")
                arguments = params.get("arguments", {})
                called_tool = str(name)
                called_arguments = arguments if isinstance(arguments, Mapping) else {}
                wire_arguments = called_arguments
                declared = [
                    item for item in tools.available_tools() if item.get("name") == name
                ]
                if len(declared) != 1:
                    raise ToolAccessError(f"UNKNOWN_TOOL:{name}")
                schema_validated = False
                if "task_name" in declared[0]["inputSchema"].get("required", []):
                    task_transport_requested = True
                    validate_schema_instance(arguments, declared[0]["inputSchema"])
                    arguments = tools.bind_task_tool_arguments(name, arguments)
                    called_arguments = arguments
                    task_transport_bound = True
                    schema_validated = True
                if (
                    name == "calculate"
                    and isinstance(tools, StatelessFixtureTools)
                    and isinstance(arguments, Mapping)
                    and all(
                        isinstance(arguments.get(key), str)
                        for key in ("run_id", "agent", "invocation_id")
                    )
                ):
                    bound = tools._bound_tools(
                        run_dir=arguments.get("run_dir"),
                        run_id=arguments["run_id"],
                        agent=arguments["agent"],
                        invocation_id=arguments["invocation_id"],
                    )
                    if "fixture_math.calculate" not in bound.allowed_tools:
                        raise ToolAccessError("TOOL_NOT_AUTHORIZED:fixture_math.calculate")
                if not schema_validated:
                    validate_schema_instance(arguments, declared[0]["inputSchema"])
                if name == "query":
                    value = tools.query(**arguments)
                elif name == "evidence_catalog" and isinstance(tools, StatelessFixtureTools):
                    value = tools.evidence_catalog(**arguments)
                elif name == "calculate":
                    value = tools.calculate(**arguments)
                elif name == "read_reports" and isinstance(tools, StatelessFixtureTools):
                    value = tools.read_reports(**arguments)
                elif name == "research_task_state" and isinstance(tools, StatelessFixtureTools):
                    value = tools.research_task_state(**arguments)
                elif name == "research_search":
                    value = tools.research_search(**arguments)
                elif name == "research_fetch":
                    value = tools.research_fetch(**arguments)
                elif name == "equity_research_attachments.query":
                    value = tools.equity_research_attachments_query(**arguments)
                elif name == "research_report_submit" and isinstance(tools, StatelessFixtureTools):
                    value = tools.research_report_submit(**arguments)
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
                if "reference_map_hash" in value:
                    transport_event = {
                        "event_type": "mcp_reference_transport",
                        "run_id": value["run_id"],
                        "invocation_id": called_arguments["invocation_id"],
                        "tool": name, "canonical_event_hash": tools.events[-1]["event_hash"],
                        "reference_map_hash": value["reference_map_hash"],
                        "output_hash": content_hash(value),
                        "output_bytes": len(canonical_json(value).encode("utf-8")),
                    }
                    transport_event["event_hash"] = content_hash(transport_event)
                    if task_transport_requested:
                        transport_event.update(task_name=wire_arguments.get("task_name"),
                                               wire_input_hash=content_hash(wire_arguments))
                        transport_event["event_hash"] = legacy_envelope_hash(transport_event, hash_field="event_hash")
                    _write_event(event_log or tools.dynamic_event_log, transport_event)
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
                if (
                    event_log is None
                    and isinstance(tools, StatelessFixtureTools)
                    and tools.dynamic_event_log is None
                    and all(
                        isinstance(called_arguments.get(key), str)
                        for key in ("run_id", "agent", "invocation_id")
                    )
                ):
                    try:
                        tools._bound_tools(
                            run_dir=called_arguments.get("run_dir"),
                            run_id=called_arguments["run_id"],
                            agent=called_arguments["agent"],
                            invocation_id=called_arguments["invocation_id"],
                        )
                    except (OSError, ValueError, TypeError):
                        pass
                error_event = {
                        "event_type": "mcp_tool_error",
                        "adapter_version": getattr(tools, "adapter_version", MCP_ADAPTER_VERSION),
                        "tool": called_tool,
                        "run_id": called_arguments.get("run_id"),
                        "invocation_id": called_arguments.get("invocation_id"),
                        "input_hash": content_hash(called_arguments),
                        "error": error_message,
                        "access_mode": "read",
                    }
                if task_transport_requested:
                    # The server root is known; an unbound task is NOT attributed to an Invocation.
                    manifest = _load_object(tools.default_run_dir / "run_manifest.json")
                    error_event.update(run_id=manifest["run_id"],
                        task_name=wire_arguments.get("task_name"),
                        routing_state="BOUND" if task_transport_bound else "UNBOUND",
                        invocation_id=called_arguments.get("invocation_id") if task_transport_bound else None,
                        wire_input_hash=content_hash(wire_arguments))
                    error_event["event_hash"] = legacy_envelope_hash(error_event, hash_field="event_hash")
                _write_event(event_log or tools.dynamic_event_log, error_event)
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
