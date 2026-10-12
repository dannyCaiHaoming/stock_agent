"""原生报告依赖与CIO消费的零模型纵向业务检查。"""
from __future__ import annotations
import copy
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from product.runtime.hashing import legacy_envelope_hash
from product.tools.research import prepare_task, ResearchTools
from product.tools.report_contracts import semantic_schema
from product.tools.report_reading import CORE_FORWARD, render_report
from tests.test_native_research_tools import AT, SECURITY, frozen_gate
from tests.test_native_research_submission import company_draft
from tests.test_single_stock_input import alb_request
from tests.test_multidimensional_research_contracts import _report


def complete_gate():
    gate = frozen_gate()
    for fact in gate["allowed_evidence"]:
        fact["source_type"] = "sec"
    for ref, field, sid, provider in (
        ("ev-rate", "us_treasury_10y_yield", "US:MARKET", "fred"),
    ):
        gate["allowed_evidence"].append({"evidence_id": ref, "security_id": sid, "semantic_field": field,
            "value": "10", "unit": "ratio", "source_id": f"synthetic-{provider}",
            "source_type": provider, "as_of": AT, "retrieved_at": AT})
        gate["allowed_evidence_ids"].append(ref)
    # Synthetic aligned rows exercise the existing math; not an exchange-calendar proof.
    for index in range(65):
        day = (date(2026, 7, 1) + timedelta(days=index)).isoformat()
        for sid in (SECURITY, "US:SPY"):
            for field in ("historical_close_price", "adjusted_close_price"):
                ref = "series-" + sid.replace(":", "-") + "-" + field + "-" + str(index)
                gate["allowed_evidence"].append({"evidence_id": ref, "security_id": sid,
                    "semantic_field": field, "value": str(100 + index), "unit": "USD_per_share",
                    "source_id": "synthetic-yahoo", "source_type": "yahoo",
                    "as_of": day+"T00:00:00Z", "retrieved_at": day+"T00:00:00Z", "metadata": {"trading_date": day}})
                gate["allowed_evidence_ids"].append(ref)
    gate["bundle_hash"] = legacy_envelope_hash(gate, hash_field="bundle_hash")
    return gate


def skeptic_draft():
    return {"status": "COMPLETE", "scope": SECURITY+"独立研究",
        "challenges": [{"challenge_id": "challenge-1", "statement": "盈利持续性仍需核实。",
                        "evidence_refs": ["ev-revenue"], "assumption_ids": [], "resolution_evidence_needed": []}],
        "assumptions": [], "evidence_refs": ["ev-revenue"], "counter_evidence_refs": [],
        "uncertainties": [], "data_gaps": [], "invalidation_conditions": [],
        "confidence": 0.5, "confidence_rationale": "仅验证合成业务接口。"}


class NativeResearchReadingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="/private/tmp")
        self.root = Path(self.tmp.name)
        self.source, self.gate = alb_request(), complete_gate()
        self.reports = []
        for cap in sorted(CORE_FORWARD | {"INDEPENDENT_FIRST_PASS"}):
            prepared = prepare_task(self.root/cap.lower(), research_input=self.source, gate=self.gate,
                                    security_id=SECURITY, capability=cap, benchmark_id="US:SPY")
            tools = ResearchTools(self.root/cap.lower(), access_token=prepared["access_token"])
            ref = "ev-rate" if cap in {"MACRO_CONTEXT", "MARKET_STATE"} else "ev-revenue"
            if cap != "TECHNICAL_STRUCTURE":
                tools.query(evidence_ids=[ref])
            if cap == "COMPANY_RESEARCH":
                draft = company_draft()
            elif cap == "INDEPENDENT_FIRST_PASS":
                draft = skeptic_draft()
            else:
                old = _report(capability=cap)
                fields = semantic_schema(cap)["properties"]
                draft = {key: copy.deepcopy(value) for key, value in old.items() if key in fields}
                draft["calculation_selections"], draft["document_selections"] = [], []
                for claim in draft["claims"]:
                    claim.pop("calculation_refs", None)
                    claim["evidence_refs"] = [ref]
                for condition in draft["observation_conditions"]:
                    condition["evidence_refs"] = [ref]
                if cap == "TECHNICAL_STRUCTURE":
                    entry = next(item for item in tools.calculations()["calculations"] if "relative_return" in item["calculation"]["method"])
                    draft["calculation_selections"] = [{"calculation_ref": entry["calculation_ref"], "claim_ids": [draft["claims"][0]["claim_id"]]}]
                    for claim in draft["claims"]:
                        claim["evidence_refs"] = []
                    for condition in draft["observation_conditions"]:
                        condition["evidence_refs"] = []
            result = tools.submit(draft=draft)
            self.assertTrue(result["accepted"], (cap, result))
            self.reports.append(tools.read_submission(draft_ref=result["draft_ref"]))

    def tearDown(self):
        self.tmp.cleanup()

    def cio(self):
        path = self.root/"cio"
        prepared = prepare_task(path, research_input=self.source, gate=self.gate, security_id=SECURITY,
                                capability="RESEARCH_SYNTHESIS", dependency_reports=self.reports)
        return ResearchTools(path, access_token=prepared["access_token"])

    def draft(self):
        refs = [r["report_id"] for r in self.reports]
        skeptic = next(r for r in self.reports if r["capability"] == "INDEPENDENT_FIRST_PASS")
        return {"status": "LOW_CONFIDENCE", "analysis_horizon": "两个季度，属于分析假设",
            "judgment": "合成材料不能证明真实公司前景。", "reasoning": "保留来源限制与独立反证。",
            "thesis": "仅验证接口", "counter_thesis": "不证明投资判断", "consensus": [],
            "conflicts": ["真实经营仍未知"], "business_outlook": "未知", "price_attractiveness": "未知",
            "key_facts": [{"fact": "合成收入100", "report_ids": [refs[0]], "evidence_refs": ["ev-revenue"],
                           "reasoning": "只是合成业务字段。"}],
            "challenge_dispositions": [{"report_id": skeptic["report_id"], "challenge_id": "challenge-1",
                                        "disposition": "UNRESOLVED", "rationale": "无法判定持续性。",
                                        "judgment_impact": "保持未知", "reevaluate_when": "新资料取得后"}],
            "macro_market_transmission": [{"channel": "利率", "report_ids": [refs[0]], "mechanism": "融资成本",
                                           "assessment": "未知", "limitations": "合成资料不作因果证明"}],
            "unresolved_questions": ["真实研究未执行"],
            "invalidation_conditions": ["真实披露"], "reevaluation_conditions": ["真实披露"],
            "watch_plan": [{"item": "经营资料", "trigger": "公开披露", "reassess_on": "资料取得后"}],
            "confidence_rationale": "不代表内容通过。", "limitations": ["合成样本"],
            "evidence_refs": ["ev-revenue"], "report_selections": refs}

    def test_dependencies_are_business_ready_not_claimed_host_or_content_pass(self):
        tools = self.cio()
        context = tools.context()
        self.assertNotIn("dependency_reports", context)
        self.assertEqual(len(context["report_catalog"]), 7)
        self.assertEqual(context["host_execution"], "UNVERIFIED")
        read = tools.read_reports(report_ids=[r["report_id"] for r in self.reports])
        self.assertEqual(read["reports"], self.reports)
        self.assertEqual(read["execution_observation"], "UNVERIFIED")

    def test_missing_dependency_wrong_target_or_gate_rejected_before_task_creation(self):
        for reports in (self.reports[:-1], [dict(r, gate_hash="a"*64) for r in self.reports]):
            path = self.root/"bad-cio"
            with self.assertRaises(ValueError):
                prepare_task(path, research_input=self.source, gate=self.gate, security_id=SECURITY,
                             capability="RESEARCH_SYNTHESIS", dependency_reports=reports)
            self.assertFalse(path.exists())

    def test_skeptic_cannot_receive_or_read_positive_reports(self):
        with self.assertRaisesRegex(ValueError, "CONTEXT_ISOLATION_VIOLATION"):
            prepare_task(self.root/"contaminated", research_input=self.source, gate=self.gate,
                         security_id=SECURITY, capability="INDEPENDENT_FIRST_PASS", dependency_reports=self.reports)
        task = json.loads((self.root/"independent_first_pass/task.json").read_text())
        access = json.loads((self.root/"independent_first_pass/access.json").read_text())
        tools = ResearchTools(self.root/"independent_first_pass", access_token=access["token"])
        with self.assertRaisesRegex(ValueError, "REPORT_READ_FORBIDDEN"):
            tools.read_reports(report_ids=[self.reports[0]["report_id"]])

    def test_unread_reports_reject_even_if_evidence_queried(self):
        tools = self.cio()
        tools.query(evidence_ids=["ev-revenue"])
        result = tools.submit(draft=self.draft())
        self.assertFalse(result["accepted"])
        self.assertEqual(result["validation_error"], "NATIVE_CIO_REPORT_CONSUMPTION_INVALID")

    def test_query_read_selection_synthesis_and_chinese_are_same_report(self):
        tools = self.cio()
        tools.query(evidence_ids=["ev-revenue"])
        tools.read_reports(report_ids=[r["report_id"] for r in self.reports])
        result = tools.submit(draft=self.draft())
        self.assertTrue(result["accepted"], result)
        report = tools.read_submission(draft_ref=result["draft_ref"])
        self.assertEqual(report["research"]["judgment"], self.draft()["judgment"])
        text = render_report(report)
        self.assertIn(self.draft()["reasoning"], text)
        self.assertIn("作者身份", text)
        self.assertEqual(report["content_verdict"], "NOT_REVIEWED")
