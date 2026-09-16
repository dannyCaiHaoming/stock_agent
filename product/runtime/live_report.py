"""中文 live 报告呈现；仅组织已有结构化结论，不生成投资判断。"""
from html import escape
import json
from pathlib import Path

from product.runtime.decision_contract import load_decision_contract, validate_decision_action
from product.runtime.validation import collect_evidence_refs, validate_evidence_closure


def _text(value) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    # 来源内容只作为文本展示，不能以 HTML 或 Markdown 图片触发外部内容。
    value = escape(value, quote=False)
    for marker in ("\\", "`", "*", "_", "[", "]", "#", "!"):
        value = value.replace(marker, "\\" + marker)
    return value


def render_live_report(decision: dict, *, gate: dict, reports: dict, holding_horizon: str,
                       portfolio: dict | None = None, snapshot: dict | None = None, calendar=None) -> str:
    if gate.get("source_mode") != "live" or decision.get("run_id") != gate.get("run_id"):
        raise ValueError("LIVE_REPORT_RUN_BINDING_MISMATCH")
    if len(decision.get("decisions", [])) != 1 or decision.get("advisory_only") is not True:
        raise ValueError("LIVE_REPORT_DECISION_INVALID")
    item = decision["decisions"][0]
    if item.get("action") not in ("HOLD", "TRIM", "EXIT", "NO_TRADE"):
        raise ValueError("LIVE_REPORT_ACTION_INVALID")
    validate_decision_action(item, load_decision_contract(Path(__file__).resolve().parents[1]))
    if not set(reports) <= {"runtime_company_analyst", "runtime_skeptic"}:
        raise ValueError("LIVE_REPORT_UNKNOWN_AGENT")
    for report in reports.values():
        if report.get("run_id") != decision["run_id"]:
            raise ValueError("LIVE_REPORT_SPECIALIST_RUN_MISMATCH")
    payload = {"decision": decision, "reports": reports}
    validate_evidence_closure(payload, allowed_evidence_ids=gate["allowed_evidence_ids"])
    facts = {f["evidence_id"]: f for f in gate["allowed_evidence"]}
    refs = set(collect_evidence_refs(payload))
    valuation, valuation_gap = None, None
    if portfolio is not None or snapshot is not None:
        if portfolio is None or snapshot is None:
            raise ValueError("LIVE_REPORT_PORTFOLIO_CONTEXT_INCOMPLETE")
        from product.runtime.live_input import value_portfolio
        try:
            valuation = value_portfolio(portfolio, snapshot, gate, calendar=calendar)
        except ValueError as exc:
            if not str(exc).startswith("LIVE_PRICE_MISSING:"):
                raise
            valuation_gap = str(exc)
        if valuation is not None:
            refs.update(row["price_evidence_id"] for row in valuation["positions"])
    pending = list(refs)
    while pending:
        fact = facts.get(pending.pop())
        if fact is None:
            raise ValueError("LIVE_REPORT_EVIDENCE_MISSING")
        for parent in fact.get("parent_ids", []):
            if parent not in refs:
                refs.add(parent)
                pending.append(parent)
    lines = ["# 美股持仓研究建议", "", "仅供研究建议；使用非实时资料，不连接券商，不执行下单。",
             "每股建议基于同一完整组合，未假设其他建议已成交，也不代表联合交易计划。", "",
             f"- 运行：{_text(decision['run_id'])}", f"- 资料截止：{_text(gate['decision_cutoff'])}",
             f"- 持有期限：{_text(holding_horizon)}", f"- 终态：{_text(decision['terminal_state'])}",
             f"- 建议：{_text(item['action'])}", f"- Risk：{_text(decision['risk_report']['status'])}", ""]

    def section(title, values):
        lines.extend([f"## {title}", ""])
        lines.extend([f"- {_text(value)}" for value in values] or ["- 本次结构化产物未提供此项。"])
        lines.append("")

    if portfolio is not None:
        if snapshot.get("schema_version") == "live-snapshot/4.0.0":
            section("数据访问范围与未核实限制", [
                f"{a['provider']}：个人研究批准={a['operator_approval']['status']}；"
                f"上游许可={a['upstream_permission']['status']}；"
                f"批准记录 hash={a['operator_approval']['record_hash']}；"
                f"限制={a['upstream_permission']['limitations']}。个人批准不代表上游授权。"
                for a in snapshot["source_access"]])
        if snapshot.get("schema_version") in ("live-snapshot/3.0.0", "live-snapshot/4.0.0"):
            section("行情来源与回退记录", [
                f"{s['security_id']}：实际来源={s['selected_provider']}；口径={s['price_basis']}；"
                f"客户端={s['attempts'][-1]['client_version']}；"
                f"尝试记录={json.dumps(s['attempts'], ensure_ascii=False, sort_keys=True)}；"
                f"选择 hash={s['selection_hash']}" for s in snapshot["source_selections"]])
            section("股票池覆盖范围", [f"NASDAQ 目录状态：{snapshot['universe']['completeness']}；"
                f"观察时间：{snapshot['universe']['as_of']}；不代表投资筛选充分性或历史成员保证。"])
        section("完整持仓与估值口径", [f"持仓来源：{portfolio['source_id']}；as_of={portfolio['as_of']}；retrieved_at={portfolio['retrieved_at']}",
            "市值=数量×Gate 合格收盘价；权重=市值÷(全部持仓市值+现金)。成本不参与估值。"] +
            ([f"组合总值（USD）：{valuation['total_value']}；现金（USD）：{valuation['cash']}"] +
             [f"{row['security_id']}：市值（USD）={row['market_value']}；权重={row['weight']}；价格 Evidence={row['price_evidence_id']}"
              for row in valuation["positions"]] if valuation else [f"未计算完整估值：{valuation_gap}"]))

    analyst = reports.get("runtime_company_analyst", {})
    skeptic = reports.get("runtime_skeptic", {})
    claims = analyst.get("claims", [])
    for claim in claims:
        if claim["kind"] == "FACT" and not claim.get("evidence_refs"):
            raise ValueError("LIVE_REPORT_UNGROUNDED_FACT")
    def claim_text(claim):
        return f"{claim['statement']}；Evidence：{', '.join(claim['evidence_refs'])}；假设：{', '.join(claim.get('assumption_ids', []))}"
    section("行情与业绩事实", [claim_text(c) for c in claims if c["kind"] == "FACT"])
    section("公司分析与假设", [claim_text(c) for c in claims if c["kind"] == "INTERPRETATION"] +
            [f"{a['assumption_id']}：{a['statement']}；依据：{a['rationale']}" for a in analyst.get("assumptions", [])])
    section("独立反证", [claim_text(c) for c in skeptic.get("challenges", [])])
    section("持仓逻辑与 CIO 综合", [item["thesis"]] if item.get("thesis") else [])
    section("CIO 反证与取舍", [item["counter_thesis"]] if item.get("counter_thesis") else [])
    section("失效与重新评估条件", item.get("invalidation_conditions", []) + item.get("reevaluation_conditions", []))
    section("未解决问题与数据局限", item.get("unresolved_questions", []) +
            analyst.get("data_gaps", []) + skeptic.get("data_gaps", []) +
            analyst.get("uncertainties", []) + skeptic.get("uncertainties", []))
    section("置信度依据", [item["confidence_rationale"]] if item.get("confidence_rationale") else [])
    if item["action"] == "NO_TRADE":
        section("暂不操作说明", [item["no_trade_reason"], item["no_trade_explanation"]])
    lines.extend(["## 证据来源与时间", ""])
    for identifier in sorted(refs):
        fact = facts[identifier]
        lines.extend([f"### {_text(identifier)}", "",
                      f"- 字段：{_text(fact['semantic_field'])}",
                      f"- 原值：{_text(fact['value'])}；单位：{_text(fact['unit'])}",
                      f"- source_id：{_text(fact['source_id'])}",
                      f"- 来源定位：{_text(fact['source_locator'])}",
                      f"- as_of：{_text(fact['as_of'])}",
                      f"- published_at：{_text(fact['published_at'])}",
                      f"- 公开时间语义：{_text(fact['published_at_policy'])}",
                      f"- retrieved_at：{_text(fact['retrieved_at'])}",
                      f"- 原始内容 hash：{_text(fact['raw_content_hash'])}"])
        if fact.get("parent_ids"):
            lines.extend([f"- 父证据：{_text(fact['parent_ids'])}",
                          f"- 公式：{_text(fact['metadata']['formula'])}",
                          f"- 计算版本：{_text(fact['source_version'])}"])
        lines.append("")
    return "\n".join(lines) + "\n"
