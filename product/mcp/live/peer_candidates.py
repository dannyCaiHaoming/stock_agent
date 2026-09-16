"""从冻结 NASDAQ 目录构造同行候选池；不替代 LLM 的同行判断。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping, Sequence

from product.mcp.provenance import content_hash, parse_timestamp


POOL_VERSION = "peer-candidate-pool/1.0.0"
PRODUCER_VERSION = "nasdaq-peer-candidate-pool/1.0.0"
_EXCLUDED_NAME_TOKENS = (
    " warrant", " warrants", " rights", " unit", " units", " preferred",
    " depositary", " etf", " fund",
)


def _market_cap(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("PEER_CANDIDATE_MARKET_CAP_INVALID") from exc
    if not number.is_finite() or number < 0:
        raise ValueError("PEER_CANDIDATE_MARKET_CAP_INVALID")
    return number


def _candidate_security_id(symbol: str) -> str:
    return f"US:NASDAQ_CANDIDATE:{symbol}"


def build_peer_candidate_pool(
    holdings: Sequence[Mapping[str, Any]], *, universe: Mapping[str, Any],
    max_candidates_per_holding: int = 12,
) -> dict[str, Any]:
    """确定性缩小请求预算；输出仍是未核实候选，不作同行选择。"""

    if type(max_candidates_per_holding) is not int or not 1 <= max_candidates_per_holding <= 30:
        raise ValueError("PEER_CANDIDATE_SCOPE_INVALID")
    if universe.get("schema_version") != "live-universe/1.0.0":
        raise ValueError("PEER_CANDIDATE_UNIVERSE_INVALID")
    if universe.get("completeness") != "COMPLETE":
        return _finalize_pool(holdings, universe=universe, rows=[], gap="UNIVERSE_NOT_COMPLETE")
    if parse_timestamp(universe["retrieved_at"]) < parse_timestamp(universe["request_started_at"]):
        raise ValueError("PEER_CANDIDATE_UNIVERSE_TIME_INVALID")
    rows = universe.get("rows")
    if not isinstance(rows, list):
        raise ValueError("PEER_CANDIDATE_UNIVERSE_INVALID")
    by_symbol = {str(row.get("symbol", "")).upper(): row for row in rows}
    if len(by_symbol) != len(rows):
        raise ValueError("PEER_CANDIDATE_UNIVERSE_DUPLICATE")

    groups = []
    holding_symbols = {str(item.get("ticker", "")).upper() for item in holdings}
    for holding in holdings:
        security_id = holding.get("security_id")
        ticker = str(holding.get("ticker", "")).upper()
        if not isinstance(security_id, str) or not security_id or not ticker:
            raise ValueError("PEER_CANDIDATE_HOLDING_INVALID")
        anchor = by_symbol.get(ticker)
        if anchor is None:
            groups.append({
                "security_id": security_id, "ticker": ticker,
                "status": "SOURCE_LIMITED", "match_basis": None,
                "anchor": None, "candidates": [],
                "gaps": ["HOLDING_NOT_IN_DIRECTORY"],
            })
            continue
        basis = "industry" if anchor.get("industry") else "sector" if anchor.get("sector") else None
        if basis is None:
            groups.append({
                "security_id": security_id, "ticker": ticker,
                "status": "SOURCE_LIMITED", "match_basis": None,
                "anchor": _row_view(anchor), "candidates": [],
                "gaps": ["DIRECTORY_CLASSIFICATION_MISSING"],
            })
            continue
        anchor_cap = _market_cap(anchor.get("market_cap"))
        candidates = []
        for row in rows:
            symbol = str(row.get("symbol", "")).upper()
            name = str(row.get("name", ""))
            if symbol in holding_symbols or row.get(basis) != anchor.get(basis):
                continue
            if any(token in f" {name.lower()}" for token in _EXCLUDED_NAME_TOKENS):
                continue
            cap = _market_cap(row.get("market_cap"))
            # 排序只服务请求预算：市值更接近者优先；未知市值排后。
            distance = (
                abs(cap.ln() - anchor_cap.ln())
                if cap is not None and cap > 0 and anchor_cap is not None and anchor_cap > 0
                else Decimal("Infinity")
            )
            view = _row_view(row)
            view.update({
                "candidate_id": "peer-candidate-" + content_hash({
                    "for_security_id": security_id,
                    "symbol": symbol,
                    "universe_hash": universe["snapshot_hash"],
                })[:24],
                "candidate_security_id": _candidate_security_id(symbol),
                "candidate_status": "UNVERIFIED",
                "candidate_only": True,
                "selection_authority": "LLM_REQUIRED",
                "budget_order_basis": "MARKET_CAP_PROXIMITY_THEN_SYMBOL",
            })
            candidates.append((distance, symbol, view))
        selected = [item[2] for item in sorted(candidates, key=lambda item: (item[0], item[1]))[:max_candidates_per_holding]]
        groups.append({
            "security_id": security_id, "ticker": ticker,
            "status": "READY" if selected else "SOURCE_LIMITED",
            "match_basis": basis, "anchor": _row_view(anchor),
            "candidates": selected,
            "gaps": [] if selected else ["NO_DIRECTORY_CANDIDATES"],
        })
    return _finalize_pool(holdings, universe=universe, rows=groups)


def _row_view(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: row.get(key) for key in (
            "symbol", "name", "market_cap", "country", "ipo_year", "sector",
            "industry", "source_id", "as_of", "retrieved_at", "raw_content_hash",
        )
    }


def _finalize_pool(
    holdings: Sequence[Mapping[str, Any]], *, universe: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]], gap: str | None = None,
) -> dict[str, Any]:
    groups = list(rows)
    if gap is not None:
        groups = [{
            "security_id": item["security_id"], "ticker": str(item["ticker"]).upper(),
            "status": "SOURCE_LIMITED", "match_basis": None, "anchor": None,
            "candidates": [], "gaps": [gap],
        } for item in holdings]
    pool = {
        "schema_version": POOL_VERSION,
        "producer_version": PRODUCER_VERSION,
        "source_id": universe.get("source_id", "nasdaq-screener"),
        "source_locator": universe.get("source_locator"),
        "universe_snapshot_hash": universe.get("snapshot_hash"),
        "as_of": universe.get("as_of"),
        "retrieved_at": universe.get("retrieved_at"),
        "candidate_semantics": "UNVERIFIED_DIRECTORY_CANDIDATES_NOT_SELECTED_PEERS",
        "groups": groups,
    }
    pool["pool_hash"] = content_hash(pool)
    validate_peer_candidate_pool(pool)
    return pool


def validate_peer_candidate_pool(pool: Mapping[str, Any]) -> None:
    if pool.get("schema_version") != POOL_VERSION or pool.get("producer_version") != PRODUCER_VERSION:
        raise ValueError("PEER_CANDIDATE_POOL_VERSION_INVALID")
    if pool.get("candidate_semantics") != "UNVERIFIED_DIRECTORY_CANDIDATES_NOT_SELECTED_PEERS":
        raise ValueError("PEER_CANDIDATE_SEMANTICS_INVALID")
    for key in ("source_id", "source_locator", "universe_snapshot_hash", "as_of", "retrieved_at"):
        if not isinstance(pool.get(key), str) or not pool[key]:
            raise ValueError(f"PEER_CANDIDATE_PROVENANCE_MISSING:{key}")
    parse_timestamp(pool["as_of"])
    parse_timestamp(pool["retrieved_at"])
    groups = pool.get("groups")
    if not isinstance(groups, list) or len({item.get("security_id") for item in groups}) != len(groups):
        raise ValueError("PEER_CANDIDATE_GROUPS_INVALID")
    candidate_ids = set()
    for group in groups:
        if group.get("status") not in {"READY", "SOURCE_LIMITED"}:
            raise ValueError("PEER_CANDIDATE_GROUP_STATUS_INVALID")
        if group.get("status") == "READY" and not group.get("candidates"):
            raise ValueError("PEER_CANDIDATE_READY_EMPTY")
        for candidate in group.get("candidates", []):
            if (
                candidate.get("candidate_status") != "UNVERIFIED"
                or candidate.get("candidate_only") is not True
                or candidate.get("selection_authority") != "LLM_REQUIRED"
            ):
                raise ValueError("PEER_CANDIDATE_AUTHORITY_INVALID")
            identifier = candidate.get("candidate_id")
            if not isinstance(identifier, str) or identifier in candidate_ids:
                raise ValueError("PEER_CANDIDATE_ID_INVALID")
            candidate_ids.add(identifier)
    expected = content_hash({key: value for key, value in pool.items() if key != "pool_hash"})
    if pool.get("pool_hash") != expected:
        raise ValueError("PEER_CANDIDATE_POOL_HASH_MISMATCH")
