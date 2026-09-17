"""Yahoo 免费期权链的快照标准化；不推断买卖方向或历史变化。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from importlib.metadata import version
import hashlib
import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from product.mcp.live.contracts import require_source_admission, validate_contract
from product.mcp.live.cache import SnapshotCache
from product.mcp.live.market import MARKET_VERSION, YFINANCE_VERSION
from product.mcp.provenance import content_hash, iso_utc, parse_timestamp


OPTIONS_VERSION = "yahoo-option-snapshot/1.0.0"


def _number(value: Any, field: str, *, nullable: bool = True) -> str | None:
    if value is None or value == "":
        return None if nullable else _raise(field)
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"YAHOO_OPTION_VALUE_INVALID:{field}") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"YAHOO_OPTION_VALUE_INVALID:{field}")
    return format(number, "f")


def _raise(field: str):
    raise ValueError(f"YAHOO_OPTION_VALUE_MISSING:{field}")


def _signed_number(value: Any, field: str) -> str | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"YAHOO_OPTION_VALUE_INVALID:{field}") from exc
    if not number.is_finite():
        raise ValueError(f"YAHOO_OPTION_VALUE_INVALID:{field}")
    return format(number, "f")


def normalize_option_rows(
    rows: Sequence[Mapping[str, Any]], *, security_id: str, ticker: str,
    expiration: str, option_type: str, retrieved_at: str,
    raw_content_hash: str,
) -> dict[str, Any]:
    if option_type not in {"CALL", "PUT"}:
        raise ValueError("YAHOO_OPTION_TYPE_INVALID")
    expiry = date.fromisoformat(expiration)
    retrieved = parse_timestamp(retrieved_at)
    if expiry < retrieved.date():
        return {"evidence": [], "gaps": [{"reason": "OPTION_EXPIRATION_PASSED", "expiration": expiration}]}
    evidence, gaps, seen = [], [], set()
    for row in rows:
        contract = row.get("contractSymbol")
        if not isinstance(contract, str) or not contract or contract in seen:
            raise ValueError("YAHOO_OPTION_CONTRACT_INVALID")
        seen.add(contract)
        strike = _number(row.get("strike"), "strike", nullable=False)
        bid = _number(row.get("bid"), "bid")
        ask = _number(row.get("ask"), "ask")
        if bid is not None and ask is not None and Decimal(ask) < Decimal(bid):
            raise ValueError("YAHOO_OPTION_CROSSED_QUOTE")
        last_trade = row.get("lastTradeDate")
        if isinstance(last_trade, datetime):
            last_trade = iso_utc(last_trade)
        elif isinstance(last_trade, str) and last_trade:
            last_trade = iso_utc(last_trade)
        else:
            last_trade = None
        if last_trade is not None and parse_timestamp(last_trade) > retrieved:
            raise ValueError("YAHOO_OPTION_LAST_TRADE_IN_FUTURE")
        multiplier = _number(
            row.get("contractMultiplier", row.get("multiplier")), "contract_multiplier"
        )
        if multiplier == "0":
            raise ValueError("YAHOO_OPTION_MULTIPLIER_INVALID")
        greeks = {
            name: _signed_number(row.get(name), name)
            for name in ("delta", "gamma", "theta", "vega", "rho")
        }
        value = {
            "contract_symbol": contract,
            "option_type": option_type,
            "expiration": expiration,
            "strike": strike,
            "last_price": _number(row.get("lastPrice"), "last_price"),
            "bid": bid,
            "ask": ask,
            "volume": _number(row.get("volume"), "volume"),
            "open_interest": _number(row.get("openInterest"), "open_interest"),
            "implied_volatility": _number(row.get("impliedVolatility"), "implied_volatility"),
            "in_the_money": bool(row.get("inTheMoney")) if row.get("inTheMoney") is not None else None,
            "last_trade_at": last_trade,
            "quote_observed_at": iso_utc(retrieved),
            "open_interest_observed_at": iso_utc(retrieved),
            "contract_size_label": row.get("contractSize"),
            "contract_multiplier": multiplier,
            "greeks": greeks,
        }
        if value["bid"] is None or value["ask"] is None:
            gaps.append({"reason": "OPTION_QUOTE_SIDE_MISSING", "contract_symbol": contract})
        if multiplier is None:
            gaps.append({"reason": "OPTION_MULTIPLIER_MISSING", "contract_symbol": contract})
        missing_greeks = sorted(name for name, number in greeks.items() if number is None)
        if missing_greeks:
            gaps.append({
                "reason": "OPTION_GREEKS_MISSING", "contract_symbol": contract,
                "fields": missing_greeks,
            })
        fact = {
            "schema_version": "live-fact/1.0.0", "security_id": security_id,
            "semantic_field": "option_chain_contract", "value": value,
            "unit": "contract_snapshot", "currency": "USD",
            "source_id": f"yahoo-options-{ticker}", "source_type": "options",
            "source_locator": f"https://query2.finance.yahoo.com/v7/finance/options/{ticker}",
            "source_version": f"yfinance/{YFINANCE_VERSION}/{OPTIONS_VERSION}",
            "as_of": iso_utc(retrieved), "published_at": iso_utc(retrieved),
            "published_at_policy": "retrieval_time_snapshot/not_exchange_timestamp",
            "retrieved_at": iso_utc(retrieved), "raw_content_hash": raw_content_hash,
            "kind": "market_structure", "usage": "current",
            "metadata": {
                "provider_symbol": ticker, "expiration": expiration,
                "snapshot_only": True, "historical_open_interest_available": False,
                "trade_direction_available": False,
                "quote_time_policy": "retrieval_time; provider exchange quote timestamp unavailable",
                "open_interest_time_policy": "retrieval_time snapshot; publication vintage unavailable",
                "greeks_status": "PARTIAL" if missing_greeks else "REPORTED_NOT_RECALCULATED",
                "cross_source_synchronization": "NOT_ASSUMED",
            },
            "parent_ids": [], "parent_hashes": [],
        }
        fact["evidence_id"] = "ev-yahoo-option-" + content_hash(fact)
        validate_contract("fact", fact)
        evidence.append(fact)
    return {"evidence": evidence, "gaps": gaps}


def _parse_option_wire(raw: bytes, *, ticker: str) -> dict[str, Any]:
    if not raw or len(raw) > 32 * 1024 * 1024:
        raise ValueError("YAHOO_OPTION_RESPONSE_SIZE_INVALID")
    try:
        body = json.loads(raw)
        root = body["optionChain"]
        results = root["result"]
    except (UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise ValueError("YAHOO_OPTION_RESPONSE_INVALID") from exc
    if root.get("error") is not None or not isinstance(results, list) or len(results) != 1:
        raise ValueError("YAHOO_OPTION_RESULT_INVALID")
    result = results[0]
    quote = result.get("quote", {})
    if result.get("underlyingSymbol") not in (None, ticker) \
            or quote.get("symbol") not in (None, ticker) \
            or quote.get("quoteType") not in (None, "EQUITY"):
        raise ValueError("YAHOO_OPTION_SECURITY_MISMATCH")
    expiration_dates = result.get("expirationDates")
    option_sets = result.get("options")
    if not isinstance(expiration_dates, list) or any(
        not isinstance(value, int) or isinstance(value, bool) or value <= 0
        for value in expiration_dates
    ) or not isinstance(option_sets, list) or len(option_sets) != 1:
        raise ValueError("YAHOO_OPTION_STRUCTURE_INVALID")
    option_set = option_sets[0]
    expiration_epoch = option_set.get("expirationDate")
    if not isinstance(expiration_epoch, int) or isinstance(expiration_epoch, bool) or expiration_epoch <= 0:
        raise ValueError("YAHOO_OPTION_EXPIRATION_INVALID")

    def rows(name: str) -> list[dict[str, Any]]:
        values = option_set.get(name, [])
        if not isinstance(values, list):
            raise ValueError("YAHOO_OPTION_STRUCTURE_INVALID")
        normalized = []
        for value in values:
            if not isinstance(value, Mapping):
                raise ValueError("YAHOO_OPTION_STRUCTURE_INVALID")
            item = dict(value)
            contract = item.get("contractSymbol")
            if not isinstance(contract, str) or not contract.startswith(ticker):
                raise ValueError("YAHOO_OPTION_SECURITY_MISMATCH")
            last_trade = item.get("lastTradeDate")
            if last_trade is not None:
                if not isinstance(last_trade, int) or isinstance(last_trade, bool) or last_trade <= 0:
                    raise ValueError("YAHOO_OPTION_LAST_TRADE_INVALID")
                item["lastTradeDate"] = iso_utc(datetime.fromtimestamp(last_trade, tz=timezone.utc))
            normalized.append(item)
        return normalized

    return {
        "expiration_dates": expiration_dates,
        "expiration": datetime.fromtimestamp(expiration_epoch, tz=timezone.utc).date().isoformat(),
        "calls": rows("calls"), "puts": rows("puts"),
    }


def collect_option_snapshot(
    *, security_id: str, ticker: str, source_access: Mapping[str, Any], session: Any,
    retrieved_at: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    max_expiries: int = 2, ticker_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    if type(max_expiries) is not int or not 1 <= max_expiries <= 2:
        raise ValueError("YAHOO_OPTION_EXPIRY_BUDGET_INVALID")
    validate_contract("source-access", dict(source_access))
    require_source_admission(dict(source_access), at=retrieved_at())
    if source_access.get("provider") != "yahoo" or source_access.get("adapter_version") != MARKET_VERSION:
        raise ValueError("YAHOO_OPTION_ACCESS_MISMATCH")
    if version("yfinance") != YFINANCE_VERSION:
        raise ValueError("YAHOO_CLIENT_VERSION_MISMATCH")
    evidence, gaps = [], []
    expirations: tuple[str, ...]
    if ticker_factory is None:
        from product.mcp.live.yahoo_transport import acquire_anonymous_crumb
        crumb = acquire_anonymous_crumb(session)
        pending_dates: list[int | None] = [None]
        completed_expirations: list[str] = []
        for index in range(max_expiries):
            requested_date = pending_dates[index]
            params = {"crumb": crumb}
            if requested_date is not None:
                params["date"] = requested_date
            response = session.get(
                f"https://query2.finance.yahoo.com/v7/finance/options/{ticker}", params=params,
            )
            parsed = _parse_option_wire(response.content, ticker=ticker)
            if index == 0:
                pending_dates = list(parsed["expiration_dates"][:max_expiries])
                if not pending_dates:
                    break
                if pending_dates[0] != int(datetime.fromisoformat(parsed["expiration"]).replace(
                    tzinfo=timezone.utc,
                ).timestamp()):
                    # Yahoo may encode midnight in a market timezone. The payload's
                    # explicit chain expiration remains authoritative for this row.
                    pending_dates[0] = None
            expiration = parsed["expiration"]
            if expiration in completed_expirations:
                raise ValueError("YAHOO_OPTION_DUPLICATE_EXPIRATION")
            completed_expirations.append(expiration)
            completed = iso_utc(retrieved_at())
            raw_hash = hashlib.sha256(response.content).hexdigest()
            for rows, option_type in ((parsed["calls"], "CALL"), (parsed["puts"], "PUT")):
                normalized = normalize_option_rows(
                    rows, security_id=security_id, ticker=ticker, expiration=expiration,
                    option_type=option_type, retrieved_at=completed, raw_content_hash=raw_hash,
                )
                evidence.extend(normalized["evidence"])
                gaps.extend(normalized["gaps"])
            if index + 1 >= len(pending_dates):
                break
        expirations = tuple(completed_expirations)
    else:
        target = ticker_factory(ticker, session=session)
        expirations = tuple(target.options or ())[:max_expiries]
        for expiration in expirations:
            chain = target.option_chain(expiration)
            completed = iso_utc(retrieved_at())
            for frame, option_type in ((chain.calls, "CALL"), (chain.puts, "PUT")):
                rows = frame.to_dict("records")
                raw_hash = content_hash({
                    "ticker": ticker, "expiration": expiration,
                    "option_type": option_type, "rows": rows,
                })
                normalized = normalize_option_rows(
                    rows, security_id=security_id, ticker=ticker, expiration=expiration,
                    option_type=option_type, retrieved_at=completed, raw_content_hash=raw_hash,
                )
                evidence.extend(normalized["evidence"])
                gaps.extend(normalized["gaps"])
    if not expirations:
        gaps.append({"reason": "YAHOO_OPTION_EXPIRATIONS_EMPTY"})
    return {
        "schema_version": "option-snapshot/1.0.0",
        "status": "FROZEN" if evidence else "SOURCE_LIMITED",
        "security_id": security_id, "ticker": ticker,
        "expirations": list(expirations), "evidence": evidence, "gaps": gaps,
        "adapter_version": OPTIONS_VERSION,
        "request_events": list(getattr(session.live_boundary, "events", [])),
    }


def collect_portfolio_option_snapshots(
    *, securities: Sequence[Mapping[str, str]], access_path: Path,
    output_path: Path, state_root: Path, cache_root: Path,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    session_factory: Callable[..., Any] | None = None,
    option_collector: Callable[..., Mapping[str, Any]] = collect_option_snapshot,
) -> dict[str, Any]:
    """逐证券隔离期权会话；一只来源失败不删除其他证券或核心研究。"""

    from product.mcp.live.contracts import external_path
    access = json.loads(external_path(access_path).read_text(encoding="utf-8"))
    matches = [item for item in access if item.get("provider") == "yahoo"] if isinstance(access, list) else []
    if len(matches) != 1:
        raise ValueError("YAHOO_OPTION_POLICY_MISSING")
    policy = matches[0]
    validate_contract("source-access", policy)
    require_source_admission(policy, at=now())
    cache = SnapshotCache(cache_root)
    if session_factory is None:
        from product.mcp.live.yahoo_transport import create_yahoo_session
        session_factory = create_yahoo_session
    evidence, gaps, events, records = [], [], [], []
    seen = set()
    for security in securities:
        security_id, ticker = security.get("security_id"), security.get("ticker")
        if not isinstance(security_id, str) or not isinstance(ticker, str) or security_id in seen:
            raise ValueError("YAHOO_OPTION_SECURITY_BINDING_INVALID")
        seen.add(security_id)
        session = None
        try:
            session = session_factory(
                policy, tickers=[ticker], state_dir=Path(state_root) / ticker, cache=cache,
            )
            result = option_collector(
                security_id=security_id, ticker=ticker, source_access=policy,
                session=session, retrieved_at=now, max_expiries=1,
            )
            evidence.extend(result["evidence"])
            gaps.extend(dict(item, security_id=security_id) for item in result["gaps"])
            records.extend({
                "record_hash": item["record"]["record_hash"],
                "raw_content_hash": item["record"]["raw_content_hash"],
                "retrieved_at": item["record"]["retrieved_at"],
            } for item in session.live_boundary.option_records)
            events.append({
                "producer": "yahoo-option-snapshot", "security_id": security_id,
                "status": result["status"], "completed_at": iso_utc(now()),
                "expirations": result["expirations"],
                "evidence_ids": [item["evidence_id"] for item in result["evidence"]],
            })
            events.extend(session.live_boundary.events)
        except (OSError, ValueError, KeyError, TypeError, ImportError) as exc:
            code = str(exc).split(":", 1)[0]
            gaps.append({"security_id": security_id, "reason": "OPTIONS_SOURCE_LIMITED", "failure_code": code})
            events.append({
                "producer": "yahoo-option-snapshot", "security_id": security_id,
                "status": "SOURCE_LIMITED", "failure_code": code,
                "completed_at": iso_utc(now()),
            })
        finally:
            if session is not None:
                session.close()
    cutoff = now()
    admitted = [
        item for item in evidence
        if max(parse_timestamp(item["as_of"]), parse_timestamp(item["published_at"]), parse_timestamp(item["retrieved_at"])) <= cutoff
    ]
    snapshot = {
        "schema_version": "portfolio-option-snapshot/1.0.0",
        "status": "FROZEN" if admitted else "SOURCE_LIMITED",
        "decision_cutoff": iso_utc(cutoff),
        "security_ids": sorted(seen),
        "evidence": sorted(admitted, key=lambda item: item["evidence_id"]),
        "excluded_evidence_ids": sorted(set(item["evidence_id"] for item in evidence) - {item["evidence_id"] for item in admitted}),
        "gaps": gaps, "events": events,
        "records": sorted(records, key=lambda item: item["record_hash"]),
        "adapter_version": OPTIONS_VERSION,
    }
    snapshot["snapshot_hash"] = content_hash(snapshot)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return snapshot
