"""本机研究浏览器的安全、无脚本 HTML 渲染。"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from html import escape
import json
from math import isfinite
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import quote, urlencode


NAV = (("/", "总览"), ("/macro", "Macro"), ("/market", "Market"), ("/companies", "Company"))


def h(value: Any) -> str:
    return escape("—" if value is None or value == "" else str(value), quote=True)


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, default=str)


def _badge(text: Any, tone: str = "neutral") -> str:
    return f'<span class="badge {h(tone)}">{h(text)}</span>'


def _empty(title: str, detail: str, *, code: str | None = None) -> str:
    suffix = f'<code>{h(code)}</code>' if code else ""
    return f'<section class="empty"><h3>{h(title)}</h3><p>{h(detail)}</p>{suffix}</section>'


def _table(headers: Sequence[str], rows: Iterable[Sequence[Any]], *, label: str) -> str:
    body = "".join("<tr>" + "".join(f"<td>{h(cell)}</td>" for cell in row) + "</tr>" for row in rows)
    if not body:
        return _empty("暂无记录", f"{label}当前没有可展示记录。")
    return (
        f'<div class="table-wrap" role="region" aria-label="{h(label)}" tabindex="0"><table><thead><tr>'
        + "".join(f"<th>{h(item)}</th>" for item in headers)
        + f"</tr></thead><tbody>{body}</tbody></table></div>"
    )


def _details(title: str, body: str, *, open_: bool = False) -> str:
    return f'<details{" open" if open_ else ""}><summary>{h(title)}</summary><div class="details-body">{body}</div></details>'


def _layout(title: str, active: str, body: str, *, subtitle: str = "只读 · 本机资料") -> str:
    nav = "".join(
        f'<a href="{href}" class="{"active" if active == href else ""}">{h(label)}</a>'
        for href, label in NAV
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{h(title)} · Research Browser</title><style>{CSS}</style></head>
<body><header><div><a class="brand" href="/">Research Browser</a><span class="sub">{h(subtitle)}</span></div><nav>{nav}</nav></header>
<main><div class="page-title"><div><p class="eyebrow">LOCAL RESEARCH MEMORY</p><h1>{h(title)}</h1></div>
<form method="post" action="/rescan"><button type="submit" class="secondary">重新扫描已配置目录</button></form></div>{body}</main>
<footer>页面读取已保存资料；不会联网刷新、调用模型或修改 Research Memory。</footer></body></html>"""


def error_page(code: str, status: int = 500) -> str:
    labels = {
        "BROWSER_NOT_FOUND": "页面不存在",
        "BROWSER_HOST_REJECTED": "请求来源不是本机",
        "BROWSER_ORIGIN_REJECTED": "跨来源操作已拒绝",
        "BROWSER_METHOD_NOT_ALLOWED": "不支持该操作",
    }
    return _layout(labels.get(code, "资料暂时无法读取"), "", _empty(labels.get(code, "资料暂时无法读取"), "其他独立栏目仍可继续使用。", code=code), subtitle=f"HTTP {status}")


def overview(memory: Mapping[str, Any] | None, artifacts: Mapping[str, Any], *, memory_error: str | None = None) -> str:
    count = memory.get("company_count", 0) if memory else 0
    cards = f"""
    <section class="grid three">
      <a class="card link-card" href="/macro"><span class="kicker">MACRO</span><h2>宏观快照</h2><p>官方指标、实际观测时间与已有宏观研究。</p></a>
      <a class="card link-card" href="/market"><span class="kicker">MARKET</span><h2>市场状态</h2><p>基准日线、已保存窗口统计与研究报告。</p></a>
      <a class="card link-card" href="/companies"><span class="kicker">COMPANY</span><h2>{h(count)} 家已保存公司</h2><p>事实、View、图表、报告及数据状态。</p></a>
    </section>"""
    status = (
        _empty("Research Memory 不可用", "请检查启动时配置的 Memory 目录；不会自动创建数据库。", code=memory_error)
        if memory_error else
        f'<section class="card"><h2>读取状态</h2><div class="metric-row"><div><span>Memory schema</span><strong>{h(memory.get("memory_schema_version"))}</strong></div><div><span>冻结产物</span><strong>{h(artifacts.get("artifact_count", 0))}</strong></div><div><span>目录提示</span><strong>{h(artifacts.get("issue_count", 0))}</strong></div></div></section>'
    )
    return _layout("研究资料总览", "/", cards + status)


def companies_page(result: Mapping[str, Any], *, query: str, status: str) -> str:
    filters = (("", "全部"), ("new_without_report", "有新资料无新报告"), ("gaps", "数据缺口"), ("source_failed", "来源失败"), ("no_report", "尚无报告"))
    filter_html = "".join(
        f'<a class="filter {"active" if value == status else ""}" href="/companies?{urlencode({"q": query, "status": value})}">{h(label)}</a>'
        for value, label in filters
    )
    rows = []
    for item in result["items"]:
        tags = []
        if item["new_without_report"]: tags.append(_badge("新资料", "accent"))
        if item["gap_count"]: tags.append(_badge(f'{item["gap_count"]} 缺口', "warn"))
        if item["source_failed"]: tags.append(_badge("来源受限", "danger"))
        if item["no_report"]: tags.append(_badge("尚无报告"))
        label = item["ticker"] + (f' · {item["company_name"]}' if item.get("company_name") else "")
        rows.append((
            f'<a href="/companies/{quote(item["security_id"], safe="")}">{h(label)}</a><small>{h(item["security_id"])}</small>',
            item.get("data_cutoff"), item.get("latest_check"), item.get("report_cutoff"), " ".join(tags),
        ))
    body = f"""
    <section class="toolbar"><form method="get" action="/companies"><input type="search" name="q" value="{h(query)}" placeholder="搜索 ticker、名称或 security_id"><input type="hidden" name="status" value="{h(status)}"><button type="submit">搜索</button></form><div class="filters">{filter_html}</div></section>
    <p class="note">共 {h(result['total'])} 家已保存公司。资料库记录不等同于当前持仓。</p>
    {_rich_table(['公司','资料截止','最近实际检查','报告研究截止','状态'], rows, label='已保存公司')}
    {_pagination(result, query=query, status=status)}"""
    return _layout("Company", "/companies", body)


def _rich_table(headers: Sequence[str], rows: Iterable[Sequence[str]], *, label: str) -> str:
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    if not body:
        return _empty("没有匹配公司", "调整搜索或状态筛选后重试。")
    return f'<div class="table-wrap" role="region" aria-label="{h(label)}" tabindex="0"><table><thead><tr>{"".join(f"<th>{h(x)}</th>" for x in headers)}</tr></thead><tbody>{body}</tbody></table></div>'


def _pagination(result: Mapping[str, Any], **params: str) -> str:
    page, per_page, total = int(result["page"]), int(result["per_page"]), int(result["total"])
    links = []
    if page > 1:
        links.append(f'<a href="?{urlencode({**params, "page": page - 1})}">← 上一页</a>')
    if page * per_page < total:
        links.append(f'<a href="?{urlencode({**params, "page": page + 1})}">下一页 →</a>')
    return f'<div class="pagination">{"".join(links)}</div>'


def _time_strip(summary: Mapping[str, Any]) -> str:
    return f"""<section class="time-strip"><div><span>资料截止</span><strong>{h(summary.get('data_cutoff'))}</strong></div><div><span>最近实际检查</span><strong>{h(summary.get('latest_check'))}</strong></div><div><span>报告研究截止</span><strong>{h(summary.get('report_cutoff'))}</strong></div></section>"""


def company_page(model: Mapping[str, Any]) -> str:
    summary = model["summary"]
    ticker = summary["ticker"]
    heading = ticker + (f' · {summary["company_name"]}' if summary.get("company_name") else "")
    anchors = "".join(f'<a href="#{target}">{label}</a>' for target, label in (("overview","概览"),("financial","财务"),("market-valuation","行情与估值"),("research","研究记录"),("sources","数据来源")))
    view_options = "".join(
        f'<option value="{h(item["view_manifest_hash"])}" {"selected" if model.get("selected_view") and item["view_manifest_hash"] == model["selected_view"]["view_manifest_hash"] else ""}>{h(item.get("decision_cutoff"))} · {"完整" if (item.get("integrity") or {}).get("complete") else "引用不完整"} · {h(item["view_manifest_hash"][:10])}</option>'
        for item in model["views"]
    )
    view_form = f'<form method="get"><label>已保存 View <select name="view">{view_options}</select></label> <button>选择</button></form>' if view_options else ""
    metrics = model.get("financial_metrics", [])
    core_metrics = metrics[:4]
    financial_charts = [item for item in model["charts"] if str(item.get("chart_id", "")).startswith("financial_")]
    market_charts = [item for item in model["charts"] if not str(item.get("chart_id", "")).startswith("financial_")]
    integrity = _view_integrity(model.get("view_integrity", {}))
    if model.get("selected_view"):
        overview = f'<section id="overview"><h2>概览</h2><p class="note">以下数值均来自当前选择的已保存 View；期间口径直接显示，不把累计值当作单季值。</p>{_metric_cards(core_metrics, summary["security_id"], model.get("selected_view"))}</section>'
        financial = f'<section id="financial"><h2>财务</h2>{_metric_sections(metrics, summary["security_id"], model.get("selected_view"))}<div class="chart-grid">{"".join(_chart(item) for item in financial_charts)}</div>{_disclosures(model["disclosures"])}<p class="more"><a href="{h(_facts_href(summary["security_id"], model.get("selected_view"), "财务与披露"))}">查看全部财务原始事实与版本 →</a></p></section>'
        market = f'<section id="market-valuation"><h2>行情与估值</h2><div class="chart-grid">{"".join(_chart(item) for item in market_charts)}</div><p class="more"><a href="{h(_facts_href(summary["security_id"], model.get("selected_view"), "行情事实"))}">查看逐日价格与成交量明细 →</a></p></section>'
    else:
        catalog_href = _facts_href(summary["security_id"], None)
        overview = f'<section id="overview"><h2>概览</h2>{_empty("尚无冻结 View", "仅提供明确标注的未冻结事实目录；不会把全部历史版本聚合成当前公司指标。", code="UNFROZEN_FACT_CATALOG")}<p class="more"><a href="{h(catalog_href)}">浏览未冻结事实目录 →</a></p></section>'
        financial = '<section id="financial"><h2>财务</h2>' + _empty("等待冻结 View", "保存 View 后才会生成当前指标、期间表和同口径趋势。") + '</section>'
        market = '<section id="market-valuation"><h2>行情与估值</h2>' + _empty("等待冻结 View", "保存 View 后才会生成行情与估值图形。") + '</section>'
    body = f"""
    <div class="company-head"><div><p class="eyebrow">{h(summary['security_id'])}</p></div>{view_form}</div>
    {_time_strip(summary)}{integrity}<nav class="anchors">{anchors}</nav>
    {overview}
    {financial}
    {market}
    <section id="research"><h2>研究记录</h2>{_research_records(summary, model['views'], model['reports'])}{_company_dimension_research(model.get('dimension_research', {}))}</section>
    <section id="sources"><h2>数据来源</h2>{_source_state(model)}{_fact_issues(model.get('fact_issues', []))}</section>"""
    return _layout(heading, "/companies", body)


def _fact_cards(facts: Sequence[Mapping[str, Any]]) -> str:
    if not facts:
        return _empty("暂无概览事实", "可继续查看财务、行情或数据来源。")
    return '<div class="grid metrics">' + "".join(
        f'<article class="metric"><span>{h(item.get("semantic_field"))}</span><strong>{h(item.get("value"))}</strong><small>{h(item.get("unit"))} · as of {h(item.get("as_of"))}</small></article>'
        for item in facts
    ) + "</div>"


def _display_value(value: Any, unit: Any) -> str:
    number = _number(value)
    unit_text = str(unit or "")
    if number is None:
        return str(value) if value is not None else "—"
    if unit_text == "USD":
        absolute = abs(number)
        if absolute >= 100_000_000:
            return f"{number / 100_000_000:,.2f} 亿美元"
        if absolute >= 10_000:
            return f"{number / 10_000:,.2f} 万美元"
        return f"{number:,.2f} 美元"
    if unit_text in {"USD/shares", "USD/share"}:
        return f"{number:,.2f} 美元/股"
    if unit_text.casefold() in {"percent", "%"}:
        return f"{number:,.2f}%"
    return f"{number:,.4g} {unit_text}".strip()


def _metric_href(security_id: str, view: Mapping[str, Any] | None, fact: Mapping[str, Any]) -> str:
    params = {"field": str(fact.get("semantic_field") or "")}
    if view:
        params["view"] = str(view["view_manifest_hash"])
    return f'/companies/{quote(security_id, safe="")}/facts?{urlencode(params)}'


def _metric_cards(
    metrics: Sequence[Mapping[str, Any]], security_id: str,
    view: Mapping[str, Any] | None,
) -> str:
    cards = []
    for metric in metrics:
        latest = metric.get("latest")
        if not isinstance(latest, Mapping):
            cards.append(f'<article class="metric"><span>{h(metric.get("label"))}</span><strong>未保存</strong><small>当前 View 没有可识别数据</small></article>')
            continue
        cards.append(
            f'<article class="metric"><span>{h(metric.get("label"))}</span>'
            f'<strong>{h(_display_value(latest.get("value"), latest.get("unit")))}</strong>'
            f'<small>{h(_period_label(latest))} · {h(latest.get("period_type"))}</small>'
            f'<a href="{h(_metric_href(security_id, view, latest))}">查看数值与证据</a></article>'
        )
    return '<div class="grid metrics">' + "".join(cards) + "</div>"


def _metric_sections(
    metrics: Sequence[Mapping[str, Any]], security_id: str,
    view: Mapping[str, Any] | None,
) -> str:
    blocks = []
    for metric in metrics:
        rows = []
        for item in metric.get("rows", [])[-12:]:
            metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
            rows.append((
                h(_period_label(item)), h(item.get("period_type")),
                h(_display_value(item.get("value"), item.get("unit"))),
                h(metadata.get("fiscal_year")), h(metadata.get("fiscal_period")),
                f'<a href="{h(_metric_href(security_id, view, item))}">来源</a>',
            ))
        body = _rich_table(["期间","口径","数值","财年","财季","证据"], rows, label=str(metric.get("label"))) if rows else _empty("尚无数据", "当前 View 没有可识别的该项指标。")
        blocks.append(_details(f'{metric.get("label")} · {len(metric.get("rows", []))} 个期间', body))
    return "".join(blocks)


def _view_integrity(value: Mapping[str, Any]) -> str:
    if value.get("mode") == "UNFROZEN_FACT_CATALOG":
        return f'<p class="note">未冻结事实目录：可读取 {h(value.get("resolved_count"))} 条已校验事实版本；这些记录不构成已保存 View。</p>'
    if value.get("complete"):
        return f'<p class="note">View 引用完整：{h(value.get("resolved_count"))}/{h(value.get("reference_count"))} 条事实已解析并校验。</p>'
    return _empty(
        "当前 View 引用不完整",
        f'引用 {value.get("reference_count", 0)} 条，成功解析 {value.get("resolved_count", 0)} 条，缺失 {value.get("missing_count", 0)} 条，校验失败 {value.get("invalid_count", 0)} 条。已有部分仅供诊断，不能视为完整研究版本。',
        code="BROWSER_VIEW_INCOMPLETE",
    )


def _facts_href(security_id: str, view: Mapping[str, Any] | None, group: str = "") -> str:
    params = {"group": group}
    if view:
        params["view"] = str(view["view_manifest_hash"])
    return f'/companies/{quote(security_id, safe="")}/facts?{urlencode(params)}'


def _sample_facts(facts: Sequence[Mapping[str, Any]], *, per_field: int = 12, maximum: int = 120) -> list[Mapping[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for item in facts:
        grouped.setdefault(str(item.get("semantic_field", "")), []).append(item)
    selected = [item for field in sorted(grouped) for item in grouped[field][-per_field:]]
    return selected[:maximum]


def _fact_table(facts: Sequence[Mapping[str, Any]], *, browse_href: str | None = None) -> str:
    rows = []
    for item in facts:
        link = f'<a href="{h(item["source_link"])}" target="_blank" rel="noreferrer noopener">主动打开来源</a>' if item.get("source_link") else h(item.get("source_id"))
        metadata = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
        period_kind = metadata.get("period_kind") or metadata.get("fiscal_period") or "—"
        origin = "Derived" if item.get("calculation_refs") or str(item.get("source_type", "")).casefold() == "derived" or str(item.get("source_id", "")).casefold().startswith("derived") else "Provider"
        inputs = item.get("parent_ids") or item.get("calculation_refs") or []
        rows.append((
            h(item.get("semantic_field")), h(item.get("value")),
            h(item.get("unit") or item.get("currency")), h(_period_label(item)),
            h(period_kind), h(origin), h(item.get("as_of")), h(item.get("published_at")),
            h(item.get("retrieved_at")), link,
            f'<code>{h(str(item.get("version_hash") or "")[:16])}</code>',
            h(", ".join(str(value) for value in inputs) if isinstance(inputs, list) else inputs),
        ))
    table = _rich_table(["字段","原值","单位/币种","财务期间","季度/年度","口径","as_of","公开时间","获取时间","来源","版本","父级/计算引用"], rows, label="事实表") if rows else _empty("暂无可用事实", "没有用零值代替缺失数据。")
    return table + (f'<p class="more"><a href="{h(browse_href)}">分页查看完整事实与版本 →</a></p>' if browse_href else "")


def facts_page(model: Mapping[str, Any]) -> str:
    identity = model["identity"]
    sid = identity["security_id"]
    view_hash = model.get("selected_view", {}).get("view_manifest_hash") if model.get("selected_view") else ""
    group_options = '<option value="">全部分组</option>' + "".join(f'<option value="{h(item)}" {"selected" if item == model["group"] else ""}>{h(item)}</option>' for item in model["groups"])
    field_options = '<option value="">全部字段</option>' + "".join(f'<option value="{h(item)}" {"selected" if item == model["field"] else ""}>{h(item)}</option>' for item in model["fields"])
    form = f'''<section class="toolbar"><form method="get"><input type="hidden" name="view" value="{h(view_hash)}"><select name="group">{group_options}</select><select name="field">{field_options}</select><button>筛选</button></form></section>'''
    params = {"view": view_hash, "group": model["group"], "field": model["field"]}
    frozen = bool(model.get("selected_view"))
    count_label = "已选 View 事实" if frozen else "未冻结事实目录记录"
    title_label = "完整事实" if frozen else "未冻结事实目录"
    body = f'<p><a href="/companies/{quote(sid, safe="")}?{urlencode({"view": view_hash})}">← 返回公司详情</a></p>{_view_integrity(model.get("view_integrity", {}))}{form}<p class="note">共 {h(model["total"])} 条{count_label}；当前每页最多 {h(model["per_page"])} 条。</p>{_fact_table(model["items"])}{_pagination(model, **params)}{_fact_issues(model["issues"])}'
    return _layout(f'{identity["ticker"]} · {title_label}', "/companies", body)


def _period_label(item: Mapping[str, Any]) -> str:
    meta = item.get("metadata") if isinstance(item.get("metadata"), Mapping) else {}
    return str(meta.get("period_end") or meta.get("trading_date") or item.get("as_of") or "—")


def _disclosures(items: Sequence[Mapping[str, Any]]) -> str:
    if not items:
        return _empty("当前 View 没有可展示的披露事件", "这表示所选版本未保存受支持的披露事实，不代表公司没有发生事件。")
    cards = []
    for item in items:
        badges = "".join((
            _badge(item.get("form") or "未标注表单"),
            _badge(item.get("period") or "未标注期间"),
        ))
        source_link = item.get("source_link")
        source = h(item.get("source_id"))
        if source_link:
            source = f'<a href="{h(source_link)}" target="_blank" rel="noopener noreferrer">{source}</a>'
        transaction = item.get("transaction") if isinstance(item.get("transaction"), list) else []
        transaction_block = ""
        if transaction:
            transaction_block = _table(
                ["字段", "已保存披露值"],
                ((row.get("label"), row.get("value")) for row in transaction),
                label="Form 4 交易字段",
            ) + '<p class="note">仅解码 SEC 披露字段，不推断交易动机、重要性或投资影响。</p>'
        body = ""
        if item.get("is_excerpt"):
            body = _details("查看已保存正文", f'<p class="disclosure-body">{h(item.get("body"))}</p>')
        collapsed = item.get("collapsed") if isinstance(item.get("collapsed"), list) else []
        collapsed_block = ""
        if collapsed:
            collapsed_rows = []
            for row in collapsed:
                folded_source = h(row.get("source_id"))
                if row.get("source_link"):
                    folded_source = f'<a href="{h(row.get("source_link"))}" target="_blank" rel="noopener noreferrer">{folded_source}</a>'
                collapsed_rows.append((
                    h(row.get("evidence_id")), h(row.get("preview")), folded_source,
                    h(str(row.get("version_hash") or "")[:16]),
                ))
            collapsed_block = _details(
                f"已折叠目录或重复片段 · {len(collapsed)}",
                _rich_table(
                    ["Evidence", "片段", "来源", "事实版本"],
                    collapsed_rows,
                    label="折叠披露片段",
                ),
            )
        cards.append(f'''<article class="event-card"><div class="event-head"><div><span class="kicker">已保存披露事实</span><h3>{h(item.get("title"))}</h3></div><div>{badges}</div></div><p>{h(item.get("excerpt"))}</p>{transaction_block}{body}{collapsed_block}<p class="note">公开时间 {h(item.get("published_at"))} · 来源 {source} · 事实版本 {h(str(item.get("version_hash") or "")[:16])}</p></article>''')
    return '<section class="disclosure-section"><h3>披露与公司事件</h3><p class="note">以下为所选 View 中已保存事实的确定性整理；研究解读仅来自下方已保存报告。</p><div class="event-timeline">' + "".join(cards) + "</div></section>"


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(Decimal(str(value)))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if isfinite(number) else None


def _chart(model: Mapping[str, Any]) -> str:
    title = model.get("title") or model.get("chart_id")
    limitations = model.get("limitations") if isinstance(model.get("limitations"), list) else []
    data = model.get("data") if isinstance(model.get("data"), list) else []
    if model.get("status") != "AVAILABLE" or not data:
        reasons = "".join(f"<li><code>{h(item)}</code></li>" for item in limitations) or "<li>没有合格曲线数据</li>"
        return f'<article class="chart limited"><div><span class="kicker">LIMITED</span><h3>{h(title)}</h3></div><ul>{reasons}</ul></article>'
    series = _choose_series(data)
    if not series:
        return f'<article class="chart limited"><h3>{h(title)}</h3><p>数据已保存，但当前字段没有可安全绘制的统一数值口径。</p></article>'
    svg = _svg_lines(series)
    window = model.get("window") if isinstance(model.get("window"), Mapping) else {}
    basis = model.get("basis")
    trace = _details("图表数据与证据版本", _table(
        ["日期/期间", "原值", "来源", "事实版本"],
        ((
            item.get("date") or item.get("period") or item.get("as_of"),
            item.get("value") if item.get("value") is not None else item.get("close"),
            item.get("source_id"), str(item.get("version_hash") or "")[:16],
        ) for item in data),
        label=f"{title}图表数据",
    ))
    return f'<article class="chart"><div class="chart-title"><div><span class="kicker">{h(model.get("unit") or "SAVED DATA")}</span><h3>{h(title)}</h3></div><span>{h(window.get("points") or len(data))} 点</span></div>{svg}<p class="note">{h(basis)}</p>{trace}</article>'


def _choose_series(rows: Sequence[Mapping[str, Any]]) -> list[tuple[str, list[tuple[str, float | None]]]]:
    preferred = ("close", "value", "security_index", "benchmark_index", "revenue", "fcf", "gross_margin_pct", "operating_margin_pct")
    keys = [key for key in preferred if any(_number(row.get(key)) is not None for row in rows)]
    result = []
    for key in keys[:3]:
        values = []
        for index, row in enumerate(rows):
            label = str(row.get("date") or row.get("period") or row.get("as_of") or index)
            values.append((label, _number(row.get(key))))
        result.append((key, values))
    return result


def _svg_lines(series: Sequence[tuple[str, Sequence[tuple[str, float | None]]]]) -> str:
    width, height, pad = 720, 260, 34
    all_values = [value for _, points in series for _, value in points if value is not None]
    if not all_values:
        return ""
    low, high = min(all_values), max(all_values)
    spread = high - low or 1.0
    longest = max(len(points) for _, points in series)
    colors = ("#37d6c0", "#ffb86b", "#9f9bff")
    paths = []
    for idx, (name, points) in enumerate(series):
        segments, active = [], []
        for pos, (_, value) in enumerate(points):
            if value is None:
                if active: segments.append(active); active = []
                continue
            x = pad + (width - 2 * pad) * pos / max(1, longest - 1)
            y = pad + (height - 2 * pad) * (high - value) / spread
            active.append((x, y))
        if active: segments.append(active)
        for segment in segments:
            points_attr = " ".join(f"{x:.1f},{y:.1f}" for x, y in segment)
            paths.append(f'<polyline points="{points_attr}" fill="none" stroke="{colors[idx]}" stroke-width="2.5" vector-effect="non-scaling-stroke"/>')
        paths.append(f'<text x="{pad + idx * 160}" y="18" fill="{colors[idx]}" font-size="12">{h(name)}</text>')
    first = series[0][1][0][0] if series[0][1] else ""
    last = series[0][1][-1][0] if series[0][1] else ""
    return f'''<svg class="plot" viewBox="0 0 {width} {height}" role="img" aria-label="保存数据折线图"><line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}" stroke="#40505e"/><line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height-pad}" stroke="#40505e"/>{''.join(paths)}<text x="{pad}" y="{height-8}" fill="#90a0ad" font-size="11">{h(first)}</text><text x="{width-pad}" y="{height-8}" text-anchor="end" fill="#90a0ad" font-size="11">{h(last)}</text><text x="{pad+4}" y="{pad+12}" fill="#90a0ad" font-size="11">{h(f'{high:.4g}')}</text><text x="{pad+4}" y="{height-pad-5}" fill="#90a0ad" font-size="11">{h(f'{low:.4g}')}</text></svg>'''


def _research_records(summary: Mapping[str, Any], views: Sequence[Mapping[str, Any]], reports: Sequence[Mapping[str, Any]]) -> str:
    view_rows = []
    sid = quote(str(summary["security_id"]), safe="")
    complete_views = [item for item in views if (item.get("integrity") or {}).get("complete")]
    for item in views:
        compare = ""
        if (item.get("integrity") or {}).get("complete"):
            index = complete_views.index(item)
            if index + 1 < len(complete_views):
                compare = f'<a href="/companies/{sid}/compare?{urlencode({"left": item["view_manifest_hash"], "right": complete_views[index+1]["view_manifest_hash"]})}">与上一完整版本比较</a>'
        status = "完整" if (item.get("integrity") or {}).get("complete") else "引用不完整"
        view_rows.append((h(item.get("decision_cutoff")), h(status), h(item.get("run_id")), h(item["view_manifest_hash"][:16]), compare))
    report_rows = []
    for index, item in enumerate(reports):
        links = [f'<a href="/companies/{sid}/report?{urlencode({"entry": item["entry_id"]})}">打开原报告</a>']
        if index + 1 < len(reports):
            links.append(f'<a href="/companies/{sid}/report?{urlencode({"entry": item["entry_id"], "right": reports[index+1]["entry_id"]})}">与上一份并排</a>')
        report_rows.append((h(item.get("original_report_cutoff")), h(item.get("research_status")), h(item.get("original_run_id")), " · ".join(links)))
    report_block = _rich_table(["研究截止","状态","原 run","报告"], report_rows, label="研究报告") if report_rows else _empty("尚无研究报告", "已有资料仍可阅读；浏览不会自动调用模型。")
    return _details(f"已保存 View · {len(views)}", _rich_table(["资料截止","完整性","run","View hash","比较"], view_rows, label="View 列表")) + _details(f"报告 · {len(reports)}", report_block)


def _company_dimension_research(model: Mapping[str, Any]) -> str:
    labels = {
        "FUNDAMENTAL_EVENT": "基本面与公司事件解读",
        "RESEARCH_REPORT": "公开研报分析",
        "OWNERSHIP_DISCLOSURE": "持股与内部人披露分析",
        "INDUSTRY_COMPARISON": "行业与同行比较",
    }
    entries = model.get("items") if isinstance(model.get("items"), list) else []
    if not entries:
        return _empty("尚未配置补充研究目录", "公司事实与 Company Agent 报告仍可独立阅读。")
    cards = []
    for entry in entries:
        capability = str(entry.get("capability") or "")
        title = labels.get(capability, capability)
        status = entry.get("status")
        if status == "NOT_GENERATED":
            cards.append(_empty(title + " · 未生成", "当前已配置资料中没有与该公司及所选 View 绑定的已保存报告；不代表相关事件或观点不存在。"))
            continue
        if status == "BINDING_FAILED":
            cards.append(_empty(title + " · 绑定校验失败", "发现同公司报告，但 run 或资料截止与所选 View 不一致，因此没有借用展示。", code=str(entry.get("code") or "COMPANY_DIMENSION_REPORT_BINDING_MISMATCH")))
            continue
        reports = entry.get("reports") if isinstance(entry.get("reports"), list) else []
        report_blocks = []
        for item in reports:
            value = item.get("value") if isinstance(item.get("value"), Mapping) else {}
            claims = value.get("claims") if isinstance(value.get("claims"), list) else []
            documents = value.get("documents") if isinstance(value.get("documents"), list) else []
            gaps = value.get("data_gaps") if isinstance(value.get("data_gaps"), list) else []
            details = _details(
                "查看主张、资料与限制",
                _table(
                    ["类型", "内容", "证据/资料"],
                    [
                        *[(claim.get("kind"), claim.get("statement"), ", ".join(claim.get("evidence_refs", []))) for claim in claims],
                        *[("DOCUMENT", document.get("title"), document.get("verification_status")) for document in documents],
                        *[("DATA_GAP", gap.get("description"), gap.get("impact")) for gap in gaps],
                        *[("LIMITATION", limitation, "") for limitation in value.get("limitations", []) if isinstance(limitation, str)],
                    ],
                    label=f"{title}报告内容",
                ),
            )
            report_blocks.append(f'''<article class="dimension-card"><div class="event-head"><div><span class="kicker">{h(capability)}</span><h4>{h(value.get("report_id"))}</h4></div><div>{_badge(value.get("status"), "accent")}{_badge(value.get("sufficiency"))}</div></div><p>{h(value.get("summary"))}</p>{details}<p class="note">run {h(value.get("run_id"))} · cutoff {h((value.get("bindings") or {}).get("decision_cutoff"))} · hash {h(str(value.get("report_hash") or "")[:16])}</p></article>''')
        cards.append(f'<section class="dimension-group"><h3>{h(title)}</h3>{"".join(report_blocks)}</section>')
    issues = model.get("issues") if isinstance(model.get("issues"), list) else []
    return '<section class="supplemental-research"><h3>补充研究</h3><p class="note">只展示已经生成、校验并与当前公司 View 精确绑定的报告；不会在浏览时重新研究。</p>' + "".join(cards) + _artifact_issues(issues) + "</section>"


def _source_state(model: Mapping[str, Any]) -> str:
    states = _table(["Provider","Dataset","Scope","Revision","最近成功","覆盖至","Watermark"], ((
        item.get("provider"), item.get("dataset"), item.get("scope"), item.get("revision"), item.get("last_success_at"), item.get("freshness_until"), item.get("watermark")
    ) for item in model["states"]), label="Checkpoint")
    attempts = _table(["Provider","Dataset","状态","开始","完成"], ((
        item.get("provider"), item.get("dataset"), item.get("status"), item.get("started_at"), item.get("completed_at")
    ) for item in model["attempts"]), label="采集尝试")
    reuse = _table(["检查时间","事件 hash"], ((item.get("checked_at"), item.get("event_hash")) for item in model["reuse_events"]), label="复用检查")
    raw = _details("覆盖与待补细节", f'<pre>{h(_json_text([{"dataset": x.get("dataset"), "coverage": x.get("coverage"), "pending": x.get("pending")} for x in model["states"]]))}</pre>')
    attachment = model.get("external_attachment")
    attachment_block = ""
    if isinstance(attachment, Mapping):
        if attachment.get("status") == "AVAILABLE":
            attachment_block = _details(
                "冻结图形附件",
                _table(
                    ["状态", "资料截止", "run", "package", "bundle"],
                    [(
                        "已校验并采用",
                        attachment.get("decision_cutoff"),
                        attachment.get("run_id"),
                        attachment.get("package_id"),
                        attachment.get("bundle_id"),
                    )],
                    label="冻结图形附件",
                ),
                open_=True,
            )
        else:
            attachment_block = _details(
                "冻结图形附件",
                _empty("附件未采用", "同一证券和截止点存在不一致的冻结图形附件。", code=str(attachment.get("code") or "COMPANY_VISUAL_ATTACHMENT_UNAVAILABLE")),
                open_=True,
            )
    return attachment_block + _details("Checkpoint", states) + _details("来源检查 / 执行记录", attempts) + _details("研究复用事件", reuse) + raw


def _fact_issues(issues: Sequence[Mapping[str, Any]]) -> str:
    if not issues:
        return ""
    return _details("引用与事实诊断", _table(["问题","内容版本"], ((item.get("code"), item.get("version_hash")) for item in issues), label="引用与事实诊断"))


def compare_page(model: Mapping[str, Any], *, show_all: bool) -> str:
    changes = model["changes"] if show_all else [item for item in model["changes"] if item["status"] != "UNCHANGED"]
    groups: dict[str, list[Mapping[str, Any]]] = {}
    for item in changes: groups.setdefault(str(item["group"]), []).append(item)
    blocks = []
    for group, items in groups.items():
        rows = []
        for item in items:
            before, after = item.get("before") or {}, item.get("after") or {}
            rows.append((h(item["status"]), h(before.get("semantic_field") or after.get("semantic_field")), h(before.get("value")), h(after.get("value")), h(before.get("unit") or after.get("unit")), h(_period_label(before or after))))
        blocks.append(f'<section><h2>{h(group)}</h2>{_rich_table(["变化","字段","左侧","右侧","单位","期间"], rows, label=f"{group}变化")}</section>')
    toggle = urlencode({"left": model["left"]["view_manifest_hash"], "right": model["right"]["view_manifest_hash"], "show": "all" if not show_all else "changed"})
    meta = f'<section class="time-strip"><div><span>左侧资料截止</span><strong>{h(model["left"].get("decision_cutoff"))}</strong></div><div><span>右侧资料截止</span><strong>{h(model["right"].get("decision_cutoff"))}</strong></div><div><a href="?{toggle}">{"只看变化" if show_all else "展开未变化项"}</a></div></section>'
    warning = "" if model.get("comparison_status") == "COMPLETE" else _empty(
        "比较结果不完整",
        "至少一侧 View 存在缺失或损坏引用；以下仅展示成功解析部分，不能据此判断事实消失。",
        code="INCOMPLETE_VIEW_REFERENCES",
    )
    return _layout("View 版本比较", "/companies", meta + warning + ("".join(blocks) or _empty("没有事实变化", "两个 View 引用相同的事实内容版本；检查时间变化不算事实修订。")) + _fact_issues(model.get("issues", [])))


def report_page(left: Mapping[str, Any], right: Mapping[str, Any] | None = None) -> str:
    section_labels = {
        "company_and_core_questions": "公司概况与核心问题",
        "business_competition_financials": "业务、竞争与财务",
        "thesis_and_valuation": "Thesis 与估值",
        "catalysts_and_counterevidence": "催化剂与反证",
        "invalidation_and_monitoring": "失效条件与监控",
        "gaps_and_confidence": "数据缺口与置信度",
    }

    def refs(values: Any) -> str:
        return ", ".join(str(value) for value in values) if isinstance(values, list) and values else "—"

    def supported_content(report: Mapping[str, Any]) -> str:
        summary = report.get("research_summary") if isinstance(report.get("research_summary"), Mapping) else {}
        blocks = [
            f'<section class="report-summary"><span class="kicker">研究摘要</span><p>{h(summary.get("summary"))}</p><p class="note">核心主张 {h(refs(summary.get("claim_refs")))} · 主要失效条件 {h(refs(summary.get("primary_invalidation_condition_ids")))}</p></section>'
        ]
        sections = report.get("sections") if isinstance(report.get("sections"), Mapping) else {}
        for name, label in section_labels.items():
            section = sections.get(name) if isinstance(sections.get(name), Mapping) else {}
            blocks.append(f'''<section class="report-section"><div class="event-head"><h3>{h(label)}</h3>{_badge(section.get("status"))}</div><p>{h(section.get("narrative"))}</p><p class="note">主张 {h(refs(section.get("claim_refs")))} · 数据缺口 {h(refs(section.get("data_gap_ids")))}</p></section>''')

        claims = report.get("claims") if isinstance(report.get("claims"), list) else []
        assumptions = report.get("assumptions") if isinstance(report.get("assumptions"), list) else []
        blocks.append(_details("主张与证据关系", _table(
            ["主张", "类型", "内容", "Evidence", "假设", "反向主张", "失效条件"],
            ((
                item.get("claim_id"), item.get("kind"), item.get("statement"), refs(item.get("evidence_refs")),
                refs(item.get("assumption_ids")), refs(item.get("counter_claim_refs")), refs(item.get("invalidation_condition_ids")),
            ) for item in claims), label="主张与证据关系",
        ), open_=True))
        blocks.append(_details("研究假设", _table(
            ["假设", "内容", "理由", "Evidence"],
            ((item.get("assumption_id"), item.get("statement"), item.get("rationale"), refs(item.get("evidence_refs"))) for item in assumptions),
            label="研究假设",
        )))

        conditions = report.get("invalidation_conditions") if isinstance(report.get("invalidation_conditions"), list) else []
        triggers = report.get("reevaluation_triggers") if isinstance(report.get("reevaluation_triggers"), list) else []
        indicators = report.get("monitoring_indicators") if isinstance(report.get("monitoring_indicators"), list) else []
        gaps = report.get("data_gaps") if isinstance(report.get("data_gaps"), list) else []
        blocks.append(_details("失效与重新评估", _table(
            ["类型", "ID", "条件/触发", "监控信号", "关联主张"],
            [
                *[("失效条件", item.get("condition_id"), item.get("description"), item.get("monitoring_signal"), refs(item.get("claim_refs"))) for item in conditions],
                *[("重新评估", item.get("trigger_id"), item.get("description"), "—", refs(item.get("claim_refs"))) for item in triggers],
            ], label="失效与重新评估",
        ), open_=True))
        blocks.append(_details("监控指标", _table(
            ["指标", "说明", "为什么重要", "基线", "比较期间", "重评规则"],
            ((
                item.get("indicator_id"), item.get("description"), item.get("why_it_matters"),
                f'{item.get("baseline") or "—"} {item.get("unit") or ""}', item.get("comparison_period"), item.get("reevaluation_rule"),
            ) for item in indicators), label="监控指标",
        ), open_=True))
        blocks.append(_details("数据缺口", _table(
            ["缺口", "原因", "说明", "影响"],
            ((item.get("gap_id"), item.get("reason_code"), item.get("description"), item.get("impact")) for item in gaps),
            label="数据缺口",
        )))
        confidence = report.get("confidence")
        blocks.append(f'<section class="confidence"><span class="kicker">置信度</span><strong>{h(confidence)}</strong><p>{h(report.get("confidence_rationale"))}</p><p class="note">反证 Evidence：{h(refs(report.get("counter_evidence_refs")))}</p></section>')
        blocks.append(_details("结构化报告原文", f'<pre>{h(_json_text(report))}</pre>'))
        return "".join(blocks)

    def legacy_content(report: Mapping[str, Any]) -> str:
        summary = report.get("summary")
        return _empty(
            "该报告格式尚未完整适配",
            f"schema={report.get('schema_version') or 'UNKNOWN'}；仅保留经允许字段的最小预览，不将其视为当前 Company Agent 契约。",
            code="REPORT_SCHEMA_UNSUPPORTED",
        ) + (f'<section class="report-summary"><p>{h(_json_text(summary))}</p></section>' if summary is not None else "")

    def panel(item: Mapping[str, Any]) -> str:
        report = item.get("report") if isinstance(item.get("report"), Mapping) else {}
        security = report.get("security") if isinstance(report.get("security"), Mapping) else {}
        title = security.get("display_symbol") or report.get("title") or report.get("report_id") or "研究报告"
        content = supported_content(report) if report.get("schema_version") == "equity-research-report/1.0.0" else legacy_content(report)
        return f'<article class="report"><div class="report-meta"><span>研究截止 {h(item.get("original_report_cutoff"))}</span><span>状态 {h(item.get("research_status"))}</span><span>原 run {h(item.get("original_run_id"))}</span><span>报告 hash {h(str(item.get("report_hash") or "")[:16])}</span></div><h2>{h(title)}</h2>{content}</article>'
    panels = panel(left) + (panel(right) if right else "")
    return _layout("已保存研究报告" if right is None else "报告原文并排", "/companies", f'<div class="report-grid {"two" if right else ""}">{panels}</div>')


def macro_page(model: Mapping[str, Any]) -> str:
    selected = model.get("selected")
    selector = _artifact_selector("/macro", model.get("snapshots", []), selected)
    if not selected:
        content = _empty("尚无 Macro 快照", "请通过启动参数配置包含已知 manifest 的冻结运行目录；浏览不会联网补采。")
    else:
        snapshot = selected["value"]
        wanted = {"us_cpi_all_items": "CPI 指数", "us_unemployment_rate": "失业率", "us_treasury_10y_yield": "10Y 收益率"}
        evidence = snapshot.get("evidence") if isinstance(snapshot.get("evidence"), list) else []
        cards = []
        for fact in evidence:
            field = str(fact.get("semantic_field", ""))
            if field in wanted or any(token in field for token in ("cpi", "unemployment", "10_year", "10y")):
                cards.append(f'<article class="metric"><span>{h(wanted.get(field, field))}</span><strong>{h(fact.get("value"))}</strong><small>{h(fact.get("unit"))} · as of {h(fact.get("as_of"))}</small></article>')
        content = f'<p class="note">单次快照只展示观测，不推断趋势；无 historical vintage 时历史修订不可见。</p><div class="grid metrics">{"".join(cards) or _empty("快照无核心指标", "该快照已保存，但没有匹配首版核心字段。")}</div>'
        gaps = [{key: item.get(key) for key in ("provider", "series_id", "reason", "impact") if key in item} for item in snapshot.get("gaps", []) if isinstance(item, Mapping)]
        content += _details("快照状态与缺口", f'<pre>{h(_json_text({"status": snapshot.get("status"), "decision_cutoff": snapshot.get("decision_cutoff"), "gaps": gaps}))}</pre>')
    return _layout("Macro", "/macro", selector + content + _dimension_reports(model["reports"]) + _artifact_issues(model["issues"]))


def market_page(model: Mapping[str, Any]) -> str:
    selected = model.get("selected")
    selector = _artifact_selector("/market", model.get("snapshots", []), selected)
    if not selected:
        content = _empty("尚无 Market 基准快照", "配置冻结运行目录后可读取已保存基准；浏览不会触发补采。")
    else:
        snapshot = selected["value"]
        evidence = snapshot.get("evidence") if isinstance(snapshot.get("evidence"), list) else []
        rows = []
        for item in evidence:
            if str(item.get("semantic_field")) in {"historical_close_price", "adjusted_close_price", "close_price"}:
                rows.append({"date": (item.get("metadata") or {}).get("trading_date") or item.get("as_of"), "close": item.get("value")})
        chart = _chart({"title": f'{snapshot.get("benchmark_ticker") or snapshot.get("benchmark_id") or "基准"} 日线', "status": "AVAILABLE" if rows else "LIMITED", "unit": "price", "data": rows, "limitations": ["BENCHMARK_SERIES_UNAVAILABLE"] if not rows else [], "basis": "按已保存价格事实呈现，不在浏览时重新计算。"})
        content = chart
    calculations = []
    for item in model["calculations"]:
        value = item["value"]
        for window in value.get("windows", []) if isinstance(value.get("windows"), list) else []:
            calculations.append((window.get("window_sessions"), window.get("status"), _json_text(window.get("metrics")), window.get("reason")))
    content += '<section><h2>已保存窗口统计</h2>' + (_table(["交易日","状态","指标","限制"], calculations, label="市场窗口统计") if calculations else _empty("尚无市场计算", "缺少计算不会阻止基准资料阅读。")) + '</section>'
    return _layout("Market", "/market", selector + content + _dimension_reports(model["reports"]) + _artifact_issues(model["issues"]))


def _artifact_selector(path: str, items: Sequence[Mapping[str, Any]], selected: Mapping[str, Any] | None) -> str:
    if not items:
        return ""
    options = []
    for item in sorted(items, key=lambda value: str((value.get("value") or {}).get("decision_cutoff") or (value.get("value") or {}).get("as_of") or value.get("identity")), reverse=True):
        value = item.get("value") if isinstance(item.get("value"), Mapping) else {}
        timestamp = value.get("decision_cutoff") or value.get("as_of") or max(
            (str(fact.get("as_of") or "") for fact in value.get("evidence", []) if isinstance(fact, Mapping)),
            default="未标注时间",
        )
        current = selected and item.get("content_hash") == selected.get("content_hash")
        options.append(f'<option value="{h(item.get("content_hash"))}" {"selected" if current else ""}>{h(timestamp)} · {h(item.get("source_label"))}</option>')
    return f'<section class="toolbar"><form method="get" action="{h(path)}"><label>已保存版本 <select name="version">{"".join(options)}</select></label><button>选择</button></form></section>'


def _dimension_reports(reports: Sequence[Mapping[str, Any]]) -> str:
    if not reports:
        return _empty("尚无相关研究报告", "已保存快照与计算仍可独立阅读。")
    rows = []
    for item in reports:
        value = item["value"]
        summary = value.get("summary")
        if isinstance(summary, (dict, list)):
            summary = _json_text(summary)
        capability = value.get("capability")
        coverage_label = item.get("coverage_label")
        display_capability = (
            f"{capability} / {coverage_label}"
            if coverage_label and coverage_label != capability else capability
        )
        rows.append((value.get("report_id"), value.get("status"), display_capability, summary, item.get("identity")))
    return '<section><h2>已有研究报告</h2>' + _table(["报告","状态","能力","摘要","稳定 ID"], rows, label="研究报告") + '</section>'


def _artifact_issues(issues: Sequence[Mapping[str, Any]]) -> str:
    if not issues:
        return ""
    return _details("目录与格式提示", _table(["代码","对象"], ((item.get("code"), item.get("label")) for item in issues), label="目录提示"))


CSS = r"""
:root{color-scheme:dark;--bg:#081018;--panel:#101b24;--panel2:#152430;--line:#263846;--text:#e8f0f4;--muted:#91a4b2;--accent:#37d6c0;--warn:#ffb86b;--danger:#ff7387;--violet:#9f9bff;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}
*{box-sizing:border-box}html{scroll-behavior:smooth;max-width:100%;overflow-x:hidden}body{margin:0;max-width:100%;overflow-x:hidden;background:radial-gradient(circle at 80% -20%,#183244 0,transparent 35%),var(--bg);color:var(--text);line-height:1.55}a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline}header{position:sticky;top:0;z-index:5;display:flex;justify-content:space-between;align-items:center;max-width:100%;padding:16px max(24px,calc((100vw - 1280px)/2));background:rgba(8,16,24,.94);border-bottom:1px solid var(--line);backdrop-filter:blur(12px)}.brand{color:var(--text);font-weight:750;letter-spacing:.02em}.sub{color:var(--muted);font-size:12px;margin-left:12px}nav{display:flex;gap:8px;min-width:0}header nav a,.anchors a,.filter{color:var(--muted);padding:7px 11px;border-radius:9px}header nav a.active,.anchors a:hover,.filter.active{color:var(--text);background:var(--panel2);text-decoration:none}main{max-width:1280px;min-width:0;margin:auto;padding:40px 24px 80px}.page-title,.company-head{display:flex;justify-content:space-between;align-items:flex-end;gap:20px;min-width:0;margin-bottom:26px}.page-title h1,.company-head h1{margin:3px 0;font-size:clamp(28px,4vw,48px);line-height:1.08}.eyebrow,.kicker{font-size:11px;letter-spacing:.14em;color:var(--accent);text-transform:uppercase;margin:0}.grid{display:grid;gap:16px;min-width:0}.three{grid-template-columns:repeat(3,1fr)}.metrics{grid-template-columns:repeat(auto-fit,minmax(180px,1fr))}.card,.metric,.chart,.empty,.toolbar,details,.report,.event-card,.dimension-card,.report-section,.report-summary,.confidence{min-width:0;background:linear-gradient(145deg,var(--panel),#0d1820);border:1px solid var(--line);border-radius:16px;padding:20px}.link-card{color:var(--text);min-height:165px}.link-card:hover{border-color:var(--accent);text-decoration:none}.card h2,.chart h3{margin:6px 0}.card p,.note,.chart p,.empty p{color:var(--muted)}section{min-width:0;margin:28px 0}section>h2{font-size:22px;margin:0 0 14px}.metric-row,.time-strip{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.metric-row div,.time-strip div,.metric{display:flex;flex-direction:column;gap:5px;min-width:0}.metric-row span,.time-strip span,.metric span{font-size:12px;color:var(--muted)}.metric-row strong,.metric strong{font-size:24px}.time-strip{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;margin-bottom:16px}.time-strip strong{font-size:13px;overflow-wrap:anywhere}.anchors{position:sticky;top:74px;z-index:4;max-width:100%;overflow:auto;white-space:nowrap;background:rgba(8,16,24,.95);padding:8px 0;border-bottom:1px solid var(--line)}button,input,select{max-width:100%;font:inherit;color:var(--text);background:var(--panel2);border:1px solid var(--line);border-radius:9px;padding:10px 12px}button{background:var(--accent);color:#05211e;border-color:var(--accent);font-weight:700;cursor:pointer}.secondary{background:transparent;color:var(--text);border-color:var(--line)}.toolbar form{display:flex;gap:8px;min-width:0}.toolbar input[type=search]{flex:1;min-width:0}.filters{display:flex;gap:7px;flex-wrap:wrap;margin-top:14px}.note{font-size:13px}.table-wrap{max-width:100%;min-width:0;overflow-x:auto;border:1px solid var(--line);border-radius:13px}table{border-collapse:collapse;width:100%;min-width:780px;background:var(--panel)}th,td{text-align:left;padding:11px 13px;border-bottom:1px solid var(--line);vertical-align:top;font-size:13px}th{color:var(--muted);font-weight:600;background:#0b151d}td small{display:block;color:var(--muted);margin-top:3px}.badge{display:inline-block;font-size:11px;padding:3px 7px;border-radius:99px;background:var(--panel2);margin:2px}.badge.accent{color:var(--accent)}.badge.warn{color:var(--warn)}.badge.danger{color:var(--danger)}.chart-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;min-width:0}.chart{margin:0;min-width:0}.chart.limited{border-style:dashed;min-height:210px}.chart-title,.event-head{display:flex;justify-content:space-between;align-items:start;gap:16px}.event-head h3,.event-head h4{margin:3px 0}.event-timeline{display:grid;gap:14px}.event-card,.dimension-card{margin:0}.event-card p,.dimension-card p,.disclosure-body{overflow-wrap:anywhere}.supplemental-research,.disclosure-section{margin-top:24px}.dimension-group{margin:18px 0}.report-section,.report-summary,.confidence{margin:14px 0}.confidence strong{display:block;font-size:30px;color:var(--accent)}.plot{display:block;width:100%;height:auto;margin-top:12px}.chart li{color:var(--muted);font-size:13px}.pagination{display:flex;justify-content:space-between;margin-top:16px}.pagination a{padding:8px 12px;border:1px solid var(--line);border-radius:9px}details{margin:12px 0;padding:0}summary{cursor:pointer;padding:15px 18px;font-weight:650}.details-body{min-width:0;padding:0 18px 18px}.details-body>*{min-width:0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#071018;padding:14px;border-radius:10px;border:1px solid var(--line);font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace}.report-grid{display:grid;grid-template-columns:1fr;gap:16px;min-width:0}.report-grid.two{grid-template-columns:repeat(2,minmax(0,1fr))}.report{min-width:0;margin:0}.report-meta{display:flex;gap:16px;flex-wrap:wrap;color:var(--muted);font-size:12px}footer{color:var(--muted);font-size:12px;text-align:center;padding:24px;border-top:1px solid var(--line)}code{color:var(--warn)}
@media(max-width:720px){header{position:static;display:block;padding:14px 16px;overflow:hidden}.sub{display:none}header nav{max-width:100%;margin-top:12px;overflow:auto;flex-wrap:nowrap}header nav a,.anchors a{white-space:nowrap;flex:0 0 auto}main{padding:26px 14px 60px}.page-title,.company-head,.event-head{display:block}.page-title form,.company-head form{max-width:100%;margin-top:14px}.company-head label,.company-head select{display:block;width:100%}.company-head button{margin-top:8px}.three,.chart-grid,.time-strip,.metric-row,.report-grid.two{grid-template-columns:minmax(0,1fr)}.anchors{top:0}.toolbar form{display:grid;grid-template-columns:minmax(0,1fr) auto}.chart,.event-card,.dimension-card,.report{padding:15px}h1{overflow-wrap:anywhere}}
"""
