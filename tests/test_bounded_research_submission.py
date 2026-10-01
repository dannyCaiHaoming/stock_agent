"""研报 MCP 首稿/局部修订：实际 stdio、Hook 与正式报告；零模型。"""
from __future__ import annotations

import copy
import io
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from product.runtime.codex_hook_recorder import (
    handle_hook_event, _multidimensional_draft_diagnostics, _research_report_monetary_findings,
)
from product.runtime.fixture_mcp import serve_stdio
from product.runtime.hashing import legacy_envelope_hash
from product.runtime import research_submission as submission
from product.runtime.multidimensional_stage import build_multidimensional_dispatch_packet, serialize_multidimensional_model_context, finalize_multidimensional_task_evidence
from tests import test_research_submission as fixtures


class BoundedResearchSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        helper = fixtures.ResearchSubmissionTests()
        self.fixture, self.run, self.task, self.env, self.draft = helper.submit_and_start(
            Path(self.temp.name), version=submission.BOUNDED_REVISION_VERSION)
        self.packet = build_multidimensional_dispatch_packet(fixtures.fixtures.ROOT, self.run, self.task["task_name"])
        self.token = helper.token(self.run, self.task)
        self.directory = submission._directory(self.run, self.task["invocation_id"], create=False)
        for field in ("documents", "calculations", "artifact_refs"):
            self.draft.pop(field)
        self.draft.update(document_selections=[], calculation_selections=[])

    def call(self, draft, *, token=None):
        request = {"id": 1, "method": "tools/call", "params": {"name": "research_report_submit", "arguments": {
            "invocation_id": self.task["invocation_id"], "submission_token": self.token if token is None else token,
            "draft": draft}}}
        output = io.StringIO()
        with patch("sys.stdin", io.StringIO(json.dumps(request) + "\n")), patch("sys.stdout", output):
            serve_stdio(stateless=True, default_run_dir=self.run)
        response = json.loads(output.getvalue())
        return response.get("result", {}).get("structuredContent"), response

    def stop(self, receipt, **overrides):
        payload = self.fixture.stop_payload(self.task, {}, parent="dependency-parent", child="r")
        payload["last_assistant_message"] = receipt["final_message"]
        return handle_hook_event({**payload, **overrides}, environ=self.env)

    def incomplete(self):
        draft = copy.deepcopy(self.draft)
        draft["data_gaps"][0].pop("impact")
        return draft

    def patch_for(self, repair, changes=None):
        return {"base_draft_ref": repair["base_draft_ref"], "changes": changes or [{
            "op": "add", "path": "/data_gaps/0/impact", "value": self.draft["data_gaps"][0]["impact"]}]}

    def test_valid_first_submission_reaches_original_formal_report(self):
        result, response = self.call(self.draft)
        self.assertIsNotNone(result, response)
        self.assertEqual(result["status"], "DRAFT_STORED_NOT_VALIDATED")
        record, _ = self.stop(result)
        self.assertEqual(record["output_capture"]["status"], "SAVED", record)
        report = json.loads((self.run / record["output_capture"]["path"]).read_text())
        for key in ("claims", "data_gaps", "limitations", "summary"):
            self.assertEqual(report[key], self.draft[key])
        self.assertEqual(report["run_id"], self.task["run_id"])

    def test_selected_document_short_alias_diagnostic_matches_real_stop(self):
        short, full = next(iter(self.packet["reference_map"]["documents"].items()))
        draft = copy.deepcopy(self.draft)
        draft["document_selections"] = [short]
        evidence_ref = next(short for short, full in self.packet["reference_map"]["evidence"].items()
                            if full == "ev-issuer-body")
        draft["claims"] = [{
            "claim_id": "issuer_document", "question": "发行人正文的证据边界？",
            "core_statement": "已选择发行人正文，不能将其冒充独立研报。",
            "research_relation_clauses": [], "kind": "INTERPRETATION",
            "evidence_refs": [evidence_ref], "research_claim_refs": [],
            "document_refs": [short], "assumption_ids": [],
        }]
        assembled, _ = submission._assemble_draft(draft, self.packet, root=self.run)
        self.assertEqual(assembled["documents"][0]["document_id"], full)
        self.assertEqual(assembled["claims"][0]["document_refs"], [short])
        original = copy.deepcopy(assembled)
        trusted = {"identity_binding": {"status": "BOUND"},
                   "trusted_task_binding": {"invocation_id": self.task["invocation_id"]}}
        for variant, expected in (("selected", False), ("unselected", True), ("unknown", True)):
            candidate = copy.deepcopy(assembled)
            if variant == "unselected":
                candidate["documents"] = []
            elif variant == "unknown":
                candidate["claims"][0]["document_refs"] = ["d.unknown.1"]
            diagnostic = _multidimensional_draft_diagnostics(
                {"last_assistant_message": json.dumps(candidate)}, self.env,
                failure_code="DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED",
                trusted_record=trusted)
            self.assertNotEqual(diagnostic["status"], "UNAVAILABLE", diagnostic)
            self.assertEqual(any(f["code"] == "DIMENSION_REPORT_INTERNAL_REFERENCE_DANGLING"
                                 for f in diagnostic["findings"]), expected, diagnostic)
        self.assertEqual(assembled, original)
        receipt, response = self.call(draft)
        self.assertIsNotNone(receipt, response)
        record, _ = self.stop(receipt)
        self.assertEqual(record["output_capture"]["status"], "SAVED", record)
        report = json.loads((self.run / record["output_capture"]["path"]).read_text())
        self.assertEqual(report["claims"][0]["document_refs"], [full])

    def test_relation_amount_requires_author_correction_in_original_two_slots(self):
        self.verify_relation_amount_repair(fix_relation=True)

    def test_core_only_second_submission_still_fails_and_exhausts_original_slots(self):
        self.verify_relation_amount_repair(fix_relation=False)

    def verify_relation_amount_repair(self, *, fix_relation):
        # 合成许可来源由真实金额护栏处理；stdio、装配、修订及Stop仍走真实路径。
        evidence_ref = next(short for short, full in self.packet["reference_map"]["evidence"].items()
                            if full == "ev-issuer-body")
        upstream_ref = next(iter(self.packet["reference_map"]["claims"]))
        draft = copy.deepcopy(self.draft)
        draft["claims"] = [{
            "claim_id": "source_relation", "question": "供应商观点与历史事实的关系？",
            "core_statement": "供应商预测为12/18 billion USD，不是已实现经营事实。",
            "research_relation_clauses": [{"research_claim_ref": upstream_ref,
                "relation_statement": "上游历史事实不能证明12/18 billion USD 的预测。"}],
            "kind": "INTERPRETATION", "evidence_refs": [evidence_ref],
            "research_claim_refs": [upstream_ref], "document_refs": [], "assumption_ids": [],
        }]

        def licensed_fixture_guard(*args, **kwargs):
            gate = copy.deepcopy(kwargs["gate"])
            source = next(f for f in gate["allowed_evidence"] if f["evidence_id"] == "ev-issuer-body")
            source["value"] = {"content_tier": "LICENSED_API_CONTENT", "content": "供应商预测120/180亿美元。"}
            gate["bundle_hash"] = legacy_envelope_hash(gate, hash_field="bundle_hash")
            return _research_report_monetary_findings(*args, **{**kwargs, "gate": gate})

        with patch("product.runtime.codex_hook_recorder._research_report_monetary_findings",
                   side_effect=licensed_fixture_guard):
            first, response = self.call(draft)
            self.assertIsNotNone(first, response)
            original = (self.directory / "1.json").read_bytes()
            record, blocked = self.stop(first)
            self.assertEqual(blocked["decision"], "block", record)
            repair = record["repair_request"]
            self.assertEqual(repair["allowed_paths"], ["/claims/0"])
            feedback = json.loads(blocked["reason"])
            self.assertIn("最终拼接", json.dumps(feedback, ensure_ascii=False))
            self.assertTrue(all(f["amount_index_basis"] == "FINAL_ASSEMBLED_STATEMENT"
                                for f in feedback["validation_details"]["findings"]
                                if f["code"] == "DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED"))
            corrected = copy.deepcopy(draft["claims"][0])
            corrected["core_statement"] = "供应商预测为120/180亿美元，不是已实现经营事实。"
            core_only = copy.deepcopy(draft)
            core_only["claims"][0] = corrected
            assembled, selected = submission._assemble_draft(core_only, self.packet, root=self.run)
            findings = licensed_fixture_guard(assembled, task=self.task,
                gate=json.loads((self.run / "evidence/gate.json").read_text()),
                reference_packet=self.packet, selected_upstream=selected)
            self.assertEqual([(f["reported_value"], f["amount_index"]) for f in findings], [("18", 0)])
            if fix_relation:
                corrected["research_relation_clauses"][0]["relation_statement"] = "上游历史事实不能证明120/180亿美元预测。"
            second, response = self.call({"base_draft_ref": repair["base_draft_ref"], "changes": [
                {"op": "replace", "path": "/claims/0", "value": corrected}]})
            self.assertIsNotNone(second, response)
            self.assertEqual(second["validation_result"]["status"], "PASSED", second)
            saved, _ = self.stop(second)
            self.assertEqual(saved["output_capture"]["status"], "SAVED" if fix_relation else "FAILED", saved)
            if not fix_relation:
                self.assertEqual(saved["output_capture"]["failure_code"],
                                 "DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED")
                self.assertEqual(saved["output_capture"]["repair_state"], "EXHAUSTED")
            self.assertEqual((self.directory / "1.json").read_bytes(), original)
            third, rejected = self.call(draft)
            self.assertIsNone(third)
            self.assertIn("LIMIT_EXHAUSTED", json.dumps(rejected))

    def test_missing_relationship_list_repair_uses_delivered_operation_schema(self):
        from jsonschema import Draft202012Validator
        from product.runtime.local_revision import REVISION_FORMAT_GUIDE
        from product.runtime.multidimensional_stage import serialize_multidimensional_initial_context
        draft = copy.deepcopy(self.draft)
        ref = next(iter(self.packet["reference_map"]["claims"]))
        draft["claims"] = [{
            "claim_id": "limited_view", "question": "来源的研究边界是什么？",
            "core_statement": "没有已核验正文，不能据标题推导作者完整观点。",
            "kind": "INTERPRETATION", "evidence_refs": [], "research_claim_refs": [ref],
            "document_refs": [], "assumption_ids": [],
            "research_relation_clauses": [{"research_claim_ref": ref,
                "relation_statement": "上游提供历史经营事实与资料限制，不能验证缺失正文的作者观点。"}],
        }]
        relations = draft["claims"][0]["research_relation_clauses"]
        draft["claims"][0].pop("research_relation_clauses")
        first, _ = self.call(draft)
        self.assertIn("research_relation_clauses", first["validation_result"]["failure_code"])
        repair = first["repair"]
        self.assertEqual(repair["revision_format_guide"], REVISION_FORMAT_GUIDE)
        for serialize in (serialize_multidimensional_model_context, serialize_multidimensional_initial_context):
            delivered = json.loads(serialize(self.packet))["submission_contract"]
            self.assertEqual(delivered["revision_format_guide"], repair["revision_format_guide"])
        original = (self.directory / "1.json").read_bytes()
        revised = {"base_draft_ref": repair["base_draft_ref"], "changes": [{
            "op": "add", "path": "/claims/0/research_relation_clauses",
            "value": relations}]}
        Draft202012Validator(repair["revision_format_guide"]).validate(revised)
        second, _ = self.call(revised)
        self.assertEqual(second["validation_result"]["status"], "PASSED")
        record, _ = self.stop(second)
        self.assertEqual(record["output_capture"]["status"], "SAVED", record)
        self.assertEqual((self.directory / "1.json").read_bytes(), original)

    def test_real_missing_op_shape_still_consumes_second_slot_and_is_rejected(self):
        from jsonschema import Draft202012Validator, ValidationError
        first, _ = self.call(self.incomplete())
        repair = first["repair"]
        malformed = {"base_draft_ref": repair["base_draft_ref"], "changes": [{
            "path": "/data_gaps/0/impact", "value": "Agent-authored correction"}]}
        with self.assertRaises(ValidationError):
            Draft202012Validator(repair["revision_format_guide"]).validate(malformed)
        second, _ = self.call(malformed)
        self.assertEqual(second["validation_result"]["failure_code"], "LOCAL_REVISION_OPERATION_INVALID")
        stored = json.loads((self.directory / "2.json").read_text())
        self.assertEqual(stored["authored_submission"], malformed)
        third, response = self.call(self.patch_for(repair))
        self.assertIsNone(third)
        self.assertIn("LIMIT_EXHAUSTED", json.dumps(response))

    def test_real_submit_event_is_readable_by_consumption_audit(self):
        from product.runtime.research_consumption_audit import _events
        from product.runtime.hashing import canonical_hash
        result, response = self.call(self.draft)
        self.assertIsNotNone(result, response)
        path = self.run / "events/mcp/events.jsonl"
        original = path.read_bytes()
        events = [json.loads(line) for line in original.decode().splitlines() if line.strip()]
        position = next(i for i, event in enumerate(events) if event.get("tool") == "research_report.submit")
        event = events[position]
        self.assertEqual(event["event_type"], "research_submission")
        for field in ("run_id", "agent", "invocation_id"):
            self.assertEqual(event[field], self.task[field])
        self.assertEqual(_events(self.run)[2], "HASH_VERIFIED")

        # 历史事件原协议无身份外壳，只读重验精确草稿/packet，不靠跳过事件通过。
        legacy = {key: value for key, value in event.items()
                  if key not in {"run_id", "agent", "event_type", "event_hash"}}
        legacy["event_hash"] = canonical_hash(legacy)
        variants = [("legacy", legacy, None),
                    ("foreign-run", {**event, "run_id": "foreign"}, "SUBMISSION_BINDING_INVALID"),
                    ("unknown-task", {**legacy, "invocation_id": "unknown"}, "SUBMISSION_BINDING_INVALID"),
                    ("wrong-digest", {**legacy, "output_hash": "0" * 64}, "SUBMISSION_BINDING_INVALID"),
                    ("wrong-number", {**legacy, "submission": 2}, "SUBMISSION_BINDING_INVALID"),
                    ("foreign-agent", {**legacy, "agent": "foreign"}, "SUBMISSION_BINDING_INVALID"),
                    ("partial-envelope", {**legacy, "run_id": self.task["run_id"]}, "SUBMISSION_BINDING_INVALID")]
        for name, altered, error in variants:
            with self.subTest(name=name):
                altered = {key: value for key, value in altered.items() if key != "event_hash"}
                altered["event_hash"] = canonical_hash(altered)
                rows = [*events]
                rows[position] = altered
                path.write_text("\n".join(json.dumps(row) for row in rows) + "\n")
                if error:
                    with self.assertRaisesRegex(ValueError, error):
                        _events(self.run)
                else:
                    before = path.read_bytes()
                    self.assertEqual(_events(self.run)[2], "HASH_VERIFIED")
                    self.assertEqual(path.read_bytes(), before)
        path.write_bytes(original)
        stored = self.directory / "1.json"
        saved = stored.read_bytes()
        value = json.loads(saved)
        value["draft"]["summary"] = "tampered"
        stored.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "SUBMISSION_BINDING_INVALID"):
            _events(self.run)
        stored.write_bytes(saved)
        foreign = {"event_type": "mcp_tool_result", "tool": "fixture_evidence.query",
                   "run_id": "foreign", "invocation_id": self.task["invocation_id"], "evidence_ids": []}
        foreign["event_hash"] = canonical_hash(foreign)
        events.append(foreign)
        path.write_text("\n".join(json.dumps(row) for row in events) + "\n")
        with self.assertRaisesRegex(ValueError, "EVENT_RUN_MISMATCH"):
            _events(self.run)

    def test_nonempty_relation_keeps_authored_qualifiers_through_stop_and_finalizer(self):
        ref, target = next(iter(self.packet["reference_map"]["claims"].items()))
        core = "来源观点需要独立核验；不等于公司盈利增长已被证实。"
        relation = "上游只给历史经营事实与资料限制，不能验证该观点。"
        draft = {**self.draft, "claims": [{
            "claim_id": "bounded_relation", "question": "来源观点和上游事实是什么关系？",
            "core_statement": core, "research_relation_clauses": [{
                "research_claim_ref": ref, "relation_statement": relation}],
            "kind": "INTERPRETATION", "evidence_refs": [], "research_claim_refs": [ref],
            "document_refs": [], "assumption_ids": [],
        }]}
        first, response = self.call(draft)
        self.assertIsNotNone(first, response)
        self.assertEqual(first["validation_result"]["status"], "PASSED", first)
        self.assertEqual(first["citation_review"]["pair_count"], 1)
        record, _ = self.stop(first)
        self.assertEqual(record["output_capture"]["status"], "SAVED", record)
        report = json.loads((self.run / record["output_capture"]["path"]).read_text())
        self.assertEqual(report["claims"][0]["statement"], core + " " + relation)
        self.assertEqual(report["claims"][0]["research_claim_refs"], [target["canonical_ref"]])
        self.assertEqual(json.loads((self.directory / "1.json").read_text())["draft"], draft)
        result = finalize_multidimensional_task_evidence(fixtures.fixtures.ROOT, self.run, self.task["task_name"])
        self.assertEqual(result["status"], "PASSED", result)

    def test_schema_invalid_first_consumes_slot_and_local_patch_revalidates(self):
        original = self.incomplete()
        first, _ = self.call(original)
        self.assertEqual(first["status"], "DRAFT_REJECTED")
        self.assertEqual(first["repair"]["allowed_paths"], ["/data_gaps/0/impact"])
        before = (self.directory / "1.json").read_bytes()
        second, response = self.call(self.patch_for(first["repair"]))
        self.assertIsNotNone(second, response)
        self.assertEqual(second["submission"], 2)
        self.assertEqual(second["validation_result"]["status"], "PASSED")
        record, _ = self.stop(second)
        self.assertEqual(record["output_capture"]["status"], "SAVED", record)
        self.assertEqual((self.directory / "1.json").read_bytes(), before)
        self.assertEqual(json.loads(before)["draft"], original)
        stored = json.loads((self.directory / "2.json").read_text())
        self.assertEqual(stored["authored_submission"], self.patch_for(first["repair"]))
        self.assertEqual(stored["draft"], self.draft)
        rejected, response = self.call(self.draft)
        self.assertIsNone(rejected)
        self.assertIn("LIMIT_EXHAUSTED", json.dumps(response))

    def test_actual_submit_checks_structure_before_reading_calculation_catalog(self):
        with patch("product.runtime.calculation_handoff.build_calculation_catalog",
                   side_effect=ValueError("CALCULATION_EVENT_INVALID")) as catalog:
            result, response = self.call(self.incomplete())
            self.assertIsNotNone(result, response)
            self.assertEqual(result["validation_result"]["failure_code"],
                             "SCHEMA_REQUIRED_MISSING:$.data_gaps[0]:impact")
            self.assertEqual(result["repair"]["allowed_paths"], ["/data_gaps/0/impact"])
            catalog.assert_not_called()
        self.assertTrue((self.directory / "1.json").is_file())

    def test_structural_pass_does_not_hide_calculation_integrity_failure(self):
        with patch("product.runtime.calculation_handoff.build_calculation_catalog",
                   side_effect=ValueError("CALCULATION_EVENT_INVALID")) as catalog:
            result, response = self.call(self.draft)
            self.assertIsNotNone(result, response)
            self.assertEqual(result["status"], "DRAFT_REJECTED")
            self.assertEqual(result["validation_result"]["failure_code"], "CALCULATION_EVENT_INVALID")
            self.assertGreater(catalog.call_count, 0)
            self.assertFalse(result.get("repair"))
        record, _ = self.stop(result)
        self.assertEqual(record["output_capture"]["status"], "FAILED", record)

    def test_wrong_credential_has_no_target_state_or_quota_effect(self):
        result, response = self.call(self.draft, token="not-authorized")
        self.assertIsNone(result)
        self.assertIn("CREDENTIAL_INVALID", json.dumps(response))
        self.assertFalse(self.directory.exists())
        result, _ = self.call(self.draft)
        self.assertEqual(result["submission"], 1)

    def test_outside_fields_fail_second_attempt_and_third_is_not_available(self):
        first, _ = self.call(self.incomplete())
        changes = [{"op": "replace", "path": "/summary", "value": "未经允许重写的结论。"}]
        second, _ = self.call(self.patch_for(first["repair"], changes))
        self.assertEqual(second["status"], "DRAFT_REJECTED")
        self.assertIn("LOCAL_REVISION_OUT_OF_SCOPE", second["validation_result"]["failure_code"])
        record, response = self.stop(second)
        self.assertEqual(record["output_capture"]["status"], "FAILED")
        self.assertEqual(record["output_capture"]["repair_state"], "EXHAUSTED")
        self.assertEqual(response, {})
        self.assertEqual(json.loads((self.directory / "2.json").read_text())["authored_submission"]["changes"], changes)
        result, response = self.call(self.patch_for(first["repair"]))
        self.assertIsNone(result)
        self.assertIn("LIMIT_EXHAUSTED", json.dumps(response))

    def test_sidecar_resigning_does_not_forge_original_tool_feedback(self):
        first, _ = self.call(self.incomplete())
        path = self.directory / "1.repair.json"
        repair = json.loads(path.read_text())
        repair["allowed_paths"].append("/summary")
        repair["content_hash"] = legacy_envelope_hash(repair, hash_field="content_hash")
        path.write_text(json.dumps(repair))
        result, response = self.call(self.patch_for(first["repair"]))
        self.assertIsNone(result)
        self.assertIn("REVISION_PROOF_MISSING", json.dumps(response))
        self.assertFalse((self.directory / "2.json").exists())

    def test_exact_rejected_receipt_is_not_latest_valid_draft(self):
        first, _ = self.call(self.incomplete())
        self.call(self.patch_for(first["repair"]))
        record, response = self.stop(first)
        self.assertEqual(record["output_capture"]["status"], "FAILED")
        self.assertIn("SCHEMA_REQUIRED_MISSING", record["output_capture"]["failure_code"])
        self.assertEqual(record["submission_binding"]["submission"], 1)
        self.assertFalse(list((self.run / "research/reports").glob("*/dimension-report.json"))[1:])

    def test_trusted_stop_creates_bound_repair_for_later_business_validation(self):
        from product.runtime.local_revision import REVISION_FORMAT_GUIDE
        from jsonschema import Draft202012Validator
        draft = {**self.draft, "status": "SOURCE_LIMITED"}
        first, _ = self.call(draft)
        self.assertEqual(first["validation_result"]["status"], "PASSED", first)
        record, response = self.stop(first)
        self.assertEqual(record["output_capture"]["repair_state"], "REPAIR_REQUESTED", record)
        repair = json.loads(response["reason"])
        self.assertEqual(repair["repair_contract"], "research-local-revision/1.0.0")
        self.assertEqual(repair["revision_format_guide"], REVISION_FORMAT_GUIDE)
        self.assertNotIn("binding_hash", repair)
        correction = self.patch_for(repair, [{
            "op": "replace", "path": "/evaluation_status", "value": "SOURCE_LIMITED"}])
        Draft202012Validator(repair["revision_format_guide"]).validate(correction)
        second, response = self.call(correction)
        self.assertIsNotNone(second, response)
        record, _ = self.stop(second)
        self.assertEqual(record["output_capture"]["status"], "SAVED", record)

    def test_missing_actual_submission_event_is_not_an_execution_proof(self):
        first, _ = self.call(self.draft)
        (self.run / "events/mcp/events.jsonl").unlink()
        record, _ = self.stop(first)
        self.assertEqual(record["output_capture"]["failure_code"], "RESEARCH_SUBMISSION_EVENT_MISSING")
        self.assertEqual(record["output_capture"]["repair_state"], "NOT_ALLOWED")

    def test_unknown_document_can_only_be_replaced_by_authors_explicit_choice(self):
        draft = {**self.draft, "document_selections": ["d.not-in-this-task"]}
        first, _ = self.call(draft)
        self.assertEqual(first["status"], "DRAFT_REJECTED")
        self.assertEqual(first["repair"]["allowed_paths"], ["/document_selections/0"])
        allowed = next(iter(self.packet["reference_map"]["documents"]))
        second, response = self.call(self.patch_for(first["repair"], [{
            "op": "replace", "path": "/document_selections/0", "value": allowed}]))
        self.assertIsNotNone(second, response)
        record, _ = self.stop(second)
        self.assertEqual(record["output_capture"]["status"], "SAVED", record)
        report = json.loads((self.run / record["output_capture"]["path"]).read_text())
        self.assertEqual(report["documents"], [self.task["allowed_documents"][0]])
        self.assertEqual(report["summary"], self.draft["summary"])
        result = finalize_multidimensional_task_evidence(fixtures.fixtures.ROOT, self.run, self.task["task_name"])
        self.assertEqual(result["status"], "PASSED", result)

    def test_revision_deleting_claim_is_still_checked_for_dangling_conditions(self):
        ref = next(iter(self.packet["reference_map"]["claims"]))
        draft = {**self.draft, "claims": [{
            "claim_id": "local", "question": "上游结论如何关联？", "core_statement": "来源提供有限观点。",
            "research_relation_clauses": [], "kind": "INTERPRETATION",
            "evidence_refs": [], "research_claim_refs": [ref], "document_refs": [],
            "assumption_ids": [],
        }], "observation_conditions": [{
            "condition_id": "follow", "description": "后续复查该有限观点。",
            "claim_refs": ["local"], "evidence_refs": [],
        }]}
        first, response = self.call(draft)
        self.assertIsNotNone(first, response)
        self.assertEqual(first["repair"]["allowed_paths"], ["/claims/0"])
        second, _ = self.call(self.patch_for(first["repair"], [{"op": "remove", "path": "/claims/0"}]))
        record, _ = self.stop(second)
        self.assertEqual(record["output_capture"]["status"], "FAILED", record)
        self.assertEqual(record["output_capture"]["failure_code"], "DIMENSION_REPORT_CONDITION_REFERENCE_DANGLING")
        self.assertEqual(record["output_capture"]["repair_state"], "EXHAUSTED")

    def test_full_replacement_consumes_second_authorized_slot_without_rewriting_base(self):
        first, _ = self.call(self.incomplete())
        base_bytes = (self.directory / "1.json").read_bytes()
        result, _ = self.call(self.draft)
        self.assertEqual(result["status"], "DRAFT_REJECTED")
        self.assertEqual(result["validation_result"]["failure_code"], "RESEARCH_SUBMISSION_BASE_REFERENCE_INVALID")
        self.assertEqual((self.directory / "1.json").read_bytes(), base_bytes)
        record, response = self.stop(result)
        self.assertEqual(record["output_capture"]["repair_state"], "EXHAUSTED")
        self.assertEqual(response, {})
        third, response = self.call(self.patch_for(first["repair"]))
        self.assertIsNone(third)
        self.assertIn("LIMIT_EXHAUSTED", json.dumps(response))

    def test_wrong_base_is_preserved_as_rejected_second_draft(self):
        first, _ = self.call(self.incomplete())
        authored = {**self.patch_for(first["repair"]), "base_draft_ref": "b.wrong"}
        second, _ = self.call(authored)
        self.assertEqual(second["validation_result"]["failure_code"], "RESEARCH_SUBMISSION_BASE_REFERENCE_INVALID")
        self.assertEqual(json.loads((self.directory / "2.json").read_text())["authored_submission"], authored)
        third, response = self.call(self.patch_for(first["repair"]))
        self.assertIsNone(third)
        self.assertIn("LIMIT_EXHAUSTED", json.dumps(response))

    def test_valid_bearer_is_not_wrong_child_stop_authentication(self):
        first, _ = self.call(self.draft)
        record, _ = self.stop(first, agent_id="wrong-child")
        self.assertNotEqual(record.get("output_capture", {}).get("status"), "SAVED")
        self.assertFalse((self.directory / "accepted.json").exists())
        record, _ = self.stop(first)
        self.assertEqual(record["output_capture"]["status"], "SAVED", record)

    def test_re_signed_stored_draft_is_rejected_by_actual_event(self):
        first, _ = self.call(self.draft)
        path = self.directory / "1.json"
        stored = json.loads(path.read_text())
        stored["draft"]["summary"] = "重新签名但并非实际提交的结论。"
        stored["content_hash"] = legacy_envelope_hash(stored, hash_field="content_hash")
        path.write_text(json.dumps(stored))
        record, response = self.stop(first)
        self.assertIn("EVENT_BINDING_INVALID", record["output_capture"]["failure_code"])
        self.assertEqual(record["output_capture"]["repair_state"], "NOT_ALLOWED")
        self.assertEqual(response, {})

    def test_too_many_structure_errors_are_saved_not_unlimited_rejected_calls(self):
        draft = {**self.draft, "data_gaps": [{} for _ in range(40)]}
        first, _ = self.call(draft)
        self.assertEqual(first["status"], "DRAFT_REJECTED")
        self.assertEqual(first["validation_result"]["failure_code"], "SCHEMA_DIAGNOSTICS_TOO_MANY")
        self.assertEqual(json.loads((self.directory / "1.json").read_text())["draft"], draft)
        self.assertNotIn("repair", first)

    def test_large_invalid_field_has_bounded_feedback_and_preserved_original(self):
        draft = {**self.draft, "未知字段" * 4000: "错误字段值"}
        first, _ = self.call(draft)
        self.assertEqual(first["status"], "DRAFT_REJECTED")
        self.assertEqual(first["validation_result"]["failure_code"], "RESEARCH_SUBMISSION_DIAGNOSTICS_TOO_LARGE")
        self.assertNotIn("repair", first)
        self.assertLess(len(json.dumps(first, ensure_ascii=False).encode()), 16 * 1024)
        self.assertEqual(json.loads((self.directory / "1.json").read_text())["draft"], draft)

    def test_non_object_event_is_diagnosed_and_does_not_enable_repair(self):
        first, _ = self.call(self.draft)
        path = self.run / "events/mcp/events.jsonl"
        path.write_text(path.read_text() + "null\n")
        record, response = self.stop(first)
        self.assertEqual(record["output_capture"]["failure_code"], "RESEARCH_SUBMISSION_EVENT_INVALID")
        self.assertEqual(record["output_capture"]["repair_state"], "NOT_ALLOWED")
        self.assertEqual(response, {})

    def test_parallel_corrections_share_one_remaining_slot(self):
        first, _ = self.call(self.incomplete())
        authored = self.patch_for(first["repair"])
        def submit_one():
            try:
                return submission.submit(self.run, self.task["invocation_id"], authored, submission_token=self.token)
            except ValueError as exc:
                return {"error": str(exc)}
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: submit_one(), range(2)))
        self.assertEqual(sum(item.get("submission") == 2 for item in results), 1)
        self.assertEqual(sum(item.get("error") == "RESEARCH_SUBMISSION_LIMIT_EXHAUSTED" for item in results), 1)
        self.assertEqual(json.loads((self.directory / "2.json").read_text())["authored_submission"], authored)

    def test_event_parent_symlink_is_rejected_not_read_as_proof(self):
        first, _ = self.call(self.draft)
        directory = self.run / "events/mcp"
        moved = Path(self.temp.name) / "moved-events"
        directory.rename(moved)
        directory.symlink_to(moved, target_is_directory=True)
        record, response = self.stop(first)
        self.assertEqual(record["output_capture"]["failure_code"], "RESEARCH_SUBMISSION_EVENT_PATH_INVALID")
        self.assertEqual(record["output_capture"]["repair_state"], "NOT_ALLOWED")
        self.assertEqual(response, {})

    def test_bounded_monetary_preview_reuses_existing_calculation_diagnostics(self):
        findings = [{"code": "DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED",
                     "path": "claims[0].statement", "identifier": "e.original"}]
        with patch("product.runtime.codex_hook_recorder._research_report_monetary_findings", return_value=findings):
            result, _ = self.call(self.draft)
        self.assertEqual(result["monetary_review"]["status"], "LOCATED")
        self.assertEqual(result["monetary_review"]["findings"], findings)
        self.assertEqual(result["validation_result"]["status"], "PASSED")  # 辅助诊断不是报告已接受。

    def monetary_repeat_draft(self):
        draft = copy.deepcopy(self.draft)
        ref = next(short for short, full in self.packet["reference_map"]["evidence"].items()
                   if full == "ev-issuer-body")
        draft["claims"] = [{
            "claim_id": "issuer_baseline", "question": "发行人指引？",
            "core_statement": "Management guidance is $12 billion.", "research_relation_clauses": [],
            "kind": "INTERPRETATION", "evidence_refs": [ref], "research_claim_refs": [],
            "document_refs": [], "assumption_ids": [],
        }]
        draft["data_gaps"][0]["description"] = "Need to cross-check $12 billion guidance."
        draft["data_gaps"].append({**draft["data_gaps"][0], "gap_id": "other_amount",
                                   "description": "Need to cross-check $18 billion."})
        finding = {"code": "DIMENSION_REPORT_MONETARY_REEXPRESSION_UNVERIFIED",
                   "path": "claims[0].statement", "identifier": ref, "amount_index": 0,
                   "source_unit": "亿美元", "reported_unit": "billion USD",
                   "source_value": "120", "reported_value": "12",
                   "amount_index_basis": "FINAL_ASSEMBLED_STATEMENT"}
        return draft, finding

    def test_trusted_stop_opens_only_exact_repeated_description_and_keeps_two_submissions(self):
        from product.runtime.local_revision import _apply
        draft, finding = self.monetary_repeat_draft()
        with patch("product.runtime.codex_hook_recorder._research_report_monetary_findings", return_value=[finding]):
            first, _ = self.call(draft)
            original = (self.directory / "1.json").read_bytes()
            record, response = self.stop(first)
        self.assertEqual(response["decision"], "block", record)
        repair = record["repair_request"]
        self.assertEqual(repair["allowed_paths"], ["/claims/0", "/data_gaps/0/description"])
        self.assertEqual(json.loads(response["reason"])["repeated_amount_context"], [{"path": "data_gaps[0].description",
                          "status": "REPEATED_EXPLICIT_AMOUNT_AUTHOR_RECHECK"}])
        for path in ("/data_gaps/0", "/data_gaps/0/impact", "/data_gaps/1/description", "/summary"):
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "OUT_OF_SCOPE"):
                _apply(draft, [{"op": "replace", "path": path, "value": "outside"}], repair["allowed_paths"])
        authored = {"base_draft_ref": repair["base_draft_ref"], "changes": [
            {"op": "replace", "path": "/claims/0/core_statement", "value": "管理层原指引为120亿美元，待核验。"},
            {"op": "replace", "path": "/data_gaps/0/description", "value": "待交叉核验原文120亿美元指引。"},
        ]}
        second, response = self.call(authored)
        self.assertIsNotNone(second, response)
        self.assertEqual(second["validation_result"]["status"], "PASSED")
        record, _ = self.stop(second)
        self.assertEqual(record["output_capture"]["status"], "SAVED", record)
        report = json.loads((self.run / record["output_capture"]["path"]).read_text())
        self.assertEqual(report["data_gaps"][0]["description"], authored["changes"][1]["value"])
        self.assertEqual(report["data_gaps"][1], draft["data_gaps"][1])
        self.assertEqual((self.directory / "1.json").read_bytes(), original)
        third, response = self.call(authored)
        self.assertIsNone(third)
        self.assertIn("LIMIT_EXHAUSTED", json.dumps(response))

    def test_repeated_description_does_not_open_other_gap_fields_in_real_second_submission(self):
        draft, finding = self.monetary_repeat_draft()
        with patch("product.runtime.codex_hook_recorder._research_report_monetary_findings", return_value=[finding]):
            first, _ = self.call(draft)
            record, _ = self.stop(first)
        repair = record["repair_request"]
        second, response = self.call({"base_draft_ref": repair["base_draft_ref"], "changes": [
            {"op": "replace", "path": "/data_gaps/0/impact", "value": "outside"}]})
        self.assertIsNotNone(second, response)
        self.assertEqual(second["validation_result"]["failure_code"], "LOCAL_REVISION_OUT_OF_SCOPE:/data_gaps/0/impact")
        final, _ = self.stop(second)
        self.assertEqual(final["output_capture"]["status"], "FAILED", final)
        self.assertEqual(final["output_capture"]["repair_state"], "EXHAUSTED")

    def test_start_context_and_tool_parameter_contract_select_same_protocol(self):
        context = json.loads(serialize_multidimensional_model_context(self.packet))
        self.assertEqual(context["submission_contract"]["version"], submission.BOUNDED_REVISION_VERSION)
        self.assertEqual(context["submission_contract"]["maximum_submissions"], 2)
        guide = context["submission_contract"]["draft_format_guide"]
        self.assertNotIn("run_id", guide["properties"])
        self.assertIn("core_statement", guide["$defs"]["claim"]["properties"])
        self.assertNotIn("statement", guide["$defs"]["claim"]["properties"])
