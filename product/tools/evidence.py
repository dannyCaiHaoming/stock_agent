"""Gate 限定的查询与金融计算；不包含宿主启动、Hook 或生命周期。"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, DivisionByZero, InvalidOperation
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from product.mcp.provenance import canonical_json, content_hash
    from product.runtime.hashing import legacy_envelope_hash
    from product.runtime.monetary import convert_monetary_value, scale_factor
except ModuleNotFoundError as exc:
    if exc.name != "product":
        raise
    from mcp.provenance import canonical_json, content_hash
    from runtime.hashing import legacy_envelope_hash
    from runtime.monetary import convert_monetary_value, scale_factor

MCP_ADAPTER_VERSION = "fixture-gate-scoped/2.5.0"
COMMON_STOCK_FIELD_QUERY_MAX_BYTES = 65536
SUPPORTED_TOOLS = {
    "fixture_evidence.query", "fixture_math.calculate",
    "public_research.search", "public_research.fetch",
    "equity_research_attachments.query", "research_report.submit",
    "research_reports.read",
}
MONETARY_MENTION = re.compile(
    r"(?P<currency>\$|USD\s*)(?P<value>[+-]?\d+(?:\.\d+)?)\s*"
    r"(?P<scale>billion|million|thousand|亿|万)\b", re.IGNORECASE,
)

class ToolAccessError(ValueError):
    pass


def _sec_numeric_input(fact: Mapping[str, Any]) -> dict[str, Any]:
    value = fact.get("value")
    if (fact.get("schema_version") != "research-supplement-fact/1.1.0"
            or fact.get("dataset") != "financial_history" or fact.get("source_family") != "sec"
            or not str(fact.get("semantic_field", "")).startswith("sec_financial_fact:")
            or not isinstance(value, dict)):
        raise ToolAccessError("SEC_NUMERIC_EVIDENCE_INVALID")
    source_fields = ("evidence_id", "security_id", "source_id", "as_of", "retrieved_at")
    value_fields = ("accession", "taxonomy", "tag", "unit", "parent_evidence_id")
    if (not all(isinstance(fact.get(key), str) and fact[key] for key in source_fields)
            or not all(isinstance(value.get(key), str) and value[key] for key in value_fields)
            or not fact["source_id"].startswith("sec-companyfacts-")
            or not fact["source_id"].endswith(":" + value["parent_evidence_id"])):
        raise ToolAccessError("SEC_NUMERIC_EVIDENCE_INVALID")
    try:
        end = date.fromisoformat(value["period_end"])
        if end > date.fromisoformat(fact["as_of"][:10]):
            raise ValueError("period ends after evidence as_of")
        if value.get("context_type") == "instant":
            valid_period = value.get("period_start") is None
        elif value.get("context_type") == "duration":
            valid_period = date.fromisoformat(value["period_start"]) <= end
        else:
            valid_period = False
        amount = value["amount"]
        if (not valid_period or type(amount) not in (str, int)
                or not re.fullmatch(r"[+-]?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?", str(amount))
                or not Decimal(str(amount)).is_finite()):
            raise ValueError("invalid amount or period")
    except (InvalidOperation, KeyError, TypeError, ValueError) as exc:
        raise ToolAccessError("SEC_NUMERIC_EVIDENCE_INVALID") from exc
    return {
        **{key: fact[key] for key in source_fields},
        **{key: value[key] for key in (*value_fields, "context_type", "period_end")},
        "period_start": value.get("period_start"), "amount": str(amount),
        "value_path": "value.amount", "source_fact_hash": content_hash(fact),
    }


class EvidenceTools:
    """查询和计算范围来自可信任务绑定，不把输入身份字符串当调用方认证。"""

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
        structured_sec_amounts: bool = False,
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
        self._structured_sec_amounts = structured_sec_amounts
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
            numeric_inputs = []
            if self._structured_sec_amounts and isinstance(value, dict):
                numeric = _sec_numeric_input(fact)
                if numeric["unit"] != "USD":
                    raise ToolAccessError("SEC_MONETARY_UNIT_INVALID")
                numeric_inputs.append(numeric)
                conversion = {
                    "source_text": canonical_json(value), "source_value": numeric["amount"],
                    "source_scale": "one", "target_scale": target_scale,
                    "converted_value": convert_monetary_value(
                        value=numeric["amount"], source_scale="one", target_scale=target_scale,
                    ),
                    "currency": "USD", "tax_basis": "UNSPECIFIED",
                }
                conversion["conversion_hash"] = content_hash({"input": numeric, **conversion})
                mentions.append(conversion)
            elif isinstance(value, str):
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
            if numeric_inputs:
                output["numeric_inputs"] = numeric_inputs
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
        numeric_inputs = []
        if self._structured_sec_amounts and any(isinstance(fact.get("value"), dict) for fact in facts):
            if operation != "ratio":
                raise ToolAccessError("SEC_NUMERIC_OPERATION_UNSUPPORTED")
            numeric_inputs = [_sec_numeric_input(fact) for fact in facts]
            frame = ("security_id", "accession", "taxonomy", "unit", "context_type", "period_start", "period_end")
            if any(numeric_inputs[0][key] != numeric_inputs[1][key] for key in frame):
                raise ToolAccessError("SEC_NUMERIC_FRAME_MISMATCH")
        try:
            first, second = (Decimal(item["amount"]) for item in numeric_inputs) if numeric_inputs else (
                Decimal(str(fact["value"])) for fact in facts
            )
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
        if numeric_inputs:
            output["numeric_inputs"] = numeric_inputs
        self._record("fixture_math.calculate", inputs, output)
        return output
