"""退役入口在任何模型/目录/网络调用前拒绝；仅零模型验证。"""
import ast
import contextlib
import importlib
import io
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from product.runtime.cli import main
from product.runtime.entry_policy import RETIRED_MODEL_COMMANDS

ROOT = Path(__file__).resolve().parents[1]


class NativeEntryRetirementTests(unittest.TestCase):
    def test_normal_cli_rejects_all_old_model_commands_before_argument_or_run_reads(self):
        with patch("subprocess.run", side_effect=AssertionError("No process")), patch("subprocess.Popen", side_effect=AssertionError("No process")):
            for command in sorted(RETIRED_MODEL_COMMANDS):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(main([command, "--run-dir", "/does/not/exist"]), 2)
                result = json.loads(output.getvalue())
                self.assertEqual(result["failure_code"], "NATIVE_HOST_EXECUTION_REQUIRED")
                self.assertEqual(result["llm_calls"], 0)

    def test_direct_legacy_launch_apis_and_private_process_helpers_have_no_execution_body(self):
        targets = {
            "nested_codex": ["launch_nested_codex"],
            "common_stock_stage": ["launch_common_stock_stage", "_run_bounded_process_group"],
            "multidimensional_stage": ["launch_multidimensional_stage"],
            "research_materials_stage": ["launch_research_materials_stage"],
            "independent_skeptic_stage": ["launch_skeptic_phase"],
            "predecision_cio_stage": ["launch_predecision_cio_run", "_run_cio_process"],
        }
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            missing = Path(temp)/"unprepared"
            for module, names in targets.items():
                loaded = importlib.import_module("product.runtime."+module)
                tree = ast.parse(Path(loaded.__file__).read_text())
                for name in names:
                    function = getattr(loaded, name)
                    arguments = {"prompt": "", "cwd": ROOT, "environment": {}, "timeout_seconds": 1} if name.startswith("_run_") else {"run_dir": missing}
                    with self.assertRaisesRegex(ValueError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                        function([] if name.startswith("_run_") else ROOT, **arguments)
                    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
                    self.assertFalse(any(isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                                         and n.func.attr in {"run", "Popen", "mkdir", "write_text", "write_bytes"} for n in ast.walk(node)))
                    self.assertFalse(missing.exists())

    def test_normal_hook_all_events_and_mixed_eval_flag_reject_without_files(self):
        from product.runtime.codex_hook_recorder import handle_hook_event, COMMON_STOCK_EVAL_VERSION
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/"never-created"
            env = {"STOCK_AGENT_RUN_DIR": str(root), "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(root/"events.jsonl"),
                   "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(root/"dispatch.jsonl")}
            for event in ("PreToolUse", "SubagentStart", "SubagentStop", "SessionStart", "Stop"):
                for extra in ({}, {"STOCK_AGENT_MULTIDIMENSIONAL_STAGE": "multidimensional-holding-research-runtime/2.0.0"},
                              {"STOCK_AGENT_COMMON_STOCK_EVAL": COMMON_STOCK_EVAL_VERSION,
                               "STOCK_AGENT_CAPTURE_SPECIALIST_OUTPUT": "1"}):
                    with self.subTest(event=event, extra=extra), self.assertRaisesRegex(ValueError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                        handle_hook_event({"hook_event_name": event}, environ={**env, **extra})
                    self.assertFalse(root.exists())

    def test_normal_command_builders_reject_before_runtime_probe_and_eval_has_no_research_hooks(self):
        import tomllib
        from product.runtime.nested_codex import build_nested_codex_command, build_verified_nested_codex_command
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)/"unprepared"
            args = {"codex_binary": "never-run", "product_root": ROOT, "run_dir": root, "model": "test-model",
                    "sqlite_home": root/"sqlite", "log_dir": root/"logs", "final_message_path": root/"final",
                    "hook_recorder_path": ROOT/"product/runtime/codex_hook_recorder.py"}
            with patch("subprocess.run", side_effect=AssertionError("No process")):
                with self.assertRaisesRegex(ValueError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                    build_verified_nested_codex_command(runtime_binding_path=root/"runtime.json", **args)
                for extra in ({}, {"hook_agent_matcher": "^runtime_market_catalyst$"},
                              {"hook_agent_matcher": "^dev_eval$", "enable_parent_stop_barrier": True},
                              {"hook_agent_matcher": "^dev_eval$", "enable_cio_local_revision": True},
                              {"hook_agent_matcher": "^dev_eval$", "fixture_mcp_run_dir": root},
                              {"hook_agent_matcher": "^dev_eval$", "research_submission_enabled": True}):
                    with self.subTest(extra=extra), self.assertRaisesRegex(ValueError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                        build_nested_codex_command(**{**args, **extra})
            command = build_nested_codex_command(**args, hook_agent_matcher="^dev_eval$")
            overrides = [tomllib.loads(command[i+1]) for i, value in enumerate(command) if value == "-c"]
            hooks = {key: value for override in overrides for key, value in override.get("hooks", {}).items()}
            self.assertEqual(set(hooks), {"PreToolUse", "SubagentStart", "SubagentStop"})
            self.assertEqual(hooks["SubagentStart"][0]["matcher"], "^dev_eval$")
            self.assertEqual(hooks["SubagentStop"][0]["matcher"], "^dev_eval$")
            self.assertFalse(root.exists())

    def test_normal_import_and_cli_help_do_not_import_old_execution_or_stage_modules(self):
        script = 'import sys; from product.runtime.cli import build_parser; build_parser(); bad=[m for m in sys.modules if m.startswith("product.runtime.") and any(s in m for s in ("nested_codex", "codex_hook", "stage", "codex_runtime", "environment_preflight"))]; assert not bad,bad; print("NORMAL_HELP_NO_EXECUTION_DEPENDENCY")'
        result = subprocess.run([sys.executable, "-B", "-c", script], cwd=ROOT, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_shell_rejects_old_normal_stages_without_provider_or_output_writes(self):
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            output = Path(temp)/"output"
            for arguments in ([], ["--stage", "single-stock-research", "--single-stock", "ALB", str(output)],
                              ["--resume-multidimensional-run", "/not/a/run", str(output)]):
                result = subprocess.run(["bash", str(ROOT/"scripts/run-product-smoke.sh"), *arguments],
                                        text=True, capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("NATIVE_HOST_EXECUTION_REQUIRED", result.stderr)
                self.assertFalse(output.exists())

    def test_thin_entry_rejects_normal_launcher_and_fake_replay_before_subprocess(self):
        namespace = runpy.run_path(str(ROOT/"scripts/council-dev.py"))
        with patch("subprocess.run", side_effect=AssertionError("No process")):
            for command in RETIRED_MODEL_COMMANDS:
                with self.assertRaisesRegex(ValueError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                    namespace["forwarded_command"]([command, "--run-dir", "/not/a/run"], calling_cwd=ROOT)
        with tempfile.TemporaryDirectory(dir="/private/tmp") as temp:
            root = Path(temp)
            (root/"run_manifest.json").write_text(json.dumps({"run_mode": "NORMAL"}))
            with self.assertRaisesRegex(ValueError, "FROZEN_EXECUTION_REPLAY_REQUIRED"):
                namespace["forwarded_command"](["execute-frozen-replay", "--run-dir", str(root)], calling_cwd=ROOT)
