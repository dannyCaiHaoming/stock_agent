"""东方财富不复权日线规范化；仅输出事实与缺口，不推导证券身份或投资判断。"""
from datetime import date
from decimal import Decimal
import hashlib
import json

from product.mcp.live.contracts import validate_contract
from product.mcp.live.eastmoney_transport import ADAPTER_VERSION, AKSHARE_VERSION, ENDPOINT, validate_payload
from product.mcp.provenance import content_hash, iso_utc, parse_timestamp


def normalize_record(record, raw, *, security_id, provider_symbol, calendar):
    key = record["key"]
    expected = {"provider": "eastmoney", "client": "akshare", "client_version": AKSHARE_VERSION,
                "adapter_version": ADAPTER_VERSION, "provider_symbol": provider_symbol,
                "interval": "daily", "adjust": "", "klt": "101", "fqt": "0", "endpoint": ENDPOINT}
    if any(key.get(k) != v for k,v in expected.items()):
        raise ValueError("EASTMONEY_RECORD_SOURCE_DRIFT")
    if hashlib.sha256(raw).hexdigest() != record["raw_content_hash"]:
        raise ValueError("EASTMONEY_RAW_HASH_MISMATCH")
    start, end = date.fromisoformat(key["start"]), date.fromisoformat(key["end"])
    body = validate_payload(raw, ticker=provider_symbol.split(".", 1)[1], start=start, end=end,
                            limit=(end - start).days + 1)
    retrieved = parse_timestamp(record["retrieved_at"])
    evidence, gaps = [], []
    for row in body["data"]["klines"]:
        columns = row.split(",")
        day, close = columns[0], Decimal(columns[2])
        close_at = calendar.session_close(day)
        if close_at is None or parse_timestamp(close_at) > retrieved:
            gaps.append({"date": day, "reason": "NOT_COMPLETED_REGULAR_SESSION"})
            continue
        fact = {"schema_version": "live-fact/2.0.0", "security_id": security_id,
                "semantic_field": "close_price", "value": format(close, "f"), "unit": "USD", "currency": "USD",
                "source_id": "eastmoney-daily", "source_type": "eastmoney", "source_locator": ENDPOINT,
                "source_version": f"akshare/{AKSHARE_VERSION}/{ADAPTER_VERSION}",
                "as_of": close_at, "published_at": close_at,
                "published_at_policy": "completed_session_end/provider_eod_not_real_time",
                "retrieved_at": iso_utc(retrieved), "raw_content_hash": record["raw_content_hash"],
                "kind": "price", "usage": "current", "parent_ids": [], "parent_hashes": [],
                "metadata": {"provider_symbol": provider_symbol, "trading_date": day,
                    "exchange_timezone": "America/New_York", "price_basis": "provider_close",
                    "client": "akshare", "client_version": AKSHARE_VERSION, "adapter_version": ADAPTER_VERSION,
                    "adjust": "", "fqt": "0", "klt": "101", "dividends": None, "stock_splits": None,
                    "adjustment_semantics": "requested_unadjusted/corporate_actions_not_provided",
                    "historical_return_eligible": False, "calendar_version": calendar.version,
                    "calendar_hash": calendar.content_hash}}
        fact["evidence_id"] = "ev-eastmoney-" + content_hash(fact)
        validate_contract("fact", fact)
        evidence.append(fact)
    return {"evidence": evidence, "gaps": gaps}


def collect_daily(securities, *, start, end, client, calendar, max_age_seconds=86400, refresh=False):
    """接收采集层已核实身份，不以 provider_symbol 前缀猜测交易所或币种。"""
    targets = {}
    for security in securities:
        if set(security) != {"security_id", "provider_symbol", "currency", "identity_verified"}:
            raise ValueError("EASTMONEY_SECURITY_SCOPE_INVALID")
        if security["currency"] != "USD" or security["identity_verified"] is not True:
            raise ValueError("EASTMONEY_VERIFIED_USD_IDENTITY_REQUIRED")
        symbol = security["provider_symbol"]
        if symbol in targets and targets[symbol] != security:
            raise ValueError("EASTMONEY_SECURITY_IDENTITY_CONFLICT")
        targets[symbol] = dict(security)
    facts, gaps, records = [], [], {}
    before = client.requests
    for symbol, security in sorted(targets.items()):
        record = client.fetch(symbol=symbol, start=start, end=end, max_age_seconds=max_age_seconds, refresh=refresh)
        normalized = normalize_record(record, client.cache.read(record), security_id=security["security_id"],
                                      provider_symbol=symbol, calendar=calendar)
        records[symbol] = record
        facts.extend(normalized["evidence"])
        gaps.extend(dict(g, security_id=security["security_id"]) for g in normalized["gaps"])
        if not normalized["evidence"]:
            gaps.append({"security_id": security["security_id"], "reason": "EASTMONEY_NO_COMPLETED_PRICE"})
    return {"evidence": facts, "gaps": gaps, "records": records,
            "actual_http_requests": client.requests - before, "adapter_version": ADAPTER_VERSION}
