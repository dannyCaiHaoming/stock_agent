"""多维研究 JSON 的同源中文渲染；不增加或修改研究判断。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from product.runtime.hashing import canonical_hash
from product.runtime.validation import collect_evidence_refs


def render_dimension_report_markdown(
    report: Mapping[str, Any], *, evidence: Sequence[Mapping[str, Any]]
) -> str:
    by_id = {str(item["evidence_id"]): item for item in evidence}
    refs = collect_evidence_refs(report)
    if refs - set(by_id):
        raise ValueError("DIMENSION_MARKDOWN_EVIDENCE_DANGLING")
    lines = [
        f"# {report['capability']} 研究报告",
        "",
        f"- 报告：`{report['report_id']}`",
        f"- 证券：{', '.join(report['security_ids']) or '共享市场'}",
        f"- 状态：`{report['status']}` / 充分程度：`{report['sufficiency']}` / 评价：`{report['evaluation_status']}`",
        f"- 截止时间：{report['bindings']['decision_cutoff']}",
        f"- Agent / Skill / Model：`{report['execution']['agent_name']}` / `{report['execution']['skill_name']}` / `{report['execution']['model']}`",
        "",
        "## 摘要",
        "",
        str(report["summary"]),
        "",
        "## 主张与依据",
        "",
    ]
    if not report["claims"]:
        lines.append("- 当前没有可成立的研究主张。")
    for claim in report["claims"]:
        lines.extend([
            f"### {claim['claim_id']}：{claim['question']}",
            "",
            str(claim["statement"]),
            "",
            f"- 类型：`{claim['kind']}`",
            f"- Evidence：{', '.join(f'`{item}`' for item in claim['evidence_refs']) or '无'}",
            f"- 派生主张：{', '.join(f'`{item}`' for item in claim['research_claim_refs']) or '无'}",
            f"- 文档：{', '.join(f'`{item}`' for item in claim['document_refs']) or '无'}",
            f"- 假设：{', '.join(f'`{item}`' for item in claim['assumption_ids']) or '无'}",
            f"- 计算：{', '.join(f'`{item}`' for item in claim['calculation_refs']) or '无'}",
            "",
        ])
    lines.extend(["## 假设与计算", ""])
    lines.extend(
        f"- 假设 `{item['assumption_id']}`：{item['statement']}；依据：{item['rationale']}"
        for item in report["assumptions"]
    )
    lines.extend(
        f"- 计算 `{item['calculation_id']}`：{item['method']} = {item['value']} {item['unit'] or ''}（产物：`{item['artifact_ref']}`）"
        for item in report["calculations"]
    )
    if not report["assumptions"] and not report["calculations"]:
        lines.append("- 未记录额外假设或计算。")
    lines.extend(["", "## 研报文档与观点关系", ""])
    for item in report["documents"]:
        lines.extend([
            f"### `{item['document_id']}` {item['title']}", "",
            f"- 类型 / 核实：`{item['material_type']}` / `{item['verification_status']}`",
            f"- 作者 / 机构：{', '.join(item['authors']) or '未披露'} / {item['institution'] or '未知'}",
            f"- published_at / as_of / retrieved_at：{item['published_at']} / {item['as_of']} / {item['retrieved_at']}",
            f"- 定位：{', '.join(item['locations']) or '未提供'}；解析范围：{item['parse_scope']}",
            f"- 来源：{item['source_url']}",
            f"- 利益披露：`{item['interest_disclosure']['status']}` — {item['interest_disclosure']['statement'] or '未取得'}",
            "",
        ])
    for item in report["research_relationships"]:
        lines.append(
            f"- `{item['relationship_id']}` `{item['effect']}`：{item['rationale']}"
            f"（文档：`{item['document_id']}`；目标：{', '.join(item['target_claim_refs'])}；结果：{', '.join(item['resulting_claim_refs']) or '无'}）"
        )
    if not report["documents"] and not report["research_relationships"]:
        lines.append("- 本维度没有研报文档或观点关系。")
    lines.extend(["", "## 限制与资料缺口", ""])
    lines.extend(f"- 限制：{item}" for item in report["limitations"])
    lines.extend(
        f"- `{item['gap_id']}` [{item['reason_code']}] {item['description']}；影响：{item['impact']}"
        for item in report["data_gaps"]
    )
    if not report["limitations"] and not report["data_gaps"]:
        lines.append("- 未记录额外限制或缺口。")
    lines.extend(["", "## 观察条件", ""])
    lines.extend(
        f"- `{item['condition_id']}` {item['description']}（关联：{', '.join(item['claim_refs']) or '无'}）"
        for item in report["observation_conditions"]
    )
    if not report["observation_conditions"]:
        lines.append("- 当前资料不足以定义可靠观察条件。")
    lines.extend(["", "## Evidence 附录", ""])
    for evidence_id in sorted(refs):
        item = by_id[evidence_id]
        lines.extend([
            f"### `{evidence_id}`",
            "",
            f"- source_id：`{item['source_id']}`",
            f"- as_of：{item['as_of']}",
            f"- retrieved_at：{item['retrieved_at']}",
            f"- semantic_field：`{item.get('semantic_field', 'UNKNOWN')}`",
            "",
        ])
    lines.extend([
        "## 边界声明",
        "",
        "本报告是研究资料，不是组合动作或交易指令；不同维度的冲突由后续专业 Agent 处理。",
        "",
    ])
    return "\n".join(lines)


def render_holding_research_bundle_markdown(
    bundle: Mapping[str, Any], *,
    dimension_reports: Sequence[Mapping[str, Any]] = (),
    equity_reports: Sequence[Mapping[str, Any]] = (),
) -> str:
    reports_by_id = {
        str(report["report_id"]): report
        for report in (*dimension_reports, *equity_reports)
    }
    lines = [
        "# 多维持仓研究包",
        "",
        str(bundle["summary"]),
        "",
        f"- run_id：`{bundle['run_id']}`",
        f"- decision_cutoff：{bundle['decision_cutoff']}",
        f"- 普通股：{', '.join(bundle['common_stock_security_ids'])}",
        f"- 结构状态：`STRUCTURALLY_CONSUMABLE`",
        f"- 下游状态：`{bundle.get('consumability', 'STRUCTURALLY_CONSUMABLE')}`",
        "",
        "## 覆盖矩阵",
        "",
        "| 证券 | 维度 | 状态 | 报告/缺口 |",
        "|---|---|---|---|",
    ]
    for item in bundle["coverage"]:
        reference = item["report_id"] or item["gap_reason"] or "未说明"
        lines.append(f"| {item['security_id']} | {item['capability']} | {item['status']} | {reference} |")
    lines.extend(["", "## 已验证报告摘要", ""])
    seen_reports: set[str] = set()
    for item in bundle["coverage"]:
        report_id = item.get("report_id")
        if not isinstance(report_id, str) or report_id in seen_reports:
            continue
        report = reports_by_id.get(report_id)
        if report is None:
            continue
        seen_reports.add(report_id)
        lines.extend([
            f"### {item['capability']} · {', '.join(report.get('security_ids', [])) or item['security_id']}",
            "",
            f"- 报告：`{report_id}`",
            f"- 状态：`{report.get('status')}`",
            f"- 摘要：{report.get('summary', '未提供摘要。')}",
        ])
        claims = report.get("claims", [])
        if claims:
            lines.append("- 主张：")
            for claim in claims:
                refs = ", ".join(f"`{value}`" for value in claim.get("evidence_refs", [])) or "无原始 Evidence"
                lines.append(
                    f"  - `{claim.get('claim_id')}` {claim.get('statement')}（Evidence：{refs}）"
                )
        conditions = report.get("observation_conditions", [])
        if conditions:
            lines.append("- 观察条件：")
            lines.extend(
                f"  - `{condition.get('condition_id')}` {condition.get('description')}"
                for condition in conditions
            )
        gaps = report.get("data_gaps", [])
        if gaps:
            lines.append("- 资料缺口：")
            lines.extend(
                f"  - `{gap.get('gap_id')}` [{gap.get('reason_code')}] "
                f"{gap.get('description')}；影响：{gap.get('impact')}"
                for gap in gaps
            )
        lines.append("")
    missing_coverage = [item for item in bundle["coverage"] if item.get("report_id") is None]
    if missing_coverage:
        lines.extend(["## 未形成有效报告的维度", ""])
        lines.extend(
            f"- {item['security_id']} / {item['capability']}：{item.get('gap_reason') or '未说明原因'}"
            for item in missing_coverage
        )
    lines.extend(["", "## 尚未解决的跨维度问题", ""])
    if bundle["unresolved_cross_dimension_questions"]:
        for item in bundle["unresolved_cross_dimension_questions"]:
            lines.append(
                f"- `{item['question_id']}` {item['question']}（证券：{', '.join(item['security_ids'])}；"
                f"维度：{', '.join(item['capabilities'])}；"
                f"报告：{', '.join(item['report_refs'])}；"
                f"主张：{', '.join(item['claim_refs']) or '无'}）"
            )
    else:
        lines.append(f"- {bundle.get('no_unresolved_reason') or '未提供空值原因。'}")
    provenance = bundle.get("package_provenance")
    if isinstance(provenance, Mapping):
        lines.extend(["", "## 交接包来源", ""])
        lines.append(
            f"- 基础运行：`{provenance.get('base_run_id')}`；基础 Gate：`{provenance.get('base_gate_hash')}`"
        )
        lines.append(
            f"- 已重新验证公司报告：{len(provenance.get('company_research_imports', []))}"
        )
        lines.append(
            f"- 已纳入补证：{len(provenance.get('incorporated_supplements', []))}；"
            f"排除补证：{len(provenance.get('excluded_supplements', []))}"
        )
        for item in provenance.get("excluded_supplements", []):
            lines.append(
                f"  - `{item.get('report_id')}` 未纳入：{', '.join(item.get('reason_codes', []))}"
            )
    lines.extend([
        "",
        "## 边界声明",
        "",
        "本研究包仅归集已有研究，不生成统一分数、买卖动作或组合结论，也不代表 Skeptic、CIO 或 Risk 已运行。",
        "",
    ])
    return "\n".join(lines)


def persist_dimension_report(
    output_dir: Path, *, report: Mapping[str, Any], evidence: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "dimension-report.json"
    markdown_path = output_dir / "dimension-report.md"
    if json_path.exists() or markdown_path.exists():
        raise FileExistsError("DIMENSION_REPORT_OUTPUT_EXISTS")
    json_text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    markdown = render_dimension_report_markdown(report, evidence=evidence)
    json_path.write_text(json_text, encoding="utf-8")
    markdown_path.write_text(markdown, encoding="utf-8")
    return {
        "json": str(json_path), "markdown": str(markdown_path),
        "json_hash": canonical_hash(report),
        "markdown_hash": canonical_hash({"markdown": markdown}),
    }
