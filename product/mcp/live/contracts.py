"""Live 数据契约与确定性校验；不加载行情 SDK 或模型。"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json
import math
from pathlib import Path

from product.mcp.provenance import content_hash, parse_timestamp, iso_utc
from product.runtime.schema_validation import validate_schema_instance

SCHEMAS = Path(__file__).resolve().parents[2] / "schemas" / "runtime"
APPROVAL_RECORD = Path(__file__).with_name("personal-research-approval.json")


def _finite_json(value):
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("LIVE_NON_FINITE_NUMBER")
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("LIVE_JSON_KEY_INVALID")
            _finite_json(item)
    elif isinstance(value, list):
        for item in value:
            _finite_json(item)
    elif value is not None and not isinstance(value, (str, int, float, bool)):
        raise ValueError("LIVE_JSON_VALUE_INVALID")


def _extra_schema_checks(value, schema):
    # 复用现有校验器；补其尚不实现的两个标准关键词，不改变旧 fixture 校验。
    if isinstance(value, list):
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise ValueError("LIVE_MAX_ITEMS")
        for item in value:
            _extra_schema_checks(item, schema.get("items", {}))
    elif isinstance(value, dict):
        for key, item in value.items():
            _extra_schema_checks(item, schema.get("properties", {}).get(key, {}))
    elif isinstance(value, (float, int)) and not isinstance(value, bool):
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            raise ValueError("LIVE_EXCLUSIVE_MINIMUM")


def validate_contract(kind: str, value: dict) -> None:
    if kind not in ("portfolio", "fact", "snapshot", "source-access", "universe", "source-selection"):
        raise ValueError("LIVE_CONTRACT_UNKNOWN")
    _finite_json(value)
    suffix = "-v2" if kind in ("portfolio", "fact", "source-access", "snapshot") and value.get("schema_version") == f"live-{kind}/2.0.0" else ""
    if kind in ("source-access", "snapshot") and value.get("schema_version") == f"live-{kind}/3.0.0":
        suffix = "-v3"
    if kind in ("source-access", "snapshot") and value.get("schema_version") == f"live-{kind}/4.0.0":
        suffix = "-v4"
    schema = json.loads((SCHEMAS / f"live-{kind}{suffix}.schema.json").read_text())
    validate_schema_instance(value, schema)
    _extra_schema_checks(value, schema)
    for field in ("as_of", "retrieved_at", "published_at", "checked_at", "request_started_at", "decision_cutoff"):
        if field in value:
            parse_timestamp(value[field])
    if kind == "source-access" and suffix in ("-v3", "-v4"):
        roles = {"nasdaq": "universe", "yahoo": "primary_market", "eastmoney": "backup_market", "sec": "disclosure"}
        if value["data_role"] != roles[value["provider"]]:
            raise ValueError("LIVE_SOURCE_ROLE_MISMATCH")
        from product.mcp.live.source_routing import validate_source_version
        validate_source_version(value)
    if kind == "source-selection":
        from product.mcp.live.source_routing import validate_selection
        validate_selection(value)
    elif kind == "universe":
        from product.mcp.live.nasdaq import validate_universe
        validate_universe(value)
    elif kind == "portfolio":
        if parse_timestamp(value["as_of"]) > parse_timestamp(value["retrieved_at"]):
            raise ValueError("LIVE_INPUT_TIME_INVALID")
        positions = value["positions"]
        if any(not p["security_id"].strip() for p in positions):
            raise ValueError("LIVE_SECURITY_FIELD_EMPTY")
        if len({p["security_id"] for p in positions}) != len(positions) or len({p["ticker"] for p in positions}) != len(positions):
            raise ValueError("LIVE_DUPLICATE_SECURITY")
        if suffix == "-v2":
            if value.get("purpose") != "COMMON_STOCK_DATA_COLLECTION":
                raise ValueError("LIVE_COLLECTION_PURPOSE_INVALID")
            if any(
                p.get("exchange") is None and p.get("share_class") is not None
                for p in positions
            ):
                raise ValueError("LIVE_COLLECTION_PARTIAL_IDENTITY_INVALID")
        else:
            if any(not p["share_class"].strip() for p in positions):
                raise ValueError("LIVE_SECURITY_FIELD_EMPTY")
            if value["focus_security_id"] not in {p["security_id"] for p in positions}:
                raise ValueError("LIVE_FOCUS_UNKNOWN")
            if value["mandate"]["max_position_weight"] <= 0:
                raise ValueError("LIVE_MANDATE_INVALID")
            if any(not value[key].strip() for key in ("holding_horizon", "research_question", "source_id")):
                raise ValueError("LIVE_INPUT_EMPTY")
    elif kind == "fact":
        ids = value["parent_ids"]
        if len(ids) != len(value["parent_hashes"]):
            raise ValueError("LIVE_PARENT_HASH_COUNT")
        if value["kind"] == "derived":
            if not ids or value["source_type"] != "derived" or not value["metadata"].get("formula"):
                raise ValueError("LIVE_DERIVATION_INVALID")
        elif ids or value["source_type"] == "derived":
            raise ValueError("LIVE_UNEXPECTED_PARENTS")
        if value["kind"] in ("financial", "price"):
            try:
                number = Decimal(str(value["value"]))
            except Exception as exc:
                raise ValueError("LIVE_FACT_NUMBER_INVALID") from exc
            if not number.is_finite() or (value["kind"] == "price" and number <= 0):
                raise ValueError("LIVE_FACT_NUMBER_INVALID")
    elif kind == "snapshot":
        if value["schema_version"] in ("live-snapshot/3.0.0", "live-snapshot/4.0.0"):
            from product.mcp.live.source_routing import validate_selection
            validate_contract("universe", value["universe"])
            if parse_timestamp(value["universe"]["retrieved_at"]) > parse_timestamp(value["decision_cutoff"]):
                raise ValueError("LIVE_UNIVERSE_AFTER_CUTOFF")
            sources = value["source_access"]
            if len(sources) != 4 or {a.get("provider") for a in sources} != {"nasdaq", "yahoo", "eastmoney", "sec"}:
                raise ValueError("LIVE_ROUTING_SOURCE_SET_INVALID")
            if any(a.get("schema_version") != value["schema_version"].replace("snapshot", "source-access") for a in sources):
                raise ValueError("LIVE_ROUTING_ACCESS_VERSION_INVALID")
            selections = value["source_selections"]
            if len({s["security_id"] for s in selections}) != len(selections):
                raise ValueError("LIVE_DUPLICATE_SOURCE_SELECTION")
            # SourceSelection 只封闭行情路由选中的当前 close_price；同一原文
            # 后续生成的 OHLCV/复权研究序列属于 comparison 事实，不能反向
            # 改写已冻结的主备来源选择证据集合。
            price_facts = [
                f for f in value["facts"]
                if f["kind"] == "price"
                and f["semantic_field"] == "close_price"
                and f["usage"] == "current"
            ]
            if not {f["security_id"] for f in price_facts} <= {s["security_id"] for s in selections}:
                raise ValueError("LIVE_SOURCE_SELECTION_MISSING")
            for selection in selections:
                validate_contract("source-selection", selection)
                validate_selection(selection, [f for f in price_facts if f["security_id"] == selection["security_id"]])
                if any(parse_timestamp(a["completed_at"]) > parse_timestamp(value["decision_cutoff"]) for a in selection["attempts"]):
                    raise ValueError("LIVE_SOURCE_SELECTION_AFTER_CUTOFF")
        if value["schema_version"] == "live-snapshot/2.0.0":
            validate_current_sources(value["source_access"], require_authorized=False)
            if any(f.get("source_type") not in ("eastmoney", "sec", "derived") for f in value["facts"]):
                raise ValueError("LIVE_CURRENT_MIXED_SOURCE_REJECTED")
            if any(f.get("source_type") == "eastmoney" and f.get("schema_version") != "live-fact/2.0.0" for f in value["facts"]):
                raise ValueError("LIVE_CURRENT_FACT_VERSION_INVALID")
        if value["snapshot_hash"] != content_hash({k: v for k, v in value.items() if k != "snapshot_hash"}):
            raise ValueError("LIVE_SNAPSHOT_HASH_MISMATCH")
        if parse_timestamp(value["request_started_at"]) > parse_timestamp(value["decision_cutoff"]):
            raise ValueError("LIVE_FREEZE_TIME_INVALID")
        for fact in value["facts"]:
            validate_contract("fact", fact)
        if len({f["evidence_id"] for f in value["facts"]}) != len(value["facts"]):
            raise ValueError("LIVE_DUPLICATE_EVIDENCE")
        for access in value["source_access"]:
            validate_contract("source-access", access)
            if value["schema_version"] == "live-snapshot/4.0.0":
                require_source_admission(access, at=value["request_started_at"])
        if len({a["provider"] for a in value["source_access"]}) != len(value["source_access"]):
            raise ValueError("LIVE_DUPLICATE_SOURCE")
def require_source_admission(access: dict, *, at=None) -> None:
    """同一准入入口；历史契约不重解释，新契约不把个人批准当上游授权。"""
    from datetime import datetime, UTC
    validate_contract("source-access", access)
    if access["schema_version"] != "live-source-access/4.0.0":
        if access["status"] != "AUTHORIZED":
            raise ValueError("LIVE_SOURCE_NOT_AUTHORIZED")
        return
    limit = parse_timestamp(at) if at is not None else datetime.now(UTC)
    approval, upstream = access["operator_approval"], access["upstream_permission"]
    record = approval["record"]
    # 随插件锁定的人工批准记录；不依赖安装目录外存在开发仓库 docs/。
    expected = json.loads(APPROVAL_RECORD.read_text(encoding="utf-8"))
    if approval["record_hash"] != content_hash(record) or record != expected:
        raise ValueError("LIVE_APPROVAL_RECORD_MISMATCH")
    if approval["status"] != "APPROVED":
        raise ValueError("LIVE_OPERATOR_NOT_APPROVED")
    if upstream["status"] == "DENIED":
        raise ValueError("LIVE_UPSTREAM_DENIED")
    if any(parse_timestamp(t) > limit for t in (record["approved_at"], access["checked_at"], upstream["checked_at"])):
        raise ValueError("LIVE_ACCESS_CHECKED_IN_FUTURE")


def source_is_admitted(access: dict, *, at=None) -> bool:
    try:
        require_source_admission(access, at=at)
    except ValueError:
        return False
    return True

def validate_current_sources(access: list, *, require_authorized: bool = True) -> dict:
    """当前采集只接受东方财富＋SEC；旧 Schema 仅用于历史读取。"""
    from product.mcp.live.eastmoney_transport import AKSHARE_VERSION, ADAPTER_VERSION as EM_VERSION
    from product.mcp.live.sec import ADAPTER_VERSION as SEC_VERSION
    from product.mcp.live.sec_client import CLIENT_VERSION
    if not isinstance(access, list) or len(access) != 2:
        raise ValueError("LIVE_TWO_SOURCE_ACCESS_RECORDS_REQUIRED")
    for item in access:
        validate_contract("source-access", item)
    policies = {item["provider"]: item for item in access}
    if set(policies) != {"eastmoney", "sec"}:
        raise ValueError("LIVE_CURRENT_SOURCE_REJECTED")
    for provider, client, adapter, domains in (
        ("eastmoney", f"akshare/{AKSHARE_VERSION}", EM_VERSION, {"63.push2his.eastmoney.com"}),
        ("sec", CLIENT_VERSION, SEC_VERSION, {"data.sec.gov", "www.sec.gov"}),
    ):
        item = policies[provider]
        if item["schema_version"] != "live-source-access/2.0.0" or item["client_version"] != client or item["adapter_version"] != adapter:
            raise ValueError("LIVE_SOURCE_VERSION_MISMATCH")
        if set(item["domains"]) != domains:
            raise ValueError("LIVE_SOURCE_DOMAIN_SCOPE_INVALID")
        if require_authorized and item["status"] != "AUTHORIZED":
            raise ValueError("LIVE_SOURCE_PAUSED_OR_NOT_AUTHORIZED")
    return policies


def external_path(path: Path) -> Path:
    resolved = Path(path).resolve()
    repo = Path(__file__).resolve().parents[3]
    if resolved == repo or repo in resolved.parents:
        raise ValueError("LIVE_PRIVATE_PATH_INSIDE_REPOSITORY")
    return resolved


def normalize_sec_fact(fact: dict, *, security_id: str, usage: str = "current") -> dict:
    if fact.get("security_id", security_id) != security_id:
        raise ValueError("LIVE_SECURITY_BINDING_MISMATCH")
    if "parent_ids" in fact:
        raise ValueError("LIVE_DERIVED_REQUIRES_NORMALIZED_PARENTS")
    is_text = "text" in fact
    value = {
        "schema_version": "live-fact/1.0.0", "evidence_id": fact["evidence_id"],
        "security_id": security_id, "semantic_field": fact["section"] if is_text else f"{fact['taxonomy']}.{fact['tag']}",
        "value": fact["text"] if is_text else fact["value"], "unit": "text" if is_text else fact["unit"],
        "currency": None if is_text else (fact["unit"] if fact["unit"] == "USD" else None),
        "source_id": fact["source_id"], "source_type": "sec", "source_locator": fact["source_locator"],
        "source_version": fact.get("parser_version", fact.get("adapter_version")),
        "as_of": fact["as_of"], "published_at": fact["published_at"],
        "published_at_policy": fact.get("published_at_policy", "submission_acceptance_datetime"),
        "retrieved_at": iso_utc(max(parse_timestamp(fact["retrieved_at"]), parse_timestamp(fact.get("publication_retrieved_at", fact["retrieved_at"])))),
        "raw_content_hash": fact["raw_content_hash"],
        "kind": "disclosure" if is_text else "financial", "usage": usage,
        "parent_ids": [], "parent_hashes": [], "metadata": deepcopy(fact),
    }
    validate_contract("fact", value)
    return value


def compare_live_financials(current_id: str, prior_id: str, facts: dict[str, dict]) -> dict:
    from product.mcp.live.financials import compare_year_over_year
    if current_id not in facts or prior_id not in facts:
        raise ValueError("LIVE_COMPARISON_PARENT_MISSING")
    parents = [facts[current_id], facts[prior_id]]
    raw = {}
    for parent in parents:
        validate_contract("fact", parent)
        if parent["kind"] != "financial":
            raise ValueError("LIVE_COMPARISON_REQUIRES_FINANCIALS")
        raw[parent["evidence_id"]] = dict(parent["metadata"], **{key: parent[key] for key in (
            "evidence_id", "security_id", "value", "source_id", "source_locator", "as_of", "published_at", "retrieved_at", "unit")})
    result = compare_year_over_year(current_id, prior_id, raw)
    normalized = {"schema_version": "live-fact/1.0.0", "evidence_id": result["evidence_id"],
                  "security_id": parents[0]["security_id"], "semantic_field": result["semantic_field"],
                  "value": result["value"], "unit": parents[0]["unit"], "currency": parents[0]["currency"],
                  "source_id": result["source_id"], "source_type": "derived", "source_locator": "parent_evidence",
                  "source_version": result["calculation_version"],
                  **{key: result[key] for key in ("as_of", "published_at", "retrieved_at")},
                  "published_at_policy": "maximum_parent_publication", "kind": "derived", "usage": "current",
                  "parent_ids": [current_id, prior_id], "parent_hashes": [content_hash(p) for p in parents],
                  "raw_content_hash": content_hash([p["raw_content_hash"] for p in parents]),
                  "metadata": dict(result, raw_hash_policy="aggregate_parent_raw_hashes")}
    normalized["evidence_id"] = "ev-live-derived-" + content_hash({k:v for k,v in normalized.items() if k != "evidence_id"})
    validate_contract("fact", normalized)
    return normalized
