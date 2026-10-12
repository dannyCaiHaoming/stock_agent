"""Council纯业务修订/明示历史向量与显式dev_eval维护接缝；零模型。"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from product.runtime import common_stock_eval as common
from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.hashing import canonical_hash, legacy_envelope_hash
from product.runtime.execution_proof import build_ephemeral_run_specialist_execution_proof, ExecutionProofError
from product.runtime.invocation import build_specialist_dispatch_message, compact_specialist_schema
from product.runtime.local_revision import bind, resolve, _apply, located_paths
from product.runtime.schema_validation import schema_issue_locations
from tests import test_council_semantic_handoff as council_fixtures
from tests import test_common_stock_research_contracts as stock_fixtures


class CouncilEvalLocalRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    @staticmethod
    def patch(feedback, path, value):
        return {"base_draft_ref": feedback["base_draft_ref"], "changes": [
            {"op": "replace", "path": path, "value": value}]}

    @staticmethod
    def assert_feedback(record, response):
        if record["output_capture"]["repair_state"] != "REPAIR_REQUESTED":
            raise AssertionError(record)
        if response.get("decision") != "block":
            raise AssertionError(response)
        return json.loads(response["reason"])

    def evaluator(self, *, failing=(), root=None):
        fixture = stock_fixtures.CommonStockFocusedEvalTests()
        _, _, directory, manifest = fixture.prepare_job(root or self.temp.name)
        (directory / "invocation").mkdir()
        env = {"STOCK_AGENT_RUN_DIR": str(directory),
               "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(directory / "invocation/subagent-events.jsonl"),
               "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(directory / "invocation/subagent-dispatches.jsonl"),
               "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": "dev_eval",
               "STOCK_AGENT_COMMON_STOCK_EVAL": common.EVAL_RUNTIME_VERSION,
               "STOCK_AGENT_COMMON_STOCK_EVAL_MODEL": "gpt-6-luna"}
        dispatch = {"hook_event_name": "PreToolUse", "session_id": "eval-parent", "turn_id": "turn",
                    "tool_name": "spawn_agent", "tool_use_id": "dispatch", "cwd": str(stock_fixtures.ROOT),
                    "model": "gpt-6-luna", "permission_mode": "workspace-write",
                    "tool_input": {"agent_type": "dev_eval", "task_name": "grade_common_stock_report",
                                   "fork_turns": "none", "message": common.build_common_stock_eval_dispatch_message(directory)}}
        record, _ = handle_hook_event(dispatch, environ=env)
        self.assertEqual(record["decision"], "ALLOW", record)
        start = {"hook_event_name": "SubagentStart", "session_id": "eval-parent", "turn_id": "turn",
                 "agent_id": "eval-child", "agent_type": "dev_eval", "model": "gpt-6-luna",
                 "cwd": str(stock_fixtures.ROOT), "permission_mode": "read-only"}
        record, _ = handle_hook_event(start, environ=env)
        self.assertEqual(record["context_binding"]["status"], "DELIVERED", record)
        def stop(draft, **override):
            return handle_hook_event({**start, "hook_event_name": "SubagentStop", "stop_hook_active": False,
                                      "last_assistant_message": json.dumps(draft, ensure_ascii=False), **override}, environ=env)
        return directory, fixture.semantic_draft(manifest, failing=failing), stop

    def test_both_specialist_roles_explicitly_repair_only_located_field(self):
        fixture = council_fixtures.CouncilSemanticHandoffTests()
        run, packets, drafts = fixture.prepare(self.temp.name)
        for agent, draft in drafts.items():
            with self.subTest(agent=agent):
                invalid = {**draft, "confidence": "not-a-number"}
                original = copy.deepcopy(invalid)
                with self.assertRaises(ValueError):
                    fixture.read_draft(run, agent, invalid)
                paths = located_paths(schema_issue_locations(invalid, packets[agent]["output_schema"]), exact_fields=True)
                self.assertEqual(paths, ["/confidence"])
                corrected = _apply(invalid, [{"op": "replace", "path": paths[0], "value": draft["confidence"]}], paths)
                report = fixture.save_report_fixture(run, agent, corrected)
                self.assertEqual(corrected, draft)
                self.assertEqual(report["confidence"], draft["confidence"])
                self.assertEqual(invalid, original)
        self.assertFalse((run / "invocation").exists())

    def test_specialist_out_of_scope_second_invalid_model_and_identity_do_not_publish(self):
        fixture = council_fixtures.CouncilSemanticHandoffTests()
        run, _, drafts = fixture.prepare(self.temp.name)
        agent = "runtime_company_analyst"
        invalid = {**drafts[agent], "confidence": "bad"}
        with self.assertRaisesRegex(ValueError, "LOCAL_REVISION_OUT_OF_SCOPE"):
            _apply(invalid, [{"op": "replace", "path": "/scope", "value": "重写未授权研究"}], ["/confidence"])
        second = _apply(invalid, [{"op": "replace", "path": "/confidence", "value": 2}], ["/confidence"])
        with self.assertRaisesRegex(ValueError, "SCHEMA_MAXIMUM"):
            fixture.save_report_fixture(run, agent, second)
        with self.assertRaisesRegex(ValueError, "SPECIALIST_DRAFT_BINDING_INVALID"):
            fixture.read_draft(run, agent, drafts[agent], model="wrong-model")
        with self.assertRaisesRegex(ValueError, "SCHEMA_"):
            fixture.save_report_fixture(run, agent, {**drafts[agent], "artifact_refs": []})
        self.assertFalse((run / "agents").exists())
        self.assertFalse((run / "invocation").exists())

    def test_eval_invalid_first_does_not_occupy_formal_path_and_repaired_grade_stays_fail(self):
        directory, draft, stop = self.evaluator(failing={"valuation_grounding"})
        invalid = copy.deepcopy(draft)
        dimension = common.DIMENSIONS[0]
        invalid["dimensions"][dimension]["rationale"] = 0
        first, response = stop(invalid)
        feedback = self.assert_feedback(first, response)
        self.assertEqual(feedback["allowed_paths"], [f"/dimensions/{dimension}/rationale"])
        self.assertFalse((directory / "invocation/semantic-result.json").exists())
        self.assertFalse((directory / "eval/result.json").exists())
        original = (directory / first["output_capture"]["raw_path"]).read_bytes()
        second, _ = stop(self.patch(feedback, feedback["allowed_paths"][0], draft["dimensions"][dimension]["rationale"]))
        self.assertEqual(second["output_capture"]["status"], "SAVED", second)
        result = json.loads((directory / "eval/result.json").read_text())
        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["dimensions"], draft["dimensions"])
        self.assertEqual((directory / first["output_capture"]["raw_path"]).read_bytes(), original)
        self.assertEqual(json.loads((directory / "invocation/semantic-result.json").read_text()), draft)
        self.assertTrue((directory / "eval/report.md").is_file())

    def test_eval_invalid_reference_is_located_but_not_silently_selected(self):
        directory, draft, stop = self.evaluator()
        dimension = common.DIMENSIONS[0]
        invalid = copy.deepcopy(draft)
        invalid["dimensions"][dimension]["evidence_refs"] = ["missing"]
        first, response = stop(invalid)
        feedback = self.assert_feedback(first, response)
        self.assertEqual(feedback["allowed_paths"], [f"/dimensions/{dimension}/evidence_refs"])
        second, response = stop(self.patch(feedback, feedback["allowed_paths"][0], ["still-missing"]))
        self.assertIn("EVIDENCE_REF_INVALID", second["output_capture"]["failure_code"])
        self.assertEqual(second["output_capture"]["repair_state"], "EXHAUSTED")
        self.assertEqual(response, {})
        self.assertFalse((directory / "invocation/semantic-result.json").exists())
        self.assertFalse((directory / "eval/result.json").exists())

    def test_eval_unauthorized_model_child_and_drift_do_not_take_revision_slot(self):
        directory, draft, stop = self.evaluator()
        invalid = copy.deepcopy(draft)
        invalid["dimensions"][common.DIMENSIONS[0]]["rationale"] = False
        for override in ({"model": "wrong-model"}, {"agent_id": "another-child"}):
            denied, _ = stop(invalid, **override)
            self.assertEqual(denied["output_capture"]["status"], "FAILED")
            self.assertNotIn("attempt", denied["output_capture"])
            self.assertFalse((directory / "research/raw-drafts").exists())
            self.assertFalse((directory / "invocation/rejected-semantic-result.json").exists())
        source = directory / "input-manifest.json"
        original = source.read_bytes()
        manifest = json.loads(original)
        manifest["report"]["summary"] = "changed"
        manifest["input_hash"] = canonical_hash({key: value for key, value in manifest.items() if key != "input_hash"})
        source.write_text(json.dumps(manifest))
        denied, _ = stop(invalid)
        self.assertIn("START_BINDING_INVALID", denied["output_capture"]["failure_code"])
        self.assertNotIn("attempt", denied["output_capture"])
        source.write_bytes(original)
        first, response = stop(invalid)
        self.assertEqual(first["output_capture"]["attempt"], 1)
        self.assert_feedback(first, response)

    def test_eval_technical_identity_echo_has_no_repair_permission(self):
        directory, draft, stop = self.evaluator()
        rejected, response = stop({**draft, "model": "forged"})
        self.assertEqual(rejected["output_capture"]["repair_state"], "NOT_ALLOWED")
        self.assertEqual(response, {})
        self.assertFalse((directory / "eval/result.json").exists())

    def test_specialist_serialization_keeps_entire_input_without_private_envelope(self):
        fixture = council_fixtures.CouncilSemanticHandoffTests()
        run, packets, _ = fixture.prepare(self.temp.name)
        for agent, view in packets.items():
            with self.subTest(agent=agent):
                private = json.loads(build_specialist_dispatch_message(stock_fixtures.ROOT, run, agent))
                self.assertNotIn("invocation", view)
                self.assertNotIn("contract_checks", view)
                for field in ("run_dir", "identity", "agent_input", "task_prompt", "instruction"):
                    self.assertEqual(view[field], private[field])
                self.assertEqual(view["output_schema"], compact_specialist_schema(
                    private["output_schema"], view["agent_input"]["allowed_evidence_ids"]))
        self.assertFalse((run / "invocation").exists())

    def test_eval_model_view_keeps_negation_footnotes_conflicts_and_exact_values(self):
        _, _, directory, manifest = stock_fixtures.CommonStockFocusedEvalTests().prepare_job(self.temp.name)
        packet = common.build_common_stock_eval_packet(directory, expected_model="gpt-6-luna")
        # 纯表示反例，不写回真实输入、冻结锁或历史报告。
        packet["input_manifest"]["report"]["research_summary"] = "不能由成交量认定净流入；资料冲突尚未解决。"
        packet["input_manifest"]["report"]["claims"][0]["statement"] = "收入不是现金流；期间及主体不可混同。"
        packet["input_manifest"]["report_markdown"] += "\n脚注：单位 USD million；仅截至指定期间，非未来预测。"
        packet["input_manifest"]["allowed_evidence"][0]["value"] = {"as_of": "原值中的时间", "content_hash": "原值中的同名键", "amount": -12.5}
        private = copy.deepcopy(packet)
        view = common.common_stock_eval_model_packet(packet)
        self.assertEqual(packet, private)
        for field in ("report", "rubric", "allowed_evidence", "report_markdown", "hard_gates"):
            self.assertEqual(view["input"][field], private["input_manifest"][field])
        self.assertEqual(view["output_schema"], private["output_schema"])
        self.assertNotIn("source_hashes", view["input"])
        self.assertNotIn("input_hash", view["input"])
        self.assertNotIn("coverage_binding", view["input"])
        self.assertEqual(manifest, json.loads((directory / "input-manifest.json").read_text()))

    def write_historical_revision_fixture(self, fixture, run, agent, draft, report, *, original=False):
        """显式旧补丁/原件/重复事件向量，只测重建，不模拟自动Stop或修订额度。"""
        last = fixture.write_historical_stop_fixture(run, agent, draft, report)
        log = run / "invocation/subagent-events.jsonl"
        rows = [json.loads(line) for line in log.read_text().splitlines()][:-1]
        payload = {"session_id": last["parent_session_id"], "agent_id": last["child_session_id"],
                   "agent_type": agent, "model": last["model"]}
        first = None
        if not original:
            invalid = {**draft, "confidence": "bad"}
            message = json.dumps(invalid, ensure_ascii=False)
            relative = f"invocation/{agent}-synthetic-base.json"
            (run / relative).write_text(message + "\n")
            first = {**last, "hook_event_name": "SubagentStopBlocked", "hook_decision": "BLOCK",
                     "output_capture": {"status": "FAILED", "attempt": 1, "repair_state": "REPAIR_REQUESTED",
                         "raw_path": relative, "raw_output_hash": canonical_hash({"assistant_message": message})}}
            schema = json.loads(build_specialist_dispatch_message(stock_fixtures.ROOT, run, agent))["output_schema"]
            repair = {"validation_error": "SCHEMA_TYPE_MISMATCH"}
            binding = bind(run, {**payload, "last_assistant_message": message}, first,
                first["output_capture"], repair, schema_issue_locations(invalid, schema))
            self.assertIsNotNone(binding)
            first["repair_request"] = {**repair, **binding}
            first["event_hash"] = legacy_envelope_hash(first, hash_field="event_hash")
            submitted = self.patch(binding, "/confidence", draft["confidence"])
            resolved = resolve(run, {**payload, "last_assistant_message": json.dumps(submitted)}, last, first)
            self.assertEqual(json.loads(resolved["last_assistant_message"]), draft)
            rows.append(first)
        else:
            submitted = draft
        message = json.dumps(submitted, ensure_ascii=False)
        relative = f"invocation/{agent}-synthetic-submission.json"
        (run / relative).write_text(message + "\n")
        last["output_capture"].update(submission_path=relative, submission_hash=canonical_hash({"assistant_message": message}),
            attempt=1 if original else 2, repair_state="NOT_REQUIRED" if original else "REPAIRED")
        last["assistant_message_sha256"] = canonical_hash({"assistant_message": message})
        last["final_structured_output_hash"] = canonical_hash(submitted)
        last["event_hash"] = legacy_envelope_hash(last, hash_field="event_hash")
        duplicate = {**last, "duplicate_of": last["event_hash"]}
        duplicate["event_hash"] = legacy_envelope_hash(duplicate, hash_field="event_hash")
        log.write_text("".join(json.dumps(row) + "\n" for row in [*rows, last, duplicate]))
        return first, last

    def test_historical_proof_rebuilds_base_and_rejects_resigned_summary_patch_and_duplicates(self):
        for tamper in (None, "summary", "patch", "duplicate", "base", "original"):
            with self.subTest(tamper=tamper), tempfile.TemporaryDirectory() as root:
                fixture = council_fixtures.CouncilSemanticHandoffTests()
                run, packets, drafts = fixture.prepare(root)
                council_fixtures.write_historical_council_starts_fixture(run)
                for agent in sorted(drafts):
                    response = fixture.query(run, agent, packets[agent]["agent_input"]["allowed_evidence_ids"])
                    self.assertNotIn("error", response, response)
                    draft = drafts[agent]
                    report = fixture.save_report_fixture(run, agent, draft)
                    first, second = self.write_historical_revision_fixture(fixture, run, agent, draft, report,
                        original=tamper == "original" and agent == "runtime_company_analyst")
                    if tamper == "patch" and agent == "runtime_company_analyst":
                        path = run / second["output_capture"]["submission_path"]
                        value = json.loads(path.read_text())
                        value["changes"][0]["value"] = 0.01
                        path.write_text(json.dumps(value))
                    if tamper == "base" and agent == "runtime_company_analyst":
                        path = run / first["output_capture"]["raw_path"]
                        value = json.loads(path.read_text())
                        value["confidence"] = "changed-base"
                        path.write_text(json.dumps(value))
                    if tamper == "original" and agent == "runtime_company_analyst":
                        path = run / second["output_capture"]["submission_path"]
                        path.write_text(path.read_text() + "\n")
                arguments = fixture.write_historical_proof_inputs_fixture(run)
                log = run / "invocation/subagent-events.jsonl"
                if tamper in {"summary", "duplicate"}:
                    records = [json.loads(line) for line in log.read_text().splitlines()]
                    target = next(item for item in records if item.get("local_revision")
                        and item.get("agent_type") == "runtime_company_analyst"
                        and bool(item.get("duplicate_of")) == (tamper == "duplicate"))
                    if tamper == "summary":
                        target["local_revision"]["output_hash"] = "0" * 64
                    else:
                        target["duplicate_of"] = "unknown-event"
                    target["event_hash"] = legacy_envelope_hash(target, hash_field="event_hash")
                    if tamper == "summary":
                        duplicate = next(item for item in records if item.get("duplicate_of")
                            and item.get("agent_type") == "runtime_company_analyst")
                        duplicate["duplicate_of"] = target["event_hash"]
                        duplicate["local_revision"] = copy.deepcopy(target["local_revision"])
                        duplicate["event_hash"] = legacy_envelope_hash(duplicate, hash_field="event_hash")
                    log.write_text("".join(json.dumps(item) + "\n" for item in records))
                if tamper:
                    with self.assertRaises(ExecutionProofError):
                        build_ephemeral_run_specialist_execution_proof(stock_fixtures.ROOT, **arguments)
                    self.assertFalse((run / "events/codex/specialist-execution-proof.json").exists())
                else:
                    result = build_ephemeral_run_specialist_execution_proof(stock_fixtures.ROOT, **arguments)
                    self.assertEqual(result["next_state"], "EXECUTION_PROOF_VERIFIED")
