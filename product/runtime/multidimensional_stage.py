"""多维持仓研究阶段的冻结输入、显式任务和 Codex-native 派发接缝。"""

from __future__ import annotations

import copy
import json
import os
import re
import shutil
import subprocess
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.council import (
    build_independent_counter_thesis_research_request,
    build_multidimensional_holding_research_request,
)
from product.council.multidimensional_research import RESEARCH_CAPABILITIES
from product.intake.v3 import validate_handoff
from product.mcp.provenance import parse_timestamp
from product.runtime.hashing import canonical_hash, file_hash


STAGE_VERSION = "multidimensional-holding-research-runtime/2.0.0"
DISPATCH_VERSION = "multidimensional-research-dispatch/2.1.0"
COMPANY_AGENT_VERSION = "3.0.20"
MARKET_AGENT_VERSION = "1.2.0"
SCOPED_PROVIDER_VIEW_INSTRUCTION = (
    " 本任务 provider_coverage 是从完整审计派生的任务视图：global_coverage"
    " 的状态、计数和失败码属于 provider 全局，不能当作本任务数据集已交付或已引用。"
    "请按 dataset_observations 与 capability_routing 判断局部交付；"
    "NO_DATASET_DETAIL 表示原件无数据集明细，NO_RELEVANT_OBSERVATIONS 表示本任务未选中明细，"
    "两者均不能单独推断无 Evidence 或获取失败。coverage_hash 指向完整审计原件。"
)


def _parent_output_schema(run_id: str, task_count: int) -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object", "additionalProperties": False,
        "required": ["stage", "run_id", "dispatched", "completed"],
        "properties": {
            "stage": {"type": "string", "const": "MULTI_DIMENSIONAL_HOLDING_RESEARCH"},
            "run_id": {"type": "string", "const": run_id},
            "dispatched": {"type": "integer", "const": task_count},
            "completed": {"type": "integer", "const": task_count},
        },
    }

CAPABILITY_BINDINGS = {
    "TECHNICAL_STRUCTURE": ("runtime_market_catalyst", "technical-structure", "PER_SECURITY"),
    "FUNDAMENTAL_EVENT": ("runtime_company_analyst", "company-research", "PER_SECURITY"),
    "RESEARCH_REPORT": ("runtime_company_analyst", "research-report-analysis", "PER_SECURITY"),
    "INDUSTRY_COMPARISON": ("runtime_market_catalyst", "industry-comparison", "PER_SECURITY"),
    "MACRO_CONTEXT": ("runtime_market_catalyst", "macro-market-analysis", "SHARED_MARKET"),
    "MARKET_STATE": ("runtime_market_catalyst", "macro-market-analysis", "SHARED_MARKET"),
    "OWNERSHIP_DISCLOSURE": ("runtime_market_catalyst", "ownership-disclosure", "PER_SECURITY"),
    "OPTIONS_FLOW": ("runtime_market_catalyst", "options-market-structure", "PER_SECURITY"),
}

DATASET_CAPABILITY_ROUTES = {
    "FUNDAMENTAL_EVENT": {
        "identity_profile", "business_segments", "management_governance",
        "financial_history", "capital_allocation", "earnings_guidance", "event_context",
    },
    "RESEARCH_REPORT": {"analyst_expectations", "research_discovery"},
    "OWNERSHIP_DISCLOSURE": {
        "institutional_ownership", "insider_transactions", "share_short_context",
    },
    "MACRO_CONTEXT": {"macro_history", "economic_calendar", "dot_plot"},
    "MARKET_STATE": {
        "market_breadth", "option_market_statistics", "fedwatch_expectations",
    },
    "OPTIONS_FLOW": {
        "options_snapshot", "options_underlying_context", "vendor_money_flow",
    },
}

MINIMUM_QUESTIONS = {
    "TECHNICAL_STRUCTURE": ["趋势与关键价格结构是什么？", "相对广泛市场基准表现如何？", "波动、回撤和量价是否支持解释？", "什么观察信号会推翻解释？"],
    "FUNDAMENTAL_EVENT": ["核心经营驱动是什么？", "盈利与现金流是什么关系？", "估值依赖哪些显式假设？", "关键未知和已公告事件如何影响判断？"],
    "RESEARCH_REPORT": ["作者使用了哪些依据与假设？", "报告之间或与公司资料有哪些真实分歧？", "报告对已有研究主张是支持、挑战、修订还是无新增信息？"],
    "INDUSTRY_COMPARISON": ["公司相对同行处于什么位置？", "行业与公司因素如何区分？", "可比性限制和传导机制是什么？"],
    "MACRO_CONTEXT": ["利率、通胀、经济活动与政策事实是什么？", "观察期、发布时间与修订边界是什么？", "这些因素怎样分别传导到持仓，什么反向情景会推翻解释？"],
    "MARKET_STATE": ["大盘、相关板块、跨资产、波动与信用状态是什么？", "哪些指标是代理且有什么边界？", "市场状态怎样分别传导到持仓，什么反向情景会推翻解释？"],
    "OWNERSHIP_DISCLOSURE": ["实际披露发生了什么变化？", "交易类型、披露滞后和覆盖限制是什么？", "哪些内容不能从披露推断？"],
    "OPTIONS_FLOW": ["当前快照实际支持什么结构观察？", "时效、覆盖和直接/代理指标边界是什么？", "哪些资金方向结论不能成立？"],
}


class MultidimensionalStageError(ValueError):
    pass


def _read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MultidimensionalStageError(f"MULTIDIMENSIONAL_INPUT_INVALID:{Path(path).name}") from exc
    if not isinstance(value, Mapping):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_INPUT_NOT_OBJECT")
    return dict(value)


def _write_object(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        raise MultidimensionalStageError(f"MULTIDIMENSIONAL_OUTPUT_EXISTS:{path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _frozen_peer_candidates(task: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        dict(item) for item in task.get("selected_peer_candidates", [])
        if isinstance(item, Mapping)
        and item.get("materialization_status") == "FROZEN"
        and isinstance(item.get("materialized_security_id"), str)
    ]


def _skill_version(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    match = re.search(r'(?m)^  version:\s*["\']?([^"\'\n]+)', text)
    if not match:
        raise MultidimensionalStageError(f"MULTIDIMENSIONAL_SKILL_VERSION_MISSING:{path.parent.name}")
    return match.group(1).strip()


def _agent_binding(product_root: Path, name: str) -> dict[str, Any]:
    path = product_root / ".codex/agents" / f"{name}.toml"
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    if config.get("name") != name:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_AGENT_BINDING_INVALID")
    return {
        "name": name,
        "version": COMPANY_AGENT_VERSION if name == "runtime_company_analyst" else MARKET_AGENT_VERSION,
        "content_hash": file_hash(path),
    }


def _skill_binding(product_root: Path, name: str) -> dict[str, Any]:
    path = product_root / "skills" / name / "SKILL.md"
    return {"name": name, "version": _skill_version(path), "content_hash": file_hash(path)}


def _facts_for_capability(
    evidence: Sequence[Mapping[str, Any]], *, capability: str, security_ids: Sequence[str], benchmark_id: str | None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    scoped_ids = set(security_ids)
    if benchmark_id and capability == "TECHNICAL_STRUCTURE":
        scoped_ids.add(benchmark_id)
    for fact in evidence:
        field = str(fact.get("semantic_field", ""))
        dataset = str(fact.get("dataset", ""))
        source = str(fact.get("source_type", ""))
        source_family = str(fact.get("source_family", ""))
        metadata = fact.get("metadata") if isinstance(fact.get("metadata"), Mapping) else {}
        form = str(metadata.get("form", ""))
        security_id = fact.get("security_id")
        matches = False
        if capability == "TECHNICAL_STRUCTURE":
            matches = security_id in scoped_ids and field in {
                "open_price", "high_price", "low_price", "historical_close_price",
                "adjusted_close_price", "share_volume", "cash_dividend", "stock_split_ratio",
            }
        elif capability == "FUNDAMENTAL_EVENT":
            # `source_type` is optional on older normalized Evidence.  Preserve
            # provider-neutral compatibility while still limiting this mode to
            # SEC-originated facts.
            source_id = str(fact.get("source_id", "")).lower()
            matches = security_id in scoped_ids and (
                source == "sec" or "sec" in source_id
                or dataset in DATASET_CAPABILITY_ROUTES[capability]
            )
        elif capability == "RESEARCH_REPORT":
            matches = security_id in scoped_ids and (
                dataset in DATASET_CAPABILITY_ROUTES[capability]
                or
                source in {"public_research", "issuer_research"}
                or source_family in {"sec", "yahoo", "moomoo_sg"}
                and field in {
                    "sec_issuer_guidance_candidate_text", "yahoo_earnings_trend",
                    "yahoo_recommendation_trend", "moomoo_analyst_consensus",
                }
                or source == "sec" and field in {"earnings_release", "management_discussion"}
            )
        elif capability == "INDUSTRY_COMPARISON":
            matches = security_id in scoped_ids and (
                source in {"sec", "yahoo", "public_research"} or field.startswith("industry_")
            )
        elif capability == "MACRO_CONTEXT":
            matches = (security_id in {"MARKET", "US:MARKET"} and dataset in DATASET_CAPABILITY_ROUTES[capability]) or source in {
                "fred", "bls", "bea", "federal_reserve", "treasury"
            }
        elif capability == "MARKET_STATE":
            matches = (security_id in {"MARKET", "US:MARKET"} and dataset in DATASET_CAPABILITY_ROUTES[capability]) or source in {
                "yahoo", "market", "fred", "treasury", "eia"
            }
        elif capability == "OWNERSHIP_DISCLOSURE":
            matches = security_id in scoped_ids and (
                dataset in DATASET_CAPABILITY_ROUTES[capability]
                or form in {"3", "4", "5", "13F-HR", "13F-HR/A"}
                or field.startswith("ownership_")
            )
        elif capability == "OPTIONS_FLOW":
            matches = security_id in scoped_ids and (
                dataset in DATASET_CAPABILITY_ROUTES[capability]
                or source == "options" or field.startswith(("option_", "short_", "fund_flow_", "moomoo_option_"))
            )
        if matches:
            selected.append(copy.deepcopy(dict(fact)))
    return sorted(selected, key=lambda item: str(item.get("evidence_id")))


def _capability_routing_coverage(
    evidence: Sequence[Mapping[str, Any]], *, capture_batches: Sequence[Mapping[str, Any]],
    security_ids: Sequence[str], benchmark_id: str | None,
) -> dict[str, Any]:
    """审计本次启用的数据集是否真正进入目标专业任务。"""

    route_by_dataset = {
        dataset: capability
        for capability, datasets in DATASET_CAPABILITY_ROUTES.items()
        for dataset in datasets
    }
    captured: dict[str, set[str]] = {dataset: set() for dataset in route_by_dataset}
    for batch in capture_batches:
        for item in batch.get("capabilities", []):
            dataset = str(item.get("dataset", ""))
            if dataset not in captured:
                continue
            captured[dataset].update(
                str(value) for value in item.get("evidence_ids", [])
                if isinstance(value, str)
            )

    gate_by_dataset: dict[str, list[Mapping[str, Any]]] = {
        dataset: [] for dataset in route_by_dataset
    }
    for fact in evidence:
        dataset = str(fact.get("dataset", ""))
        if dataset in gate_by_dataset:
            gate_by_dataset[dataset].append(fact)

    delivered_by_capability: dict[str, set[str]] = {}
    for capability in DATASET_CAPABILITY_ROUTES:
        scoped = _facts_for_capability(
            evidence, capability=capability, security_ids=security_ids,
            benchmark_id=benchmark_id,
        )
        if capability == "MARKET_STATE":
            scoped = _bounded_latest_facts(scoped)
        delivered_by_capability[capability] = {
            str(item["evidence_id"]) for item in scoped
            if isinstance(item.get("evidence_id"), str)
        }

    observations = []
    failure_codes: list[str] = []
    for dataset in sorted(route_by_dataset):
        capability = route_by_dataset[dataset]
        gate_facts = gate_by_dataset[dataset]
        gate_ids = {
            str(item["evidence_id"]) for item in gate_facts
            if isinstance(item.get("evidence_id"), str)
        }
        delivered_ids = gate_ids & delivered_by_capability[capability]
        exclusions = []
        for fact in gate_facts:
            evidence_id = str(fact.get("evidence_id", ""))
            if evidence_id in delivered_ids:
                continue
            reason = "BOUNDED_LATEST" if capability == "MARKET_STATE" else None
            if reason is None:
                failure_codes.append(
                    f"CAPABILITY_EVIDENCE_NOT_ROUTED:{capability}:{evidence_id}"
                )
                reason = "CAPABILITY_EVIDENCE_NOT_ROUTED"
            exclusions.append({"evidence_id": evidence_id, "reason": reason})
        observations.append({
            "dataset": dataset, "target_capability": capability,
            "capture_evidence_count": len(captured[dataset]),
            "gate_eligible_evidence_count": len(gate_ids),
            "delivered_evidence_count": len(delivered_ids),
            "delivery_status": (
                "DELIVERED" if delivered_ids else "NOT_DELIVERED"
                if gate_ids else "NO_GATE_EVIDENCE"
            ),
            "exclusions": exclusions,
            "actual_research_use_status": "NOT_EVALUATED_AT_PREPARATION",
        })
    return {
        "dataset_observations": observations,
        "failure_codes": sorted(failure_codes),
        "status": "FAILED" if failure_codes else "CLOSED",
    }


def _bounded_latest_facts(
    evidence: Sequence[Mapping[str, Any]], *, per_series: int = 2,
) -> list[dict[str, Any]]:
    """限制正式比较上下文，同时保留各口径最近的可核对事实。"""

    grouped: dict[tuple[str, str, str, str, str], list[Mapping[str, Any]]] = {}
    for fact in evidence:
        metadata = fact.get("metadata") if isinstance(fact.get("metadata"), Mapping) else {}
        key = (
            str(fact.get("security_id", "")),
            str(fact.get("semantic_field", "")),
            str(fact.get("unit", "")),
            str(metadata.get("form", "")),
            "duration" if metadata.get("period_start") else "instant",
        )
        grouped.setdefault(key, []).append(fact)
    selected = []
    for values in grouped.values():
        ordered = sorted(
            values,
            key=lambda item: (
                str(item.get("published_at", "")),
                str(item.get("as_of", "")),
                str(item.get("retrieved_at", "")),
                str(item.get("evidence_id", "")),
            ),
            reverse=True,
        )
        selected.extend(copy.deepcopy(dict(item)) for item in ordered[:per_series])
    return sorted(selected, key=lambda item: str(item.get("evidence_id")))


def _macro_company_context_facts(
    evidence: Sequence[Mapping[str, Any]], *, security_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """为共享宏观任务选择少量可核对的公司暴露事实。"""

    fields = {
        "business",
        "management_discussion",
        "us-gaap.Revenues",
        "us-gaap.RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap.OperatingIncomeLoss",
        "us-gaap.NetCashProvidedByUsedInOperatingActivities",
        "us-gaap.PaymentsToAcquirePropertyPlantAndEquipment",
        "us-gaap.LongTermDebt",
        "us-gaap.LongTermDebtNoncurrent",
        "us-gaap.CashAndCashEquivalentsAtCarryingValue",
    }
    scoped_ids = set(security_ids)
    scoped = [
        item for item in evidence
        if item.get("security_id") in scoped_ids
        and item.get("semantic_field") in fields
        and (
            item.get("source_type") == "sec"
            or "sec" in str(item.get("source_id", "")).lower()
        )
    ]
    return _bounded_latest_facts(scoped, per_series=1)


def _technical_rows(
    evidence: Sequence[Mapping[str, Any]], *, security_id: str,
) -> list[dict[str, Any]]:
    """把冻结的字段事实还原为确定性计算所需的逐交易日行。"""

    by_date: dict[str, dict[str, Any]] = {}
    field_map = {
        "historical_close_price": "close",
        "adjusted_close_price": "adjusted_close",
        "share_volume": "volume",
        "stock_split_ratio": "stock_split",
    }
    for fact in evidence:
        if fact.get("security_id") != security_id:
            continue
        target = field_map.get(str(fact.get("semantic_field", "")))
        if target is None:
            continue
        metadata = fact.get("metadata") if isinstance(fact.get("metadata"), Mapping) else {}
        day = metadata.get("trading_date")
        if not isinstance(day, str):
            as_of = fact.get("as_of")
            day = str(as_of)[:10] if isinstance(as_of, str) and len(as_of) >= 10 else None
        if not isinstance(day, str):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_TECHNICAL_DATE_MISSING")
        row = by_date.setdefault(
            day,
            {
                "date": day,
                "close": None,
                "adjusted_close": None,
                "volume": None,
                "stock_split": 0,
                "evidence_ids": [],
            },
        )
        if row[target] not in {None, 0}:
            raise MultidimensionalStageError(
                f"MULTIDIMENSIONAL_TECHNICAL_FIELD_DUPLICATE:{security_id}:{day}:{target}"
            )
        row[target] = fact.get("value")
        row["evidence_ids"].append(str(fact["evidence_id"]))
    return [
        row for _, row in sorted(by_date.items())
        if row["close"] is not None
    ]


def _prepare_technical_artifacts(
    run_dir: Path, *, task_id: str, security_id: str, benchmark_id: str,
    evidence: Sequence[Mapping[str, Any]], as_of: str,
) -> dict[str, Any]:
    """冻结同源技术计算与图表；资料不足时只记录可审计缺口。"""

    from product.council.technical_chart import render_relative_performance_svg
    from product.deterministic.market_analysis import calculate_technical_statistics

    security_rows = _technical_rows(evidence, security_id=security_id)
    benchmark_rows = _technical_rows(evidence, security_id=benchmark_id)
    directory = run_dir / "research/precomputed" / canonical_hash({"task_id": task_id})[:16]
    directory.mkdir(parents=True, exist_ok=False)
    result: dict[str, Any] = {
        "security_row_count": len(security_rows),
        "benchmark_row_count": len(benchmark_rows),
        "calculation": None,
        "chart": None,
        "gaps": [],
        "allowed_artifact_refs": [],
    }
    if not security_rows or not benchmark_rows:
        result["gaps"].append({
            "reason_code": "TECHNICAL_SERIES_MISSING",
            "description": "证券或广泛市场基准缺少冻结的日线研究序列。",
            "impact": "不能计算相对收益、波动、回撤或生成同源图表。",
        })
        return result
    calculation = calculate_technical_statistics(
        security_rows,
        benchmark_rows,
        security_id=security_id,
        benchmark_id=benchmark_id,
        as_of=as_of,
    )
    calculation_path = directory / "technical-calculation.json"
    _write_object(calculation_path, calculation)
    calculation_ref = str(calculation_path.relative_to(run_dir))
    result["calculation"] = {
        key: copy.deepcopy(value)
        for key, value in calculation.items()
        if key != "evidence_fact_ids"
    }
    result["calculation"]["evidence_fact_count"] = len(
        calculation["evidence_fact_ids"]
    )
    result["calculation"]["evidence_fact_ids_hash"] = canonical_hash(
        calculation["evidence_fact_ids"]
    )
    result["calculation_ref"] = calculation_ref
    result["allowed_artifact_refs"].append(calculation_ref)
    try:
        svg = render_relative_performance_svg(
            security_rows,
            benchmark_rows,
            security_label=security_id,
            benchmark_label=benchmark_id,
        )
    except ValueError as exc:
        reason_code = str(exc).split(":", 1)[0]
        if reason_code not in {
            "TECHNICAL_CHART_HISTORY_INSUFFICIENT",
            "TECHNICAL_CHART_VALUE_INVALID",
        }:
            raise
        result["gaps"].append({
            "reason_code": reason_code,
            "description": (
                "证券与基准可对齐的交易日不足，无法生成相对表现图。"
                if reason_code == "TECHNICAL_CHART_HISTORY_INSUFFICIENT"
                else "冻结序列的价格或成交量包含图表不可用数值，无法生成相对表现图。"
            ),
            "impact": "计算结果仍可使用，但本批次不提供图形。",
        })
    else:
        chart_path = directory / "relative-performance.svg"
        chart_path.write_text(svg, encoding="utf-8")
        chart_ref = str(chart_path.relative_to(run_dir))
        result["chart"] = {
            "artifact_ref": chart_ref,
            "content_hash": file_hash(chart_path),
            "price_basis": calculation["price_basis"],
            "security_id": security_id,
            "benchmark_id": benchmark_id,
        }
        result["allowed_artifact_refs"].append(chart_ref)
    return result


def _prepare_macro_market_artifacts(
    run_dir: Path, *, task_id: str, benchmark_id: str,
    evidence: Sequence[Mapping[str, Any]], as_of: str,
) -> dict[str, Any]:
    """从冻结的广泛市场日线生成共享宏观任务可消费的市场状态。"""

    from product.deterministic.market_analysis import calculate_market_state_statistics

    market_rows = _technical_rows(evidence, security_id=benchmark_id)
    directory = run_dir / "research/precomputed" / canonical_hash({"task_id": task_id})[:16]
    directory.mkdir(parents=True, exist_ok=False)
    result: dict[str, Any] = {
        "calculation": None,
        "chart": None,
        "gaps": [],
        "allowed_artifact_refs": [],
    }
    if not market_rows:
        result["gaps"].append({
            "reason_code": "MARKET_STATE_SERIES_MISSING",
            "description": "广泛市场基准缺少冻结的日线研究序列。",
            "impact": "不能形成同一截止点的大盘收益、波动或回撤状态。",
        })
        return result
    calculation = calculate_market_state_statistics(
        market_rows, market_id=benchmark_id, as_of=as_of,
    )
    calculation_path = directory / "market-state-calculation.json"
    _write_object(calculation_path, calculation)
    calculation_ref = str(calculation_path.relative_to(run_dir))
    result["calculation"] = {
        key: copy.deepcopy(value)
        for key, value in calculation.items()
        if key != "evidence_fact_ids"
    }
    result["calculation"]["evidence_fact_count"] = len(
        calculation["evidence_fact_ids"]
    )
    result["calculation"]["evidence_fact_ids_hash"] = canonical_hash(
        calculation["evidence_fact_ids"]
    )
    result["calculation_ref"] = calculation_ref
    result["allowed_artifact_refs"].append(calculation_ref)
    return result


def _dynamic_draft_schema(
    repository_root: Path, *, run_id: str, invocation_id: str, agent: str,
    allowed_evidence_ids: Sequence[str], allowed_artifact_refs: Sequence[str],
    allowed_documents: Sequence[Mapping[str, Any]] = (),
    claims_forbidden: bool = False,
    technical_calculation_missing: bool = False,
) -> dict[str, Any]:
    schema = _read_object(
        repository_root / "product/schemas/runtime/research-dimension-report-v2.schema.json"
    )
    technical = {
        "schema_version", "report_id", "capability", "scope", "security_ids",
        "bindings", "time_context", "execution", "report_hash",
    }
    for key in technical:
        schema["properties"].pop(key)
        schema["required"].remove(key)
    schema["title"] = "ResearchDimensionDraft"
    schema["$id"] = "research-dimension-draft/2.0.0"
    schema["properties"]["run_id"] = {"type": "string", "const": run_id}
    schema["properties"]["invocation_id"] = {"type": "string", "const": invocation_id}
    schema["properties"]["agent"] = {"type": "string", "const": agent}
    schema["required"].append("agent")
    schema["$defs"]["evidence_id"] = {"type": "string", "enum": list(allowed_evidence_ids)}
    schema["properties"]["artifact_refs"]["items"] = {
        "type": "string", "enum": list(allowed_artifact_refs)
    }
    schema["$defs"]["calculation"]["properties"]["artifact_ref"] = {
        "type": "string", "enum": list(allowed_artifact_refs)
    }
    schema["properties"]["documents"] = {
        "type": "array", "items": {
            "type": "object", "enum": [copy.deepcopy(dict(item)) for item in allowed_documents]
        }
    }
    if claims_forbidden or technical_calculation_missing:
        schema["properties"]["claims"]["maxItems"] = 0
    if technical_calculation_missing:
        schema["properties"]["status"] = {
            "type": "string", "const": "INSUFFICIENT_EVIDENCE",
        }
        schema["properties"]["sufficiency"] = {
            "type": "string", "const": "INSUFFICIENT",
        }
        schema["properties"]["data_gaps"]["minItems"] = 1
    return schema


def _task_id(capability: str, security_id: str | None) -> str:
    suffix = security_id.replace(":", "_").lower() if security_id else "shared"
    return f"{capability.lower()}:{suffix}"


def _calculation_ids_for_invocation(run_dir: Path, invocation_id: str) -> list[str]:
    """从来源运行的实际 MCP 事件提取计算产物 ID。"""

    path = run_dir / "events/mcp/events.jsonl"
    if not path.is_file():
        return []
    identifiers: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_MCP_EVENT_INVALID") from exc
        calculation_id = event.get("calculation_id")
        if (
            event.get("event_type") == "mcp_tool_result"
            and event.get("invocation_id") == invocation_id
            and event.get("tool") == "fixture_math.calculate"
            and isinstance(calculation_id, str)
            and calculation_id
        ):
            identifiers.append(calculation_id)
    return sorted(set(identifiers))


def _import_company_research_reports(
    *, source_run: Path, target_run: Path, expected_handoff: Mapping[str, Any],
    expected_security_ids: Sequence[str], target_gate: Mapping[str, Any],
) -> dict[str, Any]:
    """冻结并重验已有公司报告；不改写报告内容或原始版本绑定。"""

    from product.council.common_stock_research import validate_holding_research_request
    from product.council.research_output import validate_persisted_equity_research_pair
    from product.runtime.validation import collect_evidence_refs

    source_run = Path(source_run).resolve()
    target_run = Path(target_run).resolve()
    manifest = _read_object(source_run / "run_manifest.json")
    repository_root = Path(manifest["discovery"]["product_root"]).resolve().parent
    if manifest.get("stage") != "COMMON_STOCK_RESEARCH":
        raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_SOURCE_STAGE_INVALID")
    source_handoff = _read_object(source_run / "audit/portfolio-handoff.json")
    if (
        source_handoff.get("handoff_hash") != expected_handoff.get("handoff_hash")
        or source_handoff.get("portfolio_hash") != expected_handoff.get("portfolio_hash")
    ):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_SOURCE_PORTFOLIO_MISMATCH")
    source_gate = _read_object(source_run / "evidence/gate.json")
    target_cutoff = target_gate.get("decision_cutoff")
    source_cutoff = source_gate.get("decision_cutoff")
    if (
        not isinstance(source_cutoff, str)
        or not isinstance(target_cutoff, str)
        or parse_timestamp(source_cutoff) > parse_timestamp(target_cutoff)
    ):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_SOURCE_CUTOFF_INVALID")
    source_index = _read_object(source_run / "research/dispatch-index.json")
    source_reuse_index_path = source_run / "research/reuse-index.json"
    source_reuse_index = (
        _read_object(source_reuse_index_path)
        if source_reuse_index_path.is_file()
        else {"items": []}
    )
    source_proof = _read_object(source_run / "research/execution-proof.json")
    if (
        source_proof.get("all_reports_valid") is not True
        or source_proof.get("run_id") != manifest.get("run_id")
        or source_proof.get("gate_hash") != source_gate.get("bundle_hash")
        or source_proof.get("proof_hash") != canonical_hash({
            key: value for key, value in source_proof.items() if key != "proof_hash"
        })
    ):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_SOURCE_PROOF_INVALID")
    tasks_by_security: dict[str, dict[str, Any]] = {}
    for task in source_index.get("tasks", []):
        security_id = task.get("security_id")
        if isinstance(security_id, str):
            if security_id in tasks_by_security:
                raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_SOURCE_DUPLICATE")
            tasks_by_security[security_id] = dict(task, source_kind="RUN")
    for reused in source_reuse_index.get("items", []):
        security_id = reused.get("security_id") if isinstance(reused, Mapping) else None
        if isinstance(security_id, str):
            if security_id in tasks_by_security:
                raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_SOURCE_DUPLICATE")
            tasks_by_security[security_id] = dict(reused, source_kind="REUSED")
    if set(expected_security_ids) - set(tasks_by_security):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_SOURCE_COVERAGE_INCOMPLETE")
    if set(source_proof.get("completed_security_ids", [])) < set(expected_security_ids):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_SOURCE_PROOF_INCOMPLETE")

    evidence_by_id = {
        item.get("evidence_id"): item
        for item in source_gate.get("allowed_evidence", [])
        if isinstance(item, Mapping) and isinstance(item.get("evidence_id"), str)
    }
    target_evidence_by_id = {
        item.get("evidence_id"): item
        for item in target_gate.get("allowed_evidence", [])
        if isinstance(item, Mapping) and isinstance(item.get("evidence_id"), str)
    }
    imported: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen_report_ids: set[str] = set()
    for security_id in expected_security_ids:
        task = tasks_by_security[security_id]
        source_json = source_run / "research/reports" / security_id.replace(":", "_") / "equity-research.json"
        source_markdown = source_json.with_suffix(".md")
        report = _read_object(source_json)
        if task["source_kind"] == "RUN":
            request_path = source_run / str(task.get("request_path", ""))
            request = _read_object(request_path)
            validate_holding_research_request(
                request,
                handoff=source_handoff,
                council_request=_read_object(source_run / "council-request.json"),
                gate=source_gate,
            )
            calculation_ids = _calculation_ids_for_invocation(
                source_run, request["invocation_id"]
            )
            scoped_evidence = [
                evidence_by_id[evidence_id]
                for evidence_id in request["allowed_evidence_ids"]
                if evidence_id in evidence_by_id
            ]
            if len(scoped_evidence) != len(request["allowed_evidence_ids"]):
                raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_SOURCE_EVIDENCE_INCOMPLETE")
        else:
            from product.runtime.research_memory import (
                ResearchMemory, resolve_memory_root, validate_report_reference,
            )
            memory_root = manifest.get("memory_root")
            if not isinstance(memory_root, str):
                raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_REUSE_MEMORY_MISSING")
            reference = _read_object(source_run / str(task.get("reference_path", "")))
            validate_report_reference(reference)
            memory = ResearchMemory(resolve_memory_root(
                repository_root, Path(memory_root),
            ))
            package = memory.load_report_package(
                reference["package_ref"], reference["package_hash"]
            )
            if package["report"] != report:
                raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_REUSE_REPORT_MISMATCH")
            request = package["request"]
            scoped_evidence = list(package["evidence"])
            from product.runtime.common_stock_stage import (
                _report_package_calculation_ids,
            )
            calculation_ids = _report_package_calculation_ids(package)
        pair_hashes = validate_persisted_equity_research_pair(
            json_path=source_json,
            markdown_path=source_markdown,
            request=request,
            evidence=scoped_evidence,
            calculation_artifact_ids=calculation_ids,
        )
        report_cutoff = request["decision_cutoff"]
        report_id = report.get("report_id")
        if not isinstance(report_id, str) or report_id in seen_report_ids:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_REPORT_ID_INVALID")
        seen_report_ids.add(report_id)
        used_evidence_ids = sorted(collect_evidence_refs(report))
        missing_ids = sorted(set(used_evidence_ids) - set(target_evidence_by_id))
        drifted_ids = sorted(
            evidence_id for evidence_id in used_evidence_ids
            if evidence_id in target_evidence_by_id
            and canonical_hash(evidence_by_id[evidence_id])
            != canonical_hash(target_evidence_by_id[evidence_id])
        )
        if missing_ids or drifted_ids:
            rejected.append({
                "security_id": security_id,
                "report_id": report_id,
                "status": "INCOMPATIBLE_TARGET_GATE",
                "source_run_id": manifest.get("run_id"),
                "source_decision_cutoff": report_cutoff,
                "source_report_hash": canonical_hash(report),
                "missing_evidence_ids": missing_ids,
                "drifted_evidence_ids": drifted_ids,
                "gap_reason": (
                    "历史公司报告引用的冻结事实未在当前统一 Gate 中保持同一身份与内容，"
                    "因此不作为当前研究包的有效公司报告。"
                ),
            })
            continue
        destination = target_run / "research/imported-company-research" / security_id.replace(":", "_")
        destination.mkdir(parents=True, exist_ok=False)
        copied_json = destination / "equity-research.json"
        copied_markdown = destination / "equity-research.md"
        copied_request = destination / "holding-research-request.json"
        copied_evidence = destination / "evidence.json"
        shutil.copy2(source_json, copied_json)
        shutil.copy2(source_markdown, copied_markdown)
        _write_object(copied_request, request)
        _write_object(copied_evidence, {"allowed_evidence": scoped_evidence})
        if file_hash(copied_json) != file_hash(source_json) or file_hash(copied_markdown) != file_hash(source_markdown):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_IMPORT_HASH_MISMATCH")
        imported.append({
            "security_id": security_id,
            "report_id": report_id,
            "report_hash": canonical_hash(report),
            "status": report["status"],
            "source_run_id": manifest.get("run_id"),
            "source_decision_cutoff": report_cutoff,
            "source_manifest_hash": manifest.get("manifest_hash"),
            "source_gate_hash": source_gate.get("bundle_hash"),
            "source_request_hash": request.get("request_hash"),
            "source_json_file_hash": file_hash(source_json),
            "source_markdown_file_hash": file_hash(source_markdown),
            "validated_json_hash": pair_hashes["json_hash"],
            "validated_markdown_hash": pair_hashes["markdown_hash"],
            "calculation_artifact_ids": calculation_ids,
            "artifact_ref": str(copied_json.relative_to(target_run)),
            "markdown_ref": str(copied_markdown.relative_to(target_run)),
            "request_ref": str(copied_request.relative_to(target_run)),
            "evidence_ref": str(copied_evidence.relative_to(target_run)),
        })
    proof = {
        "schema_version": "company-research-import/1.0.0",
        "source_run": str(source_run),
        "source_run_id": manifest.get("run_id"),
        "source_manifest_file_hash": file_hash(source_run / "run_manifest.json"),
        "source_execution_proof_file_hash": file_hash(source_run / "research/execution-proof.json"),
        "handoff_hash": expected_handoff["handoff_hash"],
        "portfolio_hash": expected_handoff["portfolio_hash"],
        "target_decision_cutoff": target_cutoff,
        "reports": imported,
        "rejected_reports": rejected,
    }
    proof["import_hash"] = canonical_hash(proof)
    _write_object(target_run / "research/imported-company-research/import-manifest.json", proof)
    return proof


def _report_document_from_verified(value: Mapping[str, Any]) -> dict[str, Any]:
    """投影正文元数据；正文仅作为输入材料，不复制进正式报告。"""

    disclosure = value.get("interest_disclosure")
    status = disclosure if disclosure in {"DECLARED", "UNKNOWN"} else "UNKNOWN"
    return {
        "document_id": value["document_id"], "source_id": value["source_id"],
        "title": value["title"], "authors": list(value.get("authors", [])),
        "institution": value.get("institution"), "material_type": value["material_type"],
        "source_url": value["source_url"], "original_source_url": value.get("original_source_url"),
        "published_at": value["published_at"], "as_of": value["as_of"],
        "retrieved_at": value["retrieved_at"], "body_hash": value["body_hash"],
        "locations": list(value.get("locations", [])), "parse_scope": value["parse_scope"],
        "duplicate_of": value.get("duplicate_of"), "revision_of": value.get("revision_of"),
        "interest_disclosure": {"status": status, "statement": None, "location": None},
        "verification_status": value["verification_status"],
    }


def _issuer_documents_from_gate(
    evidence: Sequence[Mapping[str, Any]], *, security_ids: Sequence[str],
) -> dict[str, list[dict[str, Any]]]:
    """把已由 SEC 采集/解析并通过 Gate 的公司正文投影为 issuer documents。"""

    result = {security_id: [] for security_id in security_ids}
    candidates: dict[str, list[tuple[Mapping[str, Any], str, str]]] = {
        security_id: [] for security_id in security_ids
    }
    for fact in evidence:
        security_id = fact.get("security_id")
        if security_id not in candidates:
            continue
        source_type = str(fact.get("source_type", ""))
        source_id = str(fact.get("source_id", "")).lower()
        if fact.get("semantic_field") not in {"earnings_release", "management_discussion"}:
            continue
        if source_type != "sec" and "sec" not in source_id:
            continue
        metadata = fact.get("metadata") if isinstance(fact.get("metadata"), Mapping) else {}
        body_text = metadata.get("text") if isinstance(metadata.get("text"), str) else fact.get("value")
        if not isinstance(body_text, str):
            continue
        body_text = " ".join(body_text.split())
        # SEC 目录抽取通常只有 Item 标题和页码。它可作定位线索，但不是已读正文。
        if len(body_text) < 300 or len(body_text.split()) < 50:
            continue
        body_hash = canonical_hash({
            "text": body_text,
            "normalized_text_range": metadata.get("normalized_text_range"),
            "raw_character_spans": metadata.get("raw_character_spans"),
        })
        candidates[security_id].append((fact, body_text, body_hash))
    for security_id, items in candidates.items():
        # 同一 filing 的同一语义段只保留最长、最完整的抽取，避免把重叠段落计成多份正文。
        deduplicated: dict[tuple[str, str], tuple[Mapping[str, Any], str, str]] = {}
        for item in items:
            fact, body_text, _ = item
            raw_identity = str(
                fact.get("raw_content_hash") or fact.get("source_locator") or fact.get("source_id")
            )
            identity = (raw_identity, str(fact.get("semantic_field")))
            incumbent = deduplicated.get(identity)
            if incumbent is None or len(body_text) > len(incumbent[1]):
                deduplicated[identity] = item
        facts = list(deduplicated.values())
        for fact in sorted(
            facts,
            key=lambda item: (
                str(item[0].get("published_at", "")), str(item[0].get("evidence_id", "")),
            ),
            reverse=True,
        )[:4]:
            fact, body_text, body_hash = fact
            metadata = fact.get("metadata") if isinstance(fact.get("metadata"), Mapping) else {}
            locator = str(fact.get("source_locator", ""))
            raw_hash = str(fact.get("raw_content_hash", ""))
            report_document = {
                "document_id": "issuer-document-" + canonical_hash({
                    "evidence_id": fact["evidence_id"], "raw_content_hash": raw_hash,
                })[:24],
                "source_id": str(fact["source_id"]),
                "title": str(
                    metadata.get("description")
                    or metadata.get("attachment_description")
                    or "SEC issuer earnings material"
                ),
                "authors": [], "institution": security_id,
                "material_type": "ISSUER_MATERIAL",
                "source_url": locator, "original_source_url": locator,
                "published_at": fact["published_at"], "as_of": fact["as_of"],
                "retrieved_at": fact["retrieved_at"],
                "body_hash": body_hash,
                "locations": [
                    str(fact.get("section") or fact.get("semantic_field")),
                    f"gate-evidence:{fact['evidence_id']}",
                ],
                "parse_scope": "SEC_GATE_VERIFIED_EVIDENCE_RANGE",
                "duplicate_of": None, "revision_of": None,
                "interest_disclosure": {
                    "status": "DECLARED", "statement": None, "location": None,
                },
                "verification_status": "BODY_VERIFIED",
            }
            result[security_id].append({
                "report_document": report_document,
                "content": {
                    "schema_version": "gate-verified-issuer-document/1.0.0",
                    "document_id": report_document["document_id"],
                    "security_id": security_id,
                    "evidence_id": fact["evidence_id"],
                    "source_id": fact["source_id"],
                    "source_locator": locator,
                    "published_at": fact["published_at"], "as_of": fact["as_of"],
                    "retrieved_at": fact["retrieved_at"],
                    "body_hash": body_hash,
                    "raw_content_hash": raw_hash,
                    "body_character_count": len(body_text),
                    "classification": "ISSUER_IR_OR_ANNOUNCEMENT_BODY",
                    "body_access": "query the bound Gate evidence_id",
                },
            })
    return result


def _import_research_materials(
    *, source_run: Path, target_run: Path, expected_handoff: Mapping[str, Any],
    target_gate: Mapping[str, Any], expected_security_ids: Sequence[str],
) -> dict[str, Any]:
    """重验资料准备输出并复制其选择、正文和工具证明。"""

    from product.runtime.research_materials_stage import validate_material_preparation_output

    source_run = Path(source_run).resolve()
    target_run = Path(target_run).resolve()
    source_manifest = _read_object(source_run / "run_manifest.json")
    materials = _read_object(source_run / "research/material-preparation-manifest.json")
    source_index = _read_object(source_run / "research/dispatch-index.json")
    if (
        source_manifest.get("stage") != "MULTIDIMENSIONAL_MATERIAL_PREPARATION"
        or materials.get("manifest_hash") != canonical_hash({
            key: value for key, value in materials.items() if key != "manifest_hash"
        })
        or materials.get("handoff_hash") != expected_handoff.get("handoff_hash")
        or materials.get("portfolio_hash") != expected_handoff.get("portfolio_hash")
    ):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_MATERIALS_SOURCE_INVALID")
    target_gate_content_hash = canonical_hash({
        key: value for key, value in target_gate.items()
        if key not in {"run_id", "bundle_hash", "base_gate_content_hash"}
    })
    comparable_gate_hash = target_gate.get("base_gate_content_hash", target_gate_content_hash)
    if materials.get("gate_content_hash") != comparable_gate_hash:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_MATERIALS_GATE_MISMATCH")
    source_pool = _read_object(source_run / "research/peer-candidate-pool.json")
    candidate_by_id = {
        item["candidate_id"]: item
        for group in source_pool.get("groups", []) for item in group.get("candidates", [])
    }
    materialization_path = source_run / "research/peer-materialization/peer-materialization-manifest.json"
    materialized_by_candidate: dict[tuple[str, str], dict[str, Any]] = {}
    if materialization_path.is_file():
        materialization = _read_object(materialization_path)
        if materialization.get("materialization_hash") != canonical_hash({
            key: value for key, value in materialization.items() if key != "materialization_hash"
        }):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_PEER_MATERIALIZATION_INVALID")
        materialized_by_candidate = {
            (item["holding_security_id"], item["candidate_id"]): item
            for item in materialization.get("selected", [])
        }
    tasks = {item["task_id"]: item for item in source_index.get("tasks", [])}
    if len(tasks) != len(source_index.get("tasks", [])):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_MATERIALS_TASK_DUPLICATE")
    output_by_task = {item["task_id"]: item for item in materials.get("outputs", [])}
    if set(output_by_task) != set(tasks):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_MATERIALS_OUTPUT_INCOMPLETE")
    documents_by_security = {security_id: [] for security_id in expected_security_ids}
    documents_by_capability = {"MACRO_CONTEXT": [], "MARKET_STATE": []}
    peers_by_security = {security_id: [] for security_id in expected_security_ids}
    report_preparation_by_security = {security_id: None for security_id in expected_security_ids}
    shared_preparation_by_capability = {"MACRO_CONTEXT": None, "MARKET_STATE": None}
    peer_preparation_by_security = {security_id: None for security_id in expected_security_ids}
    copied_refs: list[str] = []
    import_entries = []
    destination_root = target_run / "research/imported-materials"
    destination_root.mkdir(parents=True, exist_ok=False)
    for task_id, task in tasks.items():
        output_entry = output_by_task[task_id]
        security_id = task["security_id"]
        preparation_kind = task["preparation_kind"]
        shared_capability = {
            "MACRO_RESEARCH_DISCOVERY": "MACRO_CONTEXT",
            "MARKET_RESEARCH_DISCOVERY": "MARKET_STATE",
        }.get(preparation_kind)
        if shared_capability is None and security_id not in documents_by_security:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_MATERIALS_SECURITY_INVALID")
        if output_entry.get("status") == "FAILED":
            failure_code = str(
                output_entry.get("failure_code") or "RESEARCH_MATERIALS_OUTPUT_INVALID"
            )
            preparation = {
                "status": "FAILED",
                "summary": "资料准备输出未通过确定性契约校验。",
                "gaps": copy.deepcopy(output_entry.get("gaps", [])),
                "artifact_refs": [],
                "failure_code": failure_code,
            }
            if preparation_kind == "RESEARCH_REPORT_DISCOVERY":
                report_preparation_by_security[security_id] = preparation
            elif shared_capability is not None:
                shared_preparation_by_capability[shared_capability] = preparation
            else:
                peer_preparation_by_security[security_id] = preparation
            import_entries.append({
                "task_id": task_id, "security_id": security_id,
                "preparation_kind": task["preparation_kind"], "status": "FAILED",
                "failure_code": failure_code, "source_output_hash": output_entry.get("output_hash"),
                "copied_output_ref": None, "copied_artifacts": [],
            })
            continue
        output_ref = output_entry.get("output_ref")
        if not isinstance(output_ref, str) or not output_ref:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_MATERIALS_OUTPUT_REF_INVALID")
        output = _read_object(source_run / output_ref)
        validate_material_preparation_output(output, task=task, run_dir=source_run)
        destination = destination_root / canonical_hash({"task_id": task_id})[:16]
        destination.mkdir(parents=True, exist_ok=False)
        copied_output = destination / "preparation-result.json"
        shutil.copy2(source_run / output_ref, copied_output)
        copied_refs.append(str(copied_output.relative_to(target_run)))
        copied_artifacts = []
        for artifact_ref in output.get("artifact_refs", []):
            source_artifact = source_run / artifact_ref
            if not source_artifact.is_file():
                raise MultidimensionalStageError("MULTIDIMENSIONAL_MATERIALS_ARTIFACT_MISSING")
            copied = destination / source_artifact.name
            shutil.copy2(source_artifact, copied)
            if file_hash(copied) != file_hash(source_artifact):
                raise MultidimensionalStageError("MULTIDIMENSIONAL_MATERIALS_ARTIFACT_DRIFT")
            copied_ref = str(copied.relative_to(target_run))
            copied_refs.append(copied_ref)
            copied_artifacts.append({"artifact_ref": copied_ref, "file_hash": file_hash(copied)})
        if preparation_kind in {
            "RESEARCH_REPORT_DISCOVERY", "MACRO_RESEARCH_DISCOVERY",
            "MARKET_RESEARCH_DISCOVERY",
        }:
            preparation = {
                "status": output["status"], "summary": output["summary"],
                "gaps": copy.deepcopy(output["gaps"]),
                "artifact_refs": list(output["artifact_refs"]),
            }
            documents = []
            for selection in output["selections"]:
                matches = []
                for artifact_ref in output["artifact_refs"]:
                    candidate = _read_object(source_run / artifact_ref)
                    if candidate.get("document_id") == selection["document_id"]:
                        matches.append(candidate)
                if len(matches) != 1 or matches[0].get("verification_status") != "BODY_VERIFIED":
                    raise MultidimensionalStageError("MULTIDIMENSIONAL_MATERIALS_DOCUMENT_MISSING")
                if parse_timestamp(matches[0]["published_at"]) > parse_timestamp(target_gate["decision_cutoff"]):
                    raise MultidimensionalStageError("MULTIDIMENSIONAL_MATERIALS_DOCUMENT_PIT_INVALID")
                documents.append({
                    "report_document": _report_document_from_verified(matches[0]),
                    "content": copy.deepcopy(matches[0]),
                })
            if shared_capability is None:
                report_preparation_by_security[security_id] = preparation
                documents_by_security[security_id] = documents
            else:
                shared_preparation_by_capability[shared_capability] = preparation
                documents_by_capability[shared_capability] = documents
        else:
            peer_preparation_by_security[security_id] = {
                "status": output["status"], "summary": output["summary"],
                "gaps": copy.deepcopy(output["gaps"]),
                "artifact_refs": list(output["artifact_refs"]),
            }
            peers = []
            for selection in output["selections"]:
                candidate = candidate_by_id.get(selection["candidate_id"])
                if candidate is None:
                    raise MultidimensionalStageError("MULTIDIMENSIONAL_MATERIALS_PEER_UNKNOWN")
                materialized = materialized_by_candidate.get((security_id, selection["candidate_id"]))
                peers.append({
                    **copy.deepcopy(candidate), "selection_rationale": selection["rationale"],
                    "materialized_security_id": (
                        materialized.get("materialized_security_id") if materialized else None
                    ),
                    "materialization_status": "FROZEN" if materialized else "NOT_MATERIALIZED",
                })
            peers_by_security[security_id] = peers
        import_entries.append({
            "task_id": task_id, "security_id": security_id,
            "preparation_kind": task["preparation_kind"], "status": output["status"],
            "source_output_hash": canonical_hash(output),
            "copied_output_ref": str(copied_output.relative_to(target_run)),
            "copied_artifacts": copied_artifacts,
        })
    proof = {
        "schema_version": "research-materials-import/1.0.0",
        "source_run": str(source_run), "source_run_id": source_manifest.get("run_id"),
        "source_manifest_file_hash": file_hash(source_run / "run_manifest.json"),
        "source_materials_manifest_file_hash": file_hash(source_run / "research/material-preparation-manifest.json"),
        "handoff_hash": expected_handoff["handoff_hash"], "portfolio_hash": expected_handoff["portfolio_hash"],
        "gate_content_hash": comparable_gate_hash, "entries": import_entries,
        "peer_materialization_file_hash": (
            file_hash(materialization_path) if materialization_path.is_file() else None
        ),
    }
    proof["import_hash"] = canonical_hash(proof)
    _write_object(destination_root / "import-manifest.json", proof)
    copied_refs.append(str((destination_root / "import-manifest.json").relative_to(target_run)))
    return {
        "documents_by_security": documents_by_security,
        "documents_by_capability": documents_by_capability,
        "peers_by_security": peers_by_security,
        "report_preparation_by_security": report_preparation_by_security,
        "shared_preparation_by_capability": shared_preparation_by_capability,
        "peer_preparation_by_security": peer_preparation_by_security,
        "artifact_refs": copied_refs,
        "import_hash": proof["import_hash"],
    }


def build_multidimensional_dispatch_packet(
    repository_root: Path, run_dir: Path, task_name: str, *,
    include_dependency_reports: bool = True,
) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    index = _read_object(run_dir / "research/dispatch-index.json")
    matches = [item for item in index["tasks"] if item["task_name"] == task_name]
    if len(matches) != 1:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_TASK_UNKNOWN")
    task = matches[0]
    packet = _read_object(run_dir / task["packet_path"])
    if canonical_hash(packet) != task["packet_hash"]:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_PACKET_HASH_MISMATCH")
    view = packet.get("provider_coverage")
    expected_view_kind = task.get("provider_coverage_view_kind")
    if expected_view_kind is not None and (
        expected_view_kind != "TASK_SCOPED_PROVIDER_COVERAGE"
        or not isinstance(view, Mapping) or view.get("view_kind") != expected_view_kind
    ):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_COVERAGE_VIEW_BINDING_MISMATCH")
    if expected_view_kind == "TASK_SCOPED_PROVIDER_COVERAGE" or (
        isinstance(view, Mapping) and view.get("view_kind") == "TASK_SCOPED_PROVIDER_COVERAGE"
    ):
        manifest = _read_object(run_dir / "run_manifest.json")
        audit = _read_object(run_dir / task["provider_coverage_ref"])
        gate = _read_object(run_dir / "evidence/gate.json")
        expected_view = _task_provider_coverage_view(
            audit, task=task, evidence=gate["allowed_evidence"],
            stage=manifest["stage"],
        )
        if view != expected_view:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_COVERAGE_VIEW_BINDING_MISMATCH")
    dependency_reports = []
    for dependency_id in task.get("depends_on", []) if include_dependency_reports else []:
        matches = []
        for path in (run_dir / "research/reports").glob("*/dimension-report.json"):
            report = _read_object(path)
            if report.get("report_id") == f"dimension-report:{dependency_id}":
                matches.append((path, report))
        if len(matches) != 1:
            raise MultidimensionalStageError(
                f"MULTIDIMENSIONAL_DEPENDENCY_REPORT_MISSING:{dependency_id}"
            )
        path, report = matches[0]
        dependency_reports.append({
            "report_id": report["report_id"],
            "report_hash": report["report_hash"],
            "capability": report["capability"],
            "security_ids": report["security_ids"],
            "summary": report["summary"],
            "claims": report["claims"],
            "assumptions": report["assumptions"],
            "limitations": report["limitations"],
            "data_gaps": report["data_gaps"],
            "artifact_ref": str(path.relative_to(run_dir)),
        })
    if task.get("depends_on") and include_dependency_reports:
        packet["dependency_reports"] = dependency_reports
        packet["allowed_research_claim_ids"] = sorted({
            claim["claim_id"]
            for report in dependency_reports
            for claim in report["claims"]
        })
    return packet


def build_multidimensional_dispatch_message(
    repository_root: Path, run_dir: Path, task_name: str,
) -> str:
    del repository_root, run_dir
    return (
        f"多维持仓研究任务 {task_name}。等待 SubagentStart Hook 注入冻结研究包；"
        "以 Hook 上下文为唯一研究输入，不在启动消息中复制资料。"
    )


def _load_research_capture_batches(
    *, gate_path: Path, gate: Mapping[str, Any], security_ids: Sequence[str],
) -> list[dict[str, Any]]:
    """从 Gate 同目录的已验证 preparation 引用中读取逐股 capability batch。"""

    preparation_path = gate_path.parent / "data-preparation.json"
    if not preparation_path.is_file():
        return []
    preparation = _read_object(preparation_path)
    if preparation.get("common_cutoff") != gate.get("decision_cutoff"):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_PROVIDER_PREPARATION_CUTOFF_MISMATCH")
    records = preparation.get("research_supplements", [])
    if not records and isinstance(preparation.get("research_supplement"), Mapping):
        record = dict(preparation["research_supplement"])
        record["batch_ref"] = "research-capture-batch.json"
        records = [record]
    if not isinstance(records, list):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_PROVIDER_PREPARATION_INVALID")
    expected_ids = set(security_ids)
    batches = []
    seen_ids: set[str] = set()
    from product.mcp.live.research_supplement import validate_capture_batch
    for record in records:
        if not isinstance(record, Mapping) or not isinstance(record.get("batch_ref"), str):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_PROVIDER_BATCH_REFERENCE_INVALID")
        security_id = record.get("security_id")
        if security_id not in expected_ids or security_id in seen_ids:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_PROVIDER_BATCH_SCOPE_INVALID")
        batch_path = (preparation_path.parent / record["batch_ref"]).resolve()
        if not batch_path.is_relative_to(preparation_path.parent.resolve()) or not batch_path.is_file():
            raise MultidimensionalStageError("MULTIDIMENSIONAL_PROVIDER_BATCH_REFERENCE_INVALID")
        batch = _read_object(batch_path)
        try:
            validate_capture_batch(batch)
        except (KeyError, TypeError, ValueError) as exc:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_PROVIDER_BATCH_INVALID") from exc
        if (
            batch.get("security_id") != security_id
            or batch.get("batch_id") != record.get("batch_id")
            or parse_timestamp(str(batch.get("decision_cutoff")))
            > parse_timestamp(str(gate.get("decision_cutoff")))
        ):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_PROVIDER_BATCH_BINDING_INVALID")
        batch_evidence_ids = {
            evidence_id
            for capability in batch.get("capabilities", [])
            for evidence_id in capability.get("evidence_ids", [])
            if isinstance(evidence_id, str)
        }
        if not batch_evidence_ids <= set(gate.get("allowed_evidence_ids", [])):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_PROVIDER_BATCH_EVIDENCE_INVALID")
        seen_ids.add(str(security_id))
        batches.append(batch)
    return batches


def _provider_scope(capability: str) -> set[str]:
    if capability == "MACRO_CONTEXT":
        return {"bls", "treasury", "federal_reserve", "bea", "fred", "moomoo_sg"}
    if capability == "MARKET_STATE":
        return {"yahoo", "treasury", "fred", "eastmoney", "moomoo_sg"}
    if capability in {"FUNDAMENTAL_EVENT", "RESEARCH_REPORT", "INDUSTRY_COMPARISON", "OWNERSHIP_DISCLOSURE", "OPTIONS_FLOW"}:
        return {"sec", "yahoo", "moomoo_sg", "openalex", "nasdaq"}
    return {"yahoo", "nasdaq", "eastmoney"}


def _task_provider_coverage_view(
    coverage: Mapping[str, Any], *, task: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]], stage: str,
) -> dict[str, Any]:
    """Project the frozen audit into the two forward shared-research inputs."""

    capability = task["capability"]
    if stage != "MULTI_DIMENSIONAL_HOLDING_RESEARCH" or capability not in {
        "MACRO_CONTEXT", "MARKET_STATE",
    }:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_COVERAGE_VIEW_SCOPE_INVALID")
    expected_hash = canonical_hash({key: value for key, value in coverage.items() if key != "coverage_hash"})
    if coverage.get("coverage_hash") != expected_hash:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_COVERAGE_AUDIT_HASH_MISMATCH")
    cutoff = task["time_context"]["window_end"]
    if coverage.get("decision_cutoff") != cutoff:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_COVERAGE_AUDIT_CUTOFF_MISMATCH")
    cutoff_time = parse_timestamp(cutoff)

    routed_datasets = set(DATASET_CAPABILITY_ROUTES[capability])
    allowed_ids = set(task["allowed_evidence_ids"])
    relevant_datasets = routed_datasets | {
        fact["dataset"] for fact in evidence
        if fact.get("evidence_id") in allowed_ids
        and isinstance(fact.get("dataset"), str) and fact["dataset"]
    }
    known_datasets = set().union(*DATASET_CAPABILITY_ROUTES.values())
    provider_fields = ("plane", "provider", "region", "access", "declared_status", "limitations")
    global_fields = (
        "observed_status", "delivery_status", "evidence_count",
        "capture_evidence_count", "gate_delivered_evidence_count", "failure_codes",
        "actual_research_use_status",
    )
    observation_fields = (
        "security_id", "dataset", "status", "failure_code", "checked_at", "as_of", "limitations",
    )
    providers = []
    for item in coverage["providers"]:
        if item["provider"] not in task["provider_scope"]:
            continue
        original = item["dataset_observations"]
        selected = [
            observation for observation in original
            if observation["dataset"] in relevant_datasets
            or observation["dataset"] not in known_datasets
        ]
        for observation in selected:
            try:
                checked_at = parse_timestamp(observation["checked_at"])
                as_of = parse_timestamp(observation["as_of"]) if observation["as_of"] is not None else None
            except (KeyError, TypeError, ValueError) as exc:
                raise MultidimensionalStageError("MULTIDIMENSIONAL_COVERAGE_VIEW_TIME_INVALID") from exc
            if checked_at > cutoff_time or (as_of is not None and as_of > cutoff_time):
                raise MultidimensionalStageError("MULTIDIMENSIONAL_COVERAGE_VIEW_AFTER_CUTOFF")
            if not observation.get("security_id") or not observation.get("dataset"):
                raise MultidimensionalStageError("MULTIDIMENSIONAL_COVERAGE_VIEW_IDENTITY_INVALID")
        providers.append({
            **{key: copy.deepcopy(item[key]) for key in provider_fields},
            "global_coverage": {key: copy.deepcopy(item[key]) for key in global_fields},
            "dataset_observation_scope": (
                "RELEVANT_OBSERVATIONS" if selected else
                "NO_RELEVANT_OBSERVATIONS" if original else "NO_DATASET_DETAIL"
            ),
            "dataset_observations": [
                {key: copy.deepcopy(observation[key]) for key in observation_fields}
                for observation in selected
            ],
        })

    routing = []
    for item in coverage["capability_routing"]["dataset_observations"]:
        if item["target_capability"] != capability:
            continue
        reasons: dict[str, int] = {}
        for exclusion in item["exclusions"]:
            reason = exclusion["reason"]
            reasons[reason] = reasons.get(reason, 0) + 1
        routing.append({
            key: copy.deepcopy(item[key]) for key in (
                "dataset", "target_capability", "capture_evidence_count",
                "gate_eligible_evidence_count", "delivered_evidence_count",
                "delivery_status", "actual_research_use_status",
            )
        } | {"exclusion_reason_counts": dict(sorted(reasons.items()))})
    return {
        "view_kind": "TASK_SCOPED_PROVIDER_COVERAGE",
        "stage": stage, "capability": capability,
        "source_schema_version": coverage["schema_version"],
        "coverage_hash": coverage["coverage_hash"],
        "decision_cutoff": coverage["decision_cutoff"],
        "fallback_policy": copy.deepcopy(coverage["fallback_policy"]),
        "capability_routing": {"dataset_observations": routing},
        "providers": providers,
    }


def prepare_multidimensional_stage_run(
    repository_root: Path, *, handoff_path: Path, gate_path: Path, run_dir: Path,
    run_id: str, model: str, research_question: str = "补全普通股持仓的免费多维研究资料。",
    benchmark_id: str = "US:SPY", target_concurrency: int = 3,
    peer_candidate_pool_path: Path | None = None,
    company_research_run_path: Path | None = None,
    research_materials_run_path: Path | None = None,
    stage: str = "MULTI_DIMENSIONAL_HOLDING_RESEARCH",
) -> dict[str, Any]:
    repository_root = Path(repository_root).resolve()
    product_root = repository_root / "product"
    run_dir = Path(run_dir).resolve()
    if run_dir.exists():
        raise MultidimensionalStageError("MULTIDIMENSIONAL_RUN_EXISTS")
    if type(target_concurrency) is not int or target_concurrency < 1:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_CONCURRENCY_INVALID")
    from product.runtime.model_routing import select_product_runtime_model
    selected_model = select_product_runtime_model(product_root, requested_model=model)
    resolved_gate_path = Path(gate_path).resolve()
    handoff = _read_object(Path(handoff_path).resolve())
    validate_handoff(handoff)
    gate = _read_object(resolved_gate_path)
    if gate.get("run_id") not in {None, run_id}:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_GATE_RUN_MISMATCH")
    gate["run_id"] = run_id
    gate["source_mode"] = gate.get("source_mode", "fixture")
    gate["bundle_hash"] = canonical_hash({key: item for key, item in gate.items() if key != "bundle_hash"})
    cutoff = gate.get("decision_cutoff")
    if not isinstance(cutoff, str):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_CUTOFF_MISSING")
    cutoff_time = parse_timestamp(cutoff)
    evidence = gate.get("allowed_evidence")
    if not isinstance(evidence, list) or {item.get("evidence_id") for item in evidence} != set(gate.get("allowed_evidence_ids", [])):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_GATE_INVALID")
    for fact in evidence:
        for key in ("source_id", "as_of", "retrieved_at"):
            if not isinstance(fact.get(key), str) or not fact[key]:
                raise MultidimensionalStageError(f"MULTIDIMENSIONAL_PROVENANCE_MISSING:{key}")
        if parse_timestamp(fact["as_of"]) > cutoff_time or parse_timestamp(fact["retrieved_at"]) > cutoff_time:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_GATE_PIT_LEAKAGE")
    if stage not in {"MULTI_DIMENSIONAL_HOLDING_RESEARCH", "INDEPENDENT_COUNTER_THESIS_RESEARCH"}:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_STAGE_INVALID")
    if stage == "INDEPENDENT_COUNTER_THESIS_RESEARCH":
        for role, source_path in (
            ("COMPANY", company_research_run_path),
            ("MATERIALS", research_materials_run_path),
        ):
            if source_path is None:
                continue
            source_run = Path(source_path).resolve()
            source_manifest = _read_object(source_run / "run_manifest.json")
            source_gate = _read_object(source_run / "evidence/gate.json")
            if (source_run.parent != run_dir.parent
                    or source_manifest.get("run_id") != run_id
                    or source_gate.get("run_id") != run_id
                    or source_gate.get("decision_cutoff") != cutoff):
                raise MultidimensionalStageError(f"COUNTER_{role}_CROSS_RUN_IMPORT_FORBIDDEN")
    request_builder = (
        build_independent_counter_thesis_research_request
        if stage == "INDEPENDENT_COUNTER_THESIS_RESEARCH"
        else build_multidimensional_holding_research_request
    )
    request = request_builder(
        handoff, request_id=f"multidimensional:{run_id}",
        research_question=research_question, benchmark_id=benchmark_id,
    )
    common_ids = [
        item["security_id"] for item in handoff["portfolio"]["positions"]
        if item["asset_type"] == "COMMON_STOCK"
    ]
    if not common_ids:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_COMMON_STOCK_REQUIRED")
    issuer_documents_by_security = _issuer_documents_from_gate(
        evidence, security_ids=common_ids
    )
    peer_candidate_pool = None
    peer_groups: dict[str, dict[str, Any]] = {}
    if peer_candidate_pool_path is not None:
        from product.mcp.live.peer_candidates import validate_peer_candidate_pool
        peer_candidate_pool = _read_object(Path(peer_candidate_pool_path).resolve())
        validate_peer_candidate_pool(peer_candidate_pool)
        if parse_timestamp(peer_candidate_pool["retrieved_at"]) > cutoff_time:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_PEER_POOL_AFTER_CUTOFF")
        peer_groups = {item["security_id"]: item for item in peer_candidate_pool["groups"]}
        if set(peer_groups) != set(common_ids):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_PEER_POOL_SCOPE_INVALID")
    bindings = {
        "handoff_id": handoff["handoff_id"], "handoff_hash": handoff["handoff_hash"],
        "portfolio_hash": handoff["portfolio_hash"], "council_request_id": request["request_id"],
        "council_request_hash": request["request_hash"], "decision_cutoff": cutoff,
    }
    from product.runtime.research_input_topology import (
        load_research_input_topology,
        research_input_topology_lock,
    )
    topology = load_research_input_topology(repository_root)
    topology_lock = research_input_topology_lock(repository_root)
    from product.runtime.research_input_topology import build_research_provider_coverage
    capture_batches = _load_research_capture_batches(
        gate_path=resolved_gate_path, gate=gate, security_ids=common_ids,
    )
    provider_coverage = build_research_provider_coverage(
        repository_root,
        evidence=evidence,
        capture_batches=capture_batches,
        decision_cutoff=cutoff,
    )
    provider_coverage["capability_routing"] = _capability_routing_coverage(
        evidence, capture_batches=capture_batches, security_ids=common_ids,
        benchmark_id=benchmark_id,
    )
    provider_coverage["coverage_hash"] = canonical_hash({
        key: value for key, value in provider_coverage.items()
        if key != "coverage_hash"
    })
    configured_capability_bindings = dict(CAPABILITY_BINDINGS)
    for domain in topology["domains"]:
        for capability in domain["capabilities"]:
            configured_capability_bindings[capability["capability"]] = (
                capability["agent"], capability["skill"], capability["scope"]
            )
    agent_bindings = {
        name: _agent_binding(product_root, name)
        for name in {item[0] for item in configured_capability_bindings.values()}
    }
    skill_bindings = {
        item[1]: _skill_binding(product_root, item[1])
        for item in configured_capability_bindings.values()
    }
    run_dir.mkdir(parents=True)
    _write_object(run_dir / "audit/portfolio-handoff.json", handoff)
    _write_object(run_dir / "council-request.json", request)
    _write_object(run_dir / "evidence/gate.json", gate)
    _write_object(run_dir / "audit/provider-coverage.json", provider_coverage)
    if peer_candidate_pool is not None:
        _write_object(run_dir / "research/peer-candidate-pool.json", peer_candidate_pool)
    company_research_import = None
    if company_research_run_path is not None:
        company_research_import = _import_company_research_reports(
            source_run=company_research_run_path,
            target_run=run_dir,
            expected_handoff=handoff,
            expected_security_ids=common_ids,
            target_gate=gate,
        )
    research_materials_import = None
    if research_materials_run_path is not None:
        research_materials_import = _import_research_materials(
            source_run=research_materials_run_path, target_run=run_dir,
            expected_handoff=handoff, target_gate=gate,
            expected_security_ids=common_ids,
        )
    tasks: list[dict[str, Any]] = []
    ordinal = 0
    for capability in RESEARCH_CAPABILITIES:
        agent, skill_name, scope = configured_capability_bindings[capability]
        scopes = [(None, common_ids)] if scope == "SHARED_MARKET" else [(security_id, [security_id]) for security_id in common_ids]
        for security_id, security_ids in scopes:
            ordinal += 1
            task_id = _task_id(capability, security_id)
            invocation_id = f"{run_id}:{agent}:{task_id}"
            task_name = f"dimension_research_{ordinal}"
            fact_security_ids = list(security_ids)
            if (
                research_materials_import is not None
                and capability == "INDUSTRY_COMPARISON"
                and security_id
            ):
                fact_security_ids.extend(
                    item["materialized_security_id"]
                    for item in research_materials_import["peers_by_security"].get(security_id, [])
                    if isinstance(item.get("materialized_security_id"), str)
                )
            analysis_facts = _facts_for_capability(
                evidence, capability=capability,
                security_ids=fact_security_ids, benchmark_id=benchmark_id,
            )
            if capability in {"MACRO_CONTEXT", "MARKET_STATE"}:
                analysis_facts = sorted(
                    [
                        *analysis_facts,
                        *_macro_company_context_facts(
                            evidence, security_ids=common_ids
                        ),
                    ],
                    key=lambda item: str(item.get("evidence_id")),
                )
            # 技术统计已经由确定性产物承载完整 Evidence lineage；把数千条
            # 日线 ID 再塞给 Agent 只会放大上下文并诱发空查询。行业比较则
            # 每个口径保留最近两条，既保留期间/修订辨析又避免把整个 Gate
            # 重复注入每个子 Agent。
            facts = (
                [] if capability == "TECHNICAL_STRUCTURE"
                else _bounded_latest_facts(analysis_facts)
                if capability in {"INDUSTRY_COMPARISON", "MARKET_STATE"}
                else analysis_facts
            )
            allowed_ids = [item["evidence_id"] for item in facts]
            dependencies: list[str] = []
            if capability == "RESEARCH_REPORT" and security_id:
                dependencies = [_task_id("FUNDAMENTAL_EVENT", security_id)]
            task = {
                "task_id": task_id, "task_name": task_name, "run_id": run_id,
                "invocation_id": invocation_id, "agent": agent, "skill_name": skill_name,
                "capability": capability, "scope": scope, "security_ids": security_ids,
                "depends_on": dependencies, "allowed_evidence_ids": allowed_ids,
                "time_context": {
                    "window_start": None, "window_end": cutoff,
                    "benchmark_id": benchmark_id if capability in {"TECHNICAL_STRUCTURE", "INDUSTRY_COMPARISON", "MARKET_STATE"} else None,
                    "price_adjustment": "ADJUSTED_CLOSE" if capability == "TECHNICAL_STRUCTURE" else None,
                    "timezone": "America/New_York" if capability == "TECHNICAL_STRUCTURE" else "UTC",
                },
                "provider_coverage_ref": "audit/provider-coverage.json",
                "provider_scope": sorted(_provider_scope(capability)),
            }
            if stage == "MULTI_DIMENSIONAL_HOLDING_RESEARCH" and capability in {
                "MACRO_CONTEXT", "MARKET_STATE",
            }:
                task["provider_coverage_view_kind"] = "TASK_SCOPED_PROVIDER_COVERAGE"
            if research_materials_import is not None and capability == "RESEARCH_REPORT" and security_id:
                task["allowed_documents"] = [
                    item["report_document"]
                    for item in [
                        *issuer_documents_by_security.get(security_id, []),
                        *research_materials_import["documents_by_security"].get(security_id, []),
                    ]
                ]
            elif capability == "RESEARCH_REPORT" and security_id:
                task["allowed_documents"] = [
                    item["report_document"]
                    for item in issuer_documents_by_security.get(security_id, [])
                ]
            elif research_materials_import is not None and capability in {"MACRO_CONTEXT", "MARKET_STATE"}:
                task["allowed_documents"] = [
                    item["report_document"]
                    for item in research_materials_import["documents_by_capability"].get(capability, [])
                ]
            else:
                task["allowed_documents"] = []
            if research_materials_import is not None and capability == "INDUSTRY_COMPARISON" and security_id:
                task["selected_peer_candidates"] = copy.deepcopy(
                    research_materials_import["peers_by_security"].get(security_id, [])
                )
            if research_materials_import is not None and capability in {"MACRO_CONTEXT", "MARKET_STATE"}:
                task["material_preparation"] = copy.deepcopy(
                    research_materials_import["shared_preparation_by_capability"].get(capability)
                )
            elif research_materials_import is not None and security_id:
                if capability == "RESEARCH_REPORT":
                    task["material_preparation"] = copy.deepcopy(
                        research_materials_import["report_preparation_by_security"].get(security_id)
                    )
                elif capability == "INDUSTRY_COMPARISON":
                    task["material_preparation"] = copy.deepcopy(
                        research_materials_import["peer_preparation_by_security"].get(security_id)
                    )
                    frozen_peer_ids = [
                        item["materialized_security_id"]
                        for item in task.get("selected_peer_candidates", [])
                        if item.get("materialization_status") == "FROZEN"
                        and isinstance(item.get("materialized_security_id"), str)
                    ]
                    if isinstance(task.get("material_preparation"), dict):
                        task["material_preparation"]["materialization_status"] = (
                            "FROZEN" if frozen_peer_ids else "NOT_MATERIALIZED"
                        )
                        task["material_preparation"]["materialized_security_ids"] = frozen_peer_ids
            if capability == "INDUSTRY_COMPARISON" and security_id:
                task["peer_candidate_group"] = (
                    None if task.get("selected_peer_candidates")
                    else copy.deepcopy(peer_groups.get(security_id))
                )
            prepared_analysis: dict[str, Any] = {
                "calculation": None, "chart": None, "gaps": [],
                "allowed_artifact_refs": [],
            }
            if capability == "TECHNICAL_STRUCTURE" and security_id:
                prepared_analysis = _prepare_technical_artifacts(
                    run_dir,
                    task_id=task_id,
                    security_id=security_id,
                    benchmark_id=benchmark_id,
                    evidence=analysis_facts,
                    as_of=cutoff,
                )
            elif capability == "MARKET_STATE":
                prepared_analysis = _prepare_macro_market_artifacts(
                    run_dir,
                    task_id=task_id,
                    benchmark_id=benchmark_id,
                    evidence=evidence,
                    as_of=cutoff,
                )
            task["allowed_artifact_refs"] = prepared_analysis["allowed_artifact_refs"]
            task["task_hash"] = canonical_hash(task)
            task_path = f"research/tasks/{canonical_hash({'task_id': task_id})}.json"
            _write_object(run_dir / task_path, task)
            skill = skill_bindings[skill_name]
            instruction = (
                "只分析本任务指定维度并回答 minimum_questions。只使用 Gate 允许的原始 evidence_id；"
                "禁止拼接来源、时间或说明。没有足够资料时输出具体 gap 及影响，不能使用模型记忆补齐。"
                " claims 中每条主张必须保留非空 question、statement 和 kind，并且 question 对应本任务"
                "实际回答的 minimum_questions；不得省略问题字段。"
                " 顶层只能包含 output_schema 声明的 draft 字段；不得补写 schema_version、report_id、"
                "capability、scope、security_ids、bindings、time_context、execution 或 report_hash，"
                "这些冻结字段由确定性封装器添加。"
                " limitations 必须是纯字符串数组；observation_conditions 与 data_gaps 必须是"
                " output_schema 定义的对象数组，不能把 limitation 写成对象或把 gap 写成字符串；"
                "每个 data_gaps 项都必须包含 gap_id、reason_code、description、impact。"
                "不得生成 action、目标仓位、推荐数量、对冲或订单。"
                " provider_coverage 是本批次的来源观测而非能力宣传；必须按 observed_status、"
                "failure_codes 和 dataset_observations 处理缺口。Moomoo 补充层失败时仍可使用"
                "已通过 Gate 的 SEC/Yahoo Evidence，不得回退到客户端 Cookie、私有 API 或登录绕过。"
            )
            scoped_provider_view = (
                stage == "MULTI_DIMENSIONAL_HOLDING_RESEARCH"
                and capability in {"MACRO_CONTEXT", "MARKET_STATE"}
            )
            if scoped_provider_view:
                instruction += SCOPED_PROVIDER_VIEW_INSTRUCTION
                if capability == "MACRO_CONTEXT":
                    instruction += (
                        " 描述当前宏观状态前，须在允许的冻结 Evidence 中按指标核对截止点内"
                        "最新可用观察及其观察期；引用较早观察时说明用途和更新观察对解释的影响。"
                        "actual、previous、consensus 分开读取；供应商当前快照不能冒充历史发布时点的原始版本。"
                    )
            if stage == "INDEPENDENT_COUNTER_THESIS_RESEARCH":
                instruction += (
                    " 本阶段的 allowed_evidence_ids 是可查询目录，不是已经读过的证据。"
                    "输出前逐项核对 claims、observation_conditions 和其他 evidence_refs："
                    "凡要引用的 evidence_id，必须由本 Invocation 先通过非空 fixture_runtime.query 实际读取；"
                    "未查询的 ID 不得引用，也不得从目录或 prepared_analysis 猜测其事实内容。"
                    "若查询预算或资料限制阻止核验，删去该事实性主张并如实记录 gap。"
                )
            frozen_peer_candidates: list[dict[str, Any]] = []
            if capability == "INDUSTRY_COMPARISON":
                frozen_peer_candidates = _frozen_peer_candidates(task)
                instruction += (
                    " peer_candidate_group 只是 NASDAQ 目录形成的未核实候选池，可用于提出最多三个"
                    "有理由的候选，不是同行事实或最终选择。候选尚未由只读工具核实身份、取得资料并"
                    "重新通过 Gate 时，不得引用其目录字段形成比较主张；应保留具体资料准备缺口。"
                )
                if frozen_peer_candidates:
                    instruction += (
                        " selected_peer_candidates 已记录 LLM 的候选选择；其中 materialization_status=FROZEN"
                        " 且 materialized_security_id 出现在本任务 Evidence 的项目已经完成身份、采集与 PIT 冻结，"
                        "必须作为正式比较候选读取其 Evidence。准备阶段原先的 UNVERIFIED_PEER_CANDIDATES gap"
                        "只描述物化前状态，不得覆盖当前 materialization_status。目录市值、行业标签仍只用于"
                        "说明选择过程，不能替代已核实的经营或估值事实。调用 query 时只选与比较问题直接相关的"
                        "非空 evidence_ids 子集，禁止发送空数组。"
                    )
                else:
                    instruction += (
                        " 本任务没有完成身份核验与 PIT 冻结的 selected_peer_candidates，因此 claims 必须为空；"
                        "必须用 data_gaps 明确记录缺少可比较同行 Evidence 的原因和影响。不得仅凭目标公司资料、"
                        "候选目录或模型记忆形成任何行业比较主张。"
                    )
            if capability == "TECHNICAL_STRUCTURE":
                if prepared_analysis["calculation"] is None:
                    missing = []
                    if not prepared_analysis["security_row_count"]:
                        missing.append(f"证券 {security_id}")
                    if not prepared_analysis["benchmark_row_count"]:
                        missing.append(f"基准 {benchmark_id}")
                    instruction += (
                        f" 本任务缺少冻结的{'、'.join(missing)}日线序列，prepared_analysis.calculation=null，"
                        "没有可引用的确定性计算或图表。必须输出 status=INSUFFICIENT_EVIDENCE、"
                        "sufficiency=INSUFFICIENT、claims=[]、calculations=[]、artifact_refs=[]；"
                        "在 data_gaps 中准确指出缺失序列及其对趋势、相对表现、波动、回撤和量价研究的影响。"
                        "不要把‘无法判断’写成无引用 Claim，也不得跨 run 补数据或伪造引用。"
                    )
                else:
                    instruction += (
                        " 本任务的 prepared_analysis.calculation 是确定性计算产物，完整原始 Evidence lineage"
                        "保存在 calculation_ref 指向的文件并以 evidence_fact_count/evidence_fact_ids_hash 锁定。"
                        "直接使用其中 windows、口径、artifact_id 与 artifact_ref 形成计算引用；"
                        "仅在 prepared_analysis.chart 存在时引用同源图表；若 chart=null，只记录具体图表 gap，"
                        "保留有效 calculation 与有计算引用的 Claims，不把缺图写成缺少计算资料。"
                    )
                instruction += (
                    " 本任务不提供原始 allowed_evidence_ids，因此不得调用空 evidence_ids 的 query，"
                    "也不得把没有原始查询误报为工具不可用。"
                )
            if capability == "RESEARCH_REPORT":
                company_facts = [
                    fact for fact in facts if fact.get("security_id") == security_id
                ]
                task["company_material_coverage"] = {
                    "issuer_body_count": len(issuer_documents_by_security.get(security_id, [])),
                    "independent_body_count": (
                        len(research_materials_import["documents_by_security"].get(security_id, []))
                        if research_materials_import is not None else 0
                    ),
                    "guidance_evidence_ids": sorted(
                        fact["evidence_id"] for fact in company_facts
                        if fact.get("semantic_field") == "sec_issuer_guidance_candidate_text"
                    ),
                    "expectation_evidence_ids": sorted(
                        fact["evidence_id"] for fact in company_facts
                        if str(fact.get("semantic_field", "")).startswith((
                            "yahoo_earnings_trend", "yahoo_recommendation_trend",
                            "moomoo_analyst_consensus",
                        ))
                    ),
                    "classification_policy": {
                        "ISSUER_MATERIAL": "SEC Gate-verified issuer/IR body",
                        "INDEPENDENT_RESEARCH": "separately fetched BODY_VERIFIED public research",
                        "EXPECTATION": "third-party snapshot Evidence, never issuer guidance",
                    },
                }
                instruction += (
                    " verified_documents 是资料准备阶段通过正文工具取得并冻结的唯一可用研报；"
                    "documents 必须逐字复制其 report_document 元数据。正文不足时输出 SOURCE_LIMITED，"
                    "不得把搜索线索、标题摘要或模型记忆冒充已读正文。若 material_preparation.status"
                    " 为 BLOCKED_CONFIGURATION，正式报告必须输出 FAILED / evaluation_status=FAIL，并逐项"
                    "保留配置缺口，不能改写成 SOURCE_LIMITED。"
                )
            if capability in {"MACRO_CONTEXT", "MARKET_STATE"}:
                instruction += (
                    " verified_documents 仅包含已通过正文核验且与当前能力匹配的"
                    "策略或政策材料；documents 必须逐字复制 report_document 元数据，并用"
                    " research_relationships 明确标记它是外部观点、支持或冲突，不得将"
                    "外部观点自动升级为事实。一个能力的材料不得借给另一个能力。"
                )
            if capability == "MACRO_CONTEXT":
                instruction += (
                    " 本任务只形成宏观环境报告。allowed_evidence_ids 同时包含官方宏观事实与按证券分组的精选公司事实。"
                    "必须区分观察期、发布时间、获取时间和修订边界，不得用市场价格走势替代政策或经济活动事实。"
                )
                instruction += (
                    "当前有多只普通股持仓：必须读取至少两只持仓的公司事实，比较其利率、通胀或经济活动敏感性；"
                    "至少形成一组有区别的公司传导机制，不能只说所有公司都受融资条件影响。"
                    if len(security_ids) >= 2 else
                    "当前只有一只普通股持仓：必须解释该公司的利率、通胀或经济活动敏感性、传导假设与反向情景；"
                    "不得因缺少第二只持仓而判定资料不足，也不得自动补入另一家公司。"
                )
                instruction += (
                    "不得仅凭 ticker、行业常识或相同宏观套话推断。Evidence 不足时明确列出具体公司缺口。"
                )
            if capability == "MARKET_STATE":
                instruction += (
                    " 本任务只形成共享市场状态报告。prepared_analysis.calculation 是广泛市场基准的确定性"
                    "市场状态产物；有完整窗口时必须使用其收益、波动和回撤，并通过 calculation.artifact_ref"
                    "引用。跨资产、板块、波动或信用指标必须保留原指标或代理身份，不得把股票波动称为信用。"
                )
                instruction += (
                    "当前有多只普通股持仓：必须读取持仓相关公司暴露事实并解释差异化传导；"
                    if len(security_ids) >= 2 else
                    "当前只有一只普通股持仓：必须解释该公司对当前市场状态的暴露、传导假设与反向情景；"
                    "不得因缺少第二只持仓而判定资料不足，也不得自动补入另一家公司。"
                )
                instruction += "不得用主观风险标签替代计算和冻结 Evidence。"
            if task.get("material_preparation", {}).get("status") == "FAILED":
                instruction += (
                    " material_preparation 已记录上游资料准备的确定性失败；本维度必须输出"
                    " FAILED / evaluation_status=FAIL，并保留 failure_code 与具体影响，不得将"
                    "实现或契约失败伪装成 SOURCE_LIMITED。"
                )
            input_refs = [
                "audit/portfolio-handoff.json", "council-request.json",
                "evidence/gate.json", "audit/provider-coverage.json", task_path,
            ]
            if capability == "INDUSTRY_COMPARISON" and peer_candidate_pool is not None:
                input_refs.append("research/peer-candidate-pool.json")
            output_schema = _dynamic_draft_schema(
                repository_root, run_id=run_id, invocation_id=invocation_id,
                agent=agent, allowed_evidence_ids=allowed_ids,
                allowed_artifact_refs=task["allowed_artifact_refs"],
                allowed_documents=task["allowed_documents"],
                claims_forbidden=(
                    capability == "INDUSTRY_COMPARISON"
                    and not frozen_peer_candidates
                ),
                technical_calculation_missing=(
                    capability == "TECHNICAL_STRUCTURE"
                    and prepared_analysis["calculation"] is None
                ),
            )
            output_contract = topology_lock["output_contracts"].get(
                capability, topology_lock.get("default_output_contract")
            )
            if not isinstance(output_contract, Mapping):
                raise MultidimensionalStageError(
                    f"MULTIDIMENSIONAL_OUTPUT_CONTRACT_MISSING:{capability}"
                )
            invocation = {
                "schema_version": "multidimensional-research-invocation/2.0.0",
                "run_id": run_id, "invocation_id": invocation_id,
                "task_id": task_id, "agent_binding": agent_bindings[agent], "skill": skill,
                "model": selected_model, "prompt_hash": canonical_hash({"instruction": instruction, "questions": MINIMUM_QUESTIONS[capability]}),
                "input_refs": input_refs,
                "tool_permissions": ["fixture_evidence.query"],
                "analysis_mode": "FORMAL_GATE_ONLY",
                "research_input_topology": {
                    "profile_id": topology_lock["profile_id"],
                    "topology_hash": topology_lock["topology_hash"],
                    "lock_hash": topology_lock["lock_hash"],
                },
                "output_contract": {
                    **copy.deepcopy(output_contract),
                    "draft_schema_version": output_schema["$id"],
                    "draft_schema_hash": canonical_hash(output_schema),
                },
            }
            invocation["manifest_hash"] = canonical_hash(invocation)
            invocation_path = f"invocations/by-id/{canonical_hash({'invocation_id': invocation_id})}.json"
            _write_object(run_dir / invocation_path, invocation)
            packet = {
                "dispatch_contract": DISPATCH_VERSION,
                "identity": {"run_id": run_id, "invocation_id": invocation_id, "task_id": task_id,
                             "task_name": task_name, "agent": agent, "security_ids": security_ids},
                "instruction": instruction,
                "minimum_questions": MINIMUM_QUESTIONS[capability],
                "task": task,
                "allowed_evidence_ids": allowed_ids,
                "allowed_artifact_refs": task["allowed_artifact_refs"],
                "prepared_analysis": prepared_analysis,
                "peer_candidate_group": copy.deepcopy(
                    task.get("peer_candidate_group")
                    if capability == "INDUSTRY_COMPARISON" and security_id else None
                ),
                "selected_peer_candidates": copy.deepcopy(task.get("selected_peer_candidates", [])),
                "material_preparation": copy.deepcopy(task.get("material_preparation")),
                "company_material_coverage": copy.deepcopy(task.get("company_material_coverage")),
                "verified_documents": copy.deepcopy(
                    [
                        *issuer_documents_by_security.get(security_id, []),
                        *(
                            research_materials_import["documents_by_security"].get(security_id, [])
                            if research_materials_import is not None else []
                        ),
                    ]
                    if capability == "RESEARCH_REPORT" and security_id
                    else research_materials_import["documents_by_capability"].get(capability, [])
                    if research_materials_import is not None and capability in {"MACRO_CONTEXT", "MARKET_STATE"}
                    else []
                ),
                "evidence_catalog": [
                    {key: fact.get(key) for key in ("evidence_id", "security_id", "semantic_field", "source_id", "as_of", "published_at", "retrieved_at", "unit", "usage")}
                    for fact in facts
                ],
                "citation_contract": {
                    "version": "exact-evidence-citation/1.0.0",
                    "required_form": "FULL_EVIDENCE_ID_FROM_TOOL_RESULT",
                    "instruction": (
                        "evidence_refs 必须逐字复制本 Invocation 工具结果返回的完整 evidence_id；"
                        "不得缩短、改写、手工补全或用相似字符串替换。无法取得完整原值时保留 gap。"
                    ),
                    "aliases": {},
                },
                "tool_context": {
                    "source_mode": "frozen-gate", "mcp_server": "fixture_runtime",
                    "query_tool": "fixture_runtime.query", "logical_permissions": invocation["tool_permissions"],
                    "required_identity_arguments": {"run_id": run_id, "agent": agent, "invocation_id": invocation_id},
                },
                "research_input_topology": copy.deepcopy(invocation["research_input_topology"]),
                "provider_coverage": _task_provider_coverage_view(
                    provider_coverage, task=task, evidence=evidence, stage=stage,
                ) if scoped_provider_view else {
                    "schema_version": provider_coverage["schema_version"],
                    "coverage_hash": provider_coverage["coverage_hash"],
                    "fallback_policy": copy.deepcopy(provider_coverage["fallback_policy"]),
                    "capability_routing": copy.deepcopy(
                        provider_coverage["capability_routing"]
                    ),
                    "providers": [
                        copy.deepcopy(item) for item in provider_coverage["providers"]
                        if item["provider"] in task["provider_scope"]
                    ],
                },
                "output_schema": output_schema,
                "output_schema_hash": canonical_hash(output_schema),
            }
            packet_path = f"research/dispatch-packets/{canonical_hash({'packet': invocation_id})}.json"
            _write_object(run_dir / packet_path, packet)
            tasks.append({
                **task, "task_path": task_path, "invocation_path": invocation_path,
                "packet_path": packet_path, "packet_hash": canonical_hash(packet),
            })
    index = {
        "schema_version": DISPATCH_VERSION, "run_id": run_id,
        "target_concurrency": target_concurrency, "tasks": tasks,
    }
    index["index_hash"] = canonical_hash(index)
    _write_object(run_dir / "research/dispatch-index.json", index)
    manifest = {
        "schema_version": STAGE_VERSION, "run_id": run_id,
        "stage": stage, "source_mode": "frozen-gate",
        "model": selected_model, "parent_model": selected_model, "output_dir": str(run_dir),
        "discovery": {"product_root": str(product_root)},
        "research_input_topology": topology_lock,
        "provider_coverage_hash": provider_coverage["coverage_hash"],
        "provider_coverage_ref": "audit/provider-coverage.json",
        "agent_bindings": agent_bindings, "skill_bindings": skill_bindings,
        "handoff_hash": handoff["handoff_hash"], "portfolio_hash": handoff["portfolio_hash"],
        "council_request_hash": request["request_hash"], "gate_hash": gate["bundle_hash"],
        "dispatch_index_hash": index["index_hash"], "target_concurrency": target_concurrency,
        "peer_candidate_pool_hash": (
            peer_candidate_pool["pool_hash"] if peer_candidate_pool is not None else None
        ),
        "company_research_import_hash": (
            company_research_import["import_hash"] if company_research_import is not None else None
        ),
        "research_materials_import_hash": (
            research_materials_import["import_hash"] if research_materials_import is not None else None
        ),
        "prepared_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "complete_portfolio_decision": False, "downstream_stages_started": [],
    }
    manifest["manifest_hash"] = canonical_hash(manifest)
    _write_object(run_dir / "run_manifest.json", manifest)
    return {"status": "PREPARED", "run_id": run_id, "run_dir": str(run_dir), "task_count": len(tasks)}


def build_multidimensional_stage_prompt(repository_root: Path, run_dir: Path) -> str:
    del repository_root
    index = _read_object(Path(run_dir).resolve() / "research/dispatch-index.json")
    task_map = {
        item["task_name"]: {
            "agent_type": item["agent"],
            "depends_on_task_names": [
                candidate["task_name"] for dependency in item["depends_on"]
                for candidate in index["tasks"] if candidate["task_id"] == dependency
            ],
            "message": build_multidimensional_dispatch_message(Path(), Path(run_dir), item["task_name"]),
        }
        for item in index["tasks"]
    }
    return f"""你是多维持仓研究阶段的 Codex 主线程，只负责按依赖有界派发和归集，不担任 CIO。
读取 product/AGENTS.md 与 portfolio-council Skill 的多维持仓研究阶段。严格使用以下任务映射：
{json.dumps(task_map, ensure_ascii=False, sort_keys=True)}

使用 Agent 工具，agent_type、task_name 和 message 必须逐项来自映射，fork_turns=none。最多同时保持 {min(index['target_concurrency'], len(task_map))} 个活跃 Subagent；只有 depends_on_task_names 全部结束且报告已保存后才能启动依赖任务。依赖任务已经结束但没有保存合法报告时，对每个直接依赖任务只尝试派发一次，让 Hook 留下 dependency-blocked 拒绝记录；不得重试该任务，也不得启动其子 Agent。具备条件的独立任务先填满槽位，任一结束后立即补位。不得复制冻结资料到启动消息，不得启动 runtime_skeptic、runtime_cio 或 Risk，不得改写 Specialist 输出。

每次派发后必须通过 wait 等待终态；并发槽位不足时先等待再补位，不得把已启动计作已完成。
在仍有活跃 Subagent、已启动任务缺少 SubagentStop，或任一任务既没有子 Agent 终态也没有 dependency-blocked Hook 拒绝时禁止返回父结果。
全部任务形成合法报告、显式失败或 dependency-blocked 终态后，只返回：{{"stage":"MULTI_DIMENSIONAL_HOLDING_RESEARCH","run_id":"{index['run_id']}","dispatched":{len(task_map)},"completed":{len(task_map)}}}。这里 completed 表示调度终态齐全，不表示所有研究报告均成功；最终状态由确定性 Finalizer 复核。
"""


def _target_task_closure(index: Mapping[str, Any], task_name: str) -> list[dict[str, Any]]:
    """按依赖先行顺序返回目标任务的最小闭包。"""

    tasks = index.get("tasks")
    if not isinstance(tasks, list):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_DISPATCH_INDEX_INVALID")
    by_name = {
        item.get("task_name"): item for item in tasks
        if isinstance(item, Mapping) and isinstance(item.get("task_name"), str)
    }
    by_id = {
        item.get("task_id"): item for item in tasks
        if isinstance(item, Mapping) and isinstance(item.get("task_id"), str)
    }
    target = by_name.get(task_name)
    if target is None:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_TARGET_TASK_UNKNOWN")
    ordered: list[dict[str, Any]] = []
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task: Mapping[str, Any]) -> None:
        task_id = str(task["task_id"])
        if task_id in visited:
            return
        if task_id in visiting:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_DEPENDENCY_CYCLE")
        visiting.add(task_id)
        dependencies = task.get("depends_on", [])
        if not isinstance(dependencies, list):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_DEPENDENCY_INVALID")
        for dependency_id in dependencies:
            dependency = by_id.get(dependency_id)
            if dependency is None:
                raise MultidimensionalStageError(
                    f"MULTIDIMENSIONAL_DEPENDENCY_UNKNOWN:{dependency_id}"
                )
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)
        ordered.append(dict(task))

    visit(target)
    return ordered


def build_multidimensional_task_prompt(
    repository_root: Path, run_dir: Path, task_name: str,
) -> str:
    """构造目标维度及其依赖闭包的定点补证 Prompt。"""

    del repository_root
    index = _read_object(Path(run_dir).resolve() / "research/dispatch-index.json")
    closure = _target_task_closure(index, task_name)
    if len(closure) == 1:
        task = closure[0]
        message = build_multidimensional_dispatch_message(Path(), Path(run_dir), task_name)
        return f"""你是多维持仓研究阶段的 Codex 主线程。本次只执行一个独立维度的定点补证，不担任 CIO。
读取 product/AGENTS.md 与 portfolio-council Skill 的多维持仓研究阶段。
使用 Agent 工具且只派发一次：agent_type={task['agent']}，task_name={task_name}，fork_turns=none，message={json.dumps(message, ensure_ascii=False)}。
等待该 Subagent 形成终态；不得启动映射外任务、runtime_skeptic、runtime_cio 或 Risk，不得改写 Specialist 输出。
完成后只返回：{{"stage":"MULTI_DIMENSIONAL_HOLDING_RESEARCH","run_id":"{index['run_id']}","dispatched":1,"completed":1}}。
"""
    closure_ids = {item["task_id"] for item in closure}
    task_map = {
        item["task_name"]: {
            "agent_type": item["agent"],
            "depends_on_task_names": [
                candidate["task_name"] for dependency_id in item.get("depends_on", [])
                for candidate in closure if candidate["task_id"] == dependency_id
            ],
            "message": build_multidimensional_dispatch_message(
                Path(), Path(run_dir), item["task_name"]
            ),
        }
        for item in closure if item["task_id"] in closure_ids
    }
    return f"""你是多维持仓研究阶段的 Codex 主线程。本次只执行目标任务及其最小依赖闭包，不担任 CIO。
读取 product/AGENTS.md 与 portfolio-council Skill 的多维持仓研究阶段。严格使用以下任务映射：
{json.dumps(task_map, ensure_ascii=False, sort_keys=True)}

按 depends_on_task_names 顺序逐个派发，任一时刻最多一个活跃 Subagent。每次使用 Agent 工具时，agent_type、task_name 和 message 必须来自映射，fork_turns=none。只有直接依赖已经结束且合法报告已保存，才能派发下游；若上游失败，只对下游尝试一次派发，让 Hook 留下 dependency-blocked 拒绝记录，不得跨批次复制或注入报告。
每次派发后使用 wait 等待真实终态；不得启动映射外任务、runtime_skeptic、runtime_cio 或 Risk，不得改写 Specialist 输出。
全部 {len(closure)} 个任务形成合法报告、显式失败或 dependency-blocked 终态后，只返回：{{"stage":"MULTI_DIMENSIONAL_HOLDING_RESEARCH","run_id":"{index['run_id']}","dispatched":{len(closure)},"completed":{len(closure)}}}。
"""


def finalize_multidimensional_task_evidence(
    repository_root: Path, run_dir: Path, task_name: str, *,
    invocation_dir: Path | None = None,
) -> dict[str, Any]:
    """验证目标任务及其依赖闭包的真实派发、合法报告与 Evidence Closure。"""

    from product.council.multidimensional_research import validate_research_dimension_report

    del repository_root
    run_dir = Path(run_dir).resolve()
    invocation_dir = (
        run_dir / "invocation" if invocation_dir is None else Path(invocation_dir).resolve()
    )
    if not invocation_dir.is_relative_to(run_dir / "invocation"):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_TARGET_INVOCATION_PATH_INVALID")
    index = _read_object(run_dir / "research/dispatch-index.json")
    closure = _target_task_closure(index, task_name)
    expected_names = [item["task_name"] for item in closure]
    expected_ids = {item["task_id"] for item in closure}
    dispatches = [
        json.loads(line)
        for line in (invocation_dir / "subagent-dispatches.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    allowed_names = [
        item.get("task_name") for item in dispatches if item.get("decision") == "ALLOW"
    ]
    if allowed_names != expected_names:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_TARGET_DISPATCH_INVALID")
    events = [
        json.loads(line)
        for line in (invocation_dir / "subagent-events.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    saved = [
        item for item in events
        if item.get("hook_event_name") == "SubagentStop"
        and item.get("output_capture", {}).get("status") == "SAVED"
    ]
    saved_by_task = {
        item.get("output_capture", {}).get("task_id"): item for item in saved
        if item.get("output_capture", {}).get("task_id") in expected_ids
    }
    if len(saved) != len(closure) or set(saved_by_task) != expected_ids:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_TARGET_OUTPUT_INVALID")
    handoff = _read_object(run_dir / "audit/portfolio-handoff.json")
    request = _read_object(run_dir / "council-request.json")
    gate = _read_object(run_dir / "evidence/gate.json")
    bindings = {
        "handoff_id": handoff["handoff_id"],
        "handoff_hash": handoff["handoff_hash"],
        "portfolio_hash": handoff["portfolio_hash"],
        "council_request_id": request["request_id"],
        "council_request_hash": request["request_hash"],
        "decision_cutoff": gate["decision_cutoff"],
    }
    security_ids = [
        item["security_id"] for item in handoff["portfolio"]["positions"]
        if item["asset_type"] == "COMMON_STOCK"
    ]
    validated_reports: dict[str, dict[str, Any]] = {}
    report_inventory: list[dict[str, Any]] = []
    for task in closure:
        event = saved_by_task[task["task_id"]]
        report_path = run_dir / event["output_capture"]["path"]
        report = _read_object(report_path)
        dependency_claim_ids = [
            claim["claim_id"]
            for dependency_id in task.get("depends_on", [])
            for claim in validated_reports[dependency_id].get("claims", [])
        ]
        validate_research_dimension_report(
            report,
            expected_bindings=bindings,
            allowed_security_ids=security_ids,
            allowed_evidence_ids=task["allowed_evidence_ids"],
            known_research_claim_ids=dependency_claim_ids,
            allowed_documents=task.get("allowed_documents", []),
        )
        if (
            report.get("capability") != task["capability"]
            or report.get("security_ids") != task["security_ids"]
            or report.get("invocation_id") != task["invocation_id"]
        ):
            raise MultidimensionalStageError(
                "MULTIDIMENSIONAL_TARGET_REPORT_BINDING_INVALID"
            )
        validated_reports[task["task_id"]] = report
        report_inventory.append({
            "task_name": task["task_name"],
            "task_id": task["task_id"],
            "capability": task["capability"],
            "report_status": report["status"],
            "report_ref": str(report_path.relative_to(run_dir)),
            "report_file_hash": file_hash(report_path),
            "report_hash": report["report_hash"],
        })
    target = closure[-1]
    target_report = validated_reports[target["task_id"]]
    target_record = report_inventory[-1]
    proof = {
        "schema_version": "multidimensional-task-execution-proof/2.0.0",
        "status": "PASSED",
        "scope": (
            "SINGLE_TASK_EVIDENCE" if len(closure) == 1
            else "DEPENDENCY_CHAIN_EVIDENCE"
        ),
        "run_id": index["run_id"],
        "task_name": task_name,
        "task_id": target["task_id"],
        "capability": target["capability"],
        "report_status": target_report["status"],
        "report_ref": target_record["report_ref"],
        "report_file_hash": target_record["report_file_hash"],
        "report_hash": target_report["report_hash"],
        "task_names": expected_names,
        "report_inventory": report_inventory,
        "dependency_chain_complete": True,
        "dispatch_events_hash": file_hash(
            invocation_dir / "subagent-dispatches.jsonl"
        ),
        "subagent_events_hash": file_hash(
            invocation_dir / "subagent-events.jsonl"
        ),
        "gate_hash": gate["bundle_hash"],
        "complete_holding_research_bundle": False,
        "downstream_models_started": [],
    }
    proof["proof_hash"] = canonical_hash(proof)
    proof_path = (
        run_dir / "research/task-execution-proof.json"
        if invocation_dir == run_dir / "invocation"
        else invocation_dir / "task-execution-proof.json"
    )
    _write_object(proof_path, proof)
    return proof


def finalize_multidimensional_stage_run(
    repository_root: Path, run_dir: Path, *,
    adopted_invocation_dirs: Sequence[Path] = (),
) -> dict[str, Any]:
    """重验每个维度报告并组装不含投资动作的 HoldingResearchBundle。"""

    from product.council.multidimensional_output import render_holding_research_bundle_markdown
    from product.council.multidimensional_research import (
        BUNDLE_CAPABILITIES,
        HOLDING_RESEARCH_BUNDLE_VERSION,
        derive_unresolved_research_questions,
        finalize_holding_research_bundle,
        validate_holding_research_bundle,
        validate_research_dimension_report,
    )

    del repository_root
    run_dir = Path(run_dir).resolve()
    manifest = _read_object(run_dir / "run_manifest.json")
    handoff = _read_object(run_dir / "audit/portfolio-handoff.json")
    council_request = _read_object(run_dir / "council-request.json")
    gate = _read_object(run_dir / "evidence/gate.json")
    index = _read_object(run_dir / "research/dispatch-index.json")
    event_path = run_dir / "invocation/subagent-events.jsonl"
    dispatch_path = run_dir / "invocation/subagent-dispatches.jsonl"
    if not event_path.is_file() or not dispatch_path.is_file():
        raise MultidimensionalStageError("MULTIDIMENSIONAL_EXECUTION_EVENTS_MISSING")
    invocation_dirs = [run_dir / "invocation"]
    for directory in adopted_invocation_dirs:
        resolved = Path(directory).resolve()
        if (not resolved.is_relative_to(run_dir / "invocation/retries")
                or not (resolved / "task-execution-proof.json").is_file()):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_RETRY_ADOPTION_INVALID")
        invocation_dirs.append(resolved)
    events = [
        json.loads(line)
        for directory in invocation_dirs
        for line in (directory / "subagent-events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    dispatches = [
        json.loads(line)
        for directory in invocation_dirs
        for line in (directory / "subagent-dispatches.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    expected_names = {item["task_name"] for item in index["tasks"]}
    allowed_names = {
        item.get("task_name") for item in dispatches
        if item.get("decision") == "ALLOW"
    }
    denied_dependency_names = {
        item.get("task_name") for item in dispatches
        if item.get("decision") == "DENY_DISPATCH_CONTRACT"
        and item.get("dispatch_binding", {}).get("failure_code")
        == "RESEARCH_DEPENDENCY_NOT_READY"
    }
    if not allowed_names <= expected_names or not denied_dependency_names <= expected_names:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_DISPATCH_PROOF_INVALID")
    completed_events = {
        item.get("output_capture", {}).get("task_id"): item
        for item in events
        if item.get("hook_event_name") == "SubagentStop"
        and item.get("output_capture", {}).get("status") == "SAVED"
    }
    task_by_invocation = {
        item["invocation_id"]: item for item in index["tasks"]
    }
    failed_events: dict[str, dict[str, Any]] = {}
    for item in events:
        binding = item.get("output_binding")
        capture = item.get("output_capture", {})
        if (
            item.get("hook_event_name") != "SubagentStop"
            or not isinstance(binding, Mapping)
            or capture.get("status") != "FAILED"
        ):
            continue
        task = task_by_invocation.get(binding.get("invocation_id"))
        if task is not None:
            failed_events[task["task_id"]] = {
                "failure_code": str(
                    capture.get("failure_code") or "MULTIDIMENSIONAL_OUTPUT_INVALID"
                ),
                "output_hash": (
                    capture.get("raw_output_hash")
                    or item.get("final_structured_output_hash")
                ),
                "failure_source": "SUBAGENT_STOP_OUTPUT_VALIDATION",
                "attempt": capture.get("attempt"),
                "repair_state": capture.get("repair_state"),
                "raw_path": capture.get("raw_path"),
            }
    # A separately recorded, explicitly adopted retry may supersede a failed
    # validation result, while the original failure remains in the archived
    # bundle/proof and retry-adoption log.
    for task_id in completed_events:
        failed_events.pop(task_id, None)
    started_invocations = {
        item.get("context_binding", {}).get("invocation_id")
        for item in events
        if item.get("hook_event_name") == "SubagentStart"
        and isinstance(item.get("context_binding"), Mapping)
        and item.get("context_binding", {}).get("status") == "DELIVERED"
    }
    for task in index["tasks"]:
        if (
            task["task_id"] not in completed_events
            and task["task_id"] not in failed_events
            and task["invocation_id"] in started_invocations
        ):
            # The parent Codex process has exited, so an invocation that has a
            # delivered start event but no stop event is no longer active.  It
            # is an explicit task failure (for example a model compaction
            # failure), not evidence that the dimension was researched.
            failed_events[task["task_id"]] = {
                "failure_code": "MULTIDIMENSIONAL_SUBAGENT_TERMINAL_EVENT_MISSING",
                "output_hash": None,
                "failure_source": "START_WITHOUT_STOP_AFTER_PARENT_EXIT",
            }
    # 上游失败是终态，但不是依赖成功。被阻塞任务必须有 Hook 拒绝证明，
    # 且不会为了凑齐任务数再启动一个没有合法输入的子 Agent。
    changed = True
    while changed:
        changed = False
        for task in index["tasks"]:
            if task["task_id"] in completed_events or task["task_id"] in failed_events:
                continue
            failed_dependencies = [
                dependency for dependency in task.get("depends_on", [])
                if dependency in failed_events
            ]
            if failed_dependencies and task["task_name"] in denied_dependency_names:
                failed_events[task["task_id"]] = {
                    "failure_code": "MULTIDIMENSIONAL_UPSTREAM_DEPENDENCY_FAILED",
                    "output_hash": None,
                    "failure_source": "DEPENDENCY_BLOCKED_WITH_HOOK_DENIAL",
                    "failed_dependency_task_ids": failed_dependencies,
                }
                changed = True
    terminal_names = {
        task["task_name"] for task in index["tasks"]
        if task["task_id"] in failed_events
    }
    if allowed_names | terminal_names != expected_names:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_DISPATCH_PROOF_INCOMPLETE")
    common_ids = [
        item["security_id"] for item in handoff["portfolio"]["positions"]
        if item["asset_type"] == "COMMON_STOCK"
    ]
    bindings = {
        "handoff_id": handoff["handoff_id"], "handoff_hash": handoff["handoff_hash"],
        "portfolio_hash": handoff["portfolio_hash"], "council_request_id": council_request["request_id"],
        "council_request_hash": council_request["request_hash"], "decision_cutoff": gate["decision_cutoff"],
    }
    reports: list[dict[str, Any]] = []
    report_paths: dict[str, str] = {}
    reports_by_task_id: dict[str, dict[str, Any]] = {}
    for task in index["tasks"]:
        event = completed_events.get(task["task_id"])
        if event is None:
            if task["task_id"] not in failed_events:
                raise MultidimensionalStageError(
                    f"MULTIDIMENSIONAL_REPORT_MISSING:{task['task_id']}"
                )
            continue
        path = run_dir / event["output_capture"]["path"]
        report = _read_object(path)
        dependency_claim_ids = [
            claim["claim_id"]
            for dependency_id in task.get("depends_on", [])
            for claim in reports_by_task_id.get(dependency_id, {}).get("claims", [])
        ]
        if any(
            dependency_id not in reports_by_task_id
            for dependency_id in task.get("depends_on", [])
        ):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_DEPENDENCY_ORDER_INVALID")
        validate_research_dimension_report(
            report, expected_bindings=bindings, allowed_security_ids=common_ids,
            allowed_evidence_ids=task["allowed_evidence_ids"],
            known_research_claim_ids=dependency_claim_ids,
            allowed_documents=task.get("allowed_documents", []),
        )
        if (
            report["capability"] != task["capability"]
            or report["security_ids"] != task["security_ids"]
            or report["invocation_id"] != task["invocation_id"]
        ):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_REPORT_TASK_BINDING_INVALID")
        reports.append(report)
        reports_by_task_id[task["task_id"]] = report
        report_paths[report["report_id"]] = str(path.relative_to(run_dir))
    imported_equity_reports: list[dict[str, Any]] = []
    imported_by_security: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    rejected_company_by_security: dict[str, dict[str, Any]] = {}
    imported_artifact_refs: list[str] = []
    materials_artifact_refs: list[str] = []
    if manifest.get("research_materials_import_hash") is not None:
        materials_manifest_path = run_dir / "research/imported-materials/import-manifest.json"
        materials_manifest = _read_object(materials_manifest_path)
        if materials_manifest.get("import_hash") != manifest["research_materials_import_hash"]:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_MATERIALS_IMPORT_HASH_MISMATCH")
        materials_artifact_refs = sorted(
            str(path.relative_to(run_dir))
            for path in (run_dir / "research/imported-materials").rglob("*")
            if path.is_file()
        )
    import_manifest_path = run_dir / "research/imported-company-research/import-manifest.json"
    if import_manifest_path.is_file():
        from product.runtime.validation import collect_evidence_refs

        import_manifest = _read_object(import_manifest_path)
        if import_manifest.get("import_hash") != canonical_hash({
            key: value for key, value in import_manifest.items() if key != "import_hash"
        }):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_IMPORT_PROOF_INVALID")
        if (
            import_manifest.get("handoff_hash") != handoff["handoff_hash"]
            or import_manifest.get("portfolio_hash") != handoff["portfolio_hash"]
            or import_manifest.get("target_decision_cutoff") != gate["decision_cutoff"]
        ):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_IMPORT_BINDING_INVALID")
        for rejected in import_manifest.get("rejected_reports", []):
            security_id = rejected.get("security_id")
            if isinstance(security_id, str):
                rejected_company_by_security[security_id] = dict(rejected)
        target_evidence_by_id = {
            item["evidence_id"]: item for item in gate.get("allowed_evidence", [])
            if isinstance(item, Mapping) and isinstance(item.get("evidence_id"), str)
        }
        for entry in import_manifest.get("reports", []):
            path = run_dir / str(entry.get("artifact_ref", ""))
            markdown_path = run_dir / str(entry.get("markdown_ref", ""))
            request_path = run_dir / str(entry.get("request_ref", ""))
            evidence_path = run_dir / str(entry.get("evidence_ref", ""))
            for artifact in (path, markdown_path, request_path, evidence_path):
                if not artifact.is_file():
                    raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_IMPORT_ARTIFACT_MISSING")
            report = _read_object(path)
            if (
                entry.get("report_id") != report.get("report_id")
                or entry.get("report_hash") != canonical_hash(report)
                or entry.get("source_json_file_hash") != file_hash(path)
                or entry.get("source_markdown_file_hash") != file_hash(markdown_path)
            ):
                raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_IMPORT_ARTIFACT_DRIFT")
            security_id = entry.get("security_id")
            if security_id != report.get("security", {}).get("security_id") or security_id in imported_by_security:
                raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_IMPORT_SECURITY_INVALID")
            source_evidence = _read_object(evidence_path).get("allowed_evidence", [])
            source_evidence_by_id = {
                item["evidence_id"]: item for item in source_evidence
                if isinstance(item, Mapping) and isinstance(item.get("evidence_id"), str)
            }
            used_evidence_ids = sorted(collect_evidence_refs(report))
            missing_ids = sorted(set(used_evidence_ids) - set(target_evidence_by_id))
            drifted_ids = sorted(
                evidence_id for evidence_id in used_evidence_ids
                if evidence_id in source_evidence_by_id
                and evidence_id in target_evidence_by_id
                and canonical_hash(source_evidence_by_id[evidence_id])
                != canonical_hash(target_evidence_by_id[evidence_id])
            )
            if missing_ids or drifted_ids:
                rejected_company_by_security[security_id] = {
                    "security_id": security_id,
                    "status": "INCOMPATIBLE_TARGET_GATE",
                    "missing_evidence_ids": missing_ids,
                    "drifted_evidence_ids": drifted_ids,
                    "gap_reason": (
                        "历史公司报告引用的冻结事实未在当前统一 Gate 中保持同一身份与内容。"
                    ),
                }
                continue
            imported_equity_reports.append(report)
            imported_by_security[security_id] = (report, entry)
            imported_artifact_refs.extend(
                str(item.relative_to(run_dir))
                for item in (path, markdown_path, request_path, evidence_path)
            )
        imported_artifact_refs.append(str(import_manifest_path.relative_to(run_dir)))
    report_refs = [
        {
            "report_id": report["report_id"], "report_hash": report["report_hash"],
            "report_type": "RESEARCH_DIMENSION_REPORT", "capability": report["capability"],
            "security_ids": report["security_ids"], "artifact_ref": report_paths[report["report_id"]],
        }
        for report in reports
    ]
    report_refs.extend({
        "report_id": report["report_id"],
        "report_hash": canonical_hash(report),
        "report_type": "EQUITY_RESEARCH_REPORT",
        "capability": "COMPANY_RESEARCH",
        "security_ids": [security_id],
        "artifact_ref": entry["artifact_ref"],
    } for security_id, (report, entry) in imported_by_security.items())
    by_pair = {
        (security_id, report["capability"]): report
        for report in reports for security_id in report["security_ids"]
    }
    coverage = []
    for security_id in common_ids:
        for capability in BUNDLE_CAPABILITIES:
            report = by_pair.get((security_id, capability))
            if capability == "COMPANY_RESEARCH" and security_id in imported_by_security:
                equity_report, _ = imported_by_security[security_id]
                coverage.append({
                    "security_id": security_id,
                    "capability": capability,
                    "status": equity_report["status"],
                    "report_id": equity_report["report_id"],
                    "gap_reason": None,
                })
                continue
            if capability == "COMPANY_RESEARCH" and security_id in rejected_company_by_security:
                rejected = rejected_company_by_security[security_id]
                coverage.append({
                    "security_id": security_id,
                    "capability": capability,
                    "status": "NOT_RESEARCHED",
                    "report_id": None,
                    "gap_reason": str(rejected.get("gap_reason") or "历史公司报告不适用于当前统一 Gate。"),
                })
                continue
            failed_task = next((
                failed_events[item["task_id"]]
                for item in index["tasks"]
                if item["capability"] == capability
                and security_id in item["security_ids"]
                and item["task_id"] in failed_events
            ), None)
            coverage.append({
                "security_id": security_id, "capability": capability,
                "status": report["status"] if report else "FAILED" if failed_task else "NOT_RESEARCHED",
                "report_id": report["report_id"] if report else None,
                "gap_reason": (
                    None if report else
                    f"该维度输出未通过确定性校验：{failed_task['failure_code']}"
                    if failed_task else
                    "本阶段未形成该维度的有效报告。"
                ),
            })
    unresolved_questions = derive_unresolved_research_questions(
        dimension_reports=reports,
        equity_reports=imported_equity_reports,
    )
    company_ready = set(imported_by_security) == set(common_ids)
    bundle = finalize_holding_research_bundle({
        "schema_version": HOLDING_RESEARCH_BUNDLE_VERSION,
        "bundle_id": f"holding-research-bundle:{manifest['run_id']}",
        "run_id": manifest["run_id"],
        "bindings": {key: value for key, value in bindings.items() if key != "decision_cutoff"},
        "decision_cutoff": gate["decision_cutoff"],
        "common_stock_security_ids": common_ids,
        "report_refs": report_refs,
        "coverage": coverage,
        "consumability": (
            "DOWNSTREAM_READY" if company_ready else "STRUCTURALLY_CONSUMABLE"
        ),
        "package_provenance": {
            "base_run_id": manifest["run_id"],
            "base_bundle_hash": None,
            "base_gate_hash": gate["bundle_hash"],
            "company_research_imports": [
                {
                    "source_run_id": entry["source_run_id"],
                    "source_decision_cutoff": entry["source_decision_cutoff"],
                    "report_id": report["report_id"],
                    "report_hash": canonical_hash(report),
                    "compatibility_status": "REVALIDATED",
                }
                for report, entry in imported_by_security.values()
            ],
            "incorporated_supplements": [],
            "excluded_supplements": [],
        },
        "unresolved_cross_dimension_questions": unresolved_questions,
        "no_unresolved_reason": (
            None if unresolved_questions else
            "已验证报告没有提供可直接归集的观察或失效条件；未执行额外语义综合。"
        ),
        "summary": "本包归集当前批次各维度报告和明确缺口；维度间分歧尚未由后续反证或 CIO 处理。",
        "artifact_refs": sorted([
            *report_paths.values(), *imported_artifact_refs, *materials_artifact_refs,
        ]),
    })
    validate_holding_research_bundle(
        bundle,
        expected_bindings={key: value for key, value in bindings.items() if key != "decision_cutoff"},
        expected_common_stock_ids=common_ids,
        dimension_reports=reports,
        equity_reports=imported_equity_reports,
    )
    _write_object(run_dir / "research/holding-research-bundle.json", bundle)
    markdown = render_holding_research_bundle_markdown(
        bundle,
        dimension_reports=reports,
        equity_reports=imported_equity_reports,
    )
    markdown_path = run_dir / "research/holding-research-bundle.md"
    markdown_path.write_text(markdown, encoding="utf-8")
    terminal_by_child = {
        item.get("child_session_id"): item
        for item in events
        if item.get("hook_event_name") == "SubagentStop"
        and isinstance(item.get("child_session_id"), str)
    }
    repair_attempts = []
    for item in events:
        request = item.get("repair_request")
        capture = item.get("output_capture")
        child_id = item.get("child_session_id")
        if (
            item.get("hook_event_name") != "SubagentStopBlocked"
            or not isinstance(request, Mapping)
            or not isinstance(capture, Mapping)
        ):
            continue
        terminal = terminal_by_child.get(child_id)
        terminal_capture = (
            terminal.get("output_capture", {}) if isinstance(terminal, Mapping) else {}
        )
        repair_attempts.append({
            "task_id": request.get("task_id"),
            "invocation_id": request.get("invocation_id"),
            "validation_error": request.get("validation_error"),
            "output_schema_hash": request.get("output_schema_hash"),
            "original_output_hash": capture.get("raw_output_hash"),
            "original_output_path": capture.get("raw_path"),
            "terminal_status": terminal_capture.get("status"),
            "terminal_repair_state": terminal_capture.get("repair_state"),
            "terminal_output_hash": terminal_capture.get("raw_output_hash"),
            "terminal_output_path": terminal_capture.get("raw_path"),
        })
    proof = {
        "schema_version": "multidimensional-research-execution-proof/2.0.0",
        "run_id": manifest["run_id"], "expected_tasks": sorted(expected_names),
        "completed_task_ids": sorted(completed_events),
        "failed_tasks": [
            {
                "task_id": task_id,
                "failure_code": item["failure_code"],
                "rejected_output_hash": item["output_hash"],
                "failure_source": item["failure_source"],
            }
            for task_id, item in sorted(failed_events.items())
        ],
        "coverage_complete": (
            len(completed_events) + len(failed_events) == len(index["tasks"])
        ),
        "all_reports_valid": not failed_events and len(completed_events) == len(index["tasks"]),
        "repair_attempts": repair_attempts,
        "gate_hash": gate["bundle_hash"], "bundle_hash": bundle["bundle_hash"],
        "company_research_import_hash": manifest.get("company_research_import_hash"),
        "research_materials_import_hash": manifest.get("research_materials_import_hash"),
        "adopted_retry_invocations": [
            str(Path(item).resolve().relative_to(run_dir))
            for item in adopted_invocation_dirs
        ],
        "consumability": bundle["consumability"],
        "complete_portfolio_decision": False,
    }
    proof["proof_hash"] = canonical_hash(proof)
    _write_object(run_dir / "research/execution-proof.json", proof)
    return {
        "status": "PASSED", "run_id": manifest["run_id"],
        "completed": len(reports), "expected": len(index["tasks"]),
        "bundle": str(run_dir / "research/holding-research-bundle.json"),
        "report": str(markdown_path),
    }


def _adopt_multidimensional_retry(
    repository_root: Path, run_dir: Path, *, invocation_dir: Path,
) -> dict[str, Any]:
    """归档旧聚合包，并只把显式成功的单任务 attempt 纳入新聚合包。"""

    run_dir = Path(run_dir).resolve()
    invocation_dir = Path(invocation_dir).resolve()
    adoption_log = run_dir / "research/retry-adoptions.jsonl"
    prior = []
    if adoption_log.is_file():
        prior = [
            json.loads(line) for line in adoption_log.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    adopted_dirs = [run_dir / item["invocation_ref"] for item in prior]
    adopted_dirs.append(invocation_dir)
    revision = len(prior) + 1
    revision_dir = run_dir / f"research/revisions/{revision}"
    if revision_dir.exists():
        raise MultidimensionalStageError("MULTIDIMENSIONAL_RETRY_REVISION_EXISTS")
    revision_dir.mkdir(parents=True)
    canonical = (
        "holding-research-bundle.json",
        "holding-research-bundle.md",
        "execution-proof.json",
    )
    archived = {}
    for name in canonical:
        source = run_dir / "research" / name
        if not source.is_file():
            raise MultidimensionalStageError("MULTIDIMENSIONAL_RETRY_BASE_ARTIFACT_MISSING")
        archived[name] = file_hash(source)
        shutil.copy2(source, revision_dir / name)
    if (run_dir / "research/consumption-proof.json").exists():
        raise MultidimensionalStageError("MULTIDIMENSIONAL_RETRY_ALREADY_CONSUMED")
    for name in canonical:
        (run_dir / "research" / name).unlink()
    try:
        result = finalize_multidimensional_stage_run(
            repository_root, run_dir, adopted_invocation_dirs=adopted_dirs,
        )
    except Exception:
        for name in canonical:
            source = revision_dir / name
            destination = run_dir / "research" / name
            if source.is_file() and not destination.exists():
                shutil.copy2(source, destination)
        raise
    proof = _read_object(invocation_dir / "task-execution-proof.json")
    record = {
        "schema_version": "multidimensional-retry-adoption/1.0.0",
        "run_id": result["run_id"], "revision": revision,
        "invocation_ref": str(invocation_dir.relative_to(run_dir)),
        "task_name": proof["task_name"], "task_id": proof["task_id"],
        "retry_proof_hash": proof["proof_hash"],
        "archived_artifact_hashes": archived,
        "adopted_bundle_file_hash": file_hash(
            run_dir / "research/holding-research-bundle.json"
        ),
    }
    record["adoption_hash"] = canonical_hash(record)
    adoption_log.parent.mkdir(parents=True, exist_ok=True)
    with adoption_log.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    return result


def _copy_run_artifact(source_run: Path, target_run: Path, relative: str) -> str:
    source = (source_run / relative).resolve()
    if not source.is_relative_to(source_run) or not source.is_file():
        raise MultidimensionalStageError("CANONICAL_PACKAGE_SOURCE_ARTIFACT_MISSING")
    destination = (target_run / relative).resolve()
    if not destination.is_relative_to(target_run):
        raise MultidimensionalStageError("CANONICAL_PACKAGE_ARTIFACT_PATH_INVALID")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if file_hash(destination) != file_hash(source):
            raise MultidimensionalStageError("CANONICAL_PACKAGE_ARTIFACT_COLLISION")
    else:
        shutil.copy2(source, destination)
    return str(destination.relative_to(target_run))


def _merge_gate_evidence(
    target: dict[str, dict[str, Any]], source: Sequence[Mapping[str, Any]], *, cutoff: str,
) -> None:
    cutoff_time = parse_timestamp(cutoff)
    for raw in source:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("evidence_id"), str):
            raise MultidimensionalStageError("CANONICAL_PACKAGE_EVIDENCE_INVALID")
        item = copy.deepcopy(dict(raw))
        for field in ("source_id", "as_of", "retrieved_at"):
            if not isinstance(item.get(field), str) or not item[field]:
                raise MultidimensionalStageError(
                    f"CANONICAL_PACKAGE_EVIDENCE_PROVENANCE_MISSING:{field}"
                )
        if parse_timestamp(item["as_of"]) > cutoff_time or parse_timestamp(item["retrieved_at"]) > cutoff_time:
            raise MultidimensionalStageError("CANONICAL_PACKAGE_EVIDENCE_AFTER_CUTOFF")
        evidence_id = item["evidence_id"]
        existing = target.get(evidence_id)
        if existing is not None and canonical_hash(existing) != canonical_hash(item):
            raise MultidimensionalStageError("CANONICAL_PACKAGE_EVIDENCE_COLLISION")
        target[evidence_id] = item


def assemble_canonical_holding_research_package(
    repository_root: Path,
    *,
    base_run_dir: Path,
    company_research_run_dir: Path,
    output_dir: Path,
    supplement_run_dirs: Sequence[Path] = (),
) -> dict[str, Any]:
    """只读重验既有研究产物并形成单一交接包；不调用模型或改写历史运行。"""

    from product.council.multidimensional_output import render_holding_research_bundle_markdown
    from product.council.multidimensional_research import (
        BUNDLE_CAPABILITIES,
        HOLDING_RESEARCH_BUNDLE_VERSION,
        LEGACY_BUNDLE_CAPABILITIES,
        LEGACY_HOLDING_RESEARCH_BUNDLE_VERSION,
        derive_unresolved_research_questions,
        finalize_holding_research_bundle,
        validate_holding_research_bundle,
        validate_research_dimension_report,
    )
    from product.runtime.validation import collect_evidence_refs

    repository_root = Path(repository_root).resolve()
    base_run = Path(base_run_dir).resolve()
    company_run = Path(company_research_run_dir).resolve()
    target = Path(output_dir).resolve()
    if target.exists():
        raise MultidimensionalStageError("CANONICAL_PACKAGE_OUTPUT_EXISTS")
    if target.is_relative_to(repository_root):
        raise MultidimensionalStageError("CANONICAL_PACKAGE_OUTPUT_INSIDE_SOURCE")

    base_manifest = _read_object(base_run / "run_manifest.json")
    base_handoff = _read_object(base_run / "audit/portfolio-handoff.json")
    base_request = _read_object(base_run / "council-request.json")
    base_gate = _read_object(base_run / "evidence/gate.json")
    base_bundle = _read_object(base_run / "research/holding-research-bundle.json")
    if (
        base_manifest.get("stage") != "MULTI_DIMENSIONAL_HOLDING_RESEARCH"
        or base_bundle.get("run_id") != base_manifest.get("run_id")
        or base_bundle.get("decision_cutoff") != base_gate.get("decision_cutoff")
    ):
        raise MultidimensionalStageError("CANONICAL_PACKAGE_BASE_BINDING_INVALID")
    common_ids = list(base_bundle.get("common_stock_security_ids", []))
    base_dimension_reports: list[dict[str, Any]] = []
    base_equity_reports: list[dict[str, Any]] = []
    for reference in base_bundle.get("report_refs", []):
        path = (base_run / str(reference.get("artifact_ref", ""))).resolve()
        if not path.is_relative_to(base_run) or not path.is_file():
            raise MultidimensionalStageError("CANONICAL_PACKAGE_BASE_REPORT_MISSING")
        report = _read_object(path)
        if reference.get("report_type") == "RESEARCH_DIMENSION_REPORT":
            base_dimension_reports.append(report)
        elif reference.get("report_type") == "EQUITY_RESEARCH_REPORT":
            base_equity_reports.append(report)
        else:
            raise MultidimensionalStageError("CANONICAL_PACKAGE_BASE_REPORT_TYPE_INVALID")
    validate_holding_research_bundle(
        base_bundle,
        expected_bindings=base_bundle["bindings"],
        expected_common_stock_ids=common_ids,
        dimension_reports=base_dimension_reports,
        equity_reports=base_equity_reports,
    )
    assembly_capabilities = (
        BUNDLE_CAPABILITIES
        if base_bundle.get("schema_version") == HOLDING_RESEARCH_BUNDLE_VERSION
        else LEGACY_BUNDLE_CAPABILITIES
        if base_bundle.get("schema_version") == LEGACY_HOLDING_RESEARCH_BUNDLE_VERSION
        else None
    )
    if assembly_capabilities is None:
        raise MultidimensionalStageError("CANONICAL_PACKAGE_BASE_VERSION_UNSUPPORTED")
    canonical_evidence: dict[str, dict[str, Any]] = {}
    _merge_gate_evidence(
        canonical_evidence,
        base_gate.get("allowed_evidence", []),
        cutoff=base_bundle["decision_cutoff"],
    )
    company_gate = _read_object(company_run / "evidence/gate.json")
    _merge_gate_evidence(
        canonical_evidence,
        company_gate.get("allowed_evidence", []),
        cutoff=base_bundle["decision_cutoff"],
    )

    target.mkdir(parents=True)
    _write_object(target / "audit/portfolio-handoff.json", base_handoff)
    _write_object(target / "council-request.json", base_request)
    canonical_gate = {
        "schema_version": "canonical-holding-research-evidence-gate/1.0.0",
        "run_id": base_bundle["run_id"],
        "decision_cutoff": base_bundle["decision_cutoff"],
        "source_mode": "canonical-revalidated",
        "source_gates": [
            {
                "role": "BASE_MULTIDIMENSIONAL",
                "run_id": base_manifest["run_id"],
                "gate_hash": base_gate["bundle_hash"],
                "file_hash": file_hash(base_run / "evidence/gate.json"),
            },
            {
                "role": "COMPANY_RESEARCH",
                "run_id": _read_object(company_run / "run_manifest.json")["run_id"],
                "gate_hash": company_gate["bundle_hash"],
                "file_hash": file_hash(company_run / "evidence/gate.json"),
            },
        ],
        "allowed_evidence_ids": sorted(canonical_evidence),
        "allowed_evidence": [canonical_evidence[key] for key in sorted(canonical_evidence)],
    }
    canonical_gate["bundle_hash"] = canonical_hash(canonical_gate)
    _write_object(target / "evidence/gate.json", canonical_gate)

    copied_artifacts = {
        _copy_run_artifact(base_run, target, relative)
        for relative in base_bundle.get("artifact_refs", [])
    }
    for reference in base_bundle.get("report_refs", []):
        copied_artifacts.add(
            _copy_run_artifact(base_run, target, str(reference["artifact_ref"]))
        )
    company_import = _import_company_research_reports(
        source_run=company_run,
        target_run=target,
        expected_handoff=base_handoff,
        expected_security_ids=common_ids,
        target_gate=canonical_gate,
    )
    if company_import["rejected_reports"]:
        raise MultidimensionalStageError("CANONICAL_PACKAGE_COMPANY_RESEARCH_INCOMPATIBLE")
    imported_equity_reports = [
        _read_object(target / entry["artifact_ref"])
        for entry in company_import["reports"]
    ]
    copied_artifacts.update(
        str(path.relative_to(target))
        for path in (target / "research/imported-company-research").rglob("*")
        if path.is_file()
    )

    dimension_reports = list(base_dimension_reports)
    report_paths = {
        reference["report_id"]: reference["artifact_ref"]
        for reference in base_bundle["report_refs"]
        if reference["report_type"] == "RESEARCH_DIMENSION_REPORT"
    }
    incorporated_supplements: list[dict[str, Any]] = []
    excluded_supplements: list[dict[str, Any]] = []
    target_bindings = {**base_bundle["bindings"], "decision_cutoff": base_bundle["decision_cutoff"]}
    for ordinal, raw_run in enumerate(supplement_run_dirs, start=1):
        supplement_run = Path(raw_run).resolve()
        supplement_manifest = _read_object(supplement_run / "run_manifest.json")
        supplement_gate = _read_object(supplement_run / "evidence/gate.json")
        task_proof = _read_object(supplement_run / "research/task-execution-proof.json")
        report_path = (supplement_run / str(task_proof.get("report_ref", ""))).resolve()
        if not report_path.is_relative_to(supplement_run) or not report_path.is_file():
            raise MultidimensionalStageError("CANONICAL_PACKAGE_SUPPLEMENT_REPORT_MISSING")
        report = _read_object(report_path)
        reason_codes: list[str] = []
        if supplement_manifest.get("run_id") != base_bundle["run_id"]:
            reason_codes.append("RUN_ID_MISMATCH")
        if supplement_gate.get("decision_cutoff") != base_bundle["decision_cutoff"]:
            reason_codes.append("DECISION_CUTOFF_MISMATCH")
        if report.get("bindings") != target_bindings:
            reason_codes.append("INPUT_BINDING_MISMATCH")
        if set(report.get("security_ids", [])) - set(common_ids):
            reason_codes.append("SECURITY_SCOPE_MISMATCH")
        supplement_evidence = {
            item.get("evidence_id"): item
            for item in supplement_gate.get("allowed_evidence", [])
            if isinstance(item, Mapping) and isinstance(item.get("evidence_id"), str)
        }
        for evidence_id in collect_evidence_refs(report):
            source_item = supplement_evidence.get(evidence_id)
            target_item = canonical_evidence.get(evidence_id)
            if source_item is None or target_item is None:
                reason_codes.append("EVIDENCE_NOT_IN_CANONICAL_GATE")
                break
            if canonical_hash(source_item) != canonical_hash(target_item):
                reason_codes.append("EVIDENCE_CONTENT_DRIFT")
                break
        provenance = {
            "source_run_id": str(supplement_manifest.get("run_id")),
            "source_decision_cutoff": str(supplement_gate.get("decision_cutoff")),
            "report_id": str(report.get("report_id")),
            "report_hash": str(report.get("report_hash")),
        }
        if reason_codes:
            excluded_supplements.append({
                **provenance,
                "compatibility_status": "EXCLUDED",
                "reason_codes": sorted(set(reason_codes)),
            })
            continue
        validate_research_dimension_report(
            report,
            expected_bindings=target_bindings,
            allowed_security_ids=common_ids,
            allowed_evidence_ids=sorted(canonical_evidence),
            allowed_documents=report.get("documents", []),
        )
        matching = [
            item for item in dimension_reports
            if item.get("capability") == report.get("capability")
            and set(item.get("security_ids", [])) == set(report.get("security_ids", []))
        ]
        if len(matching) != 1:
            raise MultidimensionalStageError("CANONICAL_PACKAGE_SUPPLEMENT_TARGET_AMBIGUOUS")
        dimension_reports.remove(matching[0])
        report_paths.pop(str(matching[0]["report_id"]), None)
        destination = f"research/supplements/{ordinal}/dimension-report.json"
        _copy_run_artifact(supplement_run, target, str(report_path.relative_to(supplement_run)))
        source_copy = target / report_path.relative_to(supplement_run)
        final_copy = target / destination
        final_copy.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_copy, final_copy)
        dimension_reports.append(report)
        report_paths[report["report_id"]] = destination
        copied_artifacts.add(destination)
        for relative in report.get("artifact_refs", []):
            copied_artifacts.add(_copy_run_artifact(supplement_run, target, relative))
        incorporated_supplements.append({
            **provenance,
            "compatibility_status": "REVALIDATED",
        })

    report_refs = [
        {
            "report_id": report["report_id"],
            "report_hash": report["report_hash"],
            "report_type": "RESEARCH_DIMENSION_REPORT",
            "capability": report["capability"],
            "security_ids": report["security_ids"],
            "artifact_ref": report_paths[report["report_id"]],
        }
        for report in dimension_reports
    ]
    imported_by_security = {
        entry["security_id"]: (report, entry)
        for entry, report in zip(company_import["reports"], imported_equity_reports, strict=True)
    }
    report_refs.extend({
        "report_id": report["report_id"],
        "report_hash": canonical_hash(report),
        "report_type": "EQUITY_RESEARCH_REPORT",
        "capability": "COMPANY_RESEARCH",
        "security_ids": [security_id],
        "artifact_ref": entry["artifact_ref"],
    } for security_id, (report, entry) in imported_by_security.items())
    report_by_pair = {
        (security_id, report["capability"]): report
        for report in dimension_reports for security_id in report["security_ids"]
    }
    coverage: list[dict[str, Any]] = []
    for security_id in common_ids:
        for capability in assembly_capabilities:
            if capability == "COMPANY_RESEARCH":
                report, _ = imported_by_security[security_id]
            else:
                report = report_by_pair.get((security_id, capability))
            coverage.append({
                "security_id": security_id,
                "capability": capability,
                "status": report["status"] if report is not None else "NOT_RESEARCHED",
                "report_id": report["report_id"] if report is not None else None,
                "gap_reason": None if report is not None else "基础运行未形成该维度的有效报告。",
            })
    unresolved = derive_unresolved_research_questions(
        dimension_reports=dimension_reports,
        equity_reports=imported_equity_reports,
    )
    package_provenance = {
        "base_run_id": base_bundle["run_id"],
        "base_bundle_hash": base_bundle["bundle_hash"],
        "base_gate_hash": base_gate["bundle_hash"],
        "company_research_imports": [
            {
                "source_run_id": entry["source_run_id"],
                "source_decision_cutoff": entry["source_decision_cutoff"],
                "report_id": report["report_id"],
                "report_hash": canonical_hash(report),
                "compatibility_status": "REVALIDATED",
            }
            for report, entry in imported_by_security.values()
        ],
        "incorporated_supplements": incorporated_supplements,
        "excluded_supplements": excluded_supplements,
    }
    bundle = finalize_holding_research_bundle({
        "schema_version": base_bundle["schema_version"],
        "bundle_id": f"canonical-holding-research-bundle:{base_bundle['run_id']}",
        "run_id": base_bundle["run_id"],
        "bindings": copy.deepcopy(base_bundle["bindings"]),
        "decision_cutoff": base_bundle["decision_cutoff"],
        "common_stock_security_ids": common_ids,
        "report_refs": report_refs,
        "coverage": coverage,
        "consumability": "DOWNSTREAM_READY",
        "package_provenance": package_provenance,
        "unresolved_cross_dimension_questions": unresolved,
        "no_unresolved_reason": (
            None if unresolved else
            "已验证报告没有提供可直接归集的观察或失效条件；未执行额外语义综合。"
        ),
        "summary": (
            "本 canonical 研究包以单一基础运行和截止时间归集公司研究及多维报告；"
            "不兼容补证保持在 provenance 中，不生成买卖动作。"
        ),
        "artifact_refs": sorted(copied_artifacts),
    })
    validate_holding_research_bundle(
        bundle,
        expected_bindings=base_bundle["bindings"],
        expected_common_stock_ids=common_ids,
        dimension_reports=dimension_reports,
        equity_reports=imported_equity_reports,
    )
    _write_object(target / "research/holding-research-bundle.json", bundle)
    markdown = render_holding_research_bundle_markdown(
        bundle,
        dimension_reports=dimension_reports,
        equity_reports=imported_equity_reports,
    )
    (target / "research/holding-research-bundle.md").write_text(markdown, encoding="utf-8")
    run_manifest = {
        "schema_version": "canonical-holding-research-package/1.0.0",
        "stage": "MULTI_DIMENSIONAL_HOLDING_RESEARCH",
        "run_id": base_bundle["run_id"],
        "source_mode": "DETERMINISTIC_REASSEMBLY",
        "base_run_dir": str(base_run),
        "company_research_run_dir": str(company_run),
        "supplement_run_dirs": [str(Path(item).resolve()) for item in supplement_run_dirs],
        "llm_calls": 0,
        "bundle_hash": bundle["bundle_hash"],
        "gate_hash": canonical_gate["bundle_hash"],
    }
    run_manifest["manifest_hash"] = canonical_hash(run_manifest)
    _write_object(target / "run_manifest.json", run_manifest)
    package_manifest = {
        "schema_version": "canonical-holding-research-package-proof/1.0.0",
        "status": "PASSED",
        "run_id": base_bundle["run_id"],
        "source_inputs": {
            "base_manifest_file_hash": file_hash(base_run / "run_manifest.json"),
            "base_bundle_file_hash": file_hash(base_run / "research/holding-research-bundle.json"),
            "base_gate_file_hash": file_hash(base_run / "evidence/gate.json"),
            "company_manifest_file_hash": file_hash(company_run / "run_manifest.json"),
            "company_gate_file_hash": file_hash(company_run / "evidence/gate.json"),
            "supplements": [
                {
                    "run_dir": str(Path(raw_run).resolve()),
                    "manifest_file_hash": file_hash(
                        Path(raw_run).resolve() / "run_manifest.json"
                    ),
                    "gate_file_hash": file_hash(
                        Path(raw_run).resolve() / "evidence/gate.json"
                    ),
                    "task_proof_file_hash": file_hash(
                        Path(raw_run).resolve()
                        / "research/task-execution-proof.json"
                    ),
                    "report_file_hash": file_hash(
                        Path(raw_run).resolve()
                        / str(
                            _read_object(
                                Path(raw_run).resolve()
                                / "research/task-execution-proof.json"
                            )["report_ref"]
                        )
                    ),
                }
                for raw_run in supplement_run_dirs
            ],
        },
        "implementation_snapshot": {
            str(path.relative_to(repository_root)): file_hash(path)
            for path in (
                repository_root / "product/council/multidimensional_research.py",
                repository_root / "product/council/multidimensional_output.py",
                repository_root / "product/runtime/multidimensional_stage.py",
                repository_root / "product/runtime/cli.py",
                repository_root
                / "product/schemas/runtime/holding-research-bundle-v1.1.schema.json",
                repository_root / "product/skills/portfolio-council/SKILL.md",
                repository_root / "product/version-manifest.json",
            )
        },
        "package_outputs": {
            "run_manifest_file_hash": file_hash(target / "run_manifest.json"),
            "bundle_file_hash": file_hash(target / "research/holding-research-bundle.json"),
            "markdown_file_hash": file_hash(target / "research/holding-research-bundle.md"),
            "gate_file_hash": file_hash(target / "evidence/gate.json"),
        },
        "package_provenance": package_provenance,
        "llm_calls": 0,
        "downstream_models_started": [],
        "complete_portfolio_decision": False,
    }
    package_manifest["proof_hash"] = canonical_hash(package_manifest)
    _write_object(target / "research/canonical-package-proof.json", package_manifest)
    return {
        "status": "PASSED",
        "run_id": bundle["run_id"],
        "consumability": bundle["consumability"],
        "bundle": str(target / "research/holding-research-bundle.json"),
        "report": str(target / "research/holding-research-bundle.md"),
        "proof": str(target / "research/canonical-package-proof.json"),
    }


def check_multidimensional_bundle_consumable(
    repository_root: Path, run_dir: Path, *, persist: bool = True,
) -> dict[str, Any]:
    """只读解析完整研究包，证明下游无需人工改写即可取得结构化研究输入。"""

    from product.council.multidimensional_research import (
        validate_holding_research_bundle,
        validate_research_dimension_report,
    )
    from product.runtime.validation import collect_evidence_refs

    del repository_root
    run_dir = Path(run_dir).resolve()
    manifest = _read_object(run_dir / "run_manifest.json")
    if manifest.get("stage") not in {
        "MULTI_DIMENSIONAL_HOLDING_RESEARCH", "INDEPENDENT_COUNTER_THESIS_RESEARCH",
    }:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_CONSUMER_STAGE_INVALID")
    bundle_path = run_dir / "research/holding-research-bundle.json"
    gate_path = run_dir / "evidence/gate.json"
    bundle, gate = _read_object(bundle_path), _read_object(gate_path)
    allowed_evidence_ids = set(gate.get("allowed_evidence_ids", []))
    common_ids = bundle.get("common_stock_security_ids", [])
    dimension_reports: list[dict[str, Any]] = []
    equity_reports: list[dict[str, Any]] = []
    inventory = []
    all_claim_ids: set[str] = set()
    loaded: list[tuple[Mapping[str, Any], dict[str, Any], Path]] = []
    for reference in bundle.get("report_refs", []):
        relative = reference.get("artifact_ref")
        if not isinstance(relative, str) or not relative:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_CONSUMER_REPORT_PATH_INVALID")
        path = (run_dir / relative).resolve()
        if not path.is_relative_to(run_dir) or not path.is_file():
            raise MultidimensionalStageError("MULTIDIMENSIONAL_CONSUMER_REPORT_MISSING")
        report = _read_object(path)
        loaded.append((reference, report, path))
        all_claim_ids.update(
            str(item["claim_id"])
            for item in report.get("claims", [])
            if isinstance(item, Mapping) and isinstance(item.get("claim_id"), str)
        )
    for reference, report, path in loaded:
        report_type = reference.get("report_type")
        if report_type == "RESEARCH_DIMENSION_REPORT":
            validate_research_dimension_report(
                report,
                expected_bindings={**bundle["bindings"], "decision_cutoff": bundle["decision_cutoff"]},
                allowed_security_ids=common_ids,
                allowed_evidence_ids=sorted(allowed_evidence_ids),
                known_research_claim_ids=sorted(all_claim_ids),
            )
            if reference.get("report_hash") != report.get("report_hash"):
                raise MultidimensionalStageError("MULTIDIMENSIONAL_CONSUMER_REPORT_HASH_MISMATCH")
            dimension_reports.append(report)
        elif report_type == "EQUITY_RESEARCH_REPORT":
            if reference.get("report_hash") != canonical_hash(report):
                raise MultidimensionalStageError("MULTIDIMENSIONAL_CONSUMER_REPORT_HASH_MISMATCH")
            equity_reports.append(report)
        else:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_CONSUMER_REPORT_TYPE_INVALID")
        evidence_refs = sorted(collect_evidence_refs(report))
        if set(evidence_refs) - allowed_evidence_ids:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_CONSUMER_EVIDENCE_DANGLING")
        inventory.append({
            "report_id": reference["report_id"], "report_type": report_type,
            "capability": reference["capability"], "security_ids": reference["security_ids"],
            "artifact_ref": str(path.relative_to(run_dir)), "file_hash": file_hash(path),
            "claim_ids": sorted(
                item["claim_id"] for item in report.get("claims", [])
                if isinstance(item, Mapping) and isinstance(item.get("claim_id"), str)
            ),
            "evidence_ids": evidence_refs,
            "assumption_ids": sorted(
                item["assumption_id"] for item in report.get("assumptions", [])
                if isinstance(item, Mapping) and isinstance(item.get("assumption_id"), str)
            ),
            "calculation_ids": sorted(
                item["calculation_id"] for item in report.get("calculations", [])
                if isinstance(item, Mapping) and isinstance(item.get("calculation_id"), str)
            ),
            "gap_ids": sorted(
                item["gap_id"] for item in report.get("data_gaps", [])
                if isinstance(item, Mapping) and isinstance(item.get("gap_id"), str)
            ),
        })
    validate_holding_research_bundle(
        bundle, expected_bindings=bundle["bindings"],
        expected_common_stock_ids=common_ids,
        dimension_reports=dimension_reports, equity_reports=equity_reports,
    )
    for relative in bundle.get("artifact_refs", []):
        artifact_path = (run_dir / relative).resolve()
        if not artifact_path.is_relative_to(run_dir) or not artifact_path.is_file():
            raise MultidimensionalStageError("MULTIDIMENSIONAL_CONSUMER_ARTIFACT_MISSING")
    proof = {
        "schema_version": "holding-research-consumption-proof/1.0.0",
        "status": "PASSED", "run_id": bundle["run_id"],
        "structural_status": "STRUCTURALLY_CONSUMABLE",
        "downstream_status": bundle.get("consumability", "STRUCTURALLY_CONSUMABLE"),
        "bundle_ref": str(bundle_path.relative_to(run_dir)),
        "bundle_file_hash": file_hash(bundle_path), "bundle_hash": bundle["bundle_hash"],
        "gate_ref": str(gate_path.relative_to(run_dir)), "gate_hash": gate["bundle_hash"],
        "decision_cutoff": bundle["decision_cutoff"],
        "report_inventory": inventory,
        "coverage_count": len(bundle["coverage"]),
        "unresolved_question_ids": sorted(
            item["question_id"] for item in bundle["unresolved_cross_dimension_questions"]
        ),
        "no_unresolved_reason": bundle.get("no_unresolved_reason"),
        "package_provenance": copy.deepcopy(bundle.get("package_provenance")),
        "parsed_fields": [
            "claims", "evidence_refs", "assumptions", "calculations",
            "data_gaps", "research_relationships", "observation_conditions",
        ],
        "downstream_models_started": [], "complete_portfolio_decision": False,
    }
    proof["proof_hash"] = canonical_hash(proof)
    if persist:
        destination = run_dir / "research/consumption-proof.json"
        if destination.exists():
            raise MultidimensionalStageError("MULTIDIMENSIONAL_CONSUMER_PROOF_EXISTS")
        _write_object(destination, proof)
    return proof


def launch_multidimensional_stage(
    repository_root: Path, *, run_dir: Path, codex_binary: str = "codex",
    timeout_seconds: int = 2400, task_name: str | None = None,
) -> tuple[dict[str, Any], int]:
    """从宿主入口启动一次多维 Codex 研究批次。"""

    from product.runtime.nested_codex import (
        build_nested_codex_command,
        fixture_mcp_runtime_environment,
        integrity_snapshot,
    )

    repository_root = Path(repository_root).resolve()
    product_root = repository_root / "product"
    run_dir = Path(run_dir).resolve()
    manifest = _read_object(run_dir / "run_manifest.json")
    if (
        manifest.get("schema_version") != STAGE_VERSION
        or manifest.get("stage") not in {
            "MULTI_DIMENSIONAL_HOLDING_RESEARCH", "INDEPENDENT_COUNTER_THESIS_RESEARCH",
        }
        or Path(manifest.get("output_dir", "")).resolve() != run_dir
    ):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_MANIFEST_INVALID")
    index = _read_object(run_dir / "research/dispatch-index.json")
    target_tasks = (
        _target_task_closure(index, task_name) if task_name is not None else []
    )
    if task_name is None:
        invocation_dir = run_dir / "invocation"
        if invocation_dir.exists():
            raise MultidimensionalStageError("MULTIDIMENSIONAL_ALREADY_LAUNCHED")
        invocation_dir.mkdir()
        runtime_root = run_dir / ".codex-runtime"
    else:
        if not (run_dir / "invocation/process-result.json").is_file():
            raise MultidimensionalStageError("MULTIDIMENSIONAL_RETRY_BASE_NOT_TERMINAL")
        target = target_tasks[-1]
        expected_report_id = f"dimension-report:{target['task_id']}"
        if any(
            _read_object(candidate).get("report_id") == expected_report_id
            for candidate in (run_dir / "research/reports").glob("*/dimension-report.json")
        ):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_RETRY_REPORT_ALREADY_VALID")
        retry_slug = canonical_hash({"task_name": task_name})[:16]
        retry_root = run_dir / f"invocation/retries/{retry_slug}"
        attempt = 1
        while (retry_root / f"attempt-{attempt}").exists():
            attempt += 1
        invocation_dir = retry_root / f"attempt-{attempt}"
        invocation_dir.mkdir(parents=True)
        runtime_root = run_dir / f".codex-runtime-retries/{retry_slug}/attempt-{attempt}"
    sqlite_home, log_dir, tmp_dir = runtime_root / "sqlite", runtime_root / "logs", runtime_root / "tmp"
    for path in (sqlite_home, log_dir, tmp_dir):
        path.mkdir(parents=True, exist_ok=False)
    prompt = (
        build_multidimensional_task_prompt(repository_root, run_dir, task_name)
        if task_name is not None
        else build_multidimensional_stage_prompt(repository_root, run_dir)
    )
    prompt_path = invocation_dir / "prompt.txt"
    prompt_path.write_text(prompt, encoding="utf-8")
    task_count = len(target_tasks) if task_name is not None else len(index["tasks"])
    parent_schema = _parent_output_schema(manifest["run_id"], task_count)
    schema_path = invocation_dir / "parent-output.schema.json"
    _write_object(schema_path, parent_schema)
    raw_final_path = tmp_dir / "final-message.json"
    command = build_nested_codex_command(
        codex_binary=codex_binary, product_root=product_root, run_dir=run_dir,
        model=manifest["parent_model"], sqlite_home=sqlite_home, log_dir=log_dir,
        final_message_path=raw_final_path,
        hook_recorder_path=product_root / "runtime/codex_hook_recorder.py",
        output_schema_path=schema_path, fixture_mcp_run_dir=run_dir,
        hook_agent_matcher="^(runtime_company_analyst|runtime_market_catalyst)$",
    )
    if manifest["stage"] == "MULTI_DIMENSIONAL_HOLDING_RESEARCH":
        # Desktop-only user MCP fields are rejected by the host CLI's strict
        # parser. The CLI also skips project agent registration in this mode,
        # so register only the specialists required by this frozen dispatch.
        command.insert(command.index("exec") + 1, "--ignore-user-config")
        product_agents = tomllib.loads(
            (product_root / ".codex/config.toml").read_text(encoding="utf-8")
        )["agents"]
        for agent_name in sorted({item["agent"] for item in index["tasks"]}):
            agent_config = product_agents.get(agent_name)
            if not isinstance(agent_config, Mapping):
                raise MultidimensionalStageError("MULTIDIMENSIONAL_AGENT_CONFIG_MISSING")
            agent_path = (product_root / ".codex" / agent_config["config_file"]).resolve()
            if not agent_path.is_relative_to(product_root / ".codex") or not agent_path.is_file():
                raise MultidimensionalStageError("MULTIDIMENSIONAL_AGENT_CONFIG_INVALID")
            command.extend((
                "-c", f"agents.{agent_name}={{"
                f"description={json.dumps(agent_config['description'], ensure_ascii=False)},"
                f"config_file={json.dumps(str(agent_path))}}}",
            ))
        command.extend(("-c", f"agents.max_threads={product_agents['max_threads']}"))
    events_path = invocation_dir / "codex-events.jsonl"
    hook_events_path = invocation_dir / "subagent-events.jsonl"
    dispatch_events_path = invocation_dir / "subagent-dispatches.jsonl"
    stderr_path = invocation_dir / "codex-stderr.log"
    environment = dict(os.environ)
    environment.update({
        "TMPDIR": str(tmp_dir), "PYTHONDONTWRITEBYTECODE": "1",
        "STOCK_AGENT_RUN_DIR": str(run_dir), "STOCK_AGENT_FIXTURE_MCP_RUN_DIR": str(run_dir),
        "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(hook_events_path),
        "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(dispatch_events_path),
        "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": (
            ",".join(sorted({item["agent"] for item in target_tasks}))
            if target_tasks
            else "runtime_company_analyst,runtime_market_catalyst"
        ),
        "STOCK_AGENT_MULTIDIMENSIONAL_STAGE": STAGE_VERSION,
        **fixture_mcp_runtime_environment(),
    })
    if task_name is not None:
        selected_names = [item["task_name"] for item in target_tasks]
        environment["STOCK_AGENT_RESEARCH_TASK_NAMES"] = json.dumps(selected_names)
        if len(selected_names) == 1:
            environment["STOCK_AGENT_RESEARCH_TASK_NAME"] = task_name
        else:
            environment.pop("STOCK_AGENT_RESEARCH_TASK_NAME", None)
    else:
        environment.pop("STOCK_AGENT_RESEARCH_TASK_NAME", None)
        environment.pop("STOCK_AGENT_RESEARCH_TASK_NAMES", None)
    environment.pop("STOCK_AGENT_START_CONTEXT", None)
    environment.pop("STOCK_AGENT_CAPTURE_SPECIALIST_OUTPUT", None)
    before = integrity_snapshot(repository_root)
    _write_object(invocation_dir / "environment-manifest.json", {
        "schema_version": "multidimensional-stage-environment/1.0.0",
        "run_id": manifest["run_id"], "cwd": str(product_root),
        "repo_root": str(repository_root), "product_root": str(product_root), "run_dir": str(run_dir),
        "command": command, "model": manifest["parent_model"], "sandbox": "workspace-write",
        "approval_policy": "never", "ephemeral": True, "sqlite_home": str(sqlite_home),
        "log_dir": str(log_dir), "tmpdir": str(tmp_dir), "prompt_hash": file_hash(prompt_path),
        "task_name": task_name,
        "selected_task_names": [item["task_name"] for item in target_tasks],
        "source_integrity_before": before,
    })
    try:
        process = subprocess.run(
            command, input=prompt, text=True, cwd=product_root, env=environment,
            capture_output=True, timeout=timeout_seconds, check=False,
        )
        stdout, stderr, process_code, timed_out = process.stdout, process.stderr, process.returncode, False
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout.decode() if isinstance(exc.stdout, bytes) else (exc.stdout or "")
        stderr = exc.stderr.decode() if isinstance(exc.stderr, bytes) else (exc.stderr or "")
        process_code, timed_out = 124, True
    events_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    failure_code = None
    try:
        if timed_out:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_TIMEOUT")
        if process_code != 0:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_CODEX_PROCESS_FAILED")
        if not raw_final_path.is_file():
            raise MultidimensionalStageError("MULTIDIMENSIONAL_FINAL_MESSAGE_MISSING")
        final_message = _read_object(raw_final_path)
        _write_object(invocation_dir / "final-message.json", final_message)
        if final_message != {
            "stage": "MULTI_DIMENSIONAL_HOLDING_RESEARCH",
            "run_id": manifest["run_id"], "dispatched": task_count,
            "completed": task_count,
        }:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_FINAL_MESSAGE_INVALID")
        if task_name is not None:
            finalize_multidimensional_task_evidence(
                repository_root, run_dir, task_name, invocation_dir=invocation_dir,
            )
            result = _adopt_multidimensional_retry(
                repository_root, run_dir, invocation_dir=invocation_dir,
            )
        else:
            result = finalize_multidimensional_stage_run(repository_root, run_dir)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        failure_code = str(exc).split(":", 1)[0]
        result = {"status": "FAILED", "run_id": manifest["run_id"], "failure_code": failure_code}
    outcome_tasks = target_tasks if target_tasks else index["tasks"]
    task_by_invocation = {item["invocation_id"]: item for item in outcome_tasks}
    outcome_by_task: dict[str, dict[str, Any]] = {
        item["task_id"]: {
            "task_id": item["task_id"], "task_name": item["task_name"],
            "status": "NOT_DISPATCHED", "failure_code": None,
        }
        for item in outcome_tasks
    }
    dispatch_records = (
        [json.loads(line) for line in dispatch_events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if dispatch_events_path.is_file() else []
    )
    hook_records = (
        [json.loads(line) for line in hook_events_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if hook_events_path.is_file() else []
    )
    for item in dispatch_records:
        task = next(
            (candidate for candidate in outcome_tasks if candidate["task_name"] == item.get("task_name")),
            None,
        )
        if task is None:
            continue
        if item.get("decision") == "ALLOW":
            outcome_by_task[task["task_id"]]["status"] = "DISPATCHED_NOT_STARTED"
        elif item.get("dispatch_binding", {}).get("failure_code") == "RESEARCH_DEPENDENCY_NOT_READY":
            outcome_by_task[task["task_id"]].update(
                status="DEPENDENCY_BLOCKED", failure_code="RESEARCH_DEPENDENCY_NOT_READY"
            )
    for item in hook_records:
        context = item.get("context_binding")
        if (
            item.get("hook_event_name") == "SubagentStart"
            and isinstance(context, Mapping)
            and context.get("invocation_id") in task_by_invocation
        ):
            task = task_by_invocation[context["invocation_id"]]
            outcome_by_task[task["task_id"]].update(
                status="STARTED_NO_TERMINAL", failure_code="TERMINAL_EVENT_MISSING"
            )
        trusted = item.get("trusted_task_binding")
        binding = item.get("output_binding")
        invocation_id = (
            trusted.get("invocation_id") if isinstance(trusted, Mapping) else None
        ) or (binding.get("invocation_id") if isinstance(binding, Mapping) else None)
        if item.get("hook_event_name") != "SubagentStop" or invocation_id not in task_by_invocation:
            continue
        task = task_by_invocation[invocation_id]
        capture = item.get("output_capture")
        if isinstance(capture, Mapping) and capture.get("status") == "SAVED":
            outcome_by_task[task["task_id"]].update(status="SAVED", failure_code=None)
        else:
            outcome_by_task[task["task_id"]].update(
                status="FAILED",
                failure_code=(
                    capture.get("failure_code")
                    if isinstance(capture, Mapping) else "MULTIDIMENSIONAL_OUTPUT_INVALID"
                ),
            )
    task_outcomes = [outcome_by_task[item["task_id"]] for item in outcome_tasks]
    after = integrity_snapshot(repository_root)
    _write_object(invocation_dir / "process-result.json", {
        "schema_version": "multidimensional-stage-process/1.0.0",
        "run_id": manifest["run_id"], "process_exit_code": process_code,
        "timed_out": timed_out, "stage_status": result["status"], "failure_code": failure_code,
        "source_integrity_unchanged": before == after,
        "task_outcomes": task_outcomes,
        "saved_task_count": sum(item["status"] == "SAVED" for item in task_outcomes),
        "failed_task_count": sum(
            item["status"] in {"FAILED", "DEPENDENCY_BLOCKED"} for item in task_outcomes
        ),
        "incomplete_task_count": sum(
            item["status"] in {"NOT_DISPATCHED", "DISPATCHED_NOT_STARTED", "STARTED_NO_TERMINAL"}
            for item in task_outcomes
        ),
    })
    return result, 0 if result["status"] == "PASSED" and before == after else 7
