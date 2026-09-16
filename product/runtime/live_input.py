"""外置 live 持仓、冻结快照与合格价格核算；不启动 Agent。"""
from copy import deepcopy
from decimal import Decimal
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


def value_portfolio(portfolio: dict, snapshot: dict, gate: dict, *, calendar=None) -> dict:
    from product.runtime.evidence_gate import run_live_evidence_gate
    validate_contract("portfolio", portfolio)
    if portfolio.get("schema_version") != "live-portfolio/1.0.0":
        raise ValueError("LIVE_COLLECTION_PORTFOLIO_NOT_VALUABLE")
    validate_contract("snapshot", snapshot)
    if parse_timestamp(portfolio["retrieved_at"]) > parse_timestamp(snapshot["decision_cutoff"]):
        raise ValueError("LIVE_PORTFOLIO_AFTER_CUTOFF")
    if snapshot["portfolio_hash"] != content_hash(portfolio) or gate["input_hash"] != content_hash(snapshot):
        raise ValueError("LIVE_VALUATION_INPUT_MISMATCH")
    if gate["bundle_hash"] != content_hash({k: v for k, v in gate.items() if k != "bundle_hash"}):
        raise ValueError("LIVE_GATE_HASH_MISMATCH")
    if gate.get("source_mode") != "live":
        raise ValueError("LIVE_GATE_SOURCE_INVALID")
    verified = run_live_evidence_gate(snapshot, run_id=gate["run_id"], calendar=calendar).artifact
    if gate != verified:
        raise ValueError("LIVE_GATE_REVALIDATION_FAILED")
    by_security = {}
    for fact in gate["allowed_evidence"]:
        if fact["kind"] == "price" and fact["semantic_field"] == "close_price" and fact["usage"] == "current":
            if fact["evidence_id"] not in gate["allowed_evidence_ids"] or fact["currency"] != "USD":
                raise ValueError("LIVE_PRICE_NOT_ALLOWED")
            by_security.setdefault(fact["security_id"], []).append(fact)
    rows, total = [], Decimal(str(portfolio["cash"]))
    for position in portfolio["positions"]:
        choices = by_security.get(position["security_id"], [])
        if not choices:
            raise ValueError(f"LIVE_PRICE_MISSING:{position['security_id']}")
        latest = max(parse_timestamp(f["as_of"]) for f in choices)
        choices = [f for f in choices if parse_timestamp(f["as_of"]) == latest]
        if len({Decimal(str(f["value"])) for f in choices}) != 1:
            raise ValueError("LIVE_PRICE_CONFLICT")
        price = choices[0]
        amount = Decimal(str(position["quantity"])) * Decimal(str(price["value"]))
        total += amount
        rows.append(dict(position, price=str(price["value"]), market_value=format(amount, "f"),
                         price_evidence_id=price["evidence_id"], price_evidence_hash=content_hash(price)))
    if total <= 0:
        raise ValueError("LIVE_PORTFOLIO_VALUE_INVALID")
    for row in rows:
        row["weight"] = format(Decimal(row["market_value"]) / total, "f")
    result = {"schema_version": "live-valuation/1.0.0", "source_mode": "live", "portfolio_hash": content_hash(portfolio),
              "gate_hash": gate["bundle_hash"], "snapshot_hash": snapshot["snapshot_hash"],
              "total_value": format(total, "f"), "cash": portfolio["cash"], "positions": rows}
    result["valuation_hash"] = content_hash(result)
    return result


def build_live_specialist_inputs(portfolio: dict, snapshot: dict, gate: dict, *, calendar=None,
                                 focus_security_id: str | None = None) -> dict:
    """Gate 后创建独立专业输入，不携带原始披露或另一个 Agent 的结论。"""
    from product.runtime.invocation import build_specialist_inputs, validate_skeptic_first_pass_input
    from product.mcp.live.identity import verify_frozen_identity
    identity = verify_frozen_identity(portfolio, snapshot.get("identity"), cutoff=snapshot["decision_cutoff"])
    valuation = value_portfolio(portfolio, snapshot, gate, calendar=calendar)
    # 仅复用既有公共输入构建器；不写入 fixture_id 或 fixture 审计路径。
    common_input = {"portfolio": dict(portfolio, positions=valuation["positions"]),
                    "decision_cutoff": snapshot["decision_cutoff"]}
    inputs = build_specialist_inputs(run_id=gate["run_id"], fixture=common_input,
        allowed_evidence_ids=gate["allowed_evidence_ids"], research_question=portfolio["research_question"],
        focus_security_id=focus_security_id if focus_security_id is not None else portfolio["focus_security_id"])
    for name in inputs:
        inputs[name] = deepcopy(inputs[name])
        inputs[name].update(source_mode="live", evidence_access="live_evidence.query",
            holding_horizon=portfolio["holding_horizon"], portfolio_hash=content_hash(portfolio),
            snapshot_hash=snapshot["snapshot_hash"], gate_hash=gate["bundle_hash"],
            valuation_hash=valuation["valuation_hash"], data_gaps=list(snapshot["gaps"]))
        inputs[name]["identity_hash"] = identity["identity_hash"]
        # 每个传入模型的价格均保留对应合格 Evidence 的绑定。
        for position, valued in zip(inputs[name]["portfolio_summary"]["positions"], valuation["positions"], strict=True):
            position["price_evidence_id"] = valued["price_evidence_id"]
            position["price_evidence_hash"] = valued["price_evidence_hash"]
    validate_skeptic_first_pass_input(inputs["runtime_skeptic"])
    return inputs
