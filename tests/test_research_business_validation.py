"""迁移后的金额/计算业务边界；不调用旧Hook或模型。"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from product.runtime.calculation_handoff import VERSION as CALCULATION_VERSION, receipt_calculation, validate_tool_calculations
from product.runtime.hashing import canonical_hash, legacy_envelope_hash
from product.runtime.monetary import research_report_monetary_findings
from product.runtime.research_submission import VERSION, LEGACY_VERSION


class CalculationReceiptValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        ref = "research/calculations/" + hashlib.sha256(b"invocation").hexdigest()[:16] + "/tool-results.jsonl"
        self.task = {"run_id": "run", "invocation_id": "invocation", "agent": "runtime_company_analyst",
                     "calculation_ledger_ref": ref, "calculation_selection_version": CALCULATION_VERSION,
                     "allowed_evidence_ids": ["ev-earlier", "ev-later"]}
        self.invocation = {"calculation_ledger_ref": ref, "tool_permissions": ["fixture_math.calculate"]}
        self.ledger = self.root/ref
        self.ledger.parent.mkdir(parents=True)
        self.events = self.root/"events/mcp/events.jsonl"
        self.events.parent.mkdir(parents=True)

    def report(self, operation="ratio"):
        inputs = {key: self.task[key] for key in ("run_id", "invocation_id", "agent")}
        inputs.update(calculation_id="calc", operation=operation, evidence_ids=["ev-earlier", "ev-later"])
        output = {key: inputs[key] for key in ("run_id", "calculation_id", "operation", "evidence_ids")}
        if operation == "institutional_period_change":
            output.update(earlier_period="2025-Q4", later_period="2026-Q1",
                          changes=[{"institution_count": "2", "holder_quantity": "40", "holder_percent": "0.5"}])
        else:
            output["value"] = "2"
        event = {**inputs, "tool": "fixture_math.calculate", "input_hash": canonical_hash(inputs),
                 "output_hash": canonical_hash(output)}
        event["event_hash"] = legacy_envelope_hash(event, hash_field="event_hash")
        receipt = {**inputs, "output": output, "tool_event_hash": event["event_hash"]}
        receipt["receipt_hash"] = legacy_envelope_hash(receipt, hash_field="receipt_hash")
        self.ledger.write_text(json.dumps(receipt)+"\n")
        self.events.write_text(json.dumps(event)+"\n")
        return {"calculations": [receipt_calculation(receipt, self.task["calculation_ledger_ref"])]}

    def validate(self, report):
        validate_tool_calculations(report, task=self.task, invocation=self.invocation, run_dir=self.root)

    def test_exact_scalar_and_historical_compound_periods_units_are_preserved(self):
        for operation in ("ratio", "percent_change", "institutional_period_change"):
            report = self.report(operation)
            before = copy.deepcopy(report)
            self.validate(report)
            self.assertEqual(report, before)
            calculation = report["calculations"][0]
            if operation == "institutional_period_change":
                self.assertEqual(json.loads(calculation["value"])["earlier_period"], "2025-Q4")
                self.assertEqual(calculation["unit"], "mixed: institution_count / holder_quantity / holder_percent")
            else:
                for field, value in (("value", "999"), ("method", "guessed"), ("unit", "%")):
                    wrong = copy.deepcopy(report)
                    wrong["calculations"][0][field] = value
                    with self.subTest(operation=operation, field=field), self.assertRaisesRegex(ValueError, "RESULT_MISMATCH"):
                        self.validate(wrong)
        self.task.pop("calculation_selection_version")
        report = self.report()
        report["calculations"][0]["unit"] = "historical original unit"
        self.validate(report)  # 明确旧版本按原语义读取，不升级历史标记。

    def test_unknown_order_authorization_event_and_ledger_drift_fail_closed(self):
        for mutation, code in (("id", "RECORD_UNKNOWN"), ("order", "INPUT_MISMATCH"),
                               ("authorization", "NOT_AUTHORIZED"), ("event", "EVENT_INVALID"),
                               ("ledger", "LEDGER_INVALID"), ("shape", "DRAFT_INVALID")):
            report = self.report()
            self.invocation["tool_permissions"] = ["fixture_math.calculate"]
            if mutation == "id":
                report["calculations"][0]["calculation_id"] = "not-recorded"
            elif mutation == "order":
                report["calculations"][0]["input_evidence_refs"].reverse()
            elif mutation == "authorization":
                self.invocation["tool_permissions"] = []
            elif mutation == "event":
                self.events.write_text("")
            elif mutation == "ledger":
                self.ledger.write_text("{}\n")
            else:
                report["calculations"] = [None]
            with self.subTest(mutation=mutation), self.assertRaisesRegex(ValueError, code):
                self.validate(report)

    def test_business_import_closure_does_not_load_old_controllers(self):
        code = ("import sys; import product.runtime.calculation_handoff; import product.runtime.monetary; "
                "import product.runtime.research_submission; import product.runtime.multidimensional_stage; "
                "assert not any(n in sys.modules for n in "
                "('product.runtime.codex_hook_recorder','product.runtime.nested_codex'))")
        result = subprocess.run([sys.executable, "-B", "-c", code], cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)


class ResearchMonetaryLineageTests(unittest.TestCase):
    def setUp(self):
        self.source_id = "ev-licensed-1"
        self.short_id = "e.short.1"
        self.task = {
            "capability": "RESEARCH_REPORT", "submission_version": VERSION,
            "allowed_evidence_ids": [self.source_id],
        }
        self.source = {
            "evidence_id": self.source_id, "source_type": "SECONDARY_VENDOR",
            "value": {"content_tier": "LICENSED_API_CONTENT", "content": "14亿美元、20亿美元、50亿美元"},
        }
        self.packet = {
            "reference_map": {"evidence": {self.short_id: self.source_id}, "claims": {}},
            "dependency_reports": [],
        }
        self.claim = {
            "claim_id": "rr_claim_1", "statement": "1.4 billion USD、2.0 billion USD、5 billion USD",
            "evidence_refs": [self.short_id], "research_claim_refs": [],
        }

    def findings(self, *, claim=None, source=None, packet=None, task=None, selections=None):
        gate = {"allowed_evidence": [source or self.source]}
        gate["bundle_hash"] = canonical_hash(gate)
        return research_report_monetary_findings(
            {"claims": [claim or self.claim]}, task=task or self.task, gate=gate,
            reference_packet=packet or self.packet, selected_upstream=selections or [],
        )

    def test_exact_chinese_to_english_rewrite_needs_source_bound_receipt(self):
        findings = self.findings()
        self.assertEqual([item["amount_index"] for item in findings], [0, 1, 2])
        self.assertTrue(all(item["path"] == "claims[0].statement" for item in findings))
        self.assertEqual({item["identifier"] for item in self.findings(
            claim={**self.claim, "evidence_refs": [self.source_id]},
        )}, {self.short_id})
        self.assertNotIn("14亿美元", json.dumps(findings, ensure_ascii=False))
        self.assertEqual(findings[0]["source_value"], "14")
        self.assertEqual(findings[0]["reported_value"], "1.4")
        self.assertEqual(findings[0]["amount_index_basis"], "FINAL_ASSEMBLED_STATEMENT")
        selection = {
            "claim_id": "rr_claim_1", "calculation": {"input_evidence_refs": [self.source_id]},
            "verified_output": {
                "operation": "monetary_scale", "evidence_ids": [self.source_id],
                "conversions": [
                    {"source_scale": "亿", "target_scale": "billion",
                     "source_value": value, "converted_value": converted}
                    for value, converted in (("14", "1.4"), ("20", "2.0"), ("50", "5"))
                ],
            },
        }
        self.assertEqual(self.findings(selections=[selection]), [])

    def test_index_and_values_include_relation_text_after_corrected_core(self):
        claim = {**self.claim, "statement": "主段落保留14亿美元；关系解释仍写1.4 billion USD。"}
        original = copy.deepcopy(claim)
        findings = self.findings(claim=claim)
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["reported_value"], "1.4")
        self.assertEqual(findings[0]["source_value"], "14")
        self.assertEqual(findings[0]["amount_index"], 0)
        self.assertEqual(claim, original)

    def test_bare_dollar_billion_uses_same_guard_without_guessing_other_currencies(self):
        claim = {**self.claim, "statement": "$1.4 billion、$2.0 billion、$5 billion"}
        self.assertEqual([x["amount_index"] for x in self.findings(claim=claim)], [0, 1, 2])
        for prefix in ("HK", "HK ", "C", "CA ", "AUD ", "SGD ", "港币 ", "人民币 ", "€", "₹", "₩ ",
                       "X", "X ", "MXN ", "BRL ", "ZAR ", "XYZ: ", "XYZ："):
            with self.subTest(prefix=prefix):
                self.assertEqual(self.findings(claim={**claim, "statement": prefix + "$1.4 billion"}), [])
        for prefix in ("revenue ", "USD ", "US", "USD: "):
            with self.subTest(usd_prefix=prefix):
                self.assertEqual(len(self.findings(claim={**claim, "statement": prefix + "$1.4 billion"})), 1)
        self.assertEqual(self.findings(claim=claim, source={
            **self.source, "value": {"content_tier": "LICENSED_API_CONTENT", "content": claim["statement"]},
        }), [])
        selection = {"claim_id": self.claim["claim_id"],
                     "calculation": {"input_evidence_refs": [self.source_id]},
                     "verified_output": {"operation": "monetary_scale", "evidence_ids": [self.source_id],
                         "conversions": [{"source_scale": "亿", "target_scale": "billion",
                                          "source_value": "14", "converted_value": "1.4"}]}}
        self.assertEqual(self.findings(claim={**claim, "statement": "$1.4 billion"}, selections=[selection]), [])
        wrong_source = dict(selection)
        wrong_source["calculation"] = {"input_evidence_refs": ["ev-other"]}
        self.assertEqual(len(self.findings(selections=[wrong_source])), 3)

    def test_repeated_gap_context_is_exact_and_requires_located_monetary_error(self):
        from product.runtime.monetary import monetary_repetition_context
        claim = {**self.claim, "statement": "$1.4 billion and $2 billion"}
        findings = self.findings(claim=claim)
        # Only the located 1.4 error opens repeats, not another amount in the same claim.
        findings = findings[:1]
        draft = {"claims": [claim], "data_gaps": [
            {"description": "Still need to verify USD 1.40 billion.", "impact": "$2 billion"},
            {"description": "$2 billion"}, {"description": "MXN $1.4 billion"},
            {"description": "14亿美元"}, {"description": "$1.5 billion"},
            {"description": "￥ $1.4 billion"}, {"description": "XYZ: $1.4 billion"},
            {"description": "No number", "impact": "$1.4 billion"},
        ]}
        original = json.dumps(draft, ensure_ascii=False, sort_keys=True)
        expected = [{"path": "data_gaps[0].description",
                     "status": "REPEATED_EXPLICIT_AMOUNT_AUTHOR_RECHECK"}]
        self.assertEqual(monetary_repetition_context(draft, findings), expected)
        native = json.loads(original)
        native["claims"][0].pop("statement")
        native["claims"][0].update(core_statement="$1.4 billion", research_relation_clauses=[
            {"relation_statement": "and $2 billion"}])
        self.assertEqual(monetary_repetition_context(native, findings), expected)
        for wrong in ([], [{**findings[0], "code": "OTHER"}],
                      [{**findings[0], "path": "claims[99].statement"}],
                      [{**findings[0], "amount_index": -1}]):
            self.assertEqual(monetary_repetition_context(draft, wrong), [])
        self.assertEqual(json.dumps(draft, ensure_ascii=False, sort_keys=True), original)

    def test_original_amount_or_upstream_original_english_is_not_rewrite(self):
        original = {**self.claim, "statement": "原文给出14亿美元、20亿美元、50亿美元"}
        self.assertEqual(self.findings(claim=original), [])
        source = {**self.source, "value": {**self.source["value"],
            "content": "14亿美元及1.4 billion USD、20亿美元及2.0 billion USD、50亿美元及5 billion USD"}}
        self.assertEqual(self.findings(source=source), [])
        packet = {**self.packet, "reference_map": {
            "evidence": {self.short_id: self.source_id},
            "claims": {"c.short.1": {"report_id": "upstream", "claim_id": "upstream_claim"}},
        }, "dependency_reports": [{"report_id": "upstream", "claims": [{
            "claim_id": "upstream_claim", "statement": self.claim["statement"],
        }]}]}
        claim = {**self.claim, "research_claim_refs": ["c.short.1"]}
        self.assertEqual(self.findings(claim=claim, packet=packet), [])

    def test_local_claim_id_takes_priority_over_same_named_upstream(self):
        packet = {**self.packet, "dependency_reports": [{
            "report_id": "upstream", "claims": [{
                "claim_id": "same_name", "statement": "1.4 billion USD",
            }],
        }]}
        gate = {"allowed_evidence": [self.source]}
        gate["bundle_hash"] = canonical_hash(gate)
        draft = {"claims": [{**self.claim, "statement": "1.4 billion USD",
                             "research_claim_refs": ["same_name"]}, {
                                 "claim_id": "same_name", "statement": "本地说明。",
                             }]}
        findings = research_report_monetary_findings(
            draft, task=self.task, gate=gate, reference_packet=packet,
            selected_upstream=[],
        )
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["path"], "claims[0].statement")

    def test_guard_does_not_expand_to_ambiguous_or_other_protocols(self):
        other = {**self.source, "evidence_id": "ev-other", "value": {
            "content_tier": "LICENSED_API_CONTENT", "content": "另一来源亦写14亿美元"}}
        gate = {"allowed_evidence": [self.source, other]}
        gate["bundle_hash"] = canonical_hash(gate)
        packet = {**self.packet, "reference_map": {"evidence": {
            self.short_id: self.source_id, "e.other": "ev-other"}, "claims": {}}}
        task = {**self.task, "allowed_evidence_ids": [self.source_id, "ev-other"]}
        self.assertEqual([x["amount_index"] for x in research_report_monetary_findings(
            {"claims": [{**self.claim, "evidence_refs": [self.short_id, "e.other"]}]},
            task=task, gate=gate, reference_packet=packet, selected_upstream=[],
        )], [1, 2])
        self.assertEqual(research_report_monetary_findings(
            {"claims": [{**self.claim, "statement": "1.4 billion USD",
                         "evidence_refs": [self.short_id, "e.other"]}]},
            task=task, gate=gate, reference_packet=packet, selected_upstream=[],
        ), [])
        self.assertEqual(self.findings(claim={**self.claim,
            "statement": "9 billion USD"}), [])
        self.assertEqual(self.findings(claim={**self.claim,
            "statement": "1.4 billion EUR"}), [])
        repeated = {**self.source, "value": {**self.source["value"],
            "content": "指标A为14亿美元，指标B同为14亿美元"}}
        self.assertEqual(len(self.findings(source=repeated, claim={**self.claim,
            "statement": "1.4 billion USD"})), 1)
        self.assertEqual(self.findings(task={**self.task,
            "submission_version": LEGACY_VERSION}), [])
        self.assertEqual(self.findings(task={**self.task,
            "capability": "FUNDAMENTAL_EVENT"}), [])
        gate = {"allowed_evidence": [self.source], "bundle_hash": "wrong"}
        with self.assertRaisesRegex(ValueError, "DIMENSION_REPORT_MONETARY_GATE_INVALID"):
            research_report_monetary_findings(
                {"claims": [self.claim]}, task=self.task, gate=gate,
                reference_packet=self.packet, selected_upstream=[],
            )

    def test_three_cited_sources_one_repeated_management_guidance_is_located(self):
        licensed = {**self.source, "value": {**self.source["value"],
            "content": "管理层2028财年指引上调至180亿美元。2028财年指引为180亿美元。"}}
        others = [
            {**self.source, "evidence_id": "ev-other-1", "value": {
                "content_tier": "LICENSED_API_CONTENT", "content": "另有经营分析。"}},
            {**self.source, "evidence_id": "ev-other-2", "value": {
                "content_tier": "PUBLIC_FILING", "content": "近期营收事实。"}},
        ]
        gate = {"allowed_evidence": [licensed, *others]}
        gate["bundle_hash"] = canonical_hash(gate)
        task = {**self.task, "allowed_evidence_ids": [self.source_id, "ev-other-1", "ev-other-2"]}
        packet = {**self.packet, "reference_map": {"evidence": {
            self.short_id: self.source_id, "e.other.1": "ev-other-1", "e.other.2": "ev-other-2",
        }, "claims": {}}}
        claim = {**self.claim, "statement": "作者预测2028财年收入为18.0 billion USD",
                 "evidence_refs": ["e.other.1", self.short_id, "e.other.2"]}
        findings = research_report_monetary_findings(
            {"claims": [claim]}, task=task, gate=gate,
            reference_packet=packet, selected_upstream=[],
        )
        self.assertEqual([(item["path"], item["identifier"]) for item in findings],
                         [("claims[0].statement", self.short_id)])
        self.assertNotIn("管理层", json.dumps(findings, ensure_ascii=False))
        self.assertEqual(research_report_monetary_findings(
            {"claims": [{**claim, "statement": "管理层指引为180亿美元"}]},
            task=task, gate=gate, reference_packet=packet, selected_upstream=[],
        ), [])

    def test_dollar_prefixed_yi_is_located_without_guessing_other_currency(self):
        licensed = {**self.source, "value": {**self.source["value"],
            "content": "截至期末持有$26亿现金及$45亿总债务；现金$26亿。"}}
        other = {**self.source, "evidence_id": "ev-other", "value": {
            "content_tier": "PUBLIC_FILING", "content": "另有并购事实。"}}
        gate = {"allowed_evidence": [licensed, other]}
        gate["bundle_hash"] = canonical_hash(gate)
        task = {**self.task, "allowed_evidence_ids": [self.source_id, "ev-other"]}
        packet = {**self.packet, "reference_map": {"evidence": {
            self.short_id: self.source_id, "e.other": "ev-other",
        }, "claims": {}}}
        claim = {**self.claim, "statement": "现金2.6 billion USD、债务4.5 billion USD",
                 "evidence_refs": [self.short_id, "e.other"]}
        findings = research_report_monetary_findings(
            {"claims": [claim]}, task=task, gate=gate,
            reference_packet=packet, selected_upstream=[],
        )
        self.assertEqual([item["amount_index"] for item in findings], [0, 1])
        self.assertEqual({item["source_unit"] for item in findings}, {"$亿"})
        self.assertEqual({item["identifier"] for item in findings}, {self.short_id})
        english_context = {**licensed, "value": {**licensed["value"],
            "content": "cash $26亿; debt $45亿."}}
        gate = {"allowed_evidence": [english_context, other]}
        gate["bundle_hash"] = canonical_hash(gate)
        self.assertEqual(len(research_report_monetary_findings(
            {"claims": [claim]}, task=task, gate=gate,
            reference_packet=packet, selected_upstream=[],
        )), 2)
        gate = {"allowed_evidence": [licensed, other]}
        gate["bundle_hash"] = canonical_hash(gate)
        self.assertEqual(research_report_monetary_findings(
            {"claims": [{**claim, "statement": "现金$26亿、债务$45亿"}]},
            task=task, gate=gate, reference_packet=packet, selected_upstream=[],
        ), [])
        for content in (
            "截至期末持有HK$26亿现金及C$45亿总债务。",
            "截至期末持有HK $26亿现金及港币$45亿总债务。",
            "截至期末持有€$26亿现金及人民币 $45亿总债务。",
            "截至期末持有A$26亿现金及S$45亿总债务。",
            "截至期末持有₹$26亿现金及₩ $45亿总债务。",
        ):
            with self.subTest(content=content):
                other_currency = {**licensed, "value": {**licensed["value"],
                    "content": content}}
                gate = {"allowed_evidence": [other_currency, other]}
                gate["bundle_hash"] = canonical_hash(gate)
                self.assertEqual(research_report_monetary_findings(
                    {"claims": [claim]}, task=task, gate=gate,
                    reference_packet=packet, selected_upstream=[],
                ), [])
        source_english = {**other, "value": {**other["value"],
            "content": "2.6 billion USD in cash."}}
        gate = {"allowed_evidence": [licensed, source_english]}
        gate["bundle_hash"] = canonical_hash(gate)
        self.assertEqual([item["amount_index"] for item in research_report_monetary_findings(
            {"claims": [claim]}, task=task, gate=gate,
            reference_packet=packet, selected_upstream=[],
        )], [1])
        selection = {"claim_id": "rr_claim_1",
                     "calculation": {"input_evidence_refs": [self.source_id]},
                     "verified_output": {"operation": "monetary_scale",
                         "evidence_ids": [self.source_id], "conversions": [
                             {"source_scale": "亿", "target_scale": "billion",
                              "source_value": original, "converted_value": target}
                             for original, target in (("26", "2.6"), ("45", "4.5"))]}}
        gate = {"allowed_evidence": [licensed, other]}
        gate["bundle_hash"] = canonical_hash(gate)
        self.assertEqual(research_report_monetary_findings(
            {"claims": [claim]}, task=task, gate=gate,
            reference_packet=packet, selected_upstream=[selection],
        ), [])
        competitor = {**other, "value": {"content_tier": "LICENSED_API_CONTENT",
            "content": "另一个来源也写$26亿现金。"}}
        gate = {"allowed_evidence": [licensed, competitor]}
        gate["bundle_hash"] = canonical_hash(gate)
        self.assertEqual([item["amount_index"] for item in research_report_monetary_findings(
            {"claims": [claim]}, task=task, gate=gate,
            reference_packet=packet, selected_upstream=[],
        )], [1])

