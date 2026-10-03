"""可重复生成已保存复盘的离线合并页；不采集、联网或调用模型。"""
from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from .charts import chart_payload, render_chart_payload
from .common import canonical_json
from .presentation import build_reader_labels
from .reflection import PHASES, ReflectionError, render_markdown, validate_report


_REPORT_ID = re.compile(r"reflection-[a-f0-9]{32}\Z")
_PRIVATE_FIELDS = {"account_ref", "account_id", "account_number", "account_name", "account", "raw", "raw_row", "raw_content", "source_path", "credentials", "cookies", "token", "password", "client"}
_FINDING_FIELDS = ("finding_id", "pattern", "record_refs", "episode_refs", "chart_refs", "calculation_refs", "diary_refs", "process_observation", "result_observation", "interpretation", "confidence_limits", "decision_evidence_refs", "outcome_evidence_refs", "uncertain_evidence_refs")
_EVIDENCE_FIELDS = ("evidence_id", "kind", "title", "content", "source_id", "as_of", "retrieved_at", "source_as_of", "publication_date", "published_at", "available_at", "event_at", "availability_basis", "available_at_basis", "publication_precision", "vintage_status", "vintage_available_at", "revised")


def _research_value(value: Any) -> Any:
    """Retain research values, excluding accidental private transport fields."""
    if isinstance(value, Mapping):
        return {key: _research_value(item) for key, item in value.items() if key.lower() not in _PRIVATE_FIELDS}
    if isinstance(value, list):
        return [_research_value(item) for item in value]
    return deepcopy(value)


def _select(value: Mapping[str, Any], fields: tuple[str, ...]) -> dict[str, Any]:
    return {key: _research_value(value[key]) for key in fields if key in value}


def _https_url(value: Any) -> str | None:
    if not isinstance(value, str) or any(ord(char) < 33 or ord(char) == 127 for char in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme.lower() == "https" and parsed.hostname and parsed.username is None and parsed.password is None:
            return value
    except ValueError:
        pass
    return None


def _time_bounds(values: list[Any]) -> tuple[str | None, str | None]:
    dated = []
    for value in values:
        if not isinstance(value, str):
            continue
        try:
            stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
            # Date-only facts keep their original precision in the output.
            # Midnight is used only for ordering, never displayed as a trade time.
            dated.append((stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp, value))
        except ValueError:
            continue
    return (min(dated)[1], max(dated)[1]) if dated else (None, None)


def _coverage_payload(coverage: Mapping[str, Any]) -> dict[str, Any]:
    """Keep business coverage facts without whole receipts or account fields."""
    result = _select(coverage, ("status", "actual_start", "actual_end", "source_id", "as_of", "retrieved_at"))
    window = coverage.get("requested_window")
    result["requested_window"] = _select(window, ("start", "end", "timezone")) if isinstance(window, Mapping) else None
    result["observations"] = []
    for row in coverage.get("observations", []):
        if not isinstance(row, Mapping):
            continue
        observation = _select(row, ("source_id", "as_of", "retrieved_at", "actual_start", "actual_end", "status", "collection_mode"))
        request = row.get("request")
        if isinstance(request, Mapping):
            observation["request"] = _select(request, ("start", "end", "timezone"))
        result["observations"].append(observation)
    if not result.get("actual_start") or not result.get("actual_end"):
        start, end = _time_bounds([value for row in result["observations"] for value in (row.get("actual_start"), row.get("actual_end"))])
        result["actual_start"] = result.get("actual_start") or start
        result["actual_end"] = result.get("actual_end") or end
    result["gaps"] = [
        _select(row, ("code", "reason", "message", "detail", "asset_type", "start", "end", "date")) if isinstance(row, Mapping) else _research_value(row)
        for row in coverage.get("gaps", [])
    ]
    return result


def _review_payload(report: Mapping[str, Any], packet: Mapping[str, Any]) -> dict[str, Any]:
    findings, used_evidence, used_calculations = [], set(), set()
    lessons, events = [], []
    for source in report.get("case_lessons", []):
        lesson = _select(source, ("finding_ref", "focus_record_ref", "limits"))
        lesson["chart_window"] = _select(source["chart_window"], ("start", "end", "record_refs", "focus_instrument_key"))
        lesson["beginner"] = _select(source["beginner"], ("read_chart", "why_it_matters", "record_refs", "evidence_refs"))
        lesson["beginner"]["terms"] = [_select(row, ("term", "meaning", "case_application")) for row in source["beginner"].get("terms", [])]
        lesson["practice"] = _select(source["practice"], ("possible_error", "exercise", "next_inputs", "verification", "record_refs", "evidence_refs"))
        lesson["advanced"] = _select(source["advanced"], ("alternative_explanation", "falsifier", "additional_evidence", "record_refs", "evidence_refs"))
        lesson["event_links"] = [_select(row, ("evidence_ref", "record_refs", "anchor_role", "relevance_note")) for row in source.get("event_links", [])]
        for name in ("beginner", "practice", "advanced"):
            used_evidence.update(lesson[name].get("evidence_refs", []))
        used_evidence.update(row["evidence_ref"] for row in lesson["event_links"])
        # Only the validated helper derives event times and per-record PIT layers.
        from .reflection import lesson_events
        for event in lesson_events(report, packet, source):
            selected = _select(event, ("evidence_id", "source_id", "as_of", "retrieved_at", "title", "content", "anchor_role", "anchor_at", "date", "dates_by_record", "publication_precision", "record_refs", "layers", "relevance_note", "availability_basis", "vintage_status"))
            selected["source_url"] = _https_url(event.get("source_url"))
            selected["finding_ref"] = lesson["finding_ref"]
            events.append(selected)
        lessons.append(lesson)
    for source in report["findings"]:
        item = _select(source, _FINDING_FIELDS)
        item["alternative_explanations"] = [_select(row, ("text", "record_refs", "episode_refs", "evidence_refs")) for row in source["alternative_explanations"]]
        item["intent_claims"] = [_select(row, ("record_id", "diary_id", "layer")) for row in source.get("intent_claims", [])]
        item["financial_claims"] = [_select(row, ("calculation_ref", "metric", "value")) for row in source.get("financial_claims", [])]
        for field in ("decision_evidence_refs", "outcome_evidence_refs", "uncertain_evidence_refs"):
            used_evidence.update(item.get(field, []))
        for row in item["alternative_explanations"]:
            used_evidence.update(row.get("evidence_refs", []))
        used_calculations.update(item.get("calculation_refs", []))
        used_calculations.update(row["calculation_ref"] for row in item["financial_claims"])
        findings.append(item)
    plans = [_select(row, ("improvement_id", "finding_refs", "record_refs", "evidence_refs", "exercise", "next_inputs", "verification", "review_window", "status")) for row in report["improvement_plan"]]
    for row in plans:
        used_evidence.update(row.get("evidence_refs", []))
    evidence = []
    for source in packet["evidence"]:
        if source["evidence_id"] in used_evidence:
            item = _select(source, _EVIDENCE_FIELDS)
            item["source_url"] = _https_url(source.get("source_url"))
            evidence.append(item)
    coverage = _coverage_payload(report["scope"]["coverage"])
    analyzed_records = set(report["scope"]["record_ids"])
    record_start, record_end = _time_bounds([row.get("occurred_at") for row in packet["snapshot"]["records"] if row["record_id"] in analyzed_records])
    return {
        **_select(report, ("report_id", "source_id", "as_of", "retrieved_at", "report_as_of", "cutoff", "snapshot_id", "input_hash", "packet_hash", "model_version", "skill_version", "limitations")),
        "scope": {**_select(report["scope"], ("mode", "record_ids", "context_record_ids", "excluded_record_ids", "asset_types", "limitations")),
                  "coverage": coverage},
        "report_basis": {
            "mode": report["scope"]["mode"],
            "record_count": len(report["scope"]["record_ids"]),
            "context_record_count": len(report["scope"].get("context_record_ids", [])),
            "excluded_record_count": len(report["scope"].get("excluded_record_ids", [])),
            "asset_types": deepcopy(report["scope"]["asset_types"]),
            "record_start": record_start,
            "record_end": record_end,
            "coverage": deepcopy(coverage),
        },
        "phase_coverage": {phase: _select(report["phase_coverage"][phase], ("status", "reason")) for phase in PHASES},
        "progress": _select(report["progress"], ("total_units", "analyzed_episode_ids", "pending_episode_ids", "status")),
        "case_selection": _select(report["case_selection"], ("available_by_result", "selected_reasons", "omitted_classes")),
        "schema_version": report.get("schema_version"),
        "findings": findings, "improvement_plan": plans, "evidence": evidence,
        "case_lessons": lessons, "lesson_events": events,
        "calculations": {identifier: _select(packet["calculations"][identifier], ("kind", "episode_id", "formula_version", "metrics", "currency", "status", "source_id", "as_of", "retrieved_at", "assumptions", "limitations")) for identifier in sorted(used_calculations)},
    }


def render_review(report: Mapping[str, Any], packet: Mapping[str, Any]) -> str:
    """Validate frozen research and attach its minimal projection to the chart."""
    validate_report(report, packet)
    return render_review_payload(chart_payload(packet["snapshot"]), _review_payload(report, packet))


def render_review_payload(chart_data: dict[str, Any], review_data: Mapping[str, Any] | None = None) -> str:
    """Render only the caller's whitelisted selection; never read a full packet."""
    page = render_chart_payload(chart_data)
    if review_data is None:
        return page
    if review_data.get("viewer_selection") is True:
        # The bounded viewer fetches only its same-origin summary projection.
        # Standalone frozen pages keep their network-denying policy.
        page = page.replace("connect-src 'none'", "connect-src 'self'", 1)
    encoded = canonical_json(review_data).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    page = page.replace("</style>", _REVIEW_CSS + "</style>", 1)
    page = page.replace('<details id="trade-table">', '<div id="jr-event-detail" class="detail" role="region" aria-label="选中事件" hidden></div><details id="trade-table">', 1)
    page = page.replace("</main>", _REVIEW_SECTION + "</main>", 1)
    page = page.replace('<script id="journal-data"', '<script id="reflection-data" type="application/json">' + encoded + '</script><script id="journal-data"', 1)
    labels = build_reader_labels(packet=review_data, report=review_data, records=chart_data.get("records", []))
    label_json = canonical_json(labels).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    registration = "\nfor(const [identifier,label] of Object.entries(" + label_json + "))jrRegisterLabel(identifier,label);\n"
    return page.replace("</script></body></html>", registration + _REVIEW_SCRIPT + "\n</script></body></html>", 1)


def _directory(descriptor: int, name: str) -> int:
    try:
        child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0), dir_fd=descriptor)
        if stat.S_IMODE(os.fstat(child).st_mode) != 0o700:
            os.close(child)
            raise ReflectionError("私人产物目录权限必须为 0700")
        return child
    except OSError as exc:
        raise ReflectionError("私人产物目录缺失、不是目录或包含符号链接") from exc


def _read_file(directory: int, name: str) -> bytes:
    try:
        descriptor = os.open(name, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0), dir_fd=directory)
        with os.fdopen(descriptor, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1:
                raise ReflectionError("私人产物必须是 0600 的独立普通文件")
            return stream.read()
    except OSError as exc:
        raise ReflectionError("私人产物无法读取或包含符号链接") from exc


def _load_json(directory: int, name: str) -> dict[str, Any]:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ReflectionError("私人 JSON 含重复字段")
            result[key] = value
        return result
    def invalid_constant(_):
        raise ReflectionError("私人 JSON 不能包含非有限数值")
    try:
        value = json.loads(_read_file(directory, name), object_pairs_hook=pairs, parse_constant=invalid_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ReflectionError("私人产物不是有效 JSON") from exc
    if not isinstance(value, dict):
        raise ReflectionError("私人 JSON 必须为对象")
    return value


@contextmanager
def _review_directory(validated_root: Path, report_id: str):
    if not isinstance(report_id, str) or not _REPORT_ID.fullmatch(report_id):
        raise ReflectionError("报告版本必须为 reflection-32位小写十六进制身份")
    root = Path(validated_root)
    if not root.is_absolute() or ".." in root.parts or any(path.is_symlink() for path in (root, *root.parents)):
        raise ReflectionError("保存目录必须是已验证的绝对私人 root，不能包含符号链接")
    descriptors = []
    try:
        # Traverse each ancestor with no-follow directory handles as well: a
        # path replacement after the preliminary check cannot follow a link.
        current = os.open(root.anchor, os.O_RDONLY | os.O_DIRECTORY)
        descriptors.append(current)
        for component in root.parts[1:]:
            current = os.open(component, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0), dir_fd=current)
            descriptors.append(current)
        if stat.S_IMODE(os.fstat(current).st_mode) != 0o700:
            raise ReflectionError("私人 root 权限必须为 0700")
        for component in ("artifacts", "reflections", report_id):
            current = _directory(current, component)
            descriptors.append(current)
        yield root, current
    except OSError as exc:
        raise ReflectionError("私人版本路径无法安全打开或写入") from exc
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def _load_bound_review(directory: int, report_id: str, load_snapshot: Callable[[str], Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    report, packet = _load_json(directory, "report.json"), _load_json(directory, "input.json")
    if report.get("report_id") != report_id:
        raise ReflectionError("报告版本与保存目录不一致")
    validate_report(report, packet)
    authoritative = load_snapshot(packet["snapshot_id"])
    if canonical_json(packet["snapshot"]) != canonical_json(authoritative):
        raise ReflectionError("报告冻结快照与本地账本保存版本不一致")
    return report, packet


def load_review(validated_root: Path, report_id: str, *, load_snapshot: Callable[[str], Mapping[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Read one immutable, bound version through the same strict fd boundary."""
    with _review_directory(validated_root, report_id) as (_, directory):
        return _load_bound_review(directory, report_id, load_snapshot)


def save_review(validated_root: Path, report_id: str, *, load_snapshot: Callable[[str], Mapping[str, Any]]) -> dict[str, Any]:
    """Create an immutable offline page from one verified saved version."""
    with _review_directory(validated_root, report_id) as (root, current):
        report, packet = _load_bound_review(current, report_id, load_snapshot)
        encoded = render_review(report, packet).encode("utf-8")
        content_hash = hashlib.sha256(encoded).hexdigest()
        filename = f"review-{content_hash}.html"
        reused = False
        try:
            descriptor = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=current)
        except FileExistsError:
            if _read_file(current, filename) != encoded:
                raise ReflectionError("既存查看页内容不一致，拒绝覆盖")
            reused = True
        else:
            with os.fdopen(descriptor, "wb") as stream:
                # umask can narrow creation permissions; enforce the private
                # artifact contract on the exclusively created descriptor.
                os.fchmod(stream.fileno(), 0o600)
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        markdown = render_markdown(report, packet).encode("utf-8")
        markdown_hash = hashlib.sha256(markdown).hexdigest()
        markdown_name = f"reading-{markdown_hash}.md"
        markdown_reused = False
        try:
            descriptor = os.open(markdown_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600, dir_fd=current)
        except FileExistsError:
            if _read_file(current, markdown_name) != markdown:
                raise ReflectionError("既存易读报告内容不一致，拒绝覆盖")
            markdown_reused = True
        else:
            with os.fdopen(descriptor, "wb") as stream:
                os.fchmod(stream.fileno(), 0o600)
                stream.write(markdown)
                stream.flush()
                os.fsync(stream.fileno())
        return {"report_id": report_id, "review_path": str(root / "artifacts" / "reflections" / report_id / filename), "content_hash": content_hash, "reused": reused,
                "markdown_path": str(root / "artifacts" / "reflections" / report_id / markdown_name), "markdown_content_hash": markdown_hash, "markdown_reused": markdown_reused}


_REVIEW_CSS = r'''
.jr-reader-heading{margin-top:24px}.jr-reader-heading h2{margin:0}.jr-reader-grid{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(270px,1fr);gap:20px}.jr-reader-grid>section{min-width:0;scroll-margin-top:16px}.jr-reader-grid .jr-reader-heading{margin-top:12px}.jr-reader-nav{display:flex;gap:12px;flex-wrap:wrap;margin:10px 0}.jr-reader-nav a{color:#087e77;font-size:13px}.jr-reader-note{font-size:12px;color:var(--muted);white-space:pre-line}.jr-overview-pager{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:12px 0}.jr-overview-pager button{font-size:12px}.jr-inline-limits{border-left:3px solid #aac0c4;padding-left:10px;font-size:12px;white-space:pre-line;color:#526d74}.jr-summary-item{background:#fbfdfd}.jr-summary-item .jr-relation{font-size:12px;color:#526d74}.jr-directory{margin-top:20px}.jr-directory>summary,.jr-meta>summary{cursor:pointer;color:#41626b}.jr-selected-title{font-size:18px;margin-top:20px}@media(max-width:800px){.jr-reader-grid{grid-template-columns:minmax(0,1fr)}}
.jr-controls{margin:14px 0}.jr-controls input{max-width:360px;width:100%}.jr-findings,.jr-plans{display:grid;gap:14px;margin-top:14px}.jr-item{border:1px solid var(--line);border-radius:10px;padding:16px;overflow-wrap:anywhere}.jr-item h3{margin:0 0 10px;font-size:17px}.jr-item p{margin:7px 0;white-space:pre-line}.jr-item details,.jr-meta{margin-top:12px}.jr-item summary,.jr-meta summary{cursor:pointer;color:#41626b}.jr-refs{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}.jr-refs button{font-size:11px;max-width:100%;overflow-wrap:anywhere;text-align:left}.jr-event-choices{display:grid;gap:8px}.jr-event-choices button{text-align:left;white-space:normal;overflow-wrap:anywhere}.jr-source{border-left:2px solid #c8d7db;padding-left:10px;margin:10px 0}.jr-source a{color:#087e77;overflow-wrap:anywhere}.jr-label{font-size:12px;color:var(--muted)}.jr-meta pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.6 inherit}.jr-count{font-size:12px;color:var(--muted)}@media print{.jr-controls{display:none}.jr-refs button,.jr-event-choices button{border:0;background:none;color:inherit;padding:0}.jr-item,.jr-source{break-inside:avoid}.jr-meta,.jr-item details{display:block}}
'''

_REVIEW_SECTION = r'''
<section class="card" id="reflection-review"><div class="jr-reader-heading"><h2>复盘总结</h2><p id="jr-reading-scope" class="jr-reader-note"></p></div><nav class="jr-reader-nav" aria-label="复盘正文"><a href="#jr-overview">原文要点</a><a href="#jr-advice">已有改进建议</a></nav><p id="jr-reading-limits" class="jr-inline-limits"></p><div class="jr-reader-grid"><section id="jr-overview" aria-label="原文复盘要点"><div id="jr-summaries" class="jr-findings"></div><div class="jr-overview-pager"><button type="button" id="jr-summary-prev">上一页要点</button><span id="jr-summary-count" class="jr-count" role="status"></span><button type="button" id="jr-summary-next">下一页要点</button></div></section><section id="jr-advice" aria-label="已有改进建议"><div class="jr-reader-heading"><h2>已有改进建议</h2><p class="jr-reader-note">保留原报告的建议和验证方式，按保存顺序展示；适用范围由原成交引用说明。</p></div><div id="jr-plans" class="jr-plans"></div></section></div>
<details id="jr-directory" class="jr-directory"><summary>完整案例目录与练习选择</summary>
<div class="controls jr-controls"><label>目录范围<select id="jr-scope"><option value="ALL">全部已保存复盘</option><option value="CURRENT">当前图表相关复盘</option></select></label><label>搜索目录<input id="jr-search" type="search" placeholder="案例、观察、引用或练习"></label><label>选择案例<select id="jr-case"><option value="">请选择案例</option></select></label><label>选择练习<select id="jr-plan"><option value="">请选择练习</option></select></label><button id="jr-all">恢复全部目录</button><span id="jr-count" class="jr-count"></span></div>
</details><p id="jr-notice" class="jr-reader-note" role="status"></p><h2 id="jr-selected-title" class="jr-selected-title" hidden>所选案例的完整讲解</h2><div id="jr-findings" class="jr-findings"></div><details id="jr-data-explanation" class="jr-meta"><summary>数据说明、报告依据与来源</summary><span class="badge" id="jr-progress"></span><div id="jr-summary" class="notice"></div><div id="jr-metadata"></div></details></section>
'''

_REVIEW_SCRIPT = r'''
const REVIEW=JSON.parse($("reflection-data").textContent),jrRecords=new Map(DATA.records.map(row=>[row.record_id,row])),jrEvidenceById=new Map((REVIEW.evidence||[]).map(row=>[row.evidence_id,row])),jrFindings=REVIEW.findings||[],jrLessons=new Map((REVIEW.case_lessons||[]).map(row=>[row.finding_ref,row])),jrDirectory=REVIEW.directory||jrFindings;
let jrSummary=REVIEW.original_summary||null,jrPlans=jrSummary?jrSummary.improvement_plan||[]:REVIEW.improvement_plan||[],jrSummaryPage=0,jrMode="ALL",jrSelectedFinding="",jrSelectedPlan="",jrSummaryRequest=0,jrSummaryKey="",jrSummaryFailure="";
const JR_SUMMARY_PAGE_SIZE=12;
const jrSummaryRecords=new Map(DATA.records.map(row=>[row.record_id,row]));
function jrRegisterSummary(summary){for(const row of summary&&summary.reference_records||[])if(!jrSummaryRecords.has(row.record_id))jrSummaryRecords.set(row.record_id,row);for(const[identifier,label]of Object.entries(summary&&summary.reference_labels||{}))jrRegisterLabel(identifier,label);for(const row of summary&&summary.findings||[])jrRegisterLabel(row.finding_id,row.pattern||"复盘案例");for(const plan of summary&&summary.improvement_plan||[])jrRegisterLabel(plan.improvement_id,plan.exercise||"已保存练习")}
jrRegisterSummary(jrSummary);
const jrOpenStates=new Map();
function jrWalkDetails(parent,visit,path=""){Array.from(parent.children).forEach((child,index)=>{const key=path+"/"+child.tagName.toLowerCase()+"["+index+"]"+(child.dataset.evidence?":"+child.dataset.evidence:"");if(child.tagName.toLowerCase()==="details")visit(child,key);jrWalkDetails(child,visit,key)})}
function jrPaneIdentity(pane){return pane.dataset.summaryFinding?"summary:"+pane.dataset.summaryFinding:pane.dataset.finding?"finding:"+pane.dataset.finding:pane.dataset.improvement?"plan:"+pane.dataset.improvement:null}
function jrRememberPanes(){for(const parent of[$("jr-findings"),$("jr-plans"),$("jr-summaries")])for(const pane of parent.children){const identity=jrPaneIdentity(pane);if(!identity)continue;const state=new Map();jrWalkDetails(pane,(details,key)=>state.set(key,!!details.open));jrOpenStates.set(identity,state)}}
function jrRestorePanes(){for(const parent of[$("jr-findings"),$("jr-plans"),$("jr-summaries")])for(const pane of parent.children){const identity=jrPaneIdentity(pane);if(!identity)continue;const state=jrOpenStates.get(identity)||new Map();jrWalkDetails(pane,(details,key)=>{if(state.has(key))details.open=state.get(key);else state.set(key,!!details.open);details.addEventListener("toggle",()=>state.set(key,!!details.open))});jrOpenStates.set(identity,state)}}
const jrValue=value=>jrReadable(value);
function jrText(parent,tag,text,klass){const el=document.createElement(tag);el.textContent=jrValue(text);if(klass)el.className=klass;parent.appendChild(el);return el}
function jrLine(parent,label,item){const p=document.createElement("p");jrText(p,"strong",label+"：");jrText(p,"span",item);parent.appendChild(p)}
function jrDetails(parent,label){const details=document.createElement("details");jrText(details,"summary",label);parent.appendChild(details);return details}
function jrRefs(parent,label,identifiers){jrLine(parent,label,(identifiers||[]).map(jrRefLabel));}
function jrClearSelection(){jrSelectedFinding="";jrSelectedPlan="";$("jr-event-detail").hidden=true}
function jrRelatedRecords(finding){return [...new Set([...(finding.record_refs||[]),...(finding.alternative_explanations||[]).flatMap(row=>row.record_refs||[]),...(finding.practice&&finding.practice.record_refs||[])])]}
function jrCurrentRecords(){return new Set(segmentRows.map(row=>row.record_id))}
function jrSummarySelection(){return {group_id:$("symbol").value,date:selectedDate||"",asset:$("asset").value||"ALL",contract:$("contract").value||"ALL",start:$("start").value||"",end:$("end").value||""}}
function jrSummarySelectionKey(selection){return JSON.stringify([selection.group_id||"",selection.date||"",selection.asset||"ALL",selection.contract||"ALL",selection.start||"",selection.end||""])}
function jrSummaryCurrentRecords(){if(!$("symbol").value)return null;return new Set(segmentRows.filter(row=>!selectedDate||row.display_date===selectedDate).map(row=>row.record_id))}
function jrSummaryRelations(finding,current){
 const matches=references=>current===null?true:(references||[]).some(id=>current.has(id)),lesson=jrLessons.get(finding.finding_id),practice=finding.practice||lesson&&lesson.practice;
 return {main:matches(finding.record_refs)&&!!(finding.record_refs||[]).length,alternatives:(finding.alternative_explanations||[]).filter(row=>current===null||matches(row.record_refs)),practice:practice&&(current===null||matches(practice.record_refs))?practice:null,limits:finding.practice_limits||lesson&&lesson.limits||[]}
}
function jrSummaryFinding(parent,finding,relations){
 const box=document.createElement("article");box.className="jr-item jr-summary-item";box.dataset.summaryFinding=finding.finding_id;box.dataset.finding=finding.finding_id;jrText(box,"h3",finding.pattern||"已保存复盘要点");
 if(relations.main){for(const[key,title]of[["process_observation","过程观察"],["result_observation","事后结果"],["interpretation","候选解释"]])if(finding[key]!=null)jrLine(box,title,finding[key]);}
 else jrText(box,"p",relations.alternatives.length?"当前选择在此案例中是反例；以下保留对应反例原文。":"当前选择与此案例的练习引用关联；以下保留练习原文。","jr-relation");
 for(const alternative of relations.alternatives){const detail=relations.main?jrDetails(box,"反例或替代解释 · 原文"):box;jrLine(detail,"反例或替代解释",alternative.text);if((alternative.record_refs||[]).length){const refs=jrDetails(detail,"反例成交引用");jrRecordButtons(refs,alternative.record_refs)}}
 if(relations.practice){const practice=relations.practice;jrText(box,"h4","关联练习 · 原文");for(const[key,title]of[["possible_error","可能的问题"],["exercise","可验证练习"],["next_inputs","下次记录"],["verification","验证方式"]])if(practice[key]!=null)jrLine(box,title,practice[key]);jrLine(box,"练习限制",relations.limits);}
 if(finding.confidence_limits!=null){const limits=document.createElement("div");limits.className="jr-inline-limits";jrLine(limits,"原判断限制",finding.confidence_limits);box.appendChild(limits)}
 const references=jrDetails(box,"对应成交与完整案例");if(relations.main)jrRecordButtons(references,finding.record_refs);if(relations.practice)jrRecordButtons(references,relations.practice.record_refs,"练习自己的成交引用");const button=jrText(references,"button","阅读完整案例");button.type="button";button.addEventListener("click",()=>jrSelectFinding(finding.finding_id));parent.appendChild(box)
}
function jrPlanScope(plan){
 if(plan.scope_label)return plan.scope_label;const records=(plan.record_refs||[]).map(id=>jrSummaryRecords.get(id)).filter(Boolean),groups=new Set(records.map(row=>row.group_id)),symbols=[...new Set(records.map(row=>row.instrument&&row.instrument.symbol).filter(Boolean))];
 return `${groups.size>1?"跨标的建议":(plan.finding_refs||[]).length>1?"跨案例建议":"原计划关联范围"}${symbols.length?"："+symbols.join(" / "):"：关联成交资料暂不可展示"}`
}
function jrRenderSummaries(){
 const selection=jrSummarySelection(),key=jrSummarySelectionKey(selection),remoteMismatch=jrSummary&&REVIEW.viewer_selection===true&&typeof window!=="undefined"&&window.location&&jrSummarySelectionKey(jrSummary.selection||{})!==key;if(!jrSummary&&key!==jrSummaryKey)jrSummaryPage=0;const current=jrSummary?null:jrSummaryCurrentRecords(),candidates=jrSummary?jrSummary.findings||[]:jrFindings,related=candidates.map(finding=>({finding,relations:jrSummaryRelations(finding,current)})).filter(row=>row.relations.main||row.relations.alternatives.length||row.relations.practice),pagination=jrSummary&&jrSummary.pagination;
 const total=pagination?pagination.total_count:related.length,pages=Math.max(1,pagination?pagination.total_pages:Math.ceil(total/JR_SUMMARY_PAGE_SIZE));jrSummaryPage=Math.max(0,Math.min(pagination?pagination.page:jrSummaryPage,pages-1));const rows=remoteMismatch?[]:pagination?related:related.slice(jrSummaryPage*JR_SUMMARY_PAGE_SIZE,(jrSummaryPage+1)*JR_SUMMARY_PAGE_SIZE);$("jr-summaries").replaceChildren();for(const row of rows)jrSummaryFinding($("jr-summaries"),row.finding,row.relations);
 if(!rows.length)jrText($("jr-summaries"),"p",remoteMismatch?(jrSummaryFailure===key?"当前选择的原文要点页暂不可读取。":"正在读取当前选择的已保存原文要点。"):(selection.group_id?"当前选择没有明确成交引用关联的已保存研究；可从完整目录阅读其他案例。":"此报告未保存可显示的研究要点。"),"jr-reader-note");
 $("jr-summary-count").textContent=remoteMismatch?"当前选择的原文要点":`原报告顺序 · 第 ${jrSummaryPage+1} / ${pages} 页 · ${total} 项要点`;$("jr-summary-count").dataset.total=remoteMismatch?0:total;$("jr-summary-prev").disabled=!!remoteMismatch||jrSummaryPage===0;$("jr-summary-next").disabled=!!remoteMismatch||jrSummaryPage>=pages-1;
 const group=DATA.groups.find(row=>row.id===selection.group_id),label=group?jrReadable(group.symbol):"全部已保存研究";$("jr-reading-scope").textContent=`${label}${selection.date?" · 固定日期 "+selection.date:""} · 以下为已保存原文要点，按原报告顺序展示。图窗筛选不重新分析或改写报告依据。`;if(!jrSummary)jrSummaryKey=key;
 if(remoteMismatch&&jrSummaryKey!==key)jrLoadSummary(0,selection)
}
async function jrLoadSummary(page,selection=jrSummarySelection()){
 const key=jrSummarySelectionKey(selection),request=++jrSummaryRequest;jrSummaryKey=key;jrSummaryFailure="";const params=new URLSearchParams({page:String(page)});if(selection.group_id){params.set("group",selection.group_id);if(selection.date)params.set("date",selection.date);if(selection.start&&selection.end){params.set("start",selection.start);params.set("end",selection.end)}}if(selection.asset!=="ALL")params.set("asset",selection.asset);if(selection.contract!=="ALL")params.set("contract",selection.contract);
 try{const response=await fetch("/summary?"+params,{credentials:"same-origin",cache:"no-store"});if(!response.ok)throw Error("summary unavailable");const body=await response.json(),summary=body.original_summary;if(!summary||!Array.isArray(summary.findings)||!summary.pagination)throw Error("summary unavailable");if(request!==jrSummaryRequest)return false;jrSummary=summary;jrPlans=summary.improvement_plan||[];jrRegisterSummary(summary);jrSummaryPage=summary.pagination.page||0;jrRender();return true}catch(error){if(request===jrSummaryRequest){jrSummaryFailure=key;$("jr-notice").textContent="当前原文要点页暂不可读取；已保存报告保持不变。";$("jr-summaries").replaceChildren();jrText($("jr-summaries"),"p","当前选择的原文要点页暂不可读取。","jr-reader-note")}return false}
}
function jrChangeSummaryPage(delta){if(jrSummary&&REVIEW.viewer_selection===true)return jrLoadSummary(jrSummaryPage+delta);jrSummaryPage+=delta;jrRender();return true}
function jrFocusRecord(identifier){
 const row=jrRecords.get(identifier);if(!row||!row.display_date){const reference=jrSummaryRecords.get(identifier);if(REVIEW.viewer_selection===true&&reference&&reference.group_id&&typeof window!=="undefined"&&window.location&&typeof window.location.assign==="function"){window.location.assign("/view?"+new URLSearchParams({kind:"group",id:reference.group_id})+"#record="+encodeURIComponent(identifier));return true}$("jr-notice").textContent="此成交未包含在当前保存资料，无法定位；原报告保持不变。";return false}
 const priorGroup=$("symbol").value;if(typeof jrClearCandleSelection==="function")jrClearCandleSelection();jrClearYearShortcut();$("asset").value="ALL";$("contract").value="ALL";$("start").value="";$("end").value="";$("symbol").value=row.group_id;$("segment").value="";selectedDate="";pageIndex=0;resetContracts();if(priorGroup!==row.group_id)clearChartFocus();ensureDateBounds();jrResetViewport();
 selectedDate=row.display_date;const sameDay=DATA.records.filter(item=>item.group_id===row.group_id&&item.display_date===row.display_date),index=sameDay.findIndex(item=>item.record_id===identifier);pageIndex=Math.max(0,Math.floor(index/PAGE_SIZE));chartFocusIds=new Set([identifier]);chartLessonEvents=jrEventsFor(jrSelectedFinding);$("trade-table").open=true;render();if(typeof jrPinCandle==="function")jrPinCandle(row.display_date,row.record_id);selectedDate=row.display_date;pageIndex=Math.max(0,Math.floor(index/PAGE_SIZE));render();showRecord(row);return true
}
function jrRecordButtons(parent,references,label="成交引用"){
 jrText(parent,"p",label,"jr-label");const box=document.createElement("div");box.className="jr-refs";
 for(const identifier of references||[]){const row=jrRecords.get(identifier),button=document.createElement("button");button.type="button";button.dataset.record=identifier;button.textContent=row?jrRecordLabel(row):jrSummaryRecords.has(identifier)?jrRefLabel(identifier):"此成交暂不可展示";button.addEventListener("click",()=>jrFocusRecord(identifier));box.appendChild(button)}
 if(!(references||[]).length)jrText(box,"span","无");parent.appendChild(box)
}
function jrEvidence(parent,references,label){
 jrText(parent,"p",label,"jr-label");if(!(references||[]).length){jrText(parent,"p","无");return}
 for(const identifier of references){const item=jrEvidenceById.get(identifier),box=document.createElement("div");box.className="jr-source";jrText(box,"strong",item&&item.title||"此资料暂不可展示");
 if(item){if(item.source_url){try{const url=new URL(item.source_url);if(url.protocol==="https:"&&!url.username&&!url.password){const a=document.createElement("a");a.href=item.source_url;a.target="_blank";a.rel="noopener noreferrer";a.textContent="打开公开原文（"+url.hostname+"）";box.appendChild(a)}}catch(error){}}
 const metadata=jrDetails(box,"公开来源、发布时间与使用限制");metadata.dataset.evidence=identifier;
 jrLine(metadata,"资料类型",jrCode(item.kind));
 for(const[key,title]of[["publication_date","发布日期"],["published_at","发布时刻"],["available_at","可用时刻"],["event_at","事件时刻"],["source_as_of","来源原始日期"],["as_of","事实截止"],["retrieved_at","取得时刻"],["availability_basis","可用时刻依据"],["available_at_basis","来源可用时刻依据"],["publication_precision","发布时间精度"],["vintage_status","历史资料状态"],["vintage_available_at","该版资料可用时刻"],["revised","修订标记"]])if(item[key]!=null)jrLine(metadata,title,item[key]);
 }parent.appendChild(box)}
}
function jrEventsFor(identifier){return (REVIEW.lesson_events||[]).filter(event=>!event.finding_ref||event.finding_ref===identifier)}
function jrShowEvent(event){
 const box=$("jr-event-detail");box.hidden=false;box.replaceChildren();jrText(box,"h3",event.title||"相关事件");jrLine(box,"相关性说明",event.relevance_note);jrLine(box,"冻结内容",event.content);jrLine(box,"可信时间锚",event.anchor_at||"未定位资料；不用事实截止或检索日期推测定位");
 for(const[identifier,date]of Object.entries(event.dates_by_record||{}))jrLine(box,jrRefLabel(identifier)+" · 证券当地日期",date);
 jrLine(box,"定位角色与精度",jrCode(event.anchor_role)+" · "+jrCode(event.publication_precision));
 for(const item of event.layers||[])jrLine(box,jrRefLabel(item.record_id)+" · "+jrCode(item.layer),item.reason);
 jrLine(box,"公开可得不等于已经阅读","这些层次是逐笔信息集，不是用户实际知晓证明。");jrEvidence(box,[event.evidence_id],"冻结公开来源")
}
function jrShowEventGroup(events,date){
 const box=$("jr-event-detail");box.hidden=false;box.replaceChildren();jrText(box,"h3",`${date} · ${events.length} 项事件标注`);jrText(box,"p","选择一项查看原证据、定位角色和逐笔信息分层；同日显示不表示相同因果关系。");const choices=document.createElement("div");choices.className="jr-event-choices";box.appendChild(choices);
 for(const event of events){const button=jrText(choices,"button",(event.title||"相关事件")+" · "+jrCode(event.anchor_role));button.type="button";button.dataset.event=event.evidence_id;button.dataset.anchorRole=event.anchor_role;button.addEventListener("click",()=>{jrShowEvent(event);const back=jrText(box,"button","返回该日事件列表");back.type="button";back.addEventListener("click",()=>jrShowEventGroup(events,date))})}
}
function jrLayer(parent,title,layer,fields){const box=jrDetails(parent,title);for(const[key,label]of fields)jrLine(box,label,layer[key]);for(const term of layer.terms||[]){jrLine(box,term.term,term.meaning);jrLine(box,"在本案中的应用",term.case_application)}const records=jrDetails(box,"本层完整成交引用");jrRecordButtons(records,layer.record_refs);jrEvidence(box,layer.evidence_refs,"本层来源");return box}
function jrLesson(parent,lesson){
 jrLine(parent,"焦点成交",jrRefLabel(lesson.focus_record_ref));jrLine(parent,"案例原图窗",`${lesson.chart_window.start} 至 ${lesson.chart_window.end} · ${jrRefLabel(lesson.chart_window.focus_instrument_key)}`);
 const beginner=jrLayer(parent,"初学 · 怎么看这张图",lesson.beginner,[["read_chart","读图"],["why_it_matters","与本案的关系"]]);beginner.open=true;
 jrLayer(parent,"练习 · 候选错误与验证",lesson.practice,[["possible_error","可能的问题"],["exercise","可验证练习"],["next_inputs","下次记录"],["verification","验证方式"]]);
 jrLayer(parent,"深入 · 替代解释与推翻条件",lesson.advanced,[["alternative_explanation","替代解释"],["falsifier","推翻条件"],["additional_evidence","还需要的证据"]]);jrLine(parent,"讲解限制",lesson.limits);
 const events=jrEventsFor(lesson.finding_ref),box=jrDetails(parent,"相关事件 · 当时 / 事后 / 不确定分层");
 for(const event of events){const button=jrText(box,"button",`${event.title||"相关事件"} · ${lessonEventDate(event,DATA.groups.find(group=>group.id===$("symbol").value))||"未定位"} · ${jrCode(event.anchor_role)}`);button.type="button";button.dataset.event=event.evidence_id;button.addEventListener("click",()=>jrShowEvent(event));for(const layer of event.layers||[])jrLine(box,jrRefLabel(layer.record_id)+" · "+jrCode(layer.layer),layer.reason)}
 if(!events.length)jrText(box,"p","此案例没有已定位事件；不补造时间锚或指数曲线。")
}
function jrCalculation(parent,identifier){
 const calculation=(REVIEW.calculations||{})[identifier],box=jrDetails(parent,jrRefLabel(identifier));if(!calculation){jrText(box,"p","此计算资料暂不可展示");return}
 jrLine(box,"计算状态",calculation.status);jrLine(box,"计算类别",calculation.kind);jrLine(box,"计价货币",calculation.currency);jrLine(box,"原始结果",calculation.metrics);jrLine(box,"核算假设",calculation.assumptions);jrLine(box,"数据限制",calculation.limitations);
 if(calculation.as_of)jrLine(box,"事实截止",calculation.as_of);if(calculation.retrieved_at)jrLine(box,"取得时刻",calculation.retrieved_at)
}
function jrFinding(parent,finding){
 const box=document.createElement("article");box.className="jr-item";box.dataset.finding=finding.finding_id;jrText(box,"h3",finding.pattern);const lesson=jrLessons.get(finding.finding_id);
 if(lesson)jrLesson(box,lesson);else jrText(box,"p","旧版报告未保存三层图表讲解；以下保留原研究内容。","jr-label");
 const original=jrDetails(box,lesson?"原发现与完整引用":"原发现与引用");if(!lesson)original.open=true;
 for(const[key,title]of[["process_observation","过程观察"],["result_observation","事后结果"],["interpretation","候选解释"],["confidence_limits","置信限制"]])jrLine(original,title,finding[key]);jrRecordButtons(original,finding.record_refs);
 for(const alternative of finding.alternative_explanations||[]){jrLine(original,"反例或替代解释",alternative.text);jrRecordButtons(original,alternative.record_refs,"反例成交引用 · 切换其独立标的图");const details=jrDetails(original,"反例片段与公开证据");jrRefs(details,"交易片段",alternative.episode_refs);jrEvidence(details,alternative.evidence_refs,"反例公开证据（保留原引用，不升级为当时背景）")}
 const details=jrDetails(original,"当时 / 事后背景与确定性计算原值");
 for(const[key,title]of[["episode_refs","交易片段"],["chart_refs","保存图表"],["calculation_refs","确定性计算"],["diary_refs","当时记录（日记原件未展示）"]])jrRefs(details,title,finding[key]);
 for(const intent of finding.intent_claims||[])jrLine(details,"当时记录 · "+jrRefLabel(intent.record_id),jrRefLabel(intent.diary_id)+" · "+jrCode(intent.layer));
 jrEvidence(details,finding.decision_evidence_refs,"当时可知背景 · 原报告当时层");jrEvidence(details,finding.outcome_evidence_refs,"事后结果证据 · 原报告事后层");jrEvidence(details,finding.uncertain_evidence_refs,"时刻 / 版本不确定 · 不作当时依据");
 for(const claim of finding.financial_claims||[]){const calculation=(REVIEW.calculations||{})[claim.calculation_ref]||{};jrLine(details,"金融原值",`${jrCode(claim.metric)} = ${jrValue(claim.value)} · ${jrValue(calculation.currency)} · ${jrRefLabel(claim.calculation_ref)}`)}
 for(const identifier of new Set([...(finding.calculation_refs||[]),...(finding.financial_claims||[]).map(claim=>claim.calculation_ref)]))jrCalculation(details,identifier);
 parent.appendChild(box)
}
function jrPlan(parent,plan){const box=document.createElement("article");box.className="jr-item";box.dataset.improvement=plan.improvement_id;jrText(box,"h3",plan.exercise||"复盘练习");jrLine(box,"原计划范围",jrPlanScope(plan));for(const[key,title]of[["exercise","练习"],["next_inputs","下次记录"],["verification","验证方式"],["review_window","复查窗口"],["status","练习进度"]])jrLine(box,title,plan[key]);const details=jrDetails(box,"对应成交、案例与公开证据");jrRecordButtons(details,plan.record_refs);jrText(details,"p","对应案例","jr-label");for(const identifier of plan.finding_refs||[]){const button=jrText(details,"button",jrRefLabel(identifier));button.type="button";button.addEventListener("click",()=>jrSelectFinding(identifier))}jrEvidence(details,plan.evidence_refs,"练习公开证据（不升级原分类）");parent.appendChild(box)}
function jrApplyLesson(lesson){
 const row=jrRecords.get(lesson.focus_record_ref);if(!row)return false;if(typeof jrClearCandleSelection==="function")jrClearCandleSelection();jrClearYearShortcut();$("symbol").value=row.group_id;$("asset").value="ALL";$("contract").value="ALL";$("start").value=lesson.chart_window.start;$("end").value=lesson.chart_window.end;$("segment").value="";selectedDate="";pageIndex=0;resetContracts();chartFocusIds=new Set([lesson.focus_record_ref,...lesson.chart_window.record_refs]);chartFocusWindow={...lesson.chart_window,group_id:row.group_id};chartLessonEvents=jrEventsFor(lesson.finding_ref);ensureDateBounds();jrResetViewport();render();if(typeof jrPinCandle==="function")jrPinCandle(row.display_date,row.record_id);showRecord(row);$("trade-table").open=false;return true
}
function jrSelectFinding(identifier){jrSelectedFinding=identifier;jrSelectedPlan="";$("jr-plan").value="";$("jr-event-detail").hidden=true;const finding=jrFindings.find(row=>row.finding_id===identifier);if(!finding){if(REVIEW.viewer_selection===true&&(jrDirectory.some(row=>row.finding_id===identifier)||(jrSummary&&jrSummary.findings||[]).some(row=>row.finding_id===identifier))&&typeof window!=="undefined"&&window.location&&typeof window.location.assign==="function"){window.location.assign("/view?"+new URLSearchParams({kind:"case",id:identifier}));return true}jrRender();return false}const lesson=jrLessons.get(identifier);if(lesson)jrApplyLesson(lesson);else if(finding.record_refs&&finding.record_refs.length)jrFocusRecord(finding.record_refs[0]);jrRender();return true}
function jrRender(){
 jrRememberPanes();const current=jrCurrentRecords(),query=$("jr-search").value.trim().toLocaleLowerCase(),matches=item=>!query||jrReadable(item).toLocaleLowerCase().includes(query),entries=jrDirectory.filter(row=>(jrMode==="ALL"||jrRelatedRecords(row).some(id=>current.has(id)))&&matches(row)),plans=jrPlans.filter(matches);
 $("jr-case").replaceChildren();option($("jr-case"),"","请选择案例");for(const item of entries)option($("jr-case"),item.finding_id,jrReadable(item.pattern||"复盘案例"));if(entries.some(row=>row.finding_id===jrSelectedFinding))$("jr-case").value=jrSelectedFinding;
 $("jr-plan").replaceChildren();option($("jr-plan"),"","请选择练习");for(const plan of plans)option($("jr-plan"),plan.improvement_id,jrReadable(plan.exercise||"复盘练习"));if(plans.some(row=>row.improvement_id===jrSelectedPlan))$("jr-plan").value=jrSelectedPlan;
 $("jr-findings").replaceChildren();$("jr-plans").replaceChildren();const selected=jrFindings.find(row=>row.finding_id===jrSelectedFinding);if(selected)jrFinding($("jr-findings"),selected);$("jr-selected-title").hidden=!selected;const shownPlans=jrSelectedPlan?jrPlans.filter(row=>row.improvement_id===jrSelectedPlan):jrPlans;for(const plan of shownPlans)jrPlan($("jr-plans"),plan);if(!shownPlans.length)jrText($("jr-plans"),"p",$("symbol").value?"当前选择没有明确成交引用关联的已有改进计划；可恢复全部要点阅读原计划。":"此版本未保存可显示的改进计划。","jr-reader-note");jrRenderSummaries();jrRestorePanes();
 $("jr-count").textContent=`案例 ${entries.length}/${jrDirectory.length} · 练习 ${plans.length}/${jrPlans.length}`;$("jr-count").dataset.findings=entries.length;$("jr-count").dataset.plans=plans.length;$("jr-notice").textContent=selected?"以下完整讲解来自所选案例；当前图窗可操作，报告依据与原判断保持不变。":""
}
const jrChartRender=render;render=function(){jrChartRender();jrRender()};
$("jr-scope").addEventListener("change",()=>{jrMode=$("jr-scope").value;jrRender()});$("jr-search").addEventListener("input",jrRender);$("jr-case").addEventListener("change",()=>jrSelectFinding($("jr-case").value));$("jr-plan").addEventListener("change",()=>{jrSelectedPlan=$("jr-plan").value;jrSelectedFinding="";jrRender()});$("jr-all").addEventListener("click",()=>{jrMode="ALL";$("jr-scope").value="ALL";$("jr-search").value="";jrRender()});
$("jr-summary-prev").addEventListener("click",()=>jrChangeSummaryPage(-1));$("jr-summary-next").addEventListener("click",()=>jrChangeSummaryPage(1));
const progress=REVIEW.progress||{status:"未提供",analyzed_episode_ids:[],pending_episode_ids:[],total_units:0},scope=REVIEW.scope||{mode:"已选择投影",record_ids:[],asset_types:[],coverage:{}},basis=REVIEW.report_basis||{mode:scope.mode,record_count:(scope.record_ids||[]).length,context_record_count:(scope.context_record_ids||[]).length,excluded_record_count:(scope.excluded_record_ids||[]).length,asset_types:scope.asset_types,record_start:scope.coverage&&scope.coverage.actual_start,record_end:scope.coverage&&scope.coverage.actual_end,coverage:scope.coverage},limitations=REVIEW.limitations||[],jrAnalyzedCount=Number.isInteger(progress.analyzed_count)&&progress.analyzed_count>=0?progress.analyzed_count:(progress.analyzed_episode_ids||[]).length,jrPendingCount=Number.isInteger(progress.pending_count)&&progress.pending_count>=0?progress.pending_count:(progress.pending_episode_ids||[]).length;
$("jr-progress").textContent=`${jrCode(progress.status)} · 已分析 ${jrAnalyzedCount} / 待分析 ${jrPendingCount}`;
$("jr-reading-limits").textContent=`资料截止：${jrValue(REVIEW.cutoff)} · 资料覆盖：${jrCode((basis.coverage||{}).status)}${((basis.coverage||{}).gaps||[]).length?"\n覆盖缺口："+jrValue(basis.coverage.gaps):""}${(scope.limitations||[]).length?"\n原数据计算限制："+scope.limitations.map(jrValue).join("；"):""}${limitations.length?"\n原报告限制："+limitations.map(jrValue).join("；"):""}`;
$("jr-summary").textContent=`报告依据：${jrCode(basis.mode)} · ${basis.record_count} 笔分析记录 · 类别 ${(basis.asset_types||[]).map(jrCode).join(" / ")}\n报告成交范围：${jrValue(basis.record_start)} 至 ${jrValue(basis.record_end)}\n请求区间：${jrValue((basis.coverage||{}).requested_window||"未指定区间，依据全部已保存记录")}\n来源返回范围：${jrValue((basis.coverage||{}).actual_start)} 至 ${jrValue((basis.coverage||{}).actual_end)} · ${jrCode((basis.coverage||{}).status)}\n覆盖缺口：${jrValue((basis.coverage||{}).gaps||[])}\n分析进度：已分析 ${jrAnalyzedCount}，待分析 ${jrPendingCount}，共 ${progress.total_units} 个单元。分析完成不等于所选期间资料完整。\n日期筛选和缩放仅改变当前图窗，不重新分析或重算已保存统计。\n资料限制：${limitations.map(jrValue).join("；")||"未提供"}`;
for(const[label,item]of[["报告日期",REVIEW.report_as_of],["资料截止",REVIEW.cutoff],["报告依据范围",jrCode(basis.mode)],["分析记录数",basis.record_count],["背景记录数",basis.context_record_count],["排除记录数",basis.excluded_record_count],["资产类别",(basis.asset_types||[]).map(jrCode)],["报告成交范围",`${jrValue(basis.record_start)} 至 ${jrValue(basis.record_end)}`],["请求区间",(basis.coverage||{}).requested_window||"未指定区间，依据全部已保存记录"],["来源返回范围",`${jrValue((basis.coverage||{}).actual_start)} 至 ${jrValue((basis.coverage||{}).actual_end)}`],["覆盖缺口",(basis.coverage||{}).gaps||[]],["覆盖说明",jrCode((basis.coverage||{}).status)],["分析进度",`${jrCode(progress.status)} · 已分析 ${jrAnalyzedCount}，待分析 ${jrPendingCount}`],["来源与数据限制",limitations]])jrLine($("jr-metadata"),label,item);
for(const observation of (basis.coverage||{}).observations||[])jrLine($("jr-metadata"),"来源覆盖观察",`${jrValue(observation.actual_start)} 至 ${jrValue(observation.actual_end)} · ${jrCode(observation.status)} · ${jrCode(observation.collection_mode)}`);
for(const[phase,item]of Object.entries(REVIEW.phase_coverage||{}))jrLine($("jr-metadata"),jrCode(phase)+"分析",jrCode(item.status)+" · "+jrValue(item.reason));
if(REVIEW.case_selection){const reasons=REVIEW.case_selection.selected_reasons||{};if(Array.isArray(reasons))jrLine($("jr-metadata"),"案例选择理由",reasons);else for(const[identifier,reason]of Object.entries(reasons))jrLine($("jr-metadata"),"案例选择 · "+jrRefLabel(identifier),reason);for(const[category,identifiers]of Object.entries(REVIEW.case_selection.available_by_result||{}))jrLine($("jr-metadata"),jrCode(category)+"数量",Array.isArray(identifiers)?identifiers.length:"未提供");jrLine($("jr-metadata"),"未覆盖案例类别",REVIEW.case_selection.omitted_classes)}
jrRender();if(REVIEW.initial_finding_id)jrSelectFinding(REVIEW.initial_finding_id);if(REVIEW.viewer_selection===true&&typeof window!=="undefined"&&window.location){const identifier=new URLSearchParams((window.location.hash||"").replace(/^#/,"")).get("record");if(identifier&&jrRecords.has(identifier))jrFocusRecord(identifier)}
'''
