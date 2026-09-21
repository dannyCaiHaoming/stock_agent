"""SEC、Yahoo 与 Moomoo SG 个股背景补充包的有界采集与装配。"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
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
        return _failure(source, dataset, code)
    return {
        "source": source, "dataset": dataset,
        "status": "PARTIAL" if gaps else "AVAILABLE",
        "failure_code": None, "evidence": evidence, "gaps": gaps,
        "limitations": [],
    }


def _append_result(target: list[dict[str, Any]], item: Mapping[str, Any]) -> None:
    """同一来源/数据集的有界多方法结果合并为一个 capability 记录。"""
    existing = next((value for value in target if value["source"] == item["source"]
                     and value["dataset"] == item["dataset"]), None)
    if existing is None:
        target.append(dict(item))
        return
    existing["evidence"].extend(dict(value) for value in item["evidence"])
    existing["gaps"].extend(item["gaps"])
    existing["limitations"].extend(str(value) for value in item["limitations"])
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


def capture_external_research_results(
    positions: Sequence[Mapping[str, Any]], *, access: Sequence[Mapping[str, Any]],
    cache_root: Path, state_root: Path,
    held_option_contracts: Mapping[str, Sequence[str]] | None = None,
    now: Callable[[], str] = _now,
) -> dict[str, list[dict[str, Any]]]:
    """先于共同 cutoff 采集 Yahoo/OpenD；任一来源失败只降级对应数据集。"""

    from product.mcp.live.cache import SnapshotCache

    result = {str(item["security_id"]): [] for item in positions}
    cache = SnapshotCache(cache_root)
    policies = {str(item["provider"]): item for item in access}
    tickers = [str(item["ticker"]) for item in positions]
    yahoo_datasets = (
        "identity_profile", "event_context", "analyst_expectations",
        "share_short_context", "capital_allocation",
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
                result[security_id].append(_failure("yahoo", "options_snapshot", code))
    except Exception as exc:
        code = str(exc).split(":", 1)[0] or "YAHOO_RESEARCH_CONFIGURATION_FAILED"
        for position in positions:
            result[str(position["security_id"])].extend(
                _failure("yahoo", dataset, code) for dataset in yahoo_datasets
            )
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
            for dataset in sorted({item[0] for item in calls} | {
                "options_snapshot", "options_underlying_context", "share_short_context",
            }):
                _append_result(result[security_id], _failure("moomoo_sg", dataset, code))
            continue
        for dataset, capability, extra_params, normalizer in core_calls:
            try:
                capture = client.read(
                    capability_id=capability,
                    params={"code": f"US.{ticker}", **extra_params},
                )
                normalized = normalizer(capture, security_id=security_id, ticker=ticker)
                _append_result(
                    result[security_id], _normalized_result("moomoo_sg", dataset, normalized),
                )
            except Exception as exc:
                code = str(exc).split(":", 1)[0] or "MOOMOO_RESEARCH_FAILED"
                _append_result(result[security_id], _failure("moomoo_sg", dataset, code))
        yahoo_options = next(
            (item for item in result[security_id]
             if item["source"] == "yahoo" and item["dataset"] == "options_snapshot"), None,
        )
        needs_moomoo_options = (
            yahoo_options is None
            or yahoo_options["status"] not in {"AVAILABLE", "PARTIAL"}
        )
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
                capture = client.read(
                    capability_id=capability,
                    params={"code": f"US.{ticker}", **extra_params},
                )
                normalized = normalizer(capture, security_id=security_id, ticker=ticker)
                _append_result(result[security_id], _normalized_result(
                    "moomoo_sg", dataset, normalized,
                ))
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
                normalized = normalize_opend_option_underlying(
                    client.read(capability_id=capability, params=params),
                    security_id=security_id, ticker=ticker,
                )
                _append_result(result[security_id], _normalized_result(
                    "moomoo_sg", "options_underlying_context", normalized,
                ))
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
    collect("economic_calendar", "economic-calendar-v1", {
        "start": (anchor - timedelta(days=7)).isoformat(), "end": calendar_end, "count": 100,
    }, lambda capture: normalize_opend_shared_frame(
        capture, dataset="economic_calendar", semantic_prefix="moomoo_economic_calendar",
        method="get_economic_calendar", limit=100,
    ))
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
            created_at=cutoff, dataset_results=dataset_results,
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
            capabilities.append(build_capability(
                source=item["source"],
                region="SG" if item["source"] == "moomoo_sg" else "US",
                security_id=security_id, dataset=item["dataset"], status=item["status"],
                fields=[fact["semantic_field"] for fact in facts],
                endpoint_version=facts[0]["source_version"] if facts else None,
                checked_at=cutoff,
                as_of=max((fact["as_of"] for fact in facts), default=cutoff),
                attempt_count=1, limitations=limitations,
                failure_code=item["failure_code"],
                evidence_ids=[fact["evidence_id"] for fact in facts],
                raw_content_hashes=[fact["raw_content_hash"] for fact in facts],
                request_budget=1, actual_requests=1,
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
