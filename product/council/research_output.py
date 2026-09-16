"""Persist and render common-stock research artifacts without adding judgment."""

from __future__ import annotations

import copy
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote, urlsplit

from product.mcp.provenance import parse_timestamp
from product.runtime.hashing import canonical_hash

from .common_stock_research import (
    SECTION_NAMES,
    CommonStockResearchError,
    validate_equity_research_report,
)


SECTION_TITLES = {
    "company_and_core_questions": "公司与核心问题",
    "business_competition_financials": "业务、竞争和财务",
    "thesis_and_valuation": "Thesis 与估值",
    "catalysts_and_counterevidence": "催化剂和反证",
    "invalidation_and_monitoring": "失效条件与观察指标",
    "gaps_and_confidence": "数据缺口和置信度理由",
}


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    if path.exists():
        raise CommonStockResearchError(f"RESEARCH_ARTIFACT_EXISTS:{path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _evidence_index(
    evidence: Sequence[Mapping[str, Any]], *, cutoff: str
) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    cutoff_time = parse_timestamp(cutoff)
    for item in evidence:
        evidence_id = item.get("evidence_id")
        if not isinstance(evidence_id, str) or evidence_id in result:
            raise CommonStockResearchError("RESEARCH_RENDER_EVIDENCE_ID_INVALID")
        for field in ("source_id", "as_of", "retrieved_at"):
            if not isinstance(item.get(field), str) or not item[field]:
                raise CommonStockResearchError(
                    f"RESEARCH_RENDER_PROVENANCE_MISSING:{evidence_id}:{field}"
                )
        if (
            parse_timestamp(item["as_of"]) > cutoff_time
            or parse_timestamp(item["retrieved_at"]) > cutoff_time
        ):
            raise CommonStockResearchError(f"RESEARCH_RENDER_PIT_LEAKAGE:{evidence_id}")
        result[evidence_id] = item
    return result


def _mentioned_dates(text: str) -> set[str]:
    """提取报告文字显式写出的 ISO/中文日期，并统一为 ISO 日期。"""

    result = set(re.findall(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)", text))
    for year, month, day in re.findall(
        r"(?<!\d)(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", text
    ):
        try:
            result.add(date(int(year), int(month), int(day)).isoformat())
        except ValueError:
            continue
    return result


def _validate_fact_period_lineage(
    report: Mapping[str, Any], *, evidence_by_id: Mapping[str, Mapping[str, Any]]
) -> None:
    """只验证 FACT 主张引用的不同流量期间是否在文字中逐项保留。"""

    for claim in report["claims"]:
        if claim["kind"] != "FACT":
            continue
        periods: set[tuple[str | None, str | None]] = set()
        for evidence_id in claim["evidence_refs"]:
            item = evidence_by_id[evidence_id]
            metadata = item.get("metadata")
            if not isinstance(metadata, Mapping):
                continue
            period_start = metadata.get("period_start")
            period_end = metadata.get("period_end")
            if metadata.get("context_type") != "duration" and period_start is None:
                continue
            periods.add((period_start, period_end))
        if len(periods) <= 1:
            continue
        mentioned = _mentioned_dates(claim["statement"])
        for value in sorted({value for period in periods for value in period if value is not None}):
            if value not in mentioned:
                raise CommonStockResearchError(
                    f"EQUITY_RESEARCH_FACT_PERIOD_LINEAGE_INCOMPLETE:"
                    f"{claim['claim_id']}:{value}"
                )


def render_equity_research_markdown(
    report: Mapping[str, Any], *, request: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]], calculation_artifact_ids: Sequence[str] = (),
) -> str:
    """Render only fields already present in the validated JSON report."""

    referenced = validate_equity_research_report(
        report, request=request, calculation_artifact_ids=calculation_artifact_ids
    )
    evidence_by_id = _evidence_index(evidence, cutoff=request["decision_cutoff"])
    if referenced - set(evidence_by_id):
        raise CommonStockResearchError("RESEARCH_RENDER_EVIDENCE_MISSING")
    _validate_fact_period_lineage(report, evidence_by_id=evidence_by_id)
    evidence_labels = {
        evidence_id: f"E{index}"
        for index, evidence_id in enumerate(sorted(referenced), start=1)
    }

    def render_evidence_refs(refs: Sequence[str]) -> str:
        return ", ".join(f"[{evidence_labels[ref]}]" for ref in refs) or "无"

    security = report["security"]
    lines = [
        f"# {security['display_symbol']} 普通股持仓研究",
        "",
        "> 本报告只完成公司研究，尚未形成完整组合动作、仓位建议或 Risk 结论。",
        "",
        f"- 证券：`{security['security_id']}`",
        f"- 研究状态：`{report['status']}`",
        f"- 资料截止：`{report['bindings']['decision_cutoff']}`",
        "- 置信度含义：当前资料对研究判断的支持程度，不是上涨或盈利概率。",
        "",
        "## 综合研究结论",
        "",
        report["research_summary"]["summary"],
        "",
        "关联主张：" + ", ".join(f"`{item}`" for item in report["research_summary"]["claim_refs"]),
        "主要失效条件：" + (", ".join(f"`{item}`" for item in report["research_summary"]["primary_invalidation_condition_ids"]) or "无"),
        "",
    ]
    claims = {item["claim_id"]: item for item in report["claims"]}
    gaps = {item["gap_id"]: item for item in report["data_gaps"]}
    displayed_claims: set[str] = set()

    def append_claim(claim_id: str) -> None:
        if claim_id in displayed_claims:
            lines.append(f"- 关联主张：`{claim_id}`（正文见前文，内容不重复）")
            return
        displayed_claims.add(claim_id)
        claim = claims[claim_id]
        lines.extend([
            f"- **{claim_id}**：{claim['statement']}",
            f"  - 类型：{'事实' if claim['kind'] == 'FACT' else '解释'}（`{claim['kind']}`）",
            f"  - Evidence：{render_evidence_refs(claim['evidence_refs'])}",
            f"  - 假设：{', '.join(f'`{item}`' for item in claim['assumption_ids']) or '无'}",
            f"  - 计算：{', '.join(f'`{item}`' for item in claim['calculation_refs']) or '无'}",
            f"  - 反证主张：{', '.join(f'`{item}`' for item in claim['counter_claim_refs']) or '无'}",
            f"  - 失效条件：{', '.join(f'`{item}`' for item in claim['invalidation_condition_ids']) or '无'}",
        ])

    for name in SECTION_NAMES:
        section = report["sections"][name]
        lines.extend([f"## {SECTION_TITLES[name]}", "", f"状态：`{section['status']}`", "", section["narrative"], ""])
        for claim_id in section["claim_refs"]:
            append_claim(claim_id)
        for gap_id in section["data_gap_ids"]:
            gap = gaps[gap_id]
            reason = f"；原因：`{gap['reason_code']}`" if gap.get("reason_code") else ""
            lines.append(f"- **资料缺口 {gap_id}**：{gap['description']}；影响：{gap['impact']}{reason}")
        lines.append("")
    remaining = [claim_id for claim_id in claims if claim_id not in displayed_claims]
    if remaining:
        lines.extend(["## 补充主张", ""])
        for claim_id in remaining:
            append_claim(claim_id)
        lines.append("")
    lines.extend(["## 显式假设（并非已证实事实）", ""])
    for item in report["assumptions"]:
        lines.extend([
            f"- **{item['assumption_id']}**：{item['statement']}",
            f"  - 理由：{item['rationale']}",
            f"  - Evidence：{render_evidence_refs(item['evidence_refs'])}",
        ])
    if not report["assumptions"]:
        lines.append("未列出显式假设。")
    lines.append("")
    def append_relations(item: Mapping[str, Any]) -> None:
        for label, key in (("关联主张", "claim_refs"), ("Evidence", "evidence_refs")):
            if key in item:
                rendered = (
                    render_evidence_refs(item[key])
                    if key == "evidence_refs"
                    else ", ".join(f"`{ref}`" for ref in item[key]) or "无"
                )
                lines.append(f"  - {label}：{rendered}")

    lines.extend(["## 失效条件", ""])
    for item in report["invalidation_conditions"]:
        lines.append(f"- **{item['condition_id']}**：{item['description']}；观察信号：{item['monitoring_signal']}")
        append_relations(item)
    lines.extend(["", "## 重评触发", ""])
    for item in report["reevaluation_triggers"]:
        lines.append(f"- **{item['trigger_id']}**：{item['description']}")
        append_relations(item)
    lines.extend(["", "## 持续观察指标", ""])
    for item in report["monitoring_indicators"]:
        context = []
        for label, key in (
            ("基线", "baseline"), ("单位", "unit"),
            ("期间", "comparison_period"), ("重评方式", "reevaluation_rule"),
        ):
            if key in item:
                context.append(f"{label}：{item[key] if item[key] is not None else '未知'}")
        suffix = ("；" + "；".join(context)) if context else ""
        lines.append(
            f"- **{item['indicator_id']}**：{item['description']}；原因：{item['why_it_matters']}{suffix}"
        )
        append_relations(item)
    lines.extend([
        "", "## 置信度", "", f"- 数值：`{report['confidence']}`",
        f"- 理由：{report['confidence_rationale']}", "", "## Evidence 来源与时间", "",
    ])
    for evidence_id in sorted(referenced):
        item = evidence_by_id[evidence_id]
        metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
        lines.append(
            f"- **[{evidence_labels[evidence_id]}]** `{evidence_id}` — "
            f"source_id=`{item['source_id']}`；as_of=`{item['as_of']}`；"
            f"retrieved_at=`{item['retrieved_at']}`"
        )
        for label, value in (
            ("期间开始", metadata.get("period_start")),
            ("期间结束", metadata.get("period_end")),
            ("数据类型", metadata.get("context_type")),
            ("单位", item.get("unit") or metadata.get("unit")),
            ("发布时间", item.get("published_at") or metadata.get("published_at")),
        ):
            lines.append(f"  - {label}：{value if value is not None else '未知'}")
        locator = item.get("source_locator") or metadata.get("source_locator")
        try:
            parsed = urlsplit(locator) if isinstance(locator, str) else None
            link_available = parsed is not None and parsed.scheme in ("https", "http") and bool(parsed.hostname)
        except ValueError:
            link_available = False
        if link_available:
            url = quote(locator, safe=":/?#[]@!$&'*+,;=%")
            lines.append(f"  - 来源：[原始资料](<{url}>)")
        else:
            lines.append("  - 来源链接：未提供可用 HTTP(S) 地址；可按上述 source_id 查询冻结资料。")
    return "\n".join(lines).rstrip() + "\n"


def persist_equity_research_report(
    output_root: Path, *, report: Mapping[str, Any], request: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]], calculation_artifact_ids: Sequence[str] = (),
) -> dict[str, str]:
    """Persist validated JSON and its same-source Chinese rendering."""

    security_id = report.get("security", {}).get("security_id")
    if not isinstance(security_id, str) or not security_id:
        raise CommonStockResearchError("RESEARCH_OUTPUT_SECURITY_ID_INVALID")
    directory = Path(output_root).resolve() / security_id.replace(":", "_")
    if directory.exists():
        raise CommonStockResearchError("RESEARCH_OUTPUT_DIRECTORY_EXISTS")
    markdown = render_equity_research_markdown(
        report, request=request, evidence=evidence,
        calculation_artifact_ids=calculation_artifact_ids,
    )
    json_path = directory / "equity-research.json"
    markdown_path = directory / "equity-research.md"
    _write_json(json_path, copy.deepcopy(dict(report)))
    markdown_path.write_text(markdown, encoding="utf-8")
    validate_persisted_equity_research_pair(
        json_path=json_path, markdown_path=markdown_path, request=request,
        evidence=evidence, calculation_artifact_ids=calculation_artifact_ids,
    )
    return {
        "json": str(json_path), "markdown": str(markdown_path),
        "json_hash": canonical_hash(report),
        "markdown_hash": canonical_hash({"text": markdown}),
    }


def validate_persisted_equity_research_pair(
    *, json_path: Path, markdown_path: Path, request: Mapping[str, Any],
    evidence: Sequence[Mapping[str, Any]], calculation_artifact_ids: Sequence[str] = (),
) -> dict[str, str]:
    """重读落盘文件，证明 Markdown 只由同一份合法 JSON 渲染。"""

    try:
        report = json.loads(Path(json_path).read_text(encoding="utf-8"))
        actual_markdown = Path(markdown_path).read_text(encoding="utf-8")
    except (OSError, json.JSONDecodeError) as exc:
        raise CommonStockResearchError("RESEARCH_OUTPUT_PAIR_UNREADABLE") from exc
    expected_markdown = render_equity_research_markdown(
        report, request=request, evidence=evidence,
        calculation_artifact_ids=calculation_artifact_ids,
    )
    if actual_markdown != expected_markdown:
        raise CommonStockResearchError("RESEARCH_OUTPUT_MARKDOWN_MISMATCH")
    return {
        "json_hash": canonical_hash(report),
        "markdown_hash": canonical_hash({"text": actual_markdown}),
    }


def render_research_progress(coverage: Mapping[str, Any]) -> str:
    """Render Chinese progress while keeping execution, research, eval and coverage separate."""

    items = coverage["items"]
    counts = {
        status: sum(item["execution_status"] == status for item in items)
        for status in ("QUEUED", "RUNNING", "COMPLETED", "FAILED", "TIMEOUT", "CANCELLED", "NOT_STARTED")
    }
    lines = [
        "# 普通股持仓研究进度", "",
        f"- 全部持仓：{len(items)}",
        f"- 排队：{counts['QUEUED']}",
        f"- 运行中：{counts['RUNNING']}",
        f"- 已完成：{counts['COMPLETED']}",
        f"- 失败/超时/取消：{counts['FAILED'] + counts['TIMEOUT'] + counts['CANCELLED']}",
        f"- 未启动或未覆盖：{counts['NOT_STARTED']}",
        f"- 阶段状态：`{coverage['stage_status']}`（不代表完整组合决策）", "",
    ]
    for item in items:
        lines.extend([
            f"## {item['security_id']}", "",
            f"- 执行状态：`{item['execution_status']}`",
            f"- 研究状态：`{item['research_status']}`",
            f"- Eval 状态：`{item['eval_status']}`",
            f"- 覆盖状态：`{item['coverage_status']}`",
            f"- 报告：{item['report_ref'] or '尚无'}",
            f"- 报告 hash：{item.get('report_hash') or '尚无'}",
            f"- Eval 产物：{item.get('eval_ref') or '未运行'}",
            f"- 失败原因：{item['failure_code'] or '无'}", "",
        ])
    return "\n".join(lines)
