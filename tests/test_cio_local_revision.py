"""主线程 CIO 原生 Stop 接缝；全部事件是合成输入，不启动模型。"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

from product.runtime import cio_local_revision as revision
from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.hashing import canonical_hash, file_hash, legacy_envelope_hash
from product.runtime.nested_codex import build_nested_codex_command
from product.runtime.predecision_cio_stage import _model_execution_proof
from tests import test_cio_handoff as fixture_helpers
from tests import test_cio_reference_handoff as predecision_helpers

REPO = fixture_helpers.REPO


class CioLocalRevisionTests(unittest.TestCase):
    def pending_fixture(self):
        from product.runtime.run_package import prepare_run
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name) / "council"
        prepare_run(REPO, fixture_path=REPO / "evals/fixtures/codex-native/normal-research.json",
                    run_dir=root, run_id="cio-pending-test", model="gpt-5.6-terra",
                    research_question="验证先启动后准备 CIO", authenticity_required=False)
        return root, None, "gpt-5.6-terra", str(REPO / "product")

    def prepare_pending_cio(self, root):
        from product.runtime.run_package import prepare_cio
        from product.runtime.cio_handoff import COUNCIL_METADATA, NATIVE_CIO_VERSION, build_cio_reference_map, cio_model_view
        from product.runtime.fixture_mcp import StatelessFixtureTools
        from tests.test_native_run_package import specialist_outputs, cio_output, read_json
        # 与宿主真实运行顺序一致：SessionStart 后才产生专业报告和 CIO 输入。
        specialist_outputs(root)
        prepare_cio(REPO, run_dir=root, model="gpt-5.6-terra")
        helper = fixture_helpers.CioHandoffTests()
        helper.run = root
        helper.invocation = read_json(root / "invocations/runtime_cio.json")
        helper.mapping = build_cio_reference_map(root, helper.invocation, helper.invocation["report_catalog"])
        helper.tools = StatelessFixtureTools(default_run_dir=root)
        helper.read([item["report_id"] for item in helper.invocation["report_catalog"]])
        draft = {key: value for key, value in cio_output(root).items() if key not in COUNCIL_METADATA}
        draft.update(schema_version=NATIVE_CIO_VERSION, report_selections=["runtime_company_analyst"])
        return cio_model_view(draft, helper.mapping)

    def fixture(self):
        helper = fixture_helpers.CioHandoffTests()
        helper.setUp()
        self.addCleanup(helper.doCleanups)
        helper.read([item["report_id"] for item in helper.invocation["report_catalog"]])
        return helper.run, helper.draft, helper.invocation["model"], str(REPO / "product")

    def predecision(self):
        helper, invocation, catalog, mapping = predecision_helpers.CioReferenceHandoffTests().prepare()
        self.addCleanup(helper.doCleanups)
        root = helper.target
        reports = list(mapping["reports"])
        reader = predecision_helpers.CioReferenceHandoffTests()
        reader.call(root, invocation, "read_reports", report_ids=reports)
        reader.call(root, invocation, "query", evidence_ids=list(mapping["evidence"]))
        draft = {"schema_version": "native-cio-draft/1.0.0", "report_selections": reports,
                 "status": "LOW_CONFIDENCE", "analysis_horizon": "两个季度的分析假设",
                 "judgment": "合成研究，保留未知", "reasoning": "证据不足，不伪造研究质量",
                 "thesis": "测试主张", "counter_thesis": "测试反证", "consensus": [],
                 "conflicts": ["尚未消解的冲突"], "business_outlook": "待核实",
                 "price_attractiveness": "未知", "account_fit": "当前账户适配未评估",
                 "key_facts": [{"fact": "合成事实", "report_ids": reports[:1],
                                "evidence_refs": list(mapping["evidence"])[:1], "reasoning": "仅测契约"}],
                 "challenge_dispositions": [], "macro_market_transmission": [{
                     "channel": "利率", "report_ids": reports[:1], "mechanism": "贴现率",
                     "assessment": "待核实", "limitations": "资料不足"}],
                 "unresolved_questions": [], "invalidation_conditions": ["新披露"],
                 "watch_plan": [{"item": "披露", "trigger": "发布", "reassess_on": "发布后"}],
                 "reevaluation_conditions": ["新披露"], "confidence_rationale": "证据不足",
                 "limitations": ["非组合建议"], "evidence_refs": list(mapping["evidence"])[:1]}
        helper._write_model_proof(draft)
        return root, draft, "gpt-6-luna", str(root)

    def launch(self, prepare, *, script_hooks=False):
        root, draft, model, cwd = prepare()
        invocation = root / "invocation"
        invocation.mkdir(exist_ok=True)
        prompt = invocation / "prompt.txt"
        if not prompt.exists():
            prompt.write_text("合成启动输入，不启动产品模型。")
        manifest_path = invocation / "environment-manifest.json"
        manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        command = build_nested_codex_command(
            codex_binary="codex", product_root=Path(cwd), run_dir=root, model=model,
            sqlite_home=root / "sqlite", log_dir=root / "logs", final_message_path=root / "last.json",
            hook_recorder_path=REPO / "product/runtime/codex_hook_recorder.py", enable_cio_local_revision=True,
        )
        if prepare == self.predecision:
            command.append("--skip-git-repo-check")
        manifest.update(cio_local_revision_version=revision.VERSION, command=command,
                        cio_local_revision_source_hashes=revision.implementation_hashes(REPO),
                        run_id=json.loads((root / "run_manifest.json").read_text())["run_id"],
                        model=model, prompt_hash=file_hash(prompt))
        manifest_path.write_text(json.dumps(manifest))
        env = {"STOCK_AGENT_RUN_DIR": str(root), "STOCK_AGENT_CIO_LOCAL_REVISION": revision.VERSION}
        base = {"session_id": "cio-main", "cwd": cwd, "model": model}
        def dispatch(payload):
            if not script_hooks:
                return handle_hook_event(payload, environ=env)
            option = next(value for value in command if value.startswith(f"hooks.{payload['hook_event_name']}="))
            hook = tomllib.loads(option)["hooks"][payload["hook_event_name"]][0]["hooks"][0]["command"]
            result = subprocess.run(
                ["/bin/sh", "-lc", hook], input=json.dumps(payload, ensure_ascii=False),
                text=True, cwd=cwd, capture_output=True, timeout=30, check=False,
                env={"PATH": os.defpath, "HOME": str(root), "SHELL": "/bin/sh",
                     "PYTHONDONTWRITEBYTECODE": "1", **env},
            )
            if result.returncode != 0:
                raise ValueError(result.stderr.strip())
            return revision._records(root)[-1], json.loads(result.stdout)
        start, _ = dispatch({**base, "hook_event_name": "SessionStart", "source": "startup"})
        self.assertEqual(start["execution_context"], "MAIN_THREAD")
        def stop(candidate, **override):
            message = json.dumps(candidate, ensure_ascii=False)
            response_text = message if prepare == self.predecision else "CIO_DRAFT_READY_FOR_DETERMINISTIC_FINALIZATION"
            if prepare != self.predecision:
                (root / "cio").mkdir(exist_ok=True)
                (root / "cio/runtime_cio.json").write_text(message)
            return dispatch({**base, "hook_event_name": "Stop", "turn_id": "turn",
                             "last_assistant_message": response_text, **override})
        def complete(candidate):
            message = json.dumps(candidate, ensure_ascii=False) if prepare == self.predecision else "CIO_DRAFT_READY_FOR_DETERMINISTIC_FINALIZATION"
            (invocation / "codex-events.jsonl").write_text("\n".join(json.dumps(event) for event in (
                {"type": "thread.started", "thread_id": base["session_id"]}, {"type": "turn.started"},
                {"type": "item.completed", "item": {"type": "agent_message", "text": message}},
                {"type": "turn.completed"})) + "\n")
            (invocation / "final-message.json").write_text(message)
            return revision.verify_completed(root, candidate=candidate)
        return root, draft, stop, complete, env, base

    def test_external_script_hooks_without_pythonpath_preserve_raw_and_complete(self):
        for repair in (False, True):
            with self.subTest(repair=repair):
                root, draft, stop, complete, _, _ = self.launch(self.predecision, script_hooks=True)
                self.assertFalse(root.is_relative_to(REPO))
                candidate = {**draft, "confidence_rationale": 12} if repair else draft
                first, response = stop(candidate)
                raw = root / first["output_capture"]["raw_path"]
                original = raw.read_bytes()
                if repair:
                    self.assertEqual(first["status"], "REPAIR_REQUESTED", first)
                    self.assertEqual(json.loads(response["reason"])["allowed_paths"], ["/confidence_rationale"])
                    second, response = stop(draft)
                    self.assertEqual(second["status"], "SAVED", second)
                else:
                    self.assertEqual(first["status"], "SAVED", first)
                self.assertEqual(response, {})
                self.assertEqual(complete(draft)["attempts"], 2 if repair else 1)
                self.assertEqual(raw.read_bytes(), original)
                self.assertEqual(json.loads(original), candidate)
                self.assertFalse((root / "decision.json").exists())
                self.assertFalse((root / "risk.json").exists())

    def test_external_script_hooks_keep_protocol_binding_and_completion_gates(self):
        root, draft, stop, complete, env, _ = self.launch(self.predecision, script_hooks=True)
        before = (root / revision.LOG).read_bytes()
        with self.assertRaisesRegex(ValueError, "COMPLETION_INVALID"):
            complete(draft)
        for override in ({"model": "wrong"}, {"session_id": "foreign"},
                         {"agent_id": "pretend-child"}, {"cwd": "/foreign"}):
            with self.subTest(override=override), self.assertRaisesRegex(ValueError, "BINDING_INVALID|SESSION_UNBOUND"):
                stop(draft, **override)
            self.assertEqual((root / revision.LOG).read_bytes(), before)
        env["STOCK_AGENT_CIO_LOCAL_REVISION"] = "invalid"
        with self.assertRaisesRegex(ValueError, "PROTOCOL_INVALID"):
            stop(draft)
        self.assertEqual((root / revision.LOG).read_bytes(), before)
        self.assertFalse((root / "invocation/cio-drafts").exists())
        self.assertFalse((root / "cio-research-synthesis.json").exists())

    def test_both_main_cio_entries_repair_one_field_preserve_base_and_reverify(self):
        for prepare, field, bad in ((self.fixture, "confidence", "bad"),
                                    (self.predecision, "confidence_rationale", 12)):
            with self.subTest(entry=prepare.__name__):
                root, draft, stop, complete, _, _ = self.launch(prepare)
                first, response = stop({**draft, field: bad})
                self.assertEqual(first["status"], "REPAIR_REQUESTED", first)
                feedback = json.loads(response["reason"])
                self.assertEqual(feedback["allowed_paths"], ["/" + field])
                self.assertNotIn("binding_hash", feedback)
                original = (root / first["output_capture"]["raw_path"]).read_bytes()
                second, response = stop(draft)
                self.assertEqual(second["status"], "SAVED", second)
                self.assertEqual(response, {})
                self.assertEqual(second["local_revision"]["changed_paths"], ["/" + field])
                self.assertNotIn("child_session_id", second)
                self.assertEqual(complete(draft)["attempts"], 2)
                self.assertEqual((root / first["output_capture"]["raw_path"]).read_bytes(), original)
                with self.assertRaisesRegex(ValueError, "NOT_AUTHORIZED"):
                    stop(draft)
                if prepare == self.predecision:
                    proof = _model_execution_proof(REPO, root, json.loads((root / "predecision-cio-request.json").read_text()))
                    self.assertEqual(proof["cio_local_revision"]["attempts"], 2)
                    self.assertFalse((root / "decision.json").exists())
                    from product.runtime.predecision_cio_stage import finalize_predecision_cio_research
                    self.assertEqual(finalize_predecision_cio_research(REPO, root)["status"], "COMPLETED_RESEARCH_SYNTHESIS")
                else:
                    self.assertFalse((root / "risk.json").exists())
                    from product.runtime.run_package import finalize_cio
                    self.assertEqual(finalize_cio(REPO, run_dir=root)["next_state"], "COMPLETED")
                    trace = json.loads((root / "decision_trace.json").read_text())
                    self.assertTrue(trace["risk_lineage"])
                    self.assertEqual(next(item["proof"]["attempts"] for item in trace["events"]
                                          if item["stage"] == "CIO_LOCAL_REVISION_VERIFIED"), 2)

    def test_scope_second_failure_technical_fields_and_illegal_reference_fail_closed(self):
        for change in ({"thesis": "重写未授权结论"}, {"confidence": "still-bad"},
                       {"evidence_refs": ["e.foreign"]}):
            with self.subTest(change=change):
                root, draft, stop, complete, _, _ = self.launch(self.fixture)
                stop({**draft, "confidence": "bad"})
                result, response = stop({**draft, **change})
                self.assertEqual(result["status"], "FAILED")
                self.assertFalse(response["continue"])
                with self.assertRaisesRegex(ValueError, "COMPLETION_INVALID"):
                    complete({**draft, **change})
        root, draft, stop, complete, _, _ = self.launch(self.fixture)
        result, response = stop({**draft, "run_id": "spoof"})
        self.assertEqual(result["status"], "FAILED")
        self.assertNotIn("repair_request", result)
        self.assertFalse(response["continue"])

    def test_wrong_identity_model_configuration_no_target_attempt(self):
        root, draft, stop, _, _, _ = self.launch(self.fixture)
        before = (root / revision.LOG).read_bytes()
        for override in ({"model": "wrong"}, {"session_id": "foreign"}, {"agent_id": "pretend-child"}, {"cwd": "/foreign"}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                stop(draft, **override)
            self.assertEqual((root / revision.LOG).read_bytes(), before)
        self.assertFalse((root / "invocation/cio-drafts").exists())
        manifest_path = root / "invocation/environment-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["extra"] = "drift"
        manifest_path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "SESSION_UNBOUND"):
            stop(draft)
        self.assertFalse((root / "invocation/cio-drafts").exists())

    def test_host_recomputes_raw_binding_scope_and_summary_not_just_saved(self):
        root, draft, stop, complete, _, _ = self.launch(self.fixture)
        first, _ = stop({**draft, "confidence": "bad"})
        second, _ = stop(draft)
        complete(draft)
        path = root / revision.LOG
        original = path.read_bytes()
        values = [json.loads(line) for line in path.read_text().splitlines()]
        values[-1]["local_revision"]["changed_paths"] = ["/thesis"]
        values[-1]["event_hash"] = legacy_envelope_hash(values[-1], hash_field="event_hash")
        path.write_text("\n".join(json.dumps(item) for item in values) + "\n")
        with self.assertRaisesRegex(ValueError, "PROOF_DRIFT"):
            complete(draft)
        path.write_bytes(original)
        base = root / first["output_capture"]["raw_path"]
        base.write_text(base.read_text() + " ")
        with self.assertRaisesRegex(ValueError, "RAW_DRIFT"):
            complete(draft)

    def test_missing_actual_report_reads_cannot_enter_repair_or_publish(self):
        root, draft, stop, _, _, _ = self.launch(self.fixture)
        (root / "events/mcp/events.jsonl").unlink()
        result, response = stop(draft)
        self.assertEqual(result["status"], "FAILED")
        self.assertIn("NOT_READ", result["failure_code"])
        self.assertNotIn("repair_request", result)
        self.assertFalse(response["continue"])

    def test_first_valid_draft_and_located_reference_correction(self):
        for prepare in (self.fixture, self.predecision):
            with self.subTest(entry=prepare.__name__):
                root, draft, stop, complete, _, _ = self.launch(prepare)
                result, response = stop(draft)
                self.assertEqual(result["status"], "SAVED", result)
                self.assertEqual(response, {})
                self.assertEqual(complete(draft)["attempts"], 1)
        root, draft, stop, complete, _, _ = self.launch(self.fixture)
        result, response = stop({**draft, "evidence_refs": ["e.foreign"]})
        self.assertEqual(result["status"], "REPAIR_REQUESTED", result)
        paths = json.loads(response["reason"])["allowed_paths"]
        self.assertEqual(paths, ["/evidence_refs/0"])
        corrected = copy.deepcopy(draft)
        # 只选该原稿位置的合法引用；长度变更或其它引用漂移仍不得借机修正。
        corrected["evidence_refs"] = draft["evidence_refs"][:1]
        result, _ = stop(corrected)
        self.assertEqual(result["status"], "SAVED", result)
        self.assertEqual(complete(corrected)["attempts"], 2)

    def test_no_trade_zero_still_rejected_and_only_null_field_repaired(self):
        root, draft, stop, complete, _, _ = self.launch(self.fixture)
        valid = {**draft, "action": "NO_TRADE", "target_weight_range": None,
                 "maximum_notional": None, "no_trade_reason": "DATA_GAP",
                 "no_trade_explanation": "合成缺口，仅测试安全契约", "reevaluation_conditions": ["新披露"]}
        result, response = stop({**valid, "maximum_notional": 0})
        self.assertEqual(result["status"], "REPAIR_REQUESTED", result)
        self.assertEqual(json.loads(response["reason"])["allowed_paths"], ["/maximum_notional"])
        result, _ = stop(valid)
        self.assertEqual(result["status"], "SAVED", result)
        complete(valid)

    def test_completion_requires_real_hook_records_even_with_valid_artifacts(self):
        root, draft, stop, complete, _, _ = self.launch(self.fixture)
        with self.assertRaisesRegex(ValueError, "COMPLETION_INVALID"):
            complete(draft)
        self.assertFalse((root / "invocation/cio-drafts").exists())

    def test_command_has_native_hooks_no_sandbox_bypass_and_no_barrier_collision(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            kwargs = dict(codex_binary="codex", product_root=REPO / "product", run_dir=root,
                          model="gpt-5.6-terra", sqlite_home=root / "sqlite", log_dir=root / "logs",
                          final_message_path=root / "final.json",
                          hook_recorder_path=REPO / "product/runtime/codex_hook_recorder.py")
            command = build_nested_codex_command(**kwargs, enable_cio_local_revision=True)
            import tomllib
            for event in ("Stop", "SessionStart"):
                option = next(value for value in command if value.startswith(f"hooks.{event}="))
                config = tomllib.loads(option)
                self.assertEqual(config["hooks"][event][0]["hooks"][0]["type"], "command")
            self.assertEqual(command[command.index("--sandbox") + 1], "workspace-write")
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", command)
            with self.assertRaisesRegex(ValueError, "CONTRACT_CONFLICT"):
                build_nested_codex_command(**kwargs, enable_cio_local_revision=True, enable_parent_stop_barrier=True)

    def test_launch_bytes_are_scoped_not_tokens_and_recomputed_from_originals(self):
        for prepare in (self.fixture, self.predecision):
            with self.subTest(entry=prepare.__name__):
                root, draft, stop, complete, _, _ = self.launch(prepare)
                stop(draft)
                proof = complete(draft)
                diagnostic = proof["delivery_diagnostics"]
                self.assertEqual(diagnostic["prompt_bytes"], len((root / "invocation/prompt.txt").read_bytes()))
                self.assertIsNone(diagnostic["token_usage"])
                self.assertIsNone(diagnostic["total_cost"])
                self.assertEqual(diagnostic["total_prompt_baseline"], "NOT_OBSERVED")
                if diagnostic["comparison_status"] == "SAME_FROZEN_INPUT_REPRESENTATION":
                    self.assertEqual(diagnostic["byte_delta"], diagnostic["model_input_bytes"] - diagnostic["full_input_bytes"])
                path = root / revision.LOG
                records = [json.loads(line) for line in path.read_text().splitlines()]
                records[0]["delivery_diagnostics"]["prompt_bytes"] += 1
                records[0]["event_hash"] = legacy_envelope_hash(records[0], hash_field="event_hash")
                path.write_text("".join(json.dumps(record) + "\n" for record in records))
                with self.assertRaisesRegex(ValueError, "DELIVERY_DRIFT"):
                    complete(draft)

    def test_session_start_before_specialists_and_prepare_cio_can_finalize(self):
        from product.runtime.run_package import finalize_cio
        root, _, stop, complete, _, _ = self.launch(self.pending_fixture)
        self.assertFalse((root / "inputs/runtime_cio.model.json").exists())
        draft = self.prepare_pending_cio(root)
        result, response = stop(draft)
        self.assertEqual(result["status"], "SAVED", result)
        self.assertEqual(response, {})
        proof = complete(draft)
        self.assertEqual(proof["launch_delivery_diagnostics"]["comparison_status"], "NOT_COMPARABLE")
        self.assertEqual(proof["delivery_diagnostics"]["comparison_status"], "SAME_FROZEN_INPUT_REPRESENTATION")
        self.assertEqual(proof["delivery_diagnostics"]["full_input_hash"],
                         canonical_hash(json.loads((root / "inputs/runtime_cio.json").read_text())))
        self.assertEqual(finalize_cio(REPO, run_dir=root)["next_state"], "COMPLETED")
        self.assertTrue(json.loads((root / "decision_trace.json").read_text())["risk_lineage"])
        for relative in ("decision.json", "report.md", "decision_trace.json"):
            self.assertTrue((root / relative).is_file(), relative)
        # 收尾不止检查文件存在：继续经过真实 Trace、artifact replay 和 Eval 输入消费者。
        from product.runtime.trace_validation import validate_decision_trace
        from product.runtime.replay import replay_run
        from product.runtime.runtime_eval import prepare_eval_job
        from product.runtime.schema_validation import validate_schema_instance
        trace = json.loads((root / "decision_trace.json").read_text())
        validate_schema_instance(trace, json.loads((REPO / "product/schemas/runtime/decision-trace.schema.json").read_text()))
        validate_decision_trace(trace, run_dir=root)
        self.assertEqual(replay_run(REPO, run_dir=root)["status"], "PASSED")
        prepared = prepare_eval_job(REPO, run_dir=root, eval_dir=root.parent / "eval-input", eval_id="phase-seam-eval")
        self.assertEqual(prepared["hard_gate_status"], "PASS")
        self.assertEqual(prepared["next_state"], "SEMANTIC_GRADING_REQUIRED")

    def test_pending_input_is_bound_before_single_local_repair(self):
        root, _, stop, complete, _, _ = self.launch(self.pending_fixture)
        draft = self.prepare_pending_cio(root)
        first, _ = stop({**draft, "confidence": "bad"})
        self.assertEqual(first["status"], "REPAIR_REQUESTED", first)
        second, _ = stop(draft)
        self.assertEqual(second["status"], "SAVED", second)
        self.assertEqual(first["delivery_diagnostics"], second["delivery_diagnostics"])
        self.assertEqual(complete(draft)["attempts"], 2)

    def test_pending_binding_rejects_same_size_input_change_before_repair_or_host(self):
        from product.runtime.cio_handoff import fixture_cio_model_input
        for repair in (False, True):
            with self.subTest(repair=repair):
                root, _, stop, complete, _, _ = self.launch(self.pending_fixture)
                draft = self.prepare_pending_cio(root)
                stop({**draft, "confidence": "bad"} if repair else draft)
                original = (root / revision.LOG).read_bytes()
                path = root / "inputs/runtime_cio.json"
                value = json.loads(path.read_text())
                # 两份投影同步改变，且字符数相同；不能只靠字节数或投影相等放行。
                question = value["research_question"]
                value["research_question"] = ("不" if question[0] != "不" else "未") + question[1:]
                self.assertEqual(len(question.encode()), len(value["research_question"].encode()))
                path.write_text(json.dumps(value, ensure_ascii=False))
                (root / "inputs/runtime_cio.model.json").write_text(
                    json.dumps(fixture_cio_model_input(root, value), ensure_ascii=False))
                with self.assertRaises(ValueError):
                    stop(draft) if repair else complete(draft)
                self.assertEqual((root / revision.LOG).read_bytes(), original)
                self.assertFalse((root / "decision.json").exists())

    def test_pending_phase_still_rejects_prompt_and_stop_binding_tampering(self):
        for target in ("prompt", "stop_hash", "missing_stop_binding"):
            with self.subTest(target=target):
                root, _, stop, complete, _, _ = self.launch(self.pending_fixture)
                draft = self.prepare_pending_cio(root)
                stop(draft)
                if target == "prompt":
                    path = root / "invocation/prompt.txt"
                    path.write_text(path.read_text() + "未经批准的改变")
                else:
                    path = root / revision.LOG
                    records = [json.loads(line) for line in path.read_text().splitlines()]
                    if target == "stop_hash":
                        records[-1]["delivery_diagnostics"]["model_input_hash"] = "0" * 64
                    else:
                        records[-1].pop("delivery_diagnostics")
                    records[-1]["event_hash"] = legacy_envelope_hash(records[-1], hash_field="event_hash")
                    path.write_text("".join(json.dumps(record) + "\n" for record in records))
                with self.assertRaisesRegex(ValueError, "PROMPT_DRIFT|DELIVERY_DRIFT"):
                    complete(draft)


if __name__ == "__main__":
    unittest.main()
