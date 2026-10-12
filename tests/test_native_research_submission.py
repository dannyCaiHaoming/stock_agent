"""原生语义提交的实际业务正负接缝；不执行或模拟模型研究。"""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import unittest

from product.mcp.research import dispatch
from product.tools.report_contracts import semantic_schema
from product.tools.research import ResearchTools, prepare_task
from tests.test_common_stock_research_contracts import research_request, valid_report
from tests.test_native_research_tools import AT, SECURITY, frozen_gate
from tests.test_single_stock_input import alb_request


def company_draft():
    old = valid_report(research_request()[2], evidence_refs=["ev-revenue"])
    fields = semantic_schema("COMPANY_RESEARCH")["properties"]
    result = {key: copy.deepcopy(value) for key, value in old.items() if key in fields}
    result["calculation_selections"] = []
    for claim in result["claims"]:
        claim.pop("calculation_refs", None)
    return result


class NativeResearchSubmissionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.tmp.name)/"research"
        self.prepared = prepare_task(self.root, research_input=alb_request(), gate=frozen_gate(),
                                     security_id=SECURITY, capability="COMPANY_RESEARCH")
        self.tools = ResearchTools(self.root, access_token=self.prepared["access_token"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_valid_company_submission_is_exact_and_does_not_invent_execution(self):
        draft = company_draft()
        self.tools.query(evidence_ids=["ev-revenue"])
        result = self.tools.submit(draft=draft)
        self.assertTrue(result["accepted"], result)
        report = self.tools.read_submission(draft_ref=result["draft_ref"])
        self.assertEqual(report["research"]["claims"][0]["statement"], draft["claims"][0]["statement"])
        self.assertEqual(report["business_validation"], "VALIDATED")
        self.assertEqual(report["host_execution"], "UNVERIFIED")
        self.assertEqual(report["caller_authentication"], "UNVERIFIED")
        self.assertEqual(report["content_verdict"], "NOT_REVIEWED")
        self.assertNotIn("model", report)
        self.assertNotIn("skill_execution", report)
        self.assertEqual(report["evidence_refs"], ["ev-revenue"])
        self.assertTrue(all(report[key] for key in ("source_id", "as_of", "retrieved_at")))
        self.assertEqual(report["as_of"], AT)

    def test_missing_wrong_other_credentials_do_not_consume_slot(self):
        other = prepare_task(Path(self.tmp.name)/"other", research_input=alb_request(), gate=frozen_gate(),
                             security_id=SECURITY, capability="COMPANY_RESEARCH")
        for token in (None, "bad", other["access_token"]):
            with self.assertRaisesRegex(ValueError, "ACCESS_INVALID"):
                ResearchTools(self.root, access_token=token).submit(draft=company_draft())
        self.assertFalse((self.root/"submissions").exists())
        self.tools.query(evidence_ids=["ev-revenue"])
        self.assertTrue(self.tools.submit(draft=company_draft())["accepted"])

    def test_model_authored_identity_is_rejected_and_never_enveloped(self):
        value = company_draft()
        value["agent"] = "runtime_skeptic"
        result = self.tools.submit(draft=value)
        self.assertFalse(result["accepted"])
        self.assertEqual(result["allowed_paths"], [])
        with self.assertRaises(ValueError):
            self.tools.read_submission(draft_ref=result["draft_ref"])

    def test_actual_query_required_not_just_catalog(self):
        self.tools.catalog()
        result = self.tools.submit(draft=company_draft())
        self.assertFalse(result["accepted"])
        self.assertEqual(result["validation_error"], "NATIVE_RESEARCH_EVIDENCE_NOT_QUERIED")
        self.assertTrue(result["allowed_paths"])

    def test_one_exact_revision_keeps_both_drafts_and_rechecks_everything(self):
        self.tools.query(evidence_ids=["ev-revenue"])
        original = company_draft()
        original["confidence"] = "LOW"
        first = self.tools.submit(draft=original)
        self.assertFalse(first["accepted"])
        self.assertIn("/confidence", first["allowed_paths"])
        revision = {"base_draft_ref": first["draft_ref"], "changes": [
            {"op": "replace", "path": "/confidence", "value": 0.5},
        ]}
        second = self.tools.submit(draft=revision)
        self.assertTrue(second["accepted"], second)
        self.assertEqual(json.loads((self.root/"submissions/1.json").read_text())["draft"], original)
        saved = self.tools.read_submission(draft_ref=second["draft_ref"])
        self.assertEqual(saved["research"]["confidence"], 0.5)
        with self.assertRaisesRegex(ValueError, "EXHAUSTED"):
            self.tools.submit(draft=company_draft())

    def period_task(self, name):
        from product.runtime.hashing import legacy_envelope_hash
        gate = frozen_gate()
        for fact, start in zip(gate["allowed_evidence"], ("2025-01-01", "2026-01-01", "2026-01-01")):
            fact["metadata"] = {"context_type": "duration", "period_start": start,
                                "period_end": start[:4] + "-06-30"}
        gate["bundle_hash"] = legacy_envelope_hash(gate, hash_field="bundle_hash")
        root = Path(self.tmp.name)/name
        prepared = prepare_task(root, research_input=alb_request(), gate=gate,
                                security_id=SECURITY, capability="COMPANY_RESEARCH")
        tools = ResearchTools(root, access_token=prepared["access_token"])
        tools.query(evidence_ids=["ev-revenue", "ev-income"])
        draft = company_draft()
        draft["claims"][0].update(kind="FACT", evidence_refs=["ev-revenue", "ev-income"],
                                  statement="收入与净利润来自不同流量期间。")
        return tools, draft

    def test_period_revision_only_opens_statement_and_preserves_evidence_and_gate(self):
        tools, draft = self.period_task("period")
        before = (tools.root/"gate.json").read_bytes()
        first = tools.submit(draft=draft)
        self.assertFalse(first["accepted"])
        self.assertEqual(first["validation_error"], "EQUITY_RESEARCH_FACT_PERIOD_LINEAGE_INCOMPLETE")
        self.assertEqual(first["allowed_paths"], ["/claims/0/statement"])
        second = tools.submit(draft={"base_draft_ref": first["draft_ref"], "changes": [
            {"op": "replace", "path": "/claims/0/statement",
             "value": "收入期间2025-01-01至2025-06-30，净利润期间2026-01-01至2026-06-30，不能直接比较。"},
        ]})
        self.assertTrue(second["accepted"], second)
        report = tools.read_submission(draft_ref=second["draft_ref"])
        self.assertEqual(report["research"]["claims"][0]["evidence_refs"], draft["claims"][0]["evidence_refs"])
        self.assertEqual((tools.root/"gate.json").read_bytes(), before)
        self.assertEqual(json.loads((tools.root/"submissions/1.json").read_text())["draft"], draft)
        with self.assertRaisesRegex(ValueError, "EXHAUSTED"):
            tools.submit(draft=draft)

    def test_period_revision_cannot_change_claim_kind_or_skip_full_revalidation(self):
        for name, change, error in (
            ("kind", {"op": "replace", "path": "/claims/0/kind", "value": "INFERENCE"}, "LOCAL_REVISION_OUT_OF_SCOPE"),
            ("incomplete", {"op": "replace", "path": "/claims/0/statement", "value": "仅补2025-01-01。"},
             "EQUITY_RESEARCH_FACT_PERIOD_LINEAGE_INCOMPLETE"),
        ):
            with self.subTest(name=name):
                tools, draft = self.period_task(name)
                first = tools.submit(draft=draft)
                second = tools.submit(draft={"base_draft_ref": first["draft_ref"], "changes": [change]})
                self.assertFalse(second["accepted"])
                self.assertEqual(second["validation_error"], error)
                with self.assertRaisesRegex(ValueError, "EXHAUSTED"):
                    tools.submit(draft=draft)

    def test_second_invalid_attempt_closes_without_third_or_overwriting_base(self):
        value = company_draft()
        value["confidence"] = "LOW"
        first = self.tools.submit(draft=value)
        before = (self.root/"submissions/1.json").read_bytes()
        second = self.tools.submit(draft={"base_draft_ref": first["draft_ref"], "changes": [
            {"op": "replace", "path": "/confidence", "value": "STILL_INVALID"},
        ]})
        self.assertFalse(second["accepted"])
        self.assertEqual((self.root/"submissions/1.json").read_bytes(), before)
        with self.assertRaisesRegex(ValueError, "EXHAUSTED"):
            self.tools.submit(draft=company_draft())

    def test_revision_cannot_change_other_field_or_identity(self):
        value = company_draft()
        value["confidence"] = "LOW"
        first = self.tools.submit(draft=value)
        before = (self.root/"submissions/1.json").read_bytes()
        rejected = self.tools.submit(draft={"base_draft_ref": first["draft_ref"], "changes": [
            {"op": "replace", "path": "/status", "value": "changed"},
        ]})
        self.assertFalse(rejected["accepted"])
        self.assertEqual(rejected["validation_error"], "LOCAL_REVISION_OUT_OF_SCOPE")
        for path in ("/run_id", "/claims/0/statement"):
            with self.assertRaisesRegex(ValueError, "EXHAUSTED"):
                self.tools.submit(draft={"base_draft_ref": first["draft_ref"], "changes": [
                    {"op": "replace", "path": path, "value": "changed"},
                ]})
        self.assertEqual((self.root/"submissions/1.json").read_bytes(), before)

    def test_receipt_cannot_select_another_task_or_tampered_report(self):
        self.tools.query(evidence_ids=["ev-revenue"])
        result = self.tools.submit(draft=company_draft())
        other = prepare_task(Path(self.tmp.name)/"other", research_input=alb_request(), gate=frozen_gate(),
                             security_id=SECURITY, capability="COMPANY_RESEARCH")
        foreign = ResearchTools(Path(self.tmp.name)/"other", access_token=other["access_token"])
        with self.assertRaises(ValueError):
            foreign.read_submission(draft_ref=result["draft_ref"])
        path = self.root/"submissions/1.json"
        stored = json.loads(path.read_text())
        stored["report"]["research"]["confidence"] = 0.99
        path.write_text(json.dumps(stored))
        with self.assertRaisesRegex(ValueError, "RECEIPT_BINDING_INVALID"):
            self.tools.read_submission(draft_ref=result["draft_ref"])

    def test_actual_calculation_choice_binds_value_order_and_claim_without_copying_metadata(self):
        self.tools.query(evidence_ids=["ev-revenue"])
        calc = self.tools.calculate(operation="ratio", evidence_ids=["ev-income", "ev-revenue"])
        catalog = self.tools.calculations()["calculations"]
        self.assertEqual(len(catalog), 1)
        draft = company_draft()
        draft["calculation_selections"] = [{"calculation_ref": catalog[0]["calculation_ref"],
                                            "claim_ids": [draft["claims"][0]["claim_id"]]}]
        result = self.tools.submit(draft=draft)
        self.assertTrue(result["accepted"], result)
        report = self.tools.read_submission(draft_ref=result["draft_ref"])
        support = report["calculation_support"][0]
        self.assertEqual(support["calculation"]["value"], calc["value"])
        self.assertEqual(support["calculation"]["input_evidence_refs"], ["ev-income", "ev-revenue"])
        self.assertEqual(report["research"]["claims"][0]["calculation_refs"], [support["calculation"]["calculation_id"]])
        self.assertEqual(len(list((self.root/"tools").glob("*.json"))), 2)

    def test_unknown_calculation_or_action_rejected(self):
        self.tools.query(evidence_ids=["ev-revenue"])
        value = company_draft()
        value["calculation_selections"] = [{"calculation_ref": "k."+"a"*12+"."+"b"*24,
                                            "claim_ids": [value["claims"][0]["claim_id"]]}]
        result = self.tools.submit(draft=value)
        self.assertFalse(result["accepted"])
        self.assertEqual(result["validation_error"], "NATIVE_RESEARCH_CALCULATION_SELECTION_INVALID")

    def test_independent_skeptic_submits_without_positive_context_or_fake_identity(self):
        root = Path(self.tmp.name)/"skeptic"
        prepared = prepare_task(root, research_input=alb_request(), gate=frozen_gate(),
                                security_id=SECURITY, capability="INDEPENDENT_FIRST_PASS")
        tools = ResearchTools(root, access_token=prepared["access_token"])
        tools.query(evidence_ids=["ev-revenue"])
        draft = {"status": "COMPLETE", "scope": SECURITY+" 独立失败路径研究",
                 "challenges": [{"challenge_id": "challenge-1", "statement": "收入事实不能单独证明持续盈利。",
                                 "evidence_refs": ["ev-revenue"], "assumption_ids": [], "resolution_evidence_needed": ["净利期间"]}],
                 "assumptions": [], "evidence_refs": ["ev-revenue"], "counter_evidence_refs": [],
                 "uncertainties": ["合成材料不证明真实投资结论。"], "data_gaps": [],
                 "invalidation_conditions": ["取得同期间净利证据后重评。"], "confidence": 0.5,
                 "confidence_rationale": "仅验证合成提交。"}
        result = tools.submit(draft=draft)
        self.assertTrue(result["accepted"], result)
        report = tools.read_submission(draft_ref=result["draft_ref"])
        self.assertEqual(report["role_scope"], "runtime_skeptic")
        self.assertEqual(report["caller_authentication"], "UNVERIFIED")

    def test_dimension_reuses_original_business_relations_without_execution_metadata(self):
        from tests.test_multidimensional_research_contracts import _report
        root = Path(self.tmp.name)/"fundamental"
        prepared = prepare_task(root, research_input=alb_request(), gate=frozen_gate(),
                                security_id=SECURITY, capability="FUNDAMENTAL_EVENT")
        tools = ResearchTools(root, access_token=prepared["access_token"])
        tools.query(evidence_ids=["ev-revenue"])
        old = _report(capability="FUNDAMENTAL_EVENT")
        fields = semantic_schema("FUNDAMENTAL_EVENT")["properties"]
        draft = {key: copy.deepcopy(value) for key, value in old.items() if key in fields}
        draft["calculation_selections"], draft["document_selections"] = [], []
        draft["claims"][0]["evidence_refs"] = ["ev-revenue"]
        draft["claims"][0].pop("calculation_refs")
        draft["observation_conditions"][0]["evidence_refs"] = ["ev-revenue"]
        result = tools.submit(draft=draft)
        self.assertTrue(result["accepted"], result)
        report = tools.read_submission(draft_ref=result["draft_ref"])
        self.assertEqual(report["research"]["claims"][0]["statement"], draft["claims"][0]["statement"])
        self.assertNotIn("execution", report["research"])
        self.assertEqual(report["content_verdict"], "NOT_REVIEWED")

    def test_submit_and_read_are_available_in_actual_mcp_dispatch(self):
        self.tools.query(evidence_ids=["ev-revenue"])
        reply = dispatch(self.tools, {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {
            "name": "research_submit", "arguments": {"draft": company_draft()},
        }})
        self.assertFalse(reply["result"]["isError"], reply)
        result = json.loads(reply["result"]["content"][0]["text"])
        self.assertTrue(result["accepted"], result)
        reply = dispatch(self.tools, {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {
            "name": "research_read_submission", "arguments": {"draft_ref": result["draft_ref"]},
        }})
        self.assertFalse(reply["result"]["isError"], reply)
