"""Portfolio Intake v3 deterministic contracts.

Codex and the ``portfolio-intake`` Skill interpret screenshots.  This module
only normalizes already structured observations, validates provenance and
confirmation, reconciles account totals, and persists neutral account state.
It never performs security research or invokes an Agent/LLM.
"""

from __future__ import annotations

import copy
import json
import math
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.schema_validation import SchemaValidationError, validate_schema_instance


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = REPO_ROOT / "product" / "schemas" / "intake"
DRAFT_SCHEMA_VERSION = "portfolio-draft/3.0.0"
HANDOFF_SCHEMA_VERSION = "portfolio-handoff/3.0.0"
RESOLVED_STATUSES = {"EXTRACTED", "USER_SUPPLIED"}
UNRESOLVED_STATUSES = {"MISSING", "AMBIGUOUS", "CONFLICTING"}
ASSET_TYPES = {"COMMON_STOCK", "ETF", "OPTION"}
IDENTITY_STATUSES = {"OBSERVED", "USER_CONFIRMED", "RESOLVED", "AMBIGUOUS"}
SOURCE_TYPES = {
    "SCREENSHOT", "MANUAL", "USER_CORRECTION", "BROKER_READ_ONLY_API", "BROKER_STATEMENT"
}
ACCOUNT_FIELDS = (
    "account_type", "base_currency", "as_of", "net_liquidation_value", "securities_value",
    "cash_balance", "available_funds", "buying_power", "margin_used",
    "initial_margin_requirement", "maintenance_margin_requirement", "excess_liquidity",
    "margin_utilization_ratio",
)
OPTION_FIELDS = (
    "underlying_symbol", "option_type", "expiration_date", "strike",
    "contract_multiplier", "raw_contract_symbol", "adjustment_status",
)
POSITION_FACT_FIELDS = (
    "quantity", "quantity_unit", "available_quantity", "average_cost_price", "quote_price",
    "quote_unit", "market_value", "unrealized_pnl_amount", "unrealized_pnl_percent", "currency",
)
FORBIDDEN_HANDOFF_FIELDS = {
    "required_capability", "capability_gaps", "council_readiness", "research_plan",
    "holding_horizon", "research_question", "benchmark_id", "mandate_artifact_id",
    "research_scope",
}
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.\-]{0,31}$")


class IntakeV3ValidationError(ValueError):
    """Fail-closed v3 intake contract violation."""


def _schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))


def _without_hash(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    result = copy.deepcopy(dict(value))
    result.pop(key, None)
    return result


def _datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise IntakeV3ValidationError(f"INTAKE_V3_DATETIME_REQUIRED:{field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IntakeV3ValidationError(f"INTAKE_V3_DATETIME_INVALID:{field}") from exc
    if parsed.tzinfo is None:
        raise IntakeV3ValidationError(f"INTAKE_V3_DATETIME_TIMEZONE_REQUIRED:{field}")
    return parsed


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise IntakeV3ValidationError(f"INTAKE_V3_NUMBER_INVALID:{field}")
    return float(value)


def _fact(value: Any, status: str, source_refs: list[str], note: str | None = None) -> dict[str, Any]:
    return {
        "value": value,
        "status": status,
        "source_refs": list(dict.fromkeys(source_refs)),
        "candidates": [],
        "note": note,
    }


def _manual_fact(value: Any, source_id: str, *, note: str | None = None) -> dict[str, Any]:
    return _fact(value, "USER_SUPPLIED", [source_id], note) if value is not None else _fact(None, "MISSING", [], note)


def _validate_fact(
    fact: Any, *, path: str, source_ids: set[str], numeric: bool = False, allowed: set[str] | None = None
) -> None:
    if not isinstance(fact, Mapping):
        raise IntakeV3ValidationError(f"INTAKE_V3_FIELD_INVALID:{path}")
    status = fact.get("status")
    value = fact.get("value")
    refs = fact.get("source_refs")
    candidates = fact.get("candidates")
    if status not in RESOLVED_STATUSES | UNRESOLVED_STATUSES:
        raise IntakeV3ValidationError(f"INTAKE_V3_FIELD_STATUS_INVALID:{path}")
    if not isinstance(refs, list) or len(refs) != len(set(refs)):
        raise IntakeV3ValidationError(f"INTAKE_V3_SOURCE_REFS_INVALID:{path}")
    if any(ref not in source_ids for ref in refs):
        raise IntakeV3ValidationError(f"INTAKE_V3_SOURCE_REF_DANGLING:{path}")
    if not isinstance(candidates, list):
        raise IntakeV3ValidationError(f"INTAKE_V3_CANDIDATES_INVALID:{path}")
    if status in RESOLVED_STATUSES and (value is None or not refs or candidates):
        raise IntakeV3ValidationError(f"INTAKE_V3_RESOLVED_FIELD_INVALID:{path}")
    if status == "MISSING" and (value is not None or refs or candidates):
        raise IntakeV3ValidationError(f"INTAKE_V3_MISSING_FIELD_INVALID:{path}")
    if status in {"AMBIGUOUS", "CONFLICTING"} and (
        value is not None or len(candidates) < 2 or not refs
    ):
        raise IntakeV3ValidationError(f"INTAKE_V3_UNCERTAIN_FIELD_INVALID:{path}")
    values = ([value] if value is not None else []) + list(candidates)
    if numeric:
        for index, item in enumerate(values):
            _number(item, f"{path}.candidate[{index}]")
    if allowed is not None and any(item not in allowed for item in values):
        raise IntakeV3ValidationError(f"INTAKE_V3_FIELD_VALUE_INVALID:{path}")


def _validate_sources(items: Any) -> set[str]:
    if not isinstance(items, list) or not items:
        raise IntakeV3ValidationError("INTAKE_V3_SOURCES_REQUIRED")
    source_ids: list[str] = []
    for index, source in enumerate(items):
        if not isinstance(source, Mapping):
            raise IntakeV3ValidationError(f"INTAKE_V3_SOURCE_INVALID:{index}")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise IntakeV3ValidationError(f"INTAKE_V3_SOURCE_ID_INVALID:{index}")
        source_ids.append(source_id)
        if source.get("source_type") not in SOURCE_TYPES:
            raise IntakeV3ValidationError(f"INTAKE_V3_SOURCE_TYPE_INVALID:{source_id}")
        as_of = _datetime(source.get("as_of"), f"source_items[{index}].as_of")
        retrieved_at = _datetime(source.get("retrieved_at"), f"source_items[{index}].retrieved_at")
        if as_of > retrieved_at:
            raise IntakeV3ValidationError(f"INTAKE_V3_SOURCE_TIME_INVALID:{source_id}")
        external_ref = source.get("external_ref")
        if external_ref is not None:
            if not isinstance(external_ref, str) or not external_ref:
                raise IntakeV3ValidationError(f"INTAKE_V3_EXTERNAL_REF_INVALID:{source_id}")
            path = Path(external_ref).expanduser()
            path = (REPO_ROOT / path).resolve() if not path.is_absolute() else path.resolve()
            if not path.is_file():
                raise IntakeV3ValidationError(f"INTAKE_V3_EXTERNAL_REF_MISSING:{source_id}")
            if source.get("content_hash") != file_hash(path):
                raise IntakeV3ValidationError(f"INTAKE_V3_SOURCE_HASH_MISMATCH:{source_id}")
            if source.get("source_type") == "SCREENSHOT" and source.get("synthetic") is False:
                try:
                    path.relative_to(REPO_ROOT)
                except ValueError:
                    pass
                else:
                    raise IntakeV3ValidationError("INTAKE_V3_PRIVATE_SOURCE_INSIDE_REPO")
    if len(source_ids) != len(set(source_ids)):
        raise IntakeV3ValidationError("INTAKE_V3_SOURCE_ID_DUPLICATE")
    return set(source_ids)


def _required_unresolved(draft: Mapping[str, Any]) -> list[str]:
    result: list[str] = []
    account = draft["account_snapshot"]
    for field in ("base_currency", "as_of", "cash_balance"):
        if account[field]["status"] in UNRESOLVED_STATUSES:
            result.append(f"account_snapshot.{field}")
    if not draft["positions"]:
        result.append("positions")
    for index, position in enumerate(draft["positions"]):
        identity = position["identity"]
        for field in ("display_symbol", "market", "asset_type"):
            if identity[field]["status"] in UNRESOLVED_STATUSES:
                result.append(f"positions[{index}].identity.{field}")
        if identity["identity_status"] == "AMBIGUOUS":
            result.append(f"positions[{index}].identity")
        for field in ("quantity", "quantity_unit", "currency"):
            if position[field]["status"] in UNRESOLVED_STATUSES:
                result.append(f"positions[{index}].{field}")
        if identity["asset_type"].get("value") == "OPTION":
            option = position.get("option_contract")
            if not isinstance(option, Mapping):
                result.append(f"positions[{index}].option_contract")
            else:
                for field in ("underlying_symbol", "option_type", "expiration_date", "strike", "contract_multiplier", "adjustment_status"):
                    if option[field]["status"] in UNRESOLVED_STATUSES:
                        result.append(f"positions[{index}].option_contract.{field}")
                if option["adjustment_status"].get("value") == "UNKNOWN":
                    result.append(f"positions[{index}].option_contract.adjustment_status")
    if draft.get("unsupported_assets"):
        result.append("unsupported_assets")
    if not draft.get("portfolio_complete"):
        result.append("portfolio_complete")
    for row in draft.get("rows", []):
        if row.get("row_type") is None:
            result.append(f"rows.{row.get('row_id', 'unknown')}.row_type")
    return sorted(set(result))


def _draft_lineage_paths(draft: Mapping[str, Any]) -> set[str]:
    """Return normalized paths that have a resolved direct source."""

    paths = {
        f"account_snapshot.{field}"
        for field in ACCOUNT_FIELDS
        if draft["account_snapshot"][field].get("value") is not None
    }
    for position in draft["positions"]:
        prefix = f"portfolio.positions.{position['position_id']}"
        paths.update(
            f"{prefix}.{field}"
            for field in ("display_symbol", "display_name", "market", "asset_type")
            if position["identity"][field].get("value") is not None
        )
        paths.update(
            f"{prefix}.{field}"
            for field in POSITION_FACT_FIELDS
            if position[field].get("value") is not None
        )
        if isinstance(position.get("option_contract"), Mapping):
            paths.update(
                f"{prefix}.option_contract.{field}"
                for field in OPTION_FIELDS
                if position["option_contract"][field].get("value") is not None
            )
    return paths


def _reconcile(draft: Mapping[str, Any], tolerance: float = 0.02) -> dict[str, Any]:
    account = draft["account_snapshot"]
    reported = account["net_liquidation_value"].get("value")
    cash = account["cash_balance"].get("value")
    market_values = [position["market_value"].get("value") for position in draft["positions"]]
    components = ["account_snapshot.cash_balance"] + [
        f"positions[{index}].market_value" for index in range(len(market_values))
    ]
    if reported is None or cash is None or any(value is None for value in market_values):
        return {
            "status": "NOT_EVALUATED", "reported_value": reported, "calculated_value": None,
            "difference": None, "tolerance": tolerance, "components": components,
            "formula_id": "NET_LIQUIDATION_FROM_SIGNED_POSITIONS_AND_CASH", "formula_version": "1.0.0",
        }
    calculated = round(float(cash) + sum(float(value) for value in market_values), 8)
    difference = round(float(reported) - calculated, 8)
    return {
        "status": "RECONCILED" if abs(difference) <= tolerance else "UNRECONCILED",
        "reported_value": reported, "calculated_value": calculated, "difference": difference,
        "tolerance": tolerance, "components": components,
        "formula_id": "NET_LIQUIDATION_FROM_SIGNED_POSITIONS_AND_CASH", "formula_version": "1.0.0",
    }


def build_manual_draft(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Expand concise manual account input into a v3 Draft."""

    source_id = str(payload.get("source_id") or "source-manual")
    as_of = payload.get("as_of")
    retrieved_at = payload.get("retrieved_at")
    _datetime(as_of, "as_of")
    _datetime(retrieved_at, "retrieved_at")
    account_input = payload.get("account_snapshot", {})
    if not isinstance(account_input, Mapping):
        raise IntakeV3ValidationError("INTAKE_V3_ACCOUNT_SNAPSHOT_INVALID")
    account = {
        field: _manual_fact(
            account_input.get(field, payload.get("cash") if field == "cash_balance" else payload.get(field)),
            source_id,
        )
        for field in ACCOUNT_FIELDS
    }
    account["account_type"] = _manual_fact(account_input.get("account_type", "UNKNOWN"), source_id)
    account["base_currency"] = _manual_fact(account_input.get("base_currency", payload.get("base_currency")), source_id)
    account["as_of"] = _manual_fact(account_input.get("as_of", as_of), source_id)
    account["broker_reported_fields"] = copy.deepcopy(account_input.get("broker_reported_fields", []))
    positions: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for index, raw_row in enumerate(payload.get("reported_rows", [])):
        if not isinstance(raw_row, Mapping):
            raise IntakeV3ValidationError(f"INTAKE_V3_REPORTED_ROW_INVALID:{index}")
        rows.append({
            "row_id": str(raw_row.get("row_id") or f"reported-row-{index + 1}"),
            "row_type": raw_row.get("row_type"),
            "label": str(raw_row.get("label") or "reported row"),
            "position_id": None,
            "reported_field": raw_row.get("reported_field"),
            "reported_value": raw_row.get("reported_value"),
            "currency": raw_row.get("currency", account["base_currency"]["value"]),
            "source_refs": [source_id],
            "note": raw_row.get("note"),
        })
    for index, raw in enumerate(payload.get("positions", [])):
        if not isinstance(raw, Mapping):
            raise IntakeV3ValidationError(f"INTAKE_V3_POSITION_INVALID:{index}")
        asset_type = str(raw.get("asset_type", "COMMON_STOCK")).upper()
        symbol = raw.get("display_symbol", raw.get("ticker"))
        identity_status = raw.get("identity_status", "USER_CONFIRMED")
        option_raw = raw.get("option_contract")
        option = None
        if asset_type == "OPTION":
            option_raw = option_raw if isinstance(option_raw, Mapping) else {}
            option = {field: _manual_fact(option_raw.get(field), source_id) for field in OPTION_FIELDS}
            if option["adjustment_status"]["value"] is None:
                option["adjustment_status"] = _manual_fact("STANDARD", source_id)
        position_id = str(raw.get("position_id") or f"position-{index + 1}")
        positions.append(
            {
                "position_id": position_id,
                "identity": {
                    "display_symbol": _manual_fact(symbol, source_id),
                    "display_name": _manual_fact(raw.get("display_name"), source_id),
                    "market": _manual_fact(raw.get("market", "US"), source_id),
                    "asset_type": _manual_fact(asset_type, source_id),
                    "identity_status": identity_status,
                    "canonical_security_id": raw.get("canonical_security_id"),
                    "candidates": copy.deepcopy(raw.get("identity_candidates", [])),
                },
                "quantity": _manual_fact(raw.get("quantity"), source_id),
                "quantity_unit": _manual_fact(raw.get("quantity_unit", "CONTRACT" if asset_type == "OPTION" else "SHARE"), source_id),
                "available_quantity": _manual_fact(raw.get("available_quantity"), source_id),
                "average_cost_price": _manual_fact(raw.get("average_cost_price", raw.get("cost_basis")), source_id),
                "quote_price": _manual_fact(raw.get("quote_price"), source_id),
                "quote_unit": _manual_fact(raw.get("quote_unit", "PER_UNDERLYING_UNIT" if asset_type == "OPTION" else "PER_SHARE") if raw.get("quote_price") is not None or raw.get("average_cost_price", raw.get("cost_basis")) is not None else None, source_id),
                "market_value": _manual_fact(raw.get("market_value"), source_id),
                "unrealized_pnl_amount": _manual_fact(raw.get("unrealized_pnl_amount"), source_id),
                "unrealized_pnl_percent": _manual_fact(raw.get("unrealized_pnl_percent"), source_id),
                "currency": _manual_fact(raw.get("currency", account["base_currency"]["value"]), source_id),
                "option_contract": option,
            }
        )
        rows.append({
            "row_id": f"row-{position_id}", "row_type": "POSITION", "label": str(symbol),
            "position_id": position_id, "reported_field": None, "reported_value": None,
            "currency": account["base_currency"]["value"], "source_refs": [source_id], "note": None,
        })
    source_type = payload.get("source_type", "MANUAL")
    external_ref = payload.get("external_ref")
    content_hash = payload.get("content_hash")
    if content_hash is None and isinstance(external_ref, str):
        external_path = Path(external_ref).expanduser().resolve()
        content_hash = file_hash(external_path) if external_path.is_file() else None
    source = {
        "source_id": source_id, "source_type": source_type, "as_of": as_of,
        "retrieved_at": retrieved_at, "content_hash": content_hash or canonical_hash(dict(payload)),
        "external_ref": external_ref, "synthetic": bool(payload.get("synthetic", False)),
        "coverage_status": "COMPLETE" if payload.get("portfolio_complete") else payload.get("coverage_status", "PARTIAL"),
    }
    return build_draft({
        "draft_id": payload.get("draft_id"), "portfolio_scope": payload.get("portfolio_scope"),
        "portfolio_complete": payload.get("portfolio_complete"), "account_ref": payload.get("account_ref"),
        "source_items": [source], "account_snapshot": account, "rows": rows, "positions": positions,
        "unsupported_assets": copy.deepcopy(payload.get("unsupported_assets", [])),
        "reported_totals": copy.deepcopy(payload.get("reported_totals", [])),
        "derived_lineage": copy.deepcopy(payload.get("derived_lineage", [])),
    })


def build_draft(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize an already structured v3 Skill observation."""

    declared_version = payload.get("schema_version")
    if declared_version is not None and declared_version != DRAFT_SCHEMA_VERSION:
        raise IntakeV3ValidationError(f"INTAKE_V3_VERSION_INVALID:{declared_version}")
    draft = copy.deepcopy(dict(payload))
    draft["schema_version"] = DRAFT_SCHEMA_VERSION
    draft.setdefault("account_ref", None)
    draft.setdefault("rows", [])
    draft.setdefault("positions", [])
    draft.setdefault("unsupported_assets", [])
    draft.setdefault("reported_totals", [])
    draft.setdefault("derived_lineage", [])
    if not draft["reported_totals"]:
        draft["reported_totals"] = [
            {
                "field": row["reported_field"], "value": row["reported_value"],
                "currency": row["currency"], "row_id": row["row_id"],
                "source_refs": row["source_refs"],
            }
            for row in draft["rows"]
            if row.get("row_type") in {"ACCOUNT_TOTAL", "ASSET_CLASS_SUBTOTAL", "CASH_BALANCE"}
            and row.get("reported_field") is not None
            and row.get("reported_value") is not None
            and row.get("currency") is not None
        ]
    for position in draft["positions"]:
        identity = position.get("identity", {})
        for name in ("display_symbol", "market", "asset_type"):
            fact = identity.get(name)
            if isinstance(fact, Mapping) and isinstance(fact.get("value"), str):
                fact["value"] = fact["value"].strip().upper()
        option = position.get("option_contract")
        if isinstance(option, Mapping):
            for name in ("underlying_symbol", "option_type", "raw_contract_symbol", "adjustment_status"):
                fact = option.get(name)
                if isinstance(fact, Mapping) and isinstance(fact.get("value"), str):
                    fact["value"] = fact["value"].strip().upper()
    draft["reconciliation"] = _reconcile(draft)
    draft["unresolved_fields"] = _required_unresolved(draft)
    draft["draft_hash"] = canonical_hash(_without_hash(draft, "draft_hash"))
    validate_draft(draft)
    return draft


def validate_draft(draft: Mapping[str, Any]) -> None:
    try:
        validate_schema_instance(draft, _schema("portfolio-draft-v3.schema.json"))
    except SchemaValidationError as exc:
        raise IntakeV3ValidationError(f"INTAKE_V3_DRAFT_SCHEMA_INVALID:{exc}") from exc
    if draft.get("draft_hash") != canonical_hash(_without_hash(draft, "draft_hash")):
        raise IntakeV3ValidationError("INTAKE_V3_DRAFT_HASH_MISMATCH")
    account_ref = draft.get("account_ref")
    if account_ref is not None:
        digits = re.sub(r"\D", "", account_ref)
        if len(digits) > 4 and "*" not in account_ref:
            raise IntakeV3ValidationError("INTAKE_V3_ACCOUNT_REF_NOT_MASKED")
    source_ids = _validate_sources(draft["source_items"])
    account = draft["account_snapshot"]
    for field in ACCOUNT_FIELDS:
        _validate_fact(
            account[field], path=f"account_snapshot.{field}", source_ids=source_ids,
            numeric=field not in {"account_type", "base_currency", "as_of"},
            allowed={"CASH", "MARGIN", "UNKNOWN"} if field == "account_type" else None,
        )
    if account["base_currency"].get("value") not in {None, "USD"}:
        raise IntakeV3ValidationError("INTAKE_V3_CURRENCY_UNSUPPORTED")
    if account["as_of"].get("value") is not None:
        _datetime(account["as_of"]["value"], "account_snapshot.as_of.value")
    for index, broker_field in enumerate(account["broker_reported_fields"]):
        if any(ref not in source_ids for ref in broker_field["source_refs"]):
            raise IntakeV3ValidationError(f"INTAKE_V3_SOURCE_REF_DANGLING:broker_reported_fields[{index}]")
    row_ids: list[str] = []
    row_position_ids: list[str] = []
    for row in draft["rows"]:
        row_ids.append(row["row_id"])
        if any(ref not in source_ids for ref in row["source_refs"]):
            raise IntakeV3ValidationError(f"INTAKE_V3_SOURCE_REF_DANGLING:rows.{row['row_id']}")
        if row["row_type"] == "POSITION":
            if not row["position_id"]:
                raise IntakeV3ValidationError("INTAKE_V3_POSITION_ROW_LINK_REQUIRED")
            row_position_ids.append(row["position_id"])
        elif row["position_id"] is not None:
            raise IntakeV3ValidationError("INTAKE_V3_NON_POSITION_ROW_LINK_FORBIDDEN")
    if len(row_ids) != len(set(row_ids)):
        raise IntakeV3ValidationError("INTAKE_V3_ROW_ID_DUPLICATE")
    for index, reported in enumerate(draft["reported_totals"]):
        if reported["row_id"] not in row_ids:
            raise IntakeV3ValidationError(f"INTAKE_V3_REPORTED_TOTAL_ROW_DANGLING:{index}")
        if any(ref not in source_ids for ref in reported["source_refs"]):
            raise IntakeV3ValidationError(f"INTAKE_V3_SOURCE_REF_DANGLING:reported_totals[{index}]")
    position_ids: list[str] = []
    security_ids: list[str] = []
    for index, position in enumerate(draft["positions"]):
        position_ids.append(position["position_id"])
        identity = position["identity"]
        for field in ("display_symbol", "display_name", "market", "asset_type"):
            _validate_fact(identity[field], path=f"positions[{index}].identity.{field}", source_ids=source_ids)
        if identity["identity_status"] not in IDENTITY_STATUSES:
            raise IntakeV3ValidationError("INTAKE_V3_IDENTITY_STATUS_INVALID")
        if identity["identity_status"] == "AMBIGUOUS" and len(identity["candidates"]) < 2:
            raise IntakeV3ValidationError("INTAKE_V3_IDENTITY_CANDIDATES_REQUIRED")
        symbol = identity["display_symbol"].get("value")
        if symbol is not None and TICKER_RE.fullmatch(symbol) is None:
            raise IntakeV3ValidationError(f"INTAKE_V3_SYMBOL_INVALID:{symbol}")
        if identity["market"].get("value") not in {None, "US"}:
            raise IntakeV3ValidationError("INTAKE_V3_MARKET_UNSUPPORTED")
        asset = identity["asset_type"].get("value")
        if asset not in ASSET_TYPES | {None}:
            raise IntakeV3ValidationError("INTAKE_V3_ASSET_UNSUPPORTED")
        for field in POSITION_FACT_FIELDS:
            _validate_fact(
                position[field], path=f"positions[{index}].{field}", source_ids=source_ids,
                numeric=field not in {"quantity_unit", "quote_unit", "currency"},
            )
        quantity = position["quantity"].get("value")
        if quantity is not None and _number(quantity, "quantity") == 0:
            raise IntakeV3ValidationError("INTAKE_V3_QUANTITY_ZERO")
        quantity_unit = position["quantity_unit"].get("value")
        expected_unit = "CONTRACT" if asset == "OPTION" else "SHARE"
        if quantity_unit is not None and quantity_unit != expected_unit:
            raise IntakeV3ValidationError("INTAKE_V3_QUANTITY_UNIT_INVALID")
        quote_unit = position["quote_unit"].get("value")
        expected_quote_unit = "PER_UNDERLYING_UNIT" if asset == "OPTION" else "PER_SHARE"
        if quote_unit is not None and quote_unit != expected_quote_unit:
            raise IntakeV3ValidationError("INTAKE_V3_QUOTE_UNIT_INVALID")
        for field in ("average_cost_price", "quote_price"):
            value = position[field].get("value")
            if value is not None and _number(value, field) < 0:
                raise IntakeV3ValidationError(f"INTAKE_V3_NEGATIVE_PRICE:{field}")
        market_value = position["market_value"].get("value")
        if quantity is not None and market_value is not None and quantity * market_value < 0:
            raise IntakeV3ValidationError("INTAKE_V3_MARKET_VALUE_SIGN_MISMATCH")
        option = position.get("option_contract")
        if asset == "OPTION":
            if not isinstance(option, Mapping):
                raise IntakeV3ValidationError("INTAKE_V3_OPTION_CONTRACT_REQUIRED")
            for field in OPTION_FIELDS:
                _validate_fact(
                    option[field], path=f"positions[{index}].option_contract.{field}", source_ids=source_ids,
                    numeric=field in {"strike", "contract_multiplier"},
                )
            if option["option_type"].get("value") not in {None, "CALL", "PUT"}:
                raise IntakeV3ValidationError("INTAKE_V3_OPTION_TYPE_INVALID")
            expiration = option["expiration_date"].get("value")
            if expiration is not None:
                try:
                    date.fromisoformat(expiration)
                except (TypeError, ValueError) as exc:
                    raise IntakeV3ValidationError("INTAKE_V3_OPTION_EXPIRATION_INVALID") from exc
            strike = option["strike"].get("value")
            if strike is not None and _number(strike, "option.strike") <= 0:
                raise IntakeV3ValidationError("INTAKE_V3_OPTION_STRIKE_INVALID")
            multiplier = option["contract_multiplier"].get("value")
            if multiplier is not None and (
                _number(multiplier, "option.contract_multiplier") <= 0
                or not float(multiplier).is_integer()
            ):
                raise IntakeV3ValidationError("INTAKE_V3_OPTION_MULTIPLIER_INVALID")
            underlying = option["underlying_symbol"].get("value")
            if symbol is not None and underlying is not None and symbol != underlying:
                raise IntakeV3ValidationError("INTAKE_V3_OPTION_UNDERLYING_MISMATCH")
        elif option is not None:
            raise IntakeV3ValidationError("INTAKE_V3_OPTION_FOR_NON_OPTION")
        if identity["canonical_security_id"]:
            security_ids.append(identity["canonical_security_id"])
        elif asset == "OPTION" and isinstance(option, Mapping) and all(
            option[field].get("value") is not None for field in ("underlying_symbol", "expiration_date", "strike", "option_type")
        ):
            security_ids.append(
                f"US:OPTION:{option['underlying_symbol']['value']}:{option['expiration_date']['value']}:"
                f"{float(option['strike']['value']):g}:{option['option_type']['value']}"
            )
        elif asset and symbol:
            security_ids.append(f"US:{asset}:{symbol}")
    if len(position_ids) != len(set(position_ids)):
        raise IntakeV3ValidationError("INTAKE_V3_POSITION_ID_DUPLICATE")
    if sorted(row_position_ids) != sorted(position_ids):
        raise IntakeV3ValidationError("INTAKE_V3_ROW_POSITION_CLOSURE_INVALID")
    if len(security_ids) != len(set(security_ids)):
        raise IntakeV3ValidationError("INTAKE_V3_SECURITY_DUPLICATE")
    lineage_paths = _draft_lineage_paths(draft)
    derived_paths: list[str] = []
    for item in draft["derived_lineage"]:
        derived_paths.append(item["field_path"])
        if item["field_path"] not in lineage_paths:
            raise IntakeV3ValidationError(f"INTAKE_V3_DERIVED_FIELD_MISSING:{item['field_path']}")
        if any(parent not in lineage_paths for parent in item["parent_fields"]):
            raise IntakeV3ValidationError(f"INTAKE_V3_DERIVED_PARENT_MISSING:{item['field_path']}")
        if any(ref not in source_ids for ref in item["source_refs"]):
            raise IntakeV3ValidationError(f"INTAKE_V3_DERIVED_LINEAGE_DANGLING:{item['field_path']}")
    if len(derived_paths) != len(set(derived_paths)):
        raise IntakeV3ValidationError("INTAKE_V3_DERIVED_PATH_DUPLICATE")
    for item in draft["unsupported_assets"]:
        if any(ref not in source_ids for ref in item["source_refs"]):
            raise IntakeV3ValidationError("INTAKE_V3_SOURCE_REF_DANGLING:unsupported_assets")
    if draft["unresolved_fields"] != _required_unresolved(draft):
        raise IntakeV3ValidationError("INTAKE_V3_UNRESOLVED_FIELDS_MISMATCH")
    if draft["reconciliation"] != _reconcile(draft, draft["reconciliation"]["tolerance"]):
        raise IntakeV3ValidationError("INTAKE_V3_RECONCILIATION_INVALID")
    if draft["portfolio_scope"] == "BROKER_ACCOUNT" and draft["portfolio_complete"]:
        if not any(item["coverage_status"] == "COMPLETE" for item in draft["source_items"]):
            raise IntakeV3ValidationError("INTAKE_V3_BROKER_COVERAGE_NOT_COMPLETE")


def apply_corrections(
    draft: Mapping[str, Any], *, correction_source: Mapping[str, Any], corrections: list[Mapping[str, Any]]
) -> dict[str, Any]:
    """Apply explicit corrections to a v3 Draft and invalidate its old hash."""

    validate_draft(draft)
    updated = copy.deepcopy(dict(draft))
    source = copy.deepcopy(dict(correction_source))
    source_id = source.get("source_id")
    if not isinstance(source_id, str) or not source_id:
        raise IntakeV3ValidationError("INTAKE_V3_CORRECTION_SOURCE_INVALID")
    updated["source_items"].append(source)
    positions = {position["position_id"]: position for position in updated["positions"]}
    for correction in corrections:
        path = correction.get("path")
        if not isinstance(path, str):
            raise IntakeV3ValidationError("INTAKE_V3_CORRECTION_PATH_INVALID")
        if path == "portfolio_complete":
            if not isinstance(correction.get("value"), bool):
                raise IntakeV3ValidationError("INTAKE_V3_CORRECTION_VALUE_INVALID")
            updated["portfolio_complete"] = correction["value"]
            continue
        parts = path.split(".")
        target: dict[str, Any]
        if len(parts) == 2 and parts[0] == "account_snapshot" and parts[1] in ACCOUNT_FIELDS:
            target = updated["account_snapshot"][parts[1]]
        elif len(parts) >= 3 and parts[0] == "positions" and parts[1] in positions:
            position = positions[parts[1]]
            if len(parts) == 3 and parts[2] in POSITION_FACT_FIELDS:
                target = position[parts[2]]
            elif len(parts) == 4 and parts[2] == "identity" and parts[3] in {"display_symbol", "display_name", "market", "asset_type"}:
                target = position["identity"][parts[3]]
            elif len(parts) == 4 and parts[2] == "option_contract" and parts[3] in OPTION_FIELDS and isinstance(position.get("option_contract"), Mapping):
                target = position["option_contract"][parts[3]]
            else:
                raise IntakeV3ValidationError(f"INTAKE_V3_CORRECTION_PATH_INVALID:{path}")
        else:
            raise IntakeV3ValidationError(f"INTAKE_V3_CORRECTION_PATH_INVALID:{path}")
        value = correction.get("value")
        refs = [*target.get("source_refs", []), source_id] if value is not None else []
        target.update(_fact(value, "USER_SUPPLIED" if value is not None else "MISSING", refs, correction.get("note")))
    updated.pop("draft_hash", None)
    return build_draft(updated)


def _security_id(position: Mapping[str, Any]) -> str:
    identity = position["identity"]
    if identity.get("canonical_security_id"):
        return str(identity["canonical_security_id"])
    asset = identity["asset_type"]["value"]
    symbol = identity["display_symbol"]["value"]
    if asset == "OPTION":
        option = position["option_contract"]
        return (
            f"US:OPTION:{option['underlying_symbol']['value']}:{option['expiration_date']['value']}:"
            f"{float(option['strike']['value']):g}:{option['option_type']['value']}"
        )
    return f"US:{asset}:{symbol}"


def _field_lineage(draft: Mapping[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for field in ACCOUNT_FIELDS:
        fact = draft["account_snapshot"][field]
        if fact["value"] is not None:
            records.append({"field_path": f"account_snapshot.{field}", "source_refs": fact["source_refs"]})
    for position in draft["positions"]:
        prefix = f"portfolio.positions.{position['position_id']}"
        for field in ("display_symbol", "display_name", "market", "asset_type"):
            fact = position["identity"][field]
            if fact["value"] is not None:
                records.append({"field_path": f"{prefix}.{field}", "source_refs": fact["source_refs"]})
        for field in POSITION_FACT_FIELDS:
            fact = position[field]
            if fact["value"] is not None:
                records.append({"field_path": f"{prefix}.{field}", "source_refs": fact["source_refs"]})
        if isinstance(position.get("option_contract"), Mapping):
            for field in OPTION_FIELDS:
                fact = position["option_contract"][field]
                if fact["value"] is not None:
                    records.append({"field_path": f"{prefix}.option_contract.{field}", "source_refs": fact["source_refs"]})
    return records


def build_handoff(draft: Mapping[str, Any], *, confirmed: bool, confirmed_at: str) -> dict[str, Any]:
    """Create neutral account-state Handoff v3 after explicit confirmation."""

    validate_draft(draft)
    if confirmed is not True:
        raise IntakeV3ValidationError("INTAKE_V3_EXPLICIT_CONFIRMATION_REQUIRED")
    if draft["unresolved_fields"] or not draft["portfolio_complete"]:
        raise IntakeV3ValidationError("INTAKE_V3_DRAFT_NOT_CONFIRMABLE")
    confirmed_time = _datetime(confirmed_at, "confirmed_at")
    account_as_of = _datetime(draft["account_snapshot"]["as_of"]["value"], "account_snapshot.as_of")
    if confirmed_time < account_as_of:
        raise IntakeV3ValidationError("INTAKE_V3_CONFIRMATION_TIME_INVALID")
    positions: list[dict[str, Any]] = []
    for source in draft["positions"]:
        identity = source["identity"]
        asset = identity["asset_type"]["value"]
        option = None
        if asset == "OPTION":
            option = {field: source["option_contract"][field]["value"] for field in OPTION_FIELDS}
            option["contract_multiplier"] = int(option["contract_multiplier"])
        refs: list[str] = []
        for fact in list(identity[field] for field in ("display_symbol", "display_name", "market", "asset_type")) + list(source[field] for field in POSITION_FACT_FIELDS):
            refs.extend(fact["source_refs"])
        if isinstance(source.get("option_contract"), Mapping):
            for field in OPTION_FIELDS:
                refs.extend(source["option_contract"][field]["source_refs"])
        positions.append({
            "position_id": source["position_id"], "security_id": _security_id(source),
            "display_symbol": identity["display_symbol"]["value"], "display_name": identity["display_name"]["value"],
            "market": identity["market"]["value"], "asset_type": asset,
            "identity_status": "USER_CONFIRMED" if identity["identity_status"] == "OBSERVED" else identity["identity_status"],
            "canonical_security_id": identity["canonical_security_id"],
            **{field: source[field]["value"] for field in POSITION_FACT_FIELDS},
            "option_contract": option, "source_refs": list(dict.fromkeys(refs)),
        })
    positions.sort(key=lambda item: item["security_id"])
    account_unknown = [
        field for field in ACCOUNT_FIELDS
        if field not in {"account_type", "base_currency", "as_of", "cash_balance"}
        and draft["account_snapshot"][field]["value"] is None
    ]
    account = {
        field: draft["account_snapshot"][field]["value"] for field in ACCOUNT_FIELDS
    }
    account.update({
        "account_ref": draft["account_ref"],
        "broker_reported_fields": copy.deepcopy(draft["account_snapshot"]["broker_reported_fields"]),
        "unknown_fields": account_unknown,
    })
    portfolio = {
        "as_of": account["as_of"], "base_currency": account["base_currency"], "positions": positions,
    }
    handoff: dict[str, Any] = {
        "schema_version": HANDOFF_SCHEMA_VERSION, "handoff_id": f"handoff-{draft['draft_id']}",
        "draft_id": draft["draft_id"], "draft_hash": draft["draft_hash"], "advisory_only": True,
        "confirmation": {"confirmed": True, "confirmed_at": confirmed_at, "draft_hash": draft["draft_hash"]},
        "portfolio_scope": draft["portfolio_scope"], "source_items": copy.deepcopy(draft["source_items"]),
        "account_snapshot": account, "portfolio": portfolio,
        "reported_totals": copy.deepcopy(draft["reported_totals"]),
        "reconciliation": copy.deepcopy(draft["reconciliation"]),
        "field_lineage": _field_lineage(draft),
        "derived_lineage": copy.deepcopy(draft.get("derived_lineage", [])),
        "unknown_fields": [
            *[f"account_snapshot.{field}" for field in account_unknown],
            *[
                f"portfolio.positions.{position['position_id']}.{field}"
                for position in positions
                for field in ("available_quantity", "average_cost_price", "quote_price", "quote_unit", "market_value", "unrealized_pnl_amount", "unrealized_pnl_percent")
                if position[field] is None
            ],
        ],
        "portfolio_hash": canonical_hash(portfolio),
    }
    handoff["handoff_hash"] = canonical_hash(_without_hash(handoff, "handoff_hash"))
    validate_handoff(handoff, source_draft=draft)
    return handoff


def validate_handoff(handoff: Mapping[str, Any], *, source_draft: Mapping[str, Any] | None = None) -> None:
    for key in FORBIDDEN_HANDOFF_FIELDS:
        if key in handoff or key in handoff.get("portfolio", {}):
            raise IntakeV3ValidationError(f"INTAKE_V3_HANDOFF_TASK_FIELD_FORBIDDEN:{key}")
    try:
        validate_schema_instance(handoff, _schema("portfolio-handoff-v3.schema.json"))
    except SchemaValidationError as exc:
        raise IntakeV3ValidationError(f"INTAKE_V3_HANDOFF_SCHEMA_INVALID:{exc}") from exc
    if handoff["handoff_hash"] != canonical_hash(_without_hash(handoff, "handoff_hash")):
        raise IntakeV3ValidationError("INTAKE_V3_HANDOFF_HASH_MISMATCH")
    if handoff["portfolio_hash"] != canonical_hash(handoff["portfolio"]):
        raise IntakeV3ValidationError("INTAKE_V3_PORTFOLIO_HASH_MISMATCH")
    if handoff["confirmation"]["draft_hash"] != handoff["draft_hash"]:
        raise IntakeV3ValidationError("INTAKE_V3_CONFIRMATION_DRAFT_MISMATCH")
    source_ids = _validate_sources(handoff["source_items"])
    if any(item["identity_status"] == "AMBIGUOUS" for item in handoff["portfolio"]["positions"]):
        raise IntakeV3ValidationError("INTAKE_V3_HANDOFF_IDENTITY_AMBIGUOUS")
    security_ids = [item["security_id"] for item in handoff["portfolio"]["positions"]]
    if len(security_ids) != len(set(security_ids)):
        raise IntakeV3ValidationError("INTAKE_V3_HANDOFF_SECURITY_DUPLICATE")
    lineage_paths: list[str] = []
    for lineage in handoff["field_lineage"]:
        lineage_paths.append(lineage["field_path"])
        if any(ref not in source_ids for ref in lineage["source_refs"]):
            raise IntakeV3ValidationError(f"INTAKE_V3_LINEAGE_DANGLING:{lineage['field_path']}")
    if len(lineage_paths) != len(set(lineage_paths)):
        raise IntakeV3ValidationError("INTAKE_V3_LINEAGE_PATH_DUPLICATE")
    for derived in handoff["derived_lineage"]:
        if any(ref not in source_ids for ref in derived["source_refs"]):
            raise IntakeV3ValidationError(f"INTAKE_V3_DERIVED_LINEAGE_DANGLING:{derived['field_path']}")
        if any(parent not in lineage_paths for parent in derived["parent_fields"]):
            raise IntakeV3ValidationError(f"INTAKE_V3_DERIVED_PARENT_MISSING:{derived['field_path']}")
    required_paths = {
        "account_snapshot.base_currency", "account_snapshot.as_of", "account_snapshot.cash_balance"
    }
    for position in handoff["portfolio"]["positions"]:
        prefix = f"portfolio.positions.{position['position_id']}"
        required_paths.update({
            f"{prefix}.display_symbol", f"{prefix}.market", f"{prefix}.asset_type",
            f"{prefix}.quantity", f"{prefix}.quantity_unit", f"{prefix}.currency",
        })
        if position["asset_type"] == "OPTION":
            required_paths.update(
                f"{prefix}.option_contract.{field}"
                for field in ("underlying_symbol", "option_type", "expiration_date", "strike", "contract_multiplier", "adjustment_status")
            )
    if not required_paths.issubset(set(lineage_paths)):
        missing = sorted(required_paths - set(lineage_paths))
        raise IntakeV3ValidationError(f"INTAKE_V3_LINEAGE_INCOMPLETE:{missing}")
    if source_draft is not None:
        validate_draft(source_draft)
        if handoff["draft_id"] != source_draft["draft_id"] or handoff["draft_hash"] != source_draft["draft_hash"]:
            raise IntakeV3ValidationError("INTAKE_V3_HANDOFF_STALE_DRAFT")
        if len(handoff["portfolio"]["positions"]) != len(source_draft["positions"]):
            raise IntakeV3ValidationError("INTAKE_V3_HANDOFF_POSITION_COUNT_MISMATCH")


def render_draft_summary(draft: Mapping[str, Any]) -> str:
    validate_draft(draft)
    account = draft["account_snapshot"]
    value = lambda field: account[field]["value"] if account[field]["value"] is not None else "未知"
    lines = [
        "# 持仓草稿 v3（尚未确认）", "",
        f"- 范围：{draft['portfolio_scope']}",
        f"- 组合是否完整：{'是' if draft['portfolio_complete'] else '否'}",
        f"- 截止时间：{value('as_of')}", f"- 基础币种：{value('base_currency')}",
        f"- 账户净值：{value('net_liquidation_value')}", f"- 证券市值：{value('securities_value')}",
        f"- 现金余额：{value('cash_balance')}", f"- 可用资金：{value('available_funds')}",
        f"- 购买力：{value('buying_power')}", f"- 保证金占用：{value('margin_used')}",
        f"- 勾稽状态：{draft['reconciliation']['status']}",
        f"- 全部持仓数量：{len(draft['positions'])}（无上限、不截断）", "",
        "| 类型 | 标的 | 数量 | 单位 | 报价 | 市值 | 身份状态 |",
        "|---|---|---:|---|---:|---:|---|",
    ]
    for position in draft["positions"]:
        identity = position["identity"]
        lines.append(
            f"| {identity['asset_type']['value']} | {identity['display_symbol']['value']} | "
            f"{position['quantity']['value']} | {position['quantity_unit']['value']} | "
            f"{position['quote_price']['value'] if position['quote_price']['value'] is not None else '未知'} | "
            f"{position['market_value']['value'] if position['market_value']['value'] is not None else '未知'} | "
            f"{identity['identity_status']} |"
        )
    lines.extend(["", "## 需要集中补充或确认的项目", ""])
    if draft["unresolved_fields"]:
        lines.extend(f"- {item}" for item in draft["unresolved_fields"])
    else:
        lines.append("- 无。请明确确认当前 draft_hash；普通“继续”不视为确认。")
    lines.extend(["", "确认只生成中立 PortfolioHandoff；研究问题由独立 CouncilRequest 提供。", ""])
    return "\n".join(lines)
