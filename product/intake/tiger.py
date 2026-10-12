"""Explicit TigerAccountSnapshot to PortfolioDraft v3 bridge."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
from typing import Any, Mapping

from product.broker.tiger.contracts import validate_contract

from .v3 import ACCOUNT_FIELDS, OPTION_FIELDS, POSITION_FACT_FIELDS, build_draft, build_manual_draft


class TigerIntakeError(ValueError):
    """Stable broker-intake bridge error."""


def _option_date(value: str | None) -> str | None:
    if not value:
        return None
    candidate = str(value)
    if len(candidate) == 8 and candidate.isdigit():
        return date(int(candidate[:4]), int(candidate[4:6]), int(candidate[6:])).isoformat()
    try:
        return date.fromisoformat(candidate).isoformat()
    except ValueError:
        return candidate


def _account_value(snapshot: Mapping[str, Any], field: str) -> Any:
    values = [item for item in snapshot["account_values"] if item["field"] == field]
    scoped = [item for item in values if item["scope"] == "US_USD_SEGMENT" and item["currency"] == "USD"]
    if scoped:
        return scoped[-1]["value"]
    if snapshot["account_scope"] == "BROKER_ACCOUNT":
        whole = [item for item in values if item["scope"] == "WHOLE_ACCOUNT" and item["currency"] in {None, "USD"}]
        if whole:
            return whole[-1]["value"]
    return None


def _to_extracted(draft: dict[str, Any]) -> dict[str, Any]:
    updated = deepcopy(draft)
    for field in ACCOUNT_FIELDS:
        fact = updated["account_snapshot"][field]
        if fact["status"] == "USER_SUPPLIED":
            fact["status"] = "EXTRACTED"
    for position in updated["positions"]:
        for field in ("display_symbol", "display_name", "market", "asset_type"):
            fact = position["identity"][field]
            if fact["status"] == "USER_SUPPLIED":
                fact["status"] = "EXTRACTED"
        for field in POSITION_FACT_FIELDS:
            fact = position[field]
            if fact["status"] == "USER_SUPPLIED":
                fact["status"] = "EXTRACTED"
        if isinstance(position.get("option_contract"), Mapping):
            for field in OPTION_FIELDS:
                fact = position["option_contract"][field]
                if fact["status"] == "USER_SUPPLIED":
                    fact["status"] = "EXTRACTED"
    updated.pop("draft_hash", None)
    return build_draft(updated)


def build_tiger_draft(snapshot: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build a confirmable Draft when the supported US/USD subset is complete.

    The returned coverage object is display metadata bound through the source
    snapshot hash; it is deliberately not inserted into ``unsupported_assets``.
    """
    validate_contract(snapshot)
    if snapshot["schema_version"] != "tiger-account-snapshot/1.0.0":
        raise TigerIntakeError("TIGER_INTAKE_SNAPSHOT_SCHEMA_INVALID")
    supported = [item for item in snapshot["positions"] if item["intake_status"] == "SUPPORTED_US_USD"]
    positions = []
    for item in supported:
        asset_type = "OPTION" if item["asset_type"] == "LISTED_OPTION" else item["asset_type"]
        option = item["option"]
        positions.append({
            "position_id": item["position_id"],
            "display_symbol": item["display_symbol"],
            "display_name": item["display_name"],
            "market": "US",
            "asset_type": asset_type,
            "identity_status": item["identity_status"],
            "canonical_security_id": item["instrument_key"],
            "quantity": item["quantity"],
            "quantity_unit": "CONTRACT" if asset_type == "OPTION" else "SHARE",
            "available_quantity": item["available_quantity"],
            "average_cost_price": item["average_cost"],
            "quote_price": item["market_price"],
            "quote_unit": "PER_UNDERLYING_UNIT" if asset_type == "OPTION" else "PER_SHARE",
            "market_value": item["market_value"],
            "unrealized_pnl_amount": item["unrealized_pnl"],
            "unrealized_pnl_percent": None,
            "currency": "USD",
            "option_contract": None if option is None else {
                "underlying_symbol": option["underlying_symbol"],
                "option_type": option["option_type"],
                "expiration_date": _option_date(option["expiration_date"]),
                "strike": option["strike"],
                "contract_multiplier": option["multiplier"],
                "raw_contract_symbol": option["raw_contract_symbol"],
                "adjustment_status": option["adjustment_status"],
            },
        })
    account_values = {
        "account_type": "UNKNOWN",
        "base_currency": "USD",
        "as_of": snapshot["as_of"],
        "net_liquidation_value": _account_value(snapshot, "net_liquidation"),
        "securities_value": _account_value(snapshot, "gross_position_value"),
        "cash_balance": _account_value(snapshot, "cash_balance"),
        "available_funds": _account_value(snapshot, "cash_available_for_trade"),
        "buying_power": _account_value(snapshot, "buying_power"),
    }
    broker_fields = [
        {
            "label": f"Tiger {item['field']} ({item['scope']})",
            "value": item["value"],
            "currency": item["currency"],
            "source_refs": [snapshot["source_id"]],
            "normalized_meaning": item["field"] if item["scope"] == "US_USD_SEGMENT" else None,
        }
        for item in snapshot["account_values"]
    ]
    draft = build_manual_draft({
        "draft_id": f"draft-{snapshot['snapshot_id']}",
        "source_id": snapshot["source_id"],
        "source_type": "BROKER_READ_ONLY_API",
        "as_of": snapshot["as_of"],
        "retrieved_at": snapshot["retrieved_at"],
        "content_hash": snapshot["content_hash"],
        "synthetic": False,
        "coverage_status": snapshot["coverage_status"],
        "account_ref": snapshot["account_ref"],
        "portfolio_scope": "BROKER_ACCOUNT" if snapshot["account_scope"] == "BROKER_ACCOUNT" else "USER_DEFINED_PORTFOLIO",
        "portfolio_complete": bool(supported),
        "account_snapshot": {**account_values, "broker_reported_fields": broker_fields},
        "positions": positions,
        # Excluded broker assets are coverage facts, not unsupported Handoff rows.
        "unsupported_assets": [],
    })
    coverage = deepcopy(snapshot["coverage"])
    coverage.update({
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_hash": snapshot["content_hash"],
        "portfolio_scope": draft["portfolio_scope"],
        "supported_subset_confirmable": not draft["unresolved_fields"],
    })
    return _to_extracted(draft), coverage


def render_tiger_coverage(coverage: Mapping[str, Any]) -> str:
    lines = [
        "## Tiger 账户覆盖（不等同于投研组合）",
        "",
        f"- 可见持仓：{coverage['visible_position_count']}",
        f"- 纳入 US/USD 子组合：{coverage['supported_position_count']}",
        f"- 已采集但投研接入待定：{coverage['excluded_position_count']}",
    ]
    for item in coverage["excluded_assets"]:
        lines.append(f"- 待定：{item['display_symbol']} / {item['market']} / {item['currency']} / {item['asset_type']}")
    return "\n".join(lines)
