"""新显式八维工具profile；真实stdio和冻结身份，零模型。"""
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from product.runtime.fixture_mcp import StatelessFixtureTools, TASK_TOOL_IDENTITY_VERSION, serve_stdio
from product.runtime.hashing import canonical_hash, legacy_envelope_hash
from product.runtime.multidimensional_stage import (
    build_multidimensional_dispatch_packet, serialize_multidimensional_initial_context,
    serialize_multidimensional_model_context, _task_tool_identity_context,
    MultidimensionalStageError,
)
from tests import test_multidimensional_stage as fixtures


class TaskBoundResearchToolsTests(unittest.TestCase):
    def prepare(self, root, enabled=True):
        run, _ = fixtures.MultidimensionalStageTests().prepare(root, count=1, task_bound_tools=enabled)
        index = json.loads((run / "research/dispatch-index.json").read_text())
        task = next(t for t in index["tasks"] if t["capability"] == "FUNDAMENTAL_EVENT")
        packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
        return run, task, packet

    def call(self, run, name, arguments):
        request = {"id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(request) + "\n")), patch("sys.stdout", output):
            serve_stdio(stateless=True, default_run_dir=run)
        return json.loads(output.getvalue())

    def test_actual_stdio_query_calculate_events_and_both_contexts(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepare(Path(directory))
            original = canonical_hash(packet)
            for serialize in (serialize_multidimensional_initial_context, serialize_multidimensional_model_context):
                view = json.loads(serialize(packet))
                self.assertEqual(view["tool_identity_contract"]["task_name"], task["task_name"])
                self.assertEqual(canonical_hash(packet), original)
            schemas = {t["name"]: t["inputSchema"] for t in StatelessFixtureTools(default_run_dir=run).available_tools()}
            for name in ("query", "calculate"):
                self.assertIn("task_name", schemas[name]["required"])
                self.assertTrue(set(schemas[name]["properties"]).isdisjoint({"run_id", "agent", "invocation_id", "run_dir"}))
            args = {"task_name": task["task_name"], "evidence_ids": list(packet["reference_map"]["evidence"])[:2]}
            for name, arguments in (("query", args), ("calculate", args | {"operation": "ratio"})):
                result = self.call(run, name, arguments)
                self.assertNotIn("error", result, result)
                value = result["result"]["structuredContent"]
                self.assertEqual(value["run_id"], task["run_id"])
            events = [json.loads(line) for line in (run / "events/mcp/events.jsonl").read_text().splitlines()]
            canonical = [e for e in events if e["event_type"] == "mcp_tool_result"]
            self.assertEqual(len(canonical), 2)
            for event in canonical:
                self.assertEqual(event["invocation_id"], task["invocation_id"])
                self.assertEqual(event["event_hash"], legacy_envelope_hash(event, hash_field="event_hash"))
            # Later rejected routing cannot revoke the existing successful read.
            self.assertIn("error", self.call(run, "query", args | {"task_name": "dimension_research_999"}))
            after = [json.loads(line) for line in (run / "events/mcp/events.jsonl").read_text().splitlines()]
            self.assertEqual([e for e in after if e["event_type"] == "mcp_tool_result"], canonical)
            rejected = after[-1]
            self.assertEqual(rejected["routing_state"], "UNBOUND")
            self.assertIsNone(rejected["invocation_id"])
            self.assertEqual(rejected["run_id"], task["run_id"])
            self.assertEqual(rejected["wire_input_hash"], canonical_hash(args | {"task_name": "dimension_research_999"}))

    def test_mixed_identity_unknown_task_override_and_out_of_scope_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepare(Path(directory))
            args = {"task_name": task["task_name"], "evidence_ids": list(packet["reference_map"]["evidence"])[:1]}
            for override in ({"run_id": task["run_id"]}, {"agent": task["agent"]},
                             {"invocation_id": task["invocation_id"]}, {"run_dir": str(run)},
                             {"task_name": "wrong"}, {"evidence_ids": ["e.foreign"]}):
                with self.subTest(override=override):
                    self.assertIn("error", self.call(run, "query", args | override))
            errors = [json.loads(line) for line in (run / "events/mcp/events.jsonl").read_text().splitlines()]
            self.assertEqual(len(errors), 6)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            option = next(t for t in index["tasks"] if t["capability"] == "OPTIONS_FLOW")
            denied = self.call(run, "calculate", {"task_name": option["task_name"],
                                                   "operation": "ratio", "evidence_ids": ["e.1", "e.2"]})
            self.assertIn("TOOL_NOT_AUTHORIZED", denied["error"]["message"])

    def test_v6_submit_task_route_token_and_pure_business_read(self):
        from tests.test_research_submission import ResearchSubmissionTests
        from product.runtime.research_submission import BOUNDED_REVISION_VERSION
        helper = ResearchSubmissionTests()
        with tempfile.TemporaryDirectory() as directory:
            _, run, task, _, draft = helper.submit_and_start(
                Path(directory), version=BOUNDED_REVISION_VERSION, task_bound_tools=True)
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            original = canonical_hash(packet)
            for serialize in (serialize_multidimensional_model_context, serialize_multidimensional_initial_context):
                view = json.loads(serialize(packet))
                self.assertEqual(view["tool_identity_contract"]["task_name"], task["task_name"])
                self.assertIn("不传invocation_id", view["submission_contract"]["instruction"])
                self.assertEqual(canonical_hash(packet), original)
                for report in view["dependency_reports"]:
                    numbers = [int(c["research_reference"].rsplit(".", 1)[1]) for c in report["claims"]]
                    self.assertEqual(numbers, sorted(numbers))
            for key in ("documents", "calculations", "artifact_refs"):
                draft.pop(key)
            draft.update(document_selections=[], calculation_selections=[])
            args = {"task_name": task["task_name"], "submission_token": helper.token(run, task), "draft": draft}
            self.assertIn("error", self.call(run, "research_report_submit", args | {"submission_token": "wrong"}))
            result = self.call(run, "research_report_submit", args)
            self.assertNotIn("error", result, result)
            receipt = result["result"]["structuredContent"]
            self.assertEqual(receipt["status"], "DRAFT_STORED_NOT_VALIDATED")
            report, _, _, _ = helper.read_bounded_submission(run, task, receipt)
            self.assertEqual(report["summary"], draft["summary"])
            self.assertEqual(report["data_gaps"], draft["data_gaps"])
            self.assertEqual(report["invocation_id"], task["invocation_id"])
            events = (run / "events/mcp/events.jsonl").read_text()
            self.assertNotIn(helper.token(run, task), events)
            self.assertFalse((run / "invocation/subagent-events.jsonl").exists())
            self.assertFalse(any((run / "research/submissions").rglob("accepted.json")))

    def test_index_and_invocation_tampering_rejected(self):
        for kind in ("index", "ambiguous", "invocation", "profile"):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as directory:
                run, task, packet = self.prepare(Path(directory))
                path = run / (task["invocation_path"] if kind == "invocation" else "research/dispatch-index.json")
                value = json.loads(path.read_text())
                if kind == "invocation":
                    value["tool_permissions"] = []
                elif kind == "ambiguous":
                    value["tasks"].append(copy.deepcopy(value["tasks"][0]))
                    value["index_hash"] = legacy_envelope_hash(value, hash_field="index_hash")
                    manifest_path = run / "run_manifest.json"
                    manifest = json.loads(manifest_path.read_text())
                    manifest["dispatch_index_hash"] = value["index_hash"]
                    manifest["manifest_hash"] = legacy_envelope_hash(manifest, hash_field="manifest_hash")
                    manifest_path.write_text(json.dumps(manifest))
                elif kind == "profile":
                    value["tasks"][0].pop("tool_identity_version")
                else:
                    value["run_id"] = "foreign"
                path.write_text(json.dumps(value))
                result = self.call(run, "query", {"task_name": task["task_name"], "evidence_ids": []})
                self.assertIn("error", result)

    def test_old_profile_and_unbound_catalog_keep_original_interface(self):
        with tempfile.TemporaryDirectory() as directory:
            run, task, packet = self.prepare(Path(directory), enabled=False)
            schema = next(t["inputSchema"] for t in StatelessFixtureTools(default_run_dir=run).available_tools() if t["name"] == "query")
            self.assertIn("invocation_id", schema["required"])
            self.assertNotIn("task_name", schema["properties"])
            self.assertNotIn("tool_identity_contract", json.loads(serialize_multidimensional_model_context(packet)))
            args = {k: task[k] for k in ("run_id", "agent", "invocation_id")}
            self.assertNotIn("error", self.call(run, "query", args | {"evidence_ids": list(packet["reference_map"]["evidence"])[:1]}))
            self.assertIn("error", self.call(run, "query", {"task_name": task["task_name"], "evidence_ids": []}))
            self.assertNotIn("task_name", StatelessFixtureTools().available_tools()[0]["inputSchema"]["properties"])

    def test_option_selector_explicit_patch_requires_actual_task_query(self):
        from product.tools.revision import _apply
        from product.runtime.multidimensional_stage import prepare_multidimensional_stage_run
        for scenario in ("valid", "wrong_field", "unqueried", "foreign_task"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                helper = fixtures.MultidimensionalStageTests()
                handoff = fixtures.stock_handoff(1)
                gate = fixtures.gate_for(handoff)
                quote = {"evidence_id": "ev-option-quote", "security_id": "US:COMMON_STOCK:AAPL",
                         "semantic_field": "moomoo_option_quote:contract", "dataset": "options_snapshot",
                         "source_type": "SECONDARY_VENDOR", "source_id": "moomoo-opend",
                         "as_of": "2026-09-10T19:58:46Z", "retrieved_at": "2026-09-11T09:00:00Z",
                         "value": {"bid": "5.35", "ask": "5.55", "contract_symbol": "US.AAPL261002C270000"}}
                gate["allowed_evidence"].append(quote)
                for key in ("input_evidence_ids", "allowed_evidence_ids"):
                    gate[key].append(quote["evidence_id"])
                gate["bundle_hash"] = legacy_envelope_hash(gate, hash_field="bundle_hash")
                for name, value in (("handoff", handoff), ("gate", gate)):
                    (root / (name + ".json")).write_text(json.dumps(value))
                run = root / "run"
                prepare_multidimensional_stage_run(fixtures.ROOT, handoff_path=root / "handoff.json",
                    gate_path=root / "gate.json", run_dir=run, run_id="option-selector-missing",
                    model="gpt-5.6-terra", task_bound_tools=True)
                tasks = json.loads((run / "research/dispatch-index.json").read_text())["tasks"]
                task = next(t for t in tasks if t["capability"] == "OPTIONS_FLOW")
                packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
                short = next(k for k, v in packet["reference_map"]["evidence"].items() if v == quote["evidence_id"])
                query = {"task_name": task["task_name"], "evidence_ids": [short]}
                if scenario == "foreign_task":
                    foreign = next(t for t in tasks if t["capability"] == "FUNDAMENTAL_EVENT")
                    self.assertIn("error", self.call(run, "query", query | {"task_name": foreign["task_name"]}))
                elif scenario != "unqueried":
                    self.assertNotIn("error", self.call(run, "query", query))
                draft = helper.dimension_draft(task)
                draft["claims"] = [{"claim_id": "quote", "question": "报价时间？", "statement": "盘口{{sf.time}}。",
                                    "kind": "FACT", "evidence_refs": [short], "research_claim_refs": [],
                                    "document_refs": [], "assumption_ids": []}]
                before = copy.deepcopy(draft)
                with self.assertRaisesRegex(ValueError, "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID"):
                    helper.read_dimension_draft(run, task, draft)
                # 测试给定作用域只验证补丁算法，不代表宿主或服务端签发修订权限。
                correction = _apply(draft, [{"op": "add", "path": "/source_literal_selections", "value": [{
                    "claim_id": "quote", "placeholder": "{{sf.time}}", "evidence_ref": short,
                    "field": "sec_usd_value" if scenario == "wrong_field" else "as_of",
                }]}], ["/source_literal_selections"])
                if scenario != "valid":
                    with self.assertRaisesRegex(ValueError, "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID"):
                        helper.read_dimension_draft(run, task, correction)
                if scenario == "foreign_task":
                    self.assertNotIn("error", self.call(run, "query", query))
                if scenario in {"valid", "foreign_task"}:
                    report, _ = helper.save_dimension_fixture(run, task, correction)
                    self.assertEqual(report["claims"][0]["statement"], "盘口as_of=2026-09-10T19:58:46Z。")
                else:
                    self.assertFalse((run / "research/reports").exists())
                self.assertEqual(draft, before)
                self.assertFalse((run / "invocation/subagent-events.jsonl").exists())
                self.assertFalse((run / "research/raw-drafts").exists())

    def test_reference_display_is_numeric_per_report_lossless_and_opt_in(self):
        reports = [{"report_id": "r", "report_hash": "original", "claims": [
            {"claim_id": "valuation", "statement": "估值原句"},
            {"claim_id": "events", "statement": "事件原句"}]}]
        mapping = {"c.a.10": {"report_id": "r", "claim_id": "valuation"},
                   "c.a.2": {"report_id": "r", "claim_id": "events"}}
        packet = {"task": {"task_name": "dimension_research_3", "tool_identity_version": TASK_TOOL_IDENTITY_VERSION},
                  "reference_map": {"claims": mapping}}
        view = {"dependency_reports": copy.deepcopy(reports)}
        _task_tool_identity_context(view, packet)
        self.assertEqual([c["claim_id"] for c in view["dependency_reports"][0]["claims"]], ["events", "valuation"])
        for claim in view["dependency_reports"][0]["claims"]:
            self.assertEqual(mapping[claim["research_reference"]]["claim_id"], claim["claim_id"])
            self.assertIn({k: v for k, v in claim.items() if k != "research_reference"}, reports[0]["claims"])
        self.assertEqual(view["dependency_reports"][0]["report_hash"], "original")
        legacy = {"dependency_reports": copy.deepcopy(reports)}
        _task_tool_identity_context(legacy, {"task": {}})
        self.assertEqual(legacy, {"dependency_reports": reports})
        for invalid in ({}, {**mapping, "c.a.3": mapping["c.a.2"]}):
            with self.assertRaises(MultidimensionalStageError):
                _task_tool_identity_context({"dependency_reports": copy.deepcopy(reports)},
                                            {**packet, "reference_map": {"claims": invalid}})
