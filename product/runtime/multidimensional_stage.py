"""多维研究的冻结输入、业务契约及只读历史归集；不派发或启动模型。"""

from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
import re
import secrets
import shutil
import tomllib
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from contextlib import ExitStack
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.council import (
    build_independent_counter_thesis_research_request,
    build_multidimensional_holding_research_request,
)
from product.council.multidimensional_research import RESEARCH_CAPABILITIES
from product.runtime.research_input import (
    artifact_input_binding, is_single_stock, load_research_input, research_input_binding,
    research_input_ref, research_subjects, validate_research_input,
)
from product.mcp.provenance import parse_timestamp
from product.runtime.hashing import canonical_hash, file_hash, legacy_envelope_hash, verify_legacy_envelope_hash, HashContractError
from product.runtime.multidimensional_references import VERSION as REFERENCE_VERSION, known_claim_references
from product.runtime.research_input_topology import (
    DATASET_CAPABILITY_ROUTES, DATASET_DOMAIN, EIGHT_DIMENSION_INPUTS,
    CAPABILITY_BINDINGS, capability_tools, dataset_consumers, fact_dataset,
    select_capability_facts,
)
from product.runtime.schema_validation import validate_schema_definition
from product.runtime.versioning import load_version_manifest, read_skill_version, validate_current_component_versions


STAGE_VERSION = "multidimensional-holding-research-runtime/2.0.0"
SINGLE_STOCK_STAGE_VERSION = "multidimensional-holding-research-runtime/3.0.0"
DISPATCH_VERSION = "multidimensional-research-dispatch/2.1.0"
OUTPUT_CONTRACT_RULES = {
    "version": "multidimensional-output-guidance/1.0.0",
    "local_claim_ids": (
        "claim_id 是本稿本地主张名称，例如 claim_business 或 business；"
        "不得以 e.、c.、d.、k.、p. 开头，也不得使用程序内部 rc1 引用前缀；"
        "这些是保留的运输引用命名空间。"
        "c.* 仅用于目录提供的上游主张引用，不能用作新主张 claim_id。"
        "observation_conditions.claim_refs 及本地关系引用须逐字指向本稿合法 claim_id。"
        "程序不自动改名，也不猜测引用。"
    ),
    "status": (
        "按实际覆盖选择状态，不因部分来源缺失自动判整项失败。"
        "现有校验要求：status=SOURCE_LIMITED 时 evaluation_status 必须为 SOURCE_LIMITED；"
        "status=FAILED/TIMEOUT 时 evaluation_status 不能为 PASS。"
        "LOW_CONFIDENCE/PARTIAL 可表达有据但有限的研究，不代表 COMPLETE。"
        "不要为了配对而删除有依据主张或隐去缺口。"
    ),
    "documents": (
        "documents 只能选本任务 task.allowed_documents 中的文档；旧完整草稿按 document_id 原样复制元数据，"
        "显式新版提交草稿仅选择 document_id，由程序装配原元数据；"
        "不得重写 as_of/published_at/retrieved_at、hash、URL 或其他字段。"
        "verified_documents 的正文内容不是可自行改写的文档元数据。"
        "许可章节仍按 Evidence 引用，不虚构 documents。"
    ),
}
SCOPED_PROVIDER_VIEW_INSTRUCTION = (
    " 本任务 provider_coverage 是从完整审计派生的任务视图：global_coverage"
    " 的状态、计数和失败码属于 provider 全局，不能当作本任务数据集已交付或已引用。"
    "请按 dataset_observations 与 capability_routing 判断局部交付；"
    "NO_DATASET_DETAIL 表示原件无数据集明细，NO_RELEVANT_OBSERVATIONS 表示本任务未选中明细，"
    "两者均不能单独推断无 Evidence 或获取失败。coverage_hash 指向完整审计原件。"
)
RESEARCH_ATTRIBUTION_GUIDANCE = {
    "version": "research-report-attribution/1.3.1",
    "source": (
        "许可章节用 claims[].evidence_refs 引用实际读取的章节；只有本段具体解释"
        "支持、补充或挑战某条上游主张时，才填写该条 research_claim_refs。"
        "独立陈述供应商观点可只引许可 Evidence，不为覆盖上游而多连。"
        "research_relationships[].document_id 只代表该文档自身内容；"
        "不得借用 SEC/发行人 document_id 表达 Morningstar 等其他来源的观点。"
        "没有适用文档关系时 research_relationships 可以为空；不虚构章节 documents，"
        "不因此删除有依据的章节分析。发行人文档自身的支持或冲突仍可记录。"
    ),
    "upstream_scope": (
        "先核对 dependency_reports 中目标 claim 原文和限定范围，再判断关系。"
        "缺少可用截止点价格或估值附件不等于完全没有估值信息；"
        "新增作者公允价值观点不自动推翻上游缺口，也不自动支持价格吸引力。"
        "区分新增信息与实际矛盾，不为填关系强制选择 REVISE/CHALLENGE。"
        "不能把上游的‘无法量化当前市场隐含增长’转述为‘完全没有估值观点’。"
    ),
    "self_check": (
        "利用既有 claims 按独立的支持/挑战/补充关系组织内容，避免一大段挂全部上游引用；"
        "不强制一引用一 claim 或固定主张数。逐项核对每个 claim 的 evidence_refs、document_refs、"
        "research_claim_refs：正文须解释所引用的上游结论及关联；未讨论的上游不要引用，"
        "不要求覆盖全部上游。research_relationships 为空也不能免除上述核对。"
        "写作顺序是先读目标主张原句及限定范围，再在本段说明具体关联，最后填写引用。"
        "逐个 research_claim_ref 反查本段对应的解释；只有相同公司或主题不够，"
        "本段未解释的具体事件主张不引用。不先列全上游ID再拼接正文。"
        "提交前逐项核对关系的来源内容、目标主张原意和 resulting_claim_refs；"
        "对每一个 resulting_claim_ref 分别说明该文档关系如何支持这个结果主张，"
        "不能把同报告中其他合法但无关的 claim 顺手加入；例如收购事实不支持独立研报覆盖不足。"
        "只保留真实相关的结果引用，不为填满关系而添加引用。"
        "无法确认的关系不作确定表述，保留具体限制。ID 合法不代表语义支持已验证。"
    ),
}

TECHNICAL_SUMMARY_GUIDANCE = {
    "version": "technical-summary-consistency/1.0.0",
    "self_check": (
        "提交前用 prepared_analysis 与正文逐项核对摘要：窗口、基准、方向、数值幅度及单位一致。"
        "区分绝对收益与相对收益、百分比与百分点；小幅/显著等描述不能与所引计算相矛盾。"
        "没有充分依据界定幅度时直接呈现计算值，不自行设阈值或补算。"
        "摘要不引入正文和计算未支持的结论；计算、引用和状态仍由原门禁校验。"
    ),
}


def _stage_input_binding(value):
    binding = research_input_binding(value)
    return binding if is_single_stock(value) else {k: v for k, v in binding.items() if k != "handoff_id"}


MINIMUM_QUESTIONS = {
    "TECHNICAL_STRUCTURE": ["趋势与关键价格结构是什么？", "相对广泛市场基准表现如何？", "波动、回撤和量价是否支持解释？", "什么观察信号会推翻解释？"],
    "FUNDAMENTAL_EVENT": ["核心经营驱动是什么？若已准入最近完整财年收入分解表，原单位的总额、主要组成和原表比例如何说明业务结构，并如何与近期季度口径区分？", "盈利与现金流是什么关系？", "估值依赖哪些显式假设？", "关键未知和已公告事件如何影响判断？"],
    "RESEARCH_REPORT": ["作者使用了哪些依据与假设？", "报告之间或与公司资料有哪些真实分歧？", "报告对已有研究主张是支持、挑战、修订还是无新增信息？"],
    "INDUSTRY_COMPARISON": [
        "从已核实冻结同行中选择至少一家：选择依据是什么，双方具体产品或终端需求有何重叠与差异？",
        "双方至少一项同口径、相近期间长度的经营或行情事实如何比较，各自期间与单位是什么？",
        "共同产业因素如何传导、公司差异在哪里，哪些部分不能比较或推断？",
    ],
    "MACRO_CONTEXT": ["利率、通胀、经济活动与政策事实是什么？", "观察期、发布时间与修订边界是什么？", "这些因素怎样分别传导到持仓，什么反向情景会推翻解释？"],
    "MARKET_STATE": ["大盘、相关板块、跨资产、波动、信用与实际市场广度状态是什么？", "哪些指标是代理且有什么边界？", "市场状态怎样分别传导到持仓，什么反向情景会推翻解释？"],
    "OWNERSHIP_DISCLOSURE": ["实际披露发生了什么变化？可比已结束机构期间的供应商汇总如何变化？", "交易类型、披露滞后和覆盖限制是什么？", "哪些内容不能从披露推断？"],
    "OPTIONS_FLOW": ["代表合约身份、到期日、同源 bid/ask 原值和观察时间是什么？报价间距对可交易性的解释有哪些限制（派生数值仅用合法工具/附件）？", "当前 OI/IV、可得 Greeks 及标的 IV/HV 支持什么期限和风险结构观察？若已查询到某一合约的 Greeks，逐项给出该合约可得的 delta、gamma、theta、vega、rho 原值，并解释其符号和风险含义；标的波动单位未知只限制跨口径比较，不抹去合约原值。", "时效、覆盖、单位和直接/代理指标边界是什么？", "哪些资金方向结论不能成立？"],
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


def _resolve_frozen_artifact(root: Path, relative: str) -> Path:
    if (not isinstance(relative, str) or not relative or Path(relative).is_absolute()
            or ".." in Path(relative).parts):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_ARTIFACT_PATH_INVALID")
    candidate = root / relative
    if any(path.is_symlink() for path in (candidate, *candidate.parents)
           if path == root or path.is_relative_to(root)):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_ARTIFACT_PATH_INVALID")
    path = candidate.resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise MultidimensionalStageError(f"MULTIDIMENSIONAL_ARTIFACT_MISSING:{relative}")
    return path


def _read_frozen_object(root: Path, relative: str) -> dict[str, Any]:
    return _read_object(_resolve_frozen_artifact(root, relative))


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


def _text_locator(fact: Mapping[str, Any]) -> dict[str, Any]:
    """Expose extraction structure, not an investment summary or a length ranking."""
    value = fact.get("value")
    metadata = fact.get("metadata") or {}
    if not isinstance(value, str) or not isinstance(metadata, Mapping):
        return {"section_locator": None, "content_kind": None, "text_length": None}
    section = metadata.get("section")
    kind = "UNKNOWN"
    if section:
        # Entire heading/page-number text, not an arbitrary short-text threshold.
        heading = str(section).replace("_", " ")
        if re.fullmatch(r"\s*(?:Item\s+\d+[A-Z]?\.?\s*)?" + re.escape(heading)
                        + r"\s*(?:\d+)?\s*", value, flags=re.I):
            kind = "HEADING_ONLY"
        else:
            kind = "SECTION_EXCERPT" if metadata.get("truncated") else "SECTION_TEXT"
    return {
        "section_locator": section,
        "content_kind": kind,
        "text_length": len(value),
    }


def _skill_version(path: Path) -> str:
    try:
        return read_skill_version(path)
    except ValueError as exc:
        raise MultidimensionalStageError(f"MULTIDIMENSIONAL_SKILL_VERSION_MISSING:{path.parent.name}") from exc


def _agent_binding(product_root: Path, name: str) -> dict[str, Any]:
    path = product_root / ".codex/agents" / f"{name}.toml"
    with path.open("rb") as stream:
        config = tomllib.load(stream)
    if config.get("name") != name:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_AGENT_BINDING_INVALID")
    approved = load_version_manifest(product_root / "version-manifest.json")["agents"]
    version = approved.get(name.replace("_", "-"))
    if not isinstance(version, str):
        raise MultidimensionalStageError(f"MULTIDIMENSIONAL_AGENT_VERSION_UNAPPROVED:{name}")
    return {
        "name": name,
        "version": version,
        "content_hash": file_hash(path),
    }


def _skill_binding(product_root: Path, name: str) -> dict[str, Any]:
    path = product_root / "skills" / name / "SKILL.md"
    version = _skill_version(path)
    approved = load_version_manifest(product_root / "version-manifest.json")["skills"].get(name)
    if version != approved:
        raise MultidimensionalStageError(f"MULTIDIMENSIONAL_SKILL_VERSION_DRIFT:{name}")
    return {"name": name, "version": version, "content_hash": file_hash(path)}


def _facts_for_capability(
    evidence: Sequence[Mapping[str, Any]], *, capability: str, security_ids: Sequence[str], benchmark_id: str | None,
) -> list[dict[str, Any]]:
    return select_capability_facts(
        evidence, capability=capability, security_ids=security_ids,
        benchmark_id=benchmark_id,
    )


def _capability_routing_coverage(
    evidence: Sequence[Mapping[str, Any]], *, capture_batches: Sequence[Mapping[str, Any]],
    security_ids: Sequence[str], benchmark_id: str | None,
) -> dict[str, Any]:
    """逐 dataset/consumer 审计候选路由；准备阶段不声称实际查询或引用。"""

    captured: dict[str, set[str]] = {}
    for batch in capture_batches:
        for item in batch.get("capabilities", []):
            dataset = str(item.get("dataset", ""))
            captured.setdefault(dataset, set()).update(
                value for value in item.get("evidence_ids", []) if isinstance(value, str)
            )
    gate_by_dataset: dict[str, list[Mapping[str, Any]]] = {}
    for fact in evidence:
        gate_by_dataset.setdefault(fact_dataset(fact), []).append(fact)

    selected_by_capability = {}
    delivered_by_capability = {}
    for capability in EIGHT_DIMENSION_INPUTS:
        scoped = _facts_for_capability(
            evidence, capability=capability, security_ids=security_ids,
            benchmark_id=benchmark_id,
        )
        if capability in {"MACRO_CONTEXT", "MARKET_STATE"}:
            # 与原任务装配使用同一精选公司暴露接缝，不能仅审计第一层 selector。
            scoped = [*scoped, *_macro_company_context_facts(evidence, security_ids=security_ids)]
        selected_by_capability[capability] = {item["evidence_id"] for item in scoped}
        if capability in {"MARKET_STATE", "INDUSTRY_COMPARISON"}:
            scoped = _bounded_latest_facts(scoped)
        delivered_by_capability[capability] = {item["evidence_id"] for item in scoped}

    observations = []
    failure_codes: list[str] = []
    unmapped_datasets = []
    datasets = set(DATASET_DOMAIN) | set(captured) | set(gate_by_dataset)
    for dataset in sorted(datasets):
        gate_facts = gate_by_dataset.get(dataset, [])
        gate_ids = {str(item["evidence_id"]) for item in gate_facts
                    if isinstance(item.get("evidence_id"), str)}
        consumers = dataset_consumers(dataset)
        # 保留原来源型选择器的实际候选关系，不丢失多对多，也不因此新增工具权限。
        actual_consumers = {cap for cap, ids in selected_by_capability.items() if gate_ids & ids}
        targets = sorted(set(consumers) | actual_consumers)
        unmapped = dataset not in DATASET_DOMAIN or not consumers
        if unmapped and (gate_facts or dataset in captured):
            unmapped_datasets.append(dataset)
        for capability in targets or ["UNMAPPED"]:
            delivered_ids = gate_ids & delivered_by_capability.get(capability, set())
            exclusions = []
            primary = dataset in DATASET_CAPABILITY_ROUTES.get(capability, set())
            for fact in gate_facts:
                evidence_id = str(fact.get("evidence_id", ""))
                if evidence_id in delivered_ids:
                    continue
                if evidence_id in selected_by_capability.get(capability, set()):
                    reason = "BOUNDED_LATEST"
                elif capability == "UNMAPPED":
                    reason = "UNMAPPED"
                elif primary:
                    reason = "CAPABILITY_EVIDENCE_NOT_ROUTED"
                    failure_codes.append(f"{reason}:{capability}:{evidence_id}")
                else:
                    reason = "OUTSIDE_EXISTING_CAPABILITY_SCOPE"
                exclusions.append({"evidence_id": evidence_id, "reason": reason})
            observations.append({
                "dataset": dataset, "source_domain": DATASET_DOMAIN.get(dataset, "UNMAPPED"),
                "mapping_status": "UNMAPPED" if unmapped else "MAPPED",
                "target_capability": capability,
                "capture_evidence_count": len(captured.get(dataset, set())),
                "capture_evidence_ids": sorted(captured.get(dataset, set())),
                "gate_eligible_evidence_count": len(gate_ids),
                "gate_eligible_evidence_ids": sorted(gate_ids),
                "delivered_evidence_count": len(delivered_ids),
                "delivered_evidence_ids": sorted(delivered_ids),
                "delivery_status": ("DELIVERED" if delivered_ids else "NOT_DELIVERED"
                                    if gate_ids else "NO_GATE_EVIDENCE"),
                "delivery_basis": "PREPARATION_SELECTOR_NOT_QUERY",
                "exclusions": exclusions,
                "actual_research_use_status": "NOT_EVALUATED_AT_PREPARATION",
            })
    return {
        "dataset_observations": observations, "unmapped_datasets": sorted(unmapped_datasets),
        "failure_codes": sorted(set(failure_codes)),
        "status": "FAILED" if failure_codes else "UNMAPPED" if unmapped_datasets else "CLOSED",
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


def _latest_annual_eps_focus(
    facts: Sequence[Mapping[str, Any]], *, security_id: str,
) -> list[dict[str, str]]:
    """Expose the latest admitted FY EPS locators, not an estimated valuation."""

    candidates: list[tuple[str, Mapping[str, Any], Mapping[str, Any]]] = []
    for fact in facts:
        metadata = fact.get("metadata")
        if (
            fact.get("security_id") != security_id
            or fact.get("semantic_field") != "us-gaap.EarningsPerShareDiluted"
            or not isinstance(metadata, Mapping)
            or metadata.get("fiscal_period") != "FY"
            or metadata.get("context_type") != "duration"
            or not (
                fact.get("source_type") == "sec"
                or str(fact.get("source_id", "")).lower().startswith("sec-")
            )
        ):
            continue
        start, end = metadata.get("period_start"), metadata.get("period_end")
        if not isinstance(start, str) or not isinstance(end, str):
            continue
        try:
            if datetime.fromisoformat(start) > datetime.fromisoformat(end):
                continue
        except ValueError:
            continue
        candidates.append((end, fact, metadata))
    if not candidates:
        return []
    latest_end = max(end for end, _, _ in candidates)
    return [
        {
            "evidence_id": str(fact["evidence_id"]),
            "semantic_field": "us-gaap.EarningsPerShareDiluted",
            "period_start": str(metadata["period_start"]),
            "period_end": str(metadata["period_end"]),
            "unit": str(fact.get("unit", "")),
        }
        for end, fact, metadata in sorted(candidates, key=lambda item: str(item[1]["evidence_id"]))
        if end == latest_end
    ]


def _same_period_profit_cash_focus(
    facts: Sequence[Mapping[str, Any]], *, security_id: str,
) -> list[dict[str, str]]:
    """Locate recent same-period SEC profit/cash candidates without choosing an interpretation."""

    fields = (
        "us-gaap.NetIncomeLoss",
        "us-gaap.NetCashProvidedByUsedInOperatingActivities",
    )
    by_period: dict[tuple[str, str], dict[str, list[Mapping[str, Any]]]] = {}
    for fact in facts:
        metadata = fact.get("metadata")
        field = fact.get("semantic_field")
        if (
            fact.get("security_id") != security_id
            or field not in fields
            or not isinstance(metadata, Mapping)
            or metadata.get("context_type") != "duration"
            or fact.get("unit") != "USD"
            or not (
                fact.get("source_type") == "sec"
                or str(fact.get("source_id", "")).lower().startswith("sec-")
            )
        ):
            continue
        start, end = metadata.get("period_start"), metadata.get("period_end")
        if not isinstance(start, str) or not isinstance(end, str):
            continue
        try:
            if datetime.fromisoformat(start) > datetime.fromisoformat(end):
                continue
        except ValueError:
            continue
        by_period.setdefault((start, end), {}).setdefault(str(field), []).append(fact)
    matched = [period for period, items in by_period.items() if all(field in items for field in fields)]
    if not matched:
        return []
    period = max(matched, key=lambda item: (item[1], item[0]))
    focus = []
    for field in fields:
        # At most two locators per metric. All Evidence remains in the full allowed catalog.
        candidates = sorted(
            by_period[period][field],
            key=lambda item: (
                str(item.get("published_at", "")),
                str(item.get("retrieved_at", "")),
                str(item["evidence_id"]),
            ),
            reverse=True,
        )[:2]
        focus.extend({
            "evidence_id": str(item["evidence_id"]),
            "semantic_field": field,
            "period_start": period[0],
            "period_end": period[1],
            "unit": "USD",
        } for item in candidates)
    return focus


def _latest_insider_trade_focus(
    facts: Sequence[Mapping[str, Any]], *, security_id: str, cutoff: str,
) -> list[dict[str, str]]:
    """Point to admitted recent insider rows without copying amounts or inferring filing lag."""

    limit = parse_timestamp(cutoff)
    candidates: list[tuple[date, date, Mapping[str, Any], Mapping[str, Any]]] = []
    for fact in facts:
        value = fact.get("value")
        if (
            fact.get("security_id") != security_id
            or not str(fact.get("semantic_field", "")).startswith("moomoo_insider_trade:")
            or not isinstance(value, Mapping)
            or not isinstance(value.get("trade_date_start"), str)
            or not isinstance(value.get("trade_date_end"), str)
            or not isinstance(value.get("transaction_type"), str)
            or not value["transaction_type"].strip()
        ):
            continue
        try:
            start_day = date.fromisoformat(value["trade_date_start"])
            end_day = date.fromisoformat(value["trade_date_end"])
            timestamps = [parse_timestamp(str(fact[key])) for key in ("as_of", "published_at", "retrieved_at")]
        except (KeyError, TypeError, ValueError):
            continue
        if start_day > end_day or end_day > limit.date() or any(stamp > limit for stamp in timestamps):
            continue
        candidates.append((end_day, start_day, fact, value))
    return [
        {
            "evidence_id": str(fact["evidence_id"]),
            "trade_date_start": start_day.isoformat(),
            "trade_date_end": end_day.isoformat(),
            "transaction_type": str(value["transaction_type"]),
            "observed_at": str(fact["published_at"]),
        }
        for end_day, start_day, fact, value in sorted(
            candidates, key=lambda item: (item[0], item[1], str(item[2]["evidence_id"])), reverse=True,
        )[:3]
    ]


_SEC_REVENUE_TABLE_UNIT = re.compile(
    r"\btable\b.{0,120}\brevenue\b.{0,120}\(in (?P<unit>millions|billions), except percentages\)",
    re.IGNORECASE,
)


def _sec_revenue_table_unit_focus(
    facts: Sequence[Mapping[str, Any]], *, security_id: str,
) -> list[dict[str, str]]:
    """Expose a disclosed table header's unit, never derived table amounts."""

    focus: list[dict[str, str]] = []
    for fact in facts:
        if (
            fact.get("security_id") != security_id
            or fact.get("semantic_field") != "business"
            or not (
                fact.get("source_type") == "sec"
                or str(fact.get("source_id", "")).lower().startswith("sec-")
            )
            or not isinstance(fact.get("value"), str)
        ):
            continue
        match = _SEC_REVENUE_TABLE_UNIT.search(fact["value"])
        if match:
            focus.append({
                "evidence_id": str(fact["evidence_id"]),
                "semantic_field": "business",
                "table_unit": match.group("unit").lower(),
                "table_label": "revenue_disaggregation",
            })
    return sorted(focus, key=lambda item: item["evidence_id"])


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


from product.tools.precomputed import _technical_rows



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


def _latest_market_breadth(evidence, as_of):
    cutoff = parse_timestamp(as_of)
    candidates = [f for f in evidence
                  if f.get("semantic_field") == "moomoo_us_rise_fall_distribution"
                  and f.get("security_id") == "US:MARKET"
                  and parse_timestamp(f["as_of"]) <= cutoff
                  and parse_timestamp(f["retrieved_at"]) <= cutoff]
    return max(candidates, key=lambda f: (
        parse_timestamp(f["as_of"]), parse_timestamp(f["retrieved_at"]), f["evidence_id"],
    ), default=None)


def _prepare_macro_market_artifacts(
    run_dir: Path, *, task_id: str, benchmark_id: str,
    evidence: Sequence[Mapping[str, Any]], as_of: str,
) -> dict[str, Any]:
    """从冻结的广泛市场日线生成共享宏观任务可消费的市场状态。"""

    from product.deterministic.market_analysis import calculate_market_state_statistics, calculate_market_breadth

    market_rows = _technical_rows(evidence, security_id=benchmark_id)
    directory = run_dir / "research/precomputed" / canonical_hash({"task_id": task_id})[:16]
    directory.mkdir(parents=True, exist_ok=False)
    result: dict[str, Any] = {
        "calculation": None,
        "chart": None,
        "gaps": [],
        "allowed_artifact_refs": [],
    }
    fact = _latest_market_breadth(evidence, as_of)
    result["breadth_calculation"] = None
    if fact is not None:
        try:
            breadth = calculate_market_breadth(fact)
        except ValueError as exc:
            result["gaps"].append({
                "reason_code": str(exc), "description": "广度分桶不能可靠汇总。",
                "impact": "保留原分桶；不得由模型补算完整合计。",
            })
        else:
            breadth_ref = str((directory / "market-breadth-calculation.json").relative_to(run_dir))
            _write_object(run_dir / breadth_ref, breadth)
            result["breadth_calculation"] = breadth
            result["breadth_calculation_ref"] = breadth_ref
            result["breadth_report_calculation"] = {
                "calculation_id": breadth["artifact_id"], "method": "provider_breadth_partition_sum",
                "value": json.dumps(breadth["counts"], sort_keys=True, separators=(",", ":")),
                "unit": breadth["unit"], "input_evidence_refs": breadth["evidence_fact_ids"],
                "artifact_ref": breadth_ref,
            }
            result["allowed_artifact_refs"].append(breadth_ref)
    else:
        result["gaps"].append({
            "reason_code": "MARKET_BREADTH_MISSING", "description": "无截止点内可用广度快照。",
            "impact": "不能计算广度合计，不影响已有基准统计。",
        })
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
    allowed_calculation_evidence_ids: Sequence[str] = (),
    allowed_documents: Sequence[Mapping[str, Any]] = (),
    claims_forbidden: bool = False,
    technical_calculation_missing: bool = False,
    source_literal_selection: bool = False,
    macro_observation_selection: bool = False,
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
    schema["$defs"]["calculation"]["properties"]["input_evidence_refs"]["items"] = {
        "type": "string", "enum": sorted(set(allowed_evidence_ids) | set(allowed_calculation_evidence_ids))
    }
    schema["properties"]["documents"] = {
        "type": "array", "items": {
            "type": "object", "enum": [copy.deepcopy(dict(item)) for item in allowed_documents]
        }
    }
    if source_literal_selection:
        schema["properties"]["source_literal_selections"] = {
            "type": "array", "maxItems": 16,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["claim_id", "placeholder", "evidence_ref", "field"],
                "properties": {
                    "claim_id": {"type": "string"},
                    "placeholder": {"type": "string", "pattern": r"^\{\{sf\.[A-Za-z][A-Za-z0-9_]{0,23}\}\}$"},
                    "evidence_ref": {"type": "string"},
                    "field": {"type": "string", "enum": (
                        ["moomoo_macro_observation"] if macro_observation_selection
                        else ["sec_usd_value", "as_of", "retrieved_at"]
                    )},
                },
            },
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
    validate_schema_definition(schema)
    return schema


def _task_id(capability: str, security_id: str | None) -> str:
    suffix = security_id.replace(":", "_").lower() if security_id else "shared"
    return f"{capability.lower()}:{suffix}"


def validate_breadth_calculation_references(run_dir: Path, report: Mapping[str, Any]) -> None:
    """Recompute new breadth artifacts from frozen Gate, including downstream reads."""
    from product.deterministic.market_analysis import calculate_market_breadth

    calculations = [c for c in report.get("calculations", [])
                    if str(c.get("artifact_ref", "")).endswith("/market-breadth-calculation.json")]
    refs = {r for r in report.get("artifact_refs", [])
            if isinstance(r, str) and r.endswith("/market-breadth-calculation.json")}
    refs.update(c["artifact_ref"] for c in calculations)
    if not refs:
        return
    root = run_dir.resolve()
    gate = _read_object(root / "evidence/gate.json")
    facts = {f["evidence_id"]: f for f in gate["allowed_evidence"]}
    for ref in refs:
        path = (root / ref).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise MultidimensionalStageError("MARKET_BREADTH_ARTIFACT_INVALID")
        artifact = _read_object(path)
        ids = artifact.get("evidence_fact_ids", [])
        if len(ids) != 1 or ids[0] not in facts:
            raise MultidimensionalStageError("MARKET_BREADTH_LINEAGE_INVALID")
        fact = facts[ids[0]]
        cutoff = parse_timestamp(gate["decision_cutoff"])
        if any(parse_timestamp(fact[k]) > cutoff for k in ("as_of", "retrieved_at")):
            raise MultidimensionalStageError("MARKET_BREADTH_PIT_INVALID")
        if artifact != calculate_market_breadth(fact):
            raise MultidimensionalStageError("MARKET_BREADTH_ARTIFACT_MISMATCH")
        for calculation in calculations:
            if calculation["artifact_ref"] == ref and (
                calculation.get("calculation_id") != artifact["artifact_id"]
                or calculation.get("input_evidence_refs") != ids
            ):
                raise MultidimensionalStageError("MARKET_BREADTH_REFERENCE_INVALID")
            if calculation["artifact_ref"] == ref:
                try:
                    counts = json.loads(calculation.get("value", ""))
                except (TypeError, ValueError) as exc:
                    raise MultidimensionalStageError("MARKET_BREADTH_VALUE_INVALID") from exc
                if (not isinstance(counts, dict) or any(type(v) is not int for v in counts.values())
                        or counts != artifact["counts"] or calculation.get("unit") != artifact["unit"]
                        or calculation.get("method") != "provider_breadth_partition_sum"):
                    raise MultidimensionalStageError("MARKET_BREADTH_VALUE_INVALID")


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
    source_handoff = load_research_input(source_run, manifest=manifest)
    if (
        research_input_binding(source_handoff) != research_input_binding(expected_handoff)
    ):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_SOURCE_PORTFOLIO_MISMATCH")
    source_gate = _read_object(source_run / "evidence/gate.json")
    target_cutoff = target_gate.get("decision_cutoff")
    source_cutoff = source_gate.get("decision_cutoff")
    if (
        not isinstance(source_cutoff, str)
        or not isinstance(target_cutoff, str)
        or parse_timestamp(source_cutoff) > parse_timestamp(target_cutoff)
        or (is_single_stock(expected_handoff) and source_cutoff != target_cutoff)
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
        or source_proof.get("proof_hash") != legacy_envelope_hash(source_proof, hash_field="proof_hash")
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
        **_stage_input_binding(expected_handoff),
        "target_decision_cutoff": target_cutoff,
        "reports": imported,
        "rejected_reports": rejected,
    }
    proof["import_hash"] = legacy_envelope_hash(proof, hash_field="import_hash")
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


def _issuer_document_title(fact: Mapping[str, Any]) -> str:
    metadata = fact.get("metadata") if isinstance(fact.get("metadata"), Mapping) else {}
    form = str(metadata.get("form") or fact.get("form") or "").upper()
    section = str(fact.get("section") or fact.get("semantic_field") or "")
    if form in {"10-Q", "10-Q/A", "10-K", "10-K/A"} and section == "management_discussion":
        return f"SEC Form {form} Management's Discussion and Analysis excerpt"
    if form in {"8-K", "8-K/A"} and section == "earnings_release":
        return f"SEC Form {form} earnings release excerpt"
    if form in {"10-Q", "10-Q/A", "10-K", "10-K/A", "8-K", "8-K/A"}:
        return f"SEC Form {form} {section or 'section unknown'} excerpt"
    return f"SEC filing form unknown, {section or 'section unknown'} excerpt"


def _dependency_calculation_records(
    run_dir: Path, *, report: Mapping[str, Any], dependency_task: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Project only calculations cited by claims, after checking their original receipts."""
    ledger_ref = dependency_task.get("calculation_ledger_ref")
    if not ledger_ref:
        return []
    from product.runtime.calculation_handoff import validate_tool_calculations

    invocation = _read_object(run_dir / dependency_task["invocation_path"])
    validate_tool_calculations(
        report, task=dependency_task, invocation=invocation, run_dir=run_dir,
    )
    ledger = run_dir / ledger_ref
    receipts = {
        item["calculation_id"]: item
        for item in (json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines())
    }
    calculations = {
        item["calculation_id"]: item for item in report.get("calculations", [])
        if item.get("artifact_ref") == ledger_ref
    }
    result = []
    for claim in report.get("claims", []):
        for calculation_id in claim.get("calculation_refs", []):
            if calculation_id not in calculations:
                continue
            calculation = calculations[calculation_id]
            receipt = receipts[calculation_id]
            result.append({
                "claim_id": claim["claim_id"],
                "calculation_id": calculation_id,
                "method": calculation["method"],
                "value": calculation["value"],
                "unit": calculation["unit"],
                "input_evidence_refs": calculation["input_evidence_refs"],
                "artifact_ref": ledger_ref,
                "receipt_hash": receipt["receipt_hash"],
                "tool_event_hash": receipt["tool_event_hash"],
            })
    return result


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
                "title": _issuer_document_title(fact),
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
                    "classification": (
                        "SEC_MANAGEMENT_DISCUSSION_EXCERPT"
                        if fact.get("semantic_field") == "management_discussion"
                        else "SEC_EARNINGS_RELEASE_EXCERPT"
                    ),
                    "body_access": "query the bound Gate evidence_id",
                },
            })
    return result


def _import_research_materials(
    *, source_run: Path, target_run: Path, expected_handoff: Mapping[str, Any],
    target_gate: Mapping[str, Any], expected_security_ids: Sequence[str],
) -> dict[str, Any]:
    """重验资料准备输出并复制其选择、正文和工具证明。"""

    from product.runtime.research_materials_stage import (
        validate_material_preparation_output, verify_material_tool_audit, SEMANTIC_OUTPUT_VERSION,
    )

    source_run = Path(source_run).resolve()
    target_run = Path(target_run).resolve()
    source_manifest = _read_object(source_run / "run_manifest.json")
    materials = _read_object(source_run / "research/material-preparation-manifest.json")
    source_index = _read_object(source_run / "research/dispatch-index.json")
    if is_single_stock(expected_handoff):
        from product.runtime.single_stock_input import validate_preparation_request_lineage
        from product.runtime.research_materials_stage import require_complete_research_materials_stage
        source_input = load_research_input(source_run, manifest=source_manifest)
        validate_preparation_request_lineage(expected_handoff, source_input)
        require_complete_research_materials_stage(source_run)
        if any(materials.get(k) != v for k, v in research_input_binding(source_input).items()):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_MATERIALS_INPUT_BINDING_INVALID")
    if (
        source_manifest.get("stage") != "MULTIDIMENSIONAL_MATERIAL_PREPARATION"
        or materials.get("manifest_hash") != legacy_envelope_hash(materials, hash_field="manifest_hash")
        or (not is_single_stock(expected_handoff) and (
            materials.get("handoff_hash") != expected_handoff.get("handoff_hash")
            or materials.get("portfolio_hash") != expected_handoff.get("portfolio_hash")))
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
        if materialization.get("materialization_hash") != legacy_envelope_hash(materialization, hash_field="materialization_hash"):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_PEER_MATERIALIZATION_INVALID")
        if materialization.get("final_view_hash") is not None:
            final_view = _read_object(
                source_run / "research/peer-materialization/final-view.json"
            )
            peer_gate = target_gate
            if is_single_stock(expected_handoff):
                peer_gate = _read_object(source_run / "research/peer-materialization/gate.json")
                delivery_fields = {"source_bundle_id", "source_bundle_hash", "run_id", "decision_cutoff", "bundle_hash"}
                if (any(target_gate.get(k) != v for k, v in peer_gate.items() if k not in delivery_fields)
                        or parse_timestamp(peer_gate["decision_cutoff"]) > parse_timestamp(target_gate["decision_cutoff"])):
                    raise MultidimensionalStageError("MULTIDIMENSIONAL_PEER_FINAL_SOURCE_CHANGED")
            if (
                final_view.get("view_hash") != materialization["final_view_hash"]
                or final_view["view_hash"] != legacy_envelope_hash(final_view, hash_field="view_hash")
                or final_view.get("gate_hash") != peer_gate.get("bundle_hash")
                or materialization.get("merged_gate_hash") != peer_gate.get("bundle_hash")
                or final_view.get("decision_cutoff") != peer_gate.get("decision_cutoff")
                or final_view.get("allowed_evidence_ids") != target_gate.get("allowed_evidence_ids")
            ):
                raise MultidimensionalStageError("MULTIDIMENSIONAL_PEER_FINAL_VIEW_INVALID")
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
        audit_binding = {}
        if task.get("semantic_output_version") == SEMANTIC_OUTPUT_VERSION:
            events = [json.loads(line) for line in (source_run / "invocation/subagent-events.jsonl").read_text().splitlines() if line.strip()]
            captures = [event["output_capture"] for event in events
                        if event.get("hook_event_name") == "SubagentStop"
                        and event.get("output_binding", {}).get("invocation_id") == task["invocation_id"]
                        and event.get("output_capture", {}).get("task_id") == task_id
                        and event["output_capture"].get("status") == "SAVED"]
            if len(captures) != 1 or captures[0].get("path") != output_ref:
                raise MultidimensionalStageError("MULTIDIMENSIONAL_MATERIALS_OUTPUT_BINDING_INVALID")
            audit_binding = verify_material_tool_audit(source_run, task, output, captures[0])
            if (output_entry.get("output_hash") != canonical_hash(output)
                    or any(output_entry.get(key) != value for key, value in audit_binding.items())):
                raise MultidimensionalStageError("MULTIDIMENSIONAL_MATERIALS_OUTPUT_BINDING_INVALID")
        destination = destination_root / canonical_hash({"task_id": task_id})[:16]
        destination.mkdir(parents=True, exist_ok=False)
        copied_output = destination / "preparation-result.json"
        shutil.copy2(source_run / output_ref, copied_output)
        copied_refs.append(str(copied_output.relative_to(target_run)))
        copied_artifacts = []
        if audit_binding:
            copied_audit = destination / "tool-audit.json"
            shutil.copy2(source_run / audit_binding["tool_audit_ref"], copied_audit)
            copied_ref = str(copied_audit.relative_to(target_run))
            copied_refs.append(copied_ref)
            copied_artifacts.append({"artifact_ref": copied_ref, "file_hash": file_hash(copied_audit)})
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
                    # 获取尝试也记录 document_id，但不是正文，不可按 ID 一项混为同类。
                    if (candidate.get("schema_version") == "verified-research-document/1.0.0"
                            and candidate.get("document_id") == selection["document_id"]
                            and candidate.get("candidate_id") == selection["candidate_id"]):
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
        **_stage_input_binding(expected_handoff),
        "gate_content_hash": comparable_gate_hash, "entries": import_entries,
        "peer_materialization_file_hash": (
            file_hash(materialization_path) if materialization_path.is_file() else None
        ),
    }
    proof["import_hash"] = legacy_envelope_hash(proof, hash_field="import_hash")
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
    for_execution: bool = True,
) -> dict[str, Any]:
    run_dir = Path(run_dir).resolve()
    index = (_read_object(run_dir / "research/dispatch-index.json") if for_execution else
             _read_frozen_object(run_dir, "research/dispatch-index.json"))
    reference_root = str(run_dir)
    if not for_execution:
        manifest = _read_frozen_object(run_dir, "run_manifest.json")
        reference_root = manifest.get("output_dir")
        if (not isinstance(reference_root, str) or not Path(reference_root).is_absolute()
                or manifest.get("manifest_hash") != legacy_envelope_hash(manifest, hash_field="manifest_hash")
                or index.get("index_hash") != legacy_envelope_hash(index, hash_field="index_hash")
                or manifest.get("dispatch_index_hash") != index.get("index_hash")
                or manifest.get("run_id") != index.get("run_id")):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_ARTIFACT_BINDING_INVALID")
        # 原目录只参与原短引用身份重建，绝不作为文件读取路径。
    matches = [item for item in index["tasks"] if item["task_name"] == task_name]
    if len(matches) != 1:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_TASK_UNKNOWN")
    task = matches[0]
    packet = (_read_object(run_dir / task["packet_path"]) if for_execution else
              _read_frozen_object(run_dir, task["packet_path"]))
    if canonical_hash(packet) != task["packet_hash"]:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_PACKET_HASH_MISMATCH")
    from product.runtime.research_submission import ASSEMBLY_VERSIONS
    if task.get("submission_version") in ASSEMBLY_VERSIONS:
        gate = _read_object(run_dir / "evidence/gate.json")
        manifest = _read_object(run_dir / "run_manifest.json")
        if (gate.get("bundle_hash") != legacy_envelope_hash(gate, hash_field="bundle_hash") or manifest.get("gate_hash") != gate.get("bundle_hash")
                or gate.get("decision_cutoff") != task["time_context"]["window_end"]):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_SUBMISSION_GATE_BINDING_INVALID")
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
        if report.get("report_hash") != legacy_envelope_hash(report, hash_field="report_hash"):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_DEPENDENCY_REPORT_HASH_MISMATCH")
        if packet.get("reference_transport_version") is not None:
            expected = [t for t in index["tasks"] if t["task_id"] == dependency_id]
            if (len(expected) != 1 or report.get("run_id") != task["run_id"]
                    or report.get("invocation_id") != expected[0]["invocation_id"]
                    or report.get("bindings", {}).get("decision_cutoff") != task["time_context"]["window_end"]):
                raise MultidimensionalStageError("MULTIDIMENSIONAL_DEPENDENCY_REPORT_BINDING_MISMATCH")
        calculation_records = []
        if packet["task"].get("submission_version") in ASSEMBLY_VERSIONS:
            dependency_task = next(t for t in index["tasks"] if t["task_id"] == dependency_id)
            calculation_records = _dependency_calculation_records(
                run_dir, report=report, dependency_task=dependency_task,
            )
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
            **({"verified_calculations": calculation_records}
               if packet["task"].get("submission_version") in ASSEMBLY_VERSIONS else {}),
        })
    if task.get("depends_on") and include_dependency_reports:
        packet["dependency_reports"] = dependency_reports
        from product.runtime.multidimensional_references import VERSION, known_claim_references
        packet["allowed_research_claim_ids"] = (
            known_claim_references(dependency_reports, allow_legacy=False)
            if packet.get("reference_transport_version") == VERSION else sorted({
                claim["claim_id"] for report in dependency_reports for claim in report["claims"]
            })
        )
    if packet.get("reference_transport_version") is not None:
        from product.runtime.multidimensional_references import READ_VERSIONS, build_reference_map
        if packet["reference_transport_version"] not in READ_VERSIONS:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_REFERENCE_VERSION_INVALID")
        gate = _read_object(run_dir / "evidence/gate.json")
        packet["reference_map"] = build_reference_map(packet, canonical_hash(gate), reference_root)
    return packet


def _compact_multidimensional_coverage(coverage: Mapping[str, Any]) -> dict[str, Any]:
    """Keep research-relevant source limits; the complete audit stays frozen on disk."""

    if coverage.get("view_kind") == "TASK_SCOPED_PROVIDER_COVERAGE":
        return copy.deepcopy(dict(coverage))
    providers = []
    for provider in coverage.get("providers", []):
        observations = provider.get("dataset_observations", [])
        relevant = [
            {key: item[key] for key in (
                "security_id", "dataset", "status", "failure_code", "as_of",
                "checked_at", "limitations",
            ) if item.get(key) is not None}
            for item in observations
            if item.get("status") not in {"AVAILABLE", "READY"}
            or item.get("failure_code") or item.get("limitations")
        ]
        dataset_counts: dict[str, dict[str, int]] = {}
        for item in observations:
            dataset = str(item.get("dataset") or "UNKNOWN")
            status = str(item.get("status") or "UNKNOWN")
            counts = dataset_counts.setdefault(dataset, {})
            counts[status] = counts.get(status, 0) + 1
        providers.append({
            **{key: provider[key] for key in (
                "plane", "provider", "region", "access", "declared_status",
                "observed_status", "delivery_status", "failure_codes",
                "limitations", "global_coverage", "dataset_observation_scope",
            ) if key in provider},
            "dataset_status_counts": dataset_counts,
            "dataset_observations": relevant,
        })
    return {
        "schema_version": "multidimensional-model-coverage/1.0.0",
        "audit_ref": "audit/provider-coverage.json",
        "audit_hash": coverage.get("coverage_hash"),
        "decision_cutoff": coverage.get("decision_cutoff"),
        "providers": providers,
        "fallback_policy": coverage.get("fallback_policy"),
        "observation_rule": (
            "dataset_observations lists failures and limitations; AVAILABLE/READY "
            "observations are counted in dataset_status_counts. Global provider "
            "status does not prove task evidence was delivered."
        ),
    }


def _model_output_format_guide(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Remove only repeated ID enums; the server still validates the full schema."""

    guide = copy.deepcopy(dict(schema))

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            options = value.get("enum")
            if (
                isinstance(options, list) and options
                and all(isinstance(item, str) and item.startswith("ev-") for item in options)
            ):
                value.pop("enum")
                value["description"] = (
                    "Use a full evidence_id returned by this invocation's query tool; "
                    "the authoritative frozen schema enforces the allowed set."
                )
            else:
                for child in value.values():
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(guide)
    return guide


def serialize_multidimensional_model_context(packet: Mapping[str, Any]) -> str:
    """Provide a lossless evidence locator without duplicating the audit or ID enums."""

    if packet.get("dispatch_contract") != DISPATCH_VERSION:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_MODEL_CONTEXT_VERSION_INVALID")
    frozen_packet_hash = canonical_hash(packet)
    canonical_packet = packet
    reference_map = packet.get("reference_map")
    if reference_map is not None:
        from product.runtime.multidimensional_references import translate_references
        packet = translate_references(dict(packet), reference_map, to_model=True)
        packet.pop("reference_map", None)
    catalog = packet.get("evidence_catalog")
    if not isinstance(catalog, list):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_MODEL_CATALOG_INVALID")
    columns = (
        "evidence_id", "security_id", "semantic_field", "source_id",
        "as_of", "published_at", "retrieved_at", "unit", "usage",
        "section_locator", "content_kind", "text_length",
    )
    if any(not isinstance(item, Mapping) for item in catalog):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_MODEL_CATALOG_INVALID")
    identifiers = [item.get("evidence_id") for item in catalog]
    if (
        any(not isinstance(item, str) for item in identifiers)
        or len(identifiers) != len(set(identifiers))
        or set(identifiers) != set(packet.get("allowed_evidence_ids", []))
    ):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_MODEL_CATALOG_BINDING_INVALID")
    task = copy.deepcopy(packet["task"])
    task.pop("allowed_evidence_ids", None)
    task.pop("allowed_calculation_evidence_ids", None)
    context = {
        **{key: copy.deepcopy(value) for key, value in packet.items()
           if key not in {
               "task", "allowed_evidence_ids", "evidence_catalog",
               "provider_coverage", "output_schema", "output_schema_hash",
               "submission_access",
           }},
        "model_context_version": "multidimensional-model-context/1.0.0",
        "frozen_packet_hash": frozen_packet_hash,
        "task": task,
        "evidence_catalog": {
            "columns": list(columns),
            "rows": [[item.get(key) for key in columns] for item in catalog],
            "row_count": len(catalog),
            "rule": (
                "Each row is a full authorized evidence locator. Query the exact full "
                "evidence_id before citing; keep period, source, unit and limitations "
                "from the tool result. Empty catalog means no direct Evidence query."
            ),
        },
        "provider_coverage": _compact_multidimensional_coverage(packet["provider_coverage"]),
        "output_format_guide": _model_output_format_guide(packet["output_schema"]),
        "authoritative_output_schema_hash": packet["output_schema_hash"],
        "output_contract_rules": copy.deepcopy(OUTPUT_CONTRACT_RULES),
    }
    if task.get("capability") == "RESEARCH_REPORT":
        context["research_attribution_guidance"] = copy.deepcopy(RESEARCH_ATTRIBUTION_GUIDANCE)
    context["instruction"] = (
        context["instruction"]
        + " output_format_guide 只指导草稿格式；服务端仍按冻结的完整 output_schema "
        "及 authoritative_output_schema_hash 校验允许引用，不得凭格式说明猜测 ID。"
    )
    if reference_map is not None:
        context["model_context_version"] = "multidimensional-model-context/2.0.0"
        context["reference_map_hash"] = reference_map["map_hash"]
        context["citation_contract"] = {
            "version": reference_map["binding"]["version"],
            "instruction": "e.* 是本任务 Evidence 引用，c.* 是限定报告版本的上游主张引用，d.* 是允许文档引用（仅提供目录中实际存在的类型）。查询、计算及草稿引用使用同一原样短引用；服务端精确还原后完整校验。不得猜测或改写引用。",
        }
        context["evidence_catalog"]["rule"] = context["citation_contract"]["instruction"]
        context["instruction"] += " 本版本引用遵守 citation_contract：e.* / c.* 可直接用于工具和草稿，无需抄写完整工程 ID。"
        for report in context.get("dependency_reports", []):
            for claim in report["claims"]:
                claim["research_reference"] = next(
                    key for key, item in reference_map["claims"].items()
                    if item["report_id"] == report["report_id"] and item["claim_id"] == claim["claim_id"]
                )
    _submission_context(context, canonical_packet)
    return json.dumps(context, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _calculation_selection_context(context, packet):
    from product.runtime.calculation_handoff import VERSION, semantic_selection_draft_schema, model_calculation_catalog
    if packet["task"].get("calculation_selection_version") != VERSION:
        return
    submission = context.get("submission_contract")
    guide = semantic_selection_draft_schema(packet)
    if submission:
        submission["draft_format_guide"] = guide
    else:
        context.pop("output_schema", None)
        context["output_format_guide"] = guide
    context["calculation_selection_contract"] = {
        "version": VERSION,
        "prepared_results": model_calculation_catalog(Path(packet["reference_map"]["binding"]["run_dir"]), packet),
        "instruction": (
            "通过calculation_selections选择本任务已成功计算的calculation_ref和本地claim_ids；"
            "动态结果的短引用从calculate工具返回，冻结预计算从prepared_results选择。"
            "在所关联claim的statement/core_statement解释用途、期间和局限；程序不补写解释。"
            "省略calculations、artifact_refs及claim.calculation_refs；数值、方法、单位、"
            "有序输入和产物位置由真实收据/冻结产物装配。没有使用计算时提交空选择数组。"
            "文档也只用document_selections选择目录d.*，省略documents；原始文档身份、来源和时间由冻结目录装配。"
            "不得抄结果来替代选择，不能选择失败/未执行/其它任务结果。"
            "这一选择契约取代旧稿的计算字段填写要求，不改变研究内容和完整验证要求。"
        ),
    }
    from product.runtime.calculation_handoff import prepared_reference_enabled, PREPARED_REFERENCE_VERSION
    if prepared_reference_enabled(packet):
        context["calculation_selection_contract"]["prepared_result_reference_version"] = PREPARED_REFERENCE_VERSION
        context["calculation_selection_contract"]["instruction"] += (
            " 本任务冻结预计算使用p.<原method>.<窗口>可读引用，例如目录中的指标/窗口键；"
            "逐字选择prepared_results中实际存在的calculation_ref，不拼接scope或hash。"
            "每个引用精确对应同条method/value/unit/window；成交量比率不是年化波动率。"
            "未知或错选仍拒绝/内容不通过，程序不会按你的正文自动换选。"
        )
    if (packet["task"].get("tool_identity_version") == "research-tool-identity/1.0.0"
            and packet["task"].get("capability") in {"TECHNICAL_STRUCTURE", "MARKET_STATE"}):
        # 同一结果和ref只展示一份；原packet/产物及完整血缘不改写。
        results = context["calculation_selection_contract"]["prepared_results"]
        results.sort(key=lambda item: (
            item["method"].partition(":")[0], item.get("window_sessions", 0), item["calculation_ref"],
        ))
        analysis = context.get("prepared_analysis", {})
        calculation = analysis.get("calculation")
        if isinstance(calculation, dict) and isinstance(calculation.get("windows"), list):
            calculation["windows"] = [
                {key: value for key, value in window.items() if key != "metrics"}
                for window in calculation["windows"]
            ]
            calculation["metrics_view"] = "calculation_selection_contract.prepared_results"
        context["calculation_selection_contract"]["instruction"] += (
            " 窗口指标数值只在prepared_results中与其calculation_ref成对展示；"
            "按同条method/window_sessions/value/unit选择并解释，不能用同附件另一个未选指标背书。"
            "prepared_analysis保留窗口覆盖、图表、血缘及限制，不再重复窗口metrics。"
        )
        if packet["task"]["capability"] == "TECHNICAL_STRUCTURE":
            context["calculation_selection_contract"]["instruction"] += (
                " 交稿前按每条主张实际采用的指标/窗口列出对应选择，分别核对"
                "security_total_return（证券自身）、benchmark_total_return（基准）和"
                "relative_return（相对），三者是不同结果；每个所述窗口的每个所述值"
                "都需在该claim关联相应calculation_ref。不要用相对值和基准值自行相加"
                "代替选择已有证券自身结果，也不要用同附件的其它结果为遗漏项背书。"
                "不要求机械引用未讨论指标；核心窗口仍按minimum_questions完成。"
            )
        else:
            context["calculation_selection_contract"]["instruction"] += (
                " 交稿前逐主张核对所有实际采用指标的method/window_sessions与选择，"
                "收益、年化波动率和回撤的不同窗口各是独立结果；"
                "正文采用某窗口数值必须在该claim关联该窗口该指标的calculation_ref，"
                "不能只选20日结果为60/252日数值背书，不要求引用未讨论指标。"
            )


def _submission_context(context, packet):
    from product.runtime.research_submission import READ_VERSIONS, ASSEMBLY_VERSIONS, WRITE_VERSIONS, FORMAL_VERSIONS, SHORT_RECEIPT_VERSIONS, BOUNDED_REVISION_VERSION, require_write_protocol
    context["output_submission_guidance"] = {
        "version": "task-output-submission/1.0.0",
        "instruction": (
            "工具列表可见不等于本任务获授权。只有显式 submission_contract 的任务可调用 research_report_submit；"
            "没有该协议时按原 instruction 和输出格式返回最终完整 JSON，不调用该提交工具，也不返回数字回执。"
            "提交工具失败属于执行诊断，不据此选择 evaluation_status、降低研究充分性或增加资料缺口；"
            "研究状态依据实际资料和分析覆盖决定，真实取证失败及其影响仍须保留。"
        ),
    }
    if packet["task"].get("capability") == "TECHNICAL_STRUCTURE":
        context["technical_summary_guidance"] = copy.deepcopy(TECHNICAL_SUMMARY_GUIDANCE)
    if packet["task"].get("submission_version") not in READ_VERSIONS:
        _calculation_selection_context(context, packet)
        _task_tool_identity_context(context, packet)
        return
    if packet["task"]["submission_version"] in WRITE_VERSIONS:
        require_write_protocol(packet["task"])
    from product.runtime.calculation_handoff import VERSION as SELECTION_VERSION, semantic_selection_draft_schema
    selections_enabled = packet["task"].get("calculation_selection_version") == SELECTION_VERSION
    guide = (semantic_selection_draft_schema(packet) if selections_enabled
             else _model_output_format_guide(packet["output_schema"]))
    for key in ("run_id", "invocation_id", "agent"):
        guide.get("properties", {}).pop(key, None)
    guide["required"] = [k for k in guide.get("required", []) if k not in {"run_id", "invocation_id", "agent"}]
    guide.pop("$id", None)
    if packet["task"]["submission_version"] in ASSEMBLY_VERSIONS and not selections_enabled:
        guide["required"] = [key for key in guide["required"] if key != "documents"]
        guide["properties"].pop("documents", None)
        guide["properties"]["document_selections"] = {
            "type": "array", "uniqueItems": True,
            "items": {"type": "string", "enum": (
                list(packet["reference_map"]["documents"])
                if packet.get("reference_map", {}).get("binding", {}).get("version") == REFERENCE_VERSION else [
                    item["document_id"] for item in packet["task"].get("allowed_documents", [])
                ]
            )},
            "description": "Choose document IDs only; omit documents. Do not mix the two forms.",
        }
        guide["properties"]["upstream_calculation_selections"] = {
            "type": "array", "items": {"type": "object", "additionalProperties": False,
                "required": ["claim_id", "report_id", "source_claim_id", "calculation_id"],
                "properties": {key: {"type": "string"} for key in (
                    "claim_id", "report_id", "source_claim_id", "calculation_id"
                )}},
            "description": "Optional exact claim to verified upstream calculation choices; no local calculation is implied.",
        }
        if packet["task"]["submission_version"] in FORMAL_VERSIONS:
            claim_guide = guide["$defs"]["claim"]
            claim_guide["required"] = [
                "core_statement" if key == "statement" else key for key in claim_guide["required"]
            ] + ["research_relation_clauses"]
            claim_guide["properties"].pop("statement")
            claim_guide["properties"]["core_statement"] = {"type": "string", "minLength": 1}
            claim_guide["properties"]["research_relation_clauses"] = {
                "type": "array", "items": {"type": "object", "additionalProperties": False,
                    "required": ["research_claim_ref", "relation_statement"],
                    "properties": {
                        "research_claim_ref": {"type": "string"},
                        "relation_statement": {"type": "string", "minLength": 1},
                    }},
                "description": "Exactly one Agent-authored relationship sentence for each external research_claim_ref in this claim; empty for no external refs. Never use another claim's explanation.",
            }
    context.pop("output_schema", None)
    context.pop("output_format_guide", None)
    context["submission_contract"] = {
        "version": packet["task"]["submission_version"], "tool": "research_report_submit",
        "draft_format_guide": guide,
        "maximum_submissions": 2,
        "instruction": "本任务用工具提交draft研究对象，省略run_id/invocation_id/agent；invocation_id仅作为工具路由参数。程序负责序列化，Stop身份以真实派发/Start为准。工具返回不代表验收通过。最终原样返回工具给出的final_message完整回执，不自行拼写hash、不重复输出整份报告。纠正时重新调用工具提交完整对象，最多两份；不得删事实或猜引用。此提交协议替代旧的最终整稿JSON要求，研究字段及校验要求不变。",
    }
    if packet["task"]["submission_version"] in WRITE_VERSIONS:
        token = packet.get("submission_access", {}).get("token")
        if not isinstance(token, str) or len(token) < 32:
            raise MultidimensionalStageError("RESEARCH_SUBMISSION_CREDENTIAL_MISSING")
        context["submission_contract"]["submission_token"] = token
        context["submission_contract"]["instruction"] += (
            " 工具参数同时传本任务submission_token；凭据只供提交，不写入研究正文、报告或其他任务。"
            "不获取其他任务凭据。"
        )
        if not selections_enabled:
            context["submission_contract"]["instruction"] += (
                "新版草稿用document_selections选择允许文档ID并省略documents；历史完整documents草稿仍可原样提交，"
                "不得同时使用两种形式。需要复用上游计算时，用upstream_calculation_selections明确本地claim_id、"
                "上游report_id/source_claim_id/calculation_id，四者必须属于同一已核验依赖。"
                "无合格结果可保留来源原单位；程序展示所选计算原结果，正文不必重复抄金额。"
            )
        if packet["task"]["submission_version"] in FORMAL_VERSIONS:
            context["submission_contract"]["instruction"] += (
                " 每条claim改写core_statement与research_relation_clauses，不得同时写statement。"
                "每个外部上游research_claim_ref须在同一claim配一条由你撰写的具体关系句；"
                "没有实际关系就删去该上游引用，不借下一条claim解释，也不为凑覆盖虚构关系。"
                "程序只核引用一一对应并拼装原句，不判断语义相关性；最终仍经原完整门禁。"
            )
        if packet["task"]["submission_version"] in SHORT_RECEIPT_VERSIONS:
            context["submission_contract"]["instruction"] += (
                " 当前版本的final_message是服务端签发的短提交引用；最终只原样返回该引用，"
                "不返回JSON回执、序号或完整content_hash。Stop将凭可信Start和精确引用重验存稿。"
            )
        if packet["task"]["submission_version"] == BOUNDED_REVISION_VERSION:
            from product.runtime.local_revision import REVISION_FORMAT_GUIDE
            context["submission_contract"]["revision_format_guide"] = copy.deepcopy(REVISION_FORMAT_GUIDE)
            context["submission_contract"]["instruction"] = (
                "首稿提交draft研究对象，省略技术身份。程序校验及序列化；有任务凭据不等于会话身份认证，"
                "最终仍须真实派发/Start/Stop。最多首稿加一次修订，已授权的无效研究对象也占额度。"
                "修订必须在工具draft中提交反馈给出的base_draft_ref和changes，仅修改allowed_paths；"
                "不能重发整稿或修改其它主张。没有修订约束时不得再次提交；最终只返回工具的final_message。"
                "调用时传本任务invocation_id和submission_token，凭据不得写入研究。"
                "每条claim使用core_statement及research_relation_clauses：每个实际外部上游引用配一条"
                "你撰写的具体关系句，不借其它claim解释、不虚构关系；没有外部引用也必须填写空列表。"
                "修订changes每项必须有op，结构见revision_format_guide。其余研究字段见draft_format_guide。"
                "文档与计算只按选择契约选真实允许对象；第二稿仍经过完整校验，失败不增加次数。"
            )
    else:
        # 展示冻结草稿结构仅用于解释历史包；不交付可执行工具或访问凭据。
        context["submission_contract"].update({
            "tool": None, "read_only": True, "status": "LEGACY_READ_ONLY",
            "instruction": "此协议已退役，仅可读取及重验历史产物；不得新提交或继续启动旧任务。需真实执行时单独准备当前协议的新运行包，不改写旧包。",
        })
        context["submission_contract"].pop("maximum_submissions", None)
    context["instruction"] += " 本任务提交方式与研究字段格式以 submission_contract 为准；格式说明不是新的权威Schema，身份装配后仍用原冻结Schema校验。"
    _calculation_selection_context(context, packet)
    _task_tool_identity_context(context, packet)


def _task_tool_identity_context(context, packet):
    from product.runtime.fixture_mcp import TASK_TOOL_IDENTITY_VERSION
    if packet["task"].get("tool_identity_version") != TASK_TOOL_IDENTITY_VERSION:
        return
    context["tool_identity_contract"] = {
        "version": TASK_TOOL_IDENTITY_VERSION,
        "task_name": packet["task"]["task_name"],
        "tools": ["query", "calculate", "research_report_submit"],
        "instruction": (
            "query/calculate以及获授权的research_report_submit只以本任务精确task_name路由；"
            "不要传run_id/agent/invocation_id/run_dir。这替代旧tool_context中的身份参数要求，"
            "不改变权限或引用选择。成功读取不因后续请求失败而失效，不把调用错误写成已读来源缺失。"
        ),
    }
    if context.get("submission_contract"):
        context["submission_contract"]["instruction"] += " 本profile工具路由只传tool_identity_contract.task_name，不传invocation_id。"
    # Change only the model-view copies, never frozen upstream reports or output refs.
    mapping = packet.get("reference_map", {}).get("claims", {})
    for report in context.get("dependency_reports", []):
        claims = []
        for original in report["claims"]:
            claim = copy.deepcopy(original)
            refs = [key for key, target in mapping.items()
                    if target["report_id"] == report["report_id"] and target["claim_id"] == claim["claim_id"]]
            if len(refs) != 1 or not re.fullmatch(r"c\.[^.]+\.\d+", refs[0]):
                raise MultidimensionalStageError("MULTIDIMENSIONAL_CLAIM_DISPLAY_BINDING_INVALID")
            if claim.get("research_reference") not in {None, refs[0]}:
                raise MultidimensionalStageError("MULTIDIMENSIONAL_CLAIM_DISPLAY_BINDING_INVALID")
            claim["research_reference"] = refs[0]
            claims.append(claim)
        report["claims"] = sorted(claims, key=lambda c: int(c["research_reference"].rsplit(".", 1)[1]))
    if context.get("dependency_reports"):
        context["upstream_reference_rule"] = (
            "每条主张旁的research_reference才是该条引用身份，数组位置不是身份。"
            "逐条阅读原claim_id/原句及限定，选择该条实际ref并解释关系，不按顺序猜ref。"
        )


def serialize_multidimensional_initial_context(packet: Mapping[str, Any]) -> str:
    """首次定点交付沿既有视图；Company 使用有界目录，其它维度保留完整视图。"""

    if packet.get("task", {}).get("capability") not in {
        "FUNDAMENTAL_EVENT", "RESEARCH_REPORT",
    }:
        if packet.get("task", {}).get("capability") in RESEARCH_CAPABILITIES:
            return serialize_multidimensional_model_context(packet)
        raise MultidimensionalStageError("MULTIDIMENSIONAL_INITIAL_CONTEXT_SCOPE_INVALID")
    retained = (
        "dispatch_contract", "identity", "instruction", "minimum_questions",
        "tool_context", "citation_contract", "output_schema", "output_schema_hash",
        "company_material_coverage", "verified_documents", "material_preparation",
        "research_input_topology", "dependency_reports", "allowed_research_claim_ids",
    )
    context = {key: copy.deepcopy(packet[key]) for key in retained if key in packet}
    context["packet_hash"] = canonical_hash(packet)
    context["task"] = {
        key: packet["task"][key]
        for key in ("task_id", "task_name", "capability", "security_ids", "depends_on", "source_focus")
        if key in packet["task"]
    }
    context["output_contract_rules"] = copy.deepcopy(OUTPUT_CONTRACT_RULES)
    if packet["task"].get("capability") == "RESEARCH_REPORT":
        context["research_attribution_guidance"] = copy.deepcopy(RESEARCH_ATTRIBUTION_GUIDANCE)
    context["task"]["allowed_documents"] = copy.deepcopy(packet["task"].get("allowed_documents", []))
    by_field: dict[str, list[dict[str, Any]]] = {}
    for item in packet["evidence_catalog"]:
        field = str(item.get("semantic_field") or "UNKNOWN")
        by_field.setdefault(field, []).append({
            key: item[key] for key in ("evidence_id", "as_of", "unit")
            if item.get(key) is not None
        })
    context["evidence_catalog"] = [
        {"semantic_field": field, "items": by_field[field]}
        for field in sorted(by_field)
    ]
    context["provider_coverage"] = {
        "coverage_hash": packet["provider_coverage"].get("coverage_hash"),
        "provider_names": sorted({
            str(item["provider"])
            for item in packet["provider_coverage"].get("providers", [])
            if isinstance(item, Mapping) and item.get("provider")
        }),
    }
    context["catalog_rule"] = (
        "evidence_catalog 按 semantic_field 分组，包含完整允许 ID；引用前必须用 fixture_runtime.query "
        "读取完整事实及期间、来源和限制，逐字复制工具返回的 evidence_id。"
    )
    if packet.get("reference_map") is not None:
        from product.runtime.multidimensional_references import translate_references
        context = translate_references(context, packet["reference_map"], to_model=True)
        context["reference_map_hash"] = packet["reference_map"]["map_hash"]
        context["output_format_guide"] = _model_output_format_guide(context.pop("output_schema"))
        context["catalog_rule"] = "目录、工具及草稿使用同一任务 e.* Evidence / c.* 限定版本上游主张 / d.* 文档引用（仅使用实际目录允许类型）；精确还原后仍执行完整 Schema 校验，不能猜测。"
        context["citation_contract"] = {"version": packet["reference_map"]["binding"]["version"], "instruction": context["catalog_rule"]}
        context["instruction"] += " 引用及格式遵守本次 citation_contract 和 output_format_guide；无需抄写完整工程 ID，服务端仍执行冻结的完整 Schema 校验。"
        from product.runtime.multidimensional_references import model_claim_targets
        context["upstream_short_references"] = model_claim_targets(packet["reference_map"])
    _submission_context(context, packet)
    serialized = json.dumps(
        context, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    if len(serialized.encode("utf-8")) > 256 * 1024:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_INITIAL_CONTEXT_TOO_LARGE")
    return serialized


def build_multidimensional_dispatch_message(
    repository_root: Path, run_dir: Path, task_name: str,
) -> str:
    del repository_root
    manifest = _read_object(Path(run_dir) / "run_manifest.json")
    if (manifest.get("stage") == "MULTI_DIMENSIONAL_HOLDING_RESEARCH"
            and manifest.get("tool_identity_version") == "research-tool-identity/1.0.0"):
        return (
            f"执行多维持仓研究任务 {task_name}。读取本次 SubagentStart Hook 提供的冻结研究包，"
            "在本次调用内完成研究并按其输出契约提交；不得以已收到或等待注入的确认句作为最终输出。"
            "以 Hook 上下文为唯一研究输入，不在启动消息中复制资料；"
            "若 Hook 明确交付失败，遵循失败指令，禁止猜测输入或绑定。"
        )
    return (
        f"多维持仓研究任务 {task_name}。等待 SubagentStart Hook 注入冻结研究包；"
        "以 Hook 上下文为唯一研究输入，不在启动消息中复制资料。"
    )


def _load_research_capture_batches(
    *, gate_path: Path, gate: Mapping[str, Any], security_ids: Sequence[str],
    base_gate_path: Path | None = None,
    allow_source_run_rebinding: bool = False,
) -> list[dict[str, Any]]:
    """读取原采集批次，并在同行合并后重新核对最终 Gate 的 Evidence 准入。"""

    preparation_path = gate_path.parent / "data-preparation.json"
    preparation_gate = gate
    final_single_stock_package = False
    bundle_path = gate_path.parent / "source-bundle.json"
    if bundle_path.is_file() and _read_object(bundle_path).get("schema_version") == "common-stock-source-bundle/3.0.0":
        from product.runtime.common_stock_data import validate_common_stock_source_bundle
        source_input = _read_object(gate_path.parent / "single-stock-request.json")
        validate_common_stock_source_bundle(source_input, gate=gate, preparation=_read_object(preparation_path),
                                            source_bundle_path=bundle_path)
        expected_base = gate_path.parent / "base-source/gate.json"
        if base_gate_path is not None and Path(base_gate_path).resolve() != expected_base.resolve():
            raise MultidimensionalStageError("MULTIDIMENSIONAL_BASE_GATE_BINDING_INVALID")
        base_gate_path = expected_base
        final_single_stock_package = True
    if gate.get("source_mode") == "live-read-only" and gate.get("base_gate_content_hash") is not None:
        if base_gate_path is None:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_BASE_GATE_REQUIRED")
        base_gate_path = Path(base_gate_path).resolve()
        base_gate = _read_object(base_gate_path)
        if (
            base_gate.get("bundle_hash") != legacy_envelope_hash(base_gate, hash_field="bundle_hash")
            or gate["base_gate_content_hash"] != canonical_hash({
                key: value for key, value in base_gate.items()
                if key not in {"run_id", "bundle_hash"}
            })
            or (not allow_source_run_rebinding and base_gate.get("run_id") != gate.get("run_id"))
            or base_gate.get("source_mode") != gate.get("source_mode")
            or (not final_single_stock_package and base_gate.get("source_bundle_hash") != gate.get("source_bundle_hash"))
            or parse_timestamp(base_gate["decision_cutoff"])
            > parse_timestamp(gate["decision_cutoff"])
        ):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_BASE_GATE_BINDING_INVALID")
        preparation_gate = base_gate
        preparation_path = base_gate_path.parent / "data-preparation.json"
    elif base_gate_path is not None:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_BASE_GATE_UNEXPECTED")
    if not preparation_path.is_file():
        if gate.get("source_mode") == "live-read-only":
            raise MultidimensionalStageError("MULTIDIMENSIONAL_DATA_PREPARATION_MISSING")
        return []
    preparation = _read_object(preparation_path)
    if preparation.get("common_cutoff") != preparation_gate.get("decision_cutoff"):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_PROVIDER_PREPARATION_CUTOFF_MISMATCH")
    if gate.get("source_mode") == "live-read-only":
        if preparation.get("preparation_hash") != legacy_envelope_hash(preparation, hash_field="preparation_hash"):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_DATA_PREPARATION_HASH_MISMATCH")
        items = preparation.get("items")
        expected_ids = set(security_ids)
        if (
            not isinstance(items, list)
            or {item.get("security_id") for item in items if isinstance(item, Mapping)}
            != expected_ids
            or len(items) != len(expected_ids)
            or any(not isinstance(item, Mapping) or item.get("status") != "READY" for item in items)
        ):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_DATA_PREPARATION_NOT_READY")
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


def _research_execution_fingerprint(repository_root: Path) -> dict[str, str]:
    """当前研究共用实现的只读指纹；不是产品版本锁或晋升指针。"""
    names = (
        "multidimensional_stage", "codex_hook_recorder", "fixture_mcp",
        "research_submission", "multidimensional_references", "calculation_handoff",
        "research_input_topology", "schema_validation", "local_revision", "nested_codex",
    )
    return {f"product/runtime/{name}.py": file_hash(repository_root / "product/runtime" / f"{name}.py")
            for name in names}


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
    expected_hash = legacy_envelope_hash(coverage, hash_field="coverage_hash")
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
    repository_root: Path, *, handoff_path: Path | None = None, research_input_path: Path | None = None, gate_path: Path, run_dir: Path,
    run_id: str, model: str, research_question: str = "补全普通股持仓的免费多维研究资料。",
    benchmark_id: str = "US:SPY", target_concurrency: int = 3,
    peer_candidate_pool_path: Path | None = None,
    company_research_run_path: Path | None = None,
    research_materials_run_path: Path | None = None,
    base_gate_path: Path | None = None,
    stage: str = "MULTI_DIMENSIONAL_HOLDING_RESEARCH",
    structured_report_submission: bool = False,
    task_bound_tools: bool = False,
    reuse_frozen_gate: bool = False,
    core_forward_only: bool = False,
) -> dict[str, Any]:
    repository_root = Path(repository_root).resolve()
    product_root = repository_root / "product"
    if task_bound_tools and stage != "MULTI_DIMENSIONAL_HOLDING_RESEARCH":
        raise MultidimensionalStageError("TASK_TOOL_IDENTITY_STAGE_INVALID")
    if core_forward_only and stage != "INDEPENDENT_COUNTER_THESIS_RESEARCH":
        raise MultidimensionalStageError("COUNTER_CORE_SCOPE_STAGE_INVALID")
    validate_current_component_versions(product_root, load_version_manifest(product_root / "version-manifest.json"))
    run_dir = Path(run_dir).resolve()
    if run_dir.exists():
        raise MultidimensionalStageError("MULTIDIMENSIONAL_RUN_EXISTS")
    if type(target_concurrency) is not int or target_concurrency < 1:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_CONCURRENCY_INVALID")
    from product.runtime.model_routing import select_product_runtime_model
    selected_model = select_product_runtime_model(product_root, requested_model=model)
    resolved_gate_path = Path(gate_path).resolve()
    if (handoff_path is None) == (research_input_path is None):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_INPUT_PATH_INVALID")
    handoff = _read_object(Path(research_input_path or handoff_path).resolve())
    validate_research_input(handoff)
    if research_input_path is not None and not is_single_stock(handoff):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_SINGLE_STOCK_REQUIRED")
    if is_single_stock(handoff):
        research_question = handoff["research_question"]
    gate = _read_object(resolved_gate_path)
    source_gate = copy.deepcopy(gate)
    gate_input_binding = None
    if reuse_frozen_gate:
        if stage != "MULTI_DIMENSIONAL_HOLDING_RESEARCH":
            raise MultidimensionalStageError("MULTIDIMENSIONAL_GATE_REUSE_STAGE_FORBIDDEN")
        from product.runtime.evidence_gate import bind_frozen_gate_to_run
        gate, gate_input_binding = bind_frozen_gate_to_run(resolved_gate_path, run_id=run_id)
    elif gate.get("run_id") not in {None, run_id}:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_GATE_RUN_MISMATCH")
    gate["run_id"] = run_id
    gate["source_mode"] = gate.get("source_mode", "fixture")
    gate["bundle_hash"] = legacy_envelope_hash(gate, hash_field="bundle_hash")
    cutoff = gate.get("decision_cutoff")
    if not isinstance(cutoff, str):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_CUTOFF_MISSING")
    cutoff_time = parse_timestamp(cutoff)
    if is_single_stock(handoff) and cutoff != handoff["resolved_cutoff"]:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_INPUT_CUTOFF_MISMATCH")
    evidence = gate.get("allowed_evidence")
    if not isinstance(evidence, list) or {item.get("evidence_id") for item in evidence} != set(gate.get("allowed_evidence_ids", [])):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_GATE_INVALID")
    for fact in evidence:
        for key in ("source_id", "as_of", "retrieved_at"):
            if not isinstance(fact.get(key), str) or not fact[key]:
                raise MultidimensionalStageError(f"MULTIDIMENSIONAL_PROVENANCE_MISSING:{key}")
        if parse_timestamp(fact["as_of"]) > cutoff_time or parse_timestamp(fact["retrieved_at"]) > cutoff_time:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_GATE_PIT_LEAKAGE")
    # Live collection identifies SPY as an ETF, while older frozen fixtures
    # use US:SPY. Resolve only the known benchmark alias from actual gated
    # daily prices; do not invent a benchmark or broaden Evidence access.
    if benchmark_id == "US:SPY" and not any(
        item.get("security_id") == benchmark_id
        and item.get("semantic_field") == "historical_close_price"
        for item in evidence
    ) and any(
        item.get("security_id") == "US:ETF:SPY"
        and item.get("semantic_field") == "historical_close_price"
        for item in evidence
    ):
        benchmark_id = "US:ETF:SPY"
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
                    or (source_gate.get("decision_cutoff") != cutoff
                        and not (role == "MATERIALS" and is_single_stock(handoff)))):
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
        item["security_id"] for item in research_subjects(handoff)
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
        **research_input_binding(handoff), "council_request_id": request["request_id"],
        "council_request_hash": request["request_hash"], "decision_cutoff": cutoff,
    }
    from product.runtime.research_input_topology import (
        load_research_input_topology,
        research_input_topology_lock,
    )
    topology = load_research_input_topology(repository_root)
    topology_lock = research_input_topology_lock(repository_root)
    from product.runtime.research_input_topology import build_research_provider_coverage
    capture_gate_path = resolved_gate_path
    capture_gate = source_gate if reuse_frozen_gate else gate
    if core_forward_only and company_research_run_path is not None:
        # 新执行视图与原采集包是两种身份。只在完整重验公司包及
        # 两份 Gate 的精确绑定后，从原包解析相对采集路径；不重签历史数据。
        from product.runtime.evidence_gate import validate_frozen_gate_binding
        from product.runtime.common_stock_data import validate_common_stock_source_bundle
        company_run = Path(company_research_run_path).resolve()
        company_manifest = _read_object(company_run / "run_manifest.json")
        company_gate = _read_object(company_run / "evidence/gate.json")
        validate_frozen_gate_binding(company_run, company_manifest, company_gate)
        if company_gate != gate:
            raise MultidimensionalStageError("COUNTER_COMPANY_GATE_MISMATCH")
        if company_manifest.get("gate_input_binding") is not None:
            binding = company_manifest["gate_input_binding"]
            frozen_source = _read_frozen_object(company_run, binding["source_ref"])
            if company_manifest.get("source_bundle_ref") is not None:
                source_bundle = _resolve_frozen_artifact(company_run, company_manifest["source_bundle_ref"])
                package_ref = source_bundle.parent.relative_to(company_run)
                capture_gate_path = _resolve_frozen_artifact(company_run, str(package_ref / "gate.json"))
                _resolve_frozen_artifact(company_run, str(package_ref / "data-preparation.json"))
                capture_gate = _read_object(capture_gate_path)
                if capture_gate != frozen_source:
                    raise MultidimensionalStageError("COUNTER_COMPANY_SOURCE_GATE_MISMATCH")
                validate_common_stock_source_bundle(
                    handoff, gate=frozen_source,
                    preparation=_read_frozen_object(company_run, "evidence/data-preparation.json"),
                    source_bundle_path=source_bundle,
                )
    capture_batches = _load_research_capture_batches(
        gate_path=capture_gate_path, gate=capture_gate, security_ids=common_ids,
        base_gate_path=base_gate_path,
        allow_source_run_rebinding=reuse_frozen_gate,
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
    provider_coverage["coverage_hash"] = legacy_envelope_hash(provider_coverage, hash_field="coverage_hash")
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
    if gate_input_binding is not None:
        source_copy = run_dir / gate_input_binding["source_ref"]
        source_copy.parent.mkdir(parents=True, exist_ok=True)
        source_copy.write_bytes(resolved_gate_path.read_bytes())
    _write_object(run_dir / research_input_ref(handoff), handoff)
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
            # 同行 final-view 绑定冻结资料身份；新执行身份另由
            # gate_input_binding 校验，不能要求历史视图重签新 run hash。
            expected_handoff=handoff, target_gate=source_gate if reuse_frozen_gate else gate,
            expected_security_ids=common_ids,
        )
    tasks: list[dict[str, Any]] = []
    ordinal = 0
    capabilities = RESEARCH_CAPABILITIES
    if core_forward_only:
        from product.runtime.independent_skeptic_stage import CORE_CAPABILITIES
        capabilities = tuple(item for item in capabilities if item in CORE_CAPABILITIES)
    for capability in capabilities:
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
            breadth_focus = _latest_market_breadth(evidence, cutoff) if capability == "MARKET_STATE" else None
            if breadth_focus is not None and breadth_focus["evidence_id"] not in {f["evidence_id"] for f in facts}:
                facts = sorted([*facts, breadth_focus], key=lambda f: f["evidence_id"])
            allowed_ids = [item["evidence_id"] for item in facts]
            if capability == "OWNERSHIP_DISCLOSURE":
                completed_by_source: dict[str, list[dict[str, Any]]] = {}
                for fact in facts:
                    value = fact.get("value")
                    if (
                        str(fact.get("semantic_field", "")).startswith("moomoo_institutional_aggregate:")
                        and isinstance(value, dict) and value.get("period_provisional") is False
                        and isinstance(value.get("period_end"), str)
                        and isinstance(value.get("period_label"), str)
                    ):
                        completed_by_source.setdefault(str(fact.get("source_id", "")), []).append(fact)
                pairs = []
                for items in completed_by_source.values():
                    by_period = {
                        item["value"]["period_end"]: item
                        for item in sorted(items, key=lambda item: item["evidence_id"])
                    }
                    if len(by_period) >= 2:
                        pairs.append([by_period[key] for key in sorted(by_period)[-2:]])
                if pairs:
                    selected_pair = max(pairs, key=lambda pair: pair[-1]["value"]["period_end"])
                    task_focus = [
                        {"evidence_id": item["evidence_id"],
                         "period_label": item["value"]["period_label"],
                         "period_end": item["value"]["period_end"]}
                        for item in selected_pair
                    ]
                else:
                    task_focus = []
                if security_id:
                    task_focus.extend(_latest_insider_trade_focus(
                        facts, security_id=security_id, cutoff=cutoff,
                    ))
            elif capability == "MARKET_STATE":
                task_focus = [
                    {"evidence_id": item["evidence_id"], "semantic_field": item["semantic_field"]}
                    for item in ([breadth_focus] if breadth_focus is not None else [])
                ]
            elif capability == "INDUSTRY_COMPARISON":
                task_focus = [
                    {"evidence_id": fact["evidence_id"], "security_id": fact.get("security_id"),
                     "source_id": fact.get("source_id"), "as_of": fact.get("as_of"),
                     "retrieved_at": fact.get("retrieved_at"),
                     "form": fact.get("metadata", {}).get("form") if isinstance(fact.get("metadata"), dict) else None,
                     "accession": fact.get("metadata", {}).get("accession") if isinstance(fact.get("metadata"), dict) else None,
                     **_text_locator(fact)}
                    for fact in facts if _text_locator(fact)["section_locator"] == "business"
                ]
            elif capability == "FUNDAMENTAL_EVENT" and security_id:
                task_focus = [
                    *_latest_annual_eps_focus(facts, security_id=security_id),
                    *_sec_revenue_table_unit_focus(facts, security_id=security_id),
                    *_same_period_profit_cash_focus(facts, security_id=security_id),
                ]
            else:
                task_focus = []
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
                "source_focus": task_focus,
            }
            if stage == "MULTI_DIMENSIONAL_HOLDING_RESEARCH" and capability == "INDUSTRY_COMPARISON":
                task["industry_source_boundary"] = "industry-source-boundary/1.0.0"
            if task_bound_tools:
                from product.runtime.fixture_mcp import TASK_TOOL_IDENTITY_VERSION
                task["tool_identity_version"] = TASK_TOOL_IDENTITY_VERSION
            if stage == "MULTI_DIMENSIONAL_HOLDING_RESEARCH" and capability in {
                "MACRO_CONTEXT", "MARKET_STATE",
            }:
                task["provider_coverage_view_kind"] = "TASK_SCOPED_PROVIDER_COVERAGE"
            if stage == "MULTI_DIMENSIONAL_HOLDING_RESEARCH" and capability in {
                "FUNDAMENTAL_EVENT", "OPTIONS_FLOW",
            }:
                task["source_literal_selection"] = "source-literal-selection/1.0.0"
            if (stage == "MULTI_DIMENSIONAL_HOLDING_RESEARCH"
                    and capability == "MACRO_CONTEXT" and task_bound_tools):
                task["source_literal_selection"] = "source-literal-selection/1.1.0"
            if structured_report_submission and stage == "MULTI_DIMENSIONAL_HOLDING_RESEARCH" and capability == "RESEARCH_REPORT":
                from product.runtime.research_submission import LATEST_VERSION
                task["submission_version"] = LATEST_VERSION
                task["source_evidence_review"] = "queried-source-excerpt-review/1.0.0"
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
            if capability in {"FUNDAMENTAL_EVENT", "OWNERSHIP_DISCLOSURE"}:
                ledger_ref = (
                    "research/calculations/"
                    + hashlib.sha256(invocation_id.encode("utf-8")).hexdigest()[:16]
                    + "/tool-results.jsonl"
                )
                ledger_path = run_dir / ledger_ref
                ledger_path.parent.mkdir(parents=True, exist_ok=False)
                ledger_path.touch(exist_ok=False)
                task["calculation_ledger_ref"] = ledger_ref
                prepared_analysis["allowed_artifact_refs"].append(ledger_ref)
            task["allowed_artifact_refs"] = prepared_analysis["allowed_artifact_refs"]
            if stage in {"MULTI_DIMENSIONAL_HOLDING_RESEARCH", "INDEPENDENT_COUNTER_THESIS_RESEARCH"}:
                from product.runtime.calculation_handoff import VERSION as CALCULATION_SELECTION_VERSION
                task["calculation_selection_version"] = CALCULATION_SELECTION_VERSION
                if (task_bound_tools and stage == "MULTI_DIMENSIONAL_HOLDING_RESEARCH"
                        and capability in {"TECHNICAL_STRUCTURE", "MARKET_STATE"}):
                    from product.runtime.calculation_handoff import PREPARED_REFERENCE_VERSION
                    task["prepared_result_reference_version"] = PREPARED_REFERENCE_VERSION
                # Only computation lineage; not new query or claim-citation permission.
                task["allowed_calculation_evidence_ids"] = sorted({
                    identifier
                    for ref in prepared_analysis["allowed_artifact_refs"]
                    if ref.endswith("-calculation.json")
                    for identifier in _read_object(run_dir / ref)["evidence_fact_ids"]
                })
            task_path = f"research/tasks/{canonical_hash({'task_id': task_id})}.json"
            skill = skill_bindings[skill_name]
            minimum_questions = copy.deepcopy(MINIMUM_QUESTIONS[capability])
            if task.get("tool_identity_version") == "research-tool-identity/1.0.0":
                if (capability == "MACRO_CONTEXT"
                        and task.get("source_literal_selection") == "source-literal-selection/1.1.0"):
                    minimum_questions[0] = (
                        "利率、通胀、经济活动与政策的官方事实是什么？"
                        "从已准入的Moomoo宏观补源自行选择至少一条与研究问题相关的代表观测，"
                        "实际query并在同一claim引用，沿本任务原值行绑定呈现其数值角色、"
                        "原单位及观察期；与官方资料有何关系，怎样影响本次解释？"
                        "供应商快照及历史vintage限制另述；没有可用准入观测时保留具体gap。"
                    )
                elif (capability == "OPTIONS_FLOW"
                        and task.get("source_literal_selection") == "source-literal-selection/1.0.0"):
                    minimum_questions[1] += (
                        " 所选代表合约的contract_multiplier/contract_size有哪些可得原值，"
                        "对应来源单位及合约规模风险含义是什么？"
                        "实际query并引用同身份补源；Yahoo未给出不等于OpenD已取得字段缺失，"
                        "单位未知须说明而不能自行默认标准合约规模。"
                    )
                elif capability == "FUNDAMENTAL_EVENT":
                    minimum_questions[1] = (
                        "盈利与现金流是什么关系？分别读取并呈现已准入累计期间的净利润与经营现金流"
                        "原值、单位及起止日，解释同期间关系；如另用业绩稿单季数字，"
                        "与累计期间分开说明，不能相互代替。确实不可得或口径不明保留具体gap。"
                    )
                    minimum_questions[2] += (
                        " 若使用年度GAAP EPS作历史价格比值，已披露的一次性处置等项目"
                        "怎样影响这个盈利基础的可重复性？实际读取并引用依据；"
                        "不能只说明滞后或非前瞻，不自行重建调整后EPS。"
                    )
                    minimum_questions[3] += (
                        " 事件或业绩稿的报告财年/财季须按所引发行人原文核对，"
                        "与公布日、累计/单季起止日及管理层预测年度分别说明；"
                        "不能把公布日的日历年份当作报告财年，不自行推算财年标签。"
                    )
                elif capability == "RESEARCH_REPORT":
                    minimum_questions[0] += (
                        " 各来源的币种和金额数量级是什么？core_statement及每条"
                        "research_relation_clauses都保留各自来源原表示；"
                        "没有同源合法换算收据不得改写金额单位，不只核对主段落。"
                    )
            instruction = (
                "只分析本任务指定维度并回答 minimum_questions。只使用本次目录和工具允许的精确引用；"
                "禁止拼接来源、时间或说明。没有足够资料时输出具体 gap 及影响，不能使用模型记忆补齐。"
                " claims 中每条主张必须保留非空 question、statement 和 kind，并且 question 对应本任务"
                "实际回答的 minimum_questions；不得省略问题字段。"
                " 顶层只能包含本次草稿契约声明的字段；不得补写 schema_version、report_id、"
                "capability、scope、security_ids、bindings、time_context、execution 或 report_hash，"
                "这些冻结字段由确定性封装器添加。"
                " limitations 必须是纯字符串数组；observation_conditions 与 data_gaps 必须是"
                " 草稿契约定义的对象数组，不能把 limitation 写成对象或把 gap 写成字符串；"
                "每个 data_gaps 项都必须包含 gap_id、reason_code、description、impact。"
                " claims 不得增加草稿契约未定义的键；每个 assumptions 项须按"
                " 草稿契约同时填写 rationale 与 evidence_refs，不要只处理第一个校验错误。"
                "不得生成 action、目标仓位、推荐数量、对冲或订单。"
                " 引用财务事实前读取 metadata.period_start/period_end/context_type："
                "fiscal_period=Q2 是申报标签，不能把年初至期末累计现金流称为当季；"
                "单季损益、累计现金流与时点余额须分别说明期间，不混算。"
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
            if capability == "FUNDAMENTAL_EVENT":
                instruction += (
                    " 最近单季SEC收入已准入时须查询并呈现原值及真实期间，按已有source_literal_selections"
                    "绑定sec_usd_value到该收入主张，以证明精确原值交付；不能以季度增速或同行报告代替。"
                    "未准入或实际不可读时保留具体gap，不从其它期间或来源猜补。"
                    " 若目录交付 historical_close_price，先实际query核对价格、币种与as_of，"
                    "只称截止点内的历史收盘价，不称实时价；没有估值附件不等于没有价格。"
                    " source_focus 如列出SEC年度 diluted EPS，仅是本任务已准入的候选定位及事实原期间；"
                    "先query核对真实数值、起止日、会计口径及一次性项目，再自行决定能否与历史价格作受限比值。"
                    "单季EPS比值工具失败不等于同Gate没有年度EPS；应检查已准入目录，"
                    "并将参数或证据数值失败与来源缺失分开记录。"
                    "不得仅凭价格与不匹配期间财务值拼估值倍数；保留仍缺的口径与假设。"
                    " 本任务可用既有 calculate 的 monetary_scale、ratio、percent_change，"
                    "仅接受实际读取的合法 Evidence；本任务输出契约指定结果提交方式，"
                    "解释计算的用途和限制，不自行补算。"
                    "先核对期间、单位和可比性再计算。该工具不支持通用减法/FCF 表达式；"
                    "没有合格计算附件时，分别解释同期间盈利、经营现金流及资本支出原值，"
                    "任何来源金额都保留原数量级；SEC原单位为USD的整数金额也不能自行缩写为million/billion，"
                    "不得自行将million改为billion或换成亿/万，"
                    "若source_focus列出SEC收入分解表的table_unit，应query该Evidence，"
                    "逐行沿用表头(in millions/in billions)的原单位；表格单元格未逐项标单位，"
                    "现有monetary_scale不能把表头继承的数字当成已成功换算。"
                    "没有对应成功收据时，总额和各分项一律按原表头单位写，不因习惯改用更大单位；"
                    "已查询并可读的最近完整财年收入分解表须用于回答经营驱动：说明原单位的总额、"
                    "主要组成、原表比例与期间/分类口径；不得只引用该表却只解释较近季度增速。"
                    "若表格实际不可读或口径不可比，说明具体缺口，不从其他来源猜补。"
                    " source_focus若列出同期间净利润/经营现金流，只是已准入的候选定位；"
                    "先分别query核对原值、起止日、主体及会计基础，再解释关系。"
                    "同起止日不自动证明现金转化率或自由现金流，也不替代其他适用事实。"
                    "准确记录派生指标限制，不把工具不支持说成原始事实不存在。"
                    " 同一主张引用精确SEC结构化事实与业绩稿舍入值时，逐项核对原值、原单位、"
                    "真实起止日和精度；不得把业绩稿约数写成带结构化事实期间的精确整数USD，"
                    "也不得把两来源拼成单一精确事实。可分别保留两种来源表述并说明舍入差异。"
                    "交稿时复核每个来源金额：包括处置收益、公司指引与业绩稿，"
                    "正文保留来源原数量级；改用亿/万等单位时须选择对应真实monetary_scale结果，"
                    "没有收据就沿用原billion/million/USD，不自行口算。"
                )
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
                        " 至少核对一只同行的业务/产品或终端暴露依据及一组可比经营或行情事实，"
                        "解释与目标公司的共同传导及差异；仅列不同财年收入不能代替业务可比性。"
                        "按 minimum_questions 顺序完成有限比较；局部可比与不能排名或量化直接竞争可以并存。"
                        "不要求全部候选统一量化终端占比或市场份额，其他候选缺项不抹去已有比较；"
                        "不为填格式虚构业务关系。"
                        " 对经营事实，先在目标与同行各自的允许 Evidence 中查找同一指标、相近期间长度的原值，"
                        "列明各自期间和单位，再解释财年截止日、业务结构等剩余不可比性；"
                        "不得把不同公司的收入与毛利等不同指标并列后宣称已完成可比经营事实。"
                        "金额比较须逐项核对原值和原单位；没有真实换算收据时直接保留来源原单位，"
                        "不自行改写为亿/万/million/billion，即使数值等价也不能称为工具结果。"
                        "确实无可比事实时才记录具体缺口，不把未查询的已准入事实写成来源缺失。"
                        "目录的 content_kind/section_locator/text_length 用于区分目录标题与章节内容；"
                        "读到 HEADING_ONLY 时继续核查已交付的业务正文，不以标题代替业务依据。"
                        "SECTION_TEXT 不保证整份申报全文，UNKNOWN 不等于无数据，短文本也可能有实质内容。"
                        " 具体业务比较须从双方实际查询的正文核对终端应用：有证据支持共同终端时，"
                        "写出该交集及各自产品作用差异；无可核实交集或资料不足时说明依据与具体gap，"
                        "不得为满足格式虚构交集。"
                        + ("仅泛述行业共性，不算回答目标与同行的具体业务可比性。"
                           if is_single_stock(handoff) else
                           "仅写半导体供应商、电子系统需求等行业共性不算回答。")
                        +
                        "引用分类变更或收购发生时点时，逐项核对所引原文的财年和季度，"
                        "不得用当前财年标签替代历史变更的发生财年。"
                        "每次query至多读取一只已物化同行，可同时读取目标公司及基准；比较另一同行时另查，"
                        "先按证券核对每段原文的产品、终端和来源，再决定选哪只同行及交集。"
                        "source_focus给出可信文件身份，但主张正文不要手抄source_id=、as_of=或retrieved_at=；"
                        "由evidence_refs追溯技术身份，正文只解释有据的业务事实和限制。"
                    )
                else:
                    instruction += (
                        " 本任务没有完成身份核验与 PIT 冻结的 selected_peer_candidates，因此 claims 必须为空；"
                        "必须用 data_gaps 明确记录缺少可比较同行 Evidence 的原因和影响。不得仅凭目标公司资料、"
                        "候选目录或模型记忆形成任何行业比较主张。"
                    )
            if capability == "OWNERSHIP_DISCLOSURE":
                instruction += (
                    " source_focus 已列出本任务允许的两个最新已结束机构期间（若可得）；"
                    "应先按原样 ID 查询并回答机构变化问题。若 Gate 中有同一供应商的两个已结束机构期间，"
                    "按先后顺序调用 institutional_period_change 取得机构数、持股量和比例的"
                    "确定性变化，按交付的计算输出契约关联相关主张并解释用途。"
                    "未结束季度只作 provisional 观察。"
                    "供应商汇总变化不等于主动净买卖，也不等于完整 SEC 13F 覆盖。"
                    " source_focus 若列出内部人交易，还须按原样 ID 查询至少代表记录，"
                    "核对原交易类型、交易起止日期及供应商观察时间；min/max可能是聚合区间，"
                    "不得写成每一天都有交易。区分普通卖出与行权获得/行权卖出，"
                    "不要把行权一概解释成主动增减仓。若原始 Form 4 申报时点未核实，"
                    "不得据供应商观察时间推断法定披露滞后；无合格记录时写具体缺口。"
                )
            if capability == "MARKET_STATE":
                instruction += (
                    " source_focus 若列出已准入的涨跌分布，应查询该完整 Evidence ID，"
                    "解释实际数值与快照时点；只有标题、目录或一句‘有广度资料’不构成市场广度研究。"
                    " 对已准入的板块与波动代理，至少读取并解释各一项实际观测及其时点；"
                    "只说明 XLK/VIX 等代理是什么、却不引用可用观测，不满足本维度最低内容。"
                    "单日观察不等于趋势或资金流，跨时点比较须分别注明日期；"
                    "两日收盘本身只支持原始价格观察；没有实际成功的确定性计算收据时，"
                    "不得自行写出板块代理的两日涨跌百分比，保留原收盘和时点即可。"
                    "未取得实际观测时明确记录具体 gap，不推断资金方向。"
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
                    "licensed_sections": [
                        {"evidence_id": fact["evidence_id"],
                         "section": fact["value"]["section"],
                         "raw_content_hash": fact["raw_content_hash"],
                         "content_tier": "LICENSED_API_CONTENT"}
                        for fact in company_facts
                        if str(fact.get("semantic_field", "")).startswith("moomoo_morningstar_section:")
                        and isinstance(fact.get("value"), dict)
                        and fact["value"].get("content_tier") == "LICENSED_API_CONTENT"
                        and isinstance(fact["value"].get("content"), str)
                        and fact["value"]["content"].strip()
                        and fact["value"].get("section")
                        and fact.get("raw_content_hash")
                    ],
                    "issuer_body_count": len(issuer_documents_by_security.get(security_id, [])),
                    "independent_body_count": (
                        len(research_materials_import["documents_by_security"].get(security_id, []))
                        if research_materials_import is not None else 0
                    ),
                    "public_lead_evidence_ids": sorted(
                        fact["evidence_id"] for fact in company_facts
                        if fact.get("dataset") == "research_discovery"
                        and fact.get("source_family") == "moomoo_public_news"
                        and isinstance(fact.get("value"), dict)
                        and fact["value"].get("content_tier") == "LEAD_ONLY"
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
                        "LICENSED_API_CONTENT": "Gate-allowed vendor sections; not independently fetched full text",
                    },
                }
                instruction += (
                    " verified_documents 是经正文工具核验的文档集合；documents 仅逐字复制其中"
                    "report_document 元数据。许可章节在 company_material_coverage.licensed_sections，"
                    "经 query 读取并使用 Evidence 引用，不为章节虚构 documents。"
                    "不得把搜索线索、标题摘要或模型记忆冒充已读正文。"
                    "material_preparation 的配置阻断及真实尝试引用必须保留为对应来源的缺口。"
                    " 写有具体来源金额的事实主张只引用实际承载该金额的 Evidence；"
                    "若一句话需要综合多条来源，先把各来源金额及原币种、原数量级分别写成可核对的事实主张，"
                    "再用另一主张解释跨来源关系，不为综合判断给每个金额批量挂上无关引用。"
                    "没有本主张有效的换算收据时保留来源原币种和单位表示，"
                    "包括原文million/billion等原词，不将其自动汉化成万/亿等倍数单位。"
                    "中文许可原文已有的万/亿金额按其原表示引用，与发行人原单位分别保留；"
                    "翻译叙述不等于授权金额换算，不因拆分主张而自行换算。"
                )
                if task["company_material_coverage"]["licensed_sections"]:
                    instruction += (
                        " 已有 Gate 合格的 Morningstar 许可章节；即使独立正文来源为 BLOCKED_CONFIGURATION，"
                        "仍须查询与研究问题相关的正反章节，说明其支持、挑战或修订上游哪个具体主张。"
                        "区分供应商转述的管理层指引、作者自身预测、估值假设与发行人已核实事实；"
                        "未在发行人材料交叉核验的指引只能标为未核实转述，不能改称作者预测。"
                        "关联上游时先核对目标原句和限定：历史价格/受限P-E不是已验证公允价值模型，"
                        "新增供应商估值观点也不自动修订该核验缺口。不要把供应商分节称为已读独立全文。"
                        "整体按实际覆盖给出有限研究（可为 LOW_CONFIDENCE/PARTIAL），"
                        "不因单一路径阻断强制 FAILED，也不因存在章节自动 COMPLETE；"
                        "未知或未读取内容保留具体 gap。"
                    )
                else:
                    instruction += (
                        " 没有许可章节时，若 material_preparation.status 为 BLOCKED_CONFIGURATION"
                        "且 verified_documents 为空，正式报告必须输出 FAILED / evaluation_status=FAIL，"
                        "保留配置缺口，不能改写成 SOURCE_LIMITED；其他正文不足情形保留实际 SOURCE_LIMITED。"
                    )
                if (task["company_material_coverage"]["public_lead_evidence_ids"]
                        and (task.get("material_preparation") or {}).get("status")
                        not in {"BLOCKED_CONFIGURATION", "FAILED"}):
                    instruction += (
                        " company_material_coverage.public_lead_evidence_ids 是本任务已准入的公开标题/链接线索，"
                        "与 OpenD 评级快照和已核验正文不同。至少用本任务只读 query 查询其中一条；"
                        "在本任务关于作者依据与假设等问题下判断相关性。采用时，以 claims[].evidence_refs"
                        " 中的原样 ID 说明具体核验用途、标题/链接层级及不能支持的结论，"
                        "不能只写‘存在标题’。不相关、重复或无新增价值时，在现有 data_gaps/limitations"
                        " 中说明排除原因，不为引用数量拼凑主张。线索自身保持 LEAD_ONLY；"
                        "整体报告状态依据已核验正文对研究问题的实际覆盖判断，不因存在标题自动降级，"
                        "也不因存在正文自动判定充分；正文不足时仍保留真实缺口。"
                        "不得据标题推断评级依据、估值、经营事实或研报分歧；查询失败时如实记录 gap，"
                        "不得假称已使用该线索。"
                    )
            if capability in {"MACRO_CONTEXT", "MARKET_STATE"}:
                instruction += (
                    " verified_documents 仅包含已通过正文核验且与当前能力匹配的"
                    "策略或政策材料；documents 必须逐字复制 report_document 元数据，并用"
                    " research_relationships 明确标记它是外部观点、支持或冲突，不得将"
                    "外部观点自动升级为事实。一个能力的材料不得借给另一个能力。"
                )
            if capability == "OPTIONS_FLOW":
                instruction += (
                    " 对已读取的 bid/ask、具体 Greeks 及标的 IV/HV，解释与期限和风险结构的关系，"
                    "不能仅说提供这些字段。分别核对合约 IV 与标的 IV/HV 各自 Evidence 的单位字段；"
                    "标的快照若只有原始数值而无单位定义，可保留数值但须写单位未核实，"
                    "不得借合约 IV 的单位推断标的为百分点或小数，也不跨口径直接比较。"
                    "派生计算仅引用受支持工具或附件。"
                    "分别判断 Yahoo 原缺项、同合约 OpenD 已补字段和有效时间/vintage 不足，"
                    "不能把时间限制写成数值字段缺失，不能合并为同步全链或推断主动资金方向。"
                )
            if task.get("source_literal_selection") == "source-literal-selection/1.1.0":
                instruction += (
                    " 供应商宏观观测事实须选同一条实际query过的记录成组呈现："
                    "在claim.statement使用{{sf.key}}，顶层source_literal_selections逐项提交"
                    "claim_id、placeholder、evidence_ref、field=moomoo_macro_observation；"
                    "同一claim.evidence_refs引用所选记录，每个占位恰好一次。"
                    "程序仅填该条原label、观察as_of、actual/previous/consensus、unit_type、"
                    "raw_release_time及vintage边界，不换算小数百分比、不填零、不替你选最新期。"
                    "不要在占位外再次手抄同一供应商观测的数值/期间；"
                    "官方事实、公司暴露、传导判断及反向情景仍由你按证据研究。"
                    "只有目录、没有成功query不能绑定；来源缺失须保留真实gap。"
                )
            elif task.get("source_literal_selection"):
                instruction += (
                    " 如需在claim.statement中逐字呈现已查询来源的SEC整数USD或期权报价时间，"
                    "可在草稿使用{{sf.key}}占位，并在顶层source_literal_selections逐项提交"
                    "claim_id、placeholder、evidence_ref、field；同一主张evidence_refs必须引用该来源。"
                    "基本面只选sec_usd_value；期权报价只选as_of或retrieved_at。"
                    "sec_usd_value占位会填入原整数和USD，正文不要在占位后重复写USD。"
                    "时间占位会填入完整的as_of=<原时间>或retrieved_at=<原时间>，"
                    "正文写‘Evidence的{{sf.time}}’，不要在占位外重复手写字段标签。"
                    "每处占位只出现一次；由你选择正确来源与字段，程序仅填原值，不审定研究含义。"
                )
                if (capability == "OPTIONS_FLOW"
                        and task.get("tool_identity_version") == "research-tool-identity/1.0.0"):
                    instruction += (
                        " 报价身份问题须呈现所用合约报价的实际观察时间as_of，"
                        "并与retrieved_at分别标明；只说存在观察时间或只给获取日不回答该问题。"
                        "沿上述来源时间选择呈现已查询且同claim引用的报价原时间。"
                        "跨期限IV/Greeks比较须在同一主张分别引用实际比较的不同到期合约，"
                        "核对各自单位及观察时间；同一合约两供应商或标的概览不构成跨期限依据。"
                        "已查询另一合约也不能替代该主张的引用；无法可靠比较时说明具体限制。"
                        " 由你选择代表合约后，按其标的、到期、call/put与行权价核对既有证据目录，"
                        "查询同身份OpenD合约报价及风险补源，再判断Yahoo缺项是否已补。"
                        "可得Greeks、IV、OI和乘数须用对应实际query及引用解释；"
                        "风险记录的有效观察时间/vintage不明只限制时效和跨源比较，"
                        "不等于这些原始数值字段缺失。各源报价和风险独立呈现，不合成同步快照；"
                        "身份无法核对或补源确实不可得时才保留相应字段gap。"
                    )
            if capability == "MACRO_CONTEXT":
                instruction += (
                    " 本任务只形成宏观环境报告。allowed_evidence_ids 同时包含官方宏观事实与按证券分组的精选公司事实。"
                    "指标所述月份以原data_time/观察期为准；raw_release_time是发布日，不是观察月份。"
                    "逐项核对value/previous属于哪一观察期，发布时间、获取时间和修订边界另述；"
                    "不得用市场价格走势替代政策或经济活动事实。"
                    " 公司SEC结构化事实若仅给出整数USD，本任务没有金额换算收据时须保留原值和USD单位；"
                    "不得自行缩写为million/billion或改写为亿美元，即使写‘约’也不能代替换算血缘。"
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
                    "交稿前区分融资/资本成本、项目要求回报门槛与预计净回报，逐条核对传导方向一致；"
                    "不要将门槛与收益混为一个变量。传导仍是你的研究假设，不等于已验证价格因果。"
                )
            if capability == "MARKET_STATE":
                instruction += (
                    " 本任务只形成共享市场状态报告。prepared_analysis.calculation 是广泛市场基准的确定性"
                    "市场状态产物；有完整窗口时必须使用其收益、波动和回撤，按计算选择契约选取对应结果。"
                    "跨资产、板块、波动或信用指标必须保留原指标或代理身份，不得把股票波动称为信用。"
                    " prepared_analysis.breadth_calculation 若存在，涨跌持平合计也选取对应冻结计算，"
                    "不得重新抄写或自行拼装合计。"
                    "交稿前检查：任何声称来自广度预计算的claim，包括仅解释rise/flat/fall分桶，"
                    "都必须在calculation_selections选择实际广度结果，"
                    "并将该claim_id关联到所选结果；SPY收益或波动计算不能替代广度计算。"
                    "只解释所选结果实际返回的字段；原rise/flat/fall三项计数不代表已有grand total。"
                    "结果未给总数时保留三个原计数，不自己相加后称为计算汇总。"
                    "它与基准日线独立。不存在时只能解释已核实分桶并保留 gap，不自行加总。"
                )
                if task.get("tool_identity_version") == "research-tool-identity/1.0.0":
                    instruction += (
                        " 定稿summary前回读本稿claims及其所选计算收据，逐项核对同一对象、"
                        "窗口、单位、比较方向和幅度；摘要不能反转正文的涨跌计数或收益关系，"
                        "也不能引入无依据结论。由你纠正研究表述，程序不替你修改摘要。"
                    )
                instruction += (
                    "当前有多只普通股持仓：必须读取持仓相关公司暴露事实并解释差异化传导；"
                    if len(security_ids) >= 2 else
                    "当前只有一只普通股持仓：必须解释该公司对当前市场状态的暴露、传导假设与反向情景；"
                    "先实际查询目录内该公司的业务/MD&A或其它合格暴露证据，再解释传导。"
                    "尚未查询不等于资料未提供，不得将目录内已准入的公司证据写成来源缺失；"
                    "不得因缺少第二只持仓而判定资料不足，也不得自动补入另一家公司。"
                )
                instruction += "不得用主观风险标签替代计算和冻结 Evidence。"
            if is_single_stock(handoff):
                instruction = instruction.replace("当前只有一只普通股持仓", "当前只有一只普通股研究标的")
                instruction = instruction.replace("不得因缺少第二只持仓", "不得因缺少第二只研究标的")
            if task.get("material_preparation", {}).get("status") == "FAILED":
                instruction += (
                    " material_preparation 已记录上游资料准备的确定性失败；本维度必须输出"
                    " FAILED / evaluation_status=FAIL，并保留 failure_code 与具体影响，不得将"
                    "实现或契约失败伪装成 SOURCE_LIMITED。"
                )
            # Finalize the task only after capability-specific source coverage
            # is attached. Hook validation reads this file, not the model packet.
            task["task_hash"] = legacy_envelope_hash(task, hash_field="task_hash")
            _write_object(run_dir / task_path, task)
            input_refs = [
                research_input_ref(handoff), "council-request.json",
                "evidence/gate.json", "audit/provider-coverage.json", task_path,
            ]
            if capability == "INDUSTRY_COMPARISON" and peer_candidate_pool is not None:
                input_refs.append("research/peer-candidate-pool.json")
            output_schema = _dynamic_draft_schema(
                repository_root, run_id=run_id, invocation_id=invocation_id,
                agent=agent, allowed_evidence_ids=allowed_ids,
                allowed_artifact_refs=task["allowed_artifact_refs"],
                allowed_calculation_evidence_ids=task.get("allowed_calculation_evidence_ids", []),
                allowed_documents=task["allowed_documents"],
                claims_forbidden=(
                    capability == "INDUSTRY_COMPARISON"
                    and not frozen_peer_candidates
                ),
                technical_calculation_missing=(
                    capability == "TECHNICAL_STRUCTURE"
                    and prepared_analysis["calculation"] is None
                ),
                source_literal_selection=bool(task.get("source_literal_selection")),
                macro_observation_selection=(
                    task.get("source_literal_selection") == "source-literal-selection/1.1.0"
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
                "model": selected_model, "prompt_hash": canonical_hash({"instruction": instruction, "questions": minimum_questions}),
                "input_refs": input_refs,
                "tool_permissions": capability_tools(capability),
                "calculation_ledger_ref": task.get("calculation_ledger_ref"),
                **({"calculation_selection_version": task["calculation_selection_version"]}
                   if task.get("calculation_selection_version") else {}),
                **({"prepared_result_reference_version": task["prepared_result_reference_version"]}
                   if task.get("prepared_result_reference_version") else {}),
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
            if task.get("submission_version"):
                invocation["tool_permissions"].append("research_report.submit")
            invocation["manifest_hash"] = legacy_envelope_hash(invocation, hash_field="manifest_hash")
            invocation_path = f"invocations/by-id/{canonical_hash({'invocation_id': invocation_id})}.json"
            _write_object(run_dir / invocation_path, invocation)
            packet = {
                "dispatch_contract": DISPATCH_VERSION,
                "reference_transport_version": REFERENCE_VERSION,
                "identity": {"run_id": run_id, "invocation_id": invocation_id, "task_id": task_id,
                             "task_name": task_name, "agent": agent, "security_ids": security_ids,
                             **(research_input_binding(handoff) if is_single_stock(handoff) else {})},
                "instruction": instruction,
                "minimum_questions": minimum_questions,
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
                    {**{key: fact.get(key) for key in ("evidence_id", "security_id", "semantic_field", "source_id", "as_of", "published_at", "retrieved_at", "unit", "usage")}, **_text_locator(fact)}
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
            if task.get("submission_version"):
                packet["submission_access"] = {"token": secrets.token_urlsafe(32)}
                private_path = run_dir / packet_path
                private_path.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(private_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as stream:
                    json.dump(packet, stream, ensure_ascii=False, indent=2, sort_keys=True)
                    stream.write("\n")
            else:
                _write_object(run_dir / packet_path, packet)
            tasks.append({
                **task, "task_path": task_path, "invocation_path": invocation_path,
                "packet_path": packet_path, "packet_hash": canonical_hash(packet),
            })
    index = {
        "schema_version": DISPATCH_VERSION, "run_id": run_id,
        "target_concurrency": target_concurrency, "tasks": tasks,
    }
    index["index_hash"] = legacy_envelope_hash(index, hash_field="index_hash")
    _write_object(run_dir / "research/dispatch-index.json", index)
    manifest = {
        "schema_version": SINGLE_STOCK_STAGE_VERSION if is_single_stock(handoff) else STAGE_VERSION, "run_id": run_id,
        "stage": stage, "source_mode": "frozen-gate",
        **({"gate_input_binding": gate_input_binding} if gate_input_binding is not None else {}),
        "reference_transport_version": REFERENCE_VERSION,
        "model": selected_model, "parent_model": selected_model, "output_dir": str(run_dir),
        "discovery": {"product_root": str(product_root)},
        "research_input_topology": topology_lock,
        "research_execution_fingerprint": _research_execution_fingerprint(repository_root),
        "provider_coverage_hash": provider_coverage["coverage_hash"],
        "provider_coverage_ref": "audit/provider-coverage.json",
        "agent_bindings": agent_bindings, "skill_bindings": skill_bindings,
        **_stage_input_binding(handoff),
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
    if core_forward_only:
        manifest["forward_scope"] = "SKEPTIC_REQUIRED_CORE_ONLY"
        manifest["selected_forward_capabilities"] = list(capabilities)
    if task_bound_tools:
        manifest["tool_identity_version"] = TASK_TOOL_IDENTITY_VERSION
    if is_single_stock(handoff):
        from product.runtime.research_input import single_stock_contract_locks
        manifest["input_contract_locks"] = single_stock_contract_locks(product_root)
    manifest["manifest_hash"] = legacy_envelope_hash(manifest, hash_field="manifest_hash")
    from product.runtime.evidence_gate import validate_frozen_gate_binding
    validate_frozen_gate_binding(run_dir, manifest, gate)
    _write_object(run_dir / "run_manifest.json", manifest)
    return {"status": "PREPARED", "run_id": run_id, "run_dir": str(run_dir), "task_count": len(tasks)}


def read_multidimensional_task_state(run_dir: Path) -> dict[str, Any]:
    """只投影本批可信生命周期；不协调、不写报告、不评判研究语义。"""
    from product.runtime.fixture_mcp import TASK_TOOL_IDENTITY_VERSION

    root = Path(run_dir).resolve()
    def reject():
        raise MultidimensionalStageError("MULTIDIMENSIONAL_TASK_STATE_BINDING_INVALID")

    def lifecycle_snapshot():
        paths = [root / "invocation/subagent-dispatches.jsonl", root / "invocation/subagent-events.jsonl"]
        locks = [p.with_suffix(p.suffix + ".lock") for p in paths]
        if any(not p.resolve().is_relative_to(root) for p in [*paths, *locks]):
            reject()
        # 尚无首个派发锁时观察为空；不随后读取可能刚产生的Start而混合时点。
        if not locks[0].exists() and not paths[0].exists():
            return [], []
        with ExitStack() as stack:
            # 与原PreToolUse的 dispatch -> event 顺序一致；同时持有读锁。
            observed = []
            for path, lock in zip(paths, locks):
                present = lock.exists() or path.exists()
                observed.append(present)
                if present:
                    handle = stack.enter_context(lock.open("r", encoding="utf-8"))
                    fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            rows_by_log = [[json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
                           if present and path.is_file() else [] for path, present in zip(paths, observed)]
        for rows in rows_by_log:
            for row in rows:
                if not isinstance(row, dict) or row.get("event_hash") != legacy_envelope_hash(row, hash_field="event_hash"):
                    reject()
        return rows_by_log

    try:
        manifest = _read_object(root / "run_manifest.json")
        index = _read_object(root / "research/dispatch-index.json")
        single_forward = (is_single_stock(manifest)
                          and manifest.get("stage") == "INDEPENDENT_COUNTER_THESIS_RESEARCH")
        if single_forward:
            # Only the coordinator's read-only lifecycle projection is shared.
            # This does not enable task_name query/calculation identity routing.
            load_research_input(root, manifest=manifest)
        if ((not single_forward and (
                manifest.get("stage") != "MULTI_DIMENSIONAL_HOLDING_RESEARCH"
                or manifest.get("tool_identity_version") != TASK_TOOL_IDENTITY_VERSION))
                or manifest.get("manifest_hash") != legacy_envelope_hash(manifest, hash_field="manifest_hash")
                or index.get("index_hash") != legacy_envelope_hash(index, hash_field="index_hash")
                or manifest.get("dispatch_index_hash") != index.get("index_hash")
                or manifest.get("run_id") != index.get("run_id")
                or Path(str(manifest.get("output_dir", ""))).resolve() != root):
            reject()
        tasks = index["tasks"]
        if (not tasks or any(len({t[key] for t in tasks}) != len(tasks)
                             for key in ("task_name", "task_id", "invocation_id"))):
            reject()
        by_name = {t["task_name"]: t for t in tasks}
        by_id = {t["task_id"]: t for t in tasks}
        for task in tasks:
            path = (root / task["invocation_path"]).resolve()
            if not path.is_relative_to(root):
                reject()
            invocation = _read_object(path)
            if (invocation.get("manifest_hash") != legacy_envelope_hash(invocation, hash_field="manifest_hash")
                    or invocation.get("run_id") != index["run_id"]
                    or invocation.get("invocation_id") != task["invocation_id"]
                    or task.get("run_id") != index["run_id"]
                    or (not single_forward and task.get("tool_identity_version") != TASK_TOOL_IDENTITY_VERSION)
                    or any(dep not in by_id for dep in task.get("depends_on", []))):
                reject()
        dispatches, events = lifecycle_snapshot()
        allowed = [d for d in dispatches if d.get("decision") == "ALLOW"]
        parents = {d.get("parent_session_id") for d in allowed}
        if (len(parents) > 1 or (parents and not next(iter(parents)))
                or any(d.get("task_name") not in by_name for d in allowed)
                or len({d["task_name"] for d in allowed}) != len(allowed)):
            reject()
        parent = next(iter(parents), None)
        by_dispatch = {d["task_name"]: d for d in allowed}
        snapshots = {}
        reports = {}
        start_by_name = {}
        for task in tasks:
            name = task["task_name"]
            dispatch = by_dispatch.get(name)
            snapshot = {"task_name": name, "execution_status": "PENDING", "outcome": None,
                        "research_status": None, "coverage_status": None}
            snapshots[task["task_id"]] = snapshot
            if dispatch is None:
                continue
            if (dispatch.get("agent_type") != task["agent"] or dispatch.get("fork_turns") != "none"
                    or dispatch.get("dispatch_binding", {}).get("matched") is not True):
                reject()
            snapshot["execution_status"] = "DISPATCHED"
            starts = [e for e in events if e.get("hook_event_name") == "SubagentStart"
                      and e.get("context_binding", {}).get("task_name") == name]
            if not starts:
                continue
            if len(starts) != 1:
                reject()
            start = starts[0]
            context = start["context_binding"]
            if (start.get("parent_session_id") != parent or not start.get("child_session_id")
                    or start.get("agent_type") != task["agent"] or start.get("model") != manifest["model"]
                    or context.get("status") != "DELIVERED" or context.get("run_id") != index["run_id"]
                    or context.get("invocation_id") != task["invocation_id"]):
                reject()
            # 派发包不含依赖；Start包含真实已保存依赖，两者hash不能机械判相等。
            if task.get("depends_on"):
                expected_start_hash = canonical_hash(build_multidimensional_dispatch_packet(Path(), root, name))
            else:
                expected_start_hash = dispatch.get("dispatch_binding", {}).get("packet_hash")
            if context.get("packet_hash") != expected_start_hash:
                reject()
            start_by_name[name] = start
            snapshot["execution_status"] = "RUNNING"
            stops = [e for e in events if e.get("hook_event_name") == "SubagentStop"
                     and e.get("trusted_task_binding", {}).get("task_name") == name]
            if not stops:
                continue  # StopBlocked/REPAIR_REQUESTED 仍在运行。
            if len(stops) != 1:
                reject()
            stop = stops[0]
            trusted = {key: task[key] for key in ("task_name", "task_id", "run_id", "invocation_id", "agent")}
            capture = stop.get("output_capture", {})
            if (stop.get("trusted_task_binding") != trusted or stop.get("parent_session_id") != parent
                    or stop.get("child_session_id") != start["child_session_id"]
                    or stop.get("agent_type") != task["agent"] or stop.get("model") != start["model"]
                    or stop.get("hook_decision") == "BLOCK" or capture.get("repair_state") == "REPAIR_REQUESTED"
                    or capture.get("status") not in {"SAVED", "FAILED"}):
                reject()
            snapshot.update(execution_status="TERMINAL", outcome=capture["status"])
            if capture["status"] == "SAVED":
                path = (root / capture["path"]).resolve()
                if not path.is_relative_to(root / "research/reports"):
                    reject()
                report = _read_object(path)
                if (stop.get("identity_binding", {}).get("status") != "BOUND"
                        or capture.get("task_id") != task["task_id"]
                        or capture.get("output_hash") != canonical_hash(report)
                        or report.get("report_hash") != legacy_envelope_hash(report, hash_field="report_hash")
                        or report.get("run_id") != index["run_id"] or report.get("invocation_id") != task["invocation_id"]
                        or report.get("report_id") != f"dimension-report:{task['task_id']}"
                        or report.get("capability") != task["capability"] or report.get("security_ids") != task["security_ids"]):
                    reject()
                reports[task["task_id"]] = report
                snapshot.update(research_status=report["status"], coverage_status=report["sufficiency"])
        # 复用报告消费者的结构/引用检查；不运行Finalizer或内容评级。
        from product.council.multidimensional_research import validate_research_dimension_report
        handoff = load_research_input(root, manifest=manifest)
        request = _read_object(root / "council-request.json")
        if (any(manifest.get(k) != v for k, v in _stage_input_binding(handoff).items())
                or request.get("request_hash") != manifest.get("council_request_hash")):
            reject()
        for task_id, report in reports.items():
            task = by_id[task_id]
            dependencies = [reports[dep] for dep in task.get("depends_on", [])]
            validate_research_dimension_report(
                report, expected_bindings={
                    **research_input_binding(handoff), "council_request_id": request["request_id"],
                    "council_request_hash": request["request_hash"], "decision_cutoff": task["time_context"]["window_end"],
                }, allowed_security_ids=task["security_ids"], allowed_evidence_ids=task["allowed_evidence_ids"],
                allowed_calculation_evidence_ids=task.get("allowed_calculation_evidence_ids", []),
                known_research_claim_ids=known_claim_references(dependencies), allowed_documents=task.get("allowed_documents", []),
            )
            if (report.get("time_context") != task["time_context"]
                    or report.get("execution", {}).get("agent_name") != task["agent"]
                    or report.get("execution", {}).get("model") != manifest["model"]):
                reject()
        # 无可信 Start/派发的额外生命周期不能被静默忽略。
        children = {e.get("child_session_id") for e in events if e.get("hook_event_name") == "SubagentStart"}
        if len(children) != sum(e.get("hook_event_name") == "SubagentStart" for e in events):
            reject()
        for event in events:
            if (event.get("parent_session_id") != parent or event.get("agent_type") not in {t["agent"] for t in tasks}
                    or event.get("child_session_id") not in children
                    or (event.get("hook_event_name") == "SubagentStart"
                        and event.get("context_binding", {}).get("task_name") not in by_dispatch)
                    or (event.get("hook_event_name") in {"SubagentStop", "SubagentStopBlocked"}
                        and event.get("trusted_task_binding", {}).get("task_name") not in by_dispatch)):
                reject()
            if event.get("hook_event_name") in {"SubagentStop", "SubagentStopBlocked"}:
                trusted = event.get("trusted_task_binding", {})
                name = trusted.get("task_name")
                task = by_name.get(name)
                start = start_by_name.get(name)
                if (task is None or start is None
                        or trusted != {key: task[key] for key in ("task_name", "task_id", "run_id", "invocation_id", "agent")}
                        or event.get("child_session_id") != start["child_session_id"]
                        or event.get("agent_type") != start["agent_type"] or event.get("model") != start["model"]):
                    reject()
        # 依赖失败只有原Hook明确拒绝后才成为终态，不将暂未就绪自动算失败。
        for task in tasks:
            state = snapshots[task["task_id"]]
            dependencies = [snapshots[dep] for dep in task.get("depends_on", [])]
            failed = any(d["outcome"] in {"FAILED", "DEPENDENCY_BLOCKED"} for d in dependencies)
            denied = any(d.get("task_name") == task["task_name"] and d.get("parent_session_id") == parent
                         and d.get("agent_type") == task["agent"] and d.get("decision") == "DENY_DISPATCH_CONTRACT"
                         and d.get("dispatch_binding", {}).get("failure_code") == "RESEARCH_DEPENDENCY_NOT_READY"
                         for d in dispatches)
            if state["execution_status"] == "PENDING" and failed and denied:
                state.update(execution_status="TERMINAL", outcome="DEPENDENCY_BLOCKED")
            state["dependency_ready"] = all(d["outcome"] == "SAVED" for d in dependencies)
        states = list(snapshots.values())
        return {"schema_version": "multidimensional-task-state/1.0.0", "run_id": index["run_id"],
                "index_hash": index["index_hash"], "tasks": states, "expected": len(states),
                "terminal_count": sum(s["execution_status"] == "TERMINAL" for s in states),
                "all_tasks_terminal": all(s["execution_status"] == "TERMINAL" for s in states),
                "content_acceptance": "NOT_EVALUATED"}
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_TASK_STATE_BINDING_INVALID") from exc




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
    if (len(by_name) != len(tasks) or len(by_id) != len(tasks)
            or any(not name for name in by_name) or any(not identifier for identifier in by_id)):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_DISPATCH_INDEX_AMBIGUOUS")
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
        if (not isinstance(dependencies, list) or any(not isinstance(item, str) or not item for item in dependencies)
                or len(set(dependencies)) != len(dependencies)):
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


def _verified_retry_dependencies(run_dir: Path, task_name: str) -> list[dict[str, Any]]:
    """Narrow read-only reuse: one saved fundamental dependency of a report retry."""
    from product.council.multidimensional_research import validate_research_dimension_report

    index = _read_object(run_dir / "research/dispatch-index.json")
    closure = _target_task_closure(index, task_name)
    if [t["capability"] for t in closure] != ["FUNDAMENTAL_EVENT", "RESEARCH_REPORT"]:
        return []
    dependency = closure[0]
    candidates = [p for p in (run_dir / "research/reports").glob("*/dimension-report.json")
                  if _read_object(p).get("report_id") == f"dimension-report:{dependency['task_id']}"]
    if not candidates:
        return []
    if len(candidates) != 1:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_REUSE_REPORT_AMBIGUOUS")
    path = candidates[0]
    report = _read_object(path)
    process = _read_object(run_dir / "invocation/process-result.json")
    if (process.get("source_integrity_unchanged") is not True
            or process.get("timed_out") is not False or process.get("process_exit_code") != 0):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_REUSE_PROCESS_INVALID")
    manifest = _read_object(run_dir / "run_manifest.json")
    if manifest.get("manifest_hash") != legacy_envelope_hash(manifest, hash_field="manifest_hash"):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_REUSE_BINDING_INVALID:manifest_hash")
    repository_root = Path(manifest["discovery"]["product_root"]).parent.resolve()
    from product.runtime.research_input_topology import research_input_topology_lock
    from product.runtime.evidence_gate import validate_frozen_gate_binding
    gate = _read_object(run_dir / "evidence/gate.json")
    validate_frozen_gate_binding(run_dir, manifest, gate)
    if (manifest.get("research_execution_fingerprint") != _research_execution_fingerprint(repository_root)
            or manifest.get("research_input_topology") != research_input_topology_lock(repository_root)):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_REUSE_VERSION_INCOMPATIBLE")
    for task in closure:
        invocation = _read_object(run_dir / task["invocation_path"])
        packet = build_multidimensional_dispatch_packet(repository_root, run_dir, task["task_name"],
                                                      include_dependency_reports=False)
        if (manifest.get("agent_bindings", {}).get(task["agent"])
                != _agent_binding(repository_root / "product", task["agent"])
                or manifest.get("skill_bindings", {}).get(task["skill_name"])
                != _skill_binding(repository_root / "product", task["skill_name"])
                or invocation.get("model") != manifest.get("model")
                or invocation.get("manifest_hash") != legacy_envelope_hash(invocation, hash_field="manifest_hash")
                or packet.get("task") != _read_object(run_dir / task["task_path"])
                or packet.get("allowed_evidence_ids") != task["allowed_evidence_ids"]
                or packet.get("task", {}).get("time_context") != task["time_context"]):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_REUSE_VERSION_INCOMPATIBLE")
    handoff = load_research_input(run_dir)
    request = _read_object(run_dir / "council-request.json")
    for value, field in ((manifest, "manifest_hash"), (index, "index_hash"), (gate, "bundle_hash")):
        try:
            verify_legacy_envelope_hash(value, hash_field=field, location=f"multidimensional-reuse:{field}")
        except HashContractError as exc:
            raise MultidimensionalStageError(f"MULTIDIMENSIONAL_REUSE_BINDING_INVALID:{exc}") from exc
    if (manifest.get("stage") != "MULTI_DIMENSIONAL_HOLDING_RESEARCH"
            or manifest["dispatch_index_hash"] != index["index_hash"]
            or manifest["gate_hash"] != gate["bundle_hash"]
            or manifest["council_request_hash"] != request["request_hash"]
            or report["run_id"] != index["run_id"]
            or report["invocation_id"] != dependency["invocation_id"]
            or report["capability"] != dependency["capability"]
            or report["security_ids"] != dependency["security_ids"]
            or report["status"] in {"FAILED", "TIMEOUT"}):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_REUSE_BINDING_INVALID")
    validate_research_dimension_report(
        report, expected_bindings={
            **research_input_binding(handoff), "council_request_id": request["request_id"],
            "council_request_hash": request["request_hash"], "decision_cutoff": gate["decision_cutoff"],
        }, allowed_security_ids=dependency["security_ids"],
        allowed_evidence_ids=dependency["allowed_evidence_ids"],
        allowed_documents=dependency.get("allowed_documents", []),
    )
    # The binding builder also checks the dependency's canonical report hash.
    build_multidimensional_dispatch_packet(Path(), run_dir, task_name)
    log = run_dir / "invocation/subagent-events.jsonl"
    events = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
    matching = [e for e in events if e.get("hook_event_name") == "SubagentStop"
                and e.get("output_capture", {}).get("status") == "SAVED"
                and e["output_capture"].get("task_id") == dependency["task_id"]
                and e["output_capture"].get("path") == str(path.relative_to(run_dir))
                and e["output_capture"].get("output_hash") == canonical_hash(report)]
    if len(matching) != 1:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_REUSE_EVENT_INVALID")
    stop = matching[0]
    starts = [e for e in events if e.get("hook_event_name") == "SubagentStart"
              and e.get("child_session_id") == stop.get("child_session_id")
              and e.get("parent_session_id") == stop.get("parent_session_id")]
    if len(starts) != 1 or any(
        e.get("event_hash") != legacy_envelope_hash(e, hash_field="event_hash")
        for e in [starts[0], stop]
    ):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_REUSE_EVENT_INVALID")
    return [{"task_id": dependency["task_id"], "task_name": dependency["task_name"],
             "target_task_name": task_name, "run_id": index["run_id"],
             "gate_hash": gate["bundle_hash"], "index_hash": index["index_hash"],
             "report_ref": str(path.relative_to(run_dir)), "report_file_hash": file_hash(path),
             "report_hash": report["report_hash"], "source_event_log_hash": file_hash(log),
             "source_event": matching[0]}]


def read_retry_dependencies(run_dir: Path, invocation_dir: Path, task_name: str) -> list[dict[str, Any]]:
    if not invocation_dir.resolve().is_relative_to((run_dir / "invocation/retries").resolve()):
        return []
    path = invocation_dir / "reused-dependencies.json"
    if not path.exists():
        return []
    value = _read_object(path)
    if value.get("target_task_name") != task_name or value.get("dependencies") != _verified_retry_dependencies(run_dir, task_name):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_REUSE_CHANGED")
    return value["dependencies"]




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
    reused = read_retry_dependencies(run_dir, invocation_dir, task_name)
    reused_ids = {d["task_id"] for d in reused}
    executed = [t for t in closure if t["task_id"] not in reused_ids]
    expected_names = [item["task_name"] for item in executed]
    expected_ids = {item["task_id"] for item in executed}
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
    if len(saved) != len(executed) or set(saved_by_task) != expected_ids:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_TARGET_OUTPUT_INVALID")
    saved_by_task.update({d["task_id"]: d["source_event"] for d in reused})
    handoff = load_research_input(run_dir)
    request = _read_object(run_dir / "council-request.json")
    gate = _read_object(run_dir / "evidence/gate.json")
    bindings = {
        **research_input_binding(handoff),
        "council_request_id": request["request_id"],
        "council_request_hash": request["request_hash"],
        "decision_cutoff": gate["decision_cutoff"],
    }
    security_ids = [
        item["security_id"] for item in research_subjects(handoff)
        if item["asset_type"] == "COMMON_STOCK"
    ]
    validated_reports: dict[str, dict[str, Any]] = {}
    report_inventory: list[dict[str, Any]] = []
    for task in closure:
        event = saved_by_task[task["task_id"]]
        report_path = run_dir / event["output_capture"]["path"]
        report = _read_object(report_path)
        dependency_claim_ids = known_claim_references([
            validated_reports[dependency_id] for dependency_id in task.get("depends_on", [])
        ])
        validate_research_dimension_report(
            report,
            expected_bindings=bindings,
            allowed_security_ids=security_ids,
            allowed_evidence_ids=task["allowed_evidence_ids"],
            allowed_calculation_evidence_ids=task.get("allowed_calculation_evidence_ids", []),
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
        "reused_dependencies": reused,
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
    proof["proof_hash"] = legacy_envelope_hash(proof, hash_field="proof_hash")
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
    user_interrupted: bool = False,
) -> dict[str, Any]:
    """重验每个维度报告并组装不含投资动作的 HoldingResearchBundle。"""

    from product.council.multidimensional_output import render_holding_research_bundle_markdown, project_research_status
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
    handoff = load_research_input(run_dir)
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
            and not user_interrupted
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
    if not user_interrupted and allowed_names | terminal_names != expected_names:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_DISPATCH_PROOF_INCOMPLETE")
    common_ids = [
        item["security_id"] for item in research_subjects(handoff)
        if item["asset_type"] == "COMMON_STOCK"
    ]
    bindings = {
        **research_input_binding(handoff), "council_request_id": council_request["request_id"],
        "council_request_hash": council_request["request_hash"], "decision_cutoff": gate["decision_cutoff"],
    }
    reports: list[dict[str, Any]] = []
    report_paths: dict[str, str] = {}
    report_submission_refs: list[str] = []
    reports_by_task_id: dict[str, dict[str, Any]] = {}
    for task in index["tasks"]:
        event = completed_events.get(task["task_id"])
        if event is None:
            if task["task_id"] not in failed_events and not user_interrupted:
                raise MultidimensionalStageError(
                    f"MULTIDIMENSIONAL_REPORT_MISSING:{task['task_id']}"
                )
            continue
        path = run_dir / event["output_capture"]["path"]
        report = _read_object(path)
        validate_breadth_calculation_references(run_dir, report)
        from product.runtime.research_submission import ASSEMBLY_VERSIONS, selected_calculations_for_report
        if task.get("submission_version") in ASSEMBLY_VERSIONS:
            selected_calculations_for_report(run_dir, report)
            accepted = event["output_capture"].get("submission_selection_record")
            binding = event.get("submission_binding")
            if (not isinstance(accepted, Mapping) or not isinstance(binding, Mapping)
                    or not isinstance(accepted.get("path"), str)
                    or not isinstance(binding.get("path"), str)):
                raise MultidimensionalStageError("MULTIDIMENSIONAL_SUBMISSION_SELECTION_RECORD_MISSING")
            report_submission_refs.extend([accepted["path"], binding["path"]])
            if ((run_dir / "events/mcp/events.jsonl").is_file()
                    and "events/mcp/events.jsonl" not in report_submission_refs):
                report_submission_refs.append("events/mcp/events.jsonl")
        if any(
            dependency_id not in reports_by_task_id
            for dependency_id in task.get("depends_on", [])
        ):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_DEPENDENCY_ORDER_INVALID")
        dependency_claim_ids = known_claim_references([
            reports_by_task_id[dependency_id] for dependency_id in task.get("depends_on", [])
        ])
        validate_research_dimension_report(
            report, expected_bindings=bindings, allowed_security_ids=common_ids,
            allowed_evidence_ids=task["allowed_evidence_ids"],
            allowed_calculation_evidence_ids=task.get("allowed_calculation_evidence_ids", []),
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
        if import_manifest.get("import_hash") != legacy_envelope_hash(import_manifest, hash_field="import_hash"):
            raise MultidimensionalStageError("MULTIDIMENSIONAL_COMPANY_IMPORT_PROOF_INVALID")
        if (
            any(import_manifest.get(k) != v for k, v in _stage_input_binding(handoff).items())
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
    declared_content_failure = any(report.get("evaluation_status") == "FAIL" for report in reports)
    bundle = finalize_holding_research_bundle({
        "schema_version": "holding-research-bundle/3.0.0" if is_single_stock(handoff) else HOLDING_RESEARCH_BUNDLE_VERSION,
        "bundle_id": f"holding-research-bundle:{manifest['run_id']}",
        "run_id": manifest["run_id"],
        "bindings": {key: value for key, value in bindings.items() if key != "decision_cutoff"},
        "decision_cutoff": gate["decision_cutoff"],
        "common_stock_security_ids": common_ids,
        "report_refs": report_refs,
        "coverage": coverage,
        "consumability": "STRUCTURALLY_CONSUMABLE",
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
            *report_paths.values(), *report_submission_refs,
            *imported_artifact_refs, *materials_artifact_refs,
            *(ref for report in reports for ref in report.get("artifact_refs", [])),
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
    proof["proof_hash"] = legacy_envelope_hash(proof, hash_field="proof_hash")
    _write_object(run_dir / "research/execution-proof.json", proof)
    contract_status = (
        "FAILED" if failed_events else "PASSED" if proof["all_reports_valid"] else "INCOMPLETE"
    )
    return {
        "status": contract_status, "run_id": manifest["run_id"],
        "contract_status": contract_status,
        "failure_code": "MULTIDIMENSIONAL_TASK_VALIDATION_FAILED" if failed_events else None,
        "research_review_status": "NOT_REVIEWED",
        "agent_declared_content_failure": declared_content_failure,
        "promotion_status": "NOT_EVALUATED",
        "status_projection": project_research_status(
            [*reports, *imported_equity_reports], coverage=coverage,
        ),
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
    record["adoption_hash"] = legacy_envelope_hash(record, hash_field="adoption_hash")
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

    from product.council.multidimensional_output import render_holding_research_bundle_markdown, project_research_status
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
    base_handoff = load_research_input(base_run, manifest=base_manifest)
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
        if base_bundle.get("schema_version") in {HOLDING_RESEARCH_BUNDLE_VERSION, "holding-research-bundle/3.0.0"}
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
    _write_object(target / research_input_ref(base_handoff), base_handoff)
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
    canonical_gate["bundle_hash"] = legacy_envelope_hash(canonical_gate, hash_field="bundle_hash")
    _write_object(target / "evidence/gate.json", canonical_gate)

    copied_artifacts = {
        _copy_run_artifact(base_run, target, relative)
        for relative in base_bundle.get("artifact_refs", [])
    }
    for reference in base_bundle.get("report_refs", []):
        copied_artifacts.add(
            _copy_run_artifact(base_run, target, str(reference["artifact_ref"]))
        )
    from product.runtime.research_submission import selected_calculations_for_report
    for report in base_dimension_reports:
        selected_calculations_for_report(target, report)
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
        "consumability": "STRUCTURALLY_CONSUMABLE",
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
    run_manifest["manifest_hash"] = legacy_envelope_hash(run_manifest, hash_field="manifest_hash")
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
    package_manifest["proof_hash"] = legacy_envelope_hash(package_manifest, hash_field="proof_hash")
    _write_object(target / "research/canonical-package-proof.json", package_manifest)
    return {
        "status": "PASSED",
        "run_id": bundle["run_id"],
        "consumability": bundle["consumability"],
        "status_projection": project_research_status(
            [*dimension_reports, *imported_equity_reports], coverage=coverage,
        ),
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
    from product.council.multidimensional_output import project_research_status

    del repository_root
    run_dir = Path(run_dir).resolve()
    manifest = _read_frozen_object(run_dir, "run_manifest.json")
    if manifest.get("stage") not in {
        "MULTI_DIMENSIONAL_HOLDING_RESEARCH", "INDEPENDENT_COUNTER_THESIS_RESEARCH",
    }:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_CONSUMER_STAGE_INVALID")
    bundle_path = run_dir / "research/holding-research-bundle.json"
    gate_path = run_dir / "evidence/gate.json"
    bundle = _read_frozen_object(run_dir, "research/holding-research-bundle.json")
    gate = _read_frozen_object(run_dir, "evidence/gate.json")
    if (gate.get("bundle_hash") != legacy_envelope_hash(gate, hash_field="bundle_hash") or gate.get("decision_cutoff") != bundle.get("decision_cutoff")
            or gate.get("run_id") != bundle.get("run_id")
            or manifest.get("gate_hash") != gate.get("bundle_hash")):
        raise MultidimensionalStageError("MULTIDIMENSIONAL_CONSUMER_GATE_INVALID")
    allowed_evidence_ids = set(gate.get("allowed_evidence_ids", []))
    common_ids = bundle.get("common_stock_security_ids", [])
    dimension_reports: list[dict[str, Any]] = []
    equity_reports: list[dict[str, Any]] = []
    inventory = []
    loaded: list[tuple[Mapping[str, Any], dict[str, Any], Path]] = []
    for reference in bundle.get("report_refs", []):
        relative = reference.get("artifact_ref")
        if not isinstance(relative, str) or not relative:
            raise MultidimensionalStageError("MULTIDIMENSIONAL_CONSUMER_REPORT_PATH_INVALID")
        path = _resolve_frozen_artifact(run_dir, relative)
        report = _read_object(path)
        loaded.append((reference, report, path))
    all_claim_ids = known_claim_references([
        {**report, "report_hash": report.get("report_hash", canonical_hash(report))}
        for _, report, _ in loaded
    ])
    for reference, report, path in loaded:
        report_type = reference.get("report_type")
        if report_type == "RESEARCH_DIMENSION_REPORT":
            validate_breadth_calculation_references(run_dir, report)
            from product.runtime.research_submission import selected_calculations_for_report
            selected_calculations_for_report(run_dir, report, for_execution=False)
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
        _resolve_frozen_artifact(run_dir, relative)
    process_path = run_dir / "invocation/process-result.json"
    process = _read_frozen_object(run_dir, "invocation/process-result.json") if process_path.exists() else None
    if process is not None and process.get("run_id") != bundle["run_id"]:
        raise MultidimensionalStageError("MULTIDIMENSIONAL_CONSUMER_PROCESS_BINDING_INVALID")
    status = project_research_status(
        [*dimension_reports, *equity_reports], coverage=bundle["coverage"], process=process,
    )
    proof = {
        "schema_version": "holding-research-consumption-proof/1.0.0",
        "status": "PASSED", "run_id": bundle["run_id"],
        "structural_status": "STRUCTURALLY_CONSUMABLE",
        "downstream_status": status["downstream_status"],
        "declared_downstream_status": bundle.get("consumability", "STRUCTURALLY_CONSUMABLE"),
        "status_projection": status,
        "process_file_hash": file_hash(process_path) if process is not None else None,
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
    proof["proof_hash"] = legacy_envelope_hash(proof, hash_field="proof_hash")
    if persist:
        destination = run_dir / "research/consumption-proof.json"
        if destination.exists():
            raise MultidimensionalStageError("MULTIDIMENSIONAL_CONSUMER_PROOF_EXISTS")
        _write_object(destination, proof)
    return proof


def launch_multidimensional_stage(
    repository_root: Path, *, run_dir: Path, codex_binary: str = "codex",
    timeout_seconds: int = 2400, task_name: str | None = None,
    initial_task: bool = False,
) -> tuple[dict[str, Any], int]:
    """旧正常模型启动已退役；历史读取不依赖此入口。"""
    raise MultidimensionalStageError("NATIVE_HOST_EXECUTION_REQUIRED:使用当前宿主portfolio-council原生会话；旧执行维护仅限明确批准的冻结版本。")


def _industry_source_identity_copy_paths(task: Mapping[str, Any], draft: Mapping[str, Any]) -> list[str]:
    if task.get("industry_source_boundary") != "industry-source-boundary/1.0.0":
        return []
    claims = draft.get("claims")
    if not isinstance(claims, list):
        return []
    return [
        f"claims[{index}].statement"
        for index, claim in enumerate(claims)
        if isinstance(claim, Mapping) and isinstance(claim.get("statement"), str)
        and re.search(r"\b(?:source_id|as_of|retrieved_at)\s*=", claim["statement"])
    ]


_SOURCE_LITERAL_VERSION = "source-literal-selection/1.0.0"
_MACRO_SOURCE_LITERAL_VERSION = "source-literal-selection/1.1.0"
_SOURCE_LITERAL_PLACEHOLDER = re.compile(r"\{\{sf\.[A-Za-z][A-Za-z0-9_]{0,23}\}\}")


def _macro_observation_literal(fact: Mapping[str, Any]) -> str:
    """呈现显式选中记录的原角色和时间；不换算、补缺或选择观察期。"""
    raw = fact.get("value")
    if (not isinstance(raw, Mapping) or fact.get("dataset") != "macro_history"
            or fact.get("source_family") != "moomoo_sg"
            or fact.get("source_type") != "SECONDARY_VENDOR"
            or fact.get("security_id") != "US:MARKET"
            or type(raw.get("indicator_id")) is not int
            or fact.get("source_id") != f"moomoo-sg-opend-macro:{raw['indicator_id']}"
            or raw.get("vintage_status") != "CURRENT_VENDOR_SNAPSHOT"):
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    values = {}
    for key in ("actual", "previous", "consensus"):
        if key not in raw:
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        value = raw[key]
        if value is None:
            values[key] = "null（原缺失）"
        elif value == "N/A":
            values[key] = "N/A"
        else:
            if type(value) not in {str, int, float} or len(str(value)) > 128:
                raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
            try:
                if not Decimal(str(value)).is_finite():
                    raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
            except InvalidOperation:
                raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID") from None
            values[key] = str(value)
    for key in ("label", "unit_type", "raw_release_time"):
        if (not isinstance(raw.get(key), str) or not raw[key].strip()
                or len(raw[key]) > 128 or any(ord(c) < 32 for c in raw[key])
                or "{{sf." in raw[key]):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    try:
        # 只验证供应商标签的日期形状；没有时区证明，不据此创造UTC时点。
        datetime.fromisoformat(raw["raw_release_time"])
    except ValueError:
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID") from None
    return (
        f"【{raw['label']}；观察期(as_of)={fact['as_of']}；"
        f"actual(原值)={values['actual']}；previous(原值)={values['previous']}；"
        f"consensus(原值)={values['consensus']}；unit_type(原标签)={raw['unit_type']}；"
        f"raw_release_time(供应商原标签，时区未核实)={raw['raw_release_time']}；"
        "vintage_status=CURRENT_VENDOR_SNAPSHOT，历史vintage未核实】"
    )


def _bind_source_literal_selections(
    draft: Mapping[str, Any], *, task: Mapping[str, Any], run_dir: Path,
    reference_map: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Fill only explicitly selected source scalars in task-local draft statements."""

    result = dict(draft)
    had_selections = "source_literal_selections" in result
    selections = result.pop("source_literal_selections", None)
    version = task.get("source_literal_selection")
    if version not in {_SOURCE_LITERAL_VERSION, _MACRO_SOURCE_LITERAL_VERSION}:
        if had_selections or "{{sf." in json.dumps(result, ensure_ascii=False):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        return result
    macro = version == _MACRO_SOURCE_LITERAL_VERSION
    if ((macro and (task.get("capability") != "MACRO_CONTEXT"
                    or task.get("tool_identity_version") != "research-tool-identity/1.0.0"))
            or (not macro and task.get("capability") not in {"FUNDAMENTAL_EVENT", "OPTIONS_FLOW"})):
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    if selections is None:
        selections = []
    if not isinstance(selections, list) or len(selections) > 16:
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    claims = result.get("claims")
    if not isinstance(claims, list):
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    claims = [dict(claim) if isinstance(claim, dict) else claim for claim in claims]
    result["claims"] = claims
    by_id = {c.get("claim_id"): c for c in claims if isinstance(c, dict) and isinstance(c.get("claim_id"), str)}
    if len(by_id) != len(claims):
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    if not selections:
        if "{{sf." in json.dumps(result, ensure_ascii=False):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        return result
    gate = json.loads((run_dir / "evidence/gate.json").read_text(encoding="utf-8"))
    if gate.get("bundle_hash") != legacy_envelope_hash(gate, hash_field="bundle_hash"):
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    allowed = set(task.get("allowed_evidence_ids", []))
    facts = {f["evidence_id"]: f for f in gate.get("allowed_evidence", [])
             if isinstance(f, dict) and f.get("evidence_id") in allowed}
    queried: set[str] = set()
    events_path = run_dir / "events/mcp/events.jsonl"
    if not events_path.is_file() or events_path.is_symlink():
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if (event.get("event_type") == "mcp_tool_result"
                and event.get("tool") in {"fixture_evidence.query", "live_evidence.query"}
                and event.get("access_mode") == "read"
                and all(event.get(k) == task.get(k) for k in ("run_id", "invocation_id", "agent"))
                and event.get("event_hash") == legacy_envelope_hash(event, hash_field="event_hash")):
            queried.update(x for x in event.get("evidence_ids", []) if isinstance(x, str))
    aliases = (reference_map or {}).get("evidence", {})
    seen: set[str] = set()
    replacements: dict[str, tuple[str, str]] = {}
    for selection in selections:
        if (not isinstance(selection, dict)
                or set(selection) != {"claim_id", "placeholder", "evidence_ref", "field"}):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        claim_id, marker, ref, field = (selection[k] for k in ("claim_id", "placeholder", "evidence_ref", "field"))
        claim = by_id.get(claim_id)
        if (not isinstance(marker, str) or not _SOURCE_LITERAL_PLACEHOLDER.fullmatch(marker)
                or marker in seen or not isinstance(ref, str) or not isinstance(field, str)
                or not isinstance(claim, dict) or not isinstance(claim.get("statement"), str)):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        seen.add(marker)
        evidence_id = aliases.get(ref, ref)
        cited = claim.get("evidence_refs", [])
        if (evidence_id not in facts or evidence_id not in queried
                or not isinstance(cited, list)
                or evidence_id not in {aliases.get(item, item) for item in cited if isinstance(item, str)}
                or (not macro and facts[evidence_id].get("security_id") not in task.get("security_ids", []))):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        fact = facts[evidence_id]
        if macro:
            if field != "moomoo_macro_observation":
                raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
            literal = _macro_observation_literal(fact)
        elif task["capability"] == "FUNDAMENTAL_EVENT":
            raw = fact.get("value")
            if (field != "sec_usd_value" or fact.get("source_type") != "sec"
                    or fact.get("unit") != "USD" or not isinstance(raw, str)
                    or len(raw) > 128 or re.fullmatch(r"-?\d+", raw) is None):
                raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
            literal = raw + " USD"
        else:
            if (field not in {"as_of", "retrieved_at"}
                    or fact.get("dataset") != "options_snapshot"
                    or not str(fact.get("semantic_field", "")).startswith((
                        "moomoo_option_quote:", "option_chain_contract:",
                    ))):
                raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
            raw = fact.get(field)
            if not isinstance(raw, str) or len(raw) > 64 or not raw.endswith("Z"):
                raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
            literal = field + "=" + raw
        try:
            if not str(fact["as_of"]).endswith("Z") or not str(gate["decision_cutoff"]).endswith("Z"):
                raise ValueError
            as_of = datetime.fromisoformat(str(fact["as_of"]).replace("Z", "+00:00"))
            cutoff = datetime.fromisoformat(str(gate["decision_cutoff"]).replace("Z", "+00:00"))
            if as_of > cutoff or (field in {"as_of", "retrieved_at"} and datetime.fromisoformat(raw.replace("Z", "+00:00")).tzinfo is None):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID") from None
        if claim["statement"].count(marker) != 1:
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        if field == "sec_usd_value" and re.match(
            r"\s*USD\b", claim["statement"].split(marker, 1)[1], flags=re.IGNORECASE,
        ):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        replacements[marker] = (claim_id, literal)
    # No placeholder may occur in metadata, another claim, or an undeclared location.
    for claim in claims:
        statement = claim["statement"]
        if "{{sf." in json.dumps({k: v for k, v in claim.items() if k != "statement"}, ensure_ascii=False):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        markers = _SOURCE_LITERAL_PLACEHOLDER.findall(statement)
        if "{{sf." in statement and statement.count("{{sf.") != len(markers):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        for marker in markers:
            if replacements.get(marker, (None,))[0] != claim["claim_id"]:
                raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
        for marker in markers:
            statement = statement.replace(marker, replacements[marker][1], 1)
        claim["statement"] = statement
    other = {k: v for k, v in result.items() if k != "claims"}
    if "{{sf." in json.dumps(other, ensure_ascii=False):
        raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    return result


def _read_multidimensional_report_artifact(value, record, *, task, invocation, reference_packet, run_dir):
    """从明确版本的草稿/回执读取正式对象；无目录创建、发布或执行准入。

    冻结任务和显式协议只证明业务绑定；本函数不认证宿主、作者或实际执行。
    历史读取检查同一业务约束，不生成执行事件或重写历史报告。
    """
    from product.runtime.multidimensional_references import translate_references
    from product.runtime.calculation_handoff import (
        validate_semantic_selection_draft, validate_tool_calculations,
        _validate_multidimensional_calculation_structure,
    )
    from product.runtime.monetary import research_report_monetary_findings
    if task.get("source_literal_selection"):
        frozen_task = json.loads((run_dir / task["task_path"]).read_text(encoding="utf-8"))
        if (reference_packet.get("task") != frozen_task
                or {k: v for k, v in task.items() if k not in {
                    "task_path", "invocation_path", "packet_path", "packet_hash",
                }} != frozen_task
                or frozen_task.get("task_hash") != legacy_envelope_hash(frozen_task, hash_field="task_hash")):
            raise ValueError("DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
    reference_map = reference_packet.get("reference_map")
    # 身份已由可信 Start/任务绑定校验；只剥离程序装配的身份后检查原稿。
    # MCP resolve 已按冻结提交版本核验原稿/事件并完成选择装配；它的返回值
    # 是正式字段，不是第二份模型草稿。非 MCP 原稿则必须完整检查选择结构。
    from product.runtime.research_submission import ASSEMBLY_VERSIONS
    assembled_submission = record.get("submission_binding", {}).get("version")
    if assembled_submission not in ASSEMBLY_VERSIONS:
        validate_semantic_selection_draft(
            {key: item for key, item in value.items() if key not in {"run_id", "invocation_id", "agent"}},
            reference_packet,
        )
    elif assembled_submission != task.get("submission_version"):
        raise ValueError("RESEARCH_SUBMISSION_BINDING_INVALID")
    if "document_selections" in value:
        from product.runtime.research_submission import _selected_documents
        documents = _selected_documents(value, reference_packet, value["document_selections"])
        value = {key: item for key, item in value.items() if key != "document_selections"}
        value["documents"] = documents
    from product.runtime.calculation_handoff import assemble_calculation_selections
    value = assemble_calculation_selections(run_dir, reference_packet, value)
    value = _bind_source_literal_selections(
        value, task=task, run_dir=run_dir, reference_map=reference_map,
    )
    if reference_map is not None:
        value = translate_references(value, reference_map, local_claims={
            c["claim_id"] for c in value.get("claims", [])
            if isinstance(c, Mapping) and isinstance(c.get("claim_id"), str)
        })
    _validate_multidimensional_calculation_structure(value, packet=reference_packet)
    if _industry_source_identity_copy_paths(task, value):
        raise ValueError("DIMENSION_REPORT_SOURCE_IDENTITY_IN_PROSE")
    artifact_refs = value.get("artifact_refs")
    if (
        not isinstance(artifact_refs, list)
        or not set(artifact_refs) <= set(task.get("allowed_artifact_refs", []))
    ):
        raise ValueError("MULTIDIMENSIONAL_OUTPUT_ARTIFACT_REF_INVALID")
    validate_tool_calculations(
        value, task=task, invocation=invocation, run_dir=run_dir,
    )
    validate_breadth_calculation_references(run_dir, value)
    from product.runtime.research_input import load_research_input, research_input_binding, research_subjects
    handoff = load_research_input(run_dir)
    council_request = json.loads((run_dir / "council-request.json").read_text(encoding="utf-8"))
    gate = json.loads((run_dir / "evidence/gate.json").read_text(encoding="utf-8"))
    from product.runtime.research_submission import selected_calculation_outputs
    selected_upstream = selected_calculation_outputs(
        run_dir, record.get("upstream_calculation_selections", []),
    )
    if research_report_monetary_findings(
        value, task=task, gate=gate, reference_packet=reference_packet,
        selected_upstream=selected_upstream,
    ):
        raise ValueError("DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED")
    bindings = {
        **research_input_binding(handoff), "council_request_id": council_request["request_id"],
        "council_request_hash": council_request["request_hash"], "decision_cutoff": gate["decision_cutoff"],
    }
    dependency_claim_ids = []
    for dependency_id in task.get("depends_on", []):
        dependency_matches = []
        for path in (run_dir / "research/reports").glob("*/dimension-report.json"):
            dependency = json.loads(path.read_text(encoding="utf-8"))
            if dependency.get("report_id") == f"dimension-report:{dependency_id}":
                dependency_matches.append(dependency)
        if len(dependency_matches) != 1:
            raise ValueError("MULTIDIMENSIONAL_DEPENDENCY_REPORT_MISSING")
        from product.runtime.multidimensional_references import known_claim_references, VERSION
        dependency_claim_ids.extend(known_claim_references(
            dependency_matches,
            allow_legacy=not reference_map or reference_map["binding"]["version"] != VERSION,
        ))
    report = __import__(
        "product.council.multidimensional_research", fromlist=["envelope_research_dimension_draft"]
    ).envelope_research_dimension_draft(
        value, task=task, invocation=invocation, expected_bindings=bindings,
        allowed_security_ids=[
            item["security_id"] for item in research_subjects(handoff)
            if item["asset_type"] == "COMMON_STOCK"
        ],
        allowed_evidence_ids=task["allowed_evidence_ids"],
        allowed_calculation_evidence_ids=task.get("allowed_calculation_evidence_ids", []),
        known_research_claim_ids=dependency_claim_ids,
        allowed_documents=task.get("allowed_documents", []),
    )
    evidence = [
        item for item in gate["allowed_evidence"]
        if item["evidence_id"] in set(task["allowed_evidence_ids"])
    ]
    return report, evidence, selected_upstream
