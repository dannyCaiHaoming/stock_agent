"""真实 Hook 接缝的有界修订；事件是测试输入，不启动 Codex/评分模型。"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from product.runtime import common_stock_eval as common
from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.hashing import canonical_hash
from product.runtime.execution_proof import build_ephemeral_run_specialist_execution_proof, ExecutionProofError
from product.runtime.smoke_prompt import build_smoke_prompt
from product.runtime.invocation import build_specialist_dispatch_message, specialist_semantic_schema, compact_specialist_schema
from tests.test_agents_instruction_proof import bind_instruction_fixture
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

    def specialist(self, agent="runtime_company_analyst"):
        fixture = council_fixtures.CouncilSemanticHandoffTests()
        run, env, starts, _, drafts = fixture.prepare(self.temp.name)
        return run, drafts[agent], lambda draft, **override: fixture.stop(
            env, {**starts[agent], **override}, draft)

    def evaluator(self, *, failing=(), root=None):
        fixture = stock_fixtures.CommonStockFocusedEvalTests()
        _, _, directory, manifest = fixture.prepare_job(root or self.temp.name)
        (directory / "invocation").mkdir()
        env = {"STOCK_AGENT_RUN_DIR": str(directory),
               "STOCK_AGENT_SUBAGENT_EVENT_LOG": str(directory / "invocation/subagent-events.jsonl"),
               "STOCK_AGENT_SUBAGENT_DISPATCH_LOG": str(directory / "invocation/subagent-dispatches.jsonl"),
               "STOCK_AGENT_REQUIRED_PARALLEL_SUBAGENTS": "dev_eval",
               "STOCK_AGENT_COMMON_STOCK_EVAL": common.EVAL_RUNTIME_VERSION,
               "STOCK_AGENT_COMMON_STOCK_EVAL_MODEL": "gpt-5.6-terra"}
        dispatch = {"hook_event_name": "PreToolUse", "session_id": "eval-parent", "turn_id": "turn",
                    "tool_name": "spawn_agent", "tool_use_id": "dispatch", "cwd": str(stock_fixtures.ROOT),
                    "model": "gpt-5.6-terra", "permission_mode": "workspace-write",
                    "tool_input": {"agent_type": "dev_eval", "task_name": "grade_common_stock_report",
                                   "fork_turns": "none", "message": common.build_common_stock_eval_dispatch_message(directory)}}
        record, _ = handle_hook_event(dispatch, environ=env)
        self.assertEqual(record["decision"], "ALLOW", record)
        start = {"hook_event_name": "SubagentStart", "session_id": "eval-parent", "turn_id": "turn",
                 "agent_id": "eval-child", "agent_type": "dev_eval", "model": "gpt-5.6-terra",
                 "cwd": str(stock_fixtures.ROOT), "permission_mode": "read-only"}
        record, _ = handle_hook_event(start, environ=env)
        self.assertEqual(record["context_binding"]["status"], "DELIVERED", record)
        def stop(draft, **override):
            return handle_hook_event({**start, "hook_event_name": "SubagentStop", "stop_hook_active": False,
                                      "last_assistant_message": json.dumps(draft, ensure_ascii=False), **override}, environ=env)
        return directory, fixture.semantic_draft(manifest, failing=failing), stop

    def test_both_specialist_roles_repair_only_original_field_and_keep_raw_hash_contract(self):
        for agent in ("runtime_company_analyst", "runtime_skeptic"):
            with self.subTest(agent=agent), tempfile.TemporaryDirectory() as root:
                fixture = council_fixtures.CouncilSemanticHandoffTests()
                run, env, starts, _, drafts = fixture.prepare(root)
                original = drafts[agent]
                invalid = {**original, "confidence": "not-a-number"}
                first, response = fixture.stop(env, starts[agent], invalid)
                feedback = self.assert_feedback(first, response)
                self.assertEqual(feedback["allowed_paths"], ["/confidence"])
                self.assertNotIn("binding_hash", feedback)
                raw_path = run / first["output_capture"]["raw_path"]
                first_bytes = raw_path.read_bytes()
                second, response = fixture.stop(env, starts[agent], self.patch(feedback, "/confidence", original["confidence"]))
                self.assertEqual(second["output_capture"]["status"], "SAVED", second)
                self.assertEqual(second["output_capture"]["repair_state"], "REPAIRED")
                self.assertEqual(response, {})
                self.assertEqual(json.loads((run / f"agents/{agent}.native.json").read_text()), original)
                self.assertEqual(second["output_capture"]["raw_output_hash"], canonical_hash(original))
                self.assertEqual(raw_path.read_bytes(), first_bytes)
                self.assertNotEqual(second["output_capture"]["submission_path"], first["output_capture"]["raw_path"])
                duplicate, _ = fixture.stop(env, starts[agent], self.patch(feedback, "/confidence", original["confidence"]))
                self.assertEqual(duplicate["output_capture"]["status"], "SAVED", duplicate)
                self.assertEqual(duplicate["duplicate_of"], second["event_hash"])

    def test_specialist_out_of_scope_second_invalid_and_unauthorized_do_not_publish(self):
        run, draft, stop = self.specialist()
        invalid = {**draft, "confidence": "bad"}
        denied, _ = stop(invalid, model="wrong-model")
        self.assertNotIn("attempt", denied["output_capture"])
        first, response = stop(invalid)
        self.assertEqual(first["output_capture"]["attempt"], 1)
        feedback = self.assert_feedback(first, response)
        second, _ = stop(self.patch(feedback, "/scope", "unrelated rewrite"))
        self.assertIn("LOCAL_REVISION_OUT_OF_SCOPE", second["output_capture"]["failure_code"])
        third, _ = stop(self.patch(feedback, "/confidence", draft["confidence"]))
        self.assertEqual(third["output_capture"]["failure_code"], "LOCAL_REVISION_LIMIT_EXHAUSTED")
        self.assertFalse((run / "agents/runtime_company_analyst.json").exists())

    def test_specialist_second_draft_is_fully_validated_and_cannot_get_third_attempt(self):
        run, draft, stop = self.specialist()
        first, response = stop({**draft, "confidence": "bad"})
        feedback = self.assert_feedback(first, response)
        second, response = stop(self.patch(feedback, "/confidence", 2))
        self.assertIn("SCHEMA_MAXIMUM", second["output_capture"]["failure_code"])
        self.assertEqual(second["output_capture"]["repair_state"], "EXHAUSTED")
        self.assertEqual(response, {})
        third, _ = stop(self.patch(feedback, "/confidence", draft["confidence"]))
        self.assertEqual(third["output_capture"]["failure_code"], "LOCAL_REVISION_LIMIT_EXHAUSTED")
        self.assertFalse((run / "agents/runtime_company_analyst.json").exists())

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

    def test_technical_identity_echo_has_no_repair_permission(self):
        run, draft, stop = self.specialist()
        rejected, response = stop({**draft, "artifact_refs": []})
        self.assertEqual(rejected["output_capture"]["repair_state"], "NOT_ALLOWED")
        self.assertEqual(response, {})
        self.assertFalse((run / "agents/runtime_company_analyst.json").exists())
        # 单独准备 Eval，避免同一临时根已经存在的 fixture 文件影响创建。
        with tempfile.TemporaryDirectory() as root:
            directory, draft, stop = self.evaluator(root=root)
            rejected, response = stop({**draft, "model": "forged"})
            self.assertEqual(rejected["output_capture"]["repair_state"], "NOT_ALLOWED")
            self.assertEqual(response, {})
            self.assertFalse((directory / "eval/result.json").exists())

    def test_current_specialist_context_keeps_entire_input_and_task_text_without_private_envelope(self):
        fixture = council_fixtures.CouncilSemanticHandoffTests()
        run, _, _, packets, _ = fixture.prepare(self.temp.name)
        log = [json.loads(line) for line in (run / "invocation/subagent-events.jsonl").read_text().splitlines()]
        for agent, view in packets.items():
            with self.subTest(agent=agent):
                private = json.loads(build_specialist_dispatch_message(stock_fixtures.ROOT, run, agent))
                self.assertNotIn("invocation", view)
                self.assertNotIn("contract_checks", view)
                for field in ("run_dir", "identity", "agent_input", "task_prompt", "instruction"):
                    self.assertEqual(view[field], private[field])
                self.assertEqual(view["output_schema"], compact_specialist_schema(
                    private["output_schema"], view["agent_input"]["allowed_evidence_ids"]))
                event = next(item for item in log if item.get("hook_event_name") == "SubagentStart"
                             and item.get("agent_type") == agent)
                diag = event["delivery_diagnostics"]
                self.assertEqual(diag["comparison_status"], "SAME_FROZEN_PACKET")
                self.assertEqual(diag["token_count_status"], "NOT_OBSERVED")
                self.assertEqual(diag["full_packet_bytes"], len(json.dumps(
                    private, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")))

    def test_eval_model_view_keeps_negation_footnotes_conflicts_and_exact_values(self):
        _, _, directory, manifest = stock_fixtures.CommonStockFocusedEvalTests().prepare_job(self.temp.name)
        packet = common.build_common_stock_eval_packet(directory, expected_model="gpt-5.6-terra")
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

    def test_proof_consumer_rebuilds_revision_from_base_and_rejects_resigned_summary_or_patch_tampering(self):
        for tamper in (None, "summary", "patch", "duplicate", "base", "original"):
            with self.subTest(tamper=tamper), tempfile.TemporaryDirectory() as root:
                fixture = council_fixtures.CouncilSemanticHandoffTests()
                run, env, starts, packets, drafts = fixture.prepare(root)
                for agent in sorted(drafts):
                    fixture.query(run, agent, packets[agent]["agent_input"]["allowed_evidence_ids"])
                    draft = drafts[agent]
                    if tamper == "original" and agent == "runtime_company_analyst":
                        message = draft
                    else:
                        first, response = fixture.stop(env, starts[agent], {**draft, "confidence": "bad"})
                        feedback = self.assert_feedback(first, response)
                        message = self.patch(feedback, "/confidence", draft["confidence"])
                    second, _ = fixture.stop(env, starts[agent], message)
                    self.assertEqual(second["output_capture"]["status"], "SAVED", second)
                    duplicate, _ = fixture.stop(env, starts[agent], message)
                    self.assertEqual(duplicate["output_capture"]["status"], "SAVED", duplicate)
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
                        path.write_text(path.read_text() + "\n")  # 语义同稿，但实际消息已漂移。
                # 合成公开遥测只用于读取器检查，不当作真实模型执行证据。
                (run / "invocation/prompt.txt").write_text(build_smoke_prompt(run, repository_root=stock_fixtures.ROOT))
                skill = stock_fixtures.ROOT / "product/skills/portfolio-council/SKILL.md"
                events = run / "invocation/codex-events.jsonl"
                with events.open("a") as stream:
                    stream.write(json.dumps({"type": "item.completed", "item": {
                        "type": "command_execution", "command": f"cat '{skill}'", "exit_code": 0,
                        "aggregated_output": skill.read_text()}}) + "\n")
                    stream.write(json.dumps({"type": "turn.completed", "usage": {
                        "input_tokens": 100, "output_tokens": 10, "cached_input_tokens": 0}}) + "\n")
                bind_instruction_fixture(stock_fixtures.ROOT, run)
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
                    target["event_hash"] = canonical_hash({key: value for key, value in target.items() if key != "event_hash"})
                    # 只改摘要也必须拒绝；保持重复来源引用对应，真正检查在底层补丁重建。
                    if tamper == "summary":
                        duplicate = next(item for item in records if item.get("duplicate_of")
                                         and item.get("agent_type") == "runtime_company_analyst")
                        duplicate["duplicate_of"] = target["event_hash"]
                        duplicate["local_revision"] = copy.deepcopy(target["local_revision"])
                        duplicate["event_hash"] = canonical_hash({key: value for key, value in duplicate.items() if key != "event_hash"})
                    log.write_text("".join(json.dumps(item) + "\n" for item in records))
                arguments = dict(run_dir=run, codex_events_path=events, hook_events_path=log, latency_ms=1)
                if tamper:
                    with self.assertRaises(ExecutionProofError):
                        build_ephemeral_run_specialist_execution_proof(stock_fixtures.ROOT, **arguments)
                    self.assertFalse((run / "events/codex/specialist-execution-proof.json").exists())
                else:
                    result = build_ephemeral_run_specialist_execution_proof(stock_fixtures.ROOT, **arguments)
                    self.assertEqual(result["next_state"], "EXECUTION_PROOF_VERIFIED")
