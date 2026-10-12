from __future__ import annotations

import copy
import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.deterministic.market_analysis import calculate_market_breadth
from product.runtime.hashing import canonical_hash
from product.runtime.monetary import MONETARY_SCALE_FACTORS, convert_monetary_value
from product.runtime.multidimensional_stage import (
    _prepare_macro_market_artifacts, validate_breadth_calculation_references,
    serialize_multidimensional_model_context, build_multidimensional_dispatch_packet,
    prepare_multidimensional_stage_run,
    finalize_multidimensional_stage_run, check_multidimensional_bundle_consumable,
)
from product.runtime.fixture_mcp import StatelessFixtureTools, serve_stdio
from product.runtime.calculation_handoff import build_calculation_catalog
from tests import test_multidimensional_stage as fixtures


def breadth_fact():
    # Captured provider layout; counts are a synthetic controlled sample.
    rows = [("NEGATIVE_INFINITY", 0, -7), ("NORMAL_RANGE", -7, -5),
            ("NORMAL_RANGE", -5, -3), ("NORMAL_RANGE", -3, 0),
            ("NORMAL_RANGE", 0, 0), ("NORMAL_RANGE", 0, 3),
            ("NORMAL_RANGE", 3, 5), ("NORMAL_RANGE", 5, 7),
            ("POSITIVE_INFINITY", 7, 0)]
    return {"evidence_id": "breadth-test", "security_id": "US:MARKET",
            "semantic_field": "moomoo_us_rise_fall_distribution", "source_id": "test-provider",
            "as_of": "2026-01-01T00:00:00Z", "retrieved_at": "2026-01-01T00:00:00Z",
            "value": {"plate": "US.USAALL", "ranges": [
                dict(type=t, left_border=l, right_border=r, stock_count=i)
                for i, (t, l, r) in enumerate(rows, 1)]}}


class BreadthTests(unittest.TestCase):
    def test_frozen_gate_to_business_report_and_historical_bundle_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            helper = fixtures.MultidimensionalStageTests()
            handoff, gate = helper.mrvl_daily_inputs(include_spy=False)
            fact = breadth_fact()
            fact.update(source_family="moomoo_sg", source_type="SECONDARY_VENDOR", dataset="market_breadth")
            gate["allowed_evidence"].append(fact)
            gate["allowed_evidence_ids"] = sorted(f["evidence_id"] for f in gate["allowed_evidence"])
            gate["input_evidence_ids"] = list(gate["allowed_evidence_ids"])
            gate["bundle_hash"] = canonical_hash({k: v for k, v in gate.items() if k != "bundle_hash"})
            (root / "handoff.json").write_text(json.dumps(handoff))
            (root / "gate.json").write_text(json.dumps(gate))
            run = root / "run"
            prepare_multidimensional_stage_run(fixtures.ROOT, handoff_path=root / "handoff.json",
                gate_path=root / "gate.json", run_dir=run, run_id="breadth-integration", model="gpt-5.6-terra")
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(t for t in index["tasks"] if t["capability"] == "MARKET_STATE")
            self.assertIn(fact["evidence_id"], task["allowed_evidence_ids"])
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            analysis = packet["prepared_analysis"]
            self.assertIsNone(analysis["calculation"])
            context = json.loads(serialize_multidimensional_model_context(packet))
            calculation = context["prepared_analysis"]["breadth_report_calculation"]
            draft = helper.dimension_draft(task)
            draft.update(status="LOW_CONFIDENCE", sufficiency="PARTIAL", evaluation_status="PASS")
            selected_ref = next(ref for ref, entry in build_calculation_catalog(run, packet).items()
                                if entry["calculation"]["calculation_id"] == calculation["calculation_id"])
            draft["calculation_selections"] = [{"calculation_ref": selected_ref, "claim_ids": ["breadth"]}]
            draft["claims"] = [{"claim_id": "breadth", "question": packet["minimum_questions"][0],
                "statement": "合成分桶上涨30、下跌10、持平5，仅供应商覆盖。", "kind": "FACT",
                "evidence_refs": [fact["evidence_id"]], "research_claim_refs": [], "document_refs": [],
                "assumption_ids": []}]
            wrong = copy.deepcopy(draft)
            wrong["calculations"] = [{**calculation, "unit": "stocks"}]
            with self.assertRaisesRegex(ValueError, "SCHEMA_EXTRA_PROPERTY"):
                helper.read_dimension_draft(run, task, wrong)
            for field, value in [("value", "30"), ("method", "sum"), ("unit", "stocks"),
                                 ("input_evidence_refs", []), ("calculation_id", "wrong")]:
                # 正式历史计算独立重验，不恢复旧Hook的辅助修订调度。
                bad = {"calculations": [copy.deepcopy(packet["prepared_analysis"]["breadth_report_calculation"])],
                       "artifact_refs": [calculation["artifact_ref"]]}
                bad["calculations"][0][field] = value
                original = copy.deepcopy(bad)
                failure = "MARKET_BREADTH_REFERENCE_INVALID" if field in {"input_evidence_refs", "calculation_id"} else "MARKET_BREADTH_VALUE_INVALID"
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, failure):
                    validate_breadth_calculation_references(run, bad)
                self.assertEqual(bad, original)
            # 下面只构造显式历史读取向量；不是实际宿主派发/执行证明。
            events = []
            for other in index["tasks"]:
                gap_draft = draft if other == task else helper.dimension_draft(other)
                if other["capability"] == "MACRO_CONTEXT":
                    wrong = copy.deepcopy(gap_draft)
                    wrong["artifact_refs"] = [calculation["artifact_ref"]]
                    with self.assertRaisesRegex(ValueError, r"SCHEMA_EXTRA_PROPERTY:\$:artifact_refs"):
                        helper.read_dimension_draft(run, other, wrong)
                saved, output = helper.save_dimension_fixture(run, other, gap_draft)
                if other == task:
                    self.assertTrue(Path(output["markdown"]).exists())
                    validate_breadth_calculation_references(run, saved)
                events.append({"hook_event_name": "SubagentStop", "output_capture": {
                    "status": "SAVED", "task_id": other["task_id"],
                    "path": str(Path(output["json"]).relative_to(run)),
                }})
            (run / "invocation").mkdir(exist_ok=True)
            (run / "invocation/subagent-events.jsonl").write_text(
                "\n".join(json.dumps(event) for event in events) + "\n")
            (run / "invocation/subagent-dispatches.jsonl").write_text(
                "\n".join(json.dumps({"task_name": item["task_name"], "decision": "ALLOW"})
                          for item in index["tasks"]) + "\n")
            finalize_multidimensional_stage_run(fixtures.ROOT, run)
            self.assertTrue((run / "research/holding-research-bundle.md").exists())
            check_multidimensional_bundle_consumable(fixtures.ROOT, run)
            artifact = json.loads((run / calculation["artifact_ref"]).read_text())
            artifact["counts"]["rise"] = 999
            (run / calculation["artifact_ref"]).write_text(json.dumps(artifact))
            with self.assertRaisesRegex(ValueError, "ARTIFACT_MISMATCH"):
                check_multidimensional_bundle_consumable(fixtures.ROOT, run)

    def test_snapshot_focus_uses_calculation_input_even_when_id_order_differs(self):
        for invalid in (False, True):
            with tempfile.TemporaryDirectory() as d:
                root = Path(d)
                helper = fixtures.MultidimensionalStageTests()
                handoff, gate = helper.mrvl_daily_inputs(include_spy=False)
                older, newer, future = [breadth_fact() for _ in range(3)]
                older.update(evidence_id="a-older", as_of="2025-12-31T00:00:00Z")
                newer.update(evidence_id="z-newer")
                future.update(evidence_id="future", as_of="2099-01-01T00:00:00Z", retrieved_at="2099-01-01T00:00:00Z")
                if invalid:
                    newer["value"]["ranges"].pop()
                # Gate admits only PIT-safe records; helper selection separately rejects future.
                from product.runtime.multidimensional_stage import _latest_market_breadth
                self.assertEqual(_latest_market_breadth([future, newer, older], gate["decision_cutoff"])["evidence_id"], "z-newer")
                for fact in (newer, older):
                    fact.update(source_family="moomoo_sg", source_type="SECONDARY_VENDOR", dataset="market_breadth")
                gate["allowed_evidence"].extend([newer, older])
                gate["allowed_evidence_ids"] = sorted(f["evidence_id"] for f in gate["allowed_evidence"])
                gate["input_evidence_ids"] = list(gate["allowed_evidence_ids"])
                gate["bundle_hash"] = canonical_hash({k:v for k,v in gate.items() if k != "bundle_hash"})
                (root / "handoff.json").write_text(json.dumps(handoff))
                (root / "gate.json").write_text(json.dumps(gate))
                run = root / "run"
                prepare_multidimensional_stage_run(fixtures.ROOT, handoff_path=root / "handoff.json", gate_path=root / "gate.json", run_dir=run, run_id="snapshot", model="gpt-5.6-terra")
                task = next(t for t in json.loads((run / "research/dispatch-index.json").read_text())["tasks"] if t["capability"] == "MARKET_STATE")
                self.assertEqual(task["source_focus"][0]["evidence_id"], "z-newer")
                self.assertIn("z-newer", task["allowed_evidence_ids"])
                packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
                breadth = packet["prepared_analysis"]["breadth_calculation"]
                if invalid:
                    self.assertIsNone(breadth)
                else:
                    self.assertEqual(breadth["evidence_fact_ids"], ["z-newer"])

    def test_invalid_breadth_fields_remain_rejected_without_auto_repair(self):
        self._invalid_breadth_draft()

    def test_breadth_field_error_does_not_authorize_unknown_document(self):
        self._invalid_breadth_draft(unknown_document=True)

    def _invalid_breadth_draft(self, unknown_document=False):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            helper = fixtures.MultidimensionalStageTests()
            handoff, gate = helper.mrvl_daily_inputs(include_spy=False)
            fact = breadth_fact()
            fact.update(source_family="moomoo_sg", source_type="SECONDARY_VENDOR", dataset="market_breadth")
            gate["allowed_evidence"].append(fact)
            gate["allowed_evidence_ids"] = sorted(f["evidence_id"] for f in gate["allowed_evidence"])
            gate["input_evidence_ids"] = list(gate["allowed_evidence_ids"])
            gate["bundle_hash"] = canonical_hash({k:v for k,v in gate.items() if k != "bundle_hash"})
            (root / "handoff.json").write_text(json.dumps(handoff))
            (root / "gate.json").write_text(json.dumps(gate))
            run = root / "run"
            prepare_multidimensional_stage_run(fixtures.ROOT, handoff_path=root / "handoff.json", gate_path=root / "gate.json", run_dir=run, run_id="exhaustion", model="gpt-5.6-terra")
            task = next(t for t in json.loads((run / "research/dispatch-index.json").read_text())["tasks"] if t["capability"] == "MARKET_STATE")
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            calc = copy.deepcopy(packet["prepared_analysis"]["breadth_report_calculation"])
            calc["unit"] = "stocks"
            formal = {"calculations": [calc], "artifact_refs": [calc["artifact_ref"]]}
            with self.assertRaisesRegex(ValueError, "MARKET_BREADTH_VALUE_INVALID"):
                validate_breadth_calculation_references(run, formal)
            native = helper.dimension_draft(task)
            if unknown_document:
                native["document_selections"] = ["d.not-authorized.1"]
                failure = "SCHEMA_ENUM_INVALID"
            else:
                native["calculations"] = [calc]
                failure = "SCHEMA_EXTRA_PROPERTY"
            original = copy.deepcopy(native)
            for _ in range(2):
                with self.assertRaisesRegex(ValueError, failure):
                    helper.read_dimension_draft(run, task, native)
                self.assertEqual(native, original)
            outside = {"calculations": [], "artifact_refs": ["../outside/market-breadth-calculation.json"]}
            with self.assertRaisesRegex(ValueError, "MARKET_BREADTH_ARTIFACT_INVALID"):
                validate_breadth_calculation_references(run, outside)
            self.assertFalse((run / "research/reports").exists())
            self.assertFalse((run / "invocation/subagent-events.jsonl").exists())

    def test_sum_and_order_and_input_unchanged(self):
        fact = breadth_fact()
        original = copy.deepcopy(fact)
        result = calculate_market_breadth(fact)
        self.assertEqual(result["counts"], {"fall": 10, "flat": 5, "rise": 30})
        self.assertEqual(fact, original)
        fact["value"]["ranges"].reverse()
        self.assertEqual(calculate_market_breadth(fact)["counts"], result["counts"])
        self.assertEqual(result["artifact_hash"], canonical_hash({k: v for k, v in result.items() if k != "artifact_hash"}))

    def test_invalid_partitions_do_not_create_totals(self):
        variants = []
        fact = breadth_fact()
        fact["value"]["ranges"].pop()
        variants.append(fact)
        fact = breadth_fact()
        fact["value"]["ranges"][0] = fact["value"]["ranges"][1]
        variants.append(fact)
        for field, value in [("type", "UNKNOWN"), ("left_border", -1),
                             ("stock_count", -1), ("stock_count", 1.5),
                             ("stock_count", True), ("stock_count", float("nan")),
                             ("stock_count", "2")]:
            fact = breadth_fact()
            fact["value"]["ranges"][5][field] = value
            variants.append(fact)
        for fact in variants:
            with self.subTest(fact=fact), self.assertRaises(ValueError):
                calculate_market_breadth(fact)

    def test_independent_availability_and_single_snapshot(self):
        row = {"date": "2026-01-01", "close": 10, "adjusted_close": 10, "volume": 1, "evidence_ids": ["daily"]}
        for daily in (False, True):
            for breadth in (False, True):
                with tempfile.TemporaryDirectory() as d, patch(
                    "product.runtime.multidimensional_stage._technical_rows", return_value=[row] if daily else [],
                ):
                    result = _prepare_macro_market_artifacts(Path(d), task_id="t", benchmark_id="SPY",
                        evidence=[breadth_fact()] if breadth else [], as_of="2026-01-02T00:00:00Z")
                    self.assertEqual(result["calculation"] is not None, daily)
                    self.assertEqual(result["breadth_calculation"] is not None, breadth)
        with tempfile.TemporaryDirectory() as d:
            future = breadth_fact()
            future["as_of"] = "2027-01-01T00:00:00Z"
            earlier = breadth_fact()
            earlier.update(evidence_id="older", as_of="2025-12-31T00:00:00Z", retrieved_at="2025-12-31T00:00:00Z")
            earlier["value"]["ranges"][5]["stock_count"] = 999
            result = _prepare_macro_market_artifacts(Path(d), task_id="t", benchmark_id="SPY",
                evidence=[earlier, breadth_fact(), future], as_of="2026-01-02T00:00:00Z")
            self.assertEqual(result["breadth_calculation"]["counts"]["rise"], 30)

    def test_mcp_invalid_unit_reports_allowed_values_after_authorization(self):
        with tempfile.TemporaryDirectory() as d:
            helper = fixtures.MultidimensionalStageTests()
            run, _ = helper.prepare(Path(d), count=1)
            tasks = json.loads((run / "research/dispatch-index.json").read_text())["tasks"]
            calls = []
            for capability in ("FUNDAMENTAL_EVENT", "MARKET_STATE"):
                task = next(t for t in tasks if t["capability"] == capability)
                calls.append(json.dumps({"jsonrpc": "2.0", "id": capability, "method": "tools/call",
                    "params": {"name": "calculate", "arguments": {
                        "run_id": task["run_id"], "agent": task["agent"], "invocation_id": task["invocation_id"],
                        "calculation_id": "invalid-scale", "operation": "monetary_scale",
                        "evidence_ids": task["allowed_evidence_ids"][:1], "target_scale": "hundred_million"}}}))
            output = io.StringIO()
            with patch("sys.stdin", io.StringIO("\n".join(calls))), patch("sys.stdout", output):
                serve_stdio(default_run_dir=run, tools_override=StatelessFixtureTools(default_run_dir=run))
            self.assertIn("allowed=one,thousand,million,billion", output.getvalue())
            self.assertIn("TOOL_NOT_AUTHORIZED", output.getvalue())

    def test_recompute_rejects_tampering_and_wrong_references(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            result = _prepare_macro_market_artifacts(root, task_id="t", benchmark_id="SPY",
                evidence=[breadth_fact()], as_of="2026-01-02T00:00:00Z")
            (root / "evidence").mkdir()
            (root / "evidence/gate.json").write_text(json.dumps({"allowed_evidence": [breadth_fact()],
                "decision_cutoff": "2026-01-02T00:00:00Z"}))
            ref = result["breadth_calculation_ref"]
            report = {"artifact_refs": [ref], "calculations": [result["breadth_report_calculation"]]}
            validate_breadth_calculation_references(root, report)
            wrong_value = copy.deepcopy(report)
            wrong_value["calculations"][0]["value"] = '{"rise":999,"fall":10,"flat":5}'
            with self.assertRaisesRegex(ValueError, "VALUE_INVALID"):
                validate_breadth_calculation_references(root, wrong_value)
            for field, value in (("value", "bad json"), ("unit", "USD"), ("method", "guess")):
                wrong = copy.deepcopy(report)
                wrong["calculations"][0][field] = value
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "VALUE_INVALID"):
                    validate_breadth_calculation_references(root, wrong)
            gate_path = root / "evidence/gate.json"
            original_gate = gate_path.read_text()
            future_gate = json.loads(original_gate)
            future_gate["allowed_evidence"][0]["retrieved_at"] = "2027-01-01T00:00:00Z"
            gate_path.write_text(json.dumps(future_gate))
            with self.assertRaisesRegex(ValueError, "PIT_INVALID"):
                validate_breadth_calculation_references(root, report)
            gate_path.write_text(original_gate)
            bad = copy.deepcopy(report)
            bad["calculations"][0]["input_evidence_refs"] = ["other"]
            with self.assertRaisesRegex(ValueError, "REFERENCE_INVALID"):
                validate_breadth_calculation_references(root, bad)
            artifact = json.loads((root / ref).read_text())
            artifact["counts"]["rise"] = 999
            artifact["artifact_hash"] = canonical_hash({k: v for k, v in artifact.items() if k != "artifact_hash"})
            (root / ref).write_text(json.dumps(artifact))
            with self.assertRaisesRegex(ValueError, "ARTIFACT_MISMATCH"):
                validate_breadth_calculation_references(root, report)

    def test_industry_questions_delivered(self):
        with tempfile.TemporaryDirectory() as d:
            helper = fixtures.MultidimensionalStageTests()
            run, _ = helper.prepare(Path(d), count=1)
            index = json.loads((run / "research/dispatch-index.json").read_text())
            task = next(t for t in index["tasks"] if t["capability"] == "INDUSTRY_COMPARISON")
            packet = build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            context = json.loads(serialize_multidimensional_model_context(packet))
            questions = " ".join(context["minimum_questions"])
            self.assertIn("至少一家", questions)
            self.assertIn("具体产品", questions)
            self.assertIn("同口径", questions)
            self.assertIn("claims 必须为空", packet["instruction"])

    def test_monetary_allowed_values_and_bounded_error(self):
        for scale, factor in MONETARY_SCALE_FACTORS.items():
            self.assertEqual(convert_monetary_value(value=str(factor), source_scale="one", target_scale=scale), "1")
        with self.assertRaises(ValueError) as error:
            convert_monetary_value(value=1, source_scale="one", target_scale="secret" * 1000)
        self.assertNotIn("secret", str(error.exception))
        self.assertIn("allowed=" + ",".join(MONETARY_SCALE_FACTORS), str(error.exception))
