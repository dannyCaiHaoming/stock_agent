"""只读Provider共用的输入/快照冻结，不导入旧专业委派或Stage控制。"""
from copy import deepcopy
import json
from pathlib import Path

from product.mcp.live.contracts import external_path, validate_contract
from product.mcp.provenance import content_hash, iso_utc, parse_timestamp

def load_live_portfolio(path: Path) -> dict:
    value = json.loads(external_path(path).read_text(encoding="utf-8"))
    validate_contract("portfolio", value)
    return value


def freeze_snapshot(*, snapshot_id: str, portfolio: dict, request_started_at: str,
                    decision_cutoff: str, facts: list, source_access: list,
                    raw_records: list, collection_events: list, gaps: list, identity: dict | None = None,
                    universe: dict | None = None, source_selections: list | None = None) -> dict:
    validate_contract("portfolio", portfolio)
    if parse_timestamp(portfolio["retrieved_at"]) > parse_timestamp(decision_cutoff):
        raise ValueError("LIVE_PORTFOLIO_AFTER_CUTOFF")
    schema_version = "live-snapshot/2.0.0" if any(a.get("provider") == "eastmoney" for a in source_access) else "live-snapshot/1.0.0"
    routed = universe is not None or source_selections is not None
    if routed:
        if not isinstance(universe, dict) or not isinstance(source_selections, list):
            raise ValueError("LIVE_ROUTED_SNAPSHOT_INPUT_MISSING")
        if {s["security_id"] for s in source_selections} != {p["security_id"] for p in portfolio["positions"]}:
            raise ValueError("LIVE_ROUTING_PORTFOLIO_COVERAGE_MISMATCH")
        schema_version = ("live-snapshot/4.0.0" if any(a.get("schema_version") == "live-source-access/4.0.0"
                          for a in source_access) else "live-snapshot/3.0.0")
    body = deepcopy({"schema_version": schema_version, "source_mode": "live",
                     "snapshot_id": snapshot_id, "request_started_at": iso_utc(request_started_at),
                     "decision_cutoff": iso_utc(decision_cutoff), "portfolio_hash": content_hash(portfolio),
                     "source_access": source_access, "facts": facts, "raw_records": raw_records,
                     "collection_events": collection_events, "gaps": gaps, "identity": identity,
                     "freshness_policy_version": "live-freshness/1.0.0"})
    if routed:
        body.update(universe=deepcopy(universe), source_selections=deepcopy(source_selections))
    # 截止由采集调用方在完成后传入；不得晚于截止仍补写一次采集事件。
    for event in collection_events:
        if "completed_at" not in event or parse_timestamp(event["completed_at"]) > parse_timestamp(decision_cutoff):
            raise ValueError("LIVE_COLLECTION_NOT_FINISHED_AT_CUTOFF")
    if identity is not None:
        from product.mcp.live.identity import verify_frozen_identity
        verify_frozen_identity(portfolio, identity, cutoff=decision_cutoff)
    body["snapshot_hash"] = content_hash(body)
    validate_contract("snapshot", body)
    return body


def freeze_research_snapshot(*, request: dict, snapshot_id: str, request_started_at: str,
                             decision_cutoff: str, facts: list, source_access: list,
                             raw_records: list, collection_events: list, gaps: list,
                             universe: dict, source_selections: list) -> dict:
    """非持仓冻结分支；与原 Gate 共用事实/路由/PIT 校验。"""
    from product.runtime.single_stock_input import validate_single_stock_request
    validate_single_stock_request(request)
    cutoff = iso_utc(decision_cutoff)
    if request["resolved_cutoff"] != cutoff:
        raise ValueError("SINGLE_STOCK_SNAPSHOT_CUTOFF_MISMATCH")
    if {item["security_id"] for item in source_selections} != {request["security"]["security_id"]}:
        raise ValueError("SINGLE_STOCK_ROUTING_SCOPE_MISMATCH")
    body = deepcopy({"schema_version": "live-research-snapshot/1.0.0", "source_mode": "live",
        "input_kind": "SINGLE_STOCK_RESEARCH", "research_request": request,
        "research_request_hash": request["request_hash"], "snapshot_id": snapshot_id,
        "request_started_at": iso_utc(request_started_at), "decision_cutoff": cutoff,
        "source_access": source_access, "facts": facts, "raw_records": raw_records,
        "collection_events": collection_events, "gaps": gaps,
        "universe": universe, "source_selections": source_selections,
        "freshness_policy_version": "live-freshness/1.0.0"})
    body["snapshot_hash"] = content_hash(body)
    validate_contract("snapshot", body)
    return body
