"""冻结上下文业务与显式历史Start读取；合成事件不是当前宿主执行证据。"""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
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
from product.runtime.run_package import prepare_run, prepare_live_run
from tests.test_native_run_package import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
ANALYST = "runtime_company_analyst"


class SpecialistStartContextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "run"
        result = prepare_run(ROOT, fixture_path=ROOT / "evals/fixtures/codex-native/normal-research.json",
                             run_dir=self.run, run_id="start-context-test", model="gpt-6-luna",
                             research_question="合成冻结上下文接缝", authenticity_required=False)
        self.assertTrue((self.run / "run_manifest.json").is_file(), result)
        manifest = read_json(self.run / "run_manifest.json")
        manifest["specialist_context_delivery"] = START_CONTEXT_VERSION
        write_json(self.run / "run_manifest.json", manifest)
        self.configure_history_paths()

    def configure_history_paths(self):
        self.log = self.run / "invocation/subagent-events.jsonl"
        self.env = {"STOCK_AGENT_RUN_DIR": str(self.run),
                    "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(self.log),
                    "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(self.run / "invocation/subagent-dispatches.jsonl"),
                    "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": ",".join(SPECIALIST_TASK_NAMES),
                    "STOCK_AGENT_START_CONTEXT": START_CONTEXT_VERSION}

    def payload(self, agent=ANALYST):
        return {"hook_event_name": "SubagentStart", "session_id": "parent-test", "turn_id": "turn-test",
                "agent_id": "child-" + agent, "agent_type": agent,
                "model": read_json(self.run / "run_manifest.json")["model"], "cwd": str(ROOT / "product")}

    def write_historical_start_fixture(self, agent=ANALYST):
        """只为历史verifier写合成向量；不调用Hook或生成当前接受/执行证明。"""
        _, binding = build_specialist_start_context(ROOT, self.run, agent)
        event = {"hook_event_name": "SubagentStart", "parent_session_id": "parent-test",
                 "child_session_id": "child-" + agent, "agent_type": agent,
                 "model": binding["model"], "context_binding": binding}
        event["event_hash"] = canonical_hash(event)
        self.log.parent.mkdir(exist_ok=True)
        with self.log.open("a") as stream:
            stream.write(json.dumps(event) + "\n")
        (self.run / "invocation/codex-events.jsonl").write_text(
            json.dumps({"type": "thread.started", "thread_id": "parent-test"}) + "\n")
        return event

    def historical_live_context(self):
        from tests.test_live_eval_contract import synthetic_run
        from product.runtime.live_context import load_live_run_context
        self.run = synthetic_run(Path(self.temp.name) / "historical-live", stop_before_cio=True)
        self.configure_history_paths()
        run = read_json(self.run / "run_manifest.json")
        run["authenticity_required"] = True
        run["specialist_context_delivery"] = START_CONTEXT_VERSION
        write_json(self.run / "run_manifest.json", run)
        # 旧合成快照不是v4/live准入；仅用原模式复核历史hash、身份、PIT和Start绑定。
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

    def test_retired_hook_never_delivers_context_or_grants_dispatch(self):
        self.use_current_contract()
        before = {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        for event_name in ("PreToolUse", "SubagentStart", "SubagentStop", "Stop"):
            with self.subTest(event=event_name), self.assertRaisesRegex(ValueError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                handle_hook_event({**self.payload(), "hook_event_name": event_name}, environ=self.env)
        self.assertFalse((self.run / "invocation").exists())
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()})

    def test_semantic_draft_uses_authoritative_schema_and_rejects_protocol_downgrade(self):
        from product.runtime.invocation import build_specialist_dispatch_message, specialist_semantic_schema
        before = json.loads(build_specialist_dispatch_message(ROOT, self.run, ANALYST))
        formal = read_json(Path(before["invocation"]["output_schema"]))
        self.assertEqual(before["output_schema"], specialist_semantic_schema(formal))
        for key in ("run_id", "invocation_id", "agent", "skill_execution", "artifact_refs"):
            self.assertNotIn(key, before["output_schema"]["properties"])
        manifest = read_json(self.run / "run_manifest.json")
        manifest["specialist_output_delivery"] = "native-research-draft/1.0.0"
        write_json(self.run / "run_manifest.json", manifest)
        with self.assertRaisesRegex(ValueError, "SPECIALIST_SEMANTIC_PROTOCOL_BINDING_INVALID"):
            build_specialist_dispatch_message(ROOT, self.run, ANALYST)

    def test_receipt_free_historical_contract_requires_binding_not_report_receipt(self):
        self.use_current_contract()
        context, binding = build_specialist_start_context(ROOT, self.run, ANALYST)
        self.assertNotIn("context_receipt", json.loads(context))
        self.assertNotIn("receipt", binding)
        with self.assertRaises((ValueError, OSError)):
            verify_specialist_start_binding(ROOT, self.run, ANALYST, report={"artifact_refs": []})
        self.write_historical_start_fixture()
        proof = verify_specialist_start_binding(ROOT, self.run, ANALYST, report={"artifact_refs": []})
        self.assertEqual(proof["binding"]["contract_version"], CURRENT_START_CONTEXT_VERSION)

    def test_historical_binding_cannot_restore_retired_live_prepare_entry(self):
        self.use_current_contract()
        for agent in SPECIALIST_TASK_NAMES:
            self.write_historical_start_fixture(agent)
        before = {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        target = Path(self.temp.name) / "forbidden-live"
        with self.assertRaisesRegex(ValueError, "LIVE_COUNCIL_ENTRY_RETIRED"):
            prepare_live_run(ROOT, portfolio_path=self.run / "portfolio.json",
                             snapshot_path=self.run / "snapshot.json", cache_root=self.run / "cache",
                             calendar=None, run_dir=target, run_id="forbidden-live", model="gpt-6-luna")
        self.assertFalse(target.exists())
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()})

    def test_historical_context_and_receipt_bind_both_independent_roles(self):
        receipts = []
        for agent in SPECIALIST_TASK_NAMES:
            context, binding = build_specialist_start_context(ROOT, self.run, agent)
            event = self.write_historical_start_fixture(agent)
            self.assertEqual(event["context_binding"], binding)
            self.assertNotIn("validated_reports", json.loads(context)["frozen_input"]["agent_input"])
            receipts.append(binding["receipt"])
            before = self.log.read_bytes()
            proof = verify_specialist_start_binding(ROOT, self.run, agent,
                                                    report={"artifact_refs": [binding["receipt"]]})
            self.assertEqual(proof["child_session_id"], "child-" + agent)
            self.assertEqual(self.log.read_bytes(), before)
        self.assertEqual(len(set(receipts)), 2)
        self.assertFalse((self.run / "invocation/subagent-dispatches.jsonl").exists())

    def test_standalone_product_cwd_rejects_normal_start_without_context_or_state(self):
        result = subprocess.run([sys.executable, "-B", str(ROOT / "product/runtime/codex_hook_recorder.py")],
            input=json.dumps(self.payload()), text=True, capture_output=True,
            cwd=ROOT / "product", env={**os.environ, **self.env}, timeout=15)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("NATIVE_HOST_EXECUTION_REQUIRED", result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertFalse((self.run / "invocation").exists())

    def test_oversize_frozen_context_fails_without_truncation_or_state(self):
        before = {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        with patch("product.runtime.invocation.MAX_START_CONTEXT_BYTES", 10):
            with self.assertRaisesRegex(ValueError, "START_CONTEXT_TOO_LARGE"):
                build_specialist_dispatch_ticket(ROOT, self.run, ANALYST)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()})

    def test_missing_historical_event_or_receipt_fails(self):
        self.log.parent.mkdir()
        self.log.write_text("")
        with self.assertRaisesRegex(ValueError, "START_CONTEXT_EVENT_COUNT_INVALID"):
            verify_specialist_start_binding(ROOT, self.run, ANALYST, parent_session_id="parent-test")
        self.write_historical_start_fixture()
        with self.assertRaisesRegex(ValueError, "START_CONTEXT_RECEIPT_MISSING"):
            verify_specialist_start_binding(ROOT, self.run, ANALYST, report={"artifact_refs": []})

    def test_resigned_historical_event_mutations_still_fail(self):
        original = self.write_historical_start_fixture()
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
                before = self.log.read_bytes()
                with self.assertRaisesRegex(ValueError, "START_CONTEXT_BINDING_MISMATCH"):
                    verify_specialist_start_binding(ROOT, self.run, ANALYST)
                self.assertEqual(self.log.read_bytes(), before)

    def test_historical_duplicate_role_child_and_wrong_model_fail(self):
        first = self.write_historical_start_fixture()
        self.log.write_text(json.dumps(first) + "\n" + json.dumps(first) + "\n")
        with self.assertRaisesRegex(ValueError, "START_CONTEXT_SESSION_INVALID"):
            verify_specialist_start_binding(ROOT, self.run, ANALYST)
        duplicate = {**first, "child_session_id": "different-child"}
        self.log.write_text(json.dumps(first) + "\n" + json.dumps(duplicate) + "\n")
        with self.assertRaisesRegex(ValueError, "START_CONTEXT_EVENT_COUNT_INVALID"):
            verify_specialist_start_binding(ROOT, self.run, ANALYST)
        wrong = {**first, "model": "wrong-model"}
        wrong["event_hash"] = canonical_hash({k: v for k, v in wrong.items() if k != "event_hash"})
        self.log.write_text(json.dumps(wrong) + "\n")
        with self.assertRaisesRegex(ValueError, "START_CONTEXT_BINDING_MISMATCH"):
            verify_specialist_start_binding(ROOT, self.run, ANALYST)

    def test_frozen_file_drift_is_rejected(self):
        self.write_historical_start_fixture()
        schema = Path(read_json(self.run / "invocations/runtime_company_analyst.json")["output_schema"])
        for path in (self.run / "inputs/runtime_company_analyst.json",
                     self.run / "prompts/runtime_company_analyst.txt", schema):
            original = path.read_bytes()
            try:
                path.write_bytes(b"{}")
                with self.assertRaises((ValueError, KeyError)):
                    verify_specialist_start_binding(ROOT, self.run, ANALYST)
                self.assertEqual(path.read_bytes(), b"{}")
            finally:
                path.write_bytes(original)

    def test_historical_live_mcp_checks_start_binding_before_returning_evidence(self):
        from product.runtime.live_mcp import StatelessLiveTools
        run = self.historical_live_context()
        invocation = read_json(self.run / "invocations/runtime_company_analyst.json")
        arguments = {"run_dir": str(self.run), "run_id": run["run_id"], "agent": ANALYST,
                     "invocation_id": invocation["invocation_id"]}
        with self.assertRaises((OSError, ValueError)):
            StatelessLiveTools()._bound_tools(**arguments)
        self.write_historical_start_fixture()
        self.assertIsNotNone(StatelessLiveTools()._bound_tools(**arguments))

    def test_historical_live_gate_drift_cannot_build_frozen_context(self):
        self.historical_live_context()
        path = self.run / "evidence/gate.json"
        gate = read_json(path)
        gate["allowed_evidence_ids"].append("future-unapproved")
        write_json(path, gate)
        before = {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()}
        with self.assertRaises(ValueError):
            build_specialist_start_context(ROOT, self.run, ANALYST)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.run.rglob("*") if p.is_file()})
