"""当前 fixture Council 的实际 Hook/MCP 接缝；事件为测试输入，不是 LLM 证明。"""
from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.fixture_mcp import serve_stdio
from product.runtime.execution_proof import build_ephemeral_run_specialist_execution_proof, ExecutionProofError
from product.runtime.hashing import canonical_hash, file_hash
from product.runtime.invocation import (
    SPECIALIST_AGENTS, SPECIALIST_SEMANTIC_DRAFT, SPECIALIST_TASK_NAMES,
    SPECIALIST_TECHNICAL_FIELDS, START_CONTEXT_VERSION, build_specialist_dispatch_message,
)
from product.runtime.nested_codex import launch_nested_codex
from product.runtime.run_package import prepare_cio, prepare_run
from product.runtime.schema_validation import validate_schema_instance
from product.runtime.smoke_prompt import build_smoke_prompt
from product.runtime.validation import validate_company_report, validate_skeptic_report
from tests.test_native_run_package import ROOT, FIXTURES, read_json, specialist_outputs, write_json
from tests.test_agents_instruction_proof import bind_instruction_fixture


def start_council_specialists(run):
    """执行真实 Hook 函数，模拟两个独立生命周期；不调用模型或 launcher。"""
    env = {
        "STOCK_AGENT_RUN_DIR": str(run),
        "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(run / "invocation/subagent-events.jsonl"),
        "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(run / "invocation/subagent-dispatches.jsonl"),
        "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": ",".join(sorted(SPECIALIST_AGENTS)),
        "STOCK_AGENT_START_CONTEXT": START_CONTEXT_VERSION,
        "STOCK_AGENT_CAPTURE_SPECIALIST_OUTPUT": SPECIALIST_SEMANTIC_DRAFT,
    }
    starts, packets = {}, {}
    for agent in sorted(SPECIALIST_AGENTS):
        record, _ = handle_hook_event({
            "hook_event_name": "PreToolUse", "session_id": "fixture-parent", "turn_id": "fixture-turn",
            "tool_name": "spawn_agent", "tool_use_id": "spawn-" + agent,
            "cwd": str(ROOT / "product"), "model": "gpt-6-luna", "permission_mode": "workspace-write",
            "tool_input": {"agent_type": agent, "task_name": SPECIALIST_TASK_NAMES[agent],
                           "fork_turns": "none", "message": "按冻结上下文开展当前研究。"},
        }, environ=env)
        if record["decision"] != "ALLOW":
            raise AssertionError(record)
    for agent in sorted(SPECIALIST_AGENTS):
        start = {
            "hook_event_name": "SubagentStart", "session_id": "fixture-parent", "turn_id": "fixture-turn",
            "agent_id": "child-" + agent, "agent_type": agent, "model": "gpt-6-luna",
            "cwd": str(ROOT / "product"), "permission_mode": "read-only",
        }
        record, response = handle_hook_event(start, environ=env)
        if record["context_binding"]["status"] != "EMITTED":
            raise AssertionError(record)
        starts[agent] = start
        packets[agent] = json.loads(response["hookSpecificOutput"]["additionalContext"])["frozen_input"]
    # 只用于消费者定位父会话，不能被当作真实 Codex 执行证明。
    (run / "invocation/codex-events.jsonl").write_text(
        json.dumps({"type": "thread.started", "thread_id": "fixture-parent"}) + "\n", encoding="utf-8",
    )
    return env, starts, packets


class CouncilSemanticHandoffTests(unittest.TestCase):
    def prepare(self, root):
        run = Path(root) / "run"
        prepare_run(ROOT, fixture_path=FIXTURES / "normal-research.json", run_dir=run,
                    run_id="semantic-fixture", model="gpt-6-luna", research_question="测试研究交接。")
        env, starts, packets = start_council_specialists(run)
        drafts = {agent: {key: value for key, value in report.items() if key not in SPECIALIST_TECHNICAL_FIELDS}
                  for agent, report in specialist_outputs(run, persist=False).items()}
        return run, env, starts, packets, drafts

    def stop(self, env, start, draft):
        return handle_hook_event({**start, "hook_event_name": "SubagentStop", "stop_hook_active": False,
                                  "last_assistant_message": json.dumps(draft, ensure_ascii=False)}, environ=env)

    def query(self, run, agent, ids):
        invocation = read_json(run / f"invocations/{agent}.json")
        request = {"id": 1, "method": "tools/call", "params": {"name": "query", "arguments": {
            "run_dir": str(run), "run_id": invocation["run_id"], "agent": agent,
            "invocation_id": invocation["invocation_id"], "evidence_ids": ids,
        }}}
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(request) + "\n")), patch("sys.stdout", output):
            serve_stdio(stateless=True, event_log=run / "events/mcp/events.jsonl")
        return json.loads(output.getvalue())

    def test_actual_hooks_query_capture_and_cio_consumer_preserve_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            run, env, starts, packets, drafts = self.prepare(directory)
            original = copy.deepcopy(drafts)
            hashes = {}
            for agent in sorted(SPECIALIST_AGENTS):
                packet = packets[agent]
                self.assertTrue(SPECIALIST_TECHNICAL_FIELDS.isdisjoint(packet["output_schema"]["properties"]))
                validate_schema_instance(drafts[agent], packet["output_schema"])
                self.assertNotIn("error", self.query(run, agent, packet["agent_input"]["allowed_evidence_ids"]))
                record, _ = self.stop(env, starts[agent], drafts[agent])
                self.assertEqual(record["output_capture"]["status"], "SAVED", record)
                report = read_json(run / f"agents/{agent}.json")
                invocation = read_json(run / f"invocations/{agent}.json")
                validator = validate_company_report if agent == "runtime_company_analyst" else validate_skeptic_report
                validator(report, run_id=invocation["run_id"], manifest=invocation)
                for key, value in drafts[agent].items():
                    self.assertEqual(report[key], value)
                self.assertEqual(report["skill_execution"], invocation["skill_execution"])
                self.assertEqual(read_json(run / f"agents/{agent}.native.json"), drafts[agent])
                self.assertEqual(record["output_capture"]["raw_output_hash"], canonical_hash(drafts[agent]))
                hashes[agent] = file_hash(run / f"agents/{agent}.json")
            result = prepare_cio(ROOT, run_dir=run, model="gpt-6-luna")
            self.assertEqual(result["next_state"], "CIO_SYNTHESIS_REQUIRED", result)
            cio = read_json(run / "inputs/runtime_cio.json")
            self.assertEqual(len(cio["report_catalog"]), 2)
            for agent in SPECIALIST_AGENTS:
                self.assertEqual(hashes[agent], file_hash(run / f"agents/{agent}.json"))
            self.assertEqual(drafts, original)
            self.assertNotIn("claims", packets["runtime_skeptic"]["agent_input"])
            self.assertNotIn("company_reports", packets["runtime_skeptic"]["agent_input"])

    def test_reference_pollution_and_unknown_ids_are_rejected_without_correction(self):
        for agent in sorted(SPECIALIST_AGENTS):
            for evidence_id in ("ev-normal-revenue|fixture", "ev-normal-revenue|as_of=now", "ev-unknown"):
                with self.subTest(agent=agent, evidence=evidence_id), tempfile.TemporaryDirectory() as directory:
                    run, env, starts, _, drafts = self.prepare(directory)
                    draft = drafts[agent]
                    field = "claims" if agent == "runtime_company_analyst" else "challenges"
                    draft[field][0]["evidence_refs"] = [evidence_id]
                    original = copy.deepcopy(draft)
                    record, _ = self.stop(env, starts[agent], draft)
                    self.assertEqual(record["output_capture"]["status"], "FAILED", record)
                    self.assertFalse((run / f"agents/{agent}.json").exists())
                    self.assertEqual(draft, original)

    def test_technical_echo_wrong_model_and_cross_child_are_rejected(self):
        cases = [{"draft": {"run_id": "foreign"}}, {"draft": {"artifact_refs": []}},
                 {"payload": {"model": "wrong"}}, {"payload": {"agent_id": "other-child"}}]
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as directory:
                run, env, starts, _, drafts = self.prepare(directory)
                agent = "runtime_company_analyst"
                start = {**starts[agent], **case.get("payload", {})}
                record, _ = self.stop(env, start, {**drafts[agent], **case.get("draft", {})})
                self.assertEqual(record["output_capture"]["status"], "FAILED", record)
                self.assertFalse((run / f"agents/{agent}.json").exists())

    def test_multiple_authorized_refs_preserve_selection_and_order(self):
        with tempfile.TemporaryDirectory() as directory:
            run, env, starts, packets, drafts = self.prepare(directory)
            agent = "runtime_company_analyst"
            selected = packets[agent]["agent_input"]["allowed_evidence_ids"][:2]
            self.assertEqual(len(selected), 2)
            drafts[agent]["claims"][0]["evidence_refs"] = selected
            self.assertNotIn("error", self.query(run, agent, selected))
            record, _ = self.stop(env, starts[agent], drafts[agent])
            self.assertEqual(record["output_capture"]["status"], "SAVED", record)
            self.assertEqual(read_json(run / f"agents/{agent}.json")["claims"][0]["evidence_refs"], selected)

    def test_missing_start_and_escaping_output_directory_fail_closed(self):
        for tamper in ("start", "path"):
            with self.subTest(tamper=tamper), tempfile.TemporaryDirectory() as directory:
                run, env, starts, _, drafts = self.prepare(directory)
                agent = "runtime_company_analyst"
                if tamper == "start":
                    path = run / "invocation/subagent-events.jsonl"
                    records = [json.loads(line) for line in path.read_text().splitlines()]
                    path.write_text("".join(json.dumps(item) + "\n" for item in records
                                            if item["agent_type"] != agent), encoding="utf-8")
                    start = {**starts[agent], "stop_hook_active": True}
                    # 第二次 Stop 不再停在并行 barrier，但仍必须通过身份验证。
                    record, _ = handle_hook_event({**start, "hook_event_name": "SubagentStop",
                        "last_assistant_message": json.dumps(drafts[agent])}, environ=env)
                else:
                    outside = Path(directory) / "outside"
                    outside.mkdir()
                    (run / "agents").symlink_to(outside, target_is_directory=True)
                    record, _ = self.stop(env, starts[agent], drafts[agent])
                    self.assertEqual(list(outside.iterdir()), [])
                self.assertEqual(record["output_capture"]["status"], "FAILED", record)
                self.assertFalse((run / f"agents/{agent}.json").exists())

    def test_missing_or_tampered_dispatch_does_not_bind_a_valid_draft(self):
        for tamper in ("missing", "hash", "input"):
            with self.subTest(tamper=tamper), tempfile.TemporaryDirectory() as directory:
                run, env, starts, _, drafts = self.prepare(directory)
                path = run / "invocation/subagent-dispatches.jsonl"
                records = [json.loads(line) for line in path.read_text().splitlines()]
                target = next(item for item in records if item["agent_type"] == "runtime_company_analyst")
                if tamper == "missing":
                    records.remove(target)
                elif tamper == "hash":
                    target["event_hash"] = "0" * 64
                else:
                    target["dispatch_binding"]["input_hash"] = "0" * 64
                    target["event_hash"] = canonical_hash({k: v for k, v in target.items() if k != "event_hash"})
                path.write_text("".join(json.dumps(item) + "\n" for item in records), encoding="utf-8")
                agent = "runtime_company_analyst"
                record, _ = self.stop(env, starts[agent], drafts[agent])
                self.assertEqual(record["output_capture"]["status"], "FAILED", record)
                self.assertIn("SPECIALIST_STOP_DISPATCH_BINDING_INVALID", record["output_capture"]["failure_code"])
                self.assertFalse((run / f"agents/{agent}.json").exists())

    def test_protocol_downgrade_or_unknown_does_not_fall_back(self):
        for value in (None, "native-research-draft/1.0.0", "unknown"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                run, _, _, _, _ = self.prepare(directory)
                manifest = read_json(run / "run_manifest.json")
                manifest["specialist_output_delivery"] = value
                write_json(run / "run_manifest.json", manifest)
                with self.assertRaisesRegex(ValueError, "SPECIALIST_.*PROTOCOL"):
                    build_specialist_dispatch_message(ROOT, run, "runtime_company_analyst")

    def test_pre_agent_safe_termination_keeps_current_protocol_without_specialist_inputs(self):
        for fixture in ("invalid-portfolio.json", "future-or-stale.json"):
            with self.subTest(fixture=fixture), tempfile.TemporaryDirectory() as directory:
                run = Path(directory) / "safe-run"
                result = prepare_run(ROOT, fixture_path=FIXTURES / fixture, run_dir=run,
                                     run_id="safe-test", model="gpt-6-luna", research_question="输入安全终止测试。")
                self.assertEqual(result["next_state"], "SAFE_NO_TRADE")
                manifest = read_json(run / "run_manifest.json")
                self.assertEqual(manifest["specialist_context_delivery"], START_CONTEXT_VERSION)
                self.assertEqual(manifest["specialist_output_delivery"], SPECIALIST_SEMANTIC_DRAFT)
                self.assertFalse((run / "invocations").exists())
                self.assertFalse((run / "agents").exists())
                self.assertEqual(read_json(run / "decision_trace.json")["agents"], [])
                prompt = build_smoke_prompt(run, repository_root=ROOT)
                self.assertNotIn("spawn_agent", prompt)

    def test_capture_is_idempotent_and_never_overwrites_a_different_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            run, env, starts, _, drafts = self.prepare(directory)
            agent = "runtime_company_analyst"
            for _ in range(2):
                record, _ = self.stop(env, starts[agent], drafts[agent])
                self.assertEqual(record["output_capture"]["status"], "SAVED", record)
            before = file_hash(run / f"agents/{agent}.json")
            record, _ = self.stop(env, starts[agent], {**drafts[agent], "scope": "different"})
            self.assertIn("OUTPUT_EXISTS", record["output_capture"]["failure_code"])
            self.assertEqual(before, file_hash(run / f"agents/{agent}.json"))

    def test_current_proof_reader_recomputes_native_envelope_and_rejects_raw_tampering(self):
        for tamper in (False, True):
            with self.subTest(tamper=tamper), tempfile.TemporaryDirectory() as directory:
                run, env, starts, packets, drafts = self.prepare(directory)
                for agent in sorted(SPECIALIST_AGENTS):
                    self.assertNotIn("error", self.query(run, agent, packets[agent]["agent_input"]["allowed_evidence_ids"]))
                    record, _ = self.stop(env, starts[agent], drafts[agent])
                    self.assertEqual(record["output_capture"]["status"], "SAVED", record)
                prompt = run / "invocation/prompt.txt"
                prompt.write_text(build_smoke_prompt(run, repository_root=ROOT), encoding="utf-8")
                skill = ROOT / "product/skills/portfolio-council/SKILL.md"
                events = run / "invocation/codex-events.jsonl"
                # 合成遥测仅用于验证读取器，不是本次真实运行证据。
                with events.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps({"type": "item.completed", "item": {
                        "type": "command_execution", "command": f"cat '{skill}'", "exit_code": 0,
                        "aggregated_output": skill.read_text(encoding="utf-8"),
                    }}) + "\n")
                    stream.write(json.dumps({"type": "turn.completed", "usage": {
                        "input_tokens": 100, "output_tokens": 10, "cached_input_tokens": 0,
                    }}) + "\n")
                bind_instruction_fixture(ROOT, run)
                if tamper:
                    path = run / "agents/runtime_company_analyst.native.json"
                    draft = read_json(path)
                    draft["confidence"] = "wrong-type"
                    write_json(path, draft)
                arguments = dict(run_dir=run, codex_events_path=events,
                                 hook_events_path=run / "invocation/subagent-events.jsonl", latency_ms=1)
                if tamper:
                    with self.assertRaisesRegex(ExecutionProofError, "SPECIALIST_NATIVE_ENVELOPE_INVALID"):
                        build_ephemeral_run_specialist_execution_proof(ROOT, **arguments)
                    self.assertFalse((run / "events/codex/specialist-execution-proof.json").exists())
                else:
                    result = build_ephemeral_run_specialist_execution_proof(ROOT, **arguments)
                    self.assertEqual(result["next_state"], "EXECUTION_PROOF_VERIFIED")
                    proof = read_json(run / "events/codex/specialist-execution-proof.json")
                    for agent, child in proof["children"].items():
                        self.assertEqual(child["raw_final_structured_output_hash"], canonical_hash(drafts[agent]))
                        self.assertEqual(child["start_context_binding"]["child_session_id"], starts[agent]["agent_id"])

    def test_legacy_launch_is_rejected_before_any_process_and_current_prompt_uses_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            run, _, _, _, _ = self.prepare(directory)
            prompt = build_smoke_prompt(run, repository_root=ROOT)
            tickets = json.loads(prompt.rsplit("```json\n", 1)[1].split("```", 1)[0])
            self.assertEqual(set(tickets), SPECIALIST_AGENTS)
            for agent, message in tickets.items():
                ticket = json.loads(message)
                self.assertEqual(ticket["agent"], agent)
                self.assertEqual(ticket["dispatch_contract"], START_CONTEXT_VERSION)
                self.assertNotIn("invocation", ticket)
                self.assertNotIn("agent_input", ticket)
            legacy_run = Path(directory) / "legacy-run"
            prepare_run(ROOT, fixture_path=FIXTURES / "normal-research.json", run_dir=legacy_run,
                        run_id="legacy-test", model="gpt-6-luna", research_question="旧入口拒绝测试。")
            manifest = read_json(legacy_run / "run_manifest.json")
            manifest["specialist_output_delivery"] = "native-research-draft/1.0.0"
            write_json(legacy_run / "run_manifest.json", manifest)
            with patch("product.runtime.nested_codex.subprocess.Popen") as spawn:
                with self.assertRaisesRegex(ValueError, "SPECIALIST_LEGACY_EXECUTION_RETIRED"):
                    launch_nested_codex(ROOT, run_dir=legacy_run)
                spawn.assert_not_called()
