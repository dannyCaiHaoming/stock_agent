"""退役启动器拒绝、显式评分命令及历史事件纯投影；不启动模型。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.runtime.nested_codex import build_nested_codex_command, launch_nested_codex
from product.runtime.codex_hook_recorder import minimize_hook_event
from product.runtime.run_package import _record_all_artifacts

ROOT = Path(__file__).resolve().parents[1]


class NestedCodexLauncherTests(unittest.TestCase):
    def command_arguments(self, run_dir):
        return dict(
            codex_binary="codex", product_root=ROOT / "product", run_dir=run_dir,
            model="gpt-6-luna", sqlite_home=run_dir / ".codex-runtime/sqlite",
            log_dir=run_dir / ".codex-runtime/logs",
            final_message_path=run_dir / ".codex-runtime/tmp/final.txt",
            hook_recorder_path=ROOT / "product/runtime/codex_hook_recorder.py",
            hook_agent_matcher="^dev_eval$",
        )

    def test_eval_command_is_ephemeral_isolated_and_keeps_user_config(self):
        command = build_nested_codex_command(**self.command_arguments(Path("/tmp/run")))
        for expected in (
            "--ephemeral", "--json", "workspace-write", "never",
            'sqlite_home="/tmp/run/.codex-runtime/sqlite"',
            'log_dir="/tmp/run/.codex-runtime/logs"',
            'history.persistence="none"', "--dangerously-bypass-hook-trust",
        ):
            self.assertIn(expected, command)
        self.assertNotIn("--ignore-user-config", command)
        for event in ("PreToolUse", "SubagentStart", "SubagentStop"):
            self.assertTrue(any(item.startswith(f"hooks.{event}=") for item in command))
        self.assertFalse(any(item.startswith("hooks.Stop=") for item in command))
        self.assertFalse(any(item.startswith("mcp_servers.") for item in command))

    def test_eval_command_preserves_native_sandbox_and_rejects_external_mode(self):
        arguments = self.command_arguments(Path("/tmp/run"))
        command = build_nested_codex_command(**arguments)
        self.assertEqual(command, build_nested_codex_command(**arguments, externally_sandboxed=False))
        self.assertEqual(command[command.index("--sandbox") + 1], "workspace-write")
        for forbidden in ("--dangerously-bypass-approvals-and-sandbox", "--yolo", "danger-full-access"):
            self.assertNotIn(forbidden, command)
        with patch("subprocess.run") as run, patch.object(Path, "mkdir") as mkdir, patch.object(Path, "read_text") as read:
            with self.assertRaisesRegex(ValueError, "^LEGACY_SANDBOX_MODE_RETIRED$"):
                build_nested_codex_command(**arguments, externally_sandboxed=True)
            run.assert_not_called()
            mkdir.assert_not_called()
            read.assert_not_called()

    def test_preflight_is_rejected_before_run_or_report_is_read(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            report = base / "preflight.json"
            report.write_text('{"status":"READY","report_hash":"historical"}')
            for path in (report, base / "missing.json"):
                with self.subTest(path=path), patch("subprocess.run") as run, patch.object(
                    Path, "read_text"
                ) as read, patch.object(Path, "mkdir") as mkdir:
                    with self.assertRaisesRegex(ValueError, "^LEGACY_SANDBOX_MODE_RETIRED$"):
                        launch_nested_codex(ROOT, run_dir=base / "unprepared", preflight_report=path)
                    read.assert_not_called()
                    mkdir.assert_not_called()
                    run.assert_not_called()
            self.assertEqual(sorted(p.name for p in base.iterdir()), ["preflight.json"])

    def test_historical_hook_projection_minimizes_output_without_writing(self):
        payload = {
            "hook_event_name": "SubagentStop", "session_id": "parent-1", "turn_id": "turn-1",
            "agent_id": "child-1", "agent_type": "runtime_skeptic", "model": "gpt-6-luna",
            "cwd": str(ROOT / "product"), "permission_mode": "dontAsk",
            "agent_transcript_path": None, "stop_hook_active": False,
            "last_assistant_message": json.dumps({
                "run_id": "run-1", "invocation_id": "inv-1", "agent": "runtime_skeptic",
                "private_prose": "不得持久化",
            }),
        }
        original = json.dumps(payload, sort_keys=True)
        with patch.object(Path, "mkdir") as mkdir, patch.object(Path, "write_text") as write:
            record = minimize_hook_event(payload)
            mkdir.assert_not_called()
            write.assert_not_called()
        self.assertNotIn("不得持久化", json.dumps(record, ensure_ascii=False))
        self.assertEqual(record["output_binding"]["invocation_id"], "inv-1")
        self.assertTrue(record["structured_output_present"])
        self.assertEqual(json.dumps(payload, sort_keys=True), original)

    def test_operational_codex_state_is_not_part_of_decision_trace_closure(self):
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory) / "run"
            (run_dir / ".codex-runtime/sqlite").mkdir(parents=True)
            (run_dir / "invocation").mkdir()
            (run_dir / "evidence").mkdir()
            (run_dir / ".codex-runtime/sqlite/state.sqlite").write_text("live")
            (run_dir / "invocation/prompt.txt").write_text("prompt")
            (run_dir / "evidence/gate.json").write_text("{}")
            trace = {"artifacts": {}}
            _record_all_artifacts(trace, run_dir)
            self.assertEqual(set(trace["artifacts"]), {"evidence/gate.json"})


if __name__ == "__main__":
    unittest.main()
