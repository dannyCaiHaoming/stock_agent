"""SEC、Yahoo 与 Moomoo SG 个股背景补充包的有界采集与装配。"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re
from typing import Any, Callable, Mapping, Sequence

from product.mcp.provenance import iso_utc, parse_timestamp
from product.mcp.live.research_supplement import (
    assemble_company_background,
    build_capability,
    build_capture_batch,
    build_research_supplement_package,
    build_supplement_fact,
    normalize_sec_financial_history,
    normalize_sec_guidance_candidate,
)


SUPPLEMENT_COLLECTION_VERSION = "research-supplement-collection/1.1.0"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _failure(source: str, dataset: str, code: str) -> dict[str, Any]:
    return {
        "source": source, "dataset": dataset, "status": "SOURCE_LIMITED",
        "failure_code": code, "evidence": [], "gaps": [code],
        "limitations": ["该来源本次未返回可验证 Evidence。"],
    }


def _normalized_result(
    source: str, dataset: str, normalized: Mapping[str, Any],
) -> dict[str, Any]:
    evidence = [
        dict(item) for item in normalized.get("evidence", [])
        if item.get("dataset") == dataset
    ]
    gaps = [
        item for item in normalized.get("gaps", [])
        if not isinstance(item, Mapping) or item.get("dataset") in (None, dataset)
    ]
    if not evidence:
        code = f"{source.upper()}_{dataset.upper()}_EMPTY"
        return {**_failure(source, dataset, code), "actual_requests": 1}
    return {
        "source": source, "dataset": dataset,
        "status": "PARTIAL" if gaps else "AVAILABLE",
        "failure_code": None, "evidence": evidence, "gaps": gaps,
        "limitations": [], "actual_requests": 1,
    }


def _append_result(target: list[dict[str, Any]], item: Mapping[str, Any]) -> None:
    """同一来源/数据集的有界多方法结果合并为一个 capability 记录。"""
    existing = next((value for value in target if value["source"] == item["source"]
                     and value["dataset"] == item["dataset"]), None)
    if existing is None:
        target.append(dict(item))
        return
    def fact_key(fact: Mapping[str, Any]) -> tuple[str, str, str]:
        return (
            str(fact.get("source_id")), str(fact.get("semantic_field")),
            json.dumps(fact.get("value"), sort_keys=True, ensure_ascii=False, default=str),
        )
    seen = {fact_key(value) for value in existing["evidence"]}
    for value in item["evidence"]:
        key = fact_key(value)
        if key not in seen:
            existing["evidence"].append(dict(value))
            seen.add(key)
    existing["gaps"].extend(item["gaps"])
    existing["limitations"].extend(str(value) for value in item["limitations"])
    existing["actual_requests"] = (
        int(existing.get("actual_requests", 0)) + int(item.get("actual_requests", 0))
    )
    statuses = {existing["status"], item["status"]}
    if statuses <= {"AVAILABLE"}:
        existing["status"] = "AVAILABLE"
        existing["failure_code"] = None
    elif existing["evidence"]:
        existing["status"] = "PARTIAL"
        existing["failure_code"] = None
    else:
        existing["status"] = item["status"]
        existing["failure_code"] = existing["failure_code"] or item["failure_code"]


def _yahoo_option_result(normalized: Mapping[str, Any]) -> dict[str, Any]:
    evidence = []
    for original in normalized.get("evidence", []):
        value = original["value"]
        contract_symbol = (
            value.get("contract_symbol") if isinstance(value, Mapping) else None
        )
        semantic_field = str(original["semantic_field"])
        if isinstance(contract_symbol, str) and contract_symbol:
            semantic_field = f"{semantic_field}:{contract_symbol}"
        evidence.append(build_supplement_fact(
            security_id=str(original["security_id"]), dataset="options_snapshot",
            semantic_field=semantic_field, value=value,
            source_id=str(original["source_id"]), source_family="yahoo",
            source_locator=str(original["source_locator"]),
            source_version=str(original["source_version"]), as_of=str(original["as_of"]),
            published_at=str(original["published_at"]), retrieved_at=str(original["retrieved_at"]),
            raw_content_hash=str(original["raw_content_hash"]), limitations=[
                "Yahoo 免费动态期权快照；字段时间按检索时点保守冻结",
                "单次 volume/OI 不证明主动买卖方向或持仓变化",
            ],
        ))
    if not evidence:
        return _failure("yahoo", "options_snapshot", "YAHOO_OPTIONS_EMPTY")
    return {
        "source": "yahoo", "dataset": "options_snapshot",
        "status": "PARTIAL" if normalized.get("gaps") else "AVAILABLE",
        "failure_code": None, "evidence": evidence,
        "gaps": list(normalized.get("gaps", [])), "limitations": [],
    }


def _yahoo_option_codes_needing_supplement(item: Mapping[str, Any] | None) -> list[str]:
    """Reuse Yahoo's already selected contracts; never run a second selection policy."""
    if item is None or item.get("status") not in {"AVAILABLE", "PARTIAL"}:
        return []
    from product.mcp.live.options import _canonical_option_symbol

    codes: set[str] = set()
    for fact in item.get("evidence", []):
        value = fact.get("value")
        if not isinstance(value, Mapping):
            continue
        symbol = value.get("contract_symbol")
        if not isinstance(symbol, str):
            continue
        greeks = value.get("greeks")
        missing_greeks = not isinstance(greeks, Mapping) or any(
            greeks.get(name) is None for name in ("delta", "gamma", "vega", "theta", "rho")
        )
        if not (missing_greeks or value.get("contract_multiplier") is None
                or value.get("implied_volatility") is None):
            continue
        canonical = _canonical_option_symbol(symbol)
        if not canonical.startswith(str(fact.get("security_id", "")).rsplit(":", 1)[-1]):
            continue
        codes.add("US." + canonical)
    return sorted(codes)[:48]


def _option_source_conflicts(
    yahoo: Mapping[str, Any], moomoo: Mapping[str, Any],
) -> list[dict[str, Any]]:
    def differs(left: Any, right: Any) -> bool:
        try:
            return Decimal(str(left)) != Decimal(str(right))
        except (InvalidOperation, ValueError):
            return str(left) != str(right)

    def identity(value: Mapping[str, Any]) -> tuple[str, str, str] | None:
        try:
            return (str(value["expiration"]), format(Decimal(str(value["strike"])).normalize(), "f"),
                    str(value["option_type"]).upper())
        except (KeyError, InvalidOperation, TypeError, ValueError):
            return None

    known = {
        identity(fact["value"]): fact["value"]
        for fact in yahoo.get("evidence", [])
        if isinstance(fact.get("value"), Mapping) and identity(fact["value"]) is not None
    }
    conflicts = []
    for fact in moomoo.get("evidence", []):
        value = fact.get("value")
        if not isinstance(value, Mapping):
            continue
        original = known.get(identity(value))
        if original is None:
            continue
        fields = []
        for name in ("bid", "ask", "open_interest", "implied_volatility", "contract_multiplier"):
            if original.get(name) is not None and value.get(name) is not None \
                    and differs(original[name], value[name]):
                fields.append(name)
        original_greeks = original.get("greeks")
        moomoo_greeks = value.get("greeks")
        if isinstance(original_greeks, Mapping) and isinstance(moomoo_greeks, Mapping):
            for name in ("delta", "gamma", "vega", "theta", "rho"):
                if original_greeks.get(name) is not None and moomoo_greeks.get(name) is not None \
                        and differs(original_greeks[name], moomoo_greeks[name]):
                    fields.append(f"greeks.{name}")
        if fields:
            conflicts.append({"reason": "OPTION_CROSS_SOURCE_FIELD_CONFLICT",
                              "contract_symbol": value.get("contract_symbol"),
                              "fields": sorted(fields)})
    return conflicts


def _map_selected_yahoo_options_to_opend(
    client: Any, *, ticker: str, yahoo: Mapping[str, Any],
    selected_codes: Sequence[str],
) -> tuple[list[str], list[dict[str, Any]], int]:
    """Resolve only existing Yahoo selections via static identity, never reselect."""
    from product.mcp.live.options import _canonical_option_symbol

    selected = {_canonical_option_symbol(code) for code in selected_codes}
    targets = {}
    gaps = []
    for fact in yahoo.get("evidence", []):
        value = fact.get("value")
        if not isinstance(value, Mapping) or _canonical_option_symbol(
            value.get("contract_symbol")
        ) not in selected:
            continue
        label = str(value.get("contract_size_label") or "").upper()
        if label not in {"REGULAR", "STANDARD"}:
            gaps.append({"reason": "OPTION_CONTRACT_ADJUSTMENT_UNVERIFIED",
                         "contract_symbol": value.get("contract_symbol")})
            continue
        try:
            key = (str(value["expiration"]), format(Decimal(str(value["strike"])).normalize(), "f"),
                   str(value["option_type"]).upper())
        except (KeyError, InvalidOperation, TypeError, ValueError):
            gaps.append({"reason": "OPTION_CONTRACT_IDENTITY_INCOMPLETE",
                         "contract_symbol": value.get("contract_symbol")})
            continue
        targets[key] = value["contract_symbol"]
    mapped = []
    expirations = sorted({key[0] for key in targets})[:3]
    for expiration in expirations:
        capture = client.read(
            capability_id="option-chain-static-v1",
            params={"code": f"US.{ticker}", "start": expiration, "end": expiration},
        )
        by_identity: dict[tuple[str, str, str], list[str]] = {}
        for row in capture["payload"]["rows"]:
            if row.get("stock_owner") != f"US.{ticker}" \
                    or row.get("option_standard_type") != "STANDARD":
                continue
            try:
                key = (str(row["strike_time"]),
                       format(Decimal(str(row["strike_price"])).normalize(), "f"),
                       str(row["option_type"]).upper())
            except (KeyError, InvalidOperation, TypeError, ValueError):
                continue
            by_identity.setdefault(key, []).append(str(row["code"]))
        for key, yahoo_symbol in targets.items():
            if key[0] != expiration:
                continue
            matches = sorted(set(by_identity.get(key, [])))
            if len(matches) == 1:
                mapped.append(matches[0])
            else:
                gaps.append({"reason": "OPTION_CONTRACT_MAPPING_NOT_UNIQUE",
                             "contract_symbol": yahoo_symbol,
                             "match_count": len(matches)})
    return sorted(set(mapped))[:48], gaps, len(expirations)


_PAGINATED_QUOTE_CAPABILITIES = frozenset({
    "institutional-aggregate-v1", "insider-holder-list-v1", "insider-trade-list-v1",
    "option-underlying-history-v1", "option-underlying-volatility-v1",
    "economic-calendar-v1",
})


def _read_quote_pages(
    client: Any, *, capability_id: str, params: Mapping[str, Any],
    max_pages: int = 3,
    stop_when: Callable[[Sequence[Mapping[str, Any]]], bool] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Only approved Quote capabilities; opaque cursors never enter research facts."""
    if capability_id not in _PAGINATED_QUOTE_CAPABILITIES or not 1 <= max_pages <= 3:
        raise ValueError("MOOMOO_QUOTE_PAGINATION_POLICY_INVALID")
    request = dict(params)
    seen: set[str] = set()
    captures, gaps = [], []
    for page in range(max_pages):
        try:
            capture = client.read(capability_id=capability_id, params=request)
        except Exception as exc:
            if not captures:
                raise
            gaps.append({"reason": "MOOMOO_QUOTE_PAGE_FAILED",
                         "capability_id": capability_id, "pages_read": page,
                         "failure_code": str(exc).split(":", 1)[0]})
            break
        captures.append(capture)
        if stop_when is not None and stop_when(captures):
            break
        payload = capture.get("payload", {})
        rows = payload.get("rows", [])
        attrs = payload.get("attrs", {})
        key_name = "next_page" if capability_id == "economic-calendar-v1" else "next_key"
        cursor = attrs.get(key_name)
        if cursor is None and rows and isinstance(rows[0], Mapping):
            cursor = rows[0].get("next_key")
        if capability_id == "economic-calendar-v1" and not attrs.get("has_more"):
            break
        if cursor in (None, "", "-1"):
            if capability_id == "economic-calendar-v1" and attrs.get("has_more"):
                gaps.append({"reason": "MOOMOO_QUOTE_PAGE_CURSOR_MISSING",
                             "capability_id": capability_id, "pages_read": page + 1})
            break
        if not isinstance(cursor, str) or cursor in seen:
            gaps.append({"reason": "MOOMOO_QUOTE_PAGE_CURSOR_REPEATED",
                         "capability_id": capability_id, "pages_read": page + 1})
            break
        if page + 1 == max_pages:
            gaps.append({"reason": "MOOMOO_QUOTE_PAGE_BUDGET_REACHED",
                         "capability_id": capability_id, "pages_read": max_pages})
            break
        seen.add(cursor)
        request["next_key"] = cursor
    return captures, gaps


def _institutional_history_covered(
    captures: Sequence[Mapping[str, Any]], *, cutoff: datetime,
) -> bool:
    periods = set()
    for capture in captures:
        for row in capture.get("payload", {}).get("rows", []):
            match = re.fullmatch(r"(\d{4})/Q([1-4])", str(row.get("period_text", "")))
            if match:
                year, quarter = int(match.group(1)), int(match.group(2))
                month = quarter * 3
                end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=timezone.utc) \
                    - timedelta(days=1)
                if end.date() < cutoff.date():
                    periods.add((year, quarter))
    return len(periods) >= 2


def _verify_institution_capture_clock(
    capture: Mapping[str, Any], *,
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Observe a rounded provider timestamp again; never backdate a future fact."""
    from product.mcp.live.moomoo_normalize import _unix_time

    original = parse_timestamp(capture["retrieved_at"])
    future = []
    for row in capture.get("payload", {}).get("rows", []):
        if not isinstance(row, Mapping) or not row.get("update_time"):
            continue
        try:
            updated = parse_timestamp(_unix_time(row["update_time"]))
        except (ValueError, OverflowError, TypeError):
            continue
        if updated > original:
            future.append(updated)
    if not future or max(future) - original > timedelta(seconds=2):
        return dict(capture)
    target = max(future)
    for _ in range(5):
        observed = clock()
        if observed >= target:
            return {**capture, "verified_at": iso_utc(observed)}
        sleep(min(0.5, max((target - observed).total_seconds(), 0)))
    return dict(capture)


def _finish_page_coverage(
    results: list[dict[str, Any]], *, dataset: str,
    page_gaps: Sequence[Mapping[str, Any]],
) -> None:
    item = next((entry for entry in results if entry["source"] == "moomoo_sg"
                 and entry["dataset"] == dataset), None)
    if item is None:
        return
    item["actual_requests"] = int(item.get("actual_requests", 0)) + sum(
        gap.get("reason") == "MOOMOO_QUOTE_PAGE_FAILED"
        for gap in page_gaps
    )
    if not page_gaps:
        item["gaps"] = [gap for gap in item["gaps"] if not (
            isinstance(gap, Mapping) and gap.get("reason") in {
                "MOOMOO_SHARED_DATA_MORE_PAGES", "MOOMOO_INSIDER_TRADES_MORE_PAGES",
            }
        )]
    if dataset == "institutional_ownership" and sum(
        fact.get("value", {}).get("period_provisional") is False
        for fact in item["evidence"]
    ) >= 2:
        item["gaps"] = [gap for gap in item["gaps"] if not (
            isinstance(gap, Mapping) and gap.get("reason") ==
            "MOOMOO_INSTITUTION_TWO_COMPLETED_PERIODS_MISSING"
        )]
    item["gaps"].extend(page_gaps)
    item["status"] = (
        "PARTIAL" if item["gaps"] and item["evidence"] else
        "AVAILABLE" if item["evidence"] else "SOURCE_LIMITED"
    )


def capture_public_company_news_result(
    *, security_id: str, ticker: str, issuer_name: str | None,
    cache_root: Path, decision_cutoff: str | None = None,
    transport: Callable[..., Any] | None = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> dict[str, Any]:
    """Two public metadata queries, never article-body fetches."""
    from product.mcp.live.moomoo_public_news import fetch_news_search

    source = "moomoo_public_news"
    dataset = "research_discovery"
    name = issuer_name.strip() if isinstance(issuer_name, str) and issuer_name.strip() else ticker
    issuer_words = [
        word for word in re.findall(r"[A-Za-z0-9]+", name.casefold())
        if word not in {"inc", "corp", "corporation", "co", "ltd", "limited", "class"}
    ]
    issuer_key = " ".join(issuer_words[:2]) if len(issuer_words) >= 2 else None
    title_ticker = re.compile(rf"(?<![A-Z0-9]){re.escape(ticker.upper())}(?:\.US)?(?![A-Z0-9])")
    candidates, gaps, seen = [], [], set()
    for keyword, news_type in ((ticker.upper(), 3), (name, 2)):
        arguments = dict(keyword=keyword, news_type=news_type, cache_root=cache_root,
                         decision_cutoff=decision_cutoff, now=now)
        if transport is not None:
            arguments["transport"] = transport
        try:
            result = fetch_news_search(**arguments)
        except (OSError, ValueError) as exc:
            code = str(exc).split(":", 1)[0]
            gaps.append(code if code.startswith("MOOMOO_PUBLIC_NEWS_") else "MOOMOO_PUBLIC_NEWS_FAILED")
            continue
        for candidate in result["candidates"]:
            title = candidate["title"]
            lowered = title.casefold()
            if re.search(r"\b(?:etf|etn|leveraged|inverse|fund)\b", lowered):
                gaps.append("MOOMOO_PUBLIC_NEWS_NON_ISSUER_INSTRUMENT")
                continue
            if not title_ticker.search(title.upper()) and not (
                issuer_key and issuer_key in " ".join(re.findall(r"[a-z0-9]+", lowered))
            ):
                gaps.append("MOOMOO_PUBLIC_NEWS_ISSUER_UNVERIFIED")
                continue
            dedupe_key = (candidate["canonical_url"], title.casefold())
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            candidates.append((candidate, result))
    if not candidates:
        return _failure(source, dataset, gaps[0] if gaps else "MOOMOO_PUBLIC_NEWS_NO_RELEVANT_LEADS")
    gaps = list(dict.fromkeys(gaps))
    evidence = []
    for candidate, result in candidates:
        news_type = candidate["news_type"]
        evidence.append(build_supplement_fact(
            security_id=security_id, dataset=dataset,
            semantic_field=f"moomoo_public_lead:{news_type}:{candidate['news_id']}",
            value={
                "title": candidate["title"], "original_url": candidate["original_url"],
                "canonical_url": candidate["canonical_url"], "news_type": news_type,
                "content_tier": "LEAD_ONLY",
                "lead_kind": "NOTICE_INDEX" if news_type == 2 else "RATING_OR_RESEARCH_NEWS",
                "body_verified": False,
            },
            source_id=candidate["source_id"], source_family=source,
            source_locator=candidate["canonical_url"],
            source_version="moomoo-public-news-search/1.0.0",
            as_of=candidate["published_at"], published_at=candidate["published_at"],
            retrieved_at=result["retrieved_at"], raw_content_hash=result["raw_content_hash"],
            limitations=["仅标题与链接线索；非独立研报或发行人原文正文"],
        ))
    return {
        "source": source, "dataset": dataset,
        "status": "PARTIAL" if gaps else "AVAILABLE", "failure_code": None,
        "evidence": evidence, "gaps": gaps,
        "limitations": ["仅发现线索；正文未核验，不能满足 BODY_VERIFIED"],
    }


def capture_external_research_results(
    positions: Sequence[Mapping[str, Any]], *, access: Sequence[Mapping[str, Any]],
    cache_root: Path, state_root: Path,
    held_option_contracts: Mapping[str, Sequence[str]] | None = None,
    peer_scope: bool = False,
    now: Callable[[], str] = _now,
) -> dict[str, list[dict[str, Any]]]:
    """先于共同 cutoff 采集 Yahoo/OpenD；任一来源失败只降级对应数据集。"""

    from product.mcp.live.cache import SnapshotCache

    result = {str(item["security_id"]): [] for item in positions}
    cache = SnapshotCache(cache_root)
    policies = {str(item["provider"]): item for item in access}
    tickers = [str(item["ticker"]) for item in positions]
    yahoo_datasets = (
        ("identity_profile", "analyst_expectations") if peer_scope else (
            "identity_profile", "event_context", "analyst_expectations",
            "share_short_context", "capital_allocation",
        )
    )
    try:
        from product.mcp.live.yahoo_research import collect_quote_summary
        from product.mcp.live.yahoo_transport import (
            acquire_anonymous_crumb, create_yahoo_session,
        )
        session = create_yahoo_session(
            policies["yahoo"], tickers=tickers,
            state_dir=state_root / "yahoo-state", cache=cache,
        )
        crumb = acquire_anonymous_crumb(session)
        for position in positions:
            security_id, ticker = str(position["security_id"]), str(position["ticker"])
            try:
                normalized = collect_quote_summary(
                    session=session, cache=cache, security_id=security_id,
                    ticker=ticker, retrieved_at=now(), crumb=crumb,
                )
                result[security_id].extend(
                    _normalized_result("yahoo", dataset, normalized)
                    for dataset in yahoo_datasets
                )
                if peer_scope:
                    continue
                try:
                    from product.mcp.live.options import collect_option_snapshot
                    option_result = collect_option_snapshot(
                        security_id=security_id, ticker=ticker,
                        source_access=policies["yahoo"], session=session,
                        retrieved_at=lambda: parse_timestamp(now()), max_expiries=3,
                        held_contracts=(held_option_contracts or {}).get(ticker, ()),
                    )
                    result[security_id].append(_yahoo_option_result(option_result))
                except Exception as exc:
                    code = str(exc).split(":", 1)[0] or "YAHOO_OPTIONS_FAILED"
                    result[security_id].append(_failure("yahoo", "options_snapshot", code))
            except Exception as exc:  # 来源错误必须被证券级隔离
                code = str(exc).split(":", 1)[0] or "YAHOO_RESEARCH_FAILED"
                result[security_id].extend(
                    _failure("yahoo", dataset, code) for dataset in yahoo_datasets
                )
                if not peer_scope:
                    result[security_id].append(_failure("yahoo", "options_snapshot", code))
    except Exception as exc:
        code = str(exc).split(":", 1)[0] or "YAHOO_RESEARCH_CONFIGURATION_FAILED"
        for position in positions:
            result[str(position["security_id"])].extend(
                _failure("yahoo", dataset, code) for dataset in yahoo_datasets
            )
            if not peer_scope:
                result[str(position["security_id"])].append(
                    _failure("yahoo", "options_snapshot", code)
                )

    from product.mcp.live.moomoo_normalize import (
        normalize_opend_analyst_consensus,
        normalize_opend_capital_flow,
        normalize_opend_capital_distribution,
        normalize_opend_company_profile,
        normalize_opend_institutional_aggregate,
        normalize_opend_morningstar_report,
        normalize_opend_company_executives,
        normalize_opend_insider_holders,
        normalize_opend_insider_trades,
        normalize_opend_market_snapshot,
        normalize_opend_option_chain,
        normalize_opend_option_underlying,
        normalize_opend_rating_summary,
        normalize_opend_revenue_breakdown,
        normalize_opend_short_interest,
        select_opend_option_contracts,
    )
    from product.mcp.live.moomoo_opend import MoomooOpenDQuoteClient, load_quote_manifest

    core_calls = (
        ("identity_profile", "company-profile-v1", {}, normalize_opend_company_profile),
        ("vendor_money_flow", "capital-flow-v1", {"period_type": "INTRADAY"}, normalize_opend_capital_flow),
        ("analyst_expectations", "analyst-consensus-v1", {}, normalize_opend_analyst_consensus),
        ("institutional_ownership", "institutional-aggregate-v1", {"num": 50}, normalize_opend_institutional_aggregate),
        ("research_discovery", "morningstar-report-v1", {}, normalize_opend_morningstar_report),
    )
    enhancement_calls = (
        ("vendor_money_flow", "capital-distribution-v1", {}, normalize_opend_capital_distribution),
        ("business_segments", "revenue-breakdown-v1", {}, normalize_opend_revenue_breakdown),
        ("management_governance", "company-executives-v1", {}, normalize_opend_company_executives),
        ("insider_transactions", "insider-holder-list-v1", {"num": 20}, normalize_opend_insider_holders),
        ("insider_transactions", "insider-trade-list-v1", {"num": 20}, normalize_opend_insider_trades),
        ("research_discovery", "institution-rating-summary-v1", {"rating_dimension_type": 1, "num": 20}, normalize_opend_rating_summary),
        ("research_discovery", "analyst-rating-summary-v1", {"rating_dimension_type": 2, "num": 20}, normalize_opend_rating_summary),
    )
    if peer_scope:
        allowed = {"identity_profile", "analyst_expectations", "business_segments", "research_discovery"}
        core_calls = tuple(item for item in core_calls if item[0] in allowed)
        enhancement_calls = tuple(item for item in enhancement_calls if item[0] in allowed)
    calls = (*core_calls, *enhancement_calls)
    deadline = time.monotonic() + 120 * max(1, len(positions))
    manifest = load_quote_manifest()
    for position in positions:
        security_id, ticker = str(position["security_id"]), str(position["ticker"])
        client = MoomooOpenDQuoteClient(manifest=manifest, cache=cache)
        try:
            client.readiness()
        except Exception as exc:
            code = str(exc).split(":", 1)[0] or "MOOMOO_OPEND_UNREACHABLE"
            fallback_datasets = set() if peer_scope else {
                "options_snapshot", "options_underlying_context", "share_short_context",
            }
            for dataset in sorted({item[0] for item in calls} | fallback_datasets):
                if dataset in {"options_snapshot", "share_short_context"} and any(
                    item["source"] == "yahoo" and item["dataset"] == dataset
                    and item["status"] in {"AVAILABLE", "PARTIAL"}
                    for item in result[security_id]
                ):
                    # Readiness failed before this fallback was needed or attempted.
                    continue
                _append_result(result[security_id], _failure("moomoo_sg", dataset, code))
            continue
        for dataset, capability, extra_params, normalizer in core_calls:
            try:
                params = {"code": f"US.{ticker}", **extra_params}
                if capability == "institutional-aggregate-v1":
                    captures, page_gaps = _read_quote_pages(
                        client, capability_id=capability, params=params,
                        stop_when=lambda pages: _institutional_history_covered(
                            pages, cutoff=parse_timestamp(now()),
                        ),
                    )
                else:
                    captures = [client.read(capability_id=capability, params=params)]
                    page_gaps = []
                for capture in captures:
                    if capability == "institutional-aggregate-v1":
                        capture = _verify_institution_capture_clock(capture)
                    normalized = normalizer(capture, security_id=security_id, ticker=ticker)
                    _append_result(
                        result[security_id], _normalized_result("moomoo_sg", dataset, normalized),
                    )
                if capability == "institutional-aggregate-v1":
                    _finish_page_coverage(result[security_id], dataset=dataset, page_gaps=page_gaps)
            except Exception as exc:
                code = str(exc).split(":", 1)[0] or "MOOMOO_RESEARCH_FAILED"
                _append_result(result[security_id], _failure("moomoo_sg", dataset, code))
        if peer_scope:
            for dataset, capability, extra_params, normalizer in enhancement_calls:
                if time.monotonic() > deadline:
                    _append_result(result[security_id], _failure(
                        "moomoo_sg", dataset, "MOOMOO_BATCH_TIME_BUDGET_EXHAUSTED",
                    ))
                    continue
                try:
                    capture = client.read(capability_id=capability,
                                          params={"code": f"US.{ticker}", **extra_params})
                    normalized = normalizer(capture, security_id=security_id, ticker=ticker)
                    _append_result(result[security_id], _normalized_result(
                        "moomoo_sg", dataset, normalized,
                    ))
                except Exception as exc:
                    _append_result(result[security_id], _failure(
                        "moomoo_sg", dataset,
                        str(exc).split(":", 1)[0] or "MOOMOO_RESEARCH_FAILED",
                    ))
            continue
        yahoo_options = next(
            (item for item in result[security_id]
             if item["source"] == "yahoo" and item["dataset"] == "options_snapshot"), None,
        )
        supplement_codes = _yahoo_option_codes_needing_supplement(yahoo_options)
        needs_moomoo_options = (
            yahoo_options is None
            or yahoo_options["status"] not in {"AVAILABLE", "PARTIAL"}
        )
        if supplement_codes and time.monotonic() <= deadline:
            try:
                mapped_codes, mapping_gaps, chain_requests = _map_selected_yahoo_options_to_opend(
                    client, ticker=ticker, yahoo=yahoo_options,
                    selected_codes=supplement_codes,
                )
                if not mapped_codes:
                    raise ValueError("MOOMOO_OPTION_CONTRACT_MAPPING_EMPTY")
                capture = client.read(
                    capability_id="market-snapshot-v1",
                    params={"code_list": mapped_codes},
                )
                normalized = normalize_opend_market_snapshot(
                    capture, security_id=security_id, ticker=ticker,
                )
                normalized["gaps"].extend(_option_source_conflicts(yahoo_options, normalized))
                normalized["gaps"].extend(mapping_gaps)
                normalized["gaps"].append({
                    "reason": "OPTION_CROSS_SOURCE_SNAPSHOT_NOT_MERGED",
                    "contract_count": len(mapped_codes),
                })
                option_result = _normalized_result(
                    "moomoo_sg", "options_snapshot", normalized,
                )
                option_result["actual_requests"] = chain_requests + 1
                _append_result(result[security_id], option_result)
            except Exception as exc:
                _append_result(result[security_id], _failure(
                    "moomoo_sg", "options_snapshot",
                    str(exc).split(":", 1)[0] or "MOOMOO_OPTIONS_SUPPLEMENT_FAILED",
                ))
        elif supplement_codes:
            _append_result(result[security_id], _failure(
                "moomoo_sg", "options_snapshot", "MOOMOO_BATCH_TIME_BUDGET_EXHAUSTED",
            ))
        if needs_moomoo_options and time.monotonic() > deadline:
            _append_result(result[security_id], _failure(
                "moomoo_sg", "options_snapshot", "MOOMOO_BATCH_TIME_BUDGET_EXHAUSTED",
            ))
        elif needs_moomoo_options:
            try:
                underlying = client.read(
                    capability_id="market-snapshot-v1", params={"code_list": [f"US.{ticker}"]},
                )
                spot = underlying["payload"]["rows"][0]["last_price"]
                expirations = client.read(
                    capability_id="option-expirations-v1", params={"code": f"US.{ticker}"},
                )
                dates = sorted({str(row["strike_time"]) for row in expirations["payload"]["rows"]})
                if not dates:
                    raise ValueError("MOOMOO_OPTION_EXPIRATIONS_EMPTY")
                today = parse_timestamp(now()).date()
                from product.mcp.live.options import select_option_expirations
                expiry_selection = select_option_expirations(
                    dates, decision_date=today.isoformat(),
                    held_contracts=(held_option_contracts or {}).get(ticker, ()),
                )
                chosen = list(expiry_selection["selected_expirations"])
                chain = client.read(capability_id="option-chain-static-v1", params={
                    "code": f"US.{ticker}", "start": min(chosen), "end": max(chosen),
                })
                selection = select_opend_option_contracts(
                    chain["payload"]["rows"], underlying_price=spot,
                    decision_date=today.isoformat(),
                    held_contracts=[str(value) for value in (
                        (held_option_contracts or {}).get(ticker, ())
                    )],
                )
                if not selection["selected_codes"]:
                    raise ValueError("MOOMOO_OPTION_SELECTION_EMPTY")
                dynamic = client.read(capability_id="market-snapshot-v1", params={
                    "code_list": selection["selected_codes"],
                })
                normalized = normalize_opend_market_snapshot(
                    dynamic, security_id=security_id, ticker=ticker,
                )
                normalized["gaps"].append({"reason": "MOOMOO_OPTION_SELECTION_COVERAGE", **selection})
                _append_result(result[security_id], _normalized_result(
                    "moomoo_sg", "options_snapshot", normalized,
                ))
            except Exception as exc:
                code = str(exc).split(":", 1)[0] or "MOOMOO_OPTIONS_FAILED"
                try:
                    static = normalize_opend_option_chain(
                        chain, security_id=security_id, ticker=ticker,
                    )
                    _append_result(result[security_id], _normalized_result(
                        "moomoo_sg", "options_snapshot", static,
                    ))
                except Exception:
                    _append_result(result[security_id], _failure(
                        "moomoo_sg", "options_snapshot", code,
                    ))
        for dataset, capability, extra_params, normalizer in enhancement_calls:
            if time.monotonic() > deadline:
                _append_result(result[security_id], _failure(
                    "moomoo_sg", dataset, "MOOMOO_BATCH_TIME_BUDGET_EXHAUSTED",
                ))
                continue
            try:
                params = {"code": f"US.{ticker}", **extra_params}
                if capability in {"insider-holder-list-v1", "insider-trade-list-v1"}:
                    captures, page_gaps = _read_quote_pages(
                        client, capability_id=capability, params=params,
                    )
                else:
                    captures = [client.read(capability_id=capability, params=params)]
                    page_gaps = []
                for capture in captures:
                    normalized = normalizer(capture, security_id=security_id, ticker=ticker)
                    _append_result(result[security_id], _normalized_result(
                        "moomoo_sg", dataset, normalized,
                    ))
                if capability in {"insider-holder-list-v1", "insider-trade-list-v1"}:
                    _finish_page_coverage(result[security_id], dataset=dataset, page_gaps=page_gaps)
            except Exception as exc:
                code = str(exc).split(":", 1)[0] or "MOOMOO_RESEARCH_FAILED"
                _append_result(result[security_id], _failure("moomoo_sg", dataset, code))
        anchor = parse_timestamp(now()).date()
        option_history_range = {
            "start": (anchor - timedelta(days=30)).isoformat(), "end": anchor.isoformat(),
        }
        for capability, params in (
            ("option-underlying-overview-v1", {"code_list": [f"US.{ticker}"]}),
            ("option-underlying-history-v1", {"code": f"US.{ticker}", **option_history_range}),
            ("option-underlying-volatility-v1", {"code": f"US.{ticker}", **option_history_range}),
        ):
            if time.monotonic() > deadline:
                _append_result(result[security_id], _failure(
                    "moomoo_sg", "options_underlying_context",
                    "MOOMOO_BATCH_TIME_BUDGET_EXHAUSTED",
                ))
                break
            try:
                if capability in {"option-underlying-history-v1", "option-underlying-volatility-v1"}:
                    captures, page_gaps = _read_quote_pages(
                        client, capability_id=capability, params=params,
                    )
                else:
                    captures = [client.read(capability_id=capability, params=params)]
                    page_gaps = []
                for capture in captures:
                    normalized = normalize_opend_option_underlying(
                        capture, security_id=security_id, ticker=ticker,
                    )
                    _append_result(result[security_id], _normalized_result(
                        "moomoo_sg", "options_underlying_context", normalized,
                    ))
                if capability in {"option-underlying-history-v1", "option-underlying-volatility-v1"}:
                    _finish_page_coverage(result[security_id], dataset="options_underlying_context",
                                          page_gaps=page_gaps)
            except Exception as exc:
                code = str(exc).split(":", 1)[0] or "MOOMOO_OPTION_CONTEXT_FAILED"
                _append_result(result[security_id], _failure(
                    "moomoo_sg", "options_underlying_context", code,
                ))
        yahoo_short = next(
            (item for item in result[security_id]
             if item["source"] == "yahoo" and item["dataset"] == "share_short_context"),
            None,
        )
        if yahoo_short is not None and yahoo_short["status"] not in {"AVAILABLE", "PARTIAL"}:
            if time.monotonic() > deadline:
                _append_result(result[security_id], _failure(
                    "moomoo_sg", "share_short_context",
                    "MOOMOO_BATCH_TIME_BUDGET_EXHAUSTED",
                ))
                continue
            try:
                capture = client.read(
                    capability_id="short-interest-v1",
                    params={"code": f"US.{ticker}", "num": 50},
                )
                normalized = normalize_opend_short_interest(
                    capture, security_id=security_id, ticker=ticker,
                )
                _append_result(result[security_id], _normalized_result(
                    "moomoo_sg", "share_short_context", normalized,
                ))
            except Exception as exc:
                code = str(exc).split(":", 1)[0] or "MOOMOO_RESEARCH_FAILED"
                _append_result(result[security_id], _failure(
                    "moomoo_sg", "share_short_context", code,
                ))
    return result


def capture_shared_research_results(
    *, cache_root: Path, now: Callable[[], str] = _now,
) -> list[dict[str, Any]]:
    """每批一次采集 Moomoo Macro/Market 补充；失败不影响逐证券主流程。"""
    from product.mcp.live.cache import SnapshotCache
    from product.mcp.live.moomoo_normalize import (
        normalize_opend_macro_history, normalize_opend_market_breadth,
        normalize_opend_shared_frame,
    )
    from product.mcp.live.moomoo_opend import MoomooOpenDQuoteClient, load_quote_manifest

    outputs: list[dict[str, Any]] = []
    deadline = time.monotonic() + 120
    client = MoomooOpenDQuoteClient(manifest=load_quote_manifest(), cache=SnapshotCache(cache_root))
    try:
        client.readiness()
    except Exception as exc:
        code = str(exc).split(":", 1)[0] or "MOOMOO_OPEND_UNREACHABLE"
        return [_failure("moomoo_sg", dataset, code) for dataset in (
            "macro_history", "economic_calendar", "fedwatch_expectations",
            "dot_plot", "market_breadth", "option_market_statistics",
        )]

    def collect(dataset: str, capability: str, params: Mapping[str, Any], normalizer: Callable[[Mapping[str, Any]], Mapping[str, Any]]) -> None:
        if time.monotonic() > deadline:
            _append_result(outputs, _failure(
                "moomoo_sg", dataset, "MOOMOO_SHARED_TIME_BUDGET_EXHAUSTED",
            ))
            return
        try:
            _append_result(outputs, _normalized_result(
                "moomoo_sg", dataset, normalizer(client.read(capability_id=capability, params=params)),
            ))
        except Exception as exc:
            code = str(exc).split(":", 1)[0] or "MOOMOO_SHARED_RESEARCH_FAILED"
            _append_result(outputs, _failure("moomoo_sg", dataset, code))

    anchor = parse_timestamp(now()).date()
    start = (anchor - timedelta(days=30)).isoformat()
    end = anchor.isoformat()
    calendar_end = (anchor + timedelta(days=30)).isoformat()
    collect("market_breadth", "rise-fall-distribution-v1", {"region": "US"}, normalize_opend_market_breadth)
    for data_type in ("VOLUME", "OPEN_INTEREST"):
        collect("option_market_statistics", "option-market-statistic-v1", {
            "option_market": "US_SECURITY", "data_type": data_type,
            "start": start, "end": end,
        }, lambda capture, data_type=data_type: normalize_opend_shared_frame(
            capture, dataset="option_market_statistics",
            semantic_prefix=f"moomoo_option_market_{data_type.lower()}",
            method="get_option_market_statistic", limit=31,
        ))
    for indicator_id in sorted({
        1003000001, 1003000002, 1003000003, 1003000004,
        1003000010, 1003000007, 1003000006, 1003000026,
    }):
        collect("macro_history", "macro-indicator-history-v1", {
            "indicator_id": indicator_id, "max_count": 24,
        }, lambda capture, indicator_id=indicator_id: normalize_opend_macro_history(
            capture, indicator_id=indicator_id,
        ))
    collect("fedwatch_expectations", "fedwatch-target-rate-v1", {},
            lambda capture: normalize_opend_shared_frame(
                capture, dataset="fedwatch_expectations", semantic_prefix="moomoo_fedwatch",
                method="get_fed_watch_target_rate", limit=3,
            ))
    collect("dot_plot", "fedwatch-dot-plot-v1", {},
            lambda capture: normalize_opend_shared_frame(
                capture, dataset="dot_plot", semantic_prefix="moomoo_dot_plot",
                method="get_fed_watch_dot_plot", limit=20,
            ))
    if time.monotonic() > deadline:
        _append_result(outputs, _failure(
            "moomoo_sg", "economic_calendar", "MOOMOO_SHARED_TIME_BUDGET_EXHAUSTED",
        ))
    else:
        try:
            page_gaps = []
            for window_start, window_end, page_limit in (
                ((anchor - timedelta(days=30)).isoformat(), anchor.isoformat(), 2),
                ((anchor + timedelta(days=1)).isoformat(), calendar_end, 1),
            ):
                captures, window_gaps = _read_quote_pages(
                    client, capability_id="economic-calendar-v1",
                    params={"start": window_start, "end": window_end, "count": 100},
                    max_pages=page_limit,
                )
                page_gaps.extend(window_gaps)
                for capture in captures:
                    _append_result(outputs, _normalized_result("moomoo_sg", "economic_calendar",
                        normalize_opend_shared_frame(
                            capture, dataset="economic_calendar",
                            semantic_prefix="moomoo_economic_calendar",
                            method="get_economic_calendar", limit=100,
                        )))
            _finish_page_coverage(outputs, dataset="economic_calendar", page_gaps=page_gaps)
        except Exception as exc:
            _append_result(outputs, _failure("moomoo_sg", "economic_calendar",
                                             str(exc).split(":", 1)[0]))
    return outputs


def _sec_business_result(
    gate_facts: Sequence[Mapping[str, Any]], *, security_id: str,
) -> dict[str, Any]:
    candidates = [
        item for item in gate_facts
        if item.get("security_id") == security_id
        and item.get("kind") == "disclosure"
        and item.get("semantic_field") == "business"
    ]
    if not candidates:
        return _failure("sec", "business_segments", "SEC_BUSINESS_DISCLOSURE_UNAVAILABLE")
    parent = max(candidates, key=lambda item: (item["published_at"], item["evidence_id"]))
    metadata = parent.get("metadata", {})
    fact = build_supplement_fact(
        security_id=security_id, dataset="business_segments",
        semantic_field="sec_business_and_segment_candidate_text",
        value={
            "text": parent["value"], "form": metadata.get("form"),
            "accession": metadata.get("accession"), "section": "business",
            "raw_character_spans": metadata.get("raw_character_spans", []),
            "truncated": bool(metadata.get("truncated", False)),
            "claim_status": "QUALITATIVE_CANDIDATE_REQUIRES_EVIDENCE_REVIEW",
        },
        source_id=parent["source_id"], source_family="sec",
        source_locator=parent["source_locator"], source_version=parent["source_version"],
        as_of=parent["as_of"], published_at=parent["published_at"],
        retrieved_at=parent["retrieved_at"], raw_content_hash=parent["raw_content_hash"],
        limitations=[
            "SEC Item 1 业务原文候选；不等同于结构化分部收入表。",
            "需要研究层核实公司业务、客户与分部口径，不据此机械分类。",
        ],
    )
    return {
        "source": "sec", "dataset": "business_segments", "status": "PARTIAL",
        "failure_code": None, "evidence": [fact], "gaps": [],
        "limitations": ["当前为业务披露原文候选，未结构化重算分部。"],
    }


def _sec_guidance_result(
    gate_facts: Sequence[Mapping[str, Any]], *, security_id: str,
) -> dict[str, Any]:
    candidates = [
        item for item in gate_facts
        if item.get("security_id") == security_id
        and item.get("kind") == "disclosure"
        and item.get("semantic_field") in {"earnings_release", "management_discussion"}
    ]
    if not candidates:
        return _failure("sec", "earnings_guidance", "SEC_GUIDANCE_CANDIDATE_UNAVAILABLE")
    parent = max(candidates, key=lambda item: (item["published_at"], item["evidence_id"]))
    metadata = parent.get("metadata", {})
    disclosure = {
        "evidence_id": parent["evidence_id"], "section": parent["semantic_field"],
        "text": parent["value"], "source_id": parent["source_id"],
        "source_locator": parent["source_locator"], "as_of": parent["as_of"],
        "published_at": parent["published_at"], "retrieved_at": parent["retrieved_at"],
        "raw_content_hash": parent["raw_content_hash"], "form": metadata.get("form"),
        "accession": metadata.get("accession"),
        "raw_character_spans": metadata.get("raw_character_spans", []),
        "truncated": bool(metadata.get("truncated", False)),
        "parser_version": metadata.get("parser_version", parent["source_version"]),
    }
    normalized = normalize_sec_guidance_candidate(disclosure, security_id=security_id)
    return {
        "source": "sec", "dataset": "earnings_guidance", "status": "PARTIAL",
        "failure_code": None, "evidence": normalized["evidence"],
        "gaps": normalized["gaps"],
        "limitations": ["仅冻结指引候选文本，是否构成明确指引由研究层判断。"],
    }


def build_research_supplements(
    positions: Sequence[Mapping[str, Any]], *, gate: Mapping[str, Any],
    external_results: Mapping[str, Sequence[Mapping[str, Any]]], run_id: str,
) -> list[dict[str, Any]]:
    """用基础 Gate 中的 SEC 事实与预采集结果生成逐证券冻结包。"""

    cutoff = str(gate["decision_cutoff"])
    gate_facts = list(gate.get("allowed_evidence", []))
    outputs = []
    for position in positions:
        security_id, ticker = str(position["security_id"]), str(position["ticker"])
        dataset_results = [dict(item) for item in external_results.get(security_id, [])]
        financial = normalize_sec_financial_history(gate_facts, security_id=security_id)
        dataset_results.extend([
            _failure("sec", "identity_profile", "SEC_IDENTITY_MAPPING_NOT_EXPORTED"),
            _sec_business_result(gate_facts, security_id=security_id),
            _failure("sec", "management_governance", "SEC_GOVERNANCE_NOT_COLLECTED"),
            _failure("sec", "relationships", "SEC_RELATIONSHIPS_NOT_COLLECTED"),
            {
                "source": "sec", "dataset": "financial_history",
                "status": "PARTIAL" if financial["gaps"] else "AVAILABLE",
                "failure_code": None if financial["evidence"] else "SEC_FINANCIAL_HISTORY_EMPTY",
                "evidence": financial["evidence"], "gaps": financial["gaps"],
                "limitations": [],
            } if financial["evidence"] else _failure(
                "sec", "financial_history", "SEC_FINANCIAL_HISTORY_EMPTY"
            ),
            _failure("sec", "capital_allocation", "SEC_CAPITAL_ALLOCATION_NOT_STRUCTURED"),
            _sec_guidance_result(gate_facts, security_id=security_id),
            _failure("sec", "event_context", "SEC_EVENT_CONTEXT_NOT_STRUCTURED"),
            _failure("sec", "institutional_ownership", "SEC_13F_ISSUER_AGGREGATE_UNAVAILABLE"),
        ])
        batch_id = f"research-supplement:{run_id}:{ticker}"
        assembled = assemble_company_background(
            snapshot_id=f"company-background:{run_id}:{ticker}", batch_id=batch_id,
            security_id=security_id, ticker=ticker, decision_cutoff=cutoff,
            created_at=cutoff, dataset_results=[
                {key: item[key] for key in (
                    "source", "dataset", "status", "failure_code", "evidence", "gaps", "limitations"
                )}
                for item in dataset_results
            ],
        )
        all_facts = assembled["background"]["evidence"] + assembled["extra_evidence"]
        capabilities = []
        for item in dataset_results:
            facts = [
                fact for fact in all_facts
                if fact["source_family"] == item["source"] and fact["dataset"] == item["dataset"]
            ]
            limitations = [str(value) for value in item["limitations"]]
            limitations.extend(
                json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, Mapping) else str(value)
                for value in item["gaps"]
            )
            if item["status"] not in {"NOT_ATTEMPTED", "AVAILABLE"} and not limitations:
                limitations.append(item["failure_code"] or "来源覆盖不完整")
            request_count = int(item.get("actual_requests", 0))
            if item["source"] == "moomoo_public_news":
                request_count = 2
            elif item["source"] == "sec":
                request_count = 0  # SEC facts were acquired in the base snapshot.
            capabilities.append(build_capability(
                source=item["source"],
                region="SG" if item["source"] == "moomoo_sg" else "US",
                security_id=security_id, dataset=item["dataset"], status=item["status"],
                fields=[fact["semantic_field"] for fact in facts],
                endpoint_version=facts[0]["source_version"] if facts else None,
                checked_at=cutoff,
                as_of=max((fact["as_of"] for fact in facts), default=cutoff),
                attempt_count=max(1, request_count), limitations=limitations,
                failure_code=item["failure_code"],
                evidence_ids=[fact["evidence_id"] for fact in facts],
                raw_content_hashes=[fact["raw_content_hash"] for fact in facts],
                request_budget=max(1, request_count), actual_requests=request_count,
            ))
        batch = build_capture_batch(
            batch_id=batch_id, security_id=security_id, decision_cutoff=cutoff,
            created_at=cutoff, capabilities=capabilities,
            source_selections=assembled["source_selections"],
        )
        package = build_research_supplement_package(
            batch=batch, background=assembled["background"],
            extra_evidence=assembled["extra_evidence"],
        )
        outputs.append({
            "security_id": security_id, "ticker": ticker,
            "background": assembled["background"], "batch": batch, "package": package,
        })
    return outputs
