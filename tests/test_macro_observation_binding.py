"""宏观选择按同一来源行装配；不模拟模型语义验收。"""

import copy
import json
import tempfile
import unittest
from pathlib import Path

from product.runtime.codex_hook_recorder import (
    _bind_source_literal_selections, _source_literal_marker_findings, handle_hook_event,
)
from product.runtime.fixture_mcp import StatelessFixtureTools, _write_event
from product.runtime.hashing import canonical_hash
from product.runtime.multidimensional_stage import (
    MINIMUM_QUESTIONS,
    build_multidimensional_dispatch_packet, prepare_multidimensional_stage_run,
    serialize_multidimensional_initial_context, serialize_multidimensional_model_context,
)
from tests.test_common_stock_research_contracts import gate_for, stock_handoff
from tests import test_multidimensional_stage as fixtures


ROOT = Path(__file__).resolve().parents[1]


def observation(identifier="new", *, old=False):
    return {
        "evidence_id": identifier, "security_id": "US:MARKET", "dataset": "macro_history",
        "source_family": "moomoo_sg", "source_type": "SECONDARY_VENDOR",
        "source_id": "moomoo-sg-opend-macro:1003000010",
        "semantic_field": "moomoo_us_retail_sales_mom:" + identifier,
        "as_of": "2025-07-01T00:00:00Z" if old else "2026-08-01T00:00:00Z",
        "retrieved_at": "2026-09-09T12:00:00Z",
        "value": {
            "indicator_id": 1003000010, "label": "零售销售环比",
            "actual": 0.011600000000000001 if old else 0.012400000000000001,
            "previous": 0.007 if old else -0.0054, "consensus": "N/A",
            "unit_type": "PERCENT", "raw_release_time": "2025-08-15 20:31:01" if old else "2026-09-09 20:31:01",
            "vintage_status": "CURRENT_VENDOR_SNAPSHOT",
        },
    }


class MacroObservationBindingTests(unittest.TestCase):
    def test_illegal_marker_locations_are_found_without_selectors_or_source_text(self):
        draft = {"summary": "private {{sf.revenue}} text", "claims": [
            {"claim_id": "c", "statement": "legal {{sf.revenue}}", "question": "{{sf.bad}}"}],
            "data_gaps": [{"description": "{{sf.gap}}"}],
            "source_literal_selections": [{"claim_id": "c", "placeholder": "{{sf.revenue}}"}]}
        original = copy.deepcopy(draft)
        findings = _source_literal_marker_findings(draft)
        self.assertEqual([f["path"] for f in findings], ["/summary", "/claims/0/question", "/data_gaps/0/description"])
        self.assertTrue(all(f["reason"] == "MARKER_OUTSIDE_STATEMENT" for f in findings))
        self.assertNotIn("private", json.dumps(findings))
        self.assertEqual(draft, original)
        self.assertEqual(_source_literal_marker_findings({"summary": "{{sf.s}}"})[0]["path"], "/summary")
        self.assertEqual(len(_source_literal_marker_findings({"gaps": ["{{sf.x}}"] * 100})), 16)

    def test_real_hook_locates_illegal_summary_and_requires_remove_not_null(self):
        helper = fixtures.MultidimensionalStageTests()
        for capability in ("MACRO_CONTEXT", "FUNDAMENTAL_EVENT"):
            for scenario in ("save", "delete", "null", "outside"):
                with self.subTest(capability=capability, scenario=scenario), tempfile.TemporaryDirectory() as temp:
                    root = Path(temp)
                    handoff, gate = stock_handoff(1), gate_for(stock_handoff(1))
                    if capability == "MACRO_CONTEXT":
                        fact, field = observation(), "moomoo_macro_observation"
                        gate["allowed_evidence"].append(fact)
                        for key in ("input_evidence_ids", "allowed_evidence_ids"):
                            gate[key] = sorted([*gate[key], fact["evidence_id"]])
                    else:
                        fact = next(f for f in gate["allowed_evidence"] if f["evidence_id"] == "ev-aapl-revenue")
                        fact.update(source_type="sec", unit="USD", value="100")
                        field = "sec_usd_value"
                    gate["bundle_hash"] = canonical_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
                    for name, value in (("handoff", handoff), ("gate", gate)):
                        (root / (name + ".json")).write_text(json.dumps(value))
                    run = root / "run"
                    prepare_multidimensional_stage_run(ROOT, handoff_path=root / "handoff.json", gate_path=root / "gate.json",
                                                      run_dir=run, run_id="outside-marker", model="gpt-5.6-terra", task_bound_tools=True)
                    task = next(t for t in json.loads((run / "research/dispatch-index.json").read_text())["tasks"]
                                if t["capability"] == capability)
                    packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
                    short = next(k for k, v in packet["reference_map"]["evidence"].items() if v == fact["evidence_id"])
                    env = helper.targeted_environment(run, task)
                    parent, child = "outside-parent", "outside-child"
                    handle_hook_event(helper.dispatch_payload(task, parent=parent), environ=env)
                    handle_hook_event(helper.start_payload(task, parent=parent, child=child), environ=env)
                    tool = StatelessFixtureTools(default_run_dir=run)
                    tool.query(**tool.bind_task_tool_arguments("query", {"task_name": task["task_name"], "evidence_ids": [short]}))
                    _write_event(run / "events/mcp/events.jsonl", tool.events[-1])
                    draft = helper.dimension_draft(task)
                    draft["summary"] = "摘要不合法使用{{sf.first}}。"
                    draft["claims"] = [{"claim_id": "source", "question": "来源事实？", "kind": "FACT",
                                        "statement": "{{sf.first}}；{{sf.second}}；{{sf.third}}", "evidence_refs": [short],
                                        "research_claim_refs": [], "document_refs": [], "assumption_ids": []}]
                    draft["source_literal_selections"] = [{"claim_id": "source", "placeholder": "{{sf." + name + "}}",
                                                           "evidence_ref": short, "field": field} for name in ("first", "second", "third")]
                    original = copy.deepcopy(draft)
                    first, response = handle_hook_event(helper.stop_payload(task, draft, parent=parent, child=child), environ=env)
                    self.assertEqual(first["output_capture"]["failure_code"], "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID")
                    repair = json.loads(response["reason"])
                    self.assertEqual(repair["validation_details"]["findings"], [{
                        "code": "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID", "path": "/summary",
                        "reason": "MARKER_OUTSIDE_STATEMENT", "observed_count": 1}])
                    self.assertIn("/summary", repair["allowed_paths"])
                    self.assertNotIn("/data_gaps", repair["allowed_paths"])
                    self.assertIn("不能replace成null", repair["instruction"])
                    raw = run / first["output_capture"]["raw_path"]
                    raw_bytes = raw.read_bytes()
                    changes = [{"op": "replace", "path": "/summary", "value": "作者重述摘要，具体原值见来源主张。"}]
                    if scenario in {"delete", "null"}:
                        changes.append({"op": "replace", "path": "/claims/0/statement", "value": "{{sf.first}}"})
                        for i in (1, 2):
                            changes.append({"op": "remove", "path": f"/source_literal_selections/{i}"} if scenario == "delete" else
                                           {"op": "replace", "path": f"/source_literal_selections/{i}", "value": None})
                    if scenario == "outside":
                        changes.append({"op": "replace", "path": "/data_gaps", "value": []})
                    patch = {"base_draft_ref": repair["base_draft_ref"], "changes": changes}
                    second, _ = handle_hook_event(helper.stop_payload(task, patch, parent=parent, child=child), environ=env)
                    self.assertEqual(second["output_capture"]["status"], "SAVED" if scenario in {"save", "delete"} else "FAILED", second)
                    self.assertEqual(raw.read_bytes(), raw_bytes)
                    self.assertEqual(draft, original)
                    if scenario in {"save", "delete"}:
                        report = json.loads((run / second["output_capture"]["path"]).read_text())
                        self.assertEqual(report["summary"], changes[0]["value"])
                        self.assertNotIn("{{sf.", report["claims"][0]["statement"])
                        self.assertNotIn("source_literal_selections", report)
                    else:
                        self.assertEqual(second["output_capture"]["repair_state"], "EXHAUSTED")
                        prefix = "SCHEMA_TYPE_INVALID" if scenario == "null" else "LOCAL_REVISION_OUT_OF_SCOPE"
                        self.assertTrue(second["output_capture"]["failure_code"].startswith(prefix))

    def test_marker_diagnostics_are_bounded_ast_only_and_do_not_claim_source_validity(self):
        draft = {"claims": [{"claim_id": "activity", "statement": "{{sf.duplicate}}{{sf.duplicate}}"}],
                 "source_literal_selections": [
                     {"claim_id": "activity", "placeholder": marker, "evidence_ref": "unread",
                      "field": "moomoo_macro_observation"}
                     for marker in ("{{sf.jobs}}", "{{sf.retail}}", "{{sf.unemployment}}", "{{sf.duplicate}}")
                 ]}
        original = copy.deepcopy(draft)
        findings = _source_literal_marker_findings(draft)
        self.assertEqual([f["observed_count"] for f in findings], [0, 0, 0, 2])
        self.assertEqual([f["path"] for f in findings], [f"source_literal_selections[{i}]" for i in range(4)])
        self.assertTrue(all(f["related_claim_path"] == "claims[0].statement" for f in findings))
        self.assertNotIn("unread", json.dumps(findings))
        self.assertEqual(draft, original)
        draft["source_literal_selections"][0]["claim_id"] = "unknown"
        self.assertEqual(_source_literal_marker_findings(draft)[0]["reason"], "TARGET_CLAIM_MISSING")
        draft["source_literal_selections"][0]["placeholder"] = "malformed secret text"
        self.assertNotIn("secret", json.dumps(_source_literal_marker_findings(draft)))
        draft["source_literal_selections"] *= 5
        self.assertEqual(_source_literal_marker_findings(draft), [])

    def test_all_missing_markers_reported_and_original_single_revision_enforced(self):
        helper = fixtures.MultidimensionalStageTests()
        for scenario in ("save", "partial", "source_invalid", "out_of_scope", "mixed_source_and_marker"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                handoff = stock_handoff(1)
                gate = gate_for(handoff)
                fact = observation()
                gate["allowed_evidence"].append(fact)
                if scenario == "mixed_source_and_marker":
                    gate["allowed_evidence"].append(observation("old", old=True))
                for key in ("input_evidence_ids", "allowed_evidence_ids"):
                    gate[key].append(fact["evidence_id"])
                    if scenario == "mixed_source_and_marker":
                        gate[key].append("old")
                    gate[key].sort()
                gate["bundle_hash"] = canonical_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
                for name, value in (("handoff", handoff), ("gate", gate)):
                    (root / (name + ".json")).write_text(json.dumps(value))
                run = root / "run"
                prepare_multidimensional_stage_run(ROOT, handoff_path=root / "handoff.json", gate_path=root / "gate.json",
                                                  run_dir=run, run_id="macro-counts", model="gpt-5.6-terra",
                                                  task_bound_tools=True)
                task = next(t for t in json.loads((run / "research/dispatch-index.json").read_text())["tasks"]
                            if t["capability"] == "MACRO_CONTEXT")
                packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
                short = next(k for k, v in packet["reference_map"]["evidence"].items() if v == fact["evidence_id"])
                env = helper.targeted_environment(run, task)
                parent, child = "marker-parent", "marker-child"
                handle_hook_event(helper.dispatch_payload(task, parent=parent), environ=env)
                handle_hook_event(helper.start_payload(task, parent=parent, child=child), environ=env)
                tool = StatelessFixtureTools(default_run_dir=run)
                tool.query(**tool.bind_task_tool_arguments("query", {"task_name": task["task_name"], "evidence_ids": [short]}))
                _write_event(run / "events/mcp/events.jsonl", tool.events[-1])
                draft = helper.dimension_draft(task)
                template = {"claim_id": "activity", "question": "经济活动事实？", "kind": "FACT",
                            "statement": "作者尚未放入声明的占位。", "evidence_refs": [short],
                            "research_claim_refs": [], "document_refs": [], "assumption_ids": []}
                draft["claims"] = [template, {**copy.deepcopy(template), "claim_id": "untouched"}]
                markers = ["{{sf.jobs}}", "{{sf.retail}}", "{{sf.unemployment}}"]
                draft["source_literal_selections"] = [
                    {"claim_id": "activity", "placeholder": marker, "evidence_ref": short,
                     "field": "moomoo_macro_observation"} for marker in markers]
                if scenario == "mixed_source_and_marker":
                    draft["claims"][0]["statement"] = markers[0]
                    old_ref = next(k for k, v in packet["reference_map"]["evidence"].items() if v == "old")
                    draft["claims"][0]["evidence_refs"].append(old_ref)
                    draft["source_literal_selections"][0]["evidence_ref"] = old_ref  # Allowed but never queried.
                first, response = handle_hook_event(helper.stop_payload(task, draft, parent=parent, child=child), environ=env)
                self.assertEqual(first["output_capture"]["repair_state"], "REPAIR_REQUESTED", first)
                repair = json.loads(response["reason"])
                self.assertEqual([f["observed_count"] for f in repair["validation_details"]["findings"]],
                                 [0, 0] if scenario == "mixed_source_and_marker" else [0, 0, 0])
                self.assertIn("/source_literal_selections/0", repair["allowed_paths"])
                self.assertNotIn("/claims/1", repair["allowed_paths"])
                self.assertEqual(repair["validation_details"]["source_validation"], "NOT_PROVEN_BY_MARKER_DIAGNOSTIC")
                raw_path = run / first["output_capture"]["raw_path"]
                raw_bytes = raw_path.read_bytes()
                chosen = markers if scenario != "partial" else [markers[0], markers[2]]
                changes = [{"op": "replace", "path": "/claims/0/statement", "value": "；".join(chosen)}]
                if scenario == "mixed_source_and_marker":
                    changes.extend([
                        {"op": "replace", "path": "/source_literal_selections/0/evidence_ref", "value": short},
                        {"op": "replace", "path": "/claims/0/evidence_refs", "value": [short]},
                    ])
                if scenario == "source_invalid":
                    changes.append({"op": "replace", "path": "/source_literal_selections/1/field", "value": "as_of"})
                if scenario == "out_of_scope":
                    changes.append({"op": "replace", "path": "/claims/1/statement", "value": "禁止改写"})
                patch = {"base_draft_ref": repair["base_draft_ref"], "changes": changes}
                second, _ = handle_hook_event(helper.stop_payload(task, patch, parent=parent, child=child), environ=env)
                success = scenario in {"save", "mixed_source_and_marker"}
                self.assertEqual(second["output_capture"]["status"], "SAVED" if success else "FAILED", second)
                self.assertEqual(raw_path.read_bytes(), raw_bytes)
                if success:
                    report = json.loads((run / second["output_capture"]["path"]).read_text())
                    self.assertEqual(report["claims"][1]["statement"], draft["claims"][1]["statement"])
                    self.assertEqual(report["claims"][0]["statement"].count("actual(原值)="), 3)
                else:
                    self.assertEqual(second["output_capture"]["repair_state"], "EXHAUSTED", second)

    def pure_fixture(self, run):
        (run / "evidence").mkdir()
        (run / "events/mcp").mkdir(parents=True)
        facts = [observation(), observation("old", old=True)]
        gate = {"decision_cutoff": "2026-09-28T12:35:32Z", "allowed_evidence": facts}
        task = {
            "capability": "MACRO_CONTEXT", "source_literal_selection": "source-literal-selection/1.1.0",
            "tool_identity_version": "research-tool-identity/1.0.0", "run_id": "run",
            "invocation_id": "inv", "agent": "runtime_market_catalyst",
            "security_ids": ["US:COMMON_STOCK:MRVL"], "allowed_evidence_ids": ["new", "old"],
        }
        event = {"event_type": "mcp_tool_result", "tool": "fixture_evidence.query", "access_mode": "read",
                 "run_id": "run", "invocation_id": "inv", "agent": task["agent"], "evidence_ids": ["new"]}
        mapping = {"evidence": {"e.new": "new", "e.old": "old"}}
        draft = {
            "claims": [{"claim_id": "activity", "statement": "观察{{sf.retail}}；反向情景仍由研究者判断。",
                        "evidence_refs": ["e.new"]}],
            "source_literal_selections": [{"claim_id": "activity", "placeholder": "{{sf.retail}}",
                                           "evidence_ref": "e.new", "field": "moomoo_macro_observation"}],
        }
        return gate, task, event, mapping, draft

    def bind(self, run, gate, task, event, mapping, draft):
        gate = copy.deepcopy(gate)
        gate["bundle_hash"] = canonical_hash(gate)
        (run / "evidence/gate.json").write_text(json.dumps(gate))
        event = copy.deepcopy(event)
        event["event_hash"] = canonical_hash(event)
        (run / "events/mcp/events.jsonl").write_text(json.dumps(event) + "\n")
        return _bind_source_literal_selections(draft, task=task, run_dir=run, reference_map=mapping)

    def test_one_record_roles_and_period_are_preserved_without_scaling(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            args = self.pure_fixture(run)
            original = copy.deepcopy(args[-1])
            result = self.bind(run, *args)
            statement = result["claims"][0]["statement"]
            for text in ("2026-08-01", "actual(原值)=0.012400000000000001",
                         "previous(原值)=-0.0054", "consensus(原值)=N/A", "PERCENT",
                         "2026-09-09 20:31:01", "时区未核实", "历史vintage未核实", "反向情景仍由研究者判断"):
                self.assertIn(text, statement)
            self.assertNotIn("2025-07", statement)
            self.assertNotIn("1.24%", statement)
            self.assertEqual(original, args[-1])
            self.assertNotIn("source_literal_selections", result)

    def test_unread_or_uncited_old_record_rejected_but_read_old_not_auto_upgraded(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            gate, task, event, mapping, draft = self.pure_fixture(run)
            draft["source_literal_selections"][0]["evidence_ref"] = "e.old"
            for read in (False, True):
                with self.subTest(read=read):
                    event["evidence_ids"] = ["new", "old"] if read else ["new"]
                    with self.assertRaisesRegex(ValueError, "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID"):
                        self.bind(run, gate, task, event, mapping, draft)
            draft["claims"][0]["evidence_refs"] = ["e.old"]
            statement = self.bind(run, gate, task, event, mapping, draft)["claims"][0]["statement"]
            self.assertIn("2025-07-01", statement)
            self.assertIn("actual(原值)=0.011600000000000001", statement)
            self.assertNotIn("2026-08", statement)

    def test_invalid_source_version_time_and_scalar_are_rejected(self):
        mutations = [
            ("source_family", "sec"), ("security_id", "US:COMMON_STOCK:MRVL"),
            ("dataset", "options_snapshot"), ("source_id", "moomoo-sg-opend-macro:999"),
            ("as_of", "2027-08-01T00:00:00Z"),
            ("value.actual", float("nan")), ("value.previous", True),
            ("value.consensus", "infinity"), ("value.unit_type", ""),
            ("value.raw_release_time", "not-a-date"), ("value.label", "x" * 129),
        ]
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            args = self.pure_fixture(run)
            for key, value in mutations:
                gate, task, event, mapping, draft = copy.deepcopy(args)
                target = gate["allowed_evidence"][0]
                if key.startswith("value."):
                    target = target["value"]
                    key = key.split(".")[1]
                target[key] = value
                with self.subTest(key=key, value=str(value)), self.assertRaises(ValueError):
                    self.bind(run, gate, task, event, mapping, draft)
            for version in (None, "source-literal-selection/1.0.0", "unknown"):
                gate, task, event, mapping, draft = copy.deepcopy(args)
                task["source_literal_selection"] = version
                with self.subTest(version=version), self.assertRaises(ValueError):
                    self.bind(run, gate, task, event, mapping, draft)
            gate, task, event, mapping, draft = copy.deepcopy(args)
            gate["allowed_evidence"][0]["value"]["actual"] = None
            self.assertIn("actual(原值)=null（原缺失）", self.bind(run, gate, task, event, mapping, draft)["claims"][0]["statement"])

    def test_new_profile_delivery_real_query_and_hook_save_old_profile_isolated(self):
        helper = fixtures.MultidimensionalStageTests()
        baseline = copy.deepcopy(MINIMUM_QUESTIONS)
        for enabled, scenario in ((False, "save"), (True, "save"), (True, "repair"), (True, "bad_repair")):
            with self.subTest(enabled=enabled, scenario=scenario), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                handoff = stock_handoff(1)
                gate = gate_for(handoff)
                fact = observation()
                gate["allowed_evidence"].append(fact)
                for key in ("input_evidence_ids", "allowed_evidence_ids"):
                    gate[key].append(fact["evidence_id"])
                    gate[key].sort()
                gate["bundle_hash"] = canonical_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
                handoff_path, gate_path = root / "handoff.json", root / "gate.json"
                handoff_path.write_text(json.dumps(handoff))
                gate_path.write_text(json.dumps(gate))
                run = root / "run"
                prepare_multidimensional_stage_run(ROOT, handoff_path=handoff_path, gate_path=gate_path,
                                                  run_dir=run, run_id="macro-bound", model="gpt-5.6-terra",
                                                  task_bound_tools=enabled)
                task = next(t for t in json.loads((run / "research/dispatch-index.json").read_text())["tasks"]
                            if t["capability"] == "MACRO_CONTEXT")
                packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
                self.assertEqual("source_literal_selection" in task, enabled)
                for body in (serialize_multidimensional_initial_context(packet), serialize_multidimensional_model_context(packet)):
                    self.assertEqual("moomoo_macro_observation" in body, enabled)
                    questions = json.loads(body)["minimum_questions"]
                    self.assertEqual("代表观测" in questions[0], enabled)
                    self.assertEqual("同一claim引用" in questions[0], enabled)
                    self.assertEqual(questions, packet["minimum_questions"])
                    if not enabled:
                        self.assertEqual(questions, baseline["MACRO_CONTEXT"])
                invocation = json.loads((run / task["invocation_path"]).read_text())
                self.assertEqual(invocation["prompt_hash"], canonical_hash({
                    "instruction": packet["instruction"], "questions": packet["minimum_questions"]}))
                env = helper.targeted_environment(run, task)
                handle_hook_event(helper.dispatch_payload(task, parent="macro-parent"), environ=env)
                start, ctx = handle_hook_event(helper.start_payload(task, parent="macro-parent", child="macro-child"), environ=env)
                self.assertEqual(start["context_binding"]["status"], "DELIVERED")
                actual = ctx["hookSpecificOutput"]["additionalContext"]
                self.assertEqual("代表观测" in actual, enabled)
                self.assertEqual(MINIMUM_QUESTIONS, baseline)
                if not enabled:
                    continue
                field_schema = packet["output_schema"]["properties"]["source_literal_selections"]["items"]["properties"]["field"]
                self.assertEqual(field_schema["enum"], ["moomoo_macro_observation"])
                short = next(k for k, v in packet["reference_map"]["evidence"].items() if v == fact["evidence_id"])
                self.assertIn("moomoo_macro_observation", ctx["hookSpecificOutput"]["additionalContext"])
                tool = StatelessFixtureTools(default_run_dir=run)
                arguments = tool.bind_task_tool_arguments("query", {"task_name": task["task_name"], "evidence_ids": [short]})
                tool.query(**arguments)
                _write_event(run / "events/mcp/events.jsonl", tool.events[-1])
                draft = helper.dimension_draft(task)
                draft["claims"] = [{"claim_id": "activity", "question": "经济活动事实？", "kind": "FACT",
                                    "statement": "供应商观测{{sf.retail}}。", "evidence_refs": [short],
                                    "research_claim_refs": [], "document_refs": [], "assumption_ids": []}]
                draft["source_literal_selections"] = [{"claim_id": "activity", "placeholder": "{{sf.retail}}",
                                                       "evidence_ref": short, "field": "moomoo_macro_observation"}]
                if scenario != "save":
                    chosen = draft.pop("source_literal_selections")
                    first, response = handle_hook_event(helper.stop_payload(task, draft, parent="macro-parent", child="macro-child"), environ=env)
                    self.assertEqual(first["output_capture"]["repair_state"], "REPAIR_REQUESTED", first)
                    repair = json.loads(response["reason"])
                    self.assertEqual(repair["allowed_paths"], ["/source_literal_selections"])
                    original_path = run / first["output_capture"]["raw_path"]
                    original_bytes = original_path.read_bytes()
                    if scenario == "bad_repair":
                        chosen[0]["field"] = "as_of"
                    draft = {"base_draft_ref": repair["base_draft_ref"], "changes": [
                        {"op": "add", "path": "/source_literal_selections", "value": chosen},
                    ]}
                stop, _ = handle_hook_event(helper.stop_payload(task, draft, parent="macro-parent", child="macro-child"), environ=env)
                if scenario != "save":
                    self.assertEqual(original_path.read_bytes(), original_bytes)
                if scenario == "bad_repair":
                    self.assertEqual(stop["output_capture"]["status"], "FAILED", stop)
                    self.assertEqual(stop["output_capture"]["repair_state"], "EXHAUSTED", stop)
                    continue
                self.assertEqual(stop["output_capture"]["status"], "SAVED", stop["output_capture"])
                report = json.loads((run / stop["output_capture"]["path"]).read_text())
                self.assertIn("actual(原值)=0.012400000000000001", report["claims"][0]["statement"])
                self.assertNotIn("source_literal_selections", report)


if __name__ == "__main__":
    unittest.main()
