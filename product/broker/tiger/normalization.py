"""Allow-list normalization for Tiger SDK values.

No SDK object is serialized.  Only fields named in this module may cross into
the private ledger or a public boundary contract.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
import math
from typing import Any, Iterable, Mapping
from uuid import uuid4
from zoneinfo import ZoneInfo

from product.runtime.hashing import canonical_hash

from .contracts import finalize_contract


SOURCE_PREFIX = "tiger:tbhk"
SUPPORTED_ASSET_TYPES = frozenset({"COMMON_STOCK", "ETF", "LISTED_OPTION"})


class TigerNormalizationError(ValueError):
    """Stable normalization error without raw provider payloads."""


def value(item: object, *names: str, default: Any = None) -> Any:
    for name in names:
        if isinstance(item, Mapping) and name in item:
            return item[name]
        try:
            return getattr(item, name)
        except (AttributeError, KeyError):
            continue
    return default


def enum_text(item: Any) -> str | None:
    if item is None:
        return None
    candidate = getattr(item, "value", None)
    if candidate is None:
        candidate = getattr(item, "name", None)
    return str(candidate if candidate is not None else item)


def text(item: Any) -> str | None:
    result = enum_text(item)
    return result if result not in (None, "") else None


def number(item: Any) -> float | None:
    if item is None or isinstance(item, bool):
        return None
    try:
        result = float(item)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def rows(response: Any) -> list[Any]:
    if response is None:
        return []
    if isinstance(response, list):
        return response
    if isinstance(response, tuple):
        return list(response)
    if isinstance(response, Mapping):
        for key in ("result", "data", "items", "orders", "transactions", "history"):
            candidate = response.get(key)
            if isinstance(candidate, (list, tuple)):
                return list(candidate)
        return [response]
    to_dict = getattr(response, "to_dict", None)
    if callable(to_dict) and response.__class__.__module__.startswith("pandas"):
        converted = to_dict(orient="records")
        return list(converted) if isinstance(converted, list) else []
    for key in ("result", "data", "items", "orders", "transactions", "history"):
        candidate = getattr(response, key, None)
        if isinstance(candidate, (list, tuple)):
            return list(candidate)
    return [response]


def next_page_token(response: Any) -> str | None:
    for key in ("next_page_token", "next_token", "page_token"):
        candidate = value(response, key)
        if candidate not in (None, ""):
            return str(candidate)
    return None


def utc_timestamp(raw: Any) -> str | None:
    if raw in (None, ""):
        return None
    if isinstance(raw, datetime):
        parsed = raw
    elif isinstance(raw, date):
        parsed = datetime(raw.year, raw.month, raw.day, tzinfo=timezone.utc)
    elif isinstance(raw, (int, float)) and not isinstance(raw, bool):
        seconds = float(raw) / 1000 if abs(float(raw)) > 10_000_000_000 else float(raw)
        parsed = datetime.fromtimestamp(seconds, tz=timezone.utc)
    else:
        candidate = str(raw).strip().replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            for pattern in ("%Y-%m-%d %H:%M:%S", "%Y%m%d", "%Y-%m-%d"):
                try:
                    parsed = datetime.strptime(candidate, pattern)
                    break
                except ValueError:
                    continue
            else:
                return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def market_date(occurred_at_utc: str | None, market: str | None) -> str | None:
    if not occurred_at_utc:
        return None
    parsed = datetime.fromisoformat(occurred_at_utc.replace("Z", "+00:00"))
    zone = ZoneInfo("America/New_York") if market == "US" else ZoneInfo("Asia/Hong_Kong") if market == "HK" else timezone.utc
    return parsed.astimezone(zone).date().isoformat()


def _market(contract: object) -> str:
    observed = (text(value(contract, "market", "primary_exchange", "exchange")) or "").upper()
    currency = (text(value(contract, "currency")) or "").upper()
    if observed in {"US", "NASDAQ", "NYSE", "AMEX", "ARCA"} or currency == "USD":
        return "US"
    if observed in {"HK", "SEHK", "HKEX"} or currency == "HKD":
        return "HK"
    return observed or "UNKNOWN"


def contract_identity(contract: object) -> dict[str, Any]:
    symbol = text(value(contract, "symbol", "origin_symbol", "local_symbol")) or "UNKNOWN"
    currency = (text(value(contract, "currency")) or "UNKNOWN").upper()
    sec_type = (text(value(contract, "sec_type", "security_type")) or "UNKNOWN").upper()
    is_etf = value(contract, "is_etf") is True
    asset_type = "ETF" if sec_type == "STK" and is_etf else "COMMON_STOCK" if sec_type == "STK" else "LISTED_OPTION" if sec_type in {"OPT", "OPTION"} else sec_type
    provider_contract_id = text(value(contract, "contract_id", "identifier"))
    stable = {
        "provider_contract_id": provider_contract_id,
        "symbol": symbol,
        "market": _market(contract),
        "currency": currency,
        "asset_type": asset_type,
        "expiry": text(value(contract, "expiry")),
        "strike": number(value(contract, "strike")),
        "put_call": text(value(contract, "put_call", "right")),
        "multiplier": number(value(contract, "multiplier")),
    }
    stable["instrument_key"] = f"tiger:{canonical_hash(stable)}"
    return stable


def normalize_position(item: object, *, source_id: str, as_of: str, retrieved_at: str) -> dict[str, Any]:
    contract = value(item, "contract")
    if contract is None:
        raise TigerNormalizationError("TIGER_POSITION_CONTRACT_MISSING")
    identity = contract_identity(contract)
    supported = identity["market"] == "US" and identity["currency"] == "USD" and identity["asset_type"] in SUPPORTED_ASSET_TYPES
    option = None
    if identity["asset_type"] == "LISTED_OPTION":
        option = {
            "underlying_symbol": text(value(contract, "symbol", "origin_symbol")),
            "option_type": text(value(contract, "put_call", "right")),
            "expiration_date": text(value(contract, "expiry")),
            "strike": number(value(contract, "strike")),
            "multiplier": number(value(contract, "multiplier")),
            "raw_contract_symbol": text(value(contract, "local_symbol", "identifier")),
            "adjustment_status": "UNKNOWN",
        }
    record_basis = {
        "instrument_key": identity["instrument_key"],
        "quantity": number(value(item, "quantity", "position_qty")) or 0,
        "average_cost": number(value(item, "average_cost")),
        "market_price": number(value(item, "market_price")),
        "market_value": number(value(item, "market_value")),
        "as_of": as_of,
    }
    return {
        "position_id": f"position:{canonical_hash(record_basis)}",
        "instrument_key": identity["instrument_key"],
        "provider_contract_id": identity["provider_contract_id"],
        "display_symbol": identity["symbol"],
        "display_name": text(value(contract, "name")),
        "market": identity["market"],
        "currency": identity["currency"],
        "asset_type": identity["asset_type"],
        "identity_status": "OBSERVED" if identity["provider_contract_id"] else "AMBIGUOUS",
        "quantity": record_basis["quantity"],
        "available_quantity": number(value(item, "salable_qty", "saleable", "available_quantity")),
        "average_cost": record_basis["average_cost"],
        "market_price": record_basis["market_price"],
        "market_value": record_basis["market_value"],
        "unrealized_pnl": number(value(item, "unrealized_pnl", "unrealized_pl")),
        "option": option,
        "intake_status": "SUPPORTED_US_USD" if supported else "PENDING_FUTURE_RESEARCH" if identity["market"] != "UNKNOWN" else "UNCLASSIFIED",
        "source_id": source_id,
        "as_of": as_of,
        "retrieved_at": retrieved_at,
        "record_hash": canonical_hash(record_basis),
    }


def _account_values(assets: object, *, source_id: str, as_of: str, retrieved_at: str) -> list[dict[str, Any]]:
    segments = value(assets, "segments", "_segments", default={})
    if not isinstance(segments, Mapping):
        return []
    stock = segments.get("S") or segments.get("SEC")
    if stock is None:
        return []
    values: list[dict[str, Any]] = []
    currencies = value(stock, "currency_assets", "_currency_assets", default={})
    usd = currencies.get("USD") if isinstance(currencies, Mapping) else None
    for field in ("cash_balance", "cash_available_for_trade", "gross_position_value", "net_liquidation", "buying_power", "unrealized_pl", "realized_pl"):
        observed = number(value(usd, field)) if usd is not None else None
        scope = "US_USD_SEGMENT"
        if observed is None:
            observed = number(value(stock, field))
            scope = "WHOLE_ACCOUNT"
        if observed is not None:
            values.append({
                "field": field,
                "value": observed,
                "currency": "USD" if scope == "US_USD_SEGMENT" else text(value(stock, "currency")),
                "scope": scope,
                "source_id": source_id,
                "as_of": as_of,
                "retrieved_at": retrieved_at,
            })
    return values


def build_account_snapshot(adapter: object, *, account_ref: str, retrieved_at: str) -> dict[str, Any]:
    # Account discovery proves the configured account is readable; its identifiers are discarded.
    adapter.managed_accounts()
    assets = adapter.prime_assets(base_currency="USD", consolidated=True)
    raw_as_of = value(assets, "update_timestamp")
    as_of = utc_timestamp(raw_as_of) or retrieved_at
    source_id = f"{SOURCE_PREFIX}:account-snapshot"
    raw_positions: list[Any] = []
    for sec_type in ("STK", "OPT"):
        raw_positions.extend(rows(adapter.positions(sec_type=sec_type, currency="ALL", market="ALL")))
    positions = [normalize_position(item, source_id=source_id, as_of=as_of, retrieved_at=retrieved_at) for item in raw_positions]
    excluded = [
        {
            "position_id": item["position_id"],
            "display_symbol": item["display_symbol"],
            "market": item["market"],
            "currency": item["currency"],
            "asset_type": item["asset_type"],
            "reason": "UNSUPPORTED_FOR_PORTFOLIO_INTAKE",
            "status": "PENDING_FUTURE_RESEARCH",
        }
        for item in positions if item["intake_status"] != "SUPPORTED_US_USD"
    ]
    supported_count = sum(item["intake_status"] == "SUPPORTED_US_USD" for item in positions)
    limitations = []
    if excluded:
        limitations.append("非 US/USD 或当前不支持资产已保留在覆盖清单，投研接入待定。")
    if any(item["identity_status"] == "AMBIGUOUS" for item in positions):
        limitations.append("部分证券缺少稳定 provider contract id，需在 Intake 确认前核对身份。")
    return finalize_contract({
        "schema_version": "tiger-account-snapshot/1.0.0",
        "snapshot_id": f"tiger-snapshot:{uuid4().hex}",
        "account_ref": account_ref,
        "source_id": source_id,
        "as_of": as_of,
        "retrieved_at": retrieved_at,
        "license": "TBHK",
        "coverage_status": "COMPLETE",
        "account_scope": "MIXED_MARKET_ACCOUNT" if excluded else "BROKER_ACCOUNT",
        "account_values": _account_values(assets, source_id=source_id, as_of=as_of, retrieved_at=retrieved_at),
        "positions": positions,
        "coverage": {
            "visible_position_count": len(positions),
            "supported_position_count": supported_count,
            "excluded_position_count": len(excluded),
            "excluded_assets": excluded,
            "limitations": limitations,
        },
    })


def persist_snapshot(ledger: object, snapshot: Mapping[str, Any], *, batch_id: str) -> list[Any]:
    results = [ledger.append_activity({
        "activity_type": "ACCOUNT_SNAPSHOT",
        "account_ref": snapshot["account_ref"],
        "provider_id": snapshot["snapshot_id"],
        "source_id": snapshot["source_id"],
        "as_of": snapshot["as_of"],
        "retrieved_at": snapshot["retrieved_at"],
        "batch_id": batch_id,
        "coverage_status": snapshot["coverage_status"],
        "account_scope": snapshot["account_scope"],
        "account_values": snapshot["account_values"],
        "coverage": snapshot["coverage"],
        "snapshot_hash": snapshot["content_hash"],
    })]
    for position in snapshot["positions"]:
        results.append(ledger.append_activity({
            "activity_type": "POSITION",
            "account_ref": snapshot["account_ref"],
            # Positions are current-state revisions, not economic events. Keep a
            # stable ledger identity across snapshots; the snapshot batch still
            # binds each observed state to its full account view.
            "provider_id": f"current-position:{position['instrument_key']}",
            "source_id": position["source_id"],
            "as_of": position["as_of"],
            "retrieved_at": position["retrieved_at"],
            "batch_id": batch_id,
            "instrument_key": position["instrument_key"],
            "display_symbol": position["display_symbol"],
            "market": position["market"],
            "currency": position["currency"],
            "asset_type": position["asset_type"],
            "quantity": position["quantity"],
            "price": position["market_price"],
            "amount": position["market_value"],
            "position": position,
        }))
    return results


def _activity_base(
    item: object,
    *,
    activity_type: str,
    account_ref: str,
    source_id: str,
    retrieved_at: str,
    batch_id: str,
    time_names: tuple[str, ...],
    provider_names: tuple[str, ...],
) -> tuple[dict[str, Any], dict[str, Any]]:
    contract = value(item, "contract", default={})
    identity = contract_identity(contract)
    raw_time = value(item, *time_names)
    occurred = utc_timestamp(raw_time)
    provider_id = text(value(item, *provider_names))
    base = {
        "activity_type": activity_type,
        "account_ref": account_ref,
        "provider_id": provider_id,
        "source_id": source_id,
        "as_of": occurred or retrieved_at,
        "retrieved_at": retrieved_at,
        "batch_id": batch_id,
        "raw_time": text(raw_time),
        "raw_timezone": "PROVIDER_UNSPECIFIED",
        "occurred_at_utc": occurred,
        "market_date": market_date(occurred, identity["market"]),
        "instrument_key": identity["instrument_key"],
        "display_symbol": identity["symbol"],
        "market": identity["market"],
        "currency": identity["currency"],
        "asset_type": identity["asset_type"],
        "contract_multiplier": identity["multiplier"],
    }
    return base, identity


def normalize_order(item: object, *, account_ref: str, retrieved_at: str, batch_id: str) -> dict[str, Any]:
    base, _ = _activity_base(
        item, activity_type="ORDER", account_ref=account_ref,
        source_id=f"{SOURCE_PREFIX}:orders", retrieved_at=retrieved_at, batch_id=batch_id,
        time_names=("update_time", "trade_time", "order_time"), provider_names=("id", "order_id"),
    )
    order_id = text(value(item, "id", "order_id"))
    base.update({
        "order_id": order_id,
        "direction": (text(value(item, "action", "direction")) or "UNKNOWN").upper(),
        "status": (text(value(item, "status", "_status")) or "UNKNOWN").upper(),
        "quantity": number(value(item, "quantity")),
        "filled_quantity": number(value(item, "filled", "filled_quantity")) or 0,
        "remaining_quantity": number(value(item, "remaining")),
        "price": number(value(item, "avg_fill_price", "limit_price")),
        "amount": number(value(item, "filled_cash_amount", "total_cash_amount")),
        "order_type": text(value(item, "order_type")),
        "time_in_force": text(value(item, "time_in_force")),
        "outside_rth": value(item, "outside_rth"),
        "reported_realized_pnl": number(value(item, "realized_pnl")),
    })
    return base


def normalize_execution(item: object, *, account_ref: str, retrieved_at: str, batch_id: str, order_id: str | None = None) -> dict[str, Any]:
    base, _ = _activity_base(
        item, activity_type="EXECUTION", account_ref=account_ref,
        source_id=f"{SOURCE_PREFIX}:transactions", retrieved_at=retrieved_at, batch_id=batch_id,
        time_names=("trade_time", "timestamp", "time", "create_time"),
        provider_names=("transaction_id", "trade_id", "id", "execution_id"),
    )
    observed_order = text(value(item, "order_id", "orderId")) or order_id
    quantity = number(value(item, "quantity", "filled", "trade_quantity"))
    price = number(value(item, "price", "trade_price", "avg_fill_price"))
    base.update({
        "order_id": observed_order,
        "direction": (text(value(item, "action", "direction")) or "UNKNOWN").upper(),
        "status": "FILLED",
        "quantity": quantity,
        "price": price,
        "amount": number(value(item, "amount", "trade_amount")) if number(value(item, "amount", "trade_amount")) is not None else (quantity * price if quantity is not None and price is not None else None),
        "reported_realized_pnl": number(value(item, "realized_pnl")),
    })
    return base


def normalize_charges(order: object, *, account_ref: str, retrieved_at: str, batch_id: str) -> list[dict[str, Any]]:
    order_record = normalize_order(order, account_ref=account_ref, retrieved_at=retrieved_at, batch_id=batch_id)
    charge_container = value(order, "charges")
    details = rows(value(charge_container, "details", "items", default=charge_container))
    if not details:
        commission = number(value(order, "commission"))
        if commission is not None:
            details = [{"type": "COMMISSION", "after_discount_amount": commission}]
    result = []
    for index, detail in enumerate(details):
        charge_type = (text(value(detail, "type", "charge_type")) or "UNSPECIFIED").upper()
        amount = number(value(detail, "after_discount_amount", "amount", "original_amount"))
        result.append({
            **{key: order_record.get(key) for key in (
                "account_ref", "as_of", "retrieved_at", "batch_id", "raw_time", "raw_timezone",
                "occurred_at_utc", "market_date", "instrument_key", "display_symbol", "market",
                "currency", "asset_type", "direction", "order_id",
            )},
            "activity_type": "CHARGE",
            "provider_id": f"{order_record.get('order_id') or 'unknown'}:{charge_type}:{index}",
            "source_id": f"{SOURCE_PREFIX}:order-charges",
            "status": "REPORTED",
            "amount": amount,
            "charge_type": charge_type,
            "charge_description": text(value(detail, "type_desc", "description")),
        })
    return result


def _fund_activity_type(item: object) -> str:
    observed = " ".join(filter(None, [
        text(value(item, "type", "fund_type", "business_type")),
        text(value(item, "description", "remark", "action")),
    ])).upper()
    if "DIVIDEND" in observed:
        return "DIVIDEND"
    if "TAX" in observed or "WITHHOLD" in observed:
        return "TAX"
    if any(token in observed for token in ("SPLIT", "MERGER", "CORPORATE")):
        return "CORPORATE_ACTION"
    if any(token in observed for token in ("FOREX", "FX", "EXCHANGE")):
        return "FOREX_ACTIVITY"
    return "CASH_ACTIVITY"


def normalize_fund_detail(item: object, *, account_ref: str, retrieved_at: str, batch_id: str) -> dict[str, Any]:
    activity_type = _fund_activity_type(item)
    raw_time = value(item, "business_date", "settlement_date", "date", "timestamp", "time")
    occurred = utc_timestamp(raw_time)
    currency = (text(value(item, "currency")) or "UNKNOWN").upper()
    provider_id = text(value(item, "id", "serial_no", "reference_id", "transaction_id"))
    amount = number(value(item, "amount", "net_amount", "cash_amount"))
    return {
        "activity_type": activity_type,
        "account_ref": account_ref,
        "provider_id": provider_id,
        "source_id": f"{SOURCE_PREFIX}:fund-details",
        "as_of": occurred or retrieved_at,
        "retrieved_at": retrieved_at,
        "batch_id": batch_id,
        "raw_time": text(raw_time),
        "raw_timezone": "PROVIDER_UNSPECIFIED",
        "occurred_at_utc": occurred,
        "market_date": market_date(occurred, text(value(item, "market"))),
        "instrument_key": text(value(item, "symbol")),
        "display_symbol": text(value(item, "symbol")),
        "market": (text(value(item, "market")) or "UNKNOWN").upper(),
        "currency": currency,
        "asset_type": text(value(item, "sec_type")),
        "direction": (text(value(item, "direction", "action")) or "UNKNOWN").upper(),
        "status": (text(value(item, "status")) or "POSTED").upper(),
        "amount": amount,
        "fund_type": text(value(item, "type", "fund_type", "business_type")),
        "description": text(value(item, "description", "remark")),
    }


def normalize_funding(item: object, *, account_ref: str, retrieved_at: str, batch_id: str) -> dict[str, Any]:
    raw_time = value(item, "updated_at", "created_at", "timestamp", "date")
    occurred = utc_timestamp(raw_time)
    return {
        "activity_type": "FUNDING_ACTIVITY",
        "account_ref": account_ref,
        "provider_id": text(value(item, "id", "reference_id", "transaction_id")),
        "source_id": f"{SOURCE_PREFIX}:funding-history",
        "as_of": occurred or retrieved_at,
        "retrieved_at": retrieved_at,
        "batch_id": batch_id,
        "raw_time": text(raw_time),
        "raw_timezone": "PROVIDER_UNSPECIFIED",
        "occurred_at_utc": occurred,
        "market_date": market_date(occurred, None),
        "market": "ACCOUNT",
        "currency": (text(value(item, "currency")) or "UNKNOWN").upper(),
        "direction": (text(value(item, "direction", "type")) or "UNKNOWN").upper(),
        "status": (text(value(item, "status")) or "UNKNOWN").upper(),
        "amount": number(value(item, "amount")),
    }


def normalize_asset_point(item: object, *, account_ref: str, retrieved_at: str, batch_id: str, currency: str = "USD") -> dict[str, Any]:
    raw_date = value(item, "dt", "date", "business_date")
    occurred = utc_timestamp(raw_date)
    business_date = text(value(item, "dt", "business_date")) or (occurred[:10] if occurred else None)
    if not business_date:
        raise TigerNormalizationError("TIGER_ASSET_POINT_DATE_MISSING")
    return {
        "account_ref": account_ref,
        "source_id": f"{SOURCE_PREFIX}:analytics-asset",
        "as_of": occurred or f"{business_date}T00:00:00Z",
        "retrieved_at": retrieved_at,
        "business_date": business_date,
        "currency": currency,
        "asset_value": number(value(item, "asset", "net_liquidation", "total_asset", "value")),
        "cash_balance": number(value(item, "cash_balance", "cash")),
        "net_external_flow": number(value(item, "net_external_flow", "deposit_withdraw")),
        "daily_pnl": number(value(item, "pnl", "daily_pnl")),
        "batch_id": batch_id,
    }
