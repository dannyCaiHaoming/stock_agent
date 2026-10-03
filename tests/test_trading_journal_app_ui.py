"""Real generated UI scripts against wholly fictional journal facts."""
from copy import deepcopy
import json
import re
import shutil
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from product.trading_journal.app_ui import render_landing, render_report, render_timeline
from product.trading_journal.cli import build_parser
from product.trading_journal.viewer import ReviewProjection
from tests.test_trading_journal_candle_hover import timeline
from tests.test_trading_journal_charts import _DOM_RUNNER, _execute_chart_script, record, snapshot
from tests.test_trading_journal_review import REPORT_ID, data_projection, execute, same_day_event_fixture


class AppUiProjectionTests(unittest.TestCase):
    def test_shell_escapes_untrusted_text_and_hides_technical_metadata(self):
        state = {"source_id": "fixture", "as_of": "2026-10-03", "retrieved_at": "2026-10-03", "timeline": {"record_count": 7}, "reports": [{"report_id": REPORT_ID, "label": "</script><img src=x>"}]}
        page = render_landing(state, "fictional-csrf")
        self.assertNotIn("</script><img", page)
        boot = json.loads(re.search(r'<script id="journal-boot" type="application/json">(.*?)</script>', page, re.S)[1])
        self.assertEqual(boot["state"], state)
        for label in ("刷新时间线", "更新 K 线", "导入新交易", "生成新复盘", "CSV 成交时区", "导出日期范围时区", "开始日期", "截止日期"):
            self.assertIn(label, page)
        self.assertIn("X-Journal-CSRF", page)
        self.assertNotIn("state.timeline.snapshot_id", page)
        self.assertNotIn("r.report_id;o.textContent=r.report_id", page)

    def test_summary_and_case_keep_original_frozen_binding_and_fixed_routes(self):
        report, packet = same_day_event_fixture()
        projection = ReviewProjection(report, packet)
        before = deepcopy(packet)
        summary = render_report(projection, "summary", "0", REPORT_ID)
        data, research = data_projection(summary, "journal-data"), data_projection(summary)
        self.assertEqual(data["records"], [])
        self.assertTrue(all(group["market"] is None for group in data["groups"]))
        self.assertEqual(research["findings"], [])
        self.assertEqual(len(research["original_summary"]["improvement_plan"]), len(report["improvement_plan"]))
        self.assertIn('fetch("/reports/'+REPORT_ID+'/summary?"', summary)
        self.assertNotIn('fetch("/summary?"', summary)
        self.assertNotIn('window.location.assign("/view?"', summary)
        case = render_report(projection, "case", report["findings"][0]["finding_id"], REPORT_ID)
        self.assertEqual(data_projection(case, "journal-data")["input_hash"], packet["snapshot"]["input_hash"])
        self.assertEqual(packet, before)
        with self.assertRaises(ValueError):
            render_report(projection, "summary", "0", "../raw.csv")

    def test_persistent_cli_has_fixed_default_and_no_expiry(self):
        args = build_parser().parse_args(["--repo", "/fictional", "serve-journal"])
        self.assertEqual(args.port, 8765)
        self.assertFalse(hasattr(args, "lifetime_seconds"))


@unittest.skipUnless(shutil.which("node"), "需要 Node 检验实际生成脚本")
class AppUiInteractionTests(unittest.TestCase):
    def run_timeline(self, value, scenario):
        with patch("tests.test_trading_journal_charts.render_chart", render_timeline):
            return _execute_chart_script(value, scenario)

    def test_refresh_bridge_keeps_group_dates_viewport_pin_page_and_record(self):
        value, days = timeline()
        value["records"][:0] = [record(f"dense-{index}", quantity=str(index+1)) for index in range(45)]
        out = self.run_timeline(value, r'''
jrPinCandle('2026-09-01','dense-23');jrZoomViewport(.6,0);$('trade-table').open=true;
const before=window.journalExportState();$('symbol').value='';jrClearCandleSelection();jrResetViewport();render();const restored=window.journalRestoreState(before),after=window.journalExportState();const outcome={before,after,restored,date:$('candle-panel').dataset.date,visible:!$('candle-panel').hidden};
''')
        self.assertEqual(out["before"], out["after"])
        self.assertTrue(out["restored"]["restored"])
        self.assertEqual(out["date"], days[0])
        self.assertTrue(out["visible"])

    def test_invalid_old_group_does_not_silently_select_another_security(self):
        out = self.run_timeline(snapshot(), r'''
const result=window.journalRestoreState({group:'unknown',asset:'ALL'});const outcome={result,group:$('symbol').value};
''')
        self.assertFalse(out["result"]["restored"])
        self.assertIn("重新选择", out["result"]["message"])

    def test_new_selection_uses_report_summary_without_modifying_old_chart(self):
        report, packet = same_day_event_fixture()
        projection = ReviewProjection(report, packet)
        page = render_report(projection, "summary", "0", REPORT_ID)
        group = next(iter(projection.groups))
        selected = projection.summary(group_id=group)
        scenario = "const calls=[];globalThis.fetch=async(path)=>{calls.push(path);return {ok:true,json:async()=>({original_summary:"+json.dumps(selected)+"})}};const success=await window.journalApplySelection("+json.dumps({"group_id":group,"asset":"ALL","contract":"ALL"})+");const outcome={success,calls,count:$('jr-summary-count').dataset.total,records:DATA.records.length,plans:$('jr-plans').children.length};"
        out = execute(page, "const outcome=(async()=>{"+scenario.replace("const outcome=", "return ")+"})();", asynchronous=True)
        self.assertTrue(out["success"])
        self.assertTrue(out["calls"][0].startswith("/reports/"+REPORT_ID+"/summary?"))
        self.assertEqual(out["records"], 0)
        self.assertEqual(int(out["count"]), selected["pagination"]["total_count"])

    def test_trade_outside_original_report_shows_pending_not_stale_summary(self):
        report, packet = same_day_event_fixture()
        page = render_report(ReviewProjection(report, packet), "summary", "0", REPORT_ID)
        out = execute(page, r'''
const outcome=(async()=>{let requests=0;globalThis.fetch=async()=>{requests++;throw Error('must not fetch')};const result=await window.journalApplySelection({group_id:'new-security',date:'2026-10-03',asset:'ALL',contract:'ALL'});return {result,requests,count:$('jr-summary-count').dataset.total,notice:$('jr-notice').textContent,plans:$('jr-plans').children.length};})();
''', asynchronous=True)
        self.assertFalse(out["result"])
        self.assertEqual(out["requests"], 0)
        self.assertEqual(int(out["count"]), 0)
        self.assertEqual(out["plans"], 1)  # Only the existing 'no saved plans' notice.
        self.assertIn("尚未包含", out["notice"])

    def run_shell(self, scenario):
        state = {"source_id": "fixture", "as_of": "2026-10-03", "retrieved_at": "2026-10-03", "timeline": {"record_count": 8, "trade_through": "2026-09-01", "market_through": "2026-10-02"}, "reports": [{"report_id": REPORT_ID, "cutoff": "2026-10-02", "report_as_of": "2026-10-03", "case_count": 15, "pending_record_count": 0}], "selected_report_id": REPORT_ID, "warnings": []}
        page = render_landing(state, "fictional-csrf")
        original = 'ids["journal-data"].textContent=html.match(/<script id="journal-data" type="application\\/json">(.*?)<\\/script>/s)[1];'
        replacement = 'ids["journal-boot"].textContent=html.match(/<script id="journal-boot" type="application\\/json">(.*?)<\\/script>/s)[1];'
        runner = _DOM_RUNNER.replace(original, replacement)
        at = runner.index('eval(script+`')
        setup = r'''let restores=[];const saved={group:'fictional-group',viewport:{start:1,end:100},pin:'2026-09-01'};
for(const id of['timeline','report']){ids[id].style={};ids[id].contentDocument={querySelector(){return {getBoundingClientRect(){return {height:420}}}},body:{}};ids[id].contentWindow={journalExportState(){return saved},journalRestoreState(s){restores.push(s);return {restored:true,message:''}},journalSelection(){return {group_id:'fictional-group'}},async journalApplySelection(){return true}}}
const location={origin:'http://127.0.0.1:12345'};
'''
        runner = runner[:at] + setup + 'eval(script+' + json.dumps('\nconst outcome=(async()=>{'+scenario+'})();\nPromise.resolve(outcome).then(value=>console.log(JSON.stringify(value))).catch(e=>{console.error(e);process.exitCode=1});') + ');'
        with tempfile.TemporaryDirectory() as temp:
            html, js = Path(temp)/"shell.html", Path(temp)/"run.cjs"
            html.write_text(page);js.write_text(runner)
            result = subprocess.run([shutil.which("node"), str(js), str(html)], capture_output=True, text=True, timeout=20)
        if result.returncode:
            raise AssertionError(result.stderr)
        return json.loads(result.stdout)

    def test_shell_success_reload_preserves_selection_and_report_version(self):
        out = self.run_shell(r'''
const calls=[];globalThis.fetch=async(path,options)=>{calls.push({path,options});return {ok:true,json:async()=>({state:{...state,timeline:{...state.timeline,record_count:9}},message:'已刷新'})}};await update('/api/refresh',{});$('timeline').listeners.load();return {calls,restores,selectedReport,count:state.timeline.record_count,status:$('update-status').textContent,enabled:!$('refresh').disabled};
''')
        self.assertEqual(out["calls"][0]["options"]["headers"]["X-Journal-CSRF"], "fictional-csrf")
        self.assertEqual(out["calls"][0]["path"], "/api/refresh")
        self.assertEqual(out["restores"][0]["viewport"], {"start": 1, "end": 100})
        self.assertEqual(out["selectedReport"], REPORT_ID)
        self.assertEqual(out["count"], 9)
        self.assertTrue(out["enabled"])

    def test_shell_failed_update_keeps_current_views_and_never_grows_frame(self):
        out = self.run_shell(r'''
const before={timeline:$('timeline').src,report:$('report').src,reportId:selectedReport,count:state.timeline.record_count};globalThis.fetch=async()=>({ok:false,json:async()=>({message:'未完成，保留原页面'})});await update('/api/import',{});const heights=[];for(let i=0;i<20;i++){fit($('timeline'));heights.push($('timeline').style.height)}return {before,after:{timeline:$('timeline').src,report:$('report').src,reportId:selectedReport,count:state.timeline.record_count},heights,status:$('update-status').textContent};
''')
        self.assertEqual(out["before"], out["after"])
        self.assertEqual(set(out["heights"]), {"432px"})
        self.assertIn("保留", out["status"])


if __name__ == "__main__":
    unittest.main()
