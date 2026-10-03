import hashlib
from copy import deepcopy
import http.client
import json
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from urllib.parse import urlencode

from product.trading_journal.common import canonical_hash
from product.trading_journal.analysis import analyze_records
from product.trading_journal.reflection import prepare_reflection, save_report, ReflectionError
from product.trading_journal.viewer import ReviewProjection, _landing, start_review
from tests.test_trading_journal_review import execute, lesson_fixture
from tests.test_trading_journal_reflection import snapshot, record, report


def synthetic_report(root, *, cross_case_plan=False):
    snap = snapshot()
    other = record("unselected-msft", "2026-01-10T16:00:00Z", instrument={"key": "US:MSFT:USD", "symbol": "MSFT", "asset_type": "STOCK", "market": "US", "currency": "USD", "exchange_timezone": "America/New_York"})
    other["account_ref"] = "SYNTHETIC_PRIVATE_ACCOUNT_MUST_NOT_LEAVE"
    snap["records"].append(other)
    if cross_case_plan:
        snap["records"].append(record("unrelated-nvda", "2026-01-11T16:00:00Z", instrument={"key": "US:NVDA:USD", "symbol": "NVDA", "asset_type": "STOCK", "market": "US", "currency": "USD", "exchange_timezone": "America/New_York"}))
    snap["analysis"] = analyze_records(snap["records"], opening_positions=snap["opening_positions"])
    snap["input_hash"] = canonical_hash({key: snap[key] for key in ("records", "coverage", "analysis", "market", "context_records", "opening_positions")})
    p = prepare_reflection(snap, chart_refs=["chart:frozen-snapshot-test"])
    r = report(p)
    if cross_case_plan:
        second = deepcopy(r["findings"][0])
        second.update(finding_id="finding-msft", pattern="跨案例比较目录", record_refs=["unselected-msft"], episode_refs=["activity:unselected-msft"], calculation_refs=[], financial_claims=[], process_observation="UNSELECTED_FINDING_BODY_MUST_NOT_LEAVE", alternative_explanations=[{"text": "合成比较反例", "record_refs": ["buy-win"], "episode_refs": [], "evidence_refs": []}])
        r["findings"].append(second)
        r["improvement_plan"][0].update(finding_refs=["finding-1", "finding-msft"], record_refs=["buy-win", "unselected-msft"])
    save_report(root, r, p)
    return r, p


class SummaryProjectionTests(unittest.TestCase):
    """Pure frozen projections; these tests never start a listener."""

    def setUp(self):
        self.report, self.packet = lesson_fixture(bulk=True)
        self.original = deepcopy((self.report, self.packet))
        self.projection = ReviewProjection(self.report, self.packet)
        self.group = {row["symbol"]: row["id"] for row in self.projection.groups.values()}

    def tearDown(self):
        self.assertEqual((self.report, self.packet), self.original)

    def test_initial_summary_is_bounded_original_prose_with_all_saved_plans(self):
        summary = self.projection.catalog()["original_summary"]
        self.assertEqual(summary["pagination"], {"page": 0, "page_size": 12, "total_count": 227, "total_pages": 19})
        self.assertEqual([row["finding_id"] for row in summary["findings"]], [row["finding_id"] for row in self.report["findings"][:12]])
        self.assertEqual(summary["findings"][0]["interpretation"], self.report["findings"][0]["interpretation"])
        self.assertEqual(len(summary["improvement_plan"]), len(self.report["improvement_plan"]))
        for original, projected in zip(self.report["improvement_plan"], summary["improvement_plan"]):
            for key in ("exercise", "next_inputs", "verification", "review_window", "record_refs", "finding_refs"):
                self.assertEqual(projected[key], original[key])
        encoded = json.dumps(summary)
        for excluded in ("calculations", "calculation_refs", "chart_refs", "evidence_refs", "diary_refs", "packet_hash", "SYNTHETIC_PRIVATE_ACCOUNT_REF", "SYNTHETIC_RAW_DIARY"):
            self.assertNotIn(excluded, encoded)
        for row in summary["reference_records"]:
            self.assertEqual(set(row), {"record_id", "group_id", "display_date", "instrument"})
            self.assertEqual(set(row["instrument"]), {"key", "symbol", "asset_type"})
        page2 = self.projection.summary_query("page=1")
        self.assertEqual([row["finding_id"] for row in page2["findings"]], [row["finding_id"] for row in self.report["findings"][12:24]])
        all_ids = [row["finding_id"] for page in range(19) for row in self.projection.summary(page=page)["findings"]]
        self.assertEqual(all_ids, [row["finding_id"] for row in self.report["findings"]])

    def test_group_and_day_keep_primary_alternative_and_practice_associations_separate(self):
        target = self.projection.lessons["finding-acme-2024"]["practice"]
        target["record_refs"] = ["beta-2025"]
        selected = self.projection.summary(group_id=self.group["BETA"], date="2025-09-01")
        related = next(row for row in selected["findings"] if row["finding_id"] == "finding-acme-2024")
        self.assertEqual(related["record_refs"], [])
        self.assertEqual(related["summary_relations"], ["alternative", "practice"])
        for field in ("process_observation", "result_observation", "interpretation"):
            self.assertNotIn(field, related)
        self.assertEqual(related["alternative_explanations"], [{"text": self.report["findings"][0]["alternative_explanations"][0]["text"], "record_refs": ["beta-2025"]}])
        self.assertEqual(related["practice"]["record_refs"], ["beta-2025"])
        self.assertEqual(related["practice"]["exercise"], target["exercise"])
        own = next(row for row in selected["findings"] if row["finding_id"] == "finding-beta-2025")
        self.assertIn("interpretation", own)
        acme = self.projection.summary(group_id=self.group["ACME"])
        primary = next(row for row in acme["findings"] if row["finding_id"] == "finding-acme-2024")
        self.assertNotIn("practice", primary)
        self.assertEqual(primary["alternative_explanations"], [])
        self.assertEqual(primary["record_refs"], ["acme-2024"])

    def test_all_five_saved_plans_are_available_before_any_case_selection(self):
        plans = deepcopy(self.projection.review["improvement_plan"])
        while len(plans) < 5:
            item = deepcopy(plans[0])
            item.update(improvement_id=f"practice-extra-{len(plans)}", exercise=f"已保存练习原文 {len(plans)}")
            plans.append(item)
        self.projection.review["improvement_plan"] = plans
        result = self.projection.catalog()["original_summary"]["improvement_plan"]
        self.assertEqual(len(result), 5)
        self.assertEqual([row["exercise"] for row in result], [row["exercise"] for row in plans])
        self.assertEqual([row["verification"] for row in result], [row["verification"] for row in plans])

    def test_cross_security_plan_keeps_original_scope_and_is_not_exclusive_to_main_finding(self):
        plan = self.projection.review["improvement_plan"][0]
        plan.update(record_refs=["acme-2024", "beta-2025"], finding_refs=["finding-acme-2024", "finding-beta-2025"])
        for symbol in ("ACME", "BETA"):
            selected = self.projection.summary(group_id=self.group[symbol])
            projected = next(row for row in selected["improvement_plan"] if row["improvement_id"] == plan["improvement_id"])
            self.assertEqual(projected["record_refs"], plan["record_refs"])
            self.assertEqual(projected["finding_refs"], plan["finding_refs"])
            self.assertEqual(projected["scope_symbols"], ["ACME", "BETA"])
            self.assertIn("跨标的", projected["scope_label"])
        # Hitting a finding is insufficient when the plan's own trade facts do
        # not belong to the selected security.
        plan["record_refs"] = ["beta-2025"]
        self.assertNotIn(plan["improvement_id"], [row["improvement_id"] for row in self.projection.summary(group_id=self.group["ACME"])["improvement_plan"]])

    def test_asset_contract_and_range_filter_before_pagination(self):
        gid = self.group["ACME"]
        contract = self.projection.records["call-2026"]["instrument"]["key"]
        summary = self.projection.summary_query(urlencode({"page": 0, "group": gid, "asset": "OPTION", "contract": contract, "start": "2026-09-01", "end": "2026-09-01"}))
        self.assertEqual([row["finding_id"] for row in summary["findings"]], ["finding-call-2026"])
        self.assertEqual(summary["pagination"]["total_count"], 1)
        self.assertEqual(summary["selection"]["contract"], contract)
        late = self.projection.summary(group_id=self.group["BETA"], start="2026-09-02", end="2026-09-02")
        self.assertEqual(late["pagination"]["total_count"], 220)
        self.assertEqual(len(late["findings"]), 12)
        self.assertEqual(late["findings"][0]["finding_id"], "finding-beta-bulk-0")

    def test_range_uses_frozen_report_bounds_without_importing_other_security_facts(self):
        gid = self.group["BETA"]
        # These are valid bounds on the report's global date controls even
        # though BETA itself has no facts on the starting date.
        selected = self.projection.summary(group_id=gid, start="2024-09-01", end="2026-09-02")
        self.assertTrue(selected["findings"])
        self.assertNotIn("finding-acme-2026", {row["finding_id"] for row in selected["findings"]})
        self.assertEqual(selected["selection"]["start"], "2024-09-01")
        for item in selected["findings"]:
            if "main" in item["summary_relations"]:
                self.assertTrue(all(self.projection.records[rid]["group_id"] == gid for rid in item["record_refs"]))
        # A single pinned date still needs an actual record/candle for BETA.
        with self.assertRaises(ReflectionError):
            self.projection.summary(group_id=gid, date="2024-09-01")
        with self.assertRaises(ReflectionError):
            self.projection.summary(group_id=gid, start="2023-01-01", end="2026-09-02")

    def test_summary_and_group_views_do_not_expand_full_case_payloads(self):
        chart, summary_review = self.projection.select("summary", "0")
        self.assertEqual(chart["records"], [])
        self.assertEqual(chart["groups"], [])
        self.assertTrue(summary_review["original_summary"]["findings"])
        for kind, identifier in (("summary", "0"), ("group", self.group["ACME"])):
            _, selected = self.projection.select(kind, identifier)
            self.assertEqual(selected["findings"], [])
            self.assertEqual(selected["evidence"], [])
            self.assertEqual(selected["calculations"], {})
            self.assertEqual(selected["case_lessons"], [])
            self.assertTrue(selected["original_summary"]["findings"])
        _, full = self.projection.select("case", "finding-acme-2024")
        self.assertEqual(full["findings"][0], self.projection.findings["finding-acme-2024"])
        self.assertTrue(full["evidence"])
        self.assertTrue(full["calculations"])
        self.assertEqual(full["report_basis"], summary_review["report_basis"])
        landing = _landing(self.projection.catalog())
        self.assertIn('src="/view?kind=summary&amp;id=0"', landing)
        self.assertNotIn('title="图表与已保存复盘" hidden', landing)

    def test_fixed_summary_query_rejects_unknown_duplicate_and_unfrozen_selections(self):
        gid = self.group["ACME"]
        invalid = ("page=-1", "page=01", "page=19", "page=1&page=0", "path=/tmp", "size=970", "model=other", "group=unknown", "date=2026-09-01", "asset=CASH", "group=" + gid + "&date=2026-09-03", "group=" + gid + "&date=20260901", "group=" + gid + "&contract=unknown", "group=" + gid + "&start=2026-09-01", "group=" + gid + "&start=2026-09-02&end=2026-09-01", "group=" + gid + "&start=2023-01-01&end=2026-09-01", "page=0&group=&date=&asset=ALL&contract=ALL&start=&end=&extra=1")
        for query in invalid:
            with self.subTest(query=query), self.assertRaises(ReflectionError):
                self.projection.summary_query(query)
        for identifier in ("-1", "01", "../packet", "999999"):
            with self.subTest(identifier=identifier), self.assertRaises(ReflectionError):
                self.projection.select("summary", identifier)


class BoundedViewerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.r, self.p = synthetic_report(self.root)
        self.report_path = self.root / "artifacts/reflections" / self.r["report_id"] / "report.json"
        self.before = hashlib.sha256(self.report_path.read_bytes()).hexdigest()
        self.session = start_review(self.root, self.r["report_id"], load_snapshot=lambda _: self.p["snapshot"], lifetime_seconds=30)
        self.origin = self.session.url.rstrip("/")
        _, headers, _ = self.request("/")
        self.cookie = headers["Set-Cookie"].split(";", 1)[0]

    def tearDown(self):
        self.session.close()
        self.assertEqual(self.before, hashlib.sha256(self.report_path.read_bytes()).hexdigest())
        self.assertIsNone(self.session.server.projection)
        self.temp.cleanup()

    def request(self, path, method="GET", headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.session.server.server_port, timeout=3)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def auth(self):
        return {"Cookie": self.cookie, "Origin": self.origin}

    def test_initial_includes_original_prose_without_full_trade_or_case_sources(self):
        status, headers, body = self.request("/")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertNotIn(b'SYNTHETIC_PRIVATE_ACCOUNT_MUST_NOT_LEAVE', body)
        self.assertIn(self.r["findings"][0]["process_observation"].encode(), body)
        self.assertNotIn(b'"calculation_refs"', body)
        self.assertNotIn(b'"financial_claims"', body)
        catalog = re.search(rb'<script id="catalog" type="application/json">(.*?)</script>', body, re.S)[1]
        self.assertNotIn(b'"price":', catalog)
        self.assertNotIn(b'"occurred_at":', catalog)
        self.assertIn(b'/view?kind=summary&amp;id=0', body)

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行实际生成目录脚本")
    def test_landing_reader_labels_and_hidden_selection_values(self):
        catalog = self.session.server.projection.catalog()
        catalog["cases"][0]["pattern"] = "已保存案例 " + catalog["cases"][0]["finding_id"]
        page = _landing(catalog)
        runner = r'''
const fs=require("node:fs"),html=fs.readFileSync(process.argv[2],"utf8"),ids={};
class Entry{constructor(text="",value=""){this.textContent=text;this.value=value;this.children=[];this.listeners={}}add(o){this.children.push(o)}addEventListener(kind,fn){this.listeners[kind]=fn}}
for(const match of html.matchAll(/\bid="([^"]+)"/g))ids[match[1]]=new Entry();
ids.catalog.textContent=html.match(/<script id="catalog" type="application\/json">(.*?)<\/script>/s)[1];
const document={getElementById:id=>ids[id]},Option=Entry;
const script=html.match(/<script>(.*?)<\/script>/s)[1];
eval(script+`console.log(JSON.stringify({scope:ids.scope.textContent,cases:ids.case.children.map(o=>({text:o.textContent,id:o.value})),groups:ids.group.children.map(o=>({text:o.textContent,id:o.value}))}));`);
'''
        with tempfile.TemporaryDirectory() as temp:
            html = Path(temp) / "catalog.html"
            script = Path(temp) / "reader.cjs"
            html.write_text(page)
            script.write_text(runner)
            observed = json.loads(subprocess.run([shutil.which("node"), str(script), str(html)], capture_output=True, text=True, check=True, timeout=10).stdout)
        self.assertNotIn(catalog["report_id"], observed["scope"])
        self.assertNotIn("PARTIAL", observed["scope"])
        self.assertIn("部分覆盖", observed["scope"])
        self.assertEqual(observed["cases"][0]["id"], catalog["cases"][0]["finding_id"])
        self.assertNotIn(catalog["cases"][0]["finding_id"], observed["cases"][0]["text"])

    @unittest.skipUnless(shutil.which("node"), "需要 Node 执行实际生成选中页面脚本")
    def test_selected_reader_keeps_full_report_basis_with_minimal_records(self):
        projection = self.session.server.projection
        data, review = projection.select("case", "finding-1")
        self.assertLess(len(data["records"]), len(projection.chart["records"]))
        self.assertEqual(review["report_basis"], projection.review["report_basis"])
        from product.trading_journal.review import render_review_payload
        observed = execute(render_review_payload(data, review), r'''const outcome={text:$("jr-summary").textContent,metadata:$("jr-metadata").textContent,caseText:$("jr-findings").textContent,retained:DATA.records.length,basis:REVIEW.report_basis.record_count};''')
        self.assertEqual(observed["basis"], len(self.r["scope"]["record_ids"]))
        self.assertIn(f"{observed['basis']} 笔分析记录", observed["text"])
        self.assertIn("当前图窗", observed["text"])
        self.assertNotIn(self.r["report_id"], observed["text"] + observed["metadata"])
        self.assertNotIn("unselected-msft", observed["caseText"])

    def test_group_and_case_projection_only_selected_facts(self):
        group = self.session.server.projection.chart["groups"][0]["id"]
        status, _, body = self.request("/selection?" + urlencode({"kind": "group", "id": group}), headers=self.auth())
        self.assertEqual(status, 200)
        self.assertNotIn(b'unselected-msft', body)
        self.assertNotIn(b'account_ref', body)
        data = json.loads(body)
        self.assertEqual(len(data["chart"]["groups"]), 1)
        self.assertEqual(data["review"]["findings"], [])
        self.assertTrue(data["review"]["original_summary"]["findings"])
        self.assertEqual(data["review"]["progress"]["analyzed_count"], 1)
        status, _, body = self.request("/view?" + urlencode({"kind": "case", "id": "finding-1"}), headers=self.auth())
        self.assertEqual(status, 200)
        self.assertIn(self.r["findings"][0]["process_observation"].encode(), body)
        self.assertNotIn(b'unselected-msft', body)

    def test_origin_host_cookie_and_methods_fail_closed(self):
        for query in ("/selection?" + urlencode({"kind": "case", "id": "finding-1"}), "/summary?page=0", "/view?kind=summary&id=0"):
            for headers in ({}, {"Cookie": self.cookie}, {"Origin": self.origin}, {"Cookie": self.cookie, "Origin": "https://evil.example"}, {"Cookie": self.cookie, "Origin": self.origin, "Host": "evil.example"}):
                with self.subTest(query=query, headers=list(headers)):
                    self.assertEqual(self.request(query, headers=headers)[0], 403)
            same_site = {"Cookie": self.cookie, "Sec-Fetch-Site": "same-origin", "Referer": self.session.url}
            self.assertEqual(self.request(query, headers=same_site)[0], 200)
            for method in ("POST", "PUT", "PATCH", "DELETE", "OPTIONS", "TRACE"):
                self.assertEqual(self.request(query, method=method, headers=self.auth())[0], 405)

    def test_summary_route_returns_bounded_text_and_rejects_arbitrary_parameters(self):
        status, headers, body = self.request("/summary?page=0", headers=self.auth())
        self.assertEqual(status, 200)
        self.assertEqual(headers["Cache-Control"], "no-store")
        result = json.loads(body)
        self.assertEqual(set(result), {"original_summary"})
        self.assertEqual(result["original_summary"]["findings"][0]["interpretation"], self.r["findings"][0]["interpretation"])
        for query in ("page=0&page=1", "page=-1", "page=9999", "path=/tmp", "size=970", "group=unknown", "date=2026-01-05"):
            with self.subTest(query=query):
                status, _, body = self.request("/summary?" + query, headers=self.auth())
                self.assertEqual((status, body), (400, b""))

    def test_cross_case_exercise_keeps_saved_references_and_required_facts(self):
        r, p = synthetic_report(self.root, cross_case_plan=True)
        frozen = deepcopy(r)
        path = self.root / "artifacts/reflections" / r["report_id"] / "report.json"
        before = path.read_bytes()
        projection = ReviewProjection(r, p)
        data, review = projection.select("case", "finding-1")
        self.assertEqual(review["improvement_plan"], projection.review["improvement_plan"])
        self.assertEqual(review["improvement_plan"][0]["record_refs"], ["buy-win", "unselected-msft"])
        self.assertEqual(review["improvement_plan"][0]["finding_refs"], ["finding-1", "finding-msft"])
        self.assertIn("unselected-msft", {row["record_id"] for row in data["records"]})
        self.assertNotIn("unrelated-nvda", {row["record_id"] for row in data["records"]})
        self.assertEqual({row["symbol"] for row in data["groups"]}, {"AAPL", "MSFT"})
        self.assertEqual([row["finding_id"] for row in review["findings"]], ["finding-1"])
        self.assertEqual({row["finding_id"] for row in review["directory"]}, {"finding-1", "finding-msft"})
        serialized = json.dumps({"chart": data, "review": review})
        self.assertNotIn("UNSELECTED_FINDING_BODY_MUST_NOT_LEAVE", serialized)
        self.assertNotIn("SYNTHETIC_PRIVATE_ACCOUNT_MUST_NOT_LEAVE", serialized)
        other_data, other_review = projection.select("case", "finding-msft")
        self.assertEqual(other_review["findings"][0]["finding_id"], "finding-msft")
        self.assertIn("unselected-msft", {row["record_id"] for row in other_data["records"]})
        group_data, group_review = projection.select("group", data["initial_group_id"])
        self.assertNotIn("unselected-msft", {row["record_id"] for row in group_data["records"]})
        self.assertEqual(group_review["improvement_plan"], [])
        self.assertEqual(r, frozen)
        self.assertEqual(path.read_bytes(), before)

    def test_unknown_duplicate_and_file_requests_not_all_data(self):
        for path in ("/selection?kind=case&id=unknown", "/selection?kind=case&id=finding-1&id=finding-1", "/selection?kind=case&id=finding-1&path=/tmp", "/report.json", "/../report.json", "/selection?kind=file&id=report.json"):
            status, _, body = self.request(path, headers=self.auth())
            self.assertIn(status, (400, 404))
            self.assertEqual(body, b"")
        status, _, body = self.request("/catalog", method="HEAD", headers=self.auth())
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")

    def test_invalid_duration_and_mismatched_snapshot_rejected_before_start(self):
        for duration in (0, 3601, True):
            with self.assertRaises(ReflectionError):
                start_review(self.root, self.r["report_id"], load_snapshot=lambda _: self.p["snapshot"], lifetime_seconds=duration)
        with self.assertRaises(ReflectionError):
            start_review(self.root, self.r["report_id"], load_snapshot=lambda _: {}, lifetime_seconds=30)

    def test_deadline_closes_listener_and_clears_projection(self):
        short = start_review(self.root, self.r["report_id"], load_snapshot=lambda _: self.p["snapshot"], lifetime_seconds=1)
        short.timer.join(timeout=3)
        self.assertFalse(short.thread.is_alive())
        self.assertIsNone(short.server.projection)
        self.assertEqual(short.server.socket.fileno(), -1)
        short.close()
