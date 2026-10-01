"""Runtime Eval 的真实文件/合成会话接缝；不调用 LLM、不替代内容评分。"""
from __future__ import annotations

import copy
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from product.runtime.eval_execution_proof import (
    collect_native_eval_output, persist_eval_execution_proof, verify_eval_execution_proof,
)
from product.runtime.hashing import legacy_envelope_hash
from product.runtime.runtime_eval import prepare_eval_job, finalize_eval_job, build_eval_smoke_prompt
from product.runtime.runtime_eval import runtime_eval_model_input, verify_runtime_eval_model_input
from tests.test_eval_execution_proof import rollouts
from tests.test_native_execution_proof import message
from tests.test_replay_capsule import complete_run, ROOT
from tests.test_runtime_eval_job import semantic_result


class RuntimeEvalLocalRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def job(self, name="job", *, invalid=True):
        root = self.root / name
        root.mkdir()
        run, evaluation = root / "run", root / "eval"
        complete_run(run, name)
        prepare_eval_job(ROOT, run_dir=run, eval_dir=evaluation, eval_id=name)
        manifest_path = evaluation / "input-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["authenticity_required"] = True
        manifest_path.write_text(json.dumps(manifest))
        semantic = semantic_result(evaluation)
        field = sorted(semantic["dimensions"])[0]
        if invalid:
            semantic["dimensions"][field]["grade"] = 4
        parent, child = rollouts(root, evaluation, semantic, plaintext_bindings=False)
        return evaluation, parent, child, field

    def collect(self, directory, parent, child):
        return collect_native_eval_output(ROOT, eval_dir=directory,
            semantic_result_path=directory / "semantic-result.json", parent_rollout=parent, child_rollout=child)

    @staticmethod
    def read(path):
        return json.loads(path.read_text())

    @staticmethod
    def append(path, records):
        with path.open("a", encoding="utf-8") as stream:
            for record in records:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def continue_child(self, parent, child, pending, draft, *, recipient="eval-child", feedback=None):
        text = pending["feedback"] if feedback is None else feedback
        self.append(parent, [{"type": "response_item", "payload": {
            "type": "function_call", "namespace": "collaboration", "name": "send_input",
            "call_id": "local-revision", "arguments": json.dumps({"id": recipient, "message": text})}}])
        self.append(child, [message("user", text), message("assistant", json.dumps(draft, ensure_ascii=False))])

    @staticmethod
    def patch(pending, field, value=2):
        feedback = json.loads(pending["feedback"])
        return {"base_draft_ref": feedback["base_draft_ref"], "changes": [{
            "op": "replace", "path": f"/dimensions/{field}/grade", "value": value}]}

    def test_original_child_patch_reaches_original_finalizer_without_hash_copy(self):
        directory, parent, child, field = self.job()
        pending = self.collect(directory, parent, child)
        self.assertEqual(pending["next_state"], "EVAL_LOCAL_REVISION_REQUIRED")
        self.assertFalse((directory / "semantic-result.json").exists())
        self.assertFalse((directory / "grader-execution-proof.json").exists())
        base = (directory / "semantic-attempt-1.json").read_bytes()
        original = json.loads(base)
        self.assertEqual(json.loads(pending["feedback"])["allowed_paths"], [f"/dimensions/{field}/grade"])
        self.assertNotRegex(pending["feedback"], r"[0-9a-f]{64}")
        self.assertEqual(set(json.loads(pending["feedback"])), {"base_draft_ref", "allowed_paths", "instruction"})
        first_parent, first_child = parent.read_bytes(), child.read_bytes()
        patch = self.patch(pending, field)
        self.continue_child(parent, child, pending, patch)
        proof = self.collect(directory, parent, child)
        self.assertEqual(proof["local_revision"]["status"], "REVISED")
        self.assertEqual((directory / "semantic-attempt-1.json").read_bytes(), base)
        self.assertEqual(self.read(directory / "semantic-attempt-2.json"), patch)
        saved = self.read(directory / "semantic-native-draft.json")
        original["dimensions"][field]["grade"] = 2
        self.assertEqual(saved, original)
        self.assertTrue(parent.read_bytes().startswith(first_parent))
        self.assertTrue(child.read_bytes().startswith(first_child))
        persist_eval_execution_proof(proof, eval_dir=directory)
        formal = self.read(directory / "semantic-result.json")
        verify_eval_execution_proof(ROOT, eval_dir=directory, semantic_result=formal)
        final = finalize_eval_job(ROOT, eval_dir=directory, semantic_result_path=directory / "semantic-result.json")
        self.assertEqual(final["status"], "PASS")
        self.assertTrue((directory / "eval/report.md").exists())
        self.assertEqual(final["grader"]["execution_proof_hash"], proof["proof_hash"])
        with self.assertRaisesRegex(ValueError, "LIMIT_EXHAUSTED"):
            self.collect(directory, parent, child)

    def test_whole_object_compatibility_preserves_other_fields_and_content_fail(self):
        directory, parent, child, field = self.job()
        pending = self.collect(directory, parent, child)
        first = self.read(directory / "semantic-attempt-1.json")
        candidate = copy.deepcopy(first)
        candidate["dimensions"][field]["grade"] = 2
        self.continue_child(parent, child, pending, candidate)
        proof = self.collect(directory, parent, child)
        self.assertEqual(self.read(directory / "semantic-revision-accepted.json")["local_revision"]["transport"],
                         "FULL_OBJECT_COMPATIBILITY")
        self.assertEqual(self.read(directory / "semantic-native-draft.json"), candidate)
        self.assertEqual(proof["local_revision"]["status"], "REVISED")
        # 合法的评分 FAIL 不是格式错误，不能为把分数变好而生成修订。
        directory, parent, child, field = self.job("content-fail", invalid=False)
        records = [json.loads(line) for line in child.read_text().splitlines()]
        for record in records:
            payload = record.get("payload", {})
            if payload.get("role") == "assistant":
                draft = json.loads(payload["content"][0]["text"])
                draft["dimensions"][field]["status"] = "FAIL"
                payload["content"][0]["text"] = json.dumps(draft)
        child.write_text("".join(json.dumps(record) + "\n" for record in records))
        proof = self.collect(directory, parent, child)
        persist_eval_execution_proof(proof, eval_dir=directory)
        final = finalize_eval_job(ROOT, eval_dir=directory, semantic_result_path=directory / "semantic-result.json")
        self.assertEqual(final["status"], "FAIL")
        self.assertFalse((directory / "semantic-revision.json").exists())

    def test_second_invalid_outside_change_or_wrong_reference_is_terminal(self):
        for failure in ("invalid", "outside", "reference"):
            with self.subTest(failure=failure):
                directory, parent, child, field = self.job(failure)
                pending = self.collect(directory, parent, child)
                patch = self.patch(pending, field, 4 if failure == "invalid" else 2)
                if failure == "outside":
                    patch["changes"].append({"op": "replace", "path": f"/dimensions/{field}/rationale", "value": "重评"})
                if failure == "reference":
                    patch["base_draft_ref"] = "wrong-base"
                self.continue_child(parent, child, pending, patch)
                with self.assertRaises(ValueError):
                    self.collect(directory, parent, child)
                self.assertTrue((directory / "semantic-attempt-2.json").exists())
                self.assertFalse((directory / "semantic-result.json").exists())
                with self.assertRaisesRegex(ValueError, "LIMIT_EXHAUSTED"):
                    self.collect(directory, parent, child)

    def test_early_poll_wrong_recipient_and_wrong_feedback_do_not_consume(self):
        for mode in ("poll", "recipient", "feedback"):
            with self.subTest(mode=mode):
                directory, parent, child, field = self.job(mode)
                pending = self.collect(directory, parent, child)
                if mode != "poll":
                    self.continue_child(parent, child, pending, self.patch(pending, field),
                        recipient="other-child" if mode == "recipient" else "eval-child",
                        feedback="wrong-feedback" if mode == "feedback" else None)
                with self.assertRaisesRegex(ValueError, "CONTINUATION_MISSING"):
                    self.collect(directory, parent, child)
                self.assertFalse((directory / "semantic-attempt-2.json").exists())
                self.assertFalse((directory / "semantic-result.json").exists())

    def test_wrong_model_identity_input_and_missing_read_never_get_first_slot(self):
        for mode in ("model", "identity", "input", "manifest-read"):
            with self.subTest(mode=mode):
                directory, parent, child, field = self.job(mode)
                if mode == "input":
                    (directory / "grader-input.json").write_text('{}')
                else:
                    records = [json.loads(line) for line in child.read_text().splitlines()]
                    for record in records:
                        payload = record.get("payload", {})
                        if mode == "model" and record["type"] == "turn_context":
                            payload["model"] = "gpt-5.6-sol"
                        if mode == "identity" and record["type"] == "session_meta":
                            payload["agent_role"] = "runtime_cio"
                    if mode == "manifest-read":
                        records = [record for record in records if record.get("payload", {}).get("call_id") != "manifest-read"]
                    child.write_text("".join(json.dumps(record) + "\n" for record in records))
                with self.assertRaises(ValueError):
                    self.collect(directory, parent, child)
                self.assertFalse((directory / "semantic-attempt-1.json").exists())
                self.assertFalse((directory / "semantic-result.json").exists())

    def test_binding_base_prefix_drift_rejected_before_second_slot(self):
        for mode in ("binding", "base", "prefix"):
            with self.subTest(mode=mode):
                directory, parent, child, field = self.job(mode)
                pending = self.collect(directory, parent, child)
                first = self.read(directory / "semantic-revision.json")
                self.continue_child(parent, child, pending, self.patch(pending, field))
                if mode == "binding":
                    path = directory / first["repair_request"]["binding_path"]
                    binding = self.read(path)
                    binding["allowed_paths"].append(f"/dimensions/{field}/rationale")
                    binding["content_hash"] = legacy_envelope_hash(binding, hash_field="content_hash")
                    path.write_text(json.dumps(binding))
                elif mode == "base":
                    path = directory / "semantic-attempt-1.json"
                    path.write_text(path.read_text().replace('4', '3', 1))
                else:
                    child.write_text(child.read_text().replace('2026-09-07', '2026-09-08', 1))
                with self.assertRaises(ValueError):
                    self.collect(directory, parent, child)
                self.assertFalse((directory / "semantic-attempt-2.json").exists())

    def test_finalizer_recomputes_local_proof_instead_of_trusting_resigned_summary(self):
        directory, parent, child, field = self.job()
        pending = self.collect(directory, parent, child)
        self.continue_child(parent, child, pending, self.patch(pending, field))
        proof = self.collect(directory, parent, child)
        persist_eval_execution_proof(proof, eval_dir=directory)
        accepted_path = directory / "semantic-revision-accepted.json"
        accepted = self.read(accepted_path)
        accepted["local_revision"]["changed_paths"] = []
        accepted["event_hash"] = legacy_envelope_hash(accepted, hash_field="event_hash")
        accepted_path.write_text(json.dumps(accepted))
        with self.assertRaisesRegex(ValueError, "PROOF_DRIFT"):
            finalize_eval_job(ROOT, eval_dir=directory, semantic_result_path=directory / "semantic-result.json")
        self.assertFalse((directory / "eval/result.json").exists())

    def test_instruction_and_skill_select_canonical_contract_without_launching(self):
        directory, _, _, _ = self.job()
        prompt = build_eval_smoke_prompt(ROOT, eval_dir=directory)
        self.assertIn("EVAL_LOCAL_REVISION_REQUIRED", prompt)
        self.assertIn("send_input", prompt)
        self.assertIn("child_session_id", prompt)
        skill = (ROOT / ".agents/skills/runtime-eval-grading/SKILL.md").read_text()
        frontmatter = skill.split("---", 2)[1]
        self.assertIn("name: runtime-eval-grading", frontmatter)
        self.assertIn("semantic-output-schema.json", skill)
        self.assertNotIn("必须输出 semantic-rubric-result/1.0.0", skill)

    def test_cli_pending_is_not_verified_and_same_collector_closes_once(self):
        from product.runtime.cli import main
        directory, parent, child, field = self.job()
        args = ["eval-execution-proof", "--repo", str(ROOT), "--eval-dir", str(directory),
                "--semantic-result", str(directory / "semantic-result.json"),
                "--sessions-root", str(parent.parent), "--collect-native-output"]
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(args)
        pending = json.loads(output.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(pending["next_state"], "EVAL_LOCAL_REVISION_REQUIRED")
        self.assertNotIn("proof_hash", pending)
        self.assertFalse((directory / "grader-execution-proof.json").exists())
        self.continue_child(parent, child, pending, self.patch(pending, field))
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(args)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["next_state"], "EVAL_EXECUTION_PROOF_VERIFIED")
        self.assertTrue((directory / "grader-execution-proof.json").exists())

    def test_commentary_is_not_a_second_draft_and_feedback_must_reach_child(self):
        directory, parent, child, field = self.job()
        pending = self.collect(directory, parent, child)
        commentary = message("assistant", "阶段进度，不是评分稿")
        commentary["payload"]["phase"] = "commentary"
        self.append(child, [commentary])
        self.continue_child(parent, child, pending, self.patch(pending, field))
        self.assertEqual(self.collect(directory, parent, child)["local_revision"]["status"], "REVISED")
        directory, parent, child, field = self.job("not-delivered")
        pending = self.collect(directory, parent, child)
        self.continue_child(parent, child, pending, self.patch(pending, field), feedback="wrong-input")
        # 父线程记录正确调用，但子线程未收到这份反馈，不能只凭调用宣称续投成功。
        records = [json.loads(line) for line in parent.read_text().splitlines()]
        arguments = json.loads(records[-1]["payload"]["arguments"])
        arguments["message"] = pending["feedback"]
        records[-1]["payload"]["arguments"] = json.dumps(arguments)
        parent.write_text("".join(json.dumps(record) + "\n" for record in records))
        with self.assertRaisesRegex(ValueError, "FEEDBACK_NOT_DELIVERED"):
            self.collect(directory, parent, child)
        self.assertFalse((directory / "semantic-attempt-2.json").exists())

    def test_missing_proof_marker_source_and_raw_drift_are_not_downgraded(self):
        for mode in ("marker", "prompt", "raw", "extra-final"):
            with self.subTest(mode=mode):
                directory, parent, child, _ = self.job(mode, invalid=False)
                proof = self.collect(directory, parent, child)
                persist_eval_execution_proof(proof, eval_dir=directory)
                if mode == "marker":
                    path = directory / "grader-execution-proof.json"
                    changed = self.read(path)
                    changed.pop("local_revision")
                    changed["proof_hash"] = legacy_envelope_hash(changed, hash_field="proof_hash")
                    path.write_text(json.dumps(changed))
                elif mode == "prompt":
                    path = directory / "grader-prompt.txt"
                    path.write_text(path.read_text() + "来源已改变")
                elif mode == "raw":
                    (directory / "semantic-attempt-1.json").write_text('{}')
                else:
                    self.append(child, [message("assistant", (directory / "semantic-attempt-1.json").read_text())])
                with self.assertRaises(ValueError):
                    finalize_eval_job(ROOT, eval_dir=directory, semantic_result_path=directory / "semantic-result.json")
                self.assertFalse((directory / "eval/result.json").exists())

    def test_model_projection_only_drops_enumerated_outer_metadata(self):
        fact = {"value": {"run_id": "原值内部标识", "schema_version": "原披露格式", "amount": 12},
                "unit": "USD", "period": "2026-Q1", "source_id": "filing", "as_of": "2026-04-01",
                "retrieved_at": "2026-04-02", "footnote": "不包含已终止业务"}
        claim = {"statement": "不能由收入增长推出利润改善", "counter_evidence": [fact],
                 "conflicts": [{"source_id": "other-source", "value": -12}],
                 "metadata": {"skill_execution": "来源正文里的同名字段"}}
        full = {"run_id": "job", "terminal_state": "COMPLETED", "failed_stage": None, "artifacts": {
            "evidence/gate.json": {"bundle_hash": "g", "allowed_evidence": [fact], "excluded": [{"reason_codes": ["FUTURE_AS_OF"]}]},
            "agents/runtime_company_analyst.json": {"run_id": "job", "skill_execution": {"skill_hash": "s"},
                "claims": [claim], "report_markdown": "中文正文\n脚注：不是利润预测"},
            "decision.json": {"run_id": "job", "action": "NO_TRADE", "maximum_notional": None,
                "target_weight_range": None, "risk_overrides": [{"reason": "真实硬约束"}]},
            "run_error.json": {"run_id": "job", "code": "保留完整错误"},
        }}
        original = copy.deepcopy(full)
        projected = runtime_eval_model_input(full)
        self.assertEqual(full, original)
        self.assertNotIn("bundle_hash", projected["artifacts"]["evidence/gate.json"])
        self.assertNotIn("skill_execution", projected["artifacts"]["agents/runtime_company_analyst.json"])
        self.assertEqual(projected["artifacts"]["evidence/gate.json"]["allowed_evidence"], [fact])
        self.assertEqual(projected["artifacts"]["agents/runtime_company_analyst.json"]["claims"], [claim])
        self.assertEqual(projected["artifacts"]["run_error.json"], full["artifacts"]["run_error.json"])
        self.assertEqual(projected["artifacts"]["decision.json"]["risk_overrides"], full["artifacts"]["decision.json"]["risk_overrides"])
        self.assertEqual(projected["artifacts"]["decision.json"]["maximum_notional"], None)

    def test_actual_model_view_read_and_resigned_projection_drift_fail_before_slot(self):
        from product.runtime.hashing import canonical_hash
        for mode in ("read", "value", "contract"):
            with self.subTest(mode=mode):
                directory, parent, child, _ = self.job(mode, invalid=False)
                if mode == "read":
                    records = [json.loads(line) for line in child.read_text().splitlines()]
                    records = [row for row in records if row.get("payload", {}).get("call_id") != "model-input-read"]
                    child.write_text("".join(json.dumps(row) + "\n" for row in records))
                else:
                    path = directory / "grader-model-input.json"
                    projected = self.read(path)
                    projected["artifacts"]["agents/runtime_company_analyst.json"]["thesis"] = "偷换研究"
                    path.write_text(json.dumps(projected))
                    if mode == "contract":
                        path = directory / "input-manifest.json"
                        manifest = self.read(path)
                        manifest["model_input_projection"]["input_hash"] = canonical_hash(projected)
                        path.write_text(json.dumps(manifest))
                        with self.assertRaisesRegex(ValueError, "PROJECTION_DRIFT"):
                            verify_runtime_eval_model_input(directory, manifest)
                with self.assertRaises(ValueError):
                    self.collect(directory, parent, child)
                self.assertFalse((directory / "semantic-attempt-1.json").exists())
                self.assertFalse((directory / "semantic-result.json").exists())

    def test_read_bytes_are_not_tokens_or_full_chain_cost(self):
        directory, parent, child, _ = self.job(invalid=False)
        proof = self.collect(directory, parent, child)
        diagnostics = proof["input_delivery_diagnostics"]
        self.assertEqual(diagnostics["model_input_bytes"], len((directory / "grader-model-input.json").read_bytes()))
        self.assertEqual(diagnostics["full_input_bytes"], len((directory / "grader-input.json").read_bytes()))
        self.assertEqual(diagnostics["byte_delta"], diagnostics["model_input_bytes"] - diagnostics["full_input_bytes"])
        self.assertIsNone(diagnostics["full_context_tokens"])
        self.assertIsNone(diagnostics["total_cost"])
        self.assertEqual(proof["telemetry"]["by_session"]["parent"]["input_tokens"], 100)
        self.assertEqual(proof["telemetry"]["by_session"]["dev_eval"]["input_tokens"], 50)

    def test_nonobject_first_grade_is_preserved_but_cannot_authorize_repair(self):
        for value in (None, True, 5, [{"invalid": "not-object"}]):
            with self.subTest(value=value):
                directory, parent, child, _ = self.job("nonobject-" + str(type(value).__name__), invalid=False)
                records = [json.loads(line) for line in child.read_text().splitlines()]
                for record in records:
                    if record.get("payload", {}).get("role") == "assistant":
                        record["payload"]["content"][0]["text"] = json.dumps(value)
                child.write_text("".join(json.dumps(record) + "\n" for record in records))
                with self.assertRaisesRegex(ValueError, "EVAL_NATIVE_DRAFT_INVALID"):
                    self.collect(directory, parent, child)
                self.assertTrue((directory / "semantic-attempt-1.json").exists())
                self.assertFalse((directory / "semantic-revision.json").exists())
                self.assertFalse((directory / "semantic-result.json").exists())


if __name__ == "__main__":
    unittest.main()
