"""Yahoo 免费期权链的快照标准化；不推断买卖方向或历史变化。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from importlib.metadata import version
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence

from product.mcp.live.contracts import require_source_admission, validate_contract
from product.mcp.live.cache import SnapshotCache
from product.mcp.live.market import MARKET_VERSION, YFINANCE_VERSION
from product.mcp.provenance import content_hash, iso_utc, parse_timestamp


OPTIONS_VERSION = "yahoo-option-snapshot/1.0.0"
OPTION_SELECTION_VERSION = "bounded-option-selection/1.0.0"
_OCC_SYMBOL = re.compile(
    r"^(?:US\.)?[A-Z0-9.-]+(?P<expiry>\d{6})[CP](?P<strike>\d{8})$"
)


def _number(value: Any, field: str, *, nullable: bool = True) -> str | None:
    if value is None or value == "":
        return None if nullable else _raise(field)
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"YAHOO_OPTION_VALUE_INVALID:{field}") from exc
    if not number.is_finite() or number < 0:
        raise ValueError(f"YAHOO_OPTION_VALUE_INVALID:{field}")
    return format(number, "f")


def _raise(field: str):
    raise ValueError(f"YAHOO_OPTION_VALUE_MISSING:{field}")


def _canonical_option_symbol(value: Any) -> str:
    symbol = str(value or "").strip().upper()
    return symbol[3:] if symbol.startswith("US.") else symbol


def _contract_expiration(value: Any) -> date | None:
    match = _OCC_SYMBOL.fullmatch(str(value or "").strip().upper())
    if match is None:
        return None
    try:
        return datetime.strptime(match.group("expiry"), "%y%m%d").date()
    except ValueError:
        return None


def select_option_expirations(
    expirations: Sequence[str], *, decision_date: str,
    held_contracts: Sequence[str] = (), max_expiries: int = 3,
) -> dict[str, Any]:
    """Select nearest/~30/~90 day expiries and replace the farthest for holdings."""

    if type(max_expiries) is not int or not 1 <= max_expiries <= 3:
        raise ValueError("OPTION_EXPIRY_SELECTION_BUDGET_INVALID")
    base = date.fromisoformat(decision_date)
    available = sorted({date.fromisoformat(str(value)) for value in expirations})
    available = [value for value in available if value >= base]
    selected: list[date] = []
    for target in (0, 30, 90)[:max_expiries]:
        remaining = [value for value in available if value not in selected]
        if remaining:
            selected.append(min(
                remaining, key=lambda value: (abs((value - base).days - target), value),
            ))

    held_expiries = sorted({
        expiry for expiry in (_contract_expiration(value) for value in held_contracts)
        if expiry is not None and expiry in available
    })
    for held_expiry in held_expiries:
        if held_expiry in selected:
            continue
        if len(selected) < max_expiries:
            selected.append(held_expiry)
            continue
        replaceable = [value for value in selected if value not in held_expiries]
        if not replaceable:
            break
        selected[selected.index(max(replaceable))] = held_expiry
    selected = sorted(set(selected))[:max_expiries]
    return {
        "policy_version": OPTION_SELECTION_VERSION,
        "selected_expirations": [value.isoformat() for value in selected],
        "available_expiration_count": len(available),
        "held_expirations_requested": [value.isoformat() for value in held_expiries],
        "held_expirations_missing": [
            value.isoformat() for value in held_expiries if value not in selected
        ],
    }


def select_option_contract_evidence(
    evidence: Sequence[Mapping[str, Any]], *, underlying_price: Any,
    decision_date: str, held_contracts: Sequence[str] = (), max_contracts: int = 48,
) -> dict[str, Any]:
    """Select four strikes on each side per call/put while retaining holdings first."""

    if type(max_contracts) is not int or not 1 <= max_contracts <= 48:
        raise ValueError("OPTION_CONTRACT_SELECTION_BUDGET_INVALID")
    try:
        spot = Decimal(str(underlying_price))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError("OPTION_UNDERLYING_PRICE_INVALID") from exc
    if not spot.is_finite() or spot <= 0:
        raise ValueError("OPTION_UNDERLYING_PRICE_INVALID")
    rows: list[tuple[Mapping[str, Any], date, Decimal, str, str]] = []
    for fact in evidence:
        value = fact.get("value")
        if not isinstance(value, Mapping):
            continue
        symbol = _canonical_option_symbol(value.get("contract_symbol"))
        option_type = str(value.get("option_type") or "")
        if not symbol or option_type not in {"CALL", "PUT"}:
            continue
        try:
            expiry = date.fromisoformat(str(value.get("expiration")))
            strike = Decimal(str(value.get("strike")))
        except (InvalidOperation, TypeError, ValueError):
            continue
        if expiry < date.fromisoformat(decision_date):
            continue
        if not strike.is_finite() or strike <= 0:
            continue
        rows.append((fact, expiry, strike, option_type, symbol))
    expiry_selection = select_option_expirations(
        [row[1].isoformat() for row in rows], decision_date=decision_date,
        held_contracts=held_contracts,
    )
    selected_expiries = {
        date.fromisoformat(value) for value in expiry_selection["selected_expirations"]
    }
    candidates = [row for row in rows if row[1] in selected_expiries]
    held = {_canonical_option_symbol(value) for value in held_contracts}
    near: dict[str, tuple[Mapping[str, Any], date, Decimal, str, str]] = {}
    for expiry in sorted(selected_expiries):
        for option_type in ("CALL", "PUT"):
            typed = [
                row for row in candidates if row[1] == expiry and row[3] == option_type
            ]
            below = sorted(
                (row for row in typed if row[2] <= spot),
                key=lambda row: (spot - row[2], row[2], row[4]),
            )[:4]
            above = sorted(
                (row for row in typed if row[2] >= spot),
                key=lambda row: (row[2] - spot, row[2], row[4]),
            )[:4]
            for row in below + above:
                near[row[4]] = row

    def order(row: tuple[Mapping[str, Any], date, Decimal, str, str]):
        return row[1], row[3], row[2], row[4]

    held_rows = sorted((row for row in candidates if row[4] in held), key=order)
    held_symbols = {row[4] for row in held_rows}
    other_rows = sorted(
        (row for symbol, row in near.items() if symbol not in held_symbols), key=order,
    )
    selected_rows = (held_rows + other_rows)[:max_contracts]
    selected_symbols = {row[4] for row in selected_rows}
    return {
        **expiry_selection,
        "selected_evidence": [dict(row[0]) for row in selected_rows],
        "selected_contract_symbols": [row[4] for row in selected_rows],
        "candidate_count": len(rows),
        "selected_count": len(selected_rows),
        "excluded_count": max(0, len(rows) - len(selected_rows)),
        "held_contracts_requested": sorted(held),
        "held_contracts_missing": sorted(held - selected_symbols),
        "underlying_price": format(spot, "f"),
    }


def _signed_number(value: Any, field: str) -> str | None:
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
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
        "underlying_price": _number(
            quote.get("regularMarketPrice"), "underlying_price", nullable=False,
        ),
        "calls": rows("calls"), "puts": rows("puts"),
    }


def collect_option_snapshot(
    *, security_id: str, ticker: str, source_access: Mapping[str, Any], session: Any,
    retrieved_at: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    max_expiries: int = 3, ticker_factory: Callable[..., Any] | None = None,
    held_contracts: Sequence[str] = (), underlying_price: Any | None = None,
) -> dict[str, Any]:
    if type(max_expiries) is not int or not 1 <= max_expiries <= 3:
        raise ValueError("YAHOO_OPTION_EXPIRY_BUDGET_INVALID")
    validate_contract("source-access", dict(source_access))
    require_source_admission(dict(source_access), at=retrieved_at())
    if source_access.get("provider") != "yahoo" or source_access.get("adapter_version") != MARKET_VERSION:
        raise ValueError("YAHOO_OPTION_ACCESS_MISMATCH")
    if version("yfinance") != YFINANCE_VERSION:
        raise ValueError("YAHOO_CLIENT_VERSION_MISMATCH")
    evidence, gaps = [], []
    expirations: tuple[str, ...]
    decision_date: str
    selection: dict[str, Any]
    if ticker_factory is None:
        from product.mcp.live.yahoo_transport import acquire_anonymous_crumb
        crumb = acquire_anonymous_crumb(session)
        first_response = session.get(
            f"https://query2.finance.yahoo.com/v7/finance/options/{ticker}",
            params={"crumb": crumb},
        )
        first_parsed = _parse_option_wire(first_response.content, ticker=ticker)
        first_completed = iso_utc(retrieved_at())
        decision_date = parse_timestamp(first_completed).date().isoformat()
        expiry_by_date = {
            datetime.fromtimestamp(value, tz=timezone.utc).date().isoformat(): value
            for value in first_parsed["expiration_dates"]
        }
        expiry_selection = select_option_expirations(
            list(expiry_by_date), decision_date=decision_date,
            held_contracts=held_contracts, max_expiries=max_expiries,
        )
        selected_expirations = list(expiry_selection["selected_expirations"])
        parsed_by_expiry = {
            first_parsed["expiration"]: (
                first_parsed, first_response.content, first_completed,
            )
        }
        for expiration in selected_expirations:
            if expiration in parsed_by_expiry:
                continue
            if expiration not in expiry_by_date:
                raise ValueError("YAHOO_OPTION_SELECTED_EXPIRATION_UNAVAILABLE")
            response = session.get(
                f"https://query2.finance.yahoo.com/v7/finance/options/{ticker}",
                params={"crumb": crumb, "date": expiry_by_date[expiration]},
            )
            parsed = _parse_option_wire(response.content, ticker=ticker)
            if parsed["expiration"] != expiration:
                raise ValueError("YAHOO_OPTION_EXPIRATION_BINDING_MISMATCH")
            completed = iso_utc(retrieved_at())
            parsed_by_expiry[expiration] = (parsed, response.content, completed)

        observed_prices = {
            str(parsed_by_expiry[value][0]["underlying_price"])
            for value in selected_expirations
        }
        if len(observed_prices) > 1:
            raise ValueError("YAHOO_OPTION_UNDERLYING_PRICE_DRIFT")
        spot = observed_prices.pop() if observed_prices else first_parsed["underlying_price"]
        for expiration in selected_expirations:
            parsed, raw_content, completed = parsed_by_expiry[expiration]
            raw_hash = hashlib.sha256(raw_content).hexdigest()
            for rows, option_type in ((parsed["calls"], "CALL"), (parsed["puts"], "PUT")):
                normalized = normalize_option_rows(
                    rows, security_id=security_id, ticker=ticker, expiration=expiration,
                    option_type=option_type, retrieved_at=completed, raw_content_hash=raw_hash,
                )
                evidence.extend(normalized["evidence"])
                gaps.extend(normalized["gaps"])
        expirations = tuple(selected_expirations)
    else:
        target = ticker_factory(ticker, session=session)
        decision_date = parse_timestamp(iso_utc(retrieved_at())).date().isoformat()
        expiry_selection = select_option_expirations(
            tuple(target.options or ()), decision_date=decision_date,
            held_contracts=held_contracts, max_expiries=max_expiries,
        )
        expirations = tuple(expiry_selection["selected_expirations"])
        spot = underlying_price
        if spot is None:
            fast_info = getattr(target, "fast_info", None)
            spot = (
                fast_info.get("last_price") if isinstance(fast_info, Mapping)
                else getattr(fast_info, "last_price", None)
            )
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
    selection = select_option_contract_evidence(
        evidence, underlying_price=spot, decision_date=decision_date,
        held_contracts=held_contracts,
    )
    for key in (
        "available_expiration_count", "held_expirations_requested",
        "held_expirations_missing",
    ):
        selection[key] = expiry_selection[key]
    selected_symbols = set(selection["selected_contract_symbols"])
    evidence = list(selection.pop("selected_evidence"))
    gaps = [
        item for item in gaps
        if not item.get("contract_symbol")
        or _canonical_option_symbol(item.get("contract_symbol")) in selected_symbols
    ]
    gaps.append({"reason": "YAHOO_OPTION_SELECTION_COVERAGE", **selection})
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
                session=session, retrieved_at=now, max_expiries=3,
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
