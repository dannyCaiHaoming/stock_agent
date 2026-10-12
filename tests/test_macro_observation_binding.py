"""宏观历史选择的纯业务校验；不模拟Hook、作者或实际模型执行。"""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from product.runtime.fixture_mcp import StatelessFixtureTools, _write_event
from product.runtime.hashing import canonical_hash
from product.runtime.multidimensional_stage import (
    MINIMUM_QUESTIONS, _bind_source_literal_selections,
    build_multidimensional_dispatch_packet, prepare_multidimensional_stage_run,
    serialize_multidimensional_initial_context, serialize_multidimensional_model_context,
)
from tests.test_common_stock_research_contracts import gate_for, stock_handoff

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
    def test_marker_scope_count_shape_and_task_binding_fail_without_mutation(self):
        with tempfile.TemporaryDirectory() as temp:
            run = Path(temp)
            base = self.pure_fixture(run)
            for scenario in ("summary", "question", "gap", "missing", "duplicate", "undeclared",
                             "wrong_claim", "wrong_field", "null", "too_many", "wrong_agent",
                             "wrong_task", "wrong_event_hash", "no_permission"):
                gate, task, event, mapping, draft = copy.deepcopy(base)
                marker = "{{sf.retail}}"
                if scenario == "summary": draft["summary"] = marker
                elif scenario == "question": draft["claims"][0]["question"] = marker
                elif scenario == "gap": draft["data_gaps"] = [{"description": marker}]
                elif scenario == "missing": draft["claims"][0]["statement"] = "未放入占位"
                elif scenario == "duplicate": draft["claims"][0]["statement"] += marker
                elif scenario == "undeclared": draft["claims"][0]["statement"] += "{{sf.other}}"
                elif scenario == "wrong_claim": draft["source_literal_selections"][0]["claim_id"] = "unknown"
                elif scenario == "wrong_field": draft["source_literal_selections"][0]["field"] = "as_of"
                elif scenario == "null": draft["source_literal_selections"][0] = None
                elif scenario == "too_many": draft["source_literal_selections"] *= 17
                elif scenario == "wrong_agent": event["agent"] = "runtime_company_analyst"
                elif scenario == "wrong_task": event["invocation_id"] = "other-invocation"
                elif scenario == "no_permission": task["allowed_evidence_ids"] = []
                else: event["event_hash"] = "forged"
                original = copy.deepcopy(draft)
                with self.subTest(scenario=scenario), self.assertRaisesRegex(
                    ValueError, "DIMENSION_SOURCE_LITERAL_SELECTION_INVALID"
                ):
                    self.bind(run, gate, task, event, mapping, draft)
                self.assertEqual(draft, original)
                self.assertFalse((run / "research").exists())

    def test_profile_delivery_and_real_query_feed_pure_binding_without_hook(self):
        baseline = copy.deepcopy(MINIMUM_QUESTIONS)
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                handoff = stock_handoff(1)
                gate = gate_for(handoff)
                fact = observation()
                gate["allowed_evidence"].append(fact)
                for key in ("input_evidence_ids", "allowed_evidence_ids"):
                    gate[key] = sorted([*gate[key], fact["evidence_id"]])
                gate["bundle_hash"] = canonical_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
                for name, value in (("handoff", handoff), ("gate", gate)):
                    (root / (name + ".json")).write_text(json.dumps(value))
                run = root / "run"
                prepare_multidimensional_stage_run(
                    ROOT, handoff_path=root / "handoff.json", gate_path=root / "gate.json",
                    run_dir=run, run_id="macro-bound", model="gpt-5.6-terra", task_bound_tools=enabled,
                )
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
                    "instruction": packet["instruction"], "questions": packet["minimum_questions"],
                }))
                if enabled:
                    field = packet["output_schema"]["properties"]["source_literal_selections"]["items"]["properties"]["field"]
                    self.assertEqual(field["enum"], ["moomoo_macro_observation"])
                    short = next(k for k, v in packet["reference_map"]["evidence"].items() if v == fact["evidence_id"])
                    tool = StatelessFixtureTools(default_run_dir=run)
                    tool.query(**tool.bind_task_tool_arguments("query", {"task_name": task["task_name"], "evidence_ids": [short]}))
                    _write_event(run / "events/mcp/events.jsonl", tool.events[-1])
                    draft = {"claims": [{"claim_id": "activity", "statement": "供应商观测{{sf.retail}}。", "evidence_refs": [short]}],
                             "source_literal_selections": [{"claim_id": "activity", "placeholder": "{{sf.retail}}",
                                                            "evidence_ref": short, "field": "moomoo_macro_observation"}]}
                    result = _bind_source_literal_selections(draft, task=task, run_dir=run, reference_map=packet["reference_map"])
                    self.assertIn("actual(原值)=0.012400000000000001", result["claims"][0]["statement"])
                    self.assertNotIn("source_literal_selections", result)
                self.assertEqual(MINIMUM_QUESTIONS, baseline)

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
