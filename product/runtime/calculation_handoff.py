"""机械计算选择装配；不选择论据、不解释结果、不执行投资判断。"""
from __future__ import annotations

import copy
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping

from product.runtime.hashing import canonical_hash, legacy_envelope_hash, verify_legacy_envelope_hash, verify_legacy_object_hash, HashContractError
from product.runtime.multidimensional_references import VERSION as REFERENCE_VERSION, validate_reference_map
from product.runtime.schema_validation import validate_schema_instance

VERSION = "research-calculation-selections/1.0.0"
PREPARED_REFERENCE_VERSION = "prepared-result-reference/1.0.0"
SELECTION_SCHEMA = {
    "type": "array", "uniqueItems": True,
    "items": {"type": "object", "additionalProperties": False,
              "required": ["calculation_ref", "claim_ids"],
              "properties": {
                  "calculation_ref": {"type": "string", "pattern": r"^k\.[0-9a-f]{12}\.[0-9a-f]{24}$"},
                  "claim_ids": {"type": "array", "minItems": 1, "uniqueItems": True,
                                "items": {"type": "string", "minLength": 1}},
              }},
}


def prepared_reference_enabled(packet: Mapping[str, Any]) -> bool:
    task = packet.get("task", {})
    version = task.get("prepared_result_reference_version")
    if version is None:
        return False
    if (version != PREPARED_REFERENCE_VERSION
            or task.get("tool_identity_version") != "research-tool-identity/1.0.0"
            or task.get("capability") not in {"TECHNICAL_STRUCTURE", "MARKET_STATE"}):
        raise ValueError("MULTIDIMENSIONAL_PREPARED_REFERENCE_PROFILE_INVALID")
    return True


def _selection_schema(packet: Mapping[str, Any]) -> dict[str, Any]:
    schema = copy.deepcopy(SELECTION_SCHEMA)
    if prepared_reference_enabled(packet):
        # Syntax only; the original verified task catalog still decides membership.
        schema["items"]["properties"]["calculation_ref"]["pattern"] = (
            r"^(?:k\.[0-9a-f]{12}\.[0-9a-f]{24}|p\.[a-z][a-z0-9_]*(?:\.[1-9][0-9]*_sessions)?)$"
        )
    return schema


def _path(root: Path, ref: str) -> Path:
    root = root.resolve()
    path = root / ref
    if (not isinstance(ref, str) or Path(ref).is_absolute()
            or not path.resolve().is_relative_to(root)
            or any(parent.is_symlink() for parent in (path, *path.parents) if parent != root)
            or not path.is_file()):
        raise ValueError("MULTIDIMENSIONAL_CALCULATION_PATH_INVALID")
    return path


def load_tool_receipts(root: Path, task: Mapping[str, Any], invocation: Mapping[str, Any], *,
                       selected_ids: set[str] | None = None) -> dict[str, dict]:
    """成功收据必须与实际事件精确闭合；失败事件不成为候选。"""
    ref = task.get("calculation_ledger_ref")
    if ref is None:
        return {}
    expected = "research/calculations/" + hashlib.sha256(task["invocation_id"].encode()).hexdigest()[:16] + "/tool-results.jsonl"
    if ref != expected or invocation.get("calculation_ledger_ref") != ref:
        raise ValueError("MULTIDIMENSIONAL_CALCULATION_LEDGER_BINDING_INVALID")
    try:
        ledger = _path(root, ref)
        receipts = {}
        for line_number, line in enumerate(ledger.read_text(encoding="utf-8").splitlines(), 1):
            receipt = json.loads(line)
            if not isinstance(receipt, dict):
                raise ValueError("MULTIDIMENSIONAL_CALCULATION_LEDGER_INVALID")
            try:
                verify_legacy_envelope_hash(receipt, hash_field="receipt_hash", location=f"{ref}:{line_number}")
            except HashContractError as exc:
                raise ValueError(f"MULTIDIMENSIONAL_CALCULATION_LEDGER_INVALID:{exc}") from exc
            if (any(receipt.get(key) != task[key] for key in ("run_id", "invocation_id", "agent"))
                    or not isinstance(receipt.get("calculation_id"), str)
                    or not isinstance(receipt.get("evidence_ids"), list)):
                raise ValueError("MULTIDIMENSIONAL_CALCULATION_LEDGER_INVALID")
            key = receipt["calculation_id"]
            if key in receipts and receipts[key] != receipt:
                raise ValueError("MULTIDIMENSIONAL_CALCULATION_LEDGER_INVALID")
            receipts[key] = receipt
    except (OSError, json.JSONDecodeError, TypeError, KeyError) as exc:
        raise ValueError("MULTIDIMENSIONAL_CALCULATION_LEDGER_INVALID") from exc
    selected = receipts if selected_ids is None else {key: value for key, value in receipts.items() if key in selected_ids}
    if not selected:
        return {}
    if "fixture_math.calculate" not in invocation.get("tool_permissions", []):
        raise ValueError("MULTIDIMENSIONAL_CALCULATION_NOT_AUTHORIZED")
    try:
        events = {}
        for line in _path(root, "events/mcp/events.jsonl").read_text(encoding="utf-8").splitlines():
            event = json.loads(line)
            if isinstance(event, dict) and event.get("tool") == "fixture_math.calculate":
                key = event.get("event_hash")
                if key in events and events[key] != event:
                    raise ValueError("MULTIDIMENSIONAL_CALCULATION_EVENT_INVALID")
                events[key] = event
        for receipt in selected.values():
            output = receipt.get("output")
            event = events.get(receipt.get("tool_event_hash"))
            if not isinstance(output, dict) or not isinstance(event, dict):
                raise ValueError("MULTIDIMENSIONAL_CALCULATION_EVENT_INVALID")
            inputs = {key: receipt[key] for key in (
                "run_id", "agent", "invocation_id", "calculation_id", "operation", "evidence_ids")}
            if output.get("target_scale") is not None:
                inputs["target_scale"] = output["target_scale"]
            try:
                verify_legacy_envelope_hash(event, hash_field="event_hash", location="events/mcp/events.jsonl:fixture_math.calculate")
                verify_legacy_object_hash(inputs, event.get("input_hash"), kind="canonical-object",
                                          location=f"calculation:{receipt['calculation_id']}:input")
                verify_legacy_object_hash(output, event.get("output_hash"), kind="canonical-object",
                                          location=f"calculation:{receipt['calculation_id']}:output")
            except HashContractError as exc:
                raise ValueError(f"MULTIDIMENSIONAL_CALCULATION_EVENT_INVALID:{exc}") from exc
            if (any(output.get(key) != receipt[key] for key in ("run_id", "calculation_id", "operation", "evidence_ids"))
                    or any(event.get(key) != inputs[key] for key in (
                        "run_id", "agent", "invocation_id", "calculation_id", "operation", "evidence_ids"))
                    or not set(receipt["evidence_ids"]) <= set(task["allowed_evidence_ids"])):
                raise ValueError("MULTIDIMENSIONAL_CALCULATION_EVENT_INVALID")
    except (OSError, json.JSONDecodeError, TypeError, KeyError) as exc:
        raise ValueError("MULTIDIMENSIONAL_CALCULATION_EVENT_INVALID") from exc
    return selected


def receipt_calculation(receipt: Mapping[str, Any], artifact_ref: str) -> dict[str, Any]:
    """报告值按操作投影；复合结果完整保存字段/单位，不选其中一个金额。"""
    output = receipt["output"]
    operation = receipt["operation"]
    if operation in {"ratio", "percent_change"}:
        value, unit = output["value"], "ratio"  # percent_change 未乘100。
    elif operation == "monetary_scale":
        value = json.dumps(output["conversions"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        unit = "USD " + output["target_scale"]
    elif operation == "institutional_period_change":
        value = json.dumps({key: output[key] for key in ("earlier_period", "later_period", "changes")},
                           ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        unit = "mixed: institution_count / holder_quantity / holder_percent"
    else:
        raise ValueError("MULTIDIMENSIONAL_CALCULATION_OPERATION_UNSUPPORTED")
    return {"calculation_id": receipt["calculation_id"], "method": operation,
            "value": value, "unit": unit, "input_evidence_refs": copy.deepcopy(receipt["evidence_ids"]),
            "artifact_ref": artifact_ref}


def calculation_reference(mapping: Mapping[str, Any], version_hash: str) -> str:
    validate_reference_map(mapping)
    if mapping["binding"]["version"] != REFERENCE_VERSION:
        raise ValueError("MULTIDIMENSIONAL_CALCULATION_SELECTION_VERSION_INVALID")
    return f"k.{canonical_hash(mapping['binding'])[:12]}.{version_hash[:24]}"


def build_common_stock_calculation_catalog(root: Path, packet: Mapping[str, Any]) -> dict[str, dict]:
    """普通股沿同一收据校验选择计算；附件仍由原 package Validator 授权。"""
    task = packet.get("calculation_context", {})
    if task.get("calculation_selection_version") != VERSION:
        raise ValueError("COMMON_STOCK_CALCULATION_SELECTION_NOT_ENABLED")
    invocation = json.loads(_path(root, task["invocation_path"]).read_text())
    result, identities = {}, {}

    def add(identifier, entry, digest):
        ref = calculation_reference(packet["reference_map"], digest)
        if (identifier in identities and identities[identifier] != ref
                or ref in result and result[ref] != entry):
            raise ValueError("COMMON_STOCK_CALCULATION_ID_AMBIGUOUS")
        identities[identifier] = ref
        result[ref] = {"calculation_id": identifier, **entry}

    for receipt in load_tool_receipts(root, task, invocation).values():
        add(receipt["calculation_id"], {"kind": "TOOL", "receipt": receipt}, receipt["receipt_hash"])
    package_ref = task.get("equity_research_package_path")
    if package_ref is not None:
        from product.runtime.equity_research_package import validate_equity_research_package, MODEL_QUERY_ARTIFACT_KINDS
        from product.runtime.common_stock_stage import _collect_calculation_identities
        package = json.loads(_path(root, package_ref).read_text())
        gate = json.loads(_path(root, "evidence/gate.json").read_text())
        validate_equity_research_package(package, gate=gate)
        if (package["package_hash"] != task["equity_research_package_hash"]
                or package["security_id"] != packet["identity"]["security_id"]):
            raise ValueError("COMMON_STOCK_CALCULATION_ATTACHMENT_BINDING_INVALID")
        for artifact in package["artifacts"]:
            if artifact["kind"] not in MODEL_QUERY_ARTIFACT_KINDS:
                continue
            for identifier in sorted(_collect_calculation_identities(artifact["artifact"])):
                digest = canonical_hash({"package_hash": package["package_hash"],
                                         "artifact_hash": artifact["artifact_hash"], "calculation_id": identifier})
                add(identifier, {"kind": "ATTACHMENT", "artifact_kind": artifact["kind"]}, digest)
    return result


def common_stock_calculation_view(value: Any, catalog: Mapping[str, Any]) -> Any:
    """仅转换计算身份位置，不改值、元数据、正文或固定原包。"""
    identities = {entry["calculation_id"]: ref for ref, entry in catalog.items()}
    def walk(item):
        if isinstance(item, list):
            return [walk(child) for child in item]
        if not isinstance(item, dict):
            return copy.deepcopy(item)
        result = {}
        for key, child in item.items():
            if key in {"calculation_id", "calculation_ref"} and isinstance(child, str):
                if child not in identities:
                    raise ValueError("COMMON_STOCK_CALCULATION_SELECTION_UNKNOWN:" + child)
                result[key] = identities[child]
            elif key in {"calculation_refs", "calculation_ids"} and isinstance(child, list):
                if any(ref not in identities for ref in child):
                    raise ValueError("COMMON_STOCK_CALCULATION_SELECTION_UNKNOWN")
                result[key] = [identities[ref] for ref in child]
            elif key in {"value", "metadata"}:
                result[key] = copy.deepcopy(child)
            else:
                result[key] = walk(child)
        return result
    return walk(value)


def assemble_common_stock_calculation_selections(root: Path, packet: Mapping[str, Any], draft: Mapping[str, Any]) -> dict[str, Any]:
    """模型的关联主张及解释原样保留，只展开它明确选中的真实计算。"""
    choices = draft.get("calculation_selections")
    validate_schema_instance(choices, SELECTION_SCHEMA, path="$.calculation_selections")
    result = copy.deepcopy(dict(draft))
    result.pop("calculation_selections")
    claims = {claim["claim_id"]: claim for claim in result["claims"]}
    if len(claims) != len(result["claims"]) or any("calculation_refs" in claim for claim in claims.values()):
        raise ValueError("COMMON_STOCK_CALCULATION_SELECTION_CLAIMS_INVALID")
    catalog = build_common_stock_calculation_catalog(root, packet)
    for claim in claims.values():
        claim["calculation_refs"] = []
    seen = set()
    for choice in choices:
        ref = choice["calculation_ref"]
        if ref in seen:
            raise ValueError("COMMON_STOCK_CALCULATION_SELECTION_DUPLICATE")
        seen.add(ref)
        if ref not in catalog:
            raise ValueError("COMMON_STOCK_CALCULATION_SELECTION_UNKNOWN:" + ref)
        for claim_id in choice["claim_ids"]:
            if claim_id not in claims:
                raise ValueError("COMMON_STOCK_CALCULATION_SELECTION_CLAIM_UNKNOWN:" + claim_id)
            claims[claim_id]["calculation_refs"].append(catalog[ref]["calculation_id"])
    return result


def _put(catalog: dict, packet: Mapping[str, Any], entry: dict, digest: str) -> None:
    ref = calculation_reference(packet["reference_map"], digest)
    if entry.get("kind") == "PRECOMPUTED" and prepared_reference_enabled(packet):
        method = entry["calculation"]["method"]
        # An exact encoding of trusted mechanical method labels, not prose parsing.
        if not isinstance(method, str) or not re.fullmatch(
                r"[a-z][a-z0-9_]*(?::[1-9][0-9]*_sessions)?", method):
            raise ValueError("MULTIDIMENSIONAL_PREPARED_REFERENCE_METHOD_INVALID")
        ref = "p." + method.replace(":", ".")
        if ref in catalog:
            raise ValueError("MULTIDIMENSIONAL_CALCULATION_REFERENCE_COLLISION")
    if ref in catalog and catalog[ref] != entry:
        raise ValueError("MULTIDIMENSIONAL_CALCULATION_REFERENCE_COLLISION")
    catalog[ref] = entry


def build_calculation_catalog(root: Path, packet: Mapping[str, Any], *, include_tools: bool = True) -> dict[str, dict]:
    """原任务限定目录；加入新收据不会重编号或改变已有短引用。"""
    if packet["task"].get("calculation_selection_version") != VERSION:
        raise ValueError("MULTIDIMENSIONAL_CALCULATION_SELECTION_NOT_ENABLED")
    task, prepared = packet["task"], packet.get("prepared_analysis", {})
    result: dict[str, dict] = {}
    if include_tools and task.get("calculation_ledger_ref"):
        invocation = json.loads(_path(root, task["invocation_path"]).read_text()) if "invocation_path" in task else None
        if invocation is None:
            index = json.loads(_path(root, "research/dispatch-index.json").read_text())
            matches = [t for t in index["tasks"] if t["invocation_id"] == task["invocation_id"]]
            if len(matches) != 1:
                raise ValueError("MULTIDIMENSIONAL_CALCULATION_TASK_INVALID")
            invocation = json.loads(_path(root, matches[0]["invocation_path"]).read_text())
        for receipt in load_tool_receipts(root, task, invocation).values():
            _put(result, packet, {"kind": "TOOL", "calculation": receipt_calculation(receipt, task["calculation_ledger_ref"]),
                                 "receipt_hash": receipt["receipt_hash"], "tool_event_hash": receipt["tool_event_hash"]},
                 receipt["receipt_hash"])
    for key, ref_key in (("calculation", "calculation_ref"), ("breadth_calculation", "breadth_calculation_ref")):
        if prepared.get(key) is None:
            continue
        ref = prepared.get(ref_key)
        if ref not in task.get("allowed_artifact_refs", []):
            raise ValueError("MULTIDIMENSIONAL_CALCULATION_PRECOMPUTED_NOT_AUTHORIZED")
        artifact = json.loads(_path(root, ref).read_text())
        try:
            verify_legacy_envelope_hash(artifact, hash_field="artifact_hash", location="product/runtime/calculation_handoff.py:artifact.artifact_hash")
        except HashContractError as exc:
            raise ValueError(f"MULTIDIMENSIONAL_CALCULATION_PRECOMPUTED_INVALID:{exc}") from exc
        ids = artifact.get("evidence_fact_ids")
        if not isinstance(ids, list) or not set(ids) <= (
            set(task["allowed_evidence_ids"]) | set(task.get("allowed_calculation_evidence_ids", []))
        ):
            raise ValueError("MULTIDIMENSIONAL_CALCULATION_PRECOMPUTED_INPUT_INVALID")
        projection = copy.deepcopy(artifact)
        if key == "calculation":
            projection.pop("evidence_fact_ids")
            projection.update(evidence_fact_count=len(ids), evidence_fact_ids_hash=canonical_hash(ids))
        if projection != prepared[key]:
            raise ValueError("MULTIDIMENSIONAL_CALCULATION_PRECOMPUTED_BINDING_INVALID")
        if key == "breadth_calculation":
            from product.deterministic.market_analysis import calculate_market_breadth
            gate = json.loads(_path(root, "evidence/gate.json").read_text())
            facts = [fact for fact in gate["allowed_evidence"] if fact["evidence_id"] in ids]
            if len(facts) != 1 or calculate_market_breadth(facts[0]) != artifact:
                raise ValueError("MULTIDIMENSIONAL_CALCULATION_PRECOMPUTED_INPUT_INVALID")
            calculation = copy.deepcopy(prepared["breadth_report_calculation"])
            expected = {"calculation_id": artifact["artifact_id"], "method": "provider_breadth_partition_sum",
                        "value": json.dumps(artifact["counts"], sort_keys=True, separators=(",", ":")),
                        "unit": artifact["unit"], "input_evidence_refs": ids, "artifact_ref": ref}
            if calculation != expected:
                raise ValueError("MULTIDIMENSIONAL_CALCULATION_PRECOMPUTED_BINDING_INVALID")
            _put(result, packet, {"kind": "PRECOMPUTED", "calculation": expected,
                                 "as_of": artifact["as_of"], "artifact_hash": artifact["artifact_hash"]}, artifact["artifact_hash"])
            continue
        from product.deterministic.market_analysis import verify_technical_calculation, verify_market_state_calculation
        validators = {"technical-calculation/1.0.0": verify_technical_calculation,
                      "market-state-calculation/1.0.0": verify_market_state_calculation}
        validator = validators.get(artifact.get("schema_version"))
        if validator is None:
            raise ValueError("MULTIDIMENSIONAL_CALCULATION_PRECOMPUTED_VERSION_INVALID")
        validator(artifact)
        for window in artifact["windows"]:
            if window["status"] != "COMPLETE":
                continue
            for metric, value in window["metrics"].items():
                if value is None:
                    continue
                digest = canonical_hash({"artifact_hash": artifact["artifact_hash"], "window_sessions": window["window_sessions"], "metric": metric})
                unit = "shares" if metric == "average_volume" else "provider_price" if metric in {"window_high", "window_low"} else "ratio"
                calculation = {"calculation_id": "calc-precomputed-" + digest[:24],
                               "method": f"{metric}:{window['window_sessions']}_sessions", "value": value,
                               "unit": unit, "input_evidence_refs": copy.deepcopy(ids), "artifact_ref": ref}
                _put(result, packet, {"kind": "PRECOMPUTED", "calculation": calculation,
                                     "as_of": artifact["as_of"], "window_sessions": window["window_sessions"],
                                     "price_basis": artifact["price_basis"], "artifact_hash": artifact["artifact_hash"]}, digest)
    for dependency in packet.get("dependency_reports", []):
        if not dependency.get("verified_calculations"):
            continue
        # No new calculate permission: re-read only the declared dependency and
        # its already verified successful receipts, preserving the original run.
        index = json.loads(_path(root, "research/dispatch-index.json").read_text())
        source_tasks = [t for t in index["tasks"] if t["task_id"] in task.get("depends_on", [])
                        and dependency["report_id"] == "dimension-report:" + t["task_id"]]
        if len(source_tasks) != 1:
            raise ValueError("MULTIDIMENSIONAL_CALCULATION_DEPENDENCY_NOT_AUTHORIZED")
        source = json.loads(_path(root, dependency["artifact_ref"]).read_text())
        if (source.get("report_id") != dependency["report_id"] or source.get("report_hash") != dependency["report_hash"]
                or source.get("report_hash") != legacy_envelope_hash(source, hash_field="report_hash")
                or source.get("invocation_id") != source_tasks[0]["invocation_id"]):
            raise ValueError("MULTIDIMENSIONAL_CALCULATION_DEPENDENCY_BINDING_INVALID")
        from product.runtime.multidimensional_stage import _dependency_calculation_records
        verified = _dependency_calculation_records(root, report=source, dependency_task=source_tasks[0])
        if verified != dependency["verified_calculations"]:
            raise ValueError("MULTIDIMENSIONAL_CALCULATION_DEPENDENCY_BINDING_INVALID")
        for record in verified:
            claim_refs = [ref for ref, target in packet["reference_map"]["claims"].items()
                          if target["report_id"] == dependency["report_id"]
                          and target["report_hash"] == dependency["report_hash"]
                          and target["claim_id"] == record["claim_id"]]
            if len(claim_refs) != 1:
                raise ValueError("MULTIDIMENSIONAL_CALCULATION_DEPENDENCY_CLAIM_INVALID")
            digest = canonical_hash({"report_id": dependency["report_id"], "report_hash": dependency["report_hash"],
                                     "source_claim_id": record["claim_id"], "receipt_hash": record["receipt_hash"]})
            _put(result, packet, {"kind": "DEPENDENCY", "calculation": {key: copy.deepcopy(record[key]) for key in (
                "calculation_id", "method", "value", "unit", "input_evidence_refs", "artifact_ref")},
                "source_claim_ref": claim_refs[0], "upstream_choice": {
                    "report_id": dependency["report_id"], "source_claim_id": record["claim_id"],
                    "calculation_id": record["calculation_id"]}}, digest)
    return result


def selection_draft_schema(schema: Mapping[str, Any], *, document_refs: list[str] | None = None) -> dict[str, Any]:
    """从现有业务草稿结构派生选择格式；最终报告Schema不改变。"""
    result = copy.deepcopy(dict(schema))
    removed = {"run_id", "invocation_id", "agent", "calculations", "artifact_refs", "upstream_calculation_selections"}
    result["required"] = [key for key in result["required"] if key not in removed] + ["calculation_selections"]
    for key in removed:
        result["properties"].pop(key, None)
    result["properties"]["calculation_selections"] = copy.deepcopy(SELECTION_SCHEMA)
    claim = result["$defs"]["claim"]
    claim["properties"].pop("calculation_refs", None)
    claim["required"] = [key for key in claim["required"] if key != "calculation_refs"]
    result["$defs"].pop("calculation", None)
    if document_refs is not None:
        result["properties"].pop("documents", None)
        result["required"] = [key for key in result["required"] if key != "documents"]
        if "document_selections" not in result["required"]:
            result["required"].append("document_selections")
        result["properties"]["document_selections"] = {
            "type": "array", "uniqueItems": True,
            "items": {"type": "string", "enum": document_refs},
        }
        result["$defs"].pop("document", None)
    return result


def semantic_selection_draft_schema(packet: Mapping[str, Any]) -> dict[str, Any]:
    """同一冻结业务结构派生模型格式与原稿检查；引用闭合仍单独严格验证。"""
    from product.runtime.research_submission import FORMAL_VERSIONS
    schema = copy.deepcopy(packet["output_schema"])
    # 原始 Evidence enum 属于冻结引用闭合，不是原稿结构。短引用先按
    # 字符串结构检查，再由现有精确映射和正式 Schema 验证允许集合。
    schema["$defs"]["evidence_id"] = copy.deepcopy(schema["$defs"]["id"])
    if packet["task"].get("submission_version") in FORMAL_VERSIONS:
        claim = schema["$defs"]["claim"]
        claim["required"] = ["core_statement" if key == "statement" else key
                             for key in claim["required"]] + ["research_relation_clauses"]
        claim["properties"]["core_statement"] = claim["properties"].pop("statement")
        claim["properties"]["research_relation_clauses"] = {
            "type": "array", "items": {"type": "object", "additionalProperties": False,
                "required": ["research_claim_ref", "relation_statement"],
                "properties": {"research_claim_ref": {"$ref": "#/$defs/id"},
                               "relation_statement": {"type": "string", "minLength": 1}}},
        }
    result = selection_draft_schema(
        schema, document_refs=list(packet["reference_map"].get("documents", {})),
    )
    result["properties"]["calculation_selections"] = _selection_schema(packet)
    return result


def validate_semantic_selection_draft(draft: Mapping[str, Any], packet: Mapping[str, Any]) -> None:
    """当前写入必查派生结构；字段缺失不得切回历史完整草稿格式。

    历史装配器按明确版本选择旧结构，不调用当前写入检查猜测格式。
    """
    if packet["task"].get("calculation_selection_version") != VERSION:
        raise ValueError("MULTIDIMENSIONAL_CALCULATION_SELECTION_NOT_ENABLED")
    validate_schema_instance(draft, semantic_selection_draft_schema(packet))


def require_current_selection_transport(
    packet: Mapping[str, Any], invocation: Mapping[str, Any], *, indexed_task: Mapping[str, Any],
) -> None:
    """当前执行准入：任务、调用与交付引用必须绑定同一个选择协议。

    历史装配/读取不调用此函数；不通过检测草稿字段猜测协议或升级旧包。
    """
    from product.runtime.multidimensional_references import VERSION as REFERENCE_VERSION
    task = packet.get("task")
    if (not isinstance(task, Mapping)
            or task.get("calculation_selection_version") != VERSION
            or indexed_task.get("calculation_selection_version") != VERSION
            or invocation.get("calculation_selection_version") != VERSION
            or packet.get("reference_transport_version") != REFERENCE_VERSION):
        raise ValueError("MULTIDIMENSIONAL_LEGACY_SELECTION_TRANSPORT_EXECUTION_RETIRED")
    if (invocation.get("manifest_hash") != legacy_envelope_hash(invocation, hash_field="manifest_hash")
            or any(task.get(key) != indexed_task.get(key) for key in ("run_id", "invocation_id", "task_id", "agent"))
            or any(task.get(key) != invocation.get(key) for key in ("run_id", "invocation_id", "task_id"))):
        raise ValueError("MULTIDIMENSIONAL_SELECTION_TRANSPORT_BINDING_INVALID")
    prepared_reference_enabled(packet)
    if (task.get("prepared_result_reference_version") != indexed_task.get("prepared_result_reference_version")
            or task.get("prepared_result_reference_version") != invocation.get("prepared_result_reference_version")):
        raise ValueError("MULTIDIMENSIONAL_PREPARED_REFERENCE_BINDING_INVALID")
    # 历史 resolve 可以读取旧回执，但不能把可读版本误当当前执行许可。
    if task.get("submission_version") is not None:
        from product.runtime.research_submission import require_write_protocol
        require_write_protocol(dict(task))


def model_calculation_catalog(root: Path, packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    """交付业务结果及语境；完整身份、hash和路径不要求模型抄录。"""
    from product.runtime.multidimensional_references import translate_references
    result = []
    for ref, entry in build_calculation_catalog(root, packet, include_tools=False).items():
        item = {"calculation_ref": ref, "kind": entry["kind"],
                **{key: entry["calculation"][key] for key in ("method", "value", "unit")},
                "input_fact_count": len(entry["calculation"]["input_evidence_refs"]),
                **{key: entry[key] for key in ("as_of", "window_sessions", "price_basis", "source_claim_ref") if key in entry}}
        result.append(translate_references(item, packet["reference_map"], to_model=True))
    return result


def assemble_calculation_selections(root: Path, packet: Mapping[str, Any], draft: dict[str, Any]) -> dict[str, Any]:
    """只执行明确选择。研究原句保持；用途和限制由所关联主张解释。"""
    if "calculation_selections" not in draft:
        return draft  # 显式旧稿读取/迁移分支仍完整校验，不能自动猜成选择。
    if {"calculations", "artifact_refs"} & draft.keys():
        raise ValueError("MULTIDIMENSIONAL_CALCULATION_SELECTION_MIXED")
    validate_schema_instance(draft["calculation_selections"], _selection_schema(packet), path="$.calculation_selections")
    result = copy.deepcopy(draft)
    if "upstream_calculation_selections" in result:
        raise ValueError("MULTIDIMENSIONAL_CALCULATION_SELECTION_MIXED")
    choices = result.pop("calculation_selections")
    claims = result.get("claims")
    if (not isinstance(claims, list) or any(not isinstance(c, dict) or not isinstance(c.get("claim_id"), str) for c in claims)
            or len({c["claim_id"] for c in claims}) != len(claims)):
        raise ValueError("MULTIDIMENSIONAL_CALCULATION_SELECTION_CLAIMS_INVALID")
    by_id = {c["claim_id"]: c for c in claims}
    if any("calculation_refs" in c for c in claims):
        raise ValueError("MULTIDIMENSIONAL_CALCULATION_SELECTION_MIXED")
    for claim in claims:
        claim["calculation_refs"] = []
    catalog = build_calculation_catalog(root, packet)
    seen, result["calculations"], result["artifact_refs"] = set(), [], []
    for choice in choices:
        ref = choice["calculation_ref"]
        if ref in seen:
            raise ValueError("MULTIDIMENSIONAL_CALCULATION_SELECTION_DUPLICATE")
        seen.add(ref)
        if ref not in catalog:
            raise ValueError("MULTIDIMENSIONAL_CALCULATION_SELECTION_UNKNOWN:" + ref)
        entry = catalog[ref]
        if entry["kind"] == "DEPENDENCY":
            for claim_id in choice["claim_ids"]:
                if claim_id not in by_id:
                    raise ValueError("MULTIDIMENSIONAL_CALCULATION_SELECTION_CLAIM_UNKNOWN:" + claim_id)
                if entry["source_claim_ref"] not in by_id[claim_id].get("research_claim_refs", []):
                    raise ValueError("MULTIDIMENSIONAL_CALCULATION_SELECTION_DEPENDENCY_CLAIM_MISMATCH")
                result.setdefault("upstream_calculation_selections", []).append({
                    "claim_id": claim_id, **copy.deepcopy(entry["upstream_choice"]),
                })
            continue
        calculation = copy.deepcopy(entry["calculation"])
        result["calculations"].append(calculation)
        if calculation["artifact_ref"] not in result["artifact_refs"]:
            result["artifact_refs"].append(calculation["artifact_ref"])
        for claim_id in choice["claim_ids"]:
            if claim_id not in by_id:
                raise ValueError("MULTIDIMENSIONAL_CALCULATION_SELECTION_CLAIM_UNKNOWN:" + claim_id)
            by_id[claim_id]["calculation_refs"].append(calculation["calculation_id"])
    return result
