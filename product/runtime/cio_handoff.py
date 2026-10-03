"""CIO 语义草稿和报告读取绑定；不改写研究或投资判断。"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .hashing import canonical_hash, canonical_json, file_hash, legacy_envelope_hash
from .schema_validation import validate_schema_definition, validate_schema_instance
from .multidimensional_references import (
    VERSION as REFERENCE_VERSION, build_reference_map, reference_output_schema, translate_references,
)

NATIVE_CIO_VERSION = "native-cio-draft/1.0.0"
REPORT_READ_TOOL = "research_reports.read"
REPORT_DELIVERY_VERSION = "cio-report-delivery/1.0.0"
COUNCIL_METADATA = frozenset({
    "schema_version", "run_id", "invocation_id", "agent", "consumed_reports",
    "skill_execution", "advisory_only",
})
PREDECISION_METADATA = frozenset({
    "schema_version", "run_id", "invocation_id", "source_run_id", "source_package_hash",
    "target_security_id", "requested_level", "actual_level", "decision_cutoff",
    "generated_at", "consumed_reports", "advisory_only", "complete_portfolio_decision",
    "risk_status",
})


def build_cio_reference_map(root: Path, invocation: Mapping[str, Any],
                            catalog: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    """沿原 CIO 的冻结输入/允许目录建图；原调用方仍负责完整执行准入。"""
    version = invocation.get("reference_transport_version")
    if version is None:
        return None
    if version != REFERENCE_VERSION:
        raise ValueError("CIO_REFERENCE_PROTOCOL_INVALID")
    gate = json.loads((root / "evidence/gate.json").read_text())
    ids = invocation.get("allowed_evidence_ids", invocation.get("evidence_ids"))
    if (gate.get("run_id") != invocation["run_id"]
            or gate.get("bundle_hash") != legacy_envelope_hash(gate, hash_field="bundle_hash")
            or not isinstance(ids, list) or len(ids) != len(set(ids))
            or not set(ids) <= set(gate["allowed_evidence_ids"])):
        raise ValueError("CIO_REFERENCE_GATE_BINDING_INVALID")
    base = {"identity": {"run_id": invocation["run_id"], "invocation_id": invocation["invocation_id"],
                         "agent": "runtime_cio"},
            "reference_transport_version": version, "allowed_evidence_ids": ids,
            "report_catalog": list(catalog)}
    return build_reference_map(base, gate["bundle_hash"], str(root.resolve()))


def cio_model_schema(schema: Mapping[str, Any], mapping: Mapping[str, Any] | None) -> dict[str, Any]:
    return reference_output_schema(schema, mapping) if mapping is not None else copy.deepcopy(dict(schema))


def cio_model_view(value: Any, mapping: Mapping[str, Any] | None) -> Any:
    return translate_references(value, mapping, to_model=True) if mapping is not None else copy.deepcopy(value)


def _report_calculations(value: Mapping[str, Any]):
    for entry in value["reports"]:
        for calculation in entry["report"].get("calculations", []):
            if "input_evidence_refs" in calculation:
                yield calculation


def expand_cio_report_view(value: Mapping[str, Any], *, binding: Mapping[str, Any]) -> dict[str, Any]:
    """只展开同响应的计算输入共享列表；验证绑定，不改写任何研究字段。"""
    output = copy.deepcopy(dict(value))
    if "report_delivery" not in output:
        return output
    delivery = output.pop("report_delivery")
    if (set(output) != {"reports"} or not isinstance(delivery, dict)
            or set(delivery) != {"version", "binding", "expanded_output_hash", "input_evidence_ref_sets"}
            or delivery["version"] != REPORT_DELIVERY_VERSION or delivery["binding"] != dict(binding)):
        raise ValueError("CIO_REPORT_DELIVERY_BINDING_INVALID")
    definitions = delivery["input_evidence_ref_sets"]
    if not isinstance(definitions, dict) or not definitions:
        raise ValueError("CIO_REPORT_DELIVERY_DEFINITIONS_INVALID")
    for key, refs in definitions.items():
        if (not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs)
                or key != "refs." + canonical_hash(refs)):
            raise ValueError("CIO_REPORT_DELIVERY_DEFINITION_DRIFT")
    uses = {key: 0 for key in definitions}
    for calculation in _report_calculations(output):
        refs = calculation["input_evidence_refs"]
        if isinstance(refs, list):
            continue
        if (not isinstance(refs, dict) or set(refs) != {"input_evidence_ref_set"}
                or not isinstance(refs["input_evidence_ref_set"], str)
                or refs["input_evidence_ref_set"] not in definitions):
            raise ValueError("CIO_REPORT_DELIVERY_REFERENCE_INVALID")
        key = refs["input_evidence_ref_set"]
        calculation["input_evidence_refs"] = copy.deepcopy(definitions[key])
        uses[key] += 1
    if any(count < 2 for count in uses.values()):
        raise ValueError("CIO_REPORT_DELIVERY_UNUSED_DEFINITION")
    if canonical_hash(output) != delivery["expanded_output_hash"]:
        raise ValueError("CIO_REPORT_DELIVERY_OUTPUT_DRIFT")
    return output


def compact_cio_report_view(value: Mapping[str, Any], invocation: Mapping[str, Any],
                            mapping: Mapping[str, Any] | None) -> dict[str, Any]:
    """新准备显式启用；仅去重完全相同的重复计算血缘，旧交付不变。"""
    version = invocation.get("report_delivery_version")
    if version is None:
        return copy.deepcopy(dict(value))
    if version != REPORT_DELIVERY_VERSION or mapping is None or set(value) != {"reports"}:
        raise ValueError("CIO_REPORT_DELIVERY_PROTOCOL_INVALID")
    binding = {"run_id": invocation["run_id"], "invocation_id": invocation["invocation_id"],
               "reference_map_hash": mapping["map_hash"]}
    groups: dict[str, list[dict[str, Any]]] = {}
    output = copy.deepcopy(dict(value))
    for calculation in _report_calculations(output):
        refs = calculation["input_evidence_refs"]
        if not isinstance(refs, list) or any(not isinstance(ref, str) for ref in refs):
            raise ValueError("CIO_REPORT_DELIVERY_INPUT_INVALID")
        key = "refs." + canonical_hash(refs)
        group = groups.setdefault(key, [])
        if group and group[0]["input_evidence_refs"] != refs:
            raise ValueError("CIO_REPORT_DELIVERY_HASH_COLLISION")
        group.append(calculation)
    definitions = {}
    for key, group in groups.items():
        refs = group[0]["input_evidence_refs"]
        marker = {"input_evidence_ref_set": key}
        if (len(group) < 2 or len(canonical_json(refs).encode("utf-8"))
                <= len(canonical_json(marker).encode("utf-8"))):
            continue
        definitions[key] = copy.deepcopy(refs)
        for calculation in group:
            calculation["input_evidence_refs"] = dict(marker)
    if not definitions:
        return output
    output["report_delivery"] = {"version": version, "binding": binding,
        "expanded_output_hash": canonical_hash(value), "input_evidence_ref_sets": definitions}
    if expand_cio_report_view(output, binding=binding) != value:
        raise ValueError("CIO_REPORT_DELIVERY_NOT_EQUIVALENT")
    if len(canonical_json(output).encode("utf-8")) >= len(canonical_json(value).encode("utf-8")):
        return copy.deepcopy(dict(value))
    return output


def cio_report_model_result(output: Mapping[str, Any], event: Mapping[str, Any],
                            invocation: Mapping[str, Any], mapping: Mapping[str, Any] | None) -> dict[str, Any]:
    projected = cio_model_view(output, mapping)
    if mapping is not None:
        projected = compact_cio_report_view(projected, invocation, mapping)
        projected.update(run_id=invocation["run_id"], reference_map_hash=mapping["map_hash"],
                         canonical_result_hash=event["output_hash"], result_hash=canonical_hash(projected))
    return projected


def build_fixture_cio_reference_map(root: Path, agent_input: Mapping[str, Any]) -> dict[str, Any] | None:
    from .invocation import invocation_identifier
    invocation = {"run_id": agent_input["run_id"], "evidence_ids": agent_input["allowed_evidence_ids"],
                  "invocation_id": invocation_identifier(agent_input["run_id"], "runtime_cio", canonical_hash(agent_input))}
    if "reference_transport_version" in agent_input:
        invocation["reference_transport_version"] = agent_input["reference_transport_version"]
    return build_cio_reference_map(root, invocation, agent_input["report_catalog"])


def fixture_cio_model_input(root: Path, agent_input: Mapping[str, Any]) -> dict[str, Any]:
    """只投影当前 CIO 研究材料；原输入和报告完整身份仍保留在运行包。"""
    mapping = build_fixture_cio_reference_map(root, agent_input)
    if mapping is None:
        return copy.deepcopy(dict(agent_input))
    projected = cio_model_view({key: agent_input[key] for key in (
        "run_id", "decision_cutoff", "research_question", "mechanical_conflicts", "portfolio_metrics",
        "allowed_evidence_ids",
    )}, mapping)
    projected["report_catalog"] = cio_model_view([{
        "report_id": item["report_id"], "role": item["identity"]["agent"],
    } for item in agent_input["report_catalog"]], mapping)
    projected["invocation_id"] = mapping["binding"]["identity"]["invocation_id"]
    projected["citation_contract"] = {
        "version": REFERENCE_VERSION, "evidence": "e.* 仅选择当前允许的 Evidence。",
        "reports": "p.* 仅选择当前获准且实际读取的报告。",
        "policy": "不得拼接、裁剪、猜测或跨运行引用；正式原始 ID 和 hash 由运行层装配。",
    }
    return projected


def native_cio_schema(formal: Mapping[str, Any], *, report_ids: Sequence[str],
                      metadata: frozenset[str]) -> dict[str, Any]:
    """从既有业务 Schema 派生草稿，保留 action 等所有语义约束。"""
    schema = copy.deepcopy(dict(formal))
    schema.pop("$id", None)
    for name in metadata:
        schema["properties"].pop(name, None)
    schema["required"] = [name for name in schema["required"] if name not in metadata]
    schema["properties"]["schema_version"] = {"const": NATIVE_CIO_VERSION}
    items = {"type": "string", "enum": list(report_ids)} if report_ids else {"type": "string"}
    schema["properties"]["report_selections"] = {
        "type": "array", "uniqueItems": True, "items": items,
        "maxItems": len(report_ids),
    }
    schema["required"].extend(["schema_version", "report_selections"])
    schema["additionalProperties"] = False
    validate_schema_definition(schema)
    return schema


def read_cio_reports(root: Path, invocation: Mapping[str, Any],
                     catalog: Sequence[Mapping[str, Any]], report_ids: Sequence[str],
                     *, prefix: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    """仅向 CIO 交付获准完整报告，事件由工具生产。"""
    if (invocation.get("agent", {}).get("name") != "runtime_cio"
            or REPORT_READ_TOOL not in invocation.get("tool_permissions", [])):
        raise ValueError("CIO_REPORT_READ_NOT_AUTHORIZED")
    if (not isinstance(report_ids, list) or not report_ids
            or any(not isinstance(item, str) for item in report_ids)
            or len(report_ids) != len(set(report_ids))):
        raise ValueError("CIO_REPORT_SELECTION_INVALID")
    by_id = {item["report_id"]: item for item in catalog}
    if len(by_id) != len(catalog) or not set(report_ids) <= by_id.keys():
        raise ValueError("CIO_REPORT_OUTSIDE_CATALOG")
    reports = []
    for report_id in report_ids:
        entry = by_id[report_id]
        ref = entry["artifact_ref"]
        path = (root / prefix / ref).resolve()
        if (Path(ref).is_absolute() or not path.is_relative_to((root / prefix).resolve())
                or not path.is_file() or file_hash(path) != entry["file_hash"]):
            raise ValueError("CIO_REPORT_DRIFT:" + report_id)
        report = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(report, dict):
            raise ValueError("CIO_REPORT_NOT_OBJECT")
        reports.append({"report_id": report_id, "report": report})
    output = {"reports": reports}
    event = {
        "event_type": "mcp_tool_result", "tool": REPORT_READ_TOOL, "access_mode": "read",
        "run_id": invocation["run_id"], "invocation_id": invocation["invocation_id"],
        "agent": "runtime_cio", "report_ids": list(report_ids),
        "catalog_hash": canonical_hash(list(catalog)), "output_hash": canonical_hash(output),
    }
    event["event_hash"] = legacy_envelope_hash(event, hash_field="event_hash")
    return output, event


def verify_cio_report_reads(root: Path, invocation: Mapping[str, Any],
                            catalog: Sequence[Mapping[str, Any]], selections: Sequence[str],
                            *, prefix: str = "") -> dict[str, Any]:
    """授予、工具实际交付、模型选择分别验证；不宣称测得模型内在理解。"""
    if (not isinstance(selections, list) or any(not isinstance(s, str) for s in selections)
            or len(selections) != len(set(selections))):
        raise ValueError("CIO_REPORT_SELECTION_INVALID")
    allowed = {item["report_id"] for item in catalog}
    if not set(selections) <= allowed:
        raise ValueError("CIO_REPORT_OUTSIDE_CATALOG")
    read_ids: set[str] = set()
    event_hashes = []
    expected_deliveries = []
    events = []
    path = root / "events/mcp/events.jsonl"
    if path.exists():
        events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for event in events:
            if not isinstance(event, dict):
                raise ValueError("CIO_REPORT_READ_EVENT_INVALID")
            if event.get("tool") != REPORT_READ_TOOL:
                continue
            if (event.get("run_id") != invocation["run_id"]
                    or event.get("invocation_id") != invocation["invocation_id"]
                    or event.get("agent") != "runtime_cio"):
                raise ValueError("CIO_REPORT_READ_IDENTITY_INVALID")
            output, expected = read_cio_reports(root, invocation, catalog,
                                                event.get("report_ids"), prefix=prefix)
            if event != expected:
                raise ValueError("CIO_REPORT_READ_EVENT_INVALID")
            if invocation.get("report_delivery_version") is not None:
                mapping = build_cio_reference_map(root, invocation, catalog)
                delivered = cio_report_model_result(output, event, invocation, mapping)
                transport = {"event_type": "mcp_reference_transport", "run_id": invocation["run_id"],
                    "invocation_id": invocation["invocation_id"], "tool": "read_reports",
                    "canonical_event_hash": event["event_hash"], "reference_map_hash": mapping["map_hash"],
                    "output_hash": canonical_hash(delivered),
                    "output_bytes": len(canonical_json(delivered).encode("utf-8"))}
                transport["event_hash"] = legacy_envelope_hash(transport, hash_field="event_hash")
                expected_deliveries.append(transport)
            read_ids.update(event["report_ids"])
            event_hashes.append(event["event_hash"])
    if invocation.get("report_delivery_version") is not None:
        actual_deliveries = [event for event in events
                            if event.get("event_type") == "mcp_reference_transport" and event.get("tool") == "read_reports"]
        if sorted(map(canonical_json, actual_deliveries)) != sorted(map(canonical_json, expected_deliveries)):
            raise ValueError("CIO_REPORT_DELIVERY_EVENT_INVALID")
    if not set(selections) <= read_ids:
        raise ValueError("CIO_SELECTED_REPORT_NOT_READ")
    if read_ids != allowed:
        raise ValueError("CIO_REQUIRED_REPORT_NOT_READ")
    return {"allowed_report_ids": sorted(allowed), "read_report_ids": sorted(read_ids),
            "selected_report_ids": list(selections), "read_event_hashes": event_hashes}


def assemble_cio_draft(draft: Mapping[str, Any], formal_schema: Mapping[str, Any],
                       metadata: Mapping[str, Any], *, root: Path,
                       invocation: Mapping[str, Any], catalog: Sequence[Mapping[str, Any]],
                       prefix: str = "") -> tuple[dict[str, Any], dict[str, Any]]:
    schema = native_cio_schema(formal_schema, report_ids=[item["report_id"] for item in catalog],
                               metadata=frozenset(metadata))
    mapping = build_cio_reference_map(root, invocation, catalog)
    validate_schema_instance(draft, cio_model_schema(schema, mapping))
    canonical = translate_references(dict(draft), mapping) if mapping is not None else draft
    proof = verify_cio_report_reads(root, invocation, catalog, canonical["report_selections"], prefix=prefix)
    if mapping is not None:
        proof["reference_map_hash"] = mapping["map_hash"]
        proof["semantic_output_hash"] = canonical_hash(draft)
    output = {key: copy.deepcopy(value) for key, value in canonical.items()
              if key not in {"schema_version", "report_selections"}}
    output.update(copy.deepcopy(dict(metadata)))
    validate_schema_instance(output, formal_schema)
    return output, proof
