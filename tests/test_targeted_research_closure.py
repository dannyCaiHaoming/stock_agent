"""既有宿主入口的最小依赖闭包；模拟子进程，不启动模型或真实 Gate。"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime import multidimensional_stage as stage
from tests import test_multidimensional_stage as fixtures

ROOT = fixtures.ROOT


class TargetedResearchClosureTests(unittest.TestCase):
    def test_each_declared_dimension_uses_only_its_necessary_closure(self):
        helper = fixtures.MultidimensionalStageTests()
        for capability in stage.RESEARCH_CAPABILITIES:
            with self.subTest(capability=capability), tempfile.TemporaryDirectory() as directory:
                run, _ = helper.prepare(Path(directory), count=1)
                index = json.loads((run / "research/dispatch-index.json").read_text())
                target = next(task for task in index["tasks"] if task["capability"] == capability)
                closure = stage._target_task_closure(index, target["task_name"])
                selected = [task["task_name"] for task in closure]
                dispatched = []

                def fake_process(command, *, input, cwd, env, **kwargs):
                    self.assertEqual(Path(cwd), ROOT / "product")
                    self.assertEqual(json.loads(env["STOCK_AGENT_RESEARCH_TASK_NAMES"]), selected)
                    self.assertEqual(env["STOCK_AGENT_MULTIDIMENSIONAL_INITIAL_CONTEXT"], "1")
                    for task in index["tasks"]:
                        if task["task_name"] not in selected:
                            self.assertNotIn(task["task_name"], input)
                    for offset, task in enumerate(closure):
                        parent, child = "closure-parent", f"closure-child-{offset}"
                        record, _ = handle_hook_event(helper.dispatch_payload(task, parent=parent), environ=env)
                        self.assertEqual(record["decision"], "ALLOW", record)
                        dispatched.append(task["task_name"])
                        started, response = handle_hook_event(helper.start_payload(task, parent=parent, child=child), environ=env)
                        self.assertEqual(started["context_binding"]["status"], "DELIVERED", started)
                        context = json.loads(response["hookSpecificOutput"]["additionalContext"])
                        self.assertEqual(context["identity"]["task_name"], task["task_name"])
                        self.assertEqual(context["task"]["capability"], task["capability"])
                        stopped, _ = handle_hook_event(helper.stop_payload(task, helper.dimension_draft(task), parent=parent, child=child), environ=env)
                        self.assertEqual(stopped["output_capture"]["status"], "SAVED", stopped)
                    (Path(env["TMPDIR"]) / "final-message.json").write_text(json.dumps({
                        "stage": "MULTI_DIMENSIONAL_HOLDING_RESEARCH", "run_id": index["run_id"],
                        "dispatched": len(closure), "completed": len(closure),
                    }))
                    return subprocess.CompletedProcess(command, 0, "", "")

                with patch.object(stage.subprocess, "run", side_effect=fake_process) as launcher:
                    result, code = stage.launch_multidimensional_stage(ROOT, run_dir=run, task_name=target["task_name"], initial_task=True)
                self.assertEqual(launcher.call_count, 1)
                self.assertEqual(code, 0, result)
                self.assertEqual(dispatched, selected)
                self.assertEqual(result["completed"], len(closure))
                self.assertEqual(len(closure), 2 if capability == "RESEARCH_REPORT" else 1)
                self.assertFalse(result["complete_holding_research_bundle"])
                proof = json.loads((run / "research/task-execution-proof.json").read_text())
                self.assertEqual(proof["task_names"], selected)
                self.assertEqual(len(proof["report_inventory"]), len(closure))
                self.assertEqual(set(result["not_run_task_names"]), {task["task_name"] for task in index["tasks"]} - set(selected))
                self.assertFalse((run / "research/holding-research-bundle.json").exists())
                with patch.object(stage.subprocess, "run") as second_launcher, self.assertRaisesRegex(
                    stage.MultidimensionalStageError, "INITIAL_TASK_SCOPE_OR_STATE_INVALID"
                ):
                    stage.launch_multidimensional_stage(ROOT, run_dir=run, task_name=target["task_name"], initial_task=True)
                second_launcher.assert_not_called()

    def test_invalid_dependency_graph_is_rejected_not_silently_shrunk(self):
        source = {"task_id": "source", "task_name": "source-task", "depends_on": []}
        target = {"task_id": "target", "task_name": "target-task", "depends_on": ["source"]}
        cases = [
            ([source, {**target, "depends_on": ["missing"]}], "DEPENDENCY_UNKNOWN"),
            ([{**source, "depends_on": ["target"]}, target], "DEPENDENCY_CYCLE"),
            ([source, {**target, "depends_on": [None]}], "DEPENDENCY_INVALID"),
            ([source, {**target, "depends_on": ["source", "source"]}], "DEPENDENCY_INVALID"),
            ([source, target, {**source, "task_name": "duplicate-id"}], "INDEX_AMBIGUOUS"),
            ([source, target, {**source, "task_id": "duplicate-name"}], "INDEX_AMBIGUOUS"),
        ]
        for tasks, code in cases:
            with self.subTest(code=code), self.assertRaisesRegex(stage.MultidimensionalStageError, code):
                stage._target_task_closure({"tasks": tasks}, "target-task")
        self.assertEqual(stage._target_task_closure({"tasks": [source, target]}, "target-task"), [source, target])

    def test_current_agent_and_skill_drift_fail_before_process_or_output_state(self):
        helper = fixtures.MultidimensionalStageTests()
        for function in ("_agent_binding", "_skill_binding"):
            with self.subTest(function=function), tempfile.TemporaryDirectory() as directory:
                run, _ = helper.prepare(Path(directory), count=1)
                index = json.loads((run / "research/dispatch-index.json").read_text())
                target = next(task for task in index["tasks"] if task["capability"] == "OPTIONS_FLOW")
                with patch.object(stage, function, return_value={"hash": "incompatible-current-resource"}), patch.object(
                    stage.subprocess, "run"
                ) as launcher, self.assertRaisesRegex(stage.MultidimensionalStageError, "INITIAL_VERSION_MISMATCH"):
                    stage.launch_multidimensional_stage(ROOT, run_dir=run, task_name=target["task_name"], initial_task=True)
                launcher.assert_not_called()
                self.assertFalse((run / "invocation").exists())

    def test_cross_run_resigned_task_index_is_not_a_fresh_launch(self):
        from product.runtime.hashing import legacy_envelope_hash
        helper = fixtures.MultidimensionalStageTests()
        with tempfile.TemporaryDirectory() as directory:
            run, _ = helper.prepare(Path(directory), count=1)
            index_path = run / "research/dispatch-index.json"
            index = json.loads(index_path.read_text())
            target = next(task for task in index["tasks"] if task["capability"] == "OPTIONS_FLOW")
            index["run_id"] = "foreign-run"
            index["index_hash"] = legacy_envelope_hash(index, hash_field="index_hash")
            index_path.write_text(json.dumps(index))
            manifest_path = run / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["dispatch_index_hash"] = index["index_hash"]
            manifest["manifest_hash"] = legacy_envelope_hash(manifest, hash_field="manifest_hash")
            manifest_path.write_text(json.dumps(manifest))
            with patch.object(stage.subprocess, "run") as launcher, self.assertRaisesRegex(
                stage.MultidimensionalStageError, "INITIAL_INPUT_NOT_READY"
            ):
                stage.launch_multidimensional_stage(ROOT, run_dir=run, task_name=target["task_name"], initial_task=True)
            launcher.assert_not_called()
            self.assertFalse((run / "invocation").exists())
