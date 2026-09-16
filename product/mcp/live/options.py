"""Yahoo 免费期权链的快照标准化；不推断买卖方向或历史变化。"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from importlib.metadata import version
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
        }
        if value["bid"] is None or value["ask"] is None:
            gaps.append({"reason": "OPTION_QUOTE_SIDE_MISSING", "contract_symbol": contract})
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
            },
            "parent_ids": [], "parent_hashes": [],
        }
        fact["evidence_id"] = "ev-yahoo-option-" + content_hash(fact)
        validate_contract("fact", fact)
        evidence.append(fact)
    return {"evidence": evidence, "gaps": gaps}


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
    if ticker_factory is None:
        import yfinance as yf
        ticker_factory = yf.Ticker
    target = ticker_factory(ticker, session=session)
    expirations = tuple(target.options or ())[:max_expiries]
    evidence, gaps = [], []
    for expiration in expirations:
        chain = target.option_chain(expiration)
        completed = iso_utc(retrieved_at())
        for frame, option_type in ((chain.calls, "CALL"), (chain.puts, "PUT")):
            rows = frame.to_dict("records")
            raw_hash = content_hash({"ticker": ticker, "expiration": expiration, "option_type": option_type, "rows": rows})
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
