"""八维旧生命周期的只读投影；显式合成历史事件不证明当前宿主执行。"""
import copy
import fcntl
import json
from contextlib import ExitStack
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.fixture_mcp import StatelessFixtureTools
from product.runtime.hashing import canonical_hash, file_hash, legacy_envelope_hash
from product.runtime.local_revision import _apply
from product.runtime.multidimensional_stage import (
    read_multidimensional_task_state,
    MultidimensionalStageError, serialize_multidimensional_initial_context,
    serialize_multidimensional_model_context, build_multidimensional_dispatch_packet,
    build_multidimensional_dispatch_message,
)
from tests import test_multidimensional_stage as fixtures
from tests import test_task_bound_research_tools as tool_fixtures

ROOT = fixtures.ROOT


class MultidimensionalTaskStateTests(unittest.TestCase):
    helper = fixtures.MultidimensionalStageTests()

    def prepare(self, root, enabled=True):
        run, _ = self.helper.prepare(root, count=1, task_bound_tools=enabled)
        tasks = json.loads((run / "research/dispatch-index.json").read_text())["tasks"]
        return run.resolve(), tasks

    def append_historical_rows(self, run, *, dispatches=(), events=(), invocation_dir=None):
        """历史消费者输入；显式协作锁只验证快照一致性，不派发或执行Agent。"""
        directory = invocation_dir or run / "invocation"
        paths = [directory / "subagent-dispatches.jsonl", directory / "subagent-events.jsonl"]
        paths[0].parent.mkdir(parents=True, exist_ok=True)
        with ExitStack() as stack:
            for path in paths:
                handle = stack.enter_context(path.with_suffix(path.suffix + ".lock").open("a"))
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            for path, rows in zip(paths, (dispatches, events)):
                if rows:
                    with path.open("a") as stream:
                        for row in rows:
                            row = {**row, "event_hash": legacy_envelope_hash(row, hash_field="event_hash")}
                            stream.write(json.dumps(row) + "\n")

    def historical_dispatch(self, task, *, packet_hash=None, denied=False):
        return {"parent_session_id": "p", "task_name": task["task_name"], "agent_type": task["agent"],
                "fork_turns": "none", "decision": "DENY_DISPATCH_CONTRACT" if denied else "ALLOW",
                "dispatch_binding": {"matched": not denied, "packet_hash": packet_hash,
                                     **({"failure_code": "RESEARCH_DEPENDENCY_NOT_READY"} if denied else {})}}

    def write_historical_start_fixture(self, run, task, *, invocation_dir=None):
        packet_hash = canonical_hash(build_multidimensional_dispatch_packet(ROOT, run, task["task_name"]))
        event = {"hook_event_name": "SubagentStart", "parent_session_id": "p",
                 "child_session_id": task["task_name"], "agent_type": task["agent"],
                 "model": json.loads((run / "run_manifest.json").read_text())["model"],
                 "context_binding": {"status": "DELIVERED", "task_name": task["task_name"],
                                     "run_id": task["run_id"], "invocation_id": task["invocation_id"],
                                     "packet_hash": packet_hash}}
        self.append_historical_rows(run, dispatches=[self.historical_dispatch(task, packet_hash=packet_hash)],
                                    events=[event], invocation_dir=invocation_dir)

    def write_historical_terminal_fixture(self, run, task, capture, *, blocked=False, invocation_dir=None):
        event = {"hook_event_name": "SubagentStopBlocked" if blocked else "SubagentStop",
                 "parent_session_id": "p", "child_session_id": task["task_name"],
                 "agent_type": task["agent"], "model": json.loads((run / "run_manifest.json").read_text())["model"],
                 "trusted_task_binding": {key: task[key] for key in ("task_name", "task_id", "run_id", "invocation_id", "agent")},
                 "identity_binding": {"status": "BOUND"}, "output_capture": capture}
        self.append_historical_rows(run, events=[event], invocation_dir=invocation_dir)
        return event

    def write_historical_saved_fixture(self, run, task, draft=None, *, invocation_dir=None):
        """真实业务保存后，另写明示的旧格式向量；不是Hook接受或作者执行。"""
        self.write_historical_start_fixture(run, task, invocation_dir=invocation_dir)
        report, output = self.helper.save_dimension_fixture(run, task, draft or self.helper.dimension_draft(task))
        return self.write_historical_terminal_fixture(run, task, {
            "status": "SAVED", "task_id": task["task_id"], "output_hash": canonical_hash(report),
            "path": str(Path(output["json"]).relative_to(run)),
        }, invocation_dir=invocation_dir)

    def state(self, run, name):
        return next(s for s in read_multidimensional_task_state(run)["tasks"] if s["task_name"] == name)

    def test_actual_stdio_empty_snapshot_no_identity_or_content_old_profile_isolated(self):
        for enabled in (True, False):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as directory:
                run, tasks = self.prepare(Path(directory), enabled)
                protected = {p: file_hash(p) for p in run.rglob("*") if p.is_file()}
                schemas = {t["name"]: t for t in StatelessFixtureTools(default_run_dir=run).available_tools()}
                self.assertNotIn('research_task_state', schemas)
                result = tool_fixtures.TaskBoundResearchToolsTests().call(run, 'research_task_state', {})
                self.assertIn('UNKNOWN_TOOL', result['error']['message'])
                with self.assertRaisesRegex(ValueError, 'RESEARCH_TASK_STATE_RETIRED'):
                    StatelessFixtureTools(default_run_dir=run).research_task_state()
                if not enabled:
                    continue
                value = read_multidimensional_task_state(run)
                self.assertEqual((8, 0, False), (value["expected"], value["terminal_count"], value["all_tasks_terminal"]))
                self.assertTrue(all(s["execution_status"] == "PENDING" for s in value["tasks"]))
                self.assertEqual(value["content_acceptance"], "NOT_EVALUATED")
                self.assertNotIn("claims", json.dumps(value))
                for arguments in ({"run_dir": str(run)}, {"task_name": tasks[0]["task_name"]}, {"run_id": "foreign"}):
                    self.assertIn("error", tool_fixtures.TaskBoundResearchToolsTests().call(run, "research_task_state", arguments))
                self.assertEqual(protected, {p: file_hash(p) for p in protected})

    def test_historical_start_and_blocked_revision_are_not_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            run, tasks = self.prepare(Path(directory))
            task = next(t for t in tasks if t["capability"] == "FUNDAMENTAL_EVENT")
            self.append_historical_rows(run, dispatches=[self.historical_dispatch(task)])
            self.assertEqual(self.state(run, task["task_name"])["execution_status"], "DISPATCHED")
            (run / "invocation/subagent-dispatches.jsonl").write_text("")
            self.write_historical_start_fixture(run, task)
            self.assertEqual(self.state(run, task["task_name"])["execution_status"], "RUNNING")
            bad = self.helper.dimension_draft(task)
            bad["data_gaps"][0].pop("impact")
            with self.assertRaises(ValueError):
                self.helper.read_dimension_draft(run, task, bad)
            self.write_historical_terminal_fixture(run, task, {"status": "FAILED", "repair_state": "REPAIR_REQUESTED"}, blocked=True)
            self.assertEqual(self.state(run, task["task_name"])["execution_status"], "RUNNING")
            # 测试提供补丁范围，不签发运行权限或自动修订额度。
            fixed = _apply(bad, [{"op": "add", "path": "/data_gaps/0/impact", "value": "仍不足以形成研究主张。"}],
                           ["/data_gaps/0/impact"])
            report, output = self.helper.save_dimension_fixture(run, task, fixed)
            self.write_historical_terminal_fixture(run, task, {"status": "SAVED", "task_id": task["task_id"],
                "output_hash": canonical_hash(report), "path": str(Path(output["json"]).relative_to(run))})
            state = self.state(run, task["task_name"])
            self.assertEqual(("TERMINAL", "SAVED", "INSUFFICIENT_EVIDENCE", "INSUFFICIENT"),
                             tuple(state[k] for k in ("execution_status", "outcome", "research_status", "coverage_status")))

    def test_historical_failed_stop_and_dependency_denial_are_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            run, tasks = self.prepare(Path(directory))
            fund = next(t for t in tasks if t["capability"] == "FUNDAMENTAL_EVENT")
            rr = next(t for t in tasks if t["capability"] == "RESEARCH_REPORT")
            self.write_historical_start_fixture(run, fund)
            self.write_historical_terminal_fixture(run, fund, {"status": "FAILED"})
            self.assertEqual(self.state(run, rr["task_name"])["execution_status"], "PENDING")
            self.append_historical_rows(run, dispatches=[self.historical_dispatch(rr, denied=True)])
            state = self.state(run, rr["task_name"])
            self.assertEqual(("TERMINAL", "DEPENDENCY_BLOCKED", False),
                             (state["execution_status"], state["outcome"], state["dependency_ready"]))
            self.assertEqual(read_multidimensional_task_state(run)["terminal_count"], 2)

    def test_all_eight_historical_terminals_are_read_only_not_content_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            run, tasks = self.prepare(Path(directory))
            for task in tasks:
                self.write_historical_saved_fixture(run, task)
            protected = {p: file_hash(p) for p in run.rglob("*") if p.is_file()}
            state = read_multidimensional_task_state(run)
            self.assertEqual((8, True, "NOT_EVALUATED"),
                             (state["terminal_count"], state["all_tasks_terminal"], state["content_acceptance"]))
            self.assertTrue(all(s["research_status"] == "INSUFFICIENT_EVIDENCE" for s in state["tasks"]))
            self.assertEqual(protected, {p: file_hash(p) for p in run.rglob("*") if p.is_file()})
            result = tool_fixtures.TaskBoundResearchToolsTests().call(run, 'research_task_state', {})
            self.assertIn('UNKNOWN_TOOL', result['error']['message'])
            self.assertEqual(protected, {p: file_hash(p) for p in protected})
            audit = run / 'events/mcp/events.jsonl'
            self.assertEqual({audit}, {p for p in run.rglob('*') if p.is_file()} - protected.keys())
            rows = [json.loads(line) for line in audit.read_text().splitlines()]
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['event_type'], 'mcp_tool_error')
            self.assertEqual(rows[0]['tool'], 'research_task_state')
            self.assertNotIn('task_state_snapshot', rows[0])
            from product.runtime.multidimensional_stage import finalize_multidimensional_stage_run
            bundle = finalize_multidimensional_stage_run(ROOT, run)
            self.assertEqual(bundle["completed"], 8)

    def test_tampered_hash_wrong_child_parent_duplicate_and_report_rejected(self):
        for scenario in ("hash", "child", "parent", "duplicate", "report", "report_path", "manifest", "index"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                run, tasks = self.prepare(Path(directory))
                task = next(t for t in tasks if t["capability"] == "FUNDAMENTAL_EVENT")
                stop = self.write_historical_saved_fixture(run, task)
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
                before = {p: file_hash(p) for p in run.rglob("*") if p.is_file()}
                with self.assertRaisesRegex(MultidimensionalStageError, "TASK_STATE_BINDING_INVALID"):
                    read_multidimensional_task_state(run)
                self.assertEqual(before, {p: file_hash(p) for p in run.rglob("*") if p.is_file()})

    def test_historical_snapshot_lock_cannot_mix_old_dispatch_and_new_start(self):
        with tempfile.TemporaryDirectory() as directory:
            run, tasks = self.prepare(Path(directory))
            fund = next(t for t in tasks if t["capability"] == "FUNDAMENTAL_EVENT")
            tech = next(t for t in tasks if t["capability"] == "TECHNICAL_STRUCTURE")
            self.write_historical_saved_fixture(run, fund)
            dispatch_path = run / "invocation/subagent-dispatches.jsonl"
            original_read = Path.read_text
            attempted, done = threading.Event(), threading.Event()
            failures = []
            triggered = False

            def producer():
                attempted.set()
                try:
                    self.write_historical_start_fixture(run, tech)
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

    def test_historical_blocked_revision_must_bind_same_start(self):
        for scenario in ("child_session_id", "agent_type", "model", "invocation_id"):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                run, tasks = self.prepare(Path(directory))
                fund = next(t for t in tasks if t["capability"] == "FUNDAMENTAL_EVENT")
                tech = next(t for t in tasks if t["capability"] == "TECHNICAL_STRUCTURE")
                self.write_historical_start_fixture(run, fund)
                self.write_historical_start_fixture(run, tech)
                self.write_historical_terminal_fixture(run, fund, {"status": "FAILED", "repair_state": "REPAIR_REQUESTED"}, blocked=True)
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
            fund = next(t for t in tasks if t["capability"] == "FUNDAMENTAL_EVENT")
            self.helper.save_dimension_fixture(run, fund, self.helper.dimension_draft(fund))
            for capability, needle in needles.items():
                task = next(t for t in tasks if t["capability"] == capability)
                packet = build_multidimensional_dispatch_packet(ROOT, run, task["task_name"])
                for serialize in (serialize_multidimensional_initial_context, serialize_multidimensional_model_context):
                    for text in needle:
                        self.assertIn(text, serialize(packet))
            self.assertFalse((run / "invocation").exists())

    def test_old_profile_message_readable_but_neither_profile_restores_hook(self):
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
                before = {p: file_hash(p) for p in run.rglob("*") if p.is_file()}
                for payload in (self.helper.dispatch_payload(task, parent="p"),
                                self.helper.start_payload(task, parent="p", child="c")):
                    with self.assertRaisesRegex(ValueError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                        handle_hook_event(payload, environ={"STOCK_AGENT_RUN_DIR": str(run),
                            "STOCK_AGENT_RESEARCH_TASK_NAME": task["task_name"]})
                self.assertEqual(before, {p: file_hash(p) for p in run.rglob("*") if p.is_file()})
                self.assertFalse((run / "invocation").exists())


if __name__ == "__main__":
    unittest.main()
