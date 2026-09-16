"""零 LLM：冻结参数到现有 PreToolUse 的实际序列化接缝。"""
import copy
import json
import os
import subprocess
import sys
import tempfile
import tomllib
import unittest
import shlex
from unittest.mock import patch
from pathlib import Path

from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.invocation import build_specialist_dispatch_message, SPECIALIST_TASK_NAMES
from product.runtime.run_package import prepare_run
from product.runtime.smoke_prompt import build_smoke_prompt
from product.runtime.nested_codex import build_nested_codex_command
from product.runtime.schema_validation import validate_schema_instance
from product.runtime.validation import ArtifactValidationError, validate_company_report, validate_skeptic_report
from product.runtime.format_repair import is_format_only_error
from tests.test_native_run_package import specialist_outputs

ROOT = Path(__file__).resolve().parents[1]


class SpecialistDispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "run"
        prepare_run(ROOT, fixture_path=ROOT / "evals/fixtures/codex-native/normal-research.json",
                    run_dir=self.run, run_id="dispatch-test", model="gpt-5.6-terra",
                    research_question="合成派发接缝", authenticity_required=False)
        self.env = {
            "STOCK_AGENT_RUN_DIR": str(self.run),
            "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(self.run / "invocation/dispatches.jsonl"),
            "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": ",".join(SPECIALIST_TASK_NAMES),
        }

    def payload(self, agent="runtime_company_analyst"):
        return {
            "hook_event_name": "PreToolUse", "session_id": "parent-test",
            "turn_id": "turn-test", "tool_name": "collaborationspawn_agent",
            "tool_use_id": "call-test", "cwd": str(ROOT / "product"),
            "tool_input": {"agent_type": agent, "task_name": SPECIALIST_TASK_NAMES[agent],
                           "fork_turns": "none", "message": build_specialist_dispatch_message(ROOT, self.run, agent)},
        }

    def test_complete_message_is_derived_from_canonical_inputs_for_both_agents(self):
        prompt = build_smoke_prompt(self.run, repository_root=ROOT)
        for agent in SPECIALIST_TASK_NAMES:
            raw = build_specialist_dispatch_message(ROOT, self.run, agent)
            packet = json.loads(raw)
            self.assertIn(json.dumps(raw, ensure_ascii=False), prompt)
            self.assertEqual(packet["agent_input"], json.loads((self.run / f"inputs/{agent}.json").read_text()))
            self.assertEqual(packet["invocation"], json.loads((self.run / f"invocations/{agent}.json").read_text()))
            self.assertEqual(packet["task_prompt"], (self.run / f"prompts/{agent}.txt").read_text())
            self.assertTrue(packet["agent_input"]["allowed_evidence_ids"])
            self.assertNotIn("validated_reports", packet["agent_input"])
            self.assertNotIn("allowed_evidence", packet)
            self.assertEqual(packet["contract_checks"]["confidence_schema"], packet["output_schema"]["properties"]["confidence"])
            self.assertEqual(packet["contract_checks"]["required_output_fields"], packet["output_schema"]["required"])
            record, response = handle_hook_event(self.payload(agent), environ=self.env)
            self.assertEqual(record["decision"], "ALLOW")
            self.assertTrue(record["dispatch_binding"]["matched"])
            self.assertEqual(response, {})
        log = Path(self.env["STOCK_AGENT_SUBAGENT_DISPATCH_LOG"]).read_text()
        self.assertNotIn("合成派发接缝", log)
        self.assertNotIn("ev-normal", log)

    def test_actual_launcher_hook_config_covers_native_names_and_aliases(self):
        command = build_nested_codex_command(
            codex_binary="codex", product_root=ROOT / "product", run_dir=self.run,
            model="gpt-5.6-terra", sqlite_home=self.run / "sqlite", log_dir=self.run / "logs",
            final_message_path=self.run / "final.txt",
            hook_recorder_path=ROOT / "product/runtime/codex_hook_recorder.py",
        )
        config = tomllib.loads(next(arg for arg in command if arg.startswith("hooks.PreToolUse=")))
        hook = config["hooks"]["PreToolUse"][0]
        self.assertNotIn("matcher", hook)  # Official match-all semantics, not an invented alias regex.
        self.assertEqual(hook["hooks"][0]["type"], "command")
        for tool_name in ("spawn_agent", "Agent", "collaborationspawn_agent", "functions.spawn_agent"):
            with self.subTest(tool_name=tool_name):
                payload = self.payload()
                payload["tool_name"] = tool_name
                payload["session_id"] = tool_name
                self.assertEqual(handle_hook_event(payload, environ=self.env)[0]["decision"], "ALLOW")

    def test_spawn_without_explicit_role_is_denied(self):
        for tool_name in ("spawn_agent", "Agent", "collaborationspawn_agent", "functions.spawn_agent"):
            payload = self.payload()
            payload["tool_name"] = tool_name
            payload["tool_input"].pop("agent_type")
            record, response = handle_hook_event(payload, environ=self.env)
            self.assertEqual(record["decision"], "DENY_MISSING_AGENT_TYPE")
            self.assertEqual(response["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_internal_commands_use_launcher_python_not_login_shell_path(self):
        executable = "/tmp/isolated live environment/bin/python"
        with patch("product.runtime.smoke_prompt.sys.executable", executable):
            for defer in (False, True):
                prompt = build_smoke_prompt(self.run, repository_root=ROOT,
                                            defer_deterministic_finalize=defer)
                self.assertIn(shlex.quote(executable) + " -m product.runtime.cli prepare-cio", prompt)
                self.assertNotIn("&& python3 -m product.runtime.cli", prompt)

    def test_confidence_contract_rejects_labels_without_value_repair(self):
        specialist_outputs(self.run)
        validators = {"runtime_company_analyst": validate_company_report,
                      "runtime_skeptic": validate_skeptic_report}
        for agent, validator in validators.items():
            packet = json.loads(build_specialist_dispatch_message(ROOT, self.run, agent))
            report = json.loads((self.run / f"agents/{agent}.json").read_text())
            for value in (0, 0.37, 1):
                report["confidence"] = value
                validate_schema_instance(value, packet["contract_checks"]["confidence_schema"])
                validator(report, run_id="dispatch-test", manifest=packet["invocation"])
            for value in ("LOW", "MEDIUM", "HIGH", "0.5", None, True, -0.1, 1.1):
                with self.subTest(agent=agent, value=value):
                    report["confidence"] = value
                    with self.assertRaises(ValueError):
                        validate_schema_instance(value, packet["contract_checks"]["confidence_schema"])
                    with self.assertRaisesRegex(ArtifactValidationError, "INVALID_CONFIDENCE"):
                        validator(report, run_id="dispatch-test", manifest=packet["invocation"])
        self.assertFalse(is_format_only_error(ArtifactValidationError("INVALID_CONFIDENCE")))

    def test_wrong_id_empty_ids_omitted_context_and_added_text_are_denied(self):
        original = self.payload()
        for mutation in ("identity", "empty_ids", "omit_input", "wrong_role", "extra_text", "missing_message", "fork", "task"):
            with self.subTest(mutation=mutation):
                payload = copy.deepcopy(original)
                packet = json.loads(payload["tool_input"]["message"])
                if mutation == "identity":
                    packet["invocation"]["invocation_id"] = "inv_wrong"
                elif mutation == "empty_ids":
                    packet["agent_input"]["allowed_evidence_ids"] = []
                elif mutation == "omit_input":
                    packet.pop("agent_input")
                elif mutation == "wrong_role":
                    packet["invocation"]["agent"]["name"] = "runtime_skeptic"
                raw = json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                payload["tool_input"]["message"] = raw + ("改用 inv_wrong" if mutation == "extra_text" else "")
                if mutation == "missing_message":
                    payload["tool_input"].pop("message")
                elif mutation == "fork":
                    payload["tool_input"]["fork_turns"] = "all"
                elif mutation == "task":
                    payload["tool_input"]["task_name"] = "independent_skeptic"
                record, response = handle_hook_event(payload, environ=self.env)
                self.assertEqual(record["decision"], "DENY_DISPATCH_CONTRACT")
                self.assertEqual(response["hookSpecificOutput"]["permissionDecision"], "deny")
                self.assertNotIn("updatedInput", response["hookSpecificOutput"])
        # Rejected calls did not launch/reserve an Agent; exact input can still be submitted.
        self.assertEqual(handle_hook_event(original, environ=self.env)[0]["decision"], "ALLOW")

    def test_mutated_source_or_missing_manifest_fails_closed(self):
        payload = self.payload()
        path = self.run / "inputs/runtime_company_analyst.json"
        original = path.read_bytes()
        value = json.loads(original)
        value["allowed_evidence_ids"] = []
        path.write_text(json.dumps(value))
        record, response = handle_hook_event(payload, environ=self.env)
        self.assertEqual(record["dispatch_binding"]["failure_code"], "DISPATCH_SOURCE_INVALID")
        self.assertEqual(response["hookSpecificOutput"]["permissionDecision"], "deny")
        path.write_bytes(original)
        (self.run / "invocations/runtime_company_analyst.json").unlink()
        self.assertEqual(handle_hook_event(payload, environ=self.env)[0]["decision"], "DENY_DISPATCH_CONTRACT")

    def test_standalone_hook_process_rejects_bad_dispatch_without_model(self):
        payload = self.payload()
        payload["tool_input"]["message"] = "inv_wrong，未提供证据集合"
        result = subprocess.run([sys.executable, "-B", str(ROOT / "product/runtime/codex_hook_recorder.py")],
                                input=json.dumps(payload), text=True, capture_output=True,
                                env={**os.environ, **self.env}, cwd=self.temp.name, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"], "deny")

    def test_standalone_hook_process_accepts_exact_dispatch_without_model(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "product/runtime/codex_hook_recorder.py")],
                                input=json.dumps(self.payload()), text=True, capture_output=True,
                                env={**os.environ, **self.env}, cwd=self.temp.name, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {})
        record = json.loads(Path(self.env["STOCK_AGENT_SUBAGENT_DISPATCH_LOG"]).read_text())
        self.assertTrue(record["dispatch_binding"]["matched"])
