"""冻结Specialist输入的业务校验与旧正常派发拒绝；零模型、零网络。"""
import json
import os
import subprocess
import sys
import tempfile
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
        result = prepare_run(ROOT, fixture_path=ROOT / "evals/fixtures/codex-native/normal-research.json",
                             run_dir=self.run, run_id="dispatch-test", model="gpt-6-luna",
                             research_question="合成输入接缝", authenticity_required=False)
        self.assertTrue((self.run / "run_manifest.json").is_file(), result)
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

    def test_complete_historical_message_is_derived_from_canonical_inputs_for_both_agents(self):
        before = {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        prompt = build_smoke_prompt(self.run, repository_root=ROOT)
        for agent in SPECIALIST_TASK_NAMES:
            packet = json.loads(build_specialist_dispatch_message(ROOT, self.run, agent))
            tickets = json.loads(prompt.rsplit("```json\n", 1)[1].split("```", 1)[0])
            ticket = json.loads(tickets[agent])
            self.assertEqual(ticket["agent"], agent)
            self.assertNotIn("agent_input", ticket)
            self.assertNotIn("invocation", ticket)
            self.assertEqual(packet["agent_input"], json.loads((self.run / f"inputs/{agent}.json").read_text()))
            self.assertEqual(packet["invocation"], json.loads((self.run / f"invocations/{agent}.json").read_text()))
            self.assertEqual(packet["task_prompt"], (self.run / f"prompts/{agent}.txt").read_text())
            self.assertTrue(packet["agent_input"]["allowed_evidence_ids"])
            self.assertNotIn("validated_reports", packet["agent_input"])
            self.assertNotIn("allowed_evidence", packet)
            self.assertEqual(packet["contract_checks"]["confidence_schema"], packet["output_schema"]["properties"]["confidence"])
            self.assertEqual(packet["contract_checks"]["required_output_fields"], packet["output_schema"]["required"])
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()})
        self.assertFalse((self.run / "invocation").exists())

    def test_retired_dispatch_rejects_native_names_aliases_and_malformed_inputs_without_state(self):
        before = {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        for tool_name in ("spawn_agent", "Agent", "collaborationspawn_agent", "functions.spawn_agent"):
            for mutation in ("exact", "no-role", "wrong-task", "fork", "changed-message"):
                with self.subTest(tool_name=tool_name, mutation=mutation):
                    payload = self.payload()
                    payload["tool_name"] = tool_name
                    if mutation == "no-role":
                        payload["tool_input"].pop("agent_type")
                    elif mutation == "wrong-task":
                        payload["tool_input"]["task_name"] = "wrong"
                    elif mutation == "fork":
                        payload["tool_input"]["fork_turns"] = "all"
                    elif mutation == "changed-message":
                        payload["tool_input"]["message"] += " changed"
                    with self.assertRaisesRegex(ValueError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                        handle_hook_event(payload, environ=self.env)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()})
        self.assertFalse((self.run / "invocation").exists())

    def test_normal_launcher_cannot_restore_dispatch_hooks(self):
        before = {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(ValueError, "NATIVE_HOST_EXECUTION_REQUIRED"):
            build_nested_codex_command(
                codex_binary="codex", product_root=ROOT / "product", run_dir=self.run,
                model="gpt-6-luna", sqlite_home=self.run / "sqlite", log_dir=self.run / "logs",
                final_message_path=self.run / "final.txt",
                hook_recorder_path=ROOT / "product/runtime/codex_hook_recorder.py",
            )
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()})
        self.assertFalse((self.run / "sqlite").exists())
        self.assertFalse((self.run / "logs").exists())

    def test_historical_prompt_commands_use_current_python_not_login_shell_path(self):
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

    def test_frozen_input_identity_gate_prompt_and_schema_drift_fail_closed(self):
        for relative in ("inputs/runtime_company_analyst.json", "invocations/runtime_company_analyst.json",
                         "evidence/gate.json", "prompts/runtime_company_analyst.txt"):
            with self.subTest(relative=relative):
                path = self.run / relative
                original = path.read_bytes()
                try:
                    if relative.startswith("prompts/"):
                        path.write_text("changed prompt")
                    else:
                        value = json.loads(original)
                        if relative.startswith("inputs/"):
                            value["allowed_evidence_ids"] = []
                        elif relative.startswith("invocations/"):
                            value["invocation_id"] = "foreign"
                        else:
                            value["allowed_evidence_ids"] = ["unknown"]
                        path.write_text(json.dumps(value))
                    changed = path.read_bytes()
                    with self.assertRaises(ValueError):
                        build_specialist_dispatch_message(ROOT, self.run, "runtime_company_analyst")
                    self.assertEqual(path.read_bytes(), changed)
                finally:
                    path.write_bytes(original)
        (self.run / "invocations/runtime_company_analyst.json").unlink()
        with self.assertRaises(FileNotFoundError):
            build_specialist_dispatch_message(ROOT, self.run, "runtime_company_analyst")

    def test_standalone_retired_hook_rejects_exact_and_bad_dispatch_without_state(self):
        before = {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        for message in (self.payload()["tool_input"]["message"], "inv_wrong，未提供证据集合"):
            payload = self.payload()
            payload["tool_input"]["message"] = message
            result = subprocess.run([sys.executable, "-B", str(ROOT / "product/runtime/codex_hook_recorder.py")],
                                    input=json.dumps(payload), text=True, capture_output=True,
                                    env={**os.environ, **self.env}, cwd=self.temp.name, timeout=10)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("NATIVE_HOST_EXECUTION_REQUIRED", result.stderr)
            self.assertEqual(result.stdout, "")
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()})
        self.assertFalse((self.run / "invocation").exists())
