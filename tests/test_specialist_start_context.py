"""冻结上下文交付接缝，合成事件不作为真实 LLM 验收证据。"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.hashing import canonical_hash
from product.runtime.invocation import (
    LEGACY_START_CONTEXT_VERSION as START_CONTEXT_VERSION,
    START_CONTEXT_VERSION as CURRENT_START_CONTEXT_VERSION,
    SPECIALIST_TASK_NAMES, build_specialist_dispatch_ticket,
    build_specialist_start_context, verify_specialist_start_binding,
)
from product.runtime.nested_codex import build_nested_codex_command
from product.runtime.run_package import prepare_run, prepare_cio
from tests.test_native_run_package import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
ANALYST = "runtime_company_analyst"


class SpecialistStartContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "run"
        prepare_run(ROOT, fixture_path=ROOT / "evals/fixtures/codex-native/normal-research.json",
                    run_dir=self.run, run_id="start-context-test", model="gpt-5.6-terra",
                    research_question="合成启动上下文接缝", authenticity_required=False)
        manifest = read_json(self.run / "run_manifest.json")
        manifest["specialist_context_delivery"] = START_CONTEXT_VERSION
        write_json(self.run / "run_manifest.json", manifest)
        self.configure_events()

    def configure_events(self):
        self.log = self.run / "invocation/subagent-events.jsonl"
        self.log.parent.mkdir(exist_ok=True)
        self.env = {"STOCK_AGENT_RUN_DIR": str(self.run),
                    "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(self.log),
                    "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(self.run / "invocation/subagent-dispatches.jsonl"),
                    "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": ",".join(SPECIALIST_TASK_NAMES),
                    "STOCK_AGENT_START_CONTEXT": START_CONTEXT_VERSION}
        (self.run / "invocation/codex-events.jsonl").write_text(
            json.dumps({"type": "thread.started", "thread_id": "parent-test"}) + "\n")

    def payload(self, agent=ANALYST):
        return {"hook_event_name": "SubagentStart", "session_id": "parent-test", "turn_id": "turn-test",
                "agent_id": "child-" + agent, "agent_type": agent,
                "model": "gpt-5.6-terra", "cwd": str(ROOT / "product")}

    def start(self, agent=ANALYST):
        return handle_hook_event(self.payload(agent), environ=self.env)

    def synthetic_authenticated_context(self):
        from tests.test_live_eval_contract import synthetic_run
        from product.runtime.live_context import load_live_run_context
        self.run = synthetic_run(Path(self.temp.name) / "live", stop_before_cio=True)
        self.configure_events()
        run = read_json(self.run / "run_manifest.json")
        run["authenticity_required"] = True
        run["specialist_context_delivery"] = START_CONTEXT_VERSION
        write_json(self.run / "run_manifest.json", run)
        # This old synthetic snapshot is not v4/live acceptance. Keep real hash,
        # identity and PIT checks, substituting only its synthetic admission mode.
        patched = patch("product.runtime.live_context.load_live_run_context",
                        side_effect=lambda path, manifest: load_live_run_context(
                            path, dict(manifest, authenticity_required=False)))
        patched.start()
        self.addCleanup(patched.stop)
        return run

    def use_current_contract(self):
        manifest = read_json(self.run / "run_manifest.json")
        manifest["specialist_context_delivery"] = CURRENT_START_CONTEXT_VERSION
        write_json(self.run / "run_manifest.json", manifest)
        self.env["STOCK_AGENT_START_CONTEXT"] = CURRENT_START_CONTEXT_VERSION

    def test_current_contract_accepts_rewording_but_rejects_wrong_isolation(self):
        self.use_current_contract()
        payload = {"hook_event_name": "PreToolUse", "session_id": "parent-test", "turn_id": "turn-test",
                   "tool_name": "spawn_agent", "tool_use_id": "call-test", "cwd": str(ROOT / "product"),
                   "tool_input": {"agent_type": ANALYST, "task_name": SPECIALIST_TASK_NAMES[ANALYST],
                                  "fork_turns": "none", "message": "请独立分析公司的业务、业绩与风险。"}}
        for field, value in (("task_name", "wrong-task"), ("fork_turns", "all")):
            bad = copy.deepcopy(payload)
            bad["tool_input"][field] = value
            self.assertEqual(handle_hook_event(bad, environ=self.env)[0]["decision"], "DENY_DISPATCH_CONTRACT")
        self.assertEqual(handle_hook_event(payload, environ=self.env)[0]["decision"], "ALLOW")

    def test_research_draft_schema_only_removes_technical_field(self):
        from product.runtime.invocation import build_specialist_dispatch_message
        before = json.loads(build_specialist_dispatch_message(ROOT, self.run, ANALYST))
        manifest = read_json(self.run / "run_manifest.json")
        manifest["specialist_output_delivery"] = "native-research-draft/1.0.0"
        write_json(self.run / "run_manifest.json", manifest)
        after = json.loads(build_specialist_dispatch_message(ROOT, self.run, ANALYST))
        expected = copy.deepcopy(before["output_schema"])
        expected["properties"].pop("skill_execution")
        expected["required"].remove("skill_execution")
        self.assertEqual(after["output_schema"], expected)
        self.assertEqual(after["agent_input"], before["agent_input"])
        self.assertEqual(after["invocation"], before["invocation"])
        self.assertNotIn("skill_execution", after["contract_checks"]["required_output_fields"])

    def test_current_contract_requires_real_binding_not_report_receipt(self):
        self.use_current_contract()
        context, binding = build_specialist_start_context(ROOT, self.run, ANALYST)
        self.assertNotIn("context_receipt", json.loads(context))
        self.assertNotIn("receipt", binding)
        with self.assertRaises((ValueError, OSError)):
            verify_specialist_start_binding(ROOT, self.run, ANALYST, report={"artifact_refs": []})
        self.start()
        proof = verify_specialist_start_binding(ROOT, self.run, ANALYST, report={"artifact_refs": []})
        self.assertEqual(proof["binding"]["contract_version"], CURRENT_START_CONTEXT_VERSION)

    def test_current_live_cio_accepts_reports_without_proof_hash(self):
        run = self.synthetic_authenticated_context()
        self.use_current_contract()
        for agent in SPECIALIST_TASK_NAMES:
            self.start(agent)
        result = prepare_cio(ROOT, run_dir=self.run, model=run["model"])
        self.assertNotEqual(result.get("terminal_state"), "FAILED_VALIDATION", result)
        self.assertTrue((self.run / "invocations/runtime_cio.json").exists())

    def test_current_live_parent_does_not_reread_specialist_packets(self):
        from product.runtime.smoke_prompt import build_smoke_prompt
        self.synthetic_authenticated_context()
        self.use_current_contract()
        prompt = build_smoke_prompt(self.run, repository_root=ROOT, defer_deterministic_finalize=True)
        preparation = prompt.split("\n1. ", 1)[1].split("\n2. ", 1)[0]
        for path in ("run_manifest.json", "evidence/gate.json", "inputs/runtime_company_analyst.json",
                     "inputs/runtime_skeptic.json", "invocations/*.json"):
            self.assertNotIn(path, preparation)
        self.assertIn("prepare-cio", preparation)
        self.assertIn("inputs/runtime_cio.json", prompt)

    def test_full_context_and_receipt_bind_both_independent_roles(self):
        receipts = []
        for agent in SPECIALIST_TASK_NAMES:
            context, binding = build_specialist_start_context(ROOT, self.run, agent)
            record, response = self.start(agent)
            self.assertEqual(response["hookSpecificOutput"]["additionalContext"], context)
            self.assertEqual(record["context_binding"], binding)
            packet = json.loads(context)
            self.assertNotIn("validated_reports", packet["frozen_input"]["agent_input"])
            receipts.append(binding["receipt"])
            proof = verify_specialist_start_binding(ROOT, self.run, agent,
                report={"artifact_refs": [binding["receipt"]]})
            self.assertEqual(proof["child_session_id"], "child-" + agent)
        self.assertEqual(len(set(receipts)), 2)
        self.assertFalse((self.run / "invocation/subagent-dispatches.jsonl").exists())

    def test_standalone_product_cwd_emits_full_context_without_model(self):
        expected, _ = build_specialist_start_context(ROOT, self.run, ANALYST)
        result = subprocess.run([sys.executable, "-B", str(ROOT / "product/runtime/codex_hook_recorder.py")],
            input=json.dumps(self.payload()), text=True, capture_output=True,
            cwd=ROOT / "product", env={**os.environ, **self.env}, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"], expected)
        verify_specialist_start_binding(ROOT, self.run, ANALYST)

    def test_oversize_context_is_failed_not_truncated(self):
        with patch("product.runtime.invocation.MAX_START_CONTEXT_BYTES", 10):
            with self.assertRaisesRegex(ValueError, "START_CONTEXT_TOO_LARGE"):
                build_specialist_dispatch_ticket(ROOT, self.run, ANALYST)
            record, response = self.start()
        self.assertEqual(record["context_binding"]["failure_code"], "START_CONTEXT_TOO_LARGE")
        self.assertNotIn("frozen_input", response["hookSpecificOutput"]["additionalContext"])
        self.assertNotIn("continue", response)  # Does not claim to prevent startup.

    def test_launcher_disables_truncation_only_for_bounded_start_handler(self):
        command = build_nested_codex_command(codex_binary="codex", product_root=ROOT / "product",
            run_dir=self.run, model="gpt-5.6-terra", sqlite_home=self.run / "sqlite",
            log_dir=self.run / "logs", final_message_path=self.run / "final.txt",
            hook_recorder_path=ROOT / "product/runtime/codex_hook_recorder.py")
        start = tomllib.loads(next(x for x in command if x.startswith("hooks.SubagentStart=")))
        handler = start["hooks"]["SubagentStart"][0]["hooks"][0]
        self.assertEqual(handler["additionalContextLimit"], 0)
        stop = tomllib.loads(next(x for x in command if x.startswith("hooks.SubagentStop=")))
        self.assertNotIn("additionalContextLimit", stop["hooks"]["SubagentStop"][0]["hooks"][0])

    def test_missing_event_or_receipt_fails(self):
        self.log.write_text("")
        with self.assertRaisesRegex(ValueError, "START_CONTEXT_EVENT_COUNT_INVALID"):
            verify_specialist_start_binding(ROOT, self.run, ANALYST)
        self.start()
        with self.assertRaisesRegex(ValueError, "START_CONTEXT_RECEIPT_MISSING"):
            verify_specialist_start_binding(ROOT, self.run, ANALYST, report={"artifact_refs": []})

    def test_rehashed_event_mutations_still_fail(self):
        original, _ = self.start()
        for mutation in ("parent", "model", "input_hash", "prompt_hash", "schema_hash", "receipt", "event_hash"):
            with self.subTest(mutation=mutation):
                event = copy.deepcopy(original)
                if mutation in ("parent", "model"):
                    event["parent_session_id" if mutation == "parent" else "model"] = "wrong"
                elif mutation != "event_hash":
                    event["context_binding"][mutation] = "wrong"
                event.pop("event_hash")
                event["event_hash"] = "wrong" if mutation == "event_hash" else canonical_hash(event)
                self.log.write_text(json.dumps(event) + "\n")
                with self.assertRaisesRegex(ValueError, "START_CONTEXT_BINDING_MISMATCH"):
                    verify_specialist_start_binding(ROOT, self.run, ANALYST)

    def test_duplicate_role_or_child_and_wrong_model_fail(self):
        first, _ = self.start()
        duplicate, _ = self.start()
        self.assertEqual(duplicate["context_binding"]["failure_code"], "START_CONTEXT_DUPLICATE_AGENT")
        with self.assertRaisesRegex(ValueError, "START_CONTEXT_SESSION_INVALID"):
            verify_specialist_start_binding(ROOT, self.run, ANALYST)
        duplicate["child_session_id"] = "different-child"
        self.log.write_text(json.dumps(first) + "\n" + json.dumps(duplicate) + "\n")
        with self.assertRaisesRegex(ValueError, "START_CONTEXT_EVENT_COUNT_INVALID"):
            verify_specialist_start_binding(ROOT, self.run, ANALYST)
        self.log.write_text("")
        payload = self.payload()
        payload["model"] = "wrong-model"
        self.assertEqual(handle_hook_event(payload, environ=self.env)[0]["context_binding"]["failure_code"],
                         "START_CONTEXT_MODEL_MISMATCH")

    def test_frozen_file_drift_is_rejected(self):
        self.start()
        for relative in ("inputs/runtime_company_analyst.json", "prompts/runtime_company_analyst.txt",
                         "schemas/runtime_company_analyst.output.schema.json"):
            # Resolve the schema from the actual invocation rather than assuming a filename.
            path = self.run / relative
            if relative.startswith("schemas/"):
                path = Path(read_json(self.run / "invocations/runtime_company_analyst.json")["output_schema"])
            original = path.read_bytes()
            try:
                path.write_bytes(b"{}")
                with self.assertRaises((ValueError, KeyError)):
                    verify_specialist_start_binding(ROOT, self.run, ANALYST)
            finally:
                path.write_bytes(original)

    def test_pre_tool_hook_accepts_ticket_and_rejects_replaced_ticket(self):
        payload = {"hook_event_name": "PreToolUse", "session_id": "parent-test", "turn_id": "turn-test",
                   "tool_name": "spawn_agent", "tool_use_id": "call-test", "cwd": str(ROOT / "product"),
                   "tool_input": {"agent_type": ANALYST, "task_name": SPECIALIST_TASK_NAMES[ANALYST],
                                  "fork_turns": "none", "message": build_specialist_dispatch_ticket(ROOT, self.run, ANALYST)}}
        original = copy.deepcopy(payload)
        payload["tool_input"]["message"] += " changed"
        self.assertEqual(handle_hook_event(payload, environ=self.env)[0]["decision"], "DENY_DISPATCH_CONTRACT")
        self.assertEqual(handle_hook_event(original, environ=self.env)[0]["decision"], "ALLOW")

    def test_live_cio_rejects_missing_receipt_before_synthesis(self):
        run = self.synthetic_authenticated_context()
        for agent in SPECIALIST_TASK_NAMES:
            self.start(agent)
        result = prepare_cio(ROOT, run_dir=self.run, model=run["model"])
        self.assertEqual(result["terminal_state"], "FAILED_VALIDATION")
        self.assertIn("START_CONTEXT_RECEIPT_MISSING", json.dumps(read_json(self.run / "run_error.json")))
        self.assertFalse((self.run / "decision.json").exists())

    def test_live_mcp_checks_binding_before_returning_evidence(self):
        from product.runtime.live_mcp import StatelessLiveTools
        run = self.synthetic_authenticated_context()
        invocation = read_json(self.run / "invocations/runtime_company_analyst.json")
        arguments = {"run_dir": str(self.run), "run_id": run["run_id"], "agent": ANALYST,
                     "invocation_id": invocation["invocation_id"]}
        with self.assertRaises((OSError, ValueError)):
            StatelessLiveTools()._bound_tools(**arguments)
        self.start()
        self.assertIsNotNone(StatelessLiveTools()._bound_tools(**arguments))

    def test_completion_recomputes_start_binding_without_pre_tool_allow(self):
        from product.runtime.nested_codex import _completion_checks
        self.synthetic_authenticated_context()
        children = {}
        for agent in SPECIALIST_TASK_NAMES:
            record, _ = self.start(agent)
            report = read_json(self.run / f"agents/{agent}.json")
            report["artifact_refs"].append(record["context_binding"]["receipt"])
            write_json(self.run / f"agents/{agent}.json", report)
            children[agent] = {"start_context_binding": verify_specialist_start_binding(
                ROOT, self.run, agent, report=report)}
        write_json(self.run / "invocation/environment-manifest.json", {"repo_root": str(ROOT)})
        proof = {"children": children}
        proof_path = self.run / "events/codex/specialist-execution-proof.json"
        write_json(proof_path, proof)
        checks, _ = _completion_checks(self.run)
        self.assertTrue(checks["dispatch_guard_active"])
        self.assertEqual(checks["dispatch_guard_method"], "START_CONTEXT_REVALIDATED")
        self.assertEqual(checks["pre_dispatch_blocking"], "NOT_GUARANTEED")
        self.assertFalse((self.run / "invocation/subagent-dispatches.jsonl").exists())
        proof["children"][ANALYST]["start_context_binding"]["binding"]["input_hash"] = "tampered"
        write_json(proof_path, proof)
        self.assertFalse(_completion_checks(self.run)[0]["dispatch_guard_active"])

    def test_live_gate_drift_never_delivers_context(self):
        self.synthetic_authenticated_context()
        path = self.run / "evidence/gate.json"
        gate = read_json(path)
        gate["allowed_evidence_ids"].append("future-unapproved")
        write_json(path, gate)
        record, response = self.start()
        self.assertEqual(record["context_binding"]["status"], "FAILED")
        self.assertNotIn("frozen_input", response["hookSpecificOutput"]["additionalContext"])
