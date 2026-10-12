"""fixture Council 真实业务/MCP及明示历史消费者；不模拟正常Hook或模型。"""
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
from product.runtime.hashing import canonical_hash, file_hash, legacy_envelope_hash
from product.runtime.invocation import (
    SPECIALIST_AGENTS, SPECIALIST_SEMANTIC_DRAFT, SPECIALIST_TASK_NAMES,
    SPECIALIST_TECHNICAL_FIELDS, START_CONTEXT_VERSION, build_specialist_dispatch_message,
    build_specialist_start_context, envelope_specialist_semantic_draft, verify_specialist_start_binding,
)
from product.runtime.local_revision import _path
from product.runtime.nested_codex import launch_nested_codex
from product.runtime.run_package import prepare_cio, prepare_run, _write_json, RunPackageError
from product.runtime.schema_validation import validate_schema_instance
from product.runtime.smoke_prompt import build_smoke_prompt
from product.runtime.validation import validate_company_report, validate_skeptic_report
from tests.test_native_run_package import ROOT, FIXTURES, read_json, specialist_outputs, write_json
from tests.test_agents_instruction_proof import bind_instruction_fixture


def write_historical_council_starts_fixture(run):
    """仅为旧Start/proof读取器写明示向量；不派发、不交付模型、不认证作者。"""
    starts = {}
    for agent in sorted(SPECIALIST_AGENTS):
        _, binding = build_specialist_start_context(ROOT, run, agent)
        event = {"schema_version": "codex-subagent-hook-event/1.0.0", "raw_prompt_or_reasoning_retained": False,
                 "hook_event_name": "SubagentStart", "parent_session_id": "synthetic-fixture-parent",
                 "child_session_id": "synthetic-child-" + agent, "agent_type": agent,
                 "model": binding["model"], "context_binding": binding}
        starts[agent] = event
    log = run / "invocation/subagent-events.jsonl"
    log.parent.mkdir(exist_ok=True)
    log.write_text("".join(json.dumps({**event, "event_hash": legacy_envelope_hash(event, hash_field="event_hash")}) + "\n"
                           for event in starts.values()))
    (run / "invocation/codex-events.jsonl").write_text(
        json.dumps({"type": "thread.started", "thread_id": "synthetic-fixture-parent"}) + "\n")
    return starts


class CouncilSemanticHandoffTests(unittest.TestCase):
    def prepare(self, root):
        run = Path(root).resolve() / "run"
        prepared = prepare_run(ROOT, fixture_path=FIXTURES / "normal-research.json", run_dir=run,
            run_id="semantic-fixture", model="gpt-6-luna", research_question="合成研究交接。", authenticity_required=False)
        self.assertTrue((run / "run_manifest.json").is_file(), prepared)
        packets = {agent: json.loads(build_specialist_start_context(ROOT, run, agent)[0])["frozen_input"]
                   for agent in sorted(SPECIALIST_AGENTS)}
        drafts = {agent: {key: value for key, value in report.items() if key not in SPECIALIST_TECHNICAL_FIELDS}
                  for agent, report in specialist_outputs(run, persist=False).items()}
        self.assertFalse((run / "invocation").exists())
        return run, packets, drafts

    def read_draft(self, run, agent, draft, *, model="gpt-6-luna"):
        packet = json.loads(build_specialist_dispatch_message(ROOT, run, agent))
        invocation = packet["invocation"]
        formal = read_json(Path(invocation["output_schema"]))
        report = envelope_specialist_semantic_draft(draft, invocation, model=model, formal_schema=formal)
        validate_schema_instance(report, formal)
        validator = validate_company_report if agent == "runtime_company_analyst" else validate_skeptic_report
        validator(report, run_id=invocation["run_id"], manifest=invocation)
        return report

    def save_report_fixture(self, run, agent, draft):
        """真实装配/校验后用既有不可覆盖JSON写入构造业务夹具；不生成执行事件。"""
        report = self.read_draft(run, agent, draft)
        paths = [_path(run, f"agents/{agent}.native.json"), _path(run, f"agents/{agent}.json")]
        _write_json(paths[0], draft)
        _write_json(paths[1], report)
        return report

    def write_historical_stop_fixture(self, run, agent, draft, report):
        """历史消费者输入；保存和真实query必须由调用方另行完成。"""
        invocation = read_json(run / f"invocations/{agent}.json")
        event = {"schema_version": "codex-subagent-hook-event/1.0.0", "raw_prompt_or_reasoning_retained": False,
                 "hook_event_name": "SubagentStop", "parent_session_id": "synthetic-fixture-parent",
                 "child_session_id": "synthetic-child-" + agent, "agent_type": agent, "model": invocation["model"],
                 "final_structured_output_hash": canonical_hash(draft),
                 "output_binding": {"run_id": invocation["run_id"], "invocation_id": invocation["invocation_id"], "agent": agent},
                 "trusted_task_binding": {"run_id": invocation["run_id"], "invocation_id": invocation["invocation_id"],
                     "agent": agent, "task_name": SPECIALIST_TASK_NAMES[agent], "input_hash": invocation["input_hash"]},
                 "identity_binding": {"status": "BOUND"},
                 "output_capture": {"status": "SAVED", "version": SPECIALIST_SEMANTIC_DRAFT,
                     "path": f"agents/{agent}.json", "output_hash": canonical_hash(report),
                     "raw_path": f"agents/{agent}.native.json", "raw_output_hash": canonical_hash(draft)}}
        event["event_hash"] = legacy_envelope_hash(event, hash_field="event_hash")
        with (run / "invocation/subagent-events.jsonl").open("a") as stream:
            stream.write(json.dumps(event) + "\n")
        return event

    def write_historical_proof_inputs_fixture(self, run):
        """合成遥测和版本测量只验证旧消费者，绝非真实Skill/模型执行证明。"""
        (run / "invocation/prompt.txt").write_text(build_smoke_prompt(run, repository_root=ROOT))
        skill = ROOT / "product/skills/portfolio-council/SKILL.md"
        events = run / "invocation/codex-events.jsonl"
        with events.open("a") as stream:
            stream.write(json.dumps({"type": "item.completed", "item": {
                "type": "command_execution", "command": f"cat '{skill}'", "exit_code": 0,
                "aggregated_output": skill.read_text()}}) + "\n")
            stream.write(json.dumps({"type": "turn.completed", "usage": {
                "input_tokens": 100, "output_tokens": 10, "cached_input_tokens": 0}}) + "\n")
        bind_instruction_fixture(ROOT, run)
        from product.runtime.codex_runtime import capture_codex_runtime
        binary = run / "version-only-codex"
        binary.write_text("#!/bin/sh\nprintf 'codex-cli 0.160.0\\n'\n")
        binary.chmod(0o700)
        capture_codex_runtime(str(binary), expected_runtime="codex-cli/0.160.0", run_id="semantic-fixture",
            lock_path=run / "run_manifest.json", output_path=run / "invocation/codex-runtime.json")
        return dict(run_dir=run, codex_events_path=events,
                    hook_events_path=run / "invocation/subagent-events.jsonl", latency_ms=1)

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

    def test_business_query_envelope_and_cio_consumer_preserve_semantics(self):
        with tempfile.TemporaryDirectory() as directory:
            run, packets, drafts = self.prepare(directory)
            original = copy.deepcopy(drafts)
            hashes = {}
            for agent, packet in packets.items():
                self.assertTrue(SPECIALIST_TECHNICAL_FIELDS.isdisjoint(packet["output_schema"]["properties"]))
                validate_schema_instance(drafts[agent], packet["output_schema"])
                self.assertNotIn("error", self.query(run, agent, packet["agent_input"]["allowed_evidence_ids"]))
                report = self.save_report_fixture(run, agent, drafts[agent])
                for key, value in drafts[agent].items():
                    self.assertEqual(report[key], value)
                self.assertEqual(read_json(run / f"agents/{agent}.native.json"), drafts[agent])
                hashes[agent] = file_hash(run / f"agents/{agent}.json")
            self.assertFalse((run / "invocation").exists())
            result = prepare_cio(ROOT, run_dir=run, model="gpt-6-luna")
            self.assertEqual(result["next_state"], "CIO_SYNTHESIS_REQUIRED", result)
            self.assertEqual(len(read_json(run / "inputs/runtime_cio.json")["report_catalog"]), 2)
            self.assertEqual(hashes, {agent: file_hash(run / f"agents/{agent}.json") for agent in drafts})
            self.assertEqual(drafts, original)
            self.assertNotIn("claims", packets["runtime_skeptic"]["agent_input"])
            self.assertNotIn("company_reports", packets["runtime_skeptic"]["agent_input"])

    def test_reference_pollution_and_unknown_ids_are_rejected_without_correction(self):
        for agent in sorted(SPECIALIST_AGENTS):
            for evidence_id in ("ev-normal-revenue|fixture", "ev-normal-revenue|as_of=now", "ev-unknown"):
                with self.subTest(agent=agent, evidence=evidence_id), tempfile.TemporaryDirectory() as directory:
                    run, _, drafts = self.prepare(directory)
                    draft = drafts[agent]
                    field = "claims" if agent == "runtime_company_analyst" else "challenges"
                    draft[field][0]["evidence_refs"] = [evidence_id]
                    original = copy.deepcopy(draft)
                    with self.assertRaisesRegex(ValueError, "SCHEMA_"):
                        self.save_report_fixture(run, agent, draft)
                    self.assertFalse((run / "agents").exists())
                    self.assertEqual(draft, original)

    def test_technical_echo_and_wrong_model_rejected_by_real_envelope(self):
        with tempfile.TemporaryDirectory() as directory:
            run, _, drafts = self.prepare(directory)
            agent = "runtime_company_analyst"
            for change in ({"run_id": "foreign"}, {"artifact_refs": []}):
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, "SCHEMA_"):
                    self.read_draft(run, agent, {**drafts[agent], **change})
            with self.assertRaisesRegex(ValueError, "SPECIALIST_DRAFT_BINDING_INVALID"):
                self.read_draft(run, agent, drafts[agent], model="wrong")
            self.assertFalse((run / "agents").exists())

    def test_multiple_authorized_refs_preserve_selection_and_order(self):
        with tempfile.TemporaryDirectory() as directory:
            run, packets, drafts = self.prepare(directory)
            agent = "runtime_company_analyst"
            selected = packets[agent]["agent_input"]["allowed_evidence_ids"][:2]
            self.assertEqual(len(selected), 2)
            drafts[agent]["claims"][0]["evidence_refs"] = selected
            self.assertNotIn("error", self.query(run, agent, selected))
            report = self.save_report_fixture(run, agent, drafts[agent])
            self.assertEqual(report["claims"][0]["evidence_refs"], selected)

    def test_missing_historical_start_and_escaping_fixture_path_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            run, _, drafts = self.prepare(directory)
            agent = "runtime_company_analyst"
            with self.assertRaises(OSError):
                verify_specialist_start_binding(ROOT, run, agent)
            outside = Path(directory) / "outside"
            outside.mkdir()
            (run / "agents").symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "SYMLINK_FORBIDDEN"):
                self.save_report_fixture(run, agent, drafts[agent])
            self.assertEqual(list(outside.iterdir()), [])

    def test_frozen_packet_tampering_cannot_bind_a_valid_draft(self):
        for defect in ("missing", "hash", "input"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                run, _, drafts = self.prepare(directory)
                agent = "runtime_company_analyst"
                path = run / f"invocations/{agent}.json"
                if defect == "missing":
                    path.unlink()
                elif defect == "hash":
                    invocation = read_json(path)
                    invocation["manifest_hash"] = "0" * 64
                    write_json(path, invocation)
                else:
                    path = run / f"inputs/{agent}.json"
                    value = read_json(path)
                    value["research_question"] = "未经绑定的输入"
                    write_json(path, value)
                before = {path: file_hash(path) for path in run.rglob("*") if path.is_file()}
                with self.assertRaises((ValueError, OSError)):
                    self.save_report_fixture(run, agent, drafts[agent])
                self.assertEqual(before, {path: file_hash(path) for path in run.rglob("*") if path.is_file()})

    def test_protocol_downgrade_or_unknown_does_not_fall_back(self):
        for value in (None, "native-research-draft/1.0.0", "unknown"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                run, _, _ = self.prepare(directory)
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
                self.assertNotIn("spawn_agent", build_smoke_prompt(run, repository_root=ROOT))

    def test_existing_json_writer_never_overwrites_saved_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            run, _, drafts = self.prepare(directory)
            agent = "runtime_company_analyst"
            self.save_report_fixture(run, agent, drafts[agent])
            before = {path: file_hash(path) for path in (run / "agents").iterdir()}
            with self.assertRaises(RunPackageError):
                self.save_report_fixture(run, agent, {**drafts[agent], "scope": "different"})
            self.assertEqual(before, {path: file_hash(path) for path in (run / "agents").iterdir()})

    def test_historical_proof_reader_recomputes_envelope_identity_and_raw_hash(self):
        for defect in (None, "raw", "child", "model"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                run, packets, drafts = self.prepare(directory)
                starts = write_historical_council_starts_fixture(run)
                for agent in sorted(SPECIALIST_AGENTS):
                    self.assertNotIn("error", self.query(run, agent, packets[agent]["agent_input"]["allowed_evidence_ids"]))
                    report = self.save_report_fixture(run, agent, drafts[agent])
                    self.write_historical_stop_fixture(run, agent, drafts[agent], report)
                arguments = self.write_historical_proof_inputs_fixture(run)
                if defect == "raw":
                    path = run / "agents/runtime_company_analyst.native.json"
                    write_json(path, {**drafts["runtime_company_analyst"], "confidence": "wrong-type"})
                elif defect:
                    path = run / "invocation/subagent-events.jsonl"
                    records = [json.loads(line) for line in path.read_text().splitlines()]
                    records[-1]["child_session_id" if defect == "child" else "model"] = "foreign"
                    records[-1]["event_hash"] = legacy_envelope_hash(records[-1], hash_field="event_hash")
                    path.write_text("".join(json.dumps(record) + "\n" for record in records))
                if defect:
                    with self.assertRaises(ExecutionProofError):
                        build_ephemeral_run_specialist_execution_proof(ROOT, **arguments)
                    self.assertFalse((run / "events/codex/specialist-execution-proof.json").exists())
                else:
                    result = build_ephemeral_run_specialist_execution_proof(ROOT, **arguments)
                    self.assertEqual(result["next_state"], "EXECUTION_PROOF_VERIFIED")
                    proof = read_json(run / "events/codex/specialist-execution-proof.json")
                    for agent, child in proof["children"].items():
                        self.assertEqual(child["raw_final_structured_output_hash"], canonical_hash(drafts[agent]))
                        self.assertEqual(child["start_context_binding"]["child_session_id"], starts[agent]["child_session_id"])

    def test_legacy_launch_and_normal_hooks_are_rejected_before_any_process(self):
        with tempfile.TemporaryDirectory() as directory:
            run, _, _ = self.prepare(directory)
            prompt = build_smoke_prompt(run, repository_root=ROOT)
            tickets = json.loads(prompt.rsplit("```json\n", 1)[1].split("```", 1)[0])
            self.assertEqual(set(tickets), SPECIALIST_AGENTS)
            for agent, message in tickets.items():
                ticket = json.loads(message)
                self.assertEqual(ticket["agent"], agent)
                self.assertEqual(ticket["dispatch_contract"], START_CONTEXT_VERSION)
                self.assertNotIn("invocation", ticket)
                self.assertNotIn("agent_input", ticket)
            with patch("subprocess.Popen") as spawn:
                with self.assertRaisesRegex(ValueError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                    launch_nested_codex(ROOT, run_dir=run)
                spawn.assert_not_called()
            for event in ("PreToolUse", "SubagentStart", "SubagentStop", "Stop"):
                with self.subTest(event=event), self.assertRaisesRegex(ValueError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                    handle_hook_event({"hook_event_name": event}, environ={"STOCK_AGENT_RUN_DIR": str(run)})
            self.assertFalse((run / "invocation").exists())
