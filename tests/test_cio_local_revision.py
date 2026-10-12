"""CIO 真实业务/有限补丁与旧记录只读重验；明示历史向量不证明宿主执行。"""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from product.runtime import cio_local_revision as revision
from product.runtime.codex_hook_recorder import handle_hook_event
from product.runtime.hashing import canonical_hash, file_hash, legacy_envelope_hash
from product.runtime.local_revision import bind, resolve, _apply, located_paths
from product.runtime.schema_validation import schema_issue_locations, validate_schema_instance
from tests import test_cio_handoff as fixture_helpers
from tests import test_cio_reference_handoff as predecision_helpers

REPO = fixture_helpers.REPO


class CioLocalRevisionTests(unittest.TestCase):
    def pending_fixture(self):
        from product.runtime.run_package import prepare_run
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name).resolve() / "council"
        prepared = prepare_run(REPO, fixture_path=REPO / "evals/fixtures/codex-native/normal-research.json",
            run_dir=root, run_id="cio-pending-test", model="gpt-6-luna",
            research_question="验证 CIO 输入冻结前后只读绑定", authenticity_required=False)
        self.assertTrue((root / "run_manifest.json").is_file(), prepared)
        return root, None, "gpt-6-luna", str(REPO / "product")

    def prepare_pending_cio(self, root):
        from product.runtime.run_package import prepare_cio
        from product.runtime.cio_handoff import COUNCIL_METADATA, NATIVE_CIO_VERSION, build_cio_reference_map, cio_model_view
        from product.runtime.fixture_mcp import StatelessFixtureTools
        from tests.test_native_run_package import specialist_outputs, cio_output, read_json
        specialist_outputs(root)
        prepared = prepare_cio(REPO, run_dir=root, model="gpt-6-luna")
        self.assertEqual(prepared["next_state"], "CIO_SYNTHESIS_REQUIRED", prepared)
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
        return helper.run.resolve(), helper.draft, helper.invocation["model"], str(REPO / "product")

    def predecision(self):
        reader = predecision_helpers.CioReferenceHandoffTests()
        self.addCleanup(reader.doCleanups)
        helper, invocation, _, mapping = reader.prepare()
        root = helper.target.resolve()
        reports = list(mapping["reports"])
        for name, arguments in (("read_reports", {"report_ids": reports}),
                                ("query", {"evidence_ids": list(mapping["evidence"])})):
            response = reader.call(root, invocation, name, **arguments)
            self.assertNotIn("error", response, response)
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
        # 上游 mock、来源文件和合成模型遥测仅属于历史消费者夹具。
        helper._write_model_proof(draft)
        return root, draft, "gpt-6-luna", str(root)

    def write_historical_launch_fixture(self, root, model, cwd):
        """显式旧配置/Start向量；标记不是可执行命令，不构造或启动旧模型。"""
        directory = root / "invocation"
        directory.mkdir(exist_ok=True)
        prompt = directory / "prompt.txt"
        if not prompt.exists():
            prompt.write_text("合成历史输入，不启动产品模型。")
        path = directory / "environment-manifest.json"
        environment = json.loads(path.read_text()) if path.exists() else {}
        command = environment.get("command", ["historical-fixture-only", "--model", model, "-C", cwd])
        command += ["hooks.SessionStart=historical-fixture-only", "hooks.Stop=historical-fixture-only"]
        environment.update(cio_local_revision_version=revision.VERSION, command=command,
            cio_local_revision_source_hashes=revision.implementation_hashes(REPO),
            run_id=json.loads((root / "run_manifest.json").read_text())["run_id"],
            model=model, prompt_hash=file_hash(prompt))
        path.write_text(json.dumps(environment))
        payload = {"hook_event_name": "Stop", "session_id": "synthetic-cio-main", "cwd": cwd, "model": model}
        launch = {"run_id": environment["run_id"], "model": model,
                  "environment_hash": file_hash(path), "prompt_hash": file_hash(prompt)}
        start = {"version": revision.VERSION, "execution_context": "MAIN_THREAD", "hook_event_name": "SessionStart",
                 "session_id": payload["session_id"], "launch_binding": launch,
                 "delivery_diagnostics": revision._delivery(root)}
        self.write_historical_rows(root, [start])
        return payload, start

    @staticmethod
    def write_historical_rows(root, records):
        values = [{**record, "event_hash": legacy_envelope_hash(record, hash_field="event_hash")}
                  for record in records]
        (root / revision.LOG).write_text("".join(json.dumps(value, ensure_ascii=False) + "\n" for value in values))
        return values

    def write_historical_execution_fixture(self, root, draft, payload, start, *, base=None):
        """显式历史终态及原件；不模拟Stop响应、自动修订许可或当前作者执行。"""
        schema, task, _, _ = revision._contract(REPO, root)
        final = json.dumps(draft, ensure_ascii=False) if (root / "predecision-cio-request.json").is_file() else "CIO_DRAFT_READY_FOR_DETERMINISTIC_FINALIZATION"
        common = {"version": revision.VERSION, "execution_context": "MAIN_THREAD", "hook_event_name": "Stop",
                  "session_id": payload["session_id"], "launch_binding": start["launch_binding"],
                  "delivery_diagnostics": revision._delivery(root), "trusted_task_binding": task,
                  "identity_binding": {"status": "BOUND"}}
        records = [start]
        for number, value in enumerate(([base, draft] if base is not None else [draft]), 1):
            message = json.dumps(value, ensure_ascii=False)
            relative = f"invocation/cio-drafts/synthetic-{number}.json"
            path = root / relative
            path.parent.mkdir(exist_ok=True)
            path.write_text(message + "\n")
            path.chmod(0o600)
            record = {**common, "attempt": number, "output_capture": {
                "raw_path": relative, "raw_output_hash": canonical_hash({"assistant_message": message})},
                "final_response_hash": canonical_hash({"assistant_message": final})}
            if base is not None and number == 1:
                # 只生成旧格式不可变binding用于真实reader重验，不签发运行权限。
                repair = {"validation_error": "SCHEMA_TYPE_MISMATCH"}
                bound = bind(root, {**payload, "last_assistant_message": message}, record,
                    record["output_capture"], repair, schema_issue_locations(base, schema))
                self.assertIsNotNone(bound)
                record.update(status="REPAIR_REQUESTED", repair_request={**repair, **bound})
            else:
                record.update(status="SAVED", candidate_hash=canonical_hash(draft))
                if base is not None:
                    resolve(root, {**payload, "last_assistant_message": message}, record, records[1])
            record["event_hash"] = legacy_envelope_hash(record, hash_field="event_hash")
            records.append(record)
        self.write_historical_rows(root, records)
        (root / "invocation/codex-events.jsonl").write_text("".join(json.dumps(event) + "\n" for event in (
            {"type": "thread.started", "thread_id": payload["session_id"]}, {"type": "turn.started"},
            {"type": "item.completed", "item": {"type": "agent_message", "text": final}}, {"type": "turn.completed"})))
        (root / "invocation/final-message.json").write_text(final)
        return records

    def historical_fixture(self, prepare, *, repair=False):
        root, draft, model, cwd = prepare()
        payload, start = self.write_historical_launch_fixture(root, model, cwd)
        field = "confidence_rationale" if prepare == self.predecision else "confidence"
        base = {**draft, field: 12 if field == "confidence_rationale" else "bad"} if repair else None
        records = self.write_historical_execution_fixture(root, draft, payload, start, base=base)
        return root, draft, payload, records

    def test_retired_cio_hooks_have_no_writer_or_side_effect(self):
        self.assertFalse(hasattr(revision, "handle"))
        self.assertFalse(hasattr(revision, "_submission"))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "absent"
            for event in ("SessionStart", "Stop"):
                with self.subTest(event=event), self.assertRaisesRegex(ValueError, "NATIVE_HOST_EXECUTION_REQUIRED"):
                    handle_hook_event({"hook_event_name": event}, environ={"STOCK_AGENT_RUN_DIR": str(root),
                        "STOCK_AGENT_CIO_LOCAL_REVISION": revision.VERSION})
                self.assertFalse(root.exists())

    def test_both_cio_business_contracts_accept_first_draft_without_hook_records(self):
        for prepare in (self.fixture, self.predecision):
            with self.subTest(entry=prepare.__name__):
                root, draft, _, _ = prepare()
                schema, _, reserved, validate = revision._contract(REPO, root)
                self.assertTrue(reserved.isdisjoint(draft))
                validate_schema_instance(draft, schema)
                validate(draft)
                self.assertFalse((root / revision.LOG).exists())
                self.assertFalse((root / "decision.json").exists())
                self.assertFalse((root / "risk.json").exists())

    def test_explicit_field_patch_preserves_base_and_revalidates_both_cio_contracts(self):
        for prepare, field, bad in ((self.fixture, "confidence", "bad"),
                                    (self.predecision, "confidence_rationale", 12)):
            with self.subTest(entry=prepare.__name__):
                root, draft, _, _ = prepare()
                invalid = {**draft, field: bad}
                original = copy.deepcopy(invalid)
                schema, _, _, validate = revision._contract(REPO, root)
                with self.assertRaises(ValueError):
                    validate_schema_instance(invalid, schema)
                paths = located_paths(schema_issue_locations(invalid, schema), exact_fields=True)
                self.assertEqual(paths, ["/" + field])
                corrected = _apply(invalid, [{"op": "replace", "path": "/" + field, "value": draft[field]}], paths)
                validate_schema_instance(corrected, schema)
                validate(corrected)
                self.assertEqual(corrected, draft)
                self.assertEqual(invalid, original)
                with self.assertRaisesRegex(ValueError, "LOCAL_REVISION_OUT_OF_SCOPE"):
                    _apply(invalid, [{"op": "replace", "path": "/thesis", "value": "重写结论"}], paths)
                self.assertFalse((root / revision.LOG).exists())

    def test_full_validation_rejects_second_invalid_reference_and_technical_echo(self):
        root, draft, _, _ = self.fixture()
        schema, _, _, validate = revision._contract(REPO, root)
        for change in ({"confidence": "still-bad"}, {"run_id": "spoof"}, {"evidence_refs": ["e.foreign"]}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                candidate = {**draft, **change}
                validate_schema_instance(candidate, schema)
                validate(candidate)
        self.assertFalse((root / revision.LOG).exists())
        self.assertFalse((root / "decision.json").exists())

    def test_missing_actual_report_reads_cannot_validate_or_publish(self):
        root, draft, _, _ = self.fixture()
        (root / "events/mcp/events.jsonl").unlink()
        _, _, _, validate = revision._contract(REPO, root)
        with self.assertRaisesRegex(ValueError, "NOT_READ"):
            validate(draft)
        self.assertFalse((root / revision.LOG).exists())
        self.assertFalse((root / "decision.json").exists())

    def test_no_trade_zero_is_rejected_then_only_explicit_null_patch_passes(self):
        root, draft, _, _ = self.fixture()
        valid = {**draft, "action": "NO_TRADE", "target_weight_range": None, "maximum_notional": None,
                 "no_trade_reason": "DATA_GAP", "no_trade_explanation": "合成缺口，仅测试安全契约",
                 "reevaluation_conditions": ["新披露"]}
        invalid = {**valid, "maximum_notional": 0}
        schema, _, _, validate = revision._contract(REPO, root)
        with self.assertRaises(ValueError):
            validate_schema_instance(invalid, schema)
        paths = located_paths(schema_issue_locations(invalid, schema), exact_fields=True)
        self.assertEqual(paths, ["/maximum_notional"])
        fixed = _apply(invalid, [{"op": "replace", "path": paths[0], "value": None}], paths)
        validate_schema_instance(fixed, schema)
        validate(fixed)
        self.assertEqual(fixed, valid)
        self.assertEqual(invalid["maximum_notional"], 0)

    def test_historical_first_and_repaired_records_are_readonly_not_execution_proof(self):
        for prepare in (self.fixture, self.predecision):
            for repair in (False, True):
                with self.subTest(entry=prepare.__name__, repair=repair):
                    root, draft, _, _ = self.historical_fixture(prepare, repair=repair)
                    before = {path: file_hash(path) for path in root.rglob("*") if path.is_file()}
                    proof = revision.verify_completed(root, candidate=draft)
                    self.assertEqual(proof["attempts"], 2 if repair else 1)
                    self.assertEqual(before, {path: file_hash(path) for path in root.rglob("*") if path.is_file()})
                    self.assertFalse((root / "decision.json").exists())
                    self.assertFalse((root / "risk.json").exists())

    def test_historical_reader_rejects_identity_model_configuration_and_prompt_drift(self):
        root, draft, payload, _ = self.historical_fixture(self.fixture)
        final = (root / "invocation/final-message.json").read_text()
        before = (root / revision.LOG).read_bytes()
        for override in ({"model": "wrong"}, {"session_id": "foreign"},
                         {"agent_id": "pretend-child"}, {"cwd": "/foreign"}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                revision.verify(root, payload={**payload, "last_assistant_message": final, **override}, candidate=draft)
            self.assertEqual((root / revision.LOG).read_bytes(), before)
        for name in ("invocation/environment-manifest.json", "invocation/prompt.txt"):
            path = root / name
            original = path.read_bytes()
            path.write_bytes(original + b" ")
            with self.assertRaises(ValueError):
                revision.verify_completed(root, candidate=draft)
            path.write_bytes(original)
        self.assertEqual((root / revision.LOG).read_bytes(), before)

    def test_historical_reader_recomputes_base_scope_summary_and_duplicate_keys(self):
        for defect in ("summary", "raw", "scope", "candidate", "duplicate-key", "extra-stop", "missing-start"):
            with self.subTest(defect=defect):
                root, draft, _, records = self.historical_fixture(self.fixture, repair=True)
                if defect in {"raw", "duplicate-key"}:
                    path = root / records[1]["output_capture"]["raw_path"]
                    path.write_text(path.read_text() + " " if defect == "raw" else '{"confidence": 0, "confidence": 1}')
                elif defect == "candidate":
                    draft = {**draft, "thesis": "改写结论"}
                else:
                    if defect == "summary":
                        records[-1]["local_revision"]["changed_paths"] = ["/thesis"]
                    elif defect == "scope":
                        path = root / records[-1]["output_capture"]["raw_path"]
                        value = {**draft, "thesis": "改写结论"}
                        message = json.dumps(value, ensure_ascii=False)
                        path.write_text(message + "\n")
                        records[-1]["output_capture"]["raw_output_hash"] = canonical_hash({"assistant_message": message})
                    elif defect == "extra-stop":
                        records.append(copy.deepcopy(records[-1]))
                    else:
                        records.pop(0)
                    self.write_historical_rows(root, records)
                before = {path: file_hash(path) for path in root.rglob("*") if path.is_file()}
                with self.assertRaises(ValueError):
                    revision.verify_completed(root, candidate=draft)
                self.assertEqual(before, {path: file_hash(path) for path in root.rglob("*") if path.is_file()})

    def test_historical_delivery_bytes_are_scoped_not_tokens_and_resigned_drift_fails(self):
        for prepare in (self.fixture, self.predecision):
            with self.subTest(entry=prepare.__name__):
                root, draft, _, records = self.historical_fixture(prepare)
                diagnostic = revision.verify_completed(root, candidate=draft)["delivery_diagnostics"]
                self.assertEqual(diagnostic["prompt_bytes"], len((root / "invocation/prompt.txt").read_bytes()))
                self.assertIsNone(diagnostic["token_usage"])
                self.assertIsNone(diagnostic["total_cost"])
                self.assertEqual(diagnostic["total_prompt_baseline"], "NOT_OBSERVED")
                self.assertEqual(diagnostic["byte_delta"], diagnostic["model_input_bytes"] - diagnostic["full_input_bytes"])
                records[0]["delivery_diagnostics"]["prompt_bytes"] += 1
                self.write_historical_rows(root, records)
                with self.assertRaisesRegex(ValueError, "DELIVERY_DRIFT"):
                    revision.verify_completed(root, candidate=draft)

    def test_historical_pending_input_binding_rejects_same_size_and_missing_hash_drift(self):
        from product.runtime.cio_handoff import fixture_cio_model_input
        for defect in (None, "input", "stop-hash", "missing-stop-binding"):
            with self.subTest(defect=defect):
                root, _, model, cwd = self.pending_fixture()
                payload, start = self.write_historical_launch_fixture(root, model, cwd)
                self.assertEqual(start["delivery_diagnostics"]["comparison_status"], "NOT_COMPARABLE")
                draft = self.prepare_pending_cio(root)
                records = self.write_historical_execution_fixture(root, draft, payload, start)
                proof = revision.verify_completed(root, candidate=draft)
                self.assertEqual(proof["delivery_diagnostics"]["full_input_hash"],
                                 canonical_hash(json.loads((root / "inputs/runtime_cio.json").read_text())))
                if defect == "input":
                    path = root / "inputs/runtime_cio.json"
                    value = json.loads(path.read_text())
                    question = value["research_question"]
                    value["research_question"] = ("不" if question[0] != "不" else "未") + question[1:]
                    self.assertEqual(len(question.encode()), len(value["research_question"].encode()))
                    path.write_text(json.dumps(value, ensure_ascii=False))
                    (root / "inputs/runtime_cio.model.json").write_text(json.dumps(fixture_cio_model_input(root, value), ensure_ascii=False))
                elif defect == "stop-hash":
                    records[-1]["delivery_diagnostics"]["model_input_hash"] = "0" * 64
                    self.write_historical_rows(root, records)
                elif defect == "missing-stop-binding":
                    records[-1].pop("delivery_diagnostics")
                    self.write_historical_rows(root, records)
                if defect:
                    with self.assertRaises(ValueError):
                        revision.verify_completed(root, candidate=draft)
                self.assertFalse((root / "decision.json").exists())


if __name__ == "__main__":
    unittest.main()
