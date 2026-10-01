"""正向/反证前置共用当前交付协议；真实 Hook 接缝，零 LLM。"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.runtime import multidimensional_stage as stage
from product.runtime.calculation_handoff import VERSION, require_current_selection_transport
from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.hashing import canonical_hash, file_hash, legacy_envelope_hash
from product.runtime.multidimensional_references import VERSION as REFERENCE_VERSION
from tests import test_multidimensional_stage as fixtures


class MultidimensionalTransportAdmissionTests(unittest.TestCase):
    helper = fixtures.MultidimensionalStageTests()

    def prepare(self, root: Path, *, counter: bool):
        handoff = fixtures.stock_handoff(1)
        (root / "handoff.json").write_text(json.dumps(handoff))
        (root / "gate.json").write_text(json.dumps(fixtures.gate_for(handoff)))
        run = root / "run"
        stage.prepare_multidimensional_stage_run(
            fixtures.ROOT, handoff_path=root / "handoff.json", gate_path=root / "gate.json",
            run_dir=run, run_id="counter-transport" if counter else "forward-transport",
            model="gpt-5.6-terra", stage=("INDEPENDENT_COUNTER_THESIS_RESEARCH" if counter
                                         else "MULTI_DIMENSIONAL_HOLDING_RESEARCH"),
        )
        return run, json.loads((run / "research/dispatch-index.json").read_text())

    @staticmethod
    def native_gap(task):
        # 测试作者明确编写选择草稿；没有从生产代码自动修复旧模型输出。
        return {
            "status": "INSUFFICIENT_EVIDENCE", "sufficiency": "INSUFFICIENT",
            "evaluation_status": "NOT_EVALUATED", "summary": "合成资料缺口，未开展真实研究。",
            "claims": [], "assumptions": [], "calculation_selections": [],
            "document_selections": [], "research_relationships": [],
            "limitations": ["仅验证协议接缝，不代表研究质量。"], "observation_conditions": [],
            "data_gaps": [{"gap_id": "gap:" + task["task_id"], "reason_code": "UNKNOWN",
                           "description": "合成资料缺口。", "impact": "不形成研究主张。"}],
        }

    def test_both_stage_producers_deliver_native_guides_and_all_eight_hook_consumers(self):
        for counter in (False, True):
            with self.subTest(counter=counter), tempfile.TemporaryDirectory() as directory:
                run, index = self.prepare(Path(directory), counter=counter)
                self.assertEqual(len(index["tasks"]), 8)
                self.assertNotIn("runtime_skeptic", {t["agent"] for t in index["tasks"]})
                inventory = []
                pending = list(index["tasks"])
                completed = set()
                while pending:
                    ready = [t for t in pending if set(t["depends_on"]) <= completed]
                    self.assertTrue(ready, "冻结任务图不可调度")
                    task = ready[0]
                    packet = stage.build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
                    invocation = json.loads((run / task["invocation_path"]).read_text())
                    require_current_selection_transport(packet, invocation, indexed_task=task)
                    self.assertEqual(packet["reference_transport_version"], REFERENCE_VERSION)
                    for serialize in (stage.serialize_multidimensional_initial_context,
                                      stage.serialize_multidimensional_model_context):
                        context = json.loads(serialize(packet))
                        guide = context["output_format_guide"]
                        self.assertIn("calculation_selections", guide["required"])
                        self.assertIn("document_selections", guide["required"])
                        for key in ("run_id", "invocation_id", "agent", "calculations", "artifact_refs", "documents"):
                            self.assertNotIn(key, guide["properties"])
                        self.assertNotIn("calculation_refs", guide["$defs"]["claim"]["properties"])
                        self.assertEqual(context["calculation_selection_contract"]["version"], VERSION)
                    env = self.helper.targeted_environment(run, task)
                    parent, child = "counter-parent" if counter else "forward-parent", "child:" + task["task_id"]
                    dispatched, _ = handle_hook_event(self.helper.dispatch_payload(task, parent=parent), environ=env)
                    self.assertEqual(dispatched["decision"], "ALLOW", dispatched)
                    started, _ = handle_hook_event(self.helper.start_payload(task, parent=parent, child=child), environ=env)
                    self.assertEqual(started["context_binding"]["status"], "DELIVERED", started)
                    draft = self.native_gap(task)
                    if task["capability"] == "FUNDAMENTAL_EVENT":
                        draft["claims"] = [{"claim_id": "fixture-baseline", "question": "冻结资料的范围是什么？",
                            "statement": "冻结资料支持本次合成接缝基线，不作投资结论。", "kind": "FACT",
                            "evidence_refs": [next(iter(packet["reference_map"]["evidence"]))],
                            "research_claim_refs": [], "document_refs": [], "assumption_ids": []}]
                    original = copy.deepcopy(draft)
                    stopped, _ = handle_hook_event(self.helper.stop_payload(task, draft, parent=parent, child=child), environ=env)
                    self.assertEqual(stopped["output_capture"]["status"], "SAVED", stopped)
                    report = json.loads((run / stopped["output_capture"]["path"]).read_text())
                    self.assertEqual(report["summary"], draft["summary"])
                    self.assertEqual(report["data_gaps"], draft["data_gaps"])
                    self.assertEqual(report["calculations"], [])
                    self.assertEqual(report["report_hash"], legacy_envelope_hash(report, hash_field="report_hash"))
                    self.assertEqual(draft, original)
                    inventory.append(stopped["output_capture"]["path"])
                    completed.add(task["task_id"])
                    pending.remove(task)
                self.assertEqual(len(set(inventory)), 8)

    def test_missing_or_drifting_transport_is_rejected_before_process_and_launch_state(self):
        for counter in (False, True):
            for field in ("packet", "task", "invocation"):
                with self.subTest(counter=counter, field=field), tempfile.TemporaryDirectory() as directory:
                    run, index = self.prepare(Path(directory), counter=counter)
                    task = next(t for t in index["tasks"] if t["capability"] == "OPTIONS_FLOW")
                    packet_path = run / task["packet_path"]
                    packet = json.loads(packet_path.read_text())
                    if field == "packet":
                        packet.pop("reference_transport_version")
                    elif field == "task":
                        packet["task"].pop("calculation_selection_version")
                        task.pop("calculation_selection_version")
                    else:
                        path = run / task["invocation_path"]
                        invocation = json.loads(path.read_text())
                        invocation.pop("calculation_selection_version")
                        invocation["manifest_hash"] = legacy_envelope_hash(invocation, hash_field="manifest_hash")
                        path.write_text(json.dumps(invocation))
                    packet_path.write_text(json.dumps(packet))
                    task["packet_hash"] = canonical_hash(packet)
                    index["index_hash"] = legacy_envelope_hash(index, hash_field="index_hash")
                    (run / "research/dispatch-index.json").write_text(json.dumps(index))
                    manifest_path = run / "run_manifest.json"
                    manifest = json.loads(manifest_path.read_text())
                    manifest["dispatch_index_hash"] = index["index_hash"]
                    manifest["manifest_hash"] = legacy_envelope_hash(manifest, hash_field="manifest_hash")
                    manifest_path.write_text(json.dumps(manifest))
                    before = {str(p.relative_to(run)): file_hash(p) for p in run.rglob("*") if p.is_file()}
                    with patch.object(stage.subprocess, "run") as process, self.assertRaisesRegex(
                        ValueError, "LEGACY_SELECTION_TRANSPORT_EXECUTION_RETIRED",
                    ):
                        stage.launch_multidimensional_stage(
                            fixtures.ROOT, run_dir=run, task_name=task["task_name"], initial_task=not counter,
                        )
                    process.assert_not_called()
                    self.assertFalse((run / "invocation").exists())
                    self.assertEqual(before, {str(p.relative_to(run)): file_hash(p)
                                              for p in run.rglob("*") if p.is_file()})

    def test_resigned_foreign_invocation_and_corrupt_manifest_are_not_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            run, index = self.prepare(Path(directory), counter=True)
            task = index["tasks"][0]
            packet = stage.build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            invocation = json.loads((run / task["invocation_path"]).read_text())
            for field in ("run_id", "task_id", "invocation_id", "manifest_hash"):
                wrong = {**invocation, field: "foreign"}
                if field != "manifest_hash":
                    wrong["manifest_hash"] = legacy_envelope_hash(wrong, hash_field="manifest_hash")
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, "SELECTION_TRANSPORT_BINDING_INVALID"):
                    require_current_selection_transport(packet, wrong, indexed_task=task)

    def test_counter_actual_stdio_calculation_is_selected_without_copying_receipt_fields(self):
        from tests.test_calculation_handoff import CalculationHandoffTests
        from product.runtime.calculation_handoff import receipt_calculation
        helper = CalculationHandoffTests()
        with tempfile.TemporaryDirectory() as directory:
            run, index = self.prepare(Path(directory), counter=True)
            task = next(t for t in index["tasks"] if t["capability"] == "FUNDAMENTAL_EVENT")
            packet = stage.build_multidimensional_dispatch_packet(fixtures.ROOT, run, task["task_name"])
            foreign_root = Path(directory) / "foreign"
            foreign_root.mkdir()
            foreign_run, foreign_index = self.prepare(foreign_root, counter=False)
            other = next(t for t in foreign_index["tasks"] if t["capability"] == "FUNDAMENTAL_EVENT")
            other_packet = stage.build_multidimensional_dispatch_packet(fixtures.ROOT, foreign_run, other["task_name"])
            denied = helper.call(run, task, "query", evidence_ids=[next(iter(other_packet["reference_map"]["evidence"]))])
            self.assertIn("error", denied)
            self.assertIn("MULTIDIMENSIONAL_REFERENCE_UNKNOWN", denied["error"]["message"])
            calculation = helper.successful_ratio(run, task, packet)
            draft = helper.draft(task, calculation["calculation_ref"], calculation["evidence_ids"])
            original = copy.deepcopy(draft)
            env = self.helper.targeted_environment(run, task)
            handle_hook_event(self.helper.dispatch_payload(task, parent="counter-calc"), environ=env)
            handle_hook_event(self.helper.start_payload(task, parent="counter-calc", child="counter-child"), environ=env)
            stopped, _ = handle_hook_event(self.helper.stop_payload(
                task, draft, parent="counter-calc", child="counter-child"), environ=env)
            self.assertEqual(stopped["output_capture"]["status"], "SAVED", stopped)
            report = json.loads((run / stopped["output_capture"]["path"]).read_text())
            receipt = json.loads((run / task["calculation_ledger_ref"]).read_text())
            self.assertEqual(report["calculations"], [receipt_calculation(receipt, task["calculation_ledger_ref"])])
            self.assertEqual(report["claims"][0]["statement"], draft["claims"][0]["statement"])
            self.assertEqual(draft, original)

    def test_direct_hook_cannot_write_a_retired_transport_even_without_launcher(self):
        for counter in (False, True):
            with self.subTest(counter=counter), tempfile.TemporaryDirectory() as directory:
                run, index = self.prepare(Path(directory), counter=counter)
                task = next(t for t in index["tasks"] if t["capability"] == "OPTIONS_FLOW")
                env = self.helper.targeted_environment(run, task)
                dispatched, _ = handle_hook_event(self.helper.dispatch_payload(task, parent="retired"), environ=env)
                self.assertEqual(dispatched["decision"], "ALLOW", dispatched)
                started, _ = handle_hook_event(self.helper.start_payload(task, parent="retired", child="old-child"), environ=env)
                self.assertEqual(started["context_binding"]["status"], "DELIVERED", started)
                path = run / task["packet_path"]
                packet = json.loads(path.read_text())
                packet["task"].pop("calculation_selection_version")
                task.pop("calculation_selection_version")
                path.write_text(json.dumps(packet))
                task["packet_hash"] = canonical_hash(packet)
                index["index_hash"] = legacy_envelope_hash(index, hash_field="index_hash")
                (run / "research/dispatch-index.json").write_text(json.dumps(index))
                stopped, _ = handle_hook_event(self.helper.stop_payload(
                    task, self.helper.dimension_draft(task), parent="retired", child="old-child"), environ=env)
                self.assertEqual(stopped["output_capture"]["status"], "FAILED", stopped)
                self.assertEqual(stopped["output_capture"]["failure_code"],
                                 "MULTIDIMENSIONAL_LEGACY_SELECTION_TRANSPORT_EXECUTION_RETIRED")
                self.assertFalse(list((run / "research/reports").glob("*/dimension-report.json")))

    def test_retired_transport_cannot_be_delivered_at_subagent_start(self):
        with tempfile.TemporaryDirectory() as directory:
            run, index = self.prepare(Path(directory), counter=True)
            task = next(t for t in index["tasks"] if t["capability"] == "OPTIONS_FLOW")
            env = self.helper.targeted_environment(run, task)
            dispatched, _ = handle_hook_event(self.helper.dispatch_payload(task, parent="before-start"), environ=env)
            self.assertEqual(dispatched["decision"], "ALLOW", dispatched)
            path = run / task["invocation_path"]
            invocation = json.loads(path.read_text())
            invocation.pop("calculation_selection_version")
            invocation["manifest_hash"] = legacy_envelope_hash(invocation, hash_field="manifest_hash")
            path.write_text(json.dumps(invocation))
            started, _ = handle_hook_event(self.helper.start_payload(
                task, parent="before-start", child="no-delivery"), environ=env)
            self.assertEqual(started["context_binding"]["status"], "FAILED", started)
            self.assertEqual(started["context_binding"]["failure_code"],
                             "MULTIDIMENSIONAL_LEGACY_SELECTION_TRANSPORT_EXECUTION_RETIRED")


if __name__ == "__main__":
    unittest.main()
