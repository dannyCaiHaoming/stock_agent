"""Deterministic PortfolioDraft and PortfolioHandoff processing.

Image interpretation remains a Codex Skill responsibility.  This module only
normalizes structured observations, validates explicit confirmation, computes
hashes, and creates the all-position handoff consumed by Portfolio Council.
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
DRAFT_SCHEMA_VERSION = "portfolio-draft/2.0.0"
HANDOFF_SCHEMA_VERSION = "portfolio-handoff/2.0.0"
RESEARCH_SCOPE = "ALL_INPUT_POSITIONS"
RESOLVED_STATUSES = {"EXTRACTED", "USER_SUPPLIED"}
UNRESOLVED_STATUSES = {"MISSING", "AMBIGUOUS", "CONFLICTING"}
SUPPORTED_MARKETS = {"US"}
SUPPORTED_ASSET_TYPES = {"COMMON_STOCK", "ETF", "OPTION"}
REQUIRED_OPTION_FIELDS = (
    "underlying_ticker",
    "option_type",
    "expiration_date",
    "strike",
    "contract_multiplier",
)
OPTION_FIELDS = (*REQUIRED_OPTION_FIELDS, "contract_symbol")
CAPABILITY_BY_ASSET_TYPE = {
    "COMMON_STOCK": "company-research",
    "ETF": "etf-research",
    "OPTION": "options-research",
}
AVAILABLE_RESEARCH_CAPABILITIES = {"company-research"}
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,15}$")


class IntakeValidationError(ValueError):
    """Fail-closed intake contract violation."""


def _load_schema(name: str) -> dict[str, Any]:
    return json.loads((SCHEMA_ROOT / name).read_text(encoding="utf-8"))


def _without_hash(value: Mapping[str, Any], key: str) -> dict[str, Any]:
    copy_value = copy.deepcopy(dict(value))
    copy_value.pop(key, None)
    return copy_value


def _parse_datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise IntakeValidationError(f"INTAKE_DATETIME_REQUIRED:{field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise IntakeValidationError(f"INTAKE_DATETIME_INVALID:{field}") from exc
    if parsed.tzinfo is None:
        raise IntakeValidationError(f"INTAKE_DATETIME_TIMEZONE_REQUIRED:{field}")
    return parsed


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise IntakeValidationError(f"INTAKE_NUMBER_INVALID:{field}")
    return float(value)


def _validate_field(
    field_value: Any,
    *,
    field: str,
    source_ids: set[str],
    optional: bool = False,
    numeric: bool = False,
) -> None:
    if not isinstance(field_value, Mapping):
        raise IntakeValidationError(f"INTAKE_FIELD_INVALID:{field}")
    status = field_value.get("status")
    value = field_value.get("value")
    refs = field_value.get("source_refs")
    candidates = field_value.get("candidates")
    if status not in RESOLVED_STATUSES | UNRESOLVED_STATUSES:
        raise IntakeValidationError(f"INTAKE_FIELD_STATUS_INVALID:{field}")
    if not isinstance(refs, list) or len(refs) != len(set(refs)):
        raise IntakeValidationError(f"INTAKE_SOURCE_REFS_INVALID:{field}")
    if any(ref not in source_ids for ref in refs):
        raise IntakeValidationError(f"INTAKE_SOURCE_REF_DANGLING:{field}")
    if not isinstance(candidates, list):
        raise IntakeValidationError(f"INTAKE_CANDIDATES_INVALID:{field}")
    if status in RESOLVED_STATUSES:
        if value is None or not refs or candidates:
            raise IntakeValidationError(f"INTAKE_RESOLVED_FIELD_INVALID:{field}")
    elif status == "MISSING":
        if value is not None or candidates:
            raise IntakeValidationError(f"INTAKE_MISSING_FIELD_INVALID:{field}")
    else:
        if value is not None or len(candidates) < 2 or not refs:
            raise IntakeValidationError(f"INTAKE_UNCERTAIN_FIELD_INVALID:{field}")
    if optional and status == "MISSING":
        return
    values = ([value] if value is not None else []) + list(candidates)
    if numeric:
        for index, item in enumerate(values):
            _finite_number(item, f"{field}.candidate[{index}]")


def _validate_account_ref(value: Any) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value.strip():
        raise IntakeValidationError("INTAKE_ACCOUNT_REF_INVALID")
    digits = re.sub(r"\D", "", value)
    if len(digits) > 4 and "*" not in value:
        raise IntakeValidationError("INTAKE_ACCOUNT_REF_NOT_MASKED")


def _validate_sources(source_items: Any) -> set[str]:
    if not isinstance(source_items, list) or not source_items:
        raise IntakeValidationError("INTAKE_SOURCE_ITEMS_REQUIRED")
    ids: list[str] = []
    for index, item in enumerate(source_items):
        if not isinstance(item, Mapping):
            raise IntakeValidationError(f"INTAKE_SOURCE_INVALID:{index}")
        source_id = item.get("source_id")
        if not isinstance(source_id, str) or not source_id:
            raise IntakeValidationError(f"INTAKE_SOURCE_ID_INVALID:{index}")
        ids.append(source_id)
        as_of = _parse_datetime(item.get("as_of"), f"source_items[{index}].as_of")
        retrieved_at = _parse_datetime(
            item.get("retrieved_at"), f"source_items[{index}].retrieved_at"
        )
        if as_of > retrieved_at:
            raise IntakeValidationError(f"INTAKE_SOURCE_TIME_INVALID:{source_id}")
        external_ref = item.get("external_ref")
        synthetic = item.get("synthetic")
        if not isinstance(synthetic, bool):
            raise IntakeValidationError(f"INTAKE_SOURCE_SYNTHETIC_INVALID:{source_id}")
        if external_ref is not None:
            if not isinstance(external_ref, str) or not external_ref:
                raise IntakeValidationError(f"INTAKE_EXTERNAL_REF_INVALID:{source_id}")
            path = Path(external_ref).expanduser()
            path = (REPO_ROOT / path).resolve() if not path.is_absolute() else path.resolve()
            if not path.is_file():
                raise IntakeValidationError(f"INTAKE_EXTERNAL_REF_MISSING:{source_id}")
            if item.get("content_hash") != file_hash(path):
                raise IntakeValidationError(f"INTAKE_SOURCE_HASH_MISMATCH:{source_id}")
            if item.get("source_type") == "SCREENSHOT" and not synthetic:
                try:
                    path.relative_to(REPO_ROOT)
                except ValueError:
                    pass
                else:
                    raise IntakeValidationError("INTAKE_PRIVATE_SOURCE_INSIDE_REPO")
    if len(ids) != len(set(ids)):
        raise IntakeValidationError("INTAKE_SOURCE_ID_DUPLICATE")
    return set(ids)


def _field(value: Any, status: str, source_refs: list[str], *, note: str | None = None) -> dict[str, Any]:
    return {
        "value": value,
        "status": status,
        "source_refs": list(dict.fromkeys(source_refs)),
        "candidates": [],
        "note": note,
    }


def _required_unresolved(draft: Mapping[str, Any]) -> list[str]:
    unresolved: list[str] = []
    for name in ("portfolio_as_of", "base_currency", "cash"):
        if draft[name]["status"] in UNRESOLVED_STATUSES:
            unresolved.append(name)
    positions = draft.get("positions", [])
    if not positions:
        unresolved.append("positions")
    for index, position in enumerate(positions):
        for name in ("ticker", "market", "asset_type", "quantity"):
            if position[name]["status"] in UNRESOLVED_STATUSES:
                unresolved.append(f"positions[{index}].{name}")
        if position["asset_type"].get("value") == "OPTION":
            option_contract = position.get("option_contract")
            if not isinstance(option_contract, Mapping):
                unresolved.append(f"positions[{index}].option_contract")
            else:
                for name in REQUIRED_OPTION_FIELDS:
                    field_value = option_contract.get(name)
                    if not isinstance(field_value, Mapping) or field_value.get("status") in UNRESOLVED_STATUSES:
                        unresolved.append(f"positions[{index}].option_contract.{name}")
    if draft.get("unsupported_assets"):
        unresolved.append("unsupported_assets")
    if not draft.get("portfolio_complete"):
        unresolved.append("portfolio_complete")
    return sorted(set(unresolved))


def build_draft(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Normalize a structured Skill observation and calculate its stable hash."""

    draft = copy.deepcopy(dict(payload))
    draft["schema_version"] = DRAFT_SCHEMA_VERSION
    draft.setdefault("account_ref", None)
    draft.setdefault("positions", [])
    draft.setdefault("unsupported_assets", [])
    draft.setdefault("unresolved_fields", [])
    for position in draft["positions"]:
        ticker = position.get("ticker", {})
        if isinstance(ticker, Mapping) and isinstance(ticker.get("value"), str):
            ticker["value"] = ticker["value"].strip().upper()
        market = position.get("market", {})
        if isinstance(market, Mapping) and isinstance(market.get("value"), str):
            market["value"] = market["value"].strip().upper()
        asset = position.get("asset_type", {})
        if isinstance(asset, Mapping) and isinstance(asset.get("value"), str):
            asset["value"] = asset["value"].strip().upper()
        position.setdefault("option_contract", None)
        option_contract = position.get("option_contract")
        if isinstance(option_contract, Mapping):
            for name in ("underlying_ticker", "option_type", "contract_symbol"):
                field_value = option_contract.get(name)
                if isinstance(field_value, Mapping) and isinstance(field_value.get("value"), str):
                    field_value["value"] = field_value["value"].strip().upper()
    draft["unresolved_fields"] = _required_unresolved(draft)
    draft["draft_hash"] = canonical_hash(_without_hash(draft, "draft_hash"))
    validate_draft(draft)
    return draft


def build_manual_draft(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Create a Draft from a concise user-supplied portfolio mapping."""

    draft_id = payload.get("draft_id")
    scope = payload.get("portfolio_scope")
    complete = payload.get("portfolio_complete")
    as_of = payload.get("as_of")
    retrieved_at = payload.get("retrieved_at")
    if not isinstance(draft_id, str) or not draft_id:
        raise IntakeValidationError("INTAKE_DRAFT_ID_REQUIRED")
    if scope not in {"BROKER_ACCOUNT", "USER_DEFINED_PORTFOLIO"}:
        raise IntakeValidationError("INTAKE_PORTFOLIO_SCOPE_INVALID")
    if not isinstance(complete, bool):
        raise IntakeValidationError("INTAKE_PORTFOLIO_COMPLETE_REQUIRED")
    _parse_datetime(as_of, "as_of")
    _parse_datetime(retrieved_at, "retrieved_at")
    source_id = payload.get("source_id", "source-manual")
    if not isinstance(source_id, str) or not source_id:
        raise IntakeValidationError("INTAKE_SOURCE_ID_INVALID")
    synthetic = payload.get("synthetic", False)
    if not isinstance(synthetic, bool):
        raise IntakeValidationError("INTAKE_SOURCE_SYNTHETIC_INVALID")
    positions_input = payload.get("positions")
    if not isinstance(positions_input, list):
        raise IntakeValidationError("INTAKE_POSITIONS_INVALID")
    positions: list[dict[str, Any]] = []
    for index, item in enumerate(positions_input):
        if not isinstance(item, Mapping):
            raise IntakeValidationError(f"INTAKE_POSITION_INVALID:{index}")
        asset_type_value = item.get("asset_type", "COMMON_STOCK")
        asset_type = (
            asset_type_value.strip().upper()
            if isinstance(asset_type_value, str)
            else asset_type_value
        )
        option_input = item.get("option_contract")
        option_contract = None
        if asset_type == "OPTION":
            if not isinstance(option_input, Mapping):
                option_input = {}
            option_contract = {
                name: (
                    _field(option_input.get(name), "USER_SUPPLIED", [source_id])
                    if option_input.get(name) is not None
                    else _field(None, "MISSING", [])
                )
                for name in OPTION_FIELDS
            }
        positions.append(
            {
                "position_id": item.get("position_id", f"position-{index + 1}"),
                "ticker": _field(item.get("ticker"), "USER_SUPPLIED", [source_id]),
                "market": _field(item.get("market", "US"), "USER_SUPPLIED", [source_id]),
                "asset_type": _field(asset_type, "USER_SUPPLIED", [source_id]),
                "quantity": _field(item.get("quantity"), "USER_SUPPLIED", [source_id]),
                "cost_basis": (
                    _field(item.get("cost_basis"), "USER_SUPPLIED", [source_id])
                    if item.get("cost_basis") is not None
                    else _field(None, "MISSING", [])
                ),
                "option_contract": option_contract,
            }
        )
    cash = payload.get("cash")
    base_currency = payload.get("base_currency")
    source = {
        "source_id": source_id,
        "source_type": "MANUAL",
        "as_of": as_of,
        "retrieved_at": retrieved_at,
        "content_hash": canonical_hash(dict(payload)),
        "external_ref": None,
        "synthetic": synthetic,
        "coverage_status": "COMPLETE" if complete else payload.get("coverage_status", "PARTIAL"),
    }
    return build_draft(
        {
            "draft_id": draft_id,
            "portfolio_scope": scope,
            "portfolio_complete": complete,
            "account_ref": payload.get("account_ref"),
            "source_items": [source],
            "portfolio_as_of": _field(as_of, "USER_SUPPLIED", [source_id]),
            "base_currency": (
                _field(base_currency, "USER_SUPPLIED", [source_id])
                if base_currency is not None
                else _field(None, "MISSING", [])
            ),
            "cash": (
                _field(cash, "USER_SUPPLIED", [source_id])
                if cash is not None
                else _field(None, "MISSING", [])
            ),
            "positions": positions,
            "unsupported_assets": copy.deepcopy(payload.get("unsupported_assets", [])),
        }
    )


def validate_draft(draft: Mapping[str, Any]) -> None:
    try:
        validate_schema_instance(draft, _load_schema("portfolio-draft.schema.json"))
    except SchemaValidationError as exc:
        raise IntakeValidationError(f"INTAKE_DRAFT_SCHEMA_INVALID:{exc}") from exc
    if draft.get("draft_hash") != canonical_hash(_without_hash(draft, "draft_hash")):
        raise IntakeValidationError("INTAKE_DRAFT_HASH_MISMATCH")
    _validate_account_ref(draft.get("account_ref"))
    source_ids = _validate_sources(draft.get("source_items"))
    _validate_field(draft["portfolio_as_of"], field="portfolio_as_of", source_ids=source_ids)
    _validate_field(draft["base_currency"], field="base_currency", source_ids=source_ids)
    _validate_field(draft["cash"], field="cash", source_ids=source_ids, numeric=True)
    if draft["cash"]["value"] is not None and _finite_number(draft["cash"]["value"], "cash") < 0:
        raise IntakeValidationError("INTAKE_CASH_NEGATIVE")
    if draft["base_currency"]["value"] not in (None, "USD"):
        raise IntakeValidationError("INTAKE_CURRENCY_UNSUPPORTED")
    if draft["portfolio_as_of"]["value"] is not None:
        _parse_datetime(draft["portfolio_as_of"]["value"], "portfolio_as_of.value")
    positions = draft.get("positions")
    if not isinstance(positions, list):
        raise IntakeValidationError("INTAKE_POSITIONS_INVALID")
    position_ids: list[str] = []
    resolved_identities: list[str] = []
    for index, position in enumerate(positions):
        position_ids.append(position["position_id"])
        for name in ("ticker", "market", "asset_type"):
            _validate_field(position[name], field=f"positions[{index}].{name}", source_ids=source_ids)
        for name in ("quantity", "cost_basis"):
            _validate_field(
                position[name],
                field=f"positions[{index}].{name}",
                source_ids=source_ids,
                optional=name == "cost_basis",
                numeric=True,
            )
        ticker = position["ticker"]["value"]
        if ticker is not None:
            if TICKER_RE.fullmatch(ticker) is None:
                raise IntakeValidationError(f"INTAKE_TICKER_INVALID:{ticker}")
        market = position["market"]["value"]
        if market is not None and market not in SUPPORTED_MARKETS:
            raise IntakeValidationError(f"INTAKE_MARKET_UNSUPPORTED:{market}")
        asset = position["asset_type"]["value"]
        if asset is not None and asset not in SUPPORTED_ASSET_TYPES:
            raise IntakeValidationError(f"INTAKE_ASSET_UNSUPPORTED:{asset}")
        quantity = position["quantity"]["value"]
        if quantity is not None and _finite_number(quantity, f"positions[{index}].quantity") == 0:
            raise IntakeValidationError("INTAKE_QUANTITY_ZERO")
        cost_basis = position["cost_basis"]["value"]
        if cost_basis is not None and _finite_number(cost_basis, f"positions[{index}].cost_basis") < 0:
            raise IntakeValidationError("INTAKE_COST_BASIS_NEGATIVE")
        option_contract = position.get("option_contract")
        if asset == "OPTION":
            if not isinstance(option_contract, Mapping):
                raise IntakeValidationError(f"INTAKE_OPTION_CONTRACT_REQUIRED:{index}")
            for name in OPTION_FIELDS:
                if name not in option_contract:
                    raise IntakeValidationError(f"INTAKE_OPTION_FIELD_REQUIRED:{name}")
                _validate_field(
                    option_contract[name],
                    field=f"positions[{index}].option_contract.{name}",
                    source_ids=source_ids,
                    optional=name == "contract_symbol",
                    numeric=name in {"strike", "contract_multiplier"},
                )
            option_type = option_contract["option_type"]["value"]
            if option_type is not None and option_type not in {"CALL", "PUT"}:
                raise IntakeValidationError("INTAKE_OPTION_TYPE_INVALID")
            expiration = option_contract["expiration_date"]["value"]
            if expiration is not None:
                try:
                    date.fromisoformat(expiration)
                except (TypeError, ValueError) as exc:
                    raise IntakeValidationError("INTAKE_OPTION_EXPIRATION_INVALID") from exc
            strike = option_contract["strike"]["value"]
            if strike is not None and _finite_number(strike, "option.strike") <= 0:
                raise IntakeValidationError("INTAKE_OPTION_STRIKE_INVALID")
            multiplier = option_contract["contract_multiplier"]["value"]
            if multiplier is not None:
                numeric_multiplier = _finite_number(multiplier, "option.contract_multiplier")
                if numeric_multiplier <= 0 or not numeric_multiplier.is_integer():
                    raise IntakeValidationError("INTAKE_OPTION_MULTIPLIER_INVALID")
            underlying = option_contract["underlying_ticker"]["value"]
            if ticker is not None and underlying is not None and ticker != underlying:
                raise IntakeValidationError("INTAKE_OPTION_UNDERLYING_MISMATCH")
            required_values = [option_contract[name]["value"] for name in REQUIRED_OPTION_FIELDS]
            if all(value is not None for value in required_values):
                resolved_identities.append(
                    f"OPTION:{underlying}:{expiration}:{float(strike):g}:{option_type}"
                )
        elif option_contract is not None:
            raise IntakeValidationError(f"INTAKE_OPTION_CONTRACT_FOR_NON_OPTION:{index}")
        elif asset is not None and ticker is not None:
            resolved_identities.append(f"{asset}:{ticker}")
    if len(position_ids) != len(set(position_ids)):
        raise IntakeValidationError("INTAKE_POSITION_ID_DUPLICATE")
    if len(resolved_identities) != len(set(resolved_identities)):
        raise IntakeValidationError("INTAKE_SECURITY_DUPLICATE")
    for index, asset in enumerate(draft.get("unsupported_assets", [])):
        if any(ref not in source_ids for ref in asset["source_refs"]):
            raise IntakeValidationError(f"INTAKE_SOURCE_REF_DANGLING:unsupported_assets[{index}]")
    expected = _required_unresolved(draft)
    if draft.get("unresolved_fields") != expected:
        raise IntakeValidationError("INTAKE_UNRESOLVED_FIELDS_MISMATCH")
    if draft["portfolio_scope"] == "BROKER_ACCOUNT" and draft["portfolio_complete"]:
        if not any(item["coverage_status"] == "COMPLETE" for item in draft["source_items"]):
            raise IntakeValidationError("INTAKE_BROKER_COVERAGE_NOT_COMPLETE")


def apply_corrections(
    draft: Mapping[str, Any],
    *,
    correction_source: Mapping[str, Any],
    corrections: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Apply explicit user corrections while retaining earlier provenance."""

    validate_draft(draft)
    updated = copy.deepcopy(dict(draft))
    source = copy.deepcopy(dict(correction_source))
    source_id = source.get("source_id")
    if not isinstance(source_id, str) or not source_id:
        raise IntakeValidationError("INTAKE_CORRECTION_SOURCE_ID_INVALID")
    updated["source_items"].append(source)
    by_id = {item["position_id"]: item for item in updated["positions"]}
    for correction in corrections:
        path = correction.get("path")
        if not isinstance(path, str):
            raise IntakeValidationError("INTAKE_CORRECTION_PATH_INVALID")
        if path == "portfolio_complete":
            if not isinstance(correction.get("value"), bool):
                raise IntakeValidationError("INTAKE_CORRECTION_VALUE_INVALID:portfolio_complete")
            updated["portfolio_complete"] = correction["value"]
            continue
        if path in {"portfolio_as_of", "base_currency", "cash"}:
            target = updated[path]
        elif path.startswith("positions."):
            parts = path.split(".")
            if len(parts) == 3 and parts[1] in by_id and parts[2] in {
                "ticker", "market", "asset_type", "quantity", "cost_basis"
            }:
                target = by_id[parts[1]][parts[2]]
            elif (
                len(parts) == 4
                and parts[1] in by_id
                and parts[2] == "option_contract"
                and parts[3] in OPTION_FIELDS
                and isinstance(by_id[parts[1]].get("option_contract"), Mapping)
            ):
                target = by_id[parts[1]]["option_contract"][parts[3]]
            else:
                raise IntakeValidationError(f"INTAKE_CORRECTION_PATH_INVALID:{path}")
        else:
            raise IntakeValidationError(f"INTAKE_CORRECTION_PATH_INVALID:{path}")
        value = correction.get("value")
        status = "MISSING" if value is None else "USER_SUPPLIED"
        target.update(_field(value, status, [*target.get("source_refs", []), source_id], note=correction.get("note")))
    updated.pop("draft_hash", None)
    return build_draft(updated)


def _assert_confirmable(draft: Mapping[str, Any]) -> None:
    validate_draft(draft)
    if draft["unresolved_fields"]:
        raise IntakeValidationError("INTAKE_DRAFT_NOT_CONFIRMABLE")
    if not draft["portfolio_complete"]:
        raise IntakeValidationError("INTAKE_PORTFOLIO_INCOMPLETE")


def build_handoff(
    draft: Mapping[str, Any],
    *,
    confirmed: bool,
    confirmed_at: str,
    holding_horizon: str,
    research_question: str,
    benchmark_id: str,
    mandate_artifact_id: str,
    batch_size: int = 5,
) -> dict[str, Any]:
    """Create a one-time, all-position handoff after explicit confirmation."""

    _assert_confirmable(draft)
    if confirmed is not True:
        raise IntakeValidationError("INTAKE_EXPLICIT_CONFIRMATION_REQUIRED")
    _parse_datetime(confirmed_at, "confirmed_at")
    for field, value in (
        ("holding_horizon", holding_horizon),
        ("research_question", research_question),
        ("benchmark_id", benchmark_id),
        ("mandate_artifact_id", mandate_artifact_id),
    ):
        if not isinstance(value, str) or not value.strip():
            raise IntakeValidationError(f"INTAKE_TEXT_REQUIRED:{field}")
    if isinstance(batch_size, bool) or not isinstance(batch_size, int) or batch_size < 1:
        raise IntakeValidationError("INTAKE_BATCH_SIZE_INVALID")
    positions: list[dict[str, Any]] = []
    for position in draft["positions"]:
        ticker = position["ticker"]["value"]
        asset_type = position["asset_type"]["value"]
        option_contract = None
        if asset_type == "OPTION":
            option_contract = {
                name: position["option_contract"][name]["value"] for name in OPTION_FIELDS
            }
            option_contract["contract_multiplier"] = int(option_contract["contract_multiplier"])
            security_id = (
                f"US:OPTION:{option_contract['underlying_ticker']}:"
                f"{option_contract['expiration_date']}:{float(option_contract['strike']):g}:"
                f"{option_contract['option_type']}"
            )
        else:
            security_id = f"US:{asset_type}:{ticker}"
        required_capability = CAPABILITY_BY_ASSET_TYPE[asset_type]
        refs: list[str] = []
        for name in ("ticker", "market", "asset_type", "quantity", "cost_basis"):
            refs.extend(position[name]["source_refs"])
        if option_contract is not None:
            for name in OPTION_FIELDS:
                refs.extend(position["option_contract"][name]["source_refs"])
        positions.append(
            {
                "security_id": security_id,
                "ticker": ticker,
                "market": position["market"]["value"],
                "asset_type": asset_type,
                "quantity": position["quantity"]["value"],
                "cost_basis": position["cost_basis"]["value"],
                "option_contract": option_contract,
                "required_capability": required_capability,
                "source_refs": list(dict.fromkeys(refs)),
            }
        )
    positions.sort(key=lambda item: item["security_id"])
    portfolio = {
        "as_of": draft["portfolio_as_of"]["value"],
        "base_currency": draft["base_currency"]["value"],
        "cash": draft["cash"]["value"],
        "positions": positions,
        "holding_horizon": holding_horizon.strip(),
        "research_question": research_question.strip(),
        "benchmark_id": benchmark_id.strip(),
        "mandate_artifact_id": mandate_artifact_id.strip(),
    }
    plan_items = [
        {
            "security_id": position["security_id"],
            "required_capability": position["required_capability"],
            "status": (
                "PENDING"
                if position["required_capability"] in AVAILABLE_RESEARCH_CAPABILITIES
                else "PENDING_CAPABILITY"
            ),
            "batch_index": index // batch_size + 1,
        }
        for index, position in enumerate(positions)
    ]
    capability_gaps = sorted(
        {
            item["required_capability"]
            for item in plan_items
            if item["required_capability"] not in AVAILABLE_RESEARCH_CAPABILITIES
        }
    )
    handoff: dict[str, Any] = {
        "schema_version": HANDOFF_SCHEMA_VERSION,
        "handoff_id": f"handoff-{draft['draft_id']}",
        "draft_id": draft["draft_id"],
        "draft_hash": draft["draft_hash"],
        "advisory_only": True,
        "confirmation": {
            "confirmed": True,
            "confirmed_at": confirmed_at,
            "draft_hash": draft["draft_hash"],
        },
        "portfolio_scope": draft["portfolio_scope"],
        "research_scope": RESEARCH_SCOPE,
        "council_readiness": "CAPABILITY_GAP" if capability_gaps else "READY",
        "capability_gaps": capability_gaps,
        "source_items": copy.deepcopy(draft["source_items"]),
        "portfolio": portfolio,
        "portfolio_hash": canonical_hash(portfolio),
        "research_plan": {
            "total": len(plan_items),
            "completed": 0,
            "pending": len(plan_items),
            "failed": 0,
            "batch_size": batch_size,
            "items": plan_items,
        },
    }
    handoff["handoff_hash"] = canonical_hash(_without_hash(handoff, "handoff_hash"))
    validate_handoff(handoff, source_draft=draft)
    return handoff


def validate_handoff(handoff: Mapping[str, Any], *, source_draft: Mapping[str, Any] | None = None) -> None:
    try:
        validate_schema_instance(handoff, _load_schema("portfolio-handoff.schema.json"))
    except SchemaValidationError as exc:
        raise IntakeValidationError(f"INTAKE_HANDOFF_SCHEMA_INVALID:{exc}") from exc
    if handoff.get("handoff_hash") != canonical_hash(_without_hash(handoff, "handoff_hash")):
        raise IntakeValidationError("INTAKE_HANDOFF_HASH_MISMATCH")
    if handoff["portfolio_hash"] != canonical_hash(handoff["portfolio"]):
        raise IntakeValidationError("INTAKE_PORTFOLIO_HASH_MISMATCH")
    if handoff["confirmation"]["draft_hash"] != handoff["draft_hash"]:
        raise IntakeValidationError("INTAKE_CONFIRMATION_DRAFT_MISMATCH")
    confirmed_at = _parse_datetime(handoff["confirmation"]["confirmed_at"], "confirmation.confirmed_at")
    portfolio_as_of = _parse_datetime(handoff["portfolio"]["as_of"], "portfolio.as_of")
    if confirmed_at < portfolio_as_of:
        raise IntakeValidationError("INTAKE_CONFIRMATION_TIME_INVALID")
    source_ids = _validate_sources(handoff["source_items"])
    positions = handoff["portfolio"]["positions"]
    security_ids = [item["security_id"] for item in positions]
    if len(security_ids) != len(set(security_ids)):
        raise IntakeValidationError("INTAKE_HANDOFF_SECURITY_DUPLICATE")
    for item in positions:
        quantity = _finite_number(item["quantity"], f"{item['security_id']}.quantity")
        if quantity == 0:
            raise IntakeValidationError("INTAKE_HANDOFF_QUANTITY_ZERO")
        if item["cost_basis"] is not None and _finite_number(
            item["cost_basis"], f"{item['security_id']}.cost_basis"
        ) < 0:
            raise IntakeValidationError("INTAKE_HANDOFF_COST_BASIS_NEGATIVE")
        asset_type = item["asset_type"]
        if item["required_capability"] != CAPABILITY_BY_ASSET_TYPE[asset_type]:
            raise IntakeValidationError("INTAKE_HANDOFF_CAPABILITY_INVALID")
        option_contract = item["option_contract"]
        if asset_type == "OPTION":
            if not isinstance(option_contract, Mapping):
                raise IntakeValidationError("INTAKE_HANDOFF_OPTION_CONTRACT_REQUIRED")
            if option_contract["underlying_ticker"] != item["ticker"]:
                raise IntakeValidationError("INTAKE_HANDOFF_OPTION_UNDERLYING_MISMATCH")
            if option_contract["option_type"] not in {"CALL", "PUT"}:
                raise IntakeValidationError("INTAKE_HANDOFF_OPTION_TYPE_INVALID")
            try:
                date.fromisoformat(option_contract["expiration_date"])
            except (TypeError, ValueError) as exc:
                raise IntakeValidationError("INTAKE_HANDOFF_OPTION_EXPIRATION_INVALID") from exc
            if _finite_number(option_contract["strike"], "option.strike") <= 0:
                raise IntakeValidationError("INTAKE_HANDOFF_OPTION_STRIKE_INVALID")
            multiplier = _finite_number(
                option_contract["contract_multiplier"], "option.contract_multiplier"
            )
            if multiplier <= 0 or not multiplier.is_integer():
                raise IntakeValidationError("INTAKE_HANDOFF_OPTION_MULTIPLIER_INVALID")
            expected_security_id = (
                f"US:OPTION:{option_contract['underlying_ticker']}:"
                f"{option_contract['expiration_date']}:{float(option_contract['strike']):g}:"
                f"{option_contract['option_type']}"
            )
        else:
            if option_contract is not None:
                raise IntakeValidationError("INTAKE_HANDOFF_OPTION_CONTRACT_FOR_NON_OPTION")
            expected_security_id = f"US:{asset_type}:{item['ticker']}"
        if item["security_id"] != expected_security_id:
            raise IntakeValidationError("INTAKE_HANDOFF_SECURITY_ID_INVALID")
        if any(ref not in source_ids for ref in item["source_refs"]):
            raise IntakeValidationError(f"INTAKE_SOURCE_REF_DANGLING:{item['security_id']}")
    _finite_number(handoff["portfolio"]["cash"], "portfolio.cash")
    plan = handoff["research_plan"]
    plan_ids = [item["security_id"] for item in plan["items"]]
    if len(plan_ids) != len(set(plan_ids)) or sorted(plan_ids) != sorted(security_ids):
        raise IntakeValidationError("INTAKE_RESEARCH_PLAN_COVERAGE_INVALID")
    position_by_id = {item["security_id"]: item for item in positions}
    for item in plan["items"]:
        position = position_by_id[item["security_id"]]
        expected_capability = position["required_capability"]
        expected_status = (
            "PENDING" if expected_capability in AVAILABLE_RESEARCH_CAPABILITIES else "PENDING_CAPABILITY"
        )
        if item["required_capability"] != expected_capability:
            raise IntakeValidationError("INTAKE_RESEARCH_PLAN_CAPABILITY_INVALID")
        if expected_capability not in AVAILABLE_RESEARCH_CAPABILITIES and item["status"] != expected_status:
            raise IntakeValidationError("INTAKE_RESEARCH_PLAN_READINESS_INVALID")
        if item["status"] in {"PENDING", "PENDING_CAPABILITY"} and item["status"] != expected_status:
            raise IntakeValidationError("INTAKE_RESEARCH_PLAN_READINESS_INVALID")
    expected_gaps = sorted(
        {
            item["required_capability"]
            for item in positions
            if item["required_capability"] not in AVAILABLE_RESEARCH_CAPABILITIES
        }
    )
    if handoff["capability_gaps"] != expected_gaps:
        raise IntakeValidationError("INTAKE_CAPABILITY_GAPS_INVALID")
    expected_readiness = "CAPABILITY_GAP" if expected_gaps else "READY"
    if handoff["council_readiness"] != expected_readiness:
        raise IntakeValidationError("INTAKE_COUNCIL_READINESS_INVALID")
    expected_batches = {
        security_id: index // plan["batch_size"] + 1
        for index, security_id in enumerate(security_ids)
    }
    if any(item["batch_index"] != expected_batches[item["security_id"]] for item in plan["items"]):
        raise IntakeValidationError("INTAKE_RESEARCH_PLAN_BATCH_INVALID")
    counts = {
        "completed": sum(item["status"] == "COMPLETED" for item in plan["items"]),
        "pending": sum(item["status"] in {"PENDING", "PENDING_CAPABILITY"} for item in plan["items"]),
        "failed": sum(item["status"] == "FAILED" for item in plan["items"]),
    }
    if plan["total"] != len(plan["items"]) or any(plan[key] != value for key, value in counts.items()):
        raise IntakeValidationError("INTAKE_RESEARCH_PLAN_COUNTS_INVALID")
    if source_draft is not None:
        validate_draft(source_draft)
        if handoff["draft_id"] != source_draft["draft_id"] or handoff["draft_hash"] != source_draft["draft_hash"]:
            raise IntakeValidationError("INTAKE_HANDOFF_STALE_DRAFT")
        if len(positions) != len(source_draft["positions"]):
            raise IntakeValidationError("INTAKE_HANDOFF_POSITION_COUNT_MISMATCH")


def build_risk_input(handoff: Mapping[str, Any]) -> dict[str, Any]:
    """Bind the deterministic Risk boundary to the complete confirmed portfolio."""

    validate_handoff(handoff)
    asset_types = sorted({item["asset_type"] for item in handoff["portfolio"]["positions"]})
    return {
        "schema_version": "portfolio-risk-input/2.0.0",
        "handoff_id": handoff["handoff_id"],
        "handoff_hash": handoff["handoff_hash"],
        "portfolio_hash": handoff["portfolio_hash"],
        "asset_types": asset_types,
        "risk_readiness": (
            "READY_FOR_EXISTING_POLICY"
            if set(asset_types) <= {"COMMON_STOCK"}
            else "REQUIRES_MULTI_ASSET_POLICY"
        ),
        "portfolio": copy.deepcopy(handoff["portfolio"]),
    }


def build_council_portfolio_input(handoff: Mapping[str, Any]) -> dict[str, Any]:
    """Preserve the complete multi-asset portfolio for Council capability routing."""

    validate_handoff(handoff)
    return {
        "schema_version": "portfolio-council-input/2.0.0",
        "source_handoff_id": handoff["handoff_id"],
        "source_handoff_hash": handoff["handoff_hash"],
        "portfolio_hash": handoff["portfolio_hash"],
        "council_readiness": handoff["council_readiness"],
        "capability_gaps": copy.deepcopy(handoff["capability_gaps"]),
        "portfolio": copy.deepcopy(handoff["portfolio"]),
        "research_plan": copy.deepcopy(handoff["research_plan"]),
    }


def render_draft_summary(draft: Mapping[str, Any]) -> str:
    """Render the review prompt without interpreting any investment meaning."""

    validate_draft(draft)
    lines = [
        "# 持仓草稿（尚未确认）",
        "",
        f"- 范围：{draft['portfolio_scope']}",
        f"- 组合是否完整：{'是' if draft['portfolio_complete'] else '否'}",
        f"- 截止时间：{draft['portfolio_as_of']['value'] or '待补充'}",
        f"- 基础币种：{draft['base_currency']['value'] or '待补充'}",
        f"- 现金：{draft['cash']['value'] if draft['cash']['value'] is not None else '待补充'}",
        f"- 已结构化持仓数量：{len(draft['positions'])}（股票、ETF、期权均完整保留）",
        f"- 未识别资产数量：{len(draft['unsupported_assets'])}（保留并阻止错误 Handoff）",
        f"- 输入项目总数：{len(draft['positions']) + len(draft['unsupported_assets'])}",
        "",
        "| 类型 | 标的/代码 | 市场 | 数量 | 成本（可选） | 状态 |",
        "|---|---|---|---:|---:|---|",
    ]
    for position in draft["positions"]:
        fields = [position[name]["status"] for name in ("ticker", "market", "asset_type", "quantity")]
        asset_type = position["asset_type"]["value"]
        label = position["ticker"]["value"] or "待补充"
        if asset_type == "OPTION" and isinstance(position.get("option_contract"), Mapping):
            option = position["option_contract"]
            fields.extend(option[name]["status"] for name in REQUIRED_OPTION_FIELDS)
            expiration = option["expiration_date"]["value"] or "到期日待补充"
            strike = option["strike"]["value"] if option["strike"]["value"] is not None else "行权价待补充"
            option_type = option["option_type"]["value"] or "类型待补充"
            label = f"{label} {expiration} {strike} {option_type}"
        status = "已识别" if all(item in RESOLVED_STATUSES for item in fields) else "需确认"
        lines.append(
            f"| {asset_type or '待补充'} | {label} | {position['market']['value'] or '待补充'} | "
            f"{position['quantity']['value'] if position['quantity']['value'] is not None else '待补充'} | "
            f"{position['cost_basis']['value'] if position['cost_basis']['value'] is not None else '未提供'} | {status} |"
        )
    if draft["unsupported_assets"]:
        lines.extend(["", "## 未识别资产（未丢弃）", ""])
        for item in draft["unsupported_assets"]:
            lines.append(f"- {item['label']}：{item['reason']}")
    lines.extend(["", "## 需要一次补充或确认的项目", ""])
    if draft["unresolved_fields"]:
        lines.extend(f"- {item}" for item in draft["unresolved_fields"])
    else:
        lines.append("- 无。请明确确认这份完整持仓草稿；普通“继续”不视为确认。")
    lines.extend(["", "确认仅生成 PortfolioHandoff，不会自动启动股票研究或交易。", ""])
    return "\n".join(lines)
