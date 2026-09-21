"""SEC/Yahoo/Moomoo SG 研究补充层的确定性契约与路由。

本模块刻意不修改 ``live-snapshot/4.0.0`` 的四源基础契约。补充事实先冻结为
独立 sidecar，再由 Runtime Evidence Gate 的显式接缝合入。这里不做投资判断，
也不在数据源之间静默拼接或把缺配置误报为来源受限。
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from product.mcp.provenance import content_hash, iso_utc, parse_timestamp
from product.runtime.schema_validation import validate_schema_instance


SCHEMAS = Path(__file__).resolve().parents[2] / "schemas" / "runtime"
SOURCE_PLAN_VERSION = "research-supplement-source-plan/1.0.0"
CAPABILITY_VERSION = "research-source-capability/1.2.0"
BATCH_VERSION = "research-capture-batch/1.1.0"
FACT_VERSION = "research-supplement-fact/1.1.0"
BACKGROUND_VERSION = "company-background-snapshot/1.0.0"

SOURCES = ("sec", "yahoo", "moomoo_sg")
CAPABILITY_STATUSES = {
    "NOT_ATTEMPTED", "AVAILABLE", "PARTIAL", "SOURCE_LIMITED",
    "BLOCKED_CONFIGURATION", "FAILED", "UNSUPPORTED",
    "OPEND_UNREACHABLE", "QUOTE_NOT_LOGGED_IN", "OPEND_VERSION_UNSUPPORTED",
    "SDK_VERSION_UNSUPPORTED", "ENTITLEMENT_REQUIRED", "RATE_LIMITED",
    "API_UNAVAILABLE", "CONTRACT_MISMATCH", "BLOCKED_BY_POLICY",
}
FALLBACK_ELIGIBLE_STATUSES = CAPABILITY_STATUSES - {"NOT_ATTEMPTED", "AVAILABLE", "PARTIAL"}
BACKGROUND_GROUPS = (
    "identity_profile",
    "business_segments",
    "management_governance",
    "relationships",
    "financial_history",
    "capital_allocation",
    "earnings_guidance",
    "analyst_expectations",
    "event_context",
    "share_short_context",
)
SHARED_MARKET_DATASETS = {
    "macro_history", "economic_calendar", "fedwatch_expectations",
    "dot_plot", "market_breadth", "option_market_statistics",
}
BACKGROUND_STATUSES = {
    "COVERED", "PARTIAL", "UNKNOWN", "NOT_ATTEMPTED",
    "SOURCE_LIMITED", "BLOCKED_CONFIGURATION",
}
SOURCE_TYPES = {
    "PRIMARY_DISCLOSURE", "MARKET_VENDOR", "SECONDARY_VENDOR",
    "VENDOR_CALCULATED_FLOW",
}


def load_source_plan(path: str | Path | None = None) -> dict[str, Any]:
    plan_path = Path(path) if path is not None else Path(__file__).with_name(
        "research-supplement-source-plan.json"
    )
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    validate_source_plan(plan)
    return plan


def validate_source_plan(plan: Mapping[str, Any]) -> None:
    if plan.get("schema_version") != SOURCE_PLAN_VERSION:
        raise ValueError("RESEARCH_SOURCE_PLAN_VERSION_INVALID")
    routes = plan.get("datasets")
    if not isinstance(routes, list) or not routes:
        raise ValueError("RESEARCH_SOURCE_PLAN_EMPTY")
    dataset_ids: set[str] = set()
    for route in routes:
        if not isinstance(route, Mapping):
            raise ValueError("RESEARCH_SOURCE_ROUTE_INVALID")
        dataset = route.get("dataset")
        primary = route.get("primary")
        fallback = route.get("fallback")
        supplemental = route.get("supplemental_sources")
        if not isinstance(dataset, str) or not dataset or dataset in dataset_ids:
            raise ValueError("RESEARCH_SOURCE_DATASET_INVALID")
        dataset_ids.add(dataset)
        if primary not in SOURCES:
            raise ValueError("RESEARCH_SOURCE_PRIMARY_INVALID")
        if fallback is not None and (fallback not in SOURCES or fallback == primary):
            raise ValueError("RESEARCH_SOURCE_FALLBACK_INVALID")
        if not isinstance(supplemental, list) or any(
            source not in SOURCES or source in {primary, fallback} for source in supplemental
        ) or len(set(supplemental)) != len(supplemental):
            raise ValueError("RESEARCH_SOURCE_SUPPLEMENTAL_INVALID")
        if route.get("max_fallback_attempts") not in (0, 1):
            raise ValueError("RESEARCH_SOURCE_FALLBACK_BUDGET_INVALID")
        if (fallback is None) != (route.get("max_fallback_attempts") == 0):
            raise ValueError("RESEARCH_SOURCE_FALLBACK_BUDGET_MISMATCH")
        if dataset == "vendor_money_flow" and (
            primary != "moomoo_sg" or fallback is not None or supplemental
        ):
            raise ValueError("RESEARCH_MONEY_FLOW_FALLBACK_FORBIDDEN")


def select_dataset_source(
    plan: Mapping[str, Any], *, dataset: str, attempts: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """依据冻结路由选择单一来源；补充源不会成为隐式 fallback。"""

    validate_source_plan(plan)
    route = next((item for item in plan["datasets"] if item["dataset"] == dataset), None)
    if route is None:
        raise ValueError("RESEARCH_DATASET_UNKNOWN")
    permitted = [route["primary"]] + ([route["fallback"]] if route["fallback"] else [])
    if not 1 <= len(attempts) <= len(permitted):
        raise ValueError("RESEARCH_SOURCE_ATTEMPT_COUNT_INVALID")
    if [item.get("source") for item in attempts] != permitted[:len(attempts)]:
        raise ValueError("RESEARCH_SOURCE_ATTEMPT_ORDER_INVALID")
    for index, attempt in enumerate(attempts):
        status = attempt.get("status")
        if status not in CAPABILITY_STATUSES:
            raise ValueError("RESEARCH_SOURCE_ATTEMPT_STATUS_INVALID")
        if index and attempts[index - 1].get("status") not in FALLBACK_ELIGIBLE_STATUSES:
            raise ValueError("RESEARCH_SOURCE_FALLBACK_FORBIDDEN")
    succeeded = [item for item in attempts if item["status"] in {"AVAILABLE", "PARTIAL"}]
    if len(succeeded) > 1:
        raise ValueError("RESEARCH_SOURCE_SELECTION_AMBIGUOUS")
    selected = succeeded[0]["source"] if succeeded else None
    return {
        "dataset": dataset,
        "selected_source": selected,
        "status": "SELECTED" if selected else attempts[-1]["status"],
        "attempts": deepcopy(attempts),
    }


def _validate_schema(filename: str, value: Mapping[str, Any]) -> None:
    schema = json.loads((SCHEMAS / filename).read_text(encoding="utf-8"))
    validate_schema_instance(value, schema)


def validate_capability(value: Mapping[str, Any]) -> None:
    _validate_schema("research-source-capability.schema.json", value)
    if value["source"] not in SOURCES or value["status"] not in CAPABILITY_STATUSES:
        raise ValueError("RESEARCH_CAPABILITY_ENUM_INVALID")
    for field in ("checked_at", "as_of"):
        parse_timestamp(value[field])
    if parse_timestamp(value["as_of"]) > parse_timestamp(value["checked_at"]):
        raise ValueError("RESEARCH_CAPABILITY_TIME_INVALID")
    if value["status"] == "NOT_ATTEMPTED" and value["attempt_count"] != 0:
        raise ValueError("RESEARCH_CAPABILITY_NOT_ATTEMPTED_INVALID")
    if value["status"] != "NOT_ATTEMPTED" and value["attempt_count"] < 1:
        raise ValueError("RESEARCH_CAPABILITY_ATTEMPT_MISSING")
    if value["actual_requests"] > value["request_budget"]:
        raise ValueError("RESEARCH_CAPABILITY_REQUEST_BUDGET_INVALID")
    if value["status"] in {"AVAILABLE", "PARTIAL"} and (
        not value["evidence_ids"] or not value["raw_content_hashes"]
    ):
        raise ValueError("RESEARCH_CAPABILITY_SUCCESS_EVIDENCE_MISSING")
    if value["status"] not in {"NOT_ATTEMPTED", "AVAILABLE"} and not value["limitations"]:
        raise ValueError("RESEARCH_CAPABILITY_LIMITATION_MISSING")
    expected = content_hash({key: item for key, item in value.items() if key != "capability_hash"})
    if value["capability_hash"] != expected:
        raise ValueError("RESEARCH_CAPABILITY_HASH_MISMATCH")


def build_capability(
    *, source: str, region: str, security_id: str, dataset: str,
    status: str, fields: list[str], endpoint_version: str | None,
    checked_at: str, as_of: str, attempt_count: int,
    limitations: list[str], failure_code: str | None = None,
    evidence_ids: list[str] | None = None,
    raw_content_hashes: list[str] | None = None,
    request_budget: int | None = None, actual_requests: int | None = None,
) -> dict[str, Any]:
    actual = attempt_count if actual_requests is None else actual_requests
    budget = max(attempt_count, actual) if request_budget is None else request_budget
    value = {
        "schema_version": CAPABILITY_VERSION,
        "source": source,
        "region": region,
        "security_id": security_id,
        "dataset": dataset,
        "status": status,
        "fields": sorted(set(fields)),
        "endpoint_version": endpoint_version,
        "checked_at": iso_utc(checked_at),
        "as_of": iso_utc(as_of),
        "attempt_count": attempt_count,
        "request_budget": budget,
        "actual_requests": actual,
        "evidence_ids": sorted(set(evidence_ids or [])),
        "raw_content_hashes": sorted(set(raw_content_hashes or [])),
        "limitations": list(limitations),
        "failure_code": failure_code,
    }
    value["capability_hash"] = content_hash(value)
    validate_capability(value)
    return value


def validate_capture_batch(value: Mapping[str, Any]) -> None:
    _validate_schema("research-capture-batch.schema.json", value)
    parse_timestamp(value["decision_cutoff"])
    parse_timestamp(value["created_at"])
    if parse_timestamp(value["created_at"]) < parse_timestamp(value["decision_cutoff"]):
        raise ValueError("RESEARCH_BATCH_TIME_INVALID")
    seen: set[tuple[str, str]] = set()
    for capability in value["capabilities"]:
        validate_capability(capability)
        key = (capability["source"], capability["dataset"])
        if key in seen:
            raise ValueError("RESEARCH_BATCH_CAPABILITY_DUPLICATE")
        seen.add(key)
        if capability["security_id"] != value["security_id"]:
            raise ValueError("RESEARCH_BATCH_SECURITY_MISMATCH")
        if parse_timestamp(capability["checked_at"]) > parse_timestamp(value["created_at"]):
            raise ValueError("RESEARCH_BATCH_FUTURE_CAPABILITY")
    routes = {item["dataset"]: item for item in load_source_plan()["datasets"]}
    selection_keys = set()
    attempt_keys = set()
    for selection in value["source_selections"]:
        required = {
            "dataset", "primary", "fallback", "selected_source", "fallback_reason",
            "supplemental_sources_used", "attempts",
        }
        if set(selection) != required or selection["dataset"] in selection_keys:
            raise ValueError("RESEARCH_BATCH_SELECTION_INVALID")
        selection_keys.add(selection["dataset"])
        route = routes.get(selection["dataset"])
        if route is None or selection["primary"] != route["primary"] \
                or selection["fallback"] != route["fallback"]:
            raise ValueError("RESEARCH_BATCH_SELECTION_ROUTE_MISMATCH")
        ordered_sources = [route["primary"]]
        if route["fallback"] is not None:
            ordered_sources.append(route["fallback"])
        ordered_sources.extend(route["supplemental_sources"])
        attempt_sources = [attempt.get("source") for attempt in selection["attempts"]]
        if attempt_sources != [source for source in ordered_sources if source in attempt_sources]:
            raise ValueError("RESEARCH_BATCH_SELECTION_ATTEMPT_ORDER_INVALID")
        attempts_by_source = {
            attempt["source"]: attempt for attempt in selection["attempts"]
        }
        primary = attempts_by_source.get(route["primary"])
        fallback = attempts_by_source.get(route["fallback"]) if route["fallback"] else None
        if fallback is not None and (
            primary is None or primary["status"] in {"AVAILABLE", "PARTIAL"}
        ):
            raise ValueError("RESEARCH_BATCH_SELECTION_FALLBACK_FORBIDDEN")
        expected_selected = None
        expected_reason = None
        if primary is not None and primary["status"] in {"AVAILABLE", "PARTIAL"}:
            expected_selected = route["primary"]
        elif fallback is not None and fallback["status"] in {"AVAILABLE", "PARTIAL"}:
            expected_selected = route["fallback"]
            expected_reason = primary.get("failure_code") or primary["status"]
        expected_supplements = sorted(
            source for source in route["supplemental_sources"]
            if source in attempts_by_source
            and attempts_by_source[source]["status"] in {"AVAILABLE", "PARTIAL"}
        )
        if selection["selected_source"] != expected_selected \
                or selection["fallback_reason"] != expected_reason \
                or selection["supplemental_sources_used"] != expected_supplements:
            raise ValueError("RESEARCH_BATCH_SELECTION_DECISION_MISMATCH")
        for attempt in selection["attempts"]:
            if set(attempt) != {"source", "status", "failure_code"}:
                raise ValueError("RESEARCH_BATCH_SELECTION_ATTEMPT_INVALID")
            key = (attempt["source"], selection["dataset"])
            if key in attempt_keys or key not in seen:
                raise ValueError("RESEARCH_BATCH_SELECTION_CAPABILITY_MISMATCH")
            capability = next(
                item for item in value["capabilities"]
                if (item["source"], item["dataset"]) == key
            )
            if capability["status"] != attempt["status"] \
                    or capability["failure_code"] != attempt["failure_code"]:
                raise ValueError("RESEARCH_BATCH_SELECTION_STATUS_MISMATCH")
            attempt_keys.add(key)
    if attempt_keys != seen:
        raise ValueError("RESEARCH_BATCH_SELECTION_COVERAGE_MISMATCH")
    expected = content_hash({key: item for key, item in value.items() if key != "batch_hash"})
    if value["batch_hash"] != expected:
        raise ValueError("RESEARCH_BATCH_HASH_MISMATCH")


def build_capture_batch(
    *, batch_id: str, security_id: str, decision_cutoff: str,
    created_at: str, capabilities: list[Mapping[str, Any]],
    source_selections: list[Mapping[str, Any]],
) -> dict[str, Any]:
    value = {
        "schema_version": BATCH_VERSION,
        "batch_id": batch_id,
        "security_id": security_id,
        "decision_cutoff": iso_utc(decision_cutoff),
        "created_at": iso_utc(created_at),
        "capabilities": [deepcopy(dict(item)) for item in capabilities],
        "source_selections": [deepcopy(dict(item)) for item in source_selections],
    }
    value["batch_hash"] = content_hash(value)
    validate_capture_batch(value)
    return value


def validate_supplement_fact(fact: Mapping[str, Any]) -> None:
    required = {
        "schema_version", "evidence_id", "security_id", "dataset", "semantic_field",
        "value", "source_id", "source_family", "source_type", "source_locator", "source_version",
        "batch_id",
        "as_of", "published_at", "retrieved_at", "raw_content_hash", "limitations",
    }
    if set(fact) != required or fact.get("schema_version") != FACT_VERSION:
        raise ValueError("RESEARCH_SUPPLEMENT_FACT_SHAPE_INVALID")
    if fact["source_family"] not in SOURCES:
        raise ValueError("RESEARCH_SUPPLEMENT_FACT_SOURCE_INVALID")
    if fact["source_type"] not in SOURCE_TYPES:
        raise ValueError("RESEARCH_SUPPLEMENT_FACT_SOURCE_TYPE_INVALID")
    if fact["source_family"] == "moomoo_sg" \
            and fact["source_locator"].startswith("moomoo-opend://") \
            and not re.search(
        r";opend/[0-9][^;]*;sdk/[^;]+;method/[^;]+;manifest/[0-9a-f]+$",
        fact["source_version"],
    ):
        raise ValueError("RESEARCH_SUPPLEMENT_MOOMOO_VERSION_INVALID")
    if not all(isinstance(fact[key], str) and fact[key] for key in required - {"value", "limitations"}):
        raise ValueError("RESEARCH_SUPPLEMENT_FACT_FIELD_INVALID")
    if not isinstance(fact["limitations"], list) or any(
        not isinstance(item, str) or not item for item in fact["limitations"]
    ):
        raise ValueError("RESEARCH_SUPPLEMENT_FACT_LIMITATION_INVALID")
    if len(fact["raw_content_hash"]) != 64 or any(c not in "0123456789abcdef" for c in fact["raw_content_hash"]):
        raise ValueError("RESEARCH_SUPPLEMENT_FACT_RAW_HASH_INVALID")
    as_of = parse_timestamp(fact["as_of"])
    published = parse_timestamp(fact["published_at"])
    retrieved = parse_timestamp(fact["retrieved_at"])
    if max(as_of, published) > retrieved:
        raise ValueError("RESEARCH_SUPPLEMENT_FACT_TIME_INVALID")
    if fact["dataset"] == "vendor_money_flow":
        value = fact["value"]
        if not isinstance(value, Mapping) or not all(
            isinstance(value.get(field), str) and value[field]
            for field in ("period_start", "period_end")
        ):
            raise ValueError("RESEARCH_SUPPLEMENT_FLOW_INTERVAL_MISSING")
        period_start = parse_timestamp(value["period_start"])
        period_end = parse_timestamp(value["period_end"])
        if period_start > period_end or period_end > retrieved or as_of != period_end:
            raise ValueError("RESEARCH_SUPPLEMENT_FLOW_INTERVAL_TIME_INVALID")
        provider_valid_time = value.get("provider_valid_time")
        if provider_valid_time is not None and parse_timestamp(provider_valid_time) > retrieved:
            raise ValueError("RESEARCH_SUPPLEMENT_FLOW_PROVIDER_TIME_INVALID")


def build_supplement_fact(
    *, security_id: str, dataset: str, semantic_field: str, value: Any,
    source_id: str, source_family: str, source_locator: str, source_version: str,
    as_of: str, published_at: str, retrieved_at: str, raw_content_hash: str,
    limitations: list[str] | None = None, batch_id: str = "UNBOUND",
) -> dict[str, Any]:
    source_type = (
        "PRIMARY_DISCLOSURE" if source_family == "sec" else
        "MARKET_VENDOR" if source_family == "yahoo" else
        "VENDOR_CALCULATED_FLOW" if dataset == "vendor_money_flow" else
        "SECONDARY_VENDOR"
    )
    fact = {
        "schema_version": FACT_VERSION,
        "evidence_id": "ev-research-supplement-" + content_hash({
            "security_id": security_id, "dataset": dataset, "semantic_field": semantic_field,
            "source_id": source_id, "batch_id": batch_id,
            "as_of": iso_utc(as_of), "raw_content_hash": raw_content_hash,
        }),
        "security_id": security_id,
        "dataset": dataset,
        "semantic_field": semantic_field,
        "value": deepcopy(value),
        "source_id": source_id,
        "source_family": source_family,
        "source_type": source_type,
        "source_locator": source_locator,
        "source_version": source_version,
        "batch_id": batch_id,
        "as_of": iso_utc(as_of),
        "published_at": iso_utc(published_at),
        "retrieved_at": iso_utc(retrieved_at),
        "raw_content_hash": raw_content_hash,
        "limitations": list(limitations or []),
    }
    validate_supplement_fact(fact)
    return fact


def _bind_supplement_fact_to_batch(fact: Mapping[str, Any], batch_id: str) -> dict[str, Any]:
    bound = deepcopy(dict(fact))
    if bound.get("batch_id") not in {"UNBOUND", batch_id}:
        raise ValueError("RESEARCH_SUPPLEMENT_FACT_BATCH_MISMATCH")
    bound["batch_id"] = batch_id
    bound["evidence_id"] = "ev-research-supplement-" + content_hash({
        "security_id": bound["security_id"], "dataset": bound["dataset"],
        "semantic_field": bound["semantic_field"], "source_id": bound["source_id"],
        "batch_id": batch_id, "as_of": bound["as_of"],
        "raw_content_hash": bound["raw_content_hash"],
    })
    validate_supplement_fact(bound)
    return bound


def normalize_sec_company_profile(
    mapping: Mapping[str, Any], *, security_id: str,
) -> dict[str, Any]:
    """把 SEC ticker/exchange 当前映射转为背景事实；不冒充历史主体快照。"""
    required = {
        "cik", "ticker", "issuer_name", "exchange", "source_id", "source_locator",
        "as_of", "retrieved_at", "raw_content_hash", "identity_version",
    }
    if not required <= set(mapping) or mapping["exchange"] is None:
        raise ValueError("SEC_COMPANY_PROFILE_MAPPING_INVALID")
    fact = build_supplement_fact(
        security_id=security_id, dataset="identity_profile",
        semantic_field="sec_legal_identity",
        value={
            "legal_name": mapping["issuer_name"], "cik": str(mapping["cik"]),
            "ticker": mapping["ticker"], "exchange": mapping["exchange"],
            "classification_system": "SEC_EXCHANGE_MAPPING",
        },
        source_id=mapping["source_id"], source_family="sec",
        source_locator=mapping["source_locator"], source_version=mapping["identity_version"],
        as_of=mapping["as_of"], published_at=mapping["retrieved_at"],
        retrieved_at=mapping["retrieved_at"], raw_content_hash=mapping["raw_content_hash"],
        limitations=["SEC ticker map 为检索时当前映射，不是历史时点公司档案"],
    )
    return {"adapter_version": "sec-company-profile/1.0.0", "evidence": [fact], "gaps": []}


def normalize_sec_financial_history(
    facts: Sequence[Mapping[str, Any]], *, security_id: str, max_facts: int = 200,
) -> dict[str, Any]:
    """把已通过 live-fact 契约的 SEC 原始财务事实映射到背景 sidecar。

    调用方负责先使用 ``research_financials`` 做字段与期间选择。本函数不重算、
    不合并不同 accession，也不把派生比较值伪装成 SEC 原始事实。
    """
    if not isinstance(max_facts, int) or not 1 <= max_facts <= 500:
        raise ValueError("SEC_FINANCIAL_HISTORY_BUDGET_INVALID")
    candidates = []
    for item in facts:
        required = {
            "evidence_id", "security_id", "semantic_field", "value", "unit",
            "source_id", "source_locator", "source_version", "as_of",
            "published_at", "retrieved_at", "raw_content_hash", "kind", "metadata",
        }
        if not isinstance(item, Mapping) or not required <= set(item):
            raise ValueError("SEC_FINANCIAL_HISTORY_FACT_INVALID")
        if item["security_id"] != security_id or item["kind"] != "financial":
            continue
        metadata = item["metadata"]
        if not isinstance(metadata, Mapping) or metadata.get("taxonomy") != "us-gaap":
            raise ValueError("SEC_FINANCIAL_HISTORY_METADATA_INVALID")
        candidates.append(item)
    candidates.sort(key=lambda item: (
        str(item["metadata"].get("period_end", "")), item["published_at"], item["evidence_id"],
    ), reverse=True)
    selected = candidates[:max_facts]
    evidence = []
    for item in selected:
        metadata = item["metadata"]
        evidence.append(build_supplement_fact(
            security_id=security_id, dataset="financial_history",
            semantic_field="sec_financial_fact:" + content_hash({
                "parent_evidence_id": item["evidence_id"],
                "tag": metadata["tag"], "unit": item["unit"],
                "period_end": metadata["period_end"], "accession": metadata["accession"],
            })[:20],
            value={
                "taxonomy": metadata["taxonomy"], "tag": metadata["tag"],
                "amount": item["value"], "unit": item["unit"],
                "form": metadata["form"], "accession": metadata["accession"],
                "period_start": metadata.get("period_start"),
                "period_end": metadata["period_end"],
                "context_type": metadata["context_type"],
                "fiscal_year": metadata.get("fiscal_year"),
                "fiscal_period": metadata.get("fiscal_period"),
                "parent_evidence_id": item["evidence_id"],
            },
            source_id=f"{item['source_id']}:{item['evidence_id']}", source_family="sec",
            source_locator=item["source_locator"], source_version=item["source_version"],
            as_of=item["as_of"], published_at=item["published_at"],
            retrieved_at=item["retrieved_at"], raw_content_hash=item["raw_content_hash"],
            limitations=[
                "SEC Company Facts 原始财务事实；不包含 XBRL dimension/member，不能替代分部披露",
                "不同 accession、重述和累计季度按原样分开保留，未在此层静默合并",
            ],
        ))
    gaps = []
    if not evidence:
        gaps.append({"reason": "SEC_FINANCIAL_HISTORY_EMPTY"})
    if len(candidates) > max_facts:
        gaps.append({
            "reason": "SEC_FINANCIAL_HISTORY_BUDGET_EXHAUSTED",
            "candidate_count": len(candidates), "emitted_count": len(evidence),
        })
    return {
        "adapter_version": "sec-financial-background/1.0.0",
        "evidence": sorted(evidence, key=lambda item: item["evidence_id"]),
        "gaps": gaps,
    }


def normalize_sec_guidance_candidate(
    disclosure: Mapping[str, Any], *, security_id: str,
) -> dict[str, Any]:
    """把冻结 SEC 原文变成指引候选；不把文本候选改写成实际值或预测。"""
    required = {
        "evidence_id", "section", "text", "source_id", "source_locator", "as_of",
        "published_at", "retrieved_at", "raw_content_hash", "form", "accession",
        "raw_character_spans", "truncated",
    }
    if not required <= set(disclosure) or disclosure["section"] not in {
        "earnings_release", "management_discussion",
    }:
        raise ValueError("SEC_GUIDANCE_DISCLOSURE_INVALID")
    fact = build_supplement_fact(
        security_id=security_id, dataset="earnings_guidance",
        semantic_field="sec_issuer_guidance_candidate_text",
        value={
            "text": disclosure["text"], "form": disclosure["form"],
            "accession": disclosure["accession"], "section": disclosure["section"],
            "raw_character_spans": disclosure["raw_character_spans"],
            "truncated": disclosure["truncated"],
            "claim_status": "CANDIDATE_REQUIRES_EVIDENCE_REVIEW",
        },
        source_id=disclosure["source_id"], source_family="sec",
        source_locator=disclosure["source_locator"],
        source_version=disclosure.get("parser_version", "sec-disclosure/unknown"),
        as_of=disclosure["as_of"], published_at=disclosure["published_at"],
        retrieved_at=disclosure["retrieved_at"], raw_content_hash=disclosure["raw_content_hash"],
        limitations=["发行人原文候选；需研究层引用核实预测期间、GAAP 口径和条件", "不得作为 SEC 实际业绩值"],
    )
    return {"adapter_version": "sec-guidance-candidate/1.0.0", "evidence": [fact], "gaps": []}


def compare_actual_to_expectation(
    *, actual: Mapping[str, Any], expectation: Mapping[str, Any], calculated_at: str,
) -> dict[str, Any]:
    """只在期间、指标、口径和 vintage 均明确时计算；非正基数不算百分比。"""
    from decimal import Decimal, InvalidOperation

    actual_value = actual.get("value")
    expected_value = expectation.get("value")
    if not isinstance(actual_value, Mapping) or not isinstance(expected_value, Mapping):
        raise ValueError("EXPECTATION_COMPARISON_VALUE_INVALID")
    keys = ("fiscal_period", "metric", "accounting_basis")
    if any(actual_value.get(key) != expected_value.get(key) for key in keys):
        raise ValueError("EXPECTATION_COMPARISON_BASIS_MISMATCH")
    vintage = expected_value.get("vintage_at")
    if not isinstance(vintage, str) or not vintage:
        raise ValueError("EXPECTATION_VINTAGE_UNKNOWN")
    if parse_timestamp(vintage) > parse_timestamp(actual["published_at"]):
        raise ValueError("EXPECTATION_VINTAGE_AFTER_ACTUAL")
    try:
        observed = Decimal(str(actual_value["amount"]))
        expected = Decimal(str(expected_value["average"]))
    except (KeyError, InvalidOperation) as exc:
        raise ValueError("EXPECTATION_COMPARISON_NUMBER_INVALID") from exc
    if not observed.is_finite() or not expected.is_finite():
        raise ValueError("EXPECTATION_COMPARISON_NUMBER_INVALID")
    delta = observed - expected
    percent = None if expected <= 0 else delta / expected * Decimal(100)
    result = {
        "schema_version": "actual-expectation-comparison/1.0.0",
        "security_id": actual["security_id"],
        "fiscal_period": actual_value["fiscal_period"],
        "metric": actual_value["metric"],
        "accounting_basis": actual_value["accounting_basis"],
        "actual": format(observed, "f"), "expectation": format(expected, "f"),
        "absolute_difference": format(delta, "f"),
        "percent_difference": format(percent, "f") if percent is not None else None,
        "percent_unavailable_reason": "NON_POSITIVE_EXPECTATION_BASE" if percent is None else None,
        "expectation_vintage_at": iso_utc(vintage),
        "actual_published_at": iso_utc(actual["published_at"]),
        "calculated_at": iso_utc(calculated_at),
        "parent_ids": [actual["evidence_id"], expectation["evidence_id"]],
    }
    result["calculation_hash"] = content_hash(result)
    return result


def validate_company_background_snapshot(value: Mapping[str, Any]) -> None:
    _validate_schema("company-background-snapshot.schema.json", value)
    cutoff = parse_timestamp(value["decision_cutoff"])
    created = parse_timestamp(value["created_at"])
    if created < cutoff:
        raise ValueError("COMPANY_BACKGROUND_TIME_INVALID")
    if set(value["groups"]) != set(BACKGROUND_GROUPS):
        raise ValueError("COMPANY_BACKGROUND_GROUP_SET_INVALID")
    evidence = value["evidence"]
    by_id: dict[str, Mapping[str, Any]] = {}
    for fact in evidence:
        validate_supplement_fact(fact)
        if fact["evidence_id"] in by_id:
            raise ValueError("COMPANY_BACKGROUND_EVIDENCE_DUPLICATE")
        if fact["security_id"] != value["security_id"]:
            raise ValueError("COMPANY_BACKGROUND_SECURITY_MISMATCH")
        if fact["batch_id"] != value["batch_id"]:
            raise ValueError("COMPANY_BACKGROUND_BATCH_MISMATCH")
        if max(
            parse_timestamp(fact["as_of"]), parse_timestamp(fact["published_at"]),
            parse_timestamp(fact["retrieved_at"]),
        ) > cutoff:
            raise ValueError("COMPANY_BACKGROUND_FUTURE_EVIDENCE")
        by_id[fact["evidence_id"]] = fact
    referenced: list[str] = []
    for name, group in value["groups"].items():
        if set(group) != {"status", "evidence_ids", "gaps", "limitations", "source_attempts"}:
            raise ValueError("COMPANY_BACKGROUND_GROUP_SHAPE_INVALID")
        identifiers = group["evidence_ids"]
        if group["status"] not in BACKGROUND_STATUSES:
            raise ValueError("COMPANY_BACKGROUND_GROUP_STATUS_INVALID")
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("COMPANY_BACKGROUND_GROUP_DUPLICATE_REFERENCE")
        for evidence_id in identifiers:
            fact = by_id.get(evidence_id)
            if fact is None:
                raise ValueError("COMPANY_BACKGROUND_DANGLING_REFERENCE")
            if fact["dataset"] != name:
                raise ValueError("COMPANY_BACKGROUND_DATASET_MISMATCH")
        if group["status"] == "COVERED" and not identifiers:
            raise ValueError("COMPANY_BACKGROUND_FALSE_COVERAGE")
        if group["status"] != "COVERED" and not group["gaps"] and not group["limitations"]:
            raise ValueError("COMPANY_BACKGROUND_GAP_UNEXPLAINED")
        attempts = group["source_attempts"]
        if not isinstance(attempts, list) or len({item.get("source") for item in attempts}) != len(attempts):
            raise ValueError("COMPANY_BACKGROUND_SOURCE_ATTEMPTS_INVALID")
        for attempt in attempts:
            if set(attempt) != {"source", "status", "failure_code"} \
                    or attempt["source"] not in SOURCES or attempt["status"] not in CAPABILITY_STATUSES:
                raise ValueError("COMPANY_BACKGROUND_SOURCE_ATTEMPT_INVALID")
        evidence_sources = {by_id[evidence_id]["source_family"] for evidence_id in identifiers}
        admitted_sources = {
            item["source"] for item in attempts if item["status"] in {"AVAILABLE", "PARTIAL"}
        }
        if evidence_sources != admitted_sources:
            raise ValueError("COMPANY_BACKGROUND_SOURCE_EVIDENCE_MISMATCH")
        referenced.extend(identifiers)
    if sorted(referenced) != sorted(by_id):
        raise ValueError("COMPANY_BACKGROUND_UNREFERENCED_EVIDENCE")
    expected_status = background_status(value["groups"])
    if value["status"] != expected_status:
        raise ValueError("COMPANY_BACKGROUND_STATUS_MISMATCH")
    expected_hash = content_hash({key: item for key, item in value.items() if key != "snapshot_hash"})
    if value["snapshot_hash"] != expected_hash:
        raise ValueError("COMPANY_BACKGROUND_HASH_MISMATCH")


def background_status(groups: Mapping[str, Mapping[str, Any]]) -> str:
    identity = groups.get("identity_profile", {})
    if identity.get("status") not in {"COVERED", "PARTIAL"} or not identity.get("evidence_ids"):
        return "INSUFFICIENT_EVIDENCE"
    statuses = {item.get("status") for item in groups.values()}
    return "FROZEN" if statuses == {"COVERED"} else "PARTIAL"


def build_company_background_snapshot(
    *, snapshot_id: str, batch_id: str, security_id: str, ticker: str,
    decision_cutoff: str, created_at: str, evidence: list[Mapping[str, Any]],
    groups: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    copied_evidence = [deepcopy(dict(item)) for item in evidence]
    source_by_id = {item["evidence_id"]: item["source_family"] for item in copied_evidence}
    normalized_groups = {
        name: {
            "status": groups[name]["status"],
            "evidence_ids": sorted(set(groups[name].get("evidence_ids", []))),
            "gaps": list(groups[name].get("gaps", [])),
            "limitations": list(groups[name].get("limitations", [])),
            "source_attempts": deepcopy(list(groups[name].get("source_attempts", (
                [
                    {"source": source, "status": "AVAILABLE", "failure_code": None}
                    for source in sorted({
                        source_by_id[evidence_id]
                        for evidence_id in groups[name].get("evidence_ids", [])
                        if evidence_id in source_by_id
                    })
                ]
                if groups[name].get("evidence_ids") else
                [
                    {"source": source, "status": "NOT_ATTEMPTED", "failure_code": None}
                    for source in SOURCES
                ]
            )))),
        }
        for name in BACKGROUND_GROUPS
    }
    value = {
        "schema_version": BACKGROUND_VERSION,
        "snapshot_id": snapshot_id,
        "batch_id": batch_id,
        "security_id": security_id,
        "ticker": ticker,
        "decision_cutoff": iso_utc(decision_cutoff),
        "created_at": iso_utc(created_at),
        "status": background_status(normalized_groups),
        "groups": normalized_groups,
        "evidence": sorted(copied_evidence, key=lambda item: item["evidence_id"]),
    }
    value["snapshot_hash"] = content_hash(value)
    validate_company_background_snapshot(value)
    return value


def _resolve_source_selections(
    dataset_results: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    routes = {item["dataset"]: item for item in load_source_plan()["datasets"]}
    results_by_dataset: dict[str, list[Mapping[str, Any]]] = {}
    for result in dataset_results:
        results_by_dataset.setdefault(str(result.get("dataset")), []).append(result)
    selections = []
    for dataset, results in sorted(results_by_dataset.items()):
        route = routes.get(dataset)
        if route is None:
            raise ValueError("COMPANY_BACKGROUND_DATASET_ROUTE_MISSING")
        by_source = {str(item.get("source")): item for item in results}
        if len(by_source) != len(results):
            raise ValueError("COMPANY_BACKGROUND_DATASET_RESULT_DUPLICATE")
        permitted = {route["primary"], *route["supplemental_sources"]}
        if route["fallback"] is not None:
            permitted.add(route["fallback"])
        if set(by_source) - permitted:
            raise ValueError("COMPANY_BACKGROUND_SOURCE_NOT_PERMITTED")
        primary = by_source.get(route["primary"])
        fallback = by_source.get(route["fallback"]) if route["fallback"] else None
        if fallback is not None and primary is None:
            raise ValueError("COMPANY_BACKGROUND_FALLBACK_WITHOUT_PRIMARY")
        if fallback is not None and primary["status"] in {"AVAILABLE", "PARTIAL"}:
            raise ValueError("COMPANY_BACKGROUND_FALLBACK_AFTER_SUCCESS")
        selected_source = None
        fallback_reason = None
        if primary is not None and primary["status"] in {"AVAILABLE", "PARTIAL"}:
            selected_source = route["primary"]
        elif fallback is not None and fallback["status"] in {"AVAILABLE", "PARTIAL"}:
            selected_source = route["fallback"]
            fallback_reason = primary.get("failure_code") or primary["status"]
        supplements = sorted(
            source for source in route["supplemental_sources"]
            if source in by_source and by_source[source]["status"] in {"AVAILABLE", "PARTIAL"}
        )
        admitted = set(supplements)
        if selected_source is not None:
            admitted.add(selected_source)
        for source, result in by_source.items():
            if result.get("evidence") and source not in admitted:
                raise ValueError("COMPANY_BACKGROUND_UNSELECTED_SOURCE_EVIDENCE")
        order = [route["primary"]]
        if route["fallback"] is not None:
            order.append(route["fallback"])
        order.extend(route["supplemental_sources"])
        selections.append({
            "dataset": dataset, "primary": route["primary"],
            "fallback": route["fallback"], "selected_source": selected_source,
            "fallback_reason": fallback_reason,
            "supplemental_sources_used": supplements,
            "attempts": [{
                "source": source, "status": by_source[source]["status"],
                "failure_code": by_source[source]["failure_code"],
            } for source in order if source in by_source],
        })
    return selections


def assemble_company_background(
    *, snapshot_id: str, batch_id: str, security_id: str, ticker: str,
    decision_cutoff: str, created_at: str,
    dataset_results: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """把各来源独立结果装配为十组背景；失败只影响对应数据集和来源。"""
    source_selections = _resolve_source_selections(dataset_results)
    groups = {
        name: {
            "status": "NOT_ATTEMPTED", "evidence_ids": [],
            "gaps": ["三源均未尝试"], "limitations": [], "source_attempts": [],
        }
        for name in BACKGROUND_GROUPS
    }
    evidence, extra_evidence, seen_results = [], [], set()
    for result in dataset_results:
        required = {"source", "dataset", "status", "failure_code", "evidence", "gaps", "limitations"}
        if not isinstance(result, Mapping) or set(result) != required:
            raise ValueError("COMPANY_BACKGROUND_DATASET_RESULT_INVALID")
        source, dataset, status = result["source"], result["dataset"], result["status"]
        if source not in SOURCES or status not in CAPABILITY_STATUSES:
            raise ValueError("COMPANY_BACKGROUND_DATASET_RESULT_STATUS_INVALID")
        if (source, dataset) in seen_results:
            raise ValueError("COMPANY_BACKGROUND_DATASET_RESULT_DUPLICATE")
        seen_results.add((source, dataset))
        facts = [
            _bind_supplement_fact_to_batch(item, batch_id)
            for item in result["evidence"]
        ]
        for fact in facts:
            validate_supplement_fact(fact)
            if fact["source_family"] != source or fact["dataset"] != dataset \
                    or fact["security_id"] not in (
                        {security_id, "US:MARKET"}
                        if dataset in SHARED_MARKET_DATASETS else {security_id}
                    ):
                raise ValueError("COMPANY_BACKGROUND_DATASET_RESULT_BINDING_INVALID")
        if status in {"AVAILABLE", "PARTIAL"} and not facts:
            raise ValueError("COMPANY_BACKGROUND_DATASET_FALSE_SUCCESS")
        if status not in {"AVAILABLE", "PARTIAL"} and facts:
            raise ValueError("COMPANY_BACKGROUND_DATASET_EVIDENCE_ON_FAILURE")
        if dataset not in groups:
            extra_evidence.extend(facts)
            continue
        group = groups[dataset]
        if group["gaps"] == ["三源均未尝试"]:
            group["gaps"] = []
        group["source_attempts"].append({
            "source": source, "status": status, "failure_code": result["failure_code"],
        })
        group["evidence_ids"].extend(item["evidence_id"] for item in facts)
        group["gaps"].extend(str(item) for item in result["gaps"])
        group["limitations"].extend(str(item) for item in result["limitations"])
        evidence.extend(facts)
    for group in groups.values():
        if not group["source_attempts"]:
            group["source_attempts"] = [
                {"source": source, "status": "NOT_ATTEMPTED", "failure_code": None}
                for source in SOURCES
            ]
        if group["evidence_ids"]:
            group["status"] = "COVERED" if not group["gaps"] and not group["limitations"] else "PARTIAL"
        elif group["source_attempts"]:
            statuses = {item["status"] for item in group["source_attempts"]}
            if "BLOCKED_CONFIGURATION" in statuses:
                group["status"] = "BLOCKED_CONFIGURATION"
            elif statuses == {"NOT_ATTEMPTED"}:
                group["status"] = "NOT_ATTEMPTED"
            elif statuses & {"SOURCE_LIMITED", "FAILED"}:
                group["status"] = "SOURCE_LIMITED"
            else:
                group["status"] = "UNKNOWN"
            if not group["gaps"] and not group["limitations"]:
                group["gaps"].append("来源未返回可验证 Evidence")
    snapshot = build_company_background_snapshot(
        snapshot_id=snapshot_id, batch_id=batch_id, security_id=security_id, ticker=ticker,
        decision_cutoff=decision_cutoff, created_at=created_at,
        evidence=evidence, groups=groups,
    )
    return {
        "background": snapshot, "extra_evidence": extra_evidence,
        "source_selections": source_selections,
    }


def build_research_supplement_package(
    *, batch: Mapping[str, Any], background: Mapping[str, Any],
    extra_evidence: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    validate_capture_batch(batch)
    validate_company_background_snapshot(background)
    if batch["batch_id"] != background["batch_id"] or batch["security_id"] != background["security_id"]:
        raise ValueError("RESEARCH_SUPPLEMENT_PACKAGE_BINDING_INVALID")
    extras = [deepcopy(dict(item)) for item in extra_evidence]
    identifiers = {item["evidence_id"] for item in background["evidence"]}
    for fact in extras:
        validate_supplement_fact(fact)
        if fact["security_id"] not in (
            {batch["security_id"], "US:MARKET"}
            if fact["dataset"] in SHARED_MARKET_DATASETS else {batch["security_id"]}
        ) \
                or fact["batch_id"] != batch["batch_id"] \
                or fact["evidence_id"] in identifiers:
            raise ValueError("RESEARCH_SUPPLEMENT_PACKAGE_EVIDENCE_INVALID")
        if max(
            parse_timestamp(fact["as_of"]), parse_timestamp(fact["published_at"]),
            parse_timestamp(fact["retrieved_at"]),
        ) > parse_timestamp(batch["decision_cutoff"]):
            raise ValueError("RESEARCH_SUPPLEMENT_PACKAGE_FUTURE_EVIDENCE")
        identifiers.add(fact["evidence_id"])
    value = {
        "schema_version": "research-supplement-package/1.0.0",
        "batch_id": batch["batch_id"], "batch_hash": batch["batch_hash"],
        "security_id": batch["security_id"], "decision_cutoff": batch["decision_cutoff"],
        "background_snapshot_id": background["snapshot_id"],
        "background_snapshot_hash": background["snapshot_hash"],
        "extra_evidence": sorted(extras, key=lambda item: item["evidence_id"]),
        "evidence_ids": sorted(identifiers),
    }
    value["package_hash"] = content_hash(value)
    validate_research_supplement_package(value, batch=batch, background=background)
    return value


def validate_research_supplement_package(
    value: Mapping[str, Any], *, batch: Mapping[str, Any], background: Mapping[str, Any],
) -> None:
    required = {
        "schema_version", "batch_id", "batch_hash", "security_id", "decision_cutoff",
        "background_snapshot_id", "background_snapshot_hash", "extra_evidence",
        "evidence_ids", "package_hash",
    }
    if set(value) != required or value.get("schema_version") != "research-supplement-package/1.0.0":
        raise ValueError("RESEARCH_SUPPLEMENT_PACKAGE_SHAPE_INVALID")
    validate_capture_batch(batch)
    validate_company_background_snapshot(background)
    if (
        value["batch_id"] != batch["batch_id"] or value["batch_hash"] != batch["batch_hash"]
        or value["security_id"] != batch["security_id"]
        or value["decision_cutoff"] != batch["decision_cutoff"]
        or background["decision_cutoff"] != batch["decision_cutoff"]
        or value["background_snapshot_id"] != background["snapshot_id"]
        or value["background_snapshot_hash"] != background["snapshot_hash"]
    ):
        raise ValueError("RESEARCH_SUPPLEMENT_PACKAGE_BINDING_INVALID")
    identifiers = {item["evidence_id"] for item in background["evidence"]}
    for fact in value["extra_evidence"]:
        validate_supplement_fact(fact)
        if fact["security_id"] not in (
            {value["security_id"], "US:MARKET"}
            if fact["dataset"] in SHARED_MARKET_DATASETS else {value["security_id"]}
        ) \
                or fact["batch_id"] != value["batch_id"] \
                or fact["evidence_id"] in identifiers:
            raise ValueError("RESEARCH_SUPPLEMENT_PACKAGE_EVIDENCE_INVALID")
        if max(
            parse_timestamp(fact["as_of"]), parse_timestamp(fact["published_at"]),
            parse_timestamp(fact["retrieved_at"]),
        ) > parse_timestamp(value["decision_cutoff"]):
            raise ValueError("RESEARCH_SUPPLEMENT_PACKAGE_FUTURE_EVIDENCE")
        identifiers.add(fact["evidence_id"])
    if value["evidence_ids"] != sorted(identifiers):
        raise ValueError("RESEARCH_SUPPLEMENT_PACKAGE_REFERENCE_MISMATCH")
    expected = content_hash({key: item for key, item in value.items() if key != "package_hash"})
    if value["package_hash"] != expected:
        raise ValueError("RESEARCH_SUPPLEMENT_PACKAGE_HASH_MISMATCH")


def render_company_background_markdown(snapshot: Mapping[str, Any]) -> str:
    """从同一冻结 JSON 生成中文覆盖视图，不产生新的事实。"""

    validate_company_background_snapshot(snapshot)
    labels = {
        "identity_profile": "身份与公司档案", "business_segments": "业务与分部",
        "management_governance": "管理层与治理", "relationships": "重要关系",
        "financial_history": "财务历史", "capital_allocation": "资本配置",
        "earnings_guidance": "业绩与指引", "analyst_expectations": "分析师预期",
        "event_context": "事件背景", "share_short_context": "股本与空头背景",
    }
    lines = [
        f"# {snapshot['ticker']} 个股背景资料",
        "",
        f"- 证券：`{snapshot['security_id']}`",
        f"- 截止时间：`{snapshot['decision_cutoff']}`",
        f"- 状态：`{snapshot['status']}`",
        f"- 批次：`{snapshot['batch_id']}`",
        "",
        "## 覆盖情况",
        "",
    ]
    for name in BACKGROUND_GROUPS:
        group = snapshot["groups"][name]
        lines.append(f"### {labels[name]}")
        lines.append("")
        lines.append(f"状态：`{group['status']}`；Evidence：{len(group['evidence_ids'])} 条。")
        if group["source_attempts"]:
            attempts = "、".join(
                f"{item['source']}={item['status']}" for item in group["source_attempts"]
            )
            lines.append("来源尝试：" + attempts)
        if group["gaps"]:
            lines.append("缺口：" + "；".join(group["gaps"]))
        if group["limitations"]:
            lines.append("限制：" + "；".join(group["limitations"]))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
