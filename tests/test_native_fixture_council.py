"""同一业务工具贯通原fixture研究/独立反证/CIO/硬Risk；零模型，非实际宿主证明。"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from product.tools.fixture_input import prepare_fixture_request
from product.tools.research import prepare_task, ResearchTools
from product.tools.report_contracts import semantic_schema
from product.tools.report_reading import render_report
from product.tools.report_history import archive_report, read_archive
from product.runtime.research_memory import ResearchMemory
from tests.test_native_research_reading import skeptic_draft
from tests.test_native_research_tools import frozen_gate, SECURITY
from tests.test_single_stock_input import alb_request

ROOT = Path(__file__).resolve().parents[1]


class NativeFixtureCouncilTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.tmp.name)
        self.prepared = prepare_fixture_request(ROOT/"evals/fixtures/codex-native/normal-research.json", research_question="仅研究合成fixture。")
        self.input, self.gate = self.prepared["input"], self.prepared["gate"]
        self.security = self.input["fixture"]["portfolio"]["positions"][0]["security_id"]
        self.reports = []
        for cap in ("FIXTURE_COMPANY_RESEARCH", "INDEPENDENT_FIRST_PASS"):
            tools = self.tools(cap)
            ref = self.gate["allowed_evidence_ids"][0]
            tools.query(evidence_ids=[ref])
            if cap == "FIXTURE_COMPANY_RESEARCH":
                draft = {"status": "COMPLETE", "scope": self.security,
                    "claims": [{"claim_id": "claim-1", "statement": "合成事实，不作真实投资结论。", "kind": "FACT", "evidence_refs": [ref], "assumption_ids": []}],
                    "assumptions": [], "counter_evidence_refs": [], "uncertainties": [], "data_gaps": [],
                    "invalidation_conditions": [], "confidence": 0.5, "confidence_rationale": "仅验证业务。", "calculation_selections": []}
            else:
                draft = skeptic_draft()
                draft["scope"] = self.security+"独立反证"
                draft["challenges"][0]["evidence_refs"] = [ref]
                draft["evidence_refs"] = [ref]
            result = tools.submit(draft=draft)
            self.assertTrue(result["accepted"], result)
            self.reports.append(tools.read_submission(draft_ref=result["draft_ref"]))

    def tearDown(self):
        self.tmp.cleanup()

    def tools(self, cap, dependencies=(), suffix=""):
        path = self.root/(cap+suffix)
        task = prepare_task(path, research_input=self.input, gate=self.gate, security_id=self.security,
                            capability=cap, dependency_reports=dependencies)
        return ResearchTools(path, access_token=task["access_token"])

    def cio(self):
        tools = self.tools("FIXTURE_COUNCIL_DECISION", self.reports)
        tools.query(evidence_ids=[self.gate["allowed_evidence_ids"][0]])
        tools.read_reports(report_ids=[r["report_id"] for r in self.reports])
        return tools

    def draft(self, *, target=(0.4, 0.5)):
        return {"status": "COMPLETE", "action": "HOLD", "target_weight_range": list(target), "maximum_notional": 1000,
                "time_horizon": "合成研究期", "thesis": "仅为业务夹具", "counter_thesis": "真实经营未知",
                "consensus": [], "conflicts": [], "unresolved_questions": [], "invalidation_conditions": ["资料变化"],
                "confidence": 0.5, "confidence_rationale": "不证明真实研究质量", "evidence_refs": [self.gate["allowed_evidence_ids"][0]],
                "no_trade_reason": None, "no_trade_explanation": None, "reevaluation_conditions": [], "advisory_only": True,
                "report_selections": [r["report_id"] for r in self.reports]}

    def test_fixture_business_reports_cio_and_original_hard_risk_without_old_execution_identity(self):
        tools = self.cio()
        result = tools.submit(draft=self.draft())
        self.assertTrue(result["accepted"], result)
        report = tools.read_submission(draft_ref=result["draft_ref"])
        self.assertEqual(report["risk_status"], "APPROVED")
        self.assertEqual(report["fixture_decision"]["final_action"], "HOLD")
        self.assertEqual(report["research"]["current_weight"], 0.5)
        self.assertEqual(report["host_execution"], "UNVERIFIED")
        self.assertNotIn("model", report)
        self.assertIn("合成fixture", render_report(report))
        memory = ResearchMemory(self.root/"memory")
        stored = archive_report(tools, draft_ref=result["draft_ref"], memory=memory)
        with patch("product.tools.fixture_input._source", side_effect=AssertionError("Historical reader does not require current fixture file")):
            self.assertEqual(read_archive(memory, object_ref=stored["object_ref"], object_hash=stored["object_hash"])["report"], report)

    def test_original_hard_bounds_allow_one_author_revision_and_never_a_third(self):
        tools = self.cio()
        first = tools.submit(draft=self.draft(target=(0.55, 0.8)))
        self.assertTrue(first["accepted"], first)
        original = tools.read_submission(draft_ref=first["draft_ref"])
        self.assertEqual(original["risk_status"], "REVISE_REQUIRED")
        self.assertEqual(original["fixture_decision"]["terminal_state"], "ONE_CIO_REVISION_REQUIRED")
        self.assertIn("/target_weight_range", first["allowed_paths"])
        second = tools.submit(draft={"base_draft_ref": first["draft_ref"],
            "changes": [{"op": "replace", "path": "/target_weight_range", "value": [0.56, 0.79]}]})
        self.assertTrue(second["accepted"], second)
        final = tools.read_submission(draft_ref=second["draft_ref"])
        self.assertEqual(final["fixture_decision"]["final_action"], "NO_TRADE")
        self.assertEqual(final["fixture_decision"]["reason_code"], "RISK_VETO")
        self.assertEqual(tools.read_submission(draft_ref=first["draft_ref"]), original)
        with self.assertRaisesRegex(ValueError, "SUBMISSION_EXHAUSTED"):
            tools.submit(draft=self.draft())

    def test_real_input_cannot_obtain_fixture_action_capability(self):
        for cap in ("FIXTURE_COMPANY_RESEARCH", "FIXTURE_COUNCIL_DECISION"):
            path = self.root/("real-"+cap)
            with self.assertRaisesRegex(ValueError, "FIXTURE_INPUT_REQUIRED"):
                prepare_task(path, research_input=alb_request(), gate=frozen_gate(), security_id=SECURITY, capability=cap)
            self.assertFalse(path.exists())

    def test_fixture_cio_cannot_skip_upstream_read_or_supply_self_authored_weight(self):
        tools = self.tools("FIXTURE_COUNCIL_DECISION", self.reports)
        tools.query(evidence_ids=[self.gate["allowed_evidence_ids"][0]])
        result = tools.submit(draft=self.draft())
        self.assertFalse(result["accepted"])
        self.assertEqual(result["validation_error"], "NATIVE_CIO_REPORT_CONSUMPTION_INVALID")
        other = self.tools("FIXTURE_COUNCIL_DECISION", self.reports, suffix="-weight")
        changed = {**self.draft(), "current_weight": 0.1}
        self.assertFalse(other.submit(draft=changed)["accepted"])

    def test_safe_fixture_input_and_stale_data_stop_before_tasks_or_models(self):
        for name, reason in (("invalid-portfolio.json", "INPUT_INVALID"), ("future-or-stale.json", "STALE_DATA")):
            result = prepare_fixture_request(ROOT/"evals/fixtures/codex-native"/name, research_question="合成安全门槛。")
            self.assertEqual(result["terminal_state"], "SAFE_NO_TRADE")
            self.assertEqual(result["reason_code"], reason)
            self.assertEqual(result["model_calls"], 0)
