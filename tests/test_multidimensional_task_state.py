"""当前八维只读状态：实际Hook生产、stdio消费，零模型。"""
import copy
import json
import subprocess
import tomllib
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.fixture_mcp import StatelessFixtureTools
from product.runtime.hashing import file_hash, legacy_envelope_hash
from product.runtime.multidimensional_stage import (
    read_multidimensional_task_state, build_multidimensional_stage_prompt,
    MultidimensionalStageError, serialize_multidimensional_initial_context,
    serialize_multidimensional_model_context, build_multidimensional_dispatch_packet,
    launch_multidimensional_stage, build_multidimensional_dispatch_message,
)
from tests import test_multidimensional_stage as fixtures
from tests import test_task_bound_research_tools as tool_fixtures

ROOT = fixtures.ROOT


class MultidimensionalTaskStateTests(unittest.TestCase):
    helper = fixtures.MultidimensionalStageTests()

    def prepare(self, root, enabled=True):
        run, _ = self.helper.prepare(root, count=1, task_bound_tools=enabled)
        tasks = json.loads((run / "research/dispatch-index.json").read_text())["tasks"]
        return run, tasks

    def start(self, run, task, *, whole_stage=False):
        env = self.helper.targeted_environment(run, task)
        if whole_stage:
            env.pop("STOCK_AGENT_RESEARCH_TASK_NAME")
            env["STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS"] = "runtime_company_analyst,runtime_market_catalyst"
        dispatch, _ = handle_hook_event(self.helper.dispatch_payload(task, parent="p"), environ=env)
        self.assertEqual(dispatch["decision"], "ALLOW", dispatch)
        start, _ = handle_hook_event(self.helper.start_payload(task, parent="p", child=task["task_name"]), environ=env)
        self.assertEqual(start["context_binding"]["status"], "DELIVERED", start)
        return env

    def finish(self, run, task, env=None):
        env = env or self.start(run, task)
        stop, _ = handle_hook_event(self.helper.stop_payload(
            task, self.helper.dimension_draft(task), parent="p", child=task["task_name"]), environ=env)
        self.assertEqual(stop["output_capture"]["status"], "SAVED", stop)
        return stop

    def state(self, run, name):
        return next(s for s in read_multidimensional_task_state(run)["tasks"] if s["task_name"] == name)

    def test_actual_stdio_empty_snapshot_no_identity_or_content_old_profile_isolated(self):
        for enabled in (True, False):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as directory:
                run, tasks = self.prepare(Path(directory), enabled)
                protected = {p: file_hash(p) for p in run.rglob("*") if p.is_file()}
                schemas = {t["name"]: t for t in StatelessFixtureTools(default_run_dir=run).available_tools()}
                self.assertEqual(enabled, "research_task_state" in schemas)
                prompt = build_multidimensional_stage_prompt(ROOT, run)
                self.assertEqual(enabled, "research_task_state" in prompt)
                result = tool_fixtures.TaskBoundResearchToolsTests().call(run, "research_task_state", {})
                if not enabled:
                    self.assertIn("UNKNOWN_TOOL", result["error"]["message"])
                    continue
                value = result["result"]["structuredContent"]
                self.assertEqual((8, 0, False), (value["expected"], value["terminal_count"], value["all_tasks_terminal"]))
                self.assertTrue(all(s["execution_status"] == "PENDING" for s in value["tasks"]))
                self.assertEqual(value["content_acceptance"], "NOT_EVALUATED")
                self.assertNotIn("claims", json.dumps(value))
                for arguments in ({"run_dir": str(run)}, {"task_name": tasks[0]["task_name"]}, {"run_id": "foreign"}):
                    self.assertIn("error", tool_fixtures.TaskBoundResearchToolsTests().call(run, "research_task_state", arguments))
                self.assertEqual(protected, {p: file_hash(p) for p in protected})

    def test_actual_launcher_allowlist_to_stdio_state_old_profile_isolated(self):
        # Inspect the exact command handed to the existing subprocess boundary,
        # not merely the server's unfiltered tools/list or a hand-built command.
        for enabled in (True, False):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as directory:
                run, _ = self.prepare(Path(directory), enabled)
                manifest = json.loads((run / "run_manifest.json").read_text())
                self.assertEqual(file_hash(ROOT / "product/runtime/nested_codex.py"),
                                 manifest["research_execution_fingerprint"]["product/runtime/nested_codex.py"])
                with patch("product.runtime.multidimensional_stage.subprocess.run",
                           return_value=subprocess.CompletedProcess([], 1, "", "zero-model stop")) as launched:
                    result, code = launch_multidimensional_stage(ROOT, run_dir=run)
                command = launched.call_args.args[0]
                saved = json.loads((run / "invocation/environment-manifest.json").read_text())
                self.assertEqual(saved["command"], command)
                override = next(v for v in command if v.startswith("mcp_servers.fixture_runtime="))
                allowed = tomllib.loads(override)["mcp_servers"]["fixture_runtime"]["enabled_tools"]
                self.assertEqual(enabled, "research_task_state" in allowed)
                advertised = {t["name"] for t in StatelessFixtureTools(default_run_dir=run).available_tools()}
                self.assertEqual(enabled, "research_task_state" in (advertised & set(allowed)))
                self.assertEqual(enabled, "research_task_state" in launched.call_args.kwargs["input"])
                self.assertEqual((7, "MULTIDIMENSIONAL_CODEX_PROCESS_FAILED"), (code, result["failure_code"]))
                if enabled:
                    reply = tool_fixtures.TaskBoundResearchToolsTests().call(run, "research_task_state", {})
                    value = reply["result"]["structuredContent"]
                    self.assertEqual((0, False), (value["terminal_count"], value["all_tasks_terminal"]))
                    self.assertTrue(all(t["execution_status"] == "PENDING" for t in value["tasks"]))

    def test_start_and_blocked_repair_are_not_terminal_saved_partial_stays_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            run, tasks = self.prepare(Path(directory))
            task = next(t for t in tasks if t["capability"] == "FUNDAMENTAL_EVENT")
            env = self.helper.targeted_environment(run, task)
            handle_hook_event(self.helper.dispatch_payload(task, parent="p"), environ=env)
            self.assertEqual(self.state(run, task["task_name"])["execution_status"], "DISPATCHED")
            handle_hook_event(self.helper.start_payload(task, parent="p", child=task["task_name"]), environ=env)
            self.assertEqual(self.state(run, task["task_name"])["execution_status"], "RUNNING")
            bad = self.helper.dimension_draft(task)
            bad["data_gaps"][0].pop("impact")
            stop, _ = handle_hook_event(self.helper.stop_payload(task, bad, parent="p", child=task["task_name"]), environ=env)
            self.assertEqual(stop["hook_event_name"], "SubagentStopBlocked", stop)
            self.assertEqual(self.state(run, task["task_name"])["execution_status"], "RUNNING")
            repair = stop["repair_request"]
            patch = {"base_draft_ref": repair["base_draft_ref"], "changes": [
                {"op": "add", "path": "/data_gaps/0/impact", "value": "仍不足以形成研究主张。"}]}
            saved, _ = handle_hook_event(self.helper.stop_payload(task, patch, parent="p", child=task["task_name"]), environ=env)
            self.assertEqual(saved["output_capture"]["status"], "SAVED", saved)
            state = self.state(run, task["task_name"])
            self.assertEqual(("TERMINAL", "SAVED", "INSUFFICIENT_EVIDENCE", "INSUFFICIENT"),
                             tuple(state[k] for k in ("execution_status", "outcome", "research_status", "coverage_status")))

    def test_real_failed_stop_and_dependency_denial_not_unstarted_success(self):
        with tempfile.TemporaryDirectory() as directory:
            run, tasks = self.prepare(Path(directory))
            fund = next(t for t in tasks if t["capability"] == "FUNDAMENTAL_EVENT")
            rr = next(t for t in tasks if t["capability"] == "RESEARCH_REPORT")
            env = self.start(run, fund)
            payload = self.helper.stop_payload(fund, {}, parent="p", child=fund["task_name"])
            payload["last_assistant_message"] = "not JSON"
            failed, _ = handle_hook_event(payload, environ=env)
            self.assertEqual(failed["hook_event_name"], "SubagentStop")
            self.assertEqual(failed["output_capture"]["status"], "FAILED")
            self.assertEqual(self.state(run, rr["task_name"])["execution_status"], "PENDING")
            denial, _ = handle_hook_event(self.helper.dispatch_payload(rr, parent="p"),
                                        environ=self.helper.targeted_environment(run, rr))
            self.assertEqual(denial["decision"], "DENY_DISPATCH_CONTRACT")
            state = self.state(run, rr["task_name"])
            self.assertEqual(("TERMINAL", "DEPENDENCY_BLOCKED", False),
                             (state["execution_status"], state["outcome"], state["dependency_ready"]))
            self.assertEqual(read_multidimensional_task_state(run)["terminal_count"], 2)

    def test_all_eight_real_hook_terminals_including_dependency_delta_are_read_only_not_content_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            run, tasks = self.prepare(Path(directory))
            for task in tasks:
                self.finish(run, task)
            protected = {p: file_hash(p) for p in run.rglob("*") if p.is_file()}
            state = read_multidimensional_task_state(run)
            self.assertEqual((8, True, "NOT_EVALUATED"),
                             (state["terminal_count"], state["all_tasks_terminal"], state["content_acceptance"]))
            self.assertTrue(all(s["research_status"] == "INSUFFICIENT_EVIDENCE" for s in state["tasks"]))
            self.assertEqual(protected, {p: file_hash(p) for p in run.rglob("*") if p.is_file()})
            result = tool_fixtures.TaskBoundResearchToolsTests().call(run, "research_task_state", {})
            self.assertEqual(result["result"]["structuredContent"], state)
            event = json.loads((run / "events/mcp/events.jsonl").read_text().splitlines()[-1])
            self.assertEqual(event["task_state_snapshot"], state)
            from product.runtime.multidimensional_stage import finalize_multidimensional_stage_run
            bundle = finalize_multidimensional_stage_run(ROOT, run)
            self.assertEqual(bundle["completed"], 8)

    def test_tampered_hash_wrong_child_parent_duplicate_and_report_rejected(self):
        for scenario in ("hash", "child", "parent", "duplicate", "report", "report_path", "manifest", "index"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                run, tasks = self.prepare(Path(directory))
                task = next(t for t in tasks if t["capability"] == "FUNDAMENTAL_EVENT")
                stop = self.finish(run, task)
                path = run / "invocation/subagent-events.jsonl"
                rows = [json.loads(l) for l in path.read_text().splitlines()]
                if scenario == "hash":
                    rows[-1]["event_hash"] = "bad"
                elif scenario in ("child", "parent"):
                    rows[-1][f"{scenario}_session_id"] = "foreign"
                    rows[-1]["event_hash"] = legacy_envelope_hash(rows[-1], hash_field="event_hash")
                elif scenario == "duplicate":
                    rows.append(copy.deepcopy(rows[-1]))
                elif scenario == "report":
                    report = run / stop["output_capture"]["path"]
                    value = json.loads(report.read_text()); value["summary"] = "tampered"
                    report.write_text(json.dumps(value))
                elif scenario == "report_path":
                    rows[-1]["output_capture"]["path"] = "../foreign.json"
                    rows[-1]["event_hash"] = legacy_envelope_hash(rows[-1], hash_field="event_hash")
                else:
                    artifact = run / ("run_manifest.json" if scenario == "manifest" else "research/dispatch-index.json")
                    value = json.loads(artifact.read_text()); value["run_id"] = "foreign"
                    artifact.write_text(json.dumps(value))
                path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
                with self.assertRaisesRegex(MultidimensionalStageError, "TASK_STATE_BINDING_INVALID"):
                    read_multidimensional_task_state(run)

    def test_concurrent_real_dispatch_start_cannot_mix_old_dispatch_and_new_start(self):
        with tempfile.TemporaryDirectory() as directory:
            run, tasks = self.prepare(Path(directory))
            fund = next(t for t in tasks if t["capability"] == "FUNDAMENTAL_EVENT")
            tech = next(t for t in tasks if t["capability"] == "TECHNICAL_STRUCTURE")
            self.finish(run, fund)
            dispatch_path = run / "invocation/subagent-dispatches.jsonl"
            original_read = Path.read_text
            attempted, done = threading.Event(), threading.Event()
            failures = []
            triggered = False

            def producer():
                attempted.set()
                try:
                    self.start(run, tech)
                except BaseException as exc:
                    failures.append(exc)
                finally:
                    done.set()

            worker = threading.Thread(target=producer, daemon=True)

            def read(path, *args, **kwargs):
                nonlocal triggered
                if path == dispatch_path and not triggered:
                    triggered = True
                    worker.start()
                    self.assertTrue(attempted.wait(1))
                    # 真实Hook新增派发应等两个状态日志快照的读锁释放。
                    self.assertFalse(done.wait(0.05))
                return original_read(path, *args, **kwargs)

            with patch.object(Path, "read_text", read):
                state = read_multidimensional_task_state(run)
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(failures, [])
            before = next(s for s in state["tasks"] if s["task_name"] == tech["task_name"])
            self.assertEqual(before["execution_status"], "PENDING")
            self.assertEqual(self.state(run, tech["task_name"])["execution_status"], "RUNNING")

    def test_blocked_revision_must_bind_same_start_not_another_existing_child(self):
        for scenario in ("child_session_id", "agent_type", "model", "invocation_id"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                run, tasks = self.prepare(Path(directory))
                fund = next(t for t in tasks if t["capability"] == "FUNDAMENTAL_EVENT")
                tech = next(t for t in tasks if t["capability"] == "TECHNICAL_STRUCTURE")
                env = self.start(run, fund, whole_stage=True)
                self.start(run, tech, whole_stage=True)
                draft = self.helper.dimension_draft(fund)
                draft["data_gaps"][0].pop("impact")
                stop, _ = handle_hook_event(self.helper.stop_payload(fund, draft, parent="p", child=fund["task_name"]), environ=env)
                self.assertEqual(stop["hook_event_name"], "SubagentStopBlocked")
                self.assertEqual(self.state(run, fund["task_name"])["execution_status"], "RUNNING")
                path = run / "invocation/subagent-events.jsonl"
                rows = [json.loads(l) for l in path.read_text().splitlines()]
                if scenario == "invocation_id":
                    rows[-1]["trusted_task_binding"][scenario] = tech[scenario]
                else:
                    rows[-1][scenario] = {"child_session_id": tech["task_name"], "agent_type": tech["agent"], "model": "foreign"}[scenario]
                rows[-1]["event_hash"] = legacy_envelope_hash(rows[-1], hash_field="event_hash")
                path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
                with self.assertRaisesRegex(MultidimensionalStageError, "TASK_STATE_BINDING_INVALID"):
                    read_multidimensional_task_state(run)

    def test_macro_market_fact_obligations_delivered_both_paths_without_numeric_rules(self):
        with tempfile.TemporaryDirectory() as directory:
            run, tasks = self.prepare(Path(directory))
            needles = {"MACRO_CONTEXT": ["raw_release_time是发布日"],
                       "MARKET_STATE": ["grand total", "包括仅解释rise/flat/fall分桶", "先实际查询目录内该公司"],
                       "RESEARCH_REPORT": ["原文million/billion", "中文许可原文已有"]}
            self.finish(run, next(t for t in tasks if t["capability"] == "FUNDAMENTAL_EVENT"))
            for capability, needle in needles.items():
                task = next(t for t in tasks if t["capability"] == capability)
                packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
                for serialize in (serialize_multidimensional_initial_context, serialize_multidimensional_model_context):
                    for text in needle:
                        self.assertIn(text, serialize(packet))

    def test_task_bound_dispatch_executes_now_original_profile_message_preserved(self):
        for enabled in (True, False):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as directory:
                run, tasks = self.prepare(Path(directory), enabled)
                task = tasks[0]
                message = build_multidimensional_dispatch_message(ROOT, run, task["task_name"])
                if enabled:
                    self.assertIn("在本次调用内完成研究", message)
                    self.assertIn("不得以已收到或等待注入的确认句作为最终输出", message)
                    self.assertNotIn("等待 SubagentStart", message)
                else:
                    self.assertEqual(message, f"多维持仓研究任务 {task['task_name']}。等待 SubagentStart Hook 注入冻结研究包；"
                                     "以 Hook 上下文为唯一研究输入，不在启动消息中复制资料。")
                prompt = build_multidimensional_stage_prompt(ROOT, run)
                self.assertIn(message, prompt)
                self.start(run, task)


if __name__ == "__main__":
    unittest.main()
