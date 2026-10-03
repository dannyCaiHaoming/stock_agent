"""合并查看的保存边界与真实生成脚本；仅使用合成私人材料。"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import unittest

from product.trading_journal.analysis import analyze_records
from product.trading_journal.common import canonical_hash, canonical_json
from product.trading_journal.reflection import PHASES, ReflectionError, assemble_report, prepare_reflection, save_report
from product.trading_journal.review import load_review, render_review, render_review_payload, save_review
from product.trading_journal.viewer import ReviewProjection
from tests.test_trading_journal_charts import _DOM_RUNNER, candle, instrument, market, record, snapshot as chart_snapshot
from tests.test_trading_journal_reflection import evidence, packet as basic_packet, report as basic_report


CUTOFF = "2026-10-02T13:22:30Z"
REPORT_ID = "reflection-" + "a" * 32


def fixture(*, bulk=False):
    rows = [record("acme-2024", occurred_at="2024-09-01T15:10:00Z"),
            record("acme-2026", occurred_at="2026-09-01T15:10:00Z"),
            record("beta-2025", symbol="BETA", occurred_at="2025-09-01T15:10:00Z"),
            record("beta-2026", symbol="BETA", occurred_at="2026-09-01T15:10:00Z"),
            record("fund-2026", asset_type="ETF", symbol="FUND"),
            record("call-2026", asset_type="OPTION", symbol="ACME261016C100", price="2"),
            record("put-2026", asset_type="OPTION", symbol="ACME261120P100", price="3", instrument=instrument("OPTION", "ACME261120P100", expiry="2026-11-20", right="PUT"))]
    if bulk:
        rows += [record(f"beta-bulk-{index}", symbol="BETA", occurred_at="2026-09-02T15:10:00Z") for index in range(220)]
    for row in rows:
        row["fees_complete"] = False
    quotes = [market(candles=[candle("2024-09-01"), candle("2026-09-01")]),
              market(instrument_key="US:USD:BETA", symbol="BETA", candles=[candle("2025-09-01"), candle("2026-09-01"), candle("2026-09-02")]),
              market(instrument_key="US:USD:FUND", symbol="FUND")]
    snapshot = {"kind": "TradeJournalSnapshot", "schema_version": "1.0.0", "snapshot_id": "snapshot-synthetic-review", "source_id": "synthetic:journal", "as_of": CUTOFF, "retrieved_at": CUTOFF, "account_ref": "SYNTHETIC_PRIVATE_ACCOUNT_REF", "records": rows, "context_records": [], "opening_positions": {}, "coverage": {"status": "PARTIAL", "account_start": None, "account_ref": "SYNTHETIC_COVERAGE_ACCOUNT_REF", "actual_start": "2024-09-01", "actual_end": "2026-09-02", "gaps": [{"reason": "ACCOUNT_START_UNKNOWN"}]}, "analysis": analyze_records(rows), "market": quotes}
    snapshot["input_hash"] = canonical_hash({key: snapshot[key] for key in ("records", "context_records", "opening_positions", "coverage", "analysis", "market")})
    materials = [evidence("prior", "2023-01-01T14:00:00Z", record_refs=[row["record_id"] for row in rows], title="当时可知合成资料", source_url="https://example.org/public/prior", raw="SYNTHETIC_RAW_EVIDENCE"),
                 evidence("later", "2026-10-01T14:00:00Z", record_refs=[row["record_id"] for row in rows], title="事后合成资料", source_url="https://example.org/public/later"),
                 evidence("uncertain", "2026-01-05", record_refs=[row["record_id"] for row in rows], publication_precision="DATE", title="只有日期的合成资料", source_url="javascript:alert(1)")]
    diary = [{"diary_id": "synthetic-diary", "record_refs": ["acme-2026"], "recorded_at": "2026-09-01T14:00:00Z", "source_id": "synthetic:diary", "as_of": "2026-09-01T14:00:00Z", "retrieved_at": CUTOFF, "text": "SYNTHETIC_RAW_DIARY"}]
    packet = prepare_reflection(snapshot, cutoff=CUTOFF, evidence=materials, diary=diary, chart_refs=["chart:synthetic-review"])
    findings = []
    for row in rows:
        identifier = row["record_id"]
        findings.append({"finding_id": "finding-" + identifier, "pattern": "合成观察 " + identifier, "record_refs": [identifier], "episode_refs": ["activity:" + identifier], "chart_refs": ["chart:synthetic-review"], "calculation_refs": ["episode:activity:" + identifier], "diary_refs": ["synthetic-diary"] if identifier == "acme-2026" else [], "process_observation": "可核验的合成成交过程", "result_observation": "不计算缺少完整条件的收益", "interpretation": "候选解释，不推断动机", "confidence_limits": "合成材料，不证明真实研究质量", "decision_evidence_refs": ["prior"], "outcome_evidence_refs": ["later"], "uncertain_evidence_refs": ["uncertain"], "alternative_explanations": [{"text": "此样例的其他解释", "record_refs": [], "episode_refs": [], "evidence_refs": ["uncertain"]}], "financial_claims": [{"calculation_ref": "episode:activity:" + identifier, "metric": "net_pnl", "value": None}]})
    # This finding is relevant to BETA only through its alternative, not the
    # original main record_refs. The source fields must stay unchanged.
    findings[0]["alternative_explanations"][0].update(record_refs=["beta-2025"], episode_refs=["activity:beta-2025"])
    plan = [{"improvement_id": "practice-stock", "finding_refs": ["finding-acme-2024"], "record_refs": ["acme-2024"], "evidence_refs": ["prior"], "exercise": "记录原计划", "next_inputs": ["计划与失效条件"], "verification": "核验记录时间", "review_window": "四周", "status": "PROPOSED"},
            {"improvement_id": "practice-option", "finding_refs": ["finding-call-2026"], "record_refs": ["call-2026"], "evidence_refs": ["uncertain"], "exercise": "记录完整合约", "next_inputs": ["到期、乘数和开平仓"], "verification": "与原始事实对照", "review_window": "四周", "status": "PROPOSED"}]
    report = assemble_report(packet, findings=findings, improvement_plan=plan, model_version="synthetic-no-model-call", skill_version="1.0.0", phase_coverage={phase: {"status": "DATA_LIMITED", "reason": "合成边界案例"} for phase in PHASES}, report_as_of="2026-10-02T15:00:00Z", analyzed_episode_ids=["activity:" + row["record_id"] for row in rows])
    report["report_id"] = REPORT_ID
    return report, packet


def data_projection(page, identifier="reflection-data"):
    return json.loads(re.search(r'<script id="' + identifier + r'" type="application/json">(.*?)</script>', page, re.S)[1])


def lesson_fixture(*, bulk=False):
    report, packet = fixture(bulk=bulk)
    rows = {row["record_id"]: row for row in packet["snapshot"]["records"]}
    lessons = []
    for finding in report["findings"]:
        identifier = finding["record_refs"][0]
        row = rows[identifier]
        day = row["occurred_at"][:10]
        layers = {"record_refs": [identifier], "evidence_refs": ["prior", "later", "uncertain"]}
        lessons.append({"finding_ref": finding["finding_id"], "focus_record_ref": identifier,
                        "chart_window": {"start": day, "end": "2026-10-02" if identifier == "acme-2026" else day,
                                         "record_refs": [identifier], "focus_instrument_key": row["instrument"]["key"]},
                        "beginner": {"read_chart": "合成初学读图说明", "why_it_matters": "连接本案成交与标的路径",
                                     "terms": [{"term": "日 K", "meaning": "冻结日线", "case_application": "只读已取得日线"}], **deepcopy(layers)},
                        "practice": {"possible_error": "候选问题，不推断动机", "exercise": "记录可验证的计划",
                                     "next_inputs": ["计划", "失效条件"], "verification": "检查记录时间", **deepcopy(layers)},
                        "advanced": {"alternative_explanation": "其他解释仍可能成立", "falsifier": "新证据可推翻候选解释",
                                     "additional_evidence": "需要当时计划", **deepcopy(layers)},
                        "event_links": [{"evidence_ref": "later", "record_refs": [identifier], "anchor_role": "AVAILABLE_AT", "relevance_note": "冻结事后资料"},
                                        {"evidence_ref": "uncertain", "record_refs": [identifier], "anchor_role": "UNPLACED", "relevance_note": "仅日期，保持不确定"}],
                        "limits": ["合成案例，不证明真实内容质量"]})
    report["schema_version"] = "1.1.0"
    report["case_lessons"] = lessons
    return report, packet


def same_day_event_fixture():
    report, original = lesson_fixture()
    materials = deepcopy(original["evidence"])
    second = deepcopy(next(row for row in materials if row["evidence_id"] == "later"))
    second.update(evidence_id="later-second", title="第二条冻结事件", content="第二条独立冻结内容", available_at="2026-10-01T15:00:00Z", event_at="2026-10-01T12:00:00Z")
    materials.append(second)
    packet = prepare_reflection(original["snapshot"], cutoff=original["cutoff"], evidence=materials, diary=original["diary"], chart_refs=["chart:synthetic-review"])
    next(row for row in report["findings"] if row["finding_id"] == "finding-acme-2026")["outcome_evidence_refs"].append("later-second")
    lesson = next(row for row in report["case_lessons"] if row["finding_ref"] == "finding-acme-2026")
    lesson["event_links"] += [{"evidence_ref": "later-second", "record_refs": ["acme-2026"], "anchor_role": role, "relevance_note": "保留此证据的原定位角色"} for role in ("AVAILABLE_AT", "EVENT_AT")]
    result = assemble_report(packet, findings=report["findings"], improvement_plan=report["improvement_plan"], case_lessons=report["case_lessons"], model_version=report["model_version"], skill_version="1.1.0", phase_coverage=report["phase_coverage"], report_as_of=report["report_as_of"], analyzed_episode_ids=report["progress"]["analyzed_episode_ids"])
    return result, packet


def ledger_coverage_fixture():
    old_report, original = fixture()
    snap = deepcopy(original["snapshot"])
    request = {"start": "2024-08-01T00:00:00+08:00", "end": "2026-09-30T23:59:59+08:00", "timezone": "Asia/Shanghai"}
    snap["coverage"] = {
        "status": "PARTIAL", "requested_window": request,
        "observations": [{"actual_start": "2024-09-01T15:10:00Z", "actual_end": "2026-09-02T15:10:00Z", "request": request,
                          "collection_mode": "COMPUTER_USE_EXPORT", "status": "PARTIAL", "source_id": "source-coverage-hidden",
                          "source_path": "/Users/example/private-source.csv", "account_ref": "PRIVATE_COVERAGE_REF"}],
        "gaps": [{"code": "SOURCE_WINDOW_CLIPPED", "message": "来源未返回所请求区间的全部记录", "asset_type": "OPTION",
                  "account_ref": "PRIVATE_GAP_REF", "source_path": "/Users/example/gap-private.csv"}],
    }
    snap["analysis"] = analyze_records(snap["records"], window=request, opening_positions=snap["opening_positions"])
    snap["input_hash"] = canonical_hash({key: snap[key] for key in ("records", "context_records", "opening_positions", "coverage", "analysis", "market")})
    packet = prepare_reflection(snap, cutoff=CUTOFF, evidence=original["evidence"], diary=original["diary"], chart_refs=original["chart_refs"])
    report = assemble_report(packet, findings=old_report["findings"], improvement_plan=old_report["improvement_plan"],
                             model_version=old_report["model_version"], skill_version=old_report["skill_version"], phase_coverage=old_report["phase_coverage"],
                             report_as_of=old_report["report_as_of"], analyzed_episode_ids=old_report["progress"]["analyzed_episode_ids"])
    return report, packet


def execute(page, scenario, *, asynchronous=False, location_hash=None):
    # Reuse the chart tests' native-select model, adapting only initialization
    # of the second data block. It executes the actual combined page script.
    original = 'ids["journal-data"].textContent=html.match(/<script id="journal-data" type="application\\/json">(.*?)<\\/script>/s)[1];'
    replacement = 'for(const match of html.matchAll(/<script id="([^"]+)" type="application\\/json">(.*?)<\\/script>/gs))ids[match[1]].textContent=match[2];'
    assert original in _DOM_RUNNER
    runner = _DOM_RUNNER.replace(original, replacement)
    emit = ('Promise.resolve(outcome).then(value=>console.log(JSON.stringify(value))).catch(error=>{console.error(error);process.exitCode=1});'
            if asynchronous else 'console.log(JSON.stringify(outcome));')
    # Scenarios are code, serialized once rather than nested in a template
    # literal which would consume JSON escapes in frozen group identities.
    before = 'window.location={hash:' + json.dumps(location_hash) + '};\n' if location_hash is not None else ''
    runner = runner[:runner.index('eval(script+`')] + before + 'eval(script+' + json.dumps("\n" + scenario + "\n" + emit) + ');\n'
    with tempfile.TemporaryDirectory(prefix="journal-review-dom-") as temp:
        path = Path(temp) / "review.html"
        path.write_text(page, encoding="utf-8")
        script = Path(temp) / "run.cjs"
        script.write_text(runner, encoding="utf-8")
        result = subprocess.run([shutil.which("node"), str(script), str(path)], capture_output=True, text=True, timeout=60)
        if result.returncode:
            raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class ReviewRenderingTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("node"), "需要 Node 验证原文阅读状态")
    def test_default_original_points_and_all_five_plans_are_visible(self):
        report, packet = lesson_fixture()
        for number in range(3, 6):
            plan = deepcopy(report["improvement_plan"][0])
            plan.update(improvement_id=f"practice-synthetic-{number}", exercise=f"原报告建议第{number}项",
                        verification=f"原报告验证方式第{number}项")
            report["improvement_plan"].append(plan)
        before = deepcopy((report, packet))
        page = render_review(report, packet)
        observed = execute(page, r'''
const visible=element=>element.tagName==="details"&&!element.open?element.children[0].textContent:(element._text||"")+element.children.map(visible).join("");
const outcome={points:$("jr-summaries").children.filter(row=>row.dataset.summaryFinding).map(row=>row.dataset.summaryFinding),text:visible($("jr-summaries")),plans:$("jr-plans").children.map(row=>row.dataset.improvement),advice:visible($("jr-plans")),fullCases:$("jr-findings").children.length,limits:$("jr-reading-limits").textContent};
''')
        self.assertEqual(observed["points"], [row["finding_id"] for row in report["findings"]])
        self.assertEqual(observed["plans"], [row["improvement_id"] for row in report["improvement_plan"]])
        for finding in report["findings"]:
            for field in ("process_observation", "result_observation", "interpretation", "confidence_limits"):
                self.assertIn(finding[field], observed["text"])
        for plan in report["improvement_plan"]:
            self.assertIn(plan["exercise"], observed["advice"])
            self.assertIn(plan["verification"], observed["advice"])
        self.assertEqual(observed["fullCases"], 0)
        self.assertIn("部分覆盖", observed["limits"])
        self.assertIn("开户起点尚未核实", observed["limits"])
        self.assertIn("原数据计算限制", observed["limits"])
        self.assertIn("币种未知", observed["limits"])
        self.assertNotIn("冻结公开来源", observed["text"])
        for identifier in ("jr-directory", "jr-data-explanation"):
            self.assertNotIn("open", re.search(r'<details id="' + identifier + r'"[^>]*>', page)[0])
        self.assertEqual((report, packet), before)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 验证事实关联")
    def test_summary_main_alternative_and_practice_use_their_own_record_refs(self):
        report, packet = lesson_fixture()
        finding = report["findings"][0]
        finding.update(process_observation="主样本A的原过程", interpretation="主样本A的原解释")
        finding["alternative_explanations"][0]["text"] = "反例B的原替代解释"
        lesson = report["case_lessons"][0]
        lesson["practice"].update(record_refs=["beta-2025"], exercise="仅关联反例B的原练习")
        plan = report["improvement_plan"][0]
        plan.update(record_refs=["acme-2024", "beta-2025"], finding_refs=[finding["finding_id"], "finding-beta-2025"])
        before = deepcopy((report, packet))
        observed = execute(render_review(report, packet), r'''
const select=symbol=>{$("symbol").value=DATA.groups.find(row=>row.symbol===symbol).id;$("symbol").listeners.change()},points=()=>$("jr-summaries").children.map(row=>row.dataset.summaryFinding),outcome={};
select("ACME");outcome.main=$("jr-summaries").textContent;outcome.mainPlans=$("jr-plans").textContent;outcome.range=[$("start").value,$("end").value];
select("BETA");outcome.counter=$("jr-summaries").textContent;outcome.counterPlans=$("jr-plans").textContent;outcome.betaAll=points();
jrPinCandle("2026-09-01");outcome.otherDay=$("jr-summaries").textContent;outcome.dayPoints=points();outcome.selectedDate=selectedDate;
''')
        self.assertIn("主样本A的原过程", observed["main"])
        self.assertNotIn("仅关联反例B的原练习", observed["main"])
        self.assertNotIn("反例B的原替代解释", observed["main"])
        self.assertIn("反例B的原替代解释", observed["counter"])
        self.assertIn("仅关联反例B的原练习", observed["counter"])
        self.assertIn("当前选择在此案例中是反例", observed["counter"])
        self.assertNotIn("主样本A的原过程", observed["counter"])
        self.assertNotIn("主样本A的原解释", observed["counter"])
        for text in (observed["mainPlans"], observed["counterPlans"]):
            self.assertIn("跨标的建议", text)
            self.assertIn("ACME / BETA", text)
        self.assertEqual(observed["range"], ["2024-09-01", "2026-09-01"])
        self.assertEqual(observed["dayPoints"], ["finding-beta-2026"])
        self.assertNotIn("反例B的原替代解释", observed["otherDay"])
        self.assertEqual(observed["selectedDate"], "2026-09-01")
        self.assertEqual((report, packet), before)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 验证分页与图窗分离")
    def test_original_point_pagination_preserves_order_and_chart_viewport(self):
        report, packet = lesson_fixture(bulk=True)
        before = deepcopy((report, packet))
        observed = execute(render_review(report, packet), r'''
const points=()=>$("jr-summaries").children.filter(row=>row.dataset.summaryFinding).map(row=>row.dataset.summaryFinding),outcome={first:points()};$("jr-summary-next").listeners.click();outcome.second=points();
$("symbol").value=DATA.groups.find(row=>row.symbol==="BETA").id;$("symbol").listeners.change();jrPinCandle("2026-09-02");$("zoom-in").listeners.click();
const state=()=>JSON.stringify({viewport:chartViewport,selectedDate,start:$("start").value,end:$("end").value});outcome.chartBefore=state();outcome.filteredFirst=points();outcome.total=$("jr-summary-count").dataset.total;$("jr-summary-next").listeners.click();outcome.filteredSecond=points();outcome.chartAfter=state();
jrPreviewCandle("2026-09-01");outcome.afterHover=points();outcome.afterHoverDate=selectedDate;
''')
        ids = [row["finding_id"] for row in report["findings"]]
        self.assertEqual(observed["first"], ids[:12])
        self.assertEqual(observed["second"], ids[12:24])
        self.assertEqual(observed["filteredFirst"], [f"finding-beta-bulk-{index}" for index in range(12)])
        self.assertEqual(observed["filteredSecond"], [f"finding-beta-bulk-{index}" for index in range(12, 24)])
        self.assertEqual(observed["total"], "220")
        self.assertEqual(observed["chartBefore"], observed["chartAfter"])
        self.assertEqual(observed["afterHover"], observed["filteredSecond"])
        self.assertEqual(observed["afterHoverDate"], "2026-09-02")
        self.assertEqual((report, packet), before)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 验证最小摘要投影")
    def test_viewer_summary_initial_text_is_readable_without_case_body(self):
        report, packet = lesson_fixture()
        before = deepcopy((report, packet))
        chart, review = ReviewProjection(report, packet).select("summary", "0")
        page = render_review_payload(chart, review)
        observed = execute(page, r'''const outcome={points:$("jr-summaries").textContent,plans:$("jr-plans").textContent,full:$("jr-findings").children.length,records:DATA.records.length,findings:jrFindings.length,evidence:jrEvidenceById.size};''')
        self.assertIn(report["findings"][0]["process_observation"], observed["points"])
        self.assertIn(report["case_lessons"][0]["practice"]["exercise"], observed["points"])
        self.assertIn(report["improvement_plan"][0]["verification"], observed["plans"])
        self.assertEqual((observed["full"], observed["records"], observed["findings"], observed["evidence"]), (0, 0, 0, 0))
        for excluded in ("SYNTHETIC_RAW_DIARY", "SYNTHETIC_RAW_EVIDENCE", "SYNTHETIC_PRIVATE_ACCOUNT_REF"):
            self.assertNotIn(excluded, page)
        self.assertEqual((report, packet), before)

    def test_same_origin_summary_policy_only_applies_to_trusted_viewer_projection(self):
        report, packet = fixture()
        offline = render_review(report, packet)
        self.assertIn("connect-src 'none'", offline)
        self.assertNotIn("connect-src 'self'", offline)
        chart, review = ReviewProjection(report, packet).select("summary", "0")
        served = render_review_payload(chart, review)
        self.assertIn("connect-src 'self'", served)
        self.assertNotIn("connect-src 'none'", served)
        for invalid in (False, None, "true", 1):
            review["viewer_selection"] = invalid
            page = render_review_payload(chart, review)
            self.assertIn("connect-src 'none'", page)
            self.assertNotIn("connect-src 'self'", page)
        self.assertIn("img-src 'none'", served)
        self.assertIn("base-uri 'none'; form-action 'none'", served)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 验证窗口与地址边界")
    def test_viewer_with_resize_window_without_location_still_renders_original_summary(self):
        report, packet = lesson_fixture()
        chart, review = ReviewProjection(report, packet).select("summary", "0")
        observed = execute(render_review_payload(chart, review), r'''const outcome={hasWindow:typeof window!=="undefined",hasLocation:!!window.location,points:$("jr-summaries").textContent,selectedDate,detail:$("detail").dataset.record||null};outcome.caseNavigation=jrSelectFinding(jrSummary.findings[0].finding_id);outcome.tradeNavigation=jrFocusRecord(jrSummary.findings[0].record_refs[0]);''')
        self.assertTrue(observed["hasWindow"])
        self.assertFalse(observed["hasLocation"])
        self.assertIn(report["findings"][0]["interpretation"], observed["points"])
        self.assertEqual(observed["selectedDate"], "")
        self.assertIsNone(observed["detail"])
        self.assertFalse(observed["caseNavigation"])
        self.assertFalse(observed["tradeNavigation"])

    @unittest.skipUnless(shutil.which("node"), "需要 Node 验证真实地址片段定位仍保留")
    def test_present_location_fragment_focuses_only_a_projected_trade(self):
        report, packet = fixture()
        projection = ReviewProjection(report, packet)
        group = next(row["id"] for row in projection.chart["groups"] if row["symbol"] == "BETA")
        chart, review = projection.select("group", group)
        # Fragment behavior is independent of summary fetching, which is tested
        # separately with a fixed same-origin response stub.
        review.pop("original_summary")
        page = render_review_payload(chart, review)
        scenario = r'''const outcome={selectedDate,detail:$("detail").dataset.record||null,rows:$("rows").children.map(row=>row.dataset.record),pinnedDate};'''
        known = execute(page, scenario, location_hash="#record=beta-2026")
        self.assertEqual(known["detail"], "beta-2026")
        self.assertEqual(known["selectedDate"], "2026-09-01")
        self.assertEqual(known["pinnedDate"], "2026-09-01")
        self.assertEqual(known["rows"], ["beta-2026"])
        unknown = execute(page, scenario, location_hash="#record=acme-2026")
        self.assertIsNone(unknown["detail"])
        self.assertEqual(unknown["selectedDate"], "")
        self.assertEqual(unknown["rows"], ["beta-2025", "beta-2026"])

    @unittest.skipUnless(shutil.which("node"), "需要 Node 验证同源摘要分页")
    def test_remote_summary_pagination_updates_only_prose_and_keeps_reading_state(self):
        report, packet = lesson_fixture(bulk=True)
        projection = ReviewProjection(report, packet)
        group_id = next(row["id"] for row in projection.chart["groups"] if row["symbol"] == "BETA")
        chart, review = projection.select("group", group_id)
        selection = {"group_id": group_id, "date": "2026-09-02", "asset": "ALL", "contract": "ALL", "start": "2025-09-01", "end": "2026-09-02"}
        review["original_summary"] = projection.summary(**selection)
        response = {"original_summary": projection.summary(**selection, page=1)}
        first_response = {"original_summary": deepcopy(review["original_summary"])}
        scenario = r'''
jrPinCandle("2026-09-02");$("zoom-in").listeners.click();const before=JSON.stringify({viewport:chartViewport,selectedDate,start:$("start").value,end:$("end").value});
const panes=$("jr-summaries").children.flatMap(row=>row.children).filter(row=>row.tagName==="details");panes[0].open=true;panes[0].listeners.toggle();
window.location={hash:""};const calls=[];globalThis.fetch=async(url,options)=>{calls.push({url,options});return {ok:true,json:async()=>(new URL(url,"https://example.invalid").searchParams.get("page")==="1"?__RESPONSE__:__FIRST_RESPONSE__)}};
const outcome=(async()=>{const success=await jrChangeSummaryPage(1),state={success,points:$("jr-summaries").children.filter(row=>row.dataset.summaryFinding).map(row=>row.dataset.summaryFinding),before,after:JSON.stringify({viewport:chartViewport,selectedDate,start:$("start").value,end:$("end").value}),summarySize:jrSummary.findings.length,evidence:jrEvidenceById.size};state.returned=await jrChangeSummaryPage(-1);state.openOnReturn=$("jr-summaries").children[0].children.filter(row=>row.tagName==="details")[0].open;state.calls=calls;return state})();
'''.replace("__FIRST_RESPONSE__", canonical_json(first_response)).replace("__RESPONSE__", canonical_json(response))
        observed = execute(render_review_payload(chart, review), scenario, asynchronous=True)
        self.assertTrue(observed["success"])
        self.assertEqual(len(observed["calls"]), 2)
        self.assertIn("/summary?page=1&group=", observed["calls"][0]["url"])
        self.assertIn("date=2026-09-02", observed["calls"][0]["url"])
        self.assertEqual(observed["calls"][0]["options"], {"credentials": "same-origin", "cache": "no-store"})
        self.assertEqual(observed["points"], [f"finding-beta-bulk-{index}" for index in range(12, 24)])
        self.assertEqual(observed["before"], observed["after"])
        self.assertEqual((observed["summarySize"], observed["evidence"]), (12, 0))
        self.assertTrue(observed["returned"])
        self.assertTrue(observed["openOnReturn"])

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行实际生成脚本的离线 DOM 检查")
    def test_ledger_observation_coverage_keeps_requested_range_gaps_and_global_basis(self):
        report, packet = ledger_coverage_fixture()
        original = deepcopy((report, packet))
        projection = ReviewProjection(report, packet)
        chart, review = projection.select("case", "finding-acme-2024")
        coverage = review["scope"]["coverage"]
        self.assertEqual(coverage["requested_window"], packet["scope"]["coverage"]["requested_window"])
        self.assertEqual(coverage["actual_start"], "2024-09-01T15:10:00Z")
        self.assertEqual(coverage["actual_end"], "2026-09-02T15:10:00Z")
        self.assertEqual(coverage["gaps"], [{"code": "SOURCE_WINDOW_CLIPPED", "message": "来源未返回所请求区间的全部记录", "asset_type": "OPTION"}])
        self.assertEqual(review["report_basis"]["record_count"], 7)
        self.assertEqual(review["report_basis"]["record_start"], "2024-09-01T15:10:00Z")
        self.assertEqual(review["report_basis"]["record_end"], "2026-09-01T15:10:00Z")
        observed = execute(render_review_payload(chart, review), 'const outcome={summary:$("jr-summary").textContent,metadata:$("jr-metadata").textContent};')
        text = observed["summary"] + observed["metadata"]
        for expected in ("2024-08-01T00:00:00+08:00", "2026-09-30T23:59:59+08:00", "2024-09-01T15:10:00Z", "7 笔分析记录", "来源未返回所请求区间的全部记录", "期权", "来源覆盖观察"):
            self.assertIn(expected, text)
        for hidden in ("SOURCE_WINDOW_CLIPPED", "COMPUTER_USE_EXPORT", "source-coverage-hidden", "PRIVATE_COVERAGE_REF", "PRIVATE_GAP_REF", "/Users/", "requested_window", "{", "}"):
            self.assertNotIn(hidden, text)
        encoded = canonical_json({"chart": chart, "review": review})
        for private in ("PRIVATE_COVERAGE_REF", "PRIVATE_GAP_REF", "source_path", "/Users/"):
            self.assertNotIn(private, encoded)
        self.assertEqual((report, packet), original)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行实际生成脚本的离线 DOM 检查")
    def test_all_reading_surfaces_use_business_labels_without_mutating_research(self):
        report, packet = lesson_fixture()
        raw = "episode:activity:acme-2024"
        report["findings"][0]["process_observation"] = (
            f"片段 {raw}；金融原值 8 USD、行权价 100；输入 {report['input_hash']}；"
            "资料 /Users/example/product/.private/trading-journal/source.csv；"
            "公开 https://example.org/public?record=record-public"
        )
        original = deepcopy((report, packet))
        observed = execute(render_review(report, packet), r'''
const descend=element=>[element,...element.children.flatMap(descend)];
const outcome={texts:[],links:[],recordButtons:[],events:[],retainedRecords:DATA.records.length};
outcome.texts.push($("jr-summary").textContent,$("jr-metadata").textContent,$("jr-case").textContent,$("jr-plan").textContent);
for(const entry of jrFindings){jrSelectFinding(entry.finding_id);outcome.texts.push($("jr-findings").textContent,$("jr-plans").textContent);for(const node of descend($("jr-findings"))){if(node.tagName==="a")outcome.links.push(node.href);if(node.dataset.record)outcome.recordButtons.push({id:node.dataset.record,text:node.textContent})}for(const event of jrEventsFor(entry.finding_id)){jrShowEvent(event);outcome.events.push({id:event.evidence_id,text:$("jr-event-detail").textContent});outcome.texts.push($("jr-event-detail").textContent)}}
outcome.rawObservation=REVIEW.findings[0].process_observation;outcome.identities=jrFindings.map(row=>row.finding_id);outcome.sourceFinancialValue=REVIEW.findings[0].financial_claims[0].value;
''')
        visible = "\n".join(observed["texts"])
        for forbidden in (report["input_hash"], report["packet_hash"], report["report_id"], packet["snapshot_id"], raw,
                          "finding-acme-2024", "practice-stock", "chart:synthetic-review", "US:USD:ACME", "AVAILABLE_AT", "UNPLACED", "PROPOSED", "SNAPSHOT_WINDOW",
                          "/Users/example", "\"status\"", "\"source_id\"", "formula_version"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, visible)
        for expected in ("金融原值 8 USD", "行权价 100", "https://example.org/public?record=record-public", "当时可知", "事后资料", "时点不确定", "报告依据", "当前图窗"):
            self.assertIn(expected, visible)
        self.assertEqual(observed["rawObservation"], report["findings"][0]["process_observation"])
        self.assertEqual(observed["identities"], [row["finding_id"] for row in report["findings"]])
        self.assertTrue(observed["recordButtons"])
        for button in observed["recordButtons"]:
            self.assertNotIn(button["id"], button["text"])
        self.assertEqual(observed["retainedRecords"], len(packet["snapshot"]["records"]))
        self.assertIsNone(observed["sourceFinancialValue"])
        self.assertEqual((report, packet), original)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行实际生成脚本的离线 DOM 检查")
    def test_cross_year_lesson_and_viewport_operations_preserve_report_basis(self):
        report, packet = lesson_fixture()
        lesson = next(row for row in report["case_lessons"] if row["finding_ref"] == "finding-acme-2024")
        lesson["chart_window"].update(start="2024-09-01", end="2026-09-01")
        original = deepcopy((report, packet))
        observed = execute(render_review(report, packet), r'''
jrSelectFinding("finding-acme-2024");
const outcome={start:$("start").value,end:$("end").value,year:$("segment").value,rows:segmentRows.map(row=>row.record_id),basis:$("jr-summary").textContent,metadata:$("jr-metadata").textContent,sourceBasis:JSON.stringify(REVIEW.report_basis)};
$("zoom-in").listeners.click();$("pan-right").listeners.click();outcome.afterZoom=$("jr-summary").textContent;outcome.afterMetadata=$("jr-metadata").textContent;outcome.afterBasis=JSON.stringify(REVIEW.report_basis);outcome.cases=$("jr-findings").children.map(row=>row.dataset.finding);outcome.range=segmentRows.map(row=>row.record_id);
jrFocusRecord("beta-2025");outcome.counterStart=$("start").value;outcome.counterEnd=$("end").value;outcome.counterYear=$("segment").value;outcome.focused=$("detail").dataset.record;
''')
        self.assertEqual((observed["start"], observed["end"], observed["year"]), ("2024-09-01", "2026-09-01", ""))
        self.assertIn("acme-2024", observed["rows"])
        self.assertIn("acme-2026", observed["rows"])
        self.assertEqual(observed["range"], observed["rows"])
        self.assertEqual(observed["afterZoom"], observed["basis"])
        self.assertEqual(observed["afterMetadata"], observed["metadata"])
        self.assertEqual(observed["afterBasis"], observed["sourceBasis"])
        self.assertEqual(observed["cases"], ["finding-acme-2024"])
        self.assertEqual((observed["counterStart"], observed["counterEnd"], observed["counterYear"]), ("2025-09-01", "2026-09-01", ""))
        self.assertEqual(observed["focused"], "beta-2025")
        self.assertEqual((report, packet), original)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行实际生成脚本的离线 DOM 检查")
    def test_same_day_event_group_selects_all_frozen_members_and_returns_to_list(self):
        report, packet = same_day_event_fixture()
        original = deepcopy((report, packet))
        observed = execute(render_review(report, packet), r'''
const descend=element=>[element,...element.children.flatMap(descend)];jrSelectFinding("finding-acme-2026");const group=lessonEventGroups(chartLessonEvents,DATA.groups.find(row=>row.id===$("symbol").value),$("start").value,$("end").value).find(row=>row.events.length===3);
const outcome={count:String(group.events.length),label:group.events.length+"项事件",icons:$("chart").children.filter(row=>row.attributes["data-event-count"]).length,unplaced:chartLessonEvents.filter(event=>event.anchor_role==="UNPLACED").map(event=>event.evidence_id),details:[]};jrShowEventGroup(group.events,group.date);
const choices=()=>descend($("jr-event-detail")).filter(row=>row.tagName==="button"&&row.dataset.event);
outcome.members=choices().map(row=>({id:row.dataset.event,role:row.dataset.anchorRole}));
for(const member of outcome.members){choices().find(row=>row.dataset.event===member.id&&row.dataset.anchorRole===member.role).listeners.click();outcome.details.push({member,text:$("jr-event-detail").textContent,visible:!$("jr-event-detail").hidden});descend($("jr-event-detail")).find(row=>row.tagName==="button"&&row.textContent==="返回该日事件列表").listeners.click()}
outcome.returned=choices().map(row=>({id:row.dataset.event,role:row.dataset.anchorRole}));outcome.eventsUnchanged=JSON.stringify(chartLessonEvents);
''')
        self.assertEqual(observed["count"], "3")
        self.assertEqual(observed["icons"], 0)
        self.assertIn("3", observed["label"])
        self.assertEqual(observed["members"], [{"id": "later", "role": "AVAILABLE_AT"}, {"id": "later-second", "role": "AVAILABLE_AT"}, {"id": "later-second", "role": "EVENT_AT"}])
        self.assertEqual(observed["returned"], observed["members"])
        self.assertEqual(observed["unplaced"], ["uncertain"])
        for detail in observed["details"]:
            self.assertTrue(detail["visible"])
            self.assertNotIn(detail["member"]["id"], detail["text"])
            self.assertNotIn(detail["member"]["role"], detail["text"])
            self.assertIn("事后资料", detail["text"])
            self.assertIn("可信时间锚", detail["text"])
            self.assertIn("冻结公开来源", detail["text"])
        self.assertEqual((report, packet), original)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行实际生成脚本的离线 DOM 检查")
    def test_case_details_survive_record_date_and_page_interactions_and_restore_per_case(self):
        report, packet = lesson_fixture(bulk=True)
        original = deepcopy((report, packet))
        observed = execute(render_review(report, packet), r'''
const descend=element=>[element,...element.children.flatMap(descend)];
const layer=label=>descend($("jr-findings")).find(row=>row.tagName==="details"&&row.children[0].textContent.startsWith(label));
const source=(label,id)=>descend(layer(label)).find(row=>row.tagName==="details"&&row.dataset.evidence===id);
const setOpen=(element,open)=>{element.open=open;if(element.listeners.toggle)element.listeners.toggle()};
const state=()=>({cases:$("jr-findings").children.map(row=>row.dataset.finding),beginner:!!layer("初学").open,practice:!!layer("练习").open,advanced:!!layer("深入").open,practiceReferences:!!descend(layer("练习")).find(row=>row.tagName==="details"&&row.children[0].textContent==="本层完整成交引用").open,beginnerPrior:!!source("初学","prior").open,advancedPrior:!!source("深入","prior").open,page:$("page-number").value,date:selectedDate,rows:$("rows").children.length,represented:$("chart").children.reduce((total,row)=>total+Number(row.attributes["data-record-count"]||0),0)});
const select=id=>{$("jr-case").value=id;$("jr-case").listeners.change()};
select("finding-beta-bulk-0");const outcome={initial:state()};
setOpen(layer("练习"),true);setOpen(layer("深入"),true);setOpen(source("深入","prior"),true);
setOpen(descend(layer("练习")).find(row=>row.tagName==="details"&&row.children[0].textContent==="本层完整成交引用"),true);
descend(layer("练习")).find(row=>row.tagName==="button"&&row.dataset.record==="beta-bulk-0").listeners.click();outcome.afterReference=state();outcome.focusedRecord=$("detail").dataset.record;
$("chart").children.find(row=>row.attributes["data-date"]==="2026-09-02"&&row.attributes["data-record-count"]).listeners.click();outcome.afterDate=state();
$("next-page").listeners.click();outcome.afterPage=state();
select("finding-acme-2026");outcome.otherCase=state();
select("finding-beta-bulk-0");outcome.restored=state();
setOpen(layer("练习"),false);setOpen(layer("深入"),false);setOpen(source("深入","prior"),false);$("events").listeners.change();outcome.closedAfterRedraw=state();
select("finding-acme-2026");select("finding-beta-bulk-0");outcome.closedAfterReturn=state();
''')
        defaults = {"beginner": True, "practice": False, "advanced": False,
                    "practiceReferences": False, "beginnerPrior": False, "advancedPrior": False}
        for key, expected in defaults.items():
            self.assertEqual(observed["initial"][key], expected, key)
            self.assertEqual(observed["otherCase"][key], expected, key)
        self.assertEqual(observed["otherCase"]["cases"], ["finding-acme-2026"])
        for action in ("afterReference", "afterDate", "afterPage", "restored"):
            with self.subTest(action=action):
                current = observed[action]
                self.assertEqual(current["cases"], ["finding-beta-bulk-0"])
                self.assertTrue(current["beginner"])
                self.assertTrue(current["practice"])
                self.assertTrue(current["advanced"])
                self.assertTrue(current["practiceReferences"])
                self.assertTrue(current["advancedPrior"])
                self.assertFalse(current["beginnerPrior"])
        self.assertEqual(observed["focusedRecord"], "beta-bulk-0")
        self.assertEqual(observed["afterDate"]["date"], "2026-09-02")
        self.assertEqual(observed["afterDate"]["rows"], 200)
        self.assertEqual(observed["afterPage"]["page"], "2")
        self.assertEqual(observed["afterPage"]["rows"], 20)
        self.assertEqual(observed["afterPage"]["represented"], 222)
        for action in ("closedAfterRedraw", "closedAfterReturn"):
            with self.subTest(action=action):
                self.assertFalse(observed[action]["practice"])
                self.assertFalse(observed[action]["advanced"])
                self.assertFalse(observed[action]["advancedPrior"])
                self.assertTrue(observed[action]["practiceReferences"])
        self.assertEqual((report, packet), original)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行实际生成脚本的离线 DOM 检查")
    def test_manually_collapsed_beginner_and_nested_source_remain_per_case(self):
        report, packet = lesson_fixture()
        original = deepcopy((report, packet))
        observed = execute(render_review(report, packet), r'''
const descend=element=>[element,...element.children.flatMap(descend)];
const beginner=()=>descend($("jr-findings")).find(row=>row.tagName==="details"&&row.children[0].textContent.startsWith("初学"));
const prior=()=>descend(beginner()).find(row=>row.tagName==="details"&&row.dataset.evidence==="prior");
const setOpen=(element,open)=>{element.open=open;if(element.listeners.toggle)element.listeners.toggle()};
const state=()=>({cases:$("jr-findings").children.map(row=>row.dataset.finding),beginner:!!beginner().open,prior:!!prior().open});
jrSelectFinding("finding-acme-2026");const outcome={initial:state()};
setOpen(prior(),true);setOpen(beginner(),false);render();outcome.afterRedraw=state();
$("chart").children.find(row=>row.attributes["data-date"]==="2026-09-01"&&row.attributes["data-record-count"]).listeners.click();outcome.afterDate=state();
jrSelectFinding("finding-beta-2026");outcome.otherCase=state();
jrSelectFinding("finding-acme-2026");outcome.returned=state();
setOpen(beginner(),true);outcome.reopened=state();setOpen(prior(),false);render();outcome.sourceClosed=state();
jrSelectFinding("finding-beta-2026");jrSelectFinding("finding-acme-2026");outcome.sourceClosedAfterReturn=state();
''')
        self.assertEqual(observed["initial"], {"cases": ["finding-acme-2026"], "beginner": True, "prior": False})
        self.assertEqual(observed["otherCase"], {"cases": ["finding-beta-2026"], "beginner": True, "prior": False})
        for action in ("afterRedraw", "afterDate", "returned"):
            with self.subTest(action=action):
                self.assertEqual(observed[action], {"cases": ["finding-acme-2026"], "beginner": False, "prior": True})
        self.assertEqual(observed["reopened"], {"cases": ["finding-acme-2026"], "beginner": True, "prior": True})
        for action in ("sourceClosed", "sourceClosedAfterReturn"):
            with self.subTest(action=action):
                self.assertEqual(observed[action], {"cases": ["finding-acme-2026"], "beginner": True, "prior": False})
        self.assertEqual((report, packet), original)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行实际生成脚本的离线 DOM 检查")
    def test_beginner_view_keeps_prose_and_terms_with_collapsed_complete_sources(self):
        report, packet = lesson_fixture()
        original = deepcopy((report, packet))
        observed = execute(render_review(report, packet), r'''jrSelectFinding("finding-acme-2026");
const descend=element=>[element,...element.children.flatMap(descend)],beginner=descend($("jr-findings")).find(row=>row.tagName==="details"&&row.children[0].textContent.startsWith("初学")),metadata=descend(beginner).filter(row=>row.dataset.evidence),visible=element=>element.tagName==="details"&&!element.open?element.children[0].textContent:(element._text||"")+element.children.map(visible).join("");const outcome={visible:visible(beginner),full:beginner.textContent,metadata:metadata.map(row=>({id:row.dataset.evidence,open:!!row.open})),candles:$("chart").children.filter(row=>row.attributes["data-candle-date"]).map(row=>row.attributes["data-candle-date"]),events:$("chart").children.filter(row=>row.attributes["data-lesson-event"]).map(row=>row.attributes["data-event-date"])};metadata[0].open=true;outcome.expanded=visible(beginner);''')
        for value in ("合成初学读图说明", "连接本案成交与标的路径", "冻结日线", "只读已取得日线", "当时可知合成资料", "事后合成资料"):
            self.assertIn(value, observed["visible"])
        for label in ("取得时刻", "事实截止", "发布时间精度"):
            self.assertNotIn(label, observed["visible"])
            self.assertIn(label, observed["full"])
        self.assertEqual(observed["metadata"], [{"id": "prior", "open": False}, {"id": "later", "open": False}, {"id": "uncertain", "open": False}])
        self.assertIn("取得时刻", observed["expanded"])
        self.assertEqual(observed["candles"], ["2026-09-01"])
        self.assertEqual(observed["events"], [])
        self.assertEqual((report, packet), original)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行实际生成脚本的离线 DOM 检查")
    def test_cross_market_event_uses_each_referenced_security_timezone(self):
        template, _ = lesson_fixture()
        rows = [record("us-focus", occurred_at="2026-01-05T15:10:00Z", fees_complete=False),
                record("hk-counter", occurred_at="2026-01-06T02:10:00Z", fees_complete=False,
                       instrument=instrument("STOCK", "0761", key="HK:HKD:0761", market="HK",
                                             currency="HKD", exchange_timezone="Asia/Hong_Kong"))]
        quotes = [market(candles=[candle("2026-01-05")]),
                  market(symbol="0761", instrument_key="HK:HKD:0761", market="HK", currency="HKD",
                         exchange_timezone="Asia/Hong_Kong", candles=[candle("2026-01-06")])]
        snapshot = chart_snapshot(rows, quotes)
        snapshot.update(snapshot_id="synthetic-cross-market", as_of=CUTOFF, retrieved_at=CUTOFF,
                        analysis=analyze_records(rows), context_records=[], opening_positions={})
        snapshot["input_hash"] = canonical_hash({key: snapshot[key] for key in ("records", "context_records", "opening_positions", "coverage", "analysis", "market")})
        materials = [evidence("cross-day", "2026-01-05T22:00:00Z", record_refs=["us-focus", "hk-counter"], title="合成跨日事件"),
                     evidence("unplaced", "2026-01-05", publication_precision="DATE", record_refs=["us-focus", "hk-counter"], title="合成未定位资料")]
        packet = prepare_reflection(snapshot, cutoff=CUTOFF, evidence=materials, chart_refs=["chart:cross-market"])
        finding = deepcopy(template["findings"][0])
        finding.update(finding_id="cross-market", record_refs=["us-focus"], episode_refs=["activity:us-focus"],
                       chart_refs=["chart:cross-market"], calculation_refs=[], diary_refs=[], financial_claims=[],
                       decision_evidence_refs=[], outcome_evidence_refs=["cross-day"], uncertain_evidence_refs=["unplaced"],
                       alternative_explanations=[{"text": "合成香港反例", "record_refs": ["hk-counter"],
                                                 "episode_refs": ["activity:hk-counter"], "evidence_refs": ["cross-day", "unplaced"]}])
        lesson = deepcopy(template["case_lessons"][0])
        lesson.update(finding_ref="cross-market", focus_record_ref="us-focus",
                      chart_window={"start": "2026-01-05", "end": "2026-01-06", "record_refs": ["us-focus"], "focus_instrument_key": rows[0]["instrument"]["key"]},
                      event_links=[{"evidence_ref": "cross-day", "record_refs": ["us-focus", "hk-counter"], "anchor_role": "AVAILABLE_AT", "relevance_note": "同一来源时刻在不同市场跨日"},
                                   {"evidence_ref": "unplaced", "record_refs": ["us-focus", "hk-counter"], "anchor_role": "UNPLACED", "relevance_note": "保持未定位"}])
        for name in ("beginner", "practice", "advanced"):
            lesson[name].update(record_refs=["us-focus"], evidence_refs=["cross-day", "unplaced"])
        plan = deepcopy(template["improvement_plan"][0])
        plan.update(finding_refs=["cross-market"], record_refs=["us-focus"], evidence_refs=["cross-day"])
        report = assemble_report(packet, findings=[finding], improvement_plan=[plan], case_lessons=[lesson],
                                 model_version="synthetic-no-model-call", skill_version="1.1.0", phase_coverage=template["phase_coverage"],
                                 report_as_of=template["report_as_of"], analyzed_episode_ids=["activity:us-focus", "activity:hk-counter"])
        page = render_review(report, packet)
        events = data_projection(page)["lesson_events"]
        self.assertEqual(events[0]["dates_by_record"], {"us-focus": "2026-01-05", "hk-counter": "2026-01-06"})
        self.assertEqual(events[1]["dates_by_record"], {"us-focus": None, "hk-counter": None})
        self.assertEqual(events[0]["anchor_at"], "2026-01-05T22:00:00Z")
        observed = execute(page, r'''const marks=()=>lessonEventGroups(chartLessonEvents,DATA.groups.find(group=>group.id===$("symbol").value),$("start").value,$("end").value).flatMap(group=>group.events.map(event=>({id:event.evidence_id,day:group.date})));const outcome={};
jrSelectFinding("cross-market");outcome.us=marks();jrFocusRecord("hk-counter");outcome.hk=marks();outcome.hkTitle=$("title").textContent;
const event=chartLessonEvents.find(row=>row.evidence_id==="cross-day");outcome.originalAnchor=event.anchor_at;outcome.originalLayers=event.layers;event.dates_by_record["hk-counter"]=null;render();outcome.nullMapping=marks();
delete event.dates_by_record;$("start").value="2026-01-05";$("end").value="2026-01-06";jrResetViewport();render();outcome.legacy=marks();''')
        self.assertEqual(observed["us"], [{"id": "cross-day", "day": "2026-01-05"}])
        self.assertEqual(observed["hk"], [{"id": "cross-day", "day": "2026-01-06"}])
        self.assertIn("HKD", observed["hkTitle"])
        self.assertEqual(observed["nullMapping"], [])
        self.assertEqual(observed["legacy"], [{"id": "cross-day", "day": "2026-01-05"}])
        self.assertEqual(observed["originalAnchor"], "2026-01-05T22:00:00Z")
        self.assertEqual(observed["originalLayers"], events[0]["layers"])

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行实际生成脚本的离线 DOM 检查")
    def test_lesson_selection_focus_window_three_layers_and_derived_events(self):
        report, packet = lesson_fixture()
        original = deepcopy((report, packet))
        page = render_review(report, packet)
        projected = data_projection(page)
        self.assertEqual(projected["case_lessons"], report["case_lessons"])
        self.assertEqual(len(projected["lesson_events"]), 14)
        observed = execute(page, r'''const outcome={initial:$("jr-findings").children.length};
$("jr-case").value="finding-acme-2026";$("jr-case").listeners.change();
outcome.selected=$("jr-findings").children.map(row=>row.dataset.finding);outcome.text=$("jr-findings").textContent;outcome.focus=chartFocusIds.has("acme-2026");outcome.start=$("start").value;outcome.end=$("end").value;outcome.windowMarks=$("chart").children.filter(row=>row.attributes["data-focus-window"]==="true").length;outcome.focusMarks=$("chart").children.filter(row=>row.attributes["data-focus"]==="true").length;outcome.events=$("chart").children.filter(row=>row.attributes["data-lesson-event"]).map(row=>row.attributes["data-lesson-event"]);outcome.tableOpen=!!$("trade-table").open;
const descend=element=>[element,...element.children.flatMap(descend)];descend($("jr-findings")).find(row=>row.tagName==="button"&&row.dataset.event==="later").listeners.click();outcome.eventDetail=$("jr-event-detail").textContent;outcome.eventVisible=!$("jr-event-detail").hidden;
jrSelectFinding("finding-acme-2024");jrFocusRecord("beta-2025");outcome.counterSymbol=$("title").textContent;outcome.counterRows=$("rows").children.map(row=>row.dataset.record);outcome.counterCase=$("jr-findings").children.map(row=>row.dataset.finding);
jrSelectFinding("finding-call-2026");outcome.optionText=$("detail").textContent;outcome.optionPrice=DATA.records.find(row=>row.record_id==="call-2026").marker_price;''')
        self.assertEqual(observed["initial"], 0)
        self.assertEqual(observed["selected"], ["finding-acme-2026"])
        for text in ("初学", "候选错误", "推翻条件", "合成初学读图说明", "不确定"):
            self.assertIn(text, observed["text"])
        self.assertTrue(observed["focus"])
        self.assertEqual((observed["start"], observed["end"]), ("2026-09-01", "2026-10-02"))
        self.assertEqual(observed["windowMarks"], 1)
        self.assertGreater(observed["focusMarks"], 0)
        self.assertEqual(observed["events"], [])
        self.assertFalse(observed["tableOpen"])
        self.assertTrue(observed["eventVisible"])
        self.assertIn("事后资料", observed["eventDetail"])
        self.assertIn("公开可得不等于已经阅读", observed["eventDetail"])
        self.assertIn("BETA", observed["counterSymbol"])
        self.assertEqual(observed["counterRows"], ["beta-2025"])
        self.assertEqual(observed["counterCase"], ["finding-acme-2024"])
        self.assertIn("权利金 2 USD", observed["optionText"])
        self.assertIsNone(observed["optionPrice"])
        self.assertEqual((report, packet), original)

    def test_projected_renderer_embeds_only_supplied_selection(self):
        report, packet = fixture()
        page = render_review(report, packet)
        chart = data_projection(page, "journal-data")
        selected = data_projection(page)
        selected["findings"] = selected["findings"][:1]
        selected["improvement_plan"] = selected["improvement_plan"][:1]
        selected["initial_finding_id"] = selected["findings"][0]["finding_id"]
        chart["records"] = [row for row in chart["records"] if row["record_id"] == "acme-2024"]
        chart["groups"] = chart["groups"][:1]
        rendered = render_review_payload(chart, selected)
        self.assertEqual(data_projection(rendered, "journal-data")["records"], chart["records"])
        self.assertNotIn("合成观察 beta-2026", rendered)
        self.assertNotIn("beta-bulk", rendered)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行实际生成脚本的离线 DOM 检查")
    def test_projected_directory_navigates_only_known_case_and_preserves_global_counts(self):
        report, packet = fixture()
        page = render_review(report, packet)
        chart, projected = data_projection(page, "journal-data"), data_projection(page)
        projected.update(findings=[], case_lessons=[], improvement_plan=[], viewer_selection=True,
                         directory=[{"finding_id": "finding-beta-2026", "pattern": "合成目录", "record_refs": []}],
                         progress={"status": "COMPLETE", "total_units": 135, "analyzed_count": 135, "pending_count": 0})
        observed = execute(render_review_payload(chart, projected), r'''const outcome={progress:$("jr-progress").textContent,summary:$("jr-summary").textContent};window.location={assign(target){outcome.target=target}};outcome.unknown=jrSelectFinding("unknown-case");outcome.before=outcome.target||null;outcome.known=jrSelectFinding("finding-beta-2026");''')
        self.assertEqual(observed["progress"], "已完成 · 已分析 135 / 待分析 0")
        self.assertIn("已分析 135，待分析 0", observed["summary"])
        self.assertFalse(observed["unknown"])
        self.assertIsNone(observed["before"])
        self.assertTrue(observed["known"])
        self.assertEqual(observed["target"], "/view?kind=case&id=finding-beta-2026")
    def test_complete_minimal_projection_and_original_financial_values(self):
        report, packet = fixture()
        original = deepcopy((report, packet))
        report["findings"][0]["raw"] = "SYNTHETIC_RAW_FINDING"
        page = render_review(report, packet)
        projected = data_projection(page)
        self.assertEqual(len(projected["findings"]), len(report["findings"]))
        self.assertEqual(projected["improvement_plan"], report["improvement_plan"])
        for field in ("scope", "progress", "phase_coverage", "case_selection", "report_id", "limitations"):
            self.assertIn(field, projected)
        self.assertEqual(projected["scope"]["coverage"]["status"], "PARTIAL")
        self.assertEqual(projected["findings"][0]["record_refs"], ["acme-2024"])
        self.assertEqual(projected["findings"][0]["alternative_explanations"][0]["record_refs"], ["beta-2025"])
        self.assertIsNone(projected["findings"][0]["financial_claims"][0]["value"])
        self.assertEqual([row["evidence_id"] for row in projected["evidence"]], ["prior", "later", "uncertain"])
        self.assertIsNone(projected["evidence"][-1]["source_url"])
        for forbidden in ("SYNTHETIC_PRIVATE_ACCOUNT_REF", "SYNTHETIC_COVERAGE_ACCOUNT_REF", "SYNTHETIC_RAW_DIARY", "SYNTHETIC_RAW_EVIDENCE", "SYNTHETIC_RAW_FINDING"):
            self.assertNotIn(forbidden, page)
        self.assertNotIn("snapshot", projected)
        self.assertNotIn("diary", projected)
        self.assertEqual(packet, original[1])
        report["findings"][0].pop("raw")
        self.assertEqual(report, original[0])
        financial_packet = basic_packet()
        financial_report = basic_report(financial_packet)
        financial_projection = data_projection(render_review(financial_report, financial_packet))
        self.assertEqual(financial_projection["findings"][0]["financial_claims"][0]["value"], "8")

    def test_json_and_text_injection_and_unsafe_public_links_are_inert(self):
        report, packet = fixture()
        attack = '</script><script>alert("x")</script><img src=x onerror=alert(1)> & \u2028\u2029'
        report["findings"][0]["pattern"] = attack
        report["findings"][0]["process_observation"] = {"text": attack, "account_ref": "SYNTHETIC_NESTED_PRIVATE"}
        page = render_review(report, packet)
        self.assertNotIn(attack, page)
        self.assertNotIn("SYNTHETIC_NESTED_PRIVATE", page)
        self.assertEqual(data_projection(page)["findings"][0]["pattern"], attack)
        self.assertEqual(page.count("<script"), 3)
        self.assertNotRegex(page, r"<(?:script|img|iframe)[^>]+src=")
        self.assertNotIn(".innerHTML", page)
        self.assertIn('a.rel="noopener noreferrer"', page)

    def test_invalid_report_or_packet_is_rejected_before_render(self):
        report, packet = fixture()
        packet["snapshot"]["records"][0]["price"] = "777"
        with self.assertRaisesRegex(ReflectionError, "packet_hash"):
            render_review(report, packet)
        report, packet = fixture()
        report["findings"][0]["decision_evidence_refs"] = ["later"]
        with self.assertRaisesRegex(ReflectionError, "当时背景"):
            render_review(report, packet)

    def test_only_https_links_without_credentials_enter_projection(self):
        for source_url, expected in (("https://example.org/public?a=1&b=2", "https://example.org/public?a=1&b=2"),
                                     ("http://example.org/public", None),
                                     ("javascript:alert(1)", None),
                                     ("https://user:password@example.org/public", None),
                                     ("https://user@example.org/public", None),
                                     ("https://example.org/\nprivate", None),
                                     ("https://", None)):
            with self.subTest(source_url=source_url):
                report, packet = fixture()
                packet["evidence"][0]["source_url"] = source_url
                packet["packet_hash"] = canonical_hash({key: value for key, value in packet.items() if key != "packet_hash"})
                report["packet_hash"] = packet["packet_hash"]
                self.assertEqual(data_projection(render_review(report, packet))["evidence"][0]["source_url"], expected)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行实际生成脚本的离线 DOM 检查")
    def test_partial_progress_is_visible_without_claiming_complete_history(self):
        report, packet = fixture()
        units = report["progress"]["analyzed_episode_ids"]
        report["progress"].update(analyzed_episode_ids=units[:1], pending_episode_ids=units[1:], status="PARTIAL")
        observed = execute(render_review(report, packet), 'const outcome={summary:$("jr-summary").textContent,progress:$("jr-progress").textContent};')
        self.assertIn("分析进度：已分析 1，待分析 6", observed["summary"])
        self.assertIn("分析完成不等于所选期间资料完整", observed["summary"])
        self.assertEqual(observed["progress"], "部分覆盖 · 已分析 1 / 待分析 6")

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行实际生成脚本的离线 DOM 检查")
    def test_native_select_directory_selection_restore_and_cross_year_focus(self):
        report, packet = fixture()
        original = deepcopy((report, packet))
        observed = execute(render_review(report, packet), r'''const view=()=>({year:$("segment").value,rows:$("rows").children.filter(row=>row.dataset.record).map(row=>row.dataset.record),findings:$("jr-findings").children.filter(row=>row.dataset.finding).map(row=>row.dataset.finding),plans:$("jr-plans").children.map(row=>row.dataset.improvement),directory:$("jr-case").children.slice(1).map(row=>row.value),detail:$("detail").dataset.record});
const outcome={initial:view(),chartHidden:$("chart-workspace").hidden};
$("jr-case").value="finding-acme-2024";$("jr-case").listeners.change();outcome.selected=view();outcome.oldText=$("jr-findings").textContent;
jrFocusRecord("beta-2025");outcome.counterexample=view();
$("jr-scope").value="CURRENT";$("jr-scope").listeners.change();outcome.related=view();
$("symbol").value=DATA.groups.find(group=>group.symbol==="BETA").id;$("symbol").listeners.change();$("segment").value="2026";$("segment").listeners.change();outcome.beta2026=view();
$("jr-all").listeners.click();outcome.restored=view();
$("jr-search").value="ACME261120P100";$("jr-search").listeners.input();outcome.search=view();
$("jr-case").value="finding-put-2026";$("jr-case").listeners.change();outcome.put=view();
$("jr-all").listeners.click();$("jr-plan").value="practice-option";$("jr-plan").listeners.change();outcome.plan=view();
$("jr-all").listeners.click();outcome.final=view();''')
        all_findings = [row["finding_id"] for row in report["findings"]]
        self.assertEqual(observed["initial"]["findings"], [])
        self.assertEqual(observed["initial"]["plans"], ["practice-stock", "practice-option"])
        self.assertEqual(observed["initial"]["directory"], all_findings)
        self.assertTrue(observed["chartHidden"])
        self.assertEqual(observed["selected"]["findings"], ["finding-acme-2024"])
        self.assertEqual(observed["selected"]["plans"], ["practice-stock", "practice-option"])
        self.assertEqual(observed["selected"]["detail"], "acme-2024")
        self.assertIn("旧版报告未保存三层图表讲解", observed["oldText"])
        self.assertEqual(observed["counterexample"]["year"], "")
        self.assertEqual(observed["counterexample"]["rows"], ["beta-2025"])
        self.assertEqual(observed["counterexample"]["findings"], ["finding-acme-2024"])
        self.assertEqual(observed["related"]["directory"], ["finding-acme-2024", "finding-beta-2025", "finding-beta-2026"])
        self.assertEqual(observed["beta2026"]["directory"], ["finding-beta-2026"])
        self.assertEqual(observed["beta2026"]["findings"], [])
        self.assertEqual(observed["restored"]["directory"], all_findings)
        self.assertEqual(observed["restored"]["findings"], [])
        self.assertEqual(observed["search"]["directory"], ["finding-put-2026"])
        self.assertEqual(observed["put"]["findings"], ["finding-put-2026"])
        self.assertEqual(observed["put"]["detail"], "put-2026")
        self.assertEqual(observed["plan"]["findings"], [])
        self.assertEqual(observed["plan"]["plans"], ["practice-option"])
        self.assertEqual(observed["final"]["directory"], all_findings)
        self.assertEqual((report, packet), original)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行实际生成脚本的离线 DOM 检查")
    def test_focus_reaches_second_page_and_clears_contract_asset_and_dates(self):
        report, packet = fixture(bulk=True)
        observed = execute(render_review(report, packet), r'''
$("asset").value="OPTION";$("contract").value=DATA.records.find(row=>row.record_id==="put-2026").instrument.key;$("start").value="2024-01-01";$("end").value="2024-12-31";render();
const success=jrFocusRecord("beta-bulk-219");const outcome={success,year:$("segment").value,page:$("page-number").value,detail:$("detail").dataset.record,rows:$("rows").children.map(row=>row.dataset.record),asset:$("asset").value,contract:$("contract").value,start:$("start").value,end:$("end").value,retained:DATA.records.length};
''')
        self.assertTrue(observed["success"])
        self.assertEqual(observed["year"], "")
        self.assertEqual(observed["page"], "2")
        self.assertEqual(observed["detail"], "beta-bulk-219")
        self.assertIn("beta-bulk-219", observed["rows"])
        self.assertEqual((observed["asset"], observed["contract"], observed["start"], observed["end"]), ("ALL", "ALL", "2025-09-01", "2026-09-02"))
        self.assertEqual(observed["retained"], 227)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行实际生成脚本的离线 DOM 检查")
    def test_safe_links_and_original_evidence_layers_execute(self):
        report, packet = fixture()
        observed = execute(render_review(report, packet), r'''
jrSelectFinding("finding-acme-2024");const descend=element=>[element,...element.children.flatMap(descend)],all=descend($("jr-findings"));const outcome={links:all.filter(row=>row.tagName==="a").map(row=>({href:row.href,target:row.target,rel:row.rel})),text:$("jr-findings").textContent,calculation:REVIEW.findings[0].financial_claims[0].value};
''')
        self.assertTrue(observed["links"])
        self.assertTrue(all(row["href"].startswith("https://") and row["target"] == "_blank" and row["rel"] == "noopener noreferrer" for row in observed["links"]))
        for text in ("原报告当时层", "原报告事后层", "不作当时依据", "金融原值", "净盈亏", "取得时刻", "当时记录"):
            self.assertIn(text, observed["text"])
        self.assertIsNone(observed["calculation"])


class ReviewSavingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="journal-review-saving-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.root.chmod(0o700)
        self.report, self.packet = fixture()
        self.paths = save_report(self.root, self.report, self.packet)
        self.directory = self.root / "artifacts" / "reflections" / REPORT_ID
        self.loaded = []

    def load_snapshot(self, identifier):
        self.loaded.append(identifier)
        return deepcopy(self.packet["snapshot"])

    def save(self, identifier=REPORT_ID, callback=None):
        return save_review(self.root, identifier, load_snapshot=callback or self.load_snapshot)

    def test_readonly_loader_validates_same_binding_without_creating_artifacts(self):
        before = {path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.directory.iterdir()}
        loaded = load_review(self.root, REPORT_ID, load_snapshot=self.load_snapshot)
        self.assertEqual(loaded, (self.report, self.packet))
        self.assertEqual({path.name: (path.read_bytes(), path.stat().st_mtime_ns) for path in self.directory.iterdir()}, before)
        self.assertEqual(self.loaded, [self.packet["snapshot_id"]])
        path = self.directory / "report.json"
        original = path.read_bytes()
        path.chmod(0o644)
        with self.assertRaisesRegex(ReflectionError, "0600"):
            load_review(self.root, REPORT_ID, load_snapshot=self.load_snapshot)
        path.chmod(0o600)
        path.write_text('{"report_id":"first","report_id":"second"}')
        with self.assertRaisesRegex(ReflectionError, "重复字段"):
            load_review(self.root, REPORT_ID, load_snapshot=self.load_snapshot)
        path.write_bytes(original)
        with self.assertRaisesRegex(ReflectionError, "本地账本"):
            load_review(self.root, REPORT_ID, load_snapshot=lambda _: {})
        self.assertEqual(list(self.directory.glob("review-*.html")), [])

    def test_content_hash_reuse_preserves_inputs_and_old_pages(self):
        original = {path: (Path(path).read_bytes(), Path(path).stat().st_mtime_ns) for path in (self.paths["json_path"], self.paths["packet_path"], self.paths["markdown_path"])}
        old = self.directory / "review.html"
        old.write_text("old page", encoding="utf-8")
        old.chmod(0o600)
        first = self.save()
        path = Path(first["review_path"])
        initial = (path.read_bytes(), path.stat().st_mtime_ns)
        second = self.save()
        self.assertFalse(first["reused"])
        self.assertTrue(second["reused"])
        self.assertEqual(second["content_hash"], hashlib.sha256(initial[0]).hexdigest())
        self.assertEqual(path.name, f"review-{second['content_hash']}.html")
        self.assertEqual(second["review_path"], first["review_path"])
        self.assertEqual((path.read_bytes(), path.stat().st_mtime_ns), initial)
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertEqual(old.read_text(), "old page")
        markdown = Path(first["markdown_path"])
        self.assertFalse(first["markdown_reused"])
        self.assertTrue(second["markdown_reused"])
        self.assertEqual(first["markdown_path"], second["markdown_path"])
        self.assertEqual(markdown.name, f"reading-{hashlib.sha256(markdown.read_bytes()).hexdigest()}.md")
        self.assertEqual(first["markdown_content_hash"], hashlib.sha256(markdown.read_bytes()).hexdigest())
        self.assertEqual(stat.S_IMODE(markdown.stat().st_mode), 0o600)
        self.assertNotIn(self.report["report_id"], markdown.read_text())
        for name, expected in original.items():
            self.assertEqual((Path(name).read_bytes(), Path(name).stat().st_mtime_ns), expected)
        self.assertEqual(self.loaded, [self.packet["snapshot_id"]] * 2)

    def test_existing_readable_markdown_conflict_link_and_permissions_fail_closed(self):
        result = self.save()
        path = Path(result["markdown_path"])
        original = path.read_bytes()
        path.write_text("conflicting reading")
        with self.assertRaisesRegex(ReflectionError, "拒绝覆盖"):
            self.save()
        self.assertEqual(path.read_text(), "conflicting reading")
        path.write_bytes(original)
        path.chmod(0o400)
        with self.assertRaisesRegex(ReflectionError, "0600"):
            self.save()
        path.chmod(0o600)
        path.unlink()
        target = self.root / "reading-outside.md"
        target.write_text("outside reading preserved")
        target.chmod(0o600)
        path.symlink_to(target)
        with self.assertRaises(ReflectionError):
            self.save()
        self.assertTrue(path.is_symlink())
        self.assertEqual(target.read_text(), "outside reading preserved")

    def test_invalid_report_ids_cannot_read_paths(self):
        for identifier in ("../report", REPORT_ID + "/../other", "reflection-" + "A" * 32, "reflection-" + "a" * 31, "reflection-" + "a" * 33, "reflection-test", None):
            with self.subTest(identifier=identifier), self.assertRaisesRegex(ReflectionError, "报告版本"):
                self.save(identifier)
        self.assertEqual(self.loaded, [])

    def test_report_and_authoritative_snapshot_bindings_fail_closed(self):
        value = deepcopy(self.report)
        value["report_id"] = "reflection-" + "b" * 32
        Path(self.paths["json_path"]).write_text(canonical_json(value))
        with self.assertRaisesRegex(ReflectionError, "保存目录"):
            self.save()
        self.assertEqual(self.loaded, [])
        Path(self.paths["json_path"]).write_text(canonical_json(self.report))
        for change in ("snapshot_id", "records", "account_ref"):
            other = deepcopy(self.packet["snapshot"])
            other[change] = "changed" if change != "records" else []
            with self.subTest(change=change), self.assertRaisesRegex(ReflectionError, "本地账本"):
                self.save(callback=lambda _: other)
        self.assertEqual(list(self.directory.glob("review-*.html")), [])

    def test_missing_nonregular_linked_and_wrong_permissions_are_rejected(self):
        for filename in ("report.json", "input.json"):
            path = self.directory / filename
            original = path.read_bytes()
            for replacement in ("missing", "directory", "symlink", "fifo", "hardlink", "permissions"):
                with self.subTest(filename=filename, replacement=replacement):
                    path.unlink()
                    target = self.root / "synthetic-target.json"
                    target.write_bytes(original)
                    target.chmod(0o600)
                    if replacement == "directory":
                        path.mkdir(mode=0o700)
                    elif replacement == "symlink":
                        path.symlink_to(target)
                    elif replacement == "fifo":
                        os.mkfifo(path, 0o600)
                    elif replacement == "hardlink":
                        os.link(target, path)
                    elif replacement == "permissions":
                        path.write_bytes(original)
                        path.chmod(0o644)
                    with self.assertRaises(ReflectionError):
                        self.save()
                    if path.is_dir():
                        path.rmdir()
                    elif path.is_symlink() or path.exists():
                        path.unlink()
                    target.unlink()
                    path.write_bytes(original)
                    path.chmod(0o600)
        self.assertEqual(self.loaded, [])

    def test_each_directory_and_ancestor_symlink_is_rejected(self):
        for directory in (self.root, self.root / "artifacts", self.root / "artifacts" / "reflections", self.directory):
            with self.subTest(directory=directory.name):
                directory.chmod(0o755)
                with self.assertRaisesRegex(ReflectionError, "0700"):
                    self.save()
                directory.chmod(0o700)
        alias = self.root.parent / (self.root.name + "-alias")
        self.addCleanup(lambda: alias.unlink(missing_ok=True))
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ReflectionError, "符号链接"):
            save_review(alias, REPORT_ID, load_snapshot=self.load_snapshot)
        with self.assertRaisesRegex(ReflectionError, "符号链接"):
            save_review(alias / "artifacts" / "..", REPORT_ID, load_snapshot=self.load_snapshot)
        with self.assertRaisesRegex(ReflectionError, "绝对"):
            save_review(Path("relative"), REPORT_ID, load_snapshot=self.load_snapshot)

    def test_existing_page_conflict_link_nonregular_or_permissions_are_not_overwritten(self):
        result = self.save()
        path = Path(result["review_path"])
        original = path.read_bytes()
        path.write_text("conflicting bytes")
        with self.assertRaisesRegex(ReflectionError, "拒绝覆盖"):
            self.save()
        self.assertEqual(path.read_text(), "conflicting bytes")
        path.write_bytes(original)
        path.chmod(0o400)
        with self.assertRaisesRegex(ReflectionError, "0600"):
            self.save()
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o400)
        path.chmod(0o600)
        path.unlink()
        outside = self.root / "synthetic-outside.html"
        outside.write_text("outside preserved")
        outside.chmod(0o600)
        path.symlink_to(outside)
        with self.assertRaises(ReflectionError):
            self.save()
        self.assertTrue(path.is_symlink())
        self.assertEqual(outside.read_text(), "outside preserved")
        path.unlink()
        path.mkdir(mode=0o700)
        with self.assertRaises(ReflectionError):
            self.save()
        self.assertTrue(path.is_dir())


if __name__ == "__main__":
    unittest.main()
