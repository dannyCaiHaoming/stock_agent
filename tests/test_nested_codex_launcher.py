from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.runtime.nested_codex import (
    _completion_checks,
    build_nested_codex_command,
    launch_nested_codex,
)
from product.runtime.codex_hook_recorder import handle_hook_event, record_hook_event
from product.runtime.run_package import _record_all_artifacts, prepare_run


ROOT = Path(__file__).resolve().parents[1]


class NestedCodexLauncherTests(unittest.TestCase):
    def test_command_is_ephemeral_isolated_and_keeps_user_config(self):
        run_dir = Path("/tmp/run")
        command = build_nested_codex_command(
            codex_binary="codex",
            product_root=ROOT / "product",
            run_dir=run_dir,
            model="gpt-5.6-terra",
            sqlite_home=run_dir / ".codex-runtime" / "sqlite",
            log_dir=run_dir / ".codex-runtime" / "logs",
            final_message_path=run_dir / ".codex-runtime" / "tmp" / "final.txt",
            hook_recorder_path=ROOT / "product" / "runtime" / "codex_hook_recorder.py",
        )
        for expected in (
            "--ephemeral",
            "--json",
            "workspace-write",
            "never",
            "sqlite_home=\"/tmp/run/.codex-runtime/sqlite\"",
            "log_dir=\"/tmp/run/.codex-runtime/logs\"",
            'history.persistence="none"',
            "--dangerously-bypass-hook-trust",
        ):
            self.assertIn(expected, command)
        self.assertNotIn("--ignore-user-config", command)
        self.assertTrue(any(item.startswith("hooks.PreToolUse=") for item in command))
        self.assertTrue(any("collaborationspawn_agent" in item for item in command))
        self.assertTrue(any(item.startswith("hooks.SubagentStart=") for item in command))
        self.assertTrue(any(item.startswith("hooks.SubagentStop=") for item in command))

    def test_hook_recorder_minimizes_output_and_scopes_log_to_run(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            log_path = run_dir / "invocation" / "subagent-events.jsonl"
            payload = {
                "hook_event_name": "SubagentStop",
                "session_id": "parent-1",
                "turn_id": "turn-1",
                "agent_id": "child-1",
                "agent_type": "runtime_skeptic",
                "model": "gpt-5.6-terra",
                "cwd": str(ROOT / "product"),
                "permission_mode": "dontAsk",
                "agent_transcript_path": None,
                "stop_hook_active": False,
                "last_assistant_message": json.dumps(
                    {
                        "run_id": "run-1",
                        "invocation_id": "inv-1",
                        "agent": "runtime_skeptic",
                        "private_prose": "不得持久化",
                    }
                ),
            }
            record = record_hook_event(
                payload,
                environ={
                    "STOCK_AGENT_RUN_DIR": str(run_dir),
                    "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(log_path),
                },
            )
            persisted = log_path.read_text(encoding="utf-8")
            self.assertNotIn("不得持久化", persisted)
            self.assertEqual(record["output_binding"]["invocation_id"], "inv-1")
            self.assertTrue(record["structured_output_present"])
            with self.assertRaisesRegex(ValueError, "OUTSIDE_RUN_DIR"):
                record_hook_event(
                    payload,
                    environ={
                        "STOCK_AGENT_RUN_DIR": str(run_dir),
                        "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(Path(directory) / "outside.jsonl"),
                    },
                )

    def test_stop_hook_blocks_first_specialist_until_both_have_started(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            log_path = run_dir / "invocation" / "subagent-events.jsonl"
            environment = {
                "STOCK_AGENT_RUN_DIR": str(run_dir),
                "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(log_path),
                "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": (
                    "runtime_company_analyst,runtime_skeptic"
                ),
            }
            common = {
                "session_id": "parent-1",
                "turn_id": "turn-1",
                "model": "gpt-5.6-terra",
                "cwd": str(ROOT / "product"),
                "permission_mode": "dontAsk",
            }
            analyst_start = {
                **common,
                "hook_event_name": "SubagentStart",
                "agent_id": "analyst-1",
                "agent_type": "runtime_company_analyst",
            }
            _, response = handle_hook_event(analyst_start, environ=environment)
            self.assertEqual(response, {})
            analyst_stop = {
                **common,
                "hook_event_name": "SubagentStop",
                "agent_id": "analyst-1",
                "agent_type": "runtime_company_analyst",
                "stop_hook_active": False,
                "last_assistant_message": "{}",
            }
            blocked, response = handle_hook_event(analyst_stop, environ=environment)
            self.assertEqual(blocked["hook_event_name"], "SubagentStopBlocked")
            self.assertEqual(response["decision"], "block")
            skeptic_start = {
                **common,
                "hook_event_name": "SubagentStart",
                "agent_id": "skeptic-1",
                "agent_type": "runtime_skeptic",
            }
            handle_hook_event(skeptic_start, environ=environment)
            allowed, response = handle_hook_event(analyst_stop, environ=environment)
            self.assertEqual(allowed["hook_event_name"], "SubagentStop")
            self.assertEqual(response, {})

    def test_dispatch_hook_atomically_rejects_duplicate_without_retaining_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            dispatch_log = run_dir / "invocation" / "subagent-dispatches.jsonl"
            environment = {
                "STOCK_AGENT_RUN_DIR": str(run_dir),
                "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(dispatch_log),
                "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": (
                    "runtime_company_analyst,runtime_skeptic"
                ),
            }
            payload = {
                "hook_event_name": "PreToolUse",
                "session_id": "parent-1",
                "turn_id": "turn-1",
                "tool_name": "spawn_agent",
                "tool_use_id": "call-1",
                "model": "gpt-5.6-terra",
                "cwd": str(ROOT / "product"),
                "permission_mode": "dontAsk",
                "tool_input": {
                    "agent_type": "runtime_skeptic",
                    "task_name": "independent_skeptic",
                    "fork_turns": "none",
                    "message": "这段 Specialist 提示不得保存",
                },
            }
            allowed, response = handle_hook_event(payload, environ=environment)
            self.assertEqual(allowed["decision"], "ALLOW")
            self.assertEqual(response, {})

            duplicate, response = handle_hook_event(
                {**payload, "tool_use_id": "call-2"},
                environ=environment,
            )
            self.assertEqual(duplicate["decision"], "DENY_DUPLICATE_AGENT")
            self.assertEqual(
                response["hookSpecificOutput"]["permissionDecision"],
                "deny",
            )
            persisted = dispatch_log.read_text(encoding="utf-8")
            self.assertNotIn("这段 Specialist 提示不得保存", persisted)

    def test_dispatch_hook_rejects_unapproved_agent(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            dispatch_log = run_dir / "invocation" / "subagent-dispatches.jsonl"
            payload = {
                "hook_event_name": "PreToolUse",
                "session_id": "parent-1",
                "turn_id": "turn-1",
                "tool_name": "spawn_agent",
                "tool_use_id": "call-1",
                "cwd": str(ROOT / "product"),
                "tool_input": {"agent_type": "runtime_cio", "message": "禁止保存"},
            }
            record, response = handle_hook_event(
                payload,
                environ={
                    "STOCK_AGENT_RUN_DIR": str(run_dir),
                    "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(dispatch_log),
                    "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": (
                        "runtime_company_analyst,runtime_skeptic"
                    ),
                },
            )
            self.assertEqual(record["decision"], "DENY_UNAPPROVED_AGENT")
            self.assertEqual(
                response["hookSpecificOutput"]["permissionDecision"],
                "deny",
            )

    def test_dispatch_hook_observes_non_agent_tool_without_retaining_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            dispatch_log = run_dir / "invocation" / "subagent-dispatches.jsonl"
            record, response = handle_hook_event(
                {
                    "hook_event_name": "PreToolUse",
                    "session_id": "parent-1",
                    "turn_id": "turn-1",
                    "tool_name": "Bash",
                    "tool_use_id": "call-1",
                    "cwd": str(ROOT / "product"),
                    "tool_input": {"command": "echo 绝不能保存的命令参数"},
                },
                environ={
                    "STOCK_AGENT_RUN_DIR": str(run_dir),
                    "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(dispatch_log),
                },
            )
            self.assertEqual(record["decision"], "IGNORE_NON_AGENT_TOOL")
            self.assertEqual(response, {})
            self.assertNotIn(
                "绝不能保存的命令参数",
                dispatch_log.read_text(encoding="utf-8"),
            )

    def test_operational_codex_state_is_not_part_of_decision_trace_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            (run_dir / ".codex-runtime" / "sqlite").mkdir(parents=True)
            (run_dir / "invocation").mkdir()
            (run_dir / "evidence").mkdir()
            (run_dir / ".codex-runtime" / "sqlite" / "state.sqlite").write_text("live")
            (run_dir / "invocation" / "prompt.txt").write_text("prompt")
            (run_dir / "evidence" / "gate.json").write_text("{}")
            trace = {"artifacts": {}}
            _record_all_artifacts(trace, run_dir)
            self.assertEqual(set(trace["artifacts"]), {"evidence/gate.json"})

    def test_prepare_only_trace_identifies_first_missing_runtime_stage(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            prepare_run(
                ROOT,
                fixture_path=ROOT / "evals" / "fixtures" / "codex-native" / "normal-research.json",
                run_dir=run_dir,
                run_id="nested-prepare-only",
                model="gpt-5.6-terra",
                research_question="验证 prepare-only 失败判定。",
            )
            checks, failure = _completion_checks(run_dir)
            self.assertEqual(failure, "SKILL_LOAD_PROOF_MISSING")
            self.assertFalse(checks["specialists_executed"])
            self.assertFalse(checks["terminal_state_valid"])

    def test_completion_check_uses_canonical_trace_agent_name(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "events" / "codex").mkdir(parents=True)
            (run_dir / "eval").mkdir()
            (run_dir / "decision_trace.json").write_text(
                json.dumps(
                    {
                        "terminal_state": "SAFE_NO_TRADE",
                        "events": [],
                        "agents": [{"name": "runtime_cio", "status": "COMPLETED"}],
                        "risk_lineage": [{"status": "COMPLETED"}],
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "events" / "codex" / "specialist-execution-proof.json").write_text(
                json.dumps(
                    {
                        "portfolio_council_skill_bound": True,
                        "dispatches": [
                            {"agent": "runtime_company_analyst"},
                            {"agent": "runtime_skeptic"},
                        ],
                        "children": {
                            "runtime_company_analyst": {},
                            "runtime_skeptic": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (run_dir / "invocation").mkdir()
            (run_dir / "invocation" / "subagent-dispatches.jsonl").write_text(
                "\n".join(
                    json.dumps(
                        {
                            "hook_event_name": "PreToolUse",
                            "agent_type": agent,
                            "decision": "ALLOW",
                            "raw_prompt_or_reasoning_retained": False,
                        }
                    )
                    for agent in ("runtime_company_analyst", "runtime_skeptic")
                )
                + "\n",
                encoding="utf-8",
            )
            for path in (
                run_dir / "decision.json",
                run_dir / "report.md",
                run_dir / "eval" / "result.json",
            ):
                path.write_text("{}", encoding="utf-8")
            checks, failure = _completion_checks(run_dir)
            self.assertIsNone(failure)
            self.assertTrue(checks["dispatch_guard_active"])
            self.assertTrue(checks["cio_executed"])

    def test_zero_codex_exit_cannot_mask_incomplete_council(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            prepare_run(
                ROOT,
                fixture_path=ROOT / "evals" / "fixtures" / "codex-native" / "normal-research.json",
                run_dir=run_dir,
                run_id="nested-exit-zero-incomplete",
                model="gpt-5.6-terra",
                research_question="验证退出码不能替代终态校验。",
            )

            def fake_run(command, **kwargs):
                kwargs["stdout"].write(
                    json.dumps({"type": "thread.started", "thread_id": "test-thread"}) + "\n"
                )
                kwargs["stdout"].flush()
                final_path = Path(command[command.index("--output-last-message") + 1])
                final_path.write_text("prepare only", encoding="utf-8")
                return subprocess.CompletedProcess(command, 0)

            with patch("product.runtime.nested_codex.subprocess.run", side_effect=fake_run):
                result, exit_code = launch_nested_codex(
                    ROOT,
                    run_dir=run_dir,
                    timeout_seconds=5,
                )

            self.assertEqual(exit_code, 7)
            self.assertEqual(result["codex_exit_code"], 0)
            self.assertEqual(result["failure_code"], "SKILL_LOAD_PROOF_MISSING")
            invocation = run_dir / "invocation"
            for name in (
                "prompt.txt",
                "invocation-manifest.json",
                "codex-events.jsonl",
                "codex-stderr.log",
                "final-message.json",
                "process-result.json",
                "environment-manifest.json",
            ):
                self.assertTrue((invocation / name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
